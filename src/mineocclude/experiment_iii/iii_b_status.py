"""III-B status surface, blockers and outcome vocabulary (authority 29.8-29.9).

Status is **observational**. ``III_A_STATUS`` is never a function of
``III_B_STATUS``: III-A closes identically whether III-B runs, skips, fails or is
dropped, and :func:`assert_iii_a_status_independent` refuses any coupling.

Three outcomes are strictly distinguished, and conflating them is the specific
reporting defect this module prevents:

``CLEAN_SKIP``
    III-B was never launched, or was dropped by the frozen time/resource ladder.
    An honourable pre-registered outcome. **Not** a failure.
``TECHNICAL_FAIL``
    Something broke. Repairable under the frozen repair policy. **Not** a result.
``SCIENTIFIC_NULL``
    A valid III-B measurement that did not support U2/U3. A publishable
    scientific result -- **never** a blocker, and never emitted as one.
"""

from __future__ import annotations

from typing import Any, Mapping

from mineocclude.experiment_iii.blockers import validate_blocker_code
from mineocclude.experiment_iii.errors import ExperimentIIIError
from mineocclude.experiment_iii.status import assert_observational_only

__all__ = [
    "III_B_BLOCKER_CODES",
    "III_B_LIFECYCLE_STATES",
    "OUTCOME_VOCABULARY",
    "assert_iii_a_status_independent",
    "assert_not_a_blocker",
    "iii_b_status_document",
    "validate_iii_b_status_document",
]

OUTCOME_VOCABULARY = {
    "CLEAN_SKIP": (
        "III-B was never launched or was dropped by the frozen time/resource "
        "ladder; an honourable pre-registered outcome, NOT a failure"
    ),
    "TECHNICAL_FAIL": (
        "something broke; repairable under the frozen repair policy; NOT a result"
    ),
    "SCIENTIFIC_NULL": (
        "a valid III-B measurement that did not support U2/U3; a publishable "
        "scientific result, NOT a blocker"
    ),
}

III_B_LIFECYCLE_STATES = (
    "B-GEN",
    "B-PILOT",
    "B-GATE",
    "B-CAP",
    "B-EXT",
    "B-ORC",
    "B-U2",
    "B-U3",
    "B-LOCK",
)

III_B_BLOCKER_CODES = (
    "B_ORACLE_MISMATCH",
    "B_Q_PAIRING_MISMATCH",
    "B_Q_HIGH_PILOT_FAIL",
    "B_Q_FALLBACK_OUTCOME_DRIVEN",
    "B_GATE_NOT_MET",
    "B_CAPTURE_ATTRITION",
    "B_VIS_UNAVAILABLE",
    "B_EXTRACTION_FAIL",
    "B_U2_ANALYSIS_FAIL",
    "B_U3_ANALYSIS_FAIL",
    "B_U2_FAMILY_ALTERED",
    "B_TAU_ALIGNMENT_ERROR",
    "B_CROSS_Q_FOLD_LEAKAGE",
    "B_DEADLINE_DROP",
    "B_III_A_DEPENDENCY_DETECTED",
)


def assert_not_a_blocker(outcome: str) -> None:
    """``SCIENTIFIC_NULL`` is a result. Emitting it as a blocker is refused."""
    if outcome == "SCIENTIFIC_NULL":
        raise ExperimentIIIError(
            "B_U2_ANALYSIS_FAIL",
            "SCIENTIFIC_NULL is a publishable measurement, never a blocker",
        )
    if outcome == "CLEAN_SKIP":
        raise ExperimentIIIError(
            "B_DEADLINE_DROP",
            "CLEAN_SKIP is a pre-registered honourable outcome, never a failure "
            "and never a blocker",
        )


def assert_iii_a_status_independent(document: Mapping[str, Any]) -> None:
    """``III_A_STATUS`` may not be derived from any III-B field."""
    derived_from = document.get("III_A_STATUS_DERIVED_FROM", ())
    offending = sorted(
        str(source)
        for source in derived_from
        if str(source).upper().startswith("III_B") or str(source).upper().startswith("B_")
    )
    if offending:
        raise ExperimentIIIError(
            "B_III_A_DEPENDENCY_DETECTED",
            f"III_A_STATUS must not be a function of {offending}; no III-B state is "
            "a prerequisite of any III-A state",
        )


def iii_b_status_document(
    *,
    iii_a_status: str,
    iii_b_status: str,
    iii_b_state: str | None = None,
    iii_b_blocker: str | None = None,
    completed_units: int = 0,
    remaining_units: int = 0,
    total_units: int = 0,
) -> dict[str, Any]:
    """The extended, observational-only status surface."""
    if iii_b_state is not None and iii_b_state not in III_B_LIFECYCLE_STATES:
        raise ExperimentIIIError(
            "B_GATE_NOT_MET", f"{iii_b_state!r} is not a III-B lifecycle state"
        )
    if iii_b_blocker is not None:
        validate_blocker_code(iii_b_blocker)
        if iii_b_blocker not in III_B_BLOCKER_CODES:
            raise ExperimentIIIError(
                "B_GATE_NOT_MET",
                f"{iii_b_blocker} is not one of the frozen III-B blocker codes",
            )
    if completed_units + remaining_units != total_units:
        raise ExperimentIIIError(
            "B_CAPTURE_ATTRITION",
            "COMPLETED_UNITS + REMAINING_UNITS must equal TOTAL_UNITS",
        )
    document = {
        "schema_version": "mineocclude-experiment-iii-b-status-v1",
        "III_A_STATUS": iii_a_status,
        "III_A_STATUS_DERIVED_FROM": ["III_A_STAGE_RECEIPTS"],
        "III_B_STATUS": iii_b_status,
        "III_B_STATE": iii_b_state,
        "III_B_BLOCKER": iii_b_blocker,
        "COMPLETED_UNITS": completed_units,
        "REMAINING_UNITS": remaining_units,
        "TOTAL_UNITS": total_units,
        "OBSERVATIONAL_ONLY": True,
    }
    validate_iii_b_status_document(document)
    return document


def validate_iii_b_status_document(document: Mapping[str, Any]) -> None:
    """Schema, taxonomy and independence checks for the emitted status document."""
    assert_observational_only(document)
    assert_iii_a_status_independent(document)
    blocker = document.get("III_B_BLOCKER")
    if blocker is not None and blocker not in III_B_BLOCKER_CODES:
        raise ExperimentIIIError(
            "B_GATE_NOT_MET", f"III_B_BLOCKER must be a taxonomy code or null, got {blocker!r}"
        )
    for field in ("COMPLETED_UNITS", "REMAINING_UNITS", "TOTAL_UNITS"):
        if field not in document:
            raise ExperimentIIIError(
                "B_CAPTURE_ATTRITION", f"the status document lacks {field}"
            )
