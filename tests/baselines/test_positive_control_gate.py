"""Tests for the Step 4.3 no-wall positive-control statistical gate.

Roadmap Step 4.3 was marked COMPLETE with only its structural half built
(``controls.audit_no_wall_control``). These tests validate the missing
scientific half: fit the frozen visible-position ridge via Person B's
real ``probes.ridge``/``metrics.u1_mean``/``metrics.resampling``
authorities and report PASSED/FAILED/BLOCKED. Real no-wall rows, a real
B fold manifest, and real oracle targets do not exist yet, so every
scenario here uses the same synthetic fixtures the rest of Phase 4 was
evidenced with (``tests/fixtures/person_d/synthetic_b_fold_manifest.json``);
none of this is a scientific claim about the actual pipeline.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from mineocclude.baselines.positive_control_gate import (
    REAL_NO_WALL_DATA_PROVENANCE,
    STEP_4_3_R2_THRESHOLD,
    PositiveControlGateError,
    evaluate_no_wall_positive_control_gate,
)
from tests.baselines.conftest import build_trajectory_contexts

FOLD_FIXTURE_PATH = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "person_d"
    / "synthetic_b_fold_manifest.json"
)

#: The fixture's 5 layouts/folds, each with exactly one 3-frame
#: always-visible (no-wall) trajectory.
LAYOUTS = tuple("abcde")


def _fold_manifest():
    return json.loads(FOLD_FIXTURE_PATH.read_text(encoding="utf-8"))


def _no_wall_contexts_and_targets(targets_by_layout):
    """Build all-visible (no-wall) contexts across the fixture's 5 layouts.

    ``fold=-1`` (UNASSIGNED) on every context: fold membership is
    attached inside the gate itself, from the real B fold manifest,
    never invented here.
    """

    contexts = []
    mu_oracle_by_key = {}
    for layout in LAYOUTS:
        positions = (0.0, 1.0, 2.0)
        ctx_list = build_trajectory_contexts(
            trajectory_id=f"traj-{layout}",
            layout_id=f"layout-{layout}",
            fold=-1,
            visible_positions=positions,
            dt=1.0,
            hidden_taus=(),  # no hidden frames at all: this is the no-wall control
        )
        contexts.extend(ctx_list)
        for ctx, target in zip(ctx_list, targets_by_layout[layout]):
            mu_oracle_by_key[(ctx.trajectory_id, ctx.model_frame_idx)] = target
    return contexts, mu_oracle_by_key


def test_blocked_when_data_provenance_is_not_the_real_literal():
    # This is the central fail-closed contract: no matter how good the
    # numbers look, anything other than the exact real-data literal
    # must report BLOCKED, not PASSED, and must not compute a real R^2.
    contexts, mu_oracle_by_key = _no_wall_contexts_and_targets(
        {layout: (0.0, 1.0, 2.0) for layout in LAYOUTS}  # perfect signal
    )
    finding = evaluate_no_wall_positive_control_gate(
        contexts,
        mu_oracle_by_key,
        fold_manifest=_fold_manifest(),
        data_provenance="synthetic_fixture_demo",
    )
    assert finding.status == "BLOCKED"
    assert finding.r2 is None
    assert finding.ci_low is None
    assert finding.ci_high is None
    assert finding.fold_count is None
    assert finding.resample_count is None
    assert finding.data_provenance == "synthetic_fixture_demo"
    assert "BLOCKED" not in {"PASSED", "FAILED"}  # sanity: status is its own value
    assert finding.status not in {"PASSED", "FAILED"}


def test_blocked_regardless_of_how_perfect_the_underlying_signal_is():
    # Even a target that is *exactly* the visible position (as clean a
    # signal as exists) must still not unlock PASSED without the real
    # data_provenance literal -- proves the block isn't just "bad data
    # numerically fails," it's an unconditional gate on provenance.
    contexts, mu_oracle_by_key = _no_wall_contexts_and_targets(
        {layout: (0.0, 1.0, 2.0) for layout in LAYOUTS}
    )
    finding = evaluate_no_wall_positive_control_gate(
        contexts,
        mu_oracle_by_key,
        fold_manifest=_fold_manifest(),
        data_provenance="not_real_data",
    )
    assert finding.status == "BLOCKED"


def test_clean_pass_on_real_declared_synthetic_signal():
    # data_provenance is intentionally set to the real literal here to
    # exercise the PASSED arithmetic branch -- this is a controlled
    # unit test of the ridge/R^2/bootstrap math, not a scientific claim
    # (no real no-wall capture exists yet); see module docstring.
    contexts, mu_oracle_by_key = _no_wall_contexts_and_targets(
        {layout: (0.0, 1.0, 2.0) for layout in LAYOUTS}
    )
    finding = evaluate_no_wall_positive_control_gate(
        contexts,
        mu_oracle_by_key,
        fold_manifest=_fold_manifest(),
        data_provenance=REAL_NO_WALL_DATA_PROVENANCE,
    )
    assert finding.status == "PASSED"
    assert finding.r2 >= STEP_4_3_R2_THRESHOLD
    assert finding.ci_low > 0.0
    assert finding.n_rows == 15
    assert finding.fold_count == 5
    assert finding.resample_count == 1000
    assert finding.seed == 20260721


def test_sub_threshold_r2_failure():
    # Targets are essentially unrelated to the visible position across
    # every layout: held-out R^2 should land well below 0.50.
    targets_by_layout = {
        "a": (3.0, -2.0, 5.0),
        "b": (-4.0, 6.0, -1.0),
        "c": (2.0, -5.0, 4.0),
        "d": (-3.0, 1.0, -6.0),
        "e": (5.0, -4.0, 2.0),
    }
    contexts, mu_oracle_by_key = _no_wall_contexts_and_targets(targets_by_layout)
    finding = evaluate_no_wall_positive_control_gate(
        contexts,
        mu_oracle_by_key,
        fold_manifest=_fold_manifest(),
        data_provenance=REAL_NO_WALL_DATA_PROVENANCE,
    )
    assert finding.status == "FAILED"
    assert finding.r2 < STEP_4_3_R2_THRESHOLD


def test_ci_straddling_zero_failure_despite_r2_above_threshold():
    # Hand-calibrated so the point-estimate R^2 clears 0.50 but the
    # hierarchical bootstrap CI still straddles zero -- confirms the
    # gate fails on the CI condition even when R^2 alone would pass.
    targets_by_layout = {
        "a": (1.61, 1.06, 2.73),
        "b": (-1.02, 1.50, 3.66),
        "c": (0.21, 1.12, 1.86),
        "d": (-2.00, 2.61, 3.30),
        "e": (-1.06, 0.87, 2.23),
    }
    contexts, mu_oracle_by_key = _no_wall_contexts_and_targets(targets_by_layout)
    finding = evaluate_no_wall_positive_control_gate(
        contexts,
        mu_oracle_by_key,
        fold_manifest=_fold_manifest(),
        data_provenance=REAL_NO_WALL_DATA_PROVENANCE,
    )
    assert finding.r2 >= STEP_4_3_R2_THRESHOLD, (
        "this scenario is calibrated so the point estimate clears the "
        "threshold; if this fails, the fixture needs recalibrating, not "
        "the gate's pass condition"
    )
    assert finding.ci_low <= 0.0
    assert finding.status == "FAILED"


def test_rejects_a_no_wall_structural_audit_failure():
    # If the underlying data isn't even a valid no-wall trajectory
    # (some frame is occluded), this is an engineering-input error, not
    # a scientific PASSED/FAILED/BLOCKED verdict.
    contexts, mu_oracle_by_key = _no_wall_contexts_and_targets(
        {layout: (0.0, 1.0, 2.0) for layout in LAYOUTS}
    )
    broken_contexts = list(contexts)
    broken_contexts[0] = replace(broken_contexts[0], visibility=False, tau_seconds=0.5)

    with pytest.raises(PositiveControlGateError, match="structural audit failed"):
        evaluate_no_wall_positive_control_gate(
            broken_contexts,
            mu_oracle_by_key,
            fold_manifest=_fold_manifest(),
            data_provenance=REAL_NO_WALL_DATA_PROVENANCE,
        )


def test_rejects_empty_contexts():
    with pytest.raises(PositiveControlGateError, match="no no-wall contexts"):
        evaluate_no_wall_positive_control_gate(
            [],
            {},
            fold_manifest=_fold_manifest(),
            data_provenance=REAL_NO_WALL_DATA_PROVENANCE,
        )


def test_rejects_a_missing_oracle_target():
    contexts, mu_oracle_by_key = _no_wall_contexts_and_targets(
        {layout: (0.0, 1.0, 2.0) for layout in LAYOUTS}
    )
    incomplete_targets = dict(mu_oracle_by_key)
    del incomplete_targets[("traj-a", 0)]

    with pytest.raises(PositiveControlGateError, match="missing real oracle mu target"):
        evaluate_no_wall_positive_control_gate(
            contexts,
            incomplete_targets,
            fold_manifest=_fold_manifest(),
            data_provenance=REAL_NO_WALL_DATA_PROVENANCE,
        )


def test_rejects_an_invalid_fold_manifest():
    contexts, mu_oracle_by_key = _no_wall_contexts_and_targets(
        {layout: (0.0, 1.0, 2.0) for layout in LAYOUTS}
    )
    broken_manifest = _fold_manifest()
    broken_manifest.pop("artifact_hash")  # breaks the seal, not a valid B artifact

    with pytest.raises(PositiveControlGateError, match="fold manifest"):
        evaluate_no_wall_positive_control_gate(
            contexts,
            mu_oracle_by_key,
            fold_manifest=broken_manifest,
            data_provenance=REAL_NO_WALL_DATA_PROVENANCE,
        )


def test_never_fabricates_a_prediction_when_blocked():
    # Belt-and-suspenders check on the module's central invariant: a
    # BLOCKED finding must carry no numeric fields at all, matching the
    # project-wide rule that a non-scientific result is never presented
    # as a numeric fact.
    contexts, mu_oracle_by_key = _no_wall_contexts_and_targets(
        {layout: (0.0, 1.0, 2.0) for layout in LAYOUTS}
    )
    finding = evaluate_no_wall_positive_control_gate(
        contexts,
        mu_oracle_by_key,
        fold_manifest=_fold_manifest(),
        data_provenance="whatever_someone_typed",
    )
    assert finding.r2 is None
    assert finding.ci_low is None
    assert finding.ci_high is None
