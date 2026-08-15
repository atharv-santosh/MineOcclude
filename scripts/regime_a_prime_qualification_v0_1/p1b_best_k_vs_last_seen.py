"""P1B: frozen layer-4 BEST-K versus a causal static last-seen baseline.

EXPLORATORY_EXISTING_DATA. Compares the FROZEN held-out BEST-K hidden-position
predictions against LAST_RENDERED_EVIDENCE_POSITION on identical eligible rows.

LAST_RENDERED_EVIDENCE_POSITION is the exploratory implementation of the
currently recommended last-seen definition. It is NOT the prospectively frozen
Regime A prime baseline authority; the primary last-seen definition still
requires Nick's approval before any confirmatory design freeze.

The independent unit is the TRAJECTORY. Frames are repeated measurements inside
a trajectory, not inferential replicates.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from p1_common import (
    DOMAINS,
    OUT,
    build_rows,
    domain_frame,
    error_stats,
    r2_secondary,
    target_stats,
    trajectory_bootstrap,
    write_json,
)

BASELINES = {
    "LAST_RENDERED_EVIDENCE_POSITION": "last_rendered_evidence_position",
    "LAST_CLEAN_VISIBLE_POSITION": "last_clean_visible_position",
}

# Frozen comparator columns already present in the closed Regime A package.
# Reported as clearly non-controlling context so that "neural beats last-seen"
# cannot be read in isolation. Nothing here is refit.
FROZEN_REFERENCE_BASELINES = {
    "FROZEN_LAST_VISIBLE_PRE_ONSET": "predicted_last_visible",
    "FROZEN_CONSTANT_VELOCITY": "predicted_constant_velocity",
    "FROZEN_TRAINING_MEAN": "predicted_training_mean",
    "FROZEN_TIME_ONLY_LINEAR": "predicted_time_only_linear",
}


def per_trajectory(frame: pd.DataFrame, column: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for traj, group in frame.groupby("trajectory_id"):
        target = group["world_x"].to_numpy(dtype=np.float64)
        prediction = group[column].to_numpy(dtype=np.float64)
        record = error_stats(target, prediction)
        record.update(target_stats(target))
        record["rows"] = int(len(group))
        record["r2_secondary_non_controlling"] = r2_secondary(target, prediction)
        out[str(traj)] = record
    return out


def describe(frame: pd.DataFrame, column: str) -> dict[str, Any]:
    target = frame["world_x"].to_numpy(dtype=np.float64)
    prediction = frame[column].to_numpy(dtype=np.float64)
    traj = per_trajectory(frame, column)
    return {
        "row_level_descriptive": {
            **error_stats(target, prediction),
            "r2_secondary_non_controlling": r2_secondary(target, prediction),
            "rows": int(len(frame)),
        },
        "trajectory_equal": {
            "rmse_blocks": float(np.mean([v["rmse_blocks"] for v in traj.values()])),
            "mae_blocks": float(np.mean([v["mae_blocks"] for v in traj.values()])),
            "signed_bias_blocks": float(
                np.mean([v["signed_bias_blocks"] for v in traj.values()])
            ),
            "macro_r2_secondary_non_controlling": float(np.mean([
                v["r2_secondary_non_controlling"] for v in traj.values()
                if v["r2_secondary_non_controlling"] is not None
            ])),
            "n_trajectories": len(traj),
        },
        "per_trajectory": traj,
    }


def analyse_domain(table: pd.DataFrame, name: str) -> dict[str, Any]:
    frame = domain_frame(table, name)
    spec = DOMAINS[name]
    target = frame["world_x"].to_numpy(dtype=np.float64)

    # Rows in the tau window that carry no in-context rendered evidence are
    # excluded because the baseline is undefined there, not because of outcome.
    window = table[(table["tau"] >= spec["tau_min"]) & (table["tau"] <= spec["tau_max"])]
    excluded = int(len(window) - len(frame))

    payload: dict[str, Any] = {
        "domain": name,
        "tau_window": [spec["tau_min"], spec["tau_max"]],
        "trajectory_count": int(frame["trajectory_id"].nunique()),
        "row_count": int(len(frame)),
        "rows_in_tau_window": int(len(window)),
        "rows_excluded_no_in_context_rendered_evidence": excluded,
        "exclusion_rule": "metadata-only: baseline undefined without in-context "
                          "rendered sheep-pixel evidence; never outcome-based",
        "target": target_stats(target),
        "evidence_age_frames": {
            "min": float(frame["frames_since_last_rendered_evidence"].min()),
            "median": float(frame["frames_since_last_rendered_evidence"].median()),
            "max": float(frame["frames_since_last_rendered_evidence"].max()),
        },
        "neural_best_k": describe(frame, "predicted_layer4_best_k"),
    }

    for label, column in BASELINES.items():
        supported = bool(frame[column].notna().all())
        if not supported:
            payload[label] = {
                "status": "UNSUPPORTED_ON_THIS_DOMAIN",
                "reason": "INSUFFICIENT_DATA_TO_VERIFY: baseline undefined for "
                          f"{int(frame[column].isna().sum())} of {len(frame)} rows",
                "rows_defined": int(frame[column].notna().sum()),
            }
            continue
        payload[label] = {"status": "SUPPORTED", **describe(frame, column)}

    payload["frozen_reference_baselines_non_controlling"] = {
        label: {
            "trajectory_equal_rmse_blocks": float(np.mean([
                v["rmse_blocks"] for v in per_trajectory(frame, column).values()
            ])),
            "row_level_rmse_blocks": error_stats(
                target, frame[column].to_numpy(dtype=np.float64)
            )["rmse_blocks"],
        }
        for label, column in FROZEN_REFERENCE_BASELINES.items()
    }
    # An oracle constant at the per-trajectory target mean. Not attainable by any
    # causal estimator; recorded only to show what the negative macro R2 means.
    payload["oracle_trajectory_mean_reference"] = {
        "status": "ORACLE_NOT_A_CAUSAL_BASELINE",
        "trajectory_equal_rmse_blocks": float(np.mean([
            float(np.sqrt(((g["world_x"] - g["world_x"].mean()) ** 2).mean()))
            for _, g in frame.groupby("trajectory_id")
        ])),
        "note": "macro R2 < 0 means the neural readout is worse than this oracle "
                "constant, in every domain reported here",
    }

    # LAST_CLEAN_VISIBLE is undefined on most hidden rows. Where coverage is
    # partial, report it on an explicitly RESTRICTED subdomain with the neural
    # readout evaluated on exactly the same rows, rather than dropping it or
    # comparing across different row sets.
    restricted = frame[frame["last_clean_visible_position"].notna()]
    min_trajectories = 10
    if 0 < len(restricted) < len(frame) and (
        restricted["trajectory_id"].nunique() < min_trajectories
    ):
        payload["last_clean_visible_restricted_subdomain"] = {
            "status": "INSUFFICIENT_DATA_TO_VERIFY",
            "reason": "fewer than "
                      f"{min_trajectories} trajectories retain a causally prior "
                      "in-context VISIBLE_AGREEMENT frame on this domain",
            "row_count": int(len(restricted)),
            "trajectory_count": int(restricted["trajectory_id"].nunique()),
        }
    elif 0 < len(restricted) < len(frame):
        neural_r = per_trajectory(restricted, "predicted_layer4_best_k")
        clean_r = per_trajectory(restricted, "last_clean_visible_position")
        lre_r = per_trajectory(restricted, "last_rendered_evidence_position")
        deltas_r = {t: clean_r[t]["rmse_blocks"] - neural_r[t]["rmse_blocks"]
                    for t in neural_r}
        payload["last_clean_visible_restricted_subdomain"] = {
            "status": "RESTRICTED_SUBDOMAIN_ONLY",
            "selection": "rows of this domain where a causally prior in-context "
                         "VISIBLE_AGREEMENT frame exists; metadata-only, not outcome-based",
            "row_count": int(len(restricted)),
            "trajectory_count": int(restricted["trajectory_id"].nunique()),
            "coverage_fraction_of_domain": float(len(restricted) / len(frame)),
            "neural_best_k_trajectory_equal_rmse_blocks": float(
                np.mean([v["rmse_blocks"] for v in neural_r.values()])),
            "last_clean_visible_trajectory_equal_rmse_blocks": float(
                np.mean([v["rmse_blocks"] for v in clean_r.values()])),
            "last_rendered_evidence_trajectory_equal_rmse_blocks": float(
                np.mean([v["rmse_blocks"] for v in lre_r.values()])),
            "equal_trajectory_mean_delta_vs_last_clean_visible": float(
                np.mean(list(deltas_r.values()))),
            "bootstrap": trajectory_bootstrap(deltas_r),
        }

    # Paired per-trajectory Delta against the primary baseline.
    neural = payload["neural_best_k"]["per_trajectory"]
    baseline = payload["LAST_RENDERED_EVIDENCE_POSITION"]
    deltas: dict[str, float] = {}
    if baseline.get("status") == "SUPPORTED":
        for traj, record in baseline["per_trajectory"].items():
            deltas[traj] = record["rmse_blocks"] - neural[traj]["rmse_blocks"]

        values = np.asarray([deltas[k] for k in sorted(deltas)], dtype=np.float64)
        payload["delta_vs_last_rendered_evidence"] = {
            "definition": "Delta_i = RMSE_last_seen_i - RMSE_neural_i "
                          "(positive favours the neural decoder)",
            "independent_unit": "TRAJECTORY",
            "equal_trajectory_mean_delta": float(values.mean()),
            "median_delta_descriptive": float(np.median(values)),
            "n_trajectories_delta_gt_zero": int((values > 0).sum()),
            "fraction_delta_gt_zero": float((values > 0).mean()),
            "n_trajectories": int(len(values)),
            "absolute_aggregate_improvement_blocks": float(
                payload["LAST_RENDERED_EVIDENCE_POSITION"]["trajectory_equal"]["rmse_blocks"]
                - payload["neural_best_k"]["trajectory_equal"]["rmse_blocks"]
            ),
            "relative_improvement_secondary": float(
                1.0
                - payload["neural_best_k"]["trajectory_equal"]["rmse_blocks"]
                / payload["LAST_RENDERED_EVIDENCE_POSITION"]["trajectory_equal"]["rmse_blocks"]
            ),
            "per_trajectory_delta": {k: float(v) for k, v in sorted(deltas.items())},
            "bootstrap": trajectory_bootstrap(deltas),
        }

        # Same contrast against the optional secondary baseline, when exact.
        clean = payload["LAST_CLEAN_VISIBLE_POSITION"]
        if clean.get("status") == "SUPPORTED":
            clean_deltas = {
                traj: record["rmse_blocks"] - neural[traj]["rmse_blocks"]
                for traj, record in clean["per_trajectory"].items()
            }
            cvals = np.asarray([clean_deltas[k] for k in sorted(clean_deltas)])
            payload["delta_vs_last_clean_visible"] = {
                "equal_trajectory_mean_delta": float(cvals.mean()),
                "median_delta_descriptive": float(np.median(cvals)),
                "fraction_delta_gt_zero": float((cvals > 0).mean()),
                "bootstrap": trajectory_bootstrap(clean_deltas),
            }

    return payload


def main() -> int:
    table = build_rows()
    domains = {name: analyse_domain(table, name) for name in DOMAINS}

    payload = {
        "artifact_id": "regime-a-prime-qualification-p1b-best-k-vs-last-seen-v0.1",
        "schema_version": "1.0",
        "phase": "P1",
        "classification": "EXPLORATORY_EXISTING_DATA",
        "status": "PASS",
        "question": "Does the frozen held-out layer-4 BEST-K hidden-position readout "
                    "beat a causal static last-seen baseline on identical eligible rows?",
        "primary_baseline": {
            "name": "LAST_RENDERED_EVIDENCE_POSITION",
            "definition": "sheep world_x at the most recent causally prior model-input "
                          "frame (within [T-15, T]) whose magenta detector state is "
                          "'detected' under the existing Regime A detector authority",
            "authority_status": "EXPLORATORY_IMPLEMENTATION_OF_RECOMMENDED_DEFINITION",
            "is_frozen_a_prime_baseline_authority": False,
            "requires_operator_approval_before_confirmatory_freeze": True,
            "baseline_selected_by_outcome": False,
        },
        "secondary_baseline": {
            "name": "LAST_CLEAN_VISIBLE_POSITION",
            "definition": "sheep world_x at the most recent causally prior model-input "
                          "frame with visibility_class == VISIBLE_AGREEMENT",
            "note": "reported only where exactly supported on every row of a domain",
        },
        "neural_predictions": {
            "column": "predicted_layer4_best_k",
            "source": "frozen closed Regime A slice_predictions.parquet",
            "held_out": True,
            "recomputed_by_p1": False,
        },
        "domains": domains,
    }

    digest = write_json(OUT / "p1_best_k_vs_last_seen.json", payload)
    print("P1B_STATUS=PASS")
    print(f"P1B_SHA256={digest}")
    for name, d in domains.items():
        delta = d.get("delta_vs_last_rendered_evidence")
        print(
            f"{name}: rows={d['row_count']} traj={d['trajectory_count']} "
            f"neural_rmse={d['neural_best_k']['trajectory_equal']['rmse_blocks']:.4f} "
            f"last_seen_rmse={d['LAST_RENDERED_EVIDENCE_POSITION']['trajectory_equal']['rmse_blocks']:.4f} "
            f"mean_delta={delta['equal_trajectory_mean_delta']:.4f} "
            f"ci=[{delta['bootstrap']['ci95_low']:.4f},{delta['bootstrap']['ci95_high']:.4f}] "
            f"frac>0={delta['fraction_delta_gt_zero']:.2f}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
