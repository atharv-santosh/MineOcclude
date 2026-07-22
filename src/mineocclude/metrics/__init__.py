"""Person B U1-U3 metrics and grouped resampling utilities."""

from .u1_mean import (
    RegressionMetrics,
    U1MetricError,
    baseline_delta_r2,
    duration_binned_metrics,
    regression_metrics,
)
from .u2_calibration import (
    CalibrationMetrics,
    SpreadAudit,
    U2MetricError,
    calibration_metrics,
    fixed_tau_q_summary,
    partial_correlation_controlling_tau,
    reconstruct_sigma,
)
from .u3_dynamics import (
    RevealSnapback,
    U3MetricError,
    oracle_slope_ratio,
    reveal_snapback,
    trajectory_growth_slopes,
)
from .resampling import (
    ResamplingError,
    bootstrap_confidence_interval,
    hierarchical_bootstrap_indices,
    permutation_p_value,
    permute_trajectory_blocks,
)

__all__ = [
    "CalibrationMetrics",
    "RegressionMetrics",
    "ResamplingError",
    "RevealSnapback",
    "SpreadAudit",
    "U1MetricError",
    "U2MetricError",
    "U3MetricError",
    "baseline_delta_r2",
    "bootstrap_confidence_interval",
    "calibration_metrics",
    "duration_binned_metrics",
    "fixed_tau_q_summary",
    "hierarchical_bootstrap_indices",
    "partial_correlation_controlling_tau",
    "permutation_p_value",
    "permute_trajectory_blocks",
    "oracle_slope_ratio",
    "reconstruct_sigma",
    "regression_metrics",
    "reveal_snapback",
    "trajectory_growth_slopes",
]
