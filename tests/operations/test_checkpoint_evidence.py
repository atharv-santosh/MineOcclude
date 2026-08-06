"""Step 7.2 contract tests: no invented value may reach the checkpoint."""

from __future__ import annotations

import unittest

from mineocclude.operations.checkpoint_evidence import (
    CHECKPOINT_EVIDENCE_SCHEMA_VERSION,
    EVIDENCE_SLOTS,
    CheckpointEvidenceError,
    build_checkpoint_evidence,
    build_visual_qa_report,
    is_placeholder_value,
    validate_checkpoint_evidence,
    validate_displayed_value,
    validate_slot,
    verify_figure_to_source,
)

DIGEST = "a" * 64
OTHER_DIGEST = "b" * 64


def displayed_value(**overrides) -> dict:
    row = {
        "label": "held-out detector precision",
        "value": 1.0,
        "units": "fraction",
        "sample_count": 48,
        "source_artifact_id": "person-e-detector-v1-formal-evaluation",
        "source_run_id": "person-e-phase3-step3-1-v0_3-formal-ordinal-1",
        "source_status": "accepted",
        "figure_input_sha256": DIGEST,
        "gate_kind": "planning",
    }
    row.update(overrides)
    return row


def slots(populated_slot: str = "u4_persistence") -> list[dict]:
    rows = []
    for name in EVIDENCE_SLOTS:
        if name == populated_slot:
            rows.append(
                {
                    "slot": name,
                    "state": "populated",
                    "displayed_values": [displayed_value()],
                }
            )
        else:
            rows.append(
                {
                    "slot": name,
                    "state": "empty_awaiting_external_input",
                    "displayed_values": [],
                    "empty_reason": "no accepted upstream result exists yet",
                    "blocking_owner": "person_b",
                }
            )
    return rows


FIGURE_INDEX = {
    "person-e-detector-v1-formal-evaluation": {
        "figure_input_sha256": DIGEST,
        "status": "accepted",
    }
}


def build(**overrides):
    defaults = {
        "slots": slots(),
        "figure_index": FIGURE_INDEX,
        "artifact_index": [{"artifact_id": "x", "status": "accepted"}],
        "accepted_count": 1,
        "excluded_count": 0,
        "missing_count": 6,
        "control_failures": [],
        "limitations": ["U4 rollout clips not yet generated"],
        "provenance_demonstration_commands": [
            ["scripts/trace_artifact.py", "person-e-detector-v1-formal-evaluation"]
        ],
        "code_commit": "0" * 40,
    }
    defaults.update(overrides)
    return build_checkpoint_evidence(**defaults)


class TestPlaceholderDetection(unittest.TestCase):
    def test_known_placeholders_detected(self) -> None:
        for value in (None, "", "TBD", "n/a", "placeholder", "XXX", float("nan")):
            self.assertTrue(is_placeholder_value(value), repr(value))

    def test_real_measurements_are_not_placeholders(self) -> None:
        for value in (0.0, 1.0, -0.25, 48, True, "layout_03"):
            self.assertFalse(is_placeholder_value(value), repr(value))


class TestDisplayedValue(unittest.TestCase):
    def test_complete_value_validates(self) -> None:
        self.assertEqual(validate_displayed_value(displayed_value())["value"], 1.0)

    def test_placeholder_value_rejects(self) -> None:
        with self.assertRaises(CheckpointEvidenceError):
            validate_displayed_value(displayed_value(value="TBD"))

    def test_missing_units_reject(self) -> None:
        with self.assertRaises(CheckpointEvidenceError):
            validate_displayed_value(displayed_value(units=""))

    def test_missing_figure_digest_rejects(self) -> None:
        with self.assertRaises(CheckpointEvidenceError):
            validate_displayed_value(displayed_value(figure_input_sha256="nope"))

    def test_unknown_gate_kind_rejects(self) -> None:
        with self.assertRaises(CheckpointEvidenceError):
            validate_displayed_value(displayed_value(gate_kind="vibes"))

    def test_superseded_source_rejects(self) -> None:
        with self.assertRaises(CheckpointEvidenceError):
            validate_displayed_value(displayed_value(source_status="superseded"))

    def test_negative_sample_count_rejects(self) -> None:
        with self.assertRaises(CheckpointEvidenceError):
            validate_displayed_value(displayed_value(sample_count=-1))


class TestSlots(unittest.TestCase):
    def test_empty_slot_requires_reason_and_owner(self) -> None:
        with self.assertRaises(CheckpointEvidenceError):
            validate_slot(
                {
                    "slot": "u4_ssim",
                    "state": "empty_awaiting_external_input",
                    "displayed_values": [],
                }
            )

    def test_empty_slot_may_not_display_values(self) -> None:
        with self.assertRaises(CheckpointEvidenceError):
            validate_slot(
                {
                    "slot": "u4_ssim",
                    "state": "empty_awaiting_external_input",
                    "displayed_values": [displayed_value()],
                    "empty_reason": "x",
                    "blocking_owner": "person_a",
                }
            )

    def test_populated_slot_must_display_something(self) -> None:
        with self.assertRaises(CheckpointEvidenceError):
            validate_slot(
                {"slot": "u4_ssim", "state": "populated", "displayed_values": []}
            )

    def test_unknown_slot_rejects(self) -> None:
        with self.assertRaises(CheckpointEvidenceError):
            validate_slot(
                {"slot": "u9_vibes", "state": "populated", "displayed_values": []}
            )


class TestFigureToSourceVerification(unittest.TestCase):
    def test_resolved_value_verifies(self) -> None:
        result = verify_figure_to_source(slots(), FIGURE_INDEX)
        self.assertTrue(result["verified"])
        self.assertEqual(result["resolved_value_count"], 1)

    def test_unknown_source_is_reported(self) -> None:
        result = verify_figure_to_source(slots(), {})
        self.assertFalse(result["verified"])
        self.assertEqual(
            result["unresolved_source_ids"],
            ["person-e-detector-v1-formal-evaluation"],
        )

    def test_digest_drift_is_reported(self) -> None:
        index = {
            "person-e-detector-v1-formal-evaluation": {
                "figure_input_sha256": OTHER_DIGEST,
                "status": "accepted",
            }
        }
        result = verify_figure_to_source(slots(), index)
        self.assertFalse(result["verified"])
        self.assertEqual(
            result["digest_mismatched_source_ids"],
            ["person-e-detector-v1-formal-evaluation"],
        )

    def test_superseded_source_is_reported(self) -> None:
        index = {
            "person-e-detector-v1-formal-evaluation": {
                "figure_input_sha256": DIGEST,
                "status": "superseded",
            }
        }
        result = verify_figure_to_source(slots(), index)
        self.assertFalse(result["verified"])
        self.assertEqual(
            result["excluded_source_ids"],
            ["person-e-detector-v1-formal-evaluation"],
        )


class TestVisualQa(unittest.TestCase):
    def test_report_counts_populated_and_empty_slots(self) -> None:
        report = build_visual_qa_report(
            slots(), verify_figure_to_source(slots(), FIGURE_INDEX)
        )
        self.assertEqual(report["populated_slot_count"], 1)
        self.assertEqual(report["empty_slot_count"], len(EVIDENCE_SLOTS) - 1)
        self.assertTrue(report["all_displayed_values_carry_units"])
        self.assertEqual(report["invalid_or_superseded_displayed_count"], 0)


class TestCheckpointPackage(unittest.TestCase):
    def test_package_builds_and_revalidates(self) -> None:
        package = build()
        self.assertEqual(
            package["checkpoint_evidence_schema_version"],
            CHECKPOINT_EVIDENCE_SCHEMA_VERSION,
        )
        self.assertEqual(package["populated_slots"], ["u4_persistence"])
        validate_checkpoint_evidence(package)

    def test_missing_slot_rejects(self) -> None:
        with self.assertRaises(CheckpointEvidenceError):
            build(slots=slots()[:-1])

    def test_no_provenance_command_rejects(self) -> None:
        with self.assertRaises(CheckpointEvidenceError):
            build(provenance_demonstration_commands=[])

    def test_placeholder_result_never_reaches_the_package(self) -> None:
        rows = slots()
        rows[EVIDENCE_SLOTS.index("u4_persistence")]["displayed_values"] = [
            displayed_value(value="TBD")
        ]
        with self.assertRaises(CheckpointEvidenceError):
            build(slots=rows)

    def test_superseded_source_blocks_validation(self) -> None:
        package = build(
            figure_index={
                "person-e-detector-v1-formal-evaluation": {
                    "figure_input_sha256": DIGEST,
                    "status": "superseded",
                }
            }
        )
        with self.assertRaises(CheckpointEvidenceError):
            validate_checkpoint_evidence(package)

    def test_tampered_package_fails_content_hash(self) -> None:
        package = build()
        package["accepted_count"] = 99
        with self.assertRaises(CheckpointEvidenceError):
            validate_checkpoint_evidence(package)

    def test_manual_generation_claim_rejects(self) -> None:
        package = build()
        package["machine_generated_values_only"] = False
        with self.assertRaises(CheckpointEvidenceError):
            validate_checkpoint_evidence(package)

    def test_scientific_and_planning_gates_are_counted_separately(self) -> None:
        rows = slots()
        rows[EVIDENCE_SLOTS.index("u4_persistence")]["displayed_values"] = [
            displayed_value(),
            displayed_value(label="U4 signed displacement", gate_kind="scientific"),
        ]
        package = build(slots=rows)
        self.assertEqual(package["scientific_value_count"], 1)


if __name__ == "__main__":
    unittest.main()
