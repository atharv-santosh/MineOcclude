"""Constant-velocity extrapolation baseline.

Roadmap D2: "Constant velocity | Visible-window position/speed |
Reference in Regime A; genuine baseline in Regime B."

Regime A note (proposal Methods): because the scripted motion law is a
known drift ``v``, constant-velocity extrapolation with the *true* v
equals the oracle mean there -- so in Regime A this baseline is a
reference, not a competitor. This module never touches
``v_scripted_blocks_per_s``; it only extrapolates from the
visible-window *estimated* velocity, exactly as the roadmap specifies,
so the same code is a fair, non-privileged baseline in both regimes.
Whether a given trajectory's result should be read as "reference" or
"baseline" is a labeling decision for the analysis layer (Person B),
not something this module decides.
"""

from __future__ import annotations

from typing import Sequence

from mineocclude.baselines.interface import BaselineRow, TrajectoryContext, make_baseline_row

BASELINE_NAME = "constant_velocity"


def predict_constant_velocity(contexts: Sequence[TrajectoryContext]) -> list[BaselineRow]:
    """Predict mu = last_seen_position + last_seen_velocity * tau.

    Applicable only when both the last-seen position and an estimated
    visible-window velocity are available. Defines no spread
    prediction (see module docstring / D2 table).
    """

    rows: list[BaselineRow] = []
    for ctx in contexts:
        position = ctx.last_seen_position_blocks
        velocity = ctx.last_seen_velocity_blocks_per_s
        applicable = position is not None and velocity is not None
        prediction = position + velocity * ctx.tau_seconds if applicable else None
        rows.append(
            make_baseline_row(
                ctx,
                baseline_name=BASELINE_NAME,
                target_name="mu_oracle_blocks",
                prediction=prediction,
                applicable=applicable,
                fit_metadata=(
                    {}
                    if applicable
                    else {"reason": "missing last-seen position or estimated velocity"}
                ),
            )
        )
        rows.append(
            make_baseline_row(
                ctx,
                baseline_name=BASELINE_NAME,
                target_name="log_sigma_oracle",
                prediction=None,
                applicable=False,
                fit_metadata={"reason": "constant-velocity baseline defines no spread"},
            )
        )
    return rows
