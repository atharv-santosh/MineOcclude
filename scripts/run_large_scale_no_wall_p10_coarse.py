#!/usr/bin/env python3
"""Run the frozen resumable P10 COARSE_2x6 learning-curve comparison."""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
import os
import resource
import subprocess
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import numpy as np

from mineocclude.probes.p7_ridge import (
    ridge_predictions_all_alphas_from_kernel,
    ridge_predictions_from_kernel,
    standardized_kernel_cuda,
)
from mineocclude.probes.p8_core import (
    canonical_sha256,
    metric_document,
    numeric_summary,
    paired_summary,
    select_alpha,
    selection_score,
)
from scripts import run_large_scale_no_wall_p8_core as p8

STUDY_ROOT = p8.STUDY_ROOT
QUALIFIED_PYTHON = p8.QUALIFIED_PYTHON
P7_CACHE_MANIFEST = STUDY_ROOT / "cache_manifest.json"
P7_RECEIPT = STUDY_ROOT / "p7_receipt.json"
P9_RECEIPT = STUDY_ROOT / "p9_receipt.json"
MANIFEST = STUDY_ROOT / "p10_run_manifest.json"
MANIFEST_LOCK = STUDY_ROOT / "p10_run_manifest.sha256"
LEDGER = STUDY_ROOT / "p10_execution_ledger.jsonl"
PROGRESS = STUDY_ROOT / "p10_progress.json"
RESULT = STUDY_ROOT / "coarse_learning_curve_results.json"
VALIDATION_RECEIPT = STUDY_ROOT / "p10_validation_receipt.json"
RECEIPT = STUDY_ROOT / "p10_receipt.json"

CACHE_ROOT = Path(
    "/mnt/sagemaker-nvme/mineocclude_large_scale_no_wall_scaling_best_k_v0_1_v2/"
    "p7_representation_solver_v0_1"
)
COARSE_CACHE = CACHE_ROOT / "coarse_2x6.f32.npy"
COARSE_METADATA = CACHE_ROOT / "coarse_2x6.metadata.json"
RESULT_ROOT = Path(
    "/mnt/sagemaker-nvme/mineocclude_large_scale_no_wall_scaling_best_k_v0_1_v2/"
    "p10_coarse_learning_curves_v0_1"
)
JOB_ROOT = RESULT_ROOT / "jobs"
S3_PREFIX = (
    "mineocclude/exploratory_large_scale_no_wall_scaling_best_k_v0_1/"
    "p10_coarse_learning_curves_v0_1"
)
S3_URI = f"s3://{p8.S3_BUCKET}/{S3_PREFIX}/"

REPRESENTATION = "COARSE_2x6"
EXPECTED_JOBS = 62
EXPECTED_BY_N = {5: 20, 15: 16, 40: 12, 70: 8, 100: 6}
COARSE_DIM = 24_576
ROW_COUNT = 7_200
HOST_CEILING = p8.HOST_CEILING
GPU_CEILING = p8.GPU_CEILING
MAX_JOB_ATTEMPTS = 2
P7_CACHE_MANIFEST_SHA256 = "0aff9b16a9e37cb004ea9bdde8725e05f59205050545176cdf5463a437aad89d"
EXPECTED_COARSE_SHA256 = "4a1c9562a26416eb6b069baeeb9f1c73513f7306f30a7cfe54dd30efe7094bdf"


class P10Error(RuntimeError):
    """Raised when P10 cannot continue under frozen authority."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise P10Error(message)


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    os.replace(temporary, path)


def append_ledger(value: dict[str, Any]) -> None:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n"
    with LEDGER.open("a", encoding="utf-8") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_authority(*, require_p9: bool = True) -> None:
    p8_manifest = p8.validate_manifest()
    p8_receipt = read_json(p8.P8_RECEIPT)
    require(p8_receipt["safe_for_p9"] is True, "P8 receipt gate")
    require(
        p8_manifest["runner_sha256"]
        == sha256_file(ROOT / "scripts/run_large_scale_no_wall_p8_core.py"),
        "frozen P8 runner changed",
    )
    require(
        p8_manifest["support_module_sha256"]
        == sha256_file(ROOT / "src/mineocclude/probes/p8_core.py"),
        "frozen P8 support changed",
    )
    require(sha256_file(P7_CACHE_MANIFEST) == P7_CACHE_MANIFEST_SHA256, "P7 cache authority")
    p7_receipt = read_json(P7_RECEIPT)
    require(
        p7_receipt["artifacts"][str(P7_CACHE_MANIFEST.relative_to(ROOT))]
        == P7_CACHE_MANIFEST_SHA256,
        "P7 cache receipt",
    )
    cache_entry = read_json(P7_CACHE_MANIFEST)["entries"][REPRESENTATION]
    require(cache_entry["checksum"] == EXPECTED_COARSE_SHA256, "coarse checksum authority")
    require(cache_entry["shape"] == [ROW_COUNT, COARSE_DIM], "coarse shape authority")
    if require_p9:
        require(P9_RECEIPT.is_file(), "P9 receipt absent")
        require(
            read_json(P9_RECEIPT)["status"] == "PASS_P9_COMPLETE_VALIDATED",
            "P9 validation gate",
        )


def _cache_metadata_valid(*, full_hash: bool) -> bool:
    if not COARSE_CACHE.is_file() or not COARSE_METADATA.is_file():
        return False
    metadata = read_json(COARSE_METADATA)
    if (
        metadata.get("sha256") != EXPECTED_COARSE_SHA256
        or metadata.get("shape") != [ROW_COUNT, COARSE_DIM]
        or metadata.get("dtype") != "float32"
        or COARSE_CACHE.stat().st_size != 707_788_928
    ):
        return False
    cache = np.load(COARSE_CACHE, mmap_mode="r", allow_pickle=False)
    if cache.shape != (ROW_COUNT, COARSE_DIM) or cache.dtype != np.float32:
        return False
    return not full_hash or sha256_file(COARSE_CACHE) == EXPECTED_COARSE_SHA256


def ensure_coarse_cache(*, full_hash: bool = True) -> dict[str, Any]:
    """Reuse or exactly reconstruct only the named P7 COARSE cache."""

    verify_authority()
    if _cache_metadata_valid(full_hash=full_hash):
        return {**read_json(COARSE_METADATA), "cache_reused": True}
    require(full_hash, "coarse cache failed lightweight validation inside worker")
    CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    temporary = COARSE_CACHE.with_name(f".{COARSE_CACHE.name}.tmp-{os.getpid()}")
    cache = np.lib.format.open_memmap(
        temporary, mode="w+", dtype=np.float32, shape=(ROW_COUNT, COARSE_DIM)
    )
    manifest = read_json(p8.P6_MANIFEST)
    require(len(manifest["chunks"]) == 120, "P6 chunk count")
    maximum_global_difference = 0.0
    started = time.perf_counter()
    for chunk_ordinal, chunk in enumerate(manifest["chunks"]):
        tokens = np.load(
            p8.ACTIVATION_ROOT / chunk["unpooled"]["path"],
            mmap_mode="r",
            allow_pickle=False,
        )
        pooled = np.load(
            p8.ACTIVATION_ROOT / chunk["pooled"]["path"],
            mmap_mode="r",
            allow_pickle=False,
        )
        start = chunk_ordinal * p8.FRAMES_PER_TRAJECTORY
        for local_start in range(0, p8.FRAMES_PER_TRAJECTORY, 4):
            local_stop = min(local_start + 4, p8.FRAMES_PER_TRAJECTORY)
            block = np.asarray(tokens[local_start:local_stop], dtype=np.float32)
            maximum_global_difference = max(
                maximum_global_difference,
                float(
                    np.max(
                        np.abs(
                            block.mean(axis=1)
                            - np.asarray(pooled[local_start:local_stop], dtype=np.float32)
                        )
                    )
                ),
            )
            coarse = (
                block.reshape(-1, 2, 7, 6, 4, p8.HIDDEN_WIDTH)
                .mean(axis=(2, 4))
                .reshape(-1, COARSE_DIM)
            )
            cache[start + local_start : start + local_stop] = coarse
    cache.flush()
    del cache
    require(maximum_global_difference == 0.0, "P6 GLOBAL equivalence")
    rebuilt_sha = sha256_file(temporary)
    require(rebuilt_sha == EXPECTED_COARSE_SHA256, "reconstructed coarse cache hash")
    os.replace(temporary, COARSE_CACHE)
    metadata = {
        "build_seconds": time.perf_counter() - started,
        "byte_size": COARSE_CACHE.stat().st_size,
        "cache_reused": False,
        "dtype": "float32",
        "global_equivalence_max_abs_difference": maximum_global_difference,
        "path": str(COARSE_CACHE),
        "recipe": "reshape [rows,2,7,6,4,2048], mean axes (2,4), flatten C",
        "row_order": "canonical_row_authority.jsonl row_ordinal",
        "sha256": rebuilt_sha,
        "shape": [ROW_COUNT, COARSE_DIM],
        "source": "exact reconstruction from protected P6 activation manifest",
    }
    write_json(COARSE_METADATA, metadata)
    return metadata


def freeze_manifest() -> dict[str, Any]:
    verify_authority()
    if MANIFEST.exists() or MANIFEST_LOCK.exists() or LEDGER.exists():
        return validate_manifest()
    schedule = read_json(p8.SUBSET_SCHEDULE)
    guard = read_json(p8.TEST_GUARD)
    jobs = []
    for subset in schedule["subsets"]:
        payload = {
            "alpha_grid": list(p8.ALPHAS),
            "coarse_cache_sha256": EXPECTED_COARSE_SHA256,
            "fixed_test_hash": guard["test_authority_hash"],
            "fixed_test_trajectory_ids": guard["test_trajectory_ids"],
            "job_id": f"coarse_2x6__{subset['subset_id']}",
            "master_id": subset["master_id"],
            "p8_manifest_sha256": sha256_file(p8.RUN_MANIFEST),
            "representation": REPRESENTATION,
            "subset_id": subset["subset_id"],
            "training_size": int(subset["training_size"]),
            "training_trajectory_hash": subset["subset_hash"],
            "training_trajectory_ids": subset["trajectory_spec_ids"],
        }
        payload["identity_sha256"] = canonical_sha256(payload)
        jobs.append(payload)
    require(len(jobs) == EXPECTED_JOBS, "P10 job count")
    document = {
        "alpha_selection": "same grouped training-only equal-layout macro R2 as P8; exact ties use smaller alpha",
        "artifact_id": "large-scale-no-wall-p10-run-manifest-v0.1",
        "coarse_geometry": "14x24 -> contiguous [2x7] by [6x4] bins; row-major flatten",
        "expected_jobs": EXPECTED_JOBS,
        "fixed_before_p10_outcomes": True,
        "jobs": jobs,
        "p7_cache_manifest_sha256": P7_CACHE_MANIFEST_SHA256,
        "p8_manifest_sha256": sha256_file(p8.RUN_MANIFEST),
        "p9_receipt_sha256": sha256_file(P9_RECEIPT),
        "representation": REPRESENTATION,
        "runner": str(Path(__file__).relative_to(ROOT)),
        "runner_sha256": sha256_file(Path(__file__).resolve()),
        "status": "FROZEN_BEFORE_P10_OUTCOMES",
        "test_used_for_selection": False,
    }
    write_json(MANIFEST, document)
    MANIFEST_LOCK.write_text(sha256_file(MANIFEST) + "\n", encoding="utf-8")
    for job in jobs:
        append_ledger(
            {
                "attempt": 0,
                "event_at": now_utc(),
                "identity_sha256": job["identity_sha256"],
                "job_id": job["job_id"],
                "state": "PENDING",
            }
        )
    write_progress(document, current_job=None)
    sync_control()
    return document


def validate_manifest() -> dict[str, Any]:
    verify_authority()
    require(MANIFEST.is_file() and MANIFEST_LOCK.is_file(), "P10 manifest absent")
    require(sha256_file(MANIFEST) == MANIFEST_LOCK.read_text().strip(), "P10 manifest lock")
    document = read_json(MANIFEST)
    require(document["status"] == "FROZEN_BEFORE_P10_OUTCOMES", "P10 manifest status")
    require(len(document["jobs"]) == EXPECTED_JOBS, "P10 manifest jobs")
    require(
        document["runner_sha256"] == sha256_file(Path(__file__).resolve()),
        "P10 runner changed after freeze",
    )
    for job in document["jobs"]:
        identity = job["identity_sha256"]
        payload = {key: value for key, value in job.items() if key != "identity_sha256"}
        require(canonical_sha256(payload) == identity, f"P10 job identity {job['job_id']}")
    return document


def latest_ledger() -> tuple[dict[str, dict[str, Any]], Counter[str], dict[str, int]]:
    latest: dict[str, dict[str, Any]] = {}
    attempts: dict[str, int] = defaultdict(int)
    for event in read_jsonl(LEDGER):
        latest[event["job_id"]] = event
        attempts[event["job_id"]] = max(attempts[event["job_id"]], int(event["attempt"]))
    return latest, Counter(event["state"] for event in latest.values()), attempts


def write_progress(manifest: dict[str, Any], *, current_job: str | None) -> None:
    _latest, counts, attempts = latest_ledger()
    write_json(
        PROGRESS,
        {
            "blocked_jobs": counts["BLOCKED"],
            "current_job_id": current_job,
            "expected_jobs": len(manifest["jobs"]),
            "failed_retryable_current_jobs": counts["FAILED_RETRYABLE"],
            "maximum_attempt": max(attempts.values(), default=0),
            "phase": "P10",
            "running_jobs": counts["RUNNING"],
            "updated_at": now_utc(),
            "validated_jobs": counts["VALIDATED"],
        },
    )


def sync_control() -> None:
    for path in (MANIFEST, MANIFEST_LOCK, LEDGER, PROGRESS):
        subprocess.run(
            ["aws", "s3", "cp", str(path), f"{S3_URI}{path.name}", "--only-show-errors"],
            check=True,
        )


def sync_job(job_id: str) -> None:
    subprocess.run(
        [
            "aws",
            "s3",
            "sync",
            str(JOB_ROOT / job_id),
            f"{S3_URI}jobs/{job_id}/",
            "--only-show-errors",
        ],
        check=True,
    )
    sync_control()


def restore_job(job_id: str) -> None:
    (JOB_ROOT / job_id).mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "aws",
            "s3",
            "sync",
            f"{S3_URI}jobs/{job_id}/",
            str(JOB_ROOT / job_id),
            "--only-show-errors",
        ],
        check=True,
    )


def coarse_features(context: p8.JobContext, identities: list[str]) -> np.ndarray:
    require(_cache_metadata_valid(full_hash=False), "coarse cache unavailable")
    cache = np.load(COARSE_CACHE, mmap_mode="r", allow_pickle=False)
    ordinals = context.access.row_ordinals(identities)
    return np.asarray(cache[ordinals], dtype=np.float32)


def run_coarse(
    context: p8.JobContext, job: dict[str, Any]
) -> tuple[np.ndarray, dict[str, Any], dict[str, Any]]:
    subset_ids = list(job["training_trajectory_ids"])
    oof: dict[float, dict[str, np.ndarray]] = {alpha: {} for alpha in p8.ALPHAS}
    fold_records = []
    gpu_seconds = 0.0
    cpu_seconds = 0.0
    peak_gpu = 0
    for fold in p8.selection_folds(context, job["subset_id"]):
        train_ids = list(fold["training_ids"])
        validation_ids = list(fold["validation_ids"])
        scope_ids = train_ids + validation_ids
        features = coarse_features(context, scope_ids)
        targets = context.targets(train_ids)
        kernel = standardized_kernel_cuda(features[: len(targets)], features)
        solve_started = time.perf_counter()
        predictions = ridge_predictions_all_alphas_from_kernel(
            kernel.kernel,
            targets,
            alphas=p8.ALPHAS,
            prediction_scope_positions=p8.prediction_positions(len(targets), len(features)),
        )
        cpu_seconds += time.perf_counter() - solve_started
        for alpha in p8.ALPHAS:
            for ordinal, identity in enumerate(validation_ids):
                start = ordinal * p8.FRAMES_PER_TRAJECTORY
                oof[alpha][identity] = predictions[alpha][start : start + p8.FRAMES_PER_TRAJECTORY]
        gpu_seconds += sum(kernel.timings.values())
        peak_gpu = max(peak_gpu, kernel.peak_device_memory_bytes)
        fold_records.append(
            {
                "fold_id": fold["fold_id"],
                "training_ids_hash": canonical_sha256(train_ids),
                "validation_ids_hash": canonical_sha256(validation_ids),
            }
        )
        del features, kernel, predictions
        gc.collect()
    actual = context.targets(subset_ids)
    scores = {}
    for alpha in p8.ALPHAS:
        predictions = np.concatenate([oof[alpha][identity] for identity in subset_ids])
        scores[alpha] = selection_score(
            actual, predictions, subset_ids, context.layouts(subset_ids)
        )
    selected_alpha = select_alpha(scores, tie_tolerance=0.0, prefer="smaller")
    final_scope = subset_ids + list(context.test_ids)
    features = coarse_features(context, final_scope)
    train_targets = context.targets(subset_ids)
    kernel = standardized_kernel_cuda(features[: len(train_targets)], features)
    solve_started = time.perf_counter()
    predictions = ridge_predictions_from_kernel(
        kernel.kernel,
        train_targets,
        alpha=selected_alpha,
        prediction_scope_positions=p8.prediction_positions(len(train_targets), len(features)),
    )
    cpu_seconds += time.perf_counter() - solve_started
    gpu_seconds += sum(kernel.timings.values())
    peak_gpu = max(peak_gpu, kernel.peak_device_memory_bytes)
    return (
        predictions,
        {
            "alpha_scores": {str(alpha): scores[alpha] for alpha in p8.ALPHAS},
            "coarse_cache_sha256": EXPECTED_COARSE_SHA256,
            "folds": fold_records,
            "selected_alpha": selected_alpha,
            "test_used_for_selection": False,
        },
        {
            "cpu_dominant_seconds": cpu_seconds,
            "gpu_active_seconds": gpu_seconds,
            "peak_gpu_bytes": peak_gpu,
        },
    )


def save_npz_atomic(path: Path, **arrays: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    with temporary.open("wb") as stream:
        np.savez_compressed(stream, **arrays)
    os.replace(temporary, path)


def run_worker(job_id: str) -> None:
    manifest = validate_manifest()
    job = next((record for record in manifest["jobs"] if record["job_id"] == job_id), None)
    require(job is not None, f"unknown P10 job {job_id}")
    ensure_coarse_cache(full_hash=False)
    started = time.perf_counter()
    context = p8.JobContext()
    require(not set(job["training_trajectory_ids"]) & set(context.test_ids), "train/test overlap")
    predictions, evidence, timing = run_coarse(context, job)
    require(predictions.shape == (1080,), "P10 prediction rows")
    test_ids = list(context.test_ids)
    metrics = metric_document(
        context.targets(test_ids), predictions, test_ids, context.layouts(test_ids)
    )
    directory = JOB_ROOT / job_id
    directory.mkdir(parents=True, exist_ok=True)
    prediction_path = directory / "predictions.npz"
    evidence_path = directory / "selection_evidence.json"
    save_npz_atomic(
        prediction_path,
        predictions=np.asarray(predictions, dtype=np.float64),
        row_ordinals=np.asarray(context.access.row_ordinals(test_ids), dtype=np.int64),
    )
    write_json(evidence_path, evidence)
    result = {
        "artifact_id": "large-scale-no-wall-p10-coarse-job-v0.1",
        "fixed_test_hash": job["fixed_test_hash"],
        "fixed_test_prediction_rows": 1080,
        "identity_sha256": job["identity_sha256"],
        "job_id": job_id,
        "master_id": job["master_id"],
        "metrics": metrics,
        "prediction_artifact": {
            "byte_count": prediction_path.stat().st_size,
            "path": str(prediction_path),
            "sha256": sha256_file(prediction_path),
        },
        "representation": REPRESENTATION,
        "runtime": {
            **timing,
            "peak_host_bytes": int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024),
            "total_seconds": time.perf_counter() - started,
        },
        "selected_alpha": float(evidence["selected_alpha"]),
        "selection_artifact": {
            "byte_count": evidence_path.stat().st_size,
            "path": str(evidence_path),
            "sha256": sha256_file(evidence_path),
        },
        "selection_provenance": {
            "alpha_selection_training_only": True,
            "test_used_for_selection": False,
        },
        "status": "VALIDATED",
        "subset_id": job["subset_id"],
        "training_size": job["training_size"],
        "training_trajectory_hash": job["training_trajectory_hash"],
        "training_trajectory_ids": job["training_trajectory_ids"],
    }
    write_json(directory / "job_result.json", result)
    print(json.dumps({"job_id": job_id, "status": "VALIDATED"}, sort_keys=True))


def validate_job_result(job: dict[str, Any]) -> dict[str, Any]:
    path = JOB_ROOT / job["job_id"] / "job_result.json"
    require(path.is_file(), f"missing P10 job {job['job_id']}")
    result = read_json(path)
    require(result["status"] == "VALIDATED", "P10 job status")
    require(result["identity_sha256"] == job["identity_sha256"], "P10 identity")
    require(result["fixed_test_hash"] == job["fixed_test_hash"], "P10 test hash")
    require(result["selected_alpha"] in p8.ALPHAS, "P10 alpha")
    require(result["selection_provenance"]["test_used_for_selection"] is False, "P10 leakage")
    for key in ("prediction_artifact", "selection_artifact"):
        artifact = result[key]
        artifact_path = Path(artifact["path"])
        require(artifact_path.is_file(), f"missing {key}")
        require(artifact_path.stat().st_size == artifact["byte_count"], f"{key} size")
        require(sha256_file(artifact_path) == artifact["sha256"], f"{key} hash")
    prediction = np.load(result["prediction_artifact"]["path"], allow_pickle=False)
    require(prediction["predictions"].shape == (1080,), "P10 prediction shape")
    require(np.isfinite(prediction["predictions"]).all(), "P10 finite prediction")
    require(result["runtime"]["peak_host_bytes"] <= HOST_CEILING, "P10 host ceiling")
    require(result["runtime"]["peak_gpu_bytes"] <= GPU_CEILING, "P10 GPU ceiling")
    return result


def run_all() -> None:
    manifest = validate_manifest()
    ensure_coarse_cache(full_hash=True)
    RESULT_ROOT.mkdir(parents=True, exist_ok=True)
    JOB_ROOT.mkdir(parents=True, exist_ok=True)
    latest, _, attempts = latest_ledger()
    for job in manifest["jobs"]:
        event = latest[job["job_id"]]
        if event["state"] == "VALIDATED":
            try:
                validate_job_result(job)
            except Exception:
                restore_job(job["job_id"])
                validate_job_result(job)
            sync_job(job["job_id"])
            continue
        if event["state"] == "RUNNING":
            append_ledger(
                {
                    "attempt": attempts[job["job_id"]],
                    "event_at": now_utc(),
                    "identity_sha256": job["identity_sha256"],
                    "job_id": job["job_id"],
                    "reason": "interrupted exact worker",
                    "state": "FAILED_RETRYABLE",
                }
            )
        succeeded = False
        while attempts[job["job_id"]] < MAX_JOB_ATTEMPTS and not succeeded:
            attempts[job["job_id"]] += 1
            attempt = attempts[job["job_id"]]
            append_ledger(
                {
                    "attempt": attempt,
                    "event_at": now_utc(),
                    "identity_sha256": job["identity_sha256"],
                    "job_id": job["job_id"],
                    "state": "RUNNING",
                }
            )
            write_progress(manifest, current_job=job["job_id"])
            log_path = RESULT_ROOT / "attempt_logs" / f"{job['job_id']}__attempt_{attempt}.log"
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with log_path.open("w", encoding="utf-8") as log:
                completed = subprocess.run(
                    [str(QUALIFIED_PYTHON), str(Path(__file__).resolve()), "--worker", job["job_id"]],
                    cwd=ROOT,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    text=True,
                    check=False,
                )
            if completed.returncode == 0:
                try:
                    result = validate_job_result(job)
                except Exception as error:
                    failure = f"post-worker validation: {type(error).__name__}: {error}"
                else:
                    append_ledger(
                        {
                            "attempt": attempt,
                            "event_at": now_utc(),
                            "identity_sha256": job["identity_sha256"],
                            "job_id": job["job_id"],
                            "result_sha256": sha256_file(JOB_ROOT / job["job_id"] / "job_result.json"),
                            "runtime_seconds": result["runtime"]["total_seconds"],
                            "state": "VALIDATED",
                        }
                    )
                    write_progress(manifest, current_job=None)
                    sync_job(job["job_id"])
                    succeeded = True
            else:
                failure = f"worker exit {completed.returncode}; log={log_path}"
            if not succeeded:
                state = "FAILED_RETRYABLE" if attempt < MAX_JOB_ATTEMPTS else "BLOCKED"
                append_ledger(
                    {
                        "attempt": attempt,
                        "event_at": now_utc(),
                        "identity_sha256": job["identity_sha256"],
                        "job_id": job["job_id"],
                        "reason": failure,
                        "state": state,
                    }
                )
                write_progress(manifest, current_job=None)
                sync_control()
                if state == "BLOCKED":
                    raise P10Error(f"P10 job blocked: {job['job_id']}")
        latest, _, _ = latest_ledger()
    _latest, counts, _attempts = latest_ledger()
    require(counts["VALIDATED"] == EXPECTED_JOBS, "P10 incomplete")
    require(not counts["BLOCKED"] and not counts["RUNNING"], "P10 terminal ledger")


def completed_results(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    latest, counts, _ = latest_ledger()
    require(counts["VALIDATED"] == EXPECTED_JOBS, "P10 completeness")
    require(not counts["BLOCKED"] and not counts["RUNNING"], "P10 ledger state")
    return [validate_job_result(job) for job in manifest["jobs"]]


def recompute_metrics(results: list[dict[str, Any]]) -> None:
    context = p8.JobContext()
    test_ids = list(context.test_ids)
    actual = context.targets(test_ids)
    rows = np.asarray(context.access.row_ordinals(test_ids), dtype=np.int64)
    for result in results:
        prediction = np.load(result["prediction_artifact"]["path"], allow_pickle=False)
        require(np.array_equal(prediction["row_ordinals"], rows), "P10 row authority")
        metrics = metric_document(
            actual, prediction["predictions"], test_ids, context.layouts(test_ids)
        )
        require(canonical_sha256(metrics) == canonical_sha256(result["metrics"]), "P10 metric recomputation")


def build_result(results: list[dict[str, Any]]) -> dict[str, Any]:
    p8_learning = read_json(p8.LEARNING_RESULTS)
    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for result in results:
        grouped[int(result["training_size"])].append(result)
    summaries = {}
    matched = {f"COARSE_MINUS_{rep}": {} for rep in p8.REPRESENTATIONS}
    p8_index = {
        (record["representation"], record["subset_id"]): record
        for record in p8_learning["job_records"]
    }
    for n, expected in EXPECTED_BY_N.items():
        records = sorted(grouped[n], key=lambda record: record["subset_id"])
        require(len(records) == expected, f"P10 N={n} count")
        r2 = [float(record["metrics"]["equal_layout_macro"]["r2"]) for record in records]
        summaries[str(n)] = {
            "macro_r2": numeric_summary(r2),
            "selected_alpha_distribution": {
                str(key): int(value)
                for key, value in sorted(Counter(r["selected_alpha"] for r in records).items())
            },
            "subset_count": len(records),
            "subset_ids": [record["subset_id"] for record in records],
            "subset_points_r2": r2,
            "training_frame_count": n * p8.FRAMES_PER_TRAJECTORY,
            "training_trajectory_count": n,
        }
        for offset, representation in enumerate(p8.REPRESENTATIONS):
            deltas = [
                float(record["metrics"]["equal_layout_macro"]["r2"])
                - float(p8_index[(representation, record["subset_id"])]["metrics"]["equal_layout_macro"]["r2"])
                for record in records
            ]
            matched[f"COARSE_MINUS_{representation}"][str(n)] = {
                **paired_summary(deltas, seed=p8.BOOTSTRAP_SEED + 5000 + offset * 100 + n),
                "paired_deltas": deltas,
                "subset_ids": [record["subset_id"] for record in records],
            }
    return {
        "artifact_id": "large-scale-no-wall-p10-coarse-learning-curves-v0.1",
        "coarse_cache_sha256": EXPECTED_COARSE_SHA256,
        "fixed_test_hash": read_json(p8.TEST_GUARD)["test_authority_hash"],
        "job_count": len(results),
        "job_records": [
            {
                "job_id": result["job_id"],
                "metrics": result["metrics"],
                "prediction_sha256": result["prediction_artifact"]["sha256"],
                "runtime_seconds": result["runtime"]["total_seconds"],
                "selected_alpha": result["selected_alpha"],
                "subset_id": result["subset_id"],
                "training_size": result["training_size"],
            }
            for result in results
        ],
        "matched_p8_deltas": matched,
        "primary_metric": "fixed-test equal-layout macro per-trajectory R2",
        "representation": REPRESENTATION,
        "status": "PASS_P10_COMPLETE_62_OF_62",
        "summaries": summaries,
    }


def aggregate() -> None:
    manifest = validate_manifest()
    results = completed_results(manifest)
    recompute_metrics(results)
    document = build_result(results)
    write_json(RESULT, document)
    validation = {
        "artifact_id": "large-scale-no-wall-p10-validation-receipt-v0.1",
        "coarse_cache_sha256": EXPECTED_COARSE_SHA256,
        "coarse_learning_curve_results_sha256": sha256_file(RESULT),
        "expected_jobs": EXPECTED_JOBS,
        "fixed_test_hash": read_json(p8.TEST_GUARD)["test_authority_hash"],
        "metrics_recomputed_from_predictions": True,
        "p8_results_unchanged": True,
        "same_62_subset_authorities": True,
        "status": "PASS_P10_COMPLETE_VALIDATED",
        "test_used_for_selection": False,
        "validated_jobs": len(results),
    }
    write_json(VALIDATION_RECEIPT, validation)
    receipt = {
        "artifact_id": "large-scale-no-wall-p10-receipt-v0.1",
        "blocker": None,
        "result_sha256": sha256_file(RESULT),
        "safe_for_p11": True,
        "status": "PASS_P10_COARSE_COMPLETE",
        "total_completed": len(results),
    }
    write_json(RECEIPT, receipt)
    for path in (RESULT, VALIDATION_RECEIPT, RECEIPT):
        subprocess.run(
            [
                "aws",
                "s3",
                "cp",
                str(path),
                f"{S3_URI}repository_artifacts/{path.name}",
                "--checksum-algorithm",
                "SHA256",
                "--only-show-errors",
            ],
            check=True,
        )
    sync_control()


def validate_complete() -> None:
    manifest = validate_manifest()
    results = completed_results(manifest)
    recompute_metrics(results)
    expected = build_result(results)
    require(RESULT.is_file(), "P10 result missing")
    require(canonical_sha256(read_json(RESULT)) == canonical_sha256(expected), "P10 deterministic aggregate")
    validation = read_json(VALIDATION_RECEIPT)
    receipt = read_json(RECEIPT)
    require(validation["status"] == "PASS_P10_COMPLETE_VALIDATED", "P10 validation receipt")
    require(validation["coarse_learning_curve_results_sha256"] == sha256_file(RESULT), "P10 result hash")
    require(receipt["safe_for_p11"] is True, "P10 SAFE_FOR_P11")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--validate-manifest", action="store_true")
    parser.add_argument("--worker")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--aggregate", action="store_true")
    parser.add_argument("--validate", action="store_true")
    args = parser.parse_args()
    actions = sum(bool(x) for x in (args.prepare, args.validate_manifest, args.worker, args.run, args.aggregate, args.validate))
    require(actions == 1, "choose exactly one P10 action")
    if args.prepare:
        ensure_coarse_cache(full_hash=True)
        freeze_manifest()
        print("PASS P10 prepared with exact COARSE cache and frozen 62-job manifest")
    elif args.validate_manifest:
        print(f"PASS P10 manifest {len(validate_manifest()['jobs'])}/62")
    elif args.worker:
        run_worker(args.worker)
    elif args.run:
        run_all()
        print("PASS P10 execution 62/62")
    elif args.aggregate:
        aggregate()
        print("PASS P10 aggregate and durability")
    else:
        validate_complete()
        print("PASS P10 validation gate SAFE_FOR_P11")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
