"""Frozen, non-executing Step 4.1 final-comparison contract.

This module contains contract data and deterministic contract-test helpers only.
It does not read production artifacts, fit probes, or calculate live metrics.
"""

from __future__ import annotations

import math
import random
from collections.abc import Mapping, Sequence
from typing import Any

CONTRACT_VERSION = "person-b-step4-1-final-comparison-v0.1"
PERSON_B_STARTING_AUTHORITY = "2a23c84995fea4e15293039063e60e9535fd2ee2"
PERSON_D_COMPLETION_COMMIT = "f89b142a6fdb52c2d238669af8df14061cee5896"
PERSON_E_STARTING_AUTHORITY = "21d83c19c9d8f36c4dbeeaf45d4626eaf082e7a7"
HOOK_SITE = "decoder_layer_output_residual_stream"
LAYERS = tuple(range(20))
CORE_PILOTS = (
    "layout_00_ep9403",
    "layout_01_ep9405",
    "layout_02_ep9407",
    "layout_03_ep9404",
    "layout_04_ep9406",
)


class FinalComparisonContractError(ValueError):
    """Raised when a final-comparison contract is not exact and complete."""


def _artifact(path: str, sha256: str, byte_size: int | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {"path": path, "sha256": sha256}
    if byte_size is not None:
        result["byte_size"] = byte_size
    return result


def build_final_comparison_contract() -> dict[str, Any]:
    """Return the one complete v0.1 contract; runtime choices are forbidden."""

    return {
        "acceptance_contract": {
            "decision_precedence": [
                "INCONCLUSIVE_integrity_or_control_gate",
                "PASS_all_scientific_gates",
                "FAIL_clean_scientific_miss",
            ],
            "fail_rule": (
                "All integrity, lineage, applicability, finiteness, positive-control, "
                "and resampling gates pass, but no contiguous qualifying layer band "
                "of length at least two exists."
            ),
            "inconclusive_rule": (
                "Any unknown version or hash, missing/extra/duplicate/nonfinite row, "
                "unexpected applicability mismatch, leakage, failed positive control, "
                "missing reveal pair, fewer than two independent layout units, "
                "degenerate required statistic, or unauthorized execution makes the "
                "result INCONCLUSIVE and forbids negative scientific interpretation."
            ),
            "layer_gate": {
                "adjacency": "integer layer_idx differs by exactly one",
                "minimum_contiguous_length": 2,
                "no_best_layer_is_selected": True,
                "qualifying_layer_requires": ["U1_green", "U2_green", "U3_green"],
                "report_all_qualifying_bands": True,
            },
            "pass_rule": (
                "All integrity and control gates pass and at least one contiguous band "
                "of two or more adjacent frozen layers has every layer satisfy U1_green, "
                "U2_green, and U3_green."
            ),
            "scientific_gates": {
                "U1_green": {
                    "held_out_r2_strictly_greater_than": 0.0,
                    "max_t_adjusted_p_strictly_less_than": 0.01,
                    "paired_loss_improvement_strictly_greater_than": 0.0,
                    "required_primary_baselines": ["last_seen", "grouped_shuffled"],
                },
                "U2_green": {
                    "average_absolute_coverage_error_at_most": 0.10,
                    "coverage_levels": [0.5, 0.8, 0.95],
                    "coverage_error_strictly_better_than": [
                        "time_only",
                        "visible_history_q",
                    ],
                    "partial_correlation_bootstrap_ci_lower_strictly_greater_than": 0.0,
                    "partial_correlation_controls": ["tau"],
                },
                "U3_green": {
                    "decoded_hidden_growth_strictly_greater_than": 0.0,
                    "median_reveal_reduction_fraction_at_least": 0.25,
                    "oracle_slope_ratio_closed_interval": [0.5, 2.0],
                    "reveal_difference_bootstrap_ci_upper_strictly_less_than": 0.0,
                },
            },
            "status_vocabulary": ["PASS", "FAIL", "INCONCLUSIVE"],
        },
        "aggregation_contract": {
            "baseline_family_aggregation": (
                "Never pool baseline families. Emit one layer-target-family result; "
                "roles and fair/non-fair labels remain attached."
            ),
            "excluded_identity_treatment": (
                "Use only exclusions named by the ratified applicability contract. "
                "Report each excluded identity and reason; never count it as failure, "
                "zero, or imputed prediction."
            ),
            "fold_aggregation": (
                "Validate OOF provenance and emit fold diagnostics, but do not average "
                "fold summaries because folds contain unequal layout counts."
            ),
            "layer_aggregation": (
                "No numeric aggregation across layers. Emit all 20 layer results and "
                "apply the frozen contiguous-band decision rule."
            ),
            "macro_micro_policy": (
                "Primary statistics are layout-macro: rows are averaged within each "
                "trajectory, trajectories equally within layout, then layouts equally. "
                "Pooled-frame micro statistics are descriptive only."
            ),
            "missing_data_policy": (
                "Strict applicability-aware inner intersection only. No imputation, "
                "carry-forward, clipping, replacement, or silent drop. Missing expected "
                "rows or extra rows make the affected required result INCONCLUSIVE."
            ),
            "pilot_aggregation": (
                "The five core pilots are scientific units. The five no-wall pilots are "
                "used only through the already frozen positive-control decision and are "
                "never pooled into hidden-target metrics."
            ),
            "row_level_pairing_keys": [
                "trajectory_id",
                "model_frame_idx",
                "fold_idx",
                "target_name",
            ],
            "probe_specific_pairing_keys": ["layer_idx", "hook_site"],
            "reveal_pairing_keys": ["event_id", "trajectory_id", "layer_idx", "hook_site"],
            "target_aggregation": (
                "Never combine mu_oracle_blocks and log_sigma_oracle. U1 consumes mean "
                "predictions; U2/U3 reconstruct sigma_hat=exp(log_sigma_hat)."
            ),
            "weighting_rule": "equal_layout_then_equal_trajectory_then_equal_row",
        },
        "authorities": {
            "person_b_starting_authority": PERSON_B_STARTING_AUTHORITY,
            "person_d_completion_commit": PERSON_D_COMPLETION_COMMIT,
            "person_e_ratification_required_before_execution": True,
            "person_e_starting_authority": PERSON_E_STARTING_AUTHORITY,
            "this_contract_authority": (
                "The Git commit containing this package; it must be the direct child "
                "of person_b_starting_authority."
            ),
        },
        "baseline_contract": {
            "applicability": _artifact(
                "docs/status/person_b_phase4_step4_1_applicability_contract_v0_1/"
                "family_target_applicability_contract.json",
                "3ee4991589b828007091811823cb6e26fbfecc14a2c0331629cf6a014b131103",
            ),
            "family_order": [
                "last_seen",
                "constant_velocity",
                "grouped_shuffled",
                "time_only",
                "explicit_feature",
                "raw_pixel",
                "visible_history_q",
                "known_q_analytic",
            ],
            "non_fair_reference_families": ["known_q_analytic"],
            "prediction_count": 10776,
            "prediction_documents": [
                {"family": "last_seen", "target": "mu_oracle_blocks", "row_count": 1695, "sha256": "48481740b50d41f87ac78ef7e2a4a1be930c400f197613c13212f7bfdb4bf4ae"},
                {"family": "constant_velocity", "target": "mu_oracle_blocks", "row_count": 1690, "sha256": "1156b6ca9bdc72355c23f8bcd2cbe9ba0324ad9e861fee47a246e5ef0a09fc7a"},
                {"family": "grouped_shuffled", "target": "log_sigma_oracle", "row_count": 493, "sha256": "cc182dfa1795eba5eb59c98dfb54d1d7eda9a39e6f3188846c863d9b12142fcc"},
                {"family": "grouped_shuffled", "target": "mu_oracle_blocks", "row_count": 1428, "sha256": "db190c7fdd99e0eb075cdf603b9e7bb516caa857d2f1167e5ecf8da84c315ba5"},
                {"family": "time_only", "target": "log_sigma_oracle", "row_count": 695, "sha256": "aa8a60d9ee36a27655abd0a13b5aba2665aa5d865a9332c3f2a840cfbae5d273"},
                {"family": "explicit_feature", "target": "mu_oracle_blocks", "row_count": 1690, "sha256": "c724dc1b8918556508e4b4260315b16cf294977d51231f7c05963bc27ea973e7"},
                {"family": "raw_pixel", "target": "mu_oracle_blocks", "row_count": 1695, "sha256": "bb0a15f9d2d54f53e46c6a201d464958f2f8db90decba5784e81a99ff2298420"},
                {"family": "visible_history_q", "target": "log_sigma_oracle", "row_count": 695, "sha256": "5ef20829a26a09d4c1407c8d398cc1429266b2b45ae233fe4679d35f57c24bbc"},
                {"family": "known_q_analytic", "target": "log_sigma_oracle", "row_count": 695, "sha256": "f589af2acc429460b8e9fc2725401e2adb5c0ce6424f73f3867fa43bda8ff2cd"},
            ],
            "production_root": (
                "/home/sagemaker-user/person-d-step4-1-approved-outputs/"
                "person-d-step4-1-production-v0-1"
            ),
            "run_state": _artifact(
                "/home/sagemaker-user/person-d-step4-1-approved-outputs/"
                "person-d-step4-1-production-v0-1/run_state.json",
                "79c49e7c794f37c4a574dfef365b8183ddb443b246adbe94743dfdf1ff1f4cf5",
                1480,
            ),
        },
        "confidence_interval_contract": {
            "bootstrap_count": 2000,
            "coverage": 0.95,
            "hierarchy": ["layout_id", "trajectory_id", "all_paired_rows"],
            "interval": "equal_tailed_percentile_linear_quantiles",
            "seed": 20260721,
            "unit": "whole_layout_then_whole_trajectory",
        },
        "control_contract": {
            "negative_control": {
                "family": "grouped_shuffled",
                "role": "trajectory_deranged_chance_floor",
                "required_targets": ["mu_oracle_blocks", "log_sigma_oracle"],
            },
            "no_object_control": {
                "decision": "NOT_APPLICABLE_TO_FROZEN_TEN_PILOT_PRODUCTION_SET",
                "reason": (
                    "No occluder-only/no-sheep pilot is in the immutable ten-pilot "
                    "production membership; adding one would change accepted identities."
                ),
            },
            "positive_control": {
                "authority_commit": "e39fef4a59142a84dfb5991d51deeb506eb23a7b",
                "decision": "PASS_FROZEN_VISIBLE_POSITION_POSITIVE_CONTROL",
                "decision_sha256": "742557b32326180003b1cd83ed5db6f1a1ebfebd692d969809698d323f239056",
                "lineage_sha256": "29fd15d6773f16843d3de6b8db58c2d100bcf47779b41bbd44a3c81a062f74f4",
                "must_be_revalidated_not_recomputed": True,
            },
        },
        "degree_of_freedom_resolutions": [
            {
                "choice": "Evaluate every frozen layer; select no best layer.",
                "consequence": "Inference is conservative and cannot promote an isolated maximum.",
                "resolution_authority": "person_b_scientific_methods_owner",
                "source": "PERSON_B_MVP_ROADMAP.md contiguous-band and no-test-layer-selection rules",
            },
            {
                "choice": "Require one common contiguous band to satisfy U1, U2, and U3.",
                "consequence": "A signal split across unrelated layers cannot pass Step 4.1.",
                "resolution_authority": "person_b_scientific_methods_owner",
                "source": "Frozen U1 band criterion and alternative-results no-favorable-layer-search rule",
            },
            {
                "choice": "Use shared-sign maxT correction within each declared objective family.",
                "consequence": "Controls family-wise error while preserving dependence across layers.",
                "resolution_authority": "person_b_scientific_methods_owner",
                "source": "Frozen whole-trajectory permutation unit, count, seed, and p<0.01 U1 gate",
            },
            {
                "choice": "Map the detailed U3_green gate, not vague directional wording, to PASS.",
                "consequence": "PASS uses the stricter predeclared slope, CI, and 25% thresholds.",
                "resolution_authority": "person_b_scientific_methods_owner",
                "source": "PERSON_B_MVP_ROADMAP.md detailed MVP acceptance gates",
            },
        ],
        "execution_interface": {
            "command": [
                "python",
                "scripts/run_person_b_step4_1_final_comparison.py",
                "--repository-root",
                "$PWD",
                "--person-b-contract-commit",
                "<PERSON_B_POST_REVEAL_CONTRACT_COMMIT>",
                "--person-e-ratification-commit",
                "<PERSON_E_COMPARISON_RATIFICATION_COMMIT>",
                "--person-b-predictions",
                "/home/sagemaker-user/person-b-step4-1-approved-outputs/person-b-step4-1-production-v0-1/fitted_probes_and_predictions.json",
                "--person-d-root",
                "/home/sagemaker-user/person-d-step4-1-approved-outputs/person-d-step4-1-production-v0-1",
                "--post-reveal-predictions",
                "/home/sagemaker-user/person-b-step4-1-approved-outputs/person-b-step4-1-bounded-reveal-v0-1/post_reveal_predictions.json",
                "--output-root",
                "/home/sagemaker-user/person-b-step4-1-approved-outputs/person-b-step4-1-final-comparison-v0-1",
            ],
            "execution_count": 1,
            "fail_closed_gates": [
                "exact B contract commits and E ratification Git objects",
                "all literal input byte sizes and SHA-256 values",
                "canonical strict JSON with no duplicate or nonfinite values",
                "exact prediction, target, layer, hook, fold, row, and applicability identities",
                "zero fold leakage and only out-of-fold fitted probes",
                "complete positive and negative control evidence",
                "complete post-reveal receipt and 100 exact predictions",
                "clean role/person-b-analysis checkout at exact contract commit",
                "output root absent or exact complete no-write receipt",
            ],
            "output_root": (
                "/home/sagemaker-user/person-b-step4-1-approved-outputs/"
                "person-b-step4-1-final-comparison-v0-1"
            ),
            "outputs": [
                "comparison_metric_table.json",
                "paired_test_results.json",
                "confidence_intervals.json",
                "layer_band_decision.json",
                "registry_v2_import_package.json",
                "execution_receipt.json",
                "sha256_inventory.json",
            ],
            "person_e_ratification_required": True,
            "resume_behavior": (
                "If the output root exists, validate a complete exact inventory and "
                "return ALREADY_COMPLETE_NO_WRITE; otherwise fail. Partial resume and "
                "overwrite are forbidden."
            ),
        },
        "input_contract": {
            "analysis_config": _artifact(
                "configs/analysis/core.yaml",
                "b2e12e7049e0494c756be442a4f300cbc7dc0a6e262deecf682f1354e887f0ab",
                4881,
            ),
            "fold_manifest": _artifact(
                "docs/status/person_b_phase4_step4_1_production_handoff_v0_1/"
                "ten_pilot_frame_fold_manifest.json",
                "53ca938c6ae936c3ecb6e6e8d95a3fda152f5fa130b52e7a000d297810738d71",
                742601,
            ),
            "oracle_target": _artifact(
                "docs/status/person_b_phase4_step4_1_production_handoff_v0_1/"
                "production_oracle_target_manifest.json",
                "afcf3afae00db6330665afc5964608c6db89eeac3767c9486d8ba0a218858282",
                4934874,
            ),
            "person_b_predictions": _artifact(
                "/home/sagemaker-user/person-b-step4-1-approved-outputs/"
                "person-b-step4-1-production-v0-1/fitted_probes_and_predictions.json",
                "01e792c4d7b58bbe4ae478195b1d9523802db5674ee06ebbf5364482f42061ba",
                84257218,
            ),
            "person_b_prediction_count": 27800,
            "person_b_probe_matrix_count": 40,
            "post_reveal_input": {
                "exact_artifact_hash_is_bound_by_person_e_after_production": True,
                "required_prediction_count": 100,
                "required_schema_id": "person-b-step4-1-bounded-reveal-predictions-v0-1",
            },
        },
        "layer_contract": {
            "hook_site": HOOK_SITE,
            "layer_indices": list(LAYERS),
            "selection_mode": "none_all_layers_fixed_before_runtime",
            "test_data_may_select_layer": False,
        },
        "metric_contract": {
            "primary_comparison_statistic": {
                "definition": (
                    "layout-macro paired loss improvement = baseline loss minus probe "
                    "loss on the exact applicability-aware row intersection"
                ),
                "log_sigma_loss": "squared_error_in_log_sigma",
                "mu_loss": "squared_error_in_blocks",
                "positive_direction": "probe_better",
            },
            "reveal_snapback": {
                "event_count": 5,
                "metric": "median(post_sigma_hat_blocks - pre_sigma_hat_blocks)",
                "pair_rule": "nearest occluded time<0 and nearest visible time>=0",
                "reduction_fraction": "median((pre_sigma_hat-post_sigma_hat)/pre_sigma_hat)",
                "relative_times_seconds": [-0.05, 0.0],
                "window_seconds": [-1.0, 1.0],
            },
            "secondary_statistics": [
                "r2",
                "mae_blocks",
                "partial_correlation_controlling_tau",
                "50_80_95_percent_interval_coverage",
                "mean_absolute_coverage_error",
                "z_diagnostics",
                "trajectory_hidden_growth_slope",
                "decoded_oracle_slope_ratio",
                "median_reveal_reduction_fraction",
            ],
        },
        "multiplicity_contract": {
            "adjustment": "single_step_shared_sign_flip_maxT",
            "family_wise_comparison_sets": {
                "U1": "20 layers x [last_seen, grouped_shuffled] = 40 hypotheses",
                "U2": "20 layers x [time_only, visible_history_q] = 40 hypotheses",
                "U3_reveal": "20 layer reveal-decrease hypotheses",
            },
            "null_hypothesis": "layout-macro paired improvement is less than or equal to zero",
            "permutation_count": 999,
            "resampling_unit": "whole_trajectory_pair_with_one_shared_sign_per_layout",
            "seed": 20260720,
            "sidedness": "one_sided_in_predeclared_improvement_direction",
            "studentization": "mean_layout_improvement_divided_by_standard_error",
            "tie_rule": "greater_than_or_equal_is_extreme",
            "p_value_rule": "add_one_numerator_and_denominator",
        },
        "output_schema_contract": {
            "canonicalization": "UTF-8 JSON sorted keys indent=2 newline; finite numbers only",
            "metric_record_required_fields": [
                "metric_id",
                "objective",
                "target_name",
                "layer_idx",
                "hook_site",
                "baseline_family",
                "value",
                "unit",
                "sample_count",
                "sample_unit",
                "status",
                "diagnostic",
                "direct_input_sha256s",
            ],
            "paired_test_required_fields": [
                "hypothesis_id",
                "objective_family",
                "observed_statistic",
                "raw_p_value",
                "max_t_adjusted_p_value",
                "permutation_count",
                "seed",
                "sidedness",
                "null_hypothesis",
                "layout_count",
            ],
            "registry_v2_artifact_type": "metric_table",
            "schema_id": "person-b-step4-1-final-comparison-output-v0-1",
        },
        "reveal_event_contract": [
            {"event_id": "layout_00_ep9403:reveal:228", "trajectory_id": "layout_00_ep9403", "layout_id": "layout_00", "fold_idx": 1, "pre_model_frame_idx": 227, "post_model_frame_idx": 228},
            {"event_id": "layout_01_ep9405:reveal:210", "trajectory_id": "layout_01_ep9405", "layout_id": "layout_01", "fold_idx": 2, "pre_model_frame_idx": 209, "post_model_frame_idx": 210},
            {"event_id": "layout_02_ep9407:reveal:138", "trajectory_id": "layout_02_ep9407", "layout_id": "layout_02", "fold_idx": 4, "pre_model_frame_idx": 137, "post_model_frame_idx": 138},
            {"event_id": "layout_03_ep9404:reveal:106", "trajectory_id": "layout_03_ep9404", "layout_id": "layout_03", "fold_idx": 0, "pre_model_frame_idx": 105, "post_model_frame_idx": 106},
            {"event_id": "layout_04_ep9406:reveal:93", "trajectory_id": "layout_04_ep9406", "layout_id": "layout_04", "fold_idx": 3, "pre_model_frame_idx": 92, "post_model_frame_idx": 93},
        ],
        "schema_id": "person-b-step4-1-final-comparison-contract-v0-1",
        "schema_version": "1.0",
        "scope": {
            "core_pilots": list(CORE_PILOTS),
            "layers": list(LAYERS),
            "targets": ["mu_oracle_blocks", "log_sigma_oracle"],
        },
        "scientific_execution_performed": False,
        "unresolved_scientific_choices": [],
        "u4_restrictions": {
            "broad_hidden_state_interpretation_authorized": False,
            "manual_u4_inspection_authorized": False,
            "u4_input_or_output_may_be_opened": False,
            "u4_output_inspected": False,
        },
        "version": CONTRACT_VERSION,
    }


def validate_final_comparison_contract(document: Any) -> None:
    """Fail unless *document* is the exact frozen contract."""

    expected = build_final_comparison_contract()
    if document != expected:
        raise FinalComparisonContractError("Contract differs from frozen v0.1 bytes.")
    if document["unresolved_scientific_choices"]:
        raise FinalComparisonContractError("Scientific choices remain unresolved.")
    if document["layer_contract"]["selection_mode"] != (
        "none_all_layers_fixed_before_runtime"
    ):
        raise FinalComparisonContractError("Layer selection is not fail-closed.")
    if document["scientific_execution_performed"] is not False:
        raise FinalComparisonContractError("Contract falsely claims execution.")
    restrictions = document["u4_restrictions"]
    if any(restrictions.values()):
        raise FinalComparisonContractError("U4 access or interpretation was expanded.")


def layout_macro_mean(rows: Sequence[Mapping[str, Any]]) -> float:
    """Synthetic-test helper for the frozen equal-layout weighting rule."""

    if not rows:
        raise FinalComparisonContractError("Macro input cannot be empty.")
    by_layout: dict[str, dict[str, list[float]]] = {}
    for row in rows:
        layout = row.get("layout_id")
        trajectory = row.get("trajectory_id")
        value = row.get("value")
        if (
            not isinstance(layout, str)
            or not layout
            or not isinstance(trajectory, str)
            or not trajectory
            or isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
        ):
            raise FinalComparisonContractError("Macro row is malformed.")
        by_layout.setdefault(layout, {}).setdefault(trajectory, []).append(float(value))
    layout_values = []
    for trajectories in by_layout.values():
        trajectory_values = [sum(values) / len(values) for values in trajectories.values()]
        layout_values.append(sum(trajectory_values) / len(trajectory_values))
    return sum(layout_values) / len(layout_values)


def _studentized(values: Sequence[float]) -> float:
    if len(values) < 2 or any(not math.isfinite(value) for value in values):
        raise FinalComparisonContractError("Studentized statistic needs finite units.")
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / (len(values) - 1)
    if variance == 0.0:
        raise FinalComparisonContractError("Studentized statistic is degenerate.")
    return mean / math.sqrt(variance / len(values))


def max_t_adjusted_p_values(
    hypotheses: Mapping[str, Mapping[str, float]],
    *,
    permutation_count: int = 999,
    seed: int = 20260720,
) -> dict[str, float]:
    """Apply the frozen shared-layout one-sided maxT sign-flip procedure."""

    if not hypotheses or permutation_count < 1:
        raise FinalComparisonContractError("maxT inputs are empty or malformed.")
    layouts = sorted({layout for values in hypotheses.values() for layout in values})
    if len(layouts) < 2:
        raise FinalComparisonContractError("maxT requires at least two layouts.")
    observed = {
        name: _studentized([float(value) for value in values.values()])
        for name, values in hypotheses.items()
    }
    rng = random.Random(seed)
    maxima = []
    for _ in range(permutation_count):
        signs = {layout: rng.choice((-1.0, 1.0)) for layout in layouts}
        null_stats = []
        for values in hypotheses.values():
            null_stats.append(
                _studentized(
                    [float(value) * signs[layout] for layout, value in values.items()]
                )
            )
        maxima.append(max(null_stats))
    return {
        name: (1.0 + sum(value >= statistic for value in maxima))
        / (permutation_count + 1.0)
        for name, statistic in observed.items()
    }


def qualifying_layer_bands(layer_gates: Mapping[int, bool]) -> tuple[tuple[int, ...], ...]:
    """Return every maximal qualifying adjacent band of length at least two."""

    if set(layer_gates) != set(LAYERS):
        raise FinalComparisonContractError("Layer gates must cover exactly layers 0..19.")
    bands: list[tuple[int, ...]] = []
    current: list[int] = []
    for layer in LAYERS:
        if layer_gates[layer] is True:
            current.append(layer)
        else:
            if len(current) >= 2:
                bands.append(tuple(current))
            current = []
    if len(current) >= 2:
        bands.append(tuple(current))
    return tuple(bands)


__all__ = [
    "CONTRACT_VERSION",
    "FinalComparisonContractError",
    "build_final_comparison_contract",
    "layout_macro_mean",
    "max_t_adjusted_p_values",
    "qualifying_layer_bands",
    "validate_final_comparison_contract",
]
