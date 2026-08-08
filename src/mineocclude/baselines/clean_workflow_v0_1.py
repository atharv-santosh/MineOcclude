"""Clean Person D workflow, checkpoint demonstration, and classifier
(Person D Steps 8.1-8.3).

Step 8.1 requires a documented clean-environment workflow that validates
the environment and package lock, verifies input hashes, validates the
accepted manifest and folds, runs the legal-input and split audits, runs
the baselines, generates grouped nulls and paired comparisons, generates
the missingness/exclusion audit, generates controls, builds the U4
control matrix, builds result and checkpoint receipts, resumes from
*registered state* rather than manually moved files, and captures the
command, stdout/stderr, versions, runtime, outputs, and failures.

Step 8.2 requires a machine-generated checkpoint demonstration and
artifact index in a fixed order, whose displayed values resolve to
machine-readable registered sources and whose real scientific slots stay
empty and blocker-labelled until real outputs exist.

Step 8.3 requires the GREEN/YELLOW/RED classifier, which must separate
engineering failure from negative science and reject unsupported manual
status overrides.

The recurring discipline in all three: a synthetic run is always labeled
synthetic, an unavailable input is ``blocked`` rather than ``passed``,
and an empty scientific slot is never rendered as a null result.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Sequence

WORKFLOW_SCHEMA_ID = "person-d-clean-workflow-run-v0-1"
CHECKPOINT_SCHEMA_ID = "person-d-checkpoint-demonstration-v0-1"
CLASSIFICATION_SCHEMA_ID = "person-d-checkpoint-classification-v0-1"
SCHEMA_VERSION = "1.0"

#: The frozen clean-workflow stage order. A run that skips a stage is
#: incomplete; a run that reorders them is a different workflow.
WORKFLOW_STAGE_IDS: tuple[str, ...] = (
    "validate_environment_and_package_lock",
    "verify_input_hashes",
    "validate_accepted_manifest_and_folds",
    "run_legal_input_audit",
    "run_split_integrity_audit",
    "run_baselines",
    "generate_grouped_nulls",
    "generate_paired_comparisons",
    "generate_missingness_exclusion_audit",
    "generate_controls",
    "build_u4_control_matrix",
    "build_result_receipt",
    "build_checkpoint_receipt",
)

STAGE_STATUSES: tuple[str, ...] = ("passed", "failed", "blocked", "skipped_resumed")

#: The frozen checkpoint demonstration order (Step 8.2).
CHECKPOINT_SECTION_IDS: tuple[str, ...] = (
    "accepted_input_identity",
    "split_integrity_audit",
    "legal_input_firewall",
    "prediction_runs",
    "grouped_nulls",
    "paired_metrics",
    "positive_control",
    "negative_control",
    "missingness_and_exclusions",
    "u4_control_manifest",
    "e_measurement_join",
    "specificity_and_damage_report",
    "evidence_and_version_matrix",
    "provenance_path",
)

CHECKPOINT_SECTION_STATUSES: tuple[str, ...] = ("resolved", "blocked")

CLASSIFICATIONS: tuple[str, ...] = ("GREEN", "YELLOW", "RED")

#: Failure kinds that force RED. Every one of them makes the *interpretation*
#: unsound, as opposed to making a scientific claim weaker.
RED_FAILURE_KINDS: tuple[str, ...] = (
    "split_leakage",
    "metadata_leakage",
    "positive_control_failure",
    "measurement_failure",
    "reproduction_failure",
)

#: Failure kinds that force YELLOW: the pipeline is valid, but a
#: scientific baseline or control result weakens a claim.
YELLOW_FAILURE_KINDS: tuple[str, ...] = (
    "baseline_matches_or_beats_probe",
    "control_weakens_specificity",
    "negative_scientific_result",
)

FAILURE_NATURES: tuple[str, ...] = ("engineering", "science", "unavailable_input")


class CleanWorkflowError(ValueError):
    """Raised when a workflow run, demonstration, or classification is dishonest."""


# --------------------------------------------------------------------------
# Step 8.1 -- clean workflow run record
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class StageResult:
    """One clean-workflow stage's execution record."""

    stage_id: str
    status: str
    command: str
    stdout_path: Optional[str]
    stderr_path: Optional[str]
    runtime_seconds: float
    output_paths: tuple[str, ...] = ()
    failure_detail: Optional[str] = None
    resumed_from_registered_state: bool = False
    registered_state_key: Optional[str] = None

    def __post_init__(self) -> None:
        if self.stage_id not in WORKFLOW_STAGE_IDS:
            raise CleanWorkflowError(f"unknown workflow stage {self.stage_id!r}")
        if self.status not in STAGE_STATUSES:
            raise CleanWorkflowError(
                f"stage {self.stage_id!r} has unknown status {self.status!r}"
            )
        if not self.command:
            raise CleanWorkflowError(
                f"stage {self.stage_id!r} records no command; a clean workflow "
                "must capture the exact command it ran"
            )
        if self.status in ("failed", "blocked") and not self.failure_detail:
            raise CleanWorkflowError(
                f"stage {self.stage_id!r} is {self.status} with no detail"
            )
        if self.status == "skipped_resumed":
            if not self.resumed_from_registered_state:
                raise CleanWorkflowError(
                    f"stage {self.stage_id!r} was skipped but does not declare a "
                    "resume from registered state; a stage may only be skipped "
                    "because the registry already holds its verified output, "
                    "never because a file was moved into place by hand"
                )
            if not self.registered_state_key:
                raise CleanWorkflowError(
                    f"stage {self.stage_id!r} resumed without naming the "
                    "registered state key it resumed from"
                )
        if self.runtime_seconds < 0:
            raise CleanWorkflowError(f"stage {self.stage_id!r} has negative runtime")


def build_clean_workflow_run(
    *,
    run_id: str,
    stages: Sequence[StageResult],
    environment: Mapping[str, Any],
    package_lock_sha256: Optional[str],
    evidence_kind: str = "synthetic",
) -> dict[str, Any]:
    """Assemble the clean-workflow run record.

    Every stage in :data:`WORKFLOW_STAGE_IDS` must be present exactly
    once and in order. A stage that could not run is ``blocked`` with a
    detail; it is never omitted, because an omitted stage is
    indistinguishable from one that silently did nothing.
    """

    if evidence_kind not in ("real", "synthetic"):
        raise CleanWorkflowError("evidence_kind must be 'real' or 'synthetic'")

    by_id: dict[str, StageResult] = {}
    for stage in stages:
        if stage.stage_id in by_id:
            raise CleanWorkflowError(f"duplicate stage {stage.stage_id!r}")
        by_id[stage.stage_id] = stage

    missing = [sid for sid in WORKFLOW_STAGE_IDS if sid not in by_id]
    if missing:
        raise CleanWorkflowError(
            f"workflow run is missing stages {missing}; a stage that could not "
            "run must be recorded as blocked, never omitted"
        )

    ordered = [by_id[sid] for sid in WORKFLOW_STAGE_IDS]
    status_counts = {status: 0 for status in STAGE_STATUSES}
    for stage in ordered:
        status_counts[stage.status] += 1

    for required in ("python_version", "platform", "interpreter_path"):
        if required not in environment:
            raise CleanWorkflowError(
                f"the run record must capture {required!r} in its environment"
            )

    reproduction_complete = (
        status_counts["failed"] == 0 and status_counts["blocked"] == 0
    )

    return {
        "schema_id": WORKFLOW_SCHEMA_ID,
        "schema_version": SCHEMA_VERSION,
        "producer_role": "person_d",
        "run_id": run_id,
        "evidence_kind": evidence_kind,
        "reproduction_kind": (
            "real_clean_reproduction"
            if evidence_kind == "real"
            else "synthetic_clean_reproduction"
        ),
        "environment": dict(sorted(environment.items())),
        "package_lock_sha256": package_lock_sha256,
        "stage_count": len(ordered),
        "stage_status_counts": status_counts,
        "total_runtime_seconds": round(
            sum(stage.runtime_seconds for stage in ordered), 6
        ),
        "resume_policy": (
            "A stage is skipped only when the run registry already records its "
            "verified output under the named state key. Manually moved files "
            "never satisfy a resume."
        ),
        "stages": tuple(
            {
                "stage_id": stage.stage_id,
                "status": stage.status,
                "command": stage.command,
                "stdout_path": stage.stdout_path,
                "stderr_path": stage.stderr_path,
                "runtime_seconds": stage.runtime_seconds,
                "output_paths": list(stage.output_paths),
                "failure_detail": stage.failure_detail,
                "resumed_from_registered_state": stage.resumed_from_registered_state,
                "registered_state_key": stage.registered_state_key,
            }
            for stage in ordered
        ),
        "reproduction_complete": reproduction_complete,
    }


def validate_clean_workflow_run(document: Mapping[str, Any]) -> None:
    """Validate a workflow run record, raising on the first violation."""

    if document.get("schema_id") != WORKFLOW_SCHEMA_ID:
        raise CleanWorkflowError(
            f"expected schema_id {WORKFLOW_SCHEMA_ID!r}, got "
            f"{document.get('schema_id')!r}"
        )
    if document.get("evidence_kind") not in ("real", "synthetic"):
        raise CleanWorkflowError("evidence_kind must be 'real' or 'synthetic'")

    expected_kind = (
        "real_clean_reproduction"
        if document["evidence_kind"] == "real"
        else "synthetic_clean_reproduction"
    )
    if document.get("reproduction_kind") != expected_kind:
        raise CleanWorkflowError(
            "reproduction_kind must follow evidence_kind; a synthetic "
            "reproduction can never be labeled a real one"
        )

    stage_ids = tuple(stage["stage_id"] for stage in document.get("stages", ()))
    if stage_ids != WORKFLOW_STAGE_IDS:
        raise CleanWorkflowError(
            f"stages must appear exactly once in the frozen order "
            f"{WORKFLOW_STAGE_IDS}, got {stage_ids}"
        )

    counts = {status: 0 for status in STAGE_STATUSES}
    for stage in document["stages"]:
        if stage["status"] not in STAGE_STATUSES:
            raise CleanWorkflowError(
                f"stage {stage['stage_id']!r} has unknown status {stage['status']!r}"
            )
        counts[stage["status"]] += 1
        if stage["status"] in ("failed", "blocked") and not stage["failure_detail"]:
            raise CleanWorkflowError(
                f"stage {stage['stage_id']!r} is {stage['status']} with no detail"
            )
        if stage["status"] == "skipped_resumed" and not stage["registered_state_key"]:
            raise CleanWorkflowError(
                f"stage {stage['stage_id']!r} resumed without a registered state key"
            )
        if not stage["command"]:
            raise CleanWorkflowError(
                f"stage {stage['stage_id']!r} records no command"
            )

    if document.get("stage_status_counts") != counts:
        raise CleanWorkflowError("stage_status_counts do not match the stages")

    expected_complete = counts["failed"] == 0 and counts["blocked"] == 0
    if document.get("reproduction_complete") != expected_complete:
        raise CleanWorkflowError(
            "reproduction_complete must be false whenever any stage failed or "
            "was blocked"
        )


# --------------------------------------------------------------------------
# Step 8.2 -- checkpoint demonstration and artifact index
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class CheckpointSection:
    """One demonstration section, resolved to a registered source or blocked."""

    section_id: str
    status: str
    source_artifact_id: Optional[str] = None
    source_path: Optional[str] = None
    source_sha256: Optional[str] = None
    owner_role: Optional[str] = None
    displayed_values: Mapping[str, Any] = field(default_factory=dict)
    blocker: Optional[str] = None
    blocker_owner: Optional[str] = None

    def __post_init__(self) -> None:
        if self.section_id not in CHECKPOINT_SECTION_IDS:
            raise CleanWorkflowError(f"unknown checkpoint section {self.section_id!r}")
        if self.status not in CHECKPOINT_SECTION_STATUSES:
            raise CleanWorkflowError(
                f"section {self.section_id!r} has unknown status {self.status!r}"
            )
        if self.status == "resolved":
            if not (self.source_artifact_id and self.source_path and self.source_sha256):
                raise CleanWorkflowError(
                    f"section {self.section_id!r} claims to be resolved but does "
                    "not resolve to a registered machine-readable source"
                )
            if len(self.source_sha256) != 64:
                raise CleanWorkflowError(
                    f"section {self.section_id!r} source_sha256 is not a SHA-256"
                )
        else:
            if self.displayed_values:
                raise CleanWorkflowError(
                    f"blocked section {self.section_id!r} displays values; a real "
                    "scientific slot must stay empty until real output exists"
                )
            if not self.blocker or not self.blocker_owner:
                raise CleanWorkflowError(
                    f"blocked section {self.section_id!r} names no blocker and "
                    "owner"
                )


def build_checkpoint_demonstration(
    *,
    run_id: str,
    sections: Sequence[CheckpointSection],
    evidence_kind: str = "synthetic",
) -> dict[str, Any]:
    """Assemble the machine-generated checkpoint demonstration."""

    if evidence_kind not in ("real", "synthetic"):
        raise CleanWorkflowError("evidence_kind must be 'real' or 'synthetic'")

    by_id: dict[str, CheckpointSection] = {}
    for section in sections:
        if section.section_id in by_id:
            raise CleanWorkflowError(f"duplicate section {section.section_id!r}")
        by_id[section.section_id] = section

    missing = [sid for sid in CHECKPOINT_SECTION_IDS if sid not in by_id]
    if missing:
        raise CleanWorkflowError(
            f"demonstration is missing sections {missing}; a section with no "
            "real output must be present and blocker-labelled"
        )

    ordered = [by_id[sid] for sid in CHECKPOINT_SECTION_IDS]
    blocked = [section for section in ordered if section.status == "blocked"]

    return {
        "schema_id": CHECKPOINT_SCHEMA_ID,
        "schema_version": SCHEMA_VERSION,
        "producer_role": "person_d",
        "run_id": run_id,
        "evidence_kind": evidence_kind,
        "section_count": len(ordered),
        "resolved_section_count": len(ordered) - len(blocked),
        "blocked_section_count": len(blocked),
        "demonstration_complete": not blocked,
        "sections": tuple(
            {
                "section_id": section.section_id,
                "status": section.status,
                "source_artifact_id": section.source_artifact_id,
                "source_path": section.source_path,
                "source_sha256": section.source_sha256,
                "owner_role": section.owner_role,
                "displayed_values": dict(sorted(section.displayed_values.items())),
                "blocker": section.blocker,
                "blocker_owner": section.blocker_owner,
            }
            for section in ordered
        ),
        "artifact_index": tuple(
            {
                "section_id": section.section_id,
                "artifact_id": section.source_artifact_id,
                "path": section.source_path,
                "sha256": section.source_sha256,
                "owner_role": section.owner_role,
            }
            for section in ordered
            if section.status == "resolved"
        ),
    }


def validate_checkpoint_demonstration(document: Mapping[str, Any]) -> None:
    """Validate a checkpoint demonstration, raising on the first violation."""

    if document.get("schema_id") != CHECKPOINT_SCHEMA_ID:
        raise CleanWorkflowError(
            f"expected schema_id {CHECKPOINT_SCHEMA_ID!r}, got "
            f"{document.get('schema_id')!r}"
        )
    if document.get("evidence_kind") not in ("real", "synthetic"):
        raise CleanWorkflowError("evidence_kind must be 'real' or 'synthetic'")

    section_ids = tuple(s["section_id"] for s in document.get("sections", ()))
    if section_ids != CHECKPOINT_SECTION_IDS:
        raise CleanWorkflowError(
            f"sections must appear exactly once in the frozen order "
            f"{CHECKPOINT_SECTION_IDS}, got {section_ids}"
        )

    for section in document["sections"]:
        if section["status"] == "resolved":
            if not (
                section["source_artifact_id"]
                and section["source_path"]
                and section["source_sha256"]
            ):
                raise CleanWorkflowError(
                    f"resolved section {section['section_id']!r} does not resolve "
                    "to a registered source"
                )
        elif section["status"] == "blocked":
            if section["displayed_values"]:
                raise CleanWorkflowError(
                    f"blocked section {section['section_id']!r} displays values"
                )
            if not section["blocker"] or not section["blocker_owner"]:
                raise CleanWorkflowError(
                    f"blocked section {section['section_id']!r} names no blocker"
                )
        else:
            raise CleanWorkflowError(
                f"section {section['section_id']!r} has unknown status "
                f"{section['status']!r}"
            )

    blocked = [s for s in document["sections"] if s["status"] == "blocked"]
    if document.get("demonstration_complete") != (not blocked):
        raise CleanWorkflowError(
            "demonstration_complete must be false whenever any section is blocked"
        )


# --------------------------------------------------------------------------
# Step 8.3 -- GREEN / YELLOW / RED classifier
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class CheckpointFinding:
    """One classified finding feeding the checkpoint decision."""

    finding_id: str
    failure_kind: str
    nature: str
    evidence_artifact_id: str
    evidence_sha256: Optional[str]
    owner_role: str
    next_action: str
    affected_claims: tuple[str, ...]
    detail: str

    def __post_init__(self) -> None:
        if self.nature not in FAILURE_NATURES:
            raise CleanWorkflowError(
                f"finding {self.finding_id!r} has unknown nature {self.nature!r}; "
                "engineering failure and negative science must stay distinct"
            )
        if self.failure_kind in RED_FAILURE_KINDS and self.nature != "engineering":
            raise CleanWorkflowError(
                f"finding {self.finding_id!r} declares {self.failure_kind!r} as "
                f"{self.nature!r}; leakage, positive-control, measurement, and "
                "reproduction failures invalidate interpretation and are always "
                "engineering failures"
            )
        if self.failure_kind in YELLOW_FAILURE_KINDS and self.nature != "science":
            raise CleanWorkflowError(
                f"finding {self.finding_id!r} declares {self.failure_kind!r} as "
                f"{self.nature!r}; a weakened claim from a valid pipeline is a "
                "scientific result, not an engineering defect"
            )
        for name, value in (
            ("evidence_artifact_id", self.evidence_artifact_id),
            ("owner_role", self.owner_role),
            ("next_action", self.next_action),
            ("detail", self.detail),
        ):
            if not value:
                raise CleanWorkflowError(
                    f"finding {self.finding_id!r} records no {name}"
                )


def classify_checkpoint(
    *,
    findings: Sequence[CheckpointFinding],
    contracts_pass: bool,
    controls_pass: bool,
    result_lineage_pass: bool,
    clean_reproduction_pass: bool,
    manual_override: Optional[str] = None,
    manual_override_evidence_artifact_id: Optional[str] = None,
) -> dict[str, Any]:
    """Classify the checkpoint GREEN, YELLOW, or RED.

    GREEN requires all four gates to pass *and* no finding at all. A
    ``unavailable_input`` finding therefore cannot produce GREEN: science
    that has not run is not successful science.

    A ``manual_override`` is accepted only when it is *more severe* than
    the computed classification and cites a registered evidence artifact.
    An override that upgrades the status, or one with no evidence, is
    rejected.
    """

    red_findings = [f for f in findings if f.failure_kind in RED_FAILURE_KINDS]
    unavailable = [f for f in findings if f.nature == "unavailable_input"]
    science_findings = [f for f in findings if f.nature == "science"]

    gates = {
        "contracts_pass": bool(contracts_pass),
        "controls_pass": bool(controls_pass),
        "result_lineage_pass": bool(result_lineage_pass),
        "clean_reproduction_pass": bool(clean_reproduction_pass),
    }

    if red_findings or not all(gates.values()):
        computed = "RED"
    elif science_findings or unavailable:
        computed = "YELLOW"
    else:
        computed = "GREEN"

    classification = computed
    override_accepted = False
    override_rejection_reason = None
    if manual_override is not None:
        if manual_override not in CLASSIFICATIONS:
            raise CleanWorkflowError(
                f"unknown manual override {manual_override!r}"
            )
        severity = {"GREEN": 0, "YELLOW": 1, "RED": 2}
        if not manual_override_evidence_artifact_id:
            override_rejection_reason = (
                "a manual status override must cite a registered evidence "
                "artifact"
            )
        elif severity[manual_override] < severity[computed]:
            override_rejection_reason = (
                f"a manual override may not upgrade {computed} to "
                f"{manual_override}; only a more severe classification may be "
                "asserted by hand"
            )
        else:
            classification = manual_override
            override_accepted = True

    return {
        "schema_id": CLASSIFICATION_SCHEMA_ID,
        "schema_version": SCHEMA_VERSION,
        "producer_role": "person_d",
        "classification": classification,
        "computed_classification": computed,
        "gates": gates,
        "manual_override": manual_override,
        "manual_override_accepted": override_accepted,
        "manual_override_rejection_reason": override_rejection_reason,
        "definitions": {
            "GREEN": (
                "Contracts, controls, result lineage, and clean reproducibility "
                "pass."
            ),
            "YELLOW": (
                "The pipeline is valid but a scientific baseline or control "
                "result weakens a claim."
            ),
            "RED": (
                "Split leakage, metadata leakage, positive-control failure, "
                "measurement failure, or reproduction failure invalidates "
                "interpretation."
            ),
        },
        "unavailable_input_count": len(unavailable),
        "engineering_failure_count": sum(
            1 for f in findings if f.nature == "engineering"
        ),
        "negative_science_count": len(science_findings),
        "findings": tuple(
            {
                "finding_id": f.finding_id,
                "failure_kind": f.failure_kind,
                "nature": f.nature,
                "evidence_artifact_id": f.evidence_artifact_id,
                "evidence_sha256": f.evidence_sha256,
                "owner_role": f.owner_role,
                "next_action": f.next_action,
                "affected_claims": list(f.affected_claims),
                "detail": f.detail,
            }
            for f in sorted(findings, key=lambda f: f.finding_id)
        ),
    }


def validate_checkpoint_classification(document: Mapping[str, Any]) -> None:
    """Validate a classification, raising on the first violation."""

    if document.get("schema_id") != CLASSIFICATION_SCHEMA_ID:
        raise CleanWorkflowError(
            f"expected schema_id {CLASSIFICATION_SCHEMA_ID!r}, got "
            f"{document.get('schema_id')!r}"
        )
    if document.get("classification") not in CLASSIFICATIONS:
        raise CleanWorkflowError(
            f"unknown classification {document.get('classification')!r}"
        )

    gates = document.get("gates") or {}
    findings = document.get("findings") or ()
    red = [f for f in findings if f["failure_kind"] in RED_FAILURE_KINDS]
    unavailable = [f for f in findings if f["nature"] == "unavailable_input"]
    science = [f for f in findings if f["nature"] == "science"]

    if red or not all(gates.values()):
        expected = "RED"
    elif science or unavailable:
        expected = "YELLOW"
    else:
        expected = "GREEN"

    if document.get("computed_classification") != expected:
        raise CleanWorkflowError(
            f"computed_classification {document.get('computed_classification')!r} "
            f"does not follow from the gates and findings (expected {expected!r})"
        )

    if document["classification"] != document["computed_classification"]:
        if not document.get("manual_override_accepted"):
            raise CleanWorkflowError(
                "classification differs from the computed classification without "
                "an accepted override"
            )
        severity = {"GREEN": 0, "YELLOW": 1, "RED": 2}
        if severity[document["classification"]] < severity[expected]:
            raise CleanWorkflowError(
                "a manual override may never upgrade the computed classification"
            )

    if expected == "GREEN" and unavailable:
        raise CleanWorkflowError(
            "unavailable science must never be classified as successful science"
        )

    for finding in findings:
        if finding["nature"] not in FAILURE_NATURES:
            raise CleanWorkflowError(
                f"finding {finding['finding_id']!r} has unknown nature"
            )
        if not finding["next_action"] or not finding["owner_role"]:
            raise CleanWorkflowError(
                f"finding {finding['finding_id']!r} names no owner or next action"
            )
        if not finding["evidence_artifact_id"]:
            raise CleanWorkflowError(
                f"finding {finding['finding_id']!r} cites no evidence"
            )


def dump_document(document: Mapping[str, Any]) -> str:
    """Serialize any of this module's documents deterministically."""

    schema_id = document.get("schema_id")
    if schema_id == WORKFLOW_SCHEMA_ID:
        validate_clean_workflow_run(document)
    elif schema_id == CHECKPOINT_SCHEMA_ID:
        validate_checkpoint_demonstration(document)
    elif schema_id == CLASSIFICATION_SCHEMA_ID:
        validate_checkpoint_classification(document)
    else:
        raise CleanWorkflowError(f"unknown schema_id {schema_id!r}")
    return json.dumps(document, indent=2, sort_keys=True, default=_json_default) + "\n"


def _json_default(value: Any) -> Any:
    if isinstance(value, tuple):
        return list(value)
    raise TypeError(f"{type(value).__name__} is not JSON serializable")


__all__ = [
    "CHECKPOINT_SCHEMA_ID",
    "CHECKPOINT_SECTION_IDS",
    "CHECKPOINT_SECTION_STATUSES",
    "CLASSIFICATIONS",
    "CLASSIFICATION_SCHEMA_ID",
    "FAILURE_NATURES",
    "RED_FAILURE_KINDS",
    "SCHEMA_VERSION",
    "STAGE_STATUSES",
    "WORKFLOW_SCHEMA_ID",
    "WORKFLOW_STAGE_IDS",
    "YELLOW_FAILURE_KINDS",
    "CheckpointFinding",
    "CheckpointSection",
    "CleanWorkflowError",
    "StageResult",
    "build_checkpoint_demonstration",
    "build_clean_workflow_run",
    "classify_checkpoint",
    "dump_document",
    "validate_checkpoint_classification",
    "validate_checkpoint_demonstration",
    "validate_clean_workflow_run",
]
