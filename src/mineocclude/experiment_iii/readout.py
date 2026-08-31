"""Grouped nested ridge readout (authority 8.8).

Primary cell, frozen: ``layer 19 | COARSE_2X6_CONCAT | CURRENT | ridge``.

    alpha grid        {0.1, 1, 10, 100, 1000} - FIVE values
    intercept         unpenalized
    standardization   training-only
    outer folds       5 frozen identity folds
    inner rotations   4, inside each outer training set only
    alpha selection   identity-macro inner-validation mean RMSE
    tie-break         smallest alpha
    held-out tuning   forbidden

``probes/ridge.py:192-223 fit_ridge`` already implements the unpenalized
intercept, training-only standardization and the dual solve, and is reused
unchanged. The legacy four-value ``ALPHAS`` tuple at
``regime_a_first25_analysis.py:17`` is NOT reused: Experiment III requires five.

The grouping unit is the trajectory identity throughout. No identity ever appears
in its own training set, and no held-out target influences any fitted quantity.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

import numpy as np

from mineocclude.experiment_iii.errors import ExperimentIIIError
from mineocclude.probes.ridge import fit_ridge, fit_standard_scaler

__all__ = [
    "ALPHA_GRID",
    "LEGACY_ALPHA_GRID_NOT_REUSED",
    "FoldData",
    "AlphaSelection",
    "identity_macro_rmse",
    "select_alpha",
    "fit_outer_fold",
    "cross_validated_predictions",
]

#: Authority 8.8 — five values, ascending. The tie-break is the smallest alpha,
#: so the ascending order is load-bearing.
ALPHA_GRID = (0.1, 1.0, 10.0, 100.0, 1000.0)

#: Present only so a test can assert the legacy grid is not what we use.
LEGACY_ALPHA_GRID_NOT_REUSED = (0.1, 1.0, 10.0, 100.0)


@dataclass(frozen=True)
class FoldData:
    """Features and targets for one identity, in frozen row order."""

    identity: str
    features: np.ndarray
    targets: np.ndarray

    def __post_init__(self) -> None:
        if self.features.ndim != 2 or self.targets.ndim != 1:
            raise ExperimentIIIError(
                "FEATURE_DIMENSION_MISMATCH",
                f"{self.identity}: features must be 2-D and targets 1-D",
            )
        if self.features.shape[0] != self.targets.shape[0]:
            raise ExperimentIIIError(
                "FEATURE_ROW_ORDER_MISMATCH",
                f"{self.identity}: {self.features.shape[0]} feature rows vs "
                f"{self.targets.shape[0]} targets",
            )


@dataclass(frozen=True)
class AlphaSelection:
    """Which alpha won, and the identity-macro score behind every candidate."""

    alpha: float
    scores: dict[float, float]
    rotations: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "selected_alpha": self.alpha,
            "alpha_grid": list(ALPHA_GRID),
            "inner_scores_identity_macro_rmse": {
                str(alpha): score for alpha, score in sorted(self.scores.items())
            },
            "inner_rotations": self.rotations,
            "tie_break": "SMALLEST_ALPHA",
            "criterion": "IDENTITY_MACRO_INNER_VALIDATION_MEAN_RMSE",
        }


def _rmse(observed: Sequence[float], predicted: Sequence[float]) -> float:
    a = np.asarray(observed, dtype=np.float64)
    b = np.asarray(predicted, dtype=np.float64)
    return float(np.sqrt(np.mean((a - b) ** 2)))


def identity_macro_rmse(per_identity: Mapping[str, float]) -> float:
    """Mean over identities of that identity's RMSE.

    Identity-macro, never pooled over rows: pooling would weight identities by
    row count and is pseudo-replication.
    """
    if not per_identity:
        raise ExperimentIIIError(
            "STATS_ZERO_TSS", "identity-macro score needs at least one identity"
        )
    return float(np.mean([float(value) for value in per_identity.values()]))


def _stack(entries: Sequence[FoldData]) -> tuple[np.ndarray, np.ndarray]:
    features = np.concatenate([entry.features for entry in entries], axis=0)
    targets = np.concatenate([entry.targets for entry in entries], axis=0)
    return features, targets


def select_alpha(
    training: Mapping[str, FoldData],
    inner_rotations: Mapping[int, Sequence[str]],
    *,
    alpha_grid: Sequence[float] = ALPHA_GRID,
) -> AlphaSelection:
    """Choose alpha inside the outer TRAINING set only.

    Every fit, scaler and score here sees only training identities; the held-out
    identities of the outer fold are not passed in at all.
    """
    if len(alpha_grid) != 5:
        raise ExperimentIIIError(
            "ANALYSIS_FAMILY_ALTERED",
            f"the alpha grid must hold five values, got {len(alpha_grid)}",
        )
    scores: dict[float, float] = {}
    for alpha in alpha_grid:
        per_rotation: list[float] = []
        for rotation, validation_ids in sorted(inner_rotations.items()):
            fit_ids = [name for name in training if name not in set(validation_ids)]
            if not fit_ids or not validation_ids:
                raise ExperimentIIIError(
                    "FOLD_LEAKAGE_DETECTED",
                    f"inner rotation {rotation} has an empty side",
                )
            features, targets = _stack([training[name] for name in fit_ids])
            scaler = fit_standard_scaler(features)
            model = fit_ridge(features, targets, alpha=float(alpha), scaler=scaler)
            per_identity = {
                name: _rmse(
                    training[name].targets, model.predict(training[name].features)
                )
                for name in validation_ids
            }
            per_rotation.append(identity_macro_rmse(per_identity))
        scores[float(alpha)] = float(np.mean(per_rotation))

    best = min(scores.values())
    # Smallest alpha wins a tie; ALPHA_GRID is ascending, so the first match is it.
    selected = next(
        float(alpha) for alpha in alpha_grid if scores[float(alpha)] == best
    )
    return AlphaSelection(
        alpha=selected, scores=scores, rotations=len(inner_rotations)
    )


def fit_outer_fold(
    training: Mapping[str, FoldData],
    held_out: Mapping[str, FoldData],
    inner_rotations: Mapping[int, Sequence[str]],
    *,
    alpha_grid: Sequence[float] = ALPHA_GRID,
) -> tuple[dict[str, np.ndarray], AlphaSelection]:
    """Fit on the outer training set and predict every held-out identity once."""
    leaked = set(training) & set(held_out)
    if leaked:
        raise ExperimentIIIError(
            "FOLD_LEAKAGE_DETECTED",
            f"identities appear in both training and held-out sets: {sorted(leaked)}",
        )
    for rotation, members in inner_rotations.items():
        escaped = set(members) - set(training)
        if escaped:
            raise ExperimentIIIError(
                "FOLD_LEAKAGE_DETECTED",
                f"inner rotation {rotation} contains non-training identities: "
                f"{sorted(escaped)}",
            )
    selection = select_alpha(training, inner_rotations, alpha_grid=alpha_grid)
    features, targets = _stack(list(training.values()))
    scaler = fit_standard_scaler(features)
    model = fit_ridge(features, targets, alpha=selection.alpha, scaler=scaler)
    predictions = {
        name: np.asarray(model.predict(entry.features), dtype=np.float64)
        for name, entry in held_out.items()
    }
    for name, predicted in predictions.items():
        if not np.isfinite(predicted).all():
            raise ExperimentIIIError(
                "PREDICTION_NONFINITE", f"{name} produced a non-finite prediction"
            )
    return predictions, selection


def cross_validated_predictions(
    data: Mapping[str, FoldData],
    folds: Sequence[Mapping[str, Any]],
    *,
    alpha_grid: Sequence[float] = ALPHA_GRID,
) -> tuple[dict[str, np.ndarray], dict[int, AlphaSelection]]:
    """One held-out prediction per identity, across the five outer folds."""
    predictions: dict[str, np.ndarray] = {}
    selections: dict[int, AlphaSelection] = {}
    for fold in folds:
        outer = int(fold["outer_fold"])
        held_ids = [name for name in fold["held_out_identities"] if name in data]
        train_ids = [name for name in fold["training_identities"] if name in data]
        rotations = {
            int(rotation): [name for name in members if name in data]
            for rotation, members in fold["inner_rotations"].items()
        }
        fold_predictions, selection = fit_outer_fold(
            {name: data[name] for name in train_ids},
            {name: data[name] for name in held_ids},
            rotations,
            alpha_grid=alpha_grid,
        )
        duplicates = set(fold_predictions) & set(predictions)
        if duplicates:
            raise ExperimentIIIError(
                "PREDICTION_DUPLICATE_CELL",
                f"identities predicted more than once: {sorted(duplicates)}",
            )
        predictions.update(fold_predictions)
        selections[outer] = selection
    missing = set(data) - set(predictions)
    if missing:
        raise ExperimentIIIError(
            "PREDICTION_LOCK_MISSING",
            f"identities never held out: {sorted(missing)}",
        )
    return predictions, selections
