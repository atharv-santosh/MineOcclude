"""Build Person E's canonical Phase 6 to Step 4.1 downstream handoff.

This is provenance and execution-contract evidence only.  It reads every
upstream source through an exact Git object, records the accepted external
artifact identities without copying their bytes, and fails closed on the
known Activation Store v2 production-runner and final-fold gaps.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_REL = "docs/status/person_e_phase6_to_step4_1_handoff_v0_1"
SCHEMA_ID = "person-e-phase6-to-step4-1-handoff-v0-1"
RECORD_DATE = "2026-07-31"

PERSON_A_ACTIVATION = "55776dc88302b89b52eef483a710fbf6811cf536"
PERSON_A_EXISTING_PILOT = "e6e0340f301abb84c127034b154be55a38bdc8f6"
PERSON_A_EXPANSION_RUNNER = "c099fe970e2ea0dbf36d994923c9e40af357e585"
PERSON_B_IMPLEMENTATION = "c6f2d1d3495fa1b4a567408e1a84a5b5484e5ecb"
PERSON_B_RATIFICATION = "a24cc316ab45b0063a11141c21a76044439042a0"
PERSON_B_POSITIVE_CONTROL = "e39fef4a59142a84dfb5991d51deeb506eb23a7b"
PERSON_B_SELECTION = "19f08b2e27217b781961da8f7299e1396a3ab703"
PERSON_C_EXISTING = "f0d4e895b56fc4ca3f4805aa13b73545744af1b0"
PERSON_C_EXISTING_SOURCE = "bf09c23bb12f59acae724811eed6b82bab17c0ed"
PERSON_C_EXPANSION = "c6bff25b5ef4f5fdb0e1ef0ce0d22e3f8b5e4960"
PERSON_D_AUTHORITY = "853e0acadf050a0b1f318b399b524e57379d03bf"
PERSON_E_ACCEPTANCE = "5bbe7c7021fe3b1c4c35c78fadfbd92ab51484e8"
PERSON_E_REGISTRY_AUTHORITY = "b27d404c6aa913bac559754fa8b7accdff46e886"

A_ROOT = (
    "docs/status/phase6_runtime/"
    "person-a-phase6-ten-pilot-expansion-seed-20260725"
)
B_RATIFICATION_ROOT = (
    "docs/status/"
    "person_b_phase6_v2_source_row_canonicalization_reratification_v0_1"
)
B_RESULT_ROOT = "docs/status/person_b_phase6_step6_6_positive_control_v0_1"
B_STEP4_ROOT = "docs/status/person_b_phase4_step4_1_registry_v2_handoff_v0_1"
C_EXISTING_ROOT = "docs/status/person_c_phase4_step4_1_registry_v2_handoff_v0_1"
C_EXPANSION_ROOT = (
    "docs/status/person_c_phase6_ten_pilot_expansion_acceptance_v0_1"
)
D_STEP4_ROOT = "docs/status/person_d_phase4_step4_1_registry_v2_handoff_v0_1"
E_ACCEPTANCE_ROOT = (
    "docs/status/person_e_phase6_step6_6_provenance_acceptance_v0_1"
)
E_STEP4_ROOT = "docs/status/person_e_phase4_step4_1_slice3a_v0_1"

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
EXPECTED_CORE = [pilot for pilot in EXPECTED_PILOTS if pilot not in EXPECTED_CONTROLS]

UNRESOLVED_BLOCKERS = [
    {
        "blocker_id": "person_b_activation_store_v2_production_consumer_absent",
        "detail": (
            "The accepted Phase 6 artifacts are person-a-activation-index-v2 / "
            "person-a-activation-store-v2, while scripts/run_person_b_pilot.py "
            "joins through mineocclude.contracts.activation.validate_activation_handoff "
            "and therefore accepts only the historical v1 handoff shape. The only "
            "committed v2 execution path is the completed visible-control runner."
        ),
        "owner": "person_b",
        "required_resolution": (
            "Publish and ratify a production v2 oracle/probe consumer or an exact "
            "contract-preserving adapter before any Step 4.1 scientific execution."
        ),
    },
    {
        "blocker_id": "ten_pilot_frame_fold_manifest_absent",
        "detail": (
            "The frozen layout plan covers 15 target-present trajectories and 2,456 "
            "condition rows, but the immutable Phase 6 selection contains exactly ten "
            "pilots (five core and five controls). The historical frame-fold binder "
            "requires exact equality with all 15 planned trajectories; the v2 positive-"
            "control path validates only the five control assignments. No ratified "
            "ten-pilot production frame-fold manifest exists."
        ),
        "owner": "person_b",
        "required_resolution": (
            "Publish a sealed, ratified frame-level fold identity for exactly the "
            "accepted ten-pilot set without changing pilot membership or layout folds."
        ),
    },
    {
        "blocker_id": "production_oracle_target_absent",
        "detail": (
            "The oracle definition is frozen, but Person B's committed Step 4.1 "
            "contract records production_artifact_created=false and no real target "
            "manifest has subsequently been published."
        ),
        "owner": "person_b",
        "required_resolution": (
            "Materialize and seal the exact production oracle target after the v2 "
            "consumer/fold contract is ratified."
        ),
    },
    {
        "blocker_id": "person_d_readiness_gate_waits_for_person_b",
        "detail": (
            "Person D's immutable readiness gate requires a real sealed B frame-fold "
            "manifest and real B oracle-target document with exact matching coverage."
        ),
        "owner": "person_d",
        "required_resolution": (
            "Run the frozen D readiness gate only after the required B artifacts exist; "
            "fit no baseline unless it returns READY with zero blocked reasons."
        ),
    },
    {
        "blocker_id": "step4_1_result_trust_packages_absent",
        "detail": (
            "No production fitted-probe, prediction, accepted scientific baseline, "
            "final comparison metric table, evidence figure, or final Registry v2 "
            "trusted manifest exists yet."
        ),
        "owner": "persons_b_d_e_in_frozen_order",
        "required_resolution": (
            "Produce the frozen B then D then B outputs and submit their exact bytes or "
            "trusted receipts to Person E for final import and pass/fail closure."
        ),
    },
]


class HandoffError(RuntimeError):
    """Raised when exact committed evidence differs from this handoff."""


def fail(message: str) -> None:
    raise HandoffError(message)


def canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, allow_nan=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def git_output(*args: str) -> bytes:
    try:
        return subprocess.check_output(["git", "-C", str(ROOT), *args])
    except subprocess.CalledProcessError as error:
        fail(f"Git command failed: {' '.join(args)}: {error}")
    raise AssertionError("unreachable")


def git_show(commit: str, path: str) -> bytes:
    return git_output("show", f"{commit}:{path}")


def strict_json(raw: bytes, identity: str) -> Any:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                fail(f"Duplicate JSON key in {identity}: {key}")
            result[key] = value
        return result

    try:
        return json.loads(raw, object_pairs_hook=reject_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        fail(f"Invalid JSON in {identity}: {error}")
    raise AssertionError("unreachable")


def git_json(commit: str, path: str) -> Any:
    return strict_json(git_show(commit, path), f"{commit}:{path}")


def source_binding(commit: str, path: str, role: str) -> dict[str, Any]:
    raw = git_show(commit, path)
    binding: dict[str, Any] = {
        "byte_size": len(raw),
        "git_blob_oid": git_output("rev-parse", f"{commit}:{path}")
        .decode("ascii")
        .strip(),
        "git_commit": commit,
        "path": path,
        "role": role,
        "sha256": sha256_bytes(raw),
    }
    if path.endswith((".json", ".yaml")):
        document = strict_json(raw, f"{commit}:{path}")
        if isinstance(document, dict):
            if isinstance(document.get("schema_id"), str):
                binding["schema_id"] = document["schema_id"]
            if isinstance(document.get("schema_version"), str):
                binding["schema_version"] = document["schema_version"]
            if isinstance(document.get("analysis_config_version"), str):
                binding["analysis_config_version"] = document[
                    "analysis_config_version"
                ]
    return binding


def verify_inventory(commit: str, root: str) -> dict[str, Any]:
    inventory_path = f"{root}/sha256_inventory.json"
    inventory = git_json(commit, inventory_path)
    entries = inventory.get("files")
    if isinstance(entries, dict):
        normalized = sorted(entries.items())
    elif isinstance(entries, list):
        normalized = sorted((row["path"], row["sha256"]) for row in entries)
    else:
        fail(f"Unsupported inventory shape: {commit}:{inventory_path}")
    excludes_self = inventory.get(
        "inventory_excludes_self", inventory.get("excludes_self")
    )
    if excludes_self is not True:
        fail(f"Inventory does not exclude itself: {commit}:{inventory_path}")
    for relative, expected_sha256 in normalized:
        raw = git_show(commit, f"{root}/{relative}")
        if sha256_bytes(raw) != expected_sha256:
            fail(f"Inventory mismatch: {commit}:{root}/{relative}")
    return {
        "entry_count": len(normalized),
        "inventory": source_binding(commit, inventory_path, _role_for_commit(commit)),
        "status": "PASS",
    }


def _role_for_commit(commit: str) -> str:
    if commit in {PERSON_A_ACTIVATION, PERSON_A_EXISTING_PILOT}:
        return "person_a"
    if commit in {
        PERSON_B_POSITIVE_CONTROL,
        PERSON_B_RATIFICATION,
        PERSON_B_SELECTION,
    }:
        return "person_b"
    if commit in {PERSON_C_EXISTING, PERSON_C_EXPANSION}:
        return "person_c"
    if commit == PERSON_D_AUTHORITY:
        return "person_d"
    if commit == PERSON_E_ACCEPTANCE:
        return "person_e"
    fail(f"No role mapping for inventory commit {commit}")
    raise AssertionError("unreachable")


def _registry_package(
    *, package_commit: str, package_root: str, artifact_source_commit: str
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    document_path = f"{package_root}/registry_v2_document.json"
    trusted_path = f"{package_root}/registry_v2_trusted_verification_inputs.json"
    wrapper = git_json(package_commit, document_path)
    trusted_wrapper = git_json(package_commit, trusted_path)
    registry = wrapper["immutable_registry_document"]
    trusted = trusted_wrapper["trusted_inputs"]
    manifests = {row["manifest_id"]: row for row in registry["manifests"]}
    verifications = {
        row["artifact_id"]: row for row in registry["byte_verifications"]
    }
    bindings: dict[str, dict[str, Any]] = {}
    for artifact in registry["artifacts"]:
        artifact_id = artifact["artifact_id"]
        source_path = next(
            row["path"]
            for row in trusted_wrapper.get(
                "artifact_bytes_sources",
                [trusted_wrapper.get("artifact_bytes_source")],
            )
            if row is not None and row["artifact_id"] == artifact_id
        )
        source_raw = git_show(artifact_source_commit, source_path)
        if len(source_raw) != artifact["size_bytes"]:
            fail(f"Registry artifact byte-size mismatch: {artifact_id}")
        if sha256_bytes(source_raw) != artifact["sha256"]:
            fail(f"Registry artifact SHA-256 mismatch: {artifact_id}")
        trusted_authorization = trusted["trusted_artifact_authorizations"][
            artifact_id
        ]["authorization"]
        authorization_record_id = trusted_authorization["authorization_record_id"]
        authorization_record_bytes = trusted["trusted_authorization_record_bytes"][
            authorization_record_id
        ].encode("utf-8")
        if sha256_bytes(authorization_record_bytes) != trusted_authorization[
            "authorization_record_sha256"
        ]:
            fail(f"Authorization record mismatch: {artifact_id}")
        manifest = manifests[artifact["manifest_id"]]
        if manifest["manifest_sha256"] != artifact["manifest_sha256"]:
            fail(f"Manifest identity mismatch: {artifact_id}")
        bindings[artifact_id] = {
            "accepted_artifact": {
                "artifact_id": artifact_id,
                "artifact_schema_version": artifact["artifact_schema_version"],
                "artifact_source_commit": artifact_source_commit,
                "artifact_type": artifact["artifact_type"],
                "byte_size": artifact["size_bytes"],
                "direct_input_artifact_ids": artifact["direct_input_artifact_ids"],
                "path": source_path,
                "producing_role": "person_c",
                "sha256": artifact["sha256"],
                "uri": artifact["uri"],
            },
            "accepted_by_commit": package_commit,
            "byte_verification": verifications[artifact_id],
            "exact_artifact_authorization": trusted_authorization,
            "manifest": manifest,
            "owner_authority": trusted["trusted_owner_authorities"][
                artifact["owner_authority_id"]
            ]["authority"],
            "trusted_record_locations": {
                "authorization_json_pointer": (
                    "#/trusted_inputs/trusted_artifact_authorizations/" + artifact_id
                ),
                "authorization_record_bytes_json_pointer": (
                    "#/trusted_inputs/trusted_authorization_record_bytes/"
                    + authorization_record_id
                ),
                "manifest_json_pointer": (
                    "#/trusted_inputs/trusted_manifest_records/"
                    + artifact["manifest_id"]
                ),
                "trusted_verification_inputs": source_binding(
                    package_commit, trusted_path, "person_c"
                ),
            },
        }
    return bindings, {
        "registry_document": source_binding(package_commit, document_path, "person_c"),
        "registry_id": registry["registry_id"],
        "registry_schema_version": registry["immutable_registry_schema_version"],
        "trusted_verification_inputs": source_binding(
            package_commit, trusted_path, "person_c"
        ),
    }


def _source_registry_bindings() -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    existing, existing_package = _registry_package(
        package_commit=PERSON_C_EXISTING,
        package_root=C_EXISTING_ROOT,
        artifact_source_commit=PERSON_C_EXISTING_SOURCE,
    )
    expansion, expansion_package = _registry_package(
        package_commit=PERSON_C_EXPANSION,
        package_root=C_EXPANSION_ROOT,
        artifact_source_commit=PERSON_C_EXISTING,
    )
    merged = {**existing, **expansion}
    if list(sorted(merged)) != list(sorted(EXPECTED_PILOTS)):
        fail("Registry v2 source pilot set changed")
    return merged, [existing_package, expansion_package]


def _phase6_artifacts(
    source_registry: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    accepted = git_json(
        PERSON_E_ACCEPTANCE, f"{E_ACCEPTANCE_ROOT}/accepted_provenance_manifest.json"
    )
    a_manifest = git_json(PERSON_A_ACTIVATION, f"{A_ROOT}/artifact_manifest.json")
    a_handoff = git_json(
        PERSON_A_ACTIVATION, f"{A_ROOT}/person_e_provenance_handoff.json"
    )
    a_completion = git_json(PERSON_A_ACTIVATION, f"{A_ROOT}/completion_report.json")
    selection = git_json(
        PERSON_B_SELECTION,
        "docs/status/person_b_phase6_ten_pilot_expansion_selection_v0_1/"
        "expansion_selection_manifest.json",
    )
    if accepted["ordered_pilot_ids"] != EXPECTED_PILOTS:
        fail("Person E accepted pilot order changed")
    if selection["ordered_pilot_ids"] != EXPECTED_PILOTS:
        fail("Person B selected pilot order changed")
    if a_completion["ordered_pilot_ids"] != EXPECTED_PILOTS:
        fail("Person A completed pilot order changed")
    external_inventory_by_pilot = {
        row["trajectory_id"]: row for row in a_handoff["per_pilot_inventories"]
    }
    accepted_by_pilot = {row["trajectory_id"]: row for row in accepted["per_pilot"]}
    selected_by_pilot = {row["trajectory_id"]: row for row in selection["pilots"]}
    pilots: list[dict[str, Any]] = []
    for pilot_id in EXPECTED_PILOTS:
        inventory_path = f"{A_ROOT}/per_pilot_inventories/{pilot_id}.json"
        inventory = git_json(PERSON_A_ACTIVATION, inventory_path)
        accepted_row = accepted_by_pilot[pilot_id]
        selected_row = selected_by_pilot[pilot_id]
        external_inventory = external_inventory_by_pilot[pilot_id]
        if inventory["activation_index"]["sha256"] != accepted_row[
            "activation_index"
        ]["sha256"]:
            fail(f"Accepted activation index changed: {pilot_id}")
        if len(inventory["chunks"]) != 20:
            fail(f"Activation chunk count changed: {pilot_id}")
        if external_inventory["sha256"] != sha256_bytes(
            git_show(PERSON_A_ACTIVATION, inventory_path)
        ):
            fail(f"External inventory binding changed: {pilot_id}")
        execution_commit = (
            PERSON_A_EXISTING_PILOT
            if pilot_id == EXPECTED_PILOTS[0]
            else PERSON_A_EXPANSION_RUNNER
        )
        chunks = []
        for chunk in inventory["chunks"]:
            chunks.append(
                {
                    **chunk,
                    "producing_commit": execution_commit,
                    "producing_role": "person_a",
                    "schema_version": "person-a-activation-store-v2",
                }
            )
        pilots.append(
            {
                "activation": {
                    "accepted_by_commit": PERSON_A_ACTIVATION,
                    "activation_index": {
                        **inventory["activation_index"],
                        "producing_commit": execution_commit,
                        "producing_role": "person_a",
                        "schema_version": "person-a-activation-index-v2",
                    },
                    "activation_row_count": inventory["activation_row_count"],
                    "chunk_count": len(chunks),
                    "chunks": chunks,
                    "committed_inventory": source_binding(
                        PERSON_A_ACTIVATION, inventory_path, "person_a"
                    ),
                    "external_inventory_copy": external_inventory,
                    "producer_contract_commit": PERSON_A_ACTIVATION,
                    "runtime_execution_commit": execution_commit,
                    "status": inventory["status"],
                },
                "condition_role": inventory["condition_role"],
                "control": inventory["control"],
                "fold_idx": inventory["fold_idx"],
                "frame_count": inventory["frame_count"],
                "layout_id": inventory["layout_id"],
                "selection_binding": {
                    "capture_package": selected_row["capture_package"],
                    "condition_role": selected_row["condition_role"],
                    "fold_idx": selected_row["fold_idx"],
                    "order": selected_row["order"],
                },
                "source_input_registry_binding": source_registry[pilot_id],
                "trajectory_id": pilot_id,
            }
        )
    if sum(row["activation"]["activation_row_count"] for row in pilots) != 37_480:
        fail("Activation row total changed")
    if sum(row["activation"]["chunk_count"] for row in pilots) != 200:
        fail("Activation chunk total changed")
    external_report = git_json(
        PERSON_E_ACCEPTANCE, f"{E_ACCEPTANCE_ROOT}/source_inventory.json"
    )["external_person_b_report"]
    result_inventory = git_json(
        PERSON_B_POSITIVE_CONTROL, f"{B_RESULT_ROOT}/sha256_inventory.json"
    )
    decision = git_json(
        PERSON_B_POSITIVE_CONTROL, f"{B_RESULT_ROOT}/positive_control_decision.json"
    )
    lineage = git_json(
        PERSON_B_POSITIVE_CONTROL, f"{B_RESULT_ROOT}/lineage_receipt.json"
    )
    if decision["positive_control_pass"] is not True:
        fail("Positive-control PASS changed")
    if decision["hidden_state_interpretation_authorized"] is not False:
        fail("Positive control expanded hidden-state authority")
    if decision["numeric_pass_threshold_added"] is not False:
        fail("Positive control added an unfrozen threshold")
    artifact_manifest = {
        "accepted_activation_index": {
            "accepted_by_commit": PERSON_A_ACTIVATION,
            "byte_size": a_manifest["combined_activation_index"]["byte_size"],
            "path": a_manifest["combined_activation_index"]["external_path"],
            "producing_commit": PERSON_A_ACTIVATION,
            "producing_role": "person_a",
            "schema_version": "person-a-combined-activation-index-v2",
            "sha256": a_manifest["combined_activation_index"]["sha256"],
        },
        "accepted_pilot_count": 10,
        "accepted_placeholder_count": 0,
        "activation_chunk_count": 200,
        "activation_row_count": 37_480,
        "external_final_report": {
            "accepted_by_commit": PERSON_A_ACTIVATION,
            "byte_size": a_manifest["final_report"]["byte_size"],
            "path": a_manifest["final_report"]["external_path"],
            "producing_commit": PERSON_A_ACTIVATION,
            "producing_role": "person_a",
            "schema_version": "1.0",
            "sha256": a_manifest["final_report"]["sha256"],
        },
        "pilots": pilots,
        "positive_control": {
            "decision": decision["decision"],
            "decision_evidence": source_binding(
                PERSON_B_POSITIVE_CONTROL,
                f"{B_RESULT_ROOT}/positive_control_decision.json",
                "person_b",
            ),
            "direct_lineage": source_binding(
                PERSON_B_POSITIVE_CONTROL,
                f"{B_RESULT_ROOT}/lineage_receipt.json",
                "person_b",
            ),
            "external_report": {
                **external_report,
                "producing_commit": PERSON_B_POSITIVE_CONTROL,
                "producing_role": "person_b",
                "schema_version": "1.0",
            },
            "frozen_target_name": decision["frozen_target_name"],
            "frozen_threshold_policy": decision["frozen_threshold_policy"],
            "input_hash": lineage["input_hash"],
            "metrics": source_binding(
                PERSON_B_POSITIVE_CONTROL,
                f"{B_RESULT_ROOT}/positive_control_metrics.json",
                "person_b",
            ),
            "pass": True,
            "predictions": source_binding(
                PERSON_B_POSITIVE_CONTROL,
                f"{B_RESULT_ROOT}/positive_control_predictions.json",
                "person_b",
            ),
            "sha256_inventory": source_binding(
                PERSON_B_POSITIVE_CONTROL,
                f"{B_RESULT_ROOT}/sha256_inventory.json",
                "person_b",
            ),
            "step6_6_complete": True,
            "threshold": {
                "numeric_pass_threshold_added": False,
                "policy": decision["frozen_threshold_policy"],
            },
            "validation_receipt": source_binding(
                PERSON_B_POSITIVE_CONTROL,
                f"{B_RESULT_ROOT}/validation_receipt.json",
                "person_b",
            ),
            "verified_result_file_hashes": result_inventory["files"],
        },
        "schema_id": f"{SCHEMA_ID}-phase6-artifact-handoff",
        "schema_version": "1.0",
    }
    evidence = [
        source_binding(
            PERSON_E_ACCEPTANCE,
            f"{E_ACCEPTANCE_ROOT}/accepted_provenance_manifest.json",
            "person_e",
        ),
        source_binding(
            PERSON_E_ACCEPTANCE,
            f"{E_ACCEPTANCE_ROOT}/phase6_closure_decision.json",
            "person_e",
        ),
        source_binding(
            PERSON_E_ACCEPTANCE,
            f"{E_ACCEPTANCE_ROOT}/registry_v2_validation_receipt.json",
            "person_e",
        ),
        source_binding(
            PERSON_E_ACCEPTANCE,
            f"{E_ACCEPTANCE_ROOT}/validation_receipt.json",
            "person_e",
        ),
        source_binding(
            PERSON_A_ACTIVATION, f"{A_ROOT}/person_b_step6_6_positive_control_handoff.json", "person_a"
        ),
        source_binding(
            PERSON_A_ACTIVATION, f"{A_ROOT}/person_e_provenance_handoff.json", "person_a"
        ),
        source_binding(
            PERSON_B_RATIFICATION,
            f"{B_RATIFICATION_ROOT}/superseding_execution_authorization.json",
            "person_b",
        ),
        source_binding(
            PERSON_B_RATIFICATION,
            f"{B_RATIFICATION_ROOT}/real_visible_control_regression_receipt.json",
            "person_b",
        ),
    ]
    return artifact_manifest, evidence


def _authority_binding() -> dict[str, Any]:
    return {
        "branch_authorities_observed_after_fetch": {
            "person_b": {
                "branch": "role/person-b-analysis",
                "commit": PERSON_B_POSITIVE_CONTROL,
                "remote_ref": "origin/role/person-b-analysis",
            },
            "person_d": {
                "branch": "role/person-d-baselines",
                "commit": PERSON_D_AUTHORITY,
                "remote_ref": "origin/role/person-d-baselines",
            },
            "person_e": {
                "branch": "role/person-e-operations",
                "handoff_parent_commit": PERSON_E_ACCEPTANCE,
                "handoff_revision_semantics": (
                    "The Git commit containing this package is the handoff authority; "
                    "the exact parent authority is recorded here to avoid a circular "
                    "self-hash field."
                ),
                "remote_ref_before_handoff": "origin/role/person-e-operations",
                "remote_tip_before_handoff": PERSON_E_ACCEPTANCE,
            },
        },
        "completed_authorities": {
            "person_a_existing_pilot_completion_commit": PERSON_A_EXISTING_PILOT,
            "person_a_ten_pilot_activation_commit": PERSON_A_ACTIVATION,
            "person_b_final_source_row_implementation_commit": PERSON_B_IMPLEMENTATION,
            "person_b_final_source_row_ratification_commit": PERSON_B_RATIFICATION,
            "person_b_step6_6_pass_commit": PERSON_B_POSITIVE_CONTROL,
            "person_b_ten_pilot_selection_commit": PERSON_B_SELECTION,
            "person_c_ten_pilot_input_acceptance_commit": PERSON_C_EXPANSION,
            "person_e_phase6_acceptance_commit": PERSON_E_ACCEPTANCE,
            "person_e_registry_v2_authority_commit": PERSON_E_REGISTRY_AUTHORITY,
        },
        "handoff_owner": "person_e",
        "record_date": RECORD_DATE,
        "schema_id": f"{SCHEMA_ID}-authority-binding",
        "schema_version": "1.0",
        "state": {
            "accepted_pilot_count": 10,
            "accepted_placeholder_count": 0,
            "activation_chunk_count": 200,
            "activation_row_count": 37_480,
            "hidden_state_interpretation_authorized": False,
            "no_wall_control_layout_count": 5,
            "person_a_reextraction_authorized": False,
            "phase6_artifacts_immutable": True,
            "phase6_complete": True,
            "phase6_reexecution_required": False,
            "registry_v2_trust_chain_complete": True,
            "step4_1_contract_complete": False,
            "step4_1_scientific_execution_performed": False,
            "step6_6_complete": True,
            "u4_output_inspected": False,
            "visible_control_row_count": 1_000,
        },
        "unresolved_blockers": UNRESOLVED_BLOCKERS,
    }


def _step4_contract() -> dict[str, Any]:
    config_path = "configs/analysis/core.yaml"
    config = git_json(PERSON_B_POSITIVE_CONTROL, config_path)
    target_contract_path = f"{B_STEP4_ROOT}/oracle_target_contract.json"
    target_contract = git_json(PERSON_B_POSITIVE_CONTROL, target_contract_path)
    fold_contract_path = f"{B_STEP4_ROOT}/sealed_fold_split_identity.json"
    fold_contract = git_json(PERSON_B_POSITIVE_CONTROL, fold_contract_path)
    metric_contract_path = f"{B_STEP4_ROOT}/metric_table_input_contract.json"
    metric_contract = git_json(PERSON_B_POSITIVE_CONTROL, metric_contract_path)
    fold_plan_path = "data/person_b/phase6_c_intake/layout_fold_plan.json"
    fold_plan = git_json(PERSON_B_POSITIVE_CONTROL, fold_plan_path)
    if fold_plan["artifact_hash"] != "ca265b64935880aede8c3bb8b6060cdda17c23932e5e98878a3fcf8ee5341f01":
        fail("Frozen layout fold artifact identity changed")
    if fold_plan["trajectory_count"] != 15 or fold_plan["accepted_row_count"] != 2456:
        fail("Frozen layout plan cardinality changed")
    d_input_path = f"{D_STEP4_ROOT}/scientific_baseline_input_contract.json"
    d_gate_path = f"{D_STEP4_ROOT}/readiness_gate_contract.json"
    d_runbook_path = f"{D_STEP4_ROOT}/execution_runbook.json"
    d_input = git_json(PERSON_D_AUTHORITY, d_input_path)
    d_gate = git_json(PERSON_D_AUTHORITY, d_gate_path)
    d_runbook = git_json(PERSON_D_AUTHORITY, d_runbook_path)
    return {
        "comparison_and_acceptance": {
            "engineering_gate_rule": (
                "A failed runtime, alignment, oracle, positive-control, or "
                "reproducibility gate is an invalid pipeline, not a negative "
                "scientific finding."
            ),
            "frozen_mvp_criteria": {
                "U1_green": (
                    "A contiguous band of at least two layers has held-out R2 greater "
                    "than zero, beats last-seen, and beats grouped shuffle at p<0.01."
                ),
                "U2_green": (
                    "Partial correlation of decoded/oracle spread controlling tau has "
                    "a hierarchical 95% bootstrap CI above zero; average absolute "
                    "50/80/95% coverage error is at most 0.10 and improves on time-only "
                    "and visible-history-q baselines."
                ),
                "U3_green": (
                    "Positive hidden-time growth, decoded/oracle slope ratio in "
                    "[0.5, 2.0], and a reveal decrease with CI below zero and median "
                    "spread reduction of at least 25%."
                ),
                "decision_rule": {
                    "GREEN": (
                        "Engineering gates pass; U1 and U2 are green; U3 is "
                        "directionally correct."
                    ),
                    "RED": (
                        "Runtime, alignment, oracle, positive control, detector, or "
                        "reproduction fails; do not interpret negative science."
                    ),
                    "YELLOW": (
                        "Engineering and controls pass, but a frozen scientific "
                        "criterion fails cleanly; report the valid alternative result."
                    ),
                },
            },
            "metric_families": metric_contract["metric_families"],
            "metric_rules": metric_contract["metric_rules"],
            "positive_control_override": {
                "authority_commit": PERSON_B_POSITIVE_CONTROL,
                "decision": "PASS_FROZEN_VISIBLE_POSITION_POSITIVE_CONTROL",
                "numeric_pass_threshold_added": False,
                "policy": "human_scientific_gate_no_unfrozen_numeric_threshold",
                "rule": (
                    "The exact completed Phase 6 decision is controlling; this handoff "
                    "does not reapply the older planning-only R2 threshold."
                ),
            },
            "resampling_rules": metric_contract["resampling_rules"],
            "source": source_binding(
                PERSON_B_POSITIVE_CONTROL, "PERSON_B_MVP_ROADMAP.md", "person_b"
            ),
        },
        "execution_order": [
            {
                "order": 1,
                "owner": "person_b",
                "sequence_id": "PERSON_B_V2_CONSUMER_AND_TEN_PILOT_FRAME_FOLD_RATIFICATION",
                "task": (
                    "Close and ratify the v2 production-consumer and exact ten-pilot "
                    "frame-fold blockers without changing the frozen science."
                ),
            },
            {
                "order": 2,
                "owner": "person_b",
                "sequence_id": "PERSON_B_ORACLE_PROBE_PREDICTIONS",
                "task": (
                    "Materialize the production oracle, bound frame folds, fitted "
                    "probes, and OOF predictions under the frozen target/config."
                ),
            },
            {
                "order": 3,
                "owner": "person_d",
                "sequence_id": "PERSON_D_BASELINES",
                "task": (
                    "Validate B's real target/fold package, require READY, then produce "
                    "accepted scientific baseline prediction documents."
                ),
            },
            {
                "order": 4,
                "owner": "person_b",
                "sequence_id": "PERSON_B_FINAL_COMPARISON_METRICS",
                "task": (
                    "Compute the final matched-row comparison and metric table from "
                    "accepted OOF probe and D baseline predictions."
                ),
            },
            {
                "order": 5,
                "owner": "person_e",
                "sequence_id": "PERSON_E_REGISTRY_IMPORT_EVIDENCE_AND_DECISION",
                "task": (
                    "Verify bytes/receipts and direct lineage, import complete Registry "
                    "v2 trust packages, produce required evidence, and issue the formal "
                    "Step 4.1 pass/fail decision."
                ),
            },
        ],
        "fold_contract": {
            "final_frame_fold_manifest": {
                "status": "ABSENT_BLOCKING_PERSON_B_AND_PERSON_D",
                "required_identity_key": ["trajectory_id", "model_frame_idx"],
                "required_scope": "exact accepted ten-pilot set",
            },
            "frozen_layout_plan": {
                "accepted_row_count": fold_plan["accepted_row_count"],
                "artifact_hash": fold_plan["artifact_hash"],
                "artifact_id": fold_plan["artifact_id"],
                "file": source_binding(
                    PERSON_B_POSITIVE_CONTROL, fold_plan_path, "person_b"
                ),
                "layout_assignments": fold_plan["layout_assignments"],
                "n_splits": fold_plan["n_splits"],
                "seed": fold_plan["seed"],
                "strategy": fold_plan["strategy"],
                "trajectory_count": fold_plan["trajectory_count"],
            },
            "frozen_split_definition": fold_contract["split_contract"],
            "source": source_binding(
                PERSON_B_POSITIVE_CONTROL, fold_contract_path, "person_b"
            ),
        },
        "person_b_scope": {
            "authorized_now": [
                "Provenance-only intake and verification of the exact accepted ten-pilot sources, indexes, and chunks.",
                "Owner preparation needed to close the v2 consumer and ten-pilot frame-fold blockers without changing targets, folds, metrics, thresholds, or membership.",
            ],
            "blocked_scientific_scope_after_owner_gates": [
                "Production oracle-target materialization.",
                "Hidden-mean and hidden-spread fitted probes and OOF predictions.",
                "Final matched-row metric/comparison computation after Person D returns accepted baselines.",
            ],
            "consumable_artifacts": [
                "Exact ten accepted Person C capture packages and their Registry v2 trust records.",
                "Exact ten Person A Activation Store v2 indexes and 200 external chunks.",
                "The immutable Person B Phase 6 positive-control PASS package.",
                "The frozen target/config contracts and layout-to-fold assignments.",
            ],
            "expected_output_package": "docs/status/person_b_phase4_step4_1_production_handoff_v0_1/",
            "forbidden_actions": [
                "Do not change targets, pilot membership, row selection, layouts, folds, thresholds, metrics, or accepted source identities.",
                "Do not reinterpret Activation Store v2 as the historical v1 handoff.",
                "Do not use U4 outcomes or authorize hidden-state interpretation before all exact gates pass.",
                "Do not alter or overwrite Phase 6 activation artifacts.",
            ],
            "required_outputs": [
                "oracle_target",
                "sealed ten-pilot frame fold manifest",
                "joined frame table and selection/filter/intake/oracle receipts",
                "fitted_probe",
                "prediction",
                "runner and environment receipts",
                "D request with exact row/fold/target identity",
                "metric_table after accepted D baselines",
                "complete Registry v2 owner trust package and direct-input lineage",
            ],
            "runner_contract": {
                "current_production_runner": "scripts/run_person_b_pilot.py",
                "current_runner_status": "BLOCKED_INCOMPATIBLE_WITH_ACCEPTED_ACTIVATION_STORE_V2",
                "required_argument_sources_after_resolution": {
                    "activation_handoff": "ratified exact ten-pilot v2 production input",
                    "artifact_id_prefix": "new append-only Person B production run identity",
                    "control_gate": "exact passing control bundle accepted for the same production input identity",
                    "layout_fold_plan": fold_plan_path,
                    "output_directory": "new no-overwrite Person B production output root",
                    "scope": ["hidden_mean", "hidden_spread"],
                    "selection_source": "data/person_b/phase6_c_intake/condition_selection_source.json",
                    "target_document": "new sealed production oracle target",
                },
                "preparation_tasks": [
                    "scripts/build_person_b_state_input.py",
                    "scripts/build_oracle_targets.py",
                    "scripts/build_person_b_d_request.py",
                    "scripts/build_person_b_e_registration.py",
                ],
            },
            "source": source_binding(
                PERSON_B_POSITIVE_CONTROL,
                f"{B_STEP4_ROOT}/fitted_probe_input_contract.json",
                "person_b",
            ),
        },
        "person_d_scope": {
            "activation_artifacts_consumed_directly": False,
            "authorized_now": [
                "Verify the handoff authority and prepare for the frozen readiness-gate call.",
                "Consume no scientific inputs until B publishes a real sealed frame-fold manifest and real oracle target.",
            ],
            "baseline_families": [
                {"baseline": "last_seen", "role": "memory heuristic floor", "targets": ["mu_oracle_blocks"]},
                {"baseline": "constant_velocity", "role": "Regime A reference", "targets": ["mu_oracle_blocks"]},
                {"baseline": "grouped_shuffled", "role": "trajectory-level chance floor", "targets": ["mu_oracle_blocks", "log_sigma_oracle"]},
                {"baseline": "time_only", "role": "clock-substitution test", "targets": ["log_sigma_oracle"]},
                {"baseline": "explicit_feature", "role": "non-privileged feature ceiling", "targets": ["mu_oracle_blocks"]},
                {"baseline": "raw_pixel", "role": "visual-leakage/scene-cue check", "targets": ["mu_oracle_blocks"]},
                {"baseline": "visible_history_q", "role": "fair spread baseline", "targets": ["log_sigma_oracle"]},
                {"baseline": "known_q_analytic", "role": "privileged non-fair reference ceiling", "targets": ["log_sigma_oracle"]},
            ],
            "consumable_inputs_after_b_gate": [
                "Exact accepted source contexts for the ten pilots.",
                "Exact sealed Person B frame-fold manifest.",
                "Exact sealed Person B oracle-target document.",
                "Literal frozen analysis config bytes.",
                "Accepted preprocessed source frames and model/preprocess identities only where the raw-pixel contract requires them.",
            ],
            "direct_input_hashes": [
                "fold_manifest_hash",
                "oracle_target_hash",
                "config_hash",
            ],
            "expected_output_package": "docs/status/person_d_phase4_step4_1_scientific_baseline_v0_1/",
            "forbidden_actions": [
                "Do not consume activation indexes or chunks directly.",
                "Do not assign or recompute folds.",
                "Do not promote docs/status/person_d_real_pilot_baseline_preview.json.",
                "Do not fit when the readiness gate is BLOCKED or carries any reason.",
                "Do not change target, row, fold, comparison, or missingness rules.",
            ],
            "readiness_gate": {
                "function": d_gate["gate_function"],
                "invocation_contract": {
                    "keyword_arguments": {
                        "candidate_scientific_use": "accepted",
                        "fold_manifest": {
                            "required_source": "Person B sealed production frame-fold manifest",
                            "status": "ABSENT_BLOCKING_EXECUTION",
                        },
                        "oracle_target_document": {
                            "required_source": "Person B sealed production oracle-target document",
                            "status": "ABSENT_BLOCKING_EXECUTION",
                        },
                    },
                    "positional_arguments": [
                        {
                            "name": "contexts",
                            "required_source": "exact accepted ten-pilot source contexts with Person B fold assignments",
                        }
                    ],
                },
                "required_result": d_gate["required_result"],
            },
            "required_outputs": [
                "Accepted person-b-baseline-input-v0.1 prediction documents with exact matching row/fold coverage.",
                "Fit and missingness/exclusion receipts and matched-row validation.",
                "Runner and environment receipts.",
                "Owner status, exact-artifact authorization, trusted manifest, byte verification receipt, and direct-input hashes.",
            ],
            "runner_contract": {
                "authoritative_steps": [
                    {
                        "action": "Verify the exact handoff, input, and code authorities before consuming any scientific inputs.",
                        "person_b_starting_authority": PERSON_B_POSITIVE_CONTROL,
                        "person_d_starting_authority": PERSON_D_AUTHORITY,
                        "step": 0,
                    },
                    {
                        "action": "Validate the sealed frame-fold manifest and oracle-target document with the committed Person D validators.",
                        "fold_validator": "mineocclude.probes.splits.validate_fold_manifest",
                        "oracle_validator": "mineocclude.oracle.schema.validate_oracle_target_document",
                        "step": 1,
                    },
                    {
                        "action": "Run the committed scientific readiness gate and require READY with an empty reason list.",
                        "function": d_gate["gate_function"],
                        "required_result": d_gate["required_result"],
                        "step": 2,
                    },
                    {
                        "action": "Fit the frozen baseline families only after the readiness gate passes.",
                        "step": 3,
                    },
                    {
                        "action": "Mint a new append-only production artifact identity and emit prediction, fit, missingness, runner, and environment receipts.",
                        "step": 4,
                    },
                    {
                        "action": "Build and validate the Person D scientific baseline document against exact Person B row, fold, and target identities.",
                        "step": 5,
                    },
                    {
                        "action": "Publish the complete Registry v2 trust package with all direct-input hashes and byte-verification evidence.",
                        "step": 6,
                    },
                    {
                        "action": "Append accepted production status without promoting preview artifacts or overwriting prior artifacts.",
                        "step": 7,
                    },
                ],
                "production_cli_status": "NO_SINGLE_PRODUCTION_CLI_FROZEN;_USE_THE_COMMITTED_API_RUNBOOK",
                "source": source_binding(PERSON_D_AUTHORITY, d_runbook_path, "person_d"),
            },
            "source": source_binding(PERSON_D_AUTHORITY, d_input_path, "person_d"),
        },
        "schema_id": f"{SCHEMA_ID}-step4-1-execution-contract",
        "schema_version": "1.0",
        "target_contract": {
            "config": source_binding(
                PERSON_B_POSITIVE_CONTROL, config_path, "person_b"
            ),
            "definitions": config["targets"],
            "information_set": target_contract["information_set"],
            "method": target_contract["method"],
            "production_target_manifest": {
                "status": "ABSENT_BLOCKING_PERSON_B_AND_PERSON_D"
            },
            "row_contract": target_contract["row_contract"],
            "source": source_binding(
                PERSON_B_POSITIVE_CONTROL, target_contract_path, "person_b"
            ),
        },
        "unresolved_blockers": UNRESOLVED_BLOCKERS,
    }


def _closure_requirements() -> dict[str, Any]:
    b_req_path = f"{E_STEP4_ROOT}/owner_handoffs/person_b_requirements.json"
    d_req_path = f"{E_STEP4_ROOT}/owner_handoffs/person_d_requirements.json"
    b_req = git_json(PERSON_E_ACCEPTANCE, b_req_path)
    d_req = git_json(PERSON_E_ACCEPTANCE, d_req_path)
    return {
        "closure_claimed": False,
        "final_person_e_inputs": {
            "from_person_b": {
                "required_artifacts": [
                    *b_req["required_output_artifacts"],
                    "sealed ten-pilot frame fold manifest",
                    "joined/filter/intake/oracle audit receipts",
                    "runner and environment receipt",
                    "matched-row comparison results after D",
                    "evidence/figure source package where the frozen closure chain requires it",
                ],
                "source": source_binding(
                    PERSON_E_ACCEPTANCE, b_req_path, "person_e"
                ),
            },
            "from_person_d": {
                "required_artifacts": [
                    *d_req["required_output_artifacts"],
                    "prediction byte sizes and SHA-256 identities",
                    "fit, missingness/exclusion, and exact coverage receipts",
                    "runner and environment receipt",
                ],
                "source": source_binding(
                    PERSON_E_ACCEPTANCE, d_req_path, "person_e"
                ),
            },
        },
        "minimum_trust_records_for_each_accepted_output": [
            "trusted owner authority",
            "verified owner status record bytes",
            "trusted exact-artifact authorization",
            "verified authorization record bytes",
            "trusted manifest with exact artifact ID, type, schema, byte size, and SHA-256",
            "verified local bytes or trusted external receipt",
            "exact direct-input artifact IDs and hashes",
        ],
        "person_e_final_actions": [
            "Verify every B/D output byte size and SHA-256 or its trusted external receipt.",
            "Validate fold, target, pilot, source, prediction, baseline, and metric direct lineage.",
            "Import only complete accepted owner-authored trust packages into Registry v2.",
            "Build the required evidence/figure package only from accepted inputs and bind every displayed value to a locked result.",
            "Publish the final trusted manifest and formal Step 4.1 pass/fail decision.",
        ],
        "retention_requirements": [
            {
                "path": "/home/sagemaker-user/person-a-phase6-approved-inputs",
                "requirement": "Retain immutable source/input trees used by the accepted extraction until final Step 4.1 closure and durable Registry v2 receipt verification.",
            },
            {
                "path": "/home/sagemaker-user/person-a-phase6-approved-outputs",
                "requirement": "Retain all accepted indexes, all 200 chunks, inventories, bounded audits, logs, and reports without overwrite, relocation, or deletion.",
            },
            {
                "path": "/home/sagemaker-user/person-b-phase6-approved-outputs/person-b-phase6-v2-positive-control-step6-6",
                "requirement": "Retain the exact external positive-control report through final closure; its byte size and SHA-256 remain controlling.",
            },
        ],
        "schema_id": f"{SCHEMA_ID}-person-e-closure-requirements",
        "schema_version": "1.0",
        "step4_1_scientific_execution_performed": False,
        "u4_output_inspected": False,
    }


def _check_starting_authorities() -> None:
    expected = {
        "refs/remotes/origin/role/person-b-analysis": PERSON_B_POSITIVE_CONTROL,
        "refs/remotes/origin/role/person-d-baselines": PERSON_D_AUTHORITY,
        "refs/remotes/origin/role/person-e-operations": PERSON_E_ACCEPTANCE,
    }
    for ref, commit in expected.items():
        actual = git_output("rev-parse", ref).decode("ascii").strip()
        if actual != commit:
            fail(f"Starting authority changed: {ref}={actual}, expected {commit}")
    branch = git_output("branch", "--show-current").decode("utf-8").strip()
    head = git_output("rev-parse", "HEAD").decode("ascii").strip()
    if branch != "role/person-e-operations" or head != PERSON_E_ACCEPTANCE:
        fail(f"Wrong starting checkout: branch={branch}, HEAD={head}")


def generate() -> dict[str, bytes]:
    inventories = [
        verify_inventory(PERSON_E_ACCEPTANCE, E_ACCEPTANCE_ROOT),
        verify_inventory(PERSON_A_ACTIVATION, A_ROOT),
        verify_inventory(PERSON_B_RATIFICATION, B_RATIFICATION_ROOT),
        verify_inventory(PERSON_B_POSITIVE_CONTROL, B_RESULT_ROOT),
        verify_inventory(PERSON_B_SELECTION, "docs/status/person_b_phase6_ten_pilot_expansion_selection_v0_1"),
        verify_inventory(PERSON_C_EXISTING, C_EXISTING_ROOT),
        verify_inventory(PERSON_C_EXPANSION, C_EXPANSION_ROOT),
        verify_inventory(PERSON_D_AUTHORITY, D_STEP4_ROOT),
    ]
    source_registry, registry_packages = _source_registry_bindings()
    phase6, phase6_evidence = _phase6_artifacts(source_registry)
    phase6["committed_evidence"] = phase6_evidence
    phase6["registry_v2_source_packages"] = registry_packages
    phase6["retention_policy_reference"] = (
        "person_e_closure_requirements.json#/retention_requirements"
    )
    package: dict[str, bytes] = {
        "authority_binding.json": canonical_json(_authority_binding()),
        "person_e_closure_requirements.json": canonical_json(
            _closure_requirements()
        ),
        "phase6_artifact_handoff.json": canonical_json(phase6),
        "step4_1_execution_contract.json": canonical_json(_step4_contract()),
    }
    package["validation_receipt.json"] = canonical_json(
        {
            "accepted_pilot_count": 10,
            "accepted_placeholder_count": 0,
            "activation_chunk_count": 200,
            "activation_row_count": 37_480,
            "canonical_json_generated": True,
            "exact_authority_git_objects_resolved": True,
            "external_artifacts_copied_into_git": False,
            "focused_validation_only": True,
            "hidden_state_interpretation_performed": False,
            "inventory_packages_verified": inventories,
            "person_b_handoff_ready": False,
            "person_d_handoff_ready": False,
            "phase6_artifacts_immutable": True,
            "phase6_reexecution_required": False,
            "record_date": RECORD_DATE,
            "registry_v2_source_trust_chains_resolved": True,
            "schema_id": f"{SCHEMA_ID}-validation-receipt",
            "schema_version": "1.0",
            "scientific_metrics_calculated": False,
            "step4_1_contract_complete": False,
            "step4_1_scientific_execution_performed": False,
            "status": "PASS_WITH_EXPLICIT_EXECUTION_BLOCKERS",
            "u4_output_inspected": False,
            "unresolved_blocker_ids": [
                row["blocker_id"] for row in UNRESOLVED_BLOCKERS
            ],
        }
    )
    package["sha256_inventory.json"] = canonical_json(
        {
            "file_count": len(package) + 1,
            "files": {
                name: sha256_bytes(data) for name, data in sorted(package.items())
            },
            "inventory_excludes_self": True,
            "schema_id": f"{SCHEMA_ID}-sha256-inventory",
            "schema_version": "1.0",
        }
    )
    return package


def build(out_dir: Path) -> None:
    package = generate()
    out_dir.mkdir(parents=True, exist_ok=True)
    existing = {path.name for path in out_dir.iterdir()} if out_dir.is_dir() else set()
    unexpected = existing - set(package)
    if unexpected:
        fail(f"Unexpected existing package paths: {sorted(unexpected)}")
    for name, data in package.items():
        (out_dir / name).write_bytes(data)


def validate(package_dir: Path) -> None:
    expected = generate()
    present = (
        {path.name for path in package_dir.iterdir()}
        if package_dir.is_dir()
        else set()
    )
    if present != set(expected):
        fail(f"Package file set mismatch: {sorted(present)}")
    for name, expected_bytes in expected.items():
        actual = (package_dir / name).read_bytes()
        strict_json(actual, str(package_dir / name))
        if actual != expected_bytes:
            fail(f"Package bytes differ from exact Git-object rebuild: {name}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("build", "validate"))
    parser.add_argument("--check-starting-authorities", action="store_true")
    parser.add_argument("--out-dir", type=Path, default=ROOT / PACKAGE_REL)
    args = parser.parse_args()
    try:
        if args.check_starting_authorities:
            _check_starting_authorities()
        if args.mode == "build":
            build(args.out_dir)
        else:
            validate(args.out_dir)
    except HandoffError as error:
        raise SystemExit(f"FAIL: {error}") from error
    print(f"PASS: {args.mode} {args.out_dir}")


if __name__ == "__main__":
    main()
