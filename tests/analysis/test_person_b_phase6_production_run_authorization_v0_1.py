"""Focused validation for Person B's Phase-6 production-run authorization.

These tests check the published decision against the frozen authorities it
rests on, and they include negative cases so that a pass means something: a
renamed run identity, a reopened Step 4.1, a silently widened scope, a drifted
Person A contract, or a post-signature edit to a bound authority must all be
rejected.

Scope is deliberately narrow. Nothing here re-runs Person B science.
"""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_DIRECTORY = (
    "docs/status/person_b_phase6_production_run_authorization_v0_1"
)
PACKAGE = REPOSITORY_ROOT / PACKAGE_DIRECTORY
VALIDATOR_PATH = (
    REPOSITORY_ROOT
    / "scripts"
    / "validate_person_b_phase6_production_run_authorization_v0_1.py"
)

RUN_ID = "mineocclude-run-ea6169430d693f8adcd16a23a62c4422"
PERSON_A_COMMIT = "ecdf3178154e594b06d1d4326993754068cae039"
PHASE6_CONDITIONS = (
    "docs/status/person_b_phase4_step4_1_registry_v2_handoff_v0_1/"
    "phase6_authorization_conditions.json"
)
B_TO_A_HANDOFF = (
    "docs/status/person_b_66_cell_oracle_target_v0_1/"
    "b_to_a_successor_handoff.json"
)


def _load_validator():
    spec = importlib.util.spec_from_file_location(
        "person_b_phase6_production_run_authorization_validator", VALIDATOR_PATH
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def validator():
    return _load_validator()


@pytest.fixture(scope="module")
def decision() -> dict:
    return json.loads((PACKAGE / "authorization_decision.json").read_bytes())


@pytest.fixture(scope="module")
def binding() -> dict:
    return json.loads((PACKAGE / "authority_binding.json").read_bytes())


@pytest.fixture(scope="module")
def preconditions() -> dict:
    return json.loads((PACKAGE / "precondition_verification.json").read_bytes())


@pytest.fixture(scope="module")
def handoff() -> dict:
    return json.loads((REPOSITORY_ROOT / B_TO_A_HANDOFF).read_bytes())


# ---------------------------------------------------------------------------
# End-to-end
# ---------------------------------------------------------------------------
def test_published_package_validates(validator):
    result = validator.validate()
    assert result["status"] == "PASS"
    assert result["authorized"] is True
    assert result["run_id"] == RUN_ID


def test_package_contains_the_expected_documents():
    names = {path.name for path in PACKAGE.iterdir()}
    assert names == {
        "authorization_decision.json",
        "authority_binding.json",
        "precondition_verification.json",
        "validation_receipt.json",
        "sha256_inventory.json",
    }


# ---------------------------------------------------------------------------
# The decision says what it must say
# ---------------------------------------------------------------------------
def test_decision_names_the_exact_run_id(decision):
    assert decision["run_id"] == RUN_ID
    assert decision["authorization_scope"]["authorized_run_id"] == RUN_ID
    assert decision["signed_for_this_run_id"] is True


def test_role_phase6_signoff_is_affirmative(decision):
    assert decision["authorized"] is True
    assert decision["person_a_phase6_authorized"] is True
    assert decision["person_b_phase6_authorization"] is True
    assert decision["person_b_phase6_signoff"] is True
    assert decision["phase6_authorized"] is True
    assert decision["decision_status"] == "AUTHORIZED"
    assert decision["decision_owner"] == "person_b_analysis"


def test_superseded_run_identity_stays_unauthorized(decision):
    superseded = decision["superseded_run_id_not_authorized"]
    assert superseded != RUN_ID
    assert superseded == "mineocclude-run-836009cb74647b413ebc6f40218bc5bf"


# ---------------------------------------------------------------------------
# Frozen history is preserved
# ---------------------------------------------------------------------------
def test_step_4_1_remains_fail(decision):
    assert decision["frozen_step_4_1_decision"] == "FAIL"
    assert decision["frozen_step_4_1_decision_unchanged"] is True
    assert decision["historical_evidence_rewritten"] is False


def test_frozen_oracle_manifest_still_records_step_4_1_fail():
    oracle = json.loads(
        (
            REPOSITORY_ROOT
            / "docs/status/person_b_66_cell_oracle_target_v0_1"
            / "oracle_target_manifest.json"
        ).read_bytes()
    )
    assert oracle["frozen_step_4_1_decision"] == "FAIL"


def test_governing_conditions_file_was_not_edited(decision):
    """Superseding one field must not rewrite the frozen document."""

    conditions = json.loads((REPOSITORY_ROOT / PHASE6_CONDITIONS).read_bytes())
    assert conditions["person_a_phase6_authorized"] is False
    assert conditions["silent_authorization_forbidden"] is True
    assert decision["supersedes_field"]["path"] == PHASE6_CONDITIONS
    assert decision["supersedes_field"]["previous_value"] is False


def test_u4_remains_unauthorized_and_uninspected(decision):
    assert decision["u4_authorized"] is False
    assert decision["u4_output_inspected"] is False

    u4 = json.loads(
        (
            REPOSITORY_ROOT
            / "docs/status/person_b_66_cell_oracle_target_v0_1"
            / "u4_status.json"
        ).read_bytes()
    )
    assert u4["u4_executed"] is False
    assert u4["u4_outcomes_inspected"] is False


def test_no_peer_branch_was_merged(decision, binding):
    assert decision["foreign_branch_merged"] is False
    assert binding["foreign_branch_merged"] is False


# ---------------------------------------------------------------------------
# The authorization is narrow
# ---------------------------------------------------------------------------
def test_scope_withholds_output_acceptance_and_downstream_claims(decision):
    withheld = " ".join(decision["authorization_scope"]["not_authorized"]).lower()
    for phrase in (
        "acceptance",
        "u4",
        "step 4.1",
        "integration readiness",
        "hidden-state",
    ):
        assert phrase in withheld


def test_person_b_does_not_declare_the_aggregate_authorization(decision):
    assert decision["aggregate_phase6_runtime_authorized"] is False
    assert decision["aggregate_authorization_is_not_person_b_to_declare"] is True
    assert decision["self_authorization_by_person_a_forbidden"] is True


def test_person_b_claims_no_scientific_execution(decision):
    assert decision["scientific_execution_performed_by_person_b"] is False


# ---------------------------------------------------------------------------
# The authorized universe matches Person B's own frozen extraction contract
# ---------------------------------------------------------------------------
def test_authorized_universe_matches_frozen_handoff(decision, handoff):
    scope = decision["authorization_scope"]["extraction_universe"]
    policy = handoff["extraction_row_policy"]
    required = handoff["required_activation_index_fields"]["required_values"]

    assert scope["model_frame_key_count"] == policy["model_frame_key_count"] == 2468
    assert scope["trajectory_count"] == policy["trajectory_count"] == 66
    assert scope["layer_count"] == required["layer_count"] == 20
    assert scope["expected_activation_row_count"] == required["activation_row_count"]
    assert scope["expected_activation_row_count"] == 49_360
    assert scope["extract_full_model_frame_universe"] is True


def test_expected_row_count_is_the_product_of_keys_and_layers(handoff):
    required = handoff["required_activation_index_fields"]["required_values"]
    policy = handoff["extraction_row_policy"]
    assert (
        policy["model_frame_key_count"] * required["layer_count"]
        == required["activation_row_count"]
    )


def test_every_governing_precondition_is_resolved(preconditions):
    conditions = json.loads((REPOSITORY_ROOT / PHASE6_CONDITIONS).read_bytes())
    declared = conditions["additional_prerequisites_for_a_new_versioned_decision"]
    assert len(preconditions["conditions"]) == len(declared)
    assert all(entry["satisfied"] for entry in preconditions["conditions"])
    assert preconditions["all_conditions_satisfied"] is True


def test_extraction_had_not_started_at_the_bound_evidence(preconditions):
    state = preconditions["person_a_runtime_state"]
    assert state["extraction_started"] is False
    assert state["transfer_pass"] is True
    assert state["payloads_valid"] == state["payloads_expected"] == 2468
    assert state["missing"] == 0
    assert state["duplicate_output_paths"] == 0
    assert state["hash_mismatches"] == 0
    assert state["size_mismatches"] == 0


def test_person_a_evidence_is_bound_by_commit_and_hash(validator, binding):
    assert binding["person_a_commit"] == PERSON_A_COMMIT
    assert binding["person_a_evidence"]
    for record in binding["person_a_evidence"]:
        payload = validator.read_foreign_blob(PERSON_A_COMMIT, record["path"])
        assert validator.sha256_bytes(payload) == record["sha256"]


# ---------------------------------------------------------------------------
# Negative cases: the validator must reject drift
# ---------------------------------------------------------------------------
def test_renamed_run_id_is_rejected(validator, decision):
    tampered = copy.deepcopy(decision)
    tampered["run_id"] = "mineocclude-run-0000000000000000000000000000000"
    with pytest.raises(validator.AuthorizationValidationError):
        validator.validate_run_identity(tampered)


def test_reopened_step_4_1_is_rejected(validator, decision):
    tampered = copy.deepcopy(decision)
    tampered["frozen_step_4_1_decision"] = "PASS"
    with pytest.raises(validator.AuthorizationValidationError):
        validator.validate_frozen_history_preserved(tampered)


def test_authorizing_u4_is_rejected(validator, decision):
    tampered = copy.deepcopy(decision)
    tampered["u4_authorized"] = True
    with pytest.raises(validator.AuthorizationValidationError):
        validator.validate_frozen_history_preserved(tampered)


def test_claiming_the_aggregate_authorization_is_rejected(validator, decision):
    tampered = copy.deepcopy(decision)
    tampered["aggregate_phase6_runtime_authorized"] = True
    with pytest.raises(validator.AuthorizationValidationError):
        validator.validate_scope_is_narrow(tampered)


def test_silently_widened_scope_is_rejected(validator, decision):
    tampered = copy.deepcopy(decision)
    tampered["authorization_scope"]["not_authorized"] = [
        "nothing in particular",
    ]
    with pytest.raises(validator.AuthorizationValidationError):
        validator.validate_scope_is_narrow(tampered)


def test_edited_governing_conditions_are_rejected(validator, decision):
    tampered = copy.deepcopy(decision)
    tampered["supersedes_field"]["sha256"] = "0" * 64
    with pytest.raises(validator.AuthorizationValidationError):
        validator.validate_frozen_history_preserved(tampered)


def test_post_signature_edit_to_a_bound_authority_is_rejected(validator, binding):
    tampered = copy.deepcopy(binding)
    tampered["person_b_frozen_authorities"][0]["sha256"] = "0" * 64
    with pytest.raises(validator.AuthorizationValidationError):
        validator.validate_authority_binding(tampered)


def test_unsatisfied_precondition_is_rejected(validator, preconditions):
    tampered = copy.deepcopy(preconditions)
    tampered["conditions"][0]["satisfied"] = False
    with pytest.raises(validator.AuthorizationValidationError):
        validator.validate_preconditions_against_evidence(tampered)


def test_dropped_precondition_is_rejected(validator, preconditions):
    tampered = copy.deepcopy(preconditions)
    tampered["conditions"] = tampered["conditions"][:-1]
    with pytest.raises(validator.AuthorizationValidationError):
        validator.validate_preconditions_against_evidence(tampered)


def test_oracle_package_drift_is_rejected(validator, preconditions):
    tampered = copy.deepcopy(preconditions)
    tampered["oracle_package_inventory_mismatches"] = ["some/frozen/file.json"]
    with pytest.raises(validator.AuthorizationValidationError):
        validator.validate_preconditions_against_evidence(tampered)
