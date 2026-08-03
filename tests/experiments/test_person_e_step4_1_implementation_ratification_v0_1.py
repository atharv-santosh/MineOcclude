"""Focused independent tests for Person E implementation ratification."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from mineocclude.experiments.step4_1_implementation_review_v0_1 import (
    BOUNDED_REVEAL_SHA256,
    EXACT_COMMAND,
    PERSON_B_IMPLEMENTATION_COMMIT,
    PERSON_B_PREPARATION_COMMIT,
    ImplementationReviewError,
    build_ratification_documents,
    independent_max_t_vector,
    review_person_b_implementation,
    validate_ratification_documents,
)
from scripts.validate_person_e_step4_1_implementation_ratification_v0_1 import (
    validate_package,
)

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = (
    ROOT
    / "docs/status/person_e_phase4_step4_1_final_comparison_implementation_ratification_v0_1"
)


def test_independent_review_passes_exact_git_objects() -> None:
    review = review_person_b_implementation(ROOT)
    assert review["implementation_commit"] == PERSON_B_IMPLEMENTATION_COMMIT
    assert review["person_b_preparation_commit"] == PERSON_B_PREPARATION_COMMIT
    assert review["implementation_blob_count"] == 4
    assert review["frozen_aggregation_exact"] is True
    assert review["probe_refit_absent"] is True
    assert review["manual_u4_inspection_absent"] is True


def test_independent_deterministic_vector_matches_frozen_result() -> None:
    assert independent_max_t_vector() == {
        "layer_00_last_seen": 0.078,
        "layer_01_last_seen": 0.037,
    }


def test_ratification_binds_completed_reveal_and_command() -> None:
    ratification = build_ratification_documents(ROOT)[
        "implementation_ratification.json"
    ]
    assert ratification["bounded_reveal_prediction_count"] == 100
    assert ratification["bounded_reveal_prediction_sha256"] == BOUNDED_REVEAL_SHA256
    assert ratification["final_comparison_implementation_ratified"] is True
    assert not any("<" in token or ">" in token for token in EXACT_COMMAND)


def test_package_and_inventory_match_independent_builder() -> None:
    observed = {
        path.name: json.loads(path.read_text(encoding="utf-8"))
        for path in PACKAGE.glob("*.json")
        if path.name != "sha256_inventory.json"
    }
    assert observed == build_ratification_documents(ROOT)
    validate_ratification_documents(ROOT, observed)
    validate_package()


@pytest.mark.parametrize(
    ("file_name", "field", "changed"),
    [
        ("implementation_ratification.json", "final_comparison_implementation_ratified", False),
        ("implementation_ratification.json", "frozen_scientific_contract_unchanged", False),
        ("independent_conformance_review.json", "probe_refit_absent", False),
        ("validation_receipt.json", "scientific_execution_performed", True),
    ],
)
def test_changed_ratification_fails(
    file_name: str, field: str, changed: object
) -> None:
    documents = copy.deepcopy(build_ratification_documents(ROOT))
    documents[file_name][field] = changed
    with pytest.raises(ImplementationReviewError, match="differs"):
        validate_ratification_documents(ROOT, documents)
