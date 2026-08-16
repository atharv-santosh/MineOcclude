"""Authority-neutral measurement of physical calibration support."""

from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Real
from typing import Sequence

__all__ = [
    "SupportWindow",
    "SupportRequirements",
    "SupportCoverage",
    "wall_relative",
    "evaluate_support",
]


def _finite_plain_number(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{name} must be a real number, not {type(value).__name__}")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


@dataclass(frozen=True)
class SupportWindow:
    """A caller-requested closed interval of a named physical coordinate."""

    coordinate: str
    minimum: float
    maximum: float
    scene: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.coordinate, str) or not self.coordinate.strip():
            raise ValueError("coordinate must be named")
        minimum = _finite_plain_number(self.minimum, "minimum")
        maximum = _finite_plain_number(self.maximum, "maximum")
        if minimum >= maximum:
            raise ValueError("minimum must be strictly less than maximum")
        object.__setattr__(self, "minimum", minimum)
        object.__setattr__(self, "maximum", maximum)

    @property
    def span(self) -> float:
        return self.maximum - self.minimum

    def contains(self, value: float) -> bool:
        return self.minimum <= value <= self.maximum


@dataclass(frozen=True)
class SupportRequirements:
    """Authority/configuration-supplied acceptance requirements.

    No values default: internal-gap width, endpoint tolerance, and minimum
    support count are scientific/design choices, not infrastructure constants.
    """

    maximum_gap: float
    endpoint_tolerance: float
    minimum_samples: int

    def __post_init__(self) -> None:
        maximum_gap = _finite_plain_number(self.maximum_gap, "maximum_gap")
        endpoint_tolerance = _finite_plain_number(
            self.endpoint_tolerance, "endpoint_tolerance"
        )
        if maximum_gap < 0 or endpoint_tolerance < 0:
            raise ValueError("gap and endpoint tolerances must be non-negative")
        if (
            not isinstance(self.minimum_samples, int)
            or isinstance(self.minimum_samples, bool)
            or self.minimum_samples < 1
        ):
            raise ValueError("minimum_samples must be a positive plain int")
        object.__setattr__(self, "maximum_gap", maximum_gap)
        object.__setattr__(self, "endpoint_tolerance", endpoint_tolerance)


@dataclass
class SupportCoverage:
    window: SupportWindow
    sample_count: int
    inside: int
    outside: int
    observed_min: float | None
    observed_max: float | None
    coverage_intervals: list[tuple[float, float]]
    largest_gap: float | None
    uncovered_low: float
    uncovered_high: float
    non_finite_count: int
    malformed_count: int
    requirements: SupportRequirements | None
    acceptance: bool | None
    reasons: list[str]

    @property
    def total(self) -> int:
        return self.sample_count + self.non_finite_count + self.malformed_count

    @property
    def total_valid_samples(self) -> int:
        """All finite, well-typed observations, inside and outside the window."""
        return self.sample_count

    @property
    def in_support_samples(self) -> int:
        """Finite, well-typed observations inside the requested support."""
        return self.inside

    @property
    def valid(self) -> bool:
        return (
            self.sample_count > 0
            and self.non_finite_count == 0
            and self.malformed_count == 0
        )

    @property
    def fully_covered(self) -> bool | None:
        """Compatibility name for an explicit, policy-backed adjudication."""
        return self.acceptance

    def to_dict(self) -> dict:
        return {
            "artifact_id": "prospective-calibration-support-coverage-v0.2",
            "coordinate": self.window.coordinate,
            "scene": self.window.scene,
            "requested_physical_support": [self.window.minimum, self.window.maximum],
            "window_span": self.window.span,
            "sample_count": self.sample_count,
            "total_valid_samples": self.total_valid_samples,
            "in_support_samples": self.in_support_samples,
            "samples_inside": self.inside,
            "samples_outside": self.outside,
            "observed_min": self.observed_min,
            "observed_max": self.observed_max,
            "coverage_intervals": [list(interval) for interval in self.coverage_intervals],
            "largest_gap": self.largest_gap,
            "uncovered_span_low": self.uncovered_low,
            "uncovered_span_high": self.uncovered_high,
            "non_finite_count": self.non_finite_count,
            "malformed_count": self.malformed_count,
            "input_valid": self.valid,
            "requirements": None
            if self.requirements is None
            else {
                "maximum_gap": self.requirements.maximum_gap,
                "endpoint_tolerance": self.requirements.endpoint_tolerance,
                "minimum_samples": self.requirements.minimum_samples,
            },
            "fully_covered": self.acceptance,
            "adjudication": (
                "INVALID"
                if not self.valid
                else "UNADJUDICATED"
                if self.requirements is None
                else "PASS"
                if self.acceptance
                else "FAIL"
            ),
            "reasons": self.reasons,
            "contains_no_embedded_scientific_requirements": True,
        }


def wall_relative(world_x: float, wall_reference_x: float) -> float:
    return _finite_plain_number(world_x, "world_x") - _finite_plain_number(
        wall_reference_x, "wall_reference_x"
    )


def evaluate_support(
    values: Sequence[float],
    window: SupportWindow,
    *,
    requirements: SupportRequirements | None = None,
) -> SupportCoverage:
    """Measure coverage and optionally apply only caller-supplied requirements."""
    numeric: list[float] = []
    non_finite = 0
    malformed = 0
    for value in values:
        if isinstance(value, bool) or not isinstance(value, Real):
            malformed += 1
            continue
        converted = float(value)
        if not math.isfinite(converted):
            non_finite += 1
            continue
        numeric.append(converted)

    ordered = sorted(set(value for value in numeric if window.contains(value)))
    observed_min = min(numeric) if numeric else None
    observed_max = max(numeric) if numeric else None
    uncovered_low = (
        max(0.0, ordered[0] - window.minimum)
        if ordered
        else window.span
    )
    uncovered_high = (
        max(0.0, window.maximum - ordered[-1])
        if ordered
        else window.span
    )
    largest_gap = (
        max((right - left for left, right in zip(ordered, ordered[1:])), default=0.0)
        if ordered
        else None
    )

    intervals: list[tuple[float, float]] = []
    if ordered:
        if requirements is None:
            intervals = [(value, value) for value in ordered]
        else:
            start = previous = ordered[0]
            for value in ordered[1:]:
                if value - previous > requirements.maximum_gap:
                    intervals.append((start, previous))
                    start = value
                previous = value
            intervals.append((start, previous))

    reasons: list[str] = []
    valid = bool(numeric) and non_finite == 0 and malformed == 0
    if not numeric:
        reasons.append("no finite coordinate observations")
    if non_finite:
        reasons.append(f"{non_finite} non-finite coordinate observations")
    if malformed:
        reasons.append(f"{malformed} malformed coordinate observations")

    acceptance: bool | None
    if not valid:
        acceptance = False
    elif requirements is None:
        acceptance = None
        reasons.append("support requirements were not supplied")
    else:
        in_support_count = sum(1 for value in numeric if window.contains(value))
        if in_support_count < requirements.minimum_samples:
            reasons.append(
                "in-support sample count is below the caller-supplied minimum"
            )
        covered_min = ordered[0] if ordered else None
        covered_max = ordered[-1] if ordered else None
        if covered_min is None or covered_min > window.minimum + requirements.endpoint_tolerance:
            reasons.append("requested lower endpoint is not covered")
        if covered_max is None or covered_max < window.maximum - requirements.endpoint_tolerance:
            reasons.append("requested upper endpoint is not covered")
        if largest_gap is None or largest_gap > requirements.maximum_gap:
            reasons.append("largest internal gap exceeds the caller-supplied maximum")
        acceptance = not reasons

    return SupportCoverage(
        window=window,
        sample_count=len(numeric),
        inside=sum(1 for value in numeric if window.contains(value)),
        outside=sum(1 for value in numeric if not window.contains(value)),
        observed_min=observed_min,
        observed_max=observed_max,
        coverage_intervals=intervals,
        largest_gap=largest_gap,
        uncovered_low=uncovered_low,
        uncovered_high=uncovered_high,
        non_finite_count=non_finite,
        malformed_count=malformed,
        requirements=requirements,
        acceptance=acceptance,
        reasons=reasons,
    )
