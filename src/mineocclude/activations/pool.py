"""Select visual-token positions without performing Phase 4.4 pooling."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from mineocclude.contracts.activation import (
    MAX_MODEL_FRAMES,
    TOKENS_PER_FRAME_ACTION_PAIR,
    VISUAL_TOKENS_PER_FRAME,
)
from mineocclude.contracts.identity import SCHEMA_VERSION
from mineocclude.models.mineworld_adapter import (
    FrameTokenMap,
    FrameTokenSpan,
)

ACTION_TOKENS_PER_FRAME = (
    TOKENS_PER_FRAME_ACTION_PAIR - VISUAL_TOKENS_PER_FRAME
)


class VisualSelectionErrorCode(str, Enum):
    """Stable failure reasons for strict FrameTokenMap selection."""

    INVALID_REQUEST = "invalid_request"
    MALFORMED_MAP = "malformed_map"
    SEQUENCE_LENGTH_MISMATCH = "sequence_length_mismatch"
    MISSING_FRAME = "missing_frame"
    AMBIGUOUS_FRAME = "ambiguous_frame"
    INVALID_VISUAL_COUNT = "invalid_visual_count"
    INVALID_ACTION_COUNT = "invalid_action_count"
    DUPLICATE_POSITION = "duplicate_position"
    OUT_OF_BOUNDS = "out_of_bounds"
    ACTION_VISUAL_OVERLAP = "action_visual_overlap"
    NEIGHBOR_VISUAL_OVERLAP = "neighbor_visual_overlap"


class VisualTokenSelectionError(ValueError):
    """Actionable visual-position selection failure."""

    def __init__(
        self,
        code: VisualSelectionErrorCode,
        message: str,
    ) -> None:
        self.code = code
        super().__init__(f"{code.value}: {message}")


@dataclass(frozen=True)
class VisualTokenSelection:
    """Explicit visual positions for one scientific frame identity."""

    trajectory_id: str
    model_frame_idx: int
    positions: tuple[int, ...]
    sequence_length: int

    def __post_init__(self) -> None:
        if (
            not isinstance(self.trajectory_id, str)
            or not self.trajectory_id.strip()
            or not isinstance(self.model_frame_idx, int)
            or isinstance(self.model_frame_idx, bool)
            or self.model_frame_idx < 0
            or not isinstance(self.sequence_length, int)
            or isinstance(self.sequence_length, bool)
            or self.sequence_length <= 0
        ):
            raise VisualTokenSelectionError(
                VisualSelectionErrorCode.INVALID_REQUEST,
                "selection identity and sequence length must be valid",
            )
        _validate_positions(
            self.positions,
            expected_count=VISUAL_TOKENS_PER_FRAME,
            sequence_length=self.sequence_length,
            count_code=VisualSelectionErrorCode.INVALID_VISUAL_COUNT,
        )


def _validate_positions(
    positions: object,
    *,
    expected_count: int,
    sequence_length: int,
    count_code: VisualSelectionErrorCode,
) -> tuple[int, ...]:
    if not isinstance(positions, tuple) or len(positions) != expected_count:
        raise VisualTokenSelectionError(
            count_code,
            f"expected exactly {expected_count} explicit positions",
        )
    if any(
        not isinstance(position, int) or isinstance(position, bool)
        for position in positions
    ):
        raise VisualTokenSelectionError(
            VisualSelectionErrorCode.MALFORMED_MAP,
            "token positions must be integers",
        )
    if tuple(sorted(positions)) != positions:
        raise VisualTokenSelectionError(
            VisualSelectionErrorCode.MALFORMED_MAP,
            "token positions must be strictly increasing",
        )
    if len(set(positions)) != len(positions):
        raise VisualTokenSelectionError(
            VisualSelectionErrorCode.DUPLICATE_POSITION,
            "token positions must be unique",
        )
    if any(position < 0 or position >= sequence_length for position in positions):
        raise VisualTokenSelectionError(
            VisualSelectionErrorCode.OUT_OF_BOUNDS,
            "token positions fall outside the hooked sequence",
        )
    return positions


def select_visual_token_positions(
    frame_token_map: FrameTokenMap,
    *,
    trajectory_id: str,
    model_frame_idx: int,
    hooked_sequence_length: int,
) -> VisualTokenSelection:
    """Return only the explicit positions recorded for one requested frame."""

    if (
        not isinstance(trajectory_id, str)
        or not trajectory_id.strip()
        or not isinstance(model_frame_idx, int)
        or isinstance(model_frame_idx, bool)
        or model_frame_idx < 0
        or not isinstance(hooked_sequence_length, int)
        or isinstance(hooked_sequence_length, bool)
        or hooked_sequence_length <= 0
    ):
        raise VisualTokenSelectionError(
            VisualSelectionErrorCode.INVALID_REQUEST,
            "trajectory, model-frame, and hooked-sequence identity are required",
        )
    if not isinstance(frame_token_map, FrameTokenMap):
        raise VisualTokenSelectionError(
            VisualSelectionErrorCode.MALFORMED_MAP,
            "selection requires the frozen FrameTokenMap type",
        )
    if (
        not isinstance(frame_token_map.sequence_length, int)
        or frame_token_map.sequence_length <= 0
        or frame_token_map.sequence_length != hooked_sequence_length
    ):
        raise VisualTokenSelectionError(
            VisualSelectionErrorCode.SEQUENCE_LENGTH_MISMATCH,
            "FrameTokenMap and hooked sequence lengths must match exactly",
        )
    if (
        frame_token_map.schema_version != SCHEMA_VERSION
        or not isinstance(frame_token_map.trajectory_id, str)
        or not frame_token_map.trajectory_id.strip()
    ):
        raise VisualTokenSelectionError(
            VisualSelectionErrorCode.MALFORMED_MAP,
            "FrameTokenMap schema or trajectory identity is invalid",
        )
    if frame_token_map.trajectory_id != trajectory_id:
        raise VisualTokenSelectionError(
            VisualSelectionErrorCode.MISSING_FRAME,
            "requested trajectory is not represented by this FrameTokenMap",
        )
    if (
        not isinstance(frame_token_map.spans, tuple)
        or not frame_token_map.spans
        or len(frame_token_map.spans) > MAX_MODEL_FRAMES
        or any(
            not isinstance(span, FrameTokenSpan)
            for span in frame_token_map.spans
        )
    ):
        raise VisualTokenSelectionError(
            VisualSelectionErrorCode.MALFORMED_MAP,
            "FrameTokenMap spans are malformed",
        )

    all_visual: list[tuple[int, int]] = []
    all_actions: list[tuple[int, int]] = []
    identities: list[tuple[str, int]] = []
    pair_indices: list[int] = []
    matching: list[FrameTokenSpan] = []
    for span_index, span in enumerate(frame_token_map.spans):
        identity = getattr(span, "identity", None)
        if (
            getattr(identity, "trajectory_id", None)
            != frame_token_map.trajectory_id
            or not isinstance(getattr(identity, "model_frame_idx", None), int)
            or isinstance(getattr(identity, "model_frame_idx", None), bool)
            or identity.model_frame_idx < 0
            or not isinstance(getattr(span, "pair_index", None), int)
            or isinstance(getattr(span, "pair_index", None), bool)
            or span.pair_index < 0
        ):
            raise VisualTokenSelectionError(
                VisualSelectionErrorCode.MALFORMED_MAP,
                "span identity does not match the map",
            )
        pair_indices.append(span.pair_index)
        identities.append(
            (identity.trajectory_id, identity.model_frame_idx)
        )
        visual = _validate_positions(
            span.visual_positions,
            expected_count=VISUAL_TOKENS_PER_FRAME,
            sequence_length=hooked_sequence_length,
            count_code=VisualSelectionErrorCode.INVALID_VISUAL_COUNT,
        )
        actions = _validate_positions(
            span.action_positions,
            expected_count=ACTION_TOKENS_PER_FRAME,
            sequence_length=hooked_sequence_length,
            count_code=VisualSelectionErrorCode.INVALID_ACTION_COUNT,
        )
        all_visual.extend((span_index, position) for position in visual)
        all_actions.extend((span_index, position) for position in actions)
        if (
            identity.trajectory_id == trajectory_id
            and identity.model_frame_idx == model_frame_idx
        ):
            matching.append(span)

    if len(identities) != len(set(identities)):
        requested_count = identities.count((trajectory_id, model_frame_idx))
        code = (
            VisualSelectionErrorCode.AMBIGUOUS_FRAME
            if requested_count > 1
            else VisualSelectionErrorCode.MALFORMED_MAP
        )
        raise VisualTokenSelectionError(
            code,
            "FrameTokenMap contains duplicate scientific identities",
        )
    if pair_indices != list(range(len(frame_token_map.spans))):
        raise VisualTokenSelectionError(
            VisualSelectionErrorCode.MALFORMED_MAP,
            "pair indices must be unique, ordered, and context-relative",
        )
    if not matching:
        raise VisualTokenSelectionError(
            VisualSelectionErrorCode.MISSING_FRAME,
            "requested frame is not included in the current model context",
        )
    if len(matching) != 1:
        raise VisualTokenSelectionError(
            VisualSelectionErrorCode.AMBIGUOUS_FRAME,
            "requested frame identity resolves to multiple spans",
        )

    selected = matching[0]
    selected_positions = set(selected.visual_positions)
    action_positions = {position for _span, position in all_actions}
    if selected_positions & action_positions:
        raise VisualTokenSelectionError(
            VisualSelectionErrorCode.ACTION_VISUAL_OVERLAP,
            "requested visual positions overlap action-token positions",
        )
    selected_span_index = frame_token_map.spans.index(selected)
    neighboring_visual = {
        position
        for span_index, position in all_visual
        if span_index != selected_span_index
    }
    if selected_positions & neighboring_visual:
        raise VisualTokenSelectionError(
            VisualSelectionErrorCode.NEIGHBOR_VISUAL_OVERLAP,
            "requested visual positions overlap another frame",
        )
    all_position_values = [
        position for _span_index, position in all_visual + all_actions
    ]
    if len(all_position_values) != len(set(all_position_values)):
        raise VisualTokenSelectionError(
            VisualSelectionErrorCode.DUPLICATE_POSITION,
            "FrameTokenMap reuses one or more token positions",
        )
    if (
        len(all_position_values) != hooked_sequence_length
        or set(all_position_values) != set(range(hooked_sequence_length))
    ):
        raise VisualTokenSelectionError(
            VisualSelectionErrorCode.MALFORMED_MAP,
            "FrameTokenMap does not cover the hooked sequence exactly",
        )
    for span_index, span in enumerate(frame_token_map.spans):
        expected_pair_start = span_index * TOKENS_PER_FRAME_ACTION_PAIR
        expected_pair_end = (
            expected_pair_start + TOKENS_PER_FRAME_ACTION_PAIR
        )
        expected_visual = tuple(
            range(
                expected_pair_start,
                expected_pair_start + VISUAL_TOKENS_PER_FRAME,
            )
        )
        expected_actions = tuple(
            range(
                expected_pair_start + VISUAL_TOKENS_PER_FRAME,
                expected_pair_end,
            )
        )
        if (
            span.pair_index != span_index
            or getattr(span, "pair_start", None) != expected_pair_start
            or getattr(span, "pair_end_exclusive", None)
            != expected_pair_end
            or span.visual_positions != expected_visual
            or span.action_positions != expected_actions
        ):
            raise VisualTokenSelectionError(
                VisualSelectionErrorCode.MALFORMED_MAP,
                "each span must retain its declared complete "
                "context-relative 336+11 token pair",
            )

    return VisualTokenSelection(
        trajectory_id=trajectory_id,
        model_frame_idx=model_frame_idx,
        positions=selected.visual_positions,
        sequence_length=hooked_sequence_length,
    )


__all__ = [
    "ACTION_TOKENS_PER_FRAME",
    "VisualSelectionErrorCode",
    "VisualTokenSelection",
    "VisualTokenSelectionError",
    "select_visual_token_positions",
]
