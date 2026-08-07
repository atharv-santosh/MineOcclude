#!/usr/bin/env python3
"""Independently validate and co-sign Person C's six wall-parallel frames.

This script reads Person C's artifacts through exact commit/path/SHA-256
bindings, rebuilds every derived quantity from the accepted geometry, replays
Person B's own projection over every captured target-bearing state row, and
only then writes Person B's additive co-sign. It never modifies a Person C
byte, never builds the oracle-target manifest, and never runs any activation
analysis.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from mineocclude.analysis.coordinate_frame_cosign_v0_1 import (  # noqa: E402
    COSIGN_PACKAGE_DIRECTORY,
    COSIGNED_FRAME_DIRECTORY,
    DECISION_DATE,
    PERSON_C_COMMIT,
    PERSON_C_COORDINATE_FRAME_AUTHORITY_PATH,
    PERSON_C_COORDINATE_FRAME_AUTHORITY_SHA256,
    CoordinateCosignError,
    build_cosign_document,
    cosign_frame,
    derive_cosign_code_sha,
    load_accepted_geometry,
    load_person_c_authority,
    replay_projection_against_capture_packages,
    require,
    sha256_bytes,
    validate_layout_frame,
)
from mineocclude.analysis.manifests import canonical_json_bytes  # noqa: E402

PACKAGE = ROOT / COSIGN_PACKAGE_DIRECTORY
FRAMES = ROOT / COSIGNED_FRAME_DIRECTORY

COSIGN_DOCUMENT = "coordinate_frame_cosign.json"
VALIDATION_RECEIPT = "validation_receipt.json"
SHA256_INVENTORY = "sha256_inventory.json"
COSIGN_RECEIPT_ID = "person-b-66-cell-coordinate-frame-cosign-v0.1"


def _write(path: Path, document: object) -> str:
    payload = canonical_json_bytes(document) + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return hashlib.sha256(payload).hexdigest()


def _current_branch() -> str:
    return subprocess.run(
        ["git", "-C", str(ROOT), "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True,
        check=True,
    ).stdout.decode("utf-8").strip()


def build() -> dict[str, object]:
    code_sha = derive_cosign_code_sha(ROOT)
    branch = _current_branch()
    require(
        branch == "role/person-b-analysis",
        f"co-sign must be published on role/person-b-analysis, not {branch!r}",
    )

    intake = load_person_c_authority(repository_root=ROOT)
    geometry = load_accepted_geometry(repository_root=ROOT)
    frames = intake["frames"]

    layout_results = [
        validate_layout_frame(layout_id, frames[layout_id], geometry[layout_id])
        for layout_id in sorted(frames)
    ]
    failed = [item["layout_id"] for item in layout_results if not item["compatible"]]
    require(
        not failed,
        "refusing to co-sign; incompatible layouts: "
        + ", ".join(
            f"{item['layout_id']}({', '.join(item['failed_checks'])})"
            for item in layout_results
            if not item["compatible"]
        ),
    )

    replay = replay_projection_against_capture_packages(frames, repository_root=ROOT)
    require(
        replay["replay_pass"],
        "refusing to co-sign; Person B's projection replay did not match "
        f"Person C's captured state: {json.dumps(replay['checks'])}",
    )

    cosigned_hashes: dict[str, str] = {}
    person_c_frame_hashes = {
        layout_id: sha256_bytes(payload)
        for layout_id, payload in intake["frame_bytes"].items()
    }
    for layout_id in sorted(frames):
        cosigned = cosign_frame(
            frames[layout_id],
            person_b_branch=branch,
            person_b_commit=None,
            cosign_receipt_id=COSIGN_RECEIPT_ID,
        )
        cosigned_hashes[layout_id] = _write(FRAMES / f"{layout_id}.json", cosigned)

    document = build_cosign_document(
        layout_results=layout_results,
        replay=replay,
        cosigned_hashes=cosigned_hashes,
        person_c_frame_hashes=person_c_frame_hashes,
        code_sha=code_sha,
        person_b_branch=branch,
        person_b_commit=None,
    )
    cosign_sha = _write(PACKAGE / COSIGN_DOCUMENT, document)

    receipt = {
        "schema_id": "person-b-66-cell-coordinate-frame-cosign-v0.1-validation-receipt",
        "schema_version": "1.0",
        "decision_date": DECISION_DATE,
        "person_c_commit": PERSON_C_COMMIT,
        "person_c_coordinate_frame_path": PERSON_C_COORDINATE_FRAME_AUTHORITY_PATH,
        "person_c_coordinate_frame_sha256": (
            PERSON_C_COORDINATE_FRAME_AUTHORITY_SHA256
        ),
        "person_c_coordinate_frame_sha256_observed": intake["authority_sha256"],
        "person_c_coordinate_frame_hash_unchanged": (
            intake["authority_sha256"] == PERSON_C_COORDINATE_FRAME_AUTHORITY_SHA256
        ),
        "person_c_frame_file_sha256": dict(sorted(person_c_frame_hashes.items())),
        "person_b_cosigned_frame_sha256": dict(sorted(cosigned_hashes.items())),
        "checks_per_layout": {
            item["layout_id"]: item["checks"] for item in layout_results
        },
        "projection_replay_checks": replay["checks"],
        "state_row_count": replay["state_row_count"],
        "target_bearing_row_count": replay["target_bearing_row_count"],
        "capture_package_count": replay["capture_package_count"],
        "coordinate_frame_compatible": True,
        "person_b_coordinate_frame_signed": True,
        "scientific_result_inspected": False,
        "outcome_dependent_change": False,
    }
    receipt_sha = _write(PACKAGE / VALIDATION_RECEIPT, receipt)

    inventory_files = [
        (f"{COSIGN_PACKAGE_DIRECTORY}/{COSIGN_DOCUMENT}", cosign_sha),
        (f"{COSIGN_PACKAGE_DIRECTORY}/{VALIDATION_RECEIPT}", receipt_sha),
    ] + [
        (f"{COSIGNED_FRAME_DIRECTORY}/{layout_id}.json", cosigned_hashes[layout_id])
        for layout_id in sorted(cosigned_hashes)
    ]
    inventory = {
        "schema_id": "person-b-66-cell-coordinate-frame-cosign-v0.1-sha256-inventory",
        "schema_version": "1.0",
        "decision_date": DECISION_DATE,
        "inventory_excludes_self": True,
        "file_count": len(inventory_files),
        "files": [
            {
                "path": path,
                "sha256": digest,
                "byte_size": (ROOT / path).stat().st_size,
            }
            for path, digest in inventory_files
        ],
    }
    _write(PACKAGE / SHA256_INVENTORY, inventory)

    return {
        "code_sha": code_sha,
        "layout_count": len(layout_results),
        "coordinate_frame_compatible": True,
        "person_b_coordinate_frame_signed": True,
        "coordinate_frame_hash_unchanged": receipt[
            "person_c_coordinate_frame_hash_unchanged"
        ],
        "capture_package_count": replay["capture_package_count"],
        "state_row_count": replay["state_row_count"],
        "target_bearing_row_count": replay["target_bearing_row_count"],
        "cosign_path": f"{COSIGN_PACKAGE_DIRECTORY}/{COSIGN_DOCUMENT}",
        "cosign_sha256": cosign_sha,
        "validation_receipt_sha256": receipt_sha,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()
    try:
        result = build()
    except CoordinateCosignError as error:
        print(f"PERSON_B_COORDINATE_FRAME_COSIGN=FAIL {error}", file=sys.stderr)
        return 1
    if not args.quiet:
        print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
