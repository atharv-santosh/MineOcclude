#!/usr/bin/env python3
"""Run the focused final ACE validation for the canonical A6.6 closure."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CLOSURE_SCRIPT = ROOT / "scripts/build_person_a_canonical_multilayout_a6_6_closure.py"
CLOSURE_ROOT = ROOT / "docs/status/person_a_canonical_multilayout_a6_6_closure_v0_1"
E_RECEIPT = ROOT / (
    "docs/status/person_e_a_multilayout_activation_provenance_acceptance_v0_1/"
    "person_e_to_person_a_multilayout_activation_provenance_receipt.json"
)
C_PACKAGE = ROOT / "docs/status/person_c_c6a_completion_v0_1/package_manifest.json"
C_IDENTITY = ROOT / "docs/status/person_c_c6a_completion_v0_1/canonical_c6a_identity.json"
C_COMPLETION = ROOT / "docs/status/person_c_c6a_completion_v0_1/c6a_completion_receipt.json"
B_HANDOFF = ROOT / (
    "docs/status/phase6_runtime/"
    "person-a-canonical-c6a-multilayout-successor-seed-20260725-retry-"
    "20260804T211350Z/person_a_to_person_b_canonical_multilayout_handoff.json"
)
E_HANDOFF = B_HANDOFF.with_name(
    "person_a_to_person_e_canonical_multilayout_handoff.json"
)

ACE_BRANCH = "integration/ace-roadmap-audit"
AUTHORIZED_CHECKPOINT = "7ff511ba8f755f8e978bb2e713ac70ec378652e0"
PERSON_C_COMMIT = "b810bae554ba4f31018d39beb304c9b936387ca4"
MAIN_COMMIT = "4b4611c3dbbfa7b492c270b80d992448b0efca53"
C_PACKAGE_SHA256 = "612b03fea372d10c5f5b87cb581dd5f993035112e16aa1de7341801bdc35a9ef"


class ACEValidationError(RuntimeError):
    """A focused integration identity or packaging error."""


def _fail(message: str) -> None:
    raise ACEValidationError(message)


def _load_module(path: Path, name: str) -> Any:
    specification = importlib.util.spec_from_file_location(name, path)
    if specification is None or specification.loader is None:
        _fail(f"module is unavailable: {path}")
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


def _git(*arguments: str) -> str:
    process = subprocess.run(
        ["git", *arguments],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if process.returncode:
        _fail(process.stderr.strip() or f"git {' '.join(arguments)} failed")
    return process.stdout.strip()


def _is_ancestor(commit: str, descendant: str = "HEAD") -> bool:
    return subprocess.run(
        ["git", "merge-base", "--is-ancestor", commit, descendant],
        cwd=ROOT,
        check=False,
        capture_output=True,
    ).returncode == 0


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_object(path: Path, label: str) -> dict[str, Any]:
    try:
        document = json.loads(path.read_bytes())
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ACEValidationError(f"could not read {label}: {error}") from error
    if not isinstance(document, dict):
        _fail(f"{label} must be a JSON object")
    return document


def _json_bytes(document: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(
            dict(document),
            allow_nan=False,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _write_exclusive(path: Path, document: Mapping[str, Any]) -> None:
    if path.exists() or path.is_symlink():
        raise FileExistsError(f"immutable integration output exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(_json_bytes(document))
        handle.flush()
        os.fsync(handle.fileno())


def _descriptor(root: Path, path: Path) -> dict[str, Any]:
    return {
        "path": path.relative_to(root).as_posix(),
        "sha256": _sha256_file(path),
        "size_bytes": path.stat().st_size,
    }


def validate_and_package(
    *,
    person_c_commit: str,
    person_e_commit: str,
    person_a_commit: str,
    destination: Path,
) -> dict[str, Any]:
    """Validate the exact merge chain and create one immutable ACE receipt."""

    if destination.exists() or destination.is_symlink():
        raise FileExistsError(f"immutable ACE validation package exists: {destination}")
    if _git("branch", "--show-current") != ACE_BRANCH:
        _fail(f"focused validation requires {ACE_BRANCH}")
    if _git("status", "--porcelain=v1", "-uall"):
        _fail("focused validation requires a clean integration worktree")
    if person_c_commit != PERSON_C_COMMIT:
        _fail("integrated Person C commit differs")
    for commit, label in (
        (AUTHORIZED_CHECKPOINT, "authorized ACE checkpoint"),
        (person_c_commit, "Person C integration commit"),
        (person_e_commit, "Person E integration commit"),
        (person_a_commit, "Person A integration commit"),
    ):
        if not _is_ancestor(commit):
            _fail(f"{label} is not an ancestor of integration HEAD")
    if _git("rev-parse", "main") != MAIN_COMMIT or _git("rev-parse", "origin/main") != MAIN_COMMIT:
        _fail("main moved during the authorized integration")

    closure_module = _load_module(CLOSURE_SCRIPT, "ace_person_a_closure_validator")
    closure_result = closure_module.validate_closure_package(CLOSURE_ROOT)
    collection = closure_module._collection_summary()
    closure = _read_object(CLOSURE_ROOT / "a6_6_closure.json", "Person A closure")
    b_descriptor = closure.get("consumed_receipts", {}).get("person_b")
    e_descriptor = closure.get("consumed_receipts", {}).get("person_e")
    if not isinstance(b_descriptor, Mapping) or not isinstance(e_descriptor, Mapping):
        _fail("Person A closure receipt bindings are missing")
    person_b_commit = str(b_descriptor.get("commit", ""))
    if _is_ancestor(person_b_commit):
        _fail("Person B receipt branch was merged instead of receipt-consumed")
    b_packaged = CLOSURE_ROOT / str(b_descriptor.get("packaged_path", ""))
    b_result_descriptor = b_descriptor.get("result_artifact")
    if not isinstance(b_result_descriptor, Mapping):
        _fail("Person A closure lacks the Person B completed-control artifact")
    b_result_packaged = CLOSURE_ROOT / str(
        b_result_descriptor.get("packaged_path", "")
    )
    e_packaged = CLOSURE_ROOT / str(e_descriptor.get("packaged_path", ""))
    if (
        _sha256_file(b_packaged) != b_descriptor.get("sha256")
        or _sha256_file(b_result_packaged) != b_result_descriptor.get("sha256")
        or _sha256_file(e_packaged) != e_descriptor.get("sha256")
        or _sha256_file(E_RECEIPT) != e_descriptor.get("sha256")
        or E_RECEIPT.read_bytes() != e_packaged.read_bytes()
    ):
        _fail("integrated receipt bytes do not match the Person A closure")
    b_receipt = _read_object(b_packaged, "packaged Person B receipt")
    e_receipt = _read_object(e_packaged, "packaged Person E receipt")
    closure_module._validate_b_receipt(b_receipt)
    closure_module._validate_e_receipt(e_receipt)

    c_identity = _read_object(C_IDENTITY, "canonical C6A identity")
    c_completion = _read_object(C_COMPLETION, "canonical C6A completion")
    if (
        _sha256_file(C_PACKAGE) != C_PACKAGE_SHA256
        or c_identity.get("canonical_c6a_id") != closure_module.CANONICAL_C6A_ID
        or c_identity.get("status") != "CANONICAL"
        or c_completion.get("status") != "PASS"
        or c_completion.get("unresolved_blockers") != []
    ):
        _fail("canonical Person C C6A authority differs")
    b_handoff = _read_object(B_HANDOFF, "Person A-to-B successor handoff")
    e_handoff = _read_object(E_HANDOFF, "Person A-to-E successor handoff")
    if b_handoff.get("schema_version") != (
        "person-a-to-person-b-canonical-multilayout-handoff-v0.1"
    ):
        _fail("Person A-to-B handoff schema differs")
    if e_handoff.get("schema_version") != "person-a-to-person-e-canonical-multilayout-handoff-v0.1":
        _fail("Person A-to-E handoff schema differs")

    destination.mkdir(parents=True)
    manifest_path = destination / "integration_manifest.json"
    validation_path = destination / "validation_receipt.json"
    _write_exclusive(
        manifest_path,
        {
            "ace_branch": ACE_BRANCH,
            "ace_stop_gate_status": "A6_6_CLOSED",
            "authorized_checkpoint": AUTHORIZED_CHECKPOINT,
            "canonical_c6a_id": closure_module.CANONICAL_C6A_ID,
            "collection_identity": collection,
            "integrated_commits": {
                "person_a": person_a_commit,
                "person_c": person_c_commit,
                "person_e": person_e_commit,
            },
            "main_commit": MAIN_COMMIT,
            "person_b_branch_merged": False,
            "person_b_receipt_commit": person_b_commit,
            "person_b_receipt_sha256": b_descriptor["sha256"],
            "person_e_receipt_sha256": e_descriptor["sha256"],
            "schema_version": "ace-canonical-multilayout-closure-integration-v0.1",
            "status": "PASS",
        },
    )
    _write_exclusive(
        validation_path,
        {
            "a6_6_stop_gate_closed": True,
            "activation_indexes_and_inventories_valid": True,
            "canonical_c6a_authority_valid": True,
            "exact_source_identities_valid": True,
            "five_layout_collection_valid": True,
            "handoff_schemas_valid": True,
            "integration_packaging_importable": True,
            "person_a_closure_valid": closure_result["status"] == "PASS",
            "person_b_branch_merged": False,
            "person_b_receipt_consumption_valid": True,
            "person_e_receipt_consumption_valid": True,
            "schema_version": "ace-canonical-multilayout-closure-validation-v0.1",
            "status": "PASS",
            "unresolved_blockers": [],
        },
    )
    inventory_path = destination / "sha256_inventory.json"
    _write_exclusive(
        inventory_path,
        {
            "files": [
                _descriptor(destination, path)
                for path in (manifest_path, validation_path)
            ],
            "schema_version": "ace-canonical-multilayout-closure-inventory-v0.1",
            "status": "PASS",
        },
    )
    return {
        "a6_6_stop_gate_closed": True,
        "person_b_branch_merged": False,
        "status": "PASS",
        "validation_receipt": str(validation_path.resolve()),
        "validation_receipt_sha256": _sha256_file(validation_path),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--person-c-commit", required=True)
    parser.add_argument("--person-e-commit", required=True)
    parser.add_argument("--person-a-commit", required=True)
    parser.add_argument("--destination", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    namespace = _parser().parse_args(argv)
    result = validate_and_package(
        person_c_commit=namespace.person_c_commit,
        person_e_commit=namespace.person_e_commit,
        person_a_commit=namespace.person_a_commit,
        destination=namespace.destination.resolve(),
    )
    print(json.dumps(result, allow_nan=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
