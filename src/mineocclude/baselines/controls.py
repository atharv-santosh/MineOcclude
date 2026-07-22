"""No-wall visible and occluder-only control checks (Person D).

Roadmap C1 / D2 / D3: the no-wall condition removes the wall so the
target Regime A sheep is visible for the entire trajectory (a positive
measurement gate -- baseline/probe machinery must work on the easiest
possible case before being trusted anywhere harder); the occluder-only
condition keeps the wall but removes the sheep entirely (a negative
condition-cue control -- nothing about the scene should let any
position-based prediction succeed, since there is no position to
predict).

These are not new prediction algorithms. Every existing baseline in
this package already runs on any ``TrajectoryContext`` sequence --
these functions only audit that the control data and the baselines'
behavior on it satisfy the two invariants the controls exist to test.
A failed audit is a control failure and must be reported, never
silently dropped (roadmap D3.4: "Retain control failures... must
change the claim").
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from mineocclude.baselines.interface import BaselineRow, TrajectoryContext


@dataclass(frozen=True)
class ControlAuditFinding:
    control_name: str
    passed: bool
    detail: str


def audit_no_wall_control(contexts: Sequence[TrajectoryContext]) -> ControlAuditFinding:
    """Verify every no-wall-visible frame is actually always visible.

    A no-wall trajectory has no occlusion period by construction: if
    any frame here reports ``visibility=False`` or ``tau>0``, the
    control data itself is broken (a Person C data-quality issue, not
    something D should repair), and D's job is to surface that rather
    than silently run baselines against an invalid control.
    """

    if not contexts:
        return ControlAuditFinding(
            "no_wall_visible", False, "no contexts supplied for the no-wall control"
        )
    bad = [ctx for ctx in contexts if not ctx.visibility or ctx.tau_seconds != 0.0]
    if bad:
        return ControlAuditFinding(
            "no_wall_visible",
            False,
            f"{len(bad)} of {len(contexts)} frames report an occluded/hidden "
            "state in a no-wall trajectory; recollect under Person C's review "
            "rather than repairing here",
        )
    return ControlAuditFinding(
        "no_wall_visible",
        True,
        f"all {len(contexts)} frames are visible with tau=0",
    )


def audit_occluder_only_control(
    contexts: Sequence[TrajectoryContext],
    baseline_rows: Sequence[BaselineRow],
) -> ControlAuditFinding:
    """Verify the occluder-only condition carries no exploitable position cue.

    Checks two things: (1) every context's ``last_seen_position_blocks``
    is ``None`` (there is genuinely no sheep to have seen), and (2)
    every supplied baseline row produced against these contexts is
    ``applicable=False``. A baseline that claims applicability here
    despite no object ever being visible would mean condition/metadata
    leakage into that baseline's logic, not a real signal.
    """

    if not contexts:
        return ControlAuditFinding(
            "occluder_only",
            False,
            "no contexts supplied for the occluder-only control",
        )
    ever_seen = [ctx for ctx in contexts if ctx.last_seen_position_blocks is not None]
    if ever_seen:
        return ControlAuditFinding(
            "occluder_only",
            False,
            f"{len(ever_seen)} of {len(contexts)} occluder-only frames carry a "
            "non-null last_seen_position_blocks; the control data itself is "
            "contaminated",
        )

    leaked_rows = [row for row in baseline_rows if row.applicable]
    if leaked_rows:
        offenders = sorted({row.baseline_name for row in leaked_rows})
        return ControlAuditFinding(
            "occluder_only",
            False,
            f"{len(leaked_rows)} rows from {offenders} were marked applicable "
            "on occluder-only (no-object) frames -- this is a control "
            "failure, not a positive result, and must be reported as such",
        )
    return ControlAuditFinding(
        "occluder_only",
        True,
        f"all {len(contexts)} frames carry no position and every baseline "
        "row correctly reports not applicable",
    )
