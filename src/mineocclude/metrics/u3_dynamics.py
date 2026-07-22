"""U3 hidden-time growth and reveal-snapback metrics."""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass


class U3MetricError(ValueError):
    """Raised when grouped dynamics cannot be estimated without repair."""


def _slope(x: Sequence[float], y: Sequence[float]) -> float:
    if len(x) != len(y) or len(x) < 2:
        raise U3MetricError("A slope requires at least two aligned values.")
    if any(not math.isfinite(float(value)) for value in (*x, *y)):
        raise U3MetricError("Slope inputs must be finite.")
    mean_x = sum(x) / len(x)
    mean_y = sum(y) / len(y)
    denominator = sum((value - mean_x) ** 2 for value in x)
    if denominator == 0.0:
        raise U3MetricError("Slope time values must vary.")
    return sum(
        (left - mean_x) * (right - mean_y) for left, right in zip(x, y)
    ) / denominator


def trajectory_growth_slopes(
    trajectory_ids: Sequence[str],
    tau_seconds: Sequence[float],
    spread_blocks: Sequence[float],
    visibility_states: Sequence[str],
) -> Mapping[str, float]:
    """Estimate one hidden-time slope per trajectory, never per pooled frame."""

    if not (
        len(trajectory_ids)
        == len(tau_seconds)
        == len(spread_blocks)
        == len(visibility_states)
        and trajectory_ids
    ):
        raise U3MetricError("Trajectory, tau, and spread rows must align.")
    grouped: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for trajectory_id, tau, spread, visibility in zip(
        trajectory_ids, tau_seconds, spread_blocks, visibility_states
    ):
        if not isinstance(trajectory_id, str) or not trajectory_id:
            raise U3MetricError("trajectory_id must be non-empty.")
        if not isinstance(visibility, str) or visibility not in {
            "visible",
            "occluded",
        }:
            raise U3MetricError("visibility must be visible or occluded.")
        if visibility != "occluded":
            continue
        if (
            isinstance(tau, bool)
            or isinstance(spread, bool)
            or not isinstance(tau, (int, float))
            or not isinstance(spread, (int, float))
            or not math.isfinite(float(tau))
            or not math.isfinite(float(spread))
        ):
            raise U3MetricError("Tau and spread must be finite numeric data.")
        grouped[trajectory_id].append((float(tau), float(spread)))
    if not grouped:
        raise U3MetricError("Hidden-time growth requires occluded rows.")
    result: dict[str, float] = {}
    for trajectory_id, values in grouped.items():
        ordered = sorted(values)
        result[trajectory_id] = _slope(
            [value[0] for value in ordered],
            [value[1] for value in ordered],
        )
    return result


def oracle_slope_ratio(
    decoded_slopes: Mapping[str, float], oracle_slopes: Mapping[str, float]
) -> Mapping[str, float]:
    if set(decoded_slopes) != set(oracle_slopes):
        raise U3MetricError("Decoded and oracle slopes require identical trajectories.")
    ratios: dict[str, float] = {}
    for trajectory_id in sorted(decoded_slopes):
        denominator = float(oracle_slopes[trajectory_id])
        numerator = float(decoded_slopes[trajectory_id])
        if not math.isfinite(numerator) or not math.isfinite(denominator):
            raise U3MetricError("Slope ratios require finite values.")
        if denominator == 0.0:
            raise U3MetricError("Oracle slope ratio is undefined at zero oracle slope.")
        ratios[trajectory_id] = numerator / denominator
    return ratios


@dataclass(frozen=True)
class RevealPair:
    event_id: str
    pre_spread: float
    post_spread: float
    difference: float
    reduction_fraction: float


@dataclass(frozen=True)
class RevealSnapback:
    pairs: tuple[RevealPair, ...]
    median_difference: float
    median_reduction_fraction: float


def _median(values: Sequence[float]) -> float:
    ordered = sorted(values)
    midpoint = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[midpoint]
    return (ordered[midpoint - 1] + ordered[midpoint]) / 2.0


def reveal_snapback(
    event_ids: Sequence[str],
    relative_time_seconds: Sequence[float],
    spread_blocks: Sequence[float],
    visibility_states: Sequence[str],
    *,
    window_seconds: tuple[float, float] = (-1.0, 1.0),
) -> RevealSnapback:
    """Pair the nearest valid pre/post-reveal spread within each event."""

    if not (
        len(event_ids)
        == len(relative_time_seconds)
        == len(spread_blocks)
        == len(visibility_states)
        and event_ids
    ):
        raise U3MetricError("Reveal rows must align and cannot be empty.")
    lower, upper = window_seconds
    if not lower < 0.0 <= upper:
        raise U3MetricError("Reveal window must straddle zero.")
    grouped: dict[str, list[tuple[float, float, str]]] = defaultdict(list)
    for event_id, time, spread, visibility in zip(
        event_ids,
        relative_time_seconds,
        spread_blocks,
        visibility_states,
    ):
        if not isinstance(event_id, str) or not event_id:
            raise U3MetricError("event_id must be non-empty.")
        if (
            isinstance(time, bool)
            or isinstance(spread, bool)
            or not isinstance(time, (int, float))
            or not isinstance(spread, (int, float))
            or not math.isfinite(float(time))
            or not math.isfinite(float(spread))
            or float(spread) < 0.0
        ):
            raise U3MetricError("Reveal times/spreads must be finite and nonnegative.")
        if not isinstance(visibility, str) or visibility not in {
            "visible",
            "occluded",
        }:
            raise U3MetricError("Reveal visibility must be visible or occluded.")
        if lower <= float(time) <= upper:
            grouped[event_id].append(
                (float(time), float(spread), visibility)
            )
    pairs: list[RevealPair] = []
    for event_id, values in sorted(grouped.items()):
        pre = [
            value
            for value in values
            if value[0] < 0.0 and value[2] == "occluded"
        ]
        post = [
            value
            for value in values
            if value[0] >= 0.0 and value[2] == "visible"
        ]
        if not pre or not post:
            raise U3MetricError(
                f"Reveal event {event_id!r} lacks a paired pre/post observation."
            )
        pre_spread = max(pre, key=lambda value: value[0])[1]
        post_spread = min(post, key=lambda value: value[0])[1]
        if pre_spread == 0.0:
            raise U3MetricError("Reveal reduction is undefined at zero pre-spread.")
        difference = post_spread - pre_spread
        pairs.append(
            RevealPair(
                event_id,
                pre_spread,
                post_spread,
                difference,
                (pre_spread - post_spread) / pre_spread,
            )
        )
    if not pairs:
        raise U3MetricError("No reveal events were inside the declared window.")
    return RevealSnapback(
        pairs=tuple(pairs),
        median_difference=_median([pair.difference for pair in pairs]),
        median_reduction_fraction=_median(
            [pair.reduction_fraction for pair in pairs]
        ),
    )
