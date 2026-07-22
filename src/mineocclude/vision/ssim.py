"""Explicit, dependency-light SSIM and background-mask measurement."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


class SsimError(ValueError):
    """Raised when frames are misaligned or SSIM settings are invalid."""


@dataclass(frozen=True)
class SsimResult:
    full_frame_ssim: float
    background_masked_ssim: float
    full_frame_pixel_count: int
    background_pixel_count: int
    data_range: float
    channel_handling: str = "rgb_per_channel_mean"

    def __post_init__(self) -> None:
        for name, value in (
            ("full_frame_ssim", self.full_frame_ssim),
            ("background_masked_ssim", self.background_masked_ssim),
        ):
            if (
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not math.isfinite(float(value))
                or not -1.0 <= float(value) <= 1.0
            ):
                raise SsimError(f"{name} must be finite and lie in [-1, 1].")
        for name, value in (
            ("full_frame_pixel_count", self.full_frame_pixel_count),
            ("background_pixel_count", self.background_pixel_count),
        ):
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                raise SsimError(f"{name} must be a positive integer.")
        if self.background_pixel_count > self.full_frame_pixel_count:
            raise SsimError("background_pixel_count cannot exceed full frame pixels.")
        if (
            not isinstance(self.data_range, (int, float))
            or isinstance(self.data_range, bool)
            or not math.isfinite(float(self.data_range))
            or self.data_range <= 0
        ):
            raise SsimError("data_range must be finite and positive.")
        if self.channel_handling != "rgb_per_channel_mean":
            raise SsimError("Unsupported channel_handling declaration.")

    def to_record(self) -> dict[str, Any]:
        return {
            "full_frame_ssim": self.full_frame_ssim,
            "background_masked_ssim": self.background_masked_ssim,
            "full_frame_pixel_count": self.full_frame_pixel_count,
            "background_pixel_count": self.background_pixel_count,
            "data_range": self.data_range,
            "channel_handling": self.channel_handling,
        }


def _normalize_image(
    image: Sequence[Sequence[Sequence[float]]], name: str
) -> tuple[int, int, int, list[list[tuple[float, ...]]]]:
    if (
        not isinstance(image, Sequence)
        or isinstance(image, (str, bytes))
        or not image
    ):
        raise SsimError(f"{name} must contain image rows.")
    width: int | None = None
    channel_count: int | None = None
    normalized: list[list[tuple[float, ...]]] = []
    for row_index, row in enumerate(image):
        if (
            not isinstance(row, Sequence)
            or isinstance(row, (str, bytes))
            or not row
        ):
            raise SsimError(f"{name} row {row_index} is empty or invalid.")
        if width is None:
            width = len(row)
        elif len(row) != width:
            raise SsimError(f"{name} rows must have equal width.")
        normalized_row: list[tuple[float, ...]] = []
        for pixel in row:
            if (
                not isinstance(pixel, Sequence)
                or isinstance(pixel, (str, bytes))
                or not pixel
            ):
                raise SsimError(f"{name} pixels must contain channel values.")
            if channel_count is None:
                channel_count = len(pixel)
            elif len(pixel) != channel_count:
                raise SsimError(f"{name} pixels must have equal channel counts.")
            channels: list[float] = []
            for value in pixel:
                if (
                    not isinstance(value, (int, float))
                    or isinstance(value, bool)
                    or not math.isfinite(float(value))
                ):
                    raise SsimError(f"{name} channel values must be finite numbers.")
                channels.append(float(value))
            normalized_row.append(tuple(channels))
        normalized.append(normalized_row)
    if width is None or channel_count is None:
        raise SsimError(f"{name} contains no pixels.")
    if channel_count != 3:
        raise SsimError(f"{name} must contain exactly three RGB channels.")
    return width, len(normalized), channel_count, normalized


def _validate_mask(
    mask: Sequence[Sequence[bool]] | None,
    *,
    width: int,
    height: int,
) -> list[list[bool]]:
    if mask is None:
        return [[True] * width for _ in range(height)]
    if (
        not isinstance(mask, Sequence)
        or isinstance(mask, (str, bytes))
        or len(mask) != height
    ):
        raise SsimError("Mask height must equal frame height.")
    normalized: list[list[bool]] = []
    for row in mask:
        if (
            not isinstance(row, Sequence)
            or isinstance(row, (str, bytes))
            or len(row) != width
            or any(not isinstance(value, bool) for value in row)
        ):
            raise SsimError("Mask rows must be boolean and match frame width.")
        normalized.append(list(row))
    return normalized


def _compute_ssim_normalized(
    first: list[list[tuple[float, ...]]],
    second: list[list[tuple[float, ...]]],
    *,
    width: int,
    height: int,
    data_range: float,
    mask: Sequence[Sequence[bool]] | None = None,
    k1: float = 0.01,
    k2: float = 0.03,
    sample_covariance: bool = True,
) -> float:
    for name, value in (("data_range", data_range), ("k1", k1), ("k2", k2)):
        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not math.isfinite(float(value))
            or float(value) <= 0.0
        ):
            raise SsimError(f"{name} must be finite and positive.")
    if not isinstance(sample_covariance, bool):
        raise SsimError("sample_covariance must be boolean.")
    channels = 3
    for image_name, image in (
        ("first", first),
        ("second", second),
    ):
        if any(
            value < 0.0 or value > float(data_range)
            for row in image
            for pixel in row
            for value in pixel
        ):
            raise SsimError(
                f"{image_name} values must lie in the declared [0, data_range]."
            )
    normalized_mask = _validate_mask(mask, width=width, height=height)
    included = [
        (x, y)
        for y in range(height)
        for x in range(width)
        if normalized_mask[y][x]
    ]
    minimum_count = 2 if sample_covariance else 1
    if len(included) < minimum_count:
        raise SsimError("SSIM mask retains too few pixels for the declared covariance.")

    denominator = len(included) - 1 if sample_covariance else len(included)
    c1 = (float(k1) * float(data_range)) ** 2
    c2 = (float(k2) * float(data_range)) ** 2
    channel_scores: list[float] = []
    for channel in range(channels):
        first_values = [first[y][x][channel] for x, y in included]
        second_values = [second[y][x][channel] for x, y in included]
        first_mean = sum(first_values) / len(first_values)
        second_mean = sum(second_values) / len(second_values)
        first_variance = sum(
            (value - first_mean) ** 2 for value in first_values
        ) / denominator
        second_variance = sum(
            (value - second_mean) ** 2 for value in second_values
        ) / denominator
        covariance = sum(
            (first_value - first_mean) * (second_value - second_mean)
            for first_value, second_value in zip(
                first_values, second_values, strict=True
            )
        ) / denominator
        score_numerator = (
            (2.0 * first_mean * second_mean + c1)
            * (2.0 * covariance + c2)
        )
        score_denominator = (
            (first_mean**2 + second_mean**2 + c1)
            * (first_variance + second_variance + c2)
        )
        if score_denominator == 0.0:
            raise SsimError("SSIM denominator is zero under the declared settings.")
        score = score_numerator / score_denominator
        if not math.isfinite(score):
            raise SsimError("SSIM result is non-finite.")
        channel_scores.append(score)
    return sum(channel_scores) / len(channel_scores)


def compute_ssim(
    first: Sequence[Sequence[Sequence[float]]],
    second: Sequence[Sequence[Sequence[float]]],
    *,
    data_range: float,
    mask: Sequence[Sequence[bool]] | None = None,
    k1: float = 0.01,
    k2: float = 0.03,
    sample_covariance: bool = True,
) -> float:
    """Compute global SSIM independently per RGB channel and average.

    This is deliberately versioned as ``global_ssim_per_channel_mean_v0.1``.
    It is not represented as interchangeable with conventional windowed SSIM.
    """

    width, height, channels, normalized_first = _normalize_image(first, "first")
    other_width, other_height, other_channels, normalized_second = _normalize_image(
        second, "second"
    )
    if (width, height, channels) != (other_width, other_height, other_channels):
        raise SsimError("SSIM frames must have exactly equal dimensions and channels.")
    return _compute_ssim_normalized(
        normalized_first,
        normalized_second,
        width=width,
        height=height,
        data_range=data_range,
        mask=mask,
        k1=k1,
        k2=k2,
        sample_covariance=sample_covariance,
    )


def build_background_mask(
    *,
    width: int,
    height: int,
    bounding_boxes_xyxy: Sequence[Sequence[int]],
    margin_pixels: int,
) -> list[list[bool]]:
    """Keep background outside the union of boxes expanded by a fixed margin."""

    for name, value in (("width", width), ("height", height)):
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise SsimError(f"{name} must be a positive integer.")
    if (
        not isinstance(margin_pixels, int)
        or isinstance(margin_pixels, bool)
        or margin_pixels < 0
    ):
        raise SsimError("margin_pixels must be a non-negative integer.")
    if not isinstance(bounding_boxes_xyxy, Sequence) or isinstance(
        bounding_boxes_xyxy, (str, bytes)
    ):
        raise SsimError("bounding_boxes_xyxy must be a sequence.")
    mask = [[True] * width for _ in range(height)]
    for index, box in enumerate(bounding_boxes_xyxy):
        if (
            not isinstance(box, Sequence)
            or isinstance(box, (str, bytes))
            or len(box) != 4
            or any(not isinstance(value, int) or isinstance(value, bool) for value in box)
        ):
            raise SsimError(f"Bounding box {index} must contain four integers.")
        x_min, y_min, x_max, y_max = box
        if not (0 <= x_min < x_max <= width and 0 <= y_min < y_max <= height):
            raise SsimError(f"Bounding box {index} lies outside the frame.")
        expanded_x_min = max(0, x_min - margin_pixels)
        expanded_y_min = max(0, y_min - margin_pixels)
        expanded_x_max = min(width, x_max + margin_pixels)
        expanded_y_max = min(height, y_max + margin_pixels)
        for y in range(expanded_y_min, expanded_y_max):
            for x in range(expanded_x_min, expanded_x_max):
                mask[y][x] = False
    return mask


def require_frame_alignment(
    first_metadata: Mapping[str, Any],
    second_metadata: Mapping[str, Any],
    *,
    identity_fields: Sequence[str] = ("event_id", "seed", "rollout_frame_idx"),
) -> None:
    """Require exact declared frame identity before comparing pixel arrays."""

    if not isinstance(first_metadata, Mapping) or not isinstance(
        second_metadata, Mapping
    ):
        raise SsimError("Frame metadata must be mappings.")
    if (
        not isinstance(identity_fields, Sequence)
        or isinstance(identity_fields, (str, bytes))
        or not identity_fields
        or any(not isinstance(field, str) or not field for field in identity_fields)
    ):
        raise SsimError("identity_fields must contain non-empty field names.")
    for field in identity_fields:
        if field not in first_metadata or field not in second_metadata:
            raise SsimError(f"Both frames require alignment field {field!r}.")
        if first_metadata[field] != second_metadata[field]:
            raise SsimError(f"Frame alignment mismatch for {field!r}.")


def require_natural_variation_pair(
    first_metadata: Mapping[str, Any],
    second_metadata: Mapping[str, Any],
) -> None:
    """Validate an independent alpha-zero pair at the same scene/time point."""

    require_frame_alignment(
        first_metadata,
        second_metadata,
        identity_fields=("event_id", "layout_id", "rollout_frame_idx"),
    )
    for name, metadata in (
        ("first", first_metadata),
        ("second", second_metadata),
    ):
        if metadata.get("control_type") != "alpha_zero":
            raise SsimError(f"{name} natural-variation frame must be alpha_zero.")
        if not isinstance(metadata.get("rollout_id"), str) or not metadata[
            "rollout_id"
        ]:
            raise SsimError(f"{name} natural-variation frame requires rollout_id.")
        seed = metadata.get("seed")
        if not isinstance(seed, int) or isinstance(seed, bool):
            raise SsimError(f"{name} natural-variation frame requires integer seed.")
    if first_metadata["rollout_id"] == second_metadata["rollout_id"]:
        raise SsimError("Natural variation cannot compare a rollout with itself.")
    if first_metadata["seed"] == second_metadata["seed"]:
        raise SsimError("Natural variation requires independent alpha-zero seeds.")


def compare_frames(
    pushed: Sequence[Sequence[Sequence[float]]],
    baseline: Sequence[Sequence[Sequence[float]]],
    *,
    data_range: float,
    pushed_box_xyxy: Sequence[int],
    baseline_box_xyxy: Sequence[int],
    background_margin_pixels: int,
    k1: float = 0.01,
    k2: float = 0.03,
    sample_covariance: bool = True,
) -> SsimResult:
    """Compute full-frame and declared background-masked coherence."""

    width, height, channels, normalized_pushed = _normalize_image(pushed, "pushed")
    other_width, other_height, other_channels, normalized_baseline = _normalize_image(
        baseline, "baseline"
    )
    if (width, height, channels) != (other_width, other_height, other_channels):
        raise SsimError("Pushed and baseline frames must have equal dimensions.")
    mask = build_background_mask(
        width=width,
        height=height,
        bounding_boxes_xyxy=[pushed_box_xyxy, baseline_box_xyxy],
        margin_pixels=background_margin_pixels,
    )
    full = _compute_ssim_normalized(
        normalized_pushed,
        normalized_baseline,
        width=width,
        height=height,
        data_range=data_range,
        k1=k1,
        k2=k2,
        sample_covariance=sample_covariance,
    )
    masked = _compute_ssim_normalized(
        normalized_pushed,
        normalized_baseline,
        width=width,
        height=height,
        data_range=data_range,
        mask=mask,
        k1=k1,
        k2=k2,
        sample_covariance=sample_covariance,
    )
    background_count = sum(sum(row) for row in mask)
    return SsimResult(
        full_frame_ssim=full,
        background_masked_ssim=masked,
        full_frame_pixel_count=width * height,
        background_pixel_count=background_count,
        data_range=float(data_range),
    )


def summarize_natural_variation(scores: Sequence[float]) -> dict[str, float | int]:
    """Summarize unpushed-vs-unpushed SSIM without hiding individual scores."""

    if (
        not isinstance(scores, Sequence)
        or isinstance(scores, (str, bytes))
        or not scores
        or any(
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not math.isfinite(float(value))
            for value in scores
        )
    ):
        raise SsimError("Natural-variation scores must be finite and non-empty.")
    ordered = sorted(float(value) for value in scores)
    midpoint = len(ordered) // 2
    median = (
        ordered[midpoint]
        if len(ordered) % 2
        else (ordered[midpoint - 1] + ordered[midpoint]) / 2.0
    )
    return {
        "sample_count": len(ordered),
        "mean": sum(ordered) / len(ordered),
        "median": median,
        "minimum": ordered[0],
        "maximum": ordered[-1],
    }
