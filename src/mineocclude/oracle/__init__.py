"""Person B oracle implementations and target construction."""

from .closed_form import closed_form_posterior
from .primary_scalar_kalman import scalar_kalman_posterior
from .schema import (
    OracleValidationError,
    ScalarPosterior,
    validate_oracle_target,
    validate_oracle_target_document,
    validate_oracle_target_rows,
)
from .targets import build_regime_a_target_document, build_regime_a_targets
from .visible_history_sensitivity import (
    VisibleHistoryEstimate,
    estimate_visible_history_motion,
    visible_history_posterior,
)

__all__ = [
    "ScalarPosterior",
    "OracleValidationError",
    "build_regime_a_target_document",
    "build_regime_a_targets",
    "closed_form_posterior",
    "scalar_kalman_posterior",
    "validate_oracle_target",
    "validate_oracle_target_document",
    "validate_oracle_target_rows",
    "VisibleHistoryEstimate",
    "estimate_visible_history_motion",
    "visible_history_posterior",
]
