#!/usr/bin/env python3
"""Run the frozen prospective P11 within-layout trajectory derangement null."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
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

from mineocclude.probes.p8_core import canonical_sha256, metric_document, numeric_summary, rank_tokens
from scripts import run_large_scale_no_wall_p8_core as p8
from scripts import run_large_scale_no_wall_p10_coarse as p10

STUDY_ROOT = p8.STUDY_ROOT
PROSPECTIVE_AUTHORITY = STUDY_ROOT / "prospective_null_authority.json"
CANONICAL_AUTHORITY = STUDY_ROOT / "canonical_null_authority.json"
P10_RECEIPT = STUDY_ROOT / "p10_receipt.json"
P10_VALIDATION = STUDY_ROOT / "p10_validation_receipt.json"
MANIFEST = STUDY_ROOT / "p11_run_manifest.json"
MANIFEST_LOCK = STUDY_ROOT / "p11_run_manifest.sha256"
LEDGER = STUDY_ROOT / "p11_execution_ledger.jsonl"
PROGRESS = STUDY_ROOT / "p11_progress.json"
BENCHMARK_RECEIPT = STUDY_ROOT / "p11_benchmark_receipt.json"
RESULT = STUDY_ROOT / "prospective_target_null_results.json"
VALIDATION_RECEIPT = STUDY_ROOT / "p11_validation_receipt.json"
RECEIPT = STUDY_ROOT / "p11_receipt.json"

RESULT_ROOT = Path(
    "/mnt/sagemaker-nvme/mineocclude_large_scale_no_wall_scaling_best_k_v0_1_v2/"
    "p11_prospective_derangement_null_v0_1"
)
JOB_ROOT = RESULT_ROOT / "jobs"
S3_PREFIX = (
    "mineocclude/exploratory_large_scale_no_wall_scaling_best_k_v0_1/"
    "p11_prospective_derangement_null_v0_1"
)
S3_URI = f"s3://{p8.S3_BUCKET}/{S3_PREFIX}/"

REPRESENTATIONS = ("GLOBAL_MEAN", "FULL_TOKEN_GRID", "BEST_K_TOKENS", "COARSE_2x6")
EXPECTED_SEEDS = 49
EXPECTED_JOBS = EXPECTED_SEEDS * len(REPRESENTATIONS)
CANONICAL_SUBSET_ID = "n100_r00"
PROSPECTIVE_SHA256 = "56e3e6d67707cd90866d73743de96d6600d4c518031769e2518b515510c91dc9"
CANONICAL_SHA256 = "11e59a2b8df90fce407d72a9f7e25549e78f240c7c49f6dd6aa0995c242182ff"
MAX_JOB_ATTEMPTS = 2


class P11Error(RuntimeError):
    """Raised when P11 cannot continue under frozen prospective authority."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise P11Error(message)


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


def seed_from(namespace: str, identity: str) -> int:
    digest = hashlib.sha256(f"{namespace}|{identity}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") & ((1 << 63) - 1)


def within_layout_derangement(
    trajectory_ids: list[str], layout_by_id: dict[str, str], seed: int
) -> dict[str, str]:
    assignments: dict[str, str] = {}
    by_layout: dict[str, list[str]] = defaultdict(list)
    for identity in trajectory_ids:
        by_layout[layout_by_id[identity]].append(identity)
    for layout in sorted(by_layout):
        recipients = sorted(by_layout[layout])
        require(len(recipients) >= 2, f"cannot derange singleton {layout}")
        donors = list(recipients)
        generator = random.Random(seed_from(f"prospective-null-{seed}", layout))
        for index in range(len(donors) - 1, 0, -1):
            other = generator.randrange(index)
            donors[index], donors[other] = donors[other], donors[index]
        require(all(a != b for a, b in zip(recipients, donors)), f"fixed point {layout}")
        assignments.update(dict(zip(recipients, donors)))
    require(len(assignments) == len(trajectory_ids), "derangement assignment count")
    return assignments


def authority_context() -> tuple[dict[str, Any], dict[str, Any], dict[str, str]]:
    prospective = read_json(PROSPECTIVE_AUTHORITY)
    canonical = read_json(CANONICAL_AUTHORITY)
    cohort = read_json(p8.COHORT_LOCK)
    layout_by_id = {
        entry["trajectory_spec_id"]: entry["layout_id"] for entry in cohort["entries"]
    }
    return prospective, canonical, layout_by_id


def verify_authority(*, require_p10_complete: bool) -> None:
    p8.validate_manifest()
    require(sha256_file(PROSPECTIVE_AUTHORITY) == PROSPECTIVE_SHA256, "prospective authority hash")
    require(sha256_file(CANONICAL_AUTHORITY) == CANONICAL_SHA256, "canonical authority hash")
    prospective, canonical, layout_by_id = authority_context()
    require(prospective["artifact_id"] == "PROSPECTIVE_WITHIN_LAYOUT_TRAJECTORY_DERANGEMENT_NULL_V0_1", "null version")
    require(prospective["B"] == EXPECTED_SEEDS, "frozen B")
    require(prospective["seeds"] == canonical["prospective_null_seeds"], "seed authority")
    require(canonical["canonical_subset_id"] == CANONICAL_SUBSET_ID, "canonical subset")
    require(len(canonical["canonical_training_trajectory_ids"]) == 100, "canonical N")
    require(canonical["null_executed"] is False, "historical null substitution")
    for seed in prospective["seeds"]:
        assignment = within_layout_derangement(
            canonical["canonical_training_trajectory_ids"], layout_by_id, int(seed)
        )
        require(
            all(
                recipient != donor
                and layout_by_id[recipient] == layout_by_id[donor]
                for recipient, donor in assignment.items()
            ),
            "within-layout no-self derangement",
        )
    p10_manifest = p10.validate_manifest()
    require(
        p10_manifest["runner_sha256"] == sha256_file(ROOT / p10_manifest["runner"]),
        "P10 runner changed",
    )
    if require_p10_complete:
        require(P10_RECEIPT.is_file() and P10_VALIDATION.is_file(), "P10 receipts absent")
        require(read_json(P10_RECEIPT)["safe_for_p11"] is True, "P10 SAFE_FOR_P11")
        require(
            read_json(P10_VALIDATION)["status"] == "PASS_P10_COMPLETE_VALIDATED",
            "P10 validation gate",
        )


class NullJobContext(p8.JobContext):
    """P8 feature/fold authority with only training targets deranged."""

    def __init__(self, assignments: dict[str, str]) -> None:
        super().__init__()
        self.assignments = dict(assignments)
        require(not set(self.assignments) & set(self.test_ids), "null assignment touches test")

    def targets(self, identities: list[str] | tuple[str, ...]) -> np.ndarray:
        values = []
        for identity in identities:
            donor = self.assignments.get(identity, identity)
            values.extend(self.entry_by_id[donor]["target_authority"]["x_true_blocks"])
        return np.asarray(values, dtype=np.float64)

    def true_targets(self, identities: list[str] | tuple[str, ...]) -> np.ndarray:
        return p8.JobContext.targets(self, identities)


def freeze_manifest() -> dict[str, Any]:
    verify_authority(require_p10_complete=False)
    if MANIFEST.exists() or MANIFEST_LOCK.exists() or LEDGER.exists():
        return validate_manifest(require_p10_complete=False)
    prospective, canonical, layout_by_id = authority_context()
    jobs = []
    for seed_index, seed in enumerate(prospective["seeds"]):
        assignment = within_layout_derangement(
            canonical["canonical_training_trajectory_ids"], layout_by_id, int(seed)
        )
        assignment_sha = canonical_sha256(assignment)
        for representation in REPRESENTATIONS:
            payload = {
                "alpha_grid": list(p8.ALPHAS),
                "assignment_sha256": assignment_sha,
                "best_k_grid": list(p8.K_GRID) if representation == "BEST_K_TOKENS" else None,
                "canonical_subset_hash": canonical["canonical_subset_hash"],
                "canonical_subset_id": CANONICAL_SUBSET_ID,
                "fixed_test_hash": read_json(p8.TEST_GUARD)["test_authority_hash"],
                "job_id": f"seed_{seed_index:02d}__{representation.lower()}",
                "null_authority_sha256": PROSPECTIVE_SHA256,
                "representation": representation,
                "seed": int(seed),
                "seed_index": seed_index,
                "training_trajectory_ids": canonical["canonical_training_trajectory_ids"],
            }
            payload["identity_sha256"] = canonical_sha256(payload)
            jobs.append(payload)
    require(len(jobs) == EXPECTED_JOBS, "P11 job count")
    document = {
        "artifact_id": "large-scale-no-wall-p11-run-manifest-v0.1",
        "benchmark": {
            "benchmark_seed_index": 0,
            "result_inspection_before_mechanics_freeze": False,
            "reuse_as_scientific_job": True,
            "scope": "first frozen seed across all four representations",
        },
        "canonical_null_authority_sha256": CANONICAL_SHA256,
        "canonical_subset_id": CANONICAL_SUBSET_ID,
        "execution_mechanics": {
            "bounded_parallelism": 1,
            "coarse_device": "cuda:0",
            "computation_dtype": "float64",
            "full_device": "cuda:0",
            "global_device": "cuda:0",
            "job_granularity": "null_seed_x_representation",
            "maximum_job_attempts": MAX_JOB_ATTEMPTS,
            "token_batch_size": p8.TOKEN_BATCH_SIZE,
            "wide_token_batch_size": p8.WIDE_TOKEN_BATCH_SIZE,
        },
        "expected_jobs": EXPECTED_JOBS,
        "expected_seeds": EXPECTED_SEEDS,
        "fixed_before_first_null_benchmark": True,
        "jobs": jobs,
        "p10_manifest_sha256": sha256_file(p10.MANIFEST),
        "prospective_null_authority_sha256": PROSPECTIVE_SHA256,
        "representations": list(REPRESENTATIONS),
        "runner": str(Path(__file__).relative_to(ROOT)),
        "runner_sha256": sha256_file(Path(__file__).resolve()),
        "status": "FROZEN_BEFORE_P11_NULL_OUTCOMES",
        "test_targets": "true and untouched",
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
                "seed": job["seed"],
                "seed_index": job["seed_index"],
                "state": "PENDING",
            }
        )
    write_progress(document, current_job=None)
    sync_control()
    return document


def validate_manifest(*, require_p10_complete: bool) -> dict[str, Any]:
    verify_authority(require_p10_complete=require_p10_complete)
    require(MANIFEST.is_file() and MANIFEST_LOCK.is_file(), "P11 manifest absent")
    require(sha256_file(MANIFEST) == MANIFEST_LOCK.read_text().strip(), "P11 manifest lock")
    document = read_json(MANIFEST)
    require(document["status"] == "FROZEN_BEFORE_P11_NULL_OUTCOMES", "P11 manifest status")
    require(len(document["jobs"]) == EXPECTED_JOBS, "P11 manifest jobs")
    require(document["expected_seeds"] == EXPECTED_SEEDS, "P11 manifest B")
    require(document["runner_sha256"] == sha256_file(Path(__file__).resolve()), "P11 runner changed")
    for job in document["jobs"]:
        identity = job["identity_sha256"]
        payload = {key: value for key, value in job.items() if key != "identity_sha256"}
        require(canonical_sha256(payload) == identity, f"P11 job identity {job['job_id']}")
    return document


def latest_ledger() -> tuple[dict[str, dict[str, Any]], Counter[str], dict[str, int]]:
    latest: dict[str, dict[str, Any]] = {}
    attempts: dict[str, int] = defaultdict(int)
    for event in read_jsonl(LEDGER):
        latest[event["job_id"]] = event
        attempts[event["job_id"]] = max(attempts[event["job_id"]], int(event["attempt"]))
    return latest, Counter(event["state"] for event in latest.values()), attempts


def write_progress(manifest: dict[str, Any], *, current_job: str | None) -> None:
    latest, counts, attempts = latest_ledger()
    complete_seeds = sum(
        all(latest.get(f"seed_{index:02d}__{rep.lower()}", {}).get("state") == "VALIDATED" for rep in REPRESENTATIONS)
        for index in range(EXPECTED_SEEDS)
    )
    current = next((job for job in manifest["jobs"] if job["job_id"] == current_job), None)
    write_json(
        PROGRESS,
        {
            "blocked_jobs": counts["BLOCKED"],
            "current_job_id": current_job,
            "current_representation": None if current is None else current["representation"],
            "current_seed": None if current is None else current["seed"],
            "current_seed_index": None if current is None else current["seed_index"],
            "expected_jobs": EXPECTED_JOBS,
            "expected_seeds": EXPECTED_SEEDS,
            "failed_retryable_current_jobs": counts["FAILED_RETRYABLE"],
            "maximum_attempt": max(attempts.values(), default=0),
            "phase": "P11",
            "running_jobs": counts["RUNNING"],
            "updated_at": now_utc(),
            "validated_jobs": counts["VALIDATED"],
            "validated_seeds": complete_seeds,
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


def assignment_for_job(job: dict[str, Any]) -> dict[str, str]:
    _prospective, canonical, layout_by_id = authority_context()
    assignment = within_layout_derangement(
        canonical["canonical_training_trajectory_ids"], layout_by_id, int(job["seed"])
    )
    require(canonical_sha256(assignment) == job["assignment_sha256"], "assignment identity")
    return assignment


def p8_job_view(job: dict[str, Any]) -> dict[str, Any]:
    return {
        "subset_id": CANONICAL_SUBSET_ID,
        "training_trajectory_ids": job["training_trajectory_ids"],
    }


def save_npz_atomic(path: Path, **arrays: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    with temporary.open("wb") as stream:
        np.savez_compressed(stream, **arrays)
    os.replace(temporary, path)


def run_worker(job_id: str) -> None:
    manifest = validate_manifest(require_p10_complete=True)
    job = next((record for record in manifest["jobs"] if record["job_id"] == job_id), None)
    require(job is not None, f"unknown P11 job {job_id}")
    assignment = assignment_for_job(job)
    context = NullJobContext(assignment)
    started = time.perf_counter()
    view = p8_job_view(job)
    if job["representation"] == "GLOBAL_MEAN":
        predictions, evidence, timing = p8.run_global(context, view)
    elif job["representation"] == "FULL_TOKEN_GRID":
        predictions, evidence, timing = p8.run_full(context, view)
    elif job["representation"] == "BEST_K_TOKENS":
        predictions, evidence, timing = p8.run_best_k(context, view)
    elif job["representation"] == "COARSE_2x6":
        p10.ensure_coarse_cache(full_hash=False)
        predictions, evidence, timing = p10.run_coarse(context, view)
    else:
        raise P11Error(f"unknown representation {job['representation']}")
    require(predictions.shape == (1080,), "P11 prediction shape")
    test_ids = list(context.test_ids)
    true_test_targets = context.true_targets(test_ids)
    metrics = metric_document(
        true_test_targets, predictions, test_ids, context.layouts(test_ids)
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
        "artifact_id": "large-scale-no-wall-p11-null-job-v0.1",
        "assignment_sha256": job["assignment_sha256"],
        "fixed_test_hash": job["fixed_test_hash"],
        "fixed_test_labels_true_and_untouched": True,
        "identity_sha256": job["identity_sha256"],
        "job_id": job_id,
        "metrics": metrics,
        "no_self_donor": True,
        "prediction_artifact": {
            "byte_count": prediction_path.stat().st_size,
            "path": str(prediction_path),
            "sha256": sha256_file(prediction_path),
        },
        "representation": job["representation"],
        "runtime": {
            **timing,
            "peak_host_bytes": max(
                int(timing.get("peak_host_bytes", 0)),
                int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024),
            ),
            "total_seconds": time.perf_counter() - started,
        },
        "seed": job["seed"],
        "seed_index": job["seed_index"],
        "selected_alpha": float(evidence["selected_alpha"]),
        "selected_k": evidence.get("selected_k"),
        "selected_token_indices": evidence.get("final_selected_token_indices"),
        "selection_artifact": {
            "byte_count": evidence_path.stat().st_size,
            "path": str(evidence_path),
            "sha256": sha256_file(evidence_path),
        },
        "selection_provenance": {
            "alpha_repeated_under_null_training_only": True,
            "best_k_repeated_under_null_training_only": job["representation"] == "BEST_K_TOKENS",
            "scaler_repeated_under_null_training_only": True,
            "test_used_for_selection": False,
            "token_ranking_repeated_under_null_training_only": job["representation"] == "BEST_K_TOKENS",
        },
        "status": "VALIDATED",
        "target_null_version": "PROSPECTIVE_WITHIN_LAYOUT_TRAJECTORY_DERANGEMENT_NULL_V0_1",
        "temporal_order_and_frame_alignment_preserved": True,
    }
    write_json(directory / "job_result.json", result)
    print(json.dumps({"job_id": job_id, "status": "VALIDATED"}, sort_keys=True))


def validate_job_result(job: dict[str, Any]) -> dict[str, Any]:
    path = JOB_ROOT / job["job_id"] / "job_result.json"
    require(path.is_file(), f"missing P11 job {job['job_id']}")
    result = read_json(path)
    require(result["status"] == "VALIDATED", "P11 job status")
    require(result["identity_sha256"] == job["identity_sha256"], "P11 identity")
    require(result["assignment_sha256"] == job["assignment_sha256"], "P11 assignment")
    require(result["seed"] == job["seed"], "P11 seed")
    require(result["fixed_test_labels_true_and_untouched"] is True, "P11 test labels")
    require(result["selection_provenance"]["test_used_for_selection"] is False, "P11 leakage")
    require(result["selected_alpha"] in p8.ALPHAS, "P11 alpha")
    assignment_for_job(job)
    if job["representation"] == "BEST_K_TOKENS":
        require(result["selected_k"] in p8.K_GRID, "P11 selected k")
        tokens = result["selected_token_indices"]
        require(tokens == sorted(tokens) and len(tokens) == result["selected_k"], "P11 selected tokens")
        evidence = read_json(Path(result["selection_artifact"]["path"]))
        ranking = evidence["final_ranking_evidence"]["ranking"]
        require(tuple(ranking) == rank_tokens(evidence["final_ranking_evidence"]["score_records"]), "P11 ranking")
        require(tokens == sorted(ranking[: result["selected_k"]]), "P11 top k")
    for key in ("prediction_artifact", "selection_artifact"):
        artifact = result[key]
        artifact_path = Path(artifact["path"])
        require(artifact_path.is_file(), f"missing P11 {key}")
        require(artifact_path.stat().st_size == artifact["byte_count"], f"P11 {key} size")
        require(sha256_file(artifact_path) == artifact["sha256"], f"P11 {key} hash")
    prediction = np.load(result["prediction_artifact"]["path"], allow_pickle=False)
    require(prediction["predictions"].shape == (1080,), "P11 predictions")
    require(np.isfinite(prediction["predictions"]).all(), "P11 finite predictions")
    require(result["runtime"]["peak_host_bytes"] <= p8.HOST_CEILING, "P11 host ceiling")
    require(result["runtime"]["peak_gpu_bytes"] <= p8.GPU_CEILING, "P11 GPU ceiling")
    return result


def run_jobs(*, seed_indices: set[int] | None) -> None:
    manifest = validate_manifest(require_p10_complete=True)
    p10.ensure_coarse_cache(full_hash=True)
    RESULT_ROOT.mkdir(parents=True, exist_ok=True)
    JOB_ROOT.mkdir(parents=True, exist_ok=True)
    latest, _, attempts = latest_ledger()
    for job in manifest["jobs"]:
        if seed_indices is not None and job["seed_index"] not in seed_indices:
            continue
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
                    "seed": job["seed"],
                    "seed_index": job["seed_index"],
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
                    "seed": job["seed"],
                    "seed_index": job["seed_index"],
                    "state": "RUNNING",
                }
            )
            write_progress(manifest, current_job=job["job_id"])
            log_path = RESULT_ROOT / "attempt_logs" / f"{job['job_id']}__attempt_{attempt}.log"
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with log_path.open("w", encoding="utf-8") as log:
                completed = subprocess.run(
                    [str(p8.QUALIFIED_PYTHON), str(Path(__file__).resolve()), "--worker", job["job_id"]],
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
                            "seed": job["seed"],
                            "seed_index": job["seed_index"],
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
                        "seed": job["seed"],
                        "seed_index": job["seed_index"],
                        "state": state,
                    }
                )
                write_progress(manifest, current_job=None)
                sync_control()
                if state == "BLOCKED":
                    raise P11Error(f"P11 job blocked: {job['job_id']}")
        latest, _, _ = latest_ledger()


def benchmark_first_seed() -> None:
    manifest = validate_manifest(require_p10_complete=True)
    require(manifest["benchmark"]["benchmark_seed_index"] == 0, "benchmark authority")
    run_jobs(seed_indices={0})
    jobs = [job for job in manifest["jobs"] if job["seed_index"] == 0]
    results = [validate_job_result(job) for job in jobs]
    receipt = {
        "artifact_id": "large-scale-no-wall-p11-first-seed-benchmark-v0.1",
        "benchmark_seed_index": 0,
        "execution_mechanics_changed_after_benchmark": False,
        "fixed_test_null_statistics_reported": False,
        "jobs_reused_as_exact_scientific_units": True,
        "representations": {
            result["representation"]: {
                "peak_gpu_bytes": result["runtime"]["peak_gpu_bytes"],
                "peak_host_bytes": result["runtime"]["peak_host_bytes"],
                "runtime_seconds": result["runtime"]["total_seconds"],
            }
            for result in results
        },
        "status": "PASS_FIRST_FROZEN_SEED_BENCHMARK_MECHANICS_FROZEN",
    }
    write_json(BENCHMARK_RECEIPT, receipt)
    subprocess.run(
        [
            "aws",
            "s3",
            "cp",
            str(BENCHMARK_RECEIPT),
            f"{S3_URI}repository_artifacts/{BENCHMARK_RECEIPT.name}",
            "--checksum-algorithm",
            "SHA256",
            "--only-show-errors",
        ],
        check=True,
    )


def run_all() -> None:
    require(BENCHMARK_RECEIPT.is_file(), "P11 first-seed benchmark receipt absent")
    require(
        read_json(BENCHMARK_RECEIPT)["status"]
        == "PASS_FIRST_FROZEN_SEED_BENCHMARK_MECHANICS_FROZEN",
        "P11 benchmark gate",
    )
    run_jobs(seed_indices=None)
    _latest, counts, _attempts = latest_ledger()
    require(counts["VALIDATED"] == EXPECTED_JOBS, "P11 incomplete")
    require(not counts["BLOCKED"] and not counts["RUNNING"], "P11 terminal ledger")


def completed_results(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    _latest, counts, _attempts = latest_ledger()
    require(counts["VALIDATED"] == EXPECTED_JOBS, "P11 completeness")
    require(not counts["BLOCKED"] and not counts["RUNNING"], "P11 ledger state")
    return [validate_job_result(job) for job in manifest["jobs"]]


def recompute_metrics(results: list[dict[str, Any]]) -> None:
    context = p8.JobContext()
    test_ids = list(context.test_ids)
    targets = context.targets(test_ids)
    rows = np.asarray(context.access.row_ordinals(test_ids), dtype=np.int64)
    for result in results:
        prediction = np.load(result["prediction_artifact"]["path"], allow_pickle=False)
        require(np.array_equal(prediction["row_ordinals"], rows), "P11 test row authority")
        metrics = metric_document(targets, prediction["predictions"], test_ids, context.layouts(test_ids))
        require(canonical_sha256(metrics) == canonical_sha256(result["metrics"]), "P11 metric recomputation")


def observed_statistics() -> dict[str, float]:
    p8_learning = read_json(p8.LEARNING_RESULTS)
    p10_learning = read_json(p10.RESULT)
    observed = {
        record["representation"]: float(record["metrics"]["equal_layout_macro"]["r2"])
        for record in p8_learning["job_records"]
        if record["subset_id"] == CANONICAL_SUBSET_ID
    }
    coarse = next(record for record in p10_learning["job_records"] if record["subset_id"] == CANONICAL_SUBSET_ID)
    observed["COARSE_2x6"] = float(coarse["metrics"]["equal_layout_macro"]["r2"])
    require(set(observed) == set(REPRESENTATIONS), "observed representation authority")
    return observed


def build_result(results: list[dict[str, Any]]) -> dict[str, Any]:
    observed = observed_statistics()
    by_representation: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for result in results:
        by_representation[result["representation"]].append(result)
    summaries = {}
    for representation in REPRESENTATIONS:
        records = sorted(by_representation[representation], key=lambda record: record["seed_index"])
        require(len(records) == EXPECTED_SEEDS, f"P11 {representation} B")
        values = [float(record["metrics"]["equal_layout_macro"]["r2"]) for record in records]
        exceedances = sum(value >= observed[representation] for value in values)
        empirical_p = (1 + exceedances) / (EXPECTED_SEEDS + 1)
        summaries[representation] = {
            "adjudication": "PASS_SEPARATED" if empirical_p <= 0.05 else "FAIL_NOT_SEPARATED",
            "empirical_upper_tail_p": empirical_p,
            "null_equal_layout_macro_r2": values,
            "null_summary": numeric_summary(values),
            "null_values_ge_observed": exceedances,
            "observed_equal_layout_macro_r2": observed[representation],
            "seed_order": [record["seed"] for record in records],
            "tail_alpha": 0.05,
        }
    return {
        "artifact_id": "large-scale-no-wall-p11-prospective-target-null-v0.1",
        "canonical_subset_id": CANONICAL_SUBSET_ID,
        "empirical_upper_tail_formula": "(1 + count(null >= observed)) / (49 + 1)",
        "fixed_statistic": "fixed-test equal-layout macro per-trajectory R2",
        "null_replicates": EXPECTED_SEEDS,
        "null_version": "PROSPECTIVE_WITHIN_LAYOUT_TRAJECTORY_DERANGEMENT_NULL_V0_1",
        "representations": summaries,
        "status": "PASS_P11_COMPLETE_49_OF_49",
        "test_targets_true_and_untouched": True,
        "training_target_unit": "complete 60-row trajectory profile",
    }


def aggregate() -> None:
    manifest = validate_manifest(require_p10_complete=True)
    results = completed_results(manifest)
    recompute_metrics(results)
    document = build_result(results)
    write_json(RESULT, document)
    validation = {
        "artifact_id": "large-scale-no-wall-p11-validation-receipt-v0.1",
        "all_49_frozen_seeds_complete": True,
        "all_derangements_no_self_donor": True,
        "best_k_selection_repeated_per_null": True,
        "expected_jobs": EXPECTED_JOBS,
        "fixed_test_labels_true_and_untouched": True,
        "metrics_recomputed_from_predictions": True,
        "prospective_null_results_sha256": sha256_file(RESULT),
        "status": "PASS_P11_COMPLETE_VALIDATED",
        "validated_jobs": len(results),
    }
    write_json(VALIDATION_RECEIPT, validation)
    receipt = {
        "artifact_id": "large-scale-no-wall-p11-receipt-v0.1",
        "blocker": None,
        "result_sha256": sha256_file(RESULT),
        "status": "PASS_P11_PROSPECTIVE_NULL_COMPLETE",
        "total_completed": len(results),
        "validated_seed_count": EXPECTED_SEEDS,
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
    manifest = validate_manifest(require_p10_complete=True)
    results = completed_results(manifest)
    recompute_metrics(results)
    require(RESULT.is_file(), "P11 result missing")
    require(canonical_sha256(read_json(RESULT)) == canonical_sha256(build_result(results)), "P11 deterministic aggregate")
    validation = read_json(VALIDATION_RECEIPT)
    receipt = read_json(RECEIPT)
    require(validation["status"] == "PASS_P11_COMPLETE_VALIDATED", "P11 validation")
    require(validation["prospective_null_results_sha256"] == sha256_file(RESULT), "P11 result hash")
    require(receipt["status"] == "PASS_P11_PROSPECTIVE_NULL_COMPLETE", "P11 receipt")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--validate-manifest", action="store_true")
    parser.add_argument("--benchmark-first-seed", action="store_true")
    parser.add_argument("--worker")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--aggregate", action="store_true")
    parser.add_argument("--validate", action="store_true")
    args = parser.parse_args()
    actions = sum(bool(x) for x in (args.prepare, args.validate_manifest, args.benchmark_first_seed, args.worker, args.run, args.aggregate, args.validate))
    require(actions == 1, "choose exactly one P11 action")
    if args.prepare:
        freeze_manifest()
        print("PASS P11 frozen 49-seed x 4-representation manifest")
    elif args.validate_manifest:
        print(f"PASS P11 manifest {len(validate_manifest(require_p10_complete=False)['jobs'])}/196")
    elif args.benchmark_first_seed:
        benchmark_first_seed()
        print("PASS P11 first frozen seed benchmark; mechanics unchanged")
    elif args.worker:
        run_worker(args.worker)
    elif args.run:
        run_all()
        print("PASS P11 execution 196/196")
    elif args.aggregate:
        aggregate()
        print("PASS P11 aggregate and durability")
    else:
        validate_complete()
        print("PASS P11 final validation gate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
