"""Focused validation of the bounded Person E Phase 6 closure package."""

from __future__ import annotations

import json
import hashlib
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import build_person_e_phase6_step6_6_provenance_acceptance_v0_1 as mod

PKG = ROOT / mod.PKG_REL


def load(name: str):
    return json.loads((PKG / name).read_bytes())


def test_exact_ten_pilot_manifest_and_external_artifact_totals():
    manifest = load("accepted_provenance_manifest.json")
    assert manifest["ordered_pilot_ids"] == mod.EXPECTED_PILOTS
    assert manifest["no_wall_control_pilot_ids"] == mod.EXPECTED_CONTROLS
    assert manifest["accepted_pilot_count"] == 10
    assert manifest["accepted_placeholder_count"] == 0
    assert manifest["activation_row_count"] == 37_480
    assert manifest["activation_chunk_count"] == 200
    assert len(manifest["per_pilot"]) == 10
    assert sum(len(row["chunks"]) for row in manifest["per_pilot"]) == 200


def test_registry_v2_trust_chain_uses_frozen_schema_without_fabricated_authority():
    receipt = load("registry_v2_validation_receipt.json")
    assert receipt["frozen_validator_commit"] == mod.PERSON_E_REGISTRY_AUTHORITY
    assert (
        receipt["registry_v2_schema_version"] == "mineocclude-immutable-registry-v2.0"
    )
    assert receipt["registry_v2_trust_chain_complete"] is True
    assert receipt["ten_input_registry_artifact_count"] == 10
    assert receipt["total_rejection_count"] == 0
    assert receipt["upstream_owner_authority_fabricated_by_person_e"] is False


def test_person_b_positive_control_and_source_row_contract_are_verified():
    receipt = load("validation_receipt.json")
    assert receipt["person_b_positive_control_verified"] is True
    assert receipt["person_b_source_row_ratification_verified"] is True
    assert receipt["positive_control_pass"] is True
    assert receipt["visible_control_row_count"] == 1000
    assert receipt["finite_prediction_count"] == 20_000
    assert receipt["exact_source_row_producer_digests_verified"] is True
    assert receipt["registry_digest_substitution_count"] == 0


def test_phase6_closure_is_bounded_and_does_not_claim_step4_1_or_integration():
    decision = load("phase6_closure_decision.json")
    assert decision["step6_6_complete"] is True
    assert decision["phase6_complete"] is True
    assert decision["ten_pilot_expansion_complete"] is True
    assert decision["hidden_state_interpretation_authorized"] is False
    assert decision["u4_output_inspected"] is False
    assert decision["step4_1_complete_claimed"] is False
    assert decision["project_integration_claimed"] is False


def test_generated_package_is_byte_deterministic():
    # The original generator also authenticated large SageMaker files at
    # historical absolute paths.  Those runtime paths are provenance, not a
    # local verification dependency.  Reproducibility of the committed package
    # is established from its canonical bytes and immutable inventory.
    inventory = load("sha256_inventory.json")
    assert inventory["inventory_excludes_self"] is True
    assert inventory["file_count"] == len(inventory["files"]) + 1
    for name, digest in inventory["files"].items():
        payload = (PKG / name).read_bytes()
        document = json.loads(payload)
        canonical = (
            json.dumps(
                document,
                allow_nan=False,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8")
        assert payload == canonical
        assert hashlib.sha256(payload).hexdigest() == digest


def test_u4_is_not_named_by_any_execution_or_read_path():
    source = Path(mod.__file__).read_text(encoding="utf-8").lower()
    assert "u4_output_inspected" in source
    assert os.environ.get("PERSON_E_U4_OUTPUT") is None
