"""Tests for the known-q analytic spread baseline (privileged reference)."""

from __future__ import annotations

import math

from mineocclude.baselines.known_q_analytic import (
    IS_FAIR_BASELINE,
    predict_known_q_analytic,
)
from tests.baselines.conftest import build_trajectory_contexts


def test_predict_known_q_analytic_matches_oracle_variance_formula():
    contexts = build_trajectory_contexts(
        trajectory_id="traj-0",
        layout_id="layout-0",
        fold=0,
        visible_positions=(0.0, 1.0, 2.0),
        dt=1.0,
        hidden_taus=(1.0, 2.0, 4.0),
        q_scripted=0.2,
    )

    rows = predict_known_q_analytic(contexts)
    mu_rows = [row for row in rows if row.target_name == "mu_oracle_blocks"]
    log_sigma_rows = [row for row in rows if row.target_name == "log_sigma_oracle"]

    assert all(not row.applicable and row.prediction is None for row in mu_rows)

    hidden_rows = [row for row in log_sigma_rows if not row.visibility]
    visible_rows = [row for row in log_sigma_rows if row.visibility]
    assert visible_rows and all(not row.applicable for row in visible_rows)
    assert hidden_rows and all(row.applicable for row in hidden_rows)

    for row in hidden_rows:
        expected = math.log(math.sqrt(0.2 * row.tau_seconds))
        assert math.isclose(row.prediction, expected, rel_tol=1e-12)
        assert row.fit_metadata["is_fair_baseline"] is False


def test_predict_known_q_analytic_is_not_applicable_without_scripted_q():
    contexts = build_trajectory_contexts(
        trajectory_id="traj-0",
        layout_id="layout-0",
        fold=0,
        visible_positions=(0.0, 1.0),
        dt=1.0,
        hidden_taus=(1.0,),
        q_scripted=None,
    )
    rows = predict_known_q_analytic(contexts)
    hidden_log_sigma = [
        row
        for row in rows
        if row.target_name == "log_sigma_oracle" and not row.visibility
    ]
    assert hidden_log_sigma
    assert all(not row.applicable and row.prediction is None for row in hidden_log_sigma)


def test_is_fair_baseline_flag_is_false():
    assert IS_FAIR_BASELINE is False
