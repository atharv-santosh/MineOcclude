#!/usr/bin/env python3
"""Hard-gate the final sequential-plus-five-shard P11 merge before aggregation."""

from __future__ import annotations

import argparse
import gzip
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

OPERATIONAL_ROOT = Path(__file__).resolve().parents[1]
_early = argparse.ArgumentParser(add_help=False)
_early.add_argument("--scientific-root", type=Path)
_known, _unknown = _early.parse_known_args()
ROOT = (_known.scientific_root or OPERATIONAL_ROOT).resolve()
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


def validate_merge_with_results(
    common_path: Path, sequential_root: Path, shard_roots: Mapping[str, Path]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
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
    true_targets = context.targets(test_ids)
    expected_rows = np.asarray(context.access.row_ordinals(test_ids), dtype=np.int64)
    validated_results: dict[str, str] = {}
    ordered_results: list[dict[str, Any]] = []
    seed_representations: dict[int, set[str]] = {}
    for job in parent["jobs"]:
        source, root = assignment[job["job_id"]]
        result, prediction_path = validate_result_at(job, root / "jobs" / job["job_id"])
        prediction = np.load(prediction_path, allow_pickle=False)
        require(np.array_equal(prediction["row_ordinals"], expected_rows), "fixed-test row authority mismatch")
        metrics = metric_document(true_targets, prediction["predictions"], test_ids, context.layouts(test_ids))
        require(canonical_sha256(metrics) == canonical_sha256(result["metrics"]), "metric recomputation mismatch")
        validated_results[job["job_id"]] = source
        ordered_results.append(result)
        seed_representations.setdefault(int(job["seed_index"]), set()).add(str(job["representation"]))
    require(len(validated_results) == 196, "not all 196 jobs validated")
    require(set(seed_representations) == set(range(49)), "not all 49 original seeds validated")
    require(all(reps == set(authority.REPRESENTATIONS) for reps in seed_representations.values()), "seed missing representation")
    receipt = {
        "artifact_id": "large-scale-no-wall-p11-five-way-merge-validation-v0.1",
        "status": "PASS_49_SEEDS_196_JOBS_SAFE_FOR_CANONICAL_AGGREGATION",
        "parent_p11_manifest_sha": parent_sha,
        "validated_seed_count": 49,
        "validated_job_count": 196,
        "representations_per_seed": 4,
        "missing_seed_count": 0,
        "extra_seed_count": 0,
        "duplicate_seed_count": 0,
        "foreign_seed_count": 0,
        "partial_seed_count": 0,
        "missing_job_count": 0,
        "extra_job_count": 0,
        "duplicate_job_count": 0,
        "foreign_job_count": 0,
        "aggregation_performed": False,
        "future_canonical_p_formula": "(1 + count(null >= observed)) / (49 + 1)",
    }
    return receipt, ordered_results


def validate_merge(
    common_path: Path, sequential_root: Path, shard_roots: Mapping[str, Path]
) -> dict[str, Any]:
    return validate_merge_with_results(common_path, sequential_root, shard_roots)[0]


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def deterministic_package(paths: list[Path], destination: Path) -> None:
    with destination.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0, compresslevel=6) as compressed:
            with tarfile.open(fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT) as archive:
                for path in sorted(paths, key=lambda item: item.name):
                    data = path.read_bytes()
                    info = tarfile.TarInfo(path.name)
                    info.size = len(data)
                    info.mtime = 0
                    info.mode = 0o644
                    info.uid = info.gid = 0
                    info.uname = info.gname = ""
                    archive.addfile(info, fileobj=io.BytesIO(data))


def durable_artifact_uri(base: str, name: str) -> str:
    return f"{base.rstrip('/')}/{name}"


def publish(path: Path, uri: str) -> None:
    if uri.startswith("s3://"):
        subprocess.run(
            ["aws", "s3", "cp", str(path), uri, "--checksum-algorithm", "SHA256", "--only-show-errors"],
            check=True,
        )
        return
    require(uri.startswith("file://"), "durable output URI must be s3:// or file://")
    destination = Path(uri.removeprefix("file://"))
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, destination)


def require_exact_merge_gate(receipt: Mapping[str, Any]) -> None:
    require(receipt.get("status") == "PASS_49_SEEDS_196_JOBS_SAFE_FOR_CANONICAL_AGGREGATION", "five-root gate did not pass")
    require(receipt.get("validated_seed_count") == 49, "five-root gate is not B=49")
    require(receipt.get("validated_job_count") == 196, "five-root gate is not 196 jobs")
    require(receipt.get("representations_per_seed") == 4, "five-root gate representation count changed")
    for key in (
        "missing_seed_count", "extra_seed_count", "duplicate_seed_count", "foreign_seed_count",
        "partial_seed_count", "missing_job_count", "extra_job_count",
        "duplicate_job_count", "foreign_job_count",
    ):
        require(receipt.get(key) == 0, f"five-root gate {key} is nonzero")
    require(receipt.get("aggregation_performed") is False, "merge gate must precede aggregation")
    require(
        receipt.get("future_canonical_p_formula") == "(1 + count(null >= observed)) / (49 + 1)",
        "frozen empirical p-value formula changed",
    )


def aggregate_distributed(
    common_path: Path,
    sequential_root: Path,
    shard_roots: Mapping[str, Path],
    output_root: Path,
    durable_output_uri: str,
) -> dict[str, Any]:
    require(not output_root.exists(), "canonical aggregation output already exists")
    merge_receipt, results = validate_merge_with_results(common_path, sequential_root, shard_roots)
    require_exact_merge_gate(merge_receipt)
    require(len(results) == 196, "canonical result input count changed")
    output_root.mkdir(parents=True)
    merge_path = output_root / "five_root_merge_validation_receipt.json"
    result_path = output_root / "prospective_target_null_results.json"
    aggregation_path = output_root / "canonical_distributed_aggregation_receipt.json"
    write_json(merge_path, merge_receipt)
    document = p11.build_result(results)
    require(document.get("null_replicates") == 49, "canonical aggregation B changed")
    require(
        document.get("empirical_upper_tail_formula") == "(1 + count(null >= observed)) / (49 + 1)",
        "canonical aggregation formula changed",
    )
    write_json(result_path, document)
    aggregation_receipt = {
        "artifact_id": "large-scale-no-wall-p11-canonical-distributed-aggregation-v0.1",
        "status": "PASS_CANONICAL_DISTRIBUTED_AGGREGATION_B49",
        "parent_p11_manifest_sha": merge_receipt["parent_p11_manifest_sha"],
        "five_root_validation_receipt_sha256": authority.sha256_file(merge_path),
        "prospective_null_results_sha256": authority.sha256_file(result_path),
        "validated_seed_count": 49,
        "validated_job_count": 196,
        "missing_job_count": 0,
        "extra_job_count": 0,
        "duplicate_job_count": 0,
        "foreign_job_count": 0,
        "partial_seed_count": 0,
        "null_replicates": 49,
        "empirical_upper_tail_formula": "(1 + count(null >= observed)) / (49 + 1)",
        "aggregation_implementation": "frozen scripts.run_large_scale_no_wall_p11_null.build_result",
        "scientific_interpretation_performed": False,
    }
    write_json(aggregation_path, aggregation_receipt)
    package_path = output_root / "p11_canonical_distributed_aggregation.tar.gz"
    deterministic_package([merge_path, result_path, aggregation_path], package_path)
    package_uri = durable_artifact_uri(durable_output_uri, package_path.name)
    receipt_uri = durable_artifact_uri(durable_output_uri, "canonical_distributed_package_receipt.json")
    package_receipt = {
        **aggregation_receipt,
        "artifact_id": "large-scale-no-wall-p11-canonical-distributed-package-v0.1",
        "status": "PASS_CANONICAL_DISTRIBUTED_PACKAGE_DURABLE",
        "package_byte_count": package_path.stat().st_size,
        "package_sha256": authority.sha256_file(package_path),
        "package_uri": package_uri,
        "receipt_uri": receipt_uri,
    }
    package_receipt_path = output_root / "canonical_distributed_package_receipt.json"
    write_json(package_receipt_path, package_receipt)
    publish(package_path, package_uri)
    publish(package_receipt_path, receipt_uri)
    return package_receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--common-authority", required=True, type=Path)
    parser.add_argument("--sequential-result-root", required=True, type=Path)
    parser.add_argument("--scientific-root", type=Path)
    parser.add_argument("--shard-result", action="append", default=[])
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--aggregate", action="store_true")
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--durable-output-uri")
    args = parser.parse_args()
    require(args.validate_only != args.aggregate, "choose exactly one merge action")
    roots = parse_roots(args.shard_result)
    if args.validate_only:
        require(args.output_root is None and args.durable_output_uri is None, "validation does not write aggregate output")
        receipt = validate_merge(args.common_authority, args.sequential_result_root, roots)
    else:
        require(args.output_root is not None and bool(args.durable_output_uri), "aggregation requires output root and durable URI")
        receipt = aggregate_distributed(
            args.common_authority, args.sequential_result_root, roots,
            args.output_root, args.durable_output_uri,
        )
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
