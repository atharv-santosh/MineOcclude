"""Frame preprocessing (Person C, C4.5).

Two distinct stages, kept deliberately separate:

1. **Canonical source normalization (C-owned).** The client captures the raw
   framebuffer at whatever 16:9 size the window provides (Retina doubles it).
   ``to_canonical`` center-crops to 16:9 and resizes to the contract's 640x360
   source resolution. The 640x360 canonical PNG is the preserved source
   evidence; it is written *next to* the raw capture, never over it.

2. **Model-input derivation (A-owned).** The 384x224 BGR/RGB + scaling +
   normalization path belongs to Person A's audited implementation. Per the
   frozen interface packet those choices are ``UNRESOLVED``; Person C must not
   duplicate them. ``derive_model_input`` therefore requires an injected
   pinned callable and records its identity; the module-level reference
   implementation exists only so the plumbing is testable, and it is tagged
   ``REFERENCE_PREPROCESS_ID`` so its outputs can never masquerade as A's.

Nothing here mutates a source frame in place (C4.5: preserve the 640x360
source and hashes unchanged).
"""
from __future__ import annotations

import hashlib
import os
from collections.abc import Callable

import numpy as np
from PIL import Image

from mineocclude.data.fsretry import open_rgb_retry

CANON_W, CANON_H = 640, 360
ASPECT = CANON_W / CANON_H  # 16:9

MODEL_W, MODEL_H = 384, 224
REFERENCE_PREPROCESS_ID = "person_c_reference_preprocess_v0"
PINNED_PREPROCESS_REQUIRED = "PINNED_PERSON_A_PREPROCESS_REQUIRED"


def to_canonical(rgb: np.ndarray) -> np.ndarray:
    """Center-crop any RGB array to 16:9 and resize to 640x360."""
    height, width = rgb.shape[:2]
    aspect = width / height
    if aspect > ASPECT:                    # too wide -> crop width
        new_w = int(round(height * ASPECT))
        x0 = (width - new_w) // 2
        rgb = rgb[:, x0:x0 + new_w]
    elif aspect < ASPECT:                  # too tall -> crop height
        new_h = int(round(width / ASPECT))
        y0 = (height - new_h) // 2
        rgb = rgb[y0:y0 + new_h, :]
    return np.asarray(
        Image.fromarray(rgb).resize((CANON_W, CANON_H), Image.BILINEAR)
    )


def sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_episode(frame_map, out_subdir: str = "frames_640x360"):
    """Write a 640x360 canonical PNG for every frame.

    Adds ``frame_640_path`` and ``frame_640_sha256`` columns. The raw capture
    referenced by ``frame_abspath`` is left untouched.
    """
    out = frame_map.copy()
    paths, hashes = [], []
    for _, row in frame_map.iterrows():
        src = str(row["frame_abspath"])
        episode_dir = os.path.dirname(os.path.dirname(src))
        dst_dir = os.path.join(episode_dir, out_subdir)
        os.makedirs(dst_dir, exist_ok=True)
        dst = os.path.join(dst_dir, os.path.basename(src))
        arr = open_rgb_retry(src)
        canon = Image.fromarray(to_canonical(arr))
        try:
            canon.save(dst)
        except FileNotFoundError:
            # Observed transiently on a near-full disk: the directory this
            # process just created can disappear before the next save() in
            # this same loop. Recreate and retry once rather than fail the
            # whole (already-accepted) episode over a filesystem hiccup.
            os.makedirs(dst_dir, exist_ok=True)
            canon.save(dst)
        paths.append(dst)
        hashes.append(sha256_file(dst))
    out["frame_640_path"] = paths
    out["frame_640_sha256"] = hashes
    return out


def encode_canonical_mp4(frame_map, out_path: str) -> str:
    """Deterministically encode the canonical 640x360 frames to a 20 fps MP4.

    Runs AFTER count validation (C3.4/C6A): the input list is the ordered
    ``frame_640_path`` column, one frame per accepted model frame. Fixed
    encoder settings; the file's SHA-256 is returned for the manifest. The
    PNG sources remain the preserved evidence; the MP4 is the model-facing
    media that ffprobe gates (640x360, exactly 20/1 fps, frame count equal
    to the frame map).
    """
    import subprocess

    ordered = frame_map.sort_values("model_frame_idx")
    list_path = out_path + ".frames.txt"
    with open(list_path, "w", encoding="utf-8") as handle:
        for path in ordered["frame_640_path"]:
            handle.write(f"file '{path}'\nduration 0.05\n")
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error",
         "-f", "concat", "-safe", "0", "-i", list_path,
         "-fps_mode", "cfr", "-r", "20",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
         "-pix_fmt", "yuv420p", out_path],
        check=True, capture_output=True, timeout=600,
    )
    os.remove(list_path)
    return sha256_file(out_path)


def reference_model_input(rgb_640x360: np.ndarray) -> np.ndarray:
    """REFERENCE 384x224 float32 derivation — NOT Person A's pinned path.

    RGB order (PNG decode is already RGB, so no BGR swap), bilinear resize to
    384x224, scale to [0, 1], then mean/std 0.5 normalization. Exists so the
    plumbing and golden-frame harness are testable before A pins the real
    implementation; its identity is ``REFERENCE_PREPROCESS_ID``.
    """
    if rgb_640x360.shape[:2] != (CANON_H, CANON_W):
        raise ValueError(
            f"model derivation expects a {CANON_W}x{CANON_H} canonical source, "
            f"got {rgb_640x360.shape[1]}x{rgb_640x360.shape[0]}"
        )
    resized = np.asarray(
        Image.fromarray(rgb_640x360).resize((MODEL_W, MODEL_H), Image.BILINEAR),
        dtype=np.float32,
    )
    scaled = resized / 255.0
    return (scaled - 0.5) / 0.5


def derive_model_input(
    rgb_640x360: np.ndarray,
    pinned: Callable[[np.ndarray], np.ndarray] | None = None,
    preprocess_id: str | None = None,
) -> tuple[np.ndarray, str]:
    """Derive the model-facing frame through an explicitly identified path.

    A scientific run must pass Person A's audited callable and its recorded
    ``preprocess_id``. With no pinned callable the reference path runs and the
    returned identity is ``REFERENCE_PREPROCESS_ID`` — a downstream validator
    rejects scientific packages carrying the reference identity.
    """
    if pinned is not None:
        if not preprocess_id:
            raise ValueError(
                "a pinned preprocess callable requires an explicit preprocess_id"
            )
        return pinned(rgb_640x360), preprocess_id
    return reference_model_input(rgb_640x360), REFERENCE_PREPROCESS_ID
