#!/usr/bin/env python3
"""Deliverable 3: authoritative geometric-visibility output (Person C -> E Phase 3).

Regenerates the geometric-visibility dataset for the frozen regime-A production
trajectories using C's authoritative workflow (mineocclude.data.visibility.
compute_geometric_visibility) and final schema. No empirical/E-authored decision
is included. Deterministic (sorted by (trajectory_id, model_frame_idx)).
"""
from __future__ import annotations

import fnmatch
import hashlib
import io
import json
import os
import subprocess
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
import mineocclude.contracts  # noqa: F401  (imported for the import-order cycle side effect)
from mineocclude.data.visibility import GEOMETRY_RULE_VERSION

OUT = os.path.join(ROOT, "data/handoff_e/phase3_visibility_authority_v0_1")
SCHEMA_VERSION = "1.0"
DATASET_ID = "person-c-phase3-geometric-visibility-authority-v0_1"

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


def _layouts(rev: str) -> dict:
    data = json.loads(_cat(rev, "configs/scenes/layouts.yaml"))
    return {l["layout_id"]: l for l in data["layouts"]}


def regime_a_trajectories(rev: str) -> list[str]:
    """Discover the regime-A NORMAL-scene ep10xxx frame maps at `rev` (via Git,
    not the working tree). NO_SHEEP/NO_WALL controls are excluded."""
    names = subprocess.run(
        ["git", "-C", ROOT, "ls-tree", "-r", "--name-only", rev, "--", "data/autonomous"],
        check=True, capture_output=True).stdout.decode().splitlines()
    out = []
    for rel in sorted(names):
        if not fnmatch.fnmatch(rel, "data/autonomous/*_ep10*/frame_map.parquet"):
            continue
        meta = pd.read_parquet(io.BytesIO(_cat(rev, rel)), columns=["regime", "scene"])
        if str(meta["regime"].iloc[0]) == "A" and str(meta["scene"].iloc[0]) == "NORMAL":
            out.append(rel)
    if not out:
        raise SourceBindingError(f"no regime-A NORMAL frame maps found at {rev}")
    return out


def build_records(source_revision: str):
    _resolve(source_revision)
    records, srcs = [], {}
    for rel in regime_a_trajectories(source_revision):
        blob = _cat(source_revision, rel)
        srcs[rel] = _sha256_bytes(blob)
        fm = pd.read_parquet(io.BytesIO(blob))
        for col in ("trajectory_id", "model_frame_idx", "layout_id", "geometric_visible",
                    "render_frame_idx", "player_x", "sheep_x"):
            if col not in fm.columns:
                raise SourceBindingError(f"{rel} missing required column {col}")
        for _, r in fm.iterrows():
            # AUTHORITATIVE value = the server as-built geometric_visible stored at
            # capture (ground truth of the placed blocks), NOT a config recompute.
            gv_raw = r["geometric_visible"]
            valid = not (r["sheep_x"] is None or pd.isna(r["sheep_x"])
                         or gv_raw is None or (isinstance(gv_raw, float) and pd.isna(gv_raw)))
            if not valid:
                status, gv, reason = "invalid", None, "sheep_world_state_missing_or_nonfinite"
            else:
                gv = bool(gv_raw)
                status = "visible" if gv else "occluded"
                reason = None
            records.append({
                "schema_version": SCHEMA_VERSION,
                "trajectory_id": str(r["trajectory_id"]),
                "model_frame_idx": int(r["model_frame_idx"]),
                "rollout_id": None,
                "event_id": None,
                "layout_id": str(r["layout_id"]),
                "regime": "A",
                "scene": "NORMAL",
                "canonical_camera_pose_id": f"{r['layout_id']}_canonical_pose_v1",
                "render_frame_idx": int(r["render_frame_idx"]),
                "frame_640_sha256": (None if pd.isna(r.get("frame_640_sha256"))
                                     else str(r.get("frame_640_sha256"))),
                "geometric_visible": (None if gv is None or (isinstance(gv, float) and pd.isna(gv))
                                      else bool(gv)),
                "geometric_status": status,
                "geometric_validity": ("invalid" if status == "invalid" else "valid"),
                "geometry_rejection_reason": reason,
                "source_world_state": {
                    "player_x": float(r["player_x"]), "player_y": float(r["player_y"]),
                    "player_z": float(r["player_z"]),
                    "sheep_x": (None if pd.isna(r["sheep_x"]) else float(r["sheep_x"])),
                    "sheep_y": (None if pd.isna(r["sheep_y"]) else float(r["sheep_y"])),
                    "sheep_z": (None if pd.isna(r["sheep_z"]) else float(r["sheep_z"]))},
                "geometry_rule_version": GEOMETRY_RULE_VERSION,
                "source_revision": source_revision,
                "source_frame_map": rel,
                "source_frame_map_sha256": srcs[rel],
                "scientific_use": "authoritative_geometry_only",
                "test_only": False,
                "synthetic": False,
                "empirical_decision_present": False,
            })
    records.sort(key=lambda x: (x["trajectory_id"], x["model_frame_idx"]))
    return records, srcs


def build_schema() -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "dataset_id": DATASET_ID,
        "geometry_rule_version": GEOMETRY_RULE_VERSION,
        "identity_primary_key": ["trajectory_id", "model_frame_idx"],
        "record_format": "jsonl (one record per line, sorted by identity key)",
        "fields": {
            "trajectory_id": "str", "model_frame_idx": "int",
            "rollout_id": "str|null", "event_id": "str|null",
            "layout_id": "str", "canonical_camera_pose_id": "str",
            "render_frame_idx": "int", "frame_640_sha256": "str|null",
            "geometric_visible": "bool|null",
            "geometric_status": "enum[visible,occluded,boundary,invalid]",
            "geometric_validity": "enum[valid,invalid]",
            "geometry_rejection_reason": "str|null",
            "source_world_state": "object(player_xyz, sheep_xyz)",
            "geometry_rule_version": "str", "source_revision": "str",
            "source_frame_map": "str", "source_frame_map_sha256": "str",
            "scientific_use": "str", "test_only": "bool", "synthetic": "bool",
            "empirical_decision_present": "bool (always false; C geometry only)"},
        "owner": "Person C",
        "geometric_visible_source": ("server as-built geometric visibility stored at capture "
                                     "(ground truth of the placed blocks), produced by C's "
                                     "geometric rule; NOT a config-based recompute"),
        "geometric_status_derivation": ("invalid when sheep world state is missing/nonfinite; "
                                        "otherwise visible/occluded from the authoritative "
                                        "geometric_visible boolean"),
        "note": ("Geometric visibility only. No E-authored empirical decision is present; "
                 "empirical records arrive later through the formal integration interface "
                 "(final_visibility_interface)."),
    }


def canon(obj) -> bytes:
    return (json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


def jsonl(records) -> bytes:
    return ("".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n"
                    for r in records)).encode()


def build_all(source_revision: str = SOURCE_REVISION):
    records, srcs = build_records(source_revision)
    trajs = sorted({r["trajectory_id"] for r in records})
    from collections import Counter
    files = {}
    files["geometric_visibility_records.jsonl"] = jsonl(records)
    files["geometric_visibility_schema.json"] = canon(build_schema())
    files["visibility_identity_manifest.json"] = canon({
        "schema_version": SCHEMA_VERSION, "dataset_id": DATASET_ID,
        "identity_primary_key": ["trajectory_id", "model_frame_idx"],
        "record_count": len(records), "trajectory_count": len(trajs),
        "trajectories": trajs,
        "per_layout_record_counts": dict(sorted(Counter(r["layout_id"] for r in records).items())),
        "status_counts": dict(sorted(Counter(r["geometric_status"] for r in records).items())),
        "records_sha256": hashlib.sha256(files["geometric_visibility_records.jsonl"]).hexdigest()})
    files["provenance_index.json"] = canon({
        "schema_version": SCHEMA_VERSION, "dataset_id": DATASET_ID,
        "source_revision": source_revision, "geometry_rule_version": GEOMETRY_RULE_VERSION,
        "source_frame_maps": dict(sorted(srcs.items()))})
    files["visibility_authority_receipt.json"] = canon({
        "schema_version": SCHEMA_VERSION, "dataset_id": DATASET_ID,
        "owner": "Person C", "geometry_rule_version": GEOMETRY_RULE_VERSION,
        "source_revision": source_revision, "record_count": len(records),
        "trajectory_count": len(trajs), "empirical_decision_present": False,
        "generated_by_c_authoritative_workflow": True,
        "file_sha256": {n: hashlib.sha256(b).hexdigest()
                        for n, b in sorted(files.items())}})
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
