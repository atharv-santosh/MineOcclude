"""Fold-integrity and provenance tests for the visible-history-q baseline.

Execution manual Step 3.4 requires this baseline to validate exactly one
authoritative outer-fold assignment per trajectory, reject train/test
overlap, estimate q-hat only from legal pre-occlusion visible history in
*training* data, keep scripted q out of the method input entirely,
preserve NA for unsupported outputs, and record fit rows / fold identity
/ feature identity / estimator metadata.

The conflicting-fold rejection itself is asserted here and in
``test_visible_history_q.py``; this file adds the surrounding invariants.
No real capture data is read anywhere in this file.
"""

from __future__ import annotations

import math
from dataclasses import replace

import pytest

from mineocclude.baselines.visible_history_q import (
    ESTIMATOR_ID,
    FEATURE_ID,
    VisibleHistoryQError,
    fit_predict_visible_history_q,
)
from tests.baselines.conftest import build_trajectory_contexts

DT = 1.0

VISIBLE_BY_TRAJECTORY = {
    "traj-a": (0.0, 1.0, 1.9, 3.1, 3.9),
    "traj-b": (0.0, 2.0, 3.9, 6.1, 8.0),
    "traj-c": (0.0, 0.9, 2.2, 2.8, 4.2),
}

FOLD_BY_TRAJECTORY = {"traj-a": 0, "traj-b": 1, "traj-c": 2}


def _three_fold_fixture():
    contexts = []
    for trajectory_id, fold in FOLD_BY_TRAJECTORY.items():
        contexts.extend(
            build_trajectory_contexts(
                trajectory_id=trajectory_id,
                layout_id=f"layout-{trajectory_id[-1]}",
                fold=fold,
                visible_positions=VISIBLE_BY_TRAJECTORY[trajectory_id],
                dt=DT,
                hidden_taus=(1.0, 2.0),
            )
        )
    return contexts, dict(VISIBLE_BY_TRAJECTORY)


# --------------------------------------------------------------------------
# Fold assignment integrity
# --------------------------------------------------------------------------


def test_conflicting_fold_assignment_is_rejected_inside_the_function():
    contexts, visible = _three_fold_fixture()
    conflicting = list(contexts)
    conflicting[0] = replace(conflicting[0], fold=97)

    with pytest.raises(VisibleHistoryQError, match="conflicting fold"):
        fit_predict_visible_history_q(conflicting, visible, dt_seconds=DT)


def test_duplicated_rows_agreeing_on_fold_are_accepted():
    """A repeated row is not a fold conflict -- only a *disagreement* is."""

    contexts, visible = _three_fold_fixture()
    duplicated = list(contexts) + [contexts[0], contexts[1]]

    rows = fit_predict_visible_history_q(duplicated, visible, dt_seconds=DT)
    assert len(rows) == 2 * len(duplicated)


def test_a_trajectory_appearing_in_every_fold_is_rejected():
    contexts, visible = _three_fold_fixture()
    spanning = [replace(ctx, trajectory_id="traj-a") for ctx in contexts]

    with pytest.raises(VisibleHistoryQError, match="conflicting fold"):
        fit_predict_visible_history_q(
            spanning, {"traj-a": VISIBLE_BY_TRAJECTORY["traj-a"]}, dt_seconds=DT
        )


def test_visible_history_for_an_unassigned_trajectory_is_rejected():
    """A trajectory with no authoritative fold cannot be pooled anywhere."""

    contexts, visible = _three_fold_fixture()
    visible["traj-orphan"] = (0.0, 1.0, 2.1, 2.9)

    with pytest.raises(VisibleHistoryQError, match="no fold assignment"):
        fit_predict_visible_history_q(contexts, visible, dt_seconds=DT)


# --------------------------------------------------------------------------
# Train / test separation
# --------------------------------------------------------------------------


def test_q_hat_for_a_fold_never_sees_that_folds_own_trajectories():
    contexts, visible = _three_fold_fixture()
    rows = fit_predict_visible_history_q(contexts, visible, dt_seconds=DT)

    for row in rows:
        if row.target_name != "log_sigma_oracle":
            continue
        fit_ids = set(row.fit_metadata["fit_trajectory_ids"])
        held_out_ids = {
            trajectory_id
            for trajectory_id, fold in FOLD_BY_TRAJECTORY.items()
            if fold == row.fold
        }
        assert fit_ids.isdisjoint(held_out_ids), (
            f"fold {row.fold} was fit on its own held-out trajectories: "
            f"{sorted(fit_ids & held_out_ids)}"
        )


def test_changing_only_a_held_out_trajectorys_visible_history_leaves_it_unchanged():
    """Perturbing fold 0's own history must not move fold 0's prediction."""

    contexts, visible = _three_fold_fixture()
    baseline_rows = fit_predict_visible_history_q(contexts, visible, dt_seconds=DT)

    perturbed = dict(visible)
    perturbed["traj-a"] = (0.0, 5.0, 1.0, 9.0, 2.0)  # wildly different, fold 0 only
    perturbed_rows = fit_predict_visible_history_q(contexts, perturbed, dt_seconds=DT)

    def fold_zero_predictions(rows):
        return [
            row.prediction
            for row in rows
            if row.fold == 0 and row.target_name == "log_sigma_oracle"
        ]

    assert fold_zero_predictions(baseline_rows) == fold_zero_predictions(perturbed_rows)
    # And a *training* fold's history genuinely does move it, so the test
    # above is asserting isolation rather than an inert estimator.
    other = dict(visible)
    other["traj-b"] = (0.0, 9.0, 1.0, 12.0, 2.0)
    other_rows = fit_predict_visible_history_q(contexts, other, dt_seconds=DT)
    assert fold_zero_predictions(baseline_rows) != fold_zero_predictions(other_rows)


# --------------------------------------------------------------------------
# Privileged-input exclusion
# --------------------------------------------------------------------------


def test_hidden_q_perturbation_with_unchanged_visible_history_changes_nothing():
    contexts, visible = _three_fold_fixture()
    clean = fit_predict_visible_history_q(contexts, visible, dt_seconds=DT)

    for scripted_q in (0.0, 0.02, 0.2, 999.0):
        poisoned = [
            replace(
                ctx,
                q_scripted_blocks2_per_s=scripted_q,
                v_scripted_blocks_per_s=scripted_q * 10.0,
            )
            for ctx in contexts
        ]
        tainted = fit_predict_visible_history_q(poisoned, visible, dt_seconds=DT)
        assert [row.prediction for row in tainted] == [row.prediction for row in clean]
        assert [
            row.fit_metadata.get("q_hat") for row in tainted
        ] == [row.fit_metadata.get("q_hat") for row in clean]


# --------------------------------------------------------------------------
# Insufficient history and NA preservation
# --------------------------------------------------------------------------


def test_insufficient_legal_history_yields_na_never_zero():
    short = build_trajectory_contexts(
        trajectory_id="traj-short",
        layout_id="layout-short",
        fold=0,
        visible_positions=(0.0, 1.0),
        dt=DT,
        hidden_taus=(1.0,),
    )
    other = build_trajectory_contexts(
        trajectory_id="traj-other",
        layout_id="layout-other",
        fold=1,
        visible_positions=(0.0, 1.0),
        dt=DT,
        hidden_taus=(1.0,),
    )
    rows = fit_predict_visible_history_q(
        short + other,
        {"traj-short": (0.0, 1.0), "traj-other": (0.0, 1.0)},
        dt_seconds=DT,
    )
    log_sigma = [row for row in rows if row.target_name == "log_sigma_oracle"]
    assert log_sigma
    for row in log_sigma:
        assert row.applicable is False
        assert row.prediction is None  # never 0.0
        assert row.fit_metadata["reason"]


def test_mu_oracle_blocks_is_always_non_applicable_with_a_reason():
    contexts, visible = _three_fold_fixture()
    rows = fit_predict_visible_history_q(contexts, visible, dt_seconds=DT)
    mu_rows = [row for row in rows if row.target_name == "mu_oracle_blocks"]
    assert mu_rows
    for row in mu_rows:
        assert row.applicable is False
        assert row.prediction is None
        assert "no positional information" in str(row.fit_metadata["reason"])


# --------------------------------------------------------------------------
# Determinism and recorded provenance
# --------------------------------------------------------------------------


def test_fit_is_deterministic_across_repeated_calls():
    contexts, visible = _three_fold_fixture()
    first = fit_predict_visible_history_q(contexts, visible, dt_seconds=DT)
    second = fit_predict_visible_history_q(contexts, visible, dt_seconds=DT)
    assert [row.prediction for row in first] == [row.prediction for row in second]
    assert [dict(row.fit_metadata) for row in first] == [
        dict(row.fit_metadata) for row in second
    ]


def test_fit_is_unchanged_by_reordered_input_rows():
    contexts, visible = _three_fold_fixture()
    forward = fit_predict_visible_history_q(contexts, visible, dt_seconds=DT)
    backward = fit_predict_visible_history_q(list(reversed(contexts)), visible, dt_seconds=DT)

    def keyed(rows):
        return {
            (row.trajectory_id, row.model_frame_idx, row.target_name): row.prediction
            for row in rows
        }

    assert keyed(forward) == keyed(backward)


def test_every_row_records_fit_rows_fold_feature_and_estimator_identity():
    contexts, visible = _three_fold_fixture()
    rows = fit_predict_visible_history_q(contexts, visible, dt_seconds=DT)

    for row in rows:
        if row.target_name != "log_sigma_oracle":
            continue
        metadata = row.fit_metadata
        assert metadata["estimator_id"] == ESTIMATOR_ID
        assert metadata["feature_id"] == FEATURE_ID
        assert metadata["held_out_fold"] == row.fold
        assert metadata["dt_seconds"] == DT
        assert isinstance(metadata["fit_row_count"], int)
        assert metadata["fit_row_count"] >= 0
        if row.applicable:
            assert metadata["fit_row_count"] >= 2
            assert math.isfinite(row.prediction)
