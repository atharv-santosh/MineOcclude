"""Validate Person B's final bounded Step 6 runtime authorization.

The validator reads exact committed policy and trust records. It does not run
models, construct scientific artifacts, execute Person A's workflow, inspect
U4, or accept any future Person A output.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

PERSON_B_REFRESH = "8942d5d514a4d124ac0baa36ffc803dc598c4f1f"
PERSON_A_ACKNOWLEDGEMENT = "ca3f5695dc37f9f2c8066e323b25485c042b6cf7"
PERSON_C_SIGNOFF = "f0d4e895b56fc4ca3f4805aa13b73545744af1b0"
PERSON_E_REGISTRY_V2 = "b27d404c6aa913bac559754fa8b7accdff46e886"

PERSON_A_REMOTE_REF = "origin/role/person-a-model"
PERSON_C_REMOTE_REF = "origin/role/person-c-data"
SELECTED_TRAJECTORY_ID = "layout_00_ep9403"
SELECTED_PILOT_SHA256 = (
    "21ea1dba91cf92ad82080088f70905fba053557392437b19591cad1333667213"
)
SELECTED_PILOT_SIZE = 662116
EXCLUDED_TRAJECTORY_ID = "layout_05_ep9422"
AUTHORIZED_STEPS = ("6.1", "6.2", "6.3", "6.4", "6.5", "6.6")

PACKAGE_RELATIVE_PATH = Path(
    "docs/status/"
    "person_b_phase4_step4_1_step6_final_runtime_authorization_v0_1"
)
B_REFRESH_PACKAGE = (
    "docs/status/"
    "person_b_phase4_step4_1_step6_authorization_refresh_v0_1"
)
A_PACKAGE = "docs/status/person_a_step6_runtime_acknowledgement_v0_1"
C_PACKAGE = (
    "docs/status/person_c_phase4_step4_1_registry_v2_handoff_v0_1"
)
E_VALIDATOR_PATH = "src/mineocclude/contracts/rollout_registry.py"

DOCUMENT_NAMES = (
    "authority_binding.json",
    "authorization_boundaries.json",
    "combined_runtime_authorization.json",
    "selected_pilot_validation.json",
    "sha256_inventory.json",
    "validation_receipt.json",
)
INVENTORIED_NAMES = tuple(
    name for name in DOCUMENT_NAMES if name != "sha256_inventory.json"
)
A_DOCUMENT_NAMES = (
    "authority_binding.json",
    "execution_gate.json",
    "frozen_runtime_configuration.json",
    "runtime_acknowledgement.json",
    "sha256_inventory.json",
    "validation_receipt.json",
)
C_DOCUMENT_NAMES = (
    "accepted_pilot_manifest.json",
    "authority_binding.json",
    "direct_input_lineage.json",
    "registry_v2_artifact_verification_receipt.json",
    "registry_v2_document.json",
    "registry_v2_exact_artifact_authorization.json",
    "registry_v2_owner_status.json",
    "registry_v2_trusted_manifest.json",
    "registry_v2_trusted_verification_inputs.json",
    "registry_v2_verified_authorization_record.json",
    "selected_pilot_acceptance.json",
    "sha256_inventory.json",
    "validation_receipt.json",
)


class FinalRuntimeAuthorizationError(ValueError):
    """Raised when any authorization condition fails closed."""


def _fail(code: str, message: str) -> None:
    raise FinalRuntimeAuthorizationError(f"{code}: {message}")


def _require(condition: bool, code: str, message: str) -> None:
    if not condition:
        _fail(code, message)


def canonical_json_bytes(value: Any) -> bytes:
    """Return the canonical JSON representation required by this package."""

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


def _parse_json(raw: bytes, label: str, *, canonical: bool = True) -> Mapping[str, Any]:
    _require(
        not raw.startswith(b"\xef\xbb\xbf"),
        "noncanonical_json",
        f"{label} has a BOM",
    )
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        _fail("invalid_json", f"{label}: {error}")
    _require(
        isinstance(value, Mapping),
        "invalid_json",
        f"{label} is not a JSON object",
    )
    if canonical:
        _require(
            raw == canonical_json_bytes(value),
            "noncanonical_json",
            f"{label} is not canonical",
        )
    return value


def _load_document(path: Path) -> Mapping[str, Any]:
    value = _parse_json(path.read_bytes(), path.name)
    _require(
        value.get("schema_version") == "1.0",
        "schema_mismatch",
        f"{path.name} schema_version is not 1.0",
    )
    schema_id = value.get("schema_id")
    _require(
        isinstance(schema_id, str)
        and "person-b-phase4-step4-1-step6-final-runtime-authorization-v0-1"
        in schema_id,
        "schema_mismatch",
        f"{path.name} schema_id is outside this package",
    )
    return value


def _load_package(package_root: Path) -> dict[str, Mapping[str, Any]]:
    actual_names = {path.name for path in package_root.glob("*.json")}
    _require(
        actual_names == set(DOCUMENT_NAMES),
        "package_inventory_mismatch",
        "the package does not contain exactly six required JSON files",
    )
    return {
        name: _load_document(package_root / name) for name in DOCUMENT_NAMES
    }


def _load_commit_package(
    repo_root: Path,
    commit: str,
    package: str,
    names: Sequence[str],
) -> dict[str, Mapping[str, Any]]:
    documents: dict[str, Mapping[str, Any]] = {}
    for name in names:
        raw = _git_bytes(repo_root, commit, f"{package}/{name}")
        documents[name] = _parse_json(raw, f"{commit}:{package}/{name}")
    return documents


def _validate_inventory(
    documents: Mapping[str, Mapping[str, Any]],
    raw_by_name: Mapping[str, bytes],
    expected_names: Sequence[str],
) -> None:
    inventory = documents["sha256_inventory.json"]
    _require(
        inventory.get("inventory_excludes_self") is True,
        "inventory_mismatch",
        "inventory must exclude itself",
    )
    expected = {name for name in expected_names if name != "sha256_inventory.json"}
    hashes = inventory.get("files")
    _require(
        isinstance(hashes, Mapping) and set(hashes) == expected,
        "inventory_mismatch",
        "inventory file set is incorrect",
    )
    for name in expected:
        _require(
            hashes[name] == _sha256(raw_by_name[name]),
            "inventory_mismatch",
            f"inventory hash mismatch for {name}",
        )


def _validate_commit_inventory(
    repo_root: Path,
    commit: str,
    package: str,
    names: Sequence[str],
    documents: Mapping[str, Mapping[str, Any]],
) -> None:
    raw_by_name = {
        name: _git_bytes(repo_root, commit, f"{package}/{name}")
        for name in names
    }
    _validate_inventory(documents, raw_by_name, names)


def _validate_remote_authorities(repo_root: Path) -> None:
    for commit in (
        PERSON_B_REFRESH,
        PERSON_A_ACKNOWLEDGEMENT,
        PERSON_C_SIGNOFF,
        PERSON_E_REGISTRY_V2,
    ):
        _require(
            _git_text(repo_root, "cat-file", "-t", commit) == "commit",
            "missing_authority",
            f"{commit} is not a commit",
        )
    _require(
        _git_text(repo_root, "rev-parse", PERSON_A_REMOTE_REF)
        == PERSON_A_ACKNOWLEDGEMENT,
        "wrong_remote_authority",
        "Person A remote ref is not the exact acknowledgement commit",
    )
    _require(
        _git_text(repo_root, "rev-parse", PERSON_C_REMOTE_REF) == PERSON_C_SIGNOFF,
        "wrong_remote_authority",
        "Person C remote ref is not the exact accepted-pilot signoff",
    )


def _validate_bound_source_records(
    repo_root: Path,
    authority_binding: Mapping[str, Any],
) -> None:
    records = authority_binding.get("source_records")
    _require(
        isinstance(records, Sequence) and not isinstance(records, (str, bytes)),
        "source_binding_mismatch",
        "source_records must be a non-empty list",
    )
    for record in records:
        _require(
            isinstance(record, Mapping),
            "source_binding_mismatch",
            "source record is not an object",
        )
        commit = record.get("source_commit")
        path = record.get("path")
        _require(
            isinstance(commit, str) and isinstance(path, str),
            "source_binding_mismatch",
            "source commit/path is missing",
        )
        raw = _git_bytes(repo_root, commit, path)
        _require(
            record.get("sha256") == _sha256(raw),
            "source_hash_mismatch",
            f"source hash mismatch for {path}",
        )
        _require(
            record.get("byte_size") == len(raw),
            "source_size_mismatch",
            f"source size mismatch for {path}",
        )


def _validate_b_refresh(repo_root: Path) -> Mapping[str, Any]:
    selection_path = f"{B_REFRESH_PACKAGE}/refreshed_c_candidate_selection.json"
    selection = _parse_json(
        _git_bytes(repo_root, PERSON_B_REFRESH, selection_path),
        selection_path,
    )
    candidates = selection.get("ordered_candidates")
    _require(
        isinstance(candidates, Sequence)
        and not isinstance(candidates, (str, bytes))
        and len(candidates) == 15,
        "candidate_selection_mismatch",
        "B refresh must contain exactly 15 ordered candidates",
    )
    candidate_ids = [candidate.get("trajectory_id") for candidate in candidates]
    _require(
        candidate_ids[0] == SELECTED_TRAJECTORY_ID,
        "candidate_selection_mismatch",
        "selected pilot is not first in B's deterministic order",
    )
    _require(
        EXCLUDED_TRAJECTORY_ID not in candidate_ids,
        "excluded_control_selected",
        "excluded no-object control appears in candidate selection",
    )
    excluded = selection.get("excluded_no_object_control")
    _require(
        isinstance(excluded, Mapping)
        and excluded.get("trajectory_id") == EXCLUDED_TRAJECTORY_ID,
        "excluded_control_mismatch",
        "B refresh does not preserve the excluded control",
    )
    selected = candidates[0]
    _require(
        selected.get("git_object_sha256") == SELECTED_PILOT_SHA256
        and selected.get("byte_size") == SELECTED_PILOT_SIZE,
        "selected_pilot_identity_mismatch",
        "B refresh selected pilot identity is incorrect",
    )
    _require(
        selected.get("scientific_use") == "pending_cross_role_signoff",
        "historical_scientific_state_mismatch",
        "B refresh must preserve the pre-signoff C scientific-use state",
    )
    return selection


def _validate_a_acknowledgement(
    repo_root: Path,
) -> dict[str, Mapping[str, Any]]:
    documents = _load_commit_package(
        repo_root,
        PERSON_A_ACKNOWLEDGEMENT,
        A_PACKAGE,
        A_DOCUMENT_NAMES,
    )
    _validate_commit_inventory(
        repo_root,
        PERSON_A_ACKNOWLEDGEMENT,
        A_PACKAGE,
        A_DOCUMENT_NAMES,
        documents,
    )
    authority = documents["authority_binding.json"]
    refresh = authority.get("authorities", {}).get("person_b_refresh", {})
    _require(
        refresh.get("refresh_authority") == PERSON_B_REFRESH
        and refresh.get("refresh_authority_verified") is True,
        "a_acknowledgement_binding_mismatch",
        "Person A acknowledgement does not bind the B refresh",
    )
    acknowledgement = documents["runtime_acknowledgement.json"]
    _require(
        acknowledgement.get("owner") == "person_a"
        and acknowledgement.get("person_a_signer_acknowledgement_complete") is True
        and acknowledgement.get("accepts_responsibility_for_bounded_steps") is True,
        "a_acknowledgement_incomplete",
        "Person A owner acknowledgement is incomplete",
    )
    _require(
        tuple(acknowledgement.get("bounded_steps", ())) == AUTHORIZED_STEPS,
        "a_scope_mismatch",
        "Person A acknowledgement has the wrong bounded steps",
    )
    _require(
        acknowledgement.get("candidate_only_output_classification") is True,
        "a_scope_mismatch",
        "Person A did not acknowledge candidate-only output classification",
    )
    for key in (
        "automatic_phase6_transition_allowed",
        "production_execution_started",
        "registry_v2_acceptance_authorized",
        "scientific_execution_claimed",
        "self_authorizes_phase6",
        "u4_output_inspected",
    ):
        _require(
            acknowledgement.get(key) is False,
            "a_claim_mismatch",
            f"Person A acknowledgement requires {key}=false",
        )
    claims = authority.get("claims", {})
    for key in (
        "model_input_bytes_created",
        "production_activation_bytes_created",
        "production_execution_started",
        "production_extraction_bytes_created",
        "production_rollout_bytes_created",
        "registry_v2_acceptance_authorized",
        "scientific_execution_performed",
        "u4_output_inspected",
    ):
        _require(
            claims.get(key) is False,
            "a_claim_mismatch",
            f"Person A authority requires {key}=false",
        )
    return documents


def _load_frozen_e_validator(repo_root: Path) -> Any:
    source = _git_bytes(repo_root, PERSON_E_REGISTRY_V2, E_VALIDATOR_PATH)
    _require(
        _sha256(source)
        == "386a6bce4f5ba727aa51b40c69ef444c0d984984697da63f6ea4045a44c07356",
        "registry_validator_hash_mismatch",
        "frozen Person E validator hash is incorrect",
    )
    src_root = str(repo_root / "src")
    if src_root not in sys.path:
        sys.path.insert(0, src_root)
    module_name = "_mineocclude_frozen_rollout_registry_b27d404"
    with tempfile.NamedTemporaryFile(
        suffix="_rollout_registry.py",
        delete=False,
    ) as handle:
        handle.write(source)
        temporary_path = Path(handle.name)
    try:
        spec = importlib.util.spec_from_file_location(module_name, temporary_path)
        _require(
            spec is not None and spec.loader is not None,
            "registry_validator_load_failed",
            "could not create the frozen validator module",
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        temporary_path.unlink(missing_ok=True)


def _validate_c_registry_trust_chain(
    repo_root: Path,
    documents: Mapping[str, Mapping[str, Any]],
    pilot_bytes: bytes,
) -> None:
    module = _load_frozen_e_validator(repo_root)
    registry = documents["registry_v2_document.json"].get(
        "immutable_registry_document"
    )
    verification = documents["registry_v2_trusted_verification_inputs.json"]
    trusted = verification.get("trusted_inputs")
    _require(
        isinstance(registry, Mapping) and isinstance(trusted, Mapping),
        "registry_trust_mismatch",
        "C Registry v2 document or trusted inputs are malformed",
    )
    status_bytes = {
        key: value.encode("utf-8")
        for key, value in trusted["trusted_status_record_bytes"].items()
    }
    authorization_bytes = {
        key: value.encode("utf-8")
        for key, value in trusted[
            "trusted_authorization_record_bytes"
        ].items()
    }
    result = module.validate_immutable_run_artifact_registry(
        registry,
        artifact_bytes_by_id={SELECTED_TRAJECTORY_ID: pilot_bytes},
        trusted_owner_authorities=trusted["trusted_owner_authorities"],
        trusted_status_record_bytes=status_bytes,
        trusted_artifact_authorizations=trusted[
            "trusted_artifact_authorizations"
        ],
        trusted_authorization_record_bytes=authorization_bytes,
        trusted_manifest_records=trusted["trusted_manifest_records"],
        trusted_artifact_receipts=None,
    )
    rejection_codes = [item.code.value for item in result.rejections]
    _require(
        result.accepted,
        "registry_trust_rejected",
        f"frozen E validator rejected C trust chain: {rejection_codes}",
    )


def _validate_c_signoff(
    repo_root: Path,
) -> dict[str, Mapping[str, Any]]:
    documents = _load_commit_package(
        repo_root,
        PERSON_C_SIGNOFF,
        C_PACKAGE,
        C_DOCUMENT_NAMES,
    )
    _validate_commit_inventory(
        repo_root,
        PERSON_C_SIGNOFF,
        C_PACKAGE,
        C_DOCUMENT_NAMES,
        documents,
    )
    authority = documents["authority_binding.json"]
    b_binding = authority.get("person_b_selection_authority", {})
    _require(
        b_binding.get("commit") == PERSON_B_REFRESH,
        "c_signoff_binding_mismatch",
        "Person C signoff does not bind the B refresh",
    )
    selected = authority.get("selected_pilot", {})
    _require(
        selected.get("trajectory_id") == SELECTED_TRAJECTORY_ID
        and selected.get("git_object_sha256") == SELECTED_PILOT_SHA256
        and selected.get("byte_size") == SELECTED_PILOT_SIZE,
        "selected_pilot_identity_mismatch",
        "Person C authority binds the wrong pilot",
    )
    acceptance = documents["selected_pilot_acceptance.json"]
    _require(
        acceptance.get("decision") == "ACCEPT_SINGLE_PILOT_FOR_SCIENTIFIC_USE"
        and acceptance.get("trajectory_id") == SELECTED_TRAJECTORY_ID
        and acceptance.get("git_object_sha256") == SELECTED_PILOT_SHA256
        and acceptance.get("owner") == "person_c"
        and acceptance.get("signers") == {"person_c": True},
        "c_signoff_incomplete",
        "Person C owner decision is incomplete or has the wrong identity",
    )
    _require(
        acceptance.get("scope") == "single_pilot_steps_6_1_through_6_6"
        and acceptance.get("scientific_use")
        == "accepted_for_single_pilot_step_6_1",
        "c_scientific_scope_mismatch",
        "Person C scientific-use scope is incorrect",
    )
    manifest = documents["accepted_pilot_manifest.json"]
    receipt = documents["validation_receipt.json"]
    _require(
        manifest.get("accepted_pilot_count") == 1
        and receipt.get("accepted_pilot_count") == 1
        and receipt.get("second_pilot_accepted") is False
        and receipt.get("accepted_placeholder_count") == 0,
        "c_pilot_count_mismatch",
        "Person C did not accept exactly one real pilot",
    )
    _require(
        receipt.get("excluded_no_object_control") == EXCLUDED_TRAJECTORY_ID
        and receipt.get("excluded_control_not_selected") is True,
        "excluded_control_mismatch",
        "Person C did not preserve the excluded no-object control",
    )
    _require(
        receipt.get("registry_v2_trust_chain_complete") is True
        and receipt.get("c_scientific_use_accepted") is True
        and receipt.get("u4_output_inspected") is False,
        "c_validation_receipt_mismatch",
        "Person C validation receipt is incomplete",
    )
    pilot_path = selected.get("source_path")
    _require(
        isinstance(pilot_path, str),
        "selected_pilot_identity_mismatch",
        "selected pilot source path is missing",
    )
    pilot_bytes = _git_bytes(repo_root, PERSON_C_SIGNOFF, pilot_path)
    _require(
        _sha256(pilot_bytes) == SELECTED_PILOT_SHA256
        and len(pilot_bytes) == SELECTED_PILOT_SIZE,
        "selected_pilot_hash_mismatch",
        "selected capture-package bytes do not match",
    )
    _parse_json(pilot_bytes, pilot_path, canonical=False)
    _validate_c_registry_trust_chain(repo_root, documents, pilot_bytes)
    return documents


def _require_false(
    document: Mapping[str, Any],
    key: str,
    label: str,
) -> None:
    _require(
        document.get(key) is False,
        "authorization_boundary_mismatch",
        f"{label}.{key} must be false",
    )


def validate_decision_documents(
    documents: Mapping[str, Mapping[str, Any]],
) -> None:
    """Validate the additive B decision without reading external evidence."""

    authority = documents["authority_binding.json"]
    bindings = authority.get("bound_authorities", {})
    _require(
        bindings.get("person_b_refresh", {}).get("commit") == PERSON_B_REFRESH,
        "authority_binding_mismatch",
        "B refresh binding is incorrect",
    )
    _require(
        bindings.get("person_a_acknowledgement", {}).get("commit")
        == PERSON_A_ACKNOWLEDGEMENT,
        "authority_binding_mismatch",
        "A acknowledgement binding is incorrect",
    )
    _require(
        bindings.get("person_c_accepted_pilot", {}).get("commit")
        == PERSON_C_SIGNOFF,
        "authority_binding_mismatch",
        "C signoff binding is incorrect",
    )

    selected = documents["selected_pilot_validation.json"]
    selected_package = selected.get("selected_capture_package", {})
    _require(
        selected.get("accepted_pilot_count") == 1
        and selected_package.get("trajectory_id") == SELECTED_TRAJECTORY_ID
        and selected_package.get("git_object_sha256") == SELECTED_PILOT_SHA256,
        "selected_pilot_identity_mismatch",
        "final decision does not bind exactly the selected pilot",
    )
    _require(
        selected.get("complete_registry_v2_trust_chain_validated") is True,
        "registry_trust_mismatch",
        "C input trust chain is not marked validated",
    )
    excluded = selected.get("excluded_no_object_control", {})
    _require(
        excluded.get("trajectory_id") == EXCLUDED_TRAJECTORY_ID
        and excluded.get("excluded") is True,
        "excluded_control_mismatch",
        "final decision does not preserve the excluded control",
    )
    _require_false(
        selected,
        "future_person_a_output_acceptance_authorized",
        "selected_pilot_validation",
    )
    _require_false(
        selected,
        "production_execution_started",
        "selected_pilot_validation",
    )
    _require_false(selected, "u4_output_inspected", "selected_pilot_validation")

    decision = documents["combined_runtime_authorization.json"]
    scope = decision.get("authorization_scope", {})
    runtime = decision.get("person_a_runtime_execution", {})
    scientific_use = decision.get("person_c_scientific_use", {})
    _require(
        decision.get("decision_status") == "AUTHORIZED"
        and runtime.get("authorized") is True,
        "runtime_authorization_mismatch",
        "bounded Person A runtime is not explicitly authorized",
    )
    _require(
        tuple(scope.get("authorized_steps", ())) == AUTHORIZED_STEPS
        and scope.get("authorized_pilot_count") == 1
        and scope.get("selected_trajectory_id") == SELECTED_TRAJECTORY_ID
        and scope.get("selected_capture_package_sha256")
        == SELECTED_PILOT_SHA256,
        "runtime_scope_mismatch",
        "runtime scope is not exactly Steps 6.1-6.6 for one pilot",
    )
    _require(
        scientific_use.get("accepted") is True
        and scientific_use.get("scope") == "single_pilot_steps_6_1_through_6_6",
        "scientific_use_mismatch",
        "bounded C scientific use is not explicitly accepted",
    )
    _require_false(
        decision,
        "future_person_a_registry_v2_output_acceptance_authorized",
        "combined_runtime_authorization",
    )
    _require_false(
        decision,
        "production_execution_started",
        "combined_runtime_authorization",
    )
    _require_false(decision, "u4_output_inspected", "combined_runtime_authorization")

    boundaries = documents["authorization_boundaries.json"]
    future = boundaries.get("future_person_a_output_acceptance", {})
    positive_control = boundaries.get("positive_control_boundary", {})
    _require(
        future.get("accepted") is False
        and future.get("state")
        == "BLOCKED_UNTIL_EXACT_BYTES_AND_TRUST_RECORDS_EXIST",
        "future_output_acceptance_mismatch",
        "future Person A output acceptance must remain blocked",
    )
    required_future = set(future.get("required_post_execution_evidence", ()))
    _require(
        {
            "exact_model_input_bytes_and_sha256",
            "exact_extraction_bytes_and_sha256",
            "exact_activation_bytes_and_sha256",
            "exact_rollout_bytes_and_sha256",
            "independent_registry_v2_verification",
        }.issubset(required_future),
        "future_output_acceptance_mismatch",
        "post-execution Registry v2 requirements are incomplete",
    )
    for key in (
        "additional_pilots_authorized",
        "hidden_state_interpretation_authorized",
        "positive_control_passed",
        "project_integration_authorized",
        "step_4_1_closure_authorized",
    ):
        _require_false(positive_control, key, "positive_control_boundary")
    for key in (
        "automatic_phase6_transition_allowed",
        "production_execution_started_at_decision",
        "u4_output_inspected",
    ):
        _require_false(boundaries, key, "authorization_boundaries")
    _require(
        boundaries.get("no_automatic_transition") is True
        and boundaries.get("no_silent_authorization") is True
        and boundaries.get(
            "registry_v2_selected_c_input_trust_chain_accepted"
        )
        is True,
        "authorization_boundary_mismatch",
        "authorization boundary safeguards are incomplete",
    )

    receipt = documents["validation_receipt.json"]
    for key in (
        "a_acknowledgement_verified",
        "c_scientific_use_accepted",
        "c_signoff_verified",
        "complete_c_registry_v2_trust_chain_validated",
        "layout_05_ep9422_excluded",
        "person_a_runtime_execution_authorized",
        "selected_pilot_hash_verified",
    ):
        _require(
            receipt.get(key) is True,
            "validation_receipt_mismatch",
            f"validation_receipt.{key} must be true",
        )
    for key in (
        "future_person_a_output_acceptance_authorized",
        "production_execution_started",
        "project_integration_authorized",
        "step_4_1_closure_authorized",
        "u4_output_inspected",
    ):
        _require_false(receipt, key, "validation_receipt")
    _require(
        receipt.get("authorized_pilot_count") == 1
        and receipt.get("authorized_step_range") == "6.1-6.6"
        and receipt.get("selected_trajectory_id") == SELECTED_TRAJECTORY_ID
        and receipt.get("structural_failures") == [],
        "validation_receipt_mismatch",
        "validation receipt scope or failure state is incorrect",
    )


def validate_package(repo_root: Path, package_root: Path) -> Mapping[str, Any]:
    """Validate all exact authorities, trust records, and local decision files."""

    _validate_remote_authorities(repo_root)
    _validate_b_refresh(repo_root)
    _validate_a_acknowledgement(repo_root)
    _validate_c_signoff(repo_root)
    documents = _load_package(package_root)
    _validate_bound_source_records(repo_root, documents["authority_binding.json"])
    raw_by_name = {
        name: (package_root / name).read_bytes() for name in DOCUMENT_NAMES
    }
    _validate_inventory(documents, raw_by_name, DOCUMENT_NAMES)
    validate_decision_documents(documents)
    return {
        "a_acknowledgement_verified": True,
        "c_signoff_verified": True,
        "person_a_runtime_execution_authorized": True,
        "production_execution_started": False,
        "registry_v2_future_a_output_acceptance_authorized": False,
        "selected_pilot_hash_verified": True,
        "selected_trajectory_id": SELECTED_TRAJECTORY_ID,
        "u4_output_inspected": False,
    }


def _default_repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=_default_repo_root(),
    )
    parser.add_argument("--package-root", type=Path)
    parser.add_argument("--json", action="store_true")
    arguments = parser.parse_args()
    repo_root = arguments.repo_root.resolve()
    package_root = (
        arguments.package_root.resolve()
        if arguments.package_root
        else repo_root / PACKAGE_RELATIVE_PATH
    )
    try:
        result = validate_package(repo_root, package_root)
    except FinalRuntimeAuthorizationError as error:
        if arguments.json:
            print(json.dumps({"accepted": False, "error": str(error)}, sort_keys=True))
        else:
            print(f"FAIL: {error}")
        return 1
    payload = {"accepted": True, **result}
    if arguments.json:
        print(json.dumps(payload, sort_keys=True))
    else:
        print("PASS: bounded Person A Steps 6.1-6.6 are authorized")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
