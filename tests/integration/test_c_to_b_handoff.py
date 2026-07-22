"""Authoritative C capture to B state/oracle compatibility evidence."""

from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from mineocclude.analysis.coordinates import (
    COORDINATE_FRAME_SCHEMA_VERSION,
    CaptureStateHandoffCode,
    CaptureStateHandoffError,
    build_state_input_from_capture_package,
    coordinate_frame_hash,
)
from mineocclude.contracts.analysis_inputs import validate_state_input
from mineocclude.oracle.targets import build_regime_a_target_document


ROOT = Path(__file__).resolve().parents[2]
PACKAGE_PATH = ROOT / "tests" / "fixtures" / "person_c" / "episode" / "accepted_episode.json"


def capture_package() -> dict:
    return json.loads(PACKAGE_PATH.read_text(encoding="utf-8"))


def coordinate_frame(package: dict | None = None) -> dict:
    package = package or capture_package()
    document = {
        "coordinate_frame_schema_version": COORDINATE_FRAME_SCHEMA_VERSION,
        "coordinate_frame_id": "synthetic_person_c_x_axis_v1",
        "wall_parallel_origin_world_xyz": [0.0, 0.0, 0.0],
        "wall_parallel_positive_unit_vector_world_xyz": [1.0, 0.0, 0.0],
        "source_layout_manifest_hash": package["episode_manifest"]["layout_config_hash"],
        "adapter_signoff": {"person_b": True, "person_c": True},
    }
    document["coordinate_frame_hash"] = coordinate_frame_hash(document)
    return document


def build(package: dict | None = None, frame: dict | None = None) -> dict:
    package = package or capture_package()
    return build_state_input_from_capture_package(
        package,
        coordinate_frame=frame or coordinate_frame(package),
        model_hash="1" * 64,
        preprocess_hash="2" * 64,
    )


class TestCToBHandoff(unittest.TestCase):
    def test_accepted_capture_builds_valid_state_and_oracle_documents(self) -> None:
        state = build()
        validation = validate_state_input(state)
        self.assertTrue(validation.accepted, validation.rejections)
        targets = build_regime_a_target_document(
            state,
            oracle_run_id="synthetic_c_to_b_oracle_run_v1",
            oracle_code_sha="3" * 40,
        )
        self.assertEqual(len(targets["rows"]), len(state["rows"]))
        self.assertTrue(all(row["synthetic"] is True for row in targets["rows"]))
        self.assertTrue(
            all(row["scientific_use"] == "forbidden" for row in targets["rows"])
        )

    def test_visibility_tau_and_observation_semantics_are_exact(self) -> None:
        rows = build()["rows"]
        self.assertEqual([row["tau"] for row in rows], [0.0, 0.05, 0.1, 0.15])
        self.assertIsNotNone(rows[0]["observed_position_blocks"])
        self.assertTrue(
            all(row["observed_position_blocks"] is None for row in rows[1:])
        )

    def test_source_row_order_is_irrelevant_and_inputs_are_not_mutated(self) -> None:
        package = capture_package()
        frame = coordinate_frame(package)
        original_package = copy.deepcopy(package)
        original_frame = copy.deepcopy(frame)
        expected = build(package, frame)
        for stream in ("frame_map", "server_state", "visibility"):
            package["streams"][stream].reverse()
        actual = build(package, frame)
        self.assertEqual(actual, expected)
        self.assertEqual(frame, original_frame)
        package["streams"]["frame_map"].reverse()
        package["streams"]["server_state"].reverse()
        package["streams"]["visibility"].reverse()
        self.assertEqual(package, original_package)

    def test_missing_duplicate_or_conflicting_identity_fails_closed(self) -> None:
        mutations = []
        missing = capture_package()
        missing["streams"]["visibility"].pop()
        mutations.append(missing)
        duplicate = capture_package()
        duplicate["streams"]["server_state"].append(
            copy.deepcopy(duplicate["streams"]["server_state"][0])
        )
        mutations.append(duplicate)
        conflicting = capture_package()
        conflicting["streams"]["visibility"][0]["trajectory_id"] = "wrong"
        mutations.append(conflicting)
        for package in mutations:
            with self.subTest():
                with self.assertRaises(CaptureStateHandoffError):
                    build(package)

    def test_layout_projection_and_a_provenance_mismatches_fail(self) -> None:
        package = capture_package()
        wrong_frame = coordinate_frame(package)
        wrong_frame["source_layout_manifest_hash"] = "9" * 64
        wrong_frame["coordinate_frame_hash"] = coordinate_frame_hash(wrong_frame)
        with self.assertRaises(CaptureStateHandoffError) as caught:
            build(package, wrong_frame)
        self.assertEqual(caught.exception.code, CaptureStateHandoffCode.LAYOUT_BINDING_MISMATCH)

        projected = capture_package()
        projected["streams"]["server_state"][0]["state"]["wall_parallel_position_blocks"] += 1
        with self.assertRaises(CaptureStateHandoffError) as caught:
            build(projected)
        self.assertEqual(
            caught.exception.code,
            CaptureStateHandoffCode.COORDINATE_PROJECTION_MISMATCH,
        )

        with self.assertRaises(CaptureStateHandoffError) as caught:
            build_state_input_from_capture_package(
                package,
                coordinate_frame=coordinate_frame(package),
                model_hash="missing",
                preprocess_hash="2" * 64,
            )
        self.assertEqual(caught.exception.code, CaptureStateHandoffCode.MISSING_A_PROVENANCE)

    def test_no_object_control_is_explicitly_not_oracle_eligible(self) -> None:
        package = capture_package()
        package["condition"] = "occluder_only_no_sheep"
        package["episode_manifest"]["condition"] = "occluder_only_no_sheep"
        for row in package["streams"]["server_state"]:
            row["state"]["target_present"] = False
        with self.assertRaises(CaptureStateHandoffError) as caught:
            build(package)
        self.assertEqual(
            caught.exception.code,
            CaptureStateHandoffCode.NO_OBJECT_NOT_ORACLE_ELIGIBLE,
        )


if __name__ == "__main__":
    unittest.main()
