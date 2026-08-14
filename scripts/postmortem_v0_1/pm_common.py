"""Shared helpers for the Regime-A outcome-aware exploratory postmortem (v0.1).

EXPLORATORY. Nothing in this package may alter, recompute, relabel, or supersede
the closed confirmatory Regime-A first25 result
(FAIL_NO_DEFENSIBLE_DECODING / REGIME_A_FIRST25_PASS_CONTINUE=NO).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

REPO = Path("/home/sagemaker-user/MineOcclude")
INTEG = REPO / "docs/status/integration/regime_a_occlusion_extraction_v0_1"
CONF = INTEG / "first25_analysis"
OUT = INTEG / "postmortem_v0_1"
WORK = Path("/mnt/sagemaker-nvme/pm_v0_1")
META = WORK / "meta"

S3_BUCKET = "sagemaker-us-east-1-323206973672"
S3_PREFIX = (
    "mineocclude/regime_a_occlusion_extraction_v0_1/"
    "mineocclude-regime-a-first25-v2"
)
S3_EXPLORATORY_PREFIX = (
    "mineocclude/regime_a_occlusion_extraction_v0_1/"
    "postmortem_v0_1_exploratory"
)

# Frozen confirmatory constants (read-only reference; never recomputed as science).
FROZEN_PRIMARY_MACRO_R2 = -1.2289064171181214
FROZEN_POOLED_R2 = 0.987131
FROZEN_RMSE = 0.417009
FROZEN_MAE = 0.338974
FROZEN_BEST_K_MACRO_R2 = -0.509944
FROZEN_NULL_P = 0.90
FROZEN_VERDICT = "FAIL_NO_DEFENSIBLE_DECODING"

PRIMARY_BINS = ("SHORT", "INTERMEDIATE", "LONG", "NEAR_CONTEXT")
ALL_BINS = ("SHORT", "INTERMEDIATE", "LONG", "NEAR_CONTEXT", "BEYOND_CONTEXT")
BIN_BOUNDS = {
    "SHORT": (1, 4),
    "INTERMEDIATE": (5, 8),
    "LONG": (9, 12),
    "NEAR_CONTEXT": (13, 15),
    "BEYOND_CONTEXT": (16, 19),
}

# Frozen model-input semantics, read off the extractor that produced the
# confirmatory activations (scripts/run_regime_a.py, PersistentMineWorldWorker.extract).
CONTEXT_PAIRS = 16          # indices = range(target - 15, target + 1)
EFFECTIVE_PRECEDING = 15    # frames strictly before the target
CONTEXT_INCLUDES_TARGET = True

# Amended directional guards (v2.1 amendment 1), frozen; recorded for provenance only.
GUARDS = {
    "LEFT_TO_RIGHT": {"g_entry_frames": 18, "g_exit_frames": 11},
    "RIGHT_TO_LEFT": {"g_entry_frames": 20, "g_exit_frames": 8},
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_jsonl(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def write_json(path: Path, payload: object) -> str:
    text = json.dumps(payload, indent=2, sort_keys=True, default=_default) + "\n"
    path.write_text(text, encoding="utf-8")
    return sha256_bytes(text.encode("utf-8"))


def _default(value: object) -> object:
    try:
        import numpy as np
    except ImportError:  # pragma: no cover
        raise TypeError(repr(value))
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    raise TypeError(repr(value))


def trajectory_ids() -> list[str]:
    binding = json.loads((CONF / "analysis_input_binding.json").read_text())
    return sorted(binding["activation_provenance"].keys())


def s3_roots() -> dict[str, str]:
    """Per-trajectory S3 root, derived from the bound activation provenance.

    The confirmatory cohort is split across two collection prefixes: t01-t03 under
    ``mineocclude-regime-a-first25-v2`` and t04-t25 under
    ``mineocclude-regime-a-first25-v2-amendment-1`` (collection halted at t04 and
    resumed under the amended guard authority). Roots are therefore read from the
    binding rather than assumed from a uniform pattern.
    """
    binding = json.loads((CONF / "analysis_input_binding.json").read_text())
    roots: dict[str, str] = {}
    for traj, artifacts in binding["activation_provenance"].items():
        uri = next(a["s3_uri"] for a in artifacts if a["layer"] == 4)
        roots[traj] = uri.rsplit("/activations/", 1)[0]
    return roots


def layer4_provenance() -> dict[str, dict]:
    """Bound layer-4 activation URI + sha256 + byte size per trajectory."""
    binding = json.loads((CONF / "analysis_input_binding.json").read_text())
    out: dict[str, dict] = {}
    for traj, artifacts in binding["activation_provenance"].items():
        entry = next(a for a in artifacts if a["layer"] == 4)
        out[traj] = dict(entry)
    return out


def context_indices(target_frame: int) -> list[int]:
    """Exact frozen model input window for a target frame.

    Mirrors scripts/run_regime_a.py line 930:
        indices = list(range(target - 15, target + 1))
    16 (frame, action) pairs, inclusive of the target frame itself.
    """
    return list(range(target_frame - EFFECTIVE_PRECEDING, target_frame + 1))


def summarize(values: list[float]) -> dict[str, float]:
    import numpy as np

    array = np.asarray(values, dtype=np.float64)
    return {
        "min": float(array.min()),
        "median": float(np.median(array)),
        "mean": float(array.mean()),
        "max": float(array.max()),
    }
