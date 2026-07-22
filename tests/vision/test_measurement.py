from __future__ import annotations

import unittest

from mineocclude.contracts.analysis_inputs import validate_measurement_input
from mineocclude.experiments.registry import hash_json_value
from mineocclude.vision.measurement import (
    FrameLocalization,
    MeasurementError,
    build_measurement_document,
    build_measurement_evidence,
    build_measurement_row,
    find_alpha_zero_matches,
    find_reappearance,
    validate_measurement_evidence,
)
from mineocclude.vision.ssim import SsimResult
from tests.experiments.test_registry import registry_bundle


def rollout(
    rollout_id: str,
    *,
    control_type: str,
    alpha: float,
    outcome: str = "measurable_continuation",
    status: str = "accepted",
) -> dict[str, object]:
    return {
        "rollout_id": rollout_id,
        "event_id": "event_1",
        "seed": 9,
        "direction_version": "direction_v1",
        "control_type": control_type,
        "dose_id": f"dose:{rollout_id}",
        "alpha_requested": alpha,
        "alpha_applied": alpha,
        "cap_reduced": False,
        "intended_block_shift": alpha,
        "layer_idx": 3,
        "hook_site": "decoder_output",
        "timestep_idx": 15,
        "outcome": outcome,
        "outcome_detail": (
            None if outcome == "measurable_continuation" else "explicit failure"
        ),
        "status": status,
        "exclusion_reason": "generation failed" if status == "excluded" else None,
    }


def measured_reappearance(offset: float) -> object:
    return find_reappearance(
        [
            FrameLocalization(1, None, False, rejection_reason="pre_reveal"),
            FrameLocalization(2, 4.0 + offset, True),
            FrameLocalization(3, 5.0 + offset, True),
            FrameLocalization(4, 6.0 + offset, True),
        ],
        reveal_frame_idx=1,
    )


SSIM = SsimResult(
    full_frame_ssim=0.95,
    background_masked_ssim=0.99,
    full_frame_pixel_count=36,
    background_pixel_count=28,
    data_range=255.0,
)


class TestReappearance(unittest.TestCase):
    def test_primary_and_first_three_sensitivity(self) -> None:
        result = measured_reappearance(0.0)
        self.assertTrue(result.measured)
        self.assertEqual(result.primary_frame_idx, 2)
        self.assertEqual(result.primary_wall_parallel_blocks, 4.0)
        self.assertEqual(result.sensitivity_wall_parallel_blocks, 5.0)

    def test_nonconsecutive_detections_are_non_persistence_not_zero(self) -> None:
        result = find_reappearance(
            [
                FrameLocalization(2, 1.0, True),
                FrameLocalization(3, None, False, rejection_reason="not_detected"),
                FrameLocalization(4, 2.0, True),
                FrameLocalization(5, None, False, rejection_reason="not_detected"),
                FrameLocalization(6, 3.0, True),
            ],
            reveal_frame_idx=1,
        )
        self.assertEqual(result.status, "non_persistence")
        self.assertIsNone(result.primary_wall_parallel_blocks)
        self.assertEqual(result.sensitivity_wall_parallel_blocks, 2.0)

    def test_missing_frame_records_are_not_called_non_persistence(self) -> None:
        with self.assertRaises(MeasurementError):
            find_reappearance(
                [
                    FrameLocalization(2, 1.0, True),
                    FrameLocalization(4, 2.0, True),
                ],
                reveal_frame_idx=1,
            )

    def test_post_reveal_coverage_cannot_start_late(self) -> None:
        with self.assertRaisesRegex(MeasurementError, "coverage must begin"):
            find_reappearance(
                [
                    FrameLocalization(10, 1.0, True),
                    FrameLocalization(11, 1.0, True),
                ],
                reveal_frame_idx=1,
            )


class TestMeasurementProduction(unittest.TestCase):
    def test_alpha_zero_matching_and_measured_displacement(self) -> None:
        baseline = rollout("rollout_zero", control_type="alpha_zero", alpha=0.0)
        pushed = rollout("rollout_push", control_type="intervention", alpha=2.0)
        matches = find_alpha_zero_matches([pushed, baseline])
        self.assertEqual(matches["rollout_push"]["rollout_id"], "rollout_zero")
        row = build_measurement_row(
            pushed,
            measurement_id="measurement_push",
            measurement_artifact_hash="a" * 64,
            baseline_rollout_id="rollout_zero",
            pushed_reappearance=measured_reappearance(2.0),
            baseline_reappearance=measured_reappearance(0.0),
            ssim_result=SSIM,
        )
        self.assertEqual(row["measurement_status"], "measured")
        self.assertEqual(row["displacement_blocks"], 2.0)
        self.assertEqual(row["sensitivity_displacement_blocks"], 2.0)
        self.assertEqual(row["intended_block_shift"], 2.0)
        self.assertEqual(row["layer_idx"], 3)
        self.assertEqual(row["timestep_idx"], 15)
        self.assertEqual(row["pushed_detection_delay_frames"], 1)

    def test_generation_failure_never_becomes_zero_or_generic_exclusion(self) -> None:
        failed = rollout(
            "rollout_failed",
            control_type="intervention",
            alpha=2.0,
            outcome="generation_failure",
            status="excluded",
        )
        row = build_measurement_row(
            failed,
            measurement_id="measurement_failed",
            measurement_artifact_hash="b" * 64,
        )
        self.assertEqual(row["measurement_status"], "generation_failure")
        self.assertIsNone(row["displacement_blocks"])
        self.assertIsNone(row["ssim"])

    def test_missing_baseline_and_negative_ssim_become_explicit_exclusions(self) -> None:
        pushed = rollout("rollout_push", control_type="intervention", alpha=2.0)
        missing_baseline = build_measurement_row(
            pushed,
            measurement_id="measurement_missing_baseline",
            measurement_artifact_hash="f" * 64,
            pushed_reappearance=measured_reappearance(1.0),
            ssim_result=SSIM,
        )
        self.assertEqual(missing_baseline["measurement_status"], "excluded")
        negative_ssim = SsimResult(
            full_frame_ssim=-0.1,
            background_masked_ssim=0.5,
            full_frame_pixel_count=16,
            background_pixel_count=12,
            data_range=255.0,
        )
        schema_gap = build_measurement_row(
            pushed,
            measurement_id="measurement_negative_ssim",
            measurement_artifact_hash="e" * 64,
            baseline_rollout_id="rollout_zero",
            pushed_reappearance=measured_reappearance(1.0),
            baseline_reappearance=measured_reappearance(0.0),
            ssim_result=negative_ssim,
        )
        self.assertEqual(schema_gap["measurement_status"], "excluded")
        self.assertEqual(schema_gap["raw_ssim"], -0.1)

    def test_missing_alpha_zero_is_reported_without_suppressing_failure(self) -> None:
        failed = rollout(
            "rollout_failed",
            control_type="intervention",
            alpha=2.0,
            outcome="generation_failure",
            status="excluded",
        )
        self.assertIsNone(find_alpha_zero_matches([failed])["rollout_failed"])

    def test_document_validates_registry_and_exact_evidence_coverage(self) -> None:
        manifest, registry = registry_bundle()
        baseline = manifest["rollout_rows"][0]
        row = build_measurement_row(
            baseline,
            measurement_id="measurement_zero",
            measurement_artifact_hash="c" * 64,
            baseline_rollout_id="rollout_zero",
            pushed_reappearance=measured_reappearance(0.0),
            baseline_reappearance=measured_reappearance(0.0),
            ssim_result=SSIM,
        )
        document = build_measurement_document(
            [row],
            rollout_manifest=manifest,
            registry=registry,
            accepted_rollout_manifest_hash="d" * 64,
            registry_hash="e" * 64,
            measurement_evidence=[
                {
                    "evidence_id": "evidence_zero",
                    "rollout_id": "rollout_zero",
                    "uri": "memory://evidence/zero",
                    "sha256": "c" * 64,
                    "producer_run_id": "run_rollout",
                }
            ],
            result_scope="known_answer",
        )
        expected = {baseline["rollout_id"]: baseline}
        self.assertTrue(
            validate_measurement_input(
                document,
                expected_rollouts_by_id=expected,
            ).accepted
        )
        self.assertEqual(
            document["alpha_zero_persistence_summary"]["persistent_count"],
            1,
        )
        with self.assertRaises(MeasurementError):
            build_measurement_document(
                [row],
                rollout_manifest=manifest,
                registry=registry,
                accepted_rollout_manifest_hash="d" * 64,
                registry_hash="e" * 64,
                measurement_evidence=[],
                result_scope="known_answer",
            )

    def test_detailed_evidence_is_hash_bound(self) -> None:
        payload = {"rollout_id": "rollout_1", "detections": []}
        document = build_measurement_evidence(
            payload,
            evidence_id="evidence_1",
            rollout_id="rollout_1",
            producer_run_id="measurement_run_1",
            code_sha="a" * 40,
            accepted_rollout_manifest_hash="e" * 64,
            registry_hash="f" * 64,
        )
        validate_measurement_evidence(document)
        payload["detections"].append("mutated")
        self.assertEqual(document["payload"]["detections"], [])
        self.assertEqual(len(hash_json_value(document)), 64)
        with self.assertRaises(MeasurementError):
            build_measurement_evidence(
                {},
                evidence_id="bad_hash",
                rollout_id="rollout_1",
                producer_run_id="measurement_run_1",
                code_sha="a" * 40,
                accepted_rollout_manifest_hash=" " + "e" * 63,
                registry_hash="f" * 64,
            )


if __name__ == "__main__":
    unittest.main()
