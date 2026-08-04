"""Focused corrected-annotation and v0.2 refit/package tests."""

from __future__ import annotations

import copy
import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "finalize_person_e_homography_refit_attempt_02_v0_2.py"
SPEC = importlib.util.spec_from_file_location("attempt_02_refit_v0_2", SCRIPT)
if SPEC is None or SPEC.loader is None:  # pragma: no cover
    raise RuntimeError("Could not load the Attempt 02 v0.2 finalizer.")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class TestAttempt02RefitFinalizeV02(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.inputs = MODULE.load_validated_inputs()
        cls.summary = MODULE.build_summary(cls.inputs, "a" * 40)
        cls.by_id = {
            layout["layout_id"]: layout for layout in cls.summary["layouts"]
        }

    def test_corrected_annotation_hash_schema_and_bindings_are_valid(self) -> None:
        self.assertEqual(
            MODULE.sha256_file(MODULE.ANNOTATION_PATH), MODULE.ANNOTATION_SHA256
        )
        annotation = self.inputs["annotation"]
        self.assertEqual(
            annotation["annotation_schema_version"],
            MODULE.ANNOTATION_SCHEMA_VERSION,
        )
        self.assertEqual(
            annotation["image_coordinate_convention"], "pixel_center_xy_zero_based"
        )
        for layout_id in MODULE.REFITTED_LAYOUT_IDS:
            layout = self.inputs["annotation_layouts"][layout_id]
            self.assertEqual(len(layout["fit_correspondences"]), 4)
            self.assertEqual(len(layout["independent_validation_points"]), 1)
            self.assertTrue(
                MODULE.v1._no_three_collinear(
                    [point["world_xz_blocks"] for point in layout["fit_correspondences"]]
                )
            )
            fit_ids = {
                point["point_id"] for point in layout["fit_correspondences"]
            }
            heldout_ids = {
                point["point_id"]
                for point in layout["independent_validation_points"]
            }
            self.assertFalse(fit_ids & heldout_ids)

    def test_four_prior_passes_are_verified_and_reused(self) -> None:
        for layout_id in MODULE.REUSED_LAYOUT_IDS:
            reused = self.inputs["prior"]["reused_layouts"][layout_id]
            self.assertEqual(self.by_id[layout_id], reused)
            record = self.inputs["prior"]["reused_layout_records"][layout_id]
            source = MODULE.V1_PACKAGE_DIR / f"{layout_id}_homography.json"
            self.assertEqual(MODULE.sha256_file(source), record["sha256"])

    def test_all_six_layouts_record_full_precision_validation_and_pass(self) -> None:
        self.assertEqual(self.summary["successor_homography_count"], 6)
        self.assertTrue(self.summary["all_tolerances_pass"])
        self.assertEqual(self.summary["failed_layout_ids"], [])
        for layout_id in MODULE.EXPECTED_LAYOUT_IDS:
            layout = self.by_id[layout_id]
            self.assertTrue(layout["tolerance_result"])
            self.assertEqual(layout["rank"], 3)
            self.assertEqual(len(layout["matrix"]), 3)
            self.assertEqual(len(layout["fit_residuals"]), 4)
            self.assertEqual(len(layout["independent_validation_residuals"]), 1)
            self.assertEqual(len(layout["roundtrip_residuals"]), 5)
            self.assertIsInstance(layout["determinant"], float)
            self.assertIsInstance(layout["condition_number"], float)
            self.assertLessEqual(
                layout["heldout_localization"][
                    "median_absolute_wall_parallel_error_blocks"
                ],
                0.2,
            )

    def test_corrected_layout_errors_pass_unchanged_tolerance(self) -> None:
        self.assertEqual(
            self.by_id["layout_04"]["heldout_localization"][
                "median_absolute_wall_parallel_error_blocks"
            ],
            0.015253450941350444,
        )
        self.assertEqual(
            self.by_id["layout_06"]["heldout_localization"][
                "median_absolute_wall_parallel_error_blocks"
            ],
            0.03674363845058526,
        )
        self.assertEqual(
            self.inputs["config"]["homography"][
                "maximum_median_wall_parallel_error_blocks"
            ],
            0.2,
        )

    def test_package_and_handoff_documents_authorize_but_do_not_execute_c6a(
        self,
    ) -> None:
        documents = MODULE.build_package_documents(self.summary, self.inputs)
        self.assertEqual(
            documents["fit_summary.json"]["schema_version"],
            "person-e-v0.4-homography-refit-summary-v0.2",
        )
        manifest = MODULE.package_manifest_document(
            self.summary,
            "b" * 64,
            {"path": "inventory.json", "size_bytes": 1, "sha256": "c" * 64},
        )
        layout_records = {
            layout_id: {
                "path": f"{layout_id}.json",
                "size_bytes": 1,
                "sha256": "d" * 64,
            }
            for layout_id in MODULE.EXPECTED_LAYOUT_IDS
        }
        handoff = MODULE.handoff_document(
            self.summary,
            "b" * 64,
            {"path": "manifest.json", "size_bytes": 1, "sha256": "e" * 64},
            layout_records,
        )
        self.assertTrue(manifest["c6a_execution_authorized"])
        self.assertFalse(manifest["c6a_executed"])
        self.assertEqual(handoff["status"], "READY_FOR_C6A")
        self.assertTrue(handoff["c6a_execution_authorized"])
        self.assertIsNone(handoff["c6a_execution_command"])
        self.assertFalse(handoff["c6a_executed"])

    def test_package_emission_fails_closed_when_any_tolerance_fails(self) -> None:
        failed = copy.deepcopy(self.summary)
        failed["all_tolerances_pass"] = False
        with self.assertRaisesRegex(MODULE.RefitV02Error, "failed tolerances"):
            MODULE.emit_package(failed, self.inputs)

    def test_v0_1_failed_closed_artifacts_remain_unchanged(self) -> None:
        MODULE.repair.verify_preserved_artifacts()
        self.assertEqual(
            MODULE.sha256_file(MODULE.V1_PACKAGE_MANIFEST),
            MODULE.V1_PACKAGE_MANIFEST_SHA256,
        )
        self.assertEqual(
            MODULE.sha256_file(MODULE.V1_HANDOFF), MODULE.V1_HANDOFF_SHA256
        )


if __name__ == "__main__":
    unittest.main()
