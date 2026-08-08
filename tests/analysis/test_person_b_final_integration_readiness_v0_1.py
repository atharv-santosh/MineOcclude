"""Focused fail-closed tests for the final Person B readiness package."""

from __future__ import annotations

import hashlib
import json
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from mineocclude.analysis import final_integration_readiness_v0_1 as readiness

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = REPOSITORY_ROOT / readiness.PACKAGE_DIRECTORY


def _canonical(value: Any) -> bytes:
    return readiness.canonical_json_bytes(value)


def _copy_package(tmp_path: Path) -> Path:
    destination = tmp_path / "package"
    shutil.copytree(PACKAGE_ROOT, destination)
    return destination


def _load(package: Path, name: str) -> dict[str, Any]:
    return json.loads((package / name).read_text(encoding="utf-8"))


def _write(package: Path, name: str, document: dict[str, Any]) -> None:
    (package / name).write_bytes(_canonical(document))


def _refresh_integrity(package: Path, *, chain: bool = False) -> None:
    """Refresh copied-package links while leaving the mutated field intact."""

    if chain:
        handoff = _load(package, "final_integration_handoff.json")
        for name in readiness.HASH_CHAIN_INPUTS:
            handoff["package_hash_chain"][name] = hashlib.sha256(
                (package / name).read_bytes()
            ).hexdigest()
        _write(package, "final_integration_handoff.json", handoff)
    receipt = _load(package, "integration_readiness_receipt.json")
    receipt["final_handoff_sha256"] = hashlib.sha256(
        (package / "final_integration_handoff.json").read_bytes()
    ).hexdigest()
    _write(package, "integration_readiness_receipt.json", receipt)
    inventory = _load(package, "sha256_inventory.json")
    for name in readiness.INVENTORIED_FILES:
        payload = (package / name).read_bytes()
        inventory["files"][name] = {
            "byte_size": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
        }
    _write(package, "sha256_inventory.json", inventory)


def _assert_rejected(package: Path) -> None:
    with pytest.raises(readiness.FinalIntegrationReadinessValidationError):
        readiness.validate_package(REPOSITORY_ROOT, package_root=package)


def test_actual_package_passes_with_distinct_scientific_decision() -> None:
    result = readiness.validate_package(REPOSITORY_ROOT)
    assert result["status"] == "PASS"
    assert result["validator_status"] == "PASS"
    assert result["integration_decision"] == "NOT_INTEGRATION_READY"
    assert result["frozen_step4_1_decision"] == "FAIL"
    assert result["all_assigned_steps_complete"] is False


def test_hash_chain_mutation_fails_closed(tmp_path: Path) -> None:
    package = _copy_package(tmp_path)
    handoff = _load(package, "final_integration_handoff.json")
    handoff["package_hash_chain"]["authority_binding.json"] = "0" * 64
    _write(package, "final_integration_handoff.json", handoff)
    _refresh_integrity(package)
    _assert_rejected(package)


def test_count_mutation_fails_closed(tmp_path: Path) -> None:
    package = _copy_package(tmp_path)
    handoff = _load(package, "final_integration_handoff.json")
    handoff["activation_row_count"] = 37_479
    _write(package, "final_integration_handoff.json", handoff)
    _refresh_integrity(package)
    _assert_rejected(package)


@pytest.mark.parametrize(
    ("name", "mutation"),
    [
        ("decision", lambda d: d.__setitem__("decision", "INTEGRATION_READY")),
        ("readiness", lambda d: d.__setitem__("all_assigned_steps_complete", True)),
    ],
)
def test_decision_or_readiness_mutation_fails_closed(
    tmp_path: Path, name: str, mutation: Callable[[dict[str, Any]], None]
) -> None:
    package = _copy_package(tmp_path / name)
    receipt = _load(package, "integration_readiness_receipt.json")
    mutation(receipt)
    _write(package, "integration_readiness_receipt.json", receipt)
    _refresh_integrity(package)
    _assert_rejected(package)


def test_main_authority_mutation_fails_closed(tmp_path: Path) -> None:
    package = _copy_package(tmp_path)
    authority = _load(package, "authority_binding.json")
    authority["verified_main_commit"] = "0" * 40
    _write(package, "authority_binding.json", authority)
    _refresh_integrity(package, chain=True)
    _assert_rejected(package)


def test_step4_1_failure_cannot_be_promoted(tmp_path: Path) -> None:
    package = _copy_package(tmp_path)
    evidence = _load(package, "evidence_validation.json")
    evidence["step4_1_decision"] = "PASS"
    _write(package, "evidence_validation.json", evidence)
    _refresh_integrity(package, chain=True)
    _assert_rejected(package)


@pytest.mark.parametrize(
    ("field", "value"),
    [("synthetic_fixtures_accepted_as_science", True), ("u4_authorized", True)],
)
def test_synthetic_or_u4_claim_fails_closed(
    tmp_path: Path, field: str, value: bool
) -> None:
    package = _copy_package(tmp_path / field)
    evidence = _load(package, "evidence_validation.json")
    evidence[field] = value
    _write(package, "evidence_validation.json", evidence)
    _refresh_integrity(package, chain=True)
    _assert_rejected(package)


def test_inventory_mutation_fails_closed(tmp_path: Path) -> None:
    package = _copy_package(tmp_path)
    inventory = _load(package, "sha256_inventory.json")
    inventory["files"]["roadmap_status.json"]["byte_size"] += 1
    _write(package, "sha256_inventory.json", inventory)
    _assert_rejected(package)


def test_certification_receipt_requires_exact_focused_result(tmp_path: Path) -> None:
    package = _copy_package(tmp_path)
    receipt = _load(package, "integration_readiness_receipt.json")
    receipt["certification_test"]["passed"] = 12
    _write(package, "integration_readiness_receipt.json", receipt)
    _refresh_integrity(package)
    _assert_rejected(package)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("command", "python -m pytest -q tests/analysis/not-the-certified-suite.py"),
        ("passed", 221),
        ("skipped", 1),
        ("result", "221 passed, 1 skipped"),
    ],
)
def test_focused_test_evidence_is_bound_to_exact_result(
    tmp_path: Path, field: str, value: Any
) -> None:
    package = _copy_package(tmp_path / field)
    receipt = _load(package, "integration_readiness_receipt.json")
    receipt["focused_test_evidence"][0][field] = value
    _write(package, "integration_readiness_receipt.json", receipt)
    _refresh_integrity(package)
    _assert_rejected(package)


def test_external_materialization_flags_cannot_be_omitted_or_promoted(
    tmp_path: Path,
) -> None:
    package = _copy_package(tmp_path / "dependency")
    dependency = _load(package, "dependency_status.json")
    external = dependency["person_a"]["ten_pilot_external_activation_index"]
    external.pop("repository_payload_present")
    _write(package, "dependency_status.json", dependency)
    _refresh_integrity(package, chain=True)
    _assert_rejected(package)

    package = _copy_package(tmp_path / "handoff")
    handoff = _load(package, "final_integration_handoff.json")
    handoff["external_activation_index"]["repository_payload_present"] = True
    _write(package, "final_integration_handoff.json", handoff)
    _refresh_integrity(package)
    _assert_rejected(package)


def test_main_and_c6a_authority_hashes_are_git_bound(tmp_path: Path) -> None:
    package = _copy_package(tmp_path / "ace")
    dependency = _load(package, "dependency_status.json")
    dependency["current_main_ace_closure"]["integration_manifest_sha256"] = "0" * 64
    _write(package, "dependency_status.json", dependency)
    _refresh_integrity(package, chain=True)
    _assert_rejected(package)

    package = _copy_package(tmp_path / "c6a")
    dependency = _load(package, "dependency_status.json")
    dependency["person_c"]["c6a_collection"]["episode_inventory_sha256"] = "0" * 64
    _write(package, "dependency_status.json", dependency)
    _refresh_integrity(package, chain=True)
    _assert_rejected(package)


def test_roadmap_checkpoint_and_closeout_identity_are_exact(tmp_path: Path) -> None:
    package = _copy_package(tmp_path / "checkpoint")
    roadmap = _load(package, "roadmap_status.json")
    roadmap["terminal_checkpoint"] += " (tampered)"
    _write(package, "roadmap_status.json", roadmap)
    _refresh_integrity(package, chain=True)
    _assert_rejected(package)

    package = _copy_package(tmp_path / "closeout")
    roadmap = _load(package, "roadmap_status.json")
    roadmap["previous_closeout"]["roadmap_matrix_sha256"] = "0" * 64
    _write(package, "roadmap_status.json", roadmap)
    _refresh_integrity(package, chain=True)
    _assert_rejected(package)


def test_dependency_blocker_set_is_exact(tmp_path: Path) -> None:
    package = _copy_package(tmp_path)
    dependency = _load(package, "dependency_status.json")
    dependency["unresolved_blockers"].append("unrecorded blocker")
    _write(package, "dependency_status.json", dependency)
    _refresh_integrity(package, chain=True)
    _assert_rejected(package)


def test_pending_producing_binding_is_fail_closed(tmp_path: Path) -> None:
    package = _copy_package(tmp_path / "mode")
    binding = _load(package, "producing_commit_binding.json")
    binding["mode"] = "PENDING_POST_COMMIT"
    binding["producing_commit"] = None
    binding["self_reference_explanation"] = (
        "The producing commit cannot be embedded in its own tree; this pending binding is accepted only before the first certification commit."
    )
    _write(package, "producing_commit_binding.json", binding)
    _refresh_integrity(package)
    _assert_rejected(package)

    package = _copy_package(tmp_path / "commit")
    binding = _load(package, "producing_commit_binding.json")
    binding["producing_commit"] = "0" * 40
    _write(package, "producing_commit_binding.json", binding)
    _refresh_integrity(package)
    _assert_rejected(package)


def test_external_prediction_hash_and_d_baseline_inventory_are_bound(
    tmp_path: Path,
) -> None:
    package = _copy_package(tmp_path)
    evidence = _load(package, "evidence_validation.json")
    outputs = evidence["completed_post_step4_1_outputs"]
    outputs["fitted_probes_oof_predictions"]["sha256"] = "0" * 64
    _write(package, "evidence_validation.json", evidence)
    _refresh_integrity(package, chain=True)
    _assert_rejected(package)

    package = _copy_package(tmp_path / "d-baseline")
    evidence = _load(package, "evidence_validation.json")
    evidence["completed_post_step4_1_outputs"]["person_d_baselines"]["sha256"][
        "raw_pixel_mu_oracle_blocks"
    ] = "0" * 64
    _write(package, "evidence_validation.json", evidence)
    _refresh_integrity(package, chain=True)
    _assert_rejected(package)


def test_git_object_verification_is_performed(monkeypatch: pytest.MonkeyPatch) -> None:
    original = readiness._git_blob
    tampered = {"done": False}

    def tamper(repository_root: Path, commit: str, path: str) -> bytes:
        payload = original(repository_root, commit, path)
        if commit != readiness.HANDOFF_COMMIT and not tampered["done"]:
            tampered["done"] = True
            return payload + b"x"
        return payload

    monkeypatch.setattr(readiness, "_git_blob", tamper)
    with pytest.raises(readiness.FinalIntegrationReadinessValidationError):
        readiness.validate_package(REPOSITORY_ROOT)
    assert tampered["done"] is True


def test_validation_is_read_only() -> None:
    before = {
        path.relative_to(REPOSITORY_ROOT): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in PACKAGE_ROOT.glob("*.json")
    }
    status_before = readiness._git_bytes(REPOSITORY_ROOT, "status", "--short")
    readiness.validate_package(REPOSITORY_ROOT)
    status_after = readiness._git_bytes(REPOSITORY_ROOT, "status", "--short")
    after = {
        path.relative_to(REPOSITORY_ROOT): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in PACKAGE_ROOT.glob("*.json")
    }
    assert before == after
    assert status_before == status_after


def test_strict_json_rejects_bom_duplicate_and_noncanonical() -> None:
    with pytest.raises(readiness.FinalIntegrationReadinessValidationError):
        readiness.load_strict_json(b"\xef\xbb\xbf{}\n", "bom")
    with pytest.raises(readiness.FinalIntegrationReadinessValidationError):
        readiness.load_strict_json(b'{"a": 1, "a": 2}\n', "duplicate", canonical=False)
    with pytest.raises(readiness.FinalIntegrationReadinessValidationError):
        readiness.load_strict_json(b'{"b": 1, "a": 2}\n', "order")
