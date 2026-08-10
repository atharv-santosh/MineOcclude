#!/usr/bin/env python3
"""Design and freeze the P4B repaired no-wall trajectory campaign offline.

This program is deliberately target-only.  It replays authoritative target motion,
searches immutable schedule geometry, and writes prospective campaign metadata.  It
does not launch Minecraft, import MineWorld, extract activations, fit probes, compute
R2, or create train/test memberships.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
import sys
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from itertools import combinations
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mineocclude.data.noise_schedule import (  # noqa: E402
    generate_noise_schedule,
    schedule_hash,
)

PACKAGE = (
    ROOT / "docs/status/integration/exploratory_large_scale_no_wall_scaling_best_k_v0_1"
)
RUNTIME_ROOT = Path(
    "/mnt/sagemaker-nvme/mineocclude_large_scale_no_wall_scaling_best_k_v0_1"
)

BRANCH = "exploration/large-scale-no-wall-scaling-best-k-v0-1"
P4A_HEAD = "b0620eb9a22bc48979b30b9abf25c19aad523a8c"
ORIGINAL_CAMPAIGN_SHA256 = (
    "1605f4738840ea531e73fdcee19536d55652a1a05ddef704304adcb1bc41cdd6"
)
ORIGINAL_CAMPAIGN_LOCK_SHA256 = (
    "479471d468598d93d861767ffa83b3e0bd1c401dbd3310cfcb509ecf7ced22aa"
)
STUDY_SHA256 = "08d77261f70a3d7e554ce6f8fe4a565fa09591ae793a87efd60e4a742c016502"
STUDY_LOCK_SHA256 = "05b337e81ffea6c6d3bb3f92ca76b7774c980f9c462565f5c50a71ad9f629f41"
P4A_RECEIPT_SHA256 = "6e9b4edafb8df5da4a517bcf930dfdbb69998cd80a4cbc5708f5ef45e4b326f3"
P4A_ARTIFACT_SHA256 = {
    "p4a_profile_gate_diagnosis.json": (
        "dd59a211a8fa50bcbfb8aea7afac369bc452918531f8439f4fba8de01c2f306f"
    ),
    "p4a_signed_similarity_by_direction.png": (
        "b296d3afa871cb82aa5e2896f03210ea62c530dcbe43e989f66291a385738aa6"
    ),
}
ORIGINAL_P4_SHA256 = {
    "p4_profile_statistics.json": (
        "3d87201a22d6fea88d563aefd6403765345c264e59105e2c567d110cf2c8844b"
    ),
    "p4_receipt.json": (
        "91642203ff2b4d4318d953e1d97b44ccf82049c257fe4d2e6025fd31519a942e"
    ),
    "p4_retry_audit.json": (
        "cafa60150998754917190a6377bc42427bd54805f868e987c6df050b16c524f8"
    ),
    "pre_extraction_profile_audit.json": (
        "59f91327c97825d0dcc96f888ec64928e62f079cf4d8812f6ea48ee03a99a993"
    ),
    "profile_similarity_distribution.png": (
        "dfd7290ab1fae597cec96f313f78d64e4081de28406b15427ea6bcd34eab0db9"
    ),
    "time_position_association.png": (
        "be6c625e09346b7213f980c62d24eb2c97d52e3229527502ec2918099cf44745"
    ),
}

FROZEN_AT = "2026-08-10T07:45:00Z"
F = 60
DT_SECONDS = 0.05
PROCESS_Q = 0.2
PAIR_R_THRESHOLD = 0.95
FROZEN_MAX_HIGH_FRACTION = 0.20
DESIGN_SAFETY_TARGET = 0.10
MIN_TARGET_RANGE = 1.30
MIN_TARGET_VARIANCE = 0.10
MAX_CANDIDATES = 3000
CANDIDATE_GENERATOR_SEED = 0x5044424D
SPEED_VALUES = np.asarray([0.0, 1.0, 1.5, 2.0], dtype=np.float64)
SPEED_PROBABILITIES = np.asarray([0.34, 0.22, 0.25, 0.19], dtype=np.float64)
EXPECTED_SELECTED_CANDIDATE_IDS = (
    1196,
    241,
    2904,
    757,
    2782,
    133,
    834,
    1219,
    2178,
    325,
    62,
    1189,
    2210,
    747,
    256,
    2191,
    1162,
    157,
    296,
    2635,
)

LAYOUTS = ("L01", "L02", "L03", "L04", "L05", "L06")
REPORTING_FAMILIES = (
    "LONG_DWELL_RESTART",
    "MULTI_DWELL_PULSE",
    "DELAYED_BOUNDED_BURST",
    "ASYMMETRIC_RESTART",
    "TERMINAL_HOLD_RESTART",
)
MOTION_SOURCE_HASHES = {
    "fabric/mineocclude-mod/src/main/java/com/mineocclude/server/MotionSchedule.java": (
        "a51dfa021b23c2a17606c487f54891e03956723b28f2d5aa1ef19c2445015845"
    ),
    "fabric/mineocclude-mod/src/main/java/com/mineocclude/server/SheepController.java": (  # noqa: E501
        "fb803f1fea628a29ae6fda40fb1936d02ff0bd329d492f3ea16bdc6e4d02753a"
    ),
    "fabric/mineocclude-mod/src/main/java/com/mineocclude/server/EpisodeManager.java": (
        "984c3863c7b2cf1e5fdc606924fd39104ca76829cb7270a2d3133b0ced6fcf75"
    ),
}


class P4BError(RuntimeError):
    """Raised when the offline successor design cannot be frozen safely."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise P4BError(message)


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(8 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"JSON authority is not an object: {path}")
    return value


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def json_bytes(value: Mapping[str, Any]) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode(
        "utf-8"
    )


def write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    data = json_bytes(value)
    with temporary.open("wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def verify_protected_authority() -> dict[str, Any]:
    expected = {
        PACKAGE / "capture_campaign.json": ORIGINAL_CAMPAIGN_SHA256,
        PACKAGE / "capture_campaign.lock.json": ORIGINAL_CAMPAIGN_LOCK_SHA256,
        PACKAGE / "study_design.json": STUDY_SHA256,
        PACKAGE / "study_design.lock.json": STUDY_LOCK_SHA256,
        PACKAGE / "p4a_receipt.json": P4A_RECEIPT_SHA256,
        **{PACKAGE / name: digest for name, digest in ORIGINAL_P4_SHA256.items()},
        **{PACKAGE / name: digest for name, digest in P4A_ARTIFACT_SHA256.items()},
        **{ROOT / name: digest for name, digest in MOTION_SOURCE_HASHES.items()},
    }
    observed = {}
    for path, digest in expected.items():
        require(path.is_file(), f"missing protected authority: {path}")
        actual = sha256_file(path)
        require(actual == digest, f"protected authority changed: {path}")
        observed[str(path.relative_to(ROOT))] = actual
    original_lock = read_json(PACKAGE / "capture_campaign.lock.json")
    require(original_lock["source_sha256"] == ORIGINAL_CAMPAIGN_SHA256, "P1 lock drift")
    p4 = read_json(PACKAGE / "p4_receipt.json")
    p4a = read_json(PACKAGE / "p4a_receipt.json")
    require(p4["status"] == "STOP_AND_REPORT", "original P4 FAIL not preserved")
    require(p4a["genuine_profile_diversity_failure"] is True, "P4A drift")
    require(p4a["safe_for_p5"] is False, "P4A unexpectedly authorizes P5")
    return observed


def commands_for_spec(spec: Mapping[str, Any]) -> np.ndarray:
    commands = np.empty(F, dtype=np.float64)
    covered = np.zeros(F, dtype=np.int8)
    expected_start = 0
    for segment in spec["exact_speed_schedule"]:
        start = int(segment["start_model_frame_idx"])
        stop = int(segment["stop_model_frame_idx_exclusive"])
        speed = float(segment["signed_speed_blocks_per_second"])
        require(
            start == expected_start and start < stop <= F, "invalid segment coverage"
        )
        require(math.isfinite(speed), "non-finite segment velocity")
        commands[start:stop] = speed
        covered[start:stop] += 1
        expected_start = stop
    require(expected_start == F and np.all(covered == 1), "schedule is not dense")
    return commands


def simulate_profile(
    spec: Mapping[str, Any], *, track_clamps: bool = False
) -> np.ndarray | tuple[np.ndarray, int]:
    """Reproduce SheepController.step: command integration, draw, then clamp."""
    commands = commands_for_spec(spec)
    noise = generate_noise_schedule(
        seed=int(spec["capture_seed"]),
        n_draws=F,
        q=float(spec["process_noise"]["q_blocks_squared_per_second"]),
        dt_seconds=float(spec["process_noise"]["dt_seconds"]),
    )
    require(
        schedule_hash(noise) == spec["process_noise"]["schedule_sha256"],
        f"noise schedule hash mismatch: {spec['trajectory_spec_id']}",
    )
    lower = float(spec["target_range"]["scalar_axis_min_blocks"])
    upper = float(spec["target_range"]["scalar_axis_max_blocks"])
    position = float(spec["start_position_authority"]["axis_position_blocks"])
    profile = np.empty(F, dtype=np.float64)
    clamp_count = 0
    for tick, (command, row) in enumerate(zip(commands, noise.rows, strict=True)):
        proposed = position + command * DT_SECONDS + row.noise_draw
        position = min(upper, max(lower, proposed))
        clamp_count += int(position != proposed)
        profile[tick] = position
    return (profile, clamp_count) if track_clamps else profile


def verify_old_runtime_equivalence() -> dict[str, Any]:
    campaign = read_json(PACKAGE / "capture_campaign.json")
    ledger = read_jsonl(PACKAGE / "p2_capture_ledger.jsonl")
    accepted = {
        row["trajectory_spec_id"]: row
        for row in ledger
        if row["record_type"] == "ATTEMPT_CLASSIFIED"
        and row.get("classification") == "ACCEPTED"
    }
    require(len(accepted) == 120, "preserved accepted runtime cohort is unavailable")
    profiles = []
    maximum_error = 0.0
    rows_checked = 0
    for spec in campaign["trajectory_specs"]:
        spec_id = spec["trajectory_spec_id"]
        root = Path(accepted[spec_id]["local_output_root"])
        require(
            root.is_relative_to(RUNTIME_ROOT), f"unexpected old runtime root: {root}"
        )
        state = read_jsonl(root / "raw/server/server_state.jsonl")
        require(len(state) == F, f"old server state does not have F=60: {spec_id}")
        simulated = np.asarray(simulate_profile(spec), dtype=np.float64)
        observed = np.asarray([float(row["axis_pos"]) for row in state])
        error = float(np.max(np.abs(simulated - observed)))
        maximum_error = max(maximum_error, error)
        require(error <= 1e-12, f"simulator/runtime mismatch for {spec_id}: {error}")
        profiles.append(simulated)
        rows_checked += F
    high_count, pair_count = high_similarity_count(np.asarray(profiles))
    require(pair_count == 7140, "old replay pair count differs")
    require(high_count == 3644, "old replay did not reproduce P4 failure")
    return {
        "status": "EXACT",
        "trajectory_count": 120,
        "row_count": rows_checked,
        "maximum_absolute_error_blocks": maximum_error,
        "tolerance_blocks": 1e-12,
        "old_pair_count": pair_count,
        "old_high_abs_r_ge_0_95_count": high_count,
        "old_high_abs_r_ge_0_95_proportion": high_count / pair_count,
        "old_profile_failure_reproduced": True,
    }


def capture_seed(candidate_id: int, layout_index: int) -> int:
    payload = f"mineocclude-p4b-monotonic-v2|{candidate_id}|{layout_index}".encode()
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big") & ((1 << 63) - 1)


def candidate_commands(candidate_id: int) -> np.ndarray | None:
    rng = np.random.Generator(np.random.PCG64(CANDIDATE_GENERATOR_SEED + candidate_id))
    raw_segment_count = int(rng.integers(7, 15))
    cuts = sorted(
        int(value)
        for value in rng.choice(np.arange(3, 58), raw_segment_count - 1, replace=False)
    )
    starts = [0, *cuts]
    stops = [*cuts, F]
    values = rng.choice(
        SPEED_VALUES,
        raw_segment_count,
        p=SPEED_PROBABILITIES,
    )
    commands = np.empty(F, dtype=np.float64)
    for start, stop, speed in zip(starts, stops, values, strict=True):
        commands[start:stop] = speed
    change_count = int(1 + np.count_nonzero(commands[1:] != commands[:-1]))
    commanded_displacement = float(np.sum(commands) * DT_SECONDS)
    dwell_ticks = int(np.count_nonzero(commands == 0.0))
    if (
        change_count < 5
        or not 2.0 <= commanded_displacement <= 4.0
        or not 10 <= dwell_ticks <= 38
    ):
        return None
    return commands


def layout_context(original: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    result = {}
    for layout in LAYOUTS:
        representative = next(
            spec
            for spec in original["trajectory_specs"]
            if spec["layout_id"] == layout
            and spec["direction"] == "LEFT_TO_RIGHT"
            and spec["repeat_id"] == 1
        )
        result[layout] = {
            "lower": float(representative["target_range"]["scalar_axis_min_blocks"]),
            "upper": float(representative["target_range"]["scalar_axis_max_blocks"]),
            "start_magnitude": abs(
                float(
                    representative["start_position_authority"]["axis_position_blocks"]
                )
            ),
        }
    return result


def simulate_candidate_group(
    candidate_id: int,
    unsigned_commands: np.ndarray,
    contexts: Mapping[str, Mapping[str, float]],
) -> np.ndarray | None:
    group = []
    for layout_index, layout in enumerate(LAYOUTS):
        context = contexts[layout]
        sign = 1.0 if (candidate_id + layout_index) % 2 == 0 else -1.0
        position = -sign * context["start_magnitude"]
        generator = np.random.Generator(
            np.random.PCG64(capture_seed(candidate_id, layout_index))
        )
        draws = generator.standard_normal(F) * math.sqrt(PROCESS_Q * DT_SECONDS)
        profile = np.empty(F, dtype=np.float64)
        for tick, (speed, draw) in enumerate(
            zip(unsigned_commands, draws, strict=True)
        ):
            proposed = position + sign * speed * DT_SECONDS + draw
            if proposed < context["lower"] or proposed > context["upper"]:
                return None  # Prospectively exclude every planned clamp.
            position = proposed
            profile[tick] = position
        if (
            float(np.ptp(profile)) < MIN_TARGET_RANGE
            or float(np.var(profile)) < MIN_TARGET_VARIANCE
        ):
            return None
        group.append(profile)
    return np.asarray(group)


def high_similarity_count(profiles: np.ndarray) -> tuple[int, int]:
    correlations = np.abs(np.corrcoef(profiles))
    upper = correlations[np.triu_indices(len(profiles), 1)]
    return int(np.sum(upper >= PAIR_R_THRESHOLD)), int(upper.size)


def search_candidates(
    contexts: Mapping[str, Mapping[str, float]],
    candidate_limit: int = MAX_CANDIDATES,
) -> dict[str, Any]:
    library: dict[int, tuple[np.ndarray, np.ndarray]] = {}
    schedule_legal_count = 0
    for candidate_id in range(candidate_limit):
        commands = candidate_commands(candidate_id)
        if commands is None:
            continue
        schedule_legal_count += 1
        group = simulate_candidate_group(candidate_id, commands, contexts)
        if group is not None:
            library[candidate_id] = (commands, group)
    require(len(library) >= 20, "candidate library is too small")

    selected: list[int] = []
    realized = np.empty((0, F), dtype=np.float64)
    command_shapes = np.empty((0, F), dtype=np.float64)
    trace = []
    for selection_index in range(20):
        required_parity = selection_index % 2
        best: tuple[tuple[Any, ...], int, np.ndarray, np.ndarray] | None = None
        for candidate_id, (commands, group) in library.items():
            if candidate_id in selected or candidate_id % 2 != required_parity:
                continue
            trial_realized = np.vstack([realized, group])
            realized_high, _ = high_similarity_count(trial_realized)
            trial_commands = np.vstack([command_shapes, np.cumsum(commands)])
            if len(trial_commands) == 1:
                command_high = 0
                command_mean_abs = 0.0
            else:
                values = np.abs(np.corrcoef(trial_commands))[
                    np.triu_indices(len(trial_commands), 1)
                ]
                command_high = int(np.sum(values >= PAIR_R_THRESHOLD))
                command_mean_abs = float(np.mean(values))
            realized_values = np.abs(np.corrcoef(trial_realized))[
                np.triu_indices(len(trial_realized), 1)
            ]
            score = (
                command_high,
                realized_high,
                command_mean_abs,
                float(np.mean(realized_values)),
                candidate_id,
            )
            if best is None or score < best[0]:
                best = (score, candidate_id, commands, group)
        require(best is not None, f"no candidate for selection {selection_index}")
        score, candidate_id, commands, group = best
        selected.append(candidate_id)
        command_shapes = np.vstack([command_shapes, np.cumsum(commands)])
        realized = np.vstack([realized, group])
        trace.append(
            {
                "selection_index": selection_index,
                "candidate_id": candidate_id,
                "required_candidate_parity": required_parity,
                "command_shape_high_pair_count_at_selection": score[0],
                "realized_high_pair_count_at_selection": score[1],
            }
        )
    require(
        tuple(selected) == EXPECTED_SELECTED_CANDIDATE_IDS,
        f"bounded selection replay differs from frozen selected IDs: {selected}",
    )
    expanded_commands = np.repeat(command_shapes, len(LAYOUTS), axis=0)
    command_high, command_pairs = high_similarity_count(expanded_commands)
    realized_high, realized_pairs = high_similarity_count(realized)
    require(realized_pairs == command_pairs == 7140, "search pair count differs")
    require(
        command_high / command_pairs <= DESIGN_SAFETY_TARGET,
        "commanded shapes miss the design safety target",
    )
    require(
        realized_high / realized_pairs <= DESIGN_SAFETY_TARGET,
        "realized simulated shapes miss the design safety target",
    )
    return {
        "candidate_limit": candidate_limit,
        "schedule_legal_count": schedule_legal_count,
        "fully_eligible_count": len(library),
        "selected_candidate_ids": selected,
        "selection_trace": trace,
        "commands_by_id": {identity: library[identity][0] for identity in selected},
        "realized_profiles": realized,
        "command_high_count": command_high,
        "command_pair_count": command_pairs,
        "realized_high_count": realized_high,
        "realized_pair_count": realized_pairs,
    }


def compress_schedule(commands: np.ndarray, sign: float) -> list[dict[str, Any]]:
    segments = []
    start = 0
    for stop in range(1, F + 1):
        if stop == F or commands[stop] != commands[start]:
            segments.append(
                {
                    "start_model_frame_idx": start,
                    "stop_model_frame_idx_exclusive": stop,
                    "signed_speed_blocks_per_second": float(sign * commands[start]),
                }
            )
            start = stop
    return segments


def world_position(spec: Mapping[str, Any], axis_position: float) -> list[float]:
    axis = spec["start_position_authority"]["scalar_axis"]
    old_world = spec["start_position_authority"]["world_xyz_blocks"]
    if axis == "x":
        return [axis_position, float(old_world[1]), float(old_world[2])]
    return [float(old_world[0]), float(old_world[1]), axis_position]


def build_specs(
    original: Mapping[str, Any], search: Mapping[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    representatives = {
        (layout, direction): next(
            spec
            for spec in original["trajectory_specs"]
            if spec["layout_id"] == layout
            and spec["direction"] == direction
            and spec["repeat_id"] == 1
        )
        for layout in LAYOUTS
        for direction in ("LEFT_TO_RIGHT", "RIGHT_TO_LEFT")
    }
    specs = []
    by_shape_layout = {}
    commands_by_id = search["commands_by_id"]
    for shape_index, candidate_id in enumerate(search["selected_candidate_ids"]):
        shape_class = f"MONOTONIC_MULTI_DWELL_SHAPE_{shape_index + 1:02d}"
        family = REPORTING_FAMILIES[shape_index // 4]
        repeat_id = (shape_index % 4) // 2 + 1
        unsigned_commands = commands_by_id[candidate_id]
        for layout_index, layout in enumerate(LAYOUTS):
            sign = 1.0 if (candidate_id + layout_index) % 2 == 0 else -1.0
            direction = "LEFT_TO_RIGHT" if sign > 0 else "RIGHT_TO_LEFT"
            direction_slug = "ltr" if sign > 0 else "rtl"
            spec = copy.deepcopy(representatives[(layout, direction)])
            spec_id = (
                f"fresh_vp_v2_{layout.lower()}_{direction_slug}_"
                f"shape_{shape_index + 1:02d}"
            )
            spec["trajectory_spec_id"] = spec_id
            spec["spec_version"] = "large-scale-no-wall-trajectory-spec-v0.2"
            spec["direction_semantics"] = "NONZERO_COMMANDED_VELOCITY_SIGN"
            spec["profile_family"] = family
            spec["trajectory_shape_class"] = shape_class
            spec["shape_taxonomy_version"] = "monotonic-multi-dwell-v0.2"
            spec["candidate_library_id"] = candidate_id
            spec["repeat_id"] = repeat_id
            spec["capture_seed"] = capture_seed(candidate_id, layout_index)
            spec["exact_speed_schedule"] = compress_schedule(unsigned_commands, sign)
            spec["commanded_direction_reversal_count"] = 0
            spec["speed_category"] = "MULTI_STRATUM_PIECEWISE"
            changes = [
                row["start_model_frame_idx"] for row in spec["exact_speed_schedule"][1:]
            ]
            nonzero = np.flatnonzero(unsigned_commands)
            spec["movement_onset_model_frame_idx"] = int(nonzero[0])
            spec["speed_change_model_frame_idx"] = None
            spec["speed_change_model_frame_indices"] = changes
            zero_segments = [
                row
                for row in spec["exact_speed_schedule"]
                if row["signed_speed_blocks_per_second"] == 0.0
            ]
            spec["stationary_segments"] = [
                {
                    "start_model_frame_idx": row["start_model_frame_idx"],
                    "stop_model_frame_idx_exclusive": row[
                        "stop_model_frame_idx_exclusive"
                    ],
                    "duration_ticks": row["stop_model_frame_idx_exclusive"]
                    - row["start_model_frame_idx"],
                    "semantics": (
                        "zero commanded drift; frozen process-noise draw remains "
                        "authoritative"
                    ),
                }
                for row in zero_segments
            ]
            spec["pause"] = None
            spec["dwell_segment_count"] = len(zero_segments)
            noise = generate_noise_schedule(
                seed=spec["capture_seed"],
                n_draws=F,
                q=PROCESS_Q,
                dt_seconds=DT_SECONDS,
            )
            spec["process_noise"] = {
                "q_blocks_squared_per_second": PROCESS_Q,
                "dt_seconds": DT_SECONDS,
                "format_version": "person-c-noise-schedule-v0.1",
                "producer": "numpy.random.Generator/PCG64",
                "numpy_version": noise.numpy_version,
                "schedule_sha256": schedule_hash(noise),
                "draw_count": F,
            }
            simulated, clamp_count = simulate_profile(spec, track_clamps=True)
            require(clamp_count == 0, f"planned clamp in repaired spec {spec_id}")
            rounded_profile = [round(float(value), 12) for value in simulated]
            spec["end_position_authority"] = {
                "expected_axis_position_blocks": rounded_profile[-1],
                "expected_world_xyz_blocks": world_position(spec, rounded_profile[-1]),
                "expected_profile_sha256": canonical_sha256(rounded_profile),
                "derivation": (
                    "exact frozen signed speed schedule plus immutable PCG64 noise "
                    "schedule, lane-clamped each tick"
                ),
            }
            spec["spec_hash"] = canonical_sha256(
                {key: value for key, value in spec.items() if key != "spec_hash"}
            )
            specs.append(spec)
            by_shape_layout[(shape_index, layout)] = spec

    order = []
    for shape_index in range(20):
        rotated = (
            LAYOUTS[shape_index % len(LAYOUTS) :]
            + LAYOUTS[: shape_index % len(LAYOUTS)]
        )
        for layout in rotated:
            spec = by_shape_layout[(shape_index, layout)]
            campaign_index = len(order)
            stage = (
                "A"
                if campaign_index < 12
                else "B" if campaign_index < 48 else "C" if campaign_index < 84 else "D"
            )
            order.append(
                {
                    "campaign_index": campaign_index,
                    "round_index": shape_index,
                    "stage": stage,
                    "trajectory_spec_id": spec["trajectory_spec_id"],
                    "spec_hash": spec["spec_hash"],
                }
            )
    return sorted(specs, key=lambda row: row["trajectory_spec_id"]), order


def build_campaign(
    original: Mapping[str, Any],
    specs: list[dict[str, Any]],
    order: list[dict[str, Any]],
) -> dict[str, Any]:
    campaign = {
        key: copy.deepcopy(value)
        for key, value in original.items()
        if key not in {"trajectory_specs", "campaign_order"}
    }
    campaign.update(
        {
            "artifact_id": "large-scale-no-wall-capture-campaign-v0.2",
            "schema_version": "2.0",
            "frozen_at": FROZEN_AT,
            "implementation_phase": "P4B",
            "status": "FROZEN_PROSPECTIVE_REPAIRED",
            "campaign_shape": {
                "layouts": 6,
                "directions": 2,
                "reporting_profile_families": 5,
                "trajectory_shape_classes": 20,
                "shape_classes_per_layout": 20,
                "repeats_per_layout_direction_reporting_family": 2,
                "trajectory_spec_count": 120,
                "capture_replicates_are_not_command_identical_duplicates": True,
            },
            "campaign_order_algorithm": (
                "20 balanced shape rounds; rotate layout order by round; each shape "
                "appears once in every layout and has three specs per commanded "
                "direction; stages retain cumulative counts 12/48/84/120."
            ),
            "stage_a_semantics": (
                "First two balanced shape rounds: exactly two specs/layout, opposite "
                "commanded directions within layout, and two distinct shape classes."
            ),
            "redesign_provenance": {
                "original_campaign_sha256": ORIGINAL_CAMPAIGN_SHA256,
                "original_campaign_status": (
                    "FAILED_PRE_EXTRACTION_PROFILE_DIVERSITY_GATE"
                ),
                "original_p4_result_preserved": True,
                "p4a_diagnosis": "GENUINE_PROFILE_DIVERSITY_FAILURE",
                "p4a_head": P4A_HEAD,
                "repaired_campaign_status": ("PROSPECTIVE_PRE_EXTRACTION_REDESIGN"),
                "model_outcomes_available_at_redesign": False,
                "fresh_activations_extracted_at_redesign": 0,
                "fresh_r2_computed_at_redesign": False,
                "train_test_split_created_at_redesign": False,
                "old_capture_reuse_in_primary": False,
            },
            "trajectory_specs": specs,
            "campaign_order": order,
        }
    )
    return campaign


def pooled_time_correlation(records: Sequence[Mapping[str, Any]]) -> float:
    normalized_time = np.arange(F, dtype=np.float64) / (F - 1)
    times = np.tile(normalized_time, len(records))
    profiles = np.concatenate([np.asarray(row["profile"]) for row in records])
    return float(np.corrcoef(times, profiles)[0, 1])


def similarity_summary(
    records: Sequence[Mapping[str, Any]],
    predicate: Callable[[Mapping[str, Any], Mapping[str, Any]], bool],
) -> dict[str, Any]:
    values = np.asarray(
        [
            float(np.corrcoef(left["profile"], right["profile"])[0, 1])
            for left, right in combinations(records, 2)
            if predicate(left, right)
        ],
        dtype=np.float64,
    )
    absolute = np.abs(values)
    high = int(np.sum(absolute >= PAIR_R_THRESHOLD))
    return {
        "pair_count": int(values.size),
        "high_abs_r_ge_0_95_count": high,
        "high_abs_r_ge_0_95_proportion": float(high / values.size),
        "mean_r": float(np.mean(values)),
        "mean_abs_r": float(np.mean(absolute)),
        "median_abs_r": float(np.median(absolute)),
        "p95_abs_r": float(np.quantile(absolute, 0.95, method="linear")),
        "maximum_abs_r": float(np.max(absolute)),
    }


def build_audit(
    campaign: Mapping[str, Any],
    search: Mapping[str, Any],
    equivalence: Mapping[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    records = []
    for spec in campaign["trajectory_specs"]:
        profile, clamp_count = simulate_profile(spec, track_clamps=True)
        records.append(
            {
                "trajectory_spec_id": spec["trajectory_spec_id"],
                "spec_hash": spec["spec_hash"],
                "layout_id": spec["layout_id"],
                "direction": spec["direction"],
                "profile_family": spec["profile_family"],
                "trajectory_shape_class": spec["trajectory_shape_class"],
                "repeat_id": spec["repeat_id"],
                "profile": profile,
                "command": commands_for_spec(spec),
                "target_min": float(np.min(profile)),
                "target_max": float(np.max(profile)),
                "target_range": float(np.ptp(profile)),
                "target_variance": float(np.var(profile)),
                "clamp_count": clamp_count,
            }
        )
    all_summary = similarity_summary(records, lambda _left, _right: True)
    same_direction = similarity_summary(
        records, lambda left, right: left["direction"] == right["direction"]
    )
    opposite_direction = similarity_summary(
        records, lambda left, right: left["direction"] != right["direction"]
    )
    same_shape = similarity_summary(
        records,
        lambda left, right: left["trajectory_shape_class"]
        == right["trajectory_shape_class"],
    )
    different_shape = similarity_summary(
        records,
        lambda left, right: left["trajectory_shape_class"]
        != right["trajectory_shape_class"],
    )
    same_family = similarity_summary(
        records,
        lambda left, right: left["profile_family"] == right["profile_family"],
    )
    different_family = similarity_summary(
        records,
        lambda left, right: left["profile_family"] != right["profile_family"],
    )
    by_direction = {
        direction: pooled_time_correlation(
            [row for row in records if row["direction"] == direction]
        )
        for direction in ("LEFT_TO_RIGHT", "RIGHT_TO_LEFT")
    }
    by_shape = {
        shape: pooled_time_correlation(
            [row for row in records if row["trajectory_shape_class"] == shape]
        )
        for shape in sorted({row["trajectory_shape_class"] for row in records})
    }
    by_family = {
        family: pooled_time_correlation(
            [row for row in records if row["profile_family"] == family]
        )
        for family in sorted({row["profile_family"] for row in records})
    }
    per_layout = Counter(row["layout_id"] for row in records)
    per_layout_direction = Counter(
        (row["layout_id"], row["direction"]) for row in records
    )
    per_layout_shape = Counter(
        (row["layout_id"], row["trajectory_shape_class"]) for row in records
    )
    per_cell = Counter(
        (row["layout_id"], row["direction"], row["profile_family"]) for row in records
    )
    command_profiles = np.asarray(
        [np.cumsum(row["command"]) * DT_SECONDS for row in records]
    )
    command_high, command_pairs = high_similarity_count(command_profiles)
    original_camera = read_json(PACKAGE / "capture_campaign.json")
    original_by_layout = {
        layout: next(
            spec
            for spec in original_camera["trajectory_specs"]
            if spec["layout_id"] == layout
        )["camera_viewpoint_authority"]
        for layout in LAYOUTS
    }
    camera_unchanged = all(
        spec["camera_viewpoint_authority"] == original_by_layout[spec["layout_id"]]
        for spec in campaign["trajectory_specs"]
    )
    aggregate_not_sole = (
        same_direction["high_abs_r_ge_0_95_proportion"] <= DESIGN_SAFETY_TARGET
        and different_shape["high_abs_r_ge_0_95_proportion"] <= DESIGN_SAFETY_TARGET
        and command_high / command_pairs <= DESIGN_SAFETY_TARGET
    )
    gates = {
        "total_specs_120": len(records) == 120,
        "specs_per_layout_20": per_layout
        == Counter({layout: 20 for layout in LAYOUTS}),
        "unique_spec_ids_120": len({row["trajectory_spec_id"] for row in records})
        == 120,
        "unique_spec_hashes_120": len({row["spec_hash"] for row in records}) == 120,
        "f_60_feasible": all(len(row["profile"]) == F for row in records),
        "legal_position_bounds": all(row["clamp_count"] == 0 for row in records),
        "target_variance": all(
            row["target_variance"] >= MIN_TARGET_VARIANCE for row in records
        ),
        "target_range": all(row["target_range"] >= MIN_TARGET_RANGE for row in records),
        "camera_layout_authority_unchanged": camera_unchanged,
        "no_wall_unchanged": all(
            spec["no_wall"] is True and spec["scene"] == "NO_WALL"
            for spec in campaign["trajectory_specs"]
        ),
        "layout_balance": per_layout == Counter({layout: 20 for layout in LAYOUTS}),
        "direction_balance": per_layout_direction
        == Counter(
            {
                (layout, direction): 10
                for layout in LAYOUTS
                for direction in ("LEFT_TO_RIGHT", "RIGHT_TO_LEFT")
            }
        ),
        "shape_balance": all(value == 1 for value in per_layout_shape.values())
        and len(per_layout_shape) == 120,
        "reporting_cell_balance": all(value == 2 for value in per_cell.values())
        and len(per_cell) == 60,
        "overall_time_position": abs(pooled_time_correlation(records)) <= 0.10,
        "profile_similarity_frozen_gate": all_summary["high_abs_r_ge_0_95_proportion"]
        <= FROZEN_MAX_HIGH_FRACTION,
        "profile_similarity_design_safety_target": all_summary[
            "high_abs_r_ge_0_95_proportion"
        ]
        <= DESIGN_SAFETY_TARGET,
        "command_shape_design_safety_target": command_high / command_pairs
        <= DESIGN_SAFETY_TARGET,
        "aggregate_cancellation_not_sole_pass": aggregate_not_sole,
        "simulator_runtime_equivalence": equivalence["status"] == "EXACT",
    }
    require(all(gates.values()), f"repaired audit gate failed: {gates}")
    audit = {
        "schema_version": "large-scale-no-wall-p4b-offline-profile-audit-v0.2",
        "status": "PASS",
        "outcome_blind": True,
        "activation_or_probe_inputs_used": False,
        "train_test_assignments_created": False,
        "simulator_runtime_equivalence": equivalence,
        "counts": {
            "total_specs": len(records),
            "specs_per_layout": dict(sorted(per_layout.items())),
            "specs_per_layout_direction": {
                "|".join(key): value
                for key, value in sorted(per_layout_direction.items())
            },
            "shape_classes": len(per_layout_shape) // len(LAYOUTS),
            "unique_spec_ids": len({row["trajectory_spec_id"] for row in records}),
            "unique_spec_hashes": len({row["spec_hash"] for row in records}),
            "simulated_profile_pair_count": all_summary["pair_count"],
        },
        "profile_similarity": {
            "threshold_inclusive": PAIR_R_THRESHOLD,
            "frozen_maximum_fraction": FROZEN_MAX_HIGH_FRACTION,
            "design_safety_target": DESIGN_SAFETY_TARGET,
            "all_pairs": all_summary,
            "same_direction": same_direction,
            "opposite_direction": opposite_direction,
            "same_shape_class": same_shape,
            "different_shape_class": different_shape,
            "same_reporting_family": same_family,
            "different_reporting_family": different_family,
            "command_only_all_pairs_auxiliary": {
                "pair_count": command_pairs,
                "high_abs_r_ge_0_95_count": command_high,
                "high_abs_r_ge_0_95_proportion": command_high / command_pairs,
                "purpose": (
                    "Shows that frozen commanded temporal geometry, without process "
                    "noise, independently clears the 0.10 design target."
                ),
            },
        },
        "time_position_correlation": {
            "normalized_time_definition": "model_frame_idx / 59 for indices 0..59",
            "overall": pooled_time_correlation(records),
            "by_direction": by_direction,
            "by_shape_class": by_shape,
            "by_reporting_family": by_family,
            "aggregate_cancellation_not_sole_pass": aggregate_not_sole,
        },
        "target_distribution": {
            "minimum_required_range_blocks": MIN_TARGET_RANGE,
            "observed_minimum_range_blocks": min(
                row["target_range"] for row in records
            ),
            "minimum_required_variance_blocks_squared": MIN_TARGET_VARIANCE,
            "observed_minimum_variance_blocks_squared": min(
                row["target_variance"] for row in records
            ),
            "planned_clamp_count": sum(row["clamp_count"] for row in records),
        },
        "component_gates": gates,
        "safe_for_repaired_capture": True,
        "safe_for_p5": False,
    }
    return audit, records


def shape_descriptions(
    search: Mapping[str, Any], records: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    result = []
    for shape_index, candidate_id in enumerate(search["selected_candidate_ids"]):
        commands = search["commands_by_id"][candidate_id]
        segments = compress_schedule(commands, 1.0)
        shape = f"MONOTONIC_MULTI_DWELL_SHAPE_{shape_index + 1:02d}"
        shape_records = [
            row for row in records if row["trajectory_shape_class"] == shape
        ]
        result.append(
            {
                "shape_class": shape,
                "reporting_family": REPORTING_FAMILIES[shape_index // 4],
                "candidate_id": candidate_id,
                "unsigned_speed_schedule": segments,
                "segment_count": len(segments),
                "dwell_segment_count": sum(
                    row["signed_speed_blocks_per_second"] == 0.0 for row in segments
                ),
                "dwell_tick_count": int(np.count_nonzero(commands == 0.0)),
                "movement_onset_tick": int(np.flatnonzero(commands)[0]),
                "commanded_displacement_blocks": float(np.sum(commands) * DT_SECONDS),
                "realized_target_range_blocks": {
                    "minimum_across_layouts": min(
                        row["target_range"] for row in shape_records
                    ),
                    "maximum_across_layouts": max(
                        row["target_range"] for row in shape_records
                    ),
                },
            }
        )
    return result


def build_design(
    campaign_sha256: str,
    search: Mapping[str, Any],
    equivalence: Mapping[str, Any],
    audit: Mapping[str, Any],
    records: Sequence[Mapping[str, Any]],
    protected_hashes: Mapping[str, str],
) -> dict[str, Any]:
    return {
        "schema_version": "large-scale-no-wall-trajectory-profile-design-v0.2",
        "artifact_id": "large-scale-no-wall-trajectory-profile-design-v0.2",
        "status": "FROZEN_PROSPECTIVE_PRE_EXTRACTION_REDESIGN",
        "frozen_at": FROZEN_AT,
        "phase": "P4B_OFFLINE_TRAJECTORY_SHAPE_REDESIGN_AND_CAMPAIGN_FREEZE",
        "branch": BRANCH,
        "p4a_head": P4A_HEAD,
        "capture_campaign_v2_sha256": campaign_sha256,
        "protected_authority_sha256": dict(sorted(protected_hashes.items())),
        "provenance": {
            "original_campaign_status": (
                "FAILED_PRE_EXTRACTION_PROFILE_DIVERSITY_GATE"
            ),
            "original_p4_result_preserved": True,
            "p4a_diagnosis": "GENUINE_PROFILE_DIVERSITY_FAILURE",
            "repaired_campaign_status": "PROSPECTIVE_PRE_EXTRACTION_REDESIGN",
            "model_outcomes_available_at_redesign": False,
            "fresh_activations_extracted_at_redesign": 0,
            "fresh_r2_computed_at_redesign": False,
            "train_test_split_created_at_redesign": False,
            "old_capture_reuse_in_primary": False,
        },
        "motion_capability": {
            "multiple_velocity_segments": True,
            "multiple_pauses": True,
            "zero_velocity_dwells": True,
            "more_than_one_speed_change": True,
            "controlled_direction_reversals": True,
            "arbitrary_finite_signed_segment_velocities": True,
            "basis": (
                "MotionSchedule.load accepts any nonempty number of finite signed "
                "segments with complete gap-free tick coverage; velocityAt supplies "
                "each command and SheepController integrates command*0.05 + frozen "
                "noise before lane clamp."
            ),
            "runtime_change_required": False,
            "runtime_change_description": "NONE",
        },
        "simulator": {
            "semantics": (
                "For tick 0..59: x_next = clamp(x_previous + "
                "signed_speed_blocks_per_second * 0.05 + frozen_noise_draw)."
            ),
            **equivalence,
        },
        "old_library_diagnosis": {
            "failure_reproduced_offline": True,
            "high_pair_result": "3644/7140 = 0.5103641456582633",
            "structural_cause": [
                "mostly monotonic ramp-like cumulative profiles",
                "too few breakpoints and dwell intervals",
                "shared transition timing and affine/time-warp similarity",
                "insufficient temporal support diversity for Pearson geometry",
            ],
        },
        "monotonic_first_decision": {
            "attempted_first": True,
            "result": "SUFFICIENT_WITH_STRONG_MARGIN",
            "controlled_reversals_used": False,
            "direction_field_meaning_changed": False,
            "direction_definition": (
                "LEFT_TO_RIGHT or RIGHT_TO_LEFT is the common sign of every nonzero "
                "commanded velocity; process-noise jitter has its unchanged v0.1 "
                "meaning."
            ),
            "justification": (
                "Twenty multi-dwell monotonic command shapes clear both the frozen "
                "0.20 gate and 0.10 safety target; reversal would add needless task "
                "and grouping complexity."
            ),
        },
        "candidate_search": {
            "outcome_blind": True,
            "allowed_inputs": (
                "frozen target schedules, layout lanes, starts, PCG64 process-noise "
                "schedules, and simulated target-profile geometry"
            ),
            "forbidden_inputs_used": [],
            "generator": {
                "candidate_id_range": [0, MAX_CANDIDATES - 1],
                "candidate_generator_seed": CANDIDATE_GENERATOR_SEED,
                "raw_segment_count_range_half_open": [7, 15],
                "breakpoint_population_ticks": [3, 57],
                "allowed_unsigned_speeds_blocks_per_second": SPEED_VALUES.tolist(),
                "speed_probabilities": SPEED_PROBABILITIES.tolist(),
                "minimum_compressed_segments": 5,
                "commanded_displacement_range_blocks_inclusive": [2.0, 4.0],
                "dwell_tick_range_inclusive": [10, 38],
                "planned_clamps_allowed": 0,
                "minimum_realized_target_range_blocks": MIN_TARGET_RANGE,
                "minimum_realized_target_variance_blocks_squared": (
                    MIN_TARGET_VARIANCE
                ),
            },
            "candidate_limit": search["candidate_limit"],
            "schedule_legal_count": search["schedule_legal_count"],
            "fully_eligible_count": search["fully_eligible_count"],
            "selection_algorithm": (
                "Greedily add one six-layout shape group per round, alternating "
                "candidate parity for exact direction balance; lexicographically "
                "minimize command-only high-pair count, realized high-pair count, "
                "command mean abs-r, realized mean abs-r, then candidate ID."
            ),
            "selected_candidate_ids": search["selected_candidate_ids"],
            "selection_trace": search["selection_trace"],
        },
        "trajectory_taxonomy": {
            "primary_shape_taxonomy": "20 exact monotonic multi-dwell shape classes",
            "shape_class_count": 20,
            "each_shape_class_per_layout": 1,
            "each_shape_class_direction_counts": {
                "LEFT_TO_RIGHT": 3,
                "RIGHT_TO_LEFT": 3,
            },
            "reporting_families": list(REPORTING_FAMILIES),
            "reporting_family_role": (
                "Balanced four-shape strata retain the frozen future split's "
                "profile/repeat scoring fields; they are not the failed v0.1 five "
                "motion primitives."
            ),
            "shape_classes": shape_descriptions(search, records),
        },
        "profile_audit_summary": {
            "all_pairs": audit["profile_similarity"]["all_pairs"],
            "command_only_all_pairs_auxiliary": audit["profile_similarity"][
                "command_only_all_pairs_auxiliary"
            ],
            "overall_time_position_correlation": audit["time_position_correlation"][
                "overall"
            ],
            "all_component_gates_pass": all(audit["component_gates"].values()),
        },
        "scope_control": {
            "runtime_java_changed": False,
            "minecraft_started": False,
            "new_trajectories_captured": 0,
            "mineworld_run": False,
            "activations_extracted": 0,
            "r2_computed": False,
            "train_test_split_created": False,
            "p5_started": False,
        },
    }


def build_receipt(
    campaign_sha256: str,
    audit: Mapping[str, Any],
    equivalence: Mapping[str, Any],
) -> dict[str, Any]:
    all_pairs = audit["profile_similarity"]["all_pairs"]
    return {
        "schema_version": "large-scale-no-wall-p4b-receipt-v0.2",
        "status": "PASS_REPAIRED_CAMPAIGN_FROZEN",
        "branch": BRANCH,
        "p4a_head": P4A_HEAD,
        "original_campaign_preserved": True,
        "original_p4_fail_preserved": True,
        "p4a_genuine_failure_preserved": True,
        "model_outcomes_available": False,
        "fresh_activations_extracted": 0,
        "fresh_r2_computed": False,
        "train_test_split_created": False,
        "offline_simulator_created": True,
        "simulator_runtime_equivalence": equivalence["status"],
        "simulator_validation_trajectories": equivalence["trajectory_count"],
        "old_profile_failure_reproduced_offline": True,
        "runtime_change_required": False,
        "runtime_change_description": "NONE",
        "repaired_profile_taxonomy": "20_MONOTONIC_MULTI_DWELL_SHAPE_CLASSES",
        "repaired_trajectory_spec_count": 120,
        "repaired_specs_per_layout": 20,
        "old_capture_reuse_in_primary": False,
        "simulated_profile_pair_count": all_pairs["pair_count"],
        "simulated_high_abs_r_ge_0_95_count": all_pairs["high_abs_r_ge_0_95_count"],
        "simulated_high_abs_r_ge_0_95_proportion": all_pairs[
            "high_abs_r_ge_0_95_proportion"
        ],
        "frozen_profile_similarity_threshold": FROZEN_MAX_HIGH_FRACTION,
        "design_safety_target": DESIGN_SAFETY_TARGET,
        "profile_similarity_safety_margin": FROZEN_MAX_HIGH_FRACTION
        - all_pairs["high_abs_r_ge_0_95_proportion"],
        "legal_position_bounds": audit["component_gates"]["legal_position_bounds"],
        "target_variance_gate": audit["component_gates"]["target_variance"],
        "f_60_feasible": audit["component_gates"]["f_60_feasible"],
        "layout_balance": audit["component_gates"]["layout_balance"],
        "direction_balance": audit["component_gates"]["direction_balance"],
        "capture_campaign_v2_sha256": campaign_sha256,
        "repaired_campaign_created": True,
        "repaired_campaign_lock_created": True,
        "repaired_campaign_version": "0.2",
        "core_nick_experiment_unchanged": True,
        "new_minecraft_capture_started": False,
        "new_trajectories_captured": 0,
        "p5_started": False,
        "safe_for_repaired_capture": True,
        "safe_for_p5": False,
        "blocker": None,
    }


def generate_artifacts(output_package: Path = PACKAGE) -> dict[str, Any]:
    protected_hashes = verify_protected_authority()
    equivalence = verify_old_runtime_equivalence()
    original = read_json(PACKAGE / "capture_campaign.json")
    contexts = layout_context(original)
    search = search_candidates(contexts)
    specs, order = build_specs(original, search)
    campaign = build_campaign(original, specs, order)
    campaign_data = json_bytes(campaign)
    campaign_sha = hashlib.sha256(campaign_data).hexdigest()
    audit, records = build_audit(campaign, search, equivalence)
    design = build_design(
        campaign_sha,
        search,
        equivalence,
        audit,
        records,
        protected_hashes,
    )
    lock = {
        "artifact_id": "large-scale-no-wall-capture-campaign-lock-v0.2",
        "schema_version": "2.0",
        "status": "LOCKED",
        "frozen_at": FROZEN_AT,
        "source_path": (
            "docs/status/integration/"
            "exploratory_large_scale_no_wall_scaling_best_k_v0_1/"
            "capture_campaign_v2.json"
        ),
        "source_sha256": campaign_sha,
        "source_byte_size": len(campaign_data),
        "p4a_head": P4A_HEAD,
        "original_campaign_sha256": ORIGINAL_CAMPAIGN_SHA256,
        "original_campaign_lock_sha256": ORIGINAL_CAMPAIGN_LOCK_SHA256,
        "fresh_outcomes_used": False,
        "old_capture_reuse_in_primary": False,
    }
    receipt = build_receipt(campaign_sha, audit, equivalence)
    write_json(output_package / "capture_campaign_v2.json", campaign)
    write_json(output_package / "capture_campaign_v2.lock.json", lock)
    write_json(output_package / "trajectory_profile_design_v2.json", design)
    write_json(output_package / "p4b_offline_profile_audit.json", audit)
    write_json(output_package / "p4b_receipt.json", receipt)
    require(
        sha256_file(output_package / "capture_campaign_v2.json") == campaign_sha,
        "written campaign hash differs",
    )
    return {
        "status": "PASS_REPAIRED_CAMPAIGN_FROZEN",
        "campaign_sha256": campaign_sha,
        "selected_candidate_ids": search["selected_candidate_ids"],
        "simulator_maximum_absolute_error_blocks": equivalence[
            "maximum_absolute_error_blocks"
        ],
        "old_high_pair_count": equivalence["old_high_abs_r_ge_0_95_count"],
        "repaired_high_pair_count": audit["profile_similarity"]["all_pairs"][
            "high_abs_r_ge_0_95_count"
        ],
        "repaired_high_pair_proportion": audit["profile_similarity"]["all_pairs"][
            "high_abs_r_ge_0_95_proportion"
        ],
        "safe_for_repaired_capture": True,
        "safe_for_p5": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-package", type=Path, default=PACKAGE)
    args = parser.parse_args()
    print(json.dumps(generate_artifacts(args.output_package), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
