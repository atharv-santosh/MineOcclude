"""D1 (EXPLORATORY): actual within-trajectory target headroom on tau1..15.

Uses the exact frozen primary rows. Reproduces the frozen macro R2 from each
trajectory's own SSE/TSS to prove the headroom arithmetic is describing the
same quantity the confirmatory gate adjudicated.
"""

from __future__ import annotations

import json
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "/home/sagemaker-user/MineOcclude/scripts/postmortem_v0_1")

from pm_common import (  # noqa: E402
    CONF,
    FROZEN_PRIMARY_MACRO_R2,
    OUT,
    summarize,
    write_json,
)


def main() -> int:
    preds = pd.read_parquet(CONF / "slice_predictions.parquet")
    primary = json.loads((CONF / "slice_primary_results.json").read_text())

    # Frozen per-trajectory SSE/TSS as adjudicated (outer-fold OOF).
    frozen = {}
    for fold, payload in primary["outer_folds"].items():
        for traj, stats in payload["per_trajectory"].items():
            frozen[traj] = dict(stats, outer_fold=int(fold))

    rows = preds[preds["tau"].between(1, 15)].copy()
    assert len(rows) == 375, len(rows)

    per_traj = []
    for traj, group in rows.groupby("trajectory_id", sort=True):
        group = group.sort_values("tau")
        y = group["world_x"].to_numpy(np.float64)
        yhat = group["predicted_layer4_full"].to_numpy(np.float64)
        n = len(y)
        assert n == 15, (traj, n)

        tss = float(((y - y.mean()) ** 2).sum())
        sse = float(((y - yhat) ** 2).sum())
        rmse = float(np.sqrt(((y - yhat) ** 2).mean()))
        mae = float(np.abs(y - yhat).mean())
        sd_pop = float(np.sqrt(tss / n))
        rng = float(y.max() - y.min())
        disp = float(y[-1] - y[0])

        fz = frozen[traj]
        per_traj.append(
            {
                "trajectory_id": traj,
                "direction": str(group["direction"].iloc[0]),
                "outer_fold": fz["outer_fold"],
                "n_rows": n,
                "target_min_blocks": float(y.min()),
                "target_max_blocks": float(y.max()),
                "target_range_blocks": rng,
                "target_mean_blocks": float(y.mean()),
                "target_sd_blocks_population": sd_pop,
                "target_tss": tss,
                "hidden_displacement_tau1_to_tau15_blocks": disp,
                "abs_hidden_displacement_blocks": abs(disp),
                "full_sse": sse,
                "full_rmse_blocks": rmse,
                "full_mae_blocks": mae,
                "rmse_over_target_sd": rmse / sd_pop,
                "mae_over_target_range": mae / rng,
                "trajectory_r2_recomputed": 1.0 - sse / tss,
                "trajectory_r2_frozen": fz["r2"],
                "tss_frozen": fz["tss"],
                "sse_frozen": fz["sse"],
                "tss_match": bool(np.isclose(tss, fz["tss"], rtol=0, atol=1e-9)),
                "sse_match": bool(np.isclose(sse, fz["sse"], rtol=0, atol=1e-9)),
            }
        )

    per_traj.sort(key=lambda r: r["trajectory_id"])
    macro_recomputed = float(np.mean([r["trajectory_r2_recomputed"] for r in per_traj]))
    macro_frozen_pertraj = float(np.mean([r["trajectory_r2_frozen"] for r in per_traj]))

    exact = bool(np.isclose(macro_recomputed, FROZEN_PRIMARY_MACRO_R2, rtol=0, atol=1e-12))

    def col(name: str) -> list[float]:
        return [r[name] for r in per_traj]

    # Counterfactual headroom: what macro R2 would the SAME absolute errors give
    # if within-trajectory target SD were larger? Descriptive only.
    rmse_vals = np.array(col("full_rmse_blocks"))
    counterfactual = {}
    for factor in (1.0, 2.0, 3.0, 4.0):
        sd_scaled = np.array(col("target_sd_blocks_population")) * factor
        counterfactual[f"target_sd_x{factor:g}"] = float(
            np.mean(1.0 - (rmse_vals**2) / (sd_scaled**2))
        )

    # SD required, at the observed per-trajectory RMSE, to reach given macro R2.
    required_sd = {
        f"macro_r2_{t}": float(np.mean(rmse_vals / np.sqrt(1.0 - t)))
        for t in (0.0, 0.5, 0.8, 0.9)
    }

    payload = {
        "artifact_id": "regime-a-postmortem-d1-headroom-v0.1",
        "status": "EXPLORATORY",
        "rows_used": int(len(rows)),
        "domain": "tau1..15 primary confirmatory rows (unchanged)",
        "reproduction": {
            "macro_r2_recomputed_from_sse_over_tss": macro_recomputed,
            "macro_r2_mean_of_frozen_per_trajectory": macro_frozen_pertraj,
            "frozen_primary_macro_r2": FROZEN_PRIMARY_MACRO_R2,
            "exact_match": exact,
            "all_tss_match": all(r["tss_match"] for r in per_traj),
            "all_sse_match": all(r["sse_match"] for r in per_traj),
        },
        "across_trajectories": {
            "target_sd_blocks": summarize(col("target_sd_blocks_population")),
            "target_range_blocks": summarize(col("target_range_blocks")),
            "abs_hidden_displacement_blocks": summarize(col("abs_hidden_displacement_blocks")),
            "full_rmse_blocks": summarize(col("full_rmse_blocks")),
            "full_mae_blocks": summarize(col("full_mae_blocks")),
            "rmse_over_target_sd": summarize(col("rmse_over_target_sd")),
            "mae_over_target_range": summarize(col("mae_over_target_range")),
        },
        "descriptive_counterfactual_macro_r2_if_target_sd_scaled": counterfactual,
        "descriptive_required_target_sd_blocks_at_observed_rmse": required_sd,
        "per_trajectory": per_traj,
        "interpretation_note": (
            "Counterfactual and required-SD figures are descriptive arithmetic on "
            "frozen errors. They do NOT re-adjudicate Regime A and are not an "
            "alternative metric for the closed result."
        ),
    }
    digest = write_json(OUT / "d1_headroom.json", payload)

    print("D1 reproduction exact:", exact)
    print(f"  macro R2 recomputed = {macro_recomputed:.12f}")
    print(f"  macro R2 frozen     = {FROZEN_PRIMARY_MACRO_R2:.12f}")
    print("  all TSS match:", payload["reproduction"]["all_tss_match"],
          "| all SSE match:", payload["reproduction"]["all_sse_match"])
    print()
    for key in ("target_sd_blocks", "target_range_blocks",
                "abs_hidden_displacement_blocks", "full_rmse_blocks",
                "rmse_over_target_sd"):
        s = payload["across_trajectories"][key]
        print(f"  {key:34s} min={s['min']:.4f} med={s['median']:.4f} "
              f"mean={s['mean']:.4f} max={s['max']:.4f}")
    print()
    print("  counterfactual macro R2:", json.dumps(counterfactual))
    print("  required SD (blocks)   :", json.dumps(required_sd))
    print("  sha256:", digest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
