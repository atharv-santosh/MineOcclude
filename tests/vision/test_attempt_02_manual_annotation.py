"""Focused tests for the create-only Attempt 02 annotation tool."""

from __future__ import annotations

import importlib.util
import copy
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
        marker_geometry = (
            ("near_west", "blue", [-5.5, 4.5]),
            ("near_east", "yellow", [6.5, 4.5]),
            ("far_east", "white", [8.5, 8.5]),
            ("far_west", "lime", [-7.5, 8.5]),
        )
        annotation_layouts.append(
            {
                "layout_id": layout_id,
                "fit_correspondences": [
                    {
                        "marker_id": marker_id,
                        "color": colour,
                        "world_xz_blocks": world_xz,
                    }
                    for marker_id, colour, world_xz in marker_geometry
                ],
            }
        )
        validation_geometry = (
            ("target_ground_contact", [-6.0, 6.0]),
            ("wall_near_face_ground_negative_end", [-3.0, 2.0]),
            ("wall_near_face_ground_midpoint", [0.5, 2.0]),
            ("wall_near_face_ground_positive_end", [4.0, 2.0]),
        )
        validation_layouts.append(
            {
                "layout_id": layout_id,
                "validation_points": [
                    {
                        "point_id": point_id,
                        "feature": f"validation feature {point_id}",
                        "world_xz_blocks": world_xz,
                    }
                    for point_id, world_xz in validation_geometry
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

        self.assertEqual(len(tasks), 30)
        for layout_id in MODULE.EXPECTED_LAYOUT_IDS:
            layout_tasks = [task for task in tasks if task["layout_id"] == layout_id]
            self.assertEqual(
                [task["kind"] for task in layout_tasks],
                ["fit_correspondence"] * 4 + ["independent_validation"],
            )
            self.assertEqual(len({task["point_id"] for task in layout_tasks}), 5)
            self.assertNotIn("far_west", {task["point_id"] for task in layout_tasks})
            for task in layout_tasks:
                self.assertEqual(task["visibility_status"], "visible_unambiguous")
                self.assertTrue(task["marker_color"])
                self.assertTrue(task["location_description"])

    def test_visibility_preflight_rejects_an_invisible_requested_point(self) -> None:
        plan = copy.deepcopy(MODULE.VISIBLE_POINT_PLAN)
        plan["layout_01"]["fit"][0]["visibility_status"] = "fully_occluded"

        with self.assertRaisesRegex(
            MODULE.AnnotationInputError, "not visible and unambiguous"
        ):
            MODULE.build_tasks(_verified_fixture(), plan)

    @mock.patch.object(MODULE, "current_git_commit", return_value="e" * 40)
    def test_complete_document_contains_no_missing_points(self, _commit: object) -> None:
        verified = _verified_fixture()
        tasks = MODULE.build_tasks(verified)
        selections = [(100 + index, 200 + index) for index in range(30)]

        document = MODULE.build_output_document(verified, tasks, selections)

        self.assertEqual(
            document["status"], "IMAGE_POINTS_COMPLETE_PENDING_HOMOGRAPHY_FIT"
        )
        self.assertTrue(document["immutable_after_creation"])
        self.assertEqual(len(document["layouts"]), 6)
        for layout in document["layouts"]:
            self.assertEqual(len(layout["fit_correspondences"]), 4)
            self.assertEqual(len(layout["independent_validation_points"]), 1)
            for point in (
                layout["fit_correspondences"]
                + layout["independent_validation_points"]
            ):
                self.assertIsNotNone(point["image_xy_pixels"])
                self.assertEqual(point["selection_status"], "operator_selected")

    def test_incomplete_document_fails_closed(self) -> None:
        verified = _verified_fixture()
        tasks = MODULE.build_tasks(verified)

        with self.assertRaisesRegex(MODULE.AnnotationInputError, "All 30"):
            MODULE.build_output_document(verified, tasks, [(1, 1)] * 29)

    def test_writer_is_create_only(self) -> None:
        output = ROOT / "unused-test-output" / "points.json"
        stream = mock.MagicMock()
        context = mock.MagicMock()
        context.__enter__.return_value = stream
        with (
            mock.patch.object(Path, "mkdir") as mkdir,
            mock.patch.object(
                Path, "open", side_effect=(context, FileExistsError("exists"))
            ) as open_file,
        ):
            MODULE.write_json_create_only(output, {"value": 1})
            with self.assertRaises(FileExistsError):
                MODULE.write_json_create_only(output, {"value": 2})

        mkdir.assert_called_with(parents=True, exist_ok=True)
        self.assertEqual(open_file.call_count, 2)
        open_file.assert_called_with("x", encoding="utf-8", newline="\n")
        stream.write.assert_called()


if __name__ == "__main__":
    unittest.main()
