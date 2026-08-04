"""Focused validation tests for the Attempt 02 homography refit package."""

from __future__ import annotations

import copy
import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "finalize_person_e_homography_refit_attempt_02.py"
SPEC = importlib.util.spec_from_file_location("attempt_02_refit_finalize", SCRIPT)
if SPEC is None or SPEC.loader is None:  # pragma: no cover
    raise RuntimeError("Could not load the Attempt 02 refit finalizer.")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class TestAttempt02RefitFinalize(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.inputs = MODULE.load_validated_inputs()
        cls.summary = MODULE.fit_all(cls.inputs, MODULE.REQUIRED_ANCESTRY)

    def test_completed_annotation_is_exact_and_complete(self) -> None:
        self.assertEqual(
            MODULE.sha256_file(MODULE.ANNOTATION_PATH), MODULE.ANNOTATION_SHA256
        )
        self.assertEqual(len(self.inputs["annotation_layouts"]), 6)
        for layout in self.inputs["annotation_layouts"].values():
            self.assertEqual(len(layout["fit_correspondences"]), 4)
            self.assertEqual(len(layout["independent_validation_points"]), 1)
            self.assertNotIn(
                "far_west",
                {point["point_id"] for point in layout["fit_correspondences"]},
            )

    def test_six_fits_fail_closed_on_repository_tolerances(self) -> None:
        self.assertEqual(self.summary["successor_homography_count"], 6)
        self.assertEqual(self.summary["passing_layout_count"], 4)
        self.assertEqual(self.summary["failed_layout_ids"], ["layout_04", "layout_06"])
        self.assertFalse(self.summary["all_tolerances_pass"])
        for layout in self.summary["layouts"]:
            self.assertEqual(layout["rank"], 3)
            self.assertTrue(layout["matrix_gate_passed"])
            self.assertEqual(len(layout["matrix"]), 3)
            self.assertEqual(len(layout["fit_residuals"]), 4)
            self.assertEqual(len(layout["independent_validation_residuals"]), 1)

    def test_package_documents_do_not_authorize_failed_candidates(self) -> None:
        documents = MODULE.build_package_documents(self.summary, self.inputs)
        registry = documents["registry_records.json"]
        supersession = documents["historical_supersession.json"]

        self.assertEqual(len(registry["records"]), 6)
        self.assertTrue(
            all(
                record["lifecycle_status"] == "candidate_not_accepted"
                for record in registry["records"]
            )
        )
        self.assertEqual(
            supersession["successor_acceptance_status"],
            "NOT_ACCEPTED_VALIDATION_FAILED",
        )

    def test_package_manifest_and_handoff_fail_closed(self) -> None:
        fake_record = {"path": "artifact.json", "size_bytes": 1, "sha256": "a" * 64}
        manifest = MODULE.package_manifest_document(
            self.summary, "b" * 64, fake_record
        )
        handoff = MODULE.handoff_document(
            self.summary,
            "b" * 64,
            fake_record,
            {
                layout_id: fake_record
                for layout_id in MODULE.annotation_tool.EXPECTED_LAYOUT_IDS
            },
        )

        self.assertFalse(manifest["c6a_execution_authorized"])
        self.assertEqual(
            handoff["status"], "REFIT_VALIDATION_FAILED_C6A_NOT_AUTHORIZED"
        )
        self.assertFalse(handoff["c6a_execution_authorized"])
        self.assertIsNone(handoff["c6a_execution_command"])
        self.assertEqual(handoff["blocking_layout_ids"], ["layout_04", "layout_06"])

    def test_out_of_frame_annotation_fails_closed(self) -> None:
        document = copy.deepcopy(self.inputs["annotation"])
        document["layouts"][0]["fit_correspondences"][0][
            "image_xy_pixels"
        ] = [1920, 0]

        with self.assertRaisesRegex(MODULE.RefitFinalizeError, "outside"):
            MODULE.validate_annotation(
                document,
                self.inputs["verified_sources"],
                self.inputs["tasks"],
            )

    def test_hidden_marker_annotation_fails_closed(self) -> None:
        document = copy.deepcopy(self.inputs["annotation"])
        document["layouts"][0]["fit_correspondences"][0]["point_id"] = "far_west"

        with self.assertRaisesRegex(
            MODULE.RefitFinalizeError, "hidden, or historical"
        ):
            MODULE.validate_annotation(
                document,
                self.inputs["verified_sources"],
                self.inputs["tasks"],
            )

    def test_emitted_package_inventory_and_handoff_are_immutable(self) -> None:
        inventory_path = MODULE.PACKAGE_DIR / "sha256_inventory.json"
        manifest_path = MODULE.PACKAGE_DIR / "package_manifest.json"
        handoff_path = MODULE.PACKAGE_DIR / "person_e_to_person_c_refit_handoff.json"
        inventory = MODULE.load_json(inventory_path)
        manifest = MODULE.load_json(manifest_path)
        handoff = MODULE.load_json(handoff_path)

        for record in inventory["files"]:
            path = MODULE.PACKAGE_DIR / record["path"]
            self.assertEqual(path.stat().st_size, record["size_bytes"])
            self.assertEqual(MODULE.sha256_file(path), record["sha256"])
        self.assertEqual(
            MODULE.hash_json_value(inventory["files"]),
            inventory["package_bundle_sha256"],
        )
        self.assertEqual(
            manifest["package_bundle_sha256"], inventory["package_bundle_sha256"]
        )
        self.assertEqual(
            handoff["person_e_refit_package"]["sha256"],
            MODULE.sha256_file(manifest_path),
        )
        self.assertFalse(manifest["c6a_execution_authorized"])
        self.assertFalse(handoff["c6a_execution_authorized"])
        self.assertEqual(handoff["blocking_layout_ids"], ["layout_04", "layout_06"])


if __name__ == "__main__":
    unittest.main()
