#!/usr/bin/env python3
"""Publish Person A's additive Step 4.1 Registry v2 trust records."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

REPOSITORY = Path("/home/sagemaker-user/MineOcclude")
SOURCE_PACKAGE = REPOSITORY / "docs/status/person_a_phase4_step4_1_frame_handoff_v0_2"
FRAME_MANIFEST = SOURCE_PACKAGE / "preprocessed_frame_manifest.json"
OUTPUT = REPOSITORY / "docs/status/person_a_phase4_step4_1_registry_v2_trust_v0_1"
STARTING_AUTHORITY = "380b9a392c7ad3a941dbdadcc777c61ed03e1206"
EXPECTED_MANIFEST_SHA256 = (
    "f52a2ece32b00faf04b68b92b56c6f6a049b8a7bcb9c7f0af0f52de7fc4759c5"
)
REGISTRY_SCHEMA_AUTHORITY = "25509bb4ba292a83d933058539aca1ca6002524a"
REGISTRY_QUERY_AUTHORITY = "5d8660c90fbf7362d7f32005f9b650e15ae1bfb5"
SCHEMA_VERSION = "1.0"
STATUS_SCHEMA_VERSION = "mineocclude-owner-status-record-v1.0"
OWNER_ID = "person_a"
AUTHORITY_ID = "person_a_step4_1_frame_input_authority_v0_1"
STATUS_RECORD_ID = "person_a_step4_1_frame_input_status_v0_1"
MANIFEST_ID = "person_a_step4_1_frame_input_manifest_v0_1"
MANIFEST_SCHEMA_VERSION = "person-a-step4-1-preprocessed-frame-manifest-v0-1"
ARTIFACT_ID = "person_a_step4_1_preprocessed_frame_inputs_v0_1"
ARTIFACT_TYPE = "model_input"
ARTIFACT_IDENTITY = "person-a-step4-1-preprocessed-frame-inputs-1695"
ARTIFACT_SCHEMA_VERSION = "person-a-step4-1-preprocessed-frame-manifest-v0-1"
AUTHORIZATION_ID = "person_a_step4_1_frame_input_authorization_v0_1"
AUTHORIZATION_RECORD_ID = "person_a_step4_1_frame_input_authorization_record_v0_1"
RUN_ID = "person_a_step4_1_frame_handoff_380b9a3"


def formatted_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, allow_nan=False, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n"
    ).encode("utf-8")


def canonical_hash(value: Any) -> str:
    payload = json.dumps(
        value, allow_nan=False, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


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
    if git_text("rev-parse", "HEAD") != STARTING_AUTHORITY:
        raise RuntimeError("Person A starting authority does not match")
    if git_text("rev-parse", "--abbrev-ref", "HEAD") != "role/person-a-model":
        raise RuntimeError("Person A branch does not match")
    unexpected = [
        line
        for line in git_text("status", "--short").splitlines()
        if not line.endswith("scripts/build_person_a_step4_1_registry_v2_trust_v0_1.py")
    ]
    if unexpected:
        raise RuntimeError(f"Unexpected worktree changes: {unexpected}")
    if OUTPUT.exists():
        raise RuntimeError(f"Refusing to overwrite existing package: {OUTPUT}")


def main() -> int:
    require_source_state()
    manifest_bytes = FRAME_MANIFEST.read_bytes()
    manifest_sha256 = sha256_bytes(manifest_bytes)
    if manifest_sha256 != EXPECTED_MANIFEST_SHA256:
        raise RuntimeError("Frame manifest SHA-256 mismatch")
    frame_manifest = json.loads(manifest_bytes)
    records = frame_manifest["records"]
    if frame_manifest["artifact_count"] != 1695 or len(records) != 1695:
        raise RuntimeError("Frame count mismatch")
    identities = [record["global_frame_identity"] for record in records]
    if len(set(identities)) != 1695:
        raise RuntimeError("Frame identities are not unique")

    hash_mismatches = 0
    size_mismatches = 0
    for record in records:
        frame_path = Path(record["output_path"])
        if not frame_path.is_file():
            raise RuntimeError(f"Missing frame payload: {frame_path}")
        if frame_path.stat().st_size != record["payload_byte_size"]:
            size_mismatches += 1
        if sha256_file(frame_path) != record["payload_sha256"]:
            hash_mismatches += 1
    if hash_mismatches or size_mismatches:
        raise RuntimeError(
            f"Frame verification failed: hashes={hash_mismatches}, sizes={size_mismatches}"
        )

    source_context = read_json(SOURCE_PACKAGE / "source_context_manifest.json")
    preprocessing = read_json(
        SOURCE_PACKAGE / "preprocessing_and_serialization_contract.json"
    )
    handoff = read_json(SOURCE_PACKAGE / "handoff_decision.json")
    validation = read_json(SOURCE_PACKAGE / "validation_receipt.json")
    authority_binding = read_json(SOURCE_PACKAGE / "authority_binding.json")
    source_inventory = read_json(SOURCE_PACKAGE / "sha256_inventory.json")

    status_record = {
        "authority_revision": STARTING_AUTHORITY,
        "decision": "accepted",
        "owner_id": OWNER_ID,
        "owner_status": "accepted",
        "schema_version": STATUS_SCHEMA_VERSION,
        "status_record_id": STATUS_RECORD_ID,
    }
    status_bytes = formatted_bytes(status_record)
    status_sha256 = sha256_bytes(status_bytes)
    owner_authority = {
        "authority_id": AUTHORITY_ID,
        "authority_revision": STARTING_AUTHORITY,
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
        "status_record_sha256": status_sha256,
        "status_record_verification_mode": "local_bytes",
    }
    trusted_owner_authority = {
        "authority": owner_authority,
        "status_record_verification": {"external_receipt": None, "mode": "local_bytes"},
    }

    trusted_manifest = {
        "artifact_identities": [
            {
                "artifact_id": ARTIFACT_ID,
                "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
                "artifact_sha256": manifest_sha256,
                "artifact_size_bytes": len(manifest_bytes),
                "artifact_type": ARTIFACT_TYPE,
                "manifest_artifact_identity": ARTIFACT_IDENTITY,
            }
        ],
        "decision": "accepted",
        "manifest_id": MANIFEST_ID,
        "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
        "manifest_sha256": manifest_sha256,
        "owner_authority_id": AUTHORITY_ID,
        "owner_authority_revision": STARTING_AUTHORITY,
        "owner_id": OWNER_ID,
        "owner_status": "accepted",
    }
    embedded_manifest = {
        "artifact_identities": [ARTIFACT_IDENTITY],
        "decision": "accepted",
        "manifest_id": MANIFEST_ID,
        "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
        "manifest_sha256": manifest_sha256,
        "owner_authority_id": AUTHORITY_ID,
        "schema_version": SCHEMA_VERSION,
    }

    authorization_record = {
        "artifact_id": ARTIFACT_ID,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "artifact_sha256": manifest_sha256,
        "artifact_size_bytes": len(manifest_bytes),
        "artifact_type": ARTIFACT_TYPE,
        "authority_id": AUTHORITY_ID,
        "authorization_id": AUTHORIZATION_ID,
        "authorization_record_id": AUTHORIZATION_RECORD_ID,
        "decision": "accepted",
        "manifest_artifact_identity": ARTIFACT_IDENTITY,
        "manifest_id": MANIFEST_ID,
        "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
        "manifest_sha256": manifest_sha256,
        "owner_authority_revision": STARTING_AUTHORITY,
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
        "authorization_record_verification": {
            "external_receipt": None,
            "mode": "local_bytes",
        },
    }

    data_identity_hash = frame_manifest["admitted_identity_set_sha256"]
    environment_hash = canonical_hash(preprocessing["runtime_identity"])
    run = {
        "checkpoint_hash": canonical_hash({"model_loaded": False}),
        "code_sha": STARTING_AUTHORITY,
        "command": [
            "/home/sagemaker-user/.conda/envs/mineworld/bin/python",
            "scripts/build_person_a_step4_1_frame_handoff_v0_2.py",
            "--check",
        ],
        "config_snapshot_hash": sha256_file(
            SOURCE_PACKAGE / "preprocessing_and_serialization_contract.json"
        ),
        "created_at": "2026-08-01T07:05:39Z",
        "data_identity_hash": data_identity_hash,
        "ended_at": "2026-08-01T07:05:41Z",
        "environment_hash": environment_hash,
        "failure_reason": None,
        "git_dirty": False,
        "input_artifact_ids": [],
        "output_artifact_ids": [ARTIFACT_ID],
        "owner": OWNER_ID,
        "parent_run_id": None,
        "pending_reason": None,
        "preprocess_hash": frame_manifest["preprocess_hash"],
        "run_id": RUN_ID,
        "schema_version": SCHEMA_VERSION,
        "seeds": {"deterministic_preprocessing_no_rng": 0},
        "started_at": "2026-08-01T07:05:40Z",
        "status": "completed",
        "supersedes_run_id": None,
        "supersession_reason": None,
    }
    verification_id = "person_a_step4_1_frame_manifest_local_bytes_v0_1"
    byte_verification = {
        "artifact_id": ARTIFACT_ID,
        "external_receipt_authority_revision": None,
        "external_receipt_id": None,
        "external_receipt_sha256": None,
        "mode": "local_bytes",
        "schema_version": SCHEMA_VERSION,
        "verification_id": verification_id,
        "verified_at": "2026-08-03T00:00:00Z",
        "verified_sha256": manifest_sha256,
        "verified_size_bytes": len(manifest_bytes),
    }
    artifact = {
        "artifact_id": ARTIFACT_ID,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "artifact_type": ARTIFACT_TYPE,
        "byte_verification_id": verification_id,
        "creator_run_id": RUN_ID,
        "direct_input_artifact_ids": [],
        "manifest_artifact_identity": ARTIFACT_IDENTITY,
        "manifest_id": MANIFEST_ID,
        "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
        "manifest_sha256": manifest_sha256,
        "owner_authority_id": AUTHORITY_ID,
        "owner_authority_revision": STARTING_AUTHORITY,
        "owner_decision": "accepted",
        "owner_status_record_id": STATUS_RECORD_ID,
        "owner_status_record_sha256": status_sha256,
        "schema_version": SCHEMA_VERSION,
        "sha256": manifest_sha256,
        "size_bytes": len(manifest_bytes),
        "status": "accepted",
        "status_reason": None,
        "superseded_by": None,
        "uri": f"file://{FRAME_MANIFEST}",
    }

    registry_records = {
        "artifacts": [artifact],
        "byte_verifications": [byte_verification],
        "manifests": [embedded_manifest],
        "owner_authorities": [owner_authority],
        "runs": [run],
        "schema_id": "person-a-step4-1-registry-v2-records-v0-1",
        "schema_version": SCHEMA_VERSION,
    }
    trust_inputs = {
        "artifact_bytes": {ARTIFACT_ID: str(FRAME_MANIFEST)},
        "trusted_artifact_authorizations": {ARTIFACT_ID: trusted_authorization},
        "trusted_authorization_record_bytes": {
            AUTHORIZATION_RECORD_ID: "artifact_authorization_record.json"
        },
        "trusted_manifest_records": {MANIFEST_ID: trusted_manifest},
        "trusted_owner_authorities": {AUTHORITY_ID: trusted_owner_authority},
        "trusted_status_record_bytes": {STATUS_RECORD_ID: "owner_status_record.json"},
    }
    source_evidence = {
        "accepted_pilot_count": source_context["accepted_pilot_count"],
        "accepted_pilot_ids": source_context["accepted_pilot_ids"],
        "authority_binding": authority_binding,
        "complete_source_context_lineage": source_context,
        "external_frame_root": frame_manifest["output_root"],
        "fold_manifest_sha256": frame_manifest["fold_manifest_sha256"],
        "frame_hash_and_size_record_count": len(records),
        "frame_hashes_and_sizes_record_path": str(FRAME_MANIFEST),
        "frame_identity_set_sha256": data_identity_hash,
        "frame_manifest_byte_size": len(manifest_bytes),
        "frame_manifest_path": str(FRAME_MANIFEST),
        "frame_manifest_sha256": manifest_sha256,
        "frame_payload_hash_mismatch_count": hash_mismatches,
        "frame_payload_size_mismatch_count": size_mismatches,
        "frame_payload_total_byte_size": frame_manifest["total_payload_byte_size"],
        "no_u4_derived_input": True,
        "person_a_producing_branch": "role/person-a-model",
        "person_a_producing_commit": STARTING_AUTHORITY,
        "preprocessing_identity": {
            "artifact_contract_id": preprocessing["artifact_contract_id"],
            "artifact_contract_sha256": preprocessing["artifact_contract_sha256"],
            "preprocess_hash": preprocessing["preprocess_hash"],
            "preprocessing_profile": preprocessing["preprocessing_profile"],
            "runtime_identity": preprocessing["runtime_identity"],
        },
        "registry_v2_query_authority": REGISTRY_QUERY_AUTHORITY,
        "registry_v2_schema_authority": REGISTRY_SCHEMA_AUTHORITY,
        "schema_id": "person-a-step4-1-registry-v2-source-evidence-v0-1",
        "schema_version": SCHEMA_VERSION,
        "scientific_rerun_during_registration": False,
        "source_handoff_decision": handoff,
        "source_package_inventory": source_inventory,
        "source_validation_receipt": validation,
        "target_manifest_sha256": frame_manifest["target_manifest_sha256"],
        "unique_frame_count": len(set(identities)),
    }
    receipt = {
        "artifact_authorization_local_bytes_ready": True,
        "canonical_json": True,
        "external_artifacts_modified": False,
        "frame_manifest_sha256_verified": True,
        "frame_payload_hash_mismatch_count": hash_mismatches,
        "frame_payload_size_mismatch_count": size_mismatches,
        "frame_payloads_directly_verified": 1695,
        "manual_u4_inspection_performed": False,
        "owner_authority_non_placeholder": True,
        "owner_status": "accepted",
        "registry_v2_import_ready": True,
        "schema_id": "person-a-step4-1-registry-v2-trust-validation-v0-1",
        "schema_version": SCHEMA_VERSION,
        "scientific_execution_performed": False,
        "status": "PASS",
        "unique_frame_count": 1695,
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
    inventory = {
        "algorithm": "sha256",
        "file_count": len(files),
        "files": files,
        "schema_id": "person-a-step4-1-registry-v2-trust-sha256-inventory-v0-1",
        "schema_version": SCHEMA_VERSION,
    }
    write_json(OUTPUT / "sha256_inventory.json", inventory)
    print(
        json.dumps(
            {
                "frame_manifest_sha256": manifest_sha256,
                "frame_payloads_verified": 1695,
                "output": str(OUTPUT),
                "owner_status": "accepted",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
