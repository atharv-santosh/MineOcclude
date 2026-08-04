"""U1 posterior-mean decoding metrics with exact-duration bins."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass


class U1MetricError(ValueError):
    """Raised when a U1 metric would be undefined or misleading."""


def _finite_vector(name: str, values: Sequence[float]) -> tuple[float, ...]:
    result: list[float] = []
    for value in values:
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
        ):
            raise U1MetricError(f"{name} must contain only finite numbers.")
        result.append(float(value))
    if not result:
        raise U1MetricError(f"{name} cannot be empty.")
    return tuple(result)


@dataclass(frozen=True)
class RegressionMetrics:
    sample_count: int
    r2: float
    mae: float
    mse: float


def regression_metrics(
    truth: Sequence[float], predictions: Sequence[float]
) -> RegressionMetrics:
    """Compute R-squared, MAE, and MSE without dropping invalid rows."""

    actual = _finite_vector("truth", truth)
    predicted = _finite_vector("predictions", predictions)
    if len(actual) != len(predicted):
        raise U1MetricError("Truth and prediction counts differ.")
    mean_actual = sum(actual) / len(actual)
    residual_sum = sum((left - right) ** 2 for left, right in zip(actual, predicted))
    total_sum = sum((value - mean_actual) ** 2 for value in actual)
    if total_sum == 0.0:
        raise U1MetricError("R-squared is undefined for constant truth.")
    return RegressionMetrics(
        sample_count=len(actual),
        r2=1.0 - residual_sum / total_sum,
        mae=sum(abs(left - right) for left, right in zip(actual, predicted))
        / len(actual),
        mse=residual_sum / len(actual),
    )


def duration_binned_metrics(
    durations_seconds: Sequence[float],
    truth: Sequence[float],
    predictions: Sequence[float],
) -> Mapping[float, RegressionMetrics]:
    """Report one bin per exact predeclared duration in seconds."""

    durations = _finite_vector("durations_seconds", durations_seconds)
    actual = _finite_vector("truth", truth)
    predicted = _finite_vector("predictions", predictions)
    if not (len(durations) == len(actual) == len(predicted)):
        raise U1MetricError("Duration, truth, and prediction counts differ.")
    result: dict[float, RegressionMetrics] = {}
    for duration in sorted(set(durations)):
        indices = [index for index, value in enumerate(durations) if value == duration]
        result[duration] = regression_metrics(
            [actual[index] for index in indices],
            [predicted[index] for index in indices],
        )
    return result


def baseline_delta_r2(
    truth: Sequence[float],
    probe_predictions: Sequence[float],
    baseline_predictions: Sequence[float],
) -> float:
    """Return probe R-squared minus baseline R-squared on identical rows."""

    probe = regression_metrics(truth, probe_predictions)
    baseline = regression_metrics(truth, baseline_predictions)
    if probe.sample_count != baseline.sample_count:
        raise U1MetricError("Probe and baseline comparisons must use identical rows.")
    return probe.r2 - baseline.r2
