"""Build the Person E Phase 6 aggregate-authorization decision package.

Additive and non-executing: this records Person E's cross-role signoff for one
exact run_id. It performs no extraction, inspects no hidden state, and rewrites
no historical or frozen evidence.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from mineocclude.experiments.registry import formatted_json_bytes

PACKAGE = ROOT / "docs/status/person_e_phase6_aggregate_authorization_v0_1"

SCHEMA_ID = "person-e-phase6-aggregate-authorization-v0-1"
RUN_ID = "mineocclude-run-ea6169430d693f8adcd16a23a62c4422"
ROLE = "person_e_operations"
RECORD_DATE = "2026-08-07"

# Person A authorities, pinned by commit and by artifact digest.
PERSON_A_TRANSPORT_COMMIT = "ecdf3178154e594b06d1d4326993754068cae039"
PERSON_A_REQUEST_COMMIT_BASIS = "3384cbfed92f069236d68746f2308ec76f1a4124"
PERSON_A_ARTIFACTS = {
    "authorization_request": {
        "path": (
            "docs/status/person_a_phase6_aggregate_authorization_request_v0_1"
            "/authorization_request.json"
        ),
        "byte_size": 3027,
        "sha256": "345d0e6b109dd6443874dce7f542e35ba9abf24ba1170b1d01ed669ff9b9cca4",
    },
    "durable_destination_record": {
        "path": (
            "docs/status/person_a_phase6_durable_destination_v0_1"
            "/durable_destination_record.json"
        ),
        "byte_size": 2072,
        "sha256": "a9ff37f6576b4407e48f0b89feedcba549b2e89213f90745096705dc8d650b82",
    },
    "preprocessed_frame_manifest": {
        "path": (
            "docs/status/person_a_66_cell_preprocessed_media_v0_2"
            "/preprocessed_frame_manifest.json"
        ),
        "byte_size": 6240221,
        "sha256": "dda2220d1e388253c671f7a7d879987e53d4c0a1a1e815fbc8da6a19356de5a1",
    },
    "transfer_verification_receipt": {
        "path": (
            "docs/status/person_a_phase6_input_transfer_verification_v0_1"
            "/transfer_verification_receipt.json"
        ),
        "byte_size": 2616,
        "sha256": "e423e640c7d43dc21e08b503adf5b4ade595b3f773ee63119f2c11afdb729090",
    },
}

# Person E authorities this decision rests on, all already frozen on this branch.
PERSON_E_EMPIRICAL_VISIBILITY_COMMIT = "fec27d08b4629afa07c7858598e94778dc6e7bef"
PERSON_E_PHASE6_ACCEPTANCE_COMMIT = "5bbe7c7021fe3b1c4c35c78fadfbd92ab51484e8"
E_66_CELL_PACKAGE = "data/handoff_c/person_e_66_cell_empirical_visibility_v0_1"
E_66_CELL_RECORDS = f"{E_66_CELL_PACKAGE}/empirical_visibility_records.jsonl"
E_66_CELL_RECORDS_SHA256 = (
    "fd0ad70ce880645fcda668d23dacc07784c2f8e418a3eceabd9f88ac391e07f9"
)
DETECTOR_IDENTITY_SHA256 = (
    "0cadf618fca1578196bde4982021c38627ccb9c39e46353812e7da3fce6aa125"
)
MARKER_LAYOUT_AUTHORITY_SHA256 = (
    "14a12db4092e05e8c41057df210eec11f07a78f593a149595a12eba45fda82d8"
)

EXPECTED_PAYLOAD_COUNT = 2468
EXPECTED_LAYER_COUNT = 20
EXPECTED_ACTIVATION_ROWS = 49_360

# Frozen Person E state that this authorization must not disturb.
FROZEN_STATE_PRESERVED = {
    "hidden_state_interpretation_authorized": False,
    "phase6_artifacts_immutable": True,
    "phase6_reexecution_required": False,
    "step4_1_contract_complete": False,
    "step4_1_decision_vocabulary_preserved": ["PASS", "FAIL", "INCONCLUSIVE"],
    "step4_1_scientific_execution_performed": False,
    "ten_pilot_accepted_activation_chunk_count": 200,
    "ten_pilot_accepted_activation_row_count": 37_480,
    "ten_pilot_accepted_pilot_count": 10,
    "u4_output_inspected": False,
}

RETENTION_REQUIREMENTS = [
    {
        "path": "/home/sagemaker-user/person-a-phase6-approved-inputs",
        "requirement": (
            "Retain immutable source/input trees used by the accepted extraction "
            "until final Step 4.1 closure and durable Registry v2 receipt "
            "verification."
        ),
    },
    {
        "path": "/home/sagemaker-user/person-a-phase6-approved-outputs",
        "requirement": (
            "Retain all accepted indexes, all 200 chunks, inventories, bounded "
            "audits, logs, and reports without overwrite, relocation, or deletion."
        ),
    },
    {
        "path": (
            "/home/sagemaker-user/person-b-phase6-approved-outputs"
            "/person-b-phase6-v2-positive-control-step6-6"
        ),
        "requirement": (
            "Retain the exact external positive-control report through final "
            "closure; its byte size and SHA-256 remain controlling."
        ),
    },
]

AUTHORIZATION_CONDITIONS = [
    {
        "condition_id": "distinct_scope_from_frozen_ten_pilot_set",
        "requirement": (
            "This authorization covers the 66-cell scope only "
            f"({EXPECTED_PAYLOAD_COUNT} payloads, {EXPECTED_LAYER_COUNT} layers, "
            f"{EXPECTED_ACTIVATION_ROWS} expected activation rows). It is not a "
            "re-extraction of the frozen ten-pilot Phase 6 artifacts, so "
            "person_a_reextraction_authorized remains false for those artifacts "
            "and phase6_artifacts_immutable remains true."
        ),
    },
    {
        "condition_id": "write_only_to_the_approved_fresh_destination",
        "requirement": (
            "All run outputs are written under the approved fresh S3 prefix for "
            "this run_id. No write, overwrite, relocation, or deletion may touch "
            "the retained trees listed in retention_requirements."
        ),
    },
    {
        "condition_id": "extraction_only_no_interpretation",
        "requirement": (
            "Authorizes activation extraction and byte-level provenance only. "
            "Hidden-state interpretation remains unauthorized, and U4 output "
            "remains uninspected, until the separate frozen gates are satisfied."
        ),
    },
    {
        "condition_id": "step4_1_untouched",
        "requirement": (
            "This decision does not advance, close, or alter Step 4.1. The Step "
            "4.1 decision vocabulary including FAIL and every historical Step 4.1 "
            "record remain exactly as frozen."
        ),
    },
    {
        "condition_id": "person_e_downstream_blockers_remain_open",
        "requirement": (
            "Person E's published downstream blockers remain open and are not "
            "waived. They are consequences of activations not yet existing, so "
            "they do not block this extraction."
        ),
    },
]

# Person E blockers that remain open but are downstream of extraction.
NON_BLOCKING_OPEN_ITEMS = [
    "person_b_activation_store_v2_production_consumer_absent",
    "ten_pilot_frame_fold_manifest_absent",
    "production_oracle_target_absent",
    "person_d_readiness_gate_waits_for_person_b",
    "step4_1_result_trust_packages_absent",
]


class AuthorizationError(RuntimeError):
    """Raised when the authorization package cannot be justified."""


def _load_person_e_identities() -> dict[tuple[str, int], dict[str, Any]]:
    """Return Person E's frozen 66-cell empirical-visibility records by identity."""

    records: dict[tuple[str, int], dict[str, Any]] = {}
    path = ROOT / E_66_CELL_RECORDS
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            records[(record["trajectory_id"], record["model_frame_idx"])] = record
    return records


def _load_person_a_records(manifest_path: Path) -> list[dict[str, Any]]:
    payload = manifest_path.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    expected = PERSON_A_ARTIFACTS["preprocessed_frame_manifest"]["sha256"]
    if digest != expected:
        raise AuthorizationError(
            "Person A preprocessed_frame_manifest.json digest mismatch: "
            f"expected {expected}, observed {digest}"
        )
    return json.loads(payload)["records"]


def cross_check_identities(manifest_path: Path) -> dict[str, Any]:
    """Cross-check Person A's transferred payloads against Person E's own frames.

    Person E already measured empirical magenta visibility over an exact 2468
    (trajectory_id, model_frame_idx) identity set. The extraction Person A wants
    to run consumes preprocessed payloads. This confirms they are the same frames
    and that they descend from byte-identical source pixels.
    """

    person_e = _load_person_e_identities()
    person_a_records = _load_person_a_records(manifest_path)
    person_a = {
        (record["trajectory_id"], record["model_frame_idx"]): record
        for record in person_a_records
    }

    if len(person_a_records) != len(person_a):
        raise AuthorizationError("Person A manifest contains duplicate identities")

    raw_matches = canonical_matches = 0
    for identity, e_record in person_e.items():
        a_record = person_a.get(identity)
        if a_record is None:
            continue
        if e_record["source_frame_sha256"] == a_record["source_raw_sha256"]:
            raw_matches += 1
        if (
            e_record["canonical_frame_rgb_sha256"]
            == a_record["source_canonical_pixel_sha256"]
        ):
            canonical_matches += 1

    only_person_a = sorted(person_a.keys() - person_e.keys())
    only_person_e = sorted(person_e.keys() - person_a.keys())

    return {
        "canonical_rgb_pixel_sha256_matches": canonical_matches,
        "canonical_rgb_pixel_sha256_mismatches": len(person_e) - canonical_matches,
        "comparison_fields": {
            "canonical_pixel": {
                "person_a": "source_canonical_pixel_sha256",
                "person_e": "canonical_frame_rgb_sha256",
            },
            "raw_source": {
                "person_a": "source_raw_sha256",
                "person_e": "source_frame_sha256",
            },
        },
        "identity_sets_exactly_equal": not only_person_a and not only_person_e,
        "join_key": ["trajectory_id", "model_frame_idx"],
        "person_a_identity_count": len(person_a),
        "person_a_only_identity_count": len(only_person_a),
        "person_e_identity_count": len(person_e),
        "person_e_only_identity_count": len(only_person_e),
        "person_e_records_path": E_66_CELL_RECORDS,
        "person_e_records_sha256": E_66_CELL_RECORDS_SHA256,
        "raw_source_sha256_matches": raw_matches,
        "raw_source_sha256_mismatches": len(person_e) - raw_matches,
        "schema_id": f"{SCHEMA_ID}-identity-cross-check",
        "schema_version": "1.0",
        "status": (
            "PASS"
            if (
                not only_person_a
                and not only_person_e
                and raw_matches == len(person_e)
                and canonical_matches == len(person_e)
            )
            else "FAIL"
        ),
    }


def _authority_binding() -> dict[str, Any]:
    return {
        "frozen_state_preserved": dict(FROZEN_STATE_PRESERVED),
        "historical_evidence_rewritten": False,
        "person_a_artifacts": {
            name: dict(artifact) for name, artifact in PERSON_A_ARTIFACTS.items()
        },
        "person_a_request_commit_basis": PERSON_A_REQUEST_COMMIT_BASIS,
        "person_a_transport_verification_commit": PERSON_A_TRANSPORT_COMMIT,
        "person_e_detector_identity_sha256": DETECTOR_IDENTITY_SHA256,
        "person_e_empirical_visibility_commit": PERSON_E_EMPIRICAL_VISIBILITY_COMMIT,
        "person_e_empirical_visibility_package": E_66_CELL_PACKAGE,
        "person_e_marker_layout_authority_sha256": MARKER_LAYOUT_AUTHORITY_SHA256,
        "person_e_phase6_acceptance_commit": PERSON_E_PHASE6_ACCEPTANCE_COMMIT,
        "record_date": RECORD_DATE,
        "role": ROLE,
        "run_id": RUN_ID,
        "schema_id": f"{SCHEMA_ID}-authority-binding",
        "schema_version": "1.0",
    }


def _authorization_decision(cross_check: dict[str, Any]) -> dict[str, Any]:
    return {
        "aggregate_authorization_complete": False,
        "authorization_conditions": [dict(item) for item in AUTHORIZATION_CONDITIONS],
        "authorized_scope": {
            "expected_activation_rows": EXPECTED_ACTIVATION_ROWS,
            "expected_layer_count": EXPECTED_LAYER_COUNT,
            "expected_payload_count": EXPECTED_PAYLOAD_COUNT,
            "stored_activation_dtype": "float32",
            "work_authorized": "activation_extraction_and_byte_provenance_only",
        },
        "basis": [
            (
                "Person E Phase 6 is already closed on this branch "
                "(phase6_complete=true, step6_6_complete=true); no Person E "
                "Phase 6 gate is pending on Person A."
            ),
            (
                "Person E's own upstream contribution for this exact 66-cell "
                f"scope is published and frozen at commit "
                f"{PERSON_E_EMPIRICAL_VISIBILITY_COMMIT}, covering all "
                f"{EXPECTED_PAYLOAD_COUNT} requested identities with zero "
                "duplicate, missing, extra, or failed frames."
            ),
            (
                "Person A's transferred payload identity set is exactly equal to "
                "Person E's measured identity set, and every payload descends "
                "from byte-identical raw source frames and byte-identical "
                "canonical RGB pixels (0 mismatches on both)."
            ),
            (
                "The approved destination is a fresh S3 prefix scoped to this "
                "run_id with zero pre-existing objects, so no frozen Person E "
                "or Person A artifact is overwritten, relocated, or deleted."
            ),
            (
                "Every open Person E blocker is downstream of activations "
                "existing; none is a precondition on extraction itself."
            ),
        ],
        "blocker": None,
        "does_not_authorize": [
            "hidden-state interpretation",
            "U4 output inspection",
            "re-extraction or mutation of the frozen ten-pilot Phase 6 artifacts",
            "Step 4.1 advancement, closure, or decision change",
            "any signoff on behalf of person_b_analysis or person_c_data",
        ],
        "historical_evidence_rewritten": False,
        "non_blocking_open_person_e_items": list(NON_BLOCKING_OPEN_ITEMS),
        "person_a_phase6_authorized": True,
        "person_e_operations_signoff": True,
        "phase6_authorized": True,
        "record_date": RECORD_DATE,
        "remaining_required_signers": ["person_b_analysis", "person_c_data"],
        "retention_requirements": [dict(item) for item in RETENTION_REQUIREMENTS],
        "role": ROLE,
        "run_id": RUN_ID,
        "schema_id": f"{SCHEMA_ID}-decision",
        "schema_version": "1.0",
        "self_authorization_forbidden": True,
        "signed_for_this_run_id": True,
        "silent_authorization_forbidden": True,
        "supporting_cross_check_status": cross_check["status"],
    }


def build_documents() -> dict[str, dict[str, Any]]:
    """Build every document in the authorization package."""

    manifest_path = ROOT / "docs/status/person_a_66_cell_preprocessed_media_v0_2"
    manifest_path = manifest_path / "preprocessed_frame_manifest.json"
    if not manifest_path.exists():
        manifest_path = _external_manifest_path()

    cross_check = cross_check_identities(manifest_path)
    if cross_check["status"] != "PASS":
        raise AuthorizationError(
            "identity cross-check did not pass; refusing to publish authorization"
        )

    return {
        "authority_binding.json": _authority_binding(),
        "identity_cross_check.json": cross_check,
        "phase6_authorization_decision.json": _authorization_decision(cross_check),
        "validation_receipt.json": _validation_receipt(cross_check),
    }


def _external_manifest_path() -> Path:
    """Locate Person A's manifest without merging or importing a foreign branch."""

    candidate = ROOT.parent / "MineOcclude"
    manifest = (
        candidate
        / "docs/status/person_a_66_cell_preprocessed_media_v0_2"
        / "preprocessed_frame_manifest.json"
    )
    if not manifest.exists():
        raise AuthorizationError(
            "Person A preprocessed_frame_manifest.json is not reachable; "
            f"expected it under {candidate}"
        )
    return manifest


def _validation_receipt(cross_check: dict[str, Any]) -> dict[str, Any]:
    return {
        "additive_only": True,
        "canonical_json_generated": True,
        "external_artifacts_copied_into_git": False,
        "focused_validation_only": True,
        "foreign_branch_merged": False,
        "frozen_evidence_preserved": True,
        "hidden_state_interpretation_performed": False,
        "identity_cross_check_status": cross_check["status"],
        "person_a_manifest_digest_reproduced": True,
        "record_date": RECORD_DATE,
        "run_id": RUN_ID,
        "schema_id": f"{SCHEMA_ID}-validation-receipt",
        "schema_version": "1.0",
        "scientific_execution_performed": False,
        "status": "PASS",
        "step4_1_records_modified": False,
        "u4_output_inspected": False,
    }


def main() -> None:
    documents = build_documents()
    PACKAGE.mkdir(parents=True, exist_ok=True)
    payloads: dict[str, bytes] = {}
    for name, document in documents.items():
        payload = formatted_json_bytes(document)
        (PACKAGE / name).write_bytes(payload)
        payloads[name] = payload
    inventory = {
        "algorithm": "sha256",
        "file_count": len(payloads),
        "files": {
            name: {
                "byte_size": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
            for name, payload in sorted(payloads.items())
        },
        "inventory_excludes_self": True,
        "run_id": RUN_ID,
        "schema_id": f"{SCHEMA_ID}-sha256-inventory",
        "schema_version": "1.0",
    }
    (PACKAGE / "sha256_inventory.json").write_bytes(formatted_json_bytes(inventory))


if __name__ == "__main__":
    main()
