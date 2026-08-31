"""Activation serialization, inventory and validation (authority 8.5).

For each **capture x layer x temporal slice**, exactly one array:

    shape  [19, 336, 2048]
    dtype  float16, little-endian ("<f2")
    bytes  19 * (336 * 2048 * 2) + 128 = 26,148,992

The 128-byte NumPy v1 header is part of the frozen expected size. The legacy
inventory validator at ``regime_a_execution.py:62-97`` hard-codes 20 layers and
``target_tau == range(1,20)``; Experiment III persists **3 layers x 2 slices = 6**
arrays per capture, so the contract is generalized here rather than reused.

The validator is deliberately independent of the writer: it re-reads the bytes
and re-derives every property rather than trusting the inventory.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np

from mineocclude.experiment_iii.authority import (
    TARGET_ROWS_PER_CAPTURE,
    canonical_sha256,
    sha256_file,
)
from mineocclude.experiment_iii.errors import ExperimentIIIError
from mineocclude.experiment_iii.extraction import SELECTED_LAYERS
from mineocclude.experiment_iii.namespace import guard_write_path
from mineocclude.experiment_iii.schema import TemporalSlice
from mineocclude.experiment_iii.slices import HIDDEN_WIDTH, VISUAL_TOKENS_PER_PAIR

__all__ = [
    "EXPECTED_SHAPE",
    "EXPECTED_DTYPE",
    "BYTES_PER_ROW_TENSOR",
    "NPY_HEADER_BYTES",
    "EXPECTED_NPY_BYTES",
    "UNITS_PER_CAPTURE",
    "ActivationBinding",
    "array_relative_path",
    "write_activation_array",
    "build_extraction_inventory",
    "validate_activation_array",
    "validate_extraction_inventory",
]

EXPECTED_SHAPE = (TARGET_ROWS_PER_CAPTURE, VISUAL_TOKENS_PER_PAIR, HIDDEN_WIDTH)
EXPECTED_DTYPE = "<f2"
BYTES_PER_ROW_TENSOR = VISUAL_TOKENS_PER_PAIR * HIDDEN_WIDTH * 2  # 1,376,256
NPY_HEADER_BYTES = 128
EXPECTED_NPY_BYTES = (
    TARGET_ROWS_PER_CAPTURE * BYTES_PER_ROW_TENSOR + NPY_HEADER_BYTES
)  # 26,148,992
UNITS_PER_CAPTURE = len(SELECTED_LAYERS) * len(TemporalSlice)  # 6


@dataclass(frozen=True)
class ActivationBinding:
    """Everything authority 8.5 requires one persisted array to bind."""

    identity: str
    condition_id: str
    layer: int
    temporal_slice: str
    target_model_frame_indices: tuple[int, ...]
    hook_site: str
    token_position_hash: str
    preprocessing_identity: str
    checkpoint_identity: str
    source_capture_hash: str
    shape: tuple[int, ...] = EXPECTED_SHAPE
    dtype: str = EXPECTED_DTYPE
    byte_size: int = EXPECTED_NPY_BYTES
    sha256: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "identity": self.identity,
            "condition_id": self.condition_id,
            "layer": self.layer,
            "temporal_slice": self.temporal_slice,
            "target_model_frame_indices": list(self.target_model_frame_indices),
            "hook_site": self.hook_site,
            "token_position_hash": self.token_position_hash,
            "preprocessing_identity": self.preprocessing_identity,
            "checkpoint_identity": self.checkpoint_identity,
            "source_capture_hash": self.source_capture_hash,
            "shape": list(self.shape),
            "dtype": self.dtype,
            "byte_size": self.byte_size,
            "sha256": self.sha256,
            "path": array_relative_path(self.layer, self.temporal_slice),
        }


def array_relative_path(layer: int, temporal_slice: str | TemporalSlice) -> str:
    name = TemporalSlice(temporal_slice).value
    return f"activations/layer_{int(layer):02d}/{name}.npy"


def _atomic_write(target: Path, payload: bytes) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".tmp")
    with temporary.open("wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, target)


def write_activation_array(
    root: Path,
    layer: int,
    temporal_slice: str | TemporalSlice,
    array: np.ndarray,
    *,
    namespace_root: Path | None = None,
) -> dict[str, Any]:
    """Persist one [19,336,2048] little-endian float16 array atomically."""
    values = np.asarray(array)
    if values.shape != EXPECTED_SHAPE:
        raise ExperimentIIIError(
            "TENSOR_SHAPE_MISMATCH",
            f"array is {values.shape}, expected {EXPECTED_SHAPE}",
        )
    if not np.isfinite(values.astype(np.float32)).all():
        raise ExperimentIIIError(
            "TENSOR_NONFINITE", "activation array contains NaN or infinity"
        )
    encoded = np.ascontiguousarray(values, dtype=EXPECTED_DTYPE)

    import io

    buffer = io.BytesIO()
    np.save(buffer, encoded, allow_pickle=False)
    payload = buffer.getvalue()
    if len(payload) != EXPECTED_NPY_BYTES:
        raise ExperimentIIIError(
            "TENSOR_BYTE_SIZE_MISMATCH",
            f"serialized array is {len(payload)} bytes, expected "
            f"{EXPECTED_NPY_BYTES}",
        )
    relative = array_relative_path(layer, temporal_slice)
    target = guard_write_path(Path(root) / relative, root=namespace_root)
    _atomic_write(target, payload)
    return {
        "path": relative,
        "byte_size": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "shape": list(EXPECTED_SHAPE),
        "dtype": EXPECTED_DTYPE,
    }


def build_extraction_inventory(
    *,
    identity: str,
    condition_id: str,
    target_model_frame_indices: Sequence[int],
    written: Mapping[tuple[int, str], Mapping[str, Any]],
    hook_site: str,
    preprocessing_identity: str,
    checkpoint_identity: str,
    source_capture_hash: str,
    token_position_hash: str,
) -> dict[str, Any]:
    """The Experiment III inventory: 3 layers x 2 slices, not 20 layers."""
    artifacts = []
    for layer in SELECTED_LAYERS:
        for name in TemporalSlice:
            key = (layer, name.value)
            if key not in written:
                raise ExperimentIIIError(
                    "EXTRACTION_INVENTORY_INCOMPLETE",
                    f"no persisted array for layer {layer} slice {name.value}",
                )
            record = written[key]
            binding = ActivationBinding(
                identity=identity,
                condition_id=condition_id,
                layer=layer,
                temporal_slice=name.value,
                target_model_frame_indices=tuple(target_model_frame_indices),
                hook_site=hook_site,
                token_position_hash=token_position_hash,
                preprocessing_identity=preprocessing_identity,
                checkpoint_identity=checkpoint_identity,
                source_capture_hash=source_capture_hash,
                sha256=str(record["sha256"]),
                byte_size=int(record["byte_size"]),
            )
            artifacts.append(binding.as_dict())
    body = {
        "schema_version": "mineocclude-experiment-iii-extraction-inventory-v1",
        "authority_section": "8.5",
        "identity": identity,
        "condition_id": condition_id,
        "layer_indices": list(SELECTED_LAYERS),
        "temporal_slices": [name.value for name in TemporalSlice],
        "units_per_capture": UNITS_PER_CAPTURE,
        "target_model_frame_indices": list(target_model_frame_indices),
        "expected_shape": list(EXPECTED_SHAPE),
        "expected_dtype": EXPECTED_DTYPE,
        "expected_byte_size": EXPECTED_NPY_BYTES,
        "artifacts": artifacts,
    }
    body["inventory_sha256"] = canonical_sha256(body)
    return body


def validate_activation_array(
    path: Path,
    binding: Mapping[str, Any],
    *,
    expected_target_rows: Sequence[int] | None = None,
) -> None:
    """Independently revalidate one persisted array from its bytes."""
    path = Path(path)
    if not path.is_file():
        raise ExperimentIIIError(
            "EXTRACTION_INVENTORY_INCOMPLETE", f"activation array is absent: {path}"
        )
    size = path.stat().st_size
    if size != EXPECTED_NPY_BYTES:
        raise ExperimentIIIError(
            "TENSOR_BYTE_SIZE_MISMATCH",
            f"{path.name} is {size} bytes, expected {EXPECTED_NPY_BYTES}",
        )
    if int(binding.get("byte_size", -1)) != EXPECTED_NPY_BYTES:
        raise ExperimentIIIError(
            "TENSOR_BYTE_SIZE_MISMATCH",
            "inventory records the wrong byte size for this array",
        )
    digest = sha256_file(path)
    if digest != binding.get("sha256"):
        raise ExperimentIIIError(
            "TENSOR_HASH_MISMATCH",
            f"{path.name} hashes {digest}, inventory records {binding.get('sha256')}",
        )
    array = np.load(path, allow_pickle=False)
    if array.shape != EXPECTED_SHAPE:
        raise ExperimentIIIError(
            "TENSOR_SHAPE_MISMATCH",
            f"{path.name} is {array.shape}, expected {EXPECTED_SHAPE}",
        )
    if array.dtype.str != EXPECTED_DTYPE:
        raise ExperimentIIIError(
            "TENSOR_DTYPE_MISMATCH",
            f"{path.name} dtype is {array.dtype.str}, expected {EXPECTED_DTYPE} "
            "(little-endian float16)",
        )
    if array.size == 0:
        raise ExperimentIIIError("TENSOR_SHAPE_MISMATCH", "array is empty")
    if not np.isfinite(array.astype(np.float32)).all():
        raise ExperimentIIIError(
            "TENSOR_NONFINITE", f"{path.name} contains NaN or infinity"
        )
    if int(binding["layer"]) not in SELECTED_LAYERS:
        raise ExperimentIIIError(
            "HOOK_LAYER_MISSING",
            f"layer {binding['layer']} is not in {SELECTED_LAYERS}",
        )
    TemporalSlice(binding["temporal_slice"])
    for field in (
        "hook_site",
        "token_position_hash",
        "preprocessing_identity",
        "checkpoint_identity",
        "source_capture_hash",
    ):
        if not binding.get(field):
            raise ExperimentIIIError(
                "PROVENANCE_BINDING_MISSING",
                f"{path.name} does not bind {field}",
            )
    if expected_target_rows is not None:
        if list(binding["target_model_frame_indices"]) != list(expected_target_rows):
            raise ExperimentIIIError(
                "TARGET_ROW_MISMATCH",
                "persisted target index order does not match the manifest",
            )


def validate_extraction_inventory(
    root: Path,
    inventory: Mapping[str, Any],
    *,
    expected_target_rows: Sequence[int] | None = None,
    source_capture_hash: str | None = None,
    checkpoint_identity: str | None = None,
    preprocessing_identity: str | None = None,
) -> list[dict[str, Any]]:
    """Independently revalidate a complete capture's six arrays."""
    if list(inventory.get("layer_indices", [])) != list(SELECTED_LAYERS):
        raise ExperimentIIIError(
            "EXTRACTION_INVENTORY_INCOMPLETE",
            f"inventory layers {inventory.get('layer_indices')} are not "
            f"{list(SELECTED_LAYERS)}; the legacy 20-layer contract is superseded",
        )
    if sorted(inventory.get("temporal_slices", [])) != sorted(
        name.value for name in TemporalSlice
    ):
        raise ExperimentIIIError(
            "EXTRACTION_INVENTORY_INCOMPLETE",
            "inventory does not carry both temporal slices",
        )
    artifacts = inventory.get("artifacts")
    if not isinstance(artifacts, list) or len(artifacts) != UNITS_PER_CAPTURE:
        raise ExperimentIIIError(
            "EXTRACTION_INVENTORY_INCOMPLETE",
            f"expected {UNITS_PER_CAPTURE} artifacts, got "
            f"{len(artifacts) if isinstance(artifacts, list) else artifacts}",
        )
    seen = {(int(row["layer"]), row["temporal_slice"]) for row in artifacts}
    expected = {(layer, name.value) for layer in SELECTED_LAYERS for name in TemporalSlice}
    if seen != expected:
        raise ExperimentIIIError(
            "EXTRACTION_INVENTORY_INCOMPLETE",
            f"artifact set {sorted(seen)} does not equal {sorted(expected)}",
        )

    validated = []
    for row in artifacts:
        relative = str(row["path"])
        pure = Path(relative)
        if pure.is_absolute() or ".." in pure.parts:
            raise ExperimentIIIError(
                "PROVENANCE_NAMESPACE_VIOLATION",
                f"unsafe activation artifact path: {relative}",
            )
        path = Path(root) / relative
        validate_activation_array(
            path, row, expected_target_rows=expected_target_rows
        )
        if source_capture_hash is not None and row["source_capture_hash"] != (
            source_capture_hash
        ):
            raise ExperimentIIIError(
                "EXTRACTION_SOURCE_CAPTURE_DRIFT",
                f"{relative} binds a different source capture",
            )
        if checkpoint_identity is not None and row["checkpoint_identity"] != (
            checkpoint_identity
        ):
            raise ExperimentIIIError(
                "ENV_CHECKPOINT_HASH_MISMATCH",
                f"{relative} binds a different checkpoint",
            )
        if preprocessing_identity is not None and row["preprocessing_identity"] != (
            preprocessing_identity
        ):
            raise ExperimentIIIError(
                "ENV_PREPROCESSING_IDENTITY_MISMATCH",
                f"{relative} binds a different preprocessing identity",
            )
        validated.append({"path": relative, "sha256": row["sha256"]})
    return validated
