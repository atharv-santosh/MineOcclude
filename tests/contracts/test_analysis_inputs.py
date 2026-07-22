from __future__ import annotations

import copy
import unittest

from mineocclude.analysis.coordinates import coordinate_frame_hash
from mineocclude.analysis.config import hash_core_analysis_config
from mineocclude.contracts.analysis_inputs import (
    validate_baseline_input,
    validate_measurement_input,
    validate_state_input,
)
from mineocclude.oracle.schema import validate_oracle_target_document
from mineocclude.oracle.targets import build_regime_a_target_document


HASHES = {
    "config": "1" * 64,
    "model": "2" * 64,
    "preprocess": "3" * 64,
    "manifest": "4" * 64,
}


def coordinate_frame() -> dict[str, object]:
    value: dict[str, object] = {
        "coordinate_frame_schema_version": "person-b-wall-parallel-frame-v0.1",
        "coordinate_frame_id": "layout_frame_v1",
        "wall_parallel_origin_world_xyz": [0.0, 0.0, 0.0],
        "wall_parallel_positive_unit_vector_world_xyz": [1.0, 0.0, 0.0],
        "source_layout_manifest_hash": "5" * 64,
        "adapter_signoff": {"person_b": True, "person_c": True},
    }
    value["coordinate_frame_hash"] = coordinate_frame_hash(value)
    return value


class TestAnalysisInputs(unittest.TestCase):
    def test_state_intake_binds_coordinate_and_manifest(self) -> None:
        row = {
            "episode_id": "episode_1",
            "trajectory_id": "trajectory_1",
            "server_tick": 10,
            "render_frame_idx": 0,
            "action_idx": 0,
            "model_frame_idx": 0,
            "layout_id": "layout_1",
            "regime": "regime_a",
            "visibility": "visible",
            "tau": 0.0,
            "v": 1.0,
            "q": 0.1,
            "duration": 1.0,
            "code_sha": "a" * 40,
            "config_hash": HASHES["config"],
            "model_hash": HASHES["model"],
            "preprocess_hash": HASHES["preprocess"],
            "seed": 7,
            "schema_version": "1.0",
            "run_id": "capture_run_v1",
            "status": "accepted",
            "exclusion_reason": None,
            "superseded_by": None,
            "accepted_manifest_hash": HASHES["manifest"],
            "x_true_blocks": 2.0,
            "observed_position_blocks": 2.0,
        }
        document = {
            "schema_version": "1.0",
            "state_input_schema_version": "person-b-state-input-v0.1",
            "producer_role": "person_c",
            "join_key": ["trajectory_id", "model_frame_idx"],
            "accepted_manifest_hash": HASHES["manifest"],
            "coordinate_frame": coordinate_frame(),
            "rows": [row],
        }
        self.assertTrue(validate_state_input(document).accepted)
        targets = build_regime_a_target_document(
            document,
            oracle_run_id="person_b_oracle_run_v1",
            oracle_code_sha="b" * 40,
        )
        self.assertEqual(targets["rows"][0]["config_hash"], hash_core_analysis_config())
        validate_oracle_target_document(targets)

    def test_baseline_intake_requires_exact_oof_folds(self) -> None:
        document = {
            "schema_version": "1.0",
            "baseline_input_schema_version": "person-b-baseline-input-v0.1",
            "producer_role": "person_d",
            "baseline_id": "last_seen_v1",
            "baseline_family": "last_seen",
            "target_name": "mu_oracle_blocks",
            "config_hash": "1" * 64,
            "input_manifest_hash": "2" * 64,
            "fold_manifest_hash": "3" * 64,
            "fit_manifest_hash": "4" * 64,
            "rows": [
                {
                    "trajectory_id": "trajectory_1",
                    "model_frame_idx": 0,
                    "fold_idx": 2,
                    "prediction": 1.5,
                    "prediction_scope": "out_of_fold",
                    "fit_id": "last_seen_fold_2",
                }
            ],
        }
        expected = {("trajectory_1", 0): 2}
        self.assertTrue(
            validate_baseline_input(
                document, expected_fold_by_frame=expected
            ).accepted
        )
        document["rows"][0]["prediction_scope"] = "in_sample"
        self.assertFalse(
            validate_baseline_input(
                document, expected_fold_by_frame=expected
            ).accepted
        )

    def test_measurement_intake_never_encodes_failures_as_zero(self) -> None:
        document = {
            "schema_version": "1.0",
            "measurement_input_schema_version": "person-b-u4-measurement-input-v0.1",
            "producer_role": "person_e",
            "accepted_rollout_manifest_hash": "1" * 64,
            "measurement_config_hash": "2" * 64,
            "rows": [
                {
                    "measurement_id": "measurement_1",
                    "rollout_id": "rollout_1",
                    "event_id": "event_1",
                    "direction_version": "direction_v1",
                    "control_type": "intervention",
                    "alpha_applied": 1.0,
                    "measurement_status": "generation_failure",
                    "displacement_blocks": None,
                    "persistence_score": None,
                    "ssim": None,
                    "outcome_detail": "Generation did not produce a valid clip.",
                    "measurement_artifact_hash": "3" * 64,
                }
            ],
        }
        self.assertTrue(validate_measurement_input(document).accepted)
        invalid = copy.deepcopy(document)
        invalid["rows"][0]["displacement_blocks"] = 0.0
        self.assertFalse(validate_measurement_input(invalid).accepted)

    def test_measurement_intake_matches_the_accepted_rollout_registry(self) -> None:
        document = {
            "schema_version": "1.0",
            "measurement_input_schema_version": (
                "person-b-u4-measurement-input-v0.1"
            ),
            "producer_role": "person_e",
            "accepted_rollout_manifest_hash": "1" * 64,
            "measurement_config_hash": "2" * 64,
            "rows": [
                {
                    "measurement_id": "measurement_1",
                    "rollout_id": "rollout_1",
                    "event_id": "event_1",
                    "direction_version": "direction_v1",
                    "control_type": "intervention",
                    "alpha_applied": 1.0,
                    "measurement_status": "measured",
                    "displacement_blocks": 2.0,
                    "persistence_score": 0.8,
                    "ssim": 0.9,
                    "outcome_detail": "",
                    "measurement_artifact_hash": "3" * 64,
                }
            ],
        }
        expected = {
            "rollout_1": {
                "event_id": "event_1",
                "direction_version": "direction_v1",
                "control_type": "intervention",
                "alpha_applied": 1.0,
            }
        }
        self.assertTrue(
            validate_measurement_input(
                document,
                expected_rollouts_by_id=expected,
            ).accepted
        )
        document["rows"][0]["alpha_applied"] = -1.0
        self.assertFalse(
            validate_measurement_input(
                document,
                expected_rollouts_by_id=expected,
            ).accepted
        )

    def test_measurement_intake_rejects_malformed_types_without_crashing(self) -> None:
        document = {
            "schema_version": "1.0",
            "measurement_input_schema_version": (
                "person-b-u4-measurement-input-v0.1"
            ),
            "producer_role": "person_e",
            "accepted_rollout_manifest_hash": "1" * 64,
            "measurement_config_hash": "2" * 64,
            "rows": [
                {
                    "measurement_id": "measurement_1",
                    "rollout_id": "rollout_1",
                    "event_id": "event_1",
                    "direction_version": "direction_v1",
                    "control_type": [],
                    "alpha_applied": 1.0,
                    "measurement_status": [],
                    "displacement_blocks": None,
                    "persistence_score": None,
                    "ssim": None,
                    "outcome_detail": "bad types",
                    "measurement_artifact_hash": "3" * 64,
                }
            ],
        }
        self.assertFalse(validate_measurement_input(document).accepted)


if __name__ == "__main__":
    unittest.main()
