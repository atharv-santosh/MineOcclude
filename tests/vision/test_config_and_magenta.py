from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from mineocclude.vision.config import (
    DEFAULT_PERSON_E_CONFIG_PATH,
    hash_person_e_config,
    load_person_e_config,
    require_live_ready_person_e_config,
)
from mineocclude.vision.magenta import (
    HsvRange,
    VisionInputError,
    detect_magenta,
    evaluate_presence,
)
from tests.vision.person_e_test_helpers import write_live_config


MAGENTA = [255, 0, 255]
BLACK = [0, 0, 0]


def image_with_block() -> list[list[list[int]]]:
    image = [[list(BLACK) for _ in range(5)] for _ in range(5)]
    for y in (2, 3):
        for x in (1, 2):
            image[y][x] = list(MAGENTA)
    return image


def blank_image(width: int, height: int) -> list[list[list[int]]]:
    return [[list(BLACK) for _ in range(width)] for _ in range(height)]


def paint_block(
    image: list[list[list[int]]],
    x0: int,
    y0: int,
    x1: int,
    y1: int,
    color: list[int] = MAGENTA,
) -> list[list[list[int]]]:
    """Paint the half-open pixel rectangle [x0, x1) x [y0, y1)."""
    for y in range(y0, y1):
        for x in range(x0, x1):
            image[y][x] = list(color)
    return image


class TestPersonEConfig(unittest.TestCase):
    def test_config_hash_uses_validated_literal_bytes(self) -> None:
        config = load_person_e_config()
        self.assertEqual(config["detector"]["hsv_ranges"], [])
        self.assertEqual(
            config["ssim"]["background_mask_margin_pixels"], None
        )
        self.assertEqual(
            hash_person_e_config(),
            hashlib.sha256(DEFAULT_PERSON_E_CONFIG_PATH.read_bytes()).hexdigest(),
        )

    def test_only_calibrated_instance_is_live_ready(self) -> None:
        with self.assertRaisesRegex(ValueError, "calibrated_live_ready"):
            require_live_ready_person_e_config()
        with tempfile.TemporaryDirectory() as temporary_directory:
            config_path = write_live_config(Path(temporary_directory))
            config = require_live_ready_person_e_config(config_path)
            self.assertEqual(config["status"], "calibrated_live_ready")


class TestMagentaDetector(unittest.TestCase):
    def setUp(self) -> None:
        self.threshold = HsvRange(280.0, 320.0, 0.5, 1.0, 0.5, 1.0)

    def test_detects_centroid_area_and_exclusive_box(self) -> None:
        result = detect_magenta(
            image_with_block(),
            hsv_ranges=[self.threshold],
            min_area_pixels=2,
        )
        self.assertTrue(result.detected)
        self.assertEqual(result.centroid_xy, (1.5, 2.5))
        self.assertEqual(result.area_pixels, 4)
        self.assertEqual(result.bounding_box_xyxy, (1, 2, 3, 4))

    def test_no_match_and_heldout_presence_metrics(self) -> None:
        absent = detect_magenta(
            [[list(BLACK) for _ in range(3)] for _ in range(3)],
            hsv_ranges=[self.threshold],
        )
        present = detect_magenta(
            image_with_block(),
            hsv_ranges=[self.threshold],
        )
        self.assertEqual(absent.rejection_reason, "no_threshold_match")
        metrics = evaluate_presence([(True, present), (False, absent)])
        self.assertEqual(metrics.precision, 1.0)
        self.assertEqual(metrics.recall, 1.0)

    def test_equal_area_blobs_break_ties_top_then_left(self) -> None:
        same_row = paint_block(paint_block(blank_image(8, 8), 1, 2, 3, 4), 5, 2, 7, 4)
        left = detect_magenta(same_row, hsv_ranges=[self.threshold], min_area_pixels=2)
        self.assertEqual(left.candidate_blob_count, 2)
        self.assertEqual(left.area_pixels, 4)
        self.assertEqual(left.centroid_xy, (1.5, 2.5))
        self.assertEqual(left.bounding_box_xyxy, (1, 2, 3, 4))

        different_rows = paint_block(
            paint_block(blank_image(8, 8), 1, 5, 3, 7), 5, 1, 7, 3
        )
        top = detect_magenta(
            different_rows, hsv_ranges=[self.threshold], min_area_pixels=2
        )
        self.assertEqual(top.candidate_blob_count, 2)
        self.assertEqual(top.area_pixels, 4)
        self.assertEqual(top.centroid_xy, (5.5, 1.5))
        self.assertEqual(top.bounding_box_xyxy, (5, 1, 7, 3))

    def test_wrapped_hue_range_matches_across_zero_degrees(self) -> None:
        wrapped = HsvRange(330.0, 20.0, 0.5, 1.0, 0.3, 1.0)
        for color in ([255, 0, 42], [255, 42, 0]):
            with self.subTest(color=tuple(color)):
                image = paint_block(blank_image(3, 3), 0, 0, 3, 3, color)
                result = detect_magenta(image, hsv_ranges=[wrapped])
                self.assertTrue(result.detected)
                self.assertEqual(result.area_pixels, 9)

        cyan = paint_block(blank_image(3, 3), 0, 0, 3, 3, [0, 255, 255])
        outside = detect_magenta(cyan, hsv_ranges=[wrapped])
        self.assertFalse(outside.detected)
        self.assertEqual(outside.rejection_reason, "no_threshold_match")

    def test_border_blobs_keep_exclusive_boxes_inside_the_frame(self) -> None:
        corner = detect_magenta(
            paint_block(blank_image(5, 5), 0, 0, 2, 2),
            hsv_ranges=[self.threshold],
            min_area_pixels=2,
        )
        self.assertEqual(corner.bounding_box_xyxy, (0, 0, 2, 2))
        self.assertEqual(corner.centroid_xy, (0.5, 0.5))

        edge = detect_magenta(
            paint_block(blank_image(5, 5), 3, 1, 5, 3),
            hsv_ranges=[self.threshold],
            min_area_pixels=2,
        )
        self.assertEqual(edge.bounding_box_xyxy, (3, 1, 5, 3))
        self.assertEqual(edge.bounding_box_xyxy[2], 5)
        self.assertEqual(edge.centroid_xy, (3.5, 1.5))

    def test_opening_removes_a_speck_without_shrinking_the_blob(self) -> None:
        def speckled() -> list[list[list[int]]]:
            image = paint_block(blank_image(7, 7), 1, 1, 4, 4)
            image[5][5] = list(MAGENTA)
            return image

        kept = detect_magenta(speckled(), hsv_ranges=[self.threshold])
        self.assertEqual(kept.candidate_blob_count, 2)
        self.assertEqual(kept.threshold_match_pixels, 10)
        self.assertEqual(kept.area_pixels, 9)
        self.assertEqual(kept.bounding_box_xyxy, (1, 1, 4, 4))

        opened = detect_magenta(
            speckled(),
            hsv_ranges=[self.threshold],
            open_iterations=1,
            morphology_radius_pixels=1,
        )
        self.assertEqual(opened.candidate_blob_count, 1)
        self.assertEqual(opened.threshold_match_pixels, 10)
        self.assertEqual(opened.area_pixels, 9)
        self.assertEqual(opened.bounding_box_xyxy, (1, 1, 4, 4))
        self.assertEqual(opened.centroid_xy, (2.0, 2.0))

    def test_malformed_or_uncalibrated_inputs_fail(self) -> None:
        with self.assertRaises(VisionInputError):
            detect_magenta(image_with_block(), hsv_ranges=[])
        with self.assertRaises(VisionInputError):
            detect_magenta([[[float("nan"), 0, 0]]], hsv_ranges=[self.threshold])


if __name__ == "__main__":
    unittest.main()
