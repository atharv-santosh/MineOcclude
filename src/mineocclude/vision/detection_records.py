"""Typed, deterministic Parquet records for Person E detector evidence.

This module intentionally uses the sole Parquet implementation authorized by
Person A.  It does not use pandas, pickle, implicit object conversion, or a
format fallback.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from mineocclude.experiments.registry import write_bytes_exclusive

PYARROW_VERSION = "25.0.0"
PERSON_A_PARQUET_AUTHORITY_REVISION = "06b87fe1f43d2133c25db498fcc1fd234f958aad"
PERSON_C_DEVELOPMENT_SOURCE_REVISION = "fa70424530f422a2e6140e0e90d0ff18f583141e"
DETECTION_RECORD_SCHEMA_VERSION = "person-e-detection-record-v1.0"
TEST_MANIFEST_SCHEMA_VERSION = "person-c-detector-test-manifest-v1.0"
ROW_ORDERING_KEY = ("layout_id", "frame_id")
TEST_MANIFEST_FRAME_FIELDS = frozenset(
    {
        "frame_id",
        "trajectory_id",
        "model_frame_idx",
        "source_artifact_id",
        "source_frame_idx",
        "layout_id",
        "canonical_camera_pose_id",
        "resolution_id",
        "image_width_px",
        "image_height_px",
        "pixel_format",
        "image_coordinate_system",
        "truth_present",
        "image_region",
        "background_stratum",
        "background_stratum_status",
        "source_path",
        "source_sha256",
        "source_git_revision",
    }
)
PARQUET_WRITER_SETTINGS: dict[str, Any] = {
    "compression": "NONE",
    "data_page_version": "1.0",
    "dictionary_encoding": False,
    "parquet_writer_version": "2.6",
    "row_group_size": 1024,
    "statistics": False,
    "store_arrow_schema": True,
    "timestamp_policy": "no_timestamp_columns",
    "use_byte_stream_split": False,
    "use_compliant_nested_type": True,
    "write_batch_size": 1024,
    "write_page_checksum": False,
    "write_page_index": False,
}


class DetectionRecordError(ValueError):
    """Raised when detector records or one-shot evaluation inputs are unsafe."""


_FIELD_SPECS: tuple[tuple[str, pa.DataType, bool, str], ...] = (
    ("schema_version", pa.string(), False, "Person E detection-row schema."),
    ("record_id", pa.string(), False, "Immutable detector-record identity."),
    ("frame_id", pa.string(), False, "Owner-authored source-frame identity."),
    ("trajectory_id", pa.string(), True, "Trajectory identity when available."),
    ("model_frame_idx", pa.int64(), True, "Model-frame index when available."),
    ("source_artifact_id", pa.string(), False, "Committed source artifact identity."),
    ("source_frame_idx", pa.int64(), False, "Frame index in the source artifact."),
    ("layout_id", pa.string(), False, "Registered layout identity."),
    (
        "canonical_camera_pose_id",
        pa.string(),
        False,
        "Canonical camera-pose identity.",
    ),
    ("resolution_id", pa.string(), False, "Registered image resolution identity."),
    ("image_width_px", pa.int32(), False, "Decoded image width in pixels."),
    ("image_height_px", pa.int32(), False, "Decoded image height in pixels."),
    ("pixel_format", pa.string(), False, "Decoded channel and sample format."),
    (
        "image_coordinate_system",
        pa.string(),
        False,
        "Pixel-centre coordinate convention.",
    ),
    ("split_role", pa.string(), False, "Current evaluation role."),
    (
        "historical_phase2_split_role",
        pa.string(),
        True,
        "Historical Phase 2 role, retained only for provenance.",
    ),
    ("truth_present", pa.bool_(), False, "Owner-authored binary presence truth."),
    ("detected_present", pa.bool_(), False, "Fail-closed detector presence result."),
    ("classification", pa.string(), False, "TP, FP, TN, or FN classification."),
    ("centroid_x", pa.float64(), True, "Detected centroid x pixel centre."),
    ("centroid_y", pa.float64(), True, "Detected centroid y pixel centre."),
    ("area_pixels", pa.int64(), True, "Selected connected-component area."),
    ("bbox_x_min", pa.int32(), True, "Inclusive bounding-box x minimum."),
    ("bbox_y_min", pa.int32(), True, "Inclusive bounding-box y minimum."),
    ("bbox_x_max_exclusive", pa.int32(), True, "Exclusive bounding-box x maximum."),
    ("bbox_y_max_exclusive", pa.int32(), True, "Exclusive bounding-box y maximum."),
    (
        "threshold_match_pixels",
        pa.int64(),
        False,
        "Pixels matching the frozen HSV thresholds before morphology.",
    ),
    (
        "threshold_match_fraction",
        pa.float64(),
        False,
        "Threshold-matching pixels divided by decoded image pixels.",
    ),
    (
        "candidate_blob_count",
        pa.int32(),
        False,
        "Connected components considered before the area filter.",
    ),
    (
        "selected_blob_fraction_of_threshold_matches",
        pa.float64(),
        True,
        "Selected area divided by threshold matches when detected.",
    ),
    ("quality_status", pa.string(), False, "accepted, low_quality, or rejected."),
    ("detector_algorithm_id", pa.string(), False, "Frozen detector algorithm ID."),
    ("detector_version", pa.string(), False, "Complete immutable detector version."),
    (
        "detector_config_sha256",
        pa.string(),
        False,
        "SHA-256 of the canonical candidate configuration identity.",
    ),
    (
        "detector_settings_sha256",
        pa.string(),
        False,
        "SHA-256 of the canonical detector settings.",
    ),
    (
        "detector_implementation_sha256",
        pa.string(),
        False,
        "SHA-256 of the detector implementation bytes.",
    ),
    ("status", pa.string(), False, "detected, not_detected, or rejected."),
    ("reason", pa.string(), True, "Explicit non-detection or rejection reason."),
    (
        "image_region",
        pa.string(),
        False,
        "Predeclared or independently derived region.",
    ),
    (
        "background_stratum",
        pa.string(),
        True,
        "Owner-authored marker/wall/background stratum when available.",
    ),
    (
        "background_stratum_status",
        pa.string(),
        False,
        "Whether the background stratum is owner-authored or unavailable.",
    ),
    ("source_path", pa.string(), False, "Repository-relative committed PNG path."),
    ("source_sha256", pa.string(), False, "SHA-256 of literal source PNG bytes."),
    (
        "person_c_source_revision",
        pa.string(),
        False,
        "Exact Person C source Git revision.",
    ),
    (
        "person_a_parquet_authority_revision",
        pa.string(),
        False,
        "Exact Person A Parquet dependency-authority revision.",
    ),
)

DETECTION_RECORD_FIELDS = tuple(spec[0] for spec in _FIELD_SPECS)


def _require_pyarrow_version() -> None:
    if pa.__version__ != PYARROW_VERSION:
        raise DetectionRecordError(
            f"pyarrow must be exactly {PYARROW_VERSION}; found {pa.__version__}."
        )


def _metadata_bytes(values: Mapping[str, str]) -> dict[bytes, bytes]:
    if any(
        not isinstance(key, str) or not isinstance(value, str)
        for key, value in values.items()
    ):
        raise DetectionRecordError("Arrow metadata keys and values must be strings.")
    return {key.encode("utf-8"): values[key].encode("utf-8") for key in sorted(values)}


def detection_arrow_schema(
    *,
    detector_version: str,
    detector_config_sha256: str,
    detector_settings_sha256: str,
    detector_implementation_sha256: str,
    person_c_source_revision: str,
    person_a_parquet_authority_revision: str = PERSON_A_PARQUET_AUTHORITY_REVISION,
) -> pa.Schema:
    """Return the exact Arrow schema for one frozen detector/source binding."""

    _require_pyarrow_version()
    for name, value in (
        ("detector_version", detector_version),
        ("detector_config_sha256", detector_config_sha256),
        ("detector_settings_sha256", detector_settings_sha256),
        ("detector_implementation_sha256", detector_implementation_sha256),
        ("person_c_source_revision", person_c_source_revision),
        (
            "person_a_parquet_authority_revision",
            person_a_parquet_authority_revision,
        ),
    ):
        _require_nonempty_string(value, name)
    fields = [
        pa.field(
            name,
            data_type,
            nullable=nullable,
            metadata=_metadata_bytes(
                {
                    "description": description,
                    "field_order": str(index),
                }
            ),
        )
        for index, (name, data_type, nullable, description) in enumerate(_FIELD_SPECS)
    ]
    schema_metadata = _metadata_bytes(
        {
            "detector_config_sha256": detector_config_sha256,
            "detector_implementation_sha256": detector_implementation_sha256,
            "detector_settings_sha256": detector_settings_sha256,
            "detector_version": detector_version,
            "person_a_parquet_authority_revision": (
                person_a_parquet_authority_revision
            ),
            "person_c_source_revision": person_c_source_revision,
            "pyarrow_version": PYARROW_VERSION,
            "row_ordering_key": ",".join(ROW_ORDERING_KEY),
            "schema_version": DETECTION_RECORD_SCHEMA_VERSION,
            "timestamp_policy": PARQUET_WRITER_SETTINGS["timestamp_policy"],
        }
    )
    return pa.schema(fields, metadata=schema_metadata)


def _require_nonempty_string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise DetectionRecordError(f"{name} must be a non-empty trimmed string.")
    return value


def _require_optional_string(value: Any, name: str) -> str | None:
    if value is None:
        return None
    return _require_nonempty_string(value, name)


def _require_sha256(value: Any, name: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or value != value.lower()
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise DetectionRecordError(f"{name} must be lowercase SHA-256.")
    return value


def _require_git_sha(value: Any, name: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 40
        or value != value.lower()
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise DetectionRecordError(f"{name} must be a full lowercase Git SHA.")
    return value


def _require_integer(
    value: Any,
    name: str,
    *,
    nullable: bool = False,
    positive: bool = False,
) -> int | None:
    if nullable and value is None:
        return None
    if type(value) is not int or value < (1 if positive else 0):
        qualifier = "positive" if positive else "non-negative"
        raise DetectionRecordError(f"{name} must be a {qualifier} integer.")
    return value


def _require_float(
    value: Any,
    name: str,
    *,
    nullable: bool = False,
    unit_interval: bool = False,
) -> float | None:
    if nullable and value is None:
        return None
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(float(value))
    ):
        raise DetectionRecordError(f"{name} must be a finite number.")
    result = float(value)
    if unit_interval and not 0.0 <= result <= 1.0:
        raise DetectionRecordError(f"{name} must lie in [0, 1].")
    return result


def validate_detection_records(records: Sequence[Mapping[str, Any]]) -> None:
    """Validate complete typed records without accepting arbitrary objects."""

    if (
        not isinstance(records, Sequence)
        or isinstance(records, (str, bytes))
        or not records
    ):
        raise DetectionRecordError("Detection records must be a non-empty sequence.")
    expected_fields = set(DETECTION_RECORD_FIELDS)
    record_ids: set[str] = set()
    frame_ids: set[str] = set()
    version_binding: tuple[str, str, str, str, str, str] | None = None
    for index, raw_record in enumerate(records):
        name = f"records[{index}]"
        if not isinstance(raw_record, Mapping) or set(raw_record) != expected_fields:
            raise DetectionRecordError(f"{name} fields changed.")
        record = raw_record
        if record["schema_version"] != DETECTION_RECORD_SCHEMA_VERSION:
            raise DetectionRecordError(f"{name}.schema_version is unsupported.")
        record_id = _require_nonempty_string(record["record_id"], f"{name}.record_id")
        frame_id = _require_nonempty_string(record["frame_id"], f"{name}.frame_id")
        if record_id in record_ids or frame_id in frame_ids:
            raise DetectionRecordError("Duplicate record_id or frame_id.")
        record_ids.add(record_id)
        frame_ids.add(frame_id)

        for field in (
            "source_artifact_id",
            "layout_id",
            "canonical_camera_pose_id",
            "resolution_id",
            "pixel_format",
            "image_coordinate_system",
            "split_role",
            "classification",
            "quality_status",
            "detector_algorithm_id",
            "detector_version",
            "status",
            "image_region",
            "background_stratum_status",
            "source_path",
        ):
            _require_nonempty_string(record[field], f"{name}.{field}")
        _require_optional_string(record["trajectory_id"], f"{name}.trajectory_id")
        _require_optional_string(
            record["historical_phase2_split_role"],
            f"{name}.historical_phase2_split_role",
        )
        _require_optional_string(
            record["background_stratum"], f"{name}.background_stratum"
        )
        _require_optional_string(record["reason"], f"{name}.reason")
        _require_integer(
            record["model_frame_idx"], f"{name}.model_frame_idx", nullable=True
        )
        _require_integer(record["source_frame_idx"], f"{name}.source_frame_idx")
        width = _require_integer(
            record["image_width_px"], f"{name}.image_width_px", positive=True
        )
        height = _require_integer(
            record["image_height_px"], f"{name}.image_height_px", positive=True
        )
        threshold_pixels = _require_integer(
            record["threshold_match_pixels"],
            f"{name}.threshold_match_pixels",
        )
        _require_integer(record["candidate_blob_count"], f"{name}.candidate_blob_count")
        _require_float(
            record["threshold_match_fraction"],
            f"{name}.threshold_match_fraction",
            unit_interval=True,
        )
        _require_float(
            record["selected_blob_fraction_of_threshold_matches"],
            f"{name}.selected_blob_fraction_of_threshold_matches",
            nullable=True,
            unit_interval=True,
        )
        for field in (
            "detector_config_sha256",
            "detector_settings_sha256",
            "detector_implementation_sha256",
            "source_sha256",
        ):
            _require_sha256(record[field], f"{name}.{field}")
        for field in (
            "person_c_source_revision",
            "person_a_parquet_authority_revision",
        ):
            _require_git_sha(record[field], f"{name}.{field}")
        if (
            record["person_a_parquet_authority_revision"]
            != PERSON_A_PARQUET_AUTHORITY_REVISION
        ):
            raise DetectionRecordError("Person A Parquet authority changed.")
        if record["image_coordinate_system"] != "pixel_center_xy_zero_based":
            raise DetectionRecordError("Image coordinate convention changed.")
        if record["pixel_format"] != "rgb8":
            raise DetectionRecordError("Only decoded RGB8 records are supported.")
        if record["split_role"] not in {"development", "test"}:
            raise DetectionRecordError("split_role must be development or test.")
        if record["historical_phase2_split_role"] not in {
            None,
            "calibration",
            "heldout",
        }:
            raise DetectionRecordError("Historical Phase 2 role is invalid.")
        if (
            type(record["truth_present"]) is not bool
            or type(record["detected_present"]) is not bool
        ):
            raise DetectionRecordError("Presence fields must be boolean.")
        expected_classification = (
            "TP"
            if record["truth_present"] and record["detected_present"]
            else "FN"
            if record["truth_present"]
            else "FP"
            if record["detected_present"]
            else "TN"
        )
        if record["classification"] != expected_classification:
            raise DetectionRecordError("Detection classification is inconsistent.")

        binding = (
            record["detector_version"],
            record["detector_config_sha256"],
            record["detector_settings_sha256"],
            record["detector_implementation_sha256"],
            record["person_c_source_revision"],
            record["person_a_parquet_authority_revision"],
        )
        if version_binding is None:
            version_binding = binding
        elif binding != version_binding:
            raise DetectionRecordError("Detection rows have mixed frozen identities.")

        status = record["status"]
        quality = record["quality_status"]
        geometry_fields = (
            "centroid_x",
            "centroid_y",
            "area_pixels",
            "bbox_x_min",
            "bbox_y_min",
            "bbox_x_max_exclusive",
            "bbox_y_max_exclusive",
        )
        if status not in {"detected", "not_detected", "rejected"}:
            raise DetectionRecordError(f"{name}.status is invalid.")
        if quality not in {"accepted", "low_quality", "rejected"}:
            raise DetectionRecordError(f"{name}.quality_status is invalid.")
        if status == "detected":
            if (
                not record["detected_present"]
                or quality == "rejected"
                or record["reason"] is not None
            ):
                raise DetectionRecordError("Detected record status fields disagree.")
            centroid_x = _require_float(record["centroid_x"], f"{name}.centroid_x")
            centroid_y = _require_float(record["centroid_y"], f"{name}.centroid_y")
            area = _require_integer(
                record["area_pixels"], f"{name}.area_pixels", positive=True
            )
            x0 = _require_integer(record["bbox_x_min"], f"{name}.bbox_x_min")
            y0 = _require_integer(record["bbox_y_min"], f"{name}.bbox_y_min")
            x1 = _require_integer(
                record["bbox_x_max_exclusive"],
                f"{name}.bbox_x_max_exclusive",
                positive=True,
            )
            y1 = _require_integer(
                record["bbox_y_max_exclusive"],
                f"{name}.bbox_y_max_exclusive",
                positive=True,
            )
            if not (
                0 <= x0 < x1 <= width
                and 0 <= y0 < y1 <= height
                and x0 <= centroid_x < x1
                and y0 <= centroid_y < y1
                and area <= (x1 - x0) * (y1 - y0)
                and threshold_pixels >= area
            ):
                raise DetectionRecordError("Detected geometry is inconsistent.")
        else:
            if record["detected_present"] or any(
                record[field] is not None for field in geometry_fields
            ):
                raise DetectionRecordError("Fail-closed record cannot carry geometry.")
            if not isinstance(record["reason"], str):
                raise DetectionRecordError(
                    "Every non-detection or rejection needs a reason."
                )
            if status == "not_detected":
                if quality == "rejected" or record["reason"] not in {
                    "no_threshold_match",
                    "no_valid_blob",
                }:
                    raise DetectionRecordError("Non-detection reason is invalid.")
            elif quality != "rejected":
                raise DetectionRecordError(
                    "Rejected record must have rejected quality."
                )

        background = record["background_stratum"]
        background_status = record["background_stratum_status"]
        if background is None and background_status != "unavailable_owner_authored":
            raise DetectionRecordError(
                "Unavailable background strata must be explicit."
            )
        if background is not None and background_status != "owner_authored":
            raise DetectionRecordError(
                "Background strata cannot be inferred by Person E."
            )
        source_path = Path(record["source_path"])
        if source_path.is_absolute() or ".." in source_path.parts:
            raise DetectionRecordError(
                "source_path must be safe and repository-relative."
            )


def sort_detection_records(
    records: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Validate and return records in the frozen Parquet row order."""

    validate_detection_records(records)
    return [
        dict(record)
        for record in sorted(
            records,
            key=lambda record: tuple(record[field] for field in ROW_ORDERING_KEY),
        )
    ]


def detection_records_to_table(
    records: Sequence[Mapping[str, Any]],
    *,
    schema: pa.Schema,
) -> pa.Table:
    """Build an exact-schema Arrow table without object inference."""

    ordered = sort_detection_records(records)
    if schema.names != list(DETECTION_RECORD_FIELDS):
        raise DetectionRecordError("Arrow column order changed.")
    try:
        table = pa.Table.from_pydict(
            {
                field_name: [record[field_name] for record in ordered]
                for field_name in DETECTION_RECORD_FIELDS
            },
            schema=schema,
        )
    except (pa.ArrowException, TypeError, ValueError) as error:
        raise DetectionRecordError(
            f"Records do not satisfy the exact Arrow schema: {error}"
        ) from error
    if table.schema != schema:
        raise DetectionRecordError("Constructed Arrow schema changed.")
    return table


def detection_parquet_bytes(
    records: Sequence[Mapping[str, Any]],
    *,
    schema: pa.Schema,
) -> bytes:
    """Serialize deterministic, uncompressed Parquet bytes."""

    _require_pyarrow_version()
    table = detection_records_to_table(records, schema=schema)
    sink = pa.BufferOutputStream()
    pq.write_table(
        table,
        sink,
        row_group_size=PARQUET_WRITER_SETTINGS["row_group_size"],
        version=PARQUET_WRITER_SETTINGS["parquet_writer_version"],
        use_dictionary=PARQUET_WRITER_SETTINGS["dictionary_encoding"],
        compression=None,
        write_statistics=PARQUET_WRITER_SETTINGS["statistics"],
        use_deprecated_int96_timestamps=False,
        data_page_version=PARQUET_WRITER_SETTINGS["data_page_version"],
        use_compliant_nested_type=PARQUET_WRITER_SETTINGS["use_compliant_nested_type"],
        write_batch_size=PARQUET_WRITER_SETTINGS["write_batch_size"],
        store_schema=PARQUET_WRITER_SETTINGS["store_arrow_schema"],
        write_page_index=PARQUET_WRITER_SETTINGS["write_page_index"],
        write_page_checksum=PARQUET_WRITER_SETTINGS["write_page_checksum"],
        use_byte_stream_split=PARQUET_WRITER_SETTINGS["use_byte_stream_split"],
    )
    return sink.getvalue().to_pybytes()


def write_detection_parquet(
    path: Path | str,
    records: Sequence[Mapping[str, Any]],
    *,
    schema: pa.Schema,
) -> str:
    """Publish one Parquet artifact exclusively and return its SHA-256."""

    import hashlib

    payload = detection_parquet_bytes(records, schema=schema)
    write_bytes_exclusive(path, payload)
    return hashlib.sha256(payload).hexdigest()


def read_detection_parquet_bytes(
    payload: bytes,
    *,
    schema: pa.Schema,
) -> list[dict[str, Any]]:
    """Read back and strictly validate a deterministic Parquet artifact."""

    if not isinstance(payload, bytes):
        raise DetectionRecordError("Parquet payload must be literal bytes.")
    try:
        table = pq.read_table(pa.BufferReader(payload))
    except (pa.ArrowException, OSError) as error:
        raise DetectionRecordError(
            f"Could not read detection Parquet: {error}"
        ) from error
    if table.schema != schema:
        raise DetectionRecordError("Parquet read-back schema or metadata changed.")
    rows = table.to_pylist()
    validate_detection_records(rows)
    if rows != sort_detection_records(rows):
        raise DetectionRecordError("Parquet rows are not in the frozen order.")
    return rows


def arrow_schema_record(schema: pa.Schema) -> dict[str, Any]:
    """Return a deterministic JSON representation of the exact Arrow schema."""

    def decode_metadata(metadata: Mapping[bytes, bytes] | None) -> dict[str, str]:
        if metadata is None:
            return {}
        return {
            key.decode("utf-8"): metadata[key].decode("utf-8")
            for key in sorted(metadata)
        }

    return {
        "schema_version": "1.0",
        "detection_record_schema_version": DETECTION_RECORD_SCHEMA_VERSION,
        "pyarrow_version": PYARROW_VERSION,
        "column_order": list(schema.names),
        "row_ordering_key": list(ROW_ORDERING_KEY),
        "schema_metadata": decode_metadata(schema.metadata),
        "fields": [
            {
                "name": field.name,
                "arrow_type": str(field.type),
                "nullable": field.nullable,
                "metadata": decode_metadata(field.metadata),
            }
            for field in schema
        ],
        "null_policy": (
            "Only schema-nullable unavailable values are null; NaN, infinity, "
            "and arbitrary Python objects reject fail-closed."
        ),
    }


def require_complete_frame_identities(
    expected_frame_ids: Sequence[str],
    observed_frame_ids: Sequence[str],
) -> None:
    """Reject missing, duplicate, or extra evaluation identities."""

    expected = list(expected_frame_ids)
    observed = list(observed_frame_ids)
    if any(not isinstance(value, str) or not value for value in expected + observed):
        raise DetectionRecordError("Frame identities must be explicit strings.")
    if len(set(expected)) != len(expected):
        raise DetectionRecordError("Expected frame identities contain duplicates.")
    if len(set(observed)) != len(observed):
        raise DetectionRecordError("Observed frame identities contain duplicates.")
    missing = sorted(set(expected) - set(observed))
    extra = sorted(set(observed) - set(expected))
    if missing or extra:
        raise DetectionRecordError(
            f"Partial evaluation is forbidden; missing={missing}, extra={extra}."
        )


def _parse_utc_timestamp(value: Any, name: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise DetectionRecordError(f"{name} must be an explicit UTC timestamp.")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        raise DetectionRecordError(f"{name} is not valid ISO-8601.") from error
    if parsed.tzinfo != timezone.utc:
        raise DetectionRecordError(f"{name} must use UTC.")
    return parsed


def validate_test_evaluation_request(
    manifest: Mapping[str, Any],
    *,
    frozen_candidate: Mapping[str, Any],
    forbidden_development_hashes: Sequence[str],
    output_paths: Sequence[Path | str],
    one_shot_test: bool,
    candidate_comparison_requested: bool,
    proposed_settings: Mapping[str, Any] | None,
) -> list[Mapping[str, Any]]:
    """Validate the future one-shot test request before any source byte is read."""

    required = {
        "schema_version",
        "test_manifest_schema_version",
        "manifest_id",
        "source_revision",
        "source_commit_timestamp_utc",
        "created_after_candidate_freeze",
        "immutable",
        "split_role",
        "candidate_version",
        "candidate_config_sha256",
        "candidate_settings_sha256",
        "candidate_implementation_sha256",
        "test_outcomes_disclosed_before_evaluation",
        "frame_count",
        "frames",
    }
    if not isinstance(manifest, Mapping) or set(manifest) != required:
        raise DetectionRecordError("Test manifest fields changed.")
    if (
        manifest["schema_version"] != "1.0"
        or manifest["test_manifest_schema_version"] != TEST_MANIFEST_SCHEMA_VERSION
        or manifest["created_after_candidate_freeze"] is not True
        or manifest["immutable"] is not True
        or manifest["split_role"] != "test"
        or manifest["test_outcomes_disclosed_before_evaluation"] is not False
    ):
        raise DetectionRecordError(
            "Test manifest is not immutable, test-only evidence."
        )
    if not one_shot_test:
        raise DetectionRecordError("Test evaluation requires explicit one-shot mode.")
    if candidate_comparison_requested or proposed_settings is not None:
        raise DetectionRecordError(
            "Tuning and candidate comparison are forbidden in test mode."
        )
    for output_path in output_paths:
        if Path(output_path).exists():
            raise DetectionRecordError(
                f"Refusing to overwrite existing test result: {output_path}"
            )
    source_revision = _require_git_sha(
        manifest["source_revision"], "manifest.source_revision"
    )
    development_revision = _require_git_sha(
        frozen_candidate.get("development_source_revision"),
        "frozen_candidate.development_source_revision",
    )
    if source_revision == development_revision:
        raise DetectionRecordError("Test source must differ from development source.")
    freeze_timestamp = _parse_utc_timestamp(
        frozen_candidate.get("freeze_timestamp_utc"),
        "frozen_candidate.freeze_timestamp_utc",
    )
    source_timestamp = _parse_utc_timestamp(
        manifest["source_commit_timestamp_utc"],
        "manifest.source_commit_timestamp_utc",
    )
    if source_timestamp <= freeze_timestamp:
        raise DetectionRecordError("Test source must postdate the candidate freeze.")
    for manifest_field, candidate_field in (
        ("candidate_version", "detector_version"),
        ("candidate_config_sha256", "detector_config_sha256"),
        ("candidate_settings_sha256", "detector_settings_sha256"),
        ("candidate_implementation_sha256", "detector_implementation_sha256"),
    ):
        if manifest[manifest_field] != frozen_candidate.get(candidate_field):
            raise DetectionRecordError(
                "Test manifest does not bind the exact candidate."
            )
    frames = manifest["frames"]
    if (
        not isinstance(frames, list)
        or type(manifest["frame_count"]) is not int
        or manifest["frame_count"] <= 0
        or len(frames) != manifest["frame_count"]
    ):
        raise DetectionRecordError("Test manifest frame count is incomplete.")
    frame_ids: list[str] = []
    source_hashes: list[str] = []
    for index, frame in enumerate(frames):
        name = f"frames[{index}]"
        if not isinstance(frame, Mapping) or set(frame) != TEST_MANIFEST_FRAME_FIELDS:
            raise DetectionRecordError(f"{name} fields changed.")
        for field in (
            "frame_id",
            "source_artifact_id",
            "layout_id",
            "canonical_camera_pose_id",
            "resolution_id",
            "pixel_format",
            "image_coordinate_system",
            "image_region",
            "source_path",
        ):
            _require_nonempty_string(frame[field], f"{name}.{field}")
        _require_optional_string(frame["trajectory_id"], f"{name}.trajectory_id")
        _require_integer(
            frame["model_frame_idx"],
            f"{name}.model_frame_idx",
            nullable=True,
        )
        _require_integer(frame["source_frame_idx"], f"{name}.source_frame_idx")
        _require_integer(
            frame["image_width_px"], f"{name}.image_width_px", positive=True
        )
        _require_integer(
            frame["image_height_px"], f"{name}.image_height_px", positive=True
        )
        if (
            frame["pixel_format"] != "rgb8"
            or frame["image_coordinate_system"] != "pixel_center_xy_zero_based"
            or type(frame["truth_present"]) is not bool
        ):
            raise DetectionRecordError(f"{name} image/truth contract changed.")
        _require_optional_string(
            frame["background_stratum"], f"{name}.background_stratum"
        )
        if (
            frame["background_stratum"] is None
            or frame["background_stratum_status"] != "owner_authored"
        ):
            raise DetectionRecordError(
                "Future test background strata must be owner-authored."
            )
        source_path = Path(frame["source_path"])
        if source_path.is_absolute() or ".." in source_path.parts:
            raise DetectionRecordError("Test source_path is unsafe.")
        frame_ids.append(frame["frame_id"])
        source_hashes.append(
            _require_sha256(frame["source_sha256"], f"{name}.source_sha256")
        )
        if frame.get("source_git_revision") != source_revision:
            raise DetectionRecordError(
                "Test frame source revision disagrees with manifest."
            )
    require_complete_frame_identities(frame_ids, frame_ids)
    forbidden = set(forbidden_development_hashes)
    if forbidden & set(source_hashes):
        raise DetectionRecordError("Test source overlaps development bytes.")
    if len(set(source_hashes)) != len(source_hashes):
        raise DetectionRecordError("Test package repeats source bytes.")
    return frames
