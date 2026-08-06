"""Validate the immutable Person E terminal status package."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import build_person_e_terminal_status_v0_1 as builder  # noqa: E402

PKG = ROOT / builder.PKG_REL

MANUAL_STEPS = (
    "0.1", "0.2", "0.3", "0.4",
    "1.1", "1.2", "1.3",
    "2.1", "2.2", "2.3", "2.4",
    "3.1", "3.2", "3.3",
    "4.1", "4.2", "4.3",
    "5.1", "5.2", "5.3",
    "6.1", "6.2", "6.3", "6.4", "6.5",
    "7.1", "7.2", "7.3",
)

ALLOWED_STATUSES = {
    "COMPLETE_AND_VERIFIED",
    "IMPLEMENTED_NOT_EXECUTED",
    "PARTIALLY_COMPLETE",
    "NOT_STARTED",
    "BLOCKED_EXTERNAL_INPUT",
    "STALE_STATUS",
}


def load(name: str) -> dict:
    return json.loads((PKG / name).read_text(encoding="utf-8"))


class TestPackageIntegrity(unittest.TestCase):
    def test_package_validates_against_its_own_inventory(self) -> None:
        builder.validate_package(PKG)

    def test_declared_output_set_is_exact(self) -> None:
        self.assertEqual(
            {path.name for path in PKG.iterdir()}, set(builder.OUTPUT_FILES)
        )


class TestStepCoverage(unittest.TestCase):
    def setUp(self) -> None:
        self.status = load("step_status.json")

    def test_every_manual_step_through_7_3_is_present_exactly_once(self) -> None:
        steps = [row["step"] for row in self.status["steps"]]
        self.assertEqual(tuple(steps), MANUAL_STEPS)
        self.assertEqual(len(set(steps)), len(steps))

    def test_every_status_is_from_the_allowed_vocabulary(self) -> None:
        for row in self.status["steps"]:
            self.assertIn(row["status"], ALLOWED_STATUSES, row["step"])

    def test_no_step_is_unstarted(self) -> None:
        self.assertEqual(
            [row["step"] for row in self.status["steps"] if row["status"] == "NOT_STARTED"],
            [],
        )

    def test_every_incomplete_step_names_what_remains(self) -> None:
        for row in self.status["steps"]:
            if row["status"] == "COMPLETE_AND_VERIFIED":
                continue
            self.assertTrue(
                str(row.get("remaining") or "").strip(),
                f"step {row['step']} does not say what remains",
            )

    def test_every_step_declares_its_evidence_class(self) -> None:
        for row in self.status["steps"]:
            self.assertIn(row["evidence_class"], {"real", "synthetic"}, row["step"])
            self.assertTrue(row["evidence"], row["step"])

    def test_declared_evidence_paths_exist(self) -> None:
        for row in self.status["steps"]:
            for relative in row["evidence"]:
                self.assertTrue(
                    (ROOT / relative).exists(),
                    f"step {row['step']} evidence missing: {relative}",
                )

    def test_manual_identity_is_bound_by_digest(self) -> None:
        manual = self.status["manual"]
        self.assertEqual(manual["terminal_step"], "7.3")
        self.assertEqual(len(manual["source_document_sha256"]), 64)


class TestFrozenEvidence(unittest.TestCase):
    def test_every_frozen_hash_revalidates_now(self) -> None:
        result = builder.verify_frozen_hashes()
        self.assertTrue(result["all_valid"], result["invalid"])

    def test_recorded_frozen_verification_matches_a_fresh_check(self) -> None:
        recorded = load("terminal_status.json")["frozen_hash_verification"]
        self.assertTrue(recorded["all_valid"])
        self.assertEqual(recorded["invalid"], [])

    def test_successor_provenance_receipt_digest_is_unchanged(self) -> None:
        checks = {
            row["name"]: row
            for row in load("terminal_status.json")["frozen_hash_verification"]["checks"]
        }
        row = checks["person_e_successor_provenance_receipt_sha256"]
        self.assertEqual(
            row["value"],
            "946a856bf704b43c13ba08ba692bda49cc2ecea4c1cc15096a35c53b31c522b3",
        )
        self.assertEqual(row["observed"], row["value"])


class TestNoOverclaiming(unittest.TestCase):
    def setUp(self) -> None:
        self.terminal = load("terminal_status.json")

    def test_real_measurement_is_not_claimed(self) -> None:
        self.assertFalse(self.terminal["real_measurement_complete"])
        self.assertIsNone(self.terminal["measurement_row_count"])
        self.assertEqual(self.terminal["real_rollout_count"], 0)

    def test_real_clean_reproduction_is_not_claimed(self) -> None:
        self.assertFalse(self.terminal["real_clean_reproduction_complete"])

    def test_u4_output_was_not_inspected(self) -> None:
        self.assertFalse(self.terminal["u4_output_inspected"])

    def test_no_mvp_tag_is_claimed_from_this_branch(self) -> None:
        self.assertFalse(self.terminal["mvp_tag_created_from_this_branch"])
        self.assertEqual(
            self.terminal["integration_readiness"]["final_tag_owner"],
            "coordinated integration review, not Person E",
        )

    def test_synthetic_evidence_is_labelled_synthetic(self) -> None:
        for row in self.terminal["synthetic_evidence_inventory"]:
            self.assertTrue(row["labelled_synthetic"])

    def test_real_evidence_carries_measured_values_and_a_gate_label(self) -> None:
        for row in self.terminal["real_evidence_inventory"]:
            self.assertTrue(row["measured"])
            self.assertEqual(row["gate_kind"], "planning")


class TestBlockersAndCommands(unittest.TestCase):
    def setUp(self) -> None:
        self.blockers = load("external_blockers.json")

    def test_every_blocker_names_owner_step_and_next_command(self) -> None:
        self.assertGreater(self.blockers["blocker_count"], 0)
        for row in self.blockers["blockers"]:
            self.assertTrue(row["dependency_id"].strip())
            self.assertTrue(row["owner"].strip())
            self.assertTrue(row["blocks_step"].strip())
            self.assertTrue(row["next_command"])

    def test_blocked_measurement_steps_each_have_an_owner(self) -> None:
        blocked_steps = {row["blocks_step"] for row in self.blockers["blockers"]}
        for step in ("6.1", "6.2", "6.3", "6.4", "6.5", "7.1"):
            self.assertIn(step, blocked_steps)

    def test_external_artifact_index_is_carried(self) -> None:
        self.assertTrue(self.blockers["external_artifact_index"])


class TestVersionsAndInventory(unittest.TestCase):
    def test_version_table_names_every_frozen_component(self) -> None:
        versions = load("version_table.json")
        for key in (
            "registry_version",
            "detector_version",
            "homography_version",
            "rollout_intake_schema_version",
            "measurement_evidence_schema_version",
            "checkpoint_evidence_schema_version",
        ):
            self.assertTrue(str(versions[key]).strip(), key)

    def test_ssim_records_its_unresolved_person_b_parameters(self) -> None:
        ssim = load("version_table.json")["ssim"]
        # These are genuinely unset pending Person B sign-off. Recording them as
        # null is the point: a fabricated margin would look like an approval.
        self.assertIsNone(ssim["background_mask_margin_pixels"])
        self.assertEqual(ssim["mask_status"], "pending_person_b_person_e_signoff")

    def test_implementation_inventory_digests_still_match(self) -> None:
        from mineocclude.experiments.registry import hash_file_bytes

        inventory = load("implementation_inventory.json")
        for group in ("entry_points", "modules", "runbooks"):
            for relative, digest in inventory[group].items():
                self.assertEqual(hash_file_bytes(ROOT / relative), digest, relative)

    def test_test_inventory_records_zero_failures_and_labelled_skips(self) -> None:
        tests = load("test_inventory.json")
        self.assertEqual(tests["results"]["failed"], 0)
        self.assertTrue(tests["zero_failures"])
        self.assertEqual(
            sum(row["count"] for row in tests["skips_are_external_input_conditions"]),
            tests["results"]["skipped"],
        )
        for row in tests["skips_are_external_input_conditions"]:
            self.assertTrue(row["owner"].strip())
            self.assertTrue(row["reason"].strip())


class TestBuilderStillRuns(unittest.TestCase):
    def test_builder_regenerates_a_valid_package(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "terminal"
            out.mkdir()
            documents = builder.build_documents(
                passed=1, failed=0, skipped=0, subtests_passed=0, duration_seconds=0.0
            )
            for name, payload in documents.items():
                (out / name).write_bytes(payload)
            builder.validate_package(out)


if __name__ == "__main__":
    unittest.main()
