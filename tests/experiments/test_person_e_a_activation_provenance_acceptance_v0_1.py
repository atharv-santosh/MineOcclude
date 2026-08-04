"""Focused provenance/schema/inventory/receipt tests for Person E acceptance."""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import build_person_e_a_activation_provenance_acceptance_v0_1 as mod


PACKAGE = ROOT / mod.PACKAGE_REL
RECEIPT_NAME = "person_e_to_person_a_activation_provenance_receipt.json"


def load(name: str):
    return json.loads((PACKAGE / name).read_bytes())


def test_provenance_binds_exact_person_a_result_to_canonical_c6a():
    receipt = load(RECEIPT_NAME)
    result = receipt["person_a_result"]
    c6a = receipt["canonical_c6a_binding"]
    assert result["canonical_result_commit"] == mod.PERSON_A_COMMIT
    assert result["producing_runtime_commit"] == mod.PERSON_A_RUNTIME_COMMIT
    assert result["output_bundle_sha256"] == mod.OUTPUT_BUNDLE_SHA256
    assert result["a_to_e_handoff_sha256"] == mod.A_TO_E_HANDOFF_SHA256
    assert result["accepted_manifest_sha256"] == mod.ACCEPTED_MANIFEST_SHA256
    assert c6a["canonical_c6a_id"] == "person-c-c6a-post-c1-v0.1"
    assert c6a["trajectory_id"] == mod.TRAJECTORY_ID
    assert c6a["episode_id"] == mod.EPISODE_ID
    assert c6a["person_e_registry_record_sha256"] == mod.PRIOR_E_RECORD_SHA256


def test_activation_receipt_has_exact_schema_counts_and_pipeline_identities():
    receipt = load(RECEIPT_NAME)
    activation = receipt["activation_provenance"]
    assert activation["activation_row_count"] == 1200
    assert activation["activation_chunk_count"] == 20
    assert len(activation["activation_chunks"]) == 20
    assert {row["layer_idx"] for row in activation["activation_chunks"]} == set(range(20))
    assert sum(row["row_count"] for row in activation["activation_chunks"]) == 1200
    assert activation["activation_index"]["sha256"] == mod.ACTIVATION_INDEX_SHA256
    assert activation["model_sha256"] == mod.MODEL_SHA256
    assert activation["model_config_sha256"] == mod.MODEL_CONFIG_SHA256
    assert activation["preprocessing"] == mod.PREPROCESSING
    assert activation["action_conversion"] == mod.ACTION_CONVERSION
    assert activation["hook_site"] == mod.HOOK_SITE
    assert activation["pooling_method"] == "mean"
    assert activation["storage_format"] == "person-a-activation-store-v2"


def test_receipt_accepts_audits_authorizes_a6_6_and_preserves_history():
    receipt = load(RECEIPT_NAME)
    validation = receipt["validation"]
    assert all(validation.values())
    assert receipt["status"] == "READY_FOR_A6_6_PROVENANCE_CONSUMPTION"
    assert receipt["a6_6_provenance_consumption_authorized"] is True
    assert receipt["a6_6_provenance_consumption_statement"] == mod.A6_6_STATEMENT
    assert receipt["a6_6_performed"] is False
    assert receipt["unresolved_blockers"] == []
    assert receipt["historical_preservation"]["existing_person_e_records_modified"] is False
    assert receipt["historical_preservation"]["prior_c6a_records_modified"] is False
    assert receipt["activation_provenance"]["direct_pooling_audit"]["maximum_repeatability_difference"] == 0.0
    assert receipt["activation_provenance"]["source_identity_join"]["failure_count"] == 0


def test_schema_inventory_and_generated_receipt_are_exact():
    mod.validate_package(PACKAGE)
    schema = load("person_e_to_person_a_activation_provenance_receipt.schema.json")
    receipt = load(RECEIPT_NAME)
    mod.validate_receipt_schema(receipt, schema)
    inventory = load("sha256_inventory.json")
    assert inventory["inventory_excludes_self"] is True
    assert inventory["file_count"] == 4
    assert {row["path"] for row in inventory["files"]} == {
        RECEIPT_NAME,
        "person_e_to_person_a_activation_provenance_receipt.schema.json",
        "validation_receipt.json",
    }
