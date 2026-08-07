#!/usr/bin/env python3
"""Build the Person B 66-cell production oracle-target package.

Runs Person B's frozen adapter and frozen Regime A oracle unchanged over the
66-cell capture packages, applies the frozen admission policy to Person C's
final strict visible_flag, checks the existing frozen fold identity still fits,
and publishes an immutable production package plus successor handoffs to
Person A and Person D.

No activation bytes are read, no U1-U3 metric is executed, no U4 event is
frozen, and no Person C, Person E, or Person A artifact is modified.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from mineocclude.analysis.config import (  # noqa: E402
    ANALYSIS_CONFIG_VERSION,
    hash_core_analysis_config,
    load_core_analysis_config,
)
from mineocclude.analysis.manifests import (  # noqa: E402
    canonical_json_bytes,
    seal_artifact,
)
from mineocclude.analysis.oracle_target_66_cell_v0_1 import (  # noqa: E402
    ACCEPTED_GEOMETRY_SHA256,
    ALWAYS_REQUIRED_TARGET_FIELDS,
    ANALYSIS_ARITHMETIC_DTYPE,
    C_ACCEPTED_MANIFEST_PATH,
    C_ACCEPTED_MANIFEST_SHA256,
    C_CAPTURE_PACKAGE_MANIFEST_PATH,
    C_CAPTURE_PACKAGE_MANIFEST_SHA256,
    C_COORDINATE_AUTHORITY_PATH,
    C_COORDINATE_AUTHORITY_SHA256,
    C_EVENT_TABLE_PATH,
    C_EVENT_TABLE_SHA256,
    C_ORACLE_HANDOFF_PATH,
    C_ORACLE_HANDOFF_SHA256,
    C_VISIBILITY_JOIN_PATH,
    C_VISIBILITY_JOIN_SHA256,
    DECISION_DATE,
    EXPECTED_LAYER_COUNT,
    EXPECTED_MODEL_FRAME_KEY_COUNT,
    EXPECTED_TRAJECTORY_COUNT,
    HIDDEN_ONLY_TARGET_FIELDS,
    ORACLE_PACKAGE_DIRECTORY,
    ORACLE_PACKAGE_SCHEMA_VERSION,
    ORACLE_RUN_ID,
    ORACLE_TARGET_FIELDS,
    PERSON_A_COMMIT,
    PERSON_A_FRAME_MAP_PACKAGE_PATH,
    PERSON_A_FRAME_MAP_PACKAGE_SHA256,
    PERSON_A_OWNER_ACKNOWLEDGEMENT_PATH,
    PERSON_A_OWNER_ACKNOWLEDGEMENT_SHA256,
    PERSON_A_PRODUCTION_AUTHORITIES_PATH,
    PERSON_A_PRODUCTION_AUTHORITIES_SHA256,
    PERSON_B_COSIGN_PATH,
    PERSON_B_COSIGN_SHA256,
    PERSON_B_FOLD_MANIFEST_PATH,
    PERSON_B_FOLD_MANIFEST_SHA256,
    PERSON_C_COMMIT,
    PERSON_E_COMMIT,
    PERSON_E_RECORDS_PATH,
    PERSON_E_RECORDS_SHA256,
    ROW_EXCLUSION_AMBIGUOUS_GEOMETRY,
    ROW_EXCLUSION_CHANNEL_DISAGREEMENT,
    ROW_EXCLUSION_NO_OBJECT,
    ROW_EXCLUSION_OUTSIDE_SELECTION,
    ROW_EXCLUSION_PRE_FIRST_SEEN,
    ROW_EXCLUSION_QUARANTINED,
    STORED_ACTIVATION_DTYPE,
    OracleTargetError,
    build_production_oracle_targets,
    build_successor_row_universe,
    derive_oracle_code_sha,
    load_person_c_oracle_inputs,
    require,
    resolve_person_a_identity,
    summarize_row_universe,
    validate_fold_compatibility,
)

PACKAGE = ROOT / ORACLE_PACKAGE_DIRECTORY

ORACLE_TARGET_MANIFEST = "oracle_target_manifest.json"
ORACLE_TARGET_RECORDS = "oracle_target_records.jsonl"
ROW_UNIVERSE_RECEIPT = "row_universe_receipt_v0_2.json"
ROW_UNIVERSE_RECORDS = "row_universe_records.jsonl"
ADMISSION_LEDGER = "admission_exclusion_ledger.json"
FOLD_COMPATIBILITY_RECEIPT = "fold_compatibility_receipt.json"
PERSON_A_IDENTITY_RESOLUTION = "person_a_identity_resolution.json"
B_TO_A_HANDOFF = "b_to_a_successor_handoff.json"
B_TO_D_HANDOFF = "b_to_d_successor_handoff.json"
U4_STATUS = "u4_status.json"
SHA256_INVENTORY = "sha256_inventory.json"

ORDERED_JSON_FILES = (
    PERSON_A_IDENTITY_RESOLUTION,
    ROW_UNIVERSE_RECEIPT,
    ADMISSION_LEDGER,
    FOLD_COMPATIBILITY_RECEIPT,
    ORACLE_TARGET_MANIFEST,
    U4_STATUS,
    B_TO_A_HANDOFF,
    B_TO_D_HANDOFF,
)
ORDERED_JSONL_FILES = (ORACLE_TARGET_RECORDS, ROW_UNIVERSE_RECORDS)


def _write_json(path: Path, document: object) -> str:
    payload = canonical_json_bytes(document) + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return hashlib.sha256(payload).hexdigest()


def _write_jsonl(path: Path, rows: list[dict]) -> str:
    payload = b"".join(canonical_json_bytes(row) + b"\n" for row in rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return hashlib.sha256(payload).hexdigest()


def _current_branch() -> str:
    return subprocess.run(
        ["git", "-C", str(ROOT), "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True,
        check=True,
    ).stdout.decode("utf-8").strip()


def _bound_authorities(person_a: dict) -> dict:
    return {
        "person_c_commit": PERSON_C_COMMIT,
        "person_c_accepted_manifest_path": C_ACCEPTED_MANIFEST_PATH,
        "person_c_accepted_manifest_sha256": C_ACCEPTED_MANIFEST_SHA256,
        "person_c_oracle_handoff_path": C_ORACLE_HANDOFF_PATH,
        "person_c_oracle_handoff_sha256": C_ORACLE_HANDOFF_SHA256,
        "person_c_visibility_join_path": C_VISIBILITY_JOIN_PATH,
        "person_c_visibility_join_sha256": C_VISIBILITY_JOIN_SHA256,
        "person_c_event_table_path": C_EVENT_TABLE_PATH,
        "person_c_event_table_sha256": C_EVENT_TABLE_SHA256,
        "person_c_capture_package_manifest_path": C_CAPTURE_PACKAGE_MANIFEST_PATH,
        "person_c_capture_package_manifest_sha256": C_CAPTURE_PACKAGE_MANIFEST_SHA256,
        "person_c_coordinate_authority_path": C_COORDINATE_AUTHORITY_PATH,
        "person_c_coordinate_authority_sha256": C_COORDINATE_AUTHORITY_SHA256,
        "accepted_geometry_sha256": ACCEPTED_GEOMETRY_SHA256,
        "person_b_coordinate_cosign_path": PERSON_B_COSIGN_PATH,
        "person_b_coordinate_cosign_sha256": PERSON_B_COSIGN_SHA256,
        "person_e_commit": PERSON_E_COMMIT,
        "person_e_records_path": PERSON_E_RECORDS_PATH,
        "person_e_records_sha256": PERSON_E_RECORDS_SHA256,
        "person_a_commit": PERSON_A_COMMIT,
        "person_a_frame_map_package_path": PERSON_A_FRAME_MAP_PACKAGE_PATH,
        "person_a_frame_map_package_sha256": PERSON_A_FRAME_MAP_PACKAGE_SHA256,
        "person_a_owner_acknowledgement_path": PERSON_A_OWNER_ACKNOWLEDGEMENT_PATH,
        "person_a_owner_acknowledgement_sha256": PERSON_A_OWNER_ACKNOWLEDGEMENT_SHA256,
        "person_a_production_authorities_path": PERSON_A_PRODUCTION_AUTHORITIES_PATH,
        "person_a_production_authorities_sha256": (
            PERSON_A_PRODUCTION_AUTHORITIES_SHA256
        ),
        "person_a_model_hash": person_a["model_hash"],
        "person_a_preprocess_hash": person_a["preprocess_hash"],
        "person_b_fold_manifest_path": PERSON_B_FOLD_MANIFEST_PATH,
        "person_b_fold_manifest_sha256": PERSON_B_FOLD_MANIFEST_SHA256,
    }


EXCLUSION_RULES = (
    {
        "exclusion_reason": ROW_EXCLUSION_NO_OBJECT,
        "rule": "control_type == 'no_object_control'",
        "owner": "person_b_frozen_adapter",
        "is_trajectory_rejection": False,
    },
    {
        "exclusion_reason": ROW_EXCLUSION_AMBIGUOUS_GEOMETRY,
        "rule": "person_c geometric_ambiguous is true",
        "owner": "person_b_frozen_admission_policy",
        "is_trajectory_rejection": False,
    },
    {
        "exclusion_reason": ROW_EXCLUSION_CHANNEL_DISAGREEMENT,
        "rule": (
            "disagreement_class in "
            "{geometry_visible_detector_hidden, geometry_hidden_detector_visible}"
        ),
        "owner": "person_b_frozen_admission_policy",
        "is_trajectory_rejection": False,
    },
    {
        "exclusion_reason": ROW_EXCLUSION_QUARANTINED,
        "rule": "person_c quarantined is true and no earlier reason applied",
        "owner": "person_c",
        "is_trajectory_rejection": False,
    },
    {
        "exclusion_reason": ROW_EXCLUSION_PRE_FIRST_SEEN,
        "rule": "model_frame_idx < first geometric_visible index",
        "owner": "person_b_frozen_filters",
        "is_trajectory_rejection": False,
    },
    {
        "exclusion_reason": ROW_EXCLUSION_OUTSIDE_SELECTION,
        "rule": (
            "visible_flag is true and control_type != 'no_wall_visible_control'"
        ),
        "owner": "person_b_frozen_condition_selection",
        "is_trajectory_rejection": False,
    },
)


def build_person_a_identity_document(person_a: dict, code_sha: str) -> dict:
    return seal_artifact(
        {
            "artifact_type": "person_b_person_a_identity_resolution",
            "artifact_id": "person-b-66-cell-person-a-identity-v0.1",
            "code_sha": code_sha,
            "config_hash": hash_core_analysis_config(),
            "input_manifest_hash": PERSON_A_PRODUCTION_AUTHORITIES_SHA256,
            "oracle_package_schema_version": ORACLE_PACKAGE_SCHEMA_VERSION,
            "decision_date": DECISION_DATE,
            "producer_role": "person_b",
            "resolved_from_repository_authority_only": True,
            "value_accepted_from_conversation": False,
            "person_a_commit": PERSON_A_COMMIT,
            "model_hash": person_a["model_hash"],
            "model_hash_definition": person_a["model_hash_definition"],
            "model_hash_definition_evidence": person_a["model_hash_definition_evidence"],
            "checkpoint_sha256": person_a["checkpoint_sha256"],
            "model_identity": person_a["model_identity"],
            "preprocess_hash": person_a["preprocess_hash"],
            "preprocess_hash_source": person_a["preprocess_hash_source"],
            "preprocessing_identity": person_a["preprocessing_identity"],
            "preprocessing_config_hash": person_a["preprocessing_config_hash"],
            "preprocessing_implementation_path": person_a[
                "preprocessing_implementation_path"
            ],
            "preprocessing_implementation_sha256": person_a[
                "preprocessing_implementation_sha256"
            ],
            "preprocessing_implementation_digest_is_not_preprocess_hash": True,
            "action_converter_identity": person_a["action_converter_identity"],
            "action_converter_path": person_a["action_converter_path"],
            "action_converter_sha256": person_a["action_converter_sha256"],
            "frame_map_schema_path": person_a["frame_map_schema_path"],
            "frame_map_schema_sha256": person_a["frame_map_schema_sha256"],
            "frame_map_schema_version": person_a["frame_map_schema_version"],
            "activation_index_format_version": person_a[
                "activation_index_format_version"
            ],
            "activation_index_key": person_a["activation_index_key"],
            "person_a_model_preprocess_authority_valid": True,
            "unresolved_person_a_authority": [],
        }
    )


def build_row_universe_receipt(
    summary: dict, records_sha: str, code_sha: str
) -> dict:
    return seal_artifact(
        {
            "artifact_type": "person_b_66_cell_row_universe_receipt_v0_2",
            "artifact_id": "person-b-66-cell-row-universe-v0.2",
            "code_sha": code_sha,
            "config_hash": hash_core_analysis_config(),
            "input_manifest_hash": C_VISIBILITY_JOIN_SHA256,
            "oracle_package_schema_version": ORACLE_PACKAGE_SCHEMA_VERSION,
            "analysis_config_version": ANALYSIS_CONFIG_VERSION,
            "decision_date": DECISION_DATE,
            "producer_role": "person_b",
            "synthetic": False,
            "scientific_use": "permitted",
            "supersedes": {
                "path": (
                    "docs/status/person_b_66_cell_preactivation_v0_1/"
                    "row_universe_receipt.json"
                ),
                "reason": (
                    "the predecessor receipt predates Person C's final empirical "
                    "and geometric strict join; its 984/1484 accounting is "
                    "historical and is not overwritten"
                ),
                "predecessor_admitted_analysis_row_count": 984,
                "predecessor_excluded_analysis_row_count": 1_484,
                "predecessor_evidence_rewritten": False,
            },
            "row_records_path": f"{ORACLE_PACKAGE_DIRECTORY}/{ROW_UNIVERSE_RECORDS}",
            "row_records_sha256": records_sha,
            "join_key": ["trajectory_id", "model_frame_idx"],
            "visible_flag_rule": "geometric_visible AND empirical_magenta_visible",
            "visible_flag_owner": "person_c",
            "person_b_overwrote_visible_flag": False,
            "person_b_retuned_detector": False,
            "person_b_modified_geometric_visibility": False,
            **_bound_authorities_summary(summary),
        }
    )


def _bound_authorities_summary(summary: dict) -> dict:
    return dict(summary)


def build_admission_ledger(summary: dict, code_sha: str) -> dict:
    return seal_artifact(
        {
            "artifact_type": "person_b_66_cell_admission_exclusion_ledger",
            "artifact_id": "person-b-66-cell-admission-ledger-v0.1",
            "code_sha": code_sha,
            "config_hash": hash_core_analysis_config(),
            "input_manifest_hash": C_VISIBILITY_JOIN_SHA256,
            "oracle_package_schema_version": ORACLE_PACKAGE_SCHEMA_VERSION,
            "decision_date": DECISION_DATE,
            "producer_role": "person_b",
            "evaluation_order": [rule["exclusion_reason"] for rule in EXCLUSION_RULES],
            "exclusion_rules": [dict(rule) for rule in EXCLUSION_RULES],
            "admitted_analysis_row_count": summary["admitted_analysis_row_count"],
            "excluded_analysis_row_count": summary["excluded_analysis_row_count"],
            "excluded_counts_by_reason": summary["excluded_counts_by_reason"],
            "admitted_counts_by_scope": summary["admitted_counts_by_scope"],
            "ambiguity_policy": {
                "reason_code": ROW_EXCLUSION_AMBIGUOUS_GEOMETRY,
                "row_count": summary["ambiguous_geometry_row_count"],
                "admitted_count": summary["ambiguous_geometry_admitted_count"],
                "excluded_count": summary["ambiguous_geometry_excluded_count"],
                "person_b_chose_a_geometry_interpretation": False,
                "rationale": (
                    "Both Person B analysis scopes are defined on unambiguous "
                    "visibility: the visible control scope requires a true strict "
                    "visible_flag and the hidden scopes require a false one. A row "
                    "whose geometry channel is edge-ambiguous cannot be assigned "
                    "to either without choosing between the half-open runtime "
                    "block volume and the closed Python-box edge convention, so "
                    "every such row is excluded and both raw values are preserved."
                ),
            },
            "disagreement_policy": {
                "reason_code": ROW_EXCLUSION_CHANNEL_DISAGREEMENT,
                "person_b_retuned_detector": False,
                "person_b_modified_geometric_visibility": False,
                "person_b_replaced_visible_flag_rule": False,
                "person_c_classifications_preserved": True,
                "disagreement_counts": summary["disagreement_counts"],
                "no_wall_control_rows_excluded_by_channel_disagreement": summary[
                    "no_wall_control_rows_excluded_by_channel_disagreement"
                ],
                "no_wall_disagreement_cause_invented": False,
                "no_wall_disagreement_disposition": (
                    "retained as factual Person C disagreement records and "
                    "excluded from Person B analysis rows; Person E may review "
                    "them separately without blocking this manifest"
                ),
            },
            "quarantine_policy": {
                "person_c_quarantined_row_count": summary[
                    "person_c_quarantined_row_count"
                ],
                "person_c_quarantined_admitted_count": summary[
                    "person_c_quarantined_admitted_count"
                ],
                "overlap_by_exclusion_reason": summary[
                    "person_c_quarantine_overlap_by_exclusion_reason"
                ],
            },
            "trajectory_acceptance_unchanged": {
                "person_c_accepted_trajectory_count": EXPECTED_TRAJECTORY_COUNT,
                "person_c_rejected_trajectory_count": 0,
                "row_level_exclusion_is_not_trajectory_rejection": True,
            },
        }
    )


def build_fold_receipt(fold: dict, code_sha: str) -> dict:
    return seal_artifact(
        {
            "artifact_type": "person_b_66_cell_fold_compatibility_receipt",
            "artifact_id": "person-b-66-cell-fold-compatibility-v0.1",
            "code_sha": code_sha,
            "config_hash": hash_core_analysis_config(),
            "input_manifest_hash": PERSON_B_FOLD_MANIFEST_SHA256,
            "oracle_package_schema_version": ORACLE_PACKAGE_SCHEMA_VERSION,
            "decision_date": DECISION_DATE,
            "producer_role": "person_b",
            "folds_regenerated": False,
            "fold_identity_preserved": True,
            "grouping_changed_after_inspecting_final_labels": False,
            **{key: value for key, value in fold.items()},
        }
    )


def build_u4_status(c_inputs: dict, code_sha: str) -> dict:
    handoff = c_inputs["handoff"]
    event_table = handoff["event_table"]
    return seal_artifact(
        {
            "artifact_type": "person_b_66_cell_u4_status",
            "artifact_id": "person-b-66-cell-u4-status-v0.1",
            "code_sha": code_sha,
            "config_hash": hash_core_analysis_config(),
            "input_manifest_hash": C_EVENT_TABLE_SHA256,
            "oracle_package_schema_version": ORACLE_PACKAGE_SCHEMA_VERSION,
            "decision_date": DECISION_DATE,
            "producer_role": "person_b",
            "CURRENT_66_CELL_U4_REVEAL_ELIGIBLE": False,
            "U4_SUPPLEMENTAL_CAPTURE_REQUIRED": True,
            "VALID_TERMINAL_REVEAL_COUNT": event_table["valid_terminal_reveal_count"],
            "stable_occlusion_event_count": event_table[
                "stable_occlusion_event_count"
            ],
            "stable_reveal_event_count": event_table["stable_reveal_event_count"],
            "heldout_event_ids_frozen": False,
            "frozen_heldout_event_ids": None,
            "reveal_window_requirement_changed": False,
            "reveal_window_seconds": load_core_analysis_config()["metric_rules"][
                "reveal_window_seconds"
            ],
            "person_c_event_table_path": C_EVENT_TABLE_PATH,
            "person_c_event_table_sha256": C_EVENT_TABLE_SHA256,
            "u4_executed": False,
            "activation_direction_constructed": False,
            "u4_outcomes_inspected": False,
            "supplemental_capture_is_a_later_task_with_new_run_identity": True,
        }
    )


def build_oracle_manifest(
    person_a: dict,
    summary: dict,
    oracle: dict,
    fold: dict,
    records_sha: str,
    row_records_sha: str,
    code_sha: str,
) -> dict:
    config = load_core_analysis_config()
    return seal_artifact(
        {
            "artifact_type": "person_b_66_cell_oracle_target_manifest",
            "artifact_id": "person-b-66-cell-oracle-target-v0.1",
            "code_sha": code_sha,
            "config_hash": hash_core_analysis_config(),
            "input_manifest_hash": C_ORACLE_HANDOFF_SHA256,
            "oracle_package_schema_version": ORACLE_PACKAGE_SCHEMA_VERSION,
            "analysis_config_version": ANALYSIS_CONFIG_VERSION,
            "decision_date": DECISION_DATE,
            "producer_role": "person_b",
            "synthetic": False,
            "scientific_use": "permitted",
            "oracle_run_id": ORACLE_RUN_ID,
            "oracle_implementation": {
                "state_adapter": (
                    "mineocclude.analysis.coordinates."
                    "build_state_input_from_capture_package"
                ),
                "target_builder": (
                    "mineocclude.oracle.targets.build_regime_a_target_document"
                ),
                "method": "primary_scalar_kalman_crosschecked_closed_form",
                "regime": "regime_a",
                "code_sha": code_sha,
                "formulas_changed_after_seeing_output": False,
                "target_truth_reconstructed_from_pixels": False,
                "detector_position_used_as_hidden_truth": False,
            },
            "target_schema": {
                "join_key": ["trajectory_id", "model_frame_idx"],
                "fields": list(ORACLE_TARGET_FIELDS),
                "always_required_fields": list(ALWAYS_REQUIRED_TARGET_FIELDS),
                "eligibility_scoped_fields": list(HIDDEN_ONLY_TARGET_FIELDS),
                "units": {
                    "mu_oracle_blocks": "blocks",
                    "var_oracle_blocks2": "blocks_squared",
                    "sigma_oracle_blocks": "blocks",
                    "log_sigma_oracle": "dimensionless",
                    "x_true_blocks": "blocks",
                    "tau": "seconds",
                    "last_visible_position_blocks": "blocks",
                },
                "log_sigma_oracle_null_policy": config["targets"]["log_sigma_oracle"][
                    "null_policy"
                ],
                "log_sigma_oracle_eligibility": config["targets"]["log_sigma_oracle"][
                    "eligibility"
                ],
            },
            "target_records_path": f"{ORACLE_PACKAGE_DIRECTORY}/{ORACLE_TARGET_RECORDS}",
            "target_records_sha256": records_sha,
            "oracle_target_row_count": len(oracle["target_rows"]),
            "oracle_eligible_trajectory_count": len(oracle["per_trajectory"]),
            "oracle_ineligible_trajectories": oracle["oracle_ineligible_trajectories"],
            "per_trajectory_provenance": oracle["per_trajectory"],
            "row_universe": {
                "path": f"{ORACLE_PACKAGE_DIRECTORY}/{ROW_UNIVERSE_RECEIPT}",
                "records_path": f"{ORACLE_PACKAGE_DIRECTORY}/{ROW_UNIVERSE_RECORDS}",
                "records_sha256": row_records_sha,
                "canonical_hash": summary["row_universe_canonical_hash"],
                "admitted_analysis_row_count": summary["admitted_analysis_row_count"],
                "excluded_analysis_row_count": summary["excluded_analysis_row_count"],
            },
            "visibility_channel_layering": {
                "oracle_state_channel": "person_c geometric visibility at capture",
                "oracle_state_channel_source": (
                    "capture package streams.visibility[].visibility"
                ),
                "analysis_admission_channel": (
                    "person_c strict visible_flag = geometric_visible AND "
                    "empirical_magenta_visible"
                ),
                "rationale": (
                    "The frozen adapter anchors tau and the last visible "
                    "observation on the physical occlusion history Person C "
                    "recorded at capture. The strict flag then decides which of "
                    "those oracle rows are admissible scientific evidence. "
                    "Neither channel was modified and no frozen formula changed."
                ),
            },
            "fold_binding": {
                "path": PERSON_B_FOLD_MANIFEST_PATH,
                "sha256": PERSON_B_FOLD_MANIFEST_SHA256,
                "artifact_hash": fold["fold_manifest_artifact_hash"],
                "fold_compatibility_pass": fold["fold_compatibility_pass"],
                "leakage_audit_pass": fold["leakage_audit_pass"],
                "layout_assignments": fold["layout_assignments"],
            },
            "condition_fields": [
                "control_type",
                "set_id",
                "scene",
                "context_fraction",
                "hidden_frames",
                "speed_blocks_per_second",
                "q_blocks_squared_per_second",
                "seed",
            ],
            "dtype_contract": {
                "stored_activation_dtype": STORED_ACTIVATION_DTYPE,
                "analysis_arithmetic_dtype": ANALYSIS_ARITHMETIC_DTYPE,
            },
            "deterministic_regeneration": {
                "builder": (
                    "scripts/build_person_b_66_cell_oracle_target_v0_1.py"
                ),
                "validator": (
                    "scripts/validate_person_b_66_cell_oracle_target_v0_1.py"
                ),
                "byte_reproducible": True,
            },
            "activation_analysis_executed": False,
            "u1_u3_executed": False,
            "u4_executed": False,
            "person_c_visibility_labels_modified": False,
            "person_e_detector_outputs_modified": False,
            "person_a_authorities_modified": False,
            "foreign_branch_merged": False,
            "frozen_step_4_1_decision": "FAIL",
            "provenance": _bound_authorities(person_a),
        }
    )


def build_b_to_a_handoff(
    person_a: dict, summary: dict, manifest: dict, fold: dict, code_sha: str
) -> dict:
    return seal_artifact(
        {
            "artifact_type": "person_b_to_person_a_66_cell_successor_handoff",
            "artifact_id": "person-b-to-person-a-66-cell-v0.2",
            "code_sha": code_sha,
            "config_hash": hash_core_analysis_config(),
            "input_manifest_hash": manifest["artifact_hash"],
            "oracle_package_schema_version": ORACLE_PACKAGE_SCHEMA_VERSION,
            "decision_date": DECISION_DATE,
            "producer_role": "person_b",
            "consumer_role": "person_a",
            "consumer_receipt_present": False,
            "downstream_acceptance_claimed": False,
            "supersedes": (
                "docs/status/person_b_66_cell_preactivation_v0_1/b_to_a_handoff.json"
            ),
            "person_c_strict_visibility_authority": {
                "commit": PERSON_C_COMMIT,
                "oracle_handoff_path": C_ORACLE_HANDOFF_PATH,
                "oracle_handoff_sha256": C_ORACLE_HANDOFF_SHA256,
                "visibility_join_path": C_VISIBILITY_JOIN_PATH,
                "visibility_join_sha256": C_VISIBILITY_JOIN_SHA256,
                "event_table_path": C_EVENT_TABLE_PATH,
                "event_table_sha256": C_EVENT_TABLE_SHA256,
                "accepted_manifest_sha256": C_ACCEPTED_MANIFEST_SHA256,
            },
            "person_b_row_universe": {
                "path": f"{ORACLE_PACKAGE_DIRECTORY}/{ROW_UNIVERSE_RECEIPT}",
                "canonical_hash": summary["row_universe_canonical_hash"],
                "admitted_analysis_row_count": summary["admitted_analysis_row_count"],
                "excluded_analysis_row_count": summary["excluded_analysis_row_count"],
            },
            "person_b_fold_manifest": {
                "path": PERSON_B_FOLD_MANIFEST_PATH,
                "sha256": PERSON_B_FOLD_MANIFEST_SHA256,
            },
            "person_b_oracle_target_manifest": {
                "path": f"{ORACLE_PACKAGE_DIRECTORY}/{ORACLE_TARGET_MANIFEST}",
                "artifact_hash": manifest["artifact_hash"],
                "target_row_count": manifest["oracle_target_row_count"],
            },
            "model_preprocess_resolution": {
                "model_hash": person_a["model_hash"],
                "model_hash_definition": person_a["model_hash_definition"],
                "preprocess_hash": person_a["preprocess_hash"],
                "preprocess_hash_source_path": PERSON_A_PRODUCTION_AUTHORITIES_PATH,
                "preprocess_hash_source_sha256": PERSON_A_PRODUCTION_AUTHORITIES_SHA256,
                "preprocessing_implementation_sha256_is_a_different_quantity": True,
                "authority_valid": True,
            },
            "dtype_decision": {
                "stored_activation_dtype": STORED_ACTIVATION_DTYPE,
                "analysis_arithmetic_dtype": ANALYSIS_ARITHMETIC_DTYPE,
                "new_run_identity_required": True,
                "person_b_edited_person_a_mvp_yaml": False,
            },
            "extraction_row_policy": {
                "extract_full_model_frame_universe": True,
                "model_frame_key_count": EXPECTED_MODEL_FRAME_KEY_COUNT,
                "trajectory_count": EXPECTED_TRAJECTORY_COUNT,
                "layer_count": EXPECTED_LAYER_COUNT,
                "person_a_must_restrict_to_person_b_admitted_rows": False,
                "note": (
                    "Person B's admission is a scientific decision applied after "
                    "extraction. The frozen extraction contract is keyed to the "
                    "full production model-frame universe, so Person A extracts "
                    f"all {EXPECTED_MODEL_FRAME_KEY_COUNT} frames and Person B "
                    "subsets afterwards. Row-level exclusion is never a reason to "
                    "skip a frame."
                ),
                "source_frame_map_package_path": PERSON_A_FRAME_MAP_PACKAGE_PATH,
                "source_frame_map_package_sha256": PERSON_A_FRAME_MAP_PACKAGE_SHA256,
            },
            "required_activation_index_fields": {
                "row_key": person_a["activation_index_key"],
                "required_index_fields": [
                    "activation_store_format",
                    "run_id",
                    "extraction_artifact_id",
                    "checkpoint_hash",
                    "model_hash",
                    "preprocess_hash",
                    "config_hash",
                    "accepted_manifest_hash",
                    "hook_site",
                    "pooling_identity",
                    "stored_dtype",
                    "vector_width",
                    "layer_count",
                    "activation_row_count",
                    "activation_chunk_count",
                    "chunk_sha256",
                    "chunk_byte_size",
                    "chunk_row_count",
                    "stable_row_order_declared",
                ],
                "required_values": {
                    "model_hash": person_a["model_hash"],
                    "preprocess_hash": person_a["preprocess_hash"],
                    "accepted_manifest_hash": C_ACCEPTED_MANIFEST_SHA256,
                    "hook_site": "decoder_layer_output_residual_stream",
                    "stored_dtype": STORED_ACTIVATION_DTYPE,
                    "vector_width": 2048,
                    "layer_count": EXPECTED_LAYER_COUNT,
                    "activation_row_count": 49_360,
                    "activation_chunk_count": 1_320,
                },
                "activation_paths_or_hashes_supplied_by_person_b": False,
            },
            "fold_compatibility_pass": fold["fold_compatibility_pass"],
            "u4_status": {
                "CURRENT_66_CELL_U4_REVEAL_ELIGIBLE": False,
                "U4_SUPPLEMENTAL_CAPTURE_REQUIRED": True,
            },
        }
    )


def build_b_to_d_handoff(
    summary: dict, manifest: dict, fold: dict, records_sha: str, code_sha: str
) -> dict:
    config = load_core_analysis_config()
    return seal_artifact(
        {
            "artifact_type": "person_b_to_person_d_66_cell_successor_handoff",
            "artifact_id": "person-b-to-person-d-66-cell-v0.2",
            "code_sha": code_sha,
            "config_hash": hash_core_analysis_config(),
            "input_manifest_hash": manifest["artifact_hash"],
            "oracle_package_schema_version": ORACLE_PACKAGE_SCHEMA_VERSION,
            "decision_date": DECISION_DATE,
            "producer_role": "person_b",
            "consumer_role": "person_d",
            "consumer_receipt_present": False,
            "downstream_acceptance_claimed": False,
            "supersedes": (
                "docs/status/person_b_66_cell_preactivation_v0_1/b_to_d_handoff.json"
            ),
            "person_b_fold_manifest": {
                "path": PERSON_B_FOLD_MANIFEST_PATH,
                "sha256": PERSON_B_FOLD_MANIFEST_SHA256,
                "artifact_hash": fold["fold_manifest_artifact_hash"],
                "layout_assignments": fold["layout_assignments"],
            },
            "person_b_oracle_target_manifest": {
                "path": f"{ORACLE_PACKAGE_DIRECTORY}/{ORACLE_TARGET_MANIFEST}",
                "artifact_hash": manifest["artifact_hash"],
                "records_path": f"{ORACLE_PACKAGE_DIRECTORY}/{ORACLE_TARGET_RECORDS}",
                "records_sha256": records_sha,
                "target_row_count": manifest["oracle_target_row_count"],
            },
            "eligible_baseline_universe": {
                "join_key": ["trajectory_id", "model_frame_idx"],
                "admitted_analysis_row_count": summary["admitted_analysis_row_count"],
                "excluded_analysis_row_count": summary["excluded_analysis_row_count"],
                "admitted_counts_by_scope": summary["admitted_counts_by_scope"],
                "admitted_counts_by_stratum": summary["admitted_counts_by_stratum"],
                "admitted_counts_by_fold": summary["admitted_counts_by_fold"],
                "admitted_counts_by_layout": summary["admitted_counts_by_layout"],
                "admitted_counts_by_control_type": summary[
                    "admitted_counts_by_control_type"
                ],
                "row_universe_canonical_hash": summary["row_universe_canonical_hash"],
                "row_identity_source": {
                    "path": f"{ORACLE_PACKAGE_DIRECTORY}/{ROW_UNIVERSE_RECORDS}",
                    "eligible_rows_selector": "status == 'accepted'",
                },
            },
            "target_fields": {
                "fields": list(ORACLE_TARGET_FIELDS),
                "always_required_fields": list(ALWAYS_REQUIRED_TARGET_FIELDS),
                "eligibility_scoped_fields": list(HIDDEN_ONLY_TARGET_FIELDS),
                "u1_target": "mu_oracle_blocks",
                "u2_target": "log_sigma_oracle",
                "scoring_only": ["x_true_blocks"],
                "time_control": ["tau"],
            },
            "analysis_row_exclusions": [
                dict(rule) for rule in EXCLUSION_RULES
            ],
            "excluded_counts_by_reason": summary["excluded_counts_by_reason"],
            "ambiguity_and_disagreement_policy": {
                "ambiguous_geometry_row_count": summary["ambiguous_geometry_row_count"],
                "ambiguous_geometry_excluded_count": summary[
                    "ambiguous_geometry_excluded_count"
                ],
                "disagreement_counts": summary["disagreement_counts"],
                "person_d_must_not_reinstate_excluded_rows": True,
            },
            "source_authorities": {
                "person_c_commit": PERSON_C_COMMIT,
                "person_c_accepted_manifest_sha256": C_ACCEPTED_MANIFEST_SHA256,
                "person_c_visibility_join_sha256": C_VISIBILITY_JOIN_SHA256,
                "person_a_commit": PERSON_A_COMMIT,
                "person_a_frame_map_package_sha256": PERSON_A_FRAME_MAP_PACKAGE_SHA256,
            },
            "metric_contract_after_person_d_predictions_exist": {
                "analysis_config_version": ANALYSIS_CONFIG_VERSION,
                "config_path": "configs/analysis/core.yaml",
                "config_hash": hash_core_analysis_config(),
                "u1_outputs": config["outputs"]["U1"],
                "u2_outputs": config["outputs"]["U2"],
                "u3_outputs": config["outputs"]["U3"],
                "metric_rules": config["metric_rules"],
                "resampling": config["resampling"],
                "coverage_levels": config["coverage_levels"],
                "grouping_hierarchy": config["resampling"]["hierarchy"],
                "permutation_unit": config["resampling"]["permutation_unit"],
                "analysis_arithmetic_dtype": ANALYSIS_ARITHMETIC_DTYPE,
            },
            "dtype_decision": {
                "stored_activation_dtype": STORED_ACTIVATION_DTYPE,
                "analysis_arithmetic_dtype": ANALYSIS_ARITHMETIC_DTYPE,
                "person_d_baselines_consume_activations": False,
            },
        }
    )


def build() -> dict:
    branch = _current_branch()
    require(
        branch == "role/person-b-analysis",
        f"oracle package must be published on role/person-b-analysis, not {branch!r}",
    )
    code_sha = derive_oracle_code_sha(ROOT)

    c_inputs = load_person_c_oracle_inputs(repository_root=ROOT)
    person_a = resolve_person_a_identity(repository_root=ROOT)
    oracle = build_production_oracle_targets(
        person_a, code_sha=code_sha, repository_root=ROOT
    )
    row_universe = build_successor_row_universe(
        c_inputs, oracle, repository_root=ROOT
    )
    summary = summarize_row_universe(row_universe)
    fold = validate_fold_compatibility(row_universe, repository_root=ROOT)
    require(fold["fold_compatibility_pass"], "fold compatibility check failed")
    require(fold["leakage_audit_pass"], "fold leakage audit failed")

    records_sha = _write_jsonl(PACKAGE / ORACLE_TARGET_RECORDS, oracle["target_rows"])
    row_records_sha = _write_jsonl(
        PACKAGE / ROW_UNIVERSE_RECORDS, row_universe["rows"]
    )

    identity_document = build_person_a_identity_document(person_a, code_sha)
    receipt = build_row_universe_receipt(summary, row_records_sha, code_sha)
    ledger = build_admission_ledger(summary, code_sha)
    fold_receipt = build_fold_receipt(fold, code_sha)
    u4 = build_u4_status(c_inputs, code_sha)
    manifest = build_oracle_manifest(
        person_a, summary, oracle, fold, records_sha, row_records_sha, code_sha
    )
    b_to_a = build_b_to_a_handoff(person_a, summary, manifest, fold, code_sha)
    b_to_d = build_b_to_d_handoff(summary, manifest, fold, records_sha, code_sha)

    documents = {
        PERSON_A_IDENTITY_RESOLUTION: identity_document,
        ROW_UNIVERSE_RECEIPT: receipt,
        ADMISSION_LEDGER: ledger,
        FOLD_COMPATIBILITY_RECEIPT: fold_receipt,
        ORACLE_TARGET_MANIFEST: manifest,
        U4_STATUS: u4,
        B_TO_A_HANDOFF: b_to_a,
        B_TO_D_HANDOFF: b_to_d,
    }
    file_hashes = {ORACLE_TARGET_RECORDS: records_sha, ROW_UNIVERSE_RECORDS: row_records_sha}
    for name in ORDERED_JSON_FILES:
        file_hashes[name] = _write_json(PACKAGE / name, documents[name])

    ordered = list(ORDERED_JSON_FILES) + list(ORDERED_JSONL_FILES)
    inventory = {
        "schema_id": "person-b-66-cell-oracle-target-v0.1-sha256-inventory",
        "schema_version": "1.0",
        "decision_date": DECISION_DATE,
        "inventory_excludes_self": True,
        "file_count": len(ordered),
        "files": [
            {
                "path": f"{ORACLE_PACKAGE_DIRECTORY}/{name}",
                "sha256": file_hashes[name],
                "byte_size": (PACKAGE / name).stat().st_size,
            }
            for name in ordered
        ],
    }
    _write_json(PACKAGE / SHA256_INVENTORY, inventory)

    return {
        "code_sha": code_sha,
        "model_hash": person_a["model_hash"],
        "preprocess_hash": person_a["preprocess_hash"],
        "total_model_frame_key_count": summary["total_model_frame_key_count"],
        "target_bearing_key_count": summary["target_bearing_key_count"],
        "no_object_not_applicable_count": summary[
            "no_object_not_applicable_key_count"
        ],
        "admitted_analysis_row_count": summary["admitted_analysis_row_count"],
        "excluded_analysis_row_count": summary["excluded_analysis_row_count"],
        "ambiguous_geometry_row_count": summary["ambiguous_geometry_row_count"],
        "ambiguous_geometry_admitted_count": summary[
            "ambiguous_geometry_admitted_count"
        ],
        "ambiguous_geometry_excluded_count": summary[
            "ambiguous_geometry_excluded_count"
        ],
        "oracle_target_row_count": len(oracle["target_rows"]),
        "fold_compatibility_pass": fold["fold_compatibility_pass"],
        "leakage_audit_pass": fold["leakage_audit_pass"],
        "oracle_target_manifest_sha256": file_hashes[ORACLE_TARGET_MANIFEST],
        "row_universe_receipt_sha256": file_hashes[ROW_UNIVERSE_RECEIPT],
        "b_to_a_handoff_sha256": file_hashes[B_TO_A_HANDOFF],
        "b_to_d_handoff_sha256": file_hashes[B_TO_D_HANDOFF],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()
    try:
        result = build()
    except OracleTargetError as error:
        print(f"PERSON_B_66_CELL_ORACLE_TARGET=FAIL {error}", file=sys.stderr)
        return 1
    if not args.quiet:
        print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
