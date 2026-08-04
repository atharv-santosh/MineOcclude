"""Focused tests for the layouts 04/06 create-only annotation repair."""

from __future__ import annotations

import copy
import importlib.util
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "repair_person_e_layout_04_06_annotations.py"
SPEC = importlib.util.spec_from_file_location("layout_04_06_repair", SCRIPT)
if SPEC is None or SPEC.loader is None:  # pragma: no cover
    raise RuntimeError("Could not load the layouts 04/06 repair tool.")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class TestLayout0406AnnotationRepair(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.verified = MODULE.verify_inputs()
        cls.tasks = MODULE.build_tasks(cls.verified)
        cls.regions = MODULE.build_feature_regions(cls.verified, cls.tasks)

    def test_tasks_cover_only_all_five_points_in_each_failed_layout(self) -> None:
        self.assertEqual(len(self.tasks), 10)
        self.assertEqual(
            {task["layout_id"] for task in self.tasks}, set(MODULE.TARGET_LAYOUT_IDS)
        )
        for layout_id in MODULE.TARGET_LAYOUT_IDS:
            layout_tasks = [
                task for task in self.tasks if task["layout_id"] == layout_id
            ]
            self.assertEqual(
                tuple(task["point_id"] for task in layout_tasks),
                MODULE.EXPECTED_POINT_IDS,
            )
            self.assertEqual(
                [task["kind"] for task in layout_tasks],
                ["fit_correspondence"] * 4 + ["independent_validation"],
            )
            for task in layout_tasks:
                self.assertTrue(task["marker_color"])
                self.assertTrue(task["location_description"])
                self.assertEqual(len(task["world_xz_blocks"]), 2)

    def test_feature_regions_reject_clicks_outside_visible_features(self) -> None:
        self.assertEqual(len(self.regions), 10)
        for task, region in zip(self.tasks, self.regions):
            allowed = region["allowed_pixels"]
            self.assertTrue(allowed)
            self.assertTrue(MODULE.is_click_allowed(region, next(iter(allowed))))
            self.assertFalse(MODULE.is_click_allowed(region, (0, 0)))
            if task["source_kind"] == "marker":
                self.assertEqual(region["diagnostic"]["confidence"], "high")

    def test_old_wall_clicks_are_not_ground_contact_corners(self) -> None:
        expected_anchors = {
            ("layout_04", "wall_near_face_ground_negative_end"): (1267, 664),
            ("layout_04", "wall_near_face_ground_positive_end"): (652, 664),
            ("layout_06", "wall_near_face_ground_negative_end"): (685, 649),
            ("layout_06", "wall_near_face_ground_positive_end"): (1234, 649),
        }
        for task, region in zip(self.tasks, self.regions):
            if task["source_kind"] != "validation_feature":
                continue
            key = (task["layout_id"], task["point_id"])
            self.assertEqual(region["anchor"], expected_anchors[key])
            self.assertFalse(
                MODULE.is_click_allowed(region, task["original_image_xy_pixels"])
            )

    def test_nearest_neighbour_mapping_is_integer_and_unscaled(self) -> None:
        self.assertEqual(MODULE.map_zoom_click((500, 600), (0, 0)), (500, 600))
        self.assertEqual(MODULE.map_zoom_click((500, 600), (7, 7)), (500, 600))
        self.assertEqual(MODULE.map_zoom_click((500, 600), (8, 16)), (501, 602))
        with self.assertRaisesRegex(MODULE.RepairInputError, "positive"):
            MODULE.map_zoom_click((0, 0), (0, 0), zoom=0)

    @mock.patch.object(MODULE, "current_git_commit", return_value="a" * 40)
    def test_output_reuses_four_layouts_and_replaces_all_ten_points(
        self, _commit: object
    ) -> None:
        base = copy.deepcopy(self.verified["document"])
        selections = []
        for task, region in zip(self.tasks, self.regions):
            if "anchor" in region:
                selections.append(region["anchor"])
            else:
                old_x, old_y = task["original_image_xy_pixels"]
                selections.append(
                    min(
                        region["allowed_pixels"],
                        key=lambda point: (point[0] - old_x) ** 2
                        + (point[1] - old_y) ** 2,
                    )
                )

        output = MODULE.build_output_document(
            self.verified, self.tasks, selections
        )

        base_layouts = MODULE._layout_map(base)
        output_layouts = MODULE._layout_map(output)
        for layout_id in MODULE.REUSED_LAYOUT_IDS:
            self.assertEqual(output_layouts[layout_id], base_layouts[layout_id])
        for layout_id in MODULE.TARGET_LAYOUT_IDS:
            for point in MODULE._point_map(output_layouts[layout_id]).values():
                self.assertEqual(
                    point["selection_status"],
                    "operator_reselected_nearest_neighbour_crop",
                )
        repair = output["annotation_method"]["repair"]
        self.assertEqual(repair["reannotation_point_count"], 10)
        self.assertFalse(repair["homography_fit_performed"])
        self.assertFalse(repair["replacement_package_emitted"])

    def test_incomplete_output_fails_closed(self) -> None:
        with self.assertRaisesRegex(MODULE.RepairInputError, "All 10"):
            MODULE.build_output_document(
                self.verified, self.tasks, [(1, 1)] * 9
            )

    def test_writer_is_additive_and_create_only(self) -> None:
        output = ROOT / "unused-test-output" / "annotation.json"
        stream = mock.MagicMock()
        context = mock.MagicMock()
        context.__enter__.return_value = stream
        with (
            mock.patch.object(Path, "mkdir") as mkdir,
            mock.patch.object(
                Path, "open", side_effect=(context, FileExistsError("exists"))
            ) as open_file,
        ):
            MODULE.write_json_create_only(output, {"ok": True})
            with self.assertRaises(FileExistsError):
                MODULE.write_json_create_only(output, {"ok": False})

        mkdir.assert_called_with(parents=True, exist_ok=True)
        self.assertEqual(open_file.call_count, 2)
        open_file.assert_called_with("x", encoding="utf-8", newline="\n")
        stream.write.assert_called()

    def test_original_annotation_package_and_handoff_still_match(self) -> None:
        MODULE.verify_preserved_artifacts()
        self.assertFalse(MODULE.DEFAULT_OUTPUT.exists())


if __name__ == "__main__":
    unittest.main()
