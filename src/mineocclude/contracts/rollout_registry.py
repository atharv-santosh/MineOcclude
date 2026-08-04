"""Combined A-to-E rollout-manifest and A/E registry contract.

The validator keeps rollout outcomes, run provenance, artifact lifecycle, and
cross-record lineage in one auditable handoff. It never derives scientific
identity from filenames, repairs malformed records, or computes Person E's
measurement outputs.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any
from urllib.parse import urlparse

from mineocclude.contracts.identity import (
    SCHEMA_VERSION,
    ArtifactStatus,
    IdentityValidationError,
    validate_identity,
)
from mineocclude.contracts.intervention_request import (
    MINEWORLD_LAYER_COUNT,
    MINEWORLD_MODEL_FRAME_COUNT,
)

ROLLOUT_REGISTRY_SCHEMA_VERSION = SCHEMA_VERSION

ALLOWED_CONTROL_TYPES = {
    "intervention",
    "alpha_zero",
    "random_direction",
}

ALLOWED_OUTCOMES = {
    "measurable_continuation",
    "non_persistence",
    "generation_failure",
}

OUTPUT_BEARING_OUTCOMES = {
    "measurable_continuation",
    "non_persistence",
}

ALLOWED_RUN_STATUSES = {
    "completed",
    "completed_with_failures",
    "failed",
}

ALLOWED_ARTIFACT_TYPES = {
    "input_context",
    "intervention_request",
    "rollout_clip",
    "partial_rollout",
    "diagnostic_log",
}

LIFECYCLE_VALUES = {
    item.value
    for item in ArtifactStatus
}

FORBIDDEN_MEASUREMENT_FIELDS = {
    "detections",
    "displacement",
    "displacement_blocks",
    "displacement_m",
    "displacement_pixels",
    "displacement_px",
    "homography",
    "measured_displacement",
    "persistence_score",
    "ssim",
    "zero_displacement",
}


class RolloutRegistryRejectionCode(str, Enum):
    """Machine-readable Step 1.6 rejection reasons."""

    MISSING_REQUIRED_FIELD = "missing_required_field"
    INVALID_SCHEMA_VERSION = "invalid_schema_version"

    INVALID_ROLLOUT_ROW = "invalid_rollout_row"
    DUPLICATE_ROLLOUT_ID = "duplicate_rollout_id"
    INVALID_OUTCOME = "invalid_outcome"
    OUTCOME_OUTPUT_MISMATCH = "outcome_output_mismatch"
    GENERATION_STATUS_MISMATCH = "generation_status_mismatch"
    DISPLACEMENT_ENCODING_FORBIDDEN = "displacement_encoding_forbidden"

    INVALID_RUN_RECORD = "invalid_run_record"
    DUPLICATE_RUN_ID = "duplicate_run_id"
    INVALID_PARENT_LINEAGE = "invalid_parent_lineage"

    INVALID_ARTIFACT_RECORD = "invalid_artifact_record"
    DUPLICATE_ARTIFACT_ID = "duplicate_artifact_id"
    INVALID_LIFECYCLE = "invalid_lifecycle"
    INVALID_SUPERSESSION = "invalid_supersession"

    INVALID_URI = "invalid_uri"
    INVALID_HASH = "invalid_hash"
    MISSING_REGISTRY_REFERENCE = "missing_registry_reference"
    LINEAGE_MISMATCH = "lineage_mismatch"
    METADATA_MISMATCH = "metadata_mismatch"


@dataclass(frozen=True)
class RolloutRegistryRejection:
    """One machine-readable rollout/registry rejection."""

    code: RolloutRegistryRejectionCode
    message: str


@dataclass(frozen=True)
class RolloutRegistryValidationResult:
    """Result returned by combined rollout/registry validation."""

    accepted: bool
    rejections: tuple[RolloutRegistryRejection, ...]


def _add_rejection(
    rejections: list[RolloutRegistryRejection],
    code: RolloutRegistryRejectionCode,
    message: str,
) -> None:
    """Append one rejection without modifying submitted records."""

    rejections.append(
        RolloutRegistryRejection(
            code=code,
            message=message,
        )
    )


def _missing_fields(
    value: Mapping[str, Any],
    required_fields: tuple[str, ...],
) -> list[str]:
    """Return required fields absent from a mapping."""

    return [
        field
        for field in required_fields
        if field not in value
    ]


def _is_non_empty_string(value: Any) -> bool:
    """Return True for non-empty strings."""

    return (
        isinstance(value, str)
        and bool(value.strip())
    )


def _is_non_negative_integer(value: Any) -> bool:
    """Return True for non-negative integers excluding booleans."""

    return (
        isinstance(value, int)
        and not isinstance(value, bool)
        and value >= 0
    )


def _is_finite_number(value: Any) -> bool:
    """Return True for safely representable finite JSON numbers."""

    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
    ):
        return False

    try:
        converted = float(value)
    except (OverflowError, TypeError, ValueError):
        return False

    return math.isfinite(converted)


def _is_hex(value: Any, length: int) -> bool:
    """Return True for hexadecimal strings of an exact length."""

    if (
        not isinstance(value, str)
        or len(value) != length
    ):
        return False

    try:
        int(value, 16)
    except ValueError:
        return False

    return True


def _is_sha256(value: Any) -> bool:
    """Return True for a SHA-256 string."""

    return _is_hex(value, 64)


def _is_code_sha(value: Any) -> bool:
    """Return True for a full Git commit SHA."""

    return _is_hex(value, 40)


def _is_uri(value: Any) -> bool:
    """Return True for an explicit URI, never a bare filename."""

    if (
        not _is_non_empty_string(value)
        or any(character.isspace() for character in value)
    ):
        return False

    # ``urlparse`` treats ``C:\\path`` as scheme ``c`` and can raise for
    # malformed bracketed hosts. Neither case is an acceptable registry URI.
    if (
        len(value) >= 2
        and value[0].isalpha()
        and value[1] == ":"
    ):
        return False

    try:
        parsed = urlparse(value)
    except ValueError:
        return False

    return (
        bool(parsed.scheme)
        and bool(parsed.netloc or parsed.path)
    )


def _valid_id_list(value: Any) -> bool:
    """Return True for a duplicate-free list of non-empty IDs."""

    return (
        isinstance(value, list)
        and all(
            _is_non_empty_string(item)
            for item in value
        )
        and len(value) == len(set(value))
    )


def _validate_lifecycle(
    record: Mapping[str, Any],
    label: str,
    rejections: list[RolloutRegistryRejection],
) -> str | None:
    """Validate Step 1.2 lifecycle names and semantics."""

    missing = _missing_fields(
        record,
        (
            "status",
            "exclusion_reason",
            "superseded_by",
        ),
    )

    if missing:
        _add_rejection(
            rejections,
            RolloutRegistryRejectionCode.INVALID_LIFECYCLE,
            f"{label} is missing lifecycle fields: " + ", ".join(missing),
        )
        return None

    status = record["status"]
    exclusion_reason = record["exclusion_reason"]
    superseded_by = record["superseded_by"]

    if (
        not isinstance(status, str)
        or status not in LIFECYCLE_VALUES
    ):
        _add_rejection(
            rejections,
            RolloutRegistryRejectionCode.INVALID_LIFECYCLE,
            f"{label}.status must be accepted, excluded, or superseded.",
        )
        return None

    if status == ArtifactStatus.ACCEPTED.value:
        if exclusion_reason is not None or superseded_by is not None:
            _add_rejection(
                rejections,
                RolloutRegistryRejectionCode.INVALID_LIFECYCLE,
                f"{label} accepted lifecycle metadata is inconsistent.",
            )

    elif status == ArtifactStatus.EXCLUDED.value:
        if (
            not _is_non_empty_string(exclusion_reason)
            or superseded_by is not None
        ):
            _add_rejection(
                rejections,
                RolloutRegistryRejectionCode.INVALID_LIFECYCLE,
                f"{label} excluded records require only exclusion_reason.",
            )

    elif (
        exclusion_reason is not None
        or not _is_non_empty_string(superseded_by)
    ):
        _add_rejection(
            rejections,
            RolloutRegistryRejectionCode.INVALID_LIFECYCLE,
            f"{label} superseded records require only superseded_by.",
        )

    return status


def _lineage_has_cycle(
    start_id: str,
    parent_by_id: Mapping[str, str | None],
) -> bool:
    """Return True if following parent links reaches a cycle."""

    seen: set[str] = set()
    current: str | None = start_id

    while current is not None:
        if current in seen:
            return True

        seen.add(current)
        current = parent_by_id.get(current)

    return False


def validate_rollout_registry_bundle(
    rollout_manifest: Mapping[str, Any],
    registry: Mapping[str, Any],
) -> RolloutRegistryValidationResult:
    """Validate the Step 1.6 rollout manifest and registry together."""

    rejections: list[RolloutRegistryRejection] = []

    if not isinstance(rollout_manifest, Mapping):
        _add_rejection(
            rejections,
            RolloutRegistryRejectionCode.MISSING_REQUIRED_FIELD,
            "rollout_manifest must be a mapping.",
        )

    if not isinstance(registry, Mapping):
        _add_rejection(
            rejections,
            RolloutRegistryRejectionCode.MISSING_REQUIRED_FIELD,
            "registry must be a mapping.",
        )

    if rejections:
        return RolloutRegistryValidationResult(
            accepted=False,
            rejections=tuple(rejections),
        )

    manifest_required = (
        "schema_version",
        "manifest_id",
        "handoff_id",
        "rollout_rows",
    )

    registry_required = (
        "schema_version",
        "registry_id",
        "handoff_id",
        "runs",
        "artifacts",
    )

    manifest_missing = _missing_fields(
        rollout_manifest,
        manifest_required,
    )
    registry_missing = _missing_fields(
        registry,
        registry_required,
    )

    if manifest_missing:
        _add_rejection(
            rejections,
            RolloutRegistryRejectionCode.MISSING_REQUIRED_FIELD,
            "rollout_manifest is missing: " + ", ".join(manifest_missing),
        )

    if registry_missing:
        _add_rejection(
            rejections,
            RolloutRegistryRejectionCode.MISSING_REQUIRED_FIELD,
            "registry is missing: " + ", ".join(registry_missing),
        )

    if rejections:
        return RolloutRegistryValidationResult(
            accepted=False,
            rejections=tuple(rejections),
        )

    for label, value in (
        ("rollout_manifest", rollout_manifest),
        ("registry", registry),
    ):
        if value["schema_version"] != ROLLOUT_REGISTRY_SCHEMA_VERSION:
            _add_rejection(
                rejections,
                RolloutRegistryRejectionCode.INVALID_SCHEMA_VERSION,
                f"{label}.schema_version must equal "
                f"{ROLLOUT_REGISTRY_SCHEMA_VERSION!r}.",
            )

    for label, field, value in (
        ("rollout_manifest", "manifest_id", rollout_manifest["manifest_id"]),
        ("rollout_manifest", "handoff_id", rollout_manifest["handoff_id"]),
        ("registry", "registry_id", registry["registry_id"]),
        ("registry", "handoff_id", registry["handoff_id"]),
    ):
        if not _is_non_empty_string(value):
            _add_rejection(
                rejections,
                RolloutRegistryRejectionCode.MISSING_REQUIRED_FIELD,
                f"{label}.{field} must be a non-empty string.",
            )

    if rollout_manifest["handoff_id"] != registry["handoff_id"]:
        _add_rejection(
            rejections,
            RolloutRegistryRejectionCode.METADATA_MISMATCH,
            "Rollout manifest and registry handoff IDs do not match.",
        )

    # ------------------------------------------------------------------
    # Run registry
    # ------------------------------------------------------------------

    runs = registry["runs"]
    run_by_id: dict[str, Mapping[str, Any]] = {}
    parent_by_run: dict[str, str | None] = {}
    run_inputs: dict[str, list[str]] = {}
    run_outputs: dict[str, list[str]] = {}

    if not isinstance(runs, list):
        _add_rejection(
            rejections,
            RolloutRegistryRejectionCode.INVALID_RUN_RECORD,
            "registry.runs must be a list.",
        )
        runs = []

    required_run_fields = (
        "run_id",
        "command",
        "owner",
        "parent_run_id",
        "input_artifact_ids",
        "output_artifact_ids",
        "code_sha",
        "config_hash",
        "model_hash",
        "preprocess_hash",
        "execution_status",
        "failure_reason",
    )

    for run_index, run in enumerate(runs):
        label = f"runs[{run_index}]"

        if not isinstance(run, Mapping):
            _add_rejection(
                rejections,
                RolloutRegistryRejectionCode.INVALID_RUN_RECORD,
                f"{label} must be a mapping.",
            )
            continue

        missing = _missing_fields(run, required_run_fields)

        if missing:
            _add_rejection(
                rejections,
                RolloutRegistryRejectionCode.INVALID_RUN_RECORD,
                f"{label} is missing: " + ", ".join(missing),
            )
            continue

        run_id = run["run_id"]

        if not _is_non_empty_string(run_id):
            _add_rejection(
                rejections,
                RolloutRegistryRejectionCode.INVALID_RUN_RECORD,
                f"{label}.run_id must be a non-empty string.",
            )
            continue

        if run_id in run_by_id:
            _add_rejection(
                rejections,
                RolloutRegistryRejectionCode.DUPLICATE_RUN_ID,
                f"Duplicate immutable run identity {run_id!r}.",
            )
            continue

        run_by_id[run_id] = run

        command = run["command"]
        if (
            not isinstance(command, list)
            or not command
            or not all(_is_non_empty_string(part) for part in command)
        ):
            _add_rejection(
                rejections,
                RolloutRegistryRejectionCode.INVALID_RUN_RECORD,
                f"Run {run_id!r}.command must be a non-empty string list.",
            )

        if not _is_non_empty_string(run["owner"]):
            _add_rejection(
                rejections,
                RolloutRegistryRejectionCode.INVALID_RUN_RECORD,
                f"Run {run_id!r}.owner must be a non-empty string.",
            )

        parent_run_id = run["parent_run_id"]
        if (
            parent_run_id is not None
            and not _is_non_empty_string(parent_run_id)
        ):
            _add_rejection(
                rejections,
                RolloutRegistryRejectionCode.INVALID_PARENT_LINEAGE,
                f"Run {run_id!r}.parent_run_id must be null or a run ID.",
            )
        else:
            parent_by_run[run_id] = parent_run_id

        for field, destination in (
            ("input_artifact_ids", run_inputs),
            ("output_artifact_ids", run_outputs),
        ):
            value = run[field]
            if not _valid_id_list(value):
                _add_rejection(
                    rejections,
                    RolloutRegistryRejectionCode.INVALID_RUN_RECORD,
                    f"Run {run_id!r}.{field} must be a duplicate-free ID list.",
                )
            else:
                destination[run_id] = list(value)

        if (
            run_id in run_inputs
            and run_id in run_outputs
            and set(run_inputs[run_id]) & set(run_outputs[run_id])
        ):
            _add_rejection(
                rejections,
                RolloutRegistryRejectionCode.LINEAGE_MISMATCH,
                f"Run {run_id!r} cannot treat one artifact as input and output.",
            )

        if not _is_code_sha(run["code_sha"]):
            _add_rejection(
                rejections,
                RolloutRegistryRejectionCode.INVALID_HASH,
                f"Run {run_id!r}.code_sha must be a full Git SHA.",
            )

        for field in ("config_hash", "model_hash", "preprocess_hash"):
            if not _is_sha256(run[field]):
                _add_rejection(
                    rejections,
                    RolloutRegistryRejectionCode.INVALID_HASH,
                    f"Run {run_id!r}.{field} must be a SHA-256 value.",
                )

        execution_status = run["execution_status"]
        if (
            not isinstance(execution_status, str)
            or execution_status not in ALLOWED_RUN_STATUSES
        ):
            _add_rejection(
                rejections,
                RolloutRegistryRejectionCode.INVALID_RUN_RECORD,
                f"Run {run_id!r} has invalid execution_status.",
            )
        elif execution_status == "completed":
            if run["failure_reason"] is not None:
                _add_rejection(
                    rejections,
                    RolloutRegistryRejectionCode.INVALID_RUN_RECORD,
                    f"Completed run {run_id!r} cannot have failure_reason.",
                )
        elif not _is_non_empty_string(run["failure_reason"]):
            _add_rejection(
                rejections,
                RolloutRegistryRejectionCode.INVALID_RUN_RECORD,
                f"Non-complete run {run_id!r} requires failure_reason.",
            )

    for run_id, parent_run_id in parent_by_run.items():
        if parent_run_id is not None and parent_run_id not in run_by_id:
            _add_rejection(
                rejections,
                RolloutRegistryRejectionCode.INVALID_PARENT_LINEAGE,
                f"Run {run_id!r} references unknown parent {parent_run_id!r}.",
            )
        elif parent_run_id == run_id:
            _add_rejection(
                rejections,
                RolloutRegistryRejectionCode.INVALID_PARENT_LINEAGE,
                f"Run {run_id!r} cannot be its own parent.",
            )
        elif _lineage_has_cycle(run_id, parent_by_run):
            _add_rejection(
                rejections,
                RolloutRegistryRejectionCode.INVALID_PARENT_LINEAGE,
                f"Run lineage containing {run_id!r} has a cycle.",
            )

    # ------------------------------------------------------------------
    # Artifact registry
    # ------------------------------------------------------------------

    artifacts = registry["artifacts"]
    artifact_by_id: dict[str, Mapping[str, Any]] = {}
    artifact_status: dict[str, str] = {}
    superseded_artifacts: dict[str, str | None] = {}

    if not isinstance(artifacts, list):
        _add_rejection(
            rejections,
            RolloutRegistryRejectionCode.INVALID_ARTIFACT_RECORD,
            "registry.artifacts must be a list.",
        )
        artifacts = []

    required_artifact_fields = (
        "schema_version",
        "artifact_id",
        "artifact_type",
        "uri",
        "sha256",
        "producer_run_id",
        "status",
        "exclusion_reason",
        "superseded_by",
    )

    for artifact_index, artifact in enumerate(artifacts):
        label = f"artifacts[{artifact_index}]"

        if not isinstance(artifact, Mapping):
            _add_rejection(
                rejections,
                RolloutRegistryRejectionCode.INVALID_ARTIFACT_RECORD,
                f"{label} must be a mapping.",
            )
            continue

        missing = _missing_fields(artifact, required_artifact_fields)
        if missing:
            _add_rejection(
                rejections,
                RolloutRegistryRejectionCode.INVALID_ARTIFACT_RECORD,
                f"{label} is missing: " + ", ".join(missing),
            )
            continue

        artifact_id = artifact["artifact_id"]
        if not _is_non_empty_string(artifact_id):
            _add_rejection(
                rejections,
                RolloutRegistryRejectionCode.INVALID_ARTIFACT_RECORD,
                f"{label}.artifact_id must be a non-empty string.",
            )
            continue

        if artifact_id in artifact_by_id:
            _add_rejection(
                rejections,
                RolloutRegistryRejectionCode.DUPLICATE_ARTIFACT_ID,
                f"Duplicate artifact identity {artifact_id!r}.",
            )
            continue

        artifact_by_id[artifact_id] = artifact

        if artifact["schema_version"] != ROLLOUT_REGISTRY_SCHEMA_VERSION:
            _add_rejection(
                rejections,
                RolloutRegistryRejectionCode.INVALID_SCHEMA_VERSION,
                f"Artifact {artifact_id!r} has invalid schema_version.",
            )

        artifact_type = artifact["artifact_type"]
        if (
            not isinstance(artifact_type, str)
            or artifact_type not in ALLOWED_ARTIFACT_TYPES
        ):
            _add_rejection(
                rejections,
                RolloutRegistryRejectionCode.INVALID_ARTIFACT_RECORD,
                f"Artifact {artifact_id!r} has invalid artifact_type.",
            )

        if not _is_uri(artifact["uri"]):
            _add_rejection(
                rejections,
                RolloutRegistryRejectionCode.INVALID_URI,
                f"Artifact {artifact_id!r}.uri must be an explicit URI.",
            )

        if not _is_sha256(artifact["sha256"]):
            _add_rejection(
                rejections,
                RolloutRegistryRejectionCode.INVALID_HASH,
                f"Artifact {artifact_id!r}.sha256 is invalid.",
            )

        if not _is_non_empty_string(artifact["producer_run_id"]):
            _add_rejection(
                rejections,
                RolloutRegistryRejectionCode.INVALID_ARTIFACT_RECORD,
                f"Artifact {artifact_id!r}.producer_run_id is invalid.",
            )

        lifecycle = _validate_lifecycle(
            artifact,
            f"Artifact {artifact_id!r}",
            rejections,
        )
        if lifecycle is not None:
            artifact_status[artifact_id] = lifecycle
            superseded_artifacts[artifact_id] = (
                artifact["superseded_by"]
                if (
                    lifecycle == ArtifactStatus.SUPERSEDED.value
                    and _is_non_empty_string(artifact["superseded_by"])
                )
                else None
            )

    for artifact_id, artifact in artifact_by_id.items():
        producer_run_id = artifact.get("producer_run_id")
        if (
            _is_non_empty_string(producer_run_id)
            and producer_run_id not in run_by_id
        ):
            _add_rejection(
                rejections,
                RolloutRegistryRejectionCode.MISSING_REGISTRY_REFERENCE,
                f"Artifact {artifact_id!r} references unknown producer run.",
            )
        elif (
            _is_non_empty_string(producer_run_id)
            and artifact_id not in run_outputs.get(producer_run_id, [])
        ):
            _add_rejection(
                rejections,
                RolloutRegistryRejectionCode.LINEAGE_MISMATCH,
                f"Producer run {producer_run_id!r} does not list "
                f"artifact {artifact_id!r} as output.",
            )

    for run_id, input_ids in run_inputs.items():
        for artifact_id in input_ids:
            if artifact_id not in artifact_by_id:
                _add_rejection(
                    rejections,
                    RolloutRegistryRejectionCode.MISSING_REGISTRY_REFERENCE,
                    f"Run {run_id!r} references unknown input {artifact_id!r}.",
                )
            elif artifact_by_id[artifact_id].get("producer_run_id") == run_id:
                _add_rejection(
                    rejections,
                    RolloutRegistryRejectionCode.LINEAGE_MISMATCH,
                    f"Run {run_id!r} cannot produce its own direct input.",
                )

    for run_id, output_ids in run_outputs.items():
        for artifact_id in output_ids:
            if artifact_id not in artifact_by_id:
                _add_rejection(
                    rejections,
                    RolloutRegistryRejectionCode.MISSING_REGISTRY_REFERENCE,
                    f"Run {run_id!r} references unknown output {artifact_id!r}.",
                )
            elif artifact_by_id[artifact_id].get("producer_run_id") != run_id:
                _add_rejection(
                    rejections,
                    RolloutRegistryRejectionCode.LINEAGE_MISMATCH,
                    f"Run {run_id!r} does not own output {artifact_id!r}.",
                )

    for artifact_id, replacement_id in superseded_artifacts.items():
        if replacement_id is None:
            continue

        if replacement_id not in artifact_by_id:
            _add_rejection(
                rejections,
                RolloutRegistryRejectionCode.INVALID_SUPERSESSION,
                f"Artifact {artifact_id!r} references unknown replacement.",
            )
        elif replacement_id == artifact_id:
            _add_rejection(
                rejections,
                RolloutRegistryRejectionCode.INVALID_SUPERSESSION,
                f"Artifact {artifact_id!r} cannot supersede itself.",
            )
        elif (
            artifact_by_id[replacement_id].get("artifact_type")
            != artifact_by_id[artifact_id].get("artifact_type")
        ):
            _add_rejection(
                rejections,
                RolloutRegistryRejectionCode.INVALID_SUPERSESSION,
                f"Artifact {artifact_id!r} replacement has a different type.",
            )
        elif _lineage_has_cycle(artifact_id, superseded_artifacts):
            _add_rejection(
                rejections,
                RolloutRegistryRejectionCode.INVALID_SUPERSESSION,
                f"Artifact supersession containing {artifact_id!r} has a cycle.",
            )

    # ------------------------------------------------------------------
    # Rollout manifest rows and registry joins
    # ------------------------------------------------------------------

    rollout_rows = rollout_manifest["rollout_rows"]
    rollout_by_id: dict[str, Mapping[str, Any]] = {}
    rollout_status: dict[str, str] = {}
    superseded_rollouts: dict[str, str | None] = {}

    if not isinstance(rollout_rows, list):
        _add_rejection(
            rejections,
            RolloutRegistryRejectionCode.INVALID_ROLLOUT_ROW,
            "rollout_manifest.rollout_rows must be a list.",
        )
        rollout_rows = []

    required_rollout_fields = (
        "schema_version",
        "rollout_id",
        "event_id",
        "episode_id",
        "trajectory_id",
        "server_tick",
        "render_frame_idx",
        "action_idx",
        "layout_id",
        "model_frame_idx",
        "regime",
        "visibility",
        "tau",
        "v",
        "q",
        "duration",
        "seed",
        "dose_id",
        "alpha_requested",
        "alpha_applied",
        "cap_reduced",
        "intended_block_shift",
        "direction_version",
        "layer_idx",
        "hook_site",
        "timestep_idx",
        "control_type",
        "input_context_id",
        "input_context_artifact_id",
        "input_context_hash",
        "intervention_request_artifact_id",
        "output_artifact_id",
        "output_uri",
        "output_hash",
        "code_sha",
        "model_hash",
        "config_hash",
        "preprocess_hash",
        "run_id",
        "outcome",
        "outcome_detail",
        "measurable",
        "status",
        "exclusion_reason",
        "superseded_by",
    )

    for row_index, row in enumerate(rollout_rows):
        label = f"rollout_rows[{row_index}]"

        if not isinstance(row, Mapping):
            _add_rejection(
                rejections,
                RolloutRegistryRejectionCode.INVALID_ROLLOUT_ROW,
                f"{label} must be a mapping.",
            )
            continue

        missing = _missing_fields(row, required_rollout_fields)
        if missing:
            _add_rejection(
                rejections,
                RolloutRegistryRejectionCode.INVALID_ROLLOUT_ROW,
                f"{label} is missing: " + ", ".join(missing),
            )
            continue

        rollout_id = row["rollout_id"]
        if not _is_non_empty_string(rollout_id):
            _add_rejection(
                rejections,
                RolloutRegistryRejectionCode.INVALID_ROLLOUT_ROW,
                f"{label}.rollout_id must be a non-empty string.",
            )
            continue

        if rollout_id in rollout_by_id:
            _add_rejection(
                rejections,
                RolloutRegistryRejectionCode.DUPLICATE_ROLLOUT_ID,
                f"Duplicate rollout identity {rollout_id!r}.",
            )
            continue

        rollout_by_id[rollout_id] = row

        try:
            validate_identity(row)
        except (
            IdentityValidationError,
            OverflowError,
            TypeError,
            ValueError,
        ) as error:
            _add_rejection(
                rejections,
                RolloutRegistryRejectionCode.INVALID_ROLLOUT_ROW,
                f"Rollout {rollout_id!r} has invalid universal identity: "
                f"{error}",
            )

        if row["schema_version"] != ROLLOUT_REGISTRY_SCHEMA_VERSION:
            _add_rejection(
                rejections,
                RolloutRegistryRejectionCode.INVALID_SCHEMA_VERSION,
                f"Rollout {rollout_id!r} has invalid schema_version.",
            )

        for field in (
            "event_id",
            "episode_id",
            "trajectory_id",
            "layout_id",
            "dose_id",
            "direction_version",
            "hook_site",
            "input_context_id",
            "input_context_artifact_id",
            "intervention_request_artifact_id",
            "run_id",
        ):
            if not _is_non_empty_string(row[field]):
                _add_rejection(
                    rejections,
                    RolloutRegistryRejectionCode.INVALID_ROLLOUT_ROW,
                    f"Rollout {rollout_id!r}.{field} must be non-empty.",
                )

        for field in ("model_frame_idx", "seed", "layer_idx", "timestep_idx"):
            if not _is_non_negative_integer(row[field]):
                _add_rejection(
                    rejections,
                    RolloutRegistryRejectionCode.INVALID_ROLLOUT_ROW,
                    f"Rollout {rollout_id!r}.{field} must be non-negative int.",
                )

        if (
            _is_non_negative_integer(row["layer_idx"])
            and row["layer_idx"] >= MINEWORLD_LAYER_COUNT
        ):
            _add_rejection(
                rejections,
                RolloutRegistryRejectionCode.INVALID_ROLLOUT_ROW,
                f"Rollout {rollout_id!r}.layer_idx is outside the model.",
            )

        if (
            _is_non_negative_integer(row["timestep_idx"])
            and row["timestep_idx"] >= MINEWORLD_MODEL_FRAME_COUNT
        ):
            _add_rejection(
                rejections,
                RolloutRegistryRejectionCode.INVALID_ROLLOUT_ROW,
                f"Rollout {rollout_id!r}.timestep_idx is outside context.",
            )

        alpha_fields_valid = all(
            _is_finite_number(row[field])
            for field in (
                "alpha_requested",
                "alpha_applied",
                "intended_block_shift",
            )
        )

        if not alpha_fields_valid:
            _add_rejection(
                rejections,
                RolloutRegistryRejectionCode.INVALID_ROLLOUT_ROW,
                f"Rollout {rollout_id!r} alpha/shift values must be finite.",
            )

        if not isinstance(row["cap_reduced"], bool):
            _add_rejection(
                rejections,
                RolloutRegistryRejectionCode.INVALID_ROLLOUT_ROW,
                f"Rollout {rollout_id!r}.cap_reduced must be boolean.",
            )
        elif alpha_fields_valid:
            requested = float(row["alpha_requested"])
            applied = float(row["alpha_applied"])

            if row["cap_reduced"]:
                if abs(applied) >= abs(requested):
                    _add_rejection(
                        rejections,
                        RolloutRegistryRejectionCode.INVALID_ROLLOUT_ROW,
                        f"Rollout {rollout_id!r} has inconsistent cap reduction.",
                    )
                if (
                    requested != 0.0
                    and applied != 0.0
                    and math.copysign(1.0, requested)
                    != math.copysign(1.0, applied)
                ):
                    _add_rejection(
                        rejections,
                        RolloutRegistryRejectionCode.INVALID_ROLLOUT_ROW,
                        f"Rollout {rollout_id!r} reverses alpha sign.",
                    )
            elif not math.isclose(
                requested,
                applied,
                rel_tol=1e-12,
                abs_tol=1e-12,
            ):
                _add_rejection(
                    rejections,
                    RolloutRegistryRejectionCode.INVALID_ROLLOUT_ROW,
                    f"Rollout {rollout_id!r} has an unflagged alpha change.",
                )

        control_type = row["control_type"]
        if (
            not isinstance(control_type, str)
            or control_type not in ALLOWED_CONTROL_TYPES
        ):
            _add_rejection(
                rejections,
                RolloutRegistryRejectionCode.INVALID_ROLLOUT_ROW,
                f"Rollout {rollout_id!r} has invalid control_type.",
            )
        elif (
            control_type == "alpha_zero"
            and alpha_fields_valid
            and (
                any(
                    float(row[field]) != 0.0
                    for field in (
                        "alpha_requested",
                        "alpha_applied",
                        "intended_block_shift",
                    )
                )
                or row["cap_reduced"] is not False
            )
        ):
            _add_rejection(
                rejections,
                RolloutRegistryRejectionCode.INVALID_ROLLOUT_ROW,
                f"Rollout {rollout_id!r} alpha-zero control is inconsistent.",
            )

        for field in (
            "input_context_hash",
            "model_hash",
            "config_hash",
            "preprocess_hash",
        ):
            if not _is_sha256(row[field]):
                _add_rejection(
                    rejections,
                    RolloutRegistryRejectionCode.INVALID_HASH,
                    f"Rollout {rollout_id!r}.{field} must be SHA-256.",
                )

        outcome = row["outcome"]
        outcome_valid = (
            isinstance(outcome, str)
            and outcome in ALLOWED_OUTCOMES
        )
        if not outcome_valid:
            _add_rejection(
                rejections,
                RolloutRegistryRejectionCode.INVALID_OUTCOME,
                f"Rollout {rollout_id!r} has invalid outcome.",
            )

        lifecycle = _validate_lifecycle(
            row,
            f"Rollout {rollout_id!r}",
            rejections,
        )
        if lifecycle is not None:
            rollout_status[rollout_id] = lifecycle
            superseded_rollouts[rollout_id] = (
                row["superseded_by"]
                if (
                    lifecycle == ArtifactStatus.SUPERSEDED.value
                    and _is_non_empty_string(row["superseded_by"])
                )
                else None
            )

        if not isinstance(row["measurable"], bool):
            _add_rejection(
                rejections,
                RolloutRegistryRejectionCode.INVALID_OUTCOME,
                f"Rollout {rollout_id!r}.measurable must be boolean.",
            )

        forbidden = sorted(
            field
            for field in FORBIDDEN_MEASUREMENT_FIELDS
            if field in row
        )
        if forbidden:
            _add_rejection(
                rejections,
                RolloutRegistryRejectionCode.DISPLACEMENT_ENCODING_FORBIDDEN,
                f"Rollout {rollout_id!r} contains Person E fields: "
                + ", ".join(forbidden),
            )

        if outcome_valid and outcome in OUTPUT_BEARING_OUTCOMES:
            if (
                not _is_non_empty_string(row["output_artifact_id"])
                or not _is_uri(row["output_uri"])
                or not _is_sha256(row["output_hash"])
            ):
                _add_rejection(
                    rejections,
                    RolloutRegistryRejectionCode.OUTCOME_OUTPUT_MISMATCH,
                    f"Rollout {rollout_id!r} outcome requires clip output.",
                )

            if outcome == "measurable_continuation":
                if row["outcome_detail"] is not None:
                    _add_rejection(
                        rejections,
                        RolloutRegistryRejectionCode.INVALID_OUTCOME,
                        f"Rollout {rollout_id!r} continuation detail must be null.",
                    )
            elif not _is_non_empty_string(row["outcome_detail"]):
                _add_rejection(
                    rejections,
                    RolloutRegistryRejectionCode.INVALID_OUTCOME,
                    f"Rollout {rollout_id!r} non-persistence requires detail.",
                )

        elif outcome_valid and outcome == "generation_failure":
            if any(
                row[field] is not None
                for field in (
                    "output_artifact_id",
                    "output_uri",
                    "output_hash",
                )
            ):
                _add_rejection(
                    rejections,
                    RolloutRegistryRejectionCode.OUTCOME_OUTPUT_MISMATCH,
                    f"Rollout {rollout_id!r} failure cannot claim clip output.",
                )

            if not _is_non_empty_string(row["outcome_detail"]):
                _add_rejection(
                    rejections,
                    RolloutRegistryRejectionCode.INVALID_OUTCOME,
                    f"Rollout {rollout_id!r} failure requires detail.",
                )

            if lifecycle != ArtifactStatus.EXCLUDED.value:
                _add_rejection(
                    rejections,
                    RolloutRegistryRejectionCode.GENERATION_STATUS_MISMATCH,
                    f"Rollout {rollout_id!r} generation failure must be excluded.",
                )

        if (
            lifecycle is not None
            and isinstance(row["measurable"], bool)
                and outcome_valid
            ):
            expected_measurable = (
                lifecycle == ArtifactStatus.ACCEPTED.value
                and outcome == "measurable_continuation"
            )
            if row["measurable"] != expected_measurable:
                _add_rejection(
                    rejections,
                    RolloutRegistryRejectionCode.GENERATION_STATUS_MISMATCH,
                    f"Rollout {rollout_id!r}.measurable conflicts with outcome/status.",
                )

        # Registry references and provenance joins.
        run_id = row["run_id"]
        run = run_by_id.get(run_id) if isinstance(run_id, str) else None
        if run is None:
            _add_rejection(
                rejections,
                RolloutRegistryRejectionCode.MISSING_REGISTRY_REFERENCE,
                f"Rollout {rollout_id!r} references unknown producing run.",
            )
        else:
            for field in (
                "code_sha",
                "model_hash",
                "config_hash",
                "preprocess_hash",
            ):
                if row[field] != run.get(field):
                    _add_rejection(
                        rejections,
                        RolloutRegistryRejectionCode.METADATA_MISMATCH,
                        f"Rollout {rollout_id!r}.{field} disagrees with run.",
                    )

            execution_status = run.get("execution_status")
            if outcome_valid and (
                (
                    outcome in OUTPUT_BEARING_OUTCOMES
                    and execution_status == "failed"
                )
                or (
                    outcome == "generation_failure"
                    and execution_status
                    not in {"failed", "completed_with_failures"}
                )
            ):
                _add_rejection(
                    rejections,
                    RolloutRegistryRejectionCode.GENERATION_STATUS_MISMATCH,
                    f"Rollout {rollout_id!r} conflicts with run execution status.",
                )

        context_id = row["input_context_artifact_id"]
        context = (
            artifact_by_id.get(context_id)
            if isinstance(context_id, str)
            else None
        )
        if context is None:
            _add_rejection(
                rejections,
                RolloutRegistryRejectionCode.MISSING_REGISTRY_REFERENCE,
                f"Rollout {rollout_id!r} references unknown input context.",
            )
        else:
            if (
                context.get("artifact_type") != "input_context"
                or context.get("sha256") != row["input_context_hash"]
                or artifact_status.get(context_id) != ArtifactStatus.ACCEPTED.value
            ):
                _add_rejection(
                    rejections,
                    RolloutRegistryRejectionCode.METADATA_MISMATCH,
                    f"Rollout {rollout_id!r} input context provenance disagrees.",
                )
            if run is not None and context_id not in run_inputs.get(run_id, []):
                _add_rejection(
                    rejections,
                    RolloutRegistryRejectionCode.LINEAGE_MISMATCH,
                    f"Rollout run {run_id!r} does not list its input context.",
                )

        request_artifact_id = row["intervention_request_artifact_id"]
        request_artifact = (
            artifact_by_id.get(request_artifact_id)
            if isinstance(request_artifact_id, str)
            else None
        )
        if request_artifact is None:
            _add_rejection(
                rejections,
                RolloutRegistryRejectionCode.MISSING_REGISTRY_REFERENCE,
                f"Rollout {rollout_id!r} references unknown intervention request.",
            )
        else:
            if (
                request_artifact.get("artifact_type") != "intervention_request"
                or artifact_status.get(request_artifact_id)
                != ArtifactStatus.ACCEPTED.value
            ):
                _add_rejection(
                    rejections,
                    RolloutRegistryRejectionCode.METADATA_MISMATCH,
                    f"Rollout {rollout_id!r} request artifact is incompatible.",
                )
            if (
                run is not None
                and request_artifact_id not in run_inputs.get(run_id, [])
            ):
                _add_rejection(
                    rejections,
                    RolloutRegistryRejectionCode.LINEAGE_MISMATCH,
                    f"Rollout run {run_id!r} does not list intervention request.",
                )

        output_id = row["output_artifact_id"]
        if (
            outcome_valid
            and outcome in OUTPUT_BEARING_OUTCOMES
            and isinstance(output_id, str)
        ):
            output = artifact_by_id.get(output_id)
            if output is None:
                _add_rejection(
                    rejections,
                    RolloutRegistryRejectionCode.MISSING_REGISTRY_REFERENCE,
                    f"Rollout {rollout_id!r} references unknown output artifact.",
                )
            else:
                if (
                    output.get("artifact_type") != "rollout_clip"
                    or output.get("uri") != row["output_uri"]
                    or output.get("sha256") != row["output_hash"]
                    or output.get("producer_run_id") != run_id
                    or artifact_status.get(output_id) != lifecycle
                ):
                    _add_rejection(
                        rejections,
                        RolloutRegistryRejectionCode.METADATA_MISMATCH,
                        f"Rollout {rollout_id!r} output provenance disagrees.",
                    )

    for rollout_id, replacement_id in superseded_rollouts.items():
        if replacement_id is None:
            continue

        if replacement_id not in rollout_by_id:
            _add_rejection(
                rejections,
                RolloutRegistryRejectionCode.INVALID_SUPERSESSION,
                f"Rollout {rollout_id!r} references unknown replacement.",
            )
        elif replacement_id == rollout_id:
            _add_rejection(
                rejections,
                RolloutRegistryRejectionCode.INVALID_SUPERSESSION,
                f"Rollout {rollout_id!r} cannot supersede itself.",
            )
        elif (
            rollout_by_id[replacement_id].get("event_id")
            != rollout_by_id[rollout_id].get("event_id")
        ):
            _add_rejection(
                rejections,
                RolloutRegistryRejectionCode.INVALID_SUPERSESSION,
                f"Rollout {rollout_id!r} replacement changes event identity.",
            )
        elif _lineage_has_cycle(rollout_id, superseded_rollouts):
            _add_rejection(
                rejections,
                RolloutRegistryRejectionCode.INVALID_SUPERSESSION,
                f"Rollout supersession containing {rollout_id!r} has a cycle.",
            )

    return RolloutRegistryValidationResult(
        accepted=not rejections,
        rejections=tuple(rejections),
    )


# Compatible Phase 1.2 extension. The frozen A-to-E rollout bundle above
# remains schema 1.0 and keeps its existing validator. This sub-schema is the
# one shared authority for richer immutable run/artifact lineage; E owns its
# data model while A orchestration may call it without redefining rollout
# identity.
IMMUTABLE_REGISTRY_SCHEMA_VERSION = "mineocclude-immutable-registry-v1.0"
IMMUTABLE_REGISTRY_V2_SCHEMA_VERSION = "mineocclude-immutable-registry-v2.0"

IMMUTABLE_RUN_STATUSES = frozenset({"in_progress", "completed", "failed"})
IMMUTABLE_ARTIFACT_STATUSES = frozenset(
    {"accepted", "excluded", "superseded"}
)
IMMUTABLE_V2_RUN_STATUSES = frozenset(
    {"pending", "running", "completed", "failed"}
)
IMMUTABLE_V2_OWNER_IDS = frozenset(
    {"person_a", "person_b", "person_c", "person_d", "person_e"}
)
IMMUTABLE_V2_AUTHORITY_DECISIONS = frozenset(
    {"accepted", "excluded", "pending", "failed"}
)
IMMUTABLE_V2_OWNER_STATUSES = frozenset(
    {"pending", "accepted", "rejected", "failed", "superseded"}
)
IMMUTABLE_V2_OWNER_STATUS_DECISIONS = {
    "pending": "pending",
    "accepted": "accepted",
    "rejected": "excluded",
    "failed": "failed",
    "superseded": "excluded",
}
IMMUTABLE_V2_MANIFEST_DECISIONS = frozenset({"accepted", "excluded"})
IMMUTABLE_V2_BYTE_VERIFICATION_MODES = frozenset(
    {"local_bytes", "external_receipt"}
)
IMMUTABLE_V2_STATUS_RECORD_SCHEMA_VERSION = (
    "mineocclude-owner-status-record-v1.0"
)
IMMUTABLE_V2_STATUS_RECORD_VERIFICATION_MODES = frozenset(
    {"local_bytes", "external_receipt"}
)

IMMUTABLE_ARTIFACT_TYPES = frozenset(
    {
        # Phase 1 roadmap catalog.
        "raw_trajectory",
        "model_input",
        "oracle_target",
        "activation",
        "fitted_probe",
        "prediction",
        "baseline",
        "rollout",
        "detection",
        "metric_table",
        "figure",
        # Existing A rollout-registry types retained for compatibility.
        "input_context",
        "intervention_request",
        "rollout_clip",
        "partial_rollout",
        "diagnostic_log",
        # E-owned lineage products represented without implementing producers.
        "detector_calibration",
        "homography",
        "localization",
        "ssim",
        "measurement",
        "figure_input",
    }
)
IMMUTABLE_V2_ARTIFACT_TYPES = frozenset(
    {*IMMUTABLE_ARTIFACT_TYPES, "extraction"}
)
IMMUTABLE_V2_STEP4_ARTIFACT_TYPE_MAP = {
    "data": "raw_trajectory",
    "model_input": "model_input",
    "oracle_target": "oracle_target",
    "extraction": "extraction",
    "activation": "activation",
    "fitted_probe": "fitted_probe",
    "prediction": "prediction",
    "baseline": "baseline",
    "rollout": "rollout",
    "detection": "detection",
    "metric_table": "metric_table",
    "figure": "figure",
}
IMMUTABLE_V2_ARTIFACT_OWNER_IDS = {
    "raw_trajectory": frozenset({"person_c"}),
    "model_input": frozenset({"person_a"}),
    "oracle_target": frozenset({"person_b"}),
    "extraction": frozenset({"person_a"}),
    "activation": frozenset({"person_a"}),
    "fitted_probe": frozenset({"person_b"}),
    "prediction": frozenset({"person_b"}),
    "baseline": frozenset({"person_d"}),
    "rollout": frozenset({"person_a"}),
    "detection": frozenset({"person_e"}),
    "homography": frozenset({"person_e"}),
    "metric_table": frozenset({"person_b"}),
    "figure": frozenset({"person_e"}),
    "figure_input": frozenset({"person_e"}),
    "input_context": frozenset({"person_a"}),
    "intervention_request": frozenset({"person_a"}),
    "rollout_clip": frozenset({"person_a"}),
    "partial_rollout": frozenset({"person_a"}),
    "diagnostic_log": frozenset({"person_a"}),
    "detector_calibration": frozenset({"person_e"}),
    "localization": frozenset({"person_e"}),
    "ssim": frozenset({"person_e"}),
    "measurement": frozenset({"person_e"}),
}

_IMMUTABLE_REGISTRY_FIELDS = frozenset(
    {
        "schema_version",
        "immutable_registry_schema_version",
        "registry_id",
        "synthetic",
        "scientific_use",
        "runs",
        "artifacts",
    }
)

_IMMUTABLE_RUN_FIELDS = frozenset(
    {
        "schema_version",
        "run_id",
        "code_sha",
        "git_dirty",
        "config_snapshot_hash",
        "checkpoint_hash",
        "data_identity_hash",
        "preprocess_hash",
        "environment_hash",
        "seeds",
        "command",
        "owner",
        "started_at",
        "ended_at",
        "status",
        "parent_run_id",
        "input_artifact_ids",
        "output_artifact_ids",
        "failure_reason",
        "supersedes_run_id",
        "supersession_reason",
    }
)

_IMMUTABLE_ARTIFACT_FIELDS = frozenset(
    {
        "schema_version",
        "artifact_schema_version",
        "artifact_id",
        "direct_input_artifact_ids",
        "creator_run_id",
        "artifact_type",
        "uri",
        "sha256",
        "size_bytes",
        "status",
        "status_authority",
        "status_reason",
        "superseded_by",
    }
)


class ImmutableRegistryRejectionCode(str, Enum):
    """Stable rejection codes for the shared immutable registry."""

    INVALID_DOCUMENT = "invalid_document"
    MISSING_REQUIRED_FIELD = "missing_required_field"
    UNVERSIONED_SCHEMA_CHANGE = "unversioned_schema_change"
    UNSUPPORTED_SCHEMA_VERSION = "unsupported_schema_version"
    MISSING_RUN_ID = "missing_run_id"
    MISSING_ARTIFACT_ID = "missing_artifact_id"
    DUPLICATE_RUN_ID = "duplicate_run_id"
    DUPLICATE_ARTIFACT_ID = "duplicate_artifact_id"
    INVALID_RUN = "invalid_run"
    INVALID_ARTIFACT = "invalid_artifact"
    BROKEN_DIRECT_INPUT = "broken_direct_input"
    MISSING_CREATOR_RUN = "missing_creator_run"
    CHECKSUM_MISMATCH = "checksum_mismatch"
    ILLEGAL_RUN_STATUS_TRANSITION = "illegal_run_status_transition"
    COMPLETED_RUN_MUTATION = "completed_run_mutation"
    IMMUTABLE_ARTIFACT_MUTATION = "immutable_artifact_mutation"
    MALFORMED_SUPERSESSION = "malformed_supersession"
    AMBIGUOUS_LINEAGE = "ambiguous_lineage"
    INVALID_AUTHORITY = "invalid_authority"
    DUPLICATE_AUTHORITY_ID = "duplicate_authority_id"
    INVALID_MANIFEST = "invalid_manifest"
    DUPLICATE_MANIFEST_ID = "duplicate_manifest_id"
    INVALID_BYTE_VERIFICATION = "invalid_byte_verification"
    DUPLICATE_BYTE_VERIFICATION_ID = "duplicate_byte_verification_id"
    OWNER_AUTHORITY_MISMATCH = "owner_authority_mismatch"
    MANIFEST_MISMATCH = "manifest_mismatch"
    UNVERIFIED_ARTIFACT = "unverified_artifact"
    INVALID_TRUSTED_AUTHORITY = "invalid_trusted_authority"
    MISSING_TRUSTED_AUTHORITY = "missing_trusted_authority"
    STATUS_RECORD_VERIFICATION_FAILED = "status_record_verification_failed"
    INVALID_ARTIFACT_AUTHORIZATION = "invalid_artifact_authorization"
    MISSING_ARTIFACT_AUTHORIZATION = "missing_artifact_authorization"
    ARTIFACT_AUTHORIZATION_VERIFICATION_FAILED = (
        "artifact_authorization_verification_failed"
    )
    INVALID_TRUSTED_MANIFEST = "invalid_trusted_manifest"
    MISSING_TRUSTED_MANIFEST = "missing_trusted_manifest"
    TRUSTED_MANIFEST_MISMATCH = "trusted_manifest_mismatch"
    INVALID_TRUSTED_ARTIFACT_RECEIPT = "invalid_trusted_artifact_receipt"
    MISSING_TRUSTED_ARTIFACT_RECEIPT = "missing_trusted_artifact_receipt"
    TRUSTED_ARTIFACT_RECEIPT_MISMATCH = "trusted_artifact_receipt_mismatch"


@dataclass(frozen=True)
class ImmutableRegistryRejection:
    code: ImmutableRegistryRejectionCode
    message: str
    record_id: str | None = None


@dataclass(frozen=True)
class ImmutableRegistryValidationResult:
    accepted: bool
    rejections: tuple[ImmutableRegistryRejection, ...]


def _immutable_reject(
    rejections: list[ImmutableRegistryRejection],
    code: ImmutableRegistryRejectionCode,
    message: str,
    record_id: str | None = None,
) -> None:
    rejections.append(ImmutableRegistryRejection(code, message, record_id))


def _strict_hex(value: Any, length: int) -> bool:
    return (
        isinstance(value, str)
        and len(value) == length
        and all(character in "0123456789abcdefABCDEF" for character in value)
    )


def _strict_id_list(value: Any) -> bool:
    return (
        isinstance(value, list)
        and all(_is_non_empty_string(item) for item in value)
        and len(value) == len(set(value))
    )


def _utc_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")  # noqa: DTZ007
    except ValueError:
        return None


def _check_exact_fields(
    value: Mapping[str, Any],
    expected: frozenset[str],
    label: str,
    rejections: list[ImmutableRegistryRejection],
    record_id: str | None = None,
) -> bool:
    string_fields = {field for field in value if isinstance(field, str)}
    non_string_fields = [repr(field) for field in value if not isinstance(field, str)]
    missing = sorted(expected - string_fields)
    extra = sorted(string_fields - expected)
    if missing:
        _immutable_reject(
            rejections,
            ImmutableRegistryRejectionCode.MISSING_REQUIRED_FIELD,
            f"{label} is missing: {', '.join(missing)}.",
            record_id,
        )
    if extra:
        _immutable_reject(
            rejections,
            ImmutableRegistryRejectionCode.UNVERSIONED_SCHEMA_CHANGE,
            f"{label} has unversioned fields: {', '.join(extra)}.",
            record_id,
        )
    if non_string_fields:
        _immutable_reject(
            rejections,
            ImmutableRegistryRejectionCode.UNVERSIONED_SCHEMA_CHANGE,
            f"{label} has non-string fields: {', '.join(non_string_fields)}.",
            record_id,
        )
    return not missing and not extra and not non_string_fields


def _has_reference_cycle(
    start: str,
    parent_by_id: Mapping[str, str | None],
) -> bool:
    seen: set[str] = set()
    current: str | None = start
    while current is not None:
        if current in seen:
            return True
        seen.add(current)
        current = parent_by_id.get(current)
    return False


def _artifact_lineage_has_cycle(
    start: str,
    direct_inputs_by_id: Mapping[str, tuple[str, ...]],
) -> bool:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(artifact_id: str) -> bool:
        if artifact_id in visiting:
            return True
        if artifact_id in visited:
            return False
        visiting.add(artifact_id)
        for input_id in direct_inputs_by_id.get(artifact_id, ()):
            if visit(input_id):
                return True
        visiting.remove(artifact_id)
        visited.add(artifact_id)
        return False

    return visit(start)


def _validate_run_record(
    run: Mapping[str, Any],
    rejections: list[ImmutableRegistryRejection],
) -> bool:
    run_id = run.get("run_id") if isinstance(run.get("run_id"), str) else None
    if not _check_exact_fields(
        run, _IMMUTABLE_RUN_FIELDS, "Run record", rejections, run_id
    ):
        return False
    if not _is_non_empty_string(run["run_id"]):
        _immutable_reject(
            rejections,
            ImmutableRegistryRejectionCode.MISSING_RUN_ID,
            "run_id must be a non-empty immutable identifier.",
            run_id,
        )
    if run["schema_version"] != SCHEMA_VERSION:
        _immutable_reject(
            rejections,
            ImmutableRegistryRejectionCode.UNSUPPORTED_SCHEMA_VERSION,
            "Run schema_version is unsupported.",
            run_id,
        )
    if not _strict_hex(run["code_sha"], 40):
        _immutable_reject(
            rejections,
            ImmutableRegistryRejectionCode.INVALID_RUN,
            "Run code_sha must be an exact full hexadecimal Git SHA.",
            run_id,
        )
    if not isinstance(run["git_dirty"], bool):
        _immutable_reject(
            rejections,
            ImmutableRegistryRejectionCode.INVALID_RUN,
            "Run git_dirty must be boolean.",
            run_id,
        )
    for field in (
        "config_snapshot_hash",
        "checkpoint_hash",
        "data_identity_hash",
        "preprocess_hash",
        "environment_hash",
    ):
        if not _strict_hex(run[field], 64):
            _immutable_reject(
                rejections,
                ImmutableRegistryRejectionCode.INVALID_RUN,
                f"Run {field} must be SHA-256.",
                run_id,
            )
    seeds = run["seeds"]
    if (
        not isinstance(seeds, Mapping)
        or not seeds
        or any(not _is_non_empty_string(key) for key in seeds)
        or any(
            not isinstance(seed, int) or isinstance(seed, bool)
            for seed in seeds.values()
        )
    ):
        _immutable_reject(
            rejections,
            ImmutableRegistryRejectionCode.INVALID_RUN,
            "Run seeds must be a non-empty mapping of names to integers.",
            run_id,
        )
    command = run["command"]
    if (
        not isinstance(command, list)
        or not command
        or any(not _is_non_empty_string(part) for part in command)
    ):
        _immutable_reject(
            rejections,
            ImmutableRegistryRejectionCode.INVALID_RUN,
            "Run command must be a non-empty list of strings.",
            run_id,
        )
    if not _is_non_empty_string(run["owner"]):
        _immutable_reject(
            rejections,
            ImmutableRegistryRejectionCode.INVALID_RUN,
            "Run owner must be non-empty.",
            run_id,
        )
    started_at = _utc_timestamp(run["started_at"])
    ended_at = None if run["ended_at"] is None else _utc_timestamp(run["ended_at"])
    if started_at is None:
        _immutable_reject(
            rejections,
            ImmutableRegistryRejectionCode.INVALID_RUN,
            "Run started_at must be an explicit UTC timestamp.",
            run_id,
        )
    status = run["status"]
    if not isinstance(status, str) or status not in IMMUTABLE_RUN_STATUSES:
        _immutable_reject(
            rejections,
            ImmutableRegistryRejectionCode.INVALID_RUN,
            "Run status is unsupported.",
            run_id,
        )
    elif status == "in_progress":
        if run["ended_at"] is not None or run["failure_reason"] is not None:
            _immutable_reject(
                rejections,
                ImmutableRegistryRejectionCode.INVALID_RUN,
                "In-progress runs require null ended_at and failure_reason.",
                run_id,
            )
    else:
        if ended_at is None or (
            started_at is not None and ended_at < started_at
        ):
            _immutable_reject(
                rejections,
                ImmutableRegistryRejectionCode.INVALID_RUN,
                "Terminal runs require an ordered UTC ended_at.",
                run_id,
            )
        if status == "failed" and not _is_non_empty_string(run["failure_reason"]):
            _immutable_reject(
                rejections,
                ImmutableRegistryRejectionCode.INVALID_RUN,
                "Failed runs require a failure_reason.",
                run_id,
            )
        if status == "completed" and run["failure_reason"] is not None:
            _immutable_reject(
                rejections,
                ImmutableRegistryRejectionCode.INVALID_RUN,
                "Completed runs require null failure_reason.",
                run_id,
            )
    for field in ("input_artifact_ids", "output_artifact_ids"):
        if not _strict_id_list(run[field]):
            _immutable_reject(
                rejections,
                ImmutableRegistryRejectionCode.AMBIGUOUS_LINEAGE,
                f"Run {field} must be a duplicate-free ID list.",
                run_id,
            )
    for field in ("parent_run_id", "supersedes_run_id"):
        if run[field] is not None and not _is_non_empty_string(run[field]):
            _immutable_reject(
                rejections,
                ImmutableRegistryRejectionCode.INVALID_RUN,
                f"Run {field} must be null or a non-empty ID.",
                run_id,
            )
    if run["supersedes_run_id"] is None:
        if run["supersession_reason"] is not None:
            _immutable_reject(
                rejections,
                ImmutableRegistryRejectionCode.MALFORMED_SUPERSESSION,
                "A run without supersedes_run_id requires null supersession_reason.",
                run_id,
            )
    elif not _is_non_empty_string(run["supersession_reason"]):
        _immutable_reject(
            rejections,
            ImmutableRegistryRejectionCode.MALFORMED_SUPERSESSION,
            "A superseding run requires a non-empty supersession_reason.",
            run_id,
        )
    return True


def _validate_artifact_record(
    artifact: Mapping[str, Any],
    rejections: list[ImmutableRegistryRejection],
) -> bool:
    artifact_id = (
        artifact.get("artifact_id")
        if isinstance(artifact.get("artifact_id"), str)
        else None
    )
    if not _check_exact_fields(
        artifact,
        _IMMUTABLE_ARTIFACT_FIELDS,
        "Artifact record",
        rejections,
        artifact_id,
    ):
        return False
    if not _is_non_empty_string(artifact["artifact_id"]):
        _immutable_reject(
            rejections,
            ImmutableRegistryRejectionCode.MISSING_ARTIFACT_ID,
            "artifact_id must be a non-empty immutable identifier.",
            artifact_id,
        )
    if artifact["schema_version"] != SCHEMA_VERSION:
        _immutable_reject(
            rejections,
            ImmutableRegistryRejectionCode.UNSUPPORTED_SCHEMA_VERSION,
            "Artifact schema_version is unsupported.",
            artifact_id,
        )
    if not _is_non_empty_string(artifact["artifact_schema_version"]):
        _immutable_reject(
            rejections,
            ImmutableRegistryRejectionCode.INVALID_ARTIFACT,
            "artifact_schema_version must be explicit.",
            artifact_id,
        )
    if (
        not isinstance(artifact["artifact_type"], str)
        or artifact["artifact_type"] not in IMMUTABLE_ARTIFACT_TYPES
    ):
        _immutable_reject(
            rejections,
            ImmutableRegistryRejectionCode.INVALID_ARTIFACT,
            "Artifact type is outside the closed catalog.",
            artifact_id,
        )
    if not _is_uri(artifact["uri"]):
        _immutable_reject(
            rejections,
            ImmutableRegistryRejectionCode.INVALID_ARTIFACT,
            "Artifact uri must be explicit and cannot be a bare filename.",
            artifact_id,
        )
    if not _strict_hex(artifact["sha256"], 64):
        _immutable_reject(
            rejections,
            ImmutableRegistryRejectionCode.INVALID_ARTIFACT,
            "Artifact sha256 must be exact hexadecimal SHA-256.",
            artifact_id,
        )
    if not _is_non_negative_integer(artifact["size_bytes"]):
        _immutable_reject(
            rejections,
            ImmutableRegistryRejectionCode.INVALID_ARTIFACT,
            "Artifact size_bytes must be a non-negative integer.",
            artifact_id,
        )
    if not _is_non_empty_string(artifact["creator_run_id"]):
        _immutable_reject(
            rejections,
            ImmutableRegistryRejectionCode.MISSING_CREATOR_RUN,
            "Artifact creator_run_id must be non-empty.",
            artifact_id,
        )
    if not _strict_id_list(artifact["direct_input_artifact_ids"]):
        _immutable_reject(
            rejections,
            ImmutableRegistryRejectionCode.AMBIGUOUS_LINEAGE,
            "Artifact direct inputs must be a duplicate-free ID list.",
            artifact_id,
        )
    if (
        not isinstance(artifact["status"], str)
        or artifact["status"] not in IMMUTABLE_ARTIFACT_STATUSES
    ):
        _immutable_reject(
            rejections,
            ImmutableRegistryRejectionCode.INVALID_ARTIFACT,
            "Artifact status is unsupported.",
            artifact_id,
        )
    if not _is_non_empty_string(artifact["status_authority"]):
        _immutable_reject(
            rejections,
            ImmutableRegistryRejectionCode.INVALID_ARTIFACT,
            "Artifact status_authority must be explicit.",
            artifact_id,
        )
    status = artifact["status"]
    if status == "accepted":
        valid_lifecycle = (
            artifact["status_reason"] is None
            and artifact["superseded_by"] is None
        )
    elif status == "excluded":
        valid_lifecycle = (
            _is_non_empty_string(artifact["status_reason"])
            and artifact["superseded_by"] is None
        )
    else:
        valid_lifecycle = (
            _is_non_empty_string(artifact["status_reason"])
            and _is_non_empty_string(artifact["superseded_by"])
        )
    if not valid_lifecycle:
        _immutable_reject(
            rejections,
            ImmutableRegistryRejectionCode.MALFORMED_SUPERSESSION,
            "Artifact lifecycle fields disagree with status.",
            artifact_id,
        )
    return True


def _validate_immutable_run_artifact_registry_v1(
    document: Any,
    *,
    previous_registry: Any = None,
    artifact_bytes_by_id: Mapping[str, bytes] | None = None,
) -> ImmutableRegistryValidationResult:
    """Validate the shared immutable registry without mutating submitted data.

    ``previous_registry`` authenticates lifecycle transitions and append-only
    behavior. ``artifact_bytes_by_id`` optionally binds literal artifact bytes
    to the recorded checksum and size. Identity is always explicit; paths,
    filenames, directory order, and physical row order are never consulted.
    """

    rejections: list[ImmutableRegistryRejection] = []
    if not isinstance(document, Mapping):
        _immutable_reject(
            rejections,
            ImmutableRegistryRejectionCode.INVALID_DOCUMENT,
            "Immutable registry must be a mapping.",
        )
        return ImmutableRegistryValidationResult(False, tuple(rejections))
    if not _check_exact_fields(
        document,
        _IMMUTABLE_REGISTRY_FIELDS,
        "Immutable registry",
        rejections,
    ):
        return ImmutableRegistryValidationResult(False, tuple(rejections))
    if (
        document["schema_version"] != SCHEMA_VERSION
        or document["immutable_registry_schema_version"]
        != IMMUTABLE_REGISTRY_SCHEMA_VERSION
    ):
        _immutable_reject(
            rejections,
            ImmutableRegistryRejectionCode.UNSUPPORTED_SCHEMA_VERSION,
            "Immutable registry schema version is unsupported.",
        )
    if not _is_non_empty_string(document["registry_id"]):
        _immutable_reject(
            rejections,
            ImmutableRegistryRejectionCode.INVALID_DOCUMENT,
            "registry_id must be non-empty.",
        )
    if not isinstance(document["synthetic"], bool):
        _immutable_reject(
            rejections,
            ImmutableRegistryRejectionCode.INVALID_DOCUMENT,
            "synthetic must be boolean.",
        )
    if (
        not isinstance(document["scientific_use"], str)
        or document["scientific_use"] not in {"forbidden", "permitted"}
    ):
        _immutable_reject(
            rejections,
            ImmutableRegistryRejectionCode.INVALID_DOCUMENT,
            "scientific_use must be forbidden or permitted.",
        )
    if document["synthetic"] is True and document["scientific_use"] != "forbidden":
        _immutable_reject(
            rejections,
            ImmutableRegistryRejectionCode.INVALID_DOCUMENT,
            "Synthetic registry evidence must forbid scientific use.",
        )
    runs = document["runs"]
    artifacts = document["artifacts"]
    if not isinstance(runs, list) or not runs:
        _immutable_reject(
            rejections,
            ImmutableRegistryRejectionCode.MISSING_REQUIRED_FIELD,
            "Immutable registry requires a non-empty runs list.",
        )
        runs = []
    if not isinstance(artifacts, list) or not artifacts:
        _immutable_reject(
            rejections,
            ImmutableRegistryRejectionCode.MISSING_REQUIRED_FIELD,
            "Immutable registry requires a non-empty artifacts list.",
        )
        artifacts = []

    run_by_id: dict[str, Mapping[str, Any]] = {}
    seen_run_ids: set[str] = set()
    for index, run in enumerate(runs):
        if not isinstance(run, Mapping):
            _immutable_reject(
                rejections,
                ImmutableRegistryRejectionCode.INVALID_RUN,
                f"Run record {index} must be a mapping.",
            )
            continue
        shape_valid = _validate_run_record(run, rejections)
        run_id = run.get("run_id")
        if not _is_non_empty_string(run_id):
            if "run_id" not in run:
                _immutable_reject(
                    rejections,
                    ImmutableRegistryRejectionCode.MISSING_RUN_ID,
                    f"Run record {index} is missing run_id.",
                )
            continue
        if run_id in seen_run_ids:
            _immutable_reject(
                rejections,
                ImmutableRegistryRejectionCode.DUPLICATE_RUN_ID,
                f"Duplicate run_id {run_id!r}.",
                run_id,
            )
        else:
            seen_run_ids.add(run_id)
            if shape_valid:
                run_by_id[run_id] = run

    artifact_by_id: dict[str, Mapping[str, Any]] = {}
    seen_artifact_ids: set[str] = set()
    for index, artifact in enumerate(artifacts):
        if not isinstance(artifact, Mapping):
            _immutable_reject(
                rejections,
                ImmutableRegistryRejectionCode.INVALID_ARTIFACT,
                f"Artifact record {index} must be a mapping.",
            )
            continue
        shape_valid = _validate_artifact_record(artifact, rejections)
        artifact_id = artifact.get("artifact_id")
        if not _is_non_empty_string(artifact_id):
            if "artifact_id" not in artifact:
                _immutable_reject(
                    rejections,
                    ImmutableRegistryRejectionCode.MISSING_ARTIFACT_ID,
                    f"Artifact record {index} is missing artifact_id.",
                )
            continue
        if artifact_id in seen_artifact_ids:
            _immutable_reject(
                rejections,
                ImmutableRegistryRejectionCode.DUPLICATE_ARTIFACT_ID,
                f"Duplicate artifact_id {artifact_id!r}.",
                artifact_id,
            )
        else:
            seen_artifact_ids.add(artifact_id)
            if shape_valid:
                artifact_by_id[artifact_id] = artifact

    parent_by_id: dict[str, str | None] = {}
    superseded_run_by_id: dict[str, str | None] = {}
    superseders_by_target: dict[str, list[str]] = {}
    for run_id, run in run_by_id.items():
        parent_id = run.get("parent_run_id")
        supersedes_id = run.get("supersedes_run_id")
        parent_ref = parent_id if isinstance(parent_id, str) else None
        supersedes_ref = supersedes_id if isinstance(supersedes_id, str) else None
        parent_by_id[run_id] = parent_ref
        superseded_run_by_id[run_id] = supersedes_ref
        if parent_ref is not None and parent_ref not in run_by_id:
            _immutable_reject(
                rejections,
                ImmutableRegistryRejectionCode.AMBIGUOUS_LINEAGE,
                f"Run {run_id!r} references unknown parent run.",
                run_id,
            )
        if supersedes_ref is not None:
            superseders_by_target.setdefault(supersedes_ref, []).append(run_id)
            target = run_by_id.get(supersedes_ref)
            if (
                supersedes_ref == run_id
                or target is None
                or target.get("status") != "completed"
                or target.get("owner") != run.get("owner")
            ):
                _immutable_reject(
                    rejections,
                    ImmutableRegistryRejectionCode.MALFORMED_SUPERSESSION,
                    f"Run {run_id!r} has an invalid supersedes_run_id.",
                    run_id,
                )
        if _has_reference_cycle(run_id, parent_by_id):
            _immutable_reject(
                rejections,
                ImmutableRegistryRejectionCode.AMBIGUOUS_LINEAGE,
                f"Run parent lineage containing {run_id!r} has a cycle.",
                run_id,
            )
    for run_id in superseded_run_by_id:
        if _has_reference_cycle(run_id, superseded_run_by_id):
            _immutable_reject(
                rejections,
                ImmutableRegistryRejectionCode.MALFORMED_SUPERSESSION,
                f"Run supersession containing {run_id!r} has a cycle.",
                run_id,
            )
    for target_id, superseder_ids in superseders_by_target.items():
        if len(superseder_ids) > 1:
            _immutable_reject(
                rejections,
                ImmutableRegistryRejectionCode.AMBIGUOUS_LINEAGE,
                f"Run {target_id!r} has multiple superseding runs.",
                target_id,
            )

    direct_inputs_by_artifact: dict[str, tuple[str, ...]] = {}
    superseded_artifact_by_id: dict[str, str | None] = {}
    for artifact_id, artifact in artifact_by_id.items():
        creator_id = artifact.get("creator_run_id")
        creator = run_by_id.get(creator_id) if isinstance(creator_id, str) else None
        if creator is None:
            _immutable_reject(
                rejections,
                ImmutableRegistryRejectionCode.MISSING_CREATOR_RUN,
                f"Artifact {artifact_id!r} references a nonexistent creator run.",
                artifact_id,
            )
        elif artifact_id not in creator.get("output_artifact_ids", []):
            _immutable_reject(
                rejections,
                ImmutableRegistryRejectionCode.AMBIGUOUS_LINEAGE,
                f"Creator run does not list artifact {artifact_id!r} as output.",
                artifact_id,
            )
        elif creator.get("status") == "in_progress":
            _immutable_reject(
                rejections,
                ImmutableRegistryRejectionCode.AMBIGUOUS_LINEAGE,
                f"Artifact {artifact_id!r} cannot be published by an in-progress run.",
                artifact_id,
            )
        elif (
            artifact.get("status") == "accepted"
            and creator.get("status") != "completed"
        ):
            _immutable_reject(
                rejections,
                ImmutableRegistryRejectionCode.AMBIGUOUS_LINEAGE,
                f"Accepted artifact {artifact_id!r} requires a completed creator run.",
                artifact_id,
            )
        direct_inputs = artifact.get("direct_input_artifact_ids")
        if _strict_id_list(direct_inputs):
            direct_inputs_by_artifact[artifact_id] = tuple(direct_inputs)
            for input_id in direct_inputs:
                source = artifact_by_id.get(input_id)
                if input_id == artifact_id or source is None:
                    _immutable_reject(
                        rejections,
                        ImmutableRegistryRejectionCode.BROKEN_DIRECT_INPUT,
                        f"Artifact {artifact_id!r} has a missing or self direct input.",
                        artifact_id,
                    )
                if creator is not None and input_id not in creator.get(
                    "input_artifact_ids", []
                ):
                    _immutable_reject(
                        rejections,
                        ImmutableRegistryRejectionCode.AMBIGUOUS_LINEAGE,
                        f"Artifact {artifact_id!r} direct input is absent from its creator run.",
                        artifact_id,
                    )
                if (
                    artifact.get("status") == "accepted"
                    and source is not None
                    and source.get("status") != "accepted"
                ):
                    _immutable_reject(
                        rejections,
                        ImmutableRegistryRejectionCode.AMBIGUOUS_LINEAGE,
                        f"Accepted artifact {artifact_id!r} depends on a non-accepted input.",
                        artifact_id,
                )
        replacement_id = artifact.get("superseded_by")
        superseded_artifact_by_id[artifact_id] = (
            replacement_id if isinstance(replacement_id, str) else None
        )
        if replacement_id is not None and not isinstance(replacement_id, str):
            _immutable_reject(
                rejections,
                ImmutableRegistryRejectionCode.MALFORMED_SUPERSESSION,
                f"Artifact {artifact_id!r} replacement ID is malformed.",
                artifact_id,
            )
        elif replacement_id is not None:
            replacement = artifact_by_id.get(replacement_id)
            replacement_creator_id = (
                replacement.get("creator_run_id")
                if replacement is not None
                and isinstance(replacement.get("creator_run_id"), str)
                else None
            )
            replacement_creator = (
                run_by_id.get(replacement_creator_id)
                if replacement_creator_id is not None
                else None
            )
            if (
                replacement_id == artifact_id
                or replacement is None
                or replacement.get("artifact_type") != artifact.get("artifact_type")
                or replacement.get("status") != "accepted"
                or replacement.get("status_authority")
                != artifact.get("status_authority")
                or replacement_creator is None
                or replacement_creator.get("supersedes_run_id")
                != artifact.get("creator_run_id")
            ):
                _immutable_reject(
                    rejections,
                    ImmutableRegistryRejectionCode.MALFORMED_SUPERSESSION,
                    f"Artifact {artifact_id!r} has an invalid replacement.",
                    artifact_id,
                )
    for artifact_id in direct_inputs_by_artifact:
        if _artifact_lineage_has_cycle(artifact_id, direct_inputs_by_artifact):
            _immutable_reject(
                rejections,
                ImmutableRegistryRejectionCode.AMBIGUOUS_LINEAGE,
                f"Artifact direct-input lineage containing {artifact_id!r} has a cycle.",
                artifact_id,
            )
    for artifact_id in superseded_artifact_by_id:
        if _has_reference_cycle(artifact_id, superseded_artifact_by_id):
            _immutable_reject(
                rejections,
                ImmutableRegistryRejectionCode.MALFORMED_SUPERSESSION,
                f"Artifact supersession containing {artifact_id!r} has a cycle.",
                artifact_id,
            )

    for run_id, run in run_by_id.items():
        run_inputs = run.get("input_artifact_ids")
        run_outputs = run.get("output_artifact_ids")
        for input_id in run_inputs if _strict_id_list(run_inputs) else []:
            if input_id not in artifact_by_id:
                _immutable_reject(
                    rejections,
                    ImmutableRegistryRejectionCode.BROKEN_DIRECT_INPUT,
                    f"Run {run_id!r} references missing input artifact {input_id!r}.",
                    run_id,
                )
        for output_id in run_outputs if _strict_id_list(run_outputs) else []:
            output = artifact_by_id.get(output_id)
            if output is None or output.get("creator_run_id") != run_id:
                _immutable_reject(
                    rejections,
                    ImmutableRegistryRejectionCode.AMBIGUOUS_LINEAGE,
                    f"Run {run_id!r} has an unresolved or foreign output {output_id!r}.",
                    run_id,
                )

    if artifact_bytes_by_id is not None:
        if not isinstance(artifact_bytes_by_id, Mapping):
            _immutable_reject(
                rejections,
                ImmutableRegistryRejectionCode.CHECKSUM_MISMATCH,
                "artifact_bytes_by_id must be a mapping when supplied.",
            )
        else:
            for artifact_id, payload in artifact_bytes_by_id.items():
                artifact = artifact_by_id.get(artifact_id)
                if artifact is None or not isinstance(payload, bytes):
                    _immutable_reject(
                        rejections,
                        ImmutableRegistryRejectionCode.CHECKSUM_MISMATCH,
                        f"Checksum evidence for {artifact_id!r} is malformed.",
                        artifact_id if isinstance(artifact_id, str) else None,
                    )
                    continue
                digest = hashlib.sha256(payload).hexdigest()
                if digest != artifact.get("sha256") or len(payload) != artifact.get(
                    "size_bytes"
                ):
                    _immutable_reject(
                        rejections,
                        ImmutableRegistryRejectionCode.CHECKSUM_MISMATCH,
                        f"Artifact {artifact_id!r} checksum or size mismatches supplied bytes.",
                        artifact_id,
                    )

    if previous_registry is not None:
        previous_result = validate_immutable_run_artifact_registry(previous_registry)
        if not previous_result.accepted or not isinstance(previous_registry, Mapping):
            _immutable_reject(
                rejections,
                ImmutableRegistryRejectionCode.INVALID_DOCUMENT,
                "previous_registry must itself be a valid immutable registry.",
            )
        else:
            if (
                previous_registry.get("registry_id") != document["registry_id"]
                or previous_registry.get("schema_version") != document["schema_version"]
                or previous_registry.get("immutable_registry_schema_version")
                != document["immutable_registry_schema_version"]
                or previous_registry.get("synthetic") != document["synthetic"]
                or previous_registry.get("scientific_use")
                != document["scientific_use"]
            ):
                _immutable_reject(
                    rejections,
                    ImmutableRegistryRejectionCode.UNVERSIONED_SCHEMA_CHANGE,
                    "Registry identity, version, or scope changed in place.",
                )
            previous_runs = {
                run["run_id"]: run
                for run in previous_registry["runs"]
                if isinstance(run, Mapping) and isinstance(run.get("run_id"), str)
            }
            for run_id, prior in previous_runs.items():
                current = run_by_id.get(run_id)
                if current is None:
                    _immutable_reject(
                        rejections,
                        ImmutableRegistryRejectionCode.COMPLETED_RUN_MUTATION,
                        f"Existing run {run_id!r} was removed.",
                        run_id,
                    )
                    continue
                prior_status = prior["status"]
                current_status = current["status"]
                if prior_status in {"completed", "failed"}:
                    if current_status != prior_status:
                        _immutable_reject(
                            rejections,
                            ImmutableRegistryRejectionCode.ILLEGAL_RUN_STATUS_TRANSITION,
                            f"Terminal run {run_id!r} cannot change status.",
                            run_id,
                        )
                    if current != prior:
                        _immutable_reject(
                            rejections,
                            ImmutableRegistryRejectionCode.COMPLETED_RUN_MUTATION,
                            f"Terminal run {run_id!r} was mutated in place.",
                            run_id,
                        )
                elif current_status not in {"in_progress", "completed", "failed"}:
                    _immutable_reject(
                        rejections,
                        ImmutableRegistryRejectionCode.ILLEGAL_RUN_STATUS_TRANSITION,
                        f"Run {run_id!r} has an illegal status transition.",
                        run_id,
                    )
                elif current_status == "in_progress" and current != prior:
                    _immutable_reject(
                        rejections,
                        ImmutableRegistryRejectionCode.ILLEGAL_RUN_STATUS_TRANSITION,
                        f"In-progress run {run_id!r} changed without a terminal transition.",
                        run_id,
                    )
                elif current_status in {"completed", "failed"}:
                    mutable_at_terminal = {
                        "status",
                        "ended_at",
                        "output_artifact_ids",
                        "failure_reason",
                    }
                    for field in _IMMUTABLE_RUN_FIELDS - mutable_at_terminal:
                        if current[field] != prior[field]:
                            _immutable_reject(
                                rejections,
                                ImmutableRegistryRejectionCode.ILLEGAL_RUN_STATUS_TRANSITION,
                                f"Run {run_id!r} changed immutable field {field!r}.",
                                run_id,
                            )
            previous_artifacts = {
                artifact["artifact_id"]: artifact
                for artifact in previous_registry["artifacts"]
                if isinstance(artifact, Mapping)
                and isinstance(artifact.get("artifact_id"), str)
            }
            for artifact_id, prior in previous_artifacts.items():
                current = artifact_by_id.get(artifact_id)
                if current is None:
                    _immutable_reject(
                        rejections,
                        ImmutableRegistryRejectionCode.IMMUTABLE_ARTIFACT_MUTATION,
                        f"Existing artifact {artifact_id!r} was removed.",
                        artifact_id,
                    )
                    continue
                if current == prior:
                    continue
                lifecycle_fields = {"status", "status_reason", "superseded_by"}
                unchanged = all(
                    current[field] == prior[field]
                    for field in _IMMUTABLE_ARTIFACT_FIELDS - lifecycle_fields
                )
                if not (
                    prior["status"] == "accepted"
                    and current["status"] == "superseded"
                    and unchanged
                ):
                    _immutable_reject(
                        rejections,
                        ImmutableRegistryRejectionCode.IMMUTABLE_ARTIFACT_MUTATION,
                        f"Artifact {artifact_id!r} was mutated outside supersession.",
                        artifact_id,
                    )
                elif current["superseded_by"] in previous_artifacts:
                    _immutable_reject(
                        rejections,
                        ImmutableRegistryRejectionCode.IMMUTABLE_ARTIFACT_MUTATION,
                        f"Artifact {artifact_id!r} must point to a newly appended replacement.",
                        artifact_id,
                    )

    return ImmutableRegistryValidationResult(not rejections, tuple(rejections))


_IMMUTABLE_V2_REGISTRY_FIELDS = frozenset(
    {
        "schema_version",
        "immutable_registry_schema_version",
        "registry_id",
        "synthetic",
        "scientific_use",
        "owner_authorities",
        "manifests",
        "byte_verifications",
        "runs",
        "artifacts",
    }
)

_IMMUTABLE_V2_AUTHORITY_FIELDS = frozenset(
    {
        "schema_version",
        "authority_id",
        "owner_id",
        "authority_revision",
        "status_record_id",
        "status_record_sha256",
        "status_record_schema_version",
        "status_record_verification_mode",
        "status_record_receipt_id",
        "status_record_receipt_sha256",
        "status_record_receipt_authority_revision",
        "decision",
        "owner_status",
        "authorized_artifact_types",
    }
)

_IMMUTABLE_V2_TRUSTED_AUTHORITY_FIELDS = frozenset(
    {"authority", "status_record_verification"}
)

_IMMUTABLE_V2_STATUS_RECORD_VERIFICATION_FIELDS = frozenset(
    {"mode", "external_receipt"}
)

_IMMUTABLE_V2_STATUS_RECORD_RECEIPT_FIELDS = frozenset(
    {
        "receipt_id",
        "receipt_sha256",
        "receipt_authority_revision",
        "verified_status_record_id",
        "verified_status_record_sha256",
        "verified_status_record_schema_version",
        "verified_owner_id",
        "verified_owner_authority_revision",
        "verified_owner_status",
        "verified_decision",
    }
)

_IMMUTABLE_V2_STATUS_RECORD_FIELDS = frozenset(
    {
        "schema_version",
        "status_record_id",
        "owner_id",
        "authority_revision",
        "owner_status",
        "decision",
    }
)

_IMMUTABLE_V2_TRUSTED_ARTIFACT_AUTHORIZATION_FIELDS = frozenset(
    {"authorization", "authorization_record_verification"}
)

_IMMUTABLE_V2_ARTIFACT_AUTHORIZATION_FIELDS = frozenset(
    {
        "authorization_id",
        "authority_id",
        "owner_id",
        "owner_authority_revision",
        "artifact_id",
        "artifact_type",
        "artifact_schema_version",
        "artifact_sha256",
        "artifact_size_bytes",
        "manifest_id",
        "manifest_sha256",
        "manifest_schema_version",
        "manifest_artifact_identity",
        "owner_status",
        "decision",
        "authorization_record_id",
        "authorization_record_sha256",
        "authorization_record_verification_mode",
        "authorization_record_receipt_id",
        "authorization_record_receipt_sha256",
        "authorization_record_receipt_authority_revision",
    }
)

_IMMUTABLE_V2_AUTHORIZATION_RECORD_FIELDS = frozenset(
    {
        "authorization_record_id",
        "authorization_id",
        "authority_id",
        "owner_id",
        "owner_authority_revision",
        "artifact_id",
        "artifact_type",
        "artifact_schema_version",
        "artifact_sha256",
        "artifact_size_bytes",
        "manifest_id",
        "manifest_sha256",
        "manifest_schema_version",
        "manifest_artifact_identity",
        "owner_status",
        "decision",
    }
)

_IMMUTABLE_V2_AUTHORIZATION_VERIFICATION_FIELDS = frozenset(
    {"mode", "external_receipt"}
)

_IMMUTABLE_V2_AUTHORIZATION_RECEIPT_FIELDS = frozenset(
    {
        "receipt_id",
        "receipt_sha256",
        "receipt_authority_revision",
        "verified_authorization_record_id",
        "verified_authorization_record_sha256",
        "verified_authority_id",
        "verified_owner_id",
        "verified_owner_revision",
        "verified_artifact_id",
        "verified_artifact_type",
        "verified_artifact_sha256",
        "verified_artifact_size",
        "verified_manifest_id",
        "verified_manifest_sha256",
        "verified_manifest_artifact_identity",
        "verified_owner_status",
        "verified_decision",
    }
)

_IMMUTABLE_V2_TRUSTED_MANIFEST_FIELDS = frozenset(
    {
        "manifest_id",
        "manifest_sha256",
        "manifest_schema_version",
        "owner_authority_id",
        "owner_id",
        "owner_authority_revision",
        "owner_status",
        "decision",
        "artifact_identities",
    }
)

_IMMUTABLE_V2_TRUSTED_MANIFEST_ARTIFACT_FIELDS = frozenset(
    {
        "artifact_id",
        "artifact_type",
        "artifact_schema_version",
        "artifact_sha256",
        "artifact_size_bytes",
        "manifest_artifact_identity",
    }
)

_IMMUTABLE_V2_TRUSTED_ARTIFACT_RECEIPT_FIELDS = frozenset(
    {
        "receipt_id",
        "receipt_sha256",
        "receipt_authority_revision",
        "verified_artifact_id",
        "verified_artifact_type",
        "verified_artifact_schema_version",
        "verified_artifact_sha256",
        "verified_artifact_size",
        "verified_owner_id",
        "verified_owner_authority_revision",
        "verified_manifest_id",
        "verified_manifest_sha256",
        "verified_manifest_artifact_identity",
    }
)

_IMMUTABLE_V2_MANIFEST_FIELDS = frozenset(
    {
        "schema_version",
        "manifest_id",
        "manifest_sha256",
        "manifest_schema_version",
        "owner_authority_id",
        "decision",
        "artifact_identities",
    }
)

_IMMUTABLE_V2_BYTE_VERIFICATION_FIELDS = frozenset(
    {
        "schema_version",
        "verification_id",
        "artifact_id",
        "mode",
        "verified_sha256",
        "verified_size_bytes",
        "verified_at",
        "external_receipt_id",
        "external_receipt_sha256",
        "external_receipt_authority_revision",
    }
)

_IMMUTABLE_V2_RUN_FIELDS = frozenset(
    {
        "schema_version",
        "run_id",
        "code_sha",
        "git_dirty",
        "config_snapshot_hash",
        "checkpoint_hash",
        "data_identity_hash",
        "preprocess_hash",
        "environment_hash",
        "seeds",
        "command",
        "owner",
        "created_at",
        "started_at",
        "ended_at",
        "status",
        "pending_reason",
        "failure_reason",
        "parent_run_id",
        "input_artifact_ids",
        "output_artifact_ids",
        "supersedes_run_id",
        "supersession_reason",
    }
)

_IMMUTABLE_V2_ARTIFACT_FIELDS = frozenset(
    {
        "schema_version",
        "artifact_schema_version",
        "artifact_id",
        "direct_input_artifact_ids",
        "creator_run_id",
        "artifact_type",
        "uri",
        "sha256",
        "size_bytes",
        "status",
        "status_reason",
        "superseded_by",
        "owner_authority_id",
        "owner_authority_revision",
        "owner_status_record_id",
        "owner_status_record_sha256",
        "owner_decision",
        "manifest_id",
        "manifest_sha256",
        "manifest_schema_version",
        "manifest_artifact_identity",
        "byte_verification_id",
    }
)


def _v2_require_record_list(
    document: Mapping[str, Any],
    field: str,
    rejections: list[ImmutableRegistryRejection],
    *,
    require_nonempty: bool = False,
) -> list[Any]:
    value = document[field]
    if not isinstance(value, list) or (require_nonempty and not value):
        qualification = "a non-empty list" if require_nonempty else "a list"
        _immutable_reject(
            rejections,
            ImmutableRegistryRejectionCode.MISSING_REQUIRED_FIELD,
            f"Immutable registry v2 {field} must be {qualification}.",
        )
        return []
    return value


def _validate_v2_authority_record(
    record: Mapping[str, Any],
    rejections: list[ImmutableRegistryRejection],
) -> bool:
    authority_id = (
        record.get("authority_id")
        if isinstance(record.get("authority_id"), str)
        else None
    )
    if not _check_exact_fields(
        record,
        _IMMUTABLE_V2_AUTHORITY_FIELDS,
        "Owner authority record",
        rejections,
        authority_id,
    ):
        return False
    valid = True
    checks = (
        (
            record["schema_version"] == SCHEMA_VERSION,
            "Authority schema_version is unsupported.",
        ),
        (
            _is_non_empty_string(record["authority_id"]),
            "authority_id must be non-empty.",
        ),
        (
            isinstance(record["owner_id"], str)
            and record["owner_id"] in IMMUTABLE_V2_OWNER_IDS,
            "Authority owner_id is outside the closed owner catalog.",
        ),
        (
            _strict_hex(record["authority_revision"], 40),
            "Authority revision must be an exact full Git commit.",
        ),
        (
            _is_non_empty_string(record["status_record_id"]),
            "Authority status_record_id must be non-empty.",
        ),
        (
            _strict_hex(record["status_record_sha256"], 64),
            "Authority status-record hash must be SHA-256.",
        ),
        (
            isinstance(record["decision"], str)
            and record["decision"] in IMMUTABLE_V2_AUTHORITY_DECISIONS,
            "Authority decision is unsupported.",
        ),
        (
            isinstance(record["owner_status"], str)
            and record["owner_status"] in IMMUTABLE_V2_OWNER_STATUSES,
            "Authority owner_status is outside the normalized closed enum.",
        ),
        (
            isinstance(record["owner_status"], str)
            and IMMUTABLE_V2_OWNER_STATUS_DECISIONS.get(record["owner_status"])
            == record["decision"],
            "Authority owner_status and decision are inconsistent.",
        ),
        (
            record["status_record_schema_version"]
            == IMMUTABLE_V2_STATUS_RECORD_SCHEMA_VERSION,
            "Authority status-record schema version is unsupported.",
        ),
        (
            isinstance(record["status_record_verification_mode"], str)
            and record["status_record_verification_mode"]
            in IMMUTABLE_V2_STATUS_RECORD_VERIFICATION_MODES,
            "Authority status-record verification mode is unsupported.",
        ),
        (
            _strict_id_list(record["authorized_artifact_types"])
            and bool(record["authorized_artifact_types"])
            and all(
                artifact_type in IMMUTABLE_V2_ARTIFACT_TYPES
                for artifact_type in record["authorized_artifact_types"]
            ),
            "Authority artifact types must be a non-empty closed-catalog list.",
        ),
    )
    for accepted, message in checks:
        if accepted:
            continue
        valid = False
        _immutable_reject(
            rejections,
            ImmutableRegistryRejectionCode.INVALID_AUTHORITY,
            message,
            authority_id,
        )
    owner_id = record["owner_id"]
    artifact_types = record["authorized_artifact_types"]
    if (
        isinstance(owner_id, str)
        and owner_id in IMMUTABLE_V2_OWNER_IDS
        and _strict_id_list(artifact_types)
        and all(
            artifact_type in IMMUTABLE_V2_ARTIFACT_TYPES
            for artifact_type in artifact_types
        )
        and any(
            owner_id not in IMMUTABLE_V2_ARTIFACT_OWNER_IDS[artifact_type]
            for artifact_type in artifact_types
        )
    ):
        valid = False
        _immutable_reject(
            rejections,
            ImmutableRegistryRejectionCode.INVALID_AUTHORITY,
            "Authority artifact types exceed the owner's closed boundary.",
            authority_id,
        )
    verification_mode = record["status_record_verification_mode"]
    receipt_fields = (
        record["status_record_receipt_id"],
        record["status_record_receipt_sha256"],
        record["status_record_receipt_authority_revision"],
    )
    if verification_mode == "local_bytes" and any(
        value is not None for value in receipt_fields
    ):
        valid = False
        _immutable_reject(
            rejections,
            ImmutableRegistryRejectionCode.INVALID_AUTHORITY,
            "Local status-record verification requires null receipt bindings.",
            authority_id,
        )
    elif verification_mode == "external_receipt" and not (
        _is_non_empty_string(record["status_record_receipt_id"])
        and _strict_hex(record["status_record_receipt_sha256"], 64)
        and _strict_hex(record["status_record_receipt_authority_revision"], 40)
        and record["status_record_receipt_authority_revision"]
        == record["authority_revision"]
    ):
        valid = False
        _immutable_reject(
            rejections,
            ImmutableRegistryRejectionCode.INVALID_AUTHORITY,
            "External status-record verification requires exact receipt bindings.",
            authority_id,
        )
    return valid


def _v2_status_record_reject(
    rejections: list[ImmutableRegistryRejection],
    message: str,
    authority_id: str | None,
) -> None:
    _immutable_reject(
        rejections,
        ImmutableRegistryRejectionCode.STATUS_RECORD_VERIFICATION_FAILED,
        message,
        authority_id,
    )


def _v2_json_object_without_duplicate_keys(
    pairs: list[tuple[str, Any]],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key {key!r}.")
        result[key] = value
    return result


def _validate_v2_local_status_record(
    authority: Mapping[str, Any],
    trusted_status_record_bytes: Mapping[str, bytes] | None,
    rejections: list[ImmutableRegistryRejection],
) -> bool:
    authority_id = authority["authority_id"]
    status_record_id = authority["status_record_id"]
    payload = (
        trusted_status_record_bytes.get(status_record_id)
        if isinstance(trusted_status_record_bytes, Mapping)
        else None
    )
    if not isinstance(payload, bytes):
        _v2_status_record_reject(
            rejections,
            "Local status-record verification requires verifier-supplied bytes.",
            authority_id,
        )
        return False
    if hashlib.sha256(payload).hexdigest() != authority["status_record_sha256"]:
        _v2_status_record_reject(
            rejections,
            "Verifier-supplied status-record bytes do not match SHA-256.",
            authority_id,
        )
        return False
    try:
        decoded = payload.decode("utf-8")
        status_record = json.loads(
            decoded,
            object_pairs_hook=_v2_json_object_without_duplicate_keys,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        _v2_status_record_reject(
            rejections,
            "Verifier-supplied status record is not unambiguous UTF-8 JSON.",
            authority_id,
        )
        return False
    expected = {
        "schema_version": authority["status_record_schema_version"],
        "status_record_id": status_record_id,
        "owner_id": authority["owner_id"],
        "authority_revision": authority["authority_revision"],
        "owner_status": authority["owner_status"],
        "decision": authority["decision"],
    }
    if not isinstance(status_record, Mapping) or status_record != expected:
        _v2_status_record_reject(
            rejections,
            "Status-record JSON does not exactly match the trusted authority.",
            authority_id,
        )
        return False
    return True


def _validate_v2_status_record_receipt(
    authority: Mapping[str, Any],
    receipt: Any,
    rejections: list[ImmutableRegistryRejection],
) -> bool:
    authority_id = authority["authority_id"]
    if not isinstance(receipt, Mapping):
        _v2_status_record_reject(
            rejections,
            "External status-record verification requires a trusted receipt.",
            authority_id,
        )
        return False
    if not _check_exact_fields(
        receipt,
        _IMMUTABLE_V2_STATUS_RECORD_RECEIPT_FIELDS,
        "Trusted status-record receipt",
        rejections,
        authority_id,
    ):
        _v2_status_record_reject(
            rejections,
            "Trusted status-record receipt fields are incomplete or unknown.",
            authority_id,
        )
        return False
    checks = (
        _is_non_empty_string(receipt["receipt_id"]),
        _strict_hex(receipt["receipt_sha256"], 64),
        _strict_hex(receipt["receipt_authority_revision"], 40),
        receipt["receipt_id"] == authority["status_record_receipt_id"],
        receipt["receipt_sha256"]
        == authority["status_record_receipt_sha256"],
        receipt["receipt_authority_revision"]
        == authority["status_record_receipt_authority_revision"],
        receipt["receipt_authority_revision"] == authority["authority_revision"],
        receipt["verified_status_record_id"] == authority["status_record_id"],
        receipt["verified_status_record_sha256"]
        == authority["status_record_sha256"],
        receipt["verified_status_record_schema_version"]
        == authority["status_record_schema_version"],
        receipt["verified_owner_id"] == authority["owner_id"],
        receipt["verified_owner_authority_revision"]
        == authority["authority_revision"],
        receipt["verified_owner_status"] == authority["owner_status"],
        receipt["verified_decision"] == authority["decision"],
    )
    if not all(checks):
        _v2_status_record_reject(
            rejections,
            "Trusted external receipt does not exactly bind the owner status record.",
            authority_id,
        )
        return False
    return True


def _validate_v2_trusted_owner_authorities(
    trusted_owner_authorities: Mapping[str, Mapping[str, Any]] | None,
    trusted_status_record_bytes: Mapping[str, bytes] | None,
    rejections: list[ImmutableRegistryRejection],
) -> dict[str, Mapping[str, Any]]:
    if trusted_status_record_bytes is not None and not isinstance(
        trusted_status_record_bytes, Mapping
    ):
        _immutable_reject(
            rejections,
            ImmutableRegistryRejectionCode.STATUS_RECORD_VERIFICATION_FAILED,
            "trusted_status_record_bytes must be a mapping when supplied.",
        )
        return {}
    if trusted_owner_authorities is None:
        if isinstance(trusted_status_record_bytes, Mapping) and (
            trusted_status_record_bytes
        ):
            _immutable_reject(
                rejections,
                ImmutableRegistryRejectionCode.INVALID_TRUSTED_AUTHORITY,
                "Status-record bytes were supplied without trusted authorities.",
            )
        return {}
    if not isinstance(trusted_owner_authorities, Mapping):
        _immutable_reject(
            rejections,
            ImmutableRegistryRejectionCode.INVALID_TRUSTED_AUTHORITY,
            "trusted_owner_authorities must be a verifier-supplied mapping.",
        )
        return {}

    trusted_by_id: dict[str, Mapping[str, Any]] = {}
    local_status_record_ids: set[str] = set()
    for key, entry in trusted_owner_authorities.items():
        record_id = key if isinstance(key, str) else None
        if not _is_non_empty_string(key) or not isinstance(entry, Mapping):
            _immutable_reject(
                rejections,
                ImmutableRegistryRejectionCode.INVALID_TRUSTED_AUTHORITY,
                "Trusted authority keys must identify mapping entries.",
                record_id,
            )
            continue
        if not _check_exact_fields(
            entry,
            _IMMUTABLE_V2_TRUSTED_AUTHORITY_FIELDS,
            "Trusted owner authority",
            rejections,
            key,
        ):
            continue
        authority = entry["authority"]
        verification = entry["status_record_verification"]
        if not isinstance(authority, Mapping):
            _immutable_reject(
                rejections,
                ImmutableRegistryRejectionCode.INVALID_TRUSTED_AUTHORITY,
                "Trusted authority must contain an authority mapping.",
                key,
            )
            continue
        authority_valid = _validate_v2_authority_record(authority, rejections)
        if authority.get("authority_id") != key:
            authority_valid = False
            _immutable_reject(
                rejections,
                ImmutableRegistryRejectionCode.INVALID_TRUSTED_AUTHORITY,
                "Trusted authority map key and authority_id differ.",
                key,
            )
        if not isinstance(verification, Mapping) or not _check_exact_fields(
            verification,
            _IMMUTABLE_V2_STATUS_RECORD_VERIFICATION_FIELDS,
            "Trusted status-record verification",
            rejections,
            key,
        ):
            _immutable_reject(
                rejections,
                ImmutableRegistryRejectionCode.INVALID_TRUSTED_AUTHORITY,
                "Trusted authority requires exact status-record verification.",
                key,
            )
            continue
        mode = verification["mode"]
        if (
            not isinstance(mode, str)
            or mode not in IMMUTABLE_V2_STATUS_RECORD_VERIFICATION_MODES
            or mode != authority.get("status_record_verification_mode")
        ):
            authority_valid = False
            _immutable_reject(
                rejections,
                ImmutableRegistryRejectionCode.INVALID_TRUSTED_AUTHORITY,
                "Trusted and embedded status-record verification modes differ.",
                key,
            )
        elif mode == "local_bytes":
            if verification["external_receipt"] is not None:
                authority_valid = False
                _v2_status_record_reject(
                    rejections,
                    "Local status-record evidence requires a null receipt.",
                    key,
                )
            elif authority_valid:
                local_status_record_ids.add(authority["status_record_id"])
                authority_valid = _validate_v2_local_status_record(
                    authority,
                    trusted_status_record_bytes,
                    rejections,
                )
        elif authority_valid:
            authority_valid = _validate_v2_status_record_receipt(
                authority,
                verification["external_receipt"],
                rejections,
            )
        if authority_valid:
            trusted_by_id[key] = entry

    if isinstance(trusted_status_record_bytes, Mapping):
        for status_record_id, payload in trusted_status_record_bytes.items():
            if (
                not _is_non_empty_string(status_record_id)
                or not isinstance(payload, bytes)
                or status_record_id not in local_status_record_ids
            ):
                _v2_status_record_reject(
                    rejections,
                    "Verifier supplied malformed or unreferenced status-record bytes.",
                    status_record_id if isinstance(status_record_id, str) else None,
                )
    return trusted_by_id


def _v2_artifact_authorization_reject(
    rejections: list[ImmutableRegistryRejection],
    message: str,
    record_id: str | None,
) -> None:
    _immutable_reject(
        rejections,
        ImmutableRegistryRejectionCode.INVALID_ARTIFACT_AUTHORIZATION,
        message,
        record_id,
    )


def _v2_authorization_evidence_reject(
    rejections: list[ImmutableRegistryRejection],
    message: str,
    record_id: str | None,
) -> None:
    _immutable_reject(
        rejections,
        ImmutableRegistryRejectionCode.ARTIFACT_AUTHORIZATION_VERIFICATION_FAILED,
        message,
        record_id,
    )


def _v2_authorization_record_document(
    authorization: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        field: authorization[field]
        for field in _IMMUTABLE_V2_AUTHORIZATION_RECORD_FIELDS
    }


def _validate_v2_artifact_authorization_record(
    authorization: Mapping[str, Any],
    rejections: list[ImmutableRegistryRejection],
) -> bool:
    authorization_id = (
        authorization.get("authorization_id")
        if isinstance(authorization.get("authorization_id"), str)
        else None
    )
    if not _check_exact_fields(
        authorization,
        _IMMUTABLE_V2_ARTIFACT_AUTHORIZATION_FIELDS,
        "Trusted exact-artifact authorization",
        rejections,
        authorization_id,
    ):
        return False
    valid = True
    checks = (
        (
            _is_non_empty_string(authorization["authorization_id"]),
            "authorization_id must be non-empty.",
        ),
        (
            _is_non_empty_string(authorization["authority_id"]),
            "authority_id must be non-empty.",
        ),
        (
            isinstance(authorization["owner_id"], str)
            and authorization["owner_id"] in IMMUTABLE_V2_OWNER_IDS,
            "Authorization owner_id is outside the closed catalog.",
        ),
        (
            _strict_hex(authorization["owner_authority_revision"], 40),
            "Authorization owner revision must be an exact full Git commit.",
        ),
        (
            _is_non_empty_string(authorization["artifact_id"]),
            "Authorization artifact_id must be non-empty.",
        ),
        (
            isinstance(authorization["artifact_type"], str)
            and authorization["artifact_type"] in IMMUTABLE_V2_ARTIFACT_TYPES,
            "Authorization artifact_type is outside the closed catalog.",
        ),
        (
            _is_non_empty_string(authorization["artifact_schema_version"]),
            "Authorization artifact schema/version must be explicit.",
        ),
        (
            _strict_hex(authorization["artifact_sha256"], 64),
            "Authorization artifact hash must be SHA-256.",
        ),
        (
            _is_non_negative_integer(authorization["artifact_size_bytes"]),
            "Authorization artifact size must be a non-negative integer.",
        ),
        (
            _is_non_empty_string(authorization["manifest_id"]),
            "Authorization manifest_id must be non-empty.",
        ),
        (
            _strict_hex(authorization["manifest_sha256"], 64),
            "Authorization manifest hash must be SHA-256.",
        ),
        (
            _is_non_empty_string(authorization["manifest_schema_version"]),
            "Authorization manifest schema/version must be explicit.",
        ),
        (
            _is_non_empty_string(authorization["manifest_artifact_identity"]),
            "Authorization manifest artifact identity must be non-empty.",
        ),
        (
            isinstance(authorization["owner_status"], str)
            and authorization["owner_status"] in IMMUTABLE_V2_OWNER_STATUSES,
            "Authorization owner_status is outside the normalized closed enum.",
        ),
        (
            isinstance(authorization["decision"], str)
            and authorization["decision"] in IMMUTABLE_V2_AUTHORITY_DECISIONS,
            "Authorization decision is unsupported.",
        ),
        (
            IMMUTABLE_V2_OWNER_STATUS_DECISIONS.get(
                authorization["owner_status"]
            )
            == authorization["decision"],
            "Authorization owner_status and decision are inconsistent.",
        ),
        (
            _is_non_empty_string(authorization["authorization_record_id"]),
            "authorization_record_id must be non-empty.",
        ),
        (
            _strict_hex(authorization["authorization_record_sha256"], 64),
            "Authorization-record hash must be SHA-256.",
        ),
        (
            authorization["authorization_record_verification_mode"]
            in IMMUTABLE_V2_STATUS_RECORD_VERIFICATION_MODES,
            "Authorization-record verification mode is unsupported.",
        ),
    )
    for accepted, message in checks:
        if accepted:
            continue
        valid = False
        _v2_artifact_authorization_reject(
            rejections, message, authorization_id
        )
    artifact_type = authorization["artifact_type"]
    owner_id = authorization["owner_id"]
    if (
        isinstance(artifact_type, str)
        and artifact_type in IMMUTABLE_V2_ARTIFACT_OWNER_IDS
        and isinstance(owner_id, str)
        and owner_id in IMMUTABLE_V2_OWNER_IDS
        and owner_id not in IMMUTABLE_V2_ARTIFACT_OWNER_IDS[artifact_type]
    ):
        valid = False
        _v2_artifact_authorization_reject(
            rejections,
            "Authorization artifact type exceeds the owner's closed boundary.",
            authorization_id,
        )
    receipt_fields = (
        authorization["authorization_record_receipt_id"],
        authorization["authorization_record_receipt_sha256"],
        authorization["authorization_record_receipt_authority_revision"],
    )
    mode = authorization["authorization_record_verification_mode"]
    if mode == "local_bytes" and any(value is not None for value in receipt_fields):
        valid = False
        _v2_artifact_authorization_reject(
            rejections,
            "Local authorization-record verification requires null receipt bindings.",
            authorization_id,
        )
    elif mode == "external_receipt" and not (
        _is_non_empty_string(receipt_fields[0])
        and _strict_hex(receipt_fields[1], 64)
        and _strict_hex(receipt_fields[2], 40)
        and receipt_fields[2] == authorization["owner_authority_revision"]
    ):
        valid = False
        _v2_artifact_authorization_reject(
            rejections,
            "External authorization-record verification requires exact receipt bindings.",
            authorization_id,
        )
    return valid


def _validate_v2_local_authorization_record(
    authorization: Mapping[str, Any],
    trusted_authorization_record_bytes: Mapping[str, bytes] | None,
    rejections: list[ImmutableRegistryRejection],
) -> bool:
    authorization_id = authorization["authorization_id"]
    record_id = authorization["authorization_record_id"]
    payload = (
        trusted_authorization_record_bytes.get(record_id)
        if isinstance(trusted_authorization_record_bytes, Mapping)
        else None
    )
    if not isinstance(payload, bytes):
        _v2_authorization_evidence_reject(
            rejections,
            "Local authorization verification requires verifier-supplied bytes.",
            authorization_id,
        )
        return False
    if (
        hashlib.sha256(payload).hexdigest()
        != authorization["authorization_record_sha256"]
    ):
        _v2_authorization_evidence_reject(
            rejections,
            "Verifier-supplied authorization bytes do not match SHA-256.",
            authorization_id,
        )
        return False
    try:
        decoded = payload.decode("utf-8")
        record = json.loads(
            decoded,
            object_pairs_hook=_v2_json_object_without_duplicate_keys,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        _v2_authorization_evidence_reject(
            rejections,
            "Authorization record is not unambiguous UTF-8 JSON.",
            authorization_id,
        )
        return False
    expected = _v2_authorization_record_document(authorization)
    canonical = json.dumps(expected, indent=2, sort_keys=True) + "\n"
    if (
        not isinstance(record, Mapping)
        or record != expected
        or decoded != canonical
    ):
        _v2_authorization_evidence_reject(
            rejections,
            "Authorization JSON is noncanonical or mismatches exact authorization.",
            authorization_id,
        )
        return False
    return True


def _validate_v2_authorization_receipt(
    authorization: Mapping[str, Any],
    receipt: Any,
    rejections: list[ImmutableRegistryRejection],
) -> bool:
    authorization_id = authorization["authorization_id"]
    if not isinstance(receipt, Mapping) or not _check_exact_fields(
        receipt,
        _IMMUTABLE_V2_AUTHORIZATION_RECEIPT_FIELDS,
        "Trusted artifact-authorization receipt",
        rejections,
        authorization_id,
    ):
        _v2_authorization_evidence_reject(
            rejections,
            "External authorization verification requires an exact trusted receipt.",
            authorization_id,
        )
        return False
    checks = (
        receipt["receipt_id"]
        == authorization["authorization_record_receipt_id"],
        receipt["receipt_sha256"]
        == authorization["authorization_record_receipt_sha256"],
        receipt["receipt_authority_revision"]
        == authorization["authorization_record_receipt_authority_revision"],
        receipt["receipt_authority_revision"]
        == authorization["owner_authority_revision"],
        receipt["verified_authorization_record_id"]
        == authorization["authorization_record_id"],
        receipt["verified_authorization_record_sha256"]
        == authorization["authorization_record_sha256"],
        receipt["verified_authority_id"] == authorization["authority_id"],
        receipt["verified_owner_id"] == authorization["owner_id"],
        receipt["verified_owner_revision"]
        == authorization["owner_authority_revision"],
        receipt["verified_artifact_id"] == authorization["artifact_id"],
        receipt["verified_artifact_type"] == authorization["artifact_type"],
        receipt["verified_artifact_sha256"]
        == authorization["artifact_sha256"],
        receipt["verified_artifact_size"]
        == authorization["artifact_size_bytes"],
        receipt["verified_manifest_id"] == authorization["manifest_id"],
        receipt["verified_manifest_sha256"]
        == authorization["manifest_sha256"],
        receipt["verified_manifest_artifact_identity"]
        == authorization["manifest_artifact_identity"],
        receipt["verified_owner_status"] == authorization["owner_status"],
        receipt["verified_decision"] == authorization["decision"],
        _strict_hex(receipt["receipt_sha256"], 64),
        _strict_hex(receipt["receipt_authority_revision"], 40),
    )
    if not all(checks):
        _v2_authorization_evidence_reject(
            rejections,
            "Trusted authorization receipt does not bind the exact artifact.",
            authorization_id,
        )
        return False
    return True


def _validate_v2_trusted_artifact_authorizations(
    trusted_artifact_authorizations: Mapping[str, Mapping[str, Any]] | None,
    trusted_authorization_record_bytes: Mapping[str, bytes] | None,
    rejections: list[ImmutableRegistryRejection],
) -> dict[str, Mapping[str, Any]]:
    if trusted_artifact_authorizations is None:
        if trusted_authorization_record_bytes:
            _v2_authorization_evidence_reject(
                rejections,
                "Authorization bytes were supplied without trusted authorizations.",
                None,
            )
        return {}
    if not isinstance(trusted_artifact_authorizations, Mapping):
        _v2_artifact_authorization_reject(
            rejections,
            "trusted_artifact_authorizations must be a verifier-supplied mapping.",
            None,
        )
        return {}
    if trusted_authorization_record_bytes is not None and not isinstance(
        trusted_authorization_record_bytes, Mapping
    ):
        _v2_authorization_evidence_reject(
            rejections,
            "trusted_authorization_record_bytes must be a mapping.",
            None,
        )
        return {}
    trusted_by_artifact: dict[str, Mapping[str, Any]] = {}
    local_record_ids: set[str] = set()
    authorization_ids: set[str] = set()
    for artifact_key, entry in trusted_artifact_authorizations.items():
        if not _is_non_empty_string(artifact_key) or not isinstance(
            entry, Mapping
        ):
            _v2_artifact_authorization_reject(
                rejections,
                "Trusted authorization keys must identify artifact mappings.",
                artifact_key if isinstance(artifact_key, str) else None,
            )
            continue
        if not _check_exact_fields(
            entry,
            _IMMUTABLE_V2_TRUSTED_ARTIFACT_AUTHORIZATION_FIELDS,
            "Trusted artifact authorization",
            rejections,
            artifact_key,
        ):
            continue
        authorization = entry["authorization"]
        verification = entry["authorization_record_verification"]
        if not isinstance(authorization, Mapping):
            _v2_artifact_authorization_reject(
                rejections,
                "Trusted artifact authorization must contain a mapping.",
                artifact_key,
            )
            continue
        valid = _validate_v2_artifact_authorization_record(
            authorization, rejections
        )
        if authorization.get("artifact_id") != artifact_key:
            valid = False
            _v2_artifact_authorization_reject(
                rejections,
                "Trusted authorization map key and artifact_id differ.",
                artifact_key,
            )
        authorization_id = authorization.get("authorization_id")
        if isinstance(authorization_id, str):
            if authorization_id in authorization_ids:
                valid = False
                _v2_artifact_authorization_reject(
                    rejections,
                    "Duplicate trusted authorization_id.",
                    authorization_id,
                )
            authorization_ids.add(authorization_id)
        if not isinstance(verification, Mapping) or not _check_exact_fields(
            verification,
            _IMMUTABLE_V2_AUTHORIZATION_VERIFICATION_FIELDS,
            "Trusted authorization-record verification",
            rejections,
            artifact_key,
        ):
            _v2_authorization_evidence_reject(
                rejections,
                "Trusted authorization requires exact verification evidence.",
                artifact_key,
            )
            continue
        mode = verification["mode"]
        if (
            mode
            != authorization.get("authorization_record_verification_mode")
        ):
            valid = False
            _v2_authorization_evidence_reject(
                rejections,
                "Authorization verification modes differ.",
                artifact_key,
            )
        elif mode == "local_bytes":
            if verification["external_receipt"] is not None:
                valid = False
                _v2_authorization_evidence_reject(
                    rejections,
                    "Local authorization evidence requires a null receipt.",
                    artifact_key,
                )
            elif valid:
                local_record_ids.add(authorization["authorization_record_id"])
                valid = _validate_v2_local_authorization_record(
                    authorization,
                    trusted_authorization_record_bytes,
                    rejections,
                )
        elif mode == "external_receipt" and valid:
            valid = _validate_v2_authorization_receipt(
                authorization,
                verification["external_receipt"],
                rejections,
            )
        else:
            valid = False
        if valid:
            trusted_by_artifact[artifact_key] = entry
    if isinstance(trusted_authorization_record_bytes, Mapping):
        for record_id, payload in trusted_authorization_record_bytes.items():
            if (
                not _is_non_empty_string(record_id)
                or not isinstance(payload, bytes)
                or record_id not in local_record_ids
            ):
                _v2_authorization_evidence_reject(
                    rejections,
                    "Verifier supplied malformed or unreferenced authorization bytes.",
                    record_id if isinstance(record_id, str) else None,
                )
    return trusted_by_artifact


def _validate_v2_trusted_manifests(
    trusted_manifest_records: Mapping[str, Mapping[str, Any]] | None,
    rejections: list[ImmutableRegistryRejection],
) -> dict[str, Mapping[str, Any]]:
    if trusted_manifest_records is None:
        return {}
    if not isinstance(trusted_manifest_records, Mapping):
        _immutable_reject(
            rejections,
            ImmutableRegistryRejectionCode.INVALID_TRUSTED_MANIFEST,
            "trusted_manifest_records must be a verifier-supplied mapping.",
        )
        return {}
    trusted_by_id: dict[str, Mapping[str, Any]] = {}
    for manifest_key, manifest in trusted_manifest_records.items():
        if (
            not _is_non_empty_string(manifest_key)
            or not isinstance(manifest, Mapping)
            or not _check_exact_fields(
                manifest,
                _IMMUTABLE_V2_TRUSTED_MANIFEST_FIELDS,
                "Trusted manifest",
                rejections,
                manifest_key if isinstance(manifest_key, str) else None,
            )
        ):
            _immutable_reject(
                rejections,
                ImmutableRegistryRejectionCode.INVALID_TRUSTED_MANIFEST,
                "Trusted manifest key or record is malformed.",
                manifest_key if isinstance(manifest_key, str) else None,
            )
            continue
        valid = True
        checks = (
            manifest["manifest_id"] == manifest_key,
            _strict_hex(manifest["manifest_sha256"], 64),
            _is_non_empty_string(manifest["manifest_schema_version"]),
            _is_non_empty_string(manifest["owner_authority_id"]),
            isinstance(manifest["owner_id"], str)
            and manifest["owner_id"] in IMMUTABLE_V2_OWNER_IDS,
            _strict_hex(manifest["owner_authority_revision"], 40),
            isinstance(manifest["owner_status"], str)
            and manifest["owner_status"] in IMMUTABLE_V2_OWNER_STATUSES,
            isinstance(manifest["decision"], str)
            and manifest["decision"] in IMMUTABLE_V2_AUTHORITY_DECISIONS,
            IMMUTABLE_V2_OWNER_STATUS_DECISIONS.get(manifest["owner_status"])
            == manifest["decision"],
            isinstance(manifest["artifact_identities"], list),
            bool(manifest["artifact_identities"]),
        )
        if not all(checks):
            valid = False
        artifact_ids: set[str] = set()
        manifest_identities: set[str] = set()
        for entry in (
            manifest["artifact_identities"]
            if isinstance(manifest["artifact_identities"], list)
            else []
        ):
            if not isinstance(entry, Mapping) or not _check_exact_fields(
                entry,
                _IMMUTABLE_V2_TRUSTED_MANIFEST_ARTIFACT_FIELDS,
                "Trusted manifest artifact identity",
                rejections,
                manifest_key,
            ):
                valid = False
                continue
            entry_checks = (
                _is_non_empty_string(entry["artifact_id"]),
                isinstance(entry["artifact_type"], str)
                and entry["artifact_type"] in IMMUTABLE_V2_ARTIFACT_TYPES,
                _is_non_empty_string(entry["artifact_schema_version"]),
                _strict_hex(entry["artifact_sha256"], 64),
                _is_non_negative_integer(entry["artifact_size_bytes"]),
                _is_non_empty_string(entry["manifest_artifact_identity"]),
                isinstance(entry["artifact_type"], str)
                and isinstance(manifest["owner_id"], str)
                and manifest["owner_id"]
                in IMMUTABLE_V2_ARTIFACT_OWNER_IDS.get(
                    entry["artifact_type"], frozenset()
                ),
            )
            if not all(entry_checks):
                valid = False
            if (
                entry["artifact_id"] in artifact_ids
                or entry["manifest_artifact_identity"] in manifest_identities
            ):
                valid = False
            artifact_ids.add(entry["artifact_id"])
            manifest_identities.add(entry["manifest_artifact_identity"])
        if not valid:
            _immutable_reject(
                rejections,
                ImmutableRegistryRejectionCode.INVALID_TRUSTED_MANIFEST,
                "Trusted manifest does not bind unique exact artifact identities.",
                manifest_key,
            )
            continue
        trusted_by_id[manifest_key] = manifest
    return trusted_by_id


def _validate_v2_trusted_artifact_receipts(
    trusted_artifact_receipts: Mapping[str, Mapping[str, Any]] | None,
    rejections: list[ImmutableRegistryRejection],
) -> dict[str, Mapping[str, Any]]:
    if trusted_artifact_receipts is None:
        return {}
    if not isinstance(trusted_artifact_receipts, Mapping):
        _immutable_reject(
            rejections,
            ImmutableRegistryRejectionCode.INVALID_TRUSTED_ARTIFACT_RECEIPT,
            "trusted_artifact_receipts must be a verifier-supplied mapping.",
        )
        return {}
    trusted_by_id: dict[str, Mapping[str, Any]] = {}
    for receipt_key, receipt in trusted_artifact_receipts.items():
        if (
            not _is_non_empty_string(receipt_key)
            or not isinstance(receipt, Mapping)
            or not _check_exact_fields(
                receipt,
                _IMMUTABLE_V2_TRUSTED_ARTIFACT_RECEIPT_FIELDS,
                "Trusted artifact receipt",
                rejections,
                receipt_key if isinstance(receipt_key, str) else None,
            )
        ):
            _immutable_reject(
                rejections,
                ImmutableRegistryRejectionCode.INVALID_TRUSTED_ARTIFACT_RECEIPT,
                "Trusted artifact receipt key or record is malformed.",
                receipt_key if isinstance(receipt_key, str) else None,
            )
            continue
        checks = (
            receipt["receipt_id"] == receipt_key,
            _strict_hex(receipt["receipt_sha256"], 64),
            _strict_hex(receipt["receipt_authority_revision"], 40),
            _is_non_empty_string(receipt["verified_artifact_id"]),
            isinstance(receipt["verified_artifact_type"], str)
            and receipt["verified_artifact_type"]
            in IMMUTABLE_V2_ARTIFACT_TYPES,
            _is_non_empty_string(receipt["verified_artifact_schema_version"]),
            _strict_hex(receipt["verified_artifact_sha256"], 64),
            _is_non_negative_integer(receipt["verified_artifact_size"]),
            isinstance(receipt["verified_owner_id"], str)
            and receipt["verified_owner_id"] in IMMUTABLE_V2_OWNER_IDS,
            _strict_hex(receipt["verified_owner_authority_revision"], 40),
            _is_non_empty_string(receipt["verified_manifest_id"]),
            _strict_hex(receipt["verified_manifest_sha256"], 64),
            _is_non_empty_string(
                receipt["verified_manifest_artifact_identity"]
            ),
        )
        if not all(checks):
            _immutable_reject(
                rejections,
                ImmutableRegistryRejectionCode.INVALID_TRUSTED_ARTIFACT_RECEIPT,
                "Trusted artifact receipt fields are malformed.",
                receipt_key,
            )
            continue
        trusted_by_id[receipt_key] = receipt
    return trusted_by_id


def _validate_v2_manifest_record(
    record: Mapping[str, Any],
    rejections: list[ImmutableRegistryRejection],
) -> bool:
    manifest_id = (
        record.get("manifest_id")
        if isinstance(record.get("manifest_id"), str)
        else None
    )
    if not _check_exact_fields(
        record,
        _IMMUTABLE_V2_MANIFEST_FIELDS,
        "Manifest record",
        rejections,
        manifest_id,
    ):
        return False
    valid = True
    checks = (
        (
            record["schema_version"] == SCHEMA_VERSION,
            "Manifest schema_version is unsupported.",
        ),
        (
            _is_non_empty_string(record["manifest_id"]),
            "manifest_id must be non-empty.",
        ),
        (
            _strict_hex(record["manifest_sha256"], 64),
            "Manifest hash must be SHA-256.",
        ),
        (
            _is_non_empty_string(record["manifest_schema_version"]),
            "Manifest schema/version must be explicit.",
        ),
        (
            _is_non_empty_string(record["owner_authority_id"]),
            "Manifest owner_authority_id must be non-empty.",
        ),
        (
            isinstance(record["decision"], str)
            and record["decision"] in IMMUTABLE_V2_MANIFEST_DECISIONS,
            "Manifest decision is unsupported.",
        ),
        (
            _strict_id_list(record["artifact_identities"])
            and bool(record["artifact_identities"]),
            "Manifest artifact identities must be a non-empty duplicate-free list.",
        ),
    )
    for accepted, message in checks:
        if accepted:
            continue
        valid = False
        _immutable_reject(
            rejections,
            ImmutableRegistryRejectionCode.INVALID_MANIFEST,
            message,
            manifest_id,
        )
    return valid


def _validate_v2_byte_verification_record(
    record: Mapping[str, Any],
    rejections: list[ImmutableRegistryRejection],
) -> bool:
    verification_id = (
        record.get("verification_id")
        if isinstance(record.get("verification_id"), str)
        else None
    )
    if not _check_exact_fields(
        record,
        _IMMUTABLE_V2_BYTE_VERIFICATION_FIELDS,
        "Byte-verification record",
        rejections,
        verification_id,
    ):
        return False
    valid = True
    checks = (
        (
            record["schema_version"] == SCHEMA_VERSION,
            "Byte-verification schema_version is unsupported.",
        ),
        (
            _is_non_empty_string(record["verification_id"]),
            "verification_id must be non-empty.",
        ),
        (
            _is_non_empty_string(record["artifact_id"]),
            "Byte verification requires an artifact_id.",
        ),
        (
            isinstance(record["mode"], str)
            and record["mode"] in IMMUTABLE_V2_BYTE_VERIFICATION_MODES,
            "Byte-verification mode is unsupported.",
        ),
        (
            _strict_hex(record["verified_sha256"], 64),
            "Verified artifact hash must be SHA-256.",
        ),
        (
            _is_non_negative_integer(record["verified_size_bytes"]),
            "Verified artifact size must be a non-negative integer.",
        ),
        (
            _utc_timestamp(record["verified_at"]) is not None,
            "Byte verification requires an explicit UTC timestamp.",
        ),
    )
    for accepted, message in checks:
        if accepted:
            continue
        valid = False
        _immutable_reject(
            rejections,
            ImmutableRegistryRejectionCode.INVALID_BYTE_VERIFICATION,
            message,
            verification_id,
        )
    if record["mode"] == "local_bytes":
        if any(
            record[field] is not None
            for field in (
                "external_receipt_id",
                "external_receipt_sha256",
                "external_receipt_authority_revision",
            )
        ):
            valid = False
            _immutable_reject(
                rejections,
                ImmutableRegistryRejectionCode.INVALID_BYTE_VERIFICATION,
                "Local-byte verification requires null external receipt fields.",
                verification_id,
            )
    elif record["mode"] == "external_receipt":
        external_checks = (
            _is_non_empty_string(record["external_receipt_id"]),
            _strict_hex(record["external_receipt_sha256"], 64),
            _strict_hex(record["external_receipt_authority_revision"], 40),
        )
        if not all(external_checks):
            valid = False
            _immutable_reject(
                rejections,
                ImmutableRegistryRejectionCode.INVALID_BYTE_VERIFICATION,
                "External verification requires exact receipt identity, hash, and revision.",
                verification_id,
            )
    return valid


def _validate_v2_run_record(
    run: Mapping[str, Any],
    rejections: list[ImmutableRegistryRejection],
) -> bool:
    run_id = run.get("run_id") if isinstance(run.get("run_id"), str) else None
    if not _check_exact_fields(
        run,
        _IMMUTABLE_V2_RUN_FIELDS,
        "Immutable registry v2 run",
        rejections,
        run_id,
    ):
        return False
    valid = True
    if not _is_non_empty_string(run["run_id"]):
        valid = False
        _immutable_reject(
            rejections,
            ImmutableRegistryRejectionCode.MISSING_RUN_ID,
            "run_id must be a non-empty immutable identifier.",
            run_id,
        )
    if run["schema_version"] != SCHEMA_VERSION:
        valid = False
        _immutable_reject(
            rejections,
            ImmutableRegistryRejectionCode.UNSUPPORTED_SCHEMA_VERSION,
            "Run schema_version is unsupported.",
            run_id,
        )
    if not _strict_hex(run["code_sha"], 40):
        valid = False
        _immutable_reject(
            rejections,
            ImmutableRegistryRejectionCode.INVALID_RUN,
            "Run code_sha must be an exact full Git commit.",
            run_id,
        )
    if not isinstance(run["git_dirty"], bool):
        valid = False
        _immutable_reject(
            rejections,
            ImmutableRegistryRejectionCode.INVALID_RUN,
            "Run git_dirty must be boolean.",
            run_id,
        )
    for field in (
        "config_snapshot_hash",
        "checkpoint_hash",
        "data_identity_hash",
        "preprocess_hash",
        "environment_hash",
    ):
        if _strict_hex(run[field], 64):
            continue
        valid = False
        _immutable_reject(
            rejections,
            ImmutableRegistryRejectionCode.INVALID_RUN,
            f"Run {field} must be SHA-256.",
            run_id,
        )
    seeds = run["seeds"]
    if (
        not isinstance(seeds, Mapping)
        or not seeds
        or any(not _is_non_empty_string(key) for key in seeds)
        or any(
            not isinstance(seed, int) or isinstance(seed, bool)
            for seed in seeds.values()
        )
    ):
        valid = False
        _immutable_reject(
            rejections,
            ImmutableRegistryRejectionCode.INVALID_RUN,
            "Run seeds must be a non-empty mapping of names to integers.",
            run_id,
        )
    command = run["command"]
    if (
        not isinstance(command, list)
        or not command
        or any(not _is_non_empty_string(part) for part in command)
    ):
        valid = False
        _immutable_reject(
            rejections,
            ImmutableRegistryRejectionCode.INVALID_RUN,
            "Run command must be a non-empty list of strings.",
            run_id,
        )
    if (
        not isinstance(run["owner"], str)
        or run["owner"] not in IMMUTABLE_V2_OWNER_IDS
    ):
        valid = False
        _immutable_reject(
            rejections,
            ImmutableRegistryRejectionCode.INVALID_RUN,
            "Run owner is outside the closed owner catalog.",
            run_id,
        )
    for field in ("input_artifact_ids", "output_artifact_ids"):
        if _strict_id_list(run[field]):
            continue
        valid = False
        _immutable_reject(
            rejections,
            ImmutableRegistryRejectionCode.AMBIGUOUS_LINEAGE,
            f"Run {field} must be a duplicate-free ID list.",
            run_id,
        )
    for field in ("parent_run_id", "supersedes_run_id"):
        if run[field] is None or _is_non_empty_string(run[field]):
            continue
        valid = False
        _immutable_reject(
            rejections,
            ImmutableRegistryRejectionCode.INVALID_RUN,
            f"Run {field} must be null or a non-empty ID.",
            run_id,
        )
    if run["supersedes_run_id"] is None:
        if run["supersession_reason"] is not None:
            valid = False
            _immutable_reject(
                rejections,
                ImmutableRegistryRejectionCode.MALFORMED_SUPERSESSION,
                "A run without supersedes_run_id requires null supersession_reason.",
                run_id,
            )
    elif not _is_non_empty_string(run["supersession_reason"]):
        valid = False
        _immutable_reject(
            rejections,
            ImmutableRegistryRejectionCode.MALFORMED_SUPERSESSION,
            "A superseding run requires a non-empty supersession_reason.",
            run_id,
        )

    created_at = _utc_timestamp(run["created_at"])
    started_at = (
        None if run["started_at"] is None else _utc_timestamp(run["started_at"])
    )
    ended_at = None if run["ended_at"] is None else _utc_timestamp(run["ended_at"])
    status = run["status"]
    if created_at is None:
        valid = False
        _immutable_reject(
            rejections,
            ImmutableRegistryRejectionCode.INVALID_RUN,
            "Run created_at must be an explicit UTC timestamp.",
            run_id,
        )
    if (
        not isinstance(status, str)
        or status not in IMMUTABLE_V2_RUN_STATUSES
    ):
        valid = False
        _immutable_reject(
            rejections,
            ImmutableRegistryRejectionCode.INVALID_RUN,
            "Run status is unsupported.",
            run_id,
        )
    elif status == "pending":
        if (
            run["started_at"] is not None
            or run["ended_at"] is not None
            or not _is_non_empty_string(run["pending_reason"])
            or run["failure_reason"] is not None
            or run["output_artifact_ids"]
        ):
            valid = False
            _immutable_reject(
                rejections,
                ImmutableRegistryRejectionCode.INVALID_RUN,
                "Pending runs require a pending reason and no start, end, failure, or outputs.",
                run_id,
            )
    elif status == "running":
        if (
            started_at is None
            or (
                created_at is not None
                and started_at is not None
                and started_at < created_at
            )
            or run["ended_at"] is not None
            or run["pending_reason"] is not None
            or run["failure_reason"] is not None
            or run["output_artifact_ids"]
        ):
            valid = False
            _immutable_reject(
                rejections,
                ImmutableRegistryRejectionCode.INVALID_RUN,
                "Running runs require a start and no end, reasons, or published outputs.",
                run_id,
            )
    else:
        if (
            started_at is None
            or ended_at is None
            or (
                created_at is not None
                and started_at is not None
                and started_at < created_at
            )
            or (
                started_at is not None
                and ended_at is not None
                and ended_at < started_at
            )
            or run["pending_reason"] is not None
        ):
            valid = False
            _immutable_reject(
                rejections,
                ImmutableRegistryRejectionCode.INVALID_RUN,
                "Terminal runs require ordered timestamps and null pending_reason.",
                run_id,
            )
        if status == "failed" and not _is_non_empty_string(
            run["failure_reason"]
        ):
            valid = False
            _immutable_reject(
                rejections,
                ImmutableRegistryRejectionCode.INVALID_RUN,
                "Failed runs require a failure_reason.",
                run_id,
            )
        if status == "completed" and run["failure_reason"] is not None:
            valid = False
            _immutable_reject(
                rejections,
                ImmutableRegistryRejectionCode.INVALID_RUN,
                "Completed runs require null failure_reason.",
                run_id,
            )
    return valid


def _validate_v2_artifact_record(
    artifact: Mapping[str, Any],
    rejections: list[ImmutableRegistryRejection],
) -> bool:
    artifact_id = (
        artifact.get("artifact_id")
        if isinstance(artifact.get("artifact_id"), str)
        else None
    )
    if not _check_exact_fields(
        artifact,
        _IMMUTABLE_V2_ARTIFACT_FIELDS,
        "Immutable registry v2 artifact",
        rejections,
        artifact_id,
    ):
        return False
    valid = True
    checks = (
        (
            _is_non_empty_string(artifact["artifact_id"]),
            ImmutableRegistryRejectionCode.MISSING_ARTIFACT_ID,
            "artifact_id must be a non-empty immutable identifier.",
        ),
        (
            artifact["schema_version"] == SCHEMA_VERSION,
            ImmutableRegistryRejectionCode.UNSUPPORTED_SCHEMA_VERSION,
            "Artifact schema_version is unsupported.",
        ),
        (
            _is_non_empty_string(artifact["artifact_schema_version"]),
            ImmutableRegistryRejectionCode.INVALID_ARTIFACT,
            "artifact_schema_version must be explicit.",
        ),
        (
            isinstance(artifact["artifact_type"], str)
            and artifact["artifact_type"] in IMMUTABLE_V2_ARTIFACT_TYPES,
            ImmutableRegistryRejectionCode.INVALID_ARTIFACT,
            "Artifact type is outside the v2 closed catalog.",
        ),
        (
            _is_uri(artifact["uri"]),
            ImmutableRegistryRejectionCode.INVALID_ARTIFACT,
            "Artifact uri must be explicit and cannot be a bare filename.",
        ),
        (
            _strict_hex(artifact["sha256"], 64),
            ImmutableRegistryRejectionCode.INVALID_ARTIFACT,
            "Artifact sha256 must be exact hexadecimal SHA-256.",
        ),
        (
            _is_non_negative_integer(artifact["size_bytes"]),
            ImmutableRegistryRejectionCode.INVALID_ARTIFACT,
            "Artifact size_bytes must be a non-negative integer.",
        ),
        (
            _is_non_empty_string(artifact["creator_run_id"]),
            ImmutableRegistryRejectionCode.MISSING_CREATOR_RUN,
            "Artifact creator_run_id must be non-empty.",
        ),
        (
            _strict_id_list(artifact["direct_input_artifact_ids"]),
            ImmutableRegistryRejectionCode.AMBIGUOUS_LINEAGE,
            "Artifact direct inputs must be a duplicate-free ID list.",
        ),
        (
            isinstance(artifact["status"], str)
            and artifact["status"] in IMMUTABLE_ARTIFACT_STATUSES,
            ImmutableRegistryRejectionCode.INVALID_ARTIFACT,
            "Artifact status is unsupported.",
        ),
        (
            _is_non_empty_string(artifact["owner_authority_id"]),
            ImmutableRegistryRejectionCode.INVALID_AUTHORITY,
            "Artifact owner_authority_id must be explicit.",
        ),
        (
            _strict_hex(artifact["owner_authority_revision"], 40),
            ImmutableRegistryRejectionCode.INVALID_AUTHORITY,
            "Artifact owner authority revision must be a full Git commit.",
        ),
        (
            _is_non_empty_string(artifact["owner_status_record_id"]),
            ImmutableRegistryRejectionCode.INVALID_AUTHORITY,
            "Artifact owner status-record identity must be explicit.",
        ),
        (
            _strict_hex(artifact["owner_status_record_sha256"], 64),
            ImmutableRegistryRejectionCode.INVALID_AUTHORITY,
            "Artifact owner status-record hash must be SHA-256.",
        ),
        (
            isinstance(artifact["owner_decision"], str)
            and artifact["owner_decision"]
            in IMMUTABLE_V2_AUTHORITY_DECISIONS,
            ImmutableRegistryRejectionCode.INVALID_AUTHORITY,
            "Artifact owner decision is unsupported.",
        ),
        (
            _is_non_empty_string(artifact["manifest_id"]),
            ImmutableRegistryRejectionCode.INVALID_MANIFEST,
            "Artifact manifest_id must be explicit.",
        ),
        (
            _strict_hex(artifact["manifest_sha256"], 64),
            ImmutableRegistryRejectionCode.INVALID_MANIFEST,
            "Artifact manifest hash must be SHA-256.",
        ),
        (
            _is_non_empty_string(artifact["manifest_schema_version"]),
            ImmutableRegistryRejectionCode.INVALID_MANIFEST,
            "Artifact manifest schema/version must be explicit.",
        ),
        (
            _is_non_empty_string(artifact["manifest_artifact_identity"]),
            ImmutableRegistryRejectionCode.INVALID_MANIFEST,
            "Artifact identity within its manifest must be explicit.",
        ),
    )
    for accepted, code, message in checks:
        if accepted:
            continue
        valid = False
        _immutable_reject(rejections, code, message, artifact_id)

    status = artifact["status"]
    if status == "accepted":
        lifecycle_valid = (
            artifact["status_reason"] is None
            and artifact["superseded_by"] is None
        )
    elif status == "excluded":
        lifecycle_valid = (
            _is_non_empty_string(artifact["status_reason"])
            and artifact["superseded_by"] is None
        )
    else:
        lifecycle_valid = (
            _is_non_empty_string(artifact["status_reason"])
            and _is_non_empty_string(artifact["superseded_by"])
        )
    if not lifecycle_valid:
        valid = False
        _immutable_reject(
            rejections,
            ImmutableRegistryRejectionCode.MALFORMED_SUPERSESSION,
            "Artifact lifecycle fields disagree with status.",
            artifact_id,
        )
    if isinstance(status, str) and status in {"accepted", "superseded"}:
        if not _is_non_empty_string(artifact["byte_verification_id"]):
            valid = False
            _immutable_reject(
                rejections,
                ImmutableRegistryRejectionCode.UNVERIFIED_ARTIFACT,
                "Accepted or superseded artifacts require byte-verification evidence.",
                artifact_id,
            )
    elif artifact["byte_verification_id"] is not None and not _is_non_empty_string(
        artifact["byte_verification_id"]
    ):
        valid = False
        _immutable_reject(
            rejections,
            ImmutableRegistryRejectionCode.INVALID_BYTE_VERIFICATION,
            "Excluded artifact byte_verification_id must be null or non-empty.",
            artifact_id,
        )
    return valid


def _validate_v2_transition(
    document: Mapping[str, Any],
    previous_registry: Any,
    rejections: list[ImmutableRegistryRejection],
    artifact_bytes_by_id: Mapping[str, bytes] | None,
    trusted_owner_authorities: Mapping[str, Mapping[str, Any]] | None,
    trusted_status_record_bytes: Mapping[str, bytes] | None,
    trusted_artifact_authorizations: Mapping[str, Mapping[str, Any]] | None,
    trusted_authorization_record_bytes: Mapping[str, bytes] | None,
    trusted_manifest_records: Mapping[str, Mapping[str, Any]] | None,
    trusted_artifact_receipts: Mapping[str, Mapping[str, Any]] | None,
) -> None:
    previous_result = validate_immutable_run_artifact_registry(
        previous_registry,
        artifact_bytes_by_id=artifact_bytes_by_id,
        trusted_owner_authorities=trusted_owner_authorities,
        trusted_status_record_bytes=trusted_status_record_bytes,
        trusted_artifact_authorizations=trusted_artifact_authorizations,
        trusted_authorization_record_bytes=trusted_authorization_record_bytes,
        trusted_manifest_records=trusted_manifest_records,
        trusted_artifact_receipts=trusted_artifact_receipts,
    )
    if (
        not previous_result.accepted
        or not isinstance(previous_registry, Mapping)
        or previous_registry.get("immutable_registry_schema_version")
        != IMMUTABLE_REGISTRY_V2_SCHEMA_VERSION
    ):
        _immutable_reject(
            rejections,
            ImmutableRegistryRejectionCode.INVALID_DOCUMENT,
            "previous_registry must be a valid immutable registry v2 document.",
        )
        return
    for field in (
        "schema_version",
        "immutable_registry_schema_version",
        "registry_id",
        "synthetic",
        "scientific_use",
    ):
        if previous_registry[field] != document[field]:
            _immutable_reject(
                rejections,
                ImmutableRegistryRejectionCode.UNVERSIONED_SCHEMA_CHANGE,
                f"Registry v2 field {field!r} changed in place.",
            )

    for field, identity in (
        ("owner_authorities", "authority_id"),
        ("manifests", "manifest_id"),
        ("byte_verifications", "verification_id"),
    ):
        current = {record[identity]: record for record in document[field]}
        for prior in previous_registry[field]:
            if current.get(prior[identity]) != prior:
                _immutable_reject(
                    rejections,
                    ImmutableRegistryRejectionCode.IMMUTABLE_ARTIFACT_MUTATION,
                    f"Existing v2 {field} record {prior[identity]!r} changed or disappeared.",
                    prior[identity],
                )

    current_runs = {run["run_id"]: run for run in document["runs"]}
    mutable_by_transition = {
        "pending": {
            "status",
            "started_at",
            "ended_at",
            "pending_reason",
            "failure_reason",
            "output_artifact_ids",
        },
        "running": {
            "status",
            "ended_at",
            "failure_reason",
            "output_artifact_ids",
        },
    }
    allowed_next = {
        "pending": {"pending", "running", "completed", "failed"},
        "running": {"running", "completed", "failed"},
    }
    for prior in previous_registry["runs"]:
        current = current_runs.get(prior["run_id"])
        if current is None:
            _immutable_reject(
                rejections,
                ImmutableRegistryRejectionCode.COMPLETED_RUN_MUTATION,
                f"Existing v2 run {prior['run_id']!r} was removed.",
                prior["run_id"],
            )
            continue
        prior_status = prior["status"]
        if prior_status in {"completed", "failed"}:
            if current != prior:
                _immutable_reject(
                    rejections,
                    ImmutableRegistryRejectionCode.COMPLETED_RUN_MUTATION,
                    f"Terminal v2 run {prior['run_id']!r} changed.",
                    prior["run_id"],
                )
            continue
        if current["status"] not in allowed_next[prior_status]:
            _immutable_reject(
                rejections,
                ImmutableRegistryRejectionCode.ILLEGAL_RUN_STATUS_TRANSITION,
                f"Run {prior['run_id']!r} has an illegal v2 status transition.",
                prior["run_id"],
            )
            continue
        mutable = mutable_by_transition[prior_status]
        for field in _IMMUTABLE_V2_RUN_FIELDS - mutable:
            if current[field] != prior[field]:
                _immutable_reject(
                    rejections,
                    ImmutableRegistryRejectionCode.ILLEGAL_RUN_STATUS_TRANSITION,
                    f"Run {prior['run_id']!r} changed immutable field {field!r}.",
                    prior["run_id"],
                )

    current_artifacts = {
        artifact["artifact_id"]: artifact for artifact in document["artifacts"]
    }
    for prior in previous_registry["artifacts"]:
        current = current_artifacts.get(prior["artifact_id"])
        if current is None:
            _immutable_reject(
                rejections,
                ImmutableRegistryRejectionCode.IMMUTABLE_ARTIFACT_MUTATION,
                f"Existing v2 artifact {prior['artifact_id']!r} was removed.",
                prior["artifact_id"],
            )
            continue
        if current == prior:
            continue
        lifecycle_fields = {"status", "status_reason", "superseded_by"}
        unchanged = all(
            current[field] == prior[field]
            for field in _IMMUTABLE_V2_ARTIFACT_FIELDS - lifecycle_fields
        )
        if not (
            prior["status"] == "accepted"
            and current["status"] == "superseded"
            and unchanged
        ):
            _immutable_reject(
                rejections,
                ImmutableRegistryRejectionCode.IMMUTABLE_ARTIFACT_MUTATION,
                f"Artifact {prior['artifact_id']!r} changed outside supersession.",
                prior["artifact_id"],
            )


def _validate_immutable_run_artifact_registry_v2(
    document: Any,
    *,
    previous_registry: Any = None,
    artifact_bytes_by_id: Mapping[str, bytes] | None = None,
    trusted_owner_authorities: Mapping[str, Mapping[str, Any]] | None = None,
    trusted_status_record_bytes: Mapping[str, bytes] | None = None,
    trusted_artifact_authorizations: Mapping[str, Mapping[str, Any]]
    | None = None,
    trusted_authorization_record_bytes: Mapping[str, bytes] | None = None,
    trusted_manifest_records: Mapping[str, Mapping[str, Any]] | None = None,
    trusted_artifact_receipts: Mapping[str, Mapping[str, Any]] | None = None,
) -> ImmutableRegistryValidationResult:
    """Validate immutable registry v2 authority, manifest, bytes, and lineage."""

    rejections: list[ImmutableRegistryRejection] = []
    if not isinstance(document, Mapping):
        _immutable_reject(
            rejections,
            ImmutableRegistryRejectionCode.INVALID_DOCUMENT,
            "Immutable registry v2 must be a mapping.",
        )
        return ImmutableRegistryValidationResult(False, tuple(rejections))
    if not _check_exact_fields(
        document,
        _IMMUTABLE_V2_REGISTRY_FIELDS,
        "Immutable registry v2",
        rejections,
    ):
        return ImmutableRegistryValidationResult(False, tuple(rejections))
    if (
        document["schema_version"] != SCHEMA_VERSION
        or document["immutable_registry_schema_version"]
        != IMMUTABLE_REGISTRY_V2_SCHEMA_VERSION
    ):
        _immutable_reject(
            rejections,
            ImmutableRegistryRejectionCode.UNSUPPORTED_SCHEMA_VERSION,
            "Immutable registry v2 schema version is unsupported.",
        )
    if not _is_non_empty_string(document["registry_id"]):
        _immutable_reject(
            rejections,
            ImmutableRegistryRejectionCode.INVALID_DOCUMENT,
            "registry_id must be non-empty.",
        )
    if not isinstance(document["synthetic"], bool):
        _immutable_reject(
            rejections,
            ImmutableRegistryRejectionCode.INVALID_DOCUMENT,
            "synthetic must be boolean.",
        )
    if (
        not isinstance(document["scientific_use"], str)
        or document["scientific_use"] not in {"forbidden", "permitted"}
    ):
        _immutable_reject(
            rejections,
            ImmutableRegistryRejectionCode.INVALID_DOCUMENT,
            "scientific_use must be forbidden or permitted.",
        )
    if document["synthetic"] is True and document["scientific_use"] != "forbidden":
        _immutable_reject(
            rejections,
            ImmutableRegistryRejectionCode.INVALID_DOCUMENT,
            "Synthetic registry v2 evidence must forbid scientific use.",
        )

    authorities = _v2_require_record_list(
        document, "owner_authorities", rejections
    )
    manifests = _v2_require_record_list(document, "manifests", rejections)
    verifications = _v2_require_record_list(
        document, "byte_verifications", rejections
    )
    runs = _v2_require_record_list(
        document, "runs", rejections, require_nonempty=True
    )
    artifacts = _v2_require_record_list(document, "artifacts", rejections)
    trusted_authority_by_id = _validate_v2_trusted_owner_authorities(
        trusted_owner_authorities,
        trusted_status_record_bytes,
        rejections,
    )
    trusted_authorization_by_artifact = (
        _validate_v2_trusted_artifact_authorizations(
            trusted_artifact_authorizations,
            trusted_authorization_record_bytes,
            rejections,
        )
    )
    trusted_manifest_by_id = _validate_v2_trusted_manifests(
        trusted_manifest_records,
        rejections,
    )
    trusted_artifact_receipt_by_id = (
        _validate_v2_trusted_artifact_receipts(
            trusted_artifact_receipts,
            rejections,
        )
    )

    authority_by_id: dict[str, Mapping[str, Any]] = {}
    authority_identity_seen: set[tuple[str, str, str]] = set()
    for index, authority in enumerate(authorities):
        if not isinstance(authority, Mapping):
            _immutable_reject(
                rejections,
                ImmutableRegistryRejectionCode.INVALID_AUTHORITY,
                f"Owner authority record {index} must be a mapping.",
            )
            continue
        shape_valid = _validate_v2_authority_record(authority, rejections)
        authority_id = authority.get("authority_id")
        if not _is_non_empty_string(authority_id):
            continue
        if authority_id in authority_by_id:
            _immutable_reject(
                rejections,
                ImmutableRegistryRejectionCode.DUPLICATE_AUTHORITY_ID,
                f"Duplicate authority_id {authority_id!r}.",
                authority_id,
            )
            continue
        if shape_valid:
            identity = (
                authority["owner_id"],
                authority["authority_revision"],
                authority["status_record_id"],
            )
            if identity in authority_identity_seen:
                _immutable_reject(
                    rejections,
                    ImmutableRegistryRejectionCode.DUPLICATE_AUTHORITY_ID,
                    f"Duplicate owner authority identity for {authority_id!r}.",
                    authority_id,
                )
            else:
                authority_identity_seen.add(identity)
            authority_by_id[authority_id] = authority

    manifest_by_id: dict[str, Mapping[str, Any]] = {}
    manifest_artifact_owners: dict[str, str] = {}
    for index, manifest in enumerate(manifests):
        if not isinstance(manifest, Mapping):
            _immutable_reject(
                rejections,
                ImmutableRegistryRejectionCode.INVALID_MANIFEST,
                f"Manifest record {index} must be a mapping.",
            )
            continue
        shape_valid = _validate_v2_manifest_record(manifest, rejections)
        manifest_id = manifest.get("manifest_id")
        if not _is_non_empty_string(manifest_id):
            continue
        if manifest_id in manifest_by_id:
            _immutable_reject(
                rejections,
                ImmutableRegistryRejectionCode.DUPLICATE_MANIFEST_ID,
                f"Duplicate manifest_id {manifest_id!r}.",
                manifest_id,
            )
            continue
        for identity in (
            manifest.get("artifact_identities")
            if _strict_id_list(manifest.get("artifact_identities"))
            else []
        ):
            prior_manifest = manifest_artifact_owners.get(identity)
            if prior_manifest is not None:
                _immutable_reject(
                    rejections,
                    ImmutableRegistryRejectionCode.DUPLICATE_MANIFEST_ID,
                    f"Manifest artifact identity {identity!r} appears in multiple manifests.",
                    manifest_id,
                )
            else:
                manifest_artifact_owners[identity] = manifest_id
        manifest_authority_id = manifest.get("owner_authority_id")
        if (
            not isinstance(manifest_authority_id, str)
            or manifest_authority_id not in authority_by_id
        ):
            shape_valid = False
            _immutable_reject(
                rejections,
                ImmutableRegistryRejectionCode.INVALID_MANIFEST,
                f"Manifest {manifest_id!r} references an unknown owner authority.",
                manifest_id,
            )
        if shape_valid:
            manifest_by_id[manifest_id] = manifest

    verification_by_id: dict[str, Mapping[str, Any]] = {}
    verification_by_artifact: dict[str, str] = {}
    for index, verification in enumerate(verifications):
        if not isinstance(verification, Mapping):
            _immutable_reject(
                rejections,
                ImmutableRegistryRejectionCode.INVALID_BYTE_VERIFICATION,
                f"Byte-verification record {index} must be a mapping.",
            )
            continue
        shape_valid = _validate_v2_byte_verification_record(
            verification, rejections
        )
        verification_id = verification.get("verification_id")
        artifact_id = verification.get("artifact_id")
        if not _is_non_empty_string(verification_id):
            continue
        if verification_id in verification_by_id:
            _immutable_reject(
                rejections,
                ImmutableRegistryRejectionCode.DUPLICATE_BYTE_VERIFICATION_ID,
                f"Duplicate verification_id {verification_id!r}.",
                verification_id,
            )
            continue
        if _is_non_empty_string(artifact_id):
            prior_verification = verification_by_artifact.get(artifact_id)
            if prior_verification is not None:
                _immutable_reject(
                    rejections,
                    ImmutableRegistryRejectionCode.DUPLICATE_BYTE_VERIFICATION_ID,
                    f"Artifact {artifact_id!r} has multiple byte verifications.",
                    verification_id,
                )
            else:
                verification_by_artifact[artifact_id] = verification_id
        if shape_valid:
            verification_by_id[verification_id] = verification

    run_by_id: dict[str, Mapping[str, Any]] = {}
    for index, run in enumerate(runs):
        if not isinstance(run, Mapping):
            _immutable_reject(
                rejections,
                ImmutableRegistryRejectionCode.INVALID_RUN,
                f"Run record {index} must be a mapping.",
            )
            continue
        shape_valid = _validate_v2_run_record(run, rejections)
        run_id = run.get("run_id")
        if not _is_non_empty_string(run_id):
            continue
        if run_id in run_by_id:
            _immutable_reject(
                rejections,
                ImmutableRegistryRejectionCode.DUPLICATE_RUN_ID,
                f"Duplicate run_id {run_id!r}.",
                run_id,
            )
        elif shape_valid:
            run_by_id[run_id] = run

    artifact_by_id: dict[str, Mapping[str, Any]] = {}
    for index, artifact in enumerate(artifacts):
        if not isinstance(artifact, Mapping):
            _immutable_reject(
                rejections,
                ImmutableRegistryRejectionCode.INVALID_ARTIFACT,
                f"Artifact record {index} must be a mapping.",
            )
            continue
        shape_valid = _validate_v2_artifact_record(artifact, rejections)
        artifact_id = artifact.get("artifact_id")
        if not _is_non_empty_string(artifact_id):
            continue
        if artifact_id in artifact_by_id:
            _immutable_reject(
                rejections,
                ImmutableRegistryRejectionCode.DUPLICATE_ARTIFACT_ID,
                f"Duplicate artifact_id {artifact_id!r}.",
                artifact_id,
            )
        elif shape_valid:
            artifact_by_id[artifact_id] = artifact

    parent_by_id: dict[str, str | None] = {}
    superseded_run_by_id: dict[str, str | None] = {}
    superseders_by_target: dict[str, list[str]] = {}
    for run_id, run in run_by_id.items():
        parent_id = run.get("parent_run_id")
        supersedes_id = run.get("supersedes_run_id")
        parent_ref = parent_id if isinstance(parent_id, str) else None
        supersedes_ref = supersedes_id if isinstance(supersedes_id, str) else None
        parent_by_id[run_id] = parent_ref
        superseded_run_by_id[run_id] = supersedes_ref
        if parent_ref is not None and parent_ref not in run_by_id:
            _immutable_reject(
                rejections,
                ImmutableRegistryRejectionCode.AMBIGUOUS_LINEAGE,
                f"Run {run_id!r} references an unknown parent.",
                run_id,
            )
        if supersedes_ref is not None:
            superseders_by_target.setdefault(supersedes_ref, []).append(run_id)
            target = run_by_id.get(supersedes_ref)
            if (
                supersedes_ref == run_id
                or target is None
                or target.get("status") != "completed"
                or target.get("owner") != run.get("owner")
            ):
                _immutable_reject(
                    rejections,
                    ImmutableRegistryRejectionCode.MALFORMED_SUPERSESSION,
                    f"Run {run_id!r} has an invalid supersedes_run_id.",
                    run_id,
                )
        if _has_reference_cycle(run_id, parent_by_id):
            _immutable_reject(
                rejections,
                ImmutableRegistryRejectionCode.AMBIGUOUS_LINEAGE,
                f"Run parent lineage containing {run_id!r} has a cycle.",
                run_id,
            )
    for run_id in superseded_run_by_id:
        if _has_reference_cycle(run_id, superseded_run_by_id):
            _immutable_reject(
                rejections,
                ImmutableRegistryRejectionCode.MALFORMED_SUPERSESSION,
                f"Run supersession containing {run_id!r} has a cycle.",
                run_id,
            )
    for target_id, superseder_ids in superseders_by_target.items():
        if len(superseder_ids) > 1:
            _immutable_reject(
                rejections,
                ImmutableRegistryRejectionCode.AMBIGUOUS_LINEAGE,
                f"Run {target_id!r} has multiple superseding runs.",
                target_id,
            )

    direct_inputs_by_artifact: dict[str, tuple[str, ...]] = {}
    superseded_artifact_by_id: dict[str, str | None] = {}
    for artifact_id, artifact in artifact_by_id.items():
        creator_id = artifact["creator_run_id"]
        creator = run_by_id.get(creator_id)
        if creator is None:
            _immutable_reject(
                rejections,
                ImmutableRegistryRejectionCode.MISSING_CREATOR_RUN,
                f"Artifact {artifact_id!r} references a nonexistent creator run.",
                artifact_id,
            )
        elif artifact_id not in creator["output_artifact_ids"]:
            _immutable_reject(
                rejections,
                ImmutableRegistryRejectionCode.AMBIGUOUS_LINEAGE,
                f"Creator run does not list artifact {artifact_id!r} as output.",
                artifact_id,
            )
        elif creator["status"] in {"pending", "running"}:
            _immutable_reject(
                rejections,
                ImmutableRegistryRejectionCode.AMBIGUOUS_LINEAGE,
                f"Pending or running run cannot publish artifact {artifact_id!r}.",
                artifact_id,
            )
        elif (
            artifact["status"] in {"accepted", "superseded"}
            and creator["status"] != "completed"
        ):
            _immutable_reject(
                rejections,
                ImmutableRegistryRejectionCode.AMBIGUOUS_LINEAGE,
                f"Accepted or superseded artifact {artifact_id!r} "
                "requires a completed run.",
                artifact_id,
            )

        authority = authority_by_id.get(artifact["owner_authority_id"])
        authority_matches = (
            authority is not None
            and creator is not None
            and authority["owner_id"] == creator["owner"]
            and authority["owner_id"]
            in IMMUTABLE_V2_ARTIFACT_OWNER_IDS[artifact["artifact_type"]]
            and authority["authority_revision"]
            == artifact["owner_authority_revision"]
            and authority["status_record_id"]
            == artifact["owner_status_record_id"]
            and authority["status_record_sha256"]
            == artifact["owner_status_record_sha256"]
            and authority["decision"] == artifact["owner_decision"]
        )
        if not authority_matches:
            _immutable_reject(
                rejections,
                ImmutableRegistryRejectionCode.OWNER_AUTHORITY_MISMATCH,
                f"Artifact {artifact_id!r} owner authority binding mismatches.",
                artifact_id,
            )
        elif artifact["status"] in {"accepted", "superseded"}:
            trusted_entry = trusted_authority_by_id.get(
                artifact["owner_authority_id"]
            )
            if trusted_entry is None:
                _immutable_reject(
                    rejections,
                    ImmutableRegistryRejectionCode.MISSING_TRUSTED_AUTHORITY,
                    f"Artifact {artifact_id!r} lacks an external owner trust anchor.",
                    artifact_id,
                )
            elif (
                trusted_entry["authority"] != authority
                or authority["owner_status"] != "accepted"
                or authority["decision"] != "accepted"
                or artifact["artifact_type"]
                not in authority["authorized_artifact_types"]
            ):
                _immutable_reject(
                    rejections,
                    ImmutableRegistryRejectionCode.OWNER_AUTHORITY_MISMATCH,
                    f"Artifact {artifact_id!r} mismatches its external owner trust anchor.",
                    artifact_id,
                )
        elif artifact["status"] == "excluded" and authority["decision"] not in {
            "excluded",
            "failed",
        }:
            _immutable_reject(
                rejections,
                ImmutableRegistryRejectionCode.OWNER_AUTHORITY_MISMATCH,
                f"Excluded artifact {artifact_id!r} has incompatible owner decision.",
                artifact_id,
            )

        manifest = manifest_by_id.get(artifact["manifest_id"])
        manifest_matches = (
            manifest is not None
            and manifest["manifest_sha256"] == artifact["manifest_sha256"]
            and manifest["manifest_schema_version"]
            == artifact["manifest_schema_version"]
            and manifest["owner_authority_id"]
            == artifact["owner_authority_id"]
            and artifact["manifest_artifact_identity"]
            in manifest["artifact_identities"]
        )
        if not manifest_matches:
            _immutable_reject(
                rejections,
                ImmutableRegistryRejectionCode.MANIFEST_MISMATCH,
                f"Artifact {artifact_id!r} manifest binding mismatches.",
                artifact_id,
            )
        elif artifact["status"] in {"accepted", "superseded"} and manifest[
            "decision"
        ] != "accepted":
            _immutable_reject(
                rejections,
                ImmutableRegistryRejectionCode.MANIFEST_MISMATCH,
                f"Artifact {artifact_id!r} lacks an accepted manifest decision.",
                artifact_id,
            )
        elif artifact["status"] == "excluded" and manifest["decision"] != "excluded":
            _immutable_reject(
                rejections,
                ImmutableRegistryRejectionCode.MANIFEST_MISMATCH,
                f"Excluded artifact {artifact_id!r} requires an excluded manifest.",
                artifact_id,
            )

        trusted_authorization: Mapping[str, Any] | None = None
        trusted_manifest: Mapping[str, Any] | None = None
        if artifact["status"] in {"accepted", "superseded"}:
            authorization_entry = trusted_authorization_by_artifact.get(
                artifact_id
            )
            if authorization_entry is None:
                _immutable_reject(
                    rejections,
                    ImmutableRegistryRejectionCode.MISSING_ARTIFACT_AUTHORIZATION,
                    f"Artifact {artifact_id!r} lacks exact external authorization.",
                    artifact_id,
                )
            else:
                trusted_authorization = authorization_entry["authorization"]
                authorization_matches = (
                    authority is not None
                    and trusted_authorization["authority_id"]
                    == artifact["owner_authority_id"]
                    and trusted_authorization["owner_id"]
                    == authority["owner_id"]
                    and trusted_authorization["owner_authority_revision"]
                    == authority["authority_revision"]
                    and trusted_authorization["artifact_id"] == artifact_id
                    and trusted_authorization["artifact_type"]
                    == artifact["artifact_type"]
                    and trusted_authorization["artifact_schema_version"]
                    == artifact["artifact_schema_version"]
                    and trusted_authorization["artifact_sha256"]
                    == artifact["sha256"]
                    and trusted_authorization["artifact_size_bytes"]
                    == artifact["size_bytes"]
                    and trusted_authorization["manifest_id"]
                    == artifact["manifest_id"]
                    and trusted_authorization["manifest_sha256"]
                    == artifact["manifest_sha256"]
                    and trusted_authorization["manifest_schema_version"]
                    == artifact["manifest_schema_version"]
                    and trusted_authorization["manifest_artifact_identity"]
                    == artifact["manifest_artifact_identity"]
                    and trusted_authorization["owner_status"] == "accepted"
                    and trusted_authorization["decision"] == "accepted"
                )
                if not authorization_matches:
                    _immutable_reject(
                        rejections,
                        ImmutableRegistryRejectionCode.INVALID_ARTIFACT_AUTHORIZATION,
                        f"Artifact {artifact_id!r} mismatches exact external authorization.",
                        artifact_id,
                    )

            trusted_manifest = trusted_manifest_by_id.get(
                artifact["manifest_id"]
            )
            if trusted_manifest is None:
                _immutable_reject(
                    rejections,
                    ImmutableRegistryRejectionCode.MISSING_TRUSTED_MANIFEST,
                    f"Artifact {artifact_id!r} lacks an external trusted manifest.",
                    artifact_id,
                )
            else:
                trusted_entries = trusted_manifest["artifact_identities"]
                matching_entries = [
                    entry
                    for entry in trusted_entries
                    if entry["artifact_id"] == artifact_id
                ]
                trusted_identity_names = [
                    entry["manifest_artifact_identity"]
                    for entry in trusted_entries
                ]
                manifest_header_matches = (
                    authority is not None
                    and manifest is not None
                    and trusted_manifest["manifest_id"]
                    == manifest["manifest_id"]
                    and trusted_manifest["manifest_sha256"]
                    == manifest["manifest_sha256"]
                    and trusted_manifest["manifest_schema_version"]
                    == manifest["manifest_schema_version"]
                    and trusted_manifest["owner_authority_id"]
                    == manifest["owner_authority_id"]
                    and trusted_manifest["owner_id"] == authority["owner_id"]
                    and trusted_manifest["owner_authority_revision"]
                    == authority["authority_revision"]
                    and trusted_manifest["owner_status"] == "accepted"
                    and trusted_manifest["decision"] == "accepted"
                    and manifest["artifact_identities"]
                    == trusted_identity_names
                )
                exact_entry_matches = (
                    len(matching_entries) == 1
                    and matching_entries[0]
                    == {
                        "artifact_id": artifact_id,
                        "artifact_type": artifact["artifact_type"],
                        "artifact_schema_version": artifact[
                            "artifact_schema_version"
                        ],
                        "artifact_sha256": artifact["sha256"],
                        "artifact_size_bytes": artifact["size_bytes"],
                        "manifest_artifact_identity": artifact[
                            "manifest_artifact_identity"
                        ],
                    }
                )
                authorization_manifest_matches = (
                    trusted_authorization is not None
                    and trusted_authorization["manifest_id"]
                    == trusted_manifest["manifest_id"]
                    and trusted_authorization["manifest_sha256"]
                    == trusted_manifest["manifest_sha256"]
                    and trusted_authorization["manifest_schema_version"]
                    == trusted_manifest["manifest_schema_version"]
                    and trusted_authorization["manifest_artifact_identity"]
                    == artifact["manifest_artifact_identity"]
                )
                if not (
                    manifest_header_matches
                    and exact_entry_matches
                    and authorization_manifest_matches
                ):
                    _immutable_reject(
                        rejections,
                        ImmutableRegistryRejectionCode.TRUSTED_MANIFEST_MISMATCH,
                        f"Artifact {artifact_id!r} mismatches its trusted manifest entry.",
                        artifact_id,
                    )

        verification_id = artifact["byte_verification_id"]
        verification = (
            verification_by_id.get(verification_id)
            if isinstance(verification_id, str)
            else None
        )
        if artifact["status"] in {"accepted", "superseded"} and verification is None:
            _immutable_reject(
                rejections,
                ImmutableRegistryRejectionCode.UNVERIFIED_ARTIFACT,
                f"Artifact {artifact_id!r} lacks byte-verification evidence.",
                artifact_id,
            )
        if verification is not None:
            if (
                verification["artifact_id"] != artifact_id
                or verification["verified_sha256"] != artifact["sha256"]
                or verification["verified_size_bytes"] != artifact["size_bytes"]
            ):
                _immutable_reject(
                    rejections,
                    ImmutableRegistryRejectionCode.UNVERIFIED_ARTIFACT,
                    f"Artifact {artifact_id!r} byte-verification binding mismatches.",
                    artifact_id,
                )
            if verification["mode"] == "local_bytes":
                payload = (
                    artifact_bytes_by_id.get(artifact_id)
                    if isinstance(artifact_bytes_by_id, Mapping)
                    else None
                )
                if (
                    not isinstance(payload, bytes)
                    or hashlib.sha256(payload).hexdigest() != artifact["sha256"]
                    or len(payload) != artifact["size_bytes"]
                ):
                    _immutable_reject(
                        rejections,
                        ImmutableRegistryRejectionCode.UNVERIFIED_ARTIFACT,
                        f"Artifact {artifact_id!r} local bytes were not supplied or verified.",
                        artifact_id,
                    )
            elif (
                verification["mode"] == "external_receipt"
                and artifact["status"] in {"accepted", "superseded"}
            ):
                receipt_id = verification["external_receipt_id"]
                trusted_receipt = (
                    trusted_artifact_receipt_by_id.get(receipt_id)
                    if isinstance(receipt_id, str)
                    else None
                )
                if trusted_receipt is None:
                    _immutable_reject(
                        rejections,
                        ImmutableRegistryRejectionCode.MISSING_TRUSTED_ARTIFACT_RECEIPT,
                        f"Artifact {artifact_id!r} lacks an external trusted receipt.",
                        artifact_id,
                    )
                else:
                    receipt_matches = (
                        authority is not None
                        and trusted_receipt["receipt_id"]
                        == verification["external_receipt_id"]
                        and trusted_receipt["receipt_sha256"]
                        == verification["external_receipt_sha256"]
                        and trusted_receipt["receipt_authority_revision"]
                        == verification["external_receipt_authority_revision"]
                        and trusted_receipt["verified_artifact_id"]
                        == artifact_id
                        and trusted_receipt["verified_artifact_type"]
                        == artifact["artifact_type"]
                        and trusted_receipt[
                            "verified_artifact_schema_version"
                        ]
                        == artifact["artifact_schema_version"]
                        and trusted_receipt["verified_artifact_sha256"]
                        == artifact["sha256"]
                        and trusted_receipt["verified_artifact_size"]
                        == artifact["size_bytes"]
                        and trusted_receipt["verified_owner_id"]
                        == authority["owner_id"]
                        and trusted_receipt[
                            "verified_owner_authority_revision"
                        ]
                        == authority["authority_revision"]
                        and trusted_receipt["verified_manifest_id"]
                        == artifact["manifest_id"]
                        and trusted_receipt["verified_manifest_sha256"]
                        == artifact["manifest_sha256"]
                        and trusted_receipt[
                            "verified_manifest_artifact_identity"
                        ]
                        == artifact["manifest_artifact_identity"]
                    )
                    if not receipt_matches:
                        _immutable_reject(
                            rejections,
                            ImmutableRegistryRejectionCode.TRUSTED_ARTIFACT_RECEIPT_MISMATCH,
                            f"Artifact {artifact_id!r} external receipt mismatches.",
                            artifact_id,
                        )

        direct_inputs = artifact["direct_input_artifact_ids"]
        direct_inputs_by_artifact[artifact_id] = tuple(direct_inputs)
        for input_id in direct_inputs:
            source = artifact_by_id.get(input_id)
            if input_id == artifact_id or source is None:
                _immutable_reject(
                    rejections,
                    ImmutableRegistryRejectionCode.BROKEN_DIRECT_INPUT,
                    f"Artifact {artifact_id!r} has a missing or self direct input.",
                    artifact_id,
                )
                continue
            if creator is not None and input_id not in creator["input_artifact_ids"]:
                _immutable_reject(
                    rejections,
                    ImmutableRegistryRejectionCode.AMBIGUOUS_LINEAGE,
                    f"Artifact {artifact_id!r} direct input is absent from its creator run.",
                    artifact_id,
                )
            source_creator = run_by_id.get(source["creator_run_id"])
            if artifact["status"] == "accepted" and (
                source["status"] != "accepted"
                or source_creator is None
                or source_creator["status"] != "completed"
            ):
                _immutable_reject(
                    rejections,
                    ImmutableRegistryRejectionCode.AMBIGUOUS_LINEAGE,
                    f"Accepted artifact {artifact_id!r} depends on an unusable input.",
                    artifact_id,
                )

        replacement_id = artifact["superseded_by"]
        superseded_artifact_by_id[artifact_id] = (
            replacement_id if isinstance(replacement_id, str) else None
        )
        if isinstance(replacement_id, str):
            replacement = artifact_by_id.get(replacement_id)
            replacement_creator = (
                run_by_id.get(replacement["creator_run_id"])
                if replacement is not None
                else None
            )
            replacement_authority = (
                authority_by_id.get(replacement["owner_authority_id"])
                if replacement is not None
                else None
            )
            if (
                replacement_id == artifact_id
                or replacement is None
                or replacement["artifact_type"] != artifact["artifact_type"]
                or replacement["status"] != "accepted"
                or replacement_creator is None
                or replacement_creator["supersedes_run_id"] != creator_id
                or authority is None
                or replacement_authority is None
                or replacement_authority["owner_id"] != authority["owner_id"]
            ):
                _immutable_reject(
                    rejections,
                    ImmutableRegistryRejectionCode.MALFORMED_SUPERSESSION,
                    f"Artifact {artifact_id!r} has an invalid replacement.",
                    artifact_id,
                )

    for artifact_id in direct_inputs_by_artifact:
        if _artifact_lineage_has_cycle(artifact_id, direct_inputs_by_artifact):
            _immutable_reject(
                rejections,
                ImmutableRegistryRejectionCode.AMBIGUOUS_LINEAGE,
                f"Artifact direct-input lineage containing {artifact_id!r} has a cycle.",
                artifact_id,
            )
    for artifact_id in superseded_artifact_by_id:
        if _has_reference_cycle(artifact_id, superseded_artifact_by_id):
            _immutable_reject(
                rejections,
                ImmutableRegistryRejectionCode.MALFORMED_SUPERSESSION,
                f"Artifact supersession containing {artifact_id!r} has a cycle.",
                artifact_id,
            )

    for run_id, run in run_by_id.items():
        for input_id in run["input_artifact_ids"]:
            if input_id not in artifact_by_id:
                _immutable_reject(
                    rejections,
                    ImmutableRegistryRejectionCode.BROKEN_DIRECT_INPUT,
                    f"Run {run_id!r} references missing input {input_id!r}.",
                    run_id,
                )
        for output_id in run["output_artifact_ids"]:
            output = artifact_by_id.get(output_id)
            if output is None or output["creator_run_id"] != run_id:
                _immutable_reject(
                    rejections,
                    ImmutableRegistryRejectionCode.AMBIGUOUS_LINEAGE,
                    f"Run {run_id!r} has an unresolved or foreign output {output_id!r}.",
                    run_id,
                )

    for verification_id, verification in verification_by_id.items():
        if verification["artifact_id"] not in artifact_by_id:
            _immutable_reject(
                rejections,
                ImmutableRegistryRejectionCode.INVALID_BYTE_VERIFICATION,
                f"Verification {verification_id!r} references an unknown artifact.",
                verification_id,
            )

    if artifact_bytes_by_id is not None and not isinstance(
        artifact_bytes_by_id, Mapping
    ):
        _immutable_reject(
            rejections,
            ImmutableRegistryRejectionCode.INVALID_BYTE_VERIFICATION,
            "artifact_bytes_by_id must be a mapping when supplied.",
        )
    elif isinstance(artifact_bytes_by_id, Mapping):
        for artifact_id, payload in artifact_bytes_by_id.items():
            artifact = artifact_by_id.get(artifact_id)
            if artifact is None or not isinstance(payload, bytes):
                _immutable_reject(
                    rejections,
                    ImmutableRegistryRejectionCode.INVALID_BYTE_VERIFICATION,
                    f"Supplied bytes for {artifact_id!r} are malformed or unregistered.",
                    artifact_id if isinstance(artifact_id, str) else None,
                )

    if previous_registry is not None and not rejections:
        _validate_v2_transition(
            document,
            previous_registry,
            rejections,
            artifact_bytes_by_id,
            trusted_owner_authorities,
            trusted_status_record_bytes,
            trusted_artifact_authorizations,
            trusted_authorization_record_bytes,
            trusted_manifest_records,
            trusted_artifact_receipts,
        )

    return ImmutableRegistryValidationResult(not rejections, tuple(rejections))


def validate_immutable_run_artifact_registry(
    document: Any,
    *,
    previous_registry: Any = None,
    artifact_bytes_by_id: Mapping[str, bytes] | None = None,
    trusted_owner_authorities: Mapping[str, Mapping[str, Any]] | None = None,
    trusted_status_record_bytes: Mapping[str, bytes] | None = None,
    trusted_artifact_authorizations: Mapping[str, Mapping[str, Any]]
    | None = None,
    trusted_authorization_record_bytes: Mapping[str, bytes] | None = None,
    trusted_manifest_records: Mapping[str, Mapping[str, Any]] | None = None,
    trusted_artifact_receipts: Mapping[str, Mapping[str, Any]] | None = None,
) -> ImmutableRegistryValidationResult:
    """Dispatch immutable-registry validation by exact frozen schema identifier.

    V1 remains frozen and is evaluated by its original implementation. V2 adds
    externally trusted owner/status evidence, exact-artifact authorization,
    trusted manifests, externally verified artifact bytes or receipts,
    explicit pending/running jobs, and the extraction artifact type. Unknown
    versions fail closed without being interpreted as either contract.
    """

    if not isinstance(document, Mapping):
        return _validate_immutable_run_artifact_registry_v1(
            document,
            previous_registry=previous_registry,
            artifact_bytes_by_id=artifact_bytes_by_id,
        )
    version = document.get("immutable_registry_schema_version")
    if version == IMMUTABLE_REGISTRY_SCHEMA_VERSION or version is None:
        return _validate_immutable_run_artifact_registry_v1(
            document,
            previous_registry=previous_registry,
            artifact_bytes_by_id=artifact_bytes_by_id,
        )
    if version == IMMUTABLE_REGISTRY_V2_SCHEMA_VERSION:
        return _validate_immutable_run_artifact_registry_v2(
            document,
            previous_registry=previous_registry,
            artifact_bytes_by_id=artifact_bytes_by_id,
            trusted_owner_authorities=trusted_owner_authorities,
            trusted_status_record_bytes=trusted_status_record_bytes,
            trusted_artifact_authorizations=trusted_artifact_authorizations,
            trusted_authorization_record_bytes=trusted_authorization_record_bytes,
            trusted_manifest_records=trusted_manifest_records,
            trusted_artifact_receipts=trusted_artifact_receipts,
        )
    rejections: list[ImmutableRegistryRejection] = []
    _immutable_reject(
        rejections,
        ImmutableRegistryRejectionCode.UNSUPPORTED_SCHEMA_VERSION,
        f"Unsupported immutable registry schema version {version!r}.",
    )
    return ImmutableRegistryValidationResult(False, tuple(rejections))
