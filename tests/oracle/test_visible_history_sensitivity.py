from __future__ import annotations

import unittest

from mineocclude.oracle.schema import OracleValidationError
from mineocclude.oracle.visible_history_sensitivity import (
    estimate_visible_history_motion,
    visible_history_posterior,
)


class TestVisibleHistorySensitivity(unittest.TestCase):
    def test_visible_history_only_estimates_motion(self) -> None:
        estimate = estimate_visible_history_motion(
            [0.0, 0.05, 0.10, 0.15],
            [1.0, 1.1, 1.2, 1.3],
        )
        self.assertAlmostEqual(estimate.velocity_blocks_per_second, 2.0)
        self.assertAlmostEqual(estimate.q_blocks2_per_second, 0.0, places=28)
        posterior = visible_history_posterior(1.3, 0.5, estimate)
        self.assertAlmostEqual(posterior.mean_blocks, 2.3)
        self.assertAlmostEqual(posterior.variance_blocks2, 0.0, places=28)

    def test_insufficient_visible_history_fails_closed(self) -> None:
        with self.assertRaises(OracleValidationError):
            estimate_visible_history_motion([0.0, 0.05], [1.0, 1.1])


if __name__ == "__main__":
    unittest.main()
