"""The P0 operational bindings frozen by Authority Amendment 3 (7.10).

v1.5 named six P0 values and procedures and deferred them to a "Phase 1" freeze
that was never written, so ``A4`` could not execute. This module implements the
four that are computational; the other two (the placement coordinates and the
sentinel *selection*) live in :mod:`mineocclude.experiment_iii.placements`.

Every rule here reads **only L0 or absent-frame technical calibration data**.
None can see a candidate material's score, a ladder, a MineWorld output or a
decoder error, and the tests assert that directly rather than trusting it.

Two design properties are load-bearing and deliberate:

* :func:`l0_noise_threshold` has **no tunable constant** -- no quantile, no
  multiplier, no floor. It is the largest per-pixel residual observed between two
  pure-noise views of the same static absent scene. There is therefore no dial an
  implementer could turn to make a material qualify, which is exactly why the
  authority chose an envelope over a fitted threshold.
* :func:`background_gate` is **noise-relative**, so one rule is meaningful at all
  nine placements instead of a raw-energy constant that would mean different
  things at different scene brightnesses.
"""

from __future__ import annotations

import hashlib
from typing import Any, Mapping, Sequence

import numpy as np

from mineocclude.experiment_iii.authority import (
    FROZEN_PHASE0_DESIGN_SHA256,
    machine_authority,
    phase0_design_sha256,
)
from mineocclude.experiment_iii.errors import ExperimentIIIError

__all__ = [
    "BOOTSTRAP_SEED_DOMAIN",
    "background_gate",
    "deterministic_split_half",
    "l0_noise_threshold",
    "p0_bootstrap_seed",
    "sentinel_envelope",
    "split_half_medians",
]

#: Authority 7.10b -- the seed derivation domain string.
BOOTSTRAP_SEED_DOMAIN = "MINEOCCLUDE_EXPERIMENT_III_P0_BOOTSTRAP_V1|"


# --------------------------------------------------------------------------
# 7.10b -- the bootstrap seed
# --------------------------------------------------------------------------


def p0_bootstrap_seed(*, phase0_sha256: str | None = None) -> int:
    """The frozen P0 bootstrap seed, **derived** and never hand-picked.

    It binds ``PHASE0_DESIGN_SHA256`` -- the immutable Phase 0 design -- rather
    than the current authority hash, so it is stable across every later
    operational amendment. Recomputing it here rather than returning a literal
    means a changed Phase 0 binding is loud.
    """
    source = phase0_sha256 or phase0_design_sha256()
    digest = hashlib.sha256((BOOTSTRAP_SEED_DOMAIN + source).encode("utf-8")).digest()
    seed = int.from_bytes(digest[:8], "big") & ((1 << 63) - 1)
    if phase0_sha256 is None:
        frozen = int(machine_authority()["p0_rve"]["bootstrap_seed"])
        if seed != frozen:
            raise ExperimentIIIError(
                "PROVENANCE_AUTHORITY_DRIFT",
                f"the derived P0 bootstrap seed {seed} disagrees with the frozen "
                f"{frozen}; the Phase 0 design binding has moved",
            )
    return seed


# --------------------------------------------------------------------------
# 7.10c -- the deterministic split and the L0 noise threshold
# --------------------------------------------------------------------------


def deterministic_split_half(
    frames: Sequence[Any],
) -> tuple[list[Any], list[Any]]:
    """The frozen balanced split by ascending capture index (authority 7.10c).

    ``first = frames[0 : n // 2]``, ``second = frames[n - n // 2 : n]``. For odd
    ``n`` the single middle frame falls in **neither** half, so the halves are
    exactly balanced -- an unbalanced split would give the two medians different
    noise scales and bias every statistic built on them.
    """
    items = list(frames)
    count = len(items)
    if count < 2:
        raise ExperimentIIIError(
            "P0_TECHNICAL_FAIL",
            f"a deterministic split-half needs at least two frames, got {count}",
        )
    half = count // 2
    return items[:half], items[count - half :]


def split_half_medians(frames: Sequence[np.ndarray]) -> tuple[np.ndarray, np.ndarray]:
    """Coordinate-wise float64 medians of the two deterministic halves."""
    first, second = deterministic_split_half(frames)
    return (
        np.median(np.stack([np.asarray(f, dtype=np.float64) for f in first]), axis=0),
        np.median(np.stack([np.asarray(f, dtype=np.float64) for f in second]), axis=0),
    )


def _residual_energy_map(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    if a.shape != b.shape:
        raise ExperimentIIIError(
            "P0_TECHNICAL_FAIL", "residual operands differ in shape"
        )
    return np.sum((a - b) ** 2, axis=-1)


def l0_noise_threshold(
    l0_absent_blocks: Sequence[Sequence[np.ndarray]],
) -> dict[str, Any]:
    """``L0_noise_threshold_p`` -- the L0 absent technical-noise envelope (7.10c).

    ``l0_absent_blocks`` is, per replicate block, that block's **settled L0
    absent frames in ascending capture index**, already linearized to float64.
    Nothing else is admissible: a candidate material's frames must never reach
    this function, because the threshold decides the support mask and therefore
    every candidate's ``D``.
    """
    if not l0_absent_blocks:
        raise ExperimentIIIError(
            "P0_TECHNICAL_FAIL", "the L0 noise envelope needs at least one block"
        )
    pooled: np.ndarray | None = None
    per_block: list[float] = []
    for block in l0_absent_blocks:
        first, second = split_half_medians(block)
        noise = _residual_energy_map(first, second)
        per_block.append(float(noise.max()))
        # max over blocks: the envelope must cover the worst noise any block
        # produced, not an average that a single quiet block could pull down.
        pooled = noise if pooled is None else np.maximum(pooled, noise)
    assert pooled is not None
    threshold = float(pooled.max())
    return {
        "threshold": threshold,
        "rule": "L0_ABSENT_TECHNICAL_NOISE_ENVELOPE",
        "aggregation_over_blocks": "MAX",
        "aggregation_over_pixels": "MAX",
        "comparison_operator": "STRICTLY_GREATER_THAN",
        "dtype": "float64",
        "tunable_constants": 0,
        "blocks": len(list(l0_absent_blocks)),
        "per_block_max_noise": per_block,
        "candidate_frames_consumed": False,
    }


# --------------------------------------------------------------------------
# 7.10d -- the background tolerance gate
# --------------------------------------------------------------------------


def _background_ratio() -> float:
    return float(machine_authority()["p0_rve"]["background_tolerance_rule"]["ratio"])


def background_gate(
    present: np.ndarray,
    absent: np.ndarray,
    absent_frames: Sequence[np.ndarray],
    mask: np.ndarray,
    *,
    ratio: float | None = None,
) -> dict[str, Any]:
    """The noise-relative outside-mask background gate (authority 7.10d).

    ``B <= ratio * N_out``, where ``N_out`` is the same outside-mask energy taken
    between this cell's **own** split-half absent medians. The reference is that
    cell's technical noise, so the gate is candidate-independent by construction:
    a material cannot widen its own tolerance.
    """
    tolerance = _background_ratio() if ratio is None else float(ratio)
    outside = ~np.asarray(mask, dtype=bool)
    if not outside.any():
        raise ExperimentIIIError(
            "RVE_MASK_DEGENERATE",
            "the support mask covers the whole frame, so no background remains "
            "to gate",
        )
    background = float(_residual_energy_map(present, absent)[outside].sum())
    first, second = split_half_medians(absent_frames)
    reference = float(_residual_energy_map(first, second)[outside].sum())

    # A demonstrably zero-noise background admits no difference at all. This is
    # the correct reading, not a degenerate one, and no epsilon is added: with
    # zero renderer noise, any outside-mask change is a real scene change.
    passed = background == 0.0 if reference == 0.0 else background <= tolerance * reference
    return {
        "background_energy": background,
        "reference_noise_energy": reference,
        "ratio": tolerance,
        "allowed": 0.0 if reference == 0.0 else tolerance * reference,
        "zero_reference": reference == 0.0,
        "passed": bool(passed),
        "blocker": None if passed else "RVE_BACKGROUND_TOLERANCE_EXCEEDED",
        "candidate_independent": True,
    }


# --------------------------------------------------------------------------
# 7.10e -- the sentinel repeatability envelope derivation
# --------------------------------------------------------------------------


def sentinel_envelope(replicate_scores: Sequence[float]) -> dict[str, Any]:
    """Derive one sentinel repeatability envelope from P0 replicate spread (7.10e).

    The **formula** is frozen before P0; the **numbers** can only exist once P0
    replicates do, and are bound in P2. Inputs are P0 replicate variation only --
    never a production measurement, and never which placements later looked
    steadiest.
    """
    values = np.asarray(list(replicate_scores), dtype=np.float64)
    if values.size < 2:
        raise ExperimentIIIError(
            "P0_TECHNICAL_FAIL",
            "a sentinel envelope needs at least two P0 replicate blocks",
        )
    rule = machine_authority()["p0_rve"]["sentinel_envelope_rule"]
    k = float(rule["k"])
    floor_fraction = float(rule["floor_fraction_of_centre"])

    centre = float(np.median(values))
    spread = float(values.max() - values.min())
    # The floor reuses the already-frozen replicate-CV bound so two exactly equal
    # P0 replicates cannot produce a zero-width envelope that every later
    # production batch would fail.
    half_width = k * max(spread, floor_fraction * centre)
    return {
        "centre": centre,
        "replicate_range": spread,
        "k": k,
        "floor_fraction_of_centre": floor_fraction,
        "half_width": half_width,
        "lower": max(centre - half_width, 0.0),
        "upper": centre + half_width,
        "replicate_blocks": int(values.size),
        "inputs": "P0_REPLICATE_VARIATION_ONLY",
        "formula_frozen_before_p0": True,
    }


def sentinel_within_envelope(score: float, envelope: Mapping[str, Any]) -> bool:
    return float(envelope["lower"]) <= float(score) <= float(envelope["upper"])
