"""Frozen Regime-A production primitives.

This module owns deterministic planning, validation, analysis contracts, and
restart/durability mechanics.  Live Minecraft and MineWorld adapters remain in
their existing validated modules; this code does not silently duplicate them.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np


VERSION = "regime-a-production-v0.1"
DT_SECONDS = 0.05
CAPTURE_HZ = 20
CONTEXT_PAIRS = 16
EFFECTIVE_PRECEDING_STEPS = 15
SPEED_BLOCKS_PER_SECOND = 1.5
MOTION_NOISE_Q = 0.05
HIDDEN_LEFT = -4.09654256549771
HIDDEN_RIGHT = 5.426536982279787
GEOMETRIC_ENTRY = {"LEFT_TO_RIGHT": -4.82, "RIGHT_TO_LEFT": 5.84}
ENTRY_GUARD = {"LEFT_TO_RIGHT": 20, "RIGHT_TO_LEFT": 8}
EXIT_GUARD = {"LEFT_TO_RIGHT": 8, "RIGHT_TO_LEFT": 20}
START_RANGE = {"LEFT_TO_RIGHT": (-8.0, -7.65), "RIGHT_TO_LEFT": (7.70, 8.0)}
BIN_BOUNDS = {
    "SHORT": (1, 4),
    "INTERMEDIATE": (5, 8),
    "LONG": (9, 12),
    "NEAR_CONTEXT": (13, 15),
    "BEYOND_CONTEXT": (16, 19),
}
PRIMARY_BINS = ("SHORT", "INTERMEDIATE", "LONG", "NEAR_CONTEXT")
ALL_LAYERS = tuple(range(20))
VISUAL_TOKEN_COUNT = 336
HIDDEN_WIDTH = 2048
FULL_DIMENSION = VISUAL_TOKEN_COUNT * HIDDEN_WIDTH
BEST_K_GRID = (1, 4, 8, 16, 32, 64, 128)
COMPLETE_STATE = "COMPLETE_VALIDATED_DURABLE"
STATE_ORDER = (
    "PLANNED",
    "RUNNING",
    "CAPTURED",
    "VALIDATED",
    "DURABLE",
    COMPLETE_STATE,
)


class RegimeAError(RuntimeError):
    """Fail-closed Regime-A contract violation."""


class ZeroTSS(RegimeAError):
    """Primary adjudication cannot proceed when any trajectory TSS is zero."""


def canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def sha256_file(path: Path, chunk_size: int = 8 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(chunk_size):
            digest.update(block)
    return digest.hexdigest()


def deterministic_seed(domain: str, authority_sha256: str, index: int) -> int:
    payload = f"{VERSION}|{domain}|{authority_sha256}|{index}".encode("utf-8")
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big") & ((1 << 63) - 1)


def direction_sign(direction: str) -> float:
    if direction == "LEFT_TO_RIGHT":
        return 1.0
    if direction == "RIGHT_TO_LEFT":
        return -1.0
    raise RegimeAError(f"unknown direction: {direction}")


def simulate_path(seed: int, direction: str, start: float, frames: int = 260) -> tuple[np.ndarray, np.ndarray]:
    if frames < 60 or not math.isfinite(start):
        raise RegimeAError("invalid state-path request")
    rng = np.random.default_rng(seed)
    noise = rng.standard_normal(frames) * math.sqrt(MOTION_NOISE_Q * DT_SECONDS)
    increments = direction_sign(direction) * SPEED_BLOCKS_PER_SECOND * DT_SECONDS + noise
    positions = float(start) + np.cumsum(increments)
    if not np.isfinite(positions).all():
        raise RegimeAError("nonfinite state path")
    return positions, noise


def stable_hidden_interval(positions: np.ndarray, direction: str) -> tuple[int, int]:
    positions = np.asarray(positions, dtype=np.float64)
    inside = (positions >= HIDDEN_LEFT) & (positions <= HIDDEN_RIGHT)
    entry = next(
        (index for index in range(len(positions) - 18) if inside[index : index + 19].all()),
        None,
    )
    if entry is None:
        raise RegimeAError("path lacks 19 consecutive stable-hidden frames")
    crossed = positions >= GEOMETRIC_ENTRY[direction] if direction == "LEFT_TO_RIGHT" else positions <= GEOMETRIC_ENTRY[direction]
    transition_indices = np.flatnonzero(crossed)
    if transition_indices.size == 0:
        raise RegimeAError("path lacks geometric entry")
    transition = int(transition_indices[0])
    if transition < EFFECTIVE_PRECEDING_STEPS:
        raise RegimeAError("path lacks full pre-entry causal history")
    if entry - transition > ENTRY_GUARD[direction]:
        raise RegimeAError("entry transition exceeds frozen direction guard")
    exited = positions > HIDDEN_RIGHT if direction == "LEFT_TO_RIGHT" else positions < HIDDEN_LEFT
    exit_indices = np.flatnonzero(exited & (np.arange(len(positions)) > entry + 18))
    if exit_indices.size == 0:
        raise RegimeAError("path lacks stable-hidden exit")
    exit_frame = int(exit_indices[0])
    if exit_frame + EXIT_GUARD[direction] >= len(positions):
        raise RegimeAError("path lacks post-exit containment margin")
    return entry, exit_frame


def trailing_window_indices(target_frame: int, frame_count: int) -> tuple[int, ...]:
    if target_frame < 0 or target_frame >= frame_count:
        raise RegimeAError("target frame outside trajectory")
    start = max(0, target_frame - EFFECTIVE_PRECEDING_STEPS)
    return tuple(range(start, target_frame + 1))


def classify_visibility(geometric_status: str, magenta_status: str) -> str:
    if geometric_status == "visible" and magenta_status == "detected":
        return "VISIBLE_AGREEMENT"
    if geometric_status == "occluded" and magenta_status == "not_detected":
        return "OCCLUDED_AGREEMENT"
    geometric_binary = geometric_status in {"visible", "occluded"}
    magenta_binary = magenta_status in {"detected", "not_detected"}
    if geometric_binary and magenta_binary:
        return "VISIBILITY_DISAGREEMENT"
    return "INVALID_VISIBILITY"


def assign_stable_hidden_tau(rows: Sequence[Mapping[str, Any]], direction: str) -> list[dict[str, Any]]:
    if direction not in ENTRY_GUARD:
        raise RegimeAError("unknown direction")
    output = [dict(row) for row in rows]
    labels = [
        classify_visibility(str(row.get("geometric_status")), str(row.get("magenta_status")))
        for row in output
    ]
    onset = next(
        (
            index
            for index in range(len(labels) - 18)
            if labels[index : index + 19] == ["OCCLUDED_AGREEMENT"] * 19
        ),
        None,
    )
    if onset is None:
        raise RegimeAError("no stable 19-frame OCCLUDED_AGREEMENT run")
    transition_start = onset
    while transition_start > 0 and labels[transition_start - 1] in {
        "VISIBILITY_DISAGREEMENT",
        "INVALID_VISIBILITY",
    }:
        transition_start -= 1
    if onset - transition_start > ENTRY_GUARD[direction]:
        raise RegimeAError("observed entry transition exceeds frozen guard")
    tau = 0
    for index, row in enumerate(output):
        row["visibility_class"] = labels[index]
        row["tau"] = None
        row["duration_bin"] = None
        row["primary_hidden_eligible"] = False
        if index >= onset and labels[index] == "OCCLUDED_AGREEMENT":
            tau += 1
            row["tau"] = tau
            row["duration_bin"] = duration_bin(tau)
            row["primary_hidden_eligible"] = duration_bin(tau) is not None
        elif index >= onset:
            tau = 0
    return output


def duration_bin(tau: int) -> str | None:
    if type(tau) is not int or tau < 1:
        return None
    for name, (start, stop) in BIN_BOUNDS.items():
        if start <= tau <= stop:
            return name
    return None


def project_world_to_coordinates(
    world_x: float, world_z: float, world_to_raw_screen: Sequence[Sequence[float]]
) -> dict[str, object]:
    matrix = np.asarray(world_to_raw_screen, dtype=np.float64)
    if matrix.shape != (3, 3) or not np.isfinite(matrix).all():
        raise RegimeAError("projection matrix must be finite 3x3")
    homogeneous = matrix @ np.asarray([world_x, world_z, 1.0], dtype=np.float64)
    if not np.isfinite(homogeneous).all() or abs(homogeneous[2]) <= 1e-12:
        raise RegimeAError("projection is nonfinite or singular")
    raw_x, raw_y = homogeneous[:2] / homogeneous[2]
    screen_x = float(raw_x * 640.0 / 1920.0)
    screen_y = float(raw_y * 360.0 / 1046.0)
    token_row = screen_y * 14.0 / 360.0
    token_col = screen_x * 24.0 / 640.0
    if not (0 <= screen_x < 640 and 0 <= screen_y < 360 and 0 <= token_row < 14 and 0 <= token_col < 24):
        raise RegimeAError("projected coordinate outside frozen bounds")
    return {
        "world_x": float(world_x),
        "world_z": float(world_z),
        "screen_x": screen_x,
        "screen_y": screen_y,
        "token_row": token_row,
        "token_col": token_col,
        "token_cell_row": math.floor(token_row),
        "token_cell_col": math.floor(token_col),
    }


def validate_frame_alignment(rows: Sequence[Mapping[str, Any]], target_entity_id: str) -> None:
    if not rows:
        raise RegimeAError("empty trajectory")
    for index, row in enumerate(rows):
        expected = (index, index, index, index)
        observed = tuple(row.get(field) for field in ("model_frame_idx", "server_tick", "render_frame_idx", "action_idx"))
        if observed != expected:
            raise RegimeAError(f"frame alignment mismatch at {index}: {observed}")
        if row.get("target_entity_id") != target_entity_id or row.get("target_present") is not True:
            raise RegimeAError(f"target identity/presence mismatch at {index}")


def trajectory_r2(actual: Sequence[float], predicted: Sequence[float]) -> dict[str, float]:
    y = np.asarray(actual, dtype=np.float64)
    yhat = np.asarray(predicted, dtype=np.float64)
    if y.ndim != 1 or y.shape != yhat.shape or y.size == 0 or not np.isfinite(y).all() or not np.isfinite(yhat).all():
        raise RegimeAError("invalid trajectory metric arrays")
    residual = y - yhat
    sse = float(residual @ residual)
    centered = y - y.mean()
    tss = float(centered @ centered)
    if tss <= 0:
        raise ZeroTSS("trajectory TSS_t is zero")
    return {"sse": sse, "tss": tss, "r2": float(1.0 - sse / tss)}


def macro_r2(
    actual: Mapping[str, Sequence[float]], predicted: Mapping[str, Sequence[float]]
) -> dict[str, object]:
    if set(actual) != set(predicted) or not actual:
        raise RegimeAError("trajectory key mismatch")
    per = {key: trajectory_r2(actual[key], predicted[key]) for key in sorted(actual)}
    return {
        "per_trajectory": per,
        "macro_r2": float(np.mean([row["r2"] for row in per.values()])),
        "trajectory_count": len(per),
        "weighting": "unweighted_equal_trajectory",
    }


def natural_unit_metrics(actual: Sequence[float], predicted: Sequence[float]) -> dict[str, float]:
    error = np.abs(np.asarray(actual, dtype=np.float64) - np.asarray(predicted, dtype=np.float64))
    if error.ndim != 1 or error.size == 0 or not np.isfinite(error).all():
        raise RegimeAError("invalid natural-unit metric arrays")
    return {"mae": float(error.mean()), "median_absolute_error": float(np.median(error))}


def last_visible_position_baseline(last_visible_x: float, tau_count: int) -> np.ndarray:
    if tau_count < 1 or not math.isfinite(last_visible_x):
        raise RegimeAError("invalid last-visible baseline request")
    return np.full(tau_count, last_visible_x, dtype=np.float64)


def constant_velocity_baseline(visible_times: Sequence[float], visible_x: Sequence[float], hidden_times: Sequence[float]) -> np.ndarray:
    time = np.asarray(visible_times, dtype=np.float64)[-EFFECTIVE_PRECEDING_STEPS:]
    x = np.asarray(visible_x, dtype=np.float64)[-EFFECTIVE_PRECEDING_STEPS:]
    targets = np.asarray(hidden_times, dtype=np.float64)
    if time.size < 2 or time.shape != x.shape or targets.ndim != 1:
        raise RegimeAError("constant-velocity baseline lacks causal visible support")
    design = np.column_stack([np.ones(time.size), time])
    coefficient, *_ = np.linalg.lstsq(design, x, rcond=None)
    return coefficient[0] + coefficient[1] * targets


def training_mean_baseline(training_targets: Sequence[float], heldout_count: int) -> np.ndarray:
    values = np.asarray(training_targets, dtype=np.float64)
    if values.ndim != 1 or values.size == 0 or heldout_count < 1 or not np.isfinite(values).all():
        raise RegimeAError("invalid training-mean baseline request")
    return np.full(heldout_count, float(values.mean()), dtype=np.float64)


def ridge_fit_predict(
    training_features: np.ndarray,
    training_targets: Sequence[float],
    heldout_features: np.ndarray,
    alpha: float,
) -> np.ndarray:
    """Deterministic centered ridge, using the sample-space solve when p > n."""
    x = np.asarray(training_features, dtype=np.float64)
    y = np.asarray(training_targets, dtype=np.float64)
    z = np.asarray(heldout_features, dtype=np.float64)
    if (
        x.ndim != 2
        or z.ndim != 2
        or x.shape[0] != y.size
        or x.shape[1] != z.shape[1]
        or x.shape[0] < 2
        or not math.isfinite(alpha)
        or alpha <= 0
        or not np.isfinite(x).all()
        or not np.isfinite(y).all()
        or not np.isfinite(z).all()
    ):
        raise RegimeAError("invalid ridge arrays")
    x_mean = x.mean(axis=0)
    y_mean = y.mean()
    xc = x - x_mean
    yc = y - y_mean
    zc = z - x_mean
    if x.shape[1] > x.shape[0]:
        dual = np.linalg.solve(xc @ xc.T + alpha * np.eye(x.shape[0]), yc)
        return zc @ xc.T @ dual + y_mean
    coefficient = np.linalg.solve(xc.T @ xc + alpha * np.eye(x.shape[1]), xc.T @ yc)
    return zc @ coefficient + y_mean


def rank_best_k_tokens(training_features: np.ndarray, training_targets: Sequence[float]) -> np.ndarray:
    """Rank visual tokens only from outer-training rows; features are [n,tokens,width]."""
    features = np.asarray(training_features, dtype=np.float64)
    target = np.asarray(training_targets, dtype=np.float64)
    if features.ndim != 3 or features.shape[0] != target.size or features.shape[1] < max(BEST_K_GRID):
        raise RegimeAError("invalid BEST-K training arrays")
    centered_y = target - target.mean()
    centered_x = features - features.mean(axis=0, keepdims=True)
    denominator = np.sqrt((centered_x * centered_x).sum(axis=0) * float(centered_y @ centered_y))
    correlation = np.divide(
        np.abs(np.einsum("nth,n->th", centered_x, centered_y)),
        denominator,
        out=np.zeros_like(denominator),
        where=denominator > 0,
    )
    score = correlation.max(axis=1)
    return np.lexsort((np.arange(score.size), -score))


def best_k_features(features: np.ndarray, ranked_tokens: Sequence[int], k: int) -> np.ndarray:
    array = np.asarray(features)
    ranking = np.asarray(ranked_tokens, dtype=np.int64)
    if array.ndim != 3 or k not in BEST_K_GRID or ranking.ndim != 1 or ranking.size < k:
        raise RegimeAError("invalid BEST-K projection")
    selected = ranking[:k]
    if len(set(selected.tolist())) != k or selected.min() < 0 or selected.max() >= array.shape[1]:
        raise RegimeAError("invalid BEST-K token identities")
    return array[:, selected, :].reshape(array.shape[0], -1)


def validate_best_k_selection(selection: Mapping[str, Any], outer_training_ids: set[str], outer_test_ids: set[str]) -> None:
    if outer_training_ids & outer_test_ids or not outer_training_ids or not outer_test_ids:
        raise RegimeAError("invalid outer trajectory partition")
    used = set(selection.get("trajectory_ids_used", ()))
    if not used or not used <= outer_training_ids or used & outer_test_ids:
        raise RegimeAError("BEST-K selection leaks heldout trajectories")
    if selection.get("layer") != 4 or selection.get("selected_k") not in BEST_K_GRID:
        raise RegimeAError("BEST-K layer/K violates frozen authority")
    if selection.get("shared_across_bins") is not True or selection.get("shared_across_directions") is not True:
        raise RegimeAError("BEST-K was reselected by bin or direction")


def bootstrap_macro_r2(per_trajectory_r2: Mapping[str, float], replicates: int, seed: int) -> np.ndarray:
    values = np.asarray([per_trajectory_r2[key] for key in sorted(per_trajectory_r2)], dtype=np.float64)
    if values.size == 0 or replicates < 1 or not np.isfinite(values).all():
        raise RegimeAError("invalid bootstrap request")
    rng = np.random.default_rng(seed)
    indices = rng.integers(0, values.size, size=(replicates, values.size))
    return values[indices].mean(axis=1)


def _derangement(values: list[str], rng: np.random.Generator) -> dict[str, str]:
    if len(values) < 2:
        raise RegimeAError("null stratum needs at least two donors")
    source = list(values)
    for _ in range(10000):
        permuted = [source[index] for index in rng.permutation(len(source))]
        if all(left != right for left, right in zip(source, permuted, strict=True)):
            return dict(zip(source, permuted, strict=True))
    raise RegimeAError("could not construct no-self derangement")


def build_null_mappings(
    training_ids: Sequence[str], strata: Mapping[str, str], *, b: int, seed: int
) -> list[dict[str, str]]:
    ids = sorted(training_ids)
    if b != 49 or set(ids) != set(strata):
        raise RegimeAError("null request violates frozen B or stratum identity")
    grouped: dict[str, list[str]] = defaultdict(list)
    for identity in ids:
        grouped[strata[identity]].append(identity)
    rng = np.random.default_rng(seed)
    mappings: list[dict[str, str]] = []
    hashes: set[str] = set()
    attempts = 0
    while len(mappings) < b and attempts < 100000:
        attempts += 1
        mapping: dict[str, str] = {}
        for values in grouped.values():
            mapping.update(_derangement(sorted(values), rng))
        digest = canonical_sha256(mapping)
        if digest not in hashes:
            hashes.add(digest)
            mappings.append(mapping)
    if len(mappings) != b:
        raise RegimeAError("49 unique valid null mappings are infeasible")
    validate_null_mappings(mappings, set(ids), strata)
    return mappings


def validate_null_mappings(
    mappings: Sequence[Mapping[str, str]], training_ids: set[str], strata: Mapping[str, str]
) -> None:
    if len(mappings) != 49 or len({canonical_sha256(dict(row)) for row in mappings}) != 49:
        raise RegimeAError("null mappings are not 49 unique replicates")
    for mapping in mappings:
        if set(mapping) != training_ids or set(mapping.values()) != training_ids:
            raise RegimeAError("null mapping leaves outer training")
        for receiver, donor in mapping.items():
            if receiver == donor:
                raise RegimeAError("null self donor")
            if strata[receiver] != strata[donor]:
                raise RegimeAError("null mapping crosses frozen motion stratum")


def fold_assignment(specs: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    if len(specs) != 25:
        raise RegimeAError("first slice must contain exactly 25 specs")
    assignments: dict[str, int] = {}
    targets = ((3, 2), (2, 3), (3, 2), (2, 3), (3, 2))
    grouped = {
        direction: sorted(
            (row for row in specs if row["direction"] == direction),
            key=lambda row: (row["seed"], row["trajectory_spec_id"]),
        )
        for direction in ("LEFT_TO_RIGHT", "RIGHT_TO_LEFT")
    }
    if [len(grouped["LEFT_TO_RIGHT"]), len(grouped["RIGHT_TO_LEFT"])] != [13, 12]:
        raise RegimeAError("direction balance must be 13/12")
    offset = {key: 0 for key in grouped}
    for fold, counts in enumerate(targets):
        for direction, count in zip(grouped, counts, strict=True):
            for row in grouped[direction][offset[direction] : offset[direction] + count]:
                assignments[row["trajectory_spec_id"]] = fold
            offset[direction] += count
    return assignments


def _candidate_spec(
    study_sha256: str,
    direction: str,
    index: int,
    serial: int,
    authority_bindings: Mapping[str, str],
) -> dict[str, Any] | None:
    seed = deterministic_seed(f"A3_{direction}", study_sha256, index)
    rng = np.random.default_rng(seed ^ 0xA3A3A3A3)
    start = float(rng.uniform(*START_RANGE[direction]))
    positions, noise = simulate_path(seed, direction, start)
    try:
        entry, exit_frame = stable_hidden_interval(positions, direction)
    except RegimeAError:
        return None
    identity = f"regime_a_v1_t{serial + 1:02d}"
    body: dict[str, Any] = {
        "schema_version": "regime-a-trajectory-spec-v1.0",
        "trajectory_spec_id": identity,
        "scientific_role": "REAL_REGIME_A_FIRST_SLICE",
        "execution_state": "FROZEN_NOT_EXECUTED",
        "episode_id": 51001 + serial,
        "seed": seed,
        "noise_seed": seed,
        "direction": direction,
        "speed_blocks_per_second": SPEED_BLOCKS_PER_SECOND,
        "motion_noise_q": MOTION_NOISE_Q,
        "start_world_x": start,
        "start_world_y": 4.0,
        "start_world_z": 6.0,
        "initial_motion_phase": float(rng.uniform(0.0, 1.0)),
        "expected_stable_hidden_onset_frame": entry,
        "expected_stable_hidden_exit_frame": exit_frame,
        "expected_tau_1_to_19_world_x": [float(value) for value in positions[entry : entry + 19]],
        "expected_profile_sha256": hashlib.sha256(np.asarray(positions, dtype="<f8").tobytes()).hexdigest(),
        "noise_schedule_sha256": hashlib.sha256(np.asarray(noise, dtype="<f8").tobytes()).hexdigest(),
        "expected_max_frames": len(positions),
        "entry_guard_frames": ENTRY_GUARD[direction],
        "exit_guard_frames": EXIT_GUARD[direction],
        "target_entity_logical_id": f"{identity}:magenta_sheep",
        "camera_authority": "layout_01_fixed_v0.4",
        "wall_authority": "layout_01_long_wall_v0.4",
        "retry_policy": "IDENTICAL_SPEC_AND_SEED_ONLY",
        "authority_bindings": dict(sorted(authority_bindings.items())),
    }
    body["spec_hash"] = canonical_sha256(body)
    return body


def generate_scientific_specs(
    study_sha256: str, authority_bindings: Mapping[str, str] | None = None
) -> list[dict[str, Any]]:
    if len(study_sha256) != 64:
        raise RegimeAError("study authority hash is invalid")
    bindings = {"a1_study_manifest_sha256": study_sha256, **dict(authority_bindings or {})}
    if any(len(name) == 0 or len(digest) != 64 for name, digest in bindings.items()):
        raise RegimeAError("authority bindings must be named SHA256 digests")
    specs: list[dict[str, Any]] = []
    for direction, needed in (("LEFT_TO_RIGHT", 13), ("RIGHT_TO_LEFT", 12)):
        index = 0
        while sum(row["direction"] == direction for row in specs) < needed:
            candidate = _candidate_spec(study_sha256, direction, index, len(specs), bindings)
            index += 1
            if candidate is not None and all(
                math.sqrt(
                    float(
                        np.mean(
                            (
                                np.asarray(candidate["expected_tau_1_to_19_world_x"])
                                - np.asarray(existing["expected_tau_1_to_19_world_x"])
                            )
                            ** 2
                        )
                    )
                )
                >= 0.10
                for existing in specs
                if existing["direction"] == direction
            ):
                specs.append(candidate)
            if index > 10000:
                raise RegimeAError("could not generate valid frozen spec set")
    assignments = fold_assignment(specs)
    result = []
    for row in specs:
        body = dict(row)
        body.pop("spec_hash")
        body["outer_fold"] = assignments[row["trajectory_spec_id"]]
        body["spec_hash"] = canonical_sha256(body)
        result.append(body)
    validate_scientific_specs(result)
    return result


def validate_scientific_specs(specs: Sequence[Mapping[str, Any]]) -> dict[str, object]:
    if len(specs) != 25:
        raise RegimeAError("manifest count is not 25")
    ids = [str(row["trajectory_spec_id"]) for row in specs]
    seeds = [int(row["seed"]) for row in specs]
    hashes = [str(row["spec_hash"]) for row in specs]
    if len(set(ids)) != 25 or len(set(seeds)) != 25 or len(set(hashes)) != 25:
        raise RegimeAError("spec IDs, seeds, or hashes are not unique")
    fold_counts = defaultdict(int)
    direction_counts = defaultdict(int)
    profiles = []
    for row in specs:
        body = dict(row)
        claimed = body.pop("spec_hash")
        if canonical_sha256(body) != claimed:
            raise RegimeAError(f"spec hash mismatch: {row['trajectory_spec_id']}")
        if row.get("execution_state") != "FROZEN_NOT_EXECUTED":
            raise RegimeAError("spec execution state is not frozen/unexecuted")
        direction = str(row["direction"])
        positions, noise = simulate_path(int(row["seed"]), direction, float(row["start_world_x"]))
        entry, exit_frame = stable_hidden_interval(positions, direction)
        if entry != row["expected_stable_hidden_onset_frame"] or exit_frame != row["expected_stable_hidden_exit_frame"]:
            raise RegimeAError("expected geometry drift")
        expected = [float(value) for value in positions[entry : entry + 19]]
        if expected != list(row["expected_tau_1_to_19_world_x"]):
            raise RegimeAError("candidate-bin target path drift")
        if hashlib.sha256(np.asarray(noise, dtype="<f8").tobytes()).hexdigest() != row["noise_schedule_sha256"]:
            raise RegimeAError("noise schedule drift")
        if float(np.var(expected[:15])) <= 0:
            raise ZeroTSS("prospective primary target has zero variance")
        fold_counts[int(row["outer_fold"])] += 1
        direction_counts[direction] += 1
        profiles.append((direction, np.asarray(expected)))
    if dict(fold_counts) != {0: 5, 1: 5, 2: 5, 3: 5, 4: 5}:
        raise RegimeAError("outer fold balance failed")
    if dict(direction_counts) != {"LEFT_TO_RIGHT": 13, "RIGHT_TO_LEFT": 12}:
        raise RegimeAError("direction balance failed")
    exact = [hashlib.sha256(values.tobytes()).hexdigest() for _direction, values in profiles]
    if len(set(exact)) != 25:
        raise RegimeAError("exact duplicate eligible target profiles")
    return {
        "trajectory_count": 25,
        "fold_counts": dict(sorted(fold_counts.items())),
        "direction_counts": dict(sorted(direction_counts.items())),
        "exact_duplicate_count": 0,
        "all_bins_covered": True,
        "all_primary_tss_positive_prospectively": True,
    }


class HashChainLedger:
    """Append-only fsync'd ledger with deterministic record hashes."""

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.records = []
        if path.exists():
            self.records = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
        previous = None
        for record in self.records:
            body = dict(record)
            claimed = body.pop("record_sha256", None)
            if body.get("previous_record_sha256") != previous or canonical_sha256(body) != claimed:
                raise RegimeAError("ledger chain validation failed")
            previous = claimed

    def append(self, trajectory_spec_id: str, state: str, **fields: object) -> dict[str, object]:
        if state not in STATE_ORDER:
            raise RegimeAError("invalid progress state")
        previous_state = next(
            (row["state"] for row in reversed(self.records) if row["trajectory_spec_id"] == trajectory_spec_id),
            None,
        )
        if previous_state is not None and STATE_ORDER.index(state) < STATE_ORDER.index(str(previous_state)):
            if not fields.get("retry_same_spec") or state not in {"PLANNED", "RUNNING"}:
                raise RegimeAError("ledger state regression")
            prior = next(
                row for row in reversed(self.records)
                if row["trajectory_spec_id"] == trajectory_spec_id
            )
            if (
                prior.get("spec_hash") not in {None, fields.get("spec_hash")}
                or prior.get("seed") not in {None, fields.get("seed")}
            ):
                raise RegimeAError("retry changed frozen spec hash or seed")
        body: dict[str, object] = {
            "schema_version": "regime-a-progress-ledger-v1.0",
            "record_index": len(self.records),
            "trajectory_spec_id": trajectory_spec_id,
            "state": state,
            "previous_record_sha256": self.records[-1]["record_sha256"] if self.records else None,
            **fields,
        }
        record = {**body, "record_sha256": canonical_sha256(body)}
        descriptor = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
        try:
            os.write(descriptor, canonical_bytes(record) + b"\n")
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        self.records.append(record)
        return record

    def complete_ids(self) -> set[str]:
        return {str(row["trajectory_spec_id"]) for row in self.records if row["state"] == COMPLETE_STATE}


class AtomicTrajectoryStore:
    """Atomic per-trajectory staging and same-spec resume boundary."""

    def __init__(self, root: Path):
        self.root = root
        root.mkdir(parents=True, exist_ok=True)

    def begin(self, spec_id: str, spec_hash: str) -> Path:
        final = self.root / spec_id
        partial = self.root / f".{spec_id}.{spec_hash[:16]}.partial"
        if final.exists():
            completion = json.loads((final / "completion.json").read_text())
            if completion.get("spec_hash") != spec_hash:
                raise RegimeAError("completed trajectory spec hash drift")
            raise FileExistsError(final)
        if partial.exists():
            raise RegimeAError("partial staging exists; validate/quarantine before retry")
        partial.mkdir(parents=True)
        _atomic_json(
            partial / "partial_identity.json",
            {"trajectory_spec_id": spec_id, "spec_hash": spec_hash},
        )
        return partial

    def discard_same_spec_partial(self, spec_id: str, spec_hash: str) -> bool:
        """Discard only an identity-proven, non-final partial retry unit."""

        partial = self.same_spec_partial(spec_id, spec_hash)
        if partial is None:
            return False
        shutil.rmtree(partial)
        return True

    def same_spec_partial(self, spec_id: str, spec_hash: str) -> Path | None:
        """Return only an identity-proven partial, without mutating it."""

        partial = self.root / f".{spec_id}.{spec_hash[:16]}.partial"
        if not partial.exists():
            return None
        marker = partial / "partial_identity.json"
        if not marker.is_file():
            raise RegimeAError("partial staging lacks an identity marker")
        identity = json.loads(marker.read_text(encoding="utf-8"))
        if identity != {"trajectory_spec_id": spec_id, "spec_hash": spec_hash}:
            raise RegimeAError("partial staging identity mismatch")
        return partial

    def finalize(self, partial: Path, spec_id: str, spec_hash: str) -> Path:
        files = sorted(path for path in partial.rglob("*") if path.is_file())
        inventory = [
            {"path": str(path.relative_to(partial)), "byte_size": path.stat().st_size, "sha256": sha256_file(path)}
            for path in files
        ]
        completion = {"status": "VALIDATED", "trajectory_spec_id": spec_id, "spec_hash": spec_hash, "inventory": inventory}
        _atomic_json(partial / "completion.json", completion)
        final = self.root / spec_id
        os.replace(partial, final)
        return final

    def validate(self, spec_id: str, spec_hash: str) -> dict[str, Any]:
        root = self.root / spec_id
        completion = json.loads((root / "completion.json").read_text())
        if completion.get("trajectory_spec_id") != spec_id or completion.get("spec_hash") != spec_hash:
            raise RegimeAError("completion identity mismatch")
        for row in completion["inventory"]:
            path = root / row["path"]
            if path.stat().st_size != row["byte_size"] or sha256_file(path) != row["sha256"]:
                raise RegimeAError("completion artifact hash mismatch")
        return completion


def _atomic_json(path: Path, value: object) -> None:
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    payload = json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"
    with temporary.open("x", encoding="utf-8") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def verified_local_durable_copy(source: Path, destination: Path) -> dict[str, object]:
    if destination.exists():
        raise RegimeAError("durable destination already exists")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    source_hash = sha256_file(source)
    destination_hash = sha256_file(destination)
    if source.stat().st_size != destination.stat().st_size or source_hash != destination_hash:
        raise RegimeAError("durable copy verification failed")
    return {"byte_size": source.stat().st_size, "sha256": source_hash, "verified": True}


def validate_a4_authorization(
    document: Mapping[str, Any],
    manifest_sha256: str,
    study_sha256: str,
    *,
    expected_bindings: Mapping[str, str] | None = None,
) -> None:
    if (
        document.get("status") != "AUTHORIZED_A4_SCIENTIFIC_EXECUTION"
        or document.get("trajectory_manifest_sha256") != manifest_sha256
        or document.get("study_manifest_sha256") != study_sha256
        or document.get("operator") != "Kazim Abbas"
    ):
        raise RegimeAError("missing or mismatched A4 operator authorization")
    for field, expected in dict(expected_bindings or {}).items():
        if document.get(field) != expected:
            raise RegimeAError(f"A4 authorization binding mismatch: {field}")


def activation_bytes_per_trajectory(eligible_frames: int = 19) -> int:
    if eligible_frames < 1:
        raise RegimeAError("eligible frame count must be positive")
    return eligible_frames * len(ALL_LAYERS) * VISUAL_TOKEN_COUNT * HIDDEN_WIDTH * 2
