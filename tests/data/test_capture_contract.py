"""Tests for the additive Person C C0 capture contract."""

from __future__ import annotations

import json
import math
import unittest
from copy import deepcopy
from pathlib import Path

from mineocclude.contracts.identity import SCHEMA_VERSION
from mineocclude.contracts.trajectory import validate_trajectory_package
from mineocclude.data.capture_contract import (
    PERSON_C_CONTRACT_VERSION,
    CaptureRejectionCode,
    validate_capture_package,
)


ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "person_c" / "episode"
SCHEMA_PATH = ROOT / "schemas" / "person_c" / "capture_v0_1.schema.json"


def load_fixture(filename: str) -> dict:
    """Load one checked synthetic Person C fixture."""

    return json.loads((FIXTURE_DIR / filename).read_text(encoding="utf-8"))


def rejection_codes(result) -> set[CaptureRejectionCode]:
    """Return the stable code set for a validation result."""

    return {rejection.code for rejection in result.rejections}


class TestPersonCCaptureContract(unittest.TestCase):
    """Prove C0 validity, corruption rejection, and non-repair behavior."""

    def test_valid_fixture_passes_c_and_frozen_a_validation(self) -> None:
        package = load_fixture("accepted_episode.json")

        c_result = validate_capture_package(package)
        a_result = validate_trajectory_package(package)

        self.assertTrue(c_result.accepted, c_result.rejections)
        self.assertEqual(c_result.rejections, ())
        self.assertTrue(a_result.accepted, a_result.rejections)
        self.assertEqual(a_result.rejections, ())

    def test_corruptions_fail_for_stable_intended_codes(self) -> None:
        expected = {
            "rejected_missing_action.json": CaptureRejectionCode.MISSING_ACTION,
            "rejected_missing_frame.json": CaptureRejectionCode.MISSING_FRAME,
            "rejected_duplicate_frame.json": CaptureRejectionCode.DUPLICATE_FRAME,
            "rejected_duplicate_state.json": CaptureRejectionCode.DUPLICATE_STATE,
            "rejected_skipped_tick.json": CaptureRejectionCode.SKIPPED_TICK,
            "rejected_mixed_episode_id.json": CaptureRejectionCode.MIXED_EPISODE_ID,
            "rejected_non_monotonic_index.json": (
                CaptureRejectionCode.NON_MONOTONIC_INDEX
            ),
            "rejected_shifted_action.json": CaptureRejectionCode.SHIFTED_ACTION,
            "rejected_invalid_media_metadata.json": (
                CaptureRejectionCode.INVALID_MEDIA_METADATA
            ),
        }

        for filename, code in expected.items():
            with self.subTest(filename=filename, code=code.value):
                result = validate_capture_package(load_fixture(filename))
                self.assertFalse(result.accepted)
                self.assertIn(code, rejection_codes(result))

    def test_validation_never_mutates_or_drops_bad_rows(self) -> None:
        for path in sorted(FIXTURE_DIR.glob("rejected_*.json")):
            with self.subTest(filename=path.name):
                package = load_fixture(path.name)
                before = json.dumps(package, sort_keys=True)
                lengths = {
                    name: len(rows)
                    for name, rows in package["streams"].items()
                }

                result = validate_capture_package(package)

                self.assertFalse(result.accepted)
                self.assertEqual(before, json.dumps(package, sort_keys=True))
                self.assertEqual(
                    lengths,
                    {
                        name: len(rows)
                        for name, rows in package["streams"].items()
                    },
                )

    def test_physical_row_order_does_not_matter(self) -> None:
        package = load_fixture("accepted_episode.json")
        reordered = deepcopy(package)
        for rows in reordered["streams"].values():
            rows.reverse()

        self.assertTrue(validate_capture_package(reordered).accepted)
        self.assertTrue(validate_trajectory_package(reordered).accepted)

    def test_non_monotonic_mapping_is_c_stricter_than_a(self) -> None:
        package = load_fixture("rejected_non_monotonic_index.json")

        c_result = validate_capture_package(package)
        a_result = validate_trajectory_package(package)

        self.assertFalse(c_result.accepted)
        self.assertIn(
            CaptureRejectionCode.NON_MONOTONIC_INDEX,
            rejection_codes(c_result),
        )
        self.assertTrue(a_result.accepted, a_result.rejections)

    def test_noise_schedule_uses_variance_rate_scaling(self) -> None:
        package = load_fixture("accepted_episode.json")
        manifest = package["episode_manifest"]
        expected_std = math.sqrt(manifest["q"] * manifest["dt_seconds"])

        for row in package["streams"]["seed_noise"]:
            self.assertAlmostEqual(row["noise_std_blocks"], expected_std)
            self.assertAlmostEqual(
                row["noise_draw"],
                row["standard_normal_draw"] * expected_std,
            )

    def test_real_capture_cannot_use_unresolved_numpy_pin(self) -> None:
        package = load_fixture("accepted_episode.json")
        package["synthetic"] = False
        package["scientific_use"] = "permitted_after_all_gates"

        result = validate_capture_package(package)

        self.assertFalse(result.accepted)
        self.assertIn(
            CaptureRejectionCode.UNRESOLVED_RUNTIME_PIN,
            rejection_codes(result),
        )

    def test_malformed_exclusion_ledger_fails_closed(self) -> None:
        package = load_fixture("accepted_episode.json")
        package["exclusion_ledger"] = [
            {
                "exclusion_id": "",
                "schema_version": "1.0",
            }
        ]

        result = validate_capture_package(package)

        self.assertFalse(result.accepted)
        self.assertIn(
            CaptureRejectionCode.INVALID_EXCLUSION_LEDGER,
            rejection_codes(result),
        )

    def test_malformed_row_identity_fails_without_crashing(self) -> None:
        package = load_fixture("accepted_episode.json")
        package["streams"]["visibility"][0]["episode_id"] = []
        before = json.dumps(package, sort_keys=True)

        result = validate_capture_package(package)

        self.assertFalse(result.accepted)
        self.assertIn(
            CaptureRejectionCode.MIXED_EPISODE_ID,
            rejection_codes(result),
        )
        self.assertEqual(before, json.dumps(package, sort_keys=True))

    def test_schema_versions_are_additive_and_frozen(self) -> None:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        package = load_fixture("accepted_episode.json")

        self.assertEqual(SCHEMA_VERSION, "1.0")
        self.assertEqual(PERSON_C_CONTRACT_VERSION, "0.1")
        self.assertEqual(schema["properties"]["schema_version"]["const"], "1.0")
        self.assertEqual(
            schema["properties"]["person_c_contract_version"]["const"],
            "0.1",
        )
        self.assertEqual(package["schema_version"], "1.0")
        self.assertEqual(package["person_c_contract_version"], "0.1")

    def test_every_numeric_schema_field_declares_a_unit(self) -> None:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        missing_units: list[str] = []

        def visit(value, path: str) -> None:
            if isinstance(value, dict):
                if value.get("type") in {"integer", "number"} and "x-unit" not in value:
                    missing_units.append(path)
                for key, child in value.items():
                    visit(child, f"{path}/{key}")
            elif isinstance(value, list):
                for index, child in enumerate(value):
                    visit(child, f"{path}/{index}")

        visit(schema, "#")
        self.assertEqual(missing_units, [])


if __name__ == "__main__":
    unittest.main()
