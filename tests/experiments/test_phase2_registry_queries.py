from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from mineocclude.experiments.registry import (
    ImmutableRegistryIndex,
    ProvenanceError,
    require_valid_immutable_registry,
    validate_phase2_step2_1_blocker_record,
)
from scripts.build_person_e_phase2_evidence import (
    A_SESSION_IDS,
    PERSON_A_REGISTRY_HANDOFF_REVISION,
    PERSON_A_SOURCE_REVISION,
    PERSON_C_REGISTRY_HANDOFF_REVISION,
    PERSON_C_REGISTRY_SOURCE_REVISION,
    build_phase2_step2_1_documents,
    load_phase2_registry_handoffs,
)
from tests.experiments.test_immutable_registry_contract import (
    in_progress_snapshot,
    superseding_registry,
)

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs" / "status" / "person_e_phase2_v0_1"


def load_evidence(name: str) -> dict[str, object]:
    return json.loads((EVIDENCE / name).read_text(encoding="utf-8"))


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


class TestAuthoritativePhase2Registry(unittest.TestCase):
    def test_exact_owner_revisions_and_shared_validation(self) -> None:
        registry = load_evidence("registry_snapshot.json")
        receipt = load_evidence("step2_1_registry_receipt.json")
        self.assertTrue(require_valid_immutable_registry(registry).accepted)
        self.assertFalse(registry["synthetic"])
        self.assertEqual(registry["scientific_use"], "permitted")
        self.assertEqual(
            receipt["owner_handoff_revisions"],
            {
                "person_a": PERSON_A_REGISTRY_HANDOFF_REVISION,
                "person_c": PERSON_C_REGISTRY_HANDOFF_REVISION,
            },
        )
        self.assertEqual(
            receipt["owner_source_revisions"],
            {
                "person_a": PERSON_A_SOURCE_REVISION,
                "person_c": PERSON_C_REGISTRY_SOURCE_REVISION,
            },
        )
        self.assertFalse(receipt["historical_episode_9410_registered"])
        self.assertNotIn("9410", json.dumps(registry, sort_keys=True))

    def test_run_queries_preserve_failures_and_completed_runs(self) -> None:
        registry = load_evidence("registry_snapshot.json")
        query = load_evidence("registry_query_example.json")
        index = ImmutableRegistryIndex(registry)
        all_runs = index.query_runs()
        failed = index.query_runs(statuses=["failed"])
        completed = index.query_runs(statuses=["completed"])
        self.assertEqual(query["run_queries"]["all_status"], all_runs)
        self.assertEqual(query["run_queries"]["failed"], failed)
        self.assertEqual(query["run_queries"]["completed"], completed)
        self.assertEqual(len(all_runs), 4)
        self.assertEqual(
            [run["run_id"] for run in failed],
            [
                f"{A_SESSION_IDS[0]}-step2.6",
                f"{A_SESSION_IDS[1]}-step2.6",
            ],
        )
        self.assertEqual(
            {run["owner"] for run in completed},
            {"person_a", "person_c"},
        )

    def test_accepted_artifacts_have_completed_creators(self) -> None:
        registry = load_evidence("registry_snapshot.json")
        receipt = load_evidence("step2_1_registry_receipt.json")
        query = load_evidence("registry_query_example.json")
        runs = {run["run_id"]: run for run in registry["runs"]}
        accepted = query["artifact_queries"]["accepted_only"]
        failed_artifacts = query["artifact_queries"][
            "failed_creator_all_status"
        ]
        self.assertEqual(receipt["accepted_artifact_count"], 28)
        self.assertEqual(len(accepted), 28)
        self.assertEqual(len(failed_artifacts), 23)
        self.assertTrue(
            all(
                artifact["status"] == "accepted"
                and runs[artifact["creator_run_id"]]["status"]
                == "completed"
                for artifact in accepted
            )
        )
        self.assertTrue(
            all(
                artifact["status"] == "excluded"
                and runs[artifact["creator_run_id"]]["status"] == "failed"
                for artifact in failed_artifacts
            )
        )

    def test_queries_and_registry_records_are_deterministically_ordered(
        self,
    ) -> None:
        registry = load_evidence("registry_snapshot.json")
        query = load_evidence("registry_query_example.json")
        self.assertEqual(
            [run["run_id"] for run in registry["runs"]],
            sorted(run["run_id"] for run in registry["runs"]),
        )
        self.assertEqual(
            [artifact["artifact_id"] for artifact in registry["artifacts"]],
            sorted(
                artifact["artifact_id"] for artifact in registry["artifacts"]
            ),
        )
        for rows in query["run_queries"].values():
            self.assertEqual(
                [run["run_id"] for run in rows],
                sorted(run["run_id"] for run in rows),
            )
        for rows in query["artifact_queries"].values():
            self.assertEqual(
                [artifact["artifact_id"] for artifact in rows],
                sorted(artifact["artifact_id"] for artifact in rows),
            )

    def test_owner_handoff_tampering_is_rejected(self) -> None:
        cases = []

        timestamp = load_phase2_registry_handoffs()
        timestamp["person_a"]["sessions"][A_SESSION_IDS[0]]["run_record"][
            "document"
        ]["started_at"] = "2026-07-27T23:51:19Z"
        cases.append(("timestamp", timestamp))

        artifact_hash = load_phase2_registry_handoffs()
        artifact_hash["person_c"]["artifact_verification"]["document"][
            "artifacts"
        ][0]["observed_sha256"] = "0" * 64
        cases.append(("hash", artifact_hash))

        incomplete = load_phase2_registry_handoffs()
        incomplete["person_c"]["attempt_scope"]["document"][
            "inventory_is_authoritative_and_complete_for_scope"
        ] = False
        cases.append(("attempt inventory", incomplete))

        invalid_verification = load_phase2_registry_handoffs()
        invalid_verification["person_a"]["sessions"][A_SESSION_IDS[-1]][
            "artifact_verification"
        ]["document"]["verification_result"] = "fail"
        cases.append(("verification", invalid_verification))

        for name, handoffs in cases:
            with self.subTest(name=name), self.assertRaises(ValueError):
                build_phase2_step2_1_documents(handoffs)

    def test_receipt_and_status_do_not_overclaim_step2_4(self) -> None:
        receipt = load_evidence("step2_1_registry_receipt.json")
        status = load_evidence("phase2_status.json")
        self.assertEqual(receipt["step"], "2.1")
        self.assertEqual(receipt["status"], "PASS")
        self.assertEqual(status["overall_status"], "PARTIAL")
        steps = {step["step"]: step for step in status["steps"]}
        self.assertEqual(steps["2.1"]["status"], "PASS")
        self.assertEqual(steps["2.4"]["status"], "PARTIAL")
        self.assertFalse(status["homography_planning_gate_passed"])


if __name__ == "__main__":
    unittest.main()
