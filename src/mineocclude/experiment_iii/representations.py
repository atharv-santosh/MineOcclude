"""Frozen feature representations (authority 8.7).

``COARSE_2X6_CONCAT``:

    source grid      14 x 24 tokens (rows x columns)
    coarse grid      2 x 6 cells
    tokens per cell  7 x 4 = 28
    cells            12, non-overlapping, exhaustive
    pooling          arithmetic mean over the 28 tokens, per hidden dimension
    concatenation    row-major over cells: (0,0),(0,1)...(0,5),(1,0)...(1,5)
    output           12 x 2048 = 24,576

The grid is **14 rows x 24 columns**, consistent with the projection at
``regime_a.py:312-337`` (``token_row = screen_y * 14/360``,
``token_col = screen_x * 24/640``). Reading it transposed produces
plausible-looking but wrong features that are undetectable downstream, so the
orientation is proved by an identity-encoding fixture rather than assumed.

Implemented **from specification**: the Experiment II source commit is not in this
object database, so no claim of literal source reuse may be made.

``mean_pool_visual_tokens`` (``activations/pool.py:437-556``) is a *global*
336-token mean and must never be used as the Experiment III representation.
"""

from __future__ import annotations

from typing import Sequence

import numpy as np

from mineocclude.experiment_iii.errors import ExperimentIIIError
from mineocclude.experiment_iii.slices import HIDDEN_WIDTH, VISUAL_TOKENS_PER_PAIR

__all__ = [
    "TOKEN_GRID_ROWS",
    "TOKEN_GRID_COLS",
    "COARSE_ROWS",
    "COARSE_COLS",
    "CELL_ROWS",
    "CELL_COLS",
    "TOKENS_PER_CELL",
    "CELL_COUNT",
    "COARSE_DIMENSION",
    "TWO_FRAME_DIMENSION",
    "cell_token_indices",
    "as_token_grid",
    "coarse_2x6_concat",
    "coarse_cells",
    "current_minus_previous",
    "two_frame_concat",
]

TOKEN_GRID_ROWS = 14
TOKEN_GRID_COLS = 24
COARSE_ROWS = 2
COARSE_COLS = 6
CELL_ROWS = TOKEN_GRID_ROWS // COARSE_ROWS  # 7
CELL_COLS = TOKEN_GRID_COLS // COARSE_COLS  # 4
TOKENS_PER_CELL = CELL_ROWS * CELL_COLS  # 28
CELL_COUNT = COARSE_ROWS * COARSE_COLS  # 12
COARSE_DIMENSION = CELL_COUNT * HIDDEN_WIDTH  # 24,576
TWO_FRAME_DIMENSION = 2 * COARSE_DIMENSION  # 49,152


def cell_token_indices(cell_row: int, cell_col: int) -> tuple[int, ...]:
    """Flat token indices of one 7x4 cell, in row-major grid order."""
    if not (0 <= cell_row < COARSE_ROWS and 0 <= cell_col < COARSE_COLS):
        raise ExperimentIIIError(
            "FEATURE_DIMENSION_MISMATCH",
            f"cell ({cell_row},{cell_col}) is outside the {COARSE_ROWS}x{COARSE_COLS} grid",
        )
    return tuple(
        row * TOKEN_GRID_COLS + col
        for row in range(cell_row * CELL_ROWS, (cell_row + 1) * CELL_ROWS)
        for col in range(cell_col * CELL_COLS, (cell_col + 1) * CELL_COLS)
    )


def as_token_grid(tokens: np.ndarray) -> np.ndarray:
    """Reshape ``[336, H]`` to ``[14, 24, H]``. Refuses a transposed grid."""
    array = np.asarray(tokens)
    if array.ndim == 3 and array.shape[:2] == (TOKEN_GRID_ROWS, TOKEN_GRID_COLS):
        return array
    if array.ndim == 3 and array.shape[:2] == (TOKEN_GRID_COLS, TOKEN_GRID_ROWS):
        raise ExperimentIIIError(
            "FEATURE_POOLING_GRID_TRANSPOSED",
            f"grid is {array.shape[:2]}, expected "
            f"({TOKEN_GRID_ROWS}, {TOKEN_GRID_COLS}) rows x columns",
        )
    if array.ndim != 2 or array.shape[0] != VISUAL_TOKENS_PER_PAIR:
        raise ExperimentIIIError(
            "FEATURE_DIMENSION_MISMATCH",
            f"expected [{VISUAL_TOKENS_PER_PAIR}, H] visual tokens, got {array.shape}",
        )
    return array.reshape(TOKEN_GRID_ROWS, TOKEN_GRID_COLS, array.shape[1])


def coarse_cells(tokens: np.ndarray) -> np.ndarray:
    """The ``[12, H]`` pooled cell matrix, before concatenation."""
    grid = as_token_grid(tokens)
    hidden = grid.shape[2]
    pooled = np.empty((CELL_COUNT, hidden), dtype=np.float64)
    covered: set[int] = set()
    for cell_row in range(COARSE_ROWS):
        for cell_col in range(COARSE_COLS):
            indices = cell_token_indices(cell_row, cell_col)
            if len(indices) != TOKENS_PER_CELL:
                raise ExperimentIIIError(
                    "FEATURE_DIMENSION_MISMATCH",
                    f"cell ({cell_row},{cell_col}) holds {len(indices)} tokens, "
                    f"expected {TOKENS_PER_CELL}",
                )
            covered |= set(indices)
            block = grid.reshape(-1, hidden)[list(indices)]
            pooled[cell_row * COARSE_COLS + cell_col] = block.astype(
                np.float64
            ).mean(axis=0)
    if len(covered) != VISUAL_TOKENS_PER_PAIR:
        raise ExperimentIIIError(
            "FEATURE_DIMENSION_MISMATCH",
            f"the 12 cells cover {len(covered)} tokens, not "
            f"{VISUAL_TOKENS_PER_PAIR}; they must be exhaustive and disjoint",
        )
    return pooled


def coarse_2x6_concat(tokens: np.ndarray) -> np.ndarray:
    """``COARSE_2X6_CONCAT`` at dimension 24,576, row-major over cells."""
    pooled = coarse_cells(tokens)
    flat = pooled.reshape(-1)
    if flat.shape[0] != CELL_COUNT * pooled.shape[1]:
        raise ExperimentIIIError(
            "FEATURE_DIMENSION_MISMATCH", "coarse concatenation lost values"
        )
    if pooled.shape[1] == HIDDEN_WIDTH and flat.shape[0] != COARSE_DIMENSION:
        raise ExperimentIIIError(
            "FEATURE_DIMENSION_MISMATCH",
            f"COARSE_2X6_CONCAT is {flat.shape[0]}, expected {COARSE_DIMENSION}",
        )
    if not np.isfinite(flat).all():
        raise ExperimentIIIError("FEATURE_NONFINITE", "pooled features are not finite")
    return flat


def current_minus_previous(
    current_tokens: np.ndarray, previous_tokens: np.ndarray
) -> np.ndarray:
    """``coarse(CURRENT) - coarse(PREVIOUS)`` at dimension 24,576.

    The sign is frozen: CURRENT minus PREVIOUS, never the reverse.
    """
    current = coarse_2x6_concat(current_tokens)
    previous = coarse_2x6_concat(previous_tokens)
    if current.shape != previous.shape:
        raise ExperimentIIIError(
            "FEATURE_DIMENSION_MISMATCH",
            f"slice dimensions differ: {current.shape} vs {previous.shape}",
        )
    return current - previous


def two_frame_concat(
    previous_tokens: np.ndarray, current_tokens: np.ndarray
) -> np.ndarray:
    """``concat(coarse(PREVIOUS), coarse(CURRENT))`` at dimension 49,152.

    PREVIOUS comes first. The argument order matches the frozen output order so a
    call site cannot silently swap the halves; swapping them is
    ``FEATURE_SLICE_SWAPPED``.
    """
    previous = coarse_2x6_concat(previous_tokens)
    current = coarse_2x6_concat(current_tokens)
    joined = np.concatenate([previous, current])
    if previous.shape[0] == COARSE_DIMENSION and joined.shape[0] != (
        TWO_FRAME_DIMENSION
    ):
        raise ExperimentIIIError(
            "FEATURE_DIMENSION_MISMATCH",
            f"TWO_FRAME_CONCAT is {joined.shape[0]}, expected {TWO_FRAME_DIMENSION}",
        )
    return joined
