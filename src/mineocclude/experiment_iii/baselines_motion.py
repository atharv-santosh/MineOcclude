"""Motion and clock baselines (authority 8.9.2-8.9.6).

    last-seen          hold the FIR-aligned world-x from the last counterfactual
                       row that was NOT fully occluded
    constant velocity  OLS on (time, position) over the last **10** FIR-aligned
                       pre-occlusion positions, extrapolated to the target tick
    training mean      outer-training mean target
    time-only          outer-training linear model on
                       [1, direction_sign, a, direction_sign * a]

Last-seen and constant-velocity are **oracle-state heuristics, not model inputs**.
They are identical across L0-L4 within an identity and contextualize motion
difficulty; they are not evidence the model had authoritative state, and their
inputs must never enter any model feature
(``BASELINE_ORACLE_USED_AS_MODEL_INPUT``).

The legacy ``constant_velocity_baseline`` (``regime_a.py:456-465``) uses a
15-sample window via ``EFFECTIVE_PRECEDING_STEPS``; Experiment III requires 10 and
does not reuse it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import numpy as np

from mineocclude.experiment_iii.authority import DT_SECONDS, direction_sign
from mineocclude.experiment_iii.errors import ExperimentIIIError

__all__ = [
    "CONSTANT_VELOCITY_WINDOW",
    "LEGACY_CONSTANT_VELOCITY_WINDOW_NOT_REUSED",
    "ORACLE_BASELINES",
    "last_seen",
    "constant_velocity",
    "training_mean",
    "time_only_design",
    "fit_time_only",
    "predict_time_only",
    "assert_no_oracle_input_in_model_features",
]

#: Authority 8.9.3 — exactly ten. Frozen window length and arithmetic.
CONSTANT_VELOCITY_WINDOW = 10
#: Present only so a test can assert the legacy window is not what we use.
LEGACY_CONSTANT_VELOCITY_WINDOW_NOT_REUSED = 15

#: Baselines that read authoritative state. Never model inputs.
ORACLE_BASELINES = frozenset({"last_seen", "constant_velocity"})


def _preocclusion(positions: Sequence[float], occluded: Sequence[bool]) -> list[int]:
    """Indices of counterfactual rows that were NOT fully occluded."""
    if len(positions) != len(occluded):
        raise ExperimentIIIError(
            "BASELINE_FORMULA_MISMATCH",
            "position and occlusion series must be the same length",
        )
    return [index for index, hidden in enumerate(occluded) if not hidden]


def last_seen(
    positions: Sequence[float], occluded: Sequence[bool], target_row: int
) -> float:
    """Hold the FIR-aligned world-x from the last not-fully-occluded row."""
    visible = [index for index in _preocclusion(positions, occluded) if index < target_row]
    if not visible:
        raise ExperimentIIIError(
            "BASELINE_MISSING",
            f"no pre-occlusion row precedes target row {target_row}",
        )
    return float(positions[visible[-1]])


def constant_velocity(
    positions: Sequence[float],
    occluded: Sequence[bool],
    target_row: int,
    *,
    window: int = CONSTANT_VELOCITY_WINDOW,
    dt: float = DT_SECONDS,
) -> float:
    """OLS velocity over the last ``window`` pre-occlusion positions.

    Fits position on time by ordinary least squares and extrapolates to the
    target tick. The window is exactly 10 (not the legacy 15).
    """
    if window != CONSTANT_VELOCITY_WINDOW:
        raise ExperimentIIIError(
            "BASELINE_FORMULA_MISMATCH",
            f"constant-velocity window is frozen at {CONSTANT_VELOCITY_WINDOW}, "
            f"got {window}",
        )
    visible = [index for index in _preocclusion(positions, occluded) if index < target_row]
    if len(visible) < window:
        raise ExperimentIIIError(
            "BASELINE_MISSING",
            f"constant velocity needs {window} pre-occlusion positions, has "
            f"{len(visible)}",
        )
    used = visible[-window:]
    times = np.asarray([index * dt for index in used], dtype=np.float64)
    values = np.asarray([positions[index] for index in used], dtype=np.float64)
    design = np.column_stack([np.ones_like(times), times])
    solution, *_ = np.linalg.lstsq(design, values, rcond=None)
    intercept, slope = float(solution[0]), float(solution[1])
    return intercept + slope * (target_row * dt)


def training_mean(
    training_targets: Mapping[str, Sequence[float]],
    *,
    directions: Mapping[str, str] | None = None,
    stratify_by_direction: bool = False,
) -> float | dict[str, float]:
    """Outer-training mean target.

    Direction stratification is applied ONLY if A1 prospectively confirms the
    stratified mean is estimable in every outer fold; otherwise the unstratified
    outer-training mean is used. The choice is frozen in P2 and never revisited.
    """
    rows = [
        float(value) for values in training_targets.values() for value in values
    ]
    if not rows:
        raise ExperimentIIIError(
            "BASELINE_MISSING", "the outer-training set carries no target rows"
        )
    if not stratify_by_direction:
        return float(np.mean(rows))
    if directions is None:
        raise ExperimentIIIError(
            "BASELINE_FORMULA_MISMATCH",
            "direction stratification needs a direction per identity",
        )
    grouped: dict[str, list[float]] = {}
    for identity, values in training_targets.items():
        grouped.setdefault(directions[identity], []).extend(
            float(value) for value in values
        )
    if len(grouped) != 2 or any(not values for values in grouped.values()):
        raise ExperimentIIIError(
            "BASELINE_MISSING",
            "the stratified mean is not estimable in this fold; the frozen "
            "fallback is the unstratified outer-training mean",
        )
    return {name: float(np.mean(values)) for name, values in grouped.items()}


def time_only_design(context_age: Sequence[int], direction: Sequence[str]) -> np.ndarray:
    """The frozen design ``[1, direction_sign, a, direction_sign * a]``."""
    if len(context_age) != len(direction):
        raise ExperimentIIIError(
            "BASELINE_FORMULA_MISMATCH",
            "context age and direction series must be the same length",
        )
    ages = np.asarray([float(value) for value in context_age], dtype=np.float64)
    signs = np.asarray(
        [direction_sign(value) for value in direction], dtype=np.float64
    )
    design = np.column_stack([np.ones_like(ages), signs, ages, signs * ages])
    if design.shape[1] != 4:
        raise ExperimentIIIError(
            "BASELINE_FORMULA_MISMATCH",
            f"time-only design has {design.shape[1]} columns, expected 4",
        )
    return design


def fit_time_only(
    context_age: Sequence[int],
    direction: Sequence[str],
    targets: Sequence[float],
) -> np.ndarray:
    """Fit on OUTER-TRAINING rows only."""
    design = time_only_design(context_age, direction)
    values = np.asarray([float(value) for value in targets], dtype=np.float64)
    if design.shape[0] != values.shape[0]:
        raise ExperimentIIIError(
            "BASELINE_FORMULA_MISMATCH", "design and target row counts differ"
        )
    solution, *_ = np.linalg.lstsq(design, values, rcond=None)
    return np.asarray(solution, dtype=np.float64)


def predict_time_only(
    coefficients: np.ndarray,
    context_age: Sequence[int],
    direction: Sequence[str],
) -> np.ndarray:
    return time_only_design(context_age, direction) @ np.asarray(
        coefficients, dtype=np.float64
    )


def assert_no_oracle_input_in_model_features(feature_names: Sequence[str]) -> None:
    """Refuse an oracle quantity that has leaked into a model feature block."""
    forbidden = {
        "last_seen",
        "last_seen_world_x",
        "constant_velocity",
        "constant_velocity_prediction",
        "true_world_x",
        "server_position",
        "oracle_position",
        "sheep_x",
    }
    leaked = sorted(set(feature_names) & forbidden)
    if leaked:
        raise ExperimentIIIError(
            "BASELINE_ORACLE_USED_AS_MODEL_INPUT",
            f"oracle-state inputs must never enter a model feature: {leaked}",
        )
