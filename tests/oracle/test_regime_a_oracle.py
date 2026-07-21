from __future__ import annotations

import copy
import json
import math
import random
import unittest
from pathlib import Path

from mineocclude.oracle.closed_form import closed_form_posterior
from mineocclude.oracle.primary_scalar_kalman import scalar_kalman_posterior
from mineocclude.oracle.schema import (
    OracleValidationError,
    validate_oracle_target,
    validate_oracle_target_rows,
)
from mineocclude.oracle.targets import build_regime_a_target_document


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures" / "person_b"


class TestRegimeAOracle(unittest.TestCase):
    def setUp(self) -> None:
        self.state_document = json.loads(
            (FIXTURES / "synthetic_state_log.json").read_text(encoding="utf-8")
        )
        self.expected_document = json.loads(
            (FIXTURES / "synthetic_oracle_targets.json").read_text(encoding="utf-8")
        )
        self.build_kwargs = {
            "oracle_run_id": "synthetic_person_b_oracle_run_001",
            "oracle_code_sha": "a" * 40,
            "oracle_config_hash": "b" * 64,
        }

    def test_independent_implementations_agree_on_seeded_cases(self) -> None:
        rng = random.Random(20260721)
        for _ in range(250):
            x_last = rng.uniform(-50.0, 50.0)
            velocity = rng.uniform(-4.0, 4.0)
            process_noise = rng.uniform(0.0001, 2.0)
            hidden_ticks = rng.randint(0, 500)
            iterative = scalar_kalman_posterior(
                x_last,
                velocity,
                process_noise,
                hidden_ticks,
            )
            closed = closed_form_posterior(
                x_last,
                velocity,
                process_noise,
                hidden_ticks * 0.05,
            )
            self.assertAlmostEqual(iterative.mean_blocks, closed.mean_blocks, delta=1e-6)
            self.assertAlmostEqual(
                iterative.variance_blocks2,
                closed.variance_blocks2,
                delta=1e-6,
            )

    def test_oracle_invariants(self) -> None:
        short = closed_form_posterior(3.0, 1.0, 0.2, 0.5)
        long = closed_form_posterior(3.0, 1.0, 0.2, 1.0)
        high_q = closed_form_posterior(3.0, 1.0, 0.8, 0.5)
        reveal = closed_form_posterior(4.0, 1.0, 0.8, 0.0)
        self.assertTrue(math.isfinite(short.variance_blocks2))
        self.assertGreater(short.variance_blocks2, 0.0)
        self.assertGreater(long.variance_blocks2, short.variance_blocks2)
        self.assertGreater(high_q.variance_blocks2, short.variance_blocks2)
        self.assertLess(reveal.variance_blocks2, long.variance_blocks2)
        self.assertEqual(reveal.variance_blocks2, 0.0)

    def test_hidden_truth_is_not_an_oracle_input(self) -> None:
        changed = copy.deepcopy(self.state_document)
        changed["rows"][1]["x_true_blocks"] = -999.0

        original_targets = build_regime_a_target_document(
            self.state_document,
            **self.build_kwargs,
        )["rows"]
        changed_targets = build_regime_a_target_document(
            changed,
            **self.build_kwargs,
        )["rows"]
        self.assertEqual(
            [row["mu_oracle_blocks"] for row in original_targets],
            [row["mu_oracle_blocks"] for row in changed_targets],
        )
        self.assertEqual(
            [row["var_oracle_blocks2"] for row in original_targets],
            [row["var_oracle_blocks2"] for row in changed_targets],
        )
        self.assertNotEqual(
            original_targets[1]["x_true_blocks"],
            changed_targets[1]["x_true_blocks"],
        )

    def test_synthetic_fixture_matches_expected_targets(self) -> None:
        actual = build_regime_a_target_document(
            self.state_document,
            **self.build_kwargs,
        )
        for row in actual["rows"]:
            validate_oracle_target(row)
        self.assertEqual(actual, self.expected_document)

    def test_reveal_resets_and_reanchors_the_stateful_oracle(self) -> None:
        rows = build_regime_a_target_document(
            self.state_document,
            **self.build_kwargs,
        )["rows"]
        before_reveal, reveal, after_reveal = rows[2:5]
        self.assertGreater(before_reveal["var_oracle_blocks2"], 0.0)
        self.assertEqual(reveal["var_oracle_blocks2"], 0.0)
        self.assertEqual(reveal["mu_oracle_blocks"], 20.0)
        self.assertEqual(after_reveal["last_visible_position_blocks"], 20.0)
        self.assertAlmostEqual(after_reveal["mu_oracle_blocks"], 20.05)

    def test_hidden_tau_cannot_stall_or_decrease_before_reveal(self) -> None:
        invalid = copy.deepcopy(self.state_document)
        invalid["rows"][2]["tau"] = invalid["rows"][1]["tau"]
        with self.assertRaisesRegex(OracleValidationError, "tau must increase"):
            build_regime_a_target_document(invalid, **self.build_kwargs)

    def test_v_and_q_cannot_change_within_an_occluded_run(self) -> None:
        for field, value in (("v", 2.0), ("q", 0.75)):
            with self.subTest(field=field):
                invalid = copy.deepcopy(self.state_document)
                invalid["rows"][2][field] = value
                with self.assertRaisesRegex(OracleValidationError, "remain fixed"):
                    build_regime_a_target_document(invalid, **self.build_kwargs)

    def test_unknown_visibility_fails_closed(self) -> None:
        invalid = copy.deepcopy(self.state_document)
        invalid["rows"][1]["visibility"] = "unknown"
        with self.assertRaises(OracleValidationError):
            build_regime_a_target_document(invalid, **self.build_kwargs)

    def test_document_envelope_is_not_silently_repaired(self) -> None:
        for field, value in (
            ("schema_version", "9.9"),
            ("join_key", ["row_order"]),
        ):
            with self.subTest(field=field):
                invalid = copy.deepcopy(self.state_document)
                invalid[field] = value
                with self.assertRaises(OracleValidationError):
                    build_regime_a_target_document(invalid, **self.build_kwargs)

    def test_mixed_manifest_and_source_run_fail_closed(self) -> None:
        mutations = (
            ("accepted_manifest_hash", "f" * 64),
            ("run_id", "different_source_run"),
        )
        for field, value in mutations:
            with self.subTest(field=field):
                invalid = copy.deepcopy(self.state_document)
                invalid["rows"][-1][field] = value
                with self.assertRaises(OracleValidationError):
                    build_regime_a_target_document(invalid, **self.build_kwargs)

    def test_target_semantics_fail_closed(self) -> None:
        mutations = (
            ("mu_oracle_blocks", 999.0),
            ("target_source", "made_up"),
            ("target_id", "wrong"),
            ("oracle_information_set", None),
        )
        for field, value in mutations:
            with self.subTest(field=field):
                invalid = copy.deepcopy(self.expected_document["rows"][1])
                invalid[field] = value
                with self.assertRaises(OracleValidationError):
                    validate_oracle_target(invalid)

    def test_target_table_preserves_the_visible_anchor(self) -> None:
        invalid = copy.deepcopy(self.expected_document["rows"])
        invalid[2]["last_visible_position_blocks"] = 99.0
        invalid[2]["mu_oracle_blocks"] = 99.1
        validate_oracle_target(invalid[2])
        with self.assertRaisesRegex(OracleValidationError, "most recent visible"):
            validate_oracle_target_rows(invalid)

    def test_builder_does_not_mutate_source_document(self) -> None:
        original = copy.deepcopy(self.state_document)
        build_regime_a_target_document(self.state_document, **self.build_kwargs)
        self.assertEqual(self.state_document, original)

    def test_invalid_parameters_fail_closed(self) -> None:
        with self.assertRaises(OracleValidationError):
            scalar_kalman_posterior(0.0, 1.0, -0.1, 2)
        with self.assertRaises(OracleValidationError):
            scalar_kalman_posterior(0.0, 1.0, 0.1, -1)
        with self.assertRaises(OracleValidationError):
            closed_form_posterior(0.0, 1.0, 0.1, -0.05)
        with self.assertRaises(OracleValidationError):
            closed_form_posterior(math.inf, 1.0, 0.1, 0.05)


if __name__ == "__main__":
    unittest.main()
