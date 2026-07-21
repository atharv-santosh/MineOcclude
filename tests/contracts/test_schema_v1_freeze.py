"""Tests for the Phase 1 schema v1.0 freeze."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from mineocclude.contracts.identity import SCHEMA_VERSION


ROOT = Path(__file__).resolve().parents[2]


IDENTITY_FIXTURE = (
    ROOT / "tests" / "fixtures" / "synthetic_identity_rows.jsonl"
)


CONTRACT_DOCS = [
    ROOT / "docs" / "contracts" / "identity_v1.md",
    ROOT / "docs" / "contracts" / "trajectory_v1.md",
    ROOT / "docs" / "contracts" / "activation_v1.md",
    ROOT / "docs" / "contracts" / "intervention_request_v1.md",
    ROOT / "docs" / "contracts" / "rollout_registry_v1.md",
]


ACCEPTED_SCHEMA_FILES = [
    ROOT / "tests" / "fixtures" / "trajectory" / "accepted_package.json",
    ROOT
    / "tests"
    / "fixtures"
    / "activation"
    / "accepted_activation_handoff.json",
    ROOT
    / "tests"
    / "fixtures"
    / "intervention"
    / "accepted_intervention_request.json",
    ROOT
    / "tests"
    / "fixtures"
    / "rollout_registry"
    / "accepted_rollout_manifest.json",
    ROOT
    / "tests"
    / "fixtures"
    / "rollout_registry"
    / "accepted_registry.json",
    ROOT
    / "tests"
    / "fixtures"
    / "integration"
    / "synthetic_cross_role_bundle.json",
    ROOT
    / "tests"
    / "fixtures"
    / "integration"
    / "synthetic_token_map.json",
    ROOT
    / "tests"
    / "fixtures"
    / "integration"
    / "synthetic_oracle_targets.json",
    ROOT
    / "tests"
    / "fixtures"
    / "integration"
    / "synthetic_baseline_predictions.json",
    ROOT
    / "tests"
    / "fixtures"
    / "integration"
    / "synthetic_fit_manifest.json",
    ROOT
    / "tests"
    / "fixtures"
    / "integration"
    / "synthetic_validation_manifest.json",
    ROOT
    / "tests"
    / "fixtures"
    / "integration"
    / "synthetic_intervention_request.json",
    ROOT
    / "tests"
    / "fixtures"
    / "integration"
    / "synthetic_input_contexts.json",
    ROOT
    / "tests"
    / "fixtures"
    / "integration"
    / "synthetic_rollout_manifest.json",
    ROOT
    / "tests"
    / "fixtures"
    / "integration"
    / "synthetic_registry.json",
    ROOT
    / "tests"
    / "fixtures"
    / "integration"
    / "synthetic_measurements.json",
    ROOT
    / "tests"
    / "fixtures"
    / "integration"
    / "synthetic_join_report.json",
]


class TestSchemaV1Freeze(unittest.TestCase):
    """Enforce the Phase 1 schema freeze."""

    def test_schema_version_constant_is_frozen_to_v1(self):
        """New Phase 1 evidence must use schema version 1.0."""

        self.assertEqual(
            SCHEMA_VERSION,
            "1.0",
        )

    def test_accepted_fixtures_use_schema_v1(self):
        """Accepted fixtures and integration evidence must use schema v1.0."""

        for path in ACCEPTED_SCHEMA_FILES:
            with self.subTest(path=str(path)):
                document = json.loads(
                    path.read_text(
                        encoding="utf-8",
                    )
                )

                self.assertEqual(
                    document.get("schema_version"),
                    "1.0",
                )

    def test_identity_jsonl_is_bom_free_valid_schema_v1(self):
        """Universal identity evidence must be portable schema-v1 JSONL."""

        raw = IDENTITY_FIXTURE.read_bytes()
        self.assertFalse(raw.startswith(b"\xef\xbb\xbf"))

        lines = raw.decode("utf-8").splitlines()
        self.assertTrue(lines)

        for line_number, line in enumerate(lines, start=1):
            with self.subTest(line_number=line_number):
                row = json.loads(line)
                self.assertEqual(row.get("schema_version"), "1.0")

    def test_contract_docs_describe_current_schema_v1(self):
        """Consumer-facing contract docs must match the frozen validators."""

        for path in CONTRACT_DOCS:
            with self.subTest(path=str(path)):
                text = path.read_text(encoding="utf-8")
                self.assertIn(
                    "Current implementation version: `1.0`",
                    text,
                )
                self.assertNotIn(
                    "Current implementation version: `0.1-draft`",
                    text,
                )

    def test_signed_schema_record_exists(self):
        """The schema freeze must have a signed record."""

        path = (
            ROOT
            / "docs"
            / "contracts"
            / "schema_v1_0_signed_record.md"
        )

        text = path.read_text(
            encoding="utf-8",
        )

        self.assertIn(
            "Schema version: `1.0`",
            text,
        )

        self.assertIn(
            "FROZEN_FOR_PHASE_1",
            text,
        )

        self.assertIn(
            "APPROVED_FOR_PHASE_1_FREEZE",
            text,
        )

        self.assertIn(
            "migration policy",
            text.lower(),
        )

        for section in (
            "authoritative file map",
            "frozen identity and units",
            "frozen allowed values and meanings",
            "filters and exclusion policy",
            "cardinality and join law",
            "rejection policy",
            "approval and sign-off",
        ):
            with self.subTest(section=section):
                self.assertIn(section, text.lower())

    def test_decision_log_exists(self):
        """The schema freeze must have a decision log."""

        path = (
            ROOT
            / "docs"
            / "contracts"
            / "schema_v1_0_decision_log.md"
        )

        text = path.read_text(
            encoding="utf-8",
        )

        self.assertIn(
            "schema-freeze-v1.0-phase-1",
            text,
        )

        self.assertIn(
            "schema_version = 1.0",
            text,
        )

        self.assertIn(
            "APPROVED_FOR_PHASE_1_INTERNAL_SCHEMA_FREEZE",
            text,
        )

        self.assertIn(
            "known step 1.7 orphan-report caveat",
            text.lower(),
        )

    def test_decision_log_records_previous_draft_version(self):
        """The freeze record must preserve migration history from the draft."""

        path = (
            ROOT
            / "docs"
            / "contracts"
            / "schema_v1_0_decision_log.md"
        )

        text = path.read_text(
            encoding="utf-8",
        )

        self.assertIn(
            "0.1-draft",
            text,
        )

        self.assertIn(
            "new schema version",
            text.lower(),
        )

        self.assertIn(
            "new run identity",
            text.lower(),
        )


if __name__ == "__main__":
    unittest.main()
