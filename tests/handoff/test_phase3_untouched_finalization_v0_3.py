"""Phase 3 Detector v1 untouched-test v0_3 finalization proofs.

Validates the finalized capture package: exactly the 48 frozen manifest rows were
captured (24 present sheep at frame indices 3,7,11,15; 24 absent NoAI foreground
cows at frame 12), every PNG exists at its predeclared path with a matching hash,
and every Person E hash-category count holds — each absent final may equal ONLY
its own registered preview, with cross-row / present-preview / unmapped /
historical / v0_1 / v0_2 / forbidden-development / final-to-final overlaps all
fail-closed at zero. No detector output is referenced anywhere in the package.
"""
import hashlib
import json
import os
import sys

import pytest
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
V3 = os.path.join(ROOT, "data/handoff_e/phase3_detector_v1_untouched_test_v0_3")
PACKAGE_ID = "person-c-phase3-detector-v1-untouched-test-v0_3"

HARD_ZERO = [
    "UNAUTHORIZED_PREVIEW_HASH_OVERLAP", "PRESENT_PREVIEW_OVERLAP",
    "CROSS_ROW_PREVIEW_OVERLAP", "HISTORICAL_OVERLAP", "V0_1_OVERLAP",
    "V0_2_OVERLAP", "FORBIDDEN_DEVELOPMENT_OVERLAP", "FINAL_TO_FINAL_DUPLICATE",
]


def loadj(name):
    with open(os.path.join(V3, name), "rb") as f:
        return json.loads(f.read())


def manifest():
    return loadj("untouched_test_frame_manifest.json")["frames"]


def final_manifest():
    return loadj("untouched_test_final_manifest.json")


# ---- 48 frames captured exactly to the frozen manifest -------------------
def test_final_manifest_matches_frozen_manifest():
    fm = final_manifest()
    assert fm["package_id"] == PACKAGE_ID
    assert fm["frame_count"] == 48 and fm["present_count"] == 24 and fm["absent_count"] == 24
    frozen = {f["frame_id"]: f for f in manifest()}
    final = {f["frame_id"]: f for f in fm["frames"]}
    assert set(final) == set(frozen)  # exact identity set, no substitutions
    for fid, f in final.items():
        z = frozen[fid]
        assert f["reserved_episode_id"] == z["reserved_episode_id"]
        assert f["reserved_frame_index"] == z["reserved_frame_index"]
        assert f["truth_present"] == z["truth_present"]
        assert f["source_relative_path"] == z["planned_source_relative_path"]
        assert (f["width"], f["height"]) == (640, 360)


def test_present_absent_frame_indices():
    fm = final_manifest()["frames"]
    present = [f for f in fm if f["truth_present"]]
    absent = [f for f in fm if not f["truth_present"]]
    assert len(present) == 24 and len(absent) == 24
    assert {f["reserved_frame_index"] for f in present} == {3, 7, 11, 15}
    assert {f["reserved_frame_index"] for f in absent} == {12}
    assert {f["reserved_episode_id"] for f in present} == set(range(53001, 53007))
    assert {f["reserved_episode_id"] for f in absent} == set(range(53007, 53031))


def test_every_png_exists_and_hash_matches():
    fm = final_manifest()["frames"]
    seen = set()
    for f in fm:
        path = os.path.join(ROOT, f["source_relative_path"])
        assert os.path.exists(path), f["source_relative_path"]
        with open(path, "rb") as fh:
            data = fh.read()
        assert hashlib.sha256(data).hexdigest() == f["sha256"], f["frame_id"]
        with Image.open(path) as im:
            assert im.size == (640, 360)
        seen.add(f["sha256"])
    assert len(seen) == 48  # all distinct


def test_exactly_48_pngs_under_package():
    pngs = [os.path.join(r, x) for r, _, fs in os.walk(V3)
            for x in fs if x.lower().endswith(".png")]
    assert len(pngs) == 48


# ---- Person E hash-category counts --------------------------------------
def test_hash_overlap_report_counts():
    rep = loadj("untouched_test_hash_overlap_report.json")
    c = rep["counts"]
    assert c["AUTHORIZED_PREVIEW_EQUIVALENCE_REGISTER_COUNT"] == 24
    assert c["FINAL_ABSENT_MATCHED_OWN_REGISTERED_PREVIEW_COUNT"] + \
        c["FINAL_ABSENT_DIFFERED"] == 24
    for k in HARD_ZERO:
        assert c[k] == 0, k
    assert rep["violations"] == {}
    assert rep["person_e_detector_never_run"] is True


def test_duplicate_hash_report():
    rep = loadj("untouched_test_duplicate_hash_report.json")
    assert rep["final_to_final_duplicate_count"] == 0
    assert rep["final_to_final_duplicate_groups"] == {}
    assert rep["distinct_final_hashes"] == 48 and rep["total_final_frames"] == 48


def test_finalization_receipt():
    r = loadj("untouched_test_finalization_receipt.json")
    assert r["finalized"] is True and r["violations"] == {}
    assert r["person_c_scope_only"] is True
    assert r["person_e_detector_never_run"] is True
    assert r["no_detector_output_inspected"] is True
    assert r["frame_selection_authority"] == "person_c_geometry_only"
    for k in HARD_ZERO:
        assert r["counts"][k] == 0, k


def test_package_receipt():
    r = loadj("untouched_test_package_receipt.json")
    assert r["frame_count"] == 48 and r["present_count"] == 24 and r["absent_count"] == 24
    assert r["no_detector_outcome_used_for_selection"] is True
    assert r["capture_postdates_register_commit"] is True


# ---- truth authority: geometry only, no detector leakage -----------------
def test_truth_records_geometry_only():
    tr = loadj("untouched_test_truth_records.json")
    assert tr["authoritative_truth_source"] == "person_c_geometry"
    assert tr["detector_never_run"] is True and tr["u4_output_not_inspected"] is True
    recs = tr["records"]
    assert len(recs) == 48
    assert sum(r["truth_present"] for r in recs) == 24
    for r in recs:
        assert r["detector_outcome_unavailable"] is True and r["test_only"] is True
        # present rows carry the sheep; absent rows do not
        assert r["target_magenta_sheep_present"] is bool(r["truth_present"])


FINALIZATION_ARTIFACTS = (
    "untouched_test_final_manifest.json", "untouched_test_truth_records.json",
    "untouched_test_capture_provenance.json", "untouched_test_capture_commands.json",
    "untouched_test_hash_overlap_report.json", "untouched_test_duplicate_hash_report.json",
    "untouched_test_provenance_index.json", "untouched_test_package_receipt.json",
    "untouched_test_finalization_receipt.json",
)


def test_no_detector_output_terms_in_finalization_artifacts():
    # detector *output* values must never leak into finalization artifacts;
    # (disclosure receipts legitimately carry `detector_*_inspected: false` fields
    # and are excluded here — they are checked structurally elsewhere).
    banned = ("centroid", "detected_present", "empirical_magenta", "confidence",
              "precision", "recall", "true_positive", "false_positive",
              "rejection_reason", "tp_count", "fp_count")
    for name in FINALIZATION_ARTIFACTS:
        with open(os.path.join(V3, name), encoding="utf-8") as fh:
            text = fh.read().lower()
        for term in banned:
            assert term not in text, f"{term} in {name}"


# ---- absent finals bind to registered previews only ----------------------
def test_absent_finals_bind_to_own_or_are_novel():
    receipt = loadj("untouched_test_precapture_feasibility_receipt.json")
    reg = {row["v0_3_frame_id"]: row["preview_sha256"]
           for row in receipt["authorized_deterministic_equivalence_register"]}
    all_preview = set(reg.values()) | set(
        receipt["unmapped_preview_hashes_remain_hard_forbidden"])
    fm = {f["frame_id"]: f for f in final_manifest()["frames"]}
    for fid, own in reg.items():
        h = fm[fid]["sha256"]
        # may equal ONLY its own registered preview; never any other preview hash
        if h in all_preview:
            assert h == own, f"{fid} matched a non-own preview hash"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
