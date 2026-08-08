"""Tests for the consolidated missingness/exclusion audit (Step 4.5)."""

from __future__ import annotations

from dataclasses import replace

from mineocclude.baselines.constant_velocity import predict_constant_velocity
from mineocclude.baselines.explicit_feature import fit_predict_explicit_feature
from mineocclude.baselines.known_q_analytic import predict_known_q_analytic
from mineocclude.baselines.last_seen import predict_last_seen
from mineocclude.baselines.missingness import build_missingness_exclusion_report
from mineocclude.baselines.shuffled import apply_grouped_shuffle
from mineocclude.baselines.time_only import fit_predict_time_only
from mineocclude.baselines.visible_history_q import fit_predict_visible_history_q
from tests.baselines.conftest import build_trajectory_contexts


def test_build_missingness_exclusion_report_tabulates_by_condition():
    contexts = build_trajectory_contexts(
        trajectory_id="traj-0",
        layout_id="layout-0",
        fold=0,
        visible_positions=(0.0, 1.0, 2.0),
        dt=1.0,
        hidden_taus=(1.0, 2.0),
    )
    rows = predict_last_seen(contexts)
    report = build_missingness_exclusion_report(rows)

    assert report.cells
    for cell in report.cells:
        assert cell.accepted_count + cell.missing_count > 0
    # last_seen's log_sigma is always non-applicable and always carries
    # a reason -- this baseline alone must never trip the silent check.
    assert not report.has_silent_missingness


def test_build_missingness_exclusion_report_flags_a_silent_exclusion():
    contexts = build_trajectory_contexts(
        trajectory_id="traj-0",
        layout_id="layout-0",
        fold=0,
        visible_positions=(0.0, 1.0),
        dt=1.0,
        hidden_taus=(1.0,),
    )
    rows = predict_last_seen(contexts)
    # Simulate a buggy baseline: non-applicable but with an empty
    # fit_metadata (no reason) -- must be caught, not silently ignored.
    buggy_row = replace(rows[0], applicable=False, prediction=None, fit_metadata={})
    report = build_missingness_exclusion_report([buggy_row])

    assert report.has_silent_missingness
    assert report.rows_missing_reason_code[0][0] == buggy_row.baseline_name


def test_no_silent_missingness_across_every_real_d_baseline():
    # End-to-end self-check: run every fitted/closed-form baseline over
    # a small multi-layout, multi-fold synthetic set and confirm none
    # of them ever produce a non-applicable row without a reason code.
    layouts = {
        "layout-a": (0.0, 1.0, 2.0),
        "layout-b": (0.0, 2.0, 4.0),
        "layout-c": (0.0, 1.5, 3.0),
        "layout-d": (0.0, 0.5, 1.0),
    }
    contexts = []
    mu_oracle_by_key = {}
    train_log_sigma = {}
    visible_positions_by_trajectory = {}
    for fold, (layout_id, positions) in enumerate(layouts.items()):
        ctx_list = build_trajectory_contexts(
            trajectory_id=f"traj-{layout_id}",
            layout_id=layout_id,
            fold=fold % 2,
            visible_positions=positions,
            dt=1.0,
            hidden_taus=(1.0, 2.0),
            duration_seconds=2.0,
        )
        contexts.extend(ctx_list)
        velocity = ctx_list[-1].last_seen_velocity_blocks_per_s
        last_seen = ctx_list[-1].last_seen_position_blocks
        visible_positions_by_trajectory[f"traj-{layout_id}"] = positions
        for ctx in ctx_list:
            key = (ctx.trajectory_id, ctx.model_frame_idx)
            mu_oracle_by_key[key] = last_seen + velocity * ctx.tau_seconds
            train_log_sigma[key] = 0.1 * ctx.tau_seconds + 0.01

    all_rows = []
    all_rows += predict_last_seen(contexts)
    all_rows += predict_constant_velocity(contexts)
    all_rows += fit_predict_time_only(contexts, train_log_sigma, degree=1)
    all_rows += fit_predict_explicit_feature(
        contexts, mu_oracle_by_key, alpha_grid=(1.0,), inner_fold_count=2
    )
    all_rows += fit_predict_visible_history_q(
        contexts, visible_positions_by_trajectory, dt_seconds=1.0
    )
    all_rows += predict_known_q_analytic(contexts)

    trajectory_targets = {
        f"traj-{layout_id}": {
            "mu_oracle_blocks": {
                idx: mu_oracle_by_key[(f"traj-{layout_id}", idx)]
                for idx in range(len(positions) + 2)
                if (f"traj-{layout_id}", idx) in mu_oracle_by_key
            }
        }
        for layout_id, positions in layouts.items()
    }
    all_rows += apply_grouped_shuffle(contexts, trajectory_targets, seed=20260719)

    report = build_missingness_exclusion_report(all_rows)
    assert not report.has_silent_missingness, report.rows_missing_reason_code
