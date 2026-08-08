"""Validate the committed Person E Phase 7 terminal package (Steps 7.1-7.3)."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import build_person_e_phase7_terminal_v0_1 as builder  # noqa: E402

from mineocclude.operations.checkpoint_evidence import (  # noqa: E402
    EVIDENCE_SLOTS,
    validate_checkpoint_evidence,
)
from mineocclude.operations.clean_reproduction import (  # noqa: E402
    REPRODUCTION_STAGES,
    validate_clean_reproduction_plan,
    validate_clean_reproduction_receipt,
)
from mineocclude.operations.handoff import (  # noqa: E402
    REQUIRED_WORKFLOWS,
    validate_operating_handoff,
    validate_second_operator_receipt,
)

PKG = ROOT / builder.PKG_REL


def load(name: str) -> dict:
    return json.loads((PKG / name).read_text(encoding="utf-8"))


class TestPackageIntegrity(unittest.TestCase):
    def test_package_validates_against_its_own_inventory(self) -> None:
        builder.validate_package(PKG)

    def test_every_declared_output_is_present(self) -> None:
        present = {path.name for path in PKG.iterdir()}
        self.assertEqual(present, set(builder.OUTPUT_FILES))

    def test_recorded_commit_remains_in_branch_history(self) -> None:
        # The package is bound to the commit it was built from. Person E keeps
        # committing afterwards, so that commit must be reachable from HEAD
        # rather than equal to it.
        commit = load("phase7_status.json")["code_commit"]
        completed = subprocess.run(
            ["git", "-C", str(ROOT), "merge-base", "--is-ancestor", commit, "HEAD"],
            check=False,
            capture_output=True,
        )
        self.assertEqual(completed.returncode, 0, f"{commit} not reachable from HEAD")


class TestStep71CleanReproduction(unittest.TestCase):
    def setUp(self) -> None:
        self.plan = load("clean_reproduction_plan.json")
        self.receipt = load("clean_reproduction_receipt.json")

    def test_plan_and_receipt_validate(self) -> None:
        validate_clean_reproduction_plan(self.plan)
        validate_clean_reproduction_receipt(self.receipt)

    def test_plan_declares_every_stage_in_order(self) -> None:
        self.assertEqual(
            tuple(stage["stage"] for stage in self.plan["stages"]),
            REPRODUCTION_STAGES,
        )

    def test_plan_contains_no_private_path(self) -> None:
        from mineocclude.operations.clean_reproduction import private_path_tokens

        for stage in self.plan["stages"]:
            self.assertEqual(private_path_tokens(stage["command"]), [])
        for row in self.plan["inputs"]:
            self.assertEqual(private_path_tokens([row["repository_path"]]), [])

    def test_receipt_is_labelled_synthetic_and_claims_nothing_real(self) -> None:
        self.assertEqual(self.receipt["evidence_class"], "synthetic_fixture")
        self.assertFalse(self.receipt["real_clean_reproduction_complete"])

    def test_every_rehearsal_stage_executed_and_passed(self) -> None:
        outcomes = {row["stage"]: row["outcome"] for row in self.receipt["stage_results"]}
        self.assertEqual(set(outcomes), set(REPRODUCTION_STAGES))
        self.assertEqual(set(outcomes.values()), {"passed"})

    def test_no_source_edit_occurred_between_stages(self) -> None:
        self.assertFalse(self.receipt["source_edited_between_stages"])
        self.assertEqual(self.receipt["source_edited_components"], [])

    def test_known_answer_geometry_was_recovered(self) -> None:
        known = self.receipt["synthetic_known_answer"]
        self.assertTrue(known["known_answer_recovered"])
        self.assertEqual(known["observed_wall_parallel_blocks"], 1.5)

    def test_blocking_external_inputs_are_named(self) -> None:
        self.assertIn("person_a_u4_rollout_clips", self.receipt["blocking_external_inputs"])
        self.assertIn("person_a_clean_run_bundle", self.receipt["blocking_external_inputs"])

    def test_component_hashes_still_match_the_working_tree(self) -> None:
        from mineocclude.operations.clean_reproduction import verify_component_hashes

        result = verify_component_hashes(self.plan, ROOT)
        self.assertTrue(result["verified"], result["mismatched_components"])

    def test_declared_inputs_still_match_their_digests(self) -> None:
        from mineocclude.operations.clean_reproduction import verify_input_hashes

        result = verify_input_hashes(self.plan, ROOT)
        self.assertTrue(result["verified"], result)


class TestStep72CheckpointEvidence(unittest.TestCase):
    def setUp(self) -> None:
        self.checkpoint = load("checkpoint_evidence.json")

    def test_checkpoint_validates(self) -> None:
        validate_checkpoint_evidence(self.checkpoint)

    def test_every_slot_is_accounted_for(self) -> None:
        self.assertEqual(
            {slot["slot"] for slot in self.checkpoint["slots"]}, set(EVIDENCE_SLOTS)
        )

    def test_only_person_e_planning_gates_are_populated(self) -> None:
        self.assertEqual(
            self.checkpoint["populated_slots"],
            ["engineering_detector_gate", "engineering_localization_gate"],
        )
        self.assertEqual(self.checkpoint["scientific_value_count"], 0)

    def test_every_empty_slot_names_a_reason_and_blocking_owner(self) -> None:
        for slot in self.checkpoint["slots"]:
            if slot["state"] == "populated":
                continue
            self.assertTrue(slot["empty_reason"].strip())
            self.assertTrue(slot["blocking_owner"].strip())
            self.assertEqual(slot["displayed_values"], [])

    def test_detector_values_match_the_committed_formal_evaluation(self) -> None:
        report = json.loads(
            (ROOT / builder.DETECTOR_EVIDENCE_REL).read_text(encoding="utf-8")
        )
        values = {
            row["label"]: row["value"]
            for slot in self.checkpoint["slots"]
            if slot["slot"] == "engineering_detector_gate"
            for row in slot["displayed_values"]
        }
        self.assertEqual(
            values["held-out detector precision"],
            report["metrics"]["precision"]["decimal"],
        )
        self.assertEqual(
            values["held-out detector recall"], report["metrics"]["recall"]["decimal"]
        )
        self.assertEqual(
            values["held-out false positives"], report["metrics"]["false_positive"]
        )

    def test_localization_values_match_the_accepted_refit(self) -> None:
        summary = json.loads(
            (ROOT / builder.HOMOGRAPHY_EVIDENCE_REL).read_text(encoding="utf-8")
        )
        expected = max(
            float(layout["heldout_wall_parallel_error_blocks"])
            for layout in summary["layouts"]
        )
        values = {
            row["label"]: row["value"]
            for slot in self.checkpoint["slots"]
            if slot["slot"] == "engineering_localization_gate"
            for row in slot["displayed_values"]
        }
        self.assertEqual(
            values["worst-layout held-out wall-parallel localization error"], expected
        )
        self.assertEqual(
            values["passing layout count"], summary["passing_layout_count"]
        )

    def test_every_displayed_value_resolves_to_its_source(self) -> None:
        self.assertTrue(self.checkpoint["figure_source_verification"]["verified"])
        self.assertEqual(
            self.checkpoint["figure_source_verification"]["excluded_source_ids"], []
        )

    def test_limitations_state_that_no_u4_measurement_exists(self) -> None:
        joined = " ".join(self.checkpoint["limitations"]).lower()
        self.assertIn("no u4 rollout clip", joined)
        self.assertIn("planning gates", joined)

    def test_provenance_demonstration_commands_are_shipped(self) -> None:
        self.assertTrue(self.checkpoint["provenance_demonstration_commands"])


class TestStep73FrozenHandoff(unittest.TestCase):
    def setUp(self) -> None:
        self.handoff = load("operating_handoff.json")
        self.receipt = load("second_operator_receipt.json")

    def test_handoff_and_receipt_validate(self) -> None:
        validate_operating_handoff(self.handoff)
        validate_second_operator_receipt(self.receipt)

    def test_all_five_workflows_are_frozen(self) -> None:
        self.assertEqual(
            {row["workflow"] for row in self.handoff["workflows"]},
            set(REQUIRED_WORKFLOWS),
        )

    def test_every_runbook_exists_on_disk(self) -> None:
        for row in self.handoff["workflows"]:
            self.assertTrue(
                (ROOT / row["runbook_path"]).is_file(), row["runbook_path"]
            )

    def test_runbook_digests_still_match(self) -> None:
        from mineocclude.experiments.registry import hash_file_bytes

        for relative, digest in self.receipt["runbook_digests"].items():
            self.assertEqual(hash_file_bytes(ROOT / relative), digest, relative)

    def test_second_operator_can_run_every_workflow(self) -> None:
        self.assertTrue(self.receipt["operable_without_person_e"])
        self.assertEqual(self.receipt["missing_runbooks"], [])

    def test_frozen_version_table_covers_the_measurement_instrument(self) -> None:
        components = {row["component"] for row in self.handoff["frozen_version_table"]}
        for required in (
            "magenta_detector",
            "homography_package",
            "ssim",
            "immutable_registry",
            "measurement_evidence_schema",
        ):
            self.assertIn(required, components)

    def test_external_artifact_index_marks_unmounted_stores(self) -> None:
        states = {
            row["artifact_id"]: row["availability"]
            for row in self.handoff["external_artifact_index"]
        }
        self.assertEqual(
            states["person_a_activation_store_phase6"], "external_unmounted"
        )
        self.assertEqual(states["person_a_u4_rollout_clips"], "pending_generation")

    def test_every_external_dependency_names_owner_step_and_next_command(self) -> None:
        for row in self.handoff["remaining_external_dependencies"]:
            self.assertTrue(row["owner"].strip())
            self.assertTrue(row["blocks_step"].strip())
            self.assertTrue(row["next_command"])

    def test_paper_workspace_plan_is_bound_and_present(self) -> None:
        self.assertTrue(
            (ROOT / self.handoff["paper_workspace_plan_path"]).is_file()
        )


class TestNoFabricatedClaims(unittest.TestCase):
    def test_status_never_claims_real_measurement_or_u4_inspection(self) -> None:
        status = load("phase7_status.json")
        self.assertFalse(status["real_measurement_complete"])
        self.assertFalse(status["u4_output_inspected"])
        self.assertFalse(status["step_7_1"]["real_clean_reproduction_complete"])

    def test_validation_receipt_never_claims_real_reproduction(self) -> None:
        validation = load("validation_receipt.json")
        self.assertFalse(validation["real_measurement_claimed"])
        self.assertFalse(validation["real_clean_reproduction_claimed"])
        self.assertFalse(validation["u4_output_inspected"])


class TestBuilderStillRuns(unittest.TestCase):
    def test_builder_regenerates_a_structurally_valid_package(self) -> None:
        # Runtimes and captured output make the receipt legitimately
        # non-deterministic, so this proves the builder still works rather than
        # asserting byte equality with the committed package.
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "phase7"
            builder.write_documents(out)
            builder.validate_package(out)


if __name__ == "__main__":
    unittest.main()
