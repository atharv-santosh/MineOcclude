"""Focused non-production tests for the bounded reveal contract."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from mineocclude.analysis.step4_1_bounded_reveal_v0_1 import (
    BoundedRevealContractError,
    build_bounded_reveal_contract,
    predict_with_raw_probe,
    reveal_events,
    validate_bounded_reveal_contract,
    validate_prediction_rows,
)

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "docs/status/person_b_phase4_step4_1_bounded_reveal_contract_v0_1"


def test_contract_is_exact_and_requires_e_authorization() -> None:
    document = json.loads((PACKAGE / "bounded_reveal_contract.json").read_text())
    assert document == build_bounded_reveal_contract()
    validate_bounded_reveal_contract(document)
    assert document["authorities"]["person_e_authorization_required"] is True
    assert document["scientific_execution_performed"] is False


def test_inputs_exist_without_extraction_or_refit() -> None:
    decision = build_bounded_reveal_contract()["availability_decision"]
    assert decision == {
        "PERSON_A_ADDITIONAL_EXTRACTION_REQUIRED": False,
        "PERSON_B_PROBE_REFIT_REQUIRED": False,
        "POST_REVEAL_INPUTS_AVAILABLE": True,
        "basis": decision["basis"],
        "core_activation_row_count": 17480,
        "core_source_frame_count": 874,
        "post_reveal_activation_row_count": 100,
    }


def test_exact_event_and_transition_identities() -> None:
    events = reveal_events()
    assert [event["post_identity"]["model_frame_idx"] for event in events] == [
        228,
        210,
        138,
        106,
        93,
    ]
    assert all(
        event["post_identity"]["model_frame_idx"]
        == event["pre_identity"]["model_frame_idx"] + 1
        for event in events
    )
    assert {event["fold_idx"] for event in events} == {0, 1, 2, 3, 4}


def test_raw_probe_prediction_vector_is_deterministic() -> None:
    vector = [0.0] * 2048
    weights = [0.0] * 2048
    vector[0] = 2.0
    weights[0] = 0.25
    assert predict_with_raw_probe(vector, weights, 0.125) == 0.625


def test_prediction_coverage_is_exact() -> None:
    rows = []
    for event in reveal_events():
        for layer in range(20):
            rows.append(
                {
                    "event_id": event["event_id"],
                    "hook_site": "decoder_layer_output_residual_stream",
                    "layer_idx": layer,
                    "prediction": 0.1,
                    "prediction_scope": "held_out",
                    "relative_time_seconds": 0.0,
                    "target_name": "log_sigma_oracle",
                    "visibility": "visible",
                }
            )
    validate_prediction_rows(rows)
    with pytest.raises(BoundedRevealContractError):
        validate_prediction_rows(rows[:-1])


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("manual_u4_inspection_authorized", True),
        ("person_a_additional_extraction_required", True),
        ("person_b_probe_refit_required", True),
        ("post_reveal_inputs_available", False),
    ],
)
def test_authority_expansion_is_rejected(field, value) -> None:
    document = copy.deepcopy(build_bounded_reveal_contract())
    document["state"][field] = value
    with pytest.raises(BoundedRevealContractError):
        validate_bounded_reveal_contract(document)


def test_command_is_frozen_without_running_it() -> None:
    command = build_bounded_reveal_contract()["execution_contract"]["command"]
    assert command[:2] == ["python", "scripts/run_person_b_step4_1_bounded_reveal.py"]
    assert "--person-e-authorization-commit" in command
