"""The A11 feature block store (authority 8.7, 8.9.1; inventory A11/A12).

A11 builds the frozen representations and A12 fits on them. Nothing between the
two stages may re-derive a feature block from scratch: the expected artifact
inventory names ``data/experiment_iii/features/<representation>/<capture_unit_id>.npy``
precisely so the blocks A12 fits are the blocks A11 hashed, byte for byte.

This module owns that seam, and only that seam. It chooses no representation --
the recipes live in :mod:`representations` and :mod:`baselines_pixel` under P2 --
and it computes no statistic. It builds a block, writes it, reads it back, and
hashes it the one way :mod:`build_features` hashes it, so a block that moved
between A11 and A12 is ``FEATURE_BLOCK_DRIFT`` rather than a silent re-analysis.

Block names are directory names, not scientific quantities. ``PIXEL_BASELINE``
is the filesystem name of the §8.9.1 baseline whose required manuscript language
remains :data:`baselines_pixel.PIXEL_BASELINE_NAME`.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence

import numpy as np

from mineocclude.experiment_iii.authority import TARGET_ROWS_PER_CAPTURE
from mineocclude.experiment_iii.baselines_pixel import (
    PIXEL_FEATURE_DIM,
    pixel_features,
)
from mineocclude.experiment_iii.errors import ExperimentIIIError
from mineocclude.experiment_iii.extraction import SELECTED_LAYERS
from mineocclude.experiment_iii.representations import (
    COARSE_DIMENSION,
    TWO_FRAME_DIMENSION,
    coarse_2x6_concat,
    current_minus_previous,
    two_frame_concat,
)

__all__ = [
    "FEATURE_ROOT",
    "PRIMARY_LAYER",
    "DEPTH_PANEL_LAYERS",
    "PIXEL_BLOCK",
    "BLOCK_DIMENSIONS",
    "RIDGE_BLOCKS",
    "block_path",
    "block_digest",
    "build_activation_blocks",
    "build_pixel_block",
    "write_block",
    "read_block",
    "read_blocks_for_unit",
    "unit_id",
]

#: Inventory A11: ``data/experiment_iii/features/<representation>/<unit>.npy``.
FEATURE_ROOT = Path("data") / "experiment_iii" / "features"

#: Authority 8.8 -- the frozen primary cell is layer 19.
PRIMARY_LAYER = 19

#: Authority 8.12 family E -- descriptive depth panel only; these may never
#: replace or rescue the primary cell.
DEPTH_PANEL_LAYERS = (4, 10)

PIXEL_BLOCK = "PIXEL_BASELINE"

#: Every block A12 may fit a ridge on, with its frozen dimension.
BLOCK_DIMENSIONS: dict[str, int] = {
    "CURRENT": COARSE_DIMENSION,
    "CURRENT_MINUS_PREVIOUS": COARSE_DIMENSION,
    "TWO_FRAME_CONCAT": TWO_FRAME_DIMENSION,
    "CURRENT_L04": COARSE_DIMENSION,
    "CURRENT_L10": COARSE_DIMENSION,
    PIXEL_BLOCK: PIXEL_FEATURE_DIM,
}

#: The blocks that carry a grouped nested ridge (§8.8 and §8.9.1). The motion and
#: clock baselines of §8.9.2-8.9.5 fit no feature block and are absent here.
RIDGE_BLOCKS = tuple(BLOCK_DIMENSIONS)


def unit_id(identity: str, condition_id: str) -> str:
    return f"{identity}__{condition_id}"


def _depth_block(layer: int) -> str:
    return f"CURRENT_L{layer:02d}"


def block_path(root: Path, block: str, capture_unit_id: str) -> Path:
    if block not in BLOCK_DIMENSIONS:
        raise ExperimentIIIError(
            "FEATURE_DIMENSION_MISMATCH",
            f"{block!r} is not one of the frozen feature blocks "
            f"{sorted(BLOCK_DIMENSIONS)}",
        )
    return Path(root) / block / f"{capture_unit_id}.npy"


def block_digest(matrix: np.ndarray) -> str:
    """The one hashing convention shared by A11 and A12.

    Contiguous float64 bytes. A11 records this digest in ``feature_config.json``
    and A12 re-derives it from the stored block; the two must agree or the block
    moved after it was hashed.
    """
    return hashlib.sha256(
        np.ascontiguousarray(matrix, dtype=np.float64).tobytes()
    ).hexdigest()


def _activation_path(root: Path, capture_unit_id: str, layer: int, slice_name: str) -> Path:
    return Path(root) / capture_unit_id / f"layer{layer:02d}_{slice_name.lower()}.npy"


def _load_slices(
    activations: Path, capture_unit_id: str, layer: int
) -> tuple[np.ndarray, np.ndarray]:
    current_path = _activation_path(activations, capture_unit_id, layer, "CURRENT")
    previous_path = _activation_path(activations, capture_unit_id, layer, "PREVIOUS")
    for path in (current_path, previous_path):
        if not path.is_file():
            raise ExperimentIIIError(
                "PROVENANCE_BINDING_MISSING", f"A11 needs {path}, which is absent"
            )
    current = np.load(current_path).astype(np.float64)
    previous = np.load(previous_path).astype(np.float64)
    if current.shape != previous.shape:
        raise ExperimentIIIError(
            "FEATURE_DIMENSION_MISMATCH",
            f"{capture_unit_id} layer {layer}: CURRENT {current.shape} != "
            f"PREVIOUS {previous.shape}",
        )
    if current.shape[0] != TARGET_ROWS_PER_CAPTURE:
        raise ExperimentIIIError(
            "FEATURE_ROW_ORDER_MISMATCH",
            f"{capture_unit_id} layer {layer} holds {current.shape[0]} rows, the "
            f"authority freezes {TARGET_ROWS_PER_CAPTURE}",
        )
    return current, previous


def build_activation_blocks(
    activations: Path,
    capture_unit_id: str,
    *,
    primary_layer: int = PRIMARY_LAYER,
    depth_layers: Sequence[int] = DEPTH_PANEL_LAYERS,
) -> dict[str, np.ndarray]:
    """The activation-derived blocks for one capture unit, in frozen row order.

    The three temporal representations come from the primary layer. The depth
    panel adds ``CURRENT`` at the other two frozen layers, which authority 8.12
    family E reports descriptively and 8.8 forbids from replacing layer 19.
    """
    for layer in (primary_layer, *depth_layers):
        if layer not in SELECTED_LAYERS:
            raise ExperimentIIIError(
                "FEATURE_DIMENSION_MISMATCH",
                f"layer {layer} is not one of the frozen {list(SELECTED_LAYERS)}",
            )
    current, previous = _load_slices(activations, capture_unit_id, primary_layer)
    blocks: dict[str, np.ndarray] = {
        "CURRENT": np.stack([coarse_2x6_concat(row) for row in current]),
        "CURRENT_MINUS_PREVIOUS": np.stack(
            [
                current_minus_previous(row_c, row_p)
                for row_c, row_p in zip(current, previous)
            ]
        ),
        # PREVIOUS first. Swapping the operands yields the same shape and a
        # different feature space, which is FEATURE_SLICE_SWAPPED.
        "TWO_FRAME_CONCAT": np.stack(
            [
                two_frame_concat(row_p, row_c)
                for row_p, row_c in zip(previous, current)
            ]
        ),
    }
    for layer in depth_layers:
        depth_current, _ = _load_slices(activations, capture_unit_id, layer)
        blocks[_depth_block(layer)] = np.stack(
            [coarse_2x6_concat(row) for row in depth_current]
        )
    return blocks


def _frame_paths(capture_dir: Path, target_rows: Sequence[int]) -> list[Path]:
    """Map each target model-frame index to its raw capture PNG.

    Through ``raw/frame_map.jsonl`` rather than by formatting the index into a
    filename: the map is the artifact that binds a rendered frame to its tick,
    and a capture whose map disagrees with the naming convention must refuse
    rather than silently read the neighbouring frame.
    """
    map_path = Path(capture_dir) / "raw" / "frame_map.jsonl"
    if not map_path.is_file():
        raise ExperimentIIIError(
            "PROVENANCE_BINDING_MISSING",
            f"the pixel baseline needs {map_path}, which is absent",
        )
    by_index: dict[int, str] = {}
    with map_path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            by_index[int(record["render_frame_idx"])] = str(record["frame_path"])
    paths: list[Path] = []
    for row in target_rows:
        if int(row) not in by_index:
            raise ExperimentIIIError(
                "CAPTURE_MISSING_FRAME",
                f"{capture_dir.name} has no rendered frame for target row {row}",
            )
        paths.append(Path(capture_dir) / by_index[int(row)])
    return paths


def build_pixel_block(
    capture_dir: Path, target_rows: Sequence[int]
) -> np.ndarray:
    """The §8.9.1 block: one 4,032-value row per target frame, in row order."""
    from mineocclude.experiment_iii.p0_analysis import read_frame_rgb

    if len(target_rows) != TARGET_ROWS_PER_CAPTURE:
        raise ExperimentIIIError(
            "TARGET_ROW_MISMATCH",
            f"the pixel block needs {TARGET_ROWS_PER_CAPTURE} target rows, got "
            f"{len(target_rows)}",
        )
    rows = [
        pixel_features(read_frame_rgb(path))
        for path in _frame_paths(Path(capture_dir), target_rows)
    ]
    return np.stack(rows).astype(np.float64)


def _validate(block: str, matrix: np.ndarray, where: str) -> np.ndarray:
    expected = BLOCK_DIMENSIONS[block]
    if matrix.ndim != 2 or matrix.shape[1] != expected:
        raise ExperimentIIIError(
            "FEATURE_DIMENSION_MISMATCH",
            f"{where} {block} is {matrix.shape}, the authority freezes "
            f"(*, {expected})",
        )
    if matrix.shape[0] != TARGET_ROWS_PER_CAPTURE:
        raise ExperimentIIIError(
            "FEATURE_ROW_ORDER_MISMATCH",
            f"{where} {block} holds {matrix.shape[0]} rows, the authority freezes "
            f"{TARGET_ROWS_PER_CAPTURE}",
        )
    if not np.all(np.isfinite(matrix)):
        raise ExperimentIIIError(
            "FEATURE_NONFINITE", f"{where} {block} holds a non-finite value"
        )
    return matrix


def write_block(
    root: Path, block: str, capture_unit_id: str, matrix: np.ndarray
) -> str:
    """Persist one block and return its digest. Atomic within the block file."""
    matrix = _validate(block, np.asarray(matrix, dtype=np.float64), capture_unit_id)
    path = block_path(root, block, capture_unit_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    # np.save appends ".npy" to any path that does not already end in it, so the
    # temporary file is written through an explicit handle rather than by name.
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("wb") as handle:
        np.save(handle, np.ascontiguousarray(matrix, dtype=np.float64))
    tmp.replace(path)
    return block_digest(matrix)


def read_block(root: Path, block: str, capture_unit_id: str) -> np.ndarray:
    path = block_path(root, block, capture_unit_id)
    if not path.is_file():
        raise ExperimentIIIError(
            "PROVENANCE_BINDING_MISSING",
            f"A12 needs the A11 feature block {path}, which is absent; A11 must "
            f"run and persist its blocks before predictions can be locked",
        )
    return _validate(block, np.load(path).astype(np.float64), capture_unit_id)


def read_blocks_for_unit(
    root: Path,
    capture_unit_id: str,
    *,
    blocks: Sequence[str] = RIDGE_BLOCKS,
    expected_digests: Mapping[str, str] | None = None,
) -> dict[str, np.ndarray]:
    """Load one unit's blocks, refusing any that moved since A11 hashed them."""
    loaded: dict[str, np.ndarray] = {}
    for block in blocks:
        matrix = read_block(root, block, capture_unit_id)
        if expected_digests is not None:
            recorded = expected_digests.get(block)
            if recorded is None:
                raise ExperimentIIIError(
                    "PROVENANCE_BINDING_MISSING",
                    f"A11 recorded no digest for {capture_unit_id} {block}",
                )
            current = block_digest(matrix)
            if current != recorded:
                raise ExperimentIIIError(
                    "PREDICTION_LOCK_AFTER_STATISTICS",
                    f"{capture_unit_id} {block} hashes to {current} but A11 "
                    f"recorded {recorded}; a feature block moved between A11 and "
                    f"A12 and the lock would not describe what was fitted",
                )
        loaded[block] = matrix
    return loaded


def iter_units(
    identities: Sequence[str], conditions: Sequence[str]
) -> Iterator[tuple[str, str, str]]:
    for identity in identities:
        for condition in conditions:
            yield identity, condition, unit_id(identity, condition)


def store_inventory(root: Path) -> dict[str, Any]:
    """What is actually on disk, for a receipt. Reads no feature values."""
    counts: dict[str, int] = {}
    for block in BLOCK_DIMENSIONS:
        directory = Path(root) / block
        counts[block] = (
            len(list(directory.glob("*.npy"))) if directory.is_dir() else 0
        )
    return {"feature_root": Path(root).as_posix(), "blocks_on_disk": counts}
