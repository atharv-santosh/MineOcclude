"""Focused tests for the additive provenance-audited Person D reauthorization."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scripts import validate_person_b_step4_1_memory_reauthorization_v0_1 as validator

ROOT = Path(__file__).resolve().parents[2]
PACKAGE_RELATIVE = Path(
    "docs/status/person_b_phase4_step4_1_provenance_reauthorization_v0_2"
)
PACKAGE = ROOT / PACKAGE_RELATIVE


def _documents() -> dict[str, dict]:
    return {
        path.name: json.loads(path.read_text(encoding="utf-8"))
        for path in PACKAGE.glob("*.json")
    }


def test_authorization_record_binds_exact_supersession_validator_and_runner() -> None:
    record = _documents()["person_d_authorization_record.json"]
    validator._validate_external_auth(ROOT, record)
    assert record["supersedes_authorization_commit"] == (
        validator.PERSON_B_PROVENANCE_STARTING_AUTHORITY
    )
    assert record["provenance_audit_validator_commit"] == (
        "d7b710d6fbc9f8ecba5075788d4149f6f62b100c"
    )
    assert record["provenance_audit_validator_commit"] == (
        validator._provenance_validator_commit(ROOT)
    )
    assert record["authorized_runner_commit"] == validator.PERSON_D_RUNNER_COMMIT
    assert record["authorized_branch"] == validator.PERSON_D_BRANCH


def test_authorization_record_requires_corrected_receipt_lifecycle() -> None:
    record = _documents()["person_d_authorization_record.json"]
    assert record["direct_output_validation_required"] is True
    assert record["provenance_receipt_is_audit_output"] is True
    assert record["atomic_receipt_generation_required"] is True
    assert record["existing_receipt_revalidation_required"] is True
    assert "preserved_output_decisions" not in record
    assert tuple(record["preserved_reusable_families"]) == (
        validator.PRESERVED_COMPLETED_FAMILIES
    )


@pytest.mark.parametrize(
    ("field", "value", "match"),
    [
        ("provenance_audit_validator_commit", "0" * 40, "validator authority"),
        ("authorized_runner_commit", "0" * 40, "runner lineage"),
        ("supersedes_authorization_commit", "0" * 40, "supersession"),
        ("direct_output_validation_required", False, "audit lifecycle"),
    ],
)
def test_authorization_record_rejects_authority_or_lifecycle_drift(
    field: str, value: object, match: str
) -> None:
    record = copy.deepcopy(_documents()["person_d_authorization_record.json"])
    record[field] = value
    with pytest.raises(validator.MemoryReauthorizationError, match=match):
        validator._validate_external_auth(ROOT, record)


def test_exact_command_orders_all_gates_before_person_d_resume() -> None:
    commands = _documents()["production_commands.json"]
    chain = commands["authorized_production_chain"]
    reuse_index = chain.index(" reuse-validate ")
    preflight_index = chain.index(" runtime-preflight ")
    run_index = chain.index(
        " scripts/run_person_d_step4_1_eight_family_production.py run "
    )
    assert reuse_index < preflight_index < run_index
    assert "--verify-payloads" in chain
    assert "--resume resume" in chain
    assert commands["authorization_record_path"] in chain
    assert validator.MATERIALIZED_ROOT_ABSOLUTE_PATH in chain
    assert validator.FRAME_ROOT_ABSOLUTE_PATH in chain
    assert validator.OUTPUT_ROOT_ABSOLUTE_PATH in chain
    assert "--d-checkout" in commands["receipt_audit_command"]
    assert "--authorization-record-path" in commands["receipt_audit_command"]
    assert "no family is hard-coded absent" in commands[
        "runtime_absent_family_selection"
    ]


def test_runtime_sequence_places_direct_audit_before_receipt_and_d() -> None:
    sequence = _documents()["production_commands.json"]["runtime_sequence"]
    assert len(sequence) == 6
    assert "materialized-input validation" in sequence[0]
    assert "memory preflight" in sequence[2]
    assert "without a provenance-receipt prerequisite" in sequence[3]
    assert "atomic Person B provenance-receipt generation" in sequence[4]
    assert "Person D producing run" in sequence[5]


def test_provenance_contract_defines_canonical_atomic_person_b_receipt() -> None:
    contract = _documents()["provenance_audit_contract.json"]
    assert contract["first_audit_receipt_prerequisite"] is False
    assert contract["receipt_schema_id"] == validator.PRESERVED_PROVENANCE_SCHEMA_ID
    assert contract["receipt_filename"] == validator.PRESERVED_PROVENANCE_FILENAME
    assert "Person B-generated audit output" in contract["receipt_role"]
    assert "canonical_receipt_sha256 omitted" in contract["receipt_hash_scope"]
    assert contract["atomic_write_protocol"]["mutates_existing_family_outputs"] is False
    assert contract["scientific_execution_performed"] is False
    assert contract["u4_output_inspected"] is False


def test_final_decision_is_conditional_and_preserves_scientific_scope() -> None:
    decision = _documents()["final_authorization_decision.json"]
    assert decision["authorization_decision"] == (
        "AUTHORIZED_CONDITIONAL_ON_ALL_RUNTIME_GATES"
    )
    assert decision["previous_authorization_superseded"] is True
    assert decision["preexisting_receipt_required"] is False
    assert decision["preserved_family_count"] == 5
    assert decision["preserved_prediction_count"] == 7691
    assert decision["runtime_absent_family_selection_required"] is True
    assert decision["person_d_code_change_required"] is False
    assert decision["production_execution_performed"] is False


def test_package_is_canonical_and_sha256_inventory_is_exact() -> None:
    documents = _documents()
    expected_names = {
        "authority_binding.json",
        "final_authorization_decision.json",
        "person_d_authorization_record.json",
        "production_commands.json",
        "provenance_audit_contract.json",
        "sha256_inventory.json",
        "validation_receipt.json",
    }
    assert set(documents) == expected_names
    for name, document in documents.items():
        raw = (PACKAGE / name).read_bytes()
        assert raw == validator.canonical_json_bytes(document)
    inventory = documents["sha256_inventory.json"]
    assert inventory["algorithm"] == "sha256"
    assert inventory["inventory_excludes_self"] is True
    expected_paths = {
        (PACKAGE_RELATIVE / name).as_posix()
        for name in expected_names - {"sha256_inventory.json"}
    }
    assert set(inventory["files"]) == expected_paths
    for relative_path, expected in inventory["files"].items():
        raw = (ROOT / relative_path).read_bytes()
        assert expected == {
            "byte_size": len(raw),
            "sha256": validator._sha256(raw),
        }


def test_authoring_performed_no_scientific_execution_or_u4_inspection() -> None:
    for document in _documents().values():
        if "scientific_execution_performed" in document:
            assert document["scientific_execution_performed"] is False
        if "production_execution_performed" in document:
            assert document["production_execution_performed"] is False
        if "u4_output_inspected" in document:
            assert document["u4_output_inspected"] is False
