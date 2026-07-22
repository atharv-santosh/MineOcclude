from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from mineocclude.contracts.rollout_registry import (
    IMMUTABLE_ARTIFACT_TYPES,
    IMMUTABLE_REGISTRY_SCHEMA_VERSION,
    ImmutableRegistryRejectionCode,
    validate_immutable_run_artifact_registry,
    validate_rollout_registry_bundle,
)
from mineocclude.experiments.registry import require_valid_immutable_registry
from tests.experiments.test_registry import registry_bundle


FIXTURE_PATH = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "person_e"
    / "immutable_registry_v1.json"
)

ARTIFACT_BYTES = {
    "artifact_raw_trajectory": b"synthetic raw trajectory v1\n",
    "artifact_model_input": b"synthetic model input v1\n",
    "artifact_activation": b"synthetic activation v1\n",
    "artifact_prediction": b"synthetic prediction v1\n",
    "artifact_metric": b"synthetic metric table v1\n",
}


def registry_fixture() -> dict[str, object]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def rejection_codes(result: object) -> set[ImmutableRegistryRejectionCode]:
    return {rejection.code for rejection in result.rejections}


def superseding_registry() -> dict[str, object]:
    document = registry_fixture()
    prior_run = next(
        run for run in document["runs"] if run["run_id"] == "run_metric"
    )
    corrected_run = copy.deepcopy(prior_run)
    corrected_run.update(
        {
            "run_id": "run_metric_correction",
            "code_sha": "ffffffffffffffffffffffffffffffffffffffff",
            "command": ["synthetic-metric-correction"],
            "started_at": "2026-01-01T00:00:10Z",
            "ended_at": "2026-01-01T00:00:11Z",
            "parent_run_id": "run_metric",
            "output_artifact_ids": ["artifact_metric_corrected"],
            "supersedes_run_id": "run_metric",
            "supersession_reason": "Corrected synthetic metric serialization.",
        }
    )
    document["runs"].append(corrected_run)
    prior_artifact = next(
        artifact
        for artifact in document["artifacts"]
        if artifact["artifact_id"] == "artifact_metric"
    )
    prior_artifact.update(
        {
            "status": "superseded",
            "status_reason": "Replaced by corrected synthetic metric.",
            "superseded_by": "artifact_metric_corrected",
        }
    )
    corrected_artifact = copy.deepcopy(prior_artifact)
    corrected_artifact.update(
        {
            "artifact_id": "artifact_metric_corrected",
            "creator_run_id": "run_metric_correction",
            "sha256": (
                "123aa447e3fd45d749fdabc777e8cfc95e95c141bc1517d8caf4074124b3feac"
            ),
            "size_bytes": 36,
            "status": "accepted",
            "status_reason": None,
            "superseded_by": None,
            "uri": "memory://person-e-phase1/metric-table-corrected",
        }
    )
    document["artifacts"].append(corrected_artifact)
    return document


def in_progress_snapshot() -> dict[str, object]:
    document = registry_fixture()
    run = next(run for run in document["runs"] if run["run_id"] == "run_metric")
    run.update(
        {
            "ended_at": None,
            "status": "in_progress",
            "output_artifact_ids": [],
        }
    )
    document["artifacts"] = [
        artifact
        for artifact in document["artifacts"]
        if artifact["artifact_id"] != "artifact_metric"
    ]
    return document


class TestImmutableRegistryContract(unittest.TestCase):
    def test_valid_synthetic_lineage_and_literal_checksums_pass(self) -> None:
        document = registry_fixture()
        original = copy.deepcopy(document)
        result = validate_immutable_run_artifact_registry(
            document,
            artifact_bytes_by_id=ARTIFACT_BYTES,
        )
        self.assertTrue(result.accepted, result.rejections)
        self.assertEqual(document, original)
        self.assertTrue(document["synthetic"])
        self.assertEqual(document["scientific_use"], "forbidden")
        self.assertEqual(
            document["immutable_registry_schema_version"],
            IMMUTABLE_REGISTRY_SCHEMA_VERSION,
        )
        self.assertTrue(require_valid_immutable_registry(document).accepted)

    def test_identity_and_row_order_are_explicit(self) -> None:
        document = registry_fixture()
        document["runs"].reverse()
        document["artifacts"].reverse()
        self.assertTrue(validate_immutable_run_artifact_registry(document).accepted)

    def test_missing_and_duplicate_run_ids_fail(self) -> None:
        missing = registry_fixture()
        missing["runs"][0].pop("run_id")
        result = validate_immutable_run_artifact_registry(missing)
        self.assertIn(
            ImmutableRegistryRejectionCode.MISSING_RUN_ID,
            rejection_codes(result),
        )
        duplicate = registry_fixture()
        duplicate["runs"].append(copy.deepcopy(duplicate["runs"][0]))
        result = validate_immutable_run_artifact_registry(duplicate)
        self.assertIn(
            ImmutableRegistryRejectionCode.DUPLICATE_RUN_ID,
            rejection_codes(result),
        )

    def test_missing_and_duplicate_artifact_ids_fail(self) -> None:
        missing = registry_fixture()
        missing["artifacts"][0].pop("artifact_id")
        result = validate_immutable_run_artifact_registry(missing)
        self.assertIn(
            ImmutableRegistryRejectionCode.MISSING_ARTIFACT_ID,
            rejection_codes(result),
        )
        duplicate = registry_fixture()
        duplicate["artifacts"].append(copy.deepcopy(duplicate["artifacts"][0]))
        result = validate_immutable_run_artifact_registry(duplicate)
        self.assertIn(
            ImmutableRegistryRejectionCode.DUPLICATE_ARTIFACT_ID,
            rejection_codes(result),
        )

    def test_missing_direct_input_fails(self) -> None:
        document = registry_fixture()
        document["artifacts"][1]["direct_input_artifact_ids"] = ["missing_input"]
        result = validate_immutable_run_artifact_registry(document)
        self.assertIn(
            ImmutableRegistryRejectionCode.BROKEN_DIRECT_INPUT,
            rejection_codes(result),
        )

    def test_missing_creator_run_fails(self) -> None:
        document = registry_fixture()
        document["artifacts"][0]["creator_run_id"] = "missing_run"
        result = validate_immutable_run_artifact_registry(document)
        self.assertIn(
            ImmutableRegistryRejectionCode.MISSING_CREATOR_RUN,
            rejection_codes(result),
        )

    def test_checksum_or_size_mismatch_fails(self) -> None:
        document = registry_fixture()
        result = validate_immutable_run_artifact_registry(
            document,
            artifact_bytes_by_id={
                "artifact_raw_trajectory": b"tampered synthetic trajectory\n"
            },
        )
        self.assertIn(
            ImmutableRegistryRejectionCode.CHECKSUM_MISMATCH,
            rejection_codes(result),
        )

    def test_valid_in_progress_to_completed_transition_passes(self) -> None:
        previous = in_progress_snapshot()
        completed = registry_fixture()
        result = validate_immutable_run_artifact_registry(
            completed, previous_registry=previous
        )
        self.assertTrue(result.accepted, result.rejections)

    def test_valid_in_progress_to_failed_transition_passes(self) -> None:
        previous = in_progress_snapshot()
        failed = copy.deepcopy(previous)
        run = next(run for run in failed["runs"] if run["run_id"] == "run_metric")
        run.update(
            {
                "status": "failed",
                "ended_at": "2026-01-01T00:00:09Z",
                "failure_reason": "Synthetic expected failure.",
            }
        )
        result = validate_immutable_run_artifact_registry(
            failed, previous_registry=previous
        )
        self.assertTrue(result.accepted, result.rejections)

    def test_illegal_terminal_status_transition_fails(self) -> None:
        previous = registry_fixture()
        candidate = in_progress_snapshot()
        result = validate_immutable_run_artifact_registry(
            candidate, previous_registry=previous
        )
        self.assertIn(
            ImmutableRegistryRejectionCode.ILLEGAL_RUN_STATUS_TRANSITION,
            rejection_codes(result),
        )

    def test_completed_run_mutation_fails(self) -> None:
        previous = registry_fixture()
        candidate = copy.deepcopy(previous)
        candidate["runs"][0]["command"] = ["silently-edited-command"]
        result = validate_immutable_run_artifact_registry(
            candidate, previous_registry=previous
        )
        self.assertIn(
            ImmutableRegistryRejectionCode.COMPLETED_RUN_MUTATION,
            rejection_codes(result),
        )

    def test_artifact_content_mutation_fails_across_snapshots(self) -> None:
        previous = registry_fixture()
        candidate = copy.deepcopy(previous)
        candidate["artifacts"][0]["sha256"] = "0" * 64
        result = validate_immutable_run_artifact_registry(
            candidate, previous_registry=previous
        )
        self.assertIn(
            ImmutableRegistryRejectionCode.IMMUTABLE_ARTIFACT_MUTATION,
            rejection_codes(result),
        )

    def test_valid_superseding_run_and_artifact_pass(self) -> None:
        previous = registry_fixture()
        candidate = superseding_registry()
        result = validate_immutable_run_artifact_registry(
            candidate, previous_registry=previous
        )
        self.assertTrue(result.accepted, result.rejections)

    def test_malformed_run_and_artifact_supersession_fail(self) -> None:
        run_document = registry_fixture()
        run_document["runs"][-1].update(
            {
                "supersedes_run_id": "missing_run",
                "supersession_reason": "Claimed correction.",
            }
        )
        result = validate_immutable_run_artifact_registry(run_document)
        self.assertIn(
            ImmutableRegistryRejectionCode.MALFORMED_SUPERSESSION,
            rejection_codes(result),
        )
        artifact_document = registry_fixture()
        artifact_document["artifacts"][-1].update(
            {
                "status": "superseded",
                "status_reason": "Claimed correction.",
                "superseded_by": "missing_artifact",
            }
        )
        result = validate_immutable_run_artifact_registry(artifact_document)
        self.assertIn(
            ImmutableRegistryRejectionCode.MALFORMED_SUPERSESSION,
            rejection_codes(result),
        )

    def test_unversioned_schema_change_fails(self) -> None:
        document = registry_fixture()
        document["runs"][0]["new_unversioned_field"] = "not allowed"
        result = validate_immutable_run_artifact_registry(document)
        self.assertIn(
            ImmutableRegistryRejectionCode.UNVERSIONED_SCHEMA_CHANGE,
            rejection_codes(result),
        )

    def test_unsupported_schema_version_fails(self) -> None:
        document = registry_fixture()
        document["immutable_registry_schema_version"] = "unknown-v2"
        result = validate_immutable_run_artifact_registry(document)
        self.assertIn(
            ImmutableRegistryRejectionCode.UNSUPPORTED_SCHEMA_VERSION,
            rejection_codes(result),
        )

    def test_artifact_catalog_is_closed_and_complete_for_phase1(self) -> None:
        required_types = {
            "raw_trajectory",
            "model_input",
            "oracle_target",
            "activation",
            "fitted_probe",
            "prediction",
            "baseline",
            "rollout",
            "detection",
            "metric_table",
            "figure",
        }
        self.assertLessEqual(required_types, IMMUTABLE_ARTIFACT_TYPES)
        document = registry_fixture()
        document["artifacts"][0]["artifact_type"] = "caller_invented_type"
        result = validate_immutable_run_artifact_registry(document)
        self.assertIn(
            ImmutableRegistryRejectionCode.INVALID_ARTIFACT,
            rejection_codes(result),
        )

    def test_malformed_unhashable_values_reject_without_crashing(self) -> None:
        mutations = (
            lambda document: document.update({"scientific_use": []}),
            lambda document: document["runs"][0].update({"status": []}),
            lambda document: document["artifacts"][0].update(
                {"artifact_type": {"renamed": "raw_trajectory"}}
            ),
            lambda document: document["artifacts"][1].update(
                {"direct_input_artifact_ids": [["artifact_raw_trajectory"]]}
            ),
        )
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                document = registry_fixture()
                mutate(document)
                result = validate_immutable_run_artifact_registry(document)
                self.assertFalse(result.accepted)

    def test_ambiguous_cycle_and_bare_filename_fail(self) -> None:
        cycle = registry_fixture()
        cycle["artifacts"][0]["direct_input_artifact_ids"] = ["artifact_metric"]
        cycle["runs"][0]["input_artifact_ids"] = ["artifact_metric"]
        result = validate_immutable_run_artifact_registry(cycle)
        self.assertIn(
            ImmutableRegistryRejectionCode.AMBIGUOUS_LINEAGE,
            rejection_codes(result),
        )
        filename = registry_fixture()
        filename["artifacts"][0]["uri"] = "raw_trajectory.json"
        result = validate_immutable_run_artifact_registry(filename)
        self.assertIn(
            ImmutableRegistryRejectionCode.INVALID_ARTIFACT,
            rejection_codes(result),
        )

    def test_existing_a_rollout_registry_behavior_still_passes(self) -> None:
        manifest, registry = registry_bundle()
        self.assertTrue(
            validate_rollout_registry_bundle(manifest, registry).accepted
        )


if __name__ == "__main__":
    unittest.main()
