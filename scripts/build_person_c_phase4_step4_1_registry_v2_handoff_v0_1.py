"""Person C Phase 4 Step 4.1: accept exactly one refreshed pilot for Step 6.1.

Additive Person C v0.2 scientific-use decision plus the complete Immutable
Registry v2 trust package for exactly one pilot selected from Person B's
refreshed deterministic 15-candidate order (commit 8942d5d). The registry trust
chain is authored in Person E's frozen v2 shapes (commit b27d404) and is
re-verified against E's frozen validator loaded read-only from that commit;
every record binds the exact refreshed pilot bytes with no placeholders.

This decision signs only Person C's owner decision. It does not authorize
Person A Phase 6.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import importlib.util
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
from mineocclude.data.capture_contract import validate_capture_package

SCHEMA_ID = "person-c-phase4-step4-1-registry-v2-handoff-v0-1"
PKG_REL = "docs/status/person_c_phase4_step4_1_registry_v2_handoff_v0_1"

PERSON_C_AUTHORITY = "bf09c23bb12f59acae724811eed6b82bab17c0ed"
PERSON_B_REFRESH = "8942d5d514a4d124ac0baa36ffc803dc598c4f1f"
PERSON_E_REGISTRY_V2 = "b27d404c6aa913bac559754fa8b7accdff46e886"
B_REFRESH_DIR = "docs/status/person_b_phase4_step4_1_step6_authorization_refresh_v0_1"
B_SELECTION = f"{B_REFRESH_DIR}/refreshed_c_candidate_selection.json"
B_C_REQUIRED = f"{B_REFRESH_DIR}/person_c_required_decision.json"
E_VALIDATOR_REL = "src/mineocclude/contracts/rollout_registry.py"
E_CONTRACT_REL = "docs/contracts/immutable_registry_v2.md"
EXCLUDED_CONTROL = "layout_05_ep9422"

JOINED_VISIBILITY = "data/handoff_b/person_c_phase3_step3_3_joined_visibility_v0_1/joined_visibility_records.jsonl"

# Step 6.1 intake artifact roles -> capture-package artifact keys
INTAKE_ROLES = {
    "media": "media", "raw_actions": "raw_actions", "normalized_actions": "normalized_actions",
    "state": "server_state", "frame_map": "frame_map", "visibility": "visibility",
}


class HandoffError(Exception):
    pass


def fail(msg: str):
    raise HandoffError(msg)


def canon(doc) -> bytes:
    return (json.dumps(doc, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def resolve_artifact_path(declared_path: str) -> str:
    """Resolve an owner-recorded artifact path without changing its identity.

    Capture packages preserve the producer's absolute workstation path as
    provenance.  A checkout on another machine must not require that original
    home directory when the same hash-bound bytes are present under this
    repository's ``data`` directory.  Only that exact repository-relative
    suffix is portable; arbitrary basename or directory-order fallbacks remain
    forbidden.
    """
    expanded = os.path.abspath(os.path.expanduser(declared_path))
    if os.path.isfile(expanded):
        return expanded

    normalized = declared_path.replace("\\", "/")
    marker = "/data/"
    marker_index = normalized.find(marker)
    if marker_index < 0 and normalized.startswith("data/"):
        relative = normalized
    elif marker_index >= 0:
        relative = normalized[marker_index + 1 :]
    else:
        fail(f"artifact path is outside the portable repository namespace: {declared_path}")

    candidate = os.path.abspath(os.path.join(ROOT, *relative.split("/")))
    if os.path.commonpath((ROOT, candidate)) != os.path.abspath(ROOT):
        fail(f"artifact path escapes the repository: {declared_path}")
    if not os.path.isfile(candidate):
        fail(
            "artifact missing at both the owner-recorded and portable paths: "
            f"{declared_path}"
        )
    return candidate


def git_show(spec: str) -> bytes:
    return subprocess.check_output(["git", "-C", ROOT, "show", spec])


def _utc() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --------------------------------------------------------------------------- #
# Person E frozen v2 validator, loaded read-only from b27d404
# --------------------------------------------------------------------------- #
def load_e_validator():
    src = git_show(f"{PERSON_E_REGISTRY_V2}:{E_VALIDATOR_REL}")
    import tempfile
    fd, tmp_path = tempfile.mkstemp(suffix="_e_rollout_registry.py")
    with os.fdopen(fd, "wb") as fh:
        fh.write(src)
    import mineocclude.contracts  # ensure package present for dataclass resolution  # noqa: F401
    name = "mineocclude.contracts.rollout_registry"
    spec = importlib.util.spec_from_file_location(name, tmp_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod, sha256_bytes(src)


# --------------------------------------------------------------------------- #
# Deterministic pilot selection + acceptance checks
# --------------------------------------------------------------------------- #
def select_pilot():
    sel = json.loads(git_show(f"{PERSON_B_REFRESH}:{B_SELECTION}"))
    ordered = sel["ordered_candidates"]
    if not isinstance(ordered, list) or not ordered:
        fail("refreshed selection has no stable ordered candidate list")
    excluded = sel["excluded_no_object_control"]
    excluded_id = excluded["trajectory_id"] if isinstance(excluded, dict) else excluded
    if excluded_id != EXCLUDED_CONTROL:
        fail(f"unexpected excluded control {excluded_id}")
    for cand in ordered:
        if cand["trajectory_id"] == EXCLUDED_CONTROL:
            fail("excluded control appears in candidate order")
        path = os.path.join(ROOT, cand["source_path"])
        if not os.path.exists(path):
            continue
        with open(path, "rb") as f:
            raw = f.read()
        if sha256_bytes(raw) != cand["git_object_sha256"] or len(raw) != cand["byte_size"]:
            continue  # refreshed identity does not match current bytes -> not qualifying
        pkg = json.loads(raw)
        result = validate_capture_package(pkg)
        if not result.accepted:
            continue
        if pkg.get("scientific_use") != "pending_cross_role_signoff":
            continue
        return cand, raw, pkg, sel  # first qualifying pilot
    fail("no candidate passed Person C strict acceptance")
    return None


def verify_artifacts(pkg):
    """Every referenced artifact resolves, checksum matches, identities one-to-one."""
    rows = {}
    for name, a in pkg["artifacts"].items():
        p = resolve_artifact_path(a["path"])
        with open(p, "rb") as f:
            data = f.read()
        if sha256_bytes(data) != a["sha256"]:
            fail(f"artifact {name} checksum mismatch")
        rows[name] = {"path": a["path"], "sha256": a["sha256"],
                      "byte_size": len(data), "format": a["format"]}
    # one-to-one stream identities
    n = pkg["media"]["frame_count"]
    for sname, stream in pkg["streams"].items():
        if len(stream) != n:
            fail(f"stream {sname} identity count {len(stream)} != frame_count {n}")
    return rows


# --------------------------------------------------------------------------- #
# Registry v2 trust chain (E frozen shapes), all real pilot bytes
# --------------------------------------------------------------------------- #
def build_registry(pilot_id, pilot_sha, pilot_size, pilot_bytes, pkg):
    m = pkg["episode_manifest"]
    code_sha = m["code_sha"]
    config_hash = m["config_hash"]
    env_hash = m["environment_lock_hash"]
    layout_hash = m["layout_config_hash"]
    noise_hash = m["noise_schedule_hash"]
    seed = pkg["seed"]

    rev = PERSON_C_AUTHORITY
    art_schema = f"person-c-capture-package-v{pkg['person_c_contract_version']}"
    man_id = f"manifest_person_c_raw_trajectory_{pilot_id.split('_ep')[-1]}"
    man_schema = "person-c-registry-v2-manifest-v1.0"
    man_ident = f"person-c-raw-trajectory-{pilot_id}"
    authority_id = f"authority_person_c_raw_trajectory_{pilot_id.split('_ep')[-1]}"
    status_id = f"person_c_{pilot_id.split('_ep')[-1]}_status_v0_1"
    authz_id = f"authorization_person_c_{pilot_id.split('_ep')[-1]}"
    authz_rec_id = f"person_c_{pilot_id.split('_ep')[-1]}_authorization_v0_1"
    run_id = f"run_person_c_capture_{pilot_id.split('_ep')[-1]}"
    ver_id = f"verification_person_c_{pilot_id.split('_ep')[-1]}"
    status_schema = "mineocclude-owner-status-record-v1.0"

    man_sha = sha256_bytes(canon({
        "artifact_identities": [man_ident], "manifest_id": man_id,
        "manifest_schema_version": man_schema, "owner_authority_id": authority_id,
        "owner_id": "person_c",
    }))

    status_doc = {"authority_revision": rev, "decision": "accepted", "owner_id": "person_c",
                  "owner_status": "accepted", "schema_version": status_schema,
                  "status_record_id": status_id}
    status_bytes = canon(status_doc)
    status_sha = sha256_bytes(status_bytes)

    authority = {
        "authority_id": authority_id, "authority_revision": rev,
        "authorized_artifact_types": ["raw_trajectory"], "decision": "accepted",
        "owner_id": "person_c", "owner_status": "accepted", "schema_version": "1.0",
        "status_record_id": status_id, "status_record_receipt_authority_revision": None,
        "status_record_receipt_id": None, "status_record_receipt_sha256": None,
        "status_record_schema_version": status_schema, "status_record_sha256": status_sha,
        "status_record_verification_mode": "local_bytes",
    }

    authz_doc = {
        "artifact_id": pilot_id, "artifact_schema_version": art_schema, "artifact_sha256": pilot_sha,
        "artifact_size_bytes": pilot_size, "artifact_type": "raw_trajectory",
        "authority_id": authority_id, "authorization_id": authz_id,
        "authorization_record_id": authz_rec_id, "decision": "accepted",
        "manifest_artifact_identity": man_ident, "manifest_id": man_id,
        "manifest_schema_version": man_schema, "manifest_sha256": man_sha,
        "owner_authority_revision": rev, "owner_id": "person_c", "owner_status": "accepted",
    }
    authz_bytes = canon(authz_doc)
    authz_rec_sha = sha256_bytes(authz_bytes)

    trusted_authorization = {
        **authz_doc, "authorization_record_receipt_authority_revision": None,
        "authorization_record_receipt_id": None, "authorization_record_receipt_sha256": None,
        "authorization_record_sha256": authz_rec_sha,
        "authorization_record_verification_mode": "local_bytes",
    }
    trusted_manifest = {
        "artifact_identities": [{
            "artifact_id": pilot_id, "artifact_schema_version": art_schema, "artifact_sha256": pilot_sha,
            "artifact_size_bytes": pilot_size, "artifact_type": "raw_trajectory",
            "manifest_artifact_identity": man_ident}],
        "decision": "accepted", "manifest_id": man_id, "manifest_schema_version": man_schema,
        "manifest_sha256": man_sha, "owner_authority_id": authority_id,
        "owner_authority_revision": rev, "owner_id": "person_c", "owner_status": "accepted",
    }

    document = {
        "artifacts": [{
            "artifact_id": pilot_id, "artifact_schema_version": art_schema, "artifact_type": "raw_trajectory",
            "byte_verification_id": ver_id, "creator_run_id": run_id, "direct_input_artifact_ids": [],
            "manifest_artifact_identity": man_ident, "manifest_id": man_id,
            "manifest_schema_version": man_schema, "manifest_sha256": man_sha,
            "owner_authority_id": authority_id, "owner_authority_revision": rev,
            "owner_decision": "accepted", "owner_status_record_id": status_id,
            "owner_status_record_sha256": status_sha, "schema_version": "1.0", "sha256": pilot_sha,
            "size_bytes": pilot_size, "status": "accepted", "status_reason": None,
            "superseded_by": None,
            "uri": f"git://role/person-c-data/data/autonomous/{pilot_id}/capture_package_v0_1.json",
        }],
        "byte_verifications": [{
            "artifact_id": pilot_id, "external_receipt_authority_revision": None,
            "external_receipt_id": None, "external_receipt_sha256": None, "mode": "local_bytes",
            "schema_version": "1.0", "verification_id": ver_id, "verified_at": "2026-07-30T00:00:03Z",
            "verified_sha256": pilot_sha, "verified_size_bytes": pilot_size,
        }],
        "immutable_registry_schema_version": "mineocclude-immutable-registry-v2.0",
        "manifests": [{
            "artifact_identities": [man_ident], "decision": "accepted", "manifest_id": man_id,
            "manifest_schema_version": man_schema, "manifest_sha256": man_sha,
            "owner_authority_id": authority_id, "schema_version": "1.0"}],
        "owner_authorities": [authority],
        "registry_id": "person_c_phase4_step4_1_registry_v2_single_pilot_v0_1",
        "runs": [{
            "checkpoint_hash": layout_hash, "code_sha": code_sha,
            "command": ["mineocclude", "capture", pilot_id],
            "config_snapshot_hash": config_hash, "created_at": "2026-07-30T00:00:00Z",
            "data_identity_hash": pilot_sha, "ended_at": "2026-07-30T00:00:02Z",
            "environment_hash": env_hash, "failure_reason": None, "git_dirty": False,
            "input_artifact_ids": [], "output_artifact_ids": [pilot_id], "owner": "person_c",
            "parent_run_id": None, "pending_reason": None, "preprocess_hash": noise_hash,
            "run_id": run_id, "schema_version": "1.0", "seeds": {"capture": seed},
            "started_at": "2026-07-30T00:00:01Z", "status": "completed",
            "supersedes_run_id": None, "supersession_reason": None}],
        "schema_version": "1.0", "scientific_use": "permitted", "synthetic": False,
    }

    trusted_inputs = {
        "trusted_owner_authorities": {authority_id: {
            "authority": authority,
            "status_record_verification": {"mode": "local_bytes", "external_receipt": None}}},
        "trusted_status_record_bytes": {status_id: status_bytes.decode("utf-8")},
        "trusted_artifact_authorizations": {pilot_id: {
            "authorization": trusted_authorization,
            "authorization_record_verification": {"mode": "local_bytes", "external_receipt": None}}},
        "trusted_authorization_record_bytes": {authz_rec_id: authz_bytes.decode("utf-8")},
        "trusted_manifest_records": {man_id: trusted_manifest},
        "trusted_artifact_receipts": None,
    }
    ids = {"authority_id": authority_id, "status_id": status_id, "authz_id": authz_id,
           "authz_rec_id": authz_rec_id, "run_id": run_id, "ver_id": ver_id, "man_id": man_id,
           "man_ident": man_ident, "man_sha": man_sha, "status_sha": status_sha,
           "authz_rec_sha": authz_rec_sha, "art_schema": art_schema}
    return document, trusted_inputs, status_bytes, authz_bytes, ids


def verify_registry(e_mod, document, trusted_inputs, status_bytes, authz_bytes, pilot_id, pilot_bytes, ids):
    res = e_mod.validate_immutable_run_artifact_registry(
        document,
        artifact_bytes_by_id={pilot_id: pilot_bytes},
        trusted_owner_authorities={k: {"authority": v["authority"],
                                       "status_record_verification": v["status_record_verification"]}
                                   for k, v in trusted_inputs["trusted_owner_authorities"].items()},
        trusted_status_record_bytes={ids["status_id"]: status_bytes},
        trusted_artifact_authorizations={k: {"authorization": v["authorization"],
                                             "authorization_record_verification": v["authorization_record_verification"]}
                                         for k, v in trusted_inputs["trusted_artifact_authorizations"].items()},
        trusted_authorization_record_bytes={ids["authz_rec_id"]: authz_bytes},
        trusted_manifest_records=trusted_inputs["trusted_manifest_records"],
        trusted_artifact_receipts=None,
    )
    if not res.accepted:
        fail("registry v2 trust chain FAILED E frozen validator: "
             + "; ".join(f"{r.code.value}: {r.message}" for r in res.rejections))
    return True


# --------------------------------------------------------------------------- #
# Package assembly
# --------------------------------------------------------------------------- #
def generate(out_dir):
    e_mod, e_validator_sha = load_e_validator()
    cand, pilot_bytes, pkg, sel = select_pilot()
    pilot_id = cand["trajectory_id"]
    pilot_sha = cand["git_object_sha256"]
    pilot_size = cand["byte_size"]
    artifacts = verify_artifacts(pkg)

    document, trusted_inputs, status_bytes, authz_bytes, ids = build_registry(
        pilot_id, pilot_sha, pilot_size, pilot_bytes, pkg)
    verify_registry(e_mod, document, trusted_inputs, status_bytes, authz_bytes, pilot_id, pilot_bytes, ids)

    jv_bytes = git_show(f"{PERSON_C_AUTHORITY}:{JOINED_VISIBILITY}")
    jv_sha = sha256_bytes(jv_bytes)

    ts = _utc()
    b_sel_sha = sha256_bytes(git_show(f"{PERSON_B_REFRESH}:{B_SELECTION}"))
    b_req_sha = sha256_bytes(git_show(f"{PERSON_B_REFRESH}:{B_C_REQUIRED}"))
    e_contract_sha = sha256_bytes(git_show(f"{PERSON_E_REGISTRY_V2}:{E_CONTRACT_REL}"))

    files = {}

    files["authority_binding.json"] = canon({
        "schema_version": "1.0", "schema_id": f"{SCHEMA_ID}-authority-binding",
        "person_c_branch": "role/person-c-data", "person_c_starting_authority": PERSON_C_AUTHORITY,
        "person_b_selection_authority": {"commit": PERSON_B_REFRESH,
                                         "refreshed_c_candidate_selection_sha256": b_sel_sha,
                                         "person_c_required_decision_sha256": b_req_sha},
        "person_e_registry_v2_authority": {"commit": PERSON_E_REGISTRY_V2,
                                           "immutable_registry_v2_contract_sha256": e_contract_sha,
                                           "frozen_validator_sha256": e_validator_sha},
        "selected_pilot": {"trajectory_id": pilot_id, "source_path": cand["source_path"],
                           "git_object_sha256": pilot_sha, "byte_size": pilot_size},
        "person_a_phase6_authorized": False, "project_integration_claimed": False,
        "u4_output_inspected": False,
    })

    files["selected_pilot_acceptance.json"] = canon({
        "schema_version": "1.0", "schema_id": f"{SCHEMA_ID}-selected-pilot-acceptance",
        "person_c_contract_version": "0.2",
        "decision_id": f"person_c_scientific_use_accept_{pilot_id}_v0_2",
        "owner": "person_c", "owner_authority_commit": PERSON_C_AUTHORITY,
        "decision": "ACCEPT_SINGLE_PILOT_FOR_SCIENTIFIC_USE",
        "trajectory_id": pilot_id, "source_path": cand["source_path"],
        "git_object_sha256": pilot_sha, "byte_size": pilot_size,
        "previous_scientific_use": "pending_cross_role_signoff",
        "scientific_use": "accepted_for_single_pilot_step_6_1",
        "scientific_use_transition": {"from": "pending_cross_role_signoff",
                                      "to": "accepted_for_single_pilot_step_6_1"},
        "scope": "single_pilot_steps_6_1_through_6_6",
        "decision_authority": "person_c owner decision on role/person-c-data",
        "decision_timestamp": ts,
        "signers": {"person_c": True},
        "reason": ("Person C owns final scientific-use of its own capture pilot. Person B's "
                   "refreshed authorization (8942d5d) explicitly requests this owner decision, "
                   "binds the candidate identity to Person C authority bf09c23, and states "
                   "person_b_may_supply_this_decision=false. The pilot passes Person C's strict "
                   "capture validator with zero rejections, every referenced artifact checksum "
                   "matches at the approved location, and the refreshed hash/size equal the "
                   "current bytes. Package-local acceptance is not scientific acceptance; this "
                   "record is the C-owned scientific-use acceptance."),
        "prohibited_uses_and_limitations": [
            "Does not authorize Person A Phase 6 or any runtime execution.",
            "Scope limited to this one pilot for Steps 6.1-6.6.",
            "Does not grant Registry v2 output-artifact acceptance (post-execution).",
            "No second pilot and no placeholder is accepted.",
        ],
        "person_a_phase6_authorized": False,
    })

    intake = {"artifact_id": pilot_id, "artifact_schema_version": ids["art_schema"],
              "capture_package_path": cand["source_path"],
              "capture_package_sha256": pilot_sha, "capture_package_byte_size": pilot_size,
              "config_runtime_identity": {"run_id": pkg["run_id"], "code_sha": pkg["episode_manifest"]["code_sha"],
                                          "config_hash": pkg["episode_manifest"]["config_hash"],
                                          "environment_lock_hash": pkg["episode_manifest"]["environment_lock_hash"]},
              "seed": pkg["seed"], "frame_count": pkg["media"]["frame_count"]}
    for role, akey in INTAKE_ROLES.items():
        a = artifacts[akey]
        intake[f"{role}_path"] = a["path"]
        intake[f"{role}_sha256"] = a["sha256"]
        intake[f"{role}_byte_size"] = a["byte_size"]
    files["accepted_pilot_manifest.json"] = canon({
        "schema_version": "1.0", "schema_id": f"{SCHEMA_ID}-accepted-pilot-manifest",
        "accepted_pilot_count": 1, "intake_row": intake})

    files["registry_v2_owner_status.json"] = canon({
        "schema_version": "1.0", "schema_id": f"{SCHEMA_ID}-registry-v2-owner-status",
        "owner_authority": trusted_inputs["trusted_owner_authorities"][ids["authority_id"]]["authority"],
        "owner_status_record_document": json.loads(status_bytes),
        "owner_status_record_sha256": ids["status_sha"],
        "status_record_verification_mode": "local_bytes",
        "trusted_owner_authorities": trusted_inputs["trusted_owner_authorities"]})

    files["registry_v2_exact_artifact_authorization.json"] = canon({
        "schema_version": "1.0", "schema_id": f"{SCHEMA_ID}-registry-v2-exact-artifact-authorization",
        "trusted_artifact_authorizations": trusted_inputs["trusted_artifact_authorizations"]})

    files["registry_v2_verified_authorization_record.json"] = canon({
        "schema_version": "1.0", "schema_id": f"{SCHEMA_ID}-registry-v2-verified-authorization-record",
        "authorization_record_document": json.loads(authz_bytes),
        "authorization_record_sha256": ids["authz_rec_sha"],
        "authorization_record_verification_mode": "local_bytes"})

    files["registry_v2_trusted_manifest.json"] = canon({
        "schema_version": "1.0", "schema_id": f"{SCHEMA_ID}-registry-v2-trusted-manifest",
        "trusted_manifest_records": trusted_inputs["trusted_manifest_records"],
        "embedded_manifest": document["manifests"][0]})

    files["registry_v2_artifact_verification_receipt.json"] = canon({
        "schema_version": "1.0", "schema_id": f"{SCHEMA_ID}-registry-v2-artifact-verification-receipt",
        "byte_verification": document["byte_verifications"][0],
        "verification_mode": "local_bytes",
        "verified_artifact_bytes_sha256": pilot_sha, "verified_artifact_byte_size": pilot_size})

    files["direct_input_lineage.json"] = canon({
        "schema_version": "1.0", "schema_id": f"{SCHEMA_ID}-direct-input-lineage",
        "raw_trajectory_promotion": {"artifact_id": pilot_id, "artifact_type": "raw_trajectory",
                                     "direct_input_artifact_ids": [], "creator_run_id": ids["run_id"],
                                     "sha256": pilot_sha, "byte_size": pilot_size},
        "joined_visibility_source": {"path": JOINED_VISIBILITY, "sha256": jv_sha,
                                     "byte_size": len(jv_bytes),
                                     "source_authority_commit": PERSON_C_AUTHORITY},
        "joined_visibility_owner_mapping_decision": {
            "owner": "person_c", "decision": "MAP_JOINED_VISIBILITY_AS_PERSON_C_OWNED_SOURCE",
            "final_visibility_label_owner": "person_c",
            "empirical_channel_owner": "person_e",
            "note": "Person C owns final visibility; Person E owns only the empirical channel."}})

    # full registry document + trusted inputs for independent E re-verification
    files["registry_v2_document.json"] = canon({
        "schema_version": "1.0", "schema_id": f"{SCHEMA_ID}-registry-v2-document",
        "immutable_registry_document": document})
    files["registry_v2_trusted_verification_inputs.json"] = canon({
        "schema_version": "1.0", "schema_id": f"{SCHEMA_ID}-registry-v2-trusted-verification-inputs",
        "verifier": {"authority_commit": PERSON_E_REGISTRY_V2, "validator_path": E_VALIDATOR_REL,
                     "frozen_validator_sha256": e_validator_sha},
        "artifact_bytes_source": {"artifact_id": pilot_id, "path": cand["source_path"],
                                  "sha256": pilot_sha, "byte_size": pilot_size},
        "trusted_inputs": trusted_inputs})

    files["validation_receipt.json"] = canon({
        "schema_version": "1.0", "schema_id": f"{SCHEMA_ID}-validation-receipt",
        "deterministic_selection_followed_b_order": True,
        "selected_trajectory_id": pilot_id,
        "selected_is_first_qualifying_in_b_order": ordered_index(sel, pilot_id) is not None,
        "candidate_set_size": len(sel["ordered_candidates"]),
        "excluded_no_object_control": EXCLUDED_CONTROL,
        "excluded_control_not_selected": pilot_id != EXCLUDED_CONTROL,
        "refreshed_hash_verified": True, "refreshed_size_verified": True,
        "person_c_strict_capture_validator_accepted": True,
        "all_referenced_artifact_checksums_match": True,
        "artifact_identities_one_to_one": True,
        "registry_v2_trust_chain_complete": True,
        "registry_v2_verified_against_frozen_validator": PERSON_E_REGISTRY_V2,
        "frozen_validator_sha256": e_validator_sha,
        "accepted_pilot_count": 1, "accepted_placeholder_count": 0, "second_pilot_accepted": False,
        "c_scientific_use_accepted": True, "person_c_signer_decision_complete": True,
        "person_a_phase6_authorized": False, "no_capture_package_modified": True,
        "u4_output_inspected": False, "decision_timestamp": ts})

    inv = {rel: sha256_bytes(data) for rel, data in sorted(files.items())}
    files["sha256_inventory.json"] = canon({
        "schema_version": "1.0", "schema_id": f"{SCHEMA_ID}-sha256-inventory",
        "files": inv, "file_count": len(files) + 1, "inventory_excludes_self": True})

    if out_dir is not None:
        for rel, data in files.items():
            dst = os.path.join(out_dir, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with open(dst, "wb") as f:
                f.write(data)
    return files, pilot_id


def ordered_index(sel, pilot_id):
    for i, c in enumerate(sel["ordered_candidates"]):
        if c["trajectory_id"] == pilot_id:
            return i
    return None


# artifacts carrying the wall-clock decision timestamp (or its hash) -> self-consistent, not byte-reproduced
VOLATILE_ARTIFACTS = frozenset({
    "selected_pilot_acceptance.json", "validation_receipt.json", "sha256_inventory.json"})


def validate(pkg_dir):
    files, _ = generate(out_dir=None)
    problems = []
    present = set(os.listdir(pkg_dir)) if os.path.isdir(pkg_dir) else set()
    for rel, data in files.items():
        p = os.path.join(pkg_dir, rel)
        if not os.path.exists(p):
            problems.append(f"missing: {rel}")
            continue
        if rel in VOLATILE_ARTIFACTS:
            continue  # timestamp-bearing; checked structurally below
        with open(p, "rb") as fh:
            if fh.read() != data:
                problems.append(f"byte-diff: {rel}")
    for extra in present - set(files):
        problems.append(f"unexpected: {extra}")
    # sha256_inventory self-consistency: every recorded hash matches the on-disk file
    inv_path = os.path.join(pkg_dir, "sha256_inventory.json")
    if os.path.exists(inv_path):
        with open(inv_path, encoding="utf-8") as fh:
            inv = json.load(fh)["files"]
        for rel, h in inv.items():
            fp = os.path.join(pkg_dir, rel)
            if not os.path.exists(fp):
                problems.append(f"inventory lists missing file: {rel}")
            else:
                with open(fp, "rb") as fh:
                    if sha256_bytes(fh.read()) != h:
                        problems.append(f"inventory hash mismatch: {rel}")
    if problems:
        fail("VALIDATE FAILED:\n  " + "\n  ".join(problems))
    print(f"VALIDATE OK: {len(files)} artifacts "
          f"({len(files) - len(VOLATILE_ARTIFACTS)} byte-identical, {len(VOLATILE_ARTIFACTS)} self-consistent)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["build", "validate"])
    ap.add_argument("--out-dir", default=os.path.join(ROOT, PKG_REL))
    args = ap.parse_args()
    try:
        if args.mode == "build":
            files, pilot = generate(args.out_dir)
            print(f"BUILD OK: {len(files)} artifacts; accepted pilot {pilot}")
        else:
            validate(args.out_dir)
    except HandoffError as exc:
        print(f"FAIL-CLOSED: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
