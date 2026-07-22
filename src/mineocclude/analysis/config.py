"""Load and validate the frozen Person B Phase 1 analysis configuration."""

from __future__ import annotations

import json
import hashlib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from mineocclude.contracts.identity import SCHEMA_VERSION


DEFAULT_CONFIG_PATH = (
    Path(__file__).resolve().parents[3]
    / "configs"
    / "analysis"
    / "core.yaml"
)
DEFAULT_SPLIT_SEED = 20260719

FROZEN_TARGETS = {
    "mu_oracle_blocks": {
        "unit": "blocks",
        "source": "primary_regime_a_oracle",
        "use": "probe_target",
        "eligibility": "accepted_post_first_seen_rows",
    },
    "var_oracle_blocks2": {
        "unit": "blocks_squared",
        "source": "primary_regime_a_oracle",
        "use": "oracle_audit",
        "eligibility": "accepted_post_first_seen_rows",
    },
    "sigma_oracle_blocks": {
        "unit": "blocks",
        "source": "sqrt(var_oracle_blocks2)",
        "use": "calibration",
        "eligibility": "accepted_post_first_seen_rows",
    },
    "log_sigma_oracle": {
        "unit": "dimensionless",
        "source": "ln(sigma_oracle_blocks / 1 block)",
        "use": "hidden_row_probe_target",
        "eligibility": "accepted_hidden_positive_spread_rows",
        "null_policy": "null_outside_eligibility",
    },
    "x_true_blocks": {
        "unit": "blocks",
        "source": "authoritative_server_state",
        "use": "scoring_only",
        "eligibility": "accepted_post_first_seen_rows",
    },
    "tau": {
        "unit": "seconds",
        "source": "schema_v1_identity",
        "use": "oracle_input_and_time_control",
        "eligibility": "accepted_post_first_seen_rows",
    },
}

FROZEN_SECTIONS = {
    "coordinate_contract": {
        "quantity": "signed_wall_parallel_position",
        "unit": "blocks",
        "coordinate_frame_fields": [
            "coordinate_frame_id",
            "coordinate_frame_hash",
            "wall_parallel_origin_world_xyz",
            "wall_parallel_positive_unit_vector_world_xyz",
        ],
        "positive_direction_rule": (
            "increasing dot(world_position - origin, positive_unit_vector)"
        ),
        "unit_vector_norm_tolerance": 1e-9,
        "requires_person_c_adapter_signoff_before_live_use": True,
        "silent_axis_inference_forbidden": True,
    },
    "filters": {
        "ordered_steps": [
            "required_fields",
            "lifecycle_status",
            "finite_numeric_values",
            "accepted_manifest_match",
            "post_first_seen",
        ],
        "allowed_status": ["accepted"],
        "required_activation_run_status": "completed",
        "exclude_pre_first_seen": True,
        "reject_manifest_mismatch": True,
        "preserve_nonfinite_failures": True,
        "silent_clipping_forbidden": True,
    },
    "cross_validation": {
        "strategy": "layout_grouped",
        "fold_count": 5,
        "split_seed": DEFAULT_SPLIT_SEED,
        "fold_schema_version": "person-b-fold-v0.1",
        "persist_membership": True,
        "inner_strategy": "layout_grouped",
        "inner_fold_count": 4,
        "fit_scaler_on_training_fold_only": True,
        "test_layout_may_select_preprocessing": False,
        "test_layout_may_select_alpha": False,
        "test_layout_may_select_layer": False,
        "test_layout_may_select_intervention_direction": False,
        "u4_development_partition": {
            "fit_layout_count": 3,
            "validation_layout_count": 1,
            "test_layout_count": 2,
            "selection_source": "layout_manifest_only",
        },
    },
    "ridge": {
        "alpha_grid": [0.1, 1.0, 10.0, 100.0],
        "selection_scope": "training_validation_only",
    },
    "mlp": {
        "hidden_layers": [256, 128],
        "activation": "relu",
        "output_dim": 1,
        "eligible_layer_count": 3,
        "eligibility_source": "predeclared_ridge_validation",
        "optimizer": "adam",
        "learning_rate": 0.001,
        "maximum_epochs": 200,
        "early_stopping_patience": 20,
        "batch_size": 64,
        "training_seed": 20260722,
    },
    "metric_rules": {
        "duration_binning": "exact_duration_seconds",
        "coverage_interval": "central_gaussian_inclusive",
        "ece_aggregation": "mean_absolute_nominal_empirical_gap",
        "near_zero_sigma_threshold_blocks": 1e-12,
        "nonfinite_policy": "count_and_fail_result_no_clipping",
        "partial_correlation_controls": ["tau"],
        "reveal_window_seconds": [-1.0, 1.0],
    },
    "resampling": {
        "permutation_count_mvp": 999,
        "bootstrap_count_mvp": 1000,
        "bootstrap_count_final_minimum": 2000,
        "hierarchy": ["layout_id", "trajectory_id"],
        "permutation_seed": 20260720,
        "bootstrap_seed": 20260721,
        "permutation_unit": "whole_trajectory_block",
        "permutation_p_value": "add_one_greater_or_equal",
    },
    "artifact_policy": {
        "schema_version": "person-b-analysis-artifact-v0.1",
        "hash_algorithm": "sha256",
        "hash_serialization": "canonical_json_utf8",
        "config_hash_source": "literal_config_file_bytes",
        "corrections_are_append_only": True,
        "result_affecting_change_requires_new_run": True,
    },
    "outputs": {
        "U1": ["r2", "mae", "grouped_permutation", "baseline_comparison"],
        "U2": [
            "partial_correlation_controlling_tau",
            "coverage",
            "ece",
            "z_diagnostics",
        ],
        "U3": ["hidden_growth", "oracle_slope_ratio", "reveal_snapback"],
        "U4": [
            "raw_space_direction",
            "time_projection_audit",
            "alpha_to_blocks",
            "norm_cap",
        ],
    },
}

FROZEN_TOP_LEVEL_KEYS = {
    "schema_version",
    "analysis_config_version",
    "status",
    "targets",
    "coverage_levels",
} | set(FROZEN_SECTIONS)


class AnalysisConfigError(ValueError):
    """Raised when the Person B analysis contract is incomplete or unsafe."""


def validate_core_analysis_config(config: Mapping[str, Any]) -> None:
    """Validate the Phase 1 analysis settings without external YAML packages.

    ``core.yaml`` intentionally contains JSON, which is valid YAML and can be
    parsed by Python's standard library during the dependency-light phase.
    """

    if not isinstance(config, Mapping):
        raise AnalysisConfigError("Analysis config must be a mapping.")
    if set(config) != FROZEN_TOP_LEVEL_KEYS:
        raise AnalysisConfigError("Top-level analysis config fields have changed.")
    if config.get("schema_version") != SCHEMA_VERSION:
        raise AnalysisConfigError(f"Expected schema version {SCHEMA_VERSION!r}.")
    if config.get("analysis_config_version") != "person-b-phase1-v0.2":
        raise AnalysisConfigError("Analysis config version has changed.")
    if config.get("status") != "frozen_before_live_results":
        raise AnalysisConfigError("Analysis config must remain frozen before live results.")

    targets = config.get("targets")
    if not isinstance(targets, Mapping) or targets != FROZEN_TARGETS:
        raise AnalysisConfigError(
            "Target names, units, sources, uses, or eligibility rules have changed."
        )

    for name, expected in FROZEN_SECTIONS.items():
        actual = config.get(name)
        if not isinstance(actual, Mapping) or actual != expected:
            raise AnalysisConfigError(f"Frozen {name} settings have changed.")

    if config.get("coverage_levels") != [0.5, 0.8, 0.95]:
        raise AnalysisConfigError("Coverage levels must be 50%, 80%, and 95%.")


def load_core_analysis_config(path: Path | str = DEFAULT_CONFIG_PATH) -> dict[str, Any]:
    """Load and validate the JSON-compatible YAML analysis config."""

    config_path = Path(path)
    try:
        payload = config_path.read_bytes()
        config = json.loads(payload.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AnalysisConfigError(
            f"Could not load analysis config {config_path}: {error}"
        ) from error

    if not isinstance(config, dict):
        raise AnalysisConfigError("Analysis config must contain one mapping.")

    validate_core_analysis_config(config)
    return config


def hash_core_analysis_config(path: Path | str = DEFAULT_CONFIG_PATH) -> str:
    """Return the SHA-256 of the exact validated config-file bytes.

    Hashing happens only after parsing and validating the same byte payload, so
    callers cannot attach a syntactically valid but unrelated hash to a run.
    """

    config_path = Path(path)
    try:
        payload = config_path.read_bytes()
        config = json.loads(payload.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AnalysisConfigError(
            f"Could not load analysis config {config_path}: {error}"
        ) from error
    if not isinstance(config, dict):
        raise AnalysisConfigError("Analysis config must contain one mapping.")
    validate_core_analysis_config(config)
    return hashlib.sha256(payload).hexdigest()
