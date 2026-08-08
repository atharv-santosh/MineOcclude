#!/usr/bin/env python3
"""Deterministic generator for the Person C -> Person E Phase 3 Detector v1
UNTOUCHED-TEST predeclaration (PREDECLARATION ONLY - no image bytes).

Binds to Person E's frozen candidate (commit
3930669eddc026ecb081e947f71f1855a7415904) and emits six canonical JSON files
under data/handoff_e/phase3_detector_v1_untouched_test_v0_1/. Byte-identical on
every run (sorted keys, LF, no BOM, no wall-clock).
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG_DIR = os.path.join(ROOT, "data/handoff_e/phase3_detector_v1_untouched_test_v0_1")

# ---- Person E frozen-candidate binding (from detector_candidate_version_record) ----
E_FREEZE_COMMIT = "3930669eddc026ecb081e947f71f1855a7415904"
E_REQUIREMENTS_PATH = ("docs/status/person_e_phase3_step3_1_candidate_freeze_v0_1/"
                       "new_untouched_test_requirements.json")
DETECTOR_VERSION = ("hsv-largest-valid-blob-v1.0-candidate:sha256:"
                    "0cadf618fca1578196bde4982021c38627ccb9c39e46353812e7da3fce6aa125")
DETECTOR_IDENTITY_SHA256 = "0cadf618fca1578196bde4982021c38627ccb9c39e46353812e7da3fce6aa125"
DETECTOR_CONFIG_SHA256 = "acfecd659958891eaee0d582c946abdfaaf47d1ab3307a24f7652e634c045bfa"
DETECTOR_SETTINGS_SHA256 = "0dbb426adf99f53455eea04c4aaeb56f3cb22cbc351d87269bb605445eb8f2ea"
DETECTOR_IMPLEMENTATION_SHA256 = "026f3b9f25c8aef7ac43fada5b8de92662b605af4868f930698651e59a228214"
FREEZE_TIMESTAMP_UTC = "2026-07-28T06:03:15Z"
E_DEV_SOURCE_REVISION = "fa70424530f422a2e6140e0e90d0ff18f583141e"

PACKAGE_ID = "person-c-phase3-detector-v1-untouched-test-v0_1"
PACKAGE_VERSION = "v0.1"
SCHEMA_VERSION = "1.0"
CAPTURE_SESSION_ID = "person-c-phase3-untouched-test-v0_1-session-01"

LAYOUTS = [f"layout_0{i}" for i in range(1, 7)]
WIDTH, HEIGHT = 640, 360
IMAGE_ENCODING = "png"
PIXEL_FORMAT = "rgb8"
COORDINATE_CONVENTION = "pixel_center_xy_zero_based"

# Reserved capture identities (NEW ranges, no overlap with any historical C id).
PRESENT_EPISODE = {lay: 51001 + 2 * i for i, lay in enumerate(LAYOUTS)}   # 51001,51003,...
ABSENT_EPISODE = {lay: 51002 + 2 * i for i, lay in enumerate(LAYOUTS)}    # 51002,51004,...
PRESENT_FRAME_INDICES = [3, 7, 11, 15]
ABSENT_FRAME_INDICES = [3, 7, 11, 15]

IMAGE_REGION_STRATA = ["region_1_left", "region_2_center_left",
                       "region_3_center_right", "region_4_right"]
PRESENT_SCENE_STRATA = ["sheep_open_ground", "sheep_near_marker",
                        "sheep_near_wall_edge", "sheep_lane_extreme"]
ABSENT_SCENE_STRATA = ["marker_adjacent", "wall_adjacent",
                       "open_background", "marker_and_wall"]


def _git_show(path_at_commit: str) -> bytes:
    return subprocess.check_output(["git", "-C", ROOT, "show", path_at_commit])


def forbidden_dev_hashes() -> list[str]:
    raw = _git_show(f"{E_FREEZE_COMMIT}:{E_REQUIREMENTS_PATH}")
    return sorted(json.loads(raw)["forbidden_development_source_sha256"])


def historical_c_episode_ids() -> list[int]:
    ids = set()
    auto = os.path.join(ROOT, "data/autonomous")
    if os.path.isdir(auto):
        for name in os.listdir(auto):
            for tok in name.replace("_", " ").split():
                if tok.startswith("ep") and tok[2:].isdigit():
                    ids.add(int(tok[2:]))
    prov = os.path.join(ROOT, "data/handoff_e/provenance_calibration_clean.json")
    if os.path.exists(prov):
        with open(prov, encoding="utf-8") as handle:
            trajectories = json.load(handle).get("trajectories", [])
        for t in trajectories:
            if isinstance(t.get("episode_id"), int):
                ids.add(t["episode_id"])
    return sorted(ids)


def _pose(layout: str) -> str:
    return f"{layout}_canonical_pose_v1"


def build_frames() -> list[dict]:
    frames = []
    for layout in LAYOUTS:
        for cls, present, ep, idxs, scene_strata in (
            ("present", True, PRESENT_EPISODE[layout], PRESENT_FRAME_INDICES, PRESENT_SCENE_STRATA),
            ("absent", False, ABSENT_EPISODE[layout], ABSENT_FRAME_INDICES, ABSENT_SCENE_STRATA),
        ):
            for i in range(4):
                frames.append({
                    "package_id": PACKAGE_ID,
                    "frame_id": f"{PACKAGE_ID}::{layout}::{cls}::{i:02d}",
                    "truth_class": cls,
                    "truth_present": present,
                    "layout_id": layout,
                    "canonical_camera_pose_id": _pose(layout),
                    "width": WIDTH,
                    "height": HEIGHT,
                    "image_encoding": IMAGE_ENCODING,
                    "pixel_format": PIXEL_FORMAT,
                    "coordinate_convention": COORDINATE_CONVENTION,
                    "image_region_stratum": IMAGE_REGION_STRATA[i],
                    "scene_element_stratum": scene_strata[i],
                    "reserved_capture_session_id": CAPTURE_SESSION_ID,
                    "reserved_episode_id": ep,
                    "reserved_frame_index": idxs[i],
                    "visible_negative_pairing_id": f"{PACKAGE_ID}::{layout}::pair::{i:02d}",
                    "planned_source_relative_path":
                        f"data/handoff_e/phase3_detector_v1_untouched_test_v0_1/"
                        f"frames/{cls}/{layout}/{i:02d}.png",
                    "test_only": True,
                    "detector_outcome_unavailable": True,
                })
    return frames


def _e_binding() -> dict:
    return {
        "person_e_freeze_commit": E_FREEZE_COMMIT,
        "detector_version": DETECTOR_VERSION,
        "detector_identity_sha256": DETECTOR_IDENTITY_SHA256,
        "detector_config_sha256": DETECTOR_CONFIG_SHA256,
        "detector_settings_sha256": DETECTOR_SETTINGS_SHA256,
        "detector_implementation_sha256": DETECTOR_IMPLEMENTATION_SHA256,
        "freeze_timestamp_utc": FREEZE_TIMESTAMP_UTC,
        "person_e_requirements_schema_version":
            "person-e-phase3-new-untouched-test-requirements-v1.0",
        "person_e_development_source_revision": E_DEV_SOURCE_REVISION,
    }


def build_predeclaration() -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "predeclaration_schema_version": "person-c-phase3-untouched-test-predeclaration-v1.0",
        "package_id": PACKAGE_ID,
        "package_version": PACKAGE_VERSION,
        "owner": "Person C",
        "consumer": "Person E",
        "mode": "predeclaration_only",
        "created_after_person_e_freeze": True,
        "person_e_candidate_binding": _e_binding(),
        "counts": {
            "total_frames": 48, "truth_present": 24, "truth_absent": 24,
            "layouts": 6, "present_per_layout": 4, "absent_per_layout": 4,
        },
        "resolution": {"width": WIDTH, "height": HEIGHT,
                       "pixel_format": PIXEL_FORMAT, "image_encoding": IMAGE_ENCODING,
                       "coordinate_convention": COORDINATE_CONVENTION},
        "canonical_camera_pose_ids": {lay: _pose(lay) for lay in LAYOUTS},
        "reserved_capture_session_id": CAPTURE_SESSION_ID,
        "reserved_episode_ids": {
            "present": {lay: PRESENT_EPISODE[lay] for lay in LAYOUTS},
            "absent": {lay: ABSENT_EPISODE[lay] for lay in LAYOUTS},
        },
        "no_image_bytes_created": True,
        "detector_outcomes_unavailable": True,
    }


def build_stratification_plan() -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "package_id": PACKAGE_ID,
        "image_region_strata": IMAGE_REGION_STRATA,
        "present_scene_element_strata": PRESENT_SCENE_STRATA,
        "absent_scene_element_strata": ABSENT_SCENE_STRATA,
        "design": (
            "Per layout: 4 truth-present and 4 truth-absent frames. Present frames "
            "span the four horizontal image-region strata via the sheep's planned "
            "visible lane position; each is tagged with a scene-element stratum "
            "(open / near-marker / near-wall-edge / lane-extreme) to exercise recall "
            "across contexts. Absent frames span the same four image regions with "
            "scene-element strata (marker / wall / open background / marker+wall) to "
            "exercise false-positive rejection. Enough present and absent cases per "
            "layout to make precision and recall gates meaningful."),
        "per_layout_matrix": {
            lay: {
                "present": [
                    {"image_region_stratum": IMAGE_REGION_STRATA[i],
                     "scene_element_stratum": PRESENT_SCENE_STRATA[i]} for i in range(4)],
                "absent": [
                    {"image_region_stratum": IMAGE_REGION_STRATA[i],
                     "scene_element_stratum": ABSENT_SCENE_STRATA[i]} for i in range(4)],
            } for lay in LAYOUTS},
    }


def build_truth_authority() -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "package_id": PACKAGE_ID,
        "truth_authority": "Person C owned geometry and authoritative capture condition",
        "person_e_detector_output_used_for_truth": False,
        "rules": {
            "truth_present": (
                "sheep present (visible capture condition) AND geometrically visible "
                "per Person C server as-built wall/sheep geometry at the reserved frame "
                "index. Binary owner-authored label truth_present=true."),
            "truth_absent": (
                "no-sheep capture condition (no sheep entity in the scene). Binary "
                "owner-authored label truth_present=false."),
            "binary_labels": "owner-authored positive/negative only; no detector outcome",
        },
        "geometry_rule_reference": "mineocclude.data.visibility (geometric visibility)",
    }


def build_capture_requirements() -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "package_id": PACKAGE_ID,
        "untouched_test_rules": [
            "All image bytes will be produced AFTER this predeclaration is committed.",
            "No old PNG, episode, capture session, source path, or SHA-256 may be reused.",
            "All 48 predeclared rows are mandatory.",
            "No frame may be removed because it is difficult.",
            "No substitutions are allowed after capture begins.",
            ("A substitution requires retiring this package version and committing a new "
             "predeclaration first."),
            "Person E receives exactly one formal evaluation run.",
            "A failed test set cannot later be reused for tuning and still be called untouched.",
            "No detector outcomes are disclosed during capture or package construction.",
        ],
        "source_commit_must_postdate_freeze": True,
        "capture_source_revision_must_postdate_this_predeclaration_commit": True,
        "captured_bytes_must_not_match_forbidden_development_hashes": True,
        "captured_bytes_must_not_match_any_historical_c_hash": True,
        "forbidden_development_source_sha256": forbidden_dev_hashes(),
        "forbidden_historical_c_episode_ids": historical_c_episode_ids(),
        "reserved_episode_ids_are_new": True,
        "present_frame_capture_constraint": (
            "Capture must be designed (sheep start position / speed) so the sheep is "
            "geometrically visible at every reserved present frame index; if not "
            "achievable, retire this package version and re-predeclare (no substitution)."),
        "missing_duplicate_or_extra_frame_behavior": "reject_fail_closed",
        "overwrite_forbidden": True,
        "partial_evaluation_forbidden": True,
    }


def canonical_bytes(obj: dict) -> bytes:
    return (json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def build_all_except_receipt() -> dict:
    return {
        "untouched_test_predeclaration.json": build_predeclaration(),
        "untouched_test_frame_manifest.json": {
            "schema_version": SCHEMA_VERSION, "package_id": PACKAGE_ID,
            "total_frames": 48, "frames": build_frames()},
        "untouched_test_stratification_plan.json": build_stratification_plan(),
        "untouched_test_truth_authority.json": build_truth_authority(),
        "untouched_test_capture_requirements.json": build_capture_requirements(),
    }


def build_receipt(others: dict) -> dict:
    file_hashes = {name: hashlib.sha256(canonical_bytes(obj)).hexdigest()
                   for name, obj in sorted(others.items())}
    return {
        "schema_version": SCHEMA_VERSION,
        "receipt_schema_version": "person-c-phase3-untouched-test-receipt-v1.0",
        "package_id": PACKAGE_ID,
        "package_version": PACKAGE_VERSION,
        "owner": "Person C",
        "mode": "predeclaration_only",
        "person_e_freeze_commit": E_FREEZE_COMMIT,
        "detector_version": DETECTOR_VERSION,
        "created_after_person_e_freeze": True,
        "no_png_created": True,
        "person_e_detector_not_run": True,
        "u4_output_not_inspected": True,
        "counts": {"total_frames": 48, "truth_present": 24, "truth_absent": 24,
                   "layouts": 6, "present_per_layout": 4, "absent_per_layout": 4},
        "predeclared_file_sha256": file_hashes,
    }


def build_all() -> dict:
    others = build_all_except_receipt()
    out = dict(others)
    out["untouched_test_predeclaration_receipt.json"] = build_receipt(others)
    return out


def write_all(dest: str = PKG_DIR) -> list[str]:
    os.makedirs(dest, exist_ok=True)
    written = []
    for name, obj in sorted(build_all().items()):
        p = os.path.join(dest, name)
        with open(p, "wb") as f:
            f.write(canonical_bytes(obj))
        written.append(p)
    return written


if __name__ == "__main__":
    for p in write_all():
        print("wrote", os.path.relpath(p, ROOT))
