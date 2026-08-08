#!/usr/bin/env python3
"""Build the Person B 66-cell pre-activation package.

Every artifact this script writes is derivable before Person A performs the
real 66-cell GPU activation extraction.  No activation bytes are read, no
activation path or hash is fabricated, no scientific metric is executed, and
the frozen ten-pilot evidence is never rewritten or relabelled.
"""

from __future__ import annotations

import argparse
import hashlib
import json
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
from mineocclude.analysis.preactivation_66_cell_v0_1 import (  # noqa: E402
    ADMISSION_STRATUM_CORE,
    ADMISSION_STRATUM_SENTINEL,
    ADMISSION_STRATUM_VISIBLE_CONTROL,
    DECISION_DATE,
    EXPECTED_ACTIVATION_CHUNK_COUNT,
    EXPECTED_ACTIVATION_ROW_COUNT,
    EXPECTED_LAYER_COUNT,
    EXPECTED_MODEL_FRAME_KEY_COUNT,
    EXPECTED_TRAJECTORY_COUNT,
    PERSON_A_COMMIT,
    PERSON_A_FRAME_MAP_PACKAGE_PATH,
    PERSON_A_FRAME_MAP_PACKAGE_SHA256,
    PERSON_A_MVP_CONFIG_PATH,
    PERSON_A_MVP_CONFIG_SHA256,
    PERSON_A_STORAGE_DTYPE_PROPOSAL_PATH,
    PERSON_A_STORAGE_DTYPE_PROPOSAL_SHA256,
    PERSON_C_ACCEPTED_MANIFEST_PATH,
    PERSON_C_ACCEPTED_MANIFEST_SHA256,
    PERSON_C_COMMIT,
    PREACTIVATION_PACKAGE_DIRECTORY,
    PREACTIVATION_SCHEMA_VERSION,
    ROW_EXCLUSION_NO_OBJECT,
    ROW_EXCLUSION_OUTSIDE_SELECTION,
    ROW_EXCLUSION_PRE_FIRST_SEEN,
    TEN_PILOT_ACTIVATION_CHUNK_COUNT,
    TEN_PILOT_ACTIVATION_ROW_COUNT,
    TEN_PILOT_ADMITTED_ROW_COUNT,
    TEN_PILOT_EXCLUDED_ROW_COUNT,
    TEN_PILOT_SOURCE_FRAME_COUNT,
    TEN_PILOT_TRAJECTORY_COUNT,
    VERIFIED_ORIGIN_MAIN,
    assess_oracle_target_inputs,
    audit_fold_leakage,
    build_66_cell_fold_manifest,
    build_row_universe,
    build_row_universe_receipt,
    build_u4_heldout_partition,
    derive_preactivation_code_sha,
    load_person_a_frame_map_package,
    load_person_c_accepted_manifest,
    read_bound_blob,
    sha256_bytes,
)

PACKAGE = ROOT / PREACTIVATION_PACKAGE_DIRECTORY

SUCCESSOR_DECISION = "successor_authority_decision.json"
ROW_UNIVERSE_RECEIPT = "row_universe_receipt.json"
FOLD_MANIFEST = "fold_manifest.json"
FOLD_LEAKAGE_AUDIT = "fold_leakage_audit.json"
ORACLE_PREFLIGHT = "oracle_target_preflight.json"
U4_PARTITION = "u4_heldout_partition.json"
B_TO_C_U4_RECEIPT = "b_to_c_u4_selection_receipt.json"
STORAGE_DTYPE_REVIEW = "storage_dtype_review.json"
B_TO_A_HANDOFF = "b_to_a_handoff.json"
B_TO_D_HANDOFF = "b_to_d_handoff.json"
POST_ACTIVATION_PREFLIGHT = "post_activation_analysis_preflight.json"
SHA256_INVENTORY = "sha256_inventory.json"

ORDERED_FILES = (
    SUCCESSOR_DECISION,
    ROW_UNIVERSE_RECEIPT,
    FOLD_MANIFEST,
    FOLD_LEAKAGE_AUDIT,
    ORACLE_PREFLIGHT,
    U4_PARTITION,
    B_TO_C_U4_RECEIPT,
    STORAGE_DTYPE_REVIEW,
    B_TO_A_HANDOFF,
    B_TO_D_HANDOFF,
    POST_ACTIVATION_PREFLIGHT,
)

# Person B-owned evidence supporting the storage-dtype review.  Every path is
# resolved and hashed at build time; nothing here is asserted from memory.
DTYPE_EVIDENCE_ON_THIS_BRANCH = (
    ("pooling_implementation", "src/mineocclude/activations/pool.py"),
    ("activation_store_v2", "src/mineocclude/activations/store_v2.py"),
    (
        "accepted_preflight_activation_contract",
        (
            "docs/status/person_a_phase4_step4_1_production_handoff_preflight_v0_1/"
            "activation_contract.json"
        ),
    ),
    (
        "accepted_preflight_immutable_runtime_configuration",
        (
            "docs/status/person_a_phase4_step4_1_production_handoff_preflight_v0_1/"
            "immutable_runtime_configuration.json"
        ),
    ),
    (
        "step6_frozen_runtime_configuration",
        (
            "docs/status/person_a_step6_runtime_acknowledgement_v0_1/"
            "frozen_runtime_configuration.json"
        ),
    ),
    (
        "person_b_sagemaker_runtime_ratification",
        (
            "docs/status/person_b_phase6_sagemaker_runtime_ratification_v0_1/"
            "sagemaker_runtime_ratification.json"
        ),
    ),
    (
        "person_b_fitted_probe_input_contract",
        (
            "docs/status/person_b_phase4_step4_1_registry_v2_handoff_v0_1/"
            "fitted_probe_input_contract.json"
        ),
    ),
    ("person_a_phase5_storage_decision", "docs/status/person_a_phase5_storage_decision.md"),
    ("person_b_consumer_production_v2", "src/mineocclude/analysis/production_v2.py"),
    (
        "person_b_consumer_positive_control_v2",
        "src/mineocclude/analysis/positive_control_v2.py",
    ),
    ("person_b_ridge_arithmetic", "src/mineocclude/probes/ridge.py"),
    ("person_b_mlp_arithmetic", "src/mineocclude/probes/mlp.py"),
)

DTYPE_EVIDENCE_ON_PERSON_A_BRANCH = (
    ("person_a_frozen_mvp_configuration", PERSON_A_MVP_CONFIG_PATH, PERSON_A_MVP_CONFIG_SHA256),
    (
        "person_a_storage_dtype_proposal",
        PERSON_A_STORAGE_DTYPE_PROPOSAL_PATH,
        PERSON_A_STORAGE_DTYPE_PROPOSAL_SHA256,
    ),
    (
        "person_a_executed_ten_pilot_certification",
        "docs/status/person_a_phase6_closeout_v0_1/step_6_7_certification.json",
        "663eda3638235b168ca10e7cef6ace8f7b385df620f751890326852af8fbb0d8",
    ),
    (
        "person_a_step_7_1_identity_freeze",
        "docs/status/person_a_phase7_mvp_v0_1/step_7_1_identity_freeze.json",
        "b0709a7eaee0384d77ef27c2b42235002bc5dda1c65feb515a8e97ef917b34d0",
    ),
    (
        "person_a_extraction_queue_certification",
        "src/mineocclude/experiments/extraction_queue.py",
        "08e12f4bb25088bb2fd4c18058fd0ac8ab34be2d57824cd4ac986819115cb159",
    ),
)


def _write(path: Path, document: object) -> str:
    payload = canonical_json_bytes(document) + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return hashlib.sha256(payload).hexdigest()


def _file_evidence(relative_path: str) -> dict[str, object]:
    payload = (ROOT / relative_path).read_bytes()
    normalized = payload.replace(b"\r\n", b"\n")
    return {
        "path": relative_path,
        "sha256": hashlib.sha256(normalized).hexdigest(),
        "byte_size": len(normalized),
        "digest_scope": "repository_canonical_lf_bytes",
        "resolved_from": "role/person-b-analysis",
    }


def _bound_evidence(relative_path: str, expected_sha256: str) -> dict[str, object]:
    payload = read_bound_blob(
        PERSON_A_COMMIT,
        relative_path,
        expected_sha256=expected_sha256,
        repository_root=ROOT,
    )
    return {
        "path": relative_path,
        "sha256": sha256_bytes(payload),
        "byte_size": len(payload),
        "digest_scope": "repository_canonical_lf_bytes",
        "resolved_from": f"role/person-a-model@{PERSON_A_COMMIT}",
    }


def build_successor_decision(code_sha: str) -> dict[str, object]:
    return seal_artifact(
        {
            "artifact_type": "person_b_66_cell_successor_authority_decision",
            "artifact_id": "person-b-66-cell-successor-authority-v0.1",
            "code_sha": code_sha,
            "config_hash": hash_core_analysis_config(),
            "input_manifest_hash": PERSON_C_ACCEPTED_MANIFEST_SHA256,
            "preactivation_schema_version": PREACTIVATION_SCHEMA_VERSION,
            "analysis_config_version": ANALYSIS_CONFIG_VERSION,
            "decision_date": DECISION_DATE,
            "decision_owner": "person_b_analysis",
            "decision": "PRODUCTION_MVP_UNIVERSE_BOUND_TO_66_CELL_AUTHORITIES",
            "producer_role": "person_b",
            "synthetic": False,
            "scientific_use": "permitted",
            "verified_origin_main": VERIFIED_ORIGIN_MAIN,
            "bound_authorities": {
                "person_c_commit": PERSON_C_COMMIT,
                "person_c_accepted_manifest_path": PERSON_C_ACCEPTED_MANIFEST_PATH,
                "person_c_accepted_manifest_sha256": PERSON_C_ACCEPTED_MANIFEST_SHA256,
                "person_a_preparation_commit": PERSON_A_COMMIT,
                "person_a_frame_map_package_path": PERSON_A_FRAME_MAP_PACKAGE_PATH,
                "person_a_frame_map_package_sha256": PERSON_A_FRAME_MAP_PACKAGE_SHA256,
            },
            "successor_universe": {
                "accepted_trajectory_count": EXPECTED_TRAJECTORY_COUNT,
                "excluded_trajectory_count": 0,
                "model_frame_key_count": EXPECTED_MODEL_FRAME_KEY_COUNT,
                "join_key": ["trajectory_id", "model_frame_idx"],
                "layer_count": EXPECTED_LAYER_COUNT,
                "expected_activation_row_count": EXPECTED_ACTIVATION_ROW_COUNT,
                "expected_activation_chunk_count": EXPECTED_ACTIVATION_CHUNK_COUNT,
            },
            "superseded_predecessor": {
                "label": "person_b_ten_pilot_certified_universe",
                "trajectory_count": TEN_PILOT_TRAJECTORY_COUNT,
                "source_frame_count": TEN_PILOT_SOURCE_FRAME_COUNT,
                "admitted_row_count": TEN_PILOT_ADMITTED_ROW_COUNT,
                "excluded_row_count": TEN_PILOT_EXCLUDED_ROW_COUNT,
                "activation_row_count": TEN_PILOT_ACTIVATION_ROW_COUNT,
                "activation_chunk_count": TEN_PILOT_ACTIVATION_CHUNK_COUNT,
                "status": "valid_historical_evidence_not_the_production_universe",
                "evidence_overwritten": False,
                "evidence_relabelled": False,
                "evidence_regenerated": False,
                "row_ids_reused_as_66_cell_universe": False,
            },
            "frozen_decisions_not_reopened": {
                "step_4_1_decision": "FAIL",
                "step_4_1_rerun_authorized": False,
                "cross_validation_strategy": "layout_grouped",
                "fold_count": 5,
                "split_seed": 20260719,
                "u4_development_partition": "3_fit_1_validation_2_test_layouts",
            },
            "supersession_style": "additive_dated_successor_record",
        }
    )


def build_b_to_c_u4_receipt(
    partition: dict, universe: dict, code_sha: str
) -> dict[str, object]:
    config = load_core_analysis_config()
    return seal_artifact(
        {
            "artifact_type": "person_b_to_person_c_u4_selection_receipt",
            "artifact_id": "person-b-to-person-c-u4-selection-v0.1",
            "code_sha": code_sha,
            "config_hash": hash_core_analysis_config(),
            "input_manifest_hash": partition["artifact_hash"],
            "preactivation_schema_version": PREACTIVATION_SCHEMA_VERSION,
            "decision_date": DECISION_DATE,
            "producer_role": "person_b",
            "consumer_role": "person_c",
            "consumer_step": "C8.2",
            "person_c_commit": PERSON_C_COMMIT,
            "person_c_accepted_manifest_sha256": PERSON_C_ACCEPTED_MANIFEST_SHA256,
            "person_a_commit": PERSON_A_COMMIT,
            "person_a_frame_map_package_sha256": PERSON_A_FRAME_MAP_PACKAGE_SHA256,
            "u4_partition_artifact_hash": partition["artifact_hash"],
            "layout_partition_frozen": True,
            "heldout_layout_ids": partition["heldout_layout_ids"],
            "heldout_trajectory_ids": partition["heldout_trajectory_ids"],
            "event_ids_frozen": False,
            "frozen_heldout_event_count": None,
            "frozen_heldout_event_ids": None,
            "selection_ready_for_c8_2": False,
            "geometric_only_candidate_event_count": partition[
                "geometric_only_candidate_event_count"
            ],
            "geometric_only_candidate_events": partition["geometric_only_candidate_events"],
            "why_event_ids_cannot_be_frozen_yet": (
                "Person B's frozen Phase 3 Step 3.3 visibility acceptance policy "
                "defines the analysis label as 'visible_flag = geometric_visible "
                "AND empirical_magenta_visible'. The bound Person C 66-cell "
                "handoff records visibility_artifact_path=null and "
                "visibility_artifact_status="
                "'produced_downstream_not_at_c6a_raw_capture_layer', so the "
                "empirical channel does not exist for these cells and no "
                "authoritative reveal event can be named."
            ),
            "remaining_inputs_required": [
                {
                    "input_id": "person_e_empirical_magenta_visibility_for_c6a_66_cells",
                    "owner_role": "person_e",
                    "detail": (
                        "Per-frame empirical_magenta_visible keyed by "
                        "(trajectory_id, model_frame_idx) for all 66 accepted "
                        "trajectories, at the frozen detector version and identity."
                    ),
                },
                {
                    "input_id": "person_c_strict_join_visible_flag_for_c6a_66_cells",
                    "owner_role": "person_c",
                    "detail": (
                        "Person C strict-join artifact publishing visible_flag = "
                        "geometric_visible AND empirical_magenta_visible, with "
                        "quarantine accounting, for episodes 12601-12666."
                    ),
                },
                {
                    "input_id": "u4_heldout_event_count_contract_reconciliation",
                    "owner_role": "person_a_and_person_b",
                    "detail": (
                        "Person A's frozen configs/experiments/mvp.yaml pins "
                        "u4_pilot.heldout_event_count=5. Under Person B's frozen "
                        "layout partition the held-out layouts contain "
                        f"{partition['geometric_only_candidate_event_count']} "
                        "geometric occluded-to-visible transitions, and each is a "
                        "short visibility blip rather than a terminal reveal, so "
                        "the frozen metric_rules.reveal_window_seconds of "
                        f"{config['metric_rules']['reveal_window_seconds']} cannot "
                        "be satisfied. A dated joint decision plus a new run "
                        "identity is required before U4 event IDs are frozen."
                    ),
                },
            ],
            "not_used_in_probe_fit": True,
            "not_used_in_layer_selection": True,
            "not_used_in_direction_construction": True,
            "not_used_in_dose_selection": True,
            "not_used_to_tune_person_e_detector": True,
            "activation_direction_constructed": False,
            "u4_outcomes_inspected": False,
            "heldout_trajectory_count": partition["heldout_trajectory_count"],
            "heldout_model_frame_row_count": sum(
                1
                for row in universe["rows"]
                if row["layout_id"] in partition["heldout_layout_ids"]
            ),
        }
    )


def build_storage_dtype_review(code_sha: str) -> dict[str, object]:
    evidence = {
        name: _file_evidence(path) for name, path in DTYPE_EVIDENCE_ON_THIS_BRANCH
    }
    for name, path, expected in DTYPE_EVIDENCE_ON_PERSON_A_BRANCH:
        evidence[name] = _bound_evidence(path, expected)

    return seal_artifact(
        {
            "artifact_type": "person_b_storage_dtype_review",
            "artifact_id": "person-b-66-cell-storage-dtype-review-v0.1",
            "code_sha": code_sha,
            "config_hash": hash_core_analysis_config(),
            "input_manifest_hash": PERSON_A_STORAGE_DTYPE_PROPOSAL_SHA256,
            "preactivation_schema_version": PREACTIVATION_SCHEMA_VERSION,
            "decision_date": DECISION_DATE,
            "decision_owner": "person_b_analysis",
            "producer_role": "person_b",
            "reviewed_proposal": {
                "path": PERSON_A_STORAGE_DTYPE_PROPOSAL_PATH,
                "sha256": PERSON_A_STORAGE_DTYPE_PROPOSAL_SHA256,
                "commit": PERSON_A_COMMIT,
                "proposal_hash_independently_verified": True,
            },
            "review_complete": True,
            "resolution_option": "A",
            "chosen_stored_activation_dtype": "float32",
            "chosen_analysis_arithmetic_dtype": "float64",
            "chosen_hooked_source_tensor_dtype": "float16",
            "evidence": dict(sorted(evidence.items())),
            "findings": [
                {
                    "finding_id": "mvp_yaml_is_internally_inconsistent",
                    "evidence": ["person_a_frozen_mvp_configuration"],
                    "detail": (
                        "The same frozen file pins extraction.stored_dtype=float16, "
                        "extraction.vector_width=2048 and "
                        "storage.bytes_per_activation_row=8192.68303094984. "
                        "2048 float16 elements occupy 4096 bytes; the declared rate "
                        "requires a 4-byte element. The float16 declaration is the "
                        "outlier inside its own file."
                    ),
                },
                {
                    "finding_id": "accepted_contracts_already_pin_float32",
                    "evidence": [
                        "accepted_preflight_activation_contract",
                        "accepted_preflight_immutable_runtime_configuration",
                        "step6_frozen_runtime_configuration",
                    ],
                    "detail": (
                        "pooled_representation.stored_dtype=float32 with "
                        "analysis_dtype=float64 is pinned by three accepted "
                        "contract artifacts that are present on origin/main, not "
                        "only on Person A's branch."
                    ),
                },
                {
                    "finding_id": "person_b_already_ratified_float32_storage",
                    "evidence": [
                        "person_b_sagemaker_runtime_ratification",
                        "person_b_fitted_probe_input_contract",
                    ],
                    "detail": (
                        "Person B's own Phase 6 SageMaker runtime ratification "
                        "records stored_dtype=float32 and analysis_dtype=float64. "
                        "Choosing float32 preserves a ratification Person B has "
                        "already made rather than creating a new one."
                    ),
                },
                {
                    "finding_id": "implementation_cannot_emit_float16_pooled_vectors",
                    "evidence": ["pooling_implementation"],
                    "detail": (
                        "select_and_pool upcasts the selected visual tokens with "
                        ".to(dtype=torch.float32) and then raises INVALID_RESULT "
                        "unless pooled.dtype is exactly torch.float32."
                    ),
                },
                {
                    "finding_id": "person_b_consumers_reject_non_float32_vectors",
                    "evidence": [
                        "person_b_consumer_production_v2",
                        "person_b_consumer_positive_control_v2",
                    ],
                    "detail": (
                        "Person B's accepted v2 consumers fail closed on any loaded "
                        "activation vector whose dtype is not float32, so float16 "
                        "storage would require changing Person B code that is "
                        "already bound to executed evidence."
                    ),
                },
                {
                    "finding_id": "executed_production_measured_four_byte_elements",
                    "evidence": ["person_a_executed_ten_pilot_certification"],
                    "detail": (
                        "All ten executed pilots measure ~8192.5-8193.1 bytes per "
                        "activation row at width 2048, implying a 4.0-byte element."
                    ),
                },
                {
                    "finding_id": "hooked_tensor_dtype_is_a_separate_question",
                    "evidence": [
                        "person_a_phase5_storage_decision",
                        "step6_frozen_runtime_configuration",
                    ],
                    "detail": (
                        "model.precision=float16 and "
                        "extraction.source_tensor_dtype=float16 are correct and "
                        "unaffected. The residual stream is hooked in float16; "
                        "pooling is a separate step. Only the pooled storage dtype "
                        "was in dispute."
                    ),
                },
                {
                    "finding_id": "authoritative_mvp_yaml_is_not_on_main",
                    "evidence": ["person_a_frozen_mvp_configuration"],
                    "detail": (
                        "configs/experiments/mvp.yaml on origin/main "
                        f"({VERIFIED_ORIGIN_MAIN}) and on role/person-b-analysis is "
                        "a 102-byte header stub. The 5958-byte frozen configuration "
                        "exists only on role/person-a-model. Any successor "
                        "configuration must therefore be published as a new file "
                        "identity, not an in-place edit of an accepted run."
                    ),
                },
            ],
            "result_changing_assessment": {
                "result_changing_by_person_a_step_7_1_register": True,
                "numerically_result_changing_versus_executed_artifacts": False,
                "reason": (
                    "extraction.stored_dtype is listed as a result-changing path, "
                    "so the change requires a new run identity and a dated decision "
                    "record. It changes no produced number, because every executed "
                    "pooled artifact and the pooling implementation are already "
                    "float32."
                ),
            },
            "person_b_approvals": {
                "approves_successor_extraction_contract": True,
                "approved_stored_activation_dtype": "float32",
                "approved_analysis_arithmetic_dtype": "float64",
                "person_a_may_create_new_successor_config_and_run_identity": True,
                "new_run_identity_required": True,
                "additive_dated_decision_record_required": True,
                "additional_scientific_review_required": False,
                "in_place_edit_of_accepted_run_authorized": False,
                "historical_ten_pilot_artifacts_may_be_rewritten": False,
                "person_b_edited_person_a_mvp_yaml": False,
            },
            "conditions": [
                (
                    "Person A publishes a new successor configuration identity; the "
                    "accepted Step 7.1 freeze of configs/experiments/mvp.yaml is not "
                    "edited in place."
                ),
                (
                    "The successor configuration sets extraction.stored_dtype=float32 "
                    "and leaves storage.bytes_per_activation_row=8192.68303094984 and "
                    "extraction.vector_width=2048 unchanged."
                ),
                (
                    "The successor run identity is distinct from the ten-pilot run "
                    "identity, and no ten-pilot artifact is regenerated or relabelled."
                ),
                (
                    "The successor activation index declares stored_dtype=float32 so "
                    "Person B's fail-closed dtype check verifies rather than assumes "
                    "it."
                ),
            ],
            "scope_note": (
                "This review resolves the pooled storage dtype only. It does not "
                "reopen model precision, hook site, pooling identity, vector width, "
                "layer count, or the frozen Step 4.1 FAIL decision."
            ),
        }
    )


def build_b_to_a_handoff(
    receipt: dict,
    fold_manifest: dict,
    leakage: dict,
    oracle: dict,
    partition: dict,
    dtype_review: dict,
    code_sha: str,
) -> dict[str, object]:
    return seal_artifact(
        {
            "artifact_type": "person_b_to_person_a_66_cell_handoff",
            "artifact_id": "person-b-to-person-a-66-cell-v0.1",
            "code_sha": code_sha,
            "config_hash": hash_core_analysis_config(),
            "input_manifest_hash": receipt["artifact_hash"],
            "preactivation_schema_version": PREACTIVATION_SCHEMA_VERSION,
            "decision_date": DECISION_DATE,
            "producer_role": "person_b",
            "consumer_role": "person_a",
            "consumer_receipt_present": False,
            "downstream_acceptance_claimed": False,
            "person_c_commit": PERSON_C_COMMIT,
            "person_c_accepted_manifest_path": PERSON_C_ACCEPTED_MANIFEST_PATH,
            "person_c_accepted_manifest_sha256": PERSON_C_ACCEPTED_MANIFEST_SHA256,
            "person_a_commit": PERSON_A_COMMIT,
            "person_a_frame_map_package_path": PERSON_A_FRAME_MAP_PACKAGE_PATH,
            "person_a_frame_map_package_sha256": PERSON_A_FRAME_MAP_PACKAGE_SHA256,
            "person_b_row_universe_receipt": {
                "path": f"{PREACTIVATION_PACKAGE_DIRECTORY}/{ROW_UNIVERSE_RECEIPT}",
                "artifact_hash": receipt["artifact_hash"],
            },
            "person_b_fold_manifest": {
                "path": f"{PREACTIVATION_PACKAGE_DIRECTORY}/{FOLD_MANIFEST}",
                "artifact_hash": fold_manifest["artifact_hash"],
                "leakage_audit_artifact_hash": leakage["artifact_hash"],
                "leakage_audit_pass": leakage["leakage_audit_pass"],
            },
            "person_b_oracle_target_manifest": {
                "path": None,
                "artifact_hash": None,
                "status": oracle["stage_status"],
                "preflight_path": f"{PREACTIVATION_PACKAGE_DIRECTORY}/{ORACLE_PREFLIGHT}",
                "preflight_artifact_hash": oracle["artifact_hash"],
            },
            "analysis_row_universe": {
                "join_key": ["trajectory_id", "model_frame_idx"],
                "model_frame_key_count": receipt["model_frame_key_count"],
                "admitted_analysis_row_count": receipt["admitted_analysis_row_count"],
                "excluded_analysis_row_count": receipt["excluded_analysis_row_count"],
                "trajectory_count": EXPECTED_TRAJECTORY_COUNT,
                "layer_count": EXPECTED_LAYER_COUNT,
                "expected_activation_row_count": EXPECTED_ACTIVATION_ROW_COUNT,
                "expected_activation_chunk_count": EXPECTED_ACTIVATION_CHUNK_COUNT,
                "row_identity_source": {
                    "path": f"{PREACTIVATION_PACKAGE_DIRECTORY}/{FOLD_MANIFEST}",
                    "artifact_hash": fold_manifest["artifact_hash"],
                    "field": "memberships",
                },
                "extraction_scope_note": (
                    "Person A extracts activations for all "
                    f"{EXPECTED_MODEL_FRAME_KEY_COUNT} model frames. Row-level "
                    "analysis exclusion is a Person B decision applied after "
                    "extraction and never a reason to skip a frame."
                ),
            },
            "exclusion_rules": [
                {
                    "exclusion_reason": ROW_EXCLUSION_NO_OBJECT,
                    "rule": "control_type == 'no_object_control'",
                    "is_trajectory_rejection": False,
                },
                {
                    "exclusion_reason": ROW_EXCLUSION_PRE_FIRST_SEEN,
                    "rule": "model_frame_idx < first geometric_visible index",
                    "is_trajectory_rejection": False,
                },
                {
                    "exclusion_reason": ROW_EXCLUSION_OUTSIDE_SELECTION,
                    "rule": (
                        "geometric_visible and control_type not in "
                        "{'no_wall_visible_control'}"
                    ),
                    "is_trajectory_rejection": False,
                },
            ],
            "dtype_decision": {
                "path": f"{PREACTIVATION_PACKAGE_DIRECTORY}/{STORAGE_DTYPE_REVIEW}",
                "artifact_hash": dtype_review["artifact_hash"],
                "approved_stored_activation_dtype": "float32",
                "approved_analysis_arithmetic_dtype": "float64",
                "approves_successor_extraction_contract": True,
                "new_run_identity_required": True,
                "person_b_edited_person_a_mvp_yaml": False,
            },
            "heldout_partition_status": {
                "path": f"{PREACTIVATION_PACKAGE_DIRECTORY}/{U4_PARTITION}",
                "artifact_hash": partition["artifact_hash"],
                "layout_partition_frozen": True,
                "heldout_layout_ids": partition["heldout_layout_ids"],
                "event_ids_frozen": False,
                "u4_outcomes_inspected": False,
                "activation_direction_constructed": False,
            },
            "required_activation_index_fields": {
                "row_key": ["trajectory_id", "model_frame_idx", "layer_idx", "hook_site"],
                "required_index_fields": [
                    "activation_store_format",
                    "run_id",
                    "extraction_artifact_id",
                    "model_hash",
                    "preprocess_hash",
                    "hook_site",
                    "pooling_identity",
                    "stored_dtype",
                    "vector_width",
                    "layer_count",
                    "activation_row_count",
                    "activation_chunk_count",
                    "c_accepted_manifest_sha256",
                    "c_source_commit",
                    "person_a_frame_map_package_sha256",
                    "chunk_sha256",
                    "chunk_byte_size",
                    "chunk_row_count",
                    "stable_row_order_declared",
                ],
                "required_per_trajectory_fields": [
                    "trajectory_id",
                    "layout_id",
                    "episode_id",
                    "planned_cell_id",
                    "model_frame_count",
                    "activation_row_count",
                    "activation_chunk_count",
                ],
                "required_values": {
                    "hook_site": "decoder_layer_output_residual_stream",
                    "pooling_identity": "person-a-visual-token-mean-v1.0",
                    "stored_dtype": "float32",
                    "vector_width": 2048,
                    "layer_count": EXPECTED_LAYER_COUNT,
                    "activation_row_count": EXPECTED_ACTIVATION_ROW_COUNT,
                    "activation_chunk_count": EXPECTED_ACTIVATION_CHUNK_COUNT,
                },
                "byte_verification_required": True,
                "activation_paths_or_hashes_supplied_by_person_b": False,
            },
        }
    )


def build_b_to_d_handoff(
    receipt: dict,
    fold_manifest: dict,
    oracle: dict,
    dtype_review: dict,
    code_sha: str,
) -> dict[str, object]:
    config = load_core_analysis_config()
    return seal_artifact(
        {
            "artifact_type": "person_b_to_person_d_66_cell_handoff",
            "artifact_id": "person-b-to-person-d-66-cell-v0.1",
            "code_sha": code_sha,
            "config_hash": hash_core_analysis_config(),
            "input_manifest_hash": receipt["artifact_hash"],
            "preactivation_schema_version": PREACTIVATION_SCHEMA_VERSION,
            "decision_date": DECISION_DATE,
            "producer_role": "person_b",
            "consumer_role": "person_d",
            "consumer_receipt_present": False,
            "downstream_acceptance_claimed": False,
            "person_c_commit": PERSON_C_COMMIT,
            "person_c_accepted_manifest_path": PERSON_C_ACCEPTED_MANIFEST_PATH,
            "person_c_accepted_manifest_sha256": PERSON_C_ACCEPTED_MANIFEST_SHA256,
            "person_b_fold_manifest": {
                "path": f"{PREACTIVATION_PACKAGE_DIRECTORY}/{FOLD_MANIFEST}",
                "artifact_hash": fold_manifest["artifact_hash"],
            },
            "person_b_oracle_target_manifest": {
                "path": None,
                "artifact_hash": None,
                "status": oracle["stage_status"],
                "preflight_path": f"{PREACTIVATION_PACKAGE_DIRECTORY}/{ORACLE_PREFLIGHT}",
                "preflight_artifact_hash": oracle["artifact_hash"],
                "baselines_requiring_oracle_targets_are_blocked": True,
            },
            "eligible_baseline_row_universe": {
                "join_key": ["trajectory_id", "model_frame_idx"],
                "admitted_analysis_row_count": receipt["admitted_analysis_row_count"],
                "excluded_analysis_row_count": receipt["excluded_analysis_row_count"],
                "admitted_row_counts_by_scope": receipt["admitted_row_counts_by_scope"],
                "admitted_row_counts_by_stratum": receipt["admitted_row_counts_by_stratum"],
                "admitted_row_counts_by_layout": receipt["admitted_row_counts_by_layout"],
                "row_universe_canonical_hash": receipt["row_universe_canonical_hash"],
                "row_identity_source": {
                    "path": f"{PREACTIVATION_PACKAGE_DIRECTORY}/{FOLD_MANIFEST}",
                    "artifact_hash": fold_manifest["artifact_hash"],
                    "field": "memberships",
                    "row_key": ["trajectory_id", "model_frame_idx"],
                    "eligible_rows_selector": "status == 'accepted'",
                    "per_row_fields": [
                        "trajectory_id",
                        "model_frame_idx",
                        "layout_id",
                        "fold_idx",
                        "status",
                        "exclusion_reason",
                        "analysis_scopes",
                        "admission_stratum",
                    ],
                },
            },
            "sample_and_grouping_identity": {
                "grouping_hierarchy": config["resampling"]["hierarchy"],
                "permutation_unit": config["resampling"]["permutation_unit"],
                "fold_strategy": "layout_grouped",
                "fold_count": config["cross_validation"]["fold_count"],
                "split_seed": config["cross_validation"]["split_seed"],
                "inner_fold_count": config["cross_validation"]["inner_fold_count"],
                "layout_assignments": fold_manifest["layout_assignments"],
                "trajectory_counts_by_fold": fold_manifest["trajectory_counts_by_fold"],
                "layout_counts_by_fold": fold_manifest["layout_counts_by_fold"],
            },
            "metric_api_identity": {
                "analysis_config_version": ANALYSIS_CONFIG_VERSION,
                "config_hash": hash_core_analysis_config(),
                "config_path": "configs/analysis/core.yaml",
                "u1_outputs": config["outputs"]["U1"],
                "u2_outputs": config["outputs"]["U2"],
                "u3_outputs": config["outputs"]["U3"],
                "metric_rules": config["metric_rules"],
                "resampling": config["resampling"],
                "coverage_levels": config["coverage_levels"],
            },
            "analysis_row_exclusions": [
                {
                    "exclusion_reason": ROW_EXCLUSION_NO_OBJECT,
                    "row_count": next(
                        (
                            item["row_count"]
                            for item in receipt["excluded_row_counts_by_reason"]
                            if item["exclusion_reason"] == ROW_EXCLUSION_NO_OBJECT
                        ),
                        0,
                    ),
                    "is_trajectory_rejection": False,
                },
                {
                    "exclusion_reason": ROW_EXCLUSION_PRE_FIRST_SEEN,
                    "row_count": next(
                        (
                            item["row_count"]
                            for item in receipt["excluded_row_counts_by_reason"]
                            if item["exclusion_reason"] == ROW_EXCLUSION_PRE_FIRST_SEEN
                        ),
                        0,
                    ),
                    "is_trajectory_rejection": False,
                },
                {
                    "exclusion_reason": ROW_EXCLUSION_OUTSIDE_SELECTION,
                    "row_count": next(
                        (
                            item["row_count"]
                            for item in receipt["excluded_row_counts_by_reason"]
                            if item["exclusion_reason"] == ROW_EXCLUSION_OUTSIDE_SELECTION
                        ),
                        0,
                    ),
                    "is_trajectory_rejection": False,
                },
            ],
            "dtype_decision_affecting_person_d_inputs": {
                "path": f"{PREACTIVATION_PACKAGE_DIRECTORY}/{STORAGE_DTYPE_REVIEW}",
                "artifact_hash": dtype_review["artifact_hash"],
                "stored_activation_dtype": "float32",
                "analysis_arithmetic_dtype": "float64",
                "person_d_baselines_consume_activations": False,
                "person_d_arithmetic_must_match_analysis_dtype": True,
                "impact": (
                    "Person D's non-activation baselines are unaffected by the "
                    "stored dtype. Any Person D comparison that shares Person B's "
                    "metric API must promote to float64 exactly as Person B does."
                ),
            },
            "admission_strata": [
                ADMISSION_STRATUM_CORE,
                ADMISSION_STRATUM_SENTINEL,
                ADMISSION_STRATUM_VISIBLE_CONTROL,
            ],
        }
    )


def build_post_activation_preflight(
    receipt: dict,
    fold_manifest: dict,
    oracle: dict,
    code_sha: str,
) -> dict[str, object]:
    config = load_core_analysis_config()
    return seal_artifact(
        {
            "artifact_type": "person_b_66_cell_post_activation_preflight",
            "artifact_id": "person-b-66-cell-post-activation-preflight-v0.1",
            "code_sha": code_sha,
            "config_hash": hash_core_analysis_config(),
            "input_manifest_hash": receipt["artifact_hash"],
            "preactivation_schema_version": PREACTIVATION_SCHEMA_VERSION,
            "decision_date": DECISION_DATE,
            "producer_role": "person_b",
            "executed": False,
            "activation_paths_fabricated": False,
            "activation_hashes_fabricated": False,
            "metrics_executed_against_synthetic_activations": False,
            "u1_u3_configuration": {
                "u1": {
                    "outputs": config["outputs"]["U1"],
                    "target": "mu_oracle_blocks",
                    "scopes": ["hidden_mean"],
                    "estimator": "mineocclude.probes.ridge.fit_ridge_oof",
                    "alpha_grid": config["ridge"]["alpha_grid"],
                    "alpha_selection_scope": config["ridge"]["selection_scope"],
                },
                "u2": {
                    "outputs": config["outputs"]["U2"],
                    "target": "log_sigma_oracle",
                    "scopes": ["hidden_spread"],
                    "coverage_levels": config["coverage_levels"],
                    "partial_correlation_controls": config["metric_rules"][
                        "partial_correlation_controls"
                    ],
                },
                "u3": {
                    "outputs": config["outputs"]["U3"],
                    "scopes": ["hidden_mean", "hidden_spread"],
                    "reveal_window_seconds": config["metric_rules"][
                        "reveal_window_seconds"
                    ],
                    "blocked_until_visible_flag_available": True,
                },
                "u4": {
                    "prepared": False,
                    "reason": "predeclared_partition_frozen_but_events_not_frozen",
                },
                "cross_validation": {
                    "strategy": "layout_grouped",
                    "fold_count": config["cross_validation"]["fold_count"],
                    "split_seed": config["cross_validation"]["split_seed"],
                    "inner_fold_count": config["cross_validation"]["inner_fold_count"],
                    "fold_manifest_artifact_hash": fold_manifest["artifact_hash"],
                    "fit_scaler_on_training_fold_only": True,
                },
                "resampling": config["resampling"],
            },
            "schema_decisions_remaining": [],
            "no_further_schema_decision_required_after_activation_index": True,
            "expected_activation_key_validation": {
                "activation_key": [
                    "trajectory_id",
                    "model_frame_idx",
                    "layer_idx",
                    "hook_site",
                ],
                "expected_model_frame_key_count": EXPECTED_MODEL_FRAME_KEY_COUNT,
                "expected_layer_count": EXPECTED_LAYER_COUNT,
                "expected_activation_row_count": EXPECTED_ACTIVATION_ROW_COUNT,
                "expected_activation_chunk_count": EXPECTED_ACTIVATION_CHUNK_COUNT,
                "expected_hook_site": "decoder_layer_output_residual_stream",
                "expected_stored_dtype": "float32",
                "expected_vector_width": 2048,
                "cardinality_identity": (
                    f"{EXPECTED_MODEL_FRAME_KEY_COUNT} model frames x "
                    f"{EXPECTED_LAYER_COUNT} layers = "
                    f"{EXPECTED_ACTIVATION_ROW_COUNT} activation rows"
                ),
                "duplicate_activation_key_tolerance": 0,
                "missing_activation_key_tolerance": 0,
                "row_universe_canonical_hash": receipt["row_universe_canonical_hash"],
                "fold_manifest_artifact_hash": fold_manifest["artifact_hash"],
            },
            "blocking_inputs_before_u1_u3_execution": [
                {
                    "input_id": "person_a_66_cell_activation_index",
                    "owner_role": "person_a",
                    "status": "not_yet_produced",
                },
                {
                    "input_id": "person_b_66_cell_oracle_target_manifest",
                    "owner_role": "person_b_blocked_on_person_c",
                    "status": oracle["stage_status"],
                },
            ],
        }
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--print-summary",
        action="store_true",
        help="Print a machine-readable summary of the produced package.",
    )
    args = parser.parse_args()

    code_sha = derive_preactivation_code_sha(ROOT)
    c_manifest = load_person_c_accepted_manifest(repository_root=ROOT)
    a_package = load_person_a_frame_map_package(repository_root=ROOT)
    universe = build_row_universe(c_manifest, a_package)

    receipt = build_row_universe_receipt(universe, code_sha=code_sha)
    fold_manifest = build_66_cell_fold_manifest(universe, code_sha=code_sha)
    leakage = audit_fold_leakage(fold_manifest, universe, code_sha=code_sha)
    oracle = assess_oracle_target_inputs(
        universe, code_sha=code_sha, repository_root=ROOT
    )
    partition = build_u4_heldout_partition(universe, code_sha=code_sha)
    u4_receipt = build_b_to_c_u4_receipt(partition, universe, code_sha)
    dtype_review = build_storage_dtype_review(code_sha)
    decision = build_successor_decision(code_sha)
    b_to_a = build_b_to_a_handoff(
        receipt, fold_manifest, leakage, oracle, partition, dtype_review, code_sha
    )
    b_to_d = build_b_to_d_handoff(receipt, fold_manifest, oracle, dtype_review, code_sha)
    preflight = build_post_activation_preflight(receipt, fold_manifest, oracle, code_sha)

    documents = {
        SUCCESSOR_DECISION: decision,
        ROW_UNIVERSE_RECEIPT: receipt,
        FOLD_MANIFEST: fold_manifest,
        FOLD_LEAKAGE_AUDIT: leakage,
        ORACLE_PREFLIGHT: oracle,
        U4_PARTITION: partition,
        B_TO_C_U4_RECEIPT: u4_receipt,
        STORAGE_DTYPE_REVIEW: dtype_review,
        B_TO_A_HANDOFF: b_to_a,
        B_TO_D_HANDOFF: b_to_d,
        POST_ACTIVATION_PREFLIGHT: preflight,
    }

    file_hashes: dict[str, str] = {}
    for name in ORDERED_FILES:
        file_hashes[name] = _write(PACKAGE / name, documents[name])

    inventory = {
        "schema_id": "person-b-66-cell-preactivation-v0.1-sha256-inventory",
        "schema_version": "1.0",
        "decision_date": DECISION_DATE,
        "inventory_excludes_self": True,
        "file_count": len(ORDERED_FILES),
        "files": [
            {
                "path": f"{PREACTIVATION_PACKAGE_DIRECTORY}/{name}",
                "sha256": file_hashes[name],
                "byte_size": (PACKAGE / name).stat().st_size,
            }
            for name in ORDERED_FILES
        ],
    }
    _write(PACKAGE / SHA256_INVENTORY, inventory)

    if args.print_summary:
        summary = {
            "code_sha": code_sha,
            "trajectory_count": EXPECTED_TRAJECTORY_COUNT,
            "model_frame_key_count": receipt["model_frame_key_count"],
            "admitted_analysis_row_count": receipt["admitted_analysis_row_count"],
            "excluded_analysis_row_count": receipt["excluded_analysis_row_count"],
            "fold_leakage_audit_pass": leakage["leakage_audit_pass"],
            "oracle_stage_status": oracle["stage_status"],
            "oracle_state_bytes_present": oracle[
                "state_payload_bytes_present_on_this_host"
            ],
            "heldout_layout_ids": partition["heldout_layout_ids"],
            "heldout_candidate_event_count": partition[
                "geometric_only_candidate_event_count"
            ],
            "file_sha256": {
                f"{PREACTIVATION_PACKAGE_DIRECTORY}/{name}": file_hashes[name]
                for name in ORDERED_FILES
            },
        }
        print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
