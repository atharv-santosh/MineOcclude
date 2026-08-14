"""Frozen, outcome-independent analysis mechanics for Regime-A first25."""

from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np

from mineocclude.probes.p7_ridge import ridge_predictions_all_alphas_from_kernel


ALPHAS = (0.1, 1.0, 10.0, 100.0)
K_GRID = (1, 4, 8, 16, 32, 64, 128)
BINS = ("SHORT", "INTERMEDIATE", "LONG", "NEAR_CONTEXT", "BEYOND_CONTEXT")


def canonical_sha256(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw.encode()).hexdigest()


def inner_fold_assignment(
    training_ids: Sequence[str], directions: Mapping[str, str], outer_fold: int
) -> dict[str, int]:
    """Freeze five deterministic, direction-stratified inner folds of four.

    Ordering is SHA256-based and therefore independent of targets and features.
    Each direction is round-robin distributed, with the second direction offset
    by one fold to avoid deterministic pairing artifacts.
    """

    identities = sorted(training_ids)
    if len(identities) != 20 or len(set(identities)) != 20 or set(identities) != set(directions):
        raise ValueError("inner selection requires exactly 20 outer-training identities")
    grouped: dict[str, list[str]] = defaultdict(list)
    for identity in identities:
        grouped[directions[identity]].append(identity)
    if set(grouped) != {"LEFT_TO_RIGHT", "RIGHT_TO_LEFT"}:
        raise ValueError("both frozen motion directions are required")
    result: dict[str, int] = {}
    for offset, direction in enumerate(("LEFT_TO_RIGHT", "RIGHT_TO_LEFT")):
        ordered = sorted(
            grouped[direction],
            key=lambda identity: hashlib.sha256(
                f"REGIME_A_INNER_FOLD_V1|outer={outer_fold}|{identity}".encode()
            ).hexdigest(),
        )
        for index, identity in enumerate(ordered):
            result[identity] = (index + offset) % 5
    counts = np.bincount(list(result.values()), minlength=5)
    if counts.tolist() != [4, 4, 4, 4, 4]:
        # One outer partition has 11/9 direction balance.  A deterministic
        # rotation finds the only needed one-row rebalance without outcomes.
        over = int(np.argmax(counts))
        under = int(np.argmin(counts))
        candidates = sorted(
            [identity for identity, fold in result.items() if fold == over],
            key=lambda identity: hashlib.sha256(
                f"REGIME_A_INNER_REBALANCE_V1|outer={outer_fold}|{identity}".encode()
            ).hexdigest(),
        )
        result[candidates[0]] = under
    if sorted(Counter(result.values()).values()) != [4, 4, 4, 4, 4]:
        raise ValueError("could not create five balanced inner folds")
    return result


# Imported below the function so the public algorithm above remains easy to
# audit as a single outcome-independent block.
from collections import Counter  # noqa: E402


def scalar_metrics(rows: Sequence[Mapping[str, object]], prediction_key: str) -> dict:
    grouped: dict[str, list[Mapping[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["trajectory_id"])].append(row)
    per = {}
    all_y, all_p = [], []
    for identity in sorted(grouped):
        selected = grouped[identity]
        y = np.asarray([float(row["world_x"]) for row in selected], dtype=np.float64)
        p = np.asarray([float(row[prediction_key]) for row in selected], dtype=np.float64)
        if y.size == 0 or not np.isfinite(y).all() or not np.isfinite(p).all():
            raise ValueError("metric rows are empty or non-finite")
        error = y - p
        tss = float(np.sum((y - y.mean()) ** 2))
        if tss <= 0:
            raise ValueError(f"zero trajectory TSS for {identity}")
        per[identity] = {
            "row_count": int(y.size), "sse": float(error @ error), "tss": tss,
            "r2": float(1.0 - (error @ error) / tss),
            "rmse": float(np.sqrt(np.mean(error**2))), "mae": float(np.mean(np.abs(error))),
        }
        all_y.extend(y.tolist())
        all_p.extend(p.tolist())
    y = np.asarray(all_y)
    p = np.asarray(all_p)
    pooled_tss = float(np.sum((y - y.mean()) ** 2))
    return {
        "trajectory_count": len(per), "row_count": int(y.size), "weighting": "unweighted_equal_trajectory",
        "macro_r2": float(np.mean([value["r2"] for value in per.values()])),
        "trajectory_aggregated_rmse": float(np.mean([value["rmse"] for value in per.values()])),
        "trajectory_aggregated_mae": float(np.mean([value["mae"] for value in per.values()])),
        "pooled_row_r2_secondary": float(1.0 - np.sum((y - p) ** 2) / pooled_tss),
        "pooled_rmse_secondary": float(np.sqrt(np.mean((y - p) ** 2))),
        "pooled_mae_secondary": float(np.mean(np.abs(y - p))),
        "per_trajectory": per,
    }


def metrics_by_bin(rows: Sequence[Mapping[str, object]], prediction_key: str) -> dict:
    return {name: scalar_metrics([row for row in rows if row["duration_bin"] == name], prediction_key) for name in BINS}


def choose_alpha(
    validation_predictions: Mapping[float, Mapping[int, float]],
    rows_by_index: Mapping[int, Mapping[str, object]],
) -> tuple[float, dict[str, float]]:
    scores = {}
    for alpha in ALPHAS:
        rows = [dict(rows_by_index[index], _prediction=prediction) for index, prediction in validation_predictions[alpha].items()]
        scores[str(alpha)] = scalar_metrics(rows, "_prediction")["macro_r2"]
    best = min(ALPHAS, key=lambda alpha: (-scores[str(alpha)], alpha))
    return best, scores


def predict_all_alphas(kernel: np.ndarray, training_y: Sequence[float], prediction_count: int) -> dict[float, np.ndarray]:
    n = len(training_y)
    return ridge_predictions_all_alphas_from_kernel(
        kernel, training_y, alphas=ALPHAS,
        prediction_scope_positions=np.arange(n, n + prediction_count, dtype=np.int64),
    )


@dataclass(frozen=True)
class PreparedKernelRidge:
    """One target-independent exact eigensystem reusable by observed/null fits."""

    eigenvalues: np.ndarray
    eigenvectors: np.ndarray
    prediction_kernel: np.ndarray

    @classmethod
    def from_kernel(cls, kernel: np.ndarray, training_row_count: int) -> "PreparedKernelRidge":
        gram = np.asarray(kernel, dtype=np.float64)
        training = gram[:training_row_count]
        training = (training + training.T) * 0.5
        eigenvalues, eigenvectors = np.linalg.eigh(training)
        return cls(eigenvalues, eigenvectors, gram[training_row_count:])

    def predict_all(self, targets: Sequence[float]) -> dict[float, np.ndarray]:
        y = np.asarray(targets, dtype=np.float64)
        if y.ndim != 1 or y.size != self.eigenvalues.size or not np.isfinite(y).all():
            raise ValueError("target vector does not match prepared kernel")
        centered = y - y.mean()
        projected = self.eigenvectors.T @ centered
        return {
            alpha: self.prediction_kernel @ (
                self.eigenvectors @ (projected / (self.eigenvalues + alpha))
            ) + y.mean()
            for alpha in ALPHAS
        }


def full_kernel_cuda(scope_tokens: np.ndarray, training_row_count: int) -> np.ndarray:
    """Use the validated exact float64 summed-token sample-space kernel."""
    from mineocclude.probes.p7a_execution import standardized_token_kernel_sum_cuda

    result = standardized_token_kernel_sum_cuda(scope_tokens, training_row_count=training_row_count)
    return result.kernel


def rank_tokens_cuda(training_tokens: np.ndarray, training_targets: Sequence[float], batch_size: int = 16) -> np.ndarray:
    """Exact A2 absolute max-dimension correlation ranking in bounded CUDA batches."""
    import torch

    tokens = np.asarray(training_tokens)
    y = np.asarray(training_targets, dtype=np.float64)
    if tokens.ndim != 3 or tokens.shape[0] != y.size or tokens.shape[1] < max(K_GRID):
        raise ValueError("malformed token ranking input")
    centered_y = torch.as_tensor(y - y.mean(), dtype=torch.float64, device="cuda:0")
    yss = centered_y @ centered_y
    scores = np.empty(tokens.shape[1], dtype=np.float64)
    for start in range(0, tokens.shape[1], batch_size):
        stop = min(tokens.shape[1], start + batch_size)
        block = torch.as_tensor(np.asarray(tokens[:, start:stop], order="C"), dtype=torch.float64, device="cuda:0")
        block -= block.mean(dim=0, keepdim=True)
        numerator = torch.abs(torch.einsum("nbh,n->bh", block, centered_y))
        denominator = torch.sqrt(torch.sum(block * block, dim=0) * yss)
        correlation = torch.where(denominator > 0, numerator / denominator, torch.zeros_like(numerator))
        scores[start:stop] = correlation.max(dim=1).values.cpu().numpy()
        del block, numerator, denominator, correlation
    del centered_y
    torch.cuda.empty_cache()
    return np.lexsort((np.arange(scores.size), -scores))


def cumulative_selected_token_kernels_cuda(
    scope_tokens: np.ndarray, training_row_count: int, ranked_tokens: Sequence[int]
) -> dict[int, np.ndarray]:
    """Return exact standardized sample kernels for every nested frozen K."""
    import torch

    ranking = np.asarray(ranked_tokens, dtype=np.int64)[: max(K_GRID)]
    selected = np.asarray(scope_tokens[:, ranking, :], order="C")
    tensor = torch.as_tensor(selected, dtype=torch.float64, device="cuda:0")
    train = tensor[:training_row_count]
    mean = train.mean(dim=0, keepdim=True)
    scale = train.std(dim=0, correction=0, keepdim=True)
    scale[scale == 0] = 1.0
    tensor = (tensor - mean) / scale
    # [token, scope, width] @ [token, width, train]
    per_token = torch.bmm(tensor.permute(1, 0, 2), tensor[:training_row_count].permute(1, 2, 0))
    cumulative = torch.cumsum(per_token, dim=0)
    output = {k: np.asarray(cumulative[k - 1].cpu().numpy(), dtype=np.float64) for k in K_GRID}
    del tensor, train, mean, scale, per_token, cumulative
    torch.cuda.empty_cache()
    return output


def bootstrap_intervals(
    overall: Mapping[str, object], bins: Mapping[str, Mapping[str, object]], *, replicates: int, seed: int
) -> dict:
    if replicates != 10000:
        raise ValueError("frozen bootstrap requires exactly 10,000 replicates")
    identities = sorted(overall["per_trajectory"])
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, len(identities), size=(replicates, len(identities)))

    def interval(values: Sequence[float]) -> dict:
        array = np.asarray(values, dtype=np.float64)
        stats = array[draws].mean(axis=1)
        return {"estimate": float(array.mean()), "lower_2_5": float(np.percentile(stats, 2.5)), "upper_97_5": float(np.percentile(stats, 97.5))}

    result = {
        "macro_r2": interval([overall["per_trajectory"][identity]["r2"] for identity in identities]),
        "trajectory_aggregated_rmse": interval([overall["per_trajectory"][identity]["rmse"] for identity in identities]),
        "trajectory_aggregated_mae": interval([overall["per_trajectory"][identity]["mae"] for identity in identities]),
        "bins": {},
    }
    for name in BINS:
        result["bins"][name] = {
            metric: interval([bins[name]["per_trajectory"][identity][metric] for identity in identities])
            for metric in ("r2", "rmse", "mae")
        }
    return result


def screen_metrics(rows: Sequence[Mapping[str, object]]) -> dict:
    component = {}
    for name in ("token_row", "token_col"):
        transformed = [dict(row, world_x=float(row[name]), _prediction=float(row[f"predicted_{name}"])) for row in rows]
        component[name] = scalar_metrics(transformed, "_prediction")
    grouped: dict[str, list[Mapping[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["trajectory_id"])].append(row)
    euclidean_per = {}
    for identity, selected in grouped.items():
        true = np.asarray([[row["token_row"], row["token_col"]] for row in selected], dtype=np.float64)
        pred = np.asarray([[row["predicted_token_row"], row["predicted_token_col"]] for row in selected], dtype=np.float64)
        distance = np.linalg.norm(true - pred, axis=1)
        euclidean_per[identity] = {"rmse": float(np.sqrt(np.mean(distance**2))), "mae": float(np.mean(distance))}
    return {
        "joint_macro_r2": float(np.mean([component[name]["macro_r2"] for name in component])),
        "components": component,
        "trajectory_aggregated_euclidean_rmse_token_cells": float(np.mean([value["rmse"] for value in euclidean_per.values()])),
        "trajectory_aggregated_euclidean_mae_token_cells": float(np.mean([value["mae"] for value in euclidean_per.values()])),
        "per_trajectory_euclidean": euclidean_per,
    }
