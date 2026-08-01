#!/usr/bin/env python3
"""Validate a canonical Person B eight-family baseline-input manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from mineocclude.contracts.baseline_family_inputs import (
    FROZEN_BASELINE_FAMILY_IDS,
    validate_eight_family_input_manifest,
)


def canonical_json_bytes(value: Any) -> bytes:
    """Return the repository's sorted, indented canonical JSON bytes."""

    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def validate_manifest_path(path: Path) -> tuple[str, ...]:
    """Validate bytes and semantics without executing scientific code."""

    raw = path.read_bytes()
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return ("invalid_utf8_or_json",)
    errors = list(validate_eight_family_input_manifest(document))
    if raw != canonical_json_bytes(document):
        errors.append("noncanonical_json_bytes")
    return tuple(errors)


def verify_artifact_reference_bytes(
    reference: dict[str, Any], repository_root: Path
) -> bool:
    """Verify a local or external artifact before it may be consumed."""

    path = Path(reference["path"])
    if not path.is_absolute():
        path = repository_root / path
    if not path.is_file():
        return False
    raw = path.read_bytes()
    return len(raw) == reference["byte_size"] and (
        hashlib.sha256(raw).hexdigest() == reference["sha256"]
    )


def validate_bound_artifact_bytes(
    document: dict[str, Any], repository_root: Path
) -> tuple[str, ...]:
    """Verify exact input bytes, including C objects at their frozen commit."""

    errors: list[str] = []
    for artifact_type, reference in document["direct_inputs"].items():
        if not verify_artifact_reference_bytes(reference, repository_root):
            errors.append(f"{artifact_type}:byte_identity_mismatch")

    source_manifest_reference = document["direct_inputs"][
        "source_context_manifest"
    ]
    source_manifest_path = repository_root / source_manifest_reference["path"]
    source_manifest = json.loads(source_manifest_path.read_text(encoding="utf-8"))
    c_commit = source_manifest["person_c_expansion_acceptance"]
    for context in source_manifest["source_contexts"]:
        reference = context["capture_package"]
        try:
            raw = subprocess.check_output(
                ["git", "show", f"{c_commit}:{reference['path']}"],
                cwd=repository_root,
                stderr=subprocess.DEVNULL,
            )
        except subprocess.CalledProcessError:
            errors.append(
                f"{context['trajectory_id']}:capture_git_object_missing"
            )
            continue
        if len(raw) != reference["byte_size"] or (
            hashlib.sha256(raw).hexdigest() != reference["sha256"]
        ):
            errors.append(
                f"{context['trajectory_id']}:capture_byte_identity_mismatch"
            )
    return tuple(errors)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument(
        "--repository-root", type=Path, default=Path.cwd(), required=False
    )
    args = parser.parse_args()
    errors = validate_manifest_path(args.manifest.resolve())
    if not errors:
        document = json.loads(args.manifest.read_text(encoding="utf-8"))
        errors = validate_bound_artifact_bytes(
            document, args.repository_root.resolve()
        )
    if errors:
        for error in errors:
            print(f"ERROR={error}")
        print("PERSON_B_BASELINE_INPUT_V0_2_VALID=False")
        return 1
    print(f"REQUIRED_BASELINE_FAMILY_COUNT={len(FROZEN_BASELINE_FAMILY_IDS)}")
    print("PERSON_B_BASELINE_INPUT_V0_2_VALID=True")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
