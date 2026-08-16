#!/usr/bin/env python3
"""EXPLORATORY_FORENSIC_DIAGNOSTIC_ONLY: direct Regime A lag reanalysis.

Uses only persisted Regime A layer-4 activations, server-state logs, frozen row
identities/procedures, and the independently measured physical FIR kernel. It
does not collect data or modify any historical result.
"""

from __future__ import annotations

import hashlib
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import boto3
import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[6]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "src"))

from mineocclude.regime_a_first25_analysis import scalar_metrics  # noqa: E402
from scripts.run_regime_a_first25_science import Analysis  # noqa: E402
from scripts.run_regime_a_first25_science import KERNELS as FROZEN_KERNEL_CACHE  # noqa: E402

CONF = REPO / "docs/status/integration/regime_a_occlusion_extraction_v0_1/first25_analysis"
P1 = REPO / "docs/status/integration/regime_a_prime_qualification_v0_1/p1_last_seen_rows.parquet"
CACHE = Path("/mnt/sagemaker-nvme/mineocclude-regime-a-direct-lag-reanalysis-v0-1")
BUCKET = "sagemaker-us-east-1-323206973672"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def download_verified(client, key: str, digest: str, destination: Path) -> None:
    if destination.is_file() and sha256_file(destination) == digest:
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(destination.suffix + ".partial")
    client.download_file(BUCKET, key, str(partial))
    if sha256_file(partial) != digest:
        raise RuntimeError(f"download hash mismatch: {key}")
    partial.replace(destination)


def fetch_existing_inputs(ids: list[str], binding: dict) -> dict[str, Path]:
    """Retrieve only already-persisted, receipt-hashed evidence."""
    client = boto3.client("s3")
    state_paths: dict[str, Path] = {}

    def one(identity: str) -> None:
        activation = binding["activation_provenance"][identity][4]
        activation_key = activation["s3_uri"].split(f"s3://{BUCKET}/", 1)[1]
        download_verified(
            client,
            activation_key,
            activation["sha256"],
            CACHE / identity / "activations/layer_04.npy",
        )

        receipt_record = next(
            record for record in binding["durable_receipts"] if record["trajectory_id"] == identity
        )
        receipt_key = receipt_record["s3_uri"].split(f"s3://{BUCKET}/", 1)[1]
        receipt_bytes = client.get_object(Bucket=BUCKET, Key=receipt_key)["Body"].read()
        if hashlib.sha256(receipt_bytes).hexdigest() != receipt_record["sha256"]:
            raise RuntimeError(f"durable receipt hash mismatch: {identity}")
        receipt = json.loads(receipt_bytes)
        candidates = [
            record
            for record in receipt["objects"]
            if record["key"].endswith("/package_v0_1/server_state.jsonl")
            and "/capture_validation/" in record["key"]
        ]
        if len(candidates) != 1:
            raise RuntimeError(f"server-state object is ambiguous for {identity}")
        state = candidates[0]
        state_path = CACHE / identity / "server_state.jsonl"
        download_verified(client, state["key"], state["local_sha256"], state_path)
        state_paths[identity] = state_path

    with ThreadPoolExecutor(max_workers=10) as pool:
        list(pool.map(one, ids))
    return state_paths


def load_state(path: Path) -> dict[int, float]:
    rows = [json.loads(line) for line in path.read_text().splitlines() if line]
    result = {
        int(row["server_tick"]): float(row["state"]["wall_parallel_position_blocks"])
        for row in rows
    }
    if sorted(result) != list(range(len(result))):
        raise RuntimeError(f"server-state ticks are not dense: {path}")
    return result


def convolved_position(state: dict[int, float], tick: int, kernel: np.ndarray) -> float:
    return float(sum(weight * state[max(0, tick - lag)] for lag, weight in enumerate(kernel)))


def metric(rows: list[dict], prediction: str) -> dict:
    result = scalar_metrics(rows, prediction)
    return {
        "trajectory_count": result["trajectory_count"],
        "row_count": result["row_count"],
        "macro_r2": result["macro_r2"],
        "trajectory_aggregated_rmse": result["trajectory_aggregated_rmse"],
        "trajectory_aggregated_mae": result["trajectory_aggregated_mae"],
    }


def refit_baselines(rows: list[dict], ids: list[str], outer: dict[str, int]) -> None:
    for fold in range(5):
        training_ids = {identity for identity in ids if outer[identity] != fold}
        means: dict[tuple[str, str], list[float]] = {}
        for row in rows:
            if row["trajectory_id"] in training_ids:
                means.setdefault((row["direction"], row["duration_bin"]), []).append(
                    row["world_x"]
                )
        training = [
            row for row in rows if row["trajectory_id"] in training_ids and row["tau"] <= 15
        ]
        design = np.asarray(
            [
                [1.0, sign, row["tau"], row["tau"] * sign]
                for row in training
                for sign in [1.0 if row["direction"] == "LEFT_TO_RIGHT" else -1.0]
            ],
            dtype=np.float64,
        )
        target = np.asarray([row["world_x"] for row in training], dtype=np.float64)
        coefficients, *_ = np.linalg.lstsq(design, target, rcond=None)
        for row in rows:
            if row["outer_fold"] != fold:
                continue
            row["predicted_training_mean_corrected"] = float(
                np.mean(means[(row["direction"], row["duration_bin"])])
            )
            sign = 1.0 if row["direction"] == "LEFT_TO_RIGHT" else -1.0
            row["predicted_time_only_corrected"] = float(
                np.asarray([1.0, sign, row["tau"], row["tau"] * sign]) @ coefficients
            )


def main(kernel_path: Path, output_path: Path) -> None:
    kernel_document = json.loads(kernel_path.read_text())
    kernel = np.asarray(kernel_document["mean_kernel"], dtype=np.float64)
    kernel /= kernel.sum()

    historical = pd.read_parquet(CONF / "slice_predictions.parquet").sort_values(
        ["trajectory_id", "tau"]
    ).reset_index(drop=True)
    p1 = pd.read_parquet(P1).sort_values(["trajectory_id", "tau"]).reset_index(drop=True)
    if not historical[["trajectory_id", "tau"]].equals(p1[["trajectory_id", "tau"]]):
        raise RuntimeError("P1 and frozen prediction row identities differ")
    binding = json.loads((CONF / "analysis_input_binding.json").read_text())
    ids = sorted(historical.trajectory_id.unique())
    state_paths = fetch_existing_inputs(ids, binding)
    states = {identity: load_state(path) for identity, path in state_paths.items()}

    rows = historical.to_dict("records")
    max_historical_target_error = 0.0
    for row in rows:
        state = states[row["trajectory_id"]]
        tick = int(row["server_tick"])
        max_historical_target_error = max(
            max_historical_target_error, abs(state[tick] - float(row["world_x"]))
        )
        row["historical_world_x"] = float(row["world_x"])
        row["world_x"] = convolved_position(state, tick, kernel)
    # Parquet/JSON decimal round-tripping differs by at most one binary64 ULP.
    # This guard is an encoding check, not a scientific tolerance.
    if max_historical_target_error > 2e-15:
        raise RuntimeError("persisted target does not match persisted server state")

    # Reuse the frozen full-grid and BEST-K procedures directly. Feature kernels
    # are target-independent; BEST-K ranking is recomputed from corrected targets.
    analysis = object.__new__(Analysis)
    analysis.rows = rows
    analysis.row_by_index = {index: row for index, row in enumerate(rows)}
    analysis.ids = ids
    analysis.direction = {
        identity: next(row["direction"] for row in rows if row["trajectory_id"] == identity)
        for identity in ids
    }
    analysis.outer = {
        identity: int(next(row["outer_fold"] for row in rows if row["trajectory_id"] == identity))
        for identity in ids
    }
    analysis.runtime = {"kernel_builds": []}
    FROZEN_KERNEL_CACHE.mkdir(parents=True, exist_ok=True)

    arrays = [
        np.load(CACHE / identity / "activations/layer_04.npy", mmap_mode="r") for identity in ids
    ]
    features = np.concatenate(arrays, axis=0)
    if features.shape != (475, 336, 2048) or features.dtype != np.float16:
        raise RuntimeError("persisted layer-4 activation shape/dtype mismatch")
    target = np.asarray([row["world_x"] for row in rows], dtype=np.float64)
    solvers = analysis.solvers(features, 4, cache=True)
    full_oof, full_selection = analysis.nested_scalar(solvers, target)
    best_oof, best_selection = analysis.best_k(features, target)
    for index, row in enumerate(rows):
        row["predicted_layer4_full_corrected"] = float(full_oof[index])
        row["predicted_layer4_best_k_corrected"] = float(best_oof[index])
    refit_baselines(rows, ids, analysis.outer)

    # The corrected last-seen value is the FIR-depicted physical position at the
    # persisted evidence frame. It is descriptive where that frame exists.
    p1_by_key = {
        (row.trajectory_id, int(row.tau)): row for row in p1.itertuples(index=False)
    }
    for row in rows:
        evidence_frame = p1_by_key[(row["trajectory_id"], row["tau"])].last_rendered_evidence_frame
        row["predicted_last_seen_corrected"] = (
            None
            if pd.isna(evidence_frame)
            else convolved_position(states[row["trajectory_id"]], int(evidence_frame), kernel)
        )

    # Separate sensitivity required by the review: keep the authoritative
    # historical hidden target fixed and correct only what the last-visible
    # frame physically depicted. This is distinct from the refit above and
    # directly checks the known SHORT comparison change.
    target_authoritative_rows = p1.to_dict("records")
    for row in target_authoritative_rows:
        evidence_frame = row["last_rendered_evidence_frame"]
        row["predicted_last_seen_fir_corrected"] = (
            None
            if pd.isna(evidence_frame)
            else convolved_position(
                states[row["trajectory_id"]], int(evidence_frame), kernel
            )
        )

    domains = {
        "FULL_TAU1_15": lambda row: row["tau"] <= 15,
        "SHORT": lambda row: row["duration_bin"] == "SHORT",
        "INTERMEDIATE": lambda row: row["duration_bin"] == "INTERMEDIATE",
        "LONG": lambda row: row["duration_bin"] == "LONG",
        "NEAR_CONTEXT": lambda row: row["duration_bin"] == "NEAR_CONTEXT",
        "MATCHED_SPAN_TAU8_15": lambda row: 8 <= row["tau"] <= 15,
        "BEYOND_CONTEXT": lambda row: row["duration_bin"] == "BEYOND_CONTEXT",
    }
    results = {}
    for name, select in domains.items():
        selected = [row for row in rows if select(row)]
        result = {
            "neural_full_corrected": metric(selected, "predicted_layer4_full_corrected"),
            "neural_best_k_corrected": metric(selected, "predicted_layer4_best_k_corrected"),
            "time_only_corrected": metric(selected, "predicted_time_only_corrected"),
            "training_mean_corrected": metric(selected, "predicted_training_mean_corrected"),
        }
        with_last_seen = [
            row for row in selected if row["predicted_last_seen_corrected"] is not None
        ]
        result["last_seen_corrected"] = (
            metric(with_last_seen, "predicted_last_seen_corrected") if with_last_seen else None
        )
        result["full_minus_time_only_rmse"] = (
            result["neural_full_corrected"]["trajectory_aggregated_rmse"]
            - result["time_only_corrected"]["trajectory_aggregated_rmse"]
        )
        result["best_k_minus_time_only_rmse"] = (
            result["neural_best_k_corrected"]["trajectory_aggregated_rmse"]
            - result["time_only_corrected"]["trajectory_aggregated_rmse"]
        )
        result["full_minus_training_mean_rmse"] = (
            result["neural_full_corrected"]["trajectory_aggregated_rmse"]
            - result["training_mean_corrected"]["trajectory_aggregated_rmse"]
        )
        result["best_k_minus_training_mean_rmse"] = (
            result["neural_best_k_corrected"]["trajectory_aggregated_rmse"]
            - result["training_mean_corrected"]["trajectory_aggregated_rmse"]
        )
        results[name] = result

    target_authoritative_sensitivity = {}
    for name in ("FULL_TAU1_15", "SHORT", "MATCHED_SPAN_TAU8_15"):
        select = domains[name]
        selected = [
            row
            for row in target_authoritative_rows
            if select(row) and row["predicted_last_seen_fir_corrected"] is not None
        ]
        target_authoritative_sensitivity[name] = {
            "neural_best_k_historical": metric(selected, "predicted_layer4_best_k"),
            "last_seen_historical_logged": metric(
                selected, "last_rendered_evidence_position"
            ),
            "last_seen_fir_corrected_depicted": metric(
                selected, "predicted_last_seen_fir_corrected"
            ),
            "time_only_historical": metric(selected, "predicted_time_only_linear"),
            "training_mean_historical": metric(selected, "predicted_training_mean"),
        }

    full = results["FULL_TAU1_15"]
    primary_gate_still_fails = full["neural_full_corrected"]["macro_r2"] <= 0
    trivial_baselines_defeat_full = (
        full["full_minus_time_only_rmse"] > 0 and full["full_minus_training_mean_rmse"] > 0
    )
    output = {
        "artifact_id": "regime-a-direct-temporal-reanalysis-v0.2",
        "label": "EXPLORATORY_FORENSIC_DIAGNOSTIC_ONLY",
        "existing_data_only": True,
        "historical_results_modified": False,
        "alignment_model": "causal_fir_kernel_convolved_target_and_last_seen",
        "kernel": kernel.tolist(),
        "group_delay_ticks": kernel_document["group_delay_mean"],
        "activation_source": "receipt-hashed persisted Regime A layer-4 arrays",
        "path_source": "receipt-hashed persisted Regime A server_state.jsonl",
        "frozen_refit_procedure": "run_regime_a_first25_science.Analysis nested FULL and BEST-K",
        "max_historical_target_vs_server_state_error": max_historical_target_error,
        "domains": results,
        "historical_target_last_seen_sensitivity": target_authoritative_sensitivity,
        "corrected_primary_macro_r2_gt_zero": not primary_gate_still_fails,
        "corrected_primary_gate_still_fails": primary_gate_still_fails,
        "lag_immune_trivial_baselines_defeat_primary_full": trivial_baselines_defeat_full,
        "regime_a_conclusion_stable": bool(primary_gate_still_fails and trivial_baselines_defeat_full),
        "selection": {
            "full": full_selection,
            "best_k": best_selection,
        },
    }
    output_path.write_text(json.dumps(output, indent=2, sort_keys=True, allow_nan=False) + "\n")
    print(
        json.dumps(
            {
                "output": str(output_path),
                "FULL_TAU1_15": results["FULL_TAU1_15"],
                "SHORT": results["SHORT"],
                "regime_a_conclusion_stable": output["regime_a_conclusion_stable"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: b08_regime_a_blast_radius.py IMPULSE_JSON OUTPUT_JSON")
    main(Path(sys.argv[1]), Path(sys.argv[2]))
