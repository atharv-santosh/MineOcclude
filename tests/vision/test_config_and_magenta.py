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

    def test_malformed_or_uncalibrated_inputs_fail(self) -> None:
        with self.assertRaises(VisionInputError):
            detect_magenta(image_with_block(), hsv_ranges=[])
        with self.assertRaises(VisionInputError):
            detect_magenta([[[float("nan"), 0, 0]]], hsv_ranges=[self.threshold])


if __name__ == "__main__":
    unittest.main()
