"""Pure authority validation for distributed P11 whole-seed shards."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

REPRESENTATIONS = ("GLOBAL_MEAN", "FULL_TOKEN_GRID", "BEST_K_TOKENS", "COARSE_2x6")
WORKERS = (
    ("ME", "me", "SHARD_0"),
    ("ALAN", "alan", "SHARD_1"),
    ("ATHARV", "atharv", "SHARD_2"),
    ("AYMAN", "ayman", "SHARD_3"),
    ("SAHIL", "sahil", "SHARD_4"),
)

FIXED_TEST_AUTHORITY_SHA = "0adc85a5d90eb92361ba0775d58a6ccc2eb674a8ae5ffd2e816b89d9d9b48ac5"
SPLIT_AUTHORITY_SHA = "b39c81454ea18125c373fb3c777ac4c1668882c9c1ad188a7d0f20e0cab43de5"
FOLD_AUTHORITY_SHA = "597bc7b401ca691897b843fc83120cc997a414b7a946819da4c3e99768e7728e"
REPRESENTATION_AUTHORITY_SHA = "757217b2b3e54e236b4ad7b9b3574d7391f896558760a54bb1b5e457b186259e"
P6_ACTIVATION_AUTHORITY_SHA = "a57be180a9054336dbe36d2ddaddbec2859e21d5b6a42dae5b25b1c276e2d5bb"
P7_CACHE_AUTHORITY_SHA = "b031b56535b39c21630a1105b154a7b0a29ffd9f665a9fdab113ac2ca538ae5f"
P10_COARSE_AUTHORITY_SHA = "d04db26c1e05eb9d0c526d19e2c5cb813ea22332d8e507032e5ad91cad487092"
STUDY_AUTHORITY_SHA = "08d77261f70a3d7e554ce6f8fe4a565fa09591ae793a87efd60e4a742c016502"
TARGET_NULL_VERSION = "PROSPECTIVE_WITHIN_LAYOUT_TRAJECTORY_DERANGEMENT_NULL_V0_1"
TOKEN_CACHE_SHA = "2cf40e7ad1f0fe5269b16c0d7e03ff486e3ffa00379f8acea5145829bff6cf90"
COARSE_CACHE_SHA = "4a1c9562a26416eb6b069baeeb9f1c73513f7306f30a7cfe54dd30efe7094bdf"


class ShardAuthorityError(RuntimeError):
    """Raised when distributed execution does not match frozen P11 authority."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ShardAuthorityError(message)


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def frozen_json_file_sha256(value: Any) -> str:
    """Hash the repository's indented/sorted JSON serialization."""

    payload = json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def shard_sha(document: Mapping[str, Any]) -> str:
    return canonical_sha256({key: value for key, value in document.items() if key != "shard_manifest_sha"})


def common_sha(document: Mapping[str, Any]) -> str:
    return canonical_sha256({key: value for key, value in document.items() if key != "common_authority_sha"})


def jobs_by_seed(parent: Mapping[str, Any]) -> dict[int, list[Mapping[str, Any]]]:
    grouped: dict[int, list[Mapping[str, Any]]] = {}
    for job in parent["jobs"]:
        grouped.setdefault(int(job["seed_index"]), []).append(job)
    return grouped


def validate_parent(parent: Mapping[str, Any], parent_sha: str) -> dict[int, list[Mapping[str, Any]]]:
    require(parent_sha == frozen_json_file_sha256(parent), "parent P11 manifest SHA mismatch")
    require(parent.get("expected_seeds") == 49, "parent P11 B must remain 49")
    require(parent.get("expected_jobs") == 196, "parent P11 job count must remain 196")
    require(tuple(parent.get("representations", ())) == REPRESENTATIONS, "parent representations changed")
    grouped = jobs_by_seed(parent)
    require(set(grouped) == set(range(49)), "parent seed indices are not exactly 0..48")
    seen_jobs: set[str] = set()
    for seed_index, jobs in grouped.items():
        require(len(jobs) == 4, f"seed {seed_index} does not have four jobs")
        require(
            [job["representation"] for job in jobs] == list(REPRESENTATIONS),
            f"seed {seed_index} representation order/membership changed",
        )
        require(len({int(job["seed"]) for job in jobs}) == 1, f"seed {seed_index} value mismatch")
        for job in jobs:
            require(job["job_id"] not in seen_jobs, f"duplicate parent job {job['job_id']}")
            seen_jobs.add(str(job["job_id"]))
            claimed = job["identity_sha256"]
            payload = {key: value for key, value in job.items() if key != "identity_sha256"}
            require(canonical_sha256(payload) == claimed, f"parent identity mismatch {job['job_id']}")
    return grouped


def build_shards(
    parent: Mapping[str, Any],
    parent_sha: str,
    completed_seed_indices: Iterable[int],
    *,
    repository_branch: str,
    implementation_commit_sha: str,
) -> list[dict[str, Any]]:
    grouped = validate_parent(parent, parent_sha)
    completed = sorted(int(index) for index in completed_seed_indices)
    require(len(completed) == len(set(completed)), "duplicate completed seed index")
    require(set(completed) <= set(grouped), "foreign completed seed index")
    remaining = [index for index in range(49) if index not in set(completed)]
    documents: list[dict[str, Any]] = []
    base_local = (
        "/mnt/sagemaker-nvme/"
        "mineocclude_large_scale_no_wall_scaling_best_k_v0_1_v2/"
        "p11_prospective_derangement_null_v0_1/p11_shards"
    )
    base_s3 = (
        "mineocclude/exploratory_large_scale_no_wall_scaling_best_k_v0_1/"
        "p11_prospective_derangement_null_v0_1/p11_shards"
    )
    for ordinal, (worker, slug, shard_id) in enumerate(WORKERS):
        indices = remaining[ordinal::len(WORKERS)]
        jobs = [job for index in indices for job in grouped[index]]
        root = f"{base_local}/{slug}"
        document: dict[str, Any] = {
            "artifact_id": "large-scale-no-wall-p11-whole-seed-shard-v0.1",
            "worker_name": worker,
            "worker_slug": slug,
            "shard_id": shard_id,
            "parent_p11_manifest_sha": parent_sha,
            "completed_seed_indices_at_pause": completed,
            "seed_indices": indices,
            "actual_seed_values": [int(grouped[index][0]["seed"]) for index in indices],
            "expected_seed_count": len(indices),
            "expected_job_count": len(jobs),
            "exact_original_job_ids": [str(job["job_id"]) for job in jobs],
            "exact_original_job_identity_sha256": {
                str(job["job_id"]): str(job["identity_sha256"]) for job in jobs
            },
            "fixed_test_authority_sha": FIXED_TEST_AUTHORITY_SHA,
            "fixed_test_hash": str(parent["jobs"][0]["fixed_test_hash"]),
            "split_authority_sha": SPLIT_AUTHORITY_SHA,
            "fold_authority_sha": FOLD_AUTHORITY_SHA,
            "representation_authority_sha": REPRESENTATION_AUTHORITY_SHA,
            "p6_activation_authority_sha": P6_ACTIVATION_AUTHORITY_SHA,
            "p7_solver_authority_sha": P7_CACHE_AUTHORITY_SHA,
            "p10_coarse_authority_sha": str(parent["p10_manifest_sha256"]),
            "study_authority_sha": STUDY_AUTHORITY_SHA,
            "canonical_null_authority_sha": str(parent["canonical_null_authority_sha256"]),
            "prospective_null_authority_sha": str(parent["prospective_null_authority_sha256"]),
            "alpha_grid": list(parent["jobs"][0]["alpha_grid"]),
            "k_grid": next(
                list(job["best_k_grid"])
                for job in parent["jobs"]
                if job["representation"] == "BEST_K_TOKENS"
            ),
            "prospective_derangement_version": TARGET_NULL_VERSION,
            "repository_branch": repository_branch,
            "implementation_commit_sha": implementation_commit_sha,
            "local_result_root": root,
            "ledger_path": f"{root}/p11_shard_{slug}_ledger.jsonl",
            "progress_path": f"{root}/p11_shard_{slug}_progress.json",
            "log_path": f"$HOME/mineocclude_p11_shard_{slug}.log",
            "durable_output_prefix": f"{base_s3}/{slug}",
            "token_cache_sha256": TOKEN_CACHE_SHA,
            "coarse_cache_sha256": COARSE_CACHE_SHA,
            "assignment_method": "original-remaining-order-round-robin-five-workers-v0.1",
            "seed_is_atomic_unit": True,
        }
        document["shard_manifest_sha"] = shard_sha(document)
        documents.append(document)
    validate_partition(parent, parent_sha, completed, documents)
    return documents


def validate_shard(
    document: Mapping[str, Any],
    parent: Mapping[str, Any],
    parent_sha: str,
    *,
    completed_seed_indices: Iterable[int],
) -> None:
    grouped = validate_parent(parent, parent_sha)
    required = {
        "worker_name", "shard_id", "parent_p11_manifest_sha", "seed_indices",
        "actual_seed_values", "expected_seed_count", "expected_job_count",
        "exact_original_job_ids", "fixed_test_authority_sha", "split_authority_sha",
        "fold_authority_sha", "representation_authority_sha", "alpha_grid", "k_grid",
        "prospective_derangement_version", "local_result_root", "ledger_path",
        "progress_path", "log_path", "durable_output_prefix", "shard_manifest_sha",
    }
    require(required <= set(document), "shard manifest missing required fields")
    require(document["shard_manifest_sha"] == shard_sha(document), "shard manifest SHA mismatch")
    require(document["parent_p11_manifest_sha"] == parent_sha, "foreign parent manifest SHA")
    worker = next((item for item in WORKERS if item[0] == document["worker_name"]), None)
    require(worker is not None, "unknown worker name")
    require(document["worker_slug"] == worker[1] and document["shard_id"] == worker[2], "worker/shard mismatch")
    indices = [int(value) for value in document["seed_indices"]]
    require(len(indices) == len(set(indices)), "duplicate seed assignment")
    require(indices == sorted(indices), "seed indices must retain original ordering")
    require(set(indices) <= set(grouped), "unknown seed identity")
    completed = {int(value) for value in completed_seed_indices}
    require(not completed.intersection(indices), "validated completed seed assigned to shard")
    expected_values = [int(grouped[index][0]["seed"]) for index in indices]
    require(list(document["actual_seed_values"]) == expected_values, "seed values changed")
    jobs = [job for index in indices for job in grouped[index]]
    expected_ids = [str(job["job_id"]) for job in jobs]
    actual_ids = [str(value) for value in document["exact_original_job_ids"]]
    require(len(actual_ids) == len(set(actual_ids)), "duplicate job identity")
    require(actual_ids == expected_ids, "missing, foreign, or reordered representation job")
    require(document["expected_seed_count"] == len(indices), "expected seed count mismatch")
    require(document["expected_job_count"] == 4 * len(indices), "expected job count mismatch")
    require([job["representation"] for job in jobs] == list(REPRESENTATIONS) * len(indices), "missing representation")
    expected_identity = {str(job["job_id"]): str(job["identity_sha256"]) for job in jobs}
    require(document["exact_original_job_identity_sha256"] == expected_identity, "original job identity changed")
    require(document["fixed_test_authority_sha"] == FIXED_TEST_AUTHORITY_SHA, "fixed-test authority mismatch")
    require(document["split_authority_sha"] == SPLIT_AUTHORITY_SHA, "split authority mismatch")
    require(document["fold_authority_sha"] == FOLD_AUTHORITY_SHA, "fold authority mismatch")
    require(document["representation_authority_sha"] == REPRESENTATION_AUTHORITY_SHA, "representation authority mismatch")
    require(document["p6_activation_authority_sha"] == P6_ACTIVATION_AUTHORITY_SHA, "P6 authority mismatch")
    require(document["p7_solver_authority_sha"] == P7_CACHE_AUTHORITY_SHA, "P7 solver authority mismatch")
    require(document["p10_coarse_authority_sha"] == parent["p10_manifest_sha256"], "P10 COARSE authority mismatch")
    require(document["study_authority_sha"] == STUDY_AUTHORITY_SHA, "study authority mismatch")
    require(document["alpha_grid"] == parent["jobs"][0]["alpha_grid"], "alpha grid changed")
    expected_k = next(job["best_k_grid"] for job in parent["jobs"] if job["representation"] == "BEST_K_TOKENS")
    require(document["k_grid"] == expected_k, "k grid changed")
    require(document["prospective_derangement_version"] == TARGET_NULL_VERSION, "derangement version changed")
    slug = worker[1]
    require(Path(str(document["local_result_root"])).name == slug, "result root is not worker-isolated")
    require(Path(str(document["ledger_path"])).parent == Path(str(document["local_result_root"])), "ledger outside shard namespace")
    require(Path(str(document["progress_path"])).parent == Path(str(document["local_result_root"])), "progress outside shard namespace")
    require(str(document["durable_output_prefix"]).endswith(f"/{slug}"), "durable prefix is not worker-isolated")


def validate_partition(
    parent: Mapping[str, Any],
    parent_sha: str,
    completed_seed_indices: Iterable[int],
    shards: Iterable[Mapping[str, Any]],
) -> None:
    grouped = validate_parent(parent, parent_sha)
    completed = sorted(int(value) for value in completed_seed_indices)
    documents = list(shards)
    require(len(documents) == 5, "exactly five shard manifests required")
    require({doc["worker_name"] for doc in documents} == {item[0] for item in WORKERS}, "worker set mismatch")
    for document in documents:
        validate_shard(document, parent, parent_sha, completed_seed_indices=completed)
    assigned: list[int] = [int(index) for document in documents for index in document["seed_indices"]]
    require(len(assigned) == len(set(assigned)), "pairwise shard seed overlap")
    remaining = set(grouped) - set(completed)
    require(set(assigned) == remaining, "five-shard union is not exactly remaining seeds")
    require(set(completed).isdisjoint(assigned), "completed and remaining overlap")
    require(set(completed).union(assigned) == set(grouped), "completed plus shards is not frozen 49")
    sizes = [len(document["seed_indices"]) for document in documents]
    require(max(sizes, default=0) - min(sizes, default=0) <= 1, "shard sizes differ by more than one")
    ordered_remaining = [index for index in range(49) if index not in set(completed)]
    for ordinal, document in enumerate(documents):
        require(document["seed_indices"] == ordered_remaining[ordinal::5], "assignment is not frozen round-robin")
    mutable_paths = [
        (document["local_result_root"], document["ledger_path"], document["progress_path"], document["log_path"], document["durable_output_prefix"])
        for document in documents
    ]
    for field_index, label in enumerate(("result root", "ledger", "progress", "log", "durable prefix")):
        values = [paths[field_index] for paths in mutable_paths]
        require(len(values) == len(set(values)), f"shared mutable {label}")


def validate_common(
    common: Mapping[str, Any], parent: Mapping[str, Any], parent_sha: str, shards: Iterable[Mapping[str, Any]]
) -> None:
    require(common.get("common_authority_sha") == common_sha(common), "common authority SHA mismatch")
    require(common.get("parent_p11_manifest_sha") == parent_sha, "common parent SHA mismatch")
    completed = common.get("completed_seed_indices", [])
    validate_partition(parent, parent_sha, completed, shards)
    expected_shas = {str(doc["worker_slug"]): str(doc["shard_manifest_sha"]) for doc in shards}
    require(common.get("shard_manifest_shas") == expected_shas, "common shard SHA map mismatch")


def require_assigned_job(document: Mapping[str, Any], job_id: str) -> None:
    """Hard-gate internal worker dispatch to the selected immutable shard."""

    require(job_id in document["exact_original_job_ids"], "unassigned job cannot execute through shard")
