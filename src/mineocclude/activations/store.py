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
import zipfile
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
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
from mineocclude.contracts.activation import VISUAL_TOKENS_PER_FRAME
from mineocclude.contracts.identity import SCHEMA_VERSION
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


__all__ = [
    "LIMITED_UNPOOLED_ARTIFACT_VERSION",
    "LIMITED_UNPOOLED_CLASSIFICATION",
    "MAX_UNPOOLED_ARTIFACT_SIZE_BYTES",
    "UNPOOLED_REPRODUCTION_ATOL",
    "UNPOOLED_REPRODUCTION_RTOL",
    "ActivationExtractionError",
    "CaptureSetFacts",
    "ExtractionErrorCode",
    "LimitedUnpooledPilot",
    "UnpooledPilotIdentity",
    "extract_complete_pooled_context",
    "validate_complete_capture_set",
    "validate_limited_unpooled_pilot",
    "write_limited_unpooled_pilot",
]
