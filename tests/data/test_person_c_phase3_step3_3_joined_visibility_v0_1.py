"""Focused tests for Person C's Phase 3 Step 3.3 joined-visibility package.

Committed-package assertions read the committed artifacts directly (portable).
build/validate exercise the generator against a git-materialized copy of Person
E's empirical package (commit 90855ea) — no external capture directory is
required. Structural fail-closed behavior is covered with synthetic fixtures
that never touch the committed C or E packages.
"""
import json
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "src"))
import build_person_c_phase3_step3_3_joined_visibility_v0_1 as mod

from mineocclude.data.visibility_join import (
    VisibilityJoinError,
    strict_join,
)

PKG = os.path.join(ROOT, mod.PKG_REL)
DET = mod.DETECTOR_VERSION
E_COMMIT = mod.PERSON_E_COMMIT
E_SUBDIR = mod.E_PKG_SUBDIR


def _loadj(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _rows(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def committed_joined():
    return _rows(os.path.join(PKG, "joined_visibility_records.jsonl"))


# --------------------------------------------------------------------------- #
# Portable Person E package root: materialize E's files from commit 90855ea.
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def e_root(tmp_path_factory):
    root = tmp_path_factory.mktemp("e_pkg")
    dst_dir = os.path.join(root, E_SUBDIR)
    os.makedirs(dst_dir, exist_ok=True)
    for name in ("empirical_visibility_records.jsonl", "detector_diagnostics.jsonl",
                 "sha256_inventory.json"):
        blob = subprocess.check_output(
            ["git", "-C", ROOT, "show", f"{E_COMMIT}:{E_SUBDIR}/{name}"])
        with open(os.path.join(dst_dir, name), "wb") as f:
            f.write(blob)
    return str(root)


# --------------------------------------------------------------------------- #
# synthetic minimal records (no 1,850 constraint) for strict_join-level checks
# --------------------------------------------------------------------------- #
def mkC(traj, idx, geo, layout="layout_01", pose="layout_01_canonical_pose_v1"):
    return {"trajectory_id": traj, "model_frame_idx": idx, "geometric_visible": geo,
            "layout_id": layout, "canonical_camera_pose_id": pose,
            "resolution": "640x360", "coordinate_convention": "pixel_center_xy_zero_based",
            "geometry_rule_version": "person-c-geometric-visibility-v0.1"}


def mkE(traj, idx, emp, layout="layout_01", pose="layout_01_canonical_pose_v1",
        res="640x360", coord="pixel_center_xy_zero_based", det=DET):
    return {"trajectory_id": traj, "model_frame_idx": idx, "empirical_magenta_visible": emp,
            "detector_version": det, "layout_id": layout, "canonical_camera_pose_id": pose,
            "resolution": res, "coordinate_convention": coord}


# ---- committed package: counts / keys / context ---------------------------
def test_committed_row_counts_and_unique_keys():
    joined = committed_joined()
    assert len(joined) == 1850
    keys = [(r["trajectory_id"], r["model_frame_idx"]) for r in joined]
    assert len(set(keys)) == 1850


def test_committed_key_equality_c_e_joined():
    c = _rows(os.path.join(ROOT, mod.GVR_REL))
    e = subprocess.check_output(
        ["git", "-C", ROOT, "show", f"{E_COMMIT}:{E_SUBDIR}/empirical_visibility_records.jsonl"]).decode()
    ek = {(r["trajectory_id"], r["model_frame_idx"]) for r in (json.loads(x) for x in e.splitlines() if x)}
    ck = {(r["trajectory_id"], r["model_frame_idx"]) for r in c}
    jk = {(r["trajectory_id"], r["model_frame_idx"]) for r in committed_joined()}
    assert ck == ek == jk and len(jk) == 1850


def test_committed_context_values_and_string_types():
    for r in committed_joined():
        assert r["resolution"] == "640x360" and isinstance(r["resolution"], str)
        assert r["coordinate_convention"] == "pixel_center_xy_zero_based"
        assert isinstance(r["coordinate_convention"], str)


# ---- committed package: AND rule + raw channels ---------------------------
def test_committed_and_rule_and_visible_flag_boolean():
    for r in committed_joined():
        assert isinstance(r["visible_flag"], bool)
        geo, emp = r["geometric_visible"], r["empirical_magenta_visible"]
        if geo is not None and emp is not None:
            assert r["visible_flag"] == (bool(geo) and bool(emp))


def test_committed_raw_channels_preserved_against_sources():
    c = {(r["trajectory_id"], r["model_frame_idx"]): r for r in _rows(os.path.join(ROOT, mod.GVR_REL))}
    e_txt = subprocess.check_output(
        ["git", "-C", ROOT, "show", f"{E_COMMIT}:{E_SUBDIR}/empirical_visibility_records.jsonl"]).decode()
    e = {(r["trajectory_id"], r["model_frame_idx"]): r
         for r in (json.loads(x) for x in e_txt.splitlines() if x)}
    for r in committed_joined():
        k = (r["trajectory_id"], r["model_frame_idx"])
        assert r["geometric_visible"] == c[k]["geometric_visible"]  # unflipped
        assert r["empirical_magenta_visible"] == e[k]["empirical_magenta_visible"]


def test_person_c_owns_visible_flag():
    for r in committed_joined():
        assert r["label_owner"] == "Person C"
    ab = _loadj(os.path.join(PKG, "authority_binding.json"))
    assert ab["final_label_owner"] == "Person C"
    assert ab["empirical_channel_owner"] == "Person E"


# ---- committed package: quarantine invariants + accounting ----------------
def test_committed_quarantine_invariants():
    for r in committed_joined():
        assert r["quarantine_category"] in mod.QUARANTINE_CATEGORIES
        assert (r["quarantine_category"] != "none") == r["quarantined"]
        if r["quarantined"]:
            assert r["visible_flag"] is False
        if r["visible_flag"]:
            assert r["quarantine_category"] == "none"


def test_committed_missing_detector_is_zero_and_no_rows_dropped():
    joined = committed_joined()
    assert sum(1 for r in joined if r["quarantine_category"] == "missing_detector") == 0
    assert len(joined) == 1850  # no row dropped


def test_committed_quarantine_and_layout_accounting_reconciles():
    qa = _loadj(os.path.join(PKG, "quarantine_accounting_report.json"))
    t = qa["total"]
    assert t["input_rows"] == 1850
    assert t["quarantined"] + t["non_quarantined"] == 1850
    cats = ("geometry_hidden_detector_visible", "geometry_visible_detector_hidden",
            "invalid_geometry", "missing_detector", "none")
    assert sum(t[c] for c in cats) == 1850
    assert sum(t[c] for c in cats if c != "none") == t["quarantined"]
    assert t["missing_detector"] == 0
    # per-layout totals sum to global
    per = qa["per_layout"]
    assert sum(v["input_rows"] for v in per.values()) == 1850
    for c in cats:
        assert sum(v[c] for v in per.values()) == t[c]
    assert sum(v["visible_flag_true"] for v in per.values()) == t["visible_flag_true"]


def test_committed_coverage_structural_zeros():
    cov = _loadj(os.path.join(PKG, "coverage_report.json"))
    for k in ("missing_e_keys", "extra_e_keys", "duplicate_c_keys", "duplicate_e_keys",
              "context_mismatches", "detector_version_mismatches", "malformed_empirical_values"):
        assert cov[k] == 0, k
    assert cov["produced_joined_rows"] == 1850 and cov["unique_joined_keys"] == 1850
    assert cov["joined_c_key_set_equality"] and cov["joined_e_key_set_equality"]
    assert cov["diagnostic_e_key_set_equality"]


# ---- committed package: no accuracy metrics, provenance, formatting -------
def test_no_accuracy_metrics_anywhere():
    banned = ("precision", "recall", "true_positive", "false_positive", "true_negative",
              "false_negative", "confusion", "\"tp\"", "\"fp\"", "\"tn\"", "\"fn\"", "f1_score")
    for name in os.listdir(PKG):
        with open(os.path.join(PKG, name), encoding="utf-8") as f:
            text = f.read().lower()
        for b in banned:
            assert b not in text, f"{b} in {name}"


def test_model_preprocessing_and_b_coordinate_bindings():
    ab = _loadj(os.path.join(PKG, "authority_binding.json"))
    assert ab["person_a_model_preprocessing_authority"]["commit"] == mod.PERSON_A_MODEL_PREPROC_AUTHORITY
    bc = ab["person_b_coordinate_authority"]
    assert bc["schema"] == "person-b-wall-parallel-frame-v0.1"
    assert bc["sha256"] == mod.PERSON_B_COORD_SHA
    assert bc["required_signoff"] == {"person_b": True, "person_c": True}
    prov = _loadj(os.path.join(PKG, "provenance_index.json"))
    assert prov["model_preprocessing_provenance"]["person_c_source_revision"] == mod.PERSON_C_SOURCE_REVISION


def test_deterministic_json_and_jsonl_formatting():
    for name in os.listdir(PKG):
        with open(os.path.join(PKG, name), "rb") as f:
            raw = f.read()
        assert raw[:3] != b"\xef\xbb\xbf" and raw.endswith(b"\n")
        if name.endswith(".json"):
            obj = json.loads(raw)
            assert raw == (json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
            assert obj.get("schema_version") == "1.0"
            assert mod.SCHEMA_ID in json.dumps(obj)
        elif name.endswith(".jsonl"):
            for line in raw.decode().splitlines():
                o = json.loads(line)
                assert line == json.dumps(o, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def test_phase3_status():
    s = _loadj(os.path.join(PKG, "phase3_status.json"))
    assert s["person_c_final_strict_join"] == "READY"
    assert s["person_b_final_joined_package_validation"] == "PENDING"
    assert s["overall_phase3"] == "IN_PROGRESS"
    assert s["u4_output_inspected"] is False


# ---- build + validate against the git-materialized E package --------------
def test_build_matches_committed_and_validate_only_passes(e_root, tmp_path):
    files, joined, _ = mod.generate(e_root, out_dir=None, command="test")
    assert len(joined) == 1850
    # deterministic artifacts equal the committed ones byte-for-byte
    for rel in mod.DETERMINISTIC_ARTIFACTS:
        with open(os.path.join(PKG, rel), "rb") as f:
            assert f.read() == files[rel], rel
    mod.validate(e_root, PKG, command="test")  # raises on failure


def test_validate_detects_tampered_row(e_root, tmp_path):
    import shutil
    clone = tmp_path / "clone"
    shutil.copytree(PKG, clone)
    recs = _rows(str(clone / "joined_visibility_records.jsonl"))
    recs[0]["visible_flag"] = not recs[0]["visible_flag"]
    with open(clone / "joined_visibility_records.jsonl", "w", encoding="utf-8") as f:
        f.writelines(json.dumps(r, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n" for r in recs)
    with pytest.raises(mod.JoinPackageError):
        mod.validate(e_root, str(clone), command="test")


# ---- strict_join-level structural fail-closed (synthetic) -----------------
def test_and_truth_table():
    c = [mkC("t", 0, True), mkC("t", 1, True), mkC("t", 2, False), mkC("t", 3, False)]
    e = [mkE("t", 0, True), mkE("t", 1, False), mkE("t", 2, True), mkE("t", 3, False)]
    out = {r["model_frame_idx"]: r for r in strict_join(c, e, expected_detector_version=DET)}
    assert out[0]["visible_flag"] is True and out[0]["quarantine_category"] == "none"
    assert out[1]["visible_flag"] is False and out[1]["quarantine_category"] == "geometry_visible_detector_hidden"
    assert out[2]["visible_flag"] is False and out[2]["quarantine_category"] == "geometry_hidden_detector_visible"
    assert out[3]["visible_flag"] is False and out[3]["quarantine_category"] == "none"
    for r in out.values():
        if r["quarantine_category"] != "none":
            assert r["quarantined"] is True and r["visible_flag"] is False


def test_invalid_geometry_and_missing_detector_categories():
    c = [mkC("t", 0, None), mkC("t", 1, True)]
    e = [mkE("t", 0, True), mkE("t", 1, None)]
    out = {r["model_frame_idx"]: r for r in strict_join(c, e, expected_detector_version=DET)}
    assert out[0]["quarantine_category"] == "invalid_geometry" and out[0]["visible_flag"] is False
    assert out[1]["quarantine_category"] == "missing_detector" and out[1]["visible_flag"] is False


def test_e_visible_flag_fails_closed():
    c = [mkC("t", 0, True)]
    e = [mkE("t", 0, True)]
    e[0]["visible_flag"] = True
    with pytest.raises(VisibilityJoinError):
        strict_join(c, e, expected_detector_version=DET)


def test_duplicate_c_and_e_fail_closed():
    with pytest.raises(VisibilityJoinError):
        strict_join([mkC("t", 0, True), mkC("t", 0, True)], [mkE("t", 0, True)], expected_detector_version=DET)
    with pytest.raises(VisibilityJoinError):
        strict_join([mkC("t", 0, True)], [mkE("t", 0, True), mkE("t", 0, True)], expected_detector_version=DET)


def test_missing_and_extra_e_fail_closed():
    with pytest.raises(VisibilityJoinError):  # C without E
        strict_join([mkC("t", 0, True), mkC("t", 1, True)], [mkE("t", 0, True)], expected_detector_version=DET)
    with pytest.raises(VisibilityJoinError):  # E without C
        strict_join([mkC("t", 0, True)], [mkE("t", 0, True), mkE("t", 9, True)], expected_detector_version=DET)


def test_wrong_detector_version_fails_closed():
    with pytest.raises(VisibilityJoinError):
        strict_join([mkC("t", 0, True)], [mkE("t", 0, True, det="other-detector")],
                    expected_detector_version=DET)


@pytest.mark.parametrize("field,badval", [
    ("layout_id", "layout_99"),
    ("canonical_camera_pose_id", "layout_99_canonical_pose_v1"),
    ("resolution", "1280x720"),
    ("coordinate_convention", "top_left_origin"),
])
def test_context_mismatch_fails_closed(field, badval):
    c = [mkC("t", 0, True)]
    e = [mkE("t", 0, True)]
    e[0][field] = badval
    with pytest.raises(VisibilityJoinError):
        strict_join(c, e, expected_detector_version=DET)


# ---- E field-discipline fail-closed (synthetic, generator helper) ---------
def test_malformed_empirical_and_field_discipline_fail_closed():
    good = mkE("t", 0, True)
    mod.assert_e_record_discipline(good)  # ok
    bad = dict(good); bad["empirical_magenta_visible"] = "yes"  # non-bool
    with pytest.raises(mod.JoinPackageError):
        mod.assert_e_record_discipline(bad)
    extra = dict(good); extra["blob_area"] = 1.0  # extra/forbidden field
    with pytest.raises(mod.JoinPackageError):
        mod.assert_e_record_discipline(extra)
    vf = dict(good); vf["visible_flag"] = True
    with pytest.raises(mod.JoinPackageError):
        mod.assert_e_record_discipline(vf)


# ---- U4 rejection + pre-existing immutability -----------------------------
def test_u4_source_root_rejected(monkeypatch):
    monkeypatch.setattr(sys, "argv",
                        ["x", "build", "--e-package-root", "/data/mineocclude_u4/out"])
    assert mod.main() == 2


def test_pre_existing_c_authorities_unchanged():
    for rel in (mod.GVR_REL, mod.FINAL_INTERFACE_REL, mod.IMPORT_CONTRACT_REL,
                mod.DISAGREEMENT_REL, mod.PERSON_B_COORD_PATH,
                "src/mineocclude/data/visibility_join.py"):
        committed = subprocess.check_output(["git", "-C", ROOT, "show", f"HEAD:{rel}"])
        with open(os.path.join(ROOT, rel), "rb") as f:
            assert f.read() == committed, rel


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
