"""Non-model baselines, floors, and controls (Person D).

See ``docs/baselines/person_d_phase0.md`` for current ownership and dependency
status. This package contains the synthetic Phase 1 baseline/control
foundation exported below. Its presence does not claim real-data execution or
final scientific results.
"""

from mineocclude.baselines.capture_ingest import (
    UNASSIGNED_FOLD,
    CaptureIngestError,
    build_contexts_from_capture,
)
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
from mineocclude.baselines.firewall import LegalInputRow, select_legal_inputs
from mineocclude.baselines.harness import (
    EstimatorPrediction,
    HarnessResult,
    run_synthetic_baseline_harness,
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
from mineocclude.baselines.missingness import (
    MissingnessCell,
    MissingnessExclusionReport,
    build_missingness_exclusion_report,
    summarize_non_applicable_reasons,
)
from mineocclude.baselines.positive_control_gate import (
    REAL_NO_WALL_DATA_PROVENANCE,
    STEP_4_3_R2_THRESHOLD,
    PositiveControlGateError,
    PositiveControlGateFinding,
    evaluate_no_wall_positive_control_gate,
)
from mineocclude.baselines.random_weight import fit_predict_random_weight
from mineocclude.baselines.raw_pixel import fit_predict_raw_pixel
from mineocclude.baselines.spec import (
    BASELINE_SPEC_SCHEMA_VERSION,
    PREDICTION_SCHEMA_VERSION,
    BaselineContractCode,
    BaselineContractError,
    BaselinePrediction,
    BaselineSpec,
    supported_baseline_spec,
    validate_baseline_spec,
    validate_prediction_row,
)
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
from mineocclude.baselines.visible_history_q import (
    VisibleHistoryQError,
    fit_predict_visible_history_q,
)

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
    "VisibleHistoryQError",
    "predict_known_q_analytic",
    "attach_b_fold_assignments",
    "build_baseline_document",
    "validate_document",
    "BASELINE_SPEC_SCHEMA_VERSION",
    "PREDICTION_SCHEMA_VERSION",
    "BaselineContractCode",
    "BaselineContractError",
    "BaselinePrediction",
    "BaselineSpec",
    "supported_baseline_spec",
    "validate_baseline_spec",
    "validate_prediction_row",
    "LegalInputRow",
    "select_legal_inputs",
    "EstimatorPrediction",
    "HarnessResult",
    "run_synthetic_baseline_harness",
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
    "MissingnessCell",
    "MissingnessExclusionReport",
    "build_missingness_exclusion_report",
    "summarize_non_applicable_reasons",
    "UNASSIGNED_FOLD",
    "CaptureIngestError",
    "build_contexts_from_capture",
    "REAL_NO_WALL_DATA_PROVENANCE",
    "STEP_4_3_R2_THRESHOLD",
    "PositiveControlGateError",
    "PositiveControlGateFinding",
    "evaluate_no_wall_positive_control_gate",
]
