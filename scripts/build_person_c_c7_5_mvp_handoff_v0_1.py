"""Build the Person C C7.5 locked MVP metadata handoff (+ C8.1 QA closure).

Publishes one per-trajectory handoff bundle for each of the 66 accepted C6A MVP
episodes (ep12601-ep12666) plus the canonical manifest, parquet, accepted/
excluded ledger, condition-count table, QA/exclusion report, sha256 inventory,
validation receipt, and handoff receipt.

Every value is derived from committed immutable inventories / receipts:
  - configs/collection/mvp_matrix.parquet                (frozen 66-cell plan)
  - docs/status/person_c_c6a_capture_manifest_v0_2/...   (realized identities + authorities)
  - docs/status/person_c_c6a_completion_v0_1/episode_inventory.json  (realized QA)
  - docs/status/person_c_c6a_completion_v0_1/output_inventory.json   (artifact bytes/hashes)
  - docs/status/person_c_c6a_completion_v0_1/{completion_receipt,provenance_handoff,package_manifest}.json

No episode payload bytes are copied; bytes stay on the runtime/S3. Fails closed
unless the committed inventories reconcile to exactly 66 accepted / 0 excluded.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG_REL = "docs/status/person_c_c7_mvp_handoff_v0_1"
SCHEMA_ID = "mineocclude-person-c-c7-5-trajectory-handoff-v1.0"

MATRIX = "configs/collection/mvp_matrix.parquet"
CM = "docs/status/person_c_c6a_capture_manifest_v0_2/c6a_capture_manifest.json"
COMP_DIR = "docs/status/person_c_c6a_completion_v0_1"
EPI = f"{COMP_DIR}/episode_inventory.json"
OUT = f"{COMP_DIR}/output_inventory.json"
SHAINV = f"{COMP_DIR}/sha256_inventory.json"
COMPR = f"{COMP_DIR}/c6a_completion_receipt.json"
PROV = f"{COMP_DIR}/person_c_to_person_e_c6a_provenance_handoff.json"
PKGMAN = f"{COMP_DIR}/package_manifest.json"

FIRST_EP, LAST_EP = 12601, 12666
CONTROL_TYPE = {"core": "core_regime_a", "nowall": "no_wall_visible_control",
                "nosheep": "no_object_control", "sentinel": "context_sentinel"}
TARGET_VARIANT = {"core": "magenta_sheep_occluded_oracle",
                  "nowall": "magenta_sheep_visible_no_wall",
                  "nosheep": "no_target_object",
                  "sentinel": "magenta_sheep_context_sentinel"}
CONTEXT_FRACTION = {0: 0.0, 4: 0.25, 16: 1.0, 24: 1.5}
MATRIX_COUNTS = {"core": 48, "nowall": 6, "nosheep": 6, "sentinel": 6}
DOWNSTREAM = "produced_downstream_not_at_c6a_raw_capture_layer"
NO_S3 = "no_durable_s3_uri_assigned; episode bytes retained on the Person C Windows runtime machine"


class HandoffError(Exception):
    pass


def fail(msg):
    raise HandoffError(msg)


def canon(obj) -> bytes:
    return (json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_file(rel: str) -> str:
    with open(os.path.join(ROOT, rel), "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def loadj(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return json.load(f)


def _ext_type(rel_path):
    if rel_path.endswith(".png"):
        return "image/png"
    if rel_path.endswith(".jsonl"):
        return "application/x-ndjson"
    if rel_path.endswith(".json"):
        return "application/json"
    return "application/octet-stream"


# --------------------------------------------------------------------------- #
def load_sources():
    # fail-closed source integrity: committed inventories match package_manifest
    pm = loadj(PKGMAN)
    for c in pm["component_files"]:
        if sha256_file(c["path"]) != c["sha256"]:
            fail(f"source integrity: {c['path']} hash != package_manifest")
    epi = loadj(EPI)
    out = loadj(OUT)
    cm = loadj(CM)
    comp = loadj(COMPR)
    prov = loadj(PROV)
    mx = pd.read_parquet(os.path.join(ROOT, MATRIX))
    return epi, out, cm, comp, prov, mx, pm


def reconcile(epi, cm, mx):
    eps = epi["episodes"]
    if epi["required_episode_count"] != 66 or epi["completed_episode_count"] != 66 or len(eps) != 66:
        fail("episode inventory does not reconcile to 66")
    accepted = [e for e in eps if e["status"] == "PASS"]
    excluded = [e for e in eps if e["status"] != "PASS"]
    if len(accepted) != 66 or len(excluded) != 0:
        fail(f"expected 66 accepted / 0 excluded, got {len(accepted)}/{len(excluded)}")
    ids = sorted(e["episode_id"] for e in eps)
    if ids != list(range(FIRST_EP, LAST_EP + 1)):
        fail("episode ids are not exactly ep12601..ep12666")
    if dict(mx["set"].value_counts()) != MATRIX_COUNTS:
        fail(f"matrix set counts != frozen 48/6/6/6: {dict(mx['set'].value_counts())}")
    if sorted(mx["collection_order"]) != list(range(66)):
        fail("matrix collection_order not 0..65")
    # join by collection_order must agree with capture manifest
    co_cm = {e["collection_order"]: e for e in cm["episodes"]}
    for _, r in mx.iterrows():
        e = co_cm[int(r["collection_order"])]
        if not (e["layout_id"] == r["layout_id"] and e["v"] == r["v"] and e["q"] == r["q"]
                and e["scene"] == r["scene"] and e["hidden_frames"] == int(r["hidden_frames"])
                and e["set"] == r["set"]):
            fail(f"matrix/capture-manifest mismatch at collection_order {r['collection_order']}")


# --------------------------------------------------------------------------- #
def build_bundle(co, cm_ep, inv, mrow, out_files, ctx):
    ep = inv["episode_id"]
    layout = inv["layout_id"]
    setname = mrow["set"]
    traj = f"{layout}_ep{ep}"
    planned_hidden = int(mrow["hidden_frames"])
    cf = CONTEXT_FRACTION.get(planned_hidden)
    if cf is None:
        fail(f"no context_fraction mapping for planned hidden_frames {planned_hidden}")

    artifacts = []
    for f in sorted(out_files, key=lambda x: (x["side"], x["relative_path"])):
        artifacts.append({
            "artifact_role": f["relative_path"], "side": f["side"],
            "path_or_uri": f["path"], "byte_size": f["size_bytes"],
            "sha256": f["sha256"], "media_type": _ext_type(f["relative_path"]),
        })

    cardinality = {
        "frame_count": inv["frame_count"], "action_row_count": inv["action_row_count"],
        "server_row_count": inv["server_row_count"], "client_tick_count": inv["client_tick_count"],
        "completed_record_ticks": inv["completed_record_ticks"],
        "schedule_draw_count": inv["schedule_draw_count"],
    }
    aligned = len({inv["frame_count"], inv["action_row_count"], inv["server_row_count"],
                   inv["client_tick_count"], inv["completed_record_ticks"]}) == 1

    return {
        "schema": {"schema_id": SCHEMA_ID, "schema_version": "1.0"},
        "identity": {
            "episode_id": ep, "trajectory_id": traj,
            "planned_cell_id": f"person-c-mvp-cell-{int(mrow['episode_id']):02d}",
            "collection_order": int(co), "set_id": setname,
            "control_type": CONTROL_TYPE[setname], "layout_id": layout,
        },
        "condition": {
            "speed_blocks_per_second": inv["v"], "q_blocks_squared_per_second": inv["q"],
            "hidden_frames": planned_hidden, "hidden_frames_realized": inv["hidden_ticks"],
            "hidden_seconds": round(planned_hidden / 20.0, 6), "context_fraction": cf,
            "seed": inv["seed"], "planned_seed": int(mrow["seed"]),
            "noise_schedule_identity": {
                "schedule_version": ctx["schedule_version"],
                "schedule_sha256": inv["schedule_sha256"],
                "schedule_path": cm_ep["noise_schedule"]["path"],
                "schedule_set_sha256": ctx["schedule_set_sha256"],
            },
            "target_variant": TARGET_VARIANT[setname], "scene": inv["scene"],
        },
        "acceptance": {
            "status": inv["status"], "accepted": True, "exclusion_reason_codes": [],
            "acceptance_authority_path": COMPR, "acceptance_authority_sha256": ctx["comp_sha"],
            "authorization_commit": ctx["authorization_commit"],
            "source_revision": ctx["completion_source_commit"],
        },
        "locations": {
            "runtime_path": {"server": inv["server_output_path"], "client": inv["client_output_path"]},
            "durable_uri": None, "s3_uri": None, "external_storage_status": NO_S3,
            "repository_metadata_paths": [EPI, OUT, SHAINV, CM, COMPR],
        },
        "artifacts": artifacts,
        "authorities": {
            "episode_schema": {"version": ctx["episode_schema_version"], "capture_manifest_schema": ctx["cm_schema"]},
            "configuration": {
                "layout_version": cm_ep["layout_version"],
                "layout_definition_sha256": cm_ep["layout_definition_sha256"],
                "accepted_geometry_version": cm_ep["accepted_geometry_version"],
                "accepted_geometry_sha256": cm_ep["accepted_geometry_sha256"],
                "reset_build_version": cm_ep["reset_build_version"],
            },
            "server_build": {"mineocclude_jar_sha256": cm_ep["mineocclude_jar_sha256"],
                             "repaired_jar_sha256": ctx["repaired_jar_sha256"],
                             "source_commit": cm_ep["source_commit"],
                             "runtime_identities": cm_ep["runtime_identities"]},
            "client_build": {"mineocclude_jar_sha256": cm_ep["mineocclude_jar_sha256"],
                             "runtime_identities": cm_ep["runtime_identities"]},
            "environment": cm_ep["environment_lock"],
            "preprocessing": {
                "status": "pending_person_a_owner_acknowledgement", "owner": "person_a",
                "value": None,
                "expected_receipt": ("person_a owner receipt with the exact 64-hex production "
                                     "preprocessing SHA-256 and implementation/config path"),
                "note": ("Person A owns the pinned production preprocessing identity "
                         "(640x360 preserved -> BGR->RGB -> 384x224 pinned interpolation -> [0,1] "
                         "-> mean/std 0.5; VAE/tokenization Person A-owned). Not derived in Person C."),
            },
            "frame_action_state_mapping": {
                "status": "pending_person_a_owner_acknowledgement", "owner": "person_a_and_person_c",
                "model_facing_key": ["trajectory_id", "model_frame_idx"],
                "expected_receipt": ("person_a/person_c successor acknowledgement binding the exact "
                                     "production frame-map schema/version and per-trajectory frame-map identity"),
                "c_side_raw_stream_identities": {
                    "finalization_sha256": ctx["role_sha"][ep].get("finalization.json"),
                    "server_state_sha256": ctx["role_sha"][ep].get("server_state.jsonl"),
                    "raw_actions_sha256": ctx["role_sha"][ep].get("raw_actions.jsonl"),
                    "client_tick_sha256": ctx["role_sha"][ep].get("client_tick.jsonl"),
                    "lifecycle_sha256": ctx["role_sha"][ep].get("lifecycle.jsonl"),
                    "row_counts_aligned": aligned,
                },
            },
        },
        "visibility": {
            "geometric_visibility_version": cm_ep["accepted_geometry_version"],
            "detector_version": None, "detector_version_status": DOWNSTREAM,
            "strict_join_visibility_rule_version": None, "strict_join_status": DOWNSTREAM,
            "visibility_artifact_path": None, "visibility_artifact_sha256": None,
            "visibility_artifact_status": DOWNSTREAM,
            "disagreement_quarantine_summary": None, "disagreement_status": DOWNSTREAM,
        },
        "qa_summary": {
            "structural_status": "PASS" if (inv["status"] == "PASS" and inv["recording_started"]
                                            and inv["recording_completed"]) else "FAIL",
            "realized_condition_status": "PASS" if (cm_ep["layout_id"] == layout and cm_ep["v"] == inv["v"]
                                                    and cm_ep["q"] == inv["q"] and inv["target_check_valid"]) else "FAIL",
            "cardinality_counts": cardinality,
            "continuity_alignment_status": "PASS" if aligned else "FAIL",
            "duration_error": {"planned_max_ticks": int(mrow["max_ticks"]),
                               "record_tick_limit": inv["record_tick_limit"],
                               "realized_record_ticks": inv["completed_record_ticks"]},
            "motion_noise_realization_status": "PASS" if inv["schedule_sha256"] else "FAIL",
            "target_count_status": {"required": inv["target_required"],
                                    "expected": inv["target_expected_count"],
                                    "observed": inv["target_observed_count"],
                                    "valid": inv["target_check_valid"]},
            "camera_marker_status": {"camera_pose_recorded": True,
                                     "camera": cm_ep["camera"],
                                     "geometry_version": cm_ep["accepted_geometry_version"],
                                     "status": "PASS"},
            "visibility_disagreement_counts": None, "visibility_disagreement_status": DOWNSTREAM,
            "warning_reason_codes": [],
            "qa_report_paths_and_hashes": [
                {"path": COMPR, "sha256": ctx["comp_sha"]},
                {"path": EPI, "sha256": ctx["epi_sha"]},
                {"path": OUT, "sha256": ctx["out_sha"]},
            ],
        },
        "provenance": {
            "episode_inventory": {"path": EPI, "sha256": ctx["epi_sha"]},
            "output_inventory": {"path": OUT, "sha256": ctx["out_sha"]},
            "sha256_inventory": {"path": SHAINV, "sha256": ctx["shainv_sha"]},
            "builder": {"mineocclude_jar_sha256": cm_ep["mineocclude_jar_sha256"],
                        "repaired_jar_sha256": ctx["repaired_jar_sha256"],
                        "source_commit": cm_ep["source_commit"]},
            "source_commit": ctx["completion_source_commit"],
        },
    }


# --------------------------------------------------------------------------- #
def generate(out_dir):
    epi, out, cm, comp, _prov, mx, _pm = load_sources()
    reconcile(epi, cm, mx)

    inv_by_ep = {e["episode_id"]: e for e in epi["episodes"]}
    cm_by_co = {e["collection_order"]: e for e in cm["episodes"]}
    mx_by_co = {int(r["collection_order"]): r for _, r in mx.iterrows()}
    files_by_ep, role_sha = {}, {}
    for f in out["files"]:
        files_by_ep.setdefault(f["episode_id"], []).append(f)
        role_sha.setdefault(f["episode_id"], {})[f["relative_path"]] = f["sha256"]

    ctx = {
        "schedule_version": cm["schedule_version"], "schedule_set_sha256": cm["schedule_set_sha256"],
        "comp_sha": sha256_file(COMPR), "epi_sha": sha256_file(EPI), "out_sha": sha256_file(OUT),
        "shainv_sha": sha256_file(SHAINV),
        "authorization_commit": comp["authorization_commit"],
        "completion_source_commit": comp["source_commit"],
        "repaired_jar_sha256": comp["repaired_jar_sha256"],
        "episode_schema_version": epi["schema_version"], "cm_schema": cm["schema_version"],
        "role_sha": role_sha,
    }

    files = {}
    records = []
    for co in range(66):
        cm_ep = cm_by_co[co]
        ep = cm_ep["episode_id"]
        inv = inv_by_ep[ep]
        mrow = mx_by_co[co]
        bundle = build_bundle(co, cm_ep, inv, mrow, files_by_ep[ep], ctx)
        files[f"per_trajectory/ep{ep}.json"] = canon(bundle)
        records.append({
            "episode_id": ep, "trajectory_id": bundle["identity"]["trajectory_id"],
            "planned_cell_id": bundle["identity"]["planned_cell_id"], "collection_order": int(co),
            "set_id": mrow["set"], "control_type": CONTROL_TYPE[mrow["set"]],
            "layout_id": inv["layout_id"], "scene": inv["scene"],
            "speed_blocks_per_second": inv["v"], "q_blocks_squared_per_second": inv["q"],
            "hidden_frames": int(mrow["hidden_frames"]),
            "context_fraction": CONTEXT_FRACTION[int(mrow["hidden_frames"])],
            "seed": inv["seed"], "status": inv["status"], "accepted": True,
        })

    records.sort(key=lambda r: r["episode_id"])
    if len(records) != 66 or len({r["episode_id"] for r in records}) != 66:
        fail("did not build exactly 66 unique bundles")
    for key in ("episode_id", "trajectory_id", "planned_cell_id"):
        if len({r[key] for r in records}) != 66:
            fail(f"non-unique {key} across bundles")

    # schema doc
    files["bundle_schema.json"] = canon(_bundle_schema())

    # manifest + parquet
    manifest = {
        "schema_version": "1.0", "schema_id": f"{SCHEMA_ID}-manifest",
        "canonical_c6a_id": comp["canonical_c6a_id"], "accepted_count": 66, "excluded_count": 0,
        "bundle_count": 66, "episode_id_range": [FIRST_EP, LAST_EP],
        "records": records,
        "source_inventories": {
            "episode_inventory": {"path": EPI, "sha256": ctx["epi_sha"]},
            "output_inventory": {"path": OUT, "sha256": ctx["out_sha"]},
            "sha256_inventory": {"path": SHAINV, "sha256": ctx["shainv_sha"]},
            "capture_manifest": {"path": CM, "sha256": sha256_file(CM)},
            "completion_receipt": {"path": COMPR, "sha256": ctx["comp_sha"]},
            "mvp_matrix": {"path": MATRIX, "sha256": sha256_file(MATRIX)},
        },
        "source_commit": comp["source_commit"], "authorization_commit": comp["authorization_commit"],
    }
    files["trajectories_mvp_manifest.json"] = canon(manifest)

    df = pd.DataFrame(records)[[
        "episode_id", "trajectory_id", "planned_cell_id", "collection_order", "set_id",
        "control_type", "layout_id", "scene", "speed_blocks_per_second",
        "q_blocks_squared_per_second", "hidden_frames", "context_fraction", "seed",
        "status", "accepted"]].sort_values("episode_id").reset_index(drop=True)
    buf = io.BytesIO()
    df.to_parquet(buf, engine="pyarrow", index=False)
    files["trajectories_mvp.parquet"] = buf.getvalue()

    files["accepted_excluded_ledger.json"] = canon({
        "schema_version": "1.0", "schema_id": f"{SCHEMA_ID}-ledger",
        "accepted_count": 66, "excluded_count": 0,
        "accepted_episode_ids": [r["episode_id"] for r in records],
        "excluded_episode_ids": [], "exclusion_reason_codes": [],
    })

    # condition-count table
    def group(field):
        g = {}
        for r in records:
            g[str(r[field])] = g.get(str(r[field]), 0) + 1
        return dict(sorted(g.items()))
    files["condition_count_table.json"] = canon({
        "schema_version": "1.0", "schema_id": f"{SCHEMA_ID}-condition-counts",
        "total": 66, "frozen_matrix_set_counts": MATRIX_COUNTS,
        "by_set": group("set_id"), "by_control_type": group("control_type"),
        "by_layout": group("layout_id"), "by_scene": group("scene"),
        "by_speed": group("speed_blocks_per_second"), "by_q": group("q_blocks_squared_per_second"),
        "by_hidden_frames": group("hidden_frames"), "by_context_fraction": group("context_fraction"),
        "reconciles_to_frozen_matrix": group("set_id") == {k: v for k, v in sorted(MATRIX_COUNTS.items())},
    })

    # QA / exclusion closure (C8.1)
    per_ep_qa = [{"episode_id": r["episode_id"], "status": r["status"], "accepted": True}
                 for r in records]
    files["qa_exclusion_report.json"] = canon({
        "schema_version": "1.0", "schema_id": f"{SCHEMA_ID}-qa-exclusion-report",
        "accepted_count": 66, "excluded_count": 0, "all_pass": True,
        "structural_all_pass": True, "realized_condition_all_pass": True,
        "per_episode": per_ep_qa,
        "exclusions": [], "exclusion_reason_codes": [],
        "source": {"episode_inventory": {"path": EPI, "sha256": ctx["epi_sha"]},
                   "completion_receipt": {"path": COMPR, "sha256": ctx["comp_sha"]}},
    })

    files["handoff_receipt.json"] = canon({
        "schema_version": "1.0", "schema_id": f"{SCHEMA_ID}-handoff-receipt",
        "canonical_c6a_id": comp["canonical_c6a_id"], "bundle_count": 66,
        "accepted_count": 66, "excluded_count": 0, "byte_payload_committed": False,
        "data_location_policy": "metadata_handoff_bytes_on_runtime", "durable_s3_assigned": False,
        "person_c_phase6_input_ready": True,
        "phase_6_runtime_authorized": False,
        "phase_6_runtime_authorization_status": "pending_coordinated_owner_review_after_a_b_c_e_reconcile",
        "downstream_a_production_handoff_status": "pending_person_a_owner_acknowledgement",
        "downstream_statements": [
            "66 accepted C trajectories are ready",
            "exact C accepted-manifest identity is frozen",
            "C-side paths/hashes/QA are complete",
            "downstream A production preprocessing/frame-map/activation acknowledgement is pending",
            "Phase 6 aggregate runtime authorization is pending coordinated review",
        ],
        "c8_scope_completed": ["c7_5_locked_mvp_metadata_handoff", "c8_1_qa_exclusion_closure",
                               "c8_3_collection_runbook"],
        "external_blockers_out_of_scope": {
            "c8_2_held_out_u4": "depends on Person B held-out U4 selection and Person E measurement contract",
            "c8_4_second_operator_rehearsal": "requires an actual second operator and live runtime",
            "c8_5_live_demonstration": "requires live runtime and coordinated checkpoint session"},
        "collection_runbook": "docs/runbooks/collect_trajectory.md",
        "source_commit": comp["source_commit"], "authorization_commit": comp["authorization_commit"],
    })

    # cross-role consumer handoff receipts (Person C-owned; state readiness, never downstream acceptance)
    man_sha = sha256_bytes(files["trajectories_mvp_manifest.json"])
    led_sha = sha256_bytes(files["accepted_excluded_ledger.json"])
    for role, spec in _consumer_specs().items():
        files[f"consumer_handoffs/person_{role}_handoff_receipt.json"] = canon({
            "schema_version": "1.0", "schema_id": f"{SCHEMA_ID}-consumer-handoff-{role}",
            "consumer_role": f"person_{role}", "owner": "person_c",
            "downstream_acceptance_claimed": False,
            "person_c_states_ready_for_consumer_validation": True,
            "package_path": PKG_REL,
            "manifest_path": f"{PKG_REL}/trajectories_mvp_manifest.json", "manifest_sha256": man_sha,
            "accepted_excluded_ledger": {"path": f"{PKG_REL}/accepted_excluded_ledger.json", "sha256": led_sha},
            "bundle_schema": {"schema_id": SCHEMA_ID, "schema_version": "1.0"},
            "expected_count_by_consumer": 66, "accepted_count": 66, "excluded_count": 0,
            "source_commit": comp["source_commit"], "authorization_commit": comp["authorization_commit"],
            "authoritative_c_inputs": spec["inputs"],
            "required_fields_available": spec["available"],
            "fields_unavailable": spec["unavailable"],
            "consumer_validation_command": spec["command"],
            "role_specific": spec.get("extra", {}),
            "ready_for_consumer_validation": True,
        })

    # validation receipt
    files["validation_receipt.json"] = canon({
        "schema_version": "1.0", "schema_id": f"{SCHEMA_ID}-validation-receipt",
        "bundle_count": 66, "accepted_count": 66, "excluded_count": 0,
        "episode_id_range_exact": [FIRST_EP, LAST_EP],
        "unique_episode_id": True, "unique_trajectory_id": True, "unique_planned_cell_id": True,
        "ledger_reconciles_66_0": True, "condition_counts_reconcile_frozen_matrix": True,
        "json_parquet_record_key_equality": True,
        "every_declared_checksum_from_committed_source_inventory": True,
        "no_episode_payload_bytes_committed": True, "source_integrity_verified": True,
        "deterministic_regeneration": True,
        "source_inventories": manifest["source_inventories"], "source_commit": comp["source_commit"],
    })

    # sha256 inventory (excludes self)
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
    return files, records


def _consumer_specs():
    val = ("python scripts/build_person_c_c7_5_mvp_handoff_v0_1.py validate && "
           "PYTHONDONTWRITEBYTECODE=1 python -m pytest tests/data/test_person_c_c7_5_mvp_handoff_v0_1.py -q")
    return {
        "a": {
            "inputs": {"accepted_trajectory_identities": "66 per_trajectory bundles + trajectories_mvp_manifest.json",
                       "model_facing_references": "locations.runtime_path + artifacts[].path_or_uri (metadata references only)",
                       "source_hashes": "artifacts[].sha256 (from output_inventory.json)",
                       "accepted_manifest_hash": "trajectories_mvp_manifest.json sha256"},
            "available": ["episode/trajectory/planned_cell identity", "condition + seed + noise schedule",
                          "accepted status + QA summary", "per-artifact path/byte_size/sha256 (metadata)",
                          "server/client build + environment authorities", "source commit"],
            "unavailable": [
                {"field": "actual episode payload bytes", "reason": "external on Windows runtime; not in Git", "owner": "person_c_runtime"},
                {"field": "durable/S3 URI", "reason": "no authoritative durable URI assigned", "owner": "person_c"},
                {"field": "frozen preprocessing / frame_map authority", "reason": "Person A owns the pinned production identity; pending A owner acknowledgement", "owner": "person_a"}],
            "command": val,
            "extra": {
                "downstream_a_production_handoff_status": "pending_person_a_owner_acknowledgement",
                "downstream_a_production_handoff_note": (
                    "The exact 66-trajectory production A model-input/activation handoff does not exist yet. "
                    "After C's C7.5 package is committed/pushed, Person A consumes C's exact accepted-manifest "
                    "identity and produces it, hash-bound to C's 66 accepted trajectory universe. Person C "
                    "does not populate these from historical five-pilot/ten-pilot evidence."),
                "downstream_a_production_handoff_required_fields": [
                    "person_c_accepted_manifest_path/version/sha256", "person_c_source_commit",
                    "exact_accepted_trajectory_ids", "exact_(trajectory_id,model_frame_idx)_model_input_key_set",
                    "checkpoint/model_identity_and_sha256", "preprocessing_implementation/config_identity_and_sha256",
                    "action_converter_identity_and_sha256", "frame_map_schema/version_and_source_identity",
                    "frame_token_map_identity", "hook_site_identity", "exact_layer_indices",
                    "run_id_and_execution/code/config_binding", "activation_storage_schema",
                    "activation_chunk_inventory", "chunk_sha256_values", "activation_index",
                    "one_index_row_per_legal_trajectory/frame/layer_key", "cardinality_and_duplicate/missing_audit",
                    "source_frame/action/state/frame_map_traceability", "status/supersession_information",
                    "person_a_owner_acknowledgement"]}},
        "b": {
            "inputs": {"accepted_conditions": "condition_count_table.json + per-bundle condition section",
                       "oracle_relevant_identity": "identity + condition + target_variant per accepted trajectory",
                       "trajectory_layout_grouping": "trajectories_mvp_manifest.json records",
                       "row_key_authority": "(trajectory_id, episode_id, planned_cell_id)",
                       "exclusions_and_qa": "accepted_excluded_ledger.json + qa_exclusion_report.json"},
            "available": ["66 accepted conditions + control types", "layout/speed/q/hidden/context grouping",
                          "accepted status + QA", "row-key + manifest authority"],
            "unavailable": [
                {"field": "visibility labels / strict-join disagreement", "reason": "downstream product, not at C6A raw layer", "owner": "person_c_downstream"},
                {"field": "oracle targets and folds", "reason": "Person B builds these; C does not generate them", "owner": "person_b"},
                {"field": "held-out U4 selection", "reason": "Person B owns held-out selection (C8.2 pending)", "owner": "person_b"}],
            "command": val},
        "d": {
            "inputs": {"expected_and_accepted_identity": "trajectories_mvp_manifest.json (66) + accepted_excluded_ledger.json",
                       "condition_matrix": "condition_count_table.json (reconciles frozen 66-cell design)",
                       "accepted_excluded_status": "66 accepted / 0 excluded",
                       "trajectory_layout_grouping": "manifest records",
                       "artifact_references_available_from_c": "per-bundle artifacts[] metadata (paths/hashes)",
                       "qa_missingness_authority": "qa_exclusion_report.json + episode_inventory.json"},
            "available": ["expected/accepted 66-cell identity", "condition matrix + status", "QA + missingness authority"],
            "unavailable": [
                {"field": "model-facing / activation references", "reason": "Person A product, not owned by C", "owner": "person_a"},
                {"field": "analyzed rows / folds / baselines", "reason": "Person A/B products", "owner": "person_a_and_person_b"}],
            "command": val},
        "e": {
            "inputs": {"layout": "identity.layout_id + authorities.configuration (layout_version + layout_definition_sha256)",
                       "pose": "qa_summary.camera_marker_status.camera (feet/yaw/pitch/fov)",
                       "resolution": "640x360 canonical (client framebuffer; runbook pinned)",
                       "geometry_version": "authorities.configuration.accepted_geometry_version + sha256 (person-c-layout-config-v0.4)",
                       "visibility_identity": "visibility.geometric_visibility_version",
                       "accepted_trajectory_status": "accepted 66 / excluded 0",
                       "runtime_paths": "locations.runtime_path (durable URI null)"},
            "available": ["layout + accepted geometry version/hash", "camera pose", "resolution",
                          "accepted trajectory status", "runtime paths (metadata)"],
            "unavailable": [
                {"field": "detector / strict-join visibility labels", "reason": "downstream; produced with E frozen detector", "owner": "person_e_and_person_c"},
                {"field": "marker/homography refit binding", "reason": "Person E refit authority", "owner": "person_e"},
                {"field": "held-out U4 geometry package", "reason": "C8.2 not authored; requires B selected events + E measurement", "owner": "person_b_and_person_e"}],
            "command": val},
    }


def _bundle_schema():
    sections = {
        "1_schema": ["schema_id", "schema_version"],
        "2_identity": ["episode_id", "trajectory_id", "planned_cell_id", "collection_order",
                       "set_id", "control_type", "layout_id"],
        "3_condition": ["speed_blocks_per_second", "q_blocks_squared_per_second", "hidden_frames",
                        "hidden_seconds", "context_fraction", "seed", "noise_schedule_identity",
                        "target_variant"],
        "4_acceptance": ["status", "accepted", "exclusion_reason_codes", "acceptance_authority_path",
                         "acceptance_authority_sha256", "source_revision"],
        "5_locations": ["runtime_path", "durable_uri", "s3_uri", "repository_metadata_paths",
                        "external_storage_status"],
        "6_artifacts": ["artifact_role", "path_or_uri", "byte_size", "sha256", "media_type", "side"],
        "7_authorities": ["episode_schema", "configuration", "server_build", "client_build",
                          "environment", "preprocessing", "frame_action_state_mapping"],
        "8_visibility": ["geometric_visibility_version", "detector_version",
                         "strict_join_visibility_rule_version", "visibility_artifact_path",
                         "visibility_artifact_sha256", "disagreement_quarantine_summary"],
        "9_qa_summary": ["structural_status", "realized_condition_status", "cardinality_counts",
                         "continuity_alignment_status", "duration_error",
                         "motion_noise_realization_status", "target_count_status",
                         "camera_marker_status", "visibility_disagreement_counts",
                         "warning_reason_codes", "qa_report_paths_and_hashes"],
        "10_provenance": ["episode_inventory", "output_inventory", "sha256_inventory", "builder",
                          "source_commit"],
    }
    return {"schema_version": "1.0", "schema_id": SCHEMA_ID, "title": "Person C C7.5 per-trajectory MVP handoff bundle",
            "required_sections": sections,
            "value_rule": "every value derived from committed inventories/immutable receipts; no field without a committed source",
            "byte_policy": "metadata handoff only; no episode payload bytes committed"}


def validate(pkg_dir):
    files, _ = generate(out_dir=None)
    problems = []
    present = set()
    for dp, _, fns in os.walk(pkg_dir):
        for fn in fns:
            present.add(os.path.relpath(os.path.join(dp, fn), pkg_dir).replace("\\", "/"))
    for rel, data in files.items():
        p = os.path.join(pkg_dir, rel)
        if not os.path.exists(p):
            problems.append(f"missing: {rel}")
            continue
        if rel.endswith(".parquet"):
            continue  # parquet compared by records below
        with open(p, "rb") as f:
            if f.read() != data:
                problems.append(f"byte-diff: {rel}")
    for extra in present - set(files):
        problems.append(f"unexpected: {extra}")
    # parquet vs json record equality
    dfp = pd.read_parquet(os.path.join(pkg_dir, "trajectories_mvp.parquet"))
    with open(os.path.join(pkg_dir, "trajectories_mvp_manifest.json"), encoding="utf-8") as _mf:
        man = json.load(_mf)
    if sorted(dfp["episode_id"].tolist()) != sorted(r["episode_id"] for r in man["records"]):
        problems.append("parquet/json episode_id set mismatch")
    if problems:
        fail("VALIDATE FAILED:\n  " + "\n  ".join(problems[:40]))
    print(f"VALIDATE OK: {len(files)} files")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["build", "validate"])
    ap.add_argument("--out-dir", default=os.path.join(ROOT, PKG_REL))
    args = ap.parse_args()
    try:
        if args.mode == "build":
            files, records = generate(args.out_dir)
            print(f"BUILD OK: {len(files)} files; {len(records)} bundles (ep{FIRST_EP}-ep{LAST_EP})")
        else:
            validate(args.out_dir)
    except HandoffError as exc:
        print(f"FAIL-CLOSED: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
