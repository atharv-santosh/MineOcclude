"""Focused tests for the Person E Phase 6 aggregate-authorization package."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from mineocclude.experiments.registry import formatted_json_bytes
from scripts.build_person_e_phase6_aggregate_authorization_v0_1 import (
    EXPECTED_ACTIVATION_ROWS,
    EXPECTED_LAYER_COUNT,
    EXPECTED_PAYLOAD_COUNT,
    PERSON_A_TRANSPORT_COMMIT,
    PERSON_E_EMPIRICAL_VISIBILITY_COMMIT,
    RUN_ID,
    build_documents,
)

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "docs/status/person_e_phase6_aggregate_authorization_v0_1"


def _read(name: str) -> dict:
    return json.loads((PACKAGE / name).read_text(encoding="utf-8"))


def test_package_files_exist() -> None:
    for name in (
        "authority_binding.json",
        "identity_cross_check.json",
        "phase6_authorization_decision.json",
        "sha256_inventory.json",
        "validation_receipt.json",
    ):
        assert (PACKAGE / name).is_file(), name


def test_decision_names_the_exact_run_id_and_signs_off() -> None:
    decision = _read("phase6_authorization_decision.json")
    assert decision["run_id"] == RUN_ID == (
        "mineocclude-run-ea6169430d693f8adcd16a23a62c4422"
    )
    assert decision["role"] == "person_e_operations"
    assert decision["person_a_phase6_authorized"] is True
    assert decision["phase6_authorized"] is True
    assert decision["person_e_operations_signoff"] is True
    assert decision["signed_for_this_run_id"] is True
    assert decision["blocker"] is None


def test_decision_does_not_sign_for_other_roles() -> None:
    decision = _read("phase6_authorization_decision.json")
    assert decision["aggregate_authorization_complete"] is False
    assert decision["remaining_required_signers"] == [
        "person_b_analysis",
        "person_c_data",
    ]
    assert decision["self_authorization_forbidden"] is True
    assert decision["silent_authorization_forbidden"] is True


def test_authorized_scope_matches_verified_input_state() -> None:
    scope = _read("phase6_authorization_decision.json")["authorized_scope"]
    assert scope["expected_payload_count"] == EXPECTED_PAYLOAD_COUNT == 2468
    assert scope["expected_layer_count"] == EXPECTED_LAYER_COUNT == 20
    assert scope["expected_activation_rows"] == EXPECTED_ACTIVATION_ROWS == 49_360
    assert scope["expected_payload_count"] * scope["expected_layer_count"] == (
        scope["expected_activation_rows"]
    )
    assert scope["stored_activation_dtype"] == "float32"


def test_identity_cross_check_is_exact_with_zero_mismatches() -> None:
    cross_check = _read("identity_cross_check.json")
    assert cross_check["status"] == "PASS"
    assert cross_check["identity_sets_exactly_equal"] is True
    assert cross_check["person_a_identity_count"] == EXPECTED_PAYLOAD_COUNT
    assert cross_check["person_e_identity_count"] == EXPECTED_PAYLOAD_COUNT
    assert cross_check["person_a_only_identity_count"] == 0
    assert cross_check["person_e_only_identity_count"] == 0
    assert cross_check["raw_source_sha256_mismatches"] == 0
    assert cross_check["canonical_rgb_pixel_sha256_mismatches"] == 0
    assert cross_check["raw_source_sha256_matches"] == EXPECTED_PAYLOAD_COUNT
    assert cross_check["canonical_rgb_pixel_sha256_matches"] == EXPECTED_PAYLOAD_COUNT


def test_frozen_person_e_state_is_preserved_including_step4_1_fail() -> None:
    frozen = _read("authority_binding.json")["frozen_state_preserved"]
    assert frozen["hidden_state_interpretation_authorized"] is False
    assert frozen["phase6_artifacts_immutable"] is True
    assert frozen["phase6_reexecution_required"] is False
    assert frozen["step4_1_contract_complete"] is False
    assert frozen["step4_1_scientific_execution_performed"] is False
    assert frozen["u4_output_inspected"] is False
    assert "FAIL" in frozen["step4_1_decision_vocabulary_preserved"]
    assert frozen["ten_pilot_accepted_pilot_count"] == 10
    assert frozen["ten_pilot_accepted_activation_row_count"] == 37_480
    assert frozen["ten_pilot_accepted_activation_chunk_count"] == 200


def test_step4_1_frozen_records_still_carry_fail_vocabulary() -> None:
    contract = json.loads(
        (
            ROOT
            / "docs/status/person_e_phase4_step4_1_final_comparison_ratification_v0_1"
            / "closure_contract.json"
        ).read_text(encoding="utf-8")
    )
    assert "FAIL" in contract["acceptance_contract"]["status_vocabulary"]


def test_authority_binding_pins_both_sides() -> None:
    binding = _read("authority_binding.json")
    assert binding["run_id"] == RUN_ID
    assert binding["person_a_transport_verification_commit"] == (
        PERSON_A_TRANSPORT_COMMIT
    )
    assert binding["person_e_empirical_visibility_commit"] == (
        PERSON_E_EMPIRICAL_VISIBILITY_COMMIT
    )
    assert binding["historical_evidence_rewritten"] is False
    for artifact in binding["person_a_artifacts"].values():
        assert len(artifact["sha256"]) == 64
        assert artifact["byte_size"] > 0


def test_retention_and_conditions_are_carried_forward() -> None:
    decision = _read("phase6_authorization_decision.json")
    retained = {item["path"] for item in decision["retention_requirements"]}
    assert "/home/sagemaker-user/person-a-phase6-approved-outputs" in retained
    assert "/home/sagemaker-user/person-a-phase6-approved-inputs" in retained
    condition_ids = {item["condition_id"] for item in decision["authorization_conditions"]}
    assert "distinct_scope_from_frozen_ten_pilot_set" in condition_ids
    assert "write_only_to_the_approved_fresh_destination" in condition_ids
    assert "extraction_only_no_interpretation" in condition_ids
    assert "step4_1_untouched" in condition_ids


def test_validation_receipt_records_a_non_executing_focused_run() -> None:
    receipt = _read("validation_receipt.json")
    assert receipt["status"] == "PASS"
    assert receipt["run_id"] == RUN_ID
    assert receipt["additive_only"] is True
    assert receipt["focused_validation_only"] is True
    assert receipt["scientific_execution_performed"] is False
    assert receipt["hidden_state_interpretation_performed"] is False
    assert receipt["u4_output_inspected"] is False
    assert receipt["step4_1_records_modified"] is False
    assert receipt["frozen_evidence_preserved"] is True
    assert receipt["foreign_branch_merged"] is False


def test_inventory_matches_published_bytes() -> None:
    inventory = _read("sha256_inventory.json")
    assert inventory["inventory_excludes_self"] is True
    assert "sha256_inventory.json" not in inventory["files"]
    assert inventory["file_count"] == len(inventory["files"])
    for name, entry in inventory["files"].items():
        payload = (PACKAGE / name).read_bytes()
        assert len(payload) == entry["byte_size"], name
        assert hashlib.sha256(payload).hexdigest() == entry["sha256"], name


def test_package_rebuilds_byte_identically() -> None:
    for name, document in build_documents().items():
        assert formatted_json_bytes(document) == (PACKAGE / name).read_bytes(), name


@pytest.mark.parametrize(
    "name",
    ["authority_binding.json", "phase6_authorization_decision.json"],
)
def test_run_id_is_named_explicitly_in_key_documents(name: str) -> None:
    assert RUN_ID in (PACKAGE / name).read_text(encoding="utf-8")
