"""Tests for the grouped-shuffle null floor, in particular explicit
donor frame-identity alignment (PDF Step 2.1 remaining gap)."""

from __future__ import annotations

from mineocclude.baselines.interface import TrajectoryContext
from mineocclude.baselines.shuffled import apply_grouped_shuffle, make_shuffle_permutation


def _context(trajectory_id: str, layout_id: str, model_frame_idx: int, fold: int) -> TrajectoryContext:
    return TrajectoryContext(
        trajectory_id=trajectory_id,
        layout_id=layout_id,
        model_frame_idx=model_frame_idx,
        fold=fold,
        regime="A",
        tau_seconds=0.0,
        visibility=True,
        last_seen_position_blocks=float(model_frame_idx),
        last_seen_velocity_blocks_per_s=None,
        v_scripted_blocks_per_s=None,
        q_scripted_blocks2_per_s=None,
        duration_seconds=None,
        config_hash="cfg-test",
        seed=1,
    )


def test_make_shuffle_permutation_is_a_derangement():
    permutation = make_shuffle_permutation(["a", "b", "c"], seed=1)
    for trajectory_id, donor_id in permutation.items():
        assert donor_id != trajectory_id


def test_apply_grouped_shuffle_aligns_by_explicit_frame_index_not_position():
    # traj-recipient has frames 0,1,2,3. Its donor (traj-donor, forced
    # via a hand-picked seed check below) is MISSING frame 1 -- if
    # alignment used list position instead of explicit model_frame_idx,
    # recipient frame 2 (3rd item in the list) would incorrectly
    # receive donor's 3rd remaining value (donor frame 3) instead of
    # correctly finding no donor value at frame 2.
    recipient_contexts = [_context("traj-recipient", "layout-r", i, fold=0) for i in range(4)]
    donor_contexts = [_context("traj-donor", "layout-d", i, fold=1) for i in (0, 2, 3)]  # missing 1
    contexts = recipient_contexts + donor_contexts

    trajectory_targets = {
        "traj-recipient": {"mu_oracle_blocks": {0: 10.0, 1: 11.0, 2: 12.0, 3: 13.0}},
        "traj-donor": {"mu_oracle_blocks": {0: 100.0, 2: 102.0, 3: 103.0}},  # no key 1
    }

    # Find a seed where traj-recipient's donor is traj-donor (only two
    # trajectories exist, so any valid derangement pairs them).
    seed = 7
    permutation = make_shuffle_permutation(["traj-recipient", "traj-donor"], seed=seed)
    assert permutation["traj-recipient"] == "traj-donor"

    rows = apply_grouped_shuffle(contexts, trajectory_targets, seed=seed)
    mu_rows_by_frame = {
        row.model_frame_idx: row
        for row in rows
        if row.trajectory_id == "traj-recipient" and row.target_name == "mu_oracle_blocks"
    }

    assert mu_rows_by_frame[0].applicable and mu_rows_by_frame[0].prediction == 100.0
    assert mu_rows_by_frame[2].applicable and mu_rows_by_frame[2].prediction == 102.0
    assert mu_rows_by_frame[3].applicable and mu_rows_by_frame[3].prediction == 103.0
    # Frame 1: donor has no value at explicit frame index 1 -- must be
    # not applicable, never silently filled from a neighboring frame.
    assert not mu_rows_by_frame[1].applicable
    assert mu_rows_by_frame[1].prediction is None


def test_apply_grouped_shuffle_marks_missing_donor_target_not_applicable():
    contexts = [_context("traj-a", "layout-a", 0, fold=0), _context("traj-b", "layout-b", 0, fold=1)]
    trajectory_targets = {"traj-a": {}, "traj-b": {}}
    rows = apply_grouped_shuffle(contexts, trajectory_targets, seed=3)
    assert all(not row.applicable and row.prediction is None for row in rows)
