"""Step 7.2 — assemble and audit machine-generated checkpoint evidence.

The checkpoint deck is the one artifact most likely to acquire a hand-typed
number, so this module refuses to build one. Every displayed value must arrive
attached to a source artifact id, a figure-input hash, and a gate label that
says whether it is an engineering (planning) threshold or a scientific result.

Slots that have no accepted upstream result stay present and explicitly empty.
An empty slot is evidence: it tells the reviewer what is missing and who owns
it, which a fabricated placeholder would hide.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

from mineocclude.analysis.manifests import is_hex_digest
from mineocclude.experiments.registry import hash_json_value


CHECKPOINT_EVIDENCE_SCHEMA_VERSION = "person-e-checkpoint-evidence-v0.1"
VISUAL_QA_REPORT_SCHEMA_VERSION = "person-e-checkpoint-visual-qa-v0.1"

#: Every slot the checkpoint must account for, present or explicitly empty.
#: The first two are Person E's own engineering gates; the rest are the
#: scientific slots whose contents Person B owns.
EVIDENCE_SLOTS = (
    "engineering_detector_gate",
    "engineering_localization_gate",
    "u1_layer_emergence",
    "u2_calibration_coverage",
    "u3_reveal_dynamics",
    "u4_dose_response",
    "u4_persistence",
    "u4_displacement",
    "u4_ssim",
)

#: A planning gate is Person E engineering evidence (detector precision,
#: localization error). A scientific gate is Person B's to label and own.
GATE_KINDS = frozenset({"planning", "scientific"})

SLOT_STATES = frozenset(
    {
        "populated",
        "empty_awaiting_external_input",
        "empty_excluded",
    }
)

#: Values that look like results but are not. A checkpoint that displays any of
#: these is presenting an invention as evidence.
PLACEHOLDER_TOKENS = frozenset(
    {
        "",
        "-",
        "--",
        "?",
        "n/a",
        "na",
        "tba",
        "tbd",
        "todo",
        "placeholder",
        "example",
        "sample",
        "dummy",
        "fake",
        "lorem ipsum",
        "xxx",
        "foo",
        "bar",
    }
)

EXCLUDED_SOURCE_STATUSES = frozenset({"superseded", "failed", "invalid", "excluded"})


SHA256_HEX_LENGTH = 64


def _is_sha256(value: object) -> bool:
    return is_hex_digest(value, SHA256_HEX_LENGTH)


class CheckpointEvidenceError(ValueError):
    """Raised when checkpoint evidence could mislead a reviewer."""


def _require_mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CheckpointEvidenceError(f"{name} must be a JSON object.")
    return value


def _require_sequence(value: Any, name: str) -> Sequence[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise CheckpointEvidenceError(f"{name} must be a JSON array.")
    return value


def _require_text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CheckpointEvidenceError(f"{name} must be a non-empty string.")
    return value


def is_placeholder_value(value: Any) -> bool:
    """Return whether ``value`` is a stand-in rather than a measured result."""

    if value is None:
        return True
    if isinstance(value, str):
        return value.strip().lower() in PLACEHOLDER_TOKENS
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return not math.isfinite(float(value))
    return False


def validate_displayed_value(row: Any) -> Mapping[str, Any]:
    """Validate one displayed number and its full provenance attachment."""

    value_row = _require_mapping(row, "displayed value")
    label = _require_text(value_row.get("label"), "displayed value label")
    if "value" not in value_row:
        raise CheckpointEvidenceError(f"Displayed value {label} has no value.")
    if is_placeholder_value(value_row.get("value")):
        raise CheckpointEvidenceError(
            f"Displayed value {label} is a placeholder, not a measurement."
        )
    _require_text(value_row.get("units"), f"{label} units")
    _require_text(value_row.get("source_artifact_id"), f"{label} source_artifact_id")
    _require_text(value_row.get("source_run_id"), f"{label} source_run_id")
    if not _is_sha256(value_row.get("figure_input_sha256")):
        raise CheckpointEvidenceError(
            f"Displayed value {label} has no figure-input digest."
        )
    gate_kind = value_row.get("gate_kind")
    if gate_kind not in GATE_KINDS:
        raise CheckpointEvidenceError(
            f"Displayed value {label} has an unsupported gate kind: {gate_kind}"
        )
    source_status = _require_text(
        value_row.get("source_status"), f"{label} source_status"
    )
    if source_status in EXCLUDED_SOURCE_STATUSES:
        raise CheckpointEvidenceError(
            f"Displayed value {label} resolves to a {source_status} source."
        )
    if not isinstance(value_row.get("sample_count"), int) or (
        value_row["sample_count"] < 0
    ):
        raise CheckpointEvidenceError(
            f"Displayed value {label} needs a non-negative sample count."
        )
    return value_row


def validate_slot(row: Any) -> Mapping[str, Any]:
    """Validate one evidence slot, populated or explicitly empty."""

    slot = _require_mapping(row, "evidence slot")
    name = _require_text(slot.get("slot"), "slot")
    if name not in EVIDENCE_SLOTS:
        raise CheckpointEvidenceError(f"Unknown evidence slot: {name}")
    state = slot.get("state")
    if state not in SLOT_STATES:
        raise CheckpointEvidenceError(f"Slot {name} has an unsupported state: {state}")
    values = _require_sequence(slot.get("displayed_values"), f"{name} displayed_values")
    if state == "populated":
        if not values:
            raise CheckpointEvidenceError(f"Populated slot {name} displays nothing.")
        for value_row in values:
            validate_displayed_value(value_row)
    else:
        if values:
            raise CheckpointEvidenceError(
                f"Empty slot {name} must not display values."
            )
        _require_text(slot.get("empty_reason"), f"{name} empty_reason")
        _require_text(slot.get("blocking_owner"), f"{name} blocking_owner")
    return slot


def verify_figure_to_source(
    slots: Sequence[Mapping[str, Any]],
    figure_index: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Check every displayed value against the figure index that produced it."""

    unresolved: list[str] = []
    digest_mismatches: list[str] = []
    excluded_sources: list[str] = []
    resolved = 0
    for slot in slots:
        for value_row in slot.get("displayed_values", ()):
            artifact_id = str(value_row["source_artifact_id"])
            entry = figure_index.get(artifact_id)
            if entry is None:
                unresolved.append(artifact_id)
                continue
            if entry.get("figure_input_sha256") != value_row.get(
                "figure_input_sha256"
            ):
                digest_mismatches.append(artifact_id)
                continue
            if entry.get("status") in EXCLUDED_SOURCE_STATUSES:
                excluded_sources.append(artifact_id)
                continue
            resolved += 1
    return {
        "digest_mismatched_source_ids": sorted(set(digest_mismatches)),
        "excluded_source_ids": sorted(set(excluded_sources)),
        "resolved_value_count": resolved,
        "unresolved_source_ids": sorted(set(unresolved)),
        "verified": not unresolved and not digest_mismatches and not excluded_sources,
    }


def build_visual_qa_report(
    slots: Sequence[Mapping[str, Any]],
    figure_verification: Mapping[str, Any],
) -> dict[str, Any]:
    """Record the objective visual checks the manual requires at Step 7.2."""

    populated = [slot for slot in slots if slot["state"] == "populated"]
    empty = [slot for slot in slots if slot["state"] != "populated"]
    missing_units = sorted(
        str(value_row["label"])
        for slot in populated
        for value_row in slot["displayed_values"]
        if not str(value_row.get("units", "")).strip()
    )
    return {
        "visual_qa_report_schema_version": VISUAL_QA_REPORT_SCHEMA_VERSION,
        "all_displayed_values_carry_units": not missing_units,
        "all_displayed_values_resolve_to_source": bool(
            figure_verification.get("verified")
        ),
        "displayed_value_count": sum(
            len(slot["displayed_values"]) for slot in populated
        ),
        "empty_slot_count": len(empty),
        "empty_slots": sorted(str(slot["slot"]) for slot in empty),
        "invalid_or_superseded_displayed_count": len(
            figure_verification.get("excluded_source_ids", ())
        ),
        "populated_slot_count": len(populated),
        "values_missing_units": missing_units,
    }


def build_checkpoint_evidence(
    *,
    slots: Sequence[Mapping[str, Any]],
    figure_index: Mapping[str, Mapping[str, Any]],
    artifact_index: Sequence[Mapping[str, Any]],
    accepted_count: int,
    excluded_count: int,
    missing_count: int,
    control_failures: Sequence[Mapping[str, Any]],
    limitations: Sequence[str],
    provenance_demonstration_commands: Sequence[Sequence[str]],
    code_commit: str,
) -> dict[str, Any]:
    """Build the checkpoint evidence package from machine-generated inputs."""

    validated = [dict(validate_slot(slot)) for slot in slots]
    present = {str(slot["slot"]) for slot in validated}
    if present != set(EVIDENCE_SLOTS):
        raise CheckpointEvidenceError(
            "Every evidence slot must be accounted for; missing: "
            f"{sorted(set(EVIDENCE_SLOTS) - present)}"
        )
    if not provenance_demonstration_commands:
        raise CheckpointEvidenceError(
            "The checkpoint must ship at least one provenance demonstration command."
        )

    figure_verification = verify_figure_to_source(validated, figure_index)
    visual_qa = build_visual_qa_report(validated, figure_verification)

    populated_slots = sorted(
        str(slot["slot"]) for slot in validated if slot["state"] == "populated"
    )
    scientific_values = [
        value_row
        for slot in validated
        for value_row in slot["displayed_values"]
        if value_row.get("gate_kind") == "scientific"
    ]

    package = {
        "checkpoint_evidence_schema_version": CHECKPOINT_EVIDENCE_SCHEMA_VERSION,
        "accepted_count": int(accepted_count),
        "artifact_index": [dict(row) for row in artifact_index],
        "code_commit": _require_text(code_commit, "code_commit"),
        "control_failures": [dict(row) for row in control_failures],
        "excluded_count": int(excluded_count),
        "figure_source_verification": dict(figure_verification),
        "limitations": list(limitations),
        "machine_generated_values_only": True,
        "missing_count": int(missing_count),
        "populated_slots": populated_slots,
        "provenance_demonstration_commands": [
            [str(token) for token in command]
            for command in provenance_demonstration_commands
        ],
        "scientific_value_count": len(scientific_values),
        "slots": validated,
        "visual_qa_report": visual_qa,
    }
    package["checkpoint_content_hash"] = hash_json_value(
        {
            key: value
            for key, value in package.items()
            if key != "checkpoint_content_hash"
        }
    )
    return package


def validate_checkpoint_evidence(document: Any) -> Mapping[str, Any]:
    """Re-check a persisted checkpoint package end to end."""

    package = _require_mapping(document, "checkpoint evidence")
    if (
        package.get("checkpoint_evidence_schema_version")
        != CHECKPOINT_EVIDENCE_SCHEMA_VERSION
    ):
        raise CheckpointEvidenceError("Unknown checkpoint evidence schema version.")
    slots = _require_sequence(package.get("slots"), "slots")
    for slot in slots:
        validate_slot(slot)
    present = {str(_require_mapping(slot, "slot")["slot"]) for slot in slots}
    if present != set(EVIDENCE_SLOTS):
        raise CheckpointEvidenceError("Checkpoint evidence is missing required slots.")
    if package.get("machine_generated_values_only") is not True:
        raise CheckpointEvidenceError(
            "Checkpoint evidence must be machine generated end to end."
        )
    verification = _require_mapping(
        package.get("figure_source_verification"), "figure_source_verification"
    )
    if verification.get("excluded_source_ids"):
        raise CheckpointEvidenceError(
            "Checkpoint evidence displays an invalid or superseded source."
        )
    recomputed = hash_json_value(
        {
            key: value
            for key, value in package.items()
            if key != "checkpoint_content_hash"
        }
    )
    if recomputed != package.get("checkpoint_content_hash"):
        raise CheckpointEvidenceError("Checkpoint evidence content hash drift.")
    return package
