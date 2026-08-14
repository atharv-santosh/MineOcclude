#!/usr/bin/env python3
"""One-pass frozen scientific analysis for MineOcclude Regime-A first25."""

from __future__ import annotations

import gc
import hashlib
import json
import subprocess
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import boto3
import numpy as np
import pandas as pd

from mineocclude.regime_a_first25_analysis import (
    ALPHAS,
    BINS,
    K_GRID,
    PreparedKernelRidge,
    bootstrap_intervals,
    canonical_sha256,
    cumulative_selected_token_kernels_cuda,
    full_kernel_cuda,
    inner_fold_assignment,
    metrics_by_bin,
    rank_tokens_cuda,
    scalar_metrics,
    screen_metrics,
)


REPO = Path(__file__).resolve().parents[1]
ROOT = REPO / "docs/status/integration/regime_a_occlusion_extraction_v0_1"
OUT = ROOT / "first25_analysis"
CACHE = Path("/mnt/sagemaker-nvme/mineocclude-regime-a-first25-analysis-input")
KERNELS = CACHE / "kernels"
BUCKET = "sagemaker-us-east-1-323206973672"
DONORS = ROOT / "v2/null_donor_manifest.jsonl"
PRIMARY_BINS = {"SHORT", "INTERMEDIATE", "LONG", "NEAR_CONTEXT"}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=REPO, text=True).strip()


def read_json(path: Path):
    return json.loads(path.read_text())


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


class Analysis:
    def __init__(self) -> None:
        self.rows = read_json(CACHE / "a5_rows.json")
        self.context = {row["trajectory_id"]: row for row in read_json(CACHE / "a5_trajectory_context.json")}
        self.binding = read_json(OUT / "analysis_input_binding.json")
        self.a5 = read_json(OUT / "a5_quality_visibility_confound_receipt.json")
        if self.a5.get("SCIENTIFIC_OUTCOME_OPENING_AUTHORIZED") != "YES" or self.a5.get("status") != "PASS":
            raise RuntimeError("A5 did not authorize scientific outcome opening")
        projection = [{key: row[key] for key in ("trajectory_id", "activation_row", "model_frame_idx", "server_tick", "tau", "duration_bin", "outer_fold")} for row in self.rows]
        if canonical_sha256(projection) != self.a5["row_identity_hash"]:
            raise RuntimeError("row identity hash changed after A5")
        self.row_by_index = {index: row for index, row in enumerate(self.rows)}
        self.ids = sorted({row["trajectory_id"] for row in self.rows})
        self.direction = {row["trajectory_id"]: row["direction"] for row in self.rows}
        self.outer = {row["trajectory_id"]: int(row["outer_fold"]) for row in self.rows}
        self.analysis_commit = git("rev-parse", "HEAD")
        self.client = boto3.client("s3")
        KERNELS.mkdir(parents=True, exist_ok=True)
        self.runtime = {"started_utc": now(), "kernel_builds": []}

    def indices(self, identities, primary_only: bool) -> list[int]:
        identity_set = set(identities)
        return [index for index, row in self.row_by_index.items() if row["trajectory_id"] in identity_set and (not primary_only or row["tau"] <= 15)]

    def ensure_layer(self, layer: int) -> None:
        provenance = self.binding["activation_provenance"]

        def one(identity: str) -> None:
            record = provenance[identity][layer]
            path = CACHE / identity / f"activations/layer_{layer:02d}.npy"
            if path.is_file() and path.stat().st_size == record["byte_size"] and sha_file(path) == record["sha256"]:
                return
            path.parent.mkdir(parents=True, exist_ok=True)
            uri = record["s3_uri"]
            key = uri.split(f"s3://{BUCKET}/", 1)[1]
            partial = path.with_suffix(".npy.partial")
            self.client.download_file(BUCKET, key, str(partial))
            if partial.stat().st_size != record["byte_size"] or sha_file(partial) != record["sha256"]:
                raise RuntimeError(f"activation download hash mismatch: {identity} layer {layer}")
            partial.replace(path)

        with ThreadPoolExecutor(max_workers=10) as pool:
            list(pool.map(one, self.ids))

    def load_layer(self, layer: int) -> np.ndarray:
        self.ensure_layer(layer)
        arrays = [np.load(CACHE / identity / f"activations/layer_{layer:02d}.npy", mmap_mode="r") for identity in self.ids]
        result = np.concatenate(arrays, axis=0)
        if result.shape != (475, 336, 2048) or result.dtype != np.float16 or not np.isfinite(result).all():
            raise RuntimeError(f"opened activation tensor validation failed for layer {layer}")
        return result

    def kernel(self, features: np.ndarray, layer: int, outer: int, tag: str, train: list[int], predict: list[int], cache: bool) -> PreparedKernelRidge:
        path = KERNELS / f"layer_{layer:02d}_outer_{outer}_{tag}.npy"
        if cache and path.is_file():
            matrix = np.load(path)
        else:
            scope = np.asarray(features[np.asarray(train + predict, dtype=np.int64)], order="C")
            started = time.perf_counter()
            matrix = full_kernel_cuda(scope, len(train))
            self.runtime["kernel_builds"].append({"layer": layer, "outer_fold": outer, "tag": tag, "training_rows": len(train), "prediction_rows": len(predict), "seconds": time.perf_counter() - started})
            if cache:
                np.save(path, matrix)
            del scope
        return PreparedKernelRidge.from_kernel(matrix, len(train))

    def solvers(self, features: np.ndarray, layer: int, cache: bool) -> dict[tuple[int, str], dict]:
        output = {}
        for outer in range(5):
            train_ids = [identity for identity in self.ids if self.outer[identity] != outer]
            test_ids = [identity for identity in self.ids if self.outer[identity] == outer]
            inner = inner_fold_assignment(train_ids, {identity: self.direction[identity] for identity in train_ids}, outer)
            for fold in range(5):
                fit_ids = [identity for identity in train_ids if inner[identity] != fold]
                validation_ids = [identity for identity in train_ids if inner[identity] == fold]
                fit = self.indices(fit_ids, True)
                validation = self.indices(validation_ids, True)
                output[(outer, f"inner_{fold}")] = {"solver": self.kernel(features, layer, outer, f"inner_{fold}", fit, validation, cache), "train": fit, "predict": validation}
            fit = self.indices(train_ids, True)
            test = self.indices(test_ids, False)
            output[(outer, "final")] = {"solver": self.kernel(features, layer, outer, "final", fit, test, cache), "train": fit, "predict": test}
        return output

    def nested_scalar(self, solvers: dict, target: np.ndarray) -> tuple[dict[int, float], dict]:
        oof = {}
        selections = {}
        for outer in range(5):
            validation = {alpha: {} for alpha in ALPHAS}
            for inner in range(5):
                unit = solvers[(outer, f"inner_{inner}")]
                predicted = unit["solver"].predict_all(target[unit["train"]])
                for alpha in ALPHAS:
                    validation[alpha].update(dict(zip(unit["predict"], predicted[alpha], strict=True)))
            scores = {}
            for alpha in ALPHAS:
                metric_rows = [dict(self.row_by_index[index], world_x=float(target[index]), pred=float(value)) for index, value in validation[alpha].items()]
                scores[str(alpha)] = scalar_metrics(metric_rows, "pred")["macro_r2"]
            selected = min(ALPHAS, key=lambda alpha: (-scores[str(alpha)], alpha))
            final = solvers[(outer, "final")]
            predicted = final["solver"].predict_all(target[final["train"]])[selected]
            oof.update(dict(zip(final["predict"], predicted, strict=True)))
            selections[str(outer)] = {"selected_alpha": selected, "inner_macro_r2_by_alpha": scores}
        if set(oof) != set(range(len(self.rows))):
            raise RuntimeError("nested OOF did not predict each frozen row exactly once")
        return oof, selections

    def nested_screen(self, solvers: dict, target: np.ndarray) -> tuple[dict[int, tuple[float, float]], dict]:
        oof = {}
        selections = {}
        for outer in range(5):
            validation = {alpha: {0: {}, 1: {}} for alpha in ALPHAS}
            for inner in range(5):
                unit = solvers[(outer, f"inner_{inner}")]
                for dim in range(2):
                    predicted = unit["solver"].predict_all(target[unit["train"], dim])
                    for alpha in ALPHAS:
                        validation[alpha][dim].update(dict(zip(unit["predict"], predicted[alpha], strict=True)))
            scores = {}
            for alpha in ALPHAS:
                component_scores = []
                for dim in range(2):
                    metric_rows = [dict(self.row_by_index[index], world_x=float(target[index, dim]), pred=float(value)) for index, value in validation[alpha][dim].items()]
                    component_scores.append(scalar_metrics(metric_rows, "pred")["macro_r2"])
                scores[str(alpha)] = float(np.mean(component_scores))
            selected = min(ALPHAS, key=lambda alpha: (-scores[str(alpha)], alpha))
            final = solvers[(outer, "final")]
            dimensions = [final["solver"].predict_all(target[final["train"], dim])[selected] for dim in range(2)]
            for offset, index in enumerate(final["predict"]):
                oof[index] = (float(dimensions[0][offset]), float(dimensions[1][offset]))
            selections[str(outer)] = {"selected_alpha": selected, "inner_joint_macro_r2_by_alpha": scores}
        return oof, selections

    def best_k(self, features: np.ndarray, target: np.ndarray) -> tuple[dict[int, float], dict]:
        oof = {}
        selections = {}
        for outer in range(5):
            train_ids = [identity for identity in self.ids if self.outer[identity] != outer]
            test_ids = [identity for identity in self.ids if self.outer[identity] == outer]
            inner = inner_fold_assignment(train_ids, {identity: self.direction[identity] for identity in train_ids}, outer)
            validation = {(k, alpha): {} for k in K_GRID for alpha in ALPHAS}
            for fold in range(5):
                fit = self.indices([identity for identity in train_ids if inner[identity] != fold], True)
                val = self.indices([identity for identity in train_ids if inner[identity] == fold], True)
                ranking = rank_tokens_cuda(features[fit], target[fit])
                kernels = cumulative_selected_token_kernels_cuda(features[fit + val], len(fit), ranking)
                for k, matrix in kernels.items():
                    predicted = PreparedKernelRidge.from_kernel(matrix, len(fit)).predict_all(target[fit])
                    for alpha in ALPHAS:
                        validation[(k, alpha)].update(dict(zip(val, predicted[alpha], strict=True)))
            scores = {}
            for k in K_GRID:
                for alpha in ALPHAS:
                    metric_rows = [dict(self.row_by_index[index], pred=float(value)) for index, value in validation[(k, alpha)].items()]
                    scores[f"K={k}|alpha={alpha}"] = scalar_metrics(metric_rows, "pred")["macro_r2"]
            selected_k, selected_alpha = min(((k, alpha) for k in K_GRID for alpha in ALPHAS), key=lambda pair: (-scores[f"K={pair[0]}|alpha={pair[1]}"], pair[0], pair[1]))
            fit = self.indices(train_ids, True)
            test = self.indices(test_ids, False)
            ranking = rank_tokens_cuda(features[fit], target[fit])
            kernels = cumulative_selected_token_kernels_cuda(features[fit + test], len(fit), ranking)
            predicted = PreparedKernelRidge.from_kernel(kernels[selected_k], len(fit)).predict_all(target[fit])[selected_alpha]
            oof.update(dict(zip(test, predicted, strict=True)))
            selections[str(outer)] = {
                "selected_k": selected_k, "selected_alpha": selected_alpha,
                "selected_tokens": [int(value) for value in ranking[:selected_k]],
                "trajectory_ids_used": train_ids, "shared_across_bins": True, "shared_across_directions": True,
                "inner_macro_r2_by_candidate": scores,
            }
        return oof, selections

    def baselines(self, prediction_rows: list[dict]) -> dict:
        for row in prediction_rows:
            context = self.context[row["trajectory_id"]]
            row["predicted_last_visible"] = context["last_visible_world_x"]
            coefficient = np.polyfit(context["visible_context_time_seconds"], context["visible_context_world_x"], deg=1)
            row["predicted_constant_velocity"] = float(np.polyval(coefficient, row["server_tick"] / 20.0))
        for outer in range(5):
            train_ids = {identity for identity in self.ids if self.outer[identity] != outer}
            means = defaultdict(list)
            for row in self.rows:
                if row["trajectory_id"] in train_ids:
                    means[(row["direction"], row["duration_bin"])].append(row["world_x"])
            for row in prediction_rows:
                if row["outer_fold"] == outer:
                    row["predicted_training_mean"] = float(np.mean(means[(row["direction"], row["duration_bin"])]))
            # Continuous time-only diagnostic: prospectively fixed linear clock,
            # direction, and direction-by-clock terms; outer-training only.
            train_rows = [row for row in self.rows if row["trajectory_id"] in train_ids and row["tau"] <= 15]
            x = np.asarray([[1.0, 1.0 if row["direction"] == "LEFT_TO_RIGHT" else -1.0, row["tau"], row["tau"] * (1.0 if row["direction"] == "LEFT_TO_RIGHT" else -1.0)] for row in train_rows])
            y = np.asarray([row["world_x"] for row in train_rows])
            coefficient, *_ = np.linalg.lstsq(x, y, rcond=None)
            for row in prediction_rows:
                if row["outer_fold"] == outer:
                    sign = 1.0 if row["direction"] == "LEFT_TO_RIGHT" else -1.0
                    row["predicted_time_only_linear"] = float(np.asarray([1.0, sign, row["tau"], row["tau"] * sign]) @ coefficient)
        return {
            name: {
                "overall": scalar_metrics([row for row in prediction_rows if row["tau"] <= 15], key),
                "bins": metrics_by_bin(prediction_rows, key),
            }
            for name, key in {
                "LAST_VISIBLE_POSITION": "predicted_last_visible",
                "CONSTANT_VELOCITY_EXTRAPOLATION": "predicted_constant_velocity",
                "TRAINING_MEAN": "predicted_training_mean",
                "TIME_ONLY_LINEAR_CONFOUND_DIAGNOSTIC": "predicted_time_only_linear",
            }.items()
        }

    def null(self, solvers: dict, target: np.ndarray, observed: float) -> dict:
        donor_rows = read_jsonl(DONORS)
        grouped = {(int(row["replicate"]), int(row["outer_fold"])): row["mapping"] for row in donor_rows}
        target_lookup = {(row["trajectory_id"], row["tau"]): target[index] for index, row in self.row_by_index.items()}
        null_stats, alpha_audit = [], {}
        for replicate in range(49):
            predictions = {}
            alpha_audit[str(replicate)] = {}
            for outer in range(5):
                mapping = grouped[(replicate, outer)]
                validation = {alpha: {} for alpha in ALPHAS}
                mapped_truth = {}
                for inner in range(5):
                    unit = solvers[(outer, f"inner_{inner}")]
                    train_y = np.asarray([target_lookup[(mapping[self.row_by_index[index]["trajectory_id"]], self.row_by_index[index]["tau"])] for index in unit["train"]])
                    predicted = unit["solver"].predict_all(train_y)
                    for index in unit["predict"]:
                        row = self.row_by_index[index]
                        mapped_truth[index] = target_lookup[(mapping[row["trajectory_id"]], row["tau"])]
                    for alpha in ALPHAS:
                        validation[alpha].update(dict(zip(unit["predict"], predicted[alpha], strict=True)))
                scores = {}
                for alpha in ALPHAS:
                    metric_rows = [dict(self.row_by_index[index], world_x=float(mapped_truth[index]), pred=float(value)) for index, value in validation[alpha].items()]
                    scores[str(alpha)] = scalar_metrics(metric_rows, "pred")["macro_r2"]
                selected = min(ALPHAS, key=lambda alpha: (-scores[str(alpha)], alpha))
                final = solvers[(outer, "final")]
                train_y = np.asarray([target_lookup[(mapping[self.row_by_index[index]["trajectory_id"]], self.row_by_index[index]["tau"])] for index in final["train"]])
                predicted = final["solver"].predict_all(train_y)[selected]
                predictions.update(dict(zip(final["predict"], predicted, strict=True)))
                alpha_audit[str(replicate)][str(outer)] = {"selected_alpha": selected, "inner_null_macro_r2_by_alpha": scores}
            metric_rows = [dict(self.row_by_index[index], pred=float(predictions[index])) for index in range(len(self.rows)) if self.row_by_index[index]["tau"] <= 15]
            null_stats.append(scalar_metrics(metric_rows, "pred")["macro_r2"])
        count = sum(value >= observed for value in null_stats)
        return {
            "B": 49, "observed_macro_r2": observed, "null_statistics": null_stats,
            "null_min": min(null_stats), "null_median": float(np.median(null_stats)), "null_max": max(null_stats),
            "count_null_gte_observed": count, "empirical_p": (1 + count) / 50.0,
            "one_sided": True, "heldout_targets_true": True, "alpha_selection_repeated_training_only": True,
            "selected_alpha_audit": alpha_audit,
        }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    analysis = Analysis()
    world = np.asarray([row["world_x"] for row in analysis.rows], dtype=np.float64)
    screen = np.asarray([[row["token_row"], row["token_col"]] for row in analysis.rows], dtype=np.float64)

    # Primary outcome is opened first, from layer 4 only.
    layer4 = analysis.load_layer(4)
    layer4_solvers = analysis.solvers(layer4, 4, cache=True)
    primary_oof, primary_selection = analysis.nested_scalar(layer4_solvers, world)
    prediction_rows = [dict(row, predicted_layer4_full=float(primary_oof[index])) for index, row in enumerate(analysis.rows)]
    primary_rows = [row for row in prediction_rows if row["tau"] <= 15]
    primary = scalar_metrics(primary_rows, "predicted_layer4_full")
    duration = metrics_by_bin(prediction_rows, "predicted_layer4_full")
    fold_metrics = {str(fold): scalar_metrics([row for row in primary_rows if row["outer_fold"] == fold], "predicted_layer4_full") for fold in range(5)}

    baseline_results = analysis.baselines(prediction_rows)
    best_oof, best_selection = analysis.best_k(layer4, world)
    for index, row in enumerate(prediction_rows):
        row["predicted_layer4_best_k"] = float(best_oof[index])
    best_results = {
        "role": "SECONDARY_CANNOT_RESCUE_GATE", "selection": best_selection,
        "overall": scalar_metrics([row for row in prediction_rows if row["tau"] <= 15], "predicted_layer4_best_k"),
        "bins": metrics_by_bin(prediction_rows, "predicted_layer4_best_k"),
    }
    token_sets = [set(row["selected_tokens"]) for row in best_selection.values()]
    best_results["selection_stability_pairwise_jaccard"] = [len(token_sets[i] & token_sets[j]) / len(token_sets[i] | token_sets[j]) for i in range(5) for j in range(i + 1, 5)]

    screen_oof, screen_selection = analysis.nested_screen(layer4_solvers, screen)
    for index, row in enumerate(prediction_rows):
        row["predicted_token_row"], row["predicted_token_col"] = screen_oof[index]
    screen_overall = screen_metrics([row for row in prediction_rows if row["tau"] <= 15])
    screen_bins = {name: screen_metrics([row for row in prediction_rows if row["duration_bin"] == name]) for name in BINS}
    del layer4
    gc.collect()

    # Predeclared correlated descriptive profile.  Layer 4 reuses its frozen
    # primary predictions and every other layer is opened exactly once.
    layer_profile = []
    for layer in range(20):
        if layer == 4:
            result = primary
            selections = primary_selection
        else:
            features = analysis.load_layer(layer)
            solvers = analysis.solvers(features, layer, cache=False)
            oof, selections = analysis.nested_scalar(solvers, world)
            rows = [dict(row, pred=float(oof[index])) for index, row in enumerate(analysis.rows) if row["tau"] <= 15]
            result = scalar_metrics(rows, "pred")
            del solvers, features
            gc.collect()
        layer_profile.append({"layer": layer, "macro_r2": result["macro_r2"], "trajectory_aggregated_rmse": result["trajectory_aggregated_rmse"], "trajectory_aggregated_mae": result["trajectory_aggregated_mae"], "outer_selection": selections})

    null_results = analysis.null(layer4_solvers, world, primary["macro_r2"])
    bootstrap_hash = "54f47bfb7167cb0a74a58b42f363258080501a05ec5519cf1c9c3edb113fd785"
    seed_payload = f"{bootstrap_hash}|REGIME_A_BOOTSTRAP_V1"
    bootstrap_seed = int.from_bytes(hashlib.sha256(seed_payload.encode()).digest()[:8], "big") & ((1 << 63) - 1)
    bootstrap = bootstrap_intervals(primary, duration, replicates=10000, seed=bootstrap_seed)

    error = np.abs(np.asarray([row["world_x"] - row["predicted_layer4_full"] for row in prediction_rows]))
    tau = np.asarray([row["tau"] for row in prediction_rows], dtype=np.float64)
    slope, intercept = np.polyfit(tau, error, 1)
    duration_result = {"bins": duration, "descriptive_absolute_error_vs_tau_linear_trend": {"slope_blocks_per_tau": float(slope), "intercept_blocks": float(intercept), "inferential_role": "DESCRIPTIVE_ONLY_NO_MONOTONICITY_REQUIREMENT"}}

    common = {
        "created_utc": now(), "analysis_code_commit": analysis.analysis_commit,
        "analysis_input_binding_sha256": sha_file(OUT / "analysis_input_binding.json"),
        "a5_receipt_sha256": sha_file(OUT / "a5_quality_visibility_confound_receipt.json"),
        "row_identity_hash": analysis.a5["row_identity_hash"],
        "primary_authority": {"layer": 4, "readout": "FULL_TOKEN_GRID", "target": "WORLD_WALL_PARALLEL_X", "rows": "tau1..15", "alphas": list(ALPHAS)},
    }
    artifacts = {
        "slice_primary_results.json": {**common, "overall": primary, "outer_folds": fold_metrics, "outer_selection": primary_selection},
        "slice_duration_results.json": {**common, **duration_result},
        "slice_baselines.json": {**common, "baselines": baseline_results, "neural_vs_kinematics_role": "DESCRIPTIVE_ONLY_NO_PREDECLARED_GATE"},
        "slice_best_k_results.json": {**common, **best_results},
        "slice_secondary_target_results.json": {**common, "target": "CONTINUOUS_SCREEN_TOKEN_COORDINATE_ROW_COL", "outer_selection": screen_selection, "overall": screen_overall, "bins": screen_bins, "role": "SECONDARY_CANNOT_RESCUE_GATE"},
        "slice_all_layer_profile.json": {**common, "role": "DESCRIPTIVE_CORRELATED_NON_CONFIRMATORY", "fixed_primary_layer": 4, "layers": layer_profile, "best_descriptive_layer": max(layer_profile, key=lambda row: row["macro_r2"])["layer"], "layer_reselection_for_primary": False},
        "slice_null_results.json": {**common, **null_results},
        "slice_bootstrap_results.json": {**common, "replicates": 10000, "resampling_unit": "whole heldout trajectory", "seed": bootstrap_seed, "seed_derivation_input": seed_payload, "hard_gate": False, "intervals": bootstrap},
    }
    for name, value in artifacts.items():
        write_json(OUT / name, value)

    predictions_path = OUT / "slice_predictions.parquet"
    pd.DataFrame(prediction_rows).to_parquet(predictions_path, index=False, compression="zstd")

    gate = {
        "A5_quality_pass": True, "all_primary_tss_gt_zero": True,
        "primary_layer4_full_macro_r2": primary["macro_r2"], "primary_macro_r2_gt_zero": primary["macro_r2"] > 0,
        "B49_empirical_p": null_results["empirical_p"], "B49_p_lte_0_05": null_results["empirical_p"] <= 0.05,
        "bootstrap_used_as_hard_gate": False, "best_k_used_to_rescue_gate": False, "secondary_target_used_to_rescue_gate": False,
    }
    passed = all((gate["A5_quality_pass"], gate["all_primary_tss_gt_zero"], gate["primary_macro_r2_gt_zero"], gate["B49_p_lte_0_05"]))
    adjudication = {
        **common, "continuation_gate": gate,
        "scientific_adjudication": "PASS_CONTINUE" if passed else "FAIL_NO_DEFENSIBLE_DECODING",
        "primary_claim_supported": passed,
        "authorized_next_step": "PREPARE_PRE_EXPANSION_DESIGN_ONLY; DO_NOT_LAUNCH_EXPANSION" if passed else "STOP_EXPANSION_AND_PRESERVE_CONTINUOUS_EVIDENCE",
    }
    write_json(OUT / "continuation_adjudication.json", adjudication)
    if passed:
        write_json(OUT / "a9_preexpansion_decision_packet.json", {
            **common, "status": "READY_FOR_PRE_EXPANSION_DESIGN_NOT_EXECUTION",
            "retained_trajectory_ids": analysis.ids, "trajectory_count": 25,
            "launch_authorized": False, "speed_noise_cells_collected": False,
            "occluder_only_control_executed": False, "run_b_started": False, "run_c_started": False,
        })

    result_paths = sorted([OUT / name for name in artifacts] + [predictions_path, OUT / "continuation_adjudication.json"] + ([OUT / "a9_preexpansion_decision_packet.json"] if passed else []))
    validation = {
        **common, "status": "PASS", "prediction_row_count": len(prediction_rows),
        "one_oof_prediction_per_frozen_row": len(prediction_rows) == 475,
        "row_identity_hash_revalidated": True, "all_predictions_finite": bool(pd.DataFrame(prediction_rows).select_dtypes(include=[np.number]).apply(np.isfinite).all().all()),
        "result_artifacts": [{"path": str(path.relative_to(REPO)), "sha256": sha_file(path), "byte_size": path.stat().st_size} for path in result_paths],
        "runtime": {**analysis.runtime, "completed_utc": now()},
    }
    write_json(OUT / "slice_validation_receipt.json", validation)
    print(json.dumps({"status": adjudication["scientific_adjudication"], "macro_r2": primary["macro_r2"], "p": null_results["empirical_p"], "bootstrap": bootstrap["macro_r2"], "best_layer": max(layer_profile, key=lambda row: row["macro_r2"])["layer"]}, indent=2))


if __name__ == "__main__":
    main()
