"""The linear current-frame pixel baseline (authority 8.9.1).

    source            the RGB target frame (raw capture PNG, NOT model-normalized)
    resize            48 x 28, frozen area interpolation
    flatten           48 * 28 * 3 = 4,032 values
    standardization   training identities only
    fit               the same grouped nested ridge recipe as 8.8

**Required manuscript language: "linear current-frame pixel baseline".** It asks
whether a linear readout of *current pixels* tracks the evidence curve. It is not
a capacity-matched neural comparison and does not represent all pixel-history
models: MineWorld ``CURRENT`` is conditioned on up to 16 visual/action pairs while
this baseline sees one downsampled current image.

The source is deliberately the raw capture, never the model preprocessing path,
which performs its own channel conversion and resize.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from mineocclude.experiment_iii.authority import (
    FRAMEBUFFER_HEIGHT,
    FRAMEBUFFER_WIDTH,
)
from mineocclude.experiment_iii.errors import ExperimentIIIError

__all__ = [
    "PIXEL_BASELINE_NAME",
    "RESIZE_WIDTH",
    "RESIZE_HEIGHT",
    "CHANNELS",
    "PIXEL_FEATURE_DIM",
    "INTERPOLATION",
    "resize_area",
    "pixel_features",
]

#: Authority 8.9.1 — the exact phrase every report must use.
PIXEL_BASELINE_NAME = "linear current-frame pixel baseline"

RESIZE_WIDTH = 48
RESIZE_HEIGHT = 28
CHANNELS = 3
PIXEL_FEATURE_DIM = RESIZE_WIDTH * RESIZE_HEIGHT * CHANNELS  # 4,032
INTERPOLATION = "AREA"


def resize_area(frame: np.ndarray) -> np.ndarray:
    """Deterministic area (box) resize to 48 x 28, in float64.

    Implemented directly rather than through OpenCV so the arithmetic is frozen
    and identical on every host: each output pixel is the mean of the input
    pixels its exact box covers, weighted by overlap. For an input whose
    dimensions are not integer multiples this is the standard area average.
    """
    array = np.asarray(frame)
    if array.ndim != 3 or array.shape[2] != CHANNELS:
        raise ExperimentIIIError(
            "BASELINE_FORMULA_MISMATCH",
            f"pixel baseline needs an HxWx3 RGB frame, got {array.shape}",
        )
    height, width = array.shape[:2]
    if height <= 0 or width <= 0:
        raise ExperimentIIIError(
            "BASELINE_FORMULA_MISMATCH", "frame has a zero dimension"
        )
    values = array.astype(np.float64)
    row_edges = np.linspace(0.0, height, RESIZE_HEIGHT + 1)
    col_edges = np.linspace(0.0, width, RESIZE_WIDTH + 1)
    output = np.empty((RESIZE_HEIGHT, RESIZE_WIDTH, CHANNELS), dtype=np.float64)
    for out_row in range(RESIZE_HEIGHT):
        row_weights = _overlap(row_edges[out_row], row_edges[out_row + 1], height)
        rows = values[row_weights[0] : row_weights[1]]
        row_w = row_weights[2][:, None]
        for out_col in range(RESIZE_WIDTH):
            col_start, col_stop, col_w = _overlap(
                col_edges[out_col], col_edges[out_col + 1], width
            )
            block = rows[:, col_start:col_stop, :]
            weights = row_w * col_w[None, :]
            total = weights.sum()
            output[out_row, out_col] = (
                block * weights[:, :, None]
            ).sum(axis=(0, 1)) / total
    return output


def _overlap(low: float, high: float, extent: int):
    """Index range and per-index overlap weights for one output box."""
    start = int(np.floor(low + 1e-12))
    stop = int(np.ceil(high - 1e-12))
    stop = max(stop, start + 1)
    stop = min(stop, extent)
    start = min(start, stop - 1)
    weights = np.empty(stop - start, dtype=np.float64)
    for offset, index in enumerate(range(start, stop)):
        weights[offset] = min(high, index + 1.0) - max(low, float(index))
    weights = np.clip(weights, 0.0, None)
    if weights.sum() <= 0:
        weights[:] = 1.0
    return start, stop, weights


def pixel_features(frame: np.ndarray) -> np.ndarray:
    """The 4,032-value feature vector for one raw RGB target frame.

    Flattening order is row-major over (row, column, channel) and is stable.
    """
    array = np.asarray(frame)
    if array.ndim == 3 and array.shape[:2] == (FRAMEBUFFER_HEIGHT, FRAMEBUFFER_WIDTH):
        pass  # the expected 640x360 capture
    resized = resize_area(array)
    flat = resized.reshape(-1)
    if flat.shape[0] != PIXEL_FEATURE_DIM:
        raise ExperimentIIIError(
            "FEATURE_DIMENSION_MISMATCH",
            f"pixel baseline produced {flat.shape[0]} features, expected "
            f"{PIXEL_FEATURE_DIM}",
        )
    if not np.isfinite(flat).all():
        raise ExperimentIIIError("FEATURE_NONFINITE", "pixel features are not finite")
    return flat
