"""Synthetic fixtures for baseline tests.

Nothing here reads from real MineOcclude captures. The current authoritative
A/B/C contracts are available from the integration foundation, but no real
accepted trajectory, target, or fold artifact is claimed. These fixtures build
small, hand-computed trajectories directly from :class:`TrajectoryContext`,
entirely in terms of what a baseline is legally allowed to see, so expected
values can be checked by hand rather than trusted from another pipeline stage.
"""

from __future__ import annotations

from typing import Optional, Sequence

import pytest

from mineocclude.baselines.interface import TrajectoryContext


def build_trajectory_contexts(
    *,
    trajectory_id: str,
    layout_id: str,
    fold: int,
    regime: str = "A",
    visible_positions: Sequence[float] = (0.0, 1.0, 2.0, 3.0),
    dt: float = 0.05,
    hidden_taus: Sequence[float] = (0.05, 0.10, 0.15),
    v_scripted: Optional[float] = None,
    q_scripted: Optional[float] = None,
    duration_seconds: Optional[float] = None,
    config_hash: str = "cfg-test",
    seed: Optional[int] = 123,
) -> list[TrajectoryContext]:
    """Build one trajectory's frames: a visible ramp, then hidden frames.

    ``last_seen_position_blocks``/``last_seen_velocity_blocks_per_s``
    are computed *causally* -- frame ``i`` only ever reflects
    positions observed up to and including frame ``i``, never a future
    position. Velocity is a simple two-point finite difference over
    the two most recent visible frames (None until a second visible
    frame exists), matching "visible-window position/speed" rather
    than the privileged scripted ``v``.
    """

    contexts: list[TrajectoryContext] = []
    last_seen_position: Optional[float] = None
    last_seen_velocity: Optional[float] = None
    previous_position: Optional[float] = None

    frame_idx = 0
    for position in visible_positions:
        if previous_position is not None:
            last_seen_velocity = (position - previous_position) / dt
        last_seen_position = position
        previous_position = position

        contexts.append(
            TrajectoryContext(
                trajectory_id=trajectory_id,
                layout_id=layout_id,
                model_frame_idx=frame_idx,
                fold=fold,
                regime=regime,
                tau_seconds=0.0,
                visibility=True,
                last_seen_position_blocks=last_seen_position,
                last_seen_velocity_blocks_per_s=last_seen_velocity,
                v_scripted_blocks_per_s=v_scripted,
                q_scripted_blocks2_per_s=q_scripted,
                duration_seconds=duration_seconds,
                config_hash=config_hash,
                seed=seed,
            )
        )
        frame_idx += 1

    for tau in hidden_taus:
        contexts.append(
            TrajectoryContext(
                trajectory_id=trajectory_id,
                layout_id=layout_id,
                model_frame_idx=frame_idx,
                fold=fold,
                regime=regime,
                tau_seconds=tau,
                visibility=False,
                last_seen_position_blocks=last_seen_position,
                last_seen_velocity_blocks_per_s=last_seen_velocity,
                v_scripted_blocks_per_s=v_scripted,
                q_scripted_blocks2_per_s=q_scripted,
                duration_seconds=duration_seconds,
                config_hash=config_hash,
                seed=seed,
            )
        )
        frame_idx += 1

    return contexts


@pytest.fixture
def single_trajectory() -> list[TrajectoryContext]:
    """One trajectory: 4 visible frames at unit speed, 3 hidden frames."""

    return build_trajectory_contexts(
        trajectory_id="traj-0",
        layout_id="layout-0",
        fold=0,
        visible_positions=(0.0, 1.0, 2.0, 3.0),
        dt=1.0,
        hidden_taus=(1.0, 2.0, 3.0),
    )


@pytest.fixture
def never_seen_context() -> TrajectoryContext:
    """A single hidden frame whose target has never been visible."""

    return TrajectoryContext(
        trajectory_id="traj-unseen",
        layout_id="layout-0",
        model_frame_idx=0,
        fold=0,
        regime="A",
        tau_seconds=0.5,
        visibility=False,
        last_seen_position_blocks=None,
        last_seen_velocity_blocks_per_s=None,
        v_scripted_blocks_per_s=None,
        q_scripted_blocks2_per_s=None,
        duration_seconds=None,
        config_hash="cfg-test",
        seed=None,
    )
