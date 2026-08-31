"""U3 -- uncertainty *dynamics* (authority 26).

U3 is **hierarchical on U2**: its scientific claims may be made only when the
U2 conjunction and the authority-23 controls pass. When U2 does not pass, U3 is
still computed, but every output is labelled descriptive.

``U3-S2`` -- the ``q``-dependent rate interaction -- is the decisive statistic of
the whole module. An additive "clock + ``q`` category" model predicts identical
slopes across ``q`` (``Delta = 0``); the oracle predicts
``b(q_high)/b(q_low) = sqrt(q_high/q_low) = 4``. No additive clock-plus-label
model can produce a positive ``Delta``.

``U3-S3`` is descriptive, enters no family and is never Holm-corrected.
"""

from __future__ import annotations

import math
from typing import Any, Mapping, Sequence

import numpy as np

from mineocclude.experiment_iii.errors import ExperimentIIIError
from mineocclude.experiment_iii.iii_b_cells import Q_HIGH, Q_LOW, Q_MID
from mineocclude.experiment_iii.iii_b_inference import (
    ALPHA,
    BOOTSTRAP_B,
    U3_FAMILY_ORDER,
    bootstrap_inversion,
    holm,
)
from mineocclude.experiment_iii.iii_b_oracle import TAU_PRIMARY_SUPPORT

__all__ = [
    "ORACLE_SLOPE_RATIOS",
    "identity_slopes",
    "u3_analysis",
    "u3_s1",
    "u3_s2",
    "u3_s3",
]

#: sqrt(q ratios): high/mid, mid/low, high/low.
ORACLE_SLOPE_RATIOS = {
    "q_high_over_q_mid": 2.0,
    "q_mid_over_q_low": 2.0,
    "q_high_over_q_low": 4.0,
}


def _ols_slope(tau: Sequence[int], values: Sequence[float]) -> float:
    x = np.asarray(tau, dtype=np.float64)
    y = np.asarray(values, dtype=np.float64)
    if x.size < 2:
        raise ExperimentIIIError(
            "B_U3_ANALYSIS_FAIL", "a per-identity slope needs at least two tau rows"
        )
    centred = x - x.mean()
    denominator = float(np.dot(centred, centred))
    if denominator <= 0.0:
        raise ExperimentIIIError(
            "B_U3_ANALYSIS_FAIL", "tau has no variation; the slope is undefined"
        )
    return float(np.dot(centred, y - y.mean()) / denominator)


def identity_slopes(
    rows: Sequence[Mapping[str, Any]],
    *,
    q_levels: Sequence[float] = (Q_LOW, Q_MID, Q_HIGH),
    tau_support: Sequence[int] = TAU_PRIMARY_SUPPORT,
) -> dict[str, dict[float, float]]:
    """``b_i(q)``: the OLS slope of raw ``sigma_hat`` on tau, per identity per q."""
    support = set(int(value) for value in tau_support)
    buckets: dict[tuple[str, float], dict[int, float]] = {}
    for row in rows:
        tau = int(row["tau"])
        if tau not in support:
            continue
        q = float(row["q"])
        level = next((value for value in q_levels if math.isclose(q, value)), None)
        if level is None:
            continue
        cell = buckets.setdefault((str(row["identity"]), level), {})
        if tau in cell:
            raise ExperimentIIIError(
                "B_U3_ANALYSIS_FAIL",
                f"duplicate held-out prediction at {(row['identity'], level, tau)}",
            )
        cell[tau] = float(row["sigma_hat"])
    slopes: dict[str, dict[float, float]] = {}
    for (identity, level), cell in buckets.items():
        taus = sorted(cell)
        slopes.setdefault(identity, {})[level] = _ols_slope(
            taus, [cell[tau] for tau in taus]
        )
    return slopes


def u3_s1(
    rows: Sequence[Mapping[str, Any]],
    *,
    seed: int,
    q_levels: Sequence[float] = (Q_LOW, Q_MID, Q_HIGH),
    replicates: int = BOOTSTRAP_B,
) -> dict[str, Any]:
    """Pooled per-identity uncertainty growth rate, plus descriptive per-``q`` means."""
    slopes = identity_slopes(rows, q_levels=q_levels)
    identities = sorted(slopes)
    pooled = {
        identity: float(np.mean([slopes[identity][level] for level in q_levels]))
        for identity in identities
    }
    values = np.asarray([pooled[name] for name in identities], dtype=np.float64)
    position = {name: index for index, name in enumerate(identities)}

    def statistic(sample: Sequence[str]) -> float:
        return float(values[[position[name] for name in sample]].mean())

    result = bootstrap_inversion(
        identities, statistic, seed=seed, t_null=0.0, replicates=replicates, label="U3-S1"
    )
    result.update(
        {
            "name": "PER_IDENTITY_UNCERTAINTY_GROWTH_RATE",
            "pooled_across_q": True,
            "per_identity_pooled_slope": pooled,
            "per_q_identity_macro_mean": {
                f"{level:.4f}": float(
                    np.mean([slopes[name][level] for name in identities])
                )
                for level in q_levels
            },
            "per_q_means_are_descriptive": True,
            "uses_raw_sigma_hat": True,
        }
    )
    return result


def u3_s2(
    rows: Sequence[Mapping[str, Any]],
    *,
    seed: int,
    q_low: float = Q_LOW,
    q_high: float = Q_HIGH,
    replicates: int = BOOTSTRAP_B,
) -> dict[str, Any]:
    """``Delta_i = b_i(q_high) - b_i(q_low)`` -- the decisive interaction."""
    slopes = identity_slopes(rows, q_levels=(q_low, q_high))
    identities = sorted(slopes)
    deltas = np.asarray(
        [slopes[name][q_high] - slopes[name][q_low] for name in identities],
        dtype=np.float64,
    )

    position = {name: index for index, name in enumerate(identities)}

    def statistic(sample: Sequence[str]) -> float:
        return float(deltas[[position[name] for name in sample]].mean())

    result = bootstrap_inversion(
        identities, statistic, seed=seed, t_null=0.0, replicates=replicates, label="U3-S2"
    )
    result.update(
        {
            "name": "Q_DEPENDENT_RATE_INTERACTION",
            "role": "MAIN_PROTECTION_AGAINST_ADDITIVE_CLOCK_PLUS_Q_CATEGORY",
            "per_identity_delta": {
                name: float(value) for name, value in zip(identities, deltas)
            },
            "uses_raw_sigma_hat": True,
        }
    )
    return result


def u3_s3(
    rows: Sequence[Mapping[str, Any]],
    *,
    q_levels: Sequence[float] = (Q_LOW, Q_MID, Q_HIGH),
) -> dict[str, Any]:
    """Descriptive slope ratios against the oracle's exact ``sqrt(q)`` ratios."""
    slopes = identity_slopes(rows, q_levels=q_levels)
    identities = sorted(slopes)
    means = {
        level: float(np.mean([slopes[name][level] for name in identities]))
        for level in q_levels
    }
    low, mid, high = (means[level] for level in q_levels)
    observed = {
        "q_high_over_q_mid": high / mid if mid else float("inf"),
        "q_mid_over_q_low": mid / low if low else float("inf"),
        "q_high_over_q_low": high / low if low else float("inf"),
    }
    return {
        "statistic": "U3-S3",
        "name": "DESCRIPTIVE_SLOPE_RATIO_COMPARISON",
        "observed_ratios": observed,
        "oracle_ratios": dict(ORACLE_SLOPE_RATIOS),
        "enters_family": False,
        "holm_corrected": False,
        "role": "DESCRIPTIVE_ONLY",
        "pass_fail_gate": None,
    }


def u3_analysis(
    rows: Sequence[Mapping[str, Any]],
    *,
    seed: int,
    u2_passed: bool,
    q_levels: Sequence[float] = (Q_LOW, Q_MID, Q_HIGH),
    replicates: int = BOOTSTRAP_B,
) -> dict[str, Any]:
    """The two inferential U3 statistics under Holm ``m = 2``, plus U3-S3."""
    members = {
        "U3-S1": u3_s1(rows, seed=seed, q_levels=q_levels, replicates=replicates),
        "U3-S2": u3_s2(rows, seed=seed, replicates=replicates),
    }
    adjusted = holm(
        {name: member["p_value"] for name, member in members.items()},
        family_order=U3_FAMILY_ORDER,
    )
    return {
        "schema_version": "mineocclude-experiment-iii-b-u3-results-v1",
        "family": list(U3_FAMILY_ORDER),
        "family_size": len(U3_FAMILY_ORDER),
        "alpha": ALPHA,
        "members": members,
        "holm_adjusted_p_values": adjusted,
        "significant": {
            name: bool(adjusted[name] <= ALPHA) for name in U3_FAMILY_ORDER
        },
        "descriptive_only": {**u3_s3(rows, q_levels=q_levels)},
        "hierarchical_on_u2": True,
        "u2_passed": bool(u2_passed),
        "claim_status": "SCIENTIFIC" if u2_passed else "DESCRIPTIVE",
        "scientific_claims_permitted": bool(u2_passed),
        "intervals_are_unadjusted": True,
    }
