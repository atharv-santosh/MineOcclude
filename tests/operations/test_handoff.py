"""Step 7.3 contract tests: a second operator must be able to run E alone."""

from __future__ import annotations

import copy
import unittest

from mineocclude.operations.handoff import (
    OPERATING_HANDOFF_SCHEMA_VERSION,
    REQUIRED_WORKFLOWS,
    OperatingHandoffError,
    build_operating_handoff,
    build_second_operator_receipt,
    validate_external_artifact_index,
    validate_external_dependencies,
    validate_frozen_version_table,
    validate_operating_handoff,
    validate_second_operator_receipt,
    validate_workflow,
)

DIGEST = "c" * 64


def workflow(name: str, **overrides) -> dict:
    row = {
        "workflow": name,
        "runbook_path": f"docs/runbooks/person_e_{name}_runbook.md",
        "required_inputs": ["accepted upstream manifest"],
        "commands": [["scripts/measure_u4.py", "--help"]],
        "validators": ["tests/vision/test_u4_pipeline.py"],
        "outputs": ["docs/status/<package>/validation_receipt.json"],
        "failure_behavior": "fail closed and record the exact rejected record",
        "version_and_supersession_rules": (
            "corrections create a new versioned successor; nothing is overwritten"
        ),
        "escalation_owner": "person_a",
        "permitted_operational_reruns": ["rerun with identical inputs"],
        "requires_ab_review": ["any threshold or metric change"],
    }
    row.update(overrides)
    return row


def workflows() -> list[dict]:
    return [workflow(name) for name in REQUIRED_WORKFLOWS]


VERSION_TABLE = [
    {
        "component": "magenta_detector",
        "version": "hsv-largest-valid-blob-v1.0",
        "owner": "person_e",
        "sha256": DIGEST,
    }
]

EXTERNAL_INDEX = [
    {
        "artifact_id": "person_a_activation_store",
        "owner": "person_a",
        "recorded_path": "/home/sagemaker-user/person-a-phase6-approved-outputs",
        "availability": "external_unmounted",
        "sha256": None,
    }
]

DEPENDENCIES = [
    {
        "dependency_id": "person_a_u4_rollout_clips",
        "owner": "person_a",
        "blocks_step": "6.1",
        "next_command": ["scripts/measure_u4.py", "<manifest>", "<registry>"],
    }
]


def build(**overrides):
    defaults = {
        "workflows": workflows(),
        "frozen_version_table": VERSION_TABLE,
        "external_artifact_index": EXTERNAL_INDEX,
        "remaining_external_dependencies": DEPENDENCIES,
        "paper_workspace_plan_path": "docs/operations/person_e_paper_workspace_plan.md",
        "code_commit": "0" * 40,
    }
    defaults.update(overrides)
    return build_operating_handoff(**defaults)


class TestWorkflow(unittest.TestCase):
    def test_complete_workflow_validates(self) -> None:
        self.assertEqual(validate_workflow(workflow("registry"))["workflow"], "registry")

    def test_unknown_workflow_rejects(self) -> None:
        with self.assertRaises(OperatingHandoffError):
            validate_workflow(workflow("registry", workflow="telemetry"))

    def test_each_required_field_is_enforced(self) -> None:
        for field in (
            "commands",
            "escalation_owner",
            "failure_behavior",
            "outputs",
            "permitted_operational_reruns",
            "required_inputs",
            "requires_ab_review",
            "runbook_path",
            "validators",
            "version_and_supersession_rules",
        ):
            row = workflow("detector")
            del row[field]
            with self.assertRaises(OperatingHandoffError, msg=field):
                validate_workflow(row)

    def test_workflow_without_commands_rejects(self) -> None:
        with self.assertRaises(OperatingHandoffError):
            validate_workflow(workflow("detector", commands=[]))

    def test_workflow_claiming_no_ab_review_rejects(self) -> None:
        with self.assertRaises(OperatingHandoffError):
            validate_workflow(workflow("detector", requires_ab_review=[]))

    def test_unknown_escalation_owner_rejects(self) -> None:
        with self.assertRaises(OperatingHandoffError):
            validate_workflow(workflow("detector", escalation_owner="whoever"))


class TestSupportingTables(unittest.TestCase):
    def test_version_table_rejects_duplicates(self) -> None:
        with self.assertRaises(OperatingHandoffError):
            validate_frozen_version_table(VERSION_TABLE + copy.deepcopy(VERSION_TABLE))

    def test_version_table_rejects_bad_digest(self) -> None:
        row = copy.deepcopy(VERSION_TABLE)
        row[0]["sha256"] = "short"
        with self.assertRaises(OperatingHandoffError):
            validate_frozen_version_table(row)

    def test_external_index_requires_known_availability(self) -> None:
        row = copy.deepcopy(EXTERNAL_INDEX)
        row[0]["availability"] = "probably_there"
        with self.assertRaises(OperatingHandoffError):
            validate_external_artifact_index(row)

    def test_external_index_allows_unmounted_without_digest(self) -> None:
        self.assertEqual(len(validate_external_artifact_index(EXTERNAL_INDEX)), 1)

    def test_dependency_requires_next_command(self) -> None:
        row = copy.deepcopy(DEPENDENCIES)
        row[0]["next_command"] = []
        with self.assertRaises(OperatingHandoffError):
            validate_external_dependencies(row)

    def test_dependency_requires_blocked_step(self) -> None:
        row = copy.deepcopy(DEPENDENCIES)
        del row[0]["blocks_step"]
        with self.assertRaises(OperatingHandoffError):
            validate_external_dependencies(row)


class TestOperatingHandoff(unittest.TestCase):
    def test_handoff_builds_and_revalidates(self) -> None:
        handoff = build()
        self.assertEqual(
            handoff["operating_handoff_schema_version"],
            OPERATING_HANDOFF_SCHEMA_VERSION,
        )
        self.assertEqual(handoff["workflow_count"], len(REQUIRED_WORKFLOWS))
        validate_operating_handoff(handoff)

    def test_missing_workflow_rejects(self) -> None:
        with self.assertRaises(OperatingHandoffError):
            build(workflows=workflows()[:-1])

    def test_tampered_handoff_fails_content_hash(self) -> None:
        handoff = build()
        handoff["workflow_count"] = 99
        with self.assertRaises(OperatingHandoffError):
            validate_operating_handoff(handoff)


class TestSecondOperatorReceipt(unittest.TestCase):
    def _digests(self) -> dict:
        return {row["runbook_path"]: DIGEST for row in workflows()}

    def test_receipt_reports_operability_when_runbooks_exist(self) -> None:
        receipt = build_second_operator_receipt(
            handoff=build(),
            runbook_digests=self._digests(),
            reproduction_receipt_hash=None,
            checkpoint_evidence_hash=None,
        )
        self.assertTrue(receipt["operable_without_person_e"])
        self.assertEqual(receipt["missing_runbooks"], [])
        self.assertEqual(
            receipt["blocked_dependency_ids"], ["person_a_u4_rollout_clips"]
        )
        validate_second_operator_receipt(receipt)

    def test_missing_runbook_blocks_operability(self) -> None:
        digests = self._digests()
        digests.pop("docs/runbooks/person_e_detector_runbook.md")
        receipt = build_second_operator_receipt(
            handoff=build(),
            runbook_digests=digests,
            reproduction_receipt_hash=None,
            checkpoint_evidence_hash=None,
        )
        self.assertFalse(receipt["operable_without_person_e"])
        self.assertEqual(
            receipt["missing_runbooks"],
            ["docs/runbooks/person_e_detector_runbook.md"],
        )

    def test_forged_operability_claim_rejects(self) -> None:
        digests = self._digests()
        digests.pop("docs/runbooks/person_e_registry_runbook.md")
        receipt = build_second_operator_receipt(
            handoff=build(),
            runbook_digests=digests,
            reproduction_receipt_hash=None,
            checkpoint_evidence_hash=None,
        )
        receipt["operable_without_person_e"] = True
        with self.assertRaises(OperatingHandoffError):
            validate_second_operator_receipt(receipt)


if __name__ == "__main__":
    unittest.main()
