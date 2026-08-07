"""Strict detector-calibration dataset validation for Person E.

The contract keeps calibration and held-out frames in one immutable document,
but makes the split, scene identity, truth, and image provenance explicit.  It
does not choose detector thresholds; selection remains a calibration-only
operation performed by the caller.
"""

from __future__ import annotations

import hashlib
import math
import struct
import subprocess
import zlib
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
FROZEN_DETECTOR_CALIBRATION_SCHEMA_VERSION = (
    "person-e-detector-calibration-dataset-v0.2"
)
SUPPORTED_DETECTOR_CALIBRATION_SCHEMA_VERSIONS = frozenset(
    {
        DETECTOR_CALIBRATION_SCHEMA_VERSION,
        FROZEN_DETECTOR_CALIBRATION_SCHEMA_VERSION,
    }
)
DETECTOR_CALIBRATION_PLAN_SCHEMA_VERSION = (
    "person-e-detector-calibration-plan-v1.0"
)
PNG_DECODER_VERSION = "person-e-stdlib-png-rgb8-v0.1"
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


def decode_png_rgb_bytes(payload: bytes) -> list[list[list[int]]]:
    """Decode non-interlaced RGB/RGBA 8-bit PNG bytes with the stdlib only."""

    signature = b"\x89PNG\r\n\x1a\n"
    if not isinstance(payload, bytes) or not payload.startswith(signature):
        raise CalibrationDatasetError("PNG input has an invalid signature.")
    offset = len(signature)
    width = height = color_type = bit_depth = interlace = None
    compressed = bytearray()
    saw_iend = False
    while offset < len(payload):
        if offset + 12 > len(payload):
            raise CalibrationDatasetError("PNG chunk framing is truncated.")
        length = struct.unpack(">I", payload[offset : offset + 4])[0]
        chunk_type = payload[offset + 4 : offset + 8]
        data_start = offset + 8
        data_end = data_start + length
        crc_end = data_end + 4
        if crc_end > len(payload):
            raise CalibrationDatasetError("PNG chunk payload is truncated.")
        chunk_data = payload[data_start:data_end]
        claimed_crc = struct.unpack(">I", payload[data_end:crc_end])[0]
        actual_crc = zlib.crc32(chunk_type)
        actual_crc = zlib.crc32(chunk_data, actual_crc) & 0xFFFFFFFF
        if claimed_crc != actual_crc:
            raise CalibrationDatasetError("PNG chunk CRC validation failed.")
        if chunk_type == b"IHDR":
            if length != 13 or width is not None:
                raise CalibrationDatasetError("PNG requires one canonical IHDR.")
            (
                width,
                height,
                bit_depth,
                color_type,
                compression,
                filtering,
                interlace,
            ) = struct.unpack(">IIBBBBB", chunk_data)
            if (
                width <= 0
                or height <= 0
                or bit_depth != 8
                or color_type not in {2, 6}
                or compression != 0
                or filtering != 0
                or interlace != 0
            ):
                raise CalibrationDatasetError(
                    "Only non-interlaced 8-bit RGB/RGBA PNG is supported."
                )
        elif chunk_type == b"IDAT":
            if width is None:
                raise CalibrationDatasetError("PNG IDAT appeared before IHDR.")
            compressed.extend(chunk_data)
        elif chunk_type == b"IEND":
            if length != 0:
                raise CalibrationDatasetError("PNG IEND must be empty.")
            saw_iend = True
            offset = crc_end
            break
        offset = crc_end
    if (
        width is None
        or height is None
        or color_type is None
        or not compressed
        or not saw_iend
        or offset != len(payload)
    ):
        raise CalibrationDatasetError("PNG is incomplete or has trailing bytes.")
    channels = 3 if color_type == 2 else 4
    row_size = width * channels
    try:
        decoded = zlib.decompress(bytes(compressed))
    except zlib.error as error:
        raise CalibrationDatasetError(f"PNG IDAT decompression failed: {error}") from error
    if len(decoded) != height * (row_size + 1):
        raise CalibrationDatasetError("PNG decoded byte count is inconsistent.")

    rows: list[bytes] = []
    previous = bytes(row_size)
    cursor = 0
    for _ in range(height):
        filter_type = decoded[cursor]
        cursor += 1
        filtered = decoded[cursor : cursor + row_size]
        cursor += row_size
        reconstructed = bytearray(row_size)
        for index, value in enumerate(filtered):
            left = reconstructed[index - channels] if index >= channels else 0
            up = previous[index]
            up_left = previous[index - channels] if index >= channels else 0
            if filter_type == 0:
                predictor = 0
            elif filter_type == 1:
                predictor = left
            elif filter_type == 2:
                predictor = up
            elif filter_type == 3:
                predictor = (left + up) // 2
            elif filter_type == 4:
                estimate = left + up - up_left
                left_distance = abs(estimate - left)
                up_distance = abs(estimate - up)
                diagonal_distance = abs(estimate - up_left)
                predictor = (
                    left
                    if left_distance <= up_distance
                    and left_distance <= diagonal_distance
                    else up
                    if up_distance <= diagonal_distance
                    else up_left
                )
            else:
                raise CalibrationDatasetError("PNG uses an unknown row filter.")
            reconstructed[index] = (value + predictor) & 0xFF
        previous = bytes(reconstructed)
        rows.append(previous)
    return [
        [
            [row[index], row[index + 1], row[index + 2]]
            for index in range(0, len(row), channels)
        ]
        for row in rows
    ]


def load_committed_frame_rgb(
    frame: Mapping[str, Any],
    *,
    repository: Path | str,
) -> list[list[list[int]]]:
    """Resolve and verify one frozen frame directly from a committed Git blob."""

    if not isinstance(frame, Mapping):
        raise CalibrationDatasetError("Frozen frame must be a mapping.")
    revision = frame.get("source_git_revision")
    source_path = frame.get("source_git_path")
    _require_sha256(frame.get("source_frame_hash"), "source_frame_hash")
    _require_sha256(frame.get("decoded_rgb_hash"), "decoded_rgb_hash")
    if (
        not isinstance(revision, str)
        or len(revision) != 40
        or any(character not in "0123456789abcdef" for character in revision)
    ):
        raise CalibrationDatasetError("source_git_revision must be a full Git SHA.")
    if (
        not isinstance(source_path, str)
        or not source_path
        or source_path.startswith(("/", "\\"))
        or ".." in Path(source_path).parts
    ):
        raise CalibrationDatasetError("source_git_path must be repository-relative.")
    try:
        completed = subprocess.run(
            [
                "git",
                "-C",
                str(Path(repository)),
                "cat-file",
                "blob",
                f"{revision}:{source_path}",
            ],
            check=False,
            capture_output=True,
        )
    except OSError as error:
        raise CalibrationDatasetError(f"Could not invoke Git: {error}") from error
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise CalibrationDatasetError(
            f"Could not resolve committed frame {revision}:{source_path}: {detail}"
        )
    payload = completed.stdout
    if hashlib.sha256(payload).hexdigest() != frame["source_frame_hash"]:
        raise CalibrationDatasetError("Committed PNG does not match source_frame_hash.")
    rgb = decode_png_rgb_bytes(payload)
    if (
        len(rgb) != frame.get("image_height_px")
        or len(rgb[0]) != frame.get("image_width_px")
        or frame.get("pixel_format") != "rgb8"
    ):
        raise CalibrationDatasetError("Decoded PNG dimensions or pixel format changed.")
    if hash_json_value(rgb) != frame["decoded_rgb_hash"]:
        raise CalibrationDatasetError("Decoded PNG does not match decoded_rgb_hash.")
    return rgb


def _validate_frozen_detector_calibration_dataset(
    root: Mapping[str, Any],
) -> None:
    _require_exact_keys(
        root,
        {
            "schema_version",
            "detector_calibration_schema_version",
            "dataset_id",
            "split_version",
            "freeze",
            "source_document",
            "capture_provenance",
            "partition_authority",
            "frames",
            "layouts",
        },
        "frozen detector calibration dataset",
    )
    _require_identifier(root["dataset_id"], "dataset_id")
    source_document = _require_mapping(root["source_document"], "source_document")
    _require_exact_keys(
        source_document,
        {"git_revision", "path", "sha256"},
        "source_document",
    )
    revision = source_document["git_revision"]
    if (
        not isinstance(revision, str)
        or len(revision) != 40
        or any(character not in "0123456789abcdef" for character in revision)
    ):
        raise CalibrationDatasetError("source_document.git_revision must be Git SHA.")
    _require_identifier(source_document["path"], "source_document.path")
    _require_sha256(source_document["sha256"], "source_document.sha256")
    capture_provenance = _require_mapping(
        root["capture_provenance"], "capture_provenance"
    )
    _require_exact_keys(
        capture_provenance,
        {"git_revision", "path", "sha256", "trajectory_count"},
        "capture_provenance",
    )
    if capture_provenance["git_revision"] != revision:
        raise CalibrationDatasetError("Capture-provenance revision changed.")
    _require_identifier(capture_provenance["path"], "capture_provenance.path")
    _require_sha256(capture_provenance["sha256"], "capture_provenance.sha256")
    if capture_provenance["trajectory_count"] != 12:
        raise CalibrationDatasetError("Capture provenance must cover 12 trajectories.")
    freeze = _require_mapping(root["freeze"], "freeze")
    if freeze != {
        "status": "frozen_before_threshold_selection",
        "split_frozen_before_threshold_selection": True,
        "threshold_selection_eligible_split": "calibration",
        "heldout_parameter_selection_forbidden": True,
    }:
        raise CalibrationDatasetError("Frozen split sequencing declaration changed.")
    partition = _require_mapping(
        root["partition_authority"], "partition_authority"
    )
    if partition != {
        "person_b_revision": "03a2c4663ce73873b4fed0369943c1f43edcd742",
        "u4_partition_schema_version": "person-b-u4-partition-v0.1",
        "real_final_u4_manifest_status": "not_available",
        "available_u4_artifact_ids": [],
        "included_u4_artifact_ids": [],
    }:
        raise CalibrationDatasetError("U4 exclusion authority changed.")

    layouts = root["layouts"]
    if not isinstance(layouts, list) or not layouts:
        raise CalibrationDatasetError("layouts must be a non-empty list.")
    layout_keys: set[tuple[str, str]] = set()
    layout_dimensions: dict[str, tuple[int, int, str, str]] = {}
    role_colors = {
        "north_west": "blue",
        "north_east": "yellow",
        "south_east": "white",
        "south_west": "lime",
    }
    for layout_index, raw_layout in enumerate(layouts):
        name = f"layouts[{layout_index}]"
        layout = _require_mapping(raw_layout, name)
        _require_exact_keys(
            layout,
            {
                "layout_id",
                "canonical_camera_pose_id",
                "marker_set_id",
                "marker_set_source_hash",
                "image_width_px",
                "image_height_px",
                "resolution_id",
                "pixel_format",
                "markers",
            },
            name,
        )
        layout_id = _require_identifier(layout["layout_id"], f"{name}.layout_id")
        pose_id = _require_identifier(
            layout["canonical_camera_pose_id"],
            f"{name}.canonical_camera_pose_id",
        )
        if (layout_id, pose_id) in layout_keys:
            raise CalibrationDatasetError("Duplicate layout/camera identity.")
        layout_keys.add((layout_id, pose_id))
        _require_identifier(layout["marker_set_id"], f"{name}.marker_set_id")
        _require_sha256(
            layout["marker_set_source_hash"],
            f"{name}.marker_set_source_hash",
        )
        width = layout["image_width_px"]
        height = layout["image_height_px"]
        if (
            not isinstance(width, int)
            or isinstance(width, bool)
            or width <= 0
            or not isinstance(height, int)
            or isinstance(height, bool)
            or height <= 0
        ):
            raise CalibrationDatasetError("Layout dimensions must be positive.")
        resolution_id = _require_identifier(
            layout["resolution_id"], f"{name}.resolution_id"
        )
        if layout["pixel_format"] != "rgb8":
            raise CalibrationDatasetError("Frozen frame pixel format must be rgb8.")
        layout_dimensions[layout_id] = (
            width,
            height,
            resolution_id,
            layout["pixel_format"],
        )
        markers = layout["markers"]
        if not isinstance(markers, list) or len(markers) != 4:
            raise CalibrationDatasetError("Every layout requires four markers.")
        seen_roles: set[str] = set()
        for marker_index, raw_marker in enumerate(markers):
            marker_name = f"{name}.markers[{marker_index}]"
            marker = _require_mapping(raw_marker, marker_name)
            _require_exact_keys(
                marker,
                {
                    "marker_id",
                    "marker_role",
                    "marker_color",
                    "image_xy",
                    "world_xz_blocks",
                    "coordinate_source_hash",
                    "source_frame_id",
                    "source_frame_hash",
                    "localization_method_version",
                    "segmentation_pixel_count",
                    "bounding_box_xyxy",
                },
                marker_name,
            )
            marker_id = _require_identifier(
                marker["marker_id"], f"{marker_name}.marker_id"
            )
            role = _require_identifier(
                marker["marker_role"], f"{marker_name}.marker_role"
            )
            if marker_id != role or role_colors.get(role) != marker["marker_color"]:
                raise CalibrationDatasetError("Marker role/color binding changed.")
            if role in seen_roles:
                raise CalibrationDatasetError("Duplicate marker role.")
            seen_roles.add(role)
            image_xy = _finite_pair(
                marker["image_xy"], f"{marker_name}.image_xy", non_negative=True
            )
            _finite_pair(
                marker["world_xz_blocks"],
                f"{marker_name}.world_xz_blocks",
            )
            if not (image_xy[0] < width and image_xy[1] < height):
                raise CalibrationDatasetError("Marker image point is outside frame.")
            _require_sha256(
                marker["coordinate_source_hash"],
                f"{marker_name}.coordinate_source_hash",
            )
            _require_identifier(
                marker["source_frame_id"], f"{marker_name}.source_frame_id"
            )
            _require_sha256(
                marker["source_frame_hash"], f"{marker_name}.source_frame_hash"
            )
            _require_identifier(
                marker["localization_method_version"],
                f"{marker_name}.localization_method_version",
            )
            _require_non_negative_integer(
                marker["segmentation_pixel_count"],
                f"{marker_name}.segmentation_pixel_count",
            )
            box = marker["bounding_box_xyxy"]
            if (
                not isinstance(box, list)
                or len(box) != 4
                or any(
                    not isinstance(value, int) or isinstance(value, bool)
                    for value in box
                )
                or not (0 <= box[0] < box[2] <= width)
                or not (0 <= box[1] < box[3] <= height)
            ):
                raise CalibrationDatasetError("Marker bounding box is malformed.")
        if seen_roles != set(role_colors):
            raise CalibrationDatasetError("Canonical marker roles are incomplete.")

    frames = root["frames"]
    if not isinstance(frames, list) or not frames:
        raise CalibrationDatasetError("frames must be a non-empty list.")
    frame_ids: set[str] = set()
    source_keys: set[tuple[str, int]] = set()
    coverage: set[tuple[str, str, str, str]] = set()
    for frame_index, raw_frame in enumerate(frames):
        name = f"frames[{frame_index}]"
        frame = _require_mapping(raw_frame, name)
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
                "source_git_revision",
                "source_git_path",
                "decoded_rgb_hash",
                "image_width_px",
                "image_height_px",
                "pixel_format",
                "resolution_id",
                "image_region",
                "threshold_selection_eligible",
                "paired_background_frame_id",
            },
            name,
        )
        frame_id = _require_identifier(frame["frame_id"], f"{name}.frame_id")
        if frame_id in frame_ids:
            raise CalibrationDatasetError("Duplicate frame_id.")
        frame_ids.add(frame_id)
        layout_id = _require_identifier(frame["layout_id"], f"{name}.layout_id")
        pose_id = _require_identifier(
            frame["canonical_camera_pose_id"],
            f"{name}.canonical_camera_pose_id",
        )
        if (layout_id, pose_id) not in layout_keys:
            raise CalibrationDatasetError("Frame references unknown layout/pose.")
        split = frame["split"]
        truth = frame["truth_class"]
        if split not in CALIBRATION_SPLITS or truth not in TRUTH_CLASSES:
            raise CalibrationDatasetError("Frame split or truth is invalid.")
        if frame["truth_present"] is not (truth == "visible"):
            raise CalibrationDatasetError("Frame truth fields disagree.")
        if frame["threshold_selection_eligible"] is not (split == "calibration"):
            raise CalibrationDatasetError("Threshold-selection eligibility leaked.")
        source_id = _require_identifier(
            frame["source_artifact_id"], f"{name}.source_artifact_id"
        )
        source_index = _require_non_negative_integer(
            frame["source_frame_idx"], f"{name}.source_frame_idx"
        )
        source_key = (source_id, source_index)
        if source_key in source_keys:
            raise CalibrationDatasetError("Source frame crosses split membership.")
        source_keys.add(source_key)
        _require_sha256(frame["source_frame_hash"], f"{name}.source_frame_hash")
        _require_sha256(frame["decoded_rgb_hash"], f"{name}.decoded_rgb_hash")
        if frame["source_git_revision"] != revision:
            raise CalibrationDatasetError("Frame source revision changed.")
        _require_identifier(frame["source_git_path"], f"{name}.source_git_path")
        expected_dimensions = layout_dimensions[layout_id]
        observed_dimensions = (
            frame["image_width_px"],
            frame["image_height_px"],
            frame["resolution_id"],
            frame["pixel_format"],
        )
        if observed_dimensions != expected_dimensions:
            raise CalibrationDatasetError("Frame resolution binding changed.")
        _require_identifier(frame["image_region"], f"{name}.image_region")
        paired = frame["paired_background_frame_id"]
        if truth == "visible":
            _require_identifier(paired, f"{name}.paired_background_frame_id")
        elif paired is not None:
            raise CalibrationDatasetError("Negative frames require null pair.")
        coverage.add((layout_id, pose_id, split, truth))
    missing_coverage = [
        (layout_id, pose_id, split, truth)
        for layout_id, pose_id in sorted(layout_keys)
        for split in sorted(CALIBRATION_SPLITS)
        for truth in sorted(TRUTH_CLASSES)
        if (layout_id, pose_id, split, truth) not in coverage
    ]
    if missing_coverage:
        raise CalibrationDatasetError(
            f"Frozen split lacks required coverage: {missing_coverage}."
        )
    for frame in frames:
        paired = frame["paired_background_frame_id"]
        if paired is not None and paired not in frame_ids:
            raise CalibrationDatasetError("Visible frame pair is missing.")
    expected_version = "sha256:" + hash_json_value(
        {key: value for key, value in root.items() if key != "split_version"}
    )
    if root["split_version"] != expected_version:
        raise CalibrationDatasetError("split_version is not content-addressed.")


def validate_detector_calibration_dataset(document: Mapping[str, Any]) -> None:
    """Validate split integrity, image truth, and four-marker provenance."""

    root = _require_mapping(document, "detector calibration dataset")
    if root.get("schema_version") != SCHEMA_VERSION:
        raise CalibrationDatasetError("schema_version must remain '1.0'.")
    version = root.get("detector_calibration_schema_version")
    if version == FROZEN_DETECTOR_CALIBRATION_SCHEMA_VERSION:
        _validate_frozen_detector_calibration_dataset(root)
        return
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
