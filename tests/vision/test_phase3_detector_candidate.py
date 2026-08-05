from __future__ import annotations

import copy
import hashlib
import json
import pickle
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pyarrow

from mineocclude.vision.detection_records import (
    DETECTION_RECORD_FIELDS,
    PERSON_A_PARQUET_AUTHORITY_REVISION,
    PERSON_C_DEVELOPMENT_SOURCE_REVISION,
    PYARROW_VERSION,
    DetectionRecordError,
    detection_arrow_schema,
    detection_parquet_bytes,
    read_detection_parquet_bytes,
    require_complete_frame_identities,
    validate_detection_records,
    validate_test_evaluation_request,
)

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs" / "status" / "person_e_phase3_step3_1_candidate_freeze_v0_1"
PERSON_C_UNTOUCHED_TEST_PACKAGE_REVISION = (
    "3ba6c091426a537d60c950dd1bb38f5fc02826d5"
)


def load_json(name: str) -> dict:
    value = json.loads((EVIDENCE / name).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"{name} is not a mapping")
    return value


class TestPhase3DetectorCandidate(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = load_json("detector_candidate_config.json")
        cls.version = load_json("detector_candidate_version_record.json")
        cls.reclassification = load_json("development_reclassification_receipt.json")
        cls.selection = load_json("candidate_selection_record.json")
        cls.performance = load_json("development_performance_report.json")
        cls.status = load_json("phase3_status.json")
        cls.provenance = load_json("provenance_index.json")
        cls.schema = detection_arrow_schema(
            detector_version=cls.version["detector_version"],
            detector_config_sha256=cls.version["detector_config_sha256"],
            detector_settings_sha256=cls.version["detector_settings_sha256"],
            detector_implementation_sha256=cls.version[
                "detector_implementation_sha256"
            ],
            person_c_source_revision=PERSON_C_DEVELOPMENT_SOURCE_REVISION,
        )
        cls.parquet_payload = (EVIDENCE / "development_detections.parquet").read_bytes()
        cls.rows = read_detection_parquet_bytes(cls.parquet_payload, schema=cls.schema)

    def test_exact_authorities_runtime_and_development_binding(self) -> None:
        self.assertEqual(pyarrow.__version__, PYARROW_VERSION)
        self.assertEqual(PYARROW_VERSION, "25.0.0")
        for authority, remote_ref in (
            (PERSON_A_PARQUET_AUTHORITY_REVISION, "refs/remotes/origin/role/person-a-model"),
            (PERSON_C_UNTOUCHED_TEST_PACKAGE_REVISION, "refs/remotes/origin/role/person-c-data"),
        ):
            subprocess.run(
                ["git", "-C", str(ROOT), "cat-file", "-e", f"{authority}^{{commit}}"],
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["git", "-C", str(ROOT), "merge-base", "--is-ancestor", authority, remote_ref],
                check=True,
                capture_output=True,
            )
        self.assertEqual(
            self.version["development_source_revision"],
            PERSON_C_DEVELOPMENT_SOURCE_REVISION,
        )
        self.assertEqual(
            self.reclassification["person_c_source_revision"],
            PERSON_C_DEVELOPMENT_SOURCE_REVISION,
        )

    def test_dependency_file_is_unmodified(self) -> None:
        committed = subprocess.run(
            ["git", "-C", str(ROOT), "show", "HEAD:requirements.txt"],
            check=True,
            capture_output=True,
        ).stdout
        self.assertEqual((ROOT / "requirements.txt").read_bytes(), committed)

    def test_historical_heldout_is_retired_without_rewriting_history(self) -> None:
        receipt = self.reclassification
        self.assertEqual(receipt["current_split_role"], "development")
        self.assertFalse(receipt["untouched_test_claim_permitted"])
        self.assertFalse(receipt["historical_phase2_evidence_rewritten"])
        self.assertEqual(
            receipt["original_role_counts"],
            {"calibration": 36, "heldout": 36},
        )
        self.assertEqual(
            {frame["split_role"] for frame in receipt["frames"]},
            {"development"},
        )
        self.assertEqual(
            {frame["historical_phase2_split_role"] for frame in receipt["frames"]},
            {"calibration", "heldout"},
        )

    def test_complete_detector_version_hashing(self) -> None:
        configuration = self.config["configuration"]
        self.assertEqual(
            self.config["detector_config_sha256"],
            hashlib.sha256(
                json.dumps(
                    configuration,
                    allow_nan=False,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                ).encode("utf-8")
            ).hexdigest(),
        )
        self.assertEqual(
            configuration["detector_settings_sha256"],
            self.version["detector_settings_sha256"],
        )
        implementation = (
            ROOT / configuration["detector_core_implementation_path"]
        ).read_bytes()
        self.assertEqual(
            hashlib.sha256(implementation).hexdigest(),
            self.version["detector_implementation_sha256"],
        )
        for field in (
            "detector_config_sha256",
            "detector_settings_sha256",
            "detector_implementation_sha256",
            "detector_identity_sha256",
        ):
            self.assertRegex(self.version[field], r"^[0-9a-f]{64}$")

    def test_candidate_list_and_development_result_are_explicit(self) -> None:
        self.assertEqual(
            self.selection["candidate_order"],
            [
                "historical_v0_1_min_area_20",
                "phase3_v1_min_area_19",
            ],
        )
        historical, selected = self.selection["candidates"]
        self.assertEqual(
            historical["metrics"],
            {
                "sample_count": 72,
                "positive_count": 36,
                "negative_count": 36,
                "true_positive": 35,
                "false_positive": 0,
                "true_negative": 36,
                "false_negative": 1,
                "precision": 1.0,
                "recall": 35 / 36,
            },
        )
        self.assertEqual(selected["metrics"]["true_positive"], 36)
        self.assertEqual(selected["metrics"]["false_positive"], 0)
        self.assertEqual(selected["metrics"]["false_negative"], 0)
        self.assertEqual(
            selected["settings"]["min_area_pixels"],
            19,
        )
        self.assertEqual(
            historical["false_negatives"][0]["frame_id"],
            "layout_02_visible_005",
        )
        self.assertFalse(self.selection["selected_candidate_is_formal_gate_result"])

    def test_schema_column_order_metadata_and_semantic_readback(self) -> None:
        self.assertEqual(self.schema.names, list(DETECTION_RECORD_FIELDS))
        metadata = {
            key.decode(): value.decode() for key, value in self.schema.metadata.items()
        }
        self.assertEqual(
            metadata["person_a_parquet_authority_revision"],
            PERSON_A_PARQUET_AUTHORITY_REVISION,
        )
        self.assertEqual(
            metadata["person_c_source_revision"],
            PERSON_C_DEVELOPMENT_SOURCE_REVISION,
        )
        self.assertEqual(metadata["detector_version"], self.version["detector_version"])
        self.assertEqual(metadata["row_ordering_key"], "layout_id,frame_id")
        self.assertEqual(len(self.rows), 72)
        self.assertEqual(
            [(row["layout_id"], row["frame_id"]) for row in self.rows],
            sorted((row["layout_id"], row["frame_id"]) for row in self.rows),
        )
        validate_detection_records(self.rows)

    def test_parquet_bytes_are_deterministic_without_pickle(self) -> None:
        guarded = (
            mock.patch.object(pickle, "dump", side_effect=AssertionError),
            mock.patch.object(pickle, "dumps", side_effect=AssertionError),
            mock.patch.object(pickle, "load", side_effect=AssertionError),
            mock.patch.object(pickle, "loads", side_effect=AssertionError),
        )
        for patcher in guarded:
            patcher.start()
        try:
            first = detection_parquet_bytes(self.rows, schema=self.schema)
            second = detection_parquet_bytes(
                list(reversed(self.rows)), schema=self.schema
            )
        finally:
            for patcher in reversed(guarded):
                patcher.stop()
        self.assertEqual(first, second)
        self.assertEqual(first, self.parquet_payload)
        self.assertEqual(
            hashlib.sha256(first).hexdigest(),
            load_json("parquet_writer_record.json")["parquet_sha256"],
        )

    def test_arbitrary_objects_nan_and_infinity_reject(self) -> None:
        for field, value in (
            ("frame_id", object()),
            ("threshold_match_fraction", float("nan")),
            ("threshold_match_fraction", float("inf")),
        ):
            with self.subTest(field=field, value=repr(value)):
                rows = copy.deepcopy(self.rows)
                rows[0][field] = value
                with self.assertRaises(DetectionRecordError):
                    validate_detection_records(rows)

    def test_all_non_detections_and_rejections_have_reasons(self) -> None:
        for row in self.rows:
            if row["status"] in {"not_detected", "rejected"}:
                self.assertIsInstance(row["reason"], str)
                self.assertTrue(row["reason"])

    def test_unavailable_background_strata_are_not_invented(self) -> None:
        self.assertTrue(all(row["background_stratum"] is None for row in self.rows))
        self.assertEqual(
            {row["background_stratum_status"] for row in self.rows},
            {"unavailable_owner_authored"},
        )

    def _valid_future_manifest(self) -> dict:
        source_revision = "a" * 40
        return {
            "schema_version": "1.0",
            "test_manifest_schema_version": ("person-c-detector-test-manifest-v1.0"),
            "manifest_id": "person_c_future_test_v1",
            "source_revision": source_revision,
            "source_commit_timestamp_utc": "2099-01-01T00:00:00Z",
            "created_after_candidate_freeze": True,
            "immutable": True,
            "split_role": "test",
            "candidate_version": self.version["detector_version"],
            "candidate_config_sha256": self.version["detector_config_sha256"],
            "candidate_settings_sha256": self.version["detector_settings_sha256"],
            "candidate_implementation_sha256": self.version[
                "detector_implementation_sha256"
            ],
            "test_outcomes_disclosed_before_evaluation": False,
            "frame_count": 1,
            "frames": [
                {
                    "frame_id": "future_frame_000",
                    "trajectory_id": "future_trajectory_000",
                    "model_frame_idx": 0,
                    "source_artifact_id": "future_artifact_000",
                    "source_frame_idx": 0,
                    "layout_id": "layout_01",
                    "canonical_camera_pose_id": ("layout_01_canonical_pose_v1"),
                    "resolution_id": "resolution_640x360_rgb8",
                    "image_width_px": 640,
                    "image_height_px": 360,
                    "pixel_format": "rgb8",
                    "image_coordinate_system": "pixel_center_xy_zero_based",
                    "truth_present": True,
                    "image_region": "center_middle",
                    "background_stratum": "wall",
                    "background_stratum_status": "owner_authored",
                    "source_path": "data/handoff_e/test/future_frame_000.png",
                    "source_sha256": "b" * 64,
                    "source_git_revision": source_revision,
                }
            ],
        }

    def test_test_mode_prevents_tuning_and_overwrite(self) -> None:
        manifest = self._valid_future_manifest()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "test.parquet"
            with self.assertRaisesRegex(DetectionRecordError, "Tuning"):
                validate_test_evaluation_request(
                    manifest,
                    frozen_candidate=self.version,
                    forbidden_development_hashes=self.reclassification[
                        "unique_source_sha256"
                    ],
                    output_paths=[output],
                    one_shot_test=True,
                    candidate_comparison_requested=False,
                    proposed_settings={"min_area_pixels": 18},
                )
            output.write_bytes(b"existing")
            with self.assertRaisesRegex(DetectionRecordError, "overwrite"):
                validate_test_evaluation_request(
                    manifest,
                    frozen_candidate=self.version,
                    forbidden_development_hashes=self.reclassification[
                        "unique_source_sha256"
                    ],
                    output_paths=[output],
                    one_shot_test=True,
                    candidate_comparison_requested=False,
                    proposed_settings=None,
                )

    def test_test_source_must_differ_and_postdate_freeze(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "test.parquet"
            same_source = self._valid_future_manifest()
            same_source["source_revision"] = PERSON_C_DEVELOPMENT_SOURCE_REVISION
            same_source["frames"][0]["source_git_revision"] = (
                PERSON_C_DEVELOPMENT_SOURCE_REVISION
            )
            with self.assertRaisesRegex(DetectionRecordError, "differ"):
                validate_test_evaluation_request(
                    same_source,
                    frozen_candidate=self.version,
                    forbidden_development_hashes=[],
                    output_paths=[output],
                    one_shot_test=True,
                    candidate_comparison_requested=False,
                    proposed_settings=None,
                )
            old_source = self._valid_future_manifest()
            old_source["source_commit_timestamp_utc"] = "2000-01-01T00:00:00Z"
            with self.assertRaisesRegex(DetectionRecordError, "postdate"):
                validate_test_evaluation_request(
                    old_source,
                    frozen_candidate=self.version,
                    forbidden_development_hashes=[],
                    output_paths=[output],
                    one_shot_test=True,
                    candidate_comparison_requested=False,
                    proposed_settings=None,
                )

    def test_missing_duplicate_and_extra_identities_fail_closed(self) -> None:
        with self.assertRaisesRegex(DetectionRecordError, "duplicates"):
            require_complete_frame_identities(["a", "a"], ["a"])
        with self.assertRaisesRegex(DetectionRecordError, "duplicates"):
            require_complete_frame_identities(["a"], ["a", "a"])
        with self.assertRaisesRegex(DetectionRecordError, "missing"):
            require_complete_frame_identities(["a", "b"], ["a", "c"])

    def test_phase3_cannot_pass_before_one_shot_test(self) -> None:
        self.assertEqual(
            self.status["step_3_1_status"],
            "AWAITING_NEW_UNTOUCHED_TEST",
        )
        self.assertFalse(self.status["step_3_1_pass_claimed"])
        self.assertEqual(self.status["phase_3_status"], "INCOMPLETE")
        self.assertFalse(self.performance["formal_precision_recall_gate_evaluated"])
        self.assertFalse(self.performance["formal_untouched_test_evaluation"])

    def test_phase1_and_phase2_evidence_is_byte_immutable(self) -> None:
        expected = self.provenance["historical_phase1_phase2_evidence_sha256"]
        self.assertTrue(expected)
        for relative_path, digest in expected.items():
            with self.subTest(path=relative_path):
                self.assertEqual(
                    hashlib.sha256((ROOT / relative_path).read_bytes()).hexdigest(),
                    digest,
                )


if __name__ == "__main__":
    unittest.main()
