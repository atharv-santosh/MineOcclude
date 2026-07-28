from __future__ import annotations

import copy
import hashlib
import json
import unittest
from pathlib import Path

from mineocclude.experiments.registry import (
    ImmutableRegistryIndex,
    formatted_json_bytes,
    hash_json_value,
    require_valid_immutable_registry,
)
from mineocclude.vision.calibration import (
    CalibrationDatasetError,
    load_committed_frame_rgb,
    validate_detector_calibration_dataset,
)
from mineocclude.vision.config import validate_person_e_config
from mineocclude.vision.homography import homography_from_record
from mineocclude.vision.magenta import validate_detection_document

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs" / "status" / "person_e_phase2_v0_1"


def load(name: str) -> dict[str, object]:
    return json.loads((EVIDENCE / name).read_text(encoding="utf-8"))


class TestPhase2RealEvidence(unittest.TestCase):
    def test_frozen_split_resolves_all_committed_frames_exactly(self) -> None:
        split = load("frozen_split_manifest.json")
        validate_detector_calibration_dataset(split)
        self.assertEqual(len(split["frames"]), 72)
        self.assertEqual(len(split["layouts"]), 6)
        calibration = {
            (row["source_artifact_id"], row["source_frame_idx"])
            for row in split["frames"]
            if row["split"] == "calibration"
        }
        heldout = {
            (row["source_artifact_id"], row["source_frame_idx"])
            for row in split["frames"]
            if row["split"] == "heldout"
        }
        self.assertEqual(len(calibration), 36)
        self.assertEqual(len(heldout), 36)
        self.assertTrue(calibration.isdisjoint(heldout))
        for frame in split["frames"]:
            with self.subTest(frame_id=frame["frame_id"]):
                rgb = load_committed_frame_rgb(frame, repository=ROOT)
                self.assertEqual(len(rgb), 360)
                self.assertEqual(len(rgb[0]), 640)

    def test_tampered_source_and_split_are_rejected(self) -> None:
        split = load("frozen_split_manifest.json")
        tampered = copy.deepcopy(split)
        tampered["frames"][0]["source_frame_hash"] = "0" * 64
        with self.assertRaises(CalibrationDatasetError):
            validate_detector_calibration_dataset(tampered)
        with self.assertRaisesRegex(
            CalibrationDatasetError, "source_frame_hash"
        ):
            load_committed_frame_rgb(tampered["frames"][0], repository=ROOT)

    def test_detector_records_are_calibration_only_and_identity_bound(self) -> None:
        split = load("frozen_split_manifest.json")
        detections = load("calibration_detection_records.json")
        report = load("calibration_report.json")
        config = load("frozen_detector_config.json")
        validate_detection_document(detections)
        validate_person_e_config(config)
        self.assertEqual(len(detections["records"]), 36)
        self.assertTrue(
            all(row["split"] == "calibration" for row in detections["records"])
        )
        self.assertTrue(
            all(
                row["detector_version"] == detections["detector_version"]
                and row["threshold_version"] == detections["threshold_version"]
                for row in detections["records"]
            )
        )
        self.assertFalse(report["heldout_opened_for_parameter_selection"])
        self.assertFalse(report["heldout_performance_reported"])
        self.assertEqual(report["metrics"]["true_positive"], 18)
        self.assertEqual(report["metrics"]["true_negative"], 18)
        self.assertEqual(report["metrics"]["false_positive"], 0)
        self.assertEqual(report["metrics"]["false_negative"], 0)
        split_hash = hashlib.sha256(
            (EVIDENCE / "frozen_split_manifest.json").read_bytes()
        ).hexdigest()
        self.assertEqual(config["detector"]["calibration_dataset_hash"], split_hash)
        self.assertEqual(
            detections["split_version"],
            split["split_version"],
        )

    def test_homographies_bind_resolution_sources_and_real_probes(self) -> None:
        correspondences = load("homography_correspondences.json")
        homographies = load("homography_record.json")
        localization = load("localization_validation_report.json")
        self.assertEqual(len(correspondences["layouts"]), 6)
        self.assertEqual(len(homographies["records"]), 6)
        self.assertEqual(localization["sample_count"], 36)
        self.assertEqual(len(localization["by_location"]), 36)
        self.assertEqual(
            len(
                {
                    row["location_id"]
                    for row in localization["by_location"]
                }
            ),
            36,
        )
        for layout, record in zip(
            correspondences["layouts"],
            homographies["records"],
            strict=True,
        ):
            source = dict(layout)
            claimed_hash = source.pop("correspondence_hash")
            self.assertEqual(claimed_hash, hash_json_value(source))
            homography = homography_from_record(record)
            self.assertEqual(homography.resolution_id, "resolution_640x360_rgb8")
            self.assertEqual(homography.image_width_px, 640)
            self.assertEqual(homography.image_height_px, 360)
            self.assertEqual(
                homography.source_correspondence_hash,
                claimed_hash,
            )
            self.assertIsNotNone(homography.detector_version)
            self.assertIsNotNone(homography.software_runtime_hash)
        for row in localization["records"]:
            homography = next(
                homography_from_record(record)
                for record in homographies["records"]
                if record["layout_id"] == row["layout_id"]
            )
            predicted = homography.transform(row["image_xy"])
            self.assertAlmostEqual(predicted[0], row["predicted_world_xz"][0])
            self.assertAlmostEqual(predicted[1], row["predicted_world_xz"][1])

    def test_real_registry_and_all_json_bytes_are_canonical_utf8_lf(
        self,
    ) -> None:
        registry = load("registry_snapshot.json")
        receipt = load("step2_1_registry_receipt.json")
        status = load("phase2_status.json")
        self.assertTrue(require_valid_immutable_registry(registry).accepted)
        index = ImmutableRegistryIndex(registry)
        self.assertEqual(len(index.query_runs()), 4)
        self.assertEqual(
            receipt["run_counts_by_lifecycle_status"],
            {"in_progress": 0, "completed": 2, "failed": 2},
        )
        self.assertEqual(receipt["accepted_artifact_count"], 28)
        steps = {row["step"]: row for row in status["steps"]}
        self.assertEqual(steps["2.1"]["status"], "PASS")
        self.assertEqual(steps["2.4"]["status"], "PARTIAL")
        self.assertEqual(status["overall_status"], "PARTIAL")
        for path in sorted(EVIDENCE.glob("*.json")):
            with self.subTest(path=path.name):
                payload = path.read_bytes()
                self.assertFalse(payload.startswith(b"\xef\xbb\xbf"))
                self.assertNotIn(b"\r\n", payload)
                document = json.loads(payload.decode("utf-8"))
                self.assertEqual(payload, formatted_json_bytes(document))


if __name__ == "__main__":
    unittest.main()
