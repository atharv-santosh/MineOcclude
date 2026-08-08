"""Grouped-shuffle null floor.

Roadmap D2: "Grouped shuffled labels | Original features; permuted
trajectory/layout target association | Chance/null floor while
preserving temporal structure."

We shuffle at the *trajectory* level: every trajectory is assigned a
different "donor" trajectory (a seeded derangement, so no trajectory
is ever paired with itself), and each frame's shuffled target is taken
from the donor trajectory's target value at the *same explicit
model_frame_idx*. This breaks the true feature/target link while
preserving each trajectory's internal temporal ordering, per the
roadmap's explicit requirement -- a plain global row shuffle would
scramble temporal structure and make the floor too weak (an
unrealistically low bar).

Donor alignment is keyed by ``model_frame_idx`` explicitly, not by a
row's position within a locally sorted list. Positional alignment
would silently misalign frames whenever the recipient and donor
trajectories have different excluded/missing-frame patterns (e.g. the
donor is missing frame 2 but the recipient is not) -- the donor's Nth
*remaining* frame is not necessarily model_frame_idx N. Keying by the
explicit frame identity instead means a donor simply has no value for
a frame index it lacks, which correctly falls out as not applicable
rather than a silent off-by-one alignment.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Mapping, Optional, Sequence

import numpy as np

from mineocclude.baselines.interface import (
    TARGET_NAMES,
    BaselineRow,
    TrajectoryContext,
    make_baseline_row,
)

BASELINE_NAME = "grouped_shuffled"


class GroupedShuffleError(ValueError):
    """Raised when donor identity cannot be established unambiguously.

    A grouped-shuffle floor whose donor identity is ambiguous is not a
    weaker floor -- it is an uninterpretable one, because the null it
    represents is no longer the one B declared. Every such condition
    fails closed here rather than resolving to whichever donor row
    happened to be seen first.
    """


@dataclass(frozen=True)
class DonorAssignment:
    """One recipient trajectory's explicit, validated donor identity.

    ``donor_trajectory_id`` is a stable trajectory identity, never a
    position in a list; ``donor_frame_indices`` records the exact
    ``model_frame_idx`` values that donor actually offers per target,
    so the recorded mapping is reproducible and auditable without
    re-running the shuffle.
    """

    recipient_trajectory_id: str
    donor_trajectory_id: str
    recipient_group_key: str
    donor_group_key: str
    seed: int

#: Per-trajectory target values, keyed explicitly by model_frame_idx
#: (never by sequential list position), keyed in turn by target name.
#: A missing model_frame_idx key or a ``None`` value both mean "not
#: applicable at this frame" and must not be treated as zero.
TrajectoryTargets = Mapping[str, Mapping[int, Optional[float]]]


def make_shuffle_permutation(trajectory_ids: Sequence[str], seed: int) -> dict[str, str]:
    """Return a seeded derangement over the distinct trajectory ids.

    A derangement guarantees no trajectory is shuffled against itself
    (that would silently leak the true association back in). Raises if
    fewer than two distinct trajectories are given, or if no
    derangement is found within a bounded number of attempts (only
    possible for n < 2, already excluded).
    """

    unique_ids = sorted(set(trajectory_ids))
    if len(unique_ids) < 2:
        raise ValueError(
            "grouped shuffle requires at least two distinct trajectories, "
            f"got {len(unique_ids)}"
        )

    rng = np.random.default_rng(seed)
    n = len(unique_ids)
    identity = np.arange(n)
    for _ in range(1000):
        perm = rng.permutation(n)
        if np.all(perm != identity):
            return {unique_ids[i]: unique_ids[perm[i]] for i in range(n)}
    raise RuntimeError(
        "failed to find a derangement after 1000 attempts; "
        "this should not happen for n >= 2"
    )


def _group_contexts_by_trajectory(
    contexts: Sequence[TrajectoryContext],
) -> dict[str, list[TrajectoryContext]]:
    """Group contexts by trajectory, rejecting ambiguous row identity.

    Two rows sharing a ``(trajectory_id, model_frame_idx)`` pair are a
    duplicate prediction-row identity: the requested row set would no
    longer have one prediction per requested row, and which duplicate
    "won" would depend on input order. Rows of one trajectory disagreeing
    on ``layout_id`` or ``fold`` are an upstream grouping defect -- B's
    layout-grouped folds mean a trajectory belongs to exactly one layout
    and exactly one fold. Both fail closed.
    """

    grouped: dict[str, list[TrajectoryContext]] = defaultdict(list)
    seen_frames: dict[str, set[int]] = defaultdict(set)
    group_key_by_trajectory: dict[str, tuple[str, int]] = {}

    for ctx in contexts:
        group_key = (ctx.layout_id, ctx.fold)
        existing = group_key_by_trajectory.setdefault(ctx.trajectory_id, group_key)
        if existing != group_key:
            raise GroupedShuffleError(
                f"trajectory {ctx.trajectory_id!r} has conflicting grouping "
                f"identity (layout/fold {existing} vs {group_key}); one "
                "trajectory must belong to exactly one layout and one fold"
            )
        if ctx.model_frame_idx in seen_frames[ctx.trajectory_id]:
            raise GroupedShuffleError(
                f"trajectory {ctx.trajectory_id!r} has a duplicate frame "
                f"identity model_frame_idx={ctx.model_frame_idx}; donor "
                "alignment requires exactly one row per (trajectory, frame)"
            )
        seen_frames[ctx.trajectory_id].add(ctx.model_frame_idx)
        grouped[ctx.trajectory_id].append(ctx)

    return grouped


def build_donor_assignments(
    contexts: Sequence[TrajectoryContext],
    trajectory_targets: Mapping[str, TrajectoryTargets],
    seed: int,
    *,
    require_cross_group_donors: bool = False,
) -> dict[str, DonorAssignment]:
    """Return the validated recipient -> donor identity mapping.

    Exposed separately from :func:`apply_grouped_shuffle` so the mapping
    can be recorded, re-validated, and compared byte-for-byte across
    runs without refitting anything. The mapping is a pure function of
    the *set* of distinct trajectory ids and the seed, so reordering the
    input rows cannot change it.

    ``require_cross_group_donors`` enforces the stricter "donor must come
    from a different (layout, fold) group" rule. It is off by default
    because B's frozen null is declared at trajectory level and a small
    accepted set may not admit any cross-group derangement at all; when
    the frozen specification calls for it, callers turn it on and get a
    hard failure rather than a silently weakened floor.
    """

    grouped = _group_contexts_by_trajectory(contexts)
    group_key_by_trajectory = {
        trajectory_id: f"{ctx_list[0].layout_id}:fold{ctx_list[0].fold}"
        for trajectory_id, ctx_list in grouped.items()
    }

    permutation = make_shuffle_permutation(list(grouped.keys()), seed)

    assignments: dict[str, DonorAssignment] = {}
    for recipient_id in sorted(grouped):
        donor_id = permutation[recipient_id]
        if donor_id == recipient_id:
            raise GroupedShuffleError(
                f"trajectory {recipient_id!r} was assigned itself as donor; a "
                "self-donor leaks the true feature/target association back in"
            )
        if donor_id not in group_key_by_trajectory:
            raise GroupedShuffleError(
                f"trajectory {recipient_id!r} was assigned unknown donor "
                f"{donor_id!r}; every donor must be a known requested trajectory"
            )
        if donor_id not in trajectory_targets:
            raise GroupedShuffleError(
                f"donor {donor_id!r} (for recipient {recipient_id!r}) has no "
                "target entry; a donor with no declared targets is missing, "
                "not empty, and must not be silently treated as all-non-"
                "applicable"
            )
        recipient_group = group_key_by_trajectory[recipient_id]
        donor_group = group_key_by_trajectory[donor_id]
        if require_cross_group_donors and recipient_group == donor_group:
            raise GroupedShuffleError(
                f"trajectory {recipient_id!r} was assigned donor {donor_id!r} "
                f"from its own group {recipient_group!r}; a within-group donor "
                "leaks group structure into the chance floor"
            )
        assignments[recipient_id] = DonorAssignment(
            recipient_trajectory_id=recipient_id,
            donor_trajectory_id=donor_id,
            recipient_group_key=recipient_group,
            donor_group_key=donor_group,
            seed=seed,
        )

    donor_counts: dict[str, int] = defaultdict(int)
    for assignment in assignments.values():
        donor_counts[assignment.donor_trajectory_id] += 1
    reused = sorted(donor_id for donor_id, count in donor_counts.items() if count > 1)
    if reused:
        raise GroupedShuffleError(
            f"donor trajectories {reused} were each assigned to more than one "
            "recipient; a derangement must be a bijection so every donor's "
            "targets are consumed exactly once"
        )

    return assignments


def apply_grouped_shuffle(
    contexts: Sequence[TrajectoryContext],
    trajectory_targets: Mapping[str, TrajectoryTargets],
    seed: int,
    *,
    require_cross_group_donors: bool = False,
) -> list[BaselineRow]:
    """Produce grouped-shuffled predictions for every context.

    Each trajectory in ``contexts`` is assigned a distinct donor
    trajectory via :func:`make_shuffle_permutation`, then validated by
    :func:`build_donor_assignments` before any value is borrowed. Every
    recipient frame receives the donor's target value at that *same
    explicit model_frame_idx* -- never at the same position-in-list,
    since a donor's Nth remaining frame is not necessarily
    model_frame_idx N once either trajectory has excluded/missing frames.
    If the donor has no value recorded for that exact frame index, the
    row is marked not applicable rather than borrowing a neighboring
    frame.

    Every emitted row records the full donor identity it used --
    donor trajectory, donor frame index, both group keys, and the seed --
    so the mapping can be audited after the fact from the rows alone.
    """

    grouped = _group_contexts_by_trajectory(contexts)
    assignments = build_donor_assignments(
        contexts,
        trajectory_targets,
        seed,
        require_cross_group_donors=require_cross_group_donors,
    )

    rows: list[BaselineRow] = []
    for trajectory_id, ctx_list in grouped.items():
        assignment = assignments[trajectory_id]
        donor_id = assignment.donor_trajectory_id
        donor_targets = trajectory_targets.get(donor_id, {})
        for ctx in ctx_list:
            for target_name in TARGET_NAMES:
                donor_sequence = donor_targets.get(target_name, {})
                value = donor_sequence.get(ctx.model_frame_idx)
                applicable = value is not None
                donor_identity: dict[str, object] = {
                    "donor_trajectory_id": donor_id,
                    "donor_model_frame_idx": ctx.model_frame_idx,
                    "donor_group_key": assignment.donor_group_key,
                    "recipient_group_key": assignment.recipient_group_key,
                    "seed": seed,
                }
                if not applicable:
                    donor_identity["reason"] = (
                        "donor trajectory has no target value at this "
                        "explicit model_frame_idx"
                    )
                rows.append(
                    make_baseline_row(
                        ctx,
                        baseline_name=BASELINE_NAME,
                        target_name=target_name,
                        prediction=value if applicable else None,
                        applicable=applicable,
                        fit_metadata=donor_identity,
                    )
                )
    return rows
