"""Focused evidence for the complete Person B Phase 1.7 synthetic chain."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from mineocclude.analysis.manifests import validate_sealed_artifact
from mineocclude.analysis.synthetic_chain import run_synthetic_analysis_chain
from mineocclude.analysis.synthetic_numbers import (
    SYNTHETIC_SIGNIFICANT_DIGITS,
    canonical_synthetic_float,
)
from mineocclude.integration.synthetic_pipeline import (
    build_authenticated_probe_bridge_inputs,
    load_pipeline_inputs,
)


ROOT = Path(__file__).resolve().parents[2]
SAVED = ROOT / "tests" / "fixtures" / "person_b" / "synthetic_analysis_chain_v1.json"


def inputs():
    bundle, documents, source_hashes = load_pipeline_inputs()
    activation, state, _targets, chunks, _lineage = build_authenticated_probe_bridge_inputs(
        bundle, documents, source_hashes
    )
    return state, activation, chunks


def execute(state=None, activation=None, chunks=None):
    original_state, original_activation, original_chunks = inputs()
    return run_synthetic_analysis_chain(
        state_document=original_state if state is None else state,
        activation_package=original_activation if activation is None else activation,
        chunk_payloads_by_id=original_chunks if chunks is None else chunks,
    )


def test_full_chain_is_sealed_non_scientific_and_matches_saved_evidence():
    report = execute()
    saved = json.loads(SAVED.read_text(encoding="utf-8"))
    assert report == saved
    assert report["status"] == "passed"
    assert report["synthetic"] is True
    assert report["scientific_use"] == "forbidden"
    validate_sealed_artifact(report["eligibility_ledger"])
    validate_sealed_artifact(report["result_bundle"])
    for artifact in report["prediction_artifacts"].values():
        validate_sealed_artifact(artifact)
        assert artifact["scientific_use"] == "forbidden"
    for artifact in report["result_artifacts"].values():
        validate_sealed_artifact(artifact)
        assert artifact["scientific_use"] == "forbidden"


def test_numeric_canonicalization_collapses_supported_numpy_last_bit_pairs():
    """Recorded NumPy 1.26.4/2.4.3 results serialize identically."""

    observed_pairs = (
        (0.17781833022759722, 0.17781833022759724),
        (8.888905555555551, 8.888905555555553),
        (15.556958355544333, 15.556958355544335),
        (-0.5621745611958644, -0.5621745611958648),
    )
    assert SYNTHETIC_SIGNIFICANT_DIGITS == 14
    for numpy_2_4_3_value, numpy_1_26_4_value in observed_pairs:
        assert canonical_synthetic_float(
            numpy_2_4_3_value
        ) == canonical_synthetic_float(numpy_1_26_4_value)


def test_signal_expectations_and_oof_audit_are_explicit():
    report = execute()
    signals = report["signal_expectations"]
    assert signals["decodable_mean_r2"] > 0.8
    assert signals["decodable_log_spread_r2"] > 0.8
    assert signals["time_only_r2"] > 0.8
    low, high = signals["pure_noise_predeclared_range"]
    assert low <= signals["pure_noise_r2"] <= high
    assert report["fit_audit"]["layout_disjoint"] is True
    assert report["fit_audit"]["preprocessing_scope"] == "outer_training_rows_only"
    assert report["fit_audit"]["forbidden_feature_sources"] == []


def test_visible_null_spread_rows_are_ledgered_not_silently_dropped():
    report = execute()
    rows = report["eligibility_ledger"]["rows"]
    assert len(rows) == len(report["frame_table"]["rows"])
    assert {row["reason"] for row in rows} == {
        "eligible_hidden_positive_spread",
        "visible_zero_spread_null",
    }


@pytest.mark.parametrize("failure", ["invalid_identity", "duplicate_state", "stale_chunk", "missing_layer"])
def test_chain_fails_closed_on_invalid_source_evidence(failure):
    state, activation, chunks = inputs()
    state = copy.deepcopy(state)
    activation = copy.deepcopy(activation)
    chunks = copy.deepcopy(chunks)
    if failure == "invalid_identity":
        state["rows"][0]["model_frame_idx"] = True
    elif failure == "duplicate_state":
        state["rows"].append(copy.deepcopy(state["rows"][0]))
    elif failure == "stale_chunk":
        chunk_id = next(iter(chunks))
        chunks[chunk_id] += b" "
    else:
        layer = activation["index_rows"][0]["layer_idx"]
        activation["index_rows"] = [
            row for row in activation["index_rows"] if row["layer_idx"] != layer
        ]
    with pytest.raises(Exception):
        execute(state, activation, chunks)


def test_chain_is_order_independent_and_non_mutating():
    state, activation, chunks = inputs()
    before = copy.deepcopy((state, activation, chunks))
    expected = execute(state, activation, chunks)
    state["rows"].reverse()
    activation["index_rows"].reverse()
    activation["chunks"].reverse()
    actual = execute(state, activation, chunks)
    assert actual == expected
    state["rows"].reverse()
    activation["index_rows"].reverse()
    activation["chunks"].reverse()
    assert (state, activation, chunks) == before
