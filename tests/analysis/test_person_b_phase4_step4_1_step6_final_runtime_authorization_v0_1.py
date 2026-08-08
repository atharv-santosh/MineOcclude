"""Focused fail-closed tests for Person B's final Step 6 authorization."""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import validate_person_b_phase4_step4_1_step6_final_runtime_authorization_v0_1 as mod

PACKAGE_ROOT = ROOT / mod.PACKAGE_RELATIVE_PATH


def _documents() -> dict[str, dict]:
    return {
        name: json.loads((PACKAGE_ROOT / name).read_text(encoding="utf-8"))
        for name in mod.DOCUMENT_NAMES
    }


def _assert_rejected(documents: dict[str, dict], code: str) -> None:
    with pytest.raises(mod.FinalRuntimeAuthorizationError, match=code):
        mod.validate_decision_documents(documents)


def test_full_exact_remote_authorization_and_c_registry_trust_chain_pass() -> None:
    result = mod.validate_package(ROOT, PACKAGE_ROOT)
    assert result == {
        "a_acknowledgement_verified": True,
        "c_signoff_verified": True,
        "person_a_runtime_execution_authorized": True,
        "production_execution_started": False,
        "registry_v2_future_a_output_acceptance_authorized": False,
        "selected_pilot_hash_verified": True,
        "selected_trajectory_id": "layout_00_ep9403",
        "u4_output_inspected": False,
    }


def test_wrong_a_acknowledgement_binding_fails_closed() -> None:
    documents = copy.deepcopy(_documents())
    documents["authority_binding.json"]["bound_authorities"][
        "person_a_acknowledgement"
    ]["commit"] = "0" * 40
    _assert_rejected(documents, "authority_binding_mismatch")


def test_wrong_c_signoff_binding_fails_closed() -> None:
    documents = copy.deepcopy(_documents())
    documents["authority_binding.json"]["bound_authorities"][
        "person_c_accepted_pilot"
    ]["commit"] = "0" * 40
    _assert_rejected(documents, "authority_binding_mismatch")


def test_second_pilot_authorization_fails_closed() -> None:
    documents = copy.deepcopy(_documents())
    documents["combined_runtime_authorization.json"]["authorization_scope"][
        "authorized_pilot_count"
    ] = 2
    _assert_rejected(documents, "runtime_scope_mismatch")


def test_wrong_selected_pilot_hash_fails_closed() -> None:
    documents = copy.deepcopy(_documents())
    documents["selected_pilot_validation.json"]["selected_capture_package"][
        "git_object_sha256"
    ] = "0" * 64
    _assert_rejected(documents, "selected_pilot_identity_mismatch")


def test_runtime_not_explicitly_authorized_fails_closed() -> None:
    documents = copy.deepcopy(_documents())
    documents["combined_runtime_authorization.json"][
        "person_a_runtime_execution"
    ]["authorized"] = False
    _assert_rejected(documents, "runtime_authorization_mismatch")


def test_wrong_runtime_step_range_fails_closed() -> None:
    documents = copy.deepcopy(_documents())
    documents["combined_runtime_authorization.json"]["authorization_scope"][
        "authorized_steps"
    ].append("6.7")
    _assert_rejected(documents, "runtime_scope_mismatch")


def test_missing_c_scientific_use_fails_closed() -> None:
    documents = copy.deepcopy(_documents())
    documents["combined_runtime_authorization.json"]["person_c_scientific_use"][
        "accepted"
    ] = False
    _assert_rejected(documents, "scientific_use_mismatch")


def test_future_a_output_acceptance_fails_closed() -> None:
    documents = copy.deepcopy(_documents())
    documents["authorization_boundaries.json"][
        "future_person_a_output_acceptance"
    ]["accepted"] = True
    _assert_rejected(documents, "future_output_acceptance_mismatch")


def test_missing_future_registry_byte_requirement_fails_closed() -> None:
    documents = copy.deepcopy(_documents())
    requirements = documents["authorization_boundaries.json"][
        "future_person_a_output_acceptance"
    ]["required_post_execution_evidence"]
    requirements.remove("exact_activation_bytes_and_sha256")
    _assert_rejected(documents, "future_output_acceptance_mismatch")


@pytest.mark.parametrize(
    "boundary",
    [
        "additional_pilots_authorized",
        "hidden_state_interpretation_authorized",
        "project_integration_authorized",
        "step_4_1_closure_authorized",
    ],
)
def test_positive_control_restrictions_fail_closed(boundary: str) -> None:
    documents = copy.deepcopy(_documents())
    documents["authorization_boundaries.json"]["positive_control_boundary"][
        boundary
    ] = True
    _assert_rejected(documents, "authorization_boundary_mismatch")


def test_production_execution_started_claim_fails_closed() -> None:
    documents = copy.deepcopy(_documents())
    documents["combined_runtime_authorization.json"][
        "production_execution_started"
    ] = True
    _assert_rejected(documents, "authorization_boundary_mismatch")


def test_u4_inspection_claim_fails_closed() -> None:
    documents = copy.deepcopy(_documents())
    documents["authorization_boundaries.json"]["u4_output_inspected"] = True
    _assert_rejected(documents, "authorization_boundary_mismatch")


def test_noncanonical_json_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "noncanonical.json"
    path.write_text('{"schema_version": "1.0"}', encoding="utf-8")
    with pytest.raises(mod.FinalRuntimeAuthorizationError, match="noncanonical_json"):
        mod._load_document(path)


def test_inventory_matches_every_decision_document() -> None:
    documents = _documents()
    raw = {
        name: (PACKAGE_ROOT / name).read_bytes() for name in mod.DOCUMENT_NAMES
    }
    mod._validate_inventory(documents, raw, mod.DOCUMENT_NAMES)
