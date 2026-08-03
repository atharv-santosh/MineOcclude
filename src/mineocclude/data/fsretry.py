"""Transient-filesystem-flakiness retry (Person C).

Observed on macOS during real collection: ``PIL.Image.open()`` raises
``FileNotFoundError`` for a frame PNG that demonstrably exists a moment before
and after the failed call (confirmed by re-checking ``os.path.isfile``
immediately after the raise) — almost certainly Spotlight/mds racing the file
right after creation, not a real data-loss bug. Retrying briefly absorbs this
without masking genuine missing files, which still raise after the retry
budget is exhausted.
"""
from __future__ import annotations

import time

import numpy as np
from PIL import Image


def open_rgb_retry(path: str, attempts: int = 30, delay: float = 0.1) -> np.ndarray:
    last_err: Exception | None = None
    for attempt in range(attempts):
        try:
            return np.asarray(Image.open(path).convert("RGB"))
        except FileNotFoundError as error:
            last_err = error
            if attempt < attempts - 1:
                time.sleep(delay)
    raise last_err
