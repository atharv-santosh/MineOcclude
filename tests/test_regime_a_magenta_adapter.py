from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from mineocclude.regime_a import RegimeAError
from mineocclude.vision.magenta import HsvRange, VisionInputError, detect_magenta


def load_runner_module():
    runner_path = Path(__file__).parents[1] / "scripts/run_regime_a.py"
    module_spec = importlib.util.spec_from_file_location(
        "regime_a_magenta_adapter_test", runner_path
    )
    module = importlib.util.module_from_spec(module_spec)
    assert module_spec.loader is not None
    module_spec.loader.exec_module(module)
    return module


class RegimeAMagentaAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.runner = load_runner_module()
        cls.threshold = HsvRange(280.0, 320.0, 0.5, 1.0, 0.5, 1.0)

    def adapter_rows(self, pixels, size):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "frame.png"
            image = Image.new("RGB", size)
            image.putdata(pixels)
            image.save(path)
            return self.runner.detector_rgb_rows(path, expected_size=size)

    def test_rgba_source_restores_prior_convert_rgb_semantics(self):
        rgba = [
            (255, 0, 255, 0),
            (0, 0, 0, 255),
            (255, 0, 255, 17),
            (1, 2, 3, 99),
        ]
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "rgba.png"
            image = Image.new("RGBA", (2, 2))
            image.putdata(rgba)
            image.save(path)
            adapted = self.runner.detector_rgb_rows(path, expected_size=(2, 2))
        historical = [
            [[255, 0, 255], [0, 0, 0]],
            [[255, 0, 255], [1, 2, 3]],
        ]
        self.assertEqual(
            [[list(pixel) for pixel in row] for row in adapted], historical
        )
        self.assertEqual(
            detect_magenta(adapted, hsv_ranges=[self.threshold]).to_record(),
            detect_magenta(historical, hsv_ranges=[self.threshold]).to_record(),
        )

    def assert_historical_equivalence(self, pixels, size, **settings):
        adapted = self.adapter_rows(pixels, size)
        historical = [
            [list(pixel) for pixel in pixels[offset : offset + size[0]]]
            for offset in range(0, len(pixels), size[0])
        ]
        adapted_result = detect_magenta(
            adapted, hsv_ranges=[self.threshold], **settings
        )
        historical_result = detect_magenta(
            historical, hsv_ranges=[self.threshold], **settings
        )
        self.assertEqual(adapted_result.to_record(), historical_result.to_record())
        return adapted_result

    def test_exact_rgb_channels_integer_type_shape_and_640_by_360(self):
        width, height = 640, 360
        pixels = [(3, 5, 7)] * (width * height)
        pixels[0] = (11, 13, 17)
        pixels[-1] = (19, 23, 29)
        rows = self.adapter_rows(pixels, (width, height))
        self.assertEqual((len(rows[0]), len(rows)), (width, height))
        self.assertEqual(rows[0][0], (11, 13, 17))
        self.assertEqual(rows[-1][-1], (19, 23, 29))
        self.assertTrue(all(type(channel) is int for channel in rows[0][0]))

    def test_no_magenta_and_mixed_background_exact_outputs(self):
        absent = self.assert_historical_equivalence(
            [(0, 0, 0), (12, 34, 56), (0, 255, 0), (255, 255, 255)],
            (2, 2),
        )
        self.assertEqual(
            absent.to_record(),
            {
                "status": "not_detected",
                "centroid_xy": None,
                "area_pixels": None,
                "bounding_box_xyxy": None,
                "threshold_match_pixels": 0,
                "candidate_blob_count": 0,
                "rejection_reason": "no_threshold_match",
            },
        )

    def test_valid_blob_tiny_invalid_and_boundary_pixels_exact_outputs(self):
        black = (0, 0, 0)
        magenta = (255, 0, 255)
        blob = [black] * 25
        for index in (11, 12, 16, 17):
            blob[index] = magenta
        detected = self.assert_historical_equivalence(blob, (5, 5), min_area_pixels=2)
        self.assertEqual(detected.status, "detected")
        self.assertEqual(detected.area_pixels, 4)
        self.assertEqual(detected.centroid_xy, (1.5, 2.5))
        self.assertEqual(detected.bounding_box_xyxy, (1, 2, 3, 4))

        tiny = [black] * 9
        tiny[4] = magenta
        rejected = self.assert_historical_equivalence(tiny, (3, 3), min_area_pixels=2)
        self.assertEqual(rejected.status, "not_detected")
        self.assertEqual(rejected.area_pixels, None)
        self.assertEqual(rejected.threshold_match_pixels, 1)
        self.assertEqual(rejected.candidate_blob_count, 1)
        self.assertEqual(rejected.rejection_reason, "no_valid_blob")

        boundary = [black] * 16
        for index in (2, 3, 6, 7):
            boundary[index] = magenta
        edge = self.assert_historical_equivalence(boundary, (4, 4), min_area_pixels=2)
        self.assertEqual(edge.bounding_box_xyxy, (2, 0, 4, 2))
        self.assertEqual(edge.centroid_xy, (2.5, 0.5))

    def test_malformed_mode_size_dtype_and_shape_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            gray = Path(temporary) / "gray.png"
            Image.new("L", (2, 2), 0).save(gray)
            with self.assertRaisesRegex(RegimeAError, "must be RGB or RGBA"):
                self.runner.detector_rgb_rows(gray, expected_size=(2, 2))
            rgb = Path(temporary) / "rgb.png"
            Image.new("RGB", (2, 2), (0, 0, 0)).save(rgb)
            with self.assertRaisesRegex(RegimeAError, "not 3x2"):
                self.runner.detector_rgb_rows(rgb, expected_size=(3, 2))
        malformed = (
            [[[True, 0, 0]]],
            [[[0, 0]]],
            [[[256, 0, 0]]],
            [[[0, 0, 0]], [[0, 0, 0], [0, 0, 0]]],
        )
        for image in malformed:
            with self.subTest(image=image), self.assertRaises(VisionInputError):
                detect_magenta(image, hsv_ranges=[self.threshold])


if __name__ == "__main__":
    unittest.main()
