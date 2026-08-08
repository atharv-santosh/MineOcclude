"""Focused tests for Person E's exact bounded reveal authorization."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from mineocclude.experiments.step4_1_contract_review_v0_1 import (
    Step41ContractReviewError,
    build_bounded_reveal_authorization,
    review_person_b_contracts,
    validate_bounded_reveal_authorization,
)

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / (
    "docs/status/person_e_phase4_step4_1_bounded_reveal_authorization_v0_1"
)


def test_exact_person_b_git_objects_pass_independent_review() -> None:
    review = review_person_b_contracts(ROOT)
    assert review["all_checks_passed"] is True
    assert review["review_mode"] == "independent_exact_git_object_reads_no_merge"
    assert review["unresolved_scientific_choices"] == []


def test_authorization_is_exact_and_narrow() -> None:
    document = json.loads(
        (PACKAGE / "bounded_reveal_authorization.json").read_text()
    )
    assert document == build_bounded_reveal_authorization(ROOT)
    validate_bounded_reveal_authorization(document, repository=ROOT)
    assert document["bounded_reveal_authorized"] is True
    assert document["post_reveal_probe_predictions_authorized"] is True
    assert document["probe_refitting_authorized"] is False
    assert document["expected_prediction_count"] == 100


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("broad_hidden_state_interpretation_authorized", True),
        ("manual_u4_inspection_authorized", True),
        ("probe_refitting_authorized", True),
        ("exploratory_metrics_authorized", True),
        ("post_hoc_layer_selection_authorized", True),
        ("post_hoc_test_selection_authorized", True),
        ("step4_1_complete", True),
        ("u4_output_inspected", True),
    ],
)
def test_authority_expansion_is_rejected(field, value) -> None:
    document = copy.deepcopy(build_bounded_reveal_authorization(ROOT))
    document[field] = value
    with pytest.raises(Step41ContractReviewError):
        validate_bounded_reveal_authorization(document, repository=ROOT)


def test_exact_rows_layers_target_and_output_are_bound() -> None:
    document = build_bounded_reveal_authorization(ROOT)
    assert len(document["authorized_event_and_row_identities"]) == 5
    assert all(
        event["layer_indices"] == list(range(20))
        for event in document["authorized_event_and_row_identities"]
    )
    assert document["authorized_fitted_probes"]["target"] == "log_sigma_oracle"
    assert document["authorized_fitted_probes"]["reuse_without_refit"] is True
    assert document["authorized_output_root"].endswith(
        "person-b-step4-1-bounded-reveal-v0-1"
    )


def test_no_scientific_execution_or_u4_claim() -> None:
    receipt = json.loads((PACKAGE / "validation_receipt.json").read_text())
    assert receipt["scientific_execution_performed"] is False
    assert receipt["post_reveal_predictions_produced"] is False
    assert receipt["u4_output_inspected"] is False
    assert receipt["person_b_branch_merged"] is False
