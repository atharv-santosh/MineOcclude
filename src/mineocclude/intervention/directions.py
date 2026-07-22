"""Raw-space, elapsed-time-orthogonal Person B intervention directions."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass


class DirectionError(ValueError):
    """Raised when a direction cannot satisfy the frozen B-to-A contract."""


def _finite_vector(name: str, values: Sequence[float]) -> tuple[float, ...]:
    result: list[float] = []
    for value in values:
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
        ):
            raise DirectionError(f"{name} must contain finite numeric values.")
        result.append(float(value))
    if not result:
        raise DirectionError(f"{name} cannot be empty.")
    return tuple(result)


def dot(left: Sequence[float], right: Sequence[float]) -> float:
    left_values = _finite_vector("left direction", left)
    right_values = _finite_vector("right direction", right)
    if len(left_values) != len(right_values):
        raise DirectionError("Direction dimensions differ.")
    result = sum(a * b for a, b in zip(left_values, right_values))
    if not math.isfinite(result):
        raise DirectionError("Direction dot product overflowed.")
    return result


def l2_norm(values: Sequence[float]) -> float:
    vector = _finite_vector("direction", values)
    norm = 0.0
    for value in vector:
        norm = math.hypot(norm, value)
    return norm


def normalize(values: Sequence[float], *, threshold: float = 1e-12) -> tuple[float, ...]:
    vector = _finite_vector("direction", values)
    norm = l2_norm(vector)
    if (
        isinstance(threshold, bool)
        or not isinstance(threshold, (int, float))
        or not math.isfinite(float(threshold))
        or threshold <= 0.0
    ):
        raise DirectionError("Near-zero threshold must be finite and positive.")
    if not math.isfinite(norm):
        raise DirectionError("Direction norm overflowed.")
    if norm <= threshold:
        raise DirectionError("Direction is zero or below the near-zero threshold.")
    return tuple(value / norm for value in vector)


def standardized_to_raw(
    standardized_coefficients: Sequence[float],
    scaler_scale: Sequence[float],
) -> tuple[float, ...]:
    """Convert `w_z` to raw coordinates as `w_raw = w_z / scale`."""

    coefficients = _finite_vector(
        "standardized_coefficients", standardized_coefficients
    )
    scale = _finite_vector("scaler_scale", scaler_scale)
    if len(coefficients) != len(scale):
        raise DirectionError("Coefficient and scaler dimensions differ.")
    if any(value <= 0.0 for value in scale):
        raise DirectionError("Scaler values must be strictly positive.")
    return tuple(value / divisor for value, divisor in zip(coefficients, scale))


def angle_degrees(left: Sequence[float], right: Sequence[float]) -> float:
    left_unit = normalize(left)
    right_unit = normalize(right)
    cosine = max(-1.0, min(1.0, dot(left_unit, right_unit)))
    return math.degrees(math.acos(cosine))


@dataclass(frozen=True)
class OrthogonalDirection:
    raw_mean_direction: tuple[float, ...]
    raw_time_direction: tuple[float, ...]
    unit_mean_before_projection: tuple[float, ...]
    unit_time_direction: tuple[float, ...]
    unit_residual_direction: tuple[float, ...]
    projection_coefficient: float
    residual_norm_before_normalization: float
    near_zero_threshold: float
    pre_projection_angle_degrees: float
    post_projection_angle_degrees: float


def derive_time_orthogonal_direction(
    mean_standardized_coefficients: Sequence[float],
    mean_scaler_scale: Sequence[float],
    time_standardized_coefficients: Sequence[float],
    time_scaler_scale: Sequence[float],
    *,
    near_zero_threshold: float = 1e-12,
) -> OrthogonalDirection:
    """Raw-convert, normalize, subtract time overlap, and renormalize."""

    raw_mean = standardized_to_raw(
        mean_standardized_coefficients, mean_scaler_scale
    )
    raw_time = standardized_to_raw(
        time_standardized_coefficients, time_scaler_scale
    )
    if len(raw_mean) != len(raw_time):
        raise DirectionError("Mean and elapsed-time directions differ in dimension.")
    unit_mean = normalize(raw_mean, threshold=near_zero_threshold)
    unit_time = normalize(raw_time, threshold=near_zero_threshold)
    projection = dot(unit_mean, unit_time)
    residual = tuple(
        mean_value - projection * time_value
        for mean_value, time_value in zip(unit_mean, unit_time)
    )
    residual_norm = l2_norm(residual)
    unit_residual = normalize(residual, threshold=near_zero_threshold)
    return OrthogonalDirection(
        raw_mean_direction=raw_mean,
        raw_time_direction=raw_time,
        unit_mean_before_projection=unit_mean,
        unit_time_direction=unit_time,
        unit_residual_direction=unit_residual,
        projection_coefficient=projection,
        residual_norm_before_normalization=residual_norm,
        near_zero_threshold=near_zero_threshold,
        pre_projection_angle_degrees=angle_degrees(unit_mean, unit_time),
        post_projection_angle_degrees=angle_degrees(unit_residual, unit_time),
    )


def verify_standardized_raw_equivalence(
    features: Sequence[Sequence[float]],
    *,
    standardized_coefficients: Sequence[float],
    standardized_intercept: float,
    scaler_mean: Sequence[float],
    scaler_scale: Sequence[float],
    absolute_tolerance: float = 1e-10,
) -> float:
    """Return maximum prediction error and fail if raw conversion disagrees."""

    coefficients = _finite_vector(
        "standardized_coefficients", standardized_coefficients
    )
    mean = _finite_vector("scaler_mean", scaler_mean)
    scale = _finite_vector("scaler_scale", scaler_scale)
    if (
        isinstance(standardized_intercept, bool)
        or not isinstance(standardized_intercept, (int, float))
        or not math.isfinite(float(standardized_intercept))
    ):
        raise DirectionError("standardized_intercept must be finite numeric data.")
    if (
        isinstance(absolute_tolerance, bool)
        or not isinstance(absolute_tolerance, (int, float))
        or not math.isfinite(float(absolute_tolerance))
        or absolute_tolerance < 0.0
    ):
        raise DirectionError("absolute_tolerance must be finite and non-negative.")
    if not (len(coefficients) == len(mean) == len(scale)):
        raise DirectionError("Coefficient and scaler dimensions differ.")
    raw = standardized_to_raw(coefficients, scale)
    raw_intercept = float(standardized_intercept) - dot(raw, mean)
    maximum_error = 0.0
    if not features:
        raise DirectionError("Equivalence verification requires feature rows.")
    for row in features:
        values = _finite_vector("feature row", row)
        if len(values) != len(raw):
            raise DirectionError("Feature dimension does not match the direction.")
        standardized_prediction = float(standardized_intercept) + sum(
            coefficient * ((value - center) / divisor)
            for coefficient, value, center, divisor in zip(
                coefficients, values, mean, scale
            )
        )
        raw_prediction = raw_intercept + dot(raw, values)
        maximum_error = max(
            maximum_error, abs(standardized_prediction - raw_prediction)
        )
    if maximum_error > absolute_tolerance:
        raise DirectionError(
            "Raw-space predictions do not match the standardized pipeline."
        )
    return maximum_error
