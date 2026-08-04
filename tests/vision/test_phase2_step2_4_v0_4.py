from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import unittest
from collections import Counter
from pathlib import Path

from mineocclude.experiments.registry import formatted_json_bytes
from mineocclude.vision.homography import homography_from_record
from scripts.build_person_e_phase2_step2_4_v0_4 import (
    CORE_DOCUMENT_NAMES,
    DOCUMENT_NAMES,
    EXPECTED_PERSON_C_CHANGED_PATHS,
    HISTORICAL_DIRECTORIES,
    MAXIMUM_MEDIAN_WALL_ERROR_BLOCKS,
    MAXIMUM_P95_WALL_ERROR_BLOCKS,
    PERSON_C_PARENT_REVISION,
    PERSON_C_REMOTE_REF,
    PERSON_C_REVISION,
    PERSON_E_STARTING_REVISION,
    V0_4_RECEIPT,
    validate_v0_4_documents,
)

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs" / "status" / "person_e_phase2_step2_4_v0_4"


def load(name: str) -> dict[str, object]:
    return json.loads((EVIDENCE / name).read_text(encoding="utf-8"))


def load_all() -> dict[str, dict[str, object]]:
    return {name: load(name) for name in sorted(DOCUMENT_NAMES)}


class TestPhase2Step24V04(unittest.TestCase):
    def test_document_set_is_canonical_and_valid(self) -> None:
        self.assertEqual(
            {path.name for path in EVIDENCE.glob("*.json")},
            DOCUMENT_NAMES,
        )
        documents = load_all()
        validate_v0_4_documents(documents)
        for name, document in documents.items():
            with self.subTest(name=name):
                payload = (EVIDENCE / name).read_bytes()
                self.assertFalse(payload.startswith(b"\xef\xbb\xbf"))
                self.assertNotIn(b"\r\n", payload)
                self.assertEqual(payload, formatted_json_bytes(document))

    def test_exact_source_revision_parent_and_bounded_delta(self) -> None:
        source = load("source_validation.json")
        self.assertEqual(source["source_revision"], PERSON_C_REVISION)
        self.assertEqual(source["source_parent_revision"], PERSON_C_PARENT_REVISION)
        self.assertEqual(source["source_remote_ref"], PERSON_C_REMOTE_REF)
        delta = source["source_commit_delta_validation"]
        self.assertTrue(delta["scope_validation_passed"])
        self.assertEqual(
            delta["changed_paths"],
            sorted(EXPECTED_PERSON_C_CHANGED_PATHS),
        )
        self.assertTrue(delta["non_layout_03_handoff_records_unchanged"])
        self.assertTrue(delta["layout_03_probe_coordinates_unchanged"])
        self.assertTrue(delta["layout_03_split_unchanged"])

    def test_layout_03_inventory_and_top_face_centre_contract(self) -> None:
        source = load("source_validation.json")
        records = [
            record
            for record in source["source_png_records"]
            if record["layout_id"] == "layout_03"
        ]
        self.assertEqual(
            Counter(record["truth_class"] for record in records),
            {"visible": 6, "negative": 6},
        )
        marker = next(
            row
            for row in source["marker_document_records"]
            if row["layout_id"] == "layout_03"
        )
        self.assertEqual(marker["marker_count"], 4)
        self.assertEqual(
            marker["world_coordinate_system"],
            "ground_plane_world_xz_blocks_topface_centre",
        )
        self.assertEqual(
            marker["world_point_convention"],
            "block_top_face_centre",
        )
        self.assertTrue(marker["marker_convention_correction"]["eval_probe_untouched"])

    def test_layout_03_has_six_border_safe_four_marker_detections(self) -> None:
        detector = load("detector_outputs.json")
        layout = next(
            row for row in detector["marker_layouts"] if row["layout_id"] == "layout_03"
        )
        self.assertTrue(layout["all_negative_frames_detected"])
        self.assertEqual(len(layout["negative_frame_results"]), 6)
        for index, frame in enumerate(layout["negative_frame_results"]):
            with self.subTest(index=index):
                self.assertEqual(
                    frame["frame_id"],
                    f"layout_03_negative_{index:03d}",
                )
                self.assertEqual(frame["status"], "detected")
                self.assertEqual(frame["marker_count"], 4)
                self.assertEqual(len(frame["markers"]), 4)
                self.assertEqual(frame["failures"], [])
                self.assertTrue(frame["border_validation"]["passed"])
                self.assertTrue(
                    frame["border_validation"][
                        "all_four_marker_cores_strictly_inside_frame"
                    ]
                )

    def test_complete_probe_coverage_and_unchanged_split(self) -> None:
        source = load("source_validation.json")
        localization = load("localization_validation_report.json")
        self.assertEqual(
            source["probe_split"],
            {
                "authority": "person_c_predeclared_probe_document",
                "calibration_count": 18,
                "heldout_count": 18,
                "changed_after_evaluation": False,
            },
        )
        self.assertEqual(localization["required_probe_count"], 36)
        self.assertEqual(localization["evaluated_probe_count"], 36)
        self.assertEqual(localization["calibration_probe_count"], 18)
        self.assertEqual(localization["heldout_probe_count"], 18)
        self.assertTrue(localization["coverage_passed"])
        self.assertTrue(localization["all_required_probes_evaluated"])
        layout_03 = next(
            row
            for row in localization["per_layout"]
            if row["layout_id"] == "layout_03"
        )
        self.assertEqual(layout_03["required_probe_count"], 6)
        self.assertEqual(layout_03["evaluated_probe_count"], 6)
        self.assertTrue(layout_03["coverage_passed"])

    def test_formal_gate_uses_only_complete_coverage_and_global_metrics(self) -> None:
        localization = load("localization_validation_report.json")
        self.assertEqual(
            localization["required_gate"],
            {
                "maximum_median_absolute_wall_parallel_error_blocks": (
                    MAXIMUM_MEDIAN_WALL_ERROR_BLOCKS
                ),
                (
                    "maximum_p95_absolute_wall_parallel_error_blocks_exclusive"
                ): MAXIMUM_P95_WALL_ERROR_BLOCKS,
            },
        )
        self.assertLessEqual(
            localization["median_absolute_wall_parallel_error_blocks"],
            MAXIMUM_MEDIAN_WALL_ERROR_BLOCKS,
        )
        self.assertLess(
            localization["p95_absolute_wall_parallel_error_blocks"],
            MAXIMUM_P95_WALL_ERROR_BLOCKS,
        )
        layout_02 = next(
            row
            for row in localization["per_layout"]
            if row["layout_id"] == "layout_02"
        )
        self.assertFalse(layout_02["summary"]["planning_gate_passed"])
        self.assertTrue(localization["formal_planning_gate_passed"])

    def test_no_output_correction_selection_or_exclusion(self) -> None:
        localization = load("localization_validation_report.json")
        receipt = load(V0_4_RECEIPT)
        self.assertFalse(localization["output_bias_adjustment_applied"])
        self.assertIsNone(localization["output_offset_blocks"])
        self.assertEqual(localization["excluded_layout_ids"], [])
        for field in (
            "probe_targets_used_for_fitting",
            "probe_targets_used_for_detector_selection",
            "probe_targets_used_for_ground_contact_selection",
            "probe_targets_used_for_exclusion_selection",
        ):
            self.assertFalse(localization[field])
        method = receipt["method_integrity"]
        self.assertFalse(method["output_bias_adjustment_applied"])
        self.assertIsNone(method["output_offset_blocks"])
        self.assertFalse(method["probe_derived_tuning_applied"])
        self.assertFalse(method["probe_filtering_applied"])
        self.assertFalse(method["exclusions_applied"])
        self.assertFalse(method["source_split_changed_after_evaluation"])

    def test_all_six_homographies_are_marker_only_and_loadable(self) -> None:
        correspondences = load("homography_correspondences.json")
        homographies = load("homography_record.json")
        self.assertEqual(correspondences["layout_count"], 6)
        self.assertEqual(homographies["layout_count"], 6)
        self.assertFalse(correspondences["probe_targets_used_for_fitting"])
        self.assertFalse(homographies["probe_targets_used_for_fitting"])
        self.assertEqual(
            [record["layout_id"] for record in homographies["records"]],
            [f"layout_{index:02d}" for index in range(1, 7)],
        )
        for record in homographies["records"]:
            with self.subTest(layout_id=record["layout_id"]):
                homography_from_record(record)

    def test_status_is_strictly_measurement_derived(self) -> None:
        localization = load("localization_validation_report.json")
        status = load("phase2_status.json")
        steps = {step["step"]: step for step in status["steps"]}
        self.assertTrue(localization["formal_planning_gate_passed"])
        self.assertTrue(
            all(steps[step]["status"] == "PASS" for step in ("2.1", "2.2", "2.3"))
        )
        self.assertEqual(steps["2.4"]["status"], "PASS")
        self.assertIsNone(steps["2.4"]["remaining_blocker"])
        self.assertEqual(status["overall_status"], "PASS")

    def test_v0_1_v0_2_and_v0_3_are_byte_immutable(self) -> None:
        committed_paths = subprocess.run(
            [
                "git",
                "-C",
                str(ROOT),
                "ls-tree",
                "-r",
                "--name-only",
                PERSON_E_STARTING_REVISION,
                "--",
                *HISTORICAL_DIRECTORIES,
            ],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.splitlines()
        current_paths = sorted(
            path.relative_to(ROOT).as_posix()
            for directory in HISTORICAL_DIRECTORIES
            for path in (ROOT / directory).rglob("*")
            if path.is_file()
        )
        self.assertEqual(current_paths, sorted(committed_paths))
        for relative_path in committed_paths:
            with self.subTest(path=relative_path):
                committed = subprocess.run(
                    [
                        "git",
                        "-C",
                        str(ROOT),
                        "cat-file",
                        "blob",
                        f"{PERSON_E_STARTING_REVISION}:{relative_path}",
                    ],
                    check=True,
                    capture_output=True,
                ).stdout
                self.assertEqual((ROOT / relative_path).read_bytes(), committed)

    def test_deterministic_attestation_matches_all_core_bytes(self) -> None:
        determinism = load("deterministic_generation.json")
        self.assertTrue(determinism["byte_identical"])
        self.assertEqual(
            determinism["compared_document_count"],
            len(CORE_DOCUMENT_NAMES),
        )
        self.assertEqual(
            determinism["first_generation_sha256"],
            determinism["second_generation_sha256"],
        )
        for name, digest in determinism["first_generation_sha256"].items():
            with self.subTest(name=name):
                self.assertEqual(
                    hashlib.sha256((EVIDENCE / name).read_bytes()).hexdigest(),
                    digest,
                )

    def test_tampered_parent_threshold_bias_split_or_status_is_rejected(self) -> None:
        documents = load_all()
        mutations = (
            (
                "parent",
                lambda value: value["source_validation.json"].__setitem__(
                    "source_parent_revision", "0" * 40
                ),
            ),
            (
                "threshold",
                lambda value: value["localization_validation_report.json"][
                    "required_gate"
                ].__setitem__(
                    "maximum_median_absolute_wall_parallel_error_blocks",
                    0.3,
                ),
            ),
            (
                "bias",
                lambda value: value["localization_validation_report.json"].__setitem__(
                    "output_bias_adjustment_applied", True
                ),
            ),
            (
                "split",
                lambda value: value["source_validation.json"]["probe_split"].__setitem__(
                    "heldout_count", 17
                ),
            ),
            (
                "status",
                lambda value: value["phase2_status.json"].__setitem__(
                    "overall_status", "PARTIAL"
                ),
            ),
        )
        for label, mutate in mutations:
            with self.subTest(label=label):
                tampered = copy.deepcopy(documents)
                mutate(tampered)
                with self.assertRaises(ValueError):
                    validate_v0_4_documents(tampered)


if __name__ == "__main__":
    unittest.main()
