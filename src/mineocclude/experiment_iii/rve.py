"""P0 Robust Visual Evidence calibration (authority 7.1-7.8).

Image-only, outcome-blind, conducted before any Experiment III MineWorld
inference. It may select materials; it may **not** read activations, decoder
errors, pilot outcomes or historical material performance.

    source        raw rendered source-RGB frames at 640x360, decoded as RGB
    linearize     the exact sRGB piecewise formula, in float64
    robust images coordinate-wise median over the settled frames of a state
    mask          ONE per placement, derived from the L0 present-minus-absent
                  residual, unioned over blocks, dilated by exactly 2 pixels,
                  and SHARED by every candidate
    D             masked squared residual between present and absent
    N             the same energy from a deterministic split-half of the ABSENT
                  frames (first half vs second half by capture index)
    E             max(D - N, 0)
    RVE           E / E(L0)

RVE measures the image perturbation attributable to inserting the sheep into a
matched rendered scene. It is not silhouette recovery, perceptual equivalence,
posterior variance or pure opacity, and it never touches model preprocessing.
A per-candidate mask would make the metric material-dependent and is forbidden.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

import numpy as np

from mineocclude.experiment_iii.conditions import ELIGIBLE_STAINED_GLASS
from mineocclude.experiment_iii.errors import ExperimentIIIError

__all__ = [
    "PLACEMENT_COUNT",
    "TARGET_RVE_POINTS",
    "LADDER_ZONES",
    "ADJACENT_SEPARATION_MIN",
    "ORDER_STABILITY_MIN_PLACEMENTS",
    "L3_SNR_MIN",
    "L3_SNR_MIN_PLACEMENTS",
    "REPLICATE_CV_MAX",
    "BOOTSTRAP_REPLICATES",
    "ABBA_BLOCKS",
    "srgb_to_linear",
    "robust_median_image",
    "placement_mask",
    "masked_energy",
    "split_half_noise",
    "excess_energy",
    "rve",
    "aggregate_placement",
    "aggregate_condition",
    "background_residual",
    "evaluate_triple",
    "select_ladder",
]

PLACEMENT_COUNT = 9
#: Authority 7.6 — the selection target points for (L1, L2, L3).
TARGET_RVE_POINTS = (0.725, 0.425, 0.165)
#: Authority 7.5 — the validity zones.
LADDER_ZONES = {"L1": (0.60, 0.85), "L2": (0.30, 0.55), "L3": (0.08, 0.25)}
ADJACENT_SEPARATION_MIN = 0.12
ORDER_STABILITY_MIN_PLACEMENTS = 8
L3_SNR_MIN = 5.0
L3_SNR_MIN_PLACEMENTS = 8
REPLICATE_CV_MAX = 0.15
BOOTSTRAP_REPLICATES = 10_000
#: Authority 7.2 — the load-bearing ABBA order, per replicate block.
ABBA_BLOCKS = (("P", "A", "A", "P"), ("A", "P", "P", "A"))

_SRGB_BREAKPOINT = 0.04045


def srgb_to_linear(image: np.ndarray) -> np.ndarray:
    """8-bit sRGB to linear light, float64, exactly as authority 7.3 step 1."""
    values = np.asarray(image)
    if values.dtype != np.uint8 and values.max() > 1.0 + 1e-9:
        values = values.astype(np.float64)
    s = values.astype(np.float64) / 255.0
    return np.where(
        s <= _SRGB_BREAKPOINT, s / 12.92, ((s + 0.055) / 1.055) ** 2.4
    )


def robust_median_image(frames: Sequence[np.ndarray]) -> np.ndarray:
    """Coordinate-wise median over the settled frames of one state."""
    if len(frames) < 1:
        raise ExperimentIIIError(
            "P0_TECHNICAL_FAIL", "a robust image needs at least one settled frame"
        )
    return np.median(np.stack([np.asarray(f, dtype=np.float64) for f in frames]), axis=0)


def _residual_energy_map(present: np.ndarray, absent: np.ndarray) -> np.ndarray:
    """``|| P - A ||_2^2`` per pixel, summed over channels."""
    if present.shape != absent.shape:
        raise ExperimentIIIError(
            "P0_TECHNICAL_FAIL", "present and absent images differ in shape"
        )
    return np.sum((present - absent) ** 2, axis=-1)


def placement_mask(
    l0_blocks: Sequence[tuple[np.ndarray, np.ndarray]],
    noise_threshold: float,
    *,
    dilation: int = 2,
) -> np.ndarray:
    """ONE outcome-independent mask per placement, from the L0 residual.

    Union over replicate blocks, then dilated by exactly 2 pixels. The same mask
    is used for every candidate; a per-candidate mask is a hard failure.
    """
    if not l0_blocks:
        raise ExperimentIIIError(
            "RVE_MASK_DEGENERATE", "the mask needs at least one L0 block"
        )
    union = None
    for present, absent in l0_blocks:
        energy = _residual_energy_map(present, absent)
        block = energy > float(noise_threshold)
        union = block if union is None else (union | block)
    mask = _dilate(union, dilation)
    if not mask.any():
        raise ExperimentIIIError(
            "RVE_MASK_DEGENERATE", "the derived support mask is empty"
        )
    if mask.mean() > 0.5:
        raise ExperimentIIIError(
            "RVE_MASK_DEGENERATE",
            f"the mask covers {mask.mean():.1%} of the frame, which is implausible "
            "for a sheep support region",
        )
    return mask


def _dilate(mask: np.ndarray, radius: int) -> np.ndarray:
    """Square-structuring-element dilation by ``radius`` pixels."""
    if radius < 0:
        raise ExperimentIIIError("RVE_MASK_DEGENERATE", "dilation must be >= 0")
    out = mask.copy()
    for _ in range(radius):
        padded = np.pad(out, 1, mode="constant", constant_values=False)
        out = (
            padded[:-2, 1:-1]
            | padded[2:, 1:-1]
            | padded[1:-1, :-2]
            | padded[1:-1, 2:]
            | padded[1:-1, 1:-1]
        )
    return out


def masked_energy(
    present: np.ndarray, absent: np.ndarray, mask: np.ndarray
) -> float:
    """``D`` — the masked squared-residual evidence energy."""
    energy = _residual_energy_map(present, absent)
    if energy.shape != mask.shape:
        raise ExperimentIIIError(
            "P0_TECHNICAL_FAIL", "mask and image shapes differ"
        )
    return float(energy[mask].sum())


def split_half_noise(
    absent_frames: Sequence[np.ndarray], mask: np.ndarray
) -> float:
    """``N`` — deterministic split-half of the ABSENT frames by capture index."""
    frames = list(absent_frames)
    if len(frames) < 2:
        raise ExperimentIIIError(
            "P0_TECHNICAL_FAIL",
            "the split-half noise floor needs at least two absent frames",
        )
    midpoint = len(frames) // 2
    first = robust_median_image(frames[:midpoint])
    second = robust_median_image(frames[midpoint:])
    return masked_energy(first, second, mask)


def excess_energy(d: float, n: float) -> float:
    """``E = max(D - N, 0)`` — clamped at zero."""
    return max(float(d) - float(n), 0.0)


def rve(e: float, e_l0: float) -> float:
    """``RVE = E / E(L0)``. ``RVE(L0) == 1`` exactly."""
    if e_l0 <= 0.0:
        raise ExperimentIIIError(
            "P0_TECHNICAL_FAIL", "the L0 excess energy must be positive"
        )
    return float(e) / float(e_l0)


def aggregate_placement(block_scores: Sequence[float]) -> float:
    """Placement score: median over replicate blocks."""
    if not block_scores:
        raise ExperimentIIIError("P0_TECHNICAL_FAIL", "no replicate blocks")
    return float(np.median(np.asarray(block_scores, dtype=np.float64)))


def aggregate_condition(placement_scores: Sequence[float]) -> float:
    """Condition score ``V_c``: median over the nine placements."""
    scores = list(placement_scores)
    if len(scores) != PLACEMENT_COUNT:
        raise ExperimentIIIError(
            "P0_TECHNICAL_FAIL",
            f"a condition score needs {PLACEMENT_COUNT} placements, got {len(scores)}",
        )
    return float(np.median(np.asarray(scores, dtype=np.float64)))


def background_residual(
    present: np.ndarray, absent: np.ndarray, mask: np.ndarray
) -> float:
    """Present/absent residual OUTSIDE the mask (authority 7.3 step 8)."""
    energy = _residual_energy_map(present, absent)
    outside = ~mask
    if not outside.any():
        return 0.0
    return float(energy[outside].sum())


def _replicate_cv(block_scores: Sequence[float]) -> float:
    values = np.asarray(block_scores, dtype=np.float64)
    mean = float(values.mean())
    if mean == 0.0:
        return 0.0
    return float(values.std(ddof=0) / abs(mean))


def evaluate_triple(
    triple: Sequence[str],
    placement_scores: Mapping[str, Sequence[float]],
    *,
    snr: Mapping[str, Sequence[float]],
    replicate_blocks: Mapping[str, Sequence[Sequence[float]]],
    background_ok: Mapping[str, bool],
    bootstrap_seed: int,
) -> dict[str, Any]:
    """All nine validity rules of authority 7.5, evaluated per triple."""
    l1, l2, l3 = triple
    medians = {
        level: aggregate_condition(placement_scores[candidate])
        for level, candidate in zip(("L1", "L2", "L3"), triple, strict=True)
    }
    rules: dict[str, bool] = {}
    for level in ("L1", "L2", "L3"):
        low, high = LADDER_ZONES[level]
        rules[f"{level}_zone"] = low <= medians[level] <= high
    rules["adjacent_separation_L1_L2"] = (
        medians["L1"] - medians["L2"] >= ADJACENT_SEPARATION_MIN
    )
    rules["adjacent_separation_L2_L3"] = (
        medians["L2"] - medians["L3"] >= ADJACENT_SEPARATION_MIN
    )
    stable = sum(
        1
        for index in range(PLACEMENT_COUNT)
        if placement_scores[l1][index]
        > placement_scores[l2][index]
        > placement_scores[l3][index]
    )
    rules["strict_order_stability"] = stable >= ORDER_STABILITY_MIN_PLACEMENTS
    rules["L3_snr"] = (
        sum(1 for value in snr[l3] if value >= L3_SNR_MIN) >= L3_SNR_MIN_PLACEMENTS
    )
    rules["replicate_repeatability"] = all(
        _replicate_cv(blocks) <= REPLICATE_CV_MAX
        for candidate in triple
        for blocks in replicate_blocks[candidate]
    )
    rules["background"] = all(background_ok[candidate] for candidate in triple)

    lower_bounds = {}
    if all(rules[name] for name in ("adjacent_separation_L1_L2", "adjacent_separation_L2_L3")):
        rng = np.random.default_rng(bootstrap_seed)
        for pair, (a, b) in (("L1_L2", (l1, l2)), ("L2_L3", (l2, l3))):
            differences = np.asarray(
                [
                    placement_scores[a][index] - placement_scores[b][index]
                    for index in range(PLACEMENT_COUNT)
                ],
                dtype=np.float64,
            )
            draws = rng.integers(0, PLACEMENT_COUNT, size=(BOOTSTRAP_REPLICATES, PLACEMENT_COUNT))
            samples = differences[draws].mean(axis=1)
            lower_bounds[pair] = float(np.percentile(samples, 2.5))
        rules["bootstrap_lower_bounds_positive"] = all(
            value > 0.0 for value in lower_bounds.values()
        )
    else:
        rules["bootstrap_lower_bounds_positive"] = False

    distance = float(
        sum(
            (medians[level] - target) ** 2
            for level, target in zip(("L1", "L2", "L3"), TARGET_RVE_POINTS, strict=True)
        )
    )
    return {
        "triple": list(triple),
        "medians": medians,
        "rules": rules,
        "valid": all(rules.values()),
        "bootstrap_lower_bounds": lower_bounds,
        "squared_distance_to_target": distance,
    }


def select_ladder(
    candidates: Sequence[str],
    placement_scores: Mapping[str, Sequence[float]],
    *,
    snr: Mapping[str, Sequence[float]],
    replicate_blocks: Mapping[str, Sequence[Sequence[float]]],
    background_ok: Mapping[str, bool],
    bootstrap_seed: int,
) -> dict[str, Any]:
    """Deterministic, exhaustive triple search (authority 7.6).

    Minimizes squared distance to ``(0.725, 0.425, 0.165)``; ties break
    lexicographically earliest by candidate registry ID, compared position by
    position L1, then L2, then L3. Returns ``NO_VALID_LADDER`` rather than an
    approximate ladder when nothing qualifies.
    """
    unsupported = sorted(set(candidates) - set(ELIGIBLE_STAINED_GLASS))
    if unsupported:
        raise ExperimentIIIError(
            "P0_CANDIDATE_ID_UNSUPPORTED",
            f"candidates outside the twelve-item roster: {unsupported}",
        )
    evaluations = []
    for triple in itertools.permutations(sorted(candidates), 3):
        evaluations.append(
            evaluate_triple(
                triple,
                placement_scores,
                snr=snr,
                replicate_blocks=replicate_blocks,
                background_ok=background_ok,
                bootstrap_seed=bootstrap_seed,
            )
        )
    valid = [row for row in evaluations if row["valid"]]
    if not valid:
        return {
            "P0_RESULT": "NO_VALID_LADDER",
            "PRODUCTION_AUTHORIZED": False,
            "evaluated_triples": len(evaluations),
            "selected": None,
            "all_evaluations": evaluations,
        }
    best = min(
        valid,
        key=lambda row: (row["squared_distance_to_target"], tuple(row["triple"])),
    )
    return {
        "P0_RESULT": "P0_PASS",
        "PRODUCTION_AUTHORIZED": True,
        "evaluated_triples": len(evaluations),
        "selected": {
            "L1": best["triple"][0],
            "L2": best["triple"][1],
            "L3": best["triple"][2],
            "V_c": best["medians"],
        },
        "selection_rule": "MIN_SQUARED_DISTANCE_THEN_LEXICOGRAPHIC_REGISTRY_ID",
        "target_points": list(TARGET_RVE_POINTS),
        "all_evaluations": evaluations,
    }
