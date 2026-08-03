"""Real-capture ingest adapter (Person D).

Parses Person C's real, accepted capture-package row streams --
``server_state.jsonl``, ``visibility.jsonl``, ``frame_map.jsonl``
(docs/contracts/trajectory_v1.md) -- into
:class:`~mineocclude.baselines.interface.TrajectoryContext` objects,
the same input type every baseline in this package already consumes.
This is the only piece needed to run last-seen/constant-velocity on
genuinely real captured trajectories rather than synthetic fixtures.

This module does not invent a fold assignment and does not read
anything from Person B: ``fold`` on every returned context is left at
the caller-supplied placeholder (default ``-1``, an explicit "not yet
assigned" sentinel) until a real, sealed B ``fold_manifest`` exists to
attach via :func:`mineocclude.baselines.export.attach_b_fold_assignments`.
Predictions computed from contexts built here are real numbers on real
data, but are not yet properly fold-scored and must not be presented
as a scientific result until that attachment happens.
"""

from __future__ import annotations

from typing import Dict, List, Mapping, Optional, Sequence

from mineocclude.baselines.interface import Regime, TrajectoryContext

REGIME_A_DT_SECONDS = 0.05

#: Explicit "no real B fold manifest attached yet" sentinel. Never a
#: valid fold index B would assign; catches an accidental unscored
#: export at the contract boundary instead of silently scoring row 0.
UNASSIGNED_FOLD = -1


class CaptureIngestError(ValueError):
    """Raised when Person C's row streams cannot be honestly joined."""


def _index_by_frame(
    rows: Sequence[Mapping[str, object]], *, stream_name: str
) -> Dict[int, Mapping[str, object]]:
    indexed: Dict[int, Mapping[str, object]] = {}
    for row in rows:
        idx = row.get("model_frame_idx")
        if not isinstance(idx, int) or isinstance(idx, bool) or idx < 0:
            raise CaptureIngestError(
                f"{stream_name} row has an invalid model_frame_idx: {row!r}"
            )
        if idx in indexed:
            raise CaptureIngestError(
                f"{stream_name} has a duplicate model_frame_idx {idx}"
            )
        indexed[idx] = row
    return indexed


def build_contexts_from_capture(
    frame_map_rows: Sequence[Mapping[str, object]],
    server_state_rows: Sequence[Mapping[str, object]],
    visibility_rows: Sequence[Mapping[str, object]],
    *,
    layout_id: str,
    config_hash: str,
    fold: int = UNASSIGNED_FOLD,
    regime: Regime = "A",
    v_scripted_blocks_per_s: Optional[float] = None,
    q_scripted_blocks2_per_s: Optional[float] = None,
    duration_seconds: Optional[float] = None,
    seed: Optional[int] = None,
    dt_seconds: float = REGIME_A_DT_SECONDS,
) -> List[TrajectoryContext]:
    """Join Person C's three real row streams into causal contexts.

    Every row across the three streams must share the same explicit
    ``model_frame_idx`` identity set and exactly one ``trajectory_id``
    -- a mismatch is a data problem to escalate, not something this
    adapter repairs, reorders, or infers past (matching the project's
    universal "row order and filenames are never identity" rule).

    ``last_seen_position_blocks``/``last_seen_velocity_blocks_per_s``
    are computed causally from the real ``wall_parallel_position_blocks``
    visible-window history only -- the estimated two-point velocity,
    never a privileged/scripted quantity, matching every other baseline
    module's convention. ``tau_seconds`` resets to 0 on every visible
    frame and increments by ``dt_seconds`` per consecutive hidden frame,
    matching the oracle's own reveal-reset behavior.
    """

    frame_map_by_idx = _index_by_frame(frame_map_rows, stream_name="frame_map")
    state_by_idx = _index_by_frame(server_state_rows, stream_name="server_state")
    visibility_by_idx = _index_by_frame(visibility_rows, stream_name="visibility")

    frame_indices = set(frame_map_by_idx)
    if frame_indices != set(state_by_idx) or frame_indices != set(visibility_by_idx):
        raise CaptureIngestError(
            "frame_map, server_state, and visibility do not share the same "
            "model_frame_idx identity set"
        )
    if not frame_indices:
        raise CaptureIngestError("no frames supplied")

    trajectory_ids = {
        row.get("trajectory_id")
        for row in (*frame_map_rows, *server_state_rows, *visibility_rows)
    }
    if len(trajectory_ids) != 1 or not all(
        isinstance(value, str) and value for value in trajectory_ids
    ):
        raise CaptureIngestError(
            "all three streams must share exactly one non-empty "
            f"trajectory_id, got {trajectory_ids!r}"
        )
    trajectory_id = next(iter(trajectory_ids))

    contexts: List[TrajectoryContext] = []
    last_seen_position: Optional[float] = None
    last_seen_velocity: Optional[float] = None
    previous_visible_position: Optional[float] = None
    hidden_ticks = 0

    for model_frame_idx in sorted(frame_indices):
        visibility_value = visibility_by_idx[model_frame_idx].get("visibility")
        if visibility_value not in ("visible", "occluded"):
            raise CaptureIngestError(
                f"frame {model_frame_idx} has an unrecognized visibility "
                f"value: {visibility_value!r}"
            )
        is_visible = visibility_value == "visible"

        if is_visible:
            state = state_by_idx[model_frame_idx].get("state")
            if not isinstance(state, Mapping) or "wall_parallel_position_blocks" not in state:
                raise CaptureIngestError(
                    f"visible frame {model_frame_idx} is missing "
                    "wall_parallel_position_blocks"
                )
            position = float(state["wall_parallel_position_blocks"])
            if previous_visible_position is not None:
                last_seen_velocity = (position - previous_visible_position) / dt_seconds
            last_seen_position = position
            previous_visible_position = position
            hidden_ticks = 0
            tau_seconds = 0.0
        else:
            hidden_ticks += 1
            tau_seconds = hidden_ticks * dt_seconds

        contexts.append(
            TrajectoryContext(
                trajectory_id=trajectory_id,
                layout_id=layout_id,
                model_frame_idx=model_frame_idx,
                fold=fold,
                regime=regime,
                tau_seconds=tau_seconds,
                visibility=is_visible,
                last_seen_position_blocks=last_seen_position,
                last_seen_velocity_blocks_per_s=last_seen_velocity,
                v_scripted_blocks_per_s=v_scripted_blocks_per_s,
                q_scripted_blocks2_per_s=q_scripted_blocks2_per_s,
                duration_seconds=duration_seconds,
                config_hash=config_hash,
                seed=seed,
            )
        )

    return contexts
