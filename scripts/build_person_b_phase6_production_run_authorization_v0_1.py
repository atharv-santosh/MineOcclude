#!/usr/bin/env python
"""Build Person B's Phase-6 production-run authorization decision.

This artifact is additive. It resolves exactly one open question that Person B
left open in

    docs/status/person_b_phase4_step4_1_registry_v2_handoff_v0_1/
        phase6_authorization_conditions.json

namely ``person_a_phase6_authorized``, and it resolves it only for the single
named production run identity. Nothing frozen is rewritten: the Step 4.1
decision stays FAIL, U4 stays unauthorized and uninspected, and acceptance of
Person A's *output* bytes into Person B's analysis stays blocked.

Person A's evidence is bound by commit, path, and SHA-256 read straight out of
the Git object store. Person A's branch is never merged into this one.
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

from mineocclude.analysis.config import (  # noqa: E402
    ANALYSIS_CONFIG_VERSION,
    DEFAULT_CONFIG_PATH,
)
from mineocclude.analysis.manifests import (  # noqa: E402
    canonical_json_bytes,
    seal_artifact,
)

PACKAGE_DIRECTORY = (
    "docs/status/person_b_phase6_production_run_authorization_v0_1"
)
PACKAGE = ROOT / PACKAGE_DIRECTORY

RUN_ID = "mineocclude-run-ea6169430d693f8adcd16a23a62c4422"
SUPERSEDED_RUN_ID = "mineocclude-run-836009cb74647b413ebc6f40218bc5bf"
DECISION_DATE = "2026-08-08"
REQUIRED_BRANCH = "role/person-b-analysis"

FROZEN_CONFIG_HASH = (
    "b2e12e7049e0494c756be442a4f300cbc7dc0a6e262deecf682f1354e887f0ab"
)

# ---------------------------------------------------------------------------
# Person A evidence, bound by commit + path + SHA-256 (never merged).
# ---------------------------------------------------------------------------
PERSON_A_COMMIT = "ecdf3178154e594b06d1d4326993754068cae039"
PERSON_A_EVIDENCE = {
    "authorization_request": (
        "docs/status/person_a_phase6_aggregate_authorization_request_v0_1/"
        "authorization_request.json"
    ),
    "extraction_config": (
        "docs/status/person_a_66_cell_preprocessed_media_v0_2/"
        "successor_extraction_config.json"
    ),
    "transfer_verification_receipt": (
        "docs/status/person_a_phase6_input_transfer_verification_v0_1/"
        "transfer_verification_receipt.json"
    ),
    "production_frame_map_inventory": (
        "data/handoff_a/person_a_66_cell_production_input_v0_1/"
        "sha256_inventory.json"
    ),
    "production_frame_map_index": (
        "data/handoff_a/person_a_66_cell_production_input_v0_1/"
        "frame_map_index.json"
    ),
}

# ---------------------------------------------------------------------------
# Person B frozen authorities on this branch.
# ---------------------------------------------------------------------------
B_TO_A_HANDOFF = (
    "docs/status/person_b_66_cell_oracle_target_v0_1/"
    "b_to_a_successor_handoff.json"
)
PHASE6_CONDITIONS = (
    "docs/status/person_b_phase4_step4_1_registry_v2_handoff_v0_1/"
    "phase6_authorization_conditions.json"
)
ORACLE_TARGET_MANIFEST = (
    "docs/status/person_b_66_cell_oracle_target_v0_1/oracle_target_manifest.json"
)
FOLD_COMPATIBILITY_RECEIPT = (
    "docs/status/person_b_66_cell_oracle_target_v0_1/"
    "fold_compatibility_receipt.json"
)
ADMISSION_LEDGER = (
    "docs/status/person_b_66_cell_oracle_target_v0_1/"
    "admission_exclusion_ledger.json"
)
U4_STATUS = "docs/status/person_b_66_cell_oracle_target_v0_1/u4_status.json"
PERSON_A_IDENTITY_RESOLUTION = (
    "docs/status/person_b_66_cell_oracle_target_v0_1/"
    "person_a_identity_resolution.json"
)
ORACLE_PACKAGE_INVENTORY = (
    "docs/status/person_b_66_cell_oracle_target_v0_1/sha256_inventory.json"
)

CODE_COMPONENTS = (
    "scripts/build_person_b_phase6_production_run_authorization_v0_1.py",
    "scripts/validate_person_b_phase6_production_run_authorization_v0_1.py",
    "src/mineocclude/analysis/manifests.py",
)

DECISION_DOCUMENT = "authorization_decision.json"
AUTHORITY_BINDING = "authority_binding.json"
PRECONDITION_VERIFICATION = "precondition_verification.json"
VALIDATION_RECEIPT = "validation_receipt.json"
SHA256_INVENTORY = "sha256_inventory.json"


class AuthorizationBuildError(RuntimeError):
    """Raised when the authorization cannot be built from frozen evidence."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AuthorizationBuildError(message)


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def read_local(relative_path: str) -> bytes:
    return (ROOT / relative_path).read_bytes()


def read_foreign_blob(commit: str, relative_path: str) -> bytes:
    """Read a peer role's file straight from the Git object store.

    The peer branch is never merged, checked out, or written into this tree.
    """

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


def derive_code_sha() -> str:
    digest = hashlib.sha1()
    for label in CODE_COMPONENTS:
        payload = read_local(label).replace(b"\r\n", b"\n")
        digest.update(label.encode("utf-8"))
        digest.update(b"\0")
        digest.update(payload)
        digest.update(b"\0")
    return digest.hexdigest()


def current_branch() -> str:
    return (
        subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            check=True,
        )
        .stdout.decode("utf-8")
        .strip()
    )


def write_document(path: Path, document: object) -> str:
    payload = canonical_json_bytes(document) + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return sha256_bytes(payload)


# ---------------------------------------------------------------------------
# Precondition checks
# ---------------------------------------------------------------------------
def check_extraction_identity(
    handoff: dict[str, Any], config: dict[str, Any]
) -> tuple[list[dict[str, Any]], bool]:
    """Compare every value Person B froze against Person A's run config."""

    required = handoff["required_activation_index_fields"]["required_values"]
    policy = handoff["extraction_row_policy"]
    dtype_decision = handoff["dtype_decision"]

    comparisons = [
        ("model_hash", required["model_hash"], config["model"]["model_hash"]),
        (
            "checkpoint_sha256",
            required["model_hash"],
            config["model"]["checkpoint_sha256"],
        ),
        (
            "preprocess_hash",
            required["preprocess_hash"],
            config["preprocessing"]["preprocess_hash"],
        ),
        (
            "accepted_manifest_hash",
            required["accepted_manifest_hash"],
            config["successor_run_identity"]["accepted_manifest_sha256"],
        ),
        ("hook_site", required["hook_site"], config["extraction"]["hook_site"]),
        (
            "vector_width",
            required["vector_width"],
            config["extraction"]["vector_width"],
        ),
        (
            "stored_dtype",
            required["stored_dtype"],
            config["extraction"]["stored_dtype"],
        ),
        (
            "analysis_arithmetic_dtype",
            dtype_decision["analysis_arithmetic_dtype"],
            config["analysis_arithmetic_dtype"],
        ),
        (
            "layer_count",
            required["layer_count"],
            config["model"]["decoder_layer_count"],
        ),
        (
            "layer_index_count",
            required["layer_count"],
            len(config["extraction"]["layer_indices"]),
        ),
        (
            "activation_row_count",
            required["activation_row_count"],
            config["expected_activation_row_count"],
        ),
        (
            "activation_chunk_count",
            required["activation_chunk_count"],
            config["expected_activation_chunk_count"],
        ),
        (
            "model_frame_key_count",
            policy["model_frame_key_count"],
            config["expected_model_frame_key_count"],
        ),
        (
            "trajectory_count",
            policy["trajectory_count"],
            config["expected_trajectory_count"],
        ),
        (
            "extract_full_model_frame_universe",
            policy["extract_full_model_frame_universe"],
            config["extraction"]["extract_full_model_frame_universe"],
        ),
        (
            "person_a_must_restrict_to_person_b_admitted_rows",
            policy["person_a_must_restrict_to_person_b_admitted_rows"],
            config["extraction"]["restricted_to_person_b_admitted_rows"],
        ),
        (
            "row_key",
            handoff["required_activation_index_fields"]["row_key"],
            config["extraction"]["activation_index_key"],
        ),
        (
            "run_id",
            RUN_ID,
            config["successor_run_identity"]["run_id"],
        ),
        (
            "new_run_identity_distinct_from_superseded",
            True,
            config["successor_run_identity"]["run_id"] != SUPERSEDED_RUN_ID,
        ),
    ]

    records = [
        {
            "field": field,
            "person_b_required": expected,
            "person_a_declared": observed,
            "agrees": expected == observed,
        }
        for field, expected, observed in comparisons
    ]
    return records, all(record["agrees"] for record in records)


def build() -> dict[str, Any]:
    branch = current_branch()
    require(
        branch == REQUIRED_BRANCH,
        f"This authorization must be published on {REQUIRED_BRANCH}, not {branch!r}.",
    )

    config_hash = sha256_bytes(DEFAULT_CONFIG_PATH.read_bytes())
    require(
        config_hash == FROZEN_CONFIG_HASH,
        "Core analysis config bytes changed; the frozen config_hash no longer holds.",
    )
    code_sha = derive_code_sha()

    # --- Person B frozen authorities -------------------------------------
    handoff_bytes = read_local(B_TO_A_HANDOFF)
    handoff = json.loads(handoff_bytes)
    conditions_bytes = read_local(PHASE6_CONDITIONS)
    conditions = json.loads(conditions_bytes)
    oracle_bytes = read_local(ORACLE_TARGET_MANIFEST)
    oracle = json.loads(oracle_bytes)
    fold_bytes = read_local(FOLD_COMPATIBILITY_RECEIPT)
    fold = json.loads(fold_bytes)
    ledger_bytes = read_local(ADMISSION_LEDGER)
    ledger = json.loads(ledger_bytes)
    u4_bytes = read_local(U4_STATUS)
    u4 = json.loads(u4_bytes)
    identity_bytes = read_local(PERSON_A_IDENTITY_RESOLUTION)
    identity = json.loads(identity_bytes)
    inventory_bytes = read_local(ORACLE_PACKAGE_INVENTORY)
    oracle_inventory = json.loads(inventory_bytes)

    # --- Person A evidence, read from the object store --------------------
    foreign: dict[str, dict[str, Any]] = {}
    for label, relative_path in PERSON_A_EVIDENCE.items():
        payload = read_foreign_blob(PERSON_A_COMMIT, relative_path)
        foreign[label] = {
            "path": relative_path,
            "sha256": sha256_bytes(payload),
            "document": json.loads(payload),
        }

    extraction_config = foreign["extraction_config"]["document"]
    transfer = foreign["transfer_verification_receipt"]["document"]
    frame_index = foreign["production_frame_map_index"]["document"]
    request = foreign["authorization_request"]["document"]

    # --- Prerequisite 1: the exact production model-input handoff ---------
    frame_package_sha = foreign["production_frame_map_inventory"]["sha256"]
    model_input_bound = (
        frame_package_sha
        == handoff["extraction_row_policy"]["source_frame_map_package_sha256"]
    )

    # --- Prerequisite 2: hash-bound run/model/preprocess identities -------
    identity_records, identity_agrees = check_extraction_identity(
        handoff, extraction_config
    )

    # --- Prerequisite 3: A key set covers the accepted C key set ----------
    key_set_covers = (
        frame_index["c_accepted_manifest_sha256"]
        == handoff["required_activation_index_fields"]["required_values"][
            "accepted_manifest_hash"
        ]
        and frame_index["model_frame_key_count"]
        == handoff["extraction_row_policy"]["model_frame_key_count"]
        and frame_index["trajectory_count"]
        == handoff["extraction_row_policy"]["trajectory_count"]
        and frame_index["duplicate_model_frame_key_count"] == 0
        and frame_index["missing_trajectory_count"] == 0
        and frame_index["model_frame_key_count_matches_expected"] is True
    )

    transfer_verification = transfer["verification"]
    transfer_clean = (
        transfer["run_id"] == RUN_ID
        and transfer_verification["pass"] is True
        and transfer_verification["expected_payload_count"]
        == handoff["extraction_row_policy"]["model_frame_key_count"]
        and transfer_verification["valid_count"]
        == handoff["extraction_row_policy"]["model_frame_key_count"]
        and transfer_verification["missing_count"] == 0
        and transfer_verification["hash_mismatch_count"] == 0
        and transfer_verification["size_mismatch_count"] == 0
        and transfer_verification["duplicate_output_paths_in_manifest"] == 0
        and transfer["gpu_extraction_started"] is False
        and transfer["scientific_execution_performed"] is False
        and transfer["historical_evidence_rewritten"] is False
    )

    # --- Prerequisite 4: folds preserve the sealed pre-A layout plan ------
    fold_checks = fold["checks"]
    folds_preserved = (
        fold["fold_compatibility_pass"] is True
        and fold["leakage_audit_pass"] is True
        and fold["fold_identity_preserved"] is True
        and fold["folds_regenerated"] is False
        and fold["grouping_changed_after_inspecting_final_labels"] is False
        and fold["fold_manifest_sha256"] == handoff["person_b_fold_manifest"]["sha256"]
        and fold["layout_assignments"] == oracle["fold_binding"]["layout_assignments"]
        and not fold["fold_disagreements"]
        and not fold["unresolved_frame_keys"]
        and all(bool(value) for value in fold_checks.values())
    )

    # --- Prerequisite 5: no structural/cardinality/leakage failure --------
    inventory_mismatches = [
        entry["path"]
        for entry in oracle_inventory["files"]
        if sha256_bytes(read_local(entry["path"])) != entry["sha256"]
        or len(read_local(entry["path"])) != entry["byte_size"]
    ]
    row_total = (
        ledger["admitted_analysis_row_count"] + ledger["excluded_analysis_row_count"]
    )
    no_residual_failure = (
        not inventory_mismatches
        and row_total == handoff["extraction_row_policy"]["model_frame_key_count"]
        and ledger["quarantine_policy"]["person_c_quarantined_admitted_count"] == 0
        and ledger["trajectory_acceptance_unchanged"][
            "person_c_accepted_trajectory_count"
        ]
        == handoff["extraction_row_policy"]["trajectory_count"]
        and ledger["trajectory_acceptance_unchanged"][
            "person_c_rejected_trajectory_count"
        ]
        == 0
        and oracle["foreign_branch_merged"] is False
        and oracle["person_a_authorities_modified"] is False
        and oracle["person_c_visibility_labels_modified"] is False
        and oracle["person_e_detector_outputs_modified"] is False
        and identity["person_a_model_preprocess_authority_valid"] is True
        and not identity["unresolved_person_a_authority"]
        and identity["value_accepted_from_conversation"] is False
    )

    # --- Prerequisite 7: no outcome-dependent selection --------------------
    outcome_blind = (
        u4["u4_executed"] is False
        and u4["u4_outcomes_inspected"] is False
        and u4["heldout_event_ids_frozen"] is False
        and u4["reveal_window_requirement_changed"] is False
        and oracle["u4_executed"] is False
        and oracle["u1_u3_executed"] is False
        and oracle["activation_analysis_executed"] is False
        and oracle["oracle_implementation"]["formulas_changed_after_seeing_output"]
        is False
        and oracle["oracle_implementation"]["detector_position_used_as_hidden_truth"]
        is False
    )

    preconditions = [
        {
            "condition_id": "exact_person_a_production_model_input_handoff_accepted",
            "evidence": (
                "Person A's production frame-map package inventory at "
                f"{PERSON_A_COMMIT} hashes to {frame_package_sha}, which is the "
                "exact value Person B froze in source_frame_map_package_sha256."
            ),
            "satisfied": bool(model_input_bound and transfer_clean),
            "source_frame_map_package_sha256": frame_package_sha,
        },
        {
            "condition_id": "person_a_identities_are_hash_bound",
            "evidence": (
                "Every value in Person B's required_activation_index_fields is "
                "reproduced by Person A's successor_extraction_config for this "
                "run identity."
            ),
            "field_comparison_count": len(identity_records),
            "satisfied": bool(identity_agrees),
        },
        {
            "condition_id": "production_a_key_set_covers_accepted_c_key_set",
            "evidence": (
                "Person A's frame_map_index binds C accepted manifest "
                f"{frame_index['c_accepted_manifest_sha256']} with "
                f"{frame_index['model_frame_key_count']} model-frame keys over "
                f"{frame_index['trajectory_count']} trajectories, no duplicates "
                "and no missing trajectories; transport verification reports "
                f"{transfer_verification['valid_count']} valid payloads."
            ),
            "satisfied": bool(key_set_covers and transfer_clean),
        },
        {
            "condition_id": "final_frame_fold_manifest_preserves_sealed_layout_plan",
            "evidence": (
                "fold_compatibility_receipt passes every check with no "
                "disagreements, no unresolved frame keys, no regeneration, and "
                "the sealed fold manifest hash unchanged."
            ),
            "satisfied": bool(folds_preserved),
        },
        {
            "condition_id": "no_structural_ownership_quarantine_provenance_"
            "cardinality_or_leakage_failure",
            "evidence": (
                f"All {oracle_inventory['file_count']} sealed oracle-package "
                "files rehash to their recorded digests; admitted "
                f"{ledger['admitted_analysis_row_count']} + excluded "
                f"{ledger['excluded_analysis_row_count']} = {row_total} equals "
                "the production key universe; no quarantined row is admitted; "
                "no peer-owned authority was modified."
            ),
            "satisfied": bool(no_residual_failure),
        },
        {
            "condition_id": "new_explicit_versioned_authorization_decision_signed",
            "evidence": (
                "This document is that decision. It is versioned, names the "
                "exact run identity, and is signed by person_b_analysis only "
                "for the scope stated in authorization_scope."
            ),
            "satisfied": True,
        },
        {
            "condition_id": "u4_and_downstream_outcomes_not_used_to_select_"
            "inputs_folds_layers_or_authorization",
            "evidence": (
                "U4 is unexecuted and uninspected, U1-U3 are unexecuted, no "
                "activation analysis has run, and no oracle formula or grouping "
                "changed after seeing any output."
            ),
            "satisfied": bool(outcome_blind),
        },
    ]

    all_satisfied = all(entry["satisfied"] for entry in preconditions)
    require(
        all_satisfied,
        "Refusing to authorize: "
        + ", ".join(
            entry["condition_id"] for entry in preconditions if not entry["satisfied"]
        ),
    )

    input_manifest_hash = sha256_bytes(
        canonical_json_bytes(
            {
                "person_a_commit": PERSON_A_COMMIT,
                "person_a_evidence": {
                    label: record["sha256"] for label, record in sorted(foreign.items())
                },
                "person_b_authorities": {
                    "admission_exclusion_ledger": sha256_bytes(ledger_bytes),
                    "b_to_a_successor_handoff": sha256_bytes(handoff_bytes),
                    "fold_compatibility_receipt": sha256_bytes(fold_bytes),
                    "oracle_package_sha256_inventory": sha256_bytes(inventory_bytes),
                    "oracle_target_manifest": sha256_bytes(oracle_bytes),
                    "person_a_identity_resolution": sha256_bytes(identity_bytes),
                    "phase6_authorization_conditions": sha256_bytes(conditions_bytes),
                    "u4_status": sha256_bytes(u4_bytes),
                },
                "run_id": RUN_ID,
            }
        )
    )

    base = {
        "analysis_config_version": ANALYSIS_CONFIG_VERSION,
        "artifact_schema_version": "person-b-analysis-artifact-v0.1",
        "code_sha": code_sha,
        "config_hash": config_hash,
        "decision_date": DECISION_DATE,
        "input_manifest_hash": input_manifest_hash,
        "producer_role": "person_b",
    }

    decision = seal_artifact(
        {
            **base,
            "artifact_id": "person-b-phase6-production-run-authorization-v0.1",
            "artifact_type": "person_b_phase6_production_run_authorization",
            "aggregate_phase6_runtime_authorized": False,
            "aggregate_authorization_is_not_person_b_to_declare": True,
            "authorization_scope": {
                "authorized_activity": (
                    "Person A executes the frozen 66-cell teacher-forced "
                    "activation extraction for the named run identity and "
                    "publishes the resulting bytes and index on Person A's own "
                    "branch."
                ),
                "authorized_run_id": RUN_ID,
                "authorized_steps": ["6.1", "6.2", "6.3", "6.4", "6.5", "6.6"],
                "extraction_universe": {
                    "extract_full_model_frame_universe": True,
                    "layer_count": handoff["required_activation_index_fields"][
                        "required_values"
                    ]["layer_count"],
                    "model_frame_key_count": handoff["extraction_row_policy"][
                        "model_frame_key_count"
                    ],
                    "expected_activation_row_count": handoff[
                        "required_activation_index_fields"
                    ]["required_values"]["activation_row_count"],
                    "trajectory_count": handoff["extraction_row_policy"][
                        "trajectory_count"
                    ],
                },
                "not_authorized": [
                    "acceptance of Person A's produced activation bytes into "
                    "Person B's scientific analysis",
                    "U1-U3 or U4 execution, reveal, or interpretation",
                    "reopening or overturning the frozen Step 4.1 FAIL decision",
                    "any claim of project integration readiness",
                    "any additional or substituted run identity",
                    "hidden-state interpretation claims of any kind",
                ],
            },
            "authorized": True,
            "decision": "AUTHORIZE_PERSON_A_PHASE6_EXTRACTION_FOR_NAMED_RUN_ID",
            "decision_owner": "person_b_analysis",
            "decision_status": "AUTHORIZED",
            "frozen_step_4_1_decision": "FAIL",
            "frozen_step_4_1_decision_unchanged": True,
            "historical_evidence_rewritten": False,
            "person_a_commit": PERSON_A_COMMIT,
            "person_a_phase6_authorized": True,
            "person_b_phase6_authorization": True,
            "person_b_phase6_signoff": True,
            "phase6_authorized": True,
            "foreign_branch_merged": False,
            "run_id": RUN_ID,
            "schema_id": (
                "person-b-phase6-production-run-authorization-v0.1-"
                "authorization-decision"
            ),
            "schema_version": "1.0",
            "scientific_execution_performed_by_person_b": False,
            "self_authorization_by_person_a_forbidden": True,
            "signer": "person_b_analysis",
            "signed_for_this_run_id": True,
            "superseded_run_id_not_authorized": SUPERSEDED_RUN_ID,
            "supersedes_field": {
                "field": "person_a_phase6_authorized",
                "path": PHASE6_CONDITIONS,
                "previous_value": conditions["person_a_phase6_authorized"],
                "scope_of_supersession": (
                    "This decision resolves that single field for run_id "
                    f"{RUN_ID} only. Every other condition in the superseded "
                    "document, including silent_authorization_forbidden, "
                    "remains in force and the file itself is unmodified."
                ),
                "sha256": sha256_bytes(conditions_bytes),
            },
            "u4_authorized": False,
            "u4_output_inspected": False,
        }
    )

    authority_binding = seal_artifact(
        {
            **base,
            "artifact_id": "person-b-phase6-production-run-authority-binding-v0.1",
            "artifact_type": "person_b_phase6_production_run_authority_binding",
            "foreign_branch_merged": False,
            "foreign_evidence_read_method": (
                "git show <commit>:<path> against the local object store; no "
                "peer branch is merged, checked out, or copied into this tree"
            ),
            "person_a_authorization_request": {
                "aggregate_phase6_runtime_authorized_at_request": request[
                    "aggregate_phase6_runtime_authorized"
                ],
                "path": PERSON_A_EVIDENCE["authorization_request"],
                "required_signers": request["required_signers"],
                "sha256": foreign["authorization_request"]["sha256"],
                "stale_person_b_head_checked_by_person_a": request["signer_status"][
                    "person_b_analysis"
                ]["branch_head_checked"],
            },
            "person_a_commit": PERSON_A_COMMIT,
            "person_a_evidence": [
                {
                    "label": label,
                    "path": record["path"],
                    "sha256": record["sha256"],
                }
                for label, record in sorted(foreign.items())
            ],
            "person_b_frozen_authorities": [
                {"label": label, "path": path, "sha256": sha256_bytes(payload)}
                for label, path, payload in sorted(
                    [
                        ("b_to_a_successor_handoff", B_TO_A_HANDOFF, handoff_bytes),
                        (
                            "phase6_authorization_conditions",
                            PHASE6_CONDITIONS,
                            conditions_bytes,
                        ),
                        ("oracle_target_manifest", ORACLE_TARGET_MANIFEST, oracle_bytes),
                        (
                            "fold_compatibility_receipt",
                            FOLD_COMPATIBILITY_RECEIPT,
                            fold_bytes,
                        ),
                        ("admission_exclusion_ledger", ADMISSION_LEDGER, ledger_bytes),
                        ("u4_status", U4_STATUS, u4_bytes),
                        (
                            "person_a_identity_resolution",
                            PERSON_A_IDENTITY_RESOLUTION,
                            identity_bytes,
                        ),
                        (
                            "oracle_package_sha256_inventory",
                            ORACLE_PACKAGE_INVENTORY,
                            inventory_bytes,
                        ),
                    ]
                )
            ],
            "run_id": RUN_ID,
            "schema_id": (
                "person-b-phase6-production-run-authorization-v0.1-authority-binding"
            ),
            "schema_version": "1.0",
        }
    )

    precondition_document = seal_artifact(
        {
            **base,
            "all_conditions_satisfied": all_satisfied,
            "artifact_id": (
                "person-b-phase6-production-run-precondition-verification-v0.1"
            ),
            "artifact_type": (
                "person_b_phase6_production_run_precondition_verification"
            ),
            "conditions": preconditions,
            "extraction_identity_comparison": identity_records,
            "governing_document": {
                "additional_prerequisites_for_a_new_versioned_decision": conditions[
                    "additional_prerequisites_for_a_new_versioned_decision"
                ],
                "automatic_transition_defined_by_existing_documents": conditions[
                    "automatic_transition_defined_by_existing_documents"
                ],
                "path": PHASE6_CONDITIONS,
                "sha256": sha256_bytes(conditions_bytes),
                "silent_authorization_forbidden": conditions[
                    "silent_authorization_forbidden"
                ],
            },
            "oracle_package_inventory_mismatches": inventory_mismatches,
            "person_a_runtime_state": {
                "extraction_started": transfer["gpu_extraction_started"],
                "payloads_expected": transfer_verification["expected_payload_count"],
                "payloads_valid": transfer_verification["valid_count"],
                "duplicate_output_paths": transfer_verification[
                    "duplicate_output_paths_in_manifest"
                ],
                "hash_mismatches": transfer_verification["hash_mismatch_count"],
                "missing": transfer_verification["missing_count"],
                "size_mismatches": transfer_verification["size_mismatch_count"],
                "transfer_pass": transfer_verification["pass"],
            },
            "run_id": RUN_ID,
            "schema_id": (
                "person-b-phase6-production-run-authorization-v0.1-"
                "precondition-verification"
            ),
            "schema_version": "1.0",
        }
    )

    written = {
        DECISION_DOCUMENT: write_document(PACKAGE / DECISION_DOCUMENT, decision),
        AUTHORITY_BINDING: write_document(
            PACKAGE / AUTHORITY_BINDING, authority_binding
        ),
        PRECONDITION_VERIFICATION: write_document(
            PACKAGE / PRECONDITION_VERIFICATION, precondition_document
        ),
    }

    receipt = {
        "all_preconditions_satisfied": all_satisfied,
        "authorized": True,
        "branch": branch,
        "decision_date": DECISION_DATE,
        "decision_document_sha256": written[DECISION_DOCUMENT],
        "extraction_identity_fields_compared": len(identity_records),
        "extraction_identity_fields_disagreeing": [
            record["field"] for record in identity_records if not record["agrees"]
        ],
        "foreign_branch_merged": False,
        "frozen_step_4_1_decision": "FAIL",
        "historical_evidence_rewritten": False,
        "oracle_package_files_rehashed": oracle_inventory["file_count"],
        "oracle_package_inventory_mismatches": inventory_mismatches,
        "person_a_commit": PERSON_A_COMMIT,
        "run_id": RUN_ID,
        "schema_id": (
            "person-b-phase6-production-run-authorization-v0.1-validation-receipt"
        ),
        "schema_version": "1.0",
        "scientific_execution_performed_by_person_b": False,
        "u4_output_inspected": False,
    }
    written[VALIDATION_RECEIPT] = write_document(
        PACKAGE / VALIDATION_RECEIPT, receipt
    )

    inventory = {
        "decision_date": DECISION_DATE,
        "file_count": len(written),
        "files": [
            {
                "byte_size": (PACKAGE / name).stat().st_size,
                "path": f"{PACKAGE_DIRECTORY}/{name}",
                "sha256": digest,
            }
            for name, digest in sorted(written.items())
        ],
        "inventory_excludes_self": True,
        "schema_id": (
            "person-b-phase6-production-run-authorization-v0.1-sha256-inventory"
        ),
        "schema_version": "1.0",
    }
    write_document(PACKAGE / SHA256_INVENTORY, inventory)

    return {
        "authorized": True,
        "decision_path": f"{PACKAGE_DIRECTORY}/{DECISION_DOCUMENT}",
        "decision_sha256": written[DECISION_DOCUMENT],
        "run_id": RUN_ID,
    }


if __name__ == "__main__":
    print(json.dumps(build(), indent=2, sort_keys=True))
