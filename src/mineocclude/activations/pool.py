"""Select and mean-pool explicit MineWorld visual-token positions."""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field
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
MEAN_POOLING_IDENTITY = "person-a-visual-token-mean-v1.0"


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


class VisualPoolingErrorCode(str, Enum):
    """Stable failure reasons for visual-token mean pooling."""

    INVALID_ACTIVATION = "invalid_activation"
    INVALID_SHAPE = "invalid_shape"
    INVALID_BATCH_SIZE = "invalid_batch_size"
    INVALID_DTYPE = "invalid_dtype"
    INVALID_SELECTION = "invalid_selection"
    SEQUENCE_LENGTH_MISMATCH = "sequence_length_mismatch"
    INVALID_LAYER_INDEX = "invalid_layer_index"
    INVALID_HOOK_SITE = "invalid_hook_site"
    NONFINITE_SELECTED_VALUE = "nonfinite_selected_value"
    INVALID_RESULT = "invalid_result"


class VisualPoolingError(ValueError):
    """Actionable visual-token pooling failure."""

    def __init__(
        self,
        code: VisualPoolingErrorCode,
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


@dataclass(frozen=True)
class PooledVisualActivation:
    """One independently owned CPU vector for one activation identity."""

    trajectory_id: str
    model_frame_idx: int
    layer_idx: int
    hook_site: str
    vector: object = field(repr=False, compare=False)
    hidden_size: int
    source_batch_size: int
    source_sequence_length: int
    selected_visual_token_count: int
    pooling_operation_identity: str
    source_dtype: str
    source_device: str
    returned_dtype: str
    returned_device: str

    @property
    def key(self) -> tuple[str, int, int, str]:
        """Return the complete scientific activation identity."""

        return (
            self.trajectory_id,
            self.model_frame_idx,
            self.layer_idx,
            self.hook_site,
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


def _validate_pooling_selection(
    selection: object,
    *,
    sequence_length: int,
) -> VisualTokenSelection:
    if not isinstance(selection, VisualTokenSelection):
        raise VisualPoolingError(
            VisualPoolingErrorCode.INVALID_SELECTION,
            "selection must be a validated VisualTokenSelection",
        )
    try:
        if (
            not isinstance(selection.trajectory_id, str)
            or not selection.trajectory_id.strip()
            or not isinstance(selection.model_frame_idx, int)
            or isinstance(selection.model_frame_idx, bool)
            or selection.model_frame_idx < 0
            or not isinstance(selection.sequence_length, int)
            or isinstance(selection.sequence_length, bool)
            or selection.sequence_length <= 0
        ):
            raise VisualTokenSelectionError(
                VisualSelectionErrorCode.INVALID_REQUEST,
                "selection identity and sequence length must be valid",
            )
        _validate_positions(
            selection.positions,
            expected_count=VISUAL_TOKENS_PER_FRAME,
            sequence_length=selection.sequence_length,
            count_code=VisualSelectionErrorCode.INVALID_VISUAL_COUNT,
        )
    except VisualTokenSelectionError as exc:
        raise VisualPoolingError(
            VisualPoolingErrorCode.INVALID_SELECTION,
            str(exc),
        ) from exc
    if selection.sequence_length != sequence_length:
        raise VisualPoolingError(
            VisualPoolingErrorCode.SEQUENCE_LENGTH_MISMATCH,
            "activation and selection sequence lengths must match exactly",
        )
    return selection


def mean_pool_visual_tokens(
    *,
    activation: object,
    selection: VisualTokenSelection,
    layer_idx: int,
    hook_site: str,
) -> PooledVisualActivation:
    """Mean exactly the selection's 336 visual rows into one CPU vector."""

    torch = importlib.import_module("torch")
    if not isinstance(activation, torch.Tensor):
        raise VisualPoolingError(
            VisualPoolingErrorCode.INVALID_ACTIVATION,
            "activation must be a torch.Tensor",
        )
    if activation.ndim != 3:
        raise VisualPoolingError(
            VisualPoolingErrorCode.INVALID_SHAPE,
            "activation must have shape [batch, sequence, hidden]",
        )
    batch_size, sequence_length, hidden_size = activation.shape
    if batch_size != 1:
        raise VisualPoolingError(
            VisualPoolingErrorCode.INVALID_BATCH_SIZE,
            "activation batch size must be exactly 1",
        )
    if sequence_length <= 0 or hidden_size <= 0:
        raise VisualPoolingError(
            VisualPoolingErrorCode.INVALID_SHAPE,
            "activation sequence and hidden dimensions must be positive",
        )
    if not torch.is_floating_point(activation) or activation.is_complex():
        raise VisualPoolingError(
            VisualPoolingErrorCode.INVALID_DTYPE,
            "activation must use a real floating-point dtype",
        )
    validated_selection = _validate_pooling_selection(
        selection,
        sequence_length=sequence_length,
    )
    if (
        not isinstance(layer_idx, int)
        or isinstance(layer_idx, bool)
        or layer_idx < 0
    ):
        raise VisualPoolingError(
            VisualPoolingErrorCode.INVALID_LAYER_INDEX,
            "layer_idx must be a non-negative integer",
        )
    if not isinstance(hook_site, str) or not hook_site.strip():
        raise VisualPoolingError(
            VisualPoolingErrorCode.INVALID_HOOK_SITE,
            "hook_site must be a non-empty explicit string",
        )

    detached = activation.detach()
    try:
        position_index = torch.tensor(
            validated_selection.positions,
            dtype=torch.long,
            device=activation.device,
        )
        selected = detached.index_select(1, position_index)
    except (IndexError, RuntimeError, TypeError, ValueError) as exc:
        raise VisualPoolingError(
            VisualPoolingErrorCode.INVALID_SELECTION,
            f"explicit visual-position selection failed: {exc}",
        ) from exc
    if selected.shape != (1, VISUAL_TOKENS_PER_FRAME, hidden_size):
        raise VisualPoolingError(
            VisualPoolingErrorCode.INVALID_RESULT,
            "selected tensor shape does not preserve batch/token/hidden axes",
        )
    if not bool(torch.isfinite(selected).all().item()):
        raise VisualPoolingError(
            VisualPoolingErrorCode.NONFINITE_SELECTED_VALUE,
            "selected visual-token values must all be finite",
        )

    pooled = (
        selected.to(dtype=torch.float32)
        .mean(dim=1)
        .squeeze(0)
        .to(device="cpu")
        .contiguous()
        .clone()
        .detach()
    )
    del selected
    del position_index
    if (
        pooled.shape != (hidden_size,)
        or pooled.dtype != torch.float32
        or pooled.device.type != "cpu"
        or not pooled.is_contiguous()
        or pooled.requires_grad
        or pooled.grad_fn is not None
        or not bool(torch.isfinite(pooled).all().item())
    ):
        raise VisualPoolingError(
            VisualPoolingErrorCode.INVALID_RESULT,
            "pooled vector failed shape, dtype, ownership, or finiteness checks",
        )

    return PooledVisualActivation(
        trajectory_id=validated_selection.trajectory_id,
        model_frame_idx=validated_selection.model_frame_idx,
        layer_idx=layer_idx,
        hook_site=hook_site,
        vector=pooled,
        hidden_size=hidden_size,
        source_batch_size=batch_size,
        source_sequence_length=sequence_length,
        selected_visual_token_count=VISUAL_TOKENS_PER_FRAME,
        pooling_operation_identity=MEAN_POOLING_IDENTITY,
        source_dtype=str(activation.dtype),
        source_device=str(activation.device),
        returned_dtype=str(pooled.dtype),
        returned_device=str(pooled.device),
    )


__all__ = [
    "ACTION_TOKENS_PER_FRAME",
    "MEAN_POOLING_IDENTITY",
    "PooledVisualActivation",
    "VisualPoolingError",
    "VisualPoolingErrorCode",
    "VisualSelectionErrorCode",
    "VisualTokenSelection",
    "VisualTokenSelectionError",
    "mean_pool_visual_tokens",
    "select_visual_token_positions",
]
