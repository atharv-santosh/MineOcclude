"""VIS6 visible controls (authority 24; VERIFY-4 at authority 18.3).

``VIS6`` is the **last** 6 consecutive model frames of a capture that are
counterfactually ``EXTENT_FULLY_VISIBLE``, clamp-free, and carry a complete
16-pair context. It is a **best-effort descriptive** control, never a
qualification gate: a cell with fewer than 6 eligible consecutive rows records
``B_VIS_UNAVAILABLE`` -- informational only -- and continues.

Two failure modes this module exists to prevent:

* returning a **pre-occlusion** window. Authority 18.3 resolved the
  pre-occlusion visible window as **infeasible**; only rows after the target
  window's last row are admissible.
* returning **clamp-pinned** rows. A sheep pinned at the lane bound has no
  motion, which voids both the position positive control and the ``q``-perception
  diagnostic (test ``D.10``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import numpy as np

from mineocclude.experiment_iii.authority import (
    CAMERA_EYE,
    CONTEXT_PAIRS,
    LANE_MAX,
    LANE_MIN,
    LAYOUT_01,
    TARGET_ROWS_PER_CAPTURE,
)
from mineocclude.experiment_iii.errors import ExperimentIIIError
from mineocclude.experiment_iii.schema import ExtentClassName
from mineocclude.experiment_iii.target_manifest import eligibility_mask, select_target_window

__all__ = [
    "VIS_ROWS",
    "VisibleWindow",
    "clamp_free_mask",
    "select_vis_window",
    "vis_coverage",
]

#: Authority 24 / 18.3. The provisional value 8 is superseded and never used.
VIS_ROWS = 6

#: A complete 16-pair context needs 15 earlier frames, so the first admissible
#: model-frame index is 15 (the same arithmetic as the III-A eligibility rule).
FIRST_COMPLETE_CONTEXT_INDEX = CONTEXT_PAIRS - 1


@dataclass(frozen=True)
class VisibleWindow:
    """The VIS6 rows of one ``(identity, q)`` cell, or an explicit absence."""

    identity: str
    q: float
    model_frame_indices: tuple[int, ...]
    available: bool
    blocker: str | None
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "identity": self.identity,
            "q": float(self.q),
            "vis_model_frame_indices": list(self.model_frame_indices),
            "vis_rows": len(self.model_frame_indices),
            "vis_available": self.available,
            "vis_blocker": self.blocker,
            "vis_reason": self.reason,
            "vis_is_a_qualification_gate": False,
        }


def clamp_free_mask(
    positions: Sequence[float],
    *,
    lane_min: float = LANE_MIN,
    lane_max: float = LANE_MAX,
) -> list[bool]:
    """Rows whose position is strictly inside the lane bounds.

    A row pinned at either bound is clamped; the generator's clamp makes the
    position exactly equal to the bound, so equality is the correct test.
    """
    return [lane_min < float(value) < lane_max for value in positions]


def select_vis_window(
    identity: str,
    positions: Sequence[float],
    *,
    q: float,
    rows: int = VIS_ROWS,
    target_window: tuple[int, int] | None = None,
    layout: Mapping[str, object] = LAYOUT_01,
    camera: Sequence[float] = CAMERA_EYE,
) -> VisibleWindow:
    """The last ``rows`` consecutive eligible visible frames, post-occlusion."""
    if rows != VIS_ROWS:
        raise ExperimentIIIError(
            "B_VIS_UNAVAILABLE",
            f"VIS_ROWS is frozen at {VIS_ROWS}; the provisional 8 is superseded",
        )
    _, classes = eligibility_mask(positions, layout=layout, camera=camera)
    if target_window is None:
        target_window = select_target_window(
            positions, length=TARGET_ROWS_PER_CAPTURE, layout=layout, camera=camera
        )
    if target_window is None:
        return VisibleWindow(
            identity=identity,
            q=float(q),
            model_frame_indices=(),
            available=False,
            blocker="B_VIS_UNAVAILABLE",
            reason="the cell has no target window, so no post-occlusion side exists",
        )
    _, occlusion_stop = target_window
    clamp_free = clamp_free_mask(positions)
    eligible = [
        classes[index] is ExtentClassName.EXTENT_FULLY_VISIBLE
        and clamp_free[index]
        and index >= FIRST_COMPLETE_CONTEXT_INDEX
        and index >= occlusion_stop
        for index in range(len(positions))
    ]

    # Scan from the end: the LAST run of `rows` adjacent eligible frames.
    for stop in range(len(eligible), rows - 1, -1):
        start = stop - rows
        if all(eligible[start:stop]):
            indices = tuple(range(start, stop))
            window = np.asarray([float(positions[i]) for i in indices], dtype=np.float64)
            if float(window.var()) <= 0.0:
                # Motionless rows would void the position control; keep scanning.
                continue
            return VisibleWindow(
                identity=identity,
                q=float(q),
                model_frame_indices=indices,
                available=True,
                blocker=None,
                reason="last 6 consecutive clamp-free fully-visible post-occlusion rows",
            )
    return VisibleWindow(
        identity=identity,
        q=float(q),
        model_frame_indices=(),
        available=False,
        blocker="B_VIS_UNAVAILABLE",
        reason=(
            f"fewer than {rows} consecutive clamp-free fully-visible post-occlusion "
            "rows with a complete 16-pair context"
        ),
    )


def vis_coverage(windows: Sequence[VisibleWindow]) -> dict[str, Any]:
    """Per-cell coverage, as authority 24 requires it to be reported."""
    total = len(windows)
    available = sum(1 for window in windows if window.available)
    return {
        "cells": total,
        "cells_with_vis6": available,
        "cells_without_vis6": total - available,
        "coverage_fraction": (available / total) if total else 0.0,
        "blocker": "B_VIS_UNAVAILABLE" if available < total else None,
        "blocker_severity": "INFORMATIONAL",
        "is_a_qualification_gate": False,
        "may_change_primary_readout_or_q_values": False,
    }
