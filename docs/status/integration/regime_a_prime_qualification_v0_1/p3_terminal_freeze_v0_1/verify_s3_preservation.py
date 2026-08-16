#!/usr/bin/env python3
"""Verify the non-destructive P3 historical S3 preservation copy.

This script lists source and backup objects, compares object-level coverage,
checks manifest/ledger identities, and writes a compact receipt.  It does not
create, modify, move, or delete S3 objects.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import boto3


REPO = Path(__file__).resolve().parents[5]
OUT = REPO / "docs/status/integration/regime_a_prime_qualification_v0_1"
SOURCE_URI = (
    "s3://sagemaker-us-east-1-323206973672/mineocclude/"
    "regime_a_prime_qualification_v0_1/p3_sequential_development_v0_1/"
)
BACKUP_URI = (
    "s3://sagemaker-us-east-1-323206973672/mineocclude/historical_preservation/"
    "regime_a_prime_qualification_v0_1/p3_terminal_preservation_2026-08-15/"
)
BASELINE_SOURCE_OBJECTS = 32844
BASELINE_SOURCE_BYTES = 2455084221


def utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def split_uri(uri: str) -> tuple[str, str]:
    parsed = urlparse(uri)
    if parsed.scheme != "s3" or not parsed.netloc:
        raise ValueError(uri)
    return parsed.netloc, parsed.path.lstrip("/")


def list_prefix(client, uri: str) -> dict[str, tuple[int, str]]:
    bucket, prefix = split_uri(uri)
    result: dict[str, tuple[int, str]] = {}
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for item in page.get("Contents", []):
            relative = item["Key"][len(prefix):]
            if relative in result:
                raise RuntimeError(f"duplicate S3 key: {relative}")
            result[relative] = (int(item["Size"]), item["ETag"].strip('"'))
    return result


def coverage_digest(objects: dict[str, tuple[int, str]], include_etag: bool) -> str:
    digest = hashlib.sha256()
    for key, (size, etag) in sorted(objects.items()):
        fields = [key, str(size)]
        if include_etag:
            fields.append(etag)
        digest.update("\0".join(fields).encode("utf-8") + b"\n")
    return digest.hexdigest()


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def get_bytes(client, uri: str, relative: str) -> bytes:
    bucket, prefix = split_uri(uri)
    return client.get_object(Bucket=bucket, Key=prefix + relative)["Body"].read()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    s3 = boto3.client("s3")
    sts = boto3.client("sts")
    source = list_prefix(s3, SOURCE_URI)
    backup = list_prefix(s3, BACKUP_URI)
    manifest = json.loads((OUT / "p3_development_manifest.json").read_text())

    ledger_by_identity = {}
    for path in sorted(OUT.glob("p3_p3dev_c0*_ledger.jsonl")):
        for row in read_jsonl(path):
            if row["identity"] in ledger_by_identity:
                raise RuntimeError(f"duplicate ledger identity: {row['identity']}")
            ledger_by_identity[row["identity"]] = row

    expected_capture: dict[str, set[str]] = defaultdict(set)
    expected_calibration: dict[str, set[str]] = defaultdict(set)
    expected_scene: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for candidate in manifest["candidates"]:
        cid = candidate["candidate_id"]
        for spec in candidate["specs"]:
            for scene, binding in spec["paired_runs"].items():
                expected_capture[cid].add(binding["run_id"])
                expected_scene[cid][scene] += 1
        for spec in candidate["visibility_calibration_specs"]:
            expected_calibration[cid].add(spec["calibration_id"])

    actual_capture: dict[str, set[str]] = defaultdict(set)
    actual_calibration: dict[str, set[str]] = defaultdict(set)
    per_candidate_objects: dict[str, int] = defaultdict(int)
    per_candidate_bytes: dict[str, int] = defaultdict(int)
    for relative, (size, _) in source.items():
        parts = relative.split("/")
        if len(parts) < 4:
            raise RuntimeError(f"unexpected source key structure: {relative}")
        cid, stage, identity = parts[:3]
        per_candidate_objects[cid] += 1
        per_candidate_bytes[cid] += size
        if stage == "capture":
            actual_capture[cid].add(identity)
        elif stage == "calibration":
            actual_calibration[cid].add(identity)
        else:
            raise RuntimeError(f"unexpected source stage: {relative}")

    unit_manifest_checks = []
    raw_entries_checked = 0
    for cid in sorted(expected_capture):
        for stage, identities in (
            ("capture", expected_capture[cid]),
            ("calibration", expected_calibration[cid]),
        ):
            for identity in sorted(identities):
                relative = f"{cid}/{stage}/{identity}/sha256_manifest.json"
                source_body = get_bytes(s3, SOURCE_URI, relative)
                backup_body = get_bytes(s3, BACKUP_URI, relative)
                body_sha256 = hashlib.sha256(source_body).hexdigest()
                row = ledger_by_identity[identity]
                parsed = json.loads(source_body)
                entry_checks = []
                for entry in parsed["files"]:
                    object_relative = f"{cid}/{stage}/{identity}/{entry['path']}"
                    present = object_relative in source and object_relative in backup
                    size_matches = present and source[object_relative][0] == entry["byte_size"]
                    entry_checks.append(present and size_matches)
                raw_entries_checked += len(entry_checks)
                unit_manifest_checks.append({
                    "candidate_id": cid,
                    "stage": stage,
                    "identity": identity,
                    "source_backup_manifest_bytes_exact": source_body == backup_body,
                    "manifest_sha256": body_sha256,
                    "recorded_manifest_sha256": row["durable"]["checksum_manifest_sha256"],
                    "recorded_sha256_matches": body_sha256 == row["durable"]["checksum_manifest_sha256"],
                    "declared_file_count": parsed["file_count"],
                    "declared_entries_covered_with_exact_size": all(entry_checks),
                    "ledger_object_count": row["durable"]["object_count"],
                    "actual_object_count": sum(
                        key.startswith(f"{cid}/{stage}/{identity}/") for key in source
                    ),
                })

    source_keys = set(source)
    backup_keys = set(backup)
    common_keys = source_keys & backup_keys
    size_mismatches = sorted(k for k in common_keys if source[k][0] != backup[k][0])
    etag_mismatches = sorted(k for k in common_keys if source[k][1] != backup[k][1])
    structure = {}
    for cid in sorted(expected_capture):
        structure[cid] = {
            "expected_capture_units": len(expected_capture[cid]),
            "actual_capture_units": len(actual_capture[cid]),
            "expected_calibration_units": len(expected_calibration[cid]),
            "actual_calibration_units": len(actual_calibration[cid]),
            "expected_wall_units": expected_scene[cid]["NORMAL"],
            "expected_no_wall_units": expected_scene[cid]["NO_WALL"],
            "capture_unit_ids_exact": expected_capture[cid] == actual_capture[cid],
            "calibration_unit_ids_exact": expected_calibration[cid] == actual_calibration[cid],
            "source_object_count": per_candidate_objects[cid],
            "source_bytes": per_candidate_bytes[cid],
        }

    manifest_checks_pass = all(
        item["source_backup_manifest_bytes_exact"]
        and item["recorded_sha256_matches"]
        and item["declared_entries_covered_with_exact_size"]
        and item["ledger_object_count"] == item["actual_object_count"]
        for item in unit_manifest_checks
    )
    checks = {
        "source_still_matches_precopy_baseline": (
            len(source) == BASELINE_SOURCE_OBJECTS
            and sum(v[0] for v in source.values()) == BASELINE_SOURCE_BYTES
        ),
        "source_backup_relative_keys_exact": source_keys == backup_keys,
        "source_backup_sizes_exact": not size_mismatches,
        "source_backup_etags_exact": not etag_mismatches,
        "candidate_structure_exact": all(
            value["capture_unit_ids_exact"] and value["calibration_unit_ids_exact"]
            and value["expected_wall_units"] == 25
            and value["expected_no_wall_units"] == 25
            for value in structure.values()
        ),
        "scientific_capture_units_exactly_150": sum(map(len, actual_capture.values())) == 150,
        "calibration_units_exactly_12": sum(map(len, actual_calibration.values())) == 12,
        "unit_sha256_manifests_verified": manifest_checks_pass,
    }
    receipt = {
        "artifact_id": "regime-a-prime-p3-terminal-s3-preservation-receipt-v0.1",
        "timestamp": utc(),
        "operation": "READ_ONLY_POST_COPY_VERIFICATION",
        "aws_identity": sts.get_caller_identity()["Arn"],
        "aws_account": sts.get_caller_identity()["Account"],
        "primary_s3_location": SOURCE_URI,
        "secondary_s3_location": BACKUP_URI,
        "copy_method": "aws s3 sync S3-to-S3; no --delete; source retained",
        "source_deletion_performed": False,
        "baseline_source_object_count_before_copy": BASELINE_SOURCE_OBJECTS,
        "baseline_source_bytes_before_copy": BASELINE_SOURCE_BYTES,
        "primary_s3_object_count": len(source),
        "backup_s3_object_count": len(backup),
        "primary_s3_bytes": sum(v[0] for v in source.values()),
        "backup_s3_bytes": sum(v[0] for v in backup.values()),
        "primary_coverage_sha256_key_size": coverage_digest(source, False),
        "backup_coverage_sha256_key_size": coverage_digest(backup, False),
        "primary_coverage_sha256_key_size_etag": coverage_digest(source, True),
        "backup_coverage_sha256_key_size_etag": coverage_digest(backup, True),
        "missing_from_backup_count": len(source_keys - backup_keys),
        "extra_in_backup_count": len(backup_keys - source_keys),
        "size_mismatch_count": len(size_mismatches),
        "etag_mismatch_count": len(etag_mismatches),
        "candidate_structure": structure,
        "scientific_capture_units_verified": sum(map(len, actual_capture.values())),
        "calibration_units_verified": sum(map(len, actual_calibration.values())),
        "unit_sha256_manifest_count_verified": len(unit_manifest_checks),
        "raw_entries_covered_by_sha256_manifests": raw_entries_checked,
        "sha256_verification_scope": (
            "All 162 source sha256_manifest.json objects were SHA-256 hashed and matched to their "
            "ledger-recorded hashes; backup manifest bytes were exact; every declared raw entry was "
            "present at both prefixes with its declared byte size. Raw payload SHA-256 values were not "
            "recomputed by downloading 2.45 GB; all 32,844 source/backup ETags and sizes were compared."
        ),
        "checks": checks,
        "backup_verification_status": "PASS" if all(checks.values()) else "FAIL",
        "REGIME_A_PRIME_COLLECTION_AUTHORIZED": "NO",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    if receipt["backup_verification_status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
