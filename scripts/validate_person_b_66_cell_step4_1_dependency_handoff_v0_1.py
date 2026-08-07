"""Fail-closed validation for Person B's 66-cell Step 4.1 D handoff.

This validator only validates immutable identities and preparation contracts. It
does not execute a probe, fit a baseline, calculate metrics, inspect U4, or
rewrite a Person C artifact.  The C accepted manifest is read from its exact
Git object because the Person C branch is intentionally not merged here.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

PACKAGE_RELATIVE = Path("docs/status/person_b_66_cell_step4_1_dependency_handoff_v0_1")
FOLD_RELATIVE = Path("docs/status/person_b_66_cell_preactivation_v0_1/fold_manifest.json")
ORACLE_RELATIVE = Path(
    "docs/status/person_b_66_cell_oracle_target_v0_1/oracle_target_manifest.json"
)
ORACLE_RECORDS_RELATIVE = Path(
    "docs/status/person_b_66_cell_oracle_target_v0_1/oracle_target_records.jsonl"
)
C_ACCEPTED_MANIFEST_PATH = (
    "docs/status/person_c_c7_mvp_handoff_v0_1/trajectories_mvp_manifest.json"
)
C_STRICT_JOIN_MANIFEST_PATH = (
    "docs/status/person_c_66_cell_strict_visibility_v0_1/visibility_join_manifest.json"
)
C_COMMIT = "e908ead4a7ff5ab3ae310bb846969a7859fdb26b"
C_ACCEPTED_MANIFEST_SHA256 = (
    "96ba43e15bc024aeaef7c519fa4ece0a4afe0bb0e877501dffaca44fee927ff7"
)
C_STRICT_JOIN_MANIFEST_SHA256 = (
    "8e03d6564c3a5d17e6199af258708bd8526842410c78a7f58330df9e0bf960cc"
)
D_COMMIT = "8cd2fdfc7759b285a7748ccdb4564e475b3ce1cf"
D_REMOTE_REF = "refs/remotes/origin/role/person-d-baselines"
FOLD_SHA256 = "86739975882f4926c3398d5bfa21611daf06c579b3893809eb385e8dcd03001d"
FOLD_SIZE_BYTES = 557603
ORACLE_SHA256 = "c064e1856be67ebab95cbcb07b80009729c396f2398b15b4dec57458b73b8ac9"
ORACLE_SIZE_BYTES = 43262
ORACLE_RECORDS_SHA256 = (
    "d95c83518d2ad322e6862f5460727382511fe831c0c6658a6cf72c9f7a8858b1"
)
ORACLE_RECORDS_SIZE_BYTES = 2953366
OLD_FOLD_SHA256 = "53ca938c6ae936c3ecb6e6e8d95a3fda152f5fa130b52e7a000d297810738d71"
OLD_ORACLE_SHA256 = "afcf3afae00db6330665afc5964608c6db89eeac3767c9486d8ba0a218858282"
OLD_METRIC_SHA256 = "c471fddb9bdc1a87c2f7e11ad8dc55db9e407f0ea45a2e038f668bda178ad0a7"
EXPECTED_LAYOUT_TO_FOLD = [
    {"fold_idx": 3, "layout_id": "layout_01"},
    {"fold_idx": 2, "layout_id": "layout_02"},
    {"fold_idx": 4, "layout_id": "layout_03"},
    {"fold_idx": 4, "layout_id": "layout_04"},
    {"fold_idx": 1, "layout_id": "layout_05"},
    {"fold_idx": 0, "layout_id": "layout_06"},
]
INVENTORY_FILES = (
    "authority_binding.json",
    "consumer_validation_receipt.json",
    "fold_target_binding.json",
    "metric_table_dependency.json",
    "step4_1_dependency_handoff.json",
)
PHASE3_RECEIPT_RELATIVE = Path(
    "docs/status/person_b_phase3_66_cell_handoff_v0_1/c_consumer_validation_receipt.json"
)
PHASE3_CLOSURE_RELATIVE = Path(
    "docs/status/person_b_phase3_66_cell_handoff_v0_1/phase3_closure_recommendation.json"
)
PHASE3_STATUS_RELATIVE = Path(
    "docs/status/person_b_phase3_66_cell_handoff_v0_1/phase3_status.json"
)


class ValidationError(ValueError):
    """Raised when an exact contract identity or preparation invariant fails."""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValidationError(f"invalid JSON: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValidationError(f"expected JSON object: {path}")
    return value


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def _canonical_json(path: Path, value: dict[str, Any]) -> bool:
    expected = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    return path.read_bytes() == expected.encode("utf-8")


def _git_blob(repository: Path, commit: str, relative_path: str) -> bytes:
    spec = f"{commit}:{relative_path}"
    result = subprocess.run(
        ["git", "-C", str(repository), "cat-file", "blob", spec],
        capture_output=True,
        check=False,
    )
    _require(result.returncode == 0, f"missing Git blob: {spec}")
    return result.stdout


def _validate_d_commit_authority(repository: Path) -> None:
    """Require D's exact terminal handoff commit and remote branch ancestry."""

    commit_check = subprocess.run(
        ["git", "-C", str(repository), "cat-file", "-e", f"{D_COMMIT}^{{commit}}"],
        capture_output=True,
        check=False,
    )
    _require(commit_check.returncode == 0, "Person D authority commit is missing")
    branch_check = subprocess.run(
        ["git", "-C", str(repository), "merge-base", "--is-ancestor", D_COMMIT, D_REMOTE_REF],
        capture_output=True,
        check=False,
    )
    _require(
        branch_check.returncode == 0,
        "Person D authority commit is not reachable from origin/role/person-d-baselines",
    )


def _validate_inventory(package: Path) -> dict[str, Any]:
    inventory_path = package / "sha256_inventory.json"
    inventory = _read_json(inventory_path)
    _require(_canonical_json(inventory_path, inventory), "inventory is not canonical JSON")
    _require(inventory.get("inventory_excludes_self") is True, "inventory must exclude itself")
    files = inventory.get("files")
    _require(isinstance(files, dict), "inventory files must be an object")
    _require(set(files) == set(INVENTORY_FILES), "inventory file set is incomplete or broadened")
    for name in INVENTORY_FILES:
        path = package / name
        _require(path.is_file(), f"missing handoff artifact: {path}")
        data = path.read_bytes()
        entry = files[name]
        _require(isinstance(entry, dict), f"invalid inventory entry: {name}")
        _require(entry.get("sha256") == _sha256(data), f"inventory SHA mismatch: {name}")
        _require(entry.get("size_bytes") == len(data), f"inventory size mismatch: {name}")
    return inventory


def _validate_c_authority(repository: Path) -> dict[str, Any]:
    manifest_bytes = _git_blob(repository, C_COMMIT, C_ACCEPTED_MANIFEST_PATH)
    _require(_sha256(manifest_bytes) == C_ACCEPTED_MANIFEST_SHA256, "C accepted manifest hash mismatch")
    accepted = json.loads(manifest_bytes.decode("utf-8"))
    _require(accepted.get("accepted_count") == 66, "C accepted count is not 66")
    _require(accepted.get("excluded_count") == 0, "C accepted manifest has exclusions")
    rows = accepted.get("records")
    _require(isinstance(rows, list) and len(rows) == 66, "C accepted manifest rows are incomplete")
    trajectory_ids = [row.get("trajectory_id") for row in rows]
    _require(all(isinstance(value, str) and value for value in trajectory_ids), "C trajectory identity missing")
    _require(len(set(trajectory_ids)) == 66, "C trajectory identities are not unique")
    _require(all(row.get("accepted") is True for row in rows), "C manifest contains unaccepted rows")

    strict_bytes = _git_blob(repository, C_COMMIT, C_STRICT_JOIN_MANIFEST_PATH)
    _require(_sha256(strict_bytes) == C_STRICT_JOIN_MANIFEST_SHA256, "C strict-join manifest hash mismatch")
    strict = json.loads(strict_bytes.decode("utf-8"))
    _require(strict.get("trajectory_count") == 66, "C strict join trajectory count mismatch")
    _require(strict.get("unique_frame_key_count") == 2468, "C strict join frame count mismatch")
    _require(strict.get("sources", {}).get("person_c_accepted_manifest_sha256") == C_ACCEPTED_MANIFEST_SHA256,
             "C strict join is not bound to the accepted manifest")
    return {
        "accepted_count": len(rows),
        "accepted_manifest_sha256": _sha256(manifest_bytes),
        "strict_join_manifest_sha256": _sha256(strict_bytes),
        "trajectory_ids": trajectory_ids,
    }


def _validate_scope_binding(package: Path, repository: Path) -> dict[str, Any]:
    fold_path = repository / FOLD_RELATIVE
    oracle_path = repository / ORACLE_RELATIVE
    oracle_records_path = repository / ORACLE_RECORDS_RELATIVE
    _require(fold_path.is_file(), f"missing fold manifest: {fold_path}")
    _require(oracle_path.is_file(), f"missing oracle target manifest: {oracle_path}")
    _require(oracle_records_path.is_file(), f"missing oracle target records: {oracle_records_path}")
    fold_bytes = fold_path.read_bytes()
    oracle_bytes = oracle_path.read_bytes()
    oracle_records_bytes = oracle_records_path.read_bytes()
    _require(_sha256(fold_bytes) == FOLD_SHA256, "66-cell fold manifest SHA mismatch")
    _require(len(fold_bytes) == FOLD_SIZE_BYTES, "66-cell fold manifest size mismatch")
    _require(_sha256(oracle_bytes) == ORACLE_SHA256, "66-cell oracle manifest SHA mismatch")
    _require(len(oracle_bytes) == ORACLE_SIZE_BYTES, "66-cell oracle manifest size mismatch")
    _require(
        _sha256(oracle_records_bytes) == ORACLE_RECORDS_SHA256,
        "66-cell oracle target records SHA mismatch",
    )
    _require(
        len(oracle_records_bytes) == ORACLE_RECORDS_SIZE_BYTES,
        "66-cell oracle target records size mismatch",
    )
    _require(FOLD_SHA256 != OLD_FOLD_SHA256 and ORACLE_SHA256 != OLD_ORACLE_SHA256,
             "66-cell package accidentally uses ten-pilot identity")

    fold = json.loads(fold_bytes.decode("utf-8"))
    oracle = json.loads(oracle_bytes.decode("utf-8"))
    target_records: list[dict[str, Any]] = []
    for line_number, line in enumerate(oracle_records_bytes.splitlines(), start=1):
        try:
            record = json.loads(line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValidationError(f"invalid oracle target record line {line_number}: {exc}") from exc
        _require(isinstance(record, dict), f"oracle target record {line_number} is not an object")
        target_records.append(record)
    _require(len(target_records) == 2108, "oracle target record count mismatch")
    target_keys = [(row.get("trajectory_id"), row.get("model_frame_idx")) for row in target_records]
    _require(
        all(isinstance(trajectory_id, str) and isinstance(frame_idx, int) for trajectory_id, frame_idx in target_keys),
        "oracle target row identity is incomplete",
    )
    _require(len(set(target_keys)) == len(target_keys), "oracle target row identities are duplicated")
    _require(
        all(row.get("target_schema_version") == "person-b-oracle-target-v0.1" for row in target_records),
        "oracle target row schema changed",
    )
    _require(all(row.get("synthetic") is False for row in target_records), "synthetic oracle target row present")
    _require(fold.get("fold_manifest_schema_version") == "person-b-66-cell-fold-manifest-v0.1",
             "unexpected fold schema")
    _require(fold.get("person_c_accepted_manifest_sha256") == C_ACCEPTED_MANIFEST_SHA256,
             "fold is not bound to C accepted data")
    _require(fold.get("model_frame_key_count") == 2468, "fold model-frame count mismatch")
    memberships = fold.get("memberships")
    _require(isinstance(memberships, list) and len(memberships) == 2468, "fold membership count mismatch")
    keys = [(row.get("trajectory_id"), row.get("model_frame_idx")) for row in memberships]
    _require(all(isinstance(row[0], str) and isinstance(row[1], int) for row in keys),
             "fold row identity is incomplete")
    _require(len(set(keys)) == len(keys), "fold row identities are duplicated")
    _require(all(row.get("fold_idx") in range(5) for row in memberships), "fold index out of range")
    _require(fold.get("layout_assignments") == EXPECTED_LAYOUT_TO_FOLD, "layout-to-fold mapping changed")
    _require(oracle.get("oracle_package_schema_version") == "person-b-66-cell-oracle-target-v0.1",
             "unexpected oracle schema")
    _require(oracle.get("provenance", {}).get("person_c_accepted_manifest_sha256") == C_ACCEPTED_MANIFEST_SHA256,
             "oracle is not bound to C accepted data")
    _require(oracle.get("oracle_target_row_count") == 2108, "oracle target row count mismatch")
    target_schema = oracle.get("target_schema", {})
    _require(target_schema.get("join_key") == ["trajectory_id", "model_frame_idx"],
             "oracle target join key changed")
    _require(oracle.get("u1_u3_executed") is False, "scientific U1-U3 execution is not allowed")
    _require(oracle.get("u4_executed") is False, "U4 execution is not allowed")
    return {
        "fold_sha256": _sha256(fold_bytes),
        "fold_size_bytes": len(fold_bytes),
        "oracle_sha256": _sha256(oracle_bytes),
        "oracle_size_bytes": len(oracle_bytes),
        "oracle_records_sha256": _sha256(oracle_records_bytes),
        "oracle_records_size_bytes": len(oracle_records_bytes),
        "oracle_records_count": len(target_records),
        "membership_count": len(memberships),
        "oracle_target_row_count": oracle["oracle_target_row_count"],
    }


def _validate_package_content(
    package: Path, repository: Path, scope: dict[str, Any], c: dict[str, Any]
) -> dict[str, Any]:
    for name in INVENTORY_FILES:
        value = _read_json(package / name)
        _require(_canonical_json(package / name, value), f"noncanonical JSON: {name}")
    authority = _read_json(package / "authority_binding.json")
    _require(authority.get("c_accepted_data_authority", {}).get("accepted_manifest_sha256") == c["accepted_manifest_sha256"],
             "authority binding C hash mismatch")
    _require(authority.get("d_dependency_contract", {}).get("source_commit") == D_COMMIT,
             "D dependency authority mismatch")
    _validate_d_commit_authority(repository)
    binding = _read_json(package / "fold_target_binding.json")
    _require(binding["fold_assignment"]["fold_manifest_sha256"] == scope["fold_sha256"], "fold binding hash mismatch")
    _require(binding["oracle_target"]["oracle_target_manifest_sha256"] == scope["oracle_sha256"], "oracle binding hash mismatch")
    _require(
        binding["oracle_target"]["oracle_target_records_sha256"] == scope["oracle_records_sha256"],
        "oracle target records hash mismatch",
    )
    _require(
        binding["oracle_target"]["oracle_target_records_size_bytes"] == scope["oracle_records_size_bytes"],
        "oracle target records size mismatch",
    )
    _require(binding["accepted_data_manifest_sha256"] == c["accepted_manifest_sha256"], "binding C hash mismatch")
    handoff = _read_json(package / "step4_1_dependency_handoff.json")
    _require(handoff.get("fold_manifest_sha256") == scope["fold_sha256"], "handoff fold hash mismatch")
    _require(handoff.get("oracle_target_sha256") == scope["oracle_sha256"], "handoff oracle hash mismatch")
    _require(handoff.get("production_scope") == "66_cell_matrix", "handoff is not 66-cell scoped")
    metric = _read_json(package / "metric_table_dependency.json")
    _require(metric.get("status") == "BLOCKED", "metric dependency must remain blocked")
    _require(metric.get("current_66_cell_metric_table") is None, "fabricated 66-cell metric table path")
    legacy = metric.get("legacy_metric_table", {})
    _require(legacy.get("sha256") == OLD_METRIC_SHA256, "legacy metric identity changed")
    _require(legacy.get("accepted_as_current_66_cell_metric_table") is False,
             "legacy ten-pilot metric was relabelled")
    receipt = _read_json(package / "consumer_validation_receipt.json")
    _require(receipt.get("status") == "PASS", "C consumer validation did not pass")
    _require(receipt.get("phase3_step3_3_joined_package_status") == "PASS",
             "Phase 3 Step 3.3 consumer validation did not pass")
    _require(receipt.get("phase3_consumer_validation_status") == "PASS",
             "Phase 3 consumer validation status mismatch")
    _require(receipt.get("phase3_closure_recommendation") == "READY",
             "Phase 3 closure recommendation mismatch")
    _require(receipt.get("phase3_independent_final_verification") == "PENDING",
             "Phase 3 independent verification status mismatch")
    _require(receipt.get("phase3_overall_status") == "IN_PROGRESS",
             "Phase 3 overall status must remain in progress")
    phase3_receipt_path = repository / PHASE3_RECEIPT_RELATIVE
    _require(
        receipt.get("phase3_consumer_validation_receipt_path")
        == PHASE3_RECEIPT_RELATIVE.as_posix(),
        "Phase 3 consumer receipt path mismatch",
    )
    _require(phase3_receipt_path.is_file(), "missing Phase 3 consumer validation receipt")
    phase3_receipt = _read_json(phase3_receipt_path)
    _require(phase3_receipt.get("decision") == "PASS", "Phase 3 consumer receipt is not PASS")
    _require(
        phase3_receipt.get("accepted_manifest_sha256") == c["accepted_manifest_sha256"],
        "Phase 3 receipt C manifest hash mismatch",
    )
    _require(phase3_receipt.get("accepted_trajectory_count") == 66, "Phase 3 receipt trajectory count mismatch")
    _require(phase3_receipt.get("unique_primary_key_count") == 2468, "Phase 3 receipt key count mismatch")
    phase3_closure = _read_json(repository / PHASE3_CLOSURE_RELATIVE)
    _require(phase3_closure.get("step_3_3") == "PASS", "Phase 3 closure Step 3.3 mismatch")
    _require(phase3_closure.get("phase3_closure_recommendation") == "READY", "Phase 3 closure recommendation mismatch")
    _require(phase3_closure.get("independent_final_verification") == "PENDING", "Phase 3 closure verification must remain pending")
    phase3_status = _read_json(repository / PHASE3_STATUS_RELATIVE)
    _require(phase3_status.get("overall_phase_3") == "IN_PROGRESS", "Phase 3 formal closure was silently completed")
    return {"status": "PASS", "metric_table_status": "BLOCKED"}


def validate(repository: Path, package: Path | None = None) -> dict[str, Any]:
    repository = repository.resolve()
    package = (repository / PACKAGE_RELATIVE if package is None else package).resolve()
    _require(package.is_dir(), f"missing package: {package}")
    _validate_inventory(package)
    c = _validate_c_authority(repository)
    scope = _validate_scope_binding(package, repository)
    status = _validate_package_content(package, repository, scope, c)
    return {
        "accepted_c_trajectory_count": c["accepted_count"],
        "c_manifest_consumer_validation": "PASS",
        "fold_manifest_sha256": scope["fold_sha256"],
        "metric_table_dependency": status["metric_table_status"],
        "oracle_target_sha256": scope["oracle_sha256"],
        "oracle_records_sha256": scope["oracle_records_sha256"],
        "oracle_records_count": scope["oracle_records_count"],
        "scientific_execution_performed": False,
        "u4_output_inspected": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--package-root", type=Path)
    args = parser.parse_args(argv)
    try:
        report = validate(args.repository_root, args.package_root)
    except ValidationError as exc:
        print(f"VALIDATION_FAILED: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
