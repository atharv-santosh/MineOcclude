"""Strict detector-calibration dataset validation for Person E.

The contract keeps calibration and held-out frames in one immutable document,
but makes the split, scene identity, truth, and image provenance explicit.  It
does not choose detector thresholds; selection remains a calibration-only
operation performed by the caller.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from mineocclude.contracts.identity import SCHEMA_VERSION
from mineocclude.experiments.registry import (
    ProvenanceError,
    hash_json_value,
    load_json_with_sha256,
)


DETECTOR_CALIBRATION_SCHEMA_VERSION = (
    "person-e-detector-calibration-dataset-v0.1"
)
DETECTOR_CALIBRATION_PLAN_SCHEMA_VERSION = (
    "person-e-detector-calibration-plan-v1.0"
)
CALIBRATION_SPLITS = frozenset({"calibration", "heldout"})
TRUTH_CLASSES = frozenset({"visible", "negative"})
CALIBRATION_SOURCE_KINDS = frozenset(
    {"visible_magenta_sheep", "negative_wall", "negative_marker"}
)
THRESHOLD_SELECTION_INPUTS = frozenset(
    {
        "hsv_ranges",
        "min_area_pixels",
        "max_area_pixels",
        "morphology_iterations",
        "morphology_radius_pixels",
        "connectivity",
    }
)


class CalibrationDatasetError(ValueError):
    """Raised when detector calibration evidence is ambiguous or incomplete."""


def _require_mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CalibrationDatasetError(f"{name} must be a mapping.")
    return value


def _require_exact_keys(
    value: Mapping[str, Any], expected: set[str], name: str
) -> None:
    actual = set(value)
    if actual != expected:
        raise CalibrationDatasetError(
            f"{name} fields changed; "
            f"missing={sorted(expected - actual)}, extra={sorted(actual - expected)}."
        )


def _require_identifier(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise CalibrationDatasetError(f"{name} must be a non-empty trimmed string.")
    if any(character.isspace() for character in value):
        raise CalibrationDatasetError(f"{name} cannot contain whitespace.")
    return value


def _require_sha256(value: Any, name: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or value != value.lower()
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise CalibrationDatasetError(f"{name} must be a lowercase SHA-256 hash.")
    return value


def _require_non_negative_integer(value: Any, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise CalibrationDatasetError(f"{name} must be a non-negative integer.")
    return value


def _finite_pair(
    value: Any,
    name: str,
    *,
    non_negative: bool = False,
) -> tuple[float, float]:
    if (
        not isinstance(value, Sequence)
        or isinstance(value, (str, bytes))
        or len(value) != 2
    ):
        raise CalibrationDatasetError(f"{name} must contain two coordinates.")
    coordinates: list[float] = []
    for coordinate in value:
        if (
            not isinstance(coordinate, (int, float))
            or isinstance(coordinate, bool)
            or not math.isfinite(float(coordinate))
        ):
            raise CalibrationDatasetError(f"{name} coordinates must be finite.")
        number = float(coordinate)
        if non_negative and number < 0.0:
            raise CalibrationDatasetError(f"{name} coordinates must be non-negative.")
        coordinates.append(number)
    return coordinates[0], coordinates[1]


def _validate_rgb(rgb: Any, name: str) -> None:
    if not isinstance(rgb, list) or not rgb:
        raise CalibrationDatasetError(f"{name} must contain at least one image row.")
    width: int | None = None
    for row_index, row in enumerate(rgb):
        if not isinstance(row, list) or not row:
            raise CalibrationDatasetError(f"{name} row {row_index} is invalid.")
        if width is None:
            width = len(row)
        elif len(row) != width:
            raise CalibrationDatasetError(f"{name} rows must have equal width.")
        for column_index, pixel in enumerate(row):
            if not isinstance(pixel, list) or len(pixel) != 3:
                raise CalibrationDatasetError(
                    f"{name} pixel ({column_index}, {row_index}) must be RGB."
                )
            if any(
                not isinstance(channel, (int, float))
                or isinstance(channel, bool)
                or not math.isfinite(float(channel))
                or not 0.0 <= float(channel) <= 255.0
                for channel in pixel
            ):
                raise CalibrationDatasetError(
                    f"{name} RGB channels must be finite values in [0, 255]."
                )


def validate_detector_calibration_dataset(document: Mapping[str, Any]) -> None:
    """Validate split integrity, image truth, and four-marker provenance."""

    root = _require_mapping(document, "detector calibration dataset")
    _require_exact_keys(
        root,
        {
            "schema_version",
            "detector_calibration_schema_version",
            "dataset_id",
            "frames",
            "layouts",
        },
        "detector calibration dataset",
    )
    if root["schema_version"] != SCHEMA_VERSION:
        raise CalibrationDatasetError("schema_version must remain '1.0'.")
    if (
        root["detector_calibration_schema_version"]
        != DETECTOR_CALIBRATION_SCHEMA_VERSION
    ):
        raise CalibrationDatasetError("Unknown detector calibration schema version.")
    _require_identifier(root["dataset_id"], "dataset_id")

    layouts = root["layouts"]
    if not isinstance(layouts, list) or not layouts:
        raise CalibrationDatasetError("layouts must be a non-empty list.")
    layout_keys: set[tuple[str, str]] = set()
    layout_ids: set[str] = set()
    for layout_index, raw_layout in enumerate(layouts):
        layout = _require_mapping(raw_layout, f"layouts[{layout_index}]")
        _require_exact_keys(
            layout,
            {
                "layout_id",
                "canonical_camera_pose_id",
                "marker_set_id",
                "marker_set_source_hash",
                "markers",
            },
            f"layouts[{layout_index}]",
        )
        layout_id = _require_identifier(
            layout["layout_id"], f"layouts[{layout_index}].layout_id"
        )
        pose_id = _require_identifier(
            layout["canonical_camera_pose_id"],
            f"layouts[{layout_index}].canonical_camera_pose_id",
        )
        if layout_id in layout_ids:
            raise CalibrationDatasetError(f"Duplicate layout_id {layout_id!r}.")
        layout_ids.add(layout_id)
        layout_keys.add((layout_id, pose_id))
        _require_identifier(
            layout["marker_set_id"], f"layouts[{layout_index}].marker_set_id"
        )
        _require_sha256(
            layout["marker_set_source_hash"],
            f"layouts[{layout_index}].marker_set_source_hash",
        )
        markers = layout["markers"]
        if not isinstance(markers, list) or len(markers) != 4:
            raise CalibrationDatasetError(
                f"Layout {layout_id!r} must contain exactly four markers."
            )
        marker_ids: set[str] = set()
        image_points: set[tuple[float, float]] = set()
        world_points: set[tuple[float, float]] = set()
        for marker_index, raw_marker in enumerate(markers):
            marker_name = f"layouts[{layout_index}].markers[{marker_index}]"
            marker = _require_mapping(raw_marker, marker_name)
            _require_exact_keys(
                marker,
                {
                    "marker_id",
                    "image_xy",
                    "world_xz_blocks",
                    "coordinate_source_hash",
                },
                marker_name,
            )
            marker_id = _require_identifier(
                marker["marker_id"], f"{marker_name}.marker_id"
            )
            if marker_id in marker_ids:
                raise CalibrationDatasetError(
                    f"Layout {layout_id!r} has duplicate marker_id {marker_id!r}."
                )
            marker_ids.add(marker_id)
            image_point = _finite_pair(
                marker["image_xy"], f"{marker_name}.image_xy", non_negative=True
            )
            world_point = _finite_pair(
                marker["world_xz_blocks"], f"{marker_name}.world_xz_blocks"
            )
            if image_point in image_points or world_point in world_points:
                raise CalibrationDatasetError(
                    f"Layout {layout_id!r} marker coordinates must be unique."
                )
            image_points.add(image_point)
            world_points.add(world_point)
            _require_sha256(
                marker["coordinate_source_hash"],
                f"{marker_name}.coordinate_source_hash",
            )

    frames = root["frames"]
    if not isinstance(frames, list) or not frames:
        raise CalibrationDatasetError("frames must be a non-empty list.")
    frame_ids: set[str] = set()
    source_frame_keys: set[tuple[str, int]] = set()
    coverage: set[tuple[str, str, str, str]] = set()
    for frame_index, raw_frame in enumerate(frames):
        frame_name = f"frames[{frame_index}]"
        frame = _require_mapping(raw_frame, frame_name)
        _require_exact_keys(
            frame,
            {
                "frame_id",
                "layout_id",
                "canonical_camera_pose_id",
                "split",
                "truth_class",
                "truth_present",
                "source_artifact_id",
                "source_frame_idx",
                "source_frame_hash",
                "decoded_rgb_hash",
                "rgb",
            },
            frame_name,
        )
        frame_id = _require_identifier(frame["frame_id"], f"{frame_name}.frame_id")
        if frame_id in frame_ids:
            raise CalibrationDatasetError(f"Duplicate frame_id {frame_id!r}.")
        frame_ids.add(frame_id)
        layout_id = _require_identifier(
            frame["layout_id"], f"{frame_name}.layout_id"
        )
        pose_id = _require_identifier(
            frame["canonical_camera_pose_id"],
            f"{frame_name}.canonical_camera_pose_id",
        )
        if (layout_id, pose_id) not in layout_keys:
            raise CalibrationDatasetError(
                f"{frame_name} references an unknown layout/canonical pose."
            )
        split = frame["split"]
        if split not in CALIBRATION_SPLITS:
            raise CalibrationDatasetError(
                f"{frame_name}.split must be calibration or heldout."
            )
        truth_class = frame["truth_class"]
        if truth_class not in TRUTH_CLASSES:
            raise CalibrationDatasetError(
                f"{frame_name}.truth_class must be visible or negative."
            )
        truth_present = frame["truth_present"]
        if not isinstance(truth_present, bool):
            raise CalibrationDatasetError(
                f"{frame_name}.truth_present must be boolean."
            )
        if truth_present != (truth_class == "visible"):
            raise CalibrationDatasetError(
                f"{frame_name} truth_class and truth_present disagree."
            )
        source_artifact_id = _require_identifier(
            frame["source_artifact_id"], f"{frame_name}.source_artifact_id"
        )
        source_frame_idx = _require_non_negative_integer(
            frame["source_frame_idx"], f"{frame_name}.source_frame_idx"
        )
        source_key = (source_artifact_id, source_frame_idx)
        if source_key in source_frame_keys:
            raise CalibrationDatasetError(
                f"Duplicate source frame identity {source_key!r}."
            )
        source_frame_keys.add(source_key)
        _require_sha256(
            frame["source_frame_hash"], f"{frame_name}.source_frame_hash"
        )
        claimed_rgb_hash = _require_sha256(
            frame["decoded_rgb_hash"], f"{frame_name}.decoded_rgb_hash"
        )
        _validate_rgb(frame["rgb"], f"{frame_name}.rgb")
        actual_rgb_hash = hash_json_value(frame["rgb"])
        if claimed_rgb_hash != actual_rgb_hash:
            raise CalibrationDatasetError(
                f"{frame_name}.decoded_rgb_hash does not match decoded RGB values."
            )
        coverage.add((layout_id, pose_id, split, truth_class))

    missing_coverage = [
        (layout_id, pose_id, split, truth_class)
        for layout_id, pose_id in sorted(layout_keys)
        for split in sorted(CALIBRATION_SPLITS)
        for truth_class in sorted(TRUTH_CLASSES)
        if (layout_id, pose_id, split, truth_class) not in coverage
    ]
    if missing_coverage:
        raise CalibrationDatasetError(
            "Each layout/canonical pose requires visible and negative frames in "
            f"both splits; missing={missing_coverage}."
        )


def load_detector_calibration_dataset(
    path: Path | str,
) -> tuple[dict[str, Any], str]:
    """Read once, validate, and return the document plus literal-byte hash."""

    dataset_path = Path(path)
    try:
        document, literal_hash = load_json_with_sha256(dataset_path)
    except ProvenanceError as error:
        raise CalibrationDatasetError(
            f"Could not load detector calibration dataset {dataset_path}: {error}"
        ) from error
    if not isinstance(document, dict):
        raise CalibrationDatasetError("Detector calibration dataset must be a mapping.")
    validate_detector_calibration_dataset(document)
    return document, literal_hash


def frames_for_split(
    document: Mapping[str, Any], split: str
) -> list[Mapping[str, Any]]:
    """Return validated frames for one explicit calibration role."""

    if split not in CALIBRATION_SPLITS:
        raise CalibrationDatasetError("split must be calibration or heldout.")
    validate_detector_calibration_dataset(document)
    return [frame for frame in document["frames"] if frame["split"] == split]


def validate_detector_calibration_plan(document: Mapping[str, Any]) -> None:
    """Validate the Phase 1 calibration/test separation contract.

    Event and frame identities are split before any threshold-selection input is
    exposed.  Held-out rows are explicitly ineligible for selection, so a
    caller cannot relabel held-out evidence as calibration evidence without
    changing the hash-bound fixture content.
    """

    root = _require_mapping(document, "detector calibration plan")
    _require_exact_keys(
        root,
        {
            "schema_version",
            "calibration_plan_schema_version",
            "plan_id",
            "synthetic",
            "scientific_use",
            "threshold_selection_inputs",
            "requested_c_inputs",
            "samples",
        },
        "detector calibration plan",
    )
    if root["schema_version"] != SCHEMA_VERSION:
        raise CalibrationDatasetError("schema_version must remain '1.0'.")
    if (
        root["calibration_plan_schema_version"]
        != DETECTOR_CALIBRATION_PLAN_SCHEMA_VERSION
    ):
        raise CalibrationDatasetError("Unknown detector calibration plan version.")
    _require_identifier(root["plan_id"], "plan_id")
    if not isinstance(root["synthetic"], bool):
        raise CalibrationDatasetError("synthetic must be boolean.")
    if root["synthetic"] and root["scientific_use"] != "forbidden":
        raise CalibrationDatasetError("Synthetic calibration plans forbid scientific use.")
    if root["scientific_use"] not in {"forbidden", "permitted"}:
        raise CalibrationDatasetError("scientific_use is invalid.")

    selection_inputs = root["threshold_selection_inputs"]
    if not isinstance(selection_inputs, Mapping) or set(selection_inputs) != set(
        THRESHOLD_SELECTION_INPUTS
    ):
        raise CalibrationDatasetError(
            "threshold_selection_inputs must be the exact frozen input set."
        )
    hsv_ranges = selection_inputs["hsv_ranges"]
    if not isinstance(hsv_ranges, list) or not hsv_ranges:
        raise CalibrationDatasetError("hsv_ranges requires explicit candidates.")
    for index, value in enumerate(hsv_ranges):
        if not isinstance(value, Mapping) or set(value) != {
            "hue_min_degrees",
            "hue_max_degrees",
            "saturation_min",
            "saturation_max",
            "value_min",
            "value_max",
        }:
            raise CalibrationDatasetError(f"hsv_ranges[{index}] is malformed.")
        numbers = list(value.values())
        if any(
            not isinstance(item, (int, float))
            or isinstance(item, bool)
            or not math.isfinite(float(item))
            for item in numbers
        ):
            raise CalibrationDatasetError(f"hsv_ranges[{index}] must be finite.")
        if not (
            0.0 <= float(value["hue_min_degrees"]) < 360.0
            and 0.0 <= float(value["hue_max_degrees"]) < 360.0
            and 0.0 <= float(value["saturation_min"])
            <= float(value["saturation_max"])
            <= 1.0
            and 0.0 <= float(value["value_min"])
            <= float(value["value_max"])
            <= 1.0
        ):
            raise CalibrationDatasetError(f"hsv_ranges[{index}] bounds are invalid.")
    for field, minimum in (
        ("min_area_pixels", 1),
        ("morphology_iterations", 0),
        ("morphology_radius_pixels", 0),
    ):
        candidates = selection_inputs[field]
        if (
            not isinstance(candidates, list)
            or not candidates
            or any(
                not isinstance(item, int)
                or isinstance(item, bool)
                or item < minimum
                for item in candidates
            )
        ):
            raise CalibrationDatasetError(f"{field} candidates are invalid.")
    maximum_areas = selection_inputs["max_area_pixels"]
    if (
        not isinstance(maximum_areas, list)
        or not maximum_areas
        or any(
            item is not None
            and (
                not isinstance(item, int)
                or isinstance(item, bool)
                or item < 1
            )
            for item in maximum_areas
        )
    ):
        raise CalibrationDatasetError("max_area_pixels candidates are invalid.")
    connectivity = selection_inputs["connectivity"]
    if (
        not isinstance(connectivity, list)
        or not connectivity
        or any(item not in {4, 8} for item in connectivity)
    ):
        raise CalibrationDatasetError("connectivity candidates are invalid.")

    requested = _require_mapping(root["requested_c_inputs"], "requested_c_inputs")
    _require_exact_keys(
        requested,
        {
            "visible_magenta_sheep_frames",
            "negative_wall_frames",
            "negative_marker_frames",
            "layout_identity",
            "canonical_camera_pose_identity",
            "resolution_identity",
        },
        "requested_c_inputs",
    )
    if any(value is not True for value in requested.values()):
        raise CalibrationDatasetError(
            "All frozen Person C calibration inputs must be explicitly requested."
        )

    samples = root["samples"]
    if not isinstance(samples, list) or not samples:
        raise CalibrationDatasetError("samples must be a non-empty list.")
    sample_ids: set[str] = set()
    frame_ids: set[str] = set()
    frame_keys: set[tuple[str, int]] = set()
    source_keys: set[tuple[str, int]] = set()
    event_split: dict[str, str] = {}
    coverage: set[tuple[str, str]] = set()
    for index, raw_sample in enumerate(samples):
        name = f"samples[{index}]"
        sample = _require_mapping(raw_sample, name)
        _require_exact_keys(
            sample,
            {
                "sample_id",
                "event_id",
                "trajectory_id",
                "model_frame_idx",
                "frame_id",
                "source_artifact_id",
                "source_frame_idx",
                "layout_id",
                "canonical_camera_pose_id",
                "resolution_id",
                "image_width_px",
                "image_height_px",
                "image_coordinate_system",
                "split",
                "source_kind",
                "threshold_selection_eligible",
            },
            name,
        )
        identifiers = {
            field: _require_identifier(sample[field], f"{name}.{field}")
            for field in (
                "sample_id",
                "event_id",
                "trajectory_id",
                "frame_id",
                "source_artifact_id",
                "layout_id",
                "canonical_camera_pose_id",
                "resolution_id",
            )
        }
        sample_id = identifiers["sample_id"]
        frame_id = identifiers["frame_id"]
        if sample_id in sample_ids:
            raise CalibrationDatasetError(f"Duplicate sample_id {sample_id!r}.")
        if frame_id in frame_ids:
            raise CalibrationDatasetError(f"Frame {frame_id!r} appears more than once.")
        sample_ids.add(sample_id)
        frame_ids.add(frame_id)
        model_frame_idx = _require_non_negative_integer(
            sample["model_frame_idx"], f"{name}.model_frame_idx"
        )
        source_frame_idx = _require_non_negative_integer(
            sample["source_frame_idx"], f"{name}.source_frame_idx"
        )
        for field in ("image_width_px", "image_height_px"):
            value = sample[field]
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise CalibrationDatasetError(f"{name}.{field} must be positive int.")
        if sample["image_coordinate_system"] != "pixel_center_xy_zero_based":
            raise CalibrationDatasetError(
                f"{name}.image_coordinate_system is unsupported."
            )
        split = sample["split"]
        if split not in CALIBRATION_SPLITS:
            raise CalibrationDatasetError(f"{name}.split is invalid.")
        if sample["source_kind"] not in CALIBRATION_SOURCE_KINDS:
            raise CalibrationDatasetError(f"{name}.source_kind is invalid.")
        if sample["threshold_selection_eligible"] is not (split == "calibration"):
            raise CalibrationDatasetError(
                f"{name} threshold-selection eligibility contradicts its split."
            )

        event_id = identifiers["event_id"]
        prior_split = event_split.setdefault(event_id, split)
        if prior_split != split:
            raise CalibrationDatasetError(
                f"Event {event_id!r} overlaps calibration and held-out data."
            )
        frame_key = (identifiers["trajectory_id"], model_frame_idx)
        source_key = (identifiers["source_artifact_id"], source_frame_idx)
        if frame_key in frame_keys or source_key in source_keys:
            raise CalibrationDatasetError(
                f"{name} repeats an explicit scientific frame identity."
            )
        frame_keys.add(frame_key)
        source_keys.add(source_key)
        coverage.add((split, sample["source_kind"]))

    missing = sorted(
        (split, source_kind)
        for split in CALIBRATION_SPLITS
        for source_kind in CALIBRATION_SOURCE_KINDS
        if (split, source_kind) not in coverage
    )
    if missing:
        raise CalibrationDatasetError(
            f"Calibration plan lacks required C input coverage: {missing}."
        )
