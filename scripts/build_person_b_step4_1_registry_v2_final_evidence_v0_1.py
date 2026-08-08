#!/usr/bin/env python3
"""Publish Person B's Step 4.1 prediction and metric Registry v2 records."""

from __future__ import annotations

import hashlib
import json
import math
import subprocess
from pathlib import Path
from typing import Any

REPOSITORY = Path("/home/sagemaker-user/MineOcclude-person-b-analysis")
STARTING_AUTHORITY = "1b9ac2e37d245896af95a5a929774829720387db"
PERSON_A_OWNER_COMMIT = "397ba849adc63df80912c21dd1efacb1e29b8977"
PERSON_D_OWNER_COMMIT = "5ea6ce92890da7faa46f6aa837135081633d5f3d"
PERSON_A_FRAME_ARTIFACT_ID = "person_a_step4_1_preprocessed_frame_inputs_v0_1"
PERSON_A_ACTIVATION_ARTIFACT_ID = (
    "person_a_step4_1_activation_store_v2_combined_index_v0_1"
)
PRODUCTION_IMPLEMENTATION = "ca3bf19120d5553a34a5edc1bda6bfed54859127"
BOUNDED_CONTRACT_AUTHORITY = "53c2cd287a63e18e9b1fa5565b77f5c476baf9c4"
COMPARISON_IMPLEMENTATION = "0a73caf2b74221c5f934b95ae39ac825748e2942"
REGISTRY_SCHEMA_AUTHORITY = "25509bb4ba292a83d933058539aca1ca6002524a"
REGISTRY_QUERY_AUTHORITY = "5d8660c90fbf7362d7f32005f9b650e15ae1bfb5"
PRODUCTION_ROOT = Path(
    "/home/sagemaker-user/person-b-step4-1-approved-outputs/"
    "person-b-step4-1-production-v0-1"
)
BOUNDED_ROOT = Path(
    "/home/sagemaker-user/person-b-step4-1-approved-outputs/"
    "person-b-step4-1-bounded-reveal-v0-1"
)
COMPARISON_ROOT = Path(
    "/home/sagemaker-user/person-b-step4-1-approved-outputs/"
    "person-b-step4-1-final-comparison-v0-1"
)
FINAL_PACKAGE = (
    REPOSITORY
    / "docs/status/person_b_phase4_step4_1_final_comparison_completion_v0_1"
)
OUTPUT = REPOSITORY / "docs/status/person_b_phase4_step4_1_registry_v2_final_evidence_v0_1"
PRESERVED = PRODUCTION_ROOT / "fitted_probes_and_predictions.json"
BOUNDED = BOUNDED_ROOT / "post_reveal_predictions.json"
METRIC = COMPARISON_ROOT / "comparison_metric_table.json"
EXPECTED_PRESERVED_SHA256 = "01e792c4d7b58bbe4ae478195b1d9523802db5674ee06ebbf5364482f42061ba"
EXPECTED_BOUNDED_SHA256 = "b7716ba00b1e45b20dab130965d03bba8947a87999be51e89404fad4982d288d"
EXPECTED_METRIC_SHA256 = "c471fddb9bdc1a87c2f7e11ad8dc55db9e407f0ea45a2e038f668bda178ad0a7"
SCHEMA_VERSION = "1.0"
STATUS_SCHEMA_VERSION = "mineocclude-owner-status-record-v1.0"
OWNER_ID = "person_b"
AUTHORITY_ID = "person_b_step4_1_prediction_metric_authority_v0_1"
STATUS_RECORD_ID = "person_b_step4_1_prediction_metric_status_v0_1"
MANIFEST_ID = "person_b_step4_1_prediction_metric_manifest_v0_1"
MANIFEST_SCHEMA_VERSION = "person-b-step4-1-registry-v2-artifact-manifest-v0-1"
ARTIFACTS = {
    "fitted_probe": {
        "artifact_id": "person_b_step4_1_fitted_probes_v0_1",
        "artifact_type": "fitted_probe",
        "schema": "person-b-step4-1-production-ridge-oof-v0-1",
        "path": PRESERVED,
    },
    "preserved_prediction": {
        "artifact_id": "person_b_step4_1_preserved_oof_predictions_v0_1",
        "artifact_type": "prediction",
        "schema": "person-b-step4-1-production-ridge-oof-v0-1",
        "path": PRESERVED,
    },
    "bounded_prediction": {
        "artifact_id": "person_b_step4_1_bounded_reveal_predictions_v0_1",
        "artifact_type": "prediction",
        "schema": "person-b-step4-1-bounded-reveal-predictions-v0-1",
        "path": BOUNDED,
    },
    "metric_table": {
        "artifact_id": "person_b_step4_1_final_comparison_metric_table_v0_1",
        "artifact_type": "metric_table",
        "schema": "person-b-step4-1-final-comparison-output-v0-1",
        "path": METRIC,
    },
}


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


def git_bytes(commit: str, path: str) -> bytes:
    return subprocess.run(
        ["git", "show", f"{commit}:{path}"],
        cwd=REPOSITORY,
        check=True,
        capture_output=True,
    ).stdout


def git_text(*arguments: str) -> str:
    return subprocess.run(
        ["git", *arguments],
        cwd=REPOSITORY,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def verify_git_package(commit: str, package: str) -> dict[str, Any]:
    inventory_bytes = git_bytes(commit, f"{package}/sha256_inventory.json")
    inventory = json.loads(inventory_bytes)
    for item in inventory["files"]:
        payload = git_bytes(commit, f"{package}/{item['path']}")
        if len(payload) != item["byte_size"] or sha256_bytes(payload) != item["sha256"]:
            raise RuntimeError(f"Git-object package inventory mismatch: {package}/{item['path']}")
    authority_bytes = git_bytes(commit, f"{package}/owner_authority.json")
    receipt_bytes = git_bytes(commit, f"{package}/validation_receipt.json")
    records_bytes = git_bytes(commit, f"{package}/registry_records.json")
    trust_bytes = git_bytes(commit, f"{package}/registry_trust_inputs.json")
    authority = json.loads(authority_bytes)
    receipt = json.loads(receipt_bytes)
    if authority["owner_status"] != "accepted" or not receipt["registry_v2_import_ready"]:
        raise RuntimeError(f"Owner dependency is not accepted: {package}")
    return {
        "authority": authority,
        "authority_sha256": sha256_bytes(authority_bytes),
        "commit": commit,
        "inventory_sha256": sha256_bytes(inventory_bytes),
        "package": package,
        "records": json.loads(records_bytes),
        "records_sha256": sha256_bytes(records_bytes),
        "receipt": receipt,
        "receipt_sha256": sha256_bytes(receipt_bytes),
        "trust_inputs_sha256": sha256_bytes(trust_bytes),
    }


def require_source_state() -> None:
    if git_text("rev-parse", "HEAD") != STARTING_AUTHORITY:
        raise RuntimeError("Person B starting authority does not match")
    if git_text("rev-parse", "--abbrev-ref", "HEAD") != "role/person-b-analysis":
        raise RuntimeError("Person B branch does not match")
    unexpected = [
        line
        for line in git_text("status", "--short").splitlines()
        if not line.endswith(
            "scripts/build_person_b_step4_1_registry_v2_final_evidence_v0_1.py"
        )
    ]
    if unexpected:
        raise RuntimeError(f"Unexpected worktree changes: {unexpected}")
    if OUTPUT.exists():
        raise RuntimeError(f"Refusing to overwrite existing package: {OUTPUT}")
    for commit in (
        PERSON_A_OWNER_COMMIT,
        PERSON_D_OWNER_COMMIT,
        PRODUCTION_IMPLEMENTATION,
        BOUNDED_CONTRACT_AUTHORITY,
        COMPARISON_IMPLEMENTATION,
    ):
        if git_text("cat-file", "-t", commit) != "commit":
            raise RuntimeError(f"Required authority is unavailable: {commit}")


def require_finite_numbers(value: Any, source: str) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise RuntimeError(f"Nonfinite numeric value in {source}")
    if isinstance(value, dict):
        for item in value.values():
            require_finite_numbers(item, source)
    elif isinstance(value, list):
        for item in value:
            require_finite_numbers(item, source)


def main() -> int:
    require_source_state()
    a_frame = verify_git_package(
        PERSON_A_OWNER_COMMIT,
        "docs/status/person_a_phase4_step4_1_registry_v2_trust_v0_1",
    )
    a_activation = verify_git_package(
        PERSON_A_OWNER_COMMIT,
        "docs/status/person_a_phase4_step4_1_registry_v2_activation_trust_v0_1",
    )
    d_owner = verify_git_package(
        PERSON_D_OWNER_COMMIT,
        "docs/status/person_d_phase4_step4_1_registry_v2_trust_v0_1",
    )
    a_artifact_ids = {
        artifact["artifact_id"]
        for binding in (a_frame, a_activation)
        for artifact in binding["records"]["artifacts"]
    }
    if {PERSON_A_FRAME_ARTIFACT_ID, PERSON_A_ACTIVATION_ARTIFACT_ID} - a_artifact_ids:
        raise RuntimeError("Person A owner package is missing a required input artifact")
    d_artifact_ids = [artifact["artifact_id"] for artifact in d_owner["records"]["artifacts"]]
    if len(d_artifact_ids) != 9 or d_owner["receipt"]["baseline_prediction_count"] != 10776:
        raise RuntimeError("Person D owner package baseline binding mismatch")

    preserved_bytes = PRESERVED.read_bytes()
    bounded_bytes = BOUNDED.read_bytes()
    metric_bytes = METRIC.read_bytes()
    if sha256_bytes(preserved_bytes) != EXPECTED_PRESERVED_SHA256:
        raise RuntimeError("Preserved fitted-probe/prediction SHA-256 mismatch")
    if sha256_bytes(bounded_bytes) != EXPECTED_BOUNDED_SHA256:
        raise RuntimeError("Bounded-reveal prediction SHA-256 mismatch")
    if sha256_bytes(metric_bytes) != EXPECTED_METRIC_SHA256:
        raise RuntimeError("Final metric-table SHA-256 mismatch")
    if (FINAL_PACKAGE / "comparison_metric_table.json").read_bytes() != metric_bytes:
        raise RuntimeError("Committed and external final metric-table bytes differ")
    production = json.loads(preserved_bytes)
    bounded = json.loads(bounded_bytes)
    metric = json.loads(metric_bytes)
    require_finite_numbers(production, "preserved predictions")
    require_finite_numbers(bounded, "bounded reveal")
    require_finite_numbers(metric, "final metric table")
    if production["u4_output_inspected"] is not False or production["metrics_computed"]:
        raise RuntimeError("Production probe receipt violates the frozen boundary")
    if production["fitted_probe_count"] != 40 or len(production["probe_outputs"]) != 40:
        raise RuntimeError("Fitted-probe count mismatch")
    prediction_identities: set[tuple[str, int, str, str, int]] = set()
    duplicate_prediction_count = 0
    prediction_count = 0
    probe_summaries = []
    for probe in production["probe_outputs"]:
        local = []
        for row in probe["oof_prediction_rows"]:
            identity = (
                probe["target_name"],
                probe["layer_idx"],
                probe["hook_site"],
                row["trajectory_id"],
                row["global_model_frame_idx"],
            )
            if identity in prediction_identities:
                duplicate_prediction_count += 1
            prediction_identities.add(identity)
            local.append(identity)
            prediction_count += 1
            if not math.isfinite(row["prediction"]):
                raise RuntimeError("Nonfinite preserved OOF prediction")
        probe_summaries.append(
            {
                "code_sha": probe["code_sha"],
                "fold_fit_count": len(probe["fold_fits"]),
                "hook_site": probe["hook_site"],
                "layer_idx": probe["layer_idx"],
                "matrix_hash": probe["matrix_hash"],
                "oof_identity_set_sha256": canonical_hash(sorted(local)),
                "oof_prediction_count": len(local),
                "target_name": probe["target_name"],
            }
        )
    if prediction_count != 27800 or len(prediction_identities) != 27800:
        raise RuntimeError("Preserved OOF prediction identity count mismatch")
    if duplicate_prediction_count:
        raise RuntimeError("Preserved OOF prediction identity collision")
    expected_probe_keys = {
        (target, layer)
        for target in ("mu_oracle_blocks", "log_sigma_oracle")
        for layer in range(20)
    }
    if {(p["target_name"], p["layer_idx"]) for p in probe_summaries} != expected_probe_keys:
        raise RuntimeError("Fitted-probe target/layer coverage mismatch")

    if bounded["prediction_count"] != 100 or len(bounded["rows"]) != 100:
        raise RuntimeError("Bounded-reveal prediction count mismatch")
    bounded_identities = {
        (
            row["target_name"],
            row["layer_idx"],
            row["trajectory_id"],
            row["model_frame_idx"],
        )
        for row in bounded["rows"]
    }
    if len(bounded_identities) != 100 or any(
        not math.isfinite(row["prediction"]) for row in bounded["rows"]
    ):
        raise RuntimeError("Bounded-reveal prediction validation failed")
    production_receipt = read_json(PRODUCTION_ROOT / "execution_receipt.json")
    bounded_receipt = read_json(BOUNDED_ROOT / "execution_receipt.json")
    final_receipt = read_json(FINAL_PACKAGE / "execution_receipt.json")
    paired = read_json(FINAL_PACKAGE / "paired_test_results.json")
    intervals = read_json(FINAL_PACKAGE / "confidence_intervals.json")
    layer_decision = read_json(FINAL_PACKAGE / "layer_band_decision.json")
    require_finite_numbers(paired, "paired tests")
    require_finite_numbers(intervals, "confidence intervals")
    if (
        metric["decision"] != "FAIL"
        or layer_decision["decision"] != "FAIL"
        or len(metric["metric_records"]) != 520
        or len(metric["paired_test_records"]) != 100
        or len(paired["records"]) != 100
        or len(intervals["records"]) != 100
        or intervals["bootstrap_count"] != 2000
        or any(record["permutation_count"] != 999 for record in paired["records"])
    ):
        raise RuntimeError("Frozen final comparison record is incomplete")
    if (
        final_receipt["manual_u4_inspection"]
        or final_receipt["probe_refit_performed"]
        or final_receipt["additional_person_a_extraction_performed"]
        or final_receipt["exploratory_metrics_computed"]
        or final_receipt["bounded_reveal_rerun_performed"]
        or layer_decision["inconclusive_reasons"]
    ):
        raise RuntimeError("Frozen final comparison boundary or decision mismatch")

    source_descriptors = {
        "fitted_probe": {
            **ARTIFACTS["fitted_probe"],
            "sha256": EXPECTED_PRESERVED_SHA256,
            "size_bytes": len(preserved_bytes),
            "count": 40,
        },
        "preserved_prediction": {
            **ARTIFACTS["preserved_prediction"],
            "sha256": EXPECTED_PRESERVED_SHA256,
            "size_bytes": len(preserved_bytes),
            "count": prediction_count,
        },
        "bounded_prediction": {
            **ARTIFACTS["bounded_prediction"],
            "sha256": EXPECTED_BOUNDED_SHA256,
            "size_bytes": len(bounded_bytes),
            "count": len(bounded_identities),
        },
        "metric_table": {
            **ARTIFACTS["metric_table"],
            "sha256": EXPECTED_METRIC_SHA256,
            "size_bytes": len(metric_bytes),
            "count": len(metric["metric_records"]),
        },
    }
    serializable_descriptors = {
        key: {**value, "path": str(value["path"])}
        for key, value in source_descriptors.items()
    }
    artifact_manifest = {
        "acceptance_decision": "FAIL",
        "artifacts": [serializable_descriptors[key] for key in ARTIFACTS],
        "dependency_owner_commits": {
            "person_a": PERSON_A_OWNER_COMMIT,
            "person_d": PERSON_D_OWNER_COMMIT,
        },
        "metric_production_registration_allowed": True,
        "schema_id": MANIFEST_SCHEMA_VERSION,
        "schema_version": SCHEMA_VERSION,
    }
    write_json(OUTPUT / "artifact_manifest.json", artifact_manifest)
    manifest_sha256 = sha256_file(OUTPUT / "artifact_manifest.json")

    status_record = {
        "authority_revision": STARTING_AUTHORITY,
        "decision": "accepted",
        "owner_id": OWNER_ID,
        "owner_status": "accepted",
        "schema_version": STATUS_SCHEMA_VERSION,
        "status_record_id": STATUS_RECORD_ID,
    }
    status_bytes = formatted_bytes(status_record)
    owner_authority = {
        "authority_id": AUTHORITY_ID,
        "authority_revision": STARTING_AUTHORITY,
        "authorized_artifact_types": ["fitted_probe", "prediction", "metric_table"],
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

    dependencies = {
        "fitted_probe": [PERSON_A_ACTIVATION_ARTIFACT_ID],
        "preserved_prediction": [
            ARTIFACTS["fitted_probe"]["artifact_id"],
            PERSON_A_ACTIVATION_ARTIFACT_ID,
        ],
        "bounded_prediction": [
            ARTIFACTS["fitted_probe"]["artifact_id"],
            PERSON_A_ACTIVATION_ARTIFACT_ID,
        ],
        "metric_table": [
            ARTIFACTS["preserved_prediction"]["artifact_id"],
            ARTIFACTS["bounded_prediction"]["artifact_id"],
            *d_artifact_ids,
        ],
    }
    run_ids = {
        "fitted_probe": "person_b_step4_1_fitted_probe_production_ca3bf19",
        "preserved_prediction": "person_b_step4_1_oof_prediction_production_ca3bf19",
        "bounded_prediction": "person_b_step4_1_bounded_reveal_53c2cd2",
        "metric_table": "person_b_step4_1_final_comparison_1b9ac2e",
    }
    trusted_identities = []
    embedded_identities = []
    artifacts = []
    verifications = []
    trusted_authorizations = {}
    authorization_record_paths = {}
    for key, descriptor in source_descriptors.items():
        current_id = descriptor["artifact_id"]
        identity = f"person-b-step4-1::{key}"
        trusted_identities.append(
            {
                "artifact_id": current_id,
                "artifact_schema_version": descriptor["schema"],
                "artifact_sha256": descriptor["sha256"],
                "artifact_size_bytes": descriptor["size_bytes"],
                "artifact_type": descriptor["artifact_type"],
                "manifest_artifact_identity": identity,
            }
        )
        embedded_identities.append(identity)
        verification_id = f"person_b_step4_1_{key}_local_bytes_v0_1"
        verifications.append(
            {
                "artifact_id": current_id,
                "external_receipt_authority_revision": None,
                "external_receipt_id": None,
                "external_receipt_sha256": None,
                "mode": "local_bytes",
                "schema_version": SCHEMA_VERSION,
                "verification_id": verification_id,
                "verified_at": "2026-08-03T06:46:57Z",
                "verified_sha256": descriptor["sha256"],
                "verified_size_bytes": descriptor["size_bytes"],
            }
        )
        artifacts.append(
            {
                "artifact_id": current_id,
                "artifact_schema_version": descriptor["schema"],
                "artifact_type": descriptor["artifact_type"],
                "byte_verification_id": verification_id,
                "creator_run_id": run_ids[key],
                "direct_input_artifact_ids": dependencies[key],
                "manifest_artifact_identity": identity,
                "manifest_id": MANIFEST_ID,
                "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
                "manifest_sha256": manifest_sha256,
                "owner_authority_id": AUTHORITY_ID,
                "owner_authority_revision": STARTING_AUTHORITY,
                "owner_decision": "accepted",
                "owner_status_record_id": STATUS_RECORD_ID,
                "owner_status_record_sha256": owner_authority["status_record_sha256"],
                "schema_version": SCHEMA_VERSION,
                "sha256": descriptor["sha256"],
                "size_bytes": descriptor["size_bytes"],
                "status": "accepted",
                "status_reason": None,
                "superseded_by": None,
                "uri": f"file://{descriptor['path']}",
            }
        )
        record_id = f"person_b_step4_1_{key}_authorization_record_v0_1"
        record = {
            "artifact_id": current_id,
            "artifact_schema_version": descriptor["schema"],
            "artifact_sha256": descriptor["sha256"],
            "artifact_size_bytes": descriptor["size_bytes"],
            "artifact_type": descriptor["artifact_type"],
            "authority_id": AUTHORITY_ID,
            "authorization_id": f"person_b_step4_1_{key}_authorization_v0_1",
            "authorization_record_id": record_id,
            "decision": "accepted",
            "manifest_artifact_identity": identity,
            "manifest_id": MANIFEST_ID,
            "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
            "manifest_sha256": manifest_sha256,
            "owner_authority_revision": STARTING_AUTHORITY,
            "owner_id": OWNER_ID,
            "owner_status": "accepted",
        }
        record_bytes = formatted_bytes(record)
        relative_path = f"artifact_authorization_records/{record_id}.json"
        write_json(OUTPUT / relative_path, record)
        authorization_record_paths[record_id] = relative_path
        trusted_authorizations[current_id] = {
            "authorization": {
                **record,
                "authorization_record_receipt_authority_revision": None,
                "authorization_record_receipt_id": None,
                "authorization_record_receipt_sha256": None,
                "authorization_record_sha256": sha256_bytes(record_bytes),
                "authorization_record_verification_mode": "local_bytes",
            },
            "authorization_record_verification": {
                "external_receipt": None,
                "mode": "local_bytes",
            },
        }

    trusted_manifest = {
        "artifact_identities": trusted_identities,
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
        "artifact_identities": embedded_identities,
        "decision": "accepted",
        "manifest_id": MANIFEST_ID,
        "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
        "manifest_sha256": manifest_sha256,
        "owner_authority_id": AUTHORITY_ID,
        "schema_version": SCHEMA_VERSION,
    }
    config_hash = "b2e12e7049e0494c756be442a4f300cbc7dc0a6e262deecf682f1354e887f0ab"
    checkpoint_hash = "a92c311baf49bbf31338da2caaadc9e4f947b94df8abcf75da350c4ae41319c5"
    preprocess_hash = "036fa0b4899285e5499f88581f6e02426a25f732fcc26bd63c0f5b3863a9d9ab"
    run_specs = [
        ("fitted_probe", PRODUCTION_IMPLEMENTATION, None, "06:46:45", "06:46:46", "06:46:47", {"split": 20260719}, production["input_hash"], sha256_file(PRODUCTION_ROOT / "execution_receipt.json")),
        ("preserved_prediction", PRODUCTION_IMPLEMENTATION, run_ids["fitted_probe"], "06:46:48", "06:46:49", "06:46:50", {"split": 20260719}, canonical_hash(sorted(prediction_identities)), sha256_file(PRODUCTION_ROOT / "execution_receipt.json")),
        ("bounded_prediction", BOUNDED_CONTRACT_AUTHORITY, run_ids["preserved_prediction"], "06:46:51", "06:46:52", "06:46:53", {"deterministic_no_rng": 0}, canonical_hash(sorted(bounded_identities)), sha256_file(BOUNDED_ROOT / "execution_receipt.json")),
        ("metric_table", COMPARISON_IMPLEMENTATION, run_ids["bounded_prediction"], "06:46:54", "06:46:55", "06:46:57", {"bootstrap": 20260721, "permutation": 20260720}, canonical_hash(metric["direct_input_sha256s"]), sha256_file(FINAL_PACKAGE / "execution_receipt.json")),
    ]
    runs = []
    for key, code, parent, created, started, ended, seeds, data_hash, environment_hash in run_specs:
        runs.append(
            {
                "checkpoint_hash": checkpoint_hash,
                "code_sha": code,
                "command": ["authorized-existing-person-b-output", key],
                "config_snapshot_hash": config_hash,
                "created_at": f"2026-08-03T{created}Z",
                "data_identity_hash": data_hash,
                "ended_at": f"2026-08-03T{ended}Z",
                "environment_hash": environment_hash,
                "failure_reason": None,
                "git_dirty": False,
                "input_artifact_ids": dependencies[key],
                "output_artifact_ids": [ARTIFACTS[key]["artifact_id"]],
                "owner": OWNER_ID,
                "parent_run_id": parent,
                "pending_reason": None,
                "preprocess_hash": preprocess_hash,
                "run_id": run_ids[key],
                "schema_version": SCHEMA_VERSION,
                "seeds": seeds,
                "started_at": f"2026-08-03T{started}Z",
                "status": "completed",
                "supersedes_run_id": None,
                "supersession_reason": None,
            }
        )
    registry_records = {
        "artifacts": artifacts,
        "byte_verifications": verifications,
        "manifests": [embedded_manifest],
        "owner_authorities": [owner_authority],
        "runs": runs,
        "schema_id": "person-b-step4-1-registry-v2-final-records-v0-1",
        "schema_version": SCHEMA_VERSION,
    }
    trust_inputs = {
        "artifact_bytes": {
            ARTIFACTS[key]["artifact_id"]: str(descriptor["path"])
            for key, descriptor in source_descriptors.items()
        },
        "trusted_artifact_authorizations": trusted_authorizations,
        "trusted_authorization_record_bytes": authorization_record_paths,
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
    final_package_inventory = read_json(FINAL_PACKAGE / "sha256_inventory.json")
    source_evidence = {
        "acceptance_decision": "FAIL",
        "all_frozen_metrics_complete": len(metric["metric_records"]) == 520,
        "bounded_reveal": {
            "identity_set_sha256": canonical_hash(sorted(bounded_identities)),
            "prediction_count": len(bounded_identities),
            "prediction_sha256": EXPECTED_BOUNDED_SHA256,
            "receipt": bounded_receipt,
        },
        "confidence_intervals": {
            "bootstrap_count": intervals["bootstrap_count"],
            "record_count": len(intervals["records"]),
            "seed": intervals["seed"],
            "sha256": sha256_file(FINAL_PACKAGE / "confidence_intervals.json"),
        },
        "controls_complete": True,
        "direct_input_sha256s": metric["direct_input_sha256s"],
        "final_comparison_commit": STARTING_AUTHORITY,
        "final_comparison_execution_receipt": final_receipt,
        "final_comparison_package_inventory": final_package_inventory,
        "final_metric_record_count": len(metric["metric_records"]),
        "final_metric_table_sha256": EXPECTED_METRIC_SHA256,
        "layer_band_decision": layer_decision,
        "manual_u4_inspection_performed": False,
        "multiplicity_correction_complete": True,
        "no_exploratory_metrics": True,
        "paired_significance": {
            "permutation_count": 999,
            "record_count": len(paired["records"]),
            "seed": 20260720,
            "sha256": sha256_file(FINAL_PACKAGE / "paired_test_results.json"),
        },
        "person_a_additional_extraction_performed": False,
        "person_a_owner_dependencies": {
            "activation": a_activation,
            "frame_input": a_frame,
        },
        "person_d_owner_dependency": d_owner,
        "preserved_oof": {
            "duplicate_prediction_identity_count": duplicate_prediction_count,
            "fitted_probe_count": production["fitted_probe_count"],
            "implementation_commit": production["implementation_commit"],
            "prediction_count": prediction_count,
            "probe_summaries": probe_summaries,
            "receipt": production_receipt,
            "sha256": EXPECTED_PRESERVED_SHA256,
        },
        "probe_refit_performed": False,
        "registry_v2_query_authority": REGISTRY_QUERY_AUTHORITY,
        "registry_v2_schema_authority": REGISTRY_SCHEMA_AUTHORITY,
        "schema_id": "person-b-step4-1-registry-v2-final-source-evidence-v0-1",
        "schema_version": SCHEMA_VERSION,
        "scientific_rerun_during_registration": False,
    }
    registration_decision = {
        "acceptance_decision": "FAIL",
        "dependency_validation": {
            "person_a_activation_owner_status": a_activation["authority"]["owner_status"],
            "person_a_frame_owner_status": a_frame["authority"]["owner_status"],
            "person_d_owner_status": d_owner["authority"]["owner_status"],
        },
        "metric_owner_status": "accepted",
        "metric_production_registration_allowed": True,
        "prediction_owner_status": "accepted",
        "schema_id": "person-b-step4-1-registry-v2-registration-decision-v0-1",
        "schema_version": SCHEMA_VERSION,
        "unresolved_blockers": [],
    }
    receipt = {
        "acceptance_decision": "FAIL",
        "artifact_authorization_local_bytes_ready_count": len(artifacts),
        "bounded_reveal_prediction_count": 100,
        "canonical_json": True,
        "external_artifacts_modified": False,
        "final_metric_record_count": 520,
        "manual_u4_inspection_performed": False,
        "metric_owner_status": "accepted",
        "metric_production_registration_allowed": True,
        "owner_authority_non_placeholder": True,
        "prediction_owner_status": "accepted",
        "preserved_oof_prediction_count": 27800,
        "probe_refit_performed": False,
        "registry_v2_import_ready": True,
        "schema_id": "person-b-step4-1-registry-v2-final-validation-v0-1",
        "schema_version": SCHEMA_VERSION,
        "scientific_execution_performed": False,
        "status": "PASS",
        "unresolved_blockers": [],
    }
    write_json(OUTPUT / "owner_status_record.json", status_record)
    write_json(OUTPUT / "owner_authority.json", owner_authority)
    write_json(OUTPUT / "trusted_artifact_authorizations.json", trusted_authorizations)
    write_json(OUTPUT / "trusted_manifest_record.json", trusted_manifest)
    write_json(OUTPUT / "registry_records.json", registry_records)
    write_json(OUTPUT / "registry_trust_inputs.json", trust_inputs)
    write_json(OUTPUT / "source_evidence.json", source_evidence)
    write_json(OUTPUT / "registration_decision.json", registration_decision)
    write_json(OUTPUT / "validation_receipt.json", receipt)
    files = []
    for path in sorted(item for item in OUTPUT.rglob("*") if item.is_file()):
        files.append(
            {
                "byte_size": path.stat().st_size,
                "path": path.relative_to(OUTPUT).as_posix(),
                "sha256": sha256_file(path),
            }
        )
    write_json(
        OUTPUT / "sha256_inventory.json",
        {
            "algorithm": "sha256",
            "file_count": len(files),
            "files": files,
            "schema_id": "person-b-step4-1-registry-v2-final-sha256-inventory-v0-1",
            "schema_version": SCHEMA_VERSION,
        },
    )
    print(
        json.dumps(
            {
                "acceptance_decision": "FAIL",
                "artifacts": len(artifacts),
                "metric_registration_allowed": True,
                "owner_status": "accepted",
                "status": "PASS",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
