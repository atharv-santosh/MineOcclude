"""Validate Person B's Phase 4 Step 4.1 Registry v2 preparation handoff.

This command validates contracts and authority bindings only. It never loads
activation vectors, fits probes, generates predictions, or computes metrics.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

SCHEMA_TOKEN = "person-b-phase4-step4-1-registry-v2-handoff-v0-1"
STARTING_AUTHORITY = "aa84ab3b05c533c3e8dbd1ab897dd04d9f26f1cd"
PACKAGE_RELATIVE_PATH = Path(
    "docs/status/person_b_phase4_step4_1_registry_v2_handoff_v0_1"
)
DOCUMENT_NAMES = (
    "accepted_c_oracle_inputs.json",
    "authority_binding.json",
    "blocked_jobs.json",
    "fitted_probe_input_contract.json",
    "metric_table_input_contract.json",
    "oracle_target_contract.json",
    "person_a_required_handoff.json",
    "phase6_authorization_conditions.json",
    "prediction_input_contract.json",
    "registry_v2_exact_artifact_authorization.json",
    "registry_v2_manifest_template.json",
    "registry_v2_owner_status.json",
    "registry_v2_validation_schema.json",
    "registry_v2_verification_receipt_template.json",
    "sealed_fold_split_identity.json",
    "sha256_inventory.json",
    "validation_receipt.json",
)
INVENTORIED_NAMES = tuple(
    name for name in DOCUMENT_NAMES if name != "sha256_inventory.json"
)
AUTHORIZED_CHANGE_PREFIXES = (
    PACKAGE_RELATIVE_PATH.as_posix() + "/",
    "scripts/validate_person_b_phase4_step4_1_registry_v2_handoff_v0_1.py",
    "tests/analysis/test_person_b_phase4_step4_1_registry_v2_handoff_v0_1.py",
)
EXPECTED_SOURCE_HASHES = {
    "configs/analysis/core.yaml": (
        "b2e12e7049e0494c756be442a4f300cbc7dc0a6e262deecf682f1354e887f0ab"
    ),
    "configs/analysis/person_b_phase6_c_sources.json": (
        "2143f589283f4759df058068b0fdd8dc5eae1b58e1315bc62aaa07b3a3d47af0"
    ),
    "data/person_b/phase6_c_intake/capture_intake_report.json": (
        "c99a9000b41bbd660f00ffc4db5813445a72fe6c44696d9d2c7214f41e439607"
    ),
    "data/person_b/phase6_c_intake/condition_selection_source.json": (
        "b5f0f22978bc62911f284da8b700bd8f166144586d0925bb03f8a730963a50aa"
    ),
    "data/person_b/phase6_c_intake/layout_fold_plan.json": (
        "a762cfe66984675e6af9177ff954540fe17cafc7747422fcad26ed1a2f7bbf8b"
    ),
    (
        "docs/status/person_b_phase3_step3_3_final_signoff_v0_1/"
        "analysis_readiness_decision.json"
    ): "537d3b8e7ee98991e11a3a1c5e391e8cc76235fed6e75c4d9674c62cb3231bfb",
    (
        "docs/status/person_b_phase3_step3_3_final_signoff_v0_1/"
        "phase3_closure_recommendation.json"
    ): "72b69c4d68b7f08e9adde32273ca3a60c3e584544a9598a215fb6917f248d83e",
    "src/mineocclude/contracts/activation.py": (
        "ce1564ee831b04ea4afbf3437f8f985c8f39ce3ebbb6eba8ee2dd515333b5dba"
    ),
    "src/mineocclude/contracts/analysis_inputs.py": (
        "562710ad0b8da78ee517ef254b415220fb46a3acf15374232433a2af9efc80fc"
    ),
    "src/mineocclude/contracts/rollout_registry.py": (
        "7dfb7579685a39bac7eed9e9d82f8326b59dd8d605a308321c78d9aacb6ec4f3"
    ),
    "src/mineocclude/oracle/schema.py": (
        "f028bc86e05944d3df66d90f05b5dddfb31ec5d07a00623d5032e69fe527bdac"
    ),
    "src/mineocclude/probes/splits.py": (
        "748d4135ccfe94c23f891ecb43ca7139cb075069fdf16f8126f8e2440a6f0510"
    ),
}
EXPECTED_LAYOUT_ASSIGNMENTS = [
    {"fold_idx": 1, "layout_id": "layout_00"},
    {"fold_idx": 2, "layout_id": "layout_01"},
    {"fold_idx": 4, "layout_id": "layout_02"},
    {"fold_idx": 0, "layout_id": "layout_03"},
    {"fold_idx": 3, "layout_id": "layout_04"},
    {"fold_idx": 4, "layout_id": "layout_05"},
]
BLOCKED_JOB_TYPES = {"fitted_probe", "prediction", "metric_table"}


class HandoffValidationError(ValueError):
    """Raised when the preparation package fails closed."""


def _fail(code: str, message: str) -> None:
    raise HandoffValidationError(f"{code}: {message}")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    try:
        return sha256_bytes(path.read_bytes())
    except OSError as error:
        _fail("missing_required_document", f"cannot read {path}: {error}")


def canonical_json_bytes(document: Any) -> bytes:
    try:
        return (
            json.dumps(
                document,
                allow_nan=False,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        _fail("noncanonical_json", str(error))


def load_canonical_json(path: Path) -> Mapping[str, Any]:
    try:
        payload = path.read_bytes()
        if payload.startswith(b"\xef\xbb\xbf"):
            _fail("noncanonical_json", f"{path.name} contains a UTF-8 BOM")
        document = json.loads(payload.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        _fail("noncanonical_json", f"{path.name}: {error}")
    if not isinstance(document, Mapping):
        _fail("noncanonical_json", f"{path.name} must contain a JSON object")
    if payload != canonical_json_bytes(document):
        _fail("noncanonical_json", f"{path.name} is not canonical formatted JSON")
    return document


def _require(condition: bool, code: str, message: str) -> None:
    if not condition:
        _fail(code, message)


def _git(repo_root: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", *arguments],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        _fail("wrong_starting_authority", result.stderr.strip() or "git failed")
    return result.stdout.strip()


def validate_worktree_scope(repo_root: Path) -> None:
    """Reject modifications outside the preparation package, script, and test."""

    status = _git(repo_root, "status", "--porcelain=v1", "--untracked-files=all")
    for line in status.splitlines():
        path = line[3:].replace("\\", "/")
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        if not any(
            path == prefix or path.startswith(prefix)
            for prefix in AUTHORIZED_CHANGE_PREFIXES
        ):
            _fail("pre_existing_path_modified", f"unauthorized changed path: {path}")


def _validate_source_authorities(repo_root: Path) -> None:
    object_type = _git(repo_root, "cat-file", "-t", STARTING_AUTHORITY)
    _require(
        object_type == "commit",
        "wrong_starting_authority",
        "starting authority is not a commit",
    )
    ancestry = subprocess.run(
        ["git", "merge-base", "--is-ancestor", STARTING_AUTHORITY, "HEAD"],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    _require(
        ancestry.returncode == 0,
        "wrong_starting_authority",
        "HEAD does not descend from the required preparation authority",
    )
    for relative_path, expected_hash in EXPECTED_SOURCE_HASHES.items():
        actual_hash = sha256_file(repo_root / relative_path)
        _require(
            actual_hash == expected_hash,
            "authority_hash_mismatch",
            f"{relative_path} expected {expected_hash}, received {actual_hash}",
        )


def _validate_document_set(
    package_root: Path,
) -> dict[str, Mapping[str, Any]]:
    actual_names = sorted(
        path.name for path in package_root.iterdir() if path.is_file()
    )
    _require(
        actual_names == sorted(DOCUMENT_NAMES),
        "missing_required_document",
        f"expected {sorted(DOCUMENT_NAMES)}, received {actual_names}",
    )
    documents = {
        name: load_canonical_json(package_root / name) for name in DOCUMENT_NAMES
    }
    for name, document in documents.items():
        _require(
            document.get("schema_version") == "1.0",
            "missing_required_document",
            f"{name} must declare schema_version 1.0",
        )
        schema_id = document.get("schema_id")
        _require(
            isinstance(schema_id, str) and SCHEMA_TOKEN in schema_id,
            "missing_required_document",
            f"{name} has the wrong schema_id",
        )
    return documents


def _validate_inventory(
    package_root: Path,
    documents: Mapping[str, Mapping[str, Any]],
) -> None:
    inventory = documents["sha256_inventory.json"]
    expected_records = [
        {
            "path": name,
            "sha256": sha256_file(package_root / name),
        }
        for name in INVENTORIED_NAMES
    ]
    _require(
        inventory.get("files") == expected_records,
        "sha256_inventory_mismatch",
        "inventory does not match exact package bytes",
    )
    _require(
        inventory.get("inventory_excludes_self") is True,
        "sha256_inventory_mismatch",
        "inventory must explicitly exclude itself",
    )


def _validate_fold_and_c_inputs(
    repo_root: Path,
    documents: Mapping[str, Mapping[str, Any]],
) -> None:
    fold = documents["sealed_fold_split_identity.json"]
    frozen = fold.get("frozen_assignment")
    final_manifest = fold.get("final_frame_manifest")
    _require(
        isinstance(frozen, Mapping)
        and frozen.get("layout_assignments") == EXPECTED_LAYOUT_ASSIGNMENTS
        and frozen.get("accepted_row_count") == 2456
        and frozen.get("trajectory_count") == 15
        and frozen.get("artifact_hash")
        == "ca265b64935880aede8c3bb8b6060cdda17c23932e5e98878a3fcf8ee5341f01",
        "fold_plan_mismatch",
        "sealed pre-A fold identity does not match the frozen plan",
    )
    _require(
        isinstance(final_manifest, Mapping)
        and final_manifest.get("construction_status")
        == "BLOCKED_PENDING_PERSON_A"
        and final_manifest.get("scientific_use_before_validation") == "forbidden",
        "final_fold_manifest_without_person_a",
        "final frame manifest is not fail-closed pending A",
    )
    plan = load_canonical_json(
        repo_root / "data/person_b/phase6_c_intake/layout_fold_plan.json"
    )
    _require(
        plan.get("layout_assignments") == EXPECTED_LAYOUT_ASSIGNMENTS
        and plan.get("accepted_row_count") == 2456,
        "fold_plan_mismatch",
        "repository layout plan changed",
    )

    c_inputs = documents["accepted_c_oracle_inputs.json"]
    report = load_canonical_json(
        repo_root / "data/person_b/phase6_c_intake/capture_intake_report.json"
    )
    accepted_report_rows = [
        row
        for row in report["package_records"]
        if row["classification"] != "no_object_not_oracle_eligible"
    ]
    expected_rows = [
        {
            field: row[field]
            for field in (
                "accepted_manifest_hash",
                "classification",
                "coordinate_frame_document_hash",
                "coordinate_frame_hash",
                "frame_count",
                "layout_id",
                "literal_sha256",
                "path",
                "trajectory_id",
            )
        }
        for row in accepted_report_rows
    ]
    _require(
        c_inputs.get("accepted_input_count") == 15
        and c_inputs.get("accepted_inputs") == expected_rows,
        "authority_hash_mismatch",
        "accepted C oracle inputs do not exactly match the intake report",
    )
    excluded = c_inputs.get("excluded_input")
    _require(
        isinstance(excluded, Mapping)
        and excluded.get("trajectory_id") == "layout_05_ep9422"
        and excluded.get("classification") == "no_object_not_oracle_eligible",
        "scientific_output_present",
        "the no-object control must remain excluded from oracle construction",
    )


def _validate_contracts(documents: Mapping[str, Mapping[str, Any]]) -> None:
    authority = documents["authority_binding.json"]
    _require(
        authority.get("branch") == "role/person-b-analysis"
        and authority.get("starting_authority") == STARTING_AUTHORITY
        and authority.get("starting_authority_tree")
        == "88dd132cf01f6392de6fc049c2a18ad12a873a66",
        "wrong_starting_authority",
        "authority binding does not match the required Person B start",
    )
    oracle = documents["oracle_target_contract.json"]
    _require(
        oracle.get("production_artifact_created") is False
        and oracle.get("scientific_output_present") is False
        and oracle.get("construction_status") == "READY_AS_CONTRACT_NOT_EXECUTED",
        "scientific_output_present",
        "oracle contract must not claim a production target artifact",
    )
    for name in (
        "fitted_probe_input_contract.json",
        "prediction_input_contract.json",
        "metric_table_input_contract.json",
    ):
        document = documents[name]
        _require(
            str(document.get("execution_status", "")).startswith("BLOCKED_")
            and document.get("scientific_output_present") is False,
            "scientific_job_unblocked",
            f"{name} is not blocked",
        )
    metric = documents["metric_table_input_contract.json"]
    _require(
        "baseline" in metric.get("direct_input_artifact_types", [])
        and metric.get("required_baseline_contract", {}).get("producer_role")
        == "person_d",
        "invalid_direct_input",
        "metric contract lacks the exact Person D baseline dependency",
    )


def _validate_registry_policy(documents: Mapping[str, Mapping[str, Any]]) -> None:
    owner = documents["registry_v2_owner_status.json"]
    owner_by_type = {
        row["artifact_type"]: row
        for row in owner.get("artifact_owner_status", [])
        if isinstance(row, Mapping) and "artifact_type" in row
    }
    _require(
        set(owner_by_type)
        == {
            "baseline",
            "fitted_probe",
            "fold_manifest",
            "metric_table",
            "oracle_target",
            "prediction",
        },
        "invalid_owner",
        "owner-status artifact set is incomplete",
    )
    _require(
        owner_by_type["baseline"].get("owner") == "person_d"
        and all(
            owner_by_type[artifact_type].get("owner") == "person_b"
            for artifact_type in (
                "fold_manifest",
                "oracle_target",
                "fitted_probe",
                "prediction",
                "metric_table",
            )
        ),
        "invalid_owner",
        "artifact ownership is incorrect",
    )

    authorization = documents["registry_v2_exact_artifact_authorization.json"]
    records = authorization.get("authorizations")
    _require(
        isinstance(records, Sequence)
        and all(
            isinstance(record, Mapping)
            and record.get("production_registration_allowed") is False
            for record in records
        ),
        "scientific_job_unblocked",
        "production registration was authorized",
    )
    forbidden = authorization.get("forbidden_source_substitutions")
    phase3_rules = [
        record
        for record in forbidden
        if isinstance(record, Mapping)
        and record.get("forbidden_source")
        == "docs/status/person_b_phase3_step3_3_final_signoff_v0_1"
    ]
    _require(
        len(phase3_rules) == 1
        and set(phase3_rules[0].get("must_not_be_registered_as", []))
        == {"oracle_target", "fitted_probe", "prediction", "metric_table"},
        "phase3_readiness_substitution",
        "Phase 3 readiness substitution is not fully prohibited",
    )

    manifest = documents["registry_v2_manifest_template.json"]
    _require(
        manifest.get("template_is_scientific_artifact") is False
        and manifest.get("template_nulls_require_exact_replacement_before_validation")
        is True,
        "scientific_output_present",
        "manifest template is being treated as an artifact",
    )
    verification = documents["registry_v2_verification_receipt_template.json"]
    _require(
        verification.get("verification_status") == "NOT_RUN"
        and verification.get("decision") == "PENDING_EXACT_ARTIFACTS"
        and verification.get("scientific_outputs_validated") is False,
        "scientific_output_present",
        "verification template claims an execution result",
    )


def _validate_blockers_and_phase(documents: Mapping[str, Mapping[str, Any]]) -> None:
    blocked = documents["blocked_jobs.json"]
    jobs = blocked.get("jobs")
    _require(
        isinstance(jobs, list)
        and {job.get("job_type") for job in jobs if isinstance(job, Mapping)}
        == BLOCKED_JOB_TYPES,
        "scientific_job_unblocked",
        "blocked job inventory is incomplete",
    )
    for job in jobs:
        _require(
            job.get("status") == "BLOCKED"
            and job.get("output_artifact_id") is None
            and job.get("output_sha256") is None,
            "scientific_job_unblocked",
            f"{job.get('job_id')} is not fail-closed",
        )
    _require(
        blocked.get("probe_fitting_executed") is False
        and blocked.get("production_predictions_executed") is False
        and blocked.get("production_metrics_executed") is False,
        "scientific_output_present",
        "blocked job record claims execution",
    )

    person_a = documents["person_a_required_handoff.json"]
    pending = person_a.get("accepted_production_values")
    _require(
        isinstance(pending, Mapping)
        and pending
        and all(value is None for value in pending.values())
        and person_a.get("accepted_production_values_status")
        == "PENDING_EXACT_PERSON_A_HANDOFF",
        "invented_pending_person_a_value",
        "a pending Person A production value was populated",
    )
    activation = person_a.get("activation_contract")
    _require(
        isinstance(activation, Mapping)
        and activation.get("vector_shape") == [2048]
        and activation.get("visual_tokens_per_frame") == 336
        and activation.get("maximum_model_frames") == 16
        and activation.get("pooling_method") == "mean",
        "invalid_direct_input",
        "Person A activation dimensions or semantics changed",
    )

    phase6 = documents["phase6_authorization_conditions.json"]
    _require(
        phase6.get("person_a_phase6_authorized") is False
        and phase6.get("this_handoff_changes_authorization") is False
        and phase6.get("silent_authorization_forbidden") is True,
        "person_a_phase6_silently_authorized",
        "this package may not authorize Person A Phase 6",
    )
    state = phase6.get("current_documented_state")
    _require(
        isinstance(state, Mapping)
        and state.get("independent_final_verification") == "PENDING"
        and state.get("phase3_formally_closed") is False
        and state.get("overall_phase3_status") == "IN_PROGRESS",
        "person_a_phase6_silently_authorized",
        "Phase 3 status was silently promoted",
    )

    receipt = documents["validation_receipt.json"]
    _require(
        receipt.get("preparation_decision") == "READY"
        and receipt.get("person_a_phase6_authorized") is False
        and receipt.get("scientific_outputs_created") is False
        and receipt.get("probe_fitting_executed") is False
        and receipt.get("production_predictions_executed") is False
        and receipt.get("production_metrics_executed") is False
        and receipt.get("u4_output_inspected") is False
        and receipt.get("validation_status") == "PASS",
        "scientific_output_present",
        "validation receipt is inconsistent with preparation-only scope",
    )


def validate_package(
    package_root: Path,
    repo_root: Path,
    *,
    verify_inventory: bool = True,
    verify_sources: bool = True,
    verify_worktree: bool = True,
) -> dict[str, Any]:
    """Validate the complete preparation package and return a receipt summary."""

    package_root = package_root.resolve()
    repo_root = repo_root.resolve()
    if any("u4" == part.lower() for part in package_root.parts):
        _fail("u4_path_rejected", "U4 paths are outside this preparation task")
    if verify_sources:
        _validate_source_authorities(repo_root)
    if verify_worktree:
        validate_worktree_scope(repo_root)
    documents = _validate_document_set(package_root)
    _validate_fold_and_c_inputs(repo_root, documents)
    _validate_contracts(documents)
    _validate_registry_policy(documents)
    _validate_blockers_and_phase(documents)
    if verify_inventory:
        _validate_inventory(package_root, documents)
    return {
        "blocked_job_count": len(documents["blocked_jobs.json"]["jobs"]),
        "person_a_phase6_authorized": False,
        "preparation_decision": "READY",
        "production_metrics_executed": False,
        "production_predictions_executed": False,
        "probe_fitting_executed": False,
        "scientific_outputs_created": False,
        "status": "PASS",
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    parser.add_argument("--package-root", type=Path)
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    repo_root = args.repo_root.resolve()
    package_root = (
        args.package_root.resolve()
        if args.package_root is not None
        else repo_root / PACKAGE_RELATIVE_PATH
    )
    try:
        result = validate_package(package_root, repo_root)
    except HandoffValidationError as error:
        print("PERSON_B_PHASE4_STEP4_1_REGISTRY_V2_HANDOFF=FAIL")
        print(str(error))
        return 1
    print("PERSON_B_PHASE4_STEP4_1_REGISTRY_V2_HANDOFF=PASS")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
