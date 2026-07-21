"""Tests for the universal MineOcclude row identity contract."""

import json
import math
import unittest

from copy import deepcopy
from pathlib import Path

from mineocclude.contracts.identity import (
    FRAME_KEY,
    IdentityValidationError,
    assert_same_key_set,
    assert_trajectory_consistency,
    assert_unique,
    validate_identity,
)


FIXTURE_PATH = (
    Path(__file__).parent.parent
    / "fixtures"
    / "synthetic_identity_rows.jsonl"
)


def load_fixture_rows():
    """Load synthetic universal identity rows."""

    with FIXTURE_PATH.open(
        "r",
        encoding="utf-8",
    ) as file:
        return [
            json.loads(line)
            for line in file
            if line.strip()
        ]


class TestUniversalIdentity(unittest.TestCase):
    """Verify the shared Step 1.2 identity contract."""

    def test_valid_rows_pass(self):
        rows = load_fixture_rows()

        for row in rows:
            validate_identity(row)

    def test_frame_identity_is_unique(self):
        rows = load_fixture_rows()

        assert_unique(
            rows,
            FRAME_KEY,
        )

    def test_duplicate_frame_identity_fails(self):
        rows = load_fixture_rows()

        rows.append(
            deepcopy(rows[0])
        )

        with self.assertRaises(
            IdentityValidationError
        ):
            assert_unique(
                rows,
                FRAME_KEY,
            )

    def test_missing_required_identity_fails(self):
        row = deepcopy(
            load_fixture_rows()[0]
        )

        del row["episode_id"]

        with self.assertRaises(
            IdentityValidationError
        ):
            validate_identity(row)

    def test_excluded_row_requires_reason(self):
        row = deepcopy(
            load_fixture_rows()[0]
        )

        row["status"] = "excluded"
        row["exclusion_reason"] = None

        with self.assertRaises(
            IdentityValidationError
        ):
            validate_identity(row)

    def test_superseded_row_requires_replacement(self):
        row = deepcopy(
            load_fixture_rows()[0]
        )

        row["status"] = "superseded"
        row["superseded_by"] = None

        with self.assertRaises(
            IdentityValidationError
        ):
            validate_identity(row)

    def test_trajectory_identity_must_stay_consistent(self):
        rows = load_fixture_rows()

        rows[1]["episode_id"] = (
            "different_episode"
        )

        with self.assertRaises(
            IdentityValidationError
        ):
            assert_trajectory_consistency(
                rows
            )

    def test_null_condition_value_fails(self):
        row = deepcopy(
            load_fixture_rows()[0]
        )

        row["tau"] = None

        with self.assertRaises(
            IdentityValidationError
        ):
            validate_identity(row)

    def test_non_numeric_condition_fails(self):
        row = deepcopy(
            load_fixture_rows()[0]
        )

        row["v"] = "fast"

        with self.assertRaises(
            IdentityValidationError
        ):
            validate_identity(row)

    def test_non_finite_condition_fails(self):
        row = deepcopy(
            load_fixture_rows()[0]
        )

        row["q"] = math.nan

        with self.assertRaises(
            IdentityValidationError
        ):
            validate_identity(row)

    def test_negative_duration_fails(self):
        row = deepcopy(
            load_fixture_rows()[0]
        )

        row["duration"] = -1

        with self.assertRaises(
            IdentityValidationError
        ):
            validate_identity(row)

    def test_wrong_schema_version_fails(self):
        row = deepcopy(
            load_fixture_rows()[0]
        )

        row["schema_version"] = "0.1-draft"

        with self.assertRaises(
            IdentityValidationError
        ):
            validate_identity(row)

    def test_invalid_hash_format_fails(self):
        row = deepcopy(
            load_fixture_rows()[0]
        )

        row["model_hash"] = "not-a-real-hash"

        with self.assertRaises(
            IdentityValidationError
        ):
            validate_identity(row)

    def test_planned_tables_join_without_row_order(self):
        identities = load_fixture_rows()

        # These tables imitate only the identity portions of the
        # major artifact categories named in Step 1.2.
        #
        # Their full role-specific schemas are intentionally deferred
        # to Steps 1.3 through 1.6.

        frames = [
            {
                **row,
                "synthetic_frame_path":
                    f"frame_{row['render_frame_idx']}.png",
            }
            for row in identities
        ]

        actions = [
            {
                **row,
                "synthetic_action": "noop",
            }
            for row in reversed(identities)
        ]

        states = [
            {
                **row,
                "synthetic_state":
                    row["model_frame_idx"],
            }
            for row in (
                identities[1],
                identities[2],
                identities[0],
            )
        ]

        targets = [
            {
                **row,
                "synthetic_target":
                    float(row["model_frame_idx"]),
            }
            for row in reversed(identities)
        ]

        activations = [
            {
                **row,
                "synthetic_activation_ref":
                    f"activation_{row['model_frame_idx']}",
            }
            for row in identities
        ]

        predictions = [
            {
                **row,
                "synthetic_prediction":
                    float(row["model_frame_idx"]) + 0.1,
            }
            for row in (
                identities[2],
                identities[0],
                identities[1],
            )
        ]

        rollouts = [
            {
                **row,
                "synthetic_rollout":
                    f"rollout_{row['model_frame_idx']}.mp4",
            }
            for row in reversed(identities)
        ]

        planned_tables = (
            actions,
            states,
            targets,
            activations,
            predictions,
            rollouts,
        )

        # Every table must contain exactly the same frame identities,
        # even though their rows appear in different orders.
        for table in planned_tables:
            assert_same_key_set(
                frames,
                table,
                FRAME_KEY,
            )


if __name__ == "__main__":
    unittest.main()