from __future__ import annotations

import unittest

from mineocclude.vision.homography import (
    HomographyError,
    fit_marker_homography,
    homography_from_record,
    localize_ground_contact_from_background_pair,
    localize_marker_top_face,
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
    def test_registered_image_localizers_are_deterministic(self) -> None:
        marker_image = [[[0, 0, 0] for _ in range(30)] for _ in range(30)]
        for y, bounds in enumerate(
            ((8, 19), (9, 20), (10, 21), (11, 22), (12, 23)),
            start=18,
        ):
            for x in range(bounds[0], bounds[1] + 1):
                marker_image[y][x] = [0, 0, 160]
        marker = localize_marker_top_face(
            marker_image,
            marker_color="blue",
        )
        self.assertEqual(marker["bounding_box_xyxy"], [8, 18, 24, 23])
        self.assertEqual(marker["segmentation_pixel_count"], 60)
        self.assertEqual(
            marker["localization_method_version"],
            "person-e-marker-color-top-face-diagonals-v0.1",
        )

        background = [[[0, 0, 0] for _ in range(10)] for _ in range(10)]
        visible = [[list(pixel) for pixel in row] for row in background]
        for y in range(3, 8):
            for x in range(2, 6):
                visible[y][x] = [120, 0, 120]
        ground = localize_ground_contact_from_background_pair(
            visible,
            background,
        )
        self.assertEqual(ground["image_xy"], [3.5, 7.0])
        self.assertEqual(ground["bounding_box_xyxy"], [2, 3, 6, 8])

    def test_bound_record_round_trip_preserves_resolution_and_sources(self) -> None:
        ids = ["north_west", "north_east", "south_east", "south_west"]
        points = {
            "north_west": [0.0, 0.0],
            "north_east": [2.0, 0.0],
            "south_east": [2.0, 2.0],
            "south_west": [0.0, 2.0],
        }
        homography = fit_marker_homography(
            points,
            points,
            marker_ids=ids,
            layout_id="layout_1",
            canonical_camera_pose_id="pose_1",
            resolution_id="resolution_640x360_rgb8",
            image_width_px=640,
            image_height_px=360,
            source_correspondence_hash="a" * 64,
            detector_version="detector_v1",
            software_runtime_hash="b" * 64,
        )
        record = homography.to_record()
        self.assertEqual(record["resolution_id"], "resolution_640x360_rgb8")
        self.assertEqual(record["source_correspondence_hash"], "a" * 64)
        restored = homography_from_record(record)
        self.assertEqual(restored.to_record(), record)
        tampered = dict(record)
        tampered["image_width_px"] = None
        with self.assertRaisesRegex(HomographyError, "all-or-none"):
            homography_from_record(tampered)

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

    def test_known_projective_transform_is_recovered_exactly(self) -> None:
        """A real camera is perspective, not affine.

        The affine case above still passes if the two perspective terms are
        dropped, so it cannot detect that class of regression. This fits a
        transform whose perspective terms are non-zero and requires them back.
        """
        known = (
            (2.0, 0.3, 5.0),
            (0.1, 1.5, -4.0),
            (0.002, 0.004, 1.0),
        )

        def project(point: tuple[float, float]) -> list[float]:
            x, y = point
            denominator = known[2][0] * x + known[2][1] * y + known[2][2]
            return [
                (known[0][0] * x + known[0][1] * y + known[0][2]) / denominator,
                (known[1][0] * x + known[1][1] * y + known[1][2]) / denominator,
            ]

        marker_ids = ["north_west", "north_east", "south_east", "south_west"]
        image_points = {
            "north_west": [10.0, 20.0],
            "north_east": [90.0, 25.0],
            "south_east": [85.0, 80.0],
            "south_west": [15.0, 70.0],
        }
        world_points = {
            name: project((point[0], point[1])) for name, point in image_points.items()
        }

        homography = fit_marker_homography(
            image_points,
            world_points,
            marker_ids=marker_ids,
            layout_id="layout_projective",
            canonical_camera_pose_id="pose_projective",
        )

        for row_index, expected_row in enumerate(known):
            for column_index, expected in enumerate(expected_row):
                self.assertAlmostEqual(
                    homography.matrix[row_index][column_index], expected, places=12
                )

        # Guard the perspective terms explicitly: an affine-only fit zeroes them.
        self.assertNotAlmostEqual(homography.matrix[2][0], 0.0, places=6)
        self.assertNotAlmostEqual(homography.matrix[2][1], 0.0, places=6)

        # A point strictly inside the marker quad, away from every fit point.
        interior = homography.transform([42.0, 55.0])
        self.assertAlmostEqual(interior[0], 80.90490797546012, places=9)
        self.assertAlmostEqual(interior[1], 63.420245398773005, places=9)

    def test_malformed_and_degenerate_inputs_fail_closed(self) -> None:
        """Each rejection reason stays distinct, so failures cannot be confused."""
        marker_ids = ["north_west", "north_east", "south_east", "south_west"]
        square = {
            "north_west": [0.0, 0.0],
            "north_east": [1.0, 0.0],
            "south_east": [1.0, 1.0],
            "south_west": [0.0, 1.0],
        }
        singular = "singular or numerically degenerate"
        not_unique = "must be unique in both spaces"
        cases = [
            (
                "three of four image points collinear",
                {
                    "north_west": [0.0, 0.0],
                    "north_east": [1.0, 0.0],
                    "south_east": [2.0, 0.0],
                    "south_west": [0.0, 1.0],
                },
                square,
                marker_ids,
                singular,
            ),
            (
                "world points collinear, image points valid",
                square,
                {
                    "north_west": [0.0, 0.0],
                    "north_east": [1.0, 0.0],
                    "south_east": [2.0, 0.0],
                    "south_west": [3.0, 0.0],
                },
                marker_ids,
                singular,
            ),
            (
                "duplicate image point",
                {
                    "north_west": [0.0, 0.0],
                    "north_east": [1.0, 0.0],
                    "south_east": [1.0, 1.0],
                    "south_west": [0.0, 0.0],
                },
                square,
                marker_ids,
                not_unique,
            ),
            (
                "duplicate world point",
                square,
                {
                    "north_west": [0.0, 0.0],
                    "north_east": [1.0, 0.0],
                    "south_east": [1.0, 1.0],
                    "south_west": [1.0, 1.0],
                },
                marker_ids,
                not_unique,
            ),
            (
                "non-finite image coordinate (nan)",
                {**square, "north_west": [float("nan"), 0.0]},
                square,
                marker_ids,
                "coordinates must be finite numbers",
            ),
            (
                "non-finite image coordinate (inf)",
                {**square, "north_west": [float("inf"), 0.0]},
                square,
                marker_ids,
                "coordinates must be finite numbers",
            ),
            (
                "three marker ids instead of four",
                {name: square[name] for name in marker_ids[:3]},
                {name: square[name] for name in marker_ids[:3]},
                marker_ids[:3],
                "must contain four unique non-empty IDs",
            ),
        ]
        for label, image_points, world_points, ids, expected in cases:
            with self.subTest(case=label):
                with self.assertRaisesRegex(HomographyError, expected):
                    fit_marker_homography(
                        image_points,
                        world_points,
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
