"""Lossless Person B contract for consuming Person A Activation Store v2.

The historical v1 contract remains in :mod:`mineocclude.contracts.activation`.
This module never rewrites or reinterprets a v1 row.  It provides explicit
format dispatch and verifies v2 index and NumPy chunk bytes before exposing any
activation vector to Person B analysis code.
"""

from __future__ import annotations

import hashlib
import io
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

import numpy as np

from mineocclude.contracts.activation import validate_activation_handoff
from mineocclude.experiments.registry import (
    canonical_json_bytes as registry_v2_canonical_json_bytes,
)

ACTIVATION_INDEX_V2_FORMAT_VERSION = "person-a-activation-index-v2"
ACTIVATION_STORE_V2_FORMAT_VERSION = "person-a-activation-store-v2"
ACTIVATION_V1_SCHEMA_VERSION = "1.0"
VISUAL_TOKENS_PER_FRAME = 336
TOKENS_PER_FRAME_ACTION_PAIR = 347
MAX_CONTEXT_LOCAL_PAIR_IDX = 15
EXPECTED_DTYPE = "float32"
PERSON_A_ACTIVATION_STORE_V2_PRODUCER_COMMIT = (
    "55776dc88302b89b52eef483a710fbf6811cf536"
)
PERSON_A_ACTIVATION_STORE_V2_PRODUCER_SHA256 = (
    "8c2313f4ab99c02abb302af1d0b688ba353e34a1cd7985492ed9e562995dd575"
)
PERSON_A_ACTIVATION_INDEX_V2_ARTIFACT_TYPE = "person_a_activation_store_v2_index"
PERSON_A_ACTIVATION_INDEX_V2_CANONICALIZATION_CONTRACT = (
    "person-a-activation-store-v2-canonical-json@"
    f"{PERSON_A_ACTIVATION_STORE_V2_PRODUCER_COMMIT}"
)
REGISTRY_V2_RECORD_ARTIFACT_TYPE = "registry_v2_record"
REGISTRY_V2_CANONICALIZATION_CONTRACT = (
    "mineocclude-immutable-registry-v2-canonical-json"
)


class ActivationV2ConsumerError(ValueError):
    """Stable fail-closed v2 consumer error."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True)
class ActivationDispatchResult:
    """Version-specific validation result without cross-version coercion."""

    format_version: str
    accepted: bool
    rejection_codes: tuple[str, ...]


@dataclass(frozen=True)
class ExternalChunkBinding:
    """Exact external location and immutable identity for one NumPy chunk."""

    chunk_id: str
    path: Path
    sha256: str
    byte_size: int
    row_count: int


@dataclass(frozen=True)
class ValidatedActivationIndexV2:
    """Authenticated producer bytes and parsed v2 index without chunk loading."""

    raw_sha256: str
    raw_byte_size: int
    document: Mapping[str, Any]
    store_identity: Mapping[str, Any]
    chunks: tuple[Mapping[str, Any], ...]
    rows: tuple[Mapping[str, Any], ...]


@dataclass(frozen=True)
class LoadedActivationIndexV2:
    """Validated v2 index plus optionally retained chunk arrays."""

    trajectory_id: str
    index_path: Path
    index_sha256: str
    index_byte_size: int
    store_identity: Mapping[str, Any]
    rows: tuple[Mapping[str, Any], ...]
    chunks: tuple[Mapping[str, Any], ...]
    arrays_by_chunk_id: Mapping[str, np.ndarray]

    @property
    def accepted_manifest_sha256(self) -> str:
        return str(self.store_identity["accepted_manifest_hash"])

    @property
    def activation_row_count(self) -> int:
        return len(self.rows)

    def vector_for_row(self, row: Mapping[str, Any]) -> np.ndarray:
        """Resolve one row only through its authenticated physical identity."""

        chunk_id = row.get("activation_chunk_id")
        chunk_row_idx = row.get("chunk_row_idx")
        array = self.arrays_by_chunk_id.get(str(chunk_id))
        if array is None:
            _fail("missing_retained_chunk", f"No retained array for {chunk_id!r}.")
        if not _is_int(chunk_row_idx, minimum=0) or chunk_row_idx >= array.shape[0]:
            _fail("invalid_chunk_row", "Activation row has an invalid chunk offset.")
        return array[chunk_row_idx]


def _fail(code: str, message: str) -> None:
    raise ActivationV2ConsumerError(code, message)


def _is_int(value: Any, *, minimum: int = 0, maximum: int | None = None) -> bool:
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        return False
    return maximum is None or value <= maximum


def _require_int(
    value: Any,
    field: str,
    *,
    minimum: int = 0,
    maximum: int | None = None,
) -> int:
    if not _is_int(value, minimum=minimum, maximum=maximum):
        upper = "" if maximum is None else f" and at most {maximum}"
        _fail("invalid_integer", f"{field} must be at least {minimum}{upper}.")
    return value


def _is_sha256(value: Any) -> bool:
    if not isinstance(value, str) or len(value) != 64:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return True


def _require_sha256(value: Any, field: str) -> str:
    if not _is_sha256(value):
        _fail("invalid_sha256", f"{field} must be a lowercase SHA-256 digest.")
    if value != value.lower():
        _fail("invalid_sha256", f"{field} must use lowercase hexadecimal.")
    return value


def _require_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail("invalid_text", f"{field} must be a non-empty string.")
    return value


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def person_a_activation_index_v2_canonical_json_bytes(value: Any) -> bytes:
    """Reproduce the exact Person A producer encoding from the bound commit."""

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
        _fail("invalid_json", f"Value is not Person A canonical JSON: {error}")


def canonical_json_bytes_for_artifact(
    value: Mapping[str, Any],
    *,
    artifact_type: str,
    canonicalization_contract: str,
) -> bytes:
    """Dispatch canonicalization only through explicit owner/schema identity."""

    if artifact_type == PERSON_A_ACTIVATION_INDEX_V2_ARTIFACT_TYPE:
        if (
            canonicalization_contract
            != PERSON_A_ACTIVATION_INDEX_V2_CANONICALIZATION_CONTRACT
        ):
            _fail(
                "canonicalization_contract_mismatch",
                "Activation Store v2 requires the exact Person A producer contract.",
            )
        if value.get("format_version") != ACTIVATION_INDEX_V2_FORMAT_VERSION:
            _fail(
                "canonicalization_identity_conflict",
                "Person A index canonicalization requires activation-index v2.",
            )
        store = value.get("store_identity")
        if (
            not isinstance(store, Mapping)
            or store.get("format_version") != ACTIVATION_STORE_V2_FORMAT_VERSION
        ):
            _fail(
                "canonicalization_identity_conflict",
                "Person A index and store format identities conflict.",
            )
        return person_a_activation_index_v2_canonical_json_bytes(value)
    if artifact_type == REGISTRY_V2_RECORD_ARTIFACT_TYPE:
        if canonicalization_contract != REGISTRY_V2_CANONICALIZATION_CONTRACT:
            _fail(
                "canonicalization_contract_mismatch",
                "Registry v2 records require their existing Registry contract.",
            )
        return registry_v2_canonical_json_bytes(value)
    _fail(
        "unknown_canonicalization_contract",
        f"Unsupported artifact type {artifact_type!r}.",
    )


def person_a_activation_index_v2_snapshot_digest(
    document: Mapping[str, Any],
    *,
    canonicalization_contract: str,
) -> str:
    """Hash Person A's exact snapshot domain: the index minus snapshot_id."""

    if "snapshot_id" not in document:
        _fail("invalid_index", "Activation Index v2 lacks snapshot_id.")
    identity_document = dict(document)
    identity_document.pop("snapshot_id")
    payload = canonical_json_bytes_for_artifact(
        identity_document,
        artifact_type=PERSON_A_ACTIVATION_INDEX_V2_ARTIFACT_TYPE,
        canonicalization_contract=canonicalization_contract,
    )
    return _sha256_bytes(payload)


def _strict_json_bytes(payload: bytes, *, label: str) -> Mapping[str, Any]:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                _fail("invalid_json", f"{label} repeats JSON key {key!r}.")
            result[key] = value
        return result

    try:
        document = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=reject_duplicates,
            parse_constant=lambda value: _fail(
                "invalid_json", f"{label} contains {value!r}."
            ),
        )
    except ActivationV2ConsumerError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        _fail("invalid_json", f"Could not parse {label}: {error}")
    if not isinstance(document, Mapping):
        _fail("invalid_json", f"{label} root must be an object.")
    return document


def _read_exact_file(
    path: Path,
    *,
    expected_sha256: str,
    expected_byte_size: int,
    label: str,
) -> bytes:
    _require_sha256(expected_sha256, f"{label}.sha256")
    _require_int(expected_byte_size, f"{label}.byte_size", minimum=1)
    if path.is_symlink() or not path.is_file():
        _fail("missing_file", f"{label} is missing or is a symlink: {path}")
    try:
        if path.stat().st_size != expected_byte_size:
            _fail("byte_size_mismatch", f"{label} byte size does not match.")
        payload = path.read_bytes()
    except OSError as error:
        _fail("file_read_error", f"Could not read {label}: {error}")
    if _sha256_bytes(payload) != expected_sha256:
        _fail("sha256_mismatch", f"{label} literal-byte SHA-256 does not match.")
    return payload


def derive_visual_token_positions(context_local_pair_idx: int) -> tuple[int, ...]:
    """Derive visual token positions only from the context-local identity."""

    local_idx = _require_int(
        context_local_pair_idx,
        "context_local_pair_idx",
        maximum=MAX_CONTEXT_LOCAL_PAIR_IDX,
    )
    start = local_idx * TOKENS_PER_FRAME_ACTION_PAIR
    return tuple(range(start, start + VISUAL_TOKENS_PER_FRAME))


def _safe_relative_chunk_path(value: Any) -> str:
    path = _require_text(value, "chunk.path")
    candidate = PurePosixPath(path)
    if candidate.is_absolute() or ".." in candidate.parts or candidate.suffix != ".npy":
        _fail(
            "invalid_chunk_path", "Index chunk paths must be safe relative .npy paths."
        )
    return path


def _scientific_key(row: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        row.get("trajectory_id"),
        row.get("global_model_frame_idx"),
        row.get("source_frame_id"),
        row.get("source_tick"),
        row.get("layer_idx"),
        row.get("hook_site"),
        row.get("run_id"),
    )


def _scientific_key_document(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "checkpoint_hash": row["checkpoint_hash"],
        "global_model_frame_idx": row["global_model_frame_idx"],
        "hook_site": row["hook_site"],
        "layer_idx": row["layer_idx"],
        "preprocess_hash": row["preprocess_hash"],
        "producing_run_id": row["run_id"],
        "source_frame_id": row["source_frame_id"],
        "source_tick": row["source_tick"],
        "trajectory_id": row["trajectory_id"],
    }


def _validate_store_identity(
    value: Any,
    *,
    expected_manifest_sha256: str,
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail("invalid_store_identity", "store_identity must be an object.")
    required = {
        "accepted_manifest_hash",
        "checkpoint_hash",
        "code_sha",
        "config_hash",
        "dtype",
        "format_version",
        "hidden_width",
        "hook_site",
        "model_hash",
        "preprocess_hash",
        "requested_layers",
        "run_id",
        "schema_version",
    }
    missing = sorted(required - set(value))
    if missing:
        _fail("invalid_store_identity", f"store_identity misses {missing}.")
    if value.get("schema_version") != ACTIVATION_V1_SCHEMA_VERSION:
        _fail("invalid_schema_version", "v2 store schema_version must equal '1.0'.")
    if value.get("format_version") != ACTIVATION_STORE_V2_FORMAT_VERSION:
        _fail("unsupported_format", "Index does not bind Activation Store v2.")
    if value.get("accepted_manifest_hash") != expected_manifest_sha256:
        _fail(
            "manifest_identity_mismatch",
            "Store manifest identity does not match the trajectory's accepted C bytes.",
        )
    if value.get("dtype") != EXPECTED_DTYPE:
        _fail("invalid_dtype", "The authorized evidence must be float32.")
    _require_int(value.get("hidden_width"), "store_identity.hidden_width", minimum=1)
    _require_text(value.get("hook_site"), "store_identity.hook_site")
    _require_text(value.get("run_id"), "store_identity.run_id")
    for field in (
        "accepted_manifest_hash",
        "checkpoint_hash",
        "config_hash",
        "model_hash",
        "preprocess_hash",
    ):
        _require_sha256(value.get(field), f"store_identity.{field}")
    code_sha = value.get("code_sha")
    if not isinstance(code_sha, str) or len(code_sha) != 40:
        _fail("invalid_store_identity", "store_identity.code_sha must be a Git SHA.")
    layers = value.get("requested_layers")
    if (
        not isinstance(layers, list)
        or not layers
        or any(not _is_int(layer) for layer in layers)
        or layers != sorted(set(layers))
    ):
        _fail("invalid_store_identity", "requested_layers must be unique and sorted.")
    return value


def _validate_index_document_v2(
    document: Mapping[str, Any],
    *,
    canonicalization_contract: str,
    expected_trajectory_id: str,
    expected_manifest_sha256: str,
) -> tuple[
    Mapping[str, Any], tuple[Mapping[str, Any], ...], tuple[Mapping[str, Any], ...]
]:
    """Validate all v2 identities without reading a chunk through an inferred path."""

    _require_text(expected_trajectory_id, "expected_trajectory_id")
    _require_sha256(expected_manifest_sha256, "expected_manifest_sha256")
    if document.get("format_version") != ACTIVATION_INDEX_V2_FORMAT_VERSION:
        _fail("unsupported_format", "Document is not Activation Index v2.")
    if document.get("schema_version") != ACTIVATION_V1_SCHEMA_VERSION:
        _fail("invalid_schema_version", "Index schema_version must equal '1.0'.")
    if document.get("run_status") != "completed":
        _fail("invalid_run_status", "Activation Index v2 must be completed.")
    store = _validate_store_identity(
        document.get("store_identity"),
        expected_manifest_sha256=expected_manifest_sha256,
    )
    chunks_value = document.get("chunks")
    rows_value = document.get("index_rows")
    if not isinstance(chunks_value, list) or not chunks_value:
        _fail("invalid_index", "Index must declare non-empty chunks.")
    if not isinstance(rows_value, list) or not rows_value:
        _fail("invalid_index", "Index must declare non-empty index_rows.")

    chunks: list[Mapping[str, Any]] = []
    chunks_by_id: dict[str, Mapping[str, Any]] = {}
    required_chunk_fields = {
        "byte_size",
        "chunk_id",
        "dtype",
        "first_scientific_key",
        "hidden_width",
        "last_scientific_key",
        "layer_idx",
        "path",
        "row_count",
        "sha256",
    }
    for position, value in enumerate(chunks_value):
        if not isinstance(value, Mapping):
            _fail("invalid_chunk_descriptor", f"chunks[{position}] must be an object.")
        missing = sorted(required_chunk_fields - set(value))
        if missing:
            _fail("invalid_chunk_descriptor", f"chunks[{position}] misses {missing}.")
        chunk_id = _require_text(value.get("chunk_id"), "chunk.chunk_id")
        if chunk_id in chunks_by_id:
            _fail("duplicate_chunk", f"Duplicate chunk identity {chunk_id!r}.")
        _safe_relative_chunk_path(value.get("path"))
        _require_sha256(value.get("sha256"), "chunk.sha256")
        _require_int(value.get("byte_size"), "chunk.byte_size", minimum=1)
        _require_int(value.get("row_count"), "chunk.row_count", minimum=1)
        if value.get("dtype") != EXPECTED_DTYPE:
            _fail("invalid_dtype", f"Chunk {chunk_id!r} is not float32.")
        if value.get("hidden_width") != store["hidden_width"]:
            _fail("shape_mismatch", f"Chunk {chunk_id!r} hidden width is stale.")
        if value.get("layer_idx") not in store["requested_layers"]:
            _fail("invalid_layer", f"Chunk {chunk_id!r} uses an unfrozen layer.")
        if not isinstance(value.get("first_scientific_key"), Mapping) or not isinstance(
            value.get("last_scientific_key"), Mapping
        ):
            _fail("invalid_chunk_descriptor", "Chunk key bounds must be objects.")
        chunks_by_id[chunk_id] = value
        chunks.append(value)

    required_row_fields = {
        "accepted_manifest_hash",
        "activation_chunk_id",
        "c_frame_map_row_sha256",
        "c_frame_map_sha256",
        "c_state_row_sha256",
        "c_state_sha256",
        "checkpoint_hash",
        "chunk_row_idx",
        "code_sha",
        "config_hash",
        "context_local_pair_idx",
        "dtype",
        "exclusion_reason",
        "frame_token_map_sha256",
        "frame_token_positions",
        "global_model_frame_idx",
        "hook_site",
        "layer_idx",
        "model_hash",
        "pooling_method",
        "preprocess_hash",
        "run_id",
        "run_status",
        "schema_version",
        "source_frame_id",
        "source_frame_idx",
        "source_tick",
        "status",
        "store_format_version",
        "superseded_by",
        "token_region",
        "trajectory_id",
        "vector_shape",
    }
    rows: list[Mapping[str, Any]] = []
    scientific_keys: set[tuple[Any, ...]] = set()
    physical_keys: set[tuple[str, int]] = set()
    rows_by_chunk: dict[str, list[Mapping[str, Any]]] = {}
    for position, row in enumerate(rows_value):
        if not isinstance(row, Mapping):
            _fail("invalid_index_row", f"index_rows[{position}] must be an object.")
        if "model_frame_idx" in row:
            _fail(
                "v1_reinterpretation_forbidden",
                "A v2 row cannot contain ambiguous v1 model_frame_idx.",
            )
        missing = sorted(required_row_fields - set(row))
        if missing:
            _fail("invalid_index_row", f"index_rows[{position}] misses {missing}.")
        global_idx = _require_int(
            row.get("global_model_frame_idx"), "global_model_frame_idx"
        )
        local_idx = _require_int(
            row.get("context_local_pair_idx"),
            "context_local_pair_idx",
            maximum=MAX_CONTEXT_LOCAL_PAIR_IDX,
        )
        positions = row.get("frame_token_positions")
        if not isinstance(positions, list) or tuple(
            positions
        ) != derive_visual_token_positions(local_idx):
            _fail(
                "invalid_token_positions",
                "Token positions must derive only from context_local_pair_idx.",
            )
        if row.get("trajectory_id") != expected_trajectory_id:
            _fail("trajectory_mismatch", "Index row crosses its trajectory boundary.")
        if row.get("source_frame_id") != (
            f"{expected_trajectory_id}:render_frame:{global_idx}"
        ):
            _fail("source_identity_mismatch", "source_frame_id is not exact.")
        if (
            row.get("source_frame_idx") != global_idx
            or row.get("source_tick") != global_idx
        ):
            _fail(
                "source_identity_mismatch", "Source frame/tick identity is not exact."
            )
        expected_identity = {
            "accepted_manifest_hash": expected_manifest_sha256,
            "checkpoint_hash": store["checkpoint_hash"],
            "code_sha": store["code_sha"],
            "config_hash": store["config_hash"],
            "dtype": EXPECTED_DTYPE,
            "hook_site": store["hook_site"],
            "model_hash": store["model_hash"],
            "preprocess_hash": store["preprocess_hash"],
            "run_id": store["run_id"],
            "run_status": "completed",
            "schema_version": ACTIVATION_V1_SCHEMA_VERSION,
            "store_format_version": ACTIVATION_STORE_V2_FORMAT_VERSION,
        }
        if any(
            row.get(field) != expected for field, expected in expected_identity.items()
        ):
            _fail("identity_mismatch", "Index row conflicts with its store identity.")
        if (
            row.get("status") != "accepted"
            or row.get("exclusion_reason") is not None
            or row.get("superseded_by") is not None
            or row.get("pooling_method") != "mean"
            or row.get("token_region") != "visual"
            or row.get("vector_shape") != [store["hidden_width"]]
        ):
            _fail(
                "invalid_index_row", "Index row lifecycle/storage metadata is invalid."
            )
        layer_idx = _require_int(row.get("layer_idx"), "layer_idx")
        if layer_idx not in store["requested_layers"]:
            _fail("invalid_layer", "Index row uses an unfrozen layer.")
        for field in (
            "c_frame_map_row_sha256",
            "c_frame_map_sha256",
            "c_state_row_sha256",
            "c_state_sha256",
            "frame_token_map_sha256",
        ):
            _require_sha256(row.get(field), field)
        scientific = _scientific_key(row)
        if scientific in scientific_keys:
            _fail("duplicate_activation_identity", "Scientific identity collision.")
        scientific_keys.add(scientific)
        chunk_id = _require_text(row.get("activation_chunk_id"), "activation_chunk_id")
        chunk_row_idx = _require_int(row.get("chunk_row_idx"), "chunk_row_idx")
        if chunk_id not in chunks_by_id:
            _fail("unknown_chunk", f"Index row references unknown chunk {chunk_id!r}.")
        physical = (chunk_id, chunk_row_idx)
        if physical in physical_keys:
            _fail("duplicate_chunk_row", f"Duplicate physical identity {physical!r}.")
        physical_keys.add(physical)
        rows_by_chunk.setdefault(chunk_id, []).append(row)
        rows.append(row)

    if set(rows_by_chunk) != set(chunks_by_id):
        _fail("chunk_coverage_mismatch", "Index and descriptor chunk sets differ.")
    for chunk_id, descriptor in chunks_by_id.items():
        claimed = sorted(rows_by_chunk[chunk_id], key=lambda row: row["chunk_row_idx"])
        expected_count = descriptor["row_count"]
        if [row["chunk_row_idx"] for row in claimed] != list(range(expected_count)):
            _fail(
                "chunk_coverage_mismatch", f"Chunk {chunk_id!r} row coverage differs."
            )
        if any(row["layer_idx"] != descriptor["layer_idx"] for row in claimed):
            _fail("invalid_layer", f"Chunk {chunk_id!r} mixes layer identities.")
        if _scientific_key_document(claimed[0]) != dict(
            descriptor["first_scientific_key"]
        ) or _scientific_key_document(claimed[-1]) != dict(
            descriptor["last_scientific_key"]
        ):
            _fail("chunk_key_mismatch", f"Chunk {chunk_id!r} key bounds differ.")

    snapshot_id = _require_sha256(document.get("snapshot_id"), "snapshot_id")
    if snapshot_id != person_a_activation_index_v2_snapshot_digest(
        document,
        canonicalization_contract=canonicalization_contract,
    ):
        _fail("snapshot_identity_mismatch", "snapshot_id is not the canonical digest.")
    return store, tuple(chunks), tuple(rows)


def dispatch_activation_document(
    document: Mapping[str, Any],
    *,
    canonicalization_contract: str | None = None,
    expected_trajectory_id: str | None = None,
    expected_manifest_sha256: str | None = None,
) -> ActivationDispatchResult:
    """Dispatch v1 and v2 explicitly while preserving historical v1 behavior."""

    if not isinstance(document, Mapping):
        _fail("invalid_document", "Activation evidence must be an object.")
    version = document.get("format_version")
    if version is None:
        if canonicalization_contract is not None:
            _fail(
                "canonicalization_identity_conflict",
                "Historical v1 dispatch cannot claim a v2 canonicalization contract.",
            )
        result = validate_activation_handoff(document)
        return ActivationDispatchResult(
            format_version="person-b-historical-activation-handoff-v1",
            accepted=result.accepted,
            rejection_codes=tuple(item.code.value for item in result.rejections),
        )
    if version != ACTIVATION_INDEX_V2_FORMAT_VERSION:
        _fail("unsupported_format", f"Unsupported activation format {version!r}.")
    if (
        canonicalization_contract is None
        or expected_trajectory_id is None
        or expected_manifest_sha256 is None
    ):
        _fail(
            "missing_authority",
            "v2 dispatch requires canonicalization, trajectory, and C authority.",
        )
    try:
        _validate_index_document_v2(
            document,
            canonicalization_contract=canonicalization_contract,
            expected_trajectory_id=expected_trajectory_id,
            expected_manifest_sha256=expected_manifest_sha256,
        )
    except ActivationV2ConsumerError as error:
        return ActivationDispatchResult(
            format_version=ACTIVATION_INDEX_V2_FORMAT_VERSION,
            accepted=False,
            rejection_codes=(error.code,),
        )
    return ActivationDispatchResult(
        format_version=ACTIVATION_INDEX_V2_FORMAT_VERSION,
        accepted=True,
        rejection_codes=(),
    )


def external_chunk_bindings(
    values: Sequence[Mapping[str, Any]],
) -> dict[str, ExternalChunkBinding]:
    """Normalize an explicit inventory without inferring any filesystem path."""

    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        _fail("invalid_inventory", "Chunk inventory must be a sequence.")
    result: dict[str, ExternalChunkBinding] = {}
    for position, value in enumerate(values):
        if not isinstance(value, Mapping):
            _fail("invalid_inventory", f"Chunk inventory row {position} is invalid.")
        chunk_id = _require_text(value.get("chunk_id"), "inventory.chunk_id")
        if chunk_id in result:
            _fail("duplicate_chunk", f"Duplicate inventory chunk {chunk_id!r}.")
        path = Path(_require_text(value.get("path"), "inventory.path"))
        if not path.is_absolute():
            _fail(
                "invalid_chunk_path",
                "External chunk paths must be explicit and absolute.",
            )
        result[chunk_id] = ExternalChunkBinding(
            chunk_id=chunk_id,
            path=path,
            sha256=_require_sha256(value.get("sha256"), "inventory.sha256"),
            byte_size=_require_int(
                value.get("byte_size"), "inventory.byte_size", minimum=1
            ),
            row_count=_require_int(
                value.get("row_count"), "inventory.row_count", minimum=1
            ),
        )
    if not result:
        _fail("invalid_inventory", "Chunk inventory cannot be empty.")
    return result


def validate_activation_index_v2_bytes(
    payload: bytes,
    *,
    canonicalization_contract: str,
    expected_index_sha256: str,
    expected_index_byte_size: int,
    expected_trajectory_id: str,
    expected_manifest_sha256: str,
) -> ValidatedActivationIndexV2:
    """Validate immutable Person A index bytes without reading activation chunks."""

    if not isinstance(payload, bytes):
        _fail("invalid_index_bytes", "Activation index payload must be literal bytes.")
    _require_sha256(expected_index_sha256, "activation_index.sha256")
    _require_int(
        expected_index_byte_size,
        "activation_index.byte_size",
        minimum=1,
    )
    if len(payload) != expected_index_byte_size:
        _fail("byte_size_mismatch", "activation_index byte size does not match.")
    actual_sha256 = _sha256_bytes(payload)
    if actual_sha256 != expected_index_sha256:
        _fail(
            "sha256_mismatch",
            "activation_index literal-byte SHA-256 does not match.",
        )
    document = _strict_json_bytes(payload, label="activation_index")
    expected_payload = canonical_json_bytes_for_artifact(
        document,
        artifact_type=PERSON_A_ACTIVATION_INDEX_V2_ARTIFACT_TYPE,
        canonicalization_contract=canonicalization_contract,
    )
    if payload != expected_payload:
        _fail(
            "noncanonical_index",
            "Activation Index v2 bytes differ from Person A producer canonical JSON.",
        )
    store, chunks, rows = _validate_index_document_v2(
        document,
        canonicalization_contract=canonicalization_contract,
        expected_trajectory_id=expected_trajectory_id,
        expected_manifest_sha256=expected_manifest_sha256,
    )
    return ValidatedActivationIndexV2(
        raw_sha256=actual_sha256,
        raw_byte_size=len(payload),
        document=dict(document),
        store_identity=dict(store),
        chunks=tuple(dict(chunk) for chunk in chunks),
        rows=tuple(dict(row) for row in rows),
    )


def load_activation_index_v2(
    index_path: Path | str,
    *,
    canonicalization_contract: str,
    expected_index_sha256: str,
    expected_index_byte_size: int,
    expected_trajectory_id: str,
    expected_manifest_sha256: str,
    chunk_bindings: Mapping[str, ExternalChunkBinding],
    retain_vectors: bool,
) -> LoadedActivationIndexV2:
    """Verify one index and all exact NumPy chunks, failing closed on mismatch."""

    path = Path(index_path)
    payload = _read_exact_file(
        path,
        expected_sha256=expected_index_sha256,
        expected_byte_size=expected_index_byte_size,
        label="activation_index",
    )
    validated = validate_activation_index_v2_bytes(
        payload,
        canonicalization_contract=canonicalization_contract,
        expected_index_sha256=expected_index_sha256,
        expected_index_byte_size=expected_index_byte_size,
        expected_trajectory_id=expected_trajectory_id,
        expected_manifest_sha256=expected_manifest_sha256,
    )
    store = validated.store_identity
    chunks = validated.chunks
    rows = validated.rows
    descriptors = {str(chunk["chunk_id"]): chunk for chunk in chunks}
    if set(descriptors) != set(chunk_bindings):
        _fail("chunk_coverage_mismatch", "Index and external inventory sets differ.")

    arrays: dict[str, np.ndarray] = {}
    references = Counter(str(row["activation_chunk_id"]) for row in rows)
    for chunk_id in sorted(descriptors):
        descriptor = descriptors[chunk_id]
        binding = chunk_bindings[chunk_id]
        if (
            descriptor["sha256"] != binding.sha256
            or descriptor["byte_size"] != binding.byte_size
            or descriptor["row_count"] != binding.row_count
            or references[chunk_id] != binding.row_count
        ):
            _fail("inventory_mismatch", f"Chunk {chunk_id!r} differs from inventory.")
        chunk_payload = _read_exact_file(
            binding.path,
            expected_sha256=binding.sha256,
            expected_byte_size=binding.byte_size,
            label=f"activation_chunk:{chunk_id}",
        )
        try:
            # Load the exact bytes just authenticated above.  Reopening the path
            # would create a verification/load race on a mutable external store.
            array = np.load(io.BytesIO(chunk_payload), allow_pickle=False)
        except (OSError, ValueError) as error:
            _fail("invalid_npy", f"Could not load chunk {chunk_id!r}: {error}")
        expected_shape = (binding.row_count, descriptor["hidden_width"])
        if array.shape != expected_shape:
            _fail("shape_mismatch", f"Chunk {chunk_id!r} has shape {array.shape}.")
        if array.dtype != np.dtype(np.float32):
            _fail("invalid_dtype", f"Chunk {chunk_id!r} must be float32.")
        if not bool(np.isfinite(array).all()):
            _fail("nonfinite_vector", f"Chunk {chunk_id!r} contains non-finite values.")
        if retain_vectors:
            array.setflags(write=False)
            arrays[chunk_id] = array

    return LoadedActivationIndexV2(
        trajectory_id=expected_trajectory_id,
        index_path=path,
        index_sha256=expected_index_sha256,
        index_byte_size=expected_index_byte_size,
        store_identity=dict(store),
        rows=tuple(dict(row) for row in rows),
        chunks=tuple(dict(chunk) for chunk in chunks),
        arrays_by_chunk_id=arrays,
    )


__all__ = [
    "ACTIVATION_INDEX_V2_FORMAT_VERSION",
    "ACTIVATION_STORE_V2_FORMAT_VERSION",
    "PERSON_A_ACTIVATION_INDEX_V2_ARTIFACT_TYPE",
    "PERSON_A_ACTIVATION_INDEX_V2_CANONICALIZATION_CONTRACT",
    "PERSON_A_ACTIVATION_STORE_V2_PRODUCER_COMMIT",
    "PERSON_A_ACTIVATION_STORE_V2_PRODUCER_SHA256",
    "REGISTRY_V2_CANONICALIZATION_CONTRACT",
    "REGISTRY_V2_RECORD_ARTIFACT_TYPE",
    "ActivationDispatchResult",
    "ActivationV2ConsumerError",
    "ExternalChunkBinding",
    "LoadedActivationIndexV2",
    "ValidatedActivationIndexV2",
    "canonical_json_bytes_for_artifact",
    "derive_visual_token_positions",
    "dispatch_activation_document",
    "external_chunk_bindings",
    "load_activation_index_v2",
    "person_a_activation_index_v2_canonical_json_bytes",
    "person_a_activation_index_v2_snapshot_digest",
    "validate_activation_index_v2_bytes",
]
