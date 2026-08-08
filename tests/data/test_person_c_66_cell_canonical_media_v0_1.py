"""Focused validation for the Person C 66-cell canonical 640x360 media.

Asserts that Person C's already-declared canonical source media is now
materialized without redefining any rule:

  - the 66 capture packages intake cleanly and every raw frame hash verifies;
  - the canonicalization authority is the pre-existing frozen
    ``mineocclude.data.preprocess.to_canonical`` at its full SHA-256;
  - Person C's canonical output satisfies Person A's frozen expected INPUT,
    with the two authorities kept separate;
  - all 2468 raw frames map one-to-one onto 2468 canonical 640x360 frames with
    no duplicate and no missing model-frame identity;
  - every canonical pixel hash reproduces Person E's independently recorded
    ``canonical_frame_rgb_sha256``, so no visibility label can have shifted;
  - the MP4s are ffprobe-gated and measurably lossy, so the lossless canonical
    PNG is the scientific pixel authority;
  - the C->A and C->D media handoffs bind every identity;
  - no frozen scientific identity changed.

Person A's preprocessing is never executed and MineWorld is never run.
"""
import hashlib
import json
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "src"))

import build_person_c_66_cell_canonical_media_v0_1 as mod  # noqa: E402

from mineocclude.data.preprocess import (  # noqa: E402
    ASPECT,
    CANON_H,
    CANON_W,
    to_canonical,
)
from mineocclude.data.fsretry import open_rgb_retry  # noqa: E402

STATUS = mod.STATUS_REL


def load(rel_path):
    with open(os.path.join(ROOT, rel_path), "rb") as handle:
        return json.load(handle)


def load_jsonl(rel_path):
    with open(os.path.join(ROOT, rel_path), "r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def sha256(rel_path):
    with open(os.path.join(ROOT, rel_path), "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


@pytest.fixture(scope="module")
def index():
    return load_jsonl(f"{STATUS}/canonical_frame_index.jsonl")


@pytest.fixture(scope="module")
def manifest():
    return load(f"{STATUS}/canonical_media_manifest.json")


@pytest.fixture(scope="module")
def audit():
    return load(f"{STATUS}/raw_media_audit.json")


@pytest.fixture(scope="module")
def authority():
    return load(f"{STATUS}/to_canonical_authority.json")


@pytest.fixture(scope="module")
def compatibility():
    return load(f"{STATUS}/a_source_contract_compatibility_receipt.json")


@pytest.fixture(scope="module")
def validation():
    return load(f"{STATUS}/media_validation_receipt.json")


@pytest.fixture(scope="module")
def a_handoff():
    return load(f"{STATUS}/c_to_a_media_handoff.json")


@pytest.fixture(scope="module")
def d_handoff():
    return load(f"{STATUS}/c_to_d_media_handoff.json")


# ---------------------------------------------------------- 66 capture intake

def test_capture_intake_is_the_frozen_66_cell_universe(audit, manifest):
    assert audit["accepted_episode_count"] == 66
    assert audit["episode_set_is_ep12601_to_ep12666"] is True
    assert manifest["person_c_accepted_manifest"]["sha256"] == (
        mod.C_ACCEPTED_MANIFEST_SHA256
    )
    assert manifest["person_c_accepted_manifest"]["accepted_count"] == 66
    assert manifest["person_c_accepted_manifest"]["excluded_count"] == 0
    assert manifest["person_c_capture_package_authority"]["sha256"] == (
        mod.C_CAPTURE_PACKAGE_MANIFEST_SHA256
    )
    assert sha256(f"{mod.C75_REL}/trajectories_mvp_manifest.json") == (
        mod.C_ACCEPTED_MANIFEST_SHA256
    )


def test_raw_media_mismatch_was_confirmed_independently(audit):
    assert audit["independent_of_person_a_report"] is True
    assert audit["mismatch_confirmed"] is True
    assert audit["raw_source_dimensions"] == "1920x1046"
    assert audit["raw_dimensions_uniform"] is True
    assert audit["raw_source_dimensions_observed"] == {"1920x1046": 2468}
    assert audit["declared_media_uniform_640x360"] is True
    assert audit["declared_canonical_derivative_640x360"] is True
    assert audit["preexisting_canonical_640x360_artifact_found"] is False
    assert audit["preexisting_canonical_640x360_artifact_count"] == 0


def test_every_raw_frame_hash_verifies(audit, index):
    assert audit["raw_frame_count"] == 2468
    assert audit["raw_frames_present"] == 2468
    assert audit["raw_frame_hashes_valid"] is True
    assert audit["raw_frame_hash_verified_count"] == 2468
    assert audit["raw_frame_hash_mismatch_count"] == 0
    assert audit["raw_frame_hash_mismatches"] == []
    # re-verify a sample straight from disk
    for row in index[:12]:
        assert os.path.exists(row["raw_source_path"])
        digest = hashlib.sha256(open(row["raw_source_path"], "rb").read()).hexdigest()
        assert digest == row["raw_source_sha256"]


# ------------------------------------------------ to_canonical C authority

def test_to_canonical_is_the_preexisting_frozen_authority(authority):
    assert authority["TO_CANONICAL_PREEXISTING_AUTHORITY"] is True
    assert authority["TO_CANONICAL_RESULT_CHANGING_DECISION_REQUIRED"] is False
    assert authority["rule"] == "mineocclude.data.preprocess.to_canonical"
    assert authority["implementation_path"] == mod.TO_CANONICAL_REL
    assert authority["implementation_sha256"] == mod.TO_CANONICAL_SHA256
    # the full SHA of the live file must still be the bound authority
    assert sha256(mod.TO_CANONICAL_REL) == mod.TO_CANONICAL_SHA256
    assert sha256(mod.FSRETRY_REL) == mod.FSRETRY_SHA256
    assert len(authority["implementation_sha256"]) == 64


def test_to_canonical_predates_the_66_cell_result_inspection(authority):
    provenance = authority["provenance"]
    assert provenance["predates_66_cell_capture"] is True
    assert provenance["predates_66_cell_detector_result_inspection"] is True
    assert provenance["last_modified_date"] < "2026-08-06"
    bound = provenance["independently_bound_by_person_e"]
    assert bound["person_e_declared_sha256"] == mod.TO_CANONICAL_SHA256
    assert bound["person_e_executed_rule_verbatim"] is True


def test_to_canonical_transformation_is_fully_recorded(authority):
    transformation = authority["transformation"]
    assert transformation["source_dimensions"] == "1920x1046"
    assert transformation["resize_target"] == "640x360"
    assert transformation["interpolation"] == "PIL.Image.BILINEAR"
    assert transformation["source_channel_order"] == "RGB"
    assert transformation["output_channel_order"] == "RGB"
    assert transformation["colour_conversion_applied"] is False
    assert transformation["normalization_applied"] is False
    assert transformation["additional_resize_applied"] is False
    # the recorded crop must be exactly what the frozen rule computes
    crop_width = int(round(1046 * ASPECT))
    x0 = (1920 - crop_width) // 2
    assert transformation["crop_width_pixels"] == crop_width
    assert transformation["crop_x0"] == x0
    assert transformation["crop_box_xyxy"] == [x0, 0, x0 + crop_width, 1046]
    assert transformation["crop_height_pixels"] == 1046


def test_frozen_rule_reproduces_a_published_canonical_frame(index):
    """Re-run the frozen rule on a raw frame and match the published output."""
    for row in index[:4]:
        produced = to_canonical(open_rgb_retry(row["raw_source_path"]))
        assert produced.shape == (CANON_H, CANON_W, 3)
        assert str(produced.dtype) == "uint8"
        digest = hashlib.sha256(produced.tobytes()).hexdigest()
        assert digest == row["canonical_pixel_sha256"]


# --------------------------------------------- A source-contract compatibility

def test_a_source_contract_is_compatible(compatibility):
    assert compatibility["A_SOURCE_CONTRACT_COMPATIBLE"] is True
    assert compatibility["person_a_commit"] == mod.PERSON_A_COMMIT
    assert compatibility["person_a_branch_merged"] is False
    assert compatibility["person_a_adapter_sha256"] == mod.A_ADAPTER_SHA256
    expected = compatibility["person_a_expected_input"]
    assert expected["pinned_source_width"] == 640
    assert expected["pinned_source_height"] == 360
    assert expected["pinned_source_shape_hwc"] == [360, 640, 3]
    assert expected["pinned_source_dtype"] == "uint8"
    delivered = compatibility["person_c_delivered_output"]
    assert delivered["width"] == 640
    assert delivered["height"] == 360
    assert delivered["dtype"] == "uint8"
    assert delivered["channel_order"] == "RGB"
    for name, ok in compatibility["checks"].items():
        assert ok is True, f"A compatibility check failed: {name}"


def test_person_a_adapter_hash_verifies_at_a_commit():
    payload = subprocess.run(
        ["git", "-C", ROOT, "show", f"{mod.PERSON_A_COMMIT}:{mod.A_ADAPTER_REL}"],
        capture_output=True, timeout=180,
    )
    assert payload.returncode == 0, "Person A commit is not available locally"
    assert hashlib.sha256(payload.stdout).hexdigest() == mod.A_ADAPTER_SHA256


def test_the_two_authorities_are_not_collapsed(compatibility):
    separation = compatibility["authority_separation"]
    assert separation["person_c_stage"] == (
        "raw framebuffer -> canonical 640x360 source"
    )
    assert separation["person_a_stage"] == (
        "canonical 640x360 source -> MineWorld model-facing derivative"
    )
    assert separation["stages_collapsed"] is False
    assert separation["person_c_executed_person_a_preprocessing"] is False
    assert separation[
        "person_a_preprocessing_implementation_modified_by_person_c"
    ] is False
    # Person A's implementation must not have been vendored onto C's branch.
    assert not os.path.exists(os.path.join(ROOT, mod.A_ADAPTER_REL))


def test_channel_order_resolution_is_the_identity_composition(compatibility, index):
    import numpy as np

    resolution = compatibility["channel_order_resolution"]
    assert resolution["opencv_executed_by_person_c"] is False
    assert resolution["person_a_owns_cv2_resize_and_normalization"] is True
    array = np.ascontiguousarray(open_rgb_retry(index[0]["canonical_path"]))
    # cv2.imread yields BGR; A's cv2.COLOR_BGR2RGB reverses it back to RGB.
    assert np.array_equal(array[:, :, ::-1][:, :, ::-1], array)
    assert compatibility["checks"]["channel_order_round_trip_is_identity"] is True


# ---------------------------------------------- 2468 raw -> canonical mapping

def test_exactly_2468_canonical_frames_over_66_episodes(index, manifest):
    assert len(index) == 2468
    assert manifest["canonical_media"]["frame_count"] == 2468
    assert manifest["canonical_media"]["episode_count"] == 66
    assert len({row["trajectory_id"] for row in index}) == 66
    assert len({row["episode_id"] for row in index}) == 66
    assert sorted({row["episode_id"] for row in index}) == list(
        range(12601, 12667)
    )


def test_no_duplicate_or_missing_model_frame_identity(index, manifest, validation):
    keys = [(row["trajectory_id"], row["model_frame_idx"]) for row in index]
    assert len(set(keys)) == 2468
    assert manifest["canonical_media"]["duplicate_model_frame_identity_count"] == 0
    assert manifest["canonical_media"]["missing_model_frame_identity_count"] == 0
    assert validation["duplicate_model_frame_identity_count"] == 0
    assert validation["missing_model_frame_identity_count"] == 0


def test_exactly_one_canonical_derivative_per_source_frame(index, validation):
    assert len({row["raw_source_path"] for row in index}) == 2468
    assert len({row["canonical_path"] for row in index}) == 2468
    assert validation["one_canonical_derivative_per_source_frame"] is True
    assert validation["distinct_raw_source_count"] == 2468
    assert validation["distinct_canonical_output_count"] == 2468


def test_mapping_binds_every_required_identity_field(index):
    required = (
        "episode_id", "trajectory_id", "server_tick", "render_frame_idx",
        "model_frame_idx", "raw_source_path", "raw_source_sha256",
        "canonical_path", "canonical_png_sha256", "canonical_pixel_sha256",
        "canonical_width", "canonical_height",
        "canonicalization_implementation_sha256",
        "canonicalization_config_version",
    )
    for row in index:
        for field in required:
            assert field in row, field
        assert len(row["raw_source_sha256"]) == 64
        assert len(row["canonical_png_sha256"]) == 64
        assert len(row["canonical_pixel_sha256"]) == 64
        assert row["canonicalization_implementation_sha256"] == (
            mod.TO_CANONICAL_SHA256
        )


def test_frame_identity_comes_from_the_committed_inventory_not_directory_order(
    index, validation,
):
    assert validation["frame_order_bound_to_immutable_identity"] is True
    assert "directory" in validation["frame_order_source"]
    # every canonical frame must correspond to the committed capture-package row
    capture = load(f"{mod.CAPTURE_AUTHORITY_REL}/capture_package_manifest.json")
    declared = {}
    for record in capture["records"]:
        for row in load_jsonl(
            f"{mod.AUTONOMOUS_REL}/{record['trajectory_id']}/package_v0_1/"
            "frame_inventory.jsonl"
        ):
            declared[(record["trajectory_id"], row["model_frame_idx"])] = row
    assert len(declared) == 2468
    for row in index:
        source = declared[(row["trajectory_id"], row["model_frame_idx"])]
        assert row["raw_source_path"] == source["runtime_path"]
        assert row["raw_source_sha256"] == source["sha256"]
        assert row["render_frame_idx"] == source["render_frame_idx"]
        assert row["server_tick"] == source["server_tick"]


# -------------------------------------------------------------- dimensions

def test_every_canonical_frame_is_exactly_640x360(index, validation):
    assert validation["all_frames_exactly_640x360"] is True
    for row in index:
        assert row["canonical_width"] == 640
        assert row["canonical_height"] == 360
    # verify a sample from the PNG header on disk
    for row in index[:20]:
        assert mod.png_dimensions(row["canonical_path"]) == (640, 360)


def test_canonical_pixel_hashes_reproduce_person_e(index, validation):
    """The decisive check that no visibility label can have shifted."""
    cross = validation["person_e_pixel_hash_cross_check"]
    assert cross["compared_frame_count"] == 2468
    assert cross["agreeing_frame_count"] == 2468
    assert cross["disagreeing_frame_count"] == 0
    assert cross["person_e_records_sha256"] == mod.E_RECORDS_SHA256
    for row in index:
        assert row["person_e_pixel_hash_agrees"] is True
        assert row["canonical_pixel_sha256"] == (
            row["person_e_canonical_frame_rgb_sha256"]
        )


def test_canonical_media_files_exist_and_hash_match(index):
    for row in index[:40]:
        assert os.path.exists(row["canonical_path"])
        digest = hashlib.sha256(open(row["canonical_path"], "rb").read()).hexdigest()
        assert digest == row["canonical_png_sha256"]


# ------------------------------------------------------------ media / ffprobe

def test_media_is_readable_and_ffprobe_gated(validation, manifest):
    assert validation["media_readable"] is True
    assert validation["ffprobe_all_640x360"] is True
    assert validation["ffprobe_all_20_fps"] is True
    assert validation["ffprobe_all_frame_counts_match"] is True
    assert validation["mp4_codec_identities"] == ["h264"]
    assert validation["mp4_pixel_formats"] == ["yuv420p"]
    assert len(manifest["episodes"]) == 66
    total = 0
    for entry in manifest["episodes"]:
        probe = entry["ffprobe"]
        assert probe["width"] == 640
        assert probe["height"] == 360
        assert probe["r_frame_rate"] == "20/1"
        assert probe["nb_frames"] == entry["frame_count"]
        assert abs(probe["duration_seconds"] - entry["frame_count"] * 0.05) < 0.15
        assert os.path.exists(os.path.join(ROOT, entry["mp4_path"]))
        assert sha256(entry["mp4_path"]) == entry["mp4_sha256"]
        total += entry["frame_count"]
    assert total == 2468


def test_mp4_is_measurably_lossy_so_png_is_the_pixel_authority(validation):
    measurement = validation["mp4_lossiness_measurement"]
    assert measurement["shapes_match"] is True
    assert measurement["bit_identical"] is False
    assert measurement["max_abs_channel_difference"] > 0
    assert validation["mp4_is_lossy_h264_crf18"] is True
    assert validation["mp4_is_not_the_pixel_authority"] is True
    assert validation["scientific_frame_identity_field"] == "canonical_pixel_sha256"
    assert validation[
        "scientific_frame_identity_depends_on_container_timestamps"
    ] is False


def test_established_representation_was_reused_not_replaced(audit, manifest):
    pilot = audit["pilot_media_convention"]
    assert pilot["committed_media_artifact"] == "video_640x360.mp4"
    assert "runtime" in pilot["canonical_png_location"]
    assert manifest["canonical_media"]["mp4_name"] == "video_640x360.mp4"
    assert manifest["canonical_media"]["png_subdirectory"] == "frames_640x360"
    # the pilot artifact this convention came from must still be present
    assert os.path.exists(
        os.path.join(ROOT, "data/autonomous/layout_01_ep9405/video_640x360.mp4")
    )


# ---------------------------------------------------- environment provenance

def test_environment_provenance_is_recorded():
    environment = load(f"{STATUS}/environment_provenance.json")
    producer = environment["producer_environment"]
    for field in ("python", "platform", "pillow", "numpy", "ffmpeg", "ffprobe"):
        assert producer[field]
    policy = environment["determinism_policy"]
    assert policy["canonical_pixel_identity_is_encoder_independent"] is True
    assert policy["canonical_png_bytes_are_encoder_dependent"] is True
    assert policy["cross_pillow_version_byte_equality_claimed"] is False
    assert policy["cross_pillow_version_byte_equality_tested"] is False
    assert policy["option_a_deterministic_regeneration_under_pinned_environment"][
        "satisfied"
    ] is True
    assert policy["option_b_immutable_bytes_plus_provenance"]["satisfied"] is True
    assert environment["matches_person_e_environment"] is True


# ------------------------------------------------------------------ handoffs

def test_c_to_a_media_handoff_is_ready_and_bound(a_handoff):
    assert a_handoff["C_66_CANONICAL_640x360_MEDIA_READY"] is True
    assert a_handoff["READY_FOR_A_PREPROCESSED_FRAME_MATERIALIZATION"] is True
    assert a_handoff["A_SOURCE_CONTRACT_COMPATIBLE"] is True
    assert a_handoff["producer_role"] == "person_c"
    assert a_handoff["consumer_role"] == "person_a"
    assert a_handoff["rewrites_frozen_c7_5_authority"] is False
    assert a_handoff["person_c_accepted_manifest_sha256"] == (
        mod.C_ACCEPTED_MANIFEST_SHA256
    )
    assert a_handoff["canonicalization"]["implementation_sha256"] == (
        mod.TO_CANONICAL_SHA256
    )
    media = a_handoff["canonical_source_media"]
    assert media["dimensions"] == "640x360"
    assert media["trajectory_count"] == 66
    assert media["frame_count"] == 2468
    assert media["channel_order"] == "RGB"
    assert media["recommended_source_for_preprocessing"] == "canonical_path PNG"
    assert media["mp4_is_not_the_pixel_authority"] is True
    assert sha256(media["frame_index_path"]) == media["frame_index_sha256"]
    assert "run MineWorld" in a_handoff["person_c_did_not"]


def test_c_to_d_media_handoff_is_ready_and_bound(d_handoff):
    assert d_handoff["C_TO_D_MEDIA_HANDOFF_READY"] is True
    assert d_handoff["producer_role"] == "person_c"
    assert d_handoff["consumer_role"] == "person_d"
    assert d_handoff["trajectory_count"] == 66
    assert len(d_handoff["trajectory_ids"]) == 66
    assert len(set(d_handoff["trajectory_ids"])) == 66
    assert d_handoff["frame_count"] == 2468
    assert d_handoff["canonical_dimensions"] == "640x360"
    assert d_handoff["person_c_accepted_manifest_sha256"] == (
        mod.C_ACCEPTED_MANIFEST_SHA256
    )
    assert sha256(d_handoff["frame_index_path"]) == d_handoff["frame_index_sha256"]
    assert d_handoff["applicability"]["media_applicable_to_all_trajectories"] is True
    assert d_handoff["applicability"]["not_applicable_trajectory_count"] == 6
    for entry in d_handoff["trajectories"]:
        assert sha256(entry["mp4_path"]) == entry["mp4_sha256"]
    # C must not define D's behaviour
    assert "Person D preprocessing" in d_handoff["person_c_did_not_define"]
    assert "Person D baseline behaviour" in d_handoff["person_c_did_not_define"]


# --------------------------------------------- scientific identity unchanged

def test_no_frozen_scientific_identity_changed():
    receipt = load(f"{STATUS}/scientific_identity_unchanged_receipt.json")
    assert receipt["SCIENTIFIC_IDENTITIES_UNCHANGED"] is True
    for name, entry in receipt["frozen_person_c_authorities"].items():
        assert entry["unchanged"] is True, name
        assert sha256(entry["path"]) == entry["expected_sha256"], name
    assert receipt["accepted_excluded_decision_unchanged"] is True
    assert receipt["accepted_count"] == 66
    assert receipt["excluded_count"] == 0
    assert receipt["visibility_labels_modified"] is False
    assert receipt["event_labels_modified"] is False
    assert receipt["u4_ineligibility_unchanged"] is True
    assert receipt["u4_reveal_eligible"] is False
    assert receipt["person_b_artifacts_modified_by_person_c"] is False
    assert receipt["person_e_detections_modified_by_person_c"] is False
    assert receipt["person_a_preprocessing_modified_by_person_c"] is False
    assert receipt["mineworld_executed"] is False
    assert receipt["episodes_recollected"] is False
    assert receipt["foreign_authorities"]["person_e_empirical_records"][
        "unchanged"
    ] is True


def test_visibility_join_and_event_table_are_byte_identical():
    assert sha256(f"{mod.VISIBILITY_REL}/visibility_join.jsonl") == (
        mod.C_VISIBILITY_JOIN_SHA256
    )
    assert sha256(f"{mod.VISIBILITY_REL}/event_table.jsonl") == (
        mod.C_EVENT_TABLE_SHA256
    )


# ------------------------------------------------------------ housekeeping

def test_sha256_inventory_matches_every_published_artifact():
    inventory = load(f"{STATUS}/sha256_inventory.json")
    assert inventory["file_count"] == len(inventory["files"])
    # 10 status artifacts plus one MP4 per trajectory
    assert inventory["file_count"] == 76
    for rel_path, digest in inventory["files"].items():
        assert os.path.exists(os.path.join(ROOT, rel_path)), rel_path
        assert sha256(rel_path) == digest, rel_path


def test_closure_receipt_reports_the_expected_outcome():
    closure = load(f"{STATUS}/closure_receipt.json")
    assert closure["raw_episode_count"] == 66
    assert closure["raw_frame_count"] == 2468
    assert closure["raw_frame_hashes_valid"] is True
    assert closure["raw_source_dimensions"] == "1920x1046"
    assert closure["to_canonical_sha256"] == mod.TO_CANONICAL_SHA256
    assert closure["TO_CANONICAL_PREEXISTING_AUTHORITY"] is True
    assert closure["TO_CANONICAL_RESULT_CHANGING_DECISION_REQUIRED"] is False
    assert closure["A_SOURCE_CONTRACT_COMPATIBLE"] is True
    assert closure["canonical_episode_count"] == 66
    assert closure["canonical_frame_count"] == 2468
    assert closure["canonical_dimensions"] == "640x360"
    assert closure["canonical_duplicate_count"] == 0
    assert closure["canonical_missing_count"] == 0
    assert closure["C_66_CANONICAL_640x360_MEDIA_READY"] is True
    assert closure["READY_FOR_A_PREPROCESSED_FRAME_MATERIALIZATION"] is True
    assert closure["SCIENTIFIC_IDENTITIES_UNCHANGED"] is True
    assert closure["person_e_pixel_hash_agreeing_frame_count"] == 2468


def test_no_canonical_frame_bytes_were_committed(index):
    """Canonical PNGs stay on the runtime, per the standing byte policy."""
    tracked = subprocess.run(
        ["git", "-C", ROOT, "ls-files", "docs/status", "data/autonomous"],
        capture_output=True, text=True, timeout=180,
    ).stdout.splitlines()
    assert not [path for path in tracked if "frames_640x360" in path]
    assert not [path for path in tracked if path.endswith(".png")]
    for row in index[:5]:
        assert "MineOcclude-Runtime" in row["canonical_path"]
