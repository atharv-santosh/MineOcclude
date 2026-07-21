"""Tests for the Step 1.6 A-to-E rollout and A/E registry contract."""

from __future__ import annotations

import json
import unittest
from copy import deepcopy
from pathlib import Path

from mineocclude.contracts.rollout_registry import (
    RolloutRegistryRejectionCode,
    validate_rollout_registry_bundle,
)


FIXTURE_DIR = (
    Path(__file__).parent.parent
    / "fixtures"
    / "rollout_registry"
)


def load_fixture(filename: str) -> dict:
    """Load one Step 1.6 JSON fixture."""

    with (FIXTURE_DIR / filename).open("r", encoding="utf-8") as file:
        return json.load(file)


def load_accepted_bundle() -> tuple[dict, dict]:
    """Load the separately handed-off accepted files."""

    return (
        load_fixture("accepted_rollout_manifest.json"),
        load_fixture("accepted_registry.json"),
    )


def validate_rejected_fixture(filename: str):
    """Validate one rejected bundle fixture."""

    bundle = load_fixture(filename)
    return validate_rollout_registry_bundle(
        bundle["rollout_manifest"],
        bundle["registry"],
    )


def rejection_codes(result) -> set[RolloutRegistryRejectionCode]:
    """Return the machine-readable codes from one result."""

    return {rejection.code for rejection in result.rejections}


class TestRolloutRegistryContract(unittest.TestCase):
    """Verify Step 1.6 outcomes, lifecycle, and provenance joins."""

    def assert_fixture_has_code(
        self,
        filename: str,
        expected: RolloutRegistryRejectionCode,
    ) -> None:
        """Assert that an invalid fixture fails for its intended reason."""

        result = validate_rejected_fixture(filename)
        self.assertFalse(result.accepted)
        self.assertIn(expected, rejection_codes(result))

    def test_accepted_manifest_and_registry_pass(self):
        manifest, registry = load_accepted_bundle()

        result = validate_rollout_registry_bundle(manifest, registry)

        self.assertTrue(result.accepted)
        self.assertEqual(result.rejections, ())

    def test_fixtures_are_explicitly_synthetic_and_non_scientific(self):
        manifest, registry = load_accepted_bundle()

        for document in (manifest, registry):
            self.assertEqual(
                document["fixture_metadata"],
                {"synthetic": True, "scientific_use": "forbidden"},
            )

    def test_person_e_can_classify_every_rollout_without_inference(self):
        manifest, _ = load_accepted_bundle()
        rows = {row["outcome"]: row for row in manifest["rollout_rows"]}

        self.assertEqual(
            set(rows),
            {
                "measurable_continuation",
                "non_persistence",
                "generation_failure",
            },
        )
        self.assertTrue(rows["measurable_continuation"]["measurable"])
        self.assertFalse(rows["non_persistence"]["measurable"])
        self.assertFalse(rows["generation_failure"]["measurable"])
        self.assertIsNotNone(rows["non_persistence"]["output_artifact_id"])
        self.assertIsNone(rows["generation_failure"]["output_artifact_id"])

        for row in rows.values():
            self.assertNotIn("measured_displacement", row)
            self.assertNotIn("displacement_blocks", row)

    def test_every_rollout_traces_to_its_run_and_direct_inputs(self):
        manifest, registry = load_accepted_bundle()
        runs = {run["run_id"]: run for run in registry["runs"]}

        for row in manifest["rollout_rows"]:
            producing_run = runs[row["run_id"]]
            self.assertIn(
                row["input_context_artifact_id"],
                producing_run["input_artifact_ids"],
            )
            self.assertIn(
                row["intervention_request_artifact_id"],
                producing_run["input_artifact_ids"],
            )
            if row["output_artifact_id"] is not None:
                self.assertIn(
                    row["output_artifact_id"],
                    producing_run["output_artifact_ids"],
                )

    def test_every_artifact_traces_to_exactly_one_producing_run(self):
        _, registry = load_accepted_bundle()
        runs = {run["run_id"]: run for run in registry["runs"]}

        for artifact in registry["artifacts"]:
            producer = runs[artifact["producer_run_id"]]
            self.assertIn(artifact["artifact_id"], producer["output_artifact_ids"])
            self.assertEqual(len(artifact["sha256"]), 64)

    def test_registry_exercises_all_lifecycle_states_and_supersession(self):
        _, registry = load_accepted_bundle()
        artifacts = {
            artifact["artifact_id"]: artifact
            for artifact in registry["artifacts"]
        }

        self.assertEqual(
            {artifact["status"] for artifact in artifacts.values()},
            {"accepted", "excluded", "superseded"},
        )
        superseded = next(
            artifact
            for artifact in artifacts.values()
            if artifact["status"] == "superseded"
        )
        replacement = artifacts[superseded["superseded_by"]]
        self.assertEqual(superseded["artifact_type"], replacement["artifact_type"])

    def test_parent_run_lineage_reaches_an_auditable_root(self):
        _, registry = load_accepted_bundle()
        parents = {
            run["run_id"]: run["parent_run_id"]
            for run in registry["runs"]
        }

        for run_id in parents:
            visited = set()
            current = run_id
            while current is not None:
                self.assertNotIn(current, visited)
                visited.add(current)
                current = parents[current]

    def test_filename_cannot_replace_event_identity(self):
        self.assert_fixture_has_code(
            "rejected_filename_only_identity.json",
            RolloutRegistryRejectionCode.INVALID_ROLLOUT_ROW,
        )

    def test_missing_universal_identity_is_rejected(self):
        self.assert_fixture_has_code(
            "rejected_universal_identity.json",
            RolloutRegistryRejectionCode.INVALID_ROLLOUT_ROW,
        )

    def test_generation_failure_cannot_encode_zero_displacement(self):
        self.assert_fixture_has_code(
            "rejected_generation_failure_as_zero.json",
            RolloutRegistryRejectionCode.DISPLACEMENT_ENCODING_FORBIDDEN,
        )

    def test_non_persistence_cannot_encode_zero_displacement(self):
        self.assert_fixture_has_code(
            "rejected_non_persistence_as_zero.json",
            RolloutRegistryRejectionCode.DISPLACEMENT_ENCODING_FORBIDDEN,
        )

    def test_bare_filename_is_not_an_output_uri_or_identity(self):
        self.assert_fixture_has_code(
            "rejected_bare_filename_uri.json",
            RolloutRegistryRejectionCode.INVALID_URI,
        )

    def test_non_persistence_cannot_be_conflated_with_generation_failure(self):
        self.assert_fixture_has_code(
            "rejected_outcome_conflation.json",
            RolloutRegistryRejectionCode.OUTCOME_OUTPUT_MISMATCH,
        )

    def test_missing_run_lineage_is_rejected(self):
        self.assert_fixture_has_code(
            "rejected_missing_run_lineage.json",
            RolloutRegistryRejectionCode.MISSING_REGISTRY_REFERENCE,
        )

    def test_invalid_artifact_supersession_is_rejected(self):
        self.assert_fixture_has_code(
            "rejected_invalid_supersession.json",
            RolloutRegistryRejectionCode.INVALID_SUPERSESSION,
        )

    def test_parent_run_cycle_is_rejected(self):
        self.assert_fixture_has_code(
            "rejected_parent_cycle.json",
            RolloutRegistryRejectionCode.INVALID_PARENT_LINEAGE,
        )

    def test_malformed_nested_types_are_rejected_without_crashing(self):
        self.assert_fixture_has_code(
            "rejected_malformed_types.json",
            RolloutRegistryRejectionCode.INVALID_OUTCOME,
        )

    def test_inconsistent_artifact_lifecycle_is_rejected(self):
        self.assert_fixture_has_code(
            "rejected_artifact_lifecycle.json",
            RolloutRegistryRejectionCode.INVALID_LIFECYCLE,
        )

    def test_cross_record_metadata_mismatch_is_rejected(self):
        self.assert_fixture_has_code(
            "rejected_metadata_mismatch.json",
            RolloutRegistryRejectionCode.METADATA_MISMATCH,
        )

    def test_duplicate_rollout_identity_is_rejected(self):
        self.assert_fixture_has_code(
            "rejected_duplicate_rollout_id.json",
            RolloutRegistryRejectionCode.DUPLICATE_ROLLOUT_ID,
        )

    def test_validator_rejects_non_mapping_documents_without_crashing(self):
        result = validate_rollout_registry_bundle([], "registry")

        self.assertFalse(result.accepted)
        self.assertEqual(
            rejection_codes(result),
            {RolloutRegistryRejectionCode.MISSING_REQUIRED_FIELD},
        )

    def test_validator_does_not_mutate_submitted_documents(self):
        manifest, registry = load_accepted_bundle()
        manifest_before = deepcopy(manifest)
        registry_before = deepcopy(registry)

        validate_rollout_registry_bundle(manifest, registry)

        self.assertEqual(manifest, manifest_before)
        self.assertEqual(registry, registry_before)


if __name__ == "__main__":
    unittest.main()
