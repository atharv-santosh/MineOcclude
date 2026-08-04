"""Focused tests for the canonical post-C1 C6A provenance closure."""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import build_person_e_c6a_provenance_closure_v0_1 as mod


PACKAGE = ROOT / mod.PACKAGE_REL


def load(name: str):
    return json.loads((PACKAGE / name).read_bytes())


def test_certified_c6a_identity_and_all_66_episode_records_are_closed():
    receipt = load("provenance_receipt.json")
    registry = load("canonical_registry_records.json")
    assert receipt["canonical_c6a_id"] == mod.CANONICAL_C6A_ID
    assert receipt["person_c_certification_commit"] == mod.PERSON_C_COMMIT
    assert receipt["person_c_c6a_package"]["sha256"] == mod.C_PACKAGE_SHA256
    assert receipt["person_c_c6a_handoff"]["sha256"] == mod.C_HANDOFF_SHA256
    assert receipt["valid_episode_count"] == mod.EXPECTED_EPISODE_COUNT
    assert registry["record_count"] == mod.EXPECTED_EPISODE_COUNT
    assert len(registry["records"]) == mod.EXPECTED_EPISODE_COUNT
    assert len(registry["record_index"]) == mod.EXPECTED_EPISODE_COUNT


def test_every_output_is_bound_to_all_required_provenance_fields():
    registry = load("canonical_registry_records.json")
    required_record_fields = {
        "canonical_c6a_id",
        "episode_id",
        "layout_id",
        "seed",
        "noise_schedule",
        "accepted_geometry",
        "homography",
        "repaired_jar_sha256",
        "outputs",
    }
    required_output_fields = {
        "path",
        "sha256",
        "expected_schema_id",
        "expected_record_count",
    }
    assert registry["total_output_file_count"] == 2930
    assert sum(len(row["outputs"]) for row in registry["records"]) == 2930
    for record in registry["records"]:
        assert required_record_fields <= record.keys()
        assert record["canonical_c6a_id"] == mod.CANONICAL_C6A_ID
        assert record["accepted_geometry"] == {
            "sha256": mod.ACCEPTED_GEOMETRY_SHA256,
            "version": mod.ACCEPTED_GEOMETRY_VERSION,
        }
        assert record["homography"]["person_e_refit_package_sha256"] == mod.E_PACKAGE_SHA256
        assert record["homography"]["person_e_refit_handoff_sha256"] == mod.E_HANDOFF_SHA256
        assert record["repaired_jar_sha256"] == mod.REPAIRED_JAR_SHA256
        assert record["byte_hashes_valid"] is True
        assert record["output_schemas_valid"] is True
        assert record["output_counts_valid"] is True
        for output in record["outputs"]:
            assert required_output_fields <= output.keys()
            assert len(output["sha256"]) == 64
            assert output["expected_record_count"] > 0


def test_registry_record_identities_are_complete_and_hash_exactly():
    registry = load("canonical_registry_records.json")
    by_id = {row["registry_record_id"]: row for row in registry["records"]}
    assert len(by_id) == mod.EXPECTED_EPISODE_COUNT
    for identity in registry["record_index"]:
        record = by_id[identity["registry_record_id"]]
        assert identity["episode_id"] == record["episode_id"]
        assert identity["registry_record_sha256"] == mod.sha256_bytes(
            mod.canonical_json(record)
        )


def test_e_refit_geometry_receipt_and_a_facing_handoff_are_exact():
    receipt = load("provenance_receipt.json")
    handoff = load("person_e_to_person_a_c6a_provenance_handoff.json")
    assert receipt["person_e_refit_commit"] == mod.PERSON_E_REFIT_COMMIT
    assert receipt["person_e_refit_package"]["sha256"] == mod.E_PACKAGE_SHA256
    assert receipt["person_e_refit_handoff"]["sha256"] == mod.E_HANDOFF_SHA256
    assert handoff["provenance_receipt"]["sha256"] == mod.sha256_bytes(
        (PACKAGE / "provenance_receipt.json").read_bytes()
    )
    assert handoff["a6_6_provenance_consumption_authorized"] is True
    assert handoff["a6_6_provenance_consumption_statement"] == mod.A6_6_STATEMENT
    assert handoff["a6_6_performed"] is False
    assert handoff["unresolved_blockers"] == []


def test_e4_1_completion_is_gated_by_passing_registry_and_provenance():
    status = load("e4_1_status.json")
    validation = load("validation_receipt.json")
    assert status["repository_registry_requirements_pass"] is True
    assert status["canonical_registry_records_complete"] is True
    assert status["e4_1_complete"] is True
    assert validation["canonical_registry_records_complete"] is True
    assert validation["e4_1_complete"] is True
    assert validation["status"] == "PASS"


def test_package_is_canonical_and_inventory_complete():
    mod.validate_package(PACKAGE)


def test_historical_authorities_are_declared_unchanged():
    receipt = load("provenance_receipt.json")
    preservation = receipt["historical_preservation"]
    assert preservation["existing_registry_entries_modified"] is False
    assert preservation["old_homographies_modified"] is False
    assert preservation["historical_pilots_modified"] is False
    assert preservation["failed_calibrations_modified"] is False
    assert preservation["failed_closed_packages_modified"] is False
    assert len(preservation["person_e_v0_1_handoff"]["sha256"]) == 64
    assert len(preservation["person_e_v0_1_package"]["sha256"]) == 64
