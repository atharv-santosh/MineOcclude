from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scripts import (
    validate_person_b_step4_1_final_person_d_authorization_v0_1 as validator,
)

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / validator.PACKAGE_RELATIVE_PATH


def _documents() -> dict[str, dict]:
    return {
        path.name: json.loads(path.read_text(encoding="utf-8"))
        for path in PACKAGE.glob("*.json")
    }


def test_final_authorization_package_validates_without_payload_bytes() -> None:
    result = validator.validate_package(ROOT, PACKAGE)
    assert result["accepted"] is True
    assert result["baseline_family_count"] == 8
    assert result["preprocessed_frame_count"] == 1695
    assert result["signed_explicit_mapping_verified"] is True
    assert result["person_d_execution_ready"] is True
    assert result["execution_performed"] is False
    assert result["final_comparison_complete"] is False
    assert result["step4_1_complete"] is False
    assert result["u4_output_inspected"] is False


@pytest.mark.parametrize(
    ("kwargs", "error"),
    [
        ({"branch": "role/person-b-analysis"}, "wrong_branch"),
        ({"worktree_dirty": True}, "dirty_worktree"),
        ({"exporter_commit_is_ancestor": False}, "exporter_commit_not_ancestor"),
        ({"head": "4915252ce5a9f346fc39f1f2583478949c3787f5"}, "head_not_authorized"),
    ],
)
def test_runtime_authorization_fails_closed(kwargs: dict, error: str) -> None:
    facts = {
        "branch": validator.PERSON_D_BRANCH,
        "head": validator.PERSON_D_RUNNER_COMMIT,
        "worktree_dirty": False,
        "exporter_commit_is_ancestor": True,
        "authorized_runner_commit": validator.PERSON_D_RUNNER_COMMIT,
    }
    facts.update(kwargs)
    errors = validator.validate_runtime_context(**facts)
    assert any(error in item for item in errors)


def test_family_order_mapping_and_counts_are_exact() -> None:
    documents = _documents()
    authority = documents["authority_binding.json"]
    authority["baseline_families"] = list(reversed(authority["baseline_families"]))
    with pytest.raises(validator.FinalPersonDAuthorizationError):
        validator._validate_authority(authority)

    authority = _documents()["authority_binding.json"]
    authority["configuration"]["time_only"]["fit_scope"] = "outer-training-folds-only"
    with pytest.raises(validator.FinalPersonDAuthorizationError):
        validator._validate_authority(authority)

    authority = _documents()["authority_binding.json"]
    authority["contract"]["assignment_by_ordered_layout"] = [0, 1, 2, 3, 4]
    with pytest.raises(validator.FinalPersonDAuthorizationError):
        validator._validate_authority(authority)


def test_predictions_execution_and_completion_boundaries_fail_closed() -> None:
    documents = _documents()
    authority = copy.deepcopy(documents["authority_binding.json"])
    authority["person_b_predictions"]["direct_input_to_person_d"] = True
    with pytest.raises(validator.FinalPersonDAuthorizationError):
        validator._validate_authority(authority)

    decision = copy.deepcopy(documents["final_authorization_decision.json"])
    decision["execution_performed"] = True
    with pytest.raises(validator.FinalPersonDAuthorizationError):
        validator._validate_decision(decision)

    documents = _documents()
    documents["output_closure_requirements.json"]["scientific_execution_performed"] = True
    with pytest.raises(validator.FinalPersonDAuthorizationError):
        validator._validate_safety_claims(documents)

    decision = copy.deepcopy(documents["final_authorization_decision.json"])
    decision["step4_1_complete"] = True
    with pytest.raises(validator.FinalPersonDAuthorizationError):
        validator._validate_decision(decision)


def test_commands_require_real_authorization_path_and_materialization() -> None:
    commands = _documents()["production_commands.json"]
    validator._validate_commands(commands)

    missing_materialize = copy.deepcopy(commands)
    missing_materialize["materialize_command"] = ""
    with pytest.raises(validator.FinalPersonDAuthorizationError):
        validator._validate_commands(missing_materialize)

    placeholder = copy.deepcopy(commands)
    placeholder["run_command"] = placeholder["run_command"].replace(
        "person-d-step4-1-production-v0-1", "<output-root>"
    )
    with pytest.raises(validator.FinalPersonDAuthorizationError):
        validator._validate_commands(placeholder)

    missing_record = copy.deepcopy(commands)
    missing_record["run_command"] = missing_record["run_command"].replace(
        validator.AUTHORIZATION_RECORD_ABSOLUTE_PATH, ""
    )
    with pytest.raises(validator.FinalPersonDAuthorizationError):
        validator._validate_commands(missing_record)


def test_manifest_identity_mutation_fails_closed() -> None:
    authority = _documents()["authority_binding.json"]
    authority["frame_manifest"]["byte_size"] += 1
    with pytest.raises(validator.FinalPersonDAuthorizationError):
        validator._validate_authority(authority)


def test_d_remote_head_must_be_exact_authorized_head() -> None:
    validator._validate_remote_head(ROOT, validator.PERSON_D_RUNNER_COMMIT)
    with pytest.raises(validator.FinalPersonDAuthorizationError):
        validator._validate_remote_head(ROOT, "4915252ce5a9f346fc39f1f2583478949c3787f5")


@pytest.mark.parametrize(
    "missing_ancestor",
    [validator.PERSON_D_SIGNED_COMMIT, validator.PERSON_D_EXPORTER_COMMIT, validator.PERSON_D_CLI_COMMIT],
)
def test_d_source_ancestry_fails_closed(
    monkeypatch: pytest.MonkeyPatch, missing_ancestor: str
) -> None:
    evidence = _documents()["person_d_compatibility_evidence.json"]
    real_is_ancestor = validator._is_ancestor

    def fake_is_ancestor(repo_root: Path, ancestor: str, descendant: str) -> bool:
        if ancestor == missing_ancestor and descendant == validator.PERSON_D_RUNNER_COMMIT:
            return False
        return real_is_ancestor(repo_root, ancestor, descendant)

    monkeypatch.setattr(validator, "_is_ancestor", fake_is_ancestor)
    with pytest.raises(validator.FinalPersonDAuthorizationError, match="git_ancestry_mismatch"):
        validator._validate_git_sources(ROOT, evidence)


def test_package_json_is_canonical_and_inventory_excludes_itself() -> None:
    for path in PACKAGE.glob("*.json"):
        raw = path.read_bytes()
        assert raw == validator.canonical_json_bytes(json.loads(raw.decode("utf-8")))
    documents = _documents()
    inventory = documents["sha256_inventory.json"]
    assert inventory["inventory_excludes_self"] is True
    assert all(
        "sha256_inventory.json" not in key for key in inventory["files"]
    )
