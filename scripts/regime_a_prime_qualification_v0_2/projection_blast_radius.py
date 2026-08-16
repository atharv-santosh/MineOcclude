#!/usr/bin/env python3
"""Bounded historical blast-radius assessment for the projection crop defect.

The superseded mapping scaled raw framebuffer coordinates to the canonical frame
by the bare resolution ratio (``raw_x * 640/1920``), ignoring that
``preprocess.to_canonical`` centre-crops the raw 1920x1046 framebuffer to 16:9
*before* resizing. The corrected mapping reproduces that crop.

This assessment reruns no neural analysis. The superseded mapping was a pure
linear scale, so the raw framebuffer coordinate is recovered exactly from each
frozen ``coordinates.jsonl`` row and re-projected through the corrected mapping.
It answers one question: can the correction change a frozen per-frame
classification? Frozen artefacts are read only, never written.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from mineocclude.regime_a import (  # noqa: E402
    CANONICAL_FRAME_HEIGHT, CANONICAL_FRAME_WIDTH, RAW_FRAMEBUFFER_HEIGHT,
    RAW_FRAMEBUFFER_WIDTH, TOKEN_GRID_COLUMNS, TOKEN_GRID_ROWS, canonical_crop_window,
)

DEFAULT_CACHE = Path.home() / ".mineocclude_cache/p1_qualification_v0_1/meta"


def assess(cache: Path) -> dict:
    crop_x0, crop_y0, crop_width, crop_height = canonical_crop_window()
    files = sorted(cache.glob("*/coordinates.jsonl"))
    if not files:
        raise SystemExit(f"no frozen coordinates.jsonl under {cache}")
    rows = in_to_out = out_to_in = column_changes = row_changes = 0
    maximum_screen_delta = maximum_column_delta = 0.0
    affine_residual = 0.0
    scale = CANONICAL_FRAME_WIDTH * RAW_FRAMEBUFFER_WIDTH / (crop_width * CANONICAL_FRAME_WIDTH)
    offset = -crop_x0 * CANONICAL_FRAME_WIDTH / crop_width
    for path in files:
        for line in path.read_text().splitlines():
            if not line:
                continue
            item = json.loads(line)
            rows += 1
            old_x, old_y = item["screen_x"], item["screen_y"]
            raw_x = old_x * RAW_FRAMEBUFFER_WIDTH / CANONICAL_FRAME_WIDTH
            raw_y = old_y * RAW_FRAMEBUFFER_HEIGHT / CANONICAL_FRAME_HEIGHT
            new_x = (raw_x - crop_x0) * CANONICAL_FRAME_WIDTH / crop_width
            new_y = (raw_y - crop_y0) * CANONICAL_FRAME_HEIGHT / crop_height
            new_column = new_x * TOKEN_GRID_COLUMNS / CANONICAL_FRAME_WIDTH
            new_row = new_y * TOKEN_GRID_ROWS / CANONICAL_FRAME_HEIGHT
            inside_old = (0 <= old_x < CANONICAL_FRAME_WIDTH
                          and 0 <= old_y < CANONICAL_FRAME_HEIGHT
                          and 0 <= item["token_row"] < TOKEN_GRID_ROWS
                          and 0 <= item["token_col"] < TOKEN_GRID_COLUMNS)
            inside_new = (0 <= new_x < CANONICAL_FRAME_WIDTH
                          and 0 <= new_y < CANONICAL_FRAME_HEIGHT
                          and 0 <= new_row < TOKEN_GRID_ROWS
                          and 0 <= new_column < TOKEN_GRID_COLUMNS)
            in_to_out += int(inside_old and not inside_new)
            out_to_in += int(inside_new and not inside_old)
            if inside_old and inside_new:
                column_changes += int(math.floor(new_column) != item["token_cell_col"])
                row_changes += int(math.floor(new_row) != item["token_cell_row"])
            maximum_screen_delta = max(maximum_screen_delta, abs(new_x - old_x))
            maximum_column_delta = max(maximum_column_delta, abs(new_column - item["token_col"]))
            affine_residual = max(affine_residual, abs(new_x - (old_x * scale + offset)))
            affine_residual = max(affine_residual, abs(new_y - old_y))
    return {
        "artifact_id": "regime-a-prime-projection-crop-blast-radius-v0.2",
        "assessment_class": "BOUNDED_ARITHMETIC_REPROJECTION_NO_NEURAL_RERUN",
        "corrected_crop_window_x0_y0_w_h": [crop_x0, crop_y0, crop_width, crop_height],
        "trajectories": len(files), "rows": rows,
        "in_frame_to_out_of_frame_flips": in_to_out,
        "out_of_frame_to_in_frame_flips": out_to_in,
        "discrete_token_cell_col_changes": column_changes,
        "discrete_token_cell_row_changes": row_changes,
        "maximum_absolute_screen_x_delta_pixels": maximum_screen_delta,
        "maximum_absolute_continuous_token_col_delta": maximum_column_delta,
        # The correction is exactly affine in x and the identity in y, so every
        # token-cell-unit secondary metric rescales by a known constant and no
        # scale-invariant metric (R^2) moves at all.
        "corrected_equals_affine_transform_of_superseded": affine_residual < 1e-9,
        "affine_scale_x": scale, "affine_offset_x_pixels": offset,
        "maximum_affine_residual_pixels": affine_residual,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    print(json.dumps(assess(parser.parse_args().cache), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
