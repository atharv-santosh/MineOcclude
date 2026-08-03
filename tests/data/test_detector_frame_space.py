"""The interim detector must report centroids in the declared source space.

Pins the C0-C6 audit defect: detection ran over the raw client framebuffer
(the native window size, 2x on Retina) while every consumer contract declares
a 640x360 source frame, so every exported ``blob_cx``/``blob_cy`` was double
its true value.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from PIL import Image

from mineocclude.data.visibility import (
    CANONICAL_FRAME_COLUMN,
    CANONICAL_FRAME_H,
    CANONICAL_FRAME_W,
    add_interim_empirical_visibility,
)

MAGENTA = (191, 76, 201)


def write_frame(path, width, height, blob_at=None, blob_size=12):
    """A frame that is empty except for one magenta square at ``blob_at``."""
    pixels = np.zeros((height, width, 3), dtype=np.uint8)
    pixels[..., :] = (30, 120, 40)  # grass-ish, must not trip the detector
    if blob_at is not None:
        x, y = blob_at
        pixels[y:y + blob_size, x:x + blob_size] = MAGENTA
    Image.fromarray(pixels).save(path)
    return str(path)


@pytest.fixture
def episode(tmp_path):
    """One frame rendered at both the canonical and a 2x raw scale."""
    canonical = write_frame(tmp_path / "c.png", CANONICAL_FRAME_W,
                            CANONICAL_FRAME_H, blob_at=(320, 180))
    raw = write_frame(tmp_path / "r.png", CANONICAL_FRAME_W * 2,
                      CANONICAL_FRAME_H * 2, blob_at=(640, 360), blob_size=24)
    return pd.DataFrame({
        "frame_abspath": [raw],
        CANONICAL_FRAME_COLUMN: [canonical],
    })


def test_centroid_is_in_canonical_space(episode):
    out = add_interim_empirical_visibility(episode)
    assert bool(out["empirical_visible"].iloc[0])
    cx, cy = out["blob_cx"].iloc[0], out["blob_cy"].iloc[0]
    assert 0 <= cx < CANONICAL_FRAME_W
    assert 0 <= cy < CANONICAL_FRAME_H
    # The blob sits at the frame centre in canonical space.
    assert cx == pytest.approx(CANONICAL_FRAME_W / 2, abs=12)
    assert cy == pytest.approx(CANONICAL_FRAME_H / 2, abs=12)


def test_frame_space_is_recorded(episode):
    out = add_interim_empirical_visibility(episode)
    assert out["detector_frame_space"].iloc[0] == f"{CANONICAL_FRAME_W}x{CANONICAL_FRAME_H}"


def test_detecting_on_the_raw_framebuffer_is_rejected(episode):
    """The original defect: raw-space centroids must not be exportable."""
    with pytest.raises(ValueError, match="outside the declared"):
        add_interim_empirical_visibility(episode, frame_column="frame_abspath")


def test_missing_canonical_column_is_an_error(episode):
    with pytest.raises(KeyError, match=CANONICAL_FRAME_COLUMN):
        add_interim_empirical_visibility(episode.drop(columns=[CANONICAL_FRAME_COLUMN]))


def test_empirical_detection_requires_canonical_frames():
    """``process_episode`` must not silently detect on the raw framebuffer."""
    from mineocclude.data import build_dataset

    with pytest.raises(ValueError, match="requires canonical_640"):
        build_dataset.process_episode(
            "unused", "unused", "unused",
            run_empirical=True, canonical_640=False,
        )
