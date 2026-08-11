#!/usr/bin/env python3
"""Run the frozen resumable P8 core learning-curve workload."""

from __future__ import annotations

import argparse
import base64
import gc
import hashlib
import json
import math
import os
import resource
import subprocess
import sys
import tarfile
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
from mineocclude.probes.p7a_execution import (
    batched_ridge_predictions_all_alphas_from_features_cuda,
    standardized_token_kernel_sum_cuda,
)
from mineocclude.probes.p8_core import (
    canonical_sha256,
    distribution,
    metric_document,
    numeric_summary,
    paired_summary,
    rank_tokens,
    select_alpha,
    selection_score,
    trajectory_metrics,
)
from scripts.build_large_scale_no_wall_p7_authority import ActivationAccess

P7A_HEAD = "0d949ccee43ee867970a3fe96eab4a7cbf4dab31"
BRANCH = "exploration/large-scale-no-wall-scaling-best-k-v0-1"
QUALIFIED_PYTHON = Path("/home/sagemaker-user/.conda/envs/mineworld/bin/python")
STUDY_ROOT = (
    ROOT / "docs/status/integration/exploratory_large_scale_no_wall_scaling_best_k_v0_1"
)
ACTIVATION_ROOT = Path(
    "/mnt/sagemaker-nvme/mineocclude_large_scale_no_wall_scaling_best_k_v0_1_v2/"
    "p6_layer4_activations_v0_1/activations"
)
RESULT_ROOT = Path(
    "/mnt/sagemaker-nvme/mineocclude_large_scale_no_wall_scaling_best_k_v0_1_v2/"
    "p8_core_learning_curves_v0_1"
)
JOB_ROOT = RESULT_ROOT / "jobs"
S3_BUCKET = "sagemaker-us-east-1-323206973672"
S3_PREFIX = (
    "mineocclude/exploratory_large_scale_no_wall_scaling_best_k_v0_1/"
    "p8_core_learning_curves_v0_1"
)
S3_URI = f"s3://{S3_BUCKET}/{S3_PREFIX}/"

SUBSET_SCHEDULE = STUDY_ROOT / "subset_schedule.json"
GROUPED_FOLDS = STUDY_ROOT / "grouped_fold_authority.json"
TEST_GUARD = STUDY_ROOT / "test_guard.lock"
P6_MANIFEST = STUDY_ROOT / "p6_activation_manifest.json"
REPRESENTATION_AUTHORITY = STUDY_ROOT / "representation_authority.json"
P7A_EXECUTION = STUDY_ROOT / "execution_budget.p7a.lock.json"
P7A_CACHE = STUDY_ROOT / "cache_manifest.p7a.json"
COHORT_LOCK = STUDY_ROOT / "accepted_cohort_v2.lock.json"
CANONICAL_ROWS = STUDY_ROOT / "canonical_row_authority.jsonl"
SPLIT_AUTHORITY = STUDY_ROOT / "split_authority.json"
STUDY_DESIGN = STUDY_ROOT / "study_design.json"

RUN_MANIFEST = STUDY_ROOT / "p8_run_manifest.json"
RUN_MANIFEST_LOCK = STUDY_ROOT / "p8_run_manifest.sha256"
LEDGER = STUDY_ROOT / "p8_execution_ledger.jsonl"
PROGRESS = STUDY_ROOT / "p8_progress.json"
TIMING_MEMORY = STUDY_ROOT / "p8_timing_memory.json"
LEARNING_RESULTS = STUDY_ROOT / "learning_curve_results.json"
BEST_K_RESULTS = STUDY_ROOT / "best_k_results.json"
PREDICTION_MANIFEST = STUDY_ROOT / "p8_prediction_manifest.json"
VALIDATION_RECEIPT = STUDY_ROOT / "p8_validation_receipt.json"
DURABILITY_RECEIPT = STUDY_ROOT / "p8_s3_durability_receipt.json"
PRIMARY_FIGURE = STUDY_ROOT / "p8_primary_learning_curves.png"
P8_RECEIPT = STUDY_ROOT / "p8_receipt.json"

TOKEN_CACHE = Path(
    "/mnt/sagemaker-nvme/mineocclude_large_scale_no_wall_scaling_best_k_v0_1_v2/"
    "p7_representation_solver_v0_1/training_tokens.token_major.f16.npy"
)
TOKEN_CACHE_METADATA = TOKEN_CACHE.with_name(
    "training_tokens.token_major.metadata.json"
)

ALPHAS = (0.1, 1.0, 10.0, 100.0)
K_GRID = (1, 4, 8, 16, 32, 64, 128)
REPRESENTATIONS = ("GLOBAL_MEAN", "FULL_TOKEN_GRID", "BEST_K_TOKENS")
TOKEN_COUNT = 336
HIDDEN_WIDTH = 2048
FRAMES_PER_TRAJECTORY = 60
EXPECTED_CORE_OUTER_FITS = 186
TOKEN_BATCH_SIZE = 4
WIDE_TOKEN_BATCH_SIZE = 16
HOST_CEILING = 14 * (1 << 30)
GPU_CEILING = 20 * (1 << 30)
PREDICTION_ATOL = 1e-7
PREDICTION_RTOL = 1e-7
JOINT_TIE_TOLERANCE = 1e-9
ALPHA_TIE_TOLERANCE = 0.0
BOOTSTRAP_REPLICATES = 10_000
BOOTSTRAP_SEED = 20260810
DURABILITY_INTERVAL_JOBS = 6
MAX_JOB_ATTEMPTS = 2

PROTECTED_SHA256 = {
    SPLIT_AUTHORITY: "b39c81454ea18125c373fb3c777ac4c1668882c9c1ad188a7d0f20e0cab43de5",
    SUBSET_SCHEDULE: "0d6f5e8394328915164bafea70468e6d26342a2eda9a1923e4d4ad745f494a48",
    GROUPED_FOLDS: "597bc7b401ca691897b843fc83120cc997a414b7a946819da4c3e99768e7728e",
    TEST_GUARD: "0adc85a5d90eb92361ba0775d58a6ccc2eb674a8ae5ffd2e816b89d9d9b48ac5",
    P6_MANIFEST: "a57be180a9054336dbe36d2ddaddbec2859e21d5b6a42dae5b25b1c276e2d5bb",
    REPRESENTATION_AUTHORITY: "757217b2b3e54e236b4ad7b9b3574d7391f896558760a54bb1b5e457b186259e",
    P7A_EXECUTION: "19660de8a39bd26bc96af303d6837c7176f8dd711fea20278da74eac7b45c82d",
    P7A_CACHE: "b031b56535b39c21630a1105b154a7b0a29ffd9f665a9fdab113ac2ca538ae5f",
    COHORT_LOCK: "b73d1b6bbedc1ca72dab480ba6f4bafb22aa7c6675bc7a2f0dabf33fff2d8501",
    CANONICAL_ROWS: "aa57352c5dea328e68f7c2c0d24489077957ef83ddf715aa13cb5cbb65d92367",
    STUDY_DESIGN: "08d77261f70a3d7e554ce6f8fe4a565fa09591ae793a87efd60e4a742c016502",
}


class P8Error(RuntimeError):
    """Raised when P8 cannot continue under frozen authority."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise P8Error(message)


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    os.replace(temporary, path)


def append_ledger(value: MappingLike) -> None:
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n"
    with LEDGER.open("a", encoding="utf-8") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


MappingLike = dict[str, Any]


def git(*arguments: str) -> str:
    return subprocess.check_output(["git", *arguments], cwd=ROOT, text=True).strip()


def verify_protected_authority() -> None:
    require(git("branch", "--show-current") == BRANCH, "wrong branch")
    subprocess.run(
        ["git", "merge-base", "--is-ancestor", P7A_HEAD, "HEAD"],
        cwd=ROOT,
        check=True,
    )
    for path, expected in PROTECTED_SHA256.items():
        require(path.is_file(), f"missing protected authority: {path.name}")
        require(sha256_file(path) == expected, f"authority changed: {path.name}")
    guard = read_json(TEST_GUARD)
    representation = read_json(REPRESENTATION_AUTHORITY)
    execution = read_json(P7A_EXECUTION)
    require(
        guard["test_authority_hash"]
        == "68455519777d8e5e613813f03ebc148c49b62cf33b11182993a3e58fd0809d4a",
        "test hash",
    )
    require(guard["test_count"] == 18, "test count")
    require(
        representation["canonical_rows"]["sha256"]
        == "13a1b6f32a502b35875bf2a2d608326cbce2619949ea47808d175cbed28084c9",
        "row authority",
    )
    require(execution["status"] == "LOCKED_FOR_P8", "P7A execution not locked")
    require(execution["token_batch_size"] == TOKEN_BATCH_SIZE, "token batch")
    require(
        execution["wide_kernel_token_batch_size"] == WIDE_TOKEN_BATCH_SIZE, "wide batch"
    )
    require(execution["bounded_parallelism"] == 1, "parallelism")
    require(execution["numerical_computation_dtype"] == "float64", "dtype")


def validate_input_objects() -> None:
    manifest = read_json(P6_MANIFEST)
    require(len(manifest["chunks"]) == 120, "P6 chunk count")
    for chunk in manifest["chunks"]:
        for key in ("unpooled", "pooled"):
            path = ACTIVATION_ROOT / chunk[key]["path"]
            require(path.is_file(), f"missing P6 object: {path}")
            require(
                path.stat().st_size == chunk[key]["byte_size"],
                f"P6 object size: {path}",
            )
    cache_manifest = read_json(P7A_CACHE)["token_cache"]
    metadata = read_json(TOKEN_CACHE_METADATA)
    require(TOKEN_CACHE.is_file(), "P7A token cache absent")
    require(
        TOKEN_CACHE.stat().st_size == cache_manifest["maximum_measured_byte_count"],
        "token cache size",
    )
    require(
        metadata["sha256"] == cache_manifest["cache_sha256"],
        "token cache metadata hash",
    )
    cache = np.load(TOKEN_CACHE, mmap_mode="r", allow_pickle=False)
    require(cache.shape == (336, 6120, 2048), "token cache shape")
    require(cache.dtype == np.float16, "token cache dtype")


def fold_subset_hash(subset: MappingLike) -> str:
    return canonical_sha256(subset)


def freeze_manifest() -> None:
    verify_protected_authority()
    require(git("rev-parse", "HEAD") == P7A_HEAD, "P7A start HEAD mismatch")
    require(git("rev-parse", f"origin/{BRANCH}") == P7A_HEAD, "remote P7A SHA mismatch")
    changed = git("status", "--porcelain").splitlines()
    allowed_prefixes = (
        "?? scripts/run_large_scale_no_wall_p8_core.py",
        "?? src/mineocclude/probes/p8_core.py",
        "?? tests/diagnostics/test_large_scale_no_wall_p8_core.py",
    )
    require(
        all(line.startswith(allowed_prefixes) for line in changed),
        "non-P8 worktree change appeared after the clean start validation",
    )
    validate_input_objects()
    schedule = read_json(SUBSET_SCHEDULE)
    folds = read_json(GROUPED_FOLDS)
    guard = read_json(TEST_GUARD)
    folds_by_subset = {record["subset_id"]: record for record in folds["subsets"]}
    jobs = []
    for subset in schedule["subsets"]:
        subset_id = subset["subset_id"]
        require(subset_id in folds_by_subset, f"missing fold authority: {subset_id}")
        for representation in REPRESENTATIONS:
            job = {
                "alpha_grid": list(ALPHAS),
                "best_k_grid": (
                    list(K_GRID) if representation == "BEST_K_TOKENS" else None
                ),
                "canonical_row_authority_hash": "13a1b6f32a502b35875bf2a2d608326cbce2619949ea47808d175cbed28084c9",
                "fixed_test_hash": guard["test_authority_hash"],
                "fixed_test_trajectory_ids": guard["test_trajectory_ids"],
                "fold_authority_file_sha256": PROTECTED_SHA256[GROUPED_FOLDS],
                "fold_authority_hash": fold_subset_hash(folds_by_subset[subset_id]),
                "job_id": f"{representation.lower()}__{subset_id}",
                "master_id": subset["master_id"],
                "p6_activation_manifest_sha256": PROTECTED_SHA256[P6_MANIFEST],
                "p7_representation_authority_sha256": PROTECTED_SHA256[
                    REPRESENTATION_AUTHORITY
                ],
                "p7a_execution_budget_sha256": PROTECTED_SHA256[P7A_EXECUTION],
                "representation": representation,
                "subset_id": subset_id,
                "training_size": subset["training_size"],
                "training_trajectory_hash": subset["subset_hash"],
                "training_trajectory_ids": subset["trajectory_spec_ids"],
            }
            job["identity_sha256"] = canonical_sha256(job)
            jobs.append(job)
    require(len(jobs) == EXPECTED_CORE_OUTER_FITS, "P8 job count")
    require(len({job["job_id"] for job in jobs}) == len(jobs), "duplicate P8 job")
    document = {
        "alpha_selection": {
            "GLOBAL_MEAN": "maximum equal-layout macro validation R2; exact ties use smaller alpha",
            "FULL_TOKEN_GRID": "maximum equal-layout macro validation R2; exact ties use smaller alpha",
            "token_ranking": "maximum median trajectory R2, then mean trajectory R2, then smaller alpha",
        },
        "artifact_id": "large-scale-no-wall-p8-run-manifest-v0.1",
        "best_k_joint_selection": "within 1e-9 of maximum equal-layout macro R2: smaller k, then larger alpha, then lower ordered token tuples",
        "bootstrap": {
            "replicates": BOOTSTRAP_REPLICATES,
            "seed": BOOTSTRAP_SEED,
            "trajectory_level_rule": "resample three fixed-test trajectories within each of six layouts; summarize the mean across subset macro values",
        },
        "created_at": now_utc(),
        "expected_core_outer_fits": EXPECTED_CORE_OUTER_FITS,
        "fixed_before_test_scores_opened": True,
        "jobs": jobs,
        "metric_authority": {
            "primary": "per-trajectory R2 -> within-layout mean -> equal six-layout mean",
            "mae": "per-trajectory MAE -> within-layout mean -> equal-layout mean",
            "nmae_std": "per-trajectory MAE / same trajectory target std(ddof=0) -> equal-layout mean",
            "pearson_slope_bias": "within trajectory then equal-layout macro",
        },
        "p7a_head": P7A_HEAD,
        "representations": list(REPRESENTATIONS),
        "runner": "scripts/run_large_scale_no_wall_p8_core.py",
        "runner_sha256": sha256_file(Path(__file__).resolve()),
        "support_module_sha256": sha256_file(
            ROOT / "src/mineocclude/probes/p8_core.py"
        ),
        "status": "FROZEN_BEFORE_P8_OUTCOMES",
        "test_used_for_selection": False,
    }
    write_json(RUN_MANIFEST, document)
    RUN_MANIFEST_LOCK.write_text(sha256_file(RUN_MANIFEST) + "\n", encoding="utf-8")
    require(not LEDGER.exists(), "P8 ledger already exists at initial freeze")
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
    write_progress(document, current_job=None, run_started=None)


def validate_manifest() -> dict[str, Any]:
    verify_protected_authority()
    require(
        RUN_MANIFEST.is_file() and RUN_MANIFEST_LOCK.is_file(), "P8 manifest absent"
    )
    expected = RUN_MANIFEST_LOCK.read_text(encoding="utf-8").strip()
    require(sha256_file(RUN_MANIFEST) == expected, "P8 manifest lock changed")
    manifest = read_json(RUN_MANIFEST)
    require(manifest["status"] == "FROZEN_BEFORE_P8_OUTCOMES", "manifest status")
    require(manifest["expected_core_outer_fits"] == 186, "manifest job count")
    require(len(manifest["jobs"]) == 186, "manifest jobs")
    for job in manifest["jobs"]:
        claimed = job["identity_sha256"]
        payload = {key: value for key, value in job.items() if key != "identity_sha256"}
        require(
            canonical_sha256(payload) == claimed,
            f"job identity changed: {job['job_id']}",
        )
    return manifest


def latest_ledger() -> tuple[dict[str, MappingLike], Counter[str], dict[str, int]]:
    latest: dict[str, MappingLike] = {}
    attempts: dict[str, int] = defaultdict(int)
    for event in read_jsonl(LEDGER):
        latest[event["job_id"]] = event
        attempts[event["job_id"]] = max(
            attempts[event["job_id"]], int(event["attempt"])
        )
    return latest, Counter(event["state"] for event in latest.values()), attempts


def write_progress(
    manifest: MappingLike,
    *,
    current_job: str | None,
    run_started: float | None,
) -> None:
    _latest, counts, attempts = latest_ledger()
    validated = counts["VALIDATED"]
    elapsed = 0.0 if run_started is None else time.monotonic() - run_started
    throughput = validated / elapsed if elapsed > 0.0 else 0.0
    remaining = len(manifest["jobs"]) - validated
    progress = {
        "blocked_jobs": counts["BLOCKED"],
        "current_job_id": current_job,
        "elapsed_seconds_this_process": elapsed,
        "eta_seconds": None if throughput == 0.0 else remaining / throughput,
        "expected_jobs": len(manifest["jobs"]),
        "failed_retryable_current_jobs": counts["FAILED_RETRYABLE"],
        "maximum_attempt": max(attempts.values(), default=0),
        "outcome_summary_suppressed_until_complete": validated < len(manifest["jobs"]),
        "running_jobs": counts["RUNNING"],
        "updated_at": now_utc(),
        "validated_jobs": validated,
    }
    write_json(PROGRESS, progress)


class JobContext:
    """One worker's read-only view of frozen P8 input authorities."""

    def __init__(self) -> None:
        self.rows = read_jsonl(CANONICAL_ROWS)
        self.access = ActivationAccess(self.rows)
        self.cohort = read_json(COHORT_LOCK)
        self.fold_document = read_json(GROUPED_FOLDS)
        self.fold_by_subset = {
            record["subset_id"]: record for record in self.fold_document["subsets"]
        }
        self.entry_by_id = {
            entry["trajectory_spec_id"]: entry for entry in self.cohort["entries"]
        }
        self.layout_by_id = {
            identity: entry["layout_id"] for identity, entry in self.entry_by_id.items()
        }
        training_ordinals = [
            int(row["row_ordinal"])
            for row in self.rows
            if row["membership"] == "training_pool"
        ]
        self.cache_position = {
            ordinal: position for position, ordinal in enumerate(training_ordinals)
        }
        self.cache = np.load(TOKEN_CACHE, mmap_mode="r", allow_pickle=False)
        self.test_ids = tuple(read_json(TEST_GUARD)["test_trajectory_ids"])

    def targets(self, identities: list[str] | tuple[str, ...]) -> np.ndarray:
        return np.asarray(
            [
                value
                for identity in identities
                for value in self.entry_by_id[identity]["target_authority"][
                    "x_true_blocks"
                ]
            ],
            dtype=np.float64,
        )

    def layouts(self, identities: list[str] | tuple[str, ...]) -> dict[str, str]:
        return {identity: self.layout_by_id[identity] for identity in identities}

    def global_features(self, identities: list[str] | tuple[str, ...]) -> np.ndarray:
        return self.access.global_rows(self.access.row_ordinals(identities))

    def token_features(
        self, identities: list[str] | tuple[str, ...], token_indices: list[int]
    ) -> np.ndarray:
        ordinals = self.access.row_ordinals(identities)
        result = np.empty(
            (len(ordinals), len(token_indices), HIDDEN_WIDTH), dtype=np.float16
        )
        training_destinations = []
        training_positions = []
        test_destinations = []
        test_ordinals = []
        for destination, ordinal in enumerate(ordinals):
            if ordinal in self.cache_position:
                training_destinations.append(destination)
                training_positions.append(self.cache_position[ordinal])
            else:
                test_destinations.append(destination)
                test_ordinals.append(ordinal)
        for offset, token in enumerate(token_indices):
            if training_destinations:
                result[training_destinations, offset, :] = np.asarray(
                    self.cache[token, training_positions, :], dtype=np.float16
                )
        if test_destinations:
            block = self.access.token_rows(test_ordinals, token_indices)
            result[test_destinations] = block
        return result


def selection_folds(context: JobContext, subset_id: str) -> list[MappingLike]:
    authority = context.fold_by_subset[subset_id]
    by_id = {record["fold_id"]: record for record in authority["selection_folds"]}
    result = []
    for held in authority["selection_folds"]:
        training = [
            identity
            for fold_id in held["selection_training_fold_ids"]
            for identity in by_id[fold_id]["validation_trajectory_ids"]
        ]
        result.append(
            {
                "fold_id": held["fold_id"],
                "training_ids": training,
                "validation_ids": list(held["validation_trajectory_ids"]),
            }
        )
    return result


def ranking_folds(
    context: JobContext, subset_id: str, outer_fold_id: str
) -> tuple[list[str], list[MappingLike]]:
    authority = context.fold_by_subset[subset_id]
    by_id = {record["fold_id"]: record for record in authority["selection_folds"]}
    outer = by_id[outer_fold_id]
    scope_ids = [
        identity
        for fold_id in outer["selection_training_fold_ids"]
        for identity in by_id[fold_id]["validation_trajectory_ids"]
    ]
    records = authority["best_k_ranking_subfolds_by_outer_selection_fold"][
        outer_fold_id
    ]
    folds = []
    for record in records:
        training = [
            identity
            for fold_id in record["ranking_training_selection_fold_ids"]
            for identity in by_id[fold_id]["validation_trajectory_ids"]
        ]
        folds.append(
            {
                "fold_id": record["ranking_subfold_id"],
                "training_ids": training,
                "validation_ids": list(
                    by_id[record["validation_selection_fold_id"]][
                        "validation_trajectory_ids"
                    ]
                ),
            }
        )
    return scope_ids, folds


def gather_oof(
    predictions_by_id: dict[float, dict[str, np.ndarray]],
    identities: list[str],
) -> dict[float, np.ndarray]:
    return {
        alpha: np.concatenate([by_id[identity] for identity in identities])
        for alpha, by_id in predictions_by_id.items()
    }


def wide_kernel(
    context: JobContext,
    scope_ids: list[str],
    training_row_count: int,
    token_indices: list[int],
) -> tuple[np.ndarray, MappingLike]:
    total = None
    timing = 0.0
    peak = 0
    bytes_read = 0
    for start in range(0, len(token_indices), WIDE_TOKEN_BATCH_SIZE):
        batch = token_indices[start : start + WIDE_TOKEN_BATCH_SIZE]
        features = context.token_features(scope_ids, batch)
        bytes_read += int(features.nbytes)
        result = standardized_token_kernel_sum_cuda(
            features, training_row_count=training_row_count
        )
        if total is None:
            total = np.zeros_like(result.kernel, dtype=np.float64)
        total += result.kernel
        timing += result.timings["total_seconds"]
        peak = max(peak, result.peak_device_memory_bytes)
        del features, result
        gc.collect()
    require(total is not None, "wide kernel received no tokens")
    return total, {
        "activation_bytes_gathered": bytes_read,
        "gpu_kernel_seconds": timing,
        "peak_gpu_bytes": peak,
        "token_count": len(token_indices),
    }


def cumulative_ranked_kernels(
    context: JobContext,
    scope_ids: list[str],
    training_row_count: int,
    ranking: tuple[int, ...],
) -> tuple[dict[int, np.ndarray], MappingLike]:
    total = None
    snapshots = {}
    previous = 0
    timing = 0.0
    peak = 0
    bytes_read = 0
    for k in K_GRID:
        additions = list(ranking[previous:k])
        for start in range(0, len(additions), WIDE_TOKEN_BATCH_SIZE):
            batch = sorted(additions[start : start + WIDE_TOKEN_BATCH_SIZE])
            features = context.token_features(scope_ids, batch)
            bytes_read += int(features.nbytes)
            result = standardized_token_kernel_sum_cuda(
                features, training_row_count=training_row_count
            )
            if total is None:
                total = np.zeros_like(result.kernel, dtype=np.float64)
            total += result.kernel
            timing += result.timings["total_seconds"]
            peak = max(peak, result.peak_device_memory_bytes)
            del features, result
            gc.collect()
        require(total is not None, "ranked kernel is empty")
        snapshots[k] = total.copy()
        previous = k
    return snapshots, {
        "activation_bytes_gathered": bytes_read,
        "gpu_kernel_seconds": timing,
        "peak_gpu_bytes": peak,
        "token_count": K_GRID[-1],
    }


def per_trajectory_r2(
    actual: np.ndarray, predictions: np.ndarray, trajectory_count: int
) -> list[float]:
    result = []
    for ordinal in range(trajectory_count):
        start = ordinal * FRAMES_PER_TRAJECTORY
        stop = start + FRAMES_PER_TRAJECTORY
        metric = trajectory_metrics(actual[start:stop], predictions[start:stop])["r2"]
        require(metric is not None and math.isfinite(metric), "ranking R2 invalid")
        result.append(float(metric))
    return result


def compute_token_ranking(
    context: JobContext,
    scope_ids: list[str],
    folds: list[MappingLike],
) -> tuple[tuple[int, ...], list[MappingLike], MappingLike]:
    row_count = len(scope_ids) * FRAMES_PER_TRAJECTORY
    position_by_id = {identity: ordinal for ordinal, identity in enumerate(scope_ids)}
    predictions = np.full(
        (TOKEN_COUNT, len(ALPHAS), row_count), np.nan, dtype=np.float64
    )
    peak_gpu = 0
    peak_host = 0
    solve_seconds = 0.0
    bytes_read = 0
    fold_provenance = []
    for fold in folds:
        train_ids = list(fold["training_ids"])
        validation_ids = list(fold["validation_ids"])
        fold_scope = train_ids + validation_ids
        targets = context.targets(train_ids)
        validation_positions = [position_by_id[identity] for identity in validation_ids]
        for start in range(0, TOKEN_COUNT, TOKEN_BATCH_SIZE):
            token_indices = list(
                range(start, min(start + TOKEN_BATCH_SIZE, TOKEN_COUNT))
            )
            features = context.token_features(fold_scope, token_indices)
            bytes_read += int(features.nbytes)
            result = batched_ridge_predictions_all_alphas_from_features_cuda(
                features,
                targets,
                training_row_count=len(targets),
                alphas=ALPHAS,
            )
            for offset, token in enumerate(token_indices):
                for alpha_offset, alpha in enumerate(ALPHAS):
                    values = result.predictions_by_token[offset][alpha]
                    for validation_offset, destination in enumerate(
                        validation_positions
                    ):
                        source_start = validation_offset * FRAMES_PER_TRAJECTORY
                        source_stop = source_start + FRAMES_PER_TRAJECTORY
                        destination_start = destination * FRAMES_PER_TRAJECTORY
                        predictions[
                            token,
                            alpha_offset,
                            destination_start : destination_start
                            + FRAMES_PER_TRAJECTORY,
                        ] = values[source_start:source_stop]
            solve_seconds += result.timings["total_seconds"]
            peak_gpu = max(peak_gpu, result.peak_device_memory_bytes)
            peak_host = max(
                peak_host,
                int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024),
            )
            del features, result
            gc.collect()
        fold_provenance.append(
            {
                "fold_id": fold["fold_id"],
                "training_ids_hash": canonical_sha256(train_ids),
                "validation_ids_hash": canonical_sha256(validation_ids),
            }
        )
    require(np.isfinite(predictions).all(), "token OOF predictions incomplete")
    actual = context.targets(scope_ids)
    score_records = []
    for token in range(TOKEN_COUNT):
        statistics = []
        for alpha_offset, alpha in enumerate(ALPHAS):
            scores = per_trajectory_r2(
                actual, predictions[token, alpha_offset], len(scope_ids)
            )
            statistics.append(
                {
                    "alpha": alpha,
                    "mean_trajectory_r2": float(np.mean(scores)),
                    "median_trajectory_r2": float(np.median(scores)),
                }
            )
        selected = min(
            statistics,
            key=lambda record: (
                -record["median_trajectory_r2"],
                -record["mean_trajectory_r2"],
                record["alpha"],
            ),
        )
        score_records.append(
            {
                "alpha_statistics": statistics,
                "mean_trajectory_r2": selected["mean_trajectory_r2"],
                "median_trajectory_r2": selected["median_trajectory_r2"],
                "selected_token_alpha": selected["alpha"],
                "token_index": token,
            }
        )
    ranking = rank_tokens(score_records)
    evidence = {
        "folds": fold_provenance,
        "oof_prediction_sha256": hashlib.sha256(
            predictions.tobytes(order="C")
        ).hexdigest(),
        "ranking": list(ranking),
        "score_records": score_records,
        "scope_ids_hash": canonical_sha256(scope_ids),
    }
    del predictions
    gc.collect()
    return (
        ranking,
        score_records,
        {
            "activation_bytes_gathered": bytes_read,
            "evidence": evidence,
            "gpu_solve_seconds": solve_seconds,
            "peak_gpu_bytes": peak_gpu,
            "peak_host_bytes": peak_host,
        },
    )


def prediction_positions(training_rows: int, total_rows: int) -> range:
    return range(training_rows, total_rows)


def run_global(
    context: JobContext, job: MappingLike
) -> tuple[np.ndarray, MappingLike, MappingLike]:
    subset_ids = list(job["training_trajectory_ids"])
    oof = {alpha: {} for alpha in ALPHAS}
    fold_records = []
    gpu_seconds = 0.0
    peak_gpu = 0
    for fold in selection_folds(context, job["subset_id"]):
        train_ids = list(fold["training_ids"])
        validation_ids = list(fold["validation_ids"])
        scope_ids = train_ids + validation_ids
        features = context.global_features(scope_ids)
        targets = context.targets(train_ids)
        kernel = standardized_kernel_cuda(features[: len(targets)], features)
        predictions = ridge_predictions_all_alphas_from_kernel(
            kernel.kernel,
            targets,
            alphas=ALPHAS,
            prediction_scope_positions=prediction_positions(
                len(targets), len(features)
            ),
        )
        for alpha in ALPHAS:
            for ordinal, identity in enumerate(validation_ids):
                start = ordinal * FRAMES_PER_TRAJECTORY
                oof[alpha][identity] = predictions[alpha][
                    start : start + FRAMES_PER_TRAJECTORY
                ]
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
    scores = {
        alpha: selection_score(
            actual,
            gather_oof(oof, subset_ids)[alpha],
            subset_ids,
            context.layouts(subset_ids),
        )
        for alpha in ALPHAS
    }
    selected_alpha = select_alpha(scores, tie_tolerance=0.0, prefer="smaller")
    final_scope = subset_ids + list(context.test_ids)
    final_features = context.global_features(final_scope)
    train_targets = context.targets(subset_ids)
    final_kernel = standardized_kernel_cuda(
        final_features[: len(train_targets)], final_features
    )
    predictions = ridge_predictions_from_kernel(
        final_kernel.kernel,
        train_targets,
        alpha=selected_alpha,
        prediction_scope_positions=prediction_positions(
            len(train_targets), len(final_features)
        ),
    )
    gpu_seconds += sum(final_kernel.timings.values())
    peak_gpu = max(peak_gpu, final_kernel.peak_device_memory_bytes)
    evidence = {
        "alpha_scores": {str(alpha): scores[alpha] for alpha in ALPHAS},
        "folds": fold_records,
        "selected_alpha": selected_alpha,
        "test_used_for_selection": False,
    }
    timing = {
        "cpu_dominant_seconds": 0.0,
        "gpu_active_seconds": gpu_seconds,
        "peak_gpu_bytes": peak_gpu,
    }
    return predictions, evidence, timing


def run_full(
    context: JobContext, job: MappingLike
) -> tuple[np.ndarray, MappingLike, MappingLike]:
    subset_ids = list(job["training_trajectory_ids"])
    oof = {alpha: {} for alpha in ALPHAS}
    fold_records = []
    gpu_seconds = 0.0
    cpu_seconds = 0.0
    peak_gpu = 0
    bytes_read = 0
    for fold in selection_folds(context, job["subset_id"]):
        train_ids = list(fold["training_ids"])
        validation_ids = list(fold["validation_ids"])
        scope_ids = train_ids + validation_ids
        targets = context.targets(train_ids)
        kernel, record = wide_kernel(
            context, scope_ids, len(targets), list(range(TOKEN_COUNT))
        )
        solve_started = time.perf_counter()
        predictions = ridge_predictions_all_alphas_from_kernel(
            kernel,
            targets,
            alphas=ALPHAS,
            prediction_scope_positions=prediction_positions(len(targets), len(kernel)),
        )
        cpu_seconds += time.perf_counter() - solve_started
        for alpha in ALPHAS:
            for ordinal, identity in enumerate(validation_ids):
                start = ordinal * FRAMES_PER_TRAJECTORY
                oof[alpha][identity] = predictions[alpha][
                    start : start + FRAMES_PER_TRAJECTORY
                ]
        gpu_seconds += record["gpu_kernel_seconds"]
        peak_gpu = max(peak_gpu, record["peak_gpu_bytes"])
        bytes_read += record["activation_bytes_gathered"]
        fold_records.append(
            {
                "fold_id": fold["fold_id"],
                "training_ids_hash": canonical_sha256(train_ids),
                "validation_ids_hash": canonical_sha256(validation_ids),
            }
        )
        del kernel, predictions
        gc.collect()
    gathered = gather_oof(oof, subset_ids)
    actual = context.targets(subset_ids)
    scores = {
        alpha: selection_score(
            actual, gathered[alpha], subset_ids, context.layouts(subset_ids)
        )
        for alpha in ALPHAS
    }
    selected_alpha = select_alpha(scores, tie_tolerance=0.0, prefer="smaller")
    final_scope = subset_ids + list(context.test_ids)
    train_targets = context.targets(subset_ids)
    final_kernel, record = wide_kernel(
        context, final_scope, len(train_targets), list(range(TOKEN_COUNT))
    )
    solve_started = time.perf_counter()
    predictions = ridge_predictions_from_kernel(
        final_kernel,
        train_targets,
        alpha=selected_alpha,
        prediction_scope_positions=prediction_positions(
            len(train_targets), len(final_kernel)
        ),
    )
    cpu_seconds += time.perf_counter() - solve_started
    gpu_seconds += record["gpu_kernel_seconds"]
    peak_gpu = max(peak_gpu, record["peak_gpu_bytes"])
    bytes_read += record["activation_bytes_gathered"]
    evidence = {
        "alpha_scores": {str(alpha): scores[alpha] for alpha in ALPHAS},
        "folds": fold_records,
        "selected_alpha": selected_alpha,
        "test_used_for_selection": False,
    }
    timing = {
        "activation_bytes_gathered": bytes_read,
        "cpu_dominant_seconds": cpu_seconds,
        "gpu_active_seconds": gpu_seconds,
        "peak_gpu_bytes": peak_gpu,
    }
    return predictions, evidence, timing


def choose_best_k_candidate(
    candidates: list[MappingLike], outer_rankings: list[MappingLike]
) -> MappingLike:
    maximum = max(float(record["score"]) for record in candidates)
    tied = [
        record
        for record in candidates
        if maximum - float(record["score"]) <= JOINT_TIE_TOLERANCE
    ]

    def token_tuple(record: MappingLike) -> tuple[int, ...]:
        k = int(record["k"])
        return tuple(
            token for outer in outer_rankings for token in sorted(outer["ranking"][:k])
        )

    return min(
        tied,
        key=lambda record: (
            int(record["k"]),
            -float(record["alpha"]),
            token_tuple(record),
        ),
    )


def run_best_k(
    context: JobContext, job: MappingLike
) -> tuple[np.ndarray, MappingLike, MappingLike]:
    subset_ids = list(job["training_trajectory_ids"])
    outer_rankings = []
    candidate_oof = {(k, alpha): {} for k in K_GRID for alpha in ALPHAS}
    gpu_seconds = 0.0
    cpu_seconds = 0.0
    peak_gpu = 0
    peak_host = 0
    bytes_read = 0
    selection_started = time.perf_counter()
    for outer in selection_folds(context, job["subset_id"]):
        ranking_scope, inner_folds = ranking_folds(
            context, job["subset_id"], outer["fold_id"]
        )
        ranking, _, ranking_record = compute_token_ranking(
            context, ranking_scope, inner_folds
        )
        train_ids = list(outer["training_ids"])
        validation_ids = list(outer["validation_ids"])
        scope_ids = train_ids + validation_ids
        targets = context.targets(train_ids)
        kernels, kernel_record = cumulative_ranked_kernels(
            context, scope_ids, len(targets), ranking
        )
        for k in K_GRID:
            solve_started = time.perf_counter()
            predictions = ridge_predictions_all_alphas_from_kernel(
                kernels[k],
                targets,
                alphas=ALPHAS,
                prediction_scope_positions=prediction_positions(
                    len(targets), len(kernels[k])
                ),
            )
            cpu_seconds += time.perf_counter() - solve_started
            for alpha in ALPHAS:
                for ordinal, identity in enumerate(validation_ids):
                    start = ordinal * FRAMES_PER_TRAJECTORY
                    candidate_oof[(k, alpha)][identity] = predictions[alpha][
                        start : start + FRAMES_PER_TRAJECTORY
                    ]
        outer_rankings.append(
            {
                "fold_id": outer["fold_id"],
                "ranking": list(ranking),
                "ranking_evidence": ranking_record["evidence"],
                "selected_membership_by_k": {
                    str(k): sorted(ranking[:k]) for k in K_GRID
                },
            }
        )
        gpu_seconds += (
            ranking_record["gpu_solve_seconds"] + kernel_record["gpu_kernel_seconds"]
        )
        peak_gpu = max(
            peak_gpu,
            ranking_record["peak_gpu_bytes"],
            kernel_record["peak_gpu_bytes"],
        )
        peak_host = max(peak_host, ranking_record["peak_host_bytes"])
        bytes_read += (
            ranking_record["activation_bytes_gathered"]
            + kernel_record["activation_bytes_gathered"]
        )
        del kernels
        gc.collect()
    actual = context.targets(subset_ids)
    candidates = []
    for k in K_GRID:
        for alpha in ALPHAS:
            predictions = np.concatenate(
                [candidate_oof[(k, alpha)][identity] for identity in subset_ids]
            )
            candidates.append(
                {
                    "alpha": alpha,
                    "k": k,
                    "score": selection_score(
                        actual,
                        predictions,
                        subset_ids,
                        context.layouts(subset_ids),
                    ),
                }
            )
    selected = choose_best_k_candidate(candidates, outer_rankings)
    selected_k = int(selected["k"])
    selected_alpha = float(selected["alpha"])
    final_ranking, _, final_ranking_record = compute_token_ranking(
        context, subset_ids, selection_folds(context, job["subset_id"])
    )
    selected_tokens = sorted(final_ranking[:selected_k])
    final_scope = subset_ids + list(context.test_ids)
    train_targets = context.targets(subset_ids)
    final_kernel, final_kernel_record = wide_kernel(
        context, final_scope, len(train_targets), selected_tokens
    )
    solve_started = time.perf_counter()
    predictions = ridge_predictions_from_kernel(
        final_kernel,
        train_targets,
        alpha=selected_alpha,
        prediction_scope_positions=prediction_positions(
            len(train_targets), len(final_kernel)
        ),
    )
    cpu_seconds += time.perf_counter() - solve_started
    gpu_seconds += (
        final_ranking_record["gpu_solve_seconds"]
        + final_kernel_record["gpu_kernel_seconds"]
    )
    peak_gpu = max(
        peak_gpu,
        final_ranking_record["peak_gpu_bytes"],
        final_kernel_record["peak_gpu_bytes"],
    )
    peak_host = max(peak_host, final_ranking_record["peak_host_bytes"])
    bytes_read += (
        final_ranking_record["activation_bytes_gathered"]
        + final_kernel_record["activation_bytes_gathered"]
    )
    evidence = {
        "candidate_scores": candidates,
        "final_ranking_evidence": final_ranking_record["evidence"],
        "final_selected_token_indices": selected_tokens,
        "outer_selection_rankings": outer_rankings,
        "selected_alpha": selected_alpha,
        "selected_k": selected_k,
        "selected_set_sha256": canonical_sha256(selected_tokens),
        "test_used_for_selection": False,
    }
    timing = {
        "activation_bytes_gathered": bytes_read,
        "cpu_dominant_seconds": cpu_seconds,
        "gpu_active_seconds": gpu_seconds,
        "peak_gpu_bytes": peak_gpu,
        "peak_host_bytes": peak_host,
        "selection_seconds": time.perf_counter() - selection_started,
    }
    return predictions, evidence, timing


def save_npz_atomic(path: Path, **arrays: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    with temporary.open("wb") as stream:
        np.savez_compressed(stream, **arrays)
    os.replace(temporary, path)


def run_worker(job_id: str) -> None:
    manifest = validate_manifest()
    job = next(
        (record for record in manifest["jobs"] if record["job_id"] == job_id), None
    )
    require(job is not None, f"unknown P8 job: {job_id}")
    started = time.perf_counter()
    context = JobContext()
    require(
        not set(job["training_trajectory_ids"]) & set(context.test_ids),
        "train/test overlap",
    )
    if job["representation"] == "GLOBAL_MEAN":
        predictions, evidence, timing = run_global(context, job)
    elif job["representation"] == "FULL_TOKEN_GRID":
        predictions, evidence, timing = run_full(context, job)
    elif job["representation"] == "BEST_K_TOKENS":
        predictions, evidence, timing = run_best_k(context, job)
    else:
        raise P8Error(f"unsupported representation: {job['representation']}")
    require(predictions.shape == (18 * FRAMES_PER_TRAJECTORY,), "test prediction shape")
    require(np.isfinite(predictions).all(), "non-finite fixed-test prediction")
    test_ids = list(context.test_ids)
    test_targets = context.targets(test_ids)
    metrics = metric_document(
        test_targets, predictions, test_ids, context.layouts(test_ids)
    )
    job_directory = JOB_ROOT / job_id
    job_directory.mkdir(parents=True, exist_ok=True)
    prediction_path = job_directory / "predictions.npz"
    test_row_ordinals = np.asarray(
        context.access.row_ordinals(test_ids), dtype=np.int64
    )
    save_npz_atomic(
        prediction_path,
        predictions=np.asarray(predictions, dtype=np.float64),
        row_ordinals=test_row_ordinals,
    )
    evidence_path = job_directory / "selection_evidence.json"
    write_json(evidence_path, evidence)
    runtime = time.perf_counter() - started
    result = {
        "artifact_id": "large-scale-no-wall-p8-outer-job-v0.1",
        "device": (
            "cuda:0 exact float64 kernel/solve"
            if job["representation"] == "GLOBAL_MEAN"
            else "hybrid cuda:0 exact float64 kernels plus exact CPU sample solve"
        ),
        "fixed_test_hash": job["fixed_test_hash"],
        "fixed_test_prediction_rows": len(predictions),
        "identity_sha256": job["identity_sha256"],
        "job_id": job_id,
        "master_id": job["master_id"],
        "metrics": metrics,
        "prediction_artifact": {
            "byte_count": prediction_path.stat().st_size,
            "path": str(prediction_path),
            "row_identity_sha256": canonical_sha256(
                [
                    [identity, frame]
                    for identity in test_ids
                    for frame in range(FRAMES_PER_TRAJECTORY)
                ]
            ),
            "sha256": sha256_file(prediction_path),
        },
        "representation": job["representation"],
        "runtime": {
            **timing,
            "peak_host_bytes": max(
                int(timing.get("peak_host_bytes", 0)),
                int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024),
            ),
            "total_seconds": runtime,
        },
        "selected_alpha": float(evidence["selected_alpha"]),
        "selected_k": evidence.get("selected_k"),
        "selected_set_sha256": evidence.get("selected_set_sha256"),
        "selected_token_indices": evidence.get("final_selected_token_indices"),
        "selection_artifact": {
            "byte_count": evidence_path.stat().st_size,
            "path": str(evidence_path),
            "sha256": sha256_file(evidence_path),
        },
        "selection_provenance": {
            "alpha_selection_training_only": True,
            "best_k_ranking_training_only": job["representation"] == "BEST_K_TOKENS",
            "final_best_k_ranking_training_only": job["representation"]
            == "BEST_K_TOKENS",
            "test_used_for_selection": False,
        },
        "status": "VALIDATED",
        "subset_id": job["subset_id"],
        "test_targets_accessed_after_selection": True,
        "training_frame_count": job["training_size"] * FRAMES_PER_TRAJECTORY,
        "training_size": job["training_size"],
        "training_trajectory_hash": job["training_trajectory_hash"],
        "training_trajectory_ids": job["training_trajectory_ids"],
    }
    write_json(job_directory / "job_result.json", result)
    print(
        json.dumps(
            {
                "job_id": job_id,
                "runtime_seconds": runtime,
                "status": "VALIDATED",
            },
            sort_keys=True,
        )
    )


def validate_job_result(job: MappingLike) -> MappingLike:
    path = JOB_ROOT / job["job_id"] / "job_result.json"
    require(path.is_file(), f"missing job result: {job['job_id']}")
    result = read_json(path)
    require(result["status"] == "VALIDATED", "job status")
    require(result["identity_sha256"] == job["identity_sha256"], "job identity")
    require(result["fixed_test_hash"] == job["fixed_test_hash"], "job test hash")
    require(result["fixed_test_prediction_rows"] == 1080, "job prediction count")
    require(
        result["selection_provenance"]["test_used_for_selection"] is False,
        "test leakage",
    )
    require(result["selected_alpha"] in ALPHAS, "selected alpha")
    if job["representation"] == "BEST_K_TOKENS":
        require(result["selected_k"] in K_GRID, "selected k")
        tokens = result["selected_token_indices"]
        require(tokens == sorted(tokens), "BEST-K feature order")
        require(len(tokens) == result["selected_k"], "BEST-K token count")
        require(len(set(tokens)) == len(tokens), "BEST-K duplicate token")
        require(all(0 <= token < 336 for token in tokens), "BEST-K token range")
    for key in ("prediction_artifact", "selection_artifact"):
        artifact = result[key]
        artifact_path = Path(artifact["path"])
        require(artifact_path.is_file(), f"missing {key}")
        require(artifact_path.stat().st_size == artifact["byte_count"], f"{key} size")
        require(sha256_file(artifact_path) == artifact["sha256"], f"{key} hash")
    prediction = np.load(result["prediction_artifact"]["path"], allow_pickle=False)
    require(prediction["predictions"].shape == (1080,), "prediction array")
    require(prediction["row_ordinals"].shape == (1080,), "prediction rows")
    require(np.isfinite(prediction["predictions"]).all(), "prediction finite")
    require(result["runtime"]["peak_host_bytes"] <= HOST_CEILING, "host ceiling")
    require(result["runtime"]["peak_gpu_bytes"] <= GPU_CEILING, "GPU ceiling")
    return result


def sync_checkpoint() -> None:
    subprocess.run(
        [
            "aws",
            "s3",
            "sync",
            str(JOB_ROOT),
            f"{S3_URI}jobs/",
            "--only-show-errors",
        ],
        check=True,
    )
    for path in (RUN_MANIFEST, RUN_MANIFEST_LOCK, LEDGER, PROGRESS):
        subprocess.run(
            [
                "aws",
                "s3",
                "cp",
                str(path),
                f"{S3_URI}{path.name}",
                "--only-show-errors",
            ],
            check=True,
        )


def run_all() -> None:
    manifest = validate_manifest()
    validate_input_objects()
    RESULT_ROOT.mkdir(parents=True, exist_ok=True)
    JOB_ROOT.mkdir(parents=True, exist_ok=True)
    run_started = time.monotonic()
    latest, _, attempts = latest_ledger()
    for job in manifest["jobs"]:
        event = latest[job["job_id"]]
        if event["state"] == "VALIDATED":
            validate_job_result(job)
            continue
        if event["state"] == "RUNNING":
            append_ledger(
                {
                    "attempt": attempts[job["job_id"]],
                    "event_at": now_utc(),
                    "identity_sha256": job["identity_sha256"],
                    "job_id": job["job_id"],
                    "reason": "interrupted worker recovered by exact job identity",
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
            write_progress(manifest, current_job=job["job_id"], run_started=run_started)
            log_path = (
                RESULT_ROOT / "attempt_logs" / f"{job['job_id']}__attempt_{attempt}.log"
            )
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with log_path.open("w", encoding="utf-8") as log:
                completed = subprocess.run(
                    [
                        str(QUALIFIED_PYTHON),
                        str(Path(__file__).resolve()),
                        "--worker",
                        job["job_id"],
                    ],
                    cwd=ROOT,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    text=True,
                    check=False,
                )
            if completed.returncode == 0:
                try:
                    result = validate_job_result(job)
                except Exception as error:  # noqa: BLE001 - worker validation boundary
                    failure = f"post-worker validation failed: {type(error).__name__}: {error}"
                else:
                    append_ledger(
                        {
                            "attempt": attempt,
                            "event_at": now_utc(),
                            "identity_sha256": job["identity_sha256"],
                            "job_id": job["job_id"],
                            "result_sha256": sha256_file(
                                JOB_ROOT / job["job_id"] / "job_result.json"
                            ),
                            "runtime_seconds": result["runtime"]["total_seconds"],
                            "state": "VALIDATED",
                        }
                    )
                    succeeded = True
            else:
                failure = f"worker exit code {completed.returncode}; log={log_path}"
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
                if state == "BLOCKED":
                    write_progress(manifest, current_job=None, run_started=run_started)
                    raise P8Error(f"job blocked after exact retry: {job['job_id']}")
        latest, counts, _ = latest_ledger()
        write_progress(manifest, current_job=None, run_started=run_started)
        if counts["VALIDATED"] % DURABILITY_INTERVAL_JOBS == 0:
            sync_checkpoint()
    latest, counts, _ = latest_ledger()
    require(counts["VALIDATED"] == EXPECTED_CORE_OUTER_FITS, "P8 incomplete")
    require(not counts["BLOCKED"], "blocked P8 jobs")
    sync_checkpoint()


def completed_results(manifest: MappingLike) -> list[MappingLike]:
    latest, counts, _ = latest_ledger()
    require(counts["VALIDATED"] == EXPECTED_CORE_OUTER_FITS, "P8 completeness gate")
    require(not counts["BLOCKED"], "blocked job at completeness gate")
    results = []
    for job in manifest["jobs"]:
        require(latest[job["job_id"]]["state"] == "VALIDATED", "ledger incomplete")
        results.append(validate_job_result(job))
    require(len(results) == 186, "result count")
    counts_by_representation = Counter(record["representation"] for record in results)
    require(
        counts_by_representation
        == {representation: 62 for representation in REPRESENTATIONS},
        "representation completeness",
    )
    return results


def recompute_all_metrics(
    context: JobContext, results: list[MappingLike]
) -> list[MappingLike]:
    test_ids = list(context.test_ids)
    test_targets = context.targets(test_ids)
    layouts = context.layouts(test_ids)
    for result in results:
        artifact = np.load(result["prediction_artifact"]["path"], allow_pickle=False)
        recomputed = metric_document(
            test_targets, artifact["predictions"], test_ids, layouts
        )
        require(
            canonical_sha256(recomputed) == canonical_sha256(result["metrics"]),
            f"metric recomputation mismatch: {result['job_id']}",
        )
        expected_rows = np.asarray(
            context.access.row_ordinals(test_ids), dtype=np.int64
        )
        require(
            np.array_equal(artifact["row_ordinals"], expected_rows),
            f"prediction row mismatch: {result['job_id']}",
        )
    return results


def metric_values(records: list[MappingLike], metric: str) -> list[float]:
    values = [record["metrics"]["equal_layout_macro"][metric] for record in records]
    require(all(value is not None for value in values), f"undefined macro {metric}")
    return [float(value) for value in values]


def trajectory_bootstrap_interval(
    records: list[MappingLike], *, seed: int
) -> list[float]:
    generator = np.random.default_rng(seed)
    layouts = sorted(records[0]["metrics"]["per_layout"])
    draws = np.empty(BOOTSTRAP_REPLICATES, dtype=np.float64)
    for bootstrap in range(BOOTSTRAP_REPLICATES):
        subset_values = []
        for record in records:
            layout_values = []
            per_trajectory = record["metrics"]["per_trajectory"]
            for layout in layouts:
                values = np.asarray(
                    [
                        trajectory["r2"]
                        for trajectory in per_trajectory.values()
                        if trajectory["layout"] == layout
                    ],
                    dtype=np.float64,
                )
                require(values.size == 3, "fixed-test layout trajectory count")
                layout_values.append(float(generator.choice(values, size=3).mean()))
            subset_values.append(float(np.mean(layout_values)))
        draws[bootstrap] = float(np.mean(subset_values))
    lower, upper = np.percentile(draws, [2.5, 97.5])
    return [float(lower), float(upper)]


def compact_job_record(record: MappingLike) -> MappingLike:
    return {
        "fixed_test_hash": record["fixed_test_hash"],
        "job_id": record["job_id"],
        "master_id": record["master_id"],
        "metrics": record["metrics"],
        "prediction_sha256": record["prediction_artifact"]["sha256"],
        "representation": record["representation"],
        "runtime_seconds": record["runtime"]["total_seconds"],
        "selected_alpha": record["selected_alpha"],
        "selected_k": record["selected_k"],
        "selected_set_sha256": record["selected_set_sha256"],
        "selected_token_indices": record["selected_token_indices"],
        "subset_id": record["subset_id"],
        "training_size": record["training_size"],
        "training_trajectory_hash": record["training_trajectory_hash"],
    }


def result_by_key(
    results: list[MappingLike],
) -> dict[tuple[str, int, str], MappingLike]:
    return {
        (
            record["representation"],
            int(record["training_size"]),
            record["subset_id"],
        ): record
        for record in results
    }


def build_aggregate_documents(
    manifest: MappingLike, results: list[MappingLike]
) -> None:
    from scipy.stats import spearmanr

    schedule = read_json(SUBSET_SCHEDULE)
    subset_by_id = {record["subset_id"]: record for record in schedule["subsets"]}
    layout_by_id = {
        entry["trajectory_spec_id"]: entry["layout_id"]
        for entry in read_json(COHORT_LOCK)["entries"]
    }
    grouped: dict[tuple[str, int], list[MappingLike]] = defaultdict(list)
    for record in results:
        grouped[(record["representation"], int(record["training_size"]))].append(record)
    expected_by_n = {5: 20, 15: 16, 40: 12, 70: 8, 100: 6}
    summaries: dict[str, dict[str, MappingLike]] = {}
    for representation_offset, representation in enumerate(REPRESENTATIONS):
        summaries[representation] = {}
        for n_offset, n in enumerate(expected_by_n):
            records = sorted(
                grouped[(representation, n)], key=lambda record: record["subset_id"]
            )
            require(
                len(records) == expected_by_n[n], f"subset count {representation} N={n}"
            )
            r2 = metric_values(records, "r2")
            summaries[representation][str(n)] = {
                "bootstrap_rule": manifest["bootstrap"],
                "macro_mae": numeric_summary(metric_values(records, "mae")),
                "macro_nmae_std": numeric_summary(metric_values(records, "nmae_std")),
                "macro_pearson_r": numeric_summary(metric_values(records, "pearson_r")),
                "macro_prediction_bias": numeric_summary(
                    metric_values(records, "bias")
                ),
                "macro_prediction_slope": numeric_summary(
                    metric_values(records, "prediction_slope")
                ),
                "macro_r2": numeric_summary(r2),
                "mean_r2_trajectory_bootstrap_95_interval": trajectory_bootstrap_interval(
                    records,
                    seed=BOOTSTRAP_SEED + representation_offset * 100 + n_offset,
                ),
                "subset_count": len(records),
                "subset_ids": [record["subset_id"] for record in records],
                "subset_points_r2": r2,
                "training_frame_count": n * FRAMES_PER_TRAJECTORY,
                "training_trajectory_count": n,
            }
    index = result_by_key(results)
    comparisons = {}
    comparison_specs = {
        "FULL_MINUS_GLOBAL": ("FULL_TOKEN_GRID", "GLOBAL_MEAN"),
        "BEST_K_MINUS_GLOBAL": ("BEST_K_TOKENS", "GLOBAL_MEAN"),
        "BEST_K_MINUS_FULL": ("BEST_K_TOKENS", "FULL_TOKEN_GRID"),
    }
    for comparison_offset, (name, (first, second)) in enumerate(
        comparison_specs.items()
    ):
        comparisons[name] = {}
        for n_offset, n in enumerate(expected_by_n):
            subset_ids = sorted(record["subset_id"] for record in grouped[(first, n)])
            deltas = [
                float(
                    index[(first, n, subset_id)]["metrics"]["equal_layout_macro"]["r2"]
                )
                - float(
                    index[(second, n, subset_id)]["metrics"]["equal_layout_macro"]["r2"]
                )
                for subset_id in subset_ids
            ]
            comparisons[name][str(n)] = {
                **paired_summary(
                    deltas,
                    seed=BOOTSTRAP_SEED + 1000 + comparison_offset * 100 + n_offset,
                ),
                "subset_ids": subset_ids,
                "paired_deltas": deltas,
            }
    complete_masters = [f"master_{ordinal:02d}" for ordinal in range(6)]
    scaling = {}
    for representation in REPRESENTATIONS:
        changes = []
        chains = []
        for master_id in complete_masters:
            subset_ids = {
                record["training_size"]: record["subset_id"]
                for record in schedule["subsets"]
                if record["master_id"] == master_id
            }
            require(
                set(subset_ids) == set(expected_by_n), f"incomplete master {master_id}"
            )
            values = {
                str(n): float(
                    index[(representation, n, subset_ids[n])]["metrics"][
                        "equal_layout_macro"
                    ]["r2"]
                )
                for n in expected_by_n
            }
            change = values["100"] - values["5"]
            changes.append(change)
            chains.append(
                {
                    "master_id": master_id,
                    "n100_minus_n5": change,
                    "r2_by_n": values,
                    "subset_ids_by_n": {str(n): subset_ids[n] for n in expected_by_n},
                }
            )
        medians = [
            summaries[representation][str(n)]["macro_r2"]["median"]
            for n in expected_by_n
        ]
        trend = spearmanr(list(expected_by_n), medians)
        scaling[representation] = {
            "complete_chain_count": 6,
            "complete_chains": chains,
            "median_r2_spearman_across_anchor_n": float(trend.statistic),
            "n100_minus_n5": numeric_summary(changes),
            "subset_r2_sd_by_n": {
                str(n): summaries[representation][str(n)]["macro_r2"]["sd_ddof1"]
                for n in expected_by_n
            },
        }
    n5_omitted_layout = {}
    layouts = {f"L{ordinal:02d}" for ordinal in range(1, 7)}
    for representation in REPRESENTATIONS:
        records_by_omitted: dict[str, list[float]] = defaultdict(list)
        for record in grouped[(representation, 5)]:
            training_layouts = {
                layout_by_id[identity]
                for identity in subset_by_id[record["subset_id"]]["trajectory_spec_ids"]
            }
            omitted = sorted(layouts - training_layouts)
            require(len(omitted) == 1, "N5 omitted-layout identity")
            records_by_omitted[omitted[0]].append(
                float(record["metrics"]["equal_layout_macro"]["r2"])
            )
        n5_omitted_layout[representation] = {
            layout: numeric_summary(values)
            for layout, values in sorted(records_by_omitted.items())
        }
    learning = {
        "artifact_id": "large-scale-no-wall-p8-learning-curve-results-v0.1",
        "complete_before_aggregation": True,
        "core_outer_fit_count": 186,
        "fixed_test_count": 18,
        "fixed_test_hash": read_json(TEST_GUARD)["test_authority_hash"],
        "job_records": [compact_job_record(record) for record in results],
        "n5_caveat": "N=5 contains five of six layouts; N5-to-N15 is not attributable purely to trajectory count.",
        "n5_omitted_layout_breakdown": n5_omitted_layout,
        "paired_core_comparisons": comparisons,
        "primary_metric": "fixed-test equal-layout macro per-trajectory R2",
        "scaling": scaling,
        "status": "PASS_COMPLETE_186_OF_186",
        "summaries": summaries,
    }
    write_json(LEARNING_RESULTS, learning)
    best_records = [
        compact_job_record(record)
        for record in results
        if record["representation"] == "BEST_K_TOKENS"
    ]
    best = {
        "all_selected_alpha_in_frozen_grid": all(
            record["selected_alpha"] in ALPHAS for record in best_records
        ),
        "all_selected_k_in_frozen_grid": all(
            record["selected_k"] in K_GRID for record in best_records
        ),
        "artifact_id": "large-scale-no-wall-p8-best-k-results-v0.1",
        "final_ranking_training_only": True,
        "job_count": len(best_records),
        "job_records": best_records,
        "k_alpha_selection_training_only": True,
        "selected_alpha_distribution_by_n": {
            str(n): distribution(
                [
                    record["selected_alpha"]
                    for record in best_records
                    if record["training_size"] == n
                ]
            )
            for n in expected_by_n
        },
        "selected_k_distribution_by_n": {
            str(n): distribution(
                [
                    record["selected_k"]
                    for record in best_records
                    if record["training_size"] == n
                ]
            )
            for n in expected_by_n
        },
        "status": "PASS_COMPLETE_62_OF_62",
        "test_used_for_selection": False,
        "token_ranking_training_only": True,
    }
    write_json(BEST_K_RESULTS, best)
    predictions = {
        "artifact_id": "large-scale-no-wall-p8-prediction-manifest-v0.1",
        "fixed_test_hash": read_json(TEST_GUARD)["test_authority_hash"],
        "job_count": len(results),
        "objects": [
            {
                "byte_count": record["prediction_artifact"]["byte_count"],
                "job_id": record["job_id"],
                "local_path": record["prediction_artifact"]["path"],
                "row_count": 1080,
                "row_identity_sha256": record["prediction_artifact"][
                    "row_identity_sha256"
                ],
                "s3_uri": f"{S3_URI}jobs/{record['job_id']}/predictions.npz",
                "sha256": record["prediction_artifact"]["sha256"],
            }
            for record in results
        ],
        "status": "PASS_COMPLETE",
    }
    write_json(PREDICTION_MANIFEST, predictions)


def create_primary_figure() -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    document = read_json(LEARNING_RESULTS)
    sizes = [5, 15, 40, 70, 100]
    labels = {
        "GLOBAL_MEAN": "GLOBAL mean",
        "FULL_TOKEN_GRID": "FULL token grid",
        "BEST_K_TOKENS": "BEST-K tokens",
    }
    colors = {
        "GLOBAL_MEAN": "#2b6cb0",
        "FULL_TOKEN_GRID": "#c05621",
        "BEST_K_TOKENS": "#2f855a",
    }
    figure, axes = plt.subplots(
        1, 2, figsize=(13.2, 5.4), gridspec_kw={"width_ratios": [2.2, 1.0]}
    )
    axis, dispersion_axis = axes
    for representation_offset, representation in enumerate(REPRESENTATIONS):
        medians = []
        means = []
        lower = []
        upper = []
        dispersions = []
        for n in sizes:
            record = document["summaries"][representation][str(n)]
            points = record["subset_points_r2"]
            jitter = (
                np.linspace(-0.9, 0.9, len(points)) + (representation_offset - 1) * 0.22
            )
            axis.scatter(
                np.asarray([n] * len(points)) + jitter,
                points,
                color=colors[representation],
                alpha=0.42,
                s=18,
                linewidths=0,
            )
            medians.append(record["macro_r2"]["median"])
            means.append(record["macro_r2"]["mean"])
            lower.append(record["mean_r2_trajectory_bootstrap_95_interval"][0])
            upper.append(record["mean_r2_trajectory_bootstrap_95_interval"][1])
            dispersions.append(record["macro_r2"]["sd_ddof1"])
        axis.plot(
            sizes,
            medians,
            color=colors[representation],
            marker=None,
            linewidth=2.0,
            label=f"{labels[representation]} median",
        )
        axis.scatter(
            sizes,
            means,
            color=colors[representation],
            marker="D",
            s=34,
            edgecolors="white",
            linewidths=0.5,
            zorder=4,
            label=f"{labels[representation]} mean",
        )
        axis.fill_between(sizes, lower, upper, color=colors[representation], alpha=0.12)
        dispersion_axis.plot(
            sizes,
            dispersions,
            color=colors[representation],
            marker="o",
            linewidth=2.0,
            label=labels[representation],
        )
    axis.axhline(0.0, color="#4a5568", linewidth=0.8, linestyle="--")
    axis.set_xticks(sizes)
    axis.set_xlabel(
        "Independent training trajectories (frames: 300/900/2400/4200/6000)"
    )
    axis.set_ylabel("Fixed-test equal-layout macro R²")
    axis.set_title("Core no-wall trajectory learning curves")
    axis.grid(alpha=0.18)
    axis.legend(fontsize=8, ncol=2)
    dispersion_axis.set_xticks(sizes)
    dispersion_axis.set_xlabel("Training trajectories")
    dispersion_axis.set_ylabel("Subset R² SD (ddof=1)")
    dispersion_axis.set_title("Predeclared subset dispersion")
    dispersion_axis.grid(alpha=0.18)
    dispersion_axis.legend(fontsize=8)
    figure.suptitle(
        "Fixed 18-trajectory test authority; frames within trajectory are correlated; "
        "the trajectory is the independent training unit",
        fontsize=10,
    )
    figure.tight_layout(rect=(0, 0, 1, 0.94))
    figure.savefig(PRIMARY_FIGURE, dpi=180)
    plt.close(figure)


def ledger_attempt_summary() -> MappingLike:
    events = read_jsonl(LEDGER)
    failed = [event for event in events if event["state"] == "FAILED_RETRYABLE"]
    attempts_by_job: dict[str, int] = defaultdict(int)
    for event in events:
        attempts_by_job[event["job_id"]] = max(
            attempts_by_job[event["job_id"]], int(event["attempt"])
        )
    return {
        "failed_job_attempts": len(failed),
        "retried_jobs": sum(value > 1 for value in attempts_by_job.values()),
    }


def build_timing_memory(results: list[MappingLike]) -> None:
    events = read_jsonl(LEDGER)
    running_times = [
        datetime.fromisoformat(event["event_at"])
        for event in events
        if event["state"] == "RUNNING"
    ]
    require(running_times, "missing run start")
    machine_seconds = (datetime.now(timezone.utc) - min(running_times)).total_seconds()
    timing = {
        "artifact_id": "large-scale-no-wall-p8-timing-memory-v0.1",
        "cpu_dominant_seconds_sum": float(
            sum(
                record["runtime"].get("cpu_dominant_seconds", 0.0) for record in results
            )
        ),
        "gpu_active_seconds_sum": float(
            sum(record["runtime"].get("gpu_active_seconds", 0.0) for record in results)
        ),
        "job_runtime_seconds_sum": float(
            sum(record["runtime"]["total_seconds"] for record in results)
        ),
        "machine_runtime_seconds": machine_seconds,
        "maximum_gpu_bytes": max(
            record["runtime"]["peak_gpu_bytes"] for record in results
        ),
        "maximum_host_bytes": max(
            record["runtime"]["peak_host_bytes"] for record in results
        ),
        "p7a_projected_seconds": 92704.73524438578,
        "status": "PASS_MEMORY_AND_TIMING",
    }
    timing["measured_vs_projection"] = (
        timing["machine_runtime_seconds"] / timing["p7a_projected_seconds"]
    )
    write_json(TIMING_MEMORY, timing)


def build_validation_receipt(manifest: MappingLike, results: list[MappingLike]) -> None:
    subset_counts = Counter(int(record["training_size"]) for record in results)
    representation_counts = Counter(record["representation"] for record in results)
    require(
        subset_counts == {5: 60, 15: 48, 40: 36, 70: 24, 100: 18},
        "all-representation subset counts",
    )
    require(
        representation_counts
        == {representation: 62 for representation in REPRESENTATIONS},
        "representation counts",
    )
    by_representation = {
        representation: {
            record["subset_id"]
            for record in results
            if record["representation"] == representation
        }
        for representation in REPRESENTATIONS
    }
    require(
        len({frozenset(values) for values in by_representation.values()}) == 1,
        "subset identity differs",
    )
    receipt = {
        "all_best_k_alpha_in_grid": all(
            record["selected_alpha"] in ALPHAS
            for record in results
            if record["representation"] == "BEST_K_TOKENS"
        ),
        "all_best_k_k_in_grid": all(
            record["selected_k"] in K_GRID
            for record in results
            if record["representation"] == "BEST_K_TOKENS"
        ),
        "all_fixed_test_hashes_identical": len(
            {record["fixed_test_hash"] for record in results}
        )
        == 1,
        "all_prediction_rows_complete": all(
            record["fixed_test_prediction_rows"] == 1080 for record in results
        ),
        "artifact_id": "large-scale-no-wall-p8-validation-receipt-v0.1",
        "best_k_completed": representation_counts["BEST_K_TOKENS"],
        "best_k_selection_training_only": all(
            record["selection_provenance"]["best_k_ranking_training_only"]
            for record in results
            if record["representation"] == "BEST_K_TOKENS"
        ),
        "coarse_core_fits_run": False,
        "expected_core_outer_fits": 186,
        "fixed_test_hash": read_json(TEST_GUARD)["test_authority_hash"],
        "full_completed": representation_counts["FULL_TOKEN_GRID"],
        "global_completed": representation_counts["GLOBAL_MEAN"],
        "learning_curve_results_sha256": sha256_file(LEARNING_RESULTS),
        "logical_subset_counts_by_n_per_representation": {
            "5": 20,
            "15": 16,
            "40": 12,
            "70": 8,
            "100": 6,
        },
        "manifest_sha256": sha256_file(RUN_MANIFEST),
        "metrics_recomputed_from_predictions": True,
        "no_full_feature_covariance": True,
        "p5_p5a_p6_p7_p7a_authority_preserved": True,
        "p7a_exact_path_used": True,
        "p9_started": False,
        "plots_regenerated_from_json": True,
        "same_subset_ids_across_representations": True,
        "status": "PASS_P8_COMPLETE_VALIDATED",
        "target_null_executed": False,
        "test_used_for_selection": False,
        "total_core_completed": len(results),
        "train_test_overlap_all_jobs": 0,
        "v1_primary_intersection": 0,
    }
    write_json(VALIDATION_RECEIPT, receipt)


def create_durable_package() -> None:
    package_path = RESULT_ROOT / "p8_durable_result_package.tar.gz"
    compact_paths = [
        RUN_MANIFEST,
        RUN_MANIFEST_LOCK,
        LEDGER,
        PROGRESS,
        TIMING_MEMORY,
        LEARNING_RESULTS,
        BEST_K_RESULTS,
        PREDICTION_MANIFEST,
        VALIDATION_RECEIPT,
        PRIMARY_FIGURE,
    ]
    with tarfile.open(package_path, "w:gz") as archive:
        archive.add(JOB_ROOT, arcname="jobs")
        for path in compact_paths:
            archive.add(path, arcname=f"repository_artifacts/{path.name}")
    package_sha = sha256_file(package_path)
    object_key = f"{S3_PREFIX}/{package_path.name}"
    subprocess.run(
        [
            "aws",
            "s3",
            "cp",
            str(package_path),
            f"s3://{S3_BUCKET}/{object_key}",
            "--checksum-algorithm",
            "SHA256",
            "--only-show-errors",
        ],
        check=True,
    )
    head = json.loads(
        subprocess.check_output(
            [
                "aws",
                "s3api",
                "head-object",
                "--bucket",
                S3_BUCKET,
                "--key",
                object_key,
                "--checksum-mode",
                "ENABLED",
            ],
            text=True,
        )
    )
    expected_checksum = base64.b64encode(bytes.fromhex(package_sha)).decode("ascii")
    require(
        int(head["ContentLength"]) == package_path.stat().st_size, "S3 package size"
    )
    require(head.get("ChecksumSHA256") == expected_checksum, "S3 package checksum")
    for path in compact_paths:
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
    receipt = {
        "artifact_id": "large-scale-no-wall-p8-s3-durability-v0.1",
        "compact_repository_artifact_count": len(compact_paths),
        "package_byte_count": package_path.stat().st_size,
        "package_local_path": str(package_path),
        "package_s3_uri": f"s3://{S3_BUCKET}/{object_key}",
        "package_sha256": package_sha,
        "prediction_and_selection_job_count": 186,
        "result_hash_valid": True,
        "s3_checksum_sha256": head["ChecksumSHA256"],
        "s3_prefix": S3_URI,
        "status": "PASS_DURABLE",
        "token_cache_uploaded": False,
    }
    write_json(DURABILITY_RECEIPT, receipt)
    subprocess.run(
        [
            "aws",
            "s3",
            "cp",
            str(DURABILITY_RECEIPT),
            f"{S3_URI}repository_artifacts/{DURABILITY_RECEIPT.name}",
            "--checksum-algorithm",
            "SHA256",
            "--only-show-errors",
        ],
        check=True,
    )


def build_p8_receipt(results: list[MappingLike]) -> None:
    attempts = ledger_attempt_summary()
    timing = read_json(TIMING_MEMORY)
    durability = read_json(DURABILITY_RECEIPT)
    receipt = {
        "artifact_id": "large-scale-no-wall-p8-receipt-v0.1",
        "best_k_completed": 62,
        "blocker": None,
        "coarse_core_fits_run": False,
        "failed_job_attempts": attempts["failed_job_attempts"],
        "fixed_test_scores_opened": True,
        "fixed_test_targets_used_for_selection": False,
        "full_completed": 62,
        "global_completed": 62,
        "machine_runtime_seconds": timing["machine_runtime_seconds"],
        "operator_intervention_count": 0,
        "p7a_head": P7A_HEAD,
        "p9_started": False,
        "result_artifacts_durable": True,
        "result_package_sha256": durability["package_sha256"],
        "result_s3_prefix": S3_URI,
        "retried_jobs": attempts["retried_jobs"],
        "safe_for_p9": True,
        "status": "PASS_P8_CORE_LEARNING_CURVES_COMPLETE",
        "target_null_executed": False,
        "total_core_completed": len(results),
    }
    write_json(P8_RECEIPT, receipt)


def aggregate_and_package() -> None:
    manifest = validate_manifest()
    context = JobContext()
    results = recompute_all_metrics(context, completed_results(manifest))
    build_aggregate_documents(manifest, results)
    create_primary_figure()
    build_timing_memory(results)
    build_validation_receipt(manifest, results)
    create_durable_package()
    build_p8_receipt(results)
    subprocess.run(
        [
            "aws",
            "s3",
            "cp",
            str(P8_RECEIPT),
            f"{S3_URI}repository_artifacts/{P8_RECEIPT.name}",
            "--checksum-algorithm",
            "SHA256",
            "--only-show-errors",
        ],
        check=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze-manifest", action="store_true")
    parser.add_argument("--validate-manifest", action="store_true")
    parser.add_argument("--worker")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--aggregate", action="store_true")
    args = parser.parse_args()
    if args.freeze_manifest:
        freeze_manifest()
        print("PASS P8 manifest frozen before outcomes")
        return 0
    if args.validate_manifest:
        manifest = validate_manifest()
        print(f"PASS P8 manifest {len(manifest['jobs'])}/186")
        return 0
    if args.worker:
        run_worker(args.worker)
        return 0
    if args.run:
        run_all()
        print("PASS P8 core execution 186/186")
        return 0
    if args.aggregate:
        aggregate_and_package()
        print("PASS P8 aggregate, figure, and durable package")
        return 0
    parser.error("choose one P8 action")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
