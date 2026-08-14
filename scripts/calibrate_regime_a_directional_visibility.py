#!/usr/bin/env python3
"""Derive directional Regime-A visibility authority from qualified crossings."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from mineocclude.regime_a import (  # noqa: E402
    RegimeAError,
    classify_visibility,
    validate_capture_temporal_alignment,
)
from mineocclude.vision.magenta import HsvRange, detect_magenta  # noqa: E402
from scripts.run_regime_a import detector_rgb_rows, read_jsonl  # noqa: E402

DETECTOR_CONFIG = (
    ROOT
    / "docs/status/person_e_phase3_step3_1_candidate_freeze_v0_1/detector_candidate_config.json"
)
TRANSITIONAL = {"VISIBILITY_DISAGREEMENT", "INVALID_VISIBILITY"}


def longest_run(labels: list[str], start: int, stop: int) -> int:
    best = current = 0
    for label in labels[start:stop]:
        if label in TRANSITIONAL:
            current += 1
            best = max(best, current)
        else:
            current = 0
    return best


def _first_after(indices: list[int], after: int) -> int:
    try:
        return next(index for index in indices if index > after)
    except StopIteration as exc:
        raise RegimeAError("capture never returns to full geometric visibility") from exc


def calibrate(partial: Path, direction: str, evidence_dir: Path) -> dict[str, object]:
    config = json.loads(DETECTOR_CONFIG.read_text())["configuration"]["detector_settings"]
    thresholds = tuple(HsvRange(*values) for values in config["hsv_ranges"])
    raw = partial / "raw"
    state = read_jsonl(raw / "server_state.jsonl")
    ticks = read_jsonl(raw / "client_tick.jsonl")
    actions = read_jsonl(raw / "actions.jsonl")
    if not (len(state) == len(ticks) == len(actions) == 260):
        raise RegimeAError(f"{partial.name}: capture cardinality is not 260")
    alignment = validate_capture_temporal_alignment(state, ticks)

    labels: list[str] = []
    areas: list[int] = []
    magenta_statuses: list[str] = []
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
        geometric = "visible" if row["geometric_visible"] else "occluded"
        labels.append(classify_visibility(geometric, result.status))
        magenta_statuses.append(result.status)
        areas.append(0 if result.area_pixels is None else int(result.area_pixels))

    x = [float(row["sheep_x"]) for row in state]
    onset = next(
        (
            index
            for index in range(len(labels) - 18)
            if labels[index : index + 19] == ["OCCLUDED_AGREEMENT"] * 19
        ),
        None,
    )
    if onset is None:
        raise RegimeAError(f"{partial.name}: no stable 19-frame OCCLUDED_AGREEMENT run")
    last_hidden = onset
    while last_hidden + 1 < len(labels) and labels[last_hidden + 1] == "OCCLUDED_AGREEMENT":
        last_hidden += 1

    geometric_hidden = [index for index, row in enumerate(state) if not row["geometric_visible"]]
    geometric_visible = [index for index, row in enumerate(state) if row["geometric_visible"]]
    if not geometric_hidden:
        raise RegimeAError(f"{partial.name}: no geometric occlusion")
    first_geometric_hidden = geometric_hidden[0]
    last_geometric_hidden = geometric_hidden[-1]
    first_geometric_visible_after = _first_after(geometric_visible, last_geometric_hidden)

    entry_start = onset
    while entry_start > 0 and labels[entry_start - 1] in TRANSITIONAL:
        entry_start -= 1
    exit_stop = last_hidden
    while exit_stop + 1 < len(labels) and labels[exit_stop + 1] in TRANSITIONAL:
        exit_stop += 1
    entry_max = longest_run(labels, first_geometric_hidden, onset)
    exit_max = longest_run(labels, last_hidden + 1, first_geometric_visible_after + 1)

    evidence_dir.mkdir(parents=True, exist_ok=True)
    evidence_path = evidence_dir / f"{partial.name.removeprefix('.')}.visibility_evidence.jsonl"
    with evidence_path.open("w", encoding="utf-8") as stream:
        for index, row in enumerate(state):
            tick = ticks[index]
            action = actions[index]
            evidence = {
                "trajectory_spec_id": row["trajectory_spec_id"],
                "spec_hash": row["spec_hash"],
                "seed": row["seed"],
                "direction": direction,
                "model_frame_idx": index,
                "server_tick": row["server_tick"],
                "render_frame_idx": tick["render_frame_idx"],
                "action_idx": action["action_idx"],
                "capture_ack_episode_id": tick["episode_id"],
                "capture_ack_tick_identity": tick["server_tick"],
                "tick_queue_depth_at_capture": tick["tick_queue_depth_at_capture"],
                "server_epoch_nanos": row["server_epoch_nanos"],
                "client_capture_nanos": tick["client_capture_nanos"],
                "world_x": x[index],
                "geometric_status": "visible" if row["geometric_visible"] else "occluded",
                "magenta_status": magenta_statuses[index],
                "magenta_area_pixels": areas[index],
                "visibility_class": labels[index],
                "disagreement": labels[index] == "VISIBILITY_DISAGREEMENT",
                "partial_transition": labels[index] in TRANSITIONAL,
            }
            stream.write(json.dumps(evidence, sort_keys=True, allow_nan=False) + "\n")

    return {
        "direction": direction,
        "trajectory_partial": partial.name,
        "trajectory_spec_id": state[0]["trajectory_spec_id"],
        "spec_hash": state[0]["spec_hash"],
        "seed": state[0]["seed"],
        "temporal_alignment": alignment,
        "frame_count": len(state),
        "capture_ack_identity_exact": all(
            row["server_tick"] == index
            and ticks[index]["server_tick"] == index
            and ticks[index]["render_frame_idx"] == index
            and actions[index]["action_idx"] == index
            and ticks[index]["episode_id"] == row["episode_id"]
            for index, row in enumerate(state)
        ),
        "capture_ack_count": len(ticks),
        "capture_ack_queue_depth_max": max(int(row["tick_queue_depth_at_capture"]) for row in ticks),
        "geometric_first_hidden_frame": first_geometric_hidden,
        "geometric_first_hidden_world_x": x[first_geometric_hidden],
        "geometric_last_visible_before_entry_frame": first_geometric_hidden - 1,
        "geometric_last_visible_before_entry_world_x": x[first_geometric_hidden - 1],
        "geometric_last_hidden_frame": last_geometric_hidden,
        "geometric_last_hidden_world_x": x[last_geometric_hidden],
        "geometric_first_visible_after_exit_frame": first_geometric_visible_after,
        "geometric_first_visible_after_exit_world_x": x[first_geometric_visible_after],
        "stable_hidden_onset_frame": onset,
        "stable_hidden_onset_world_x": x[onset],
        "stable_hidden_last_frame": last_hidden,
        "stable_hidden_last_world_x": x[last_hidden],
        "stable_hidden_length_frames": last_hidden - onset + 1,
        "entry_transition_start_frame": entry_start,
        "entry_transition_run_immediately_before_stable_frames": onset - entry_start,
        "entry_transition_max_consecutive_frames": entry_max,
        "exit_transition_stop_frame": exit_stop,
        "exit_transition_run_immediately_after_stable_frames": exit_stop - last_hidden,
        "exit_transition_max_consecutive_frames": exit_max,
        "derived_g_entry": max(1, entry_max + 1),
        "derived_g_exit": max(1, exit_max + 1),
        "guard_rule": "maximum consecutive partial/disagreement run + 1 captured frame, minimum 1",
        "label_histogram": {name: labels.count(name) for name in sorted(set(labels))},
        "evidence_jsonl": str(evidence_path),
    }


def lambda_free_calibrate(arguments: tuple[Path, str, Path]) -> dict[str, object]:
    """Pickle-safe process-pool adapter for independent crossings."""

    return calibrate(*arguments)


def aggregate(direction: str, crossings: list[dict[str, object]]) -> dict[str, object]:
    entry_max = max(int(row["entry_transition_max_consecutive_frames"]) for row in crossings)
    exit_max = max(int(row["exit_transition_max_consecutive_frames"]) for row in crossings)
    onsets = [float(row["stable_hidden_onset_world_x"]) for row in crossings]
    exits = [float(row["stable_hidden_last_world_x"]) for row in crossings]
    if direction == "LEFT_TO_RIGHT":
        stable_entry = max(onsets)
        stable_exit = min(exits)
    else:
        stable_entry = min(onsets)
        stable_exit = max(exits)
    return {
        "direction": direction,
        "crossing_count": len(crossings),
        "crossings": crossings,
        "geometric_first_hidden_world_x_observed": [
            row["geometric_first_hidden_world_x"] for row in crossings
        ],
        "geometric_first_visible_after_exit_world_x_observed": [
            row["geometric_first_visible_after_exit_world_x"] for row in crossings
        ],
        "stable_hidden_entry_world_x_conservative": stable_entry,
        "stable_hidden_exit_world_x_conservative": stable_exit,
        "entry_transition_max_consecutive_frames": entry_max,
        "exit_transition_max_consecutive_frames": exit_max,
        "derived_g_entry": max(1, entry_max + 1),
        "derived_g_exit": max(1, exit_max + 1),
        "all_temporally_aligned": all(
            int(row["temporal_alignment"]["frame_count"]) == 260
            and int(row["temporal_alignment"]["stale_frame_count"]) == 0
            for row in crossings
        ),
        "all_capture_ack_identities_exact": all(
            bool(row["capture_ack_identity_exact"]) for row in crossings
        ),
        "dual_visibility_qualified": all(
            int(row["stable_hidden_length_frames"]) >= 19 for row in crossings
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ltr-partial", type=Path, action="append", required=True)
    parser.add_argument("--rtl-partial", type=Path, action="append", required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if len(args.ltr_partial) < 2 or len(args.rtl_partial) < 2:
        raise RegimeAError("prospective authority requires at least two crossings per direction")
    work = [
        *((path, "LEFT_TO_RIGHT", args.evidence_dir) for path in args.ltr_partial),
        *((path, "RIGHT_TO_LEFT", args.evidence_dir) for path in args.rtl_partial),
    ]
    with concurrent.futures.ProcessPoolExecutor(max_workers=min(4, len(work))) as pool:
        measured = list(pool.map(lambda_free_calibrate, work))
    ltr = aggregate("LEFT_TO_RIGHT", measured[: len(args.ltr_partial)])
    rtl = aggregate("RIGHT_TO_LEFT", measured[len(args.ltr_partial) :])
    report = {
        "schema_version": "regime-a-fresh-directional-visibility-calibration-v2.0",
        "NON_SCIENTIFIC_CALIBRATION": True,
        "ELIGIBLE_FOR_REGIME_A_RESULTS": False,
        "guard_rule": "maximum consecutive partial/disagreement run + 1 captured frame, minimum 1",
        "time_reversal_assumed": False,
        "LEFT_TO_RIGHT": ltr,
        "RIGHT_TO_LEFT": rtl,
        "observed_symmetry": {
            "entry_runs_equal": ltr["entry_transition_max_consecutive_frames"]
            == rtl["entry_transition_max_consecutive_frames"],
            "exit_runs_equal": ltr["exit_transition_max_consecutive_frames"]
            == rtl["exit_transition_max_consecutive_frames"],
            "ltr_entry_vs_rtl_exit": [
                ltr["entry_transition_max_consecutive_frames"],
                rtl["exit_transition_max_consecutive_frames"],
            ],
            "ltr_exit_vs_rtl_entry": [
                ltr["exit_transition_max_consecutive_frames"],
                rtl["entry_transition_max_consecutive_frames"],
            ],
            "imposed": False,
        },
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RegimeAError, FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"REGIME_A_CALIBRATION_REFUSAL: {exc}", file=sys.stderr)
        raise SystemExit(2)
