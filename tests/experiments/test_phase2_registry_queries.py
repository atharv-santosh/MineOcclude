from __future__ import annotations

import copy
import unittest

from mineocclude.experiments.registry import (
    ImmutableRegistryIndex,
    ProvenanceError,
    validate_phase2_step2_1_blocker_record,
)
from tests.experiments.test_immutable_registry_contract import (
    in_progress_snapshot,
    superseding_registry,
)


def blocker_record() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "blocker_schema_version": "person-e-phase2-step2.1-blocker-v0.1",
        "record_id": "person_e_phase2_step2_1_blockers_v0_1",
        "step": "2.1",
        "status": "BLOCKED",
        "pass_claimed": False,
        "real_completed_records_emitted": False,
        "located_committed_metadata": {"person_a": True, "person_c": True},
        "source_revisions": {
            "person_a_execution_revision": (
                "35baf673312af5c21ae3f22168de405bd4ee8bd9"
            ),
            "person_a_evidence_revision": (
                "e5032cc00dd83716df6f8e1b863659477adddb95"
            ),
            "person_c_pilot_revision": (
                "82ef1212091b3f32eac02d7eabe25d55376086f2"
            ),
        },
        "missing_authoritative_fields": [
            {
                "authority": "person_a",
                "record_id": (
                    "person-a-phase2-aws-20260725-055616-step2.6"
                ),
                "fields": ["started_at", "ended_at"],
            },
            {
                "authority": "person_c",
                "record_id": "layout_00_ep9410",
                "fields": ["started_at", "ended_at"],
            },
            {
                "authority": "person_a",
                "record_id": (
                    "person-a-phase2-aws-20260725-055616-step2.6"
                ),
                "fields": ["external_artifact_byte_verification_authority"],
            },
            {
                "authority": "person_a",
                "record_id": "failed_attempts",
                "fields": ["authoritative_failed_attempt_registry_metadata"],
            },
        ],
        "non_inference": {
            "timestamps_inferred": False,
            "external_byte_authority_inferred": False,
            "failed_attempts_manufactured": False,
        },
        "decision": "blocked_not_failed",
    }


class TestImmutableRegistryQueries(unittest.TestCase):
    def test_all_status_and_accepted_only_queries_are_deterministic(self) -> None:
        document = superseding_registry()
        document["runs"].reverse()
        document["artifacts"].reverse()
        index = ImmutableRegistryIndex(document)
        all_artifacts = index.query_artifacts()
        self.assertEqual(
            [row["artifact_id"] for row in all_artifacts],
            sorted(row["artifact_id"] for row in all_artifacts),
        )
        self.assertIn(
            "artifact_metric",
            [row["artifact_id"] for row in all_artifacts],
        )
        accepted_ids = [
            row["artifact_id"] for row in index.accepted_artifacts()
        ]
        self.assertNotIn("artifact_metric", accepted_ids)
        self.assertIn("artifact_metric_corrected", accepted_ids)
        superseded = index.query_artifacts(statuses=["superseded"])
        self.assertEqual(
            [row["artifact_id"] for row in superseded],
            ["artifact_metric"],
        )

    def test_forward_and_backward_lineage_are_canonical(self) -> None:
        index = ImmutableRegistryIndex(superseding_registry())
        forward = index.forward_lineage("artifact_raw_trajectory")
        backward = index.backward_lineage("artifact_metric_corrected")
        self.assertEqual(
            [row["artifact_id"] for row in forward["artifact_nodes"]],
            sorted(row["artifact_id"] for row in forward["artifact_nodes"]),
        )
        self.assertEqual(
            [row["artifact_id"] for row in backward["artifact_nodes"]],
            [
                "artifact_activation",
                "artifact_model_input",
                "artifact_prediction",
                "artifact_raw_trajectory",
            ],
        )
        self.assertEqual(
            forward["direct_input_edges"],
            sorted(
                forward["direct_input_edges"],
                key=lambda row: (
                    row["input_artifact_id"],
                    row["output_artifact_id"],
                ),
            ),
        )

    def test_failed_run_remains_queryable(self) -> None:
        failed = in_progress_snapshot()
        run = next(
            row for row in failed["runs"] if row["run_id"] == "run_metric"
        )
        run.update(
            {
                "status": "failed",
                "ended_at": "2026-01-01T00:00:09Z",
                "failure_reason": "Synthetic expected failure.",
            }
        )
        index = ImmutableRegistryIndex(failed)
        self.assertEqual(
            [row["run_id"] for row in index.query_runs(statuses=["failed"])],
            ["run_metric"],
        )
        self.assertTrue(
            all(
                row["creator_run_id"] != "run_metric"
                for row in index.accepted_artifacts()
            )
        )


class TestPhase2BlockerRecord(unittest.TestCase):
    def test_exact_non_inferential_record_passes(self) -> None:
        validate_phase2_step2_1_blocker_record(blocker_record())

    def test_pass_claim_or_inferred_timestamp_is_rejected(self) -> None:
        for field, value in (
            ("pass_claimed", True),
            ("status", "PASS"),
        ):
            with self.subTest(field=field):
                document = copy.deepcopy(blocker_record())
                document[field] = value
                with self.assertRaises(ProvenanceError):
                    validate_phase2_step2_1_blocker_record(document)
        inferred = copy.deepcopy(blocker_record())
        inferred["non_inference"]["timestamps_inferred"] = True
        with self.assertRaises(ProvenanceError):
            validate_phase2_step2_1_blocker_record(inferred)


if __name__ == "__main__":
    unittest.main()
