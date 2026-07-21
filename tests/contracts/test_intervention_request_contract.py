"""Tests for the MineOcclude B→A intervention-request contract."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from mineocclude.contracts.intervention_request import (
    InterventionRejectionCode,
    validate_intervention_request,
)


FIXTURE_DIR = (
    Path(__file__).parent.parent
    / "fixtures"
    / "intervention"
)


def load_fixture(filename: str) -> dict:
    """Load one Step 1.5 fixture."""

    path = FIXTURE_DIR / filename

    with path.open(
        "r",
        encoding="utf-8",
    ) as file:
        return json.load(file)


def rejection_codes(
    result,
) -> set[InterventionRejectionCode]:
    """Return all rejection codes from a validation result."""

    return {
        rejection.code
        for rejection in result.rejections
    }


class TestInterventionRequestContract(
    unittest.TestCase
):
    """Verify the Step 1.5 B→A intervention contract."""

    def test_accepted_request_passes(self):
        request = load_fixture(
            "accepted_intervention_request.json"
        )

        result = validate_intervention_request(
            request
        )

        self.assertTrue(
            result.accepted
        )

        self.assertEqual(
            result.rejections,
            (),
        )

    def test_standardized_direction_is_rejected(self):
        request = load_fixture(
            "rejected_standardized_direction.json"
        )

        result = validate_intervention_request(
            request
        )

        codes = rejection_codes(
            result
        )

        self.assertFalse(
            result.accepted
        )

        self.assertIn(
            InterventionRejectionCode.DIRECTION_NOT_RAW_SPACE,
            codes,
        )

        self.assertIn(
            InterventionRejectionCode.RAW_SPACE_EQUIVALENCE_UNVERIFIED,
            codes,
        )

    def test_test_selected_direction_is_rejected(self):
        request = load_fixture(
            "rejected_test_selected_direction.json"
        )

        result = validate_intervention_request(
            request
        )

        self.assertFalse(
            result.accepted
        )

        self.assertIn(
            InterventionRejectionCode.TEST_SELECTED_DIRECTION,
            rejection_codes(result),
        )

    def test_near_zero_direction_is_rejected(self):
        request = load_fixture(
            "rejected_near_zero_direction.json"
        )

        result = validate_intervention_request(
            request
        )

        self.assertFalse(
            result.accepted
        )

        self.assertIn(
            InterventionRejectionCode.NEAR_ZERO_RESIDUAL_DIRECTION,
            rejection_codes(result),
        )

    def test_non_unit_direction_is_rejected(self):
        request = load_fixture(
            "rejected_non_unit_direction.json"
        )

        result = validate_intervention_request(
            request
        )

        self.assertFalse(
            result.accepted
        )

        self.assertIn(
            InterventionRejectionCode.DIRECTION_NOT_UNIT_NORM,
            rejection_codes(result),
        )

    def test_incomplete_request_is_rejected(self):
        request = load_fixture(
            "rejected_incomplete_request.json"
        )

        result = validate_intervention_request(
            request
        )

        self.assertFalse(
            result.accepted
        )

        self.assertIn(
            InterventionRejectionCode.MISSING_REQUIRED_FIELD,
            rejection_codes(result),
        )

    def test_data_split_overlap_is_rejected(self):
        request = load_fixture(
            "rejected_split_overlap.json"
        )

        result = validate_intervention_request(
            request
        )

        self.assertFalse(
            result.accepted
        )

        self.assertIn(
            InterventionRejectionCode.DATA_SPLIT_OVERLAP,
            rejection_codes(result),
        )

    def test_invalid_cap_reduction_is_rejected(self):
        request = load_fixture(
            "rejected_cap_reduction.json"
        )

        result = validate_intervention_request(
            request
        )

        self.assertFalse(
            result.accepted
        )

        self.assertIn(
            InterventionRejectionCode.CAP_REDUCTION_MISMATCH,
            rejection_codes(result),
        )

    def test_cap_flag_mismatch_is_rejected(self):
        request = load_fixture(
            "rejected_cap_flag_mismatch.json"
        )

        result = validate_intervention_request(
            request
        )

        self.assertFalse(
            result.accepted
        )

        self.assertIn(
            InterventionRejectionCode.CAP_REDUCTION_MISMATCH,
            rejection_codes(result),
        )

    def test_unflagged_alpha_reduction_is_rejected(self):
        request = load_fixture(
            "rejected_unflagged_alpha_reduction.json"
        )

        result = validate_intervention_request(
            request
        )

        self.assertFalse(
            result.accepted
        )

        self.assertIn(
            InterventionRejectionCode.CAP_REDUCTION_MISMATCH,
            rejection_codes(result),
        )

    def test_applied_alpha_exceeding_cap_is_rejected(self):
        request = load_fixture(
            "rejected_alpha_exceeds_cap.json"
        )

        result = validate_intervention_request(
            request
        )

        self.assertFalse(
            result.accepted
        )

        self.assertIn(
            InterventionRejectionCode.ALPHA_EXCEEDS_CAP,
            rejection_codes(result),
        )

    def test_alpha_sign_reversal_is_rejected(self):
        request = load_fixture(
            "rejected_alpha_sign_reversal.json"
        )

        result = validate_intervention_request(
            request
        )

        self.assertFalse(
            result.accepted
        )

        self.assertIn(
            InterventionRejectionCode.ALPHA_SIGN_REVERSAL,
            rejection_codes(result),
        )

    def test_extreme_finite_direction_rejects_without_crashing(self):
        request = load_fixture(
            "rejected_extreme_direction.json"
        )

        result = validate_intervention_request(
            request
        )

        self.assertFalse(
            result.accepted
        )

        self.assertIn(
            InterventionRejectionCode.INVALID_DIRECTION,
            rejection_codes(result),
        )

    def test_validator_does_not_mutate_request(self):
        request = load_fixture(
            "rejected_standardized_direction.json"
        )

        before = json.dumps(
            request,
            sort_keys=True,
        )

        validate_intervention_request(
            request
        )

        after = json.dumps(
            request,
            sort_keys=True,
        )

        self.assertEqual(
            before,
            after,
        )


if __name__ == "__main__":
    unittest.main()