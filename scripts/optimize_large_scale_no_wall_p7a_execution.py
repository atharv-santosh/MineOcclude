#!/usr/bin/env python3
"""Run one bounded exact P7A execution-plan optimization before P8."""

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
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import numpy as np

from mineocclude.probes.p7_ridge import standardized_kernel_numpy
from mineocclude.probes.p7a_execution import (
    batched_ridge_predictions_all_alphas_from_features,
    batched_ridge_predictions_all_alphas_from_features_cuda,
    standardized_token_kernel_sum_cuda,
)
from scripts.build_large_scale_no_wall_p7_authority import (
    ACTIVATION_ROOT,
    ALPHAS,
    CACHE_ROOT,
    CANONICAL_ROWS,
    COHORT_LOCK,
    EQUIVALENCE_ATOL,
    EQUIVALENCE_RTOL,
    GROUPED_FOLDS,
    HIDDEN_WIDTH,
    P6_MANIFEST,
    SPLIT_AUTHORITY,
    STUDY_ROOT,
    SUBSET_SCHEDULE,
    TEST_GUARD,
    TOKEN_COUNT,
    ActivationAccess,
    canonical_sha256,
    read_json,
    read_jsonl,
    sha256_file,
    subset_fold_ids,
    training_targets,
    validate_logical_budgets,
    validate_nested_grouping,
)

RUNNER_VERSION = "large-scale-no-wall-p7a-exact-execution-optimization-v0.1"
P7_HEAD = "00b5ee06e4fbb6c9b1868d46ed3551c152ff8e53"
BRANCH = "exploration/large-scale-no-wall-scaling-best-k-v0-1"
OLD_EXPECTED_SECONDS = 161366.48
HOST_CEILING = 14 * (1 << 30)
GPU_CEILING = 20 * (1 << 30)
BASELINE_BATCH = 4
BASELINE_PARALLELISM = 1
ADOPTION_THRESHOLD = 0.20
P7_REPRESENTATION = STUDY_ROOT / "representation_authority.json"
P7_BENCHMARK = STUDY_ROOT / "solver_benchmark.json"
P7_EXECUTION = STUDY_ROOT / "execution_budget.lock.json"
P7_CACHE = STUDY_ROOT / "cache_manifest.json"
P7_RECEIPT = STUDY_ROOT / "p7_receipt.json"
P7A_BENCHMARK = STUDY_ROOT / "solver_benchmark.p7a.json"
P7A_EXECUTION = STUDY_ROOT / "execution_budget.p7a.lock.json"
P7A_CACHE = STUDY_ROOT / "cache_manifest.p7a.json"
P7A_AUDIT = STUDY_ROOT / "p7a_execution_optimization.json"
TRAINING_TOKEN_CACHE = CACHE_ROOT / "training_tokens.token_major.f16.npy"
TRAINING_TOKEN_CACHE_METADATA = CACHE_ROOT / "training_tokens.token_major.metadata.json"

PROTECTED_SHA256 = {
    P6_MANIFEST: "a57be180a9054336dbe36d2ddaddbec2859e21d5b6a42dae5b25b1c276e2d5bb",
    SPLIT_AUTHORITY: "b39c81454ea18125c373fb3c777ac4c1668882c9c1ad188a7d0f20e0cab43de5",
    SUBSET_SCHEDULE: "0d6f5e8394328915164bafea70468e6d26342a2eda9a1923e4d4ad745f494a48",
    GROUPED_FOLDS: "597bc7b401ca691897b843fc83120cc997a414b7a946819da4c3e99768e7728e",
    TEST_GUARD: "0adc85a5d90eb92361ba0775d58a6ccc2eb674a8ae5ffd2e816b89d9d9b48ac5",
    P7_REPRESENTATION: "757217b2b3e54e236b4ad7b9b3574d7391f896558760a54bb1b5e457b186259e",
    P7_BENCHMARK: "1b925d1ca3fa95e78fb94cd3618430e3cd55a15b1398ae64c19672bebebafaaf",
    P7_EXECUTION: "ec9cf3c384fa3aec15029b55d6f649c9cb5ce8cf018f2a3245f49090607aeab2",
    P7_CACHE: "0aff9b16a9e37cb004ea9bdde8725e05f59205050545176cdf5463a437aad89d",
    P7_RECEIPT: "501b3ba391f94dc0ab739d66d3321e9b0f98459609e1e1655f9c77bb1d334c29",
}


class P7AError(RuntimeError):
    """Raised when optimization would violate frozen P7 authority."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise P7AError(message)


def git(*arguments: str) -> str:
    return subprocess.check_output(["git", *arguments], cwd=ROOT, text=True).strip()


def write_json(path: Path, value: Any) -> None:
    payload = json.dumps(value, indent=2, sort_keys=True) + "\n"
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    temporary.write_text(payload, encoding="utf-8")
    os.replace(temporary, path)


def build_training_token_cache() -> dict[str, Any]:
    """Build one reconstructable token-major cache for the 102 training trajectories."""

    rows = read_jsonl(CANONICAL_ROWS)
    training_rows = [row for row in rows if row["membership"] == "training_pool"]
    require(len(training_rows) == 6120, "training cache row authority mismatch")
    row_hash = canonical_sha256([row["scientific_row_key"] for row in training_rows])
    source_identity = canonical_sha256(
        {
            "p6_manifest_sha256": sha256_file(P6_MANIFEST),
            "row_hash": row_hash,
            "recipe": "training-only [row,token,hidden] -> [token,row,hidden] float16",
        }
    )
    if TRAINING_TOKEN_CACHE.is_file() and TRAINING_TOKEN_CACHE_METADATA.is_file():
        metadata = read_json(TRAINING_TOKEN_CACHE_METADATA)
        array = np.load(TRAINING_TOKEN_CACHE, mmap_mode="r", allow_pickle=False)
        if (
            metadata.get("source_identity_sha256") == source_identity
            and list(array.shape) == [TOKEN_COUNT, 6120, HIDDEN_WIDTH]
            and array.dtype == np.float16
            and metadata.get("byte_count") == TRAINING_TOKEN_CACHE.stat().st_size
            and metadata.get("sha256") == sha256_file(TRAINING_TOKEN_CACHE)
        ):
            return {**metadata, "cache_reused": True}

    CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    cache = np.lib.format.open_memmap(
        TRAINING_TOKEN_CACHE,
        mode="w+",
        dtype=np.float16,
        shape=(TOKEN_COUNT, 6120, HIDDEN_WIDTH),
    )
    started = time.perf_counter()
    offset = 0
    by_trajectory: dict[str, list[dict[str, Any]]] = {}
    for row in training_rows:
        by_trajectory.setdefault(str(row["trajectory_spec_id"]), []).append(row)
    for identity, trajectory_rows in by_trajectory.items():
        require(len(trajectory_rows) == 60, f"{identity}: cache row count")
        source = np.load(
            ACTIVATION_ROOT / str(trajectory_rows[0]["p6_activation_shard"]),
            mmap_mode="r",
            allow_pickle=False,
        )
        cache[:, offset : offset + 60, :] = np.asarray(source).transpose(1, 0, 2)
        offset += 60
    require(offset == 6120, "training token cache incomplete")
    cache.flush()
    del cache
    metadata = {
        "build_seconds": time.perf_counter() - started,
        "byte_count": TRAINING_TOKEN_CACHE.stat().st_size,
        "cache_reused": False,
        "dtype": "float16",
        "path": str(TRAINING_TOKEN_CACHE),
        "recipe": "training-only [row,token,hidden] -> [token,row,hidden] float16",
        "row_authority_hash": row_hash,
        "sha256": sha256_file(TRAINING_TOKEN_CACHE),
        "shape": [TOKEN_COUNT, 6120, HIDDEN_WIDTH],
        "source_identity_sha256": source_identity,
    }
    write_json(TRAINING_TOKEN_CACHE_METADATA, metadata)
    return metadata


def verify_authority() -> dict[str, Any]:
    require(git("branch", "--show-current") == BRANCH, "wrong branch")
    subprocess.run(
        ["git", "merge-base", "--is-ancestor", P7_HEAD, "HEAD"],
        cwd=ROOT,
        check=True,
    )
    for path, expected in PROTECTED_SHA256.items():
        require(sha256_file(path) == expected, f"protected authority changed: {path}")
    receipt = read_json(P7_RECEIPT)
    require(receipt["status"] == "PASS_P7_REPRESENTATION_SOLVER_AUTHORITY", "P7 status")
    require(
        receipt["safe_for_p8"] is True and receipt["p8_started"] is False, "P7 guard"
    )
    authority = {
        "folds": read_json(GROUPED_FOLDS),
        "guard": read_json(TEST_GUARD),
        "manifest": read_json(P6_MANIFEST),
        "schedule": read_json(SUBSET_SCHEDULE),
        "split": read_json(SPLIT_AUTHORITY),
    }
    require(validate_nested_grouping(authority)["status"] == "PASS", "nested grouping")
    require(validate_logical_budgets(authority)["status"] == "PASS", "logical budgets")
    return authority


def prediction_digest(
    predictions: tuple[dict[float, np.ndarray], ...], count: int
) -> str:
    digest = hashlib.sha256()
    for record in predictions[:count]:
        for alpha in ALPHAS:
            digest.update(
                np.asarray(record[alpha], dtype=np.float64).tobytes(order="C")
            )
    return digest.hexdigest()


def maximum_prediction_difference(
    first: tuple[dict[float, np.ndarray], ...],
    second: tuple[dict[float, np.ndarray], ...],
    count: int,
) -> float:
    return max(
        float(np.max(np.abs(first[token][alpha] - second[token][alpha])))
        for token in range(count)
        for alpha in ALPHAS
    )


def ranking_orders(
    predictions: tuple[dict[float, np.ndarray], ...],
    validation_targets: np.ndarray,
) -> dict[float, tuple[int, ...]]:
    """Compare token order without retaining any training-only score values."""

    require(
        validation_targets.size % 60 == 0,
        "ranking validation targets must contain whole trajectories",
    )
    trajectory_count = validation_targets.size // 60
    result = {}
    for alpha in ALPHAS:
        statistics = []
        for token_index, record in enumerate(predictions):
            scores = []
            values = record[alpha]
            for trajectory in range(trajectory_count):
                start = trajectory * 60
                stop = start + 60
                actual = validation_targets[start:stop]
                residual = float(np.sum((actual - values[start:stop]) ** 2))
                total = float(np.sum((actual - actual.mean()) ** 2))
                scores.append(1.0 - residual / total)
            statistics.append(
                (float(np.median(scores)), float(np.mean(scores)), token_index)
            )
        result[alpha] = tuple(
            item[2]
            for item in sorted(
                statistics, key=lambda item: (-item[0], -item[1], item[2])
            )
        )
    return result


def benchmark_candidate(
    cache: np.ndarray,
    scope_positions: list[int],
    targets: np.ndarray,
    *,
    batch_size: int,
    parallelism: int,
    baseline_predictions: tuple[dict[float, np.ndarray], ...] | None,
) -> tuple[dict[str, Any], tuple[dict[float, np.ndarray], ...]]:
    train_count = len(targets)
    gather_started = time.perf_counter()
    gathered = np.asarray(
        cache[:batch_size, scope_positions, :], dtype=np.float16, order="C"
    ).transpose(1, 0, 2)
    gathered = np.ascontiguousarray(gathered)
    gather_seconds = time.perf_counter() - gather_started
    solve = batched_ridge_predictions_all_alphas_from_features(
        gathered,
        targets,
        training_row_count=train_count,
        alphas=ALPHAS,
        parallelism=parallelism,
    )
    summed = standardized_token_kernel_sum_cuda(
        gathered, training_row_count=train_count
    )

    small_scope = gathered[:300]
    small_train_count = 240
    small_sum = standardized_token_kernel_sum_cuda(
        small_scope, training_row_count=small_train_count
    )
    reference = np.zeros_like(small_sum.kernel)
    for token_offset in range(batch_size):
        reference += standardized_kernel_numpy(
            small_scope[:small_train_count, token_offset, :],
            small_scope[:, token_offset, :],
        ).kernel
    kernel_difference = float(np.max(np.abs(reference - small_sum.kernel)))
    require(
        np.allclose(
            reference,
            small_sum.kernel,
            atol=EQUIVALENCE_ATOL,
            rtol=EQUIVALENCE_RTOL,
        ),
        f"batch {batch_size}: summed kernel changed",
    )
    prediction_difference = (
        0.0
        if baseline_predictions is None
        else maximum_prediction_difference(
            baseline_predictions, solve.predictions_by_token, min(4, batch_size)
        )
    )
    require(
        prediction_difference <= EQUIVALENCE_ATOL, "batched CPU predictions changed"
    )
    peak_host = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024)
    result = {
        "batch_size": batch_size,
        "cpu_parallelism": parallelism,
        "gather_seconds": gather_seconds,
        "gathered_byte_count": int(gathered.nbytes),
        "host_peak_bytes": peak_host,
        "prediction_digest_first_four_tokens": prediction_digest(
            solve.predictions_by_token, min(4, batch_size)
        ),
        "prediction_max_abs_difference_vs_baseline": prediction_difference,
        "small_extracted_kernel_max_abs_difference": kernel_difference,
        "solve_seconds": solve.timings["total_seconds"],
        "solve_seconds_per_token": solve.timings["seconds_per_token"],
        "solve_spaces": sorted(set(solve.solve_spaces)),
        "system_dimensions": sorted(set(solve.system_dimensions)),
        "summed_kernel_gpu_peak_bytes": summed.peak_device_memory_bytes,
        "summed_kernel_seconds": summed.timings["total_seconds"],
        "summed_kernel_seconds_per_token": (
            summed.timings["total_seconds"] / batch_size
        ),
        "summed_kernel_timing": dict(summed.timings),
        "total_representative_seconds": (
            gather_seconds
            + solve.timings["total_seconds"]
            + summed.timings["total_seconds"]
        ),
    }
    del gathered, summed, small_scope, small_sum, reference
    gc.collect()
    return result, solve.predictions_by_token


def worker(subset_id: str, selected_only: tuple[int, int] | None) -> dict[str, Any]:
    authority = verify_authority()
    access = ActivationAccess(read_jsonl(CANONICAL_ROWS))
    training_ids, _, scope_ids = subset_fold_ids(authority, subset_id)
    fixed = set(authority["guard"]["test_trajectory_ids"])
    require(not set(scope_ids) & fixed, "worker scope intersects fixed test")
    scope_rows = access.row_ordinals(scope_ids)
    cohort = read_json(COHORT_LOCK)
    targets = training_targets(cohort, training_ids)
    scope_targets = training_targets(cohort, scope_ids)
    validation_targets = scope_targets[len(targets) :]
    require(len(targets) == len(access.row_ordinals(training_ids)), "target alignment")

    all_rows = read_jsonl(CANONICAL_ROWS)
    training_ordinals = [
        int(row["row_ordinal"])
        for row in all_rows
        if row["membership"] == "training_pool"
    ]
    cache_position = {
        row_ordinal: position for position, row_ordinal in enumerate(training_ordinals)
    }
    require(all(row in cache_position for row in scope_rows), "cache scope mismatch")
    scope_positions = [cache_position[row] for row in scope_rows]
    cache = np.load(TRAINING_TOKEN_CACHE, mmap_mode="r", allow_pickle=False)
    metadata = read_json(TRAINING_TOKEN_CACHE_METADATA)
    cache_peak = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024)
    candidates = []
    baseline_predictions = None
    configurations = (
        [selected_only]
        if selected_only is not None
        else [(4, 1), (8, 1), (16, 1), (16, 2)]
    )
    for batch_size, parallelism in configurations:
        record, predictions = benchmark_candidate(
            cache,
            scope_positions,
            targets,
            batch_size=batch_size,
            parallelism=parallelism,
            baseline_predictions=baseline_predictions,
        )
        if baseline_predictions is None:
            baseline_predictions = predictions
        candidates.append(record)

    cuda_candidate = None
    if selected_only is None or subset_id == "n005_r00":
        require(baseline_predictions is not None, "CPU baseline predictions absent")
        cuda_records = []
        for cuda_batch_size in (2, 4):
            gather_started = time.perf_counter()
            gathered = np.asarray(
                cache[:cuda_batch_size, scope_positions, :],
                dtype=np.float16,
                order="C",
            ).transpose(1, 0, 2)
            gathered = np.ascontiguousarray(gathered)
            gather_seconds = time.perf_counter() - gather_started
            cuda = batched_ridge_predictions_all_alphas_from_features_cuda(
                gathered,
                targets,
                training_row_count=len(targets),
                alphas=ALPHAS,
            )
            cuda_difference = maximum_prediction_difference(
                baseline_predictions,
                cuda.predictions_by_token,
                cuda_batch_size,
            )
            cpu_order = ranking_orders(
                baseline_predictions[:cuda_batch_size], validation_targets
            )
            cuda_order = ranking_orders(cuda.predictions_by_token, validation_targets)
            ordering_equal = cpu_order == cuda_order
            equivalence_pass = cuda_difference <= EQUIVALENCE_ATOL and ordering_equal
            cuda_records.append(
                {
                    "batch_size": cuda_batch_size,
                    "cuda_peak_bytes": cuda.peak_device_memory_bytes,
                    "equivalence_pass": equivalence_pass,
                    "gather_seconds": gather_seconds,
                    "max_abs_prediction_difference": cuda_difference,
                    "ranking_order_equal_for_all_alphas": ordering_equal,
                    "seconds_per_token": cuda.timings["seconds_per_token"],
                    "total_seconds_per_token_including_gather": (
                        gather_seconds + cuda.timings["total_seconds"]
                    )
                    / cuda_batch_size,
                    "timings": dict(cuda.timings),
                }
            )
            del gathered, cuda
            gc.collect()
        equivalent_cuda = [
            record
            for record in cuda_records
            if record["equivalence_pass"] and record["cuda_peak_bytes"] <= GPU_CEILING
        ]
        selected_cuda = (
            min(
                equivalent_cuda,
                key=lambda record: record["total_seconds_per_token_including_gather"],
            )
            if equivalent_cuda
            else None
        )
        cpu_record = (
            next(
                record
                for record in candidates
                if record["batch_size"] == 4 and record["cpu_parallelism"] == 1
            )
            if selected_only is None
            else candidates[0]
        )
        cpu_seconds = (
            cpu_record["gather_seconds"] + cpu_record["solve_seconds"]
        ) / cpu_record["batch_size"]
        cuda_candidate = {
            "candidates": cuda_records,
            "selected": selected_cuda,
            "status": (
                "CANDIDATE_FASTER"
                if selected_cuda is not None
                and selected_cuda["total_seconds_per_token_including_gather"]
                < cpu_seconds
                else (
                    "REJECT_SLOWER_THAN_CPU"
                    if selected_cuda is not None
                    else "REJECT_NUMERICAL_OR_MEMORY_EQUIVALENCE"
                )
            ),
        }
    result = {
        "cache": {
            "byte_count": metadata["byte_count"],
            "build_seconds": metadata["build_seconds"],
            "dtype": metadata["dtype"],
            "peak_host_bytes_after_build": cache_peak,
            "policy": "RECONSTRUCTABLE_TRAINING_ONLY_TOKEN_MAJOR_NVME",
            "shape": metadata["shape"],
        },
        "candidates": candidates,
        "cuda_token_solve_candidate": cuda_candidate,
        "fixed_test_target_count": 0,
        "fixed_test_trajectory_count": 0,
        "subset_id": subset_id,
    }
    del cache
    gc.collect()
    return result


def run_worker(subset_id: str, selected_only: tuple[int, int] | None) -> dict[str, Any]:
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--worker",
        "--subset",
        subset_id,
    ]
    if selected_only is not None:
        command.extend(
            [
                "--selected-batch",
                str(selected_only[0]),
                "--selected-parallelism",
                str(selected_only[1]),
            ]
        )
    completed = subprocess.run(
        command, cwd=ROOT, check=True, capture_output=True, text=True
    )
    return json.loads(completed.stdout.strip().splitlines()[-1])


def baseline_decomposition() -> dict[str, float]:
    benchmark = read_json(P7_BENCHMARK)
    execution = read_json(P7_EXECUTION)
    replicates = {5: 20, 15: 16, 40: 12, 70: 8, 100: 6}
    seconds_by_n = {
        int(key): value
        for key, value in execution["expected_machine_runtime"][
            "ranking_exact_solve_seconds_by_training_size"
        ].items()
    }
    nested = sum(
        replicates[size] * 20 * TOKEN_COUNT * seconds_by_n[size] for size in replicates
    )
    final = sum(
        replicates[size] * 5 * TOKEN_COUNT * seconds_by_n[size] for size in replicates
    )
    full = (
        benchmark["n100"]["full_style_bounded_kernel"][
            "estimated_five_fold_kernel_seconds"
        ]
        * 62
    )
    coarse = (
        sum(
            benchmark["n100"]["coarse_grouped_alpha_cv_representative_fold"]["cuda"][
                key
            ]
            for key in ("scaling_seconds", "kernel_seconds")
        )
        * 5
        * 62
    )
    wide = (
        benchmark["n100"]["ranking_token_kernel"]["solve"][
            "estimated_full_solve_seconds_cubic"
        ]
        * 6
        * 62
    )
    result = {
        "BEST_K_candidate_and_other_wide_solves": wide,
        "COARSE": coarse,
        "FULL": full,
        "GLOBAL": 0.0,
        "IO_cache_overhead": 0.0,
        "final_all_training_token_ranking": final,
        "nested_token_ranking": nested,
    }
    require(
        abs(
            sum(result.values())
            - execution["expected_machine_runtime"]["estimated_single_machine_seconds"]
        )
        < 1e-6,
        "baseline decomposition does not replay P7",
    )
    return result


def build_documents() -> dict[str, Any]:
    verify_authority()
    baseline = baseline_decomposition()
    print("P7A build/verify training-only token-major cache", flush=True)
    cache_build = build_training_token_cache()
    print("P7A N=100 bounded candidates", flush=True)
    n100 = run_worker("n100_r00", None)
    memory_safe = [
        record
        for record in n100["candidates"]
        if record["host_peak_bytes"] <= HOST_CEILING
        and record["summed_kernel_gpu_peak_bytes"] <= GPU_CEILING
        and record["cpu_parallelism"] == 1
    ]
    require(memory_safe, "no P7A candidate respects memory ceilings")
    selected = min(
        memory_safe,
        key=lambda record: (
            record["summed_kernel_seconds_per_token"],
            -record["batch_size"],
            record["cpu_parallelism"],
        ),
    )
    selected_configuration = (
        int(selected["batch_size"]),
        int(selected["cpu_parallelism"]),
    )
    print("P7A selected-candidate N=5 sanity", flush=True)
    n5 = run_worker("n005_r00", selected_configuration)

    p7_benchmark = read_json(P7_BENCHMARK)
    old_token_seconds = p7_benchmark["n100"]["ranking_token_kernel"][
        "exact_smaller_space_solve"
    ]["total_seconds"]
    selected_cuda = n100["cuda_token_solve_candidate"]["selected"]
    cuda_selected = (
        n100["cuda_token_solve_candidate"]["status"] == "CANDIDATE_FASTER"
        and selected_cuda is not None
    )
    selected_token_seconds = (
        selected_cuda["seconds_per_token"]
        if cuda_selected
        else selected["solve_seconds_per_token"]
    )
    solve_ratio = selected_token_seconds / old_token_seconds
    old_wide_per_token = (
        p7_benchmark["n100"]["ranking_token_kernel"]["cuda_batch_seconds"]
        / BASELINE_BATCH
    )
    wide_ratio = selected["summed_kernel_seconds_per_token"] / old_wide_per_token
    new_nested = baseline["nested_token_ranking"] * solve_ratio
    new_final = baseline["final_all_training_token_ranking"] * solve_ratio
    new_full = baseline["FULL"] * wide_ratio

    replicates = {5: 20, 15: 16, 40: 12, 70: 8, 100: 6}
    n5_selected = n5["candidates"][0]
    wide_gather_by_n = {
        size: n5_selected["gather_seconds"]
        + (selected["gather_seconds"] - n5_selected["gather_seconds"])
        * ((size - 5) / 95)
        for size in replicates
    }
    ranking_batch_size = int(
        selected_cuda["batch_size"] if cuda_selected else selected["batch_size"]
    )
    n100_ranking_gather = (
        selected_cuda["gather_seconds"] if cuda_selected else selected["gather_seconds"]
    )
    n5_cuda = None
    if cuda_selected:
        n5_cuda = next(
            record
            for record in n5["cuda_token_solve_candidate"]["candidates"]
            if record["batch_size"] == ranking_batch_size
        )
        require(n5_cuda["equivalence_pass"], "N=5 CUDA equivalence changed")
    n5_ranking_gather = (
        n5_cuda["gather_seconds"] if cuda_selected else n5_selected["gather_seconds"]
    )
    ranking_gather_by_n = {
        size: n5_ranking_gather
        + (n100_ranking_gather - n5_ranking_gather) * ((size - 5) / 95)
        for size in replicates
    }
    ranking_batches_per_context = int(np.ceil(TOKEN_COUNT / ranking_batch_size))
    wide_batches_per_context = int(np.ceil(TOKEN_COUNT / selected["batch_size"]))
    new_io = cache_build["build_seconds"] + sum(
        replicates[size]
        * (
            25 * ranking_batches_per_context * ranking_gather_by_n[size]
            + 5 * wide_batches_per_context * wide_gather_by_n[size]
        )
        for size in replicates
    )
    new_decomposition = {
        "BEST_K_candidate_and_other_wide_solves": baseline[
            "BEST_K_candidate_and_other_wide_solves"
        ],
        "COARSE": baseline["COARSE"],
        "FULL": new_full,
        "GLOBAL": baseline["GLOBAL"],
        "IO_cache_overhead": new_io,
        "final_all_training_token_ranking": new_final,
        "nested_token_ranking": new_nested,
    }
    new_total = sum(new_decomposition.values())
    reduction = (OLD_EXPECTED_SECONDS - new_total) / OLD_EXPECTED_SECONDS
    adopted = reduction >= ADOPTION_THRESHOLD

    old_n100_section = (
        p7_benchmark["n100"]["ranking_token_kernel"]["input_seconds"]
        + p7_benchmark["n100"]["ranking_token_kernel"]["cpu_batch_seconds"]
        + p7_benchmark["n100"]["ranking_token_kernel"]["cuda_batch_seconds"]
    )
    selected_per_four = (
        n100_ranking_gather + selected_token_seconds * ranking_batch_size
    ) * 4 / ranking_batch_size + (
        selected["gather_seconds"] + selected["summed_kernel_seconds"]
    ) * 4 / selected[
        "batch_size"
    ]
    selected_n100_runtime = (
        p7_benchmark["n100"]["total_seconds"]
        - old_n100_section
        + selected_per_four
        + cache_build["build_seconds"]
        / (62 * (25 * ranking_batches_per_context + 5 * wide_batches_per_context))
    )

    maximum_prediction_difference_selected = max(
        record["prediction_max_abs_difference_vs_baseline"]
        for record in n100["candidates"]
    )
    if cuda_selected:
        maximum_prediction_difference_selected = max(
            maximum_prediction_difference_selected,
            selected_cuda["max_abs_prediction_difference"],
            n5_cuda["max_abs_prediction_difference"],
        )
    maximum_difference = max(
        maximum_prediction_difference_selected,
        max(
            record["small_extracted_kernel_max_abs_difference"]
            for record in n100["candidates"]
        ),
    )
    require(maximum_difference <= EQUIVALENCE_ATOL, "numerical tolerance exceeded")

    if not adopted:
        candidate_configuration = {
            "token_ranking": {
                "batch_size": ranking_batch_size,
                "device": "cuda:0" if cuda_selected else "cpu",
                "parallelism": 1,
            },
            "wide_kernel": {
                "batch_size": selected_configuration[0],
                "device": "cuda:0",
                "parallelism": selected_configuration[1],
            },
        }
        candidate_audit = {
            "artifact_id": "large-scale-no-wall-p7a-execution-optimization-v0.1",
            "adoption_threshold": ADOPTION_THRESHOLD,
            "alpha_reuse_already_optimal": True,
            "baseline_n100_runtime_seconds": p7_benchmark["n100"]["total_seconds"],
            "baseline_projection": baseline,
            "batched_sufficient_statistics_optimized": False,
            "best_candidate_configuration": candidate_configuration,
            "best_candidate_n100_adjusted_runtime_seconds": selected_n100_runtime,
            "best_candidate_projection": new_decomposition,
            "best_candidate_projection_seconds": new_total,
            "best_candidate_relative_reduction": reduction,
            "blocker": None,
            "bounded_candidates": {"n100": n100, "selected_n5": n5},
            "cache_candidate": {
                "byte_count": cache_build["byte_count"],
                "build_seconds": cache_build["build_seconds"],
                "removed_after_rejection": True,
                "sha256": cache_build["sha256"],
            },
            "cuda_token_ranking_decision": n100["cuda_token_solve_candidate"]["status"],
            "execution_plan_changed": False,
            "fixed_test_predictions_computed": False,
            "fixed_test_scores_opened_at_optimization": False,
            "fixed_test_targets_used": False,
            "logical_budgets_unchanged": True,
            "maximum_numerical_difference": maximum_difference,
            "maximum_prediction_difference": maximum_prediction_difference_selected,
            "model_outcomes_used_for_optimization": False,
            "numerical_tolerance": {
                "atol": EQUIVALENCE_ATOL,
                "rtol": EQUIVALENCE_RTOL,
            },
            "p7_head": P7_HEAD,
            "p7_plan_retained": {
                "expected_runtime_seconds": OLD_EXPECTED_SECONDS,
                "parallelism": BASELINE_PARALLELISM,
                "token_batch_size": BASELINE_BATCH,
                "token_device": "cpu exact smaller-space",
            },
            "p7_scientific_authority_unchanged": True,
            "p8_started": False,
            "runner_version": RUNNER_VERSION,
            "safe_for_p8": True,
            "scientific_authority_changed": False,
            "status": "PASS_P7A_NO_MATERIAL_EXACT_IMPROVEMENT",
        }
        write_json(P7A_AUDIT, candidate_audit)
        if TRAINING_TOKEN_CACHE.is_file():
            TRAINING_TOKEN_CACHE.unlink()
        if TRAINING_TOKEN_CACHE_METADATA.is_file():
            TRAINING_TOKEN_CACHE_METADATA.unlink()
        return candidate_audit

    benchmark_document = {
        "artifact_id": "large-scale-no-wall-p7a-solver-benchmark-v0.1",
        "alpha_reuse_already_optimal": True,
        "baseline_n100_runtime_seconds": p7_benchmark["n100"]["total_seconds"],
        "baseline_projection": baseline,
        "bounded_candidates": {"n100": n100, "selected_n5": n5},
        "cuda_token_ranking_decision": n100["cuda_token_solve_candidate"]["status"],
        "fixed_test_predictions_computed": False,
        "fixed_test_scores_opened": False,
        "fixed_test_targets_used": False,
        "maximum_numerical_difference": maximum_difference,
        "maximum_prediction_difference": maximum_prediction_difference_selected,
        "model_outcomes_used_for_optimization": False,
        "numerical_tolerance": {"atol": EQUIVALENCE_ATOL, "rtol": EQUIVALENCE_RTOL},
        "selected_configuration": {
            "n100_adjusted_runtime_seconds": selected_n100_runtime,
            "token_ranking": {
                "batch_size": ranking_batch_size,
                "device": "cuda:0" if cuda_selected else "cpu",
                "parallelism": 1,
            },
            "wide_kernel": {
                "batch_size": selected_configuration[0],
                "device": "cuda:0",
                "parallelism": selected_configuration[1],
            },
        },
        "status": "PASS_EXACT_BOUNDED_OPTIMIZATION",
    }
    write_json(P7A_BENCHMARK, benchmark_document)

    cache_document = {
        "artifact_id": "large-scale-no-wall-p7a-cache-manifest-v0.1",
        "durable_cache_change": True,
        "full_float32_cache_materialized": False,
        "p6_source_manifest_sha256": sha256_file(P6_MANIFEST),
        "p7_cache_manifest_sha256": sha256_file(P7_CACHE),
        "reconstructable_cache_s3_upload_skipped": True,
        "status": "LOCKED_FOR_P8",
        "token_cache": {
            "cache_sha256": cache_build["sha256"],
            "durability": "RECONSTRUCTABLE_NVME_ONLY",
            "dtype": "float16",
            "lifetime": "retain through P8",
            "maximum_measured_byte_count": cache_build["byte_count"],
            "maximum_measured_peak_host_bytes": max(
                record["host_peak_bytes"] for record in n100["candidates"]
            ),
            "path": cache_build["path"],
            "recipe": "training pool [row,token,hidden] -> [token,row,hidden] float16",
            "resume_behavior": "validate and reuse; rebuild only this reconstructable cache",
        },
    }
    write_json(P7A_CACHE, cache_document)

    hours_saved = (OLD_EXPECTED_SECONDS - new_total) / 3600
    gpu_active = (
        new_full
        + baseline["COARSE"]
        + (new_nested + new_final if cuda_selected else 0.0)
    )
    cpu_dominant = baseline["BEST_K_candidate_and_other_wide_solves"] + (
        0.0 if cuda_selected else new_nested + new_final
    )
    execution_document = {
        "artifact_id": "large-scale-no-wall-p7a-execution-budget-v0.1",
        "adoption_basis": "material runtime reduction with exact numerical equivalence",
        "bounded_parallelism": selected_configuration[1],
        "cache_strategy": "training-only token-major float16 NVMe cache; reconstructable, not S3",
        "device": {
            "COARSE_2x6": "cuda:0",
            "FULL_TOKEN_GRID": "cuda:0 summed bounded token kernels",
            "GLOBAL_MEAN": "cuda:0",
            "TOKEN_RANKING": (
                "cuda:0 exact batched float64 smaller-space"
                if cuda_selected
                else "cpu exact smaller-space"
            ),
        },
        "expected_machine_runtime": {
            "absolute_hours_saved": hours_saved,
            "estimated_cpu_dominant_seconds": cpu_dominant,
            "estimated_gpu_active_seconds": gpu_active,
            "new_seconds": new_total,
            "old_seconds": OLD_EXPECTED_SECONDS,
            "relative_reduction": reduction,
            "speedup": OLD_EXPECTED_SECONDS / new_total,
        },
        "feature_chunk_size": selected_configuration[0] * HIDDEN_WIDTH,
        "frozen_before_fixed_test_outcomes": True,
        "gpu_memory_ceiling_bytes": GPU_CEILING,
        "host_memory_ceiling_bytes": HOST_CEILING,
        "new_projection": new_decomposition,
        "numerical_computation_dtype": "float64",
        "p7_execution_budget_sha256": sha256_file(P7_EXECUTION),
        "resume_granularity": "subset_id/selection_fold/kernel_family/token_batch",
        "staged_device_plan": (
            "single hybrid environment; logical CPU/CUDA stages only because instance "
            "migration adds setup risk and no proven billing control"
        ),
        "status": "LOCKED_FOR_P8",
        "token_batch_size": ranking_batch_size,
        "wide_kernel_token_batch_size": selected_configuration[0],
    }
    write_json(P7A_EXECUTION, execution_document)

    audit = {
        "artifact_id": "large-scale-no-wall-p7a-execution-optimization-v0.1",
        "adoption_threshold": ADOPTION_THRESHOLD,
        "artifacts": {
            str(path.relative_to(ROOT)): sha256_file(path)
            for path in (P7A_BENCHMARK, P7A_CACHE, P7A_EXECUTION)
        },
        "batched_sufficient_statistics_optimized": True,
        "blocker": None,
        "execution_plan_changed": True,
        "fixed_test_predictions_computed": False,
        "fixed_test_scores_opened_at_optimization": False,
        "fixed_test_targets_used": False,
        "logical_budgets_unchanged": True,
        "model_outcomes_used_for_optimization": False,
        "p7_head": P7_HEAD,
        "p7_scientific_authority_unchanged": True,
        "p8_started": False,
        "runner_version": RUNNER_VERSION,
        "safe_for_p8": True,
        "scientific_authority_changed": False,
        "maximum_prediction_difference": maximum_prediction_difference_selected,
        "selected_configuration": benchmark_document["selected_configuration"],
        "status": "PASS_P7A_EXACT_EXECUTION_PLAN_OPTIMIZED",
    }
    write_json(P7A_AUDIT, audit)
    return audit


def validate_existing() -> None:
    authority = verify_authority()
    require(validate_logical_budgets(authority)["status"] == "PASS", "budgets")
    require(P7A_AUDIT.is_file(), f"missing P7A artifact: {P7A_AUDIT.name}")
    audit = read_json(P7A_AUDIT)
    require(audit["scientific_authority_changed"] is False, "scientific authority")
    require(audit["p8_started"] is False, "P8 guard")
    if audit["execution_plan_changed"]:
        for path in (P7A_BENCHMARK, P7A_CACHE, P7A_EXECUTION):
            require(path.is_file(), f"missing P7A artifact: {path.name}")
        benchmark = read_json(P7A_BENCHMARK)
        execution = read_json(P7A_EXECUTION)
        require(benchmark["fixed_test_scores_opened"] is False, "fixed-test scores")
        require(benchmark["fixed_test_targets_used"] is False, "fixed-test targets")
        require(
            benchmark["maximum_numerical_difference"] <= EQUIVALENCE_ATOL,
            "numerical equivalence",
        )
        require(execution["host_memory_ceiling_bytes"] == HOST_CEILING, "host ceiling")
        require(execution["gpu_memory_ceiling_bytes"] == GPU_CEILING, "GPU ceiling")
    else:
        require(
            audit["status"] == "PASS_P7A_NO_MATERIAL_EXACT_IMPROVEMENT",
            "no-change status",
        )
        require(
            audit["maximum_numerical_difference"] <= EQUIVALENCE_ATOL,
            "numerical equivalence",
        )
        require(not TRAINING_TOKEN_CACHE.exists(), "rejected cache retained")
        require(
            not TRAINING_TOKEN_CACHE_METADATA.exists(), "rejected metadata retained"
        )
        require(not P7A_BENCHMARK.exists(), "unselected benchmark lock exists")
        require(not P7A_CACHE.exists(), "unselected cache lock exists")
        require(not P7A_EXECUTION.exists(), "unselected execution lock exists")
    require(not (STUDY_ROOT / "learning_curve_results.json").exists(), "P8 started")
    require(not (STUDY_ROOT / "best_k_results.json").exists(), "P8 BEST-K exists")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--subset", default="n100_r00")
    parser.add_argument("--selected-batch", type=int)
    parser.add_argument("--selected-parallelism", type=int)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    if args.worker:
        selected = (
            None
            if args.selected_batch is None
            else (args.selected_batch, args.selected_parallelism)
        )
        print(json.dumps(worker(args.subset, selected), sort_keys=True))
        return 0
    if args.validate_only:
        validate_existing()
        print("PASS P7A focused execution validation")
        return 0
    print(json.dumps(build_documents(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
