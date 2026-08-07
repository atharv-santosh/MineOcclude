#!/usr/bin/env python3
"""Fail-closed validator for the Person B 66-cell oracle-target package.

Rebuilds every published artifact from the bound Person C, Person E, and
Person A authorities and requires byte-for-byte agreement.  Writes nothing,
reads no activation bytes, and executes no scientific metric.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from mineocclude.analysis.manifests import validate_sealed_artifact  # noqa: E402
from mineocclude.analysis.oracle_target_66_cell_v0_1 import (  # noqa: E402
    ORACLE_PACKAGE_DIRECTORY,
    OracleTargetError,
    require,
)

BUILDER_PATH = ROOT / "scripts" / "build_person_b_66_cell_oracle_target_v0_1.py"
PACKAGE = ROOT / ORACLE_PACKAGE_DIRECTORY

EXPECTED_ARTIFACT_TYPES = {
    "person_a_identity_resolution.json": "person_b_person_a_identity_resolution",
    "row_universe_receipt_v0_2.json": "person_b_66_cell_row_universe_receipt_v0_2",
    "admission_exclusion_ledger.json": "person_b_66_cell_admission_exclusion_ledger",
    "fold_compatibility_receipt.json": "person_b_66_cell_fold_compatibility_receipt",
    "oracle_target_manifest.json": "person_b_66_cell_oracle_target_manifest",
    "u4_status.json": "person_b_66_cell_u4_status",
    "b_to_a_successor_handoff.json": (
        "person_b_to_person_a_66_cell_successor_handoff"
    ),
    "b_to_d_successor_handoff.json": (
        "person_b_to_person_d_66_cell_successor_handoff"
    ),
}


def _load_builder():
    spec = importlib.util.spec_from_file_location(
        "person_b_66_cell_oracle_target_builder", BUILDER_PATH
    )
    module = importlib.util.module_from_spec(spec)
    if spec.loader is None:  # pragma: no cover - defensive
        raise OracleTargetError("Could not load the oracle-target builder.")
    spec.loader.exec_module(module)
    return module


def validate() -> dict:
    builder = _load_builder()
    ordered = list(builder.ORDERED_JSON_FILES) + list(builder.ORDERED_JSONL_FILES)

    before = {}
    for name in ordered + [builder.SHA256_INVENTORY]:
        path = PACKAGE / name
        require(path.is_file(), f"missing published artifact: {name}")
        before[name] = path.read_bytes()

    builder.build()

    for name in ordered + [builder.SHA256_INVENTORY]:
        after = (PACKAGE / name).read_bytes()
        require(
            after == before[name],
            f"{name} is not deterministically reproducible",
        )

    for name in builder.ORDERED_JSON_FILES:
        document = json.loads(before[name].decode("utf-8"))
        validate_sealed_artifact(document, expected_type=EXPECTED_ARTIFACT_TYPES[name])

    manifest = json.loads(
        before[builder.ORACLE_TARGET_MANIFEST].decode("utf-8")
    )
    records = [
        json.loads(line)
        for line in before[builder.ORACLE_TARGET_RECORDS].decode("utf-8").splitlines()
        if line.strip()
    ]
    require(
        len(records) == manifest["oracle_target_row_count"],
        "oracle target record count disagrees with the manifest",
    )
    require(
        hashlib.sha256(before[builder.ORACLE_TARGET_RECORDS]).hexdigest()
        == manifest["target_records_sha256"],
        "oracle target records hash disagrees with the manifest",
    )

    rows = [
        json.loads(line)
        for line in before[builder.ROW_UNIVERSE_RECORDS].decode("utf-8").splitlines()
        if line.strip()
    ]
    receipt = json.loads(before[builder.ROW_UNIVERSE_RECEIPT].decode("utf-8"))
    require(
        len(rows) == receipt["total_model_frame_key_count"],
        "row universe record count disagrees with the receipt",
    )

    inventory = json.loads(before[builder.SHA256_INVENTORY].decode("utf-8"))
    require(inventory["file_count"] == len(ordered), "inventory file_count is wrong")
    for item in inventory["files"]:
        name = item["path"].rsplit("/", 1)[-1]
        require(name in before, f"inventory names an unknown file: {name}")
        require(
            hashlib.sha256(before[name]).hexdigest() == item["sha256"],
            f"inventory SHA-256 mismatch for {name}",
        )

    require(
        manifest["frozen_step_4_1_decision"] == "FAIL",
        "the frozen Step 4.1 FAIL decision was reopened",
    )
    require(
        manifest["activation_analysis_executed"] is False
        and manifest["u1_u3_executed"] is False
        and manifest["u4_executed"] is False,
        "the manifest claims activation-dependent analysis was executed",
    )
    u4 = json.loads(before[builder.U4_STATUS].decode("utf-8"))
    require(
        u4["CURRENT_66_CELL_U4_REVEAL_ELIGIBLE"] is False
        and u4["U4_SUPPLEMENTAL_CAPTURE_REQUIRED"] is True
        and u4["heldout_event_ids_frozen"] is False,
        "U4 status changed without a new decision record",
    )
    fold = json.loads(before[builder.FOLD_COMPATIBILITY_RECEIPT].decode("utf-8"))
    require(
        fold["fold_compatibility_pass"] is True and fold["leakage_audit_pass"] is True,
        "fold compatibility or leakage audit did not pass",
    )

    return {
        "validated": True,
        "deterministic": True,
        "oracle_target_row_count": manifest["oracle_target_row_count"],
        "admitted_analysis_row_count": receipt["admitted_analysis_row_count"],
        "excluded_analysis_row_count": receipt["excluded_analysis_row_count"],
        "oracle_target_manifest_sha256": hashlib.sha256(
            before[builder.ORACLE_TARGET_MANIFEST]
        ).hexdigest(),
        "fold_compatibility_pass": fold["fold_compatibility_pass"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()
    try:
        result = validate()
    except (OracleTargetError, ValueError) as error:
        print(
            f"PERSON_B_66_CELL_ORACLE_TARGET_VALIDATION=FAIL {error}", file=sys.stderr
        )
        return 1
    if not args.quiet:
        print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
