from __future__ import annotations

import math
import unittest

from mineocclude.metrics.resampling import (
    bootstrap_confidence_interval,
    hierarchical_bootstrap_indices,
    permutation_p_value,
    permute_trajectory_blocks,
)
from mineocclude.metrics.u1_mean import duration_binned_metrics, regression_metrics
from mineocclude.metrics.u2_calibration import (
    U2MetricError,
    calibration_metrics,
    partial_correlation_controlling_tau,
    partial_correlation_controlling_tau_and_tau_squared,
)
from mineocclude.metrics.u3_dynamics import (
    U3MetricError,
    oracle_slope_ratio,
    reveal_snapback,
    trajectory_growth_slopes,
)


class TestU1KnownAnswers(unittest.TestCase):
    def test_perfect_predictions(self) -> None:
        result = regression_metrics([0.0, 1.0, 2.0], [0.0, 1.0, 2.0])
        self.assertEqual(result.r2, 1.0)
        self.assertEqual(result.mae, 0.0)

    def test_duration_bins_are_exact_seconds(self) -> None:
        result = duration_binned_metrics(
            [0.25, 0.25, 1.0, 1.0],
            [0.0, 1.0, 0.0, 2.0],
            [0.0, 1.0, 0.0, 2.0],
        )
        self.assertEqual(set(result), {0.25, 1.0})
        self.assertTrue(all(value.r2 == 1.0 for value in result.values()))


class TestU2KnownAnswers(unittest.TestCase):
    def test_calibration_uses_central_inclusive_intervals(self) -> None:
        result = calibration_metrics(
            truth=[-0.5, 0.0, 0.5],
            predicted_mean=[0.0, 0.0, 0.0],
            predicted_sigma=[1.0, 1.0, 1.0],
            levels=[0.5, 0.95],
        )
        self.assertEqual(result.empirical_coverage, (1.0, 1.0))
        self.assertAlmostEqual(result.z_diagnostics.mean, 0.0)

    def test_nonpositive_spread_is_counted_and_refused(self) -> None:
        with self.assertRaises(U2MetricError) as raised:
            calibration_metrics([0.0, 1.0], [0.0, 1.0], [1.0, 0.0])
        self.assertEqual(raised.exception.audit.nonpositive_indices, (1,))

    def test_partial_correlation_removes_linear_tau(self) -> None:
        tau = [0.0, 1.0, 2.0, 3.0, 4.0, 5.0]
        latent = [-1.0, 1.0, -1.0, 1.0, -1.0, 1.0]
        decoded = [value + 2.0 * time for value, time in zip(latent, tau)]
        oracle = [3.0 * value - time for value, time in zip(latent, tau)]
        self.assertAlmostEqual(
            partial_correlation_controlling_tau(decoded, oracle, tau),
            1.0,
            places=12,
        )

    def test_partial_correlation_removes_quadratic_tau(self) -> None:
        tau = [0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0]
        latent = [-1.0, 1.0, -2.0, 2.0, -3.0, 3.0, -4.0, 4.0]
        decoded = [
            value + 2.0 * time + 0.5 * time * time
            for value, time in zip(latent, tau)
        ]
        oracle = [
            3.0 * value - time + 1.25 * time * time
            for value, time in zip(latent, tau)
        ]
        self.assertAlmostEqual(
            partial_correlation_controlling_tau_and_tau_squared(
                decoded, oracle, tau
            ),
            1.0,
            places=12,
        )

    def test_quadratic_partial_correlation_requires_full_rank_controls(self) -> None:
        with self.assertRaises(U2MetricError):
            partial_correlation_controlling_tau_and_tau_squared(
                [1.0, 2.0], [2.0, 4.0], [0.0, 1.0]
            )
        with self.assertRaises(U2MetricError):
            partial_correlation_controlling_tau_and_tau_squared(
                [1.0, 2.0, 3.0, 4.0],
                [2.0, 4.0, 6.0, 8.0],
                [0.0, 1.0, 0.0, 1.0],
            )

    def test_quadratic_partial_correlation_rejects_nonfinite_and_bool_values(
        self,
    ) -> None:
        with self.assertRaises(U2MetricError):
            partial_correlation_controlling_tau_and_tau_squared(
                [1.0, math.nan, 3.0], [2.0, 4.0, 6.0], [0.0, 1.0, 2.0]
            )
        with self.assertRaises(U2MetricError):
            partial_correlation_controlling_tau_and_tau_squared(
                [1.0, 2.0, 3.0], [2.0, 4.0, 6.0], [0.0, True, 2.0]
            )


class TestU3KnownAnswers(unittest.TestCase):
    def test_grouped_growth_and_slope_ratio(self) -> None:
        decoded = trajectory_growth_slopes(
            ["a", "a", "b", "b"],
            [0.0, 1.0, 0.0, 2.0],
            [1.0, 2.0, 2.0, 4.0],
            ["occluded", "occluded", "occluded", "occluded"],
        )
        oracle = {"a": 2.0, "b": 2.0}
        self.assertEqual(decoded, {"a": 1.0, "b": 1.0})
        self.assertEqual(oracle_slope_ratio(decoded, oracle), {"a": 0.5, "b": 0.5})

    def test_reveal_snapback_pairs_nearest_frames(self) -> None:
        result = reveal_snapback(
            ["event_a", "event_a", "event_b", "event_b"],
            [-0.05, 0.0, -0.05, 0.0],
            [2.0, 1.0, 4.0, 1.0],
            ["occluded", "visible", "occluded", "visible"],
        )
        self.assertEqual(result.median_difference, -2.0)
        self.assertAlmostEqual(result.median_reduction_fraction, 0.625)

    def test_reveal_snapback_requires_occluded_to_visible_transition(self) -> None:
        with self.assertRaisesRegex(U3MetricError, "paired pre/post"):
            reveal_snapback(
                ["event_a", "event_a"],
                [-0.05, 0.0],
                [2.0, 1.0],
                ["visible", "visible"],
            )


class TestResamplingKnownAnswers(unittest.TestCase):
    def test_hierarchy_keeps_whole_trajectory_frames(self) -> None:
        rows = [
            {"layout_id": layout, "trajectory_id": trajectory}
            for layout, trajectory in (
                ("l1", "t1"),
                ("l1", "t1"),
                ("l1", "t2"),
                ("l1", "t2"),
                ("l2", "t3"),
                ("l2", "t3"),
            )
        ]
        replicates = hierarchical_bootstrap_indices(rows, resample_count=10, seed=7)
        for replicate in replicates:
            self.assertEqual(replicate.count(0), replicate.count(1))
            self.assertEqual(replicate.count(2), replicate.count(3))
            self.assertEqual(replicate.count(4), replicate.count(5))

    def test_trajectory_permutation_preserves_sequences(self) -> None:
        permuted = permute_trajectory_blocks(
            ["a", "a", "b", "b"], [1.0, 2.0, 3.0, 4.0], seed=2
        )
        self.assertIn(permuted[:2], ((1.0, 2.0), (3.0, 4.0)))
        self.assertIn(permuted[2:], ((1.0, 2.0), (3.0, 4.0)))

    def test_add_one_p_value_and_equal_tailed_interval(self) -> None:
        self.assertEqual(permutation_p_value(2.0, [0.0, 1.0, 2.0]), 0.5)
        self.assertEqual(bootstrap_confidence_interval([0.0, 1.0, 2.0], coverage=0.5), (0.5, 1.5))


if __name__ == "__main__":
    unittest.main()
