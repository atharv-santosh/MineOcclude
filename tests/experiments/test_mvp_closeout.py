"""Step 7.8 — the implementation closeout never overstates what was produced."""

from __future__ import annotations

import unittest

from mineocclude.experiments.mvp_closeout import (
    ArtifactIndexEntry,
    CloseoutError,
    CloseoutErrorCode,
    Gate,
    GateState,
    U4Readiness,
    build_mvp_closeout,
)

IDENTITY = {"config_hash": "a" * 64, "code_sha": "b" * 40}


def _gates(**overrides):
    states = {
        "model_runtime": GateState.PASS,
        "input_alignment": GateState.PASS,
        "hook_site": GateState.PASS,
        "storage": GateState.PASS,
        "reproducibility": GateState.PASS,
    }
    states.update(overrides)
    return tuple(
        Gate(gate_id=name, state=state, evidence=f"docs/{name}.json")
        for name, state in states.items()
    )


def _matrix(accepted=5, expected=66):
    return {
        "accepted_cell_count": accepted,
        "expected_cell_count": expected,
        "shortfall_count": expected - accepted,
        "shortfall_owners": ["person_c_data"] if accepted < expected else [],
    }


def _cardinality(completed=0, queued=5, complete=False):
    return {
        "completed_item_count": completed,
        "queued_item_count": queued,
        "complete": complete,
    }


def _artifacts(real=True):
    return (
        ArtifactIndexEntry(
            artifact_id="a1",
            artifact_type="activation",
            uri="s3://bucket/a1",
            sha256="c" * 64,
            owner="person_a_model",
            real=real,
        ),
    )


class CompletenessTests(unittest.TestCase):
    def test_an_incomplete_queue_is_reported_visibly_short(self):
        document = build_mvp_closeout(
            identity=IDENTITY,
            matrix_report=_matrix(),
            queue_status={"forecast": {"seconds_per_frame": 1.1}},
            cardinality_report=_cardinality(),
            gates=_gates(),
            artifact_index=_artifacts(),
            capacity={"bytes_per_model_frame": 163853.66},
        )
        self.assertTrue(document["queue_completeness"]["visibly_short"])
        self.assertEqual(document["queue_completeness"]["shortfall_count"], 61)
        self.assertEqual(
            document["queue_completeness"]["shortfall_owners"], ["person_c_data"]
        )

    def test_a_failing_gate_blocks_the_closeout(self):
        document = build_mvp_closeout(
            identity=IDENTITY,
            matrix_report=_matrix(),
            queue_status={},
            cardinality_report=_cardinality(),
            gates=_gates(reproducibility=GateState.FAIL),
            artifact_index=_artifacts(),
            capacity={},
        )
        self.assertEqual(document["status"], "BLOCKED")
        self.assertEqual(document["failing_gate_ids"], ["reproducibility"])
        self.assertEqual(document["u4_readiness"], U4Readiness.BLOCKED.value)

    def test_external_blockers_change_the_status_without_failing_a_gate(self):
        document = build_mvp_closeout(
            identity=IDENTITY,
            matrix_report=_matrix(),
            queue_status={},
            cardinality_report=_cardinality(),
            gates=_gates(),
            artifact_index=_artifacts(),
            capacity={},
            external_blockers=({"blocker_id": "C-66", "owner": "person_c_data"},),
        )
        self.assertEqual(
            document["status"], "IMPLEMENTATION_COMPLETE_EXECUTION_BLOCKED"
        )
        self.assertEqual(document["failing_gate_ids"], [])

    def test_a_closeout_needs_at_least_one_gate(self):
        with self.assertRaises(CloseoutError) as caught:
            build_mvp_closeout(
                identity=IDENTITY,
                matrix_report=_matrix(),
                queue_status={},
                cardinality_report=_cardinality(),
                gates=(),
                artifact_index=_artifacts(),
                capacity={},
            )
        self.assertIs(caught.exception.code, CloseoutErrorCode.INVALID_REQUEST)


class U4ReadinessTests(unittest.TestCase):
    def _complete(self, **overrides):
        kwargs = dict(
            identity=IDENTITY,
            matrix_report=_matrix(accepted=66),
            queue_status={},
            cardinality_report=_cardinality(completed=66, queued=66, complete=True),
            gates=_gates(),
            artifact_index=_artifacts(),
            capacity={},
            person_b_typical_norm_path_confirmed=True,
            person_e_rollout_schema_confirmed=True,
            real_extraction_executed=True,
        )
        kwargs.update(overrides)
        return build_mvp_closeout(**kwargs)

    def test_a_complete_real_run_with_prerequisites_is_scientific(self):
        self.assertEqual(
            self._complete()["u4_readiness"], U4Readiness.SCIENTIFIC.value
        )

    def test_a_missing_b_norm_path_blocks_u4(self):
        document = self._complete(person_b_typical_norm_path_confirmed=False)
        self.assertEqual(document["u4_readiness"], U4Readiness.BLOCKED.value)
        self.assertIn("typical activation norm", document["u4_readiness_reason"])

    def test_no_real_extraction_caps_u4_at_plumbing_only(self):
        document = self._complete(
            real_extraction_executed=False, artifact_index=_artifacts(real=False)
        )
        self.assertEqual(document["u4_readiness"], U4Readiness.PLUMBING_ONLY.value)

    def test_an_incomplete_dataset_blocks_u4(self):
        document = self._complete(
            matrix_report=_matrix(accepted=5),
            cardinality_report=_cardinality(),
        )
        self.assertEqual(document["u4_readiness"], U4Readiness.BLOCKED.value)


class EvidenceHonestyTests(unittest.TestCase):
    def test_a_real_run_cannot_be_claimed_from_synthetic_artifacts(self):
        with self.assertRaises(CloseoutError) as caught:
            build_mvp_closeout(
                identity=IDENTITY,
                matrix_report=_matrix(),
                queue_status={},
                cardinality_report=_cardinality(),
                gates=_gates(),
                artifact_index=_artifacts(real=False),
                capacity={},
                real_extraction_executed=True,
            )
        self.assertIs(caught.exception.code, CloseoutErrorCode.SYNTHETIC_AS_REAL)

    def test_metrics_are_never_interpreted_by_the_closeout(self):
        document = build_mvp_closeout(
            identity=IDENTITY,
            matrix_report=_matrix(),
            queue_status={},
            cardinality_report=_cardinality(),
            gates=_gates(),
            artifact_index=_artifacts(),
            capacity={},
        )
        self.assertFalse(document["metrics_interpreted"])
        self.assertFalse(
            document["real_data_steps_claimed_from_synthetic_evidence"]
        )

    def test_superseded_runs_and_their_downstream_outputs_are_listed(self):
        document = build_mvp_closeout(
            identity=IDENTITY,
            matrix_report=_matrix(),
            queue_status={},
            cardinality_report=_cardinality(),
            gates=_gates(),
            artifact_index=_artifacts(),
            capacity={},
            superseded_runs=(
                {
                    "run_id": "old",
                    "superseded_by": "new",
                    "affected_outputs": ["metric_table_1"],
                },
            ),
        )
        self.assertEqual(len(document["superseded_runs"]), 1)
        self.assertEqual(
            document["affected_downstream_outputs"], ["metric_table_1"]
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
