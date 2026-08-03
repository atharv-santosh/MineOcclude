"""Focused tests for the additive final-comparison preparation package."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from mineocclude.analysis.step4_1_final_comparison_preparation_v0_1 import (
    IMPLEMENTATION_COMMIT,
    IMPLEMENTATION_PATHS,
    FinalComparisonPreparationError,
    build_preparation_documents,
    validate_preparation_documents,
)
from scripts.validate_person_b_step4_1_final_comparison_preparation_v0_1 import (
    validate_package,
)

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = (
    ROOT
    / "docs/status/person_b_phase4_step4_1_final_comparison_execution_preparation_v0_1"
)


def test_preparation_package_matches_builder_and_inventory() -> None:
    observed = {
        path.name: json.loads(path.read_text(encoding="utf-8"))
        for path in PACKAGE.glob("*.json")
        if path.name != "sha256_inventory.json"
    }
    assert observed == build_preparation_documents(ROOT)
    validate_preparation_documents(ROOT, observed)
    validate_package()


def test_implementation_binding_reads_exact_committed_files() -> None:
    binding = build_preparation_documents(ROOT)["implementation_binding.json"]
    assert binding["implementation_commit"] == IMPLEMENTATION_COMMIT
    assert set(binding["files"]) == set(IMPLEMENTATION_PATHS)
    assert binding["scientific_contract_unchanged"] is True
    assert binding["no_new_scientific_choice"] is True


def test_input_contract_requires_completed_reveal_reuse() -> None:
    contract = build_preparation_documents(ROOT)["execution_input_contract.json"]
    reveal = contract["bounded_reveal"]
    assert reveal["prediction_count"] == 100
    assert reveal["sha256"] == (
        "b7716ba00b1e45b20dab130965d03bba8947a87999be51e89404fad4982d288d"
    )
    assert reveal["reuse_required"] is True
    assert reveal["rerun_authorized"] is False
    assert reveal["probe_refitting_authorized"] is False


def test_command_is_exact_non_placeholder_and_non_executed() -> None:
    command = build_preparation_documents(ROOT)["execution_command.json"]
    assert command["non_placeholder"] is True
    assert command["command"][:2] == [
        "python",
        "scripts/run_person_b_step4_1_final_comparison.py",
    ]
    assert "origin/role/person-e-operations" in command["command"]
    assert command["scientific_execution_performed"] is False


def test_output_and_closure_requirements_are_exact() -> None:
    output = build_preparation_documents(ROOT)[
        "output_and_closure_requirements.json"
    ]
    assert len(output["output_files"]) == 7
    assert output["person_e_implementation_ratification_required"] is True
    assert output["person_e_superseding_execution_authorization_required"] is True
    assert output["step4_1_complete"] is False


@pytest.mark.parametrize(
    ("file_name", "field", "changed"),
    [
        ("execution_command.json", "non_placeholder", False),
        ("execution_input_contract.json", "u4_output_inspected", True),
        ("implementation_binding.json", "scientific_contract_unchanged", False),
        ("validation_receipt.json", "scientific_execution_performed", True),
    ],
)
def test_changed_preparation_fails(
    file_name: str, field: str, changed: object
) -> None:
    documents = copy.deepcopy(build_preparation_documents(ROOT))
    documents[file_name][field] = changed
    with pytest.raises(FinalComparisonPreparationError, match="differ"):
        validate_preparation_documents(ROOT, documents)
