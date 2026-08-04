"""Focused tests for the create-only Attempt 02 annotation tool."""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "annotate_person_e_homography_refit_attempt_02.py"
SPEC = importlib.util.spec_from_file_location("attempt_02_annotation", SCRIPT)
if SPEC is None or SPEC.loader is None:  # pragma: no cover - import machinery guard
    raise RuntimeError("Could not load the Attempt 02 annotation tool.")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _verified_fixture() -> dict[str, object]:
    screenshots = []
    annotation_layouts = []
    validation_layouts = []
    for index, layout_id in enumerate(MODULE.EXPECTED_LAYOUT_IDS, start=1):
        screenshot = {
            "layout_id": layout_id,
            "path": f"C:/capture/{layout_id}.png",
            "size_bytes": 100 + index,
            "sha256": f"{index:064x}",
            "width_pixels": 1920,
            "height_pixels": 1046,
        }
        screenshots.append(screenshot)
        annotation_layouts.append(
            {
                "layout_id": layout_id,
                "fit_correspondences": [
                    {
                        "marker_id": marker_id,
                        "color": colour,
                        "world_xz_blocks": [float(point), float(index)],
                    }
                    for point, (marker_id, colour) in enumerate(
                        (
                            ("near_west", "blue"),
                            ("near_east", "yellow"),
                            ("far_east", "white"),
                            ("far_west", "lime"),
                        )
                    )
                ],
            }
        )
        validation_layouts.append(
            {
                "layout_id": layout_id,
                "validation_points": [
                    {
                        "point_id": f"validation_{point}",
                        "feature": f"validation feature {point}",
                        "world_xz_blocks": [float(point), float(index)],
                    }
                    for point in range(4)
                ],
            }
        )
    return {
        "handoff_record": {
            "path": "C:/capture/handoff.json",
            "size_bytes": 1000,
            "sha256": MODULE.EXPECTED_HANDOFF_SHA256,
        },
        "annotation_template": {"layouts": annotation_layouts},
        "annotation_template_record": {
            "path": "C:/capture/annotation.json",
            "size_bytes": 1000,
            "sha256": "a" * 64,
        },
        "validation_template": {"layouts": validation_layouts},
        "validation_template_record": {
            "path": "C:/capture/validation.json",
            "size_bytes": 1000,
            "sha256": "b" * 64,
        },
        "coordinate_convention_record": {
            "path": "C:/capture/coordinates.json",
            "size_bytes": 1000,
            "sha256": "c" * 64,
        },
        "screenshots": screenshots,
        "receipts": [
            {
                "layout_id": layout_id,
                "path": f"C:/capture/{layout_id}.json",
                "size_bytes": 100,
                "sha256": "d" * 64,
            }
            for layout_id in MODULE.EXPECTED_LAYOUT_IDS
        ],
    }


class TestAttempt02Annotation(unittest.TestCase):
    def test_tasks_cover_six_layouts_and_both_point_classes(self) -> None:
        tasks = MODULE.build_tasks(_verified_fixture())

        self.assertEqual(len(tasks), 48)
        for layout_id in MODULE.EXPECTED_LAYOUT_IDS:
            layout_tasks = [task for task in tasks if task["layout_id"] == layout_id]
            self.assertEqual(
                [task["kind"] for task in layout_tasks],
                ["fit_marker"] * 4 + ["independent_validation"] * 4,
            )
            self.assertEqual(len({task["point_id"] for task in layout_tasks}), 8)

    @mock.patch.object(MODULE, "current_git_commit", return_value="e" * 40)
    def test_complete_document_contains_no_missing_points(self, _commit: object) -> None:
        verified = _verified_fixture()
        tasks = MODULE.build_tasks(verified)
        selections = [(100 + index, 200 + index) for index in range(48)]

        document = MODULE.build_output_document(verified, tasks, selections)

        self.assertEqual(
            document["status"], "IMAGE_POINTS_COMPLETE_PENDING_HOMOGRAPHY_FIT"
        )
        self.assertTrue(document["immutable_after_creation"])
        self.assertEqual(len(document["layouts"]), 6)
        for layout in document["layouts"]:
            self.assertEqual(len(layout["fit_correspondences"]), 4)
            self.assertEqual(len(layout["independent_validation_points"]), 4)
            for point in (
                layout["fit_correspondences"]
                + layout["independent_validation_points"]
            ):
                self.assertIsNotNone(point["image_xy_pixels"])
                self.assertEqual(point["selection_status"], "operator_selected")

    def test_incomplete_document_fails_closed(self) -> None:
        verified = _verified_fixture()
        tasks = MODULE.build_tasks(verified)

        with self.assertRaisesRegex(MODULE.AnnotationInputError, "All 48"):
            MODULE.build_output_document(verified, tasks, [(1, 1)] * 47)

    def test_writer_is_create_only(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            output = Path(directory) / "nested" / "points.json"
            MODULE.write_json_create_only(output, {"value": 1})
            self.assertEqual(json.loads(output.read_text(encoding="utf-8")), {"value": 1})

            with self.assertRaises(FileExistsError):
                MODULE.write_json_create_only(output, {"value": 2})


if __name__ == "__main__":
    unittest.main()
