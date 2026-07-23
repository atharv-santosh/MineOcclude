"""Tests for the visible-history-q spread baseline."""

from __future__ import annotations

import math
from dataclasses import replace

import pytest

from mineocclude.baselines.visible_history_q import (
    VisibleHistoryQError,
    fit_predict_visible_history_q,
)
from tests.baselines.conftest import build_trajectory_contexts


def _build_two_fold_fixture():
    traj_a = build_trajectory_contexts(
        trajectory_id="traj-a",
        layout_id="layout-a",
        fold=0,
        visible_positions=(0.0, 1.0, 1.9, 3.1, 3.9),
        dt=1.0,
        hidden_taus=(1.0, 2.0),
    )
    traj_b = build_trajectory_contexts(
        trajectory_id="traj-b",
        layout_id="layout-b",
        fold=1,
        visible_positions=(0.0, 2.0, 3.9, 6.1, 8.0),
        dt=1.0,
        hidden_taus=(1.0, 2.0),
    )
    visible_positions_by_trajectory = {
        "traj-a": (0.0, 1.0, 1.9, 3.1, 3.9),
        "traj-b": (0.0, 2.0, 3.9, 6.1, 8.0),
    }
    return traj_a + traj_b, visible_positions_by_trajectory


def test_fit_predict_visible_history_q_scores_only_hidden_rows():
    contexts, visible_positions_by_trajectory = _build_two_fold_fixture()

    rows = fit_predict_visible_history_q(
        contexts, visible_positions_by_trajectory, dt_seconds=1.0
    )

    mu_rows = [row for row in rows if row.target_name == "mu_oracle_blocks"]
    log_sigma_rows = [row for row in rows if row.target_name == "log_sigma_oracle"]

    assert all(not row.applicable and row.prediction is None for row in mu_rows)

    visible_log_sigma = [row for row in log_sigma_rows if row.visibility]
    hidden_log_sigma = [row for row in log_sigma_rows if not row.visibility]
    assert visible_log_sigma and all(not row.applicable for row in visible_log_sigma)
    assert hidden_log_sigma and all(row.applicable for row in hidden_log_sigma)
    for row in hidden_log_sigma:
        assert math.isfinite(row.prediction)
        assert row.fit_metadata["q_hat"] > 0.0


def test_fit_predict_visible_history_q_never_touches_scripted_q():
    contexts, visible_positions_by_trajectory = _build_two_fold_fixture()
    poisoned = [
        replace(ctx, q_scripted_blocks2_per_s=999.0, v_scripted_blocks_per_s=999.0)
        for ctx in contexts
    ]

    clean = fit_predict_visible_history_q(
        contexts, visible_positions_by_trajectory, dt_seconds=1.0
    )
    tainted = fit_predict_visible_history_q(
        poisoned, visible_positions_by_trajectory, dt_seconds=1.0
    )

    clean_predictions = [row.prediction for row in clean]
    tainted_predictions = [row.prediction for row in tainted]
    assert clean_predictions == tainted_predictions


def test_fit_predict_visible_history_q_handles_missing_fold_residuals():
    # A fold whose training trajectories yield no usable residuals
    # (too short a visible window) must mark hidden rows not
    # applicable rather than fabricate a q_hat.
    short_traj = build_trajectory_contexts(
        trajectory_id="traj-short",
        layout_id="layout-short",
        fold=0,
        visible_positions=(0.0, 1.0),
        dt=1.0,
        hidden_taus=(1.0,),
    )
    rows = fit_predict_visible_history_q(
        short_traj, {"traj-short": (0.0, 1.0)}, dt_seconds=1.0
    )
    hidden_log_sigma = [
        row
        for row in rows
        if row.target_name == "log_sigma_oracle" and not row.visibility
    ]
    assert hidden_log_sigma
    assert all(not row.applicable and row.prediction is None for row in hidden_log_sigma)


def test_fit_predict_visible_history_q_rejects_conflicting_fold_assignments():
    # One trajectory can never legitimately span two folds under B's
    # layout-grouped splits; a caller bug that produces this must be
    # surfaced loudly, not silently resolved to whichever fold value
    # happened to appear first (PDF Step 3.4 remaining gap).
    contexts, visible_positions_by_trajectory = _build_two_fold_fixture()
    conflicting = list(contexts)
    conflicting[-1] = replace(conflicting[-1], fold=99)

    with pytest.raises(VisibleHistoryQError, match="conflicting fold"):
        fit_predict_visible_history_q(
            conflicting, visible_positions_by_trajectory, dt_seconds=1.0
        )
