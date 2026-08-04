from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from mineocclude.analysis.coordinates import coordinate_frame_hash
from mineocclude.analysis.config import hash_core_analysis_config
from mineocclude.analysis.manifests import sha256_value
from mineocclude.contracts.analysis_inputs import (
    AnalysisInputRejectionCode,
    validate_baseline_input,
    validate_measurement_input,
    validate_state_input,
)
from mineocclude.contracts.rollout_registry import validate_rollout_registry_bundle
from mineocclude.oracle.schema import validate_oracle_target_document
from mineocclude.oracle.targets import build_regime_a_target_document


HASHES = {
    "config": "1" * 64,
    "model": "2" * 64,
    "preprocess": "3" * 64,
    "manifest": "4" * 64,
}
ROOT = Path(__file__).resolve().parents[2]


def baseline_document() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "baseline_input_schema_version": "person-b-baseline-input-v0.1",
        "producer_role": "person_d",
        "baseline_id": "last_seen_v1",
        "baseline_family": "last_seen",
        "target_name": "mu_oracle_blocks",
        "feature_access": [
            "last_visible_position_blocks",
            "tau",
            "visibility",
        ],
        "legal_information": {
            "uses_hidden_truth": False,
            "uses_future_information": False,
            "uses_scripted_q": False,
        },
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


def measurement_context() -> tuple[dict, dict, dict]:
    fixture_dir = ROOT / "tests" / "fixtures" / "rollout_registry"
    rollout_manifest = json.loads(
        (fixture_dir / "accepted_rollout_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    registry = json.loads(
        (fixture_dir / "accepted_registry.json").read_text(encoding="utf-8")
    )
    validation = validate_rollout_registry_bundle(rollout_manifest, registry)
    if not validation.accepted:
        raise AssertionError(validation.rejections)

    measurement_rows = []
    for index, rollout in enumerate(rollout_manifest["rollout_rows"], start=1):
        outcome = rollout["outcome"]
        measured = outcome == "measurable_continuation"
        measurement_rows.append(
            {
                "measurement_id": f"measurement_{index}",
                "rollout_id": rollout["rollout_id"],
                "rollout_run_id": rollout["run_id"],
                "event_id": rollout["event_id"],
                "direction_version": rollout["direction_version"],
                "control_type": rollout["control_type"],
                "alpha_applied": rollout["alpha_applied"],
                "measurement_status": (
                    "measured" if measured else outcome
                ),
                "displacement_blocks": 2.0 if measured else None,
                "persistence_score": 0.8 if measured else None,
                "ssim": 0.9 if measured else None,
                "outcome_detail": "" if measured else rollout["outcome_detail"],
                "measurement_artifact_hash": f"{index}" * 64,
            }
        )
    document = {
        "schema_version": "1.0",
        "measurement_input_schema_version": "person-b-u4-measurement-input-v0.1",
        "producer_role": "person_e",
        "accepted_rollout_manifest_hash": sha256_value(rollout_manifest),
        "accepted_registry_hash": sha256_value(registry),
        "measurement_config_hash": "a" * 64,
        "rows": measurement_rows,
    }
    return document, rollout_manifest, registry


def rollout_lookup(rollout_manifest: dict, registry: dict) -> dict:
    """Build a caller assertion for adversarial boundary tests only."""

    run_by_id = {run["run_id"]: run for run in registry["runs"]}
    return {
        rollout["rollout_id"]: {
            "event_id": rollout["event_id"],
            "direction_version": rollout["direction_version"],
            "control_type": rollout["control_type"],
            "alpha_applied": rollout["alpha_applied"],
            "outcome": rollout["outcome"],
            "measurable": rollout["measurable"],
            "status": rollout["status"],
            "run_id": rollout["run_id"],
            "execution_status": run_by_id[rollout["run_id"]][
                "execution_status"
            ],
        }
        for rollout in rollout_manifest["rollout_rows"]
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


def state_input_document() -> dict:
    document = json.loads(
        (
            ROOT / "tests" / "fixtures" / "person_b" / "synthetic_state_log.json"
        ).read_text(encoding="utf-8")
    )
    document.update(
        {
            "state_input_schema_version": "person-b-state-input-v0.1",
            "producer_role": "person_c",
            "accepted_manifest_hash": document["rows"][0][
                "accepted_manifest_hash"
            ],
            "coordinate_frame": coordinate_frame(),
        }
    )
    return document


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

    def test_state_intake_rejects_cross_row_timebase_failures(self) -> None:
        cases = (
            (
                "server_tick_skip",
                lambda document: document["rows"][2].update({"server_tick": 103}),
                AnalysisInputRejectionCode.NONCONSECUTIVE_SERVER_TICK,
            ),
            (
                "mixed_episode",
                lambda document: document["rows"][2].update(
                    {"episode_id": "different_episode"}
                ),
                AnalysisInputRejectionCode.MIXED_EPISODE_ID,
            ),
            (
                "tau_mismatch",
                lambda document: document["rows"][2].update({"tau": 0.15}),
                AnalysisInputRejectionCode.TIMEBASE_MISMATCH,
            ),
        )
        self.assertTrue(validate_state_input(state_input_document()).accepted)
        for name, mutate, expected_code in cases:
            with self.subTest(name=name):
                document = state_input_document()
                mutate(document)
                original = copy.deepcopy(document)
                result = validate_state_input(document)
                self.assertFalse(result.accepted)
                self.assertIn(
                    expected_code,
                    {item.code for item in result.rejections},
                )
                self.assertEqual(document, original)

    def test_baseline_intake_requires_exact_oof_folds(self) -> None:
        document = baseline_document()
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

    def test_baseline_intake_rejects_illegal_information_access(self) -> None:
        cases = (
            (
                "hidden_truth_family",
                {"baseline_family": "hidden_truth"},
                AnalysisInputRejectionCode.UNSUPPORTED_BASELINE_FAMILY,
            ),
            (
                "hidden_truth_target",
                {"target_name": "x_true_blocks"},
                AnalysisInputRejectionCode.LEGAL_INFORMATION_VIOLATION,
            ),
            (
                "future_information",
                {"legal_information": {
                    "uses_hidden_truth": False,
                    "uses_future_information": True,
                    "uses_scripted_q": False,
                }},
                AnalysisInputRejectionCode.LEGAL_INFORMATION_VIOLATION,
            ),
            (
                "scripted_q",
                {"feature_access": ["last_visible_position_blocks", "q"]},
                AnalysisInputRejectionCode.LEGAL_INFORMATION_VIOLATION,
            ),
            (
                "renamed_hidden_truth",
                {
                    "feature_access": [
                        "last_visible_position_blocks",
                        "tau",
                        "visibility",
                        "authoritative_server_position_blocks",
                    ]
                },
                AnalysisInputRejectionCode.LEGAL_INFORMATION_VIOLATION,
            ),
            (
                "renamed_future_information",
                {
                    "feature_access": [
                        "last_visible_position_blocks",
                        "tau",
                        "visibility",
                        "position_at_next_frame",
                    ]
                },
                AnalysisInputRejectionCode.LEGAL_INFORMATION_VIOLATION,
            ),
            (
                "renamed_scripted_q",
                {
                    "feature_access": [
                        "last_visible_position_blocks",
                        "tau",
                        "visibility",
                        "q_blocks2_per_second",
                    ]
                },
                AnalysisInputRejectionCode.LEGAL_INFORMATION_VIOLATION,
            ),
            (
                "unknown_feature",
                {
                    "feature_access": [
                        "last_visible_position_blocks",
                        "tau",
                        "visibility",
                        "apparently_safe_but_unknown",
                    ]
                },
                AnalysisInputRejectionCode.LEGAL_INFORMATION_VIOLATION,
            ),
            (
                "malformed_feature_access",
                {"feature_access": ["last_visible_position_blocks", []]},
                AnalysisInputRejectionCode.INVALID_VALUE,
            ),
            (
                "malformed_legal_information",
                {"legal_information": []},
                AnalysisInputRejectionCode.INVALID_VALUE,
            ),
        )
        for name, changes, expected_code in cases:
            with self.subTest(name=name):
                document = baseline_document()
                document.update(changes)
                original = copy.deepcopy(document)
                result = validate_baseline_input(
                    document,
                    expected_fold_by_frame={("trajectory_1", 0): 2},
                )
                self.assertFalse(result.accepted)
                self.assertIn(
                    expected_code,
                    {item.code for item in result.rejections},
                )
                self.assertEqual(document, original)

    def test_measurement_intake_never_encodes_failures_as_zero(self) -> None:
        document, rollout_manifest, registry = measurement_context()
        self.assertTrue(
            validate_measurement_input(
                document,
                rollout_manifest=rollout_manifest,
                registry=registry,
            ).accepted
        )
        invalid = copy.deepcopy(document)
        failed = next(
            row
            for row in invalid["rows"]
            if row["measurement_status"] == "generation_failure"
        )
        failed["displacement_blocks"] = 0.0
        self.assertFalse(
            validate_measurement_input(
                invalid,
                rollout_manifest=rollout_manifest,
                registry=registry,
            ).accepted
        )

    def test_measurement_intake_matches_the_accepted_rollout_registry(self) -> None:
        document, rollout_manifest, registry = measurement_context()
        original = copy.deepcopy(document)
        original_manifest = copy.deepcopy(rollout_manifest)
        original_registry = copy.deepcopy(registry)
        result = validate_measurement_input(
            document,
            rollout_manifest=rollout_manifest,
            registry=registry,
        )
        self.assertTrue(result.accepted, result.rejections)
        self.assertEqual(document, original)
        self.assertEqual(rollout_manifest, original_manifest)
        self.assertEqual(registry, original_registry)
        missing_context = validate_measurement_input(document)
        self.assertFalse(missing_context.accepted)
        self.assertIn(
            AnalysisInputRejectionCode.INVALID_ROLLOUT_REGISTRY_BUNDLE,
            {item.code for item in missing_context.rejections},
        )

    def test_measurement_intake_rejects_rollout_outcome_contradictions(self) -> None:
        for outcome in ("non_persistence", "generation_failure"):
            with self.subTest(outcome=outcome):
                document, rollout_manifest, registry = measurement_context()
                rollout_by_id = {
                    rollout["rollout_id"]: rollout
                    for rollout in rollout_manifest["rollout_rows"]
                }
                row = next(
                    row
                    for row in document["rows"]
                    if rollout_by_id[row["rollout_id"]]["outcome"] == outcome
                )
                row.update(
                    {
                        "measurement_status": "measured",
                        "displacement_blocks": 0.0,
                        "persistence_score": 0.0,
                        "ssim": 0.0,
                    }
                )
                result = validate_measurement_input(
                    document,
                    rollout_manifest=rollout_manifest,
                    registry=registry,
                )
                self.assertFalse(result.accepted)
                self.assertIn(
                    AnalysisInputRejectionCode.OUTCOME_CONFLATION,
                    {item.code for item in result.rejections},
                )

    def test_measurement_intake_binds_manifest_registry_event_and_run(self) -> None:
        cases = (
            (
                "stale_manifest_hash",
                lambda document, _manifest, _registry: document.update(
                    {"accepted_rollout_manifest_hash": "f" * 64}
                ),
            ),
            (
                "stale_registry_hash",
                lambda document, _manifest, _registry: document.update(
                    {"accepted_registry_hash": "f" * 64}
                ),
            ),
            (
                "wrong_event",
                lambda document, _manifest, _registry: document["rows"][0].update(
                    {"event_id": "different_event"}
                ),
            ),
            (
                "wrong_producing_run",
                lambda document, _manifest, _registry: document["rows"][0].update(
                    {"rollout_run_id": "different_run"}
                ),
            ),
            (
                "malformed_registry_lifecycle",
                lambda _document, _manifest, registry: registry["runs"][0].update(
                    {"execution_status": []}
                ),
            ),
        )
        for name, mutate in cases:
            with self.subTest(name=name):
                document, rollout_manifest, registry = measurement_context()
                mutate(document, rollout_manifest, registry)
                result = validate_measurement_input(
                    document,
                    rollout_manifest=rollout_manifest,
                    registry=registry,
                )
                self.assertFalse(result.accepted)

    def test_fake_lookup_cannot_make_non_persistence_measurable(self) -> None:
        document, rollout_manifest, registry = measurement_context()
        claimed = rollout_lookup(rollout_manifest, registry)
        row = next(
            row
            for row in document["rows"]
            if claimed[row["rollout_id"]]["outcome"] == "non_persistence"
        )
        row.update(
            {
                "measurement_status": "measured",
                "displacement_blocks": 0.0,
                "persistence_score": 0.0,
                "ssim": 0.0,
                "outcome_detail": "",
            }
        )
        claimed[row["rollout_id"]].update(
            {
                "outcome": "measurable_continuation",
                "measurable": True,
            }
        )

        result = validate_measurement_input(
            document,
            rollout_manifest=rollout_manifest,
            registry=registry,
            expected_rollouts_by_id=claimed,
        )

        self.assertFalse(result.accepted)
        self.assertIn(
            AnalysisInputRejectionCode.ROLLOUT_LOOKUP_MISMATCH,
            {item.code for item in result.rejections},
        )
        self.assertIn(
            AnalysisInputRejectionCode.OUTCOME_CONFLATION,
            {item.code for item in result.rejections},
        )

    def test_fake_lookup_cannot_override_real_rollout_outcome(self) -> None:
        document, rollout_manifest, registry = measurement_context()
        claimed = rollout_lookup(rollout_manifest, registry)
        rollout_id = next(
            rollout_id
            for rollout_id, facts in claimed.items()
            if facts["outcome"] == "non_persistence"
        )
        claimed[rollout_id].update(
            {
                "outcome": "measurable_continuation",
                "measurable": True,
            }
        )

        result = validate_measurement_input(
            document,
            rollout_manifest=rollout_manifest,
            registry=registry,
            expected_rollouts_by_id=claimed,
        )

        self.assertFalse(result.accepted)
        self.assertIn(
            AnalysisInputRejectionCode.ROLLOUT_LOOKUP_MISMATCH,
            {item.code for item in result.rejections},
        )

    def test_real_hashes_do_not_authenticate_a_mutated_lookup(self) -> None:
        document, rollout_manifest, registry = measurement_context()
        claimed = rollout_lookup(rollout_manifest, registry)
        rollout_id = next(iter(claimed))
        claimed[rollout_id].update(
            {
                "outcome": "non_persistence",
                "measurable": False,
                "status": "excluded",
                "execution_status": "failed",
            }
        )

        result = validate_measurement_input(
            document,
            rollout_manifest=rollout_manifest,
            registry=registry,
            expected_rollouts_by_id=claimed,
        )

        self.assertFalse(result.accepted)
        self.assertIn(
            AnalysisInputRejectionCode.ROLLOUT_LOOKUP_MISMATCH,
            {item.code for item in result.rejections},
        )

    def test_measurement_intake_rejects_malformed_types_without_crashing(self) -> None:
        document, rollout_manifest, registry = measurement_context()
        document["rows"][0]["control_type"] = []
        document["rows"][0]["measurement_status"] = []
        self.assertFalse(
            validate_measurement_input(
                document,
                rollout_manifest=rollout_manifest,
                registry=registry,
            ).accepted
        )


if __name__ == "__main__":
    unittest.main()
