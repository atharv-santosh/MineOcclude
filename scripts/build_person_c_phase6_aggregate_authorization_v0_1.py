"""Build Person C's Phase 6 aggregate runtime authorization for one exact run_id.

This is an additive owner decision.  It re-verifies, byte for byte, the Person C
authorities that Person A bound as its inputs, reads Person A's request and
input-transfer receipt from the exact Git objects, and then records Person C's
affirmative Phase 6 signoff for
``mineocclude-run-ea6169430d693f8adcd16a23a62c4422``.

It rewrites no historical or frozen evidence.  The prior scoped decisions --
including the Step 4.1 single-pilot record and the ten-pilot expansion record,
both of which remain FAIL/false for their own scopes -- stay exactly as they
were committed and are restated here as preserved, not superseded.  It never
executes extraction, never loads a model, and never inspects U4 output.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SCHEMA_ID = "person-c-phase6-aggregate-authorization-v0-1"
PKG_REL = "docs/status/person_c_phase6_aggregate_authorization_v0_1"

ROLE = "person_c_data"
RUN_ID = "mineocclude-run-ea6169430d693f8adcd16a23a62c4422"
DECISION_TIMESTAMP = "2026-08-07T00:00:00Z"

PERSON_C_AUTHORITY_COMMIT = "3846230a4f141a8a55084eeaaa040f9a10cfc408"
PERSON_A_REQUEST_COMMIT = "ecdf3178154e594b06d1d4326993754068cae039"

# Person C artifacts that Person A bound as its declared inputs, plus the
# Person C closure receipts that govern them.  Verified on disk at build and
# validate time; a single byte of drift fails closed.
PERSON_C_BOUND_INPUTS = {
    "docs/status/person_c_66_cell_canonical_media_v0_1/canonical_media_manifest.json":
        "a11762bd9292404b58ddccc062ebcf5115d935d61426fff4cd4474c8def257c9",
    "docs/status/person_c_66_cell_canonical_media_v0_1/c_to_a_media_handoff.json":
        "94c852466167db01a678d0d7d6a3ae6e3211abaef995f95b20f5d182ed599b3e",
    "docs/status/person_c_66_cell_canonical_media_v0_1/c_to_d_media_handoff.json":
        "84b5b927ab41d34d51ebf30f1af9d48cf1b5af9d057518a6ca6338cef7f38a56",
    "docs/status/person_c_66_cell_canonical_media_v0_1/canonical_frame_index.jsonl":
        "745e556578587981c5fe7d96ca873d8744e53e9f1e11b23b931af37dd9499dab",
    "docs/status/person_c_66_cell_canonical_media_v0_1/closure_receipt.json":
        "cc2201d5c3b6d4655612acfb93ce68ee5a7756668ece89cad734f9661f25e2b1",
    "docs/status/person_c_66_cell_capture_authority_v0_1/capture_package_manifest.json":
        "ca6ef6bd0a6ee144731ff3e6f470f767a2c1a82e8b46aef9fb5e458efb814f56",
    "docs/status/person_c_66_cell_capture_authority_v0_1/closure_receipt.json":
        "4169109d4d9fb64462225e2e7731c054f2d7fff1f179e9a2b89e179e9398e09b",
    "docs/status/person_c_66_cell_strict_visibility_v0_1/visibility_join_manifest.json":
        "8e03d6564c3a5d17e6199af258708bd8526842410c78a7f58330df9e0bf960cc",
    "docs/status/person_c_66_cell_strict_visibility_v0_1/c_to_b_oracle_handoff.json":
        "dd5569164d72ba8a25e4efbd74e013819744b7cf10b22ea949e22a13b3a3b33b",
    "docs/status/person_c_66_cell_strict_visibility_v0_1/closure_receipt.json":
        "2d7ba1bb7dd953c3679fcfef0c69c32588b86775c3fb3af86e14deb58e9b6a8a",
    "docs/status/person_c_c7_mvp_handoff_v0_1/handoff_receipt.json":
        "2ea0c6b91c4605c3e8fe393744574cd450c4a3e112f74be0b51a49b7c212b536",
}

# Frozen Person C evidence that this decision preserves without modification.
PRESERVED_FROZEN_EVIDENCE = {
    "docs/status/person_c_phase4_step4_1_registry_v2_handoff_v0_1/selected_pilot_acceptance.json":
        "6e663b1c5a4e4e269a680a0b5c142da6f4f0d22ecf46092cdc8c81c0ce1ad8a9",
    "docs/status/person_c_phase4_step4_1_registry_v2_handoff_v0_1/validation_receipt.json":
        "0a726fb3c915eb37a5821fed786870c0f79a4b0581c25f85c070b21b67e3cffc",
    "docs/status/person_c_phase6_ten_pilot_expansion_acceptance_v0_1/expansion_acceptance_decision.json":
        "8862cdfb329767c458f8744d3f1d4bcc479e2b2ed2fb2b30e37101070ece5bfe",
    "docs/status/person_c_phase6_ten_pilot_expansion_acceptance_v0_1/validation_receipt.json":
        "1c78b2c6a50374f92a913b22a8fd3152696976f01a2495c78e765041c0a6edcc",
}

# Person A records read from the exact Git commit named in the request.
PERSON_A_RECORDS = {
    "docs/status/person_a_phase6_aggregate_authorization_request_v0_1/authorization_request.json":
        "345d0e6b109dd6443874dce7f542e35ba9abf24ba1170b1d01ed669ff9b9cca4",
    "docs/status/person_a_phase6_input_transfer_verification_v0_1/transfer_verification_receipt.json":
        "e423e640c7d43dc21e08b503adf5b4ade595b3f773ee63119f2c11afdb729090",
    "docs/status/person_a_66_cell_preprocessed_media_v0_2/phase6_precondition_receipt.json":
        "d4b246e6d20727d528c97becb62c04b9bcb8d0eaabb55d905cd5004d3dc41fc4",
    "docs/status/person_a_66_cell_preprocessed_media_v0_2/preprocessed_frame_manifest.json":
        "dda2220d1e388253c671f7a7d879987e53d4c0a1a1e815fbc8da6a19356de5a1",
}

PERSON_C_OWNED_CONDITIONS = [
    "person_c_accepted_66_cell_manifest_bound",
    "person_c_strict_visibility_authority_bound",
    "model_input_source_media_at_frozen_source_resolution",
]

EXPECTED_TRAJECTORY_COUNT = 66
EXPECTED_FRAME_KEY_COUNT = 2468


class AuthorizationError(RuntimeError):
    """Raised when any precondition for this authorization fails."""


def fail(message: str) -> None:
    raise AuthorizationError(message)


def canon(document) -> bytes:
    return (
        json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_local(relative: str) -> bytes:
    path = os.path.join(ROOT, relative)
    if not os.path.isfile(path):
        fail(f"required Person C authority is missing: {relative}")
    with open(path, "rb") as handle:
        return handle.read()


def read_git_object(commit: str, relative: str) -> bytes:
    try:
        return subprocess.check_output(
            ["git", "show", f"{commit}:{relative}"],
            cwd=ROOT,
            stderr=subprocess.PIPE,
        )
    except subprocess.CalledProcessError:
        fail(f"cannot read {relative} at exact commit {commit}")


def verify_pinned(source: str, expected: dict, reader) -> dict:
    """Verify every pinned digest and return the per-file verification rows."""
    rows = {}
    for relative, digest in sorted(expected.items()):
        data = reader(relative)
        actual = sha256_bytes(data)
        if actual != digest:
            fail(
                f"{source} byte drift: {relative} expected {digest}, found {actual}"
            )
        rows[relative] = {"byte_size": len(data), "sha256": actual}
    return rows


def verify_person_a_state() -> dict:
    """Check the Person A claims this authorization actually depends on."""
    request = json.loads(
        read_git_object(
            PERSON_A_REQUEST_COMMIT,
            "docs/status/person_a_phase6_aggregate_authorization_request_v0_1/"
            "authorization_request.json",
        )
    )
    transfer = json.loads(
        read_git_object(
            PERSON_A_REQUEST_COMMIT,
            "docs/status/person_a_phase6_input_transfer_verification_v0_1/"
            "transfer_verification_receipt.json",
        )
    )
    precondition = json.loads(
        read_git_object(
            PERSON_A_REQUEST_COMMIT,
            "docs/status/person_a_66_cell_preprocessed_media_v0_2/"
            "phase6_precondition_receipt.json",
        )
    )

    if request["run_id"] != RUN_ID:
        fail(f"Person A request names {request['run_id']}, not {RUN_ID}")
    if transfer["run_id"] != RUN_ID:
        fail(f"Person A transfer receipt names {transfer['run_id']}, not {RUN_ID}")
    if ROLE not in request["required_signers"]:
        fail(f"Person A request does not list {ROLE} as a required signer")
    if request["signer_status"][ROLE]["branch_head_checked"] != PERSON_C_AUTHORITY_COMMIT:
        fail(
            "Person A checked a different Person C branch head than the authority "
            f"this decision is published from ({PERSON_C_AUTHORITY_COMMIT})"
        )
    if transfer["gpu_extraction_started"] is not False:
        fail("Person A reports extraction already started; this decision is prospective only")
    if transfer["historical_evidence_rewritten"] is not False:
        fail("Person A reports historical evidence rewritten")
    if transfer["source_manifest"]["sha256"] != PERSON_A_RECORDS[
        "docs/status/person_a_66_cell_preprocessed_media_v0_2/preprocessed_frame_manifest.json"
    ]:
        fail("Person A transfer receipt does not bind the pinned preprocessed frame manifest")

    verification = transfer["verification"]
    for field in ("missing_count", "hash_mismatch_count", "size_mismatch_count",
                  "duplicate_output_paths_in_manifest", "extra_files_on_disk_not_in_manifest"):
        if verification[field] != 0:
            fail(f"Person A transfer verification reports {field}={verification[field]}")
    if verification["pass"] is not True:
        fail("Person A transfer verification did not pass")
    if verification["valid_count"] != EXPECTED_FRAME_KEY_COUNT:
        fail(
            f"Person A transferred {verification['valid_count']} payloads, "
            f"expected {EXPECTED_FRAME_KEY_COUNT}"
        )

    conditions = {row["condition"]: row for row in precondition["contract_conditions"]}
    for name in PERSON_C_OWNED_CONDITIONS:
        row = conditions.get(name)
        if row is None:
            fail(f"Person A precondition receipt is missing Person C condition {name}")
        if row["owner"] != ROLE:
            fail(f"condition {name} is owned by {row['owner']}, not {ROLE}")
        if row["satisfied"] is not True:
            fail(f"Person C-owned condition {name} is not satisfied")

    return {
        "person_a_commit": PERSON_A_REQUEST_COMMIT,
        "person_a_reported_person_c_head": request["signer_status"][ROLE]["branch_head_checked"],
        "person_a_self_authorization_forbidden": request["self_authorization_forbidden"],
        "person_c_owned_contract_conditions_all_satisfied": True,
        "transferred_payload_count": verification["valid_count"],
        "transfer_hash_mismatch_count": verification["hash_mismatch_count"],
        "transfer_missing_count": verification["missing_count"],
        "transfer_duplicate_count": verification["duplicate_output_paths_in_manifest"],
        "extraction_not_started_at_decision_time": True,
    }


def verify_person_c_scope() -> dict:
    """Re-read Person C's own closure receipts and confirm the input scope."""
    capture = json.loads(
        read_local("docs/status/person_c_66_cell_capture_authority_v0_1/closure_receipt.json")
    )
    media = json.loads(
        read_local("docs/status/person_c_66_cell_canonical_media_v0_1/closure_receipt.json")
    )
    visibility = json.loads(
        read_local("docs/status/person_c_66_cell_strict_visibility_v0_1/closure_receipt.json")
    )
    mvp = json.loads(read_local("docs/status/person_c_c7_mvp_handoff_v0_1/handoff_receipt.json"))

    if capture["accepted_trajectory_count"] != EXPECTED_TRAJECTORY_COUNT:
        fail("Person C capture authority does not cover exactly 66 accepted trajectories")
    if capture["capture_packages_complete"] is not True:
        fail("Person C capture packages are not complete")
    if media["canonical_frame_count"] != EXPECTED_FRAME_KEY_COUNT:
        fail("Person C canonical media does not cover exactly 2468 frames")
    if media["canonical_missing_count"] != 0 or media["canonical_duplicate_count"] != 0:
        fail("Person C canonical media has missing or duplicate frames")
    if media["A_SOURCE_CONTRACT_COMPATIBLE"] is not True:
        fail("Person C canonical media is not declared compatible with the Person A source contract")
    if media["READY_FOR_A_PREPROCESSED_FRAME_MATERIALIZATION"] is not True:
        fail("Person C has not declared the canonical media ready for Person A materialization")
    if visibility["VISIBILITY_JOIN_COMPLETE"] is not True:
        fail("Person C strict visibility join is not complete")
    if visibility["frame_key_count"] != EXPECTED_FRAME_KEY_COUNT:
        fail("Person C visibility join does not cover exactly 2468 frame keys")
    if mvp["person_c_phase6_input_ready"] is not True:
        fail("Person C has not declared its Phase 6 inputs ready")

    return {
        "accepted_trajectory_count": capture["accepted_trajectory_count"],
        "canonical_frame_count": media["canonical_frame_count"],
        "excluded_trajectory_count": capture["excluded_trajectory_count"],
        "person_c_phase6_input_ready": mvp["person_c_phase6_input_ready"],
        "prior_status_before_this_decision": mvp["phase_6_runtime_authorization_status"],
        "visibility_frame_key_count": visibility["frame_key_count"],
    }


def generate(out_dir):
    bound_inputs = verify_pinned("person_c bound input", PERSON_C_BOUND_INPUTS, read_local)
    preserved = verify_pinned("preserved frozen evidence", PRESERVED_FROZEN_EVIDENCE, read_local)
    person_a_records = verify_pinned(
        "person_a record",
        PERSON_A_RECORDS,
        lambda relative: read_git_object(PERSON_A_REQUEST_COMMIT, relative),
    )
    person_a_state = verify_person_a_state()
    person_c_scope = verify_person_c_scope()

    decision = {
        "schema_id": f"{SCHEMA_ID}-decision",
        "schema_version": "1.0",
        "owner": ROLE,
        "role": ROLE,
        "run_id": RUN_ID,
        "decision": "AUTHORIZE_PERSON_A_PHASE6_EXTRACTION_FOR_THIS_EXACT_RUN_ID",
        "decision_timestamp": DECISION_TIMESTAMP,
        "person_a_phase6_authorized": True,
        "person_c_phase6_signoff": True,
        "signed_for_this_run_id": True,
        "person_c_blocker_present": False,
        "blocker": None,
        "owner_authority_commit": PERSON_C_AUTHORITY_COMMIT,
        "person_c_branch": "role/person-c-data",
        "person_a_request_commit": PERSON_A_REQUEST_COMMIT,
        "aggregate_authorization_complete": False,
        "aggregate_authorization_note": (
            "This document supplies only the person_c_data signature. Person A's "
            "aggregate_phase6_runtime_authorized remains false until person_b_analysis "
            "and person_e_operations publish their own affirmative decisions for this "
            "exact run_id."
        ),
        "reason": (
            "Person C owns the 66-cell capture packages, the canonical 640x360 source "
            "media, and the strict visibility join that Person A consumes. Every Person C "
            "artifact Person A bound as an input re-verifies byte-exact at Person C "
            "authority commit "
            f"{PERSON_C_AUTHORITY_COMMIT}, all three person_c_data-owned contract "
            "conditions in Person A's precondition receipt are satisfied, and Person A's "
            "input-transfer receipt verifies 2468/2468 payloads with zero missing, zero "
            "duplicate, and zero hash mismatches against the pinned preprocessed frame "
            "manifest. Person C's remaining false flags are scoped 'not yet granted' "
            "states awaiting exactly this coordinated review, not adverse findings. No "
            "real Person C blocker to executing this run_id exists."
        ),
        "run_id_scope": "single_exact_run_id_only",
        "reauthorization_required_for_any_other_run_id": True,
    }

    scope = {
        "schema_id": f"{SCHEMA_ID}-scope-and-limitations",
        "schema_version": "1.0",
        "run_id": RUN_ID,
        "authorized_scope": [
            "Person A MineWorld activation extraction over the exact 2468 model-facing "
            "payloads already transferred and verified for this run_id.",
            "Storage of the resulting activation rows at the declared float32 dtype "
            "across the declared 20 layers.",
        ],
        "authorized_input_identity": {
            "canonical_frame_count": EXPECTED_FRAME_KEY_COUNT,
            "person_c_authority_commit": PERSON_C_AUTHORITY_COMMIT,
            "trajectory_count": EXPECTED_TRAJECTORY_COUNT,
        },
        "not_authorized_by_this_document": [
            "Any run_id other than " + RUN_ID + ".",
            "Re-capture, re-canonicalization, or any modification of Person C source media.",
            "Registry v2 acceptance of the resulting activation output artifacts; "
            "post-execution output acceptance remains a separate Person C decision.",
            "U4 output inspection or hidden-state interpretation.",
            "Any claim that depends on a terminal reveal window: the 66-cell capture "
            "remains U4-reveal-ineligible and supplemental capture is still required.",
            "Person B's coordinate-frame co-signature, which Person C does not sign.",
            "The person_b_analysis and person_e_operations signatures required to make "
            "Person A's aggregate authorization true.",
        ],
        "carried_forward_scientific_limitations": {
            "CURRENT_66_CELL_U4_REVEAL_ELIGIBLE": False,
            "U4_SUPPLEMENTAL_CAPTURE_REQUIRED": True,
            "hidden_state_interpretation_authorized": False,
            "oracle_ineligible_no_object_control_count": 6,
            "u4_output_inspected": False,
        },
    }

    authority_binding = {
        "schema_id": f"{SCHEMA_ID}-authority-binding",
        "schema_version": "1.0",
        "run_id": RUN_ID,
        "person_c_authority_commit": PERSON_C_AUTHORITY_COMMIT,
        "person_c_branch": "role/person-c-data",
        "person_c_bound_inputs": bound_inputs,
        "person_a": {
            "commit": PERSON_A_REQUEST_COMMIT,
            "records": person_a_records,
            "source_read_policy": "exact_git_commit_object",
        },
        "person_a_verified_state": person_a_state,
        "person_c_verified_scope": person_c_scope,
        "foreign_branch_merged": False,
        "foreign_branch_modified": False,
    }

    preserved_evidence = {
        "schema_id": f"{SCHEMA_ID}-preserved-frozen-evidence",
        "schema_version": "1.0",
        "additive_only": True,
        "historical_evidence_rewritten": False,
        "frozen_decision_modified": False,
        "preserved_records": preserved,
        "step_4_1_status": "FAIL",
        "step_4_1_status_preserved": True,
        "step_4_1_note": (
            "The Step 4.1 verdict remains FAIL and is not reopened, reinterpreted, or "
            "superseded by this document. The Step 4.1 registry-v2 handoff records "
            "person_a_phase6_authorized=false scoped to the single layout_00_ep9403 pilot "
            "for Steps 6.1-6.6; that scoped record stays false and byte-unchanged."
        ),
        "scoped_false_flags_left_unchanged": [
            {
                "field": "person_a_phase6_authorized",
                "path": "docs/status/person_c_phase4_step4_1_registry_v2_handoff_v0_1/"
                        "selected_pilot_acceptance.json",
                "scope": "single_pilot_steps_6_1_through_6_6",
                "value": False,
            },
            {
                "field": "person_a_expansion_execution_authorized",
                "path": "docs/status/person_c_phase6_ten_pilot_expansion_acceptance_v0_1/"
                        "expansion_acceptance_decision.json",
                "scope": "exact_phase6_ten_pilot_expansion_inputs_for_steps_6_1_through_6_5",
                "value": False,
            },
        ],
        "relationship_to_this_decision": (
            "Those two records govern the single-pilot and ten-pilot tracks and remain "
            "false for their own scopes. This decision governs a different, disjoint "
            "scope: the 66-cell production track at run_id " + RUN_ID + ". It grants "
            "no authority inside the pilot or expansion scopes."
        ),
    }

    validation = {
        "schema_id": f"{SCHEMA_ID}-validation-receipt",
        "schema_version": "1.0",
        "run_id": RUN_ID,
        "status": "PASS",
        "all_person_a_records_read_from_exact_git_objects": True,
        "all_person_a_records_hash_verified": True,
        "all_person_c_bound_inputs_hash_verified": True,
        "all_preserved_frozen_records_hash_verified": True,
        "person_c_owned_contract_conditions_satisfied": PERSON_C_OWNED_CONDITIONS,
        "person_c_owned_contract_condition_failures": 0,
        "run_id_named_explicitly": True,
        "person_a_phase6_authorized": True,
        "person_c_phase6_signoff": True,
        "person_c_blocker_present": False,
        "accepted_trajectory_count": EXPECTED_TRAJECTORY_COUNT,
        "canonical_frame_count": EXPECTED_FRAME_KEY_COUNT,
        "transferred_payload_count": person_a_state["transferred_payload_count"],
        "transfer_hash_mismatch_count": person_a_state["transfer_hash_mismatch_count"],
        "transfer_missing_count": person_a_state["transfer_missing_count"],
        "activation_extraction_performed_by_person_c": False,
        "model_loaded_by_person_c": False,
        "scientific_execution_performed": False,
        "u4_output_inspected": False,
        "historical_evidence_rewritten": False,
        "step_4_1_status_preserved_as_fail": True,
    }

    files = {
        "authorization_decision.json": canon(decision),
        "scope_and_limitations.json": canon(scope),
        "authority_binding.json": canon(authority_binding),
        "preserved_frozen_evidence.json": canon(preserved_evidence),
        "validation_receipt.json": canon(validation),
    }

    inventory = {
        "schema_id": f"{SCHEMA_ID}-sha256-inventory",
        "schema_version": "1.0",
        "file_count": len(files) + 1,
        "files": {name: sha256_bytes(data) for name, data in sorted(files.items())},
        "inventory_excludes_self": True,
    }
    files["sha256_inventory.json"] = canon(inventory)

    if out_dir is not None:
        os.makedirs(out_dir, exist_ok=True)
        for name, data in files.items():
            with open(os.path.join(out_dir, name), "wb") as handle:
                handle.write(data)
    return files


def validate(package_dir: str) -> None:
    expected = generate(out_dir=None)
    present = set(os.listdir(package_dir)) if os.path.isdir(package_dir) else set()
    if present != set(expected):
        fail(
            f"authorization package file set mismatch: expected {sorted(expected)}, "
            f"found {sorted(present)}"
        )
    for name, data in expected.items():
        with open(os.path.join(package_dir, name), "rb") as handle:
            if handle.read() != data:
                fail(f"authorization package byte drift: {name}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("build", "validate"))
    parser.add_argument("--out-dir", default=os.path.join(ROOT, PKG_REL))
    args = parser.parse_args()
    try:
        if args.mode == "build":
            files = generate(args.out_dir)
            print(f"BUILD OK: {len(files)} artifacts; {ROLE} authorized {RUN_ID}")
        else:
            validate(args.out_dir)
            print(f"VALIDATE OK: {ROLE} Phase 6 authorization for {RUN_ID}")
    except AuthorizationError as exc:
        print(f"FAIL-CLOSED: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
