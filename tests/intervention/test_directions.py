from __future__ import annotations

import unittest

from mineocclude.analysis.manifests import build_event_manifest
from mineocclude.contracts.intervention_request import validate_intervention_request
from mineocclude.intervention.directions import (
    derive_time_orthogonal_direction,
    verify_standardized_raw_equivalence,
)
from mineocclude.intervention.doses import build_alpha_table, decoded_blocks_per_alpha
from mineocclude.intervention.producer import build_intervention_request


class TestDirectionMath(unittest.TestCase):
    def test_raw_conversion_equivalence_and_time_projection(self) -> None:
        error = verify_standardized_raw_equivalence(
            [[1.0, 2.0], [3.0, 5.0]],
            standardized_coefficients=[2.0, 4.0],
            standardized_intercept=1.0,
            scaler_mean=[1.0, 1.0],
            scaler_scale=[2.0, 4.0],
        )
        self.assertLess(error, 1e-12)
        direction = derive_time_orthogonal_direction(
            [1.0, 1.0, 0.0],
            [1.0, 1.0, 1.0],
            [0.0, 1.0, 0.0],
            [1.0, 1.0, 1.0],
        )
        self.assertAlmostEqual(direction.unit_residual_direction[0], 1.0)
        self.assertAlmostEqual(direction.post_projection_angle_degrees, 90.0)

    def test_alpha_table_records_cap_reductions(self) -> None:
        effect = decoded_blocks_per_alpha([2.0, 0.0], [1.0, 0.0])
        doses = build_alpha_table(
            [-2.0, 0.0, 4.0],
            blocks_per_alpha=effect,
            typical_activation_norm=4.0,
        )
        self.assertEqual(doses[0].alpha_applied, -1.0)
        self.assertFalse(doses[0].cap_reduced)
        self.assertEqual(doses[2].alpha_applied, 1.0)
        self.assertTrue(doses[2].cap_reduced)


class TestInterventionProducer(unittest.TestCase):
    def test_producer_emits_a_valid_frozen_request(self) -> None:
        dimension = 2048
        mean = [0.0] * dimension
        mean[0] = 1.0
        mean[1] = 1.0
        time = [0.0] * dimension
        time[1] = 1.0
        scale = [1.0] * dimension
        direction = derive_time_orthogonal_direction(mean, scale, time, scale)
        doses = build_alpha_table(
            [-1.0, 0.0, 1.0],
            blocks_per_alpha=1.0,
            typical_activation_norm=10.0,
        )
        request = build_intervention_request(
            request_id="person_b_direction_request_v1",
            direction_version="person_b_mean_direction_v1",
            source_run_id="person_b_probe_run_v1",
            direction=direction,
            layer_idx=10,
            hook_site="residual_stream",
            timestep_idx=8,
            doses=doses,
            typical_activation_norm=10.0,
            scaler_id="scaler_outer_training_v1",
            scaler_hash="a" * 64,
            activation_norm_artifact_hash="d" * 64,
            fit_manifest=build_event_manifest(
                "fit_events_v1", ["fit_event"]
            ),
            validation_manifest=build_event_manifest(
                "validation_events_v1", ["validation_event"]
            ),
            heldout_events=[
                {
                    "event_id": "heldout_event",
                    "trajectory_id": "heldout_trajectory",
                    "layout_id": "heldout_layout",
                }
            ],
            raw_space_equivalence_max_error=0.0,
        )
        self.assertTrue(validate_intervention_request(request).accepted)


if __name__ == "__main__":
    unittest.main()
