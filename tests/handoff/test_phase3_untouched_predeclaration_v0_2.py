"""Phase 3 untouched-test v0_2 predeclaration + v0_1 retirement proofs.

Proves v0_2 binds exactly to E's frozen candidate, has the balanced 48/24/24
structure with brand-new identities (no v0_1 / historical reuse, by PARSED
identity fields), gives every negative an exact non-magenta cow distractor,
discloses no detector outcomes, creates no image bytes, and regenerates
byte-identically.
"""
import json
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import gen_phase3_untouched_predeclaration_v0_2 as gen

V1 = os.path.join(ROOT, "data/handoff_e/phase3_detector_v1_untouched_test_v0_1")
V2 = os.path.join(ROOT, "data/handoff_e/phase3_detector_v1_untouched_test_v0_2")
LAYOUTS = [f"layout_0{i}" for i in range(1, 7)]
V2_PREDECLARATION_COMMIT = "b466c233c08502ce5b9a23f07729eb71a47dbbfb"


def load(base, name):
    with open(os.path.join(base, name), "rb") as f:
        return f.read()


def loadj(base, name):
    return json.loads(load(base, name))


def frames():
    return loadj(V2, "untouched_test_frame_manifest.json")["frames"]


def parse_id(frame_id):
    pkg, layout, cls, slot = frame_id.split("::")
    return {"package_id": pkg, "layout_id": layout, "truth_class": cls, "slot": slot}


# ---- exact E freeze binding ----
def test_exact_person_e_freeze_binding():
    b = loadj(V2, "untouched_test_predeclaration.json")["person_e_candidate_binding"]
    assert b["person_e_freeze_commit"] == "3930669eddc026ecb081e947f71f1855a7415904"
    assert b["detector_version"] == (
        "hsv-largest-valid-blob-v1.0-candidate:sha256:"
        "0cadf618fca1578196bde4982021c38627ccb9c39e46353812e7da3fce6aa125")
    assert b["detector_config_sha256"] == "acfecd659958891eaee0d582c946abdfaaf47d1ab3307a24f7652e634c045bfa"
    assert b["detector_settings_sha256"] == "0dbb426adf99f53455eea04c4aaeb56f3cb22cbc351d87269bb605445eb8f2ea"
    assert b["detector_implementation_sha256"] == "026f3b9f25c8aef7ac43fada5b8de92662b605af4868f930698651e59a228214"


def test_counts_pairs_and_per_layout():
    fr = frames()
    assert len(fr) == 48
    assert sum(f["truth_present"] is True for f in fr) == 24
    assert sum(f["truth_present"] is False for f in fr) == 24
    assert {f["layout_id"] for f in fr} == set(LAYOUTS)
    for lay in LAYOUTS:
        lf = [f for f in fr if f["layout_id"] == lay]
        assert sum(f["truth_class"] == "present" for f in lf) == 4
        assert sum(f["truth_class"] == "absent" for f in lf) == 4
    # exactly 24 valid pairs, each one present + one absent within one layout
    pairs = {}
    for f in fr:
        pairs.setdefault(f["visible_negative_pairing_id"], []).append(f)
    assert len(pairs) == 24
    for members in pairs.values():
        assert len(members) == 2
        classes = sorted(m["truth_class"] for m in members)
        assert classes == ["absent", "present"]
        assert len({m["layout_id"] for m in members}) == 1


def test_unique_identities_paths_resolution_pose():
    fr = frames()
    assert len({f["frame_id"] for f in fr}) == 48
    assert len({f["planned_source_relative_path"] for f in fr}) == 48
    assert len({(f["reserved_capture_session_id"], f["reserved_episode_id"],
                 f["reserved_frame_index"]) for f in fr}) == 48
    for f in fr:
        assert (f["width"], f["height"]) == (640, 360)
        assert f["canonical_camera_pose_id"] == f"{f['layout_id']}_canonical_pose_v1"
        assert f["coordinate_convention"] == "pixel_center_xy_zero_based"
        assert f["planned_source_relative_path"].startswith(
            "data/handoff_e/phase3_detector_v1_untouched_test_v0_2/frames/")


# ---- distractor / truth-absent design ----
def test_every_absent_row_has_exact_cow_distractor_and_no_sheep():
    fr = frames()
    absent = [f for f in fr if f["truth_class"] == "absent"]
    assert len(absent) == 24
    for f in absent:
        assert f["target_magenta_sheep_present"] is False
        assert f["truth_present"] is False
        assert f["distractor_entity_type"] == "minecraft:cow"
        assert f["distractor_is_detection_target"] is False
        p = f["distractor_world_position"]
        assert set(p) == {"x", "y", "z"} and all(isinstance(v, (int, float)) for v in p.values())
        assert f["distractor_identity"].endswith(f["frame_id"].split("::")[-1])
    # four positions per layout are distinct
    for lay in LAYOUTS:
        pos = [tuple(f["distractor_world_position"].values())
               for f in absent if f["layout_id"] == lay]
        assert len(pos) == 4 and len(set(pos)) == 4
    # no pig anywhere in the package (avoidable magenta ambiguity)
    blob = load(V2, "untouched_test_predeclaration.json").decode().lower()
    assert "pig" in blob and "not used" in blob  # documented exclusion
    assert "minecraft:pig" not in json.dumps(fr)


def test_present_rows_target_sheep():
    fr = frames()
    present = [f for f in fr if f["truth_class"] == "present"]
    assert len(present) == 24
    for f in present:
        assert f["target_magenta_sheep_present"] is True
        assert f["reserved_frame_index"] in (3, 7, 11, 15)


# ---- brand-new identities: no v0_1 / historical reuse, by PARSED fields ----
def test_new_session_and_episodes():
    fr = frames()
    assert {f["reserved_capture_session_id"] for f in fr} == {
        "person-c-phase3-untouched-test-v0_2-session-01"}
    eps = {f["reserved_episode_id"] for f in fr}
    assert eps == set(range(52001, 52031))          # 30 brand-new episodes
    assert eps.isdisjoint(set(range(51001, 51013)))  # no v0_1 episodes


def test_no_v0_1_semantic_identity_reuse():
    """Parsed-field non-overlap against the frozen v0_1 manifest (not substring)."""
    v1 = loadj(V1, "untouched_test_frame_manifest.json")["frames"]
    v2 = frames()
    v1_eps = {f["reserved_episode_id"] for f in v1}
    v2_eps = {f["reserved_episode_id"] for f in v2}
    assert v1_eps.isdisjoint(v2_eps)
    assert {f["frame_id"] for f in v1}.isdisjoint({f["frame_id"] for f in v2})
    assert {f["planned_source_relative_path"] for f in v1}.isdisjoint(
        {f["planned_source_relative_path"] for f in v2})
    assert {f["package_id"] for f in v1}.isdisjoint({f["package_id"] for f in v2})
    assert {f["visible_negative_pairing_id"] for f in v1}.isdisjoint(
        {f["visible_negative_pairing_id"] for f in v2})
    # parsed package id differs
    assert {parse_id(f["frame_id"])["package_id"] for f in v2} == {
        "person-c-phase3-detector-v1-untouched-test-v0_2"}


def test_no_historical_episode_reuse():
    """v0_2 episodes disjoint from every historical committed capture episode."""
    hist = set()
    auto = os.path.join(ROOT, "data/autonomous")
    for name in os.listdir(auto):
        for tok in name.replace("_", " ").split():
            if tok.startswith("ep") and tok[2:].isdigit():
                hist.add(int(tok[2:]))
    v2_eps = {f["reserved_episode_id"] for f in frames()}
    assert v2_eps.isdisjoint(hist), v2_eps & hist


# ---- detector outcomes unavailable / no image bytes ----
def test_detector_outcomes_unavailable_and_no_png():
    fr = frames()
    assert all(f["detector_outcome_unavailable"] is True for f in fr)
    assert all(f["test_only"] is True for f in fr)
    rec = loadj(V2, "untouched_test_predeclaration_receipt.json")
    assert rec["person_e_detector_not_run"] is True
    assert rec["u4_output_not_inspected"] is True and rec["no_png_created"] is True
    blob = load(V2, "untouched_test_frame_manifest.json").decode()
    for banned in ("centroid", "detected_present", "classification", "empirical", "confidence"):
        assert banned not in blob
    pngs = [f for _, _, fs in os.walk(V2) for f in fs if f.lower().endswith(".png")]
    assert pngs == []


def test_capture_requirements_fail_closed():
    cr = loadj(V2, "untouched_test_capture_requirements.json")
    rules = " ".join(cr["untouched_test_rules"]).lower()
    assert "all 48 predeclared rows are mandatory" in rules
    assert "no substitutions" in rules
    assert "no frame may be selected or replaced based on detector behavior" in rules
    assert "no v0_1 png bytes may be reused" in rules
    assert cr["duplicate_png_hashes_fail_closed"] is True
    assert cr["duplicate_negative_hashes_pre_authorized"] is False
    assert cr["capture_source_revision_must_postdate_this_predeclaration_commit"] is True


# ---- v0_1 retirement receipt ----
def test_v0_1_retirement_receipt():
    r = loadj(V1, "untouched_test_retirement_receipt.json")
    assert r["retired_package_id"] == "person-c-phase3-detector-v1-untouched-test-v0_1"
    assert r["person_e_detector_never_run"] is True
    assert r["no_detector_outcome_inspected"] is True
    assert r["no_u4_output_inspected"] is True
    assert r["no_v0_1_capture_package_committed"] is True
    assert r["frozen_duplicate_hash_rule_did_not_permit_acceptance"] is True
    assert r["no_post_capture_addendum_used_to_weaken_rule"] is True
    assert r["successor_package_id"] == "person-c-phase3-detector-v1-untouched-test-v0_2"
    assert "static" in r["retirement_reason"].lower()


def test_frozen_v0_1_predeclaration_unchanged():
    """The six frozen v0_1 JSON files are unchanged from commit 260f587."""
    for name in ("untouched_test_predeclaration.json", "untouched_test_frame_manifest.json",
                 "untouched_test_stratification_plan.json", "untouched_test_truth_authority.json",
                 "untouched_test_capture_requirements.json",
                 "untouched_test_predeclaration_receipt.json"):
        committed = subprocess.check_output([
            "git", "-C", ROOT, "show",
            ("260f5871f33090e786c6efaf2c704ab4189cc0c0:"
             f"data/handoff_e/phase3_detector_v1_untouched_test_v0_1/{name}")])
        assert load(V1, name) == committed, name


# ---- deterministic generation ----
def test_deterministic_byte_identical_generation():
    a = gen.build_v2()
    b = gen.build_v2()
    for name, obj in a.items():
        assert gen.canon(obj) == gen.canon(b[name])
        assert load(V2, name) == gen.canon(obj), name
    assert gen.canon(gen.build_retirement_receipt()) == \
        load(V1, "untouched_test_retirement_receipt.json")


def test_only_permitted_paths_changed():
    out = subprocess.check_output(
        ["git", "-C", ROOT, "diff", "--name-status",
         f"{V2_PREDECLARATION_COMMIT}^", V2_PREDECLARATION_COMMIT,
         "--", "data/handoff_e", "src", "tests", "configs", "schemas", "scripts"]).decode()
    for line in out.splitlines():
        if not line.strip():
            continue
        _status, path = line.split("\t", 1)
        ok = (path.startswith(("data/handoff_e/phase3_detector_v1_untouched_test_v0_2/",
                               "scripts/gen_phase3_untouched_predeclaration_v0_2.py",
                               "tests/handoff/"))
              or path == "data/handoff_e/phase3_detector_v1_untouched_test_v0_1/untouched_test_retirement_receipt.json")
        assert ok, f"unexpected change: {line!r}"
        # the six frozen v0_1 JSON must NOT be modified
        assert "v0_1/untouched_test_predeclaration" not in path or "retirement" in path


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
