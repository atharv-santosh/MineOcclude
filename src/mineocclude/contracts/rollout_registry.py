"""Combined A-to-E rollout-manifest and A/E registry contract.

The validator keeps rollout outcomes, run provenance, artifact lifecycle, and
cross-record lineage in one auditable handoff. It never derives scientific
identity from filenames, repairs malformed records, or computes Person E's
measurement outputs.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
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

    return (
        isinstance(value, str)
        and len(value) == length
        and all(character in "0123456789abcdefABCDEF" for character in value)
    )


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
