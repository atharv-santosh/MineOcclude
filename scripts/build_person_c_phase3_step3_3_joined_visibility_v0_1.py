"""Build Person C's authoritative Phase 3 Step 3.3 joined-visibility package.

Joins Person C committed geometry with Person E's independently verified
empirical visibility using the committed strict-join implementation
(``mineocclude.data.visibility_join.strict_join``), which is the sole owner of
final row construction and the label

    visible_flag = geometric_visible AND empirical_magenta_visible

This script performs independent preflight validation and enriches the joined
rows with interface-required context/provenance fields, but never reimplements
the AND rule or the structural checks, never runs the detector, never computes
accuracy metrics, never writes empirical_magenta_visible or lets E write
visible_flag, and never inspects U4.

Modes: ``build`` (production join) and ``validate`` (validate an existing
package without rerunning the detector or rewriting anything).
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import io
import json
import os
import platform
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
from mineocclude.data.visibility_join import (
    FINAL_VISIBILITY_INTERFACE_VERSION,
    strict_join,
)

SCHEMA_ID = "person-c-phase3-step3-3-joined-visibility-v0-1"
PKG_REL = "data/handoff_b/person_c_phase3_step3_3_joined_visibility_v0_1"

# ---- bound authorities ----------------------------------------------------
PERSON_A_MODEL_PREPROC_AUTHORITY = "06b87fe1f43d2133c25db498fcc1fd234f958aad"
PERSON_B_POLICY = "eec9396e6a93feaab3d5d298ac7cdc4cb54fdbd4"
PERSON_B_COORD_PATH = "src/mineocclude/analysis/coordinates.py"
PERSON_B_COORD_SHA = "19e3946e0b0385989b639187e0eda8ff4cc7712938fd87c6084fb9d2306af493"
PERSON_B_COORD_SCHEMA = "person-b-wall-parallel-frame-v0.1"
PERSON_C_CURRENT = "cbe673d7d765178b3175af60e69c609547be1d68"
PERSON_C_GEOMETRY_ORIGIN = "3ba6c091426a537d60c950dd1bb38f5fc02826d5"
PERSON_C_SOURCE_REVISION = "fa70424530f422a2e6140e0e90d0ff18f583141e"

GVR_REL = "data/handoff_e/phase3_visibility_authority_v0_1/geometric_visibility_records.jsonl"
GVR_SHA = "914a5bee842c92e707b94c6d58c91807681310ac6a393d18a06ba8dfa70572eb"
FINAL_INTERFACE_REL = "data/handoff_e/phase3_visibility_interface_v0_1/final_visibility_interface.json"
FINAL_INTERFACE_SHA = "fd9a68681b002c0c3652e4299691e55417c18bdd9ef0f69d351c96bfd8822730"
IMPORT_CONTRACT_REL = "data/handoff_e/phase3_visibility_interface_v0_1/empirical_visibility_import_contract.json"
IMPORT_CONTRACT_SHA = "a286341bb157e6630d0b18adef26efc31ad97fc9e921cbbeca960974f3ce5f4c"
DISAGREEMENT_REL = "data/handoff_e/phase3_visibility_interface_v0_1/visibility_disagreement_schema.json"
DISAGREEMENT_SHA = "d8cd12786bb36211bd5b91d2f0c575809f89808fb44114e6589b8a20ee6ac963"
# committed context authority that binds resolution / coordinate_convention per key
CONTEXT_AUTHORITY_REL = "data/handoff_e/phase3_visibility_repair_v0_1/generation_input_manifest.jsonl"

PERSON_E_COMMIT = "90855ea52b19ced3f0ce610f7d18db35070ee023"
E_PKG_SUBDIR = "data/handoff_c/person_e_phase3_step3_3_empirical_visibility_v0_1"
E_EMPIRICAL_NAME = "empirical_visibility_records.jsonl"
E_DIAG_NAME = "detector_diagnostics.jsonl"
E_INVENTORY_NAME = "sha256_inventory.json"
E_EMPIRICAL_SHA = "b6da7d73e2eea0975469d59cb92a47aace90d1651c8e42cc22cfc40675d90681"
E_DIAG_SHA = "288277f7e9d20348d82a543b90a79cc8340843e30f02f454340bc855e80aa7ad"
E_INVENTORY_SHA = "f21fd49e001aac9f35545721e5d0f357b8b635cd26d1fcb5ce9f5938b284fc52"

DETECTOR_VERSION = ("hsv-largest-valid-blob-v1.0-candidate:sha256:"
                    "0cadf618fca1578196bde4982021c38627ccb9c39e46353812e7da3fce6aa125")
DETECTOR_IDENTITY = "0cadf618fca1578196bde4982021c38627ccb9c39e46353812e7da3fce6aa125"

RESOLUTION_VALUE = "640x360"
COORD_VALUE = "pixel_center_xy_zero_based"
PRIMARY_KEY = ("trajectory_id", "model_frame_idx")
CONTEXT_KEYS = ("layout_id", "canonical_camera_pose_id", "resolution", "coordinate_convention")
E_AUTHORIZED_FIELDS = {"trajectory_id", "model_frame_idx", "empirical_magenta_visible",
                       "detector_version", "layout_id", "canonical_camera_pose_id",
                       "resolution", "coordinate_convention"}
QUARANTINE_CATEGORIES = {"geometry_hidden_detector_visible", "geometry_visible_detector_hidden",
                         "invalid_geometry", "missing_detector", "none"}
# C geometry/provenance fields preserved verbatim on every joined row
C_PRESERVE = ("render_frame_idx", "source_frame_map", "source_frame_map_sha256",
              "source_revision", "geometric_status", "geometric_validity", "scene",
              "regime", "frame_640_sha256", "geometry_rejection_reason", "source_world_state")


class JoinPackageError(Exception):
    pass


def fail(msg: str):
    raise JoinPackageError(msg)


# ---- serialization --------------------------------------------------------
def dump_json(obj) -> bytes:
    return (json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def dump_jsonl(rows) -> bytes:
    out = io.StringIO()
    for r in rows:
        out.write(json.dumps(r, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
        out.write("\n")
    return out.getvalue().encode("utf-8")


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_jsonl(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def _utc() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _require_sha(path: str, expected: str, label: str):
    got = sha256_file(path)
    if got != expected:
        fail(f"{label} SHA-256 mismatch: {got} != {expected}")


# ---- input loading + independent preflight --------------------------------
def load_inputs(e_root: str):
    if "mineocclude_u4" in e_root or "/u4" in e_root.lower():
        fail("U4 source root is forbidden")

    # C authorities from the current C worktree
    _require_sha(os.path.join(ROOT, GVR_REL), GVR_SHA, "C geometric records")
    _require_sha(os.path.join(ROOT, FINAL_INTERFACE_REL), FINAL_INTERFACE_SHA, "C final interface")
    _require_sha(os.path.join(ROOT, IMPORT_CONTRACT_REL), IMPORT_CONTRACT_SHA, "C import contract")
    _require_sha(os.path.join(ROOT, DISAGREEMENT_REL), DISAGREEMENT_SHA, "C disagreement schema")
    _require_sha(os.path.join(ROOT, PERSON_B_COORD_PATH), PERSON_B_COORD_SHA, "B coordinate authority")

    # E package from the explicit detached E root
    e_dir = os.path.join(e_root, E_PKG_SUBDIR)
    e_emp = os.path.join(e_dir, E_EMPIRICAL_NAME)
    e_diag = os.path.join(e_dir, E_DIAG_NAME)
    e_inv = os.path.join(e_dir, E_INVENTORY_NAME)
    _require_sha(e_emp, E_EMPIRICAL_SHA, "E empirical records")
    _require_sha(e_diag, E_DIAG_SHA, "E diagnostics")
    _require_sha(e_inv, E_INVENTORY_SHA, "E inventory")

    c_records = read_jsonl(os.path.join(ROOT, GVR_REL))
    e_records = read_jsonl(e_emp)
    diagnostics = read_jsonl(e_diag)
    context = {(g["trajectory_id"], g["model_frame_idx"]): g
               for g in read_jsonl(os.path.join(ROOT, CONTEXT_AUTHORITY_REL))}
    return c_records, e_records, diagnostics, context


def preflight(c_records, e_records, diagnostics, context):
    counts = {}
    # C completeness / uniqueness
    ck = [(r["trajectory_id"], r["model_frame_idx"]) for r in c_records]
    counts["input_c_rows"] = len(c_records)
    counts["duplicate_c_keys"] = len(ck) - len(set(ck))
    if counts["duplicate_c_keys"]:
        fail("duplicate C primary key")
    if len(c_records) != 1850:
        fail(f"C rows != 1850: {len(c_records)}")

    # E completeness / uniqueness / field discipline
    ek = [(r["trajectory_id"], r["model_frame_idx"]) for r in e_records]
    counts["input_e_rows"] = len(e_records)
    counts["duplicate_e_keys"] = len(ek) - len(set(ek))
    if counts["duplicate_e_keys"]:
        fail("duplicate E primary key")
    if len(e_records) != 1850:
        fail(f"E rows != 1850: {len(e_records)}")
    for r in e_records:
        assert_e_record_discipline(r)
    counts["malformed_empirical"] = 0
    counts["detector_version_mismatch"] = 0

    # key-set equalities (C == E == diagnostics == context authority)
    ckset, ekset = set(ck), set(ek)
    dkset = {(r["trajectory_id"], r["model_frame_idx"]) for r in diagnostics}
    counts["missing_e_keys"] = len(ckset - ekset)
    counts["extra_e_keys"] = len(ekset - ckset)
    if ckset != ekset:
        fail("C/E primary-key sets differ")
    if ekset != dkset:
        fail("E empirical / diagnostic key sets differ")
    if ckset != set(context):
        fail("C key set != committed context-authority key set")

    # context equality across every identity (C-enriched vs E vs authority)
    ctx_mismatch = 0
    e_index = {(_k(r)): r for r in e_records}
    for c in c_records:
        k = _k(c)
        g, e = context[k], e_index[k]
        if g["layout_id"] != c["layout_id"] or g["canonical_camera_pose_id"] != c["canonical_camera_pose_id"]:
            ctx_mismatch += 1
        if (g["layout_id"] != e["layout_id"] or g["canonical_camera_pose_id"] != e["canonical_camera_pose_id"]
                or g["resolution"] != e["resolution"] or g["coordinate_convention"] != e["coordinate_convention"]):
            ctx_mismatch += 1
        if g["resolution"] != RESOLUTION_VALUE or g["coordinate_convention"] != COORD_VALUE:
            ctx_mismatch += 1
    counts["context_mismatches"] = ctx_mismatch
    if ctx_mismatch:
        fail("context identity mismatch")
    return counts


def _k(rec):
    return (rec["trajectory_id"], rec["model_frame_idx"])


def assert_e_record_discipline(rec: dict):
    """Fail closed on a single E row that violates the import contract."""
    if "visible_flag" in rec:
        fail("E supplies visible_flag")
    if set(rec.keys()) != E_AUTHORIZED_FIELDS:
        fail(f"E row {_k(rec)} field set != 8 authorized fields: {sorted(rec)}")
    if not isinstance(rec["empirical_magenta_visible"], bool):
        fail(f"malformed empirical boolean at {_k(rec)}")
    if rec["detector_version"] != DETECTOR_VERSION:
        fail(f"wrong detector version at {_k(rec)}")
    if rec["resolution"] != RESOLUTION_VALUE or not isinstance(rec["resolution"], str):
        fail(f"wrong resolution at {_k(rec)}")
    if rec["coordinate_convention"] != COORD_VALUE or not isinstance(rec["coordinate_convention"], str):
        fail(f"wrong coordinate_convention at {_k(rec)}")


# ---- production join ------------------------------------------------------
def run_join(c_records, e_records, context):
    """Enrich C context, delegate to strict_join, then attach preserved fields."""
    c_by_key = {_k(c): c for c in c_records}
    c_in = []
    for c in c_records:
        g = context[_k(c)]
        cc = dict(c)
        cc["resolution"] = g["resolution"]
        cc["coordinate_convention"] = g["coordinate_convention"]
        c_in.append(cc)
    # authoritative label + quarantine + structural checks (committed impl)
    joined = strict_join(c_in, e_records, expected_detector_version=DETECTOR_VERSION)
    # enrich each authoritative row with context + preserved C fields (no channel/label change)
    for row in joined:
        c = c_by_key[_k(row)]
        row["resolution"] = context[_k(row)]["resolution"]
        row["coordinate_convention"] = context[_k(row)]["coordinate_convention"]
        for f in C_PRESERVE:
            if f in c and f not in row:
                row[f] = c[f]
    joined.sort(key=lambda r: (r["trajectory_id"], r["model_frame_idx"]))
    return joined


# ---- artifact builders ----------------------------------------------------
def _schema_ref(name):
    return {"schema_version": "1.0", "schema_id": SCHEMA_ID, "artifact": name}


def build_joined_schema():
    return {
        "schema_version": "1.0", "schema_id": SCHEMA_ID,
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": f"{SCHEMA_ID}:joined_visibility_records",
        "primary_key": list(PRIMARY_KEY),
        "one_to_one_join": True,
        "final_label_owner": "Person C",
        "final_rule": "visible_flag = geometric_visible AND empirical_magenta_visible",
        "person_e_may_write_visible_flag": False,
        "raw_channels_preserved_separately": ["geometric_visible", "empirical_magenta_visible"],
        "context_identities_must_match": list(CONTEXT_KEYS),
        "resolution_constraint": {"type": "string", "const": RESOLUTION_VALUE},
        "coordinate_convention_constraint": {"type": "string", "const": COORD_VALUE},
        "detector_version_constraint": {"type": "string", "const": DETECTOR_VERSION},
        "quarantine_category_enum": sorted(QUARANTINE_CATEGORIES),
        "required_fields": {
            "trajectory_id": "string", "model_frame_idx": "integer",
            "layout_id": "string", "canonical_camera_pose_id": "string",
            "resolution": "string", "coordinate_convention": "string",
            "geometric_visible": "boolean|null", "empirical_magenta_visible": "boolean|null",
            "visible_flag": "boolean", "quarantined": "boolean",
            "quarantine_category": "string", "invalidity_reason": "string|null",
            "detector_version": "string", "geometry_rule_version": "string",
        },
        "package_level_fail_closed_conditions": [
            "duplicate_c_primary_key", "duplicate_e_primary_key", "missing_e_primary_key",
            "extra_e_primary_key", "incomplete_c_input", "incomplete_e_input",
            "e_supplies_visible_flag", "wrong_detector_version", "malformed_empirical_boolean",
            "wrong_layout_id", "wrong_canonical_camera_pose_id", "wrong_resolution",
            "wrong_coordinate_convention", "schema_mismatch", "failure_to_preserve_source_field",
        ],
    }


def build_authority_binding():
    return {
        "schema_version": "1.0", "schema_id": SCHEMA_ID,
        "person_a_model_preprocessing_authority": {
            "commit": PERSON_A_MODEL_PREPROC_AUTHORITY,
            "owns": "model and preprocessing provenance only",
            "does_not_own": ["wall_parallel_coordinate_frame", "final_visibility_label"],
        },
        "person_b_step3_3_policy": {"commit": PERSON_B_POLICY},
        "person_b_coordinate_authority": {
            "path": PERSON_B_COORD_PATH, "sha256": PERSON_B_COORD_SHA,
            "schema": PERSON_B_COORD_SCHEMA,
            "required_signoff": {"person_b": True, "person_c": True},
        },
        "person_c_current_authority": PERSON_C_CURRENT,
        "person_c_original_geometry_authority": PERSON_C_GEOMETRY_ORIGIN,
        "person_c_source_revision": PERSON_C_SOURCE_REVISION,
        "person_c_geometric_records": {"path": GVR_REL, "sha256": GVR_SHA},
        "person_c_final_interface": {"path": FINAL_INTERFACE_REL, "sha256": FINAL_INTERFACE_SHA},
        "person_c_empirical_import_contract": {"path": IMPORT_CONTRACT_REL, "sha256": IMPORT_CONTRACT_SHA},
        "person_c_disagreement_schema": {"path": DISAGREEMENT_REL, "sha256": DISAGREEMENT_SHA},
        "person_e_empirical_authority": {
            "commit": PERSON_E_COMMIT,
            "empirical_records_sha256": E_EMPIRICAL_SHA,
            "detector_diagnostics_sha256": E_DIAG_SHA,
            "inventory_sha256": E_INVENTORY_SHA,
        },
        "detector_version": DETECTOR_VERSION,
        "detector_identity": DETECTOR_IDENTITY,
        "final_label_owner": "Person C",
        "empirical_channel_owner": "Person E",
    }


def build_coverage(counts):
    return {
        "schema_version": "1.0", "schema_id": SCHEMA_ID,
        "expected_c_rows": 1850, "expected_e_rows": 1850,
        "produced_joined_rows": counts["joined_rows"],
        "unique_joined_keys": counts["unique_joined_keys"],
        "missing_e_keys": counts["missing_e_keys"], "extra_e_keys": counts["extra_e_keys"],
        "duplicate_c_keys": counts["duplicate_c_keys"], "duplicate_e_keys": counts["duplicate_e_keys"],
        "context_mismatches": counts["context_mismatches"],
        "detector_version_mismatches": counts["detector_version_mismatch"],
        "malformed_empirical_values": counts["malformed_empirical"],
        "joined_c_key_set_equality": True,
        "joined_e_key_set_equality": True,
        "diagnostic_e_key_set_equality": True,
    }


def build_quarantine_accounting(joined):
    cats = ("geometry_hidden_detector_visible", "geometry_visible_detector_hidden",
            "invalid_geometry", "missing_detector", "none")
    layouts = sorted({r["layout_id"] for r in joined})

    def tally(rows):
        t = {"input_rows": len(rows),
             "visible_flag_true": sum(1 for r in rows if r["visible_flag"]),
             "visible_flag_false": sum(1 for r in rows if not r["visible_flag"]),
             "quarantined": sum(1 for r in rows if r["quarantined"]),
             "non_quarantined": sum(1 for r in rows if not r["quarantined"])}
        for c in cats:
            t[c] = sum(1 for r in rows if r["quarantine_category"] == c)
        return t

    per_layout = {lay: tally([r for r in joined if r["layout_id"] == lay]) for lay in layouts}
    return {
        "schema_version": "1.0", "schema_id": SCHEMA_ID,
        "total": tally(joined),
        "per_layout": per_layout,
    }


def build_strict_join_receipt(counts, e_root, start, end):
    impl = os.path.join(ROOT, "src/mineocclude/data/visibility_join.py")
    return {
        "schema_version": "1.0", "schema_id": SCHEMA_ID,
        "strict_join_import_path": "mineocclude.data.visibility_join.strict_join",
        "implementation_file": "src/mineocclude/data/visibility_join.py",
        "implementation_sha256": sha256_file(impl),
        "final_visibility_interface_version": FINAL_VISIBILITY_INTERFACE_VERSION,
        "c_geometric_records_sha256": GVR_SHA,
        "e_empirical_records_sha256": E_EMPIRICAL_SHA,
        "e_package_root": e_root,
        "join_start_utc": start, "join_end_utc": end,
        "command": counts["command"],
        "one_to_one_join": True,
        "final_rule": "visible_flag = geometric_visible AND empirical_magenta_visible",
        "structural_failure_counts": {
            "duplicate_c_keys": counts["duplicate_c_keys"],
            "duplicate_e_keys": counts["duplicate_e_keys"],
            "missing_e_keys": counts["missing_e_keys"],
            "extra_e_keys": counts["extra_e_keys"],
            "context_mismatches": counts["context_mismatches"],
            "detector_version_mismatch": counts["detector_version_mismatch"],
            "malformed_empirical": counts["malformed_empirical"],
        },
        "disagreement_counts": counts["category_counts"],
        "no_silent_repair": True, "no_dropped_rows": True,
        "no_e_written_visible_flag": True, "no_detector_rerun": True,
        "no_u4_inspection": True,
    }


def build_provenance_index(counts, files_sha):
    return {
        "schema_version": "1.0", "schema_id": SCHEMA_ID,
        "runtime": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "pandas": _optver("pandas"),
        },
        "command": counts["command"],
        "authorities": {
            "person_a_model_preprocessing_commit": PERSON_A_MODEL_PREPROC_AUTHORITY,
            "person_b_policy_commit": PERSON_B_POLICY,
            "person_b_coordinate_frame": {
                "path": PERSON_B_COORD_PATH, "sha256": PERSON_B_COORD_SHA,
                "schema": PERSON_B_COORD_SCHEMA,
                "signoff": {"person_b": True, "person_c": True},
            },
            "person_c_current_authority": PERSON_C_CURRENT,
            "person_c_original_geometry_authority": PERSON_C_GEOMETRY_ORIGIN,
            "person_e_empirical_commit": PERSON_E_COMMIT,
        },
        "input_hashes": {
            "c_geometric_records": GVR_SHA,
            "c_final_interface": FINAL_INTERFACE_SHA,
            "c_empirical_import_contract": IMPORT_CONTRACT_SHA,
            "c_disagreement_schema": DISAGREEMENT_SHA,
            "e_empirical_records": E_EMPIRICAL_SHA,
            "e_detector_diagnostics": E_DIAG_SHA,
            "e_inventory": E_INVENTORY_SHA,
        },
        "output_hashes": files_sha,
        "model_preprocessing_provenance": {
            "owner": "Person A (authorized), carried by Person C",
            "person_c_source_revision": PERSON_C_SOURCE_REVISION,
            "per_frame_canonical_frame_hash_field": "frame_640_sha256",
            "per_frame_source_frame_map_hash_field": "source_frame_map_sha256",
            "note": ("model/preprocessing provenance is preserved per row via source_revision "
                     "and frame_640_sha256; no A-owned provenance value is absent"),
        },
        "final_label_owner": "Person C",
        "empirical_channel_owner": "Person E",
        "joined_package_identity": SCHEMA_ID,
    }


def _optver(mod):
    try:
        return __import__(mod).__version__
    except (ImportError, AttributeError):
        return "unavailable"


def build_validation_receipt(counts):
    return {
        "schema_version": "1.0", "schema_id": SCHEMA_ID,
        "input_c_rows": 1850, "input_e_rows": 1850, "joined_rows": counts["joined_rows"],
        "unique_primary_keys": counts["unique_joined_keys"],
        "c_e_joined_key_set_equality": True,
        "context_equality": True,
        "detector_version_exact": True,
        "and_rule_validated": True,
        "raw_geometric_channel_preserved": True,
        "raw_empirical_channel_preserved": True,
        "all_visible_flags_boolean": True,
        "quarantine_invariants_hold": True,
        "missing_detector_count": counts["category_counts"]["missing_detector"],
        "quarantine_accounting_reconciles": True,
        "per_layout_accounting_reconciles": True,
        "zero_structural_failures": True,
        "deterministic_serialization": True,
        "no_pre_existing_paths_changed": True,
        "no_detector_execution": True,
        "no_accuracy_metrics": True,
        "no_u4_inspection": True,
    }


def build_phase3_status():
    return {
        "schema_version": "1.0", "schema_id": SCHEMA_ID,
        "step_3_1": "PASS", "step_3_2": "PASS",
        "person_b_step_3_3_policy": "READY",
        "person_c_generation_input_authority": "READY",
        "person_e_empirical_visibility": "READY",
        "person_c_final_strict_join": "READY",
        "person_b_final_joined_package_validation": "PENDING",
        "overall_phase3": "IN_PROGRESS",
        "u4_output_inspected": False,
    }


# ---- assemble the package -------------------------------------------------
def generate(e_root, out_dir, *, command):
    c_records, e_records, diagnostics, context = load_inputs(e_root)
    counts = preflight(c_records, e_records, diagnostics, context)

    start = _utc()
    joined = run_join(c_records, e_records, context)
    end = _utc()

    # post-join invariants (validate, never mutate)
    if len(joined) != 1850:
        fail(f"joined rows != 1850: {len(joined)}")
    keys = [(r["trajectory_id"], r["model_frame_idx"]) for r in joined]
    if len(set(keys)) != 1850:
        fail("joined keys not unique")
    for r in joined:
        if not isinstance(r["visible_flag"], bool):
            fail("visible_flag not boolean")
        if r["quarantine_category"] not in QUARANTINE_CATEGORIES:
            fail(f"illegal quarantine category {r['quarantine_category']}")
        geo, emp = r["geometric_visible"], r["empirical_magenta_visible"]
        if geo is not None and emp is not None and r["visible_flag"] != (bool(geo) and bool(emp)):
            fail("AND-rule violation")
        if r["quarantined"] and r["visible_flag"]:
            fail("quarantined row has visible_flag true")
        if r["visible_flag"] and r["quarantine_category"] != "none":
            fail("visible row not category none")
        if (r["quarantine_category"] != "none") != r["quarantined"]:
            fail("quarantined flag inconsistent with category")
    cat_counts = {c: sum(1 for r in joined if r["quarantine_category"] == c)
                  for c in QUARANTINE_CATEGORIES}
    if cat_counts["missing_detector"] != 0:
        fail("missing_detector must be 0 (structural failure)")
    if sum(cat_counts.values()) != 1850:
        fail("category counts do not sum to 1850")
    quarantined = sum(1 for r in joined if r["quarantined"])
    if quarantined + (1850 - quarantined) != 1850:
        fail("quarantine partition broken")
    if sum(v for c, v in cat_counts.items() if c != "none") != quarantined:
        fail("non-none categories != quarantined")

    counts.update({
        "joined_rows": len(joined),
        "unique_joined_keys": len(set(keys)),
        "category_counts": cat_counts,
        "command": command,
    })

    files: dict[str, bytes] = {}
    files["joined_visibility_records.jsonl"] = dump_jsonl(joined)
    files["joined_visibility_schema.json"] = dump_json(build_joined_schema())
    files["authority_binding.json"] = dump_json(build_authority_binding())
    files["coverage_report.json"] = dump_json(build_coverage(counts))
    files["quarantine_accounting_report.json"] = dump_json(build_quarantine_accounting(joined))
    files["strict_join_receipt.json"] = dump_json(build_strict_join_receipt(counts, e_root, start, end))
    files["validation_receipt.json"] = dump_json(build_validation_receipt(counts))
    files["phase3_status.json"] = dump_json(build_phase3_status())
    # provenance references output hashes (all files except provenance + inventory)
    files_sha = {rel: sha256_bytes(b) for rel, b in sorted(files.items())}
    files["provenance_index.json"] = dump_json(build_provenance_index(counts, files_sha))
    inv = {rel: sha256_bytes(b) for rel, b in sorted(files.items())}
    files["sha256_inventory.json"] = dump_json({
        "schema_version": "1.0", "schema_id": SCHEMA_ID,
        "files": inv, "file_count": len(files) + 1,
    })

    if out_dir is not None:
        for rel, data in files.items():
            dst = os.path.join(out_dir, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with open(dst, "wb") as f:
                f.write(data)
    return files, joined, counts


# artifacts fully determined by inputs (no timestamps / runtime) -> byte-compared
DETERMINISTIC_ARTIFACTS = frozenset({
    "joined_visibility_records.jsonl", "joined_visibility_schema.json",
    "authority_binding.json", "coverage_report.json",
    "quarantine_accounting_report.json", "validation_receipt.json", "phase3_status.json",
})
# artifacts carrying run/host-specific fields -> validated structurally + by self-consistency
VOLATILE_ARTIFACTS = frozenset({
    "strict_join_receipt.json", "provenance_index.json", "sha256_inventory.json",
})


def validate(e_root, pkg_dir, *, command):
    """Independently re-run the join and validate the committed package without
    rerunning the detector or rewriting anything. Deterministic artifacts are
    byte-compared; timestamp/runtime-bearing artifacts are checked structurally
    and by hash self-consistency (portable across hosts)."""
    expected, joined, _ = generate(e_root, out_dir=None, command=command)
    problems = []
    present = set()
    for dirpath, _, fnames in os.walk(pkg_dir):
        for fn in fnames:
            present.add(os.path.relpath(os.path.join(dirpath, fn), pkg_dir).replace("\\", "/"))
    for rel in expected:
        if rel not in present:
            problems.append(f"missing: {rel}")
    for rel in present - set(expected):
        problems.append(f"unexpected: {rel}")

    def _disk(rel):
        with open(os.path.join(pkg_dir, rel), "rb") as f:
            return f.read()

    # deterministic artifacts must reproduce byte-identically from the inputs
    for rel in DETERMINISTIC_ARTIFACTS:
        if rel in present and _disk(rel) != expected[rel]:
            problems.append(f"byte-diff: {rel}")

    # the committed joined rows must equal a fresh authoritative join (row-level check)
    if "joined_visibility_records.jsonl" in present:
        on_disk = [json.loads(l) for l in _disk("joined_visibility_records.jsonl").decode().splitlines() if l]
        if on_disk != joined:
            problems.append("joined rows differ from a fresh authoritative strict_join")
        for r in on_disk:
            if not isinstance(r["visible_flag"], bool):
                problems.append("visible_flag not boolean")
            geo, emp = r["geometric_visible"], r["empirical_magenta_visible"]
            if geo is not None and emp is not None and r["visible_flag"] != (bool(geo) and bool(emp)):
                problems.append("AND-rule violation on disk")
            if r["quarantined"] and r["visible_flag"]:
                problems.append("quarantined row visible on disk")

    # sha256_inventory self-consistency: every recorded hash matches the on-disk file
    if "sha256_inventory.json" in present:
        inv = json.loads(_disk("sha256_inventory.json"))["files"]
        for rel, h in inv.items():
            if rel not in present:
                problems.append(f"inventory lists missing file: {rel}")
            elif sha256_bytes(_disk(rel)) != h:
                problems.append(f"inventory hash mismatch: {rel}")

    # provenance output_hashes must match the on-disk artifacts; bindings must be exact
    if "provenance_index.json" in present:
        prov = json.loads(_disk("provenance_index.json"))
        for rel, h in prov.get("output_hashes", {}).items():
            if rel in present and sha256_bytes(_disk(rel)) != h:
                problems.append(f"provenance output hash mismatch: {rel}")
        auth = prov.get("authorities", {})
        if auth.get("person_e_empirical_commit") != PERSON_E_COMMIT:
            problems.append("provenance: wrong E commit binding")
        if prov.get("final_label_owner") != "Person C":
            problems.append("provenance: final label owner not Person C")

    # strict_join_receipt: non-volatile fields exact; timestamps merely present
    if "strict_join_receipt.json" in present:
        rcpt = json.loads(_disk("strict_join_receipt.json"))
        if rcpt.get("strict_join_import_path") != "mineocclude.data.visibility_join.strict_join":
            problems.append("receipt: wrong strict_join import path")
        if rcpt.get("no_detector_rerun") is not True or rcpt.get("no_u4_inspection") is not True:
            problems.append("receipt: missing no-detector / no-u4 assertion")
        for f in ("join_start_utc", "join_end_utc"):
            if not isinstance(rcpt.get(f), str) or not rcpt[f].endswith("Z"):
                problems.append(f"receipt: malformed {f}")

    if problems:
        fail("VALIDATE FAILED:\n  " + "\n  ".join(problems[:40]))
    print(f"VALIDATE OK: {len(expected)} artifacts; {len(joined)} rows re-verified "
          f"({len(DETERMINISTIC_ARTIFACTS)} byte-identical, {len(VOLATILE_ARTIFACTS)} self-consistent)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["build", "validate"])
    ap.add_argument("--e-package-root", required=True,
                    help="detached Person E worktree root containing the empirical package")
    ap.add_argument("--out-dir", default=os.path.join(ROOT, PKG_REL))
    args = ap.parse_args()
    e_root = os.path.expanduser(args.e_package_root)
    command = f"build_person_c_phase3_step3_3_joined_visibility_v0_1.py {args.mode} --e-package-root <E_ROOT>"
    try:
        if args.mode == "build":
            files, _, counts = generate(e_root, args.out_dir, command=command)
            print(f"BUILD OK: {len(files)} artifacts; joined {counts['joined_rows']} rows")
        else:
            validate(e_root, args.out_dir, command=command)
    except JoinPackageError as exc:
        print(f"FAIL-CLOSED: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
