"""Leakage-safe ridge probes and train-only scaler artifacts."""

from __future__ import annotations

import hashlib
import math
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from mineocclude.analysis.manifests import is_hex_digest, seal_artifact


class ProbeFitError(ValueError):
    """Raised when a probe fit is invalid or would leak held-out data."""


def _np() -> Any:
    try:
        import numpy as numpy
    except ImportError as error:  # pragma: no cover - environment gate
        raise ProbeFitError(
            "NumPy must come from the approved MineWorld environment before "
            "probe fitting can run."
        ) from error
    return numpy


def _matrix(values: Sequence[Sequence[float]], *, name: str) -> Any:
    np = _np()
    try:
        matrix = np.asarray(values, dtype=np.float64)
    except (TypeError, ValueError) as error:
        raise ProbeFitError(f"{name} must be a rectangular numeric matrix.") from error
    if matrix.ndim != 2 or matrix.shape[0] == 0 or matrix.shape[1] == 0:
        raise ProbeFitError(f"{name} must be a non-empty two-dimensional matrix.")
    if not np.isfinite(matrix).all():
        raise ProbeFitError(f"{name} contains non-finite values.")
    return matrix


def _vector(values: Sequence[float], *, name: str) -> Any:
    np = _np()
    try:
        vector = np.asarray(values, dtype=np.float64)
    except (TypeError, ValueError) as error:
        raise ProbeFitError(f"{name} must be numeric.") from error
    if vector.ndim != 1 or vector.size == 0 or not np.isfinite(vector).all():
        raise ProbeFitError(f"{name} must be a non-empty finite vector.")
    return vector


@dataclass(frozen=True)
class StandardScaler:
    mean: tuple[float, ...]
    scale: tuple[float, ...]
    constant_feature_indices: tuple[int, ...]
    training_row_count: int

    def transform(self, features: Sequence[Sequence[float]]) -> Any:
        np = _np()
        matrix = _matrix(features, name="features")
        if (
            not self.mean
            or len(self.mean) != len(self.scale)
            or any(not math.isfinite(value) for value in self.mean)
            or any(not math.isfinite(value) or value <= 0.0 for value in self.scale)
            or not isinstance(self.training_row_count, int)
            or isinstance(self.training_row_count, bool)
            or self.training_row_count <= 0
            or any(
                not isinstance(index, int)
                or isinstance(index, bool)
                or not 0 <= index < len(self.mean)
                for index in self.constant_feature_indices
            )
        ):
            raise ProbeFitError("Scaler metadata is invalid.")
        if matrix.shape[1] != len(self.mean):
            raise ProbeFitError("Feature dimension does not match the scaler.")
        return (
            matrix - np.asarray(self.mean, dtype=np.float64)
        ) / np.asarray(self.scale, dtype=np.float64)


@dataclass(frozen=True)
class RidgeModel:
    alpha: float
    standardized_coefficients: tuple[float, ...]
    standardized_intercept: float
    scaler: StandardScaler

    def predict(self, features: Sequence[Sequence[float]]) -> tuple[float, ...]:
        np = _np()
        transformed = self.scaler.transform(features)
        predictions = transformed @ np.asarray(
            self.standardized_coefficients, dtype=np.float64
        ) + self.standardized_intercept
        return tuple(float(value) for value in predictions)

    @property
    def raw_coefficients(self) -> tuple[float, ...]:
        return tuple(
            coefficient / scale
            for coefficient, scale in zip(
                self.standardized_coefficients,
                self.scaler.scale,
            )
        )

    @property
    def raw_intercept(self) -> float:
        return self.standardized_intercept - sum(
            coefficient * mean
            for coefficient, mean in zip(self.raw_coefficients, self.scaler.mean)
        )

    def predict_raw_equivalent(
        self, features: Sequence[Sequence[float]]
    ) -> tuple[float, ...]:
        matrix = _matrix(features, name="features")
        np = _np()
        predictions = matrix @ np.asarray(self.raw_coefficients) + self.raw_intercept
        return tuple(float(value) for value in predictions)


@dataclass(frozen=True)
class AlphaSelection:
    selected_alpha: float
    mean_mse_by_alpha: Mapping[float, float]
    inner_fold_count: int


@dataclass(frozen=True)
class RidgeFoldFit:
    outer_fold_idx: int
    model: RidgeModel
    alpha_selection: AlphaSelection
    training_indices: tuple[int, ...]
    test_indices: tuple[int, ...]


@dataclass(frozen=True)
class RidgeOOFResult:
    predictions: tuple[float, ...]
    fits: tuple[RidgeFoldFit, ...]


def fit_standard_scaler(features: Sequence[Sequence[float]]) -> StandardScaler:
    np = _np()
    matrix = _matrix(features, name="training features")
    mean = matrix.mean(axis=0)
    raw_scale = matrix.std(axis=0, ddof=0)
    constant = np.flatnonzero(raw_scale == 0.0)
    scale = raw_scale.copy()
    scale[constant] = 1.0
    return StandardScaler(
        mean=tuple(float(value) for value in mean),
        scale=tuple(float(value) for value in scale),
        constant_feature_indices=tuple(int(value) for value in constant),
        training_row_count=int(matrix.shape[0]),
    )


def fit_ridge(
    features: Sequence[Sequence[float]],
    targets: Sequence[float],
    *,
    alpha: float,
    scaler: StandardScaler | None = None,
) -> RidgeModel:
    """Fit an L2-penalized linear probe with an unpenalized intercept."""

    np = _np()
    matrix = _matrix(features, name="training features")
    target = _vector(targets, name="training targets")
    if matrix.shape[0] != target.size:
        raise ProbeFitError("Feature and target row counts differ.")
    if (
        isinstance(alpha, bool)
        or not isinstance(alpha, (int, float))
        or not math.isfinite(float(alpha))
        or alpha <= 0
    ):
        raise ProbeFitError("Ridge alpha must be finite and positive.")
    fitted_scaler = scaler or fit_standard_scaler(matrix)
    if scaler is not None and scaler.training_row_count != matrix.shape[0]:
        raise ProbeFitError(
            "A supplied scaler must be fit on exactly these training rows."
        )
    standardized = fitted_scaler.transform(matrix)
    target_mean = float(target.mean())
    centered_target = target - target_mean
    try:
        if standardized.shape[1] > standardized.shape[0]:
            # Activation vectors are wide (2,048 dimensions) even in the tiny
            # CPU fixture. The dual ridge system is algebraically equivalent
            # and keeps the solve proportional to training-row count.
            dual_system = (
                standardized @ standardized.T
                + float(alpha)
                * np.eye(standardized.shape[0], dtype=np.float64)
            )
            dual_coefficients = np.linalg.solve(
                dual_system,
                centered_target,
            )
            coefficients = standardized.T @ dual_coefficients
        else:
            gram = standardized.T @ standardized
            system = gram + float(alpha) * np.eye(
                gram.shape[0],
                dtype=np.float64,
            )
            rhs = standardized.T @ centered_target
            coefficients = np.linalg.solve(system, rhs)
    except np.linalg.LinAlgError as error:
        raise ProbeFitError("Ridge system could not be solved.") from error
    return RidgeModel(
        alpha=float(alpha),
        standardized_coefficients=tuple(float(value) for value in coefficients),
        standardized_intercept=target_mean,
        scaler=fitted_scaler,
    )


def _group_fold_assignments(
    group_ids: Sequence[str], *, n_splits: int, seed: int
) -> dict[str, int]:
    if (
        not isinstance(n_splits, int)
        or isinstance(n_splits, bool)
        or n_splits < 2
    ):
        raise ProbeFitError("Inner validation requires at least two folds.")
    if not isinstance(seed, int) or isinstance(seed, bool):
        raise ProbeFitError("Inner-validation seed must be an integer.")
    if len(group_ids) == 0 or any(
        not isinstance(value, str) or not value for value in group_ids
    ):
        raise ProbeFitError("Every row requires a non-empty group ID.")
    counts = Counter(group_ids)
    if len(counts) < n_splits:
        raise ProbeFitError(
            f"Need at least {n_splits} groups for grouped inner validation."
        )
    ordered = sorted(
        counts,
        key=lambda group: (
            -counts[group],
            hashlib.sha256(f"{seed}:{group}".encode("utf-8")).hexdigest(),
        ),
    )
    loads = [0] * n_splits
    result: dict[str, int] = {}
    for group in ordered:
        fold = min(range(n_splits), key=lambda item: (loads[item], item))
        result[group] = fold
        loads[fold] += counts[group]
    return result


def select_ridge_alpha_grouped(
    features: Sequence[Sequence[float]],
    targets: Sequence[float],
    group_ids: Sequence[str],
    *,
    alpha_grid: Sequence[float] = (0.1, 1.0, 10.0, 100.0),
    n_splits: int = 4,
    seed: int = 20260719,
) -> AlphaSelection:
    """Select alpha using grouped inner validation and train-only scaling."""

    np = _np()
    matrix = _matrix(features, name="inner-validation features")
    target = _vector(targets, name="inner-validation targets")
    groups = tuple(group_ids)
    if matrix.shape[0] != target.size or target.size != len(groups):
        raise ProbeFitError("Features, targets, and group IDs must align.")
    if not alpha_grid or any(
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or float(value) <= 0.0
        for value in alpha_grid
    ):
        raise ProbeFitError("alpha_grid must contain finite positive values.")
    alphas = tuple(float(value) for value in alpha_grid)
    if len(set(alphas)) != len(alphas):
        raise ProbeFitError("alpha_grid cannot contain duplicate values.")
    assignments = _group_fold_assignments(groups, n_splits=n_splits, seed=seed)
    losses: dict[float, list[float]] = {alpha: [] for alpha in alphas}
    for validation_fold in range(n_splits):
        train_indices = [
            index
            for index, group in enumerate(groups)
            if assignments[group] != validation_fold
        ]
        validation_indices = [
            index
            for index, group in enumerate(groups)
            if assignments[group] == validation_fold
        ]
        if not train_indices or not validation_indices:
            raise ProbeFitError("Grouped inner validation produced an empty split.")
        scaler = fit_standard_scaler(matrix[train_indices])
        for alpha in alphas:
            model = fit_ridge(
                matrix[train_indices],
                target[train_indices],
                alpha=alpha,
                scaler=scaler,
            )
            prediction = np.asarray(model.predict(matrix[validation_indices]))
            mse = float(np.mean((prediction - target[validation_indices]) ** 2))
            losses[alpha].append(mse)
    means = {alpha: float(sum(values) / len(values)) for alpha, values in losses.items()}
    selected = min(alphas, key=lambda alpha: (means[alpha], alpha))
    return AlphaSelection(selected, means, n_splits)


def fit_ridge_oof(
    features: Sequence[Sequence[float]],
    targets: Sequence[float],
    outer_folds: Sequence[int],
    layout_ids: Sequence[str],
    *,
    alpha_grid: Sequence[float] = (0.1, 1.0, 10.0, 100.0),
    inner_fold_count: int = 4,
    seed: int = 20260719,
) -> RidgeOOFResult:
    """Generate predictions only from models that excluded each outer fold."""

    if not isinstance(seed, int) or isinstance(seed, bool):
        raise ProbeFitError("OOF seed must be an integer.")
    np = _np()
    matrix = _matrix(features, name="probe features")
    target = _vector(targets, name="probe targets")
    folds = tuple(outer_folds)
    layouts = tuple(layout_ids)
    if not (matrix.shape[0] == target.size == len(folds) == len(layouts)):
        raise ProbeFitError("OOF inputs must have identical row counts.")
    if any(
        not isinstance(value, int)
        or isinstance(value, bool)
        or value < 0
        for value in folds
    ):
        raise ProbeFitError("Outer folds must be non-negative integer indices.")
    layout_fold: dict[str, int] = {}
    for layout, fold in zip(layouts, folds):
        if not isinstance(layout, str) or not layout:
            raise ProbeFitError("Every row requires a non-empty layout ID.")
        previous = layout_fold.setdefault(layout, fold)
        if previous != fold:
            raise ProbeFitError("One layout appears in multiple outer folds.")
    predictions = np.full(target.shape, np.nan, dtype=np.float64)
    fits: list[RidgeFoldFit] = []
    for outer_fold in sorted(set(folds)):
        training_indices = tuple(index for index, fold in enumerate(folds) if fold != outer_fold)
        test_indices = tuple(index for index, fold in enumerate(folds) if fold == outer_fold)
        if not training_indices or not test_indices:
            raise ProbeFitError("Outer validation produced an empty split.")
        selection = select_ridge_alpha_grouped(
            matrix[list(training_indices)],
            target[list(training_indices)],
            [layouts[index] for index in training_indices],
            alpha_grid=alpha_grid,
            n_splits=inner_fold_count,
            seed=seed + outer_fold,
        )
        model = fit_ridge(
            matrix[list(training_indices)],
            target[list(training_indices)],
            alpha=selection.selected_alpha,
        )
        predictions[list(test_indices)] = model.predict(matrix[list(test_indices)])
        fits.append(
            RidgeFoldFit(
                outer_fold,
                model,
                selection,
                training_indices,
                test_indices,
            )
        )
    if not np.isfinite(predictions).all():
        raise ProbeFitError("Not every row received one out-of-fold prediction.")
    return RidgeOOFResult(
        predictions=tuple(float(value) for value in predictions),
        fits=tuple(fits),
    )


def build_scaler_artifact(
    scaler: StandardScaler,
    *,
    artifact_id: str,
    code_sha: str,
    config_hash: str,
    input_manifest_hash: str,
    outer_fold_idx: int,
) -> dict[str, Any]:
    if (
        not isinstance(outer_fold_idx, int)
        or isinstance(outer_fold_idx, bool)
        or outer_fold_idx < 0
    ):
        raise ProbeFitError("outer_fold_idx must be a non-negative integer.")
    return seal_artifact(
        {
            "artifact_type": "scaler_manifest",
            "artifact_id": artifact_id,
            "code_sha": code_sha,
            "config_hash": config_hash,
            "input_manifest_hash": input_manifest_hash,
            "outer_fold_idx": outer_fold_idx,
            "fit_scope": "outer_training_rows_only",
            "feature_count": len(scaler.mean),
            "training_row_count": scaler.training_row_count,
            "mean": list(scaler.mean),
            "scale": list(scaler.scale),
            "constant_feature_indices": list(scaler.constant_feature_indices),
        }
    )


def build_ridge_fit_artifact(
    fit: RidgeFoldFit,
    *,
    artifact_id: str,
    code_sha: str,
    config_hash: str,
    input_manifest_hash: str,
    fold_manifest_hash: str,
    scaler_hash: str,
    layer_idx: int,
    hook_site: str,
    target_name: str,
) -> dict[str, Any]:
    for name, value in (
        ("fold_manifest_hash", fold_manifest_hash),
        ("scaler_hash", scaler_hash),
    ):
        if not is_hex_digest(value, 64):
            raise ProbeFitError(f"{name} must be SHA-256.")
    if (
        not isinstance(fit.outer_fold_idx, int)
        or isinstance(fit.outer_fold_idx, bool)
        or fit.outer_fold_idx < 0
    ):
        raise ProbeFitError("Ridge fit outer_fold_idx is invalid.")
    if not math.isclose(
        fit.model.alpha,
        fit.alpha_selection.selected_alpha,
        rel_tol=0.0,
        abs_tol=0.0,
    ):
        raise ProbeFitError("Ridge model alpha differs from its selection record.")
    if not isinstance(layer_idx, int) or isinstance(layer_idx, bool) or layer_idx < 0:
        raise ProbeFitError("layer_idx must be a non-negative integer.")
    for name, value in (
        ("hook_site", hook_site),
        ("target_name", target_name),
    ):
        if not isinstance(value, str) or not value.strip():
            raise ProbeFitError(f"{name} must be non-empty.")
    return seal_artifact(
        {
            "artifact_type": "ridge_fit_manifest",
            "artifact_id": artifact_id,
            "code_sha": code_sha,
            "config_hash": config_hash,
            "input_manifest_hash": input_manifest_hash,
            "fold_manifest_hash": fold_manifest_hash,
            "scaler_hash": scaler_hash,
            "outer_fold_idx": fit.outer_fold_idx,
            "layer_idx": layer_idx,
            "hook_site": hook_site,
            "target_name": target_name,
            "selected_alpha": fit.model.alpha,
            "inner_fold_count": fit.alpha_selection.inner_fold_count,
            "validation_mse_by_alpha": {
                str(alpha): mse
                for alpha, mse in fit.alpha_selection.mean_mse_by_alpha.items()
            },
            "standardized_coefficients": list(fit.model.standardized_coefficients),
            "standardized_intercept": fit.model.standardized_intercept,
            "raw_coefficients": list(fit.model.raw_coefficients),
            "raw_intercept": fit.model.raw_intercept,
            "training_row_indices": list(fit.training_indices),
            "test_row_indices": list(fit.test_indices),
            "selection_policy": "grouped_inner_validation_training_only",
        }
    )
