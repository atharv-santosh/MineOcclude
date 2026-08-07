"""Additive Phase 6 activation store with separate frame identities.

The Phase 5 ``store`` module remains the only implementation of the historical
v1 formats.  This module does not reinterpret v1 rows: it introduces explicit
v2 format dispatch and keeps global source-frame identity separate from the
pair position inside one 16-pair MineWorld context.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Any

from mineocclude.activations.hooks import EXPECTED_DECODER_LAYER_COUNT
from mineocclude.contracts.activation import VISUAL_TOKENS_PER_FRAME
from mineocclude.contracts.identity import SCHEMA_VERSION
from mineocclude.models.mineworld_adapter import FrameTokenMap

ACTIVATION_STORE_V2_FORMAT_VERSION = "person-a-activation-store-v2"
ACTIVATION_INDEX_V2_FORMAT_VERSION = "person-a-activation-index-v2"
ACTIVATION_SOURCE_BINDING_V2_FORMAT_VERSION = (
    "person-a-activation-source-binding-v2"
)
ACTIVATION_STORE_V1_FORMAT_VERSION = "person-a-activation-store-v1"
ACTIVATION_INDEX_V1_FORMAT_VERSION = "person-a-activation-index-v1"
TOKENS_PER_FRAME_ACTION_PAIR = 347
MAX_CONTEXT_PAIR_COUNT = 16
FROZEN_PHASE6_LAYERS = tuple(range(EXPECTED_DECODER_LAYER_COUNT))
SUPPORTED_DTYPES = frozenset({"float16", "float32", "float64"})
MAX_INDEX_ROWS = 2_000_000
MAX_ROWS_PER_CHUNK = 16_384
MAX_HIDDEN_WIDTH = 16_384
MAX_CHUNK_BYTES = 512 * 1024 * 1024


class ActivationStoreV2Error(ValueError):
    """Fail-closed v2 identity, publication, or dispatch error."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        field: str | None = None,
        path: Path | str | None = None,
    ) -> None:
        self.code = code
        self.field = field
        self.path = None if path is None else str(path)
        prefix = code
        if field is not None:
            prefix += f"[field={field}]"
        if path is not None:
            prefix += f"[path={path}]"
        super().__init__(f"{prefix}: {message}")


def _fail(
    code: str,
    message: str,
    *,
    field: str | None = None,
    path: Path | str | None = None,
) -> None:
    raise ActivationStoreV2Error(code, message, field=field, path=path)


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail("invalid_identity", "must be a non-empty string", field=field)
    return value


def _integer(
    value: object,
    field: str,
    *,
    minimum: int = 0,
    maximum: int | None = None,
) -> int:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or value < minimum
        or (maximum is not None and value > maximum)
    ):
        suffix = "" if maximum is None else f" and <= {maximum}"
        _fail(
            "invalid_identity",
            f"must be an integer >= {minimum}{suffix}",
            field=field,
        )
    return value


def _hex(value: object, field: str, length: int) -> str:
    if (
        not isinstance(value, str)
        or len(value) != length
        or any(character not in "0123456789abcdef" for character in value)
    ):
        _fail(
            "invalid_identity",
            f"must be a lowercase {length}-character hexadecimal value",
            field=field,
        )
    return value


def _timestamp(value: object, field: str) -> str:
    text = _text(value, field)
    if not text.endswith("Z") or "T" not in text:
        _fail(
            "invalid_identity",
            "must be an explicit ISO-8601 UTC timestamp ending in Z",
            field=field,
        )
    return text


def canonical_json_bytes(value: object) -> bytes:
    """Return the repository canonical JSON representation."""

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
        _fail("invalid_json", f"value is not canonical JSON: {error}")


def _digest(value: object) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType(
            {str(key): _freeze(item) for key, item in value.items()}
        )
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


def _safe_relative_path(value: object, field: str) -> str:
    text = _text(value, field)
    pure = PurePosixPath(text)
    if (
        "\\" in text
        or ":" in text
        or pure.is_absolute()
        or text != pure.as_posix()
        or any(part in {"", ".", ".."} for part in pure.parts)
    ):
        _fail(
            "unsafe_path",
            "must be a normalized relative POSIX path without traversal",
            field=field,
        )
    return text


def _resolve(root: Path | str, relative_path: str) -> Path:
    safe = _safe_relative_path(relative_path, "relative_path")
    lexical_root = Path(root).absolute()
    if lexical_root.is_symlink():
        _fail("unsafe_path", "store root must not be a symlink", path=root)
    destination = lexical_root.joinpath(*PurePosixPath(safe).parts)
    resolved_root = lexical_root.resolve()
    resolved_destination = destination.resolve(strict=False)
    try:
        resolved_destination.relative_to(resolved_root)
    except ValueError:
        _fail("unsafe_path", "store path escapes the root", path=destination)
    return destination


def derive_visual_token_positions(
    context_local_pair_idx: int,
) -> tuple[int, ...]:
    """Derive visual positions solely from the context-local pair identity."""

    pair_idx = _integer(
        context_local_pair_idx,
        "context_local_pair_idx",
        maximum=MAX_CONTEXT_PAIR_COUNT - 1,
    )
    start = pair_idx * TOKENS_PER_FRAME_ACTION_PAIR
    return tuple(range(start, start + VISUAL_TOKENS_PER_FRAME))


def expected_activation_row_count(
    global_model_frame_count: int,
    requested_layers: Sequence[int] = FROZEN_PHASE6_LAYERS,
) -> int:
    """Derive row cardinality from frame count and the explicit layer set."""

    frames = _integer(
        global_model_frame_count,
        "global_model_frame_count",
        minimum=1,
    )
    layers = _validated_layers(requested_layers)
    return frames * len(layers)


def _validated_layers(value: object) -> tuple[int, ...]:
    if (
        isinstance(value, (str, bytes))
        or not isinstance(value, Sequence)
        or not value
        or any(
            not isinstance(layer, int)
            or isinstance(layer, bool)
            or layer < 0
            for layer in value
        )
    ):
        _fail(
            "invalid_identity",
            "requested_layers must be a non-empty integer sequence",
            field="requested_layers",
        )
    layers = tuple(value)
    if tuple(sorted(set(layers))) != layers:
        _fail(
            "invalid_identity",
            "requested_layers must be sorted and unique",
            field="requested_layers",
        )
    return layers


@dataclass(frozen=True)
class ActivationStoreIdentityV2:
    """Complete immutable identity for one v2 pooled activation run."""

    schema_version: str
    format_version: str
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
            _fail(
                "invalid_identity",
                f"schema_version must equal {SCHEMA_VERSION!r}",
                field="schema_version",
            )
        if self.format_version != ACTIVATION_STORE_V2_FORMAT_VERSION:
            _fail(
                "invalid_identity",
                "format_version is not activation-store v2",
                field="format_version",
            )
        _text(self.run_id, "run_id")
        for field in (
            "checkpoint_hash",
            "model_hash",
            "config_hash",
            "preprocess_hash",
            "accepted_manifest_hash",
        ):
            _hex(getattr(self, field), field, 64)
        if self.model_hash != self.checkpoint_hash:
            _fail(
                "identity_conflict",
                "model_hash must equal the frozen checkpoint hash",
                field="model_hash",
            )
        _hex(self.code_sha, "code_sha", 40)
        _text(self.hook_site, "hook_site")
        layers = _validated_layers(self.requested_layers)
        object.__setattr__(self, "requested_layers", layers)
        if self.dtype not in SUPPORTED_DTYPES:
            _fail(
                "unsupported_dtype",
                "dtype must be float16, float32, or float64",
                field="dtype",
            )
        _integer(
            self.hidden_width,
            "hidden_width",
            minimum=1,
            maximum=MAX_HIDDEN_WIDTH,
        )

    def to_document(self) -> dict[str, Any]:
        return {
            "accepted_manifest_hash": self.accepted_manifest_hash,
            "checkpoint_hash": self.checkpoint_hash,
            "code_sha": self.code_sha,
            "config_hash": self.config_hash,
            "dtype": self.dtype,
            "format_version": self.format_version,
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
        return _digest(self.to_document())


@dataclass(frozen=True, order=True)
class ActivationSourceFrameIdentityV2:
    """Exact C and model identity of one global pilot frame."""

    trajectory_id: str
    global_model_frame_idx: int
    source_frame_id: str
    source_frame_idx: int
    source_tick: int
    c_frame_map_sha256: str
    c_frame_map_row_sha256: str
    c_state_sha256: str
    c_state_row_sha256: str

    def __post_init__(self) -> None:
        _text(self.trajectory_id, "trajectory_id")
        _integer(self.global_model_frame_idx, "global_model_frame_idx")
        _text(self.source_frame_id, "source_frame_id")
        _integer(self.source_frame_idx, "source_frame_idx")
        _integer(self.source_tick, "source_tick")
        for field in (
            "c_frame_map_sha256",
            "c_frame_map_row_sha256",
            "c_state_sha256",
            "c_state_row_sha256",
        ):
            _hex(getattr(self, field), field, 64)

    def to_document(self) -> dict[str, Any]:
        return {
            "c_frame_map_row_sha256": self.c_frame_map_row_sha256,
            "c_frame_map_sha256": self.c_frame_map_sha256,
            "c_state_row_sha256": self.c_state_row_sha256,
            "c_state_sha256": self.c_state_sha256,
            "global_model_frame_idx": self.global_model_frame_idx,
            "source_frame_id": self.source_frame_id,
            "source_frame_idx": self.source_frame_idx,
            "source_tick": self.source_tick,
            "trajectory_id": self.trajectory_id,
        }


@dataclass(frozen=True, order=True)
class ActivationScientificKeyV2:
    """Globally unique scientific activation identity."""

    trajectory_id: str
    global_model_frame_idx: int
    source_frame_id: str
    source_tick: int
    layer_idx: int
    hook_site: str
    checkpoint_hash: str
    preprocess_hash: str
    producing_run_id: str

    def __post_init__(self) -> None:
        _text(self.trajectory_id, "trajectory_id")
        _integer(self.global_model_frame_idx, "global_model_frame_idx")
        _text(self.source_frame_id, "source_frame_id")
        _integer(self.source_tick, "source_tick")
        _integer(self.layer_idx, "layer_idx")
        _text(self.hook_site, "hook_site")
        _hex(self.checkpoint_hash, "checkpoint_hash", 64)
        _hex(self.preprocess_hash, "preprocess_hash", 64)
        _text(self.producing_run_id, "producing_run_id")

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> ActivationScientificKeyV2:
        return cls(
            trajectory_id=row.get("trajectory_id"),
            global_model_frame_idx=row.get("global_model_frame_idx"),
            source_frame_id=row.get("source_frame_id"),
            source_tick=row.get("source_tick"),
            layer_idx=row.get("layer_idx"),
            hook_site=row.get("hook_site"),
            checkpoint_hash=row.get("checkpoint_hash"),
            preprocess_hash=row.get("preprocess_hash"),
            producing_run_id=row.get("run_id"),
        )

    def to_document(self) -> dict[str, Any]:
        return {
            "checkpoint_hash": self.checkpoint_hash,
            "global_model_frame_idx": self.global_model_frame_idx,
            "hook_site": self.hook_site,
            "layer_idx": self.layer_idx,
            "preprocess_hash": self.preprocess_hash,
            "producing_run_id": self.producing_run_id,
            "source_frame_id": self.source_frame_id,
            "source_tick": self.source_tick,
            "trajectory_id": self.trajectory_id,
        }


@dataclass(frozen=True, order=True)
class ActivationPhysicalKeyV2:
    """Scientific identity plus immutable chunk and row location."""

    scientific_key: ActivationScientificKeyV2
    chunk_id: str
    chunk_row_idx: int

    def __post_init__(self) -> None:
        if not isinstance(self.scientific_key, ActivationScientificKeyV2):
            _fail(
                "invalid_identity",
                "scientific_key must be ActivationScientificKeyV2",
                field="scientific_key",
            )
        _text(self.chunk_id, "chunk_id")
        _integer(self.chunk_row_idx, "chunk_row_idx")

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> ActivationPhysicalKeyV2:
        return cls(
            scientific_key=ActivationScientificKeyV2.from_row(row),
            chunk_id=row.get("activation_chunk_id"),
            chunk_row_idx=row.get("chunk_row_idx"),
        )


def build_source_frame_bindings_v2(
    *,
    trajectory_id: str,
    frame_map_rows: Sequence[Mapping[str, Any]],
    state_rows: Sequence[Mapping[str, Any]],
    c_frame_map_sha256: str,
    c_state_sha256: str,
) -> tuple[ActivationSourceFrameIdentityV2, ...]:
    """Bind exact one-to-one C frame-map and state rows."""

    _text(trajectory_id, "trajectory_id")
    _hex(c_frame_map_sha256, "c_frame_map_sha256", 64)
    _hex(c_state_sha256, "c_state_sha256", 64)
    if (
        isinstance(frame_map_rows, (str, bytes))
        or not isinstance(frame_map_rows, Sequence)
        or not frame_map_rows
        or isinstance(state_rows, (str, bytes))
        or not isinstance(state_rows, Sequence)
        or len(frame_map_rows) != len(state_rows)
    ):
        _fail(
            "source_identity_conflict",
            "frame-map and state rows must be equal non-empty sequences",
        )
    bindings: list[ActivationSourceFrameIdentityV2] = []
    for position, (frame_row, state_row) in enumerate(
        zip(frame_map_rows, state_rows, strict=True)
    ):
        if not isinstance(frame_row, Mapping) or not isinstance(
            state_row, Mapping
        ):
            _fail(
                "source_identity_conflict",
                "source rows must be mappings",
                field=f"source_rows[{position}]",
            )
        exact = {
            "trajectory_id": trajectory_id,
            "model_frame_idx": position,
            "render_frame_idx": position,
            "server_tick": position,
        }
        for field, expected in exact.items():
            if (
                frame_row.get(field) != expected
                or state_row.get(field) != expected
            ):
                _fail(
                    "source_identity_conflict",
                    f"C frame-map/state identity must equal {expected!r}",
                    field=f"source_rows[{position}].{field}",
                )
        bindings.append(
            ActivationSourceFrameIdentityV2(
                trajectory_id=trajectory_id,
                global_model_frame_idx=position,
                source_frame_id=f"{trajectory_id}:render_frame:{position}",
                source_frame_idx=position,
                source_tick=position,
                c_frame_map_sha256=c_frame_map_sha256,
                c_frame_map_row_sha256=_digest(dict(frame_row)),
                c_state_sha256=c_state_sha256,
                c_state_row_sha256=_digest(dict(state_row)),
            )
        )
    return tuple(bindings)


_SOURCE_FIELDS = tuple(
    ActivationSourceFrameIdentityV2.__dataclass_fields__.keys()
)
_CANDIDATE_REQUIRED_FIELDS = frozenset(
    {
        "accepted_manifest_hash",
        "checkpoint_hash",
        "code_sha",
        "config_hash",
        "context_local_pair_idx",
        "exclusion_reason",
        "frame_token_map_sha256",
        "frame_token_positions",
        "hook_site",
        "layer_idx",
        "model_hash",
        "preprocess_hash",
        "run_id",
        "schema_version",
        "status",
        "store_format_version",
        "superseded_by",
        *_SOURCE_FIELDS,
    }
)
_PHYSICAL_FIELDS = frozenset(
    {
        "activation_chunk_id",
        "chunk_row_idx",
        "dtype",
        "pooling_method",
        "run_status",
        "token_region",
        "vector_shape",
    }
)


def _source_map(
    bindings: Sequence[ActivationSourceFrameIdentityV2],
) -> dict[tuple[str, int], ActivationSourceFrameIdentityV2]:
    if (
        isinstance(bindings, (str, bytes))
        or not isinstance(bindings, Sequence)
        or not bindings
        or any(
            not isinstance(value, ActivationSourceFrameIdentityV2)
            for value in bindings
        )
    ):
        _fail(
            "source_identity_conflict",
            "source bindings must be a non-empty typed sequence",
        )
    keys = [
        (value.trajectory_id, value.global_model_frame_idx)
        for value in bindings
    ]
    if len(keys) != len(set(keys)):
        _fail(
            "source_identity_conflict",
            "source bindings contain duplicate global frame identities",
        )
    return dict(zip(keys, bindings, strict=True))


def validate_activation_row_v2(
    row: Mapping[str, Any],
    *,
    store_identity: ActivationStoreIdentityV2,
    source_bindings: Sequence[ActivationSourceFrameIdentityV2],
    require_physical_identity: bool = False,
) -> ActivationScientificKeyV2 | ActivationPhysicalKeyV2:
    """Validate one row under v2 without granting v1 compatibility."""

    if not isinstance(store_identity, ActivationStoreIdentityV2):
        _fail(
            "invalid_identity",
            "store_identity must be ActivationStoreIdentityV2",
        )
    if not isinstance(row, Mapping):
        _fail("invalid_row", "activation row must be a mapping")
    if "model_frame_idx" in row:
        _fail(
            "v1_reinterpretation_forbidden",
            "v2 forbids the ambiguous v1 model_frame_idx field",
            field="model_frame_idx",
        )
    required = _CANDIDATE_REQUIRED_FIELDS | (
        _PHYSICAL_FIELDS if require_physical_identity else frozenset()
    )
    missing = sorted(required - set(row))
    if missing:
        _fail(
            "missing_identity",
            "v2 row is missing required fields: " + ", ".join(missing),
        )
    global_idx = _integer(
        row.get("global_model_frame_idx"),
        "global_model_frame_idx",
    )
    local_idx = _integer(
        row.get("context_local_pair_idx"),
        "context_local_pair_idx",
        maximum=MAX_CONTEXT_PAIR_COUNT - 1,
    )
    positions = row.get("frame_token_positions")
    expected_positions = list(derive_visual_token_positions(local_idx))
    if (
        isinstance(positions, (str, bytes))
        or not isinstance(positions, Sequence)
        or list(positions) != expected_positions
    ):
        _fail(
            "invalid_token_positions",
            "visual positions must derive only from context_local_pair_idx",
            field="frame_token_positions",
        )
    _hex(row.get("frame_token_map_sha256"), "frame_token_map_sha256", 64)
    expected_identity = {
        "accepted_manifest_hash": store_identity.accepted_manifest_hash,
        "checkpoint_hash": store_identity.checkpoint_hash,
        "code_sha": store_identity.code_sha,
        "config_hash": store_identity.config_hash,
        "hook_site": store_identity.hook_site,
        "model_hash": store_identity.model_hash,
        "preprocess_hash": store_identity.preprocess_hash,
        "run_id": store_identity.run_id,
        "schema_version": store_identity.schema_version,
        "store_format_version": store_identity.format_version,
    }
    for field, expected in expected_identity.items():
        if row.get(field) != expected:
            _fail(
                "identity_conflict",
                f"row must equal store identity value {expected!r}",
                field=field,
            )
    layer = _integer(row.get("layer_idx"), "layer_idx")
    if layer not in store_identity.requested_layers:
        _fail(
            "identity_conflict",
            "row layer is outside the frozen requested layer set",
            field="layer_idx",
        )
    if (
        row.get("status") != "accepted"
        or row.get("exclusion_reason") is not None
        or row.get("superseded_by") is not None
    ):
        _fail(
            "invalid_state",
            "candidate row must have accepted unsuperseded lifecycle state",
        )
    authority = _source_map(source_bindings).get(
        (row.get("trajectory_id"), global_idx)
    )
    if authority is None:
        _fail(
            "source_identity_conflict",
            "global frame has no exact C source binding",
        )
    for field in _SOURCE_FIELDS:
        if row.get(field) != getattr(authority, field):
            _fail(
                "source_identity_conflict",
                "row conflicts with FrameTokenMap or C source identity",
                field=field,
            )
    scientific = ActivationScientificKeyV2.from_row(row)
    if require_physical_identity:
        if (
            row.get("dtype") != store_identity.dtype
            or row.get("pooling_method") != "mean"
            or row.get("run_status") != "completed"
            or row.get("token_region") != "visual"
            or tuple(row.get("vector_shape", ()))
            != (store_identity.hidden_width,)
        ):
            _fail(
                "invalid_row",
                "physical row storage metadata is inconsistent",
            )
        return ActivationPhysicalKeyV2.from_row(row)
    return scientific


def validate_activation_rows_v2(
    rows: Sequence[Mapping[str, Any]],
    *,
    store_identity: ActivationStoreIdentityV2,
    source_bindings: Sequence[ActivationSourceFrameIdentityV2],
    expected_global_frame_count: int | None = None,
    require_complete_layers: bool = False,
    require_physical_identity: bool = False,
) -> tuple[ActivationScientificKeyV2 | ActivationPhysicalKeyV2, ...]:
    """Validate uniqueness, monotonic global identity, and optional cardinality."""

    if (
        isinstance(rows, (str, bytes))
        or not isinstance(rows, Sequence)
        or not rows
    ):
        _fail("invalid_row", "rows must be a non-empty sequence")
    keys = tuple(
        validate_activation_row_v2(
            row,
            store_identity=store_identity,
            source_bindings=source_bindings,
            require_physical_identity=require_physical_identity,
        )
        for row in rows
    )
    scientific_keys = tuple(
        key.scientific_key
        if isinstance(key, ActivationPhysicalKeyV2)
        else key
        for key in keys
    )
    if len(scientific_keys) != len(set(scientific_keys)):
        _fail(
            "duplicate_activation_key",
            "duplicate global-frame/layer scientific activation key",
        )
    if require_physical_identity and len(keys) != len(set(keys)):
        _fail(
            "duplicate_activation_key",
            "duplicate physical activation index key",
        )
    if expected_global_frame_count is not None:
        frame_count = _integer(
            expected_global_frame_count,
            "expected_global_frame_count",
            minimum=1,
        )
        observed_frames = sorted(
            {
                (key.trajectory_id, key.global_model_frame_idx)
                for key in scientific_keys
            }
        )
        indices = [frame_idx for _trajectory, frame_idx in observed_frames]
        if indices != list(range(frame_count)):
            _fail(
                "source_identity_conflict",
                "global model-frame identities must be monotonic and complete",
            )
        if require_complete_layers:
            expected_rows = expected_activation_row_count(
                frame_count,
                store_identity.requested_layers,
            )
            if len(rows) != expected_rows:
                _fail(
                    "cardinality_mismatch",
                    f"expected {expected_rows} complete activation rows",
                )
            by_frame: dict[int, set[int]] = {}
            for key in scientific_keys:
                by_frame.setdefault(key.global_model_frame_idx, set()).add(
                    key.layer_idx
                )
            expected_layers = set(store_identity.requested_layers)
            if any(layers != expected_layers for layers in by_frame.values()):
                _fail(
                    "cardinality_mismatch",
                    "every global frame must have the complete frozen layer set",
                )
    return keys


@dataclass(frozen=True)
class ActivationChunkRecordV2:
    """Immutable descriptor for one homogeneous v2 NumPy chunk."""

    chunk_id: str
    path: str
    layer_idx: int
    row_count: int
    hidden_width: int
    dtype: str
    byte_size: int
    sha256: str
    first_scientific_key: Mapping[str, Any]
    last_scientific_key: Mapping[str, Any]

    def __post_init__(self) -> None:
        _text(self.chunk_id, "chunk_id")
        _safe_relative_path(self.path, "path")
        _integer(self.layer_idx, "layer_idx")
        _integer(self.row_count, "row_count", minimum=1)
        _integer(self.hidden_width, "hidden_width", minimum=1)
        if self.dtype not in SUPPORTED_DTYPES:
            _fail("unsupported_dtype", "chunk dtype is unsupported")
        _integer(self.byte_size, "byte_size", minimum=1)
        _hex(self.sha256, "sha256", 64)
        for field in ("first_scientific_key", "last_scientific_key"):
            if not isinstance(getattr(self, field), Mapping):
                _fail(
                    "invalid_identity",
                    "chunk key bounds must be mappings",
                    field=field,
                )

    def to_document(self) -> dict[str, Any]:
        return {
            "byte_size": self.byte_size,
            "chunk_id": self.chunk_id,
            "dtype": self.dtype,
            "first_scientific_key": dict(self.first_scientific_key),
            "hidden_width": self.hidden_width,
            "last_scientific_key": dict(self.last_scientific_key),
            "layer_idx": self.layer_idx,
            "path": self.path,
            "row_count": self.row_count,
            "sha256": self.sha256,
        }


@dataclass(frozen=True)
class ActivationIndexSnapshotV2:
    """Backend-neutral immutable v2 index snapshot."""

    snapshot_id: str
    store_identity: ActivationStoreIdentityV2
    creation_timestamp: str
    run_status: str
    chunks: tuple[ActivationChunkRecordV2, ...]
    index_rows: tuple[Mapping[str, Any], ...]

    def __post_init__(self) -> None:
        _hex(self.snapshot_id, "snapshot_id", 64)
        if not isinstance(self.store_identity, ActivationStoreIdentityV2):
            _fail(
                "invalid_identity",
                "store_identity must be ActivationStoreIdentityV2",
            )
        _timestamp(self.creation_timestamp, "creation_timestamp")
        if self.run_status != "completed":
            _fail("invalid_state", "v2 snapshots must be completed")
        if (
            not isinstance(self.chunks, tuple)
            or any(
                not isinstance(chunk, ActivationChunkRecordV2)
                for chunk in self.chunks
            )
            or not isinstance(self.index_rows, tuple)
        ):
            _fail("invalid_index", "snapshot collections must be tuples")
        object.__setattr__(
            self,
            "index_rows",
            tuple(_freeze(dict(row)) for row in self.index_rows),
        )

    @property
    def relative_path(self) -> str:
        return f"indexes/index-{self.snapshot_id}.json"

    def identity_document(self) -> dict[str, Any]:
        return {
            "chunks": [chunk.to_document() for chunk in self.chunks],
            "creation_timestamp": self.creation_timestamp,
            "format_version": ACTIVATION_INDEX_V2_FORMAT_VERSION,
            "index_rows": [_thaw(row) for row in self.index_rows],
            "run_status": self.run_status,
            "schema_version": SCHEMA_VERSION,
            "store_identity": self.store_identity.to_document(),
        }

    def to_document(self) -> dict[str, Any]:
        document = self.identity_document()
        document["snapshot_id"] = self.snapshot_id
        return document


def _store_identity_from_document(
    value: object,
) -> ActivationStoreIdentityV2:
    if not isinstance(value, Mapping):
        _fail("invalid_index", "store_identity must be a mapping")
    try:
        return ActivationStoreIdentityV2(
            schema_version=value["schema_version"],
            format_version=value["format_version"],
            run_id=value["run_id"],
            checkpoint_hash=value["checkpoint_hash"],
            model_hash=value["model_hash"],
            config_hash=value["config_hash"],
            preprocess_hash=value["preprocess_hash"],
            accepted_manifest_hash=value["accepted_manifest_hash"],
            code_sha=value["code_sha"],
            hook_site=value["hook_site"],
            requested_layers=tuple(value["requested_layers"]),
            dtype=value["dtype"],
            hidden_width=value["hidden_width"],
        )
    except KeyError as error:
        _fail("invalid_index", f"store identity misses {error.args[0]!r}")


def _strict_json(path: Path) -> Mapping[str, Any]:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                _fail(
                    "invalid_json",
                    f"duplicate JSON key {key!r}",
                    path=path,
                )
            result[key] = value
        return result

    try:
        document = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=reject_duplicates,
            parse_constant=lambda value: _fail(
                "invalid_json",
                f"nonfinite JSON constant {value!r}",
                path=path,
            ),
        )
    except ActivationStoreV2Error:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        _fail("invalid_json", f"could not parse JSON: {error}", path=path)
    if not isinstance(document, Mapping):
        _fail("invalid_json", "JSON root must be an object", path=path)
    return document


def _snapshot_from_document(
    value: Mapping[str, Any],
) -> ActivationIndexSnapshotV2:
    if value.get("format_version") != ACTIVATION_INDEX_V2_FORMAT_VERSION:
        _fail(
            "unsupported_format",
            "document is not activation-index v2",
            field="format_version",
        )
    chunks_value = value.get("chunks")
    rows_value = value.get("index_rows")
    if not isinstance(chunks_value, list) or not isinstance(rows_value, list):
        _fail("invalid_index", "chunks and index_rows must be lists")
    chunks: list[ActivationChunkRecordV2] = []
    for source in chunks_value:
        if not isinstance(source, Mapping):
            _fail("invalid_index", "chunk record must be a mapping")
        try:
            chunks.append(
                ActivationChunkRecordV2(
                    chunk_id=source["chunk_id"],
                    path=source["path"],
                    layer_idx=source["layer_idx"],
                    row_count=source["row_count"],
                    hidden_width=source["hidden_width"],
                    dtype=source["dtype"],
                    byte_size=source["byte_size"],
                    sha256=source["sha256"],
                    first_scientific_key=source["first_scientific_key"],
                    last_scientific_key=source["last_scientific_key"],
                )
            )
        except KeyError as error:
            _fail("invalid_index", f"chunk misses {error.args[0]!r}")
    try:
        return ActivationIndexSnapshotV2(
            snapshot_id=value["snapshot_id"],
            store_identity=_store_identity_from_document(
                value["store_identity"]
            ),
            creation_timestamp=value["creation_timestamp"],
            run_status=value["run_status"],
            chunks=tuple(chunks),
            index_rows=tuple(rows_value),
        )
    except KeyError as error:
        _fail("invalid_index", f"snapshot misses {error.args[0]!r}")


def validate_activation_index_snapshot_v2(
    snapshot: ActivationIndexSnapshotV2,
    *,
    store_root: Path | str,
    source_bindings: Sequence[ActivationSourceFrameIdentityV2],
) -> None:
    """Validate index identity, C bindings, and every referenced chunk."""

    if not isinstance(snapshot, ActivationIndexSnapshotV2):
        _fail(
            "invalid_index",
            "snapshot must be ActivationIndexSnapshotV2",
        )
    if snapshot.snapshot_id != _digest(snapshot.identity_document()):
        _fail("invalid_index", "snapshot_id does not match canonical identity")
    validate_activation_rows_v2(
        snapshot.index_rows,
        store_identity=snapshot.store_identity,
        source_bindings=source_bindings,
        require_physical_identity=True,
    )
    chunks_by_id = {chunk.chunk_id: chunk for chunk in snapshot.chunks}
    if len(chunks_by_id) != len(snapshot.chunks):
        _fail("invalid_index", "chunk IDs must be unique")
    references: dict[str, list[Mapping[str, Any]]] = {}
    for row in snapshot.index_rows:
        references.setdefault(str(row["activation_chunk_id"]), []).append(row)
    if set(references) != set(chunks_by_id):
        _fail(
            "invalid_index",
            "index rows and chunk records must reference the same chunk set",
        )
    numpy = __import__("numpy")
    for chunk_id, chunk in chunks_by_id.items():
        path = _resolve(store_root, chunk.path)
        if path.is_symlink() or not path.is_file():
            _fail("missing_chunk", "chunk file is unavailable", path=path)
        if (
            path.stat().st_size != chunk.byte_size
            or _sha256_file(path) != chunk.sha256
        ):
            _fail("checksum_mismatch", "chunk bytes do not match", path=path)
        try:
            array = numpy.load(path, allow_pickle=False)
        except (OSError, ValueError) as error:
            _fail("invalid_chunk", f"could not load chunk: {error}", path=path)
        if (
            array.shape != (chunk.row_count, chunk.hidden_width)
            or array.dtype.name != chunk.dtype
            or not bool(numpy.isfinite(array).all())
        ):
            _fail(
                "invalid_chunk",
                "chunk shape, dtype, or finite values are invalid",
                path=path,
            )
        rows = sorted(
            references[chunk_id],
            key=lambda row: int(row["chunk_row_idx"]),
        )
        if (
            [row["chunk_row_idx"] for row in rows]
            != list(range(chunk.row_count))
            or any(row["layer_idx"] != chunk.layer_idx for row in rows)
            or ActivationScientificKeyV2.from_row(rows[0]).to_document()
            != dict(chunk.first_scientific_key)
            or ActivationScientificKeyV2.from_row(rows[-1]).to_document()
            != dict(chunk.last_scientific_key)
        ):
            _fail(
                "invalid_index",
                "chunk row offsets or scientific key bounds are invalid",
            )


def _exclusive_publish(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() or path.is_symlink():
        _fail("output_exists", "immutable output already exists", path=path)
    temporary_fd, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(temporary_fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        if _sha256_file(temporary) != hashlib.sha256(payload).hexdigest():
            _fail(
                "checksum_mismatch",
                "temporary output differs from requested bytes",
                path=temporary,
            )
        try:
            os.link(temporary, path)
        except FileExistsError:
            _fail("output_exists", "immutable output already exists", path=path)
        except OSError as error:
            _fail(
                "publication_failed",
                f"atomic no-overwrite publication failed: {error}",
                path=path,
            )
    finally:
        temporary.unlink(missing_ok=True)


def publish_activation_chunk_v2(
    *,
    store_root: Path | str,
    store_identity: ActivationStoreIdentityV2,
    source_bindings: Sequence[ActivationSourceFrameIdentityV2],
    rows: Sequence[Mapping[str, Any]],
    vectors: object,
    creation_timestamp: str,
    prior_snapshot: ActivationIndexSnapshotV2 | None = None,
) -> ActivationIndexSnapshotV2:
    """Publish one homogeneous layer chunk and the next immutable v2 index."""

    root = Path(store_root)
    if not root.is_dir() or root.is_symlink():
        _fail(
            "unsafe_path",
            "store_root must be an existing ordinary directory",
            path=root,
        )
    _timestamp(creation_timestamp, "creation_timestamp")
    if (
        isinstance(rows, (str, bytes))
        or not isinstance(rows, Sequence)
        or not rows
        or len(rows) > MAX_ROWS_PER_CHUNK
    ):
        _fail(
            "invalid_row",
            f"rows must contain 1..{MAX_ROWS_PER_CHUNK} records",
        )
    scientific_keys = validate_activation_rows_v2(
        rows,
        store_identity=store_identity,
        source_bindings=source_bindings,
    )
    assert all(
        isinstance(key, ActivationScientificKeyV2)
        for key in scientific_keys
    )
    layers = {key.layer_idx for key in scientific_keys}
    if len(layers) != 1:
        _fail(
            "invalid_chunk",
            "each v2 chunk must contain one homogeneous layer",
        )
    numpy = __import__("numpy")
    array = numpy.asarray(vectors)
    if (
        array.dtype.hasobject
        or array.ndim != 2
        or array.shape != (len(rows), store_identity.hidden_width)
        or array.dtype.name != store_identity.dtype
        or not numpy.issubdtype(array.dtype, numpy.floating)
        or not bool(numpy.isfinite(array).all())
    ):
        _fail(
            "invalid_chunk",
            "vectors must be finite matching [row_count, hidden_width] values",
        )
    order = sorted(range(len(scientific_keys)), key=scientific_keys.__getitem__)
    ordered_keys = [scientific_keys[index] for index in order]
    ordered_rows = [dict(rows[index]) for index in order]
    ordered_vectors = numpy.ascontiguousarray(array[order])
    if prior_snapshot is not None:
        validate_activation_index_snapshot_v2(
            prior_snapshot,
            store_root=root,
            source_bindings=source_bindings,
        )
        if prior_snapshot.store_identity != store_identity:
            _fail(
                "identity_conflict",
                "prior snapshot has another complete store identity",
            )
        existing = {
            ActivationScientificKeyV2.from_row(row)
            for row in prior_snapshot.index_rows
        }
        if existing & set(ordered_keys):
            _fail(
                "duplicate_activation_key",
                "new chunk collides with an existing global-frame/layer key",
            )
        previous_chunks = prior_snapshot.chunks
        previous_rows = prior_snapshot.index_rows
    else:
        previous_chunks = ()
        previous_rows = ()
    chunk_identity = {
        "first_scientific_key": ordered_keys[0].to_document(),
        "last_scientific_key": ordered_keys[-1].to_document(),
        "layer_idx": ordered_keys[0].layer_idx,
        "row_count": len(ordered_keys),
        "store_identity_digest": store_identity.digest,
    }
    chunk_digest = _digest(chunk_identity)
    chunk_id = f"activation-v2-chunk-{chunk_digest[:24]}"
    chunk_relative_path = f"chunks/{chunk_id}.npy"
    stream = io.BytesIO()
    numpy.save(stream, ordered_vectors, allow_pickle=False)
    payload = stream.getvalue()
    if len(payload) > MAX_CHUNK_BYTES:
        _fail("limit_exceeded", "serialized chunk exceeds byte limit")
    chunk_path = _resolve(root, chunk_relative_path)
    _exclusive_publish(chunk_path, payload)
    chunk = ActivationChunkRecordV2(
        chunk_id=chunk_id,
        path=chunk_relative_path,
        layer_idx=ordered_keys[0].layer_idx,
        row_count=len(ordered_keys),
        hidden_width=store_identity.hidden_width,
        dtype=store_identity.dtype,
        byte_size=len(payload),
        sha256=hashlib.sha256(payload).hexdigest(),
        first_scientific_key=ordered_keys[0].to_document(),
        last_scientific_key=ordered_keys[-1].to_document(),
    )
    materialized: list[dict[str, Any]] = []
    for chunk_row_idx, source in enumerate(ordered_rows):
        row = dict(source)
        row.update(
            {
                "activation_chunk_id": chunk_id,
                "chunk_row_idx": chunk_row_idx,
                "dtype": store_identity.dtype,
                "pooling_method": "mean",
                "run_status": "completed",
                "token_region": "visual",
                "vector_shape": [store_identity.hidden_width],
            }
        )
        validate_activation_row_v2(
            row,
            store_identity=store_identity,
            source_bindings=source_bindings,
            require_physical_identity=True,
        )
        materialized.append(row)
    combined_rows = tuple(
        sorted(
            (dict(row) for row in (*previous_rows, *materialized)),
            key=ActivationScientificKeyV2.from_row,
        )
    )
    if len(combined_rows) > MAX_INDEX_ROWS:
        _fail("limit_exceeded", "v2 index row limit exceeded")
    combined_chunks = tuple(
        sorted((*previous_chunks, chunk), key=lambda value: value.chunk_id)
    )
    prototype = ActivationIndexSnapshotV2(
        snapshot_id="0" * 64,
        store_identity=store_identity,
        creation_timestamp=creation_timestamp,
        run_status="completed",
        chunks=combined_chunks,
        index_rows=combined_rows,
    )
    snapshot = ActivationIndexSnapshotV2(
        snapshot_id=_digest(prototype.identity_document()),
        store_identity=store_identity,
        creation_timestamp=creation_timestamp,
        run_status="completed",
        chunks=combined_chunks,
        index_rows=combined_rows,
    )
    validate_activation_index_snapshot_v2(
        snapshot,
        store_root=root,
        source_bindings=source_bindings,
    )
    index_path = _resolve(root, snapshot.relative_path)
    _exclusive_publish(index_path, canonical_json_bytes(snapshot.to_document()))
    return load_activation_index_snapshot_v2(
        index_path,
        store_root=root,
        source_bindings=source_bindings,
    )


def load_activation_index_snapshot_v2(
    path: Path | str,
    *,
    store_root: Path | str,
    source_bindings: Sequence[ActivationSourceFrameIdentityV2],
) -> ActivationIndexSnapshotV2:
    """Read only an explicitly versioned v2 index."""

    index_path = Path(path)
    document = _strict_json(index_path)
    if document.get("format_version") != ACTIVATION_INDEX_V2_FORMAT_VERSION:
        _fail(
            "unsupported_format",
            "v2 loader refuses non-v2 activation indexes",
            field="format_version",
            path=index_path,
        )
    if index_path.read_bytes() != canonical_json_bytes(dict(document)):
        _fail("invalid_json", "index bytes are not canonical", path=index_path)
    snapshot = _snapshot_from_document(document)
    validate_activation_index_snapshot_v2(
        snapshot,
        store_root=store_root,
        source_bindings=source_bindings,
    )
    return snapshot


def load_activation_index_dispatched(
    path: Path | str,
    *,
    store_root: Path | str,
    source_bindings_v2: (
        Sequence[ActivationSourceFrameIdentityV2] | None
    ) = None,
) -> object:
    """Dispatch explicitly to the historical v1 or additive v2 loader."""

    index_path = Path(path)
    document = _strict_json(index_path)
    version = document.get("format_version")
    if version == ACTIVATION_INDEX_V1_FORMAT_VERSION:
        from mineocclude.activations.store import (
            load_activation_index_snapshot,
        )

        return load_activation_index_snapshot(index_path, store_root=store_root)
    if version == ACTIVATION_INDEX_V2_FORMAT_VERSION:
        if source_bindings_v2 is None:
            _fail(
                "source_identity_conflict",
                "v2 dispatch requires explicit C source bindings",
            )
        return load_activation_index_snapshot_v2(
            index_path,
            store_root=store_root,
            source_bindings=source_bindings_v2,
        )
    _fail(
        "unsupported_format",
        f"unsupported activation-index format {version!r}",
        field="format_version",
        path=index_path,
    )


def candidate_row_from_frame_token_span_v2(
    *,
    store_identity: ActivationStoreIdentityV2,
    source_identity: ActivationSourceFrameIdentityV2,
    frame_token_map: FrameTokenMap,
    frame_token_map_sha256: str,
    layer_idx: int,
) -> dict[str, Any]:
    """Build a v2 candidate row from an audited FrameTokenMap span."""

    if not isinstance(frame_token_map, FrameTokenMap):
        _fail(
            "source_identity_conflict",
            "frame_token_map must be the frozen project-owned type",
            field="frame_token_map",
        )
    _hex(frame_token_map_sha256, "frame_token_map_sha256", 64)
    matching = tuple(
        span
        for span in frame_token_map.spans
        if span.identity.trajectory_id == source_identity.trajectory_id
        and span.identity.model_frame_idx
        == source_identity.global_model_frame_idx
    )
    if len(matching) != 1:
        _fail(
            "source_identity_conflict",
            "FrameTokenMap must contain exactly the bound global frame",
            field="frame_token_map",
        )
    span = matching[0]
    local_idx = span.pair_index
    if span.visual_positions != derive_visual_token_positions(local_idx):
        _fail(
            "invalid_token_positions",
            "FrameTokenMap positions conflict with its context-local identity",
            field="frame_token_map",
        )
    _integer(layer_idx, "layer_idx")
    row = {
        **source_identity.to_document(),
        "accepted_manifest_hash": store_identity.accepted_manifest_hash,
        "checkpoint_hash": store_identity.checkpoint_hash,
        "code_sha": store_identity.code_sha,
        "config_hash": store_identity.config_hash,
        "context_local_pair_idx": local_idx,
        "exclusion_reason": None,
        "frame_token_map_sha256": frame_token_map_sha256,
        "frame_token_positions": list(
            derive_visual_token_positions(local_idx)
        ),
        "hook_site": store_identity.hook_site,
        "layer_idx": layer_idx,
        "model_hash": store_identity.model_hash,
        "preprocess_hash": store_identity.preprocess_hash,
        "run_id": store_identity.run_id,
        "schema_version": store_identity.schema_version,
        "status": "accepted",
        "store_format_version": store_identity.format_version,
        "superseded_by": None,
    }
    validate_activation_row_v2(
        row,
        store_identity=store_identity,
        source_bindings=(source_identity,),
    )
    return row


__all__ = [
    "ACTIVATION_INDEX_V1_FORMAT_VERSION",
    "ACTIVATION_INDEX_V2_FORMAT_VERSION",
    "ACTIVATION_SOURCE_BINDING_V2_FORMAT_VERSION",
    "ACTIVATION_STORE_V1_FORMAT_VERSION",
    "ACTIVATION_STORE_V2_FORMAT_VERSION",
    "FROZEN_PHASE6_LAYERS",
    "MAX_CONTEXT_PAIR_COUNT",
    "TOKENS_PER_FRAME_ACTION_PAIR",
    "ActivationIndexSnapshotV2",
    "ActivationPhysicalKeyV2",
    "ActivationScientificKeyV2",
    "ActivationSourceFrameIdentityV2",
    "ActivationStoreIdentityV2",
    "ActivationStoreV2Error",
    "build_source_frame_bindings_v2",
    "candidate_row_from_frame_token_span_v2",
    "canonical_json_bytes",
    "derive_visual_token_positions",
    "expected_activation_row_count",
    "load_activation_index_dispatched",
    "load_activation_index_snapshot_v2",
    "publish_activation_chunk_v2",
    "validate_activation_index_snapshot_v2",
    "validate_activation_row_v2",
    "validate_activation_rows_v2",
]
