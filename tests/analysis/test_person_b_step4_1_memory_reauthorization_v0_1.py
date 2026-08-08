"""Focused, non-scientific tests for the Step 4.1 memory reauthorization."""

from __future__ import annotations

import copy
import json
import subprocess
from pathlib import Path

import pytest

from scripts import validate_person_b_step4_1_memory_reauthorization_v0_1 as validator

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / validator.PACKAGE_RELATIVE_PATH


def _documents() -> dict[str, dict]:
    return {
        path.name: json.loads(path.read_text(encoding="utf-8"))
        for path in PACKAGE.glob("*.json")
    }


def test_package_validates_without_payloads_or_scientific_execution() -> None:
    result = validator.validate_package(ROOT, PACKAGE)
    assert result["accepted"] is True
    assert result["baseline_family_count"] == 8
    assert result["preprocessed_frame_count"] == 1695
    assert result["minimum_available_memory_gib"] == 20.0
    assert result["person_d_baseline_execution_performed"] is False
    assert result["final_b_vs_d_comparison_complete"] is False
    assert result["u4_output_inspected"] is False


def test_external_record_names_exact_new_d_head() -> None:
    record = _documents()["person_d_authorization_record.json"]
    validator._validate_external_auth(ROOT, record)
    record["authorized_runner_commit"] = validator.PERSON_D_MEMORY_IMPLEMENTATION_COMMIT
    with pytest.raises(validator.MemoryReauthorizationError, match="authorized_runner_commit"):
        validator._validate_external_auth(ROOT, record)


@pytest.mark.parametrize(
    ("physical", "available", "error"),
    [
        (19, 21, "memory_physical_low"),
        (21, 19, "memory_available_low"),
        (None, 21, "memory_physical_missing"),
        (21, None, "memory_available_missing"),
    ],
)
def test_memory_gate_fails_closed_for_low_or_missing_capacity(
    physical: int | None, available: int | None, error: str
) -> None:
    memory = {
        "physical_bytes": None if physical is None else physical * validator.BYTES_PER_GIB,
        "available_bytes": None if available is None else available * validator.BYTES_PER_GIB,
    }
    with pytest.raises(validator.MemoryReauthorizationError, match=error):
        validator.validate_memory_gate(memory)


def test_memory_gate_exact_threshold_passes_and_swap_does_not_substitute() -> None:
    passed = validator.validate_memory_gate(
        {
            "physical_bytes": 20 * validator.BYTES_PER_GIB,
            "available_bytes": 20 * validator.BYTES_PER_GIB,
            "swap_total_bytes": 0,
        }
    )
    assert passed["passed"] is True
    assert passed["swap_counted_as_capacity"] is False
    with pytest.raises(validator.MemoryReauthorizationError, match="memory_physical_low"):
        validator.validate_memory_gate(
            {
                "physical_bytes": 19 * validator.BYTES_PER_GIB,
                "available_bytes": 20 * validator.BYTES_PER_GIB,
                "swap_total_bytes": 100 * validator.BYTES_PER_GIB,
            }
        )


def test_finite_cgroup_capacity_and_missing_usage_fail_closed() -> None:
    with pytest.raises(validator.MemoryReauthorizationError, match="memory_available_low"):
        validator.validate_memory_gate(
            {
                "physical_bytes": 64 * validator.BYTES_PER_GIB,
                "available_bytes": 64 * validator.BYTES_PER_GIB,
                "cgroup_limit_bytes": 24 * validator.BYTES_PER_GIB,
                "cgroup_usage_bytes": 5 * validator.BYTES_PER_GIB,
            }
        )
    with pytest.raises(validator.MemoryReauthorizationError, match="memory_cgroup_missing"):
        validator.validate_memory_gate(
            {
                "physical_bytes": 64 * validator.BYTES_PER_GIB,
                "available_bytes": 64 * validator.BYTES_PER_GIB,
                "cgroup_limit_bytes": 24 * validator.BYTES_PER_GIB,
            }
        )


def test_command_auth_payload_memory_and_order_requirements_fail_closed() -> None:
    commands = _documents()["production_commands.json"]
    validator._validate_commands(commands)
    missing_auth = copy.deepcopy(commands)
    missing_auth["production_run_command"] = missing_auth["production_run_command"].replace(
        "--authorization-record-path", "--omitted-authorization-record-path", 1
    )
    with pytest.raises(validator.MemoryReauthorizationError, match="authorization"):
        validator._validate_commands(missing_auth)
    missing_payload = copy.deepcopy(commands)
    missing_payload["production_run_command"] = missing_payload["production_run_command"].replace(
        "--verify-payloads", "", 1
    )
    with pytest.raises(validator.MemoryReauthorizationError, match="payload"):
        validator._validate_commands(missing_payload)
    missing_memory = copy.deepcopy(commands)
    missing_memory["authorized_production_chain"] = missing_memory["authorized_production_chain"].replace(
        "runtime-preflight", "omitted-preflight", 1
    )
    with pytest.raises(validator.MemoryReauthorizationError, match="command_order"):
        validator._validate_commands(missing_memory)


def test_d_checkout_contract_rejects_wrong_head_and_dirty_worktree(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    checkout = tmp_path / "d"
    checkout.mkdir()
    original = validator._git_text

    def fake_git(path: Path, *args: str) -> str:
        if args == ("branch", "--show-current"):
            return validator.PERSON_D_BRANCH
        if args == ("rev-parse", "HEAD"):
            return validator.PERSON_D_RUNNER_COMMIT
        if args == ("status", "--porcelain"):
            return ""
        if args == ("cat-file", "-t", validator.PERSON_D_RUNNER_COMMIT):
            return "commit"
        return original(path, *args)

    monkeypatch.setattr(validator, "_git_text", fake_git)
    assert validator.validate_d_checkout(checkout)["passed"] is True
    monkeypatch.setattr(
        validator,
        "_git_text",
        lambda path, *args: "0" * 40
        if args == ("rev-parse", "HEAD")
        else fake_git(path, *args),
    )
    with pytest.raises(validator.MemoryReauthorizationError, match="d_wrong_head"):
        validator.validate_d_checkout(checkout)
    monkeypatch.setattr(
        validator,
        "_git_text",
        lambda path, *args: validator.PERSON_D_RUNNER_COMMIT
        if args == ("rev-parse", "HEAD")
        else ("dirty" if args == ("status", "--porcelain") else fake_git(path, *args)),
    )
    with pytest.raises(validator.MemoryReauthorizationError, match="d_dirty_worktree"):
        validator.validate_d_checkout(checkout)


def test_resume_state_rejects_traversal_and_unknown_family(tmp_path: Path) -> None:
    output = tmp_path / "output"
    output.mkdir()
    state = {"schema_version": "1.0", "families": {"unknown": {"status": "completed", "output_path": "x.json"}}}
    (output / "run_state.json").write_text(json.dumps(state), encoding="utf-8")
    with pytest.raises(validator.MemoryReauthorizationError, match="resume_unknown_family"):
        validator.validate_output_resume_state(output)
    state["families"] = {"last_seen": {"status": "completed", "output_path": "../escape.json"}}
    (output / "run_state.json").write_text(json.dumps(state), encoding="utf-8")
    with pytest.raises(validator.MemoryReauthorizationError, match="resume_output_path_unsafe"):
        validator.validate_output_resume_state(output)


def test_reuse_contract_rejects_identity_size_pilot_mapping_and_leakage_mutations() -> None:
    reuse = _documents()["materialized_input_reuse.json"]
    validator._validate_reuse_contract(reuse)
    for field, mutation, error in (
        ("capture_packages", lambda value: value[0].update({"sha256": "0" * 64}), "capture identities"),
        ("capture_packages", lambda value: value[0].update({"byte_size": 1}), "capture identities"),
        ("accepted_pilot_ids", lambda value: value.__setitem__(0, "wrong"), "pilots"),
        ("signed_explicit_mapping", lambda value: value.__setitem__(0, 0), "mapping"),
    ):
        mutated = copy.deepcopy(reuse)
        mutation(mutated[field])
        with pytest.raises(validator.MemoryReauthorizationError, match=error):
            validator._validate_reuse_contract(mutated)


def test_frame_payload_revalidation_hashes_all_rows_and_rejects_path_or_hash_drift(
    tmp_path: Path,
) -> None:
    payload = b"\x00\x00\x80?"
    (tmp_path / "payload.f32le").write_bytes(payload)
    records = []
    for index in range(1695):
        trajectory = validator.EXPECTED_PILOTS[index % len(validator.EXPECTED_PILOTS)]
        frame_idx = index // len(validator.EXPECTED_PILOTS)
        records.append(
            {
                "trajectory_id": trajectory,
                "model_frame_idx": frame_idx,
                "output_relative_path": "payload.f32le",
                "payload_byte_size": len(payload),
                "payload_sha256": validator._sha256(payload),
                "global_frame_identity": f"{trajectory}:{frame_idx}",
                "target_binding": {"target_id": f"{trajectory}:{frame_idx}:regime_a_primary_v1"},
                "fold_binding": {"fold_idx": index % 5},
                "dtype": validator.REQUIRED_PAYLOAD_DTYPE,
                "layout": validator.REQUIRED_PAYLOAD_LAYOUT,
                "color_order": validator.REQUIRED_PAYLOAD_COLOR_ORDER,
                "payload_format": validator.REQUIRED_PAYLOAD_FORMAT,
                "shape": list(validator.REQUIRED_PAYLOAD_SHAPE),
            }
        )
    frame = {
        "artifact_count": 1695,
        "unique_frame_count": 1695,
        "duplicate_frame_count": 0,
        "missing_frame_count": 0,
        "fold_manifest_sha256": validator.FOLD_MANIFEST_SHA256,
        "target_manifest_sha256": validator.TARGET_MANIFEST_SHA256,
        "records": records,
    }
    result = validator._verify_frame_payloads(frame, tmp_path)
    assert result["actual_frame_count"] == 1695
    assert result["payload_hashes_revalidated"] is True

    drifted = copy.deepcopy(frame)
    drifted["records"][0]["payload_sha256"] = "0" * 64
    with pytest.raises(validator.MemoryReauthorizationError, match="payload_hash_mismatch"):
        validator._verify_frame_payloads(drifted, tmp_path)

    escaped = copy.deepcopy(frame)
    escaped["records"][0]["output_relative_path"] = "../escape.f32le"
    with pytest.raises(validator.MemoryReauthorizationError, match="payload_path_unsafe"):
        validator._verify_frame_payloads(escaped, tmp_path)


def test_real_frozen_manifest_semantics_cover_rows_mapping_and_leakage() -> None:
    frame = json.loads(
        subprocess.check_output(
            [
                "git",
                "show",
                f"{validator.PERSON_A_FRAME_COMMIT}:{validator.FRAME_MANIFEST_PATH}",
            ],
            cwd=ROOT,
        )
    )
    fold = json.loads(
        (ROOT / validator.FOLD_MANIFEST_PATH).read_text(encoding="utf-8")
    )
    target = json.loads(
        (ROOT / validator.TARGET_MANIFEST_PATH).read_text(encoding="utf-8")
    )
    result = validator.validate_reuse_semantics(frame, fold, target)
    assert result["row_count"] == 1695
    short = copy.deepcopy(frame)
    short["records"].pop()
    with pytest.raises(validator.MemoryReauthorizationError, match="frame records"):
        validator.validate_reuse_semantics(short, fold, target)
    wrong_mapping = copy.deepcopy(fold)
    wrong_mapping["layout_assignments"][0]["fold_idx"] = 0
    with pytest.raises(validator.MemoryReauthorizationError, match="layout assignment"):
        validator.validate_reuse_semantics(frame, wrong_mapping, target)
    leakage = copy.deepcopy(fold)
    leakage["memberships"][0]["layout_id"] = "layout_01"
    leakage["memberships"][0]["fold_idx"] = 2
    with pytest.raises(validator.MemoryReauthorizationError, match="trajectory spans folds"):
        validator.validate_reuse_semantics(frame, leakage, target)


def test_resume_direct_input_and_family_lineage_rules_are_explicit() -> None:
    compatibility = _documents()["compatibility_evidence.json"]
    compatibility["direct_pixel_features_by_key_bypass_authorized"] = True
    with pytest.raises(validator.MemoryReauthorizationError, match="direct pixel bypass"):
        validator._validate_compatibility(ROOT, compatibility)


def test_canonical_json_and_inventory_are_exact() -> None:
    documents = _documents()
    for name in validator.DOCUMENT_NAMES:
        raw = (PACKAGE / name).read_bytes()
        assert raw == validator.canonical_json_bytes(documents[name])
    validator._validate_inventory(PACKAGE, documents)
    assert documents["sha256_inventory.json"]["inventory_excludes_self"] is True
