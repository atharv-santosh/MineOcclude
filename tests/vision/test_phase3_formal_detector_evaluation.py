from __future__ import annotations

import hashlib
import importlib.util
import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path

import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = (
    ROOT / "docs/status/person_e_phase3_step3_1_formal_evaluation_v0_1"
)
RUNNER = ROOT / "scripts/run_person_e_phase3_formal_detector_evaluation.py"
PACKAGE_ID = "person-c-phase3-detector-v1-untouched-test-v0_3"
PACKAGE_COMMIT = "3ba6c091426a537d60c950dd1bb38f5fc02826d5"
FREEZE_COMMIT = "3930669eddc026ecb081e947f71f1855a7415904"
ACTUAL_DETECTOR_VERSION = (
    "hsv-largest-valid-blob-v1.0-candidate:sha256:"
    "0cadf618fca1578196bde4982021c38627ccb9c39e46353812e7da3fce6aa125"
)
RUN_ID = "person-e-phase3-step3-1-v0_3-formal-ordinal-1"
RUNNER_SHA256 = (
    "99cb46dcb67a8416f1f9d8e7fe7f35eac71a672294788a2f50052deacc383c44"
)


def load_json(name: str) -> dict:
    return json.loads((EVIDENCE / name).read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class TestPhase3FormalDetectorEvaluation(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = load_json("formal_evaluation_report.json")
        cls.receipt = load_json("formal_run_receipt.json")
        cls.started = load_json("formal_run_started.json")
        cls.complete = load_json("inference_complete.json")
        cls.records_document = load_json("formal_detection_records.json")
        cls.records = cls.records_document["records"]
        cls.package = load_json("package_binding.json")
        cls.runtime = load_json("runtime_environment.json")
        cls.status = load_json("phase3_status.json")
        cls.provenance = load_json("provenance_index.json")
        cls.journal = [
            json.loads(line)
            for line in (EVIDENCE / "inference_outcomes.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
            if line
        ]

    def test_exact_authorities_candidate_and_orchestration_source(self) -> None:
        self.assertEqual(self.report["package_id"], PACKAGE_ID)
        self.assertEqual(self.report["package_commit"], PACKAGE_COMMIT)
        self.assertEqual(self.report["detector_version"], ACTUAL_DETECTOR_VERSION)
        self.assertEqual(self.receipt["run_id"], RUN_ID)
        self.assertEqual(self.runtime["source_commit"], FREEZE_COMMIT)
        self.assertEqual(self.runtime["test_package_commit"], PACKAGE_COMMIT)
        self.assertEqual(sha256_file(RUNNER), RUNNER_SHA256)
        self.assertEqual(
            self.runtime["orchestration_script_sha256"],
            RUNNER_SHA256,
        )

    def test_formal_run_is_exactly_one_and_cannot_be_recharacterized(self) -> None:
        self.assertEqual(self.receipt["formal_run_ordinal"], 1)
        self.assertEqual(self.receipt["formal_run_count"], 1)
        self.assertTrue(self.receipt["formal_run_consumed"])
        self.assertFalse(self.receipt["second_formal_run_occurred"])
        self.assertFalse(self.receipt["detector_tuned_after_result"])
        self.assertFalse(self.receipt["u4_output_inspected"])
        self.assertEqual(
            self.started["exact_command"],
            self.receipt["exact_command"],
        )
        self.assertEqual(
            self.started["evaluation_start_utc"],
            self.receipt["evaluation_start_utc"],
        )
        self.assertEqual(
            self.complete["evaluation_end_utc"],
            self.receipt["evaluation_end_utc"],
        )

    def test_truth_free_inference_journal_is_complete_and_durable(self) -> None:
        self.assertEqual(len(self.journal), 48)
        self.assertEqual(
            [row["outcome_ordinal"] for row in self.journal],
            list(range(1, 49)),
        )
        self.assertEqual(len({row["frame_id"] for row in self.journal}), 48)
        forbidden = {
            "truth_class",
            "truth_present",
            "classification",
            "target_magenta_sheep_present",
        }
        self.assertTrue(all(forbidden.isdisjoint(row) for row in self.journal))
        self.assertEqual(self.complete["outcome_count"], 48)
        self.assertFalse(
            self.complete["truth_artifacts_opened_during_inference"]
        )
        self.assertEqual(
            self.complete["inference_journal_sha256"],
            sha256_file(EVIDENCE / "inference_outcomes.jsonl"),
        )
        self.assertTrue(
            self.package[
                "truth_artifacts_opened_only_after_inference_complete"
            ]
        )

    def test_all_required_per_frame_records_are_complete(self) -> None:
        required = {
            "package_id",
            "package_commit",
            "frame_id",
            "layout_id",
            "truth_class",
            "truth_present",
            "source_relative_png_path",
            "png_sha256",
            "detector_version",
            "detector_identity_sha256",
            "detector_config_sha256",
            "detector_settings_sha256",
            "detector_implementation_sha256",
            "detected_present",
            "accepted",
            "rejected",
            "centroid_x",
            "centroid_y",
            "selected_bounding_box_xyxy",
            "selected_blob_area_pixels",
            "rejection_reason",
            "classification",
            "run_id",
            "formal_run_ordinal",
            "evaluation_start_utc",
            "evaluation_end_utc",
            "runtime_python_version",
            "runtime_numpy_version",
            "runtime_pandas_version",
            "runtime_pyarrow_version",
            "runtime_opencv_version",
            "source_commit",
            "test_package_commit",
        }
        self.assertEqual(len(self.records), 48)
        self.assertEqual(len({row["frame_id"] for row in self.records}), 48)
        for row in self.records:
            with self.subTest(frame_id=row["frame_id"]):
                self.assertTrue(required <= set(row))
                self.assertEqual(row["package_id"], PACKAGE_ID)
                self.assertEqual(row["package_commit"], PACKAGE_COMMIT)
                self.assertEqual(row["run_id"], RUN_ID)
                self.assertEqual(row["formal_run_ordinal"], 1)
                self.assertFalse(row["truth_exposed_to_detector"])
                self.assertEqual(row["source_commit"], FREEZE_COMMIT)
                self.assertEqual(row["test_package_commit"], PACKAGE_COMMIT)

    def test_formal_confusion_metrics_and_exact_fractions(self) -> None:
        metrics = self.report["metrics"]
        self.assertEqual(metrics["total_frames"], 48)
        self.assertEqual(metrics["true_positive"], 24)
        self.assertEqual(metrics["false_positive"], 0)
        self.assertEqual(metrics["true_negative"], 24)
        self.assertEqual(metrics["false_negative"], 0)
        self.assertEqual(
            metrics["precision"],
            {
                "decimal": 1.0,
                "denominator": 24,
                "fraction": "1/1",
                "numerator": 24,
            },
        )
        self.assertEqual(
            metrics["recall"],
            {
                "decimal": 1.0,
                "denominator": 24,
                "fraction": "1/1",
                "numerator": 24,
            },
        )
        self.assertTrue(self.report["all_records_valid"])
        self.assertTrue(self.report["formal_gate_passed"])

    def test_each_layout_has_four_tp_and_four_tn(self) -> None:
        self.assertEqual(len(self.report["per_layout"]), 6)
        for index, row in enumerate(self.report["per_layout"], start=1):
            self.assertEqual(row["layout_id"], f"layout_{index:02d}")
            self.assertEqual(row["total_frames"], 8)
            self.assertEqual(row["true_positive"], 4)
            self.assertEqual(row["false_positive"], 0)
            self.assertEqual(row["true_negative"], 4)
            self.assertEqual(row["false_negative"], 0)

    def test_acceptance_rejections_and_nulls_are_explicit(self) -> None:
        self.assertEqual(self.report["accepted_frame_count"], 24)
        self.assertEqual(self.report["rejected_frame_count"], 24)
        self.assertEqual(
            self.report["rejection_reason_counts"],
            {"no_threshold_match": 24},
        )
        self.assertEqual(
            Counter(row["classification"] for row in self.records),
            {"TP": 24, "TN": 24},
        )
        for row in self.records:
            if row["rejected"]:
                self.assertFalse(row["accepted"])
                self.assertIsNone(row["centroid_x"])
                self.assertIsNone(row["centroid_y"])
                self.assertIsNone(row["selected_bounding_box_xyxy"])
                self.assertIsNone(row["selected_blob_area_pixels"])
                self.assertEqual(row["rejection_reason"], "no_threshold_match")
            else:
                self.assertTrue(row["accepted"])
                self.assertIsNotNone(row["centroid_x"])
                self.assertIsNotNone(row["centroid_y"])
                self.assertIsNotNone(row["selected_bounding_box_xyxy"])
                self.assertIsNotNone(row["selected_blob_area_pixels"])
                self.assertIsNone(row["rejection_reason"])

    def test_coverage_has_no_missing_duplicate_or_extra_records(self) -> None:
        self.assertEqual(self.report["missing_record_count"], 0)
        self.assertEqual(self.report["duplicate_record_count"], 0)
        self.assertEqual(self.report["extra_record_count"], 0)
        self.assertEqual(self.records_document["record_count"], 48)
        self.assertEqual(self.receipt["inference_outcome_count"], 48)
        self.assertEqual(self.receipt["result_record_count"], 48)

    def test_parquet_semantic_readback_matches_json(self) -> None:
        table = pq.read_table(EVIDENCE / "formal_detection_records.parquet")
        self.assertEqual(table.num_rows, 48)
        self.assertEqual(
            table.schema.metadata[b"formal_run_ordinal"],
            b"1",
        )
        parquet_by_id = {row["frame_id"]: row for row in table.to_pylist()}
        self.assertEqual(set(parquet_by_id), {row["frame_id"] for row in self.records})
        for record in self.records:
            row = parquet_by_id[record["frame_id"]]
            box = record["selected_bounding_box_xyxy"]
            self.assertEqual(row["classification"], record["classification"])
            self.assertEqual(row["truth_present"], record["truth_present"])
            self.assertEqual(
                row["detected_present"],
                record["detected_present"],
            )
            self.assertEqual(
                [
                    row["bbox_x_min"],
                    row["bbox_y_min"],
                    row["bbox_x_max_exclusive"],
                    row["bbox_y_max_exclusive"],
                ]
                if box is not None
                else None,
                box,
            )

    def test_package_binding_and_runtime_are_exact(self) -> None:
        self.assertEqual(self.package["package_id"], PACKAGE_ID)
        self.assertEqual(self.package["package_commit"], PACKAGE_COMMIT)
        self.assertEqual(
            self.package["png_inventory_sha256"],
            "54fdfd69673404773395e11f7b60bad8f048b005e97d8c624672417a803c5700",
        )
        self.assertEqual(self.package["frame_count"], 48)
        self.assertEqual(
            self.runtime["runtime"],
            {
                "numpy": "1.26.4",
                "opencv": "4.11.0.86",
                "pandas": "2.3.3",
                "pyarrow": "25.0.0",
                "python": "3.10.20",
            },
        )

    def test_provenance_hashes_every_non_self_artifact(self) -> None:
        actual_files = {
            path.name for path in EVIDENCE.iterdir() if path.is_file()
        }
        records = self.provenance["records"]
        self.assertTrue(self.provenance["self_reference_excluded"])
        self.assertEqual(
            {record["path"] for record in records},
            actual_files - {"provenance_index.json"},
        )
        for record in records:
            path = EVIDENCE / record["path"]
            self.assertEqual(record["sha256"], sha256_file(path))
            self.assertEqual(record["size_bytes"], path.stat().st_size)

    def test_status_is_derived_from_the_formal_gate_only(self) -> None:
        self.assertEqual(self.status["step_3_1_status"], "PASS")
        self.assertTrue(self.status["step_3_1_pass_claimed"])
        self.assertEqual(self.status["step_3_1_formal_run_ordinal"], 1)
        self.assertEqual(self.status["phase_3_status"], "INCOMPLETE")
        self.assertFalse(self.status["development_metrics_are_formal_gate_result"])

    def test_exclusive_writer_prevents_result_overwrite(self) -> None:
        specification = importlib.util.spec_from_file_location(
            "formal_detector_runner",
            RUNNER,
        )
        self.assertIsNotNone(specification)
        self.assertIsNotNone(specification.loader)
        module = importlib.util.module_from_spec(specification)
        specification.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "immutable.bin"
            module._write_bytes_exclusive(output, b"first")
            with self.assertRaises(FileExistsError):
                module._write_bytes_exclusive(output, b"second")
            self.assertEqual(output.read_bytes(), b"first")


if __name__ == "__main__":
    unittest.main()
