#!/usr/bin/env python3
"""Fresh NON-SCIENTIFIC directional visibility calibration.

Measures, independently for each direction and only from temporally aligned
non-scientific captures:

  * the geometric full-visible / partial / full-hidden boundaries,
  * the magenta transition,
  * the dual-agreement disagreement runs on entry and exit,
  * the resulting direction guards under the controlling rule
      guard = longest consecutive partial/disagreement run + 1 captured frame,
      minimum 1,
  * the stable-hidden world-x interval.

Symmetry between directions is reported, never imposed.
"""

from __future__ import annotations

import argparse
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


def longest_run(labels: list[str], start: int, stop: int, members: set[str]) -> int:
    best = current = 0
    for index in range(start, stop):
        if labels[index] in members:
            current += 1
            best = max(best, current)
        else:
            current = 0
    return best


def calibrate(partial: Path, direction: str) -> dict[str, object]:
    config = json.loads(DETECTOR_CONFIG.read_text())["configuration"]["detector_settings"]
    thresholds = tuple(HsvRange(*values) for values in config["hsv_ranges"])
    raw = partial / "raw"
    state = read_jsonl(raw / "server_state.jsonl")
    ticks = read_jsonl(raw / "client_tick.jsonl")
    alignment = validate_capture_temporal_alignment(state, ticks)

    labels: list[str] = []
    areas: list[int] = []
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
                "visible" if row["geometric_visible"] else "occluded", result.status
            )
        )
        areas.append(int(result.area_pixels))

    x = [float(row["sheep_x"]) for row in state]
    transitional = {"VISIBILITY_DISAGREEMENT", "INVALID_VISIBILITY"}

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

    entry_start = onset
    while entry_start > 0 and labels[entry_start - 1] in transitional:
        entry_start -= 1
    exit_stop = last_hidden
    while exit_stop + 1 < len(labels) and labels[exit_stop + 1] in transitional:
        exit_stop += 1

    entry_run = onset - entry_start
    exit_run = exit_stop - last_hidden
    geom_hidden = [index for index, row in enumerate(state) if not row["geometric_visible"]]

    return {
        "direction": direction,
        "trajectory_partial": partial.name,
        "temporal_alignment": alignment,
        "frame_count": len(state),
        "geometric_first_hidden_frame": geom_hidden[0],
        "geometric_last_hidden_frame": geom_hidden[-1],
        "geometric_hidden_entry_world_x": x[geom_hidden[0]],
        "geometric_hidden_exit_world_x": x[geom_hidden[-1]],
        "magenta_first_zero_frame": next(i for i, a in enumerate(areas) if a == 0 and i >= geom_hidden[0]),
        "stable_hidden_onset_frame": onset,
        "stable_hidden_last_frame": last_hidden,
        "stable_hidden_length_frames": last_hidden - onset + 1,
        "stable_hidden_onset_world_x": x[onset],
        "stable_hidden_exit_world_x": x[last_hidden],
        "entry_transition_start_frame": entry_start,
        "entry_transition_run_frames": entry_run,
        "exit_transition_stop_frame": exit_stop,
        "exit_transition_run_frames": exit_run,
        "longest_transitional_run_before_onset": longest_run(labels, 0, onset, transitional),
        "longest_transitional_run_after_last_hidden": longest_run(
            labels, last_hidden + 1, len(labels), transitional
        ),
        "derived_g_entry": max(1, entry_run + 1),
        "derived_g_exit": max(1, exit_run + 1),
        "guard_rule": "longest consecutive partial/disagreement run + 1 captured frame, minimum 1",
        "label_histogram": {name: labels.count(name) for name in sorted(set(labels))},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ltr-partial", type=Path, required=True)
    parser.add_argument("--rtl-partial", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    ltr = calibrate(args.ltr_partial, "LEFT_TO_RIGHT")
    rtl = calibrate(args.rtl_partial, "RIGHT_TO_LEFT")
    report = {
        "schema_version": "regime-a-fresh-directional-visibility-calibration-v1.0",
        "NON_SCIENTIFIC_CALIBRATION": True,
        "ELIGIBLE_FOR_REGIME_A_RESULTS": False,
        "guard_rule": "longest consecutive partial/disagreement run + 1 captured frame, minimum 1",
        "time_reversal_assumed": False,
        "LEFT_TO_RIGHT": ltr,
        "RIGHT_TO_LEFT": rtl,
        "observed_symmetry": {
            "entry_runs_equal": ltr["entry_transition_run_frames"] == rtl["entry_transition_run_frames"],
            "ltr_entry_vs_rtl_exit": [ltr["entry_transition_run_frames"], rtl["exit_transition_run_frames"]],
            "ltr_exit_vs_rtl_entry": [ltr["exit_transition_run_frames"], rtl["entry_transition_run_frames"]],
            "note": "reported only; never imposed on the derived guards",
        },
    }
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RegimeAError, FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"REGIME_A_CALIBRATION_REFUSAL: {exc}", file=sys.stderr)
        raise SystemExit(2)
