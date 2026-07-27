"""Bounded activation extraction and limited pilot-artifact validation.

Ordinary extraction returns only independently owned pooled CPU candidates.
Unpooled retention is a separate explicit opt-in used for one audited frame.
"""

from __future__ import annotations

import hashlib
import importlib
import io
import json
import math
import os
import tempfile
import zipfile
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Any

from mineocclude.activations.hooks import (
    EXPECTED_DECODER_LAYER_COUNT,
    HookCapture,
)
from mineocclude.activations.pool import (
    PooledVisualActivation,
    VisualPoolingError,
    VisualTokenSelection,
    VisualTokenSelectionError,
    mean_pool_visual_tokens,
    select_visual_token_positions,
)
from mineocclude.contracts.activation import (
    VISUAL_TOKENS_PER_FRAME,
    validate_activation_handoff,
)
from mineocclude.contracts.identity import (
    SCHEMA_VERSION,
    IdentityValidationError,
    validate_identity,
)
from mineocclude.models.mineworld_adapter import FrameTokenMap

LIMITED_UNPOOLED_ARTIFACT_VERSION = "person-a-limited-unpooled-pilot-v1.1"
LIMITED_UNPOOLED_CLASSIFICATION = "limited_one_frame_unpooled_pilot"
MAX_UNPOOLED_ARTIFACT_SIZE_BYTES = 32 * 1024 * 1024
UNPOOLED_REPRODUCTION_RTOL = 1e-3
UNPOOLED_REPRODUCTION_ATOL = 1e-3
UNPOOLED_TOKEN_ARRAY_NAME = "token_values"
UNPOOLED_POOLED_ARRAY_NAME = "pooled_means"
UNPOOLED_LAYER_ARRAY_NAME = "layer_indices"
UNPOOLED_POSITION_ARRAY_NAME = "visual_positions"
_UNPOOLED_ARRAY_NAMES = (
    UNPOOLED_TOKEN_ARRAY_NAME,
    UNPOOLED_POOLED_ARRAY_NAME,
    UNPOOLED_LAYER_ARRAY_NAME,
    UNPOOLED_POSITION_ARRAY_NAME,
)
_TENSOR_ARTIFACT_SUFFIXES = {
    ".ckpt",
    ".npy",
    ".npz",
    ".pt",
    ".pth",
    ".safetensors",
}
_SHA256_LENGTH = 64
_GIT_SHA_LENGTH = 40


class ExtractionErrorCode(str, Enum):
    """Stable failure codes for complete extraction and pilot storage."""

    INVALID_CAPTURES = "invalid_captures"
    INCOMPLETE_LAYERS = "incomplete_layers"
    INCONSISTENT_CAPTURE = "inconsistent_capture"
    INVALID_FRAME_TOKEN_MAP = "invalid_frame_token_map"
    INVALID_HOOK_SITE = "invalid_hook_site"
    INVALID_CANDIDATES = "invalid_candidates"
    UNPOOLED_DISABLED = "unpooled_disabled"
    INVALID_IDENTITY = "invalid_identity"
    UNSAFE_OUTPUT = "unsafe_output"
    OUTPUT_EXISTS = "output_exists"
    SERIALIZATION_FAILED = "serialization_failed"
    SIZE_LIMIT_EXCEEDED = "size_limit_exceeded"
    MISSING_ARTIFACT = "missing_artifact"
    INVALID_MANIFEST = "invalid_manifest"
    ARTIFACT_IDENTITY_MISMATCH = "artifact_identity_mismatch"
    UNSAFE_ARRAY = "unsafe_array"
    POOLING_AUDIT_FAILED = "pooling_audit_failed"
    EXTRA_ARTIFACT = "extra_artifact"


class ActivationExtractionError(ValueError):
    """Actionable project-owned extraction or artifact failure."""

    def __init__(
        self,
        code: ExtractionErrorCode,
        message: str,
        *,
        field: str | None = None,
        layer_idx: int | None = None,
    ) -> None:
        self.code = code
        self.field = field
        self.layer_idx = layer_idx
        prefix = code.value
        if field is not None:
            prefix += f"[field={field}]"
        if layer_idx is not None:
            prefix += f"[layer_idx={layer_idx}]"
        super().__init__(f"{prefix}: {message}")


@dataclass(frozen=True)
class CaptureSetFacts:
    """Non-owning scalar facts validated across one complete capture set."""

    layer_count: int
    batch_size: int
    sequence_length: int
    hidden_size: int
    source_dtype: str
    source_device: str
    normalization_identity: tuple[str, int | None, str | None]


@dataclass(frozen=True)
class UnpooledPilotIdentity:
    """Complete provenance for one explicitly enabled unpooled pilot."""

    session_id: str
    trajectory_id: str
    model_frame_idx: int
    hook_site: str
    frame_token_map_sha256: str
    mineocclude_revision: str
    mineworld_revision: str
    asset_revision: str
    model_config_sha256: str
    main_checkpoint_sha256: str
    vae_config_sha256: str
    vae_checkpoint_sha256: str
    environment_report_sha256: str
    preprocessing_profile: str
    action_conversion_profile: str
    tokenization_profile: str
    accepted_trajectory_package_sha256: str
    input_mp4_sha256: str

    def __post_init__(self) -> None:
        text_fields = (
            "session_id",
            "trajectory_id",
            "hook_site",
            "preprocessing_profile",
            "action_conversion_profile",
            "tokenization_profile",
        )
        for field_name in text_fields:
            _require_text(getattr(self, field_name), field_name)
        if (
            not isinstance(self.model_frame_idx, int)
            or isinstance(self.model_frame_idx, bool)
            or self.model_frame_idx < 0
        ):
            _fail(
                ExtractionErrorCode.INVALID_IDENTITY,
                "model_frame_idx must be a non-negative integer",
                field="model_frame_idx",
            )
        for field_name in (
            "frame_token_map_sha256",
            "model_config_sha256",
            "main_checkpoint_sha256",
            "vae_config_sha256",
            "vae_checkpoint_sha256",
            "environment_report_sha256",
            "accepted_trajectory_package_sha256",
            "input_mp4_sha256",
        ):
            _require_hex(
                getattr(self, field_name),
                field_name,
                _SHA256_LENGTH,
            )
        for field_name in (
            "mineocclude_revision",
            "mineworld_revision",
            "asset_revision",
        ):
            _require_hex(
                getattr(self, field_name),
                field_name,
                _GIT_SHA_LENGTH,
            )


@dataclass(frozen=True)
class LimitedUnpooledPilot:
    """Immutable scalar identity for a written limited pilot."""

    session_id: str
    trajectory_id: str
    model_frame_idx: int
    hook_site: str
    source_sequence_length: int
    source_hidden_size: int
    source_dtype: str
    source_device: str
    manifest_path: Path
    artifact_path: Path
    manifest_size_bytes: int
    artifact_size_bytes: int
    manifest_sha256: str
    artifact_sha256: str
    token_shape: tuple[int, int, int]
    token_dtype: str
    pooled_shape: tuple[int, int]
    pooled_dtype: str
    layer_indices: tuple[int, ...]
    visual_positions: tuple[int, ...]
    pooling_maximum_absolute_difference: float
    pooling_maximum_tolerance_ratio: float
    pooling_unequal_layer_count: int
    pooling_audit: tuple[Mapping[str, object], ...]


def _fail(
    code: ExtractionErrorCode,
    message: str,
    *,
    field: str | None = None,
    layer_idx: int | None = None,
) -> None:
    raise ActivationExtractionError(
        code,
        message,
        field=field,
        layer_idx=layer_idx,
    )


def _require_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail(
            ExtractionErrorCode.INVALID_IDENTITY,
            "must be a non-empty string",
            field=field,
        )
    return value


def _require_hex(value: object, field: str, length: int) -> str:
    if (
        not isinstance(value, str)
        or len(value) != length
        or any(character not in "0123456789abcdef" for character in value)
    ):
        _fail(
            ExtractionErrorCode.INVALID_IDENTITY,
            f"must be a lowercase {length}-character hexadecimal value",
            field=field,
        )
    return value


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _strict_json(path: Path) -> Mapping[str, Any]:
    def duplicate_reject(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                _fail(
                    ExtractionErrorCode.INVALID_MANIFEST,
                    f"duplicate JSON key {key!r}",
                )
            result[key] = value
        return result

    def constant_reject(value: str) -> None:
        _fail(
            ExtractionErrorCode.INVALID_MANIFEST,
            f"nonfinite JSON constant {value!r}",
        )

    try:
        parsed = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=duplicate_reject,
            parse_constant=constant_reject,
        )
    except ActivationExtractionError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        _fail(
            ExtractionErrorCode.INVALID_MANIFEST,
            f"could not parse manifest: {exc}",
        )
    if not isinstance(parsed, dict):
        _fail(
            ExtractionErrorCode.INVALID_MANIFEST,
            "manifest root must be an object",
        )
    return parsed


def _capture_tensor(capture: HookCapture, layer_idx: int) -> object:
    if not isinstance(capture, HookCapture):
        _fail(
            ExtractionErrorCode.INVALID_CAPTURES,
            "each capture must be HookCapture",
            layer_idx=layer_idx,
        )
    if capture.layer.layer_idx != layer_idx:
        _fail(
            ExtractionErrorCode.INCONSISTENT_CAPTURE,
            "mapping key and capture layer identity differ",
            layer_idx=layer_idx,
        )
    return capture.output.tensor


def validate_complete_capture_set(
    captures: Mapping[int, HookCapture],
    *,
    hook_site: str,
) -> CaptureSetFacts:
    """Validate scalar/tensor facts for one complete 20-layer capture set."""

    _require_text(hook_site, "hook_site")
    if not isinstance(captures, Mapping):
        _fail(
            ExtractionErrorCode.INVALID_CAPTURES,
            "captures must be a layer-indexed mapping",
        )
    expected = tuple(range(EXPECTED_DECODER_LAYER_COUNT))
    raw_keys = tuple(captures)
    keys_are_integers = all(
        isinstance(key, int) and not isinstance(key, bool)
        for key in raw_keys
    )
    observed = tuple(sorted(raw_keys)) if keys_are_integers else raw_keys
    if (
        not keys_are_integers
        or observed != expected
        or len(captures) != EXPECTED_DECODER_LAYER_COUNT
    ):
        _fail(
            ExtractionErrorCode.INCOMPLETE_LAYERS,
            "capture keys must be exactly 0 through 19; "
            f"observed={observed!r}",
        )

    torch = importlib.import_module("torch")
    reference: tuple[
        tuple[int, int, int],
        object,
        object,
        tuple[str, int | None, str | None],
    ] | None = None
    for layer_idx in expected:
        capture = captures[layer_idx]
        tensor = _capture_tensor(capture, layer_idx)
        if capture.layer.conceptual_site != hook_site:
            _fail(
                ExtractionErrorCode.INVALID_HOOK_SITE,
                "capture conceptual site does not match explicit hook_site",
                layer_idx=layer_idx,
            )
        if not isinstance(tensor, torch.Tensor) or tensor.ndim != 3:
            _fail(
                ExtractionErrorCode.INVALID_CAPTURES,
                "capture tensor must have rank-3 [batch, sequence, hidden] shape",
                layer_idx=layer_idx,
            )
        shape = tuple(int(value) for value in tensor.shape)
        if shape[0] != 1 or shape[1] <= 0 or shape[2] <= 0:
            _fail(
                ExtractionErrorCode.INVALID_CAPTURES,
                "capture shape must have batch 1 and positive sequence/hidden axes",
                layer_idx=layer_idx,
            )
        if not torch.is_floating_point(tensor) or tensor.is_complex():
            _fail(
                ExtractionErrorCode.INVALID_CAPTURES,
                "capture tensor must use a real floating dtype",
                layer_idx=layer_idx,
            )
        normalized = capture.output
        normalization_identity = (
            normalized.container_kind,
            normalized.tuple_index,
            normalized.structured_field,
        )
        current = (
            shape,
            tensor.dtype,
            tensor.device,
            normalization_identity,
        )
        if reference is None:
            reference = current
        elif current != reference:
            _fail(
                ExtractionErrorCode.INCONSISTENT_CAPTURE,
                "shape, dtype, device, or normalization identity differs",
                layer_idx=layer_idx,
            )
        if (
            normalized.shape != shape
            or normalized.batch_size != shape[0]
            or normalized.sequence_length != shape[1]
            or normalized.hidden_size != shape[2]
        ):
            _fail(
                ExtractionErrorCode.INCONSISTENT_CAPTURE,
                "normalized capture metadata differs from its tensor",
                layer_idx=layer_idx,
            )
    assert reference is not None
    shape, dtype, device, normalization_identity = reference
    return CaptureSetFacts(
        layer_count=EXPECTED_DECODER_LAYER_COUNT,
        batch_size=shape[0],
        sequence_length=shape[1],
        hidden_size=shape[2],
        source_dtype=str(dtype),
        source_device=str(device),
        normalization_identity=normalization_identity,
    )


def extract_complete_pooled_context(
    *,
    captures: Mapping[int, HookCapture],
    frame_token_map: FrameTokenMap,
    hook_site: str,
) -> tuple[PooledVisualActivation, ...]:
    """Pool every explicit frame at every captured layer in stable order."""

    facts = validate_complete_capture_set(captures, hook_site=hook_site)
    if not isinstance(frame_token_map, FrameTokenMap):
        _fail(
            ExtractionErrorCode.INVALID_FRAME_TOKEN_MAP,
            "frame_token_map must be the frozen project-owned type",
        )
    if frame_token_map.sequence_length != facts.sequence_length:
        _fail(
            ExtractionErrorCode.INVALID_FRAME_TOKEN_MAP,
            "map sequence length must equal every capture sequence length",
        )

    candidates: list[PooledVisualActivation] = []
    for span in frame_token_map.spans:
        try:
            selection = select_visual_token_positions(
                frame_token_map,
                trajectory_id=span.identity.trajectory_id,
                model_frame_idx=span.identity.model_frame_idx,
                hooked_sequence_length=facts.sequence_length,
            )
        except ActivationExtractionError:
            raise
        except VisualTokenSelectionError as exc:
            raise ActivationExtractionError(
                ExtractionErrorCode.INVALID_FRAME_TOKEN_MAP,
                f"visual-token selection failed: {exc}",
            ) from exc
        except (KeyError, IndexError, TypeError, ValueError, RuntimeError) as exc:
            raise ActivationExtractionError(
                ExtractionErrorCode.INVALID_FRAME_TOKEN_MAP,
                "visual-token selection failed unexpectedly",
            ) from exc
        for layer_idx in range(EXPECTED_DECODER_LAYER_COUNT):
            try:
                tensor = _capture_tensor(captures[layer_idx], layer_idx)
                candidates.append(
                    mean_pool_visual_tokens(
                        activation=tensor,
                        selection=selection,
                        layer_idx=layer_idx,
                        hook_site=hook_site,
                    )
                )
            except ActivationExtractionError:
                raise
            except VisualPoolingError as exc:
                raise ActivationExtractionError(
                    ExtractionErrorCode.INVALID_CANDIDATES,
                    f"visual-token pooling failed: {exc}",
                    layer_idx=layer_idx,
                ) from exc
            except (IndexError, TypeError, ValueError, RuntimeError):
                raise ActivationExtractionError(
                    ExtractionErrorCode.INVALID_CANDIDATES,
                    "visual-token pooling failed unexpectedly",
                    layer_idx=layer_idx,
                ) from None

    expected_count = len(frame_token_map.spans) * EXPECTED_DECODER_LAYER_COUNT
    keys = tuple(candidate.key for candidate in candidates)
    expected_keys = tuple(
        (
            span.identity.trajectory_id,
            span.identity.model_frame_idx,
            layer_idx,
            hook_site,
        )
        for span in frame_token_map.spans
        for layer_idx in range(EXPECTED_DECODER_LAYER_COUNT)
    )
    if (
        len(candidates) != expected_count
        or len(keys) != len(set(keys))
        or keys != expected_keys
    ):
        _fail(
            ExtractionErrorCode.INVALID_CANDIDATES,
            "pooled candidates do not have complete unique frame-then-layer order",
        )
    return tuple(candidates)


def _tensor_sha256(tensor: object) -> str:
    torch = importlib.import_module("torch")
    if not isinstance(tensor, torch.Tensor):
        _fail(
            ExtractionErrorCode.INVALID_CANDIDATES,
            "candidate vector must be a tensor",
        )
    numeric = tensor.detach().to(device="cpu").contiguous().numpy()
    return _sha256_bytes(numeric.tobytes(order="C"))


def _pooling_comparison(
    recomputed: object,
    reference: object,
) -> tuple[bool, float, float]:
    torch = importlib.import_module("torch")
    if (
        not isinstance(recomputed, torch.Tensor)
        or not isinstance(reference, torch.Tensor)
        or recomputed.shape != reference.shape
        or recomputed.dtype != torch.float32
        or reference.dtype != torch.float32
        or recomputed.device.type != "cpu"
        or reference.device.type != "cpu"
        or not bool(torch.isfinite(recomputed).all().item())
        or not bool(torch.isfinite(reference).all().item())
    ):
        _fail(
            ExtractionErrorCode.POOLING_AUDIT_FAILED,
            "pooling comparison requires finite matching CPU float32 vectors",
        )
    absolute_difference = (recomputed - reference).abs()
    tolerance = (
        UNPOOLED_REPRODUCTION_ATOL
        + UNPOOLED_REPRODUCTION_RTOL * reference.abs()
    )
    maximum_absolute_difference = float(
        absolute_difference.max().item()
    )
    maximum_tolerance_ratio = float(
        (absolute_difference / tolerance).max().item()
    )
    allclose = bool(
        torch.allclose(
            recomputed,
            reference,
            rtol=UNPOOLED_REPRODUCTION_RTOL,
            atol=UNPOOLED_REPRODUCTION_ATOL,
        )
    )
    if (
        not math.isfinite(maximum_absolute_difference)
        or not math.isfinite(maximum_tolerance_ratio)
    ):
        _fail(
            ExtractionErrorCode.POOLING_AUDIT_FAILED,
            "pooling comparison produced nonfinite audit telemetry",
        )
    return (
        allclose,
        maximum_absolute_difference,
        maximum_tolerance_ratio,
    )


def _candidate_by_layer(
    candidates: tuple[PooledVisualActivation, ...],
    *,
    selection: VisualTokenSelection,
    hook_site: str,
) -> Mapping[int, PooledVisualActivation]:
    if (
        not isinstance(candidates, tuple)
        or not all(
            isinstance(candidate, PooledVisualActivation)
            for candidate in candidates
        )
    ):
        _fail(
            ExtractionErrorCode.INVALID_CANDIDATES,
            "pooled_candidates must be an immutable tuple of "
            "PooledVisualActivation values",
        )
    matching_candidates = tuple(
        candidate
        for candidate in candidates
        if candidate.trajectory_id == selection.trajectory_id
        and candidate.model_frame_idx == selection.model_frame_idx
        and candidate.hook_site == hook_site
    )
    layer_indices = tuple(
        candidate.layer_idx for candidate in matching_candidates
    )
    if (
        len(matching_candidates) != EXPECTED_DECODER_LAYER_COUNT
        or any(
            not isinstance(layer_idx, int) or isinstance(layer_idx, bool)
            for layer_idx in layer_indices
        )
        or tuple(sorted(layer_indices))
        != tuple(range(EXPECTED_DECODER_LAYER_COUNT))
        or len(set(layer_indices)) != EXPECTED_DECODER_LAYER_COUNT
    ):
        _fail(
            ExtractionErrorCode.INVALID_CANDIDATES,
            "pilot frame must have exactly one pooled candidate at every layer",
        )
    complete_keys = tuple(
        candidate.key for candidate in matching_candidates
    )
    if len(set(complete_keys)) != len(complete_keys):
        _fail(
            ExtractionErrorCode.INVALID_CANDIDATES,
            "pilot frame candidate activation keys must be unique",
        )
    matching = {
        candidate.layer_idx: candidate
        for candidate in matching_candidates
    }
    torch = importlib.import_module("torch")
    for layer_idx, candidate in matching.items():
        vector = candidate.vector
        if (
            not isinstance(vector, torch.Tensor)
            or vector.shape != (candidate.hidden_size,)
            or vector.dtype != torch.float32
            or vector.device.type != "cpu"
            or not vector.is_contiguous()
            or vector.requires_grad
            or vector.grad_fn is not None
            or not bool(torch.isfinite(vector).all().item())
            or candidate.selected_visual_token_count
            != VISUAL_TOKENS_PER_FRAME
            or candidate.layer_idx != layer_idx
        ):
            _fail(
                ExtractionErrorCode.INVALID_CANDIDATES,
                "pilot pooled candidate failed identity or ownership checks",
                layer_idx=layer_idx,
            )
    return MappingProxyType(matching)


def _safe_stem(value: str) -> str:
    _require_text(value, "artifact_stem")
    if (
        value in {".", ".."}
        or Path(value).name != value
        or any(separator in value for separator in ("/", "\\"))
    ):
        _fail(
            ExtractionErrorCode.UNSAFE_OUTPUT,
            "artifact_stem must be one safe filename component",
        )
    return value


def _npy_payload(array: object) -> bytes:
    numpy = importlib.import_module("numpy")
    stream = io.BytesIO()
    numpy.lib.format.write_array(stream, array, allow_pickle=False)
    return stream.getvalue()


def _deterministic_npz(arrays: Mapping[str, object]) -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(
        stream,
        mode="w",
        compression=zipfile.ZIP_STORED,
        allowZip64=False,
    ) as archive:
        for name in _UNPOOLED_ARRAY_NAMES:
            information = zipfile.ZipInfo(
                filename=f"{name}.npy",
                date_time=(1980, 1, 1, 0, 0, 0),
            )
            information.compress_type = zipfile.ZIP_STORED
            information.external_attr = 0o600 << 16
            archive.writestr(information, _npy_payload(arrays[name]))
    return stream.getvalue()


def _atomic_write(path: Path, payload: bytes) -> None:
    temporary = _temporary_path(path)
    if _path_present(path) or _path_present(temporary):
        _fail(
            ExtractionErrorCode.OUTPUT_EXISTS,
            f"refusing to overwrite {path}",
        )
    try:
        with temporary.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except ActivationExtractionError:
        raise
    except OSError as exc:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        _fail(
            ExtractionErrorCode.SERIALIZATION_FAILED,
            f"atomic write failed for {path}: {exc}",
        )


def _temporary_path(path: Path) -> Path:
    return path.with_name(f".{path.name}.tmp")


def _path_present(path: Path) -> bool:
    return path.exists() or path.is_symlink()


def _raise_primary_after_output_cleanup(
    primary: BaseException,
    operation_paths: tuple[Path, ...],
) -> None:
    cleanup_failures: list[tuple[Path, OSError]] = []
    for path in operation_paths:
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:
            cleanup_failures.append((path, exc))
    if cleanup_failures:
        failed_paths = ", ".join(
            str(path) for path, _error in cleanup_failures
        )
        cleanup_error = ActivationExtractionError(
            ExtractionErrorCode.SERIALIZATION_FAILED,
            "output cleanup failed after the primary operation failure for "
            f"{failed_paths}",
        )
        cleanup_error.__cause__ = cleanup_failures[0][1]
        raise primary from cleanup_error
    raise primary


def _manifest_payload(
    *,
    identity: UnpooledPilotIdentity,
    facts: CaptureSetFacts,
    selection: VisualTokenSelection,
    artifact_path: Path,
    artifact_size: int,
    artifact_sha256: str,
    token_shape: tuple[int, int, int],
    pooled_shape: tuple[int, int],
    pooling_audit: tuple[Mapping[str, object], ...],
) -> dict[str, object]:
    positions_bytes = json.dumps(
        list(selection.positions),
        separators=(",", ":"),
    ).encode("utf-8")
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_version": LIMITED_UNPOOLED_ARTIFACT_VERSION,
        "classification": LIMITED_UNPOOLED_CLASSIFICATION,
        "status": "PASS",
        "session_id": identity.session_id,
        "scientific_identity": {
            "trajectory_id": identity.trajectory_id,
            "model_frame_idx": identity.model_frame_idx,
            "hook_site": identity.hook_site,
        },
        "capture": {
            "layer_indices": list(range(EXPECTED_DECODER_LAYER_COUNT)),
            "source_sequence_length": facts.sequence_length,
            "source_hidden_size": facts.hidden_size,
            "source_dtype": facts.source_dtype,
            "source_device": facts.source_device,
            "normalization_identity": list(facts.normalization_identity),
            "visual_token_count": VISUAL_TOKENS_PER_FRAME,
            "visual_positions": list(selection.positions),
            "visual_positions_sha256": _sha256_bytes(positions_bytes),
            "token_payload_shape": list(token_shape),
            "token_payload_dtype": "float16",
            "pooled_payload_shape": list(pooled_shape),
            "pooled_payload_dtype": "float32",
            "serialized_device": "cpu",
        },
        "provenance": {
            "frame_token_map_sha256": identity.frame_token_map_sha256,
            "mineocclude_revision": identity.mineocclude_revision,
            "mineworld_revision": identity.mineworld_revision,
            "asset_revision": identity.asset_revision,
            "model_config_sha256": identity.model_config_sha256,
            "main_checkpoint_sha256": identity.main_checkpoint_sha256,
            "vae_config_sha256": identity.vae_config_sha256,
            "vae_checkpoint_sha256": identity.vae_checkpoint_sha256,
            "environment_report_sha256": identity.environment_report_sha256,
            "preprocessing_profile": identity.preprocessing_profile,
            "action_conversion_profile": identity.action_conversion_profile,
            "tokenization_profile": identity.tokenization_profile,
            "accepted_trajectory_package_sha256": (
                identity.accepted_trajectory_package_sha256
            ),
            "input_mp4_sha256": identity.input_mp4_sha256,
        },
        "artifact": {
            "path": artifact_path.name,
            "size_bytes": artifact_size,
            "sha256": artifact_sha256,
            "array_names": list(_UNPOOLED_ARRAY_NAMES),
            "allow_pickle": False,
            "maximum_size_bytes": MAX_UNPOOLED_ARTIFACT_SIZE_BYTES,
        },
        "pooling_audit": {
            "exact_candidate_binding": {
                "comparison": "sha256_byte_equality",
                "stored_array": UNPOOLED_POOLED_ARRAY_NAME,
                "all_layers_match": True,
                "status": "PASS",
            },
            "token_reproduction": {
                "comparison": "torch.allclose",
                "recomputed_from": UNPOOLED_TOKEN_ARRAY_NAME,
                "reference_array": UNPOOLED_POOLED_ARRAY_NAME,
                "recomputed_device": "cpu",
                "recomputed_dtype": "float32",
                "reference_semantics": (
                    "exact stored production pooled vectors; CPU-recomputed "
                    "means may differ from CUDA reductions within tolerance"
                ),
                "rtol": UNPOOLED_REPRODUCTION_RTOL,
                "atol": UNPOOLED_REPRODUCTION_ATOL,
                "maximum_absolute_difference": max(
                    float(record["maximum_absolute_difference"])
                    for record in pooling_audit
                ),
                "maximum_tolerance_ratio": max(
                    float(record["maximum_tolerance_ratio"])
                    for record in pooling_audit
                ),
                "unequal_layer_count": sum(
                    record["allclose"] is not True
                    for record in pooling_audit
                ),
                "status": "PASS",
            },
            "layer_records": [dict(record) for record in pooling_audit],
            "status": "PASS",
        },
        "scope": {
            "one_frame_only": True,
            "all_twenty_layers": True,
            "visual_rows_only": True,
            "action_rows_saved": False,
            "neighbor_rows_saved": False,
            "whole_sequence_saved": False,
            "dataset_wide_unpooled_storage_enabled": False,
        },
    }


def write_limited_unpooled_pilot(
    *,
    captures: Mapping[int, HookCapture],
    frame_token_map: FrameTokenMap,
    selection: VisualTokenSelection,
    pooled_candidates: tuple[PooledVisualActivation, ...],
    identity: UnpooledPilotIdentity,
    output_directory: Path,
    artifact_stem: str = "limited_unpooled_pilot",
    enabled: bool = False,
    maximum_size_bytes: int = MAX_UNPOOLED_ARTIFACT_SIZE_BYTES,
) -> LimitedUnpooledPilot:
    """Write the one-frame pilot only when explicitly enabled."""

    if enabled is not True:
        _fail(
            ExtractionErrorCode.UNPOOLED_DISABLED,
            "limited unpooled retention requires explicit enabled=True",
        )
    if maximum_size_bytes != MAX_UNPOOLED_ARTIFACT_SIZE_BYTES:
        _fail(
            ExtractionErrorCode.SIZE_LIMIT_EXCEEDED,
            "the deterministic 32 MiB storage bound cannot be changed per call",
        )
    if not isinstance(output_directory, Path) or not output_directory.is_dir():
        _fail(
            ExtractionErrorCode.UNSAFE_OUTPUT,
            "output_directory must be an existing ordinary directory",
        )
    if output_directory.is_symlink():
        _fail(
            ExtractionErrorCode.UNSAFE_OUTPUT,
            "output_directory must not be a symbolic link",
        )
    stem = _safe_stem(artifact_stem)
    artifact_path = output_directory / f"{stem}.npz"
    manifest_path = output_directory / f"{stem}.manifest.json"
    artifact_temporary = _temporary_path(artifact_path)
    manifest_temporary = _temporary_path(manifest_path)
    operation_paths = (
        artifact_path,
        manifest_path,
        artifact_temporary,
        manifest_temporary,
    )
    if any(_path_present(path) for path in operation_paths):
        _fail(
            ExtractionErrorCode.OUTPUT_EXISTS,
            "pilot artifact, manifest, or atomic temporary file already exists",
        )

    facts = validate_complete_capture_set(captures, hook_site=identity.hook_site)
    if not isinstance(selection, VisualTokenSelection):
        _fail(
            ExtractionErrorCode.INVALID_FRAME_TOKEN_MAP,
            "selection must be a validated VisualTokenSelection",
        )
    if (
        selection.trajectory_id != identity.trajectory_id
        or selection.model_frame_idx != identity.model_frame_idx
        or selection.sequence_length != facts.sequence_length
    ):
        _fail(
            ExtractionErrorCode.INVALID_IDENTITY,
            "selection and pilot identity differ",
        )
    try:
        authoritative = select_visual_token_positions(
            frame_token_map,
            trajectory_id=identity.trajectory_id,
            model_frame_idx=identity.model_frame_idx,
            hooked_sequence_length=facts.sequence_length,
        )
    except (TypeError, ValueError) as exc:
        _fail(
            ExtractionErrorCode.INVALID_FRAME_TOKEN_MAP,
            f"could not validate pilot selection: {exc}",
        )
    if authoritative != selection:
        _fail(
            ExtractionErrorCode.INVALID_FRAME_TOKEN_MAP,
            "selection differs from the explicit FrameTokenMap visual positions",
        )
    candidate_by_layer = _candidate_by_layer(
        pooled_candidates,
        selection=selection,
        hook_site=identity.hook_site,
    )

    torch = importlib.import_module("torch")
    numpy = importlib.import_module("numpy")
    copied_layers: list[object] = []
    copied_pooled_layers: list[object] = []
    audit: list[Mapping[str, object]] = []
    for layer_idx in range(EXPECTED_DECODER_LAYER_COUNT):
        source = _capture_tensor(captures[layer_idx], layer_idx)
        if source.dtype != torch.float16:
            _fail(
                ExtractionErrorCode.UNSAFE_ARRAY,
                "real pilot token values must preserve source float16 dtype",
                layer_idx=layer_idx,
            )
        position_index = torch.tensor(
            selection.positions,
            dtype=torch.long,
            device=source.device,
        )
        selected = (
            source.detach()
            .index_select(1, position_index)
            .squeeze(0)
            .to(device="cpu")
            .contiguous()
            .clone()
            .detach()
        )
        del position_index
        if (
            selected.shape != (VISUAL_TOKENS_PER_FRAME, facts.hidden_size)
            or selected.dtype != torch.float16
            or selected.device.type != "cpu"
            or not selected.is_contiguous()
            or selected.requires_grad
            or selected.grad_fn is not None
        ):
            _fail(
                ExtractionErrorCode.UNSAFE_ARRAY,
                "selected pilot rows failed shape, dtype, or ownership checks",
                layer_idx=layer_idx,
            )
        candidate = candidate_by_layer[layer_idx].vector
        stored_pooled = (
            candidate.detach()
            .to(device="cpu")
            .contiguous()
            .clone()
            .detach()
        )
        if (
            stored_pooled.shape != (facts.hidden_size,)
            or stored_pooled.dtype != torch.float32
            or stored_pooled.device.type != "cpu"
            or not stored_pooled.is_contiguous()
            or stored_pooled.requires_grad
            or stored_pooled.grad_fn is not None
            or not bool(torch.isfinite(stored_pooled).all().item())
        ):
            _fail(
                ExtractionErrorCode.UNSAFE_ARRAY,
                "stored pooled row failed shape, dtype, or ownership checks",
                layer_idx=layer_idx,
            )
        candidate_sha256 = _tensor_sha256(candidate)
        stored_pooled_sha256 = _tensor_sha256(stored_pooled)
        if stored_pooled_sha256 != candidate_sha256:
            _fail(
                ExtractionErrorCode.POOLING_AUDIT_FAILED,
                "stored pooled row is not byte-identical to extraction A",
                layer_idx=layer_idx,
            )
        mean = selected.to(dtype=torch.float32).mean(dim=0).contiguous()
        (
            equal,
            maximum_absolute_difference,
            maximum_tolerance_ratio,
        ) = _pooling_comparison(mean, stored_pooled)
        if not equal:
            _fail(
                ExtractionErrorCode.POOLING_AUDIT_FAILED,
                "CPU token reproduction exceeded tolerance: "
                f"maximum_absolute_difference={maximum_absolute_difference!r}, "
                f"maximum_tolerance_ratio={maximum_tolerance_ratio!r}, "
                f"rtol={UNPOOLED_REPRODUCTION_RTOL!r}, "
                f"atol={UNPOOLED_REPRODUCTION_ATOL!r}",
                layer_idx=layer_idx,
            )
        audit.append(
            MappingProxyType(
                {
                    "layer_idx": layer_idx,
                    "candidate_sha256": candidate_sha256,
                    "stored_pooled_sha256": stored_pooled_sha256,
                    "cpu_recomputed_mean_sha256": _tensor_sha256(mean),
                    "candidate_binding_sha256_equal": True,
                    "allclose": True,
                    "maximum_absolute_difference": (
                        maximum_absolute_difference
                    ),
                    "maximum_tolerance_ratio": maximum_tolerance_ratio,
                    "rtol": UNPOOLED_REPRODUCTION_RTOL,
                    "atol": UNPOOLED_REPRODUCTION_ATOL,
                }
            )
        )
        copied_layers.append(selected.numpy().copy(order="C"))
        copied_pooled_layers.append(
            stored_pooled.numpy().copy(order="C")
        )
        del mean
        del selected
        del stored_pooled

    token_values = numpy.stack(copied_layers, axis=0)
    copied_layers.clear()
    pooled_means = numpy.stack(copied_pooled_layers, axis=0)
    copied_pooled_layers.clear()
    layer_indices = numpy.arange(
        EXPECTED_DECODER_LAYER_COUNT,
        dtype=numpy.int64,
    )
    visual_positions = numpy.asarray(selection.positions, dtype=numpy.int64)
    expected_shape = (
        EXPECTED_DECODER_LAYER_COUNT,
        VISUAL_TOKENS_PER_FRAME,
        facts.hidden_size,
    )
    expected_pooled_shape = (
        EXPECTED_DECODER_LAYER_COUNT,
        facts.hidden_size,
    )
    if (
        token_values.shape != expected_shape
        or token_values.dtype != numpy.float16
        or pooled_means.shape != expected_pooled_shape
        or pooled_means.dtype != numpy.float32
    ):
        _fail(
            ExtractionErrorCode.UNSAFE_ARRAY,
            "assembled token or pooled payload has an invalid shape or dtype",
        )
    payload = _deterministic_npz(
        {
            UNPOOLED_TOKEN_ARRAY_NAME: token_values,
            UNPOOLED_POOLED_ARRAY_NAME: pooled_means,
            UNPOOLED_LAYER_ARRAY_NAME: layer_indices,
            UNPOOLED_POSITION_ARRAY_NAME: visual_positions,
        }
    )
    if len(payload) > maximum_size_bytes:
        _fail(
            ExtractionErrorCode.SIZE_LIMIT_EXCEEDED,
            f"serialized pilot is {len(payload)} bytes, above {maximum_size_bytes}",
        )
    artifact_sha256 = _sha256_bytes(payload)
    try:
        _atomic_write(artifact_path, payload)
        manifest = _manifest_payload(
            identity=identity,
            facts=facts,
            selection=selection,
            artifact_path=artifact_path,
            artifact_size=len(payload),
            artifact_sha256=artifact_sha256,
            token_shape=expected_shape,
            pooled_shape=expected_pooled_shape,
            pooling_audit=tuple(audit),
        )
        manifest_bytes = (
            json.dumps(
                manifest,
                indent=2,
                sort_keys=True,
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
        _atomic_write(manifest_path, manifest_bytes)
        del token_values
        del pooled_means
        return validate_limited_unpooled_pilot(
            manifest_path,
            expected_hidden_size=facts.hidden_size,
            expected_candidates=candidate_by_layer,
        )
    # This is the transaction boundary: every ordinary failure must roll back
    # both outputs before the original exception is re-raised.
    except Exception as primary:  # noqa: BLE001
        _raise_primary_after_output_cleanup(primary, operation_paths)


def _mapping(value: object, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail(
            ExtractionErrorCode.INVALID_MANIFEST,
            "must be an object",
            field=field,
        )
    return value


def _integer(value: object, field: str, *, positive: bool = False) -> int:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or (positive and value <= 0)
        or (not positive and value < 0)
    ):
        _fail(
            ExtractionErrorCode.INVALID_MANIFEST,
            "must be an integer in the required range",
            field=field,
        )
    return value


def validate_limited_unpooled_pilot(
    manifest_path: Path,
    *,
    expected_hidden_size: int | None = None,
    expected_candidates: Mapping[int, PooledVisualActivation] | None = None,
    reject_extra_tensor_artifacts: bool = True,
) -> LimitedUnpooledPilot:
    """Independently reopen and validate one no-pickle numeric pilot."""

    if (
        not isinstance(manifest_path, Path)
        or not manifest_path.is_file()
        or manifest_path.is_symlink()
    ):
        _fail(
            ExtractionErrorCode.MISSING_ARTIFACT,
            "pilot manifest does not exist",
        )
    manifest = _strict_json(manifest_path)
    if (
        manifest.get("schema_version") != SCHEMA_VERSION
        or manifest.get("artifact_version")
        != LIMITED_UNPOOLED_ARTIFACT_VERSION
        or manifest.get("classification")
        != LIMITED_UNPOOLED_CLASSIFICATION
        or manifest.get("status") != "PASS"
    ):
        _fail(
            ExtractionErrorCode.INVALID_MANIFEST,
            "schema, artifact, classification, or status identity is invalid",
        )
    identity = _mapping(manifest.get("scientific_identity"), "scientific_identity")
    capture = _mapping(manifest.get("capture"), "capture")
    provenance = _mapping(manifest.get("provenance"), "provenance")
    artifact = _mapping(manifest.get("artifact"), "artifact")
    scope = _mapping(manifest.get("scope"), "scope")
    pooling = _mapping(manifest.get("pooling_audit"), "pooling_audit")

    session_id = _require_text(manifest.get("session_id"), "session_id")
    trajectory_id = _require_text(
        identity.get("trajectory_id"),
        "trajectory_id",
    )
    model_frame_idx = _integer(
        identity.get("model_frame_idx"),
        "model_frame_idx",
    )
    hook_site = _require_text(identity.get("hook_site"), "hook_site")
    layer_indices_json = capture.get("layer_indices")
    positions_json = capture.get("visual_positions")
    if layer_indices_json != list(range(EXPECTED_DECODER_LAYER_COUNT)):
        _fail(
            ExtractionErrorCode.ARTIFACT_IDENTITY_MISMATCH,
            "manifest layer indices must be exactly 0 through 19",
        )
    if (
        not isinstance(positions_json, list)
        or len(positions_json) != VISUAL_TOKENS_PER_FRAME
        or any(
            not isinstance(value, int) or isinstance(value, bool)
            for value in positions_json
        )
        or positions_json != sorted(set(positions_json))
    ):
        _fail(
            ExtractionErrorCode.ARTIFACT_IDENTITY_MISMATCH,
            "manifest visual positions must be 336 unique ordered integers",
        )
    expected_pair_start = positions_json[0]
    if (
        expected_pair_start % 347 != 0
        or positions_json
        != list(
            range(
                expected_pair_start,
                expected_pair_start + VISUAL_TOKENS_PER_FRAME,
            )
        )
    ):
        _fail(
            ExtractionErrorCode.ARTIFACT_IDENTITY_MISMATCH,
            "visual positions must be one complete 336-row visual prefix "
            "of a frozen 347-token pair",
        )
    source_sequence_length = _integer(
        capture.get("source_sequence_length"),
        "source_sequence_length",
        positive=True,
    )
    source_hidden_size = _integer(
        capture.get("source_hidden_size"),
        "source_hidden_size",
        positive=True,
    )
    if expected_hidden_size is not None and source_hidden_size != expected_hidden_size:
        _fail(
            ExtractionErrorCode.ARTIFACT_IDENTITY_MISMATCH,
            "hidden size differs from the required runtime value",
        )
    source_dtype = _require_text(capture.get("source_dtype"), "source_dtype")
    source_device = _require_text(capture.get("source_device"), "source_device")
    normalization_identity = capture.get("normalization_identity")
    if (
        not isinstance(normalization_identity, list)
        or len(normalization_identity) != 3
        or not isinstance(normalization_identity[0], str)
        or not normalization_identity[0]
        or (
            normalization_identity[1] is not None
            and type(normalization_identity[1]) is not int
        )
        or (
            normalization_identity[2] is not None
            and not isinstance(normalization_identity[2], str)
        )
    ):
        _fail(
            ExtractionErrorCode.INVALID_MANIFEST,
            "capture normalization identity is invalid",
        )
    expected_shape = (
        EXPECTED_DECODER_LAYER_COUNT,
        VISUAL_TOKENS_PER_FRAME,
        source_hidden_size,
    )
    expected_pooled_shape = (
        EXPECTED_DECODER_LAYER_COUNT,
        source_hidden_size,
    )
    if (
        capture.get("visual_token_count") != VISUAL_TOKENS_PER_FRAME
        or capture.get("token_payload_shape") != list(expected_shape)
        or capture.get("token_payload_dtype") != "float16"
        or capture.get("pooled_payload_shape")
        != list(expected_pooled_shape)
        or capture.get("pooled_payload_dtype") != "float32"
        or capture.get("serialized_device") != "cpu"
    ):
        _fail(
            ExtractionErrorCode.ARTIFACT_IDENTITY_MISMATCH,
            "manifest token/pooled shape, count, dtype, or device is invalid",
        )
    positions_hash = _sha256_bytes(
        json.dumps(
            positions_json,
            separators=(",", ":"),
        ).encode("utf-8")
    )
    if capture.get("visual_positions_sha256") != positions_hash:
        _fail(
            ExtractionErrorCode.ARTIFACT_IDENTITY_MISMATCH,
            "visual-position hash mismatch",
        )
    for field_name in (
        "frame_token_map_sha256",
        "model_config_sha256",
        "main_checkpoint_sha256",
        "vae_config_sha256",
        "vae_checkpoint_sha256",
        "environment_report_sha256",
        "accepted_trajectory_package_sha256",
        "input_mp4_sha256",
    ):
        _require_hex(provenance.get(field_name), field_name, _SHA256_LENGTH)
    for field_name in (
        "mineocclude_revision",
        "mineworld_revision",
        "asset_revision",
    ):
        _require_hex(provenance.get(field_name), field_name, _GIT_SHA_LENGTH)
    for field_name in (
        "preprocessing_profile",
        "action_conversion_profile",
        "tokenization_profile",
    ):
        _require_text(provenance.get(field_name), field_name)

    artifact_name = artifact.get("path")
    if (
        not isinstance(artifact_name, str)
        or Path(artifact_name).name != artifact_name
        or Path(artifact_name).suffix != ".npz"
    ):
        _fail(
            ExtractionErrorCode.UNSAFE_OUTPUT,
            "artifact path must be one relative .npz filename",
        )
    artifact_path = manifest_path.parent / artifact_name
    if not artifact_path.is_file() or artifact_path.is_symlink():
        _fail(
            ExtractionErrorCode.MISSING_ARTIFACT,
            "referenced numeric artifact does not exist",
        )
    artifact_size = artifact_path.stat().st_size
    declared_size = _integer(
        artifact.get("size_bytes"),
        "artifact.size_bytes",
        positive=True,
    )
    declared_sha = _require_hex(
        artifact.get("sha256"),
        "artifact.sha256",
        _SHA256_LENGTH,
    )
    if (
        artifact_size != declared_size
        or artifact_size > MAX_UNPOOLED_ARTIFACT_SIZE_BYTES
        or artifact.get("maximum_size_bytes")
        != MAX_UNPOOLED_ARTIFACT_SIZE_BYTES
        or _sha256_file(artifact_path) != declared_sha
        or artifact.get("array_names") != list(_UNPOOLED_ARRAY_NAMES)
        or artifact.get("allow_pickle") is not False
    ):
        _fail(
            ExtractionErrorCode.ARTIFACT_IDENTITY_MISMATCH,
            "artifact size, hash, array inventory, or safety identity mismatch",
        )
    if reject_extra_tensor_artifacts:
        extra = sorted(
            child.name
            for child in manifest_path.parent.iterdir()
            if child.is_file()
            and child.suffix.lower() in _TENSOR_ARTIFACT_SUFFIXES
            and child.resolve() != artifact_path.resolve()
        )
        if extra:
            _fail(
                ExtractionErrorCode.EXTRA_ARTIFACT,
                f"unapproved tensor artifacts exist: {extra!r}",
            )

    required_scope = {
        "one_frame_only": True,
        "all_twenty_layers": True,
        "visual_rows_only": True,
        "action_rows_saved": False,
        "neighbor_rows_saved": False,
        "whole_sequence_saved": False,
        "dataset_wide_unpooled_storage_enabled": False,
    }
    if any(scope.get(key) is not value for key, value in required_scope.items()):
        _fail(
            ExtractionErrorCode.INVALID_MANIFEST,
            "limited-pilot scope assertions are incomplete",
        )

    numpy = importlib.import_module("numpy")
    try:
        with zipfile.ZipFile(artifact_path, mode="r") as archive:
            members = archive.infolist()
            expected_members = [
                f"{name}.npy" for name in _UNPOOLED_ARRAY_NAMES
            ]
            member_names = [member.filename for member in members]
            if (
                member_names != expected_members
                or len(member_names) != len(set(member_names))
                or any(
                    Path(name).name != name
                    or name.startswith(("/", "\\"))
                    for name in member_names
                )
            ):
                _fail(
                    ExtractionErrorCode.UNSAFE_ARRAY,
                    "NPZ members must be the exact unique safe array inventory",
                )
        with numpy.load(artifact_path, allow_pickle=False) as arrays:
            if set(arrays.files) != set(_UNPOOLED_ARRAY_NAMES):
                _fail(
                    ExtractionErrorCode.UNSAFE_ARRAY,
                    "numeric artifact has an unexpected array inventory",
                )
            token_values = arrays[UNPOOLED_TOKEN_ARRAY_NAME]
            pooled_means = arrays[UNPOOLED_POOLED_ARRAY_NAME]
            layer_indices = arrays[UNPOOLED_LAYER_ARRAY_NAME]
            visual_positions = arrays[UNPOOLED_POSITION_ARRAY_NAME]
            if any(
                getattr(array.dtype, "hasobject", False)
                for array in (
                    token_values,
                    pooled_means,
                    layer_indices,
                    visual_positions,
                )
            ):
                _fail(
                    ExtractionErrorCode.UNSAFE_ARRAY,
                    "object arrays are forbidden",
                )
            token_values = token_values.copy(order="C")
            pooled_means = pooled_means.copy(order="C")
            layer_indices = layer_indices.copy(order="C")
            visual_positions = visual_positions.copy(order="C")
    except ActivationExtractionError:
        raise
    except Exception as exc:  # noqa: BLE001
        _fail(
            ExtractionErrorCode.UNSAFE_ARRAY,
            f"safe allow_pickle=False read failed: {type(exc).__name__}: {exc}",
        )
    if (
        token_values.shape != expected_shape
        or token_values.dtype != numpy.float16
        or pooled_means.shape != expected_pooled_shape
        or pooled_means.dtype != numpy.float32
    ):
        _fail(
            ExtractionErrorCode.UNSAFE_ARRAY,
            "token_values or pooled_means has an invalid shape or dtype",
        )
    expected_layers_array = numpy.arange(
        EXPECTED_DECODER_LAYER_COUNT,
        dtype=numpy.int64,
    )
    expected_positions_array = numpy.asarray(positions_json, dtype=numpy.int64)
    if (
        layer_indices.dtype != numpy.int64
        or not numpy.array_equal(layer_indices, expected_layers_array)
        or visual_positions.dtype != numpy.int64
        or not numpy.array_equal(visual_positions, expected_positions_array)
        or any(position < 0 or position >= source_sequence_length for position in positions_json)
    ):
        _fail(
            ExtractionErrorCode.UNSAFE_ARRAY,
            "layer or visual-position array identity mismatch",
        )

    binding = _mapping(
        pooling.get("exact_candidate_binding"),
        "pooling_audit.exact_candidate_binding",
    )
    reproduction = _mapping(
        pooling.get("token_reproduction"),
        "pooling_audit.token_reproduction",
    )
    records = pooling.get("layer_records")
    if (
        binding.get("comparison") != "sha256_byte_equality"
        or binding.get("stored_array") != UNPOOLED_POOLED_ARRAY_NAME
        or binding.get("all_layers_match") is not True
        or binding.get("status") != "PASS"
        or reproduction.get("comparison") != "torch.allclose"
        or reproduction.get("recomputed_from") != UNPOOLED_TOKEN_ARRAY_NAME
        or reproduction.get("reference_array")
        != UNPOOLED_POOLED_ARRAY_NAME
        or reproduction.get("recomputed_device") != "cpu"
        or reproduction.get("recomputed_dtype") != "float32"
        or reproduction.get("reference_semantics")
        != (
            "exact stored production pooled vectors; CPU-recomputed means "
            "may differ from CUDA reductions within tolerance"
        )
        or reproduction.get("rtol") != UNPOOLED_REPRODUCTION_RTOL
        or reproduction.get("atol") != UNPOOLED_REPRODUCTION_ATOL
        or reproduction.get("status") != "PASS"
        or pooling.get("status") != "PASS"
        or not isinstance(records, list)
        or len(records) != EXPECTED_DECODER_LAYER_COUNT
    ):
        _fail(
            ExtractionErrorCode.POOLING_AUDIT_FAILED,
            "pooling-audit header is invalid",
    )
    torch = importlib.import_module("torch")
    validated_audit: list[Mapping[str, object]] = []
    maximum_absolute_difference = 0.0
    maximum_tolerance_ratio = 0.0
    unequal_layer_count = 0
    for layer_idx, record_value in enumerate(records):
        record = _mapping(record_value, f"pooling_audit.layer_records[{layer_idx}]")
        mean = (
            torch.from_numpy(token_values[layer_idx].copy())
            .to(dtype=torch.float32)
            .mean(dim=0)
            .contiguous()
        )
        stored_pooled = (
            torch.from_numpy(pooled_means[layer_idx].copy())
            .to(dtype=torch.float32)
            .contiguous()
        )
        mean_sha = _tensor_sha256(mean)
        stored_pooled_sha = _tensor_sha256(stored_pooled)
        candidate_sha = _require_hex(
            record.get("candidate_sha256"),
            "candidate_sha256",
            _SHA256_LENGTH,
        )
        (
            allclose,
            layer_maximum_absolute_difference,
            layer_maximum_tolerance_ratio,
        ) = _pooling_comparison(mean, stored_pooled)
        if (
            record.get("layer_idx") != layer_idx
            or record.get("stored_pooled_sha256") != stored_pooled_sha
            or stored_pooled_sha != candidate_sha
            or record.get("cpu_recomputed_mean_sha256") != mean_sha
            or record.get("candidate_binding_sha256_equal") is not True
            or record.get("allclose") is not allclose
            or record.get("maximum_absolute_difference")
            != layer_maximum_absolute_difference
            or record.get("maximum_tolerance_ratio")
            != layer_maximum_tolerance_ratio
            or record.get("rtol") != UNPOOLED_REPRODUCTION_RTOL
            or record.get("atol") != UNPOOLED_REPRODUCTION_ATOL
        ):
            _fail(
                ExtractionErrorCode.POOLING_AUDIT_FAILED,
                "stored candidate binding or independently recomputed token "
                "audit differs from the manifest",
                layer_idx=layer_idx,
            )
        if expected_candidates is not None:
            candidate = expected_candidates.get(layer_idx)
            if (
                candidate is None
                or _tensor_sha256(candidate.vector) != stored_pooled_sha
            ):
                _fail(
                    ExtractionErrorCode.POOLING_AUDIT_FAILED,
                    "stored pooled row is not byte-identical to the supplied "
                    "extraction-A candidate",
                    layer_idx=layer_idx,
                )
        if not allclose:
            _fail(
                ExtractionErrorCode.POOLING_AUDIT_FAILED,
                "CPU token reproduction exceeded tolerance: "
                f"maximum_absolute_difference="
                f"{layer_maximum_absolute_difference!r}, "
                f"maximum_tolerance_ratio={layer_maximum_tolerance_ratio!r}, "
                f"rtol={UNPOOLED_REPRODUCTION_RTOL!r}, "
                f"atol={UNPOOLED_REPRODUCTION_ATOL!r}",
                layer_idx=layer_idx,
            )
        maximum_absolute_difference = max(
            maximum_absolute_difference,
            layer_maximum_absolute_difference,
        )
        maximum_tolerance_ratio = max(
            maximum_tolerance_ratio,
            layer_maximum_tolerance_ratio,
        )
        unequal_layer_count += int(not allclose)
        validated_audit.append(
            MappingProxyType(
                {
                    "layer_idx": layer_idx,
                    "candidate_sha256": candidate_sha,
                    "stored_pooled_sha256": stored_pooled_sha,
                    "cpu_recomputed_mean_sha256": mean_sha,
                    "candidate_binding_sha256_equal": True,
                    "allclose": allclose,
                    "maximum_absolute_difference": (
                        layer_maximum_absolute_difference
                    ),
                    "maximum_tolerance_ratio": (
                        layer_maximum_tolerance_ratio
                    ),
                    "rtol": UNPOOLED_REPRODUCTION_RTOL,
                    "atol": UNPOOLED_REPRODUCTION_ATOL,
                }
            )
        )
        del mean
        del stored_pooled

    if (
        reproduction.get("maximum_absolute_difference")
        != maximum_absolute_difference
        or reproduction.get("maximum_tolerance_ratio")
        != maximum_tolerance_ratio
        or reproduction.get("unequal_layer_count") != unequal_layer_count
        or unequal_layer_count != 0
    ):
        _fail(
            ExtractionErrorCode.POOLING_AUDIT_FAILED,
            "aggregate token-reproduction audit differs from independently "
            "recomputed values",
        )

    manifest_size = manifest_path.stat().st_size
    return LimitedUnpooledPilot(
        session_id=session_id,
        trajectory_id=trajectory_id,
        model_frame_idx=model_frame_idx,
        hook_site=hook_site,
        source_sequence_length=source_sequence_length,
        source_hidden_size=source_hidden_size,
        source_dtype=source_dtype,
        source_device=source_device,
        manifest_path=manifest_path,
        artifact_path=artifact_path,
        manifest_size_bytes=manifest_size,
        artifact_size_bytes=artifact_size,
        manifest_sha256=_sha256_file(manifest_path),
        artifact_sha256=declared_sha,
        token_shape=expected_shape,
        token_dtype="float16",
        pooled_shape=expected_pooled_shape,
        pooled_dtype="float32",
        layer_indices=tuple(range(EXPECTED_DECODER_LAYER_COUNT)),
        visual_positions=tuple(positions_json),
        pooling_maximum_absolute_difference=maximum_absolute_difference,
        pooling_maximum_tolerance_ratio=maximum_tolerance_ratio,
        pooling_unequal_layer_count=unequal_layer_count,
        pooling_audit=tuple(validated_audit),
    )


# ---------------------------------------------------------------------------
# Phase 5 pooled activation store
# ---------------------------------------------------------------------------

ACTIVATION_STORE_FORMAT_VERSION = "person-a-activation-store-v1"
ACTIVATION_INDEX_FORMAT_VERSION = "person-a-activation-index-v1"
ACTIVATION_CHUNK_TIMESTAMP_SEMANTICS = (
    "index_record_time_not_chunk_byte_creation"
)
ACTIVATION_RUN_BINDING_FORMAT_VERSION = "person-a-activation-run-binding-v1"
ACTIVATION_ELIGIBILITY_FORMAT_VERSION = (
    "person-a-activation-eligibility-proof-v1"
)
SUPPORTED_ACTIVATION_STORE_DTYPES = frozenset(
    {"float16", "float32", "float64"}
)
ACTIVATION_OPERATIONAL_STATUSES = frozenset(
    {"pending", "writing", "completed", "failed"}
)
ACTIVATION_ANALYSIS_STATUSES = frozenset(
    {"accepted", "excluded", "superseded"}
)
MAX_ACTIVATION_INDEX_JSON_BYTES = 128 * 1024 * 1024
MAX_ACTIVATION_INDEX_ROWS = 2_000_000
MAX_ACTIVATION_CHUNKS_PER_SNAPSHOT = 100_000
MAX_ACTIVATION_CHUNK_BYTES = 512 * 1024 * 1024
MAX_ACTIVATION_ROWS_PER_CHUNK = 16_384
MAX_ACTIVATION_HIDDEN_WIDTH = 16_384
MAX_ACTIVATION_SNAPSHOT_REFERENCED_BYTES = 2 * 1024**4
MAX_ACTIVATION_RUN_BINDING_BYTES = 128 * 1024
MAX_ACTIVATION_READ_ROWS = 65_536
MAX_ACTIVATION_READ_RESULT_BYTES = 512 * 1024 * 1024
MAX_ACTIVATION_READ_CHUNKS = 256
_MAX_SAFE_ACTIVATION_READ_INTEGER = (1 << 63) - 1
_ACTIVATION_DTYPE_ITEM_SIZES = {
    "float16": 2,
    "float32": 4,
    "float64": 8,
}
ACTIVATION_ELIGIBILITY_METADATA_FIELDS = (
    "accepted_manifest_hash",
    "action_idx",
    "code_sha",
    "config_hash",
    "duration",
    "episode_id",
    "exclusion_reason",
    "layout_id",
    "model_frame_idx",
    "model_hash",
    "preprocess_hash",
    "q",
    "regime",
    "render_frame_idx",
    "run_id",
    "schema_version",
    "seed",
    "server_tick",
    "status",
    "superseded_by",
    "tau",
    "trajectory_id",
    "v",
    "visibility",
)


class ActivationStoreErrorCode(str, Enum):
    """Stable fail-closed errors for the pooled activation store."""

    INVALID_IDENTITY = "invalid_identity"
    INVALID_ROW = "invalid_row"
    INVALID_STATE = "invalid_state"
    UNSAFE_PATH = "unsafe_path"
    UNSUPPORTED_DTYPE = "unsupported_dtype"
    INVALID_CHUNK = "invalid_chunk"
    INVALID_INDEX = "invalid_index"
    OUTPUT_EXISTS = "output_exists"
    IDENTITY_CONFLICT = "identity_conflict"
    CHECKSUM_MISMATCH = "checksum_mismatch"
    BYTE_SIZE_MISMATCH = "byte_size_mismatch"
    PUBLICATION_FAILED = "publication_failed"
    RUN_BINDING_CONFLICT = "run_binding_conflict"
    ELIGIBILITY_CONFLICT = "eligibility_conflict"
    LIMIT_EXCEEDED = "limit_exceeded"
    FORCED_INTERRUPTION = "forced_interruption"
    RESUME_CONFLICT = "resume_conflict"
    READ_FAILED = "read_failed"
    AUDIT_FAILED = "audit_failed"


class ActivationStoreError(ValueError):
    """Actionable project-owned pooled-store failure."""

    def __init__(
        self,
        code: ActivationStoreErrorCode,
        message: str,
        *,
        field: str | None = None,
        path: Path | str | None = None,
    ) -> None:
        self.code = code
        self.field = field
        self.path = None if path is None else str(path)
        prefix = code.value
        if field is not None:
            prefix += f"[field={field}]"
        if path is not None:
            prefix += f"[path={path}]"
        super().__init__(f"{prefix}: {message}")


class ActivationPublicationFaultPoint(str, Enum):
    """Deterministic test-only interruption boundaries."""

    DURING_RUN_BINDING_PUBLICATION = "during_run_binding_publication"
    BEFORE_TEMPORARY_CHUNK = "before_temporary_chunk"
    DURING_TEMPORARY_CHUNK = "during_temporary_chunk"
    AFTER_TEMPORARY_CHUNK_VALIDATION = "after_temporary_chunk_validation"
    AFTER_FINAL_CHUNK_PUBLICATION = "after_final_chunk_publication"
    AFTER_INDEX_CONSTRUCTION = "after_index_construction"
    DURING_INDEX_PUBLICATION = "during_index_publication"
    AFTER_INDEX_PUBLICATION = "after_index_publication"


def _store_error(
    code: ActivationStoreErrorCode,
    message: str,
    *,
    field: str | None = None,
    path: Path | str | None = None,
) -> None:
    raise ActivationStoreError(code, message, field=field, path=path)


def _phase5_require_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _store_error(
            ActivationStoreErrorCode.INVALID_IDENTITY,
            "must be a non-empty string",
            field=field,
        )
    return value


def _phase5_require_hex(
    value: object,
    field: str,
    length: int,
) -> str:
    if (
        not isinstance(value, str)
        or len(value) != length
        or any(character not in "0123456789abcdef" for character in value)
    ):
        _store_error(
            ActivationStoreErrorCode.INVALID_IDENTITY,
            f"must be a lowercase {length}-character hexadecimal value",
            field=field,
        )
    return value


def _phase5_require_integer(
    value: object,
    field: str,
    *,
    minimum: int = 0,
) -> int:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or value < minimum
    ):
        _store_error(
            ActivationStoreErrorCode.INVALID_IDENTITY,
            f"must be an integer greater than or equal to {minimum}",
            field=field,
        )
    return value


def _phase5_require_timestamp(value: object, field: str) -> str:
    text = _phase5_require_text(value, field)
    if not text.endswith("Z") or "T" not in text:
        _store_error(
            ActivationStoreErrorCode.INVALID_IDENTITY,
            "must be an explicit UTC timestamp ending in 'Z'",
            field=field,
        )
    try:
        parsed = datetime.fromisoformat(text[:-1] + "+00:00")
    except ValueError:
        _store_error(
            ActivationStoreErrorCode.INVALID_IDENTITY,
            "must be a valid ISO-8601 UTC timestamp",
            field=field,
        )
    if parsed.utcoffset() is None or parsed.utcoffset().total_seconds() != 0:
        _store_error(
            ActivationStoreErrorCode.INVALID_IDENTITY,
            "must identify UTC",
            field=field,
        )
    return text


def _canonical_json_bytes(value: object) -> bytes:
    try:
        return (
            json.dumps(
                value,
                allow_nan=False,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        _store_error(
            ActivationStoreErrorCode.INVALID_INDEX,
            f"value is not canonical-JSON serializable: {error}",
        )


def _canonical_digest(value: object) -> str:
    return _sha256_bytes(_canonical_json_bytes(value))


def _freeze_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType(
            {str(key): _freeze_json(item) for key, item in value.items()}
        )
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_json(item) for item in value)
    return value


def _thaw_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_json(item) for item in value]
    return value


def _safe_store_relative_path(value: object, field: str) -> str:
    text = _phase5_require_text(value, field)
    if "\\" in text or ":" in text:
        _store_error(
            ActivationStoreErrorCode.UNSAFE_PATH,
            "must use normalized relative POSIX separators without drive aliases",
            field=field,
        )
    pure = PurePosixPath(text)
    if (
        pure.is_absolute()
        or text != pure.as_posix()
        or any(part in {"", ".", ".."} for part in pure.parts)
    ):
        _store_error(
            ActivationStoreErrorCode.UNSAFE_PATH,
            "must be a normalized relative path without traversal",
            field=field,
        )
    return text


def _resolve_store_path(store_root: Path | str, relative_path: str) -> Path:
    safe = _safe_store_relative_path(relative_path, "relative_path")
    lexical_root = Path(store_root).absolute()
    if lexical_root.is_symlink():
        _store_error(
            ActivationStoreErrorCode.UNSAFE_PATH,
            "store_root must not be a symbolic link",
            path=lexical_root,
        )
    lexical_destination = lexical_root
    for part in PurePosixPath(safe).parts:
        lexical_destination /= part
        if lexical_destination.is_symlink():
            _store_error(
                ActivationStoreErrorCode.UNSAFE_PATH,
                "store path must not contain symbolic-link components",
                path=lexical_destination,
            )
    root = lexical_root.resolve()
    destination = lexical_destination.resolve(strict=False)
    try:
        destination.relative_to(root)
    except ValueError:
        _store_error(
            ActivationStoreErrorCode.UNSAFE_PATH,
            "resolved path escapes the selected store root",
            path=destination,
        )
    return lexical_destination


def _require_ordinary_store_file(
    store_root: Path | str,
    relative_path: str,
) -> Path:
    path = _resolve_store_path(store_root, relative_path)
    if path.is_symlink() or not path.is_file():
        _store_error(
            ActivationStoreErrorCode.UNSAFE_PATH,
            "completed store object must be an ordinary non-symlink file",
            path=path,
        )
    return path


def _validate_store_dtype(dtype: object) -> str:
    text = _phase5_require_text(dtype, "dtype")
    if text == "bfloat16":
        _store_error(
            ActivationStoreErrorCode.UNSUPPORTED_DTYPE,
            "NumPy 1.26.4 has no native safe bfloat16 storage path",
            field="dtype",
        )
    if text not in SUPPORTED_ACTIVATION_STORE_DTYPES:
        _store_error(
            ActivationStoreErrorCode.UNSUPPORTED_DTYPE,
            "supported pooled-store dtypes are float16, float32, and float64",
            field="dtype",
        )
    return text


@dataclass(frozen=True)
class ActivationStoreIdentity:
    """Complete identity of one immutable pooled activation run."""

    schema_version: str
    run_id: str
    checkpoint_hash: str
    model_hash: str
    config_hash: str
    preprocess_hash: str
    accepted_manifest_hash: str
    code_sha: str
    hook_site: str
    requested_layers: tuple[int, ...]
    dtype: str
    hidden_width: int

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            _store_error(
                ActivationStoreErrorCode.INVALID_IDENTITY,
                f"schema_version must equal {SCHEMA_VERSION!r}",
                field="schema_version",
            )
        _phase5_require_text(self.run_id, "run_id")
        for field in (
            "checkpoint_hash",
            "model_hash",
            "config_hash",
            "preprocess_hash",
            "accepted_manifest_hash",
        ):
            _phase5_require_hex(getattr(self, field), field, 64)
        _phase5_require_hex(self.code_sha, "code_sha", 40)
        _phase5_require_text(self.hook_site, "hook_site")
        if (
            not isinstance(self.requested_layers, tuple)
            or not self.requested_layers
            or any(
                not isinstance(layer, int)
                or isinstance(layer, bool)
                or layer < 0
                for layer in self.requested_layers
            )
            or tuple(sorted(set(self.requested_layers)))
            != self.requested_layers
        ):
            _store_error(
                ActivationStoreErrorCode.INVALID_IDENTITY,
                "requested_layers must be a non-empty sorted unique tuple",
                field="requested_layers",
            )
        _validate_store_dtype(self.dtype)
        _phase5_require_integer(
            self.hidden_width,
            "hidden_width",
            minimum=1,
        )
        if self.hidden_width > MAX_ACTIVATION_HIDDEN_WIDTH:
            _store_error(
                ActivationStoreErrorCode.LIMIT_EXCEEDED,
                f"hidden_width exceeds reviewed limit "
                f"{MAX_ACTIVATION_HIDDEN_WIDTH}",
                field="hidden_width",
            )

    def to_document(self) -> dict[str, Any]:
        return {
            "accepted_manifest_hash": self.accepted_manifest_hash,
            "checkpoint_hash": self.checkpoint_hash,
            "code_sha": self.code_sha,
            "config_hash": self.config_hash,
            "dtype": self.dtype,
            "hidden_width": self.hidden_width,
            "hook_site": self.hook_site,
            "model_hash": self.model_hash,
            "preprocess_hash": self.preprocess_hash,
            "requested_layers": list(self.requested_layers),
            "run_id": self.run_id,
            "schema_version": self.schema_version,
        }

    @property
    def digest(self) -> str:
        return _canonical_digest(self.to_document())


@dataclass(frozen=True, order=True)
class ActivationRowKey:
    """Scientific pooled-vector identity, including the producing run."""

    trajectory_id: str
    model_frame_idx: int
    layer_idx: int
    hook_site: str
    producing_run_id: str

    def __post_init__(self) -> None:
        _phase5_require_text(self.trajectory_id, "trajectory_id")
        _phase5_require_integer(self.model_frame_idx, "model_frame_idx")
        _phase5_require_integer(self.layer_idx, "layer_idx")
        _phase5_require_text(self.hook_site, "hook_site")
        _phase5_require_text(self.producing_run_id, "producing_run_id")

    def to_document(self) -> dict[str, Any]:
        return {
            "hook_site": self.hook_site,
            "layer_idx": self.layer_idx,
            "model_frame_idx": self.model_frame_idx,
            "producing_run_id": self.producing_run_id,
            "trajectory_id": self.trajectory_id,
        }

    @property
    def digest(self) -> str:
        return _canonical_digest(self.to_document())

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> ActivationRowKey:
        return cls(
            trajectory_id=row.get("trajectory_id"),
            model_frame_idx=row.get("model_frame_idx"),
            layer_idx=row.get("layer_idx"),
            hook_site=row.get("hook_site"),
            producing_run_id=row.get("run_id"),
        )


@dataclass(frozen=True)
class ActivationEligibilityProof:
    """Immutable eligible-row universe derived from the accepted manifest."""

    store_identity_digest: str
    accepted_manifest_hash: str
    source_manifest_row_count: int
    source_rows_digest: str
    eligible_rows: tuple[Mapping[str, Any], ...]

    def __post_init__(self) -> None:
        _phase5_require_hex(
            self.store_identity_digest,
            "store_identity_digest",
            64,
        )
        _phase5_require_hex(
            self.accepted_manifest_hash,
            "accepted_manifest_hash",
            64,
        )
        _phase5_require_integer(
            self.source_manifest_row_count,
            "source_manifest_row_count",
            minimum=1,
        )
        _phase5_require_hex(self.source_rows_digest, "source_rows_digest", 64)
        if not isinstance(self.eligible_rows, tuple) or not self.eligible_rows:
            _store_error(
                ActivationStoreErrorCode.ELIGIBILITY_CONFLICT,
                "eligible_rows must be a non-empty immutable tuple",
                field="eligible_rows",
            )
        frozen_rows: list[Mapping[str, Any]] = []
        keys: list[ActivationRowKey] = []
        required = {"metadata", "row_key"}
        for index, value in enumerate(self.eligible_rows):
            if not isinstance(value, Mapping) or set(value) != required:
                _store_error(
                    ActivationStoreErrorCode.ELIGIBILITY_CONFLICT,
                    "eligible row must contain exactly metadata and row_key",
                    field=f"eligible_rows[{index}]",
                )
            key = _row_key_from_document(value.get("row_key"))
            metadata = value.get("metadata")
            if (
                not isinstance(metadata, Mapping)
                or set(metadata) != set(ACTIVATION_ELIGIBILITY_METADATA_FIELDS)
            ):
                _store_error(
                    ActivationStoreErrorCode.ELIGIBILITY_CONFLICT,
                    "eligible metadata fields do not match the reviewed set",
                    field=f"eligible_rows[{index}].metadata",
                )
            if (
                metadata.get("trajectory_id") != key.trajectory_id
                or metadata.get("model_frame_idx") != key.model_frame_idx
                or metadata.get("run_id") != key.producing_run_id
                or metadata.get("accepted_manifest_hash")
                != self.accepted_manifest_hash
            ):
                _store_error(
                    ActivationStoreErrorCode.ELIGIBILITY_CONFLICT,
                    "eligible metadata disagrees with its scientific identity",
                    field=f"eligible_rows[{index}]",
                )
            keys.append(key)
            frozen_rows.append(_freeze_json(dict(value)))
        if tuple(sorted(keys)) != tuple(keys) or len(set(keys)) != len(keys):
            _store_error(
                ActivationStoreErrorCode.ELIGIBILITY_CONFLICT,
                "eligible activation keys must be sorted and unique",
                field="eligible_rows",
            )
        object.__setattr__(self, "eligible_rows", tuple(frozen_rows))

    def to_document(self) -> dict[str, Any]:
        return {
            "accepted_manifest_hash": self.accepted_manifest_hash,
            "eligible_rows": [_thaw_json(row) for row in self.eligible_rows],
            "format_version": ACTIVATION_ELIGIBILITY_FORMAT_VERSION,
            "source_manifest_row_count": self.source_manifest_row_count,
            "source_rows_digest": self.source_rows_digest,
            "store_identity_digest": self.store_identity_digest,
        }

    @property
    def digest(self) -> str:
        return _canonical_digest(self.to_document())


def build_activation_eligibility_proof(
    *,
    store_identity: ActivationStoreIdentity,
    accepted_manifest_rows: Sequence[Mapping[str, Any]],
) -> ActivationEligibilityProof:
    """Derive the exact post-first-visible row universe from its authority."""

    if not isinstance(store_identity, ActivationStoreIdentity):
        _store_error(
            ActivationStoreErrorCode.INVALID_IDENTITY,
            "store_identity must be ActivationStoreIdentity",
        )
    if (
        isinstance(accepted_manifest_rows, (str, bytes))
        or not isinstance(accepted_manifest_rows, Sequence)
        or not accepted_manifest_rows
    ):
        _store_error(
            ActivationStoreErrorCode.ELIGIBILITY_CONFLICT,
            "accepted_manifest_rows must be a non-empty sequence",
        )
    source_rows: list[dict[str, Any]] = []
    for index, value in enumerate(accepted_manifest_rows):
        if not isinstance(value, Mapping):
            _store_error(
                ActivationStoreErrorCode.ELIGIBILITY_CONFLICT,
                "every accepted-manifest row must be a mapping",
                field=f"accepted_manifest_rows[{index}]",
            )
        row = dict(value)
        try:
            validate_identity(row)
        except (IdentityValidationError, TypeError) as error:
            _store_error(
                ActivationStoreErrorCode.ELIGIBILITY_CONFLICT,
                f"accepted-manifest identity validation failed: {error}",
                field=f"accepted_manifest_rows[{index}]",
            )
        if row.get("accepted_manifest_hash") != (
            store_identity.accepted_manifest_hash
        ):
            _store_error(
                ActivationStoreErrorCode.ELIGIBILITY_CONFLICT,
                "accepted-manifest row hash does not match store identity",
                field=f"accepted_manifest_rows[{index}].accepted_manifest_hash",
            )
        missing_metadata = sorted(
            set(ACTIVATION_ELIGIBILITY_METADATA_FIELDS) - set(row)
        )
        if missing_metadata:
            _store_error(
                ActivationStoreErrorCode.ELIGIBILITY_CONFLICT,
                "accepted-manifest row lacks authoritative eligibility "
                f"metadata: {missing_metadata!r}",
                field=f"accepted_manifest_rows[{index}]",
            )
        source_rows.append(row)

    from mineocclude.analysis.filters import (
        FilterRejectionCode,
        apply_ordered_filters,
    )

    result = apply_ordered_filters(
        source_rows,
        accepted_manifest_hash=store_identity.accepted_manifest_hash,
    )
    invalid_rejections = [
        rejection
        for rejection in result.rejections
        if rejection.code != FilterRejectionCode.PRE_FIRST_SEEN
    ]
    if invalid_rejections:
        first = invalid_rejections[0]
        _store_error(
            ActivationStoreErrorCode.ELIGIBILITY_CONFLICT,
            "accepted-manifest eligibility rejected row "
            f"{first.row_index}: {first.code.value}: {first.message}",
            field=f"accepted_manifest_rows[{first.row_index}]",
        )

    eligible: list[dict[str, Any]] = []
    for source in result.accepted_rows:
        for layer_idx in store_identity.requested_layers:
            key = ActivationRowKey(
                trajectory_id=str(source["trajectory_id"]),
                model_frame_idx=int(source["model_frame_idx"]),
                layer_idx=layer_idx,
                hook_site=store_identity.hook_site,
                producing_run_id=store_identity.run_id,
            )
            metadata = {
                field: _thaw_json(source[field])
                for field in ACTIVATION_ELIGIBILITY_METADATA_FIELDS
            }
            eligible.append(
                {
                    "metadata": metadata,
                    "row_key": key.to_document(),
                }
            )
    eligible.sort(key=lambda value: _row_key_from_document(value["row_key"]))
    return ActivationEligibilityProof(
        store_identity_digest=store_identity.digest,
        accepted_manifest_hash=store_identity.accepted_manifest_hash,
        source_manifest_row_count=len(source_rows),
        source_rows_digest=_canonical_digest(source_rows),
        eligible_rows=tuple(eligible),
    )


@dataclass(frozen=True)
class ActivationChunkIdentity:
    """Deterministic identity of one homogeneous immutable chunk."""

    store_identity: ActivationStoreIdentity
    layer_idx: int
    first_row_key: ActivationRowKey
    last_row_key: ActivationRowKey
    row_count: int
    dtype: str
    hidden_width: int

    def __post_init__(self) -> None:
        if not isinstance(self.store_identity, ActivationStoreIdentity):
            _store_error(
                ActivationStoreErrorCode.INVALID_IDENTITY,
                "store_identity must be ActivationStoreIdentity",
                field="store_identity",
            )
        _phase5_require_integer(self.layer_idx, "layer_idx")
        _phase5_require_integer(self.row_count, "row_count", minimum=1)
        _validate_store_dtype(self.dtype)
        _phase5_require_integer(self.hidden_width, "hidden_width", minimum=1)
        if (
            not isinstance(self.first_row_key, ActivationRowKey)
            or not isinstance(self.last_row_key, ActivationRowKey)
            or self.layer_idx not in self.store_identity.requested_layers
            or self.dtype != self.store_identity.dtype
            or self.hidden_width != self.store_identity.hidden_width
            or self.first_row_key > self.last_row_key
        ):
            _store_error(
                ActivationStoreErrorCode.INVALID_IDENTITY,
                "chunk identity does not agree with its store identity",
            )
        for field, key in (
            ("first_row_key", self.first_row_key),
            ("last_row_key", self.last_row_key),
        ):
            if (
                key.layer_idx != self.layer_idx
                or key.hook_site != self.store_identity.hook_site
                or key.producing_run_id != self.store_identity.run_id
                or key.layer_idx not in self.store_identity.requested_layers
            ):
                _store_error(
                    ActivationStoreErrorCode.INVALID_IDENTITY,
                    "bounded row key does not agree with chunk/store identity",
                    field=field,
                )

    def to_document(self) -> dict[str, Any]:
        return {
            "dtype": self.dtype,
            "first_row_key": self.first_row_key.to_document(),
            "hidden_width": self.hidden_width,
            "last_row_key": self.last_row_key.to_document(),
            "layer_idx": self.layer_idx,
            "row_count": self.row_count,
            "store_identity": self.store_identity.to_document(),
        }

    @property
    def digest(self) -> str:
        return _canonical_digest(self.to_document())


@dataclass(frozen=True)
class ActivationChunkRecord:
    """Persisted immutable chunk descriptor."""

    chunk_id: str
    chunk_identity: ActivationChunkIdentity
    chunk_identity_digest: str
    relative_path: str
    row_count: int
    hidden_width: int
    vector_shape: tuple[int, ...]
    dtype: str
    byte_size: int
    sha256: str
    creation_timestamp: str
    operational_status: str

    def to_document(self) -> dict[str, Any]:
        return {
            "byte_size": self.byte_size,
            "chunk_id": self.chunk_id,
            "chunk_identity": self.chunk_identity.to_document(),
            "chunk_identity_digest": self.chunk_identity_digest,
            "creation_timestamp": self.creation_timestamp,
            "creation_timestamp_semantics": (
                ACTIVATION_CHUNK_TIMESTAMP_SEMANTICS
            ),
            "dtype": self.dtype,
            "hidden_width": self.hidden_width,
            "operational_status": self.operational_status,
            "path": self.relative_path,
            "row_count": self.row_count,
            "sha256": self.sha256,
            "vector_shape": list(self.vector_shape),
        }


@dataclass(frozen=True)
class ActivationIndexSnapshot:
    """Backend-neutral immutable activation index snapshot."""

    snapshot_id: str
    store_identity: ActivationStoreIdentity
    run_status: str
    creation_timestamp: str
    chunks: tuple[ActivationChunkRecord, ...]
    index_rows: tuple[Mapping[str, Any], ...]

    def __post_init__(self) -> None:
        if not isinstance(self.index_rows, tuple):
            _store_error(
                ActivationStoreErrorCode.INVALID_INDEX,
                "index_rows must be an immutable tuple",
            )
        object.__setattr__(
            self,
            "index_rows",
            tuple(_freeze_json(dict(row)) for row in self.index_rows),
        )

    @property
    def relative_path(self) -> str:
        return f"indexes/index-{self.snapshot_id}.json"

    def to_document(self) -> dict[str, Any]:
        document = _snapshot_identity_document(self)
        document["snapshot_id"] = self.snapshot_id
        return document


@dataclass(frozen=True)
class ActivationShortfallReason:
    """One expected key that is not validated completed accepted."""

    row_key: ActivationRowKey
    operational_status: str
    lifecycle_status: str
    reason: str
    source_classification: str

    def to_document(self) -> dict[str, Any]:
        return {
            "lifecycle_status": self.lifecycle_status,
            "operational_status": self.operational_status,
            "reason": self.reason,
            "row_key": self.row_key.to_document(),
            "source_classification": self.source_classification,
        }


@dataclass(frozen=True)
class ActivationResumePlan:
    """Deterministic row classifications for an explicit resume snapshot."""

    skip: tuple[ActivationRowKey, ...]
    retry: tuple[ActivationRowKey, ...]
    conflicts: tuple[ActivationRowKey, ...]
    excluded: tuple[ActivationRowKey, ...]


@dataclass(frozen=True)
class ActivationStoreAudit:
    """Machine-readable cardinality, identity, and integrity audit."""

    expected_keys: tuple[ActivationRowKey, ...]
    completed_accepted_keys: tuple[ActivationRowKey, ...]
    missing_keys: tuple[ActivationRowKey, ...]
    duplicate_scientific_keys: tuple[ActivationRowKey, ...]
    duplicate_chunk_row_references: tuple[tuple[str, int], ...]
    unexpected_keys: tuple[ActivationRowKey, ...]
    pre_first_seen_keys: tuple[ActivationRowKey, ...]
    corrupt_chunks: tuple[str, ...]
    checksum_mismatches: tuple[str, ...]
    byte_size_mismatches: tuple[str, ...]
    dtype_mismatches: tuple[str, ...]
    shape_mismatches: tuple[str, ...]
    row_count_mismatches: tuple[str, ...]
    identity_mismatches: tuple[str, ...]
    pending_keys: tuple[ActivationRowKey, ...]
    writing_keys: tuple[ActivationRowKey, ...]
    failed_keys: tuple[ActivationRowKey, ...]
    excluded_keys: tuple[ActivationRowKey, ...]
    superseded_keys: tuple[ActivationRowKey, ...]
    immutable_orphan_chunks: tuple[str, ...]
    conflicting_completed_keys: tuple[ActivationRowKey, ...]
    unknown_referenced_chunks: tuple[str, ...]
    out_of_bounds_references: tuple[tuple[str, int], ...]
    incomplete_chunk_offsets: tuple[str, ...]
    row_chunk_layer_mismatches: tuple[ActivationRowKey, ...]
    row_chunk_dtype_mismatches: tuple[ActivationRowKey, ...]
    row_chunk_shape_mismatches: tuple[ActivationRowKey, ...]
    row_store_hook_mismatches: tuple[ActivationRowKey, ...]
    row_store_run_mismatches: tuple[ActivationRowKey, ...]
    chunk_row_range_mismatches: tuple[str, ...]
    referenced_row_count_mismatches: tuple[str, ...]
    shortfall_reasons: tuple[ActivationShortfallReason, ...]

    def to_document(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for field, value in self.__dict__.items():
            if value and isinstance(
                value[0], (ActivationShortfallReason, ActivationRowKey)
            ):
                result[field] = [item.to_document() for item in value]
            elif value and isinstance(value[0], tuple):
                result[field] = [list(item) for item in value]
            else:
                result[field] = list(value)
        result["audit_format_version"] = "person-a-activation-store-audit-v1"
        result["schema_version"] = SCHEMA_VERSION
        return result


def _store_identity_from_document(
    value: object,
) -> ActivationStoreIdentity:
    if not isinstance(value, Mapping):
        _store_error(
            ActivationStoreErrorCode.INVALID_INDEX,
            "store_identity must be an object",
        )
    required = {
        "accepted_manifest_hash",
        "checkpoint_hash",
        "code_sha",
        "config_hash",
        "dtype",
        "hidden_width",
        "hook_site",
        "model_hash",
        "preprocess_hash",
        "requested_layers",
        "run_id",
        "schema_version",
    }
    if set(value) != required:
        _store_error(
            ActivationStoreErrorCode.INVALID_INDEX,
            "store_identity has missing or additional fields",
        )
    layers = value["requested_layers"]
    if not isinstance(layers, list):
        _store_error(
            ActivationStoreErrorCode.INVALID_INDEX,
            "requested_layers must be a JSON list",
        )
    return ActivationStoreIdentity(
        schema_version=value["schema_version"],
        run_id=value["run_id"],
        checkpoint_hash=value["checkpoint_hash"],
        model_hash=value["model_hash"],
        config_hash=value["config_hash"],
        preprocess_hash=value["preprocess_hash"],
        accepted_manifest_hash=value["accepted_manifest_hash"],
        code_sha=value["code_sha"],
        hook_site=value["hook_site"],
        requested_layers=tuple(layers),
        dtype=value["dtype"],
        hidden_width=value["hidden_width"],
    )


def _row_key_from_document(value: object) -> ActivationRowKey:
    if not isinstance(value, Mapping):
        _store_error(
            ActivationStoreErrorCode.INVALID_INDEX,
            "row key must be an object",
        )
    required = {
        "hook_site",
        "layer_idx",
        "model_frame_idx",
        "producing_run_id",
        "trajectory_id",
    }
    if set(value) != required:
        _store_error(
            ActivationStoreErrorCode.INVALID_INDEX,
            "row key has missing or additional fields",
        )
    return ActivationRowKey(
        trajectory_id=value.get("trajectory_id"),
        model_frame_idx=value.get("model_frame_idx"),
        layer_idx=value.get("layer_idx"),
        hook_site=value.get("hook_site"),
        producing_run_id=value.get("producing_run_id"),
    )


def _chunk_record_from_document(value: object) -> ActivationChunkRecord:
    if not isinstance(value, Mapping):
        _store_error(
            ActivationStoreErrorCode.INVALID_INDEX,
            "chunk record must be an object",
        )
    required = {
        "byte_size",
        "chunk_id",
        "chunk_identity",
        "chunk_identity_digest",
        "creation_timestamp",
        "creation_timestamp_semantics",
        "dtype",
        "hidden_width",
        "operational_status",
        "path",
        "row_count",
        "sha256",
        "vector_shape",
    }
    if set(value) != required:
        _store_error(
            ActivationStoreErrorCode.INVALID_INDEX,
            "chunk record has missing or additional fields",
        )
    if (
        value["creation_timestamp_semantics"]
        != ACTIVATION_CHUNK_TIMESTAMP_SEMANTICS
    ):
        _store_error(
            ActivationStoreErrorCode.INVALID_INDEX,
            "chunk timestamp semantics are invalid",
        )
    identity_value = value.get("chunk_identity")
    if not isinstance(identity_value, Mapping):
        _store_error(
            ActivationStoreErrorCode.INVALID_INDEX,
            "chunk_identity must be an object",
        )
    identity_required = {
        "dtype",
        "first_row_key",
        "hidden_width",
        "last_row_key",
        "layer_idx",
        "row_count",
        "store_identity",
    }
    if set(identity_value) != identity_required:
        _store_error(
            ActivationStoreErrorCode.INVALID_INDEX,
            "chunk_identity has missing or additional fields",
        )
    chunk_identity = ActivationChunkIdentity(
        store_identity=_store_identity_from_document(
            identity_value.get("store_identity")
        ),
        layer_idx=identity_value.get("layer_idx"),
        first_row_key=_row_key_from_document(
            identity_value.get("first_row_key")
        ),
        last_row_key=_row_key_from_document(
            identity_value.get("last_row_key")
        ),
        row_count=identity_value.get("row_count"),
        dtype=identity_value.get("dtype"),
        hidden_width=identity_value.get("hidden_width"),
    )
    shape = value.get("vector_shape")
    if not isinstance(shape, list):
        _store_error(
            ActivationStoreErrorCode.INVALID_INDEX,
            "vector_shape must be a list",
        )
    return ActivationChunkRecord(
        chunk_id=value.get("chunk_id"),
        chunk_identity=chunk_identity,
        chunk_identity_digest=value.get("chunk_identity_digest"),
        relative_path=value.get("path"),
        row_count=value.get("row_count"),
        hidden_width=value.get("hidden_width"),
        vector_shape=tuple(shape),
        dtype=value.get("dtype"),
        byte_size=value.get("byte_size"),
        sha256=value.get("sha256"),
        creation_timestamp=value.get("creation_timestamp"),
        operational_status=value.get("operational_status"),
    )


def _snapshot_identity_document(
    snapshot: ActivationIndexSnapshot,
) -> dict[str, Any]:
    return {
        "chunks": [chunk.to_document() for chunk in snapshot.chunks],
        "creation_timestamp": snapshot.creation_timestamp,
        "format_version": ACTIVATION_INDEX_FORMAT_VERSION,
        "index_rows": [_thaw_json(row) for row in snapshot.index_rows],
        "run_status": snapshot.run_status,
        "schema_version": SCHEMA_VERSION,
        "store_identity": snapshot.store_identity.to_document(),
    }


def _strict_index_document(path: Path) -> Mapping[str, Any]:
    try:
        byte_size = path.stat().st_size
    except OSError as error:
        _store_error(
            ActivationStoreErrorCode.INVALID_INDEX,
            f"could not inspect index snapshot: {error}",
            path=path,
        )
    if byte_size > MAX_ACTIVATION_INDEX_JSON_BYTES:
        _store_error(
            ActivationStoreErrorCode.LIMIT_EXCEEDED,
            f"index JSON exceeds reviewed byte limit "
            f"{MAX_ACTIVATION_INDEX_JSON_BYTES}",
            path=path,
        )

    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                _store_error(
                    ActivationStoreErrorCode.INVALID_INDEX,
                    f"duplicate JSON key {key!r}",
                    path=path,
                )
            result[key] = value
        return result

    def reject_constant(value: str) -> None:
        _store_error(
            ActivationStoreErrorCode.INVALID_INDEX,
            f"nonfinite JSON constant {value!r}",
            path=path,
        )

    try:
        document = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=reject_duplicates,
            parse_constant=reject_constant,
        )
    except ActivationStoreError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        _store_error(
            ActivationStoreErrorCode.INVALID_INDEX,
            f"could not parse index snapshot: {error}",
            path=path,
        )
    if not isinstance(document, Mapping):
        _store_error(
            ActivationStoreErrorCode.INVALID_INDEX,
            "index snapshot root must be an object",
            path=path,
        )
    return document


def _snapshot_from_document(document: Mapping[str, Any]) -> ActivationIndexSnapshot:
    required = {
        "chunks",
        "creation_timestamp",
        "format_version",
        "index_rows",
        "run_status",
        "schema_version",
        "snapshot_id",
        "store_identity",
    }
    if set(document) != required:
        _store_error(
            ActivationStoreErrorCode.INVALID_INDEX,
            "index snapshot has missing or additional top-level fields",
        )
    if document["format_version"] != ACTIVATION_INDEX_FORMAT_VERSION:
        _store_error(
            ActivationStoreErrorCode.INVALID_INDEX,
            "unsupported activation index format version",
        )
    if document["schema_version"] != SCHEMA_VERSION:
        _store_error(
            ActivationStoreErrorCode.INVALID_INDEX,
            "activation schema version must remain 1.0",
        )
    chunks = document["chunks"]
    rows = document["index_rows"]
    if not isinstance(chunks, list) or not isinstance(rows, list):
        _store_error(
            ActivationStoreErrorCode.INVALID_INDEX,
            "chunks and index_rows must be lists",
        )
    if len(chunks) > MAX_ACTIVATION_CHUNKS_PER_SNAPSHOT:
        _store_error(
            ActivationStoreErrorCode.LIMIT_EXCEEDED,
            "declared chunk count exceeds reviewed snapshot limit",
            field="chunks",
        )
    if len(rows) > MAX_ACTIVATION_INDEX_ROWS:
        _store_error(
            ActivationStoreErrorCode.LIMIT_EXCEEDED,
            "declared index row count exceeds reviewed snapshot limit",
            field="index_rows",
        )
    if not all(isinstance(row, Mapping) for row in rows):
        _store_error(
            ActivationStoreErrorCode.INVALID_INDEX,
            "every index row must be an object",
        )
    return ActivationIndexSnapshot(
        snapshot_id=document["snapshot_id"],
        store_identity=_store_identity_from_document(
            document["store_identity"]
        ),
        run_status=document["run_status"],
        creation_timestamp=document["creation_timestamp"],
        chunks=tuple(_chunk_record_from_document(chunk) for chunk in chunks),
        index_rows=tuple(dict(row) for row in rows),
    )


def _numpy_module() -> Any:
    return importlib.import_module("numpy")


def _validate_chunk_record_metadata(
    record: ActivationChunkRecord,
    store_identity: ActivationStoreIdentity,
) -> None:
    if not isinstance(record, ActivationChunkRecord):
        _store_error(
            ActivationStoreErrorCode.INVALID_CHUNK,
            "chunk descriptor must be ActivationChunkRecord",
        )
    identity = record.chunk_identity
    if not isinstance(identity, ActivationChunkIdentity):
        _store_error(
            ActivationStoreErrorCode.INVALID_CHUNK,
            "chunk_identity must be ActivationChunkIdentity",
        )
    ActivationChunkIdentity(
        store_identity=identity.store_identity,
        layer_idx=identity.layer_idx,
        first_row_key=identity.first_row_key,
        last_row_key=identity.last_row_key,
        row_count=identity.row_count,
        dtype=identity.dtype,
        hidden_width=identity.hidden_width,
    )
    _phase5_require_text(record.chunk_id, "chunk_id")
    _safe_store_relative_path(record.relative_path, "path")
    if not record.relative_path.endswith(".npy"):
        _store_error(
            ActivationStoreErrorCode.UNSAFE_PATH,
            "pooled chunk path must end in .npy",
            field="path",
        )
    if record.chunk_identity.store_identity != store_identity:
        _store_error(
            ActivationStoreErrorCode.IDENTITY_CONFLICT,
            "chunk is bound to a different store identity",
        )
    if record.chunk_identity_digest != record.chunk_identity.digest:
        _store_error(
            ActivationStoreErrorCode.IDENTITY_CONFLICT,
            "chunk identity digest does not match its complete identity",
        )
    expected_chunk_id = f"activation-chunk-{record.chunk_identity_digest[:24]}"
    if record.chunk_id != expected_chunk_id:
        _store_error(
            ActivationStoreErrorCode.IDENTITY_CONFLICT,
            "chunk_id does not match its deterministic identity digest",
        )
    _phase5_require_integer(record.row_count, "row_count", minimum=1)
    _phase5_require_integer(record.hidden_width, "hidden_width", minimum=1)
    _phase5_require_integer(record.byte_size, "byte_size", minimum=1)
    if record.row_count > MAX_ACTIVATION_ROWS_PER_CHUNK:
        _store_error(
            ActivationStoreErrorCode.LIMIT_EXCEEDED,
            "chunk row count exceeds reviewed limit",
            field="row_count",
        )
    if record.hidden_width > MAX_ACTIVATION_HIDDEN_WIDTH:
        _store_error(
            ActivationStoreErrorCode.LIMIT_EXCEEDED,
            "chunk hidden width exceeds reviewed limit",
            field="hidden_width",
        )
    if record.byte_size > MAX_ACTIVATION_CHUNK_BYTES:
        _store_error(
            ActivationStoreErrorCode.LIMIT_EXCEEDED,
            "declared chunk byte size exceeds reviewed limit",
            field="byte_size",
        )
    _phase5_require_hex(record.sha256, "sha256", 64)
    _phase5_require_timestamp(record.creation_timestamp, "creation_timestamp")
    _validate_store_dtype(record.dtype)
    if record.operational_status != "completed":
        _store_error(
            ActivationStoreErrorCode.INVALID_STATE,
            "accepted index chunks must have operational_status='completed'",
        )
    if (
        record.row_count != record.chunk_identity.row_count
        or record.hidden_width != record.chunk_identity.hidden_width
        or record.dtype != record.chunk_identity.dtype
        or record.vector_shape != (record.hidden_width,)
    ):
        _store_error(
            ActivationStoreErrorCode.INVALID_CHUNK,
            "chunk metadata disagrees with its identity or vector shape",
        )


def _validate_persisted_chunk(
    store_root: Path | str,
    record: ActivationChunkRecord,
    store_identity: ActivationStoreIdentity,
) -> None:
    _validate_chunk_record_metadata(record, store_identity)
    path = _require_ordinary_store_file(store_root, record.relative_path)
    observed_size = path.stat().st_size
    if observed_size > MAX_ACTIVATION_CHUNK_BYTES:
        _store_error(
            ActivationStoreErrorCode.LIMIT_EXCEEDED,
            f"persisted chunk exceeds reviewed byte limit "
            f"{MAX_ACTIVATION_CHUNK_BYTES}",
            path=path,
        )
    if observed_size != record.byte_size:
        _store_error(
            ActivationStoreErrorCode.BYTE_SIZE_MISMATCH,
            f"expected {record.byte_size} bytes, observed {observed_size}",
            path=path,
        )
    observed_hash = _sha256_file(path)
    if observed_hash != record.sha256:
        _store_error(
            ActivationStoreErrorCode.CHECKSUM_MISMATCH,
            "persisted chunk SHA-256 does not match its descriptor",
            path=path,
        )
    numpy = _numpy_module()
    try:
        array = numpy.load(path, allow_pickle=False)
    except (OSError, ValueError, TypeError) as error:
        _store_error(
            ActivationStoreErrorCode.INVALID_CHUNK,
            f"could not load persisted .npy chunk: {error}",
            path=path,
        )
    if (
        not isinstance(array, numpy.ndarray)
        or array.ndim != 2
        or array.shape != (record.row_count, record.hidden_width)
        or array.dtype.name != record.dtype
        or array.dtype.hasobject
        or not array.flags.c_contiguous
        or not numpy.issubdtype(array.dtype, numpy.floating)
    ):
        _store_error(
            ActivationStoreErrorCode.INVALID_CHUNK,
            "persisted array rank, shape, dtype, or layout is invalid",
            path=path,
        )
    if not bool(numpy.isfinite(array).all()):
        _store_error(
            ActivationStoreErrorCode.INVALID_CHUNK,
            "persisted pooled vectors must contain only finite values",
            path=path,
        )


def _validate_index_row(
    row: Mapping[str, Any],
    identity: ActivationStoreIdentity,
) -> ActivationRowKey:
    if not isinstance(row, Mapping):
        _store_error(
            ActivationStoreErrorCode.INVALID_ROW,
            "index row must be an object",
        )
    try:
        validate_identity(row)
    except (IdentityValidationError, TypeError) as error:
        _store_error(
            ActivationStoreErrorCode.INVALID_ROW,
            f"universal identity validation failed: {error}",
        )
    required = {
        "accepted_manifest_hash",
        "activation_chunk_id",
        "checkpoint_hash",
        "chunk_row_idx",
        "dtype",
        "frame_token_positions",
        "hook_site",
        "layer_idx",
        "pooling_method",
        "run_status",
        "token_region",
        "vector_shape",
    }
    missing = sorted(required - set(row))
    if missing:
        _store_error(
            ActivationStoreErrorCode.INVALID_ROW,
            "missing activation fields: " + ", ".join(missing),
        )
    if row["status"] != "accepted":
        _store_error(
            ActivationStoreErrorCode.INVALID_STATE,
            "only lifecycle status 'accepted' may enter the accepted index",
        )
    if row["run_status"] != "completed":
        _store_error(
            ActivationStoreErrorCode.INVALID_STATE,
            "only completed producing runs may enter the accepted index",
        )
    key = ActivationRowKey.from_row(row)
    expected_pairs = {
        "accepted_manifest_hash": identity.accepted_manifest_hash,
        "checkpoint_hash": identity.checkpoint_hash,
        "code_sha": identity.code_sha,
        "config_hash": identity.config_hash,
        "dtype": identity.dtype,
        "hook_site": identity.hook_site,
        "model_hash": identity.model_hash,
        "preprocess_hash": identity.preprocess_hash,
        "run_id": identity.run_id,
        "schema_version": identity.schema_version,
    }
    for field, expected in expected_pairs.items():
        if row.get(field) != expected:
            _store_error(
                ActivationStoreErrorCode.IDENTITY_CONFLICT,
                f"row value does not match store identity; expected {expected!r}",
                field=field,
            )
    if tuple(row.get("vector_shape", ())) != (identity.hidden_width,):
        _store_error(
            ActivationStoreErrorCode.IDENTITY_CONFLICT,
            "row vector_shape does not match store identity",
            field="vector_shape",
        )
    if key.layer_idx not in identity.requested_layers:
        _store_error(
            ActivationStoreErrorCode.IDENTITY_CONFLICT,
            "row layer is not in requested_layers",
            field="layer_idx",
        )
    if row["token_region"] != "visual" or row["pooling_method"] != "mean":
        _store_error(
            ActivationStoreErrorCode.INVALID_ROW,
            "production chunks contain mean-pooled visual vectors only",
        )
    chunk_row_idx = row["chunk_row_idx"]
    _phase5_require_integer(chunk_row_idx, "chunk_row_idx")
    return key


def _handoff_document(snapshot: ActivationIndexSnapshot) -> dict[str, Any]:
    layer_counts = Counter(
        int(row["layer_idx"]) for row in snapshot.index_rows
    )
    frame_keys = {
        (str(row["trajectory_id"]), int(row["model_frame_idx"]))
        for row in snapshot.index_rows
    }
    counts = {str(layer): count for layer, count in sorted(layer_counts.items())}
    return {
        "accepted_manifest_hash": snapshot.store_identity.accepted_manifest_hash,
        "cardinality_report": {
            "accepted_manifest_rows": len(frame_keys),
            "actual_activation_rows": len(snapshot.index_rows),
            "actual_rows_by_layer": counts,
            "expected_activation_rows": len(snapshot.index_rows),
            "expected_rows_by_layer": counts,
        },
        "checkpoint_hash": snapshot.store_identity.checkpoint_hash,
        "chunks": [
            {
                "chunk_id": chunk.chunk_id,
                "dtype": chunk.dtype,
                "path": chunk.relative_path,
                "row_count": chunk.row_count,
                "sha256": chunk.sha256,
                "vector_shape": list(chunk.vector_shape),
            }
            for chunk in snapshot.chunks
        ],
        "handoff_id": snapshot.snapshot_id,
        "index_rows": [_thaw_json(row) for row in snapshot.index_rows],
        "preprocess_hash": snapshot.store_identity.preprocess_hash,
        "run_id": snapshot.store_identity.run_id,
        "run_status": snapshot.run_status,
        "schema_version": SCHEMA_VERSION,
        "selection_policy": {
            "description": (
                "Accepted-manifest and requested-layer extraction independent "
                "of target and held-out labels."
            ),
            "uses_heldout_labels": False,
            "uses_target_labels": False,
        },
    }


def _validate_snapshot_structure(snapshot: ActivationIndexSnapshot) -> None:
    if not isinstance(snapshot, ActivationIndexSnapshot):
        _store_error(
            ActivationStoreErrorCode.INVALID_INDEX,
            "snapshot must be ActivationIndexSnapshot",
        )
    _phase5_require_hex(snapshot.snapshot_id, "snapshot_id", 64)
    _phase5_require_timestamp(
        snapshot.creation_timestamp,
        "creation_timestamp",
    )
    if snapshot.run_status != "completed":
        _store_error(
            ActivationStoreErrorCode.INVALID_STATE,
            "accepted index snapshots require a completed run",
        )
    if snapshot.snapshot_id != _canonical_digest(
        _snapshot_identity_document(snapshot)
    ):
        _store_error(
            ActivationStoreErrorCode.INVALID_INDEX,
            "snapshot_id does not match canonical snapshot identity",
        )
    if tuple(sorted(snapshot.chunks, key=lambda item: item.chunk_id)) != (
        snapshot.chunks
    ):
        _store_error(
            ActivationStoreErrorCode.INVALID_INDEX,
            "chunk descriptors are not in deterministic order",
        )
    if len(snapshot.chunks) > MAX_ACTIVATION_CHUNKS_PER_SNAPSHOT:
        _store_error(
            ActivationStoreErrorCode.LIMIT_EXCEEDED,
            "snapshot chunk count exceeds reviewed limit",
            field="chunks",
        )
    if len(snapshot.index_rows) > MAX_ACTIVATION_INDEX_ROWS:
        _store_error(
            ActivationStoreErrorCode.LIMIT_EXCEEDED,
            "snapshot row count exceeds reviewed limit",
            field="index_rows",
        )
    chunk_by_id: dict[str, ActivationChunkRecord] = {}
    for chunk in snapshot.chunks:
        _validate_chunk_record_metadata(chunk, snapshot.store_identity)
        if chunk.chunk_id in chunk_by_id:
            _store_error(
                ActivationStoreErrorCode.INVALID_INDEX,
                f"duplicate chunk_id {chunk.chunk_id!r}",
            )
        chunk_by_id[chunk.chunk_id] = chunk
    referenced_bytes = sum(chunk.byte_size for chunk in snapshot.chunks)
    if referenced_bytes > MAX_ACTIVATION_SNAPSHOT_REFERENCED_BYTES:
        _store_error(
            ActivationStoreErrorCode.LIMIT_EXCEEDED,
            "snapshot referenced-byte total exceeds reviewed limit",
            field="chunks",
        )
    keys: list[ActivationRowKey] = []
    references: set[tuple[str, int]] = set()
    reference_counts: Counter[str] = Counter()
    keys_by_chunk: dict[str, list[ActivationRowKey]] = {
        chunk_id: [] for chunk_id in chunk_by_id
    }
    offsets_by_chunk: dict[str, list[int]] = {
        chunk_id: [] for chunk_id in chunk_by_id
    }
    for row in snapshot.index_rows:
        key = _validate_index_row(row, snapshot.store_identity)
        keys.append(key)
        chunk_id = row["activation_chunk_id"]
        if chunk_id not in chunk_by_id:
            _store_error(
                ActivationStoreErrorCode.INVALID_INDEX,
                f"row references unknown chunk {chunk_id!r}",
            )
        reference = (chunk_id, int(row["chunk_row_idx"]))
        if reference in references:
            _store_error(
                ActivationStoreErrorCode.INVALID_INDEX,
                f"duplicate chunk-row reference {reference!r}",
            )
        references.add(reference)
        reference_counts[chunk_id] += 1
        chunk = chunk_by_id[chunk_id]
        if (
            reference[1] >= chunk.row_count
            or row["dtype"] != chunk.dtype
            or tuple(row["vector_shape"]) != chunk.vector_shape
            or key.layer_idx != chunk.chunk_identity.layer_idx
            or key.hook_site
            != chunk.chunk_identity.store_identity.hook_site
            or key.producing_run_id
            != chunk.chunk_identity.store_identity.run_id
        ):
            _store_error(
                ActivationStoreErrorCode.INVALID_INDEX,
                "row offset, shape, dtype, layer, hook, or run disagrees "
                "with its chunk",
            )
        keys_by_chunk[chunk_id].append(key)
        offsets_by_chunk[chunk_id].append(reference[1])
    if tuple(sorted(keys)) != tuple(keys):
        _store_error(
            ActivationStoreErrorCode.INVALID_INDEX,
            "index rows are not in deterministic scientific-key order",
        )
    if len(set(keys)) != len(keys):
        _store_error(
            ActivationStoreErrorCode.INVALID_INDEX,
            "duplicate scientific activation identity",
        )
    for chunk in snapshot.chunks:
        chunk_keys = keys_by_chunk[chunk.chunk_id]
        offsets = offsets_by_chunk[chunk.chunk_id]
        expected_offsets = set(range(chunk.row_count))
        if (
            reference_counts[chunk.chunk_id] != chunk.row_count
            or len(set(chunk_keys)) != chunk.chunk_identity.row_count
            or set(offsets) != expected_offsets
            or (chunk_keys and min(chunk_keys) != chunk.chunk_identity.first_row_key)
            or (chunk_keys and max(chunk_keys) != chunk.chunk_identity.last_row_key)
            or not chunk_keys
        ):
            _store_error(
                ActivationStoreErrorCode.INVALID_INDEX,
                f"chunk {chunk.chunk_id!r} row range, count, or offsets differ",
            )
    contract_result = validate_activation_handoff(
        _handoff_document(snapshot)
    )
    if not contract_result.accepted:
        details = "; ".join(
            f"{item.code.value}: {item.message}"
            for item in contract_result.rejections
        )
        _store_error(
            ActivationStoreErrorCode.INVALID_INDEX,
            f"activation handoff contract rejected snapshot: {details}",
        )


def validate_activation_index_snapshot(
    snapshot: ActivationIndexSnapshot,
    *,
    store_root: Path | str,
) -> None:
    """Validate canonical index structure and every referenced chunk."""

    _validate_snapshot_structure(snapshot)
    _validate_run_identity_binding(
        store_root=store_root,
        identity=snapshot.store_identity,
    )
    for chunk in snapshot.chunks:
        _validate_persisted_chunk(
            store_root,
            chunk,
            snapshot.store_identity,
        )


def load_activation_index_snapshot(
    path: Path | str,
    *,
    store_root: Path | str,
) -> ActivationIndexSnapshot:
    """Strictly load and independently validate an explicit snapshot."""

    snapshot_path = Path(path)
    if not snapshot_path.is_absolute():
        snapshot_path = _require_ordinary_store_file(
            store_root,
            snapshot_path.as_posix(),
        )
    else:
        lexical_root = Path(store_root).absolute()
        lexical_snapshot = snapshot_path.absolute()
        try:
            relative = lexical_snapshot.relative_to(lexical_root).as_posix()
        except ValueError:
            _store_error(
                ActivationStoreErrorCode.UNSAFE_PATH,
                "snapshot path is outside the selected store root",
                path=snapshot_path,
            )
        snapshot_path = _require_ordinary_store_file(store_root, relative)
    document = _strict_index_document(snapshot_path)
    snapshot = _snapshot_from_document(document)
    expected_path = _require_ordinary_store_file(
        store_root,
        snapshot.relative_path,
    )
    if snapshot_path.absolute() != expected_path.absolute():
        _store_error(
            ActivationStoreErrorCode.IDENTITY_CONFLICT,
            "snapshot filename does not match its canonical identity",
            path=snapshot_path,
        )
    if snapshot_path.read_bytes() != _canonical_json_bytes(
        snapshot.to_document()
    ):
        _store_error(
            ActivationStoreErrorCode.INVALID_INDEX,
            "snapshot bytes are not canonical deterministic JSON",
            path=snapshot_path,
        )
    validate_activation_index_snapshot(snapshot, store_root=store_root)
    return snapshot


def _raise_for_fault(
    configured: ActivationPublicationFaultPoint | None,
    current: ActivationPublicationFaultPoint,
) -> None:
    if configured == current:
        _store_error(
            ActivationStoreErrorCode.FORCED_INTERRUPTION,
            f"forced interruption at {current.value}",
        )


def _publish_exact_bytes(
    destination: Path,
    payload: bytes,
    *,
    fault_during: bool,
) -> bool:
    """Publish exact bytes exclusively; return False for identical reuse."""

    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor: int | None = None
    temporary: Path | None = None
    primary: BaseException | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
        )
        temporary = Path(temporary_name)
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = None
            if fault_during:
                stream.write(payload[: max(1, len(payload) // 2)])
                stream.flush()
                os.fsync(stream.fileno())
                _store_error(
                    ActivationStoreErrorCode.FORCED_INTERRUPTION,
                    "forced interruption during immutable publication",
                    path=destination,
                )
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, destination)
            return True
        except FileExistsError:
            if destination.is_symlink():
                _store_error(
                    ActivationStoreErrorCode.UNSAFE_PATH,
                    "existing immutable output must not be a symbolic link",
                    path=destination,
                )
            try:
                existing = destination.read_bytes()
            except OSError as error:
                _store_error(
                    ActivationStoreErrorCode.OUTPUT_EXISTS,
                    f"could not validate existing immutable output: {error}",
                    path=destination,
                )
            if existing != payload:
                _store_error(
                    ActivationStoreErrorCode.IDENTITY_CONFLICT,
                    "existing immutable path contains conflicting bytes",
                    path=destination,
                )
            return False
        except OSError as error:
            _store_error(
                ActivationStoreErrorCode.PUBLICATION_FAILED,
                f"exclusive hard-link publication failed: {error}",
                path=destination,
            )
    except BaseException as error:
        primary = error
        raise
    finally:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError as cleanup_error:
                cleanup = ActivationStoreError(
                    ActivationStoreErrorCode.PUBLICATION_FAILED,
                    "could not remove operation-created temporary file",
                    path=temporary,
                )
                cleanup.__cause__ = cleanup_error
                if primary is not None:
                    primary.__context__ = cleanup
                else:
                    raise cleanup


def _run_binding_relative_path(identity: ActivationStoreIdentity) -> str:
    run_digest = hashlib.sha256(identity.run_id.encode("utf-8")).hexdigest()
    return f"run_bindings/run-{run_digest}.json"


def _run_binding_identity_document(
    identity: ActivationStoreIdentity,
    proof: ActivationEligibilityProof,
) -> dict[str, Any]:
    return {
        "eligibility_proof_digest": proof.digest,
        "eligibility_row_count": len(proof.eligible_rows),
        "eligibility_source_manifest_row_count": (
            proof.source_manifest_row_count
        ),
        "eligibility_source_rows_digest": proof.source_rows_digest,
        "format_version": ACTIVATION_RUN_BINDING_FORMAT_VERSION,
        "run_id": identity.run_id,
        "schema_version": SCHEMA_VERSION,
        "store_identity": identity.to_document(),
        "store_identity_digest": identity.digest,
    }


def _run_binding_document(
    identity: ActivationStoreIdentity,
    proof: ActivationEligibilityProof,
) -> dict[str, Any]:
    document = _run_binding_identity_document(identity, proof)
    document["binding_digest"] = _canonical_digest(document)
    return document


def _strict_run_binding_document(path: Path) -> Mapping[str, Any]:
    if path.stat().st_size > MAX_ACTIVATION_RUN_BINDING_BYTES:
        _store_error(
            ActivationStoreErrorCode.LIMIT_EXCEEDED,
            "run binding exceeds reviewed byte limit",
            path=path,
        )

    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                _store_error(
                    ActivationStoreErrorCode.RUN_BINDING_CONFLICT,
                    f"duplicate run-binding JSON key {key!r}",
                    path=path,
                )
            result[key] = value
        return result

    def reject_constant(value: str) -> None:
        _store_error(
            ActivationStoreErrorCode.RUN_BINDING_CONFLICT,
            f"nonfinite run-binding JSON constant {value!r}",
            path=path,
        )

    try:
        document = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=reject_duplicates,
            parse_constant=reject_constant,
        )
    except ActivationStoreError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        _store_error(
            ActivationStoreErrorCode.RUN_BINDING_CONFLICT,
            f"could not parse immutable run binding: {error}",
            path=path,
        )
    if not isinstance(document, Mapping):
        _store_error(
            ActivationStoreErrorCode.RUN_BINDING_CONFLICT,
            "run binding root must be an object",
            path=path,
        )
    return document


def _validate_run_identity_binding(
    *,
    store_root: Path | str,
    identity: ActivationStoreIdentity,
    eligibility_proof: ActivationEligibilityProof | None = None,
) -> None:
    path = _require_ordinary_store_file(
        store_root,
        _run_binding_relative_path(identity),
    )
    document = _strict_run_binding_document(path)
    required = {
        "binding_digest",
        "eligibility_proof_digest",
        "eligibility_row_count",
        "eligibility_source_manifest_row_count",
        "eligibility_source_rows_digest",
        "format_version",
        "run_id",
        "schema_version",
        "store_identity",
        "store_identity_digest",
    }
    if set(document) != required:
        _store_error(
            ActivationStoreErrorCode.RUN_BINDING_CONFLICT,
            "run binding has missing or additional fields",
            path=path,
        )
    identity_document = dict(document)
    binding_digest = identity_document.pop("binding_digest")
    existing_identity = _store_identity_from_document(
        identity_document.get("store_identity")
    )
    _phase5_require_hex(
        document.get("eligibility_proof_digest"),
        "eligibility_proof_digest",
        64,
    )
    _phase5_require_hex(
        document.get("eligibility_source_rows_digest"),
        "eligibility_source_rows_digest",
        64,
    )
    _phase5_require_integer(
        document.get("eligibility_row_count"),
        "eligibility_row_count",
        minimum=1,
    )
    _phase5_require_integer(
        document.get("eligibility_source_manifest_row_count"),
        "eligibility_source_manifest_row_count",
        minimum=1,
    )
    if (
        document.get("format_version")
        != ACTIVATION_RUN_BINDING_FORMAT_VERSION
        or document.get("schema_version") != SCHEMA_VERSION
        or document.get("run_id") != identity.run_id
        or document.get("store_identity_digest") != existing_identity.digest
        or binding_digest != _canonical_digest(identity_document)
        or path.read_bytes() != _canonical_json_bytes(dict(document))
    ):
        _store_error(
            ActivationStoreErrorCode.RUN_BINDING_CONFLICT,
            "run binding bytes, digest, or identity are invalid",
            path=path,
        )
    if existing_identity != identity:
        _store_error(
            ActivationStoreErrorCode.RUN_BINDING_CONFLICT,
            f"run_id={identity.run_id!r} is already bound to "
            f"{existing_identity.digest}; requested {identity.digest}",
            field="run_id",
            path=path,
        )
    if eligibility_proof is not None and (
        document["eligibility_proof_digest"] != eligibility_proof.digest
        or document["eligibility_row_count"]
        != len(eligibility_proof.eligible_rows)
        or document["eligibility_source_manifest_row_count"]
        != eligibility_proof.source_manifest_row_count
        or document["eligibility_source_rows_digest"]
        != eligibility_proof.source_rows_digest
    ):
        _store_error(
            ActivationStoreErrorCode.ELIGIBILITY_CONFLICT,
            f"run_id={identity.run_id!r} is already bound to eligibility "
            f"{document['eligibility_proof_digest']}; requested "
            f"{eligibility_proof.digest}",
            field="eligibility_proof",
            path=path,
        )


def _ensure_run_identity_binding(
    *,
    store_root: Path | str,
    identity: ActivationStoreIdentity,
    eligibility_proof: ActivationEligibilityProof,
    fault_point: ActivationPublicationFaultPoint | None,
) -> None:
    relative_path = _run_binding_relative_path(identity)
    path = _resolve_store_path(store_root, relative_path)
    payload = _canonical_json_bytes(
        _run_binding_document(identity, eligibility_proof)
    )
    if len(payload) > MAX_ACTIVATION_RUN_BINDING_BYTES:
        _store_error(
            ActivationStoreErrorCode.LIMIT_EXCEEDED,
            "canonical run binding exceeds reviewed byte limit",
            path=path,
        )
    if path.exists() or path.is_symlink():
        _validate_run_identity_binding(
            store_root=store_root,
            identity=identity,
            eligibility_proof=eligibility_proof,
        )
        return
    try:
        _publish_exact_bytes(
            path,
            payload,
            fault_during=(
                fault_point
                == ActivationPublicationFaultPoint.DURING_RUN_BINDING_PUBLICATION
            ),
        )
    except ActivationStoreError as error:
        if error.code == ActivationStoreErrorCode.IDENTITY_CONFLICT:
            _validate_run_identity_binding(
                store_root=store_root,
                identity=identity,
                eligibility_proof=eligibility_proof,
            )
        raise
    _validate_run_identity_binding(
        store_root=store_root,
        identity=identity,
        eligibility_proof=eligibility_proof,
    )


def _validate_candidate_eligibility(
    *,
    identity: ActivationStoreIdentity,
    proof: ActivationEligibilityProof,
    rows: Sequence[Mapping[str, Any]],
) -> None:
    if not isinstance(proof, ActivationEligibilityProof):
        _store_error(
            ActivationStoreErrorCode.ELIGIBILITY_CONFLICT,
            "eligibility_proof must be ActivationEligibilityProof",
        )
    if (
        proof.store_identity_digest != identity.digest
        or proof.accepted_manifest_hash != identity.accepted_manifest_hash
    ):
        _store_error(
            ActivationStoreErrorCode.ELIGIBILITY_CONFLICT,
            "eligibility proof is bound to a different complete store identity",
        )
    authority = {
        _row_key_from_document(value["row_key"]): value["metadata"]
        for value in proof.eligible_rows
    }
    if len(authority) != len(proof.eligible_rows):
        _store_error(
            ActivationStoreErrorCode.ELIGIBILITY_CONFLICT,
            "eligibility proof contains duplicate activation keys",
        )
    for index, row in enumerate(rows):
        key = ActivationRowKey.from_row(row)
        expected = authority.get(key)
        if expected is None:
            _store_error(
                ActivationStoreErrorCode.ELIGIBILITY_CONFLICT,
                "candidate row is outside the internally reconstructed "
                "eligible universe; "
                f"candidate_key={key.to_document()!r}; "
                "accepted_manifest_hash="
                f"{proof.accepted_manifest_hash}; "
                f"authoritative_eligibility_digest={proof.digest}",
                field=f"rows[{index}]",
            )
        for field in ACTIVATION_ELIGIBILITY_METADATA_FIELDS:
            if row.get(field) != expected[field]:
                _store_error(
                    ActivationStoreErrorCode.ELIGIBILITY_CONFLICT,
                    f"candidate metadata differs from authority; expected "
                    f"{expected[field]!r}; "
                    f"candidate_key={key.to_document()!r}; "
                    "accepted_manifest_hash="
                    f"{proof.accepted_manifest_hash}; "
                    f"authoritative_eligibility_digest={proof.digest}",
                    field=f"rows[{index}].{field}",
                )


def _validate_claimed_eligibility_proof(
    *,
    authoritative: ActivationEligibilityProof,
    claimed: ActivationEligibilityProof | None,
    candidate_key: object,
) -> None:
    """Require any compatibility proof claim to equal reconstructed authority."""

    if claimed is None:
        return
    if not isinstance(claimed, ActivationEligibilityProof):
        _store_error(
            ActivationStoreErrorCode.ELIGIBILITY_CONFLICT,
            "eligibility_proof is only a compatibility claim and must be an "
            "ActivationEligibilityProof; accepted_manifest_hash="
            f"{authoritative.accepted_manifest_hash}; "
            "authoritative_eligibility_digest="
            f"{authoritative.digest}; candidate_key={candidate_key!r}",
            field="eligibility_proof",
        )
    fields = (
        "store_identity_digest",
        "accepted_manifest_hash",
        "source_manifest_row_count",
        "source_rows_digest",
        "eligible_rows",
    )
    for field in fields:
        if getattr(claimed, field) != getattr(authoritative, field):
            _store_error(
                ActivationStoreErrorCode.ELIGIBILITY_CONFLICT,
                "caller-supplied eligibility proof conflicts with internally "
                "reconstructed authority; "
                f"accepted_manifest_hash="
                f"{authoritative.accepted_manifest_hash}; "
                "authoritative_eligibility_digest="
                f"{authoritative.digest}; "
                f"supplied_eligibility_digest={claimed.digest}; "
                f"candidate_key={candidate_key!r}",
                field=f"eligibility_proof.{field}",
            )


def _candidate_key_diagnostic(
    rows: object,
) -> object:
    """Return a safe first-key diagnostic without granting it authority."""

    if (
        isinstance(rows, Sequence)
        and not isinstance(rows, (str, bytes))
        and rows
        and isinstance(rows[0], Mapping)
    ):
        first = rows[0]
        return {
            "hook_site": first.get("hook_site"),
            "layer_idx": first.get("layer_idx"),
            "model_frame_idx": first.get("model_frame_idx"),
            "producing_run_id": first.get("run_id"),
            "trajectory_id": first.get("trajectory_id"),
        }
    return "<unavailable>"


def _candidate_rows_and_vectors(
    *,
    identity: ActivationStoreIdentity,
    rows: Sequence[Mapping[str, Any]],
    vectors: object,
) -> tuple[list[dict[str, Any]], Any, list[ActivationRowKey]]:
    if (
        isinstance(rows, (str, bytes))
        or not isinstance(rows, Sequence)
        or not rows
    ):
        _store_error(
            ActivationStoreErrorCode.INVALID_ROW,
            "rows must be a non-empty sequence of mappings",
        )
    if len(rows) > MAX_ACTIVATION_ROWS_PER_CHUNK:
        _store_error(
            ActivationStoreErrorCode.LIMIT_EXCEEDED,
            f"candidate row count exceeds reviewed per-chunk limit "
            f"{MAX_ACTIVATION_ROWS_PER_CHUNK}",
            field="rows",
        )
    numpy = _numpy_module()
    candidate_array = numpy.asarray(vectors)
    if candidate_array.dtype.hasobject:
        _store_error(
            ActivationStoreErrorCode.UNSUPPORTED_DTYPE,
            "object arrays are forbidden",
        )
    if (
        candidate_array.ndim != 2
        or candidate_array.shape
        != (len(rows), identity.hidden_width)
    ):
        _store_error(
            ActivationStoreErrorCode.INVALID_CHUNK,
            "candidate vectors must have shape [row_count, hidden_width]",
        )
    if candidate_array.dtype.name != identity.dtype:
        _store_error(
            ActivationStoreErrorCode.UNSUPPORTED_DTYPE,
            "candidate vector dtype does not match store identity",
        )
    if (
        not numpy.issubdtype(candidate_array.dtype, numpy.floating)
        or not bool(numpy.isfinite(candidate_array).all())
    ):
        _store_error(
            ActivationStoreErrorCode.INVALID_CHUNK,
            "candidate vectors must be finite floating values",
        )
    normalized_rows: list[dict[str, Any]] = []
    keys: list[ActivationRowKey] = []
    for source in rows:
        if not isinstance(source, Mapping):
            _store_error(
                ActivationStoreErrorCode.INVALID_ROW,
                "every candidate row must be a mapping",
            )
        row = dict(source)
        try:
            validate_identity(row)
        except (IdentityValidationError, TypeError) as error:
            _store_error(
                ActivationStoreErrorCode.INVALID_ROW,
                f"universal identity validation failed: {error}",
            )
        key = ActivationRowKey.from_row(row)
        if (
            row.get("status") != "accepted"
            or row.get("exclusion_reason") is not None
            or row.get("superseded_by") is not None
        ):
            _store_error(
                ActivationStoreErrorCode.INVALID_STATE,
                "candidate rows must have accepted lifecycle state",
            )
        required_matches = {
            "accepted_manifest_hash": identity.accepted_manifest_hash,
            "checkpoint_hash": identity.checkpoint_hash,
            "code_sha": identity.code_sha,
            "config_hash": identity.config_hash,
            "hook_site": identity.hook_site,
            "model_hash": identity.model_hash,
            "preprocess_hash": identity.preprocess_hash,
            "run_id": identity.run_id,
            "schema_version": identity.schema_version,
        }
        for field, expected in required_matches.items():
            if row.get(field) != expected:
                _store_error(
                    ActivationStoreErrorCode.IDENTITY_CONFLICT,
                    f"candidate row expected {expected!r}",
                    field=field,
                )
        if key.layer_idx not in identity.requested_layers:
            _store_error(
                ActivationStoreErrorCode.IDENTITY_CONFLICT,
                "candidate layer is not in requested_layers",
                field="layer_idx",
            )
        positions = row.get("frame_token_positions")
        model_frame_idx = row["model_frame_idx"]
        expected_positions = list(
            range(
                model_frame_idx * 347,
                model_frame_idx * 347 + VISUAL_TOKENS_PER_FRAME,
            )
        )
        if (
            not isinstance(positions, list)
            or len(positions) != VISUAL_TOKENS_PER_FRAME
            or positions != expected_positions
            or model_frame_idx >= 16
        ):
            _store_error(
                ActivationStoreErrorCode.INVALID_ROW,
                "candidate row visual positions do not match the frozen layout",
                field="frame_token_positions",
            )
        normalized_rows.append(row)
        keys.append(key)
    if len(set(keys)) != len(keys):
        _store_error(
            ActivationStoreErrorCode.INVALID_ROW,
            "duplicate scientific activation key in candidate rows",
        )
    layers = {key.layer_idx for key in keys}
    if len(layers) != 1:
        _store_error(
            ActivationStoreErrorCode.INVALID_CHUNK,
            "each v1 chunk must contain one homogeneous layer",
        )
    order = sorted(range(len(keys)), key=keys.__getitem__)
    sorted_rows = [normalized_rows[index] for index in order]
    sorted_keys = [keys[index] for index in order]
    sorted_vectors = numpy.ascontiguousarray(candidate_array[order])
    return sorted_rows, sorted_vectors, sorted_keys


def _npy_bytes(array: object) -> bytes:
    numpy = _numpy_module()
    stream = io.BytesIO()
    numpy.save(stream, array, allow_pickle=False)
    return stream.getvalue()


def _validate_temporary_npy(
    path: Path,
    *,
    row_count: int,
    hidden_width: int,
    dtype: str,
) -> None:
    if path.stat().st_size > MAX_ACTIVATION_CHUNK_BYTES:
        _store_error(
            ActivationStoreErrorCode.LIMIT_EXCEEDED,
            f"temporary chunk exceeds reviewed byte limit "
            f"{MAX_ACTIVATION_CHUNK_BYTES}",
            path=path,
        )
    numpy = _numpy_module()
    try:
        array = numpy.load(path, allow_pickle=False)
    except (OSError, ValueError, TypeError) as error:
        _store_error(
            ActivationStoreErrorCode.INVALID_CHUNK,
            f"temporary .npy validation failed: {error}",
            path=path,
        )
    if (
        not isinstance(array, numpy.ndarray)
        or array.ndim != 2
        or array.shape != (row_count, hidden_width)
        or array.dtype.name != dtype
        or array.dtype.hasobject
        or not array.flags.c_contiguous
        or not numpy.issubdtype(array.dtype, numpy.floating)
        or not bool(numpy.isfinite(array).all())
    ):
        _store_error(
            ActivationStoreErrorCode.INVALID_CHUNK,
            "temporary .npy inventory is invalid",
            path=path,
        )


def _write_and_validate_chunk_temporary(
    destination: Path,
    payload: bytes,
    *,
    row_count: int,
    hidden_width: int,
    dtype: str,
    fault_point: ActivationPublicationFaultPoint | None,
) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=destination.parent,
        prefix=f".{destination.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            if fault_point == ActivationPublicationFaultPoint.DURING_TEMPORARY_CHUNK:
                stream.write(payload[: max(1, len(payload) // 2)])
                stream.flush()
                os.fsync(stream.fileno())
                _raise_for_fault(
                    fault_point,
                    ActivationPublicationFaultPoint.DURING_TEMPORARY_CHUNK,
                )
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        _validate_temporary_npy(
            temporary,
            row_count=row_count,
            hidden_width=hidden_width,
            dtype=dtype,
        )
        _raise_for_fault(
            fault_point,
            ActivationPublicationFaultPoint.AFTER_TEMPORARY_CHUNK_VALIDATION,
        )
        return temporary
    except BaseException as primary_error:
        try:
            temporary.unlink(missing_ok=True)
        except OSError as cleanup_error:
            cleanup = ActivationStoreError(
                ActivationStoreErrorCode.PUBLICATION_FAILED,
                f"temporary chunk cleanup failed: {cleanup_error}",
                path=temporary,
            )
            cleanup.__cause__ = cleanup_error
            primary_error.cleanup_error = cleanup  # type: ignore[attr-defined]
            if hasattr(primary_error, "add_note"):
                primary_error.add_note(str(cleanup))
            primary_error.__context__ = cleanup
        raise


def _publish_validated_temporary(
    temporary: Path,
    destination: Path,
    expected_payload: bytes,
) -> bool:
    published = False
    primary_error: BaseException | None = None
    try:
        try:
            os.link(temporary, destination)
            published = True
        except FileExistsError:
            if destination.is_symlink():
                _store_error(
                    ActivationStoreErrorCode.UNSAFE_PATH,
                    "existing immutable chunk must not be a symbolic link",
                    path=destination,
                )
            try:
                existing = destination.read_bytes()
            except OSError as error:
                _store_error(
                    ActivationStoreErrorCode.OUTPUT_EXISTS,
                    f"could not validate existing immutable chunk: {error}",
                    path=destination,
                )
            if existing != expected_payload:
                _store_error(
                    ActivationStoreErrorCode.IDENTITY_CONFLICT,
                    "existing chunk path contains conflicting orphan bytes",
                    path=destination,
                )
            published = False
        except OSError as error:
            _store_error(
                ActivationStoreErrorCode.PUBLICATION_FAILED,
                f"exclusive hard-link publication failed: {error}",
                path=destination,
            )
    except BaseException as error:
        primary_error = error
        raise
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError as cleanup_error:
            cleanup = ActivationStoreError(
                ActivationStoreErrorCode.PUBLICATION_FAILED,
                f"temporary chunk cleanup failed: {cleanup_error}",
                path=temporary,
            )
            cleanup.__cause__ = cleanup_error
            if primary_error is not None:
                primary_error.cleanup_error = cleanup  # type: ignore[attr-defined]
                if hasattr(primary_error, "add_note"):
                    primary_error.add_note(str(cleanup))
                primary_error.__context__ = cleanup
            else:
                raise cleanup
    return published


def publish_activation_chunk(
    *,
    store_root: Path | str,
    store_identity: ActivationStoreIdentity,
    rows: Sequence[Mapping[str, Any]],
    vectors: object,
    creation_timestamp: str,
    accepted_manifest_rows: Sequence[Mapping[str, Any]] | None = None,
    eligibility_proof: ActivationEligibilityProof | None = None,
    prior_snapshot: ActivationIndexSnapshot | None = None,
    fault_point: ActivationPublicationFaultPoint | None = None,
) -> ActivationIndexSnapshot:
    """Publish one pooled chunk and the next immutable accepted index."""

    if not isinstance(store_identity, ActivationStoreIdentity):
        _store_error(
            ActivationStoreErrorCode.INVALID_IDENTITY,
            "store_identity must be ActivationStoreIdentity",
        )
    if store_identity.model_hash != store_identity.checkpoint_hash:
        _store_error(
            ActivationStoreErrorCode.IDENTITY_CONFLICT,
            "frozen activation handoff requires model_hash=checkpoint_hash",
        )
    _phase5_require_timestamp(creation_timestamp, "creation_timestamp")
    if fault_point is not None and not isinstance(
        fault_point, ActivationPublicationFaultPoint
    ):
        _store_error(
            ActivationStoreErrorCode.INVALID_STATE,
            "fault_point must be ActivationPublicationFaultPoint",
        )
    root = Path(store_root)
    if not root.is_dir() or root.is_symlink():
        _store_error(
            ActivationStoreErrorCode.UNSAFE_PATH,
            "store_root must be an existing ordinary directory",
            path=root,
        )
    if accepted_manifest_rows is None:
        _store_error(
            ActivationStoreErrorCode.ELIGIBILITY_CONFLICT,
            "authoritative accepted_manifest_rows are required; a "
            "caller-created eligibility proof is not publication authority; "
            "accepted_manifest_hash="
            f"{store_identity.accepted_manifest_hash}; "
            f"candidate_key={_candidate_key_diagnostic(rows)!r}",
            field="accepted_manifest_rows",
        )
    authoritative_proof = build_activation_eligibility_proof(
        store_identity=store_identity,
        accepted_manifest_rows=accepted_manifest_rows,
    )
    _validate_claimed_eligibility_proof(
        authoritative=authoritative_proof,
        claimed=eligibility_proof,
        candidate_key=_candidate_key_diagnostic(rows),
    )
    if prior_snapshot is not None:
        validate_activation_index_snapshot(
            prior_snapshot,
            store_root=root,
        )
        if prior_snapshot.store_identity != store_identity:
            _store_error(
                ActivationStoreErrorCode.IDENTITY_CONFLICT,
                "prior snapshot has a different complete store identity",
            )
    candidate_rows, candidate_vectors, row_keys = _candidate_rows_and_vectors(
        identity=store_identity,
        rows=rows,
        vectors=vectors,
    )
    _validate_candidate_eligibility(
        identity=store_identity,
        proof=authoritative_proof,
        rows=candidate_rows,
    )
    previous_chunks = () if prior_snapshot is None else prior_snapshot.chunks
    previous_rows = () if prior_snapshot is None else prior_snapshot.index_rows
    if len(previous_chunks) + 1 > MAX_ACTIVATION_CHUNKS_PER_SNAPSHOT:
        _store_error(
            ActivationStoreErrorCode.LIMIT_EXCEEDED,
            "publication would exceed snapshot chunk-count limit",
            field="chunks",
        )
    if len(previous_rows) + len(row_keys) > MAX_ACTIVATION_INDEX_ROWS:
        _store_error(
            ActivationStoreErrorCode.LIMIT_EXCEEDED,
            "publication would exceed snapshot row-count limit",
            field="index_rows",
        )
    chunk_identity = ActivationChunkIdentity(
        store_identity=store_identity,
        layer_idx=row_keys[0].layer_idx,
        first_row_key=row_keys[0],
        last_row_key=row_keys[-1],
        row_count=len(row_keys),
        dtype=store_identity.dtype,
        hidden_width=store_identity.hidden_width,
    )
    chunk_identity_digest = chunk_identity.digest
    chunk_id = f"activation-chunk-{chunk_identity_digest[:24]}"
    relative_path = f"chunks/{chunk_id}.npy"
    chunk_path = _resolve_store_path(root, relative_path)
    payload = _npy_bytes(candidate_vectors)
    if len(payload) > MAX_ACTIVATION_CHUNK_BYTES:
        _store_error(
            ActivationStoreErrorCode.LIMIT_EXCEEDED,
            "candidate serialized chunk exceeds reviewed byte limit",
            field="vectors",
        )
    if (
        sum(chunk.byte_size for chunk in previous_chunks) + len(payload)
        > MAX_ACTIVATION_SNAPSHOT_REFERENCED_BYTES
    ):
        _store_error(
            ActivationStoreErrorCode.LIMIT_EXCEEDED,
            "publication would exceed snapshot referenced-byte limit",
            field="chunks",
        )
    _ensure_run_identity_binding(
        store_root=root,
        identity=store_identity,
        eligibility_proof=authoritative_proof,
        fault_point=fault_point,
    )
    _raise_for_fault(
        fault_point,
        ActivationPublicationFaultPoint.BEFORE_TEMPORARY_CHUNK,
    )
    temporary = _write_and_validate_chunk_temporary(
        chunk_path,
        payload,
        row_count=len(row_keys),
        hidden_width=store_identity.hidden_width,
        dtype=store_identity.dtype,
        fault_point=fault_point,
    )
    if (
        temporary.stat().st_size != len(payload)
        or _sha256_file(temporary) != _sha256_bytes(payload)
    ):
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        _store_error(
            ActivationStoreErrorCode.CHECKSUM_MISMATCH,
            "temporary persisted bytes do not match the candidate .npy bytes",
            path=temporary,
        )
    _publish_validated_temporary(temporary, chunk_path, payload)
    chunk_record = ActivationChunkRecord(
        chunk_id=chunk_id,
        chunk_identity=chunk_identity,
        chunk_identity_digest=chunk_identity_digest,
        relative_path=relative_path,
        row_count=len(row_keys),
        hidden_width=store_identity.hidden_width,
        vector_shape=(store_identity.hidden_width,),
        dtype=store_identity.dtype,
        byte_size=chunk_path.stat().st_size,
        sha256=_sha256_file(chunk_path),
        creation_timestamp=creation_timestamp,
        operational_status="completed",
    )
    _validate_persisted_chunk(root, chunk_record, store_identity)
    _raise_for_fault(
        fault_point,
        ActivationPublicationFaultPoint.AFTER_FINAL_CHUNK_PUBLICATION,
    )
    materialized: list[dict[str, Any]] = []
    for offset, source in enumerate(candidate_rows):
        row = dict(source)
        row.update(
            {
                "activation_chunk_id": chunk_id,
                "chunk_row_idx": offset,
                "dtype": store_identity.dtype,
                "pooling_method": "mean",
                "run_status": "completed",
                "token_region": "visual",
                "vector_shape": [store_identity.hidden_width],
            }
        )
        _validate_index_row(row, store_identity)
        materialized.append(row)
    combined_chunks = tuple(
        sorted((*previous_chunks, chunk_record), key=lambda item: item.chunk_id)
    )
    combined_rows = tuple(
        sorted(
            (dict(row) for row in (*previous_rows, *materialized)),
            key=ActivationRowKey.from_row,
        )
    )
    prototype = ActivationIndexSnapshot(
        snapshot_id="0" * 64,
        store_identity=store_identity,
        run_status="completed",
        creation_timestamp=creation_timestamp,
        chunks=combined_chunks,
        index_rows=combined_rows,
    )
    snapshot = ActivationIndexSnapshot(
        snapshot_id=_canonical_digest(_snapshot_identity_document(prototype)),
        store_identity=store_identity,
        run_status="completed",
        creation_timestamp=creation_timestamp,
        chunks=combined_chunks,
        index_rows=combined_rows,
    )
    validate_activation_index_snapshot(snapshot, store_root=root)
    _raise_for_fault(
        fault_point,
        ActivationPublicationFaultPoint.AFTER_INDEX_CONSTRUCTION,
    )
    index_path = _resolve_store_path(root, snapshot.relative_path)
    index_payload = _canonical_json_bytes(snapshot.to_document())
    _publish_exact_bytes(
        index_path,
        index_payload,
        fault_during=(
            fault_point
            == ActivationPublicationFaultPoint.DURING_INDEX_PUBLICATION
        ),
    )
    loaded = load_activation_index_snapshot(index_path, store_root=root)
    _raise_for_fault(
        fault_point,
        ActivationPublicationFaultPoint.AFTER_INDEX_PUBLICATION,
    )
    return loaded


def plan_activation_resume(
    *,
    store_root: Path | str,
    requested_identity: ActivationStoreIdentity,
    snapshot: ActivationIndexSnapshot,
    expected_rows: Mapping[ActivationRowKey, Mapping[str, Any]],
) -> ActivationResumePlan:
    """Plan an idempotent resume from one explicitly selected snapshot."""

    validate_activation_index_snapshot(snapshot, store_root=store_root)
    if snapshot.store_identity != requested_identity:
        _store_error(
            ActivationStoreErrorCode.RESUME_CONFLICT,
            "resume requires an exact complete store/run identity match",
        )
    if not isinstance(expected_rows, Mapping):
        _store_error(
            ActivationStoreErrorCode.INVALID_ROW,
            "expected_rows must map ActivationRowKey to metadata",
        )
    completed = {
        ActivationRowKey.from_row(row): row for row in snapshot.index_rows
    }
    skip: list[ActivationRowKey] = []
    retry: list[ActivationRowKey] = []
    conflicts: list[ActivationRowKey] = []
    excluded: list[ActivationRowKey] = []
    for key, metadata in sorted(expected_rows.items()):
        if not isinstance(key, ActivationRowKey) or not isinstance(
            metadata, Mapping
        ):
            _store_error(
                ActivationStoreErrorCode.INVALID_ROW,
                "resume keys and metadata have invalid types",
            )
        expected_identity = {
            "accepted_manifest_hash": requested_identity.accepted_manifest_hash,
            "checkpoint_hash": requested_identity.checkpoint_hash,
            "code_sha": requested_identity.code_sha,
            "config_hash": requested_identity.config_hash,
            "dtype": requested_identity.dtype,
            "hook_site": requested_identity.hook_site,
            "layer_idx": key.layer_idx,
            "model_hash": requested_identity.model_hash,
            "model_frame_idx": key.model_frame_idx,
            "preprocess_hash": requested_identity.preprocess_hash,
            "run_id": requested_identity.run_id,
            "schema_version": requested_identity.schema_version,
            "trajectory_id": key.trajectory_id,
        }
        if (
            key.producing_run_id != requested_identity.run_id
            or key.hook_site != requested_identity.hook_site
            or key.layer_idx not in requested_identity.requested_layers
            or any(
            metadata.get(field) != expected
            for field, expected in expected_identity.items()
            )
        ):
            conflicts.append(key)
            continue
        if tuple(metadata.get("vector_shape", ())) != (
            requested_identity.hidden_width,
        ):
            conflicts.append(key)
            continue
        lifecycle = metadata.get("status", "accepted")
        operational = metadata.get("operational_status", "pending")
        if lifecycle not in ACTIVATION_ANALYSIS_STATUSES:
            _store_error(
                ActivationStoreErrorCode.INVALID_STATE,
                "resume row has an invalid analysis lifecycle",
            )
        if operational not in ACTIVATION_OPERATIONAL_STATUSES:
            _store_error(
                ActivationStoreErrorCode.INVALID_STATE,
                "resume row has an invalid operational state",
            )
        stored = completed.get(key)
        if lifecycle in {"excluded", "superseded"}:
            if stored is not None:
                conflicts.append(key)
            else:
                excluded.append(key)
            continue
        if stored is None:
            if operational in {"pending", "writing", "failed"}:
                retry.append(key)
            else:
                conflicts.append(key)
            continue
        if operational != "completed":
            conflicts.append(key)
            continue
        comparable = {
            field: value
            for field, value in metadata.items()
            if field not in {"operational_status"}
        }
        if all(
            _thaw_json(stored.get(field)) == _thaw_json(value)
            for field, value in comparable.items()
        ):
            skip.append(key)
        else:
            conflicts.append(key)
    unexpected_completed = sorted(set(completed) - set(expected_rows))
    conflicts.extend(unexpected_completed)
    return ActivationResumePlan(
        skip=tuple(sorted(set(skip))),
        retry=tuple(sorted(set(retry))),
        conflicts=tuple(sorted(set(conflicts))),
        excluded=tuple(sorted(set(excluded))),
    )


def read_activation_vectors(
    *,
    store_root: Path | str,
    snapshot: ActivationIndexSnapshot,
    row_keys: Sequence[ActivationRowKey],
    promote_float16: bool = True,
) -> Any:
    """Read selected vectors without opening unrelated chunks."""

    _validate_snapshot_structure(snapshot)
    if isinstance(row_keys, (str, bytes)) or not isinstance(
        row_keys, Sequence
    ):
        _store_error(
            ActivationStoreErrorCode.READ_FAILED,
            "row_keys must be a sequence",
        )
    if any(not isinstance(key, ActivationRowKey) for key in row_keys):
        _store_error(
            ActivationStoreErrorCode.READ_FAILED,
            "every requested row key must be ActivationRowKey",
            field="row_keys",
        )
    if len(set(row_keys)) != len(row_keys):
        _store_error(
            ActivationStoreErrorCode.READ_FAILED,
            "duplicate requested scientific row key",
        )
    row_by_key = {
        ActivationRowKey.from_row(row): row for row in snapshot.index_rows
    }
    chunk_by_id = {chunk.chunk_id: chunk for chunk in snapshot.chunks}
    missing = [key for key in row_keys if key not in row_by_key]
    if missing:
        _store_error(
            ActivationStoreErrorCode.READ_FAILED,
            f"{len(missing)} requested activation rows are absent",
        )
    selected_chunk_ids = {
        str(row_by_key[key]["activation_chunk_id"]) for key in row_keys
    }
    selected_rows = len(row_keys)
    selected_chunks = len(selected_chunk_ids)
    hidden_width = snapshot.store_identity.hidden_width
    output_dtype = (
        "float32"
        if promote_float16 and snapshot.store_identity.dtype == "float16"
        else snapshot.store_identity.dtype
    )
    item_size = _ACTIVATION_DTYPE_ITEM_SIZES[output_dtype]
    if (
        selected_rows > 0
        and hidden_width
        > _MAX_SAFE_ACTIVATION_READ_INTEGER // selected_rows
    ):
        _store_error(
            ActivationStoreErrorCode.LIMIT_EXCEEDED,
            "selected activation result element count exceeds reviewed "
            "signed-64-bit arithmetic; "
            f"selected_rows={selected_rows}; "
            f"selected_chunks={selected_chunks}; "
            f"hidden_width={hidden_width}; "
            f"requested_output_dtype={output_dtype}; "
            f"row_limit={MAX_ACTIVATION_READ_ROWS}; "
            f"chunk_limit={MAX_ACTIVATION_READ_CHUNKS}; "
            f"result_byte_limit={MAX_ACTIVATION_READ_RESULT_BYTES}",
            field="row_keys",
        )
    result_elements = selected_rows * hidden_width
    if (
        result_elements > 0
        and item_size
        > _MAX_SAFE_ACTIVATION_READ_INTEGER // result_elements
    ):
        _store_error(
            ActivationStoreErrorCode.LIMIT_EXCEEDED,
            "selected activation result byte count exceeds reviewed "
            "signed-64-bit arithmetic; "
            f"selected_rows={selected_rows}; "
            f"selected_chunks={selected_chunks}; "
            f"hidden_width={hidden_width}; "
            f"requested_output_dtype={output_dtype}; "
            f"row_limit={MAX_ACTIVATION_READ_ROWS}; "
            f"chunk_limit={MAX_ACTIVATION_READ_CHUNKS}; "
            f"result_byte_limit={MAX_ACTIVATION_READ_RESULT_BYTES}",
            field="row_keys",
        )
    result_bytes = result_elements * item_size
    if (
        selected_rows > MAX_ACTIVATION_READ_ROWS
        or selected_chunks > MAX_ACTIVATION_READ_CHUNKS
        or result_bytes > MAX_ACTIVATION_READ_RESULT_BYTES
    ):
        _store_error(
            ActivationStoreErrorCode.LIMIT_EXCEEDED,
            "selected activation read exceeds reviewed single-call limits; "
            f"selected_rows={selected_rows}; "
            f"selected_chunks={selected_chunks}; "
            f"hidden_width={hidden_width}; "
            f"requested_output_dtype={output_dtype}; "
            f"calculated_result_bytes={result_bytes}; "
            f"row_limit={MAX_ACTIVATION_READ_ROWS}; "
            f"chunk_limit={MAX_ACTIVATION_READ_CHUNKS}; "
            f"result_byte_limit={MAX_ACTIVATION_READ_RESULT_BYTES}",
            field="row_keys",
        )
    numpy = _numpy_module()
    arrays: dict[str, Any] = {}
    for chunk_id in sorted(selected_chunk_ids):
        chunk = chunk_by_id[chunk_id]
        _validate_persisted_chunk(
            store_root,
            chunk,
            snapshot.store_identity,
        )
        arrays[chunk_id] = numpy.load(
            _require_ordinary_store_file(store_root, chunk.relative_path),
            allow_pickle=False,
            mmap_mode="r",
        )
    vectors = [
        arrays[str(row_by_key[key]["activation_chunk_id"])][
            int(row_by_key[key]["chunk_row_idx"])
        ]
        for key in row_keys
    ]
    if not vectors:
        dtype = (
            numpy.float32
            if promote_float16 and snapshot.store_identity.dtype == "float16"
            else numpy.dtype(snapshot.store_identity.dtype)
        )
        return numpy.empty((0, snapshot.store_identity.hidden_width), dtype=dtype)
    result = numpy.stack(vectors)
    if promote_float16 and result.dtype.name == "float16":
        result = result.astype(numpy.float32)
    return result


def _work_keys_by_state(
    work_records: Iterable[Mapping[str, Any]],
) -> tuple[
    dict[str, set[ActivationRowKey]],
    set[ActivationRowKey],
]:
    operational: dict[str, set[ActivationRowKey]] = {
        state: set() for state in ACTIVATION_OPERATIONAL_STATUSES
    }
    lifecycle_keys: set[ActivationRowKey] = set()
    for record in work_records:
        if not isinstance(record, Mapping):
            _store_error(
                ActivationStoreErrorCode.AUDIT_FAILED,
                "work records must be mappings",
            )
        try:
            validate_identity(record)
        except (IdentityValidationError, TypeError) as error:
            _store_error(
                ActivationStoreErrorCode.AUDIT_FAILED,
                f"work record identity/lifecycle is invalid: {error}",
            )
        key = ActivationRowKey.from_row(record)
        state = record.get("operational_status")
        lifecycle = record.get("status", "accepted")
        if state not in ACTIVATION_OPERATIONAL_STATUSES:
            _store_error(
                ActivationStoreErrorCode.INVALID_STATE,
                "work record has an invalid operational state",
            )
        if lifecycle not in ACTIVATION_ANALYSIS_STATUSES:
            _store_error(
                ActivationStoreErrorCode.INVALID_STATE,
                "work record has an invalid analysis lifecycle",
            )
        if state != "completed":
            reason = record.get("state_reason")
            if not isinstance(reason, str) or not reason.strip():
                _store_error(
                    ActivationStoreErrorCode.AUDIT_FAILED,
                    "non-completed work requires a non-empty state_reason",
                )
        operational[str(state)].add(key)
        if lifecycle != "accepted":
            lifecycle_keys.add(key)
    return operational, lifecycle_keys


def audit_activation_store(
    *,
    store_root: Path | str,
    snapshot: ActivationIndexSnapshot,
    accepted_manifest_rows: Sequence[Mapping[str, Any]],
    work_records: Sequence[Mapping[str, Any]] = (),
) -> ActivationStoreAudit:
    """Audit expected post-first-visible cardinality and store integrity."""

    if isinstance(accepted_manifest_rows, (str, bytes)) or not isinstance(
        accepted_manifest_rows, Sequence
    ):
        _store_error(
            ActivationStoreErrorCode.AUDIT_FAILED,
            "accepted_manifest_rows must be a sequence",
        )
    from mineocclude.analysis.filters import (
        FilterRejectionCode,
        apply_ordered_filters,
    )

    filter_result = apply_ordered_filters(
        accepted_manifest_rows,
        accepted_manifest_hash=snapshot.store_identity.accepted_manifest_hash,
    )
    accepted_frames = {
        (str(row["trajectory_id"]), int(row["model_frame_idx"]))
        for row in filter_result.accepted_rows
    }
    pre_first_frames = {
        (str(rejection.frame_key[0]), int(rejection.frame_key[1]))
        for rejection in filter_result.rejections
        if rejection.code == FilterRejectionCode.PRE_FIRST_SEEN
        and rejection.frame_key is not None
    }

    def expand(
        frames: Iterable[tuple[str, int]],
    ) -> set[ActivationRowKey]:
        return {
            ActivationRowKey(
                trajectory_id=trajectory_id,
                model_frame_idx=model_frame_idx,
                layer_idx=layer_idx,
                hook_site=snapshot.store_identity.hook_site,
                producing_run_id=snapshot.store_identity.run_id,
            )
            for trajectory_id, model_frame_idx in frames
            for layer_idx in snapshot.store_identity.requested_layers
        }

    expected = expand(accepted_frames)
    all_pre_first = expand(pre_first_frames)
    observed_keys: list[ActivationRowKey] = []
    identity_mismatches: set[str] = set()
    integrity_by_key: dict[ActivationRowKey, set[str]] = {}
    references: list[tuple[str, int]] = []
    corrupt_chunks: set[str] = set()
    checksum_mismatches: set[str] = set()
    byte_size_mismatches: set[str] = set()
    dtype_mismatches: set[str] = set()
    shape_mismatches: set[str] = set()
    row_count_mismatches: set[str] = set()
    chunk_by_id: dict[str, ActivationChunkRecord] = {}
    valid_chunk_ids: set[str] = set()
    for chunk in snapshot.chunks:
        if chunk.chunk_id in chunk_by_id:
            identity_mismatches.add(
                f"chunk[{chunk.chunk_id}]: duplicate chunk identifier"
            )
            corrupt_chunks.add(chunk.chunk_id)
            continue
        chunk_by_id[chunk.chunk_id] = chunk
        try:
            _validate_chunk_record_metadata(chunk, snapshot.store_identity)
            chunk_path = _require_ordinary_store_file(
                store_root, chunk.relative_path
            )
        except ActivationStoreError as error:
            corrupt_chunks.add(chunk.chunk_id)
            identity_mismatches.add(f"chunk[{chunk.chunk_id}]: {error}")
            continue
        chunk_valid = True
        observed_chunk_size = chunk_path.stat().st_size
        if observed_chunk_size != chunk.byte_size:
            corrupt_chunks.add(chunk.chunk_id)
            byte_size_mismatches.add(chunk.chunk_id)
            chunk_valid = False
        if observed_chunk_size > MAX_ACTIVATION_CHUNK_BYTES:
            corrupt_chunks.add(chunk.chunk_id)
            byte_size_mismatches.add(chunk.chunk_id)
            identity_mismatches.add(
                f"chunk[{chunk.chunk_id}]: persisted bytes exceed reviewed limit"
            )
            continue
        if _sha256_file(chunk_path) != chunk.sha256:
            corrupt_chunks.add(chunk.chunk_id)
            checksum_mismatches.add(chunk.chunk_id)
            chunk_valid = False
        try:
            array = _numpy_module().load(chunk_path, allow_pickle=False)
        except (OSError, ValueError, TypeError) as error:
            corrupt_chunks.add(chunk.chunk_id)
            identity_mismatches.add(
                f"chunk[{chunk.chunk_id}]: could not load .npy: {error}"
            )
            continue
        if array.ndim != 2:
            corrupt_chunks.add(chunk.chunk_id)
            shape_mismatches.add(chunk.chunk_id)
            chunk_valid = False
        elif array.shape[0] != chunk.row_count:
            corrupt_chunks.add(chunk.chunk_id)
            row_count_mismatches.add(chunk.chunk_id)
            chunk_valid = False
        if array.ndim == 2 and array.shape[1:] != (chunk.hidden_width,):
            corrupt_chunks.add(chunk.chunk_id)
            shape_mismatches.add(chunk.chunk_id)
            chunk_valid = False
        if array.dtype.name != chunk.dtype:
            corrupt_chunks.add(chunk.chunk_id)
            dtype_mismatches.add(chunk.chunk_id)
            chunk_valid = False
        numpy = _numpy_module()
        if (
            array.dtype.hasobject
            or not numpy.issubdtype(array.dtype, numpy.floating)
            or not array.flags.c_contiguous
            or (
                numpy.issubdtype(array.dtype, numpy.number)
                and not bool(numpy.isfinite(array).all())
            )
        ):
            corrupt_chunks.add(chunk.chunk_id)
            identity_mismatches.add(
                f"chunk[{chunk.chunk_id}]: array safety constraints failed"
            )
            chunk_valid = False
        if chunk_valid:
            valid_chunk_ids.add(chunk.chunk_id)

    unknown_referenced_chunks: set[str] = set()
    out_of_bounds_references: set[tuple[str, int]] = set()
    row_chunk_layer_mismatches: set[ActivationRowKey] = set()
    row_chunk_dtype_mismatches: set[ActivationRowKey] = set()
    row_chunk_shape_mismatches: set[ActivationRowKey] = set()
    row_store_hook_mismatches: set[ActivationRowKey] = set()
    row_store_run_mismatches: set[ActivationRowKey] = set()
    rows_by_chunk: dict[
        str, list[tuple[ActivationRowKey, int, bool]]
    ] = {}
    for index, row in enumerate(snapshot.index_rows):
        try:
            key = ActivationRowKey.from_row(row)
        except (ActivationStoreError, TypeError, ValueError) as error:
            identity_mismatches.add(f"index_rows[{index}]: {error}")
            continue
        observed_keys.append(key)
        row_valid = True
        if key.hook_site != snapshot.store_identity.hook_site:
            row_store_hook_mismatches.add(key)
            integrity_by_key.setdefault(key, set()).add(
                "row hook_site disagrees with store identity"
            )
            row_valid = False
        if key.producing_run_id != snapshot.store_identity.run_id:
            row_store_run_mismatches.add(key)
            integrity_by_key.setdefault(key, set()).add(
                "row run_id disagrees with store identity"
            )
            row_valid = False
        try:
            _validate_index_row(row, snapshot.store_identity)
        except (ActivationStoreError, TypeError, ValueError) as error:
            identity_mismatches.add(f"index_rows[{index}]: {error}")
            integrity_by_key.setdefault(key, set()).add(str(error))
            row_valid = False
        chunk_id_value = row.get("activation_chunk_id")
        offset_value = row.get("chunk_row_idx")
        if (
            not isinstance(chunk_id_value, str)
            or not isinstance(offset_value, int)
            or isinstance(offset_value, bool)
        ):
            identity_mismatches.add(
                f"index_rows[{index}]: invalid chunk reference"
            )
            integrity_by_key.setdefault(key, set()).add(
                "invalid chunk identifier or row offset"
            )
            continue
        chunk_id = chunk_id_value
        offset = offset_value
        reference = (chunk_id, offset)
        references.append(reference)
        chunk = chunk_by_id.get(chunk_id)
        if chunk is None:
            unknown_referenced_chunks.add(chunk_id)
            integrity_by_key.setdefault(key, set()).add(
                f"unknown referenced chunk {chunk_id!r}"
            )
            continue
        if offset < 0 or offset >= chunk.row_count:
            out_of_bounds_references.add(reference)
            integrity_by_key.setdefault(key, set()).add(
                f"chunk row offset {offset} is out of bounds"
            )
            row_valid = False
        if key.layer_idx != chunk.chunk_identity.layer_idx:
            row_chunk_layer_mismatches.add(key)
            integrity_by_key.setdefault(key, set()).add(
                "row layer disagrees with homogeneous chunk layer"
            )
            row_valid = False
        if row.get("dtype") != chunk.dtype:
            row_chunk_dtype_mismatches.add(key)
            integrity_by_key.setdefault(key, set()).add(
                "row dtype disagrees with chunk dtype"
            )
            row_valid = False
        if tuple(row.get("vector_shape", ())) != chunk.vector_shape:
            row_chunk_shape_mismatches.add(key)
            integrity_by_key.setdefault(key, set()).add(
                "row vector shape disagrees with chunk vector shape"
            )
            row_valid = False
        rows_by_chunk.setdefault(chunk_id, []).append((key, offset, row_valid))

    key_counts = Counter(observed_keys)
    reference_counts = Counter(references)
    duplicate_keys = {
        key for key, count in key_counts.items() if count > 1
    }
    duplicate_references = {
        reference
        for reference, count in reference_counts.items()
        if count > 1
    }
    incomplete_chunk_offsets: set[str] = set()
    chunk_row_range_mismatches: set[str] = set()
    referenced_row_count_mismatches: set[str] = set()
    invalid_binding_chunks: set[str] = set()
    completed: set[ActivationRowKey] = set()
    for chunk_id, chunk in chunk_by_id.items():
        bound = rows_by_chunk.get(chunk_id, [])
        bound_keys = [key for key, _offset, _valid in bound]
        offsets = [offset for _key, offset, _valid in bound]
        if len(bound) != chunk.row_count:
            referenced_row_count_mismatches.add(chunk_id)
            invalid_binding_chunks.add(chunk_id)
        if set(offsets) != set(range(chunk.row_count)):
            incomplete_chunk_offsets.add(chunk_id)
            invalid_binding_chunks.add(chunk_id)
        if (
            len(set(bound_keys)) != chunk.chunk_identity.row_count
            or not bound_keys
            or min(bound_keys) != chunk.chunk_identity.first_row_key
            or max(bound_keys) != chunk.chunk_identity.last_row_key
        ):
            chunk_row_range_mismatches.add(chunk_id)
            invalid_binding_chunks.add(chunk_id)
        if any(
            reference_counts[(chunk_id, offset)] != 1
            for offset in set(offsets)
        ):
            invalid_binding_chunks.add(chunk_id)
        if chunk_id not in valid_chunk_ids:
            invalid_binding_chunks.add(chunk_id)
        if chunk_id in invalid_binding_chunks:
            reason = f"chunk {chunk_id!r} failed integrity or row binding"
            for key in bound_keys:
                integrity_by_key.setdefault(key, set()).add(reason)
            continue
        for key, _offset, row_valid in bound:
            if row_valid and key not in duplicate_keys:
                completed.add(key)

    operational, lifecycle_nonaccepted = _work_keys_by_state(work_records)
    work_by_key: dict[ActivationRowKey, Mapping[str, Any]] = {}
    for record in work_records:
        key = ActivationRowKey.from_row(record)
        if key in work_by_key:
            identity_mismatches.add(f"work_records: duplicate key {key}")
        else:
            work_by_key[key] = record
    excluded_keys = {
        ActivationRowKey.from_row(row)
        for row in work_records
        if row.get("status") == "excluded"
    }
    superseded_keys = {
        ActivationRowKey.from_row(row)
        for row in work_records
        if row.get("status") == "superseded"
    }
    referenced_paths = {chunk.relative_path for chunk in snapshot.chunks}
    orphan_paths = set()
    try:
        chunks_directory = _resolve_store_path(store_root, "chunks")
    except ActivationStoreError as error:
        identity_mismatches.add(
            f"orphan discovery: unsafe chunks directory: {error}"
        )
        chunks_directory = None
    if chunks_directory is not None and chunks_directory.is_dir():
        for path in chunks_directory.iterdir():
            if path.suffix != ".npy":
                continue
            relative = path.relative_to(Path(store_root).absolute()).as_posix()
            if path.is_symlink():
                corrupt_chunks.add(relative)
                identity_mismatches.add(
                    f"orphan discovery: symbolic-link chunk {relative!r}"
                )
            elif path.is_file() and relative not in referenced_paths:
                orphan_paths.add(relative)
    conflicting = duplicate_keys | (
        completed & operational["completed"] & lifecycle_nonaccepted
    )
    missing = expected - completed
    observed_or_work = set(observed_keys) | set(work_by_key)
    pre_first = all_pre_first & observed_or_work
    shortfalls: list[ActivationShortfallReason] = []
    for key in sorted(missing):
        work = work_by_key.get(key)
        integrity_reasons = sorted(integrity_by_key.get(key, ()))
        if work is not None:
            operational_status = str(work.get("operational_status"))
            lifecycle_status = str(work.get("status"))
            state_reason = work.get("state_reason")
            exclusion_reason = work.get("exclusion_reason")
            superseded_by = work.get("superseded_by")
            if isinstance(state_reason, str) and state_reason.strip():
                reason = state_reason
                source = "work_record"
            elif isinstance(exclusion_reason, str) and exclusion_reason.strip():
                reason = exclusion_reason
                source = "work_record"
            elif isinstance(superseded_by, str) and superseded_by.strip():
                reason = f"superseded_by={superseded_by}"
                source = "work_record"
            elif integrity_reasons:
                reason = "; ".join(integrity_reasons)
                source = "integrity"
            else:
                reason = "completed claim has no validated accepted stored row"
                source = "work_record_conflict"
        elif integrity_reasons:
            operational_status = "completed"
            lifecycle_status = "accepted"
            reason = "; ".join(integrity_reasons)
            source = "integrity"
        else:
            operational_status = "missing"
            lifecycle_status = "accepted"
            reason = "no validated completed row or explicit work status"
            source = "unexplained_missing"
        shortfalls.append(
            ActivationShortfallReason(
                row_key=key,
                operational_status=operational_status,
                lifecycle_status=lifecycle_status,
                reason=reason,
                source_classification=source,
            )
        )
    return ActivationStoreAudit(
        expected_keys=tuple(sorted(expected)),
        completed_accepted_keys=tuple(sorted(completed)),
        missing_keys=tuple(sorted(missing)),
        duplicate_scientific_keys=tuple(sorted(duplicate_keys)),
        duplicate_chunk_row_references=tuple(sorted(duplicate_references)),
        unexpected_keys=tuple(sorted(completed - expected)),
        pre_first_seen_keys=tuple(sorted(pre_first)),
        corrupt_chunks=tuple(sorted(corrupt_chunks)),
        checksum_mismatches=tuple(sorted(checksum_mismatches)),
        byte_size_mismatches=tuple(sorted(byte_size_mismatches)),
        dtype_mismatches=tuple(sorted(dtype_mismatches)),
        shape_mismatches=tuple(sorted(shape_mismatches)),
        row_count_mismatches=tuple(sorted(row_count_mismatches)),
        identity_mismatches=tuple(sorted(identity_mismatches)),
        pending_keys=tuple(sorted(operational["pending"])),
        writing_keys=tuple(sorted(operational["writing"])),
        failed_keys=tuple(sorted(operational["failed"])),
        excluded_keys=tuple(sorted(excluded_keys)),
        superseded_keys=tuple(sorted(superseded_keys)),
        immutable_orphan_chunks=tuple(sorted(orphan_paths)),
        conflicting_completed_keys=tuple(sorted(conflicting)),
        unknown_referenced_chunks=tuple(sorted(unknown_referenced_chunks)),
        out_of_bounds_references=tuple(sorted(out_of_bounds_references)),
        incomplete_chunk_offsets=tuple(sorted(incomplete_chunk_offsets)),
        row_chunk_layer_mismatches=tuple(
            sorted(row_chunk_layer_mismatches)
        ),
        row_chunk_dtype_mismatches=tuple(
            sorted(row_chunk_dtype_mismatches)
        ),
        row_chunk_shape_mismatches=tuple(
            sorted(row_chunk_shape_mismatches)
        ),
        row_store_hook_mismatches=tuple(sorted(row_store_hook_mismatches)),
        row_store_run_mismatches=tuple(sorted(row_store_run_mismatches)),
        chunk_row_range_mismatches=tuple(
            sorted(chunk_row_range_mismatches)
        ),
        referenced_row_count_mismatches=tuple(
            sorted(referenced_row_count_mismatches)
        ),
        shortfall_reasons=tuple(shortfalls),
    )


__all__ = [
    "ACTIVATION_ANALYSIS_STATUSES",
    "ACTIVATION_CHUNK_TIMESTAMP_SEMANTICS",
    "ACTIVATION_ELIGIBILITY_FORMAT_VERSION",
    "ACTIVATION_INDEX_FORMAT_VERSION",
    "ACTIVATION_OPERATIONAL_STATUSES",
    "ACTIVATION_RUN_BINDING_FORMAT_VERSION",
    "ACTIVATION_STORE_FORMAT_VERSION",
    "LIMITED_UNPOOLED_ARTIFACT_VERSION",
    "LIMITED_UNPOOLED_CLASSIFICATION",
    "MAX_ACTIVATION_CHUNKS_PER_SNAPSHOT",
    "MAX_ACTIVATION_CHUNK_BYTES",
    "MAX_ACTIVATION_HIDDEN_WIDTH",
    "MAX_ACTIVATION_INDEX_JSON_BYTES",
    "MAX_ACTIVATION_INDEX_ROWS",
    "MAX_ACTIVATION_READ_CHUNKS",
    "MAX_ACTIVATION_READ_RESULT_BYTES",
    "MAX_ACTIVATION_READ_ROWS",
    "MAX_ACTIVATION_ROWS_PER_CHUNK",
    "MAX_ACTIVATION_RUN_BINDING_BYTES",
    "MAX_ACTIVATION_SNAPSHOT_REFERENCED_BYTES",
    "MAX_UNPOOLED_ARTIFACT_SIZE_BYTES",
    "SUPPORTED_ACTIVATION_STORE_DTYPES",
    "UNPOOLED_REPRODUCTION_ATOL",
    "UNPOOLED_REPRODUCTION_RTOL",
    "ActivationChunkIdentity",
    "ActivationChunkRecord",
    "ActivationEligibilityProof",
    "ActivationExtractionError",
    "ActivationIndexSnapshot",
    "ActivationPublicationFaultPoint",
    "ActivationResumePlan",
    "ActivationRowKey",
    "ActivationShortfallReason",
    "ActivationStoreAudit",
    "ActivationStoreError",
    "ActivationStoreErrorCode",
    "ActivationStoreIdentity",
    "CaptureSetFacts",
    "ExtractionErrorCode",
    "LimitedUnpooledPilot",
    "UnpooledPilotIdentity",
    "audit_activation_store",
    "build_activation_eligibility_proof",
    "extract_complete_pooled_context",
    "load_activation_index_snapshot",
    "plan_activation_resume",
    "publish_activation_chunk",
    "read_activation_vectors",
    "validate_activation_index_snapshot",
    "validate_complete_capture_set",
    "validate_limited_unpooled_pilot",
    "write_limited_unpooled_pilot",
]
