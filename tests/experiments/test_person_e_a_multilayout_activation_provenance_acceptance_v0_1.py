"""Focused collection/provenance/schema/inventory tests for successor acceptance."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import build_person_e_a_multilayout_activation_provenance_acceptance_v0_1 as mod


PACKAGE = ROOT / mod.PACKAGE_REL


def load(name: str):
    return json.loads((PACKAGE / name).read_bytes())


def test_receipt_binds_exact_successor_collection_and_authoritative_order():
    receipt = load(mod.RECEIPT_NAME)
    collection = receipt["collection_identity"]
    assert receipt["person_a_result"]["producing_successor_commit"] == mod.PERSON_A_COMMIT
    assert collection["collection_manifest_sha256"] == mod.COLLECTION_MANIFEST_SHA256
    assert collection["a_to_e_handoff_sha256"] == mod.A_TO_E_HANDOFF_SHA256
    assert collection["layout_count"] == 5
    assert collection["trajectory_count"] == 5
    assert collection["activation_index_count"] == 5
    assert collection["activation_row_count"] == 6000
    assert collection["activation_chunk_count"] == 100
    assert collection["source_frame_count"] == 300
    assert collection["trajectory_ids"] == [row[1] for row in mod.TRAJECTORIES]
    assert collection["layout_ids"] == [row[0] for row in mod.TRAJECTORIES]
    assert [row["activation_index_sha256"] for row in collection["logical_order"]] == (
        mod.ACTIVATION_INDEX_SHA256S
    )


def test_all_run_artifacts_and_canonical_c6a_records_are_bound():
    receipt = load(mod.RECEIPT_NAME)
    activation = receipt["activation_provenance"]
    runs = activation["per_run"]
    assert len(runs) == 5
    assert [row["trajectory_id"] for row in runs] == [row[1] for row in mod.TRAJECTORIES]
    assert [row["layout_id"] for row in runs] == [row[0] for row in mod.TRAJECTORIES]
    assert [row["episode_id"] for row in runs] == [row[2] for row in mod.TRAJECTORIES]
    assert len(activation["activation_indexes"]) == 5
    assert [row["sha256"] for row in activation["activation_indexes"]] == (
        mod.ACTIVATION_INDEX_SHA256S
    )
    assert len(activation["activation_chunks"]) == 100
    assert sum(row["row_count"] for row in activation["activation_chunks"]) == 6000
    assert len(receipt["canonical_c6a_binding"]["registry_records"]) == 5
    assert receipt["canonical_c6a_binding"]["canonical_c6a_id"] == mod.CANONICAL_C6A_ID


def test_model_pipeline_audits_repeatability_and_source_joins_are_exact():
    activation = load(mod.RECEIPT_NAME)["activation_provenance"]
    identities = activation["identities"]
    assert identities["model_sha256"] == mod.MODEL_SHA256
    assert identities["checkpoint_sha256"] == mod.MODEL_SHA256
    assert identities["model_config_sha256"] == mod.MODEL_CONFIG_SHA256
    assert identities["preprocessing"] == mod.PREPROCESSING
    assert identities["action_conversion"] == mod.ACTION_CONVERSION
    assert identities["hook_site"] == mod.HOOK_SITE
    assert identities["pooling_method"] == "mean"
    assert identities["token_region"] == "visual"
    assert identities["activation_store_format"] == "person-a-activation-store-v2"
    assert identities["activation_index_format"] == "person-a-activation-index-v2"
    assert len(activation["direct_pooling_audits"]) == 5
    assert all(row["status"] == "PASS" for row in activation["direct_pooling_audits"])
    assert all(row["status"] == "PASS" for row in activation["repeatability_checks"])
    assert all(row["maximum_absolute_difference"] == 0.0 for row in activation["repeatability_checks"])
    assert all(row["status"] == "PASS" for row in activation["source_identity_joins"])
    assert all(row["failure_count"] == 0 for row in activation["source_identity_joins"])


def test_successor_authorizes_a6_6_and_preserves_single_layout_predecessor():
    receipt = load(mod.RECEIPT_NAME)
    history = receipt["historical_preservation"]
    assert receipt["status"] == "READY_FOR_A6_6_PROVENANCE_CONSUMPTION"
    assert receipt["a6_6_provenance_consumption_authorized"] is True
    assert receipt["a6_6_provenance_consumption_statement"] == mod.A6_6_STATEMENT
    assert receipt["a6_6_performed"] is False
    assert receipt["unresolved_blockers"] == []
    assert all(receipt["validation"].values())
    assert history["predecessor_acceptance_receipt_sha256"] == (
        mod.PRIOR_ACCEPTANCE_RECEIPT_SHA256
    )
    assert history["predecessor_claims_successor_acceptance"] is False
    assert history["predecessor_package_modified"] is False
    assert history["successor_relationship"] == "additive five-layout successor acceptance"


def test_schema_fails_closed_and_generated_package_is_byte_exact():
    # Regeneration loads Person A's validator from their worktree, and that
    # module imports Person A's `mineocclude` package. In a shared pytest
    # process `mineocclude` is already bound to this worktree, so the import
    # resolves against the wrong tree. A fresh interpreter is the only way to
    # exercise the real regeneration path.
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / f"{mod.__name__}.py"),
            "--validate",
            "--out-dir",
            str(PACKAGE),
        ],
        cwd=str(ROOT),
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout

    schema = load(mod.SCHEMA_NAME)
    receipt = load(mod.RECEIPT_NAME)
    mod.validate_receipt_schema(receipt, schema)
    rejected = copy.deepcopy(receipt)
    rejected["collection_identity"]["activation_row_count"] = 5999
    with pytest.raises(mod.AcceptanceError, match="collection cardinality mismatch"):
        mod.validate_receipt_schema(rejected, schema)


def test_receipt_inventory_is_complete_and_excludes_only_itself():
    inventory = load("sha256_inventory.json")
    assert inventory["inventory_excludes_self"] is True
    assert inventory["file_count"] == 4
    assert {row["path"] for row in inventory["files"]} == {
        mod.RECEIPT_NAME,
        mod.SCHEMA_NAME,
        "validation_receipt.json",
    }
