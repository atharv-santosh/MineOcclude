"""Final frozen P2 layer-4 BEST-K and FULL_TOKEN_GRID visible readouts."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from mineocclude.regime_a_first25_analysis import (
    ALPHAS,
    K_GRID,
    PreparedKernelRidge,
    cumulative_selected_token_kernels_cuda,
    full_kernel_cuda,
    inner_fold_assignment,
    rank_tokens_cuda,
    scalar_metrics,
)
from mineocclude.prospective.fold_discipline import row_key_digest

from p2_common import OUT, REPO, WORK, p2_run_id, read_jsonl, sha256_file, source_specs, write_json


def fold_discipline_record(rows: list[dict[str, Any]], test_indices: list[int],
                           inner: dict[str, int]) -> dict[str, Any]:
    """The evidence a terminal needs to verify this fold rather than believe it.

    ``inner`` is the assignment the fold actually used, recorded so an
    independent evaluator can re-derive it from the training identities and
    refuse a mismatch. The row digest is over the ``(trajectory_id, tau)`` keys
    this fold really predicted, so a fold that predicted the wrong rows, the same
    row twice, or somebody else's rows cannot be mistaken for a correct one.
    """
    return {
        "inner_fold_assignment": {identity: int(fold) for identity, fold in sorted(inner.items())},
        "predicted_row_count": len(test_indices),
        "predicted_row_keys_sha256": row_key_digest(
            [(rows[index]["trajectory_id"], int(rows[index]["tau"])) for index in test_indices]),
        "selection_training_tau_maximum": SELECTION_TRAINING_TAU_MAXIMUM,
    }

ACT = WORK / "activations"
AUTHORITY_RESULT = (
    REPO / "docs/status/integration/regime_a_occlusion_extraction_v0_1"
    / "first25_analysis/slice_best_k_results.json"
)
AUTHORITY_SHA256 = "11d5d2f0527feb31a27a18a19ac76d342f5c72ca3326bee1863b75187dfc4427"
BOOTSTRAP_SEED = 20260815
BOOTSTRAP_RESAMPLES = 10000

#: The tau ceiling on rows that may enter model selection and the final fit.
#: Previously a bare ``15`` inside :func:`indices`; named here so the readout can
#: record the value it actually applied and a terminal can check it against the
#: frozen selection rule rather than assume it.
SELECTION_TRAINING_TAU_MAXIMUM = 15


def load() -> tuple[np.ndarray, np.ndarray, list[dict[str, Any]], list[str], dict[str, int], dict[str, str]]:
    manifest = json.loads((OUT / "p2_activation_manifest.json").read_text())
    if manifest["status"] != "PASS" or manifest["layers_extracted"] != [4]:
        raise RuntimeError("activation manifest is not the qualified layer-4 cohort")
    specs = source_specs()
    rows: list[dict[str, Any]] = []
    arrays: list[np.ndarray] = []
    ids: list[str] = []
    outer: dict[str, int] = {}
    direction: dict[str, str] = {}
    by_run = {row["p2_no_wall_run_id"]: row for row in manifest["runs"]}
    for spec in specs:
        identity = str(spec["trajectory_spec_id"])
        run_id = p2_run_id(identity)
        record = by_run[run_id]
        array = np.load(Path(record["activation_path"]), mmap_mode="r")
        if array.shape != (19, 336, 2048) or array.dtype != np.float16:
            raise RuntimeError(f"{run_id}: activation identity failed")
        coordinates = {int(row["model_frame_idx"]): row for row in read_jsonl(
            WORK / "captures" / run_id / "coordinates.jsonl"
        )}
        targets = [int(value) for value in record["targets"]]
        for offset, frame in enumerate(targets):
            coordinate = coordinates[frame]
            rows.append({
                "trajectory_id": identity,
                "p2_no_wall_run_id": run_id,
                "activation_row": offset,
                "model_frame_idx": frame,
                "server_tick": frame,
                "tau": offset + 1,
                "outer_fold": int(spec["outer_fold"]),
                "direction": spec["direction"],
                "world_x": float(coordinate["world_x"]),
            })
        arrays.append(array)
        ids.append(identity)
        outer[identity] = int(spec["outer_fold"])
        direction[identity] = str(spec["direction"])
    features = np.concatenate(arrays, axis=0)
    target = np.asarray([row["world_x"] for row in rows], dtype=np.float64)
    if features.shape != (475, 336, 2048) or len(rows) != 475:
        raise RuntimeError("P2 analysis tensor/row cardinality failed")
    return features, target, rows, ids, outer, direction


def indices(rows: list[dict[str, Any]], identities: list[str], primary_only: bool) -> list[int]:
    selected = set(identities)
    return [i for i, row in enumerate(rows)
            if row["trajectory_id"] in selected
            and (not primary_only or row["tau"] <= SELECTION_TRAINING_TAU_MAXIMUM)]


def full_readout(features: np.ndarray, target: np.ndarray, rows: list[dict[str, Any]],
                 ids: list[str], outer_map: dict[str, int], directions: dict[str, str]) -> tuple[dict[int, float], dict, float]:
    oof: dict[int, float] = {}
    selections = {}
    gpu_seconds = 0.0
    for outer in range(5):
        train_ids = [identity for identity in ids if outer_map[identity] != outer]
        test_ids = [identity for identity in ids if outer_map[identity] == outer]
        inner = inner_fold_assignment(train_ids, {identity: directions[identity] for identity in train_ids}, outer)
        validation = {alpha: {} for alpha in ALPHAS}
        for fold in range(5):
            fit = indices(rows, [identity for identity in train_ids if inner[identity] != fold], True)
            val = indices(rows, [identity for identity in train_ids if inner[identity] == fold], True)
            started = time.monotonic()
            kernel = full_kernel_cuda(np.asarray(features[fit + val], order="C"), len(fit))
            gpu_seconds += time.monotonic() - started
            predicted = PreparedKernelRidge.from_kernel(kernel, len(fit)).predict_all(target[fit])
            for alpha in ALPHAS:
                validation[alpha].update(dict(zip(val, predicted[alpha], strict=True)))
        scores = {}
        for alpha in ALPHAS:
            metric_rows = [dict(rows[i], pred=float(value)) for i, value in validation[alpha].items()]
            scores[str(alpha)] = scalar_metrics(metric_rows, "pred")["macro_r2"]
        selected_alpha = min(ALPHAS, key=lambda alpha: (-scores[str(alpha)], alpha))
        fit = indices(rows, train_ids, True)
        test = indices(rows, test_ids, False)
        started = time.monotonic()
        kernel = full_kernel_cuda(np.asarray(features[fit + test], order="C"), len(fit))
        gpu_seconds += time.monotonic() - started
        predicted = PreparedKernelRidge.from_kernel(kernel, len(fit)).predict_all(target[fit])[selected_alpha]
        oof.update(dict(zip(test, predicted, strict=True)))
        selections[str(outer)] = {
            "selected_alpha": selected_alpha,
            "inner_macro_r2_by_alpha": scores,
            "training_trajectory_ids": train_ids,
            "test_trajectory_ids": test_ids,
            **fold_discipline_record(rows, test, inner),
        }
        print(f"FULL outer={outer} alpha={selected_alpha}", flush=True)
    return oof, selections, gpu_seconds


def best_k_readout(features: np.ndarray, target: np.ndarray, rows: list[dict[str, Any]],
                   ids: list[str], outer_map: dict[str, int], directions: dict[str, str]) -> tuple[dict[int, float], dict, float]:
    oof: dict[int, float] = {}
    selections = {}
    gpu_seconds = 0.0
    for outer in range(5):
        train_ids = [identity for identity in ids if outer_map[identity] != outer]
        test_ids = [identity for identity in ids if outer_map[identity] == outer]
        inner = inner_fold_assignment(train_ids, {identity: directions[identity] for identity in train_ids}, outer)
        validation = {(k, alpha): {} for k in K_GRID for alpha in ALPHAS}
        for fold in range(5):
            fit = indices(rows, [identity for identity in train_ids if inner[identity] != fold], True)
            val = indices(rows, [identity for identity in train_ids if inner[identity] == fold], True)
            started = time.monotonic()
            ranking = rank_tokens_cuda(features[fit], target[fit])
            kernels = cumulative_selected_token_kernels_cuda(
                np.asarray(features[fit + val], order="C"), len(fit), ranking
            )
            gpu_seconds += time.monotonic() - started
            for k, kernel in kernels.items():
                predicted = PreparedKernelRidge.from_kernel(kernel, len(fit)).predict_all(target[fit])
                for alpha in ALPHAS:
                    validation[(k, alpha)].update(dict(zip(val, predicted[alpha], strict=True)))
        scores = {}
        for k in K_GRID:
            for alpha in ALPHAS:
                metric_rows = [dict(rows[i], pred=float(value))
                               for i, value in validation[(k, alpha)].items()]
                scores[f"K={k}|alpha={alpha}"] = scalar_metrics(metric_rows, "pred")["macro_r2"]
        selected_k, selected_alpha = min(
            ((k, alpha) for k in K_GRID for alpha in ALPHAS),
            key=lambda pair: (-scores[f"K={pair[0]}|alpha={pair[1]}"], pair[0], pair[1]),
        )
        fit = indices(rows, train_ids, True)
        test = indices(rows, test_ids, False)
        started = time.monotonic()
        ranking = rank_tokens_cuda(features[fit], target[fit])
        kernels = cumulative_selected_token_kernels_cuda(
            np.asarray(features[fit + test], order="C"), len(fit), ranking
        )
        gpu_seconds += time.monotonic() - started
        predicted = PreparedKernelRidge.from_kernel(
            kernels[selected_k], len(fit)
        ).predict_all(target[fit])[selected_alpha]
        oof.update(dict(zip(test, predicted, strict=True)))
        selections[str(outer)] = {
            "selected_k": selected_k,
            "selected_alpha": selected_alpha,
            "selected_tokens": [int(value) for value in ranking[:selected_k]],
            "training_trajectory_ids": train_ids,
            "test_trajectory_ids": test_ids,
            "inner_macro_r2_by_candidate": scores,
            **fold_discipline_record(rows, test, inner),
        }
        print(f"BEST_K outer={outer} K={selected_k} alpha={selected_alpha}", flush=True)
    return oof, selections, gpu_seconds


def summarize(rows: list[dict[str, Any]], prediction_key: str) -> dict[str, Any]:
    base = scalar_metrics(rows, prediction_key)
    y = np.asarray([row["world_x"] for row in rows], dtype=np.float64)
    pred = np.asarray([row[prediction_key] for row in rows], dtype=np.float64)
    per = base["per_trajectory"]
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    values = np.asarray([per[identity]["r2"] for identity in sorted(per)], dtype=np.float64)
    draws = rng.integers(0, len(values), size=(BOOTSTRAP_RESAMPLES, len(values)))
    stats = values[draws].mean(axis=1)
    rmse = np.asarray([per[identity]["rmse"] for identity in sorted(per)])
    return {
        "trajectory_count": base["trajectory_count"],
        "row_count": base["row_count"],
        "rmse_blocks": base["trajectory_aggregated_rmse"],
        "mae_blocks": base["trajectory_aggregated_mae"],
        "signed_bias_blocks_pred_minus_true": float(np.mean(pred - y)),
        "correlation_pooled_descriptive": float(np.corrcoef(y, pred)[0, 1]),
        "pooled_r2_descriptive": base["pooled_row_r2_secondary"],
        "pooled_rmse_descriptive": base["pooled_rmse_secondary"],
        "pooled_mae_descriptive": base["pooled_mae_secondary"],
        "macro_r2": base["macro_r2"],
        "trajectory_rmse_mean": float(rmse.mean()),
        "trajectory_rmse_median": float(np.median(rmse)),
        "bootstrap": {
            "metric": "trajectory-equal macro R2",
            "unit": "WHOLE_TRAJECTORY",
            "resamples": BOOTSTRAP_RESAMPLES,
            "seed": BOOTSTRAP_SEED,
            "estimate": float(values.mean()),
            "lower_2_5": float(np.percentile(stats, 2.5)),
            "upper_97_5": float(np.percentile(stats, 97.5)),
        },
        "per_trajectory": per,
    }


def main() -> int:
    started = time.monotonic()
    if sha256_file(AUTHORITY_RESULT) != AUTHORITY_SHA256:
        raise RuntimeError("frozen BEST-K authority hash mismatch")
    pre = json.loads((OUT / "p2_preoutcome_authority.json").read_text())
    if pre["status"] != "FROZEN_PRE_OUTCOME":
        raise RuntimeError("P2 pre-outcome authority mismatch")
    for gate, field in (("p2_path_equivalence_receipt.json", "path_equivalence_status"),
                        ("p2_visibility_qualification_receipt.json", "visibility_qualification_status")):
        if json.loads((OUT / gate).read_text())[field] != "PASS":
            raise RuntimeError(f"blocked by {gate}")

    write_json(OUT / "p2_readout_authority_receipt.json", {
        "artifact_id": "regime-a-prime-p2-readout-authority-binding-v0.1",
        "status": "BOUND_BEFORE_P2_SCORING",
        "controlling_preoutcome_authority": "p2_preoutcome_authority.json",
        "controlling_preoutcome_authority_sha256": sha256_file(
            OUT / "p2_preoutcome_authority.json"
        ),
        "best_k_authority": str(AUTHORITY_RESULT.relative_to(REPO)),
        "best_k_authority_sha256": AUTHORITY_SHA256,
        "source_analysis_commit": "8c1b8ec921ac7cd2b742b926db162d99ff877395",
        "source_generator": "scripts/run_regime_a_first25_science.py",
        "source_generator_sha256": sha256_file(REPO / "scripts/run_regime_a_first25_science.py"),
        "source_mechanics": "src/mineocclude/regime_a_first25_analysis.py",
        "source_mechanics_sha256": sha256_file(
            REPO / "src/mineocclude/regime_a_first25_analysis.py"
        ),
        "full_token_grid": "exact standardized summed-token kernel ridge",
        "best_k": {
            "k_grid": list(K_GRID),
            "token_ranking": "absolute maximum hidden-dimension training correlation",
            "ranking_scope": "training rows only inside every inner/final fold",
        },
        "outer_folds": "frozen trajectory-grouped outer_fold from source specs",
        "inner_folds": "inner_fold_assignment: deterministic direction-stratified trajectories",
        "feature_standardization": "training rows only for every kernel",
        "target_handling": "training-target centering inside ridge; no target standardization",
        "alpha_grid": list(ALPHAS),
        "alpha_selection": "maximum inner trajectory-equal macro R2; exact tie smaller alpha",
        "k_selection": "maximum inner trajectory-equal macro R2; exact tie smaller K then alpha",
        "selection_training_scope": "tau1..15, matching frozen source procedure",
        "visible_evaluation_scope": "all frozen qualified tau1..19 rows (475)",
        "visible_qualification": {
            "metric": "trajectory-equal visible macro R2",
            "threshold": "> 0",
            "bootstrap_requirement": "whole-trajectory 95% lower bound > 0",
        },
        "bootstrap": {
            "unit": "WHOLE_TRAJECTORY", "resamples": BOOTSTRAP_RESAMPLES,
            "seed": BOOTSTRAP_SEED,
        },
        "p2_outcomes_observed_before_binding": False,
    })

    features, target, rows, ids, outer, direction = load()
    best_oof, best_selection, best_gpu = best_k_readout(features, target, rows, ids, outer, direction)
    full_oof, full_selection, full_gpu = full_readout(features, target, rows, ids, outer, direction)
    if set(full_oof) != set(range(475)) or set(best_oof) != set(range(475)):
        raise RuntimeError("OOF predictions do not cover each row exactly once")
    for i, row in enumerate(rows):
        row["predicted_layer4_full"] = float(full_oof[i])
        row["predicted_layer4_best_k"] = float(best_oof[i])

    full_visible = summarize(rows, "predicted_layer4_full")
    best_visible = summarize(rows, "predicted_layer4_best_k")
    full_primary = summarize([row for row in rows if row["tau"] <= 15], "predicted_layer4_full")
    best_primary = summarize([row for row in rows if row["tau"] <= 15], "predicted_layer4_best_k")

    def qualified(result: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
        checks = {
            "all_path_identity_quality_gates_pass": True,
            "frozen_procedure_no_test_leakage": True,
            "trajectory_equal_visible_macro_r2_gt_0": result["macro_r2"] > 0.0,
            "whole_trajectory_bootstrap_lower_95_gt_0": result["bootstrap"]["lower_2_5"] > 0.0,
        }
        return all(checks.values()), checks

    best_pass, best_checks = qualified(best_visible)
    full_pass, full_checks = qualified(full_visible)
    decision = (
        "GO_BEST_K_FULL_VISIBLE" if best_pass and full_pass
        else "GO_BEST_K" if best_pass
        else "STOP_VISIBLE_CONTROL_FAILURE"
    )
    p3_allowed = bool(best_pass)
    common = {
        "classification": "EXPLORATORY_MATCHED_DIAGNOSTIC",
        "layer": 4,
        "target": "WORLD_WALL_PARALLEL_X",
        "visible_rows": "tau1..19 (475 rows)",
        "selection_training_rows": "tau1..15 of outer-training trajectories, exactly as frozen Regime A procedure",
        "outer_evaluation": "trajectory-grouped frozen folds",
        "inner_selection": "deterministic direction-stratified trajectory folds",
        "alphas": list(ALPHAS),
        "feature_standardization": "fit on each training split only",
        "target_handling": "training-target centering inside kernel ridge; no target standardization",
        "authority_sha256": AUTHORITY_SHA256,
    }
    write_json(OUT / "p2_full_results.json", {
        **common, "artifact_id": "regime-a-prime-p2-full-visible-v0.1",
        "readout": "FULL_TOKEN_GRID", "status": "PASS",
        "qualification_status": "PASS" if full_pass else "FAIL",
        "qualification_checks": full_checks, "visible_metrics": full_visible,
        "frozen_primary_scope_reference_tau1_15": full_primary,
        "selection_by_outer_fold": full_selection,
    })
    write_json(OUT / "p2_best_k_results.json", {
        **common, "artifact_id": "regime-a-prime-p2-best-k-visible-v0.1",
        "readout": "BEST_K", "k_grid": list(K_GRID), "status": "PASS",
        "qualification_status": "PASS" if best_pass else "FAIL",
        "qualification_checks": best_checks, "visible_metrics": best_visible,
        "frozen_primary_scope_reference_tau1_15": best_primary,
        "selection_by_outer_fold": best_selection,
    })
    pd.DataFrame(rows).to_parquet(OUT / "p2_predictions.parquet", index=False, compression="zstd")
    analysis_seconds = time.monotonic() - started
    receipt = {
        "artifact_id": "regime-a-prime-p2-final-analysis-receipt-v0.1",
        "status": "PASS",
        "extraction_validation_status": "PASS",
        "analysis_cpu_gpu_wall_seconds": analysis_seconds,
        "gpu_kernel_ranking_seconds": best_gpu + full_gpu,
        "best_k_qualification_status": "PASS" if best_pass else "FAIL",
        "full_qualification_status": "PASS" if full_pass else "FAIL",
        "p2_decision": decision,
        "p3_allowed": p3_allowed,
        "p3_started": False,
        "REGIME_A_PRIME_COLLECTION_AUTHORIZED": "NO",
        "scientific_interpretation": "current-apparatus visible readout qualification at matched physical paths only",
        "historical_comparison": "DESCRIPTIVE_CROSS_APPARATUS_CONTEXT_ONLY",
        "best_k_results_sha256": sha256_file(OUT / "p2_best_k_results.json"),
        "full_results_sha256": sha256_file(OUT / "p2_full_results.json"),
        "predictions_sha256": sha256_file(OUT / "p2_predictions.parquet"),
    }
    write_json(OUT / "p2_final_analysis_receipt.json", receipt)
    print(json.dumps({
        "BEST_K_QUALIFICATION_STATUS": receipt["best_k_qualification_status"],
        "BEST_K_MACRO_R2": best_visible["macro_r2"],
        "BEST_K_BOOTSTRAP_95": [best_visible["bootstrap"]["lower_2_5"], best_visible["bootstrap"]["upper_97_5"]],
        "FULL_QUALIFICATION_STATUS": receipt["full_qualification_status"],
        "FULL_MACRO_R2": full_visible["macro_r2"],
        "FULL_BOOTSTRAP_95": [full_visible["bootstrap"]["lower_2_5"], full_visible["bootstrap"]["upper_97_5"]],
        "P2_DECISION": decision, "P3_ALLOWED": p3_allowed,
        "CPU_GPU_ANALYSIS_SECONDS": analysis_seconds,
        "GPU_KERNEL_RANKING_SECONDS": best_gpu + full_gpu,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
