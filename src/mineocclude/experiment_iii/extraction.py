"""Multi-layer temporal extraction (authority 8.4).

**One teacher-forced forward per target row** yields layers {4, 10, 19} and both
{PREVIOUS, CURRENT} from that same forward. Decoder causality means the pair-14
residual cannot attend to pair 15, so a second forward for PREVIOUS is neither
necessary nor authorized; nor is one forward per layer. Production is exactly
2,375 forwards and any excess is ``EXTRACTION_FORWARD_COUNT_EXCESS``.

**Shape agreement is not evidence.** A correctly shaped tensor from the wrong
frame is rejected: :func:`assert_semantic_slice_identity` checks the pair index,
the exact visual positions, the *frame identity*, full sequence coverage and
action disjointness, per forward.

The model is injected. Nothing here imports MineWorld, and the module is exercised
against deterministic stub decoders on CPU.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping, Protocol, Sequence

import numpy as np

from mineocclude.experiment_iii.errors import ExperimentIIIError
from mineocclude.experiment_iii.schema import TemporalSlice
from mineocclude.experiment_iii.slices import (
    HIDDEN_WIDTH,
    SEQUENCE_LENGTH,
    SLICE_SPECS,
    TOKENS_PER_PAIR,
    VISUAL_TOKENS_PER_PAIR,
    action_positions,
    slice_spec,
    visual_positions,
)

__all__ = [
    "SELECTED_LAYERS",
    "TRANSIENT_HOOK_LAYER_COUNT",
    "ForwardResult",
    "TeacherForcedDecoder",
    "ExtractionCounter",
    "assert_semantic_slice_identity",
    "assert_full_sequence_coverage",
    "extract_target_row",
    "extract_capture",
]

#: Authority 8.4. The hook manager may transiently register all 20 decoder
#: layers, but ONLY these three are serialized.
SELECTED_LAYERS = (4, 10, 19)
TRANSIENT_HOOK_LAYER_COUNT = 20


class TeacherForcedDecoder(Protocol):
    """The injected model seam. One call must yield every hooked layer."""

    def teacher_forced(
        self, *, trajectory_id: str, model_frame_idx: int
    ) -> "ForwardResult": ...


@dataclass(frozen=True)
class ForwardResult:
    """One teacher-forced call: the hooked residuals plus the token map."""

    #: layer index -> array of shape [1, 5552, 2048]
    layer_activations: Mapping[int, np.ndarray]
    #: the FrameTokenMap (or a structurally identical stand-in) for this call
    frame_token_map: Any
    trajectory_id: str
    model_frame_idx: int


class ExtractionCounter:
    """Counts forwards so an excess is detectable rather than assumed absent."""

    def __init__(self, expected_per_capture: int) -> None:
        self.expected_per_capture = expected_per_capture
        self.forwards = 0

    def record(self) -> None:
        self.forwards += 1

    def assert_within_budget(self, captures: int = 1) -> None:
        budget = self.expected_per_capture * captures
        if self.forwards > budget:
            raise ExperimentIIIError(
                "EXTRACTION_FORWARD_COUNT_EXCESS",
                f"{self.forwards} forwards exceed the authorized {budget}",
            )


def assert_full_sequence_coverage(frame_token_map: Any) -> None:
    """The map must cover ``range(5552)`` exactly, with no gap or duplicate."""
    spans = tuple(frame_token_map.spans)
    positions: list[int] = []
    for span in spans:
        positions.extend(span.visual_positions)
        positions.extend(span.action_positions)
    if len(positions) != len(set(positions)):
        raise ExperimentIIIError(
            "TOKEN_SEQUENCE_LENGTH_MISMATCH",
            "token positions are duplicated across spans",
        )
    if sorted(positions) != list(range(SEQUENCE_LENGTH)):
        raise ExperimentIIIError(
            "TOKEN_SEQUENCE_LENGTH_MISMATCH",
            f"FrameTokenMap does not cover range({SEQUENCE_LENGTH}) exactly",
        )
    if getattr(frame_token_map, "sequence_length", None) != SEQUENCE_LENGTH:
        raise ExperimentIIIError(
            "TOKEN_SEQUENCE_LENGTH_MISMATCH",
            "FrameTokenMap sequence_length is not 5552",
        )
    if len(spans) * TOKENS_PER_PAIR != SEQUENCE_LENGTH:
        raise ExperimentIIIError(
            "TOKEN_SEQUENCE_LENGTH_MISMATCH",
            f"expected {SEQUENCE_LENGTH // TOKENS_PER_PAIR} pairs, got {len(spans)}",
        )


def assert_semantic_slice_identity(
    frame_token_map: Any, target_row: int, *, trajectory_id: str
) -> None:
    """The five semantic assertions of authority 8.4.

    Shape agreement is deliberately NOT among them: a correctly shaped tensor
    from the wrong pair is exactly what this exists to reject.
    """
    assert_full_sequence_coverage(frame_token_map)
    spans = tuple(frame_token_map.spans)
    current, previous = spans[-1], spans[-2]

    for span, spec in (
        (current, slice_spec(TemporalSlice.CURRENT)),
        (previous, slice_spec(TemporalSlice.PREVIOUS)),
    ):
        if span.pair_index != spec.pair_index:
            raise ExperimentIIIError(
                "TOKEN_SPAN_MISMATCH",
                f"{spec.name.value} expects pair_index {spec.pair_index}, got "
                f"{span.pair_index}",
            )
        expected_visual = visual_positions(spec.pair_index)
        if tuple(span.visual_positions) != expected_visual:
            raise ExperimentIIIError(
                "TOKEN_SPAN_MISMATCH",
                f"{spec.name.value} visual positions are not "
                f"range({expected_visual[0]}, {expected_visual[-1] + 1})",
            )
        expected_frame = spec.model_frame_idx(target_row)
        identity = span.identity
        if getattr(identity, "model_frame_idx", None) != expected_frame:
            raise ExperimentIIIError(
                "TOKEN_FRAME_IDENTITY_MISMATCH",
                f"{spec.name.value} carries frame "
                f"{getattr(identity, 'model_frame_idx', None)}, expected "
                f"{expected_frame}; a correctly shaped tensor from the wrong "
                "frame is not acceptable evidence",
            )
        if getattr(identity, "trajectory_id", None) != trajectory_id:
            raise ExperimentIIIError(
                "TOKEN_FRAME_IDENTITY_MISMATCH",
                f"{spec.name.value} belongs to trajectory "
                f"{getattr(identity, 'trajectory_id', None)}, expected "
                f"{trajectory_id}",
            )

    selected = set(visual_positions(previous.pair_index)) | set(
        visual_positions(current.pair_index)
    )
    every_action = {
        position
        for span in spans
        for position in span.action_positions
    }
    contaminated = selected & every_action
    if contaminated:
        raise ExperimentIIIError(
            "TOKEN_ACTION_CONTAMINATION",
            f"{len(contaminated)} selected visual positions are action tokens",
        )


def _slice_layer(activation: np.ndarray, spec) -> np.ndarray:
    array = np.asarray(activation)
    if array.ndim == 3 and array.shape[0] == 1:
        array = array[0]
    if array.shape != (SEQUENCE_LENGTH, HIDDEN_WIDTH):
        raise ExperimentIIIError(
            "TENSOR_SHAPE_MISMATCH",
            f"hooked activation must be [1,{SEQUENCE_LENGTH},{HIDDEN_WIDTH}], got "
            f"{np.asarray(activation).shape}",
        )
    sliced = array[spec.python_slice]
    if sliced.shape != (VISUAL_TOKENS_PER_PAIR, HIDDEN_WIDTH):
        raise ExperimentIIIError(
            "TENSOR_SHAPE_MISMATCH",
            f"{spec.name.value} slice is {sliced.shape}, expected "
            f"({VISUAL_TOKENS_PER_PAIR}, {HIDDEN_WIDTH})",
        )
    return sliced


def extract_target_row(
    decoder: TeacherForcedDecoder,
    *,
    trajectory_id: str,
    target_row: int,
    layers: Sequence[int] = SELECTED_LAYERS,
    counter: ExtractionCounter | None = None,
) -> dict[tuple[int, TemporalSlice], np.ndarray]:
    """ONE forward -> three layers x two slices for a single target row."""
    result = decoder.teacher_forced(
        trajectory_id=trajectory_id, model_frame_idx=target_row
    )
    if counter is not None:
        counter.record()

    if result.model_frame_idx != target_row or result.trajectory_id != trajectory_id:
        raise ExperimentIIIError(
            "TOKEN_FRAME_IDENTITY_MISMATCH",
            f"forward returned ({result.trajectory_id}, {result.model_frame_idx}), "
            f"expected ({trajectory_id}, {target_row})",
        )
    assert_semantic_slice_identity(
        result.frame_token_map, target_row, trajectory_id=trajectory_id
    )

    missing = [layer for layer in layers if layer not in result.layer_activations]
    if missing:
        raise ExperimentIIIError(
            "HOOK_LAYER_MISSING",
            f"the forward did not capture layers {missing}",
        )
    harvested: dict[tuple[int, TemporalSlice], np.ndarray] = {}
    for layer in layers:
        for name in (TemporalSlice.PREVIOUS, TemporalSlice.CURRENT):
            harvested[(layer, name)] = _slice_layer(
                result.layer_activations[layer], slice_spec(name)
            )
    return harvested


def extract_capture(
    decoder: TeacherForcedDecoder,
    *,
    trajectory_id: str,
    target_rows: Sequence[int],
    layers: Sequence[int] = SELECTED_LAYERS,
) -> tuple[dict[tuple[int, TemporalSlice], np.ndarray], ExtractionCounter]:
    """All 19 target rows of one capture; six [19,336,2048] stacks come out.

    The 19 forwards are shared by all six (layer, slice) units, which is why the
    ledger records the shared forward set rather than per-unit forwards.
    """
    rows = list(target_rows)
    counter = ExtractionCounter(expected_per_capture=len(rows))
    per_row: list[dict[tuple[int, TemporalSlice], np.ndarray]] = []
    for target_row in rows:
        per_row.append(
            extract_target_row(
                decoder,
                trajectory_id=trajectory_id,
                target_row=target_row,
                layers=layers,
                counter=counter,
            )
        )
    counter.assert_within_budget()

    stacked: dict[tuple[int, TemporalSlice], np.ndarray] = {}
    for layer in layers:
        for name in (TemporalSlice.PREVIOUS, TemporalSlice.CURRENT):
            stacked[(layer, name)] = np.stack(
                [row[(layer, name)] for row in per_row], axis=0
            )
    return stacked, counter
