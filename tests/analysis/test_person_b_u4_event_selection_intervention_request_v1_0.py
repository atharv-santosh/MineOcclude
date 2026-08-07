"""Focused tests for the fail-closed Person B U4 request preparation."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from mineocclude.analysis.u4_event_selection_intervention_request_v1_0 import (
    DECISION_BLOCKED,
    INVENTORIED_PACKAGE_FILES,
    PACKAGE_DIRECTORY,
    U4EventRequestError,
    validate_documents,
    validate_package,
)

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / PACKAGE_DIRECTORY


def _documents() -> tuple[dict[str, dict], dict[str, object]]:
    documents = {
        name: json.loads((PACKAGE / name).read_text(encoding="utf-8"))
        for name in INVENTORIED_PACKAGE_FILES
    }
    inventory = json.loads(
        (PACKAGE / "sha256_inventory.json").read_text(encoding="utf-8")
    )
    return documents, inventory


def _assert_rejected(documents: dict[str, dict], inventory: dict[str, object]) -> None:
    with pytest.raises(U4EventRequestError):
        validate_documents(documents, inventory, repository_root=ROOT)


def test_current_package_validates_without_scientific_execution() -> None:
    result = validate_package(PACKAGE, ROOT)
    assert result["validated"] is True
    assert result["decision"] == DECISION_BLOCKED
    assert result["selected_event_count"] == 0
    assert result["required_event_count"] == 5
    assert result["selection_ready_for_c8_2"] is False
    assert result["scientific_execution_performed"] is False
    assert result["u4_output_inspected"] is False


def test_event_ids_cannot_be_frozen_without_direction_authority() -> None:
    documents, inventory = _documents()
    documents["event_selection_decision.json"]["selected_event_ids"] = [
        "invented:event:0"
    ]
    _assert_rejected(documents, inventory)


def test_direction_identity_must_remain_unresolved() -> None:
    documents, inventory = _documents()
    documents["intervention_request.json"]["direction_id"] = "invented-direction"
    _assert_rejected(documents, inventory)


def test_doses_must_remain_unresolved() -> None:
    documents, inventory = _documents()
    documents["intervention_request.json"]["dose_table"] = [
        {
            "alpha_applied": 1.0,
            "alpha_requested": 1.0,
            "cap_reduced": False,
            "dose_id": "invented-dose",
            "intended_block_shift": 1.0,
        }
    ]
    _assert_rejected(documents, inventory)


def test_missing_producer_must_be_person_b() -> None:
    documents, inventory = _documents()
    documents["intervention_request.json"]["missing_producer"] = "person_c"
    _assert_rejected(documents, inventory)


def test_c8_2_cannot_be_marked_ready() -> None:
    documents, inventory = _documents()
    documents["validation_receipt.json"]["selection_ready_for_c8_2"] = True
    _assert_rejected(documents, inventory)


def test_required_input_placeholders_are_rejected() -> None:
    documents, inventory = _documents()
    documents["missing_inputs.json"]["required_inputs"][0]["placeholder_created"] = True
    _assert_rejected(documents, inventory)


def test_wrong_c_authority_is_rejected() -> None:
    documents, inventory = _documents()
    documents["authority_binding.json"]["person_c_source_commit"] = "0" * 40
    _assert_rejected(documents, inventory)


def test_malformed_historical_selection_hash_is_rejected() -> None:
    documents, inventory = _documents()
    documents["event_selection_decision.json"]["source_selection_sha256"] = (
        "603972fe36b24925dfa3ea5b655a4285a86375bbe9ee0ac976c75f3c3d59369"
    )
    _assert_rejected(documents, inventory)


def test_person_d_required_field_contract_is_rejected_when_changed() -> None:
    documents, inventory = _documents()
    documents["authority_binding.json"]["person_d_dependency"]["required_fields"] = []
    _assert_rejected(documents, inventory)


def test_wrong_inventory_digest_is_rejected() -> None:
    documents, inventory = _documents()
    changed = copy.deepcopy(inventory)
    changed["files"][0]["sha256"] = "0" * 64
    _assert_rejected(documents, changed)


def test_request_contract_version_is_explicit() -> None:
    documents, inventory = _documents()
    assert documents["intervention_request.json"]["schema_version"] == (
        "person-b-intervention-request-v1.0"
    )
    documents["intervention_request.json"]["schema_version"] = (
        "person-b-intervention-request-v2.0"
    )
    _assert_rejected(documents, inventory)
