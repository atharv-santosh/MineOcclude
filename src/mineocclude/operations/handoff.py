"""Step 7.3 — the frozen Person E operating contract for a second operator.

The pass check for this step is behavioural, not documentary: someone who is
not Person E must be able to identify the inputs, run the validators, produce
the outputs, and escalate a failure without private knowledge. So the handoff
is validated as data. Each of the five workflows must name its inputs,
commands, validators, outputs, failure behaviour, version rules, and an
escalation owner, and the operator must be told which reruns they may perform
alone versus which changes require Person A or Person B review.

A Git tag without external artifact identity is explicitly incomplete, so the
external artifact index is a required part of the receipt rather than an
appendix to it.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from mineocclude.analysis.manifests import is_hex_digest
from mineocclude.experiments.registry import hash_json_value


OPERATING_HANDOFF_SCHEMA_VERSION = "person-e-operating-handoff-v0.1"
SECOND_OPERATOR_RECEIPT_SCHEMA_VERSION = "person-e-second-operator-receipt-v0.1"

#: The five frozen workflows a second operator inherits.
REQUIRED_WORKFLOWS = (
    "registry",
    "detector",
    "homography",
    "u4_measurement",
    "preliminary_figures",
)

REQUIRED_WORKFLOW_FIELDS = (
    "commands",
    "escalation_owner",
    "failure_behavior",
    "outputs",
    "permitted_operational_reruns",
    "required_inputs",
    "requires_ab_review",
    "runbook_path",
    "validators",
    "version_and_supersession_rules",
)

#: Owners a failure may be escalated to. Person E cannot escalate to itself for
#: scientific decisions, so those route to Person A or Person B by contract.
ESCALATION_OWNERS = frozenset(
    {"person_a", "person_b", "person_c", "person_d", "person_e"}
)

EXTERNAL_ARTIFACT_STATES = frozenset(
    {"present_local", "external_unmounted", "pending_generation"}
)


SHA256_HEX_LENGTH = 64


def _is_sha256(value: object) -> bool:
    return is_hex_digest(value, SHA256_HEX_LENGTH)


class OperatingHandoffError(ValueError):
    """Raised when the frozen handoff would leave a second operator stuck."""


def _require_mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise OperatingHandoffError(f"{name} must be a JSON object.")
    return value


def _require_sequence(value: Any, name: str) -> Sequence[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise OperatingHandoffError(f"{name} must be a JSON array.")
    return value


def _require_text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise OperatingHandoffError(f"{name} must be a non-empty string.")
    return value


def _require_non_empty_sequence(value: Any, name: str) -> Sequence[Any]:
    items = _require_sequence(value, name)
    if not items:
        raise OperatingHandoffError(f"{name} must not be empty.")
    return items


def validate_workflow(row: Any) -> Mapping[str, Any]:
    """Validate one operating workflow against the second-operator contract."""

    workflow = _require_mapping(row, "workflow")
    name = _require_text(workflow.get("workflow"), "workflow")
    if name not in REQUIRED_WORKFLOWS:
        raise OperatingHandoffError(f"Unknown workflow: {name}")
    missing = [field for field in REQUIRED_WORKFLOW_FIELDS if field not in workflow]
    if missing:
        raise OperatingHandoffError(f"Workflow {name} is missing fields: {missing}")

    _require_non_empty_sequence(workflow["required_inputs"], f"{name} required_inputs")
    _require_non_empty_sequence(workflow["outputs"], f"{name} outputs")
    _require_non_empty_sequence(workflow["validators"], f"{name} validators")
    _require_text(workflow["failure_behavior"], f"{name} failure_behavior")
    _require_text(
        workflow["version_and_supersession_rules"],
        f"{name} version_and_supersession_rules",
    )
    _require_text(workflow["runbook_path"], f"{name} runbook_path")

    commands = _require_non_empty_sequence(workflow["commands"], f"{name} commands")
    for command in commands:
        tokens = _require_non_empty_sequence(command, f"{name} command")
        for token in tokens:
            _require_text(token, f"{name} command token")

    owner = workflow["escalation_owner"]
    if owner not in ESCALATION_OWNERS:
        raise OperatingHandoffError(
            f"Workflow {name} has an unsupported escalation owner: {owner}"
        )

    # A workflow that permits no rerun at all is not operable, and one that
    # claims no change ever needs A/B review has quietly taken their authority.
    _require_non_empty_sequence(
        workflow["permitted_operational_reruns"],
        f"{name} permitted_operational_reruns",
    )
    _require_non_empty_sequence(
        workflow["requires_ab_review"], f"{name} requires_ab_review"
    )
    return workflow


def validate_frozen_version_table(rows: Any) -> Sequence[Mapping[str, Any]]:
    """Validate the frozen component and schema version table."""

    entries = _require_non_empty_sequence(rows, "frozen_version_table")
    seen: set[str] = set()
    for row in entries:
        entry = _require_mapping(row, "frozen version row")
        component = _require_text(entry.get("component"), "component")
        if component in seen:
            raise OperatingHandoffError(f"Duplicate frozen component: {component}")
        seen.add(component)
        _require_text(entry.get("version"), f"{component} version")
        _require_text(entry.get("owner"), f"{component} owner")
        digest = entry.get("sha256")
        if digest is not None and not _is_sha256(digest):
            raise OperatingHandoffError(f"{component} sha256 is not a digest.")
    return entries


def validate_external_artifact_index(rows: Any) -> Sequence[Mapping[str, Any]]:
    """Validate the external artifact index that a Git tag alone cannot carry."""

    entries = _require_sequence(rows, "external_artifact_index")
    seen: set[str] = set()
    for row in entries:
        entry = _require_mapping(row, "external artifact row")
        artifact_id = _require_text(entry.get("artifact_id"), "artifact_id")
        if artifact_id in seen:
            raise OperatingHandoffError(f"Duplicate external artifact: {artifact_id}")
        seen.add(artifact_id)
        _require_text(entry.get("owner"), f"{artifact_id} owner")
        _require_text(entry.get("recorded_path"), f"{artifact_id} recorded_path")
        state = entry.get("availability")
        if state not in EXTERNAL_ARTIFACT_STATES:
            raise OperatingHandoffError(
                f"{artifact_id} has an unsupported availability: {state}"
            )
        digest = entry.get("sha256")
        if digest is not None and not _is_sha256(digest):
            raise OperatingHandoffError(f"{artifact_id} sha256 is not a digest.")
    return entries


def validate_external_dependencies(rows: Any) -> Sequence[Mapping[str, Any]]:
    """Validate the exact remaining external dependencies and their owners."""

    entries = _require_sequence(rows, "remaining_external_dependencies")
    for row in entries:
        entry = _require_mapping(row, "external dependency row")
        _require_text(entry.get("dependency_id"), "dependency_id")
        _require_text(entry.get("owner"), "dependency owner")
        _require_text(entry.get("blocks_step"), "blocks_step")
        _require_non_empty_sequence(
            entry.get("next_command"), "dependency next_command"
        )
    return entries


def build_operating_handoff(
    *,
    workflows: Sequence[Mapping[str, Any]],
    frozen_version_table: Sequence[Mapping[str, Any]],
    external_artifact_index: Sequence[Mapping[str, Any]],
    remaining_external_dependencies: Sequence[Mapping[str, Any]],
    paper_workspace_plan_path: str,
    code_commit: str,
) -> dict[str, Any]:
    """Assemble the frozen operating handoff document."""

    validated = [dict(validate_workflow(row)) for row in workflows]
    present = {str(row["workflow"]) for row in validated}
    if present != set(REQUIRED_WORKFLOWS):
        raise OperatingHandoffError(
            "Handoff must cover every frozen workflow; missing: "
            f"{sorted(set(REQUIRED_WORKFLOWS) - present)}"
        )
    validate_frozen_version_table(frozen_version_table)
    validate_external_artifact_index(external_artifact_index)
    validate_external_dependencies(remaining_external_dependencies)

    document = {
        "operating_handoff_schema_version": OPERATING_HANDOFF_SCHEMA_VERSION,
        "code_commit": _require_text(code_commit, "code_commit"),
        "external_artifact_index": [dict(row) for row in external_artifact_index],
        "frozen_version_table": [dict(row) for row in frozen_version_table],
        "paper_workspace_plan_path": _require_text(
            paper_workspace_plan_path, "paper_workspace_plan_path"
        ),
        "remaining_external_dependencies": [
            dict(row) for row in remaining_external_dependencies
        ],
        "workflow_count": len(validated),
        "workflows": sorted(validated, key=lambda row: str(row["workflow"])),
    }
    document["handoff_content_hash"] = hash_json_value(
        {
            key: value
            for key, value in document.items()
            if key != "handoff_content_hash"
        }
    )
    return document


def validate_operating_handoff(document: Any) -> Mapping[str, Any]:
    """Re-check a persisted operating handoff."""

    handoff = _require_mapping(document, "operating handoff")
    if (
        handoff.get("operating_handoff_schema_version")
        != OPERATING_HANDOFF_SCHEMA_VERSION
    ):
        raise OperatingHandoffError("Unknown operating handoff schema version.")
    workflows = _require_sequence(handoff.get("workflows"), "workflows")
    for row in workflows:
        validate_workflow(row)
    present = {str(_require_mapping(row, "workflow")["workflow"]) for row in workflows}
    if present != set(REQUIRED_WORKFLOWS):
        raise OperatingHandoffError("Operating handoff is missing a frozen workflow.")
    validate_frozen_version_table(handoff.get("frozen_version_table"))
    validate_external_artifact_index(handoff.get("external_artifact_index"))
    validate_external_dependencies(handoff.get("remaining_external_dependencies"))
    recomputed = hash_json_value(
        {
            key: value
            for key, value in handoff.items()
            if key != "handoff_content_hash"
        }
    )
    if recomputed != handoff.get("handoff_content_hash"):
        raise OperatingHandoffError("Operating handoff content hash drift.")
    return handoff


def build_second_operator_receipt(
    *,
    handoff: Mapping[str, Any],
    runbook_digests: Mapping[str, str],
    reproduction_receipt_hash: str | None,
    checkpoint_evidence_hash: str | None,
) -> dict[str, Any]:
    """Record whether a second operator could actually run each workflow.

    ``operable_without_person_e`` is derived from whether every workflow's
    runbook exists and every workflow declares commands and validators. It is
    not a statement that real measurement has run.
    """

    validate_operating_handoff(handoff)
    missing_runbooks: list[str] = []
    for workflow in handoff["workflows"]:
        path = str(workflow["runbook_path"])
        digest = runbook_digests.get(path)
        if digest is None or not _is_sha256(digest):
            missing_runbooks.append(path)

    blocked = [
        str(row["dependency_id"])
        for row in handoff["remaining_external_dependencies"]
    ]
    receipt = {
        "second_operator_receipt_schema_version": (
            SECOND_OPERATOR_RECEIPT_SCHEMA_VERSION
        ),
        "blocked_dependency_ids": sorted(blocked),
        "checkpoint_evidence_hash": checkpoint_evidence_hash,
        "handoff_content_hash": handoff["handoff_content_hash"],
        "missing_runbooks": sorted(missing_runbooks),
        "operable_without_person_e": not missing_runbooks,
        "reproduction_receipt_hash": reproduction_receipt_hash,
        "runbook_digests": dict(sorted(runbook_digests.items())),
        "workflow_count": handoff["workflow_count"],
    }
    receipt["receipt_content_hash"] = hash_json_value(
        {key: value for key, value in receipt.items() if key != "receipt_content_hash"}
    )
    return receipt


def validate_second_operator_receipt(document: Any) -> Mapping[str, Any]:
    receipt = _require_mapping(document, "second operator receipt")
    if (
        receipt.get("second_operator_receipt_schema_version")
        != SECOND_OPERATOR_RECEIPT_SCHEMA_VERSION
    ):
        raise OperatingHandoffError("Unknown second-operator receipt schema version.")
    if receipt.get("operable_without_person_e") is True and receipt.get(
        "missing_runbooks"
    ):
        raise OperatingHandoffError(
            "A receipt cannot claim operability while runbooks are missing."
        )
    recomputed = hash_json_value(
        {
            key: value
            for key, value in receipt.items()
            if key != "receipt_content_hash"
        }
    )
    if recomputed != receipt.get("receipt_content_hash"):
        raise OperatingHandoffError("Second-operator receipt content hash drift.")
    return receipt
