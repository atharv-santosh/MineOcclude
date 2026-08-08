"""Final visibility interface / strict-join proofs (Person C owns visible_flag)."""
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "src"))
import mineocclude.contracts  # noqa: F401,E402
from mineocclude.data.visibility_join import (  # noqa: E402
    VisibilityJoinError, strict_join)

DET = "hsv-largest-valid-blob-v1.0-candidate:sha256:0cadf618"
CTX = {"layout_id": "layout_01", "canonical_camera_pose_id": "layout_01_canonical_pose_v1",
       "resolution": "640x360", "coordinate_convention": "pixel_center_xy_zero_based"}


def c_rec(idx, geo, **over):
    r = {"trajectory_id": "layout_01_ep10000", "model_frame_idx": idx,
         "geometric_visible": geo, "geometry_rule_version": "person-c-geometric-visibility-v0.1"}
    r.update(CTX); r.update(over); return r


def e_rec(idx, emp, **over):
    r = {"trajectory_id": "layout_01_ep10000", "model_frame_idx": idx,
         "empirical_magenta_visible": emp, "detector_version": DET}
    r.update(CTX); r.update(over); return r


def test_exact_one_to_one_join_and_and_rule():
    c = [c_rec(0, True), c_rec(1, True), c_rec(2, False), c_rec(3, False)]
    e = [e_rec(0, True), e_rec(1, False), e_rec(2, True), e_rec(3, False)]
    out = strict_join(c, e, expected_detector_version=DET)
    assert len(out) == 4
    flags = {r["model_frame_idx"]: r["visible_flag"] for r in out}
    assert flags == {0: True, 1: False, 2: False, 3: False}  # AND rule


def test_raw_channels_kept_separate_from_final_label():
    out = strict_join([c_rec(0, True)], [e_rec(0, False)], expected_detector_version=DET)
    r = out[0]
    assert r["geometric_visible"] is True
    assert r["empirical_magenta_visible"] is False
    assert r["visible_flag"] is False
    assert r["label_owner"] == "Person C"


def test_e_cannot_write_or_overwrite_visible_flag():
    bad = e_rec(0, True); bad["visible_flag"] = True  # E tries to force the label
    with pytest.raises(VisibilityJoinError) as ei:
        strict_join([c_rec(0, False)], [bad], expected_detector_version=DET)
    assert ei.value.category == "e_cannot_write_visible_flag"


@pytest.mark.parametrize("mutate,category", [
    ("missing_e", "missing_e_record"),
    ("extra_e", "extra_unmatched_e_record"),
    ("dup_c", "duplicate_c_record"),
    ("dup_e", "duplicate_e_record"),
    ("wrong_det", "wrong_detector_version"),
    ("wrong_layout", "context_identity_mismatch"),
    ("wrong_pose", "context_identity_mismatch"),
    ("wrong_res", "context_identity_mismatch"),
    ("wrong_coord", "context_identity_mismatch"),
    ("incomplete_c", "incomplete_c_input"),
    ("incomplete_e", "incomplete_e_input"),
])
def test_every_structural_mismatch_fails_closed(mutate, category):
    c = [c_rec(0, True), c_rec(1, True)]
    e = [e_rec(0, True), e_rec(1, True)]
    if mutate == "missing_e":
        e = [e_rec(0, True)]
    elif mutate == "extra_e":
        e.append(e_rec(2, True))
    elif mutate == "dup_c":
        c.append(c_rec(0, True))
    elif mutate == "dup_e":
        e.append(e_rec(0, True))
    elif mutate == "wrong_det":
        e[0]["detector_version"] = "some-other-detector-v9"
    elif mutate == "wrong_layout":
        e[0]["layout_id"] = "layout_02"
    elif mutate == "wrong_pose":
        e[0]["canonical_camera_pose_id"] = "layout_02_canonical_pose_v1"
    elif mutate == "wrong_res":
        e[0]["resolution"] = "384x224"
    elif mutate == "wrong_coord":
        e[0]["coordinate_convention"] = "top_left_origin"
    elif mutate == "incomplete_c":
        del c[0]["geometric_visible"]
    elif mutate == "incomplete_e":
        del e[0]["empirical_magenta_visible"]
    with pytest.raises(VisibilityJoinError) as ei:
        strict_join(c, e, expected_detector_version=DET)
    assert ei.value.category == category


def test_extra_unmatched_e_row_is_rejected_not_ignored():
    c = [c_rec(0, True)]
    e = [e_rec(0, True), e_rec(99, True)]
    with pytest.raises(VisibilityJoinError) as ei:
        strict_join(c, e, expected_detector_version=DET)
    assert ei.value.category == "extra_unmatched_e_record"


def test_disagreement_categories_retained_and_quarantined():
    c = [c_rec(0, True), c_rec(1, False), c_rec(2, None), c_rec(3, True)]
    e = [e_rec(0, False), e_rec(1, True), e_rec(2, True), e_rec(3, None)]
    out = {r["model_frame_idx"]: r for r in strict_join(c, e, expected_detector_version=DET)}
    assert out[0]["quarantine_category"] == "geometry_visible_detector_hidden"
    assert out[1]["quarantine_category"] == "geometry_hidden_detector_visible"
    assert out[2]["quarantine_category"] == "invalid_geometry"
    assert out[3]["quarantine_category"] == "missing_detector"
    for i in range(4):
        assert out[i]["quarantined"] is True
        assert out[i]["visible_flag"] is False  # no disagreement silently becomes visible
    assert out[2]["invalidity_reason"] == "invalid_geometry"
    assert out[3]["invalidity_reason"] == "missing_detector"


def test_c_owns_label_generation():
    # visible_flag is computed by C's join, always present, never taken from E
    out = strict_join([c_rec(0, True)], [e_rec(0, True)], expected_detector_version=DET)
    assert out[0]["visible_flag"] is True and out[0]["label_owner"] == "Person C"


def test_interface_generation_deterministic(tmp_path):
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    import gen_phase3_visibility_interface as g
    a = g.build_all()
    b = g.build_all()
    assert {k: v for k, v in a.items()} == {k: v for k, v in b.items()}
    # committed files match regeneration byte-for-byte
    base = os.path.join(ROOT, "data/handoff_e/phase3_visibility_interface_v0_1")
    for name, data in a.items():
        with open(os.path.join(base, name), "rb") as f:
            assert f.read() == data, name


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
