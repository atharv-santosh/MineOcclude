"""Private Person A Phase 3 Wave 3 tokenization and teacher forcing.

The public contract remains in :mod:`mineocclude.models.mineworld_adapter`.
This module implements Steps 3.6 and 3.7 behind that contract without owning
activation-hook selection, pooling, storage, rollout, or scientific analysis.
"""

from __future__ import annotations

import hashlib
import importlib
import math
import random
import time
from collections.abc import Callable, Mapping, Sequence
from contextlib import nullcontext
from dataclasses import dataclass
from typing import Any

from mineocclude.contracts.activation import (
    MAX_MODEL_FRAMES,
    TOKENS_PER_FRAME_ACTION_PAIR,
)
from mineocclude.contracts.identity import SCHEMA_VERSION
from mineocclude.models._mineworld_adapter_wave2 import (
    ACTION_CONVERTER_IDENTITY,
    ACTION_POSITIONAL_ROLES,
    ACTION_VOCABULARY_OFFSET,
    PINNED_ACTION_TOKENS,
    PINNED_DEVICE,
    PINNED_PRECISION,
    PINNED_PROCESSED_VIDEO_HEIGHT,
    PINNED_PROCESSED_VIDEO_WIDTH,
    PINNED_SOURCE_REVISION,
    PINNED_TOKENS_PER_PAIR,
    PINNED_VISUAL_TOKENS,
    PINNED_VOCAB_SIZE,
    PREPROCESSING_PROFILE,
    _adapter_error,
    _LoadedRuntime,
    _Wave2MineWorldAdapter,
)
from mineocclude.models.mineworld_adapter import (
    AdapterFailureCode,
    AdapterOperation,
    FrameIdentity,
    FrameTokenMap,
    FrameTokenSpan,
    MineWorldAdapterError,
    MineWorldRuntimeIdentity,
    PreprocessedFrame,
    TeacherForcedRequest,
    TeacherForcedResult,
    TokenizedTrajectory,
    TrajectoryTokenizationRequest,
)
from mineocclude.models.phase2_evidence import canonical_json_bytes

VISUAL_VOCABULARY_SIZE = ACTION_VOCABULARY_OFFSET
TOKENIZATION_PROFILE = (
    "mineworld-700m-16f-interleaved-v1.0:"
    f"{PINNED_SOURCE_REVISION}:vae.py#VAE.tokenize_images"
)
TEACHER_FORCED_PROFILE = (
    "mineworld-700m-16f-teacher-forced-v1.0:"
    f"{PINNED_SOURCE_REVISION}:lvm.py#LlamaForCausalLM.forward"
)


@dataclass(frozen=True)
class _TeacherExecution:
    output: object
    output_shape: tuple[int, ...]
    dtype: str
    device: str
    output_sha256: str
    elapsed_seconds: float
    output_statistics: tuple[tuple[str, float], ...]
    inference_mode_applied: bool


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _map_payload(frame_token_map: FrameTokenMap) -> dict[str, object]:
    def identity_payload(identity: FrameIdentity | None) -> object:
        if identity is None:
            return None
        return {
            "trajectory_id": identity.trajectory_id,
            "model_frame_idx": identity.model_frame_idx,
        }

    return {
        "schema_version": frame_token_map.schema_version,
        "trajectory_id": frame_token_map.trajectory_id,
        "sequence_length": frame_token_map.sequence_length,
        "spans": [
            {
                "identity": identity_payload(span.identity),
                "pair_index": span.pair_index,
                "accepted_pair_index": span.accepted_pair_index,
                "pair_start": span.pair_start,
                "pair_end_exclusive": span.pair_end_exclusive,
                "visual_positions": list(span.visual_positions),
                "action_positions": list(span.action_positions),
                "causal_predecessor": identity_payload(span.causal_predecessor),
                "causal_successor": identity_payload(span.causal_successor),
                "included_in_context": span.included_in_context,
            }
            for span in frame_token_map.spans
        ],
        "excluded_frame_identities": [
            identity_payload(identity)
            for identity in frame_token_map.excluded_frame_identities
        ],
    }


def _frame_token_map_sha256(frame_token_map: FrameTokenMap) -> str:
    return _canonical_sha256(_map_payload(frame_token_map))


def _compact_map_payload(frame_token_map: FrameTokenMap) -> dict[str, object]:
    """Return a compact, machine-checkable pilot view of exact map positions."""

    return {
        "trajectory_id": frame_token_map.trajectory_id,
        "sequence_length": frame_token_map.sequence_length,
        "spans": [
            {
                "model_frame_idx": span.identity.model_frame_idx,
                "pair_index": span.pair_index,
                "accepted_pair_index": span.accepted_pair_index,
                "pair_start": span.pair_start,
                "pair_end_exclusive": span.pair_end_exclusive,
                "visual_start": span.visual_positions[0],
                "visual_end_exclusive": span.visual_positions[-1] + 1,
                "visual_count": len(span.visual_positions),
                "action_start": span.action_positions[0],
                "action_end_exclusive": span.action_positions[-1] + 1,
                "action_count": len(span.action_positions),
                "causal_predecessor_model_frame_idx": (
                    span.causal_predecessor.model_frame_idx
                    if span.causal_predecessor is not None
                    else None
                ),
                "causal_successor_model_frame_idx": (
                    span.causal_successor.model_frame_idx
                    if span.causal_successor is not None
                    else None
                ),
            }
            for span in frame_token_map.spans
        ],
        "excluded_model_frame_indices": [
            identity.model_frame_idx
            for identity in frame_token_map.excluded_frame_identities
        ],
    }


def _token_sha256(token_ids: Sequence[int]) -> str:
    return _canonical_sha256(list(token_ids))


def _array_sha256(value: object) -> str:
    tobytes = getattr(value, "tobytes", None)
    if not callable(tobytes):
        raise TypeError("frame payload does not expose deterministic bytes")
    return hashlib.sha256(tobytes(order="C")).hexdigest()


def _validate_preprocessed_frame(
    frame: PreprocessedFrame,
    runtime_identity: MineWorldRuntimeIdentity,
) -> None:
    operation = AdapterOperation.TOKENIZE_TRAJECTORY
    expected_shape = (
        3,
        PINNED_PROCESSED_VIDEO_HEIGHT,
        PINNED_PROCESSED_VIDEO_WIDTH,
    )
    if (
        frame.preprocessing_profile != PREPROCESSING_PROFILE
        or frame.preprocessing_profile
        != runtime_identity.preprocessing_identity
    ):
        raise _adapter_error(
            AdapterFailureCode.INVALID_PROVENANCE,
            operation,
            "frames.preprocessing_profile",
            "does not match the loaded pinned preprocessing profile",
        )
    payload = frame.frame
    if (
        frame.shape != expected_shape
        or tuple(getattr(payload, "shape", ())) != expected_shape
        or frame.dtype != "float32"
        or str(getattr(payload, "dtype", "")) != "float32"
        or frame.color_order != "RGB"
    ):
        raise _adapter_error(
            AdapterFailureCode.INVALID_REQUEST,
            operation,
            "frames.frame",
            "must be finite float32 RGB CHW data with shape (3, 224, 384)",
        )
    try:
        numpy = importlib.import_module("numpy")
        numeric = numpy.asarray(payload)
        finite = bool(numpy.isfinite(numeric).all())
        observed_sha256 = _array_sha256(numeric)
    except Exception as exc:
        raise _adapter_error(
            AdapterFailureCode.INVALID_REQUEST,
            operation,
            "frames.frame",
            f"could not validate deterministic numeric content: {exc}",
        ) from exc
    if not finite:
        raise _adapter_error(
            AdapterFailureCode.INVALID_REQUEST,
            operation,
            "frames.frame",
            "contains nonfinite data",
        )
    if observed_sha256 != frame.content_sha256:
        raise _adapter_error(
            AdapterFailureCode.INVALID_PROVENANCE,
            operation,
            "frames.content_sha256",
            "does not match the preprocessed frame payload",
        )


def _validate_action(
    action: object,
    runtime_identity: MineWorldRuntimeIdentity,
) -> None:
    operation = AdapterOperation.TOKENIZE_TRAJECTORY
    token_ids = getattr(action, "token_ids", ())
    if (
        getattr(action, "converter_identity", None)
        != runtime_identity.action_conversion_identity
        or getattr(action, "converter_identity", None)
        != ACTION_CONVERTER_IDENTITY
        or getattr(action, "converter_source_revision", None)
        != PINNED_SOURCE_REVISION
    ):
        raise _adapter_error(
            AdapterFailureCode.INVALID_PROVENANCE,
            operation,
            "actions.converter_identity",
            "does not match the loaded pinned action converter",
        )
    if (
        getattr(action, "vocabulary_offset", None)
        != ACTION_VOCABULARY_OFFSET
        or getattr(action, "positional_roles", ())
        != ACTION_POSITIONAL_ROLES
        or not isinstance(getattr(action, "normalized_action", None), Mapping)
        or not isinstance(getattr(action, "is_noop", None), bool)
    ):
        raise _adapter_error(
            AdapterFailureCode.INVALID_PROVENANCE,
            operation,
            "actions",
            "does not carry the complete pinned conversion result",
        )
    if (
        not isinstance(token_ids, tuple)
        or len(token_ids) != PINNED_ACTION_TOKENS
        or any(
            type(token) is not int
            or token < ACTION_VOCABULARY_OFFSET
            or token >= PINNED_VOCAB_SIZE
            for token in token_ids
        )
    ):
        raise _adapter_error(
            AdapterFailureCode.INVALID_REQUEST,
            operation,
            "actions.token_ids",
            "must contain exactly 11 pinned action-vocabulary token IDs",
        )
    expected_content = {
        "normalized_action": dict(action.normalized_action),
        "token_ids": list(token_ids),
        "positional_roles": list(ACTION_POSITIONAL_ROLES),
        "vocabulary_offset": ACTION_VOCABULARY_OFFSET,
    }
    if _canonical_sha256(expected_content) != getattr(
        action, "content_sha256", None
    ):
        raise _adapter_error(
            AdapterFailureCode.INVALID_PROVENANCE,
            operation,
            "actions.content_sha256",
            "does not match the complete converted action content",
        )


def _coerce_visual_rows(
    value: object,
    expected_rows: int,
) -> tuple[tuple[int, ...], ...]:
    operation = AdapterOperation.TOKENIZE_TRAJECTORY
    candidate = value
    for method_name in ("detach", "cpu"):
        method = getattr(candidate, method_name, None)
        if callable(method):
            candidate = method()
    shape = tuple(int(part) for part in getattr(candidate, "shape", ()))
    allowed_shapes = {
        (expected_rows, 14, 24),
        (expected_rows, PINNED_VISUAL_TOKENS),
    }
    if shape not in allowed_shapes:
        raise _adapter_error(
            AdapterFailureCode.INVALID_REQUEST,
            operation,
            "vae_output",
            (
                "must have official shape "
                f"({expected_rows}, 14, 24) or "
                f"({expected_rows}, {PINNED_VISUAL_TOKENS}); observed {shape}"
            ),
        )
    reshape = getattr(candidate, "reshape", None)
    if not callable(reshape):
        raise _adapter_error(
            AdapterFailureCode.INVALID_REQUEST,
            operation,
            "vae_output",
            "does not expose a reshape operation",
        )
    flattened = reshape(expected_rows, PINNED_VISUAL_TOKENS)
    tolist = getattr(flattened, "tolist", None)
    if not callable(tolist):
        raise _adapter_error(
            AdapterFailureCode.INVALID_REQUEST,
            operation,
            "vae_output",
            "does not expose deterministic integer values",
        )
    raw_rows = tolist()
    if (
        not isinstance(raw_rows, list)
        or len(raw_rows) != expected_rows
        or any(not isinstance(row, list) for row in raw_rows)
    ):
        raise _adapter_error(
            AdapterFailureCode.INVALID_REQUEST,
            operation,
            "vae_output",
            "did not decode to one visual-token row per accepted frame",
        )
    rows: list[tuple[int, ...]] = []
    for row_index, row in enumerate(raw_rows):
        if (
            len(row) != PINNED_VISUAL_TOKENS
            or any(
                type(token) is not int
                or token < 0
                or token >= VISUAL_VOCABULARY_SIZE
                for token in row
            )
        ):
            raise _adapter_error(
                AdapterFailureCode.INVALID_REQUEST,
                operation,
                f"vae_output[{row_index}]",
                "must contain exactly 336 integral visual-vocabulary IDs",
            )
        rows.append(tuple(row))
    return tuple(rows)


def _official_visual_tokenizer(
    runtime: _LoadedRuntime,
    frames: tuple[PreprocessedFrame, ...],
    runtime_identity: MineWorldRuntimeIdentity,
) -> tuple[tuple[int, ...], ...]:
    """Invoke the pinned VAE boundary once; the adapter verifies repeatability."""

    torch = importlib.import_module("torch")
    numpy = importlib.import_module("numpy")
    if runtime.vae is None or not callable(
        getattr(runtime.vae, "tokenize_images", None)
    ):
        raise RuntimeError("loaded runtime does not expose VAE.tokenize_images")
    if getattr(runtime.vae, "training", False):
        raise RuntimeError("loaded VAE must be in evaluation mode")
    stacked = numpy.stack(
        [numpy.asarray(frame.frame, dtype=numpy.float32) for frame in frames],
        axis=0,
    )
    tensor = torch.from_numpy(stacked).to(runtime_identity.device)
    dtype = (
        torch.float16
        if runtime_identity.precision == "float16"
        else torch.bfloat16
    )

    with torch.no_grad(), torch.autocast("cuda", dtype=dtype):
        output = runtime.vae.tokenize_images(tensor)
    return _coerce_visual_rows(output, len(frames))


def _output_metadata(output: object) -> tuple[
    tuple[int, ...],
    str,
    str,
    str,
    tuple[tuple[str, float], ...],
]:
    tensor = output[0] if isinstance(output, tuple) and output else output
    shape = tuple(int(part) for part in getattr(tensor, "shape", ()))
    if not shape or any(part <= 0 for part in shape):
        raise RuntimeError("teacher-forced output has no valid tensor shape")
    detached = tensor
    for method_name in ("detach", "cpu", "contiguous"):
        method = getattr(detached, method_name, None)
        if callable(method):
            detached = method()
    numpy_method = getattr(detached, "numpy", None)
    if not callable(numpy_method):
        raise TypeError("teacher-forced output cannot be hashed")
    array = numpy_method()
    try:
        numpy = importlib.import_module("numpy")
        numeric = numpy.asarray(array)
        if not numpy.isfinite(numeric).all():
            raise RuntimeError("teacher-forced output contains nonfinite data")
        statistics = (
            ("minimum", float(numeric.min())),
            ("maximum", float(numeric.max())),
            ("mean", float(numeric.mean())),
            ("standard_deviation", float(numeric.std())),
        )
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError(
            f"teacher-forced output statistics failed: {exc}"
        ) from exc
    digest = hashlib.sha256(array.tobytes(order="C")).hexdigest()
    return (
        shape,
        str(getattr(tensor, "dtype", "")).removeprefix("torch."),
        str(getattr(tensor, "device", "")),
        digest,
        statistics,
    )


def _official_teacher_executor(
    runtime: _LoadedRuntime,
    trajectory: TokenizedTrajectory,
    request: TeacherForcedRequest,
) -> _TeacherExecution:
    """Run the exact Phase 2 transformer call, without generation or hooks."""

    torch = importlib.import_module("torch")
    random.seed(request.seed)
    torch.manual_seed(request.seed)
    torch.cuda.manual_seed_all(request.seed)
    input_ids = torch.tensor(
        [trajectory.token_ids],
        dtype=torch.long,
        device=request.runtime_identity.device,
    )
    position_ids = torch.tensor(
        trajectory.position_ids,
        dtype=torch.long,
        device=request.runtime_identity.device,
    )
    # The pinned LlamaModel constructs its causal attention mask from the
    # explicit position IDs. The all-one project mask records that this
    # unpadded sequence contains no masked-out input tokens.
    transformer = getattr(runtime.model, "transformer", None)
    if transformer is None or not callable(transformer):
        raise RuntimeError("loaded model does not expose transformer forward")
    refresh = getattr(transformer, "refresh_kvcache", None)
    if not callable(refresh):
        raise TypeError("loaded transformer does not expose refresh_kvcache")
    refresh()
    dtype = (
        torch.float16
        if request.precision == "float16"
        else torch.bfloat16
    )
    torch.cuda.synchronize()
    started = time.perf_counter()
    with torch.inference_mode(), torch.autocast("cuda", dtype=dtype):
        output = transformer(
            input_ids=input_ids,
            position_ids=position_ids,
        )
    torch.cuda.synchronize()
    elapsed = time.perf_counter() - started
    shape, output_dtype, device, digest, statistics = _output_metadata(output)
    return _TeacherExecution(
        output=output,
        output_shape=shape,
        dtype=output_dtype,
        device=device,
        output_sha256=digest,
        elapsed_seconds=elapsed,
        output_statistics=statistics,
        inference_mode_applied=True,
    )


class _Wave3MineWorldAdapter(_Wave2MineWorldAdapter):
    """Private Wave 2 extension implementing Steps 3.6 and 3.7 together."""

    def __init__(
        self,
        *args: Any,
        visual_tokenizer: Callable[
            [
                _LoadedRuntime,
                tuple[PreprocessedFrame, ...],
                MineWorldRuntimeIdentity,
            ],
            tuple[tuple[int, ...], ...],
        ] = _official_visual_tokenizer,
        teacher_executor: Callable[
            [_LoadedRuntime, TokenizedTrajectory, TeacherForcedRequest],
            _TeacherExecution,
        ] = _official_teacher_executor,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._visual_tokenizer = visual_tokenizer
        self._teacher_executor = teacher_executor

    def tokenize_trajectory(
        self, request: TrajectoryTokenizationRequest
    ) -> TokenizedTrajectory:
        operation = AdapterOperation.TOKENIZE_TRAJECTORY
        runtime, identity = self._require_runtime(operation)
        if request.runtime_identity != identity:
            raise _adapter_error(
                AdapterFailureCode.INVALID_IDENTITY,
                operation,
                "runtime_identity",
                "does not exactly match the loaded runtime",
            )
        if runtime.vae is None or getattr(runtime.vae, "training", True):
            raise _adapter_error(
                AdapterFailureCode.OPERATION_UNAVAILABLE,
                operation,
                "vae",
                "the loaded VAE must be present and in evaluation mode",
            )
        accepted = request.trajectory.frame_identities
        if tuple(frame.identity for frame in request.frames) != accepted:
            raise _adapter_error(
                AdapterFailureCode.INVALID_IDENTITY,
                operation,
                "frames",
                "do not exactly preserve the validated trajectory",
            )
        if tuple(action.identity for action in request.actions) != accepted:
            raise _adapter_error(
                AdapterFailureCode.INVALID_IDENTITY,
                operation,
                "actions",
                "do not exactly preserve the validated trajectory",
            )
        for frame, action in zip(request.frames, request.actions, strict=True):
            accepted_frame = self._require_accepted_frame(
                frame.identity, operation
            )
            accepted_action = self._require_accepted_frame(
                action.identity, operation
            )
            if frame.source_frame_idx != accepted_frame.render_frame_idx:
                raise _adapter_error(
                    AdapterFailureCode.INVALID_IDENTITY,
                    operation,
                    "frames.source_frame_idx",
                    "does not match the accepted render-frame index",
                )
            if action.action_idx != accepted_action.action_idx:
                raise _adapter_error(
                    AdapterFailureCode.INVALID_IDENTITY,
                    operation,
                    "actions.action_idx",
                    "does not match the accepted action index",
                )
            _validate_preprocessed_frame(frame, identity)
            _validate_action(action, identity)
        try:
            first_output = self._visual_tokenizer(
                runtime, request.frames, identity
            )
            second_output = self._visual_tokenizer(
                runtime, request.frames, identity
            )
            visual_rows = _coerce_visual_rows(
                _Rows(first_output), len(request.frames)
            )
            repeated_rows = _coerce_visual_rows(
                _Rows(second_output), len(request.frames)
            )
            if visual_rows != repeated_rows:
                raise RuntimeError(
                    "VAE tokenization was nondeterministic for identical input"
                )
        except MineWorldAdapterError:
            raise
        except Exception as exc:
            raise _adapter_error(
                AdapterFailureCode.RUNTIME_EXECUTION_FAILED,
                operation,
                "vae_tokenization",
                str(exc),
                ("exception_type", type(exc).__name__),
            ) from exc
        if len(visual_rows) != len(accepted):
            raise _adapter_error(
                AdapterFailureCode.INVALID_IDENTITY,
                operation,
                "vae_output",
                "row count does not match the validated trajectory",
            )

        start = max(0, len(accepted) - identity.max_context_pairs)
        included = accepted[start:]
        excluded = accepted[:start]
        token_ids: list[int] = []
        spans: list[FrameTokenSpan] = []
        for pair_index, accepted_index in enumerate(
            range(start, len(accepted))
        ):
            frame_identity = accepted[accepted_index]
            visual = visual_rows[accepted_index]
            action = request.actions[accepted_index].token_ids
            pair_start = len(token_ids)
            token_ids.extend(visual)
            action_start = len(token_ids)
            token_ids.extend(action)
            pair_end = len(token_ids)
            if (
                len(visual) != PINNED_VISUAL_TOKENS
                or len(action) != PINNED_ACTION_TOKENS
                or pair_end - pair_start != PINNED_TOKENS_PER_PAIR
            ):
                raise _adapter_error(
                    AdapterFailureCode.INVALID_REQUEST,
                    operation,
                    "sequence",
                    "could not assemble one complete 336+11 token pair",
                )
            spans.append(
                FrameTokenSpan(
                    identity=frame_identity,
                    pair_index=pair_index,
                    visual_positions=tuple(range(pair_start, action_start)),
                    action_positions=tuple(range(action_start, pair_end)),
                    accepted_pair_index=accepted_index,
                    pair_start=pair_start,
                    pair_end_exclusive=pair_end,
                    causal_predecessor=(
                        accepted[accepted_index - 1]
                        if accepted_index > 0
                        else None
                    ),
                    causal_successor=(
                        accepted[accepted_index + 1]
                        if accepted_index + 1 < len(accepted)
                        else None
                    ),
                    included_in_context=True,
                )
            )
        if (
            len(spans) > MAX_MODEL_FRAMES
            or len(token_ids) != len(spans) * TOKENS_PER_FRAME_ACTION_PAIR
            or len(token_ids) > identity.max_position_embeddings
        ):
            raise _adapter_error(
                AdapterFailureCode.INVALID_REQUEST,
                operation,
                "sequence",
                "complete-pair context exceeds the pinned model position budget",
            )
        frame_token_map = FrameTokenMap(
            schema_version=SCHEMA_VERSION,
            trajectory_id=request.trajectory.trajectory_id,
            sequence_length=len(token_ids),
            spans=tuple(spans),
            excluded_frame_identities=excluded,
        )
        token_tuple = tuple(token_ids)
        return TokenizedTrajectory(
            runtime_identity=identity,
            trajectory_id=request.trajectory.trajectory_id,
            token_ids=token_tuple,
            frame_token_map=frame_token_map,
            token_sha256=_token_sha256(token_tuple),
            attention_mask=(1,) * len(token_tuple),
            position_ids=tuple(range(len(token_tuple))),
            included_frame_identities=included,
            excluded_frame_identities=excluded,
            tokenization_profile=TOKENIZATION_PROFILE,
            preprocessing_profile=identity.preprocessing_identity,
            action_conversion_profile=identity.action_conversion_identity,
            frame_token_map_sha256=_frame_token_map_sha256(frame_token_map),
            accepted_frame_count=len(accepted),
            context_pair_count=len(included),
        )

    def teacher_forced(
        self, request: TeacherForcedRequest
    ) -> TeacherForcedResult:
        operation = AdapterOperation.TEACHER_FORCED
        runtime, identity = self._require_runtime(operation)
        trajectory = request.trajectory
        if request.runtime_identity != identity:
            raise _adapter_error(
                AdapterFailureCode.INVALID_IDENTITY,
                operation,
                "runtime_identity",
                "does not exactly match the loaded runtime",
            )
        self._validate_teacher_input(runtime, trajectory, request, identity)
        decoder_modules = self._decoder_modules(runtime, identity)
        context = nullcontext()
        if request.hook_context_factory is not None:
            try:
                context = request.hook_context_factory(decoder_modules)
            except Exception as exc:
                raise _adapter_error(
                    AdapterFailureCode.INVALID_REQUEST,
                    operation,
                    "hook_context_factory",
                    str(exc),
                    ("exception_type", type(exc).__name__),
                ) from exc
            if not (
                callable(getattr(context, "__enter__", None))
                and callable(getattr(context, "__exit__", None))
            ):
                raise _adapter_error(
                    AdapterFailureCode.INVALID_REQUEST,
                    operation,
                    "hook_context_factory",
                    "must return a context manager",
                )
        try:
            with context:
                execution = self._teacher_executor(
                    runtime, trajectory, request
                )
        except MineWorldAdapterError:
            raise
        except Exception as exc:
            raise _adapter_error(
                AdapterFailureCode.RUNTIME_EXECUTION_FAILED,
                operation,
                "model_forward",
                str(exc),
                ("exception_type", type(exc).__name__),
            ) from exc
        if not isinstance(execution, _TeacherExecution):
            raise _adapter_error(
                AdapterFailureCode.RUNTIME_EXECUTION_FAILED,
                operation,
                "model_forward",
                "executor returned an unsupported result structure",
            )
        if not execution.inference_mode_applied:
            raise _adapter_error(
                AdapterFailureCode.RUNTIME_EXECUTION_FAILED,
                operation,
                "model_forward",
                "executor did not apply no-grad/inference mode",
            )
        if (
            not execution.output_shape
            or execution.output_shape[0] != 1
            or execution.output_shape[1] != len(trajectory.token_ids)
            or execution.dtype != request.precision
            or execution.device != identity.device
            or execution.elapsed_seconds < 0
            or not math.isfinite(execution.elapsed_seconds)
        ):
            raise _adapter_error(
                AdapterFailureCode.RUNTIME_EXECUTION_FAILED,
                operation,
                "model_forward",
                "output metadata contradicts the teacher-forced request",
            )
        return TeacherForcedResult(
            runtime_identity=identity,
            trajectory_id=trajectory.trajectory_id,
            frame_token_map=trajectory.frame_token_map,
            output_shape=execution.output_shape,
            dtype=execution.dtype,
            device=execution.device,
            output_sha256=execution.output_sha256,
            elapsed_seconds=execution.elapsed_seconds,
            output=execution.output,
            token_sha256=trajectory.token_sha256,
            frame_token_map_sha256=trajectory.frame_token_map_sha256,
            seed=request.seed,
            batch_size=request.batch_size,
            input_sequence_length=len(trajectory.token_ids),
            included_frame_identities=trajectory.included_frame_identities,
            excluded_frame_identities=trajectory.excluded_frame_identities,
            output_statistics=execution.output_statistics,
            warnings=(),
        )

    def _require_runtime(
        self, operation: AdapterOperation
    ) -> tuple[_LoadedRuntime, MineWorldRuntimeIdentity]:
        if self._runtime is None or self._runtime_identity_record is None:
            raise _adapter_error(
                AdapterFailureCode.OPERATION_UNAVAILABLE,
                operation,
                "runtime",
                "load_runtime must complete before this operation",
            )
        return self._runtime, self._runtime_identity_record

    @staticmethod
    def _decoder_modules(
        runtime: _LoadedRuntime,
        identity: MineWorldRuntimeIdentity,
    ) -> tuple[tuple[str, object], ...]:
        named_modules_method = getattr(runtime.model, "named_modules", None)
        if not callable(named_modules_method):
            raise _adapter_error(
                AdapterFailureCode.INVALID_REQUEST,
                AdapterOperation.TEACHER_FORCED,
                "model.named_modules",
                "loaded model does not expose decoder modules",
            )
        named_modules = dict(named_modules_method())
        expected_names = tuple(
            f"{identity.decoder_layer_path}.{index}"
            for index in range(identity.layer_count)
        )
        if (
            len(expected_names) != len(set(expected_names))
            or any(name not in named_modules for name in expected_names)
            or len({id(named_modules[name]) for name in expected_names})
            != len(expected_names)
        ):
            raise _adapter_error(
                AdapterFailureCode.INVALID_PROVENANCE,
                AdapterOperation.TEACHER_FORCED,
                "decoder_modules",
                "loaded decoder module set contradicts runtime identity",
            )
        return tuple((name, named_modules[name]) for name in expected_names)

    @staticmethod
    def _validate_teacher_input(
        runtime: _LoadedRuntime,
        trajectory: TokenizedTrajectory,
        request: TeacherForcedRequest,
        identity: MineWorldRuntimeIdentity,
    ) -> None:
        operation = AdapterOperation.TEACHER_FORCED
        if request.batch_size != 1:
            raise _adapter_error(
                AdapterFailureCode.INVALID_REQUEST,
                operation,
                "batch_size",
                "the pinned teacher-forced runtime supports batch size 1 only",
            )
        if (
            request.precision != identity.precision
            or identity.precision != PINNED_PRECISION
            or identity.device != PINNED_DEVICE
        ):
            raise _adapter_error(
                AdapterFailureCode.INVALID_PROVENANCE,
                operation,
                "precision/device",
                "must exactly match the loaded pinned float16 CUDA runtime",
            )
        if (
            trajectory.runtime_identity != identity
            or trajectory.tokenization_profile != TOKENIZATION_PROFILE
            or trajectory.preprocessing_profile
            != identity.preprocessing_identity
            or trajectory.action_conversion_profile
            != identity.action_conversion_identity
        ):
            raise _adapter_error(
                AdapterFailureCode.INVALID_PROVENANCE,
                operation,
                "trajectory",
                "runtime and adapter profiles must exactly match",
            )
        if (
            not trajectory.attention_mask
            or trajectory.attention_mask
            != (1,) * len(trajectory.token_ids)
            or trajectory.position_ids
            != tuple(range(len(trajectory.token_ids)))
        ):
            raise _adapter_error(
                AdapterFailureCode.INVALID_REQUEST,
                operation,
                "attention_mask/position_ids",
                "must describe one complete unpadded context-relative sequence",
            )
        if (
            len(trajectory.token_ids)
            != trajectory.frame_token_map.sequence_length
            or len(trajectory.token_ids)
            > identity.max_position_embeddings
            or len(trajectory.frame_token_map.spans)
            > identity.max_context_pairs
            or _token_sha256(trajectory.token_ids)
            != trajectory.token_sha256
            or _frame_token_map_sha256(trajectory.frame_token_map)
            != trajectory.frame_token_map_sha256
        ):
            raise _adapter_error(
                AdapterFailureCode.INVALID_PROVENANCE,
                operation,
                "trajectory",
                "sequence or FrameTokenMap identity does not validate",
            )
        if (
            tuple(span.identity for span in trajectory.frame_token_map.spans)
            != trajectory.included_frame_identities
            or trajectory.frame_token_map.excluded_frame_identities
            != trajectory.excluded_frame_identities
            or trajectory.context_pair_count
            != len(trajectory.frame_token_map.spans)
            or trajectory.accepted_frame_count
            != (
                len(trajectory.included_frame_identities)
                + len(trajectory.excluded_frame_identities)
            )
        ):
            raise _adapter_error(
                AdapterFailureCode.INVALID_IDENTITY,
                operation,
                "trajectory",
                "included/excluded frame identity metadata is inconsistent",
            )
        accepted_identities = (
            trajectory.excluded_frame_identities
            + trajectory.included_frame_identities
        )
        excluded_count = len(trajectory.excluded_frame_identities)
        for pair_index, span in enumerate(trajectory.frame_token_map.spans):
            accepted_index = excluded_count + pair_index
            expected_predecessor = (
                accepted_identities[accepted_index - 1]
                if accepted_index > 0
                else None
            )
            expected_successor = (
                accepted_identities[accepted_index + 1]
                if accepted_index + 1 < len(accepted_identities)
                else None
            )
            if (
                span.accepted_pair_index != accepted_index
                or span.causal_predecessor != expected_predecessor
                or span.causal_successor != expected_successor
                or span.pair_start != pair_index * PINNED_TOKENS_PER_PAIR
                or span.pair_end_exclusive
                != (pair_index + 1) * PINNED_TOKENS_PER_PAIR
            ):
                raise _adapter_error(
                    AdapterFailureCode.INVALID_IDENTITY,
                    operation,
                    "frame_token_map.spans",
                    "pair bounds or accepted causal neighbors are inconsistent",
                )
        for span in trajectory.frame_token_map.spans:
            if any(
                trajectory.token_ids[position] >= VISUAL_VOCABULARY_SIZE
                for position in span.visual_positions
            ) or any(
                trajectory.token_ids[position] < ACTION_VOCABULARY_OFFSET
                or trajectory.token_ids[position] >= 8262
                for position in span.action_positions
            ):
                raise _adapter_error(
                    AdapterFailureCode.INVALID_REQUEST,
                    operation,
                    "trajectory.token_ids",
                    "visual/action token regions violate the pinned vocabulary",
                )
        for label, object_ in (("model", runtime.model), ("vae", runtime.vae)):
            if object_ is None or getattr(object_, "training", True):
                raise _adapter_error(
                    AdapterFailureCode.INVALID_REQUEST,
                    operation,
                    label,
                    "must be present and in evaluation mode",
                )


class _Rows:
    """Tiny array-like adapter for injected CPU visual-token fixtures."""

    def __init__(self, rows: Sequence[Sequence[int]]) -> None:
        self._rows = [list(row) for row in rows]
        self.shape = (
            len(self._rows),
            len(self._rows[0]) if self._rows else 0,
        )

    def reshape(self, rows: int, columns: int) -> _Rows:
        if self.shape != (rows, columns):
            raise ValueError(
                f"cannot reshape injected rows {self.shape} to {(rows, columns)}"
            )
        return self

    def tolist(self) -> list[list[int]]:
        return [list(row) for row in self._rows]
