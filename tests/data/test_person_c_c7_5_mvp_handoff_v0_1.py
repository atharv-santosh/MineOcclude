"""Focused validation for the Person C C7.5 MVP handoff (+ C8.1 / C8.3).

Asserts exactly 66 per-trajectory bundles (ep12601-ep12666), unique identities,
ledger reconciliation (66 accepted / 0 excluded), JSON/Parquet record equality,
condition-count reconciliation to the frozen 66-cell matrix, every declared
checksum traceable to a committed source inventory, no episode payload bytes,
deterministic regeneration, and presence of the C8.3 collection runbook.
"""
import json
import os
import sys

import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import build_person_c_c7_5_mvp_handoff_v0_1 as mod

PKG = os.path.join(ROOT, mod.PKG_REL)
FIRST, LAST = 12601, 12666
SETS = {"core": 48, "nowall": 6, "nosheep": 6, "sentinel": 6}


def loadj(rel):
    with open(os.path.join(PKG, rel), encoding="utf-8") as f:
        return json.load(f)


def bundles():
    d = os.path.join(PKG, "per_trajectory")
    return [json.load(open(os.path.join(d, f), encoding="utf-8"))
            for f in sorted(os.listdir(d)) if f.endswith(".json")]


def test_exactly_66_bundles_ep_range_and_unique_identities():
    d = os.path.join(PKG, "per_trajectory")
    files = [f for f in os.listdir(d) if f.endswith(".json")]
    assert len(files) == 66
    bs = bundles()
    eps = [b["identity"]["episode_id"] for b in bs]
    assert sorted(eps) == list(range(FIRST, LAST + 1))
    for key in ("episode_id", "trajectory_id", "planned_cell_id"):
        vals = [b["identity"][key] for b in bs]
        assert len(set(vals)) == 66, key


def test_every_bundle_has_ten_sections():
    need = {"schema", "identity", "condition", "acceptance", "locations", "artifacts",
            "authorities", "visibility", "qa_summary", "provenance"}
    for b in bundles():
        assert need <= set(b), set(b)
        assert b["schema"]["schema_id"] == mod.SCHEMA_ID
        assert b["schema"]["schema_version"] == "1.0"
        assert b["acceptance"]["accepted"] is True
        assert b["acceptance"]["exclusion_reason_codes"] == []


def test_ledger_reconciles_66_0():
    led = loadj("accepted_excluded_ledger.json")
    assert led["accepted_count"] == 66 and led["excluded_count"] == 0
    assert led["accepted_episode_ids"] == list(range(FIRST, LAST + 1))
    assert led["excluded_episode_ids"] == []


def test_condition_counts_reconcile_frozen_matrix():
    c = loadj("condition_count_table.json")
    assert c["total"] == 66
    assert c["by_set"] == SETS
    assert c["reconciles_to_frozen_matrix"] is True
    assert c["by_layout"] == {f"layout_0{i}": 11 for i in range(1, 7)}


def test_json_parquet_record_and_key_set_equality():
    man = loadj("trajectories_mvp_manifest.json")
    recs = man["records"]
    assert len(recs) == 66
    df = pd.read_parquet(os.path.join(PKG, "trajectories_mvp.parquet"))
    assert len(df) == 66
    assert sorted(df["episode_id"].tolist()) == sorted(r["episode_id"] for r in recs)
    assert set(df["trajectory_id"]) == {r["trajectory_id"] for r in recs}
    assert set(df.columns) >= {"episode_id", "trajectory_id", "planned_cell_id",
                               "control_type", "context_fraction", "seed", "accepted"}


def test_every_checksum_traceable_to_committed_source_inventory():
    # each bundle artifact sha256/byte_size must equal the committed output_inventory
    out = mod.loadj(mod.OUT)["files"]
    idx = {(f["episode_id"], f["relative_path"]): f for f in out}
    for b in bundles():
        ep = b["identity"]["episode_id"]
        for a in b["artifacts"]:
            src = idx[(ep, a["artifact_role"])]
            assert a["sha256"] == src["sha256"]
            assert a["byte_size"] == src["size_bytes"]
            assert a["path_or_uri"] == src["path"]


def test_no_episode_payload_bytes_committed():
    for dp, _, fns in os.walk(PKG):
        for fn in fns:
            assert not fn.endswith(".png"), fn
            assert not fn.endswith(".jsonl"), fn  # payload streams never committed here
            p = os.path.join(dp, fn)
            assert os.path.getsize(p) < 200_000, p  # metadata only


def test_preprocessing_and_frame_map_pending_person_a_not_null():
    for b in bundles():
        pp = b["authorities"]["preprocessing"]
        fm = b["authorities"]["frame_action_state_mapping"]
        assert pp["status"] == "pending_person_a_owner_acknowledgement" and pp["owner"] == "person_a"
        assert fm["status"] == "pending_person_a_owner_acknowledgement"
        assert fm["model_facing_key"] == ["trajectory_id", "model_frame_idx"]
        # C-side raw stream identities are still present + sourced (not discarded)
        assert fm["c_side_raw_stream_identities"]["server_state_sha256"]


def test_phase6_authorization_not_claimed():
    hr = loadj("handoff_receipt.json")
    assert hr["person_c_phase6_input_ready"] is True
    assert hr["phase_6_runtime_authorized"] is False
    assert hr["downstream_a_production_handoff_status"] == "pending_person_a_owner_acknowledgement"
    a = loadj("consumer_handoffs/person_a_handoff_receipt.json")
    rs = a["role_specific"]
    assert rs["downstream_a_production_handoff_status"] == "pending_person_a_owner_acknowledgement"
    assert "person_a_owner_acknowledgement" in rs["downstream_a_production_handoff_required_fields"]
    # never claims phase 6 authorized
    assert "phase_6_runtime_authorized\": true" not in json.dumps(hr).lower()


def test_metadata_handoff_bytes_stay_on_runtime():
    for b in bundles():
        loc = b["locations"]
        assert loc["durable_uri"] is None and loc["s3_uri"] is None
        assert "no_durable_s3_uri_assigned" in loc["external_storage_status"]
        assert loc["runtime_path"]["server"].startswith("C:\\Users\\lollo")
    hr = loadj("handoff_receipt.json")
    assert hr["byte_payload_committed"] is False
    assert hr["durable_s3_assigned"] is False


def test_deterministic_regeneration_json_byte_identical():
    a, _ = mod.generate(out_dir=None)
    b, _ = mod.generate(out_dir=None)
    for k in a:
        if k.endswith(".parquet"):
            continue
        assert a[k] == b[k], k
    # committed JSON matches a fresh generation
    for k, data in a.items():
        if k.endswith(".parquet"):
            continue
        with open(os.path.join(PKG, k), "rb") as f:
            assert f.read() == data, k


def test_fail_closed_on_count_mismatch(monkeypatch):
    real = mod.loadj

    def fake(rel):
        d = real(rel)
        if rel == mod.EPI:
            d = json.loads(json.dumps(d))
            d["episodes"] = d["episodes"][:-1]  # drop one -> 65
        return d
    monkeypatch.setattr(mod, "loadj", fake)
    with pytest.raises(mod.HandoffError):
        mod.generate(out_dir=None)


def test_c8_3_collection_runbook_present_and_covers_stages():
    p = os.path.join(ROOT, "docs/runbooks/collect_trajectory.md")
    assert os.path.exists(p)
    with open(p, encoding="utf-8") as f:
        text = f.read().lower()
    for stage in ("build", "start the server", "reset", "collect", "finalize",
                  "validate", "transfer", "retry", "shut down"):
        assert stage in text, stage
    assert "credential" in text and "secret channel" in text


def test_c8_scope_and_external_blockers_recorded():
    hr = loadj("handoff_receipt.json")
    assert "c7_5_locked_mvp_metadata_handoff" in hr["c8_scope_completed"]
    assert "c8_1_qa_exclusion_closure" in hr["c8_scope_completed"]
    assert "c8_3_collection_runbook" in hr["c8_scope_completed"]
    blockers = hr["external_blockers_out_of_scope"]
    assert set(blockers) == {"c8_2_held_out_u4", "c8_4_second_operator_rehearsal",
                             "c8_5_live_demonstration"}


def test_cross_role_handoff_receipts_present_and_no_downstream_acceptance():
    hd = os.path.join(PKG, "consumer_handoffs")
    files = sorted(f for f in os.listdir(hd) if f.endswith(".json"))
    assert files == [f"person_{r}_handoff_receipt.json" for r in ("a", "b", "d", "e")]
    with open(os.path.join(PKG, "trajectories_mvp_manifest.json"), "rb") as f:
        man_sha = mod.sha256_bytes(f.read())
    with open(os.path.join(PKG, "accepted_excluded_ledger.json"), "rb") as f:
        led_sha = mod.sha256_bytes(f.read())
    for role in ("a", "b", "d", "e"):
        with open(os.path.join(hd, f"person_{role}_handoff_receipt.json"), encoding="utf-8") as f:
            r = json.load(f)
        assert r["consumer_role"] == f"person_{role}" and r["owner"] == "person_c"
        assert r["downstream_acceptance_claimed"] is False
        assert r["ready_for_consumer_validation"] is True
        assert r["person_c_states_ready_for_consumer_validation"] is True
        assert r["manifest_sha256"] == man_sha
        assert r["accepted_excluded_ledger"]["sha256"] == led_sha
        assert r["expected_count_by_consumer"] == 66 and r["accepted_count"] == 66
        assert r["authoritative_c_inputs"] and r["fields_unavailable"]
        # never asserts a downstream owner accepted
        assert "accepted_by_person" not in json.dumps(r).lower()


def test_no_dangling_paths_in_bundles_and_manifest():
    for b in bundles():
        for p in b["locations"]["repository_metadata_paths"]:
            assert os.path.exists(os.path.join(ROOT, p)), p
        for k in ("episode_inventory", "output_inventory", "sha256_inventory"):
            assert os.path.exists(os.path.join(ROOT, b["provenance"][k]["path"]))
        assert os.path.exists(os.path.join(ROOT, b["acceptance"]["acceptance_authority_path"]))
    man = loadj("trajectories_mvp_manifest.json")
    for v in man["source_inventories"].values():
        assert os.path.exists(os.path.join(ROOT, v["path"])), v["path"]


def test_sha256_inventory_covers_all_files_excludes_self():
    inv = loadj("sha256_inventory.json")
    assert inv["inventory_excludes_self"] is True
    on_disk = set()
    for dp, _, fns in os.walk(PKG):
        for fn in fns:
            on_disk.add(os.path.relpath(os.path.join(dp, fn), PKG).replace("\\", "/"))
    assert set(inv["files"]) == on_disk - {"sha256_inventory.json"}
    for rel, h in inv["files"].items():
        with open(os.path.join(PKG, rel), "rb") as f:
            assert mod.sha256_bytes(f.read()) == h, rel


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
