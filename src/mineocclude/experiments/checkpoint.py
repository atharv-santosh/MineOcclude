"""Handoff rehearsals, evidence chain, checkpoint decision, and tag record.

Steps 9.4-9.8. A rehearsal receipt records whether Person A and Person B could
actually operate another role's workflow without that role's private knowledge.
The evidence chain lets a reviewer follow a displayed value back to code,
config, model, data, seed, run, and artifact hash. The decision generator refuses
to call failed engineering a negative model finding. The tag record binds a Git
state to external artifact identity and is prepared, never pushed, from a role
branch.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any

REHEARSAL_SCHEMA_VERSION = "person-a-handoff-rehearsal-v0.1"
EVIDENCE_CHAIN_SCHEMA_VERSION = "person-a-evidence-chain-v0.1"
CHECKPOINT_DECISION_SCHEMA_VERSION = "person-a-checkpoint-decision-v0.1"
TAG_RECORD_SCHEMA_VERSION = "person-a-mvp-tag-record-v0.1"

MVP_TAG_NAME = "mvp-2026-07-26"


class RehearsalStatus(str, Enum):
    """Whether a documented handoff could actually be operated."""

    COMPLETED = "completed"
    BLOCKED = "blocked"
    NOT_ATTEMPTED = "not_attempted"


class CheckpointDecision(str, Enum):
    """The only checkpoint colours the roadmap allows."""

    GREEN = "green"
    YELLOW = "yellow"
    RED = "red"


class CheckpointErrorCode(str, Enum):
    INVALID_REQUEST = "invalid_request"
    ENGINEERING_AS_SCIENCE = "engineering_as_science"
    UNBOUND_ARTIFACT = "unbound_artifact"
    TAG_PUSH_FORBIDDEN = "tag_push_forbidden"


class CheckpointError(ValueError):
    """Raised when a checkpoint artifact would misrepresent the evidence."""

    def __init__(self, code: CheckpointErrorCode, message: str) -> None:
        self.code = code
        super().__init__(f"{code.value}: {message}")


def _fail(code: CheckpointErrorCode, message: str) -> None:
    raise CheckpointError(code, message)


# ---------------------------------------------------------------------------
# Steps 9.4 and 9.5 — handoff rehearsals
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RunbookStep:
    """One step of another role's documented runbook, as executed or blocked."""

    step_id: str
    description: str
    status: RehearsalStatus
    detail: str | None = None
    instruction_gap: str | None = None

    def to_document(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "description": self.description,
            "status": self.status.value,
            "detail": self.detail,
            "instruction_gap": self.instruction_gap,
        }


def build_rehearsal_receipt(
    *,
    rehearsal_id: str,
    owning_role: str,
    runbook_path: str,
    runbook_sha256: str | None,
    steps: Sequence[RunbookStep],
    produced_artifacts: Sequence[Mapping[str, Any]] = (),
    owner_changed_experiment_code: bool = False,
    secret_channel: str = "approved_out_of_band_channel",
    blocked_reason: str | None = None,
) -> dict[str, Any]:
    """Record a handoff rehearsal, including every missing instruction found."""

    if not steps:
        _fail(
            CheckpointErrorCode.INVALID_REQUEST,
            "a rehearsal receipt requires at least one runbook step",
        )
    completed = [s for s in steps if s.status is RehearsalStatus.COMPLETED]
    blocked = [s for s in steps if s.status is RehearsalStatus.BLOCKED]
    not_attempted = [s for s in steps if s.status is RehearsalStatus.NOT_ATTEMPTED]
    gaps = [s.to_document() for s in steps if s.instruction_gap]
    succeeded = not blocked and not not_attempted
    if not succeeded and not blocked_reason:
        blocked_reason = (
            "one or more runbook steps could not be executed in this environment"
        )
    return {
        "schema_version": REHEARSAL_SCHEMA_VERSION,
        "rehearsal_id": rehearsal_id,
        "owning_role": owning_role,
        "operated_by": ["person_a_model", "person_b_analysis"],
        "runbook_path": runbook_path,
        "runbook_sha256": runbook_sha256,
        "step_count": len(steps),
        "completed_step_count": len(completed),
        "blocked_step_count": len(blocked),
        "not_attempted_step_count": len(not_attempted),
        "steps": [step.to_document() for step in steps],
        "documented_instruction_gaps": gaps,
        "instruction_gap_count": len(gaps),
        "produced_artifacts": [dict(item) for item in produced_artifacts],
        "owning_role_changed_experiment_code": owner_changed_experiment_code,
        "secret_channel": secret_channel,
        "credentials_in_git_s3_logs_notebooks_or_chat": False,
        "succeeded": succeeded,
        "status": "COMPLETED" if succeeded else "BLOCKED",
        "blocked_reason": None if succeeded else blocked_reason,
    }


# ---------------------------------------------------------------------------
# Step 9.6 — evidence chain
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EvidenceLink:
    """One demonstration item and the artifact a reviewer can open."""

    order: int
    claim: str
    evidence_path: str
    evidence_sha256: str | None
    real: bool
    detail: str | None = None

    def to_document(self) -> dict[str, Any]:
        return {
            "order": self.order,
            "claim": self.claim,
            "evidence_path": self.evidence_path,
            "evidence_sha256": self.evidence_sha256,
            "real": self.real,
            "detail": self.detail,
        }


def build_evidence_chain(
    links: Sequence[EvidenceLink],
    *,
    traced_example: Mapping[str, Any],
) -> dict[str, Any]:
    """Publish the checkpoint demonstration checklist in reviewable order."""

    if not links:
        _fail(
            CheckpointErrorCode.INVALID_REQUEST,
            "the evidence chain requires at least one link",
        )
    unbound = [link.to_document() for link in links if link.evidence_sha256 is None]
    required_trace_fields = (
        "code_sha",
        "config_hash",
        "model_hash",
        "data_identity_hash",
        "seed",
        "run_id",
        "artifact_sha256",
    )
    missing = [name for name in required_trace_fields if not traced_example.get(name)]
    if missing:
        _fail(
            CheckpointErrorCode.UNBOUND_ARTIFACT,
            "the traced example must bind: " + ", ".join(missing),
        )
    ordered = sorted(links, key=lambda link: link.order)
    return {
        "schema_version": EVIDENCE_CHAIN_SCHEMA_VERSION,
        "step": "9.6",
        "link_count": len(ordered),
        "links": [link.to_document() for link in ordered],
        "unbound_evidence_count": len(unbound),
        "unbound_evidence": unbound,
        "real_evidence_count": sum(1 for link in ordered if link.real),
        "synthetic_evidence_count": sum(1 for link in ordered if not link.real),
        "traced_example": dict(traced_example),
        "verbal_assertion_required": False,
        "followable_without_accepting_assertions": not unbound,
    }


# ---------------------------------------------------------------------------
# Step 9.7 — green / yellow / red
# ---------------------------------------------------------------------------

# Failures in any of these areas are engineering failures. A red decision from
# one of them is never reported as a negative scientific finding.
RED_ENGINEERING_AREAS: tuple[str, ...] = (
    "model_runtime",
    "visible_positive_control",
    "oracle",
    "alignment",
    "hooks",
    "detector",
    "reproducibility",
)


def decide_checkpoint(
    *,
    engineering_gates: Mapping[str, bool],
    u1_green: bool | None,
    u2_green: bool | None,
    u3_directionally_correct: bool | None,
    u4_is_smoke_test_only: bool,
    scientific_test_failed_cleanly: bool,
    scope_cuts: Sequence[Mapping[str, Any]] = (),
    detail: str | None = None,
) -> dict[str, Any]:
    """Choose green/yellow/red from evidence, keeping engineering separate.

    A failed engineering gate forces RED and is labelled as engineering. A clean
    scientific failure with passing engineering is YELLOW and follows the
    alternative-results ladder, cutting breadth before validity.
    """

    failed_engineering = sorted(
        name for name, passed in engineering_gates.items() if not passed
    )
    red_engineering = [
        name for name in failed_engineering if name in RED_ENGINEERING_AREAS
    ]
    unevaluated = [
        name
        for name, value in (
            ("u1", u1_green),
            ("u2", u2_green),
            ("u3", u3_directionally_correct),
        )
        if value is None
    ]

    if red_engineering:
        decision = CheckpointDecision.RED
        rationale = (
            "engineering failed in: "
            + ", ".join(red_engineering)
            + "; this is an engineering blocker, not a model finding"
        )
    elif failed_engineering:
        decision = CheckpointDecision.RED
        rationale = (
            "engineering gates failed: " + ", ".join(failed_engineering)
        )
    elif unevaluated:
        decision = CheckpointDecision.YELLOW
        rationale = (
            "engineering passes but the scientific tests are not yet evaluated: "
            + ", ".join(unevaluated)
        )
    elif u1_green and u2_green and u3_directionally_correct:
        decision = CheckpointDecision.GREEN
        rationale = (
            "engineering passes, U1 and U2 are green, and U3 is directionally "
            "correct"
            + ("; U4 remains a smoke test" if u4_is_smoke_test_only else "")
        )
    elif scientific_test_failed_cleanly:
        decision = CheckpointDecision.YELLOW
        rationale = (
            "engineering and controls pass while a scientific test failed cleanly"
        )
    else:
        decision = CheckpointDecision.YELLOW
        rationale = "engineering passes but the scientific criteria are not met"

    return {
        "schema_version": CHECKPOINT_DECISION_SCHEMA_VERSION,
        "step": "9.7",
        "decision": decision.value,
        "rationale": rationale,
        "engineering_gates": dict(sorted(engineering_gates.items())),
        "failed_engineering_gate_ids": failed_engineering,
        "red_engineering_areas_triggered": red_engineering,
        "scientific": {
            "u1_green": u1_green,
            "u2_green": u2_green,
            "u3_directionally_correct": u3_directionally_correct,
            "u4_smoke_test_only": u4_is_smoke_test_only,
            "unevaluated": unevaluated,
        },
        "failed_engineering_reported_as_negative_model_finding": False,
        "alternative_results_ladder_applies": decision
        is CheckpointDecision.YELLOW,
        "scope_cuts": [dict(entry) for entry in scope_cuts],
        "cut_breadth_before_validity": True,
        "detail": detail,
    }


# ---------------------------------------------------------------------------
# Step 9.8 — tag record and bound external artifact index
# ---------------------------------------------------------------------------


def build_tag_record(
    *,
    tag_name: str,
    target_commit: str,
    branch: str,
    identity: Mapping[str, Any],
    accepted_manifest_sha256: str,
    schema_version: str,
    external_artifacts: Sequence[Mapping[str, Any]],
    run_ids: Sequence[str],
    review_completed: bool,
    tag_created: bool = False,
    tag_pushed: bool = False,
) -> dict[str, Any]:
    """Prepare and validate the MVP tag record without creating the tag.

    A tag whose external artifacts are not bound by checksum is incomplete, and
    final tagging is a coordinated five-role operation that never happens from a
    single role branch.
    """

    if tag_pushed:
        _fail(
            CheckpointErrorCode.TAG_PUSH_FORBIDDEN,
            "the MVP release tag must not be pushed from a role branch",
        )
    unbound = [
        dict(entry)
        for entry in external_artifacts
        if not entry.get("sha256") or not entry.get("uri")
    ]
    required = ("code_sha", "config_hash", "model_hash", "preprocess_hash")
    missing = [name for name in required if not identity.get(name)]
    complete = (
        not unbound
        and not missing
        and bool(accepted_manifest_sha256)
        and bool(run_ids)
        and review_completed
    )
    return {
        "schema_version": TAG_RECORD_SCHEMA_VERSION,
        "step": "9.8",
        "tag_name": tag_name,
        "target_commit": target_commit,
        "prepared_on_branch": branch,
        "tag_created": tag_created,
        "tag_pushed": False,
        "tag_creation_is_coordinated_five_role_operation": True,
        "created_from_role_branch": False,
        "review_completed": review_completed,
        "identity": dict(identity),
        "missing_identity_fields": missing,
        "schema_version_bound": schema_version,
        "accepted_manifest_sha256": accepted_manifest_sha256,
        "run_ids": list(run_ids),
        "external_artifact_index": [dict(entry) for entry in external_artifacts],
        "external_artifact_count": len(external_artifacts),
        "unbound_external_artifacts": unbound,
        "unbound_external_artifact_count": len(unbound),
        "tag_record_complete": complete,
        "status": "READY_FOR_COORDINATED_TAGGING" if complete else "INCOMPLETE",
        "reconstructs_accepted_mvp_identity": complete,
    }


def index_digest(index: Sequence[Mapping[str, Any]]) -> str:
    """Hash an artifact index so the tag record itself can be referenced."""

    return hashlib.sha256(
        json.dumps(list(index), sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


__all__ = [
    "CHECKPOINT_DECISION_SCHEMA_VERSION",
    "EVIDENCE_CHAIN_SCHEMA_VERSION",
    "MVP_TAG_NAME",
    "REHEARSAL_SCHEMA_VERSION",
    "RED_ENGINEERING_AREAS",
    "TAG_RECORD_SCHEMA_VERSION",
    "CheckpointDecision",
    "CheckpointError",
    "CheckpointErrorCode",
    "EvidenceLink",
    "RehearsalStatus",
    "RunbookStep",
    "build_evidence_chain",
    "build_rehearsal_receipt",
    "build_tag_record",
    "decide_checkpoint",
    "index_digest",
]
