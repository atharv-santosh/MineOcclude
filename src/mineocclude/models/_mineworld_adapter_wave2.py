"""Private Person A Phase 3 Wave 2 adapter implementation.

Public callers obtain this implementation through
``mineocclude.models.mineworld_adapter.create_mineworld_adapter``.  This
module owns no public schema and is deliberately not re-exported.
"""

from __future__ import annotations

import copy
import hashlib
import importlib
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

from mineocclude.contracts.identity import SCHEMA_VERSION
from mineocclude.contracts.trajectory import (
    RejectionCode,
    validate_trajectory_package,
)
from mineocclude.models.mineworld_adapter import (
    MINEWORLD_ADAPTER_API_VERSION,
    AcceptedTrajectoryInput,
    ActionConversionRequest,
    AdapterFailureCode,
    AdapterOperation,
    ConvertedAction,
    FrameIdentity,
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
    UnavailableMineWorldAdapter,
    ValidatedTrajectory,
)
from mineocclude.models.phase2_aws import (
    EXPECTED_HIDDEN_SIZE,
    EXPECTED_LAYERS,
    PINNED_ASSET_REVISION,
    PINNED_MAIN_CHECKPOINT_SHA256,
    PINNED_MAX_POSITION_EMBEDDINGS,
    PINNED_PROCESSED_VIDEO_HEIGHT,
    PINNED_PROCESSED_VIDEO_WIDTH,
    PINNED_SOURCE_REVISION,
    PINNED_VAE_CHECKPOINT_SHA256,
    PINNED_VAE_CONFIG_SHA256,
    _decoder_layers,
    _external_source_imports,
    _load_model_with_key_evidence,
    _normalize_flat_action,
    _parameter_distribution,
    _validate_raw_action_fields,
)
from mineocclude.models.phase2_evidence import (
    ACTION_COMPATIBILITY_TRANSFORMATION,
    ACTION_COMPATIBILITY_VERSION,
    VIDEO_PREPROCESSING_TRANSFORMATION,
    VIDEO_PREPROCESSING_VERSION,
    canonical_json_bytes,
    sha256_file,
    validate_checkpoint_load_state,
)


PINNED_MODEL_CONFIG_SHA256 = (
    "e13b3a80fb370547a05852809c2c8f02d05ebe2fce3b3bb2fd1ee54eee78c018"
)
PINNED_MODEL_CLASS = "LlamaLVM"
PINNED_TRANSFORMER_CLASS = "LlamaForCausalLM"
PINNED_VAE_CLASS = "VAE"
PINNED_DECODER_PATH = "transformer.model.layers"
PINNED_INTERMEDIATE_SIZE = 4096
PINNED_VOCAB_SIZE = 8262
PINNED_ATTENTION_HEADS = 32
PINNED_KEY_VALUE_HEADS = 4
PINNED_VISUAL_TOKENS = 336
PINNED_ACTION_TOKENS = 11
PINNED_TOKENS_PER_PAIR = 347
PINNED_CONTEXT_PAIRS = 16
PINNED_PRECISION = "float16"
PINNED_DEVICE = "cuda:0"
PINNED_SOURCE_WIDTH = 640
PINNED_SOURCE_HEIGHT = 360
ACTION_VOCABULARY_OFFSET = 8192
ACTION_POSITIONAL_ROLES = (
    "bos",
    "camera_pitch",
    "camera_yaw",
    "hotbar",
    "forward_back",
    "left_right",
    "sprint_sneak",
    "use_attack",
    "jump",
    "drop_pick",
    "eos",
)
MCDATASET_BLOB_SHA256 = (
    "7e8d16db01f085481d41d340e5a0b84669b8e163f3338d5fd572731532c52746"
)
MINEWORLD_PREPROCESS_BLOB_SHA256 = (
    "036fa0b4899285e5499f88581f6e02426a25f732fcc26bd63c0f5b3863a9d9ab"
)
PREPROCESSING_PROFILE = (
    f"{VIDEO_PREPROCESSING_TRANSFORMATION}@{VIDEO_PREPROCESSING_VERSION}:"
    f"{MINEWORLD_PREPROCESS_BLOB_SHA256}"
)
ACTION_CONVERTER_IDENTITY = (
    f"{ACTION_COMPATIBILITY_TRANSFORMATION}@{ACTION_COMPATIBILITY_VERSION}:"
    f"{MCDATASET_BLOB_SHA256}"
)

_EXPECTED_ARCHITECTURE = {
    "model_class": PINNED_MODEL_CLASS,
    "transformer_class": PINNED_TRANSFORMER_CLASS,
    "vae_class": PINNED_VAE_CLASS,
    "decoder_layer_path": PINNED_DECODER_PATH,
    "layer_count": EXPECTED_LAYERS,
    "hidden_size": EXPECTED_HIDDEN_SIZE,
    "intermediate_size": PINNED_INTERMEDIATE_SIZE,
    "vocab_size": PINNED_VOCAB_SIZE,
    "max_position_embeddings": PINNED_MAX_POSITION_EMBEDDINGS,
    "num_attention_heads": PINNED_ATTENTION_HEADS,
    "num_key_value_heads": PINNED_KEY_VALUE_HEADS,
    "visual_tokens": PINNED_VISUAL_TOKENS,
    "action_tokens": PINNED_ACTION_TOKENS,
    "tokens_per_pair": PINNED_TOKENS_PER_PAIR,
    "context_pairs": PINNED_CONTEXT_PAIRS,
    "precision": PINNED_PRECISION,
    "device": PINNED_DEVICE,
}


@dataclass(frozen=True)
class _PreparedRuntime:
    request: RuntimeLoadRequest
    source_root: Path
    model_config: Path
    main_checkpoint: Path
    vae_config: Path
    vae_checkpoint: Path

    @property
    def checkpoint_identity(self) -> dict[str, Any]:
        return {
            "source_revision": self.request.mineworld_source_revision,
            "asset_revision": self.request.modelscope_asset_revision,
            "main_checkpoint_sha256": self.request.main_checkpoint_sha256,
            "vae_checkpoint_sha256": self.request.vae_checkpoint_sha256,
        }

    def as_phase2_prepared(self) -> dict[str, Any]:
        return {
            "source_root": self.source_root,
            "model_config": self.model_config,
            "main_checkpoint": self.main_checkpoint,
            "vae_config": self.vae_config,
            "vae_checkpoint": self.vae_checkpoint,
            "identity": {
                "run_id": self.request.runtime_id,
                "source_revision": self.request.mineworld_source_revision,
                "asset_revision": self.request.modelscope_asset_revision,
                "mineocclude_code_sha": self.request.mineocclude_revision,
                "mineocclude_dirty": False,
                "model_config_sha256": self.request.model_config_sha256,
                "main_checkpoint_sha256": self.request.main_checkpoint_sha256,
                "vae_config_sha256": self.request.vae_config_sha256,
                "vae_checkpoint_sha256": self.request.vae_checkpoint_sha256,
                "environment_report_sha256": (
                    self.request.environment_report_sha256
                ),
            },
        }


@dataclass
class _LoadedRuntime:
    model: Any
    vae: Any
    config: Any
    load_state: Mapping[str, Any]
    architecture: Mapping[str, Any]


@dataclass(frozen=True)
class _AcceptedFrame:
    identity: FrameIdentity
    render_frame_idx: int
    action_idx: int
    raw_action: Mapping[str, Any]
    raw_action_sha256: str


def _adapter_error(
    code: AdapterFailureCode,
    operation: AdapterOperation,
    field: str,
    message: str,
    *details: tuple[str, str],
) -> MineWorldAdapterError:
    return MineWorldAdapterError(
        code,
        operation,
        f"{field}: {message}",
        details=((field, message), *details),
    )


def _inspect_source(source_root: Path) -> tuple[str, bool]:
    def run(*arguments: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(source_root), *arguments],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode:
            raise RuntimeError(
                (result.stderr or result.stdout or "git inspection failed").strip()
            )
        return result.stdout.strip()

    # Interpreter caches and other untracked files do not change the audited
    # Git objects used by the adapter.  Require the pinned revision and no
    # tracked-file modifications while leaving unrelated untracked files out
    # of the scientific authority decision.
    return run("rev-parse", "HEAD"), not bool(
        run("status", "--porcelain", "--untracked-files=no")
    )


def _git_blob_sha256(source_root: Path, revision: str, relative_path: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(source_root), "show", f"{revision}:{relative_path}"],
        capture_output=True,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(
            (result.stderr or result.stdout or b"git show failed")
            .decode("utf-8", errors="replace")
            .strip()
        )
    return hashlib.sha256(result.stdout).hexdigest()


def _load_official_runtime(prepared: _PreparedRuntime) -> _LoadedRuntime:
    """Call the exact Phase 2 loader and preserve its audited load state."""

    try:
        import torch
    except Exception as exc:  # pragma: no cover - exercised on the GPU host
        raise RuntimeError(f"PyTorch could not be imported: {exc}") from exc

    model, config, load_state, _load_runtime = _load_model_with_key_evidence(
        prepared.as_phase2_prepared(),
        torch,
        precision=prepared.request.precision,
    )
    decoder_path, decoder_layers = _decoder_layers(model, torch)
    transformer_config = model.transformer.config
    architecture = {
        "model_class": model.__class__.__name__,
        "transformer_class": model.transformer.__class__.__name__,
        "vae_class": model.tokenizer.__class__.__name__,
        "decoder_layer_path": decoder_path,
        "layer_count": len(decoder_layers),
        "hidden_size": transformer_config.hidden_size,
        "intermediate_size": transformer_config.intermediate_size,
        "vocab_size": transformer_config.vocab_size,
        "max_position_embeddings": transformer_config.max_position_embeddings,
        "num_attention_heads": transformer_config.num_attention_heads,
        "num_key_value_heads": transformer_config.num_key_value_heads,
        "visual_tokens": PINNED_VISUAL_TOKENS,
        "action_tokens": PINNED_ACTION_TOKENS,
        "tokens_per_pair": PINNED_TOKENS_PER_PAIR,
        "context_pairs": PINNED_CONTEXT_PAIRS,
        "precision": prepared.request.precision,
        "device": prepared.request.device,
        "dtype_distribution": _parameter_distribution(model, "dtype"),
        "device_distribution": _parameter_distribution(model, "device"),
    }
    return _LoadedRuntime(
        model=model,
        vae=model.tokenizer,
        config=config,
        load_state=load_state,
        architecture=architecture,
    )


class _OfficialActionConverter:
    """Narrow invocation wrapper around the pinned MCDataset converter."""

    def __init__(self, source_root: Path) -> None:
        observed_revision, source_clean = _inspect_source(source_root)
        if observed_revision != PINNED_SOURCE_REVISION or not source_clean:
            raise RuntimeError(
                "Official action conversion requires the clean pinned "
                f"MineWorld checkout at {PINNED_SOURCE_REVISION}."
            )
        observed_hash = _git_blob_sha256(
            source_root, PINNED_SOURCE_REVISION, "mcdataset.py"
        )
        if observed_hash != MCDATASET_BLOB_SHA256:
            raise RuntimeError(
                "Pinned mcdataset.py Git-blob SHA-256 does not match the "
                "audited converter identity."
            )
        with _external_source_imports(source_root):
            module = importlib.import_module("mcdataset")
        module_path = Path(module.__file__).resolve()
        expected_path = (source_root / "mcdataset.py").resolve()
        if module_path != expected_path:
            raise RuntimeError(
                "Imported MCDataset does not come from the validated pinned "
                f"checkout: expected {expected_path}, observed {module_path}."
            )
        self._module = module
        self._converter = module.MCDataset()
        self._converter.make_action_vocab(
            action_vocab_offset=ACTION_VOCABULARY_OFFSET
        )
        self.required_action_keys = tuple(sorted(module.NOOP_ACTION))

    @property
    def keyboard_mapping(self) -> Mapping[str, str]:
        return self._module.KEYBOARD_BUTTON_MAPPING

    def convert(
        self, raw_action: Mapping[str, Any]
    ) -> tuple[dict[str, Any], tuple[int, ...], bool]:
        _validate_raw_action_fields(
            raw_action,
            0,
            keyboard_mapping=self.keyboard_mapping,
        )

        def once() -> tuple[dict[str, Any], tuple[int, ...], bool]:
            official_action, is_noop = (
                self._converter.json_action_to_env_action(
                    copy.deepcopy(dict(raw_action))
                )
            )
            normalized = _normalize_flat_action(
                official_action,
                0,
                required_action_keys=self.required_action_keys,
            )
            tokens = self._converter.get_action_index_from_actiondict(
                official_action,
                action_vocab_offset=ACTION_VOCABULARY_OFFSET,
            )
            if (
                not isinstance(tokens, list)
                or len(tokens) != PINNED_ACTION_TOKENS
                or any(type(token) is not int for token in tokens)
            ):
                raise RuntimeError(
                    "Pinned action converter did not return exactly 11 integers."
                )
            vocabulary = self._converter.action_vocab
            if min(vocabulary.values()) != ACTION_VOCABULARY_OFFSET:
                raise RuntimeError("Pinned action vocabulary offset changed.")
            allowed_tokens = set(vocabulary.values())
            if any(token not in allowed_tokens for token in tokens):
                raise RuntimeError(
                    "Pinned action converter returned a token outside its vocabulary."
                )
            return normalized, tuple(tokens), bool(is_noop)

        first = once()
        second = once()
        if first != second:
            raise RuntimeError("Pinned action conversion was nondeterministic.")
        return first


def _canonical_mapping_sha256(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(dict(value))).hexdigest()


def _array_sha256(value: Any) -> str:
    return hashlib.sha256(value.tobytes(order="C")).hexdigest()


def _preprocess_bgr_frame(frame: object) -> tuple[Any, dict[str, Any]]:
    try:
        import cv2
        import numpy as np
    except Exception as exc:
        raise RuntimeError(
            f"NumPy and OpenCV are required for frame preprocessing: {exc}"
        ) from exc

    if not isinstance(frame, np.ndarray):
        raise ValueError("frame must be a NumPy array")
    if frame.size == 0:
        raise ValueError("frame must not be empty")
    if frame.shape != (PINNED_SOURCE_HEIGHT, PINNED_SOURCE_WIDTH, 3):
        raise ValueError(
            "source frame must have shape "
            f"({PINNED_SOURCE_HEIGHT}, {PINNED_SOURCE_WIDTH}, 3)"
        )
    if frame.dtype != np.uint8:
        raise ValueError("source frame dtype must be uint8")
    if not np.isfinite(frame).all():
        raise ValueError("source frame must contain only finite values")

    source = np.ascontiguousarray(frame)
    rgb = cv2.cvtColor(source, cv2.COLOR_BGR2RGB)
    resized = cv2.resize(
        rgb,
        (PINNED_PROCESSED_VIDEO_WIDTH, PINNED_PROCESSED_VIDEO_HEIGHT),
        interpolation=cv2.INTER_LINEAR,
    )
    if resized.shape != (
        PINNED_PROCESSED_VIDEO_HEIGHT,
        PINNED_PROCESSED_VIDEO_WIDTH,
        3,
    ):
        raise RuntimeError("OpenCV returned an unexpected resized frame shape.")
    if resized.dtype != np.uint8:
        raise RuntimeError("OpenCV did not preserve uint8 before normalization.")
    tensor = np.ascontiguousarray(
        resized.transpose(2, 0, 1).astype(np.float32) / np.float32(255.0)
    )
    tensor = np.ascontiguousarray(
        (tensor - np.float32(0.5)) / np.float32(0.5)
    )
    if tensor.shape != (
        3,
        PINNED_PROCESSED_VIDEO_HEIGHT,
        PINNED_PROCESSED_VIDEO_WIDTH,
    ):
        raise RuntimeError("Normalized frame has an unexpected CHW shape.")
    if tensor.dtype != np.float32 or not np.isfinite(tensor).all():
        raise RuntimeError("Normalized frame must be finite float32.")
    statistics = {
        "minimum": float(tensor.min()),
        "maximum": float(tensor.max()),
        "mean": float(tensor.mean()),
        "standard_deviation": float(tensor.std()),
    }
    return tensor, {
        "source_shape": tuple(int(value) for value in source.shape),
        "source_dtype": str(source.dtype),
        "source_sha256": _array_sha256(source),
        "output_shape": tuple(int(value) for value in tensor.shape),
        "output_dtype": str(tensor.dtype),
        "output_sha256": _array_sha256(tensor),
        "statistics": statistics,
    }


class _Wave2MineWorldAdapter:
    """Private stateful implementation of the frozen public adapter protocol."""

    def __init__(
        self,
        *,
        file_hasher: Callable[[Path], str] = sha256_file,
        source_inspector: Callable[[Path], tuple[str, bool]] = _inspect_source,
        runtime_loader: Callable[[_PreparedRuntime], _LoadedRuntime] = (
            _load_official_runtime
        ),
        converter_factory: Callable[[Path], Any] = _OfficialActionConverter,
    ) -> None:
        self._file_hasher = file_hasher
        self._source_inspector = source_inspector
        self._runtime_loader = runtime_loader
        self._converter_factory = converter_factory
        self._runtime: _LoadedRuntime | None = None
        self._runtime_identity_record: MineWorldRuntimeIdentity | None = None
        self._source_root: Path | None = None
        self._converter: Any | None = None
        self._accepted_frames: dict[tuple[str, int], _AcceptedFrame] = {}
        self._unavailable = UnavailableMineWorldAdapter()

    def load_runtime(
        self, request: RuntimeLoadRequest
    ) -> MineWorldRuntimeIdentity:
        prepared = self._prepare_runtime(request)
        try:
            loaded = self._runtime_loader(prepared)
        except MineWorldAdapterError:
            raise
        except Exception as exc:
            raise _adapter_error(
                AdapterFailureCode.INVALID_REQUEST,
                AdapterOperation.LOAD_RUNTIME,
                "runtime_loader",
                str(exc),
            ) from exc

        self._validate_load_state(loaded.load_state, prepared)
        self._validate_architecture(loaded.architecture)
        for label, object_ in (("model", loaded.model), ("vae", loaded.vae)):
            eval_method = getattr(object_, "eval", None)
            if not callable(eval_method):
                raise _adapter_error(
                    AdapterFailureCode.INVALID_REQUEST,
                    AdapterOperation.LOAD_RUNTIME,
                    label,
                    "loaded object does not expose eval()",
                )
            eval_method()

        identity = MineWorldRuntimeIdentity(
            schema_version=SCHEMA_VERSION,
            adapter_api_version=MINEWORLD_ADAPTER_API_VERSION,
            runtime_id=request.runtime_id,
            mineocclude_revision=request.mineocclude_revision,
            mineworld_source_revision=request.mineworld_source_revision,
            modelscope_asset_revision=request.modelscope_asset_revision,
            model_config_sha256=request.model_config_sha256,
            main_checkpoint_sha256=request.main_checkpoint_sha256,
            vae_config_sha256=request.vae_config_sha256,
            vae_checkpoint_sha256=request.vae_checkpoint_sha256,
            environment_report_sha256=request.environment_report_sha256,
            preprocessing_identity=PREPROCESSING_PROFILE,
            action_conversion_identity=ACTION_CONVERTER_IDENTITY,
            model_class=PINNED_MODEL_CLASS,
            transformer_class=PINNED_TRANSFORMER_CLASS,
            vae_class=PINNED_VAE_CLASS,
            decoder_layer_path=PINNED_DECODER_PATH,
            layer_count=EXPECTED_LAYERS,
            hidden_size=EXPECTED_HIDDEN_SIZE,
            max_position_embeddings=PINNED_MAX_POSITION_EMBEDDINGS,
            visual_tokens_per_frame=PINNED_VISUAL_TOKENS,
            action_tokens_per_frame=PINNED_ACTION_TOKENS,
            tokens_per_pair=PINNED_TOKENS_PER_PAIR,
            max_context_pairs=PINNED_CONTEXT_PAIRS,
            precision=request.precision,
            device=request.device,
        )
        self._runtime = loaded
        self._runtime_identity_record = identity
        self._source_root = prepared.source_root
        return identity

    def validate_trajectory(
        self, request: AcceptedTrajectoryInput
    ) -> ValidatedTrajectory:
        document = request.document
        result = validate_trajectory_package(document)
        if not result.accepted:
            first = result.rejections[0]
            code = _contract_failure_code(first.code)
            raise _adapter_error(
                code,
                AdapterOperation.VALIDATE_TRAJECTORY,
                "$",
                first.message,
                ("contract_rejection_code", first.code.value),
                ("rejection_count", str(len(result.rejections))),
                ("request_trajectory_id", request.trajectory_id),
            )
        if document.get("schema_version") != request.schema_version:
            raise _adapter_error(
                AdapterFailureCode.INVALID_SCHEMA_VERSION,
                AdapterOperation.VALIDATE_TRAJECTORY,
                "$.schema_version",
                "request and accepted package schema versions differ",
            )
        if document.get("trajectory_id") != request.trajectory_id:
            raise _adapter_error(
                AdapterFailureCode.INVALID_IDENTITY,
                AdapterOperation.VALIDATE_TRAJECTORY,
                "$.trajectory_id",
                "request and accepted package trajectory identities differ",
            )
        try:
            source_document_sha256 = hashlib.sha256(
                canonical_json_bytes(document)
            ).hexdigest()
        except (TypeError, ValueError) as exc:
            raise _adapter_error(
                AdapterFailureCode.INVALID_REQUEST,
                AdapterOperation.VALIDATE_TRAJECTORY,
                "$",
                f"accepted package is not deterministic finite JSON: {exc}",
            ) from exc

        frame_rows = document["streams"]["frame_map"]
        raw_rows = {
            (row["trajectory_id"], row["model_frame_idx"]): row
            for row in document["streams"]["raw_actions"]
        }
        accepted_frames: dict[tuple[str, int], _AcceptedFrame] = {}
        identities: list[FrameIdentity] = []
        for row in frame_rows:
            identity = FrameIdentity(
                schema_version=SCHEMA_VERSION,
                trajectory_id=row["trajectory_id"],
                model_frame_idx=row["model_frame_idx"],
            )
            raw_action = raw_rows[identity.key]["raw_action"]
            raw_action_hash = _canonical_mapping_sha256(raw_action)
            accepted_frames[identity.key] = _AcceptedFrame(
                identity=identity,
                render_frame_idx=row["render_frame_idx"],
                action_idx=row["action_idx"],
                raw_action=MappingProxyType(copy.deepcopy(dict(raw_action))),
                raw_action_sha256=raw_action_hash,
            )
            identities.append(identity)
        self._accepted_frames = accepted_frames
        return ValidatedTrajectory(
            schema_version=SCHEMA_VERSION,
            trajectory_id=request.trajectory_id,
            accepted_manifest_sha256=request.accepted_manifest_sha256,
            source_document_sha256=source_document_sha256,
            frame_identities=tuple(identities),
        )

    def preprocess_frame(
        self, request: FramePreprocessRequest
    ) -> PreprocessedFrame:
        accepted = self._require_accepted_frame(
            request.identity, AdapterOperation.PREPROCESS_FRAME
        )
        if request.source_frame_idx != accepted.render_frame_idx:
            raise _adapter_error(
                AdapterFailureCode.INVALID_IDENTITY,
                AdapterOperation.PREPROCESS_FRAME,
                "source_frame_idx",
                "does not match the accepted render_frame_idx",
            )
        try:
            tensor, evidence = _preprocess_bgr_frame(request.frame)
        except Exception as exc:
            raise _adapter_error(
                AdapterFailureCode.INVALID_REQUEST,
                AdapterOperation.PREPROCESS_FRAME,
                "frame",
                str(exc),
            ) from exc
        expected_evidence = {
            "source_shape": (
                PINNED_SOURCE_HEIGHT,
                PINNED_SOURCE_WIDTH,
                3,
            ),
            "source_dtype": "uint8",
            "output_shape": (
                3,
                PINNED_PROCESSED_VIDEO_HEIGHT,
                PINNED_PROCESSED_VIDEO_WIDTH,
            ),
            "output_dtype": "float32",
        }
        for field, expected in expected_evidence.items():
            if evidence.get(field) != expected:
                raise _adapter_error(
                    AdapterFailureCode.INVALID_REQUEST,
                    AdapterOperation.PREPROCESS_FRAME,
                    field,
                    (
                        "preprocessing postcondition mismatch; "
                        f"expected {expected!r}, observed {evidence.get(field)!r}"
                    ),
                )
        if (
            tuple(getattr(tensor, "shape", ())) != expected_evidence["output_shape"]
            or str(getattr(tensor, "dtype", "")) != "float32"
        ):
            raise _adapter_error(
                AdapterFailureCode.INVALID_REQUEST,
                AdapterOperation.PREPROCESS_FRAME,
                "frame",
                "preprocessed payload contradicts its pinned shape or dtype",
            )
        return PreprocessedFrame(
            identity=request.identity,
            source_frame_idx=request.source_frame_idx,
            shape=evidence["output_shape"],
            dtype=evidence["output_dtype"],
            color_order="RGB",
            content_sha256=evidence["output_sha256"],
            frame=tensor,
            source_shape=evidence["source_shape"],
            source_dtype=evidence["source_dtype"],
            color_conversion="BGR_TO_RGB",
            interpolation="cv2.INTER_LINEAR",
            preprocessing_profile=PREPROCESSING_PROFILE,
            source_sha256=evidence["source_sha256"],
            statistics=tuple(evidence["statistics"].items()),
        )

    def convert_action(
        self, request: ActionConversionRequest
    ) -> ConvertedAction:
        accepted = self._require_accepted_frame(
            request.identity, AdapterOperation.CONVERT_ACTION
        )
        if request.action_idx != accepted.action_idx:
            raise _adapter_error(
                AdapterFailureCode.INVALID_IDENTITY,
                AdapterOperation.CONVERT_ACTION,
                "action_idx",
                "does not match the accepted action_idx",
            )
        try:
            raw_hash = _canonical_mapping_sha256(request.raw_action)
        except (TypeError, ValueError) as exc:
            raise _adapter_error(
                AdapterFailureCode.INVALID_REQUEST,
                AdapterOperation.CONVERT_ACTION,
                "raw_action",
                f"must be deterministic finite JSON: {exc}",
            ) from exc
        if raw_hash != accepted.raw_action_sha256:
            raise _adapter_error(
                AdapterFailureCode.INVALID_IDENTITY,
                AdapterOperation.CONVERT_ACTION,
                "raw_action",
                "does not match the accepted raw-action row",
            )
        if self._source_root is None:
            raise _adapter_error(
                AdapterFailureCode.OPERATION_UNAVAILABLE,
                AdapterOperation.CONVERT_ACTION,
                "runtime",
                "load_runtime must establish the pinned source first",
            )
        try:
            if self._converter is None:
                self._converter = self._converter_factory(self._source_root)
            normalized, tokens, is_noop = self._converter.convert(
                request.raw_action
            )
        except MineWorldAdapterError:
            raise
        except Exception as exc:
            raise _adapter_error(
                AdapterFailureCode.INVALID_REQUEST,
                AdapterOperation.CONVERT_ACTION,
                "raw_action",
                str(exc),
            ) from exc
        content = {
            "normalized_action": normalized,
            "token_ids": list(tokens),
            "positional_roles": list(ACTION_POSITIONAL_ROLES),
            "vocabulary_offset": ACTION_VOCABULARY_OFFSET,
        }
        return ConvertedAction(
            identity=request.identity,
            action_idx=request.action_idx,
            token_ids=tokens,
            converter_identity=ACTION_CONVERTER_IDENTITY,
            content_sha256=hashlib.sha256(
                canonical_json_bytes(content)
            ).hexdigest(),
            raw_action_sha256=raw_hash,
            normalized_action=MappingProxyType(copy.deepcopy(normalized)),
            vocabulary_offset=ACTION_VOCABULARY_OFFSET,
            positional_roles=ACTION_POSITIONAL_ROLES,
            converter_source_revision=PINNED_SOURCE_REVISION,
            is_noop=is_noop,
        )

    def tokenize_trajectory(
        self, request: TrajectoryTokenizationRequest
    ) -> TokenizedTrajectory:
        return self._unavailable.tokenize_trajectory(request)

    def teacher_forced(
        self, request: TeacherForcedRequest
    ) -> TeacherForcedResult:
        return self._unavailable.teacher_forced(request)

    def free_rollout(
        self, request: FreeRolloutRequest
    ) -> FreeRolloutResult:
        return self._unavailable.free_rollout(request)

    def _prepare_runtime(self, request: RuntimeLoadRequest) -> _PreparedRuntime:
        operation = AdapterOperation.LOAD_RUNTIME
        source_root = request.mineworld_source_root.resolve()
        if not source_root.is_dir():
            raise _adapter_error(
                AdapterFailureCode.INVALID_REQUEST,
                operation,
                "mineworld_source_root",
                "directory does not exist",
            )
        expected_model_config = (
            source_root / "configs" / "700M_16f.yaml"
        ).resolve()
        if request.model_config_path.resolve() != expected_model_config:
            raise _adapter_error(
                AdapterFailureCode.INVALID_PROVENANCE,
                operation,
                "model_config_path",
                f"must be the pinned 700M_16f config at {expected_model_config}",
            )
        if request.mineworld_source_revision != PINNED_SOURCE_REVISION:
            raise _adapter_error(
                AdapterFailureCode.INVALID_PROVENANCE,
                operation,
                "mineworld_source_revision",
                "does not match the pinned Phase 2 source revision",
            )
        if request.modelscope_asset_revision != PINNED_ASSET_REVISION:
            raise _adapter_error(
                AdapterFailureCode.INVALID_PROVENANCE,
                operation,
                "modelscope_asset_revision",
                "does not match the pinned Phase 2 asset revision",
            )
        expected_hashes = {
            "model_config_sha256": PINNED_MODEL_CONFIG_SHA256,
            "main_checkpoint_sha256": PINNED_MAIN_CHECKPOINT_SHA256,
            "vae_config_sha256": PINNED_VAE_CONFIG_SHA256,
            "vae_checkpoint_sha256": PINNED_VAE_CHECKPOINT_SHA256,
        }
        for field, expected in expected_hashes.items():
            if getattr(request, field) != expected:
                raise _adapter_error(
                    AdapterFailureCode.INVALID_PROVENANCE,
                    operation,
                    field,
                    "does not match the pinned Phase 2 identity",
                )
        if request.precision != PINNED_PRECISION:
            raise _adapter_error(
                AdapterFailureCode.INVALID_PROVENANCE,
                operation,
                "precision",
                f"must equal {PINNED_PRECISION}",
            )
        if request.device != PINNED_DEVICE:
            raise _adapter_error(
                AdapterFailureCode.INVALID_PROVENANCE,
                operation,
                "device",
                f"must equal {PINNED_DEVICE}",
            )
        paths = {
            "model_config": expected_model_config,
            "main_checkpoint": request.main_checkpoint_path.resolve(),
            "vae_config": request.vae_config_path.resolve(),
            "vae_checkpoint": request.vae_checkpoint_path.resolve(),
        }
        expected_by_role = {
            "model_config": request.model_config_sha256,
            "main_checkpoint": request.main_checkpoint_sha256,
            "vae_config": request.vae_config_sha256,
            "vae_checkpoint": request.vae_checkpoint_sha256,
        }
        for role, path in paths.items():
            if not path.is_file():
                raise _adapter_error(
                    AdapterFailureCode.INVALID_REQUEST,
                    operation,
                    role,
                    f"file does not exist: {path}",
                )
            actual_hash = self._file_hasher(path)
            if actual_hash != expected_by_role[role]:
                raise _adapter_error(
                    AdapterFailureCode.INVALID_PROVENANCE,
                    operation,
                    role,
                    (
                        "SHA-256 mismatch before checkpoint loading; "
                        f"expected {expected_by_role[role]}, observed {actual_hash}"
                    ),
                )
        try:
            observed_revision, source_clean = self._source_inspector(source_root)
        except Exception as exc:
            raise _adapter_error(
                AdapterFailureCode.INVALID_PROVENANCE,
                operation,
                "mineworld_source_root",
                f"source inspection failed: {exc}",
            ) from exc
        if observed_revision != request.mineworld_source_revision:
            raise _adapter_error(
                AdapterFailureCode.INVALID_PROVENANCE,
                operation,
                "mineworld_source_revision",
                f"observed checkout revision {observed_revision}",
            )
        if not source_clean:
            raise _adapter_error(
                AdapterFailureCode.INVALID_PROVENANCE,
                operation,
                "mineworld_source_root",
                "pinned source checkout is dirty",
            )
        return _PreparedRuntime(
            request=request,
            source_root=source_root,
            model_config=paths["model_config"],
            main_checkpoint=paths["main_checkpoint"],
            vae_config=paths["vae_config"],
            vae_checkpoint=paths["vae_checkpoint"],
        )

    @staticmethod
    def _validate_load_state(
        load_state: Mapping[str, Any],
        prepared: _PreparedRuntime,
    ) -> None:
        rejections = validate_checkpoint_load_state(
            load_state,
            prepared.checkpoint_identity,
        )
        if rejections:
            first = rejections[0]
            raise _adapter_error(
                AdapterFailureCode.INVALID_PROVENANCE,
                AdapterOperation.LOAD_RUNTIME,
                first.path,
                first.message,
                ("checkpoint_rejection_code", first.code),
            )

    @staticmethod
    def _validate_architecture(architecture: Mapping[str, Any]) -> None:
        for field, expected in _EXPECTED_ARCHITECTURE.items():
            if architecture.get(field) != expected:
                raise _adapter_error(
                    AdapterFailureCode.INVALID_PROVENANCE,
                    AdapterOperation.LOAD_RUNTIME,
                    f"architecture.{field}",
                    f"expected {expected!r}, observed {architecture.get(field)!r}",
                )

    def _require_accepted_frame(
        self,
        identity: FrameIdentity,
        operation: AdapterOperation,
    ) -> _AcceptedFrame:
        accepted = self._accepted_frames.get(identity.key)
        if accepted is None:
            raise _adapter_error(
                AdapterFailureCode.INVALID_IDENTITY,
                operation,
                "identity",
                "frame was not accepted by validate_trajectory",
            )
        return accepted


def _contract_failure_code(code: RejectionCode) -> AdapterFailureCode:
    if code is RejectionCode.INVALID_SCHEMA_VERSION:
        return AdapterFailureCode.INVALID_SCHEMA_VERSION
    if code in {
        RejectionCode.INVALID_IDENTITY_TYPE,
        RejectionCode.DUPLICATE_IDENTITY,
        RejectionCode.IDENTITY_MISMATCH,
        RejectionCode.NON_CONSECUTIVE_SERVER_TICKS,
    }:
        return AdapterFailureCode.INVALID_IDENTITY
    if code in {
        RejectionCode.INVALID_HASH,
        RejectionCode.INVALID_ARTIFACT_DESCRIPTOR,
    }:
        return AdapterFailureCode.INVALID_PROVENANCE
    return AdapterFailureCode.INVALID_REQUEST
