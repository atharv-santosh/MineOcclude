from __future__ import annotations

import unittest

import numpy as np

from mineocclude.regime_a_first25_analysis import (
    ALPHAS,
    PreparedKernelRidge,
    bootstrap_intervals,
    choose_alpha,
    inner_fold_assignment,
    predict_all_alphas,
    scalar_metrics,
)
from mineocclude.probes.p7_ridge import standardized_kernel_numpy


class RegimeAFirst25AnalysisTests(unittest.TestCase):
    def test_inner_folds_are_deterministic_balanced_and_outcome_independent(self) -> None:
        ids = [f"t{i:02d}" for i in range(20)]
        directions = {identity: "LEFT_TO_RIGHT" if index < 11 else "RIGHT_TO_LEFT" for index, identity in enumerate(ids)}
        first = inner_fold_assignment(ids, directions, 3)
        second = inner_fold_assignment(list(reversed(ids)), directions, 3)
        self.assertEqual(first, second)
        self.assertEqual({fold: list(first.values()).count(fold) for fold in range(5)}, {fold: 4 for fold in range(5)})

    def test_exact_macro_is_equal_trajectory_not_pooled(self) -> None:
        rows = [
            {"trajectory_id": "a", "world_x": 0.0, "pred": 0.0},
            {"trajectory_id": "a", "world_x": 1.0, "pred": 1.0},
            {"trajectory_id": "b", "world_x": 0.0, "pred": 1.0},
            {"trajectory_id": "b", "world_x": 2.0, "pred": 1.0},
        ]
        result = scalar_metrics(rows, "pred")
        self.assertAlmostEqual(result["macro_r2"], 0.5)
        self.assertEqual(result["trajectory_count"], 2)

    def test_kernel_predictions_match_explicit_standardized_ridge(self) -> None:
        rng = np.random.default_rng(11)
        train = rng.normal(size=(9, 7))
        test = rng.normal(size=(4, 7))
        y = rng.normal(size=9)
        kernel = standardized_kernel_numpy(train, np.vstack([train, test])).kernel
        got = predict_all_alphas(kernel, y, 4)
        prepared = PreparedKernelRidge.from_kernel(kernel, 9).predict_all(y)
        mean, scale = train.mean(0), train.std(0)
        scale[scale == 0] = 1
        x = (train - mean) / scale
        z = (test - mean) / scale
        for alpha in ALPHAS:
            dual = np.linalg.solve(x @ x.T + alpha * np.eye(9), y - y.mean())
            expected = z @ x.T @ dual + y.mean()
            np.testing.assert_allclose(got[alpha], expected, rtol=1e-10, atol=1e-10)
            np.testing.assert_allclose(prepared[alpha], expected, rtol=1e-10, atol=1e-10)

    def test_alpha_selection_and_whole_trajectory_bootstrap(self) -> None:
        rows = {}
        predictions = {alpha: {} for alpha in ALPHAS}
        for trajectory in range(3):
            for tau in range(2):
                index = trajectory * 2 + tau
                rows[index] = {"trajectory_id": f"t{trajectory}", "world_x": float(tau)}
                for alpha in ALPHAS:
                    predictions[alpha][index] = float(tau) if alpha == 1.0 else 0.5
        selected, _ = choose_alpha(predictions, rows)
        self.assertEqual(selected, 1.0)
        overall = scalar_metrics([dict(row, pred=predictions[1.0][index]) for index, row in rows.items()], "pred")
        bins = {name: overall for name in ("SHORT", "INTERMEDIATE", "LONG", "NEAR_CONTEXT", "BEYOND_CONTEXT")}
        first = bootstrap_intervals(overall, bins, replicates=10000, seed=9)
        second = bootstrap_intervals(overall, bins, replicates=10000, seed=9)
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
