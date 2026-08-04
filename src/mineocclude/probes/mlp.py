"""Predeclared MLP comparison harness for validation-selected layers."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any

from mineocclude.analysis.manifests import is_hex_digest, seal_artifact, sha256_value

from .ridge import (
    ProbeFitError,
    StandardScaler,
    _group_fold_assignments,
    _matrix,
    _np,
    _vector,
    fit_standard_scaler,
)


@dataclass(frozen=True)
class MLPTrainingSpec:
    hidden_layers: tuple[int, int] = (256, 128)
    learning_rate: float = 0.001
    maximum_epochs: int = 200
    early_stopping_patience: int = 20
    batch_size: int = 64
    seed: int = 20260722


@dataclass(frozen=True)
class MLPModel:
    weights: tuple[Any, ...]
    biases: tuple[Any, ...]
    scaler: StandardScaler
    completed_epochs: int
    best_validation_mse: float
    training_spec: MLPTrainingSpec

    def predict(self, features: Sequence[Sequence[float]]) -> tuple[float, ...]:
        np = _np()
        values = self.scaler.transform(features)
        for index, (weight, bias) in enumerate(zip(self.weights, self.biases)):
            values = values @ weight + bias
            if index < len(self.weights) - 1:
                values = np.maximum(values, 0.0)
        if not np.isfinite(values).all():
            raise ProbeFitError("MLP prediction produced non-finite values.")
        return tuple(float(value) for value in values.reshape(-1))


def select_mlp_eligible_layers(
    validation_records: Sequence[Mapping[str, Any]],
    *,
    eligible_count: int = 3,
) -> tuple[int, ...]:
    """Select layers only from predeclared ridge validation records."""

    if eligible_count <= 0:
        raise ProbeFitError("eligible_count must be positive.")
    by_layer: dict[int, float] = {}
    for record in validation_records:
        if record.get("selection_split") != "validation":
            raise ProbeFitError("MLP eligibility must use validation records only.")
        if record.get("uses_test_data") is not False:
            raise ProbeFitError("Test data cannot select MLP-eligible layers.")
        layer = record.get("layer_idx")
        score = record.get("validation_r2")
        if (
            not isinstance(layer, int)
            or isinstance(layer, bool)
            or layer < 0
            or isinstance(score, bool)
            or not isinstance(score, (int, float))
            or not math.isfinite(float(score))
        ):
            raise ProbeFitError("Layer validation record is invalid.")
        if layer in by_layer:
            raise ProbeFitError(f"Duplicate validation record for layer {layer}.")
        by_layer[layer] = float(score)
    if len(by_layer) < eligible_count:
        raise ProbeFitError("Not enough validated layers for the MLP comparison.")
    return tuple(
        layer
        for layer, _score in sorted(
            by_layer.items(), key=lambda item: (-item[1], item[0])
        )[:eligible_count]
    )


def _validate_spec(spec: MLPTrainingSpec) -> None:
    if (
        len(spec.hidden_layers) != 2
        or any(
            not isinstance(width, int) or isinstance(width, bool) or width <= 0
            for width in spec.hidden_layers
        )
    ):
        raise ProbeFitError("MLP requires two positive hidden-layer widths.")
    if not math.isfinite(spec.learning_rate) or spec.learning_rate <= 0:
        raise ProbeFitError("MLP learning_rate must be finite and positive.")
    for name in ("maximum_epochs", "early_stopping_patience", "batch_size"):
        value = getattr(spec, name)
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise ProbeFitError(f"MLP {name} must be a positive integer.")
    if not isinstance(spec.seed, int) or isinstance(spec.seed, bool):
        raise ProbeFitError("MLP seed must be an integer.")


def fit_mlp(
    training_features: Sequence[Sequence[float]],
    training_targets: Sequence[float],
    validation_features: Sequence[Sequence[float]],
    validation_targets: Sequence[float],
    *,
    spec: MLPTrainingSpec = MLPTrainingSpec(),
) -> MLPModel:
    """Fit a deterministic ReLU MLP with validation-only early stopping.

    The caller must construct the validation set from training layouts. Test
    rows are intentionally absent from this API.
    """

    _validate_spec(spec)
    np = _np()
    train_x = _matrix(training_features, name="MLP training features")
    train_y = _vector(training_targets, name="MLP training targets").reshape(-1, 1)
    validation_x = _matrix(validation_features, name="MLP validation features")
    validation_y = _vector(validation_targets, name="MLP validation targets").reshape(-1, 1)
    if train_x.shape[0] != train_y.shape[0] or validation_x.shape[0] != validation_y.shape[0]:
        raise ProbeFitError("MLP feature and target row counts differ.")
    if train_x.shape[1] != validation_x.shape[1]:
        raise ProbeFitError("MLP train/validation feature dimensions differ.")
    scaler = fit_standard_scaler(train_x)
    train_x = scaler.transform(train_x)
    validation_x = scaler.transform(validation_x)

    rng = np.random.default_rng(spec.seed)
    dimensions = (train_x.shape[1], *spec.hidden_layers, 1)
    weights = [
        rng.normal(
            0.0,
            math.sqrt(2.0 / dimensions[index]),
            size=(dimensions[index], dimensions[index + 1]),
        )
        for index in range(len(dimensions) - 1)
    ]
    biases = [np.zeros((1, width), dtype=np.float64) for width in dimensions[1:]]
    first_moment_w = [np.zeros_like(value) for value in weights]
    second_moment_w = [np.zeros_like(value) for value in weights]
    first_moment_b = [np.zeros_like(value) for value in biases]
    second_moment_b = [np.zeros_like(value) for value in biases]
    best_weights = [value.copy() for value in weights]
    best_biases = [value.copy() for value in biases]
    best_validation = math.inf
    stale_epochs = 0
    update_step = 0
    completed_epochs = 0

    def forward(values: Any) -> tuple[list[Any], list[Any]]:
        activations = [values]
        preactivations: list[Any] = []
        for layer_index, (weight, bias) in enumerate(zip(weights, biases)):
            before = activations[-1] @ weight + bias
            preactivations.append(before)
            activations.append(
                np.maximum(before, 0.0)
                if layer_index < len(weights) - 1
                else before
            )
        return activations, preactivations

    for epoch in range(spec.maximum_epochs):
        completed_epochs = epoch + 1
        order = rng.permutation(train_x.shape[0])
        for start in range(0, train_x.shape[0], spec.batch_size):
            indices = order[start : start + spec.batch_size]
            batch_x = train_x[indices]
            batch_y = train_y[indices]
            activations, preactivations = forward(batch_x)
            gradient = 2.0 * (activations[-1] - batch_y) / batch_y.shape[0]
            gradients_w: list[Any] = [None] * len(weights)
            gradients_b: list[Any] = [None] * len(biases)
            for layer_index in reversed(range(len(weights))):
                gradients_w[layer_index] = activations[layer_index].T @ gradient
                gradients_b[layer_index] = gradient.sum(axis=0, keepdims=True)
                if layer_index > 0:
                    gradient = (gradient @ weights[layer_index].T) * (
                        preactivations[layer_index - 1] > 0.0
                    )
            update_step += 1
            for layer_index in range(len(weights)):
                first_moment_w[layer_index] = (
                    0.9 * first_moment_w[layer_index]
                    + 0.1 * gradients_w[layer_index]
                )
                second_moment_w[layer_index] = (
                    0.999 * second_moment_w[layer_index]
                    + 0.001 * (gradients_w[layer_index] ** 2)
                )
                first_moment_b[layer_index] = (
                    0.9 * first_moment_b[layer_index]
                    + 0.1 * gradients_b[layer_index]
                )
                second_moment_b[layer_index] = (
                    0.999 * second_moment_b[layer_index]
                    + 0.001 * (gradients_b[layer_index] ** 2)
                )
                correction1 = 1.0 - 0.9**update_step
                correction2 = 1.0 - 0.999**update_step
                weights[layer_index] -= (
                    spec.learning_rate
                    * (first_moment_w[layer_index] / correction1)
                    / (np.sqrt(second_moment_w[layer_index] / correction2) + 1e-8)
                )
                biases[layer_index] -= (
                    spec.learning_rate
                    * (first_moment_b[layer_index] / correction1)
                    / (np.sqrt(second_moment_b[layer_index] / correction2) + 1e-8)
                )
        validation_prediction = forward(validation_x)[0][-1]
        validation_mse = float(np.mean((validation_prediction - validation_y) ** 2))
        if not math.isfinite(validation_mse):
            raise ProbeFitError("MLP training produced a non-finite validation loss.")
        if validation_mse < best_validation:
            best_validation = validation_mse
            best_weights = [value.copy() for value in weights]
            best_biases = [value.copy() for value in biases]
            stale_epochs = 0
        else:
            stale_epochs += 1
            if stale_epochs >= spec.early_stopping_patience:
                break
    return MLPModel(
        weights=tuple(best_weights),
        biases=tuple(best_biases),
        scaler=scaler,
        completed_epochs=completed_epochs,
        best_validation_mse=best_validation,
        training_spec=spec,
    )


@dataclass(frozen=True)
class MLPValidationFit:
    model: MLPModel
    training_indices: tuple[int, ...]
    validation_indices: tuple[int, ...]
    training_group_ids: tuple[str, ...]
    validation_group_ids: tuple[str, ...]


@dataclass(frozen=True)
class MLPFoldFit:
    outer_fold_idx: int
    model: MLPModel
    training_indices: tuple[int, ...]
    validation_indices: tuple[int, ...]
    test_indices: tuple[int, ...]
    training_group_ids: tuple[str, ...]
    validation_group_ids: tuple[str, ...]


@dataclass(frozen=True)
class MLPOOFResult:
    predictions: tuple[float, ...]
    fits: tuple[MLPFoldFit, ...]


def fit_mlp_grouped_validation(
    features: Sequence[Sequence[float]],
    targets: Sequence[float],
    group_ids: Sequence[str],
    *,
    validation_fold_idx: int = 0,
    n_splits: int = 4,
    spec: MLPTrainingSpec = MLPTrainingSpec(),
) -> MLPValidationFit:
    """Build a validation split from whole training groups and fit the MLP."""

    matrix = _matrix(features, name="MLP grouped-validation features")
    target = _vector(targets, name="MLP grouped-validation targets")
    groups = tuple(group_ids)
    if not (matrix.shape[0] == target.size == len(groups)):
        raise ProbeFitError("MLP features, targets, and groups must align.")
    if (
        not isinstance(n_splits, int)
        or isinstance(n_splits, bool)
        or n_splits < 2
    ):
        raise ProbeFitError("MLP n_splits must be an integer of at least two.")
    if (
        not isinstance(validation_fold_idx, int)
        or isinstance(validation_fold_idx, bool)
        or not 0 <= validation_fold_idx < n_splits
    ):
        raise ProbeFitError("validation_fold_idx is outside the inner split.")
    assignments = _group_fold_assignments(
        groups, n_splits=n_splits, seed=spec.seed
    )
    training_indices = tuple(
        index
        for index, group in enumerate(groups)
        if assignments[group] != validation_fold_idx
    )
    validation_indices = tuple(
        index
        for index, group in enumerate(groups)
        if assignments[group] == validation_fold_idx
    )
    training_groups = tuple(sorted({groups[index] for index in training_indices}))
    validation_groups = tuple(
        sorted({groups[index] for index in validation_indices})
    )
    if set(training_groups) & set(validation_groups):
        raise ProbeFitError("MLP training and validation groups overlap.")
    model = fit_mlp(
        matrix[list(training_indices)],
        target[list(training_indices)],
        matrix[list(validation_indices)],
        target[list(validation_indices)],
        spec=spec,
    )
    return MLPValidationFit(
        model=model,
        training_indices=training_indices,
        validation_indices=validation_indices,
        training_group_ids=training_groups,
        validation_group_ids=validation_groups,
    )


def fit_mlp_oof(
    features: Sequence[Sequence[float]],
    targets: Sequence[float],
    outer_folds: Sequence[int],
    layout_ids: Sequence[str],
    *,
    inner_fold_count: int = 4,
    validation_fold_idx: int = 0,
    spec: MLPTrainingSpec = MLPTrainingSpec(),
) -> MLPOOFResult:
    """Generate MLP predictions from fits that never see their outer fold."""

    _validate_spec(spec)
    np = _np()
    matrix = _matrix(features, name="MLP OOF features")
    target = _vector(targets, name="MLP OOF targets")
    folds = tuple(outer_folds)
    layouts = tuple(layout_ids)
    if not (matrix.shape[0] == target.size == len(folds) == len(layouts)):
        raise ProbeFitError("MLP OOF inputs must have identical row counts.")
    if any(
        not isinstance(value, int)
        or isinstance(value, bool)
        or value < 0
        for value in folds
    ):
        raise ProbeFitError(
            "MLP outer folds must be non-negative integer indices."
        )
    layout_fold: dict[str, int] = {}
    for layout, fold in zip(layouts, folds):
        if not isinstance(layout, str) or not layout:
            raise ProbeFitError("Every MLP row requires a non-empty layout ID.")
        previous = layout_fold.setdefault(layout, fold)
        if previous != fold:
            raise ProbeFitError("One layout appears in multiple MLP outer folds.")

    predictions = np.full(target.shape, np.nan, dtype=np.float64)
    fits: list[MLPFoldFit] = []
    for outer_fold in sorted(set(folds)):
        outer_training = tuple(
            index for index, fold in enumerate(folds) if fold != outer_fold
        )
        test_indices = tuple(
            index for index, fold in enumerate(folds) if fold == outer_fold
        )
        if not outer_training or not test_indices:
            raise ProbeFitError("MLP outer validation produced an empty split.")
        fold_spec = replace(spec, seed=spec.seed + outer_fold)
        validation_fit = fit_mlp_grouped_validation(
            matrix[list(outer_training)],
            target[list(outer_training)],
            [layouts[index] for index in outer_training],
            validation_fold_idx=validation_fold_idx,
            n_splits=inner_fold_count,
            spec=fold_spec,
        )
        training_indices = tuple(
            outer_training[index] for index in validation_fit.training_indices
        )
        validation_indices = tuple(
            outer_training[index] for index in validation_fit.validation_indices
        )
        if set(training_indices) & set(validation_indices):
            raise ProbeFitError("MLP inner training and validation rows overlap.")
        if (set(training_indices) | set(validation_indices)) & set(test_indices):
            raise ProbeFitError("MLP fit rows overlap the held-out outer fold.")
        predictions[list(test_indices)] = validation_fit.model.predict(
            matrix[list(test_indices)]
        )
        fits.append(
            MLPFoldFit(
                outer_fold_idx=outer_fold,
                model=validation_fit.model,
                training_indices=training_indices,
                validation_indices=validation_indices,
                test_indices=test_indices,
                training_group_ids=validation_fit.training_group_ids,
                validation_group_ids=validation_fit.validation_group_ids,
            )
        )
    if not np.isfinite(predictions).all():
        raise ProbeFitError("Not every row received one MLP OOF prediction.")
    return MLPOOFResult(
        predictions=tuple(float(value) for value in predictions),
        fits=tuple(fits),
    )


def build_mlp_fit_artifact(
    fit: MLPValidationFit | MLPFoldFit,
    *,
    artifact_id: str,
    code_sha: str,
    config_hash: str,
    input_manifest_hash: str,
    fold_manifest_hash: str,
    layer_idx: int,
    hook_site: str,
    target_name: str,
) -> dict[str, Any]:
    """Seal MLP selection/training metadata without embedding large weights."""

    if not is_hex_digest(fold_manifest_hash, 64):
        raise ProbeFitError("fold_manifest_hash must be SHA-256.")
    if (
        not isinstance(layer_idx, int)
        or isinstance(layer_idx, bool)
        or layer_idx < 0
    ):
        raise ProbeFitError("layer_idx must be a non-negative integer.")
    for name, value in (
        ("hook_site", hook_site),
        ("target_name", target_name),
    ):
        if not isinstance(value, str) or not value.strip():
            raise ProbeFitError(f"{name} must be non-empty.")
    model = fit.model
    model_hash = sha256_value(
        {
            "weights": [value.tolist() for value in model.weights],
            "biases": [value.tolist() for value in model.biases],
        }
    )
    payload: dict[str, Any] = {
        "artifact_type": "mlp_fit_manifest",
        "artifact_id": artifact_id,
        "code_sha": code_sha,
        "config_hash": config_hash,
        "input_manifest_hash": input_manifest_hash,
        "fold_manifest_hash": fold_manifest_hash,
        "layer_idx": layer_idx,
        "hook_site": hook_site,
        "target_name": target_name,
        "model_hash": model_hash,
        "hidden_layers": list(model.training_spec.hidden_layers),
        "learning_rate": model.training_spec.learning_rate,
        "maximum_epochs": model.training_spec.maximum_epochs,
        "early_stopping_patience": (
            model.training_spec.early_stopping_patience
        ),
        "batch_size": model.training_spec.batch_size,
        "seed": model.training_spec.seed,
        "completed_epochs": model.completed_epochs,
        "best_validation_mse": model.best_validation_mse,
        "training_indices": list(fit.training_indices),
        "validation_indices": list(fit.validation_indices),
        "training_group_ids": list(fit.training_group_ids),
        "validation_group_ids": list(fit.validation_group_ids),
        "selection_policy": "grouped_validation_no_test_rows",
    }
    if isinstance(fit, MLPFoldFit):
        payload.update(
            {
                "outer_fold_idx": fit.outer_fold_idx,
                "test_indices": list(fit.test_indices),
                "fit_scope": "outer_fold_oof",
            }
        )
    else:
        payload["fit_scope"] = "grouped_validation"
    return seal_artifact(payload)
