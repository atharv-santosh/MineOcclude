"""Deadline fallback plans and cohort attrition (authority 10, 8.x cohort closure).

Two outcome-blind decisions live here, and both are decisions the experiment
would be tempted to make on results if the rule were not frozen first.

**Plan selection** reads the clock and stage-receipt **status** only. Plans
escalate monotonically -- a later evaluation may move to a more reduced plan,
never back -- and once selected a plan is **frozen**. Reduced plans take the
first ``N`` identities by ``identity_priority_order``, never by observed
performance.

**Attrition** is a property of how many identities have all five conditions
complete. Below 15 the experiment closes with **no graded inferential claim** --
which is a valid closure, not a failure. In no branch is a missing cell imputed,
a condition dropped, or an identity replaced; a partial identity is excluded
whole.
"""

from __future__ import annotations

import datetime as _dt
from typing import Any, Mapping, Sequence

from mineocclude.experiment_iii.authority import machine_authority
from mineocclude.experiment_iii.errors import ExperimentIIIError

__all__ = [
    "ATTRITION_BRANCHES",
    "CLOCK_TRIGGERS",
    "PLAN_ORDER",
    "DeadlinePlanSelector",
    "attrition_branch",
    "plan_definition",
]

PLAN_ORDER = ("NORMAL", "ONE_DAY_BEHIND", "TWO_DAYS_BEHIND", "DISASTER")

CLOCK_TRIGGERS = {
    "TARGET_CAPTURE_LAUNCH": _dt.datetime(2026, 9, 1, 20, 0),
    "TARGET_RESULT_LOCK": _dt.datetime(2026, 9, 2, 23, 0),
}

ATTRITION_BRANCHES = {
    "NORMAL": {"minimum": 25, "graded_inferential_claim": True},
    "REDUCED_PRECISION": {"minimum": 15, "graded_inferential_claim": True},
    "NO_GRADED_CLAIM": {"minimum": 0, "graded_inferential_claim": False},
}

_SCIENTIFIC_OUTCOME_FIELDS = frozenset(
    {
        "effect_size",
        "p_value",
        "primary_estimand",
        "rmse",
        "observed_performance",
        "scientific_outcome",
        "condition_response",
        "decoder_accuracy",
    }
)


def _refuse_outcomes(inputs: Mapping[str, Any]) -> None:
    offending = sorted(
        key for key in inputs if str(key).lower() in _SCIENTIFIC_OUTCOME_FIELDS
    )
    if offending:
        raise ExperimentIIIError(
            "DEADLINE_OUTCOME_BASED_SELECTION",
            f"plan selection reads time and status only; {offending} is a "
            "scientific outcome and is refused",
        )


def plan_definition(plan: str) -> dict[str, Any]:
    """The frozen plan body, read from the machine authority."""
    plans = machine_authority()["deadline_fallbacks"]["plans"]
    if plan not in plans:
        raise ExperimentIIIError(
            "DEADLINE_OUTCOME_BASED_SELECTION", f"{plan!r} is not a frozen fallback plan"
        )
    return dict(plans[plan])


class DeadlinePlanSelector:
    """Selects a plan from time and status, once, then freezes it."""

    def __init__(self) -> None:
        self.selected: str | None = None
        self.evaluations: list[dict[str, Any]] = []

    def select(
        self,
        *,
        now: _dt.datetime,
        capture_launched: bool,
        a2_passed: bool,
        identity_priority_order: Sequence[str] = (),
        **inputs: Any,
    ) -> dict[str, Any]:
        _refuse_outcomes(inputs)
        if not a2_passed:
            plan = "DISASTER"
            reason = "A2 has not passed; no fresh confirmatory capture is producible"
        elif now < CLOCK_TRIGGERS["TARGET_CAPTURE_LAUNCH"]:
            plan = "NORMAL"
            reason = "before the target capture launch instant"
        elif not capture_launched and now >= CLOCK_TRIGGERS["TARGET_RESULT_LOCK"]:
            plan = "DISASTER"
            reason = "capture had not launched by the target result lock"
        elif not capture_launched:
            plan = "TWO_DAYS_BEHIND"
            reason = "the target capture launch instant passed with capture not launched"
        elif now >= CLOCK_TRIGGERS["TARGET_RESULT_LOCK"]:
            plan = "TWO_DAYS_BEHIND"
            reason = "the target result lock instant passed"
        else:
            plan = "ONE_DAY_BEHIND"
            reason = "capture launched after the target launch instant"

        # Plans escalate monotonically: a later evaluation may move only to a
        # MORE reduced plan, never back to a fuller one.
        if self.selected is not None:
            if PLAN_ORDER.index(plan) < PLAN_ORDER.index(self.selected):
                plan = self.selected
                reason = "plans escalate monotonically; the frozen plan is retained"

        body = plan_definition(plan)
        identities = int(body.get("identities", 0) or 0)
        verdict = {
            "plan": plan,
            "reason": reason,
            "evaluated_at": now.isoformat(),
            "selection_inputs": "TIME_AND_STATUS_ONLY",
            "outcome_based_selection_allowed": False,
            "frozen_once_selected": True,
            "identities": identities,
            "captures": body.get("captures"),
            "layers": body.get("layers"),
            "analyses": body.get("analyses"),
            "identity_selection": body.get(
                "identity_selection", "ALL_25_BY_IDENTITY_PRIORITY_ORDER"
            ),
            "selected_identities": list(identity_priority_order[:identities]),
        }
        self.selected = plan
        self.evaluations.append(verdict)
        return verdict

    def freeze(self) -> str:
        if self.selected is None:
            raise ExperimentIIIError(
                "DEADLINE_OUTCOME_BASED_SELECTION", "no plan has been selected yet"
            )
        return self.selected


def attrition_branch(
    n_complete: int, *, identity_priority_order: Sequence[str] = (), **inputs: Any
) -> dict[str, Any]:
    """The cohort-closure branch for ``n_complete`` five-way-complete identities."""
    _refuse_outcomes(inputs)
    closure = machine_authority()["cohort_closure"]
    normal = int(closure["normal_complete_identities"])
    minimum = int(closure["minimum_complete_identities_for_graded_inference"])
    low, high = closure["reduced_precision_band"]
    if not isinstance(n_complete, int) or isinstance(n_complete, bool) or n_complete < 0:
        raise ExperimentIIIError(
            "COHORT_MATRIX_INCONSISTENT", "N_complete must be a non-negative int"
        )
    if n_complete >= normal:
        branch = "NORMAL"
        claim = True
        disclosure = False
    elif low <= n_complete <= high:
        branch = "REDUCED_PRECISION"
        claim = True
        disclosure = True
    else:
        branch = "NO_GRADED_CLAIM"
        claim = False
        disclosure = True
    return {
        "schema_version": "mineocclude-experiment-iii-cohort-closure-receipt-v1",
        "n_complete": n_complete,
        "branch": branch,
        "graded_inferential_claim": claim,
        "attrition_disclosure_required": disclosure,
        "minimum_complete_identities_for_graded_inference": minimum,
        "reduced_precision_band": list(closure["reduced_precision_band"]),
        "missing_cell_imputation_allowed": False,
        "reactive_condition_drop_allowed": False,
        "outcome_based_identity_replacement_allowed": False,
        "partial_identities_excluded_whole": True,
        "primary_population": closure["primary_population"],
        "adjudication_row_if_no_claim": 16 if not claim else None,
        "is_a_valid_closure": True,
        "analysed_identities": list(identity_priority_order[:n_complete]),
    }
