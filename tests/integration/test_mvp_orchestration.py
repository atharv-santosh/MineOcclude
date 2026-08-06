"""End-to-end orchestration checks for the Person A MVP and U4 entry points.

Every command runs against the real repository configuration into a temporary
output root, so the test proves the documented workflow works without editing
source between commands and without writing into the published evidence tree.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


run_mvp = _load("person_a_run_mvp", ROOT / "scripts" / "run_mvp.py")
run_u4 = _load("person_a_run_u4", ROOT / "scripts" / "run_u4_rollouts.py")


class MvpCommandTests(unittest.TestCase):
    def setUp(self):
        self._directory = tempfile.TemporaryDirectory()
        self.output = Path(self._directory.name)
        self.queue_state = self.output / "extraction_queue_state.json"
        self.addCleanup(self._directory.cleanup)

    def _argv(self, *command):
        return [
            "--output-root",
            str(self.output),
            "--queue-state",
            str(self.queue_state),
            *command,
        ]

    def _read(self, name):
        return json.loads((self.output / name).read_text(encoding="utf-8"))

    def test_freeze_writes_a_signed_identity_record(self):
        self.assertEqual(run_mvp.main(self._argv("freeze")), 0)
        record = self._read("step_7_1_identity_freeze.json")
        self.assertEqual(record["status"], "FROZEN")
        self.assertEqual(len(record["validated_by_roles"]), 5)
        self.assertEqual(record["frozen_step_4_1_decision"], "FAIL")

    def test_matrix_publishes_the_expected_and_accepted_counts(self):
        self.assertEqual(run_mvp.main(self._argv("matrix")), 0)
        report = self._read("step_7_2_matrix_report.json")
        self.assertEqual(report["expected_cell_count"], 66)
        self.assertEqual(
            report["accepted_cell_count"] + report["shortfall_count"], 66
        )
        self.assertTrue(report["every_cell_has_a_state_and_owner"])

    def test_graph_publishes_the_nine_stage_graph(self):
        self.assertEqual(run_mvp.main(self._argv("graph")), 0)
        document = self._read("step_7_3_stage_graph.json")
        self.assertEqual(document["stage_count"], 9)

    def test_queue_plan_is_idempotent_and_resumable(self):
        self.assertEqual(run_mvp.main(self._argv("queue-plan")), 0)
        first = self._read("step_7_5_queue_status.json")
        self.assertEqual(run_mvp.main(self._argv("queue-plan")), 0)
        second = self._read("step_7_5_queue_status.json")
        self.assertEqual(first["identity_digest"], second["identity_digest"])
        self.assertEqual(first["item_count"], second["item_count"])

    def test_synthetic_run_completes_every_stage_and_is_registry_valid(self):
        run_mvp.main(self._argv("queue-plan"))
        self.assertEqual(run_mvp.main(self._argv("run", "--mode", "synthetic")), 0)
        report = self._read("step_7_3_synthetic_stage_report.json")
        self.assertTrue(report["complete"])
        self.assertEqual(report["completed_stage_count"], 9)
        self.assertEqual(report["scientific_use"], "forbidden")

        lineage = self._read("step_7_4_synthetic_lineage.json")
        self.assertTrue(lineage["person_e_registry_validation"]["accepted"])
        self.assertTrue(lineage["synthetic"])
        self.assertEqual(lineage["scientific_use"], "forbidden")

    def test_real_run_blocks_every_stage_without_real_entry_points(self):
        run_mvp.main(self._argv("queue-plan"))
        run_mvp.main(self._argv("run", "--mode", "real"))
        report = self._read("step_7_3_real_stage_report.json")
        self.assertFalse(report["complete"])
        self.assertEqual(report["completed_stage_count"], 0)
        self.assertEqual(report["blocked_stage_count"], 9)
        self.assertEqual(report["scientific_use"], "permitted")

    def test_u1_u3_records_a_blocked_invocation_with_its_reason(self):
        run_mvp.main(self._argv("queue-plan"))
        self.assertEqual(run_mvp.main(self._argv("u1-u3")), 0)
        record = self._read("step_7_7_u1_u3_invocation.json")
        self.assertEqual(record["status"], "BLOCKED")
        self.assertIn("not complete", record["blocked_reason"])
        self.assertFalse(record["metrics_interpreted_by_person_a"])

    def test_closeout_reports_implementation_complete_with_external_blockers(self):
        run_mvp.main(self._argv("queue-plan"))
        run_mvp.main(self._argv("u1-u3"))
        self.assertEqual(run_mvp.main(self._argv("closeout")), 0)
        document = self._read("step_7_8_implementation_closeout.json")
        self.assertEqual(
            document["status"], "IMPLEMENTATION_COMPLETE_EXECUTION_BLOCKED"
        )
        self.assertEqual(document["failing_gate_ids"], [])
        self.assertFalse(document["real_extraction_executed"])
        self.assertFalse(
            document["real_data_steps_claimed_from_synthetic_evidence"]
        )
        self.assertTrue(document["external_blockers"])

    def test_a_changed_run_identity_supersedes_rather_than_resumes(self):
        run_mvp.main(self._argv("queue-plan"))
        state = json.loads(self.queue_state.read_text(encoding="utf-8"))
        state["identity"]["config_hash"] = "0" * 64
        self.queue_state.write_text(json.dumps(state), encoding="utf-8")

        self.assertEqual(run_mvp.main(self._argv("queue-plan")), 0)
        archived = list(self.output.glob("*.superseded.*.json"))
        self.assertEqual(len(archived), 1)
        document = json.loads(archived[0].read_text(encoding="utf-8"))
        self.assertIn("superseded_by_run_id", document)


class U4CommandTests(unittest.TestCase):
    def setUp(self):
        self._directory = tempfile.TemporaryDirectory()
        self.output = Path(self._directory.name)
        self.addCleanup(self._directory.cleanup)

    def _read(self, name):
        return json.loads((self.output / name).read_text(encoding="utf-8"))

    def test_an_incomplete_request_is_rejected_and_recorded(self):
        request = self.output / "request.json"
        request.write_text(json.dumps({"schema_version": "1.0"}), encoding="utf-8")
        exit_code = run_u4.main(
            [
                "--output-root",
                str(self.output),
                "validate-request",
                "--request",
                str(request),
            ]
        )
        self.assertEqual(exit_code, 1)
        report = self._read("step_8_1_request_validation.json")
        self.assertEqual(report["status"], "REJECTED")
        self.assertTrue(report["rejections"])
        self.assertEqual(len(report["request_sha256"]), 64)

    def test_manifest_freeze_refuses_a_rejected_request(self):
        request = self.output / "request.json"
        request.write_text(json.dumps({"schema_version": "1.0"}), encoding="utf-8")
        exit_code = run_u4.main(
            [
                "--output-root",
                str(self.output),
                "freeze-manifest",
                "--request",
                str(request),
            ]
        )
        self.assertEqual(exit_code, 1)
        self.assertFalse((self.output / "step_8_5_rollout_manifest.json").is_file())

    def test_classification_without_evidence_is_invalid_not_causal(self):
        exit_code = run_u4.main(
            ["--output-root", str(self.output), "classify"]
        )
        self.assertEqual(exit_code, 0)
        document = self._read("step_8_8_u4_classification.json")
        self.assertEqual(document["classification"], "invalid_measurement")
        self.assertFalse(document["causal_claim_made"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
