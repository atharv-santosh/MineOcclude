"""D5 (EXPLORATORY): training-size / estimator-variance diagnostic.

Reuses ONLY the frozen layer-4 activations of the existing 25 trajectories and
the five original outer held-out sets. Nothing new is collected.

Within each outer fold the 20 training trajectories are subsampled to
N in {5, 10, 15, 20} using deterministic, direction-balanced, SHA256-ordered
subsets. Held-out targets are never changed and never influence standardization,
alpha selection, or token selection.

Readout matches the frozen primary: layer 4, FULL_TOKEN_GRID, per-dimension
standardization on training rows only, sample-space ridge over ALPHAS,
trajectory-equal macro R2, target = world wall-parallel x, rows tau1..15.
"""

from __future__ import annotations

import hashlib
import json
import sys
import time

import numpy as np
import pandas as pd
import torch

sys.path.insert(0, "/home/sagemaker-user/MineOcclude/scripts/postmortem_v0_1")

from pm_common import CONF, OUT, WORK, write_json  # noqa: E402

ALPHAS = (0.1, 1.0, 10.0, 100.0)
K_GRID = (1, 4, 8, 16, 32, 64, 128)
SIZES = (5, 10, 15, 20)
REPLICATES = 5
DEVICE = "cuda:0"
ACT = WORK / "act4"


def load_rows() -> tuple[pd.DataFrame, np.ndarray]:
    """tau1..15 rows in a fixed order, with matching [rows, 336, 2048] tokens."""
    preds = pd.read_parquet(CONF / "slice_predictions.parquet")
    rows = preds[preds["tau"].between(1, 15)].copy()
    rows = rows.sort_values(["trajectory_id", "tau"]).reset_index(drop=True)

    blocks = []
    for traj in sorted(rows["trajectory_id"].unique()):
        array = np.load(ACT / f"{traj}.layer_04.npy", mmap_mode="r")
        # Frozen inventory order is tau = 1..19 -> array rows 0..18.
        blocks.append(np.asarray(array[:15], dtype=np.float16))
    tokens = np.concatenate(blocks, axis=0)
    assert tokens.shape == (375, 336, 2048), tokens.shape
    assert len(rows) == 375
    return rows, tokens


def deterministic_subsets(
    training: list[str], directions: dict[str, str], outer_fold: int, size: int
) -> list[list[str]]:
    """Direction-balanced, outcome-independent subsets frozen by SHA256 ordering."""
    if size >= len(training):
        return [sorted(training)]
    ltr = [t for t in training if directions[t] == "LEFT_TO_RIGHT"]
    rtl = [t for t in training if directions[t] == "RIGHT_TO_LEFT"]
    n_ltr = size // 2 + (size % 2)
    n_rtl = size - n_ltr
    n_ltr, n_rtl = min(n_ltr, len(ltr)), min(n_rtl, len(rtl))
    while n_ltr + n_rtl < size:
        if n_ltr < len(ltr):
            n_ltr += 1
        else:
            n_rtl += 1

    out = []
    for rep in range(REPLICATES):
        def order(pool: list[str]) -> list[str]:
            return sorted(
                pool,
                key=lambda t: hashlib.sha256(
                    f"REGIME_A_PM_D5_V1|outer={outer_fold}|size={size}|rep={rep}|{t}".encode()
                ).hexdigest(),
            )

        out.append(sorted(order(ltr)[:n_ltr] + order(rtl)[:n_rtl]))
    # Distinct subsets only, order preserved.
    seen, unique = set(), []
    for subset in out:
        key = tuple(subset)
        if key not in seen:
            seen.add(key)
            unique.append(subset)
    return unique


def standardized_matrix(tokens: np.ndarray, train_idx: np.ndarray, scope_idx: np.ndarray):
    """Flatten -> standardize on training rows -> float64 GPU matrix.

    Algebraically identical to the frozen summed-token kernel
    (src/mineocclude/probes/p7a_execution.py :: standardized_token_kernel_sum_cuda).
    """
    scope = np.asarray(tokens[scope_idx], dtype=np.float64, order="C").reshape(
        len(scope_idx), -1
    )
    position = {int(g): i for i, g in enumerate(scope_idx)}
    train_pos = np.array([position[int(t)] for t in train_idx], dtype=np.int64)
    train = scope[train_pos]
    mean = train.mean(axis=0)
    scale = train.std(axis=0, ddof=0)
    scale[scale == 0.0] = 1.0
    matrix = torch.as_tensor(scope, dtype=torch.float64, device=DEVICE)
    matrix.sub_(torch.as_tensor(mean, dtype=torch.float64, device=DEVICE))
    matrix.div_(torch.as_tensor(scale, dtype=torch.float64, device=DEVICE))
    return matrix, train_pos


def ridge_predict(gram_tt: torch.Tensor, gram_pt: torch.Tensor, y: np.ndarray):
    """Sample-space ridge predictions for every frozen alpha."""
    symmetric = (gram_tt + gram_tt.T) * 0.5
    eigenvalues, eigenvectors = torch.linalg.eigh(symmetric)
    target = torch.as_tensor(y, dtype=torch.float64, device=DEVICE)
    mean = target.mean()
    projected = eigenvectors.T @ (target - mean)
    out = {}
    for alpha in ALPHAS:
        weights = eigenvectors @ (projected / (eigenvalues + alpha))
        out[alpha] = (gram_pt @ weights + mean).cpu().numpy()
    return out


def macro_r2(y: np.ndarray, pred: np.ndarray, groups: np.ndarray) -> float:
    scores = []
    for g in np.unique(groups):
        m = groups == g
        yy, pp = y[m], pred[m]
        tss = float(((yy - yy.mean()) ** 2).sum())
        if tss <= 0:
            continue
        scores.append(1.0 - float(((yy - pp) ** 2).sum()) / tss)
    return float(np.mean(scores))


def select_alpha_inner(matrix, train_pos, y_train, traj_train) -> float:
    """Leave-one-trajectory-out alpha selection inside the training subset only."""
    unique = list(dict.fromkeys(traj_train))
    scores = {a: [] for a in ALPHAS}
    for held in unique:
        mask = traj_train != held
        if mask.sum() < 2 or (~mask).sum() == 0:
            continue
        inner_pos = train_pos[mask]
        outer_pos = train_pos[~mask]
        gram_tt = matrix[inner_pos] @ matrix[inner_pos].T
        gram_pt = matrix[outer_pos] @ matrix[inner_pos].T
        preds = ridge_predict(gram_tt, gram_pt, y_train[mask])
        yy = y_train[~mask]
        tss = float(((yy - yy.mean()) ** 2).sum())
        if tss <= 0:
            continue
        for alpha in ALPHAS:
            scores[alpha].append(1.0 - float(((yy - preds[alpha]) ** 2).sum()) / tss)
    means = {a: (float(np.mean(v)) if v else -np.inf) for a, v in scores.items()}
    return min(ALPHAS, key=lambda a: (-means[a], a))


def rank_tokens(matrix_tokens: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Frozen A2 absolute max-dimension correlation ranking, training rows only."""
    centered_y = torch.as_tensor(y - y.mean(), dtype=torch.float64, device=DEVICE)
    yss = centered_y @ centered_y
    scores = np.empty(matrix_tokens.shape[1], dtype=np.float64)
    for start in range(0, matrix_tokens.shape[1], 16):
        stop = min(matrix_tokens.shape[1], start + 16)
        block = torch.as_tensor(
            np.asarray(matrix_tokens[:, start:stop], dtype=np.float64, order="C"),
            device=DEVICE,
        )
        block -= block.mean(dim=0, keepdim=True)
        numerator = torch.abs(torch.einsum("nbh,n->bh", block, centered_y))
        denominator = torch.sqrt(torch.sum(block * block, dim=0) * yss)
        corr = torch.where(
            denominator > 0, numerator / denominator, torch.zeros_like(numerator)
        )
        scores[start:stop] = corr.max(dim=1).values.cpu().numpy()
        del block, numerator, denominator, corr
    torch.cuda.empty_cache()
    return np.lexsort((np.arange(scores.size), -scores))


def main() -> int:
    started = time.perf_counter()
    rows, tokens = load_rows()
    y_all = rows["world_x"].to_numpy(np.float64)
    traj_all = rows["trajectory_id"].to_numpy()
    fold_all = rows["outer_fold"].to_numpy()
    directions = dict(
        rows[["trajectory_id", "direction"]].drop_duplicates().itertuples(
            index=False, name=None
        )
    )
    all_traj = sorted(set(traj_all))

    results = []
    for size in SIZES:
        for fold in sorted(set(fold_all)):
            held = sorted({t for t in all_traj if fold_all[traj_all == t][0] == fold})
            training_pool = [t for t in all_traj if t not in held]
            subsets = deterministic_subsets(training_pool, directions, int(fold), size)

            for rep, subset in enumerate(subsets):
                train_mask = np.isin(traj_all, subset)
                held_mask = np.isin(traj_all, held)
                train_idx = np.flatnonzero(train_mask)
                held_idx = np.flatnonzero(held_mask)
                scope_idx = np.concatenate([train_idx, held_idx])

                matrix, train_pos = standardized_matrix(tokens, train_idx, scope_idx)
                held_pos = np.arange(len(train_idx), len(scope_idx))
                y_train = y_all[train_idx]
                traj_train = traj_all[train_idx]

                alpha = select_alpha_inner(matrix, train_pos, y_train, traj_train)
                gram_tt = matrix[train_pos] @ matrix[train_pos].T
                gram_pt = matrix[held_pos] @ matrix[train_pos].T
                pred = ridge_predict(gram_tt, gram_pt, y_train)[alpha]

                y_held = y_all[held_idx]
                g_held = traj_all[held_idx]
                record = {
                    "readout": "FULL",
                    "n_train": size,
                    "outer_fold": int(fold),
                    "replicate": rep,
                    "subset": subset,
                    "alpha": alpha,
                    "macro_r2": macro_r2(y_held, pred, g_held),
                    "rmse": float(np.sqrt(((y_held - pred) ** 2).mean())),
                    "mae": float(np.abs(y_held - pred).mean()),
                }
                results.append(record)

                # --- BEST-K on the same subset, selection training-only ---
                ranked = rank_tokens(tokens[train_idx], y_train)
                sel = ranked[: max(K_GRID)]
                sub_tokens = np.asarray(tokens[scope_idx][:, sel, :], order="C")
                sub_scope = np.asarray(sub_tokens, dtype=np.float64).reshape(
                    len(scope_idx), max(K_GRID), 2048
                )
                train_block = sub_scope[np.arange(len(train_idx))]
                mean = train_block.mean(axis=0, keepdims=True)
                scale = train_block.std(axis=0, ddof=0, keepdims=True)
                scale[scale == 0.0] = 1.0
                std_tokens = torch.as_tensor(
                    (sub_scope - mean) / scale, dtype=torch.float64, device=DEVICE
                )
                per_token = torch.bmm(
                    std_tokens.permute(1, 0, 2),
                    std_tokens[: len(train_idx)].permute(1, 2, 0),
                )
                cumulative = torch.cumsum(per_token, dim=0)

                best = None
                for k in K_GRID:
                    gram_k = cumulative[k - 1]
                    tt = gram_k[: len(train_idx)]
                    inner_scores = []
                    for h in dict.fromkeys(traj_train):
                        m = traj_train != h
                        if m.sum() < 2:
                            continue
                        preds_k = ridge_predict(
                            tt[np.ix_(m, m)], tt[np.ix_(~m, m)], y_train[m]
                        )
                        yy = y_train[~m]
                        tss = float(((yy - yy.mean()) ** 2).sum())
                        if tss <= 0:
                            continue
                        inner_scores.append(
                            {
                                a: 1.0 - float(((yy - preds_k[a]) ** 2).sum()) / tss
                                for a in ALPHAS
                            }
                        )
                    if not inner_scores:
                        continue
                    for a in ALPHAS:
                        score = float(np.mean([s[a] for s in inner_scores]))
                        if best is None or score > best[0]:
                            best = (score, k, a)
                if best is not None:
                    _, k_best, a_best = best
                    gram_k = cumulative[k_best - 1]
                    pred_k = ridge_predict(
                        gram_k[: len(train_idx)], gram_k[len(train_idx):], y_train
                    )[a_best]
                    results.append(
                        {
                            "readout": "BEST_K",
                            "n_train": size,
                            "outer_fold": int(fold),
                            "replicate": rep,
                            "subset": subset,
                            "alpha": a_best,
                            "k": k_best,
                            "macro_r2": macro_r2(y_held, pred_k, g_held),
                            "rmse": float(np.sqrt(((y_held - pred_k) ** 2).mean())),
                            "mae": float(np.abs(y_held - pred_k).mean()),
                        }
                    )
                del matrix, gram_tt, gram_pt, std_tokens, per_token, cumulative
                torch.cuda.empty_cache()

            print(f"  size={size} fold={fold} subsets={len(subsets)} "
                  f"elapsed={time.perf_counter()-started:.0f}s", flush=True)

    frame = pd.DataFrame(results)
    curve = {}
    for readout in ("FULL", "BEST_K"):
        sub = frame[frame["readout"] == readout]
        curve[readout] = {}
        for size in SIZES:
            block = sub[sub["n_train"] == size]
            if block.empty:
                continue
            per_fold = block.groupby("outer_fold")["macro_r2"].mean()
            entry = {
                "n_train": size,
                "n_fits": int(len(block)),
                "mean_macro_r2": float(block["macro_r2"].mean()),
                "sd_macro_r2_across_fits": float(block["macro_r2"].std(ddof=0)),
                "min_macro_r2": float(block["macro_r2"].min()),
                "max_macro_r2": float(block["macro_r2"].max()),
                "mean_rmse_blocks": float(block["rmse"].mean()),
                "mean_mae_blocks": float(block["mae"].mean()),
                "mean_of_fold_means": float(per_fold.mean()),
                "alphas_selected": sorted(block["alpha"].unique().tolist()),
            }
            if readout == "BEST_K":
                entry["k_values_selected"] = sorted(block["k"].unique().tolist())
                entry["k_value_counts"] = {
                    str(k): int(v) for k, v in block["k"].value_counts().items()
                }
            curve[readout][str(size)] = entry

    payload = {
        "artifact_id": "regime-a-postmortem-d5-learning-curve-v0.1",
        "status": "EXPLORATORY",
        "design": {
            "held_out_sets": "original five outer trajectory folds, unchanged",
            "training_subsets": "deterministic SHA256-ordered, direction-balanced",
            "sizes": list(SIZES),
            "replicates_requested": REPLICATES,
            "alpha_grid": list(ALPHAS),
            "k_grid": list(K_GRID),
            "alpha_and_k_selection": (
                "leave-one-trajectory-out inside the training subset only; "
                "held-out trajectories never influence standardization, alpha, or "
                "token selection"
            ),
            "readout": "layer 4, FULL_TOKEN_GRID and BEST_K, tau1..15, world x",
            "deviation_from_frozen_pipeline": (
                "The frozen run used five fixed inner folds of four, which is defined "
                "only for exactly 20 training trajectories. D5 substitutes inner "
                "leave-one-trajectory-out so a single scheme applies at every subset "
                "size. Both are training-only."
            ),
        },
        "learning_curve": curve,
        "fits": results,
        "runtime_seconds": time.perf_counter() - started,
    }
    digest = write_json(OUT / "d5_learning_curve.json", payload)

    print()
    for readout in ("FULL", "BEST_K"):
        print(f"=== D5 {readout} ===")
        print(f"{'N':>4s} {'fits':>5s} {'meanR2':>9s} {'sd':>8s} {'min':>9s} "
              f"{'max':>9s} {'RMSE':>7s}")
        for size in SIZES:
            e = curve[readout].get(str(size))
            if not e:
                continue
            print(f"{e['n_train']:4d} {e['n_fits']:5d} {e['mean_macro_r2']:9.4f} "
                  f"{e['sd_macro_r2_across_fits']:8.4f} {e['min_macro_r2']:9.4f} "
                  f"{e['max_macro_r2']:9.4f} {e['mean_rmse_blocks']:7.4f}")
        print()
    print("  sha256:", digest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
