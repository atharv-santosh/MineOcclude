#!/usr/bin/env python3
"""Restore only the 12 frozen historical P11 job results from durable S3."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Protocol
from urllib.parse import urlsplit

OPERATIONAL_ROOT = Path(__file__).resolve().parents[1]
_early = argparse.ArgumentParser(add_help=False)
_early.add_argument("--scientific-root", type=Path)
_known, _unknown = _early.parse_known_args()
SCIENTIFIC_ROOT = (_known.scientific_root or OPERATIONAL_ROOT).resolve()
sys.path.insert(0, str(SCIENTIFIC_ROOT))
sys.path.insert(0, str(SCIENTIFIC_ROOT / "src"))

from mineocclude.probes import p11_sharding as authority


class SequentialRestoreError(RuntimeError):
    """Raised before accepting an ambiguous historical P11 restoration."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SequentialRestoreError(message)


def load_operational_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    require(spec is not None and spec.loader is not None, f"cannot load operational module: {path.name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


merge = load_operational_module(
    "p11_operational_sequential_restore_merge_validator",
    OPERATIONAL_ROOT / "scripts/validate_large_scale_no_wall_p11_merge.py",
)
p11 = merge.p11

HISTORICAL_SEED_INDICES = (0, 1, 2)
REPRESENTATIONS = authority.REPRESENTATIONS
JOB_FILES = frozenset({"job_result.json", "predictions.npz", "selection_evidence.json"})
EXPECTED_JOB_COUNT = len(HISTORICAL_SEED_INDICES) * len(REPRESENTATIONS)
EXPECTED_JOB_OBJECT_COUNT = EXPECTED_JOB_COUNT * len(JOB_FILES)
PAUSE_STATUS = "PASS_P11_PAUSED_CLEANLY_AT_COMPLETE_SEED_BOUNDARY"
RESTORE_STATUS = "PASS_P11_HISTORICAL_SEQUENTIAL_RESULTS_RESTORED"
RECEIPT_NAME = "sequential_restore_receipt.json"
STUDY_RELATIVE = Path(
    "docs/status/integration/exploratory_large_scale_no_wall_scaling_best_k_v0_1"
)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def is_sha256(value: Any) -> bool:
    if not isinstance(value, str) or len(value) != hashlib.sha256().digest_size * 2:
        return False
    try:
        bytes.fromhex(value)
    except ValueError:
        return False
    return True


def write_json_exclusive(path: Path, value: Any) -> None:
    with path.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(value, indent=2, sort_keys=True) + "\n")


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


class HistoricalTransport(Protocol):
    source_uri: str

    def list_keys(self, relative_prefix: str) -> list[str]: ...

    def download_file(self, relative: str, destination: Path) -> None: ...


class S3HistoricalTransport:
    """Read only the durable prefix recorded by the historical pause receipt."""

    def __init__(self, source_uri: str) -> None:
        parsed = urlsplit(source_uri)
        require(parsed.scheme == "s3" and bool(parsed.netloc), "pause receipt S3 prefix is invalid")
        require(not parsed.query and not parsed.fragment, "pause receipt S3 prefix is ambiguous")
        prefix = parsed.path.strip("/")
        require(bool(prefix), "pause receipt S3 prefix is empty")
        self.bucket = parsed.netloc
        self.prefix = prefix
        self.source_uri = f"s3://{self.bucket}/{self.prefix}/"

    def list_keys(self, relative_prefix: str) -> list[str]:
        relative_prefix = relative_prefix.lstrip("/")
        completed = subprocess.run(
            [
                "aws",
                "s3api",
                "list-objects-v2",
                "--bucket",
                self.bucket,
                "--prefix",
                f"{self.prefix}/{relative_prefix}",
                "--output",
                "json",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        document = json.loads(completed.stdout)
        require(not document.get("IsTruncated"), "durable historical listing is truncated/ambiguous")
        marker = f"{self.prefix}/"
        keys = [str(item["Key"]) for item in document.get("Contents", [])]
        require(len(keys) == len(set(keys)), "duplicate durable historical object key")
        require(all(key.startswith(marker) for key in keys), "foreign durable historical object prefix")
        return [key[len(marker) :] for key in keys]

    def download_file(self, relative: str, destination: Path) -> None:
        require(not destination.exists() and not destination.is_symlink(), "restore destination file already exists")
        destination.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [
                "aws",
                "s3",
                "cp",
                f"{self.source_uri}{relative}",
                str(destination),
                "--only-show-errors",
            ],
            check=True,
        )


def validate_authorities(
    pause_receipt_path: Path, common_authority_path: Path
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], str, list[dict[str, Any]]]:
    pause = read_json(pause_receipt_path)
    common = read_json(common_authority_path)
    parent = p11.validate_manifest(require_p10_complete=True)
    parent_sha = authority.sha256_file(p11.MANIFEST)
    shard_documents = [
        read_json(common_authority_path.parent / name)
        for name in common.get("shard_manifest_files", [])
    ]
    authority.validate_common(common, parent, parent_sha, shard_documents)

    require(
        pause.get("artifact_id") == "large-scale-no-wall-p11-clean-pause-v0.1",
        "foreign historical pause receipt",
    )
    require(pause.get("status") == PAUSE_STATUS, "historical pause receipt status mismatch")
    require(pause.get("durable_checkpoint_verified") is True, "historical durable checkpoint is unverified")
    require(pause.get("partial_seed_present") is False, "historical pause contains a partial seed")
    require(pause.get("parent_p11_manifest_sha") == parent_sha, "historical parent authority mismatch")
    require(common.get("parent_p11_manifest_sha") == parent_sha, "common parent authority mismatch")
    require(
        pause.get("implementation_commit_sha") == common.get("implementation_commit_sha"),
        "historical implementation authority mismatch",
    )
    require(
        tuple(pause.get("completed_seed_indices", ())) == HISTORICAL_SEED_INDICES,
        "historical completed seeds are not exactly 0,1,2",
    )
    require(
        tuple(common.get("completed_seed_indices", ())) == HISTORICAL_SEED_INDICES,
        "common completed seeds are not exactly 0,1,2",
    )
    require(pause.get("validated_seed_count") == 3, "historical validated seed count mismatch")
    require(pause.get("validated_job_count") == EXPECTED_JOB_COUNT, "historical validated job count mismatch")
    durable_check = pause.get("s3_downloaded_hash_verification", {})
    require(durable_check.get("status") == "PASS", "historical S3 verification did not pass")
    require(
        tuple(durable_check.get("seed_indices", ())) == HISTORICAL_SEED_INDICES,
        "historical S3 verification seed set mismatch",
    )
    require(durable_check.get("object_count") == EXPECTED_JOB_OBJECT_COUNT + 4, "historical durable object count mismatch")
    require(parent.get("canonical_subset_id") == "n100_r00", "historical canonical N=100 authority changed")
    require(tuple(parent.get("representations", ())) == REPRESENTATIONS, "historical representations changed")

    jobs = [job for job in parent["jobs"] if int(job["seed_index"]) in HISTORICAL_SEED_INDICES]
    require(len(jobs) == EXPECTED_JOB_COUNT, "historical parent job count mismatch")
    grouped: dict[int, list[dict[str, Any]]] = {}
    for job in jobs:
        grouped.setdefault(int(job["seed_index"]), []).append(job)
        require(job.get("canonical_subset_id") == "n100_r00", "historical job is not canonical N=100")
    require(set(grouped) == set(HISTORICAL_SEED_INDICES), "historical parent seed set mismatch")
    for seed_index in HISTORICAL_SEED_INDICES:
        require(
            tuple(job["representation"] for job in grouped[seed_index]) == REPRESENTATIONS,
            f"historical seed {seed_index} representation set/order mismatch",
        )
    expected_seed_values = [int(grouped[index][0]["seed"]) for index in HISTORICAL_SEED_INDICES]
    require(
        pause.get("completed_seed_values") == expected_seed_values,
        "historical pause seed values mismatch",
    )
    require(
        common.get("completed_seed_values") == expected_seed_values,
        "common historical seed values mismatch",
    )
    expected_ids = {str(job["job_id"]) for job in jobs}
    expected_hashes = pause.get("job_result_sha256", {})
    require(isinstance(expected_hashes, dict), "historical job-result hash authority is invalid")
    require(set(expected_hashes) == expected_ids, "historical job-result hash set mismatch")
    require(
        all(is_sha256(value) for value in expected_hashes.values()),
        "historical job-result SHA is invalid",
    )
    source_uri = pause.get("s3_prefix")
    require(isinstance(source_uri, str) and bool(source_uri), "historical durable source prefix absent")
    return pause, common, parent, parent_sha, jobs


def inspect_job_keys(keys: list[str], expected_job_ids: set[str]) -> list[str]:
    require(len(keys) == len(set(keys)), "duplicate durable historical object key")
    observed: dict[str, set[str]] = {}
    normalized_keys: list[str] = []
    for key in keys:
        pure = PurePosixPath(key)
        parts = pure.parts
        require(
            bool(parts) and not pure.is_absolute() and ".." not in parts and "\\" not in key,
            "unsafe durable historical object path",
        )
        normalized = tuple(part for part in parts if part not in {"", "."})
        require(len(normalized) == 3 and normalized[0] == "jobs", "foreign durable historical object path")
        job_id, filename = normalized[1], normalized[2]
        require(job_id in expected_job_ids, f"foreign historical job: {job_id}")
        require(filename in JOB_FILES, f"foreign historical job artifact: {filename}")
        require(filename not in observed.setdefault(job_id, set()), f"duplicate historical job artifact: {key}")
        observed[job_id].add(filename)
        normalized_keys.append("/".join(normalized))
    require(set(observed) == expected_job_ids, "missing or foreign historical job directory")
    require(
        all(filenames == JOB_FILES for filenames in observed.values()),
        "historical job artifact set mismatch",
    )
    require(len(normalized_keys) == EXPECTED_JOB_OBJECT_COUNT, "historical job object count mismatch")
    return sorted(normalized_keys)


def validate_local_structure(output_root: Path, expected_job_ids: set[str]) -> None:
    jobs_root = output_root / "jobs"
    require(jobs_root.is_dir(), "restored historical jobs root absent")
    entries = list(jobs_root.iterdir())
    require(all(path.is_dir() and not path.is_symlink() for path in entries), "foreign file in historical jobs root")
    require({path.name for path in entries} == expected_job_ids, "missing or foreign restored job directory")
    for job_id in expected_job_ids:
        artifacts = list((jobs_root / job_id).iterdir())
        require(all(path.is_file() and not path.is_symlink() for path in artifacts), "foreign restored job artifact type")
        require({path.name for path in artifacts} == JOB_FILES, f"restored artifact set mismatch: {job_id}")


def validate_result_identity(job: Mapping[str, Any], result: Mapping[str, Any]) -> None:
    require(result.get("artifact_id") == "large-scale-no-wall-p11-null-job-v0.1", "historical result schema mismatch")
    require(result.get("status") == "VALIDATED", "historical result is not validated")
    require(result.get("job_id") == job["job_id"], "historical result job identity mismatch")
    require(result.get("identity_sha256") == job["identity_sha256"], "historical result frozen identity mismatch")
    require(result.get("seed_index") == job["seed_index"], "historical result seed index mismatch")
    require(result.get("seed") == job["seed"], "historical result seed value mismatch")
    require(result.get("representation") == job["representation"], "historical result representation mismatch")
    require(result.get("fixed_test_hash") == job["fixed_test_hash"], "historical result fixed-test authority mismatch")


def safe_output_root(output_root: Path) -> Path:
    resolved = output_root.expanduser().resolve(strict=False)
    require(not resolved.exists() and not resolved.is_symlink(), "output root already exists; use a new empty root")
    forbidden = {
        (OPERATIONAL_ROOT / STUDY_RELATIVE).resolve(),
        Path(p11.STUDY_ROOT).resolve(),
    }
    require(
        all(resolved != root and root not in resolved.parents for root in forbidden),
        "output root cannot be inside the Git experimental artifact directory",
    )
    require(resolved != resolved.parent, "unsafe output root")
    return resolved


def restore_sequential_results(
    pause_receipt_path: Path,
    common_authority_path: Path,
    output_root: Path,
    *,
    transport: HistoricalTransport | None = None,
    result_validator: Callable[[Mapping[str, Any], Path], Any] | None = None,
    timestamp: str | None = None,
) -> dict[str, Any]:
    pause_receipt_path = pause_receipt_path.resolve()
    common_authority_path = common_authority_path.resolve()
    require(pause_receipt_path.is_file(), "pause receipt absent")
    require(common_authority_path.is_file(), "common authority absent")
    output_root = safe_output_root(output_root)
    pause, common, _parent, parent_sha, jobs = validate_authorities(
        pause_receipt_path, common_authority_path
    )
    source_uri = str(pause["s3_prefix"])
    authoritative_transport = S3HistoricalTransport(source_uri)
    if transport is None:
        transport = authoritative_transport
    require(
        transport.source_uri.rstrip("/") == authoritative_transport.source_uri.rstrip("/"),
        "transport source differs from pause authority",
    )
    result_validator = result_validator or merge.validate_result_at

    expected_job_ids = {str(job["job_id"]) for job in jobs}
    keys = inspect_job_keys(transport.list_keys("jobs/"), expected_job_ids)
    output_root.parent.mkdir(parents=True, exist_ok=True)
    output_root.mkdir(exist_ok=False)
    for relative in keys:
        target = output_root.joinpath(*PurePosixPath(relative).parts)
        require(
            os.path.commonpath((str(output_root), str(target.resolve(strict=False)))) == str(output_root),
            "historical restore path traversal",
        )
        transport.download_file(relative, target)
    validate_local_structure(output_root, expected_job_ids)

    expected_hashes = {str(key): str(value) for key, value in pause["job_result_sha256"].items()}
    observed_hashes: dict[str, str] = {}
    for job in jobs:
        job_id = str(job["job_id"])
        job_root = output_root / "jobs" / job_id
        result_path = job_root / "job_result.json"
        observed_hash = authority.sha256_file(result_path)
        observed_hashes[job_id] = observed_hash
        require(observed_hash == expected_hashes[job_id], f"historical job-result SHA mismatch: {job_id}")
        validate_result_identity(job, read_json(result_path))
        result_validator(job, job_root)

    receipt = {
        "artifact_id": "large-scale-no-wall-p11-historical-sequential-restore-v0.1",
        "canonical_subset_id": "n100_r00",
        "common_authority_path": str(common_authority_path),
        "common_authority_sha": common["common_authority_sha"],
        "duplicate_job_count": 0,
        "expected_job_count": EXPECTED_JOB_COUNT,
        "expected_job_ids": [str(job["job_id"]) for job in jobs],
        "expected_job_result_sha256": expected_hashes,
        "foreign_job_count": 0,
        "missing_job_count": 0,
        "observed_job_result_sha256": observed_hashes,
        "output_root": str(output_root),
        "parent_p11_manifest_sha": parent_sha,
        "representations": list(REPRESENTATIONS),
        "restored_at": timestamp or now_utc(),
        "restored_job_count": len(observed_hashes),
        "seeds": list(HISTORICAL_SEED_INDICES),
        "source_durable_prefix": source_uri,
        "source_job_object_count": len(keys),
        "source_pause_receipt_path": str(pause_receipt_path),
        "source_pause_receipt_sha256": authority.sha256_file(pause_receipt_path),
        "status": RESTORE_STATUS,
        "validation_status": "PASS_EXISTING_FROZEN_RESULT_VALIDATION",
    }
    write_json_exclusive(output_root / RECEIPT_NAME, receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scientific-root", required=True, type=Path)
    parser.add_argument("--pause-receipt", required=True, type=Path)
    parser.add_argument("--common-authority", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    args = parser.parse_args()
    require(args.scientific_root.resolve() == SCIENTIFIC_ROOT, "scientific root argument changed during import")
    receipt = restore_sequential_results(
        args.pause_receipt, args.common_authority, args.output_root
    )
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
