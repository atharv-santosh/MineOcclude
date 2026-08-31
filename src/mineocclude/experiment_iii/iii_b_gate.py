"""III-B launch gate, drop ladder and the absolute stop (authority 29.5-29.7).

Every decision here reads **time, technical stage receipts and resource
measurements only**. A scientific outcome offered to any evaluator is
**refused**, not ignored -- silently dropping it would let an outcome-driven
decision look identical to a compliant one in the receipt.

The gate evaluates at most twice: Wednesday 2026-09-02 at 12:00 local and, on a
NO-GO, once more at 17:00 the same day. There is no third reconsideration and no
Friday launch.
"""

from __future__ import annotations

import datetime as _dt
from typing import Any, Iterable, Mapping, Sequence

from mineocclude.experiment_iii.errors import ExperimentIIIError

__all__ = [
    "ABSOLUTE_EXPERIMENT_DEADLINE",
    "DROP_LEVELS",
    "GIB",
    "LAUNCH_GATE_EVALUATIONS",
    "LAUNCH_GATE_REQUIREMENTS",
    "POOL_DURABLE_FREE_GATE_BYTES",
    "POOL_WORKING_FREE_GATE_BYTES",
    "LaunchGate",
    "assert_absolute_stop",
    "assert_no_scientific_outcome_input",
    "select_drop_level",
]

GIB = 1 << 30
POOL_WORKING_FREE_GATE_BYTES = 15 * GIB
POOL_DURABLE_FREE_GATE_BYTES = 5 * GIB

LAUNCH_GATE_REQUIREMENTS = (
    "III_A_CAPTURE_TECHNICALLY_CLOSED_OR_SUFFICIENTLY_COMPLETE_UNDER_THE_A8_GATE",
    "III_A_ON_SCHEDULE_FOR_RESULT_LOCK",
    "POOL_WORKING_FREE_GE_15_GIB",
    "POOL_DURABLE_FREE_GE_5_GIB_ONLY_IF_POOL_DURABLE_IS_A_DISTINCT_LOCAL_FILESYSTEM",
    "III_B_TESTS_PASS",
    "III_B_PILOT_PASS",
    "NO_UNRESOLVED_SHARED_RIG_BLOCKER",
    "LAUNCHING_III_B_DOES_NOT_THREATEN_THE_III_A_RESULT_LOCK",
)

LAUNCH_GATE_EVALUATIONS = (
    _dt.datetime(2026, 9, 2, 12, 0),
    _dt.datetime(2026, 9, 2, 17, 0),
)

ABSOLUTE_EXPERIMENT_DEADLINE = _dt.datetime(2026, 9, 3, 20, 0)

DROP_LEVELS = {
    "NORMAL": {"q_set": (0.0125, 0.05, 0.2), "identities": 25, "new_captures": 50},
    "LEVEL_1": {"q_set": (0.05, 0.2), "identities": 25, "new_captures": 25},
    "LEVEL_2": {"q_set": (0.05, 0.2), "identities": 25, "new_captures": 25},
    "LEVEL_3": {"q_set": (0.0125, 0.05, 0.2), "identities": 15, "new_captures": 30},
    "LEVEL_4": {"q_set": (), "identities": 0, "new_captures": 0},
}

#: Any field whose presence proves an outcome reached an outcome-blind decision.
_SCIENTIFIC_OUTCOME_FIELDS = frozenset(
    {
        "u2_positive",
        "u2_result",
        "u3_result",
        "rho",
        "dbar",
        "delta",
        "p_value",
        "holm_adjusted_p_value",
        "effect_size",
        "sigma_hat",
        "decoder_accuracy",
        "scientific_outcome",
        "uncertainty_separation",
        "observed_performance",
    }
)


def assert_no_scientific_outcome_input(inputs: Mapping[str, Any]) -> None:
    """Refuse -- never ignore -- a scientific outcome offered to a gate."""
    offending = sorted(key for key in inputs if str(key).lower() in _SCIENTIFIC_OUTCOME_FIELDS)
    if offending:
        raise ExperimentIIIError(
            "B_Q_FALLBACK_OUTCOME_DRIVEN",
            f"the decision reads time, technical state and resources only; {offending} "
            "is a scientific outcome and is refused, not ignored",
        )


class LaunchGate:
    """The ``B-GATE`` evaluator. At most two evaluations, ever."""

    def __init__(self) -> None:
        self.evaluations: list[dict[str, Any]] = []

    def evaluate(self, *, now: _dt.datetime, **inputs: Any) -> dict[str, Any]:
        assert_no_scientific_outcome_input(inputs)
        if len(self.evaluations) >= len(LAUNCH_GATE_EVALUATIONS):
            raise ExperimentIIIError(
                "B_GATE_NOT_MET",
                "the launch gate evaluates at 12:00 and, on a NO-GO, once more at "
                "17:00; there is no third reconsideration",
            )
        expected = LAUNCH_GATE_EVALUATIONS[len(self.evaluations)]
        if now != expected:
            raise ExperimentIIIError(
                "B_GATE_NOT_MET",
                f"evaluation {len(self.evaluations) + 1} is frozen at {expected:%Y-%m-%d %H:%M}, got "
                f"{now:%Y-%m-%d %H:%M}",
            )
        if now.weekday() >= 4:
            raise ExperimentIIIError(
                "B_GATE_NOT_MET", "no Friday or weekend experiment launch is permitted"
            )

        durable_distinct = bool(inputs.get("pool_durable_is_distinct_local_filesystem"))
        results = {
            "III_A_CAPTURE_TECHNICALLY_CLOSED_OR_SUFFICIENTLY_COMPLETE_UNDER_THE_A8_GATE": bool(
                inputs.get("iii_a_capture_closed")
            ),
            "III_A_ON_SCHEDULE_FOR_RESULT_LOCK": bool(inputs.get("iii_a_on_schedule")),
            "POOL_WORKING_FREE_GE_15_GIB": int(inputs.get("pool_working_free_bytes", 0))
            >= POOL_WORKING_FREE_GATE_BYTES,
            "POOL_DURABLE_FREE_GE_5_GIB_ONLY_IF_POOL_DURABLE_IS_A_DISTINCT_LOCAL_FILESYSTEM": (
                int(inputs.get("pool_durable_free_bytes", 0)) >= POOL_DURABLE_FREE_GATE_BYTES
                if durable_distinct
                else True
            ),
            "III_B_TESTS_PASS": bool(inputs.get("iii_b_tests_pass")),
            "III_B_PILOT_PASS": bool(inputs.get("iii_b_pilot_pass")),
            "NO_UNRESOLVED_SHARED_RIG_BLOCKER": not inputs.get("shared_rig_blocker"),
            "LAUNCHING_III_B_DOES_NOT_THREATEN_THE_III_A_RESULT_LOCK": bool(
                inputs.get("does_not_threaten_iii_a_lock")
            ),
        }
        go = all(results.values())
        verdict = {
            "evaluation_index": len(self.evaluations) + 1,
            "evaluated_at": now.isoformat(),
            "requirements": list(LAUNCH_GATE_REQUIREMENTS),
            "requirement_count": len(LAUNCH_GATE_REQUIREMENTS),
            "results": results,
            "verdict": "GO" if go else "NO_GO",
            "pool_durable_requirement": "EVALUATED" if durable_distinct else "N/A",
            "decision_inputs": "TIME_TECHNICAL_STATE_AND_RESOURCES_ONLY",
            "scientific_outcome_consulted": False,
        }
        if not go and len(self.evaluations) + 1 == len(LAUNCH_GATE_EVALUATIONS):
            verdict["outcome"] = "CLEAN_SKIP"
            verdict["blocker"] = "B_GATE_NOT_MET"
        self.evaluations.append(verdict)
        return verdict

    def receipt(self) -> dict[str, Any]:
        return {
            "schema_version": "mineocclude-experiment-iii-b-launch-gate-v1",
            "evaluations": list(self.evaluations),
            "third_reconsideration_permitted": False,
            "friday_launch_permitted": False,
        }


def select_drop_level(
    *,
    now: _dt.datetime,
    complete_identity_triples: int,
    remaining_capture_hours: float,
    pool_working_free_bytes: int,
    identity_priority_order: Sequence[str] = (),
    **inputs: Any,
) -> dict[str, Any]:
    """Choose a drop level from time, technical completion and resources only."""
    assert_no_scientific_outcome_input(inputs)
    if now >= ABSOLUTE_EXPERIMENT_DEADLINE:
        level = "LEVEL_4"
        reason = "the absolute Thursday stop has passed; no new execution may begin"
    elif pool_working_free_bytes < POOL_WORKING_FREE_GATE_BYTES:
        level = "LEVEL_4"
        reason = "POOL_WORKING is below the frozen 15 GiB launch gate"
    elif remaining_capture_hours < 1.0:
        level = "LEVEL_4"
        reason = "no capture time remains before the absolute stop"
    elif remaining_capture_hours < 2.0:
        level = "LEVEL_2"
        reason = "time permits only the two-q fallback without the q_mid VIS re-inference"
    elif remaining_capture_hours < 3.0:
        level = "LEVEL_1"
        reason = "time permits the predeclared two-q U2 fallback only"
    elif complete_identity_triples < 25:
        level = "LEVEL_3"
        reason = "fewer than 25 complete identity q-triples are technically available"
    else:
        level = "NORMAL"
        reason = "time, technical completion and resources all permit the full plan"
    selected = dict(DROP_LEVELS[level])
    identities = selected["identities"]
    return {
        "schema_version": "mineocclude-experiment-iii-b-drop-level-v1",
        "level": level,
        "reason": reason,
        "selection_inputs": "TIME_TECHNICAL_COMPLETION_AND_RESOURCES_ONLY",
        "outcome_based_selection_allowed": False,
        "q_set": list(selected["q_set"]),
        "identities": identities,
        "new_captures": selected["new_captures"],
        "u2_family_size": 2 if level in {"LEVEL_1", "LEVEL_2"} else 3,
        "u2_s3_estimable": level not in {"LEVEL_1", "LEVEL_2"},
        "ordering": "identity_priority_order",
        "selected_identities": list(identity_priority_order[:identities]),
        "blocker": "B_DEADLINE_DROP" if level != "NORMAL" else None,
        "is_an_honourable_pre_registered_outcome": level == "LEVEL_4",
    }


def assert_absolute_stop(
    *, now: _dt.datetime, starting_new_scientific_execution: bool
) -> dict[str, Any]:
    """No new scientific execution may begin at or after the absolute deadline."""
    past = now >= ABSOLUTE_EXPERIMENT_DEADLINE
    if past and starting_new_scientific_execution:
        raise ExperimentIIIError(
            "B_DEADLINE_DROP",
            f"the absolute experiment deadline {ABSOLUTE_EXPERIMENT_DEADLINE:%Y-%m-%d %H:%M} "
            "has passed; no new scientific execution may begin, and no experiment "
            "work rolls into Friday",
        )
    return {
        "absolute_deadline": ABSOLUTE_EXPERIMENT_DEADLINE.isoformat(),
        "past_deadline": past,
        "friday_experiment_execution_planned": False,
        "iii_a_closure_delayed_for_iii_b": False,
    }
