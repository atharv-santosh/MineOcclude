#!/usr/bin/env python3
"""Build P7 representation and exact-solver authority without starting P8.

The runner is deliberately limited to structural representation checks,
training-only numerical equivalence, and pre-outcome execution benchmarks.  It
never loads fixed-test targets into a benchmark matrix and never emits a fixed-
test prediction or scientific score.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import resource
import subprocess
import sys
import time
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np

from mineocclude.probes.p7_ridge import (
    batched_ridge_predictions_all_alphas,
    batched_token_kernels_cuda,
    batched_token_kernels_numpy,
    cumulative_token_kernel_snapshots,
    ridge_predictions_all_alphas_from_features,
    ridge_predictions_all_alphas_from_kernel,
    standardized_kernel_cuda,
    standardized_kernel_numpy,
)

RUNNER_VERSION = "large-scale-no-wall-p7-representation-solver-v0.1"
P6_HEAD = "416d1041121f1f33e2fdebdebc5df6610ddb1d89"
BRANCH = "exploration/large-scale-no-wall-scaling-best-k-v0-1"
STUDY_REL = Path(
    "docs/status/integration/exploratory_large_scale_no_wall_scaling_best_k_v0_1"
)
STUDY_ROOT = ROOT / STUDY_REL
EXTERNAL_P6_ROOT = Path(
    "/mnt/sagemaker-nvme/"
    "mineocclude_large_scale_no_wall_scaling_best_k_v0_1_v2/"
    "p6_layer4_activations_v0_1"
)
ACTIVATION_ROOT = EXTERNAL_P6_ROOT / "activations"
CACHE_ROOT = Path(
    "/mnt/sagemaker-nvme/"
    "mineocclude_large_scale_no_wall_scaling_best_k_v0_1_v2/"
    "p7_representation_solver_v0_1"
)
COARSE_CACHE = CACHE_ROOT / "coarse_2x6.f32.npy"
COARSE_METADATA = CACHE_ROOT / "coarse_2x6.metadata.json"

P6_MANIFEST = STUDY_ROOT / "p6_activation_manifest.json"
COHORT_LOCK = STUDY_ROOT / "accepted_cohort_v2.lock.json"
SPLIT_AUTHORITY = STUDY_ROOT / "split_authority.json"
SUBSET_SCHEDULE = STUDY_ROOT / "subset_schedule.json"
GROUPED_FOLDS = STUDY_ROOT / "grouped_fold_authority.json"
TEST_GUARD = STUDY_ROOT / "test_guard.lock"
CANONICAL_ROWS = STUDY_ROOT / "canonical_row_authority.jsonl"
REPRESENTATION_AUTHORITY = STUDY_ROOT / "representation_authority.json"
CACHE_MANIFEST = STUDY_ROOT / "cache_manifest.json"
SOLVER_BENCHMARK = STUDY_ROOT / "solver_benchmark.json"
EXECUTION_BUDGET = STUDY_ROOT / "execution_budget.lock.json"
P7_RECEIPT = STUDY_ROOT / "p7_receipt.json"

PROTECTED_SHA256 = {
    "accepted_cohort_v2.lock.json": (
        "b73d1b6bbedc1ca72dab480ba6f4bafb22aa7c6675bc7a2f0dabf33fff2d8501"
    ),
    "split_authority.json": (
        "b39c81454ea18125c373fb3c777ac4c1668882c9c1ad188a7d0f20e0cab43de5"
    ),
    "subset_schedule.json": (
        "0d6f5e8394328915164bafea70468e6d26342a2eda9a1923e4d4ad745f494a48"
    ),
    "grouped_fold_authority.json": (
        "597bc7b401ca691897b843fc83120cc997a414b7a946819da4c3e99768e7728e"
    ),
    "test_guard.lock": (
        "0adc85a5d90eb92361ba0775d58a6ccc2eb674a8ae5ffd2e816b89d9d9b48ac5"
    ),
    "p6_activation_manifest.json": (
        "a57be180a9054336dbe36d2ddaddbec2859e21d5b6a42dae5b25b1c276e2d5bb"
    ),
}
ALPHAS = (0.1, 1.0, 10.0, 100.0)
BEST_K = (1, 4, 8, 16, 32, 64, 128)
TOKEN_GRID = (14, 24)
TOKEN_COUNT = 336
HIDDEN_WIDTH = 2048
ROW_COUNT = 7200
TRAJECTORY_COUNT = 120
FRAMES_PER_TRAJECTORY = 60
GLOBAL_DIM = HIDDEN_WIDTH
FULL_DIM = TOKEN_COUNT * HIDDEN_WIDTH
COARSE_DIM = 12 * HIDDEN_WIDTH
EQUIVALENCE_ATOL = 1e-7
EQUIVALENCE_RTOL = 1e-7
BENCHMARK_TOKEN_BATCH_SIZE = 4
SOLVE_CALIBRATION_ROWS = 480


class P7Error(RuntimeError):
    """Raised when P7 would violate a frozen authority or leakage boundary."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise P7Error(message)


def sha256_file(path: Path, chunk_size: int = 8 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(chunk_size), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"JSON authority is not a mapping: {path}")
    return value


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, indent=2, sort_keys=True) + "\n"
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    temporary.write_text(payload, encoding="utf-8")
    os.replace(temporary, path)


def write_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    with temporary.open("wb") as handle:
        for row in rows:
            handle.write(canonical_bytes(dict(row)) + b"\n")
    os.replace(temporary, path)


def git(*arguments: str) -> str:
    return subprocess.check_output(["git", *arguments], cwd=ROOT, text=True).strip()


def verify_start_authority() -> dict[str, Any]:
    """Verify immutable predecessor identities without rehashing 10 GB."""

    require(git("branch", "--show-current") == BRANCH, "wrong P7 branch")
    subprocess.run(
        ["git", "merge-base", "--is-ancestor", P6_HEAD, "HEAD"],
        cwd=ROOT,
        check=True,
    )
    for name, expected in PROTECTED_SHA256.items():
        require(
            sha256_file(STUDY_ROOT / name) == expected, f"changed authority: {name}"
        )
    require(EXTERNAL_P6_ROOT.is_dir(), "validated local P6 root is absent")
    external_manifest = EXTERNAL_P6_ROOT / "activation_manifest.json"
    require(
        sha256_file(external_manifest)
        == PROTECTED_SHA256["p6_activation_manifest.json"],
        "local P6 manifest identity differs from Git authority",
    )
    manifest = read_json(P6_MANIFEST)
    split = read_json(SPLIT_AUTHORITY)
    schedule = read_json(SUBSET_SCHEDULE)
    folds = read_json(GROUPED_FOLDS)
    guard = read_json(TEST_GUARD)
    require(
        manifest["cohort_version"] == "V2_ACCEPTED_REPAIRED_PRIMARY", "wrong cohort"
    )
    require(manifest["trajectory_count"] == TRAJECTORY_COUNT, "wrong trajectory count")
    require(manifest["frame_count"] == ROW_COUNT, "wrong activation row count")
    require(len(manifest["chunks"]) == TRAJECTORY_COUNT, "wrong P6 shard count")
    require(split["fixed_test"]["count"] == guard["test_count"] == 18, "test mismatch")
    require(split["training_pool"]["count"] == 102, "training-pool mismatch")
    require(split["train_test_overlap"] == 0, "train/test overlap")
    require(split["v1_primary_intersection"] == 0, "V1 primary intersection")
    require(
        split["fixed_test"]["authority_hash"] == guard["test_authority_hash"],
        "fixed-test hash mismatch",
    )
    require(
        schedule["total_subsets"] == len(schedule["subsets"]) == 62, "subset mismatch"
    )
    require(len(folds["subsets"]) == 62, "grouped-fold subset mismatch")
    return {
        "manifest": manifest,
        "split": split,
        "schedule": schedule,
        "folds": folds,
        "guard": guard,
        "p6_manifest_sha256": PROTECTED_SHA256["p6_activation_manifest.json"],
    }


def build_canonical_rows(
    authority: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], str]:
    manifest = authority["manifest"]
    split = authority["split"]
    cohort = read_json(COHORT_LOCK)
    entries = cohort["entries"]
    cohort_by_id = {row["trajectory_spec_id"]: row for row in entries}
    entry_ordinal = {
        row["trajectory_spec_id"]: ordinal for ordinal, row in enumerate(entries)
    }
    membership = {}
    for name in ("training_pool", "fixed_test"):
        for row in split[name]["members"]:
            identity = row["trajectory_spec_id"]
            require(identity not in membership, f"duplicate split member: {identity}")
            membership[identity] = name
    require(set(cohort_by_id) == set(membership), "P5/P6 cohort membership differs")
    rows = []
    keys = set()
    for chunk_ordinal, chunk in enumerate(manifest["chunks"]):
        identity = chunk["trajectory_spec_id"]
        require(identity.startswith("fresh_vp_v2_"), f"V1 identity in P6: {identity}")
        require(identity in cohort_by_id, f"P6 identity absent from cohort: {identity}")
        metadata = cohort_by_id[identity]
        row_path = ACTIVATION_ROOT / chunk["rows"]["path"]
        token_path = ACTIVATION_ROOT / chunk["unpooled"]["path"]
        pooled_path = ACTIVATION_ROOT / chunk["pooled"]["path"]
        require(
            row_path.is_file() and token_path.is_file() and pooled_path.is_file(),
            f"missing P6 shard: {identity}",
        )
        require(
            token_path.stat().st_size == chunk["unpooled"]["byte_size"],
            f"token size mismatch: {identity}",
        )
        require(
            pooled_path.stat().st_size == chunk["pooled"]["byte_size"],
            f"pooled size mismatch: {identity}",
        )
        shard_rows = read_jsonl(row_path)
        require(
            len(shard_rows) == FRAMES_PER_TRAJECTORY, f"row count mismatch: {identity}"
        )
        for within_shard, source_row in enumerate(shard_rows):
            key = (identity, int(source_row["model_frame_idx"]))
            require(key not in keys, f"duplicate scientific row: {key}")
            require(key[1] == within_shard, f"nonascending model frames: {identity}")
            keys.add(key)
            rows.append(
                {
                    "direction": metadata["direction"],
                    "layout": metadata["layout_id"],
                    "membership": membership[identity],
                    "membership_reference": (
                        f"{STUDY_REL}/split_authority.json#/"
                        f"{membership[identity]}/members"
                    ),
                    "model_frame_idx": within_shard,
                    "p6_activation_shard": chunk["unpooled"]["path"],
                    "p6_chunk_ordinal": chunk_ordinal,
                    "pooled_activation_shard": chunk["pooled"]["path"],
                    "reporting_stratum": metadata["reporting_stratum"],
                    "row_ordinal": len(rows),
                    "scientific_row_key": [identity, within_shard],
                    "target_authority_reference": (
                        f"{STUDY_REL}/accepted_cohort_v2.lock.json#/entries/"
                        f"{entry_ordinal[identity]}/target_authority/x_true_blocks/"
                        f"{within_shard}"
                    ),
                    "trajectory_shape_class": metadata["trajectory_shape_class"],
                    "trajectory_spec_id": identity,
                    "within_shard_row": within_shard,
                }
            )
    require(
        len(rows) == len(keys) == ROW_COUNT, "canonical row authority is incomplete"
    )
    require(
        sum(row["membership"] == "fixed_test" for row in rows) == 1080,
        "test row mismatch",
    )
    require(
        sum(row["membership"] == "training_pool" for row in rows) == 6120,
        "training row mismatch",
    )
    row_hash = canonical_sha256(rows)
    write_jsonl(CANONICAL_ROWS, rows)
    return rows, row_hash


class ActivationAccess:
    """One manifest-addressed access path shared by every P7 representation."""

    def __init__(self, rows: Sequence[Mapping[str, Any]]):
        self.rows = tuple(rows)
        self.by_trajectory: dict[str, list[int]] = defaultdict(list)
        for row in self.rows:
            self.by_trajectory[str(row["trajectory_spec_id"])].append(
                int(row["row_ordinal"])
            )

    def row_ordinals(self, trajectory_ids: Sequence[str]) -> list[int]:
        ordinals = []
        for identity in trajectory_ids:
            require(identity in self.by_trajectory, f"unknown trajectory: {identity}")
            ordinals.extend(self.by_trajectory[identity])
        return ordinals

    def _group(self, row_ordinals: Sequence[int]) -> dict[str, list[tuple[int, int]]]:
        grouped: dict[str, list[tuple[int, int]]] = defaultdict(list)
        for destination, ordinal in enumerate(row_ordinals):
            row = self.rows[int(ordinal)]
            grouped[str(row["trajectory_spec_id"])].append(
                (destination, int(row["within_shard_row"]))
            )
        return grouped

    def global_rows(self, row_ordinals: Sequence[int]) -> np.ndarray:
        result = np.empty((len(row_ordinals), HIDDEN_WIDTH), dtype=np.float32)
        for identity, claims in self._group(row_ordinals).items():
            first = self.rows[self.by_trajectory[identity][0]]
            source = np.load(
                ACTIVATION_ROOT / str(first["pooled_activation_shard"]),
                mmap_mode="r",
                allow_pickle=False,
            )
            for destination, within in claims:
                result[destination] = source[within]
        return result

    def token_rows(
        self, row_ordinals: Sequence[int], token_indices: Sequence[int]
    ) -> np.ndarray:
        selected = tuple(int(value) for value in token_indices)
        require(selected, "at least one token index is required")
        require(len(set(selected)) == len(selected), "duplicate token selection")
        require(
            all(0 <= value < TOKEN_COUNT for value in selected), "token out of range"
        )
        result = np.empty(
            (len(row_ordinals), len(selected), HIDDEN_WIDTH), dtype=np.float16
        )
        for identity, claims in self._group(row_ordinals).items():
            first = self.rows[self.by_trajectory[identity][0]]
            source = np.load(
                ACTIVATION_ROOT / str(first["p6_activation_shard"]),
                mmap_mode="r",
                allow_pickle=False,
            )
            within = [claim[1] for claim in claims]
            block = np.asarray(source[within])[:, selected, :]
            for offset, (destination, _) in enumerate(claims):
                result[destination] = block[offset]
        return result


def build_coarse_cache_and_equivalence(
    authority: Mapping[str, Any], rows: Sequence[Mapping[str, Any]], row_hash: str
) -> dict[str, Any]:
    """Build the cheap reconstructable COARSE cache while checking all means."""

    CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    expected_identity = canonical_sha256(
        {
            "p6_manifest_sha256": authority["p6_manifest_sha256"],
            "row_authority_sha256": row_hash,
            "recipe": "reshape [rows,2,7,6,4,2048], mean axes (2,4), flatten C",
        }
    )
    if COARSE_CACHE.is_file() and COARSE_METADATA.is_file():
        metadata = read_json(COARSE_METADATA)
        cached = np.load(COARSE_CACHE, mmap_mode="r", allow_pickle=False)
        if (
            metadata.get("source_identity_sha256") == expected_identity
            and list(cached.shape) == [ROW_COUNT, COARSE_DIM]
            and cached.dtype == np.float32
            and metadata.get("sha256") == sha256_file(COARSE_CACHE)
        ):
            return {**metadata, "cache_reused": True}

    cache = np.lib.format.open_memmap(
        COARSE_CACHE, mode="w+", dtype=np.float32, shape=(ROW_COUNT, COARSE_DIM)
    )
    maximum_global_difference = 0.0
    started = time.perf_counter()
    for chunk_ordinal, chunk in enumerate(authority["manifest"]["chunks"]):
        tokens = np.load(
            ACTIVATION_ROOT / chunk["unpooled"]["path"],
            mmap_mode="r",
            allow_pickle=False,
        )
        pooled = np.load(
            ACTIVATION_ROOT / chunk["pooled"]["path"],
            mmap_mode="r",
            allow_pickle=False,
        )
        start = chunk_ordinal * FRAMES_PER_TRAJECTORY
        for local_start in range(0, FRAMES_PER_TRAJECTORY, 4):
            local_stop = min(local_start + 4, FRAMES_PER_TRAJECTORY)
            block = np.asarray(tokens[local_start:local_stop], dtype=np.float32)
            global_mean = block.mean(axis=1)
            maximum_global_difference = max(
                maximum_global_difference,
                float(
                    np.max(
                        np.abs(
                            global_mean
                            - np.asarray(
                                pooled[local_start:local_stop], dtype=np.float32
                            )
                        )
                    )
                ),
            )
            coarse = (
                block.reshape(-1, 2, 7, 6, 4, HIDDEN_WIDTH)
                .mean(axis=(2, 4))
                .reshape(-1, COARSE_DIM)
            )
            cache[start + local_start : start + local_stop] = coarse
    cache.flush()
    del cache
    require(maximum_global_difference == 0.0, "GLOBAL mean differs from P6 pool")
    metadata = {
        "byte_size": COARSE_CACHE.stat().st_size,
        "cache_reused": False,
        "dtype": "float32",
        "global_equivalence_max_abs_difference": maximum_global_difference,
        "path": str(COARSE_CACHE),
        "recipe": "reshape [rows,2,7,6,4,2048], mean axes (2,4), flatten C",
        "row_order": "canonical_row_authority.jsonl row_ordinal",
        "sha256": sha256_file(COARSE_CACHE),
        "shape": [ROW_COUNT, COARSE_DIM],
        "source_identity_sha256": expected_identity,
        "build_seconds": time.perf_counter() - started,
    }
    write_json(COARSE_METADATA, metadata)
    return metadata


def validate_representation_views(
    access: ActivationAccess, coarse_metadata: Mapping[str, Any]
) -> dict[str, Any]:
    sample_rows = [0, 59, 60, 3071, 7199]
    tokens = access.token_rows(sample_rows, [0, 1, 17, 335]).astype(np.float32)
    full_source = access.token_rows(sample_rows, list(range(TOKEN_COUNT))).astype(
        np.float32
    )
    flattened = full_source.reshape(len(sample_rows), FULL_DIM)
    for token_index in (0, 1, 17, 335):
        begin = token_index * HIDDEN_WIDTH
        require(
            np.array_equal(
                flattened[:, begin : begin + HIDDEN_WIDTH],
                full_source[:, token_index, :],
            ),
            f"FULL token order mismatch at {token_index}",
        )
    selected = [335, 1, 17, 0]
    ascending = sorted(selected)
    best = (
        access.token_rows(sample_rows, ascending)
        .astype(np.float32)
        .reshape(len(sample_rows), -1)
    )
    for offset, token_index in enumerate(ascending):
        require(
            np.array_equal(
                best[:, offset * HIDDEN_WIDTH : (offset + 1) * HIDDEN_WIDTH],
                full_source[:, token_index, :],
            ),
            "BEST-K ascending concatenation mismatch",
        )
    coarse_cache = np.load(
        str(coarse_metadata["path"]), mmap_mode="r", allow_pickle=False
    )
    direct = full_source.reshape(-1, 14, 24, HIDDEN_WIDTH)
    independent = np.stack(
        [
            np.stack(
                [
                    direct[:, row * 7 : (row + 1) * 7, col * 4 : (col + 1) * 4].mean(
                        axis=(1, 2)
                    )
                    for col in range(6)
                ],
                axis=1,
            )
            for row in range(2)
        ],
        axis=1,
    ).reshape(-1, COARSE_DIM)
    require(
        np.array_equal(independent, np.asarray(coarse_cache[sample_rows])),
        "COARSE 2x6 independent geometry mismatch",
    )
    require(tokens.shape == (len(sample_rows), 4, HIDDEN_WIDTH), "token view shape")
    return {
        "best_k_ascending_order": "PASS",
        "coarse_geometry": "PASS",
        "full_token_order": "PASS",
        "sample_row_ordinals": sample_rows,
    }


def validate_nested_grouping(authority: Mapping[str, Any]) -> dict[str, Any]:
    schedule = {row["subset_id"]: row for row in authority["schedule"]["subsets"]}
    fold_authority = {row["subset_id"]: row for row in authority["folds"]["subsets"]}
    fixed_test = set(authority["guard"]["test_trajectory_ids"])
    require(set(schedule) == set(fold_authority), "subset/fold IDs differ")
    ranking_subfold_count = 0
    for subset_id, subset in schedule.items():
        expected = set(subset["trajectory_spec_ids"])
        record = fold_authority[subset_id]
        folds = {fold["fold_id"]: fold for fold in record["selection_folds"]}
        require(len(folds) == 5, f"{subset_id}: wrong selection fold count")
        seen = []
        for fold in folds.values():
            validation = set(fold["validation_trajectory_ids"])
            training = set().union(
                *(
                    set(folds[fold_id]["validation_trajectory_ids"])
                    for fold_id in fold["selection_training_fold_ids"]
                )
            )
            require(not validation & training, f"{subset_id}: outer fold leakage")
            require(validation | training == expected, f"{subset_id}: outer coverage")
            seen.extend(validation)
        require(
            set(seen) == expected and len(seen) == len(expected),
            f"{subset_id}: fold partition",
        )
        require(
            not expected & fixed_test, f"{subset_id}: fixed-test member in training"
        )
        nested = record["best_k_ranking_subfolds_by_outer_selection_fold"]
        for withheld_fold_id, subfolds in nested.items():
            withheld = set(folds[withheld_fold_id]["validation_trajectory_ids"])
            require(len(subfolds) == 4, f"{subset_id}: wrong ranking subfold count")
            ranking_validation_folds = set()
            for subfold in subfolds:
                validation_fold_id = subfold["validation_selection_fold_id"]
                training_fold_ids = set(subfold["ranking_training_selection_fold_ids"])
                require(
                    withheld_fold_id not in training_fold_ids,
                    f"{subset_id}: withheld fold ranked",
                )
                require(
                    validation_fold_id != withheld_fold_id,
                    f"{subset_id}: withheld fold validates ranking",
                )
                require(
                    validation_fold_id not in training_fold_ids,
                    f"{subset_id}: ranking leakage",
                )
                require(
                    len(training_fold_ids) == 3,
                    f"{subset_id}: ranking train fold count",
                )
                exposed = set(folds[validation_fold_id]["validation_trajectory_ids"])
                for training_fold_id in training_fold_ids:
                    exposed.update(folds[training_fold_id]["validation_trajectory_ids"])
                require(
                    not exposed & withheld, f"{subset_id}: withheld IDs reached ranking"
                )
                ranking_validation_folds.add(validation_fold_id)
                ranking_subfold_count += 1
            require(
                ranking_validation_folds == set(folds) - {withheld_fold_id},
                f"{subset_id}: ranking validation coverage",
            )
    return {
        "fixed_test_ids_used": 0,
        "nested_ranking_subfold_records": ranking_subfold_count,
        "status": "PASS",
        "subset_count": len(schedule),
    }


def validate_logical_budgets(authority: Mapping[str, Any]) -> dict[str, int | str]:
    subsets = len(authority["schedule"]["subsets"])
    values: dict[str, int | str] = {
        "learning_curve_subset_authorities": subsets,
        "core_final_outer_fits": subsets * 3,
        "secondary_coarse_outer_fits": subsets,
        "global_full_coarse_alpha_cv_logical_evaluations": subsets * 5 * 4 * 3,
        "nested_token_ranking_logical_evaluations": subsets * 5 * 4 * 336 * 4,
        "nested_ranking_subfold_batches_before_vectorization": subsets * 5 * 4,
        "best_k_candidate_logical_evaluations": subsets * 5 * 7 * 4,
        "final_token_ranking_logical_evaluations": subsets * 5 * 336 * 4,
        "final_ranking_fold_batches_before_vectorization": subsets * 5,
    }
    expected = {
        "learning_curve_subset_authorities": 62,
        "core_final_outer_fits": 186,
        "secondary_coarse_outer_fits": 62,
        "global_full_coarse_alpha_cv_logical_evaluations": 3720,
        "nested_token_ranking_logical_evaluations": 1666560,
        "nested_ranking_subfold_batches_before_vectorization": 1240,
        "best_k_candidate_logical_evaluations": 8680,
        "final_token_ranking_logical_evaluations": 416640,
        "final_ranking_fold_batches_before_vectorization": 310,
    }
    require(values == expected, "logical budgets differ from P7 roadmap")
    values["status"] = "PASS"
    return values


def subset_fold_ids(
    authority: Mapping[str, Any], subset_id: str, fold_ordinal: int = 0
) -> tuple[list[str], list[str], list[str]]:
    subset = next(
        row for row in authority["folds"]["subsets"] if row["subset_id"] == subset_id
    )
    folds = {row["fold_id"]: row for row in subset["selection_folds"]}
    held = folds[f"selection_fold_{fold_ordinal}"]
    training = [
        identity
        for fold_id in held["selection_training_fold_ids"]
        for identity in folds[fold_id]["validation_trajectory_ids"]
    ]
    validation = list(held["validation_trajectory_ids"])
    return training, validation, training + validation


def training_targets(
    cohort: Mapping[str, Any], trajectory_ids: Sequence[str]
) -> np.ndarray:
    """Load targets only for an explicit training-pool allowlist."""

    requested = set(trajectory_ids)
    values_by_id = {}
    for entry in cohort["entries"]:
        identity = entry["trajectory_spec_id"]
        if identity in requested:
            values_by_id[identity] = entry["target_authority"]["x_true_blocks"]
    require(set(values_by_id) == requested, "training target allowlist is incomplete")
    return np.asarray(
        [value for identity in trajectory_ids for value in values_by_id[identity]],
        dtype=np.float64,
    )


def solve_timing(
    kernel: np.ndarray, targets: np.ndarray, *, full_training_rows: int
) -> dict[str, Any]:
    calibration = min(SOLVE_CALIBRATION_ROWS, len(targets))
    small_kernel = kernel[:calibration, :calibration]
    small_targets = targets[:calibration]
    started = time.perf_counter()
    predictions = ridge_predictions_all_alphas_from_kernel(
        small_kernel, small_targets, alphas=ALPHAS
    )
    elapsed = time.perf_counter() - started
    require(set(predictions) == set(ALPHAS), "not all alphas were solved")
    estimate = elapsed * (full_training_rows / calibration) ** 3
    return {
        "alpha_count": len(ALPHAS),
        "calibration_rows": calibration,
        "calibration_seconds": elapsed,
        "estimated_full_solve_seconds_cubic": estimate,
        "prediction_values_persisted": False,
    }


def benchmark_subset(
    authority: Mapping[str, Any], access: ActivationAccess, subset_id: str
) -> dict[str, Any]:
    """Benchmark one frozen subset using only its training-pool trajectories."""

    cohort = read_json(COHORT_LOCK)
    training_ids, validation_ids, scope_ids = subset_fold_ids(authority, subset_id)
    require(
        not set(scope_ids) & set(authority["guard"]["test_trajectory_ids"]),
        "benchmark scope intersects fixed test",
    )
    train_rows = access.row_ordinals(training_ids)
    scope_rows = access.row_ordinals(scope_ids)
    train_count = len(train_rows)
    targets = training_targets(cohort, training_ids)
    require(len(targets) == train_count, "training targets do not align")
    benchmark_started = time.perf_counter()

    input_started = time.perf_counter()
    global_scope = access.global_rows(scope_rows)
    global_train = global_scope[:train_count]
    global_input_seconds = time.perf_counter() - input_started
    cpu_global = standardized_kernel_numpy(global_train, global_scope)
    cuda_global = standardized_kernel_cuda(global_train, global_scope)
    global_feature_solve = ridge_predictions_all_alphas_from_features(
        global_train,
        global_scope,
        targets,
        alphas=ALPHAS,
        prediction_scope_positions=range(train_count, len(scope_rows)),
    )
    global_solve = solve_timing(
        cuda_global.kernel, targets, full_training_rows=train_count
    )

    token_indices = list(range(BENCHMARK_TOKEN_BATCH_SIZE))
    input_started = time.perf_counter()
    token_scope = access.token_rows(scope_rows, token_indices)
    token_train = token_scope[:train_count]
    token_input_seconds = time.perf_counter() - input_started
    cpu_token_started = time.perf_counter()
    cpu_token_kernels, _ = batched_token_kernels_numpy(token_train, token_scope)
    cpu_token_seconds = time.perf_counter() - cpu_token_started
    cuda_token_started = time.perf_counter()
    cuda_token_kernels, _, cuda_token_audit = batched_token_kernels_cuda(
        token_train, token_scope
    )
    cuda_token_total = time.perf_counter() - cuda_token_started
    maximum_token_kernel_difference = float(
        np.max(np.abs(cpu_token_kernels - cuda_token_kernels))
    )
    require(
        np.allclose(
            cpu_token_kernels,
            cuda_token_kernels,
            atol=EQUIVALENCE_ATOL,
            rtol=EQUIVALENCE_RTOL,
        ),
        f"{subset_id}: CUDA token kernel differs from float64 reference",
    )
    token_solve = solve_timing(
        cuda_token_kernels[0], targets, full_training_rows=train_count
    )
    token_feature_solve = ridge_predictions_all_alphas_from_features(
        token_train[:, 0, :],
        token_scope[:, 0, :],
        targets,
        alphas=ALPHAS,
        prediction_scope_positions=range(train_count, len(scope_rows)),
    )
    calibration = min(SOLVE_CALIBRATION_ROWS, train_count)
    batched_predictions = batched_ridge_predictions_all_alphas(
        cuda_token_kernels[:, :calibration, :calibration],
        targets[:calibration],
        alphas=ALPHAS,
    )
    require(len(batched_predictions) == BENCHMARK_TOKEN_BATCH_SIZE, "batched solve")
    cumulative = cumulative_token_kernel_snapshots(
        {index: cuda_token_kernels[index] for index in token_indices},
        token_indices,
        (1, 4),
    )
    require(set(cumulative) == {1, 4}, "cumulative BEST-K kernel failed")

    coarse = np.load(COARSE_CACHE, mmap_mode="r", allow_pickle=False)
    input_started = time.perf_counter()
    coarse_scope = np.asarray(coarse[scope_rows], dtype=np.float32)
    coarse_train = coarse_scope[:train_count]
    coarse_input_seconds = time.perf_counter() - input_started
    cuda_coarse = standardized_kernel_cuda(coarse_train, coarse_scope)
    coarse_solve = solve_timing(
        cuda_coarse.kernel, targets, full_training_rows=train_count
    )

    selected_kernel_device = (
        "cuda:0" if cuda_token_total <= cpu_token_seconds else "cpu"
    )
    peak_host = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024)
    full_one_fold_kernel_estimate = (
        (cuda_token_total if selected_kernel_device == "cuda:0" else cpu_token_seconds)
        * TOKEN_COUNT
        / BENCHMARK_TOKEN_BATCH_SIZE
    )
    return {
        "alpha_grid": list(ALPHAS),
        "benchmark_scope": "TRAINING_POOL_ONLY",
        "fixed_test_target_count_loaded": 0,
        "fixed_test_trajectory_count": 0,
        "full_style_bounded_kernel": {
            "feature_order": "ascending visual_token_index",
            "measured_token_count": BENCHMARK_TOKEN_BATCH_SIZE,
            "estimated_full_one_fold_kernel_seconds": full_one_fold_kernel_estimate,
            "estimated_five_fold_kernel_seconds": full_one_fold_kernel_estimate * 5,
        },
        "global_grouped_alpha_cv_representative_fold": {
            "cpu": {**cpu_global.timings},
            "cuda": {
                **cuda_global.timings,
                "peak_device_memory_bytes": cuda_global.peak_device_memory_bytes,
            },
            "input_seconds": global_input_seconds,
            "exact_smaller_space_solve": {
                "prediction_values_persisted": False,
                "solve_space": global_feature_solve.solve_space,
                "system_dimension": global_feature_solve.system_dimension,
                **global_feature_solve.timings,
            },
            "solve": global_solve,
        },
        "coarse_grouped_alpha_cv_representative_fold": {
            "cuda": {
                **cuda_coarse.timings,
                "peak_device_memory_bytes": cuda_coarse.peak_device_memory_bytes,
            },
            "input_seconds": coarse_input_seconds,
            "solve": coarse_solve,
        },
        "best_k_cumulative_kernel": {
            "candidate_boundaries_exercised": [1, 4],
            "full_candidate_grid_supported": list(BEST_K),
            "status": "PASS",
        },
        "peak_host_rss_bytes": peak_host,
        "ranking_token_kernel": {
            "cpu_batch_seconds": cpu_token_seconds,
            "cuda_batch_seconds": cuda_token_total,
            "cuda_detail": cuda_token_audit,
            "input_seconds": token_input_seconds,
            "max_abs_cuda_vs_cpu_kernel_difference": maximum_token_kernel_difference,
            "exact_smaller_space_solve": {
                "prediction_values_persisted": False,
                "solve_space": token_feature_solve.solve_space,
                "system_dimension": token_feature_solve.system_dimension,
                **token_feature_solve.timings,
            },
            "solve": token_solve,
            "token_batch_size": BENCHMARK_TOKEN_BATCH_SIZE,
            "tokens_per_second_cpu": BENCHMARK_TOKEN_BATCH_SIZE / cpu_token_seconds,
            "tokens_per_second_cuda": BENCHMARK_TOKEN_BATCH_SIZE / cuda_token_total,
        },
        "representation_row_count": len(scope_rows),
        "selected_kernel_device_by_runtime": selected_kernel_device,
        "subset_id": subset_id,
        "total_seconds": time.perf_counter() - benchmark_started,
        "training_row_count": train_count,
        "training_trajectory_count": len(training_ids),
        "validation_row_count": len(scope_rows) - train_count,
        "validation_trajectory_count": len(validation_ids),
    }


def solver_equivalence(access: ActivationAccess) -> dict[str, Any]:
    """Compare optimized sample-space predictions with trusted direct ridge."""

    from mineocclude.probes.ridge import fit_ridge, fit_standard_scaler

    generator = np.random.default_rng(20260810)
    matrices = {
        "global_shaped": generator.normal(size=(19, 31)),
        "multi_token": generator.normal(size=(17, 47)),
        "small_full_style": generator.normal(size=(15, 83)),
        "coarse_style": generator.normal(size=(21, 53)),
        "primal_style": generator.normal(size=(29, 7)),
    }
    extracted_rows = access.row_ordinals(["fresh_vp_v2_l01_ltr_shape_01"])[:12]
    matrices["extracted_multi_token"] = (
        access.token_rows(extracted_rows, [0, 17, 335])
        .astype(np.float64)
        .reshape(12, -1)
    )
    checks = []
    maximum = 0.0
    for name, matrix in matrices.items():
        train_count = matrix.shape[0] - 4
        training = matrix[:train_count]
        validation = matrix[train_count:]
        scope = np.concatenate([training, validation], axis=0)
        targets = generator.normal(size=train_count)
        kernel = standardized_kernel_numpy(training, scope).kernel
        smaller_space = ridge_predictions_all_alphas_from_features(
            training,
            scope,
            targets,
            alphas=ALPHAS,
            prediction_scope_positions=range(train_count, len(scope)),
        )
        for alpha in ALPHAS:
            optimized = ridge_predictions_all_alphas_from_kernel(
                kernel,
                targets,
                alphas=(alpha,),
                prediction_scope_positions=range(train_count, len(scope)),
            )[alpha]
            scaler = fit_standard_scaler(training)
            reference = np.asarray(
                fit_ridge(training, targets, alpha=alpha, scaler=scaler).predict(
                    validation
                )
            )
            difference = float(np.max(np.abs(reference - optimized)))
            smaller_difference = float(
                np.max(np.abs(reference - smaller_space.predictions_by_alpha[alpha]))
            )
            maximum = max(maximum, difference)
            maximum = max(maximum, smaller_difference)
            require(
                np.allclose(
                    reference,
                    optimized,
                    atol=EQUIVALENCE_ATOL,
                    rtol=EQUIVALENCE_RTOL,
                ),
                f"{name}: optimized ridge predictions differ",
            )
            require(
                np.allclose(
                    reference,
                    smaller_space.predictions_by_alpha[alpha],
                    atol=EQUIVALENCE_ATOL,
                    rtol=EQUIVALENCE_RTOL,
                ),
                f"{name}: smaller-space ridge predictions differ",
            )
        checks.append(
            {"case": name, "feature_count": matrix.shape[1], "status": "PASS"}
        )

    token_matrix = generator.normal(size=(14, 3, 23))
    token_training = token_matrix[:10]
    token_scope = token_matrix
    batched, _ = batched_token_kernels_numpy(token_training, token_scope)
    for token_offset in range(3):
        direct = standardized_kernel_numpy(
            token_training[:, token_offset], token_scope[:, token_offset]
        ).kernel
        require(np.array_equal(batched[token_offset], direct), "batched token mismatch")
    return {
        "alpha_grid": list(ALPHAS),
        "atol": EQUIVALENCE_ATOL,
        "checks": checks,
        "kernel_construction": "PASS",
        "maximum_absolute_prediction_difference": maximum,
        "rtol": EQUIVALENCE_RTOL,
        "standardization": "training-only population variance; constants scale to 1",
        "status": "PASS",
    }


def choose_execution_budget(benchmarks: Mapping[str, Any]) -> dict[str, Any]:
    n5 = benchmarks["n5"]
    n100 = benchmarks["n100"]
    device = n100["selected_kernel_device_by_runtime"]
    n5_token_solve = n5["ranking_token_kernel"]["exact_smaller_space_solve"][
        "total_seconds"
    ]
    n100_token_solve = n100["ranking_token_kernel"]["exact_smaller_space_solve"][
        "total_seconds"
    ]
    subset_replicates = {5: 20, 15: 16, 40: 12, 70: 8, 100: 6}
    solve_seconds_by_n = {
        size: n5_token_solve
        + (n100_token_solve - n5_token_solve) * ((size - 5) / 95) ** 3
        for size in subset_replicates
    }
    # Each subset has 20 nested ranking subfolds and five all-training ranking
    # folds. Each bounded token solve handles all four alphas together.
    ranking_seconds = sum(
        subset_replicates[size] * 25 * TOKEN_COUNT * solve_seconds_by_n[size]
        for size in subset_replicates
    )
    full_seconds_upper = (
        n100["full_style_bounded_kernel"]["estimated_five_fold_kernel_seconds"] * 62
    )
    coarse_seconds_upper = (
        sum(
            n100["coarse_grouped_alpha_cv_representative_fold"]["cuda"].get(key, 0.0)
            for key in ("scaling_seconds", "kernel_seconds")
        )
        * 5
        * 62
    )
    wide_solve_upper = (
        n100["ranking_token_kernel"]["solve"]["estimated_full_solve_seconds_cubic"]
        * 6
        * 62
    )
    total_upper = (
        ranking_seconds + full_seconds_upper + coarse_seconds_upper + wide_solve_upper
    )
    return {
        "artifact_id": "large-scale-no-wall-p8-execution-budget-v0.1",
        "bounded_parallelism": 1,
        "cache_root": str(CACHE_ROOT),
        "cache_strategy": {
            "COARSE_2x6": "retain reconstructable float32 NVMe cache",
            "FULL_TOKEN_GRID": "manifest-addressed P6 float16 shards; no full cache",
            "GLOBAL_MEAN": "reuse authoritative P6 float32 pooled shards",
            "TOKEN_INDEXED_VIEW": "bounded manifest-addressed token reads",
        },
        "conditions_for_smallest_unit_retry": [
            "cache identity mismatch: rebuild only named reconstructable cache",
            "CUDA OOM: retry only current fold with token_batch_size=1",
            "interrupted solve: retry only current subset/fold/representation",
        ],
        "device": {
            "COARSE_2x6": device,
            "FULL_TOKEN_GRID": device,
            "GLOBAL_MEAN": (
                "cuda:0"
                if sum(
                    n100["global_grouped_alpha_cv_representative_fold"]["cuda"].get(
                        key, 0.0
                    )
                    for key in ("scaling_seconds", "kernel_seconds")
                )
                <= sum(
                    n100["global_grouped_alpha_cv_representative_fold"]["cpu"].values()
                )
                else "cpu"
            ),
            "TOKEN_RANKING": "cpu_exact_smaller_space",
        },
        "expected_disk_footprint_bytes": int(COARSE_CACHE.stat().st_size),
        "expected_machine_runtime": {
            "estimated_single_machine_seconds": total_upper,
            "method": "runtime-only extrapolation; no R2 or decoding trend used",
            "ranking_exact_solve_seconds_by_training_size": {
                str(size): value for size, value in solve_seconds_by_n.items()
            },
            "note": "interpolates exact N=5/N=100 endpoints and frozen per-N replicate counts",
        },
        "feature_chunk_size": BENCHMARK_TOKEN_BATCH_SIZE * HIDDEN_WIDTH,
        "frozen_alpha_grid": list(ALPHAS),
        "frozen_before_fixed_test_outcomes": True,
        "gpu_memory_ceiling_bytes": 20 * (1 << 30),
        "host_memory_ceiling_bytes": 14 * (1 << 30),
        "numerical_computation_dtype": "float64",
        "resume_granularity": "subset_id/selection_fold/kernel_family",
        "selection_basis": ["runtime", "memory", "stability", "I/O", "cost"],
        "status": "LOCKED_FOR_P8",
        "temporary_cache_footprint_bytes": int(COARSE_CACHE.stat().st_size),
        "token_batch_size": BENCHMARK_TOKEN_BATCH_SIZE,
    }


def build_documents() -> dict[str, Any]:
    authority = verify_start_authority()
    rows, row_hash = build_canonical_rows(authority)
    access = ActivationAccess(rows)
    coarse = build_coarse_cache_and_equivalence(authority, rows, row_hash)
    representation_checks = validate_representation_views(access, coarse)
    nested = validate_nested_grouping(authority)
    budgets = validate_logical_budgets(authority)
    equivalence = solver_equivalence(access)

    print("P7 benchmark N=5 n005_r00 (training only)", flush=True)
    n5 = benchmark_subset(authority, access, "n005_r00")
    print("P7 benchmark N=100 n100_r00 (training only)", flush=True)
    n100 = benchmark_subset(authority, access, "n100_r00")
    benchmarks = {
        "artifact_id": "large-scale-no-wall-p7-solver-benchmark-v0.1",
        "benchmark_selection_basis": "predeclared subset IDs; no decoding behavior",
        "cpu_gpu_comparison_performed": True,
        "fixed_test_predictions_computed": False,
        "fixed_test_scores_opened": False,
        "fixed_test_targets_used": False,
        "n5": n5,
        "n100": n100,
        "no_scientific_r2_values_persisted": True,
        "solver_equivalence": equivalence,
        "status": "PASS_TRAINING_ONLY",
    }
    write_json(SOLVER_BENCHMARK, benchmarks)
    execution = choose_execution_budget(benchmarks)
    write_json(EXECUTION_BUDGET, execution)

    cache_manifest = {
        "artifact_id": "large-scale-no-wall-p7-cache-manifest-v0.1",
        "cache_root": str(CACHE_ROOT),
        "entries": {
            "COARSE_2x6": {
                "byte_size": coarse["byte_size"],
                "checksum": coarse["sha256"],
                "dtype": "float32",
                "durability_status": "RECONSTRUCTABLE_NVME_ONLY",
                "path": coarse["path"],
                "reconstructable": True,
                "representation_recipe_version": "coarse-2x6-contiguous-v0.1",
                "row_order": "canonical row ordinal",
                "shape": coarse["shape"],
            },
            "FULL_TOKEN_GRID": {
                "cache_materialized": False,
                "durability_status": "P6_SOURCE_AUTHORITY_ONLY",
                "reconstructable": True,
                "representation_recipe_version": "ascending-token-flatten-v0.1",
            },
            "GLOBAL_MEAN": {
                "cache_materialized": False,
                "durability_status": "P6_POOLED_AUTHORITY_REUSED",
                "reconstructable": True,
                "representation_recipe_version": "p6-global-mean-f32-v0.1",
            },
            "TOKEN_INDEXED_VIEW": {
                "cache_materialized": False,
                "durability_status": "P6_SOURCE_AUTHORITY_ONLY",
                "reconstructable": True,
                "representation_recipe_version": "indexed-token-view-v0.1",
            },
        },
        "p6_source_manifest_sha256": authority["p6_manifest_sha256"],
        "reconstructable_cache_s3_upload_skipped": True,
        "row_authority_sha256": row_hash,
        "status": "PASS",
    }
    write_json(CACHE_MANIFEST, cache_manifest)

    representation = {
        "alpha_grid": list(ALPHAS),
        "artifact_id": "large-scale-no-wall-p7-representation-authority-v0.1",
        "best_k_tokens": {
            "candidate_k": list(BEST_K),
            "feature_dimensions": {str(k): k * HIDDEN_WIDTH for k in BEST_K},
            "membership_order": "training-only rank order",
            "feature_concatenation_order": "ascending visual_token_index",
            "nested_grouping": nested,
        },
        "canonical_rows": {
            "count": len(rows),
            "identity": ["trajectory_spec_id", "model_frame_idx"],
            "path": str(CANONICAL_ROWS.relative_to(ROOT)),
            "sha256": row_hash,
        },
        "coarse_2x6": {
            "dimension": COARSE_DIM,
            "geometry": "14x24 -> contiguous [2x7] by [6x4] bins; row-major flatten",
            "validation": representation_checks["coarse_geometry"],
        },
        "fixed_test_guard": {
            "fixed_test_rows_structurally_verified": True,
            "scores_opened": False,
            "targets_used_for_benchmark": False,
            "test_authority_hash": authority["guard"]["test_authority_hash"],
        },
        "full_token_grid": {
            "dimension": FULL_DIM,
            "order": "visual_token_index 0..335; each token contributes contiguous 2048 values",
            "strategy": "bounded manifest-addressed token/feature chunks; no full cache",
            "validation": representation_checks["full_token_order"],
        },
        "global_mean": {
            "dimension": GLOBAL_DIM,
            "equivalence_max_abs_difference": coarse[
                "global_equivalence_max_abs_difference"
            ],
            "source": "P6 authoritative pooled float32 shards",
            "validation": "PASS",
        },
        "grouping_authority": str(GROUPED_FOLDS.relative_to(ROOT)),
        "kernel_formulation": "sum feature-block Z_scope @ Z_train.T; never p-by-p for FULL",
        "logical_budgets": budgets,
        "numerical_tolerance": {"atol": EQUIVALENCE_ATOL, "rtol": EQUIVALENCE_RTOL},
        "p6_source": {
            "manifest": str(P6_MANIFEST.relative_to(ROOT)),
            "sha256": authority["p6_manifest_sha256"],
        },
        "primary_cohort_version": "V2_ACCEPTED_REPAIRED_PRIMARY",
        "scaler_authority": {
            "constant_feature_scale": 1.0,
            "fit_scope": "current fold training rows only",
            "implementation": "mineocclude.probes.ridge.fit_standard_scaler",
            "variance": "population ddof=0",
        },
        "solver": {
            "implementation": "mineocclude.probes.p7_ridge",
            "implementation_sha256": sha256_file(
                ROOT / "src/mineocclude/probes/p7_ridge.py"
            ),
            "intercept": "unpenalized training-target mean",
            "objective": "literal repository ridge alpha semantics",
            "sample_space_kernel": True,
            "token_ranking_solve": (
                "exact bounded min(training_rows,2048) primal/sample system; "
                "four alphas per sufficient structure"
            ),
        },
        "status": "PASS_AUTHORITY_FROZEN",
    }
    write_json(REPRESENTATION_AUTHORITY, representation)

    artifact_paths = [
        CANONICAL_ROWS,
        REPRESENTATION_AUTHORITY,
        CACHE_MANIFEST,
        SOLVER_BENCHMARK,
        EXECUTION_BUDGET,
    ]
    receipt = {
        "artifact_id": "large-scale-no-wall-p7-receipt-v0.1",
        "artifacts": {
            str(path.relative_to(ROOT)): sha256_file(path) for path in artifact_paths
        },
        "blocker": None,
        "canonical_row_count": len(rows),
        "canonical_row_hash": row_hash,
        "fixed_test_predictions_computed": False,
        "fixed_test_scores_opened": False,
        "fixed_test_targets_used_for_benchmark": False,
        "fresh_activations_extracted": False,
        "fresh_r2_computed": False,
        "mineworld_rerun": False,
        "p6_head": P6_HEAD,
        "p8_started": False,
        "safe_for_p8": True,
        "status": "PASS_P7_REPRESENTATION_SOLVER_AUTHORITY",
        "validation": {
            "logical_budgets": budgets["status"],
            "nested_grouping": nested["status"],
            "representation_views": representation_checks,
            "solver_equivalence": equivalence["status"],
        },
    }
    write_json(P7_RECEIPT, receipt)
    return receipt


def validate_existing_documents() -> None:
    authority = verify_start_authority()
    rows = read_jsonl(CANONICAL_ROWS)
    require(len(rows) == ROW_COUNT, "canonical row artifact has wrong count")
    require(
        canonical_sha256(rows) == read_json(P7_RECEIPT)["canonical_row_hash"],
        "row hash mismatch",
    )
    require(validate_nested_grouping(authority)["status"] == "PASS", "nested grouping")
    require(validate_logical_budgets(authority)["status"] == "PASS", "logical budgets")
    for path in (
        REPRESENTATION_AUTHORITY,
        CACHE_MANIFEST,
        SOLVER_BENCHMARK,
        EXECUTION_BUDGET,
        P7_RECEIPT,
    ):
        require(path.is_file(), f"missing P7 artifact: {path.name}")
    benchmark = read_json(SOLVER_BENCHMARK)
    require(benchmark["fixed_test_scores_opened"] is False, "fixed-test score guard")
    require(benchmark["fixed_test_targets_used"] is False, "fixed-test target guard")
    require(
        not (STUDY_ROOT / "learning_curve_results.json").exists(),
        "P8 learning curve exists",
    )
    require(
        not (STUDY_ROOT / "best_k_results.json").exists(), "P8 BEST-K results exist"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    if args.validate_only:
        validate_existing_documents()
        print("PASS P7 focused authority validation")
        return 0
    receipt = build_documents()
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
