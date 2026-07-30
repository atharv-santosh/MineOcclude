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
from mineocclude.baselines.registry_v2_artifacts import (
    EXACT_ARTIFACT_AUTHORIZATION_ARTIFACT_TYPE,
    HANDOFF_MANIFEST_ARTIFACT_TYPE,
    OWNER_STATUS_ARTIFACT_TYPE,
    OWNER_STATUS_DECISIONS,
    OWNER_STATUSES,
    REGISTRY_V2_HANDOFF_SCHEMA_VERSION,
    VERIFICATION_RECEIPT_ARTIFACT_TYPE,
    RegistryV2ArtifactError,
    RegistryV2HandoffPackage,
    build_exact_artifact_authorization,
    build_handoff_manifest,
    build_owner_status_record,
    build_verification_receipt,
    validate_exact_artifact_authorization,
    validate_handoff_manifest,
    validate_owner_status_record,
    validate_registry_v2_handoff_package,
    validate_verification_receipt,
)
from mineocclude.baselines.scientific_readiness import (
    BASELINE_PREDICTION_DIRECT_INPUTS,
    READY_SCIENTIFIC_USE,
    SCIENTIFIC_BASELINE_INPUT_CONTRACT_SCHEMA_VERSION,
    ScientificReadinessError,
    ScientificReadinessFinding,
    build_baseline_prediction_artifact_id,
    validate_scientific_baseline_readiness,
)
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
    "SCIENTIFIC_BASELINE_INPUT_CONTRACT_SCHEMA_VERSION",
    "READY_SCIENTIFIC_USE",
    "BASELINE_PREDICTION_DIRECT_INPUTS",
    "ScientificReadinessError",
    "ScientificReadinessFinding",
    "validate_scientific_baseline_readiness",
    "build_baseline_prediction_artifact_id",
    "REGISTRY_V2_HANDOFF_SCHEMA_VERSION",
    "OWNER_STATUS_ARTIFACT_TYPE",
    "EXACT_ARTIFACT_AUTHORIZATION_ARTIFACT_TYPE",
    "HANDOFF_MANIFEST_ARTIFACT_TYPE",
    "VERIFICATION_RECEIPT_ARTIFACT_TYPE",
    "OWNER_STATUSES",
    "OWNER_STATUS_DECISIONS",
    "RegistryV2ArtifactError",
    "RegistryV2HandoffPackage",
    "build_owner_status_record",
    "validate_owner_status_record",
    "build_exact_artifact_authorization",
    "validate_exact_artifact_authorization",
    "build_handoff_manifest",
    "validate_handoff_manifest",
    "build_verification_receipt",
    "validate_verification_receipt",
    "validate_registry_v2_handoff_package",
]
