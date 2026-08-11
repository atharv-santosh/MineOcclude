#!/usr/bin/env python3
"""Hard-gate the final sequential-plus-five-shard P11 merge before aggregation."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import numpy as np

from mineocclude.probes import p11_sharding as authority
from mineocclude.probes.p8_core import canonical_sha256, metric_document, rank_tokens
from scripts import run_large_scale_no_wall_p11_null as p11


class MergeValidationError(RuntimeError):
    """Raised before any aggregation when five-way merge authority is invalid."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise MergeValidationError(message)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_roots(values: list[str]) -> dict[str, Path]:
    roots: dict[str, Path] = {}
    for value in values:
        slug, separator, path = value.partition("=")
        require(bool(separator) and bool(slug) and bool(path), "--shard-result must be worker_slug=/result/root")
        require(slug not in roots, f"duplicate shard result root: {slug}")
        roots[slug] = Path(path)
    return roots


def artifact_path(job_directory: Path, artifact: Mapping[str, Any]) -> Path:
    claimed = Path(str(artifact["path"]))
    require(claimed.name in {"predictions.npz", "selection_evidence.json"}, "foreign artifact name")
    return job_directory / claimed.name


def validate_result_at(job: Mapping[str, Any], job_directory: Path) -> tuple[dict[str, Any], Path]:
    result_path = job_directory / "job_result.json"
    require(result_path.is_file(), f"missing result {job['job_id']}")
    result = read_json(result_path)
    require(result.get("status") == "VALIDATED", f"invalid status {job['job_id']}")
    require(result.get("job_id") == job["job_id"], "foreign job result")
    require(result.get("identity_sha256") == job["identity_sha256"], "job identity mismatch")
    require(result.get("assignment_sha256") == job["assignment_sha256"], "assignment authority mismatch")
    require(result.get("seed") == job["seed"] and result.get("seed_index") == job["seed_index"], "seed authority mismatch")
    require(result.get("representation") == job["representation"], "representation mismatch")
    require(result.get("fixed_test_hash") == job["fixed_test_hash"], "fixed-test authority mismatch")
    require(result.get("fixed_test_labels_true_and_untouched") is True, "fixed-test labels changed")
    require(result.get("target_null_version") == authority.TARGET_NULL_VERSION, "target-null version mismatch")
    require(result.get("no_self_donor") is True, "self donor permitted")
    require(result.get("temporal_order_and_frame_alignment_preserved") is True, "temporal/frame authority changed")
    provenance = result.get("selection_provenance", {})
    require(provenance.get("test_used_for_selection") is False, "test selection leakage")
    require(provenance.get("alpha_repeated_under_null_training_only") is True, "alpha not selected under null training")
    require(provenance.get("scaler_repeated_under_null_training_only") is True, "scaler not fit under null training")
    p11.assignment_for_job(dict(job))
    require(result.get("selected_alpha") in p11.p8.ALPHAS, "foreign alpha")
    for key in ("prediction_artifact", "selection_artifact"):
        artifact = result[key]
        path = artifact_path(job_directory, artifact)
        require(path.is_file(), f"missing {key} {job['job_id']}")
        require(path.stat().st_size == artifact["byte_count"], f"{key} byte count mismatch")
        require(authority.sha256_file(path) == artifact["sha256"], f"{key} SHA mismatch")
    prediction_path = artifact_path(job_directory, result["prediction_artifact"])
    prediction = np.load(prediction_path, allow_pickle=False)
    require(prediction["predictions"].shape == (1080,), "prediction shape mismatch")
    require(np.isfinite(prediction["predictions"]).all(), "non-finite predictions")
    if job["representation"] == "BEST_K_TOKENS":
        require(provenance.get("best_k_repeated_under_null_training_only") is True, "BEST-K not reselected under null")
        require(provenance.get("token_ranking_repeated_under_null_training_only") is True, "ranking not repeated under null")
        require(result.get("selected_k") in p11.p8.K_GRID, "foreign selected k")
        evidence = read_json(artifact_path(job_directory, result["selection_artifact"]))
        ranking = evidence["final_ranking_evidence"]["ranking"]
        require(tuple(ranking) == rank_tokens(evidence["final_ranking_evidence"]["score_records"]), "BEST-K ranking provenance mismatch")
        require(result["selected_token_indices"] == sorted(ranking[: result["selected_k"]]), "BEST-K final tokens mismatch")
    return result, prediction_path


def validate_merge(
    common_path: Path, sequential_root: Path, shard_roots: Mapping[str, Path]
) -> dict[str, Any]:
    p11.validate_manifest(require_p10_complete=True)
    parent = read_json(p11.MANIFEST)
    parent_sha = authority.sha256_file(p11.MANIFEST)
    common = read_json(common_path)
    shard_documents = [read_json(common_path.parent / name) for name in common["shard_manifest_files"]]
    authority.validate_common(common, parent, parent_sha, shard_documents)
    expected_slugs = {document["worker_slug"] for document in shard_documents}
    require(set(shard_roots) == expected_slugs, "exactly five named shard result roots required")
    completed = {int(value) for value in common["completed_seed_indices"]}
    assignment: dict[str, tuple[str, Path]] = {}
    for job in parent["jobs"]:
        if int(job["seed_index"]) in completed:
            assignment[job["job_id"]] = ("sequential", sequential_root)
    for document in shard_documents:
        slug = document["worker_slug"]
        for job_id in document["exact_original_job_ids"]:
            require(job_id not in assignment, f"duplicate representation job assignment {job_id}")
            assignment[job_id] = (slug, shard_roots[slug])
    expected_jobs = {job["job_id"] for job in parent["jobs"]}
    require(set(assignment) == expected_jobs and len(assignment) == 196, "merge assignment is not exact 196 jobs")
    allowed_by_source: dict[str, set[str]] = {"sequential": set()}
    for slug in expected_slugs:
        allowed_by_source[slug] = set()
    for job_id, (source, _root) in assignment.items():
        allowed_by_source[source].add(job_id)
    roots = {"sequential": sequential_root, **shard_roots}
    for source, root in roots.items():
        jobs_root = root / "jobs"
        require(jobs_root.is_dir(), f"missing jobs directory for {source}")
        observed = {path.name for path in jobs_root.iterdir() if path.is_dir()}
        require(observed == allowed_by_source[source], f"missing or foreign job directory for {source}")
    context = p11.p8.JobContext()
    test_ids = list(context.test_ids)
    true_targets = context.true_targets(test_ids)
    expected_rows = np.asarray(context.access.row_ordinals(test_ids), dtype=np.int64)
    validated_results: dict[str, str] = {}
    seed_representations: dict[int, set[str]] = {}
    for job in parent["jobs"]:
        source, root = assignment[job["job_id"]]
        result, prediction_path = validate_result_at(job, root / "jobs" / job["job_id"])
        prediction = np.load(prediction_path, allow_pickle=False)
        require(np.array_equal(prediction["row_ordinals"], expected_rows), "fixed-test row authority mismatch")
        metrics = metric_document(true_targets, prediction["predictions"], test_ids, context.layouts(test_ids))
        require(canonical_sha256(metrics) == canonical_sha256(result["metrics"]), "metric recomputation mismatch")
        validated_results[job["job_id"]] = source
        seed_representations.setdefault(int(job["seed_index"]), set()).add(str(job["representation"]))
    require(len(validated_results) == 196, "not all 196 jobs validated")
    require(set(seed_representations) == set(range(49)), "not all 49 original seeds validated")
    require(all(reps == set(authority.REPRESENTATIONS) for reps in seed_representations.values()), "seed missing representation")
    return {
        "artifact_id": "large-scale-no-wall-p11-five-way-merge-validation-v0.1",
        "status": "PASS_49_SEEDS_196_JOBS_SAFE_FOR_CANONICAL_AGGREGATION",
        "parent_p11_manifest_sha": parent_sha,
        "validated_seed_count": 49,
        "validated_job_count": 196,
        "representations_per_seed": 4,
        "missing_seed_count": 0,
        "duplicate_seed_count": 0,
        "foreign_seed_count": 0,
        "missing_job_count": 0,
        "duplicate_job_count": 0,
        "foreign_job_count": 0,
        "aggregation_performed": False,
        "future_canonical_p_formula": "(1 + count(null >= observed)) / (49 + 1)",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--common-authority", required=True, type=Path)
    parser.add_argument("--sequential-result-root", required=True, type=Path)
    parser.add_argument("--shard-result", action="append", default=[])
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    require(args.validate_only, "only the pre-aggregation --validate-only action is authorized")
    receipt = validate_merge(args.common_authority, args.sequential_result_root, parse_roots(args.shard_result))
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
