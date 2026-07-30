from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from scripts.validate_person_b_phase4_step4_1_step6_authorization_refresh_v0_1 import (
    DOCUMENT_NAMES,
    EXCLUDED_TRAJECTORY_ID,
    EXPECTED_SCIENTIFIC_USE,
    EXPECTED_TRAJECTORY_IDS,
    HISTORICAL_SELECTION_PATH,
    PACKAGE_RELATIVE_PATH,
    PERSON_C_AUTHORITY,
    AuthorizationRefreshValidationError,
    canonical_json_bytes,
    validate_package,
    validate_worktree_scope,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = REPO_ROOT / PACKAGE_RELATIVE_PATH


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_bytes())
    assert isinstance(value, dict)
    return value


def _copy_package(tmp_path: Path) -> Path:
    destination = tmp_path / PACKAGE_RELATIVE_PATH.name
    shutil.copytree(PACKAGE_ROOT, destination)
    return destination


def _mutate(
    package: Path,
    name: str,
    mutation: Any,
) -> None:
    path = package / name
    document = _load(path)
    mutation(document)
    path.write_bytes(canonical_json_bytes(document))


def _validate_copy(
    package: Path,
    *,
    verify_inventory: bool = False,
) -> dict[str, Any]:
    return validate_package(
        package,
        REPO_ROOT,
        verify_inventory=verify_inventory,
        verify_worktree=False,
    )


def _git_bytes(commit: str, path: str) -> bytes:
    return subprocess.run(
        ["git", "show", f"{commit}:{path}"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
    ).stdout


def test_real_package_passes_complete_validation() -> None:
    assert validate_package(PACKAGE_ROOT, REPO_ROOT) == {
        "c_scientific_use_accepted": False,
        "current_c_hashes_verified": True,
        "excluded_control_preserved": True,
        "missing_required_signers": ["person_a", "person_c"],
        "person_a_runtime_execution_authorized": False,
        "refreshed_c_selection_count": 15,
        "registry_v2_acceptance_authorized": False,
        "runtime_authorization_circularity_removed": True,
        "scientific_execution_performed": False,
        "status": "PASS",
        "u4_output_inspected": False,
    }


def test_exact_eight_document_inventory() -> None:
    assert {path.name for path in PACKAGE_ROOT.glob("*.json")} == set(
        DOCUMENT_NAMES
    )


def test_refreshed_selection_has_exact_order() -> None:
    selection = _load(PACKAGE_ROOT / "refreshed_c_candidate_selection.json")
    assert selection["selection_count"] == 15
    assert tuple(
        item["trajectory_id"] for item in selection["ordered_candidates"]
    ) == EXPECTED_TRAJECTORY_IDS


def test_current_c_hashes_sizes_and_metadata_match() -> None:
    selection = _load(PACKAGE_ROOT / "refreshed_c_candidate_selection.json")
    for item in selection["ordered_candidates"]:
        raw = _git_bytes(PERSON_C_AUTHORITY, item["source_path"])
        package = json.loads(raw)
        assert item["git_object_sha256"] == hashlib.sha256(raw).hexdigest()
        assert item["byte_size"] == len(raw)
        assert item["frame_count"] == package["media"]["frame_count"]
        assert item["package_local_status"] == package["episode_manifest"]["status"]
        assert item["scientific_use"] == package["scientific_use"]
        assert item["source_authority_commit"] == PERSON_C_AUTHORITY


def test_all_current_c_scientific_use_values_remain_pending() -> None:
    selection = _load(PACKAGE_ROOT / "refreshed_c_candidate_selection.json")
    assert {
        item["scientific_use"] for item in selection["ordered_candidates"]
    } == {EXPECTED_SCIENTIFIC_USE}
    assert selection["accepted_scientific_input_count"] == 0
    assert selection["c_scientific_use_currently_accepted"] is False


def test_historical_hashes_are_superseded_not_current() -> None:
    historical = _load(REPO_ROOT / HISTORICAL_SELECTION_PATH)
    selection = _load(PACKAGE_ROOT / "refreshed_c_candidate_selection.json")
    stale = {item["literal_sha256"] for item in historical["accepted_inputs"]}
    current = {
        item["git_object_sha256"] for item in selection["ordered_candidates"]
    }
    assert selection["old_selection_hashes_superseded"] is True
    assert stale.isdisjoint(current)
    assert all(
        "literal_sha256" not in item for item in selection["ordered_candidates"]
    )


def test_no_object_control_is_preserved() -> None:
    selection = _load(PACKAGE_ROOT / "refreshed_c_candidate_selection.json")
    excluded = selection["excluded_no_object_control"]
    assert excluded["trajectory_id"] == EXCLUDED_TRAJECTORY_ID
    assert excluded["classification"] == "excluded_no_object_control"
    assert excluded["registry_v2_accepted"] is False


def test_source_set_digest_is_deterministic() -> None:
    selection = _load(PACKAGE_ROOT / "refreshed_c_candidate_selection.json")
    expected = hashlib.sha256(
        "\n".join(
            f"{item['trajectory_id']}:{item['git_object_sha256']}"
            for item in selection["ordered_candidates"]
        ).encode("utf-8")
    ).hexdigest()
    assert selection["source_set_digest"] == expected
    assert selection["source_frame_count"] == 2877


def test_selection_order_mutation_fails(tmp_path: Path) -> None:
    package = _copy_package(tmp_path)

    def reverse(document: dict[str, Any]) -> None:
        document["ordered_candidates"].reverse()

    _mutate(package, "refreshed_c_candidate_selection.json", reverse)
    with pytest.raises(
        AuthorizationRefreshValidationError,
        match="selection_order_mismatch",
    ):
        _validate_copy(package)


@pytest.mark.parametrize("field", ["git_object_sha256", "byte_size"])
def test_current_c_identity_mutation_fails(
    tmp_path: Path,
    field: str,
) -> None:
    package = _copy_package(tmp_path)

    def change(document: dict[str, Any]) -> None:
        document["ordered_candidates"][0][field] = (
            "0" * 64 if field == "git_object_sha256" else 0
        )

    _mutate(package, "refreshed_c_candidate_selection.json", change)
    with pytest.raises(
        AuthorizationRefreshValidationError,
        match="current_c_identity_mismatch",
    ):
        _validate_copy(package)


def test_scientific_use_promotion_fails(tmp_path: Path) -> None:
    package = _copy_package(tmp_path)

    def promote(document: dict[str, Any]) -> None:
        document["ordered_candidates"][0]["scientific_use"] = "accepted"

    _mutate(package, "refreshed_c_candidate_selection.json", promote)
    with pytest.raises(
        AuthorizationRefreshValidationError,
        match="current_c_identity_mismatch",
    ):
        _validate_copy(package)


def test_wrong_person_c_authority_fails(tmp_path: Path) -> None:
    package = _copy_package(tmp_path)
    _mutate(
        package,
        "refreshed_c_candidate_selection.json",
        lambda document: document.__setitem__(
            "refreshed_selection_source_commit",
            "0" * 40,
        ),
    )
    with pytest.raises(
        AuthorizationRefreshValidationError,
        match="current_c_authority_mismatch",
    ):
        _validate_copy(package)


def test_wrong_authority_binding_fails(tmp_path: Path) -> None:
    package = _copy_package(tmp_path)

    def change(document: dict[str, Any]) -> None:
        document["authorities"]["person_c"]["commit"] = "0" * 40

    _mutate(package, "authority_binding.json", change)
    with pytest.raises(
        AuthorizationRefreshValidationError,
        match="authority_binding_mismatch",
    ):
        _validate_copy(package)


def test_runtime_does_not_depend_on_future_output_bytes() -> None:
    matrix = _load(PACKAGE_ROOT / "authorization_dependency_matrix.json")
    runtime = next(
        item
        for item in matrix["decisions"]
        if item["decision_id"] == "person_a_runtime_execution"
    )
    assert runtime["post_execution_dependencies"] == []
    assert all(
        "bytes" not in dependency
        for dependency in runtime["pre_execution_dependencies"]
    )


def test_runtime_post_execution_dependency_fails(tmp_path: Path) -> None:
    package = _copy_package(tmp_path)

    def make_circular(document: dict[str, Any]) -> None:
        runtime = next(
            item
            for item in document["decisions"]
            if item["decision_id"] == "person_a_runtime_execution"
        )
        runtime["pre_execution_dependencies"].append(
            "production_activation_bytes"
        )

    _mutate(package, "authorization_dependency_matrix.json", make_circular)
    with pytest.raises(
        AuthorizationRefreshValidationError,
        match="runtime_circularity",
    ):
        _validate_copy(package)


def test_registry_acceptance_requires_future_exact_bytes() -> None:
    matrix = _load(PACKAGE_ROOT / "authorization_dependency_matrix.json")
    registry = next(
        item
        for item in matrix["decisions"]
        if item["decision_id"] == "registry_v2_artifact_acceptance"
    )
    assert "exact_output_artifact_bytes" in registry["post_execution_dependencies"]


def test_registry_without_future_exact_bytes_fails(tmp_path: Path) -> None:
    package = _copy_package(tmp_path)

    def remove_bytes(document: dict[str, Any]) -> None:
        registry = next(
            item
            for item in document["decisions"]
            if item["decision_id"] == "registry_v2_artifact_acceptance"
        )
        registry["post_execution_dependencies"].remove(
            "exact_output_artifact_bytes"
        )

    _mutate(package, "authorization_dependency_matrix.json", remove_bytes)
    with pytest.raises(
        AuthorizationRefreshValidationError,
        match="registry_acceptance_mismatch",
    ):
        _validate_copy(package)


def test_b_alone_does_not_authorize_runtime() -> None:
    decision = _load(PACKAGE_ROOT / "authorization_decision.json")
    runtime = decision["decision_layers"]["person_a_runtime_execution"]
    assert runtime["authorized"] is False
    assert runtime["missing_required_signers"] == ["person_a", "person_c"]
    assert runtime["signer_status"]["person_b"] == (
        "CONDITIONAL_SCOPE_APPROVAL_RECORDED"
    )


def test_runtime_authorized_with_missing_signers_fails(tmp_path: Path) -> None:
    package = _copy_package(tmp_path)

    def authorize(document: dict[str, Any]) -> None:
        document["decision_layers"]["person_a_runtime_execution"][
            "authorized"
        ] = True

    _mutate(package, "authorization_decision.json", authorize)
    with pytest.raises(
        AuthorizationRefreshValidationError,
        match="runtime_authorization_mismatch",
    ):
        _validate_copy(package)


def test_missing_signer_accounting_mutation_fails(tmp_path: Path) -> None:
    package = _copy_package(tmp_path)

    def remove_signer(document: dict[str, Any]) -> None:
        document["decision_layers"]["person_a_runtime_execution"][
            "missing_required_signers"
        ] = []

    _mutate(package, "authorization_decision.json", remove_signer)
    with pytest.raises(
        AuthorizationRefreshValidationError,
        match="runtime_authorization_mismatch",
    ):
        _validate_copy(package)


def test_automatic_transition_fails(tmp_path: Path) -> None:
    package = _copy_package(tmp_path)
    _mutate(
        package,
        "authorization_decision.json",
        lambda document: document.__setitem__(
            "automatic_phase6_transition_allowed",
            True,
        ),
    )
    with pytest.raises(
        AuthorizationRefreshValidationError,
        match="automatic_authorization_forbidden",
    ):
        _validate_copy(package)


@pytest.mark.parametrize(
    ("layer", "field"),
    [
        ("person_c_scientific_use", "accepted"),
        ("registry_v2_artifact_acceptance", "accepted"),
    ],
)
def test_scientific_or_registry_acceptance_fails(
    tmp_path: Path,
    layer: str,
    field: str,
) -> None:
    package = _copy_package(tmp_path)

    def accept(document: dict[str, Any]) -> None:
        document["decision_layers"][layer][field] = True

    _mutate(package, "authorization_decision.json", accept)
    with pytest.raises(AuthorizationRefreshValidationError):
        _validate_copy(package)


def test_required_owner_decisions_are_not_fabricated() -> None:
    c_required = _load(PACKAGE_ROOT / "person_c_required_decision.json")
    a_required = _load(PACKAGE_ROOT / "person_a_required_acknowledgement.json")
    assert c_required["current_decision"] is None
    assert c_required["person_b_may_supply_this_decision"] is False
    assert a_required["current_acknowledgement"] is None
    assert a_required["person_b_may_supply_this_acknowledgement"] is False


@pytest.mark.parametrize(
    "field",
    ["accepted_scientific_artifact_count", "accepted_placeholder_count"],
)
def test_scientific_artifact_or_placeholder_fails(
    tmp_path: Path,
    field: str,
) -> None:
    package = _copy_package(tmp_path)
    _mutate(
        package,
        "validation_receipt.json",
        lambda document: document.__setitem__(field, 1),
    )
    with pytest.raises(
        AuthorizationRefreshValidationError,
        match="receipt_mismatch",
    ):
        _validate_copy(package)


def test_all_package_json_is_canonical() -> None:
    for name in DOCUMENT_NAMES:
        path = PACKAGE_ROOT / name
        assert path.read_bytes() == canonical_json_bytes(_load(path))


def test_inventory_is_complete_and_current() -> None:
    validate_package(
        PACKAGE_ROOT,
        REPO_ROOT,
        verify_sources=True,
        verify_inventory=True,
        verify_worktree=False,
    )


def test_inventory_hash_mutation_fails(tmp_path: Path) -> None:
    package = _copy_package(tmp_path)

    def corrupt(document: dict[str, Any]) -> None:
        document["files"][0]["sha256"] = "0" * 64

    _mutate(package, "sha256_inventory.json", corrupt)
    with pytest.raises(
        AuthorizationRefreshValidationError,
        match="inventory_mismatch",
    ):
        _validate_copy(package, verify_inventory=True)


def test_worktree_scope_is_focused() -> None:
    validate_worktree_scope(REPO_ROOT)


def test_receipt_proves_no_scientific_execution_or_u4() -> None:
    receipt = _load(PACKAGE_ROOT / "validation_receipt.json")
    assert receipt["scientific_execution_performed"] is False
    assert receipt["oracle_construction_executed"] is False
    assert receipt["fitted_probe_executed"] is False
    assert receipt["prediction_executed"] is False
    assert receipt["scientific_metrics_executed"] is False
    assert receipt["u4_output_inspected"] is False
