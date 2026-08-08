"""Focused checks for the 66-cell fold/oracle and metric dependency handoff."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PACKAGE = REPOSITORY_ROOT / "docs/status/person_b_66_cell_step4_1_dependency_handoff_v0_1"
VALIDATOR_PATH = (
    REPOSITORY_ROOT / "scripts/validate_person_b_66_cell_step4_1_dependency_handoff_v0_1.py"
)


@pytest.fixture(scope="module")
def validator():
    spec = importlib.util.spec_from_file_location("person_b_66_cell_d_handoff", VALIDATOR_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _copy_package(tmp_path: Path) -> Path:
    destination = tmp_path / PACKAGE.name
    shutil.copytree(PACKAGE, destination)
    return destination


def _rewrite_inventory(package: Path) -> None:
    inventory_path = package / "sha256_inventory.json"
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    for name in inventory["files"]:
        data = (package / name).read_bytes()
        inventory["files"][name] = {
            "sha256": hashlib.sha256(data).hexdigest(),
            "size_bytes": len(data),
        }
    inventory_path.write_text(
        json.dumps(inventory, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def test_current_handoff_validates_against_exact_c_git_object(validator):
    result = validator.validate(REPOSITORY_ROOT)
    assert result["c_manifest_consumer_validation"] == "PASS"
    assert result["accepted_c_trajectory_count"] == 66
    assert result["fold_manifest_sha256"] == validator.FOLD_SHA256
    assert result["oracle_target_sha256"] == validator.ORACLE_SHA256
    assert result["oracle_records_sha256"] == validator.ORACLE_RECORDS_SHA256
    assert result["oracle_records_count"] == 2108
    assert result["metric_table_dependency"] == "BLOCKED"


def test_oracle_target_records_bind_exact_hash_and_size(validator):
    assert validator.ORACLE_RECORDS_SIZE_BYTES == 2953366
    binding = json.loads((PACKAGE / "fold_target_binding.json").read_text(encoding="utf-8"))
    assert binding["oracle_target"]["oracle_target_records_sha256"] == validator.ORACLE_RECORDS_SHA256
    assert binding["oracle_target"]["oracle_target_records_size_bytes"] == validator.ORACLE_RECORDS_SIZE_BYTES


def test_oracle_target_records_hash_mismatch_fails_closed(validator):
    original = validator.ORACLE_RECORDS_SHA256
    validator.ORACLE_RECORDS_SHA256 = "0" * 64
    try:
        with pytest.raises(validator.ValidationError):
            validator.validate(REPOSITORY_ROOT)
    finally:
        validator.ORACLE_RECORDS_SHA256 = original


def test_fold_target_binding_exposes_d_section_7_identity_fields():
    binding = json.loads((PACKAGE / "fold_target_binding.json").read_text(encoding="utf-8"))
    handoff = json.loads((PACKAGE / "step4_1_dependency_handoff.json").read_text(encoding="utf-8"))
    assert binding["fold_assignment"]["fold_manifest_sha256"] == handoff["fold_manifest_sha256"]
    assert binding["oracle_target"]["oracle_target_manifest_sha256"] == handoff["oracle_target_sha256"]
    assert handoff["exact_identity_fields"] == [
        "trajectory_id",
        "model_frame_idx",
        "fold_idx",
        "target_name",
        "fold_manifest_sha256",
        "oracle_target_sha256",
    ]


def test_old_ten_pilot_hashes_are_explicitly_rejected_as_current_scope(validator, tmp_path):
    package = _copy_package(tmp_path)
    binding_path = package / "fold_target_binding.json"
    binding = json.loads(binding_path.read_text(encoding="utf-8"))
    binding["fold_assignment"]["fold_manifest_sha256"] = validator.OLD_FOLD_SHA256
    binding_path.write_text(json.dumps(binding, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _rewrite_inventory(package)
    with pytest.raises(validator.ValidationError):
        validator.validate(REPOSITORY_ROOT, package)


def test_changed_c_manifest_identity_fails_closed(validator, tmp_path):
    package = _copy_package(tmp_path)
    receipt_path = package / "consumer_validation_receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["accepted_data_authority"]["accepted_manifest_sha256"] = "0" * 64
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _rewrite_inventory(package)
    with pytest.raises(validator.ValidationError):
        validator.validate(REPOSITORY_ROOT, package)


def test_metric_dependency_cannot_be_promoted_without_66_cell_artifact(validator, tmp_path):
    package = _copy_package(tmp_path)
    metric_path = package / "metric_table_dependency.json"
    metric = json.loads(metric_path.read_text(encoding="utf-8"))
    metric["status"] = "PASS"
    metric_path.write_text(json.dumps(metric, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _rewrite_inventory(package)
    with pytest.raises(validator.ValidationError):
        validator.validate(REPOSITORY_ROOT, package)


def test_legacy_metric_table_is_not_relabelled():
    metric = json.loads((PACKAGE / "metric_table_dependency.json").read_text(encoding="utf-8"))
    legacy = metric["legacy_metric_table"]
    assert legacy["sha256"] == "c471fddb9bdc1a87c2f7e11ad8dc55db9e407f0ea45a2e038f668bda178ad0a7"
    assert legacy["accepted_as_current_66_cell_metric_table"] is False
    assert metric["current_66_cell_metric_table"] is None


def test_phase3_joined_package_passes_but_formal_closure_remains_pending():
    receipt = json.loads((PACKAGE / "consumer_validation_receipt.json").read_text(encoding="utf-8"))
    assert receipt["status"] == "PASS"
    assert receipt["phase3_step3_3_joined_package_status"] == "PASS"
    assert receipt["phase3_consumer_validation_status"] == "PASS"
    assert receipt["phase3_closure_recommendation"] == "READY"
    assert receipt["phase3_independent_final_verification"] == "PENDING"
    assert receipt["phase3_overall_status"] == "IN_PROGRESS"


def test_person_d_authority_must_exist_on_remote_branch(validator):
    original = validator.D_COMMIT
    validator.D_COMMIT = "0" * 40
    try:
        with pytest.raises(validator.ValidationError):
            validator.validate(REPOSITORY_ROOT)
    finally:
        validator.D_COMMIT = original


def test_handoff_is_nonexecuting_and_u4_closed():
    for path in PACKAGE.glob("*.json"):
        value = json.loads(path.read_text(encoding="utf-8"))
        assert value["scientific_execution_performed"] is False
        assert value["u4_output_inspected"] is False
