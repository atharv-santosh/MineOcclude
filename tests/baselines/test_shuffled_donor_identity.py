"""Explicit donor-identity tests for the grouped shuffled-label floor.

Execution manual Step 2.1 requires the floor to identify every donor by
a *stable trajectory/frame identity* rather than by a row's position
inside a locally ordered list, and to fail closed on a duplicate,
missing, ambiguous, or illegal donor. These tests exercise exactly
those properties; the frame-alignment behavior itself is covered in
``test_shuffled.py``.

Nothing here reads real capture data: every trajectory is a small,
hand-built :class:`TrajectoryContext` sequence.
"""

from __future__ import annotations

import pytest

from mineocclude.baselines.interface import TrajectoryContext
from mineocclude.baselines.shuffled import (
    GroupedShuffleError,
    apply_grouped_shuffle,
    build_donor_assignments,
    make_shuffle_permutation,
)

SEED = 20260806


def _context(
    trajectory_id: str,
    layout_id: str,
    model_frame_idx: int,
    fold: int,
) -> TrajectoryContext:
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


def _four_trajectory_fixture(frame_counts=(3, 3, 3, 3)):
    """Four trajectories, one per layout/fold group, uneven lengths allowed."""

    contexts: list[TrajectoryContext] = []
    targets: dict[str, dict[str, dict[int, float]]] = {}
    for index, frame_count in enumerate(frame_counts):
        trajectory_id = f"traj-{index}"
        layout_id = f"layout-{index}"
        contexts.extend(
            _context(trajectory_id, layout_id, frame_idx, fold=index)
            for frame_idx in range(frame_count)
        )
        targets[trajectory_id] = {
            "mu_oracle_blocks": {
                frame_idx: 100.0 * index + frame_idx for frame_idx in range(frame_count)
            },
            "log_sigma_oracle": {
                frame_idx: -1.0 * index - frame_idx for frame_idx in range(frame_count)
            },
        }
    return contexts, targets


# --------------------------------------------------------------------------
# Repeatability and input-order independence
# --------------------------------------------------------------------------


def test_donor_mapping_is_repeatable_for_the_same_seed_and_inputs():
    contexts, targets = _four_trajectory_fixture()
    first = build_donor_assignments(contexts, targets, SEED)
    second = build_donor_assignments(contexts, targets, SEED)
    assert first == second


def test_donor_mapping_is_unchanged_by_reordered_input_rows():
    contexts, targets = _four_trajectory_fixture()
    reference = build_donor_assignments(contexts, targets, SEED)
    reversed_rows = build_donor_assignments(list(reversed(contexts)), targets, SEED)
    interleaved = build_donor_assignments(
        sorted(contexts, key=lambda ctx: (ctx.model_frame_idx, ctx.trajectory_id)),
        targets,
        SEED,
    )
    assert reversed_rows == reference
    assert interleaved == reference


def test_predictions_are_byte_stable_across_reordered_input_rows():
    contexts, targets = _four_trajectory_fixture()

    def by_identity(rows):
        return {
            (row.trajectory_id, row.model_frame_idx, row.target_name): (
                row.prediction,
                row.applicable,
                row.fit_metadata["donor_trajectory_id"],
                row.fit_metadata["donor_model_frame_idx"],
            )
            for row in rows
        }

    forward = by_identity(apply_grouped_shuffle(contexts, targets, SEED))
    backward = by_identity(apply_grouped_shuffle(list(reversed(contexts)), targets, SEED))
    assert forward == backward


def test_a_different_seed_produces_a_different_mapping():
    contexts, targets = _four_trajectory_fixture()
    mappings = {
        seed: tuple(
            (recipient, assignment.donor_trajectory_id)
            for recipient, assignment in sorted(
                build_donor_assignments(contexts, targets, seed).items()
            )
        )
        for seed in (1, 2, 3, 4, 5)
    }
    assert len(set(mappings.values())) > 1


# --------------------------------------------------------------------------
# Derangement, bijection, and eligibility
# --------------------------------------------------------------------------


def test_no_trajectory_is_ever_its_own_donor():
    contexts, targets = _four_trajectory_fixture()
    for seed in range(25):
        for recipient, assignment in build_donor_assignments(contexts, targets, seed).items():
            assert assignment.donor_trajectory_id != recipient


def test_every_donor_is_consumed_exactly_once():
    contexts, targets = _four_trajectory_fixture()
    assignments = build_donor_assignments(contexts, targets, SEED)
    donors = [a.donor_trajectory_id for a in assignments.values()]
    assert sorted(donors) == sorted(assignments)


def test_a_single_trajectory_cannot_form_a_derangement():
    with pytest.raises(ValueError, match="at least two distinct trajectories"):
        make_shuffle_permutation(["only-one"], seed=SEED)


def test_donor_without_a_declared_target_entry_is_rejected():
    contexts, targets = _four_trajectory_fixture()
    # A trajectory that is requested but carries no target entry at all is
    # *missing*, not empty -- borrowing from it would silently turn every
    # recipient row into a bare non-applicable with no upstream signal.
    del targets["traj-2"]
    with pytest.raises(GroupedShuffleError, match="has no target entry"):
        build_donor_assignments(contexts, targets, SEED)


def test_cross_group_donor_enforcement_rejects_a_within_group_donor():
    # Both trajectories live in the same layout/fold group, so the only
    # possible derangement is within-group and must be rejected when the
    # frozen specification requires cross-group donors.
    contexts = [
        _context("traj-a", "layout-0", frame_idx, fold=0) for frame_idx in range(3)
    ] + [_context("traj-b", "layout-0", frame_idx, fold=0) for frame_idx in range(3)]
    targets = {
        "traj-a": {"mu_oracle_blocks": {0: 1.0, 1: 2.0, 2: 3.0}},
        "traj-b": {"mu_oracle_blocks": {0: 4.0, 1: 5.0, 2: 6.0}},
    }
    with pytest.raises(GroupedShuffleError, match="from its own group"):
        build_donor_assignments(contexts, targets, SEED, require_cross_group_donors=True)
    # Without the stricter flag the same inputs are accepted, so the rule is
    # an explicit caller decision rather than a silent default.
    assert build_donor_assignments(contexts, targets, SEED)


# --------------------------------------------------------------------------
# Group integrity and frame identity
# --------------------------------------------------------------------------


def test_conflicting_group_identity_for_one_trajectory_is_rejected():
    contexts = [
        _context("traj-a", "layout-0", 0, fold=0),
        _context("traj-a", "layout-1", 1, fold=0),  # same trajectory, other layout
        _context("traj-b", "layout-2", 0, fold=1),
    ]
    targets = {"traj-a": {}, "traj-b": {}}
    with pytest.raises(GroupedShuffleError, match="conflicting grouping identity"):
        apply_grouped_shuffle(contexts, targets, SEED)


def test_conflicting_fold_for_one_trajectory_is_rejected():
    contexts = [
        _context("traj-a", "layout-0", 0, fold=0),
        _context("traj-a", "layout-0", 1, fold=3),  # same trajectory, other fold
        _context("traj-b", "layout-1", 0, fold=1),
    ]
    targets = {"traj-a": {}, "traj-b": {}}
    with pytest.raises(GroupedShuffleError, match="conflicting grouping identity"):
        apply_grouped_shuffle(contexts, targets, SEED)


def test_duplicate_frame_identity_is_rejected():
    contexts = [
        _context("traj-a", "layout-0", 0, fold=0),
        _context("traj-a", "layout-0", 0, fold=0),  # duplicate (trajectory, frame)
        _context("traj-b", "layout-1", 0, fold=1),
    ]
    targets = {"traj-a": {}, "traj-b": {}}
    with pytest.raises(GroupedShuffleError, match="duplicate frame identity"):
        apply_grouped_shuffle(contexts, targets, SEED)


def test_uneven_trajectory_lengths_never_borrow_a_neighboring_frame():
    contexts, targets = _four_trajectory_fixture(frame_counts=(2, 5, 3, 4))
    assignments = build_donor_assignments(contexts, targets, SEED)
    rows = apply_grouped_shuffle(contexts, targets, SEED)

    for row in rows:
        donor_id = assignments[row.trajectory_id].donor_trajectory_id
        donor_values = targets[donor_id][row.target_name]
        assert row.fit_metadata["donor_trajectory_id"] == donor_id
        assert row.fit_metadata["donor_model_frame_idx"] == row.model_frame_idx
        if row.model_frame_idx in donor_values:
            assert row.applicable
            assert row.prediction == donor_values[row.model_frame_idx]
        else:
            # The donor is shorter here: no value at this exact frame index.
            assert not row.applicable
            assert row.prediction is None
            assert row.fit_metadata["reason"]


def test_missing_donor_frame_identity_is_non_applicable_never_zero():
    contexts, targets = _four_trajectory_fixture(frame_counts=(4, 4, 4, 4))
    assignments = build_donor_assignments(contexts, targets, SEED)
    # Punch a hole in one donor's frame identities.
    victim = assignments["traj-0"].donor_trajectory_id
    del targets[victim]["mu_oracle_blocks"][2]

    rows = apply_grouped_shuffle(contexts, targets, SEED)
    holed = [
        row
        for row in rows
        if row.trajectory_id == "traj-0"
        and row.target_name == "mu_oracle_blocks"
        and row.model_frame_idx == 2
    ]
    assert len(holed) == 1
    assert holed[0].applicable is False
    assert holed[0].prediction is None  # never 0.0
    assert holed[0].fit_metadata["reason"]


# --------------------------------------------------------------------------
# Row identity and null behavior
# --------------------------------------------------------------------------


def test_requested_prediction_row_identity_is_preserved_exactly():
    contexts, targets = _four_trajectory_fixture(frame_counts=(2, 3, 2, 3))
    rows = apply_grouped_shuffle(contexts, targets, SEED)
    requested = {
        (ctx.trajectory_id, ctx.model_frame_idx, target)
        for ctx in contexts
        for target in ("mu_oracle_blocks", "log_sigma_oracle")
    }
    emitted = {(row.trajectory_id, row.model_frame_idx, row.target_name) for row in rows}
    assert emitted == requested
    assert len(rows) == len(requested)


def test_every_row_carries_the_full_donor_identity_record():
    contexts, targets = _four_trajectory_fixture()
    rows = apply_grouped_shuffle(contexts, targets, SEED)
    for row in rows:
        metadata = row.fit_metadata
        assert metadata["seed"] == SEED
        assert isinstance(metadata["donor_trajectory_id"], str)
        assert metadata["donor_trajectory_id"] != row.trajectory_id
        assert metadata["donor_model_frame_idx"] == row.model_frame_idx
        assert metadata["recipient_group_key"] == f"{row.layout_id}:fold{row.fold}"
        assert isinstance(metadata["donor_group_key"], str)


def test_synthetic_chance_behavior_predictions_come_only_from_the_donor():
    """The floor must never reproduce a recipient's own target values."""

    contexts, targets = _four_trajectory_fixture(frame_counts=(4, 4, 4, 4))
    assignments = build_donor_assignments(contexts, targets, SEED)
    rows = apply_grouped_shuffle(contexts, targets, SEED)

    for row in rows:
        if not row.applicable:
            continue
        own_value = targets[row.trajectory_id][row.target_name][row.model_frame_idx]
        donor_id = assignments[row.trajectory_id].donor_trajectory_id
        donor_value = targets[donor_id][row.target_name][row.model_frame_idx]
        assert row.prediction == donor_value
        assert row.prediction != own_value
