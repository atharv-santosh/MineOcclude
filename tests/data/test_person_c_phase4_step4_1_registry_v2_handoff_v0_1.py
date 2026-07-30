"""Focused handoff validation for Person C Phase 4 Step 4.1 single-pilot signoff.

Proves exactly one pilot is accepted from Person B's refreshed 15-candidate
order, the excluded no-object control stays excluded, every referenced byte and
checksum matches, the complete Registry v2 trust chain re-validates against
Person E's frozen validator (b27d404), no placeholder or second pilot exists,
no Person A Phase 6 authorization was created, no existing capture package was
modified, and no U4 output was inspected.
"""
import json
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "src"))
import build_person_c_phase4_step4_1_registry_v2_handoff_v0_1 as mod

PKG = os.path.join(ROOT, mod.PKG_REL)
PILOT = "layout_00_ep9403"
EXCLUDED = "layout_05_ep9422"


def loadj(name):
    with open(os.path.join(PKG, name), encoding="utf-8") as f:
        return json.load(f)


def test_exactly_one_pilot_accepted_no_second_no_placeholder():
    apm = loadj("accepted_pilot_manifest.json")
    assert apm["accepted_pilot_count"] == 1
    vr = loadj("validation_receipt.json")
    assert vr["accepted_pilot_count"] == 1
    assert vr["second_pilot_accepted"] is False
    assert vr["accepted_placeholder_count"] == 0


def test_pilot_in_refreshed_15_set_and_first_qualifying_in_b_order():
    sel = json.loads(subprocess.check_output(
        ["git", "-C", ROOT, "show", f"{mod.PERSON_B_REFRESH}:{mod.B_SELECTION}"]))
    order = [c["trajectory_id"] for c in sel["ordered_candidates"]]
    assert len(order) == 15 and PILOT in order
    assert order[0] == PILOT  # first qualifying == first in B's order
    vr = loadj("validation_receipt.json")
    assert vr["selected_trajectory_id"] == PILOT
    assert vr["deterministic_selection_followed_b_order"] is True


def test_excluded_control_never_selected():
    sel = json.loads(subprocess.check_output(
        ["git", "-C", ROOT, "show", f"{mod.PERSON_B_REFRESH}:{mod.B_SELECTION}"]))
    order = [c["trajectory_id"] for c in sel["ordered_candidates"]]
    assert EXCLUDED not in order
    assert loadj("selected_pilot_acceptance.json")["trajectory_id"] != EXCLUDED
    assert loadj("validation_receipt.json")["excluded_control_not_selected"] is True


def test_refreshed_hash_and_size_match_current_bytes():
    acc = loadj("selected_pilot_acceptance.json")
    with open(os.path.join(ROOT, acc["source_path"]), "rb") as f:
        raw = f.read()
    assert mod.sha256_bytes(raw) == acc["git_object_sha256"]
    assert len(raw) == acc["byte_size"]


def test_all_referenced_artifact_bytes_and_checksums_match():
    intake = loadj("accepted_pilot_manifest.json")["intake_row"]
    # capture package
    with open(os.path.join(ROOT, intake["capture_package_path"]), "rb") as f:
        assert mod.sha256_bytes(f.read()) == intake["capture_package_sha256"]
    for role in ("media", "raw_actions", "normalized_actions", "state", "frame_map", "visibility"):
        p = os.path.expanduser(intake[f"{role}_path"])
        with open(p, "rb") as f:
            data = f.read()
        assert mod.sha256_bytes(data) == intake[f"{role}_sha256"]
        assert len(data) == intake[f"{role}_byte_size"]


def test_registry_v2_trust_chain_revalidates_against_frozen_e_validator():
    e_mod, e_sha = mod.load_e_validator()
    doc = loadj("registry_v2_document.json")["immutable_registry_document"]
    tv = loadj("registry_v2_trusted_verification_inputs.json")
    assert tv["verifier"]["frozen_validator_sha256"] == e_sha
    ti = tv["trusted_inputs"]
    src = tv["artifact_bytes_source"]
    with open(os.path.join(ROOT, src["path"]), "rb") as f:
        pilot_bytes = f.read()
    status_id = next(iter(ti["trusted_status_record_bytes"]))
    authz_rec_id = next(iter(ti["trusted_authorization_record_bytes"]))
    res = e_mod.validate_immutable_run_artifact_registry(
        doc,
        artifact_bytes_by_id={src["artifact_id"]: pilot_bytes},
        trusted_owner_authorities=ti["trusted_owner_authorities"],
        trusted_status_record_bytes={status_id: ti["trusted_status_record_bytes"][status_id].encode("utf-8")},
        trusted_artifact_authorizations=ti["trusted_artifact_authorizations"],
        trusted_authorization_record_bytes={authz_rec_id: ti["trusted_authorization_record_bytes"][authz_rec_id].encode("utf-8")},
        trusted_manifest_records=ti["trusted_manifest_records"],
        trusted_artifact_receipts=None,
    )
    assert res.accepted, [r.code.value for r in res.rejections]


def test_trust_chain_binds_exact_pilot_bytes_no_placeholder():
    doc = loadj("registry_v2_document.json")["immutable_registry_document"]
    art = doc["artifacts"][0]
    acc = loadj("selected_pilot_acceptance.json")
    assert art["artifact_id"] == PILOT
    assert art["sha256"] == acc["git_object_sha256"]
    assert art["size_bytes"] == acc["byte_size"]
    assert art["status"] == "accepted" and art["owner_authority_id"].startswith("authority_person_c")
    # byte verification is local_bytes over the exact pilot bytes
    bv = doc["byte_verifications"][0]
    assert bv["mode"] == "local_bytes" and bv["verified_sha256"] == acc["git_object_sha256"]


def test_c_scientific_use_accepted_transition_and_owner_only_signer():
    acc = loadj("selected_pilot_acceptance.json")
    assert acc["decision"] == "ACCEPT_SINGLE_PILOT_FOR_SCIENTIFIC_USE"
    assert acc["previous_scientific_use"] == "pending_cross_role_signoff"
    assert acc["scientific_use"] == "accepted_for_single_pilot_step_6_1"
    assert acc["scope"] == "single_pilot_steps_6_1_through_6_6"
    assert acc["owner"] == "person_c" and acc["owner_authority_commit"] == mod.PERSON_C_AUTHORITY
    assert acc["signers"] == {"person_c": True}  # only Person C signs
    assert acc["person_c_contract_version"] == "0.2"


def test_no_person_a_phase6_authorization_created():
    for name in ("authority_binding.json", "selected_pilot_acceptance.json", "validation_receipt.json"):
        assert loadj(name).get("person_a_phase6_authorized") is False
    # no artifact grants runtime execution
    blob = json.dumps([loadj(n) for n in os.listdir(PKG) if n.endswith(".json")])
    assert "person_a_phase6_authorized\": true" not in blob.lower()


def test_no_existing_capture_package_modified():
    acc = loadj("selected_pilot_acceptance.json")
    committed = subprocess.check_output(
        ["git", "-C", ROOT, "show", f"HEAD:{acc['source_path']}"])
    with open(os.path.join(ROOT, acc["source_path"]), "rb") as f:
        assert f.read() == committed  # pilot capture package byte-identical to HEAD


def test_no_u4_inspected_and_deterministic_formatting():
    for name in os.listdir(PKG):
        with open(os.path.join(PKG, name), "rb") as f:
            raw = f.read()
        assert raw[:3] != b"\xef\xbb\xbf" and raw.endswith(b"\n")
        obj = json.loads(raw)
        assert raw == (json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode()
        assert obj.get("schema_version") == "1.0"
        assert "u4" not in json.dumps(obj).lower() or obj.get("u4_output_inspected") is False
    assert loadj("validation_receipt.json")["u4_output_inspected"] is False


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
