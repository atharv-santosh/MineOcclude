#!/usr/bin/env python3
"""Outcome-blind structural replay of frozen amendment authority on t01-t04."""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from mineocclude.regime_a import (  # noqa: E402
    BIN_BOUNDS,
    RegimeAError,
    classify_visibility,
    sha256_file,
    validate_capture_temporal_alignment,
)
from mineocclude.vision.magenta import HsvRange, detect_magenta  # noqa: E402
from scripts.calibrate_regime_a_directional_visibility import (  # noqa: E402
    TRANSITIONAL,
    longest_run,
)
from scripts.run_regime_a import detector_rgb_rows, read_jsonl  # noqa: E402

DETECTOR_CONFIG = (
    ROOT
    / "docs/status/person_e_phase3_step3_1_candidate_freeze_v0_1/detector_candidate_config.json"
)


def replay_one(
    item: tuple[dict[str, object], Path, dict[str, object]]
) -> dict[str, object]:
    spec, root, authority = item
    state = read_jsonl(root / "raw/server_state.jsonl")
    ticks = read_jsonl(root / "raw/client_tick.jsonl")
    actions = read_jsonl(root / "raw/actions.jsonl")
    if not (len(state) == len(ticks) == len(actions) == 260):
        raise RegimeAError(f"{spec['trajectory_spec_id']}: raw stream count mismatch")
    pngs = sorted((root / "raw/frames").glob("*.png"))
    if len(pngs) != 260 or [path.name for path in pngs] != [
        f"{index:06d}.png" for index in range(260)
    ]:
        raise RegimeAError(f"{spec['trajectory_spec_id']}: PNG inventory mismatch")
    capture_hash = str(spec["raw_capture_spec_hash"])
    if not all(
        row.get("trajectory_spec_id") == spec["trajectory_spec_id"]
        and row.get("spec_hash") == capture_hash
        and row.get("seed") == spec["seed"]
        and row.get("server_tick") == index
        and row.get("target_respawn_count") == 0
        for index, row in enumerate(state)
    ):
        raise RegimeAError(f"{spec['trajectory_spec_id']}: raw capture identity mismatch")
    if not all(
        tick.get("server_tick") == index
        and tick.get("render_frame_idx") == index
        and tick.get("tick_queue_depth_at_capture") == 0
        and action.get("server_tick") == index
        and action.get("render_frame_idx") == index
        and action.get("action_idx") == index
        for index, (tick, action) in enumerate(zip(ticks, actions, strict=True))
    ):
        raise RegimeAError(f"{spec['trajectory_spec_id']}: capture ACK identity mismatch")
    alignment = validate_capture_temporal_alignment(state, ticks)
    config = json.loads(DETECTOR_CONFIG.read_text())["configuration"]["detector_settings"]
    thresholds = tuple(HsvRange(*values) for values in config["hsv_ranges"])
    labels: list[str] = []
    for index, row in enumerate(state):
        result = detect_magenta(
            detector_rgb_rows(root / f"raw/frames/{index:06d}.png", expected_size=(640, 360)),
            hsv_ranges=thresholds,
            min_area_pixels=config["min_area_pixels"],
            max_area_pixels=config["max_area_pixels"],
            open_iterations=config["open_iterations"],
            close_iterations=config["close_iterations"],
            morphology_radius_pixels=config["morphology_radius_pixels"],
            connectivity=config["connectivity"],
        )
        labels.append(
            classify_visibility(
                "visible" if row["geometric_visible"] else "occluded", result.status
            )
        )
    onset = next(
        (
            index
            for index in range(len(labels) - 18)
            if labels[index : index + 19] == ["OCCLUDED_AGREEMENT"] * 19
        ),
        None,
    )
    if onset is None:
        raise RegimeAError(f"{spec['trajectory_spec_id']}: no 19-frame hidden support")
    entry_start = onset
    while entry_start > 0 and labels[entry_start - 1] in TRANSITIONAL:
        entry_start -= 1
    last_hidden = onset
    while last_hidden + 1 < len(labels) and labels[last_hidden + 1] == "OCCLUDED_AGREEMENT":
        last_hidden += 1
    geometric_hidden = [index for index, row in enumerate(state) if not row["geometric_visible"]]
    geometric_visible = [index for index, row in enumerate(state) if row["geometric_visible"]]
    last_geometric_hidden = geometric_hidden[-1]
    first_geometric_visible_after = next(
        index for index in geometric_visible if index > last_geometric_hidden
    )
    entry_run = longest_run(labels, geometric_hidden[0], onset)
    exit_run = longest_run(labels, last_hidden + 1, first_geometric_visible_after + 1)
    direction = str(spec["direction"])
    direction_authority = dict(authority[direction])
    entry_guard = int(direction_authority["g_entry_frames"])
    exit_guard = int(direction_authority["g_exit_frames"])
    targets = list(range(onset, onset + 19))
    bin_counts = {
        name: stop - start + 1 for name, (start, stop) in BIN_BOUNDS.items()
    }
    inventory_path = root / "activation_inventory.json"
    activation_indices = None
    if inventory_path.is_file():
        activation_indices = json.loads(inventory_path.read_text()).get(
            "target_model_frame_indices"
        )
    return {
        "trajectory_spec_id": spec["trajectory_spec_id"],
        "seed": spec["seed"],
        "direction": direction,
        "raw_capture_spec_hash": capture_hash,
        "amended_spec_hash": spec["spec_hash"],
        "frame_count": 260,
        "capture_ack_identity_exact": True,
        "temporal_alignment": alignment,
        "observed_entry_transition_run_frames": entry_run,
        "amended_g_entry_frames": entry_guard,
        "entry_guard_pass": entry_run <= entry_guard,
        "observed_exit_transition_run_frames": exit_run,
        "amended_g_exit_frames": exit_guard,
        "exit_guard_pass": exit_run <= exit_guard,
        "observed_target_model_frame_indices": targets,
        "eligible_target_count": len(targets),
        "bin_counts": bin_counts,
        "all_five_bins_feasible": onset >= 15 and len(targets) == 19,
        "existing_activation_target_indices": activation_indices,
        "existing_serialized_activations_exactly_reusable": (
            activation_indices == targets if activation_indices is not None else None
        ),
        "pass": entry_run <= entry_guard
        and exit_run <= exit_guard
        and onset >= 15
        and len(targets) == 19,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--authority", type=Path, required=True)
    parser.add_argument("--scientific-runtime", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    specs = [
        json.loads(line)
        for line in args.manifest.read_text().splitlines()
        if line.strip()
    ][:4]
    if [row["trajectory_spec_id"] for row in specs] != [
        f"regime_a_v2_t{index:02d}" for index in range(1, 5)
    ]:
        raise RegimeAError("amended replay manifest t01-t04 identity mismatch")
    authority = json.loads(args.authority.read_text())
    if (
        authority.get("status") != "FROZEN_OUTCOME_BLIND_AFTER_STRUCTURAL_QC_TRIGGER"
        or authority.get("t04_used_in_numerical_derivation") is not False
        or authority.get("scientific_decoding_outcomes_computed_before_freeze") != 0
    ):
        raise RegimeAError("amended authority is not frozen outcome-blind")
    roots = []
    for spec in specs:
        identity = str(spec["trajectory_spec_id"])
        if identity == "regime_a_v2_t04":
            root = (
                args.scientific_runtime
                / "trajectories"
                / f".{identity}.{str(spec['raw_capture_spec_hash'])[:16]}.partial"
            )
        else:
            root = args.scientific_runtime / "trajectories" / identity
        roots.append(root)
    if not all(root.is_dir() for root in roots):
        raise RegimeAError("scientific replay root is missing")
    with concurrent.futures.ProcessPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(replay_one, zip(specs, roots, [authority] * 4, strict=True)))
    all_pass = all(bool(row["pass"]) for row in results)
    activations_reusable = all(
        row["existing_serialized_activations_exactly_reusable"] is True
        for row in results[:3]
    )
    report = {
        "schema_version": "regime-a-v2-amendment-1-scientific-structural-replay-v1.0",
        "authority_sha256": sha256_file(args.authority),
        "amended_manifest_sha256": sha256_file(args.manifest),
        "authority_frozen_before_scientific_replay": True,
        "t04_used_in_authority_derivation": False,
        "scientific_outcomes_computed": 0,
        "physical_capture_protocol_changed": False,
        "results": results,
        "all_t01_t04_pass_independently_frozen_amended_authority": all_pass,
        "scientific_capture_salvage_classification": (
            "EXISTING_SCIENTIFIC_CAPTURE_SALVAGE_VALID"
            if all_pass
            else "FRESH_SCIENTIFIC_COHORT_REQUIRED"
        ),
        "t01_t03_serialized_activations_reusable": activations_reusable,
        "downstream_reprocessing": (
            ["t04 post-capture packaging", "t04 activation extraction", "amended provenance/serialization/durability"]
            if all_pass and activations_reusable
            else ["target-dependent activation re-extraction"]
        ),
        "replacement_trajectories_required": False if all_pass else None,
        "pass": all_pass,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if all_pass else 3


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RegimeAError, FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"REGIME_A_AMENDED_SCIENTIFIC_REPLAY_REFUSAL: {exc}", file=sys.stderr)
        raise SystemExit(2)
