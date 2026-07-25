"""Private Person A Phase 3 Wave 4 rollout and identity implementation.

The public contract remains in :mod:`mineocclude.models.mineworld_adapter`.
This module implements Steps 3.8 and 3.9 without owning activation hooks,
pooling, storage, interventions, analysis, or experiment registration.
"""

from __future__ import annotations

import dataclasses
import hashlib
import importlib
import math
import random
import re
import subprocess
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mineocclude.contracts.identity import SCHEMA_VERSION
from mineocclude.models._mineworld_adapter_wave2 import (
    PINNED_ACTION_TOKENS,
    PINNED_DEVICE,
    PINNED_PRECISION,
    PINNED_PROCESSED_VIDEO_HEIGHT,
    PINNED_PROCESSED_VIDEO_WIDTH,
    PINNED_VISUAL_TOKENS,
    _adapter_error,
    _LoadedRuntime,
)
from mineocclude.models._mineworld_adapter_wave3 import (
    TOKENIZATION_PROFILE,
    _frame_token_map_sha256,
    _token_sha256,
    _validate_action,
    _Wave3MineWorldAdapter,
)
from mineocclude.models.mineworld_adapter import (
    MINEWORLD_ADAPTER_API_VERSION,
    AdapterFailureCode,
    AdapterOperation,
    AcceptedTrajectoryInput,
    ActionConversionRequest,
    ConvertedAction,
    FramePreprocessRequest,
    FreeRolloutRequest,
    FreeRolloutResult,
    MineWorldAdapterError,
    MineWorldRuntimeIdentity,
    PreprocessedFrame,
    RuntimeLoadRequest,
    TeacherForcedRequest,
    TeacherForcedResult,
    TokenizedTrajectory,
    TrajectoryTokenizationRequest,
    ValidatedTrajectory,
)
from mineocclude.models.phase2_aws import _external_source_imports
from mineocclude.models.phase2_evidence import (
    canonical_json_bytes,
    sha256_file,
)


ROLLOUT_PROFILE = (
    "mineworld-700m-16f-naive-free-rollout-v1.0:"
    "9f49efbcc68a5f0cf60e78f0abc566eac409282f:"
    "lvm.py#LlamaForCausalLM.naive_generate"
)
CODE_IDENTITY_VERSION = "person-a-mineworld-adapter-code-v1.0"
ROLLOUT_REPORT_VERSION = "person-a-phase3-rollout-v1.0"
PINNED_OUTPUT_WIDTH = 384
PINNED_OUTPUT_HEIGHT = 224
_SAFE_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_REPO_ROOT = Path(__file__).resolve().parents[3]
_CODE_FILES = (
    "src/mineocclude/models/_mineworld_adapter_wave2.py",
    "src/mineocclude/models/_mineworld_adapter_wave3.py",
    "src/mineocclude/models/_mineworld_adapter_wave4.py",
    "src/mineocclude/models/mineworld_adapter.py",
)


@dataclass(frozen=True)
class _AdapterCodeIdentity:
    sha256: str
    inventory: tuple[tuple[str, str, int], ...]


@dataclass(frozen=True)
class _VideoProbe:
    decoded_frames: int
    width: int
    height: int
    frame_rate: float
    duration_seconds: float


@dataclass(frozen=True)
class _RolloutExecution:
    generated_token_ids: tuple[int, ...]
    generated_token_sha256: str
    generated_frame_count: int
    elapsed_seconds: float
    peak_cuda_allocated_bytes: int
    peak_cuda_reserved_bytes: int
    inference_mode_applied: bool


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _adapter_code_identity(
    repository_root: Path = _REPO_ROOT,
    *,
    relative_paths: Sequence[str] = _CODE_FILES,
) -> _AdapterCodeIdentity:
    """Hash a deterministic sorted inventory of adapter implementation files."""

    rows: list[tuple[str, str, int]] = []
    normalized = tuple(sorted(relative_paths))
    if not normalized or len(normalized) != len(set(normalized)):
        raise ValueError("adapter code paths must be nonempty and unique")
    for relative in normalized:
        path = (repository_root / relative).resolve()
        if not path.is_file() or not path.is_relative_to(repository_root.resolve()):
            raise ValueError(f"adapter code file is missing or unsafe: {relative}")
        rows.append((Path(relative).as_posix(), sha256_file(path), path.stat().st_size))
    inventory = tuple(rows)
    digest = _canonical_sha256(
        {
            "identity_version": CODE_IDENTITY_VERSION,
            "files": [
                {"path": path, "sha256": digest, "size_bytes": size}
                for path, digest, size in inventory
            ],
        }
    )
    return _AdapterCodeIdentity(digest, inventory)


def _rollout_generation_config_payload(
    request: FreeRolloutRequest,
) -> dict[str, object]:
    return {
        "profile": ROLLOUT_PROFILE,
        "generated_frame_count": request.generated_frame_count,
        "temperature": float(request.temperature),
        "top_k": request.top_k,
        "top_p": request.top_p,
        "output_frame_rate": float(request.output_frame_rate),
        "generation_actions": [
            {
                "trajectory_id": action.identity.trajectory_id,
                "model_frame_idx": action.identity.model_frame_idx,
                "action_idx": action.action_idx,
                "content_sha256": action.content_sha256,
                "token_ids": list(action.token_ids),
            }
            for action in request.generation_actions
        ],
    }


def _rollout_generation_config_sha256(
    request: FreeRolloutRequest,
) -> str:
    return _canonical_sha256(_rollout_generation_config_payload(request))


def _request_payload(request: FreeRolloutRequest) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "adapter_api_version": MINEWORLD_ADAPTER_API_VERSION,
        "operation": AdapterOperation.FREE_ROLLOUT.value,
        "runtime_id": request.runtime_identity.runtime_id,
        "runtime_code_revision": request.runtime_identity.mineocclude_revision,
        "adapter_code_sha256": request.runtime_identity.adapter_code_sha256,
        "trajectory_id": request.context.trajectory_id,
        "accepted_manifest_sha256": request.accepted_manifest_sha256,
        "token_sha256": request.context.token_sha256,
        "frame_token_map_sha256": request.context.frame_token_map_sha256,
        "run_id": request.run_id,
        "seed": request.seed,
        "precision": request.precision,
        "device": request.device,
        "generation_config_sha256": request.generation_config_sha256,
        "output_directory": str(request.output_directory.resolve()),
        "protected_input_paths": sorted(
            str(path.resolve()) for path in request.protected_input_paths
        ),
        "allow_overwrite": request.allow_overwrite,
    }


def _teacher_request_sha256(request: TeacherForcedRequest) -> str:
    return _canonical_sha256(
        {
            "schema_version": SCHEMA_VERSION,
            "adapter_api_version": MINEWORLD_ADAPTER_API_VERSION,
            "operation": AdapterOperation.TEACHER_FORCED.value,
            "runtime_id": request.runtime_identity.runtime_id,
            "adapter_code_sha256": (
                request.runtime_identity.adapter_code_sha256
            ),
            "trajectory_id": request.trajectory.trajectory_id,
            "accepted_manifest_sha256": (
                request.trajectory.accepted_manifest_sha256
            ),
            "token_sha256": request.trajectory.token_sha256,
            "frame_token_map_sha256": (
                request.trajectory.frame_token_map_sha256
            ),
            "seed": request.seed,
            "precision": request.precision,
            "batch_size": request.batch_size,
            "external_hook_context_requested": (
                request.hook_context_factory is not None
            ),
        }
    )


def _runtime_payload(identity: MineWorldRuntimeIdentity) -> dict[str, object]:
    return dataclasses.asdict(identity)


def _default_video_probe(path: Path) -> _VideoProbe:
    cv2 = importlib.import_module("cv2")
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        capture.release()
        raise RuntimeError("generated MP4 could not be opened")
    decoded = 0
    try:
        width = int(round(capture.get(cv2.CAP_PROP_FRAME_WIDTH)))
        height = int(round(capture.get(cv2.CAP_PROP_FRAME_HEIGHT)))
        frame_rate = float(capture.get(cv2.CAP_PROP_FPS))
        while True:
            ok, _frame = capture.read()
            if not ok:
                break
            decoded += 1
    finally:
        capture.release()
    duration = decoded / frame_rate if frame_rate > 0 else 0.0
    return _VideoProbe(decoded, width, height, frame_rate, duration)


def _is_git_ignored(path: Path, repository_root: Path) -> bool:
    try:
        relative = path.resolve().relative_to(repository_root.resolve())
    except ValueError:
        return False
    result = subprocess.run(
        ["git", "-C", str(repository_root), "check-ignore", "-q", str(relative)],
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


def _official_rollout_executor(
    runtime: _LoadedRuntime,
    context: TokenizedTrajectory,
    request: FreeRolloutRequest,
    source_root: Path,
    output_video: Path,
) -> _RolloutExecution:
    """Invoke the pinned official naive generation and decode boundaries."""

    torch = importlib.import_module("torch")
    numpy = importlib.import_module("numpy")
    transformer = getattr(runtime.model, "transformer", None)
    tokenizer = getattr(runtime.model, "tokenizer", None)
    if transformer is None or not callable(
        getattr(transformer, "naive_generate", None)
    ):
        raise RuntimeError("loaded model does not expose naive_generate")
    if tokenizer is None or not callable(getattr(tokenizer, "token2image", None)):
        raise RuntimeError("loaded model does not expose VAE token2image")
    refresh = getattr(transformer, "refresh_kvcache", None)
    if not callable(refresh):
        raise RuntimeError("loaded transformer does not expose refresh_kvcache")
    random.seed(request.seed)
    numpy.random.seed(request.seed)
    torch.manual_seed(request.seed)
    torch.cuda.manual_seed_all(request.seed)
    visual_ids = tuple(
        context.token_ids[position]
        for span in context.frame_token_map.spans
        for position in span.visual_positions
    )
    action_ids = tuple(action.token_ids for action in request.generation_actions)
    image_input = torch.tensor(
        [visual_ids],
        dtype=torch.long,
        device=request.device,
    )
    action_all = torch.tensor(
        action_ids,
        dtype=torch.long,
        device=request.device,
    ).unsqueeze(1)
    refresh()
    torch.cuda.synchronize()
    torch.cuda.reset_peak_memory_stats(0)
    started = time.perf_counter()
    dtype = torch.float16 if request.precision == "float16" else torch.bfloat16
    with torch.inference_mode(), torch.autocast("cuda", dtype=dtype):
        output = transformer.naive_generate(
            input_ids=image_input,
            max_new_tokens=(
                PINNED_VISUAL_TOKENS * request.generated_frame_count
            ),
            temperature=float(request.temperature),
            action_all=action_all,
            top_k=request.top_k,
            top_p=request.top_p,
        )
    torch.cuda.synchronize()
    elapsed = time.perf_counter() - started
    values = output.detach().cpu().reshape(-1).tolist()
    if any(type(value) is not int for value in values):
        raise RuntimeError("official rollout returned nonintegral token IDs")
    generated = tuple(int(value) for value in values)
    with _external_source_imports(source_root):
        upstream_inference = importlib.import_module("inference")
        upstream_inference.token2video(
            generated,
            tokenizer,
            str(output_video),
            float(request.output_frame_rate),
            request.device,
        )
    return _RolloutExecution(
        generated_token_ids=generated,
        generated_token_sha256=_canonical_sha256(list(generated)),
        generated_frame_count=(
            len(generated) // PINNED_VISUAL_TOKENS
            if len(generated) % PINNED_VISUAL_TOKENS == 0
            else 0
        ),
        elapsed_seconds=elapsed,
        peak_cuda_allocated_bytes=int(torch.cuda.max_memory_allocated(0)),
        peak_cuda_reserved_bytes=int(torch.cuda.max_memory_reserved(0)),
        inference_mode_applied=True,
    )


class _Wave4MineWorldAdapter(_Wave3MineWorldAdapter):
    """Private final local adapter implementation for Steps 3.8 and 3.9."""

    def __init__(
        self,
        *args: Any,
        rollout_executor: Callable[
            [
                _LoadedRuntime,
                TokenizedTrajectory,
                FreeRolloutRequest,
                Path,
                Path,
            ],
            _RolloutExecution,
        ] = _official_rollout_executor,
        video_probe: Callable[[Path], _VideoProbe] = _default_video_probe,
        code_identity_provider: Callable[[], _AdapterCodeIdentity] = (
            _adapter_code_identity
        ),
        repository_root: Path = _REPO_ROOT,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._rollout_executor = rollout_executor
        self._video_probe = video_probe
        self._code_identity_provider = code_identity_provider
        self._repository_root = repository_root.resolve()
        self._code_identity: _AdapterCodeIdentity | None = None
        self._runtime_load_request: RuntimeLoadRequest | None = None

    def load_runtime(
        self, request: RuntimeLoadRequest
    ) -> MineWorldRuntimeIdentity:
        operation = AdapterOperation.LOAD_RUNTIME
        try:
            code_identity = self._code_identity_provider()
        except Exception as exc:
            raise _adapter_error(
                AdapterFailureCode.INVALID_PROVENANCE,
                operation,
                "adapter_code_identity",
                str(exc),
                ("exception_type", type(exc).__name__),
            ) from exc
        if (
            request.expected_adapter_code_sha256 is not None
            and request.expected_adapter_code_sha256 != code_identity.sha256
        ):
            raise _mismatch(
                operation,
                "expected_adapter_code_sha256",
                request.expected_adapter_code_sha256,
                code_identity.sha256,
            )
        identity = super().load_runtime(request)
        identity = dataclasses.replace(
            identity,
            adapter_code_sha256=code_identity.sha256,
            adapter_code_inventory=code_identity.inventory,
        )
        self._runtime_identity_record = identity
        self._code_identity = code_identity
        self._runtime_load_request = request
        return identity

    def validate_trajectory(
        self,
        request: AcceptedTrajectoryInput,
    ) -> ValidatedTrajectory:
        code_identity = self._observed_code_identity(
            AdapterOperation.VALIDATE_TRAJECTORY
        )
        result = super().validate_trajectory(request)
        return dataclasses.replace(
            result,
            adapter_code_sha256=code_identity.sha256,
            mineocclude_revision=self._mineocclude_revision_or_none(),
        )

    def preprocess_frame(
        self,
        request: FramePreprocessRequest,
    ) -> PreprocessedFrame:
        code_identity = self._observed_code_identity(
            AdapterOperation.PREPROCESS_FRAME
        )
        result = super().preprocess_frame(request)
        return dataclasses.replace(
            result,
            adapter_code_sha256=code_identity.sha256,
            mineocclude_revision=self._mineocclude_revision_or_none(),
        )

    def convert_action(
        self,
        request: ActionConversionRequest,
    ) -> ConvertedAction:
        code_identity = self._observed_code_identity(
            AdapterOperation.CONVERT_ACTION
        )
        result = super().convert_action(request)
        return dataclasses.replace(
            result,
            adapter_code_sha256=code_identity.sha256,
            mineocclude_revision=self._mineocclude_revision_or_none(),
        )

    def tokenize_trajectory(
        self,
        request: TrajectoryTokenizationRequest,
    ) -> TokenizedTrajectory:
        identity = self._require_complete_runtime(
            AdapterOperation.TOKENIZE_TRAJECTORY
        )
        if any(
            record.adapter_code_sha256 != identity.adapter_code_sha256
            or record.mineocclude_revision != identity.mineocclude_revision
            for record in (*request.frames, *request.actions)
        ) or (
            request.trajectory.adapter_code_sha256
            != identity.adapter_code_sha256
            or request.trajectory.mineocclude_revision
            not in (None, identity.mineocclude_revision)
        ):
            raise _adapter_error(
                AdapterFailureCode.INVALID_PROVENANCE,
                AdapterOperation.TOKENIZE_TRAJECTORY,
                "adapter_code_identity",
                "trajectory, frames, and actions must match the loaded code",
                ("trajectory_id", request.trajectory.trajectory_id),
            )
        return super().tokenize_trajectory(request)

    def teacher_forced(
        self, request: TeacherForcedRequest
    ) -> TeacherForcedResult:
        identity = self._require_complete_runtime(
            AdapterOperation.TEACHER_FORCED
        )
        _validate_expected_code(
            request.expected_adapter_code_sha256,
            identity,
            AdapterOperation.TEACHER_FORCED,
        )
        _validate_accepted_manifest(
            request.accepted_manifest_sha256,
            request.trajectory,
            AdapterOperation.TEACHER_FORCED,
        )
        request_sha256 = _teacher_request_sha256(request)
        result = super().teacher_forced(request)
        result_payload = {
            "operation": AdapterOperation.TEACHER_FORCED.value,
            "request_sha256": request_sha256,
            "output_sha256": result.output_sha256,
            "output_shape": list(result.output_shape),
            "runtime_id": identity.runtime_id,
            "adapter_code_sha256": identity.adapter_code_sha256,
        }
        return dataclasses.replace(
            result,
            accepted_manifest_sha256=(
                request.trajectory.accepted_manifest_sha256
            ),
            adapter_code_sha256=identity.adapter_code_sha256,
            request_sha256=request_sha256,
            result_sha256=_canonical_sha256(result_payload),
        )

    def free_rollout(
        self, request: FreeRolloutRequest
    ) -> FreeRolloutResult:
        operation = AdapterOperation.FREE_ROLLOUT
        runtime, identity = self._require_runtime(operation)
        self._validate_rollout_request(runtime, identity, request)
        output_directory, video_path, metadata_path, failure_path = (
            self._prepare_output_paths(request)
        )
        request_sha256 = _canonical_sha256(_request_payload(request))
        try:
            output_directory.mkdir(parents=True, exist_ok=True)
            execution = self._rollout_executor(
                runtime,
                request.context,
                request,
                self._source_root_or_fail(operation),
                video_path,
            )
            self._validate_execution(execution, request)
            if not video_path.is_file():
                raise RuntimeError("official rollout did not create its MP4")
            probe = self._video_probe(video_path)
            self._validate_probe(probe, request)
            video_size = video_path.stat().st_size
            if video_size <= 0:
                raise RuntimeError("generated MP4 is empty")
            video_sha256 = sha256_file(video_path)
            generated_frame_ids = tuple(
                f"{request.run_id}:generated:{index}"
                for index in range(request.generated_frame_count)
            )
            document = self._rollout_document(
                request=request,
                identity=identity,
                request_sha256=request_sha256,
                execution=execution,
                probe=probe,
                video_path=video_path,
                video_size=video_size,
                video_sha256=video_sha256,
                generated_frame_ids=generated_frame_ids,
            )
            metadata_path.write_bytes(canonical_json_bytes(document))
            metadata_sha256 = sha256_file(metadata_path)
            result_sha256 = _canonical_sha256(
                {
                    "request_sha256": request_sha256,
                    "video_sha256": video_sha256,
                    "metadata_sha256": metadata_sha256,
                }
            )
            return FreeRolloutResult(
                runtime_identity=identity,
                trajectory_id=request.context.trajectory_id,
                run_id=request.run_id,
                generated_frame_count=execution.generated_frame_count,
                video_path=video_path,
                video_sha256=video_sha256,
                metadata_path=metadata_path,
                metadata_sha256=metadata_sha256,
                elapsed_seconds=execution.elapsed_seconds,
                requested_frame_count=request.generated_frame_count,
                output_width=probe.width,
                output_height=probe.height,
                output_frame_rate=probe.frame_rate,
                video_size_bytes=video_size,
                generated_frame_ids=generated_frame_ids,
                seed=request.seed,
                precision=request.precision,
                device=request.device,
                generation_config_sha256=(
                    request.generation_config_sha256
                ),
                token_sha256=request.context.token_sha256,
                frame_token_map_sha256=(
                    request.context.frame_token_map_sha256
                ),
                accepted_manifest_sha256=(
                    request.context.accepted_manifest_sha256
                ),
                adapter_code_sha256=identity.adapter_code_sha256,
                request_sha256=request_sha256,
                result_sha256=result_sha256,
                peak_cuda_allocated_bytes=(
                    execution.peak_cuda_allocated_bytes
                ),
                peak_cuda_reserved_bytes=(
                    execution.peak_cuda_reserved_bytes
                ),
                warnings=(),
            )
        except MineWorldAdapterError as exc:
            self._record_failure_or_raise(failure_path, request, exc)
            raise
        except Exception as exc:
            wrapped = _adapter_error(
                AdapterFailureCode.RUNTIME_EXECUTION_FAILED,
                operation,
                "official_rollout",
                str(exc),
                ("exception_type", type(exc).__name__),
                ("trajectory_id", request.context.trajectory_id),
            )
            self._record_failure_or_raise(failure_path, request, wrapped)
            raise wrapped from exc

    def _require_complete_runtime(
        self,
        operation: AdapterOperation,
    ) -> MineWorldRuntimeIdentity:
        _runtime, identity = self._require_runtime(operation)
        if (
            self._code_identity is None
            or identity.adapter_code_sha256 != self._code_identity.sha256
            or identity.adapter_code_inventory != self._code_identity.inventory
        ):
            raise _adapter_error(
                AdapterFailureCode.INVALID_PROVENANCE,
                operation,
                "adapter_code_identity",
                "loaded runtime lacks the exact Wave 4 code inventory",
            )
        return identity

    def _validate_rollout_request(
        self,
        runtime: _LoadedRuntime,
        identity: MineWorldRuntimeIdentity,
        request: FreeRolloutRequest,
    ) -> None:
        operation = AdapterOperation.FREE_ROLLOUT
        self._require_complete_runtime(operation)
        if request.seed > 0xFFFFFFFF:
            raise _adapter_error(
                AdapterFailureCode.INVALID_REQUEST,
                operation,
                "seed",
                "must fit the deterministic NumPy/PyTorch seed range",
            )
        if request.top_k is not None and request.top_k > 8192:
            raise _adapter_error(
                AdapterFailureCode.INVALID_REQUEST,
                operation,
                "top_k",
                "must not exceed the pinned visual vocabulary size 8192",
            )
        if request.runtime_identity != identity:
            raise _mismatch(
                operation,
                "runtime_identity",
                identity.runtime_id,
                getattr(request.runtime_identity, "runtime_id", "<invalid>"),
                request.context.trajectory_id,
            )
        _validate_expected_code(
            request.expected_adapter_code_sha256,
            identity,
            operation,
        )
        _validate_accepted_manifest(
            request.accepted_manifest_sha256,
            request.context,
            operation,
        )
        if request.precision != identity.precision:
            raise _mismatch(
                operation,
                "precision",
                identity.precision,
                request.precision,
                request.context.trajectory_id,
            )
        if request.device != identity.device:
            raise _mismatch(
                operation,
                "device",
                identity.device,
                request.device,
                request.context.trajectory_id,
            )
        if (
            request.context.runtime_identity != identity
            or request.context.tokenization_profile != TOKENIZATION_PROFILE
            or request.context.preprocessing_profile
            != identity.preprocessing_identity
            or request.context.action_conversion_profile
            != identity.action_conversion_identity
        ):
            raise _adapter_error(
                AdapterFailureCode.INVALID_PROVENANCE,
                operation,
                "context",
                "runtime or translation profile identity does not match",
                ("trajectory_id", request.context.trajectory_id),
            )
        if (
            _token_sha256(request.context.token_ids)
            != request.context.token_sha256
            or _frame_token_map_sha256(request.context.frame_token_map)
            != request.context.frame_token_map_sha256
        ):
            raise _adapter_error(
                AdapterFailureCode.INVALID_PROVENANCE,
                operation,
                "context",
                "token sequence or FrameTokenMap hash mismatch",
                ("trajectory_id", request.context.trajectory_id),
            )
        try:
            self._validate_teacher_input(
                runtime,
                request.context,
                TeacherForcedRequest(
                    runtime_identity=identity,
                    trajectory=request.context,
                    seed=request.seed,
                    precision=request.precision,
                    batch_size=1,
                ),
                identity,
            )
        except MineWorldAdapterError as exc:
            raise MineWorldAdapterError(
                exc.code,
                operation,
                f"rollout context failed validation: {exc}",
                details=(
                    *exc.details,
                    ("source_operation", exc.operation.value),
                ),
            ) from exc
        if (
            len(request.generation_actions)
            != request.generated_frame_count
        ):
            raise _mismatch(
                operation,
                "generation_actions",
                str(request.generated_frame_count),
                str(len(request.generation_actions)),
                request.context.trajectory_id,
            )
        if not request.context.included_frame_identities:
            raise _adapter_error(
                AdapterFailureCode.INVALID_REQUEST,
                operation,
                "context",
                "must contain at least one included accepted frame",
            )
        first_expected = request.context.included_frame_identities[-1]
        for index, action in enumerate(request.generation_actions):
            _validate_action(action, identity, operation=operation)
            if (
                action.adapter_code_sha256 != identity.adapter_code_sha256
                or action.mineocclude_revision != identity.mineocclude_revision
                or action.identity.trajectory_id
                != request.context.trajectory_id
                or action.identity.model_frame_idx
                != first_expected.model_frame_idx + index
            ):
                raise _adapter_error(
                    AdapterFailureCode.INVALID_IDENTITY,
                    operation,
                    f"generation_actions[{index}].identity",
                    "does not preserve action-to-next-frame causal order",
                    ("trajectory_id", request.context.trajectory_id),
                )
        expected_config = _rollout_generation_config_sha256(request)
        if request.generation_config_sha256 != expected_config:
            raise _mismatch(
                operation,
                "generation_config_sha256",
                expected_config,
                request.generation_config_sha256,
                request.context.trajectory_id,
            )
        context_visual = (
            len(request.context.frame_token_map.spans)
            * PINNED_VISUAL_TOKENS
        )
        generated_positions = request.generated_frame_count * (
            PINNED_ACTION_TOKENS + PINNED_VISUAL_TOKENS
        )
        if (
            context_visual + generated_positions
            > identity.max_position_embeddings
        ):
            raise _adapter_error(
                AdapterFailureCode.INVALID_REQUEST,
                operation,
                "position_budget",
                (
                    f"{context_visual} context visual positions + "
                    f"{generated_positions} generated action/visual positions "
                    f"exceed {identity.max_position_embeddings}"
                ),
                ("trajectory_id", request.context.trajectory_id),
            )
        if (
            getattr(runtime.model, "training", True)
            or getattr(runtime.vae, "training", True)
        ):
            raise _adapter_error(
                AdapterFailureCode.INVALID_REQUEST,
                operation,
                "runtime",
                "model and VAE must both be in evaluation mode",
            )

    def _prepare_output_paths(
        self,
        request: FreeRolloutRequest,
    ) -> tuple[Path, Path, Path, Path]:
        operation = AdapterOperation.FREE_ROLLOUT
        if (
            _SAFE_RUN_ID.fullmatch(request.run_id) is None
            or ".." in request.run_id
        ):
            raise _adapter_error(
                AdapterFailureCode.INVALID_REQUEST,
                operation,
                "run_id",
                "must be a path-free stable identifier",
            )
        output_directory = request.output_directory.resolve()
        if output_directory.is_relative_to(self._repository_root) and not (
            _is_git_ignored(output_directory, self._repository_root)
        ):
            raise _adapter_error(
                AdapterFailureCode.INVALID_REQUEST,
                operation,
                "output_directory",
                "must remain outside tracked source or in an ignored path",
            )
        source_root = self._source_root_or_fail(operation).resolve()
        if (
            output_directory == source_root
            or output_directory.is_relative_to(source_root)
        ):
            raise _adapter_error(
                AdapterFailureCode.INVALID_REQUEST,
                operation,
                "output_directory",
                "must not write into the pinned MineWorld checkout",
            )
        video_path = output_directory / f"{request.run_id}.mp4"
        metadata_path = output_directory / f"{request.run_id}.rollout.json"
        failure_path = output_directory / f"{request.run_id}.failure.json"
        protected = {path.resolve() for path in request.protected_input_paths}
        if self._runtime_load_request is not None:
            protected.update(
                {
                    self._runtime_load_request.model_config_path.resolve(),
                    self._runtime_load_request.main_checkpoint_path.resolve(),
                    self._runtime_load_request.vae_config_path.resolve(),
                    self._runtime_load_request.vae_checkpoint_path.resolve(),
                }
            )
        if {video_path, metadata_path, failure_path} & protected:
            raise _adapter_error(
                AdapterFailureCode.INVALID_REQUEST,
                operation,
                "output_directory",
                "would overwrite a protected source, media, or checkpoint file",
            )
        collisions = tuple(
            path
            for path in (video_path, metadata_path, failure_path)
            if path.exists()
        )
        if collisions and not request.allow_overwrite:
            raise _adapter_error(
                AdapterFailureCode.INVALID_REQUEST,
                operation,
                "output_collision",
                f"durable output already exists: {collisions[0]}",
            )
        return output_directory, video_path, metadata_path, failure_path

    @staticmethod
    def _validate_execution(
        execution: _RolloutExecution,
        request: FreeRolloutRequest,
    ) -> None:
        operation = AdapterOperation.FREE_ROLLOUT
        expected_tokens = (
            request.generated_frame_count * PINNED_VISUAL_TOKENS
        )
        if (
            not isinstance(execution, _RolloutExecution)
            or not execution.inference_mode_applied
            or execution.generated_frame_count
            != request.generated_frame_count
            or len(execution.generated_token_ids) != expected_tokens
            or any(
                type(token) is not int or token < 0 or token >= 8192
                for token in execution.generated_token_ids
            )
            or execution.generated_token_sha256
            != _canonical_sha256(list(execution.generated_token_ids))
            or not math.isfinite(execution.elapsed_seconds)
            or execution.elapsed_seconds < 0
            or execution.peak_cuda_allocated_bytes < 0
            or execution.peak_cuda_reserved_bytes < 0
        ):
            raise _adapter_error(
                AdapterFailureCode.RUNTIME_EXECUTION_FAILED,
                operation,
                "generation",
                "official generation result is incomplete or inconsistent",
            )

    @staticmethod
    def _validate_probe(
        probe: _VideoProbe,
        request: FreeRolloutRequest,
    ) -> None:
        if (
            not isinstance(probe, _VideoProbe)
            or probe.decoded_frames != request.generated_frame_count
            or probe.width != PINNED_OUTPUT_WIDTH
            or probe.height != PINNED_OUTPUT_HEIGHT
            or not math.isclose(
                probe.frame_rate,
                float(request.output_frame_rate),
                rel_tol=0,
                abs_tol=1e-6,
            )
            or not math.isfinite(probe.duration_seconds)
            or probe.duration_seconds <= 0
        ):
            raise _adapter_error(
                AdapterFailureCode.RUNTIME_EXECUTION_FAILED,
                AdapterOperation.FREE_ROLLOUT,
                "generated_video",
                "decoded output count, shape, frame rate, or duration mismatch",
            )

    def _rollout_document(
        self,
        *,
        request: FreeRolloutRequest,
        identity: MineWorldRuntimeIdentity,
        request_sha256: str,
        execution: _RolloutExecution,
        probe: _VideoProbe,
        video_path: Path,
        video_size: int,
        video_sha256: str,
        generated_frame_ids: tuple[str, ...],
    ) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "adapter_api_version": MINEWORLD_ADAPTER_API_VERSION,
            "report_version": ROLLOUT_REPORT_VERSION,
            "status": "completed",
            "operation": AdapterOperation.FREE_ROLLOUT.value,
            "identity": {
                "runtime": _runtime_payload(identity),
                "accepted_manifest_sha256": (
                    request.context.accepted_manifest_sha256
                ),
                "source_document_sha256": (
                    request.context.source_document_sha256
                ),
                "trajectory_id": request.context.trajectory_id,
                "token_sha256": request.context.token_sha256,
                "frame_token_map_sha256": (
                    request.context.frame_token_map_sha256
                ),
                "request_sha256": request_sha256,
            },
            "request": {
                **_rollout_generation_config_payload(request),
                "run_id": request.run_id,
                "seed": request.seed,
                "precision": request.precision,
                "device": request.device,
                "generation_config_sha256": (
                    request.generation_config_sha256
                ),
                "context_pair_count": (
                    request.context.context_pair_count
                ),
                "protected_input_paths": sorted(
                    str(path.resolve())
                    for path in request.protected_input_paths
                ),
                "allow_overwrite": request.allow_overwrite,
            },
            "generation": {
                "generated_frame_count": execution.generated_frame_count,
                "generated_frame_ids": list(generated_frame_ids),
                "generated_token_count": len(
                    execution.generated_token_ids
                ),
                "generated_token_sha256": (
                    execution.generated_token_sha256
                ),
                "inference_mode_applied": execution.inference_mode_applied,
            },
            "output": {
                "classification": "generated",
                "path": str(video_path),
                "size_bytes": video_size,
                "sha256": video_sha256,
                "decoded_frames": probe.decoded_frames,
                "width": probe.width,
                "height": probe.height,
                "frame_rate": probe.frame_rate,
                "duration_seconds": probe.duration_seconds,
                "storage_classification": "runtime_only_outside_git",
            },
            "runtime": {
                "elapsed_seconds": execution.elapsed_seconds,
                "peak_cuda_allocated_bytes": (
                    execution.peak_cuda_allocated_bytes
                ),
                "peak_cuda_reserved_bytes": (
                    execution.peak_cuda_reserved_bytes
                ),
            },
            "integrity_note": (
                "The report does not claim a cryptographic hash of itself; "
                "the caller records its byte hash after serialization."
            ),
        }

    @staticmethod
    def _write_failure_record(
        path: Path,
        request: FreeRolloutRequest,
        error: MineWorldAdapterError,
    ) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        document = {
            "schema_version": SCHEMA_VERSION,
            "adapter_api_version": MINEWORLD_ADAPTER_API_VERSION,
            "report_version": ROLLOUT_REPORT_VERSION,
            "status": "failed",
            "operation": error.operation.value,
            "run_id": request.run_id,
            "trajectory_id": request.context.trajectory_id,
            "failure": {
                "code": error.code.value,
                "message": str(error),
                "details": [
                    {"field": field, "value": value}
                    for field, value in error.details
                ],
            },
        }
        path.write_bytes(canonical_json_bytes(document))

    def _record_failure_or_raise(
        self,
        path: Path,
        request: FreeRolloutRequest,
        original: MineWorldAdapterError,
    ) -> None:
        try:
            self._write_failure_record(path, request, original)
        except Exception as exc:
            raise _adapter_error(
                AdapterFailureCode.RUNTIME_EXECUTION_FAILED,
                AdapterOperation.FREE_ROLLOUT,
                "failure_record",
                f"could not preserve durable failure evidence: {exc}",
                ("original_failure_code", original.code.value),
                ("original_failure", str(original)),
                ("exception_type", type(exc).__name__),
            ) from exc

    def _source_root_or_fail(
        self,
        operation: AdapterOperation,
    ) -> Path:
        if self._source_root is None:
            raise _adapter_error(
                AdapterFailureCode.OPERATION_UNAVAILABLE,
                operation,
                "mineworld_source_root",
                "runtime source identity is unavailable",
            )
        return self._source_root

    def _observed_code_identity(
        self,
        operation: AdapterOperation,
    ) -> _AdapterCodeIdentity:
        if self._code_identity is None:
            try:
                self._code_identity = self._code_identity_provider()
            except Exception as exc:
                raise _adapter_error(
                    AdapterFailureCode.INVALID_PROVENANCE,
                    operation,
                    "adapter_code_identity",
                    str(exc),
                    ("exception_type", type(exc).__name__),
                ) from exc
        return self._code_identity

    def _mineocclude_revision_or_none(self) -> str | None:
        if self._runtime_identity_record is None:
            return None
        return self._runtime_identity_record.mineocclude_revision


def _validate_expected_code(
    expected: str | None,
    identity: MineWorldRuntimeIdentity,
    operation: AdapterOperation,
) -> None:
    if identity.adapter_code_sha256 is None:
        raise _adapter_error(
            AdapterFailureCode.INVALID_PROVENANCE,
            operation,
            "adapter_code_sha256",
            "loaded runtime does not carry adapter code identity",
        )
    if expected is not None and expected != identity.adapter_code_sha256:
        raise _mismatch(
            operation,
            "expected_adapter_code_sha256",
            identity.adapter_code_sha256,
            expected,
        )


def _validate_accepted_manifest(
    expected: str | None,
    trajectory: TokenizedTrajectory,
    operation: AdapterOperation,
) -> None:
    observed = trajectory.accepted_manifest_sha256
    if observed is None:
        raise _adapter_error(
            AdapterFailureCode.INVALID_PROVENANCE,
            operation,
            "accepted_manifest_sha256",
            "tokenized trajectory does not carry accepted-package identity",
            ("trajectory_id", trajectory.trajectory_id),
        )
    if expected is not None and expected != observed:
        raise _mismatch(
            operation,
            "accepted_manifest_sha256",
            observed,
            expected,
            trajectory.trajectory_id,
        )


def _mismatch(
    operation: AdapterOperation,
    field: str,
    expected: object,
    observed: object,
    trajectory_id: str | None = None,
) -> MineWorldAdapterError:
    details = [
        ("failed_field", field),
        ("expected", repr(expected)),
        ("observed", repr(observed)),
    ]
    if trajectory_id is not None:
        details.append(("trajectory_id", trajectory_id))
    return _adapter_error(
        AdapterFailureCode.INVALID_PROVENANCE,
        operation,
        field,
        "identity mismatch",
        *details,
    )
