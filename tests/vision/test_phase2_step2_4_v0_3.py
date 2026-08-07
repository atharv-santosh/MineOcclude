from __future__ import annotations

import copy
import json
import subprocess
import unittest
from pathlib import Path

from mineocclude.experiments.registry import formatted_json_bytes
from mineocclude.vision.homography import homography_from_record
from scripts.build_person_e_phase2_step2_4_v0_3 import (
    DOCUMENT_NAMES,
    EXPECTED_LAYOUT_IDS,
    IMMUTABLE_HISTORICAL_PATHS,
    MAXIMUM_MEDIAN_WALL_ERROR_BLOCKS,
    MAXIMUM_P95_WALL_ERROR_BLOCKS,
    PERSON_C_REVISION,
    PERSON_E_STARTING_REVISION,
    WORLD_COORDINATE_SYSTEM,
    WORLD_POINT_CONVENTION,
    validate_v0_3_documents,
)

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs" / "status" / "person_e_phase2_step2_4_v0_3"


def load(name: str) -> dict[str, object]:
    return json.loads((EVIDENCE / name).read_text(encoding="utf-8"))


def load_all() -> dict[str, dict[str, object]]:
    return {name: load(name) for name in sorted(DOCUMENT_NAMES)}


class TestPhase2Step24V03(unittest.TestCase):
    def test_document_set_is_canonical_and_valid(self) -> None:
        self.assertEqual(
            {path.name for path in EVIDENCE.glob("*.json")},
            DOCUMENT_NAMES,
        )
        documents = load_all()
        validate_v0_3_documents(documents)
        for name, document in documents.items():
            with self.subTest(name=name):
                payload = (EVIDENCE / name).read_bytes()
                self.assertFalse(payload.startswith(b"\xef\xbb\xbf"))
                self.assertNotIn(b"\r\n", payload)
                self.assertEqual(payload, formatted_json_bytes(document))

    def test_exact_source_revision_and_top_face_conventions(self) -> None:
        source = load("source_validation.json")
        self.assertEqual(source["source_revision"], PERSON_C_REVISION)
        self.assertEqual(source["validated_png_count"], 72)
        marker_documents = source["marker_document_records"]
        self.assertEqual(
            [row["layout_id"] for row in marker_documents],
            list(EXPECTED_LAYOUT_IDS),
        )
        for row in marker_documents:
            with self.subTest(layout_id=row["layout_id"]):
                self.assertEqual(row["marker_count"], 4)
                self.assertEqual(
                    row["world_coordinate_system"],
                    WORLD_COORDINATE_SYSTEM,
                )
                self.assertEqual(
                    row["world_point_convention"],
                    WORLD_POINT_CONVENTION,
                )
                self.assertTrue(
                    row["marker_convention_correction"]["eval_probe_untouched"]
                )

    def test_layout_02_passes_and_layout_03_fails_closed(self) -> None:
        detector = load("detector_outputs.json")
        layouts = {row["layout_id"]: row for row in detector["marker_layouts"]}
        self.assertTrue(layouts["layout_02"]["all_negative_frames_detected"])
        for frame in layouts["layout_02"]["negative_frame_results"]:
            self.assertEqual(frame["status"], "detected")
            self.assertEqual(frame["marker_count"], 4)
            self.assertEqual(len(frame["markers"]), 4)
            self.assertEqual(frame["failures"], [])

        self.assertFalse(layouts["layout_03"]["all_negative_frames_detected"])
        self.assertEqual(detector["blocked_layout_ids"], ["layout_03"])
        for frame in layouts["layout_03"]["negative_frame_results"]:
            self.assertEqual(frame["status"], "rejected")
            self.assertEqual(
                {failure["marker_role"] for failure in frame["failures"]},
                {"north_west", "north_east"},
            )
            self.assertTrue(
                all(
                    "touches the frame border" in failure["reason"]
                    for failure in frame["failures"]
                )
            )

    def test_probe_coverage_thresholds_and_split_are_fail_closed(
        self,
    ) -> None:
        localization = load("localization_validation_report.json")
        self.assertEqual(localization["required_probe_count"], 36)
        self.assertEqual(localization["evaluated_probe_count"], 30)
        self.assertEqual(localization["calibration_probe_count"], 15)
        self.assertEqual(localization["heldout_probe_count"], 15)
        self.assertFalse(localization["coverage_passed"])
        self.assertFalse(localization["all_required_probes_evaluated"])
        self.assertEqual(localization["blocked_layout_ids"], ["layout_03"])
        self.assertEqual(
            localization["required_gate"],
            {
                "maximum_median_absolute_wall_parallel_error_blocks": (
                    MAXIMUM_MEDIAN_WALL_ERROR_BLOCKS
                ),
                (
                    "maximum_p95_absolute_wall_parallel_error_blocks_exclusive"
                ): MAXIMUM_P95_WALL_ERROR_BLOCKS,
            },
        )
        self.assertTrue(localization["evaluated_subset_error_gate_passed"])
        self.assertLessEqual(
            localization["median_absolute_wall_parallel_error_blocks"],
            MAXIMUM_MEDIAN_WALL_ERROR_BLOCKS,
        )
        self.assertLess(
            localization["p95_absolute_wall_parallel_error_blocks"],
            MAXIMUM_P95_WALL_ERROR_BLOCKS,
        )
        self.assertFalse(localization["formal_planning_gate_passed"])
        self.assertFalse(localization["planning_gate_passed"])
        self.assertEqual(
            {row["split"] for row in localization["records"]},
            {"calibration", "heldout"},
        )

    def test_no_output_adjustment_or_probe_derived_selection(self) -> None:
        localization = load("localization_validation_report.json")
        receipt = load("step2_4_v0_3_receipt.json")
        self.assertFalse(localization["output_bias_adjustment_applied"])
        self.assertIsNone(localization["output_offset_blocks"])
        self.assertEqual(localization["excluded_layout_ids"], [])
        for field in (
            "probe_targets_used_for_fitting",
            "probe_targets_used_for_detector_selection",
            "probe_targets_used_for_ground_contact_selection",
            "probe_targets_used_for_exclusion_selection",
        ):
            self.assertFalse(localization[field])
        method = receipt["method_integrity"]
        self.assertFalse(method["output_bias_adjustment_applied"])
        self.assertIsNone(method["output_offset_blocks"])
        self.assertFalse(method["probe_derived_tuning_applied"])
        self.assertFalse(method["probe_filtering_applied"])
        self.assertFalse(method["exclusions_applied"])
        self.assertFalse(method["source_split_changed_after_evaluation"])

    def test_homographies_exist_only_for_detectable_layouts(self) -> None:
        homographies = load("homography_record.json")
        self.assertEqual(homographies["layout_count"], 5)
        self.assertEqual(
            [record["layout_id"] for record in homographies["records"]],
            ["layout_01", "layout_02", "layout_04", "layout_05", "layout_06"],
        )
        for record in homographies["records"]:
            with self.subTest(layout_id=record["layout_id"]):
                homography_from_record(record)

    def test_status_is_derived_from_complete_formal_gate(self) -> None:
        localization = load("localization_validation_report.json")
        status = load("phase2_status.json")
        steps = {step["step"]: step for step in status["steps"]}
        self.assertTrue(
            all(steps[step]["status"] == "PASS" for step in ("2.1", "2.2", "2.3"))
        )
        self.assertFalse(localization["formal_planning_gate_passed"])
        self.assertEqual(steps["2.4"]["status"], "PARTIAL")
        self.assertEqual(
            steps["2.4"]["remaining_blocker"],
            "layout_03_clipped_markers_block_complete_probe_coverage",
        )
        self.assertEqual(status["overall_status"], "PARTIAL")

    def test_v0_1_and_v0_2_scientific_evidence_is_immutable(self) -> None:
        for relative_path in IMMUTABLE_HISTORICAL_PATHS:
            with self.subTest(path=relative_path):
                committed = subprocess.run(
                    [
                        "git",
                        "-C",
                        str(ROOT),
                        "cat-file",
                        "blob",
                        f"{PERSON_E_STARTING_REVISION}:{relative_path}",
                    ],
                    check=True,
                    capture_output=True,
                ).stdout
                self.assertEqual(
                    (ROOT / relative_path).read_bytes(),
                    committed,
                )

    def test_deterministic_regeneration_attestation_matches_bytes(
        self,
    ) -> None:
        determinism = load("deterministic_generation.json")
        self.assertTrue(determinism["byte_identical"])
        self.assertEqual(determinism["compared_document_count"], 8)
        self.assertEqual(
            determinism["first_generation_sha256"],
            determinism["second_generation_sha256"],
        )
        for name, digest in determinism["first_generation_sha256"].items():
            with self.subTest(name=name):
                import hashlib

                self.assertEqual(
                    hashlib.sha256((EVIDENCE / name).read_bytes()).hexdigest(),
                    digest,
                )

    def test_tampered_source_gate_or_bias_claim_is_rejected(self) -> None:
        documents = load_all()

        source_tampered = copy.deepcopy(documents)
        source_tampered["source_validation.json"]["source_revision"] = "0" * 40
        with self.assertRaisesRegex(ValueError, "source binding"):
            validate_v0_3_documents(source_tampered)

        threshold_tampered = copy.deepcopy(documents)
        threshold_tampered["localization_validation_report.json"]["required_gate"][
            "maximum_median_absolute_wall_parallel_error_blocks"
        ] = 0.3
        with self.assertRaisesRegex(ValueError, "thresholds"):
            validate_v0_3_documents(threshold_tampered)

        bias_tampered = copy.deepcopy(documents)
        bias_tampered["localization_validation_report.json"][
            "output_bias_adjustment_applied"
        ] = True
        with self.assertRaisesRegex(ValueError, "output adjustment"):
            validate_v0_3_documents(bias_tampered)

        status_tampered = copy.deepcopy(documents)
        status_tampered["phase2_status.json"]["overall_status"] = "PASS"
        with self.assertRaisesRegex(ValueError, "status"):
            validate_v0_3_documents(status_tampered)


if __name__ == "__main__":
    unittest.main()
