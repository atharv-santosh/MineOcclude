"""Build the additive Person C Phase 3 Step 3.3 generation-input authority.

This package is an *E generation-input* authority, not a final visibility
package. It repackages the already-recovered canonical 640x360 PNG bytes into 56
deterministic per-trajectory tar.gz archives and emits the identity / context /
provenance / validation authorities Person E needs to bind detector inputs.

It never modifies any pre-existing path, never runs a detector, never reads
detector-result columns, never writes empirical_magenta_visible or visible_flag,
and never inspects U4. Frame selection and truth are Person C geometry only.

Modes:
  build     regenerate the package under the authorized directory
  validate  verify an already-generated package (no writes)

All frame maps are read with an explicit safe column set; detector columns are
never loaded.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
import sys
import tarfile

import pandas as pd
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEMA_ID = "person-c-phase3-step3-3-visibility-repair-v0-1"
PKG_REL = "data/handoff_e/phase3_visibility_repair_v0_1"
AUTH_REL = "data/handoff_e/phase3_visibility_authority_v0_1"
GVR_REL = f"{AUTH_REL}/geometric_visibility_records.jsonl"
PROV_REL = f"{AUTH_REL}/provenance_index.json"
HOMOG_REL = ("data/handoff_e/phase3_homography_authority_v0_1/"
             "homography_applicability_manifest.json")
IMPORT_CONTRACT_REL = ("data/handoff_e/phase3_visibility_interface_v0_1/"
                       "empirical_visibility_import_contract.json")
FINAL_INTERFACE_REL = ("data/handoff_e/phase3_visibility_interface_v0_1/"
                       "final_visibility_interface.json")

PERSON_C_CURRENT = "3ba6c091426a537d60c950dd1bb38f5fc02826d5"
PERSON_C_SOURCE = "fa70424530f422a2e6140e0e90d0ff18f583141e"
GEOMETRIC_RECORDS_SHA = "914a5bee842c92e707b94c6d58c91807681310ac6a393d18a06ba8dfa70572eb"
IMPORT_CONTRACT_SHA = "a286341bb157e6630d0b18adef26efc31ad97fc9e921cbbeca960974f3ce5f4c"
FINAL_INTERFACE_SHA = "fd9a68681b002c0c3652e4299691e55417c18bdd9ef0f69d351c96bfd8822730"
PERSON_B_POLICY = "eec9396e6a93feaab3d5d298ac7cdc4cb54fdbd4"
PERSON_E_DETECTOR_AUTH = "bfe7d55acc1fcf0b90aca5c152672070b15e6ee7"
DETECTOR_VERSION = ("hsv-largest-valid-blob-v1.0-candidate:sha256:"
                    "0cadf618fca1578196bde4982021c38627ccb9c39e46353812e7da3fce6aa125")
DETECTOR_IDENTITY = "0cadf618fca1578196bde4982021c38627ccb9c39e46353812e7da3fce6aa125"

RESOLUTION_VALUE = "640x360"
COORD_VALUE = "pixel_center_xy_zero_based"

# only these frame-map columns are ever read; detector columns are excluded
SAFE_COLS = ["trajectory_id", "model_frame_idx", "render_frame_idx",
             "frame_640_path", "frame_640_sha256", "detector_frame_space"]
ARCHIVE_MEMBER_MODE = 0o644


class FailClosed(Exception):
    pass


# --------------------------------------------------------------------------- #
# deterministic serialization helpers
# --------------------------------------------------------------------------- #
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


def read_bytes(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()


def load_json_path(path: str):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def read_lines(path: str) -> list[str]:
    with open(path, encoding="utf-8") as f:
        return [l for l in f if l.strip()]


def canonical_relative_path(rel: str) -> str:
    """Map a local-filesystem relative path to its POSIX manifest form.

    Separator normalization only: Windows "\\" becomes canonical "/". Absolute
    paths and ".." traversal components are preserved verbatim (never collapsed
    or stripped), so an unsafe path is never silently turned into a valid
    package-relative key -- it simply fails to match any expected manifest path.
    """
    return rel.replace("\\", "/")


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_file(abspath: str, data: bytes) -> None:
    os.makedirs(os.path.dirname(abspath), exist_ok=True)
    with open(abspath, "wb") as f:
        f.write(data)


# --------------------------------------------------------------------------- #
# deterministic tar.gz
# --------------------------------------------------------------------------- #
def build_deterministic_archive(members: list[tuple[str, bytes]]) -> bytes:
    """members: list of (member_name, raw_bytes), already ordered."""
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w", format=tarfile.GNU_FORMAT) as tar:
        for name, data in members:
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            info.mtime = 0
            info.mode = ARCHIVE_MEMBER_MODE
            info.uid = 0
            info.gid = 0
            info.uname = ""
            info.gname = ""
            info.type = tarfile.REGTYPE
            tar.addfile(info, io.BytesIO(data))
    tar_bytes = raw.getvalue()
    gz = io.BytesIO()
    # mtime=0 and no embedded filename in the gzip header
    with gzip.GzipFile(filename="", mode="wb", fileobj=gz, mtime=0) as g:
        g.write(tar_bytes)
    return gz.getvalue()


# --------------------------------------------------------------------------- #
# authority loading (read-only, geometry/identity only)
# --------------------------------------------------------------------------- #
def load_records():
    path = os.path.join(ROOT, GVR_REL)
    if sha256_file(path) != GEOMETRIC_RECORDS_SHA:
        raise FailClosed("geometric_visibility_records.jsonl SHA-256 changed")
    return [json.loads(l) for l in read_lines(path)]


def load_provenance():
    return load_json_path(os.path.join(ROOT, PROV_REL))["source_frame_maps"]


def load_coord_convention():
    h = load_json_path(os.path.join(ROOT, HOMOG_REL))
    val = h.get("image_coordinate_convention")
    if val != COORD_VALUE:
        raise FailClosed(f"coordinate_convention source != {COORD_VALUE!r}: {val!r}")
    return val


def gather(source_root: str):
    """Read the 56 SHA-pinned frame maps and resolve every canonical PNG.

    Returns (rows, per_traj) where rows are the fully-resolved 1,850 entries and
    per_traj maps trajectory_id -> ordered list of member dicts.
    """
    recs = load_records()
    rec_keys = {(r["trajectory_id"], int(r["model_frame_idx"])): r for r in recs}
    prov = load_provenance()
    load_coord_convention()

    trajs = sorted({r["trajectory_id"] for r in recs})
    rows = []
    per_traj: dict[str, list] = {}
    seen_keys: set[tuple[str, int]] = set()

    for t in trajs:
        rel = f"data/autonomous/{t}/frame_map.parquet"
        abspath = os.path.join(ROOT, rel)
        if not os.path.exists(abspath):
            raise FailClosed(f"frame map missing: {rel}")
        disk_sha = sha256_file(abspath)
        if prov.get(rel) != disk_sha:
            raise FailClosed(f"frame-map SHA mismatch vs provenance: {rel}")
        df = pd.read_parquet(abspath, columns=SAFE_COLS)
        members = []
        for _, row in df.iterrows():
            traj = row["trajectory_id"]
            mfi = int(row["model_frame_idx"])
            key = (traj, mfi)
            if key in seen_keys:
                raise FailClosed(f"duplicate identity key: {key}")
            if key not in rec_keys:
                raise FailClosed(f"map key not in geometric records: {key}")
            seen_keys.add(key)
            rec = rec_keys[key]
            dfs = row["detector_frame_space"]
            if dfs != RESOLUTION_VALUE:
                raise FailClosed(f"detector_frame_space != {RESOLUTION_VALUE!r}: {dfs!r} for {key}")
            rfi = int(row["render_frame_idx"])
            member_name = f"frames_640x360/{rfi:06d}.png"
            # resolve the source PNG under the explicit source root
            declared = row["frame_640_path"]
            base = os.path.basename(declared)
            src = os.path.join(source_root, f"episode_{_episode_of(traj)}",
                               "frames_640x360", base)
            if not os.path.exists(src):
                # fall back to the declared absolute path if it exists
                if os.path.exists(declared):
                    src = declared
                else:
                    raise FailClosed(f"source PNG missing for {key}: {src}")
            raw = read_bytes(src)
            got = sha256_bytes(raw)
            if got != row["frame_640_sha256"]:
                raise FailClosed(f"source PNG hash mismatch for {key}: {src}")
            if got != rec.get("frame_640_sha256"):
                raise FailClosed(f"record vs map frame_640_sha256 mismatch for {key}")
            try:
                with Image.open(io.BytesIO(raw)) as im:
                    dims = im.size
            except Exception as exc:
                raise FailClosed(f"PNG decode failure for {key}: {exc}") from exc
            if dims != (640, 360):
                raise FailClosed(f"PNG not 640x360 for {key}: {dims}")
            members.append({
                "trajectory_id": traj, "model_frame_idx": mfi, "render_frame_idx": rfi,
                "layout_id": rec["layout_id"],
                "canonical_camera_pose_id": rec["canonical_camera_pose_id"],
                "member_name": member_name, "raw": raw, "sha256": got,
                "size": len(raw), "source_frame_map": rel, "source_frame_map_sha256": disk_sha,
            })
        members.sort(key=lambda m: m["render_frame_idx"])
        per_traj[t] = members
        rows.extend(members)

    if len(seen_keys) != 1850:
        raise FailClosed(f"expected 1850 keys, got {len(seen_keys)}")
    if seen_keys != set(rec_keys):
        raise FailClosed("derived key set != geometric-record key set")
    rows.sort(key=lambda m: (m["trajectory_id"], m["model_frame_idx"]))
    return rows, per_traj, prov


def _episode_of(trajectory_id: str) -> str:
    # trajectory_id like layout_01_ep10000 -> episode number 10000
    tok = trajectory_id.rsplit("_ep", 1)
    return tok[1] if len(tok) == 2 else trajectory_id


# --------------------------------------------------------------------------- #
# package build
# --------------------------------------------------------------------------- #
def _context_authority():
    return {
        "schema_version": "1.0",
        "schema_id": SCHEMA_ID,
        "owner": "Person C",
        "person_c_authorized": True,
        "resolution": {
            "source": "source_frame_map.detector_frame_space",
            "required_source_value": RESOLUTION_VALUE,
            "emitted_field": "resolution",
            "emitted_value": RESOLUTION_VALUE,
            "emitted_json_type": "string",
        },
        "coordinate_convention": {
            "source": (f"{HOMOG_REL}::image_coordinate_convention"),
            "required_source_value": COORD_VALUE,
            "emitted_field": "coordinate_convention",
            "emitted_value": COORD_VALUE,
            "emitted_json_type": "string",
        },
        "both_mappings_constant_across_all_six_layouts_and_1850_records": True,
        "no_competing_source_value_found": True,
        "person_e_may_copy_emitted_values_but_may_not_translate_or_substitute": True,
    }


def _identity_authority(prov, rows):
    maps = sorted({r["source_frame_map"] for r in rows})
    return {
        "schema_version": "1.0",
        "schema_id": SCHEMA_ID,
        "owner": "Person C",
        "identity_authority_mode": "OptionB_hash_bound_frame_maps_with_materialized_flat_inventory",
        "primary_key": ["trajectory_id", "model_frame_idx"],
        "source_frame_maps": [
            {"source_frame_map": m, "source_frame_map_sha256": prov[m]} for m in maps
        ],
        "deterministic_derivation": (
            "union of the (trajectory_id, model_frame_idx) key sets parsed from the "
            "56 SHA-256-bound frame maps listed above"),
        "no_duplicate_keys_required": True,
        "derived_key_count": 1850,
        "derived_key_set_bound_to_geometric_record_key_set": True,
        "exact_equality": True,
        "extra_keys": 0,
        "missing_keys": 0,
        "duplicate_keys": 0,
    }


def _provenance_index():
    return {
        "schema_version": "1.0",
        "schema_id": SCHEMA_ID,
        "person_c_current_authority": PERSON_C_CURRENT,
        "person_c_source_authority": PERSON_C_SOURCE,
        "geometric_records": {"path": GVR_REL, "sha256": GEOMETRIC_RECORDS_SHA},
        "person_c_empirical_import_contract": {"path": IMPORT_CONTRACT_REL, "sha256": IMPORT_CONTRACT_SHA},
        "person_c_final_interface": {"path": FINAL_INTERFACE_REL, "sha256": FINAL_INTERFACE_SHA},
        "person_b_policy": {"commit": PERSON_B_POLICY},
        "person_e_detector_authority": {
            "commit": PERSON_E_DETECTOR_AUTH,
            "detector_version": DETECTOR_VERSION,
            "detector_identity": DETECTOR_IDENTITY,
        },
    }


def _phase3_status():
    return {
        "schema_version": "1.0",
        "schema_id": SCHEMA_ID,
        "step_3_1": "PASS",
        "step_3_2": "PASS",
        "person_b_step_3_3_policy": "READY",
        "person_c_step_3_3_generation_input_authority": "READY",
        "person_e_empirical_generation": "PENDING",
        "person_c_final_strict_join": "PENDING",
        "person_b_final_joined_package_validation": "PENDING",
        "overall_phase3": "IN_PROGRESS",
        "u4_output_inspected": False,
    }


def _schemas():
    def obj(title, required):
        return {
            "schema_version": "1.0",
            "schema_id": SCHEMA_ID,
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "title": f"{SCHEMA_ID}:{title}",
            "type": "object",
            "required": required,
        }
    return {
        "generation_input_manifest.schema.json": obj("generation_input_manifest", [
            "trajectory_id", "model_frame_idx", "render_frame_idx", "layout_id",
            "canonical_camera_pose_id", "resolution", "coordinate_convention",
            "archive_path", "archive_member_path", "archive_sha256", "frame_640_sha256",
            "frame_size_bytes", "source_frame_map", "source_frame_map_sha256"]),
        "derived_identity_manifest.schema.json": obj("derived_identity_manifest", [
            "trajectory_id", "model_frame_idx", "source_frame_map", "source_frame_map_sha256"]),
        "context_field_derivation_authority.schema.json": obj(
            "context_field_derivation_authority", ["resolution", "coordinate_convention"]),
        "identity_authority.schema.json": obj("identity_authority", [
            "primary_key", "source_frame_maps", "derived_key_count", "exact_equality"]),
        "archive_inventory.schema.json": obj("archive_inventory", [
            "archives", "archive_count", "member_count"]),
        "provenance_index.schema.json": obj("provenance_index", [
            "person_c_current_authority", "geometric_records", "person_e_detector_authority"]),
        "validation_receipt.schema.json": obj("validation_receipt", [
            "source_pngs_recovered", "exact_png_byte_hash_matches"]),
        "phase3_status.schema.json": obj("phase3_status", ["overall_phase3"]),
    }


def generate(source_root: str, out_dir: str):
    rows, per_traj, prov = gather(source_root)

    files: dict[str, bytes] = {}  # package-relative path -> bytes

    # 56 deterministic archives
    archives = []
    for t in sorted(per_traj):
        members = per_traj[t]
        arch = build_deterministic_archive([(m["member_name"], m["raw"]) for m in members])
        rel = f"canonical_frames/{t}_frames_640x360.tar.gz"
        files[rel] = arch
        archives.append({
            "trajectory_id": t,
            "archive_path": rel,
            "archive_sha256": sha256_bytes(arch),
            "archive_size_bytes": len(arch),
            "member_count": len(members),
            "first_render_frame_idx": members[0]["render_frame_idx"],
            "last_render_frame_idx": members[-1]["render_frame_idx"],
            "total_uncompressed_member_bytes": sum(m["size"] for m in members),
        })
    arch_by_traj = {a["trajectory_id"]: a for a in archives}

    # generation_input_manifest.jsonl
    gen_rows = []
    for m in rows:
        a = arch_by_traj[m["trajectory_id"]]
        gen_rows.append({
            "trajectory_id": m["trajectory_id"],
            "model_frame_idx": m["model_frame_idx"],
            "render_frame_idx": m["render_frame_idx"],
            "layout_id": m["layout_id"],
            "canonical_camera_pose_id": m["canonical_camera_pose_id"],
            "resolution": RESOLUTION_VALUE,
            "coordinate_convention": COORD_VALUE,
            "archive_path": a["archive_path"],
            "archive_member_path": m["member_name"],
            "archive_sha256": a["archive_sha256"],
            "frame_640_sha256": m["sha256"],
            "frame_size_bytes": m["size"],
            "source_frame_map": m["source_frame_map"],
            "source_frame_map_sha256": m["source_frame_map_sha256"],
        })
    files["generation_input_manifest.jsonl"] = dump_jsonl(gen_rows)

    # derived_identity_manifest.jsonl
    ident_rows = [{
        "trajectory_id": m["trajectory_id"],
        "model_frame_idx": m["model_frame_idx"],
        "source_frame_map": m["source_frame_map"],
        "source_frame_map_sha256": m["source_frame_map_sha256"],
    } for m in rows]
    files["derived_identity_manifest.jsonl"] = dump_jsonl(ident_rows)

    # authorities
    files["context_field_derivation_authority.json"] = dump_json(_context_authority())
    files["identity_authority.json"] = dump_json(_identity_authority(prov, rows))
    files["provenance_index.json"] = dump_json(_provenance_index())
    files["phase3_status.json"] = dump_json(_phase3_status())

    # per-layout counts
    per_layout: dict[str, int] = {}
    for m in rows:
        per_layout[m["layout_id"]] = per_layout.get(m["layout_id"], 0) + 1

    files["archive_inventory.json"] = dump_json({
        "schema_version": "1.0", "schema_id": SCHEMA_ID,
        "archives": archives,
        "archive_count": len(archives),
        "member_count": sum(a["member_count"] for a in archives),
        "total_unique_primary_keys": len({(m["trajectory_id"], m["model_frame_idx"]) for m in rows}),
        "missing_members": 0, "extra_members": 0,
        "duplicate_identity_members": 0, "member_hash_mismatches": 0,
        "per_layout_counts": per_layout,
    })

    files["validation_receipt.json"] = dump_json({
        "schema_version": "1.0", "schema_id": SCHEMA_ID,
        "source_pngs_recovered": 1850,
        "exact_png_byte_hash_matches": 1850,
        "missing_pngs": 0, "png_hash_mismatches": 0, "decode_failures": 0,
        "wrong_dimensions": 0, "all_decoded_dimensions_640x360": True,
        "frame_maps_verified": 56, "frame_map_hashes_verified": 56,
        "map_keys": 1850, "unique_map_keys": 1850,
        "exact_record_map_key_set_equality": True,
        "context_mappings_constant_and_unambiguous": True,
        "no_existing_artifact_modified": True,
        "no_recapture": True,
        "no_png_regeneration_or_reencoding": True,
        "no_detector_execution": True,
        "no_empirical_records": True,
        "no_visible_flag": True,
        "no_u4_inspection": True,
    })

    # schemas
    for name, schema in _schemas().items():
        files[f"schemas/{name}"] = dump_json(schema)

    # sha256_inventory over every package file (excluding itself)
    inv = {rel: sha256_bytes(data) for rel, data in sorted(files.items())}
    files["sha256_inventory.json"] = dump_json({
        "schema_version": "1.0", "schema_id": SCHEMA_ID,
        "files": inv,
        "archive_count": len(archives),
        "package_file_count": len(files) + 1,
    })

    if out_dir is not None:
        for rel, data in files.items():
            write_file(os.path.join(out_dir, rel), data)
    return files


# --------------------------------------------------------------------------- #
# validate-only mode
# --------------------------------------------------------------------------- #
def validate(source_root: str, pkg_dir: str):
    expected = generate(source_root, out_dir=None)
    problems = []
    for rel, data in expected.items():
        p = os.path.join(pkg_dir, rel)
        if not os.path.exists(p):
            problems.append(f"missing: {rel}")
            continue
        if read_bytes(p) != data:
            problems.append(f"byte-diff: {rel}")
    # extra files on disk
    for dirpath, _, fnames in os.walk(pkg_dir):
        for fn in fnames:
            rel = canonical_relative_path(os.path.relpath(os.path.join(dirpath, fn), pkg_dir))
            if rel not in expected:
                problems.append(f"unexpected: {rel}")
    # extract archives and re-verify member hashes + dims
    gen = [json.loads(l) for l in read_lines(os.path.join(pkg_dir, "generation_input_manifest.jsonl"))]
    by_arch: dict[str, list] = {}
    for r in gen:
        by_arch.setdefault(r["archive_path"], []).append(r)
    members_checked = 0
    for arch_rel, grp in by_arch.items():
        with tarfile.open(os.path.join(pkg_dir, arch_rel), "r:gz") as tar:
            got = {ti.name: tar.extractfile(ti).read() for ti in tar.getmembers()}
        for r in grp:
            b = got.get(r["archive_member_path"])
            if b is None:
                problems.append(f"member missing: {r['archive_member_path']} in {arch_rel}")
                continue
            if sha256_bytes(b) != r["frame_640_sha256"]:
                problems.append(f"member hash mismatch: {arch_rel}/{r['archive_member_path']}")
            with Image.open(io.BytesIO(b)) as im:
                if im.size != (640, 360):
                    problems.append(f"member wrong dims: {arch_rel}/{r['archive_member_path']}")
            members_checked += 1
    if members_checked != 1850:
        problems.append(f"members checked {members_checked} != 1850")
    if problems:
        raise FailClosed("VALIDATE FAILED:\n  " + "\n  ".join(problems[:40]))
    print(f"VALIDATE OK: {len(expected)} files, {members_checked} members verified")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["build", "validate"])
    ap.add_argument("--source-root", required=True,
                    help="canonical source root, e.g. ~/mineocclude-client/mineocclude_client_out")
    ap.add_argument("--out-dir", default=os.path.join(ROOT, PKG_REL))
    args = ap.parse_args()
    source_root = os.path.expanduser(args.source_root)
    try:
        if "mineocclude_u4" in source_root or "/u4" in source_root.lower():
            raise FailClosed("U4 source root is forbidden")
        if args.mode == "build":
            files = generate(source_root, args.out_dir)
            print(f"BUILD OK: wrote {len(files)} package files to {args.out_dir}")
        else:
            validate(source_root, args.out_dir)
    except FailClosed as exc:
        print(f"FAIL-CLOSED: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
