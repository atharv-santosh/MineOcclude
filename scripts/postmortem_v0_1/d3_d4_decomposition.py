"""D3 + D4 (EXPLORATORY): trajectory offset/motion decomposition and bin breakdown.

Uses ONLY the frozen out-of-fold predictions in slice_predictions.parquet.
No model is refit. No per-bin model is fit.

D3's mean-centering is an ORACLE descriptive decomposition: it subtracts the
held-out trajectory's own mean from both target and prediction. It is NOT an
operational decoder, NOT a replacement metric, and may NOT rescue Regime A.
"""

from __future__ import annotations

import json
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "/home/sagemaker-user/MineOcclude/scripts/postmortem_v0_1")

from pm_common import ALL_BINS, CONF, OUT, write_json  # noqa: E402

try:
    from scipy import stats as scipy_stats
except ImportError:  # pragma: no cover
    scipy_stats = None


def decompose(rows: pd.DataFrame, pred_col: str) -> dict:
    per_traj = []
    for traj, group in rows.groupby("trajectory_id", sort=True):
        group = group.sort_values("tau")
        y = group["world_x"].to_numpy(np.float64)
        yhat = group[pred_col].to_numpy(np.float64)
        n = len(y)

        tss = float(((y - y.mean()) ** 2).sum())
        sse = float(((y - yhat) ** 2).sum())
        slope, intercept = np.polyfit(y, yhat, 1)
        pearson = float(np.corrcoef(y, yhat)[0, 1])
        spearman = (
            float(scipy_stats.spearmanr(y, yhat).statistic)
            if scipy_stats is not None
            else None
        )

        yc = y - y.mean()
        yhc = yhat - yhat.mean()
        sse_c = float(((yc - yhc) ** 2).sum())

        per_traj.append(
            {
                "trajectory_id": traj,
                "direction": str(group["direction"].iloc[0]),
                "outer_fold": int(group["outer_fold"].iloc[0]),
                "n_rows": n,
                "target_mean": float(y.mean()),
                "prediction_mean": float(yhat.mean()),
                "signed_mean_bias": float(yhat.mean() - y.mean()),
                "absolute_mean_bias": float(abs(yhat.mean() - y.mean())),
                "ols_slope_yhat_on_y": float(slope),
                "ols_intercept": float(intercept),
                "pearson_r": pearson,
                "spearman_r": spearman,
                "trajectory_r2": 1.0 - sse / tss,
                "rmse_blocks": float(np.sqrt(sse / n)),
                "mae_blocks": float(np.abs(y - yhat).mean()),
                "target_tss": tss,
                "centered_rmse_blocks": float(np.sqrt(sse_c / n)),
                "centered_mae_blocks": float(np.abs(yc - yhc).mean()),
                "centered_r2": 1.0 - sse_c / tss,
                "centered_pearson_r": pearson,  # centering does not change correlation
                "bias_share_of_sse": float((sse - sse_c) / sse) if sse > 0 else None,
            }
        )

    def col(name: str) -> np.ndarray:
        return np.array(
            [r[name] for r in per_traj if r[name] is not None], dtype=np.float64
        )

    return {
        "macro_r2": float(col("trajectory_r2").mean()),
        "macro_centered_r2": float(col("centered_r2").mean()),
        "macro_rmse_blocks": float(col("rmse_blocks").mean()),
        "macro_centered_rmse_blocks": float(col("centered_rmse_blocks").mean()),
        "macro_mae_blocks": float(col("mae_blocks").mean()),
        "macro_centered_mae_blocks": float(col("centered_mae_blocks").mean()),
        "mean_signed_bias": float(col("signed_mean_bias").mean()),
        "mean_absolute_bias": float(col("absolute_mean_bias").mean()),
        "median_absolute_bias": float(np.median(col("absolute_mean_bias"))),
        "max_absolute_bias": float(col("absolute_mean_bias").max()),
        "mean_ols_slope": float(col("ols_slope_yhat_on_y").mean()),
        "median_ols_slope": float(np.median(col("ols_slope_yhat_on_y"))),
        "min_ols_slope": float(col("ols_slope_yhat_on_y").min()),
        "max_ols_slope": float(col("ols_slope_yhat_on_y").max()),
        "n_trajectories_with_positive_slope": int((col("ols_slope_yhat_on_y") > 0).sum()),
        "mean_pearson_r": float(col("pearson_r").mean()),
        "median_pearson_r": float(np.median(col("pearson_r"))),
        "min_pearson_r": float(col("pearson_r").min()),
        "n_trajectories_with_positive_pearson": int((col("pearson_r") > 0).sum()),
        "mean_spearman_r": (
            float(col("spearman_r").mean()) if scipy_stats is not None else None
        ),
        "n_trajectories_with_positive_centered_r2": int((col("centered_r2") > 0).sum()),
        "mean_bias_share_of_sse": float(col("bias_share_of_sse").mean()),
        "per_trajectory": per_traj,
    }


def main() -> int:
    preds = pd.read_parquet(CONF / "slice_predictions.parquet")
    rows = preds[preds["tau"].between(1, 15)].copy()
    assert len(rows) == 375

    full = decompose(rows, "predicted_layer4_full")
    best_k = decompose(rows, "predicted_layer4_best_k")

    d3 = {
        "artifact_id": "regime-a-postmortem-d3-prediction-decomposition-v0.1",
        "status": "EXPLORATORY",
        "domain": "tau1..15, frozen out-of-fold predictions, no refit",
        "oracle_centering_disclaimer": (
            "Mean-centering uses the held-out trajectory's own target mean. It is an "
            "ORACLE descriptive decomposition used solely to ask whether the frozen "
            "prediction tracked within-trajectory motion once a trajectory-specific "
            "offset is removed. It is not an operational decoder, is not a "
            "replacement metric, and does not and may not rescue Regime A."
        ),
        "layer4_FULL": full,
        "layer4_BEST_K": best_k,
    }
    d3_hash = write_json(OUT / "d3_prediction_decomposition.json", d3)

    # ---------------- D4 ----------------
    d2 = pd.read_parquet(OUT / "d2_context_visibility.parquet")
    ctx = d2.set_index(["trajectory_id", "tau"])

    all_rows = preds.copy()
    per_bin = {}
    for bin_name in ALL_BINS:
        sub = all_rows[all_rows["duration_bin"] == bin_name]
        y = sub["world_x"].to_numpy(np.float64)
        yhat = sub["predicted_layer4_full"].to_numpy(np.float64)
        yhat_bk = sub["predicted_layer4_best_k"].to_numpy(np.float64)

        # Within-trajectory target spread inside this bin (equal-trajectory mean).
        sds, ranges = [], []
        for _, g in sub.groupby("trajectory_id"):
            v = g["world_x"].to_numpy(np.float64)
            sds.append(float(v.std(ddof=0)))
            ranges.append(float(v.max() - v.min()))

        ctx_sub = ctx.loc[list(zip(sub["trajectory_id"], sub["tau"]))]
        rmse = float(np.sqrt(((y - yhat) ** 2).mean()))
        mean_sd = float(np.mean(sds))

        per_bin[bin_name] = {
            "rows": int(len(sub)),
            "tau_range": [int(sub["tau"].min()), int(sub["tau"].max())],
            "mean_within_trajectory_target_sd_blocks": mean_sd,
            "mean_within_trajectory_target_range_blocks": float(np.mean(ranges)),
            "pooled_target_sd_blocks": float(y.std(ddof=0)),
            "full_rmse_blocks": rmse,
            "full_mae_blocks": float(np.abs(y - yhat).mean()),
            "full_normalized_rmse_over_within_traj_sd": (
                rmse / mean_sd if mean_sd > 0 else None
            ),
            "full_signed_bias_blocks": float((yhat - y).mean()),
            "full_pearson_r_pooled": float(np.corrcoef(y, yhat)[0, 1]),
            "best_k_rmse_blocks": float(np.sqrt(((y - yhat_bk) ** 2).mean())),
            "best_k_mae_blocks": float(np.abs(y - yhat_bk).mean()),
            "context_evidence": {
                "median_rendered_evidence_frames": float(
                    ctx_sub["n_rendered_pixel_evidence"].median()
                ),
                "median_clean_visible_frames": float(
                    ctx_sub["n_clean_visible"].median()
                ),
                "pct_rows_with_clean_visible": float(
                    100.0 * ctx_sub["any_clean_visible"].mean()
                ),
                "pct_rows_with_rendered_evidence": float(
                    100.0 * ctx_sub["any_rendered_pixel_evidence"].mean()
                ),
                "median_max_context_magenta_pixels": float(
                    ctx_sub["max_context_magenta_pixels"].median()
                ),
            },
            "correlation_meaningfulness_caveat": (
                "NEAR_CONTEXT contributes only 3 rows per trajectory and every bin has "
                "very small within-trajectory TSS; pooled correlation here is dominated "
                "by between-trajectory spread and per-bin R2 is not reported."
            ),
        }

    d4 = {
        "artifact_id": "regime-a-postmortem-d4-bin-decomposition-v0.1",
        "status": "EXPLORATORY",
        "method": "descriptive breakdown of frozen OOF predictions; no per-bin refit",
        "per_bin": per_bin,
        "linking_note": (
            "Joins target headroom (D1), in-context evidence (D2) and frozen "
            "prediction error on identical rows."
        ),
    }
    d4_hash = write_json(OUT / "d4_bin_decomposition.json", d4)

    # ---------------- console ----------------
    print("=== D3 layer-4 FULL (tau1..15) ===")
    for key in (
        "macro_r2",
        "macro_centered_r2",
        "macro_rmse_blocks",
        "macro_centered_rmse_blocks",
        "mean_absolute_bias",
        "median_absolute_bias",
        "max_absolute_bias",
        "median_ols_slope",
        "min_ols_slope",
        "max_ols_slope",
        "n_trajectories_with_positive_slope",
        "median_pearson_r",
        "min_pearson_r",
        "n_trajectories_with_positive_pearson",
        "n_trajectories_with_positive_centered_r2",
        "mean_bias_share_of_sse",
    ):
        print(f"  {key:44s} {full[key]}")
    print()
    print("=== D3 layer-4 BEST-K (tau1..15) ===")
    for key in (
        "macro_r2",
        "macro_centered_r2",
        "macro_rmse_blocks",
        "macro_centered_rmse_blocks",
        "median_absolute_bias",
        "median_ols_slope",
        "median_pearson_r",
        "n_trajectories_with_positive_centered_r2",
    ):
        print(f"  {key:44s} {best_k[key]}")
    print()
    print("=== D4 per bin ===")
    print(f"{'bin':16s} {'rows':>5s} {'tgtSD':>7s} {'RMSE':>7s} {'nRMSE':>7s} "
          f"{'bias':>8s} {'evFrames':>9s} {'maxPx':>7s}")
    for b in ALL_BINS:
        s = per_bin[b]
        print(f"  {b:14s} {s['rows']:5d} {s['mean_within_trajectory_target_sd_blocks']:7.4f} "
              f"{s['full_rmse_blocks']:7.4f} "
              f"{s['full_normalized_rmse_over_within_traj_sd']:7.3f} "
              f"{s['full_signed_bias_blocks']:8.4f} "
              f"{s['context_evidence']['median_rendered_evidence_frames']:9.1f} "
              f"{s['context_evidence']['median_max_context_magenta_pixels']:7.0f}")
    print()
    print("  d3 sha256:", d3_hash)
    print("  d4 sha256:", d4_hash)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
