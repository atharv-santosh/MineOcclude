"""Small public boundary between MineOcclude and the MineWorld runtime.

This module freezes Person A's Phase 3.1 API. It deliberately imports no
MineWorld implementation and performs no model loading, preprocessing,
tokenization, or inference. Later Phase 3 steps implement the operations
behind :class:`MineWorldAdapter` without changing downstream callers.

Activation hook selection, pooling, and storage remain separate
``mineocclude.activations`` responsibilities.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, NoReturn, Protocol, runtime_checkable

from mineocclude.contracts.activation import (
    MAX_MODEL_FRAMES,
    TOKENS_PER_FRAME_ACTION_PAIR,
    VISUAL_TOKENS_PER_FRAME,
)
from mineocclude.contracts.identity import (
    CODE_SHA_LENGTH,
    SCHEMA_VERSION,
    SHA256_LENGTH,
)

MINEWORLD_ADAPTER_API_VERSION = "person-a-mineworld-adapter-v1.0"
_ACTION_TOKENS_PER_FRAME = (
    TOKENS_PER_FRAME_ACTION_PAIR - VISUAL_TOKENS_PER_FRAME
)
_HEX = re.compile(r"^[0-9a-fA-F]+$")


class AdapterOperation(str, Enum):
    """Stable names for the seven public adapter responsibilities."""

    LOAD_RUNTIME = "load_runtime"
    VALIDATE_TRAJECTORY = "validate_trajectory"
    PREPROCESS_FRAME = "preprocess_frame"
    CONVERT_ACTION = "convert_action"
    TOKENIZE_TRAJECTORY = "tokenize_trajectory"
    TEACHER_FORCED = "teacher_forced"
    FREE_ROLLOUT = "free_rollout"


class AdapterFailureCode(str, Enum):
    """Stable fail-closed rejection codes at the adapter boundary."""

    INVALID_SCHEMA_VERSION = "invalid_schema_version"
    INVALID_IDENTITY = "invalid_identity"
    INVALID_REQUEST = "invalid_request"
    INVALID_PROVENANCE = "invalid_provenance"
    RUNTIME_EXECUTION_FAILED = "runtime_execution_failed"
    OPERATION_UNAVAILABLE = "operation_unavailable"


class MineWorldAdapterError(RuntimeError):
    """Structured adapter failure with an actionable code and details."""

    def __init__(
        self,
        code: AdapterFailureCode,
        operation: AdapterOperation,
        message: str,
        *,
        details: tuple[tuple[str, str], ...] = (),
    ) -> None:
        if not isinstance(code, AdapterFailureCode):
            raise TypeError("code must be an AdapterFailureCode")
        if not isinstance(operation, AdapterOperation):
            raise TypeError("operation must be an AdapterOperation")
        if not isinstance(message, str) or not message.strip():
            raise TypeError("message must be a non-empty string")
        if not isinstance(details, tuple) or any(
            not isinstance(item, tuple)
            or len(item) != 2
            or not all(isinstance(part, str) and part for part in item)
            for item in details
        ):
            raise TypeError("details must be non-empty string pairs")
        self.code = code
        self.operation = operation
        self.details = details
        super().__init__(f"{code.value}: {operation.value}: {message}")


@dataclass(frozen=True)
class FrameIdentity:
    """The frozen model-analysis key: trajectory_id + model_frame_idx."""

    schema_version: str
    trajectory_id: str
    model_frame_idx: int

    def __post_init__(self) -> None:
        operation = AdapterOperation.VALIDATE_TRAJECTORY
        _schema(self.schema_version, operation)
        _text(self.trajectory_id, "trajectory_id", operation)
        _uint(self.model_frame_idx, "model_frame_idx", operation)

    @property
    def key(self) -> tuple[str, int]:
        return (self.trajectory_id, self.model_frame_idx)


@dataclass(frozen=True)
class RuntimeLoadRequest:
    """Explicit paths and identities required by the Step 3.2 loader."""

    schema_version: str
    runtime_id: str
    mineocclude_revision: str
    mineworld_source_revision: str
    modelscope_asset_revision: str
    mineworld_source_root: Path
    model_config_path: Path
    main_checkpoint_path: Path
    vae_config_path: Path
    vae_checkpoint_path: Path
    model_config_sha256: str
    main_checkpoint_sha256: str
    vae_config_sha256: str
    vae_checkpoint_sha256: str
    environment_report_sha256: str
    precision: str
    device: str

    def __post_init__(self) -> None:
        operation = AdapterOperation.LOAD_RUNTIME
        _schema(self.schema_version, operation)
        _text(self.runtime_id, "runtime_id", operation)
        for name in (
            "mineocclude_revision",
            "mineworld_source_revision",
            "modelscope_asset_revision",
        ):
            _digest(getattr(self, name), CODE_SHA_LENGTH, name, operation)
        for name in (
            "model_config_sha256",
            "main_checkpoint_sha256",
            "vae_config_sha256",
            "vae_checkpoint_sha256",
            "environment_report_sha256",
        ):
            _digest(getattr(self, name), SHA256_LENGTH, name, operation)
        for name in (
            "mineworld_source_root",
            "model_config_path",
            "main_checkpoint_path",
            "vae_config_path",
            "vae_checkpoint_path",
        ):
            _path(getattr(self, name), name, operation)
        _text(self.precision, "precision", operation)
        _text(self.device, "device", operation)


@dataclass(frozen=True)
class MineWorldRuntimeIdentity:
    """Complete project-owned identity for one loaded MineWorld runtime."""

    schema_version: str
    adapter_api_version: str
    runtime_id: str
    mineocclude_revision: str
    mineworld_source_revision: str
    modelscope_asset_revision: str
    model_config_sha256: str
    main_checkpoint_sha256: str
    vae_config_sha256: str
    vae_checkpoint_sha256: str
    environment_report_sha256: str
    preprocessing_identity: str
    action_conversion_identity: str
    model_class: str
    transformer_class: str
    vae_class: str
    decoder_layer_path: str
    layer_count: int
    hidden_size: int
    max_position_embeddings: int
    visual_tokens_per_frame: int
    action_tokens_per_frame: int
    tokens_per_pair: int
    max_context_pairs: int
    precision: str
    device: str

    def __post_init__(self) -> None:
        operation = AdapterOperation.LOAD_RUNTIME
        _schema(self.schema_version, operation)
        if self.adapter_api_version != MINEWORLD_ADAPTER_API_VERSION:
            _fail(
                AdapterFailureCode.INVALID_SCHEMA_VERSION,
                operation,
                "adapter_api_version",
                f"expected {MINEWORLD_ADAPTER_API_VERSION!r}",
            )
        _text(self.runtime_id, "runtime_id", operation)
        for name in (
            "mineocclude_revision",
            "mineworld_source_revision",
            "modelscope_asset_revision",
        ):
            _digest(getattr(self, name), CODE_SHA_LENGTH, name, operation)
        for name in (
            "model_config_sha256",
            "main_checkpoint_sha256",
            "vae_config_sha256",
            "vae_checkpoint_sha256",
            "environment_report_sha256",
        ):
            _digest(getattr(self, name), SHA256_LENGTH, name, operation)
        for name in (
            "preprocessing_identity",
            "action_conversion_identity",
            "model_class",
            "transformer_class",
            "vae_class",
            "decoder_layer_path",
            "precision",
            "device",
        ):
            _text(getattr(self, name), name, operation)
        for name in ("layer_count", "hidden_size", "max_position_embeddings"):
            _positive_int(getattr(self, name), name, operation)
        expected = {
            "visual_tokens_per_frame": VISUAL_TOKENS_PER_FRAME,
            "action_tokens_per_frame": _ACTION_TOKENS_PER_FRAME,
            "tokens_per_pair": TOKENS_PER_FRAME_ACTION_PAIR,
            "max_context_pairs": MAX_MODEL_FRAMES,
        }
        for name, value in expected.items():
            if getattr(self, name) != value:
                _fail(
                    AdapterFailureCode.INVALID_IDENTITY,
                    operation,
                    name,
                    f"expected frozen value {value}",
                )


@dataclass(frozen=True)
class AcceptedTrajectoryInput:
    """Accepted C-to-A package submitted for strict Step 3.3 validation."""

    schema_version: str
    trajectory_id: str
    accepted_manifest_sha256: str
    document: Mapping[str, Any]

    def __post_init__(self) -> None:
        operation = AdapterOperation.VALIDATE_TRAJECTORY
        _schema(self.schema_version, operation)
        _text(self.trajectory_id, "trajectory_id", operation)
        _digest(
            self.accepted_manifest_sha256,
            SHA256_LENGTH,
            "accepted_manifest_sha256",
            operation,
        )
        if not isinstance(self.document, Mapping):
            _fail(
                AdapterFailureCode.INVALID_REQUEST,
                operation,
                "document",
                "must be a mapping",
            )


@dataclass(frozen=True)
class ValidatedTrajectory:
    """Project-owned result of accepted trajectory validation."""

    schema_version: str
    trajectory_id: str
    accepted_manifest_sha256: str
    source_document_sha256: str
    frame_identities: tuple[FrameIdentity, ...]

    def __post_init__(self) -> None:
        operation = AdapterOperation.VALIDATE_TRAJECTORY
        _schema(self.schema_version, operation)
        _text(self.trajectory_id, "trajectory_id", operation)
        _digest(
            self.accepted_manifest_sha256,
            SHA256_LENGTH,
            "accepted_manifest_sha256",
            operation,
        )
        _digest(
            self.source_document_sha256,
            SHA256_LENGTH,
            "source_document_sha256",
            operation,
        )
        _frame_identities(self.frame_identities, self.trajectory_id, operation)


@dataclass(frozen=True)
class FramePreprocessRequest:
    """One accepted source frame submitted to the Step 3.4 preprocessor."""

    identity: FrameIdentity
    source_frame_idx: int
    frame: object

    def __post_init__(self) -> None:
        operation = AdapterOperation.PREPROCESS_FRAME
        _frame_identity(self.identity, operation)
        _uint(self.source_frame_idx, "source_frame_idx", operation)
        _payload(self.frame, "frame", operation)


@dataclass(frozen=True)
class PreprocessedFrame:
    """Project-owned preprocessed frame and byte-level identity."""

    identity: FrameIdentity
    source_frame_idx: int
    shape: tuple[int, int, int]
    dtype: str
    color_order: str
    content_sha256: str
    frame: object
    source_shape: tuple[int, int, int] | None = None
    source_dtype: str | None = None
    color_conversion: str | None = None
    interpolation: str | None = None
    preprocessing_profile: str | None = None
    source_sha256: str | None = None
    statistics: tuple[tuple[str, float], ...] = ()

    def __post_init__(self) -> None:
        operation = AdapterOperation.PREPROCESS_FRAME
        _frame_identity(self.identity, operation)
        _uint(self.source_frame_idx, "source_frame_idx", operation)
        if (
            not isinstance(self.shape, tuple)
            or len(self.shape) != 3
            or any(type(value) is not int or value <= 0 for value in self.shape)
        ):
            _fail(
                AdapterFailureCode.INVALID_REQUEST,
                operation,
                "shape",
                "must contain three positive integer dimensions",
            )
        _text(self.dtype, "dtype", operation)
        _text(self.color_order, "color_order", operation)
        _digest(
            self.content_sha256,
            SHA256_LENGTH,
            "content_sha256",
            operation,
        )
        _payload(self.frame, "frame", operation)
        if self.source_shape is not None and (
            not isinstance(self.source_shape, tuple)
            or len(self.source_shape) != 3
            or any(
                type(value) is not int or value <= 0
                for value in self.source_shape
            )
        ):
            _fail(
                AdapterFailureCode.INVALID_REQUEST,
                operation,
                "source_shape",
                "must contain three positive integer dimensions",
            )
        for field, value in (
            ("source_dtype", self.source_dtype),
            ("color_conversion", self.color_conversion),
            ("interpolation", self.interpolation),
            ("preprocessing_profile", self.preprocessing_profile),
        ):
            if value is not None:
                _text(value, field, operation)
        if self.source_sha256 is not None:
            _digest(
                self.source_sha256,
                SHA256_LENGTH,
                "source_sha256",
                operation,
            )
        if (
            not isinstance(self.statistics, tuple)
            or any(
                not isinstance(item, tuple)
                or len(item) != 2
                or not isinstance(item[0], str)
                or not item[0]
                or isinstance(item[1], bool)
                or not isinstance(item[1], (int, float))
                or not math.isfinite(float(item[1]))
                for item in self.statistics
            )
        ):
            _fail(
                AdapterFailureCode.INVALID_REQUEST,
                operation,
                "statistics",
                "must contain finite named values",
            )


@dataclass(frozen=True)
class ActionConversionRequest:
    """One accepted raw action submitted to the Step 3.5 converter."""

    identity: FrameIdentity
    action_idx: int
    raw_action: Mapping[str, Any]

    def __post_init__(self) -> None:
        operation = AdapterOperation.CONVERT_ACTION
        _frame_identity(self.identity, operation)
        _uint(self.action_idx, "action_idx", operation)
        if not isinstance(self.raw_action, Mapping):
            _fail(
                AdapterFailureCode.INVALID_REQUEST,
                operation,
                "raw_action",
                "must be a mapping",
            )


@dataclass(frozen=True)
class ConvertedAction:
    """Official action tokens with source-row identity."""

    identity: FrameIdentity
    action_idx: int
    token_ids: tuple[int, ...]
    converter_identity: str
    content_sha256: str
    raw_action_sha256: str | None = None
    normalized_action: Mapping[str, Any] | None = None
    vocabulary_offset: int | None = None
    positional_roles: tuple[str, ...] = ()
    converter_source_revision: str | None = None
    is_noop: bool | None = None

    def __post_init__(self) -> None:
        operation = AdapterOperation.CONVERT_ACTION
        _frame_identity(self.identity, operation)
        _uint(self.action_idx, "action_idx", operation)
        _tokens(
            self.token_ids,
            "token_ids",
            operation,
            count=_ACTION_TOKENS_PER_FRAME,
        )
        _text(self.converter_identity, "converter_identity", operation)
        _digest(
            self.content_sha256,
            SHA256_LENGTH,
            "content_sha256",
            operation,
        )
        if self.raw_action_sha256 is not None:
            _digest(
                self.raw_action_sha256,
                SHA256_LENGTH,
                "raw_action_sha256",
                operation,
            )
        if self.normalized_action is not None and not isinstance(
            self.normalized_action, Mapping
        ):
            _fail(
                AdapterFailureCode.INVALID_REQUEST,
                operation,
                "normalized_action",
                "must be a mapping",
            )
        if self.vocabulary_offset is not None:
            _uint(self.vocabulary_offset, "vocabulary_offset", operation)
        if (
            not isinstance(self.positional_roles, tuple)
            or any(
                not isinstance(role, str) or not role.strip()
                for role in self.positional_roles
            )
            or (
                self.positional_roles
                and len(self.positional_roles) != len(self.token_ids)
            )
        ):
            _fail(
                AdapterFailureCode.INVALID_REQUEST,
                operation,
                "positional_roles",
                "must contain one non-empty role name per token when present",
            )
        if self.converter_source_revision is not None:
            _digest(
                self.converter_source_revision,
                CODE_SHA_LENGTH,
                "converter_source_revision",
                operation,
            )
        if self.is_noop is not None and not isinstance(self.is_noop, bool):
            _fail(
                AdapterFailureCode.INVALID_REQUEST,
                operation,
                "is_noop",
                "must be boolean",
            )


@dataclass(frozen=True)
class FrameTokenSpan:
    """One model frame's exact visual and action token positions."""

    identity: FrameIdentity
    pair_index: int
    visual_positions: tuple[int, ...]
    action_positions: tuple[int, ...]
    accepted_pair_index: int | None = None
    pair_start: int | None = None
    pair_end_exclusive: int | None = None
    causal_predecessor: FrameIdentity | None = None
    causal_successor: FrameIdentity | None = None
    included_in_context: bool = True

    def __post_init__(self) -> None:
        operation = AdapterOperation.TOKENIZE_TRAJECTORY
        _frame_identity(self.identity, operation)
        _uint(self.pair_index, "pair_index", operation)
        _positions(
            self.visual_positions,
            "visual_positions",
            VISUAL_TOKENS_PER_FRAME,
            operation,
        )
        _positions(
            self.action_positions,
            "action_positions",
            _ACTION_TOKENS_PER_FRAME,
            operation,
        )
        if set(self.visual_positions) & set(self.action_positions):
            _fail(
                AdapterFailureCode.INVALID_IDENTITY,
                operation,
                "visual_positions/action_positions",
                "positions must be disjoint",
            )
        expected_start = self.pair_index * TOKENS_PER_FRAME_ACTION_PAIR
        expected_visual = tuple(
            range(expected_start, expected_start + VISUAL_TOKENS_PER_FRAME)
        )
        expected_action = tuple(
            range(
                expected_start + VISUAL_TOKENS_PER_FRAME,
                expected_start + TOKENS_PER_FRAME_ACTION_PAIR,
            )
        )
        if (
            self.visual_positions != expected_visual
            or self.action_positions != expected_action
        ):
            _fail(
                AdapterFailureCode.INVALID_IDENTITY,
                operation,
                "visual_positions/action_positions",
                "must be one complete visual-then-action pair",
            )
        if self.accepted_pair_index is not None:
            _uint(self.accepted_pair_index, "accepted_pair_index", operation)
        if self.pair_start is not None and self.pair_start != expected_start:
            _fail(
                AdapterFailureCode.INVALID_IDENTITY,
                operation,
                "pair_start",
                f"must equal {expected_start}",
            )
        expected_end = expected_start + TOKENS_PER_FRAME_ACTION_PAIR
        if (
            self.pair_end_exclusive is not None
            and self.pair_end_exclusive != expected_end
        ):
            _fail(
                AdapterFailureCode.INVALID_IDENTITY,
                operation,
                "pair_end_exclusive",
                f"must equal {expected_end}",
            )
        for field, neighbor in (
            ("causal_predecessor", self.causal_predecessor),
            ("causal_successor", self.causal_successor),
        ):
            if neighbor is not None:
                _frame_identity(neighbor, operation)
                if (
                    neighbor.trajectory_id != self.identity.trajectory_id
                    or neighbor.key == self.identity.key
                ):
                    _fail(
                        AdapterFailureCode.INVALID_IDENTITY,
                        operation,
                        field,
                        "must identify a different frame in the same trajectory",
                    )
        if self.included_in_context is not True:
            _fail(
                AdapterFailureCode.INVALID_IDENTITY,
                operation,
                "included_in_context",
                "FrameTokenSpan values represent included context only",
            )


@dataclass(frozen=True)
class FrameTokenMap:
    """Complete frame-to-token map for one MineWorld sequence."""

    schema_version: str
    trajectory_id: str
    sequence_length: int
    spans: tuple[FrameTokenSpan, ...]
    excluded_frame_identities: tuple[FrameIdentity, ...] = ()

    def __post_init__(self) -> None:
        operation = AdapterOperation.TOKENIZE_TRAJECTORY
        _schema(self.schema_version, operation)
        _text(self.trajectory_id, "trajectory_id", operation)
        _positive_int(self.sequence_length, "sequence_length", operation)
        if (
            not isinstance(self.spans, tuple)
            or not self.spans
            or not all(isinstance(span, FrameTokenSpan) for span in self.spans)
            or len(self.spans) > MAX_MODEL_FRAMES
        ):
            _fail(
                AdapterFailureCode.INVALID_REQUEST,
                operation,
                "spans",
                f"must contain 1..{MAX_MODEL_FRAMES} FrameTokenSpan values",
            )
        keys = [span.identity.key for span in self.spans]
        pair_indices = [span.pair_index for span in self.spans]
        all_positions = [
            position
            for span in self.spans
            for position in span.visual_positions + span.action_positions
        ]
        if any(span.identity.trajectory_id != self.trajectory_id for span in self.spans):
            _fail(
                AdapterFailureCode.INVALID_IDENTITY,
                operation,
                "spans.identity",
                "trajectory_id must match the map",
            )
        if len(keys) != len(set(keys)) or len(pair_indices) != len(set(pair_indices)):
            _fail(
                AdapterFailureCode.INVALID_IDENTITY,
                operation,
                "spans",
                "frame identities and pair indices must be unique",
            )
        if pair_indices != list(range(len(self.spans))):
            _fail(
                AdapterFailureCode.INVALID_IDENTITY,
                operation,
                "spans.pair_index",
                "must be consecutive context-relative indices starting at zero",
            )
        if len(all_positions) != len(set(all_positions)):
            _fail(
                AdapterFailureCode.INVALID_IDENTITY,
                operation,
                "spans",
                "token positions must not overlap",
            )
        if (
            self.sequence_length
            != len(self.spans) * TOKENS_PER_FRAME_ACTION_PAIR
            or all_positions != list(range(self.sequence_length))
        ):
            _fail(
                AdapterFailureCode.INVALID_IDENTITY,
                operation,
                "spans",
                "must cover the complete sequence exactly once in order",
            )
        if (
            not isinstance(self.excluded_frame_identities, tuple)
            or any(
                not isinstance(identity, FrameIdentity)
                for identity in self.excluded_frame_identities
            )
        ):
            _fail(
                AdapterFailureCode.INVALID_IDENTITY,
                operation,
                "excluded_frame_identities",
                "must be a tuple of FrameIdentity values",
            )
        excluded_keys = [
            identity.key for identity in self.excluded_frame_identities
        ]
        if (
            len(excluded_keys) != len(set(excluded_keys))
            or set(excluded_keys) & set(keys)
            or any(
                identity.trajectory_id != self.trajectory_id
                for identity in self.excluded_frame_identities
            )
        ):
            _fail(
                AdapterFailureCode.INVALID_IDENTITY,
                operation,
                "excluded_frame_identities",
                "must be unique, disjoint, and belong to this trajectory",
            )


@dataclass(frozen=True)
class TrajectoryTokenizationRequest:
    """Validated components submitted to Step 3.6 sequence construction."""

    runtime_identity: MineWorldRuntimeIdentity
    trajectory: ValidatedTrajectory
    frames: tuple[PreprocessedFrame, ...]
    actions: tuple[ConvertedAction, ...]

    def __post_init__(self) -> None:
        operation = AdapterOperation.TOKENIZE_TRAJECTORY
        _runtime_identity(self.runtime_identity, operation)
        if not isinstance(self.trajectory, ValidatedTrajectory):
            _fail(
                AdapterFailureCode.INVALID_REQUEST,
                operation,
                "trajectory",
                "must be a ValidatedTrajectory",
            )
        if (
            not isinstance(self.frames, tuple)
            or not self.frames
            or not all(isinstance(item, PreprocessedFrame) for item in self.frames)
            or not isinstance(self.actions, tuple)
            or not self.actions
            or not all(isinstance(item, ConvertedAction) for item in self.actions)
        ):
            _fail(
                AdapterFailureCode.INVALID_REQUEST,
                operation,
                "frames/actions",
                "must be non-empty tuples of preprocessed frames and actions",
            )
        expected = tuple(item.key for item in self.trajectory.frame_identities)
        frame_keys = tuple(item.identity.key for item in self.frames)
        action_keys = tuple(item.identity.key for item in self.actions)
        if frame_keys != expected or action_keys != expected:
            _fail(
                AdapterFailureCode.INVALID_IDENTITY,
                operation,
                "frames/actions",
                "must exactly preserve validated frame identity and order",
            )


@dataclass(frozen=True)
class TokenizedTrajectory:
    """Project-owned sequence with explicit source-frame positions."""

    runtime_identity: MineWorldRuntimeIdentity
    trajectory_id: str
    token_ids: tuple[int, ...]
    frame_token_map: FrameTokenMap
    token_sha256: str
    attention_mask: tuple[int, ...] = ()
    position_ids: tuple[int, ...] = ()
    included_frame_identities: tuple[FrameIdentity, ...] = ()
    excluded_frame_identities: tuple[FrameIdentity, ...] = ()
    tokenization_profile: str | None = None
    preprocessing_profile: str | None = None
    action_conversion_profile: str | None = None
    frame_token_map_sha256: str | None = None
    accepted_frame_count: int | None = None
    context_pair_count: int | None = None

    def __post_init__(self) -> None:
        operation = AdapterOperation.TOKENIZE_TRAJECTORY
        _runtime_identity(self.runtime_identity, operation)
        _text(self.trajectory_id, "trajectory_id", operation)
        _tokens(self.token_ids, "token_ids", operation)
        if (
            not isinstance(self.frame_token_map, FrameTokenMap)
            or self.frame_token_map.trajectory_id != self.trajectory_id
            or self.frame_token_map.sequence_length != len(self.token_ids)
        ):
            _fail(
                AdapterFailureCode.INVALID_IDENTITY,
                operation,
                "frame_token_map",
                "must match trajectory_id and token sequence length",
            )
        if len(self.token_ids) > self.runtime_identity.max_position_embeddings:
            _fail(
                AdapterFailureCode.INVALID_REQUEST,
                operation,
                "token_ids",
                "sequence exceeds max_position_embeddings",
            )
        _digest(self.token_sha256, SHA256_LENGTH, "token_sha256", operation)
        if self.attention_mask and (
            len(self.attention_mask) != len(self.token_ids)
            or any(value != 1 for value in self.attention_mask)
        ):
            _fail(
                AdapterFailureCode.INVALID_REQUEST,
                operation,
                "attention_mask",
                "must mark every unpadded sequence position with one",
            )
        if self.position_ids and self.position_ids != tuple(
            range(len(self.token_ids))
        ):
            _fail(
                AdapterFailureCode.INVALID_REQUEST,
                operation,
                "position_ids",
                "must be consecutive context-relative positions",
            )
        for field, values in (
            ("included_frame_identities", self.included_frame_identities),
            ("excluded_frame_identities", self.excluded_frame_identities),
        ):
            if values:
                _frame_identities(values, self.trajectory_id, operation)
        if self.included_frame_identities and tuple(
            span.identity for span in self.frame_token_map.spans
        ) != self.included_frame_identities:
            _fail(
                AdapterFailureCode.INVALID_IDENTITY,
                operation,
                "included_frame_identities",
                "must exactly match FrameTokenMap span order",
            )
        if (
            self.excluded_frame_identities
            and self.excluded_frame_identities
            != self.frame_token_map.excluded_frame_identities
        ):
            _fail(
                AdapterFailureCode.INVALID_IDENTITY,
                operation,
                "excluded_frame_identities",
                "must exactly match FrameTokenMap exclusions",
            )
        for field, value in (
            ("tokenization_profile", self.tokenization_profile),
            ("preprocessing_profile", self.preprocessing_profile),
            ("action_conversion_profile", self.action_conversion_profile),
        ):
            if value is not None:
                _text(value, field, operation)
        if self.frame_token_map_sha256 is not None:
            _digest(
                self.frame_token_map_sha256,
                SHA256_LENGTH,
                "frame_token_map_sha256",
                operation,
            )
        if self.accepted_frame_count is not None:
            _positive_int(
                self.accepted_frame_count, "accepted_frame_count", operation
            )
        if self.context_pair_count is not None:
            _positive_int(
                self.context_pair_count, "context_pair_count", operation
            )
            if self.context_pair_count != len(self.frame_token_map.spans):
                _fail(
                    AdapterFailureCode.INVALID_IDENTITY,
                    operation,
                    "context_pair_count",
                    "must equal the FrameTokenMap span count",
                )


@dataclass(frozen=True)
class TeacherForcedRequest:
    """Explicit Step 3.7 request; it never implies a free rollout."""

    runtime_identity: MineWorldRuntimeIdentity
    trajectory: TokenizedTrajectory
    seed: int
    precision: str
    batch_size: int = 1
    hook_context_factory: (
        Callable[
            [tuple[tuple[str, object], ...]],
            AbstractContextManager[object],
        ]
        | None
    ) = None

    def __post_init__(self) -> None:
        operation = AdapterOperation.TEACHER_FORCED
        _runtime_and_tokens(self.runtime_identity, self.trajectory, operation)
        _uint(self.seed, "seed", operation)
        _text(self.precision, "precision", operation)
        _positive_int(self.batch_size, "batch_size", operation)
        if self.hook_context_factory is not None and not callable(
            self.hook_context_factory
        ):
            _fail(
                AdapterFailureCode.INVALID_REQUEST,
                operation,
                "hook_context_factory",
                "must be callable when provided",
            )


@dataclass(frozen=True)
class TeacherForcedResult:
    """Step 3.7 output metadata without activation-hook policy."""

    runtime_identity: MineWorldRuntimeIdentity
    trajectory_id: str
    frame_token_map: FrameTokenMap
    output_shape: tuple[int, ...]
    dtype: str
    device: str
    output_sha256: str
    elapsed_seconds: float
    output: object
    token_sha256: str | None = None
    frame_token_map_sha256: str | None = None
    seed: int | None = None
    batch_size: int | None = None
    input_sequence_length: int | None = None
    included_frame_identities: tuple[FrameIdentity, ...] = ()
    excluded_frame_identities: tuple[FrameIdentity, ...] = ()
    output_statistics: tuple[tuple[str, float], ...] = ()
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        operation = AdapterOperation.TEACHER_FORCED
        _runtime_identity(self.runtime_identity, operation)
        _text(self.trajectory_id, "trajectory_id", operation)
        if (
            not isinstance(self.frame_token_map, FrameTokenMap)
            or self.frame_token_map.trajectory_id != self.trajectory_id
        ):
            _fail(
                AdapterFailureCode.INVALID_IDENTITY,
                operation,
                "frame_token_map",
                "must match trajectory_id",
            )
        if (
            not isinstance(self.output_shape, tuple)
            or not self.output_shape
            or any(type(value) is not int or value <= 0 for value in self.output_shape)
        ):
            _fail(
                AdapterFailureCode.INVALID_REQUEST,
                operation,
                "output_shape",
                "must contain positive dimensions",
            )
        _text(self.dtype, "dtype", operation)
        _text(self.device, "device", operation)
        _digest(self.output_sha256, SHA256_LENGTH, "output_sha256", operation)
        _nonnegative_real(self.elapsed_seconds, "elapsed_seconds", operation)
        _payload(self.output, "output", operation)
        for field, digest in (
            ("token_sha256", self.token_sha256),
            ("frame_token_map_sha256", self.frame_token_map_sha256),
        ):
            if digest is not None:
                _digest(digest, SHA256_LENGTH, field, operation)
        if self.seed is not None:
            _uint(self.seed, "seed", operation)
        if self.batch_size is not None:
            _positive_int(self.batch_size, "batch_size", operation)
        if self.input_sequence_length is not None:
            _positive_int(
                self.input_sequence_length,
                "input_sequence_length",
                operation,
            )
            if self.input_sequence_length != self.frame_token_map.sequence_length:
                _fail(
                    AdapterFailureCode.INVALID_IDENTITY,
                    operation,
                    "input_sequence_length",
                    "must equal FrameTokenMap.sequence_length",
                )
        for field, values in (
            ("included_frame_identities", self.included_frame_identities),
            ("excluded_frame_identities", self.excluded_frame_identities),
        ):
            if values:
                _frame_identities(values, self.trajectory_id, operation)
        if (
            not isinstance(self.output_statistics, tuple)
            or any(
                not isinstance(item, tuple)
                or len(item) != 2
                or not isinstance(item[0], str)
                or not item[0]
                or isinstance(item[1], bool)
                or not isinstance(item[1], (int, float))
                or not math.isfinite(float(item[1]))
                for item in self.output_statistics
            )
        ):
            _fail(
                AdapterFailureCode.INVALID_REQUEST,
                operation,
                "output_statistics",
                "must contain finite named values",
            )
        if (
            not isinstance(self.warnings, tuple)
            or any(
                not isinstance(warning, str) or not warning.strip()
                for warning in self.warnings
            )
        ):
            _fail(
                AdapterFailureCode.INVALID_REQUEST,
                operation,
                "warnings",
                "must contain non-empty strings",
            )


@dataclass(frozen=True)
class FreeRolloutRequest:
    """Explicit Step 3.8 request; it never invokes teacher forcing."""

    runtime_identity: MineWorldRuntimeIdentity
    context: TokenizedTrajectory
    run_id: str
    seed: int
    generated_frame_count: int
    output_directory: Path
    generation_config_sha256: str

    def __post_init__(self) -> None:
        operation = AdapterOperation.FREE_ROLLOUT
        _runtime_and_tokens(self.runtime_identity, self.context, operation)
        _text(self.run_id, "run_id", operation)
        _uint(self.seed, "seed", operation)
        _positive_int(
            self.generated_frame_count,
            "generated_frame_count",
            operation,
        )
        _path(self.output_directory, "output_directory", operation)
        _digest(
            self.generation_config_sha256,
            SHA256_LENGTH,
            "generation_config_sha256",
            operation,
        )


@dataclass(frozen=True)
class FreeRolloutResult:
    """Durable output identity for one Step 3.8 rollout."""

    runtime_identity: MineWorldRuntimeIdentity
    trajectory_id: str
    run_id: str
    generated_frame_count: int
    video_path: Path
    video_sha256: str
    metadata_path: Path
    metadata_sha256: str
    elapsed_seconds: float

    def __post_init__(self) -> None:
        operation = AdapterOperation.FREE_ROLLOUT
        _runtime_identity(self.runtime_identity, operation)
        _text(self.trajectory_id, "trajectory_id", operation)
        _text(self.run_id, "run_id", operation)
        _positive_int(
            self.generated_frame_count,
            "generated_frame_count",
            operation,
        )
        _path(self.video_path, "video_path", operation)
        _path(self.metadata_path, "metadata_path", operation)
        _digest(self.video_sha256, SHA256_LENGTH, "video_sha256", operation)
        _digest(
            self.metadata_sha256,
            SHA256_LENGTH,
            "metadata_sha256",
            operation,
        )
        _nonnegative_real(self.elapsed_seconds, "elapsed_seconds", operation)


@runtime_checkable
class MineWorldAdapter(Protocol):
    """Stable downstream dependency surface implemented across Phase 3."""

    def load_runtime(
        self, request: RuntimeLoadRequest
    ) -> MineWorldRuntimeIdentity: ...

    def validate_trajectory(
        self, request: AcceptedTrajectoryInput
    ) -> ValidatedTrajectory: ...

    def preprocess_frame(
        self, request: FramePreprocessRequest
    ) -> PreprocessedFrame: ...

    def convert_action(
        self, request: ActionConversionRequest
    ) -> ConvertedAction: ...

    def tokenize_trajectory(
        self, request: TrajectoryTokenizationRequest
    ) -> TokenizedTrajectory: ...

    def teacher_forced(
        self, request: TeacherForcedRequest
    ) -> TeacherForcedResult: ...

    def free_rollout(
        self, request: FreeRolloutRequest
    ) -> FreeRolloutResult: ...


class UnavailableMineWorldAdapter:
    """Executable Phase 3.1 boundary that never pretends runtime work passed."""

    def load_runtime(
        self, request: RuntimeLoadRequest
    ) -> MineWorldRuntimeIdentity:
        _unavailable(
            AdapterOperation.LOAD_RUNTIME, request, RuntimeLoadRequest, "Step 3.2"
        )

    def validate_trajectory(
        self, request: AcceptedTrajectoryInput
    ) -> ValidatedTrajectory:
        _unavailable(
            AdapterOperation.VALIDATE_TRAJECTORY,
            request,
            AcceptedTrajectoryInput,
            "Step 3.3",
        )

    def preprocess_frame(
        self, request: FramePreprocessRequest
    ) -> PreprocessedFrame:
        _unavailable(
            AdapterOperation.PREPROCESS_FRAME,
            request,
            FramePreprocessRequest,
            "Step 3.4",
        )

    def convert_action(
        self, request: ActionConversionRequest
    ) -> ConvertedAction:
        _unavailable(
            AdapterOperation.CONVERT_ACTION,
            request,
            ActionConversionRequest,
            "Step 3.5",
        )

    def tokenize_trajectory(
        self, request: TrajectoryTokenizationRequest
    ) -> TokenizedTrajectory:
        _unavailable(
            AdapterOperation.TOKENIZE_TRAJECTORY,
            request,
            TrajectoryTokenizationRequest,
            "Step 3.6",
        )

    def teacher_forced(
        self, request: TeacherForcedRequest
    ) -> TeacherForcedResult:
        _unavailable(
            AdapterOperation.TEACHER_FORCED,
            request,
            TeacherForcedRequest,
            "Step 3.7",
        )

    def free_rollout(
        self, request: FreeRolloutRequest
    ) -> FreeRolloutResult:
        _unavailable(
            AdapterOperation.FREE_ROLLOUT,
            request,
            FreeRolloutRequest,
            "Step 3.8",
        )


def create_mineworld_adapter() -> MineWorldAdapter:
    """Construct the private Wave 3 implementation behind the frozen protocol."""

    from mineocclude.models._mineworld_adapter_wave3 import (
        _Wave3MineWorldAdapter,
    )

    return _Wave3MineWorldAdapter()


def _unavailable(
    operation: AdapterOperation,
    request: object,
    request_type: type[object],
    roadmap_step: str,
) -> NoReturn:
    if not isinstance(request, request_type):
        _fail(
            AdapterFailureCode.INVALID_REQUEST,
            operation,
            "request",
            f"must be {request_type.__name__}",
        )
    raise MineWorldAdapterError(
        AdapterFailureCode.OPERATION_UNAVAILABLE,
        operation,
        f"implementation is intentionally unavailable until Person A {roadmap_step}",
        details=(("roadmap_step", roadmap_step),),
    )


def _fail(
    code: AdapterFailureCode,
    operation: AdapterOperation,
    field: str,
    issue: str,
) -> NoReturn:
    raise MineWorldAdapterError(
        code,
        operation,
        f"{field}: {issue}",
        details=((field, issue),),
    )


def _schema(value: object, operation: AdapterOperation) -> None:
    if value != SCHEMA_VERSION:
        _fail(
            AdapterFailureCode.INVALID_SCHEMA_VERSION,
            operation,
            "schema_version",
            f"must equal {SCHEMA_VERSION!r}",
        )


def _text(value: object, field: str, operation: AdapterOperation) -> None:
    if not isinstance(value, str) or not value.strip():
        _fail(
            AdapterFailureCode.INVALID_REQUEST,
            operation,
            field,
            "must be a non-empty string",
        )


def _digest(
    value: object,
    length: int,
    field: str,
    operation: AdapterOperation,
) -> None:
    if (
        not isinstance(value, str)
        or len(value) != length
        or _HEX.fullmatch(value) is None
    ):
        _fail(
            AdapterFailureCode.INVALID_PROVENANCE,
            operation,
            field,
            f"must be a {length}-character hexadecimal identity",
        )


def _path(value: object, field: str, operation: AdapterOperation) -> None:
    if not isinstance(value, Path) or not str(value):
        _fail(
            AdapterFailureCode.INVALID_REQUEST,
            operation,
            field,
            "must be a pathlib.Path",
        )


def _uint(value: object, field: str, operation: AdapterOperation) -> None:
    if type(value) is not int or value < 0:
        _fail(
            AdapterFailureCode.INVALID_REQUEST,
            operation,
            field,
            "must be a non-negative integer",
        )


def _positive_int(value: object, field: str, operation: AdapterOperation) -> None:
    if type(value) is not int or value <= 0:
        _fail(
            AdapterFailureCode.INVALID_REQUEST,
            operation,
            field,
            "must be a positive integer",
        )


def _nonnegative_real(
    value: object, field: str, operation: AdapterOperation
) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or value < 0
    ):
        _fail(
            AdapterFailureCode.INVALID_REQUEST,
            operation,
            field,
            "must be a finite non-negative real number",
        )


def _payload(value: object, field: str, operation: AdapterOperation) -> None:
    if value is None:
        _fail(
            AdapterFailureCode.INVALID_REQUEST,
            operation,
            field,
            "must not be None",
        )


def _frame_identity(value: object, operation: AdapterOperation) -> None:
    if not isinstance(value, FrameIdentity):
        _fail(
            AdapterFailureCode.INVALID_IDENTITY,
            operation,
            "identity",
            "must be a FrameIdentity",
        )


def _runtime_identity(value: object, operation: AdapterOperation) -> None:
    if not isinstance(value, MineWorldRuntimeIdentity):
        _fail(
            AdapterFailureCode.INVALID_IDENTITY,
            operation,
            "runtime_identity",
            "must be a MineWorldRuntimeIdentity",
        )


def _frame_identities(
    values: object,
    trajectory_id: str,
    operation: AdapterOperation,
) -> None:
    if (
        not isinstance(values, tuple)
        or not values
        or not all(isinstance(value, FrameIdentity) for value in values)
    ):
        _fail(
            AdapterFailureCode.INVALID_IDENTITY,
            operation,
            "frame_identities",
            "must be a non-empty tuple of FrameIdentity values",
        )
    keys = [value.key for value in values]
    if (
        any(value.trajectory_id != trajectory_id for value in values)
        or len(keys) != len(set(keys))
    ):
        _fail(
            AdapterFailureCode.INVALID_IDENTITY,
            operation,
            "frame_identities",
            "must have matching trajectory IDs and unique frame keys",
        )


def _tokens(
    values: object,
    field: str,
    operation: AdapterOperation,
    *,
    count: int | None = None,
) -> None:
    if (
        not isinstance(values, tuple)
        or not values
        or any(type(value) is not int or value < 0 for value in values)
        or (count is not None and len(values) != count)
    ):
        suffix = f" and contain exactly {count} values" if count is not None else ""
        _fail(
            AdapterFailureCode.INVALID_REQUEST,
            operation,
            field,
            f"must be non-negative integer token IDs{suffix}",
        )


def _positions(
    values: object,
    field: str,
    count: int,
    operation: AdapterOperation,
) -> None:
    if (
        not isinstance(values, tuple)
        or len(values) != count
        or any(type(value) is not int or value < 0 for value in values)
        or tuple(sorted(set(values))) != values
    ):
        _fail(
            AdapterFailureCode.INVALID_IDENTITY,
            operation,
            field,
            f"must contain {count} unique increasing non-negative positions",
        )


def _runtime_and_tokens(
    runtime: object,
    trajectory: object,
    operation: AdapterOperation,
) -> None:
    _runtime_identity(runtime, operation)
    if not isinstance(trajectory, TokenizedTrajectory):
        _fail(
            AdapterFailureCode.INVALID_REQUEST,
            operation,
            "trajectory",
            "must be a TokenizedTrajectory",
        )
    if trajectory.runtime_identity != runtime:
        _fail(
            AdapterFailureCode.INVALID_IDENTITY,
            operation,
            "trajectory.runtime_identity",
            "must exactly match the request runtime identity",
        )


__all__ = [
    "MINEWORLD_ADAPTER_API_VERSION",
    "AcceptedTrajectoryInput",
    "ActionConversionRequest",
    "AdapterFailureCode",
    "AdapterOperation",
    "ConvertedAction",
    "FrameIdentity",
    "FramePreprocessRequest",
    "FrameTokenMap",
    "FrameTokenSpan",
    "FreeRolloutRequest",
    "FreeRolloutResult",
    "MineWorldAdapter",
    "MineWorldAdapterError",
    "MineWorldRuntimeIdentity",
    "PreprocessedFrame",
    "RuntimeLoadRequest",
    "TeacherForcedRequest",
    "TeacherForcedResult",
    "TokenizedTrajectory",
    "TrajectoryTokenizationRequest",
    "UnavailableMineWorldAdapter",
    "ValidatedTrajectory",
    "create_mineworld_adapter",
]
