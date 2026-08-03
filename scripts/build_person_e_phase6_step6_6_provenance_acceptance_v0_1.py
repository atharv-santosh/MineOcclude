"""Build and validate Person E's bounded Phase 6 Step 6.6 acceptance.

The package verifies upstream evidence from exact Git objects, validates the
ten Person C inputs with the frozen Registry v2 validator, re-hashes Person A's
external Activation Store v2 artifacts, and binds the frozen Person B result.
It does not create upstream owner authority or inspect U4.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mineocclude.contracts.rollout_registry import (
    validate_immutable_run_artifact_registry,
)

SCHEMA_ID = "person-e-phase6-step6-6-provenance-acceptance-v0-1"
PKG_REL = "docs/status/person_e_phase6_step6_6_provenance_acceptance_v0_1"
PERSON_E_REGISTRY_AUTHORITY = "b27d404c6aa913bac559754fa8b7accdff46e886"
PERSON_C_EXPANSION = "c6bff25b5ef4f5fdb0e1ef0ce0d22e3f8b5e4960"
PERSON_C_EXISTING = "f0d4e895b56fc4ca3f4805aa13b73545744af1b0"
PERSON_C_EXISTING_SOURCE = "bf09c23bb12f59acae724811eed6b82bab17c0ed"
PERSON_A_COMPLETION = "55776dc88302b89b52eef483a710fbf6811cf536"
PERSON_B_IMPLEMENTATION = "c6f2d1d3495fa1b4a567408e1a84a5b5484e5ecb"
PERSON_B_RATIFICATION = "a24cc316ab45b0063a11141c21a76044439042a0"
PERSON_B_POSITIVE_CONTROL = "e39fef4a59142a84dfb5991d51deeb506eb23a7b"

C_EXPANSION_ROOT = "docs/status/person_c_phase6_ten_pilot_expansion_acceptance_v0_1"
C_EXISTING_ROOT = "docs/status/person_c_phase4_step4_1_registry_v2_handoff_v0_1"
A_ROOT = "docs/status/phase6_runtime/person-a-phase6-ten-pilot-expansion-seed-20260725"
B_RATIFICATION_ROOT = (
    "docs/status/person_b_phase6_v2_source_row_canonicalization_reratification_v0_1"
)
B_RESULT_ROOT = "docs/status/person_b_phase6_step6_6_positive_control_v0_1"
B_EXTERNAL_REPORT = Path(
    "/home/sagemaker-user/person-b-phase6-approved-outputs/"
    "person-b-phase6-v2-positive-control-step6-6/"
    "person_b_step6_6_positive_control.json"
)

EXPECTED_PILOTS = [
    "layout_00_ep9403",
    "layout_00_ep9441",
    "layout_01_ep9405",
    "layout_01_ep9442",
    "layout_02_ep9407",
    "layout_02_ep9432",
    "layout_03_ep9404",
    "layout_03_ep9443",
    "layout_04_ep9406",
    "layout_04_ep9444",
]
EXPECTED_CONTROLS = [
    "layout_00_ep9441",
    "layout_01_ep9442",
    "layout_02_ep9432",
    "layout_03_ep9443",
    "layout_04_ep9444",
]
EXPECTED_EXTERNAL_REPORT_SHA256 = (
    "91254b04549745e2f4c8084aa6290dfa5b653c2f407ece8d62589b48d9832bb8"
)
EXPECTED_EXTERNAL_REPORT_SIZE = 50_568_852
FROZEN_VALIDATOR_SHA256 = (
    "386a6bce4f5ba727aa51b40c69ef444c0d984984697da63f6ea4045a44c07356"
)


class AcceptanceError(RuntimeError):
    """Fail-closed acceptance error."""


def fail(message: str) -> None:
    raise AcceptanceError(message)


def canonical_json(document: Any) -> bytes:
    return (
        json.dumps(
            document,
            allow_nan=False,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        while block := handle.read(8 * 1024 * 1024):
            size += len(block)
            digest.update(block)
    return size, digest.hexdigest()


def git_show(commit: str, path: str) -> bytes:
    try:
        return subprocess.check_output(
            ["git", "-C", str(ROOT), "show", f"{commit}:{path}"]
        )
    except subprocess.CalledProcessError as exc:
        fail(f"missing exact Git object {commit}:{path}: {exc}")
    raise AssertionError("unreachable")


def load_json_bytes(raw: bytes, identity: str) -> Any:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                fail(f"duplicate JSON key in {identity}: {key}")
            result[key] = value
        return result

    try:
        return json.loads(raw, object_pairs_hook=reject_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        fail(f"invalid UTF-8 JSON in {identity}: {exc}")
    raise AssertionError("unreachable")


def git_json(commit: str, path: str, *, require_canonical: bool = True) -> Any:
    raw = git_show(commit, path)
    document = load_json_bytes(raw, f"{commit}:{path}")
    if require_canonical and canonical_json(document) != raw:
        fail(f"noncanonical JSON Git object: {commit}:{path}")
    return document


def verify_git_inventory(commit: str, root: str) -> dict[str, Any]:
    inventory_path = f"{root}/sha256_inventory.json"
    inventory = git_json(commit, inventory_path)
    entries = inventory.get("files")
    if isinstance(entries, dict):
        normalized = sorted(entries.items())
        expected_file_count = len(normalized) + 1
    elif isinstance(entries, list):
        normalized = sorted((row["path"], row["sha256"]) for row in entries)
        expected_file_count = len(normalized)
    else:
        fail(f"unsupported inventory shape: {commit}:{inventory_path}")
    if inventory.get("inventory_excludes_self") is not True:
        fail(f"inventory must exclude itself: {commit}:{inventory_path}")
    if "file_count" in inventory and inventory["file_count"] != expected_file_count:
        fail(f"inventory file_count mismatch: {commit}:{inventory_path}")
    canonical_json_count = 1
    for relative, expected_hash in normalized:
        raw = git_show(commit, f"{root}/{relative}")
        if sha256_bytes(raw) != expected_hash:
            fail(f"Git-object inventory mismatch: {commit}:{root}/{relative}")
        if relative.endswith(".json"):
            document = load_json_bytes(raw, f"{commit}:{root}/{relative}")
            if canonical_json(document) != raw:
                fail(f"noncanonical inventoried JSON: {commit}:{root}/{relative}")
            canonical_json_count += 1
    return {
        "canonical_json_file_count": canonical_json_count,
        "inventory_file_count": inventory.get("file_count", expected_file_count),
        "inventory_path": inventory_path,
        "inventory_sha256": sha256_bytes(git_show(commit, inventory_path)),
    }


def _trusted_registry_arguments(wrapper: dict[str, Any]) -> dict[str, Any]:
    trusted = wrapper["trusted_inputs"]
    return {
        "trusted_owner_authorities": trusted["trusted_owner_authorities"],
        "trusted_status_record_bytes": {
            key: value.encode("utf-8")
            for key, value in trusted["trusted_status_record_bytes"].items()
        },
        "trusted_artifact_authorizations": trusted["trusted_artifact_authorizations"],
        "trusted_authorization_record_bytes": {
            key: value.encode("utf-8")
            for key, value in trusted["trusted_authorization_record_bytes"].items()
        },
        "trusted_manifest_records": trusted["trusted_manifest_records"],
        "trusted_artifact_receipts": trusted["trusted_artifact_receipts"],
    }


def verify_c_registry(
    *, package_commit: str, package_root: str, artifact_source_commit: str
) -> dict[str, Any]:
    document_wrapper = git_json(
        package_commit, f"{package_root}/registry_v2_document.json"
    )
    trusted_wrapper = git_json(
        package_commit,
        f"{package_root}/registry_v2_trusted_verification_inputs.json",
    )
    document = document_wrapper["immutable_registry_document"]
    sources = trusted_wrapper.get("artifact_bytes_sources")
    if sources is None:
        sources = [trusted_wrapper["artifact_bytes_source"]]
    artifact_bytes: dict[str, bytes] = {}
    for source in sources:
        raw = git_show(artifact_source_commit, source["path"])
        if len(raw) != source.get("size_bytes", source.get("byte_size")):
            fail(f"Person C Registry v2 source size mismatch: {source['artifact_id']}")
        if sha256_bytes(raw) != source["sha256"]:
            fail(f"Person C Registry v2 source hash mismatch: {source['artifact_id']}")
        artifact_bytes[source["artifact_id"]] = raw
    result = validate_immutable_run_artifact_registry(
        document,
        artifact_bytes_by_id=artifact_bytes,
        **_trusted_registry_arguments(trusted_wrapper),
    )
    if not result.accepted or result.rejections:
        reasons = "; ".join(
            f"{reason.code.value}: {reason.message}" for reason in result.rejections
        )
        fail(f"Person C Registry v2 rejection: {reasons}")
    return {
        "accepted_artifact_count": len(document["artifacts"]),
        "accepted_placeholder_count": 0,
        "artifact_ids": sorted(artifact_bytes),
        "registry_id": document["registry_id"],
        "rejection_count": 0,
    }


def verify_person_a() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    completion = git_json(PERSON_A_COMPLETION, f"{A_ROOT}/completion_report.json")
    validation = git_json(PERSON_A_COMPLETION, f"{A_ROOT}/validation_receipt.json")
    manifest = git_json(PERSON_A_COMPLETION, f"{A_ROOT}/artifact_manifest.json")
    if completion["ordered_pilot_ids"] != EXPECTED_PILOTS:
        fail("Person A pilot order changed")
    required_completion = {
        "accepted_pilot_count": 10,
        "actual_activation_row_count": 37_480,
        "duplicate_activation_row_count": 0,
        "missing_activation_row_count": 0,
        "nonfinite_activation_count": 0,
        "no_wall_control_count": 5,
        "pooling_audit_pass": True,
        "repeatability_audit_pass": True,
        "source_identity_join_pass": True,
        "step6_6_complete": False,
        "u4_output_inspected": False,
    }
    for key, value in required_completion.items():
        if completion.get(key) != value:
            fail(f"Person A completion mismatch for {key}")
    if completion["no_wall_control_pilots"] != EXPECTED_CONTROLS:
        fail("Person A no-wall control set changed")
    if validation.get("activation_chunk_hash_count") != 200:
        fail("Person A activation chunk count changed")
    if validation.get("activation_index_hash_count") != 10:
        fail("Person A activation index count changed")
    if not all(
        validation.get(key) is value
        for key, value in {
            "canonical_json_pass": True,
            "combined_activation_index_identities_unique": True,
            "inventory_pass": True,
            "scientific_completion_audit_pass": True,
            "u4_output_inspected": False,
        }.items()
    ):
        fail("Person A committed validation receipt is not passing")

    per_pilot: list[dict[str, Any]] = []
    total_rows = 0
    total_chunks = 0
    for pilot_id in EXPECTED_PILOTS:
        relative = f"{A_ROOT}/per_pilot_inventories/{pilot_id}.json"
        inventory = git_json(PERSON_A_COMPLETION, relative)
        allowed_status = (
            inventory["status"] == "PASS"
            or (
                pilot_id == EXPECTED_PILOTS[0]
                and inventory["status"] == "REUSED_EXACT_EXISTING_ARTIFACTS"
                and inventory.get("existing_pilot_reextracted") is False
            )
        )
        if inventory["trajectory_id"] != pilot_id or not allowed_status:
            fail(f"Person A per-pilot identity mismatch: {pilot_id}")
        index = inventory["activation_index"]
        index_path = Path(index["path"])
        size, digest = sha256_file(index_path)
        if size != index["byte_size"] or digest != index["sha256"]:
            fail(f"Person A activation index byte mismatch: {pilot_id}")
        chunk_rows = []
        for chunk in inventory["chunks"]:
            chunk_path = Path(chunk["path"])
            chunk_size, chunk_digest = sha256_file(chunk_path)
            if chunk_size != chunk["byte_size"] or chunk_digest != chunk["sha256"]:
                fail(f"Person A activation chunk byte mismatch: {chunk['chunk_id']}")
            chunk_rows.append(
                {
                    "byte_size": chunk_size,
                    "chunk_id": chunk["chunk_id"],
                    "row_count": chunk["row_count"],
                    "sha256": chunk_digest,
                }
            )
        row_count = inventory["activation_row_count"]
        total_rows += row_count
        total_chunks += len(chunk_rows)
        per_pilot.append(
            {
                "activation_index": {
                    "byte_size": size,
                    "sha256": digest,
                },
                "activation_row_count": row_count,
                "chunks": chunk_rows,
                "condition_role": inventory["condition_role"],
                "control": inventory["control"],
                "fold_idx": inventory["fold_idx"],
                "trajectory_id": pilot_id,
            }
        )
    if total_rows != 37_480 or total_chunks != 200:
        fail("Person A external activation totals changed")

    for key in ("combined_activation_index", "final_report"):
        row = manifest[key]
        path = Path(row.get("external_path", row.get("path")))
        size, digest = sha256_file(path)
        if size != row["byte_size"] or digest != row["sha256"]:
            fail(f"Person A external {key} byte mismatch")
    return (
        {
            "activation_chunk_count": total_chunks,
            "activation_index_count": len(per_pilot),
            "activation_row_count": total_rows,
            "combined_activation_index_sha256": manifest["combined_activation_index"][
                "sha256"
            ],
            "final_report_sha256": manifest["final_report"]["sha256"],
        },
        per_pilot,
    )


def verify_person_b() -> dict[str, Any]:
    owner = git_json(
        PERSON_B_RATIFICATION, f"{B_RATIFICATION_ROOT}/owner_reratification.json"
    )
    regression = git_json(
        PERSON_B_RATIFICATION,
        f"{B_RATIFICATION_ROOT}/real_visible_control_regression_receipt.json",
    )
    authorization = git_json(
        PERSON_B_RATIFICATION,
        f"{B_RATIFICATION_ROOT}/superseding_execution_authorization.json",
    )
    if owner["implementation_commit"] != PERSON_B_IMPLEMENTATION:
        fail("Person B ratification implementation binding changed")
    if owner["person_a_ten_pilot_commit"] != PERSON_A_COMPLETION:
        fail("Person B ratification Person A binding changed")
    if owner["supersedes_ratification_commit"] != (
        "03e8cdb8673f2260f42b8554b00ac30e3e4f7c8b"
    ):
        fail("Person B supersession binding changed")
    if not owner["previous_execution_authorization_superseded"]:
        fail("Person B previous execution authorization remains active")
    if owner["e_schema_change_required"] is not False:
        fail("unexpected Person E schema change requirement")
    required_regression = {
        "activation_chunk_count_verified": 200,
        "activation_index_count_verified": 10,
        "activation_row_count_verified": 37_480,
        "core_visible_substitution_count": 0,
        "exact_source_identity_join_pass": True,
        "hidden_row_count": 0,
        "layout_fold_group_count": 5,
        "no_wall_trajectory_count": 5,
        "probe_fit_executed": False,
        "random_split_used": False,
        "registry_digest_substitution_count": 0,
        "visible_control_rows_matched": 1000,
        "visible_control_rows_tested": 1000,
    }
    for key, value in required_regression.items():
        if regression.get(key) != value:
            fail(f"Person B ratification regression mismatch for {key}")
    if not all(
        authorization.get(key) is value
        for key, value in {
            "frozen_fold_unchanged": True,
            "frozen_target_unchanged": True,
            "frozen_threshold_unchanged": True,
            "hidden_state_interpretation_authorized": False,
            "positive_control_execution_authorized": True,
            "u4_output_inspected": False,
        }.items()
    ):
        fail("Person B superseding execution authorization changed")

    execution = git_json(
        PERSON_B_POSITIVE_CONTROL, f"{B_RESULT_ROOT}/execution_receipt.json"
    )
    decision = git_json(
        PERSON_B_POSITIVE_CONTROL, f"{B_RESULT_ROOT}/positive_control_decision.json"
    )
    validation = git_json(
        PERSON_B_POSITIVE_CONTROL, f"{B_RESULT_ROOT}/validation_receipt.json"
    )
    lineage = git_json(
        PERSON_B_POSITIVE_CONTROL, f"{B_RESULT_ROOT}/lineage_receipt.json"
    )
    metrics = git_json(
        PERSON_B_POSITIVE_CONTROL, f"{B_RESULT_ROOT}/positive_control_metrics.json"
    )
    predictions = git_json(
        PERSON_B_POSITIVE_CONTROL,
        f"{B_RESULT_ROOT}/positive_control_predictions.json",
    )
    report_size, report_hash = sha256_file(B_EXTERNAL_REPORT)
    if (
        report_size != EXPECTED_EXTERNAL_REPORT_SIZE
        or report_hash != EXPECTED_EXTERNAL_REPORT_SHA256
    ):
        fail("external Person B positive-control report byte mismatch")
    raw_report = load_json_bytes(B_EXTERNAL_REPORT.read_bytes(), str(B_EXTERNAL_REPORT))
    if raw_report["u4_output_inspected"] is not False:
        fail("Person B raw report indicates U4 inspection")
    if raw_report["hidden_state_interpretation_authorized"] is not False:
        fail("Person B raw report authorizes hidden-state interpretation")
    if raw_report["person_b_owner_ratification_commit"] != PERSON_B_RATIFICATION:
        fail("Person B raw report ratification binding changed")
    raw_layers = raw_report["positive_control_results"]
    if len(raw_layers) != 20 or len(metrics["layers"]) != 20:
        fail("Person B layer count changed")
    if len(predictions["layers"]) != 20:
        fail("Person B prediction layer count changed")
    all_prediction_identities: list[str] = []
    finite_prediction_count = 0
    for raw_layer, metric_layer, prediction_layer in zip(
        raw_layers, metrics["layers"], predictions["layers"], strict=True
    ):
        for key in ("hook_site", "layer_idx", "matrix_hash"):
            if (
                raw_layer[key] != prediction_layer[key]
                or raw_layer[key] != metric_layer[key]
            ):
                fail(f"Person B layer identity mismatch: {key}")
        if raw_layer["oof_predictions"] != prediction_layer["oof_predictions"]:
            fail("Person B bounded predictions differ from raw report")
        if raw_layer["r2"] != metric_layer["global"]["r2"]:
            fail("Person B bounded R2 differs from raw report")
        if raw_layer["mse_blocks2"] != metric_layer["global"]["mse_blocks2"]:
            fail("Person B bounded MSE differs from raw report")
        values = prediction_layer["oof_predictions"]
        identities = prediction_layer["row_identity_sha256"]
        if len(values) != 1000 or len(identities) != 1000:
            fail("Person B per-layer visible-control row count changed")
        if len(set(identities)) != 1000:
            fail("Person B per-layer activation row identities are not unique")
        all_prediction_identities.extend(identities)
        if not all(
            isinstance(value, (int, float)) and math.isfinite(value) for value in values
        ):
            fail("Person B non-finite positive-control prediction")
        finite_prediction_count += len(values)
    if finite_prediction_count != 20_000:
        fail("Person B finite prediction count changed")
    if len(set(all_prediction_identities)) != 20_000:
        fail("Person B combined activation row identities are not unique")
    if not all(
        decision.get(key) is value
        for key, value in {
            "hidden_state_interpretation_authorized": False,
            "positive_control_pass": True,
            "step6_6_complete": True,
            "u4_output_inspected": False,
        }.items()
    ):
        fail("Person B scientific decision is not a passing visible control")
    if decision["frozen_target_name"] != "x_true_blocks":
        fail("Person B frozen target changed")
    if decision["numeric_pass_threshold_added"] is not False:
        fail("Person B added an unratified numeric threshold")
    if not all(
        validation.get(key) is value
        for key, value in {
            "exact_source_identity_join_pass": True,
            "frozen_fold_verified": True,
            "frozen_target_verified": True,
            "frozen_threshold_verified": True,
            "hidden_state_interpretation_performed": False,
            "positive_control_pass": True,
            "source_row_canonicalization_verified": True,
            "u4_output_inspected": False,
        }.items()
    ):
        fail("Person B validation receipt changed")
    source_contract = lineage["source_row_canonicalization"]
    if source_contract != raw_report["source_row_canonicalization"]:
        fail("Person B source-row contract differs between raw and bounded evidence")
    if source_contract["producer_commit"] != PERSON_A_COMPLETION:
        fail("Person B source-row producer commit changed")
    if source_contract["registry_digest_substitution_count"] != 0:
        fail("Person B used a Registry digest substitution")
    if execution["ratification_commit"] != PERSON_B_RATIFICATION:
        fail("Person B execution receipt ratification changed")
    if execution["implementation_commit"] != PERSON_B_IMPLEMENTATION:
        fail("Person B execution receipt implementation changed")
    return {
        "external_report_byte_size": report_size,
        "external_report_sha256": report_hash,
        "finite_prediction_count": finite_prediction_count,
        "layer_count": 20,
        "positive_control_pass": True,
        "registry_digest_substitution_count": 0,
        "visible_control_row_count": 1000,
    }


def generate(out_dir: Path | None = None) -> dict[str, bytes]:
    validator_bytes = git_show(
        PERSON_E_REGISTRY_AUTHORITY,
        "src/mineocclude/contracts/rollout_registry.py",
    )
    if sha256_bytes(validator_bytes) != FROZEN_VALIDATOR_SHA256:
        fail("frozen Registry v2 validator hash changed")

    source_packages = {
        "person_c_existing": verify_git_inventory(PERSON_C_EXISTING, C_EXISTING_ROOT),
        "person_c_expansion": verify_git_inventory(
            PERSON_C_EXPANSION, C_EXPANSION_ROOT
        ),
        "person_a_completion": verify_git_inventory(PERSON_A_COMPLETION, A_ROOT),
        "person_b_ratification": verify_git_inventory(
            PERSON_B_RATIFICATION, B_RATIFICATION_ROOT
        ),
        "person_b_positive_control": verify_git_inventory(
            PERSON_B_POSITIVE_CONTROL, B_RESULT_ROOT
        ),
    }
    c_existing = verify_c_registry(
        package_commit=PERSON_C_EXISTING,
        package_root=C_EXISTING_ROOT,
        artifact_source_commit=PERSON_C_EXISTING_SOURCE,
    )
    c_expansion = verify_c_registry(
        package_commit=PERSON_C_EXPANSION,
        package_root=C_EXPANSION_ROOT,
        artifact_source_commit=PERSON_C_EXISTING,
    )
    if c_existing["artifact_ids"] != [EXPECTED_PILOTS[0]]:
        fail("existing Person C Registry v2 pilot changed")
    if c_expansion["artifact_ids"] != sorted(EXPECTED_PILOTS[1:]):
        fail("Person C expansion Registry v2 pilots changed")
    person_a, per_pilot = verify_person_a()
    person_b = verify_person_b()

    package_files: dict[str, bytes] = {}
    package_files["authority_binding.json"] = canonical_json(
        {
            "claims": {
                "hidden_state_interpretation_authorized": False,
                "project_integration_claimed": False,
                "step4_1_complete_claimed": False,
                "u4_output_inspected": False,
            },
            "person_a_completion_commit": PERSON_A_COMPLETION,
            "person_b_implementation_commit": PERSON_B_IMPLEMENTATION,
            "person_b_positive_control_commit": PERSON_B_POSITIVE_CONTROL,
            "person_b_source_row_ratification_commit": PERSON_B_RATIFICATION,
            "person_c_expansion_acceptance_commit": PERSON_C_EXPANSION,
            "person_c_existing_pilot_acceptance_commit": PERSON_C_EXISTING,
            "person_e_registry_v2_authority_commit": PERSON_E_REGISTRY_AUTHORITY,
            "schema_id": f"{SCHEMA_ID}-authority-binding",
            "schema_version": "1.0",
        }
    )
    package_files["accepted_provenance_manifest.json"] = canonical_json(
        {
            "accepted_pilot_count": 10,
            "accepted_placeholder_count": 0,
            "activation_chunk_count": person_a["activation_chunk_count"],
            "activation_index_count": person_a["activation_index_count"],
            "activation_row_count": person_a["activation_row_count"],
            "combined_activation_index_sha256": person_a[
                "combined_activation_index_sha256"
            ],
            "no_wall_control_pilot_ids": EXPECTED_CONTROLS,
            "ordered_pilot_ids": EXPECTED_PILOTS,
            "per_pilot": per_pilot,
            "schema_id": f"{SCHEMA_ID}-accepted-provenance-manifest",
            "schema_version": "1.0",
            "visible_control_row_count": 1000,
        }
    )
    package_files["registry_v2_validation_receipt.json"] = canonical_json(
        {
            "accepted_placeholder_count": 0,
            "existing_input_registry": c_existing,
            "expansion_input_registry": c_expansion,
            "frozen_validator_commit": PERSON_E_REGISTRY_AUTHORITY,
            "frozen_validator_sha256": FROZEN_VALIDATOR_SHA256,
            "registry_v2_schema_version": "mineocclude-immutable-registry-v2.0",
            "registry_v2_trust_chain_complete": True,
            "schema_change_required": False,
            "schema_id": f"{SCHEMA_ID}-registry-v2-validation-receipt",
            "schema_version": "1.0",
            "status": "PASS",
            "ten_input_registry_artifact_count": 10,
            "total_rejection_count": 0,
            "upstream_owner_authority_fabricated_by_person_e": False,
        }
    )
    package_files["phase6_closure_decision.json"] = canonical_json(
        {
            "accepted_pilot_count": 10,
            "accepted_placeholder_count": 0,
            "decision": "ACCEPT_TEN_PILOT_PHASE6_STEP6_6_PROVENANCE_AND_CLOSE_PHASE6",
            "hidden_state_interpretation_authorized": False,
            "owner": "person_e",
            "phase6_complete": True,
            "positive_control_pass": True,
            "project_integration_claimed": False,
            "schema_id": f"{SCHEMA_ID}-phase6-closure-decision",
            "schema_version": "1.0",
            "step4_1_complete_claimed": False,
            "step6_6_complete": True,
            "ten_pilot_expansion_complete": True,
            "u4_output_inspected": False,
        }
    )
    package_files["source_inventory.json"] = canonical_json(
        {
            "external_person_b_report": {
                "byte_size": person_b["external_report_byte_size"],
                "path": str(B_EXTERNAL_REPORT),
                "sha256": person_b["external_report_sha256"],
            },
            "packages": [
                {
                    "commit": commit,
                    "inventory_path": row["inventory_path"],
                    "inventory_sha256": row["inventory_sha256"],
                    "name": name,
                }
                for name, commit, row in (
                    (
                        "person_c_existing",
                        PERSON_C_EXISTING,
                        source_packages["person_c_existing"],
                    ),
                    (
                        "person_c_expansion",
                        PERSON_C_EXPANSION,
                        source_packages["person_c_expansion"],
                    ),
                    (
                        "person_a_completion",
                        PERSON_A_COMPLETION,
                        source_packages["person_a_completion"],
                    ),
                    (
                        "person_b_ratification",
                        PERSON_B_RATIFICATION,
                        source_packages["person_b_ratification"],
                    ),
                    (
                        "person_b_positive_control",
                        PERSON_B_POSITIVE_CONTROL,
                        source_packages["person_b_positive_control"],
                    ),
                )
            ],
            "schema_id": f"{SCHEMA_ID}-source-inventory",
            "schema_version": "1.0",
        }
    )
    package_files["validation_receipt.json"] = canonical_json(
        {
            "accepted_pilot_count": 10,
            "accepted_placeholder_count": 0,
            "activation_chunk_count": 200,
            "activation_index_count": 10,
            "activation_row_count": 37_480,
            "canonical_json_and_sha256_inventories_verified": True,
            "complete_direct_lineage_verified": True,
            "duplicate_activation_row_count": 0,
            "exact_source_row_producer_digests_verified": True,
            "finite_prediction_count": person_b["finite_prediction_count"],
            "frozen_fold_verified": True,
            "frozen_target_verified": True,
            "frozen_threshold_verified": True,
            "hidden_state_interpretation_performed": False,
            "identity_collision_count": 0,
            "missing_activation_row_count": 0,
            "no_wall_control_pilot_count": 5,
            "nonfinite_activation_count": 0,
            "person_a_artifacts_verified": True,
            "person_b_positive_control_verified": True,
            "person_b_source_row_ratification_verified": True,
            "positive_control_pass": person_b["positive_control_pass"],
            "prediction_layer_count": person_b["layer_count"],
            "registry_digest_substitution_count": person_b[
                "registry_digest_substitution_count"
            ],
            "registry_v2_trust_chain_complete": True,
            "schema_id": f"{SCHEMA_ID}-validation-receipt",
            "schema_version": "1.0",
            "status": "PASS",
            "u4_output_inspected": False,
            "visible_control_row_count": person_b["visible_control_row_count"],
        }
    )
    inventory = {
        relative: sha256_bytes(data) for relative, data in sorted(package_files.items())
    }
    package_files["sha256_inventory.json"] = canonical_json(
        {
            "file_count": len(package_files) + 1,
            "files": inventory,
            "inventory_excludes_self": True,
            "schema_id": f"{SCHEMA_ID}-sha256-inventory",
            "schema_version": "1.0",
        }
    )
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        for relative, data in package_files.items():
            (out_dir / relative).write_bytes(data)
    return package_files


def validate(package_dir: Path) -> None:
    expected = generate()
    present = (
        {path.name for path in package_dir.iterdir()} if package_dir.is_dir() else set()
    )
    if present != set(expected):
        fail(f"acceptance package file set mismatch: {sorted(present)}")
    for relative, expected_bytes in expected.items():
        if (package_dir / relative).read_bytes() != expected_bytes:
            fail(f"acceptance package byte drift: {relative}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("build", "validate"))
    parser.add_argument("--out-dir", type=Path, default=ROOT / PKG_REL)
    args = parser.parse_args()
    try:
        if args.mode == "build":
            files = generate(args.out_dir)
            print(
                f"BUILD OK: {len(files)} files; 10 accepted pilots; "
                "0 placeholders; Phase 6 complete"
            )
        else:
            validate(args.out_dir)
            print("VALIDATE OK: exact Phase 6 Step 6.6 provenance acceptance")
    except (AcceptanceError, FileNotFoundError, KeyError, TypeError, ValueError) as exc:
        print(f"FAIL-CLOSED: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
