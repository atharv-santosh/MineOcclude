"""Frozen P8 metric, selection, and aggregation helpers.

The functions in this module are outcome-agnostic.  They encode the prospective
trajectory/layout macro rules used by the P8 runner and never choose execution
parameters from scientific results.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np


class P8CoreError(ValueError):
    """Raised when a P8 metric or selection request violates its contract."""


def canonical_sha256(value: Any) -> str:
    """Hash a JSON-compatible value with one canonical serialization."""

    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _finite_vector(values: Sequence[float], name: str) -> np.ndarray:
    result = np.asarray(values, dtype=np.float64)
    if result.ndim != 1 or result.size == 0 or not np.isfinite(result).all():
        raise P8CoreError(f"{name} must be a non-empty finite vector")
    return result


def trajectory_metrics(
    actual_values: Sequence[float], prediction_values: Sequence[float]
) -> dict[str, float | None | bool]:
    """Compute the frozen within-trajectory metrics."""

    actual = _finite_vector(actual_values, "actual values")
    prediction = _finite_vector(prediction_values, "prediction values")
    if actual.shape != prediction.shape:
        raise P8CoreError("actual and prediction rows do not align")
    residual = actual - prediction
    centered_actual = actual - actual.mean()
    total = float(centered_actual @ centered_actual)
    r2 = None if total == 0.0 else float(1.0 - (residual @ residual) / total)
    mae = float(np.mean(np.abs(residual)))
    target_std = float(actual.std(ddof=0))
    nmae_std = None if target_std == 0.0 else float(mae / target_std)
    prediction_std = float(prediction.std(ddof=0))
    if target_std == 0.0 or prediction_std == 0.0:
        pearson = None
    else:
        pearson = float(np.corrcoef(actual, prediction)[0, 1])
    slope = None if total == 0.0 else float(centered_actual @ prediction / total)
    return {
        "bias": float(np.mean(prediction - actual)),
        "mae": mae,
        "nmae_std": nmae_std,
        "pearson_r": pearson,
        "pearson_undefined": pearson is None,
        "prediction_slope": slope,
        "r2": r2,
        "row_count": int(actual.size),
        "target_std_ddof0": target_std,
    }


def _mean_optional(values: Sequence[float | None]) -> float | None:
    finite = [float(value) for value in values if value is not None]
    return None if not finite else float(np.mean(finite))


def metric_document(
    actual: Sequence[float],
    predictions: Sequence[float],
    trajectory_ids: Sequence[str],
    layout_by_trajectory: Mapping[str, str],
    *,
    frames_per_trajectory: int = 60,
) -> dict[str, Any]:
    """Build per-trajectory, per-layout, and equal-layout macro metrics."""

    actual_array = _finite_vector(actual, "actual values")
    prediction_array = _finite_vector(predictions, "prediction values")
    identities = tuple(str(value) for value in trajectory_ids)
    if actual_array.shape != prediction_array.shape:
        raise P8CoreError("metric rows do not align")
    if actual_array.size != len(identities) * frames_per_trajectory:
        raise P8CoreError("metric rows do not match whole trajectory identities")
    by_trajectory: dict[str, dict[str, Any]] = {}
    by_layout: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for ordinal, identity in enumerate(identities):
        start = ordinal * frames_per_trajectory
        stop = start + frames_per_trajectory
        record = trajectory_metrics(
            actual_array[start:stop], prediction_array[start:stop]
        )
        record = {
            **record,
            "layout": str(layout_by_trajectory[identity]),
            "trajectory_spec_id": identity,
        }
        by_trajectory[identity] = record
        by_layout[record["layout"]].append(record)
    metric_names = (
        "r2",
        "mae",
        "nmae_std",
        "pearson_r",
        "prediction_slope",
        "bias",
    )
    layout_records = {
        layout: {
            "trajectory_count": len(records),
            **{
                metric: _mean_optional([record[metric] for record in records])
                for metric in metric_names
            },
        }
        for layout, records in sorted(by_layout.items())
    }
    macro = {
        metric: _mean_optional([record[metric] for record in layout_records.values()])
        for metric in metric_names
    }
    if macro["r2"] is None or not math.isfinite(macro["r2"]):
        raise P8CoreError("primary macro R2 is undefined or non-finite")
    return {
        "equal_layout_macro": macro,
        "layout_count": len(layout_records),
        "per_layout": layout_records,
        "per_trajectory": by_trajectory,
        "trajectory_count": len(identities),
    }


def selection_score(
    actual: Sequence[float],
    predictions: Sequence[float],
    trajectory_ids: Sequence[str],
    layout_by_trajectory: Mapping[str, str],
) -> float:
    """Return the frozen equal-layout macro validation R2."""

    document = metric_document(
        actual, predictions, trajectory_ids, layout_by_trajectory
    )
    return float(document["equal_layout_macro"]["r2"])


def select_alpha(
    score_by_alpha: Mapping[float, float],
    *,
    tie_tolerance: float = 0.0,
    prefer: str = "smaller",
) -> float:
    """Select the highest-scoring alpha with a frozen numeric tie rule."""

    if prefer not in {"smaller", "larger"}:
        raise P8CoreError("alpha tie preference must be smaller or larger")
    records = [(float(alpha), float(score)) for alpha, score in score_by_alpha.items()]
    if not records or any(not math.isfinite(score) for _, score in records):
        raise P8CoreError("alpha scores must be non-empty and finite")
    maximum = max(score for _, score in records)
    tied = [alpha for alpha, score in records if maximum - score <= tie_tolerance]
    return min(tied) if prefer == "smaller" else max(tied)


def rank_tokens(
    score_records: Sequence[Mapping[str, Any]],
) -> tuple[int, ...]:
    """Rank tokens by median R2, mean R2, then lower token index."""

    if len(score_records) != 336:
        raise P8CoreError("a complete visual-token ranking requires 336 records")
    tokens = [int(record["token_index"]) for record in score_records]
    if sorted(tokens) != list(range(336)):
        raise P8CoreError("token ranking records are incomplete or duplicated")
    return tuple(
        int(record["token_index"])
        for record in sorted(
            score_records,
            key=lambda record: (
                -float(record["median_trajectory_r2"]),
                -float(record["mean_trajectory_r2"]),
                int(record["token_index"]),
            ),
        )
    )


def numeric_summary(values: Sequence[float]) -> dict[str, float | int]:
    """Return the frozen compact descriptive summary."""

    array = _finite_vector(values, "summary values")
    q25, q75 = np.percentile(array, [25.0, 75.0])
    return {
        "count": int(array.size),
        "iqr": float(q75 - q25),
        "maximum": float(array.max()),
        "mean": float(array.mean()),
        "median": float(np.median(array)),
        "minimum": float(array.min()),
        "sd_ddof1": float(array.std(ddof=1)) if array.size > 1 else 0.0,
    }


def paired_summary(
    values: Sequence[float], *, seed: int, bootstrap_replicates: int = 10_000
) -> dict[str, Any]:
    """Summarize paired deltas with one deterministic descriptive interval."""

    array = _finite_vector(values, "paired deltas")
    generator = np.random.default_rng(seed)
    draws = generator.choice(
        array, size=(bootstrap_replicates, array.size), replace=True
    ).mean(axis=1)
    lower, upper = np.percentile(draws, [2.5, 97.5])
    return {
        **numeric_summary(array),
        "descriptive_mean_bootstrap_95_interval": [float(lower), float(upper)],
        "win_count": int(np.sum(array > 0.0)),
        "win_rate": float(np.mean(array > 0.0)),
    }


def distribution(values: Sequence[Any]) -> dict[str, int]:
    """Return a stable string-keyed count distribution."""

    return {
        str(key): int(value)
        for key, value in sorted(Counter(values).items(), key=lambda item: str(item[0]))
    }
