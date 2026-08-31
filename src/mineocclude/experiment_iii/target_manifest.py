"""Prospective target window, FIR labels, and context age (authority 2.5, 4.6, 5.4).

The target window is the **first 19 consecutive eligible rows in ascending
model-frame order** — no phase offset, no per-fold phase schedule, no
outcome-derived adjustment. A-prime's ``phase_offsets_frames = [0,3,6,9,12]`` is
removed and must not reappear.

Selection reads only the regenerated path and the counterfactual geometry. It
never reads a rendered frame, a magenta detection, an RVE score or a decoder
error, so the same 19 rows and 19 labels apply unchanged to all five conditions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from mineocclude.experiment_iii.authority import (
    CAMERA_EYE,
    CONTEXT_PAIRS,
    LAYOUT_01,
    TARGET_ROWS_PER_CAPTURE,
)
from mineocclude.experiment_iii.errors import ExperimentIIIError
from mineocclude.experiment_iii.extent_geometry import (
    counterfactual_extent_classes,
    counterfactual_wall,
    first_fully_occluded_run,
)
from mineocclude.experiment_iii.fir import (
    FIRST_FULLY_RESOLVED_TICK,
    fir_labels,
)
from mineocclude.experiment_iii.schema import ConditionId, ExtentClassName

__all__ = [
    "TargetWindow",
    "eligibility_mask",
    "select_target_window",
    "build_target_window",
    "context_ages",
    "last_preocclusion_index",
    "evidence_in_context",
    "assert_rows_identical_across_conditions",
]

FULLY_OCCLUDED = ExtentClassName.EXTENT_FULLY_OCCLUDED


@dataclass(frozen=True)
class TargetWindow:
    """The 19 frozen target rows of one identity, shared by all five conditions."""

    identity: str
    direction: str
    target_model_frame_indices: tuple[int, ...]
    labels: tuple[float, ...]
    context_ages: tuple[int, ...]
    last_preocclusion_model_frame_idx: int
    extent_classes: tuple[str, ...]

    def __post_init__(self) -> None:
        if len(self.target_model_frame_indices) != TARGET_ROWS_PER_CAPTURE:
            raise ExperimentIIIError(
                "TARGET_ROW_MISMATCH",
                f"a target window holds {TARGET_ROWS_PER_CAPTURE} rows, got "
                f"{len(self.target_model_frame_indices)}",
            )
        if len(self.labels) != TARGET_ROWS_PER_CAPTURE:
            raise ExperimentIIIError(
                "TARGET_ROW_MISMATCH", "label count must match the target row count"
            )
        indices = self.target_model_frame_indices
        if list(indices) != list(range(indices[0], indices[0] + len(indices))):
            raise ExperimentIIIError(
                "TARGET_ROW_MISMATCH", "target rows must be consecutive and ascending"
            )
        if indices[0] < FIRST_FULLY_RESOLVED_TICK:
            raise ExperimentIIIError(
                "FIR_INCOMPLETE_HISTORY",
                f"first target row {indices[0]} precedes the first fully resolved "
                f"tick {FIRST_FULLY_RESOLVED_TICK}",
            )
        if set(self.extent_classes) != {FULLY_OCCLUDED.value}:
            raise ExperimentIIIError(
                "TARGET_ROW_MISMATCH",
                "every target row must be counterfactually fully occluded",
            )

    def as_manifest_fields(self) -> dict[str, Any]:
        return {
            "target_model_frame_indices": list(self.target_model_frame_indices),
            "expected_causal_fir_target_world_x_blocks": list(self.labels),
            "context_ages": list(self.context_ages),
            "last_preocclusion_model_frame_idx": self.last_preocclusion_model_frame_idx,
        }


def eligibility_mask(
    positions: Sequence[float],
    *,
    layout: Mapping[str, object] = LAYOUT_01,
    camera: Sequence[float] = CAMERA_EYE,
) -> tuple[list[bool], list[ExtentClassName]]:
    """Per-row §4.6 eligibility, before manifest membership is known.

    Eligibility is counterfactual occlusion **and** complete causal FIR history.
    Nothing material-dependent enters: no magenta, no RVE, no server centre ray.
    """
    wall = counterfactual_wall(layout)
    classes = counterfactual_extent_classes(positions, layout=layout, camera=camera, wall=wall)
    mask = [
        value is FULLY_OCCLUDED and index >= FIRST_FULLY_RESOLVED_TICK
        for index, value in enumerate(classes)
    ]
    return mask, classes


def select_target_window(
    positions: Sequence[float],
    *,
    length: int = TARGET_ROWS_PER_CAPTURE,
    layout: Mapping[str, object] = LAYOUT_01,
    camera: Sequence[float] = CAMERA_EYE,
) -> tuple[int, int] | None:
    """The earliest ``[start, stop)`` run of ``length`` adjacent eligible rows."""
    mask, classes = eligibility_mask(positions, layout=layout, camera=camera)
    eligible = [
        FULLY_OCCLUDED if keep else ExtentClassName.EXTENT_FULLY_VISIBLE
        for keep in mask
    ]
    del classes
    return first_fully_occluded_run(eligible, length)


def last_preocclusion_index(
    classes: Sequence[ExtentClassName], first_target_index: int
) -> int:
    """Index of the last counterfactual row before the window that was NOT occluded.

    Authority 5.4 defines context age as ticks since that row.
    """
    for index in range(first_target_index - 1, -1, -1):
        if classes[index] is not FULLY_OCCLUDED:
            return index
    raise ExperimentIIIError(
        "TOKEN_CONTEXT_AGE_UNVERIFIED",
        "no pre-occlusion counterfactual row precedes the target window; context "
        "age is undefined",
    )


def context_ages(
    classes: Sequence[ExtentClassName], indices: Sequence[int]
) -> tuple[int, ...]:
    """``a`` per target row: ticks since the last not-fully-occluded row.

    Authority 5.4 also fixes ``a = 1`` at the first target row and ``a = 19`` at
    the last. Both statements agree only when the window begins at the occlusion
    onset; this refuses rather than silently reporting a shifted age if they ever
    disagree.
    """
    anchor = last_preocclusion_index(classes, indices[0])
    ages = tuple(index - anchor for index in indices)
    expected = tuple(range(1, len(indices) + 1))
    if ages != expected:
        raise ExperimentIIIError(
            "TOKEN_CONTEXT_AGE_UNVERIFIED",
            f"context ages {ages[:3]}...{ages[-1]} do not run 1..{len(indices)}; "
            "the target window does not begin at the occlusion onset",
        )
    return ages


def evidence_in_context(age: int, *, context_pairs: int = CONTEXT_PAIRS) -> bool:
    """Whether the last pre-occlusion pair is still inside the model context.

    The context is ``[t-15, ..., t]``, so the pair is present for ``a <= 15`` and
    absent for ``a >= 16``. This is the arithmetic only; the frame identity itself
    must be verified from the tokenized context (authority 5.4, fixture A.13).
    """
    return age <= context_pairs - 1


def build_target_window(
    identity: str,
    direction: str,
    positions: Sequence[float],
    *,
    length: int = TARGET_ROWS_PER_CAPTURE,
    layout: Mapping[str, object] = LAYOUT_01,
    camera: Sequence[float] = CAMERA_EYE,
) -> TargetWindow:
    """Materialize one identity's frozen target rows, labels and context ages."""
    mask, classes = eligibility_mask(positions, layout=layout, camera=camera)
    eligible = [
        FULLY_OCCLUDED if keep else ExtentClassName.EXTENT_FULLY_VISIBLE
        for keep in mask
    ]
    window = first_fully_occluded_run(eligible, length)
    if window is None:
        raise ExperimentIIIError(
            "COHORT_QUALIFICATION_INFEASIBLE",
            f"{identity} has no run of {length} consecutive eligible target rows",
        )
    start, stop = window
    indices = tuple(range(start, stop))
    labels = tuple(fir_labels([float(value) for value in positions], indices, direction))
    return TargetWindow(
        identity=identity,
        direction=direction,
        target_model_frame_indices=indices,
        labels=labels,
        context_ages=context_ages(classes, indices),
        last_preocclusion_model_frame_idx=last_preocclusion_index(classes, start),
        extent_classes=tuple(classes[index].value for index in indices),
    )


def assert_rows_identical_across_conditions(
    per_condition: Mapping[str, TargetWindow],
) -> None:
    """Refuse any per-condition divergence in target indices or labels.

    Authority 4.6: the exact same 19 rows and 19 labels are shared across L0-L4.
    """
    missing = [
        condition.value
        for condition in ConditionId
        if condition.value not in per_condition
    ]
    if missing:
        raise ExperimentIIIError(
            "TARGET_ROW_CONDITION_DIVERGENCE",
            f"target rows are absent for conditions {missing}",
        )
    reference = per_condition[ConditionId.L0.value]
    for condition in ConditionId:
        window = per_condition[condition.value]
        if window.target_model_frame_indices != reference.target_model_frame_indices:
            raise ExperimentIIIError(
                "TARGET_ROW_CONDITION_DIVERGENCE",
                f"{condition.value} target indices differ from L0",
            )
        if window.labels != reference.labels:
            raise ExperimentIIIError(
                "TARGET_ROW_CONDITION_DIVERGENCE",
                f"{condition.value} FIR labels differ from L0",
            )
