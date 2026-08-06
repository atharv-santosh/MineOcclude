"""Generate the MVP implementation closeout memo and artifact index (Step 7.8).

The closeout must make the critical path, shortfalls, capacity, and U4
prerequisites explicit. It reports gate state without interpreting metrics, and
it never reports a real-data step as complete on synthetic evidence.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any

CLOSEOUT_SCHEMA_VERSION = "person-a-mvp-implementation-closeout-v0.1"


class GateState(str, Enum):
    """The only states an engineering gate may report."""

    PASS = "pass"
    FAIL = "fail"
    BLOCKED = "blocked"
    NOT_EVIDENCED = "not_evidenced"


class U4Readiness(str, Enum):
    """How Step 7.8 hands the U4 decision to the team."""

    SCIENTIFIC = "scientific"
    PLUMBING_ONLY = "plumbing_only"
    BLOCKED = "blocked"


class CloseoutErrorCode(str, Enum):
    INVALID_REQUEST = "invalid_request"
    SYNTHETIC_AS_REAL = "synthetic_as_real"


class CloseoutError(ValueError):
    """Raised when a closeout would overstate what was actually produced."""

    def __init__(self, code: CloseoutErrorCode, message: str) -> None:
        self.code = code
        super().__init__(f"{code.value}: {message}")


def _fail(code: CloseoutErrorCode, message: str) -> None:
    raise CloseoutError(code, message)


@dataclass(frozen=True)
class Gate:
    """One named engineering gate with its evidence pointer."""

    gate_id: str
    state: GateState
    evidence: str
    detail: str | None = None

    def to_document(self) -> dict[str, Any]:
        return {
            "gate_id": self.gate_id,
            "state": self.state.value,
            "evidence": self.evidence,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class ArtifactIndexEntry:
    """One immutable artifact the closeout points at."""

    artifact_id: str
    artifact_type: str
    uri: str
    sha256: str
    owner: str
    real: bool

    def to_document(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "artifact_type": self.artifact_type,
            "uri": self.uri,
            "sha256": self.sha256,
            "owner": self.owner,
            "real": self.real,
        }


def build_mvp_closeout(
    *,
    identity: Mapping[str, Any],
    matrix_report: Mapping[str, Any],
    queue_status: Mapping[str, Any],
    cardinality_report: Mapping[str, Any],
    gates: Sequence[Gate],
    artifact_index: Sequence[ArtifactIndexEntry],
    capacity: Mapping[str, Any],
    superseded_runs: Sequence[Mapping[str, Any]] = (),
    u1_u3_invocation: Mapping[str, Any] | None = None,
    person_b_typical_norm_path_confirmed: bool = False,
    person_e_rollout_schema_confirmed: bool = False,
    real_extraction_executed: bool = False,
    external_blockers: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Publish the Step 7.8 memo with an honest completeness statement."""

    if not gates:
        _fail(
            CloseoutErrorCode.INVALID_REQUEST,
            "the closeout must report at least one gate",
        )
    synthetic_artifacts = [entry for entry in artifact_index if not entry.real]
    if real_extraction_executed and not any(entry.real for entry in artifact_index):
        _fail(
            CloseoutErrorCode.SYNTHETIC_AS_REAL,
            "a real extraction cannot be claimed with only synthetic artifacts",
        )

    accepted = int(matrix_report.get("accepted_cell_count", 0))
    expected = int(matrix_report.get("expected_cell_count", 0))
    completed_items = int(cardinality_report.get("completed_item_count", 0))
    queue_complete = bool(cardinality_report.get("complete"))
    failing = [gate for gate in gates if gate.state is GateState.FAIL]
    blocked = [
        gate
        for gate in gates
        if gate.state in {GateState.BLOCKED, GateState.NOT_EVIDENCED}
    ]

    if failing:
        u4_readiness = U4Readiness.BLOCKED
        u4_reason = "one or more engineering gates failed"
    elif not queue_complete or accepted < expected:
        u4_readiness = U4Readiness.BLOCKED
        u4_reason = (
            f"the MVP activation dataset is incomplete: {completed_items} of "
            f"{expected} expected cells have completed extraction"
        )
    elif not (
        person_b_typical_norm_path_confirmed and person_e_rollout_schema_confirmed
    ):
        u4_readiness = U4Readiness.BLOCKED
        u4_reason = (
            "U4 requires Person B's typical activation norm measurement path and "
            "Person E's rollout schema to be confirmed"
        )
    elif not real_extraction_executed:
        u4_readiness = U4Readiness.PLUMBING_ONLY
        u4_reason = "no real extraction has been executed for this run identity"
    else:
        u4_readiness = U4Readiness.SCIENTIFIC
        u4_reason = "engineering gates pass and the accepted dataset is complete"

    return {
        "schema_version": CLOSEOUT_SCHEMA_VERSION,
        "step": "7.8",
        "identity": dict(identity),
        "queue_completeness": {
            "expected_cell_count": expected,
            "accepted_cell_count": accepted,
            "queued_item_count": int(cardinality_report.get("queued_item_count", 0)),
            "completed_item_count": completed_items,
            "complete": queue_complete,
            "shortfall_count": int(matrix_report.get("shortfall_count", 0)),
            "shortfall_owners": list(matrix_report.get("shortfall_owners", ())),
            "visibly_short": not queue_complete,
        },
        "gates": [gate.to_document() for gate in gates],
        "gate_state_counts": {
            state.value: sum(1 for gate in gates if gate.state is state)
            for state in GateState
        },
        "failing_gate_ids": [gate.gate_id for gate in failing],
        "blocked_gate_ids": [gate.gate_id for gate in blocked],
        "capacity": dict(capacity),
        "queue_forecast": dict(queue_status.get("forecast", {})),
        "superseded_runs": [dict(entry) for entry in superseded_runs],
        "affected_downstream_outputs": sorted(
            {
                str(name)
                for entry in superseded_runs
                for name in entry.get("affected_outputs", ())
            }
        ),
        "u1_u3_invocation": dict(u1_u3_invocation) if u1_u3_invocation else None,
        "u4_prerequisites": {
            "person_b_typical_activation_norm_path_confirmed": (
                person_b_typical_norm_path_confirmed
            ),
            "person_e_rollout_schema_confirmed": person_e_rollout_schema_confirmed,
        },
        "u4_readiness": u4_readiness.value,
        "u4_readiness_reason": u4_reason,
        "artifact_index": [entry.to_document() for entry in artifact_index],
        "artifact_count": len(artifact_index),
        "synthetic_artifact_count": len(synthetic_artifacts),
        "real_extraction_executed": bool(real_extraction_executed),
        "real_data_steps_claimed_from_synthetic_evidence": False,
        "external_blockers": [dict(entry) for entry in external_blockers],
        "metrics_interpreted": False,
        "status": (
            "IMPLEMENTATION_COMPLETE_EXECUTION_BLOCKED"
            if external_blockers and not failing
            else ("IMPLEMENTATION_COMPLETE" if not failing else "BLOCKED")
        ),
    }


__all__ = [
    "CLOSEOUT_SCHEMA_VERSION",
    "ArtifactIndexEntry",
    "CloseoutError",
    "CloseoutErrorCode",
    "Gate",
    "GateState",
    "U4Readiness",
    "build_mvp_closeout",
]
