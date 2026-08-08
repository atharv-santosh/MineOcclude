"""Frozen baseline metrics for the 66-cell production run (Person D).

Computes Person D's baseline metrics using **Person B's own frozen metric
implementations** -- ``mineocclude.metrics.u1_mean``,
``mineocclude.metrics.u2_calibration``, and
``mineocclude.metrics.resampling`` -- under the exact arithmetic,
grouping, seed, and resampling conventions Person B's
``b_to_d_successor_handoff.json`` declares. Nothing here reimplements a
statistic, and no threshold is applied: Person D reports values, Person B
interprets them.

Three things are deliberately *not* computed, each recorded as blocked
with its reason rather than substituted:

* **Probe-versus-baseline comparison.** ``baseline_comparison`` in Person
  B's U1 output list compares a probe against these baselines. No probe
  exists until Person A's activation index does. Person D instead reports
  baseline-versus-chance-floor deltas, which are D-owned and available
  now, and labels them as such.
* **Coverage / ECE / z-diagnostics.** ``calibration_metrics`` needs a
  paired mean *and* spread on the same rows. Every Person D spread family
  (``time_only``, ``visible_history_q``, ``known_q_analytic``) explicitly
  defines no mean prediction, and no frozen Person D baseline pairs a
  spread family with a mean family. Manufacturing such a pair would be a
  new method, so these are reported unavailable.
* **U3 reveal snapback.** Requires terminal reveal events; the 66-cell
  dataset has none (``VALID_TERMINAL_REVEAL_COUNT = 0``).

Non-finite policy is Person B's: ``count_and_fail_result_no_clipping``.
A metric that cannot be computed honestly is recorded as unavailable with
its reason; it is never clipped, imputed, or silently dropped.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Optional

from mineocclude.baselines.interface import BaselineRow
from mineocclude.metrics.resampling import (
    ResamplingError,
    bootstrap_confidence_interval,
    hierarchical_bootstrap_indices,
    permutation_p_value,
    permute_trajectory_blocks,
)
from mineocclude.metrics.u1_mean import U1MetricError, regression_metrics
from mineocclude.metrics.u2_calibration import (
    U2MetricError,
    partial_correlation_controlling_tau,
)

SCHEMA_ID = "person-d-66-cell-baseline-metrics-v0-1"
SCHEMA_VERSION = "1.0"

#: Person B's frozen conventions, copied verbatim from
#: ``b_to_d_successor_handoff.json -> metric_contract_after_person_d_predictions_exist``.
ANALYSIS_ARITHMETIC_DTYPE = "float64"
ANALYSIS_CONFIG_VERSION = "person-b-phase1-v0.2"
GROUPING_HIERARCHY: tuple[str, ...] = ("layout_id", "trajectory_id")
COVERAGE_LEVELS: tuple[float, ...] = (0.5, 0.8, 0.95)
BOOTSTRAP_COUNT_MVP = 1000
BOOTSTRAP_SEED = 20260721
BOOTSTRAP_COVERAGE = 0.95
PERMUTATION_COUNT_MVP = 999
PERMUTATION_SEED = 20260720
PERMUTATION_UNIT = "whole_trajectory_block"
PERMUTATION_P_VALUE_RULE = "add_one_greater_or_equal"
NONFINITE_POLICY = "count_and_fail_result_no_clipping"
NEAR_ZERO_SIGMA_THRESHOLD_BLOCKS = 1e-12

U1_TARGET = "mu_oracle_blocks"
U2_TARGET = "log_sigma_oracle"

#: The frozen chance floor every other family is compared against.
CHANCE_FLOOR_FAMILY = "grouped_shuffled"

#: Person D's already-published comparison-class labels, restated so a
#: reader can never mistake a privileged ceiling for a fair competitor.
COMPARISON_CLASS_BY_FAMILY: Mapping[str, str] = {
    "last_seen": "memory_heuristic",
    "constant_velocity": "reference",
    "grouped_shuffled": "chance_floor",
    "time_only": "clock_floor",
    "explicit_feature": "fair_fitted_ceiling",
    "raw_pixel": "fair_fitted_ceiling",
    "visible_history_q": "fair_baseline",
    "known_q_analytic": "privileged_oracle_ceiling",
}

RowKey = tuple[str, int]


class BaselineMetricsError(ValueError):
    """Raised when a metric package cannot be assembled honestly."""


@dataclass(frozen=True)
class ScoredRow:
    """One scored prediction paired with its oracle truth and identity."""

    trajectory_id: str
    layout_id: str
    model_frame_idx: int
    fold_idx: int
    control_type: str
    prediction: float
    truth: float
    tau_seconds: float


def _unavailable(reason: str) -> dict[str, Any]:
    return {"available": False, "reason": reason}


def _regression_block(
    truth: Sequence[float], predictions: Sequence[float]
) -> dict[str, Any]:
    """Person B's ``regression_metrics``, or an explicit unavailability."""

    if not truth:
        return _unavailable("no scored rows")
    try:
        metrics = regression_metrics(truth, predictions)
    except U1MetricError as error:
        return _unavailable(f"u1_metric_error:{error}")
    return {
        "available": True,
        "sample_count": metrics.sample_count,
        "r2": metrics.r2,
        "mae": metrics.mae,
        "mse": metrics.mse,
    }


def _bootstrap_r2_interval(rows: Sequence[ScoredRow]) -> dict[str, Any]:
    """Hierarchical layout->trajectory bootstrap CI on R-squared."""

    if len(rows) < 2:
        return _unavailable("fewer than two scored rows")
    payload = [
        {"layout_id": row.layout_id, "trajectory_id": row.trajectory_id} for row in rows
    ]
    try:
        replicates = hierarchical_bootstrap_indices(
            payload, resample_count=BOOTSTRAP_COUNT_MVP, seed=BOOTSTRAP_SEED
        )
    except ResamplingError as error:
        return _unavailable(f"resampling_error:{error}")

    statistics: list[float] = []
    refused = 0
    for indices in replicates:
        try:
            statistics.append(
                regression_metrics(
                    [rows[i].truth for i in indices],
                    [rows[i].prediction for i in indices],
                ).r2
            )
        except U1MetricError:
            refused += 1
    if not statistics:
        return _unavailable("every bootstrap replicate was refused by regression_metrics")
    try:
        low, high = bootstrap_confidence_interval(
            statistics, coverage=BOOTSTRAP_COVERAGE
        )
    except ResamplingError as error:
        return _unavailable(f"resampling_error:{error}")
    return {
        "available": True,
        "coverage": BOOTSTRAP_COVERAGE,
        "resample_count": BOOTSTRAP_COUNT_MVP,
        "usable_replicate_count": len(statistics),
        "refused_replicate_count": refused,
        "seed": BOOTSTRAP_SEED,
        "hierarchy": list(GROUPING_HIERARCHY),
        "r2_ci_low": low,
        "r2_ci_high": high,
    }


def _grouped_permutation(rows: Sequence[ScoredRow]) -> dict[str, Any]:
    """Whole-trajectory-block permutation of predictions against truth.

    Uses Person B's frozen unit, count, seed, and add-one p-value rule.
    ``permute_trajectory_blocks`` requires at least two trajectories per
    block-length stratum; when the admitted row universe does not satisfy
    that, the refusal is reported verbatim rather than worked around with
    a different resampling unit.
    """

    if len(rows) < 2:
        return _unavailable("fewer than two scored rows")
    trajectory_ids = [row.trajectory_id for row in rows]
    predictions = [row.prediction for row in rows]
    truth = [row.truth for row in rows]
    try:
        observed = regression_metrics(truth, predictions).r2
    except U1MetricError as error:
        return _unavailable(f"u1_metric_error:{error}")

    null_statistics: list[float] = []
    for offset in range(PERMUTATION_COUNT_MVP):
        try:
            permuted = permute_trajectory_blocks(
                trajectory_ids, predictions, seed=PERMUTATION_SEED + offset
            )
        except ResamplingError as error:
            return {
                **_unavailable(f"resampling_error:{error}"),
                "permutation_unit": PERMUTATION_UNIT,
                "requested_permutation_count": PERMUTATION_COUNT_MVP,
                "observed_r2": observed,
            }
        try:
            null_statistics.append(regression_metrics(truth, permuted).r2)
        except U1MetricError:
            continue
    if not null_statistics:
        return _unavailable("no usable permutation replicate")
    return {
        "available": True,
        "permutation_unit": PERMUTATION_UNIT,
        "permutation_count": len(null_statistics),
        "seed": PERMUTATION_SEED,
        "p_value_rule": PERMUTATION_P_VALUE_RULE,
        "observed_r2": observed,
        "p_value": permutation_p_value(observed, null_statistics),
    }


def _partial_correlation_block(rows: Sequence[ScoredRow]) -> dict[str, Any]:
    """Partial correlation of decoded vs oracle spread, controlling tau."""

    if len(rows) < 3:
        return _unavailable("fewer than three scored rows")
    try:
        value = partial_correlation_controlling_tau(
            [row.prediction for row in rows],
            [row.truth for row in rows],
            [row.tau_seconds for row in rows],
        )
    except U2MetricError as error:
        return _unavailable(f"u2_metric_error:{error}")
    return {
        "available": True,
        "sample_count": len(rows),
        "control": "tau",
        "partial_correlation": value,
    }


def build_scored_rows(
    prediction_rows: Sequence[BaselineRow],
    *,
    target_name: str,
    truth_by_key: Mapping[RowKey, float],
    tau_by_key: Mapping[RowKey, float],
    control_type_by_key: Mapping[RowKey, str],
) -> tuple[list[ScoredRow], dict[str, int]]:
    """Pair applicable predictions with oracle truth on identical rows.

    Returns the scored rows plus an accounting of everything that was not
    scored, so a shrinking denominator can never pass unnoticed.
    """

    scored: list[ScoredRow] = []
    accounting = {
        "emitted_rows": 0,
        "applicable_rows": 0,
        "non_applicable_rows": 0,
        "scored_rows": 0,
        "applicable_without_truth": 0,
    }
    for row in prediction_rows:
        if row.target_name != target_name:
            continue
        accounting["emitted_rows"] += 1
        key = (row.trajectory_id, row.model_frame_idx)
        if not row.applicable:
            accounting["non_applicable_rows"] += 1
            continue
        accounting["applicable_rows"] += 1
        truth = truth_by_key.get(key)
        if truth is None:
            accounting["applicable_without_truth"] += 1
            continue
        scored.append(
            ScoredRow(
                trajectory_id=row.trajectory_id,
                layout_id=row.layout_id,
                model_frame_idx=row.model_frame_idx,
                fold_idx=row.fold,
                control_type=control_type_by_key.get(key, "unknown"),
                prediction=float(row.prediction),
                truth=float(truth),
                tau_seconds=float(tau_by_key.get(key, row.tau_seconds)),
            )
        )
    accounting["scored_rows"] = len(scored)
    return scored, accounting


def build_family_target_metrics(
    *,
    family_id: str,
    target_name: str,
    scored: Sequence[ScoredRow],
    accounting: Mapping[str, int],
) -> dict[str, Any]:
    """Aggregate and per-fold metrics for one (family, target) pair."""

    by_fold: dict[int, list[ScoredRow]] = {}
    for row in scored:
        by_fold.setdefault(row.fold_idx, []).append(row)

    fold_results = []
    for fold_idx in sorted(by_fold):
        fold_rows = by_fold[fold_idx]
        fold_results.append(
            {
                "fold_idx": fold_idx,
                "scored_row_count": len(fold_rows),
                "trajectory_count": len({r.trajectory_id for r in fold_rows}),
                "layout_count": len({r.layout_id for r in fold_rows}),
                "regression": _regression_block(
                    [r.truth for r in fold_rows], [r.prediction for r in fold_rows]
                ),
            }
        )

    aggregate: dict[str, Any] = {
        "scored_row_count": len(scored),
        "trajectory_count": len({r.trajectory_id for r in scored}),
        "layout_count": len({r.layout_id for r in scored}),
        "regression": _regression_block(
            [r.truth for r in scored], [r.prediction for r in scored]
        ),
        "bootstrap_r2": _bootstrap_r2_interval(scored),
        "grouped_permutation": _grouped_permutation(scored),
    }
    if target_name == U2_TARGET:
        aggregate["partial_correlation_controlling_tau"] = _partial_correlation_block(
            scored
        )
        aggregate["coverage_and_ece"] = _unavailable(
            "this family defines no mean prediction; central-Gaussian coverage, "
            "ECE, and z-diagnostics require a paired mean and spread on the same "
            "rows, and no frozen Person D baseline pairs a spread family with a "
            "mean family"
        )

    return {
        "family_id": family_id,
        "comparison_class": COMPARISON_CLASS_BY_FAMILY[family_id],
        "target_name": target_name,
        "row_accounting": dict(accounting),
        "aggregate": aggregate,
        "per_fold": fold_results,
    }


def build_floor_comparison(
    *,
    family_id: str,
    target_name: str,
    family_scored: Sequence[ScoredRow],
    floor_scored: Sequence[ScoredRow],
) -> dict[str, Any]:
    """Delta R-squared against the chance floor on the exact row intersection.

    Person B's ``baseline_comparison`` compares a *probe* to these
    baselines and cannot run until a probe exists. This is the Person
    D-owned comparison that can run now, and it is labeled as such so it
    is never mistaken for the probe comparison.
    """

    family_by_key = {(r.trajectory_id, r.model_frame_idx): r for r in family_scored}
    floor_by_key = {(r.trajectory_id, r.model_frame_idx): r for r in floor_scored}
    shared = sorted(set(family_by_key) & set(floor_by_key))
    result: dict[str, Any] = {
        "family_id": family_id,
        "floor_family_id": CHANCE_FLOOR_FAMILY,
        "target_name": target_name,
        "comparison_kind": "person_d_baseline_versus_chance_floor",
        "is_probe_comparison": False,
        "family_scored_row_count": len(family_scored),
        "floor_scored_row_count": len(floor_scored),
        "intersection_row_count": len(shared),
        "family_rows_not_in_floor": len(set(family_by_key) - set(floor_by_key)),
        "floor_rows_not_in_family": len(set(floor_by_key) - set(family_by_key)),
    }
    if not shared:
        result["delta_r2"] = _unavailable("no shared scored rows with the floor")
        return result

    truth = [family_by_key[key].truth for key in shared]
    floor_truth = [floor_by_key[key].truth for key in shared]
    if truth != floor_truth:
        result["delta_r2"] = _unavailable(
            "family and floor disagree on oracle truth for a shared row"
        )
        return result
    try:
        family_r2 = regression_metrics(
            truth, [family_by_key[key].prediction for key in shared]
        ).r2
        floor_r2 = regression_metrics(
            truth, [floor_by_key[key].prediction for key in shared]
        ).r2
    except U1MetricError as error:
        result["delta_r2"] = _unavailable(f"u1_metric_error:{error}")
        return result
    result["delta_r2"] = {
        "available": True,
        "family_r2": family_r2,
        "floor_r2": floor_r2,
        "delta_r2": family_r2 - floor_r2,
        "sample_count": len(shared),
    }
    return result


def build_metric_package(
    *,
    run_id: str,
    family_metrics: Sequence[Mapping[str, Any]],
    floor_comparisons: Sequence[Mapping[str, Any]],
    source_identities: Mapping[str, Any],
    evidence_kind: str = "real",
) -> dict[str, Any]:
    """Assemble the deterministic metric package document."""

    if evidence_kind not in ("real", "synthetic"):
        raise BaselineMetricsError("evidence_kind must be 'real' or 'synthetic'")

    fold_result_count = sum(len(entry["per_fold"]) for entry in family_metrics)

    return {
        "schema_id": SCHEMA_ID,
        "schema_version": SCHEMA_VERSION,
        "producer_role": "person_d",
        "run_id": run_id,
        "evidence_kind": evidence_kind,
        "metric_authority": {
            "owner_role": "person_b",
            "u1_implementation": "mineocclude.metrics.u1_mean.regression_metrics",
            "u2_implementation": (
                "mineocclude.metrics.u2_calibration."
                "partial_correlation_controlling_tau"
            ),
            "resampling_implementation": "mineocclude.metrics.resampling",
            "analysis_arithmetic_dtype": ANALYSIS_ARITHMETIC_DTYPE,
            "analysis_config_version": ANALYSIS_CONFIG_VERSION,
            "grouping_hierarchy": list(GROUPING_HIERARCHY),
            "coverage_levels": list(COVERAGE_LEVELS),
            "nonfinite_policy": NONFINITE_POLICY,
            "near_zero_sigma_threshold_blocks": NEAR_ZERO_SIGMA_THRESHOLD_BLOCKS,
            "bootstrap_count": BOOTSTRAP_COUNT_MVP,
            "bootstrap_seed": BOOTSTRAP_SEED,
            "permutation_count": PERMUTATION_COUNT_MVP,
            "permutation_seed": PERMUTATION_SEED,
            "permutation_unit": PERMUTATION_UNIT,
            "permutation_p_value_rule": PERMUTATION_P_VALUE_RULE,
            "person_d_created_no_threshold": True,
            "person_d_applied_no_threshold": True,
        },
        "source_identities": dict(sorted(source_identities.items())),
        "targets": {"u1": U1_TARGET, "u2": U2_TARGET},
        "family_metric_count": len(family_metrics),
        "fold_result_count": fold_result_count,
        "aggregate_result_count": len(family_metrics),
        "floor_comparison_count": len(floor_comparisons),
        "family_metrics": list(family_metrics),
        "floor_comparisons": list(floor_comparisons),
        "not_computed": [
            {
                "metric": "baseline_comparison (probe versus baseline)",
                "owner": "person_b",
                "reason": (
                    "No probe exists until Person A publishes the 66-cell "
                    "activation index and Person B fits the probe against it."
                ),
            },
            {
                "metric": "coverage / expected_calibration_error / z_diagnostics",
                "owner": "person_b",
                "reason": (
                    "calibration_metrics requires a paired mean and spread on "
                    "the same rows. Every Person D spread family defines no "
                    "mean prediction, and pairing one with a mean family would "
                    "create a method Person D has not frozen."
                ),
            },
            {
                "metric": "u3 reveal_snapback",
                "owner": "person_b",
                "reason": (
                    "Requires terminal reveal events; the 66-cell dataset has "
                    "VALID_TERMINAL_REVEAL_COUNT = 0 and supplemental capture "
                    "is required."
                ),
            },
        ],
    }


__all__ = [
    "ANALYSIS_ARITHMETIC_DTYPE",
    "BOOTSTRAP_COUNT_MVP",
    "BOOTSTRAP_SEED",
    "CHANCE_FLOOR_FAMILY",
    "COMPARISON_CLASS_BY_FAMILY",
    "COVERAGE_LEVELS",
    "GROUPING_HIERARCHY",
    "NONFINITE_POLICY",
    "PERMUTATION_COUNT_MVP",
    "PERMUTATION_SEED",
    "PERMUTATION_UNIT",
    "SCHEMA_ID",
    "SCHEMA_VERSION",
    "U1_TARGET",
    "U2_TARGET",
    "BaselineMetricsError",
    "ScoredRow",
    "build_family_target_metrics",
    "build_floor_comparison",
    "build_metric_package",
    "build_scored_rows",
]
