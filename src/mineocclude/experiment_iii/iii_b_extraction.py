"""III-B extraction inventory -- L19 only, occluded plus VIS6 (authority 29.1).

III-B serializes **layer 19 only**, at both temporal slices. Layers 4 and 10 are
explicitly forbidden (authority 21.2): III-B is an uncertainty test, not another
representation search, so an inventory that carries them is a defect and not a
harmless surplus.

Two array shapes exist, and both byte counts include the 128-byte NumPy v1
header, exactly as III-A's ``A.18`` fixes it:

===============  ===================  ==============
occluded rows    ``[19, 336, 2048]``  26,148,992 B
``VIS6`` rows    ``[6, 336, 2048]``   8,257,664 B
===============  ===================  ==============
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Sequence

from mineocclude.experiment_iii.activation_store import (
    BYTES_PER_ROW_TENSOR,
    EXPECTED_DTYPE,
    EXPECTED_NPY_BYTES,
    EXPECTED_SHAPE,
    NPY_HEADER_BYTES,
)
from mineocclude.experiment_iii.errors import ExperimentIIIError
from mineocclude.experiment_iii.iii_b_vis import VIS_ROWS
from mineocclude.experiment_iii.schema import TemporalSlice

__all__ = [
    "III_B_LAYERS",
    "OCCLUDED_NPY_BYTES",
    "OCCLUDED_SHAPE",
    "VIS_NPY_BYTES",
    "VIS_SHAPE",
    "assert_only_l19_serialized",
    "expected_bytes_for",
    "iii_b_extraction_inventory",
    "validate_iii_b_array",
]

III_B_LAYERS = (19,)

OCCLUDED_SHAPE = EXPECTED_SHAPE
OCCLUDED_NPY_BYTES = EXPECTED_NPY_BYTES
VIS_SHAPE = (VIS_ROWS, EXPECTED_SHAPE[1], EXPECTED_SHAPE[2])
VIS_NPY_BYTES = VIS_ROWS * BYTES_PER_ROW_TENSOR + NPY_HEADER_BYTES


def expected_bytes_for(rows: int) -> int:
    """Serialized ``.npy`` size for ``rows`` row tensors, header included."""
    if rows not in (OCCLUDED_SHAPE[0], VIS_ROWS):
        raise ExperimentIIIError(
            "B_EXTRACTION_FAIL",
            f"III-B serializes {OCCLUDED_SHAPE[0]} occluded or {VIS_ROWS} visible "
            f"rows per array, not {rows}",
        )
    return rows * BYTES_PER_ROW_TENSOR + NPY_HEADER_BYTES


def assert_only_l19_serialized(layers: Iterable[int]) -> None:
    """Layers 4 and 10 are forbidden in III-B."""
    offending = sorted({int(layer) for layer in layers} - set(III_B_LAYERS))
    if offending:
        raise ExperimentIIIError(
            "B_EXTRACTION_FAIL",
            f"III-B serializes layer 19 only; {offending} is forbidden (authority 21.2)",
        )


def validate_iii_b_array(record: Mapping[str, Any]) -> None:
    """Shape, dtype and exact byte count for one persisted III-B array."""
    layer = int(record["layer"])
    assert_only_l19_serialized([layer])
    TemporalSlice(record["temporal_slice"])
    shape = tuple(int(value) for value in record["shape"])
    if shape not in (OCCLUDED_SHAPE, VIS_SHAPE):
        raise ExperimentIIIError(
            "B_EXTRACTION_FAIL",
            f"III-B arrays are {OCCLUDED_SHAPE} or {VIS_SHAPE}, got {shape}",
        )
    if record["dtype"] != EXPECTED_DTYPE:
        raise ExperimentIIIError(
            "B_EXTRACTION_FAIL",
            f"III-B arrays are little-endian float16 ({EXPECTED_DTYPE}), got "
            f"{record['dtype']!r}; a native-endian dtype is not byte-defined",
        )
    expected = expected_bytes_for(shape[0])
    if int(record["byte_size"]) != expected:
        raise ExperimentIIIError(
            "B_EXTRACTION_FAIL",
            f"a {shape[0]}-row III-B array is exactly {expected} bytes, got "
            f"{record['byte_size']}",
        )


def iii_b_extraction_inventory(
    capture_unit_ids: Sequence[str], *, with_vis: bool = True
) -> dict[str, Any]:
    """The expected ``B-EXT`` inventory: 2 slices x L19 x {occluded, VIS6}."""
    arrays: list[dict[str, Any]] = []
    for unit in capture_unit_ids:
        for layer in III_B_LAYERS:
            for temporal_slice in TemporalSlice:
                arrays.append(
                    {
                        "capture_unit_id": unit,
                        "layer": layer,
                        "temporal_slice": temporal_slice.value,
                        "window": "OCCLUDED",
                        "shape": list(OCCLUDED_SHAPE),
                        "dtype": EXPECTED_DTYPE,
                        "byte_size": OCCLUDED_NPY_BYTES,
                    }
                )
                if with_vis:
                    arrays.append(
                        {
                            "capture_unit_id": unit,
                            "layer": layer,
                            "temporal_slice": temporal_slice.value,
                            "window": "VIS6",
                            "shape": list(VIS_SHAPE),
                            "dtype": EXPECTED_DTYPE,
                            "byte_size": VIS_NPY_BYTES,
                        }
                    )
    for record in arrays:
        validate_iii_b_array(record)
    return {
        "schema_version": "mineocclude-experiment-iii-b-extraction-inventory-v1",
        "layers": list(III_B_LAYERS),
        "temporal_slices": [slice_.value for slice_ in TemporalSlice],
        "arrays": arrays,
        "array_count": len(arrays),
        "total_bytes": sum(record["byte_size"] for record in arrays),
    }
