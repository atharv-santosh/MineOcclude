"""Fail-closed C/D/E consumer requirements owned by Person B.

These validators define what B needs to perform analysis. They do not claim
that another role has produced or signed a matching artifact yet.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any

from mineocclude.analysis.coordinates import (
    CoordinateContractError,
    validate_coordinate_frame,
)
from mineocclude.analysis.manifests import is_hex_digest
from mineocclude.contracts.identity import (
    FRAME_KEY,
    SCHEMA_VERSION,
    IdentityValidationError,
    get_key,
    validate_identity,
)


STATE_INPUT_SCHEMA_VERSION = "person-b-state-input-v0.1"
BASELINE_INPUT_SCHEMA_VERSION = "person-b-baseline-input-v0.1"
MEASUREMENT_INPUT_SCHEMA_VERSION = "person-b-u4-measurement-input-v0.1"

ALLOWED_BASELINE_FAMILIES = frozenset({"last_seen"})
ALLOWED_BASELINE_TARGETS = frozenset({"mu_oracle_blocks"})
BASELINE_LEGAL_INFORMATION_FIELDS = frozenset(
    {
        "uses_hidden_truth",
        "uses_future_information",
        "uses_scripted_q",
    }
)
FORBIDDEN_BASELINE_FEATURES = frozenset(
    {
        "hidden_truth",
        "q",
        "scripted_q",
        "x_true_blocks",
    }
)


class AnalysisInputRejectionCode(str, Enum):
    MISSING_REQUIRED_FIELD = "missing_required_field"
    INVALID_SCHEMA_VERSION = "invalid_schema_version"
    INVALID_PRODUCER_ROLE = "invalid_producer_role"
    INVALID_HASH = "invalid_hash"
    INVALID_COORDINATE_FRAME = "invalid_coordinate_frame"
    INVALID_IDENTITY = "invalid_identity"
    DUPLICATE_IDENTITY = "duplicate_identity"
    MANIFEST_MISMATCH = "manifest_mismatch"
    INVALID_VALUE = "invalid_value"
    INVALID_LIFECYCLE = "invalid_lifecycle"
    FOLD_MISMATCH = "fold_mismatch"
    NON_OOF_PREDICTION = "non_oof_prediction"
    OUTCOME_CONFLATION = "outcome_conflation"
    UNSUPPORTED_BASELINE_FAMILY = "unsupported_baseline_family"
    LEGAL_INFORMATION_VIOLATION = "legal_information_violation"
    MIXED_EPISODE_ID = "mixed_episode_id"
    NONCONSECUTIVE_SERVER_TICK = "nonconsecutive_server_tick"
    TIMEBASE_MISMATCH = "timebase_mismatch"


@dataclass(frozen=True)
class AnalysisInputRejection:
    code: AnalysisInputRejectionCode
    message: str
    row_index: int | None = None


@dataclass(frozen=True)
class AnalysisInputValidationResult:
    accepted: bool
    rejections: tuple[AnalysisInputRejection, ...]


def _reject(
    rejections: list[AnalysisInputRejection],
    code: AnalysisInputRejectionCode,
    message: str,
    row_index: int | None = None,
) -> None:
    rejections.append(AnalysisInputRejection(code, message, row_index))


def _finite(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _require_envelope(
    document: Any,
    *,
    version_field: str,
    version: str,
    producer_role: str,
    required: tuple[str, ...],
) -> tuple[list[AnalysisInputRejection], list[Any] | None]:
    rejections: list[AnalysisInputRejection] = []
    if not isinstance(document, Mapping):
        _reject(
            rejections,
            AnalysisInputRejectionCode.MISSING_REQUIRED_FIELD,
            "Input document must be a mapping.",
        )
        return rejections, None
    missing = [field for field in required if field not in document]
    if missing:
        _reject(
            rejections,
            AnalysisInputRejectionCode.MISSING_REQUIRED_FIELD,
            "Input document is missing: " + ", ".join(missing),
        )
        return rejections, None
    if (
        document.get("schema_version") != SCHEMA_VERSION
        or document.get(version_field) != version
    ):
        _reject(
            rejections,
            AnalysisInputRejectionCode.INVALID_SCHEMA_VERSION,
            "Input schema version mismatch.",
        )
    if document.get("producer_role") != producer_role:
        _reject(
            rejections,
            AnalysisInputRejectionCode.INVALID_PRODUCER_ROLE,
            f"Expected producer_role={producer_role!r}.",
        )
    rows = document.get("rows")
    if not isinstance(rows, list) or not rows:
        _reject(
            rejections,
            AnalysisInputRejectionCode.MISSING_REQUIRED_FIELD,
            "Input document requires a non-empty rows list.",
        )
        return rejections, None
    return rejections, rows


def validate_state_input(document: Any) -> AnalysisInputValidationResult:
    """Validate the signed wall-parallel state table required from C."""

    required = (
        "schema_version",
        "state_input_schema_version",
        "producer_role",
        "join_key",
        "accepted_manifest_hash",
        "coordinate_frame",
        "rows",
    )
    rejections, rows = _require_envelope(
        document,
        version_field="state_input_schema_version",
        version=STATE_INPUT_SCHEMA_VERSION,
        producer_role="person_c",
        required=required,
    )
    if rows is None or not isinstance(document, Mapping):
        return AnalysisInputValidationResult(False, tuple(rejections))
    if document.get("join_key") != list(FRAME_KEY):
        _reject(
            rejections,
            AnalysisInputRejectionCode.INVALID_VALUE,
            "State input join_key must use the universal frame key.",
        )
    manifest_hash = document.get("accepted_manifest_hash")
    if not is_hex_digest(manifest_hash, 64):
        _reject(
            rejections,
            AnalysisInputRejectionCode.INVALID_HASH,
            "accepted_manifest_hash must be SHA-256.",
        )
    # Import locally to keep the public contracts package independent from the
    # oracle package's builder imports during module initialization.
    from mineocclude.oracle.schema import (
        OracleRejectionCode,
        OracleValidationError,
        validate_trajectory_timebase_rows,
    )

    try:
        validate_coordinate_frame(document.get("coordinate_frame"))
    except CoordinateContractError as error:
        _reject(
            rejections,
            AnalysisInputRejectionCode.INVALID_COORDINATE_FRAME,
            str(error),
        )
    seen: set[tuple[Any, ...]] = set()
    identity_valid_rows: list[Mapping[str, Any]] = []
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            _reject(
                rejections,
                AnalysisInputRejectionCode.INVALID_IDENTITY,
                "State row must be a mapping.",
                index,
            )
            continue
        try:
            validate_identity(row)
            key = get_key(row)
        except IdentityValidationError as error:
            _reject(
                rejections,
                AnalysisInputRejectionCode.INVALID_IDENTITY,
                str(error),
                index,
            )
            continue
        identity_valid_rows.append(row)
        if key in seen:
            _reject(
                rejections,
                AnalysisInputRejectionCode.DUPLICATE_IDENTITY,
                f"Duplicate state row {key}.",
                index,
            )
        seen.add(key)
        if row.get("status") != "accepted":
            _reject(
                rejections,
                AnalysisInputRejectionCode.INVALID_LIFECYCLE,
                "Only accepted state rows may enter target construction.",
                index,
            )
        if row.get("accepted_manifest_hash") != manifest_hash:
            _reject(
                rejections,
                AnalysisInputRejectionCode.MANIFEST_MISMATCH,
                "State row accepted-manifest hash differs from the envelope.",
                index,
            )
        for field in ("x_true_blocks", "observed_position_blocks"):
            if field not in row:
                _reject(
                    rejections,
                    AnalysisInputRejectionCode.MISSING_REQUIRED_FIELD,
                    f"State row is missing {field}.",
                    index,
                )
        observed = row.get("observed_position_blocks")
        if row.get("visibility") == "visible":
            if not _finite(observed):
                _reject(
                    rejections,
                    AnalysisInputRejectionCode.INVALID_VALUE,
                    "Visible state rows require a finite observed position.",
                    index,
                )
        elif observed is not None:
            _reject(
                rejections,
                AnalysisInputRejectionCode.INVALID_VALUE,
                "Occluded state rows cannot expose observed position.",
                index,
            )
        if not _finite(row.get("x_true_blocks")):
            _reject(
                rejections,
                AnalysisInputRejectionCode.INVALID_VALUE,
                "x_true_blocks must be finite scoring-only truth.",
                index,
            )
    try:
        validate_trajectory_timebase_rows(identity_valid_rows)
    except OracleValidationError as error:
        code_map = {
            OracleRejectionCode.MIXED_EPISODE_ID: (
                AnalysisInputRejectionCode.MIXED_EPISODE_ID
            ),
            OracleRejectionCode.NONCONSECUTIVE_SERVER_TICK: (
                AnalysisInputRejectionCode.NONCONSECUTIVE_SERVER_TICK
            ),
            OracleRejectionCode.TIMEBASE_MISMATCH: (
                AnalysisInputRejectionCode.TIMEBASE_MISMATCH
            ),
        }
        _reject(
            rejections,
            code_map.get(error.code, AnalysisInputRejectionCode.INVALID_VALUE),
            str(error),
        )
    return AnalysisInputValidationResult(not rejections, tuple(rejections))


def validate_baseline_input(
    document: Any,
    *,
    expected_fold_by_frame: Mapping[tuple[str, int], int] | None = None,
) -> AnalysisInputValidationResult:
    """Validate D-to-B baseline predictions as OOF rows with locked folds."""

    required = (
        "schema_version",
        "baseline_input_schema_version",
        "producer_role",
        "baseline_id",
        "baseline_family",
        "target_name",
        "feature_access",
        "legal_information",
        "config_hash",
        "input_manifest_hash",
        "fold_manifest_hash",
        "fit_manifest_hash",
        "rows",
    )
    rejections, rows = _require_envelope(
        document,
        version_field="baseline_input_schema_version",
        version=BASELINE_INPUT_SCHEMA_VERSION,
        producer_role="person_d",
        required=required,
    )
    if rows is None or not isinstance(document, Mapping):
        return AnalysisInputValidationResult(False, tuple(rejections))
    for field in (
        "config_hash",
        "input_manifest_hash",
        "fold_manifest_hash",
        "fit_manifest_hash",
    ):
        if not is_hex_digest(document.get(field), 64):
            _reject(
                rejections,
                AnalysisInputRejectionCode.INVALID_HASH,
                f"{field} must be SHA-256.",
            )
    for field in ("baseline_id", "baseline_family", "target_name"):
        if not isinstance(document.get(field), str) or not document[field].strip():
            _reject(
                rejections,
                AnalysisInputRejectionCode.MISSING_REQUIRED_FIELD,
                f"{field} must be non-empty.",
            )
    baseline_family = document.get("baseline_family")
    if (
        isinstance(baseline_family, str)
        and baseline_family.strip()
        and baseline_family not in ALLOWED_BASELINE_FAMILIES
    ):
        _reject(
            rejections,
            AnalysisInputRejectionCode.UNSUPPORTED_BASELINE_FAMILY,
            f"Unsupported baseline_family={baseline_family!r}.",
        )
    target_name = document.get("target_name")
    if (
        isinstance(target_name, str)
        and target_name.strip()
        and target_name not in ALLOWED_BASELINE_TARGETS
    ):
        _reject(
            rejections,
            AnalysisInputRejectionCode.LEGAL_INFORMATION_VIOLATION,
            "Baseline targets cannot expose scoring-only hidden truth.",
        )

    feature_access = document.get("feature_access")
    if (
        not isinstance(feature_access, list)
        or not feature_access
        or any(
            not isinstance(field, str) or not field.strip()
            for field in feature_access
        )
        or len(feature_access) != len(set(feature_access))
    ):
        _reject(
            rejections,
            AnalysisInputRejectionCode.INVALID_VALUE,
            "feature_access must be a non-empty list of unique field names.",
        )
    else:
        forbidden_features = sorted(
            field
            for field in feature_access
            if field.lower() in FORBIDDEN_BASELINE_FEATURES
            or field.lower().startswith(("future_", "next_", "hidden_"))
        )
        if forbidden_features:
            _reject(
                rejections,
                AnalysisInputRejectionCode.LEGAL_INFORMATION_VIOLATION,
                "Baseline feature access is illegal: "
                + ", ".join(forbidden_features),
            )

    legal_information = document.get("legal_information")
    if (
        not isinstance(legal_information, Mapping)
        or set(legal_information) != BASELINE_LEGAL_INFORMATION_FIELDS
        or any(
            not isinstance(legal_information.get(field), bool)
            for field in BASELINE_LEGAL_INFORMATION_FIELDS
        )
    ):
        _reject(
            rejections,
            AnalysisInputRejectionCode.INVALID_VALUE,
            "legal_information must explicitly declare all access flags as booleans.",
        )
    elif any(legal_information[field] for field in BASELINE_LEGAL_INFORMATION_FIELDS):
        _reject(
            rejections,
            AnalysisInputRejectionCode.LEGAL_INFORMATION_VIOLATION,
            "Hidden truth, future information, and scripted q are forbidden inputs.",
        )
    seen: set[tuple[str, int]] = set()
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            _reject(
                rejections,
                AnalysisInputRejectionCode.INVALID_VALUE,
                "Baseline row must be a mapping.",
                index,
            )
            continue
        required_row = (
            "trajectory_id",
            "model_frame_idx",
            "fold_idx",
            "prediction",
            "prediction_scope",
            "fit_id",
        )
        missing = [field for field in required_row if field not in row]
        if missing:
            _reject(
                rejections,
                AnalysisInputRejectionCode.MISSING_REQUIRED_FIELD,
                "Baseline row is missing: " + ", ".join(missing),
                index,
            )
            continue
        key = (row["trajectory_id"], row["model_frame_idx"])
        if (
            not isinstance(row["trajectory_id"], str)
            or not row["trajectory_id"]
            or not isinstance(row["model_frame_idx"], int)
            or isinstance(row["model_frame_idx"], bool)
            or row["model_frame_idx"] < 0
            or not isinstance(row["fold_idx"], int)
            or isinstance(row["fold_idx"], bool)
            or row["fold_idx"] < 0
            or not isinstance(row["fit_id"], str)
            or not row["fit_id"]
        ):
            _reject(
                rejections,
                AnalysisInputRejectionCode.INVALID_IDENTITY,
                "Baseline frame/fold/fit identity is invalid.",
                index,
            )
            continue
        if key in seen:
            _reject(
                rejections,
                AnalysisInputRejectionCode.DUPLICATE_IDENTITY,
                f"Duplicate baseline prediction {key}.",
                index,
            )
        seen.add(key)
        if not _finite(row["prediction"]):
            _reject(
                rejections,
                AnalysisInputRejectionCode.INVALID_VALUE,
                "Baseline prediction must be finite.",
                index,
            )
        if row["prediction_scope"] != "out_of_fold":
            _reject(
                rejections,
                AnalysisInputRejectionCode.NON_OOF_PREDICTION,
                "Scientific baseline rows must be out-of-fold.",
                index,
            )
        if expected_fold_by_frame is not None:
            expected = expected_fold_by_frame.get(key)
            if expected is None or row["fold_idx"] != expected:
                _reject(
                    rejections,
                    AnalysisInputRejectionCode.FOLD_MISMATCH,
                    "Baseline fold does not match B's frozen fold manifest.",
                    index,
                )
    if expected_fold_by_frame is not None and seen != set(expected_fold_by_frame):
        _reject(
            rejections,
            AnalysisInputRejectionCode.MANIFEST_MISMATCH,
            "Baseline rows do not exactly cover B's accepted frame keys.",
        )
    return AnalysisInputValidationResult(not rejections, tuple(rejections))


def validate_measurement_input(
    document: Any,
    *,
    expected_rollouts_by_id: Mapping[str, Mapping[str, Any]] | None = None,
    expected_rollout_manifest_hash: str | None = None,
) -> AnalysisInputValidationResult:
    """Validate the minimal E-to-B U4 measurement table B will consume."""

    required = (
        "schema_version",
        "measurement_input_schema_version",
        "producer_role",
        "accepted_rollout_manifest_hash",
        "measurement_config_hash",
        "rows",
    )
    rejections, rows = _require_envelope(
        document,
        version_field="measurement_input_schema_version",
        version=MEASUREMENT_INPUT_SCHEMA_VERSION,
        producer_role="person_e",
        required=required,
    )
    if rows is None or not isinstance(document, Mapping):
        return AnalysisInputValidationResult(False, tuple(rejections))
    if expected_rollouts_by_id is not None and not isinstance(
        expected_rollouts_by_id, Mapping
    ):
        _reject(
            rejections,
            AnalysisInputRejectionCode.INVALID_VALUE,
            "expected_rollouts_by_id must be a mapping when supplied.",
        )
        expected_rollouts_by_id = None
    for field in ("accepted_rollout_manifest_hash", "measurement_config_hash"):
        if not is_hex_digest(document.get(field), 64):
            _reject(
                rejections,
                AnalysisInputRejectionCode.INVALID_HASH,
                f"{field} must be SHA-256.",
            )
    if expected_rollouts_by_id is not None:
        if not is_hex_digest(expected_rollout_manifest_hash, 64):
            _reject(
                rejections,
                AnalysisInputRejectionCode.MANIFEST_MISMATCH,
                "A validated rollout manifest hash is required with rollout rows.",
            )
        elif (
            document.get("accepted_rollout_manifest_hash")
            != expected_rollout_manifest_hash
        ):
            _reject(
                rejections,
                AnalysisInputRejectionCode.MANIFEST_MISMATCH,
                "Measurement envelope names a different rollout manifest.",
            )
    elif expected_rollout_manifest_hash is not None:
        _reject(
            rejections,
            AnalysisInputRejectionCode.MANIFEST_MISMATCH,
            "A rollout manifest hash cannot be checked without its rollout rows.",
        )
    else:
        _reject(
            rejections,
            AnalysisInputRejectionCode.MANIFEST_MISMATCH,
            "Validated A rollout/registry context is required for measurements.",
        )
    allowed_statuses = {
        "measured",
        "non_persistence",
        "generation_failure",
        "excluded",
    }
    seen: set[str] = set()
    seen_rollouts: set[str] = set()
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            _reject(
                rejections,
                AnalysisInputRejectionCode.INVALID_VALUE,
                "Measurement row must be a mapping.",
                index,
            )
            continue
        required_row = (
            "measurement_id",
            "rollout_id",
            "event_id",
            "direction_version",
            "control_type",
            "alpha_applied",
            "measurement_status",
            "displacement_blocks",
            "persistence_score",
            "ssim",
            "outcome_detail",
            "measurement_artifact_hash",
        )
        missing = [field for field in required_row if field not in row]
        if missing:
            _reject(
                rejections,
                AnalysisInputRejectionCode.MISSING_REQUIRED_FIELD,
                "Measurement row is missing: " + ", ".join(missing),
                index,
            )
            continue
        measurement_id = row["measurement_id"]
        if (
            not isinstance(measurement_id, str)
            or not measurement_id
            or measurement_id in seen
        ):
            _reject(
                rejections,
                AnalysisInputRejectionCode.DUPLICATE_IDENTITY,
                "measurement_id must be unique and non-empty.",
                index,
            )
        else:
            seen.add(measurement_id)
        rollout_id = row["rollout_id"]
        if isinstance(rollout_id, str):
            if rollout_id in seen_rollouts:
                _reject(
                    rejections,
                    AnalysisInputRejectionCode.DUPLICATE_IDENTITY,
                    "Each rollout must have exactly one measurement row.",
                    index,
                )
            seen_rollouts.add(rollout_id)
        status = row["measurement_status"]
        if not isinstance(status, str) or status not in allowed_statuses:
            _reject(
                rejections,
                AnalysisInputRejectionCode.INVALID_LIFECYCLE,
                "Unknown measurement_status.",
                index,
            )
            continue
        for field in (
            "rollout_id",
            "event_id",
            "direction_version",
            "control_type",
        ):
            if not isinstance(row[field], str) or not row[field]:
                _reject(
                    rejections,
                    AnalysisInputRejectionCode.INVALID_IDENTITY,
                    f"{field} must be a non-empty string.",
                    index,
                )
        control_type = row["control_type"]
        if not isinstance(control_type, str) or control_type not in {
            "intervention",
            "alpha_zero",
            "random_direction",
        }:
            _reject(
                rejections,
                AnalysisInputRejectionCode.INVALID_VALUE,
                "Unknown control_type.",
                index,
            )
        if expected_rollouts_by_id is not None and isinstance(rollout_id, str):
            expected = expected_rollouts_by_id.get(rollout_id)
            if expected is None:
                _reject(
                    rejections,
                    AnalysisInputRejectionCode.MANIFEST_MISMATCH,
                    "Measurement references a rollout outside the accepted manifest.",
                    index,
                )
            elif not isinstance(expected, Mapping):
                _reject(
                    rejections,
                    AnalysisInputRejectionCode.MANIFEST_MISMATCH,
                    "Rollout registry entry must be a mapping.",
                    index,
                )
            else:
                expected_fields = (
                    "event_id",
                    "direction_version",
                    "control_type",
                    "alpha_applied",
                    "outcome",
                    "measurable",
                    "status",
                    "execution_status",
                )
                missing_expected = [
                    field for field in expected_fields if field not in expected
                ]
                if missing_expected:
                    _reject(
                        rejections,
                        AnalysisInputRejectionCode.MANIFEST_MISMATCH,
                        "Rollout registry entry is missing: "
                        + ", ".join(missing_expected),
                        index,
                    )
                    expected = {}
                for field in ("event_id", "direction_version", "control_type"):
                    if row[field] != expected.get(field):
                        _reject(
                            rejections,
                            AnalysisInputRejectionCode.MANIFEST_MISMATCH,
                            f"Measurement {field} differs from the rollout registry.",
                            index,
                        )
                expected_alpha = expected.get("alpha_applied")
                if not _finite(expected_alpha):
                    _reject(
                        rejections,
                        AnalysisInputRejectionCode.MANIFEST_MISMATCH,
                        "Rollout registry alpha must be finite.",
                        index,
                    )
                outcome = expected.get("outcome")
                measurable = expected.get("measurable")
                lifecycle = expected.get("status")
                execution_status = expected.get("execution_status")
                expected_measurement_status: str | None = None
                lifecycle_is_coherent = False
                if outcome == "generation_failure":
                    lifecycle_is_coherent = (
                        measurable is False
                        and lifecycle == "excluded"
                        and execution_status in ("failed", "completed_with_failures")
                    )
                    expected_measurement_status = "generation_failure"
                elif lifecycle in ("excluded", "superseded"):
                    lifecycle_is_coherent = (
                        measurable is False
                        and execution_status in ("completed", "completed_with_failures")
                        and outcome in ("measurable_continuation", "non_persistence")
                    )
                    expected_measurement_status = "excluded"
                elif outcome == "measurable_continuation":
                    lifecycle_is_coherent = (
                        measurable is True
                        and lifecycle == "accepted"
                        and execution_status in ("completed", "completed_with_failures")
                    )
                    expected_measurement_status = "measured"
                elif outcome == "non_persistence":
                    lifecycle_is_coherent = (
                        measurable is False
                        and lifecycle == "accepted"
                        and execution_status in ("completed", "completed_with_failures")
                    )
                    expected_measurement_status = "non_persistence"

                if not lifecycle_is_coherent:
                    _reject(
                        rejections,
                        AnalysisInputRejectionCode.INVALID_LIFECYCLE,
                        (
                            "Rollout outcome, lifecycle, measurable flag, "
                            "and run status conflict."
                        ),
                        index,
                    )
                elif row["measurement_status"] != expected_measurement_status:
                    _reject(
                        rejections,
                        AnalysisInputRejectionCode.OUTCOME_CONFLATION,
                        (
                            "Measurement status contradicts the producing "
                            "rollout outcome."
                        ),
                        index,
                    )
                if (
                    _finite(expected_alpha)
                    and _finite(row["alpha_applied"])
                    and not math.isclose(
                        float(row["alpha_applied"]),
                        float(expected_alpha),
                        rel_tol=1e-10,
                        abs_tol=1e-12,
                    )
                ):
                    _reject(
                        rejections,
                        AnalysisInputRejectionCode.MANIFEST_MISMATCH,
                        "Measurement alpha differs from the rollout registry.",
                        index,
                    )
        if not _finite(row["alpha_applied"]):
            _reject(
                rejections,
                AnalysisInputRejectionCode.INVALID_VALUE,
                "alpha_applied must be finite.",
                index,
            )
        if not is_hex_digest(row["measurement_artifact_hash"], 64):
            _reject(
                rejections,
                AnalysisInputRejectionCode.INVALID_HASH,
                "measurement_artifact_hash must be SHA-256.",
                index,
            )
        measurements = (
            row["displacement_blocks"],
            row["persistence_score"],
            row["ssim"],
        )
        if status == "measured":
            if not all(_finite(value) for value in measurements):
                _reject(
                    rejections,
                    AnalysisInputRejectionCode.INVALID_VALUE,
                    (
                        "Measured rows require finite displacement, "
                        "persistence, and SSIM."
                    ),
                    index,
                )
            elif not (
                0.0 <= float(row["persistence_score"]) <= 1.0
                and 0.0 <= float(row["ssim"]) <= 1.0
            ):
                _reject(
                    rejections,
                    AnalysisInputRejectionCode.INVALID_VALUE,
                    "Persistence and SSIM must lie in [0, 1].",
                    index,
                )
        else:
            if any(value is not None for value in measurements):
                _reject(
                    rejections,
                    AnalysisInputRejectionCode.OUTCOME_CONFLATION,
                    (
                        "Unmeasured outcomes must not be encoded as zero "
                        "measurements."
                    ),
                    index,
                )
            if (
                not isinstance(row["outcome_detail"], str)
                or not row["outcome_detail"].strip()
            ):
                _reject(
                    rejections,
                    AnalysisInputRejectionCode.INVALID_VALUE,
                    "Unmeasured outcomes require outcome_detail.",
                    index,
                )
    if (
        expected_rollouts_by_id is not None
        and seen_rollouts != set(expected_rollouts_by_id)
    ):
        _reject(
            rejections,
            AnalysisInputRejectionCode.MANIFEST_MISMATCH,
            "Measurement rows do not exactly cover the accepted rollout IDs.",
        )
    return AnalysisInputValidationResult(not rejections, tuple(rejections))
