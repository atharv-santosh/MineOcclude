from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from mineocclude.experiments.figure_inputs import (
    FIGURE_FAMILIES,
    FigureInputError,
    build_figure_input,
    validate_figure_input,
)


ROOT = Path(__file__).resolve().parents[2]
BUILD_SCRIPT = ROOT / "scripts" / "build_figure_input.py"


def figure_row(**changes: object) -> dict[str, object]:
    row: dict[str, object] = {
        "series_id": "ridge",
        "source_result_id": "metric_layer_3",
        "source_artifact_id": "artifact_metrics_v1",
        "source_artifact_hash": "b" * 64,
        "source_run_id": "analysis_run_1",
        "source_lifecycle": "accepted",
        "source_superseded_by": None,
        "accepted_manifest_hash": "c" * 64,
        "fold_manifest_hash": "d" * 64,
        "x": 3,
        "y": 0.42,
        "x_unit": "layer_index",
        "y_unit": "r_squared",
        "sample_count": 120,
        "uncertainty_type": "layout_trajectory_bootstrap_95ci",
        "lower": 0.20,
        "upper": 0.60,
        "status": "valid",
        "diagnostic": None,
    }
    row.update(changes)
    return row


def build_document(*rows: dict[str, object]) -> dict[str, object]:
    return build_figure_input(
        list(rows) if rows else [figure_row()],
        figure_id="figure_layer_curve_v1",
        figure_family="layer_curve",
        code_sha="a" * 40,
        result_scope="known_answer",
    )


class TestFigureInputs(unittest.TestCase):
    def test_family_set_is_immutable_and_complete_for_phase_one(self) -> None:
        self.assertIsInstance(FIGURE_FAMILIES, frozenset)
        self.assertTrue(
            {
                "baseline_comparison",
                "growth_dynamics",
                "geometry_localization",
            }.issubset(FIGURE_FAMILIES)
        )

    def test_values_and_row_level_provenance_are_sealed(self) -> None:
        second = figure_row(
            series_id="mlp",
            source_result_id="metric_layer_4",
            source_artifact_id="artifact_metrics_v2",
            source_artifact_hash="e" * 64,
            source_run_id="analysis_run_2",
            fold_manifest_hash=None,
            x=4,
            y=0.5,
            lower=0.3,
            upper=0.7,
        )
        document = build_document(figure_row(), second)
        validate_figure_input(document)
        self.assertEqual(document["source_run_ids"], ["analysis_run_1", "analysis_run_2"])
        self.assertEqual(
            document["source_artifact_ids"],
            ["artifact_metrics_v1", "artifact_metrics_v2"],
        )
        self.assertEqual(document["fold_manifest_hashes"], ["d" * 64])
        self.assertEqual(document["rows"][0]["sample_count"], 120)

        tampered = copy.deepcopy(document)
        tampered["rows"][0]["y"] = 0.99
        with self.assertRaises(FigureInputError):
            validate_figure_input(tampered)

        forged_top_level = copy.deepcopy(document)
        forged_top_level["source_run_ids"] = ["unrelated_run"]
        with self.assertRaises(FigureInputError):
            validate_figure_input(forged_top_level)

    def test_valid_rows_require_positive_n_known_uncertainty_and_live_source(self) -> None:
        cases = (
            figure_row(sample_count=0),
            figure_row(uncertainty_type="mystery_interval"),
            figure_row(
                source_lifecycle="superseded",
                source_superseded_by="artifact_metrics_v2",
            ),
            figure_row(source_lifecycle="excluded"),
        )
        for row in cases:
            with self.subTest(row=row):
                with self.assertRaises(FigureInputError):
                    build_document(row)

    def test_invalid_rows_preserve_diagnostic_without_numeric_output(self) -> None:
        document = build_document(
            figure_row(
                y=None,
                sample_count=0,
                uncertainty_type="none",
                lower=None,
                upper=None,
                status="invalid",
                diagnostic="source run was excluded",
                source_lifecycle="excluded",
            )
        )
        validate_figure_input(document)
        invalid = copy.deepcopy(document["rows"][0])
        invalid["y"] = 0.5
        with self.assertRaises(FigureInputError):
            build_document(invalid)

    def test_cli_derives_source_hash_from_literal_input_bytes(self) -> None:
        source_row = figure_row()
        source_row.pop("source_artifact_hash")
        source = {"rows": [source_row]}
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary = Path(temporary_directory)
            input_path = temporary / "locked_metrics.json"
            output_path = temporary / "figure_input.json"
            input_path.write_text(
                json.dumps(source, sort_keys=True),
                encoding="utf-8",
            )
            completed = subprocess.run(
                [
                    sys.executable,
                    str(BUILD_SCRIPT),
                    str(input_path),
                    str(output_path),
                    "--figure-id",
                    "figure_layer_curve_v1",
                    "--figure-family",
                    "layer_curve",
                    "--code-sha",
                    "a" * 40,
                    "--result-scope",
                    "known_answer",
                ],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            output = json.loads(output_path.read_text(encoding="utf-8"))
            source_hash = hashlib.sha256(input_path.read_bytes()).hexdigest()
            self.assertEqual(output["source_artifact_hashes"], [source_hash])
            self.assertEqual(output["rows"][0]["source_artifact_hash"], source_hash)
            validate_figure_input(output)

    def test_cli_rejects_embedded_or_manual_source_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary = Path(temporary_directory)
            input_path = temporary / "metrics.json"
            output_path = temporary / "figure_input.json"
            input_path.write_text(
                json.dumps({"rows": [figure_row()]}),
                encoding="utf-8",
            )
            completed = subprocess.run(
                [
                    sys.executable,
                    str(BUILD_SCRIPT),
                    str(input_path),
                    str(output_path),
                    "--figure-id",
                    "figure_layer_curve_v1",
                    "--figure-family",
                    "layer_curve",
                    "--code-sha",
                    "a" * 40,
                    "--result-scope",
                    "known_answer",
                ],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(completed.returncode, 0)
            self.assertFalse(output_path.exists())


if __name__ == "__main__":
    unittest.main()
