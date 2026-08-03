"""Exact Step 4.1 final-comparison implementation.

The scientific choices in this module are data copied from the frozen contract
at ``4da02023`` and its ratification at ``d2a82a09``.  Runtime code may supply
data, but it cannot supply methods, thresholds, layers, tests, or metrics.
"""

from __future__ import annotations

import math
import random
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from mineocclude.analysis.step4_1_final_contract_v0_1 import (
    HOOK_SITE,
    LAYERS,
    FinalComparisonContractError,
    build_final_comparison_contract,
    qualifying_layer_bands,
    validate_final_comparison_contract,
)
from mineocclude.metrics.resampling import bootstrap_confidence_interval
from mineocclude.metrics.u2_calibration import (
    calibration_metrics,
    partial_correlation_controlling_tau,
    reconstruct_sigma,
)
from mineocclude.metrics.u3_dynamics import (
    oracle_slope_ratio,
    trajectory_growth_slopes,
)

COMPARISON_CONTRACT_COMMIT = "4da02023a376df77eacb48084b1406ec1accfcb1"
BOUNDED_REVEAL_CONTRACT_COMMIT = "53c2cd287a63e18e9b1fa5565b77f5c476baf9c4"
E_BOUNDED_REVEAL_AUTHORIZATION_COMMIT = (
    "99fb896ed8e6a3b187272fe078706bc7b17666d8"
)
E_COMPARISON_RATIFICATION_COMMIT = "d2a82a09b2f0acf73c9c7d95c1ea2e382a6cc4f7"
PERSON_D_COMPLETION_COMMIT = "f89b142a6fdb52c2d238669af8df14061cee5896"
PERSON_D_COMPLETION_SHA256 = (
    "79c49e7c794f37c4a574dfef365b8183ddb443b246adbe94743dfdf1ff1f4cf5"
)
PERSON_B_PREDICTIONS_SHA256 = (
    "01e792c4d7b58bbe4ae478195b1d9523802db5674ee06ebbf5364482f42061ba"
)
BOUNDED_REVEAL_PREDICTION_COUNT = 100
BOUNDED_REVEAL_PREDICTIONS_SHA256 = (
    "b7716ba00b1e45b20dab130965d03bba8947a87999be51e89404fad4982d288d"
)

PERMUTATION_COUNT = 999
PERMUTATION_SEED = 20260720
BOOTSTRAP_COUNT = 2000
BOOTSTRAP_SEED = 20260721
BOOTSTRAP_COVERAGE = 0.95
COVERAGE_LEVELS = (0.5, 0.8, 0.95)
LAYOUT_IDS = tuple(f"layout_{index:02d}" for index in range(5))
TARGETS = ("mu_oracle_blocks", "log_sigma_oracle")
PRIMARY_U1_BASELINES = ("last_seen", "grouped_shuffled")
PRIMARY_U2_BASELINES = ("time_only", "visible_history_q")
MU_BASELINES = (
    "last_seen",
    "constant_velocity",
    "grouped_shuffled",
    "explicit_feature",
    "raw_pixel",
)
LOG_SIGMA_BASELINES = (
    "grouped_shuffled",
    "time_only",
    "visible_history_q",
    "known_q_analytic",
)

FINAL_OUTPUT_FILENAMES = (
    "comparison_metric_table.json",
    "paired_test_results.json",
    "confidence_intervals.json",
    "layer_band_decision.json",
    "registry_v2_import_package.json",
    "execution_receipt.json",
    "sha256_inventory.json",
)


class FinalComparisonExecutionError(RuntimeError):
    """Raised when exact execution cannot continue without changing the contract."""


@dataclass(frozen=True)
class ComparisonDataset:
    """Validated normalized inputs consumed by the frozen metric implementation."""

    oracle_rows: tuple[Mapping[str, Any], ...]
    probe_rows: tuple[Mapping[str, Any], ...]
    baseline_rows: Mapping[tuple[str, str], tuple[Mapping[str, Any], ...]]
    post_reveal_rows: tuple[Mapping[str, Any], ...]
    direct_input_sha256s: Mapping[str, str]
    positive_control_valid: bool


def frozen_method_configuration() -> dict[str, Any]:
    """Return the only accepted runtime method configuration."""

    contract = build_final_comparison_contract()
    return {
        "acceptance_contract": contract["acceptance_contract"],
        "aggregation_contract": contract["aggregation_contract"],
        "confidence_interval_contract": contract["confidence_interval_contract"],
        "control_contract": contract["control_contract"],
        "layer_contract": contract["layer_contract"],
        "metric_contract": contract["metric_contract"],
        "multiplicity_contract": contract["multiplicity_contract"],
    }


def validate_method_configuration(document: Any) -> None:
    """Reject every post-hoc or exploratory method substitution."""

    if document != frozen_method_configuration():
        raise FinalComparisonExecutionError(
            "Runtime method configuration differs from the ratified contract."
        )


def validate_frozen_contract(document: Any) -> None:
    """Validate the exact contract and every execution-sensitive constant."""

    try:
        validate_final_comparison_contract(document)
    except FinalComparisonContractError as error:
        raise FinalComparisonExecutionError(str(error)) from error
    checks = {
        "layers": document["layer_contract"]["layer_indices"] == list(LAYERS),
        "hook": document["layer_contract"]["hook_site"] == HOOK_SITE,
        "selection": document["layer_contract"]["selection_mode"]
        == "none_all_layers_fixed_before_runtime",
        "permutations": document["multiplicity_contract"]["permutation_count"]
        == PERMUTATION_COUNT,
        "permutation_seed": document["multiplicity_contract"]["seed"]
        == PERMUTATION_SEED,
        "bootstrap": document["confidence_interval_contract"]["bootstrap_count"]
        == BOOTSTRAP_COUNT,
        "bootstrap_seed": document["confidence_interval_contract"]["seed"]
        == BOOTSTRAP_SEED,
        "coverage": document["confidence_interval_contract"]["coverage"]
        == BOOTSTRAP_COVERAGE,
        "targets": document["scope"]["targets"] == list(TARGETS),
    }
    failed = [name for name, accepted in checks.items() if not accepted]
    if failed:
        raise FinalComparisonExecutionError(
            f"Frozen method constants differ: {', '.join(failed)}."
        )


def _finite(value: Any, *, label: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
    ):
        raise FinalComparisonExecutionError(f"{label} must be finite numeric data.")
    return float(value)


def _identity(row: Mapping[str, Any]) -> tuple[str, int, int, str]:
    trajectory = row.get("trajectory_id")
    frame = row.get("model_frame_idx")
    fold = row.get("fold_idx")
    target = row.get("target_name")
    if (
        not isinstance(trajectory, str)
        or not trajectory
        or not isinstance(frame, int)
        or isinstance(frame, bool)
        or frame < 0
        or not isinstance(fold, int)
        or isinstance(fold, bool)
        or fold not in range(5)
        or target not in TARGETS
    ):
        raise FinalComparisonExecutionError("A scientific row identity is malformed.")
    return trajectory, frame, fold, target


def _index_unique(
    rows: Sequence[Mapping[str, Any]],
    *,
    keys: Sequence[str],
    label: str,
) -> dict[tuple[Any, ...], Mapping[str, Any]]:
    result: dict[tuple[Any, ...], Mapping[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            raise FinalComparisonExecutionError(f"{label} contains a non-object row.")
        key = tuple(row.get(field) for field in keys)
        if None in key or key in result:
            raise FinalComparisonExecutionError(
                f"{label} has a missing or duplicate identity {key!r}."
            )
        result[key] = row
    return result


def _layout_macro_values(
    rows: Sequence[Mapping[str, Any]],
    *,
    value_field: str,
) -> dict[str, float]:
    """Apply equal layout -> trajectory -> row weighting to an additive value."""

    grouped: dict[str, dict[str, list[float]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for row in rows:
        layout = row.get("layout_id")
        trajectory = row.get("trajectory_id")
        if not isinstance(layout, str) or layout not in LAYOUT_IDS:
            raise FinalComparisonExecutionError("A macro row has an unknown layout.")
        if not isinstance(trajectory, str) or not trajectory:
            raise FinalComparisonExecutionError("A macro row lacks trajectory_id.")
        grouped[layout][trajectory].append(
            _finite(row.get(value_field), label=value_field)
        )
    if len(grouped) < 2:
        raise FinalComparisonExecutionError(
            "A required statistic has fewer than two independent layouts."
        )
    return {
        layout: sum(
            sum(values) / len(values) for values in trajectories.values()
        )
        / len(trajectories)
        for layout, trajectories in sorted(grouped.items())
    }


def _mean(values: Sequence[float]) -> float:
    if not values:
        raise FinalComparisonExecutionError("A required statistic is empty.")
    return sum(values) / len(values)


def _median(values: Sequence[float]) -> float:
    if not values:
        raise FinalComparisonExecutionError("A required median is empty.")
    ordered = sorted(values)
    midpoint = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[midpoint]
    return (ordered[midpoint - 1] + ordered[midpoint]) / 2.0


def _studentized(values: Sequence[float]) -> float:
    if len(values) < 2:
        raise FinalComparisonExecutionError(
            "A studentized statistic needs at least two layouts."
        )
    mean = _mean(values)
    variance = sum((value - mean) ** 2 for value in values) / (len(values) - 1)
    if variance == 0.0:
        raise FinalComparisonExecutionError(
            "A required studentized statistic is degenerate."
        )
    return mean / math.sqrt(variance / len(values))


def shared_sign_flip_max_t(
    hypotheses: Mapping[str, Mapping[str, float]],
) -> dict[str, dict[str, float]]:
    """Run the exact one-sided, add-one, shared-layout, single-step maxT test."""

    if not hypotheses:
        raise FinalComparisonExecutionError("A maxT family cannot be empty.")
    layouts = sorted(
        {layout for layout_values in hypotheses.values() for layout in layout_values}
    )
    if len(layouts) < 2:
        raise FinalComparisonExecutionError("maxT requires at least two layouts.")
    observed = {
        name: _studentized([float(values[key]) for key in sorted(values)])
        for name, values in sorted(hypotheses.items())
    }
    null_by_hypothesis = {name: [] for name in observed}
    maxima: list[float] = []
    rng = random.Random(PERMUTATION_SEED)
    for _ in range(PERMUTATION_COUNT):
        signs = {layout: rng.choice((-1.0, 1.0)) for layout in layouts}
        replicate: dict[str, float] = {}
        for name, values in sorted(hypotheses.items()):
            replicate[name] = _studentized(
                [float(values[key]) * signs[key] for key in sorted(values)]
            )
            null_by_hypothesis[name].append(replicate[name])
        maxima.append(max(replicate.values()))
    result = {}
    for name, statistic in observed.items():
        raw_extreme = sum(value >= statistic for value in null_by_hypothesis[name])
        adjusted_extreme = sum(value >= statistic for value in maxima)
        result[name] = {
            "observed_statistic": statistic,
            "raw_p_value": (raw_extreme + 1.0) / (PERMUTATION_COUNT + 1.0),
            "max_t_adjusted_p_value": (adjusted_extreme + 1.0)
            / (PERMUTATION_COUNT + 1.0),
        }
    return result


def hierarchical_layout_confidence_interval(
    layout_values: Mapping[str, float],
    *,
    statistic: str = "mean",
) -> tuple[float, float]:
    """Apply the frozen hierarchy for the one-trajectory-per-layout core set."""

    if set(layout_values) != set(LAYOUT_IDS):
        raise FinalComparisonExecutionError(
            "Final hierarchical intervals require the exact five core layouts."
        )
    ordered = [float(layout_values[layout]) for layout in LAYOUT_IDS]
    if any(not math.isfinite(value) for value in ordered):
        raise FinalComparisonExecutionError("Bootstrap inputs must be finite.")
    reducer = _mean if statistic == "mean" else _median if statistic == "median" else None
    if reducer is None:
        raise FinalComparisonExecutionError("Unknown frozen bootstrap statistic.")
    rng = random.Random(BOOTSTRAP_SEED)
    replicates = [
        reducer(rng.choices(ordered, k=len(ordered)))
        for _ in range(BOOTSTRAP_COUNT)
    ]
    return bootstrap_confidence_interval(replicates, coverage=BOOTSTRAP_COVERAGE)


def _metric_record(
    *,
    metric_id: str,
    objective: str,
    target: str,
    layer: int,
    baseline: str | None,
    value: float,
    unit: str,
    sample_count: int,
    sample_unit: str,
    direct_input_sha256s: Mapping[str, str],
    diagnostic: str | None = None,
) -> dict[str, Any]:
    return {
        "baseline_family": baseline,
        "diagnostic": diagnostic,
        "direct_input_sha256s": dict(sorted(direct_input_sha256s.items())),
        "hook_site": HOOK_SITE,
        "layer_idx": layer,
        "metric_id": metric_id,
        "objective": objective,
        "sample_count": sample_count,
        "sample_unit": sample_unit,
        "status": "valid",
        "target_name": target,
        "unit": unit,
        "value": _finite(value, label=metric_id),
    }


def _oracle_index(dataset: ComparisonDataset) -> dict[tuple[str, int], Mapping[str, Any]]:
    return _index_unique(
        dataset.oracle_rows,
        keys=("trajectory_id", "model_frame_idx"),
        label="oracle targets",
    )


def _probe_index(
    dataset: ComparisonDataset,
) -> dict[tuple[str, int, int, str, str], Mapping[str, Any]]:
    return _index_unique(
        dataset.probe_rows,
        keys=(
            "trajectory_id",
            "model_frame_idx",
            "layer_idx",
            "hook_site",
            "target_name",
        ),
        label="probe predictions",
    )


def _baseline_index(
    rows: Sequence[Mapping[str, Any]], *, family: str, target: str
) -> dict[tuple[str, int], Mapping[str, Any]]:
    return _index_unique(
        rows,
        keys=("trajectory_id", "model_frame_idx"),
        label=f"{family}/{target} baseline",
    )


def _paired_loss_rows(
    *,
    layer: int,
    target: str,
    family: str,
    oracle: Mapping[tuple[str, int], Mapping[str, Any]],
    probes: Mapping[tuple[str, int, int, str, str], Mapping[str, Any]],
    baselines: Mapping[tuple[str, int], Mapping[str, Any]],
) -> list[dict[str, Any]]:
    probe_keys = {
        (trajectory, frame)
        for trajectory, frame, row_layer, hook, row_target in probes
        if row_layer == layer and hook == HOOK_SITE and row_target == target
    }
    keys = sorted(probe_keys & set(baselines) & set(oracle))
    if not keys:
        raise FinalComparisonExecutionError(
            f"No applicability-aware intersection for {layer}/{target}/{family}."
        )
    rows = []
    for trajectory, frame in keys:
        probe = probes[(trajectory, frame, layer, HOOK_SITE, target)]
        baseline = baselines[(trajectory, frame)]
        truth = _finite(oracle[(trajectory, frame)][target], label=target)
        probe_prediction = _finite(probe.get("prediction"), label="probe prediction")
        baseline_prediction = _finite(
            baseline.get("prediction"), label="baseline prediction"
        )
        if probe.get("fold_idx") != baseline.get("fold_idx") or probe.get(
            "fold_idx"
        ) != oracle[(trajectory, frame)].get("fold_idx"):
            raise FinalComparisonExecutionError("A paired row has a fold mismatch.")
        rows.append(
            {
                "improvement": (baseline_prediction - truth) ** 2
                - (probe_prediction - truth) ** 2,
                "layout_id": oracle[(trajectory, frame)]["layout_id"],
                "trajectory_id": trajectory,
            }
        )
    return rows


def _layer_probe_rows(
    dataset: ComparisonDataset,
    *,
    layer: int,
    target: str,
) -> list[Mapping[str, Any]]:
    rows = [
        row
        for row in dataset.probe_rows
        if row.get("layer_idx") == layer
        and row.get("hook_site") == HOOK_SITE
        and row.get("target_name") == target
    ]
    if len(rows) != 695:
        raise FinalComparisonExecutionError(
            f"Layer {layer}/{target} must contain exactly 695 OOF rows."
        )
    return sorted(rows, key=lambda row: (row["trajectory_id"], row["model_frame_idx"]))


def _u1_layer_metrics(
    dataset: ComparisonDataset,
    *,
    layer: int,
    oracle: Mapping[tuple[str, int], Mapping[str, Any]],
    probes: Mapping[tuple[str, int, int, str, str], Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Mapping[str, float]], float]:
    rows = _layer_probe_rows(dataset, layer=layer, target="mu_oracle_blocks")
    by_trajectory: dict[str, list[tuple[float, float]]] = defaultdict(list)
    additive = []
    for row in rows:
        key = (row["trajectory_id"], row["model_frame_idx"])
        truth = _finite(oracle[key]["mu_oracle_blocks"], label="mu truth")
        prediction = _finite(row["prediction"], label="mu prediction")
        by_trajectory[row["trajectory_id"]].append((truth, prediction))
        additive.append(
            {
                "absolute_error": abs(truth - prediction),
                "layout_id": oracle[key]["layout_id"],
                "trajectory_id": row["trajectory_id"],
            }
        )
    r2_by_layout: dict[str, float] = {}
    for trajectory, pairs in sorted(by_trajectory.items()):
        truths = [pair[0] for pair in pairs]
        mean_truth = _mean(truths)
        denominator = sum((value - mean_truth) ** 2 for value in truths)
        if denominator == 0.0:
            raise FinalComparisonExecutionError("U1 R2 is degenerate.")
        layout = oracle[(trajectory, rows_by_trajectory_frame(rows, trajectory))][
            "layout_id"
        ]
        r2_by_layout[layout] = 1.0 - sum(
            (truth - prediction) ** 2 for truth, prediction in pairs
        ) / denominator
    r2 = _mean(list(r2_by_layout.values()))
    mae = _mean(list(_layout_macro_values(additive, value_field="absolute_error").values()))
    records = [
        _metric_record(
            metric_id=f"u1_r2:layer_{layer:02d}",
            objective="U1",
            target="mu_oracle_blocks",
            layer=layer,
            baseline=None,
            value=r2,
            unit="dimensionless",
            sample_count=len(rows),
            sample_unit="layout_macro_oof_frame",
            direct_input_sha256s=dataset.direct_input_sha256s,
        ),
        _metric_record(
            metric_id=f"u1_mae_blocks:layer_{layer:02d}",
            objective="U1",
            target="mu_oracle_blocks",
            layer=layer,
            baseline=None,
            value=mae,
            unit="blocks",
            sample_count=len(rows),
            sample_unit="layout_macro_oof_frame",
            direct_input_sha256s=dataset.direct_input_sha256s,
        ),
    ]
    hypotheses: dict[str, Mapping[str, float]] = {}
    for family in MU_BASELINES:
        baseline = _baseline_index(
            dataset.baseline_rows[(family, "mu_oracle_blocks")],
            family=family,
            target="mu_oracle_blocks",
        )
        paired = _paired_loss_rows(
            layer=layer,
            target="mu_oracle_blocks",
            family=family,
            oracle=oracle,
            probes=probes,
            baselines=baseline,
        )
        layout_values = _layout_macro_values(paired, value_field="improvement")
        value = _mean(list(layout_values.values()))
        records.append(
            _metric_record(
                metric_id=(
                    f"u1_paired_loss_improvement:{family}:layer_{layer:02d}"
                ),
                objective="U1",
                target="mu_oracle_blocks",
                layer=layer,
                baseline=family,
                value=value,
                unit="squared_blocks",
                sample_count=len(paired),
                sample_unit="layout_macro_paired_oof_frame",
                direct_input_sha256s=dataset.direct_input_sha256s,
            )
        )
        if family in PRIMARY_U1_BASELINES:
            hypotheses[f"u1:{family}:layer_{layer:02d}"] = layout_values
    return records, hypotheses, r2


def rows_by_trajectory_frame(
    rows: Sequence[Mapping[str, Any]], trajectory_id: str
) -> int:
    """Return one known frame for looking up trajectory-level oracle metadata."""

    for row in rows:
        if row["trajectory_id"] == trajectory_id:
            return int(row["model_frame_idx"])
    raise FinalComparisonExecutionError("Trajectory metadata lookup failed.")


def _layout_partial_correlations(rows: Sequence[Mapping[str, Any]]) -> dict[str, float]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["layout_id"])].append(row)
    if set(grouped) != set(LAYOUT_IDS):
        raise FinalComparisonExecutionError("U2 must cover all five core layouts.")
    return {
        layout: partial_correlation_controlling_tau(
            [float(row["decoded_sigma"]) for row in values],
            [float(row["oracle_sigma"]) for row in values],
            [float(row["tau"]) for row in values],
        )
        for layout, values in sorted(grouped.items())
    }


def _coverage_summary(rows: Sequence[Mapping[str, Any]]) -> tuple[dict[str, float], list[float]]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["layout_id"])].append(row)
    if set(grouped) != set(LAYOUT_IDS):
        raise FinalComparisonExecutionError("Coverage must cover all five core layouts.")
    ece_by_layout: dict[str, float] = {}
    coverage_by_level: dict[float, list[float]] = defaultdict(list)
    for layout, values in sorted(grouped.items()):
        metrics = calibration_metrics(
            [float(row["truth_position"]) for row in values],
            [float(row["mean_prediction"]) for row in values],
            [float(row["sigma_prediction"]) for row in values],
            levels=COVERAGE_LEVELS,
        )
        ece_by_layout[layout] = metrics.expected_calibration_error
        for level, coverage in zip(
            metrics.nominal_levels, metrics.empirical_coverage, strict=True
        ):
            coverage_by_level[level].append(coverage)
    return ece_by_layout, [
        _mean(coverage_by_level[level]) for level in COVERAGE_LEVELS
    ]


def _u2_layer_metrics(
    dataset: ComparisonDataset,
    *,
    layer: int,
    oracle: Mapping[tuple[str, int], Mapping[str, Any]],
    probes: Mapping[tuple[str, int, int, str, str], Mapping[str, Any]],
) -> tuple[
    list[dict[str, Any]],
    dict[str, Mapping[str, float]],
    dict[str, float],
    float,
    dict[str, float],
]:
    spread_rows = _layer_probe_rows(dataset, layer=layer, target="log_sigma_oracle")
    normalized = []
    for spread in spread_rows:
        trajectory = spread["trajectory_id"]
        frame = spread["model_frame_idx"]
        key = (trajectory, frame)
        mean_row = probes.get(
            (trajectory, frame, layer, HOOK_SITE, "mu_oracle_blocks")
        )
        if mean_row is None:
            raise FinalComparisonExecutionError("U2 lacks its paired mean prediction.")
        target = oracle[key]
        decoded_sigma = reconstruct_sigma([float(spread["prediction"])])[0]
        oracle_sigma = reconstruct_sigma([float(target["log_sigma_oracle"])])[0]
        if not math.isfinite(decoded_sigma) or decoded_sigma <= 0.0:
            raise FinalComparisonExecutionError("Decoded spread is not finite positive.")
        normalized.append(
            {
                "decoded_sigma": decoded_sigma,
                "layout_id": target["layout_id"],
                "mean_prediction": float(mean_row["prediction"]),
                "model_frame_idx": frame,
                "oracle_sigma": oracle_sigma,
                "sigma_prediction": decoded_sigma,
                "tau": float(target["tau"]),
                "trajectory_id": trajectory,
                "truth_position": float(target["x_true_blocks"]),
            }
        )
    partial_by_layout = _layout_partial_correlations(normalized)
    partial = _mean(list(partial_by_layout.values()))
    ece_by_layout, coverages = _coverage_summary(normalized)
    ece = _mean(list(ece_by_layout.values()))
    records = [
        _metric_record(
            metric_id=f"u2_partial_correlation_controlling_tau:layer_{layer:02d}",
            objective="U2",
            target="log_sigma_oracle",
            layer=layer,
            baseline=None,
            value=partial,
            unit="dimensionless",
            sample_count=len(normalized),
            sample_unit="layout_macro_oof_frame",
            direct_input_sha256s=dataset.direct_input_sha256s,
        ),
        _metric_record(
            metric_id=f"u2_mean_absolute_coverage_error:layer_{layer:02d}",
            objective="U2",
            target="log_sigma_oracle",
            layer=layer,
            baseline=None,
            value=ece,
            unit="proportion",
            sample_count=len(normalized),
            sample_unit="layout_macro_oof_frame",
            direct_input_sha256s=dataset.direct_input_sha256s,
        ),
    ]
    for level, coverage in zip(COVERAGE_LEVELS, coverages, strict=True):
        records.append(
            _metric_record(
                metric_id=f"u2_coverage_{level}:layer_{layer:02d}",
                objective="U2",
                target="log_sigma_oracle",
                layer=layer,
                baseline=None,
                value=coverage,
                unit="proportion",
                sample_count=len(normalized),
                sample_unit="layout_macro_oof_frame",
                direct_input_sha256s=dataset.direct_input_sha256s,
                diagnostic=f"nominal={level}",
            )
        )
    z_values = [
        (row["truth_position"] - row["mean_prediction"]) / row["sigma_prediction"]
        for row in normalized
    ]
    z_mean = _mean(z_values)
    z_variance = sum((value - z_mean) ** 2 for value in z_values) / (
        len(z_values) - 1
    )
    for metric_name, value in (
        ("z_mean", z_mean),
        ("z_sample_std", math.sqrt(z_variance)),
        ("z_root_mean_square", math.sqrt(_mean([value * value for value in z_values]))),
        ("z_coverage_1_96", _mean([float(abs(value) <= 1.96) for value in z_values])),
    ):
        records.append(
            _metric_record(
                metric_id=f"u2_{metric_name}:layer_{layer:02d}",
                objective="U2",
                target="log_sigma_oracle",
                layer=layer,
                baseline=None,
                value=value,
                unit="dimensionless",
                sample_count=len(normalized),
                sample_unit="oof_frame_diagnostic",
                direct_input_sha256s=dataset.direct_input_sha256s,
            )
        )
    hypotheses: dict[str, Mapping[str, float]] = {}
    baseline_eces: dict[str, float] = {}
    for family in LOG_SIGMA_BASELINES:
        baseline_rows = dataset.baseline_rows[(family, "log_sigma_oracle")]
        baseline = _baseline_index(
            baseline_rows, family=family, target="log_sigma_oracle"
        )
        paired = _paired_loss_rows(
            layer=layer,
            target="log_sigma_oracle",
            family=family,
            oracle=oracle,
            probes=probes,
            baselines=baseline,
        )
        layout_values = _layout_macro_values(paired, value_field="improvement")
        records.append(
            _metric_record(
                metric_id=(
                    f"u2_paired_loss_improvement:{family}:layer_{layer:02d}"
                ),
                objective="U2",
                target="log_sigma_oracle",
                layer=layer,
                baseline=family,
                value=_mean(list(layout_values.values())),
                unit="squared_log_sigma",
                sample_count=len(paired),
                sample_unit="layout_macro_paired_oof_frame",
                direct_input_sha256s=dataset.direct_input_sha256s,
            )
        )
        if family in PRIMARY_U2_BASELINES:
            hypotheses[f"u2:{family}:layer_{layer:02d}"] = layout_values
            baseline_normalized = []
            for row in normalized:
                key = (row["trajectory_id"], row["model_frame_idx"])
                if key not in baseline:
                    raise FinalComparisonExecutionError(
                        "A U2 coverage-baseline row is missing."
                    )
                baseline_normalized.append(
                    {
                        **row,
                        "sigma_prediction": reconstruct_sigma(
                            [float(baseline[key]["prediction"])]
                        )[0],
                    }
                )
            baseline_ece_by_layout, _ = _coverage_summary(baseline_normalized)
            baseline_eces[family] = _mean(list(baseline_ece_by_layout.values()))
            records.append(
                _metric_record(
                    metric_id=(
                        f"u2_mean_absolute_coverage_error:{family}:"
                        f"layer_{layer:02d}"
                    ),
                    objective="U2",
                    target="log_sigma_oracle",
                    layer=layer,
                    baseline=family,
                    value=baseline_eces[family],
                    unit="proportion",
                    sample_count=len(baseline_normalized),
                    sample_unit="layout_macro_paired_oof_frame",
                    direct_input_sha256s=dataset.direct_input_sha256s,
                )
            )
    return records, hypotheses, partial_by_layout, ece, baseline_eces


def _u3_layer_metrics(
    dataset: ComparisonDataset,
    *,
    layer: int,
    oracle: Mapping[tuple[str, int], Mapping[str, Any]],
) -> tuple[
    list[dict[str, Any]],
    Mapping[str, float],
    dict[str, tuple[float, float]],
    dict[str, float],
]:
    rows = _layer_probe_rows(dataset, layer=layer, target="log_sigma_oracle")
    trajectory_ids = [str(row["trajectory_id"]) for row in rows]
    tau = [float(oracle[(row["trajectory_id"], row["model_frame_idx"])]["tau"]) for row in rows]
    decoded = reconstruct_sigma([float(row["prediction"]) for row in rows])
    oracle_sigma = reconstruct_sigma(
        [
            float(oracle[(row["trajectory_id"], row["model_frame_idx"])]["log_sigma_oracle"])
            for row in rows
        ]
    )
    visibility = ["occluded"] * len(rows)
    decoded_slopes = trajectory_growth_slopes(trajectory_ids, tau, decoded, visibility)
    oracle_slopes = trajectory_growth_slopes(
        trajectory_ids, tau, oracle_sigma, visibility
    )
    ratios = oracle_slope_ratio(decoded_slopes, oracle_slopes)
    layout_by_trajectory = {
        str(row["trajectory_id"]): str(
            oracle[(row["trajectory_id"], row["model_frame_idx"])]["layout_id"]
        )
        for row in rows
    }
    growth_by_layout = {
        layout_by_trajectory[trajectory]: value
        for trajectory, value in decoded_slopes.items()
    }
    ratio_by_layout = {
        layout_by_trajectory[trajectory]: value for trajectory, value in ratios.items()
    }
    post = _index_unique(
        [row for row in dataset.post_reveal_rows if row.get("layer_idx") == layer],
        keys=("event_id", "trajectory_id", "layer_idx", "hook_site"),
        label="post-reveal predictions",
    )
    contract_events = build_final_comparison_contract()["reveal_event_contract"]
    difference_by_layout: dict[str, float] = {}
    reduction_by_layout: dict[str, float] = {}
    for event in contract_events:
        pre_key = (
            event["trajectory_id"],
            event["pre_model_frame_idx"],
            layer,
            HOOK_SITE,
            "log_sigma_oracle",
        )
        pre_rows = [
            row
            for row in rows
            if (
                row["trajectory_id"],
                row["model_frame_idx"],
                row["layer_idx"],
                row["hook_site"],
                row["target_name"],
            )
            == pre_key
        ]
        post_row = post.get(
            (event["event_id"], event["trajectory_id"], layer, HOOK_SITE)
        )
        if len(pre_rows) != 1 or post_row is None:
            raise FinalComparisonExecutionError("A reveal pair is missing.")
        pre_sigma = reconstruct_sigma([float(pre_rows[0]["prediction"])])[0]
        post_sigma = reconstruct_sigma([float(post_row["prediction"])])[0]
        if pre_sigma <= 0.0 or not math.isfinite(post_sigma):
            raise FinalComparisonExecutionError("A reveal pair has invalid spread.")
        difference_by_layout[event["layout_id"]] = post_sigma - pre_sigma
        reduction_by_layout[event["layout_id"]] = (pre_sigma - post_sigma) / pre_sigma
    median_difference = _median(list(difference_by_layout.values()))
    median_reduction = _median(list(reduction_by_layout.values()))
    records = [
        _metric_record(
            metric_id=f"u3_trajectory_hidden_growth_slope:layer_{layer:02d}",
            objective="U3",
            target="log_sigma_oracle",
            layer=layer,
            baseline=None,
            value=_mean(list(growth_by_layout.values())),
            unit="blocks_per_second",
            sample_count=len(growth_by_layout),
            sample_unit="layout_macro_trajectory",
            direct_input_sha256s=dataset.direct_input_sha256s,
        ),
        _metric_record(
            metric_id=f"u3_decoded_oracle_slope_ratio:layer_{layer:02d}",
            objective="U3",
            target="log_sigma_oracle",
            layer=layer,
            baseline=None,
            value=_mean(list(ratio_by_layout.values())),
            unit="ratio",
            sample_count=len(ratio_by_layout),
            sample_unit="layout_macro_trajectory",
            direct_input_sha256s=dataset.direct_input_sha256s,
        ),
        _metric_record(
            metric_id=f"u3_reveal_difference:layer_{layer:02d}",
            objective="U3",
            target="log_sigma_oracle",
            layer=layer,
            baseline=None,
            value=median_difference,
            unit="blocks",
            sample_count=len(difference_by_layout),
            sample_unit="layout_reveal_event",
            direct_input_sha256s=dataset.direct_input_sha256s,
        ),
        _metric_record(
            metric_id=f"u3_median_reveal_reduction_fraction:layer_{layer:02d}",
            objective="U3",
            target="log_sigma_oracle",
            layer=layer,
            baseline=None,
            value=median_reduction,
            unit="proportion",
            sample_count=len(reduction_by_layout),
            sample_unit="layout_reveal_event",
            direct_input_sha256s=dataset.direct_input_sha256s,
        ),
    ]
    intervals = {
        "decoded_hidden_growth": hierarchical_layout_confidence_interval(
            growth_by_layout
        ),
        "oracle_slope_ratio": hierarchical_layout_confidence_interval(
            ratio_by_layout
        ),
        "reveal_difference": hierarchical_layout_confidence_interval(
            difference_by_layout, statistic="median"
        ),
        "reveal_reduction_fraction": hierarchical_layout_confidence_interval(
            reduction_by_layout, statistic="median"
        ),
    }
    reveal_improvement = {
        layout: -difference for layout, difference in difference_by_layout.items()
    }
    gates = {
        "growth": _mean(list(growth_by_layout.values())),
        "ratio": _mean(list(ratio_by_layout.values())),
        "reduction": median_reduction,
    }
    return records, reveal_improvement, intervals, gates


def _paired_test_records(
    objective: str,
    hypotheses: Mapping[str, Mapping[str, float]],
) -> tuple[list[dict[str, Any]], dict[str, dict[str, float]]]:
    results = shared_sign_flip_max_t(hypotheses)
    records = []
    for hypothesis_id, result in sorted(results.items()):
        records.append(
            {
                "hypothesis_id": hypothesis_id,
                "layout_count": len(hypotheses[hypothesis_id]),
                "max_t_adjusted_p_value": result["max_t_adjusted_p_value"],
                "null_hypothesis": (
                    "layout-macro paired improvement is less than or equal to zero"
                ),
                "objective_family": objective,
                "observed_statistic": result["observed_statistic"],
                "permutation_count": PERMUTATION_COUNT,
                "raw_p_value": result["raw_p_value"],
                "seed": PERMUTATION_SEED,
                "sidedness": "one_sided_in_predeclared_improvement_direction",
            }
        )
    return records, results


def build_output_documents(
    *,
    decision: str,
    metric_records: Sequence[Mapping[str, Any]],
    paired_test_records: Sequence[Mapping[str, Any]],
    confidence_interval_records: Sequence[Mapping[str, Any]],
    layer_gates: Mapping[int, Mapping[str, bool]],
    layer_bands: Sequence[Sequence[int]],
    direct_input_sha256s: Mapping[str, str],
    inconclusive_reasons: Sequence[str] = (),
) -> dict[str, dict[str, Any]]:
    """Build every non-receipt output with exact stable ordering and schemas."""

    if decision not in {"PASS", "FAIL", "INCONCLUSIVE"}:
        raise FinalComparisonExecutionError("Unknown final decision.")
    if any(not isinstance(value, str) or len(value) != 64 for value in direct_input_sha256s.values()):
        raise FinalComparisonExecutionError("Direct input hashes are malformed.")
    metrics = sorted(
        (dict(record) for record in metric_records),
        key=lambda row: (
            row.get("objective", ""),
            row.get("layer_idx", -1),
            row.get("metric_id", ""),
            row.get("baseline_family") or "",
        ),
    )
    tests = sorted(
        (dict(record) for record in paired_test_records),
        key=lambda row: (row.get("objective_family", ""), row.get("hypothesis_id", "")),
    )
    intervals = sorted(
        (dict(record) for record in confidence_interval_records),
        key=lambda row: (row.get("objective", ""), row.get("layer_idx", -1), row.get("metric_id", "")),
    )
    bands = [list(band) for band in layer_bands]
    table = {
        "decision": decision,
        "direct_input_sha256s": dict(sorted(direct_input_sha256s.items())),
        "layer_bands": bands,
        "metric_records": metrics,
        "paired_test_records": tests,
        "schema_id": "person-b-step4-1-final-comparison-output-v0-1",
        "schema_version": "1.0",
        "scientific_execution_performed": True,
        "u4_output_inspected": False,
    }
    paired = {
        "family_wise_sets": ["U1", "U2", "U3_reveal"],
        "records": tests,
        "schema_id": "person-b-step4-1-paired-test-results-v0-1",
        "schema_version": "1.0",
        "u4_output_inspected": False,
    }
    confidence = {
        "bootstrap_count": BOOTSTRAP_COUNT,
        "coverage": BOOTSTRAP_COVERAGE,
        "hierarchy": ["layout_id", "trajectory_id", "all_paired_rows"],
        "interval": "equal_tailed_percentile_linear_quantiles",
        "records": intervals,
        "schema_id": "person-b-step4-1-confidence-intervals-v0-1",
        "schema_version": "1.0",
        "seed": BOOTSTRAP_SEED,
        "u4_output_inspected": False,
    }
    band_decision = {
        "decision": decision,
        "decision_precedence": [
            "INCONCLUSIVE_integrity_or_control_gate",
            "PASS_all_scientific_gates",
            "FAIL_clean_scientific_miss",
        ],
        "inconclusive_reasons": list(inconclusive_reasons),
        "layer_gates": [
            {"layer_idx": layer, **dict(layer_gates[layer])}
            for layer in sorted(layer_gates)
        ],
        "minimum_contiguous_length": 2,
        "qualifying_layer_bands": bands,
        "schema_id": "person-b-step4-1-layer-band-decision-v0-1",
        "schema_version": "1.0",
        "u4_output_inspected": False,
    }
    return {
        "comparison_metric_table.json": table,
        "confidence_intervals.json": confidence,
        "layer_band_decision.json": band_decision,
        "paired_test_results.json": paired,
    }


def compute_final_comparison(dataset: ComparisonDataset) -> dict[str, dict[str, Any]]:
    """Compute only the frozen U1/U2/U3 comparison on already validated inputs."""

    if not dataset.positive_control_valid:
        raise FinalComparisonExecutionError("The frozen positive control is not valid.")
    oracle = _oracle_index(dataset)
    probes = _probe_index(dataset)
    metric_records: list[dict[str, Any]] = []
    interval_records: list[dict[str, Any]] = []
    u1_hypotheses: dict[str, Mapping[str, float]] = {}
    u2_hypotheses: dict[str, Mapping[str, float]] = {}
    u3_hypotheses: dict[str, Mapping[str, float]] = {}
    u1_r2: dict[int, float] = {}
    u2_values: dict[int, tuple[float, Mapping[str, float], tuple[float, float]]] = {}
    u3_values: dict[int, dict[str, float]] = {}
    u3_intervals: dict[int, Mapping[str, tuple[float, float]]] = {}
    for layer in LAYERS:
        records, hypotheses, r2 = _u1_layer_metrics(
            dataset, layer=layer, oracle=oracle, probes=probes
        )
        metric_records.extend(records)
        u1_hypotheses.update(hypotheses)
        u1_r2[layer] = r2
        records, hypotheses, partial_by_layout, ece, baseline_eces = _u2_layer_metrics(
            dataset, layer=layer, oracle=oracle, probes=probes
        )
        metric_records.extend(records)
        u2_hypotheses.update(hypotheses)
        partial_ci = hierarchical_layout_confidence_interval(partial_by_layout)
        u2_values[layer] = (ece, baseline_eces, partial_ci)
        interval_records.append(
            {
                "bootstrap_count": BOOTSTRAP_COUNT,
                "ci_lower": partial_ci[0],
                "ci_upper": partial_ci[1],
                "layer_idx": layer,
                "metric_id": "u2_partial_correlation_controlling_tau",
                "objective": "U2",
                "seed": BOOTSTRAP_SEED,
            }
        )
        records, reveal_hypothesis, intervals, gate_values = _u3_layer_metrics(
            dataset, layer=layer, oracle=oracle
        )
        metric_records.extend(records)
        u3_hypotheses[f"u3:reveal_decrease:layer_{layer:02d}"] = reveal_hypothesis
        u3_values[layer] = gate_values
        u3_intervals[layer] = intervals
        for metric_id, interval in sorted(intervals.items()):
            interval_records.append(
                {
                    "bootstrap_count": BOOTSTRAP_COUNT,
                    "ci_lower": interval[0],
                    "ci_upper": interval[1],
                    "layer_idx": layer,
                    "metric_id": f"u3_{metric_id}",
                    "objective": "U3",
                    "seed": BOOTSTRAP_SEED,
                }
            )
    paired_records = []
    records, u1_tests = _paired_test_records("U1", u1_hypotheses)
    paired_records.extend(records)
    records, _ = _paired_test_records("U2", u2_hypotheses)
    paired_records.extend(records)
    records, _ = _paired_test_records("U3_reveal", u3_hypotheses)
    paired_records.extend(records)
    layer_gates: dict[int, dict[str, bool]] = {}
    for layer in LAYERS:
        u1_green = u1_r2[layer] > 0.0 and all(
            _metric_value(
                metric_records,
                f"u1_paired_loss_improvement:{family}:layer_{layer:02d}",
            )
            > 0.0
            and u1_tests[f"u1:{family}:layer_{layer:02d}"][
                "max_t_adjusted_p_value"
            ]
            < 0.01
            for family in PRIMARY_U1_BASELINES
        )
        ece, baseline_eces, partial_ci = u2_values[layer]
        u2_green = (
            ece <= 0.10
            and all(ece < baseline_eces[family] for family in PRIMARY_U2_BASELINES)
            and partial_ci[0] > 0.0
        )
        u3 = u3_values[layer]
        u3_green = (
            u3["growth"] > 0.0
            and 0.5 <= u3["ratio"] <= 2.0
            and u3["reduction"] >= 0.25
            and u3_intervals[layer]["reveal_difference"][1] < 0.0
        )
        layer_gates[layer] = {
            "U1_green": u1_green,
            "U2_green": u2_green,
            "U3_green": u3_green,
            "qualifies": u1_green and u2_green and u3_green,
        }
    bands = qualifying_layer_bands(
        {layer: gates["qualifies"] for layer, gates in layer_gates.items()}
    )
    decision = "PASS" if bands else "FAIL"
    return build_output_documents(
        decision=decision,
        metric_records=metric_records,
        paired_test_records=paired_records,
        confidence_interval_records=interval_records,
        layer_gates=layer_gates,
        layer_bands=bands,
        direct_input_sha256s=dataset.direct_input_sha256s,
    )


def _metric_value(records: Sequence[Mapping[str, Any]], metric_id: str) -> float:
    matches = [record for record in records if record.get("metric_id") == metric_id]
    if len(matches) != 1:
        raise FinalComparisonExecutionError(f"Required metric {metric_id!r} is missing.")
    return _finite(matches[0].get("value"), label=metric_id)


def inconclusive_output_documents(
    *, direct_input_sha256s: Mapping[str, str], reason: str
) -> dict[str, dict[str, Any]]:
    """Emit a fail-closed scientific INCONCLUSIVE result for valid inputs."""

    empty_gates = {
        layer: {
            "U1_green": False,
            "U2_green": False,
            "U3_green": False,
            "qualifies": False,
        }
        for layer in LAYERS
    }
    return build_output_documents(
        decision="INCONCLUSIVE",
        metric_records=(),
        paired_test_records=(),
        confidence_interval_records=(),
        layer_gates=empty_gates,
        layer_bands=(),
        direct_input_sha256s=direct_input_sha256s,
        inconclusive_reasons=(reason,),
    )


def validate_output_documents(documents: Mapping[str, Any]) -> None:
    """Validate the exact non-receipt output schemas without recomputing metrics."""

    required = {
        "comparison_metric_table.json",
        "paired_test_results.json",
        "confidence_intervals.json",
        "layer_band_decision.json",
    }
    if set(documents) != required:
        raise FinalComparisonExecutionError("Output document set differs.")
    table = documents["comparison_metric_table.json"]
    if (
        not isinstance(table, Mapping)
        or table.get("schema_id")
        != "person-b-step4-1-final-comparison-output-v0-1"
        or table.get("schema_version") != "1.0"
        or table.get("decision") not in {"PASS", "FAIL", "INCONCLUSIVE"}
        or table.get("scientific_execution_performed") is not True
        or table.get("u4_output_inspected") is not False
    ):
        raise FinalComparisonExecutionError("Metric-table envelope differs.")
    required_metric_fields = set(
        build_final_comparison_contract()["output_schema_contract"][
            "metric_record_required_fields"
        ]
    )
    for row in table.get("metric_records", []):
        if not isinstance(row, Mapping) or not required_metric_fields <= set(row):
            raise FinalComparisonExecutionError("A metric record is incomplete.")
        _finite(row.get("value"), label="metric value")
    required_test_fields = set(
        build_final_comparison_contract()["output_schema_contract"][
            "paired_test_required_fields"
        ]
    )
    for row in table.get("paired_test_records", []):
        if not isinstance(row, Mapping) or not required_test_fields <= set(row):
            raise FinalComparisonExecutionError("A paired-test record is incomplete.")
        for field in (
            "observed_statistic",
            "raw_p_value",
            "max_t_adjusted_p_value",
        ):
            _finite(row.get(field), label=field)
    if documents["paired_test_results.json"].get("records") != table.get(
        "paired_test_records"
    ):
        raise FinalComparisonExecutionError("Paired-test documents disagree.")
    if documents["layer_band_decision.json"].get("decision") != table.get(
        "decision"
    ):
        raise FinalComparisonExecutionError("Decision documents disagree.")


__all__ = [
    "BOOTSTRAP_COUNT",
    "BOOTSTRAP_SEED",
    "BOUNDED_REVEAL_CONTRACT_COMMIT",
    "BOUNDED_REVEAL_PREDICTIONS_SHA256",
    "BOUNDED_REVEAL_PREDICTION_COUNT",
    "COMPARISON_CONTRACT_COMMIT",
    "E_COMPARISON_RATIFICATION_COMMIT",
    "FINAL_OUTPUT_FILENAMES",
    "PERMUTATION_COUNT",
    "PERMUTATION_SEED",
    "PERSON_B_PREDICTIONS_SHA256",
    "PERSON_D_COMPLETION_COMMIT",
    "PERSON_D_COMPLETION_SHA256",
    "ComparisonDataset",
    "FinalComparisonExecutionError",
    "build_output_documents",
    "compute_final_comparison",
    "frozen_method_configuration",
    "hierarchical_layout_confidence_interval",
    "inconclusive_output_documents",
    "shared_sign_flip_max_t",
    "validate_frozen_contract",
    "validate_method_configuration",
    "validate_output_documents",
]
