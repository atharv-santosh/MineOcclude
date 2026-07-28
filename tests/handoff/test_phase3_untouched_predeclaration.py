"""Phase 3 Detector v1 UNTOUCHED-TEST predeclaration (Person C -> Person E).

Proves the predeclaration binds exactly to Person E's frozen candidate, has the
mandated 48/24/24 structure with unique brand-new identities, discloses no
detector outcomes, creates no image bytes, and regenerates byte-identically.
"""
import hashlib
import json
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import gen_phase3_untouched_predeclaration as gen  # noqa: E402

PKG = os.path.join(ROOT, "data/handoff_e/phase3_detector_v1_untouched_test_v0_1")


def load(name):
    with open(os.path.join(PKG, name), "rb") as f:
        return f.read()


def loadj(name):
    return json.loads(load(name))


FRAMES = property  # placeholder to keep flake quiet


def frames():
    return loadj("untouched_test_frame_manifest.json")["frames"]


# ---- exact E freeze / version / hash binding ----
def test_exact_person_e_freeze_binding():
    b = loadj("untouched_test_predeclaration.json")["person_e_candidate_binding"]
    assert b["person_e_freeze_commit"] == "3930669eddc026ecb081e947f71f1855a7415904"
    assert b["detector_version"] == (
        "hsv-largest-valid-blob-v1.0-candidate:sha256:"
        "0cadf618fca1578196bde4982021c38627ccb9c39e46353812e7da3fce6aa125")
    assert b["detector_identity_sha256"] == "0cadf618fca1578196bde4982021c38627ccb9c39e46353812e7da3fce6aa125"
    assert b["detector_config_sha256"] == "acfecd659958891eaee0d582c946abdfaaf47d1ab3307a24f7652e634c045bfa"
    assert b["detector_settings_sha256"] == "0dbb426adf99f53455eea04c4aaeb56f3cb22cbc351d87269bb605445eb8f2ea"
    assert b["detector_implementation_sha256"] == "026f3b9f25c8aef7ac43fada5b8de92662b605af4868f930698651e59a228214"
    assert b["freeze_timestamp_utc"] == "2026-07-28T06:03:15Z"


def test_binding_matches_person_e_freeze_commit_record():
    """The bound hashes equal what E actually committed in the freeze record."""
    raw = subprocess.check_output([
        "git", "-C", ROOT, "show",
        "3930669eddc026ecb081e947f71f1855a7415904:docs/status/"
        "person_e_phase3_step3_1_candidate_freeze_v0_1/detector_candidate_version_record.json"])
    rec = json.loads(raw)
    b = loadj("untouched_test_predeclaration.json")["person_e_candidate_binding"]
    assert b["detector_identity_sha256"] == rec["detector_identity_sha256"]
    assert b["detector_config_sha256"] == rec["detector_config_sha256"]
    assert b["detector_settings_sha256"] == rec["detector_settings_sha256"]
    assert b["detector_implementation_sha256"] == rec["detector_implementation_sha256"]
    assert b["freeze_timestamp_utc"] == rec["freeze_timestamp_utc"]


# ---- structure: 48 / 24 / 24, per-layout 4+4, six layouts ----
def test_counts_and_per_layout():
    fr = frames()
    assert len(fr) == 48
    assert sum(f["truth_present"] is True for f in fr) == 24
    assert sum(f["truth_present"] is False for f in fr) == 24
    layouts = {f"layout_0{i}" for i in range(1, 7)}
    assert {f["layout_id"] for f in fr} == layouts
    for lay in layouts:
        lf = [f for f in fr if f["layout_id"] == lay]
        assert sum(f["truth_class"] == "present" for f in lf) == 4
        assert sum(f["truth_class"] == "absent" for f in lf) == 4
    dec = loadj("untouched_test_predeclaration.json")["counts"]
    assert dec == {"total_frames": 48, "truth_present": 24, "truth_absent": 24,
                   "layouts": 6, "present_per_layout": 4, "absent_per_layout": 4}


def test_48_unique_frame_identities():
    fr = frames()
    assert len({f["frame_id"] for f in fr}) == 48
    # (session, episode, frame_index) is a unique physical identity
    phys = {(f["reserved_capture_session_id"], f["reserved_episode_id"],
             f["reserved_frame_index"]) for f in fr}
    assert len(phys) == 48
    assert len({f["planned_source_relative_path"] for f in fr}) == 48


def test_resolution_and_pose():
    fr = frames()
    for f in fr:
        assert (f["width"], f["height"]) == (640, 360)
        assert f["canonical_camera_pose_id"] == f"{f['layout_id']}_canonical_pose_v1"
        assert f["coordinate_convention"] == "pixel_center_xy_zero_based"


# ---- no historical identity / hash reuse ----
def test_no_historical_episode_reuse():
    fr = frames()
    reserved = {f["reserved_episode_id"] for f in fr}
    historical = set(gen.historical_c_episode_ids())
    assert reserved.isdisjoint(historical), reserved & historical
    assert all(50000 < e < 52000 for e in reserved)  # brand-new reserved range


def test_capture_requirements_forbid_reuse_and_bind_forbidden_hashes():
    cr = loadj("untouched_test_capture_requirements.json")
    # exactly Person E's 36 forbidden development hashes, bound
    raw = subprocess.check_output([
        "git", "-C", ROOT, "show",
        "3930669eddc026ecb081e947f71f1855a7415904:docs/status/"
        "person_e_phase3_step3_1_candidate_freeze_v0_1/new_untouched_test_requirements.json"])
    forb = sorted(json.loads(raw)["forbidden_development_source_sha256"])
    assert cr["forbidden_development_source_sha256"] == forb
    assert len(forb) == 37
    assert cr["captured_bytes_must_not_match_forbidden_development_hashes"] is True
    assert cr["captured_bytes_must_not_match_any_historical_c_hash"] is True


# ---- detector outcomes unavailable / not disclosed ----
def test_detector_outcomes_unavailable():
    fr = frames()
    assert all(f["detector_outcome_unavailable"] is True for f in fr)
    assert all(f["test_only"] is True for f in fr)
    rec = loadj("untouched_test_predeclaration_receipt.json")
    assert rec["person_e_detector_not_run"] is True
    assert rec["u4_output_not_inspected"] is True
    assert rec["no_png_created"] is True
    # no detector-outcome-like fields anywhere in the manifest
    blob = load("untouched_test_frame_manifest.json").decode()
    for banned in ("centroid", "detected", "classification", "detector_outcome\":", "mask", "confidence"):
        assert banned not in blob


def test_truth_from_c_geometry_only():
    ta = loadj("untouched_test_truth_authority.json")
    assert ta["person_e_detector_output_used_for_truth"] is False
    assert "geometr" in ta["rules"]["truth_present"].lower()


# ---- all frames mandatory / capture-after-commit ----
def test_all_frames_mandatory_and_capture_after_commit():
    cr = loadj("untouched_test_capture_requirements.json")
    rules = " ".join(cr["untouched_test_rules"]).lower()
    assert "all 48 predeclared rows are mandatory" in rules
    assert "no frame may be removed" in rules
    assert "no substitutions" in rules
    assert cr["capture_source_revision_must_postdate_this_predeclaration_commit"] is True
    assert cr["source_commit_must_postdate_freeze"] is True
    assert loadj("untouched_test_predeclaration.json")["created_after_person_e_freeze"] is True


# ---- no image bytes created ----
def test_no_image_files_created():
    pngs = []
    for dirpath, _, files in os.walk(PKG):
        pngs += [f for f in files if f.lower().endswith((".png", ".jpg", ".jpeg", ".bmp", ".webp"))]
    assert pngs == []
    assert loadj("untouched_test_predeclaration.json")["no_image_bytes_created"] is True


# ---- deterministic byte-identical generation ----
def test_deterministic_byte_identical_generation(tmp_path):
    gen.write_all(str(tmp_path))
    for name, obj in gen.build_all().items():
        committed = load(name)
        regenerated = (tmp_path / name).read_bytes()
        assert committed == regenerated == gen.canonical_bytes(obj), name
    # receipt file-hashes match recomputed canonical bytes
    rec = loadj("untouched_test_predeclaration_receipt.json")
    for name, h in rec["predeclared_file_sha256"].items():
        assert hashlib.sha256(load(name)).hexdigest() == h, name


# ---- existing C evidence unchanged (only the new package dir added) ----
def test_only_new_package_paths_changed():
    """Existing tracked C evidence is unchanged: every working-tree change under
    the sensitive paths is an ADDITION (untracked), never a modification or
    deletion of an existing tracked file."""
    out = subprocess.check_output(
        ["git", "-C", ROOT, "status", "--porcelain",
         "--", "data/handoff_e", "src", "tests", "configs", "schemas"]).decode()
    for line in out.splitlines():
        if not line.strip():
            continue
        status = line[:2]
        assert status == "??", f"existing evidence modified/deleted: {line!r}"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
