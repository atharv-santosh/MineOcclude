"""Proofs for the Person D Phase 4 Step 4.1 registry v2 handoff package.

Covers the corrected Person B branch/authority, the package's own
internal consistency (canonical JSON, blocked status, forbidden-preview
binding), and re-confirms -- in this package's own context, not by
assuming another test file's presence -- that the fail-closed
guarantees this handoff depends on still hold. None of these tests fit,
generate, or accept a scientific baseline.
"""

from __future__ import annotations

import importlib.util
import json
from dataclasses import replace
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PACKAGE_DIR = ROOT / "docs" / "status" / "person_d_phase4_step4_1_registry_v2_handoff_v0_1"
VALIDATOR_SCRIPT = (
    ROOT / "scripts" / "validate_person_d_phase4_step4_1_registry_v2_handoff_v0_1.py"
)

from mineocclude.baselines.capture_ingest import UNASSIGNED_FOLD
from mineocclude.baselines.registry_v2_artifacts import (
    RegistryV2ArtifactError,
    validate_owner_status_record,
)
from mineocclude.baselines.scientific_readiness import (
    READY_SCIENTIFIC_USE,
    validate_scientific_baseline_readiness,
)

# Reuse the exact best-case fixture builder from test_scientific_readiness.py
# rather than re-deriving B's oracle-target row shape from scratch here.
from tests.baselines.test_scientific_readiness import _best_case_inputs


def _load_validator_module():
    spec = importlib.util.spec_from_file_location(
        "validate_person_d_phase4_step4_1_registry_v2_handoff_v0_1", VALIDATOR_SCRIPT
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_json(name: str) -> dict:
    return json.loads((PACKAGE_DIR / name).read_text(encoding="utf-8"))


def _all_package_json_files() -> list[Path]:
    return sorted(
        path for path in PACKAGE_DIR.rglob("*.json") if path.name != "sha256_inventory.json"
    )


# --------------------------------------------------------------------------
# Corrected Person B authority
# --------------------------------------------------------------------------


def test_b_branch_name_is_role_person_b_analysis():
    doc = _load_json("authority_binding.json")
    assert doc["person_b"]["corrected_branch"] == "role/person-b-analysis"
    assert doc["person_b"]["task_stated_branch"] == "role/person-b-methods"


def test_person_e_authorities_match_verified_commits():
    doc = _load_json("authority_binding.json")
    assert (
        doc["person_e"]["registry_v2_contract_authority"]
        == "25509bb4ba292a83d933058539aca1ca6002524a"
    )
    assert (
        doc["person_e"]["registry_v2_query_authority"]
        == "5d8660c90fbf7362d7f32005f9b650e15ae1bfb5"
    )


# --------------------------------------------------------------------------
# The D job remains blocked; nothing accepted, no execution, no placeholders
# --------------------------------------------------------------------------


def test_d_job_remains_blocked():
    doc = _load_json("production_job_status.json")
    assert doc["status"] == "blocked"
    assert doc["output_artifact_id"] is None
    assert doc["output_sha256"] is None
    reason_codes = {blocker["reason_code"] for blocker in doc["required_blockers"]}
    assert reason_codes == {
        "committed_authoritative_person_b_handoff_unavailable",
        "sealed_fold_membership_unavailable",
        "actual_oracle_target_unavailable",
        "exact_accepted_upstream_identities_unavailable",
    }


def test_no_accepted_baseline_artifact_exists_anywhere_in_the_package():
    for path in _all_package_json_files():
        doc = json.loads(path.read_text(encoding="utf-8"))
        flat = json.dumps(doc)
        assert '"artifact_status": "contract_only"' not in flat or '"accepted": true' not in flat
    contract = _load_json("baseline_artifact_contract.json")
    assert contract["accepted"] is False
    assert contract["artifact_status"] == "contract_only"
    assert contract["required_fields"]["prediction_rows"]["current_value"] == []


def test_no_placeholder_is_promoted_to_accepted():
    templates = _load_json("registry_v2_handoff_templates.json")
    assert templates["owner_status_record_template"]["owner_status"] == "pending"
    assert templates["owner_status_record_template"]["decision"] == "pending"
    for key in (
        "exact_artifact_authorization_template",
        "trusted_manifest_entry_template",
        "artifact_verification_receipt_template",
    ):
        flat = json.dumps(templates[key])
        assert '"accepted"' not in flat


def test_no_scientific_execution_occurred():
    contract = _load_json("scientific_baseline_input_contract.json")
    assert contract["current_actual_result"]["status"] == "BLOCKED"
    for identity in contract["required_identities"].values():
        if "status" in identity:
            assert identity["status"] in (
                "unavailable",
                "partially_available_but_not_directly_consumed",
                "unavailable_as_a_sealed_document_bound_into_an_oracle_target_document",
            )


# --------------------------------------------------------------------------
# The forbidden preview remains forbidden
# --------------------------------------------------------------------------


def test_forbidden_preview_remains_forbidden_and_hash_is_current():
    doc = _load_json("forbidden_preview_guard.json")
    assert doc["bound_artifact"]["scientific_use"] == "forbidden"
    preview_path = ROOT / "docs" / "status" / "person_d_real_pilot_baseline_preview.json"
    import hashlib

    live_sha256 = hashlib.sha256(preview_path.read_bytes()).hexdigest()
    assert doc["bound_artifact"]["literal_sha256"] == live_sha256


# --------------------------------------------------------------------------
# Re-confirmed fail-closed guarantees, in this package's own context
# --------------------------------------------------------------------------


def test_unassigned_fold_cannot_pass_in_this_packages_context():
    contexts, fold_manifest, oracle_target_document = _best_case_inputs()
    contexts = list(contexts)
    contexts[0] = replace(contexts[0], fold=UNASSIGNED_FOLD)
    finding = validate_scientific_baseline_readiness(
        contexts,
        fold_manifest=fold_manifest,
        oracle_target_document=oracle_target_document,
        candidate_scientific_use=READY_SCIENTIFIC_USE,
    )
    assert finding.status == "BLOCKED"
    assert any("UNASSIGNED_FOLD" in reason for reason in finding.blocked_reasons)


def test_missing_fold_identity_cannot_pass_in_this_packages_context():
    contexts, fold_manifest, oracle_target_document = _best_case_inputs()
    broken_manifest = dict(fold_manifest)
    del broken_manifest["artifact_hash"]
    finding = validate_scientific_baseline_readiness(
        contexts,
        fold_manifest=broken_manifest,
        oracle_target_document=oracle_target_document,
        candidate_scientific_use=READY_SCIENTIFIC_USE,
    )
    assert finding.status == "BLOCKED"
    assert any("fold manifest identity" in reason for reason in finding.blocked_reasons)


def test_missing_oracle_identity_cannot_pass_in_this_packages_context():
    contexts, fold_manifest, oracle_target_document = _best_case_inputs()
    broken_document = dict(oracle_target_document)
    del broken_document["target_schema_version"]
    finding = validate_scientific_baseline_readiness(
        contexts,
        fold_manifest=fold_manifest,
        oracle_target_document=broken_document,
        candidate_scientific_use=READY_SCIENTIFIC_USE,
    )
    assert finding.status == "BLOCKED"
    assert any("oracle target identity" in reason for reason in finding.blocked_reasons)


def test_readiness_blocked_cannot_be_promoted_even_in_the_best_case():
    contexts, fold_manifest, oracle_target_document = _best_case_inputs()
    finding = validate_scientific_baseline_readiness(
        contexts,
        fold_manifest=fold_manifest,
        oracle_target_document=oracle_target_document,
        candidate_scientific_use=READY_SCIENTIFIC_USE,
    )
    assert finding.status == "BLOCKED"
    readiness_gate_contract = _load_json("readiness_gate_contract.json")
    assert readiness_gate_contract["required_result"]["status"] == "READY"
    assert readiness_gate_contract["current_call_status"] == "not_yet_callable_with_real_arguments"


def test_accepted_registry_v2_records_cannot_be_created_from_templates():
    templates = _load_json("registry_v2_handoff_templates.json")
    with pytest.raises(RegistryV2ArtifactError):
        validate_owner_status_record(templates["owner_status_record_template"])


# --------------------------------------------------------------------------
# Historical files untouched; every package JSON is canonical
# --------------------------------------------------------------------------


def test_historical_phase1_files_were_not_modified():
    import subprocess

    result = subprocess.run(
        [
            "git",
            "diff",
            "--name-only",
            "--",
            "docs/baselines/person_d_phase0.md",
            "docs/baselines/person_d_phase1.md",
            "PERSON_D_ISSUE.md",
            "docs/decisions/person_d_phase1_decision_log.md",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == "", (
        f"historical Phase 1 files were modified: {result.stdout}"
    )


def test_all_package_json_is_canonical_and_deterministic():
    validator = _load_validator_module()
    for path in _all_package_json_files():
        validator.check_json_canonical(path)  # raises HandoffValidationError if not
