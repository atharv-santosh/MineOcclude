"""Strict, read-only certification validator for the final Person B package.

The package is a record of integration readiness, not a scientific rerun.  This
module verifies its canonical JSON bytes, immutable inventory, Git-object
provenance, and fail-closed readiness decision without writing repository state.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

SCHEMA_ID = "person-b-final-integration-readiness-v0-1"
SCHEMA_VERSION = "1.0"
PACKAGE_DIRECTORY = "docs/status/person_b_final_integration_readiness_certification_v0_1"
PACKAGE_FILES = (
    "authority_binding.json",
    "dependency_status.json",
    "evidence_validation.json",
    "final_integration_handoff.json",
    "integration_readiness_receipt.json",
    "roadmap_status.json",
    "producing_commit_binding.json",
    "sha256_inventory.json",
)
PRODUCING_BINDING_FILE = "producing_commit_binding.json"
INVENTORY_FILE = "sha256_inventory.json"
INVENTORIED_FILES = tuple(
    name for name in PACKAGE_FILES if name != INVENTORY_FILE
)
STABLE_CERTIFICATION_PATHS = tuple(
    name for name in PACKAGE_FILES if name not in {PRODUCING_BINDING_FILE, INVENTORY_FILE}
) + (
    "src/mineocclude/analysis/final_integration_readiness_v0_1.py",
    "scripts/validate_person_b_final_integration_readiness_v0_1.py",
    "tests/analysis/test_person_b_final_integration_readiness_v0_1.py",
)
HASH_CHAIN_INPUTS = (
    "authority_binding.json",
    "dependency_status.json",
    "evidence_validation.json",
    "roadmap_status.json",
)

BRANCH = "role/person-b-analysis"
EVIDENCE_SNAPSHOT_COMMIT = "7f9faa4ab1434099e03dd9c266d5617dd17b262b"
VERIFIED_MAIN_COMMIT = "15adc43674420ae35921847a953ebbee2135f142"
HANDOFF_COMMIT = "1905f4bec7c917baafa084d7bf3a473fb8e40460"
HANDOFF_PATH = (
    "docs/status/integration/mvp_step4_1_candidate_v0_1/handoffs/"
    "person_b_next_phase_input_manifest.json"
)
HANDOFF_SHA256 = "60b98bf60fb696a052a3ebe9f5ba8af846977da5871bd760f5c71a42f191d6c6"
HANDOFF_SIZE = 25_849
HANDOFF_BLOB_OID = "040c85ce2a2b9e1df161a2c613f42ffc2203a01d"
EXTERNAL_SHA256 = "1a25d2186912ba72fdbf123ea9f07b2255bd0e55c6a48a1a50e3b7c0f23eb1e9"
EXTERNAL_SIZE = 245_491_346
EXTERNAL_PATH = (
    "/home/sagemaker-user/person-a-phase6-approved-outputs/"
    "person-a-phase6-ten-pilot-expansion-seed-20260725/combined_activation_index.json"
)
PERSON_C_ACCEPTED_PILOT_PATH = (
    "docs/status/person_c_phase6_ten_pilot_expansion_acceptance_v0_1/"
    "accepted_pilot_manifest.json"
)
PERSON_C_COMMIT = "c6bff25b5ef4f5fdb0e1ef0ce0d22e3f8b5e4960"
PERSON_C_ACCEPTED_PILOT_SHA256 = "7a12b8a5c5ce8b81b32bcdb044f72d5c4d9ada41af9a9402d3ac52904e494be2"
EXPECTED_TERMINAL_CHECKPOINT = "Phase 9 Step 9.8 — Freeze and tag the MVP analysis identity"
EXPECTED_ROADMAP_SOURCE = {
    "path": r"C:\Users\gensa\Downloads\MineOcclude_Person_B_MVP_Week_1_Only (4).docx",
    "sha256": "fb1fab1c960e979749cf0e7badcaaa2dae5ae919bc2d3c362c0c77d5e74ce6c4",
    "size_bytes": 71_186,
    "title": "MineOcclude — Person B MVP Execution Manual",
    "subtitle": "Week 1 only · Phase 0 through Phase 9",
    "version": None,
}
EXPECTED_CLOSEOUT = {
    "path": "docs/status/person_b_week1_mvp_closeout_v0_1",
    "roadmap_step_count": 85,
    "roadmap_matrix_path": "docs/status/person_b_week1_mvp_closeout_v0_1/roadmap_completion_matrix.json",
    "roadmap_matrix_sha256": "858e616668560688359e497770875b85f03c610154ac5877a2b577160b981ffc",
    "roadmap_matrix_size_bytes": 41_409,
    "validation_receipt_path": "docs/status/person_b_week1_mvp_closeout_v0_1/validation_receipt.json",
    "validation_receipt_sha256": "b20364e3fed7f2671824f2ff11790915129be1bb476ad74cb37532d871288305",
    "validation_receipt_size_bytes": 417,
}
EXPECTED_UNRESOLVED_ASSIGNED_SCOPE = [
    "Full 66-trajectory A activations and model-input handoff are absent or unauthorized.",
    "Full-MVP B targets, folds, probes, U1-U3, and post-Step-4.1 analysis are absent.",
    "Matched D full baselines are absent.",
    "E full registry, measurement, and U4 closure are absent.",
    "Clean reproduction and a result tag remain absent.",
    "The integration candidate authority and its Person C accepted-pilot input are not reachable in the current tree; their source Git objects remain independently verified.",
]
EXPECTED_UNRESOLVED_BLOCKERS = [
    "Authoritative Week-1 roadmap is not terminally complete.",
    "Candidate authority commit and manifest are not reachable from the current branch.",
    "One candidate input is source-object verified but absent from the current tree.",
    "External activation bytes are authority-bound but not locally materialized or independently byte-verified in this Windows worktree.",
    "Full-66 A activations/model-input handoff, B analysis, matched D baselines, and E registry/measurement/U4 closure are absent or unauthorized.",
    "U4 remains unauthorized and uninspected; synthetic fixtures are not scientific evidence.",
    "No clean reproduction/result tag is authorized.",
]
EXPECTED_COUNTS = {
    "trajectory_count": 10,
    "admitted_sample_count": 1_695,
    "exclusion_count": 179,
    "activation_row_count": 37_480,
    "activation_chunk_count": 200,
    "fold_count": 5,
}

AUTHORITY_COMMITS = {
    "person_a": "397ba849adc63df80912c21dd1efacb1e29b8977",
    "person_b": "8c5374d00983e6fec22f560a9fd5849e92060f3e",
    "person_c": PERSON_C_COMMIT,
    "person_d": "5ea6ce92890da7faa46f6aa837135081633d5f3d",
    "person_e": "ab41a76ce0c855c0ac54c59c736bac7599f7e69d",
}
EXPECTED_TRAJECTORY_IDS = [
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
EXPECTED_FOLD_TO_LAYOUT = [
    {"fold_idx": 0, "layout_id": "layout_03"},
    {"fold_idx": 1, "layout_id": "layout_00"},
    {"fold_idx": 2, "layout_id": "layout_01"},
    {"fold_idx": 3, "layout_id": "layout_04"},
    {"fold_idx": 4, "layout_id": "layout_02"},
]
EXPECTED_ACCEPTED_IDENTITY_SET = {
    "source_run_ids": ["runtime_pilot_session_2026_07_22"],
    "trajectory_ids": EXPECTED_TRAJECTORY_IDS,
    "sample_join_key": ["trajectory_id", "model_frame_idx"],
    "admitted_sample_count": EXPECTED_COUNTS["admitted_sample_count"],
    "excluded_sample_count": EXPECTED_COUNTS["exclusion_count"],
    "activation_row_count": EXPECTED_COUNTS["activation_row_count"],
    "activation_chunk_count": EXPECTED_COUNTS["activation_chunk_count"],
    "fold_count": EXPECTED_COUNTS["fold_count"],
    "fold_to_layout": EXPECTED_FOLD_TO_LAYOUT,
}
EXPECTED_IDENTITY_CONTRACT = {
    "rollout_identity_fields": ["source_run_id", "producing_run_id", "run_id"],
    "trajectory_identity_fields": ["trajectory_id", "layout_id"],
    "sample_identity_fields": ["trajectory_id", "model_frame_idx", "source_frame_id"],
    "activation_identity_fields": [
        "artifact_id",
        "chunk_id",
        "trajectory_id",
        "model_frame_idx",
        "layer",
        "site",
    ],
    "fold_identity_fields": ["fold_idx", "layout_id", "trajectory_id", "model_frame_idx"],
    "standalone_rollout_id_status": "not_defined_by_the_accepted_step4_1_capture_authority",
    "standalone_rollout_id_handling": "Do not synthesize an alias. Use the accepted source_run_id, producing_run_id, and run_id fields exactly as stored.",
}

# The candidate manifest is an authority input, not merely a set of advisory
# labels.  Keep its twelve rows ordered and bind every row to the exact source
# object that was reviewed.
EXPECTED_CANDIDATE_INPUTS = (
    (
        "docs/status/person_a_phase4_step4_1_registry_v2_activation_trust_v0_1/trusted_manifest_record.json",
        "person_a",
        "397ba849adc63df80912c21dd1efacb1e29b8977",
        "397ba849adc63df80912c21dd1efacb1e29b8977",
        "3a246e605437b24957951eb07b8eba048a0e58be99fa3723e99801943ba26635",
    ),
    (
        "docs/status/person_a_phase4_step4_1_registry_v2_activation_trust_v0_1/source_evidence.json",
        "person_a",
        "397ba849adc63df80912c21dd1efacb1e29b8977",
        "397ba849adc63df80912c21dd1efacb1e29b8977",
        "2df44ed46edbfa3c3ea2067408accceb4116718b51147e33ee901a48da05d4e1",
    ),
    (
        "docs/status/person_a_phase4_step4_1_frame_handoff_v0_2/source_context_manifest.json",
        "person_a",
        "397ba849adc63df80912c21dd1efacb1e29b8977",
        "380b9a392c7ad3a941dbdadcc777c61ed03e1206",
        "5200925c66d348cc95d132b30ae69e9662f47a2d7245a06d41b9f2c75e5788fd",
    ),
    (
        "docs/status/person_c_phase6_ten_pilot_expansion_acceptance_v0_1/accepted_pilot_manifest.json",
        "person_c",
        "c6bff25b5ef4f5fdb0e1ef0ce0d22e3f8b5e4960",
        "c6bff25b5ef4f5fdb0e1ef0ce0d22e3f8b5e4960",
        "7a12b8a5c5ce8b81b32bcdb044f72d5c4d9ada41af9a9402d3ac52904e494be2",
    ),
    (
        "docs/status/person_a_phase4_step4_1_registry_v2_activation_trust_v0_1/artifact_authorization_record.json",
        "person_a",
        "397ba849adc63df80912c21dd1efacb1e29b8977",
        "397ba849adc63df80912c21dd1efacb1e29b8977",
        "e69c37042dd2fa96ac707f0238f9d069a4a169ca9c9fd08bca2bba351c8e90e1",
    ),
    (
        "docs/status/person_b_phase4_step4_1_production_handoff_v0_1/production_oracle_target_manifest.json",
        "person_b",
        "8c5374d00983e6fec22f560a9fd5849e92060f3e",
        "c9a519b42cf651e05f5b4f640fda6e1a0aed3e7c",
        "afcf3afae00db6330665afc5964608c6db89eeac3767c9486d8ba0a218858282",
    ),
    (
        "docs/status/person_b_phase4_step4_1_production_handoff_v0_1/ten_pilot_frame_fold_manifest.json",
        "person_b",
        "8c5374d00983e6fec22f560a9fd5849e92060f3e",
        "c9a519b42cf651e05f5b4f640fda6e1a0aed3e7c",
        "53ca938c6ae936c3ecb6e6e8d95a3fda152f5fa130b52e7a000d297810738d71",
    ),
    (
        "src/mineocclude/probes/join.py",
        "person_b",
        "8c5374d00983e6fec22f560a9fd5849e92060f3e",
        "08a6b1ee9e6bf035b127cedf3845486d99a304c0",
        "431053b3166866dd4104ee27aafd2fb0333f8c94b64c321f2ca778dac6e96421",
    ),
    (
        "docs/status/person_b_phase4_step4_1_registry_v2_final_evidence_v0_1/trusted_manifest_record.json",
        "person_b",
        "8c5374d00983e6fec22f560a9fd5849e92060f3e",
        "8c5374d00983e6fec22f560a9fd5849e92060f3e",
        "42a53809cd2146edc567d9cf37417a55a723022a1c0be8a275669842db731ed7",
    ),
    (
        "docs/status/person_e_phase4_step4_1_registry_v2_closure_v0_1/registry_import_receipt.json",
        "person_e",
        "ab41a76ce0c855c0ac54c59c736bac7599f7e69d",
        "ab41a76ce0c855c0ac54c59c736bac7599f7e69d",
        "a68584586dc7a8fef2cbc6e1bd8fd2f0b8ce4927e78a6632446911659aca8233",
    ),
    (
        "docs/status/person_b_phase4_step4_1_final_comparison_completion_v0_1/execution_receipt.json",
        "person_b",
        "8c5374d00983e6fec22f560a9fd5849e92060f3e",
        "1b9ac2e37d245896af95a5a929774829720387db",
        "d14992316f7fac7d09313ccc938dd1a82d8655f6de8764db9f99f6f03719fcb7",
    ),
    (
        "docs/status/person_b_phase4_step4_1_final_comparison_completion_v0_1/layer_band_decision.json",
        "person_b",
        "8c5374d00983e6fec22f560a9fd5849e92060f3e",
        "1b9ac2e37d245896af95a5a929774829720387db",
        "7737b43ed13b1a7c7f3af1ebb07dbd050224e50064873b4bdbce47273e72d36c",
    ),
)

PERSON_A_SOURCE_EVIDENCE_PATH = "docs/status/person_a_phase4_step4_1_registry_v2_activation_trust_v0_1/source_evidence.json"
PERSON_A_SOURCE_EVIDENCE_COMMIT = AUTHORITY_COMMITS["person_a"]
PERSON_A_SOURCE_EVIDENCE_SHA256 = "2df44ed46edbfa3c3ea2067408accceb4116718b51147e33ee901a48da05d4e1"
PERSON_A_SOURCE_EVIDENCE_SIZE = 117_664
PERSON_A_TRUSTED_MANIFEST_PATH = "docs/status/person_a_phase4_step4_1_registry_v2_activation_trust_v0_1/trusted_manifest_record.json"
PERSON_A_TRUSTED_MANIFEST_SHA256 = "3a246e605437b24957951eb07b8eba048a0e58be99fa3723e99801943ba26635"
PERSON_A_TRUSTED_MANIFEST_SIZE = 933
PERSON_A_AUTHORIZATION_PATH = "docs/status/person_a_phase4_step4_1_registry_v2_activation_trust_v0_1/artifact_authorization_record.json"
PERSON_A_AUTHORIZATION_SHA256 = "e69c37042dd2fa96ac707f0238f9d069a4a169ca9c9fd08bca2bba351c8e90e1"
PERSON_A_AUTHORIZATION_SIZE = 1_018
PERSON_A_SOURCE_CONTEXT_PATH = "docs/status/person_a_phase4_step4_1_frame_handoff_v0_2/source_context_manifest.json"
PERSON_A_SOURCE_CONTEXT_COMMIT = "380b9a392c7ad3a941dbdadcc777c61ed03e1206"
PERSON_A_SOURCE_CONTEXT_SHA256 = "5200925c66d348cc95d132b30ae69e9662f47a2d7245a06d41b9f2c75e5788fd"
PERSON_A_SOURCE_CONTEXT_SIZE = 84_058
PERSON_B_ORACLE_PATH = "docs/status/person_b_phase4_step4_1_production_handoff_v0_1/production_oracle_target_manifest.json"
PERSON_B_ORACLE_COMMIT = "c9a519b42cf651e05f5b4f640fda6e1a0aed3e7c"
PERSON_B_ORACLE_SHA256 = "afcf3afae00db6330665afc5964608c6db89eeac3767c9486d8ba0a218858282"
PERSON_B_ORACLE_SIZE = 4_934_874
PERSON_B_FOLD_PATH = "docs/status/person_b_phase4_step4_1_production_handoff_v0_1/ten_pilot_frame_fold_manifest.json"
PERSON_B_FOLD_SHA256 = "53ca938c6ae936c3ecb6e6e8d95a3fda152f5fa130b52e7a000d297810738d71"
PERSON_B_FOLD_SIZE = 742_601

POSITIVE_CONTROL_PATH = (
    "docs/status/person_b_phase6_step6_6_positive_control_v0_1/"
    "positive_control_decision.json"
)
STEP4_PATH = (
    "docs/status/person_b_phase4_step4_1_final_comparison_completion_v0_1/"
    "layer_band_decision.json"
)
REGISTRY_VALIDATION_PATH = (
    "docs/status/person_b_phase4_step4_1_registry_v2_final_evidence_v0_1/"
    "validation_receipt.json"
)
REGISTRY_DECISION_PATH = (
    "docs/status/person_b_phase4_step4_1_registry_v2_final_evidence_v0_1/"
    "registration_decision.json"
)
REGISTRY_MANIFEST_PATH = (
    "docs/status/person_b_phase4_step4_1_registry_v2_final_evidence_v0_1/"
    "trusted_manifest_record.json"
)
POSITIVE_CONTROL_SHA256 = "742557b32326180003b1cd83ed5db6f1a1ebfebd692d969809698d323f239056"
STEP4_SHA256 = "7737b43ed13b1a7c7f3af1ebb07dbd050224e50064873b4bdbce47273e72d36c"
FINAL_COMPARISON_EXECUTION_PATH = (
    "docs/status/person_b_phase4_step4_1_final_comparison_completion_v0_1/"
    "execution_receipt.json"
)
FINAL_COMPARISON_EXECUTION_SHA256 = (
    "d14992316f7fac7d09313ccc938dd1a82d8655f6de8764db9f99f6f03719fcb7"
)
POST_STEP4_INVENTORIES = {
    "positive_control": (
        "docs/status/person_b_phase6_step6_6_positive_control_v0_1/sha256_inventory.json",
        "e0262d989f83c78019bbeb108e5e0439efd4d8929198e11f921834a955e7a509",
        776,
    ),
    "final_comparison": (
        "docs/status/person_b_phase4_step4_1_final_comparison_completion_v0_1/sha256_inventory.json",
        "2ebbd6e456f9930b79999ae0488c5546de2aa0b30f002513cdfbfa7c67fb33e3",
        798,
    ),
    "registry_v2_final_evidence": (
        "docs/status/person_b_phase4_step4_1_registry_v2_final_evidence_v0_1/sha256_inventory.json",
        "39d94b603eb6d5a254c25cd9c8c7f58130a53efc6f041c26a9164ada34f21738",
        2735,
    ),
    "person_e_registry_closure": (
        "docs/status/person_e_phase4_step4_1_registry_v2_closure_v0_1/sha256_inventory.json",
        "c65de3425a98a7dc2e9621174113508f9c0a3f4b29bc424aeb441ac7bc888d38",
        1507,
    ),
}
EXTERNAL_PERSON_B_PREDICTIONS = {
    "path": "/home/sagemaker-user/person-b-step4-1-approved-outputs/"
    "person-b-step4-1-production-v0-1/fitted_probes_and_predictions.json",
    "uri": "file:///home/sagemaker-user/person-b-step4-1-approved-outputs/"
    "person-b-step4-1-production-v0-1/fitted_probes_and_predictions.json",
    "sha256": "01e792c4d7b58bbe4ae478195b1d9523802db5674ee06ebbf5364482f42061ba",
    "size_bytes": 84_257_218,
}
PERSON_D_BASELINE_HASHES = {
    "constant_velocity_mu_oracle_blocks": "1156b6ca9bdc72355c23f8bcd2cbe9ba0324ad9e861fee47a246e5ef0a09fc7a",
    "explicit_feature_mu_oracle_blocks": "c724dc1b8918556508e4b4260315b16cf294977d51231f7c05963bc27ea973e7",
    "grouped_shuffled_log_sigma_oracle": "cc182dfa1795eba5eb59c98dfb54d1d7eda9a39e6f3188846c863d9b12142fcc",
    "grouped_shuffled_mu_oracle_blocks": "db190c7fdd99e0eb075cdf603b9e7bb516caa857d2f1167e5ecf8da84c315ba5",
    "known_q_analytic_log_sigma_oracle": "f589af2acc429460b8e9fc2725401e2adb5c0ce6424f73f3867fa43bda8ff2cd",
    "last_seen_mu_oracle_blocks": "48481740b50d41f87ac78ef7e2a4a1be930c400f197613c13212f7bfdb4bf4ae",
    "raw_pixel_mu_oracle_blocks": "bb0a15f9d2d54f53e46c6a201d464958f2f8db90decba5784e81a99ff2298420",
    "time_only_log_sigma_oracle": "aa8a60d9ee36a27655abd0a13b5aba2665aa5d865a9332c3f2a840cfbae5d273",
    "visible_history_q_log_sigma_oracle": "5ef20829a26a09d4c1407c8d398cc1429266b2b45ae233fe4679d35f57c24bbc",
}
PERSON_D_COMPLETION_SHA256 = "79c49e7c794f37c4a574dfef365b8183ddb443b246adbe94743dfdf1ff1f4cf5"
PERSON_D_ROOT = "/home/sagemaker-user/person-d-step4-1-approved-outputs/person-d-step4-1-production-v0-1"
PERSON_D_ARTIFACTS = {
    "constant_velocity__mu_oracle_blocks.json": PERSON_D_BASELINE_HASHES["constant_velocity_mu_oracle_blocks"],
    "explicit_feature__mu_oracle_blocks.json": PERSON_D_BASELINE_HASHES["explicit_feature_mu_oracle_blocks"],
    "grouped_shuffled__log_sigma_oracle.json": PERSON_D_BASELINE_HASHES["grouped_shuffled_log_sigma_oracle"],
    "grouped_shuffled__mu_oracle_blocks.json": PERSON_D_BASELINE_HASHES["grouped_shuffled_mu_oracle_blocks"],
    "known_q_analytic__log_sigma_oracle.json": PERSON_D_BASELINE_HASHES["known_q_analytic_log_sigma_oracle"],
    "last_seen__mu_oracle_blocks.json": PERSON_D_BASELINE_HASHES["last_seen_mu_oracle_blocks"],
    "raw_pixel__mu_oracle_blocks.json": PERSON_D_BASELINE_HASHES["raw_pixel_mu_oracle_blocks"],
    "time_only__log_sigma_oracle.json": PERSON_D_BASELINE_HASHES["time_only_log_sigma_oracle"],
    "visible_history_q__log_sigma_oracle.json": PERSON_D_BASELINE_HASHES["visible_history_q_log_sigma_oracle"],
}
CURRENT_MAIN_ACE = {
    "integration_manifest": (
        "docs/status/integration/ace_canonical_multilayout_closure_v0_1/integration_manifest.json",
        "be662a2a11891d3f47b4e5c142a048bcb7cd58827b2fb5e7ad591c21a1f869e2",
        2_354,
    ),
    "validation_receipt": (
        "docs/status/integration/ace_canonical_multilayout_closure_v0_1/validation_receipt.json",
        "7b3eeb0c5b9ef44fad3e0d40464b46867356fd77cc6978bee0c9909f45c3bd18",
        570,
    ),
}
CURRENT_MAIN_C6A = {
    "canonical_identity": (
        "docs/status/person_c_c6a_completion_v0_1/canonical_c6a_identity.json",
        "736d416d05cdee57653eae536c5236b6edf1047536b2ccebff897e1240341b0e",
        726,
    ),
    "completion_receipt": (
        "docs/status/person_c_c6a_completion_v0_1/c6a_completion_receipt.json",
        "5cc653f01db1363179253aeb8bdb0ad509f20e03b419f9945aa023e0ac7fbe46",
        2_472,
    ),
    "episode_inventory": (
        "docs/status/person_c_c6a_completion_v0_1/episode_inventory.json",
        "9846b705b747aa19e3abab1d08d4cbaf37546f7cfb0b163ede7ce0143875a82a",
        88_864,
    ),
    "package_manifest": (
        "docs/status/person_c_c6a_completion_v0_1/package_manifest.json",
        "612b03fea372d10c5f5b87cb581dd5f993035112e16aa1de7341801bdc35a9ef",
        2_716,
    ),
}
EXPECTED_TEST_COMMAND = (
    "python -m pytest -q tests/analysis/test_person_b_week1_closeout_v0_1.py "
    "tests/analysis/test_person_b_phase6_v2_consumer.py "
    "tests/analysis/test_person_b_phase6_v2_producer_canonicalization.py "
    "tests/analysis/test_person_b_phase6_v2_source_row_canonicalization.py "
    "tests/analysis/test_person_b_step4_1_production_v2.py "
    "tests/analysis/test_person_b_step4_1_production_fold_contract_v0_1.py "
    "tests/analysis/test_person_b_step4_1_fold_validation_interface_v0_1.py "
    "tests/analysis/test_person_b_step4_1_final_comparison_contract_v0_1.py "
    "tests/analysis/test_person_b_step4_1_final_comparison_entrypoint_v0_1.py "
    "tests/analysis/test_person_b_step4_1_final_comparison_preparation_v0_1.py "
    "tests/analysis/test_person_b_step4_1_bounded_reveal_contract_v0_1.py "
    "tests/analysis/test_person_b_canonical_positive_control.py "
    "tests/analysis/test_person_b_canonical_multilayout_positive_control.py "
    "tests/contracts/test_activation_contract.py "
    "tests/contracts/test_baseline_family_inputs_v0_2.py "
    "tests/metrics/test_person_b_metrics.py "
    "tests/probes/test_join_and_splits.py"
)
EXPECTED_CERTIFICATION_COMMAND = "python -m pytest tests/analysis/test_person_b_final_integration_readiness_v0_1.py -q"
EXPECTED_CERTIFICATION_PASSED = 24
EXPECTED_CERTIFICATION_RESULT = "24 passed"
EXPECTED_PRODUCING_SUBJECT = "Record Person B final integration readiness certification"


class FinalIntegrationReadinessValidationError(ValueError):
    """Raised for any package, provenance, or readiness invariant violation."""


# Short compatibility alias used by existing Person B validators.
CertificationValidationError = FinalIntegrationReadinessValidationError


def require(condition: bool, message: str) -> None:
    if not condition:
        raise FinalIntegrationReadinessValidationError(message)


def require_equal(actual: Any, expected: Any, name: str) -> None:
    require(actual == expected, f"{name}: expected {expected!r}, got {actual!r}")


def require_bool(actual: Any, expected: bool, name: str) -> None:
    require(type(actual) is bool, f"{name}: expected boolean")
    require_equal(actual, expected, name)


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def canonical_json_bytes(value: Any) -> bytes:
    try:
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
    except (TypeError, ValueError, UnicodeEncodeError) as error:
        raise FinalIntegrationReadinessValidationError(
            f"cannot canonicalize JSON: {error}"
        ) from error


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        require(key not in value, f"duplicate JSON key: {key!r}")
        value[key] = item
    return value


def _reject_constant(token: str) -> Any:
    raise FinalIntegrationReadinessValidationError(
        f"non-finite JSON constant: {token}"
    )


def _all_finite(value: Any) -> bool:
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, Mapping):
        return all(_all_finite(item) for item in value.values())
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return all(_all_finite(item) for item in value)
    return True


def load_strict_json(
    payload: bytes, label: str, *, canonical: bool = True
) -> dict[str, Any]:
    """Parse one UTF-8 JSON object, rejecting BOM, duplicates, and non-finite values."""

    require(not payload.startswith(b"\xef\xbb\xbf"), f"{label}: UTF-8 BOM forbidden")
    try:
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except FinalIntegrationReadinessValidationError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise FinalIntegrationReadinessValidationError(
            f"{label}: invalid JSON: {error}"
        ) from error
    require(isinstance(value, dict), f"{label}: root must be an object")
    require(_all_finite(value), f"{label}: non-finite number")
    if canonical:
        require_equal(payload, canonical_json_bytes(value), f"{label}: noncanonical JSON")
    return value


def _git_bytes(repository_root: Path, *arguments: str) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(repository_root), *arguments],
        capture_output=True,
        check=False,
    )
    if result.returncode:
        detail = result.stderr.decode("utf-8", "replace").strip()
        raise FinalIntegrationReadinessValidationError(
            f"git {' '.join(arguments)} failed: {detail or 'unknown error'}"
        )
    return result.stdout


def _git_text(repository_root: Path, *arguments: str) -> str:
    return _git_bytes(repository_root, *arguments).decode("utf-8").strip()


def _safe_repo_path(path: str) -> None:
    require(isinstance(path, str) and path, "repository path must be non-empty text")
    normalized = path.replace("\\", "/").casefold()
    require("u4" not in normalized, f"U4 artifact path forbidden: {path}")
    require("\x00" not in path and not path.startswith("/"), f"invalid repository path: {path}")
    require(".." not in Path(path).parts, f"parent repository path forbidden: {path}")


def _safe_artifact_path(path: str) -> None:
    _safe_repo_path(path)
    require("synthetic" not in path.casefold(), f"synthetic artifact path forbidden: {path}")


def _git_blob(repository_root: Path, commit: str, path: str) -> bytes:
    _safe_repo_path(path)
    require(re.fullmatch(r"[0-9a-f]{40}", commit) is not None, f"invalid commit: {commit}")
    # ``git show <commit>:<path>`` returns the exact blob bytes, unlike a
    # working-tree read; no checkout or normalization is performed.
    return _git_bytes(repository_root, "show", "--no-ext-diff", "--format=", f"{commit}:{path}")


def _git_blob_oid(repository_root: Path, commit: str, path: str) -> str:
    _safe_repo_path(path)
    require(re.fullmatch(r"[0-9a-f]{40}", commit) is not None, f"invalid commit: {commit}")
    oid = _git_text(repository_root, "rev-parse", f"{commit}:{path}")
    require(re.fullmatch(r"[0-9a-f]{40}", oid) is not None, f"invalid Git blob OID for {path}")
    return oid


def _git_blob_oid_bytes(repository_root: Path, payload: bytes) -> str:
    result = subprocess.run(
        ["git", "-C", str(repository_root), "hash-object", "--stdin"],
        input=payload,
        capture_output=True,
        check=False,
    )
    require(result.returncode == 0, "git hash-object failed")
    oid = result.stdout.decode("ascii").strip()
    require(re.fullmatch(r"[0-9a-f]{40}", oid) is not None, "invalid computed Git blob OID")
    return oid


def _require_commit(repository_root: Path, commit: str, label: str) -> None:
    require(isinstance(commit, str) and re.fullmatch(r"[0-9a-f]{40}", commit) is not None, f"{label}: invalid commit")
    require_equal(_git_text(repository_root, "cat-file", "-t", commit), "commit", f"{label} object type")


def _git_head(repository_root: Path) -> str:
    return _git_text(repository_root, "rev-parse", "HEAD")


def _is_ancestor(repository_root: Path, ancestor: str, descendant: str) -> bool:
    result = subprocess.run(
        ["git", "-C", str(repository_root), "merge-base", "--is-ancestor", ancestor, descendant],
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


def _git_direct_parent(repository_root: Path, commit: str) -> str:
    parents = _git_text(repository_root, "rev-list", "--parents", "-n", "1", commit).split()
    require(len(parents) == 2, f"commit {commit}: expected exactly one direct parent")
    require_equal(parents[0], commit, f"commit {commit} self identity")
    return parents[1]


def _schema(document: Mapping[str, Any], name: str) -> None:
    require_equal(document.get("schema_version"), SCHEMA_VERSION, f"{name} schema_version")
    schema_id = document.get("schema_id")
    require(
        isinstance(schema_id, str)
        and (schema_id == SCHEMA_ID or schema_id.startswith(f"{SCHEMA_ID}-")),
        f"{name} schema_id",
    )


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    require(isinstance(value, Mapping), f"{label}: expected object")
    return value


def _path_exists(repository_root: Path, commit: str, path: str) -> bool:
    _safe_repo_path(path)
    require(re.fullmatch(r"[0-9a-f]{40}", commit) is not None, f"invalid commit: {commit}")
    listing = _git_bytes(
        repository_root, "ls-tree", "-r", "--name-only", commit, "--", path
    ).decode("utf-8")
    return path in listing.splitlines()


def _validate_git_ancestry(repository_root: Path) -> str:
    require(repository_root.is_dir(), "repository root missing")
    _require_commit(repository_root, VERIFIED_MAIN_COMMIT, "verified main")
    _require_commit(repository_root, EVIDENCE_SNAPSHOT_COMMIT, "evidence snapshot")
    head = _git_head(repository_root)
    _require_commit(repository_root, head, "current HEAD")
    require_equal(_git_text(repository_root, "symbolic-ref", "--short", "HEAD"), BRANCH, "branch")
    require_equal(_git_text(repository_root, "rev-parse", "origin/main"), VERIFIED_MAIN_COMMIT, "origin/main")
    require(_is_ancestor(repository_root, VERIFIED_MAIN_COMMIT, head), "origin/main is not an ancestor of current HEAD")
    require(_is_ancestor(repository_root, VERIFIED_MAIN_COMMIT, EVIDENCE_SNAPSHOT_COMMIT), "origin/main is not an ancestor of evidence snapshot")
    require(_is_ancestor(repository_root, EVIDENCE_SNAPSHOT_COMMIT, head), "current HEAD is not descended from evidence snapshot")
    return head


def _validate_candidate_manifest(
    candidate_manifest: Mapping[str, Any], repository_root: Path
) -> None:
    require_equal(candidate_manifest.get("schema_version"), "0.1", "candidate manifest schema_version")
    require_equal(
        candidate_manifest.get("schema_id"),
        "mineocclude-person-b-next-phase-input-manifest-v0.1",
        "candidate manifest schema_id",
    )
    require_equal(candidate_manifest.get("consumer_role"), "person_b", "candidate consumer role")
    require_equal(candidate_manifest.get("candidate_branch"), "integration/mvp-step4-1-candidate", "candidate branch")
    require_equal(candidate_manifest.get("authority_commits"), AUTHORITY_COMMITS, "candidate authority commits")
    require_equal(candidate_manifest.get("identity_contract"), EXPECTED_IDENTITY_CONTRACT, "candidate identity contract")
    require_equal(candidate_manifest.get("accepted_identity_set"), EXPECTED_ACCEPTED_IDENTITY_SET, "candidate accepted identity set")
    external = _mapping(candidate_manifest.get("external_materialization"), "candidate external materialization")
    require_bool(external.get("required_for_computation"), True, "candidate external required")
    require_bool(external.get("repository_payload_present"), False, "candidate external repository payload")
    require_bool(external.get("bound_by_current_authority_record"), True, "candidate external authority binding")
    require_bool(external.get("blocking_missing_input"), False, "candidate external missing-input block")
    require_equal(
        external.get("active_registry_artifact_id"),
        "person_a_step4_1_activation_store_v2_combined_index_v0_1",
        "candidate external artifact id",
    )
    require_equal(external.get("active_registry_uri"), f"file://{EXTERNAL_PATH}", "candidate external URI")
    require_equal(external.get("sha256"), EXTERNAL_SHA256, "candidate external SHA-256")
    require_equal(external.get("byte_size"), EXTERNAL_SIZE, "candidate external size")

    inputs = candidate_manifest.get("inputs")
    require(isinstance(inputs, list) and len(inputs) == len(EXPECTED_CANDIDATE_INPUTS), "candidate input count")
    for index, (expected_path, expected_role, expected_authority, expected_source, expected_hash) in enumerate(
        EXPECTED_CANDIDATE_INPUTS, start=1
    ):
        row = _mapping(inputs[index - 1], f"candidate input {index}")
        require_equal(row.get("repository_relative_path"), expected_path, f"candidate input {index} path")
        require_equal(row.get("owning_role"), expected_role, f"candidate input {index} owning role")
        require_equal(row.get("owning_authority_commit"), expected_authority, f"candidate input {index} owning authority")
        require_equal(row.get("source_commit"), expected_source, f"candidate input {index} source commit")
        require_equal(row.get("sha256"), expected_hash, f"candidate input {index} SHA-256")
        require_bool(row.get("required"), True, f"candidate input {index} required")
        require_bool(row.get("frozen"), True, f"candidate input {index} frozen")
        validation = _mapping(row.get("validation"), f"candidate input {index} validation")
        require_bool(validation.get("path_exists"), True, f"candidate input {index} source path")
        require_bool(validation.get("sha256_verified"), True, f"candidate input {index} source hash")
        require_bool(validation.get("authority_blob_matches_candidate"), True, f"candidate input {index} authority blob")
        _require_commit(repository_root, expected_source, f"candidate input {index} source commit")
        blob = _git_blob(repository_root, expected_source, expected_path)
        require_equal(sha256_bytes(blob), expected_hash, f"candidate input {index} Git object hash")
    candidate_authority = _mapping(candidate_manifest.get("candidate_authority"), "candidate authority")
    require_equal(
        candidate_authority.get("binding"),
        "the commit containing this manifest",
        "candidate authority binding description",
    )
    require_equal(
        candidate_authority.get("parent_certification_commit"),
        "b285437531ebdce21cd001a6a961c2895d292c32",
        "candidate authority parent certification",
    )


def _load_authority_json(
    repository_root: Path, commit: str, path: str, expected_hash: str, label: str
) -> dict[str, Any]:
    _require_commit(repository_root, commit, f"{label} commit")
    blob = _git_blob(repository_root, commit, path)
    require_equal(sha256_bytes(blob), expected_hash, f"{label} SHA-256")
    return load_strict_json(blob, f"{commit}:{path}", canonical=False)


def _validate_identity_artifacts(repository_root: Path) -> None:
    source_evidence = _load_authority_json(
        repository_root,
        PERSON_A_SOURCE_EVIDENCE_COMMIT,
        PERSON_A_SOURCE_EVIDENCE_PATH,
        PERSON_A_SOURCE_EVIDENCE_SHA256,
        "Person A source evidence",
    )
    require_equal(source_evidence.get("accepted_pilot_count"), 10, "Person A accepted pilot count")
    require_equal(source_evidence.get("ordered_pilot_ids"), EXPECTED_TRAJECTORY_IDS, "Person A ordered pilot IDs")
    for key, expected in {
        "activation_chunk_count": 200,
        "activation_chunk_row_count": 37_480,
        "activation_row_count": 37_480,
        "unique_activation_identity_count": 37_480,
        "activation_chunk_hash_mismatch_count": 0,
        "activation_chunk_size_mismatch_count": 0,
        "activation_index_hash_mismatch_count": 0,
        "activation_index_size_mismatch_count": 0,
        "combined_activation_index_path": EXTERNAL_PATH,
        "combined_activation_index_sha256": EXTERNAL_SHA256,
        "combined_activation_index_size_bytes": EXTERNAL_SIZE,
    }.items():
        require_equal(source_evidence.get(key), expected, f"Person A source evidence {key}")
    require_bool(source_evidence.get("no_u4_derived_input"), True, "Person A source no-U4")
    require_bool(source_evidence.get("scientific_rerun_during_registration"), False, "Person A source rerun")
    completion = _mapping(source_evidence.get("completion_report"), "Person A completion report")
    for key, expected in {
        "accepted_pilot_count": 10,
        "actual_activation_row_count": 37_480,
        "expected_activation_row_count": 37_480,
        "duplicate_activation_row_count": 0,
        "missing_activation_row_count": 0,
        "nonfinite_activation_count": 0,
        "combined_activation_index_identities_unique": True,
        "source_identity_join_pass": True,
        "status": "PASS",
        "u4_output_inspected": False,
        "step6_6_complete": False,
    }.items():
        if isinstance(expected, bool):
            require_bool(completion.get(key), expected, f"Person A completion {key}")
        else:
            require_equal(completion.get(key), expected, f"Person A completion {key}")
    validation = _mapping(source_evidence.get("source_validation_receipt"), "Person A source validation receipt")
    for key, expected in {
        "accepted_pilot_count": 10,
        "activation_chunk_hash_count": 200,
        "activation_chunk_hash_failure_count": 0,
        "activation_index_hash_count": 10,
        "activation_index_hash_failure_count": 0,
        "combined_activation_index_identities_unique": True,
        "combined_activation_index_row_count": 37_480,
        "missing_activation_row_count": 0,
        "nonfinite_activation_count": 0,
        "canonical_json_pass": True,
        "inventory_pass": True,
        "pooling_audit_pass": True,
        "repeatability_audit_pass": True,
        "source_identity_join_pass": True,
        "scientific_completion_audit_pass": True,
        "status": "PASS",
        "u4_output_inspected": False,
        "step6_6_complete": False,
    }.items():
        if isinstance(expected, bool):
            require_bool(validation.get(key), expected, f"Person A validation {key}")
        else:
            require_equal(validation.get(key), expected, f"Person A validation {key}")

    trusted = _load_authority_json(
        repository_root,
        PERSON_A_SOURCE_EVIDENCE_COMMIT,
        PERSON_A_TRUSTED_MANIFEST_PATH,
        PERSON_A_TRUSTED_MANIFEST_SHA256,
        "Person A trusted manifest",
    )
    require_equal(trusted.get("decision"), "accepted", "Person A trusted decision")
    require_equal(trusted.get("owner_id"), "person_a", "Person A trusted owner")
    require_equal(trusted.get("owner_status"), "accepted", "Person A trusted owner status")
    artifact_identities = trusted.get("artifact_identities")
    require(isinstance(artifact_identities, list) and len(artifact_identities) == 1, "Person A trusted artifact identities")
    artifact = _mapping(artifact_identities[0], "Person A trusted artifact")
    require_equal(artifact.get("artifact_sha256"), EXTERNAL_SHA256, "Person A trusted artifact hash")
    require_equal(artifact.get("artifact_size_bytes"), EXTERNAL_SIZE, "Person A trusted artifact size")

    authorization = _load_authority_json(
        repository_root,
        PERSON_A_SOURCE_EVIDENCE_COMMIT,
        PERSON_A_AUTHORIZATION_PATH,
        PERSON_A_AUTHORIZATION_SHA256,
        "Person A authorization",
    )
    for key, expected in {
        "artifact_sha256": EXTERNAL_SHA256,
        "artifact_size_bytes": EXTERNAL_SIZE,
        "decision": "accepted",
        "owner_id": "person_a",
        "owner_status": "accepted",
    }.items():
        require_equal(authorization.get(key), expected, f"Person A authorization {key}")

    source_context = _load_authority_json(
        repository_root,
        PERSON_A_SOURCE_CONTEXT_COMMIT,
        PERSON_A_SOURCE_CONTEXT_PATH,
        PERSON_A_SOURCE_CONTEXT_SHA256,
        "Person A source context",
    )
    for key, expected in {
        "accepted_pilot_count": 10,
        "accepted_pilot_ids": EXPECTED_TRAJECTORY_IDS,
        "admitted_frame_count": 1_695,
        "excluded_frame_count": 179,
        "fold_manifest_sha256": PERSON_B_FOLD_SHA256,
        "source_context_artifact_count": 10,
        "source_frame_count": 1_874,
        "source_identities_verified": True,
        "target_manifest_sha256": PERSON_B_ORACLE_SHA256,
        "u4_output_inspected": False,
    }.items():
        if isinstance(expected, bool):
            require_bool(source_context.get(key), expected, f"Person A source context {key}")
        else:
            require_equal(source_context.get(key), expected, f"Person A source context {key}")
    contexts = source_context.get("source_contexts")
    require(isinstance(contexts, list) and len(contexts) == 10, "Person A source context rows")
    context_ids: set[str] = set()
    context_admitted = context_excluded = 0
    for index, row_value in enumerate(contexts, start=1):
        row = _mapping(row_value, f"Person A source context row {index}")
        trajectory_id = row.get("trajectory_id")
        require(trajectory_id in EXPECTED_TRAJECTORY_IDS and trajectory_id not in context_ids, f"Person A source context row {index} trajectory")
        context_ids.add(trajectory_id)
        require_equal(row.get("admitted_frame_count") + row.get("excluded_frame_count"), row.get("frame_count"), f"Person A source context row {index} frame accounting")
        context_admitted += row.get("admitted_frame_count")
        context_excluded += row.get("excluded_frame_count")
        lineage = _mapping(row.get("target_lineage"), f"Person A source context row {index} target lineage")
        require_equal(lineage.get("trajectory_id"), trajectory_id, f"Person A source context row {index} lineage trajectory")
        require_equal(lineage.get("source_run_id"), "runtime_pilot_session_2026_07_22", f"Person A source context row {index} lineage run")
    require_equal(context_ids, set(EXPECTED_TRAJECTORY_IDS), "Person A source context trajectory set")
    require_equal(context_admitted, 1_695, "Person A source context admitted total")
    require_equal(context_excluded, 179, "Person A source context excluded total")

    oracle = _load_authority_json(
        repository_root,
        PERSON_B_ORACLE_COMMIT,
        PERSON_B_ORACLE_PATH,
        PERSON_B_ORACLE_SHA256,
        "Person B oracle",
    )
    fold = _load_authority_json(
        repository_root,
        PERSON_B_ORACLE_COMMIT,
        PERSON_B_FOLD_PATH,
        PERSON_B_FOLD_SHA256,
        "Person B fold manifest",
    )
    require_equal(oracle.get("accepted_pilot_ids"), EXPECTED_TRAJECTORY_IDS, "oracle trajectory IDs")
    require_equal(oracle.get("join_key"), ["trajectory_id", "model_frame_idx"], "oracle join key")
    require_equal(oracle.get("row_count"), 1_695, "oracle row count")
    require_bool(oracle.get("synthetic"), False, "oracle synthetic")
    require_bool(oracle.get("u4_output_inspected"), False, "oracle U4")
    require_equal(oracle.get("scientific_use"), "permitted", "oracle scientific use")
    require_equal(oracle.get("input_manifest_hash"), fold.get("artifact_hash"), "oracle-fold artifact binding")
    require_equal(fold.get("accepted_pilot_ids"), EXPECTED_TRAJECTORY_IDS, "fold trajectory IDs")
    for key, expected in {
        "activation_chunk_count": 200,
        "activation_row_count": 37_480,
        "admitted_frame_count": 1_695,
        "excluded_frame_count": 179,
        "n_splits": 5,
        "source_frame_count": 1_874,
        "strategy": "layout_grouped",
        "random_split_used": False,
        "synthetic": False,
        "u4_output_inspected": False,
    }.items():
        if isinstance(expected, bool):
            require_bool(fold.get(key), expected, f"fold {key}")
        else:
            require_equal(fold.get(key), expected, f"fold {key}")
    fold_layout = {row.get("fold_idx"): row.get("layout_id") for row in fold.get("layout_assignments", [])}
    require_equal(fold_layout, {row["fold_idx"]: row["layout_id"] for row in EXPECTED_FOLD_TO_LAYOUT}, "fold layout assignments")
    memberships = fold.get("memberships")
    excluded = fold.get("excluded_memberships")
    rows = oracle.get("rows")
    require(isinstance(memberships, list) and len(memberships) == 1_695, "fold admitted memberships")
    require(isinstance(excluded, list) and len(excluded) == 179, "fold excluded memberships")
    require(isinstance(rows, list) and len(rows) == 1_695, "oracle rows")
    admitted_keys: set[tuple[str, int]] = set()
    membership_by_key: dict[tuple[str, int], Mapping[str, Any]] = {}
    admitted_by_fold: dict[int, int] = {}
    for index, row_value in enumerate(memberships, start=1):
        row = _mapping(row_value, f"fold membership {index}")
        key = (row.get("trajectory_id"), row.get("model_frame_idx"))
        require(key not in admitted_keys and key[0] in EXPECTED_TRAJECTORY_IDS and isinstance(key[1], int), f"fold membership {index} key")
        admitted_keys.add(key)
        membership_by_key[key] = row
        require_equal(row.get("layout_id"), key[0].split("_ep", 1)[0], f"fold membership {index} layout")
        require_equal(fold_layout.get(row.get("fold_idx")), row.get("layout_id"), f"fold membership {index} fold mapping")
        require_equal(row.get("status"), "accepted", f"fold membership {index} status")
        admitted_by_fold[row.get("fold_idx")] = admitted_by_fold.get(row.get("fold_idx"), 0) + 1
    excluded_keys: set[tuple[str, int]] = set()
    for index, row_value in enumerate(excluded, start=1):
        row = _mapping(row_value, f"fold excluded membership {index}")
        key = (row.get("trajectory_id"), row.get("model_frame_idx"))
        require(key not in excluded_keys and key not in admitted_keys and key[0] in EXPECTED_TRAJECTORY_IDS and isinstance(key[1], int), f"fold excluded membership {index} key")
        excluded_keys.add(key)
    require_equal(sum(admitted_by_fold.values()), 1_695, "fold admitted total")
    oracle_keys: set[tuple[str, int]] = set()
    oracle_by_fold: dict[int, int] = {}
    for index, row_value in enumerate(rows, start=1):
        row = _mapping(row_value, f"oracle row {index}")
        key = (row.get("trajectory_id"), row.get("model_frame_idx"))
        require(key in admitted_keys and key not in oracle_keys, f"oracle row {index} key")
        oracle_keys.add(key)
        matching = membership_by_key[key]
        require_equal(row.get("source_frame_id"), matching.get("source_frame_id"), f"oracle row {index} source frame")
        require_equal(row.get("fold_idx"), matching.get("fold_idx"), f"oracle row {index} fold")
        require_equal(row.get("layout_id"), matching.get("layout_id"), f"oracle row {index} layout")
        require_equal(row.get("status"), "accepted", f"oracle row {index} status")
        require_bool(row.get("synthetic"), False, f"oracle row {index} synthetic")
        oracle_by_fold[row.get("fold_idx")] = oracle_by_fold.get(row.get("fold_idx"), 0) + 1
    require_equal(oracle_keys, admitted_keys, "oracle-fold key set")
    require_equal(oracle_by_fold, admitted_by_fold, "oracle-fold counts")


def _validate_authority(document: Mapping[str, Any], repository_root: Path) -> None:
    _schema(document, "authority_binding")
    require_equal(document.get("branch"), BRANCH, "authority branch")
    require_equal(document.get("verified_main_commit"), VERIFIED_MAIN_COMMIT, "authority verified main")
    require_equal(document.get("verified_main_ref"), "origin/main", "authority verified main ref")
    require_equal(document.get("evidence_snapshot_commit"), EVIDENCE_SNAPSHOT_COMMIT, "authority evidence snapshot")
    require_equal(document.get("producing_parent_commit"), EVIDENCE_SNAPSHOT_COMMIT, "authority producing parent")
    require_bool(document.get("main_ancestor_of_evidence_snapshot"), True, "authority main ancestry")
    candidate = _mapping(document.get("candidate_authority"), "authority candidate")
    for name, expected in (
        ("branch", "integration/mvp-step4-1-candidate"),
        ("commit", HANDOFF_COMMIT),
        ("manifest_path", HANDOFF_PATH),
        ("manifest_sha256", HANDOFF_SHA256),
        ("manifest_size_bytes", HANDOFF_SIZE),
        ("manifest_blob_oid_sha1", HANDOFF_BLOB_OID),
    ):
        require_equal(candidate.get(name), expected, f"authority candidate {name}")
    require_bool(candidate.get("reachable_from_current_head"), False, "candidate reachability")
    roadmap = _mapping(document.get("roadmap"), "authority roadmap")
    require_equal(roadmap.get("version"), None, "manual version")
    _require_commit(repository_root, HANDOFF_COMMIT, "candidate handoff commit")
    blob = _git_blob(repository_root, HANDOFF_COMMIT, HANDOFF_PATH)
    require_equal(len(blob), HANDOFF_SIZE, "candidate handoff byte size")
    require_equal(sha256_bytes(blob), HANDOFF_SHA256, "candidate handoff SHA-256")
    require_equal(_git_text(repository_root, "rev-parse", f"{HANDOFF_COMMIT}:{HANDOFF_PATH}"), HANDOFF_BLOB_OID, "candidate handoff blob OID")
    require(not _path_exists(repository_root, _git_head(repository_root), HANDOFF_PATH), "candidate manifest unexpectedly present in current tree")
    candidate_manifest = load_strict_json(blob, f"{HANDOFF_COMMIT}:{HANDOFF_PATH}", canonical=False)
    _validate_candidate_manifest(candidate_manifest, repository_root)
    _validate_identity_artifacts(repository_root)


def _validate_roadmap(document: Mapping[str, Any], repository_root: Path) -> None:
    _schema(document, "roadmap_status")
    require_bool(document.get("all_assigned_steps_complete"), False, "roadmap completion")
    require_equal(document.get("phase_count"), 10, "roadmap phase count")
    require_equal(document.get("status"), "INCOMPLETE", "roadmap status")
    require_equal(document.get("terminal_checkpoint"), EXPECTED_TERMINAL_CHECKPOINT, "roadmap terminal checkpoint")
    closeout = _mapping(document.get("previous_closeout"), "roadmap previous closeout")
    for name, expected in EXPECTED_CLOSEOUT.items():
        require_equal(closeout.get(name), expected, f"roadmap previous closeout {name}")
    require_equal(closeout.get("validated_status"), "PASS", "roadmap previous closeout validation")
    source = _mapping(document.get("roadmap_source"), "roadmap source")
    for name, expected in EXPECTED_ROADMAP_SOURCE.items():
        require_equal(source.get(name), expected, f"roadmap source {name}")
    source_path = Path(EXPECTED_ROADMAP_SOURCE["path"])
    require(source_path.is_file(), f"roadmap source missing: {source_path}")
    source_blob = source_path.read_bytes()
    require_equal(len(source_blob), EXPECTED_ROADMAP_SOURCE["size_bytes"], "roadmap source byte size")
    require_equal(sha256_bytes(source_blob), EXPECTED_ROADMAP_SOURCE["sha256"], "roadmap source SHA-256")
    matrix_blob = _git_blob(repository_root, EVIDENCE_SNAPSHOT_COMMIT, EXPECTED_CLOSEOUT["roadmap_matrix_path"])
    require_equal(len(matrix_blob), EXPECTED_CLOSEOUT["roadmap_matrix_size_bytes"], "roadmap matrix byte size")
    require_equal(sha256_bytes(matrix_blob), EXPECTED_CLOSEOUT["roadmap_matrix_sha256"], "roadmap matrix SHA-256")
    matrix = load_strict_json(matrix_blob, f"{EVIDENCE_SNAPSHOT_COMMIT}:{EXPECTED_CLOSEOUT['roadmap_matrix_path']}", canonical=True)
    require_equal(matrix.get("roadmap_step_count"), EXPECTED_CLOSEOUT["roadmap_step_count"], "roadmap matrix step count")
    require_bool(matrix.get("roadmap_complete"), False, "roadmap matrix completion")
    receipt_blob = _git_blob(repository_root, EVIDENCE_SNAPSHOT_COMMIT, EXPECTED_CLOSEOUT["validation_receipt_path"])
    require_equal(len(receipt_blob), EXPECTED_CLOSEOUT["validation_receipt_size_bytes"], "roadmap validation receipt byte size")
    require_equal(sha256_bytes(receipt_blob), EXPECTED_CLOSEOUT["validation_receipt_sha256"], "roadmap validation receipt SHA-256")
    closeout_receipt = load_strict_json(receipt_blob, f"{EVIDENCE_SNAPSHOT_COMMIT}:{EXPECTED_CLOSEOUT['validation_receipt_path']}", canonical=True)
    require_equal(closeout_receipt.get("status"), "PASS", "roadmap closeout receipt status")
    require_equal(closeout_receipt.get("steps_validated"), EXPECTED_CLOSEOUT["roadmap_step_count"], "roadmap closeout receipt steps")
    require_bool(closeout_receipt.get("roadmap_complete"), False, "roadmap closeout receipt completion")
    reconciliation = _mapping(document.get("c6a_reconciliation"), "C6A reconciliation")
    require_bool(reconciliation.get("accepted_collection_is_complete"), True, "C6A complete")
    require_equal(reconciliation.get("completed_episode_count"), 66, "C6A episode count")
    require_equal(reconciliation.get("breakdown"), {"core": 48, "nosheep": 6, "nowall": 6, "sentinel": 6}, "C6A breakdown")
    require_equal(document.get("unresolved_assigned_scope"), EXPECTED_UNRESOLVED_ASSIGNED_SCOPE, "roadmap unresolved scope")


def _validate_main_closures(
    current_main: Mapping[str, Any], repository_root: Path
) -> None:
    require_equal(current_main.get("status"), "PARTIAL", "main ACE closure status")
    for name, (path, expected_hash, expected_size) in CURRENT_MAIN_ACE.items():
        require_equal(current_main.get(f"{name}_path"), path, f"main ACE {name} path")
        require_equal(current_main.get(f"{name}_sha256"), expected_hash, f"main ACE {name} SHA-256")
        blob = _git_blob(repository_root, VERIFIED_MAIN_COMMIT, path)
        require_equal(len(blob), expected_size, f"main ACE {name} byte size")
        require_equal(sha256_bytes(blob), expected_hash, f"main ACE {name} Git SHA-256")
        loaded = load_strict_json(blob, f"{VERIFIED_MAIN_COMMIT}:{path}", canonical=True)
        if name == "integration_manifest":
            require_equal(loaded.get("status"), "PASS", "main ACE manifest status")
            require_equal(loaded.get("ace_stop_gate_status"), "A6_6_CLOSED", "main ACE stop gate")
            require_bool(loaded.get("person_b_branch_merged"), False, "main ACE Person B merge")
            collection = _mapping(loaded.get("collection_identity"), "main ACE collection identity")
            for key, expected in {
                "trajectory_count": 5,
                "activation_row_count": 6_000,
                "activation_chunk_count": 100,
                "layout_count": 5,
                "layout_ids": ["layout_01", "layout_02", "layout_03", "layout_04", "layout_05"],
            }.items():
                require_equal(collection.get(key), expected, f"main ACE collection {key}")
        else:
            require_equal(loaded.get("status"), "PASS", "main ACE validation status")
            require_bool(loaded.get("person_b_branch_merged"), False, "main ACE validation Person B merge")
            require_equal(loaded.get("unresolved_blockers"), [], "main ACE validation blockers")


def _validate_c6a_closure(c6a: Mapping[str, Any], repository_root: Path) -> None:
    require_bool(c6a.get("immutable"), True, "Person C C6A immutable")
    require_equal(c6a.get("completed_episode_count"), 66, "Person C C6A count")
    require_equal(c6a.get("status"), "COMPLETE", "Person C C6A status")
    for name, (path, expected_hash, expected_size) in CURRENT_MAIN_C6A.items():
        require_equal(c6a.get({
            "canonical_identity": "canonical_identity_path",
            "completion_receipt": "completion_receipt_path",
            "episode_inventory": "episode_inventory_path",
            "package_manifest": "package_manifest_path",
        }[name]), path, f"Person C C6A {name} path")
        require_equal(c6a.get({
            "canonical_identity": "canonical_identity_sha256",
            "completion_receipt": "completion_receipt_sha256",
            "episode_inventory": "episode_inventory_sha256",
            "package_manifest": "package_manifest_sha256",
        }[name]), expected_hash, f"Person C C6A {name} SHA-256")
        blob = _git_blob(repository_root, VERIFIED_MAIN_COMMIT, path)
        require_equal(len(blob), expected_size, f"Person C C6A {name} byte size")
        require_equal(sha256_bytes(blob), expected_hash, f"Person C C6A {name} Git SHA-256")
        loaded = load_strict_json(blob, f"{VERIFIED_MAIN_COMMIT}:{path}", canonical=True)
        if name == "canonical_identity":
            require_equal(loaded.get("status"), "CANONICAL", "C6A canonical identity status")
            require_equal(loaded.get("canonical_c6a_id"), "person-c-c6a-post-c1-v0.1", "C6A canonical identity id")
        elif name == "completion_receipt":
            require_equal(loaded.get("status"), "PASS", "C6A completion status")
            require_equal(loaded.get("completed_episode_count"), 66, "C6A completion count")
            require_equal(loaded.get("required_episode_count"), 66, "C6A required count")
            require_bool(loaded.get("immutable"), True, "C6A completion immutable")
        elif name == "episode_inventory":
            require_equal(loaded.get("completed_episode_count"), 66, "C6A inventory count")
            require_equal(loaded.get("required_episode_count"), 66, "C6A inventory required count")
        else:
            require_equal(loaded.get("status"), "PASS", "C6A package status")
            require_equal(loaded.get("completed_episode_count"), 66, "C6A package count")
            require_equal(loaded.get("required_episode_count"), 66, "C6A package required count")
            require_bool(loaded.get("immutable"), True, "C6A package immutable")


def _validate_dependency(document: Mapping[str, Any], repository_root: Path) -> None:
    _schema(document, "dependency_status")
    blockers = document.get("unresolved_blockers")
    require_equal(blockers, EXPECTED_UNRESOLVED_BLOCKERS, "dependency blockers")
    current_main = _mapping(document.get("current_main_ace_closure"), "main ACE closure")
    _validate_main_closures(current_main, repository_root)
    a = _mapping(document.get("person_a"), "Person A status")
    require_equal(a.get("status"), "BLOCKED", "Person A status")
    external = _mapping(a.get("ten_pilot_external_activation_index"), "external activation index")
    _validate_external(external)
    b = _mapping(document.get("person_b"), "Person B status")
    require_equal(b.get("status"), "INCOMPLETE", "Person B status")
    c = _mapping(document.get("person_c"), "Person C status")
    require_equal(c.get("status"), "C6A_COMPLETE_DOWNSTREAM_UNAVAILABLE", "Person C status")
    c6a = _mapping(c.get("c6a_collection"), "Person C C6A")
    _validate_c6a_closure(c6a, repository_root)
    accepted = _mapping(c.get("current_tree_accepted_pilot_manifest"), "Person C accepted manifest")
    require_equal(accepted.get("path"), PERSON_C_ACCEPTED_PILOT_PATH, "Person C accepted manifest path")
    require_bool(accepted.get("present"), False, "Person C accepted manifest presence")
    require_equal(accepted.get("source_commit"), PERSON_C_COMMIT, "Person C accepted manifest commit")
    require_bool(accepted.get("source_git_object_verified"), True, "Person C accepted manifest object")
    require(not _path_exists(repository_root, _git_head(repository_root), PERSON_C_ACCEPTED_PILOT_PATH), "Person C accepted manifest unexpectedly present in current tree")
    c_blob = _git_blob(repository_root, PERSON_C_COMMIT, PERSON_C_ACCEPTED_PILOT_PATH)
    require_equal(sha256_bytes(c_blob), PERSON_C_ACCEPTED_PILOT_SHA256, "Person C source object hash")
    e = _mapping(document.get("person_e"), "Person E status")
    require_equal(e.get("status"), "INCOMPLETE", "Person E status")


def _validate_external(external: Mapping[str, Any]) -> None:
    require_equal(external.get("sha256"), EXTERNAL_SHA256, "external activation SHA-256")
    require_equal(external.get("byte_size"), EXTERNAL_SIZE, "external activation size")
    require_equal(external.get("path"), EXTERNAL_PATH, "external activation path")
    require_equal(external.get("uri"), f"file://{EXTERNAL_PATH}", "external activation URI")
    authority = external.get("source_authority_verified", external.get("authority_binding_verified"))
    require_bool(authority, True, "external authority")
    require_bool(external.get("local_materialized"), False, "external local materialization")
    require_bool(external.get("independently_byte_verified_in_windows_worktree"), False, "external independent byte verification")
    if "local_byte_verified" in external:
        require_bool(external.get("local_byte_verified"), False, "external local byte verification")
    require_bool(external.get("required_for_computation"), True, "external required for computation")
    require_bool(external.get("repository_payload_present"), False, "external repository payload")
    require_bool(external.get("bound_by_current_authority_record"), True, "external current authority binding")
    require_bool(external.get("blocking_missing_input"), False, "external missing-input block")


def _validate_evidence(
    document: Mapping[str, Any], repository_root: Path, head: str
) -> None:
    _schema(document, "evidence_validation")
    require_bool(document.get("positive_control_pass"), True, "positive control")
    require_equal(document.get("step4_1_decision"), "FAIL", "Step 4.1 decision")
    require_equal(document.get("frozen_step4_1_decision"), "FAIL", "frozen Step 4.1 decision")
    require_bool(document.get("synthetic_fixtures_accepted_as_science"), False, "synthetic science")
    require_bool(document.get("u4_authorized"), False, "U4 authorization")
    require_bool(document.get("u4_output_inspected"), False, "U4 inspection")
    require_equal(document.get("qualifying_layer_bands"), [], "qualifying layer bands")
    require_equal(document.get("layer_count"), 20, "layer count")
    scope = document.get("scientific_scope")
    require(isinstance(scope, str) and "synthetic" not in scope.casefold(), "synthetic scientific scope")
    artifacts = document.get("artifact_evidence")
    require(isinstance(artifacts, list) and artifacts, "artifact evidence")
    expected_paths = {POSITIVE_CONTROL_PATH, STEP4_PATH, REGISTRY_VALIDATION_PATH, REGISTRY_DECISION_PATH, REGISTRY_MANIFEST_PATH}
    observed_paths: set[str] = set()
    for item in artifacts:
        row = _mapping(item, "artifact evidence row")
        path = row.get("path")
        require(isinstance(path, str), "artifact evidence path type")
        observed_paths.add(path)
    require_equal(observed_paths, expected_paths, "artifact evidence paths")
    for index, item in enumerate(artifacts, start=1):
        row = _mapping(item, f"artifact evidence {index}")
        path = row.get("path")
        _safe_artifact_path(path)
        commit = row.get("source_commit")
        require_equal(commit, EVIDENCE_SNAPSHOT_COMMIT, f"artifact {path} source commit")
        blob = _git_blob(repository_root, commit, path)
        require_equal(len(blob), row.get("size_bytes"), f"artifact {path} byte size")
        require_equal(sha256_bytes(blob), row.get("sha256"), f"artifact {path} SHA-256")
        if path == POSITIVE_CONTROL_PATH:
            require_equal(row.get("sha256"), POSITIVE_CONTROL_SHA256, "positive control artifact hash")
            require(isinstance(row.get("decision"), str) and row["decision"].startswith("PASS"), "positive control artifact decision")
        if path == STEP4_PATH:
            require_equal(row.get("sha256"), STEP4_SHA256, "Step 4.1 artifact hash")
            require_equal(row.get("decision"), "FAIL", "Step 4.1 artifact decision")
            require_equal(row.get("qualifying_layer_bands"), [], "Step 4.1 bands")
        for key, value in row.items():
            if key.endswith("path") or key == "path":
                _safe_artifact_path(value)
    _validate_completed_outputs(document, repository_root, head)


def _validate_repo_inventory(
    repository_root: Path,
    head: str,
    descriptor: Mapping[str, Any],
    label: str,
    *,
    expected: tuple[str, str, int],
) -> dict[str, Any]:
    """Verify a repository-owned inventory and every listed file at exact HEAD bytes."""

    path = descriptor.get("path", descriptor.get("inventory_path"))
    inventory_path, inventory_sha256, inventory_size = expected
    require_equal(path, inventory_path, f"{label} inventory path")
    require_equal(descriptor.get("sha256", descriptor.get("inventory_sha256")), inventory_sha256, f"{label} inventory SHA-256")
    require_equal(descriptor.get("size_bytes", descriptor.get("inventory_size_bytes")), inventory_size, f"{label} inventory size")
    _safe_repo_path(path)
    blob = _git_blob(repository_root, head, path)
    require_equal(len(blob), inventory_size, f"{label} HEAD inventory size")
    require_equal(sha256_bytes(blob), inventory_sha256, f"{label} HEAD inventory SHA-256")
    inventory = load_strict_json(blob, f"HEAD:{path}", canonical=True)
    if "inventory_excludes_self" in inventory:
        require_bool(inventory.get("inventory_excludes_self"), True, f"{label} inventory self exclusion")
    files = inventory.get("files")
    require(isinstance(files, (Mapping, list)), f"{label} inventory files")
    entries: list[tuple[str, str, int | None]] = []
    if isinstance(files, Mapping):
        for name, value in files.items():
            require(isinstance(name, str) and name, f"{label} inventory file name")
            require(isinstance(value, str), f"{label} inventory {name} hash")
            entries.append((name, value, None))
    else:
        for index, value in enumerate(files, start=1):
            row = _mapping(value, f"{label} inventory file {index}")
            entries.append((row.get("path"), row.get("sha256"), row.get("byte_size")))
    if "file_count" in inventory:
        require_equal(inventory.get("file_count"), len(entries), f"{label} inventory file count")
    parent = str(Path(path).parent).replace("\\", "/")
    for name, expected_hash, expected_size in entries:
        require(isinstance(expected_hash, str) and re.fullmatch(r"[0-9a-f]{64}", expected_hash) is not None, f"{label} inventory hash")
        require(isinstance(name, str) and name and not Path(name).is_absolute(), f"{label} inventory relative path")
        listed_path = f"{parent}/{name}" if parent != "." else name
        _safe_artifact_path(listed_path)
        listed_blob = _git_blob(repository_root, head, listed_path)
        require_equal(sha256_bytes(listed_blob), expected_hash, f"{label} listed file {name} SHA-256")
        if expected_size is not None:
            require_equal(len(listed_blob), expected_size, f"{label} listed file {name} size")
    return inventory


def _validate_completed_outputs(
    document: Mapping[str, Any], repository_root: Path, head: str
) -> None:
    outputs = _mapping(document.get("completed_post_step4_1_outputs"), "completed post-Step-4.1 outputs")
    require_equal(outputs.get("evidence_scope"), "completed ten-pilot evidence only; not full-66 completion", "post-Step-4.1 evidence scope")
    positive = _mapping(outputs.get("positive_control"), "post-Step-4.1 positive control")
    _validate_repo_inventory(repository_root, head, _mapping(positive.get("inventory"), "positive control inventory"), "positive control", expected=POST_STEP4_INVENTORIES["positive_control"])
    final_comparison = _mapping(outputs.get("final_comparison"), "post-Step-4.1 final comparison")
    require_equal(final_comparison.get("decision"), "FAIL", "post-Step-4.1 final comparison decision")
    final_inventory = _mapping(final_comparison.get("inventory"), "final comparison inventory")
    _validate_repo_inventory(repository_root, head, final_inventory, "final comparison", expected=POST_STEP4_INVENTORIES["final_comparison"])
    registry = _mapping(outputs.get("registry_v2_final_evidence"), "Registry v2 final evidence")
    require_equal(registry.get("status"), "PASS", "Registry v2 final evidence status")
    require_equal(registry.get("acceptance_decision"), "FAIL", "Registry v2 final evidence decision")
    _validate_repo_inventory(repository_root, head, registry, "Registry v2 final evidence", expected=POST_STEP4_INVENTORIES["registry_v2_final_evidence"])
    predictions = _mapping(outputs.get("fitted_probes_oof_predictions"), "external B predictions")
    for name, expected in EXTERNAL_PERSON_B_PREDICTIONS.items():
        require_equal(predictions.get(name), expected, f"external B predictions {name}")
    require_bool(predictions.get("immutable"), True, "external B predictions immutable")
    require_bool(predictions.get("later_evidence_only"), True, "external B predictions later-evidence-only")
    baselines = _mapping(outputs.get("person_d_baselines"), "Person D baselines")
    require_equal(baselines.get("root"), PERSON_D_ROOT, "Person D baseline root")
    require_equal(baselines.get("completion_manifest_sha256"), PERSON_D_COMPLETION_SHA256, "Person D completion manifest")
    require_equal(baselines.get("sha256"), PERSON_D_BASELINE_HASHES, "Person D nine baseline hashes")
    artifacts = baselines.get("artifacts")
    require(isinstance(artifacts, list) and len(artifacts) == 9, "Person D baseline artifact count")
    seen_artifacts: set[str] = set()
    for index, item in enumerate(artifacts, start=1):
        row = _mapping(item, f"Person D baseline artifact {index}")
        filename = row.get("filename")
        require(isinstance(filename, str), f"Person D baseline artifact {index} filename type")
        require(filename in PERSON_D_ARTIFACTS and filename not in seen_artifacts, f"Person D baseline artifact {index} filename")
        seen_artifacts.add(filename)
        require_equal(row.get("path"), f"{PERSON_D_ROOT}/{filename}", f"Person D baseline artifact {filename} path")
        require_equal(row.get("sha256"), PERSON_D_ARTIFACTS[filename], f"Person D baseline artifact {filename} hash")
    require_equal(seen_artifacts, set(PERSON_D_ARTIFACTS), "Person D baseline artifact filenames")
    completion = _mapping(baselines.get("completion_manifest"), "Person D completion manifest")
    require_equal(completion.get("filename"), "completion_manifest.json", "Person D completion filename")
    require_equal(completion.get("path"), f"{PERSON_D_ROOT}/completion_manifest.json", "Person D completion path")
    require_equal(completion.get("sha256"), PERSON_D_COMPLETION_SHA256, "Person D completion hash")
    closure = _mapping(outputs.get("person_e_registry_closure"), "Person E registry closure")
    _validate_repo_inventory(repository_root, head, _mapping(closure.get("inventory"), "Person E closure inventory"), "Person E registry closure", expected=POST_STEP4_INVENTORIES["person_e_registry_closure"])
    receipt = _mapping(closure.get("receipt"), "Person E closure receipt")
    for name, expected in (("artifact_count", 15), ("rejection_count", 0), ("status", "PASS"), ("strict_validator_accepted", True), ("path", "docs/status/person_e_phase4_step4_1_registry_v2_closure_v0_1/registry_import_receipt.json"), ("sha256", "a68584586dc7a8fef2cbc6e1bd8fd2f0b8ce4927e78a6632446911659aca8233"), ("size_bytes", 2819)):
        if isinstance(expected, bool):
            require_bool(receipt.get(name), expected, f"Person E closure receipt {name}")
        else:
            require_equal(receipt.get(name), expected, f"Person E closure receipt {name}")
    execution_blob = _git_blob(repository_root, head, FINAL_COMPARISON_EXECUTION_PATH)
    require_equal(sha256_bytes(execution_blob), FINAL_COMPARISON_EXECUTION_SHA256, "final comparison execution receipt SHA-256")
    execution = load_strict_json(execution_blob, f"HEAD:{FINAL_COMPARISON_EXECUTION_PATH}", canonical=True)
    direct = _mapping(execution.get("direct_input_sha256s"), "final comparison direct inputs")
    require_equal(direct.get("person_b_predictions"), predictions.get("sha256"), "external B hash versus final comparison receipt")
    require_equal(direct.get("person_d_completion_manifest"), baselines.get("completion_manifest_sha256"), "Person D completion hash versus final comparison receipt")
    for name, value in PERSON_D_BASELINE_HASHES.items():
        require_equal(direct.get(f"person_d_{name}"), value, f"Person D {name} versus final comparison receipt")
    require_equal(direct.get("positive_control_decision"), POSITIVE_CONTROL_SHA256, "positive control hash versus final comparison receipt")


def _validate_handoff(
    document: Mapping[str, Any], repository_root: Path, raw: Mapping[str, bytes]
) -> None:
    _schema(document, "final_integration_handoff")
    for name, expected in EXPECTED_COUNTS.items():
        require_equal(document.get(name), expected, f"handoff {name}")
    require_bool(document.get("all_assigned_steps_complete"), False, "handoff completion")
    require_equal(document.get("branch"), BRANCH, "handoff branch")
    require_equal(document.get("candidate_authority_commit"), HANDOFF_COMMIT, "handoff candidate commit")
    require_equal(document.get("evidence_snapshot_commit"), EVIDENCE_SNAPSHOT_COMMIT, "handoff evidence snapshot")
    require_equal(document.get("verified_main_commit"), VERIFIED_MAIN_COMMIT, "handoff verified main")
    require_bool(document.get("main_ancestor_of_branch"), True, "handoff main ancestry")
    require_equal(document.get("input_hash_count"), 12, "handoff input count")
    require_equal(document.get("input_hash_mismatch_count"), 0, "handoff input mismatches")
    require_equal(document.get("frozen_step4_1_decision"), "FAIL", "handoff frozen Step 4.1")
    require_equal(document.get("integration_decision"), "NOT_INTEGRATION_READY", "handoff integration decision")
    candidate = _mapping(document.get("candidate_manifest"), "handoff candidate manifest")
    for name, expected in (("path", HANDOFF_PATH), ("sha256", HANDOFF_SHA256), ("size_bytes", HANDOFF_SIZE), ("blob_oid_sha1", HANDOFF_BLOB_OID)):
        require_equal(candidate.get(name), expected, f"handoff candidate {name}")
    require_bool(candidate.get("source_commit_reachable_from_current_head"), False, "handoff candidate reachability")
    external = _mapping(document.get("external_activation_index"), "handoff external activation")
    _validate_external(external)
    candidate_blob = _git_blob(repository_root, HANDOFF_COMMIT, HANDOFF_PATH)
    candidate_manifest = load_strict_json(
        candidate_blob, f"{HANDOFF_COMMIT}:{HANDOFF_PATH}", canonical=False
    )
    require_equal(candidate_manifest.get("PERSON_B_NEXT_PHASE_HANDOFF_READY"), True, "candidate handoff ready")
    candidate_inputs = candidate_manifest.get("inputs")
    require(isinstance(candidate_inputs, list) and len(candidate_inputs) == 12, "candidate handoff inputs")
    candidate_by_path = {
        row.get("repository_relative_path"): row
        for row in candidate_inputs
        if isinstance(row, Mapping)
    }
    require_equal(len(candidate_by_path), 12, "candidate handoff unique inputs")
    rows = document.get("repository_inputs")
    require(isinstance(rows, list) and len(rows) == 12, "handoff repository inputs")
    mismatches = 0
    seen: set[str] = set()
    for index, item in enumerate(rows, start=1):
        row = _mapping(item, f"handoff input {index}")
        path = row.get("repository_relative_path")
        _safe_repo_path(path)
        require(path not in seen, f"duplicate handoff input path: {path}")
        seen.add(path)
        expected = _mapping(candidate_by_path.get(path), f"candidate input {path}")
        require_equal(row.get("source_commit"), expected.get("source_commit"), f"handoff input {index} source commit authority")
        require_equal(row.get("sha256"), expected.get("sha256"), f"handoff input {index} SHA-256 authority")
        require_equal(row.get("logical_input_name"), expected.get("logical_input_name"), f"handoff input {index} logical name")
        commit = row.get("source_commit")
        _require_commit(repository_root, commit, f"handoff input {index} source commit")
        blob = _git_blob(repository_root, commit, path)
        actual_hash = sha256_bytes(blob)
        actual_size = len(blob)
        if actual_hash != row.get("sha256") or actual_size != row.get("byte_size"):
            mismatches += 1
        require_equal(actual_hash, row.get("sha256"), f"handoff input {index} source SHA-256")
        require_equal(actual_size, row.get("byte_size"), f"handoff input {index} source byte size")
        require_bool(row.get("source_git_object_verified"), True, f"handoff input {index} Git verification")
        expected_present = _path_exists(repository_root, _git_head(repository_root), path)
        require_bool(row.get("current_tree_path_present"), expected_present, f"handoff input {index} current-tree presence")
    require_equal(mismatches, 0, "handoff computed input mismatch count")
    chain = _mapping(document.get("package_hash_chain"), "handoff package hash chain")
    require_equal(set(chain), set(HASH_CHAIN_INPUTS), "handoff package hash chain keys")
    for name in HASH_CHAIN_INPUTS:
        require_equal(chain.get(name), sha256_bytes(raw[name]), f"handoff package hash {name}")


def _validate_receipt(document: Mapping[str, Any], raw: Mapping[str, bytes]) -> None:
    _schema(document, "integration_readiness_receipt")
    require_equal(document.get("decision"), "NOT_INTEGRATION_READY", "receipt decision")
    require_equal(document.get("branch"), BRANCH, "receipt branch")
    require_equal(document.get("verified_main_commit"), VERIFIED_MAIN_COMMIT, "receipt verified main")
    require_bool(document.get("all_assigned_steps_complete"), False, "receipt completion")
    for name in (
        "trajectory_count",
        "admitted_sample_count",
        "activation_row_count",
        "activation_chunk_count",
    ):
        require_equal(document.get(name), EXPECTED_COUNTS[name], f"receipt {name}")
    require_equal(document.get("candidate_input_hash_count"), 12, "receipt candidate input count")
    require_equal(document.get("candidate_input_hash_mismatch_count"), 0, "receipt candidate input mismatches")
    require_equal(document.get("frozen_step4_1_decision"), "FAIL", "receipt frozen Step 4.1")
    require_bool(document.get("main_ancestor_of_branch"), True, "receipt main ancestry")
    require_bool(document.get("inventory_verified"), True, "receipt inventory")
    require_bool(document.get("package_canonical"), True, "receipt canonical")
    require_bool(document.get("scientific_execution_performed_by_validator"), False, "receipt scientific execution")
    require_bool(document.get("u4_authorized"), False, "receipt U4 authorization")
    require_bool(document.get("u4_output_inspected"), False, "receipt U4 inspection")
    require_equal(document.get("external_activation_index_sha256"), EXTERNAL_SHA256, "receipt external hash")
    handoff_name = "final_integration_handoff.json"
    require_equal(document.get("final_handoff_path"), f"{PACKAGE_DIRECTORY}/{handoff_name}", "receipt handoff path")
    require_equal(document.get("final_handoff_sha256"), sha256_bytes(raw[handoff_name]), "receipt handoff hash")
    tests = document.get("focused_test_evidence")
    require(isinstance(tests, list) and len(tests) == 1, "receipt focused test evidence")
    row = _mapping(tests[0], "receipt focused test")
    require_equal(row.get("command"), EXPECTED_TEST_COMMAND, "receipt focused test command")
    require_equal(row.get("passed"), 222, "receipt focused test passed count")
    require_equal(row.get("skipped"), 2, "receipt focused test skipped count")
    require_equal(row.get("result"), "222 passed, 2 skipped", "receipt focused test result")
    require_equal(row.get("status"), "PASS", "receipt focused test status")
    certification = _mapping(document.get("certification_test"), "receipt certification test")
    require_equal(certification.get("command"), EXPECTED_CERTIFICATION_COMMAND, "receipt certification command")
    require_equal(certification.get("status"), "PASS", "receipt certification status")
    require_equal(certification.get("passed"), EXPECTED_CERTIFICATION_PASSED, "receipt certification passed count")
    require_equal(certification.get("result"), EXPECTED_CERTIFICATION_RESULT, "receipt certification result")


def _validate_producing_binding(
    document: Mapping[str, Any], repository_root: Path, package_root: Path
) -> None:
    _schema(document, "producing_commit_binding")
    require_equal(document.get("expected_direct_parent_commit"), EVIDENCE_SNAPSHOT_COMMIT, "producing binding expected parent")
    require_equal(document.get("expected_subject"), EXPECTED_PRODUCING_SUBJECT, "producing binding expected subject")
    require_equal(document.get("stable_paths"), list(STABLE_CERTIFICATION_PATHS), "producing binding stable paths")
    mode = document.get("mode")
    require(mode in {"PENDING_POST_COMMIT", "BOUND"}, "producing binding mode")
    producing_commit = document.get("producing_commit")
    if mode == "PENDING_POST_COMMIT":
        require(producing_commit is None, "pending producing binding must not name a commit")
        require_equal(_git_head(repository_root), EVIDENCE_SNAPSHOT_COMMIT, "pending producing binding HEAD")
        require_equal(
            document.get("self_reference_explanation"),
            "The producing commit cannot be embedded in its own tree; this pending binding is accepted only before the first certification commit.",
            "pending producing binding explanation",
        )
        return
    require(isinstance(producing_commit, str) and re.fullmatch(r"[0-9a-f]{40}", producing_commit) is not None, "bound producing commit")
    _require_commit(repository_root, producing_commit, "bound producing commit")
    require_equal(_git_direct_parent(repository_root, producing_commit), EVIDENCE_SNAPSHOT_COMMIT, "bound producing direct parent")
    require_equal(_git_text(repository_root, "show", "-s", "--format=%s", producing_commit), EXPECTED_PRODUCING_SUBJECT, "bound producing subject")
    require(_is_ancestor(repository_root, producing_commit, _git_head(repository_root)), "bound producing commit is not an ancestor of HEAD")
    for stable_path in STABLE_CERTIFICATION_PATHS:
        if stable_path in INVENTORIED_FILES:
            working_path = package_root / stable_path
            git_path = f"{PACKAGE_DIRECTORY}/{stable_path}"
        else:
            working_path = repository_root / stable_path
            git_path = stable_path
        require(working_path.is_file(), f"stable certification path missing: {stable_path}")
        current_blob = working_path.read_bytes()
        producing_blob = _git_blob(repository_root, producing_commit, git_path)
        require_equal(producing_blob, current_blob, f"stable certification bytes {stable_path}")
        require_equal(_git_blob_oid(repository_root, producing_commit, git_path), _git_blob_oid_bytes(repository_root, current_blob), f"stable certification blob identity {stable_path}")


def _validate_inventory(package_root: Path, raw: Mapping[str, bytes]) -> None:
    inventory = load_strict_json(raw["sha256_inventory.json"], "sha256_inventory.json", canonical=True)
    _schema(inventory, "sha256_inventory")
    require_bool(inventory.get("inventory_excludes_self"), True, "inventory self exclusion")
    require_equal(inventory.get("file_count"), len(INVENTORIED_FILES), "inventory file count")
    files = _mapping(inventory.get("files"), "inventory files")
    require_equal(set(files), set(INVENTORIED_FILES), "inventory file names")
    for name in INVENTORIED_FILES:
        row = _mapping(files.get(name), f"inventory {name}")
        require_equal(row.get("byte_size"), len(raw[name]), f"inventory {name} byte size")
        require_equal(row.get("sha256"), sha256_bytes(raw[name]), f"inventory {name} SHA-256")


def validate_package(repository_root: Path, package_root: Path | None = None) -> dict[str, Any]:
    """Validate an existing package without changing any bytes on disk."""

    repository_root = Path(repository_root).resolve()
    package_root = (Path(package_root) if package_root is not None else repository_root / PACKAGE_DIRECTORY).resolve()
    _validate_git_ancestry(repository_root)
    require(package_root.is_dir(), f"package root missing: {package_root}")
    entries = list(package_root.iterdir())
    require(all(entry.is_file() and not entry.is_symlink() for entry in entries), "package contains non-file entry")
    require_equal({entry.name for entry in entries}, set(PACKAGE_FILES), "package file set")
    raw = {name: (package_root / name).read_bytes() for name in PACKAGE_FILES}
    documents = {
        name: load_strict_json(raw[name], str(package_root / name), canonical=True)
        for name in PACKAGE_FILES
    }
    _validate_authority(documents["authority_binding.json"], repository_root)
    _validate_roadmap(documents["roadmap_status.json"], repository_root)
    _validate_dependency(documents["dependency_status.json"], repository_root)
    _validate_evidence(documents["evidence_validation.json"], repository_root, _git_head(repository_root))
    _validate_handoff(
        documents["final_integration_handoff.json"], repository_root, raw
    )
    _validate_producing_binding(
        documents[PRODUCING_BINDING_FILE], repository_root, package_root
    )
    _validate_inventory(package_root, raw)
    _validate_receipt(documents["integration_readiness_receipt.json"], raw)
    return {
        "status": "PASS",
        "validator_status": "PASS",
        "integration_decision": "NOT_INTEGRATION_READY",
        "schema_id": SCHEMA_ID,
        "schema_version": SCHEMA_VERSION,
        "branch": BRANCH,
        "verified_main_commit": VERIFIED_MAIN_COMMIT,
        "evidence_snapshot_commit": EVIDENCE_SNAPSHOT_COMMIT,
        "input_hash_count": 12,
        "input_hash_mismatch_count": 0,
        "trajectory_count": EXPECTED_COUNTS["trajectory_count"],
        "admitted_sample_count": EXPECTED_COUNTS["admitted_sample_count"],
        "exclusion_count": EXPECTED_COUNTS["exclusion_count"],
        "activation_row_count": EXPECTED_COUNTS["activation_row_count"],
        "activation_chunk_count": EXPECTED_COUNTS["activation_chunk_count"],
        "fold_count": EXPECTED_COUNTS["fold_count"],
        "frozen_step4_1_decision": "FAIL",
        "all_assigned_steps_complete": False,
        "u4_output_inspected": False,
        "scientific_execution_performed": False,
        "validation_mode": "read-only",
    }


def validate(repository_root: Path, *, package_root: Path | None = None) -> dict[str, Any]:
    """Compatibility alias matching existing Person B validators."""

    return validate_package(repository_root, package_root=package_root)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", nargs="?", choices=("validate-package",), default="validate-package")
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--package-root", type=Path)
    parser.add_argument("--json", action="store_true", help="emit JSON summary")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = validate_package(args.repository_root, package_root=args.package_root)
    except (FinalIntegrationReadinessValidationError, OSError, UnicodeError) as error:
        print(f"PERSON_B_FINAL_INTEGRATION_READINESS_VALIDATION=FAIL: {error}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print("PERSON_B_FINAL_INTEGRATION_READINESS_VALIDATION=PASS")
        print(f"INTEGRATION_DECISION={result['integration_decision']}")
    return 0


__all__ = [
    "AUTHORITY_COMMITS",
    "EVIDENCE_SNAPSHOT_COMMIT",
    "EXPECTED_COUNTS",
    "HANDOFF_COMMIT",
    "HANDOFF_PATH",
    "INVENTORIED_FILES",
    "PACKAGE_DIRECTORY",
    "PACKAGE_FILES",
    "SCHEMA_ID",
    "SCHEMA_VERSION",
    "CertificationValidationError",
    "FinalIntegrationReadinessValidationError",
    "canonical_json_bytes",
    "load_strict_json",
    "main",
    "sha256_bytes",
    "validate",
    "validate_package",
]


if __name__ == "__main__":
    raise SystemExit(main())
