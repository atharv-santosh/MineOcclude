"""Focused tests for the superseding Person E execution authorization."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from mineocclude.experiments.step4_1_execution_authorization_v0_1 import (
    FINAL_OUTPUT_FILES,
    FINAL_OUTPUT_ROOT,
    PERSON_E_IMPLEMENTATION_RATIFICATION_COMMIT,
    ExecutionAuthorizationError,
    build_authorization_documents,
    validate_authorization_documents,
    validate_implementation_ratification_commit,
)
from mineocclude.experiments.step4_1_implementation_review_v0_1 import (
    BOUNDED_REVEAL_SHA256,
    EXACT_COMMAND,
    PERSON_B_IMPLEMENTATION_COMMIT,
    PERSON_B_PREPARATION_COMMIT,
)
from scripts.validate_person_e_step4_1_execution_authorization_v0_1 import (
    validate_package,
)

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = (
    ROOT
    / "docs/status/person_e_phase4_step4_1_final_comparison_execution_authorization_v0_1"
)


def test_exact_preceding_ratification_commit_validates() -> None:
    documents = validate_implementation_ratification_commit(ROOT)
    ratification = documents["implementation_ratification.json"]
    assert ratification["final_comparison_implementation_ratified"] is True
    assert ratification["person_b_comparison_implementation_commit"] == (
        PERSON_B_IMPLEMENTATION_COMMIT
    )


def test_authorization_binds_exact_command_inputs_and_output() -> None:
    authorization = build_authorization_documents(ROOT)[
        "execution_authorization.json"
    ]
    assert authorization["authorized_command"] == EXACT_COMMAND
    assert authorization["authorized_output_root"] == FINAL_OUTPUT_ROOT
    assert authorization["exact_output_files"] == FINAL_OUTPUT_FILES
    assert authorization["bounded_reveal_artifact_sha256"] == BOUNDED_REVEAL_SHA256
    assert authorization["person_b_comparison_implementation_commit"] == (
        PERSON_B_IMPLEMENTATION_COMMIT
    )
    assert authorization["person_b_execution_preparation_commit"] == (
        PERSON_B_PREPARATION_COMMIT
    )
    assert authorization["implementation_ratification_commit"] == (
        PERSON_E_IMPLEMENTATION_RATIFICATION_COMMIT
    )


def test_prohibited_authorizations_and_execution_state_remain_false() -> None:
    authorization = build_authorization_documents(ROOT)[
        "execution_authorization.json"
    ]
    for field in (
        "additional_person_a_extraction_authorized",
        "bounded_reveal_rerun_authorized",
        "broad_hidden_state_interpretation_authorized",
        "exploratory_metrics_authorized",
        "manual_u4_inspection_authorized",
        "probe_refitting_authorized",
        "scientific_execution_performed",
        "step4_1_complete",
        "u4_output_inspected",
    ):
        assert authorization[field] is False
    assert authorization["bounded_reveal_reuse_authorized"] is True


def test_package_and_inventory_match_builder() -> None:
    observed = {
        path.name: json.loads(path.read_text(encoding="utf-8"))
        for path in PACKAGE.glob("*.json")
        if path.name != "sha256_inventory.json"
    }
    assert observed == build_authorization_documents(ROOT)
    validate_authorization_documents(ROOT, observed)
    validate_package()


@pytest.mark.parametrize(
    ("file_name", "field", "changed"),
    [
        ("execution_authorization.json", "bounded_reveal_reuse_authorized", False),
        ("execution_authorization.json", "probe_refitting_authorized", True),
        ("execution_authorization.json", "authorized_command", ["python"]),
        ("closure_requirements.json", "step4_1_complete", True),
        ("validation_receipt.json", "scientific_execution_performed", True),
    ],
)
def test_changed_authorization_fails(
    file_name: str, field: str, changed: object
) -> None:
    documents = copy.deepcopy(build_authorization_documents(ROOT))
    documents[file_name][field] = changed
    with pytest.raises(ExecutionAuthorizationError, match="differs"):
        validate_authorization_documents(ROOT, documents)
