from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from mineocclude.experiments.figure_inputs import build_figure_input

from tests.experiments.test_figure_inputs import figure_row


ROOT = Path(__file__).resolve().parents[2]
RENDER_SCRIPT = ROOT / "scripts" / "render_figure_svg.py"


class TestFigureRenderer(unittest.TestCase):
    def test_renderer_exposes_units_counts_uncertainty_and_run_ids(self) -> None:
        document = build_figure_input(
            [figure_row()],
            figure_id="figure_layer_curve_v1",
            figure_family="layer_curve",
            code_sha="a" * 40,
            result_scope="known_answer",
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary = Path(temporary_directory)
            input_path = temporary / "figure_input.json"
            output_path = temporary / "figure.svg"
            manifest_path = temporary / "figure_manifest.json"
            caption_path = temporary / "caption.txt"
            input_path.write_text(json.dumps(document), encoding="utf-8")
            caption_path.write_text("Layer probe performance.", encoding="utf-8")
            completed = subprocess.run(
                [
                    sys.executable,
                    str(RENDER_SCRIPT),
                    str(input_path),
                    str(output_path),
                    str(manifest_path),
                    "--caption-file",
                    str(caption_path),
                ],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            svg = output_path.read_text(encoding="utf-8")
            ET.fromstring(svg)
            self.assertIn("<svg", svg)
            self.assertIn("layer_index", svg)
            self.assertIn("r_squared", svg)
            self.assertIn("n=120", svg)
            self.assertIn("layout_trajectory_bootstrap_95ci", svg)
            self.assertIn("run=analysis_run_1", svg)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["caption"], "Layer probe performance.")
            self.assertEqual(manifest["source_run_ids"], ["analysis_run_1"])

            second = subprocess.run(
                [
                    sys.executable,
                    str(RENDER_SCRIPT),
                    str(input_path),
                    str(output_path),
                    str(manifest_path),
                    "--caption-file",
                    str(caption_path),
                ],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(second.returncode, 0)
            self.assertEqual(output_path.read_text(encoding="utf-8"), svg)

    def test_renderer_rejects_tampered_input_before_writing(self) -> None:
        document = build_figure_input(
            [figure_row()],
            figure_id="figure_layer_curve_v1",
            figure_family="layer_curve",
            code_sha="a" * 40,
            result_scope="known_answer",
        )
        document["rows"][0]["sample_count"] = 0
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary = Path(temporary_directory)
            input_path = temporary / "tampered.json"
            output_path = temporary / "figure.svg"
            manifest_path = temporary / "figure_manifest.json"
            caption_path = temporary / "caption.txt"
            input_path.write_text(json.dumps(document), encoding="utf-8")
            caption_path.write_text("Tampered figure.", encoding="utf-8")
            completed = subprocess.run(
                [
                    sys.executable,
                    str(RENDER_SCRIPT),
                    str(input_path),
                    str(output_path),
                    str(manifest_path),
                    "--caption-file",
                    str(caption_path),
                ],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(completed.returncode, 0)
            self.assertFalse(output_path.exists())

    def test_renderer_help_surface(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(RENDER_SCRIPT), "--help"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("usage:", completed.stdout.lower())


if __name__ == "__main__":
    unittest.main()
