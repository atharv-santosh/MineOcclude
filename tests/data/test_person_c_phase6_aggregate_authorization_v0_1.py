"""Focused checks for Person C's Phase 6 aggregate runtime authorization."""
import json
import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import build_person_c_phase6_aggregate_authorization_v0_1 as mod


PKG = os.path.join(ROOT, mod.PKG_REL)


def load(name):
    with open(os.path.join(PKG, name), encoding="utf-8") as handle:
        return json.load(handle)


def test_authorization_names_the_exact_run_id_and_is_affirmative():
    decision = load("authorization_decision.json")
    assert decision["run_id"] == "mineocclude-run-ea6169430d693f8adcd16a23a62c4422"
    assert decision["role"] == "person_c_data"
    assert decision["person_a_phase6_authorized"] is True
    assert decision["person_c_phase6_signoff"] is True
    assert decision["signed_for_this_run_id"] is True
    assert decision["person_c_blocker_present"] is False
    assert decision["blocker"] is None
    assert decision["run_id_scope"] == "single_exact_run_id_only"
    assert decision["reauthorization_required_for_any_other_run_id"] is True


def test_authorization_does_not_claim_aggregate_completion():
    decision = load("authorization_decision.json")
    assert decision["aggregate_authorization_complete"] is False


def test_step_4_1_fail_and_scoped_false_flags_are_preserved():
    preserved = load("preserved_frozen_evidence.json")
    assert preserved["step_4_1_status"] == "FAIL"
    assert preserved["step_4_1_status_preserved"] is True
    assert preserved["historical_evidence_rewritten"] is False
    assert preserved["frozen_decision_modified"] is False
    assert preserved["additive_only"] is True
    assert {row["field"] for row in preserved["scoped_false_flags_left_unchanged"]} == {
        "person_a_phase6_authorized",
        "person_a_expansion_execution_authorized",
    }
    for row in preserved["scoped_false_flags_left_unchanged"]:
        assert row["value"] is False


def test_frozen_scoped_decisions_are_still_false_on_disk():
    """The pilot and expansion tracks must not have been flipped by this work."""
    with open(
        os.path.join(
            ROOT,
            "docs/status/person_c_phase4_step4_1_registry_v2_handoff_v0_1",
            "selected_pilot_acceptance.json",
        ),
        encoding="utf-8",
    ) as handle:
        assert json.load(handle)["person_a_phase6_authorized"] is False
    with open(
        os.path.join(
            ROOT,
            "docs/status/person_c_phase6_ten_pilot_expansion_acceptance_v0_1",
            "expansion_acceptance_decision.json",
        ),
        encoding="utf-8",
    ) as handle:
        assert json.load(handle)["person_a_expansion_execution_authorized"] is False


def test_bound_person_c_inputs_and_person_a_records_verify():
    binding = load("authority_binding.json")
    assert binding["person_c_authority_commit"] == mod.PERSON_C_AUTHORITY_COMMIT
    assert set(binding["person_c_bound_inputs"]) == set(mod.PERSON_C_BOUND_INPUTS)
    for relative, row in binding["person_c_bound_inputs"].items():
        assert row["sha256"] == mod.PERSON_C_BOUND_INPUTS[relative]
    assert binding["person_a"]["commit"] == mod.PERSON_A_REQUEST_COMMIT
    assert binding["person_a"]["source_read_policy"] == "exact_git_commit_object"
    assert binding["foreign_branch_merged"] is False
    assert binding["foreign_branch_modified"] is False

    state = binding["person_a_verified_state"]
    assert state["transferred_payload_count"] == mod.EXPECTED_FRAME_KEY_COUNT
    assert state["transfer_hash_mismatch_count"] == 0
    assert state["transfer_missing_count"] == 0
    assert state["person_c_owned_contract_conditions_all_satisfied"] is True
    assert state["extraction_not_started_at_decision_time"] is True

    scope = binding["person_c_verified_scope"]
    assert scope["accepted_trajectory_count"] == mod.EXPECTED_TRAJECTORY_COUNT
    assert scope["canonical_frame_count"] == mod.EXPECTED_FRAME_KEY_COUNT
    assert scope["visibility_frame_key_count"] == mod.EXPECTED_FRAME_KEY_COUNT


def test_scope_withholds_output_acceptance_and_u4():
    scope = load("scope_and_limitations.json")
    limits = scope["carried_forward_scientific_limitations"]
    assert limits["CURRENT_66_CELL_U4_REVEAL_ELIGIBLE"] is False
    assert limits["U4_SUPPLEMENTAL_CAPTURE_REQUIRED"] is True
    assert limits["hidden_state_interpretation_authorized"] is False
    assert limits["u4_output_inspected"] is False
    joined = " ".join(scope["not_authorized_by_this_document"])
    assert "Registry v2 acceptance" in joined
    assert "U4 output inspection" in joined


def test_person_c_performed_no_execution():
    receipt = load("validation_receipt.json")
    assert receipt["status"] == "PASS"
    assert receipt["activation_extraction_performed_by_person_c"] is False
    assert receipt["model_loaded_by_person_c"] is False
    assert receipt["scientific_execution_performed"] is False
    assert receipt["u4_output_inspected"] is False
    assert receipt["historical_evidence_rewritten"] is False
    assert receipt["step_4_1_status_preserved_as_fail"] is True
    assert receipt["person_c_owned_contract_condition_failures"] == 0


def test_package_is_byte_reproducible_and_inventory_is_complete():
    mod.validate(PKG)
    inventory = load("sha256_inventory.json")
    assert inventory["inventory_excludes_self"] is True
    assert "sha256_inventory.json" not in inventory["files"]
    assert inventory["file_count"] == len(inventory["files"]) + 1
    assert set(inventory["files"]) == {
        name for name in os.listdir(PKG) if name != "sha256_inventory.json"
    }
