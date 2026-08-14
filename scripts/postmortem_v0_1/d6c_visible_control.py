"""D6 step D (EXPLORATORY): decode the matched visible-sheep positive control.

Applies the SAME readout the confirmatory primary used - layer 4,
FULL_TOKEN_GRID, per-dimension standardization on outer-training rows only,
sample-space ridge over the frozen alpha grid, the five original outer
trajectory folds, trajectory-equal macro R2, world wall-parallel x - to
activations captured while the sheep was genuinely VISIBLE.

Question: can this readout/geometry decode the sheep at all?

A matched-span descriptive comparator is also computed: the frozen HIDDEN
predictions restricted to the last 8 taus (tau 8..15), so the visible and hidden
numbers are compared over the same number of rows per trajectory.
"""

from __future__ import annotations

import json
import sys
import time

import numpy as np
import pandas as pd
import torch

sys.path.insert(0, "/home/sagemaker-user/MineOcclude/scripts/postmortem_v0_1")

from pm_common import CONF, OUT, WORK, write_json  # noqa: E402
from d5_learning_curve import (  # noqa: E402
    ALPHAS,
    K_GRID,
    macro_r2,
    rank_tokens,
    ridge_predict,
    select_alpha_inner,
    standardized_matrix,
)

ACT = WORK / "d6_activations"
DEVICE = "cuda:0"
BOOTSTRAP = 10000
BOOTSTRAP_SEED = 20260814


def bootstrap_ci(values: list[float], seed: int = BOOTSTRAP_SEED) -> dict:
    array = np.asarray(values, dtype=np.float64)
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, array.size, size=(BOOTSTRAP, array.size))
    stats = array[draws].mean(axis=1)
    return {
        "estimate": float(array.mean()),
        "lower_2_5": float(np.percentile(stats, 2.5)),
        "upper_97_5": float(np.percentile(stats, 97.5)),
        "replicates": BOOTSTRAP,
        "resampled_unit": "trajectory",
    }


def evaluate(rows: pd.DataFrame, tokens: np.ndarray) -> dict:
    y_all = rows["world_x"].to_numpy(np.float64)
    traj_all = rows["trajectory_id"].to_numpy()
    fold_all = rows["outer_fold"].to_numpy()
    all_traj = sorted(set(traj_all))

    predictions = {"FULL": np.full(len(rows), np.nan), "BEST_K": np.full(len(rows), np.nan)}
    per_fold = {}

    for fold in sorted(set(fold_all)):
        held = sorted({t for t in all_traj if fold_all[traj_all == t][0] == fold})
        train = [t for t in all_traj if t not in held]
        train_idx = np.flatnonzero(np.isin(traj_all, train))
        held_idx = np.flatnonzero(np.isin(traj_all, held))
        scope_idx = np.concatenate([train_idx, held_idx])

        matrix, train_pos = standardized_matrix(tokens, train_idx, scope_idx)
        held_pos = np.arange(len(train_idx), len(scope_idx))
        y_train = y_all[train_idx]
        traj_train = traj_all[train_idx]

        alpha = select_alpha_inner(matrix, train_pos, y_train, traj_train)
        gram_tt = matrix[train_pos] @ matrix[train_pos].T
        gram_pt = matrix[held_pos] @ matrix[train_pos].T
        pred_full = ridge_predict(gram_tt, gram_pt, y_train)[alpha]
        predictions["FULL"][held_idx] = pred_full

        # BEST-K, selection strictly training-only.
        ranked = rank_tokens(tokens[train_idx], y_train)
        sel = ranked[: max(K_GRID)]
        sub = np.asarray(tokens[scope_idx][:, sel, :], dtype=np.float64)
        train_block = sub[: len(train_idx)]
        mean = train_block.mean(axis=0, keepdims=True)
        scale = train_block.std(axis=0, ddof=0, keepdims=True)
        scale[scale == 0.0] = 1.0
        std_tokens = torch.as_tensor((sub - mean) / scale, dtype=torch.float64, device=DEVICE)
        per_token = torch.bmm(
            std_tokens.permute(1, 0, 2), std_tokens[: len(train_idx)].permute(1, 2, 0)
        )
        cumulative = torch.cumsum(per_token, dim=0)

        best = None
        for k in K_GRID:
            tt = cumulative[k - 1][: len(train_idx)]
            scores = []
            for h in dict.fromkeys(traj_train):
                m = traj_train != h
                if m.sum() < 2:
                    continue
                preds_k = ridge_predict(tt[np.ix_(m, m)], tt[np.ix_(~m, m)], y_train[m])
                yy = y_train[~m]
                tss = float(((yy - yy.mean()) ** 2).sum())
                if tss <= 0:
                    continue
                scores.append({a: 1.0 - float(((yy - preds_k[a]) ** 2).sum()) / tss for a in ALPHAS})
            if not scores:
                continue
            for a in ALPHAS:
                value = float(np.mean([s[a] for s in scores]))
                if best is None or value > best[0]:
                    best = (value, k, a)
        _, k_best, a_best = best
        gram_k = cumulative[k_best - 1]
        pred_k = ridge_predict(gram_k[: len(train_idx)], gram_k[len(train_idx):], y_train)[a_best]
        predictions["BEST_K"][held_idx] = pred_k

        per_fold[str(int(fold))] = {
            "held_out": held,
            "alpha_full": alpha,
            "alpha_best_k": a_best,
            "k_best": int(k_best),
            "macro_r2_full": macro_r2(y_all[held_idx], pred_full, traj_all[held_idx]),
            "macro_r2_best_k": macro_r2(y_all[held_idx], pred_k, traj_all[held_idx]),
            "rmse_full": float(np.sqrt(((y_all[held_idx] - pred_full) ** 2).mean())),
            "rmse_best_k": float(np.sqrt(((y_all[held_idx] - pred_k) ** 2).mean())),
        }
        del matrix, gram_tt, gram_pt, std_tokens, per_token, cumulative
        torch.cuda.empty_cache()

    out = {"per_fold": per_fold}
    for name, pred in predictions.items():
        assert np.isfinite(pred).all()
        per_traj = {}
        for traj in all_traj:
            m = traj_all == traj
            yy, pp = y_all[m], pred[m]
            tss = float(((yy - yy.mean()) ** 2).sum())
            per_traj[traj] = {
                "rows": int(m.sum()),
                "r2": 1.0 - float(((yy - pp) ** 2).sum()) / tss,
                "rmse": float(np.sqrt(((yy - pp) ** 2).mean())),
                "mae": float(np.abs(yy - pp).mean()),
                "tss": tss,
                "target_sd_blocks": float(yy.std(ddof=0)),
                "target_range_blocks": float(yy.max() - yy.min()),
            }
        r2s = [v["r2"] for v in per_traj.values()]
        out[name] = {
            "macro_r2": float(np.mean(r2s)),
            "pooled_row_r2_secondary": float(
                1.0 - ((y_all - pred) ** 2).sum() / ((y_all - y_all.mean()) ** 2).sum()
            ),
            "trajectory_aggregated_rmse": float(
                np.mean([v["rmse"] for v in per_traj.values()])
            ),
            "trajectory_aggregated_mae": float(
                np.mean([v["mae"] for v in per_traj.values()])
            ),
            "pooled_rmse": float(np.sqrt(((y_all - pred) ** 2).mean())),
            "n_trajectories_positive_r2": int(sum(r > 0 for r in r2s)),
            "bootstrap_macro_r2": bootstrap_ci(r2s),
            "mean_target_sd_blocks": float(
                np.mean([v["target_sd_blocks"] for v in per_traj.values()])
            ),
            "mean_target_range_blocks": float(
                np.mean([v["target_range_blocks"] for v in per_traj.values()])
            ),
            "per_trajectory": per_traj,
        }
    return out


def main() -> int:
    started = time.perf_counter()
    manifest = json.loads((OUT / "visible_positive_control_manifest.json").read_text())
    rows = pd.DataFrame(manifest["rows"]).sort_values(
        ["trajectory_id", "visible_index"]
    ).reset_index(drop=True)

    blocks = []
    for traj in sorted(rows["trajectory_id"].unique()):
        array = np.load(ACT / f"{traj}.visible.layer_04.npy")
        blocks.append(np.asarray(array, dtype=np.float16))
    tokens = np.concatenate(blocks, axis=0)
    assert tokens.shape[0] == len(rows), (tokens.shape, len(rows))
    print("visible tokens", tokens.shape, flush=True)

    visible = evaluate(rows, tokens)

    # Matched-span descriptive comparator on the frozen hidden predictions.
    preds = pd.read_parquet(CONF / "slice_predictions.parquet")
    length = int(manifest["visible_rows_per_trajectory"])
    matched = preds[preds["tau"].between(16 - length, 15)]
    comparator = {}
    for name, column in (("FULL", "predicted_layer4_full"), ("BEST_K", "predicted_layer4_best_k")):
        r2s, sds = [], []
        for traj, group in matched.groupby("trajectory_id"):
            y = group["world_x"].to_numpy(np.float64)
            p = group[column].to_numpy(np.float64)
            tss = float(((y - y.mean()) ** 2).sum())
            r2s.append(1.0 - float(((y - p) ** 2).sum()) / tss)
            sds.append(float(y.std(ddof=0)))
        comparator[name] = {
            "macro_r2": float(np.mean(r2s)),
            "rows_per_trajectory": length,
            "tau_window": [16 - length, 15],
            "mean_target_sd_blocks": float(np.mean(sds)),
            "n_trajectories_positive_r2": int(sum(r > 0 for r in r2s)),
        }

    payload = {
        "artifact_id": "regime-a-postmortem-d6-visible-positive-control-v0.1",
        "status": "EXPLORATORY_VISIBLE_POSITIVE_CONTROL",
        "question": (
            "Can the same layer-4 FULL_TOKEN_GRID readout, in the same Regime-A "
            "geometry with the same checkpoint and the same grouped trajectory "
            "evaluation, decode the sheep while it is genuinely visible?"
        ),
        "matched_to_confirmatory": {
            "layer": 4,
            "readout": "FULL_TOKEN_GRID and BEST_K",
            "target": "WORLD_WALL_PARALLEL_X",
            "outer_folds": "original five trajectory-grouped folds",
            "standardization": "outer-training rows only",
            "alpha_grid": list(ALPHAS),
            "k_grid": list(K_GRID),
            "metric": "trajectory-equal macro R2",
            "checkpoint": "same qualified 700M 16f checkpoint",
            "camera_and_captures": "same immutable Regime-A captures",
        },
        "rows_per_trajectory": length,
        "total_rows": int(len(rows)),
        "visible_control": visible,
        "matched_span_hidden_comparator": comparator,
        "comparator_note": (
            "The visible window is 8 rows per trajectory (limited by the full "
            "16-frame context requirement), against 15 for the confirmatory primary. "
            "The comparator restricts the FROZEN hidden predictions to the same "
            "number of rows so the visible/hidden contrast is not confounded by "
            "window length. It is descriptive and does not re-adjudicate Regime A."
        ),
        "runtime_seconds": time.perf_counter() - started,
    }
    digest = write_json(OUT / "d6_visible_positive_control.json", payload)

    print("=== D6 VISIBLE positive control ===")
    for name in ("FULL", "BEST_K"):
        v = visible[name]
        print(f"  {name:7s} macroR2={v['macro_r2']:+.4f}  pooled={v['pooled_row_r2_secondary']:+.4f}  "
              f"RMSE={v['trajectory_aggregated_rmse']:.4f}  MAE={v['trajectory_aggregated_mae']:.4f}  "
              f"pos={v['n_trajectories_positive_r2']}/25  "
              f"CI=[{v['bootstrap_macro_r2']['lower_2_5']:+.4f},{v['bootstrap_macro_r2']['upper_97_5']:+.4f}]")
    print()
    print("=== matched-span HIDDEN comparator (frozen preds, tau 8..15) ===")
    for name in ("FULL", "BEST_K"):
        c = comparator[name]
        print(f"  {name:7s} macroR2={c['macro_r2']:+.4f}  pos={c['n_trajectories_positive_r2']}/25  "
              f"meanSD={c['mean_target_sd_blocks']:.4f}")
    print()
    print("=== per fold (visible) ===")
    for fold, f in sorted(visible["per_fold"].items()):
        print(f"  fold {fold}: FULL={f['macro_r2_full']:+.4f} BEST_K={f['macro_r2_best_k']:+.4f} "
              f"alpha={f['alpha_full']} k={f['k_best']}")
    print("  sha256:", digest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
