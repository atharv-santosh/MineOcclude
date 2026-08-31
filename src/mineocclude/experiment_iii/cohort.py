"""Deterministic Experiment III path generation and candidate stream (authority 2.2).

The generator is **iterative binary64 with drift added before noise**, and both
properties are load-bearing to the bit:

* a vectorized ``start + cumsum(increments)`` is not bit-identical and is
  forbidden as the generator of record;
* ``(x + s*v*dt) + w`` and ``(x + w) + s*v*dt`` diverge by one ULP from tick 40
  and produce completely different path SHA-256 values. Only the drift-first
  order reproduces the frozen A-prime hash bound by test D.2.

:func:`generate_path` is **q-generalized** (task ``IB02``): each ``(identity, q)``
cell regenerates its own path from the identity seed with this identical
arithmetic. The standard-normal draws are shared across ``q`` — only the
``sqrt(q*dt)`` scale changes — which is what pairs the cells.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from typing import Sequence

import numpy as np

from mineocclude.experiment_iii.authority import (
    CANDIDATE_DOMAIN,
    DT_SECONDS,
    FRAMES_PER_CAPTURE,
    LANE_MAX,
    LANE_MIN,
    MOTION_NOISE_Q,
    SPEED_BLOCKS_PER_SECOND,
    START_POSITION_RNG_XOR,
    START_RANGE,
    derive_seed,
    direction_sign,
)
from mineocclude.experiment_iii.errors import ExperimentIIIError

__all__ = [
    "NoiseSchedule",
    "Candidate",
    "generate_noise_schedule",
    "generate_path",
    "generate_path_vectorized_forbidden",
    "generate_path_noise_first_forbidden",
    "candidate_start_world_x",
    "candidate_at",
    "candidate_stream",
    "path_sha256",
    "noise_sha256",
]


@dataclass(frozen=True)
class NoiseSchedule:
    """The per-tick innovation of one ``(seed, q)`` cell.

    ``standard_normal_draw`` is q-invariant at a fixed seed; ``noise_draw`` is
    that draw scaled by ``sqrt(q*dt)``. The ratio between any two ``q`` is
    therefore exactly ``sqrt(q_a/q_b)`` at every tick, which is the pairing the
    q-generalization relies on.
    """

    seed: int
    q: float
    dt: float
    standard_normal_draw: np.ndarray
    noise_draw: np.ndarray

    @property
    def rows(self) -> list["NoiseRow"]:
        return [
            NoiseRow(
                tick=tick,
                standard_normal_draw=float(self.standard_normal_draw[tick]),
                noise_draw=float(self.noise_draw[tick]),
            )
            for tick in range(len(self.noise_draw))
        ]


@dataclass(frozen=True)
class NoiseRow:
    tick: int
    standard_normal_draw: float
    noise_draw: float


def _validate_motion(q: float, speed: float, dt: float, frames: int) -> None:
    if not isinstance(frames, int) or isinstance(frames, bool) or frames < 1:
        raise ExperimentIIIError(
            "COHORT_MATRIX_INCONSISTENT", "frame count must be a positive int"
        )
    for name, value in (("q", q), ("speed", speed), ("dt", dt)):
        if not isinstance(value, float) or not math.isfinite(value) or value <= 0:
            raise ExperimentIIIError(
                "COHORT_MATRIX_INCONSISTENT", f"{name} must be a positive finite float"
            )
    if speed == 1.5:
        raise ExperimentIIIError(
            "COHORT_SPEED_VIOLATION",
            "speed 1.5 is the superseded implementation-base default of the "
            "original executable lineage; Experiment III is speed 2.0",
        )


def generate_noise_schedule(
    seed: int,
    frames: int = FRAMES_PER_CAPTURE,
    q: float = MOTION_NOISE_Q,
    dt: float = DT_SECONDS,
) -> NoiseSchedule:
    """``default_rng(noise_seed).standard_normal(frames) * sqrt(q*dt)``."""
    _validate_motion(q, SPEED_BLOCKS_PER_SECOND, dt, frames)
    draws = np.random.default_rng(seed).standard_normal(frames)
    return NoiseSchedule(
        seed=int(seed),
        q=float(q),
        dt=float(dt),
        standard_normal_draw=draws,
        noise_draw=draws * math.sqrt(q * dt),
    )


def generate_path(
    identity_seed: int,
    q: float = MOTION_NOISE_Q,
    *,
    direction: str,
    start_world_x: float,
    speed: float = SPEED_BLOCKS_PER_SECOND,
    dt: float = DT_SECONDS,
    frames: int = FRAMES_PER_CAPTURE,
    lane_min: float = LANE_MIN,
    lane_max: float = LANE_MAX,
) -> tuple[np.ndarray, np.ndarray]:
    """The frozen iterative recurrence, for arbitrary ``q``.

    ``x[t] = clamp( (x[t-1] + signed_speed*dt) + noise[t] )``

    Returns ``(positions, noise)`` as little-endian float64 arrays, so the
    manifest hashes are byte-defined regardless of host endianness.
    """
    _validate_motion(q, speed, dt, frames)
    if not math.isfinite(start_world_x):
        raise ExperimentIIIError(
            "COHORT_MATRIX_INCONSISTENT", "start position must be finite"
        )
    schedule = generate_noise_schedule(identity_seed, frames, q, dt)
    noise = schedule.noise_draw
    drift = direction_sign(direction) * speed * dt
    position = float(start_world_x)
    positions = np.empty(frames, dtype=np.float64)
    for tick in range(frames):
        # Drift FIRST, then noise. Binary64 addition is not associative and the
        # other order changes every downstream path hash.
        position = (position + drift) + float(noise[tick])
        if position < lane_min:
            position = lane_min
        elif position > lane_max:
            position = lane_max
        positions[tick] = position
    if not np.isfinite(positions).all():
        raise ExperimentIIIError(
            "COHORT_QUALIFICATION_INFEASIBLE", "generated path is not finite"
        )
    return np.asarray(positions, dtype="<f8"), np.asarray(noise, dtype="<f8")


def generate_path_vectorized_forbidden(
    identity_seed: int,
    q: float = MOTION_NOISE_Q,
    *,
    direction: str,
    start_world_x: float,
    speed: float = SPEED_BLOCKS_PER_SECOND,
    dt: float = DT_SECONDS,
    frames: int = FRAMES_PER_CAPTURE,
) -> np.ndarray:
    """The forbidden vectorized substitution, for the A.3 negative control only.

    Present so the regression fixture can prove the two hashes differ. Never call
    this from a production path.
    """
    schedule = generate_noise_schedule(identity_seed, frames, q, dt)
    increments = direction_sign(direction) * speed * dt + schedule.noise_draw
    positions = float(start_world_x) + np.cumsum(increments)
    return np.asarray(np.clip(positions, LANE_MIN, LANE_MAX), dtype="<f8")


def generate_path_noise_first_forbidden(
    identity_seed: int,
    q: float = MOTION_NOISE_Q,
    *,
    direction: str,
    start_world_x: float,
    speed: float = SPEED_BLOCKS_PER_SECOND,
    dt: float = DT_SECONDS,
    frames: int = FRAMES_PER_CAPTURE,
) -> np.ndarray:
    """The forbidden ``(x + noise) + drift`` order, for the D.2 negative control."""
    schedule = generate_noise_schedule(identity_seed, frames, q, dt)
    noise = schedule.noise_draw
    drift = direction_sign(direction) * speed * dt
    position = float(start_world_x)
    positions = np.empty(frames, dtype=np.float64)
    for tick in range(frames):
        position = (position + float(noise[tick])) + drift
        position = min(LANE_MAX, max(LANE_MIN, position))
        positions[tick] = position
    return np.asarray(positions, dtype="<f8")


def path_sha256(positions: Sequence[float]) -> str:
    return hashlib.sha256(np.asarray(positions, dtype="<f8").tobytes()).hexdigest()


def noise_sha256(noise: Sequence[float]) -> str:
    return hashlib.sha256(np.asarray(noise, dtype="<f8").tobytes()).hexdigest()


# --------------------------------------------------------------------------
# The candidate stream (authority 2.2, 2.3)
# --------------------------------------------------------------------------

def candidate_start_world_x(seed: int, direction: str) -> float:
    """``default_rng(seed ^ 0xE3E3E3E3).uniform(*start_range)``."""
    low, high = START_RANGE[direction]
    return float(np.random.default_rng(seed ^ START_POSITION_RNG_XOR).uniform(low, high))


@dataclass(frozen=True)
class Candidate:
    """One deterministic candidate, before any qualification gate is applied."""

    direction: str
    index: int
    seed: int
    start_world_x: float

    @property
    def noise_seed(self) -> int:
        """Authority 2.2: the noise seed equals the identity seed."""
        return self.seed

    def path(self, q: float = MOTION_NOISE_Q) -> tuple[np.ndarray, np.ndarray]:
        """This cell's OWN path, regenerated at ``q`` from the identity seed."""
        return generate_path(
            self.seed,
            q,
            direction=self.direction,
            start_world_x=self.start_world_x,
        )


def candidate_at(direction: str, index: int) -> Candidate:
    if direction not in CANDIDATE_DOMAIN:
        raise ExperimentIIIError(
            "COHORT_MATRIX_INCONSISTENT", f"unknown direction {direction!r}"
        )
    seed = derive_seed(CANDIDATE_DOMAIN[direction], index)
    return Candidate(
        direction=direction,
        index=index,
        seed=seed,
        start_world_x=candidate_start_world_x(seed, direction),
    )


def candidate_stream(direction: str, bound: int):
    """Candidates in strictly ascending index, to the frozen bound."""
    for index in range(bound):
        yield candidate_at(direction, index)
