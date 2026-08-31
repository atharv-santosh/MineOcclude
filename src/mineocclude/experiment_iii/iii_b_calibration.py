"""The III-B calibration battery and its positivity guard (authority 27).

Nothing in this module enters any Holm family. Every interval is an ordinary
unadjusted two-sided 95% whole-identity bootstrap percentile interval.

The load-bearing rule is the **calibration-only** positivity guard of
authority 27.0:

```
sigma_tilde = max(sigma_hat, EPS)        EPS = 1e-4 blocks
```

It exists because an unconstrained ridge fitted to linear sigma may return
``sigma_hat < 0``, which leaves Gaussian intervals, Gaussian NLL and
``log(sigma_hat)`` undefined. It applies to **probabilistic uses only** --
coverage, both NLL variants, any log axis, any density score. It must never
reach ``U2-S1/S2/S3``, ``U3-S1/S2/S3``, scale agreement, monotonicity, the eight
confound controls or the context-boundary secondary; those use **raw**
``sigma_hat``, and :func:`assert_guard_scope` refuses any other use.

The locked predictions store raw ``sigma_hat``. Clipping before the prediction
lock, and changing ``EPS`` or the guard's scope after it, are both
``B_CALIBRATION_POSITIVITY_RULE_ALTERED``.
"""

from __future__ import annotations

import math
from typing import Any, Mapping, Sequence

import numpy as np

from mineocclude.experiment_iii.errors import ExperimentIIIError
from mineocclude.experiment_iii.iii_b_cells import Q_HIGH, Q_LOW, Q_MID
from mineocclude.experiment_iii.iii_b_inference import (
    BOOTSTRAP_B,
    percentile_interval,
    whole_identity_replicates,
)
from mineocclude.experiment_iii.iii_b_oracle import TAU_PRIMARY_SUPPORT

__all__ = [
    "EPS",
    "GUARDED_STATISTICS",
    "MATERIAL_CLIPPING_THRESHOLD",
    "RAW_SIGMA_STATISTICS",
    "assert_guard_scope",
    "assert_positivity_rule_unchanged",
    "assert_predictions_store_raw_sigma_hat",
    "calibration_report",
    "coverage",
    "mean_gate",
    "monotonicity",
    "nll",
    "positivity_report",
    "scale_agreement",
    "sigma_tilde",
]

EPS = 1e-4
MATERIAL_CLIPPING_THRESHOLD = 0.05
_Z_95 = 1.959963984540054

#: Probabilistic uses -- these, and only these, may see ``sigma_tilde``.
GUARDED_STATISTICS = frozenset(
    {
        "C_COVERAGE",
        "D_NLL_DECODED_MU",
        "D_NLL_HYBRID",
        "D_NLL_TAU_ONLY_SPREAD_BASELINE",
        "D_NLL_ORACLE_SPREAD_CEILING",
        "LOG_SIGMA_AXIS",
        "GAUSSIAN_DENSITY_SCORE",
        "PROBABILITY_INTEGRAL_TRANSFORM",
    }
)

#: These use RAW ``sigma_hat``; the guard never leaks into them.
RAW_SIGMA_STATISTICS = frozenset(
    {
        "U2-S1",
        "U2-S2",
        "U2-S3",
        "U3-S1",
        "U3-S2",
        "U3-S3",
        "A_SCALE_AGREEMENT",
        "B_MONOTONICITY",
        "CONFOUND_CONTROLS",
        "CONTEXT_BOUNDARY_SECONDARY",
    }
)


def sigma_tilde(sigma_hat: Sequence[float], *, eps: float = EPS) -> np.ndarray:
    """``max(sigma_hat, EPS)`` -- calibration only."""
    if eps != EPS:
        raise ExperimentIIIError(
            "B_CALIBRATION_POSITIVITY_RULE_ALTERED",
            f"EPS is frozen at {EPS} blocks, got {eps}",
        )
    return np.maximum(np.asarray(sigma_hat, dtype=np.float64), eps)


def assert_guard_scope(statistic: str) -> None:
    """Refuse ``sigma_tilde`` anywhere authority 27.0 mandates raw ``sigma_hat``."""
    if statistic in RAW_SIGMA_STATISTICS:
        raise ExperimentIIIError(
            "B_CALIBRATION_POSITIVITY_RULE_ALTERED",
            f"{statistic} uses RAW sigma_hat; the calibration positivity guard "
            "may not leak into it",
        )
    if statistic not in GUARDED_STATISTICS:
        raise ExperimentIIIError(
            "B_CALIBRATION_POSITIVITY_RULE_ALTERED",
            f"{statistic} is not one of the frozen guarded uses {sorted(GUARDED_STATISTICS)}",
        )


def assert_predictions_store_raw_sigma_hat(rows: Sequence[Mapping[str, Any]]) -> None:
    """Clipping before the prediction lock is forbidden."""
    for row in rows:
        if row.get("sigma_hat_clipped") or row.get("positivity_guard_applied"):
            raise ExperimentIIIError(
                "B_CALIBRATION_POSITIVITY_RULE_ALTERED",
                "the locked predictions store RAW sigma_hat; clipping before the "
                "prediction lock is refused",
            )


def assert_positivity_rule_unchanged(
    locked: Mapping[str, Any], proposed: Mapping[str, Any]
) -> None:
    """The rule may not be changed after ``iii_b_u2_prediction_lock.json`` exists."""
    for field in ("EPS_blocks", "applies_to", "does_not_apply_to"):
        if field in locked or field in proposed:
            if locked.get(field) != proposed.get(field):
                raise ExperimentIIIError(
                    "B_CALIBRATION_POSITIVITY_RULE_ALTERED",
                    f"{field} changed after prediction lock: "
                    f"{locked.get(field)!r} -> {proposed.get(field)!r}",
                )


def positivity_report(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """``fraction_clipped``, ``count_negative`` and ``min_sigma_hat``, split by q and tau."""
    values = np.asarray([float(row["sigma_hat"]) for row in rows], dtype=np.float64)
    if values.size == 0:
        raise ExperimentIIIError(
            "B_U3_ANALYSIS_FAIL", "the positivity report needs at least one row"
        )

    def split(keys: Sequence[Any]) -> dict[str, float]:
        table: dict[Any, list[float]] = {}
        for key, value in zip(keys, values):
            table.setdefault(key, []).append(value)
        return {
            str(key): float(np.mean(np.asarray(group) < EPS))
            for key, group in sorted(table.items(), key=lambda item: str(item[0]))
        }

    fraction = float(np.mean(values < EPS))
    return {
        "EPS_blocks": EPS,
        "N": int(values.size),
        "fraction_clipped": fraction,
        "count_negative": int(np.count_nonzero(values < 0.0)),
        "min_sigma_hat": float(values.min()),
        "fraction_clipped_by_q": split([f"{float(row['q']):.4f}" for row in rows]),
        "fraction_clipped_by_tau": split([int(row["tau"]) for row in rows]),
        "material_clipping_threshold": MATERIAL_CLIPPING_THRESHOLD,
        "POSITIVITY_GUARD_MATERIAL": bool(fraction > MATERIAL_CLIPPING_THRESHOLD),
        "is_a_disclosure_not_a_failure": True,
        "is_a_reason_to_refit": False,
    }


# --------------------------------------------------------------------------
# A. Scale agreement -- RAW sigma_hat
# --------------------------------------------------------------------------

def _pooled(
    rows: Sequence[Mapping[str, Any]], tau_support: Sequence[int]
) -> tuple[list[str], dict[str, np.ndarray], dict[str, np.ndarray]]:
    support = set(int(value) for value in tau_support)
    identities: list[str] = []
    blocks: dict[str, list[int]] = {}
    columns: dict[str, list[float]] = {
        "sigma_hat": [],
        "sigma_oracle": [],
        "tau": [],
        "q": [],
    }
    for row in rows:
        tau = int(row["tau"])
        if tau not in support:
            continue
        identity = str(row["identity"])
        if identity not in blocks:
            blocks[identity] = []
            identities.append(identity)
        blocks[identity].append(len(columns["sigma_hat"]))
        columns["sigma_hat"].append(float(row["sigma_hat"]))
        columns["sigma_oracle"].append(float(row["sigma_oracle"]))
        columns["tau"].append(float(tau))
        columns["q"].append(float(row["q"]))
    flat = {key: np.asarray(value, dtype=np.float64) for key, value in columns.items()}
    return (
        sorted(identities),
        flat,
        {name: np.asarray(index, dtype=np.int64) for name, index in blocks.items()},
    )


def _ols_line(x: np.ndarray, y: np.ndarray) -> tuple[float, float, float]:
    centred = x - x.mean()
    denominator = float(np.dot(centred, centred))
    if denominator <= 0.0:
        raise ExperimentIIIError(
            "B_U3_ANALYSIS_FAIL", "sigma_oracle has no variation; the scale fit is undefined"
        )
    slope = float(np.dot(centred, y - y.mean()) / denominator)
    intercept = float(y.mean() - slope * x.mean())
    residual = y - (intercept + slope * x)
    total = float(np.dot(y - y.mean(), y - y.mean()))
    r2 = float(1.0 - float(np.dot(residual, residual)) / total) if total > 0 else 0.0
    return slope, intercept, r2


def scale_agreement(
    rows: Sequence[Mapping[str, Any]],
    *,
    seed: int,
    tau_support: Sequence[int] = TAU_PRIMARY_SUPPORT,
    replicates: int = BOOTSTRAP_B,
) -> dict[str, Any]:
    """Regress RAW ``sigma_hat`` on ``sigma_oracle``; slope, intercept, R^2 with CIs."""
    assert_predictions_store_raw_sigma_hat(rows)
    identities, flat, blocks = _pooled(rows, tau_support)
    slope, intercept, r2 = _ols_line(flat["sigma_oracle"], flat["sigma_hat"])
    draws = whole_identity_replicates(identities, seed=seed, replicates=replicates)
    slopes = np.empty(replicates, dtype=np.float64)
    intercepts = np.empty(replicates, dtype=np.float64)
    for position, row in enumerate(draws):
        index = np.concatenate([blocks[identities[i]] for i in row])
        slopes[position], intercepts[position], _ = _ols_line(
            flat["sigma_oracle"][index], flat["sigma_hat"][index]
        )
    slope_ci = percentile_interval(slopes)
    intercept_ci = percentile_interval(intercepts)
    passes = slope_ci[0] <= 1.0 <= slope_ci[1] and intercept_ci[0] <= 0.0 <= intercept_ci[1]
    return {
        "analysis": "A_SCALE_AGREEMENT",
        "uses_raw_sigma_hat": True,
        "slope": slope,
        "intercept": intercept,
        "r2": r2,
        "slope_ci": list(slope_ci),
        "intercept_ci": list(intercept_ci),
        "strong_criterion": "SLOPE_CI_CONTAINS_1_AND_INTERCEPT_CI_CONTAINS_0",
        "strong_criterion_passes": bool(passes),
        "wording": (
            "consistent with scale calibration; scale mismatch is not detected at "
            "this power"
            if passes
            else "sigma_hat tracks oracle spread ordinally but is not scale-calibrated"
        ),
        "equivalence_test_run": False,
        "enters_holm_family": False,
        "replicates": replicates,
        "seed": seed,
    }


_FORBIDDEN_SCALE_CLAIMS = (
    "proven scale-calibrated",
    "proven scale calibrated",
    "equivalent to the oracle scale",
    "scale equivalence",
    "proven calibrated",
)


def assert_no_equivalence_claim(*texts: str) -> None:
    """No equivalence test is run anywhere, so no equivalence claim is permitted."""
    for text in texts:
        lowered = str(text).lower()
        for phrase in _FORBIDDEN_SCALE_CLAIMS:
            if phrase in lowered:
                raise ExperimentIIIError(
                    "B_U3_ANALYSIS_FAIL",
                    f"{phrase!r} is an equivalence claim; a CI containing 1 is a "
                    "non-rejection at this power, and no equivalence test is run",
                )


# --------------------------------------------------------------------------
# B. Monotonicity -- RAW sigma_hat, sign comparisons only
# --------------------------------------------------------------------------

def monotonicity(
    rows: Sequence[Mapping[str, Any]],
    *,
    tau_support: Sequence[int] = TAU_PRIMARY_SUPPORT,
) -> dict[str, Any]:
    """Ordered ``(q, tau)`` cell-pair agreement against the oracle. Chance is 0.5."""
    assert_predictions_store_raw_sigma_hat(rows)
    support = set(int(value) for value in tau_support)
    cells: dict[tuple[float, int], list[tuple[float, float]]] = {}
    for row in rows:
        tau = int(row["tau"])
        if tau not in support:
            continue
        cells.setdefault((float(row["q"]), tau), []).append(
            (float(row["sigma_hat"]), float(row["sigma_oracle"]))
        )
    means = {
        key: (float(np.mean([v[0] for v in group])), float(np.mean([v[1] for v in group])))
        for key, group in cells.items()
    }
    keys = sorted(means)
    agree = 0
    compared = 0
    for i, a in enumerate(keys):
        for b in keys[i + 1 :]:
            oracle_sign = np.sign(means[a][1] - means[b][1])
            if oracle_sign == 0:
                continue
            compared += 1
            agree += int(np.sign(means[a][0] - means[b][0]) == oracle_sign)
    return {
        "analysis": "B_MONOTONICITY",
        "uses_raw_sigma_hat": True,
        "pairs_compared": compared,
        "agreement_fraction": (agree / compared) if compared else 0.0,
        "chance": 0.5,
        "enters_holm_family": False,
    }


# --------------------------------------------------------------------------
# C. Coverage -- CONDITIONAL on the mean gate; uses sigma_tilde
# --------------------------------------------------------------------------

def mean_gate(
    per_identity_decoded_rmse: Mapping[str, float],
    per_identity_baseline_rmse: Mapping[str, float],
    *,
    seed: int,
    replicates: int = BOOTSTRAP_B,
) -> dict[str, Any]:
    """The decoded mu must beat the frozen constant-velocity baseline."""
    identities = sorted(per_identity_decoded_rmse)
    if sorted(per_identity_baseline_rmse) != identities:
        raise ExperimentIIIError(
            "B_U3_ANALYSIS_FAIL", "the mean gate needs both RMSEs for every identity"
        )
    improvement = np.asarray(
        [
            float(per_identity_baseline_rmse[name]) - float(per_identity_decoded_rmse[name])
            for name in identities
        ],
        dtype=np.float64,
    )
    draws = whole_identity_replicates(identities, seed=seed, replicates=replicates)
    samples = improvement[draws].mean(axis=1)
    low, high = percentile_interval(samples)
    return {
        "gate": "MEAN_GATE",
        "identity_macro_improvement": float(improvement.mean()),
        "ci_low": low,
        "ci_high": high,
        "passes": bool(low > 0.0),
        "replicates": replicates,
        "seed": seed,
    }


def coverage(
    rows: Sequence[Mapping[str, Any]], *, mean_gate_passes: bool, z: float = _Z_95
) -> dict[str, Any]:
    """Gaussian coverage of ``mu_hat +/- z*sigma_tilde``, only if the mean gate passes."""
    report = positivity_report(rows)
    if not mean_gate_passes:
        return {
            "analysis": "C_COVERAGE",
            "status": "NOT_INTERPRETABLE",
            "is_a_calibration_failure": False,
            "reason": (
                "a miscentred interval fails coverage for reasons unrelated to sigma; "
                "coverage is uninterpretable as calibration until the mean gate passes"
            ),
            "positivity": report,
            "enters_holm_family": False,
        }
    assert_guard_scope("C_COVERAGE")
    guarded = sigma_tilde([row["sigma_hat"] for row in rows])
    mu = np.asarray([float(row["mu_hat"]) for row in rows], dtype=np.float64)
    y = np.asarray([float(row["y_true"]) for row in rows], dtype=np.float64)
    covered = np.abs(y - mu) <= z * guarded
    return {
        "analysis": "C_COVERAGE",
        "status": "INTERPRETABLE",
        "nominal": 0.95,
        "empirical_coverage": float(np.mean(covered)),
        "uses_sigma_tilde": True,
        "positivity": report,
        "enters_holm_family": False,
    }


# --------------------------------------------------------------------------
# D. NLL -- both variants, hybrid primary; uses sigma_tilde
# --------------------------------------------------------------------------

def _gaussian_nll(
    y: np.ndarray, mu: np.ndarray, spread: np.ndarray, identities: Sequence[str]
) -> float:
    pointwise = (
        0.5 * math.log(2.0 * math.pi)
        + np.log(spread)
        + 0.5 * ((y - mu) / spread) ** 2
    )
    table: dict[str, list[float]] = {}
    for identity, value in zip(identities, pointwise):
        table.setdefault(identity, []).append(float(value))
    return float(np.mean([np.mean(values) for _, values in sorted(table.items())]))


def nll(
    rows: Sequence[Mapping[str, Any]], *, mean_gate_passes: bool
) -> dict[str, Any]:
    """Both NLL variants plus the two frozen baselines. The hybrid is primary."""
    identities = [str(row["identity"]) for row in rows]
    y = np.asarray([float(row["y_true"]) for row in rows], dtype=np.float64)
    mu_decoded = np.asarray([float(row["mu_hat"]) for row in rows], dtype=np.float64)
    mu_hybrid = np.asarray(
        [float(row["mu_oracle_compatible"]) for row in rows], dtype=np.float64
    )
    assert_guard_scope("D_NLL_HYBRID")
    spread = sigma_tilde([row["sigma_hat"] for row in rows])
    assert_guard_scope("D_NLL_TAU_ONLY_SPREAD_BASELINE")
    tau_only = sigma_tilde([row["sigma_tau_only_baseline"] for row in rows])
    assert_guard_scope("D_NLL_ORACLE_SPREAD_CEILING")
    oracle = sigma_tilde([row["sigma_oracle"] for row in rows])

    variants: dict[str, Any] = {
        "HYBRID_ORACLE_COMPATIBLE_MEAN_PLUS_DECODED_SIGMA": _gaussian_nll(
            y, mu_hybrid, spread, identities
        )
    }
    if mean_gate_passes:
        assert_guard_scope("D_NLL_DECODED_MU")
        variants["DECODED_MU_PLUS_DECODED_SIGMA"] = _gaussian_nll(
            y, mu_decoded, spread, identities
        )
    else:
        variants["DECODED_MU_PLUS_DECODED_SIGMA"] = None
    return {
        "analysis": "D_NLL",
        "primary_variant": "HYBRID_ORACLE_COMPATIBLE_MEAN_PLUS_DECODED_SIGMA",
        "variants": variants,
        "baselines": {
            "TAU_ONLY_SPREAD": _gaussian_nll(y, mu_hybrid, tau_only, identities),
            "ORACLE_SPREAD_CEILING": _gaussian_nll(y, mu_hybrid, oracle, identities),
        },
        "uses_sigma_tilde": True,
        "positivity": positivity_report(rows),
        "enters_holm_family": False,
    }


def calibration_report(
    rows: Sequence[Mapping[str, Any]],
    *,
    seed: int,
    per_identity_decoded_rmse: Mapping[str, float],
    per_identity_baseline_rmse: Mapping[str, float],
    replicates: int = BOOTSTRAP_B,
) -> dict[str, Any]:
    """``iii_b_calibration_report.json`` -- A, B, C and D, none Holm-corrected."""
    gate = mean_gate(
        per_identity_decoded_rmse,
        per_identity_baseline_rmse,
        seed=seed,
        replicates=replicates,
    )
    return {
        "schema_version": "mineocclude-experiment-iii-b-calibration-report-v1",
        "positivity_rule": {
            "name": "CALIBRATION_ONLY_POSITIVITY_GUARD",
            "EPS_blocks": EPS,
            "applies_to": sorted(GUARDED_STATISTICS),
            "does_not_apply_to": sorted(RAW_SIGMA_STATISTICS),
        },
        "mean_gate": gate,
        "A_scale_agreement": scale_agreement(rows, seed=seed, replicates=replicates),
        "B_monotonicity": monotonicity(rows),
        "C_coverage": coverage(rows, mean_gate_passes=gate["passes"]),
        "D_nll": nll(rows, mean_gate_passes=gate["passes"]),
        "enters_holm_family": False,
        "calibration_holm_corrected": False,
    }
