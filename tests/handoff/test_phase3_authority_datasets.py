"""Deliverables 2 & 3: homography-authority and geometric-visibility-authority
structure, owner boundaries, and deterministic generation."""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import mineocclude.contracts  # noqa: F401,E402
import gen_phase3_homography_authority as gh  # noqa: E402
import gen_phase3_visibility_authority as gv  # noqa: E402

HOMO = os.path.join(ROOT, "data/handoff_e/phase3_homography_authority_v0_1")
VIS = os.path.join(ROOT, "data/handoff_e/phase3_visibility_authority_v0_1")
LAYOUTS = [f"layout_0{i}" for i in range(1, 7)]


def loadj(path):
    with open(path) as f:
        return json.load(f)


# ---------- Deliverable 2: homography authority ----------
def test_homography_manifest_bindings():
    m = loadj(os.path.join(HOMO, "homography_applicability_manifest.json"))
    assert m["layout_ids"] == LAYOUTS
    assert m["capture_resolution"] == {"width": 640, "height": 360}
    assert m["world_coordinate_convention"] == "ground_plane_world_xz_blocks_topface_centre"
    assert m["marker_identities_and_ordering"] == ["north_west", "north_east", "south_east", "south_west"]
    assert "fail_closed_requirement" in m
    for key in ("resolution", "crop", "scaling", "camera", "layout_id", "canonical_camera_pose_id"):
        assert key in m["applicability_limits"]


def test_known_direction_owner_authored_and_not_from_detector():
    k = loadj(os.path.join(HOMO, "known_direction_validation_records.json"))
    assert len(k["records"]) == 6
    seen = set()
    for r in k["records"]:
        seen.add(r["layout_id"])
        assert r["units"] == "blocks"
        assert r["truth_source"] == "person_c_server_world_state"
        assert r["detector_output_used_to_define_direction"] is False
        assert "before" in r and "after" in r
        assert isinstance(r["expected_signed_displacement_blocks"], (int, float))
        assert r["expected_direction"] in ("positive", "negative")
        assert r["source_frame_map_sha256"]
        # sign must be establishable independently of E's localization noise
        assert abs(r["expected_signed_displacement_blocks"]) >= 0.5
        assert r["displacement_exceeds_localization_noise"] is True
    assert seen == set(LAYOUTS)


def test_bindings_bind_marker_pose_resolution_and_conventions():
    b = loadj(os.path.join(HOMO, "marker_pose_resolution_bindings.json"))
    assert len(b["per_layout"]) == 6
    for rec in b["per_layout"]:
        assert rec["canonical_camera_pose_id"] == f"{rec['layout_id']}_canonical_pose_v1"
        assert rec["capture_resolution"] == {"width": 640, "height": 360}
        assert rec["image_coordinate_convention"] == "pixel_center_xy_zero_based"
        assert rec["world_coordinate_convention"] == "ground_plane_world_xz_blocks_topface_centre"
        assert rec["marker_source_sha256"] and rec["marker_source_committed"] is True
        assert [m["marker_role"] for m in rec["markers"]] == \
            ["north_west", "north_east", "south_east", "south_west"]


def test_wall_axis_sign_defined_per_layout():
    s = loadj(os.path.join(HOMO, "wall_axis_sign_authority.json"))
    assert s["detector_output_used_to_define_direction"] is False
    for lay in LAYOUTS:
        pl = s["per_layout"][lay]
        assert pl["wall_parallel_axis"] in ("x", "z")
        assert pl["positive_direction"].startswith("increasing")
        assert pl["negative_direction"].startswith("decreasing")


def test_homography_authority_deterministic():
    a, b = gh.build_all(), gh.build_all()
    assert a == b
    for name, data in a.items():
        with open(os.path.join(HOMO, name), "rb") as f:
            assert f.read() == data, name


# ---------- Deliverable 3: geometric-visibility authority ----------
def test_geometric_records_schema_and_no_empirical():
    man = loadj(os.path.join(VIS, "visibility_identity_manifest.json"))
    assert man["identity_primary_key"] == ["trajectory_id", "model_frame_idx"]
    recs = [json.loads(l) for l in open(os.path.join(VIS, "geometric_visibility_records.jsonl")) if l.strip()]
    assert len(recs) == man["record_count"] > 0
    keys = set()
    for r in recs:
        assert r["empirical_decision_present"] is False
        assert "empirical" not in json.dumps(r).lower() or "empirical_decision_present" in r
        assert r["geometry_rule_version"] == gv.GEOMETRY_RULE_VERSION
        assert r["geometric_status"] in ("visible", "occluded", "boundary", "invalid")
        assert r["scene"] == "NORMAL" and r["regime"] == "A"
        keys.add((r["trajectory_id"], r["model_frame_idx"]))
    assert len(keys) == len(recs)  # unique identity keys (one-to-one)


def test_geometric_records_sorted_and_hashed():
    recs = [json.loads(l) for l in open(os.path.join(VIS, "geometric_visibility_records.jsonl")) if l.strip()]
    order = [(r["trajectory_id"], r["model_frame_idx"]) for r in recs]
    assert order == sorted(order)
    import hashlib
    man = loadj(os.path.join(VIS, "visibility_identity_manifest.json"))
    with open(os.path.join(VIS, "geometric_visibility_records.jsonl"), "rb") as f:
        assert hashlib.sha256(f.read()).hexdigest() == man["records_sha256"]


def test_geometric_authority_deterministic():
    a, b = gv.build_all(), gv.build_all()
    assert a == b
    for name, data in a.items():
        with open(os.path.join(VIS, name), "rb") as f:
            assert f.read() == data, name


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
