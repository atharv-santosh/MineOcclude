"""Step 7.3 — the integrated stage graph runs synthetically and gates correctly."""

from __future__ import annotations

import unittest

from mineocclude.experiments.stage_graph import (
    MVP_STAGES,
    ExecutionMode,
    StageError,
    StageErrorCode,
    StageSpec,
    StageStatus,
    describe_graph,
    hash_value,
    run_stage_graph,
)

IDENTITY = {
    "model_hash": "a" * 64,
    "config_hash": "b" * 64,
    "code_sha": "c" * 40,
    "seed": 20260725,
}


def _handlers():
    def manifest_validation(_context):
        return {"expected_vs_accepted_matrix": {"accepted_cell_count": 5}}

    def oracle(context):
        context.require("expected_vs_accepted_matrix")
        return {"oracle_targets": {"owner": "person_b_analysis"}}

    def model_extraction(context):
        context.require("expected_vs_accepted_matrix")
        return {"activation_index": {"rows": 100}, "queue_status": {"pending": 0}}

    def activation_audit(context):
        context.require("activation_index")
        return {"activation_audit_report": {"complete": True}}

    def probes(context):
        context.require("activation_audit_report")
        return {"probe_results": {"owner": "person_b_analysis"}}

    def baselines(context):
        context.require("activation_audit_report")
        return {"baseline_results": {"owner": "person_d_baselines"}}

    def u1_u3_metrics(context):
        context.require("probe_results")
        return {"u1_u3_metrics": {"owner": "person_b_analysis"}}

    def u4_generation(context):
        context.require("u1_u3_metrics")
        return {"rollout_manifest": {"clips": 70}, "rollout_bundle": {"clips": 0}}

    def measurement(context):
        context.require("rollout_bundle")
        return {"measurement_tables": {"owner": "person_e_operations"}}

    return {
        "manifest_validation": manifest_validation,
        "oracle": oracle,
        "model_extraction": model_extraction,
        "activation_audit": activation_audit,
        "probes": probes,
        "baselines": baselines,
        "u1_u3_metrics": u1_u3_metrics,
        "u4_generation": u4_generation,
        "measurement": measurement,
    }


class GraphDescriptionTests(unittest.TestCase):
    def test_graph_orders_stages_by_dependency(self):
        document = describe_graph()
        order = document["execution_order"]
        self.assertLess(
            order.index("manifest_validation"), order.index("model_extraction")
        )
        self.assertLess(order.index("activation_audit"), order.index("probes"))
        self.assertLess(order.index("u1_u3_metrics"), order.index("u4_generation"))
        self.assertLess(order.index("u4_generation"), order.index("measurement"))

    def test_scientific_stages_stay_with_their_owning_roles(self):
        document = describe_graph()
        self.assertIn("probes", document["delegated_stages"])
        self.assertIn("baselines", document["delegated_stages"])
        self.assertIn("measurement", document["delegated_stages"])
        self.assertIn("model_extraction", document["person_a_owned_stages"])

    def test_every_consumed_boundary_has_exactly_one_producer(self):
        document = describe_graph()
        producers = document["boundary_producers"]
        for stage in document["stages"]:
            for name in stage["consumes"]:
                self.assertIn(name, producers)

    def test_cyclic_graph_is_rejected(self):
        stages = (
            StageSpec(stage_id="a", owner="o", description="", requires=("b",)),
            StageSpec(stage_id="b", owner="o", description="", requires=("a",)),
        )
        with self.assertRaises(StageError) as caught:
            describe_graph(stages)
        self.assertIs(caught.exception.code, StageErrorCode.CYCLIC_GRAPH)

    def test_unknown_dependency_is_rejected(self):
        stages = (
            StageSpec(stage_id="a", owner="o", description="", requires=("z",)),
        )
        with self.assertRaises(StageError) as caught:
            describe_graph(stages)
        self.assertIs(caught.exception.code, StageErrorCode.UNKNOWN_STAGE)


class SyntheticExecutionTests(unittest.TestCase):
    def test_synthetic_pipeline_runs_cleanly_end_to_end(self):
        report = run_stage_graph(
            _handlers(),
            mode=ExecutionMode.SYNTHETIC,
            run_id="run-1",
            identity=IDENTITY,
        )
        self.assertTrue(report["complete"])
        self.assertEqual(report["completed_stage_count"], len(MVP_STAGES))
        self.assertEqual(report["scientific_use"], "forbidden")
        self.assertTrue(report["synthetic"])

    def test_every_boundary_value_is_hashed(self):
        report = run_stage_graph(
            _handlers(),
            mode=ExecutionMode.SYNTHETIC,
            run_id="run-1",
            identity=IDENTITY,
        )
        self.assertIn("activation_index", report["boundary_hashes"])
        self.assertEqual(
            report["boundary_hashes"]["activation_index"],
            hash_value({"rows": 100}),
        )


class GateTests(unittest.TestCase):
    def test_a_failed_upstream_stage_stops_every_downstream_stage(self):
        handlers = _handlers()

        def failing(_context):
            raise RuntimeError("upstream extraction failed")

        handlers["model_extraction"] = failing
        report = run_stage_graph(
            handlers,
            mode=ExecutionMode.SYNTHETIC,
            run_id="run-1",
            identity=IDENTITY,
        )
        by_id = {stage["stage_id"]: stage for stage in report["stages"]}
        self.assertEqual(by_id["model_extraction"]["status"], StageStatus.FAILED.value)
        self.assertEqual(
            by_id["activation_audit"]["status"],
            StageStatus.SKIPPED_UPSTREAM_GATE.value,
        )
        self.assertEqual(
            by_id["measurement"]["status"], StageStatus.SKIPPED_UPSTREAM_GATE.value
        )
        # An independent branch that does not depend on extraction still runs.
        self.assertEqual(by_id["oracle"]["status"], StageStatus.COMPLETED.value)
        self.assertFalse(report["complete"])

    def test_a_stage_without_an_entry_point_is_blocked_not_skipped_silently(self):
        handlers = _handlers()
        del handlers["measurement"]
        report = run_stage_graph(
            handlers,
            mode=ExecutionMode.SYNTHETIC,
            run_id="run-1",
            identity=IDENTITY,
        )
        by_id = {stage["stage_id"]: stage for stage in report["stages"]}
        self.assertEqual(by_id["measurement"]["status"], StageStatus.BLOCKED.value)
        self.assertIn("no entry point", by_id["measurement"]["detail"])

    def test_real_mode_without_entry_points_blocks_every_stage(self):
        report = run_stage_graph(
            {},
            mode=ExecutionMode.REAL,
            run_id="run-real",
            identity=IDENTITY,
        )
        self.assertEqual(report["completed_stage_count"], 0)
        self.assertEqual(report["blocked_stage_count"], len(MVP_STAGES))
        self.assertEqual(report["scientific_use"], "permitted")

    def test_real_mode_requires_exact_identity(self):
        with self.assertRaises(StageError) as caught:
            run_stage_graph(
                _handlers(),
                mode=ExecutionMode.REAL,
                run_id="run-real",
                identity={"config_hash": "b" * 64},
            )
        self.assertIs(
            caught.exception.code, StageErrorCode.REAL_MODE_IDENTITY_MISSING
        )

    def test_undeclared_output_is_rejected(self):
        handlers = _handlers()
        handlers["manifest_validation"] = lambda _c: {
            "expected_vs_accepted_matrix": {},
            "surprise": {},
        }
        with self.assertRaises(StageError) as caught:
            run_stage_graph(
                handlers,
                mode=ExecutionMode.SYNTHETIC,
                run_id="run-1",
                identity=IDENTITY,
            )
        self.assertIs(caught.exception.code, StageErrorCode.UNDECLARED_OUTPUT)

    def test_missing_declared_output_fails_the_stage(self):
        handlers = _handlers()
        handlers["model_extraction"] = lambda _c: {"activation_index": {}}
        report = run_stage_graph(
            handlers,
            mode=ExecutionMode.SYNTHETIC,
            run_id="run-1",
            identity=IDENTITY,
        )
        by_id = {stage["stage_id"]: stage for stage in report["stages"]}
        self.assertEqual(by_id["model_extraction"]["status"], StageStatus.FAILED.value)
        self.assertIn("queue_status", by_id["model_extraction"]["detail"])

    def test_declared_input_hash_mismatch_is_rejected(self):
        with self.assertRaises(StageError) as caught:
            run_stage_graph(
                _handlers(),
                mode=ExecutionMode.SYNTHETIC,
                run_id="run-1",
                identity=IDENTITY,
                declared_input_hashes={"expected_vs_accepted_matrix": "0" * 64},
            )
        self.assertIs(caught.exception.code, StageErrorCode.INPUT_HASH_MISMATCH)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
