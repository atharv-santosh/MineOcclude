"""I11 / I12 — coarse pooling and the temporal representations (A.20–A.23).

The identity-encoding fixture is the whole point: it proves the grid is read as
14 rows x 24 columns and not transposed, which a shape check alone cannot do.
"""

from __future__ import annotations

import numpy as np
import pytest

from mineocclude.experiment_iii.errors import ExperimentIIIError
from mineocclude.experiment_iii.representations import (
    CELL_COLS,
    CELL_COUNT,
    CELL_ROWS,
    COARSE_COLS,
    COARSE_DIMENSION,
    COARSE_ROWS,
    TOKENS_PER_CELL,
    TOKEN_GRID_COLS,
    TOKEN_GRID_ROWS,
    TWO_FRAME_DIMENSION,
    as_token_grid,
    cell_token_indices,
    coarse_2x6_concat,
    coarse_cells,
    current_minus_previous,
    two_frame_concat,
)
from mineocclude.experiment_iii.slices import HIDDEN_WIDTH, VISUAL_TOKENS_PER_PAIR

HIDDEN = 4  # a small hidden width keeps the identity fixture readable


def identity_grid(hidden: int = HIDDEN) -> np.ndarray:
    """Token (r, c) carries [r, c, r*24+c, ...] so its origin is recoverable."""
    tokens = np.zeros((VISUAL_TOKENS_PER_PAIR, hidden), dtype=np.float64)
    for row in range(TOKEN_GRID_ROWS):
        for col in range(TOKEN_GRID_COLS):
            flat = row * TOKEN_GRID_COLS + col
            tokens[flat, 0] = row
            tokens[flat, 1] = col
            if hidden > 2:
                tokens[flat, 2] = flat
            if hidden > 3:
                tokens[flat, 3] = 1.0
    return tokens


# --------------------------------------------------------------------------
# A.20 — coarse pooling exactness
# --------------------------------------------------------------------------

def test_frozen_grid_constants():
    assert (TOKEN_GRID_ROWS, TOKEN_GRID_COLS) == (14, 24)
    assert TOKEN_GRID_ROWS * TOKEN_GRID_COLS == VISUAL_TOKENS_PER_PAIR == 336
    assert (COARSE_ROWS, COARSE_COLS) == (2, 6)
    assert (CELL_ROWS, CELL_COLS) == (7, 4)
    assert TOKENS_PER_CELL == 28
    assert CELL_COUNT == 12
    assert COARSE_DIMENSION == 12 * HIDDEN_WIDTH == 24_576
    assert TWO_FRAME_DIMENSION == 49_152


def test_cells_are_exhaustive_non_overlapping_and_28_tokens():
    seen: set[int] = set()
    for cell_row in range(COARSE_ROWS):
        for cell_col in range(COARSE_COLS):
            indices = cell_token_indices(cell_row, cell_col)
            assert len(indices) == TOKENS_PER_CELL == 28
            assert len(set(indices)) == 28
            assert not seen & set(indices), "cells must not overlap"
            seen |= set(indices)
    assert seen == set(range(VISUAL_TOKENS_PER_PAIR))


def test_pooled_cells_match_an_independently_derived_matrix():
    tokens = identity_grid()
    pooled = coarse_cells(tokens)
    assert pooled.shape == (CELL_COUNT, HIDDEN)
    expected = np.zeros((CELL_COUNT, HIDDEN), dtype=np.float64)
    for cell_row in range(COARSE_ROWS):
        for cell_col in range(COARSE_COLS):
            rows = range(cell_row * CELL_ROWS, (cell_row + 1) * CELL_ROWS)
            cols = range(cell_col * CELL_COLS, (cell_col + 1) * CELL_COLS)
            members = [(r, c) for r in rows for c in cols]
            index = cell_row * COARSE_COLS + cell_col
            expected[index, 0] = np.mean([r for r, _ in members])
            expected[index, 1] = np.mean([c for _, c in members])
            expected[index, 2] = np.mean([r * TOKEN_GRID_COLS + c for r, c in members])
            expected[index, 3] = 1.0
    assert np.array_equal(pooled, expected)


def test_concatenation_is_row_major_over_cells():
    tokens = identity_grid()
    pooled = coarse_cells(tokens)
    flat = coarse_2x6_concat(tokens)
    assert flat.shape == (CELL_COUNT * HIDDEN,)
    assert np.array_equal(flat, pooled.reshape(-1))
    # Cell order is (0,0),(0,1)...(0,5),(1,0)...(1,5).
    assert flat[0] == pooled[0, 0]
    assert flat[5 * HIDDEN] == pooled[5, 0]
    assert flat[6 * HIDDEN] == pooled[6, 0]


def test_full_width_output_is_24576():
    tokens = np.zeros((VISUAL_TOKENS_PER_PAIR, HIDDEN_WIDTH), dtype=np.float16)
    assert coarse_2x6_concat(tokens).shape == (COARSE_DIMENSION,)


# --------------------------------------------------------------------------
# A.21 — grid orientation
# --------------------------------------------------------------------------

def test_pooling_reads_fourteen_rows_by_twentyfour_columns():
    pooled = coarse_cells(identity_grid())
    # Cell (0,0) spans rows 0-6 and cols 0-3; cell (1,5) spans rows 7-13, cols 20-23.
    assert pooled[0, 0] == pytest.approx(np.mean(range(0, 7)))
    assert pooled[0, 1] == pytest.approx(np.mean(range(0, 4)))
    assert pooled[CELL_COUNT - 1, 0] == pytest.approx(np.mean(range(7, 14)))
    assert pooled[CELL_COUNT - 1, 1] == pytest.approx(np.mean(range(20, 24)))


def test_transposed_grid_gives_a_different_result():
    """The negative control: the fixture must discriminate, not merely pass."""
    tokens = identity_grid()
    transposed = (
        tokens.reshape(TOKEN_GRID_ROWS, TOKEN_GRID_COLS, HIDDEN)
        .transpose(1, 0, 2)
        .reshape(VISUAL_TOKENS_PER_PAIR, HIDDEN)
    )
    assert not np.array_equal(coarse_2x6_concat(tokens), coarse_2x6_concat(transposed))


def test_explicitly_transposed_grid_shape_is_refused():
    grid = np.zeros((TOKEN_GRID_COLS, TOKEN_GRID_ROWS, HIDDEN))
    with pytest.raises(ExperimentIIIError) as caught:
        as_token_grid(grid)
    assert caught.value.blocker == "FEATURE_POOLING_GRID_TRANSPOSED"


def test_wrong_token_count_is_refused():
    with pytest.raises(ExperimentIIIError) as caught:
        coarse_2x6_concat(np.zeros((335, HIDDEN)))
    assert caught.value.blocker == "FEATURE_DIMENSION_MISMATCH"


def test_global_mean_pool_is_not_the_representation():
    """A global 336-token mean collapses the 12 cells; the coarse form does not."""
    tokens = identity_grid()
    global_mean = tokens.astype(np.float64).mean(axis=0)
    pooled = coarse_cells(tokens)
    assert not np.allclose(pooled, np.tile(global_mean, (CELL_COUNT, 1)))


# --------------------------------------------------------------------------
# A.22 — temporal subtraction
# --------------------------------------------------------------------------

def test_current_minus_previous_is_exact_and_correctly_signed():
    previous = identity_grid()
    current = identity_grid() + 3.0
    difference = current_minus_previous(current, previous)
    assert difference.shape == (CELL_COUNT * HIDDEN,)
    assert np.array_equal(
        difference, coarse_2x6_concat(current) - coarse_2x6_concat(previous)
    )
    # PREVIOUS < CURRENT must yield a positive difference.
    assert np.all(difference > 0)


def test_temporal_difference_dimension_is_24576():
    previous = np.zeros((VISUAL_TOKENS_PER_PAIR, HIDDEN_WIDTH), dtype=np.float16)
    current = np.ones((VISUAL_TOKENS_PER_PAIR, HIDDEN_WIDTH), dtype=np.float16)
    assert current_minus_previous(current, previous).shape == (COARSE_DIMENSION,)


def test_sign_inversion_is_detectable():
    previous = identity_grid()
    current = identity_grid() + 1.0
    forward = current_minus_previous(current, previous)
    backward = current_minus_previous(previous, current)
    assert np.array_equal(forward, -backward)
    assert not np.array_equal(forward, backward)


# --------------------------------------------------------------------------
# A.23 — concatenation order
# --------------------------------------------------------------------------

def test_two_frame_concat_places_previous_first():
    previous = identity_grid()
    current = identity_grid() + 7.0
    joined = two_frame_concat(previous, current)
    half = CELL_COUNT * HIDDEN
    assert joined.shape == (2 * half,)
    assert np.array_equal(joined[:half], coarse_2x6_concat(previous))
    assert np.array_equal(joined[half:], coarse_2x6_concat(current))


def test_two_frame_concat_dimension_is_49152():
    previous = np.zeros((VISUAL_TOKENS_PER_PAIR, HIDDEN_WIDTH), dtype=np.float16)
    current = np.ones((VISUAL_TOKENS_PER_PAIR, HIDDEN_WIDTH), dtype=np.float16)
    assert two_frame_concat(previous, current).shape == (TWO_FRAME_DIMENSION,)


def test_swapped_halves_are_detected():
    previous = identity_grid()
    current = identity_grid() + 7.0
    correct = two_frame_concat(previous, current)
    swapped = two_frame_concat(current, previous)
    assert not np.array_equal(correct, swapped)
    half = CELL_COUNT * HIDDEN
    assert np.array_equal(swapped[:half], correct[half:])
