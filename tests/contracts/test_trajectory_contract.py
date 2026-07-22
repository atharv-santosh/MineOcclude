"""Tests for the MineOcclude C→A trajectory contract."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from mineocclude.contracts.trajectory import (
    RejectionCode,
    validate_trajectory_package,
)


FIXTURE_DIR = (
    Path(__file__).parent.parent
    / "fixtures"
    / "trajectory"
)


def load_fixture(filename: str) -> dict:
    """Load one synthetic trajectory-package fixture."""

    path = FIXTURE_DIR / filename

    with path.open(
        "r",
        encoding="utf-8",
    ) as file:
        return json.load(file)


def rejection_codes(result) -> set[RejectionCode]:
    """Return all rejection codes from one validation result."""

    return {
        rejection.code
        for rejection in result.rejections
    }


class TestTrajectoryContract(unittest.TestCase):
    """Verify the Step 1.3 C→A trajectory contract."""

    def test_accepted_package_passes(self):
        package = load_fixture(
            "accepted_package.json"
        )

        result = validate_trajectory_package(
            package
        )

        self.assertTrue(
            result.accepted
        )

        self.assertEqual(
            result.rejections,
            (),
        )

    def test_cardinality_mismatch_fails_for_expected_reason(self):
        package = load_fixture(
            "rejected_cardinality.json"
        )

        result = validate_trajectory_package(
            package
        )

        self.assertFalse(
            result.accepted
        )

        self.assertIn(
            RejectionCode.CARDINALITY_MISMATCH,
            rejection_codes(result),
        )

    def test_nonconsecutive_tick_fails_for_expected_reason(self):
        package = load_fixture(
            "rejected_nonconsecutive_tick.json"
        )

        result = validate_trajectory_package(
            package
        )

        self.assertFalse(
            result.accepted
        )

        self.assertIn(
            RejectionCode.NON_CONSECUTIVE_SERVER_TICKS,
            rejection_codes(result),
        )

    def test_duplicate_identity_fails_for_expected_reason(self):
        package = load_fixture(
            "rejected_duplicate_identity.json"
        )

        result = validate_trajectory_package(
            package
        )

        self.assertFalse(
            result.accepted
        )

        self.assertIn(
            RejectionCode.DUPLICATE_IDENTITY,
            rejection_codes(result),
        )

    def test_unverified_impulse_orientation_fails_for_expected_reason(self):
        package = load_fixture(
            "rejected_impulse_orientation.json"
        )

        result = validate_trajectory_package(
            package
        )

        self.assertFalse(
            result.accepted
        )

        self.assertIn(
            RejectionCode.IMPULSE_ORIENTATION_UNVERIFIED,
            rejection_codes(result),
        )

    def test_mismatched_stream_identity_is_rejected(self):
        package = load_fixture(
            "rejected_mismatched_stream_identity.json"
        )

        result = validate_trajectory_package(
            package
        )

        self.assertFalse(
            result.accepted
        )

        self.assertIn(
            RejectionCode.IDENTITY_MISMATCH,
            rejection_codes(result),
        )

    def test_invalid_identity_type_is_rejected(self):
        package = load_fixture(
            "rejected_invalid_identity_type.json"
        )

        result = validate_trajectory_package(
            package
        )

        self.assertFalse(
            result.accepted
        )

        self.assertIn(
            RejectionCode.INVALID_IDENTITY_TYPE,
            rejection_codes(result),
        )

    def test_invalid_normalized_action_payload_is_rejected(self):
        package = load_fixture(
            "rejected_invalid_payload.json"
        )

        result = validate_trajectory_package(
            package
        )

        self.assertFalse(
            result.accepted
        )

        self.assertIn(
            RejectionCode.INVALID_ROW_PAYLOAD,
            rejection_codes(result),
        )

    def test_malformed_media_returns_rejection_instead_of_crashing(self):
        package = load_fixture(
            "rejected_malformed_media.json"
        )

        result = validate_trajectory_package(
            package
        )

        self.assertFalse(
            result.accepted
        )

        self.assertIn(
            RejectionCode.INVALID_MEDIA_SPEC,
            rejection_codes(result),
        )

    def test_invalid_server_state_is_rejected(self):
        package = load_fixture(
            "rejected_invalid_state.json"
        )

        result = validate_trajectory_package(
            package
        )

        self.assertFalse(
            result.accepted
        )

        self.assertIn(
            RejectionCode.INVALID_ROW_PAYLOAD,
            rejection_codes(result),
        )

    def test_invalid_client_tick_is_rejected(self):
        package = load_fixture(
            "rejected_invalid_client_tick.json"
        )

        result = validate_trajectory_package(
            package
        )

        self.assertFalse(
            result.accepted
        )

        self.assertIn(
            RejectionCode.INVALID_ROW_PAYLOAD,
            rejection_codes(result),
        )

    def test_validator_does_not_mutate_package(self):
        package = load_fixture(
            "rejected_cardinality.json"
        )

        original = json.dumps(
            package,
            sort_keys=True,
        )

        validate_trajectory_package(
            package
        )

        after = json.dumps(
            package,
            sort_keys=True,
        )

        self.assertEqual(
            original,
            after,
        )

    def test_each_stream_matches_frame_map_identity(self):
        package = load_fixture(
            "accepted_package.json"
        )

        frame_map = package[
            "streams"
        ][
            "frame_map"
        ]

        identity_fields = (
            "episode_id",
            "trajectory_id",
            "server_tick",
            "render_frame_idx",
            "action_idx",
            "model_frame_idx",
        )

        frame_keys = {
            tuple(
                row[field]
                for field in identity_fields
            )
            for row in frame_map
        }

        for stream_name, rows in package[
            "streams"
        ].items():
            stream_keys = {
                tuple(
                    row[field]
                    for field in identity_fields
                )
                for row in rows
            }

            self.assertEqual(
                frame_keys,
                stream_keys,
                msg=(
                    f"{stream_name} does not match "
                    "frame_map identities."
                ),
            )


if __name__ == "__main__":
    unittest.main()