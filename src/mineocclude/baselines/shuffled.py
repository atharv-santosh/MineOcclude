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
from typing import Mapping, Optional, Sequence

import numpy as np

from mineocclude.baselines.interface import (
    TARGET_NAMES,
    BaselineRow,
    TrajectoryContext,
    make_baseline_row,
)

BASELINE_NAME = "grouped_shuffled"

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


def apply_grouped_shuffle(
    contexts: Sequence[TrajectoryContext],
    trajectory_targets: Mapping[str, TrajectoryTargets],
    seed: int,
) -> list[BaselineRow]:
    """Produce grouped-shuffled predictions for every context.

    Each trajectory in ``contexts`` is assigned a distinct donor
    trajectory via :func:`make_shuffle_permutation`. Every recipient
    frame receives the donor's target value at that *same explicit
    model_frame_idx* -- never at the same position-in-list, since a
    donor's Nth remaining frame is not necessarily model_frame_idx N
    once either trajectory has excluded/missing frames. If the donor
    has no value recorded for that exact frame index, the row is
    marked not applicable rather than borrowing a neighboring frame.
    """

    grouped: dict[str, list[TrajectoryContext]] = defaultdict(list)
    for ctx in contexts:
        grouped[ctx.trajectory_id].append(ctx)

    permutation = make_shuffle_permutation(list(grouped.keys()), seed)

    rows: list[BaselineRow] = []
    for trajectory_id, ctx_list in grouped.items():
        donor_id = permutation[trajectory_id]
        donor_targets = trajectory_targets.get(donor_id, {})
        for ctx in ctx_list:
            for target_name in TARGET_NAMES:
                donor_sequence = donor_targets.get(target_name, {})
                value = donor_sequence.get(ctx.model_frame_idx)
                applicable = value is not None
                rows.append(
                    make_baseline_row(
                        ctx,
                        baseline_name=BASELINE_NAME,
                        target_name=target_name,
                        prediction=value if applicable else None,
                        applicable=applicable,
                        fit_metadata=(
                            {
                                "donor_trajectory_id": donor_id,
                                "donor_model_frame_idx": ctx.model_frame_idx,
                                "seed": seed,
                            }
                            if applicable
                            else {
                                "donor_trajectory_id": donor_id,
                                "donor_model_frame_idx": ctx.model_frame_idx,
                                "seed": seed,
                                "reason": (
                                    "donor trajectory has no target value at this "
                                    "explicit model_frame_idx"
                                ),
                            }
                        ),
                    )
                )
    return rows
