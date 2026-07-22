from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from mineocclude.contracts.rollout_registry import validate_rollout_registry_bundle
from mineocclude.vision.calibration import (
    CalibrationDatasetError,
    validate_detector_calibration_plan,
)
from mineocclude.vision.homography import (
    HomographyError,
    validate_homography_fixture,
)
from mineocclude.vision.magenta import (
    VisionInputError,
    validate_detection_document,
)
from mineocclude.vision.measurement import (
    MeasurementError,
    validate_phase1_rollout_measurement_fixture,
)


FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "person_e"


def load_fixture(name: str) -> dict[str, object]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class TestDetectorCalibrationPlan(unittest.TestCase):
    def test_disjoint_calibration_and_heldout_sets_pass(self) -> None:
        document = load_fixture("calibration_plan_v1.json")
        original = copy.deepcopy(document)
        validate_detector_calibration_plan(document)
        self.assertEqual(document, original)
        self.assertTrue(
            all(
                sample["threshold_selection_eligible"]
                is (sample["split"] == "calibration")
                for sample in document["samples"]
            )
        )

    def test_overlapping_event_fixture_fails(self) -> None:
        document = load_fixture("rejected_calibration_overlap_event_v1.json")
        with self.assertRaisesRegex(CalibrationDatasetError, "overlaps"):
            validate_detector_calibration_plan(document)

    def test_overlapping_frame_identity_and_heldout_selection_fail(self) -> None:
        frame_overlap = load_fixture("calibration_plan_v1.json")
        frame_overlap["samples"][3]["trajectory_id"] = frame_overlap["samples"][0][
            "trajectory_id"
        ]
        frame_overlap["samples"][3]["model_frame_idx"] = frame_overlap["samples"][
            0
        ]["model_frame_idx"]
        with self.assertRaisesRegex(CalibrationDatasetError, "frame identity"):
            validate_detector_calibration_plan(frame_overlap)
        heldout_selection = load_fixture("calibration_plan_v1.json")
        heldout_selection["samples"][3]["threshold_selection_eligible"] = True
        with self.assertRaisesRegex(CalibrationDatasetError, "eligibility"):
            validate_detector_calibration_plan(heldout_selection)


class TestDetectionContract(unittest.TestCase):
    def test_valid_detection_and_explicit_missing_frame_pass(self) -> None:
        document = load_fixture("detection_records_v1.json")
        original = copy.deepcopy(document)
        validate_detection_document(document)
        self.assertEqual(document, original)
        missing = next(
            row for row in document["records"] if row["status"] == "rejected"
        )
        self.assertEqual(missing["rejection_reason"], "missing_frame")
        self.assertIsNone(missing["centroid_xy"])

    def test_malformed_detection_identity_fixture_fails(self) -> None:
        with self.assertRaisesRegex(VisionInputError, "source context"):
            validate_detection_document(
                load_fixture("rejected_detection_identity_v1.json")
            )

    def test_ambiguous_detection_and_record_order_handling(self) -> None:
        document = load_fixture("detection_records_v1.json")
        document["source_contexts"].reverse()
        document["records"].reverse()
        validate_detection_document(document)
        duplicate = load_fixture("detection_records_v1.json")
        duplicate["records"][1]["source_frame_id"] = duplicate["records"][0][
            "source_frame_id"
        ]
        with self.assertRaises(VisionInputError):
            validate_detection_document(duplicate)


class TestHomographyFixture(unittest.TestCase):
    def test_known_transform_is_recovered(self) -> None:
        document = load_fixture("homography_fixture_v1.json")
        original = copy.deepcopy(document)
        homography = validate_homography_fixture(document)
        self.assertEqual(document, original)
        world_x, world_z = homography.transform([300.0, 180.0])
        self.assertAlmostEqual(world_x, 2.0)
        self.assertAlmostEqual(world_z, 2.0)

    def test_degenerate_and_inconsistent_correspondences_fail(self) -> None:
        with self.assertRaises(HomographyError):
            validate_homography_fixture(
                load_fixture("rejected_homography_degenerate_v1.json")
            )
        inconsistent = load_fixture("homography_fixture_v1.json")
        markers = inconsistent["marker_correspondences"]
        markers[0]["world_xz_blocks"], markers[1]["world_xz_blocks"] = (
            markers[1]["world_xz_blocks"],
            markers[0]["world_xz_blocks"],
        )
        with self.assertRaisesRegex(HomographyError, "inconsistent"):
            validate_homography_fixture(inconsistent)

    def test_layout_camera_and_resolution_reuse_mismatches_fail(self) -> None:
        document = load_fixture("homography_fixture_v1.json")
        context = {
            field: document[field]
            for field in (
                "layout_id",
                "canonical_camera_pose_id",
                "resolution_id",
                "image_width_px",
                "image_height_px",
                "image_coordinate_system",
            )
        }
        validate_homography_fixture(document, required_context=context)
        for field, value in (
            ("layout_id", "layout_other"),
            ("canonical_camera_pose_id", "pose_other"),
            ("resolution_id", "resolution_other"),
            ("image_width_px", 320),
        ):
            with self.subTest(field=field):
                mismatch = copy.deepcopy(context)
                mismatch[field] = value
                with self.assertRaisesRegex(HomographyError, "context mismatch"):
                    validate_homography_fixture(
                        document, required_context=mismatch
                    )


class TestRolloutMeasurementFixture(unittest.TestCase):
    def test_all_required_rollout_and_measurement_cases_are_machine_checkable(self) -> None:
        document = load_fixture("rollout_measurement_scenarios_v1.json")
        original = copy.deepcopy(document)
        a_validation = validate_rollout_registry_bundle(
            document["rollout_manifest"], document["registry"]
        )
        self.assertTrue(a_validation.accepted, a_validation.rejections)
        results = validate_phase1_rollout_measurement_fixture(document)
        self.assertEqual(document, original)
        self.assertEqual(results["case_alpha_zero"], "accepted_measurement")
        self.assertEqual(results["case_positive"], "accepted_non_persistence")
        self.assertEqual(results["case_negative"], "accepted_measurement")
        self.assertEqual(results["case_random"], "accepted_measurement")
        self.assertEqual(results["case_missing_frame"], "rejected_missing_frame")
        self.assertEqual(
            results["case_misaligned_frame"], "rejected_misaligned_frame"
        )

    def test_non_persistence_cannot_become_zero_displacement(self) -> None:
        document = load_fixture("rollout_measurement_scenarios_v1.json")
        case = next(
            item for item in document["cases"] if item["case_id"] == "case_non_persistence"
        )
        case["displacement_blocks"] = 0.0
        with self.assertRaisesRegex(MeasurementError, "cannot become numeric"):
            validate_phase1_rollout_measurement_fixture(document)

    def test_missing_and_misaligned_frames_cannot_be_relabelled_accepted(self) -> None:
        for case_id in ("case_missing_frame", "case_misaligned_frame"):
            with self.subTest(case_id=case_id):
                document = load_fixture("rollout_measurement_scenarios_v1.json")
                case = next(item for item in document["cases"] if item["case_id"] == case_id)
                case["measurement_status"] = "measured"
                case["displacement_blocks"] = 0.0
                with self.assertRaises(MeasurementError):
                    validate_phase1_rollout_measurement_fixture(document)

    def test_rollout_and_case_record_order_is_irrelevant(self) -> None:
        document = load_fixture("rollout_measurement_scenarios_v1.json")
        expected = validate_phase1_rollout_measurement_fixture(document)
        document["cases"].reverse()
        document["rollout_manifest"]["rollout_rows"].reverse()
        document["registry"]["runs"].reverse()
        document["registry"]["artifacts"].reverse()
        self.assertEqual(validate_phase1_rollout_measurement_fixture(document), expected)


if __name__ == "__main__":
    unittest.main()
