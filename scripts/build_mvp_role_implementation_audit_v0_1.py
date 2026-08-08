#!/usr/bin/env python3
"""Build the immutable Week-1 MVP role implementation audit package.

This builder records an audit of existing authorities.  It does not execute
MineWorld, refit probes/baselines, or mutate any scientific result package.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
import xml.etree.ElementTree as ET


REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "docs/status/integration/mvp_role_implementation_audit_v0_1"
BRANCH = "integration/mvp-final"
HEAD = "3a45957d3b06e43ec80b2032fcb1cd50a2aea204"
STATUS_VALUES = {
    "PASS",
    "PASS_SUPERSEDED_IMPLEMENTATION",
    "BLOCKED_EXTERNAL_DATA",
    "NOT_APPLICABLE_MVP_SCOPE",
    "UNVERIFIED",
    "FAIL",
}
VERDICT_VALUES = {
    "ROLE_COMPLETE",
    "ROLE_COMPLETE_WITH_NONBLOCKING_SCOPE_EXCLUSIONS",
    "ROLE_INCOMPLETE",
    "ROLE_INVALID",
}
REQUIRED_FIELDS = {
    "role",
    "manual_phase_or_step",
    "requirement",
    "status",
    "implementation_path",
    "evidence_path",
    "tests",
    "explanation",
    "blocker_if_any",
}

MANUAL_ATTACHMENTS = {
    "controlling_audit": Path("/home/sagemaker-user/.codex/attachments/364a3a60-61ce-44ed-bb8d-c396977bc259/pasted-text.txt"),
    "person_a": Path("/home/sagemaker-user/.codex/attachments/0aab7542-8b8b-4324-a339-18bb35166931/pasted-text.txt"),
    "person_b": Path("/home/sagemaker-user/.codex/attachments/358c3eba-7c43-4629-ba01-d25cfe3577de/pasted-text.txt"),
    "person_c": Path("/home/sagemaker-user/.codex/attachments/4efe5be0-b81c-425b-9df7-7b613ca0cec6/pasted-text.txt"),
    "person_d": Path("/home/sagemaker-user/.codex/attachments/7e56de97-c6b2-493d-8ed3-2221f95a3fee/pasted-text.txt"),
    "person_e": Path("/home/sagemaker-user/.codex/attachments/0a632b36-e896-4112-acc8-28df8034c56f/pasted-text.txt"),
}

TEST_A = ["tests/models/test_person_a_66_cell_production_finalization_v0_1.py"]
TEST_B = [
    "tests/oracle/test_oracle_audit.py",
    "tests/probes/test_probe_harness.py",
    "tests/metrics/test_person_b_metrics.py",
    "tests/analysis/test_production_u1_u2_66_cell_v0_1.py",
]
TEST_C = [
    "tests/data/test_align.py",
    "tests/data/test_person_c_c7_5_mvp_handoff_v0_1.py",
    "tests/data/test_person_c_66_cell_strict_visibility_v0_1.py",
]
TEST_D = [
    "tests/baselines/test_66_cell_production_universe_v0_1.py",
    "tests/baselines/test_production_input_ingest.py",
    "tests/baselines/test_production_fold_contract_v0_1.py",
]
TEST_E = [
    "tests/experiments/test_immutable_registry_v2_contract.py",
    "tests/vision/test_phase3_formal_detector_evaluation.py",
    "tests/vision/test_person_e_phase3_step3_3_empirical_visibility_v0_1.py",
]


def requirement(
    role: str,
    step: str,
    text: str,
    status: str,
    implementation: list[str],
    evidence: list[str],
    tests: list[str],
    explanation: str,
    blocker: str | None = None,
) -> dict[str, object]:
    assert status in STATUS_VALUES
    return {
        "role": role,
        "manual_phase_or_step": step,
        "requirement": text,
        "status": status,
        "implementation_path": implementation,
        "evidence_path": evidence,
        "tests": tests,
        "explanation": explanation,
        "blocker_if_any": blocker,
    }


def role_a() -> list[dict[str, object]]:
    runtime = ["docs/status/person_a_phase2_runtime_record.md"]
    production = [
        "docs/status/person_a_66_cell_production_activation_index_v0_1/production_validation_receipt.json",
        "docs/status/person_a_66_cell_production_activation_index_v0_1/production_run_evidence.json",
    ]
    handoff = ["docs/status/person_a_66_cell_production_activation_index_v0_1/production_activation_handoff.json"]
    index = ["docs/status/person_a_66_cell_production_activation_index_v0_1/production_activation_index_manifest.json"]
    return [
        requirement("A", "A1 / Phases 0-2", "Model/source/checkpoint/VAE/environment identity", "PASS", ["src/mineocclude/models/mineworld_adapter.py", "src/mineocclude/models/phase2_evidence.py"], runtime, TEST_A, "The runtime record pins source, checkpoint, VAE, package, CUDA, PyTorch, and hardware identities with hashes."),
        requirement("A", "A2 / Phase 2", "Real MineWorld runtime and CUDA execution", "PASS", ["src/mineocclude/models/phase2_aws.py"], runtime + production, TEST_A, "The recorded production run used the real MineWorld runtime on an NVIDIA L4 with CUDA; this is not a synthetic CPU claim."),
        requirement("A", "A3 / Phases 1-3", "Strict input identity validation", "PASS", ["src/mineocclude/contracts/activation_v2.py", "src/mineocclude/models/_mineworld_adapter_wave4.py"], production, TEST_A, "Trajectory, frame, action, model, checkpoint, preprocessing, layer, and run identities are validated and fail closed."),
        requirement("A", "A4 / Phases 1-3", "Current truthful preprocessing identity", "PASS_SUPERSEDED_IMPLEMENTATION", ["src/mineocclude/models/_mineworld_adapter_wave5.py", "scripts/build_person_a_66_cell_preprocessed_media_v0_2.py"], production, TEST_A, "The historical preprocessing description was superseded by a hashed source-to-model-frame derivation and current wave-5 identity checks that describe the bytes actually consumed."),
        requirement("A", "A5 / Phases 2-3", "Official/action-authority behavior", "PASS", ["src/mineocclude/models/mineworld_adapter.py", "src/mineocclude/models/_mineworld_adapter_wave3.py"], production, TEST_A, "Teacher inputs are taken from the authoritative action stream and are not reconstructed from filenames or frame order."),
        requirement("A", "A6 / Phase 3", "FrameTokenMap / frame-action causal mapping", "PASS", ["src/mineocclude/contracts/activation_v2.py", "src/mineocclude/models/_mineworld_adapter_wave5.py"], production, TEST_A, "The current map explicitly binds model frame, teacher-forced action position, token slice, and causal orientation."),
        requirement("A", "A7 / Phase 3", "Teacher-forced execution", "PASS", ["src/mineocclude/models/mineworld_adapter.py", "src/mineocclude/models/_mineworld_adapter_wave4.py"], runtime + production, TEST_A, "Production evidence records teacher-forced forward execution over authoritative actions."),
        requirement("A", "A8 / Phase 3", "Runtime hook-site discovery / intended 20 layers", "PASS", ["src/mineocclude/activations/hooks.py", "src/mineocclude/models/mineworld_adapter.py"], production + index, TEST_A, "Runtime discovery selected and published exactly 20 intended layer sites."),
        requirement("A", "A9 / Phase 3", "Scoped hook cleanup", "PASS", ["src/mineocclude/activations/hooks.py"], production, TEST_A, "Hooks are scoped to an extraction context and removed after forward execution, including failure paths."),
        requirement("A", "A10 / Phase 3", "Exact visual-token selection", "PASS", ["src/mineocclude/activations/pool.py", "src/mineocclude/contracts/activation_v2.py"], production, TEST_A, "Pooling uses the explicit visual slice supplied by the frame-token map."),
        requirement("A", "A11 / Phase 3", "Visual-token mean pooling", "PASS", ["src/mineocclude/activations/pool.py"], production, TEST_A, "The selected visual token vectors are mean pooled without adding other token classes."),
        requirement("A", "A12 / Phase 3", "Action-token / neighboring-frame exclusion", "PASS", ["src/mineocclude/activations/pool.py", "src/mineocclude/models/_mineworld_adapter_wave5.py"], production, TEST_A, "Explicit token boundaries exclude action tokens and tokens belonging to adjacent frames."),
        requirement("A", "A13 / Phases 3-4", "Storage dtype/device behavior", "PASS", ["src/mineocclude/activations/store_v2.py", "src/mineocclude/activations/pool.py"], production, TEST_A, "Activations are detached and copied from GPU for immutable float32 storage; the runtime computation identity remains recorded."),
        requirement("A", "A14 / Phase 4", "Store-v2 immutable publication", "PASS", ["src/mineocclude/activations/store_v2.py", "src/mineocclude/contracts/activation_v2.py"], production + index, TEST_A, "Store-v2 publishes content-addressed chunks and a sealed index rather than overwriting accepted chunks."),
        requirement("A", "A15 / Phase 4", "Duplicate rejection and resumability", "PASS", ["src/mineocclude/activations/store_v2.py", "src/mineocclude/experiments/extraction_queue.py"], production, TEST_A, "Duplicate scientific keys fail closed while identical completed work can be resumed through the validated queue/store chain."),
        requirement("A", "A16 / Phase 4", "Activation-index identity/cardinality", "PASS", ["src/mineocclude/contracts/activation_v2.py", "scripts/build_person_a_66_cell_production_activation_index_v0_1.py"], index + production, TEST_A, "The index reconciles 2,468 unique frame keys x 20 layers = 49,360 activation rows across 66 trajectories."),
        requirement("A", "A17 / Phases 3-4", ">16-frame window rollover correctness", "PASS", ["src/mineocclude/models/_mineworld_adapter_wave5.py", "scripts/run_person_a_66_cell_production_extraction.py"], production, TEST_A, "The receipt includes a passing rollover-boundary audit for trajectories exceeding the model window."),
        requirement("A", "A18 / Phase 6", "66-trajectory production extraction", "PASS", ["scripts/run_person_a_66_cell_production_extraction.py"], production + index, TEST_A, "Existing production evidence validates all 66 trajectories, 2,468 frames, 20 layers, 1,320 chunks, and no missing or duplicate keys; extraction was not rerun for this audit."),
        requirement("A", "A19 / Phases 6-7", "A-to-B downstream activation handoff", "PASS", ["scripts/build_person_a_66_cell_production_activation_index_v0_1.py"], handoff + ["docs/status/integration/bd_production_input_readiness_v0_1/readiness_receipt.json"], TEST_A + ["tests/integration/test_bd_production_input_readiness_v0_1.py"], "B's readiness authority resolves the exact A run and activation-index hashes."),
        requirement("A", "A20 / Phases 0-7", "Exact production artifact reproducibility/provenance", "PASS", ["src/mineocclude/contracts/activation_v2.py", "src/mineocclude/activations/store_v2.py"], runtime + handoff + ["docs/status/person_a_66_cell_production_activation_index_v0_1/sha256_inventory.json"], TEST_A, "Run, code, source, model, VAE, preprocessing, trajectory, chunk, index, and handoff identities are sufficient to identify the exact existing production artifacts."),
    ]


def role_b() -> list[dict[str, object]]:
    oracle = [
        "docs/status/person_b_66_cell_oracle_target_v0_1/oracle_target_manifest.json",
        "docs/status/person_b_66_cell_oracle_target_v0_1/row_universe_receipt_v0_2.json",
    ]
    pre = [
        "docs/status/person_b_66_cell_preactivation_v0_1/fold_manifest.json",
        "docs/status/person_b_66_cell_preactivation_v0_1/fold_leakage_audit.json",
    ]
    result = [
        "docs/status/integration/bd_u1_u2_production_results_v0_1/execution_receipt.json",
        "docs/status/integration/bd_u1_u2_production_results_v0_1/fit_provenance.json",
        "docs/status/integration/bd_u1_u2_production_results_v0_1/oof_prediction_manifest.json",
    ]
    readiness = ["docs/status/integration/bd_production_input_readiness_v0_1/readiness_receipt.json"]
    common_analysis = ["src/mineocclude/analysis/production_u1_u2_66_cell_v0_1.py"]
    return [
        requirement("B", "B1 / Phases 0-1", "Target/unit/legal-information contract", "PASS", ["src/mineocclude/oracle/schema.py", "src/mineocclude/contracts/analysis_inputs.py"], oracle, TEST_B, "The oracle and analysis schemas declare target meanings, units, legal fields, validity, and provenance."),
        requirement("B", "B2 / Phase 1", "Hidden truth cannot enter primary oracle inputs", "PASS", ["src/mineocclude/oracle/audit.py", "src/mineocclude/oracle/schema.py"], oracle, TEST_B, "The primary oracle accepts the visible-history contract and rejects hidden-truth leakage."),
        requirement("B", "B3 / Phase 1", "Recursive oracle", "PASS", ["src/mineocclude/oracle/primary_scalar_kalman.py"], oracle, TEST_B, "The seeded scalar recursive estimator is implemented with explicit validity handling."),
        requirement("B", "B4 / Phase 1", "Independent closed-form oracle", "PASS", ["src/mineocclude/oracle/closed_form.py"], oracle, TEST_B, "An independently implemented closed-form reference is available for equivalence checks."),
        requirement("B", "B5 / Phase 1", "Seeded oracle equivalence/invariants", "PASS", ["src/mineocclude/oracle/audit.py", "src/mineocclude/oracle/closed_form.py"], oracle, TEST_B, "Known-answer and seeded invariants compare recursive and closed-form outputs and fail closed on disagreement."),
        requirement("B", "B6 / Phase 1", "Spread/log-spread validity handling", "PASS", ["src/mineocclude/oracle/targets.py", "src/mineocclude/oracle/schema.py"], oracle, TEST_B, "Invalid, nonpositive, or nonfinite spread values are represented as exclusions rather than silently logged."),
        requirement("B", "B7 / Phase 2", "Exact activation-target joins", "PASS", ["src/mineocclude/probes/join.py", "src/mineocclude/probes/bridge.py"], readiness + result, TEST_B, "The production join uses explicit trajectory/frame/layer identities and reports exact cardinalities."),
        requirement("B", "B8 / Phase 2", "Named deterministic inclusion/exclusion filters", "PASS", ["src/mineocclude/analysis/filters.py", "src/mineocclude/analysis/oracle_target_66_cell_v0_1.py"], oracle + readiness, TEST_B, "The 662 admitted and 1,806 excluded frame rows are assigned named deterministic reasons."),
        requirement("B", "B9 / Phase 2", "Five grouped outer folds", "PASS", ["src/mineocclude/probes/splits.py", "src/mineocclude/probes/production_fold_contract_v0_1.py"], pre + result, TEST_B, "The current authority contains five frozen grouped outer folds."),
        requirement("B", "B10 / Phase 2", "No layout leakage", "PASS", ["src/mineocclude/probes/splits.py", "src/mineocclude/analysis/layout_fold_plan.py"], pre, TEST_B, "The leakage audit verifies that held-out layouts do not appear in training for the corresponding fold."),
        requirement("B", "B11 / Phase 3", "Train-only activation scaling", "PASS", ["src/mineocclude/probes/ridge.py", *common_analysis], result, TEST_B, "Activation centering/scaling parameters are fit inside each outer training fold."),
        requirement("B", "B12 / Phase 3", "Training-only ridge alpha selection", "PASS", ["src/mineocclude/probes/ridge.py", *common_analysis], result, TEST_B, "Nested alpha selection is confined to outer-training data and is recorded for all 40 target/layer fits."),
        requirement("B", "B13 / Phase 3", "Out-of-fold prediction identity", "PASS", ["src/mineocclude/probes/ridge.py", *common_analysis], result, TEST_B, "The manifest binds every prediction to target, layer, trajectory, frame, fold, fit, and source identities; 12,440 OOF rows reconcile exactly."),
        requirement("B", "B14 / Phase 3", "Per-layer posterior-mean ridge", "PASS", ["src/mineocclude/probes/ridge.py", *common_analysis], result, TEST_B, "Twenty per-layer nested OOF posterior-mean ridge probes were fit and provenance-sealed."),
        requirement("B", "B15 / Phase 3", "Per-layer spread/log-spread ridge", "PASS", ["src/mineocclude/probes/ridge.py", *common_analysis], result, TEST_B, "Twenty per-layer nested OOF log-spread probes were fit with valid-target filtering."),
        requirement("B", "B16 / Phase 4", "Grouped shuffled-label implementation", "PASS", ["src/mineocclude/analysis/production_v2.py", *common_analysis], result, TEST_B, "Grouped null construction preserves group structure and uses the frozen row/fold authority."),
        requirement("B", "B17 / Phase 4", "U1 R-squared/MAE implementation", "PASS", ["src/mineocclude/metrics/u1_mean.py", *common_analysis], result, TEST_B, "U1 metrics operate on exact held-out predictions and include both R-squared and MAE."),
        requirement("B", "B18 / Phase 4", "U1 grouped permutation", "PASS_SUPERSEDED_IMPLEMENTATION", ["src/mineocclude/analysis/step4_1_final_comparison_v0_1.py", *common_analysis], ["docs/status/person_b_phase4_step4_1_final_comparison_contract_v0_1/final_comparison_contract.json", *result], TEST_B, "The earlier grouped refit-permutation proposal was legitimately replaced by the reviewed shared-layout paired sign-flip/maxT contract, preserving group-level inference and multiplicity control."),
        requirement("B", "B19 / Phase 4", "U2 time-controlled association", "PASS", ["src/mineocclude/metrics/u2_calibration.py", *common_analysis], result, TEST_B, "U2 association controls for the frozen time covariate on held-out rows."),
        requirement("B", "B20 / Phase 4", "Hierarchical layout-to-trajectory bootstrap", "PASS", ["src/mineocclude/metrics/resampling.py", *common_analysis], result, TEST_B, "Bootstrap resampling is hierarchical at layout then trajectory level rather than treating frames as IID."),
        requirement("B", "B21 / Phase 4", "U2 50/80/95 coverage/calibration", "PASS", ["src/mineocclude/metrics/u2_calibration.py", *common_analysis], result, TEST_B, "The implementation emits the requested 50%, 80%, and 95% interval coverage/calibration quantities."),
        requirement("B", "B22 / Phases 4-5", "Baseline-comparison consumption", "PASS", [*common_analysis, "src/mineocclude/baselines/production_input_ingest.py"], readiness + result + ["docs/status/person_d_66_cell_production_baselines_v0_1/d_to_b_production_baseline_handoff.json"], TEST_B + TEST_D, "The numerical comparator predictions consumed by B use D's current sealed production manifest and B's exact frozen rows/folds. This does not cure the separate positive-control gate defect in B23/D17."),
        requirement("B", "B23 / Phase 5", "Production U1/U2 result generation", "FAIL", ["scripts/build_bd_production_input_readiness_v0_1.py", *common_analysis], readiness + result + ["docs/status/person_b_phase6_step6_6_positive_control_v0_1/positive_control_decision.json", "docs/status/person_b_canonical_multilayout_positive_control_v0_1/completed_control_results.json"], ["tests/integration/test_bd_production_input_readiness_v0_1.py", "tests/analysis/test_production_u1_u2_66_cell_v0_1.py", "tests/baselines/test_positive_control_gate.py"], "The generator publishes READY_EXISTING/READY_EXISTING_CONSUMED from prediction-slot coverage without executing the manual's current-authority no-wall decoding gate. Inherited strongest R-squared values (0.338170676 and 0.390514057) are below 0.50. Therefore the package did not fail closed before scientific interpretation.", "RESULT_INVALIDATING: current U1/U2 result status depends on an unexecuted/unsatisfied no-wall positive-control gate."),
        requirement("B", "B24 / Phase 5", "U3 implementation and production-data availability", "BLOCKED_EXTERNAL_DATA", ["src/mineocclude/metrics/u3_dynamics.py", "src/mineocclude/analysis/step4_1_bounded_reveal_v0_1.py"], ["docs/status/person_c_66_cell_capture_authority_v0_1/u4_reveal_eligibility_finding.json", "docs/status/integration/bd_u1_u2_production_results_v0_1/final_verdict.json"], TEST_B, "U3 implementation is present, but the accepted production authority contains no valid terminal reveal events. The code is not marked failed for absent events.", "NO_VALID_TERMINAL_REVEAL_EVENTS in the current production data authority."),
        requirement("B", "B25 / Phase 6", "U4 implementation/scope status", "NOT_APPLICABLE_MVP_SCOPE", ["src/mineocclude/analysis/u4_event_selection_intervention_request_v1_0.py", "src/mineocclude/intervention/inject.py"], ["docs/status/person_b_66_cell_oracle_target_v0_1/u4_status.json"], TEST_B, "U4 contracts and analysis interfaces exist, but no causal intervention was performed in this MVP; no U4 scientific result is claimed.", "No U4 intervention execution is in the current MVP scope."),
    ]


def role_c() -> list[dict[str, object]]:
    handoff = [
        "docs/status/person_c_c7_mvp_handoff_v0_1/trajectories_mvp_manifest.json",
        "docs/status/person_c_c7_mvp_handoff_v0_1/validation_receipt.json",
    ]
    capture = [
        "docs/status/person_c_66_cell_capture_authority_v0_1/capture_package_manifest.json",
        "docs/status/person_c_66_cell_capture_authority_v0_1/coordinate_frame_authority.json",
    ]
    media = [
        "docs/status/person_c_66_cell_canonical_media_v0_1/canonical_media_manifest.json",
        "docs/status/person_c_66_cell_canonical_media_v0_1/media_validation_receipt.json",
    ]
    visibility = [
        "docs/status/person_c_66_cell_strict_visibility_v0_1/visibility_join_manifest.json",
        "docs/status/person_c_66_cell_strict_visibility_v0_1/closure_receipt.json",
    ]
    geometry = ["docs/status/person_c_geometry_authority_v0_2/accepted_geometry_authority.json"]
    return [
        requirement("C", "C1 / Phases C0-C1", "Environment/layout identity", "PASS", ["src/mineocclude/data/environment_lock.py", "src/mineocclude/data/layout_contract.py"], handoff + capture, TEST_C, "The accepted authority pins the environment and per-trajectory layout identity."),
        requirement("C", "C2 / Phases C0-C2", "Six-layout authority", "PASS", ["src/mineocclude/data/layout_contract.py", "src/mineocclude/data/collection_matrix.py"], handoff + geometry, TEST_C, "All and only layouts 01-06 are represented and validated."),
        requirement("C", "C3 / Phases C1-C2", "Condition/control identity", "PASS", ["src/mineocclude/contracts/trajectory.py", "src/mineocclude/data/collection_matrix.py"], handoff + ["docs/status/person_c_c7_mvp_handoff_v0_1/condition_count_table.json"], TEST_C, "Condition labels and core/no-wall/no-object/sentinel control cells are explicit immutable fields."),
        requirement("C", "C4 / Phases C1-C4", "Stable trajectory/frame/tick/action IDs", "PASS", ["src/mineocclude/contracts/trajectory.py", "src/mineocclude/contracts/identity.py"], handoff + media, TEST_C, "Stable IDs are carried as data fields throughout the accepted handoff."),
        requirement("C", "C5 / Phases C2-C4", "State/action/frame cardinality", "PASS", ["src/mineocclude/data/package_episode.py", "src/mineocclude/data/qa_report.py"], handoff + media, TEST_C, "Per-trajectory and global cardinalities reconcile in sealed validation receipts."),
        requirement("C", "C6 / Phases C3-C4", "No row-order identity assumptions", "PASS", ["src/mineocclude/data/align.py", "src/mineocclude/contracts/identity.py"], handoff, TEST_C, "Joins use explicit composite identities; shuffled ordering is not a scientific key."),
        requirement("C", "C7 / Phase C3", "No nearest-time alignment repair", "PASS", ["src/mineocclude/data/align.py"], handoff, TEST_C, "Alignment is exact and rejects missing/ambiguous identities; there is no nearest-time repair path."),
        requirement("C", "C8 / Phase C3", "Action/frame causal orientation", "PASS", ["src/mineocclude/data/align.py", "src/mineocclude/contracts/trajectory.py"], handoff + capture, TEST_C, "The authority explicitly declares which action precedes/causes each captured model frame."),
        requirement("C", "C9 / Phases C3-C4", "Frame-map authority", "PASS", ["src/mineocclude/data/package_episode.py", "src/mineocclude/contracts/trajectory.py"], handoff + media, TEST_C, "The canonical frame index is an explicit authority with hashes and exact keys."),
        requirement("C", "C10 / Phases C4-C7", "Model-frame identity", "PASS", ["src/mineocclude/data/preprocess.py", "src/mineocclude/contracts/trajectory.py"], media, TEST_C, "The model-frame identity is distinct from and linked to the source capture identity."),
        requirement("C", "C11 / Phases C4-C7", "Source-to-preprocessed frame provenance", "PASS", ["src/mineocclude/data/preprocess.py", "scripts/build_person_c_66_cell_canonical_media_v0_1.py"], media + ["docs/status/person_c_66_cell_canonical_media_v0_1/scientific_identity_unchanged_receipt.json"], TEST_C, "Every model frame is bound to source bytes and a deterministic preprocessing derivation."),
        requirement("C", "C12 / Phase C7", "Accepted/excluded trajectory authority", "PASS", ["src/mineocclude/data/qa_report.py", "scripts/build_person_c_66_cell_capture_authority_v0_1.py"], handoff + ["docs/status/person_c_c7_mvp_handoff_v0_1/accepted_excluded_ledger.json"], TEST_C, "The writer-of-record ledger declares 66 accepted and zero excluded trajectories for the production authority."),
        requirement("C", "C13 / Phases C5-C7", "Geometry/homography input authority", "PASS", ["src/mineocclude/data/layout_contract.py", "src/mineocclude/data/visibility.py"], geometry + capture, TEST_C, "The accepted geometry package pins per-layout world geometry and the homography-facing coordinate contract."),
        requirement("C", "C14 / Phases C5-C7", "Visibility ownership and preserved raw components", "PASS", ["src/mineocclude/data/visibility.py", "src/mineocclude/data/visibility_join.py"], visibility, TEST_C, "C owns geometric visibility and the final join while preserving raw geometric and E empirical components without allowing E to overwrite C."),
        requirement("C", "C15 / Phases C0-C7", "Coordinate-frame/world-axis convention", "PASS", ["src/mineocclude/data/layout_contract.py", "src/mineocclude/analysis/coordinates_v2.py"], capture + geometry, TEST_C, "World axes, wall axis, origin, pose, units, and coordinate transforms are explicit and hashed."),
        requirement("C", "C16 / Phases C4-C7", "Oracle-facing state fields/units", "PASS", ["src/mineocclude/contracts/trajectory.py", "src/mineocclude/analysis/oracle_target_66_cell_v0_1.py"], handoff + ["docs/status/person_b_66_cell_oracle_target_v0_1/oracle_target_manifest.json"], TEST_C + TEST_B, "The state handoff names fields/units consumed by B and B binds the exact C authority hashes."),
        requirement("C", "C17 / Phase C7", "66-cell accepted production manifest", "PASS", ["scripts/build_person_c_66_cell_capture_authority_v0_1.py"], handoff, TEST_C, "The final accepted manifest contains exactly the planned 48 core plus 18 control trajectories."),
        requirement("C", "C18 / Phase C7", "2,468 production model-frame universe", "PASS", ["scripts/build_person_c_66_cell_canonical_media_v0_1.py"], media + handoff, TEST_C, "The sealed canonical frame universe contains 2,468 unique production model-frame keys."),
        requirement("C", "C19 / Phase C7", "C-to-A and C-to-B handoff integrity", "PASS", ["src/mineocclude/data/package_episode.py", "src/mineocclude/analysis/capture_intake.py"], ["docs/status/person_c_c7_mvp_handoff_v0_1/consumer_handoffs/person_a_handoff_receipt.json", "docs/status/person_c_c7_mvp_handoff_v0_1/consumer_handoffs/person_b_handoff_receipt.json", "docs/status/person_c_66_cell_capture_authority_v0_1/c_to_b_successor_handoff.json"], TEST_C + TEST_A + TEST_B, "A and B resolve the same accepted trajectory/frame identities and authority hashes."),
        requirement("C", "C20 / Historical architecture", "Superseded historical C implementation requirements", "PASS_SUPERSEDED_IMPLEMENTATION", ["src/mineocclude/data/capture_contract.py", "src/mineocclude/data/package_episode.py", "src/mineocclude/contracts/trajectory.py"], handoff + capture + media, TEST_C, "The manual's historical Java/Fabric capture architecture and proposed filenames were superseded by the accepted capture-authority, canonical-media, and typed handoff path. The replacement preserves the same identity, causality, geometry, and fail-closed scientific interfaces."),
    ]


def role_d() -> list[dict[str, object]]:
    prod = [
        "docs/status/person_d_66_cell_production_baselines_v0_1/authority_verification_receipt.json",
        "docs/status/person_d_66_cell_production_baselines_v0_1/execution_receipt.json",
        "docs/status/person_d_66_cell_production_baselines_v0_1/prediction_manifest.json",
    ]
    handoff = ["docs/status/person_d_66_cell_production_baselines_v0_1/d_to_b_production_baseline_handoff.json"]
    specs = [
        ("D1 / Phases 0-1", "BaselineSpec/prediction schema", "PASS", ["src/mineocclude/baselines/spec.py", "src/mineocclude/baselines/interface.py"], "Typed specs and prediction rows carry family, target, row, fold, fit, and provenance identities."),
        ("D2 / Phase 1", "Legal-input firewall", "PASS", ["src/mineocclude/baselines/firewall.py"], "The firewall admits only declared legal features per family and rejects oracle/hidden channels."),
        ("D3 / Phases 1-2", "Grouped-fold enforcement", "PASS", ["src/mineocclude/baselines/production_fold_contract_v0_1.py"], "Production baseline execution consumes B's grouped fold authority and rejects unknown rows/folds."),
        ("D4 / Phases 1-3", "Common fit/predict/evaluate harness", "PASS", ["src/mineocclude/baselines/harness.py", "src/mineocclude/baselines/eight_family_runner.py"], "All current baseline families use the common fit/predict/export harness."),
        ("D5 / Phase 2", "Grouped shuffled-label floor", "PASS", ["src/mineocclude/baselines/shuffled.py", "src/mineocclude/baselines/grouped_nulls_v0_1.py"], "The null permutes at the declared group level and is labeled as a floor/null."),
        ("D6 / Phase 2", "Explicit donor/frame identity in current grouped shuffle", "PASS", ["src/mineocclude/baselines/shuffled.py", "src/mineocclude/baselines/grouped_nulls_v0_1.py"], "The repaired implementation records donor group/frame identity rather than obscuring provenance."),
        ("D7 / Phase 2", "Last-seen baseline", "PASS", ["src/mineocclude/baselines/last_seen.py"], "Last-seen uses only legal visible history and emits explicit missingness."),
        ("D8 / Phase 2", "Constant-velocity baseline", "PASS", ["src/mineocclude/baselines/constant_velocity.py"], "Constant velocity is fit/evaluated within the common legal-input/fold harness."),
        ("D9 / Phase 2", "Time-only baseline", "PASS", ["src/mineocclude/baselines/time_only.py"], "Time-only consumes the frozen legal time feature and training folds only."),
        ("D10 / Phase 2", "Explicit-feature baseline", "PASS", ["src/mineocclude/baselines/explicit_feature.py"], "The explicit feature family uses its declared legal inputs under the common harness."),
        ("D11 / Phase 2", "Raw-pixel baseline with train-only preprocessing", "PASS", ["src/mineocclude/baselines/raw_pixel.py"], "Raw-pixel preprocessing is learned on outer-training data and applied to held-out rows."),
        ("D12 / Phase 2", "Visible-history spread baseline", "PASS", ["src/mineocclude/baselines/visible_history_q.py"], "The spread predictor uses only visible-history information and preserves invalid/missing rows."),
        ("D13 / Phases 1-3", "Conflicting fold assignments fail closed", "PASS", ["src/mineocclude/baselines/production_input_ingest.py", "src/mineocclude/baselines/production_fold_contract_v0_1.py"], "Conflicting row-to-fold assignments are rejected; historical permissive behavior is repaired and covered by current tests."),
        ("D14 / Phase 2", "Known-q analytic reference labeled as ceiling/reference", "PASS", ["src/mineocclude/baselines/known_q_analytic.py"], "Known-q is explicitly labeled a privileged analytic reference/ceiling, not a legal deployable baseline."),
        ("D15 / Phase 3", "Split-integrity audit", "PASS", ["src/mineocclude/baselines/leakage.py", "src/mineocclude/baselines/production_fold_contract_v0_1.py"], "The authority receipt verifies row/fold/layout integrity before fit."),
        ("D16 / Phase 3", "Metadata leakage audit", "PASS", ["src/mineocclude/baselines/leakage.py", "src/mineocclude/baselines/firewall.py"], "Declared metadata are screened against forbidden target/oracle/hidden inputs."),
    ]
    records = [requirement("D", step, text, status, impl, prod, TEST_D, explanation) for step, text, status, impl, explanation in specs]
    records.extend([
        requirement("D", "D17 / Step 4.3", "No-wall positive control", "FAIL", ["src/mineocclude/baselines/positive_control_gate.py", "scripts/build_bd_production_input_readiness_v0_1.py"], [*prod, "docs/status/integration/bd_production_input_readiness_v0_1/readiness_receipt.json", "docs/status/person_b_phase6_step6_6_positive_control_v0_1/positive_control_decision.json", "docs/status/person_b_canonical_multilayout_positive_control_v0_1/completed_control_results.json"], [*TEST_D, "tests/baselines/test_positive_control_gate.py", "tests/integration/test_bd_production_input_readiness_v0_1.py"], "The correct R-squared >= 0.50 and bootstrap-CI-above-zero gate exists in positive_control_gate.py, but it was not run on current 66-cell no-wall activations. Readiness instead treats complete prediction slots as READY_EXISTING. The two inherited strongest global R-squared values are 0.338170676 and 0.390514057, both below the manual threshold.", "RESULT_INVALIDATING: no current-authority passed no-wall positive-control decision exists."),
        requirement("D", "D18 / Step 4.4", "Occluder-only/no-object control applicability/current status", "PASS", ["src/mineocclude/baselines/production_universe_66_cell_v0_1.py", "src/mineocclude/baselines/missingness.py"], prod + ["docs/status/integration/bd_production_input_readiness_v0_1/readiness_receipt.json"], TEST_D, "The no-object control remains in the 66-cell capture authority but its 360 frames are explicitly excluded from B/D target-bearing execution because no oracle target is applicable; D does not silently reinstate them."),
        requirement("D", "D19 / Phases 2-4", "Missingness/exclusion handling", "PASS", ["src/mineocclude/baselines/missingness.py", "src/mineocclude/baselines/missingness_audit_v0_1.py"], prod, TEST_D, "Admitted/excluded/not-applicable rows reconcile exactly and missing values are not imputed across scientific identities."),
        requirement("D", "D20 / Production", "Production baselines use exactly B's frozen rows/folds", "PASS", ["src/mineocclude/baselines/production_input_ingest.py", "scripts/run_person_d_66_cell_production_baselines.py"], prod + handoff, TEST_D, "Eight families produce 10,592 prediction rows over exactly B's 662 admitted rows, targets, and five frozen folds."),
        requirement("D", "D21 / Production handoff", "Production comparator artifacts used by U1/U2 are current and valid", "FAIL", ["scripts/build_bd_production_input_readiness_v0_1.py", "src/mineocclude/analysis/production_u1_u2_66_cell_v0_1.py"], handoff + ["docs/status/integration/bd_production_input_readiness_v0_1/readiness_receipt.json", "docs/status/integration/bd_u1_u2_production_results_v0_1/execution_receipt.json"], [*TEST_D, "tests/integration/test_bd_production_input_readiness_v0_1.py", "tests/analysis/test_production_u1_u2_66_cell_v0_1.py"], "The ordinary comparator prediction rows are current and row/fold exact, but the comparator-control bundle consumed by U1/U2 claims the no-wall control is ready without a valid current-authority gate decision. Therefore the complete comparator authority used for interpretation is not valid.", "RESULT_INVALIDATING: B consumed a coverage surrogate in place of D's required positive-control gate."),
    ])
    return records


def role_e() -> list[dict[str, object]]:
    registry = [
        "docs/status/person_e_phase4_step4_1_registry_v2_closure_v0_1/immutable_registry_v2.json",
        "docs/status/person_e_phase4_step4_1_registry_v2_closure_v0_1/validation_receipt.json",
    ]
    detector = ["docs/status/person_e_phase3_step3_1_formal_evaluation_v0_1/formal_evaluation_report.json"]
    homography = ["docs/status/person_e_phase3_step3_2_homography_closure_v0_1/step3_2_closure_report.json"]
    terminal = ["docs/status/person_e_terminal_status_v0_1/terminal_status.json"]
    operations = [
        "docs/status/person_e_phase7_terminal_v0_1/operating_handoff.json",
        "docs/status/person_e_phase7_terminal_v0_1/second_operator_receipt.json",
        "docs/status/person_e_phase7_terminal_v0_1/validation_receipt.json",
    ]
    return [
        requirement("E", "E1 / Phase 0", "Shared ownership/interface map", "PASS", ["src/mineocclude/experiments/mvp_matrix.py", "src/mineocclude/experiments/stage_graph.py"], terminal, TEST_E, "Ownership and writer-of-record boundaries across A-E are explicit."),
        requirement("E", "E2 / Phases 1-2", "Immutable run/artifact identity", "PASS", ["src/mineocclude/experiments/registry.py", "src/mineocclude/experiments/mvp_lineage.py"], registry, TEST_E, "Registry records use immutable run/artifact IDs and content hashes."),
        requirement("E", "E3 / Phases 1-2", "Direct-input lineage", "PASS", ["src/mineocclude/experiments/mvp_lineage.py", "src/mineocclude/experiments/registry.py"], registry, TEST_E, "Direct input IDs/hashes are required and queryable in registered records."),
        requirement("E", "E4 / Phases 1-2", "Fail-closed registry behavior", "PASS", ["src/mineocclude/experiments/registry.py"], registry, TEST_E, "Duplicate/conflicting IDs, missing inputs, and hash mismatches fail closed."),
        requirement("E", "E5 / Phase 3", "Detector implementation/config validation", "PASS", ["src/mineocclude/vision/magenta.py", "src/mineocclude/vision/config.py"], detector, TEST_E, "The frozen detector and config schema validate channel/threshold/morphology inputs."),
        requirement("E", "E6 / Phase 3", "Detector calibration/test separation", "PASS", ["src/mineocclude/vision/calibration.py", "src/mineocclude/vision/phase3_detector_candidate.py"], detector, TEST_E, "Calibration frames and held-out evaluation frames are distinct and the report records no post-test tuning."),
        requirement("E", "E7 / Phase 3", "Detector held-out performance evidence", "PASS", ["src/mineocclude/vision/phase3_detector_candidate.py", "src/mineocclude/vision/detection_records.py"], detector, TEST_E, "Formal held-out evidence covers 48 frames (24 positive/24 negative) with precision=1.0 and recall=1.0 under the frozen detector."),
        requirement("E", "E8 / Phase 3", "Homography implementation", "PASS", ["src/mineocclude/vision/homography.py"], homography, TEST_E, "Homography estimation/application and failure validation are implemented."),
        requirement("E", "E9 / Phase 3", "Multi-layout homography/localization evidence", "PASS", ["src/mineocclude/vision/homography.py", "src/mineocclude/vision/measurement.py"], homography, TEST_E, "Real closure evidence covers all six layouts with median wall-axis error 0.093418 and p95 0.287204 in the declared units."),
        requirement("E", "E10 / Phase 3", "Coordinate-resolution/pose applicability", "PASS", ["src/mineocclude/vision/homography.py", "src/mineocclude/vision/config.py"], homography, TEST_E, "Pose, layout, resolution, and coordinate convention are bound and mismatches fail closed."),
        requirement("E", "E11 / Phases 3-4", "Empirical visibility output preserves C authority", "PASS", ["src/mineocclude/operations/person_e_66_cell_empirical_visibility.py", "src/mineocclude/vision/measurement.py"], ["docs/status/person_c_66_cell_strict_visibility_v0_1/e_handoff_intake_receipt.json", "docs/status/person_c_66_cell_strict_visibility_v0_1/visibility_join_manifest.json"], TEST_E, "E supplies an empirical channel keyed to C identities; C remains the final visibility writer and raw components remain preserved."),
        requirement("E", "E12 / Phases 2-6", "Registry integration across real result-bearing workstreams", "UNVERIFIED", ["src/mineocclude/experiments/registry.py", "src/mineocclude/experiments/mvp_lineage.py"], registry, TEST_E, "Registry-v2 proves earlier result-bearing integration, but no current registry import/closure objectively includes the final 66-cell A activation run and the current B/D U1/U2 result packages."),
        requirement("E", "E13 / Phases 2-7", "Fast fail-closed CPU checks", "PASS", ["src/mineocclude/experiments/mvp_lineage.py", "src/mineocclude/operations/checkpoint_evidence.py"], terminal + operations, TEST_E, "CPU validators check hashes, schemas, identities, cardinalities, and forbidden synthetic/superseded status without executing costly production work."),
        requirement("E", "E14 / Phases 4-6", "Artifact/result input templates", "PASS", ["src/mineocclude/experiments/figure_inputs.py", "src/mineocclude/experiments/checkpoint.py"], terminal, TEST_E, "Typed checkpoint and figure-input builders/templates exist with lineage fields."),
        requirement("E", "E15 / Phase 6", "Production activation/result provenance traceability", "UNVERIFIED", ["src/mineocclude/experiments/registry.py", "src/mineocclude/experiments/mvp_lineage.py"], ["docs/status/person_a_66_cell_production_activation_index_v0_1/production_activation_handoff.json", "docs/status/person_a_66_cell_production_activation_index_v0_1/sha256_inventory.json", *registry], TEST_E, "A's final activation package is self-sealed and exactly traceable, but E's current central registry does not contain an objective import/acceptance record for that final production run."),
        requirement("E", "E16 / Phase 6", "U1/U2 result-package traceability", "UNVERIFIED", ["src/mineocclude/experiments/registry.py", "src/mineocclude/experiments/figure_inputs.py"], ["docs/status/integration/bd_u1_u2_production_results_v0_1/sha256_inventory.json", "docs/status/integration/bd_u1_u2_production_results_v0_1/fit_provenance.json", *registry], TEST_E, "The U1/U2 package is internally hash-sealed and traces its fits/inputs, but no E registry import/query receipt binds this final package as a current result-bearing record."),
        requirement("E", "E17 / Phases 2-7", "Superseded/synthetic evidence cannot masquerade as production", "PASS", ["src/mineocclude/experiments/registry.py", "src/mineocclude/experiments/mvp_lineage.py"], registry + terminal, TEST_E, "Evidence classes and supersession fields keep synthetic/rehearsal artifacts from satisfying production gates."),
        requirement("E", "E18 / Phases 4-6", "U4 measurement implementation versus U4 execution", "NOT_APPLICABLE_MVP_SCOPE", ["src/mineocclude/vision/measurement.py", "scripts/measure_u4.py", "scripts/compose_u4_evidence.py"], terminal, TEST_E, "U4 measurement/composition code exists and terminal status truthfully reports zero real U4 rollouts. No causal U4 result is claimed.", "No U4 intervention was executed in the current MVP."),
        requirement("E", "E19 / Phases 5-6", "Figure/checkpoint implementation status", "UNVERIFIED", ["src/mineocclude/experiments/figure_inputs.py", "scripts/render_figure_svg.py", "src/mineocclude/experiments/checkpoint.py"], terminal + operations, TEST_E, "Figure/checkpoint implementations and historical/synthetic validations exist, but no current result-bearing checkpoint/figure package was issued after the final 66-cell U1/U2 publication."),
        requirement("E", "E20 / Phase 7", "Operational handoff/reproduction status", "PASS", ["src/mineocclude/operations/handoff.py", "src/mineocclude/operations/clean_reproduction.py"], operations, TEST_E, "Runbooks, exact inputs, second-operator validation, and a clean-reproduction plan are sealed. The evidence correctly does not claim a new real U4 reproduction."),
    ]


def status_counts(records: list[dict[str, object]]) -> dict[str, int]:
    raw = Counter(str(record["status"]) for record in records)
    return {
        "pass": raw["PASS"] + raw["PASS_SUPERSEDED_IMPLEMENTATION"],
        "pass_direct": raw["PASS"],
        "pass_superseded_implementation": raw["PASS_SUPERSEDED_IMPLEMENTATION"],
        "fail": raw["FAIL"],
        "unverified": raw["UNVERIFIED"],
        "blocked_external_data": raw["BLOCKED_EXTERNAL_DATA"],
        "not_applicable_mvp_scope": raw["NOT_APPLICABLE_MVP_SCOPE"],
        "blocked_or_na": raw["BLOCKED_EXTERNAL_DATA"] + raw["NOT_APPLICABLE_MVP_SCOPE"],
        "total": len(records),
    }


def role_document(role: str, verdict: str, records: list[dict[str, object]]) -> dict[str, object]:
    assert verdict in VERDICT_VALUES
    return {
        "schema_version": "mvp-role-implementation-audit-v0.1",
        "branch": BRANCH,
        "audited_head": HEAD,
        "role": role,
        "verdict": verdict,
        "status_counts": status_counts(records),
        "requirements": records,
    }


def cross_role() -> list[dict[str, object]]:
    return [
        requirement("C->A", "Cross-role C-to-A", "Same authoritative trajectory/frame/model-media identity and no duplicate writer", "PASS", ["src/mineocclude/contracts/trajectory.py", "src/mineocclude/contracts/activation_v2.py"], ["docs/status/person_c_66_cell_canonical_media_v0_1/c_to_a_media_handoff.json", "docs/status/person_a_66_cell_production_activation_index_v0_1/production_activation_handoff.json"], TEST_C + TEST_A, "A's production index resolves C's exact 66-trajectory/2,468-frame authority and preprocessing lineage."),
        requirement("A->B", "Cross-role A-to-B", "Exact activation identity/cardinality/schema handoff", "PASS", ["src/mineocclude/probes/join.py", "src/mineocclude/contracts/activation_v2.py"], ["docs/status/person_a_66_cell_production_activation_index_v0_1/production_activation_handoff.json", "docs/status/integration/bd_production_input_readiness_v0_1/readiness_receipt.json"], TEST_A + TEST_B, "B resolves A's exact run/index hashes and joins 49,360 activation rows by scientific identity."),
        requirement("B<->D", "Cross-role B-and-D", "Shared rows/folds/comparator authority including required controls", "FAIL", ["src/mineocclude/baselines/production_input_ingest.py", "scripts/build_bd_production_input_readiness_v0_1.py", "src/mineocclude/analysis/production_u1_u2_66_cell_v0_1.py"], ["docs/status/person_d_66_cell_production_baselines_v0_1/d_to_b_production_baseline_handoff.json", "docs/status/integration/bd_production_input_readiness_v0_1/readiness_receipt.json"], TEST_B + TEST_D, "Rows, folds, and ordinary comparator predictions match, but the integration substitutes no-wall prediction-slot coverage for D's required decoded-state positive-control decision.", "RESULT_INVALIDATING: no passed current-authority no-wall positive-control gate was handed from D to B."),
        requirement("C->B", "Cross-role C-to-B", "Exact geometry/state/visibility/oracle identity handoff", "PASS", ["src/mineocclude/analysis/capture_intake.py", "src/mineocclude/analysis/oracle_target_66_cell_v0_1.py"], ["docs/status/person_c_66_cell_capture_authority_v0_1/c_to_b_successor_handoff.json", "docs/status/person_c_66_cell_strict_visibility_v0_1/c_to_b_oracle_handoff.json", "docs/status/person_b_66_cell_oracle_target_v0_1/oracle_target_manifest.json"], TEST_C + TEST_B, "B's oracle target authority binds C's exact state, geometry, coordinate, frame, and final visibility hashes."),
        requirement("C<->E", "Cross-role C-and-E", "C visibility authority preserved around E empirical measurement", "PASS", ["src/mineocclude/operations/person_e_66_cell_empirical_visibility.py", "src/mineocclude/data/visibility_join.py"], ["docs/status/person_c_66_cell_strict_visibility_v0_1/e_handoff_intake_receipt.json", "docs/status/person_c_66_cell_strict_visibility_v0_1/visibility_join_manifest.json"], TEST_C + TEST_E, "E's empirical channel is keyed to C's universe, and C retains the final writer-of-record role with raw channels preserved."),
        requirement("A<->E", "Cross-role A-and-E", "Final production activation registered/accepted in current provenance authority", "UNVERIFIED", ["src/mineocclude/experiments/registry.py", "src/mineocclude/contracts/activation_v2.py"], ["docs/status/person_a_66_cell_production_activation_index_v0_1/sha256_inventory.json", "docs/status/person_e_phase4_step4_1_registry_v2_closure_v0_1/immutable_registry_v2.json"], TEST_A + TEST_E, "A's package is self-sealed, but E has not issued a registry-v2 import/acceptance receipt for this final 66-cell activation run."),
        requirement("B->E", "Cross-role B-to-E", "Current U1/U2 result/figure provenance registration", "UNVERIFIED", ["src/mineocclude/experiments/registry.py", "src/mineocclude/experiments/figure_inputs.py"], ["docs/status/integration/bd_u1_u2_production_results_v0_1/sha256_inventory.json", "docs/status/person_e_phase4_step4_1_registry_v2_closure_v0_1/immutable_registry_v2.json"], TEST_B + TEST_E, "The current U1/U2 output self-traces, but no current E registry/figure-input closure imports it; moreover its positive-control status must be invalidated before result-bearing registration."),
    ]


ENVIRONMENT_CLASSNAMES = {
    "tests.analysis.test_person_b_phase3_step3_3_final_signoff_v0_1",
    "tests.analysis.test_person_b_week1_closeout_v0_1",
    "tests.baselines.test_phase6to8_completion_package",
    "tests.data.test_build_dataset",
    "tests.data.test_package_episode",
    "tests.data.test_person_c_66_cell_canonical_media_v0_1",
    "tests.data.test_person_c_66_cell_capture_authority_v0_1",
    "tests.data.test_person_c_66_cell_strict_visibility_v0_1",
    "tests.experiments.test_person_e_a_activation_provenance_acceptance_v0_1",
    "tests.experiments.test_person_e_a_multilayout_activation_provenance_acceptance_v0_1",
    "tests.models.test_mineworld_adapter_wave2",
    "tests.models.test_mineworld_adapter_wave3",
    "tests.models.test_mineworld_adapter_wave4",
    "tests.models.test_phase3_certification_inputs",
    "tests.test_parquet_dependency_authority",
    "tests.test_person_c_c1_5_first_success_second_operator",
    "tests.test_person_c_c1_5_second_operator_attempt_02",
    "tests.test_person_c_c6a_completion",
    "tests.test_person_c_c6a_live_log",
    "tests.test_person_c_e_refit_calibration_attempt_02",
    "tests.test_person_c_e_refit_calibration_attempt_02_chronology_parser",
    "tests.test_person_c_e_refit_calibration_attempt_02_finalizer_hashtable",
    "tests.test_person_c_e_refit_calibration_attempt_02_live_hash",
    "tests.test_person_c_e_refit_calibration_attempt_02_mutable_log_finalizer",
    "tests.test_person_c_e_refit_calibration_attempt_02_preflight_receipt_recovery",
    "tests.test_server_properties_semantic_authority",
    "tests.vision.test_attempt_02_refit_finalize",
    "tests.vision.test_attempt_02_refit_finalize_v0_2",
    "tests.vision.test_layout_04_06_annotation_repair",
    "tests.vision.test_person_e_66_cell_empirical_visibility_v0_1",
    "tests.vision.test_phase3_detector_candidate",
}


def parse_failure_audit(junit_path: Path) -> tuple[list[dict[str, object]], Counter[str]]:
    root = ET.parse(junit_path).getroot()
    records: list[dict[str, object]] = []
    counts: Counter[str] = Counter()
    for case in root.findall(".//testcase"):
        child = case.find("failure")
        outcome = "failure"
        if child is None:
            child = case.find("error")
            outcome = "error"
        if child is None:
            continue
        classname = case.get("classname", "")
        if any(classname == module or classname.startswith(module + ".") for module in ENVIRONMENT_CLASSNAMES):
            category = "ENVIRONMENT_ONLY"
            reason = "Requires an unavailable external/Windows/runtime input or an exact host dependency; current sealed evidence is audited separately."
        else:
            category = "STALE_HISTORICAL_ASSUMPTION"
            reason = "Asserts an older branch name, object/hash, byte receipt, or superseded authority rather than the current integration authority."
        counts[category] += 1
        records.append({
            "node_id": f"{classname}::{case.get('name', '')}",
            "outcome": outcome,
            "classification": category,
            "reason": reason,
            "message_excerpt": (child.get("message", "") or "")[:500],
        })
    return records, counts


def test_document(junit_path: Path) -> dict[str, object]:
    records, junit_counts = parse_failure_audit(junit_path)
    if len(records) != 172 or junit_counts != Counter({"ENVIRONMENT_ONLY": 139, "STALE_HISTORICAL_ASSUMPTION": 33}):
        raise RuntimeError(f"Unexpected last-failure JUnit classification: {len(records)=}, {junit_counts=}")
    classification_counts = {
        "GENUINE_IMPLEMENTATION_FAILURE": 0,
        "ENVIRONMENT_ONLY": 198,
        "STALE_HISTORICAL_ASSUMPTION": 33,
        "EXPECTED_NEGATIVE_FIXTURE": 0,
        "OUT_OF_SCOPE": 0,
    }
    return {
        "schema_version": "mvp-role-implementation-test-audit-v0.1",
        "branch": BRANCH,
        "audited_head": HEAD,
        "commands": [
            {
                "command": "python -m pytest -q",
                "result": "181 failed, 3330 passed, 29 skipped, 50 errors, 7415 subtests passed",
                "elapsed_seconds": 275.53,
                "failing_or_error_count": 231,
            },
            {
                "command": "python -m pytest --lf -q --tb=no --junitxml=/tmp/mvp-role-audit-pytest-failures.xml",
                "result": "122 failed, 528 deselected, 50 errors",
                "elapsed_seconds": 18.20,
                "junit_case_count": 172,
            },
            {
                "command": "python -m pytest -q tests/models/test_person_a_66_cell_production_finalization_v0_1.py tests/integration/test_bd_production_input_readiness_v0_1.py tests/analysis/test_production_u1_u2_66_cell_v0_1.py tests/baselines/test_66_cell_production_universe_v0_1.py tests/baselines/test_production_input_ingest.py tests/baselines/test_production_fold_contract_v0_1.py tests/baselines/test_positive_control_gate.py tests/vision/test_phase3_formal_detector_evaluation.py tests/vision/test_person_e_phase3_step3_3_empirical_visibility_v0_1.py",
                "result": "157 passed, 1 skipped, 48 subtests passed",
                "elapsed_seconds": 3.04,
                "failing_or_error_count": 0,
            },
            {
                "command": "./gradlew test --offline",
                "result": "NOT_EXECUTED_ENVIRONMENT_ONLY: JAVA_HOME/java unavailable",
                "failing_or_error_count": 0,
                "classification": "ENVIRONMENT_ONLY",
            },
        ],
        "classification_counts": classification_counts,
        "accounting": {
            "full_suite_failures": 181,
            "full_suite_errors": 50,
            "full_suite_failure_or_error_total": 231,
            "junit_serialized_failure_or_error_cases": 172,
            "unittest_subtest_delta": 59,
            "junit_environment_only": 139,
            "subtest_delta_environment_only": 59,
            "environment_only_total": 198,
            "stale_historical_total": 33,
            "sum_of_classifications": sum(classification_counts.values()),
        },
        "subtest_delta_classification": {
            "selector": "The 59 full-run failure instances not serialized as independent JUnit testcase nodes by unittest subtest reporting.",
            "count": 59,
            "classification": "ENVIRONMENT_ONLY",
            "reason": "The full output attributes these subtest instances to the same missing external Windows capture/media/detector-replay prerequisites; they do not contradict sealed current production receipts.",
        },
        "junit_failure_records": records,
        "audit_interpretation": {
            "current_authority_focused_suite": "PASS",
            "positive_control_defect_detected_by_failing_test": False,
            "coverage_gap": "The green positive-control unit test validates gate logic in isolation, while readiness tests validate the READY_EXISTING label. No test requires readiness to execute/bind the gate decision, which permits the audited result-invalidating substitution.",
            "tests_weakened_or_modified": False,
        },
    }


def manual_sources() -> dict[str, object]:
    result: dict[str, object] = {}
    for name, path in MANUAL_ATTACHMENTS.items():
        payload = path.read_bytes()
        result[name] = {
            "path": str(path),
            "sha256": hashlib.sha256(payload).hexdigest(),
            "size_bytes": len(payload),
        }
    return result


def validate_records(documents: dict[str, dict[str, object]]) -> None:
    expected = {"A": 20, "B": 25, "C": 20, "D": 21, "E": 20}
    for role, expected_count in expected.items():
        records = documents[role]["requirements"]
        assert isinstance(records, list) and len(records) == expected_count
        for record in records:
            assert isinstance(record, dict) and set(record) == REQUIRED_FIELDS
            assert record["status"] in STATUS_VALUES
    expected_counts = {
        "A": {"pass": 20, "fail": 0, "unverified": 0, "blocked_or_na": 0},
        "B": {"pass": 22, "fail": 1, "unverified": 0, "blocked_or_na": 2},
        "C": {"pass": 20, "fail": 0, "unverified": 0, "blocked_or_na": 0},
        "D": {"pass": 19, "fail": 2, "unverified": 0, "blocked_or_na": 0},
        "E": {"pass": 15, "fail": 0, "unverified": 4, "blocked_or_na": 1},
    }
    for role, expected_subset in expected_counts.items():
        actual = documents[role]["status_counts"]
        assert all(actual[key] == value for key, value in expected_subset.items())


def write_json(name: str, payload: dict[str, object]) -> Path:
    path = OUT / name
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--junitxml", type=Path, required=True)
    args = parser.parse_args()
    documents = {
        "A": role_document("A", "ROLE_COMPLETE", role_a()),
        "B": role_document("B", "ROLE_INVALID", role_b()),
        "C": role_document("C", "ROLE_COMPLETE", role_c()),
        "D": role_document("D", "ROLE_INVALID", role_d()),
        "E": role_document("E", "ROLE_INCOMPLETE", role_e()),
    }
    validate_records(documents)
    cross_records = cross_role()
    for record in cross_records:
        assert set(record) == REQUIRED_FIELDS and record["status"] in STATUS_VALUES
    test_audit = test_document(args.junitxml)

    defect = {
        "classification": "RESULT_INVALIDATING",
        "affected_requirements": ["B23", "D17", "D21", "B<->D"],
        "current_behavior": "scripts/build_bd_production_input_readiness_v0_1.py assigns no_wall_positive_control=READY_EXISTING from prediction-slot coverage; production_u1_u2_66_cell_v0_1.py only consumes that label.",
        "required_behavior": "Execute and bind the frozen no-wall visible-position ridge positive-control decision on the current 66-cell authority, requiring held-out R^2 >= 0.50 and bootstrap CI strictly above zero, then fail closed if it does not pass.",
        "inherited_evidence": {
            "person_b_phase6_step6_6_strongest_global_r2": 0.338170676,
            "person_b_canonical_multilayout_strongest_global_r2": 0.390514057,
            "manual_threshold": 0.50,
        },
        "impact": "Existing U1/U2 numerical fits are not recomputed or judged here, but the current scientific result status cannot distinguish an absent hidden-state signal from a pipeline that has not demonstrated decodability on the required positive control.",
        "repair_policy_applied": "No scientific code/result repair was made because the gate adjudication can affect interpretation and result authority.",
    }
    summary = {
        "schema_version": "mvp-role-implementation-audit-summary-v0.1",
        "audit_kind": "AUDIT_1_OF_2_ROLE_IMPLEMENTATION_ONLY",
        "branch": BRANCH,
        "audited_head": HEAD,
        "manual_sources": manual_sources(),
        "role_verdicts": {role: doc["verdict"] for role, doc in documents.items()},
        "role_status_counts": {role: doc["status_counts"] for role, doc in documents.items()},
        "cross_role_contracts_pass": False,
        "current_u1_u2_result_invalidating_defect_found": True,
        "result_invalidating_defect": defect,
        "u3_implementation_status": "PASS",
        "u3_production_execution_status": "BLOCKED_EXTERNAL_DATA",
        "u4_implementation_status": "PASS",
        "u4_production_execution_status": "NOT_APPLICABLE_MVP_SCOPE",
        "test_failure_classification_counts": test_audit["classification_counts"],
        "focused_repair_required": True,
        "blocker": "RESULT_INVALIDATING: D17 no-wall positive-control gate was not executed on the current 66-cell authority; readiness equates prediction-slot coverage with a passed control, and inherited evidence has R2<0.50.",
        "next_action": "STOP scientific interpretation; B/D must adjudicate the manual positive-control contract, execute it on current 66-cell no-wall activations, and then supersede/reissue readiness and U1/U2 result-status artifacts under a reviewed authority.",
        "audit_scope_guardrails": {
            "final_scientific_conclusion_audited": False,
            "production_extraction_rerun": False,
            "u1_u2_refit": False,
            "u3_capture": False,
            "u4_executed": False,
            "scientific_result_files_modified": False,
        },
        "audit_package_digest_definition": "SHA-256 over UTF-8 lines sorted by relative path: relative_path + NUL + file_sha256 + NUL + decimal_size + LF, for the eight required audit JSON files; sha256_inventory.json is excluded to avoid recursive self-hashing.",
    }

    OUT.mkdir(parents=True, exist_ok=True)
    required_files = {
        "role_a_audit.json": documents["A"],
        "role_b_audit.json": documents["B"],
        "role_c_audit.json": documents["C"],
        "role_d_audit.json": documents["D"],
        "role_e_audit.json": documents["E"],
        "cross_role_audit.json": {
            "schema_version": "mvp-cross-role-implementation-audit-v0.1",
            "branch": BRANCH,
            "audited_head": HEAD,
            "cross_role_contracts_pass": False,
            "requirements": cross_records,
        },
        "test_audit.json": test_audit,
        "audit_summary.json": summary,
    }
    written = [write_json(name, payload) for name, payload in required_files.items()]
    entries = []
    digest_lines = bytearray()
    for path in sorted(written, key=lambda item: item.name):
        payload = path.read_bytes()
        relative = path.relative_to(REPO).as_posix()
        sha = hashlib.sha256(payload).hexdigest()
        entries.append({"path": relative, "sha256": sha, "size_bytes": len(payload)})
        digest_lines.extend(relative.encode("utf-8") + b"\0" + sha.encode("ascii") + b"\0" + str(len(payload)).encode("ascii") + b"\n")
    package_sha = hashlib.sha256(digest_lines).hexdigest()
    write_json("sha256_inventory.json", {
        "schema_version": "mvp-role-implementation-audit-inventory-v0.1",
        "branch": BRANCH,
        "audited_head": HEAD,
        "digest_definition": summary["audit_package_digest_definition"],
        "package_sha256": package_sha,
        "file_count": len(entries),
        "files": entries,
    })
    print(package_sha)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
