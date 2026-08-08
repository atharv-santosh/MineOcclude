#!/usr/bin/env python
"""Validate Person B's Phase-6 production-run authorization package.

This re-derives the decision from frozen evidence rather than trusting the
published document. It fails loudly if the authorization ever drifts from the
authorities it claims to rest on, if frozen history was rewritten, or if the
authorization silently widened beyond the single named run identity.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mineocclude.analysis.manifests import validate_sealed_artifact  # noqa: E402

PACKAGE_DIRECTORY = (
    "docs/status/person_b_phase6_production_run_authorization_v0_1"
)
PACKAGE = ROOT / PACKAGE_DIRECTORY

RUN_ID = "mineocclude-run-ea6169430d693f8adcd16a23a62c4422"
SUPERSEDED_RUN_ID = "mineocclude-run-836009cb74647b413ebc6f40218bc5bf"
PERSON_A_COMMIT = "ecdf3178154e594b06d1d4326993754068cae039"

DECISION_DOCUMENT = "authorization_decision.json"
AUTHORITY_BINDING = "authority_binding.json"
PRECONDITION_VERIFICATION = "precondition_verification.json"
VALIDATION_RECEIPT = "validation_receipt.json"
SHA256_INVENTORY = "sha256_inventory.json"

B_TO_A_HANDOFF = (
    "docs/status/person_b_66_cell_oracle_target_v0_1/"
    "b_to_a_successor_handoff.json"
)
PHASE6_CONDITIONS = (
    "docs/status/person_b_phase4_step4_1_registry_v2_handoff_v0_1/"
    "phase6_authorization_conditions.json"
)

class AuthorizationValidationError(AssertionError):
    """Raised when the published authorization does not hold up."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AuthorizationValidationError(message)


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def read_local(relative_path: str) -> bytes:
    return (ROOT / relative_path).read_bytes()


def read_foreign_blob(commit: str, relative_path: str) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(ROOT), "show", f"{commit}:{relative_path}"],
        capture_output=True,
    )
    require(
        result.returncode == 0,
        f"Could not read {relative_path} at {commit}: "
        f"{result.stderr.decode('utf-8', 'replace').strip()}",
    )
    return result.stdout


def load_package_document(name: str) -> dict[str, Any]:
    return json.loads((PACKAGE / name).read_bytes())


def validate_inventory() -> None:
    inventory = load_package_document(SHA256_INVENTORY)
    require(
        inventory["inventory_excludes_self"] is True,
        "Inventory must exclude itself.",
    )
    recorded = {entry["path"] for entry in inventory["files"]}
    expected = {
        f"{PACKAGE_DIRECTORY}/{name}"
        for name in (
            DECISION_DOCUMENT,
            AUTHORITY_BINDING,
            PRECONDITION_VERIFICATION,
            VALIDATION_RECEIPT,
        )
    }
    require(
        recorded == expected,
        f"Inventory covers {sorted(recorded)}, expected {sorted(expected)}.",
    )
    require(
        inventory["file_count"] == len(inventory["files"]),
        "Inventory file_count disagrees with the recorded file list.",
    )
    for entry in inventory["files"]:
        payload = read_local(entry["path"])
        require(
            sha256_bytes(payload) == entry["sha256"],
            f"{entry['path']} does not match its recorded SHA-256.",
        )
        require(
            len(payload) == entry["byte_size"],
            f"{entry['path']} does not match its recorded byte size.",
        )


def validate_sealed_documents() -> dict[str, dict[str, Any]]:
    documents = {
        DECISION_DOCUMENT: (
            load_package_document(DECISION_DOCUMENT),
            "person_b_phase6_production_run_authorization",
        ),
        AUTHORITY_BINDING: (
            load_package_document(AUTHORITY_BINDING),
            "person_b_phase6_production_run_authority_binding",
        ),
        PRECONDITION_VERIFICATION: (
            load_package_document(PRECONDITION_VERIFICATION),
            "person_b_phase6_production_run_precondition_verification",
        ),
    }
    for name, (document, expected_type) in documents.items():
        try:
            validate_sealed_artifact(document, expected_type=expected_type)
        except Exception as error:  # noqa: BLE001 - re-raised with context
            raise AuthorizationValidationError(
                f"{name} is not a valid sealed artifact: {error}"
            ) from error
    return {name: document for name, (document, _) in documents.items()}


def validate_run_identity(decision: dict[str, Any]) -> None:
    require(
        decision["run_id"] == RUN_ID,
        f"Decision names {decision['run_id']!r}, expected {RUN_ID!r}.",
    )
    require(
        decision["authorized"] is True
        and decision["person_a_phase6_authorized"] is True
        and decision["person_b_phase6_signoff"] is True
        and decision["signed_for_this_run_id"] is True,
        "Decision must carry an explicit affirmative authorization.",
    )
    require(
        decision["authorization_scope"]["authorized_run_id"] == RUN_ID,
        "Authorization scope must name the exact run identity.",
    )
    require(
        decision["superseded_run_id_not_authorized"] == SUPERSEDED_RUN_ID,
        "The superseded run identity must stay explicitly unauthorized.",
    )
    require(
        RUN_ID not in decision["superseded_run_id_not_authorized"],
        "Authorized and superseded run identities must be distinct.",
    )


def validate_frozen_history_preserved(decision: dict[str, Any]) -> None:
    require(
        decision["frozen_step_4_1_decision"] == "FAIL",
        "Step 4.1 must remain FAIL.",
    )
    require(
        decision["frozen_step_4_1_decision_unchanged"] is True,
        "Step 4.1 must be declared unchanged.",
    )
    require(
        decision["historical_evidence_rewritten"] is False,
        "Historical evidence must not be rewritten.",
    )
    require(
        decision["u4_authorized"] is False
        and decision["u4_output_inspected"] is False,
        "U4 must remain unauthorized and uninspected.",
    )
    require(
        decision["foreign_branch_merged"] is False,
        "No peer branch may be merged.",
    )

    handoff = json.loads(read_local(B_TO_A_HANDOFF))
    require(
        handoff["u4_status"]["CURRENT_66_CELL_U4_REVEAL_ELIGIBLE"] is False,
        "The frozen handoff must still report U4 as reveal-ineligible.",
    )

    # The governing conditions file must be byte-identical to what the
    # decision claims to supersede: superseding a field is not editing a file.
    superseded = decision["supersedes_field"]
    conditions_bytes = read_local(superseded["path"])
    require(
        sha256_bytes(conditions_bytes) == superseded["sha256"],
        "The superseded governing document's bytes changed; it must stay frozen.",
    )
    conditions = json.loads(conditions_bytes)
    require(
        conditions["person_a_phase6_authorized"] is False,
        "The frozen conditions file must still record its original false value.",
    )
    require(
        superseded["previous_value"] is False and superseded["field"]
        == "person_a_phase6_authorized",
        "The supersession record must name the exact field and prior value.",
    )
    require(
        conditions["silent_authorization_forbidden"] is True,
        "silent_authorization_forbidden must remain in force.",
    )


def validate_scope_is_narrow(decision: dict[str, Any]) -> None:
    scope = decision["authorization_scope"]
    require(
        decision["aggregate_phase6_runtime_authorized"] is False,
        "Person B must not declare the aggregate authorization.",
    )
    require(
        decision["self_authorization_by_person_a_forbidden"] is True,
        "Person A self-authorization must stay forbidden.",
    )
    not_authorized = " ".join(scope["not_authorized"]).lower()
    for phrase in ("acceptance", "u4", "step 4.1", "integration readiness"):
        require(
            phrase in not_authorized,
            f"Scope must explicitly withhold {phrase!r}.",
        )
    require(
        decision["scientific_execution_performed_by_person_b"] is False,
        "This decision must not claim Person B ran any science.",
    )


def validate_preconditions_against_evidence(
    precondition_document: dict[str, Any],
) -> None:
    require(
        precondition_document["all_conditions_satisfied"] is True,
        "Every governing precondition must be satisfied.",
    )
    conditions = json.loads(read_local(PHASE6_CONDITIONS))
    declared = conditions["additional_prerequisites_for_a_new_versioned_decision"]
    require(
        len(precondition_document["conditions"]) == len(declared),
        f"Expected {len(declared)} resolved conditions, found "
        f"{len(precondition_document['conditions'])}.",
    )
    for entry in precondition_document["conditions"]:
        require(
            entry["satisfied"] is True,
            f"Condition {entry['condition_id']} is not satisfied.",
        )
    require(
        not precondition_document["oracle_package_inventory_mismatches"],
        "The sealed oracle package no longer rehashes to its recorded digests.",
    )

    # Re-derive the extraction identity agreement instead of trusting it.
    handoff = json.loads(read_local(B_TO_A_HANDOFF))
    required = handoff["required_activation_index_fields"]["required_values"]
    policy = handoff["extraction_row_policy"]
    config = json.loads(
        read_foreign_blob(
            PERSON_A_COMMIT,
            "docs/status/person_a_66_cell_preprocessed_media_v0_2/"
            "successor_extraction_config.json",
        )
    )

    checks = {
        "model_hash": (required["model_hash"], config["model"]["model_hash"]),
        "preprocess_hash": (
            required["preprocess_hash"],
            config["preprocessing"]["preprocess_hash"],
        ),
        "accepted_manifest_hash": (
            required["accepted_manifest_hash"],
            config["successor_run_identity"]["accepted_manifest_sha256"],
        ),
        "hook_site": (required["hook_site"], config["extraction"]["hook_site"]),
        "vector_width": (
            required["vector_width"],
            config["extraction"]["vector_width"],
        ),
        "stored_dtype": (
            required["stored_dtype"],
            config["extraction"]["stored_dtype"],
        ),
        "layer_count": (
            required["layer_count"],
            config["model"]["decoder_layer_count"],
        ),
        "activation_row_count": (
            required["activation_row_count"],
            config["expected_activation_row_count"],
        ),
        "activation_chunk_count": (
            required["activation_chunk_count"],
            config["expected_activation_chunk_count"],
        ),
        "model_frame_key_count": (
            policy["model_frame_key_count"],
            config["expected_model_frame_key_count"],
        ),
        "trajectory_count": (
            policy["trajectory_count"],
            config["expected_trajectory_count"],
        ),
        "row_key": (
            handoff["required_activation_index_fields"]["row_key"],
            config["extraction"]["activation_index_key"],
        ),
        "run_id": (RUN_ID, config["successor_run_identity"]["run_id"]),
    }
    disagreements = [
        field for field, (expected, observed) in checks.items() if expected != observed
    ]
    require(
        not disagreements,
        "Person A's run config disagrees with Person B's frozen contract on: "
        + ", ".join(disagreements),
    )

    # Extraction must still not have started at the bound evidence commit.
    transfer = json.loads(
        read_foreign_blob(
            PERSON_A_COMMIT,
            "docs/status/person_a_phase6_input_transfer_verification_v0_1/"
            "transfer_verification_receipt.json",
        )
    )
    require(
        transfer["run_id"] == RUN_ID,
        "The bound transfer receipt names a different run identity.",
    )
    require(
        transfer["verification"]["pass"] is True
        and transfer["verification"]["missing_count"] == 0
        and transfer["verification"]["hash_mismatch_count"] == 0
        and transfer["verification"]["size_mismatch_count"] == 0
        and transfer["verification"]["duplicate_output_paths_in_manifest"] == 0,
        "The bound transfer verification is not clean.",
    )
    require(
        transfer["verification"]["valid_count"] == policy["model_frame_key_count"],
        "Transferred payload count does not cover the production key universe.",
    )
    require(
        transfer["gpu_extraction_started"] is False,
        "This authorization is a pre-execution decision; extraction had started.",
    )


def validate_authority_binding(binding: dict[str, Any]) -> None:
    require(
        binding["foreign_branch_merged"] is False,
        "Authority binding must record that no peer branch was merged.",
    )
    require(
        binding["person_a_commit"] == PERSON_A_COMMIT,
        f"Authority binding must bind Person A commit {PERSON_A_COMMIT}.",
    )
    for record in binding["person_a_evidence"]:
        payload = read_foreign_blob(PERSON_A_COMMIT, record["path"])
        require(
            sha256_bytes(payload) == record["sha256"],
            f"Bound Person A evidence {record['path']} no longer hashes as recorded.",
        )
    for record in binding["person_b_frozen_authorities"]:
        payload = read_local(record["path"])
        require(
            sha256_bytes(payload) == record["sha256"],
            f"Bound Person B authority {record['path']} changed after signing.",
        )


def validate() -> dict[str, Any]:
    validate_inventory()
    documents = validate_sealed_documents()
    decision = documents[DECISION_DOCUMENT]

    validate_run_identity(decision)
    validate_frozen_history_preserved(decision)
    validate_scope_is_narrow(decision)
    validate_preconditions_against_evidence(documents[PRECONDITION_VERIFICATION])
    validate_authority_binding(documents[AUTHORITY_BINDING])

    receipt = load_package_document(VALIDATION_RECEIPT)
    require(
        receipt["run_id"] == RUN_ID and receipt["authorized"] is True,
        "Validation receipt disagrees with the decision.",
    )
    require(
        not receipt["extraction_identity_fields_disagreeing"],
        "Validation receipt records identity disagreements.",
    )

    return {
        "authorized": True,
        "decision_path": f"{PACKAGE_DIRECTORY}/{DECISION_DOCUMENT}",
        "decision_sha256": sha256_bytes(read_local(
            f"{PACKAGE_DIRECTORY}/{DECISION_DOCUMENT}"
        )),
        "run_id": RUN_ID,
        "status": "PASS",
    }


if __name__ == "__main__":
    print(json.dumps(validate(), indent=2, sort_keys=True))
