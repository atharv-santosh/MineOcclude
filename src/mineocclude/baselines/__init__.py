"""Non-model baselines, floors, and controls (Person D).

See docs/roadmap Role reference / Person D for the full ownership
list. This package currently implements the closed-form comparisons
that need no fitted model: last-seen, constant-velocity, grouped
shuffled labels, and the time-only spread floor. Explicit-feature,
raw-pixel, visible-history-q, and known-q analytic baselines are not
yet implemented here.
"""

from mineocclude.baselines.constant_velocity import predict_constant_velocity
from mineocclude.baselines.controls import (
    ControlAuditFinding,
    audit_no_wall_control,
    audit_occluder_only_control,
)
from mineocclude.baselines.explicit_feature import fit_predict_explicit_feature
from mineocclude.baselines.export import (
    attach_b_fold_assignments,
    build_baseline_document,
    validate_document,
)
from mineocclude.baselines.interface import BaselineRow, TrajectoryContext, make_baseline_row
from mineocclude.baselines.known_q_analytic import predict_known_q_analytic
from mineocclude.baselines.last_seen import predict_last_seen
from mineocclude.baselines.leakage import (
    IdentityLeakageFinding,
    PredictabilityFinding,
    audit_identity_not_filename_derived,
    audit_layout_fold_isolation,
    check_metadata_predictability,
)
from mineocclude.baselines.random_weight import fit_predict_random_weight
from mineocclude.baselines.raw_pixel import fit_predict_raw_pixel
from mineocclude.baselines.shuffled import apply_grouped_shuffle, make_shuffle_permutation
from mineocclude.baselines.time_only import fit_predict_time_only
from mineocclude.baselines.u4_control_matrix import (
    ControlConditionSpec,
    ControlKind,
    ControlMatrixFinding,
    audit_control_matrix_completeness,
    audit_orthogonal_to_real_direction,
    audit_random_direction_norm_matched,
    build_control_matrix,
)
from mineocclude.baselines.visible_history_q import fit_predict_visible_history_q

__all__ = [
    "BaselineRow",
    "TrajectoryContext",
    "make_baseline_row",
    "predict_constant_velocity",
    "predict_last_seen",
    "apply_grouped_shuffle",
    "make_shuffle_permutation",
    "fit_predict_time_only",
    "fit_predict_explicit_feature",
    "fit_predict_raw_pixel",
    "fit_predict_visible_history_q",
    "predict_known_q_analytic",
    "attach_b_fold_assignments",
    "build_baseline_document",
    "validate_document",
    "ControlAuditFinding",
    "audit_no_wall_control",
    "audit_occluder_only_control",
    "fit_predict_random_weight",
    "IdentityLeakageFinding",
    "PredictabilityFinding",
    "audit_identity_not_filename_derived",
    "audit_layout_fold_isolation",
    "check_metadata_predictability",
    "ControlConditionSpec",
    "ControlKind",
    "ControlMatrixFinding",
    "build_control_matrix",
    "audit_control_matrix_completeness",
    "audit_random_direction_norm_matched",
    "audit_orthogonal_to_real_direction",
]
