from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

from mineocclude.analysis.no_wall_positive_control_66_cell_v0_1 import (
    ACTIVATION_INDEX_SHA256,
    PERSON_B_FOLD_MANIFEST_SHA256,
    PERSON_B_ROW_UNIVERSE_RECORDS_SHA256,
    PERSON_D_PREDICTION_MANIFEST_SHA256,
    RUN_ID,
    bootstrap_r2_interval,
    evaluate_positive_control_readiness,
    score_oof_predictions,
)


def _receipt(*, r2=0.8, ci_low=0.4, p=0.001, improvement=1.0):
    r2_pass = r2 >= 0.5
    ci_pass = ci_low > 0.0
    shuffle_pass = improvement > 0.0 and p < 0.01
    positive_pass = r2_pass and ci_pass and shuffle_pass
    return {
        "schema_id": "integration-bd-66-cell-no-wall-positive-control-v0-1",
        "run_id": RUN_ID,
        "authority_bindings": {
            "activation_index_sha256": ACTIVATION_INDEX_SHA256,
            "person_b_fold_manifest_sha256": PERSON_B_FOLD_MANIFEST_SHA256,
            "person_b_row_universe_records_sha256": PERSON_B_ROW_UNIVERSE_RECORDS_SHA256,
            "person_d_prediction_manifest_sha256": PERSON_D_PREDICTION_MANIFEST_SHA256,
        },
        "best_layer_metrics": {
            "r2": r2,
            "r2_ci_low": ci_low,
            "grouped_shuffle_max_t_adjusted_p": p,
            "grouped_shuffle_layout_macro_improvement": improvement,
        },
        "gate_decision": {
            "r2_gate_pass": r2_pass,
            "bootstrap_ci_gate_pass": ci_pass,
            "shuffle_comparison_gate_pass": shuffle_pass,
            "positive_control_pass": positive_pass,
        },
    }


def test_artifact_exists_but_subthreshold_r2_fails():
    result = evaluate_positive_control_readiness(_receipt(r2=0.49))
    assert result.artifact_present is True
    assert result.r2_gate_pass is False
    assert result.statistical_gate_pass is False


def test_r2_passes_but_ci_crosses_zero_fails():
    result = evaluate_positive_control_readiness(_receipt(r2=0.8, ci_low=0.0))
    assert result.r2_gate_pass is True
    assert result.bootstrap_ci_gate_pass is False
    assert result.statistical_gate_pass is False


def test_all_frozen_gate_conditions_pass():
    result = evaluate_positive_control_readiness(_receipt())
    assert result.artifact_present is True
    assert result.r2_gate_pass is True
    assert result.bootstrap_ci_gate_pass is True
    assert result.shuffle_comparison_gate_pass is True
    assert result.statistical_gate_pass is True


def test_missing_current_receipt_cannot_fall_back_to_historical_evidence():
    result = evaluate_positive_control_readiness(None)
    assert result.artifact_present is False
    assert result.statistical_gate_pass is False
    assert "NO_HISTORICAL_FALLBACK" in result.reason


def test_declared_pass_cannot_override_recomputed_gate():
    receipt = deepcopy(_receipt(r2=0.49))
    receipt["gate_decision"]["positive_control_pass"] = True
    result = evaluate_positive_control_readiness(receipt)
    assert result.artifact_present is True
    assert result.statistical_gate_pass is False
    assert result.reason == "CURRENT_POSITIVE_CONTROL_RECEIPT_DECLARED_GATE_MISMATCH"


def test_positive_control_scoring_and_hierarchical_bootstrap_are_finite():
    truth = [0.0, 1.0, 2.0, 0.0, 1.0, 2.0]
    prediction = [0.1, 0.9, 2.1, -0.1, 1.1, 1.9]
    rows = [
        {"layout_id": "layout_01", "trajectory_id": "trajectory_01"},
        {"layout_id": "layout_01", "trajectory_id": "trajectory_01"},
        {"layout_id": "layout_01", "trajectory_id": "trajectory_01"},
        {"layout_id": "layout_02", "trajectory_id": "trajectory_02"},
        {"layout_id": "layout_02", "trajectory_id": "trajectory_02"},
        {"layout_id": "layout_02", "trajectory_id": "trajectory_02"},
    ]
    metric = score_oof_predictions(truth, prediction)
    low, high, values = bootstrap_r2_interval(
        truth, prediction, rows, resample_count=25, seed=20260721
    )
    assert metric["r2"] > 0.9
    assert len(values) == 25
    assert low <= high


def test_superseding_readiness_separates_presence_from_statistical_pass():
    path = (
        Path(__file__).resolve().parents[2]
        / "docs/status/integration/bd_production_input_readiness_v0_2/readiness_receipt.json"
    )
    readiness = json.loads(path.read_text(encoding="utf-8"))
    assert readiness["positive_control"]["positive_control_artifact_present"] is True
    assert readiness["positive_control"]["positive_control_statistical_gate_pass"] is False
    assert readiness["readiness_decision"]["u1_u2_interpretation_permitted"] is False
    assert readiness["historical_positive_control_fallback_allowed"] is False
