"""Dependency-light, versionable HSV detector for Person E calibration.

The detector consumes decoded RGB arrays. Video/image decoding is intentionally
outside this module until the official runtime dependencies are pinned.
"""

from __future__ import annotations

import colorsys
import math
from collections import deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


class VisionInputError(ValueError):
    """Raised when pixels or detector parameters are malformed."""


DETECTION_DOCUMENT_SCHEMA_VERSION = "person-e-detection-records-v1.0"
CALIBRATION_DETECTION_DOCUMENT_SCHEMA_VERSION = (
    "person-e-detection-records-v1.1"
)
DETECTOR_ALGORITHM_VERSION = "hsv-largest-valid-blob-v0.1"
DETECTION_STATUSES = frozenset({"detected", "not_detected", "rejected"})
DETECTION_QUALITY_STATUSES = frozenset({"accepted", "low_quality", "rejected"})


@dataclass(frozen=True)
class HsvRange:
    """HSV threshold using hue degrees and unit-interval saturation/value."""

    hue_min_degrees: float
    hue_max_degrees: float
    saturation_min: float
    saturation_max: float
    value_min: float
    value_max: float

    def __post_init__(self) -> None:
        values = (
            self.hue_min_degrees,
            self.hue_max_degrees,
            self.saturation_min,
            self.saturation_max,
            self.value_min,
            self.value_max,
        )
        if any(
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not math.isfinite(float(value))
            for value in values
        ):
            raise VisionInputError("HSV range values must be finite numbers.")
        if not (
            0.0 <= self.hue_min_degrees < 360.0
            and 0.0 <= self.hue_max_degrees < 360.0
        ):
            raise VisionInputError("Hue bounds must lie in [0, 360).")
        for low, high, name in (
            (self.saturation_min, self.saturation_max, "saturation"),
            (self.value_min, self.value_max, "value"),
        ):
            if not 0.0 <= low <= high <= 1.0:
                raise VisionInputError(f"{name} bounds must satisfy 0 <= min <= max <= 1.")

    def contains(self, hue: float, saturation: float, value: float) -> bool:
        if self.hue_min_degrees <= self.hue_max_degrees:
            hue_matches = self.hue_min_degrees <= hue <= self.hue_max_degrees
        else:
            hue_matches = hue >= self.hue_min_degrees or hue <= self.hue_max_degrees
        return (
            hue_matches
            and self.saturation_min <= saturation <= self.saturation_max
            and self.value_min <= value <= self.value_max
        )


@dataclass(frozen=True)
class DetectionResult:
    """One deterministic presence/localization result in image coordinates."""

    status: str
    centroid_xy: tuple[float, float] | None
    area_pixels: int | None
    bounding_box_xyxy: tuple[int, int, int, int] | None
    threshold_match_pixels: int
    candidate_blob_count: int
    rejection_reason: str | None

    @property
    def detected(self) -> bool:
        return self.status == "detected"

    def to_record(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "centroid_xy": (
                None if self.centroid_xy is None else list(self.centroid_xy)
            ),
            "area_pixels": self.area_pixels,
            "bounding_box_xyxy": (
                None
                if self.bounding_box_xyxy is None
                else list(self.bounding_box_xyxy)
            ),
            "threshold_match_pixels": self.threshold_match_pixels,
            "candidate_blob_count": self.candidate_blob_count,
            "rejection_reason": self.rejection_reason,
        }


@dataclass(frozen=True)
class PresenceMetrics:
    true_positive: int
    false_positive: int
    true_negative: int
    false_negative: int
    precision: float
    recall: float


def _validate_image(
    image: Sequence[Sequence[Sequence[float]]],
) -> tuple[int, int, list[list[tuple[float, float, float]]]]:
    if (
        not isinstance(image, Sequence)
        or isinstance(image, (str, bytes))
        or not image
    ):
        raise VisionInputError("Image must contain at least one row.")
    width: int | None = None
    normalized: list[list[tuple[float, float, float]]] = []
    for row_index, row in enumerate(image):
        if (
            not isinstance(row, Sequence)
            or isinstance(row, (str, bytes))
            or not row
        ):
            raise VisionInputError(f"Image row {row_index} is empty or invalid.")
        if width is None:
            width = len(row)
        elif len(row) != width:
            raise VisionInputError("Image rows must have equal width.")
        normalized_row: list[tuple[float, float, float]] = []
        for column_index, pixel in enumerate(row):
            if (
                not isinstance(pixel, Sequence)
                or isinstance(pixel, (str, bytes))
                or len(pixel) != 3
            ):
                raise VisionInputError(
                    f"Pixel ({column_index}, {row_index}) must contain RGB values."
                )
            values: list[float] = []
            for channel in pixel:
                if (
                    not isinstance(channel, (int, float))
                    or isinstance(channel, bool)
                    or not math.isfinite(float(channel))
                    or not 0.0 <= float(channel) <= 255.0
                ):
                    raise VisionInputError("RGB values must be finite values in [0, 255].")
                values.append(float(channel))
            normalized_row.append((values[0], values[1], values[2]))
        normalized.append(normalized_row)
    if width is None:
        raise VisionInputError("Image contains no pixels.")
    return width, len(normalized), normalized


def _erode(mask: list[list[bool]], radius: int) -> list[list[bool]]:
    height = len(mask)
    width = len(mask[0])
    output = [[False] * width for _ in range(height)]
    for y in range(height):
        for x in range(width):
            output[y][x] = all(
                0 <= other_y < height
                and 0 <= other_x < width
                and mask[other_y][other_x]
                for other_y in range(y - radius, y + radius + 1)
                for other_x in range(x - radius, x + radius + 1)
            )
    return output


def _dilate(mask: list[list[bool]], radius: int) -> list[list[bool]]:
    height = len(mask)
    width = len(mask[0])
    output = [[False] * width for _ in range(height)]
    for y in range(height):
        for x in range(width):
            output[y][x] = any(
                0 <= other_y < height
                and 0 <= other_x < width
                and mask[other_y][other_x]
                for other_y in range(y - radius, y + radius + 1)
                for other_x in range(x - radius, x + radius + 1)
            )
    return output


def _components(
    mask: list[list[bool]], connectivity: int
) -> list[list[tuple[int, int]]]:
    height = len(mask)
    width = len(mask[0])
    visited = [[False] * width for _ in range(height)]
    if connectivity == 4:
        offsets = ((-1, 0), (1, 0), (0, -1), (0, 1))
    elif connectivity == 8:
        offsets = tuple(
            (dx, dy)
            for dy in (-1, 0, 1)
            for dx in (-1, 0, 1)
            if (dx, dy) != (0, 0)
        )
    else:
        raise VisionInputError("connectivity must be 4 or 8.")
    components: list[list[tuple[int, int]]] = []
    for y in range(height):
        for x in range(width):
            if not mask[y][x] or visited[y][x]:
                continue
            queue = deque([(x, y)])
            visited[y][x] = True
            component: list[tuple[int, int]] = []
            while queue:
                current_x, current_y = queue.popleft()
                component.append((current_x, current_y))
                for dx, dy in offsets:
                    next_x = current_x + dx
                    next_y = current_y + dy
                    if (
                        0 <= next_x < width
                        and 0 <= next_y < height
                        and mask[next_y][next_x]
                        and not visited[next_y][next_x]
                    ):
                        visited[next_y][next_x] = True
                        queue.append((next_x, next_y))
            components.append(component)
    return components


def detect_magenta(
    image: Sequence[Sequence[Sequence[float]]],
    *,
    hsv_ranges: Sequence[HsvRange],
    min_area_pixels: int = 1,
    max_area_pixels: int | None = None,
    open_iterations: int = 0,
    close_iterations: int = 0,
    morphology_radius_pixels: int = 1,
    connectivity: int = 8,
) -> DetectionResult:
    """Detect the largest calibrated magenta blob in one RGB image."""

    if (
        not isinstance(hsv_ranges, Sequence)
        or isinstance(hsv_ranges, (str, bytes))
        or not hsv_ranges
        or any(not isinstance(item, HsvRange) for item in hsv_ranges)
    ):
        raise VisionInputError("At least one validated HsvRange is required.")
    for name, value in (
        ("min_area_pixels", min_area_pixels),
        ("open_iterations", open_iterations),
        ("close_iterations", close_iterations),
        ("morphology_radius_pixels", morphology_radius_pixels),
    ):
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise VisionInputError(f"{name} must be a non-negative integer.")
    if min_area_pixels < 1:
        raise VisionInputError("min_area_pixels must be at least one.")
    if max_area_pixels is not None and (
        not isinstance(max_area_pixels, int)
        or isinstance(max_area_pixels, bool)
        or max_area_pixels < min_area_pixels
    ):
        raise VisionInputError("max_area_pixels must be null or >= min_area_pixels.")
    if connectivity not in {4, 8}:
        raise VisionInputError("connectivity must be 4 or 8.")

    width, height, normalized = _validate_image(image)
    mask = [[False] * width for _ in range(height)]
    for y, row in enumerate(normalized):
        for x, (red, green, blue) in enumerate(row):
            hue_unit, saturation, value = colorsys.rgb_to_hsv(
                red / 255.0, green / 255.0, blue / 255.0
            )
            hue_degrees = (hue_unit * 360.0) % 360.0
            mask[y][x] = any(
                threshold.contains(hue_degrees, saturation, value)
                for threshold in hsv_ranges
            )
    threshold_match_pixels = sum(sum(row) for row in mask)
    if threshold_match_pixels == 0:
        return DetectionResult(
            status="not_detected",
            centroid_xy=None,
            area_pixels=None,
            bounding_box_xyxy=None,
            threshold_match_pixels=0,
            candidate_blob_count=0,
            rejection_reason="no_threshold_match",
        )

    for _ in range(open_iterations):
        mask = _dilate(_erode(mask, morphology_radius_pixels), morphology_radius_pixels)
    for _ in range(close_iterations):
        mask = _erode(_dilate(mask, morphology_radius_pixels), morphology_radius_pixels)

    candidates = _components(mask, connectivity)
    valid = [
        component
        for component in candidates
        if len(component) >= min_area_pixels
        and (max_area_pixels is None or len(component) <= max_area_pixels)
    ]
    if not valid:
        return DetectionResult(
            status="not_detected",
            centroid_xy=None,
            area_pixels=None,
            bounding_box_xyxy=None,
            threshold_match_pixels=threshold_match_pixels,
            candidate_blob_count=len(candidates),
            rejection_reason="no_valid_blob",
        )
    valid.sort(
        key=lambda component: (
            -len(component),
            min(y for _, y in component),
            min(x for x, _ in component),
        )
    )
    selected = valid[0]
    xs = [x for x, _ in selected]
    ys = [y for _, y in selected]
    return DetectionResult(
        status="detected",
        centroid_xy=(sum(xs) / len(xs), sum(ys) / len(ys)),
        area_pixels=len(selected),
        bounding_box_xyxy=(min(xs), min(ys), max(xs) + 1, max(ys) + 1),
        threshold_match_pixels=threshold_match_pixels,
        candidate_blob_count=len(candidates),
        rejection_reason=None,
    )


def evaluate_presence(
    labeled_results: Sequence[tuple[bool, DetectionResult]],
) -> PresenceMetrics:
    """Compute held-out precision/recall with both positive and negative truth."""

    if (
        not isinstance(labeled_results, Sequence)
        or isinstance(labeled_results, (str, bytes))
        or not labeled_results
    ):
        raise VisionInputError("Presence evaluation requires labeled results.")
    if any(
        not isinstance(item, tuple)
        or len(item) != 2
        or not isinstance(item[0], bool)
        or not isinstance(item[1], DetectionResult)
        for item in labeled_results
    ):
        raise VisionInputError("Each evaluation item must be (truth, DetectionResult).")
    truths = [truth for truth, _ in labeled_results]
    if not any(truths) or all(truths):
        raise VisionInputError(
            "Held-out presence evaluation requires positive and negative frames."
        )
    true_positive = sum(truth and result.detected for truth, result in labeled_results)
    false_positive = sum(
        not truth and result.detected for truth, result in labeled_results
    )
    true_negative = sum(
        not truth and not result.detected for truth, result in labeled_results
    )
    false_negative = sum(
        truth and not result.detected for truth, result in labeled_results
    )
    precision_denominator = true_positive + false_positive
    recall_denominator = true_positive + false_negative
    precision = (
        true_positive / precision_denominator if precision_denominator else 0.0
    )
    recall = true_positive / recall_denominator if recall_denominator else 0.0
    return PresenceMetrics(
        true_positive=true_positive,
        false_positive=false_positive,
        true_negative=true_negative,
        false_negative=false_negative,
        precision=precision,
        recall=recall,
    )


def _explicit_id(value: Any, name: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or any(character.isspace() for character in value)
    ):
        raise VisionInputError(f"{name} must be an explicit non-empty ID.")
    return value


def _non_negative_int(value: Any, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise VisionInputError(f"{name} must be a non-negative integer.")
    return value


def _validate_calibration_detection_document(
    document: Mapping[str, Any],
) -> None:
    required_root = {
        "schema_version",
        "detection_schema_version",
        "document_id",
        "synthetic",
        "scientific_use",
        "detector_version",
        "threshold_version",
        "split_version",
        "settings_hash",
        "source_contexts",
        "records",
    }
    if set(document) != required_root:
        raise VisionInputError("Calibration detection-document fields changed.")
    if document["schema_version"] != "1.0":
        raise VisionInputError("schema_version must remain '1.0'.")
    for field in (
        "document_id",
        "detector_version",
        "threshold_version",
        "split_version",
    ):
        _explicit_id(document[field], field)
    settings_hash = document["settings_hash"]
    if (
        not isinstance(settings_hash, str)
        or len(settings_hash) != 64
        or any(character not in "0123456789abcdef" for character in settings_hash)
    ):
        raise VisionInputError("settings_hash must be lowercase SHA-256.")
    if document["synthetic"] is not False or document["scientific_use"] != "permitted":
        raise VisionInputError("Real calibration records must permit scientific use.")

    context_fields = {
        "source_frame_id",
        "source_artifact_id",
        "source_frame_idx",
        "source_frame_hash",
        "decoded_rgb_hash",
        "source_git_revision",
        "source_git_path",
        "split",
        "layout_id",
        "canonical_camera_pose_id",
        "resolution_id",
        "image_width_px",
        "image_height_px",
        "pixel_format",
        "image_coordinate_system",
        "truth_class",
        "truth_present",
        "frame_available",
    }
    contexts = document["source_contexts"]
    if not isinstance(contexts, list) or not contexts:
        raise VisionInputError("source_contexts must be a non-empty list.")
    context_by_id: dict[str, Mapping[str, Any]] = {}
    source_keys: set[tuple[str, int]] = set()
    for index, context in enumerate(contexts):
        name = f"source_contexts[{index}]"
        if not isinstance(context, Mapping) or set(context) != context_fields:
            raise VisionInputError(f"{name} fields changed.")
        for field in (
            "source_frame_id",
            "source_artifact_id",
            "source_git_path",
            "split",
            "layout_id",
            "canonical_camera_pose_id",
            "resolution_id",
            "pixel_format",
        ):
            _explicit_id(context[field], f"{name}.{field}")
        frame_id = context["source_frame_id"]
        if frame_id in context_by_id:
            raise VisionInputError("Duplicate source_frame_id.")
        source_index = _non_negative_int(
            context["source_frame_idx"], f"{name}.source_frame_idx"
        )
        source_key = (context["source_artifact_id"], source_index)
        if source_key in source_keys:
            raise VisionInputError("Duplicate source-frame identity.")
        source_keys.add(source_key)
        for field in ("source_frame_hash", "decoded_rgb_hash"):
            value = context[field]
            if (
                not isinstance(value, str)
                or len(value) != 64
                or any(character not in "0123456789abcdef" for character in value)
            ):
                raise VisionInputError(f"{name}.{field} must be SHA-256.")
        revision = context["source_git_revision"]
        if (
            not isinstance(revision, str)
            or len(revision) != 40
            or any(character not in "0123456789abcdef" for character in revision)
        ):
            raise VisionInputError(f"{name}.source_git_revision must be Git SHA.")
        if context["split"] != "calibration":
            raise VisionInputError("Calibration records cannot contain held-out frames.")
        if context["truth_class"] not in {"visible", "negative"}:
            raise VisionInputError("Calibration truth_class is invalid.")
        if context["truth_present"] is not (
            context["truth_class"] == "visible"
        ):
            raise VisionInputError("Calibration truth fields disagree.")
        for field in ("image_width_px", "image_height_px"):
            value = context[field]
            if (
                not isinstance(value, int)
                or isinstance(value, bool)
                or value <= 0
            ):
                raise VisionInputError(f"{name}.{field} must be positive.")
        if (
            context["pixel_format"] != "rgb8"
            or context["image_coordinate_system"]
            != "pixel_center_xy_zero_based"
            or context["frame_available"] is not True
        ):
            raise VisionInputError("Calibration image contract changed.")
        context_by_id[frame_id] = context

    record_fields = (
        context_fields
        - {"frame_available"}
        | {
            "detection_id",
            "detector_version",
            "threshold_version",
            "status",
            "presence",
            "centroid_xy",
            "area_pixels",
            "bounding_box_xyxy",
            "quality_status",
            "rejection_reason",
            "threshold_match_pixels",
            "candidate_blob_count",
        }
    )
    records = document["records"]
    if not isinstance(records, list) or len(records) != len(contexts):
        raise VisionInputError("Calibration records must cover every context.")
    seen_detections: set[str] = set()
    seen_frames: set[str] = set()
    for index, record in enumerate(records):
        name = f"records[{index}]"
        if not isinstance(record, Mapping) or set(record) != record_fields:
            raise VisionInputError(f"{name} fields changed.")
        detection_id = _explicit_id(
            record["detection_id"], f"{name}.detection_id"
        )
        if detection_id in seen_detections:
            raise VisionInputError("Duplicate detection_id.")
        seen_detections.add(detection_id)
        frame_id = _explicit_id(
            record["source_frame_id"], f"{name}.source_frame_id"
        )
        context = context_by_id.get(frame_id)
        if context is None or frame_id in seen_frames:
            raise VisionInputError("Detection source-frame identity is invalid.")
        seen_frames.add(frame_id)
        for field in context_fields - {"frame_available"}:
            if record[field] != context[field]:
                raise VisionInputError(f"{name}.{field} disagrees with context.")
        if (
            record["detector_version"] != document["detector_version"]
            or record["threshold_version"] != document["threshold_version"]
        ):
            raise VisionInputError("Detection version propagation changed.")
        status = record["status"]
        quality = record["quality_status"]
        if status not in DETECTION_STATUSES or quality not in DETECTION_QUALITY_STATUSES:
            raise VisionInputError("Detection status or quality is invalid.")
        if record["presence"] is not (status == "detected"):
            raise VisionInputError("Detection presence disagrees with status.")
        for field in ("threshold_match_pixels", "candidate_blob_count"):
            _non_negative_int(record[field], f"{name}.{field}")
        if status == "not_detected":
            if (
                quality == "rejected"
                or record["centroid_xy"] is not None
                or record["area_pixels"] is not None
                or record["bounding_box_xyxy"] is not None
                or record["rejection_reason"]
                not in {"no_threshold_match", "no_valid_blob"}
            ):
                raise VisionInputError("Not-detected calibration record is malformed.")
            continue
        if status == "rejected":
            if (
                quality != "rejected"
                or not isinstance(record["rejection_reason"], str)
                or any(
                    record[field] is not None
                    for field in (
                        "centroid_xy",
                        "area_pixels",
                        "bounding_box_xyxy",
                    )
                )
            ):
                raise VisionInputError("Rejected calibration record is malformed.")
            continue
        if quality == "rejected" or record["rejection_reason"] is not None:
            raise VisionInputError("Detected calibration record has invalid quality.")
        centroid = record["centroid_xy"]
        box = record["bounding_box_xyxy"]
        area = record["area_pixels"]
        if (
            not isinstance(centroid, list)
            or len(centroid) != 2
            or any(
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not math.isfinite(float(value))
                for value in centroid
            )
            or not isinstance(box, list)
            or len(box) != 4
            or any(
                not isinstance(value, int) or isinstance(value, bool)
                for value in box
            )
            or not isinstance(area, int)
            or isinstance(area, bool)
            or area <= 0
        ):
            raise VisionInputError("Detected calibration geometry is malformed.")
        x0, y0, x1, y1 = box
        if not (
            0 <= x0 < x1 <= context["image_width_px"]
            and 0 <= y0 < y1 <= context["image_height_px"]
            and x0 <= float(centroid[0]) < x1
            and y0 <= float(centroid[1]) < y1
            and area <= (x1 - x0) * (y1 - y0)
        ):
            raise VisionInputError("Detected calibration geometry is out of bounds.")
    if seen_frames != set(context_by_id):
        raise VisionInputError("Calibration records do not cover all contexts.")


def validate_detection_document(document: Mapping[str, Any]) -> None:
    """Validate synthetic or real detector records against source contexts.

    Source contexts are an explicit join authority for this E-owned evidence.
    A missing frame is preserved as a rejected record; any other identity
    disagreement is malformed input and fails closed.
    """

    if not isinstance(document, Mapping):
        raise VisionInputError("Detection document must be a mapping.")
    if (
        document.get("detection_schema_version")
        == CALIBRATION_DETECTION_DOCUMENT_SCHEMA_VERSION
    ):
        _validate_calibration_detection_document(document)
        return
    required_root = {
        "schema_version",
        "detection_schema_version",
        "document_id",
        "synthetic",
        "scientific_use",
        "detector_version",
        "threshold_version",
        "source_contexts",
        "records",
    }
    if set(document) != required_root:
        raise VisionInputError("Detection document fields have changed.")
    if document["schema_version"] != "1.0":
        raise VisionInputError("schema_version must remain '1.0'.")
    if document["detection_schema_version"] != DETECTION_DOCUMENT_SCHEMA_VERSION:
        raise VisionInputError("Unsupported detection schema version.")
    _explicit_id(document["document_id"], "document_id")
    detector_version = _explicit_id(document["detector_version"], "detector_version")
    threshold_version = _explicit_id(
        document["threshold_version"], "threshold_version"
    )
    if not isinstance(document["synthetic"], bool):
        raise VisionInputError("synthetic must be boolean.")
    if document["scientific_use"] not in {"forbidden", "permitted"}:
        raise VisionInputError("scientific_use is invalid.")
    if document["synthetic"] and document["scientific_use"] != "forbidden":
        raise VisionInputError("Synthetic detection evidence forbids scientific use.")

    context_fields = {
        "source_frame_id",
        "source_artifact_id",
        "rollout_id",
        "event_id",
        "trajectory_id",
        "model_frame_idx",
        "rollout_frame_idx",
        "layout_id",
        "canonical_camera_pose_id",
        "resolution_id",
        "image_width_px",
        "image_height_px",
        "image_coordinate_system",
        "frame_available",
    }
    contexts = document["source_contexts"]
    if not isinstance(contexts, list) or not contexts:
        raise VisionInputError("source_contexts must be a non-empty list.")
    context_by_frame_id: dict[str, Mapping[str, Any]] = {}
    context_keys: set[tuple[str, int, int]] = set()
    for index, context in enumerate(contexts):
        name = f"source_contexts[{index}]"
        if not isinstance(context, Mapping) or set(context) != context_fields:
            raise VisionInputError(f"{name} fields have changed.")
        for field in (
            "source_frame_id",
            "source_artifact_id",
            "event_id",
            "trajectory_id",
            "layout_id",
            "canonical_camera_pose_id",
            "resolution_id",
        ):
            _explicit_id(context[field], f"{name}.{field}")
        rollout_id = context["rollout_id"]
        if rollout_id is not None:
            _explicit_id(rollout_id, f"{name}.rollout_id")
        model_frame_idx = _non_negative_int(
            context["model_frame_idx"], f"{name}.model_frame_idx"
        )
        rollout_frame_idx = _non_negative_int(
            context["rollout_frame_idx"], f"{name}.rollout_frame_idx"
        )
        for field in ("image_width_px", "image_height_px"):
            value = context[field]
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise VisionInputError(f"{name}.{field} must be a positive integer.")
        if context["image_coordinate_system"] != "pixel_center_xy_zero_based":
            raise VisionInputError(f"{name} has an unsupported coordinate system.")
        if not isinstance(context["frame_available"], bool):
            raise VisionInputError(f"{name}.frame_available must be boolean.")
        frame_id = context["source_frame_id"]
        if frame_id in context_by_frame_id:
            raise VisionInputError(f"Duplicate source_frame_id {frame_id!r}.")
        context_key = (
            context["trajectory_id"],
            model_frame_idx,
            rollout_frame_idx,
        )
        if context_key in context_keys:
            raise VisionInputError(f"Duplicate source scientific identity {context_key!r}.")
        context_keys.add(context_key)
        context_by_frame_id[frame_id] = context

    record_fields = {
        "detection_id",
        *context_fields - {"frame_available"},
        "detector_version",
        "threshold_version",
        "status",
        "centroid_xy",
        "area_pixels",
        "bounding_box_xyxy",
        "quality_status",
        "rejection_reason",
    }
    records = document["records"]
    if not isinstance(records, list) or not records:
        raise VisionInputError("records must be a non-empty list.")
    detection_ids: set[str] = set()
    resolved_frame_ids: set[str] = set()
    for index, record in enumerate(records):
        name = f"records[{index}]"
        if not isinstance(record, Mapping) or set(record) != record_fields:
            raise VisionInputError(f"{name} fields have changed.")
        detection_id = _explicit_id(record["detection_id"], f"{name}.detection_id")
        if detection_id in detection_ids:
            raise VisionInputError(f"Duplicate detection_id {detection_id!r}.")
        detection_ids.add(detection_id)
        frame_id = _explicit_id(record["source_frame_id"], f"{name}.source_frame_id")
        context = context_by_frame_id.get(frame_id)
        if context is None:
            raise VisionInputError(f"{name} references an unknown source frame.")
        if frame_id in resolved_frame_ids:
            raise VisionInputError(f"Source frame {frame_id!r} has multiple records.")
        resolved_frame_ids.add(frame_id)
        for field in context_fields - {"frame_available"}:
            if record[field] != context[field]:
                raise VisionInputError(f"{name}.{field} disagrees with source context.")
        if record["detector_version"] != detector_version:
            raise VisionInputError(f"{name}.detector_version disagrees with envelope.")
        if record["threshold_version"] != threshold_version:
            raise VisionInputError(f"{name}.threshold_version disagrees with envelope.")
        status = record["status"]
        quality = record["quality_status"]
        if status not in DETECTION_STATUSES or quality not in DETECTION_QUALITY_STATUSES:
            raise VisionInputError(f"{name} has invalid status or quality_status.")

        if not context["frame_available"]:
            if (
                status != "rejected"
                or quality != "rejected"
                or record["rejection_reason"] != "missing_frame"
                or any(
                    record[field] is not None
                    for field in ("centroid_xy", "area_pixels", "bounding_box_xyxy")
                )
            ):
                raise VisionInputError(
                    f"{name} must preserve a missing frame as an explicit rejection."
                )
            continue
        if status == "rejected":
            if quality != "rejected" or not isinstance(record["rejection_reason"], str):
                raise VisionInputError(f"{name} rejected evidence needs a reason.")
            if any(
                record[field] is not None
                for field in ("centroid_xy", "area_pixels", "bounding_box_xyxy")
            ):
                raise VisionInputError(f"{name} rejected evidence cannot carry geometry.")
            continue
        if quality == "rejected":
            raise VisionInputError(f"{name} usable detection cannot have rejected quality.")
        if status == "not_detected":
            if (
                record["centroid_xy"] is not None
                or record["area_pixels"] is not None
                or record["bounding_box_xyxy"] is not None
                or record["rejection_reason"] not in {
                    "no_threshold_match",
                    "no_valid_blob",
                }
            ):
                raise VisionInputError(f"{name} not-detected geometry is inconsistent.")
            continue
        if record["rejection_reason"] is not None:
            raise VisionInputError(f"{name} detected record requires null rejection_reason.")
        centroid = record["centroid_xy"]
        box = record["bounding_box_xyxy"]
        area = record["area_pixels"]
        if (
            not isinstance(centroid, list)
            or len(centroid) != 2
            or any(
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not math.isfinite(float(value))
                for value in centroid
            )
            or not isinstance(box, list)
            or len(box) != 4
            or any(not isinstance(value, int) or isinstance(value, bool) for value in box)
            or not isinstance(area, int)
            or isinstance(area, bool)
            or area <= 0
        ):
            raise VisionInputError(f"{name} detected geometry is malformed.")
        x0, y0, x1, y1 = box
        width = context["image_width_px"]
        height = context["image_height_px"]
        if not (0 <= x0 < x1 <= width and 0 <= y0 < y1 <= height):
            raise VisionInputError(f"{name} bounding box is outside the image.")
        if not (x0 <= float(centroid[0]) < x1 and y0 <= float(centroid[1]) < y1):
            raise VisionInputError(f"{name} centroid is outside its bounding box.")
        if area > (x1 - x0) * (y1 - y0):
            raise VisionInputError(f"{name} area exceeds its bounding box.")

    if resolved_frame_ids != set(context_by_frame_id):
        missing = sorted(set(context_by_frame_id) - resolved_frame_ids)
        raise VisionInputError(f"Detection records do not cover source frames: {missing}.")
