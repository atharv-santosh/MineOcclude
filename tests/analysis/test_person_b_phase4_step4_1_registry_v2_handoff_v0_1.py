"""Fail-closed tests for the Phase 4 Step 4.1 Registry v2 handoff."""

from __future__ import annotations

import ast
import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from scripts.validate_person_b_phase4_step4_1_registry_v2_handoff_v0_1 import (
    DOCUMENT_NAMES,
    INVENTORIED_NAMES,
    PACKAGE_RELATIVE_PATH,
    HandoffValidationError,
    canonical_json_bytes,
    sha256_file,
    validate_package,
    validate_worktree_scope,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = REPO_ROOT / PACKAGE_RELATIVE_PATH
VALIDATOR_PATH = (
    REPO_ROOT
    / "scripts/validate_person_b_phase4_step4_1_registry_v2_handoff_v0_1.py"
)


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, document: Any) -> None:
    path.write_bytes(canonical_json_bytes(document))


def _copy_package(tmp_path: Path) -> Path:
    destination = tmp_path / PACKAGE_ROOT.name
    shutil.copytree(PACKAGE_ROOT, destination)
    return destination


def _refresh_inventory(package_root: Path) -> None:
    inventory = _load(package_root / "sha256_inventory.json")
    inventory["files"] = [
        {"path": name, "sha256": sha256_file(package_root / name)}
        for name in INVENTORIED_NAMES
    ]
    _write(package_root / "sha256_inventory.json", inventory)


def _mutate(
    package_root: Path,
    name: str,
    transform: Any,
) -> None:
    path = package_root / name
    document = _load(path)
    transform(document)
    _write(path, document)
    _refresh_inventory(package_root)


def _validate_copy(package_root: Path) -> None:
    validate_package(
        package_root,
        REPO_ROOT,
        verify_sources=False,
        verify_worktree=False,
    )


def test_real_package_passes_complete_validation() -> None:
    result = validate_package(PACKAGE_ROOT, REPO_ROOT)
    assert result == {
        "blocked_job_count": 3,
        "person_a_phase6_authorized": False,
        "preparation_decision": "READY",
        "production_metrics_executed": False,
        "production_predictions_executed": False,
        "probe_fitting_executed": False,
        "scientific_outputs_created": False,
        "status": "PASS",
    }


def test_exact_document_inventory() -> None:
    assert sorted(path.name for path in PACKAGE_ROOT.iterdir() if path.is_file()) == (
        sorted(DOCUMENT_NAMES)
    )


def test_wrong_starting_authority_fails(tmp_path: Path) -> None:
    package = _copy_package(tmp_path)
    _mutate(
        package,
        "authority_binding.json",
        lambda document: document.__setitem__("starting_authority", "0" * 40),
    )
    with pytest.raises(HandoffValidationError, match="wrong_starting_authority"):
        _validate_copy(package)


def test_fold_assignment_change_fails(tmp_path: Path) -> None:
    package = _copy_package(tmp_path)

    def mutate(document: dict[str, Any]) -> None:
        document["frozen_assignment"]["layout_assignments"][0]["fold_idx"] = 4

    _mutate(package, "sealed_fold_split_identity.json", mutate)
    with pytest.raises(HandoffValidationError, match="fold_plan_mismatch"):
        _validate_copy(package)


def test_final_fold_unblocked_without_a_fails(tmp_path: Path) -> None:
    package = _copy_package(tmp_path)

    def mutate(document: dict[str, Any]) -> None:
        document["final_frame_manifest"]["construction_status"] = "READY"

    _mutate(package, "sealed_fold_split_identity.json", mutate)
    with pytest.raises(
        HandoffValidationError,
        match="final_fold_manifest_without_person_a",
    ):
        _validate_copy(package)


def test_wrong_c_input_hash_fails(tmp_path: Path) -> None:
    package = _copy_package(tmp_path)

    def mutate(document: dict[str, Any]) -> None:
        document["accepted_inputs"][0]["literal_sha256"] = "0" * 64

    _mutate(package, "accepted_c_oracle_inputs.json", mutate)
    with pytest.raises(HandoffValidationError, match="authority_hash_mismatch"):
        _validate_copy(package)


def test_phase3_readiness_substitution_fails(tmp_path: Path) -> None:
    package = _copy_package(tmp_path)

    def mutate(document: dict[str, Any]) -> None:
        document["forbidden_source_substitutions"][0][
            "must_not_be_registered_as"
        ].remove("oracle_target")

    _mutate(package, "registry_v2_exact_artifact_authorization.json", mutate)
    with pytest.raises(HandoffValidationError, match="phase3_readiness_substitution"):
        _validate_copy(package)


def test_person_a_pending_hash_cannot_be_invented(tmp_path: Path) -> None:
    package = _copy_package(tmp_path)

    def mutate(document: dict[str, Any]) -> None:
        document["accepted_production_values"]["checkpoint_hash"] = "1" * 64

    _mutate(package, "person_a_required_handoff.json", mutate)
    with pytest.raises(HandoffValidationError, match="invented_pending_person_a_value"):
        _validate_copy(package)


def test_fitted_probe_job_cannot_be_unblocked(tmp_path: Path) -> None:
    package = _copy_package(tmp_path)

    def mutate(document: dict[str, Any]) -> None:
        document["jobs"][0]["status"] = "READY"

    _mutate(package, "blocked_jobs.json", mutate)
    with pytest.raises(HandoffValidationError, match="scientific_job_unblocked"):
        _validate_copy(package)


def test_blocked_job_cannot_claim_output_hash(tmp_path: Path) -> None:
    package = _copy_package(tmp_path)

    def mutate(document: dict[str, Any]) -> None:
        document["jobs"][1]["output_sha256"] = "2" * 64

    _mutate(package, "blocked_jobs.json", mutate)
    with pytest.raises(HandoffValidationError, match="scientific_job_unblocked"):
        _validate_copy(package)


def test_metric_contract_requires_person_d_baseline(tmp_path: Path) -> None:
    package = _copy_package(tmp_path)

    def mutate(document: dict[str, Any]) -> None:
        document["direct_input_artifact_types"].remove("baseline")

    _mutate(package, "metric_table_input_contract.json", mutate)
    with pytest.raises(HandoffValidationError, match="invalid_direct_input"):
        _validate_copy(package)


def test_production_metric_execution_claim_fails(tmp_path: Path) -> None:
    package = _copy_package(tmp_path)
    _mutate(
        package,
        "blocked_jobs.json",
        lambda document: document.__setitem__(
            "production_metrics_executed",
            True,
        ),
    )
    with pytest.raises(HandoffValidationError, match="scientific_output_present"):
        _validate_copy(package)


def test_oracle_contract_cannot_claim_output(tmp_path: Path) -> None:
    package = _copy_package(tmp_path)
    _mutate(
        package,
        "oracle_target_contract.json",
        lambda document: document.__setitem__("production_artifact_created", True),
    )
    with pytest.raises(HandoffValidationError, match="scientific_output_present"):
        _validate_copy(package)


def test_person_a_phase6_authorization_fails(tmp_path: Path) -> None:
    package = _copy_package(tmp_path)
    _mutate(
        package,
        "phase6_authorization_conditions.json",
        lambda document: document.__setitem__("person_a_phase6_authorized", True),
    )
    with pytest.raises(
        HandoffValidationError,
        match="person_a_phase6_silently_authorized",
    ):
        _validate_copy(package)


def test_wrong_owner_fails(tmp_path: Path) -> None:
    package = _copy_package(tmp_path)

    def mutate(document: dict[str, Any]) -> None:
        document["artifact_owner_status"][0]["owner"] = "person_a"

    _mutate(package, "registry_v2_owner_status.json", mutate)
    with pytest.raises(HandoffValidationError, match="invalid_owner"):
        _validate_copy(package)


def test_manifest_template_cannot_be_scientific_artifact(tmp_path: Path) -> None:
    package = _copy_package(tmp_path)
    _mutate(
        package,
        "registry_v2_manifest_template.json",
        lambda document: document.__setitem__("template_is_scientific_artifact", True),
    )
    with pytest.raises(HandoffValidationError, match="scientific_output_present"):
        _validate_copy(package)


def test_noncanonical_json_fails(tmp_path: Path) -> None:
    package = _copy_package(tmp_path)
    path = package / "oracle_target_contract.json"
    path.write_bytes(path.read_bytes() + b"\n")
    _refresh_inventory(package)
    with pytest.raises(HandoffValidationError, match="noncanonical_json"):
        _validate_copy(package)


def test_sha256_inventory_mismatch_fails(tmp_path: Path) -> None:
    package = _copy_package(tmp_path)
    path = package / "blocked_jobs.json"
    document = _load(path)
    document["person_a_dependency_status"] = "tampered"
    _write(path, document)
    with pytest.raises(HandoffValidationError, match="sha256_inventory_mismatch"):
        _validate_copy(package)


def test_missing_document_fails(tmp_path: Path) -> None:
    package = _copy_package(tmp_path)
    (package / "prediction_input_contract.json").unlink()
    with pytest.raises(HandoffValidationError, match="missing_required_document"):
        _validate_copy(package)


def test_worktree_changes_are_new_authorized_paths_only() -> None:
    validate_worktree_scope(REPO_ROOT)


def test_validator_has_no_scientific_execution_imports_or_calls() -> None:
    source = VALIDATOR_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_modules = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    assert not any(module.startswith("mineocclude") for module in imported_modules)
    assert "fit_ridge_oof(" not in source
    assert "regression_metrics(" not in source
    assert "build_oracle_targets(" not in source
