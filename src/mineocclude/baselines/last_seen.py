"""Last-seen-position baseline (memory heuristic, no spread claim).

Roadmap D2: "Last seen | Final visible wall-parallel position | Simple
memory heuristic; no spread prediction."
"""

from __future__ import annotations

from typing import Sequence

from mineocclude.baselines.interface import BaselineRow, TrajectoryContext, make_baseline_row

BASELINE_NAME = "last_seen"


def predict_last_seen(contexts: Sequence[TrajectoryContext]) -> list[BaselineRow]:
    """Predict the hidden position as exactly the last visible position.

    No extrapolation, no velocity, no spread. A row is only applicable
    when the target has been seen at least once.
    """

    rows: list[BaselineRow] = []
    for ctx in contexts:
        position = ctx.last_seen_position_blocks
        applicable = position is not None
        rows.append(
            make_baseline_row(
                ctx,
                baseline_name=BASELINE_NAME,
                target_name="mu_oracle_blocks",
                prediction=position if applicable else None,
                applicable=applicable,
                fit_metadata={} if applicable else {"reason": "target not yet seen"},
            )
        )
        rows.append(
            make_baseline_row(
                ctx,
                baseline_name=BASELINE_NAME,
                target_name="log_sigma_oracle",
                prediction=None,
                applicable=False,
                fit_metadata={"reason": "memory heuristic defines no spread prediction"},
            )
        )
    return rows
