"""Combined A-to-E rollout-manifest and A/E registry contract.

The validator keeps rollout outcomes, run provenance, artifact lifecycle, and
cross-record lineage in one auditable handoff. It never derives scientific
identity from filenames, repairs malformed records, or computes Person E's
measurement outputs.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any
from urllib.parse import urlparse

from mineocclude.contracts.identity import (
    ArtifactStatus,
    IdentityValidationError,
    SCHEMA_VERSION,
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
        elif _is_non_empty_string(producer_run_id):
            if artifact_id not in run_outputs.get(producer_run_id, []):
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
        elif control_type == "alpha_zero" and alpha_fields_valid:
            if any(
                float(row[field]) != 0.0
                for field in (
                    "alpha_requested",
                    "alpha_applied",
                    "intended_block_shift",
                )
            ) or row["cap_reduced"] is not False:
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

IMMUTABLE_RUN_STATUSES = frozenset({"in_progress", "completed", "failed"})
IMMUTABLE_ARTIFACT_STATUSES = frozenset(
    {"accepted", "excluded", "superseded"}
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
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
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


def validate_immutable_run_artifact_registry(
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
