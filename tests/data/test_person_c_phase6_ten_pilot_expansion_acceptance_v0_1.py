"""Preparation-only checks for the Phase 6 ten-pilot C acceptance."""
import json
import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import build_person_c_phase6_ten_pilot_expansion_acceptance_v0_1 as mod


PKG = os.path.join(ROOT, mod.PKG_REL)


def load(name):
    with open(os.path.join(PKG, name), encoding="utf-8") as handle:
        return json.load(handle)


def test_exact_b_order_and_counts_are_preserved():
    manifest = load("accepted_pilot_manifest.json")
    assert manifest["ordered_pilot_ids"] == mod.EXPECTED_ORDER
    assert [row["trajectory_id"] for row in manifest["intake_rows"]] == mod.EXPECTED_ORDER
    assert manifest["accepted_pilot_count"] == 10
    assert manifest["newly_accepted_pilot_count"] == 9
    assert manifest["accepted_placeholder_count"] == 0


def test_all_captures_and_referenced_artifacts_are_strictly_verified():
    manifest = load("accepted_pilot_manifest.json")
    required = {
        "media",
        "raw_actions",
        "normalized_actions",
        "server_state",
        "frame_map",
        "visibility",
        "config",
        "seed_noise",
        "seed_noise_source",
    }
    for row in manifest["intake_rows"]:
        assert row["strict_capture_validator_accepted"] is True
        assert required - {"config", "seed_noise_source"} <= set(row["verified_artifacts"])
        assert required <= set(row["sealed_declared_artifacts"])
        assert isinstance(row["seed"], int)


def test_exact_five_no_wall_controls_are_accepted():
    decision = load("expansion_acceptance_decision.json")
    assert decision["no_wall_control_pilot_ids"] == mod.EXPECTED_CONTROLS
    rows = load("accepted_pilot_manifest.json")["intake_rows"]
    assert [row["trajectory_id"] for row in rows if row["control"]] == mod.EXPECTED_CONTROLS


def test_existing_pilot_decision_is_bound_not_duplicated():
    binding = load("existing_pilot_acceptance_binding.json")
    assert binding["trajectory_id"] == mod.EXISTING_PILOT
    assert binding["decision_duplicated"] is False
    registry = load("registry_v2_document.json")["immutable_registry_document"]
    assert mod.EXISTING_PILOT not in {row["artifact_id"] for row in registry["artifacts"]}


def test_complete_registry_v2_chain_covers_all_nine_new_inputs():
    registry = load("registry_v2_document.json")["immutable_registry_document"]
    expected = set(mod.EXPECTED_ORDER[1:])
    assert {row["artifact_id"] for row in registry["artifacts"]} == expected
    assert {row["artifact_id"] for row in registry["byte_verifications"]} == expected
    assert len(registry["owner_authorities"]) == 9
    assert len(registry["manifests"]) == 9
    assert len(registry["runs"]) == 9
    trusted = load("registry_v2_trusted_verification_inputs.json")
    assert trusted["verifier"]["result"] == "ACCEPTED_ZERO_REJECTIONS"
    assert len(trusted["artifact_bytes_sources"]) == 9


def test_person_a_execution_and_hidden_interpretation_remain_unauthorized():
    decision = load("expansion_acceptance_decision.json")
    assert decision["person_a_expansion_execution_authorized"] is False
    assert decision["hidden_state_interpretation_authorized"] is False
    assert decision["step_6_6_complete"] is False
    assert decision["u4_output_inspected"] is False


def test_generated_package_is_byte_deterministic():
    mod.validate(PKG)
