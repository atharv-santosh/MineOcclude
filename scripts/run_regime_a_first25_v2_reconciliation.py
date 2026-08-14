#!/usr/bin/env python3
"""Capture and independently reconcile two non-scientific v2 rehearsals."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from mineocclude.regime_a import (  # noqa: E402
    AtomicTrajectoryStore,
    RegimeAError,
    canonical_sha256,
    classify_visibility,
    validate_capture_temporal_alignment,
)
from mineocclude.vision.magenta import HsvRange, detect_magenta  # noqa: E402
from scripts.run_regime_a import (  # noqa: E402
    ProductionCaptureWorker,
    detector_rgb_rows,
    read_jsonl,
)

DETECTOR_CONFIG = (
    ROOT
    / "docs/status/person_e_phase3_step3_1_candidate_freeze_v0_1/detector_candidate_config.json"
)
SCIENTIFIC = (
    ROOT
    / "docs/status/integration/regime_a_occlusion_extraction_v0_1/v2/trajectory_manifest.jsonl"
)


def validate_specs(path: Path) -> list[dict[str, object]]:
    rows = read_jsonl(path)
    if len(rows) != 2 or {row.get("direction") for row in rows} != {
        "LEFT_TO_RIGHT",
        "RIGHT_TO_LEFT",
    }:
        raise RegimeAError("v2 rehearsal manifest must have one crossing per direction")
    scientific = read_jsonl(SCIENTIFIC)
    scientific_ids = {row["trajectory_spec_id"] for row in scientific}
    scientific_seeds = {row["seed"] for row in scientific}
    for row in rows:
        body = dict(row)
        claimed = body.pop("spec_hash", None)
        if canonical_sha256(body) != claimed:
            raise RegimeAError("v2 rehearsal spec hash mismatch")
        if (
            row.get("NON_SCIENTIFIC_INTEGRATION_REHEARSAL") is not True
            or row.get("ELIGIBLE_FOR_REGIME_A_RESULTS") is not False
            or row.get("trajectory_spec_id") in scientific_ids
            or row.get("seed") in scientific_seeds
        ):
            raise RegimeAError("v2 rehearsal is not isolated from science")
    return rows


def independent_targets(spec: dict[str, object], partial: Path) -> tuple[list[int], dict[str, object]]:
    raw = partial / "raw"
    state = read_jsonl(raw / "server_state.jsonl")
    ticks = read_jsonl(raw / "client_tick.jsonl")
    actions = read_jsonl(raw / "actions.jsonl")
    if not (len(state) == len(ticks) == len(actions) == 260):
        raise RegimeAError("independent reconciliation capture cardinality mismatch")
    alignment = validate_capture_temporal_alignment(state, ticks)
    config = json.loads(DETECTOR_CONFIG.read_text())["configuration"]["detector_settings"]
    thresholds = tuple(HsvRange(*values) for values in config["hsv_ranges"])
    labels = []
    for index, row in enumerate(state):
        result = detect_magenta(
            detector_rgb_rows(raw / f"frames/{index:06d}.png", expected_size=(640, 360)),
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
                "visible" if row["geometric_visible"] else "occluded",
                result.status,
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
        raise RegimeAError("independent reconciliation found no stable dual-hidden run")
    transition_start = onset
    while transition_start > 0 and labels[transition_start - 1] in {
        "VISIBILITY_DISAGREEMENT",
        "INVALID_VISIBILITY",
    }:
        transition_start -= 1
    transition_run = onset - transition_start
    if transition_run > int(spec["entry_guard_frames"]):
        raise RegimeAError("independent reconciliation exceeded directional guard")
    return list(range(onset, onset + 19)), {
        "temporal_alignment": alignment,
        "entry_transition_run_frames": transition_run,
        "entry_guard_frames": spec["entry_guard_frames"],
        "label_histogram": {label: labels.count(label) for label in sorted(set(labels))},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--exercise-controlled-recovery", action="store_true")
    args = parser.parse_args()
    specs = validate_specs(args.manifest)
    runtime_root = args.runtime_root.resolve()
    if runtime_root == ROOT.resolve() or ROOT.resolve() in runtime_root.parents:
        raise RegimeAError("v2 rehearsal runtime root must be outside repository")
    store = AtomicTrajectoryStore(runtime_root / "trajectories")
    recovery = None
    first = specs[0]
    first_id, first_hash = str(first["trajectory_spec_id"]), str(first["spec_hash"])
    if args.exercise_controlled_recovery and store.same_spec_partial(first_id, first_hash) is None:
        interrupted = store.begin(first_id, first_hash)
        recovery = {
            "controlled_interrupted_unit": first_id,
            "partial_created": True,
            "same_spec_preserved": True,
            "same_seed_preserved": True,
            "replacement_identity_generated": False,
            "partial_path": str(interrupted),
        }
        if not store.discard_same_spec_partial(first_id, first_hash):
            raise RegimeAError("controlled same-spec partial was not recoverable")

    worker = ProductionCaptureWorker(runtime_root)
    results = []
    try:
        for spec in specs:
            spec_id, spec_hash = str(spec["trajectory_spec_id"]), str(spec["spec_hash"])
            partial = store.same_spec_partial(spec_id, spec_hash)
            if partial is None:
                partial = store.begin(spec_id, spec_hash)
                worker.capture(spec, partial, validate_and_package=False)
            elif not (partial / "raw").is_dir():
                raise RegimeAError("v2 rehearsal partial lacks captured raw evidence")
            expected, independent = independent_targets(spec, partial)
            production = worker.target_reconciliation(spec, partial)
            observed = production["observed_target_model_frame_indices"]
            result = {
                "trajectory_spec_id": spec_id,
                "spec_hash": spec_hash,
                "seed": spec["seed"],
                "direction": spec["direction"],
                "NON_SCIENTIFIC_INTEGRATION_REHEARSAL": True,
                "ELIGIBLE_FOR_REGIME_A_RESULTS": False,
                "prospective_support_forecast_indices": production[
                    "expected_target_model_frame_indices"
                ],
                "independently_recomputed_authority_indices": expected,
                "observed_production_target_indices": observed,
                "unexplained_mismatch": expected != observed,
                "exact_reconciliation": expected == observed,
                **independent,
            }
            results.append(result)
    finally:
        worker.close()
    report = {
        "schema_version": "regime-a-first25-v2-target-reconciliation-v1.0",
        "NON_SCIENTIFIC_INTEGRATION_REHEARSAL": True,
        "ELIGIBLE_FOR_REGIME_A_RESULTS": False,
        "controlled_recovery": recovery,
        "results": results,
        "LTR_PASS": next(row for row in results if row["direction"] == "LEFT_TO_RIGHT")[
            "exact_reconciliation"
        ],
        "RTL_PASS": next(row for row in results if row["direction"] == "RIGHT_TO_LEFT")[
            "exact_reconciliation"
        ],
    }
    report["PASS"] = report["LTR_PASS"] and report["RTL_PASS"]
    runtime_root.mkdir(parents=True, exist_ok=True)
    (runtime_root / "target_reconciliation_qualification.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["PASS"] else 3


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RegimeAError, FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"REGIME_A_V2_RECONCILIATION_REFUSAL: {exc}", file=sys.stderr)
        raise SystemExit(2)
