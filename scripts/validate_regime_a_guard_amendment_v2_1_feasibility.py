#!/usr/bin/env python3
"""Detailed outcome-free context/bin feasibility gate for amendment 1."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mineocclude.regime_a import BIN_BOUNDS, RegimeAError, sha256_file  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--authority", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = [json.loads(line) for line in args.manifest.read_text().splitlines() if line.strip()]
    if len(rows) != 25:
        raise RegimeAError("amended feasibility manifest count is not 25")
    support = []
    for fold in range(5):
        for direction in ("LEFT_TO_RIGHT", "RIGHT_TO_LEFT"):
            training = [
                row for row in rows if row["outer_fold"] != fold and row["direction"] == direction
            ]
            heldout = [
                row for row in rows if row["outer_fold"] == fold and row["direction"] == direction
            ]
            if not training or not heldout:
                raise RegimeAError("amended fold/direction support is empty")
            for name, (start, stop) in BIN_BOUNDS.items():
                train_values = [
                    float(value)
                    for row in training
                    for value in row["expected_tau_1_to_19_world_x"][start - 1 : stop]
                ]
                heldout_values = [
                    float(value)
                    for row in heldout
                    for value in row["expected_tau_1_to_19_world_x"][start - 1 : stop]
                ]
                overlap = min(max(train_values), max(heldout_values)) - max(
                    min(train_values), min(heldout_values)
                )
                support.append(
                    {
                        "outer_fold": fold,
                        "direction": direction,
                        "duration_bin": name,
                        "train_trajectory_count": len(training),
                        "heldout_trajectory_count": len(heldout),
                        "clean_frames_per_trajectory": stop - start + 1,
                        "train_range_world_x": [min(train_values), max(train_values)],
                        "heldout_range_world_x": [min(heldout_values), max(heldout_values)],
                        "overlap_width_blocks": overlap,
                        "pass": overlap > 0 and stop - start + 1 >= 3,
                    }
                )
    profile_hashes = [
        hashlib.sha256(
            np.asarray(row["expected_tau_1_to_19_world_x"], dtype="<f8").tobytes()
        ).hexdigest()
        for row in rows
    ]
    per_direction_tss = {
        direction: all(
            float(np.var(np.asarray(row["expected_tau_1_to_19_world_x"][:15], dtype=np.float64)))
            > 0
            for row in rows
            if row["direction"] == direction
        )
        for direction in ("LEFT_TO_RIGHT", "RIGHT_TO_LEFT")
    }
    document = {
        "schema_version": "regime-a-v2-amendment-1-context-bin-revalidation-v1.1",
        "status": "PASS",
        "authority_sha256": sha256_file(args.authority),
        "manifest_sha256": sha256_file(args.manifest),
        "effective_preceding_frames_E": 15,
        "context_duration_simulated_seconds_C": 0.75,
        "duration_bins": {name: list(bounds) for name, bounds in BIN_BOUNDS.items()},
        "fold_direction_bin_support": support,
        "all_fold_direction_bin_support_pass": all(row["pass"] for row in support),
        "left_to_right_support": all(
            row["pass"] for row in support if row["direction"] == "LEFT_TO_RIGHT"
        ),
        "right_to_left_support": all(
            row["pass"] for row in support if row["direction"] == "RIGHT_TO_LEFT"
        ),
        "all_trajectories_have_19_clean_target_frames": all(
            len(row["expected_tau_1_to_19_world_x"]) == 19 for row in rows
        ),
        "all_trajectories_have_at_least_15_preceding_frames": all(
            int(row["expected_stable_hidden_onset_frame"]) >= 15 for row in rows
        ),
        "all_primary_target_tss_positive_by_direction": per_direction_tss,
        "exact_duplicate_profile_count": len(profile_hashes) - len(set(profile_hashes)),
        "scientific_outcomes_computed": 0,
        "pass": True,
    }
    if not (
        document["all_fold_direction_bin_support_pass"]
        and document["all_trajectories_have_19_clean_target_frames"]
        and document["all_trajectories_have_at_least_15_preceding_frames"]
        and all(per_direction_tss.values())
        and document["exact_duplicate_profile_count"] == 0
    ):
        raise RegimeAError("amended context/bin feasibility gate failed")
    args.output.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")
    print(json.dumps(document, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RegimeAError, FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"REGIME_A_AMENDMENT_FEASIBILITY_REFUSAL: {exc}", file=sys.stderr)
        raise SystemExit(2)
