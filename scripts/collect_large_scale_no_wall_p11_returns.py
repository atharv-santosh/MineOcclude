#!/usr/bin/env python3
"""Collect and validate the exact five durable P11 shard return packages."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any, Protocol

OPERATIONAL_ROOT = Path(__file__).resolve().parents[1]
_early = argparse.ArgumentParser(add_help=False)
_early.add_argument("--scientific-root", type=Path)
_known, _unknown = _early.parse_known_args()
SCIENTIFIC_ROOT = (_known.scientific_root or OPERATIONAL_ROOT).resolve()
sys.path.insert(0, str(SCIENTIFIC_ROOT))
sys.path.insert(0, str(SCIENTIFIC_ROOT / "src"))

from mineocclude.probes import p11_sharding as authority
from scripts import run_large_scale_no_wall_p11_null as p11


def load_operational_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    require(spec is not None and spec.loader is not None, f"cannot load operational module: {path.name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class CollectionError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise CollectionError(message)


shard_runner = load_operational_module(
    "p11_operational_shard_runner", OPERATIONAL_ROOT / "scripts/run_large_scale_no_wall_p11_shard.py"
)
merge = load_operational_module(
    "p11_operational_merge", OPERATIONAL_ROOT / "scripts/validate_large_scale_no_wall_p11_merge.py"
)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


class PackageTransport(Protocol):
    def download(self, relative: str, destination: Path) -> None: ...


class S3PackageTransport:
    def __init__(self, shard: dict[str, Any]) -> None:
        self.uri = f"s3://{p11.p8.S3_BUCKET}/{str(shard['durable_output_prefix']).strip('/')}/"

    def download(self, relative: str, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["aws", "s3", "cp", f"{self.uri}{relative}", str(destination), "--only-show-errors"],
            check=True,
        )


class LocalPackageTransport:
    """Read-only fixture transport with the same relative durable layout."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def download(self, relative: str, destination: Path) -> None:
        source = self.root / relative
        require(source.is_file(), f"durable fixture object absent: {relative}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(source.read_bytes())


def validate_package_receipt(receipt: dict[str, Any], shard: dict[str, Any]) -> str:
    expected_name = f"p11_shard_{shard['worker_slug']}_return.tar.gz"
    expected_uri = (
        f"s3://{p11.p8.S3_BUCKET}/{str(shard['durable_output_prefix']).strip('/')}/"
        f"return/{expected_name}"
    )
    require(receipt.get("status") == "PASS_P11_SHARD_COMPLETE_VALIDATED", "return package is not complete")
    for key in ("worker_name", "shard_manifest_sha", "parent_p11_manifest_sha", "durable_output_prefix"):
        require(receipt.get(key) == shard.get(key), f"return receipt {key} mismatch")
    require(receipt.get("package_s3_uri") == expected_uri, "return package durable URI mismatch")
    require(Path(str(receipt.get("package_path", ""))).name == expected_name, "return package name mismatch")
    require(int(receipt.get("package_byte_count", -1)) >= 1, "return package size invalid")
    require(len(str(receipt.get("package_sha256", ""))) == 64, "return package SHA invalid")
    return expected_name


def safe_extract_return(archive_path: Path, destination: Path, shard: dict[str, Any]) -> None:
    allowed_roots = {
        "jobs",
        "shard_manifest.json",
        Path(str(shard["ledger_path"])).name,
        Path(str(shard["progress_path"])).name,
        "completion_receipt.json",
    }
    destination.mkdir(parents=True, exist_ok=False)
    seen: set[tuple[str, ...]] = set()
    with tarfile.open(archive_path, "r:gz") as archive:
        members = archive.getmembers()
        require(bool(members), "empty return archive")
        for member in members:
            pure = PurePosixPath(member.name)
            parts = pure.parts
            require(
                bool(parts) and not pure.is_absolute() and ".." not in parts and "\\" not in member.name,
                "unsafe return archive path",
            )
            normalized = tuple(part for part in parts if part not in {"", "."})
            require(normalized and normalized not in seen, "duplicate return archive member")
            seen.add(normalized)
            require(normalized[0] in allowed_roots, "foreign return archive member")
            require(member.isdir() or member.isfile(), "links/devices are forbidden in return archive")
            target = destination.joinpath(*normalized)
            require(
                os.path.commonpath((str(destination.resolve()), str(target.resolve())))
                == str(destination.resolve()),
                "return archive path traversal",
            )
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                source = archive.extractfile(member)
                require(source is not None, "return archive file unreadable")
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open("xb") as stream:
                    while block := source.read(8 << 20):
                        stream.write(block)
    observed_roots = {path.name for path in destination.iterdir()}
    require(observed_roots == allowed_roots, "return archive root set mismatch")


def validate_extracted_worker(
    root: Path, shard: dict[str, Any], parent: dict[str, Any]
) -> set[str]:
    require(read_json(root / "shard_manifest.json") == shard, "extracted shard manifest mismatch")
    ledger = root / Path(str(shard["ledger_path"])).name
    shard_runner.validate_ledger_authority(shard, parent, ledger)
    latest, counts, _attempts = shard_runner.latest_ledger(ledger)
    require(counts["VALIDATED"] == shard["expected_job_count"], "extracted shard ledger incomplete")
    require(set(latest) == set(shard["exact_original_job_ids"]), "foreign or missing ledger job")
    jobs_root = root / "jobs"
    require(jobs_root.is_dir(), "extracted jobs root absent")
    observed = {path.name for path in jobs_root.iterdir() if path.is_dir()}
    require(observed == set(shard["exact_original_job_ids"]), "foreign, missing, or duplicate extracted job")
    require(all(path.is_dir() for path in jobs_root.iterdir()), "foreign file in extracted jobs root")
    completion = read_json(root / "completion_receipt.json")
    for key in ("worker_name", "shard_manifest_sha", "parent_p11_manifest_sha"):
        require(completion.get(key) == shard.get(key), f"completion {key} mismatch")
    require(set(completion.get("job_result_sha256", {})) == observed, "completion job hash set mismatch")
    jobs = {job["job_id"]: job for job in shard_runner.assigned_jobs(shard, parent)}
    for job_id in sorted(observed):
        result_path = jobs_root / job_id / "job_result.json"
        require(
            authority.sha256_file(result_path) == completion["job_result_sha256"][job_id],
            f"completion result hash mismatch: {job_id}",
        )
        merge.validate_result_at(jobs[job_id], jobs_root / job_id)
    return observed


def collect_return_packages(
    common_path: Path,
    output_root: Path,
    *,
    local_durable_root: Path | None = None,
) -> dict[str, Any]:
    require(not output_root.exists(), "collection output already exists")
    p11.validate_manifest(require_p10_complete=True)
    parent = read_json(p11.MANIFEST)
    parent_sha = authority.sha256_file(p11.MANIFEST)
    common = read_json(common_path)
    shards = [read_json(common_path.parent / name) for name in common["shard_manifest_files"]]
    authority.validate_common(common, parent, parent_sha, shards)
    output_root.mkdir(parents=True)
    all_jobs: set[str] = set()
    worker_receipts: dict[str, Any] = {}
    with tempfile.TemporaryDirectory(prefix="p11-return-packages-", dir=output_root.parent) as temporary:
        packages = Path(temporary)
        for shard in sorted(shards, key=lambda item: item["worker_slug"]):
            slug = shard["worker_slug"]
            transport: PackageTransport = (
                LocalPackageTransport(local_durable_root / slug)
                if local_durable_root is not None else S3PackageTransport(shard)
            )
            receipt_path = packages / f"{slug}_package_upload_receipt.json"
            transport.download("return/package_upload_receipt.json", receipt_path)
            receipt = read_json(receipt_path)
            package_name = validate_package_receipt(receipt, shard)
            package_path = packages / package_name
            transport.download(f"return/{package_name}", package_path)
            require(package_path.stat().st_size == receipt["package_byte_count"], "return package size mismatch")
            require(authority.sha256_file(package_path) == receipt["package_sha256"], "return package checksum mismatch")
            worker_root = output_root / slug
            safe_extract_return(package_path, worker_root, shard)
            observed = validate_extracted_worker(worker_root, shard, parent)
            require(all_jobs.isdisjoint(observed), "duplicate job across worker packages")
            all_jobs.update(observed)
            worker_receipts[slug] = {
                "worker_name": shard["worker_name"],
                "shard_manifest_sha": shard["shard_manifest_sha"],
                "package_byte_count": receipt["package_byte_count"],
                "package_sha256": receipt["package_sha256"],
                "root": str(worker_root),
                "validated_job_count": len(observed),
            }
    expected = {job_id for shard in shards for job_id in shard["exact_original_job_ids"]}
    require(all_jobs == expected and len(all_jobs) == 184, "five return packages are not exact 184 remaining jobs")
    receipt = {
        "artifact_id": "large-scale-no-wall-p11-owner-package-collection-v0.1",
        "status": "PASS_EXACT_FIVE_ISOLATED_SHARD_ROOTS",
        "parent_p11_manifest_sha": parent_sha,
        "worker_roots": {slug: str(output_root / slug) for slug in sorted(worker_receipts)},
        "worker_packages": worker_receipts,
        "collected_worker_count": 5,
        "collected_job_count": len(all_jobs),
        "foreign_job_count": 0,
        "duplicate_job_count": 0,
    }
    shard_runner.write_json(output_root / "collection_receipt.json", receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--common-authority", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--scientific-root", type=Path)
    parser.add_argument("--local-durable-root", type=Path, help="focused-test fixture transport only")
    args = parser.parse_args()
    print(json.dumps(
        collect_return_packages(
            args.common_authority.resolve(), args.output_root.resolve(),
            local_durable_root=args.local_durable_root.resolve() if args.local_durable_root else None,
        ), indent=2, sort_keys=True,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
