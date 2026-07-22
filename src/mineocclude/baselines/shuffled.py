"""Grouped-shuffle null floor.

Roadmap D2: "Grouped shuffled labels | Original features; permuted
trajectory/layout target association | Chance/null floor while
preserving temporal structure."

We shuffle at the *trajectory* level: every trajectory is assigned a
different "donor" trajectory (a seeded derangement, so no trajectory
is ever paired with itself), and each frame's shuffled target is taken
from the donor trajectory's target sequence at the same
within-trajectory position. This breaks the true feature/target link
while preserving each trajectory's internal temporal ordering, per the
roadmap's explicit requirement -- a plain global row shuffle would
scramble temporal structure and make the floor too weak (an
unrealistically low bar).
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

#: Per-trajectory target sequences, in ascending model_frame_idx order,
#: keyed by target name. ``None`` entries mean "not applicable at this
#: position" and must not be treated as zero.
TrajectoryTargets = Mapping[str, Sequence[Optional[float]]]


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
    trajectory via :func:`make_shuffle_permutation`. Frame ``i`` (0-
    indexed by ascending ``model_frame_idx`` within its trajectory)
    receives the donor's target value at the same index ``i``. If the
    donor trajectory is shorter, the excess frames are marked not
    applicable rather than padded with a value from the wrong context.
    """

    grouped: dict[str, list[TrajectoryContext]] = defaultdict(list)
    for ctx in contexts:
        grouped[ctx.trajectory_id].append(ctx)
    for ctx_list in grouped.values():
        ctx_list.sort(key=lambda c: c.model_frame_idx)

    permutation = make_shuffle_permutation(list(grouped.keys()), seed)

    rows: list[BaselineRow] = []
    for trajectory_id, ctx_list in grouped.items():
        donor_id = permutation[trajectory_id]
        donor_targets = trajectory_targets.get(donor_id, {})
        for position, ctx in enumerate(ctx_list):
            for target_name in TARGET_NAMES:
                sequence = donor_targets.get(target_name, ())
                applicable = position < len(sequence) and sequence[position] is not None
                prediction = sequence[position] if applicable else None
                rows.append(
                    make_baseline_row(
                        ctx,
                        baseline_name=BASELINE_NAME,
                        target_name=target_name,
                        prediction=prediction,
                        applicable=applicable,
                        fit_metadata={
                            "donor_trajectory_id": donor_id,
                            "donor_position": position,
                            "seed": seed,
                        },
                    )
                )
    return rows
