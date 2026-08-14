"""Unit tests for the 66-cell production metric package (Person D).

``baseline_metrics_66_cell_v0_1`` computes the actual real U1/U2 numbers
published for the 66-cell production run (``docs/status/
person_d_66_cell_production_baselines_v0_1/baseline_metrics.json``), but
unlike every other Person D module it had no dedicated unit test file --
only indirect, whole-package coverage from the one real production run.
These tests exercise the fail-closed ``_unavailable(...)`` branches and
accounting logic directly with small synthetic fixtures, since the real
production data never triggers most of them (too many admitted rows).
"""

from __future__ import annotations

import pytest

from mineocclude.baselines.baseline_metrics_66_cell_v0_1 import (
    BaselineMetricsError,
    ScoredRow,
    build_family_target_metrics,
    build_floor_comparison,
    build_metric_package,
    build_scored_rows,
)
from mineocclude.baselines.interface import BaselineRow

SYNTHETIC = "synthetic"


def _row(
    *,
    trajectory_id: str,
    layout_id: str,
    model_frame_idx: int = 0,
    fold: int = 0,
    target_name: str = "mu_oracle_blocks",
    baseline_name: str = "last_seen",
    prediction: float | None,
    applicable: bool = True,
) -> BaselineRow:
    return BaselineRow(
        trajectory_id=trajectory_id,
        layout_id=layout_id,
        model_frame_idx=model_frame_idx,
        fold=fold,
        regime="A",
        target_name=target_name,
        baseline_name=baseline_name,
        prediction=prediction,
        applicable=applicable,
        visibility=True,
        tau_seconds=1.0,
        v_scripted_blocks_per_s=1.0,
        q_scripted_blocks2_per_s=0.05,
        duration_seconds=3.0,
        config_hash="test",
        seed=1,
    )


def _scored(
    trajectory_id: str,
    layout_id: str,
    fold_idx: int,
    prediction: float,
    truth: float,
    tau_seconds: float = 1.0,
) -> ScoredRow:
    return ScoredRow(
        trajectory_id=trajectory_id,
        layout_id=layout_id,
        model_frame_idx=0,
        fold_idx=fold_idx,
        control_type="unknown",
        prediction=prediction,
        truth=truth,
        tau_seconds=tau_seconds,
    )


# --------------------------------------------------------------------------
# build_scored_rows: pairing and the row-accounting ledger
# --------------------------------------------------------------------------


def test_build_scored_rows_filters_by_target_and_applicability_and_truth():
    rows = [
        _row(trajectory_id="t1", layout_id="L1", target_name="mu_oracle_blocks", prediction=1.0),
        _row(trajectory_id="t1", layout_id="L1", target_name="log_sigma_oracle", prediction=1.0),
        _row(trajectory_id="t2", layout_id="L1", target_name="mu_oracle_blocks", prediction=None, applicable=False),
        _row(trajectory_id="t3", layout_id="L1", target_name="mu_oracle_blocks", prediction=2.0),
    ]
    truth_by_key = {("t1", 0): 1.5}  # t3 applicable but has no truth on record

    scored, accounting = build_scored_rows(
        rows,
        target_name="mu_oracle_blocks",
        truth_by_key=truth_by_key,
        tau_by_key={},
        control_type_by_key={},
    )

    assert [row.trajectory_id for row in scored] == ["t1"]
    assert accounting == {
        "emitted_rows": 3,
        "applicable_rows": 2,
        "non_applicable_rows": 1,
        "scored_rows": 1,
        "applicable_without_truth": 1,
    }


def test_build_scored_rows_empty_when_target_absent():
    rows = [_row(trajectory_id="t1", layout_id="L1", target_name="log_sigma_oracle", prediction=1.0)]
    scored, accounting = build_scored_rows(
        rows, target_name="mu_oracle_blocks", truth_by_key={}, tau_by_key={}, control_type_by_key={}
    )
    assert scored == []
    assert accounting["emitted_rows"] == 0


# --------------------------------------------------------------------------
# build_family_target_metrics: fail-closed unavailability at the edges
# --------------------------------------------------------------------------


def test_regression_block_unavailable_for_a_single_row():
    scored = [_scored("t1", "L1", 0, prediction=1.0, truth=1.0)]
    result = build_family_target_metrics(
        family_id="last_seen", target_name="mu_oracle_blocks", scored=scored, accounting={}
    )
    aggregate = result["aggregate"]
    # A single row makes truth constant -> regression_metrics refuses (R^2 undefined).
    assert aggregate["regression"]["available"] is False
    assert "u1_metric_error" in aggregate["regression"]["reason"]
    assert aggregate["bootstrap_r2"] == {"available": False, "reason": "fewer than two scored rows"}
    assert aggregate["grouped_permutation"] == {"available": False, "reason": "fewer than two scored rows"}


def test_regression_block_unavailable_when_no_rows_at_all():
    result = build_family_target_metrics(
        family_id="last_seen", target_name="mu_oracle_blocks", scored=[], accounting={}
    )
    assert result["aggregate"]["regression"] == {"available": False, "reason": "no scored rows"}


def test_permutation_reports_resampling_error_for_a_singleton_stratum():
    # One trajectory of length 1 and one of length 2: neither length has
    # two blocks to permute against, so permute_trajectory_blocks refuses.
    scored = [
        _scored("t1", "L1", 0, prediction=1.0, truth=1.0),
        _scored("t2", "L1", 0, prediction=2.0, truth=1.5),
        _scored("t2", "L1", 1, prediction=2.5, truth=2.0),
    ]
    result = build_family_target_metrics(
        family_id="last_seen", target_name="mu_oracle_blocks", scored=scored, accounting={}
    )
    permutation = result["aggregate"]["grouped_permutation"]
    assert permutation["available"] is False
    assert permutation["reason"].startswith("resampling_error:")
    assert permutation["permutation_unit"] == "whole_trajectory_block"
    assert permutation["requested_permutation_count"] == 999
    assert "observed_r2" in permutation


def test_u2_target_adds_partial_correlation_and_marks_coverage_unavailable():
    scored = [
        _scored("t1", "L1", 0, prediction=1.0, truth=1.0, tau_seconds=0.5),
        _scored("t2", "L1", 0, prediction=2.0, truth=1.5, tau_seconds=1.5),
        _scored("t3", "L2", 1, prediction=0.5, truth=0.4, tau_seconds=3.0),
    ]
    result = build_family_target_metrics(
        family_id="known_q_analytic", target_name="log_sigma_oracle", scored=scored, accounting={}
    )
    aggregate = result["aggregate"]
    assert aggregate["partial_correlation_controlling_tau"]["available"] is True
    assert aggregate["partial_correlation_controlling_tau"]["control"] == "tau"
    assert aggregate["coverage_and_ece"]["available"] is False
    assert "no frozen Person D baseline pairs" in aggregate["coverage_and_ece"]["reason"]


def test_partial_correlation_unavailable_below_three_rows():
    scored = [
        _scored("t1", "L1", 0, prediction=1.0, truth=1.0),
        _scored("t2", "L1", 0, prediction=2.0, truth=1.5),
    ]
    result = build_family_target_metrics(
        family_id="known_q_analytic", target_name="log_sigma_oracle", scored=scored, accounting={}
    )
    assert result["aggregate"]["partial_correlation_controlling_tau"] == {
        "available": False,
        "reason": "fewer than three scored rows",
    }


def test_per_fold_results_are_grouped_and_sorted_by_fold_idx():
    scored = [
        _scored("t1", "L1", 2, prediction=1.0, truth=1.0),
        _scored("t2", "L1", 0, prediction=2.0, truth=1.5),
        _scored("t3", "L2", 0, prediction=0.5, truth=0.4),
    ]
    result = build_family_target_metrics(
        family_id="last_seen", target_name="mu_oracle_blocks", scored=scored, accounting={}
    )
    fold_indices = [entry["fold_idx"] for entry in result["per_fold"]]
    assert fold_indices == [0, 2]
    fold0 = result["per_fold"][0]
    assert fold0["scored_row_count"] == 2
    assert fold0["trajectory_count"] == 2
    assert fold0["layout_count"] == 2
    assert result["comparison_class"] == "memory_heuristic"


def test_bootstrap_and_permutation_are_available_and_deterministic_with_enough_rows():
    scored = [
        _scored("t1", "L1", 0, prediction=1.0, truth=1.1),
        _scored("t2", "L1", 0, prediction=2.0, truth=1.9),
        _scored("t3", "L2", 1, prediction=3.0, truth=3.2),
        _scored("t4", "L2", 1, prediction=4.0, truth=3.8),
    ]
    first = build_family_target_metrics(
        family_id="last_seen", target_name="mu_oracle_blocks", scored=scored, accounting={}
    )
    second = build_family_target_metrics(
        family_id="last_seen", target_name="mu_oracle_blocks", scored=scored, accounting={}
    )
    bootstrap = first["aggregate"]["bootstrap_r2"]
    permutation = first["aggregate"]["grouped_permutation"]
    assert bootstrap["available"] is True
    assert bootstrap["seed"] == 20260721
    assert permutation["available"] is True
    assert permutation["seed"] == 20260720
    # Fixed seeds -> byte-identical statistics across repeated runs.
    assert first["aggregate"]["bootstrap_r2"] == second["aggregate"]["bootstrap_r2"]
    assert first["aggregate"]["grouped_permutation"] == second["aggregate"]["grouped_permutation"]


# --------------------------------------------------------------------------
# build_floor_comparison
# --------------------------------------------------------------------------


def test_floor_comparison_unavailable_with_no_shared_rows():
    family_scored = [_scored("t1", "L1", 0, prediction=1.0, truth=1.0)]
    floor_scored = [_scored("t2", "L1", 0, prediction=0.5, truth=0.4)]
    result = build_floor_comparison(
        family_id="last_seen",
        target_name="mu_oracle_blocks",
        family_scored=family_scored,
        floor_scored=floor_scored,
    )
    assert result["intersection_row_count"] == 0
    assert result["delta_r2"] == {"available": False, "reason": "no shared scored rows with the floor"}


def test_floor_comparison_unavailable_when_truth_disagrees_on_a_shared_row():
    family_scored = [_scored("t1", "L1", 0, prediction=1.0, truth=1.0)]
    floor_scored = [_scored("t1", "L1", 0, prediction=0.5, truth=999.0)]
    result = build_floor_comparison(
        family_id="last_seen",
        target_name="mu_oracle_blocks",
        family_scored=family_scored,
        floor_scored=floor_scored,
    )
    assert result["intersection_row_count"] == 1
    assert result["delta_r2"] == {
        "available": False,
        "reason": "family and floor disagree on oracle truth for a shared row",
    }


def test_floor_comparison_computes_a_real_delta_on_the_row_intersection():
    family_scored = [
        _scored("t1", "L1", 0, prediction=1.0, truth=1.1),
        _scored("t2", "L1", 0, prediction=2.0, truth=1.9),
    ]
    floor_scored = [
        _scored("t1", "L1", 0, prediction=5.0, truth=1.1),
        _scored("t2", "L1", 0, prediction=-3.0, truth=1.9),
    ]
    result = build_floor_comparison(
        family_id="last_seen",
        target_name="mu_oracle_blocks",
        family_scored=family_scored,
        floor_scored=floor_scored,
    )
    delta = result["delta_r2"]
    assert delta["available"] is True
    assert delta["sample_count"] == 2
    assert delta["family_r2"] > delta["floor_r2"]
    assert delta["delta_r2"] == pytest.approx(delta["family_r2"] - delta["floor_r2"])
    assert result["family_rows_not_in_floor"] == 0
    assert result["floor_rows_not_in_family"] == 0


# --------------------------------------------------------------------------
# build_metric_package
# --------------------------------------------------------------------------


def test_build_metric_package_rejects_an_invalid_evidence_kind():
    with pytest.raises(BaselineMetricsError, match="evidence_kind"):
        build_metric_package(
            run_id="test-run",
            family_metrics=[],
            floor_comparisons=[],
            source_identities={},
            evidence_kind="fabricated",
        )


def test_build_metric_package_counts_and_declares_not_computed_metrics():
    family_metrics = [
        {"per_fold": [{"fold_idx": 0}, {"fold_idx": 1}]},
        {"per_fold": [{"fold_idx": 0}]},
    ]
    document = build_metric_package(
        run_id="test-run",
        family_metrics=family_metrics,
        floor_comparisons=[{"family_id": "last_seen"}],
        source_identities={"b": "b-commit", "a": "a-commit"},
        evidence_kind=SYNTHETIC,
    )
    assert document["evidence_kind"] == SYNTHETIC
    assert document["family_metric_count"] == 2
    assert document["fold_result_count"] == 3
    assert document["floor_comparison_count"] == 1
    # Sorted regardless of insertion order.
    assert list(document["source_identities"]) == ["a", "b"]
    not_computed_metrics = {entry["metric"] for entry in document["not_computed"]}
    assert "u3 reveal_snapback" in not_computed_metrics
    assert all(entry["owner"] == "person_b" for entry in document["not_computed"])
