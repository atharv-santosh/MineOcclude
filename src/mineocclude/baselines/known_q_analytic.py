"""Known-q analytic spread baseline (privileged oracle-ceiling reference).

Roadmap D2: "Known-q analytic spread | Condition q and tau under the
locked scalar oracle | Oracle/reference ceiling, not a fair learned
competitor."

This reproduces the primary Regime A oracle's own variance formula,
``variance(tau) = q*tau`` (docs/contracts/person_b_oracle_target_v0_1.md),
using the *true* scripted q. It is intentionally privileged and must
never be presented as competing on equal informational footing with a
real probe or with :mod:`mineocclude.baselines.visible_history_q` --
see Person B's B4.4: "the known-q reference is an oracle ceiling, not a
fair learned competitor." Its only legitimate use is as a sensitivity/
reference line, always labeled as such.
"""

from __future__ import annotations

import math
from typing import Sequence

from mineocclude.baselines.interface import BaselineRow, TrajectoryContext, make_baseline_row

BASELINE_NAME = "known_q_analytic"

#: Privileged oracle-ceiling reference, not a fair baseline. Any
#: comparison table built from these rows must carry this flag as-is.
IS_FAIR_BASELINE = False


def predict_known_q_analytic(contexts: Sequence[TrajectoryContext]) -> list[BaselineRow]:
    """Predict ``log_sigma_oracle = ln(sqrt(q_scripted * tau))``.

    Applicable only for hidden rows with a known scripted q and
    positive tau; defines no mean prediction. Reading
    ``q_scripted_blocks2_per_s`` here is intentional, not a leak --
    this baseline exists specifically to be the privileged reference
    ceiling that :func:`visible_history_q.fit_predict_visible_history_q`
    is compared against.
    """

    rows: list[BaselineRow] = []
    for ctx in contexts:
        q_scripted = ctx.q_scripted_blocks2_per_s
        applicable = (
            not ctx.visibility
            and q_scripted is not None
            and q_scripted > 0.0
            and ctx.tau_seconds > 0.0
        )
        prediction = (
            math.log(math.sqrt(q_scripted * ctx.tau_seconds)) if applicable else None
        )
        rows.append(
            make_baseline_row(
                ctx,
                baseline_name=BASELINE_NAME,
                target_name="log_sigma_oracle",
                prediction=prediction,
                applicable=applicable,
                fit_metadata=(
                    {
                        "q_scripted_blocks2_per_s": q_scripted,
                        "is_fair_baseline": False,
                    }
                    if applicable
                    else {
                        "is_fair_baseline": False,
                        "reason": (
                            "target is visible (no spread defined)"
                            if ctx.visibility
                            else "missing scripted q or non-positive tau"
                        ),
                    }
                ),
            )
        )
        rows.append(
            make_baseline_row(
                ctx,
                baseline_name=BASELINE_NAME,
                target_name="mu_oracle_blocks",
                prediction=None,
                applicable=False,
                fit_metadata={
                    "reason": "known-q analytic reference defines no mean prediction",
                    "is_fair_baseline": False,
                },
            )
        )
    return rows
