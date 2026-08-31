"""III-A statistical machinery (authority 8.10-8.12, 15.1).

**Inferential unit: the trajectory identity.** Not the row, not the frame, not the
capture. Row- or capture-level inference is pseudo-replication
(``STATS_BOOTSTRAP_UNIT_VIOLATION``).

Primary family, and only these three:

    S_i        OLS slope of RMSE_ic on O_c across L0..L4
    Dpartial_i mean(RMSE_i,L1:L3) - RMSE_i,L0
    Dopaque_i  RMSE_i,L4 - RMSE_i,L3

All three are hypothesized positive, tested one-sided, Holm-adjusted across
exactly three, with two-sided 95% whole-identity bootstrap intervals at
``B = 10,000``.

Intervals **report**; Holm-adjusted p-values **decide**. There is no overall
experiment pass/fail gate and no success threshold; adding one is
``ANALYSIS_SUCCESS_GATE_REINTRODUCED``. The B=49 derangement null is not ported.

Nothing here inspects a scientific outcome on import, and every entry point
refuses to run before the prediction lock is sealed.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

import numpy as np

from mineocclude.experiment_iii.errors import ExperimentIIIError
from mineocclude.experiment_iii.prediction_lock import PredictionLock
from mineocclude.experiment_iii.schema import ConditionId

__all__ = [
    "BOOTSTRAP_REPLICATES",
    "PRIMARY_FAMILY",
    "SECONDARY_FAMILIES",
    "REMOVED_GATES",
    "CONTEXT_AGE_BINS",
    "BOUNDARY_INTERACTION_WINDOWS",
    "IdentityMetrics",
    "identity_metrics",
    "evidence_coordinate",
    "slope_on_evidence",
    "primary_estimands",
    "one_sided_t_test",
    "holm_adjust",
    "identity_bootstrap_interval",
    "primary_analysis",
    "l0_interpretability_control",
    "temporal_rescue",
    "context_age_bin",
    "boundary_interaction",
    "assert_no_success_gate",
]

BOOTSTRAP_REPLICATES = 10_000
PRIMARY_FAMILY = ("S_i", "Dpartial_i", "Dopaque_i")
SECONDARY_FAMILIES = (
    "MINEWORLD_VS_LINEAR_CURRENT_PIXEL",
    "TEMPORAL_RESCUE",
    "CONTEXT_BOUNDARY",
    "MOTION_AND_CLOCK_BASELINES",
    "DEPTH_PANEL",
)

#: Authority 8.10.6 — removed and never to reappear.
REMOVED_GATES = (
    "DISCONTINUITY_RATIO_GE_3",
    "EXPECTED_OPAQUE_R2_RMSE_REPRODUCTION_GATE",
    "B_199_PER_CONDITION_DECODER_NULLS",
    "B_49_SELECTION_AWARE_DERANGEMENT_NULL",
    "PIXEL_COMPARISON_IN_PRIMARY_HOLM_FAMILY",
    "ROW_LEVEL_PSEUDOREPLICATION",
    "MLP_STRETCH_RESCUE",
    "OUTCOME_DEPENDENT_CONDITION_DROPPING",
    "OVERALL_EXPERIMENT_PASS_FAIL_QUALIFICATION",
)

CONTEXT_AGE_BINS = ((1, 5), (6, 10), (11, 15), (16, 19))
BOUNDARY_INTERACTION_WINDOWS = ((12, 15), (16, 19))


@dataclass(frozen=True)
class IdentityMetrics:
    """Per-(identity, condition) metrics from that cell's 19 held-out rows."""

    identity: str
    condition_id: str
    rmse: float
    mae: float
    r2: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "identity": self.identity,
            "condition_id": self.condition_id,
            "rmse": self.rmse,
            "mae": self.mae,
            "r2": self.r2,
        }


def identity_metrics(
    identity: str,
    condition_id: str,
    targets: Sequence[float],
    predictions: Sequence[float],
) -> IdentityMetrics:
    """RMSE (primary), MAE and R^2 for one cell. Zero TSS is refused."""
    observed = np.asarray(targets, dtype=np.float64)
    predicted = np.asarray(predictions, dtype=np.float64)
    if observed.shape != predicted.shape or observed.size == 0:
        raise ExperimentIIIError(
            "FEATURE_ROW_ORDER_MISMATCH",
            f"{identity}/{condition_id}: target and prediction shapes differ",
        )
    residual = observed - predicted
    total = float(np.sum((observed - observed.mean()) ** 2))
    if total == 0.0:
        raise ExperimentIIIError(
            "STATS_ZERO_TSS",
            f"{identity}/{condition_id} has zero total sum of squares; the "
            "target-SD floor of 0.10 blocks should have prevented this",
        )
    return IdentityMetrics(
        identity=identity,
        condition_id=condition_id,
        rmse=float(np.sqrt(np.mean(residual**2))),
        mae=float(np.mean(np.abs(residual))),
        r2=float(1.0 - np.sum(residual**2) / total),
    )


def evidence_coordinate(v_c: Mapping[str, float]) -> dict[str, float]:
    """``O_c = 1 - V_c``. ``V_0 = 1`` by definition; ``V_4`` is measured."""
    if abs(float(v_c[ConditionId.L0.value]) - 1.0) > 0.0:
        raise ExperimentIIIError(
            "ANALYSIS_FAMILY_ALTERED", "V_L0 is 1 by definition"
        )
    return {name: 1.0 - float(value) for name, value in v_c.items()}


def slope_on_evidence(
    rmse_by_condition: Mapping[str, float], o_c: Mapping[str, float]
) -> float:
    """OLS slope of RMSE on the evidence coordinate across all five conditions."""
    names = [condition.value for condition in ConditionId]
    missing = [name for name in names if name not in rmse_by_condition]
    if missing:
        raise ExperimentIIIError(
            "ANALYSIS_INPUT_NOT_LOCKED",
            f"the slope needs all five conditions; missing {missing}",
        )
    x = np.asarray([float(o_c[name]) for name in names], dtype=np.float64)
    y = np.asarray([float(rmse_by_condition[name]) for name in names], dtype=np.float64)
    centred = x - x.mean()
    denominator = float(np.sum(centred**2))
    if denominator == 0.0:
        raise ExperimentIIIError(
            "ANALYSIS_FAMILY_ALTERED",
            "the evidence coordinate is constant across conditions",
        )
    return float(np.sum(centred * (y - y.mean())) / denominator)


def primary_estimands(
    rmse_by_condition: Mapping[str, float], o_c: Mapping[str, float]
) -> dict[str, float]:
    """The three per-identity primary estimands, and only these three."""
    partial = [
        float(rmse_by_condition[name])
        for name in (ConditionId.L1.value, ConditionId.L2.value, ConditionId.L3.value)
    ]
    return {
        "S_i": slope_on_evidence(rmse_by_condition, o_c),
        "Dpartial_i": float(np.mean(partial))
        - float(rmse_by_condition[ConditionId.L0.value]),
        "Dopaque_i": float(rmse_by_condition[ConditionId.L4.value])
        - float(rmse_by_condition[ConditionId.L3.value]),
    }


def one_sided_t_test(values: Sequence[float]) -> tuple[float, float, float]:
    """One-sided identity-level t test in the hypothesized POSITIVE direction.

    Returns ``(mean, standard_error, p_value)``.
    """
    sample = np.asarray([float(value) for value in values], dtype=np.float64)
    n = sample.size
    if n < 2:
        raise ExperimentIIIError(
            "STATS_BOOTSTRAP_UNIT_VIOLATION",
            "an identity-level test needs at least two identities",
        )
    mean = float(sample.mean())
    sd = float(sample.std(ddof=1))
    if sd == 0.0:
        return mean, 0.0, 0.0 if mean > 0 else 1.0
    standard_error = sd / math.sqrt(n)
    statistic = mean / standard_error
    try:
        from scipy import stats as scipy_stats

        p_value = float(scipy_stats.t.sf(statistic, df=n - 1))
    except ImportError:  # pragma: no cover - scipy is a declared dependency
        p_value = float(0.5 * math.erfc(statistic / math.sqrt(2.0)))
    return mean, standard_error, p_value


def holm_adjust(p_values: Mapping[str, float]) -> dict[str, float]:
    """Holm step-down across exactly the supplied family.

    Adjusted p-values decide significance; intervals only report. An output that
    describes an interval as "Holm-adjusted" is a reporting violation.
    """
    if not p_values:
        raise ExperimentIIIError(
            "STATS_MULTIPLICITY_FAMILY_MISMATCH", "the family is empty"
        )
    ordered = sorted(p_values.items(), key=lambda item: (item[1], item[0]))
    size = len(ordered)
    adjusted: dict[str, float] = {}
    running = 0.0
    for rank, (name, raw) in enumerate(ordered):
        candidate = (size - rank) * float(raw)
        running = max(running, min(candidate, 1.0))
        adjusted[name] = running
    return adjusted


def identity_bootstrap_interval(
    per_identity: Mapping[str, float],
    *,
    seed: int,
    replicates: int = BOOTSTRAP_REPLICATES,
    statistic=None,
) -> dict[str, float]:
    """Two-sided 95% interval, resampling WHOLE identities with replacement.

    The resampling unit is the identity, carrying all five conditions, all rows,
    all predictions and all representations together. Resampling rows or captures
    is pseudo-replication and is refused elsewhere by
    :func:`assert_identity_level_unit`.
    """
    if replicates != BOOTSTRAP_REPLICATES:
        raise ExperimentIIIError(
            "STATS_BOOTSTRAP_UNIT_VIOLATION",
            f"B is frozen at {BOOTSTRAP_REPLICATES}, got {replicates}",
        )
    names = sorted(per_identity)
    if len(names) < 2:
        raise ExperimentIIIError(
            "STATS_BOOTSTRAP_UNIT_VIOLATION",
            "the bootstrap needs at least two identities",
        )
    values = np.asarray([float(per_identity[name]) for name in names], dtype=np.float64)
    reducer = statistic or (lambda sample: float(np.mean(sample)))
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, len(values), size=(replicates, len(values)))
    samples = np.asarray([reducer(values[row]) for row in draws], dtype=np.float64)
    low, high = np.percentile(samples, [2.5, 97.5])
    return {
        "point_estimate": float(np.mean(values)),
        "ci_low": float(low),
        "ci_high": float(high),
        "replicates": replicates,
        "seed": seed,
        "resampling_unit": "WHOLE_IDENTITY",
        "note": "intervals report; Holm-adjusted p-values decide",
    }


def assert_identity_level_unit(unit: str) -> None:
    if unit != "IDENTITY":
        raise ExperimentIIIError(
            "STATS_BOOTSTRAP_UNIT_VIOLATION",
            f"the inferential unit is the trajectory identity, not {unit}; "
            "row- or capture-level inference is pseudo-replication",
        )


def assert_no_success_gate(payload: Mapping[str, Any]) -> None:
    """Refuse any overall pass/fail verdict or reintroduced success gate."""
    forbidden = {
        "experiment_passed",
        "experiment_result",
        "overall_verdict",
        "success",
        "qualified",
        "pass_fail",
        "discontinuity_ratio",
    }
    present = sorted(set(payload) & forbidden)
    if present:
        raise ExperimentIIIError(
            "ANALYSIS_SUCCESS_GATE_REINTRODUCED",
            f"Experiment III emits no overall pass/fail verdict; found {present}",
        )
    for gate in REMOVED_GATES:
        if gate in payload:
            raise ExperimentIIIError(
                "ANALYSIS_SUCCESS_GATE_REINTRODUCED",
                f"{gate} was removed by authority 8.10.6 and may not reappear",
            )


def primary_analysis(
    per_identity_estimands: Mapping[str, Mapping[str, float]],
    *,
    lock: PredictionLock,
    bootstrap_seed: int,
) -> dict[str, Any]:
    """The frozen primary family: three estimands, Holm-3, one-sided, positive."""
    lock.require_sealed("the primary analysis")
    families = {name: {} for name in PRIMARY_FAMILY}
    for identity, estimands in per_identity_estimands.items():
        unknown = set(estimands) - set(PRIMARY_FAMILY)
        if unknown:
            raise ExperimentIIIError(
                "ANALYSIS_FAMILY_ALTERED",
                f"the primary family is exactly {PRIMARY_FAMILY}; found {sorted(unknown)}",
            )
        for name in PRIMARY_FAMILY:
            families[name][identity] = float(estimands[name])

    raw: dict[str, float] = {}
    results: dict[str, Any] = {}
    for name in PRIMARY_FAMILY:
        mean, standard_error, p_value = one_sided_t_test(list(families[name].values()))
        raw[name] = p_value
        results[name] = {
            "mean": mean,
            "standard_error": standard_error,
            "raw_p_value": p_value,
            "hypothesis": "POSITIVE",
            "test": "ONE_SIDED_IDENTITY_LEVEL_T_TEST",
            "interval": identity_bootstrap_interval(
                families[name], seed=bootstrap_seed
            ),
        }
    adjusted = holm_adjust(raw)
    for name in PRIMARY_FAMILY:
        results[name]["holm_adjusted_p_value"] = adjusted[name]
        results[name]["significant"] = adjusted[name] < 0.05

    payload = {
        "schema_version": "mineocclude-experiment-iii-primary-analysis-v1",
        "authority_section": "8.10",
        "family": list(PRIMARY_FAMILY),
        "family_size": len(PRIMARY_FAMILY),
        "multiplicity": "HOLM_ACROSS_3",
        "inferential_unit": "IDENTITY",
        "bootstrap_replicates": BOOTSTRAP_REPLICATES,
        "bootstrap_seed": bootstrap_seed,
        "prediction_lock_sha256": lock.sealed_hash,
        "decisions_come_from": "HOLM_ADJUSTED_P_VALUES",
        "intervals_are_descriptive": True,
        "estimands": results,
    }
    assert_no_success_gate(payload)
    return payload


def l0_interpretability_control(
    model_l0_rmse: Mapping[str, float],
    training_mean_l0_rmse: Mapping[str, float],
    *,
    lock: PredictionLock,
    bootstrap_seed: int,
) -> dict[str, Any]:
    """The single L0 control: model improvement over the training-mean baseline.

    On failure the experiment becomes an apparatus/readout-limited result and
    still closes; nothing is retuned, replaced or redefined.
    """
    lock.require_sealed("the L0 interpretability control")
    improvement = {
        identity: float(training_mean_l0_rmse[identity]) - float(value)
        for identity, value in model_l0_rmse.items()
    }
    interval = identity_bootstrap_interval(improvement, seed=bootstrap_seed)
    passed = interval["ci_low"] > 0.0
    return {
        "schema_version": "mineocclude-experiment-iii-l0-control-v1",
        "authority_section": "8.11",
        "statistic": "L0_RMSE_IMPROVEMENT_OVER_OUTER_TRAINING_MEAN",
        "interval": interval,
        "excludes_zero_in_the_favorable_direction": passed,
        "interpretation": (
            "interpretable" if passed else "APPARATUS_READOUT_LIMITED_RESULT"
        ),
        "on_failure_retune_allowed": False,
        "on_failure_replace_identities_allowed": False,
        "on_failure_redefine_representation_allowed": False,
        "experiment_can_still_close": True,
    }


def temporal_rescue(
    per_identity: Mapping[str, Mapping[str, float]],
    *,
    lock: PredictionLock,
    bootstrap_seed: int,
) -> dict[str, Any]:
    """Secondary family B: Holm across exactly TWO temporal comparisons."""
    lock.require_sealed("the temporal rescue family")
    contrasts = ("CURRENT_MINUS_PREVIOUS_VS_CURRENT", "TWO_FRAME_CONCAT_VS_CURRENT")
    raw: dict[str, float] = {}
    results: dict[str, Any] = {}
    for name in contrasts:
        values = {
            identity: float(row[name]) for identity, row in per_identity.items()
        }
        mean, standard_error, p_value = one_sided_t_test(list(values.values()))
        raw[name] = p_value
        results[name] = {
            "mean": mean,
            "standard_error": standard_error,
            "raw_p_value": p_value,
            "interval": identity_bootstrap_interval(values, seed=bootstrap_seed),
        }
    adjusted = holm_adjust(raw)
    for name in contrasts:
        results[name]["holm_adjusted_p_value"] = adjusted[name]
    return {
        "family": list(contrasts),
        "family_size": 2,
        "multiplicity": "HOLM_ACROSS_2",
        "tests": "TWO_ONE_SIDED_PAIRED_T_TESTS",
        "contrasts": results,
    }


def context_age_bin(age: int) -> str:
    for low, high in CONTEXT_AGE_BINS:
        if low <= age <= high:
            return f"{low}-{high}"
    raise ExperimentIIIError(
        "ANALYSIS_CONTEXT_BIN_MISMATCH", f"context age {age} is outside 1..19"
    )


def boundary_interaction(
    rmse_l4: Mapping[tuple[int, int], float],
    rmse_partial_mean: Mapping[tuple[int, int], float],
) -> float:
    """The single prespecified descriptive boundary interaction.

    Uses the ADJACENT four-row windows 12-15 and 16-19 straddling the context
    boundary at a = 15/16 — deliberately not the four reporting bins.
    """
    early, late = BOUNDARY_INTERACTION_WINDOWS
    for table, label in ((rmse_l4, "L4"), (rmse_partial_mean, "L1..L3 mean")):
        missing = [window for window in (early, late) if window not in table]
        if missing:
            raise ExperimentIIIError(
                "ANALYSIS_CONTEXT_BIN_MISMATCH",
                f"{label} lacks window(s) {missing}; the interaction uses 12-15 "
                "and 16-19",
            )
    return (float(rmse_l4[late]) - float(rmse_l4[early])) - (
        float(rmse_partial_mean[late]) - float(rmse_partial_mean[early])
    )
