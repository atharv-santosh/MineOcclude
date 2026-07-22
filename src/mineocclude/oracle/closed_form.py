"""Independent closed-form Regime A posterior implementation."""

from __future__ import annotations

from .schema import OracleValidationError, ScalarPosterior, require_finite_number


def closed_form_posterior(
    last_visible_position_blocks: float,
    v_blocks_per_second: float,
    q_blocks2_per_second: float,
    tau_seconds: float,
) -> ScalarPosterior:
    """Return the primary posterior ``mu=x_last+v*tau``, ``P=q*tau``.

    The authoritative visible state is exact, so ``P_last=0``. Hidden truth is
    deliberately absent from this function's signature.
    """

    x_last = require_finite_number(
        "last_visible_position_blocks",
        last_visible_position_blocks,
    )
    velocity = require_finite_number("v_blocks_per_second", v_blocks_per_second)
    process_noise = require_finite_number(
        "q_blocks2_per_second",
        q_blocks2_per_second,
    )
    tau = require_finite_number("tau_seconds", tau_seconds)
    if process_noise < 0:
        raise OracleValidationError("q cannot be negative.")
    if tau < 0:
        raise OracleValidationError("tau cannot be negative.")

    return ScalarPosterior(
        mean_blocks=x_last + velocity * tau,
        variance_blocks2=process_noise * tau,
    )
