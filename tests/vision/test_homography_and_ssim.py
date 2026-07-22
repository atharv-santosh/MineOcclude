from __future__ import annotations

import unittest

from mineocclude.vision.homography import (
    HomographyError,
    fit_marker_homography,
    summarize_localization,
)
from mineocclude.vision.ssim import (
    SsimError,
    compare_frames,
    compute_ssim,
    require_frame_alignment,
    require_natural_variation_pair,
    summarize_natural_variation,
)


class TestHomography(unittest.TestCase):
    def test_known_affine_mapping_and_localization_report(self) -> None:
        marker_ids = ["north_west", "north_east", "south_east", "south_west"]
        image_points = {
            "north_west": [0.0, 0.0],
            "north_east": [2.0, 0.0],
            "south_east": [2.0, 2.0],
            "south_west": [0.0, 2.0],
        }
        world_points = {
            "north_west": [10.0, -2.0],
            "north_east": [14.0, -2.0],
            "south_east": [14.0, 4.0],
            "south_west": [10.0, 4.0],
        }
        homography = fit_marker_homography(
            image_points,
            world_points,
            marker_ids=marker_ids,
            layout_id="layout_1",
            canonical_camera_pose_id="pose_1",
        )
        world = homography.transform([1.0, 1.0])
        self.assertAlmostEqual(world[0], 12.0)
        self.assertAlmostEqual(world[1], 1.0)
        report = summarize_localization(
            homography,
            [([0.5, 1.5], [11.0, 2.5]), ([1.0, 1.0], [12.0, 1.0])],
            wall_parallel_origin_xz=[10.0, -2.0],
            wall_parallel_positive_unit_xz=[1.0, 0.0],
            image_regions=["left", "center"],
        )
        self.assertAlmostEqual(
            report["median_absolute_wall_parallel_error_blocks"], 0.0
        )
        self.assertEqual(report["sample_count"], 2)
        self.assertTrue(report["planning_gate_passed"])
        self.assertIsNone(report["minimum_shift_if_gate_fails_blocks"])
        self.assertEqual(report["by_image_region"]["left"]["sample_count"], 1)

    def test_degenerate_markers_are_rejected(self) -> None:
        ids = ["a", "b", "c", "d"]
        with self.assertRaises(HomographyError):
            fit_marker_homography(
                {name: [float(index), 0.0] for index, name in enumerate(ids)},
                {name: [float(index), 0.0] for index, name in enumerate(ids)},
                marker_ids=ids,
                layout_id="layout_1",
                canonical_camera_pose_id="pose_1",
            )


class TestSsim(unittest.TestCase):
    def test_identical_frames_have_unit_ssim(self) -> None:
        image = [[[100, 100, 100] for _ in range(4)] for _ in range(4)]
        self.assertAlmostEqual(compute_ssim(image, image, data_range=255.0), 1.0)

    def test_background_mask_excludes_subject_difference(self) -> None:
        baseline = [[[50, 50, 50] for _ in range(6)] for _ in range(6)]
        pushed = [[[50, 50, 50] for _ in range(6)] for _ in range(6)]
        for y in range(2, 4):
            for x in range(1, 3):
                baseline[y][x] = [255, 0, 255]
        for y in range(2, 4):
            for x in range(3, 5):
                pushed[y][x] = [255, 0, 255]
        result = compare_frames(
            pushed,
            baseline,
            data_range=255.0,
            pushed_box_xyxy=[3, 2, 5, 4],
            baseline_box_xyxy=[1, 2, 3, 4],
            background_margin_pixels=0,
        )
        self.assertLess(result.full_frame_ssim, 1.0)
        self.assertAlmostEqual(result.background_masked_ssim, 1.0)
        summary = summarize_natural_variation([1.0, 0.9, 0.95])
        self.assertAlmostEqual(summary["median"], 0.95)

    def test_alignment_and_dimensions_are_strict(self) -> None:
        with self.assertRaises(SsimError):
            require_frame_alignment(
                {"event_id": "e", "seed": 1, "rollout_frame_idx": 2},
                {"event_id": "e", "seed": 1, "rollout_frame_idx": 3},
            )
        with self.assertRaises(SsimError):
            compute_ssim(
                [[[0, 0, 0], [0, 0, 0]]],
                [[[0, 0, 0]]],
                data_range=255.0,
            )
        with self.assertRaises(SsimError):
            compute_ssim([[[0]]], [[[0]]], data_range=255.0)

    def test_natural_variation_requires_independent_alpha_zero_runs(self) -> None:
        first = {
            "event_id": "event_1",
            "layout_id": "layout_1",
            "rollout_frame_idx": 2,
            "rollout_id": "zero_1",
            "control_type": "alpha_zero",
            "seed": 1,
        }
        second = {**first, "rollout_id": "zero_2", "seed": 2}
        require_natural_variation_pair(first, second)
        with self.assertRaises(SsimError):
            require_natural_variation_pair(first, {**second, "seed": 1})


if __name__ == "__main__":
    unittest.main()
