"""Focused contract-only tests for the final Step 4.1 comparison."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from mineocclude.analysis.step4_1_final_contract_v0_1 import (
    FinalComparisonContractError,
    build_final_comparison_contract,
    layout_macro_mean,
    max_t_adjusted_p_values,
    qualifying_layer_bands,
    validate_final_comparison_contract,
)

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "docs/status/person_b_phase4_step4_1_final_comparison_contract_v0_1"


def test_frozen_contract_is_exact_and_has_no_open_choice() -> None:
    document = json.loads((PACKAGE / "final_comparison_contract.json").read_text())
    assert document == build_final_comparison_contract()
    validate_final_comparison_contract(document)
    assert document["unresolved_scientific_choices"] == []
    assert document["layer_contract"]["selection_mode"] == (
        "none_all_layers_fixed_before_runtime"
    )


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("layer_contract", "selection_mode"), "best_observed_layer"),
        (("multiplicity_contract", "adjustment"), "none"),
        (("confidence_interval_contract", "bootstrap_count"), 1000),
        (("u4_restrictions", "manual_u4_inspection_authorized"), True),
    ],
)
def test_post_hoc_or_scope_expansion_is_rejected(path, value) -> None:
    document = copy.deepcopy(build_final_comparison_contract())
    document[path[0]][path[1]] = value
    with pytest.raises(FinalComparisonContractError):
        validate_final_comparison_contract(document)


def test_applicability_pairing_and_macro_weighting_vector() -> None:
    rows = [
        {"layout_id": "a", "trajectory_id": "a1", "value": 1.0},
        {"layout_id": "a", "trajectory_id": "a1", "value": 3.0},
        {"layout_id": "b", "trajectory_id": "b1", "value": 9.0},
    ]
    assert layout_macro_mean(rows) == 5.5


def test_max_t_is_deterministic_and_jointly_adjusted() -> None:
    hypotheses = {
        "h1": {"a": 0.5, "b": 0.2, "c": 0.4, "d": -0.1, "e": 0.3},
        "h2": {"a": 0.6, "b": 0.3, "c": 0.5, "d": 0.1, "e": 0.4},
    }
    first = max_t_adjusted_p_values(hypotheses)
    second = max_t_adjusted_p_values(hypotheses)
    assert first == second
    assert set(first) == set(hypotheses)
    assert all(0.001 <= value <= 1.0 for value in first.values())


def test_contiguous_band_rule_never_selects_isolated_peak() -> None:
    gates = {layer: layer in {2, 3, 4, 8} for layer in range(20)}
    assert qualifying_layer_bands(gates) == ((2, 3, 4),)


def test_reveal_pair_identities_and_count_are_exact() -> None:
    contract = build_final_comparison_contract()
    events = contract["reveal_event_contract"]
    assert len(events) == 5
    assert {event["post_model_frame_idx"] for event in events} == {228, 210, 138, 106, 93}
    assert all(event["post_model_frame_idx"] == event["pre_model_frame_idx"] + 1 for event in events)


def test_contract_prohibits_execution_before_e_ratification() -> None:
    contract = build_final_comparison_contract()
    assert contract["execution_interface"]["person_e_ratification_required"] is True
    assert contract["scientific_execution_performed"] is False
    assert not any(contract["u4_restrictions"].values())
