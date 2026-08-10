"""Exact bounded execution optimizations layered on frozen P7 semantics.

This module changes scheduling only.  Every token retains its own training-only
scaler, ridge sufficient structure, four-alpha solve, and predictions.  The
P7 transformation and solver authority remains untouched.
"""

from __future__ import annotations

import math
import resource
import time
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any

import numpy as np

from mineocclude.probes.p7_ridge import (
    FeatureSolveResult,
    SampleSpaceRidgeError,
    ridge_predictions_all_alphas_from_features,
)


@dataclass(frozen=True)
class BatchedFeatureSolveResult:
    """Independent exact per-token fits sharing one activation gather."""

    predictions_by_token: tuple[Mapping[float, np.ndarray], ...]
    solve_spaces: tuple[str, ...]
    system_dimensions: tuple[int, ...]
    timings: Mapping[str, float]
    parallelism: int
    peak_host_memory_bytes: int


@dataclass(frozen=True)
class TokenKernelSumResult:
    """One additive kernel for a bounded batch of independently scaled tokens."""

    kernel: np.ndarray
    token_count: int
    constant_feature_count: int
    training_row_count: int
    timings: Mapping[str, float]
    peak_device_memory_bytes: int


@dataclass(frozen=True)
class BatchedCudaFeatureSolveResult:
    """Exact batched float64 CUDA per-token four-alpha fits."""

    predictions_by_token: tuple[Mapping[float, np.ndarray], ...]
    solve_space: str
    system_dimension: int
    timings: Mapping[str, float]
    peak_device_memory_bytes: int


def batched_ridge_predictions_all_alphas_from_features(
    scope_tokens: Any,
    training_targets: Sequence[float],
    *,
    training_row_count: int,
    alphas: Sequence[float],
    prediction_scope_positions: Sequence[int] | None = None,
    parallelism: int = 1,
) -> BatchedFeatureSolveResult:
    """Solve a bounded token batch with one or two exact CPU workers."""

    tokens = np.asarray(scope_tokens)
    if tokens.ndim != 3 or tokens.shape[1] == 0 or tokens.shape[2] == 0:
        raise SampleSpaceRidgeError("scope tokens must have [rows,tokens,hidden]")
    if (
        not isinstance(training_row_count, int)
        or isinstance(training_row_count, bool)
        or not 0 < training_row_count <= tokens.shape[0]
    ):
        raise SampleSpaceRidgeError("training_row_count is invalid")
    if parallelism not in (1, 2):
        raise SampleSpaceRidgeError("bounded token parallelism must be 1 or 2")
    positions = (
        tuple(range(training_row_count, tokens.shape[0]))
        if prediction_scope_positions is None
        else tuple(int(value) for value in prediction_scope_positions)
    )

    def solve(offset: int) -> FeatureSolveResult:
        return ridge_predictions_all_alphas_from_features(
            tokens[:training_row_count, offset, :],
            tokens[:, offset, :],
            training_targets,
            alphas=alphas,
            prediction_scope_positions=positions,
        )

    started = time.perf_counter()
    if parallelism == 1:
        results = tuple(solve(offset) for offset in range(tokens.shape[1]))
    else:
        with ThreadPoolExecutor(max_workers=parallelism) as executor:
            results = tuple(executor.map(solve, range(tokens.shape[1])))
    elapsed = time.perf_counter() - started
    return BatchedFeatureSolveResult(
        predictions_by_token=tuple(item.predictions_by_alpha for item in results),
        solve_spaces=tuple(item.solve_space for item in results),
        system_dimensions=tuple(item.system_dimension for item in results),
        timings={
            "total_seconds": elapsed,
            "seconds_per_token": elapsed / tokens.shape[1],
        },
        parallelism=parallelism,
        peak_host_memory_bytes=int(
            resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
        ),
    )


def standardized_token_kernel_sum_cuda(
    scope_tokens: Any,
    *,
    training_row_count: int,
    device: str = "cuda:0",
) -> TokenKernelSumResult:
    """Build one exact summed Gram matrix for a bounded token batch.

    Flattening independently standardized token features before GEMM is
    algebraically identical to summing individual token kernels.  It retains
    only one scope-by-training matrix, which materially reduces output memory.
    """

    import torch

    tokens = np.asarray(scope_tokens)
    if tokens.ndim != 3 or tokens.shape[1] == 0 or tokens.shape[2] == 0:
        raise SampleSpaceRidgeError("scope tokens must have [rows,tokens,hidden]")
    if (
        not isinstance(training_row_count, int)
        or isinstance(training_row_count, bool)
        or not 0 < training_row_count <= tokens.shape[0]
    ):
        raise SampleSpaceRidgeError("training_row_count is invalid")
    if not torch.cuda.is_available():
        raise SampleSpaceRidgeError("CUDA token kernel requested without CUDA")
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.cuda.reset_peak_memory_stats()

    scaling_started = time.perf_counter()
    training = np.asarray(
        tokens[:training_row_count], dtype=np.float64, order="C"
    ).reshape(training_row_count, -1)
    mean = training.mean(axis=0)
    raw_scale = training.std(axis=0, ddof=0)
    constant = raw_scale == 0.0
    raw_scale[constant] = 1.0
    del training
    matrix = torch.as_tensor(
        np.asarray(tokens, dtype=np.float64, order="C").reshape(tokens.shape[0], -1),
        dtype=torch.float64,
        device=device,
    )
    mean_device = torch.as_tensor(mean, dtype=torch.float64, device=device)
    scale_device = torch.as_tensor(raw_scale, dtype=torch.float64, device=device)
    matrix.sub_(mean_device).div_(scale_device)
    del mean_device, scale_device
    torch.cuda.synchronize(device)
    scaling_seconds = time.perf_counter() - scaling_started

    kernel_started = time.perf_counter()
    kernel_device = matrix @ matrix[:training_row_count].T
    torch.cuda.synchronize(device)
    kernel_seconds = time.perf_counter() - kernel_started
    kernel = np.asarray(kernel_device.cpu().numpy(), dtype=np.float64)
    peak = int(torch.cuda.max_memory_allocated())
    del kernel_device, matrix
    torch.cuda.empty_cache()
    return TokenKernelSumResult(
        kernel=kernel,
        token_count=int(tokens.shape[1]),
        constant_feature_count=int(constant.sum()),
        training_row_count=training_row_count,
        timings={
            "scaling_seconds": scaling_seconds,
            "kernel_seconds": kernel_seconds,
            "total_seconds": scaling_seconds + kernel_seconds,
        },
        peak_device_memory_bytes=peak,
    )


def batched_ridge_predictions_all_alphas_from_features_cuda(
    scope_tokens: Any,
    training_targets: Sequence[float],
    *,
    training_row_count: int,
    alphas: Sequence[float],
    prediction_scope_positions: Sequence[int] | None = None,
    device: str = "cuda:0",
) -> BatchedCudaFeatureSolveResult:
    """Fit multiple independent token models in one bounded CUDA schedule."""

    import torch

    tokens = np.asarray(scope_tokens)
    targets = np.asarray(training_targets, dtype=np.float64)
    alpha_values = tuple(float(value) for value in alphas)
    if tokens.ndim != 3 or tokens.shape[1] == 0 or tokens.shape[2] == 0:
        raise SampleSpaceRidgeError("scope tokens must have [rows,tokens,hidden]")
    if not 0 < training_row_count <= tokens.shape[0]:
        raise SampleSpaceRidgeError("training_row_count is invalid")
    if targets.ndim != 1 or targets.size != training_row_count:
        raise SampleSpaceRidgeError("training targets do not align")
    if not alpha_values or any(
        not math.isfinite(value) or value <= 0.0 for value in alpha_values
    ):
        raise SampleSpaceRidgeError("alphas must be finite and positive")
    if not torch.cuda.is_available():
        raise SampleSpaceRidgeError("CUDA solve requested without CUDA")
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.cuda.reset_peak_memory_stats()

    positions = np.asarray(
        (
            list(range(training_row_count, tokens.shape[0]))
            if prediction_scope_positions is None
            else prediction_scope_positions
        ),
        dtype=np.int64,
    )
    scaling_started = time.perf_counter()
    training = np.asarray(
        tokens[:training_row_count], dtype=np.float64, order="C"
    ).reshape(training_row_count, -1)
    mean = training.mean(axis=0).reshape(tokens.shape[1], tokens.shape[2])
    raw_scale = training.std(axis=0, ddof=0).reshape(tokens.shape[1], tokens.shape[2])
    raw_scale[raw_scale == 0.0] = 1.0
    del training
    matrix = torch.as_tensor(
        np.asarray(tokens, dtype=np.float64, order="C"),
        dtype=torch.float64,
        device=device,
    ).permute(1, 0, 2)
    mean_device = torch.as_tensor(mean, dtype=torch.float64, device=device)
    scale_device = torch.as_tensor(raw_scale, dtype=torch.float64, device=device)
    matrix.sub_(mean_device[:, None, :]).div_(scale_device[:, None, :])
    del mean_device, scale_device
    torch.cuda.synchronize(device)
    scaling_seconds = time.perf_counter() - scaling_started

    build_started = time.perf_counter()
    train = matrix[:, :training_row_count, :]
    centered = torch.as_tensor(
        targets - targets.mean(), dtype=torch.float64, device=device
    )
    if tokens.shape[2] < training_row_count:
        solve_space = "primal"
        sufficient = torch.bmm(train.transpose(1, 2), train)
        rhs = torch.matmul(train.transpose(1, 2), centered)
    else:
        solve_space = "sample"
        sufficient = torch.bmm(train, train.transpose(1, 2))
        rhs = centered.expand(tokens.shape[1], -1)
    torch.cuda.synchronize(device)
    build_seconds = time.perf_counter() - build_started

    solve_started = time.perf_counter()
    identity = torch.eye(sufficient.shape[1], dtype=torch.float64, device=device)
    prediction_matrix = matrix[
        :, torch.as_tensor(positions, dtype=torch.int64, device=device), :
    ]
    predictions: list[dict[float, np.ndarray]] = [{} for _ in range(tokens.shape[1])]
    for alpha in alpha_values:
        solution = torch.linalg.solve(sufficient + alpha * identity, rhs)
        if solve_space == "sample":
            solution = torch.bmm(train.transpose(1, 2), solution[:, :, None]).squeeze(2)
        values = (
            (
                torch.bmm(prediction_matrix, solution[:, :, None]).squeeze(2)
                + targets.mean()
            )
            .cpu()
            .numpy()
        )
        for token_offset in range(tokens.shape[1]):
            predictions[token_offset][alpha] = np.asarray(
                values[token_offset], dtype=np.float64
            )
    torch.cuda.synchronize(device)
    solve_seconds = time.perf_counter() - solve_started
    peak = int(torch.cuda.max_memory_allocated())
    del matrix, sufficient, identity, prediction_matrix, train
    torch.cuda.empty_cache()
    return BatchedCudaFeatureSolveResult(
        predictions_by_token=tuple(predictions),
        solve_space=solve_space,
        system_dimension=int(rhs.shape[1]),
        timings={
            "scaling_seconds": scaling_seconds,
            "sufficient_structure_seconds": build_seconds,
            "four_alpha_solve_predict_seconds": solve_seconds,
            "total_seconds": scaling_seconds + build_seconds + solve_seconds,
            "seconds_per_token": (scaling_seconds + build_seconds + solve_seconds)
            / tokens.shape[1],
        },
        peak_device_memory_bytes=peak,
    )
