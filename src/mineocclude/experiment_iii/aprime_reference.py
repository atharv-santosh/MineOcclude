"""Retrieval of the bound historical A-prime artifacts from the git object database.

Authority 5.1/5.3 and test D.2 bind their reference artifacts to git objects
rather than to working-tree files, because the paths are not present in the
current worktree. Everything here reads those objects, verifies the bound
SHA-256 **before** any field is read, and refuses otherwise.

Nothing in this module is an Experiment III scientific value. It supplies the
historical evidence that the FIR recovery and the q-regression are checked
against.
"""

from __future__ import annotations

import hashlib
import json
import math
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Mapping, Sequence

import numpy as np

from mineocclude.experiment_iii.authority import (
    D2_REFERENCE_BLOB_SHA1,
    D2_REFERENCE_BYTES,
    D2_REFERENCE_COMMIT,
    D2_REFERENCE_PATH,
    D2_REFERENCE_SHA256,
    D2_REFERENCE_UNIT_ID,
    FIR_RECOVERY_COMMIT,
    FIR_RECOVERY_PATH,
    FIR_RECOVERY_SHA256,
    REPOSITORY_ROOT,
)
from mineocclude.experiment_iii.errors import ExperimentIIIError

__all__ = [
    "AprimeUnit",
    "read_git_blob",
    "fir_recovery_manifest",
    "d2_reference_manifest",
    "aprime_materialized_units",
    "d2_reference_unit",
    "aprime_generate_path",
    "path_sha256",
]


def read_git_blob(commit: str, path: str, *, expected_sha256: str | None = None) -> bytes:
    """``git cat-file blob <commit>:<path>``, verified against a bound digest."""
    try:
        completed = subprocess.run(
            ["git", "cat-file", "blob", f"{commit}:{path}"],
            cwd=REPOSITORY_ROOT,
            capture_output=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise ExperimentIIIError(
            "APRIME_PORT_SOURCE_UNAVAILABLE",
            f"cannot retrieve {commit}:{path} from the git object database: {error}",
        ) from error
    payload = completed.stdout
    if expected_sha256 is not None:
        observed = hashlib.sha256(payload).hexdigest()
        if observed != expected_sha256:
            raise ExperimentIIIError(
                "APRIME_PORT_SOURCE_UNAVAILABLE",
                f"{commit}:{path} hashes {observed}, expected {expected_sha256}",
            )
    return payload


def _git_blob_sha1(payload: bytes) -> str:
    return hashlib.sha1(b"blob %d\0" % len(payload) + payload).hexdigest()


@lru_cache(maxsize=1)
def fir_recovery_manifest() -> dict[str, Any]:
    """The bound ``v0_4`` stage-2 manifest carrying the materialized labels."""
    payload = read_git_blob(
        FIR_RECOVERY_COMMIT, FIR_RECOVERY_PATH, expected_sha256=FIR_RECOVERY_SHA256
    )
    return json.loads(payload)


@lru_cache(maxsize=1)
def d2_reference_manifest() -> dict[str, Any]:
    """The bound ``v0_3`` manifest carrying the D.2 regression reference.

    A **different file** from the FIR recovery source, bound at the same commit.
    The reference path hash is not present in ``v0_4``.
    """
    payload = read_git_blob(
        D2_REFERENCE_COMMIT, D2_REFERENCE_PATH, expected_sha256=D2_REFERENCE_SHA256
    )
    if len(payload) != D2_REFERENCE_BYTES:
        raise ExperimentIIIError(
            "APRIME_PORT_SOURCE_UNAVAILABLE",
            f"D.2 reference manifest is {len(payload)} bytes, expected "
            f"{D2_REFERENCE_BYTES}",
        )
    observed_blob = _git_blob_sha1(payload)
    if observed_blob != D2_REFERENCE_BLOB_SHA1:
        raise ExperimentIIIError(
            "APRIME_PORT_SOURCE_UNAVAILABLE",
            f"D.2 reference blob is {observed_blob}, expected {D2_REFERENCE_BLOB_SHA1}",
        )
    return json.loads(payload)


@dataclass(frozen=True)
class AprimeUnit:
    """One A-prime stage-2 capture unit with a materialized target window."""

    unit_id: str
    trajectory_id: str
    scene: str
    direction: str
    seed: int
    noise_seed: int
    start_world_x: float
    speed_blocks_per_second: float
    motion_noise_q: float
    expected_frames: int
    expected_path_sha256: str
    #: Empty on a pre-materialization manifest such as the ``v0_3`` D.2
    #: reference, whose units carry a trajectory but no target window yet.
    target_model_frame_indices: tuple[int, ...] = ()
    expected_causal_fir_target_world_x_blocks: tuple[float, ...] = ()

    @classmethod
    def from_mapping(cls, row: Mapping[str, Any]) -> "AprimeUnit":
        return cls(
            unit_id=str(row["unit_id"]),
            trajectory_id=str(row["trajectory_id"]),
            scene=str(row["scene"]),
            direction=str(row["direction"]),
            seed=int(row["seed"]),
            noise_seed=int(row["noise_seed"]),
            start_world_x=float(row["start_world_x"]),
            speed_blocks_per_second=float(row["speed_blocks_per_second"]),
            motion_noise_q=float(row["motion_noise_q"]),
            expected_frames=int(row["expected_frames"]),
            expected_path_sha256=str(row["expected_path_sha256"]),
            target_model_frame_indices=tuple(
                int(value) for value in row.get("target_model_frame_indices", ())
            ),
            expected_causal_fir_target_world_x_blocks=tuple(
                float(value)
                for value in row.get(
                    "expected_causal_fir_target_world_x_blocks", ()
                )
            ),
        )


def aprime_materialized_units() -> list[AprimeUnit]:
    """The 50 capture units whose target windows were materialized from Stage 1."""
    manifest = fir_recovery_manifest()
    units = [
        AprimeUnit.from_mapping(row)
        for row in manifest["units"]
        if row.get("target_window_status") == "MATERIALIZED_FROM_STAGE1"
    ]
    if len(units) != 50:
        raise ExperimentIIIError(
            "FIR_KERNEL_RECOVERY_FAILED",
            f"expected 50 materialized A-prime units, found {len(units)}",
        )
    incomplete = [unit.unit_id for unit in units if not unit.target_model_frame_indices]
    if incomplete:
        raise ExperimentIIIError(
            "FIR_KERNEL_RECOVERY_FAILED",
            f"materialized units carry no target window: {incomplete[:4]}",
        )
    return units


def d2_reference_unit() -> AprimeUnit:
    """``a2x_t01_wall`` from the bound ``v0_3`` manifest."""
    manifest = d2_reference_manifest()
    for row in manifest["units"]:
        if row.get("unit_id") == D2_REFERENCE_UNIT_ID:
            return AprimeUnit.from_mapping(row)
    raise ExperimentIIIError(
        "APRIME_PORT_SOURCE_UNAVAILABLE",
        f"{D2_REFERENCE_UNIT_ID} is absent from the bound D.2 reference manifest",
    )


def aprime_generate_path(
    *,
    noise_seed: int,
    start_world_x: float,
    direction: str,
    q: float,
    speed: float,
    frames: int,
    dt: float = 0.05,
    lane_min: float = -8.0,
    lane_max: float = 8.0,
) -> tuple[np.ndarray, np.ndarray]:
    """The A-prime generator arithmetic, reproduced exactly.

    Iterative binary64 accumulation, drift added **before** noise, clamped to the
    lane. This is the arithmetic the FIR recovery is validated against; a
    vectorized ``cumsum`` is not bit-identical and is forbidden.

    Kept separate from :mod:`mineocclude.experiment_iii.cohort` so the historical
    reproduction and the Experiment III generator can be compared rather than
    assumed identical.
    """
    if direction == "LEFT_TO_RIGHT":
        sign = 1.0
    elif direction == "RIGHT_TO_LEFT":
        sign = -1.0
    else:
        raise ExperimentIIIError(
            "COHORT_MATRIX_INCONSISTENT", f"unknown direction {direction!r}"
        )
    noise = np.random.default_rng(noise_seed).standard_normal(frames) * math.sqrt(q * dt)
    drift = sign * speed * dt
    position = float(start_world_x)
    positions = np.empty(frames, dtype=np.float64)
    for tick in range(frames):
        position = (position + drift) + float(noise[tick])
        if position < lane_min:
            position = lane_min
        elif position > lane_max:
            position = lane_max
        positions[tick] = position
    return np.asarray(positions, dtype="<f8"), np.asarray(noise, dtype="<f8")


def path_sha256(positions: Sequence[float]) -> str:
    return hashlib.sha256(np.asarray(positions, dtype="<f8").tobytes()).hexdigest()
