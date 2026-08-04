#!/usr/bin/env python3
"""Deliverable 2: homography sign & applicability authority (Person C -> E Phase 3).

Owner-authored ground truth for the world-axis sign and applicability domain.
The known-direction movement is taken from C's server world state (geometry),
NOT from Person E's homography output. C supplies authority + ground truth;
E performs and publishes the validation. Deterministic JSON.
"""
from __future__ import annotations

import fnmatch
import hashlib
import io
import json
import os
import subprocess

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data/handoff_e/phase3_homography_authority_v0_1")
SCHEMA_VERSION = "1.0"
PACKAGE_ID = "person-c-phase3-homography-authority-v0_1"
LAYOUTS = [f"layout_0{i}" for i in range(1, 7)]
MARKER_ORDER = ["north_west", "north_east", "south_east", "south_west"]

# Immutable frozen authority-input revision. All input discovery/reads bind to
# THIS Git object, never the current HEAD/working tree, so the committed
# authority artifacts regenerate byte-identically from any descendant commit.
SOURCE_REVISION = "fa70424530f422a2e6140e0e90d0ff18f583141e"


class SourceBindingError(Exception):
    """Fail-closed error when the frozen source input cannot be resolved."""


def _resolve(rev: str) -> None:
    try:
        subprocess.run(["git", "-C", ROOT, "rev-parse", "--verify", f"{rev}^{{commit}}"],
                       check=True, capture_output=True)
    except subprocess.CalledProcessError as exc:
        raise SourceBindingError(f"source revision {rev} is not resolvable") from exc


def _cat(rev: str, path: str) -> bytes:
    """Exact bytes of `path` at Git revision `rev`; fail closed if missing."""
    try:
        return subprocess.run(["git", "-C", ROOT, "cat-file", "blob", f"{rev}:{path}"],
                              check=True, capture_output=True).stdout
    except subprocess.CalledProcessError as exc:
        raise SourceBindingError(f"required object {rev}:{path} is missing") from exc


def _sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _exists_at(rev: str, path: str) -> bool:
    return subprocess.run(["git", "-C", ROOT, "cat-file", "-e", f"{rev}:{path}"],
                          check=False, capture_output=True).returncode == 0


def _layouts(rev: str) -> dict:
    data = json.loads(_cat(rev, "configs/scenes/layouts.yaml"))
    return {l["layout_id"]: l for l in data["layouts"]}


def _layout_frame_maps(rev: str, layout: str) -> list[str]:
    names = subprocess.run(
        ["git", "-C", ROOT, "ls-tree", "-r", "--name-only", rev, "--", "data/autonomous"],
        check=True, capture_output=True).stdout.decode().splitlines()
    return sorted(n for n in names
                  if fnmatch.fnmatch(n, f"data/autonomous/{layout}_ep*/frame_map.parquet"))


def visible_capture_for(rev: str, layout: str, wall_parallel_axis: str) -> tuple[str, str] | None:
    """A capture for this layout (at `rev`) whose sheep sweeps the widest visible
    span along the wall-parallel axis, so the known-direction displacement is far
    above the localization noise floor. Prefers NO_WALL controls (sheep fully
    visible / unoccluded => long monotonic sweep); falls back to NORMAL."""
    axcol = "sheep_x" if wall_parallel_axis == "x" else "sheep_z"
    best = None  # (weight, rel, scene, span)
    for rel in _layout_frame_maps(rev, layout):
        fm = pd.read_parquet(io.BytesIO(_cat(rev, rel)))
        scene = str(fm["scene"].iloc[0])
        if scene not in ("NO_WALL", "NORMAL"):
            continue
        vis = fm[fm["geometric_visible"] == True]
        if len(vis) < 2:
            continue
        span = float(vis[axcol].max() - vis[axcol].min())
        # NO_WALL preferred: a large scene-priority weight guarantees it wins when present
        weight = span + (1000.0 if scene == "NO_WALL" else 0.0)
        if best is None or weight > best[0]:
            best = (weight, rel, scene, span)
    return (best[1], best[2]) if best else None


def known_direction_record(rev: str, layout: str, wall_parallel_axis: str) -> dict | None:
    found = visible_capture_for(rev, layout, wall_parallel_axis)
    if found is None:
        return None
    rel, scene = found
    fmp = rel
    fm = pd.read_parquet(io.BytesIO(_cat(rev, rel))).sort_values("model_frame_idx").reset_index(drop=True)
    vis = fm[fm["geometric_visible"] == True].reset_index(drop=True)
    if len(vis) < 2:
        return None
    axcol = "sheep_x" if wall_parallel_axis == "x" else "sheep_z"
    # before = first visible frame; after = the visible frame furthest from it
    # along the axis -> the largest, unambiguously-signed displacement.
    a = vis.iloc[0]
    j = int((vis[axcol] - float(a[axcol])).abs().idxmax())
    b = vis.iloc[j]
    disp = float(b[axcol]) - float(a[axcol])
    def pos(row):
        return {"x": float(row["sheep_x"]), "y": float(row["sheep_y"]), "z": float(row["sheep_z"])}
    def ident(row):
        return {"trajectory_id": str(row["trajectory_id"]),
                "model_frame_idx": int(row["model_frame_idx"]),
                "render_frame_idx": int(row["render_frame_idx"]),
                "frame_640_sha256": (None if pd.isna(row.get("frame_640_sha256"))
                                     else str(row.get("frame_640_sha256")))}
    return {
        "layout_id": layout, "wall_parallel_axis": wall_parallel_axis,
        "units": "blocks",
        "capture_scene": scene,
        "controlled_condition": ("NO_WALL positive control: sheep fully visible / unoccluded, "
                                 "so it sweeps a long monotonic span"
                                 if scene == "NO_WALL" else
                                 "NORMAL scene visible-window sweep"),
        "before": {"identity": ident(a), "world_position": pos(a)},
        "after": {"identity": ident(b), "world_position": pos(b)},
        "expected_signed_displacement_blocks": round(disp, 6),
        "expected_direction": ("positive" if disp > 0 else "negative"),
        "displacement_exceeds_localization_noise": abs(disp) >= 0.5,
        "truth_source": "person_c_server_world_state",
        "detector_output_used_to_define_direction": False,
        "source_frame_map": fmp,
        "source_frame_map_sha256": _sha256_bytes(_cat(rev, rel)),
        "source_revision": rev,
    }


def marker_binding(rev: str, layout: str) -> dict:
    rel = f"data/handoff_e/markers_layout_{layout[-2:]}.json"
    blob = _cat(rev, rel)
    mk = json.loads(blob)
    by_role = {m["marker_role"]: m for m in mk["marker_correspondences"]}
    return {
        "layout_id": layout,
        "canonical_camera_pose_id": f"{layout}_canonical_pose_v1",
        "capture_resolution": {"width": 640, "height": 360},
        "image_coordinate_convention": "pixel_center_xy_zero_based",
        "world_coordinate_convention": "ground_plane_world_xz_blocks_topface_centre",
        "marker_source_record": rel,
        "marker_source_sha256": _sha256_bytes(blob),
        "marker_source_committed": _exists_at(rev, rel),
        "marker_order": MARKER_ORDER,
        "binding_note": ("this marker set is valid ONLY at this layout_id + "
                         "canonical_camera_pose_id + 640x360 + these conventions; "
                         "any differing context is out of domain (fail closed)"),
        "markers": [{
            "marker_role": role, "marker_color": by_role[role]["marker_color"],
            "world_xz_blocks": by_role[role]["world_xz_blocks"],
            "world_point_convention": by_role[role].get("world_point_convention",
                                                         "block_top_face_centre"),
        } for role in MARKER_ORDER],
    }


def build_all(source_revision: str = SOURCE_REVISION):
    _resolve(source_revision)
    head = source_revision
    layouts = _layouts(source_revision)
    wall_parallel = {}
    for lay in LAYOUTS:
        wall_parallel[lay] = layouts[lay]["lane"]["axis"]  # sheep travels parallel to the wall

    manifest = {
        "schema_version": SCHEMA_VERSION, "package_id": PACKAGE_ID, "owner": "Person C",
        "layout_ids": LAYOUTS,
        "canonical_camera_pose_ids": {l: f"{l}_canonical_pose_v1" for l in LAYOUTS},
        "capture_resolution": {"width": 640, "height": 360},
        "image_coordinate_convention": "pixel_center_xy_zero_based",
        "world_coordinate_convention": "ground_plane_world_xz_blocks_topface_centre",
        "marker_identities_and_ordering": MARKER_ORDER,
        "units": "blocks",
        "applicability_limits": {
            "layout_id": "must equal the record's layout_id",
            "canonical_camera_pose_id": "must equal the record's pose id",
            "resolution": "exactly 640x360",
            "crop": "no crop; full frame",
            "scaling": "no rescaling of the source 640x360 frame",
            "camera": "the canonical validated capture pose only",
            "coordinate_convention": "image pixel_center_xy_zero_based + world topface-centre",
        },
        "fail_closed_requirement": (
            "If layout_id, canonical_camera_pose_id, resolution, crop, scaling, camera, or "
            "coordinate convention differs from these bindings, the homography is OUT OF "
            "DOMAIN and must be rejected fail-closed - no extrapolated application."),
        "refit_disclaimer": ("Person C does not refit or alter Person E's matrices. C supplies "
                             "axis-sign authority and ground truth; E performs and publishes "
                             "the validation."),
    }
    sign = {
        "schema_version": SCHEMA_VERSION, "package_id": PACKAGE_ID, "owner": "Person C",
        "units": "blocks",
        "wall_parallel_axis_definition": (
            "The wall-parallel axis is the world axis the occluding wall runs along, which is "
            "the same axis the sheep validation lane runs along (the sheep travels parallel to "
            "the wall). Per layout it is the lane axis from configs/scenes/layouts.yaml."),
        "per_layout": {lay: {
            "wall_parallel_axis": wall_parallel[lay],
            "positive_direction": f"increasing {wall_parallel[lay]}",
            "negative_direction": f"decreasing {wall_parallel[lay]}",
        } for lay in LAYOUTS},
        "detector_output_used_to_define_direction": False,
    }
    kdr = {
        "schema_version": SCHEMA_VERSION, "package_id": PACKAGE_ID, "owner": "Person C",
        "note": ("Owner-authored controlled known-direction movements from Person C server "
                 "world state. Each establishes the wall-parallel sign INDEPENDENTLY of Person "
                 "E's measured localization errors. Detector output was NOT used."),
        "records": [r for r in (known_direction_record(head, lay, wall_parallel[lay])
                                for lay in LAYOUTS) if r is not None],
    }
    bindings = {
        "schema_version": SCHEMA_VERSION, "package_id": PACKAGE_ID, "owner": "Person C",
        "per_layout": [marker_binding(head, lay) for lay in LAYOUTS],
        "source_revision": head,
    }
    files = {}
    def canon(o): return (json.dumps(o, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
    files["homography_applicability_manifest.json"] = canon(manifest)
    files["wall_axis_sign_authority.json"] = canon(sign)
    files["known_direction_validation_records.json"] = canon(kdr)
    files["marker_pose_resolution_bindings.json"] = canon(bindings)
    files["homography_authority_receipt.json"] = canon({
        "schema_version": SCHEMA_VERSION, "package_id": PACKAGE_ID, "owner": "Person C",
        "source_revision": head, "layout_count": len(LAYOUTS),
        "known_direction_record_count": len(kdr["records"]),
        "detector_output_used_to_define_direction": False,
        "person_c_did_not_refit_e_matrices": True,
        "file_sha256": {n: hashlib.sha256(b).hexdigest() for n, b in sorted(files.items())}})
    return files


def write_all(dest: str = OUT):
    os.makedirs(dest, exist_ok=True)
    for n, b in sorted(build_all().items()):
        with open(os.path.join(dest, n), "wb") as f:
            f.write(b)
    return sorted(build_all().keys())


if __name__ == "__main__":
    for n in write_all():
        print("wrote", n)
