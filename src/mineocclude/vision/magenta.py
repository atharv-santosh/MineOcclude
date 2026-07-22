"""Dependency-light, versionable HSV detector for Person E calibration.

The detector consumes decoded RGB arrays. Video/image decoding is intentionally
outside this module until the official runtime dependencies are pinned.
"""

from __future__ import annotations

import colorsys
import math
from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any


class VisionInputError(ValueError):
    """Raised when pixels or detector parameters are malformed."""


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
