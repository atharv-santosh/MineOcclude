#!/usr/bin/env python3
"""Publish Person A's completed Activation Store v2 Registry trust record."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

REPOSITORY = Path("/home/sagemaker-user/MineOcclude")
CURRENT_PARENT = "e3182af19e60a46ab900e060cb7ad213c014083a"
PRODUCING_AUTHORITY = "55776dc88302b89b52eef483a710fbf6811cf536"
RUNNER_AUTHORITY = "c099fe970e2ea0dbf36d994923c9e40af357e585"
FRAME_OWNER_COMMIT = CURRENT_PARENT
FRAME_ARTIFACT_ID = "person_a_step4_1_preprocessed_frame_inputs_v0_1"
SOURCE = REPOSITORY / "docs/status/phase6_runtime/person-a-phase6-ten-pilot-expansion-seed-20260725"
EXTERNAL_ROOT = Path(
    "/home/sagemaker-user/person-a-phase6-approved-outputs/"
    "person-a-phase6-ten-pilot-expansion-seed-20260725"
)
COMBINED_INDEX = EXTERNAL_ROOT / "combined_activation_index.json"
OUTPUT = REPOSITORY / "docs/status/person_a_phase4_step4_1_registry_v2_activation_trust_v0_1"
EXPECTED_INDEX_SHA256 = "1a25d2186912ba72fdbf123ea9f07b2255bd0e55c6a48a1a50e3b7c0f23eb1e9"
EXPECTED_INDEX_SIZE = 245491346
EXPECTED_ROWS = 37480
SCHEMA_VERSION = "1.0"
STATUS_SCHEMA_VERSION = "mineocclude-owner-status-record-v1.0"
OWNER_ID = "person_a"
AUTHORITY_ID = "person_a_step4_1_activation_authority_v0_1"
STATUS_RECORD_ID = "person_a_step4_1_activation_status_v0_1"
MANIFEST_ID = "person_a_step4_1_activation_manifest_v0_1"
ARTIFACT_ID = "person_a_step4_1_activation_store_v2_combined_index_v0_1"
ARTIFACT_TYPE = "activation"
ARTIFACT_IDENTITY = "person-a-step4-1-activation-store-v2-ten-pilot-combined-index"
ARTIFACT_SCHEMA_VERSION = "person-a-multi-pilot-activation-index-v1"
AUTHORIZATION_RECORD_ID = "person_a_step4_1_activation_authorization_record_v0_1"
REGISTRY_SCHEMA_AUTHORITY = "25509bb4ba292a83d933058539aca1ca6002524a"
REGISTRY_QUERY_AUTHORITY = "5d8660c90fbf7362d7f32005f9b650e15ae1bfb5"


def formatted_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, allow_nan=False, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n"
    ).encode("utf-8")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"Expected JSON object: {path}")
    return value


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(formatted_bytes(value))


def git_text(*arguments: str) -> str:
    return subprocess.run(
        ["git", *arguments],
        cwd=REPOSITORY,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def require_source_state() -> None:
    if git_text("rev-parse", "HEAD") != CURRENT_PARENT:
        raise RuntimeError("Person A activation-record parent does not match")
    if git_text("rev-parse", "--abbrev-ref", "HEAD") != "role/person-a-model":
        raise RuntimeError("Person A branch does not match")
    unexpected = [
        line
        for line in git_text("status", "--short").splitlines()
        if not line.endswith(
            "scripts/build_person_a_step4_1_registry_v2_activation_trust_v0_1.py"
        )
    ]
    if unexpected:
        raise RuntimeError(f"Unexpected worktree changes: {unexpected}")
    if OUTPUT.exists():
        raise RuntimeError(f"Refusing to overwrite existing package: {OUTPUT}")
    for commit in (PRODUCING_AUTHORITY, RUNNER_AUTHORITY):
        if git_text("cat-file", "-t", commit) != "commit":
            raise RuntimeError(f"Missing producing authority: {commit}")


def main() -> int:
    require_source_state()
    artifact_manifest_path = SOURCE / "artifact_manifest.json"
    artifact_manifest = read_json(artifact_manifest_path)
    completion = read_json(SOURCE / "completion_report.json")
    validation = read_json(SOURCE / "validation_receipt.json")
    runtime = read_json(SOURCE / "runtime_preflight_receipt.json")
    if COMBINED_INDEX.stat().st_size != EXPECTED_INDEX_SIZE:
        raise RuntimeError("Combined activation-index byte size mismatch")
    if sha256_file(COMBINED_INDEX) != EXPECTED_INDEX_SHA256:
        raise RuntimeError("Combined activation-index SHA-256 mismatch")
    combined = read_json(COMBINED_INDEX)
    rows = combined["index_rows"]
    if combined["combined_activation_row_count"] != EXPECTED_ROWS or len(rows) != EXPECTED_ROWS:
        raise RuntimeError("Combined activation row count mismatch")
    if combined["activation_store_format_version"] != "person-a-activation-store-v2":
        raise RuntimeError("Activation Store v2 identity mismatch")
    if combined["scientific_identity_collision_count"] != 0:
        raise RuntimeError("Combined activation-index identity collision")
    identities = {
        (
            row["trajectory_id"],
            row["global_model_frame_idx"],
            row["layer_idx"],
            row["hook_site"],
        )
        for row in rows
    }
    if len(identities) != EXPECTED_ROWS:
        raise RuntimeError("Activation identities are not unique")
    if any(row["run_status"] != "completed" or row["status"] != "accepted" for row in rows):
        raise RuntimeError("Activation index contains a nonaccepted row")
    if any(row["store_format_version"] != "person-a-activation-store-v2" for row in rows):
        raise RuntimeError("Activation row store identity mismatch")

    per_pilot_inventories = []
    chunk_hash_mismatches = 0
    chunk_size_mismatches = 0
    index_hash_mismatches = 0
    index_size_mismatches = 0
    chunk_count = 0
    chunk_row_count = 0
    for pilot_id in combined["ordered_pilot_ids"]:
        path = SOURCE / "per_pilot_inventories" / f"{pilot_id}.json"
        inventory = read_json(path)
        for chunk in inventory["chunks"]:
            chunk_path = Path(chunk["path"])
            chunk_count += 1
            chunk_row_count += chunk["row_count"]
            if chunk_path.stat().st_size != chunk["byte_size"]:
                chunk_size_mismatches += 1
            if sha256_file(chunk_path) != chunk["sha256"]:
                chunk_hash_mismatches += 1
        index = inventory["activation_index"]
        index_path = Path(index["path"])
        if index_path.stat().st_size != index["byte_size"]:
            index_size_mismatches += 1
        if sha256_file(index_path) != index["sha256"]:
            index_hash_mismatches += 1
        per_pilot_inventories.append(inventory)
    if any(
        (
            chunk_hash_mismatches,
            chunk_size_mismatches,
            index_hash_mismatches,
            index_size_mismatches,
        )
    ):
        raise RuntimeError("Activation Store v2 external inventory verification failed")
    if chunk_count != 200 or chunk_row_count != EXPECTED_ROWS:
        raise RuntimeError("Activation chunk count or row count mismatch")

    status_record = {
        "authority_revision": PRODUCING_AUTHORITY,
        "decision": "accepted",
        "owner_id": OWNER_ID,
        "owner_status": "accepted",
        "schema_version": STATUS_SCHEMA_VERSION,
        "status_record_id": STATUS_RECORD_ID,
    }
    status_bytes = formatted_bytes(status_record)
    owner_authority = {
        "authority_id": AUTHORITY_ID,
        "authority_revision": PRODUCING_AUTHORITY,
        "authorized_artifact_types": [ARTIFACT_TYPE],
        "decision": "accepted",
        "owner_id": OWNER_ID,
        "owner_status": "accepted",
        "schema_version": SCHEMA_VERSION,
        "status_record_id": STATUS_RECORD_ID,
        "status_record_receipt_authority_revision": None,
        "status_record_receipt_id": None,
        "status_record_receipt_sha256": None,
        "status_record_schema_version": STATUS_SCHEMA_VERSION,
        "status_record_sha256": sha256_bytes(status_bytes),
        "status_record_verification_mode": "local_bytes",
    }
    manifest_sha256 = sha256_file(artifact_manifest_path)
    manifest_schema = "person-a-phase6-ten-pilot-artifact-manifest-v1.0"
    trusted_manifest = {
        "artifact_identities": [
            {
                "artifact_id": ARTIFACT_ID,
                "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
                "artifact_sha256": EXPECTED_INDEX_SHA256,
                "artifact_size_bytes": EXPECTED_INDEX_SIZE,
                "artifact_type": ARTIFACT_TYPE,
                "manifest_artifact_identity": ARTIFACT_IDENTITY,
            }
        ],
        "decision": "accepted",
        "manifest_id": MANIFEST_ID,
        "manifest_schema_version": manifest_schema,
        "manifest_sha256": manifest_sha256,
        "owner_authority_id": AUTHORITY_ID,
        "owner_authority_revision": PRODUCING_AUTHORITY,
        "owner_id": OWNER_ID,
        "owner_status": "accepted",
    }
    embedded_manifest = {
        "artifact_identities": [ARTIFACT_IDENTITY],
        "decision": "accepted",
        "manifest_id": MANIFEST_ID,
        "manifest_schema_version": manifest_schema,
        "manifest_sha256": manifest_sha256,
        "owner_authority_id": AUTHORITY_ID,
        "schema_version": SCHEMA_VERSION,
    }
    authorization_record = {
        "artifact_id": ARTIFACT_ID,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "artifact_sha256": EXPECTED_INDEX_SHA256,
        "artifact_size_bytes": EXPECTED_INDEX_SIZE,
        "artifact_type": ARTIFACT_TYPE,
        "authority_id": AUTHORITY_ID,
        "authorization_id": "person_a_step4_1_activation_authorization_v0_1",
        "authorization_record_id": AUTHORIZATION_RECORD_ID,
        "decision": "accepted",
        "manifest_artifact_identity": ARTIFACT_IDENTITY,
        "manifest_id": MANIFEST_ID,
        "manifest_schema_version": manifest_schema,
        "manifest_sha256": manifest_sha256,
        "owner_authority_revision": PRODUCING_AUTHORITY,
        "owner_id": OWNER_ID,
        "owner_status": "accepted",
    }
    authorization_bytes = formatted_bytes(authorization_record)
    authorization = {
        **authorization_record,
        "authorization_record_receipt_authority_revision": None,
        "authorization_record_receipt_id": None,
        "authorization_record_receipt_sha256": None,
        "authorization_record_sha256": sha256_bytes(authorization_bytes),
        "authorization_record_verification_mode": "local_bytes",
    }
    trusted_authorization = {
        "authorization": authorization,
        "authorization_record_verification": {"external_receipt": None, "mode": "local_bytes"},
    }
    verification_id = "person_a_step4_1_activation_combined_index_local_bytes_v0_1"
    run_id = "person_a_phase6_ten_pilot_activation_completion_55776dc"
    registry_records = {
        "artifacts": [
            {
                "artifact_id": ARTIFACT_ID,
                "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
                "artifact_type": ARTIFACT_TYPE,
                "byte_verification_id": verification_id,
                "creator_run_id": run_id,
                "direct_input_artifact_ids": [],
                "manifest_artifact_identity": ARTIFACT_IDENTITY,
                "manifest_id": MANIFEST_ID,
                "manifest_schema_version": manifest_schema,
                "manifest_sha256": manifest_sha256,
                "owner_authority_id": AUTHORITY_ID,
                "owner_authority_revision": PRODUCING_AUTHORITY,
                "owner_decision": "accepted",
                "owner_status_record_id": STATUS_RECORD_ID,
                "owner_status_record_sha256": owner_authority["status_record_sha256"],
                "schema_version": SCHEMA_VERSION,
                "sha256": EXPECTED_INDEX_SHA256,
                "size_bytes": EXPECTED_INDEX_SIZE,
                "status": "accepted",
                "status_reason": None,
                "superseded_by": None,
                "uri": f"file://{COMBINED_INDEX}",
            }
        ],
        "byte_verifications": [
            {
                "artifact_id": ARTIFACT_ID,
                "external_receipt_authority_revision": None,
                "external_receipt_id": None,
                "external_receipt_sha256": None,
                "mode": "local_bytes",
                "schema_version": SCHEMA_VERSION,
                "verification_id": verification_id,
                "verified_at": "2026-08-03T07:00:00Z",
                "verified_sha256": EXPECTED_INDEX_SHA256,
                "verified_size_bytes": EXPECTED_INDEX_SIZE,
            }
        ],
        "manifests": [embedded_manifest],
        "owner_authorities": [owner_authority],
        "runs": [
            {
                "checkpoint_hash": "a92c311baf49bbf31338da2caaadc9e4f947b94df8abcf75da350c4ae41319c5",
                "code_sha": PRODUCING_AUTHORITY,
                "command": ["bash", "scripts/run_person_a_phase6_ten_pilot_sagemaker.sh"],
                "config_snapshot_hash": "eb634c1e81c65a724b7cf32cbfe03f62e80a4428afda605071e1a43c6d0f4c10",
                "created_at": "2026-07-31T11:42:07Z",
                "data_identity_hash": EXPECTED_INDEX_SHA256,
                "ended_at": "2026-07-31T11:42:09Z",
                "environment_hash": sha256_file(SOURCE / "runtime_preflight_receipt.json"),
                "failure_reason": None,
                "git_dirty": False,
                "input_artifact_ids": [],
                "output_artifact_ids": [ARTIFACT_ID],
                "owner": OWNER_ID,
                "parent_run_id": None,
                "pending_reason": None,
                "preprocess_hash": "036fa0b4899285e5499f88581f6e02426a25f732fcc26bd63c0f5b3863a9d9ab",
                "run_id": run_id,
                "schema_version": SCHEMA_VERSION,
                "seeds": {"phase6": 20260725},
                "started_at": "2026-07-31T11:42:08Z",
                "status": "completed",
                "supersedes_run_id": None,
                "supersession_reason": None,
            }
        ],
        "schema_id": "person-a-step4-1-registry-v2-activation-records-v0-1",
        "schema_version": SCHEMA_VERSION,
    }
    trust_inputs = {
        "artifact_bytes": {ARTIFACT_ID: str(COMBINED_INDEX)},
        "trusted_artifact_authorizations": {ARTIFACT_ID: trusted_authorization},
        "trusted_authorization_record_bytes": {
            AUTHORIZATION_RECORD_ID: "artifact_authorization_record.json"
        },
        "trusted_manifest_records": {MANIFEST_ID: trusted_manifest},
        "trusted_owner_authorities": {
            AUTHORITY_ID: {
                "authority": owner_authority,
                "status_record_verification": {
                    "external_receipt": None,
                    "mode": "local_bytes",
                },
            }
        },
        "trusted_status_record_bytes": {STATUS_RECORD_ID: "owner_status_record.json"},
    }
    source_evidence = {
        "accepted_pilot_count": completion["accepted_pilot_count"],
        "activation_chunk_count": chunk_count,
        "activation_chunk_hash_mismatch_count": chunk_hash_mismatches,
        "activation_chunk_row_count": chunk_row_count,
        "activation_chunk_size_mismatch_count": chunk_size_mismatches,
        "activation_index_hash_mismatch_count": index_hash_mismatches,
        "activation_index_size_mismatch_count": index_size_mismatches,
        "activation_row_count": len(identities),
        "activation_store_format_version": combined["activation_store_format_version"],
        "combined_activation_index_path": str(COMBINED_INDEX),
        "combined_activation_index_sha256": EXPECTED_INDEX_SHA256,
        "combined_activation_index_size_bytes": EXPECTED_INDEX_SIZE,
        "complete_per_pilot_inventories": per_pilot_inventories,
        "completion_report": completion,
        "frame_owner_record_binding": {
            "artifact_id": FRAME_ARTIFACT_ID,
            "commit": FRAME_OWNER_COMMIT,
            "package": "docs/status/person_a_phase4_step4_1_registry_v2_trust_v0_1",
        },
        "hook_sites": sorted({row["hook_site"] for row in rows}),
        "layer_indices": sorted({row["layer_idx"] for row in rows}),
        "no_u4_derived_input": True,
        "ordered_pilot_ids": combined["ordered_pilot_ids"],
        "person_a_producing_branch": "role/person-a-model",
        "person_a_producing_commit": PRODUCING_AUTHORITY,
        "person_a_runner_commit": RUNNER_AUTHORITY,
        "registry_v2_query_authority": REGISTRY_QUERY_AUTHORITY,
        "registry_v2_schema_authority": REGISTRY_SCHEMA_AUTHORITY,
        "runtime_preflight_receipt": runtime,
        "schema_id": "person-a-step4-1-registry-v2-activation-source-evidence-v0-1",
        "schema_version": SCHEMA_VERSION,
        "scientific_rerun_during_registration": False,
        "source_artifact_manifest": artifact_manifest,
        "source_validation_receipt": validation,
        "unique_activation_identity_count": len(identities),
    }
    receipt = {
        "activation_chunk_count": chunk_count,
        "activation_row_count": len(identities),
        "activation_store_v2_external_bytes_verified": True,
        "canonical_json": True,
        "external_artifacts_modified": False,
        "manual_u4_inspection_performed": False,
        "owner_authority_non_placeholder": True,
        "owner_status": "accepted",
        "registry_v2_import_ready": True,
        "schema_id": "person-a-step4-1-registry-v2-activation-validation-v0-1",
        "schema_version": SCHEMA_VERSION,
        "scientific_execution_performed": False,
        "status": "PASS",
        "unresolved_blockers": [],
    }
    write_json(OUTPUT / "owner_status_record.json", status_record)
    write_json(OUTPUT / "owner_authority.json", owner_authority)
    write_json(OUTPUT / "artifact_authorization_record.json", authorization_record)
    write_json(OUTPUT / "trusted_artifact_authorization.json", trusted_authorization)
    write_json(OUTPUT / "trusted_manifest_record.json", trusted_manifest)
    write_json(OUTPUT / "registry_records.json", registry_records)
    write_json(OUTPUT / "registry_trust_inputs.json", trust_inputs)
    write_json(OUTPUT / "source_evidence.json", source_evidence)
    write_json(OUTPUT / "validation_receipt.json", receipt)
    files = []
    for path in sorted(OUTPUT.iterdir()):
        files.append(
            {
                "byte_size": path.stat().st_size,
                "path": path.name,
                "sha256": sha256_file(path),
            }
        )
    write_json(
        OUTPUT / "sha256_inventory.json",
        {
            "algorithm": "sha256",
            "file_count": len(files),
            "files": files,
            "schema_id": "person-a-step4-1-registry-v2-activation-sha256-inventory-v0-1",
            "schema_version": SCHEMA_VERSION,
        },
    )
    print(
        json.dumps(
            {
                "activation_rows": len(identities),
                "chunks_verified": chunk_count,
                "owner_status": "accepted",
                "status": "PASS",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
