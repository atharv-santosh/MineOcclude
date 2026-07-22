from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from mineocclude.experiments.registry import hash_json_value
from mineocclude.vision.calibration import (
    CalibrationDatasetError,
    frames_for_split,
    load_detector_calibration_dataset,
    validate_detector_calibration_dataset,
)
from mineocclude.vision.config import DEFAULT_PERSON_E_CONFIG_PATH


ROOT = Path(__file__).resolve().parents[2]
EVALUATOR = ROOT / "scripts" / "evaluate_magenta_detector.py"
MAGENTA = [255, 0, 255]


def _image(*, present: bool, background: int) -> list[list[list[int]]]:
    image = [[[background, background, background] for _ in range(5)] for _ in range(5)]
    if present:
        for y in (2, 3):
            for x in (1, 2):
                image[y][x] = list(MAGENTA)
    return image


def calibration_dataset() -> dict[str, object]:
    frames = []
    specifications = (
        ("calibration_visible", "calibration", "visible", True, 0),
        ("calibration_negative", "calibration", "negative", False, 1),
        ("heldout_visible", "heldout", "visible", True, 2),
        ("heldout_negative", "heldout", "negative", False, 3),
    )
    for frame_index, specification in enumerate(specifications):
        frame_id, split, truth_class, truth_present, background = specification
        rgb = _image(present=truth_present, background=background)
        frames.append(
            {
                "frame_id": frame_id,
                "layout_id": "layout_1",
                "canonical_camera_pose_id": "pose_1",
                "split": split,
                "truth_class": truth_class,
                "truth_present": truth_present,
                "source_artifact_id": "capture_1",
                "source_frame_idx": frame_index,
                "source_frame_hash": f"{frame_index + 1:x}" * 64,
                "decoded_rgb_hash": hash_json_value(rgb),
                "rgb": rgb,
            }
        )
    markers = [
        {
            "marker_id": marker_id,
            "image_xy": image_xy,
            "world_xz_blocks": world_xz,
            "coordinate_source_hash": f"{index + 5:x}" * 64,
        }
        for index, (marker_id, image_xy, world_xz) in enumerate(
            (
                ("north_west", [0.0, 0.0], [0.0, 0.0]),
                ("north_east", [4.0, 0.0], [4.0, 0.0]),
                ("south_east", [4.0, 4.0], [4.0, 4.0]),
                ("south_west", [0.0, 4.0], [0.0, 4.0]),
            )
        )
    ]
    return {
        "schema_version": "1.0",
        "detector_calibration_schema_version": (
            "person-e-detector-calibration-dataset-v0.1"
        ),
        "dataset_id": "detector_calibration_1",
        "layouts": [
            {
                "layout_id": "layout_1",
                "canonical_camera_pose_id": "pose_1",
                "marker_set_id": "marker_set_1",
                "marker_set_source_hash": "e" * 64,
                "markers": markers,
            }
        ],
        "frames": frames,
    }


class TestCalibrationDataset(unittest.TestCase):
    def test_valid_dataset_loads_once_with_literal_hash_and_split(self) -> None:
        document = calibration_dataset()
        validate_detector_calibration_dataset(document)
        self.assertEqual(len(frames_for_split(document, "calibration")), 2)
        self.assertEqual(len(frames_for_split(document, "heldout")), 2)
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "calibration.json"
            payload = json.dumps(document).encode("utf-8")
            path.write_bytes(payload)
            loaded, literal_hash = load_detector_calibration_dataset(path)
        self.assertEqual(loaded["dataset_id"], "detector_calibration_1")
        self.assertEqual(literal_hash, hashlib.sha256(payload).hexdigest())

    def test_duplicate_truth_hash_and_coverage_errors_are_rejected(self) -> None:
        mutations = {}

        duplicate_id = copy.deepcopy(calibration_dataset())
        duplicate_id["frames"][1]["frame_id"] = duplicate_id["frames"][0][
            "frame_id"
        ]
        mutations["duplicate frame"] = duplicate_id

        inconsistent_truth = copy.deepcopy(calibration_dataset())
        inconsistent_truth["frames"][0]["truth_present"] = False
        mutations["truth mismatch"] = inconsistent_truth

        bad_hash = copy.deepcopy(calibration_dataset())
        bad_hash["frames"][0]["decoded_rgb_hash"] = "0" * 64
        mutations["decoded hash"] = bad_hash

        missing_coverage = copy.deepcopy(calibration_dataset())
        missing_coverage["frames"] = missing_coverage["frames"][:-1]
        mutations["split/layout coverage"] = missing_coverage

        duplicate_source = copy.deepcopy(calibration_dataset())
        duplicate_source["frames"][1]["source_frame_idx"] = duplicate_source[
            "frames"
        ][0]["source_frame_idx"]
        mutations["source frame identity"] = duplicate_source

        three_markers = copy.deepcopy(calibration_dataset())
        three_markers["layouts"][0]["markers"] = three_markers["layouts"][0][
            "markers"
        ][:-1]
        mutations["four marker requirement"] = three_markers

        for label, document in mutations.items():
            with self.subTest(label=label), self.assertRaises(CalibrationDatasetError):
                validate_detector_calibration_dataset(document)


class TestDetectorEvaluationCli(unittest.TestCase):
    def _run_evaluator(
        self,
        *,
        input_path: Path,
        output_path: Path,
        split: str,
        calibration_report: Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        arguments = [
                sys.executable,
                str(EVALUATOR),
                str(input_path),
                str(output_path),
                "--split",
                split,
                "--threshold-version",
                "detector_threshold_v1",
                "--producer-run-id",
                f"detector_{split}_run_1",
                "--code-sha",
                "a" * 40,
                "--config",
                str(DEFAULT_PERSON_E_CONFIG_PATH),
        ]
        if split == "calibration":
            arguments.extend(
                [
                    "--hsv-range",
                    "280",
                    "320",
                    "0.5",
                    "1.0",
                    "0.5",
                    "1.0",
                    "--min-area",
                    "1",
                ]
            )
        elif calibration_report is not None:
            arguments.extend(["--calibration-report", str(calibration_report)])
        return subprocess.run(
            arguments,
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

    def test_only_heldout_split_can_claim_gate_and_metrics_are_per_layout(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary = Path(temporary_directory)
            input_path = temporary / "calibration.json"
            input_path.write_text(
                json.dumps(calibration_dataset()), encoding="utf-8"
            )
            reports = {}
            calibration_path = temporary / "calibration_report.json"
            completed = self._run_evaluator(
                input_path=input_path,
                output_path=calibration_path,
                split="calibration",
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            reports["calibration"] = json.loads(
                calibration_path.read_text(encoding="utf-8")
            )
            heldout_path = temporary / "heldout_report.json"
            completed = self._run_evaluator(
                input_path=input_path,
                output_path=heldout_path,
                split="heldout",
                calibration_report=calibration_path,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            reports["heldout"] = json.loads(
                heldout_path.read_text(encoding="utf-8")
            )

        calibration = reports["calibration"]
        heldout = reports["heldout"]
        self.assertNotIn("planning_gate_passed", calibration["metrics"])
        self.assertNotIn(
            "planning_gate_passed", calibration["per_layout_metrics"][0]
        )
        self.assertFalse(calibration["heldout_gate"]["eligible"])
        self.assertTrue(heldout["metrics"]["planning_gate_passed"])
        self.assertTrue(heldout["per_layout_metrics"][0]["planning_gate_passed"])
        self.assertTrue(heldout["heldout_gate"]["eligible"])
        self.assertIsNotNone(heldout["calibration_report_hash"])
        self.assertEqual(heldout["per_layout_metrics"][0]["layout_id"], "layout_1")
        self.assertEqual(heldout["producer_run_id"], "detector_heldout_run_1")
        self.assertEqual(heldout["code_sha"], "a" * 40)
        self.assertEqual(len(heldout["rows"]), 2)
        self.assertTrue(all(row["split"] == "heldout" for row in heldout["rows"]))

    def test_heldout_cannot_select_settings_directly(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary = Path(temporary_directory)
            input_path = temporary / "calibration.json"
            input_path.write_text(
                json.dumps(calibration_dataset()), encoding="utf-8"
            )
            completed = self._run_evaluator(
                input_path=input_path,
                output_path=temporary / "heldout.json",
                split="heldout",
            )
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("--calibration-report", completed.stderr)


if __name__ == "__main__":
    unittest.main()
