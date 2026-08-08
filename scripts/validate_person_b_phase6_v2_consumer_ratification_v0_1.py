"""Validate Person B's additive v2-consumer owner-ratification package."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any

EXPECTED_FILES = {
    "authority_binding.json",
    "consumer_contract_ratification.json",
    "e_registry_compatibility.json",
    "execution_authorization.json",
    "owner_ratification.json",
    "validation_receipt.json",
}
INVENTORY_NAME = "sha256_inventory.json"
SCHEMA_TOKEN = "person-b-phase6-v2-consumer-ratification-v0-1"


class RatificationValidationError(ValueError):
    """Fail-closed ratification validation error."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RatificationValidationError(message)


def _formatted_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _load_canonical(path: Path) -> Mapping[str, Any]:
    payload = path.read_bytes()
    _require(not payload.startswith(b"\xef\xbb\xbf"), f"{path.name} has a BOM.")
    try:
        document = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RatificationValidationError(
            f"{path.name} is invalid JSON: {error}"
        ) from error
    _require(isinstance(document, Mapping), f"{path.name} root must be an object.")
    _require(
        payload == _formatted_json_bytes(document), f"{path.name} is not canonical."
    )
    _require(
        document.get("schema_version") == "1.0", f"{path.name} schema version differs."
    )
    schema_id = document.get("schema_id")
    _require(
        isinstance(schema_id, str) and SCHEMA_TOKEN in schema_id,
        f"{path.name} schema_id lacks the package token.",
    )
    return document


def _git(repository: Path, *arguments: str, binary: bool = False) -> bytes | str:
    try:
        completed = subprocess.run(
            ["git", "-C", str(repository), *arguments],
            check=True,
            capture_output=True,
            text=not binary,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise RatificationValidationError(f"Git validation failed: {error}") from error
    return completed.stdout


def validate_package(repository: Path, package_root: Path) -> dict[str, Any]:
    names = {path.name for path in package_root.iterdir() if path.is_file()}
    _require(
        names == EXPECTED_FILES | {INVENTORY_NAME}, "Ratification file set differs."
    )
    documents = {name: _load_canonical(package_root / name) for name in names}
    inventory = documents[INVENTORY_NAME]
    entries = inventory.get("files")
    _require(
        inventory.get("inventory_excludes_self") is True
        and isinstance(entries, Mapping)
        and set(entries) == EXPECTED_FILES,
        "SHA-256 inventory shape differs.",
    )
    for name in EXPECTED_FILES:
        actual = hashlib.sha256((package_root / name).read_bytes()).hexdigest()
        _require(entries.get(name) == actual, f"Inventory hash differs for {name}.")

    owner = documents["owner_ratification.json"]
    implementation_commit = owner.get("implementation_commit")
    _require(
        isinstance(implementation_commit, str) and len(implementation_commit) == 40,
        "Owner ratification lacks implementation commit.",
    )
    _require(
        _git(repository, "cat-file", "-t", implementation_commit).strip() == "commit",
        "Implementation commit is unavailable.",
    )
    files = owner.get("implementation_files")
    _require(isinstance(files, list) and files, "Implementation files are missing.")
    for entry in files:
        _require(isinstance(entry, Mapping), "Implementation file entry is malformed.")
        path = entry.get("path")
        sha256 = entry.get("sha256")
        _require(isinstance(path, str) and path, "Implementation path is invalid.")
        _require(
            isinstance(sha256, str) and len(sha256) == 64,
            "Implementation hash is invalid.",
        )
        payload = _git(
            repository, "show", f"{implementation_commit}:{path}", binary=True
        )
        _require(
            hashlib.sha256(payload).hexdigest() == sha256,
            f"Implementation hash differs: {path}",
        )

    required_owner = {
        "decision": "RATIFY_EXACT_V2_POSITIVE_CONTROL_CONSUMER",
        "person_a_ten_pilot_commit": "55776dc88302b89b52eef483a710fbf6811cf536",
        "person_b_expansion_selection_commit": "19f08b2e27217b781961da8f7299e1396a3ab703",
        "person_b_expansion_authorization_commit": "a838c9703003176d8e793bbd43dd6de917740be6",
        "person_c_expansion_acceptance_commit": "c6bff25b5ef4f5fdb0e1ef0ce0d22e3f8b5e4960",
        "authorized_execution": "person_b_frozen_visible_position_positive_control_only",
        "hidden_state_interpretation_authorized": False,
        "u4_output_inspected": False,
    }
    _require(
        all(owner.get(key) == value for key, value in required_owner.items()),
        "Owner ratification changes an authority or authorization boundary.",
    )
    contract = documents["consumer_contract_ratification.json"]
    for field in (
        "v1_consumer_preserved",
        "v2_dispatch_added",
        "global_frame_identity_supported",
        "context_local_identity_supported",
        "npy_chunks_supported",
        "multi_pilot_manifest_identities_supported",
        "literal_capture_sha_preserved",
        "canonical_state_hash_preserved",
        "frozen_target_unchanged",
        "frozen_fold_unchanged",
        "frozen_threshold_unchanged",
    ):
        _require(contract.get(field) is True, f"Consumer ratification lacks {field}.")
    _require(
        contract.get("visible_control_row_count") == 1000
        and contract.get("visible_control_layout_count") == 5,
        "Visible-control contract cardinality differs.",
    )
    compatibility = documents["e_registry_compatibility.json"]
    _require(
        compatibility.get("e_schema_change_required") is False
        and compatibility.get("decision")
        == "COMPATIBLE_WITH_FROZEN_GENERIC_REGISTRY_V2",
        "Person E compatibility decision differs.",
    )
    execution = documents["execution_authorization.json"]
    _require(
        execution.get("scientific_execution_performed") is False
        and execution.get("positive_control_execution_authorized") is True
        and execution.get("hidden_state_interpretation_authorized") is False
        and execution.get("additional_signers_required") == [],
        "Execution authorization is malformed or too broad.",
    )
    receipt = documents["validation_receipt.json"]
    _require(
        receipt.get("status") == "PASS"
        and receipt.get("focused_tests_pass") is True
        and receipt.get("u4_output_inspected") is False,
        "Validation receipt is not PASS.",
    )
    return {
        "implementation_commit": implementation_commit,
        "package_file_count": len(names),
        "status": "PASS",
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--package-root", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = validate_package(
        args.repository_root.resolve(), args.package_root.resolve()
    )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
