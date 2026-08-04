"""Tests for the no-wall/occluder-only control audits."""

from __future__ import annotations

from dataclasses import replace

from mineocclude.baselines.constant_velocity import predict_constant_velocity
from mineocclude.baselines.controls import (
    audit_no_wall_control,
    audit_occluder_only_control,
)
from mineocclude.baselines.last_seen import predict_last_seen
from mineocclude.baselines.interface import TrajectoryContext


def _no_wall_contexts() -> list[TrajectoryContext]:
    return [
        TrajectoryContext(
            trajectory_id="traj-no-wall",
            layout_id="layout-0",
            model_frame_idx=i,
            fold=0,
            regime="A",
            tau_seconds=0.0,
            visibility=True,
            last_seen_position_blocks=float(i),
            last_seen_velocity_blocks_per_s=1.0 if i > 0 else None,
            v_scripted_blocks_per_s=1.0,
            q_scripted_blocks2_per_s=0.02,
            duration_seconds=None,
            config_hash="cfg-test",
            seed=1,
        )
        for i in range(4)
    ]


def _occluder_only_contexts() -> list[TrajectoryContext]:
    return [
        TrajectoryContext(
            trajectory_id="traj-occluder-only",
            layout_id="layout-0",
            model_frame_idx=i,
            fold=0,
            regime="A",
            tau_seconds=float(i) * 0.05,
            visibility=False,
            last_seen_position_blocks=None,
            last_seen_velocity_blocks_per_s=None,
            v_scripted_blocks_per_s=1.0,
            q_scripted_blocks2_per_s=0.02,
            duration_seconds=None,
            config_hash="cfg-test",
            seed=1,
        )
        for i in range(4)
    ]


def test_audit_no_wall_control_passes_when_always_visible():
    finding = audit_no_wall_control(_no_wall_contexts())
    assert finding.passed


def test_audit_no_wall_control_fails_on_contaminated_data():
    contexts = _no_wall_contexts()
    contaminated = [replace(contexts[0], visibility=False, tau_seconds=0.5)] + contexts[1:]
    finding = audit_no_wall_control(contaminated)
    assert not finding.passed
    assert "1 of 4" in finding.detail


def test_audit_no_wall_control_requires_nonempty_contexts():
    finding = audit_no_wall_control([])
    assert not finding.passed


def test_audit_occluder_only_control_passes_with_clean_baselines():
    contexts = _occluder_only_contexts()
    rows = predict_last_seen(contexts) + predict_constant_velocity(contexts)
    finding = audit_occluder_only_control(contexts, rows)
    assert finding.passed


def test_audit_occluder_only_control_catches_contaminated_context_data():
    contexts = _occluder_only_contexts()
    contaminated = [replace(contexts[0], last_seen_position_blocks=2.0)] + contexts[1:]
    finding = audit_occluder_only_control(contaminated, [])
    assert not finding.passed
    assert "contaminated" in finding.detail


def test_audit_occluder_only_control_catches_a_leaking_baseline():
    contexts = _occluder_only_contexts()
    honest_rows = predict_last_seen(contexts)
    # Simulate a buggy baseline that hallucinated a position on a
    # no-object frame -- the audit must flag this as a control failure.
    leaking_row = replace(
        honest_rows[0], applicable=True, prediction=3.0, baseline_name="buggy_baseline"
    )
    finding = audit_occluder_only_control(contexts, [leaking_row])
    assert not finding.passed
    assert "buggy_baseline" in finding.detail
