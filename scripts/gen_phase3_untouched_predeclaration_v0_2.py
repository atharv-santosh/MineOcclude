#!/usr/bin/env python3
"""Deterministic generator for the Person C -> Person E Phase 3 Detector v1
UNTOUCHED-TEST v0_2 predeclaration + the v0_1 retirement receipt.

PREDECLARATION ONLY - no image bytes. v0_1 is retired (its static no-target
scene deterministically yields byte-identical negatives). v0_2 gives each
truth-absent frame a distinct, exactly-positioned non-magenta COW distractor so
the four negatives per layout are genuinely different while the binary truth
stays absent (no magenta sheep). Byte-identical on every run.
"""
from __future__ import annotations

import hashlib
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
V1_DIR = os.path.join(ROOT, "data/handoff_e/phase3_detector_v1_untouched_test_v0_1")
V2_DIR = os.path.join(ROOT, "data/handoff_e/phase3_detector_v1_untouched_test_v0_2")

# ---- Person E frozen-candidate binding (identity only; detector never run) ----
E_FREEZE_COMMIT = "3930669eddc026ecb081e947f71f1855a7415904"
DETECTOR_VERSION = ("hsv-largest-valid-blob-v1.0-candidate:sha256:"
                    "0cadf618fca1578196bde4982021c38627ccb9c39e46353812e7da3fce6aa125")
DETECTOR_IDENTITY_SHA256 = "0cadf618fca1578196bde4982021c38627ccb9c39e46353812e7da3fce6aa125"
DETECTOR_CONFIG_SHA256 = "acfecd659958891eaee0d582c946abdfaaf47d1ab3307a24f7652e634c045bfa"
DETECTOR_SETTINGS_SHA256 = "0dbb426adf99f53455eea04c4aaeb56f3cb22cbc351d87269bb605445eb8f2ea"
DETECTOR_IMPLEMENTATION_SHA256 = "026f3b9f25c8aef7ac43fada5b8de92662b605af4868f930698651e59a228214"
FREEZE_TIMESTAMP_UTC = "2026-07-28T06:03:15Z"

PACKAGE_ID = "person-c-phase3-detector-v1-untouched-test-v0_2"
PACKAGE_VERSION = "v0.2"
SCHEMA_VERSION = "1.0"
CAPTURE_SESSION_ID = "person-c-phase3-untouched-test-v0_2-session-01"
V1_PACKAGE_ID = "person-c-phase3-detector-v1-untouched-test-v0_1"

LAYOUTS = [f"layout_0{i}" for i in range(1, 7)]
WIDTH, HEIGHT = 640, 360
IMAGE_ENCODING, PIXEL_FORMAT = "png", "rgb8"
COORDINATE_CONVENTION = "pixel_center_xy_zero_based"
WORLD_CONVENTION = "ground_plane_world_xz_blocks_topface_centre"

# Reserved capture identities: brand-new 52xxx range, never used by v0_1 (51xxx)
# or historical packages. Present: one episode/layout, 4 frames at indices
# below. Absent: one episode PER negative frame (a static NoAI cow at one exact
# position => a trivially distinct, exactly-reproducible negative).
PRESENT_EPISODE = {lay: 52001 + i for i, lay in enumerate(LAYOUTS)}          # 52001..52006
ABSENT_EPISODE = {lay: [52007 + 4 * i + s for s in range(4)]                  # 52007..52030
                  for i, lay in enumerate(LAYOUTS)}
PRESENT_FRAME_INDICES = [3, 7, 11, 15]
ABSENT_FRAME_INDEX = 12

IMAGE_REGION_STRATA = ["region_1_left", "region_2_center_left",
                       "region_3_center_right", "region_4_right"]
PRESENT_SCENE_STRATA = ["sheep_open_ground", "sheep_near_marker",
                        "sheep_near_wall_edge", "sheep_lane_extreme"]
ABSENT_SCENE_STRATA = ["cow_far_negative_end_open", "cow_left_of_wall_segment",
                       "cow_right_of_wall_segment", "cow_far_positive_end_open"]
DISTRACTOR_ENTITY_TYPE = "minecraft:cow"


def _layouts_cfg() -> dict:
    with open(os.path.join(ROOT, "configs/scenes/layouts.yaml"), encoding="utf-8") as h:
        return {l["layout_id"]: l for l in json.load(h)["layouts"]}


def cow_positions(layout: str, cfg: dict) -> list[dict]:
    """Four exact, distinct, in-frame cow world positions per layout: at the
    sheep depth, at four axis positions all OUTSIDE the wall's axis-shadow so the
    cow is unoccluded. Order left->right. Returns world {x,y,z} dicts."""
    L = cfg[layout]
    lane = L["lane"]
    axis = lane["axis"]
    lane_min = float(lane["min_scalar_blocks"])
    lane_max = float(lane["max_scalar_blocks"])
    depth = float(lane["fixed_coordinate_blocks"])
    y = float(lane["y_blocks"])
    if axis == "x":
        occ_min, occ_max = float(L["wall"]["min_x"]), float(L["wall"]["max_x"])
    else:
        occ_min, occ_max = float(L["wall"]["min_z"]), float(L["wall"]["max_z"])
    axis_positions = [lane_min + 1.0, occ_min - 1.0, occ_max + 1.0, lane_max - 1.0]
    out = []
    for a in axis_positions:
        if axis == "x":
            out.append({"x": round(a, 3), "y": round(y, 3), "z": round(depth, 3)})
        else:
            out.append({"x": round(depth, 3), "y": round(y, 3), "z": round(a, 3)})
    return out


def _pose(layout: str) -> str:
    return f"{layout}_canonical_pose_v1"


def _common(layout: str, cls: str, slot: int, ep: int, idx: int) -> dict:
    return {
        "package_id": PACKAGE_ID,
        "frame_id": f"{PACKAGE_ID}::{layout}::{cls}::{slot:02d}",
        "truth_class": cls,
        "truth_present": cls == "present",
        "target_magenta_sheep_present": cls == "present",
        "layout_id": layout,
        "canonical_camera_pose_id": _pose(layout),
        "width": WIDTH, "height": HEIGHT,
        "image_encoding": IMAGE_ENCODING, "pixel_format": PIXEL_FORMAT,
        "coordinate_convention": COORDINATE_CONVENTION,
        "world_coordinate_convention": WORLD_CONVENTION,
        "image_region_stratum": IMAGE_REGION_STRATA[slot],
        "scene_element_stratum": (PRESENT_SCENE_STRATA if cls == "present" else ABSENT_SCENE_STRATA)[slot],
        "reserved_capture_session_id": CAPTURE_SESSION_ID,
        "reserved_episode_id": ep,
        "reserved_frame_index": idx,
        "visible_negative_pairing_id": f"{PACKAGE_ID}::{layout}::pair::{slot:02d}",
        "planned_source_relative_path":
            f"data/handoff_e/phase3_detector_v1_untouched_test_v0_2/"
            f"frames/{cls}/{layout}/{slot:02d}.png",
        "authoritative_truth_source": "person_c_server_world_state_and_geometry",
        "geometry_rule_version": "person-c-geometric-visibility-v0.1",
        "test_only": True,
        "detector_outcome_unavailable": True,
    }


def build_frames(cfg: dict) -> list[dict]:
    frames = []
    for layout in LAYOUTS:
        for slot in range(4):
            f = _common(layout, "present", slot, PRESENT_EPISODE[layout], PRESENT_FRAME_INDICES[slot])
            f["present_condition"] = (
                "magenta sheep present and geometrically visible per C geometry "
                "at the reserved frame index")
            frames.append(f)
        cows = cow_positions(layout, cfg)
        for slot in range(4):
            f = _common(layout, "absent", slot, ABSENT_EPISODE[layout][slot], ABSENT_FRAME_INDEX)
            f["distractor_entity_type"] = DISTRACTOR_ENTITY_TYPE
            f["distractor_identity"] = f"{PACKAGE_ID}::{layout}::cow::{slot:02d}"
            f["distractor_world_position"] = cows[slot]
            f["distractor_hold"] = "NoAI (held static at the exact world position)"
            f["distractor_is_detection_target"] = False
            frames.append(f)
    return frames


def canon(obj) -> bytes:
    return (json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


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
    }


def build_predeclaration(cfg: dict) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "predeclaration_schema_version": "person-c-phase3-untouched-test-predeclaration-v2.0",
        "package_id": PACKAGE_ID, "package_version": PACKAGE_VERSION,
        "owner": "Person C", "consumer": "Person E", "mode": "predeclaration_only",
        "created_after_person_e_freeze": True,
        "supersedes_retired_package": V1_PACKAGE_ID,
        "person_e_candidate_binding": _e_binding(),
        "counts": {"total_frames": 48, "truth_present": 24, "truth_absent": 24,
                   "layouts": 6, "present_per_layout": 4, "absent_per_layout": 4,
                   "pairs": 24},
        "resolution": {"width": WIDTH, "height": HEIGHT, "pixel_format": PIXEL_FORMAT,
                       "image_encoding": IMAGE_ENCODING,
                       "coordinate_convention": COORDINATE_CONVENTION},
        "world_coordinate_convention": WORLD_CONVENTION,
        "canonical_camera_pose_ids": {lay: _pose(lay) for lay in LAYOUTS},
        "reserved_capture_session_id": CAPTURE_SESSION_ID,
        "reserved_episode_ids": {
            "present": {lay: PRESENT_EPISODE[lay] for lay in LAYOUTS},
            "absent": {lay: ABSENT_EPISODE[lay] for lay in LAYOUTS}},
        "truth_absent_design": {
            "definition": "target magenta sheep absent; binary truth = absent",
            "distractor_entity_type": DISTRACTOR_ENTITY_TYPE,
            "distractor_is_detection_target": False,
            "distractor_hold": "NoAI, held static at the exact predeclared position",
            "no_pig": ("a pig is intentionally NOT used: its pink colour could create "
                       "avoidable ambiguity in a magenta-target detector test"),
            "cow_positions": {lay: cow_positions(lay, cfg) for lay in LAYOUTS}},
        "no_image_bytes_created": True,
        "detector_outcomes_unavailable": True,
    }


def build_stratification(cfg: dict) -> dict:
    return {
        "schema_version": SCHEMA_VERSION, "package_id": PACKAGE_ID,
        "image_region_strata": IMAGE_REGION_STRATA,
        "present_scene_element_strata": PRESENT_SCENE_STRATA,
        "absent_scene_element_strata": ABSENT_SCENE_STRATA,
        "design": (
            "Per layout: 4 truth-present (moving magenta sheep -> distinct frames) "
            "and 4 truth-absent (a static NoAI cow distractor at 4 distinct, "
            "unoccluded world positions -> distinct frames). The cow is never the "
            "detection target; the binary truth stays absent. Enough distinct "
            "positives and negatives per layout to make precision and recall "
            "gates meaningful."),
        "per_layout_absent_cow_positions": {lay: cow_positions(lay, cfg) for lay in LAYOUTS},
    }


def build_truth_authority() -> dict:
    return {
        "schema_version": SCHEMA_VERSION, "package_id": PACKAGE_ID,
        "truth_authority": "Person C owned geometry and authoritative capture condition",
        "person_e_detector_output_used_for_truth": False,
        "rules": {
            "truth_present": ("magenta sheep present AND geometrically visible per Person C "
                              "server as-built geometry at the reserved frame index"),
            "truth_absent": ("no magenta sheep entity present. A non-magenta cow distractor "
                             "held static at an exact world position may be present; it is NOT "
                             "the detection target and does not change the binary absent label"),
            "binary_labels": "owner-authored positive/negative only; no detector outcome"},
        "geometry_rule_reference": "mineocclude.data.visibility (geometric visibility)",
    }


def build_capture_requirements() -> dict:
    return {
        "schema_version": SCHEMA_VERSION, "package_id": PACKAGE_ID,
        "untouched_test_rules": [
            "All image bytes will be produced AFTER this v0_2 predeclaration is committed and pushed.",
            "No v0_1 PNG bytes may be reused in v0_2.",
            "No old PNG, episode, capture session, source path, or SHA-256 may be reused.",
            "All 48 predeclared rows are mandatory.",
            "No frame may be removed because it is difficult.",
            "No frame may be selected or replaced based on detector behavior.",
            "No substitutions are allowed after capture begins.",
            "A substitution requires retiring this package version and committing a new predeclaration first.",
            "Person E receives exactly one formal evaluation run.",
            "A failed or retired package may not be reused for detector tuning.",
            "No detector outcomes are disclosed during capture or package construction.",
        ],
        "source_commit_must_postdate_freeze": True,
        "capture_source_revision_must_postdate_this_predeclaration_commit": True,
        "captured_bytes_must_not_match_v0_1_png_hashes": True,
        "captured_bytes_must_not_match_forbidden_development_hashes": True,
        "captured_bytes_must_not_match_any_historical_c_hash": True,
        "duplicate_png_hashes_fail_closed": True,
        "duplicate_negative_hashes_pre_authorized": False,
        "present_frame_capture_constraint": (
            "Capture must be designed so the magenta sheep is geometrically visible at every "
            "reserved present frame index; if not achievable, retire v0_2 and re-predeclare."),
        "absent_frame_capture_constraint": (
            "Each absent frame holds a NoAI cow at exactly its predeclared distractor_world_position; "
            "no magenta sheep present; the four positions per layout must render distinct images."),
        "missing_duplicate_or_extra_frame_behavior": "reject_fail_closed",
        "overwrite_forbidden": True, "partial_evaluation_forbidden": True,
    }


def build_all_except_receipt(cfg: dict) -> dict:
    return {
        "untouched_test_predeclaration.json": build_predeclaration(cfg),
        "untouched_test_frame_manifest.json": {
            "schema_version": SCHEMA_VERSION, "package_id": PACKAGE_ID,
            "total_frames": 48, "frames": build_frames(cfg)},
        "untouched_test_stratification_plan.json": build_stratification(cfg),
        "untouched_test_truth_authority.json": build_truth_authority(),
        "untouched_test_capture_requirements.json": build_capture_requirements(),
    }


def build_receipt(others: dict) -> dict:
    file_hashes = {name: hashlib.sha256(canon(obj)).hexdigest()
                   for name, obj in sorted(others.items())}
    return {
        "schema_version": SCHEMA_VERSION,
        "receipt_schema_version": "person-c-phase3-untouched-test-receipt-v2.0",
        "package_id": PACKAGE_ID, "package_version": PACKAGE_VERSION, "owner": "Person C",
        "mode": "predeclaration_only", "person_e_freeze_commit": E_FREEZE_COMMIT,
        "detector_version": DETECTOR_VERSION, "created_after_person_e_freeze": True,
        "supersedes_retired_package": V1_PACKAGE_ID,
        "no_png_created": True, "person_e_detector_not_run": True,
        "u4_output_not_inspected": True,
        "counts": {"total_frames": 48, "truth_present": 24, "truth_absent": 24,
                   "layouts": 6, "present_per_layout": 4, "absent_per_layout": 4, "pairs": 24},
        "predeclared_file_sha256": file_hashes,
    }


def build_v2() -> dict:
    cfg = _layouts_cfg()
    others = build_all_except_receipt(cfg)
    out = dict(others)
    out["untouched_test_predeclaration_receipt.json"] = build_receipt(others)
    return out


def build_retirement_receipt() -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "retirement_receipt_schema_version": "person-c-phase3-untouched-test-retirement-v1.0",
        "retired_package_id": V1_PACKAGE_ID, "owner": "Person C",
        "retired_before_formal_evaluation": True,
        "person_e_detector_never_run": True,
        "no_detector_outcome_inspected": True,
        "no_u4_output_inspected": True,
        "no_v0_1_capture_package_committed": True,
        "retirement_reason": (
            "The frozen no-target scene is static at the canonical pose, so reserved frame "
            "indexes 3, 7, 11, and 15 produce byte-identical truth-absent PNGs within each "
            "layout (verified: 0 differing pixels even at the raw 1280x720 source)."),
        "frozen_duplicate_hash_rule_did_not_permit_acceptance": True,
        "no_post_capture_addendum_used_to_weaken_rule": True,
        "no_v0_1_png_may_be_treated_as_untouched_test_evidence": True,
        "any_locally_captured_v0_1_files_retired_and_excluded_from_v0_2": True,
        "successor_package_id": PACKAGE_ID,
    }


def write_all() -> list[str]:
    written = []
    os.makedirs(V1_DIR, exist_ok=True)
    p = os.path.join(V1_DIR, "untouched_test_retirement_receipt.json")
    with open(p, "wb") as f:
        f.write(canon(build_retirement_receipt()))
    written.append(p)
    os.makedirs(V2_DIR, exist_ok=True)
    for name, obj in sorted(build_v2().items()):
        p = os.path.join(V2_DIR, name)
        with open(p, "wb") as f:
            f.write(canon(obj))
        written.append(p)
    return written


if __name__ == "__main__":
    for p in write_all():
        print("wrote", os.path.relpath(p, ROOT))
