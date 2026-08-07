#!/usr/bin/env python3
"""Import accepted Step 4.1 owner records and publish Person E closure."""

from __future__ import annotations

import hashlib
import json
import math
import subprocess
from pathlib import Path
from typing import Any

from mineocclude.experiments.registry import (
    ImmutableRegistryIndex,
    require_valid_immutable_registry,
)

REPOSITORY = Path("/home/sagemaker-user/MineOcclude-Person-E-Step6_6")
STARTING_AUTHORITY = "1a1122dc7a80add664bf2aaa02b9a3e1f161ec91"
PERSON_A_OWNER_COMMIT = "397ba849adc63df80912c21dd1efacb1e29b8977"
PERSON_D_OWNER_COMMIT = "5ea6ce92890da7faa46f6aa837135081633d5f3d"
PERSON_B_OWNER_COMMIT = "8c5374d00983e6fec22f560a9fd5849e92060f3e"
PERSON_D_COMPLETION_COMMIT = "f89b142a6fdb52c2d238669af8df14061cee5896"
REGISTRY_SCHEMA_AUTHORITY = "25509bb4ba292a83d933058539aca1ca6002524a"
REGISTRY_QUERY_AUTHORITY = "5d8660c90fbf7362d7f32005f9b650e15ae1bfb5"
COMPARISON_CONTRACT_COMMIT = "4da02023a376df77eacb48084b1406ec1accfcb1"
POST_REVEAL_CONTRACT_COMMIT = "53c2cd287a63e18e9b1fa5565b77f5c476baf9c4"
BOUNDED_REVEAL_AUTHORITY = "99fb896ed8e6a3b187272fe078706bc7b17666d8"
POSITIVE_CONTROL_AUTHORITY = "e39fef4a59142a84dfb5991d51deeb506eb23a7b"
POSITIVE_CONTROL_PATH = (
    "docs/status/person_b_phase6_step6_6_positive_control_v0_1/"
    "positive_control_decision.json"
)
POSITIVE_CONTROL_SHA256 = (
    "742557b32326180003b1cd83ed5db6f1a1ebfebd692d969809698d323f239056"
)
REGISTRY_ID = "mineocclude_step4_1_final_comparison_registry_v2"
SCHEMA_VERSION = "1.0"
REGISTRY_SCHEMA_VERSION = "mineocclude-immutable-registry-v2.0"
OUTPUT = REPOSITORY / (
    "docs/status/person_e_phase4_step4_1_registry_v2_closure_v0_1"
)
FINAL_ROOT = Path(
    "/home/sagemaker-user/person-b-step4-1-approved-outputs/"
    "person-b-step4-1-final-comparison-v0-1"
)
BOUNDED_ROOT = Path(
    "/home/sagemaker-user/person-b-step4-1-approved-outputs/"
    "person-b-step4-1-bounded-reveal-v0-1"
)
FINAL_METRIC_ARTIFACT_ID = (
    "person_b_step4_1_final_comparison_metric_table_v0_1"
)
FRAME_ARTIFACT_ID = "person_a_step4_1_preprocessed_frame_inputs_v0_1"
ACTIVATION_ARTIFACT_ID = (
    "person_a_step4_1_activation_store_v2_combined_index_v0_1"
)
PACKAGES = (
    (
        "person_a_frame_input",
        PERSON_A_OWNER_COMMIT,
        "docs/status/person_a_phase4_step4_1_registry_v2_trust_v0_1",
    ),
    (
        "person_a_activation",
        PERSON_A_OWNER_COMMIT,
        "docs/status/person_a_phase4_step4_1_registry_v2_activation_trust_v0_1",
    ),
    (
        "person_d_baselines",
        PERSON_D_OWNER_COMMIT,
        "docs/status/person_d_phase4_step4_1_registry_v2_trust_v0_1",
    ),
    (
        "person_b_predictions_metrics",
        PERSON_B_OWNER_COMMIT,
        "docs/status/person_b_phase4_step4_1_registry_v2_final_evidence_v0_1",
    ),
)


def formatted_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
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
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise TypeError(f"Expected JSON object: {path}")
    return document


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


def require_finite(value: Any, source: str) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise RuntimeError(f"Nonfinite value in {source}")
    if isinstance(value, dict):
        for item in value.values():
            require_finite(item, source)
    elif isinstance(value, list):
        for item in value:
            require_finite(item, source)


def require_source_state() -> None:
    if git_text("rev-parse", "HEAD") != STARTING_AUTHORITY:
        raise RuntimeError("Person E starting authority does not match")
    if git_text("rev-parse", "--abbrev-ref", "HEAD") != "role/person-e-operations":
        raise RuntimeError("Person E branch does not match")
    allowed_path = (
        "scripts/build_person_e_step4_1_registry_v2_closure_v0_1.py"
    )
    unexpected = [
        line
        for line in git_text("status", "--short").splitlines()
        if not line.endswith(allowed_path)
    ]
    if unexpected:
        raise RuntimeError(f"Unexpected worktree changes: {unexpected}")
    if OUTPUT.exists():
        raise RuntimeError(f"Refusing to overwrite existing package: {OUTPUT}")
    required_commits = {
        STARTING_AUTHORITY,
        PERSON_A_OWNER_COMMIT,
        PERSON_D_OWNER_COMMIT,
        PERSON_B_OWNER_COMMIT,
        PERSON_D_COMPLETION_COMMIT,
        REGISTRY_SCHEMA_AUTHORITY,
        REGISTRY_QUERY_AUTHORITY,
        COMPARISON_CONTRACT_COMMIT,
        POST_REVEAL_CONTRACT_COMMIT,
        BOUNDED_REVEAL_AUTHORITY,
        POSITIVE_CONTROL_AUTHORITY,
    }
    for commit in sorted(required_commits):
        if git_text("cat-file", "-t", commit) != "commit":
            raise RuntimeError(f"Required authority is unavailable: {commit}")


def verify_git_package(label: str, commit: str, package: str) -> dict[str, Any]:
    inventory_path = f"{package}/sha256_inventory.json"
    inventory_bytes = git_bytes(commit, inventory_path)
    inventory = json.loads(inventory_bytes)
    verified_files: list[dict[str, Any]] = []
    for item in inventory["files"]:
        source_path = f"{package}/{item['path']}"
        payload = git_bytes(commit, source_path)
        if len(payload) != item["byte_size"]:
            raise RuntimeError(f"Git-object byte-size mismatch: {source_path}")
        if sha256_bytes(payload) != item["sha256"]:
            raise RuntimeError(f"Git-object SHA-256 mismatch: {source_path}")
        verified_files.append(
            {
                "byte_size": len(payload),
                "git_object_path": f"{commit}:{source_path}",
                "sha256": sha256_bytes(payload),
            }
        )
    records_path = f"{package}/registry_records.json"
    trust_path = f"{package}/registry_trust_inputs.json"
    authority_path = f"{package}/owner_authority.json"
    receipt_path = f"{package}/validation_receipt.json"
    records_bytes = git_bytes(commit, records_path)
    trust_bytes = git_bytes(commit, trust_path)
    authority_bytes = git_bytes(commit, authority_path)
    receipt_bytes = git_bytes(commit, receipt_path)
    authority = json.loads(authority_bytes)
    receipt = json.loads(receipt_bytes)
    if authority["owner_status"] != "accepted":
        raise RuntimeError(f"Owner authority is not accepted: {label}")
    if receipt["status"] != "PASS" or not receipt["registry_v2_import_ready"]:
        raise RuntimeError(f"Owner validation is not import-ready: {label}")
    return {
        "authority": authority,
        "authority_sha256": sha256_bytes(authority_bytes),
        "commit": commit,
        "inventory_sha256": sha256_bytes(inventory_bytes),
        "label": label,
        "package": package,
        "receipt": receipt,
        "receipt_sha256": sha256_bytes(receipt_bytes),
        "records": json.loads(records_bytes),
        "records_sha256": sha256_bytes(records_bytes),
        "trust": json.loads(trust_bytes),
        "trust_sha256": sha256_bytes(trust_bytes),
        "verified_files": verified_files,
    }


def merge_unique(target: dict[str, Any], source: dict[str, Any], name: str) -> None:
    collision = set(target) & set(source)
    if collision:
        raise RuntimeError(f"Duplicate {name}: {sorted(collision)}")
    target.update(source)


def verify_external_inventory(root: Path) -> dict[str, Any]:
    inventory_path = root / "sha256_inventory.json"
    inventory = read_json(inventory_path)
    for relative_path, expected_sha256 in inventory["files"].items():
        path = root / relative_path
        if not path.is_file() or sha256_file(path) != expected_sha256:
            raise RuntimeError(f"External inventory mismatch: {path}")
    return inventory


def evidence_descriptor(label: str, path: Path) -> dict[str, Any]:
    return {
        "byte_size": path.stat().st_size,
        "evidence_id": label,
        "path": str(path),
        "sha256": sha256_file(path),
    }


def main() -> int:
    require_source_state()
    package_data = [verify_git_package(*spec) for spec in PACKAGES]
    packages_by_label = {item["label"]: item for item in package_data}

    owner_authorities: list[dict[str, Any]] = []
    manifests: list[dict[str, Any]] = []
    byte_verifications: list[dict[str, Any]] = []
    run_by_id: dict[str, dict[str, Any]] = {}
    artifact_by_id: dict[str, dict[str, Any]] = {}
    artifact_bytes: dict[str, bytes] = {}
    artifact_paths: dict[str, str] = {}
    trusted_owner_authorities: dict[str, Any] = {}
    trusted_status_record_bytes: dict[str, bytes] = {}
    trusted_artifact_authorizations: dict[str, Any] = {}
    trusted_authorization_record_bytes: dict[str, bytes] = {}
    trusted_manifest_records: dict[str, Any] = {}
    status_record_bindings: dict[str, Any] = {}
    authorization_record_bindings: dict[str, Any] = {}

    for package in package_data:
        records = package["records"]
        trust = package["trust"]
        owner_authorities.extend(records["owner_authorities"])
        manifests.extend(records["manifests"])
        byte_verifications.extend(records["byte_verifications"])
        for run in records["runs"]:
            if run["run_id"] in run_by_id:
                raise RuntimeError(f"Duplicate run ID: {run['run_id']}")
            run_by_id[run["run_id"]] = run
        for artifact in records["artifacts"]:
            artifact_id = artifact["artifact_id"]
            if artifact_id in artifact_by_id:
                raise RuntimeError(f"Duplicate artifact ID: {artifact_id}")
            artifact_by_id[artifact_id] = artifact
        merge_unique(
            trusted_owner_authorities,
            trust["trusted_owner_authorities"],
            "trusted owner authority",
        )
        merge_unique(
            trusted_artifact_authorizations,
            trust["trusted_artifact_authorizations"],
            "trusted artifact authorization",
        )
        merge_unique(
            trusted_manifest_records,
            trust["trusted_manifest_records"],
            "trusted manifest",
        )
        for artifact_id, source in trust["artifact_bytes"].items():
            if artifact_id in artifact_bytes:
                raise RuntimeError(f"Duplicate artifact byte binding: {artifact_id}")
            path = Path(source)
            payload = path.read_bytes()
            artifact = artifact_by_id[artifact_id]
            if (
                len(payload) != artifact["size_bytes"]
                or sha256_bytes(payload) != artifact["sha256"]
            ):
                raise RuntimeError(f"Artifact byte verification failed: {artifact_id}")
            if artifact["uri"] != f"file://{path}":
                raise RuntimeError(f"Artifact URI binding failed: {artifact_id}")
            artifact_bytes[artifact_id] = payload
            artifact_paths[artifact_id] = str(path)
        for record_id, relative_path in trust[
            "trusted_status_record_bytes"
        ].items():
            payload = git_bytes(
                package["commit"], f"{package['package']}/{relative_path}"
            )
            if record_id in trusted_status_record_bytes:
                raise RuntimeError(f"Duplicate status record: {record_id}")
            trusted_status_record_bytes[record_id] = payload
            status_record_bindings[record_id] = {
                "byte_size": len(payload),
                "git_object_path": (
                    f"{package['commit']}:{package['package']}/{relative_path}"
                ),
                "record": json.loads(payload),
                "sha256": sha256_bytes(payload),
            }
        for record_id, relative_path in trust[
            "trusted_authorization_record_bytes"
        ].items():
            payload = git_bytes(
                package["commit"], f"{package['package']}/{relative_path}"
            )
            if record_id in trusted_authorization_record_bytes:
                raise RuntimeError(f"Duplicate authorization record: {record_id}")
            trusted_authorization_record_bytes[record_id] = payload
            authorization_record_bindings[record_id] = {
                "byte_size": len(payload),
                "git_object_path": (
                    f"{package['commit']}:{package['package']}/{relative_path}"
                ),
                "record": json.loads(payload),
                "sha256": sha256_bytes(payload),
            }

    d_artifact_ids = [
        item["artifact_id"]
        for item in packages_by_label["person_d_baselines"]["records"]["artifacts"]
    ]
    b_artifact_ids = [
        item["artifact_id"]
        for item in packages_by_label["person_b_predictions_metrics"]["records"][
            "artifacts"
        ]
    ]
    import_order = [
        FRAME_ARTIFACT_ID,
        ACTIVATION_ARTIFACT_ID,
        b_artifact_ids[0],
        b_artifact_ids[1],
        *d_artifact_ids,
        b_artifact_ids[2],
        b_artifact_ids[3],
    ]
    if len(import_order) != 15 or set(import_order) != set(artifact_by_id):
        raise RuntimeError("Registry v2 import order is incomplete")
    run_order: list[str] = []
    for artifact_id in import_order:
        run_id = artifact_by_id[artifact_id]["creator_run_id"]
        if run_id not in run_order:
            run_order.append(run_id)

    registry = {
        "artifacts": [artifact_by_id[item] for item in import_order],
        "byte_verifications": byte_verifications,
        "immutable_registry_schema_version": REGISTRY_SCHEMA_VERSION,
        "manifests": manifests,
        "owner_authorities": owner_authorities,
        "registry_id": REGISTRY_ID,
        "runs": [run_by_id[item] for item in run_order],
        "schema_version": SCHEMA_VERSION,
        "scientific_use": "permitted",
        "synthetic": False,
    }
    validation = require_valid_immutable_registry(
        registry,
        artifact_bytes_by_id=artifact_bytes,
        trusted_owner_authorities=trusted_owner_authorities,
        trusted_status_record_bytes=trusted_status_record_bytes,
        trusted_artifact_authorizations=trusted_artifact_authorizations,
        trusted_authorization_record_bytes=trusted_authorization_record_bytes,
        trusted_manifest_records=trusted_manifest_records,
    )
    if not validation.accepted or validation.rejections:
        raise RuntimeError("Registry v2 strict import unexpectedly rejected")
    index = ImmutableRegistryIndex(
        registry,
        artifact_bytes_by_id=artifact_bytes,
        trusted_owner_authorities=trusted_owner_authorities,
        trusted_status_record_bytes=trusted_status_record_bytes,
        trusted_artifact_authorizations=trusted_artifact_authorizations,
        trusted_authorization_record_bytes=trusted_authorization_record_bytes,
        trusted_manifest_records=trusted_manifest_records,
    )
    backward_query = index.backward_provenance(FINAL_METRIC_ARTIFACT_ID)
    forward_frame_query = index.forward_artifact_impact(FRAME_ARTIFACT_ID)
    forward_activation_query = index.forward_artifact_impact(ACTIVATION_ARTIFACT_ID)
    if len(backward_query["upstream_artifacts"]) != 14:
        raise RuntimeError("Final metric provenance query is incomplete")

    final_inventory = verify_external_inventory(FINAL_ROOT)
    bounded_inventory = verify_external_inventory(BOUNDED_ROOT)
    metric = read_json(FINAL_ROOT / "comparison_metric_table.json")
    paired = read_json(FINAL_ROOT / "paired_test_results.json")
    intervals = read_json(FINAL_ROOT / "confidence_intervals.json")
    layer_decision = read_json(FINAL_ROOT / "layer_band_decision.json")
    final_receipt = read_json(FINAL_ROOT / "execution_receipt.json")
    post_reveal_receipt = read_json(BOUNDED_ROOT / "execution_receipt.json")
    for document, label in (
        (metric, "metric table"),
        (paired, "paired tests"),
        (intervals, "confidence intervals"),
        (layer_decision, "layer decision"),
    ):
        require_finite(document, label)
        if document["u4_output_inspected"] is not False:
            raise RuntimeError(f"U4 boundary mismatch: {label}")
    if (
        metric["decision"] != "FAIL"
        or layer_decision["decision"] != "FAIL"
        or metric["layer_bands"]
        or layer_decision["qualifying_layer_bands"]
        or layer_decision["inconclusive_reasons"]
    ):
        raise RuntimeError("Frozen FAIL decision changed")
    if (
        len(metric["metric_records"]) != 520
        or len(metric["paired_test_records"]) != 100
        or metric["paired_test_records"] != paired["records"]
        or len(paired["records"]) != 100
        or len(intervals["records"]) != 100
        or intervals["bootstrap_count"] != 2000
        or any(item["permutation_count"] != 999 for item in paired["records"])
    ):
        raise RuntimeError("Frozen metric or statistical procedure mismatch")
    required_receipt_values = {
        "additional_person_a_extraction_performed": False,
        "bounded_reveal_prediction_count": 100,
        "bounded_reveal_prediction_sha256": (
            "b7716ba00b1e45b20dab130965d03bba8947a87999be51e89404fad4982d288d"
        ),
        "bounded_reveal_rerun_performed": False,
        "broad_hidden_state_interpretation": False,
        "exploratory_metrics_computed": False,
        "manual_u4_inspection": False,
        "post_hoc_layer_selection_performed": False,
        "post_hoc_test_selection_performed": False,
        "probe_refit_performed": False,
        "u4_output_inspected": False,
    }
    if any(final_receipt.get(key) != value for key, value in required_receipt_values.items()):
        raise RuntimeError("Final execution receipt violates closure requirements")
    if (
        post_reveal_receipt["prediction_count"] != 100
        or post_reveal_receipt["metrics_computed"]
        or post_reveal_receipt["probe_refit_performed"]
        or post_reveal_receipt["additional_person_a_extraction_performed"]
        or post_reveal_receipt["u4_output_inspected"]
    ):
        raise RuntimeError("Post-reveal receipt violates the frozen boundary")

    positive_bytes = git_bytes(POSITIVE_CONTROL_AUTHORITY, POSITIVE_CONTROL_PATH)
    if sha256_bytes(positive_bytes) != POSITIVE_CONTROL_SHA256:
        raise RuntimeError("Positive-control decision SHA-256 mismatch")
    positive_control = json.loads(positive_bytes)
    if (
        positive_control["decision"]
        != "PASS_FROZEN_VISIBLE_POSITION_POSITIVE_CONTROL"
        or positive_control["positive_control_pass"] is not True
        or positive_control["u4_output_inspected"] is not False
    ):
        raise RuntimeError("Positive-control decision mismatch")

    negative_metrics = [
        item
        for item in metric["metric_records"]
        if item["baseline_family"] == "grouped_shuffled"
    ]
    negative_tests = [
        item for item in paired["records"] if "grouped_shuffled" in item["hypothesis_id"]
    ]
    if (
        len(negative_metrics) != 40
        or len(negative_tests) != 20
        or {item["target_name"] for item in negative_metrics}
        != {"mu_oracle_blocks", "log_sigma_oracle"}
    ):
        raise RuntimeError("Negative-control evidence is incomplete")

    b_registration_path = (
        packages_by_label["person_b_predictions_metrics"]["package"]
        + "/registration_decision.json"
    )
    b_registration = json.loads(git_bytes(PERSON_B_OWNER_COMMIT, b_registration_path))
    if (
        b_registration["prediction_owner_status"] != "accepted"
        or b_registration["metric_owner_status"] != "accepted"
        or b_registration["metric_production_registration_allowed"] is not True
        or b_registration["acceptance_decision"] != "FAIL"
        or b_registration["unresolved_blockers"]
    ):
        raise RuntimeError("Person B registration decision is not final")

    registry_bytes = formatted_bytes(registry)
    registry_sha256 = sha256_bytes(registry_bytes)
    direct_inputs = []
    for artifact_id in import_order:
        artifact = artifact_by_id[artifact_id]
        direct_inputs.append(
            {
                "artifact_id": artifact_id,
                "artifact_type": artifact["artifact_type"],
                "byte_size": artifact["size_bytes"],
                "path": artifact_paths[artifact_id],
                "sha256": artifact["sha256"],
                "verification_mode": "local_bytes",
            }
        )
    for label, path in (
        ("post_reveal_execution_receipt", BOUNDED_ROOT / "execution_receipt.json"),
        ("final_comparison_execution_receipt", FINAL_ROOT / "execution_receipt.json"),
        ("paired_test_results", FINAL_ROOT / "paired_test_results.json"),
        ("confidence_intervals", FINAL_ROOT / "confidence_intervals.json"),
        ("layer_band_decision", FINAL_ROOT / "layer_band_decision.json"),
    ):
        direct_inputs.append(evidence_descriptor(label, path))
    direct_inputs.append(
        {
            "byte_size": len(positive_bytes),
            "evidence_id": "positive_control_decision",
            "path": f"{POSITIVE_CONTROL_AUTHORITY}:{POSITIVE_CONTROL_PATH}",
            "sha256": POSITIVE_CONTROL_SHA256,
            "verification_mode": "exact_git_object_bytes",
        }
    )

    owner_record_bindings = {
        "all_owner_statuses_final_non_placeholder": True,
        "packages": [
            {
                "commit": item["commit"],
                "inventory_sha256": item["inventory_sha256"],
                "label": item["label"],
                "owner_authority": item["authority"],
                "owner_authority_sha256": item["authority_sha256"],
                "package": item["package"],
                "registry_records_sha256": item["records_sha256"],
                "registry_trust_inputs_sha256": item["trust_sha256"],
                "validation_receipt_sha256": item["receipt_sha256"],
                "verified_file_count": len(item["verified_files"]),
            }
            for item in package_data
        ],
        "schema_id": "person-e-step4-1-owner-record-bindings-v0-1",
        "schema_version": SCHEMA_VERSION,
    }
    trust_records = {
        "artifact_byte_bindings": {
            artifact_id: {
                "byte_size": artifact_by_id[artifact_id]["size_bytes"],
                "path": artifact_paths[artifact_id],
                "sha256": artifact_by_id[artifact_id]["sha256"],
            }
            for artifact_id in import_order
        },
        "authorization_record_bindings": authorization_record_bindings,
        "schema_id": "person-e-step4-1-registry-v2-trust-records-v0-1",
        "schema_version": SCHEMA_VERSION,
        "status_record_bindings": status_record_bindings,
        "trusted_artifact_authorizations": trusted_artifact_authorizations,
        "trusted_manifest_records": trusted_manifest_records,
        "trusted_owner_authorities": trusted_owner_authorities,
    }
    registry_query_receipt = {
        "backward_final_metric_provenance": backward_query,
        "forward_activation_impact": forward_activation_query,
        "forward_frame_input_impact": forward_frame_query,
        "query_mechanics_authority": REGISTRY_QUERY_AUTHORITY,
        "registry_id": REGISTRY_ID,
        "schema_id": "person-e-step4-1-registry-v2-query-receipt-v0-1",
        "schema_version": SCHEMA_VERSION,
    }
    import_receipt = {
        "artifact_count": len(import_order),
        "byte_verification_count": len(byte_verifications),
        "dependency_prerequisite_artifact_ids": [
            FRAME_ARTIFACT_ID,
            ACTIVATION_ARTIFACT_ID,
        ],
        "import_order": import_order,
        "imported_artifact_ids": import_order,
        "manifest_count": len(manifests),
        "owner_authority_count": len(owner_authorities),
        "owner_authored_trust_records_complete": True,
        "registry_id": REGISTRY_ID,
        "registry_sha256": registry_sha256,
        "registry_v2_import_complete": True,
        "rejection_count": 0,
        "run_count": len(run_order),
        "schema_authority": REGISTRY_SCHEMA_AUTHORITY,
        "schema_id": "person-e-step4-1-registry-v2-import-receipt-v0-1",
        "schema_version": SCHEMA_VERSION,
        "scientific_execution_performed": False,
        "strict_validator_accepted": True,
        "u4_output_inspected": False,
    }
    authority_chain = {
        "person_a": {
            "owner_commit": PERSON_A_OWNER_COMMIT,
            "starting_authority": "380b9a392c7ad3a941dbdadcc777c61ed03e1206",
            "status": "accepted",
        },
        "person_b": {
            "final_comparison_authority": (
                "1b9ac2e37d245896af95a5a929774829720387db"
            ),
            "owner_commit": PERSON_B_OWNER_COMMIT,
            "status": "accepted",
        },
        "person_d": {
            "completion_authority": PERSON_D_COMPLETION_COMMIT,
            "owner_commit": PERSON_D_OWNER_COMMIT,
            "status": "accepted",
        },
        "person_e": {
            "comparison_ratification_authority": STARTING_AUTHORITY,
            "registry_query_authority": REGISTRY_QUERY_AUTHORITY,
            "registry_schema_authority": REGISTRY_SCHEMA_AUTHORITY,
        },
        "schema_id": "person-e-step4-1-final-authority-chain-v0-1",
        "schema_version": SCHEMA_VERSION,
    }
    closure_report = {
        "all_direct_input_paths_sizes_and_sha256s": direct_inputs,
        "all_qualifying_contiguous_layer_bands": [],
        "bootstrap_confidence_intervals": {
            "bootstrap_count": intervals["bootstrap_count"],
            "coverage": intervals["coverage"],
            "records": intervals["records"],
            "seed": intervals["seed"],
        },
        "decision": "FAIL",
        "decision_rationale": (
            "All integrity and control gates passed, all frozen required metrics "
            "were valid, and no contiguous band of at least two layers met every "
            "U1/U2/U3 gate."
        ),
        "final_acceptance_decision": "FAIL",
        "final_comparison_execution_receipt": final_receipt,
        "manual_u4_inspection_performed": False,
        "negative_control_results": {
            "family": "grouped_shuffled",
            "metric_records": negative_metrics,
            "no_object_control": (
                "NOT_APPLICABLE_TO_FROZEN_TEN_PILOT_PRODUCTION_SET"
            ),
            "paired_test_records": negative_tests,
            "required_targets": ["mu_oracle_blocks", "log_sigma_oracle"],
        },
        "paired_tests_and_max_t_adjusted_p_values": paired["records"],
        "per_layer_u1_u2_u3_results": layer_decision["layer_gates"],
        "person_b_comparison_contract_commit": COMPARISON_CONTRACT_COMMIT,
        "person_b_post_reveal_contract_commit": POST_REVEAL_CONTRACT_COMMIT,
        "person_d_completion_commit": PERSON_D_COMPLETION_COMMIT,
        "person_e_bounded_reveal_authorization_commit": BOUNDED_REVEAL_AUTHORITY,
        "person_e_comparison_ratification_commit": STARTING_AUTHORITY,
        "positive_control_decision": positive_control,
        "post_reveal_execution_receipt": post_reveal_receipt,
        "registry_v2_imported_artifact_ids": import_order,
        "registry_v2_registry_id_and_sha256": {
            "registry_id": REGISTRY_ID,
            "sha256": registry_sha256,
        },
        "registration_provenance_only": True,
        "schema_id": "person-e-step4-1-registry-v2-final-closure-v0-1",
        "schema_version": SCHEMA_VERSION,
        "scientific_execution_performed": False,
        "step4_1_complete": True,
        "u4_output_inspected": False,
        "unresolved_blockers": [],
        "unresolved_scientific_limitations": [
            "No qualifying contiguous layer band met every frozen U1/U2/U3 gate."
        ],
    }
    validation_receipt = {
        "acceptance_decision": "FAIL",
        "canonical_json": True,
        "closure_contract_required_fields_complete": True,
        "external_scientific_artifacts_modified": False,
        "final_comparison_controls_complete": True,
        "manual_u4_inspection_performed": False,
        "owner_authored_trust_records_complete": True,
        "person_a_owner_status": "accepted",
        "person_b_metric_owner_status": b_registration["metric_owner_status"],
        "person_b_metric_production_registration_allowed": True,
        "person_b_prediction_owner_status": b_registration[
            "prediction_owner_status"
        ],
        "person_d_owner_status": "accepted",
        "registry_v2_import_complete": True,
        "schema_id": "person-e-step4-1-registry-v2-closure-validation-v0-1",
        "schema_version": SCHEMA_VERSION,
        "scientific_execution_performed": False,
        "status": "PASS",
        "step4_1_complete": True,
        "u4_output_inspected": False,
        "unresolved_blockers": [],
    }

    required_closure_fields = set(
        read_json(
            REPOSITORY
            / "docs/status/person_e_phase4_step4_1_final_comparison_ratification_v0_1/"
            "closure_contract.json"
        )["closure_report_required_fields"]
    )
    if required_closure_fields - set(closure_report):
        raise RuntimeError("Closure report is missing required contract fields")
    if set(final_inventory["files"]) != {
        "comparison_metric_table.json",
        "confidence_intervals.json",
        "execution_receipt.json",
        "layer_band_decision.json",
        "paired_test_results.json",
        "registry_v2_import_package.json",
    }:
        raise RuntimeError("Final comparison file inventory changed")
    if set(bounded_inventory["files"]) != {
        "execution_receipt.json",
        "post_reveal_predictions.json",
    }:
        raise RuntimeError("Bounded-reveal file inventory changed")

    documents = {
        "authority_chain.json": authority_chain,
        "closure_report.json": closure_report,
        "immutable_registry_v2.json": registry,
        "owner_record_bindings.json": owner_record_bindings,
        "registry_import_receipt.json": import_receipt,
        "registry_query_receipt.json": registry_query_receipt,
        "registry_trust_records.json": trust_records,
        "validation_receipt.json": validation_receipt,
    }
    OUTPUT.mkdir(parents=True, exist_ok=False)
    for name, document in documents.items():
        (OUTPUT / name).write_bytes(formatted_bytes(document))
    files = [
        {
            "byte_size": path.stat().st_size,
            "path": path.name,
            "sha256": sha256_file(path),
        }
        for path in sorted(OUTPUT.glob("*.json"))
    ]
    inventory = {
        "algorithm": "sha256",
        "file_count": len(files),
        "files": files,
        "inventory_excludes_self": True,
        "schema_id": "person-e-step4-1-registry-v2-closure-inventory-v0-1",
        "schema_version": SCHEMA_VERSION,
    }
    (OUTPUT / "sha256_inventory.json").write_bytes(formatted_bytes(inventory))
    print(
        json.dumps(
            {
                "acceptance_decision": "FAIL",
                "artifact_count": len(import_order),
                "owner_authority_count": len(owner_authorities),
                "registry_sha256": registry_sha256,
                "registry_v2_import_complete": True,
                "status": "PASS",
                "step4_1_complete": True,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
