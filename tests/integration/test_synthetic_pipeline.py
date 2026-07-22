"""Tests for the Phase 1 Step 1.7 synthetic cross-role pipeline."""

from __future__ import annotations

import json
import unittest
from copy import deepcopy

from mineocclude.analysis.manifests import validate_sealed_artifact
from mineocclude.contracts.analysis_inputs import (
    validate_baseline_input,
    validate_measurement_input,
)
from mineocclude.integration.synthetic_pipeline import (
    DEFAULT_REPORT_PATH,
    join_report,
    load_pipeline_inputs,
    run_synthetic_pipeline,
    run_synthetic_pipeline_from_documents,
)
from mineocclude.vision.measurement import (
    MeasurementError,
    build_measurement_document,
    validate_measurement_evidence,
)


EXPECTED_JOIN_NAMES = {
    "trajectory_to_normalized_actions",
    "trajectory_to_token_map",
    "trajectory_to_targets",
    "targets_to_activations",
    "b_chain_targets_to_d_baselines",
    "request_heldout_events_to_rollouts",
    "request_alpha_table_to_rollouts",
    "contexts_to_rollouts",
    "rollouts_to_runs",
    "rollouts_to_input_context_artifacts",
    "rollouts_to_intervention_request_artifacts",
    "rollouts_to_output_artifacts",
    "rollouts_to_measurements",
}


def failed_check_names(report: dict) -> set[str]:
    """Return names of failed integrity checks."""

    return {
        check["name"]
        for check in report["integrity_checks"]
        if not check["passed"]
    }


def failed_join_names(report: dict) -> set[str]:
    """Return names of failed joins."""

    return {
        join["name"]
        for join in report["joins"]
        if join["status"] != "passed"
    }


class TestSyntheticCrossRolePipeline(unittest.TestCase):
    """Prove all Phase 1 cross-role interfaces work together."""

    @classmethod
    def setUpClass(cls) -> None:
        """Load and run the CPU-only synthetic pipeline once."""

        cls.bundle, cls.documents, cls.source_hashes = load_pipeline_inputs()
        cls.report = run_synthetic_pipeline_from_documents(
            cls.bundle,
            cls.documents,
            cls.source_hashes,
        )

    def mutated_report(self, mutator):
        """Run the pipeline on a mutated in-memory copy."""

        bundle = deepcopy(self.bundle)
        documents = deepcopy(self.documents)
        source_hashes = deepcopy(self.source_hashes)

        mutator(bundle, documents, source_hashes)

        return run_synthetic_pipeline_from_documents(
            bundle,
            documents,
            source_hashes,
        )

    def test_complete_pipeline_passes(self):
        """The complete Step 1.7 integration proof must pass."""

        self.assertEqual(self.report["overall_status"], "passed")

    def test_authenticated_a_b_probe_bridge_is_part_of_step_1_7(self):
        """The report must execute A handoff through B's sealed OOF ridge path."""

        bridge = self.report["authenticated_a_b_probe_bridge"]

        self.assertEqual(bridge["status"], "passed")
        self.assertEqual(bridge["fixture_metadata"], {
            "synthetic": True,
            "scientific_use": "forbidden",
        })
        self.assertEqual(bridge["summary"], {
            "frame_rows": 15,
            "fold_count": 5,
            "matrix_count": 2,
            "prediction_rows": 30,
            "sealed_prediction_artifacts": 2,
            "sealed_u1_result_artifacts": 2,
        })
        self.assertEqual(
            bridge["lineage"]["source_handoff_id"],
            self.documents["activation_handoff"]["handoff_id"],
        )
        self.assertEqual(
            bridge["lineage"]["source_activation_sha256"],
            self.source_hashes["activation_handoff"],
        )
        self.assertEqual(
            bridge["lineage"]["source_chunk_sha256"],
            self.source_hashes["activation_chunk"],
        )
        self.assertEqual(len(bridge["lineage"]["derived_chunk_hashes"]), 5)

    def test_authenticated_bridge_outputs_are_sealed_and_non_scientific(self):
        """Every bridge output must retain identity, hashes, and use restrictions."""

        bridge = self.report["authenticated_a_b_probe_bridge"]
        self.assertTrue(bridge["frame_table"]["synthetic"])
        self.assertEqual(bridge["frame_table"]["scientific_use"], "forbidden")
        self.assertTrue(bridge["fold_manifest"]["synthetic"])
        self.assertEqual(bridge["fold_manifest"]["scientific_use"], "forbidden")

        expected_sites = {(5, "residual_stream"), (12, "residual_stream")}
        actual_sites = {
            (run["layer_idx"], run["hook_site"])
            for run in bridge["probe_runs"]
        }
        self.assertEqual(actual_sites, expected_sites)

        for run in bridge["probe_runs"]:
            with self.subTest(layer=run["layer_idx"], site=run["hook_site"]):
                self.assertEqual(run["row_count"], 15)
                self.assertEqual(run["feature_count"], 2048)
                self.assertEqual(run["folds"], [0, 1, 2, 3, 4])
                self.assertTrue(run["synthetic"])
                self.assertEqual(run["scientific_use"], "forbidden")
                for artifact_name in ("prediction_artifact", "u1_result_artifact"):
                    artifact = run[artifact_name]
                    validate_sealed_artifact(artifact)
                    self.assertTrue(artifact["synthetic"])
                    self.assertEqual(artifact["scientific_use"], "forbidden")
                    self.assertEqual(artifact["matrix_hash"], run["matrix_hash"])
                    self.assertEqual(len(artifact["artifact_hash"]), 64)
                    self.assertNotEqual(
                        artifact["artifact_hash"],
                        artifact["uncompacted_artifact_hash"],
                    )
                    self.assertEqual(artifact["fold_fit_records_count"], 5)
                    self.assertEqual(len(artifact["fold_fit_records_hash"]), 64)
                    self.assertEqual(len(artifact["fold_fit_summaries"]), 5)
                    self.assertNotIn("fold_fit_records", artifact)

                    for fold_summary in artifact["fold_fit_summaries"]:
                        self.assertIn(fold_summary["outer_fold_idx"], range(5))
                        self.assertIn(
                            fold_summary["selected_alpha"],
                            artifact["probe_parameters"]["alpha_grid"],
                        )
                        self.assertGreater(fold_summary["training_row_count"], 0)
                        self.assertGreater(fold_summary["test_row_count"], 0)
                        self.assertEqual(
                            fold_summary["scaler"]["fit_scope"],
                            "outer_training_rows_only",
                        )
                        for hash_name in (
                            "training_indices_hash",
                            "test_indices_hash",
                            "training_membership_hash",
                            "test_membership_hash",
                        ):
                            self.assertEqual(len(fold_summary[hash_name]), 64)

                self.assertEqual(
                    run["u1_result_artifact"]["prediction_manifest_hashes"],
                    [run["prediction_artifact"]["artifact_hash"]],
                )
                self.assertEqual(
                    run["u1_result_artifact"][
                        "uncompacted_prediction_manifest_hashes"
                    ],
                    [run["prediction_artifact"]["uncompacted_artifact_hash"]],
                )

                prediction_rows = run["prediction_artifact"]["rows"]
                self.assertEqual(len(prediction_rows), 15)
                for row in prediction_rows:
                    self.assertEqual(row["layer_idx"], run["layer_idx"])
                    self.assertEqual(row["hook_site"], run["hook_site"])
                    self.assertIn("trajectory_id", row)
                    self.assertIn("model_frame_idx", row)

    def test_stale_a_activation_chunk_bytes_fail_the_step_1_7_gate(self):
        """Mutated vectors cannot pass under the checked A chunk hash."""

        def mutate(_bundle, documents, _hashes):
            documents["activation_chunk"]["rows"][0]["vector"][0] += 1.0

        report = self.mutated_report(mutate)
        bridge = report["authenticated_a_b_probe_bridge"]

        self.assertEqual(report["overall_status"], "failed")
        self.assertEqual(bridge["status"], "failed")
        self.assertEqual(
            bridge["rejections"][0]["code"],
            "stale_bridge_source_hash",
        )
        self.assertIn("authenticated_a_b_probe_bridge", failed_check_names(report))

    def test_mutated_a_handoff_cannot_reuse_its_loaded_source_hash(self):
        """A valid-looking handoff edit must receive new authenticated lineage."""

        def mutate(_bundle, documents, _hashes):
            documents["activation_handoff"]["handoff_id"] = (
                "valid_looking_but_unauthenticated_handoff"
            )

        report = self.mutated_report(mutate)
        bridge = report["authenticated_a_b_probe_bridge"]

        self.assertEqual(report["overall_status"], "failed")
        self.assertEqual(bridge["status"], "failed")
        self.assertEqual(
            bridge["rejections"][0]["code"],
            "stale_bridge_source_hash",
        )
        self.assertIn("authenticated_a_b_probe_bridge", failed_check_names(report))

    def test_pipeline_does_not_mutate_authenticated_bridge_inputs(self):
        """Bridge derivation and fitting must leave all submitted evidence unchanged."""

        bundle = deepcopy(self.bundle)
        documents = deepcopy(self.documents)
        source_hashes = deepcopy(self.source_hashes)
        before_bundle = deepcopy(bundle)
        before_documents = deepcopy(documents)
        before_hashes = deepcopy(source_hashes)

        report = run_synthetic_pipeline_from_documents(
            bundle,
            documents,
            source_hashes,
        )

        self.assertEqual(report["overall_status"], "passed")
        self.assertEqual(bundle, before_bundle)
        self.assertEqual(documents, before_documents)
        self.assertEqual(source_hashes, before_hashes)

    def test_oracle_targets_follow_corrected_activation_timebase_and_lineage(self):
        """Integration targets must resolve to the corrected A handoff."""

        activation = self.documents["activation_handoff"]
        targets = self.documents["oracle_targets"]

        self.assertEqual(targets["schema_version"], "1.0")
        self.assertEqual(
            targets["source_activation"],
            {
                "handoff_id": activation["handoff_id"],
                "run_id": activation["run_id"],
                "accepted_manifest_hash": activation["accepted_manifest_hash"],
            },
        )

        activation_by_frame = {}
        for row in activation["index_rows"]:
            activation_by_frame.setdefault(
                (row["trajectory_id"], row["model_frame_idx"]),
                row,
            )

        for target in targets["rows"]:
            activation_row = activation_by_frame[
                (target["trajectory_id"], target["model_frame_idx"])
            ]
            self.assertEqual(target["server_tick"], activation_row["server_tick"])
            self.assertEqual(target["tau"], activation_row["tau"])

    def test_all_existing_contracts_validate(self):
        """Every contract used by the integration fixture must pass."""

        validations = self.report["contract_validations"]

        self.assertEqual(
            set(validations),
            {
                "trajectory",
                "activation",
                "intervention_request",
                "rollout_registry",
                "c_to_b_state",
                "d_to_b_baseline",
                "e_to_b_measurement",
                "b_to_a_chain_request",
            },
        )

        for name, result in validations.items():
            with self.subTest(contract=name):
                self.assertTrue(result["accepted"], msg=result["rejections"])

        self.assertEqual(self.report["summary"]["contracts_passed"], 8)
        self.assertEqual(self.report["summary"]["contracts_total"], 8)

    def test_all_required_cross_role_joins_are_exercised(self):
        """The report must contain every required Step 1.7 join."""

        actual_names = {
            join["name"]
            for join in self.report["joins"]
        }

        self.assertEqual(actual_names, EXPECTED_JOIN_NAMES)
        self.assertEqual(self.report["summary"]["joins_total"], len(EXPECTED_JOIN_NAMES))

    def test_every_cross_role_join_passes(self):
        """No required join may contain unresolved keys or cardinality errors."""

        for join in self.report["joins"]:
            with self.subTest(join=join["name"]):
                self.assertEqual(join["status"], "passed")
                self.assertEqual(join["invalid_left_rows"], [])
                self.assertEqual(join["invalid_right_rows"], [])
                self.assertEqual(join["cardinality_mismatches"], [])
                self.assertFalse(join["empty_input_failure"])
                self.assertFalse(join["no_common_key_failure"])

        self.assertEqual(self.report["summary"]["joins_passed"], len(EXPECTED_JOIN_NAMES))

    def test_all_integrity_checks_pass(self):
        """All deeper cross-contract consistency rules must pass."""

        for check in self.report["integrity_checks"]:
            with self.subTest(check=check["name"]):
                self.assertTrue(check["passed"], msg=check["details"])

        self.assertEqual(
            self.report["summary"]["integrity_checks_passed"],
            self.report["summary"]["integrity_checks_total"],
        )

    def test_no_claim_bearing_rows_are_orphaned(self):
        """Every synthetic claim-bearing row must resolve through its joins."""

        self.assertEqual(self.report["summary"]["orphaned_claim_bearing_rows"], 0)
        self.assertEqual(self.report["orphaned_claim_bearing_rows"], [])

    def test_join_logic_does_not_depend_on_row_order(self):
        """Explicit-key joins must still work when row order changes."""

        left_rows = [
            {"trajectory_id": "trajectory_001", "model_frame_idx": 0},
            {"trajectory_id": "trajectory_001", "model_frame_idx": 1},
        ]

        right_rows = [
            {"trajectory_id": "trajectory_001", "model_frame_idx": 1},
            {"trajectory_id": "trajectory_001", "model_frame_idx": 0},
        ]

        result = join_report(
            name="synthetic_row_order_test",
            left_name="left",
            right_name="right",
            left_rows=left_rows,
            right_rows=right_rows,
            left_key_fields=("trajectory_id", "model_frame_idx"),
            relationship="one_to_one",
        )

        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["joined_rows"], 2)

    def test_join_logic_rejects_bool_int_identity_collision(self):
        """True must not join to integer 1."""

        result = join_report(
            name="bool_int_collision",
            left_name="left",
            right_name="right",
            left_rows=[{"model_frame_idx": True}],
            right_rows=[{"model_frame_idx": 1}],
            left_key_fields=("model_frame_idx",),
            relationship="one_to_one",
        )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["invalid_left_rows"], [0])

    def test_join_logic_rejects_float_int_identity_collision(self):
        """1.0 must not join to integer 1."""

        result = join_report(
            name="float_int_collision",
            left_name="left",
            right_name="right",
            left_rows=[{"model_frame_idx": 1.0}],
            right_rows=[{"model_frame_idx": 1}],
            left_key_fields=("model_frame_idx",),
            relationship="one_to_one",
        )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["invalid_left_rows"], [0])

    def test_join_logic_rejects_empty_required_join(self):
        """Required joins may not pass when both sides are empty."""

        result = join_report(
            name="empty_join",
            left_name="left",
            right_name="right",
            left_rows=[],
            right_rows=[],
            left_key_fields=("rollout_id",),
            relationship="one_to_one",
        )

        self.assertEqual(result["status"], "failed")
        self.assertTrue(result["empty_input_failure"])

    def test_missing_expected_activation_site_fails(self):
        """Activation coverage must come from independent expected sites."""

        def mutate(bundle, _documents, _hashes):
            bundle["expected_activation_sites"].append(
                {
                    "layer_idx": 99,
                    "hook_site": "residual_stream",
                }
            )

        report = self.mutated_report(mutate)

        self.assertEqual(report["overall_status"], "failed")
        self.assertIn("exact_activation_site_coverage", failed_check_names(report))

    def test_duplicate_activation_site_fails(self):
        """Duplicate activation layer/site rows must not silently pass."""

        def mutate(_bundle, documents, _hashes):
            duplicate = deepcopy(documents["activation_handoff"]["index_rows"][0])
            documents["activation_handoff"]["index_rows"].append(duplicate)

        report = self.mutated_report(mutate)

        self.assertEqual(report["overall_status"], "failed")
        self.assertIn("targets_to_activations", failed_join_names(report))
        self.assertIn("exact_activation_site_coverage", failed_check_names(report))

    def test_corrupt_token_positions_fail(self):
        """Stored token-map ranges must be validated, not merely generated."""

        def mutate(_bundle, documents, _hashes):
            documents["token_map"]["rows"][0]["frame_token_positions"][0] = 999

        report = self.mutated_report(mutate)

        self.assertEqual(report["overall_status"], "failed")
        self.assertIn("token_map_matches_mineworld_layout", failed_check_names(report))

    def test_wrong_intervention_timestep_fails(self):
        """Rollout intervention location must match the request."""

        def mutate(_bundle, documents, _hashes):
            documents["rollout_manifest"]["rollout_rows"][0]["timestep_idx"] = 7

        report = self.mutated_report(mutate)

        self.assertEqual(report["overall_status"], "failed")
        self.assertIn("intervention_request_matches_rollouts", failed_check_names(report))

    def test_wrong_alpha_metadata_fails(self):
        """Rollout alpha metadata must match the request."""

        def mutate(_bundle, documents, _hashes):
            documents["rollout_manifest"]["rollout_rows"][1]["alpha_requested"] = 0.75
            documents["rollout_manifest"]["rollout_rows"][1]["alpha_applied"] = 0.75

        report = self.mutated_report(mutate)

        self.assertEqual(report["overall_status"], "failed")
        self.assertIn("intervention_request_matches_rollouts", failed_check_names(report))

    def test_stale_registry_context_hash_fails(self):
        """Registry context hash must match actual loaded file bytes."""

        def mutate(_bundle, documents, _hashes):
            artifact_id = documents["rollout_manifest"]["rollout_rows"][0][
                "input_context_artifact_id"
            ]

            for artifact in documents["registry"]["artifacts"]:
                if artifact["artifact_id"] == artifact_id:
                    artifact["sha256"] = "8" * 64

        report = self.mutated_report(mutate)

        self.assertEqual(report["overall_status"], "failed")
        self.assertIn(
            "registry_input_hashes_match_actual_file_bytes",
            failed_check_names(report),
        )

    def test_request_manifest_event_mismatch_fails(self):
        """Request manifest event IDs must match the actual manifest document."""

        def mutate(_bundle, documents, _hashes):
            documents["intervention_request"]["fit_manifest"]["event_ids"] = [
                "different_event"
            ]

        report = self.mutated_report(mutate)

        self.assertEqual(report["overall_status"], "failed")
        self.assertIn("request_manifest_metadata_resolves", failed_check_names(report))

    def test_duplicate_context_id_fails(self):
        """Each logical input context must resolve exactly once."""

        def mutate(_bundle, documents, _hashes):
            rows = documents["input_contexts"]["rows"]
            rows[1]["input_context_id"] = rows[0]["input_context_id"]

        report = self.mutated_report(mutate)

        self.assertEqual(report["overall_status"], "failed")
        self.assertIn("contexts_to_rollouts", failed_join_names(report))
        self.assertIn("logical_input_contexts_resolve_exactly", failed_check_names(report))

    def test_generation_failure_zero_displacement_fails(self):
        """Generation failure must not become zero displacement."""
        document = deepcopy(
            self.report["person_e_measurement_handoff"]["measurement_document"]
        )
        row = next(
            row for row in document["rows"] if row["measurement_status"] == "generation_failure"
        )
        row["displacement_blocks"] = 0.0
        with self.assertRaises(MeasurementError):
            build_measurement_document(
                document["rows"],
                rollout_manifest=self.documents["rollout_manifest"],
                registry=self.documents["registry"],
                accepted_rollout_manifest_hash=document[
                    "accepted_rollout_manifest_hash"
                ],
                accepted_registry_hash=document["accepted_registry_hash"],
                measurement_evidence=document["measurement_evidence"],
                result_scope="known_answer",
            )

    def test_non_persistence_zero_displacement_fails(self):
        """Non-persistence must not become zero displacement."""

        document = deepcopy(
            self.report["person_e_measurement_handoff"]["measurement_document"]
        )
        row = next(
            row for row in document["rows"] if row["measurement_status"] == "non_persistence"
        )
        row["displacement_blocks"] = 0.0
        result = validate_measurement_input(
            document,
            rollout_manifest=self.documents["rollout_manifest"],
            registry=self.documents["registry"],
        )
        self.assertFalse(result.accepted)

    def test_missing_measurement_fails(self):
        """Every rollout must receive exactly one measurement row."""

        document = deepcopy(
            self.report["person_e_measurement_handoff"]["measurement_document"]
        )
        document["rows"].pop()
        result = validate_measurement_input(
            document,
            rollout_manifest=self.documents["rollout_manifest"],
            registry=self.documents["registry"],
        )
        self.assertFalse(result.accepted)

    def test_duplicate_measurement_fails(self):
        """Duplicate rollout measurements must not pass."""

        document = deepcopy(
            self.report["person_e_measurement_handoff"]["measurement_document"]
        )
        document["rows"].append(deepcopy(document["rows"][0]))
        result = validate_measurement_input(
            document,
            rollout_manifest=self.documents["rollout_manifest"],
            registry=self.documents["registry"],
        )
        self.assertFalse(result.accepted)

    def test_current_d_and_e_boundaries_use_real_validators(self):
        d = self.report["person_d_baseline_handoff"]
        e = self.report["person_e_measurement_handoff"]
        self.assertEqual(d["status"], "passed")
        self.assertEqual(d["prediction_counts"], {"last_seen": 15, "constant_velocity": 15})
        self.assertEqual(
            d["heldout_identity_hashes"]["last_seen"],
            d["heldout_identity_hashes"]["constant_velocity"],
        )
        self.assertTrue(d["b_validation"]["accepted"])
        self.assertEqual(e["status"], "passed")
        self.assertTrue(e["validation"]["accepted"])
        self.assertEqual(len(e["evidence_documents"]), 3)
        for evidence in e["evidence_documents"]:
            validate_measurement_evidence(evidence)

    def test_d_illegal_feature_fold_and_stale_provenance_fail(self):
        document = deepcopy(
            self.report["person_d_baseline_handoff"]["baseline_document"]
        )
        expected = {
            (row["trajectory_id"], row["model_frame_idx"]): row["fold_idx"]
            for row in document["rows"]
        }
        illegal = deepcopy(document)
        illegal["feature_access"].append("x_true_blocks")
        self.assertFalse(
            validate_baseline_input(illegal, expected_fold_by_frame=expected).accepted
        )
        wrong_fold = deepcopy(document)
        wrong_fold["rows"][0]["fold_idx"] = (wrong_fold["rows"][0]["fold_idx"] + 1) % 5
        self.assertFalse(
            validate_baseline_input(wrong_fold, expected_fold_by_frame=expected).accepted
        )
        stale = deepcopy(document)
        stale["fit_manifest_hash"] = "stale"
        self.assertFalse(
            validate_baseline_input(stale, expected_fold_by_frame=expected).accepted
        )

    def test_e_evidence_payload_and_reference_hash_tampering_fail(self):
        handoff = self.report["person_e_measurement_handoff"]
        evidence = deepcopy(handoff["evidence_documents"][0])
        evidence["payload"]["outcome"] = "tampered"
        with self.assertRaises(MeasurementError):
            validate_measurement_evidence(evidence)
        document = deepcopy(handoff["measurement_document"])
        document["measurement_evidence"][0]["sha256"] = "0" * 64
        with self.assertRaises(MeasurementError):
            build_measurement_document(
                document["rows"],
                rollout_manifest=self.documents["rollout_manifest"],
                registry=self.documents["registry"],
                accepted_rollout_manifest_hash=document[
                    "accepted_rollout_manifest_hash"
                ],
                accepted_registry_hash=document["accepted_registry_hash"],
                measurement_evidence=document["measurement_evidence"],
                result_scope="known_answer",
            )

    def test_pipeline_report_is_deterministic(self):
        """Running the same synthetic evidence twice must give the same report."""

        second_report = run_synthetic_pipeline()

        self.assertEqual(self.report, second_report)

    def test_checked_machine_readable_report_matches_fresh_execution(self):
        """The saved Step 1.7 evidence must not lag behind the actual runner."""

        checked_report = json.loads(DEFAULT_REPORT_PATH.read_text(encoding="utf-8"))

        self.assertEqual(checked_report, self.report)

    def test_every_saved_compact_artifact_validates_exactly_as_stored(self):
        """Checked prediction and U1 projections must carry hashes over saved bytes."""

        checked_report = json.loads(DEFAULT_REPORT_PATH.read_text(encoding="utf-8"))

        for run in checked_report["authenticated_a_b_probe_bridge"]["probe_runs"]:
            for artifact_name in ("prediction_artifact", "u1_result_artifact"):
                with self.subTest(
                    layer=run["layer_idx"],
                    site=run["hook_site"],
                    artifact=artifact_name,
                ):
                    artifact = run[artifact_name]
                    validate_sealed_artifact(artifact)
                    self.assertNotEqual(
                        artifact["artifact_hash"],
                        artifact["uncompacted_artifact_hash"],
                    )
                    self.assertTrue(artifact["synthetic"])
                    self.assertEqual(artifact["scientific_use"], "forbidden")


if __name__ == "__main__":
    unittest.main()
