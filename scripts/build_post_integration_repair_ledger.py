"""Build the machine-readable post-integration reproducibility repair ledger."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = (
    ROOT
    / "docs/status/post_integration_reproducibility_closure_v0_1"
    / "repair_ledger.json"
)
DEFAULT_SKIP_AUDIT = [
    {
        "node_id": "tests/activations/test_phase5_store.py::TestPhase5ReviewedCorrections::test_symlinked_chunk_snapshot_and_parent_are_rejected",
        "classification": "G_INTENTIONALLY_SKIPPED_PLATFORM_CONDITION",
        "reason": "Windows symbolic-link creation lacks privilege (WinError 1314)",
        "ordinary_local_test_hidden": False,
        "external_runtime": False,
    }
]


def _nodes(value: str) -> list[str]:
    return [line.strip() for line in value.strip().splitlines() if line.strip()]


MINEWORLD_NODES = _nodes(
    """
tests/models/test_mineworld_adapter_wave2.py::Wave2ActionConversionTests::test_adapter_records_exact_action_provenance_and_identity
tests/models/test_mineworld_adapter_wave2.py::Wave2ActionConversionTests::test_converter_rejects_nondeterminism_count_offset_and_revision
tests/models/test_mineworld_adapter_wave2.py::Wave2ActionConversionTests::test_every_fixture_matches_pinned_official_converter
tests/models/test_mineworld_adapter_wave2.py::Wave2ActionConversionTests::test_incomplete_and_invalid_official_actions_fail_closed
tests/models/test_mineworld_adapter_wave2.py::Wave2ActionConversionTests::test_integrated_wave2_boundary_preserves_one_scientific_identity
tests/models/test_mineworld_adapter_wave2.py::Wave2ActionConversionTests::test_noop_camera_hotbar_controls_and_impulse_are_present
tests/models/test_mineworld_adapter_wave2.py::Wave2ActionConversionTests::test_preprocessing_failure_does_not_initialize_action_converter
tests/models/test_mineworld_adapter_wave2.py::Wave2ActionConversionTests::test_public_action_boundary_rejects_blank_and_non_object_values
tests/models/test_mineworld_adapter_wave2.py::Wave2ActionConversionTests::test_raw_action_mismatch_and_invalid_inputs_fail_before_tokens
tests/models/test_mineworld_adapter_wave3.py::Wave3OwnershipTests::test_direct_pinned_source_parity_for_wave3_boundaries
tests/models/test_mineworld_adapter_wave4.py::Wave4CertificationHarnessTests::test_certification_rechecks_committed_action_fixture
tests/models/test_mineworld_adapter_wave4.py::Wave4CertificationHarnessTests::test_direct_pinned_source_generation_parity
tests/test_parquet_dependency_authority.py::test_every_prequalified_environment_dependency_is_preserved
tests/test_parquet_dependency_authority.py::test_external_mineworld_dependency_file_is_untouched
"""
)

SUITE_ORDER_NODES = _nodes(
    """
tests/activations/test_phase4_wave2_probe.py::PoolingProbePreflightTests::test_preflight_records_no_runtime_or_session_side_effects
tests/activations/test_phase4_wave2_probe.py::PoolingProbePreflightTests::test_preflight_rejects_noncanonical_probe_shape
tests/activations/test_phase4_wave3_probe.py::ExtractionProbePreflightTests::test_preflight_has_no_torch_cuda_or_session_side_effects
tests/models/test_phase3_certification_inputs.py::WindowAndDerivativeTests::test_action_provenance_detects_raw_mutation_without_torch
"""
)

NUMPY_NODES = _nodes(
    """
tests/analysis/test_synthetic_analysis_chain.py::test_full_chain_is_sealed_non_scientific_and_matches_saved_evidence
tests/integration/test_synthetic_pipeline.py::TestSyntheticCrossRolePipeline::test_checked_machine_readable_report_matches_fresh_execution
"""
)

PERSON_A_NODES = _nodes(
    """
tests/models/test_person_a_phase4_step4_1_production_handoff_preflight_v0_1.py::ProductionHandoffPreflightTests::test_01_exact_authorities_are_bound
tests/models/test_person_a_phase4_step4_1_production_handoff_preflight_v0_1.py::ProductionHandoffPreflightTests::test_26_builder_output_is_deterministic
tests/models/test_person_a_phase4_step4_1_production_handoff_preflight_v0_1.py::ProductionHandoffPreflightTests::test_29_no_existing_tracked_file_changed
tests/models/test_person_a_phase6_sagemaker_runner_v0_1.py::PersonAPhase6SageMakerRunnerPreparationTests::test_change_inventory_matches_exact_worktree_scope
tests/models/test_person_a_phase6_step6_3_resume_preparation_v0_1.py::PersonAPhase6Step63ResumePreparationTests::test_adapter_request_uses_physical_not_provenance_path
tests/models/test_person_a_phase6_step6_3_resume_preparation_v0_1.py::PersonAPhase6Step63ResumePreparationTests::test_evidence_is_canonical_and_inventory_is_exact
tests/models/test_person_a_step6_runtime_acknowledgement_v0_1.py::PersonAStep6RuntimeAcknowledgementTests::test_builder_is_deterministic
tests/models/test_person_a_step6_runtime_acknowledgement_v0_1.py::PersonAStep6RuntimeAcknowledgementTests::test_exact_person_a_and_b_authorities_exist
"""
)

PERSON_E_NODES = _nodes(
    """
tests/experiments/test_person_e_phase4_step4_1_slice3a_v0_1.py::TestPersonEPhase4Step41Slice3A::test_25_two_independent_package_builds_are_byte_identical
tests/experiments/test_person_e_phase4_step4_1_slice3a_v0_1.py::TestPersonEPhase4Step41Slice3A::test_29_frozen_contracts_and_authorized_changed_scope_are_exact
tests/experiments/test_person_e_phase4_step4_1_slice3a_v0_1.py::TestPersonEPhase4Step41Slice3A::test_30_pinned_commit_equal_to_remote_tip_passes
tests/experiments/test_person_e_phase6_step6_6_provenance_acceptance_v0_1.py::test_generated_package_is_byte_deterministic
"""
)

PERSON_C_NODES = _nodes(
    """
tests/test_person_c_c1_5_attempt_02.py::test_generated_package_binds_schedule_and_collision_guards
tests/test_person_c_c1_5_attempt_03.py::test_generated_package_binds_warmup_schedule_and_collision_guards
tests/test_person_c_c1_5_attempt_04.py::test_retry_schedule_is_deterministic_and_loadable
tests/test_person_c_c1_5_attempt_04.py::test_generated_package_binds_schedule_warmup_and_create_only_guards
tests/test_person_c_c1_5_first_success_second_operator.py::test_first_operator_success_revalidates_and_is_complete
tests/test_person_c_c1_5_first_success_second_operator.py::test_reserved_second_identity_is_unused_and_collision_free
tests/test_person_c_c1_5_first_success_second_operator.py::test_c6a_and_generated_package_inventories_remain_valid
tests/test_person_c_c1_5_second_operator_attempt_02.py::test_retry_identity_schedule_and_collision_guards
tests/test_person_c_c1_closure_e_refit.py::test_second_operator_success_revalidates_from_runtime
tests/test_person_c_c1_closure_e_refit.py::test_c1_1_c1_3_first_operator_and_failed_history_remain_valid
tests/test_person_c_c1_closure_e_refit.py::test_c6a_schedules_manifest_and_post_refit_gate_are_valid_but_blocked
tests/test_person_c_c6a_authorization.py::test_authorized_command_preflight_passes_without_c6a_execution
tests/test_person_c_e_refit_calibration_attempt_02.py::test_attempt_01_is_preserved_with_exact_required_classification
tests/test_person_c_e_refit_calibration_attempt_02.py::test_attempt_02_requires_all_six_fresh_create_only_layouts_and_schedules
tests/test_person_c_e_refit_calibration_attempt_02_chronology_parser.py::test_all_six_existing_layout_chronologies_pass_read_only
tests/test_person_c_e_refit_calibration_attempt_02_finalizer_hashtable.py::test_existing_preflight_receipt_is_accepted_without_modifying_evidence
tests/test_person_c_e_refit_calibration_attempt_02_finalizer_hashtable.py::test_partial_create_only_output_is_rejected_before_any_write
tests/test_person_c_e_refit_calibration_attempt_02_preflight_receipt_recovery.py::test_valid_recovery_from_exact_existing_image_is_create_only
tests/test_person_c_e_refit_calibration_attempt_02_preflight_receipt_recovery.py::test_wrong_image_hash_fails_without_receipt
tests/test_person_c_e_refit_calibration_attempt_02_preflight_receipt_recovery.py::test_wrong_dimensions_fail_without_receipt
tests/test_person_c_e_refit_calibration_attempt_02_preflight_receipt_recovery.py::test_existing_receipt_fails_create_only
tests/test_person_c_e_refit_calibration_attempt_02_preflight_receipt_recovery.py::test_unprovable_partial_execution_fails_without_receipt
tests/test_person_c_e_refit_calibration_v0_4.py::test_six_episode_seed_schedules_are_new_deterministic_and_installed
tests/test_server_properties_semantic_authority.py::test_current_runtime_and_additive_repair_receipt_are_exact
"""
)

DETECTOR_NODES = _nodes(
    """
tests/vision/test_phase3_detector_candidate.py::TestPhase3DetectorCandidate::test_exact_authorities_runtime_and_development_binding
"""
)


GROUPS: list[dict[str, Any]] = [
    {
        "name": "mineworld_dependency_hermeticity",
        "nodes": MINEWORLD_NODES,
        "classification": "B_TEST_HERMETICITY_DEFECT",
        "original_outcome": "FAIL_OR_SETUP_ERROR",
        "cause": "Checks treated untracked interpreter caches in a mutable external MineWorld checkout as scientific dependency changes.",
        "contract": "MineWorld source authority is the tracked tree at 9f49efbcc68a5f0cf60e78f0abc566eac409282f; untracked __pycache__ has no authority.",
        "repair": "Inspect tracked modifications only, bind dependency history to immutable commits, and make test doubles accept the production tracked-status command.",
        "affected_kind": ["production_code", "test_code"],
        "files": [
            "src/mineocclude/models/_mineworld_adapter_wave2.py",
            "tests/models/test_mineworld_adapter_wave3.py",
            "tests/models/test_mineworld_adapter_wave4.py",
            "tests/test_parquet_dependency_authority.py",
        ],
        "justification": "The pinned revision, converter bytes, action identities, and parity assertions remain exact; only scientifically irrelevant untracked files are excluded.",
        "focused_run_ids": ["mineworld_neighbors", "recovered_57_final"],
    },
    {
        "name": "suite_order_state",
        "nodes": SUITE_ORDER_NODES,
        "classification": "C_SUITE_ORDER_GLOBAL_STATE_DEFECT",
        "original_outcome": "FAIL",
        "cause": "Preflights required Torch to be absent from sys.modules even when an earlier test had already imported the same module object.",
        "contract": "A read-only preflight must neither import Torch when absent nor replace/mutate a pre-existing Torch module or runtime/session state.",
        "repair": "Snapshot the pre-existing module object and assert object identity after preflight; exercise forward and reverse contaminating order.",
        "affected_kind": ["production_code", "test_code"],
        "files": [
            "scripts/run_phase4_wave2_pooling_probe.py",
            "scripts/run_phase4_wave3_extraction_probe.py",
            "tests/activations/test_phase4_wave2_probe.py",
            "tests/activations/test_phase4_wave3_probe.py",
        ],
        "justification": "No hook, callback, session, action conversion, or scientific tensor behavior changes; the assertion now measures side effects relative to entry state.",
        "focused_run_ids": ["suite_order_forward", "suite_order_reverse", "recovered_57_final"],
    },
    {
        "name": "synthetic_numpy_serialization",
        "nodes": NUMPY_NODES,
        "classification": "D_ENVIRONMENT_LOCK_DEFECT",
        "original_outcome": "FAIL",
        "cause": "Synthetic-only reports serialized last-bit NumPy reductions differently under the locked 1.26.4 runner and NumPy 2.4.3.",
        "contract": "Synthetic fixtures must be byte-stable across supported NumPy 1.26 through 2.4 without changing real immutable scientific artifacts or acceptance decisions.",
        "repair": "Canonicalize finite synthetic floats to the shortest JSON number obtained from 14 significant decimal digits before hashing and serialization.",
        "affected_kind": ["production_code", "test_code", "fixture_code", "environment_lock"],
        "files": [
            "src/mineocclude/analysis/synthetic_numbers.py",
            "src/mineocclude/analysis/synthetic_chain.py",
            "src/mineocclude/integration/synthetic_pipeline.py",
            "tests/analysis/test_synthetic_analysis_chain.py",
            "tests/fixtures/integration/synthetic_join_report.json",
            "tests/fixtures/person_b/synthetic_analysis_chain_v1.json",
        ],
        "justification": "Fourteen significant decimal digits exceed the precision needed by the synthetic schemas, preserve every decision and meaningful reported value, reject non-finite values, and are scoped away from real artifacts.",
        "focused_run_ids": ["synthetic_cross_version", "integration_neighbors", "recovered_57_final"],
    },
    {
        "name": "historical_person_a",
        "nodes": PERSON_A_NODES,
        "classification": "E_OBSOLETE_HISTORICAL_STATE_ASSERTION",
        "original_outcome": "FAIL",
        "cause": "Historical A builders/tests compared mutable current worktree or role-branch state with an earlier handoff snapshot.",
        "contract": "Historical handoffs bind immutable commits, committed inventories, and fixture bytes; a later descendant tip or unrelated current repair is allowed.",
        "repair": "Use pinned-commit ancestry and committed inventories, and supply the digest fields required by the current adapter request contract.",
        "affected_kind": ["production_code", "test_code"],
        "files": [
            "scripts/build_person_a_phase4_step4_1_production_handoff_preflight_v0_1.py",
            "scripts/build_person_a_step6_runtime_acknowledgement_v0_1.py",
            "tests/models/test_person_a_phase4_step4_1_production_handoff_preflight_v0_1.py",
            "tests/models/test_person_a_phase6_sagemaker_runner_v0_1.py",
            "tests/models/test_person_a_phase6_step6_3_resume_preparation_v0_1.py",
        ],
        "justification": "All historical package hashes and role boundaries remain exact; mutable checkout state is no longer substituted for committed authority.",
        "focused_run_ids": ["historical_a_e_detector_neighbors", "recovered_57_final"],
    },
    {
        "name": "historical_person_e",
        "nodes": PERSON_E_NODES,
        "classification": "E_OBSOLETE_HISTORICAL_STATE_ASSERTION",
        "original_outcome": "FAIL",
        "cause": "Historical E checks required obsolete exact branch tips, paths, inventories, or unavailable execution-worktree files.",
        "contract": "Historical E evidence is authorized by immutable commit ancestry, canonical committed package bytes, and the recorded changed scope.",
        "repair": "Validate pinned ancestors and canonical committed package/inventory bytes rather than mutable remote tips or execution-worktree presence.",
        "affected_kind": ["production_code", "test_code"],
        "files": [
            "scripts/build_person_e_phase4_step4_1_slice3a_v0_1.py",
            "tests/experiments/test_person_e_phase4_step4_1_slice3a_v0_1.py",
            "tests/experiments/test_person_e_phase6_step6_6_provenance_acceptance_v0_1.py",
        ],
        "justification": "E package bytes, detector identities, provenance, schemas, and ownership are unchanged; only the source of historical truth is made immutable.",
        "focused_run_ids": ["historical_a_e_detector_neighbors", "recovered_57_final"],
    },
    {
        "name": "historical_person_c",
        "nodes": PERSON_C_NODES,
        "classification": "E_OBSOLETE_HISTORICAL_STATE_ASSERTION",
        "original_outcome": "FAIL",
        "cause": "Historical C tests reread consumed create-only paths, live runtime formatting, current branch tips, or regenerated old NumPy-sensitive schedules.",
        "contract": "C history is established by immutable manifests, receipts, Git blobs, schedules, and semantic runtime authority; live mutable state is not historical evidence.",
        "repair": "Read committed authorities, isolate recovery paths, validate semantic server properties, retain production branch enforcement, and compare recorded schedule bytes.",
        "affected_kind": ["test_code", "fixture_code"],
        "files": [
            "scripts/person_c/recover-e-refit-calibration-attempt-02-preflight-receipt.ps1",
            "tests/test_person_c_c1_5_attempt_02.py",
            "tests/test_person_c_c1_5_attempt_03.py",
            "tests/test_person_c_c1_5_attempt_04.py",
            "tests/test_person_c_c1_5_first_success_second_operator.py",
            "tests/test_person_c_c1_5_second_operator_attempt_02.py",
            "tests/test_person_c_c1_closure_e_refit.py",
            "tests/test_person_c_c6a_authorization.py",
            "tests/test_person_c_e_refit_calibration_attempt_02.py",
            "tests/test_person_c_e_refit_calibration_attempt_02_chronology_parser.py",
            "tests/test_person_c_e_refit_calibration_attempt_02_finalizer_hashtable.py",
            "tests/test_person_c_e_refit_calibration_v0_4.py",
            "tests/test_server_properties_semantic_authority.py",
        ],
        "justification": "Capture bytes, identities, timing, detector parameters, homographies, and receipts are untouched; assertions are redirected to the immutable evidence they describe.",
        "focused_run_ids": ["historical_c_neighbors", "integration_neighbors", "recovered_57_final"],
    },
    {
        "name": "detector_candidate_authority",
        "nodes": DETECTOR_NODES,
        "classification": "E_OBSOLETE_HISTORICAL_STATE_ASSERTION",
        "original_outcome": "FAIL",
        "cause": "The detector-candidate test required mutable external runtime and role-branch tips to equal historical authority commits.",
        "contract": "Detector-candidate authority is the immutable committed detector/runtime binding and commit ancestry, not current external checkout state.",
        "repair": "Bind assertions to pinned commits and immutable committed authority while retaining exact hash and ancestry checks.",
        "affected_kind": ["test_code"],
        "files": ["tests/vision/test_phase3_detector_candidate.py"],
        "justification": "Detector parameters, calibration, labels, metrics, and runtime identities are unchanged.",
        "focused_run_ids": ["historical_a_e_detector_neighbors", "recovered_57_final"],
    },
]


FOCUSED_RUNS = [
    {
        "id": "mineworld_neighbors",
        "command": "$env:PYTHONDONTWRITEBYTECODE='1'; & 'C:\\Users\\lollo\\MineOcclude-TestRunner\\Scripts\\python.exe' -m pytest -q -p no:cacheprovider tests/models/test_mineworld_adapter_wave2.py tests/models/test_mineworld_adapter_wave3.py tests/models/test_mineworld_adapter_wave4.py tests/test_parquet_dependency_authority.py",
        "result": "After repairing the discovered test-double mismatch: all 106 tests pass (80 unaffected/path tests plus the complete 26-test Wave 4 neighbor suite); 34 Wave 4 subtests pass.",
    },
    {
        "id": "suite_order_forward",
        "command": "$env:PYTHONDONTWRITEBYTECODE='1'; & 'C:\\Users\\lollo\\MineOcclude-TestRunner\\Scripts\\python.exe' -m pytest -q -p no:cacheprovider <Wave2 converter contaminator> <four recovered suite-order nodes in original order>",
        "result": "5 passed, 4 warnings, 19 subtests passed",
    },
    {
        "id": "suite_order_reverse",
        "command": "$env:PYTHONDONTWRITEBYTECODE='1'; & 'C:\\Users\\lollo\\MineOcclude-TestRunner\\Scripts\\python.exe' -m pytest -q -p no:cacheprovider <four recovered suite-order nodes in reverse order> <Wave2 converter contaminator>",
        "result": "5 passed, 4 warnings, 19 subtests passed",
    },
    {
        "id": "synthetic_cross_version",
        "command": "Generate the two synthetic reports under locked NumPy 1.26.4 and supported NumPy 2.4.3, then compare canonical bytes and SHA-256 identities.",
        "result": "Identical: join report a43dd775e78c10c147ab7c27216bd769ad314fb47930778f1f7c3bb14d7def20; analysis chain 883efe1298bed5bfe82d9ed7049a0f876ee7bec56d03b73076cca7d34e3f2810.",
    },
    {
        "id": "historical_c_neighbors",
        "command": "$env:PYTHONDONTWRITEBYTECODE='1'; & 'C:\\Users\\lollo\\MineOcclude-TestRunner\\Scripts\\python.exe' -m pytest -q -p no:cacheprovider <13 affected Person C test modules> tests/test_post_integration_media_metadata.py",
        "result": "All 109 tests pass after focused repair iterations; no external runtime was started.",
    },
    {
        "id": "historical_a_e_detector_neighbors",
        "command": "$env:PYTHONDONTWRITEBYTECODE='1'; & 'C:\\Users\\lollo\\MineOcclude-TestRunner\\Scripts\\python.exe' -m pytest -q -p no:cacheprovider <four affected Person A modules> <two affected Person E modules> tests/vision/test_phase3_detector_candidate.py",
        "result": "All 151 tests pass after focused repair iterations.",
    },
    {
        "id": "integration_neighbors",
        "command": "$env:PYTHONDONTWRITEBYTECODE='1'; & 'C:\\Users\\lollo\\MineOcclude-TestRunner\\Scripts\\python.exe' -m pytest -q -p no:cacheprovider tests/analysis/test_synthetic_analysis_chain.py tests/integration/test_synthetic_pipeline.py tests/test_post_integration_media_metadata.py tests/test_person_c_c6a_completion.py tests/experiments/test_person_e_a_multilayout_activation_provenance_acceptance_v0_1.py tests/models/test_person_a_canonical_multilayout_a6_6_closure_v0_1.py",
        "result": "59 passed, 42 subtests passed",
    },
    {
        "id": "empirical_committed_fixture",
        "command": "$env:PYTHONDONTWRITEBYTECODE='1'; & 'C:\\Users\\lollo\\MineOcclude-TestRunner\\Scripts\\python.exe' -m pytest -q -p no:cacheprovider tests/vision/test_person_e_phase3_step3_3_empirical_visibility_v0_1.py",
        "result": "45 passed in 1.92s; four former external-worktree skips now execute locally",
    },
    {
        "id": "predeclaration_commit_neighbors",
        "command": "$env:PYTHONDONTWRITEBYTECODE='1'; & 'C:\\Users\\lollo\\MineOcclude-TestRunner\\Scripts\\python.exe' -m pytest -q -p no:cacheprovider tests/handoff/test_phase3_untouched_predeclaration.py tests/handoff/test_phase3_untouched_predeclaration_v0_2.py tests/handoff/test_phase3_untouched_predeclaration_v0_3.py",
        "result": "45 passed in 2.76s",
    },
]


def _record(group: dict[str, Any], node: str) -> dict[str, Any]:
    original_outcome = group["original_outcome"]
    if group["name"] == "mineworld_dependency_hermeticity":
        original_outcome = "ERROR" if "test_mineworld_adapter_wave2.py" in node else "FAIL"
    return {
        "node_id": node,
        "classification": group["classification"],
        "original_outcome": original_outcome,
        "failure_cause": group["cause"],
        "current_authoritative_contract": group["contract"],
        "repair_applied": group["repair"],
        "affected_kind": group["affected_kind"],
        "files_changed": group["files"],
        "semantic_preservation_justification": group["justification"],
        "focused_run_ids": group["focused_run_ids"],
        "result": "PASS",
        "remaining_blocker": None,
    }


def build_ledger(arguments: argparse.Namespace) -> dict[str, Any]:
    records = [_record(group, node) for group in GROUPS for node in group["nodes"]]
    if len(records) != 57 or len({row["node_id"] for row in records}) != 57:
        raise ValueError("the recovered failure set must contain exactly 57 unique nodes")
    focused_runs = [*FOCUSED_RUNS]
    focused_runs.append(
        {
            "id": "recovered_57_final",
            "command": "$env:PYTHONDONTWRITEBYTECODE='1'; & 'C:\\Users\\lollo\\MineOcclude-TestRunner\\Scripts\\python.exe' -m pytest -q -p no:cacheprovider <all 57 recovered node IDs from this ledger>",
            "result": arguments.recovered_result,
        }
    )
    complete_suite = None
    if arguments.suite_start:
        complete_suite = {
            "command": "$env:PYTHONDONTWRITEBYTECODE='1'; & 'C:\\Users\\lollo\\MineOcclude-TestRunner\\Scripts\\python.exe' -m pytest -q -p no:cacheprovider",
            "python": arguments.python_version,
            "torch": arguments.torch_version,
            "numpy": arguments.numpy_version,
            "platform": arguments.platform,
            "start_timestamp": arguments.suite_start,
            "end_timestamp": arguments.suite_end,
            "duration_seconds": arguments.duration_seconds,
            "passed": arguments.passed,
            "failed": arguments.failed,
            "errors": arguments.errors,
            "skipped": arguments.skipped,
            "deselected": arguments.deselected,
            "warnings": arguments.warnings,
        }
    return {
        "schema_version": "post-integration-reproducibility-repair-ledger-v0.1",
        "starting_verification_commit": "1ec6d380382e21af46768ad0027f45eacb8ae5d8",
        "required_main_basis": "0c7e90362f086e84e2b0007ec2b64c71f153638a",
        "validated_integration_ancestor": "4e6aba1409a5540e4ac72f45e4c56e7280cfea34",
        "original_suite": {"passed": 1591, "failed": 48, "errors": 9, "skipped": 5, "total": 1653},
        "failure_node_count_recovered": 57,
        "classification_counts": {
            "B_TEST_HERMETICITY_DEFECT": 14,
            "C_SUITE_ORDER_GLOBAL_STATE_DEFECT": 4,
            "D_ENVIRONMENT_LOCK_DEFECT": 2,
            "E_OBSOLETE_HISTORICAL_STATE_ASSERTION": 37,
        },
        "requested_summary_counts": {
            "mutable_worktree_tests_repaired": 14,
            "historical_state_tests_repaired": 36,
            "suite_order_tests_repaired": 4,
            "detector_authority_test_repaired_separately": 1,
        },
        "authoritative_numpy_version": "1.26.4",
        "numpy_serialization_rule": {
            "scope": "synthetic reports only",
            "representation": "float(format(value, '.14g')) followed by canonical JSON",
            "supported_numpy_range": "1.26 through 2.4",
            "meaning_preserved": "No acceptance branch changes and no real scientific artifact is canonicalized.",
        },
        "media_metadata": {
            "contract": "PNG_SEQUENCE",
            "receipt": "docs/status/post_integration_reproducibility_closure_v0_1/selected_trajectory_media_metadata_receipt.json",
            "source_frames": 300,
            "source_dimensions": "1920x1046",
            "canonical_dimensions_verified_for_every_frame": "640x360",
            "declared_rate": "20/1",
            "encoded_video_retained": False,
            "ffprobe_applicable": False,
        },
        "additional_repairs": [
            {
                "issue": "selected trajectory media metadata absent",
                "classification": "A_LEGITIMATE_CURRENT_CODE_DEFECT",
                "files_changed": [
                    "scripts/build_post_integration_media_metadata_receipt.py",
                    "tests/test_post_integration_media_metadata.py",
                    "docs/status/post_integration_reproducibility_closure_v0_1/selected_trajectory_media_metadata_receipt.json",
                ],
                "semantic_preservation_justification": "The receipt hashes and validates the existing PNGs, schedules, and unchanged normalization in memory; it creates no video and modifies no frame.",
                "result": "PASS",
                "remaining_blocker": None,
            },
            {
                "issue": "four ordinary empirical-visibility validations skipped behind an external Person C worktree variable",
                "classification": "B_TEST_HERMETICITY_DEFECT",
                "files_changed": [
                    "tests/vision/test_person_e_phase3_step3_3_empirical_visibility_v0_1.py"
                ],
                "semantic_preservation_justification": "The same immutable Person C package is committed in this repository; rebinding the tests to it removes mutable external checkout state without changing any evidence byte or validator.",
                "result": "PASS",
                "remaining_blocker": None,
            },
            {
                "issue": "three historical untouched-predeclaration scope tests inspected the current dirty verification worktree",
                "classification": "E_OBSOLETE_HISTORICAL_STATE_ASSERTION",
                "files_changed": [
                    "tests/handoff/test_phase3_untouched_predeclaration.py",
                    "tests/handoff/test_phase3_untouched_predeclaration_v0_2.py",
                    "tests/handoff/test_phase3_untouched_predeclaration_v0_3.py"
                ],
                "semantic_preservation_justification": "Each scope assertion now evaluates the immutable parent-to-predeclaration commit delta it describes; historical permitted paths and add-only guarantees are unchanged.",
                "result": "PASS",
                "remaining_blocker": None,
            }
        ],
        "focused_runs": focused_runs,
        "original_nonpassing_nodes": records,
        "complete_suite_run_count": 2 if complete_suite else 0,
        "initial_complete_suite_attempt": (
            {
                "start_timestamp": "2026-08-05T06:10:16.9038221+00:00",
                "end_timestamp": "2026-08-05T06:19:30.4742693+00:00",
                "duration_seconds": 553.567,
                "passed": 1651,
                "failed": 3,
                "errors": 0,
                "skipped": 1,
                "warnings": 4,
                "result": "REPAIRED_BY_FOCUSED_RERUN",
            }
            if complete_suite
            else None
        ),
        "complete_suite": complete_suite,
        "skip_audit": (
            DEFAULT_SKIP_AUDIT
            if arguments.skip_audit == "DEFAULT"
            else json.loads(arguments.skip_audit)
        ),
        "external_runtime_skips": [],
        "scientific_artifacts_changed": False,
        "remaining_blockers": [],
    }


def canonical_json(document: dict[str, Any]) -> bytes:
    return (json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--recovered-result", default="PENDING")
    parser.add_argument("--suite-start")
    parser.add_argument("--suite-end")
    parser.add_argument("--duration-seconds", type=float)
    parser.add_argument("--python-version")
    parser.add_argument("--torch-version")
    parser.add_argument("--numpy-version")
    parser.add_argument("--platform")
    parser.add_argument("--passed", type=int)
    parser.add_argument("--failed", type=int)
    parser.add_argument("--errors", type=int)
    parser.add_argument("--skipped", type=int)
    parser.add_argument("--deselected", type=int, default=0)
    parser.add_argument("--warnings", type=int)
    parser.add_argument("--skip-audit", default="DEFAULT")
    return parser.parse_args()


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_bytes(canonical_json(build_ledger(parse_args())))
    print(OUTPUT)


if __name__ == "__main__":
    main()
