"""The frozen III-B inferential procedure (authority 22.0).

```
CI_ROLE   = EFFECT_SIZE_REPORTING
HOLM_ROLE = FAMILYWISE_HYPOTHESIS_DECISION
```

Intervals **report**; Holm-adjusted p-values **decide**. Every interval in III-B
is an ordinary two-sided 95% whole-identity bootstrap percentile interval with
``B = 10,000``, unadjusted, carrying no familywise guarantee. The phrase
"Holm-adjusted CI" names no procedure and is refused outright by
:func:`assert_no_holm_adjusted_interval_language`.

The inference unit is the **identity**. Rows are never independent units, so
every resampling pass here draws whole identities with replacement and
recomputes the *entire* statistic -- ranking, residualization, fold-wise pooling
and all -- inside each replicate.
"""

from __future__ import annotations

import math
from typing import Any, Callable, Mapping, Sequence

import numpy as np

from mineocclude.experiment_iii.errors import ExperimentIIIError

__all__ = [
    "ALPHA",
    "BOOTSTRAP_B",
    "PERMUTATION_B",
    "U2_FAMILY_AT_DROP_LEVEL_1",
    "U2_FAMILY_ORDER",
    "U3_FAMILY_ORDER",
    "assert_family",
    "assert_no_holm_adjusted_interval_language",
    "bootstrap_inversion",
    "holm",
    "percentile_interval",
    "whole_identity_replicates",
    "within_identity_q_permutation_p_value",
]

BOOTSTRAP_B = 10_000
PERMUTATION_B = 9_999
ALPHA = 0.05

U2_FAMILY_ORDER = ("U2-S1", "U2-S2", "U2-S3")
U2_FAMILY_AT_DROP_LEVEL_1 = ("U2-S1", "U2-S2")
U3_FAMILY_ORDER = ("U3-S1", "U3-S2")

_FORBIDDEN_INTERVAL_PHRASES = (
    "holm-adjusted ci",
    "holm adjusted ci",
    "holm-adjusted confidence interval",
    "holm adjusted confidence interval",
    "holm-adjusted interval",
    "holm adjusted interval",
)


def assert_no_holm_adjusted_interval_language(*texts: str) -> None:
    """Refuse the phrase "Holm-adjusted CI" anywhere in reported output.

    Holm adjusts p-values. A "CI after Holm" is not a unique construction, and
    describing an interval that way misstates what decided significance.
    """
    for text in texts:
        lowered = str(text).lower()
        for phrase in _FORBIDDEN_INTERVAL_PHRASES:
            if phrase in lowered:
                raise ExperimentIIIError(
                    "B_INFERENCE_PROCEDURE_MISMATCH",
                    f"{phrase!r} names no procedure: intervals are ordinary "
                    "unadjusted 95% percentile intervals and Holm adjusts "
                    "p-values, never intervals",
                )


def assert_family(members: Sequence[str], expected: Sequence[str]) -> None:
    """Refuse a family that has been inflated, reduced or reordered post hoc."""
    if tuple(members) != tuple(expected):
        raise ExperimentIIIError(
            "B_U2_FAMILY_ALTERED",
            f"the frozen family is {tuple(expected)}, got {tuple(members)}; the "
            "family may not be altered after results exist",
        )


def whole_identity_replicates(
    identities: Sequence[str], *, seed: int, replicates: int = BOOTSTRAP_B
) -> np.ndarray:
    """Bootstrap index draws over WHOLE identities, under the frozen seed."""
    if replicates != BOOTSTRAP_B:
        raise ExperimentIIIError(
            "B_INFERENCE_PROCEDURE_MISMATCH",
            f"B is frozen at {BOOTSTRAP_B}, got {replicates}",
        )
    if len(identities) < 2:
        raise ExperimentIIIError(
            "B_INFERENCE_PROCEDURE_MISMATCH",
            "the whole-identity bootstrap needs at least two identities",
        )
    rng = np.random.default_rng(seed)
    return rng.integers(0, len(identities), size=(replicates, len(identities)))


def percentile_interval(samples: Sequence[float]) -> tuple[float, float]:
    """Ordinary two-sided 95% percentile interval. Unadjusted, reporting only."""
    values = np.asarray(samples, dtype=np.float64)
    low, high = np.percentile(values, [2.5, 97.5])
    return float(low), float(high)


def bootstrap_inversion(
    identities: Sequence[str],
    statistic: Callable[[Sequence[str]], float],
    *,
    seed: int,
    t_null: float,
    replicates: int = BOOTSTRAP_B,
    label: str = "",
) -> dict[str, Any]:
    """The frozen one-sided bootstrap-inversion procedure of authority 22.0.

    One resampling pass serves both the reported interval and the p-value.
    ``p = (1 + #{T*_b <= T_null}) / (B + 1)``, clipped to ``[1/(B+1), 1]`` so it
    is never exactly zero.
    """
    names = list(identities)
    observed = float(statistic(names))
    if not math.isfinite(observed):
        raise ExperimentIIIError(
            "B_INFERENCE_PROCEDURE_MISMATCH",
            f"{label or 'the statistic'} produced a non-finite observed value; no "
            "decision may rest on an IEEE comparison against NaN",
        )
    draws = whole_identity_replicates(names, seed=seed, replicates=replicates)
    samples = np.empty(draws.shape[0], dtype=np.float64)
    for index, row in enumerate(draws):
        samples[index] = statistic([names[position] for position in row])
    if not np.isfinite(samples).all():
        raise ExperimentIIIError(
            "B_INFERENCE_PROCEDURE_MISMATCH",
            f"{label or 'the statistic'} produced a non-finite bootstrap replicate",
        )
    low, high = percentile_interval(samples)
    floor = 1.0 / (replicates + 1)
    raw = (1 + int(np.count_nonzero(samples <= t_null))) / (replicates + 1)
    return {
        "statistic": label,
        "observed": observed,
        "ci_low": low,
        "ci_high": high,
        "ci_is_unadjusted": True,
        "ci_role": "EFFECT_SIZE_REPORTING",
        "p_value": min(1.0, max(floor, raw)),
        "p_value_floor": floor,
        "p_null": float(t_null),
        "sided": "ONE_SIDED",
        "replicates": replicates,
        "seed": seed,
        "resampling_unit": "WHOLE_IDENTITY",
        "construction": "WHOLE_IDENTITY_BOOTSTRAP_INVERSION",
    }


def within_identity_q_permutation_p_value(
    differences: Sequence[Sequence[float]],
    *,
    seed: int,
    permutations: int = PERMUTATION_B,
) -> dict[str, Any]:
    """U2-S1's null: permute ``q_low``/``q_high`` labels WITHIN each identity.

    ``differences`` is the ``(identity, tau)`` matrix of
    ``sigma_hat(q_high) - sigma_hat(q_low)``. Authority 22.1 holds tau, identity,
    fold "and everything else" fixed, so the label permutation acts inside each
    ``(identity, tau)`` stratum. Each stratum holds exactly the two labels, so
    its two permutations are the identity and the swap -- i.e. the sign of
    ``D_i,tau``. This is the exact permutation set, enumerated rather than
    approximated, and it destroys the ``q`` -> sigma association while preserving
    every clock, identity and context structure.

    ``p = (1 + #{D_perm >= D_obs}) / 10,000``.
    """
    if permutations != PERMUTATION_B:
        raise ExperimentIIIError(
            "B_INFERENCE_PROCEDURE_MISMATCH",
            f"the permutation B is frozen at {PERMUTATION_B}, got {permutations}",
        )
    matrix = np.asarray(differences, dtype=np.float64)
    if matrix.ndim != 2 or matrix.size == 0:
        raise ExperimentIIIError(
            "B_TAU_ALIGNMENT_ERROR",
            "U2-S1 needs a two-dimensional (identity, tau) difference matrix; "
            "matching is by occlusion age, never by absolute frame index",
        )
    if not np.isfinite(matrix).all():
        raise ExperimentIIIError(
            "B_INFERENCE_PROCEDURE_MISMATCH",
            "a non-finite matched-tau difference reached the permutation null",
        )
    observed = float(np.mean(np.mean(matrix, axis=1)))
    rng = np.random.default_rng(seed)
    signs = rng.integers(0, 2, size=(permutations, *matrix.shape)) * 2 - 1
    permuted = np.mean(np.mean(signs * matrix, axis=2), axis=1)
    total = permutations + 1
    return {
        "observed": observed,
        "p_value": (1 + int(np.count_nonzero(permuted >= observed))) / total,
        "permutations": permutations,
        "denominator": total,
        "seed": seed,
        "sided": "ONE_SIDED",
        "stratum": "IDENTITY_X_TAU",
        "construction": "WITHIN_IDENTITY_Q_ASSIGNMENT_PERMUTATION",
    }


def holm(
    p_values: Mapping[str, float], *, family_order: Sequence[str]
) -> dict[str, float]:
    """Holm step-down with monotonicity, ties broken by the frozen member order.

    ``padj_(1) = min(1, m*p_(1))``;
    ``padj_(k) = min(1, max(padj_(k-1), (m-k+1)*p_(k)))``.
    """
    assert_family(sorted(p_values), sorted(family_order))
    order = {name: position for position, name in enumerate(family_order)}
    ordered = sorted(p_values.items(), key=lambda item: (item[1], order[item[0]]))
    size = len(ordered)
    adjusted: dict[str, float] = {}
    running = 0.0
    for rank, (name, raw) in enumerate(ordered):
        running = min(1.0, max(running, (size - rank) * float(raw)))
        adjusted[name] = running
    return {name: adjusted[name] for name in family_order}
