"""Validate Person B's additive Step 6 authorization refresh evidence.

This validator reads committed source objects and policy JSON only. It never
constructs an oracle, runs a model, fits a probe, predicts, computes metrics,
or inspects U4.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

STARTING_AUTHORITY = "a189c7f0c6a822f3dd0d9869a572e1e2d390c5f1"
PERSON_A_AUTHORITY = "0416ce88060277b28512f95dca0af94984a8211d"
PERSON_C_AUTHORITY = "bf09c23bb12f59acae724811eed6b82bab17c0ed"
PERSON_E_AUTHORITY = "b27d404c6aa913bac559754fa8b7accdff46e886"
PACKAGE_RELATIVE_PATH = Path(
    "docs/status/person_b_phase4_step4_1_step6_authorization_refresh_v0_1"
)
HISTORICAL_SELECTION_PATH = Path(
    "docs/status/person_b_phase4_step4_1_registry_v2_handoff_v0_1"
    "/accepted_c_oracle_inputs.json"
)
SCRIPT_RELATIVE_PATH = Path(
    "scripts/"
    "validate_person_b_phase4_step4_1_step6_authorization_refresh_v0_1.py"
)
TEST_RELATIVE_PATH = Path(
    "tests/analysis/"
    "test_person_b_phase4_step4_1_step6_authorization_refresh_v0_1.py"
)
DOCUMENT_NAMES = (
    "authority_binding.json",
    "authorization_decision.json",
    "authorization_dependency_matrix.json",
    "person_a_required_acknowledgement.json",
    "person_c_required_decision.json",
    "refreshed_c_candidate_selection.json",
    "sha256_inventory.json",
    "validation_receipt.json",
)
INVENTORIED_NAMES = tuple(
    name for name in DOCUMENT_NAMES if name != "sha256_inventory.json"
)
EXPECTED_TRAJECTORY_IDS = (
    "layout_00_ep9403",
    "layout_00_ep9410",
    "layout_00_ep9441",
    "layout_01_ep9405",
    "layout_01_ep9412",
    "layout_01_ep9442",
    "layout_02_ep9407",
    "layout_02_ep9432",
    "layout_03_ep9404",
    "layout_03_ep9409",
    "layout_03_ep9443",
    "layout_04_ep9406",
    "layout_04_ep9411",
    "layout_04_ep9444",
    "layout_05_ep9408",
)
EXCLUDED_TRAJECTORY_ID = "layout_05_ep9422"
EXPECTED_SCIENTIFIC_USE = "pending_cross_role_signoff"
POST_EXECUTION_OUTPUT_DEPENDENCIES = {
    "production_model_input_bytes",
    "production_extraction_bytes",
    "production_activation_bytes",
    "production_rollout_bytes",
    "registry_v2_output_acceptance_records",
}
SOURCE_EVIDENCE = (
    (
        PERSON_A_AUTHORITY,
        (
            "docs/status/"
            "person_a_phase4_step4_1_production_handoff_preflight_v0_1/"
            "authority_binding.json"
        ),
        "83b08e01c07783ac366b6f5c90111aadfc6bc4f973634633036e1d78a6aba68a",
        3318,
    ),
    (
        PERSON_A_AUTHORITY,
        (
            "docs/status/"
            "person_a_phase4_step4_1_production_handoff_preflight_v0_1/"
            "blocker_receipt.json"
        ),
        "def7c03e36a9c7ab0a57aeceadf224f8c9edc3c6ebb64f13169d05bf37018ea3",
        2152,
    ),
    (
        PERSON_A_AUTHORITY,
        (
            "docs/status/"
            "person_a_phase4_step4_1_production_handoff_preflight_v0_1/"
            "selected_c_inputs.json"
        ),
        "3a3046ddbff5569ea5d18d4441849d3368d7791124c02a8c10b03604ce57fc9e",
        11716,
    ),
    (
        PERSON_A_AUTHORITY,
        (
            "docs/status/"
            "person_a_phase4_step4_1_production_handoff_preflight_v0_1/"
            "validation_receipt.json"
        ),
        "764894b5c8bc6df0be55c8d461304823f2b842c678edb0146c54803d28484630",
        2221,
    ),
    (
        PERSON_E_AUTHORITY,
        (
            "docs/status/person_e_phase4_step4_1_slice3a_v0_1/"
            "owner_handoffs/person_a_requirements.json"
        ),
        "26e56ecb95b8aa678eff320540eb1dd982dc51d51b12b71ac3653f7114b39879",
        2002,
    ),
    (
        PERSON_E_AUTHORITY,
        (
            "docs/status/person_e_phase4_step4_1_slice3a_v0_1/"
            "owner_handoffs/person_c_requirements.json"
        ),
        "7f42a6b8590bfd8229f815652e838540a987bd5da945f810464e105a20a50c53",
        11307,
    ),
)


class AuthorizationRefreshValidationError(ValueError):
    """Raised when the authorization refresh fails closed."""


def _fail(code: str, message: str) -> None:
    raise AuthorizationRefreshValidationError(f"{code}: {message}")


def _require(condition: bool, code: str, message: str) -> None:
    if not condition:
        _fail(code, message)


def canonical_json_bytes(value: Any) -> bytes:
    """Return canonical package JSON bytes."""

    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _git(
    repo_root: Path,
    *arguments: str,
    text: bool = False,
) -> bytes | str:
    result = subprocess.run(
        ["git", *arguments],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=text,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip()
        _fail("git_source_error", stderr or f"git {' '.join(arguments)} failed")
    return result.stdout


def _git_bytes(repo_root: Path, commit: str, path: str) -> bytes:
    output = _git(repo_root, "show", f"{commit}:{path}")
    _require(isinstance(output, bytes), "git_source_error", "expected bytes")
    return output


def _git_text(repo_root: Path, *arguments: str) -> str:
    output = _git(repo_root, *arguments, text=True)
    _require(isinstance(output, str), "git_source_error", "expected text")
    return output.strip()


def _load_document(path: Path) -> Mapping[str, Any]:
    raw = path.read_bytes()
    _require(
        not raw.startswith(b"\xef\xbb\xbf"),
        "noncanonical_json",
        f"{path.name} has a BOM",
    )
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        _fail("invalid_json", f"{path.name}: {error}")
    _require(
        isinstance(value, Mapping),
        "invalid_json",
        f"{path.name} is not a JSON object",
    )
    _require(
        raw == canonical_json_bytes(value),
        "noncanonical_json",
        f"{path.name} is not canonical",
    )
    _require(
        value.get("schema_version") == "1.0",
        "schema_mismatch",
        f"{path.name} schema_version is not 1.0",
    )
    return value


def _load_package(package_root: Path) -> dict[str, Mapping[str, Any]]:
    actual_names = {path.name for path in package_root.glob("*.json")}
    _require(
        actual_names == set(DOCUMENT_NAMES),
        "package_inventory_mismatch",
        "the package does not contain exactly eight required JSON files",
    )
    return {
        name: _load_document(package_root / name) for name in DOCUMENT_NAMES
    }


def _validate_source_authorities(repo_root: Path) -> None:
    for commit in (
        STARTING_AUTHORITY,
        PERSON_A_AUTHORITY,
        PERSON_C_AUTHORITY,
        PERSON_E_AUTHORITY,
    ):
        _require(
            _git_text(repo_root, "cat-file", "-t", commit) == "commit",
            "authority_mismatch",
            f"{commit} is not a commit",
        )
    for commit, path, expected_sha256, expected_size in SOURCE_EVIDENCE:
        raw = _git_bytes(repo_root, commit, path)
        _require(
            len(raw) == expected_size and _sha256(raw) == expected_sha256,
            "authority_mismatch",
            f"source evidence changed: {commit}:{path}",
        )


def _validate_authority_binding(binding: Mapping[str, Any]) -> None:
    authorities = binding.get("authorities")
    _require(
        isinstance(authorities, Mapping),
        "authority_binding_mismatch",
        "authority map is missing",
    )
    person_a = authorities.get("person_a_preflight")
    person_b = authorities.get("person_b")
    person_c = authorities.get("person_c")
    person_e = authorities.get("person_e")
    _require(
        isinstance(person_a, Mapping)
        and person_a.get("commit") == PERSON_A_AUTHORITY
        and isinstance(person_b, Mapping)
        and person_b.get("starting_authority") == STARTING_AUTHORITY
        and isinstance(person_c, Mapping)
        and person_c.get("commit") == PERSON_C_AUTHORITY
        and person_c.get("source_read_policy") == "exact_git_object_bytes"
        and isinstance(person_e, Mapping)
        and person_e.get("commit") == PERSON_E_AUTHORITY,
        "authority_binding_mismatch",
        "one or more owner authorities are wrong",
    )
    expected_a_evidence = [
        {
            "byte_size": byte_size,
            "path": path,
            "sha256": sha256,
        }
        for _, path, sha256, byte_size in SOURCE_EVIDENCE[:4]
    ]
    expected_e_evidence = [
        {
            "path": path,
            "sha256": sha256,
        }
        for _, path, sha256, _ in SOURCE_EVIDENCE[4:]
    ]
    _require(
        person_a.get("evidence") == expected_a_evidence
        and person_e.get("evidence") == expected_e_evidence,
        "authority_binding_mismatch",
        "Person A or Person E evidence bindings are wrong",
    )
    b_evidence = person_b.get("evidence")
    _require(
        isinstance(b_evidence, Sequence)
        and {
            (item.get("path"), item.get("sha256"))
            for item in b_evidence
            if isinstance(item, Mapping)
        }
        == {
            (
                HISTORICAL_SELECTION_PATH.as_posix(),
                "67a4a61f77e2200b8570a5d13489c55796f5a2f00f95d525b22d7aefde2cb29c",
            ),
            (
                (
                    "docs/status/"
                    "person_b_phase4_step4_1_registry_v2_handoff_v0_1/"
                    "phase6_authorization_conditions.json"
                ),
                "fcea4c2fa2cf943ab40914aa397ccfb91e35307fc1a1f83257c83731ddb5ec24",
            ),
        },
        "authority_binding_mismatch",
        "Person B evidence bindings are wrong",
    )
    claims = binding.get("claims")
    _require(
        isinstance(claims, Mapping)
        and all(value is False for value in claims.values()),
        "authority_binding_mismatch",
        "the authority binding makes an execution or acceptance claim",
    )


def _expected_c_record(
    repo_root: Path,
    trajectory_id: str,
) -> dict[str, Any]:
    path = f"data/autonomous/{trajectory_id}/capture_package_v0_1.json"
    raw = _git_bytes(repo_root, PERSON_C_AUTHORITY, path)
    try:
        package = json.loads(raw)
    except json.JSONDecodeError as error:
        _fail("current_c_object_invalid", f"{trajectory_id}: {error}")
    return {
        "byte_size": len(raw),
        "frame_count": package["media"]["frame_count"],
        "git_blob_oid": _git_text(
            repo_root,
            "rev-parse",
            f"{PERSON_C_AUTHORITY}:{path}",
        ),
        "git_object_sha256": _sha256(raw),
        "layout_id": package["layout_id"],
        "package_local_status": package["episode_manifest"]["status"],
        "registry_v2_accepted": False,
        "scientific_use": package["scientific_use"],
        "source_authority_commit": PERSON_C_AUTHORITY,
        "source_path": path,
        "trajectory_id": trajectory_id,
    }


def _validate_c_selection(
    repo_root: Path,
    selection: Mapping[str, Any],
) -> None:
    _require(
        selection.get("refreshed_selection_source_commit") == PERSON_C_AUTHORITY,
        "current_c_authority_mismatch",
        "the refreshed selection does not bind current Person C",
    )
    _require(
        selection.get("selection_count") == 15,
        "selection_count_mismatch",
        "the refreshed selection must contain 15 candidates",
    )
    candidates = selection.get("ordered_candidates")
    _require(
        isinstance(candidates, Sequence) and not isinstance(candidates, str),
        "selection_count_mismatch",
        "ordered_candidates is not a list",
    )
    candidate_ids = tuple(
        item.get("trajectory_id") for item in candidates if isinstance(item, Mapping)
    )
    _require(
        candidate_ids == EXPECTED_TRAJECTORY_IDS,
        "selection_order_mismatch",
        "the deterministic Person C selection order changed",
    )

    historical = json.loads((repo_root / HISTORICAL_SELECTION_PATH).read_bytes())
    historical_inputs = historical["accepted_inputs"]
    _require(
        tuple(item["trajectory_id"] for item in historical_inputs)
        == EXPECTED_TRAJECTORY_IDS,
        "historical_selection_mismatch",
        "the historical selection no longer has the expected identities",
    )
    stale_hashes = {item["literal_sha256"] for item in historical_inputs}

    expected_candidates = [
        _expected_c_record(repo_root, trajectory_id)
        for trajectory_id in EXPECTED_TRAJECTORY_IDS
    ]
    _require(
        list(candidates) == expected_candidates,
        "current_c_identity_mismatch",
        "a current Person C path, hash, size, frame count, or status is wrong",
    )
    _require(
        all(
            item["scientific_use"] == EXPECTED_SCIENTIFIC_USE
            and item["package_local_status"] == "accepted"
            and item["registry_v2_accepted"] is False
            and item["git_object_sha256"] not in stale_hashes
            for item in expected_candidates
        ),
        "scientific_use_or_stale_hash_mismatch",
        "current C candidates are accepted or reuse stale identities",
    )
    source_set_digest = _sha256(
        "\n".join(
            f"{item['trajectory_id']}:{item['git_object_sha256']}"
            for item in expected_candidates
        ).encode("utf-8")
    )
    _require(
        selection.get("source_set_digest") == source_set_digest
        and selection.get("source_frame_count")
        == sum(item["frame_count"] for item in expected_candidates),
        "selection_aggregate_mismatch",
        "the refreshed selection aggregate identity is wrong",
    )

    excluded = selection.get("excluded_no_object_control")
    expected_excluded = _expected_c_record(repo_root, EXCLUDED_TRAJECTORY_ID)
    expected_excluded.pop("frame_count")
    expected_excluded.pop("layout_id")
    expected_excluded["classification"] = "excluded_no_object_control"
    _require(
        excluded == expected_excluded,
        "excluded_control_mismatch",
        "the no-object control identity or exclusion changed",
    )
    _require(
        selection.get("old_selection_hashes_superseded") is True
        and selection.get("c_scientific_use_currently_accepted") is False
        and selection.get("registry_v2_inputs_currently_accepted") is False
        and selection.get("accepted_scientific_input_count") == 0,
        "selection_acceptance_mismatch",
        "the refreshed candidate selection claims scientific acceptance",
    )


def _validate_decisions(documents: Mapping[str, Mapping[str, Any]]) -> None:
    decision = documents["authorization_decision.json"]
    _require(
        decision.get("automatic_phase6_transition_allowed") is False
        and decision.get("explicit_aggregate_authorization_required") is True
        and decision.get("no_silent_authorization") is True,
        "automatic_authorization_forbidden",
        "authorization must remain explicit and fail closed",
    )
    layers = decision.get("decision_layers")
    _require(isinstance(layers, Mapping), "decision_mismatch", "layers missing")
    runtime = layers.get("person_a_runtime_execution")
    _require(isinstance(runtime, Mapping), "decision_mismatch", "runtime missing")
    _require(
        runtime.get("authorized") is False
        and runtime.get("current_state") == "BLOCKED_MISSING_REQUIRED_SIGNERS"
        and runtime.get("required_pre_execution_signers")
        == ["person_a", "person_b", "person_c"]
        and runtime.get("missing_required_signers") == ["person_a", "person_c"],
        "runtime_authorization_mismatch",
        "runtime authorization or signer accounting is wrong",
    )
    signer_status = runtime.get("signer_status")
    _require(
        isinstance(signer_status, Mapping)
        and signer_status.get("person_b")
        == "CONDITIONAL_SCOPE_APPROVAL_RECORDED"
        and signer_status.get("person_a")
        == "MISSING_REQUIRED_ACKNOWLEDGEMENT"
        and signer_status.get("person_c")
        == "MISSING_REQUIRED_SCIENTIFIC_USE_DECISION",
        "missing_signer_decision",
        "required pre-execution decisions are not represented precisely",
    )
    _require(
        set(runtime.get("forbidden_pre_execution_dependencies", []))
        == POST_EXECUTION_OUTPUT_DEPENDENCIES,
        "runtime_circularity",
        "post-execution output dependencies are not explicitly forbidden",
    )
    c_layer = layers.get("person_c_scientific_use")
    registry = layers.get("registry_v2_artifact_acceptance")
    _require(
        isinstance(c_layer, Mapping)
        and c_layer.get("accepted") is False
        and c_layer.get("decision_owner") == "person_c",
        "scientific_use_authorization_mismatch",
        "Person C scientific-use authorization is wrong",
    )
    _require(
        isinstance(registry, Mapping)
        and registry.get("accepted") is False
        and {
            "exact_production_model_input_bytes_and_sha256",
            "exact_production_extraction_bytes_and_sha256",
            "exact_production_activation_bytes_and_sha256",
            "exact_production_rollout_bytes_and_sha256",
        }.issubset(set(registry.get("post_execution_requirements", []))),
        "registry_acceptance_mismatch",
        "Registry v2 acceptance does not require exact future bytes",
    )

    matrix = documents["authorization_dependency_matrix.json"]
    circularity = matrix.get("circularity_audit")
    _require(
        isinstance(circularity, Mapping)
        and circularity.get("result") == "PASS"
        and circularity.get(
            "post_execution_outputs_required_for_runtime_authorization"
        )
        is False,
        "runtime_circularity",
        "the dependency matrix retains circular runtime requirements",
    )
    decisions = matrix.get("decisions")
    _require(
        isinstance(decisions, Sequence) and len(decisions) == 3,
        "decision_mismatch",
        "the dependency matrix must separate exactly three decisions",
    )
    indexed = {
        item["decision_id"]: item
        for item in decisions
        if isinstance(item, Mapping) and "decision_id" in item
    }
    runtime_dependencies = indexed["person_a_runtime_execution"]
    _require(
        runtime_dependencies.get("post_execution_dependencies") == []
        and not POST_EXECUTION_OUTPUT_DEPENDENCIES.intersection(
            runtime_dependencies.get("pre_execution_dependencies", [])
        ),
        "runtime_circularity",
        "runtime authorization depends on post-execution output bytes",
    )
    registry_dependencies = indexed["registry_v2_artifact_acceptance"]
    _require(
        "exact_output_artifact_bytes"
        in registry_dependencies.get("post_execution_dependencies", []),
        "registry_acceptance_mismatch",
        "Registry v2 acceptance lacks exact future output bytes",
    )

    c_required = documents["person_c_required_decision.json"]
    _require(
        c_required.get("current_decision") is None
        and c_required.get("current_state") == "MISSING_REQUIRED_OWNER_DECISION"
        and c_required.get("decision_owner") == "person_c"
        and c_required.get("person_b_may_supply_this_decision") is False
        and c_required.get("c_scientific_use_currently_accepted") is False,
        "missing_signer_decision",
        "the missing Person C decision was fabricated or misrepresented",
    )
    a_required = documents["person_a_required_acknowledgement.json"]
    _require(
        a_required.get("current_acknowledgement") is None
        and a_required.get("current_state")
        == "MISSING_REQUIRED_OWNER_ACKNOWLEDGEMENT"
        and a_required.get("acknowledgement_owner") == "person_a"
        and a_required.get("person_b_may_supply_this_acknowledgement") is False
        and a_required.get("post_execution_bytes_required_for_acknowledgement")
        is False,
        "missing_signer_decision",
        "the missing Person A acknowledgement was fabricated or circular",
    )


def _validate_receipt(receipt: Mapping[str, Any]) -> None:
    false_fields = (
        "automatic_phase6_transition_allowed",
        "c_scientific_use_currently_accepted",
        "fitted_probe_executed",
        "model_work_performed",
        "oracle_construction_executed",
        "person_a_runtime_execution_authorized",
        "prediction_executed",
        "registry_v2_inputs_currently_accepted",
        "scientific_execution_performed",
        "scientific_metrics_executed",
        "u4_output_inspected",
    )
    _require(
        all(receipt.get(field) is False for field in false_fields)
        and receipt.get("accepted_placeholder_count") == 0
        and receipt.get("accepted_scientific_artifact_count") == 0
        and receipt.get("current_c_hashes_verified") is True
        and receipt.get("excluded_no_object_control_preserved") is True
        and receipt.get("refreshed_c_selection_count") == 15
        and receipt.get("refreshed_selection_source_commit")
        == PERSON_C_AUTHORITY
        and receipt.get("runtime_authorization_circularity_removed") is True
        and receipt.get("missing_required_signers") == ["person_a", "person_c"]
        and receipt.get("validation_status") == "PASS",
        "receipt_mismatch",
        "the validation receipt violates the focused evidence-only scope",
    )


def _validate_inventory(
    package_root: Path,
    inventory: Mapping[str, Any],
) -> None:
    entries = inventory.get("files")
    _require(
        inventory.get("inventory_excludes_self") is True
        and isinstance(entries, Sequence)
        and not isinstance(entries, str),
        "inventory_mismatch",
        "the inventory self-exclusion convention is wrong",
    )
    indexed = {
        item.get("path"): item.get("sha256")
        for item in entries
        if isinstance(item, Mapping)
    }
    _require(
        set(indexed) == set(INVENTORIED_NAMES),
        "inventory_mismatch",
        "the inventory has a missing, stale, or extra entry",
    )
    for name in INVENTORIED_NAMES:
        _require(
            indexed[name] == _sha256((package_root / name).read_bytes()),
            "inventory_mismatch",
            f"inventory hash mismatch for {name}",
        )


def validate_worktree_scope(repo_root: Path) -> None:
    """Require all changes to remain within the focused additive repair."""

    output = _git(
        repo_root,
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
        text=True,
    )
    _require(isinstance(output, str), "scope_mismatch", "status was not text")
    allowed_exact = {
        SCRIPT_RELATIVE_PATH.as_posix(),
        TEST_RELATIVE_PATH.as_posix(),
    }
    for line in output.splitlines():
        path = line[3:].replace("\\", "/")
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        allowed = path.startswith(PACKAGE_RELATIVE_PATH.as_posix() + "/") or (
            path in allowed_exact
        )
        _require(allowed, "scope_mismatch", f"unexpected changed path: {path}")


def validate_package(
    package_root: Path,
    repo_root: Path,
    *,
    verify_sources: bool = True,
    verify_inventory: bool = True,
    verify_worktree: bool = True,
) -> dict[str, Any]:
    """Validate the complete authorization refresh and return a summary."""

    package_root = package_root.resolve()
    repo_root = repo_root.resolve()
    _require(
        package_root.name == PACKAGE_RELATIVE_PATH.name,
        "package_inventory_mismatch",
        "the package root name is wrong",
    )
    if any(part.lower() == "u4" for part in package_root.parts):
        _fail("u4_path_rejected", "U4 paths are prohibited")
    if verify_sources:
        _validate_source_authorities(repo_root)
    if verify_worktree:
        _require(
            package_root == (repo_root / PACKAGE_RELATIVE_PATH).resolve(),
            "scope_mismatch",
            "the package is not at the authorized additive path",
        )
        validate_worktree_scope(repo_root)
    documents = _load_package(package_root)
    _validate_authority_binding(documents["authority_binding.json"])
    _validate_c_selection(
        repo_root,
        documents["refreshed_c_candidate_selection.json"],
    )
    _validate_decisions(documents)
    _validate_receipt(documents["validation_receipt.json"])
    if verify_inventory:
        _validate_inventory(
            package_root,
            documents["sha256_inventory.json"],
        )
    return {
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
    except AuthorizationRefreshValidationError as error:
        print("PERSON_B_STEP6_AUTHORIZATION_REFRESH=FAIL")
        print(str(error))
        return 1
    print("PERSON_B_STEP6_AUTHORIZATION_REFRESH=PASS")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
