"""P1C: matched visible-versus-SHORT comparison on existing data.

EXPLORATORY_EXISTING_DATA.

Outcome firewall. The match manifest is constructed and hashed from METADATA
ONLY (trajectory identity, direction, outer fold, frame index, and distance from
the visibility boundary). No decoder prediction, residual, RMSE or R2 is read
before the manifest is frozen. Outcome columns are joined only afterwards.

Known limitation, reported rather than worked around: the postmortem D6 visible
positive control persisted only PER-TRAJECTORY aggregates
(d6_visible_positive_control.json), not per-row visible predictions. Recovering
row-level visible predictions would require re-reading visible activations and
refitting the ridge readout, which P1 forbids. Exact row-level scoring of the
matched pairs on the visible side is therefore
UNSUPPORTED_FROM_PERSISTED_PREDICTIONS.

This module deliberately keeps three different things apart, because conflating
them is the easiest way to misread P1:

  (a) the metadata-selected visible/SHORT matching manifest -- 100 exact row
      pairs, a matching authority only, never scored row-for-row;
  (b) the D6 VISIBLE-WINDOW versus matched-SHORT aggregate comparison -- the
      visible term is the 8-row-per-trajectory D6 window, NOT the matched rows;
  (c) the D6 visible window versus hidden tau 8..15 comparison -- the only
      contrast here with equal 8-row-per-trajectory support on both sides.

No visible RMSE anywhere in P1 is computed from the 100 matched visible rows.
"""

from __future__ import annotations

import json
from typing import Any

import numpy as np
import pandas as pd

from p1_common import (
    OUT,
    PM,
    build_rows,
    error_stats,
    r2_secondary,
    sha256_obj,
    target_stats,
    trajectory_bootstrap,
    write_json,
)

MATCH_ALGORITHM = "boundary_offset_rank_v1"
SHORT_TAU_MAX = 4


def build_match_manifest(visible: pd.DataFrame, short: pd.DataFrame) -> dict[str, Any]:
    """Pair visible rows to SHORT rows by distance from the visibility boundary.

    Metadata-only. The visible window is the last 8 contiguous clean-visible
    frames ending at the last clean-visible frame before the entry transition
    (visible_index 8 is that boundary frame). The SHORT window is tau 1..4 after
    occlusion onset. Both are indexed by their offset k from the same visibility
    boundary, so k=1 pairs the frame nearest the boundary on each side.
    """
    pairs: list[dict[str, Any]] = []
    unmatched: list[dict[str, Any]] = []

    visible = visible.copy()
    visible["boundary_offset_k"] = (
        visible["visible_index"].max() - visible["visible_index"] + 1
    )

    for traj in sorted(set(visible["trajectory_id"]) | set(short["trajectory_id"])):
        vis_t = visible[visible["trajectory_id"] == traj]
        short_t = short[short["trajectory_id"] == traj]
        for _, vrow in vis_t.sort_values("boundary_offset_k").iterrows():
            k = int(vrow["boundary_offset_k"])
            candidate = short_t[short_t["tau"] == k]
            if k > SHORT_TAU_MAX or candidate.empty:
                unmatched.append({
                    "side": "VISIBLE",
                    "trajectory_id": traj,
                    "visible_index": int(vrow["visible_index"]),
                    "model_frame_idx": int(vrow["model_frame_idx"]),
                    "boundary_offset_k": k,
                    "reason": "NO_CORRESPONDING_SHORT_TAU: the SHORT bin spans tau 1..4 "
                              "only, so visible rows at boundary offset > 4 have no "
                              "metadata-matched hidden counterpart",
                })
                continue
            srow = candidate.iloc[0]
            if str(vrow["direction"]) != str(srow["direction"]):
                unmatched.append({
                    "side": "VISIBLE", "trajectory_id": traj,
                    "boundary_offset_k": k, "reason": "DIRECTION_MISMATCH",
                })
                continue
            if int(vrow["outer_fold"]) != int(srow["outer_fold"]):
                unmatched.append({
                    "side": "VISIBLE", "trajectory_id": traj,
                    "boundary_offset_k": k, "reason": "OUTER_FOLD_MISMATCH",
                })
                continue
            pairs.append({
                "trajectory_id": traj,
                "direction": str(vrow["direction"]),
                "outer_fold": int(vrow["outer_fold"]),
                "boundary_offset_k": k,
                "visible_row_identity": {
                    "visible_index": int(vrow["visible_index"]),
                    "model_frame_idx": int(vrow["model_frame_idx"]),
                    "context_first_frame": int(vrow["context_first_frame"]),
                    "context_last_frame": int(vrow["context_last_frame"]),
                },
                "short_row_identity": {
                    "tau": int(srow["tau"]),
                    "model_frame_idx": int(srow["model_frame_idx"]),
                    "server_tick": int(srow["server_tick"]),
                    "activation_row": int(srow["activation_row"]),
                    "context_first_frame": int(srow["context_first_frame"]),
                    "context_last_frame": int(srow["context_last_frame"]),
                },
                "matched": True,
            })

    for traj in sorted(set(short["trajectory_id"])):
        short_t = short[short["trajectory_id"] == traj]
        matched_taus = {
            p["short_row_identity"]["tau"] for p in pairs if p["trajectory_id"] == traj
        }
        for _, srow in short_t.iterrows():
            if int(srow["tau"]) not in matched_taus:
                unmatched.append({
                    "side": "SHORT", "trajectory_id": traj, "tau": int(srow["tau"]),
                    "reason": "NO_CORRESPONDING_VISIBLE_ROW",
                })

    pairs.sort(key=lambda p: (p["trajectory_id"], p["boundary_offset_k"]))
    unmatched.sort(key=lambda u: (u["side"], u["trajectory_id"],
                                  u.get("boundary_offset_k", u.get("tau", 0))))

    manifest = {
        "artifact_id": "regime-a-prime-qualification-p1-matching-manifest-v0.1",
        "schema_version": "1.0",
        "phase": "P1",
        "status": "FROZEN_BEFORE_OUTCOME_JOIN",
        "matching_algorithm": MATCH_ALGORITHM,
        "matching_rule": "pair the visible row and the SHORT row at equal offset k "
                         "from the same visibility boundary (k = 1..4); visible "
                         "boundary_offset_k = max(visible_index) - visible_index + 1, "
                         "SHORT boundary_offset_k = tau",
        "matching_keys": ["trajectory_id", "direction", "outer_fold", "boundary_offset_k"],
        "deterministic_ordering": "sorted by (trajectory_id, boundary_offset_k)",
        "outcome_firewall": {
            "selection_used_metadata_only": True,
            "prediction_columns_read_before_freeze": [],
            "forbidden_inputs": [
                "decoder prediction", "neural residual", "RMSE", "R2",
                "any neural performance outcome",
            ],
        },
        "matched_pair_count": len(pairs),
        "unmatched_count": len(unmatched),
        "matched_trajectory_count": len({p["trajectory_id"] for p in pairs}),
        "scoring_support": {
            "exact_row_level_visible_scoring_status":
                "UNSUPPORTED_FROM_PERSISTED_PREDICTIONS",
            "reason": "row-level visible BEST-K predictions were never persisted "
                      "(d6_visible_positive_control.json stores per-trajectory "
                      "aggregates only) and refitting the readout from activations is "
                      "prohibited in P1",
            "short_side_row_level_scoring": "SUPPORTED",
            "visible_side_row_level_scoring": "UNSUPPORTED_FROM_PERSISTED_PREDICTIONS",
            "manifest_remains_valid_as":
                "METADATA_ONLY_MATCHING_AUTHORITY",
            "these_pairs_were_not_used_to_compute_any_visible_rmse": True,
        },
        "pairs": pairs,
        "unmatched": unmatched,
    }
    manifest["manifest_integrity_sha256"] = sha256_obj({
        "algorithm": MATCH_ALGORITHM, "pairs": pairs, "unmatched": unmatched,
    })
    return manifest


def side_metrics(frame: pd.DataFrame, column: str) -> dict[str, Any]:
    target = frame["world_x"].to_numpy(dtype=np.float64)
    prediction = frame[column].to_numpy(dtype=np.float64)
    per_traj = {}
    for traj, group in frame.groupby("trajectory_id"):
        t = group["world_x"].to_numpy(dtype=np.float64)
        p = group[column].to_numpy(dtype=np.float64)
        per_traj[str(traj)] = {**error_stats(t, p), **target_stats(t),
                               "rows": int(len(group))}
    return {
        "row_level_descriptive": {
            **error_stats(target, prediction), **target_stats(target),
            "rows": int(len(frame)),
            "r2_secondary_non_controlling": r2_secondary(target, prediction),
        },
        "trajectory_equal": {
            "rmse_blocks": float(np.mean([v["rmse_blocks"] for v in per_traj.values()])),
            "mae_blocks": float(np.mean([v["mae_blocks"] for v in per_traj.values()])),
            "signed_bias_blocks": float(
                np.mean([v["signed_bias_blocks"] for v in per_traj.values()])),
            "n_trajectories": len(per_traj),
        },
        "per_trajectory": per_traj,
    }


def main() -> int:
    table = build_rows()
    vis_manifest = json.loads((PM / "visible_positive_control_manifest.json").read_text())
    visible = pd.DataFrame(vis_manifest["rows"])
    short = table[table["duration_bin"] == "SHORT"].copy()

    # --- OUTCOME FIREWALL: manifest built and persisted before any outcome join.
    manifest = build_match_manifest(visible, short)
    manifest_digest = write_json(OUT / "p1_matching_manifest.json", manifest)

    # --- Outcome analysis begins here.
    matched_short_keys = {
        (p["trajectory_id"], p["short_row_identity"]["tau"]) for p in manifest["pairs"]
    }
    short_matched = short[
        short.apply(lambda r: (r["trajectory_id"], int(r["tau"])) in matched_short_keys,
                    axis=1)
    ].copy()

    d6 = json.loads((PM / "d6_visible_positive_control.json").read_text())
    visible_per_traj = d6["visible_control"]["BEST_K"]["per_trajectory"]

    short_side = side_metrics(short_matched, "predicted_layer4_best_k")

    # Trajectory-level paired difference: visible (8-row D6 window) vs matched SHORT.
    paired = {}
    for traj, srec in short_side["per_trajectory"].items():
        if traj in visible_per_traj:
            paired[traj] = srec["rmse_blocks"] - visible_per_traj[traj]["rmse"]

    # Row-count-matched contrast already frozen by existing authority:
    # D6 visible (8 rows/traj) vs matched-span hidden tau 8..15 (8 rows/traj).
    span = table[(table["tau"] >= 8) & (table["tau"] <= 15)].copy()
    span_side = side_metrics(span, "predicted_layer4_best_k")
    span_paired = {
        traj: rec["rmse_blocks"] - visible_per_traj[traj]["rmse"]
        for traj, rec in span_side["per_trajectory"].items() if traj in visible_per_traj
    }

    payload = {
        "artifact_id": "regime-a-prime-qualification-p1c-visible-vs-short-v0.1",
        "schema_version": "1.0",
        "phase": "P1",
        "classification": "EXPLORATORY_EXISTING_DATA",
        "status": "PASS",
        "sub_analysis_status": "PARTIAL_UNSUPPORTED_ROW_LEVEL_SCORING",
        "status_note": "P1 overall remains PASS. Every analysis that the persisted data "
                       "can support was executed validly; the single unsupported element "
                       "is exact row-level scoring on the visible side, encoded "
                       "explicitly rather than approximated.",
        "matching_manifest_sha256": manifest_digest,
        "matching_manifest_integrity_sha256": manifest["manifest_integrity_sha256"],
        "matched_pair_count": manifest["matched_pair_count"],
        "matched_trajectory_count": manifest["matched_trajectory_count"],
        "exact_row_level_visible_scoring_status":
            "UNSUPPORTED_FROM_PERSISTED_PREDICTIONS",
        "three_distinct_analyses": {
            "a_metadata_selected_matching_manifest": {
                "what": "100 metadata-selected visible/SHORT row pairs across 25 "
                        "trajectories, matched on boundary offset k=1..4",
                "population": "exact row pairs",
                "scored_row_for_row": False,
                "visible_side_scoring": "UNSUPPORTED_FROM_PERSISTED_PREDICTIONS",
                "short_side_scoring": "SUPPORTED",
                "role": "metadata-only matching authority; carries no visible RMSE",
            },
            "b_d6_visible_window_vs_short_matched_aggregate": {
                "what": "descriptive aggregate contrast between the D6 visible window "
                        "and the metadata-matched SHORT rows",
                "visible_population": "D6 visible positive-control window, 8 rows per "
                                      "trajectory, 200 rows total",
                "short_population": "metadata-matched SHORT rows, 4 rows per trajectory, "
                                    "100 rows total",
                "row_count_matched": False,
                "derived_from_the_100_matched_pairs": False,
            },
            "c_d6_visible_window_vs_hidden_tau8_15": {
                "what": "existing-authority contrast with equal 8-row-per-trajectory "
                        "support on both sides",
                "visible_population": "D6 visible window, 8 rows per trajectory",
                "hidden_population": "frozen hidden matched span tau 8..15, 8 rows per "
                                     "trajectory",
                "row_count_matched": True,
            },
        },
        "visible_row_level_outcome_join": {
            "status": "UNSUPPORTED_FROM_PERSISTED_PREDICTIONS",
            "reason": "per-row visible BEST-K predictions were never persisted. "
                      "d6_visible_positive_control.json stores per-trajectory aggregates "
                      "only, and recovering row-level visible predictions would require "
                      "re-reading visible activations and refitting the readout, which "
                      "P1 forbids.",
            "consequence": "the frozen row-level match manifest is NOT scored on the "
                           "visible side. No visible RMSE reported anywhere in P1 is "
                           "computed from the 100 matched visible rows.",
        },
        "short_matched_side": {
            "source": "frozen closed Regime A predicted_layer4_best_k",
            "rows_per_trajectory": 4,
            **short_side,
        },
        "d6_visible_window_side": {
            "source": "postmortem D6 visible positive control, BEST_K, per-trajectory",
            "population": "D6 visible positive-control window: the last 8 contiguous "
                          "clean-visible frames per trajectory, 200 rows over 25 "
                          "trajectories",
            "is_the_100_matched_visible_rows": False,
            "population_warning": "these metrics are the D6 VISIBLE-WINDOW aggregate. "
                                  "They are NOT the matched-row visible RMSE and were "
                                  "not computed from the 100 metadata-matched pairs.",
            "rows_per_trajectory": int(d6["rows_per_trajectory"]),
            "d6_visible_window_trajectory_equal_rmse_blocks": float(
                d6["visible_control"]["BEST_K"]["trajectory_aggregated_rmse"]),
            "d6_visible_window_trajectory_equal_mae_blocks": float(
                d6["visible_control"]["BEST_K"]["trajectory_aggregated_mae"]),
            "pooled_rmse_blocks": float(d6["visible_control"]["BEST_K"]["pooled_rmse"]),
            "macro_r2_secondary_non_controlling": float(
                d6["visible_control"]["BEST_K"]["macro_r2"]),
            "mean_target_sd_blocks": float(
                d6["visible_control"]["BEST_K"]["mean_target_sd_blocks"]),
            "mean_target_range_blocks": float(
                d6["visible_control"]["BEST_K"]["mean_target_range_blocks"]),
            "per_trajectory": visible_per_traj,
        },
        "d6_visible_window_vs_short_matched_paired": {
            "definition": "per trajectory, RMSE_short_matched - "
                          "RMSE_d6_visible_window (positive means the hidden SHORT side "
                          "is worse)",
            "population_warning": "the visible term is the D6 VISIBLE-WINDOW "
                                  "per-trajectory RMSE (8 rows), NOT a matched-row "
                                  "visible RMSE. This contrast is not derived from the "
                                  "100 metadata-matched pairs.",
            "row_count_caveat": "visible side spans 8 rows per trajectory, SHORT side 4; "
                                "this contrast is NOT row-count matched",
            "n_trajectories": len(paired),
            "equal_trajectory_mean_difference": float(np.mean(list(paired.values()))),
            "median_difference_descriptive": float(np.median(list(paired.values()))),
            "fraction_short_worse": float(
                np.mean([v > 0 for v in paired.values()])),
            "per_trajectory_difference": {k: float(v) for k, v in sorted(paired.items())},
            "bootstrap": trajectory_bootstrap(paired),
        },
        "d6_visible_window_vs_hidden_tau8_15": {
            "definition": "row-count-matched contrast already defined by existing "
                          "authority: D6 visible window (8 rows/trajectory) versus the "
                          "frozen hidden matched span tau 8..15 (8 rows/trajectory)",
            "row_count_matched": True,
            "hidden_side_trajectory_equal_rmse_blocks":
                span_side["trajectory_equal"]["rmse_blocks"],
            "d6_visible_window_trajectory_equal_rmse_blocks": float(
                d6["visible_control"]["BEST_K"]["trajectory_aggregated_rmse"]),
            "n_trajectories": len(span_paired),
            "equal_trajectory_mean_difference": float(np.mean(list(span_paired.values()))),
            "fraction_hidden_worse": float(np.mean([v > 0 for v in span_paired.values()])),
            "bootstrap": trajectory_bootstrap(span_paired),
        },
        "interpretation_constraints": {
            "supports": "a visible-versus-hidden performance gap under the OLD Regime A "
                        "design, descriptively",
            "does_not_isolate": [
                "hidden-state memory loss",
                "wall/background distribution change",
                "retained evidence amount",
                "estimator mismatch",
                "explicit object permanence",
                "belief or uncertainty representation",
                "causal use of hidden position",
            ],
            "re_adjudicates_closed_regime_a": False,
        },
    }

    digest = write_json(OUT / "p1_visible_vs_short.json", payload)
    print("P1C_STATUS=PASS")
    print("P1C_SUB_ANALYSIS_STATUS=PARTIAL_UNSUPPORTED_ROW_LEVEL_SCORING")
    print("P1C_EXACT_ROW_LEVEL_VISIBLE_SCORING=UNSUPPORTED_FROM_PERSISTED_PREDICTIONS")
    print(f"P1C_SHA256={digest}")
    print(f"P1C_METADATA_MATCHED_PAIRS={manifest['matched_pair_count']} "
          f"UNMATCHED={manifest['unmatched_count']} "
          f"TRAJ={manifest['matched_trajectory_count']} (not row-level scored)")
    print(f"P1C_SHORT_MATCHED_RMSE={short_side['trajectory_equal']['rmse_blocks']:.4f} "
          f"MAE={short_side['trajectory_equal']['mae_blocks']:.4f}")
    print("P1C_D6_VISIBLE_WINDOW_RMSE="
          f"{d6['visible_control']['BEST_K']['trajectory_aggregated_rmse']:.4f} "
          f"MAE={d6['visible_control']['BEST_K']['trajectory_aggregated_mae']:.4f} "
          "(8-row D6 window, NOT matched rows)")
    print(f"P1C_HIDDEN_TAU8_15_RMSE={span_side['trajectory_equal']['rmse_blocks']:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
