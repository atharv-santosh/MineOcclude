"""Build Person A's non-executing Step 6 runtime acknowledgement."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = ROOT / "docs" / "status" / "person_a_step6_runtime_acknowledgement_v0_1"
A_STARTING_AUTHORITY = "0416ce88060277b28512f95dca0af94984a8211d"
B_REFRESH_AUTHORITY = "8942d5d514a4d124ac0baa36ffc803dc598c4f1f"
A_PREFLIGHT_ROOT = (
    "docs/status/person_a_phase4_step4_1_production_handoff_preflight_v0_1"
)
B_REFRESH_ROOT = "docs/status/person_b_phase4_step4_1_step6_authorization_refresh_v0_1"
BUILDER_PATH = "scripts/build_person_a_step6_runtime_acknowledgement_v0_1.py"
TEST_PATH = "tests/models/test_person_a_step6_runtime_acknowledgement_v0_1.py"
SCHEMA_VERSION = "1.0"
BOUNDED_STEPS = ("6.1", "6.2", "6.3", "6.4", "6.5", "6.6")
OUTPUT_PATHS = (
    "authority_binding.json",
    "execution_gate.json",
    "frozen_runtime_configuration.json",
    "runtime_acknowledgement.json",
    "sha256_inventory.json",
    "validation_receipt.json",
)

B_SOURCES = {
    "authorization_decision": {
        "path": f"{B_REFRESH_ROOT}/authorization_decision.json",
        "sha256": ("4be0cc05839dc1d51b0e110510b39009eafb4e07b913903b812c4c940d6b7628"),
    },
    "person_a_required_acknowledgement": {
        "path": f"{B_REFRESH_ROOT}/person_a_required_acknowledgement.json",
        "sha256": ("97b227ecfdf4dcfc2ac7616cb02acc3db3b9e743ec0d1b64055d6861a421d255"),
    },
    "person_c_required_decision": {
        "path": f"{B_REFRESH_ROOT}/person_c_required_decision.json",
        "sha256": ("670319f62af4a59afdd04e0f52917ce557744a7fdf264315ca93f9ee5c9119e1"),
    },
    "refreshed_c_candidate_selection": {
        "path": f"{B_REFRESH_ROOT}/refreshed_c_candidate_selection.json",
        "sha256": ("d6971bcf8c0e7ab9e77235336f0a96ccecbb6517b4a9bd0f9b9e61e7975479f3"),
    },
}

A_SOURCES = {
    "activation_contract": {
        "path": f"{A_PREFLIGHT_ROOT}/activation_contract.json",
        "sha256": ("3a0195317121b7a07f47bd0eed624635adafa2b2ba3530aa3236ae9b2634f03f"),
    },
    "extraction_contract": {
        "path": f"{A_PREFLIGHT_ROOT}/extraction_contract.json",
        "sha256": ("3d74495887236cc99788c95ed04ad5a24324e4bff0ac5ee841257c9ceae69f61"),
    },
    "immutable_runtime_configuration": {
        "path": f"{A_PREFLIGHT_ROOT}/immutable_runtime_configuration.json",
        "sha256": ("eb634c1e81c65a724b7cf32cbfe03f62e80a4428afda605071e1a43c6d0f4c10"),
    },
    "model_input_contract": {
        "path": f"{A_PREFLIGHT_ROOT}/model_input_contract.json",
        "sha256": ("df37ae94c0912b4e1f9780f053d54fa0fe9fd29f85ad8319b86e05c7d528d06b"),
    },
    "rollout_contract": {
        "path": f"{A_PREFLIGHT_ROOT}/rollout_contract.json",
        "sha256": ("25511191c5790c8f39914d60b8e6b5f5fc88df6b269eba71266e75388c280d5b"),
    },
}

PROTECTED_FALSE_FIELDS = frozenset(
    {
        "aggregate_authorization_present",
        "automatic_phase6_transition_allowed",
        "execution_gate_open",
        "model_input_bytes_created",
        "person_a_phase6_authorized",
        "production_activation_bytes_created",
        "production_execution_started",
        "production_extraction_bytes_created",
        "production_rollout_bytes_created",
        "registry_v2_acceptance_authorized",
        "scientific_execution_claimed",
        "scientific_execution_performed",
        "scientific_use_authorized",
        "self_authorizes_phase6",
        "u4_output_inspected",
    }
)


def _completed(command: list[str]) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        command,
        cwd=ROOT,
        check=False,
        capture_output=True,
    )


def _git_text(*arguments: str) -> str:
    result = _completed(["git", *arguments])
    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode("utf-8", errors="replace").strip())
    return result.stdout.decode("utf-8").strip()


def _git_bytes(commit: str, path: str) -> bytes:
    result = _completed(["git", "show", f"{commit}:{path}"])
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"Unable to read {commit}:{path}: {detail}")
    return result.stdout


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _source_record(
    commit: str,
    name: str,
    expected: dict[str, str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    raw = _git_bytes(commit, expected["path"])
    digest = _sha256(raw)
    if digest != expected["sha256"]:
        raise RuntimeError(f"Changed source bytes: {name}")
    document = json.loads(raw)
    if not isinstance(document, dict):
        raise TypeError(f"Source is not an object: {name}")
    return document, {
        "byte_size": len(raw),
        "path": expected["path"],
        "sha256": digest,
        "source_commit": commit,
        "source_read_policy": "exact_git_commit_object",
    }


def verify_authorities() -> None:
    for commit in (A_STARTING_AUTHORITY, B_REFRESH_AUTHORITY):
        result = _completed(["git", "cat-file", "-e", f"{commit}^{{commit}}"])
        if result.returncode != 0:
            raise RuntimeError(f"Missing authority commit: {commit}")
    if (
        _completed(
            ["git", "merge-base", "--is-ancestor", A_STARTING_AUTHORITY, "HEAD"]
        ).returncode
        != 0
    ):
        raise RuntimeError("Person A starting authority is not an ancestor")
    if (
        _completed(
            [
                "git",
                "merge-base",
                "--is-ancestor",
                B_REFRESH_AUTHORITY,
                "origin/role/person-b-analysis",
            ]
        ).returncode
        != 0
    ):
        raise RuntimeError("Person B refresh is not remote-authoritative")


def _load_sources() -> tuple[
    dict[str, dict[str, Any]],
    dict[str, dict[str, Any]],
    list[dict[str, Any]],
]:
    b_documents: dict[str, dict[str, Any]] = {}
    a_documents: dict[str, dict[str, Any]] = {}
    records: list[dict[str, Any]] = []
    for name, expected in sorted(B_SOURCES.items()):
        document, record = _source_record(
            B_REFRESH_AUTHORITY,
            name,
            expected,
        )
        b_documents[name] = document
        records.append({"owner": "person_b", **record})
    for name, expected in sorted(A_SOURCES.items()):
        document, record = _source_record(
            A_STARTING_AUTHORITY,
            name,
            expected,
        )
        a_documents[name] = document
        records.append({"owner": "person_a", **record})
    return a_documents, b_documents, records


def _validate_b_refresh(b_documents: dict[str, dict[str, Any]]) -> None:
    decision = b_documents["authorization_decision"]
    runtime = decision["decision_layers"]["person_a_runtime_execution"]
    if runtime["b_decision_contribution"]["decision"] != ("CONDITIONAL_SCOPE_APPROVAL"):
        raise RuntimeError("Person B conditional decision changed")
    if runtime["authorized"] is not False:
        raise RuntimeError("Person B unexpectedly authorized execution")
    if runtime["bounded_scope"]["allowed_steps"] != list(BOUNDED_STEPS):
        raise RuntimeError("Person B bounded steps changed")
    if set(runtime["missing_required_signers"]) != {"person_a", "person_c"}:
        raise RuntimeError("Person B missing-signer state changed")
    required = b_documents["person_a_required_acknowledgement"]
    if required["required_values"]["bounded_steps"] != list(BOUNDED_STEPS):
        raise RuntimeError("Person A acknowledgement scope changed")
    if required["current_acknowledgement"] is not None:
        raise RuntimeError("Person B package unexpectedly contains A acknowledgement")
    c_decision = b_documents["person_c_required_decision"]
    if c_decision["current_decision"] is not None:
        raise RuntimeError("Person C decision is no longer missing")
    if c_decision["required_positive_decision"] != {
        "decision": "ACCEPT_SINGLE_PILOT_FOR_SCIENTIFIC_USE",
        "owner": "person_c",
        "scientific_use": "accepted_for_single_pilot_step_6_1",
        "scope": "single_pilot_steps_6_1_through_6_6",
    }:
        raise RuntimeError("Person C required decision changed")
    selection = b_documents["refreshed_c_candidate_selection"]
    if selection["selection_count"] != 15:
        raise RuntimeError("Person B C-candidate count changed")
    if selection["accepted_scientific_input_count"] != 0:
        raise RuntimeError("Person B unexpectedly accepted a C candidate")


def _runtime_values(
    a_documents: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    configuration = a_documents["immutable_runtime_configuration"]
    if configuration["status"] != "PROPOSED_FROZEN_CONFIGURATION":
        raise RuntimeError("Person A frozen configuration status changed")
    rows = configuration["configuration"]
    if not all(
        row.get("classification") == "PROPOSED_FROZEN_CONFIGURATION" for row in rows
    ):
        raise RuntimeError("Person A runtime value classification changed")
    values = {row["name"]: row["value"] for row in rows}
    required_names = {
        "activation_index_key",
        "activation_layers",
        "chunk_and_index_rules",
        "extraction_hook",
        "input_dimensions_hwc",
        "main_checkpoint_sha256",
        "model_config_sha256",
        "pooling",
        "preprocessed_dimensions_chw",
        "preprocessing_identity",
        "rollout_configuration",
        "source_tensor_dtype",
        "source_tensor_shape",
        "vae_checkpoint_sha256",
        "visual_tokens_per_frame",
    }
    if set(values) != required_names:
        raise RuntimeError("Person A frozen runtime inventory changed")
    if values["chunk_and_index_rules"]["no_overwrite"] is not True:
        raise RuntimeError("Frozen chunk no-overwrite rule changed")
    for contract_name in (
        "activation_contract",
        "extraction_contract",
        "model_input_contract",
        "rollout_contract",
    ):
        if a_documents[contract_name]["no_overwrite"] is not True:
            raise RuntimeError(f"{contract_name} no-overwrite rule changed")
    return values


def _authority_binding(records: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "authorities": {
            "person_a": {
                "branch": "role/person-a-model",
                "starting_authority": A_STARTING_AUTHORITY,
            },
            "person_b_refresh": {
                "branch": "role/person-b-analysis",
                "refresh_authority": B_REFRESH_AUTHORITY,
                "refresh_authority_verified": True,
            },
        },
        "builder_path": BUILDER_PATH,
        "claims": {
            "model_input_bytes_created": False,
            "person_a_phase6_authorized": False,
            "production_activation_bytes_created": False,
            "production_execution_started": False,
            "production_extraction_bytes_created": False,
            "production_rollout_bytes_created": False,
            "registry_v2_acceptance_authorized": False,
            "scientific_execution_performed": False,
            "scientific_use_authorized": False,
            "u4_output_inspected": False,
        },
        "schema_id": "person-a-step6-runtime-ack-v0.1-authority-binding",
        "schema_version": SCHEMA_VERSION,
        "source_records": records,
        "test_path": TEST_PATH,
    }


def _frozen_configuration(values: dict[str, Any]) -> dict[str, Any]:
    return {
        "activation": {
            "index_key": values["activation_index_key"],
            "layers": values["activation_layers"],
            "pooling": values["pooling"],
            "visual_tokens_per_frame": values["visual_tokens_per_frame"],
        },
        "checkpoint": {
            "main_checkpoint_sha256": values["main_checkpoint_sha256"],
            "model_config_sha256": values["model_config_sha256"],
            "vae_checkpoint_sha256": values["vae_checkpoint_sha256"],
        },
        "classification": "ACKNOWLEDGED_FROZEN_FOR_FUTURE_BOUNDED_RUNTIME",
        "configuration_identity": A_SOURCES["immutable_runtime_configuration"][
            "sha256"
        ],
        "extraction": {
            "hook": values["extraction_hook"],
            "source_tensor_dtype": values["source_tensor_dtype"],
            "source_tensor_shape": values["source_tensor_shape"],
        },
        "input_and_preprocessing": {
            "input_dimensions_hwc": values["input_dimensions_hwc"],
            "preprocessed_dimensions_chw": values["preprocessed_dimensions_chw"],
            "preprocessing_identity": values["preprocessing_identity"],
        },
        "no_overwrite": {
            "activation_contract": True,
            "chunk_and_index": values["chunk_and_index_rules"],
            "extraction_contract": True,
            "model_input_contract": True,
            "rollout_contract": True,
        },
        "rollout": values["rollout_configuration"],
        "schema_id": "person-a-step6-runtime-ack-v0.1-frozen-configuration",
        "schema_version": SCHEMA_VERSION,
        "source_commit": A_STARTING_AUTHORITY,
        "source_path": A_SOURCES["immutable_runtime_configuration"]["path"],
    }


def _acknowledgement() -> dict[str, Any]:
    return {
        "accepted_person_c_decision_id": None,
        "acknowledgement_id": "person-a-step6-runtime-conditions-v0-1",
        "accepts_responsibility_for_bounded_steps": True,
        "automatic_phase6_transition_allowed": False,
        "bounded_steps": list(BOUNDED_STEPS),
        "candidate_only_output_classification": True,
        "immutable_runtime_configuration_identity": A_SOURCES[
            "immutable_runtime_configuration"
        ]["sha256"],
        "owner": "person_a",
        "owner_authority_commit": A_STARTING_AUTHORITY,
        "person_a_phase6_authorized": False,
        "person_a_signer_acknowledgement_complete": True,
        "production_execution_started": False,
        "registry_v2_acceptance_authorized": False,
        "scientific_execution_claimed": False,
        "scientific_use_authorized": False,
        "selected_git_object_sha256": None,
        "selected_trajectory_id": None,
        "self_authorizes_phase6": False,
        "status": "ACKNOWLEDGED_AWAITING_C_PILOT_AND_AGGREGATE_AUTHORIZATION",
        "u4_output_inspected": False,
    }


def _execution_gate(
    b_documents: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    selection = b_documents["refreshed_c_candidate_selection"]
    return {
        "aggregate_authorization_present": False,
        "aggregate_authorization_required": True,
        "c_accepted_pilot_required": True,
        "candidate_selection_binding": {
            "candidate_count": selection["selection_count"],
            "person_b_refresh_commit": B_REFRESH_AUTHORITY,
            "source_commit": selection["refreshed_selection_source_commit"],
            "source_path": B_SOURCES["refreshed_c_candidate_selection"]["path"],
            "source_set_digest": selection["source_set_digest"],
        },
        "execution_gate_open": False,
        "person_a_acknowledgement_complete": True,
        "person_b_conditional_scope_approval_verified": True,
        "production_execution_started": False,
        "required_person_c_pilot_decision": {
            "accepted_person_c_decision_id": None,
            "decision": "ACCEPT_SINGLE_PILOT_FOR_SCIENTIFIC_USE",
            "git_object_sha256": None,
            "owner": "person_c",
            "owner_authority_commit": None,
            "scientific_use": "accepted_for_single_pilot_step_6_1",
            "scope": "single_pilot_steps_6_1_through_6_6",
            "source_path": None,
            "state": "MISSING_REQUIRED_C_SIGNED_ACCEPTED_PILOT",
            "trajectory_id": None,
        },
        "schema_id": "person-a-step6-runtime-ack-v0.1-execution-gate",
        "schema_version": SCHEMA_VERSION,
        "state": "BLOCKED_PENDING_C_PILOT_AND_AGGREGATE_AUTHORIZATION",
    }


def _validation_receipt() -> dict[str, Any]:
    return {
        "accepted_artifact_count": 0,
        "accepted_placeholder_count": 0,
        "b_refresh_authority_verified": True,
        "canonical_json_validation_passed": True,
        "focused_validation_passed": True,
        "git_diff_check_passed": True,
        "model_input_bytes_created": False,
        "person_a_phase6_authorized": False,
        "person_a_signer_acknowledgement_complete": True,
        "production_activation_bytes_created": False,
        "production_execution_started": False,
        "production_extraction_bytes_created": False,
        "production_rollout_bytes_created": False,
        "registry_v2_acceptance_authorized": False,
        "schema_id": "person-a-step6-runtime-ack-v0.1-validation-receipt",
        "schema_version": SCHEMA_VERSION,
        "scientific_execution_performed": False,
        "scientific_use_authorized": False,
        "u4_output_inspected": False,
    }


def _protected_false_violations(value: Any, path: str) -> list[str]:
    violations: list[str] = []
    if isinstance(value, dict):
        for key in sorted(value):
            child = value[key]
            child_path = f"{path}.{key}"
            if key in PROTECTED_FALSE_FIELDS and child is not False:
                violations.append(f"{child_path} must be exact Boolean false")
            violations.extend(_protected_false_violations(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            violations.extend(_protected_false_violations(child, f"{path}[{index}]"))
    return violations


def validate_package(documents: dict[str, Any]) -> tuple[str, ...]:
    violations: list[str] = []
    if set(documents) != set(OUTPUT_PATHS):
        violations.append("Package path inventory changed")
    for path, document in sorted(documents.items()):
        violations.extend(_protected_false_violations(document, path))
    acknowledgement = documents.get("runtime_acknowledgement.json", {})
    if acknowledgement.get("person_a_signer_acknowledgement_complete") is not True:
        violations.append("Person A signer acknowledgement is incomplete")
    if acknowledgement.get("accepts_responsibility_for_bounded_steps") is not True:
        violations.append("Person A bounded-step responsibility is missing")
    if acknowledgement.get("bounded_steps") != list(BOUNDED_STEPS):
        violations.append("Person A bounded-step scope changed")
    for field in (
        "accepted_person_c_decision_id",
        "selected_git_object_sha256",
        "selected_trajectory_id",
    ):
        if acknowledgement.get(field) is not None:
            violations.append(f"{field} must remain null before C decision")
    gate = documents.get("execution_gate.json", {})
    if gate.get("c_accepted_pilot_required") is not True:
        violations.append("Exact C-accepted pilot is not required")
    required_c = gate.get("required_person_c_pilot_decision", {})
    if required_c.get("state") != "MISSING_REQUIRED_C_SIGNED_ACCEPTED_PILOT":
        violations.append("Person C pilot gate state changed")
    configuration = documents.get("frozen_runtime_configuration.json", {})
    if (
        configuration.get("configuration_identity")
        != A_SOURCES["immutable_runtime_configuration"]["sha256"]
    ):
        violations.append("Frozen runtime identity changed")
    no_overwrite = configuration.get("no_overwrite", {})
    if not isinstance(no_overwrite, dict) or any(
        value is not True
        for key, value in no_overwrite.items()
        if key != "chunk_and_index"
    ):
        violations.append("Contract no-overwrite rule changed")
    if (
        not isinstance(no_overwrite, dict)
        or no_overwrite.get("chunk_and_index", {}).get("no_overwrite") is not True
    ):
        violations.append("Chunk no-overwrite rule changed")
    receipt = documents.get("validation_receipt.json", {})
    for field in (
        "accepted_artifact_count",
        "accepted_placeholder_count",
    ):
        if receipt.get(field) != 0:
            violations.append(f"{field} must equal zero")
    return tuple(violations)


def build_documents() -> dict[str, Any]:
    verify_authorities()
    a_documents, b_documents, records = _load_sources()
    _validate_b_refresh(b_documents)
    values = _runtime_values(a_documents)
    documents: dict[str, Any] = {
        "authority_binding.json": _authority_binding(records),
        "execution_gate.json": _execution_gate(b_documents),
        "frozen_runtime_configuration.json": _frozen_configuration(values),
        "runtime_acknowledgement.json": _acknowledgement(),
        "validation_receipt.json": _validation_receipt(),
    }
    documents["sha256_inventory.json"] = {
        "files": {
            path: _sha256(_json_bytes(document))
            for path, document in sorted(documents.items())
        },
        "inventory_excludes_self": True,
        "schema_id": "person-a-step6-runtime-ack-v0.1-sha256-inventory",
        "schema_version": SCHEMA_VERSION,
    }
    violations = validate_package(documents)
    if violations:
        raise RuntimeError("; ".join(violations))
    return documents


def write_documents(output_root: Path) -> None:
    documents = build_documents()
    output_root.mkdir(parents=True, exist_ok=True)
    expected = {output_root / path for path in documents}
    existing = {path for path in output_root.rglob("*") if path.is_file()}
    if existing - expected:
        raise RuntimeError("Unexpected output paths exist")
    for path, document in sorted(documents.items()):
        (output_root / path).write_bytes(_json_bytes(document))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build Person A's Step 6 runtime acknowledgement."
    )
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_ROOT)
    arguments = parser.parse_args()
    write_documents(arguments.output_dir.resolve())


if __name__ == "__main__":
    main()
