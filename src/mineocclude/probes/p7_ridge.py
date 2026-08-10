"""Bounded sample-space ridge kernels for the large-scale P7 authority.

The routines in this module preserve the literal objective implemented in
``mineocclude.probes.ridge``: population-variance StandardScaler statistics are
fit on training rows only, constant features receive unit scale, targets are
centered, and the intercept is not penalized.  Wide representations are never
converted into a feature-by-feature covariance matrix.
"""

from __future__ import annotations

import math
import time
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np


class SampleSpaceRidgeError(ValueError):
    """Raised when a bounded ridge request is malformed or leakage-prone."""


@dataclass(frozen=True)
class ScalerStatistics:
    """The training-only population statistics for one feature block."""

    mean: np.ndarray
    scale: np.ndarray
    constant_feature_count: int
    training_row_count: int


@dataclass(frozen=True)
class KernelResult:
    """One scope-by-training standardized Gram block and timing audit."""

    kernel: np.ndarray
    scaler: ScalerStatistics
    device: str
    timings: Mapping[str, float]
    peak_device_memory_bytes: int


@dataclass(frozen=True)
class FeatureSolveResult:
    """All-alpha predictions from the smaller exact primal/dual system."""

    predictions_by_alpha: Mapping[float, np.ndarray]
    solve_space: str
    system_dimension: int
    scaler: ScalerStatistics
    timings: Mapping[str, float]


def training_scaler_statistics(training_features: Any) -> ScalerStatistics:
    """Fit the repository's exact population StandardScaler on training rows."""

    matrix = np.asarray(training_features, dtype=np.float64)
    if matrix.ndim != 2 or not matrix.shape[0] or not matrix.shape[1]:
        raise SampleSpaceRidgeError("training features must be a non-empty matrix")
    if not np.isfinite(matrix).all():
        raise SampleSpaceRidgeError("training features contain non-finite values")
    mean = matrix.mean(axis=0)
    raw_scale = matrix.std(axis=0, ddof=0)
    constant = raw_scale == 0.0
    scale = raw_scale.copy()
    scale[constant] = 1.0
    return ScalerStatistics(
        mean=mean,
        scale=scale,
        constant_feature_count=int(constant.sum()),
        training_row_count=int(matrix.shape[0]),
    )


def _validate_scope(training_features: Any, scope_features: Any) -> tuple[Any, Any]:
    training = np.asarray(training_features)
    scope = np.asarray(scope_features)
    if training.ndim != 2 or scope.ndim != 2:
        raise SampleSpaceRidgeError("training and scope features must be matrices")
    if training.shape[0] == 0 or training.shape[1] == 0 or scope.shape[0] == 0:
        raise SampleSpaceRidgeError("training and scope features cannot be empty")
    if training.shape[1] != scope.shape[1]:
        raise SampleSpaceRidgeError("training and scope feature widths differ")
    return training, scope


def standardized_kernel_numpy(
    training_features: Any,
    scope_features: Any,
) -> KernelResult:
    """Build an exact float64 scope-by-training standardized Gram matrix."""

    training, scope = _validate_scope(training_features, scope_features)
    scale_started = time.perf_counter()
    scaler = training_scaler_statistics(training)
    train_standardized = (
        np.asarray(training, dtype=np.float64) - scaler.mean
    ) / scaler.scale
    scope_standardized = (
        np.asarray(scope, dtype=np.float64) - scaler.mean
    ) / scaler.scale
    scaling_seconds = time.perf_counter() - scale_started
    kernel_started = time.perf_counter()
    kernel = scope_standardized @ train_standardized.T
    kernel_seconds = time.perf_counter() - kernel_started
    return KernelResult(
        kernel=np.asarray(kernel, dtype=np.float64),
        scaler=scaler,
        device="cpu",
        timings={"scaling_seconds": scaling_seconds, "kernel_seconds": kernel_seconds},
        peak_device_memory_bytes=0,
    )


def standardized_kernel_cuda(
    training_features: Any,
    scope_features: Any,
    *,
    device: str = "cuda:0",
) -> KernelResult:
    """Build the literal float64 kernel on CUDA with TF32 disabled."""

    import torch

    training, scope = _validate_scope(training_features, scope_features)
    if not torch.cuda.is_available():
        raise SampleSpaceRidgeError("CUDA kernel requested without CUDA")
    torch.backends.cuda.matmul.allow_tf32 = False
    # The qualified MineWorld Torch build accepts only its current-device form
    # for these memory helpers.
    torch.cuda.reset_peak_memory_stats()
    scale_started = time.perf_counter()
    scaler = training_scaler_statistics(training)
    mean = torch.as_tensor(scaler.mean, dtype=torch.float64, device=device)
    scale = torch.as_tensor(scaler.scale, dtype=torch.float64, device=device)
    train = torch.as_tensor(
        np.asarray(training, dtype=np.float64, order="C"),
        dtype=torch.float64,
        device=device,
    )
    scope_tensor = torch.as_tensor(
        np.asarray(scope, dtype=np.float64, order="C"),
        dtype=torch.float64,
        device=device,
    )
    train_standardized = (train - mean) / scale
    scope_standardized = (scope_tensor - mean) / scale
    del train, scope_tensor, mean, scale
    torch.cuda.synchronize(device)
    scaling_seconds = time.perf_counter() - scale_started
    kernel_started = time.perf_counter()
    kernel_device = scope_standardized @ train_standardized.T
    torch.cuda.synchronize(device)
    kernel_seconds = time.perf_counter() - kernel_started
    kernel = np.asarray(kernel_device.cpu().numpy(), dtype=np.float64)
    peak = int(torch.cuda.max_memory_allocated())
    del kernel_device, scope_standardized, train_standardized
    torch.cuda.empty_cache()
    return KernelResult(
        kernel=kernel,
        scaler=scaler,
        device=device,
        timings={"scaling_seconds": scaling_seconds, "kernel_seconds": kernel_seconds},
        peak_device_memory_bytes=peak,
    )


def accumulate_standardized_kernel(
    feature_blocks: Iterable[tuple[Any, Any]],
    *,
    device: str,
) -> tuple[np.ndarray, list[KernelResult]]:
    """Accumulate exact additive feature-block kernels in bounded memory."""

    total: np.ndarray | None = None
    records: list[KernelResult] = []
    for training_block, scope_block in feature_blocks:
        result = (
            standardized_kernel_numpy(training_block, scope_block)
            if device == "cpu"
            else standardized_kernel_cuda(training_block, scope_block, device=device)
        )
        if total is None:
            total = np.zeros_like(result.kernel, dtype=np.float64)
        if total.shape != result.kernel.shape:
            raise SampleSpaceRidgeError("feature blocks produced inconsistent kernels")
        total += result.kernel
        records.append(result)
    if total is None:
        raise SampleSpaceRidgeError("at least one feature block is required")
    return total, records


def ridge_predictions_from_kernel(
    kernel: Any,
    training_targets: Sequence[float],
    *,
    alpha: float,
    training_scope_positions: Sequence[int] | None = None,
    prediction_scope_positions: Sequence[int] | None = None,
) -> np.ndarray:
    """Solve the literal centered ridge objective from a sample-space kernel."""

    gram = np.asarray(kernel, dtype=np.float64)
    targets = np.asarray(training_targets, dtype=np.float64)
    if gram.ndim != 2 or targets.ndim != 1 or targets.size == 0:
        raise SampleSpaceRidgeError("kernel and training targets are malformed")
    if not math.isfinite(float(alpha)) or float(alpha) <= 0.0:
        raise SampleSpaceRidgeError("alpha must be finite and positive")
    train_positions = np.asarray(
        list(range(targets.size))
        if training_scope_positions is None
        else training_scope_positions,
        dtype=np.int64,
    )
    if train_positions.size != targets.size or gram.shape[1] != targets.size:
        raise SampleSpaceRidgeError("kernel training axis does not match targets")
    if np.any(train_positions < 0) or np.any(train_positions >= gram.shape[0]):
        raise SampleSpaceRidgeError("training scope position is out of bounds")
    prediction_positions = np.asarray(
        list(range(gram.shape[0]))
        if prediction_scope_positions is None
        else prediction_scope_positions,
        dtype=np.int64,
    )
    centered = targets - targets.mean()
    system = gram[train_positions] + float(alpha) * np.eye(
        targets.size, dtype=np.float64
    )
    dual = np.linalg.solve(system, centered)
    return gram[prediction_positions] @ dual + targets.mean()


def ridge_predictions_all_alphas_from_kernel(
    kernel: Any,
    training_targets: Sequence[float],
    *,
    alphas: Sequence[float],
    training_scope_positions: Sequence[int] | None = None,
    prediction_scope_positions: Sequence[int] | None = None,
) -> dict[float, np.ndarray]:
    """Reuse one exact symmetric eigensystem for all frozen ridge alphas."""

    gram = np.asarray(kernel, dtype=np.float64)
    targets = np.asarray(training_targets, dtype=np.float64)
    alpha_values = tuple(float(value) for value in alphas)
    if not alpha_values or any(
        not math.isfinite(value) or value <= 0 for value in alpha_values
    ):
        raise SampleSpaceRidgeError("alphas must be finite and positive")
    train_positions = np.asarray(
        list(range(targets.size))
        if training_scope_positions is None
        else training_scope_positions,
        dtype=np.int64,
    )
    prediction_positions = np.asarray(
        list(range(gram.shape[0]))
        if prediction_scope_positions is None
        else prediction_scope_positions,
        dtype=np.int64,
    )
    if gram.ndim != 2 or gram.shape[1] != targets.size:
        raise SampleSpaceRidgeError("kernel training axis does not match targets")
    training_gram = gram[train_positions]
    # Additive block accumulation can introduce a last-bit asymmetry even though
    # the mathematical Gram matrix is symmetric.  Symmetrizing is an exact
    # equivalent scheduling normalization frozen before scientific outcomes.
    training_gram = (training_gram + training_gram.T) * 0.5
    eigenvalues, eigenvectors = np.linalg.eigh(training_gram)
    centered = targets - targets.mean()
    projected = eigenvectors.T @ centered
    predictions = {}
    for alpha in alpha_values:
        dual = eigenvectors @ (projected / (eigenvalues + alpha))
        predictions[alpha] = gram[prediction_positions] @ dual + targets.mean()
    return predictions


def ridge_predictions_all_alphas_from_features(
    training_features: Any,
    scope_features: Any,
    training_targets: Sequence[float],
    *,
    alphas: Sequence[float],
    prediction_scope_positions: Sequence[int] | None = None,
) -> FeatureSolveResult:
    """Solve all alphas in the smaller exact primal or sample space.

    This path is useful for the 2,048-wide per-token ranking fits: at large N,
    a bounded 2,048-dimensional primal system is substantially cheaper than a
    row-space system.  FULL and BEST-K remain in sample space because their
    feature counts exceed their row counts; a FULL feature covariance is never
    formed.
    """

    training, scope = _validate_scope(training_features, scope_features)
    targets = np.asarray(training_targets, dtype=np.float64)
    alpha_values = tuple(float(value) for value in alphas)
    if targets.ndim != 1 or targets.size != training.shape[0]:
        raise SampleSpaceRidgeError("training targets do not align with features")
    if not alpha_values or any(
        not math.isfinite(value) or value <= 0 for value in alpha_values
    ):
        raise SampleSpaceRidgeError("alphas must be finite and positive")
    scaling_started = time.perf_counter()
    scaler = training_scaler_statistics(training)
    train_standardized = (
        np.asarray(training, dtype=np.float64) - scaler.mean
    ) / scaler.scale
    scope_standardized = (
        np.asarray(scope, dtype=np.float64) - scaler.mean
    ) / scaler.scale
    scaling_seconds = time.perf_counter() - scaling_started
    positions = np.asarray(
        list(range(scope.shape[0]))
        if prediction_scope_positions is None
        else prediction_scope_positions,
        dtype=np.int64,
    )
    centered = targets - targets.mean()
    build_started = time.perf_counter()
    if training.shape[1] < training.shape[0]:
        solve_space = "primal"
        sufficient = train_standardized.T @ train_standardized
        rhs = train_standardized.T @ centered
    else:
        solve_space = "sample"
        sufficient = train_standardized @ train_standardized.T
        rhs = centered
    build_seconds = time.perf_counter() - build_started
    solve_started = time.perf_counter()
    predictions = {}
    identity = np.eye(sufficient.shape[0], dtype=np.float64)
    for alpha in alpha_values:
        solution = np.linalg.solve(sufficient + alpha * identity, rhs)
        if solve_space == "sample":
            solution = train_standardized.T @ solution
        predictions[alpha] = scope_standardized[positions] @ solution + targets.mean()
    solve_seconds = time.perf_counter() - solve_started
    return FeatureSolveResult(
        predictions_by_alpha=predictions,
        solve_space=solve_space,
        system_dimension=int(sufficient.shape[0]),
        scaler=scaler,
        timings={
            "scaling_seconds": scaling_seconds,
            "sufficient_structure_seconds": build_seconds,
            "four_alpha_solve_predict_seconds": solve_seconds,
            "total_seconds": scaling_seconds + build_seconds + solve_seconds,
        },
    )


def batched_ridge_predictions_all_alphas(
    kernels: Any,
    training_targets: Sequence[float],
    *,
    alphas: Sequence[float],
    training_scope_positions: Sequence[int] | None = None,
    prediction_scope_positions: Sequence[int] | None = None,
) -> tuple[dict[float, np.ndarray], ...]:
    """Solve every token in one bounded kernel batch for all alphas."""

    batch = np.asarray(kernels, dtype=np.float64)
    if batch.ndim != 3 or batch.shape[0] == 0:
        raise SampleSpaceRidgeError("kernels must have [tokens,scope,training]")
    return tuple(
        ridge_predictions_all_alphas_from_kernel(
            batch[offset],
            training_targets,
            alphas=alphas,
            training_scope_positions=training_scope_positions,
            prediction_scope_positions=prediction_scope_positions,
        )
        for offset in range(batch.shape[0])
    )


def batched_token_kernels_numpy(
    training_tokens: Any,
    scope_tokens: Any,
) -> tuple[np.ndarray, tuple[ScalerStatistics, ...]]:
    """Build independent exact kernels for multiple token positions per call."""

    training = np.asarray(training_tokens)
    scope = np.asarray(scope_tokens)
    if training.ndim != 3 or scope.ndim != 3:
        raise SampleSpaceRidgeError("token batches must have [rows,tokens,hidden]")
    if training.shape[1:] != scope.shape[1:] or training.shape[0] == 0:
        raise SampleSpaceRidgeError("training and scope token batches do not align")
    kernels = []
    scalers = []
    for token_offset in range(training.shape[1]):
        result = standardized_kernel_numpy(
            training[:, token_offset, :], scope[:, token_offset, :]
        )
        kernels.append(result.kernel)
        scalers.append(result.scaler)
    return np.stack(kernels), tuple(scalers)


def batched_token_kernels_cuda(
    training_tokens: Any,
    scope_tokens: Any,
    *,
    device: str = "cuda:0",
) -> tuple[np.ndarray, tuple[ScalerStatistics, ...], dict[str, float | int]]:
    """Build multiple independent token kernels in one bounded CUDA batch."""

    import torch

    training = np.asarray(training_tokens)
    scope = np.asarray(scope_tokens)
    if training.ndim != 3 or scope.ndim != 3:
        raise SampleSpaceRidgeError("token batches must have [rows,tokens,hidden]")
    if training.shape[1:] != scope.shape[1:] or training.shape[0] == 0:
        raise SampleSpaceRidgeError("training and scope token batches do not align")
    if not torch.cuda.is_available():
        raise SampleSpaceRidgeError("CUDA token kernel requested without CUDA")
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.cuda.reset_peak_memory_stats()
    started = time.perf_counter()
    scalers = tuple(
        training_scaler_statistics(training[:, offset, :])
        for offset in range(training.shape[1])
    )
    means = np.stack([item.mean for item in scalers])
    scales = np.stack([item.scale for item in scalers])
    mean = torch.as_tensor(means, dtype=torch.float64, device=device)
    scale = torch.as_tensor(scales, dtype=torch.float64, device=device)
    train = torch.as_tensor(
        np.asarray(training, dtype=np.float64, order="C"),
        dtype=torch.float64,
        device=device,
    ).permute(1, 0, 2)
    scope_tensor = torch.as_tensor(
        np.asarray(scope, dtype=np.float64, order="C"),
        dtype=torch.float64,
        device=device,
    ).permute(1, 0, 2)
    train_standardized = (train - mean[:, None, :]) / scale[:, None, :]
    scope_standardized = (scope_tensor - mean[:, None, :]) / scale[:, None, :]
    del train, scope_tensor, mean, scale
    torch.cuda.synchronize(device)
    scaling_seconds = time.perf_counter() - started
    kernel_started = time.perf_counter()
    kernels_device = torch.bmm(scope_standardized, train_standardized.transpose(1, 2))
    torch.cuda.synchronize(device)
    kernel_seconds = time.perf_counter() - kernel_started
    kernels = np.asarray(kernels_device.cpu().numpy(), dtype=np.float64)
    peak = int(torch.cuda.max_memory_allocated())
    del kernels_device, scope_standardized, train_standardized
    torch.cuda.empty_cache()
    return (
        kernels,
        scalers,
        {
            "scaling_seconds": scaling_seconds,
            "kernel_seconds": kernel_seconds,
            "peak_device_memory_bytes": peak,
        },
    )


def cumulative_token_kernel_snapshots(
    token_kernels: Mapping[int, Any],
    ranked_token_indices: Sequence[int],
    candidate_k: Sequence[int],
) -> dict[int, np.ndarray]:
    """Accumulate ranked-token membership kernels at the frozen k boundaries."""

    ranking = tuple(int(value) for value in ranked_token_indices)
    candidates = tuple(int(value) for value in candidate_k)
    if len(set(ranking)) != len(ranking) or any(value < 0 for value in ranking):
        raise SampleSpaceRidgeError(
            "ranked token indices must be unique and nonnegative"
        )
    if tuple(sorted(set(candidates))) != candidates or not candidates:
        raise SampleSpaceRidgeError("candidate k must be unique ascending values")
    if candidates[-1] > len(ranking):
        raise SampleSpaceRidgeError("candidate k exceeds the ranked token count")
    running: np.ndarray | None = None
    snapshots: dict[int, np.ndarray] = {}
    requested = set(candidates)
    for ordinal, token_index in enumerate(ranking, start=1):
        if token_index not in token_kernels:
            raise SampleSpaceRidgeError(f"missing kernel for token {token_index}")
        contribution = np.asarray(token_kernels[token_index], dtype=np.float64)
        if running is None:
            running = np.zeros_like(contribution)
        if contribution.shape != running.shape:
            raise SampleSpaceRidgeError("token kernels have inconsistent shapes")
        running += contribution
        if ordinal in requested:
            snapshots[ordinal] = running.copy()
        if ordinal == candidates[-1]:
            break
    return snapshots
