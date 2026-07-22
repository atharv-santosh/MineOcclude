"""Iterative float64-equivalent scalar Regime A Kalman prediction."""

from __future__ import annotations

from .schema import (
    REGIME_A_DT_SECONDS,
    OracleValidationError,
    ScalarPosterior,
    require_finite_number,
)


def scalar_kalman_posterior(
    last_visible_position_blocks: float,
    v_blocks_per_second: float,
    q_blocks2_per_second: float,
    hidden_ticks: int,
) -> ScalarPosterior:
    """Iteratively predict the scalar posterior for ``hidden_ticks``.

    The visible state is exact (R=0), the initial variance is zero, and the
    timestep is locked to 0.05 seconds. There is no hidden measurement update,
    and hidden truth is deliberately absent from the function signature.
    """

    if (
        not isinstance(hidden_ticks, int)
        or isinstance(hidden_ticks, bool)
        or hidden_ticks < 0
    ):
        raise OracleValidationError("hidden_ticks must be a non-negative integer.")

    mean = require_finite_number(
        "last_visible_position_blocks",
        last_visible_position_blocks,
    )
    velocity = require_finite_number("v_blocks_per_second", v_blocks_per_second)
    process_noise = require_finite_number(
        "q_blocks2_per_second",
        q_blocks2_per_second,
    )
    if process_noise < 0:
        raise OracleValidationError("q cannot be negative.")

    mean_step = velocity * REGIME_A_DT_SECONDS
    variance_step = process_noise * REGIME_A_DT_SECONDS
    variance = 0.0
    for _ in range(hidden_ticks):
        mean += mean_step
        variance += variance_step

    return ScalarPosterior(mean_blocks=mean, variance_blocks2=variance)
