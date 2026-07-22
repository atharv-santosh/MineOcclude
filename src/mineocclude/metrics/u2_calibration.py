"""U2 calibrated-spread metrics with explicit invalid/near-zero auditing."""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from statistics import NormalDist


NEAR_ZERO_SIGMA_BLOCKS = 1e-12


class U2MetricError(ValueError):
    """Raised instead of clipping, taking absolute values, or dropping rows."""

    def __init__(self, message: str, audit: "SpreadAudit | None" = None) -> None:
        super().__init__(message)
        self.audit = audit


@dataclass(frozen=True)
class SpreadAudit:
    row_count: int
    finite_positive_count: int
    nonfinite_indices: tuple[int, ...]
    nonpositive_indices: tuple[int, ...]
    near_zero_indices: tuple[int, ...]

    @property
    def valid(self) -> bool:
        return not self.nonfinite_indices and not self.nonpositive_indices


@dataclass(frozen=True)
class ZDiagnostics:
    sample_count: int
    mean: float
    sample_std: float
    root_mean_square: float
    coverage_1_96: float


@dataclass(frozen=True)
class CalibrationMetrics:
    sample_count: int
    nominal_levels: tuple[float, ...]
    empirical_coverage: tuple[float, ...]
    coverage_gaps: tuple[float, ...]
    expected_calibration_error: float
    z_diagnostics: ZDiagnostics
    spread_audit: SpreadAudit


def audit_spread_predictions(
    sigma_predictions: Sequence[float],
    *,
    near_zero_threshold: float = NEAR_ZERO_SIGMA_BLOCKS,
) -> SpreadAudit:
    if near_zero_threshold <= 0 or not math.isfinite(near_zero_threshold):
        raise U2MetricError("near_zero_threshold must be finite and positive.")
    nonfinite: list[int] = []
    nonpositive: list[int] = []
    near_zero: list[int] = []
    finite_positive = 0
    for index, value in enumerate(sigma_predictions):
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
        ):
            nonfinite.append(index)
            continue
        numeric = float(value)
        if numeric <= 0.0:
            nonpositive.append(index)
            continue
        finite_positive += 1
        if numeric <= near_zero_threshold:
            near_zero.append(index)
    return SpreadAudit(
        row_count=len(sigma_predictions),
        finite_positive_count=finite_positive,
        nonfinite_indices=tuple(nonfinite),
        nonpositive_indices=tuple(nonpositive),
        near_zero_indices=tuple(near_zero),
    )


def reconstruct_sigma(log_sigma_predictions: Sequence[float]) -> tuple[float, ...]:
    result: list[float] = []
    for value in log_sigma_predictions:
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
        ):
            result.append(math.nan)
            continue
        try:
            result.append(math.exp(float(value)))
        except OverflowError:
            result.append(math.inf)
    return tuple(result)


def _finite_aligned(*vectors: Sequence[float]) -> tuple[tuple[float, ...], ...]:
    if not vectors or len({len(vector) for vector in vectors}) != 1:
        raise U2MetricError("Metric vectors must have identical lengths.")
    if not vectors[0]:
        raise U2MetricError("Metric vectors cannot be empty.")
    converted: list[tuple[float, ...]] = []
    for vector in vectors:
        values: list[float] = []
        for value in vector:
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
            ):
                raise U2MetricError("Metric vectors contain non-finite values.")
            values.append(float(value))
        converted.append(tuple(values))
    return tuple(converted)


def calibration_metrics(
    truth: Sequence[float],
    predicted_mean: Sequence[float],
    predicted_sigma: Sequence[float],
    *,
    levels: Sequence[float] = (0.5, 0.8, 0.95),
    near_zero_threshold: float = NEAR_ZERO_SIGMA_BLOCKS,
) -> CalibrationMetrics:
    """Evaluate inclusive central Gaussian intervals and z diagnostics."""

    actual, mean = _finite_aligned(truth, predicted_mean)
    if len(actual) != len(predicted_sigma):
        raise U2MetricError("Truth, mean, and spread counts differ.")
    audit = audit_spread_predictions(
        predicted_sigma, near_zero_threshold=near_zero_threshold
    )
    if not audit.valid:
        raise U2MetricError(
            "Spread predictions contain non-finite or non-positive values; "
            "result refused without clipping or dropping rows.",
            audit,
        )
    sigma = tuple(float(value) for value in predicted_sigma)
    nominal = tuple(float(level) for level in levels)
    if (
        not nominal
        or any(not math.isfinite(level) or not 0.0 < level < 1.0 for level in nominal)
        or len(set(nominal)) != len(nominal)
    ):
        raise U2MetricError("Coverage levels must be unique values in (0, 1).")
    empirical: list[float] = []
    normal = NormalDist()
    for level in nominal:
        multiplier = normal.inv_cdf((1.0 + level) / 2.0)
        covered = sum(
            abs(value - center) <= multiplier * spread
            for value, center, spread in zip(actual, mean, sigma)
        )
        empirical.append(covered / len(actual))
    gaps = tuple(observed - level for observed, level in zip(empirical, nominal))
    z_values = tuple(
        (value - center) / spread
        for value, center, spread in zip(actual, mean, sigma)
    )
    z_mean = sum(z_values) / len(z_values)
    z_sample_std = (
        math.sqrt(
            sum((value - z_mean) ** 2 for value in z_values)
            / (len(z_values) - 1)
        )
        if len(z_values) > 1
        else 0.0
    )
    z = ZDiagnostics(
        sample_count=len(z_values),
        mean=z_mean,
        sample_std=z_sample_std,
        root_mean_square=math.sqrt(sum(value * value for value in z_values) / len(z_values)),
        coverage_1_96=sum(abs(value) <= 1.96 for value in z_values) / len(z_values),
    )
    return CalibrationMetrics(
        sample_count=len(actual),
        nominal_levels=nominal,
        empirical_coverage=tuple(empirical),
        coverage_gaps=gaps,
        expected_calibration_error=sum(abs(value) for value in gaps) / len(gaps),
        z_diagnostics=z,
        spread_audit=audit,
    )


def _residualize(values: Sequence[float], control: Sequence[float]) -> tuple[float, ...]:
    mean_control = sum(control) / len(control)
    mean_value = sum(values) / len(values)
    denominator = sum((item - mean_control) ** 2 for item in control)
    if denominator == 0.0:
        raise U2MetricError("tau must vary for partial correlation.")
    slope = sum(
        (item - mean_control) * (value - mean_value)
        for item, value in zip(control, values)
    ) / denominator
    intercept = mean_value - slope * mean_control
    return tuple(
        value - (intercept + slope * item)
        for value, item in zip(values, control)
    )


def _pearson(left: Sequence[float], right: Sequence[float]) -> float:
    left_mean = sum(left) / len(left)
    right_mean = sum(right) / len(right)
    numerator = sum(
        (a - left_mean) * (b - right_mean) for a, b in zip(left, right)
    )
    left_sum = sum((value - left_mean) ** 2 for value in left)
    right_sum = sum((value - right_mean) ** 2 for value in right)
    denominator = math.sqrt(left_sum * right_sum)
    if denominator == 0.0:
        raise U2MetricError("Partial correlation residuals must vary.")
    return numerator / denominator


def partial_correlation_controlling_tau(
    decoded_spread: Sequence[float],
    oracle_spread: Sequence[float],
    tau_seconds: Sequence[float],
) -> float:
    decoded, oracle, tau = _finite_aligned(
        decoded_spread, oracle_spread, tau_seconds
    )
    return _pearson(_residualize(decoded, tau), _residualize(oracle, tau))


def fixed_tau_q_summary(
    tau_seconds: Sequence[float],
    q_blocks2_per_second: Sequence[float],
    decoded_spread: Sequence[float],
    oracle_spread: Sequence[float],
) -> Mapping[tuple[float, float], Mapping[str, float | int]]:
    tau, q, decoded, oracle = _finite_aligned(
        tau_seconds,
        q_blocks2_per_second,
        decoded_spread,
        oracle_spread,
    )
    grouped: dict[tuple[float, float], list[tuple[float, float]]] = defaultdict(list)
    for values in zip(tau, q, decoded, oracle):
        grouped[(values[0], values[1])].append((values[2], values[3]))
    return {
        key: {
            "count": len(values),
            "decoded_spread_mean": sum(value[0] for value in values) / len(values),
            "oracle_spread_mean": sum(value[1] for value in values) / len(values),
        }
        for key, values in sorted(grouped.items())
    }
