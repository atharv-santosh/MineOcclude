#!/usr/bin/env python3
"""Fail-closed validator for the Person B 66-cell pre-activation package.

The validator rebuilds every published artifact from the bound Person C and
Person A authorities and requires byte-for-byte agreement with the published
package.  It writes nothing, reads no activation bytes, and executes no
scientific metric.
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

from mineocclude.analysis.manifests import (  # noqa: E402
    canonical_json_bytes,
    validate_sealed_artifact,
)
from mineocclude.analysis.preactivation_66_cell_v0_1 import (  # noqa: E402
    ORACLE_STAGE_BLOCKED,
    PREACTIVATION_PACKAGE_DIRECTORY,
    PreactivationError,
    require,
)

BUILDER_PATH = ROOT / "scripts" / "build_person_b_66_cell_preactivation_v0_1.py"
PACKAGE = ROOT / PREACTIVATION_PACKAGE_DIRECTORY

EXPECTED_ARTIFACT_TYPES = {
    "successor_authority_decision.json": (
        "person_b_66_cell_successor_authority_decision"
    ),
    "row_universe_receipt.json": "person_b_66_cell_row_universe_receipt",
    "fold_manifest.json": "person_b_66_cell_fold_manifest",
    "fold_leakage_audit.json": "person_b_66_cell_fold_leakage_audit",
    "oracle_target_preflight.json": "person_b_66_cell_oracle_target_preflight",
    "u4_heldout_partition.json": "person_b_66_cell_u4_heldout_partition",
    "b_to_c_u4_selection_receipt.json": "person_b_to_person_c_u4_selection_receipt",
    "storage_dtype_review.json": "person_b_storage_dtype_review",
    "b_to_a_handoff.json": "person_b_to_person_a_66_cell_handoff",
    "b_to_d_handoff.json": "person_b_to_person_d_66_cell_handoff",
    "post_activation_analysis_preflight.json": (
        "person_b_66_cell_post_activation_preflight"
    ),
}


def _load_builder():
    spec = importlib.util.spec_from_file_location(
        "person_b_66_cell_preactivation_builder", BUILDER_PATH
    )
    module = importlib.util.module_from_spec(spec)
    if spec.loader is None:  # pragma: no cover - defensive
        raise PreactivationError("Could not load the pre-activation builder.")
    spec.loader.exec_module(module)
    return module


def _published(name: str) -> dict:
    path = PACKAGE / name
    require(path.is_file(), f"missing published artifact: {name}")
    return json.loads(path.read_text(encoding="utf-8"))


def validate() -> dict[str, object]:
    builder = _load_builder()

    code_sha = builder.derive_preactivation_code_sha(ROOT)
    c_manifest = builder.load_person_c_accepted_manifest(repository_root=ROOT)
    a_package = builder.load_person_a_frame_map_package(repository_root=ROOT)
    universe = builder.build_row_universe(c_manifest, a_package)

    receipt = builder.build_row_universe_receipt(universe, code_sha=code_sha)
    fold_manifest = builder.build_66_cell_fold_manifest(universe, code_sha=code_sha)
    leakage = builder.audit_fold_leakage(fold_manifest, universe, code_sha=code_sha)
    oracle = builder.assess_oracle_target_inputs(
        universe, code_sha=code_sha, repository_root=ROOT
    )
    partition = builder.build_u4_heldout_partition(universe, code_sha=code_sha)
    u4_receipt = builder.build_b_to_c_u4_receipt(partition, universe, code_sha)
    dtype_review = builder.build_storage_dtype_review(code_sha)
    decision = builder.build_successor_decision(code_sha)
    b_to_a = builder.build_b_to_a_handoff(
        receipt, fold_manifest, leakage, oracle, partition, dtype_review, code_sha
    )
    b_to_d = builder.build_b_to_d_handoff(
        receipt, fold_manifest, oracle, dtype_review, code_sha
    )
    preflight = builder.build_post_activation_preflight(
        receipt, fold_manifest, oracle, code_sha
    )

    rebuilt = {
        builder.SUCCESSOR_DECISION: decision,
        builder.ROW_UNIVERSE_RECEIPT: receipt,
        builder.FOLD_MANIFEST: fold_manifest,
        builder.FOLD_LEAKAGE_AUDIT: leakage,
        builder.ORACLE_PREFLIGHT: oracle,
        builder.U4_PARTITION: partition,
        builder.B_TO_C_U4_RECEIPT: u4_receipt,
        builder.STORAGE_DTYPE_REVIEW: dtype_review,
        builder.B_TO_A_HANDOFF: b_to_a,
        builder.B_TO_D_HANDOFF: b_to_d,
        builder.POST_ACTIVATION_PREFLIGHT: preflight,
    }

    file_hashes: dict[str, str] = {}
    for name in builder.ORDERED_FILES:
        published = _published(name)
        validate_sealed_artifact(published, expected_type=EXPECTED_ARTIFACT_TYPES[name])
        require(
            canonical_json_bytes(published) == canonical_json_bytes(rebuilt[name]),
            f"published {name} does not match its rebuilt evidence",
        )
        file_hashes[name] = hashlib.sha256((PACKAGE / name).read_bytes()).hexdigest()

    inventory = _published(builder.SHA256_INVENTORY)
    require(
        inventory["file_count"] == len(builder.ORDERED_FILES),
        "inventory file_count is wrong",
    )
    for item in inventory["files"]:
        name = item["path"].rsplit("/", 1)[-1]
        require(name in file_hashes, f"inventory names an unknown file: {name}")
        require(
            item["sha256"] == file_hashes[name],
            f"inventory SHA-256 mismatch for {name}",
        )

    require(leakage["leakage_audit_pass"] is True, "fold leakage audit did not pass")
    require(
        oracle["stage_status"] == ORACLE_STAGE_BLOCKED,
        "oracle stage status changed without a new decision record",
    )
    require(
        decision["frozen_decisions_not_reopened"]["step_4_1_decision"] == "FAIL",
        "the frozen Step 4.1 FAIL decision was reopened",
    )
    require(
        dtype_review["chosen_stored_activation_dtype"] == "float32"
        and dtype_review["chosen_analysis_arithmetic_dtype"] == "float64",
        "storage dtype review changed without a new decision record",
    )

    return {
        "validated": True,
        "code_sha": code_sha,
        "model_frame_key_count": receipt["model_frame_key_count"],
        "admitted_analysis_row_count": receipt["admitted_analysis_row_count"],
        "excluded_analysis_row_count": receipt["excluded_analysis_row_count"],
        "fold_manifest_sha256": file_hashes[builder.FOLD_MANIFEST],
        "fold_leakage_audit_pass": leakage["leakage_audit_pass"],
        "oracle_stage_status": oracle["stage_status"],
        "b_to_a_handoff_sha256": file_hashes[builder.B_TO_A_HANDOFF],
        "b_to_d_handoff_sha256": file_hashes[builder.B_TO_D_HANDOFF],
        "storage_dtype_review_sha256": file_hashes[builder.STORAGE_DTYPE_REVIEW],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()
    try:
        result = validate()
    except (PreactivationError, ValueError) as error:
        print(f"PERSON_B_66_CELL_PREACTIVATION_VALIDATION=FAIL {error}", file=sys.stderr)
        return 1
    if not args.quiet:
        print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
