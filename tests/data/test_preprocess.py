"""Tests for canonical 640x360 normalization and model-input gating (C4.5)."""

import numpy as np
import pytest

from mineocclude.data.align import align_episode
from mineocclude.data.preprocess import (
    CANON_H,
    CANON_W,
    MODEL_H,
    MODEL_W,
    REFERENCE_PREPROCESS_ID,
    derive_model_input,
    normalize_episode,
    reference_model_input,
    sha256_file,
    to_canonical,
)

from tests.data.synthetic_episode import make_episode


def test_to_canonical_widescreen_and_tall_inputs():
    wide = np.zeros((360, 1000, 3), dtype=np.uint8)   # wider than 16:9
    tall = np.zeros((500, 640, 3), dtype=np.uint8)    # taller than 16:9
    exact = np.zeros((720, 1280, 3), dtype=np.uint8)  # already 16:9 (Retina)
    for image in (wide, tall, exact):
        out = to_canonical(image)
        assert out.shape == (CANON_H, CANON_W, 3)


def test_to_canonical_center_crop_keeps_center_content():
    image = np.zeros((360, 1000, 3), dtype=np.uint8)
    image[:, 490:510] = 255  # vertical stripe at the true center
    out = to_canonical(image)
    center_col = out[:, CANON_W // 2 - 2:CANON_W // 2 + 2]
    assert center_col.mean() > 200


def test_normalize_episode_preserves_source_and_hashes(tmp_path):
    server_dir, client_dir = make_episode(str(tmp_path), n=4)
    frame_map, report = align_episode(server_dir, client_dir)
    assert report.accepted
    source_hashes = [sha256_file(p) for p in frame_map["frame_abspath"]]

    out = normalize_episode(frame_map)
    assert "frame_640_path" in out.columns
    assert "frame_640_sha256" in out.columns
    for path, digest in zip(out["frame_640_path"], out["frame_640_sha256"]):
        assert path.endswith(".png")
        assert sha256_file(path) == digest
    # C4.5: the raw source frames are byte-identical after normalization.
    assert [sha256_file(p) for p in frame_map["frame_abspath"]] == source_hashes


def test_reference_model_input_shape_and_range():
    rgb = np.random.default_rng(0).integers(
        0, 256, size=(CANON_H, CANON_W, 3), dtype=np.uint8
    )
    out = reference_model_input(rgb)
    assert out.shape == (MODEL_H, MODEL_W, 3)
    assert out.dtype == np.float32
    assert out.min() >= -1.0 and out.max() <= 1.0


def test_reference_model_input_rejects_wrong_source_size():
    with pytest.raises(ValueError, match="canonical source"):
        reference_model_input(np.zeros((100, 100, 3), dtype=np.uint8))


def test_derive_model_input_identity_gating():
    rgb = np.zeros((CANON_H, CANON_W, 3), dtype=np.uint8)
    _, identity = derive_model_input(rgb)
    assert identity == REFERENCE_PREPROCESS_ID  # never mistakable for A's path

    def pinned(image):
        return np.zeros((MODEL_H, MODEL_W, 3), dtype=np.float32)

    _, identity = derive_model_input(rgb, pinned=pinned,
                                     preprocess_id="person_a_preprocess_v1")
    assert identity == "person_a_preprocess_v1"

    with pytest.raises(ValueError, match="preprocess_id"):
        derive_model_input(rgb, pinned=pinned)
