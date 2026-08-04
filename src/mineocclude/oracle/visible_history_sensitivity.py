"""Separately labeled visible-history sensitivity for Regime A.

This is not the primary oracle. It estimates velocity and process variance from
authoritative visible positions only and never consumes hidden truth.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from .schema import OracleValidationError, ScalarPosterior


VISIBLE_HISTORY_METHOD = "visible_history_ols_velocity_residual_q_v0.1"


@dataclass(frozen=True)
class VisibleHistoryEstimate:
    velocity_blocks_per_second: float
    q_blocks2_per_second: float
    visible_sample_count: int
    method: str = VISIBLE_HISTORY_METHOD


def estimate_visible_history_motion(
    times_seconds: Sequence[float],
    positions_blocks: Sequence[float],
) -> VisibleHistoryEstimate:
    """Estimate linear velocity and innovation variance from visible rows."""

    if len(times_seconds) != len(positions_blocks) or len(times_seconds) < 3:
        raise OracleValidationError(
            "Visible-history sensitivity requires at least three aligned samples."
        )
    times: list[float] = []
    positions: list[float] = []
    for time, position in zip(times_seconds, positions_blocks):
        if (
            isinstance(time, bool)
            or isinstance(position, bool)
            or not isinstance(time, (int, float))
            or not isinstance(position, (int, float))
            or not math.isfinite(float(time))
            or not math.isfinite(float(position))
        ):
            raise OracleValidationError(
                "Visible-history times and positions must be finite numeric data."
            )
        times.append(float(time))
        positions.append(float(position))
    if any(right <= left for left, right in zip(times, times[1:])):
        raise OracleValidationError(
            "Visible-history times must be strictly increasing."
        )
    mean_time = sum(times) / len(times)
    mean_position = sum(positions) / len(positions)
    time_sum = sum((time - mean_time) ** 2 for time in times)
    if time_sum == 0.0:
        raise OracleValidationError("Visible-history time must vary.")
    velocity = sum(
        (time - mean_time) * (position - mean_position)
        for time, position in zip(times, positions)
    ) / time_sum
    innovations: list[float] = []
    elapsed: list[float] = []
    for left_index in range(len(times) - 1):
        delta_t = times[left_index + 1] - times[left_index]
        residual = (
            positions[left_index + 1]
            - positions[left_index]
            - velocity * delta_t
        )
        innovations.append(residual)
        elapsed.append(delta_t)
    q_estimates = [
        residual * residual / delta_t
        for residual, delta_t in zip(innovations, elapsed)
    ]
    q = sum(q_estimates) / len(q_estimates)
    return VisibleHistoryEstimate(
        velocity_blocks_per_second=velocity,
        q_blocks2_per_second=q,
        visible_sample_count=len(times),
    )


def visible_history_posterior(
    last_visible_position_blocks: float,
    tau_seconds: float,
    estimate: VisibleHistoryEstimate,
) -> ScalarPosterior:
    """Propagate the visible-history estimate without hidden observations."""

    if not isinstance(estimate, VisibleHistoryEstimate):
        raise OracleValidationError(
            "estimate must be a VisibleHistoryEstimate."
        )
    if (
        not math.isfinite(estimate.velocity_blocks_per_second)
        or not math.isfinite(estimate.q_blocks2_per_second)
        or estimate.q_blocks2_per_second < 0.0
        or not isinstance(estimate.visible_sample_count, int)
        or isinstance(estimate.visible_sample_count, bool)
        or estimate.visible_sample_count < 3
        or estimate.method != VISIBLE_HISTORY_METHOD
    ):
        raise OracleValidationError("Visible-history estimate is invalid.")
    for name, value in (
        ("last_visible_position_blocks", last_visible_position_blocks),
        ("tau_seconds", tau_seconds),
    ):
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
        ):
            raise OracleValidationError(f"{name} must be finite numeric data.")
    if tau_seconds < 0:
        raise OracleValidationError("tau_seconds cannot be negative.")
    return ScalarPosterior(
        mean_blocks=(
            float(last_visible_position_blocks)
            + estimate.velocity_blocks_per_second * float(tau_seconds)
        ),
        variance_blocks2=(
            estimate.q_blocks2_per_second * float(tau_seconds)
        ),
    )
