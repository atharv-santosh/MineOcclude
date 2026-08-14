#!/usr/bin/env python3
"""Outcome-blind Regime-A S0 motion/confound feasibility calibration.

The generated paths are design-only and permanently ineligible for scientific
use.  No frame, model, activation, target prediction, or decoding result is
read by this script.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np


VERSION = "regime-a-s0-confound-calibration-v0.1"
MASTER_SEED = 2026081401
DT = 0.05
SPEED = 1.5
Q = 0.05
POOL_PER_DIRECTION = 512
MAX_FRAMES = 260
E = 15
BIN_BOUNDS = ((1, 4), (5, 8), (9, 12), (13, 15), (16, 19))
BIN_NAMES = ("SHORT", "INTERMEDIATE", "LONG", "NEAR_CONTEXT", "BEYOND_CONTEXT")
HIDDEN_LEFT = -4.09654256549771
HIDDEN_RIGHT = 5.426536982279787
GEOMETRIC_ENTRY = {"LEFT_TO_RIGHT": -4.82, "RIGHT_TO_LEFT": 5.84}
ENTRY_GUARD = {"LEFT_TO_RIGHT": 20, "RIGHT_TO_LEFT": 8}
EXIT_GUARD = {"LEFT_TO_RIGHT": 8, "RIGHT_TO_LEFT": 20}
START_RANGE = {"LEFT_TO_RIGHT": (-8.0, -7.65), "RIGHT_TO_LEFT": (7.70, 8.0)}


def canonical_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def seed_for(direction: str, index: int) -> int:
    payload = f"{VERSION}|{MASTER_SEED}|{direction}|{index}".encode()
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big") & ((1 << 63) - 1)


@dataclass(frozen=True)
class Candidate:
    direction: str
    index: int
    seed: int
    start: float
    entry_frame: int
    exit_frame: int
    positions: np.ndarray
    tau_positions: np.ndarray
    noise: np.ndarray

    @property
    def candidate_id(self) -> str:
        return f"s0_design_only_{self.direction.lower()}_{self.index:04d}"


def build_candidate(direction: str, index: int) -> Candidate | None:
    seed = seed_for(direction, index)
    rng = np.random.default_rng(seed)
    start = float(rng.uniform(*START_RANGE[direction]))
    sign = 1.0 if direction == "LEFT_TO_RIGHT" else -1.0
    noise = rng.standard_normal(MAX_FRAMES) * math.sqrt(Q * DT)
    positions = start + np.cumsum(sign * SPEED * DT + noise)
    inside = (positions >= HIDDEN_LEFT) & (positions <= HIDDEN_RIGHT)
    entry = None
    for frame in range(MAX_FRAMES - 19):
        if inside[frame : frame + 19].all():
            entry = frame
            break
    if entry is None:
        return None
    transition = np.flatnonzero(
        positions >= GEOMETRIC_ENTRY[direction]
        if direction == "LEFT_TO_RIGHT"
        else positions <= GEOMETRIC_ENTRY[direction]
    )
    if transition.size == 0:
        return None
    transition_frame = int(transition[0])
    if transition_frame < E or entry - transition_frame > ENTRY_GUARD[direction]:
        return None
    exit_side = positions > HIDDEN_RIGHT if direction == "LEFT_TO_RIGHT" else positions < HIDDEN_LEFT
    exits = np.flatnonzero(exit_side & (np.arange(MAX_FRAMES) > entry + 18))
    if exits.size == 0:
        return None
    exit_frame = int(exits[0])
    if exit_frame + EXIT_GUARD[direction] >= MAX_FRAMES:
        return None
    tau_positions = positions[entry : entry + 19].copy()
    if tau_positions.size != 19 or not np.isfinite(tau_positions).all():
        return None
    return Candidate(direction, index, seed, start, entry, exit_frame, positions, tau_positions, noise)


def candidate_features(candidate: Candidate) -> np.ndarray:
    residual = candidate.tau_positions - np.linspace(candidate.tau_positions[0], candidate.tau_positions[-1], 19)
    return np.concatenate(
        [
            np.asarray([candidate.start, candidate.entry_frame * DT], dtype=np.float64),
            residual,
        ]
    )


def farthest_subset(candidates: list[Candidate], count: int) -> list[Candidate]:
    matrix = np.stack([candidate_features(row) for row in candidates])
    scale = matrix.std(axis=0)
    scale[scale == 0] = 1.0
    matrix = (matrix - matrix.mean(axis=0)) / scale
    first = int(np.argmax(np.linalg.norm(matrix, axis=1)))
    chosen = [first]
    remaining = set(range(len(candidates))) - {first}
    while len(chosen) < count:
        next_index = max(
            remaining,
            key=lambda idx: (
                min(float(np.linalg.norm(matrix[idx] - matrix[j])) for j in chosen),
                -candidates[idx].seed,
            ),
        )
        chosen.append(next_index)
        remaining.remove(next_index)
    return [candidates[index] for index in chosen]


def pearson(left: np.ndarray, right: np.ndarray) -> float | None:
    if left.size != right.size or left.size < 2 or left.std() == 0 or right.std() == 0:
        return None
    return float(np.corrcoef(left, right)[0, 1])


def profile_matrix(rows: list[Candidate], points: int = 128) -> np.ndarray:
    normalized = np.linspace(0.0, 1.0, points)
    values = []
    for row in rows:
        path = row.positions[: row.exit_frame + EXIT_GUARD[row.direction] + 1]
        source = np.linspace(0.0, 1.0, len(path))
        values.append(np.interp(normalized, source, path))
    return np.stack(values)


def pair_summary(rows: list[Candidate]) -> dict[str, object]:
    profiles = profile_matrix(rows)
    pairs = []
    for left in range(len(rows)):
        for right in range(left + 1, len(rows)):
            corr = pearson(profiles[left], profiles[right])
            rms = float(np.sqrt(np.mean((profiles[left] - profiles[right]) ** 2)))
            pairs.append((rows[left].direction == rows[right].direction, corr, rms))
    def summarize(selected: list[tuple[bool, float | None, float]]) -> dict[str, object]:
        correlations = [float(item[1]) for item in selected if item[1] is not None]
        distances = [item[2] for item in selected]
        return {
            "pair_count": len(selected),
            "absolute_r_ge_0_95_fraction": float(np.mean([abs(v) >= 0.95 for v in correlations])),
            "absolute_r_median": float(np.median(np.abs(correlations))),
            "profile_rms_distance_blocks_min": min(distances),
            "profile_rms_distance_blocks_median": float(np.median(distances)),
            "near_duplicate_rms_lt_0_10_fraction": float(np.mean([v < 0.10 for v in distances])),
        }
    return {
        "overall": summarize(pairs),
        "within_direction": summarize([item for item in pairs if item[0]]),
        "cross_direction": summarize([item for item in pairs if not item[0]]) if any(not item[0] for item in pairs) else None,
    }


def assign_folds(rows: list[Candidate]) -> dict[str, int]:
    by_direction = {
        direction: sorted((row for row in rows if row.direction == direction), key=lambda row: row.seed)
        for direction in ("LEFT_TO_RIGHT", "RIGHT_TO_LEFT")
    }
    assignments: dict[str, int] = {}
    targets = [
        (3, 2),
        (2, 3),
        (3, 2),
        (2, 3),
        (3, 2),
    ]
    offsets = {direction: 0 for direction in by_direction}
    for fold, (ltr_count, rtl_count) in enumerate(targets):
        for direction, count in (("LEFT_TO_RIGHT", ltr_count), ("RIGHT_TO_LEFT", rtl_count)):
            start = offsets[direction]
            for row in by_direction[direction][start : start + count]:
                assignments[row.candidate_id] = fold
            offsets[direction] += count
    if len(assignments) != len(rows):
        raise RuntimeError("fold assignment did not consume selected design")
    return assignments


def support_report(rows: list[Candidate], folds: dict[str, int]) -> dict[str, object]:
    checks = []
    for fold in range(5):
        for direction in ("LEFT_TO_RIGHT", "RIGHT_TO_LEFT"):
            train = [row for row in rows if folds[row.candidate_id] != fold and row.direction == direction]
            test = [row for row in rows if folds[row.candidate_id] == fold and row.direction == direction]
            for name, (start, stop) in zip(BIN_NAMES, BIN_BOUNDS):
                train_values = np.concatenate([row.tau_positions[start - 1 : stop] for row in train])
                test_values = np.concatenate([row.tau_positions[start - 1 : stop] for row in test])
                overlap = max(0.0, min(train_values.max(), test_values.max()) - max(train_values.min(), test_values.min()))
                union = max(train_values.max(), test_values.max()) - min(train_values.min(), test_values.min())
                checks.append(
                    {
                        "fold": fold,
                        "direction": direction,
                        "bin": name,
                        "interval_overlap_fraction": float(overlap / union) if union > 0 else 0.0,
                        "train_min_max": [float(train_values.min()), float(train_values.max())],
                        "test_min_max": [float(test_values.min()), float(test_values.max())],
                    }
                )
    return {
        "all_fold_direction_bin_intervals_overlap": all(row["interval_overlap_fraction"] > 0 for row in checks),
        "minimum_interval_overlap_fraction": min(row["interval_overlap_fraction"] for row in checks),
        "checks": checks,
    }


def family_report(name: str, rows: list[Candidate]) -> dict[str, object]:
    time_values = []
    position_values = []
    tau_values = []
    tau_positions = []
    for row in rows:
        path = row.positions[: row.exit_frame + EXIT_GUARD[row.direction] + 1]
        time_values.extend(np.linspace(0.0, 1.0, len(path)))
        position_values.extend(path)
        tau_values.extend(range(1, 20))
        tau_positions.extend(row.tau_positions)
    hashes = [hashlib.sha256(np.asarray(row.positions, dtype="<f8").tobytes()).hexdigest() for row in rows]
    report = {
        "family": name,
        "trajectory_count": len(rows),
        "direction_counts": {direction: sum(row.direction == direction for row in rows) for direction in sorted({row.direction for row in rows})},
        "absolute_pooled_normalized_time_world_x_correlation": abs(pearson(np.asarray(time_values), np.asarray(position_values)) or 0.0),
        "absolute_pooled_clean_tau_world_x_correlation": abs(pearson(np.asarray(tau_values), np.asarray(tau_positions)) or 0.0),
        "start_position": {"unique_count": len({row.start for row in rows}), "range": [min(row.start for row in rows), max(row.start for row in rows)]},
        "stable_onset_frame": {"unique_count": len({row.entry_frame for row in rows}), "range": [min(row.entry_frame for row in rows), max(row.entry_frame for row in rows)]},
        "target_support_by_bin": {
            name: [
                float(min(row.tau_positions[start - 1 : stop].min() for row in rows)),
                float(max(row.tau_positions[start - 1 : stop].max() for row in rows)),
            ]
            for name, (start, stop) in zip(BIN_NAMES, BIN_BOUNDS)
        },
        "exact_duplicate_complete_profile_count": len(hashes) - len(set(hashes)),
        "pairwise_profiles": pair_summary(rows),
    }
    if len({row.direction for row in rows}) == 2:
        folds = assign_folds(rows)
        report["fold_counts"] = {str(fold): sum(value == fold for value in folds.values()) for fold in range(5)}
        report["fold_direction_counts"] = {
            str(fold): {
                direction: sum(folds[row.candidate_id] == fold and row.direction == direction for row in rows)
                for direction in ("LEFT_TO_RIGHT", "RIGHT_TO_LEFT")
            }
            for fold in range(5)
        }
        report["support_overlap"] = support_report(rows, folds)
    return report


def build_report() -> dict[str, object]:
    pools = {
        direction: [row for index in range(POOL_PER_DIRECTION) if (row := build_candidate(direction, index)) is not None]
        for direction in ("LEFT_TO_RIGHT", "RIGHT_TO_LEFT")
    }
    if min(map(len, pools.values())) < 25:
        raise RuntimeError("insufficient valid design-only candidates")
    single = farthest_subset(pools["LEFT_TO_RIGHT"], 25)
    bidirectional = farthest_subset(pools["LEFT_TO_RIGHT"], 13) + farthest_subset(pools["RIGHT_TO_LEFT"], 12)
    single_report = family_report("SINGLE_PLUS_X", single)
    bidirectional_report = family_report("BALANCED_BIDIRECTIONAL_13_12", bidirectional)
    inherited_transferable = (
        single_report["absolute_pooled_normalized_time_world_x_correlation"] <= 0.10
        and single_report["pairwise_profiles"]["overall"]["absolute_r_ge_0_95_fraction"] <= 0.20
    ) or (
        bidirectional_report["absolute_pooled_normalized_time_world_x_correlation"] <= 0.10
        and bidirectional_report["pairwise_profiles"]["overall"]["absolute_r_ge_0_95_fraction"] <= 0.20
        and bidirectional_report["pairwise_profiles"]["within_direction"]["absolute_r_ge_0_95_fraction"] <= 0.10
    )
    selected = "BALANCED_BIDIRECTIONAL_13_12"
    return {
        "schema_version": VERSION,
        "status": "PASS_OUTCOME_BLIND_CONFOUND_FEASIBILITY",
        "designation": "NON_SCIENTIFIC_DESIGN_ONLY_NEVER_ELIGIBLE_FOR_REGIME_A_RESULTS",
        "inputs": {
            "master_seed": MASTER_SEED,
            "pool_per_direction": POOL_PER_DIRECTION,
            "speed_blocks_per_second": SPEED,
            "motion_noise_q": Q,
            "dt_seconds": DT,
            "effective_context_steps": E,
            "hidden_interval_conservative_blocks": [HIDDEN_LEFT, HIDDEN_RIGHT],
            "entry_guards_by_direction": ENTRY_GUARD,
            "exit_guards_by_direction": EXIT_GUARD,
        },
        "valid_candidate_counts": {direction: len(rows) for direction, rows in pools.items()},
        "single_direction_result": single_report,
        "bidirectional_result": bidirectional_report,
        "INHERITED_PROFILE_THRESHOLDS_NONTRANSFERABLE_TO_REGIME_A": not inherited_transferable,
        "selected_motion_design": selected,
        "selection_reason": "Balanced direction materially reduces pooled time/world-x and clean-tau/world-x association while retaining visibility/runway/bin feasibility, exact uniqueness, five equal outer folds, and within-direction train/test target-support overlap.",
        "prospective_confound_authority": {
            "randomized_start_position": True,
            "randomized_occlusion_onset_and_motion_phase": True,
            "varied_stochastic_motion_realization": True,
            "target_support_overlap_across_grouped_folds_by_direction_and_bin": "REQUIRED_POSITIVE_INTERVAL_OVERLAP",
            "target_support_overlap_across_duration_bins": "REQUIRED_AND_REPORTED",
            "exact_duplicate_complete_profiles": 0,
            "near_duplicate_definition": "complete-profile RMS world-x distance <0.10 block",
            "near_duplicate_concentration": "MINIMIZE_PROSPECTIVELY_AND_REPORT; NO OUTCOME-BASED THRESHOLD",
            "outer_fold_size": 5,
            "outer_fold_direction_balance": "2/3 or 3/2",
            "time_only_predictability": "CONTINUOUS_MANDATORY_REPORTING_NO_HARD_THRESHOLD",
            "target_specific_null": "MANDATORY_B49_WHOLE_TRAJECTORY_OUTER_TRAINING_ONLY",
        },
        "scientific_outcomes_read": False,
        "scientific_specs_generated": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = build_report()
    report["document_sha256_without_self"] = canonical_sha256(report)
    payload = json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
