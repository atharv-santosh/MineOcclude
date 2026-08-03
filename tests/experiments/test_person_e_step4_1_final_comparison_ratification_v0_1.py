"""Focused tests for Person E final comparison ratification."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from mineocclude.experiments.step4_1_closure_contract_v0_1 import (
    Step41ClosureContractError,
    build_closure_contract,
    build_final_comparison_ratification,
    build_registry_v2_import_contract,
    validate_final_ratification_package,
)

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / (
    "docs/status/person_e_phase4_step4_1_final_comparison_ratification_v0_1"
)


def _documents():
    return (
        build_final_comparison_ratification(ROOT),
        build_closure_contract(ROOT),
        build_registry_v2_import_contract(ROOT),
    )


def test_final_ratification_package_is_exact() -> None:
    ratification, closure, registry = _documents()
    assert ratification == json.loads(
        (PACKAGE / "final_comparison_ratification.json").read_text()
    )
    assert closure == json.loads((PACKAGE / "closure_contract.json").read_text())
    assert registry == json.loads(
        (PACKAGE / "registry_v2_import_contract.json").read_text()
    )
    validate_final_ratification_package(
        ratification, closure, registry, repository=ROOT
    )


def test_only_exact_metric_sequence_is_authorized() -> None:
    ratification = build_final_comparison_ratification(ROOT)
    assert [
        item["step"] for item in ratification["permitted_execution_sequence"]
    ] == [
        "BOUNDED_REVEAL_PREDICTIONS",
        "FINAL_COMPARISON_METRICS",
        "VERIFY_IMPORT_AND_CLOSE",
    ]
    assert ratification["exact_final_comparison_metrics_authorized"] is True
    assert ratification["exploratory_metrics_authorized"] is False


def test_pass_fail_inconclusive_rules_are_closed() -> None:
    acceptance = build_closure_contract(ROOT)["acceptance_contract"]
    assert acceptance["status_vocabulary"] == ["PASS", "FAIL", "INCONCLUSIVE"]
    assert "contiguous band" in acceptance["pass"]
    assert "integrity and control" in acceptance["fail"]
    assert "unknown hash/version" in acceptance["inconclusive"]


def test_registry_v2_fields_and_trust_chain_are_exact() -> None:
    registry = build_registry_v2_import_contract(ROOT)
    assert registry["registry_generation"] == "v2"
    assert set(registry["accepted_artifact_types"]) == {
        "fitted_probe",
        "prediction",
        "baseline",
        "metric_table",
    }
    assert len(registry["minimum_trust_records_per_output"]) == 7
    assert "direct_input_artifact_ids" in registry["artifact_exact_fields"]


@pytest.mark.parametrize(
    ("document_index", "field", "value"),
    [
        (0, "post_hoc_layer_selection_authorized", True),
        (0, "post_hoc_test_selection_authorized", True),
        (0, "probe_refitting_authorized", True),
        (0, "manual_u4_inspection_authorized", True),
        (0, "step4_1_complete", True),
        (1, "u4_output_inspected", True),
        (2, "unknown_or_extra_type_policy", "ACCEPT"),
    ],
)
def test_scope_or_closure_expansion_is_rejected(document_index, field, value) -> None:
    documents = [copy.deepcopy(document) for document in _documents()]
    documents[document_index][field] = value
    with pytest.raises(Step41ClosureContractError):
        validate_final_ratification_package(*documents, repository=ROOT)


def test_no_scientific_execution_or_premature_closure_claim() -> None:
    receipt = json.loads((PACKAGE / "validation_receipt.json").read_text())
    assert receipt["scientific_execution_performed"] is False
    assert receipt["step4_1_complete"] is False
    assert receipt["u4_output_inspected"] is False
