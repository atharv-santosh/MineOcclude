"""Phase 3 untouched-test v0_3 predeclaration + v0_2 retirement proofs.

v0_3 supersedes retired v0_2 (whose four sheep-depth cow positions were occluded
by the wall). Proves v0_3 binds exactly to E's frozen candidate, has the
balanced 48/24/24 structure with brand-new identities (no v0_1/v0_2/historical
reuse, by PARSED identity fields), gives every negative an exact FOREGROUND cow
distractor, discloses no detector outcomes, creates no image bytes, and
regenerates byte-identically.
"""
import json
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import gen_phase3_untouched_predeclaration_v0_3 as gen

V1 = os.path.join(ROOT, "data/handoff_e/phase3_detector_v1_untouched_test_v0_1")
V2 = os.path.join(ROOT, "data/handoff_e/phase3_detector_v1_untouched_test_v0_2")
V3 = os.path.join(ROOT, "data/handoff_e/phase3_detector_v1_untouched_test_v0_3")
V2_COMMIT = "b466c233c08502ce5b9a23f07729eb71a47dbbfb"
LAYOUTS = [f"layout_0{i}" for i in range(1, 7)]


def load(base, name):
    with open(os.path.join(base, name), "rb") as f:
        return f.read()


def loadj(base, name):
    return json.loads(load(base, name))


def frames():
    return loadj(V3, "untouched_test_frame_manifest.json")["frames"]


def committed_frames(base_rel):
    raw = subprocess.check_output(["git", "-C", ROOT, "show", f"{V2_COMMIT}:{base_rel}"])
    return json.loads(raw)["frames"]


def test_exact_person_e_freeze_binding():
    b = loadj(V3, "untouched_test_predeclaration.json")["person_e_candidate_binding"]
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
    pairs = {}
    for f in fr:
        pairs.setdefault(f["visible_negative_pairing_id"], []).append(f)
    assert len(pairs) == 24
    for members in pairs.values():
        assert len(members) == 2
        assert sorted(m["truth_class"] for m in members) == ["absent", "present"]
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
            "data/handoff_e/phase3_detector_v1_untouched_test_v0_3/frames/")


def test_every_absent_row_has_exact_foreground_cow_and_no_sheep():
    fr = frames()
    absent = [f for f in fr if f["truth_class"] == "absent"]
    assert len(absent) == 24
    for f in absent:
        assert f["target_magenta_sheep_present"] is False
        assert f["truth_present"] is False
        assert f["distractor_entity_type"] == "minecraft:cow"
        assert f["distractor_is_detection_target"] is False
        assert "foreground" in f["distractor_placement"]
        p = f["distractor_world_position"]
        assert set(p) == {"x", "y", "z"} and all(isinstance(v, (int, float)) for v in p.values())
        assert f["distractor_identity"].endswith(f["frame_id"].split("::")[-1])
    for lay in LAYOUTS:
        pos = [tuple(f["distractor_world_position"].values())
               for f in absent if f["layout_id"] == lay]
        assert len(pos) == 4 and len(set(pos)) == 4
    blob = load(V3, "untouched_test_predeclaration.json").decode().lower()
    assert "pig" in blob and "not used" in blob
    assert "minecraft:pig" not in json.dumps(fr)


def test_present_rows_target_sheep():
    present = [f for f in frames() if f["truth_class"] == "present"]
    assert len(present) == 24
    for f in present:
        assert f["target_magenta_sheep_present"] is True
        assert f["reserved_frame_index"] in (3, 7, 11, 15)


def test_new_session_and_episodes():
    fr = frames()
    assert {f["reserved_capture_session_id"] for f in fr} == {
        "person-c-phase3-untouched-test-v0_3-session-01"}
    eps = {f["reserved_episode_id"] for f in fr}
    assert eps == set(range(53001, 53031))
    assert eps.isdisjoint(set(range(51001, 51013)))   # not v0_1
    assert eps.isdisjoint(set(range(52001, 52031)))   # not v0_2


def test_no_v0_1_or_v0_2_semantic_identity_reuse():
    """Parsed-field non-overlap against the committed v0_1 AND v0_2 manifests."""
    v3 = frames()
    for base in ("data/handoff_e/phase3_detector_v1_untouched_test_v0_1/untouched_test_frame_manifest.json",
                 "data/handoff_e/phase3_detector_v1_untouched_test_v0_2/untouched_test_frame_manifest.json"):
        prev = committed_frames(base)
        assert {f["reserved_episode_id"] for f in prev}.isdisjoint({f["reserved_episode_id"] for f in v3})
        assert {f["frame_id"] for f in prev}.isdisjoint({f["frame_id"] for f in v3})
        assert {f["planned_source_relative_path"] for f in prev}.isdisjoint(
            {f["planned_source_relative_path"] for f in v3})
        assert {f["package_id"] for f in prev}.isdisjoint({f["package_id"] for f in v3})
        assert {f["visible_negative_pairing_id"] for f in prev}.isdisjoint(
            {f["visible_negative_pairing_id"] for f in v3})


def test_no_historical_episode_reuse():
    hist = set()
    auto = os.path.join(ROOT, "data/autonomous")
    for name in os.listdir(auto):
        for tok in name.replace("_", " ").split():
            if tok.startswith("ep") and tok[2:].isdigit():
                hist.add(int(tok[2:]))
    assert {f["reserved_episode_id"] for f in frames()}.isdisjoint(hist)


def test_detector_outcomes_unavailable_and_no_png():
    fr = frames()
    assert all(f["detector_outcome_unavailable"] is True for f in fr)
    assert all(f["test_only"] is True for f in fr)
    rec = loadj(V3, "untouched_test_predeclaration_receipt.json")
    assert rec["person_e_detector_not_run"] is True
    assert rec["u4_output_not_inspected"] is True and rec["no_png_created"] is True
    blob = load(V3, "untouched_test_frame_manifest.json").decode()
    for banned in ("centroid", "detected_present", "classification", "empirical", "confidence"):
        assert banned not in blob
    pngs = [f for _, _, fs in os.walk(V3) for f in fs if f.lower().endswith(".png")]
    assert pngs == []


def test_capture_requirements_fail_closed():
    cr = loadj(V3, "untouched_test_capture_requirements.json")
    rules = " ".join(cr["untouched_test_rules"]).lower()
    assert "all 48 predeclared rows are mandatory" in rules
    assert "no substitutions" in rules
    assert "no frame may be selected or replaced based on detector behavior" in rules
    assert "no v0_1 or v0_2 png bytes may be reused" in rules
    assert cr["duplicate_png_hashes_fail_closed"] is True
    assert cr["duplicate_negative_hashes_pre_authorized"] is False
    assert cr["capture_source_revision_must_postdate_this_predeclaration_commit"] is True


def test_v0_2_retirement_receipt():
    r = loadj(V2, "untouched_test_retirement_receipt.json")
    assert r["retired_package_id"] == "person-c-phase3-detector-v1-untouched-test-v0_2"
    assert r["person_e_detector_never_run"] is True
    assert r["no_detector_outcome_inspected"] is True
    assert r["no_u4_output_inspected"] is True
    assert r["no_v0_2_capture_package_committed"] is True
    assert r["frozen_duplicate_hash_rule_did_not_permit_acceptance"] is True
    assert r["no_post_capture_addendum_used_to_weaken_rule"] is True
    assert r["successor_package_id"] == "person-c-phase3-detector-v1-untouched-test-v0_3"
    assert "occlud" in r["retirement_reason"].lower()


def test_frozen_v0_1_and_v0_2_predeclarations_unchanged():
    """The six frozen v0_1 and six frozen v0_2 predeclaration JSON are unchanged."""
    for ver, base in (("v0_1", V1), ("v0_2", V2)):
        for name in ("untouched_test_predeclaration.json", "untouched_test_frame_manifest.json",
                     "untouched_test_stratification_plan.json", "untouched_test_truth_authority.json",
                     "untouched_test_capture_requirements.json",
                     "untouched_test_predeclaration_receipt.json"):
            rel = f"data/handoff_e/phase3_detector_v1_untouched_test_{ver}/{name}"
            committed = subprocess.check_output(["git", "-C", ROOT, "show", f"{V2_COMMIT}:{rel}"])
            assert load(base, name) == committed, rel


def test_deterministic_byte_identical_generation():
    a, b = gen.build_v3(), gen.build_v3()
    for name, obj in a.items():
        assert gen.canon(obj) == gen.canon(b[name])
        assert load(V3, name) == gen.canon(obj), name
    assert gen.canon(gen.build_v2_retirement_receipt()) == \
        load(V2, "untouched_test_retirement_receipt.json")


def test_only_permitted_paths_changed():
    out = subprocess.check_output(
        ["git", "-C", ROOT, "status", "--porcelain",
         "--", "data/handoff_e", "src", "tests", "configs", "schemas", "scripts"]).decode()
    for line in out.splitlines():
        if not line.strip():
            continue
        path = line[3:]
        ok = (path.startswith(("data/handoff_e/phase3_detector_v1_untouched_test_v0_3/",
                               "scripts/gen_phase3_untouched_predeclaration_v0_3.py",
                               "tests/handoff/"))
              or path == "data/handoff_e/phase3_detector_v1_untouched_test_v0_2/untouched_test_retirement_receipt.json")
        assert ok, f"unexpected change: {line!r}"


# ---- pre-capture feasibility receipt (documentation-only commit) ----
FEASIBILITY = "untouched_test_precapture_feasibility_receipt.json"
V3_PREDECL_COMMIT = "24791b155a8962adce451a804a2bad94165392cc"


def test_feasibility_receipt():
    r = loadj(V3, FEASIBILITY)
    assert r["package_id"] == "person-c-phase3-detector-v1-untouched-test-v0_3"
    assert r["owner"] == "Person C"
    assert r["purpose"] == "physical scene-feasibility validation only"
    assert r["preview_was_a_formal_test_capture"] is False
    assert r["preview_was_a_detector_evaluation"] is False
    assert r["person_e_detector_ever_executed"] is False
    assert r["detector_outcome_or_metric_inspected"] is False
    assert r["detector_mask_inspected"] is False
    assert r["detector_centroid_inspected"] is False
    assert r["detector_classification_inspected"] is False
    assert r["u4_output_inspected"] is False
    assert r["previews_quarantined_and_forbidden_from_formal_v0_3_package"] is True
    assert r["previews_are_not_eligible_for_person_e_evaluation"] is True
    assert r["no_test_result_was_learned_from_the_preview"] is True
    assert r["preview_paths_bytes_may_not_be_copied_renamed_transcoded_resized_or_reused"] is True
    assert r["all_final_48_png_byte_streams_must_be_created_after_this_documentation_commit"] is True
    assert r["final_capture_uses_only_episodes_53001_53030_and_the_exact_frozen_v0_3_manifest"] is True
    assert r["layouts_covered"] == LAYOUTS and r["cow_positions_checked_per_layout"] == 4
    assert isinstance(r["preview_frame_count"], int) and r["preview_frame_count"] > 0
    # deterministic-identity disclosure present and flags E confirmation
    d = r["deterministic_identity_disclosure"]
    assert d["requesting_person_e_confirmation_before_final_capture"] is True


def test_feasibility_deterministic_equivalence_register():
    r = loadj(V3, FEASIBILITY)
    reg = r["authorized_deterministic_equivalence_register"]
    assert r["authorized_preview_equivalence_register_count"] == 24
    assert len(reg) == 24
    absent = [f for f in frames() if f["truth_class"] == "absent"]
    absent_by_id = {f["frame_id"]: f for f in absent}
    assert {row["v0_3_frame_id"] for row in reg} == set(absent_by_id)  # exactly the 24 absent frames
    assert len({row["preview_sha256"] for row in reg}) == 24          # one distinct preview each
    for row in reg:
        f = absent_by_id[row["v0_3_frame_id"]]
        # binds the exact frozen identity
        assert row["layout_id"] == f["layout_id"]
        assert row["reserved_episode_id"] == f["reserved_episode_id"]
        assert row["reserved_frame_index"] == f["reserved_frame_index"]
        assert row["distractor_identity"] == f["distractor_identity"]
        assert row["cow_world_position"] == f["distractor_world_position"]
        assert row["canonical_camera_pose_id"] == f["canonical_camera_pose_id"]
        assert row["planned_final_png_path"] == f["planned_source_relative_path"]
        assert len(row["preview_sha256"]) == 64
        assert row["preview_feasibility_only"] is True
        assert row["person_e_detector_never_run"] is True
        assert row["preview_bytes_forbidden_from_copy_or_reuse"] is True
    # unmapped previews remain hard-forbidden; no overlap with the registered set
    mapped = {row["preview_sha256"] for row in reg}
    assert set(r["unmapped_preview_hashes_remain_hard_forbidden"]).isdisjoint(mapped)
    cats = r["hard_forbidden_hash_categories"]
    assert any("37 Detector v1 development" in c for c in cats)
    assert any("cross-row" in c for c in cats)
    assert any("present frame" in c for c in cats)
    sd = r["scientific_disclosure"]
    assert sd["set_remains_held_out_from_person_e_frozen_detector"] is True
    assert sd["no_claim_of_pixel_novelty_relative_to_person_c_feasibility_previews_is_made"] is True


def test_frozen_v0_3_six_predeclaration_json_unchanged():
    """The six frozen v0_3 predeclaration JSON are unchanged from 24791b1 (the
    feasibility receipt is a new 7th file, not a modification)."""
    for name in ("untouched_test_predeclaration.json", "untouched_test_frame_manifest.json",
                 "untouched_test_stratification_plan.json", "untouched_test_truth_authority.json",
                 "untouched_test_capture_requirements.json",
                 "untouched_test_predeclaration_receipt.json"):
        rel = f"data/handoff_e/phase3_detector_v1_untouched_test_v0_3/{name}"
        committed = subprocess.check_output(["git", "-C", ROOT, "show", f"{V3_PREDECL_COMMIT}:{rel}"])
        assert load(V3, name) == committed, rel


def test_no_png_under_committed_v0_3_package():
    pngs = [f for _, _, fs in os.walk(V3) for f in fs if f.lower().endswith(".png")]
    assert pngs == []


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
