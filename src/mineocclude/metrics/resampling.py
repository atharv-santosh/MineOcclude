"""Trajectory-preserving permutation and hierarchical bootstrap foundations."""

from __future__ import annotations

import math
import random
from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Any


class ResamplingError(ValueError):
    """Raised when a resample would break the declared sampling unit."""


def _validate_seed(seed: int) -> None:
    if not isinstance(seed, int) or isinstance(seed, bool):
        raise ResamplingError("Resampling seed must be an integer.")


def hierarchical_bootstrap_indices(
    rows: Sequence[Mapping[str, Any]],
    *,
    resample_count: int,
    seed: int,
) -> tuple[tuple[int, ...], ...]:
    """Sample layouts, then trajectories, retaining all frames in each draw."""

    if (
        not isinstance(resample_count, int)
        or isinstance(resample_count, bool)
        or resample_count <= 0
    ):
        raise ResamplingError("resample_count must be a positive integer.")
    _validate_seed(seed)
    hierarchy: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(list))
    trajectory_layout: dict[str, str] = {}
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise ResamplingError("Bootstrap rows must be mappings.")
        layout = row.get("layout_id")
        trajectory = row.get("trajectory_id")
        if (
            not isinstance(layout, str)
            or not layout
            or not isinstance(trajectory, str)
            or not trajectory
        ):
            raise ResamplingError("Every row needs layout_id and trajectory_id.")
        previous = trajectory_layout.setdefault(trajectory, layout)
        if previous != layout:
            raise ResamplingError("A trajectory cannot appear in multiple layouts.")
        hierarchy[layout][trajectory].append(index)
    layouts = sorted(hierarchy)
    if not layouts:
        raise ResamplingError("Bootstrap input cannot be empty.")
    rng = random.Random(seed)
    results: list[tuple[int, ...]] = []
    for _ in range(resample_count):
        replicate: list[int] = []
        for sampled_layout in rng.choices(layouts, k=len(layouts)):
            trajectories = sorted(hierarchy[sampled_layout])
            for sampled_trajectory in rng.choices(
                trajectories, k=len(trajectories)
            ):
                replicate.extend(hierarchy[sampled_layout][sampled_trajectory])
        results.append(tuple(replicate))
    return tuple(results)


def permute_trajectory_blocks(
    trajectory_ids: Sequence[str],
    values: Sequence[float],
    *,
    seed: int,
) -> tuple[float, ...]:
    """Shuffle whole equal-length trajectories without rearranging frames."""

    if len(trajectory_ids) != len(values) or not values:
        raise ResamplingError("Trajectory IDs and values must align.")
    _validate_seed(seed)
    grouped: dict[str, list[int]] = defaultdict(list)
    for index, trajectory_id in enumerate(trajectory_ids):
        if not isinstance(trajectory_id, str) or not trajectory_id:
            raise ResamplingError("trajectory_id must be non-empty.")
        value = values[index]
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
        ):
            raise ResamplingError("Permutation values must be finite numeric data.")
        grouped[trajectory_id].append(index)
    by_length: dict[int, list[str]] = defaultdict(list)
    for trajectory_id, indices in grouped.items():
        by_length[len(indices)].append(trajectory_id)
    rng = random.Random(seed)
    result = [math.nan] * len(values)
    for trajectory_length, recipients in sorted(by_length.items()):
        recipients = sorted(recipients)
        if len(recipients) < 2:
            raise ResamplingError(
                "Every trajectory-length stratum needs at least two blocks to permute."
            )
        donors = list(recipients)
        rng.shuffle(donors)
        for recipient, donor in zip(recipients, donors):
            recipient_indices = grouped[recipient]
            donor_indices = grouped[donor]
            if len(recipient_indices) != trajectory_length:
                raise ResamplingError("Internal trajectory-length mismatch.")
            for recipient_index, donor_index in zip(recipient_indices, donor_indices):
                result[recipient_index] = float(values[donor_index])
    if any(not math.isfinite(value) for value in result):
        raise ResamplingError("Permutation did not populate every row.")
    return tuple(result)


def permutation_p_value(
    observed_statistic: float,
    null_statistics: Sequence[float],
) -> float:
    """Return the predeclared add-one, greater-or-equal permutation p-value."""

    if (
        isinstance(observed_statistic, bool)
        or not isinstance(observed_statistic, (int, float))
        or not math.isfinite(float(observed_statistic))
        or not null_statistics
    ):
        raise ResamplingError("Permutation statistics must be finite and non-empty.")
    if any(
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        for value in null_statistics
    ):
        raise ResamplingError("Null statistics must be finite.")
    null = [float(value) for value in null_statistics]
    extreme = sum(value >= float(observed_statistic) for value in null)
    return (extreme + 1.0) / (len(null) + 1.0)


def bootstrap_confidence_interval(
    statistics: Sequence[float],
    *,
    coverage: float = 0.95,
) -> tuple[float, float]:
    """Return a deterministic equal-tailed interval with linear quantiles."""

    if not statistics:
        raise ResamplingError("Bootstrap statistics cannot be empty.")
    if not math.isfinite(coverage) or not 0.0 < coverage < 1.0:
        raise ResamplingError("coverage must be in (0, 1).")
    values = sorted(float(value) for value in statistics)
    if any(not math.isfinite(value) for value in values):
        raise ResamplingError("Bootstrap statistics must be finite.")

    def quantile(probability: float) -> float:
        position = probability * (len(values) - 1)
        lower = math.floor(position)
        upper = math.ceil(position)
        if lower == upper:
            return values[lower]
        fraction = position - lower
        return values[lower] * (1.0 - fraction) + values[upper] * fraction

    tail = (1.0 - coverage) / 2.0
    return quantile(tail), quantile(1.0 - tail)
