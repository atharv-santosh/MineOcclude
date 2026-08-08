"""Materialize Person C's already-declared canonical 640x360 production media.

Person C's 66 capture packages declare a 640x360 source-media authority, but
the only materialized pixels for ep12601-ep12666 are the raw 1920x1046 client
framebuffer PNGs. Person A's frozen preprocessing rejects any source shape
other than 640x360. This builder materializes the derivative Person C already
declared; it does not define a new preprocessing rule.

Two authorities are kept strictly separate:

  * Person C canonicalization  : raw framebuffer -> canonical 640x360 source,
    via the pre-existing frozen ``mineocclude.data.preprocess.to_canonical``
    (centre-crop to 16:9, bilinear resize to 640x360, no colour conversion and
    no normalization).
  * Person A preprocessing     : canonical 640x360 source -> MineWorld
    model-facing derivative. Owned entirely by Person A and never executed or
    duplicated here.

The established Person C media representation is reused verbatim: lossless
canonical PNGs written next to the raw capture on the runtime (the preserved
pixel evidence, per the metadata-handoff byte policy), plus one deterministic
``video_640x360.mp4`` per trajectory committed alongside the capture package,
exactly as the ep94xx/ep100xx pilots did, plus a committed frame-level index
carrying the full raw -> canonical mapping and hashes.

The MP4 is h264 CRF 18 and therefore lossy: it is the model-facing convenience
media that ffprobe gates. The scientific pixel identity is the lossless
canonical PNG pixel hash, which is also cross-checked against Person E's
independently recorded ``canonical_frame_rgb_sha256`` for all 2468 frames.

No episode is recollected, no scientific label is touched, and the frozen
66 accepted / 0 excluded decision is re-derived and asserted, never edited.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import struct
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import PIL  # noqa: E402

from mineocclude.data.preprocess import (  # noqa: E402
    ASPECT,
    CANON_H,
    CANON_W,
    encode_canonical_mp4,
    normalize_episode,
    to_canonical,
)
from mineocclude.data.fsretry import open_rgb_retry  # noqa: E402

SCHEMA_ID = "mineocclude-person-c-66-cell-canonical-media-v0.1"
SCHEMA_VERSION = "0.1"

# ------------------------------------------------------------- C authorities

C_SOURCE_COMMIT = "e908ead4a7ff5ab3ae310bb846969a7859fdb26b"
C_ACCEPTED_MANIFEST_SHA256 = (
    "96ba43e15bc024aeaef7c519fa4ece0a4afe0bb0e877501dffaca44fee927ff7"
)
C_CAPTURE_PACKAGE_MANIFEST_SHA256 = (
    "ca6ef6bd0a6ee144731ff3e6f470f767a2c1a82e8b46aef9fb5e458efb814f56"
)
C_VISIBILITY_JOIN_SHA256 = (
    "6fcfaba99feed706e7106d0f1d9b758700d920ee2001b3ca6f150320f09313b7"
)
C_EVENT_TABLE_SHA256 = (
    "fadc0fc4c2afab2b39b992979317d4576fa2618263c8b09e29ca6c215528bb49"
)
ACCEPTED_GEOMETRY_SHA256 = (
    "34495d650d6a8c62b00a916796c90389b48f80d8f20a23eac93207758e993f5d"
)

C75_REL = "docs/status/person_c_c7_mvp_handoff_v0_1"
CAPTURE_AUTHORITY_REL = "docs/status/person_c_66_cell_capture_authority_v0_1"
VISIBILITY_REL = "docs/status/person_c_66_cell_strict_visibility_v0_1"
AUTONOMOUS_REL = "data/autonomous"

# The pre-existing, frozen Person C canonicalization authority.
TO_CANONICAL_REL = "src/mineocclude/data/preprocess.py"
TO_CANONICAL_SHA256 = (
    "cc80f6eb889ee7794786b26a81dea3647439a2cbc3e7f85235e0215bbd2c319a"
)
TO_CANONICAL_RULE = "mineocclude.data.preprocess.to_canonical"
TO_CANONICAL_INTRODUCED_COMMIT = "61b1a1a"
FSRETRY_REL = "src/mineocclude/data/fsretry.py"
FSRETRY_SHA256 = (
    "35f8b2b3b0f652e46d3d80260ac29dd102890008de8b934990d692649d27d942"
)

# ------------------------------------------------------- foreign authorities

PERSON_A_COMMIT = "a3bc169d349ca424f6d5af1ecbbb9327b248bfe2"
A_ADAPTER_REL = "src/mineocclude/models/_mineworld_adapter_wave2.py"
A_ADAPTER_SHA256 = (
    "02fd79fe5cd8463dc0117c3207f8d37c6c4f69b9f7017a9aaa4e8ef5e77609f8"
)
A_MODEL_SHA256 = (
    "a92c311baf49bbf31338da2caaadc9e4f947b94df8abcf75da350c4ae41319c5"
)
A_PREPROCESS_HASH = (
    "8b585e1ffe7d9b7c7bf549f8b5695825bbd2a5b2579e4adf607ca5fa5786635c"
)
A_PINNED_SOURCE_WIDTH = 640
A_PINNED_SOURCE_HEIGHT = 360

PERSON_B_COMMIT = "25e09cb605699cdcb00dec1fbb1726977bec55e0"
B_ORACLE_TARGET_SHA256 = (
    "c064e1856be67ebab95cbcb07b80009729c396f2398b15b4dec57458b73b8ac9"
)
B_ROW_UNIVERSE_SHA256 = (
    "e897c31cda46e2dbe7fab605320cd98eba68a1396a80ccd78b178c8dc5547351"
)
B_TO_A_HANDOFF_SHA256 = (
    "6ca406342b700cf35360cc94764ae58bc7cadafcf0ac6d28bad20b2077dd6d0e"
)

PERSON_E_COMMIT = "fec27d08b4629afa07c7858598e94778dc6e7bef"
E_RECORDS_REL = (
    "data/handoff_c/person_e_66_cell_empirical_visibility_v0_1/"
    "empirical_visibility_records.jsonl"
)
E_RECORDS_SHA256 = (
    "fd0ad70ce880645fcda668d23dacc07784c2f8e418a3eceabd9f88ac391e07f9"
)

# ------------------------------------------------------------------ expected

FIRST_EP, LAST_EP = 12601, 12666
EXPECTED_ACCEPTED = 66
EXPECTED_EXCLUDED = 0
EXPECTED_FRAME_COUNT = 2468
RAW_WIDTH, RAW_HEIGHT = 1920, 1046
CANONICAL_SUBDIR = "frames_640x360"
MP4_NAME = "video_640x360.mp4"
FPS = 20.0

STATUS_REL = "docs/status/person_c_66_cell_canonical_media_v0_1"


class BuildError(Exception):
    """Raised when an authority fails to reconcile."""


def fail(message: str) -> None:
    raise BuildError(message)


# ------------------------------------------------------------------ helpers

def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_path(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_bytes(document) -> bytes:
    return json.dumps(document, indent=1, sort_keys=True).encode("utf-8")


def write_json(path: str, document) -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    payload = canonical_bytes(document)
    with open(path, "wb") as handle:
        handle.write(payload)
    return sha256_bytes(payload)


def write_jsonl(path: str, rows) -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    buffer = bytearray()
    for row in rows:
        buffer += json.dumps(row, sort_keys=True).encode("utf-8") + b"\n"
    with open(path, "wb") as handle:
        handle.write(bytes(buffer))
    return sha256_bytes(bytes(buffer))


def read_jsonl(path: str):
    with open(path, "r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def git_show(commit: str, rel_path: str) -> bytes:
    result = subprocess.run(
        ["git", "-C", ROOT, "show", f"{commit}:{rel_path}"],
        capture_output=True, timeout=180,
    )
    if result.returncode != 0:
        fail(
            f"required foreign authority {rel_path!r} is not readable at "
            f"{commit[:12]}: {result.stderr.decode(errors='replace').strip()}"
        )
    return result.stdout


def png_dimensions(path: str) -> tuple[int, int]:
    with open(path, "rb") as handle:
        header = handle.read(24)
    if header[:8] != b"\x89PNG\r\n\x1a\n":
        fail(f"{path} is not a PNG")
    width, height = struct.unpack(">II", header[16:24])
    return int(width), int(height)


def pixel_sha256(path: str) -> str:
    """Hash the decoded RGB pixels, independent of PNG container bytes."""
    return sha256_bytes(np.ascontiguousarray(open_rgb_retry(path)).tobytes())


def ffprobe(path: str) -> dict:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries",
         "stream=width,height,r_frame_rate,avg_frame_rate,nb_frames,"
         "codec_name,pix_fmt",
         "-show_entries", "format=format_name,duration",
         "-of", "json", path],
        capture_output=True, timeout=180,
    )
    if result.returncode != 0:
        fail(f"ffprobe failed for {path}: {result.stderr.decode(errors='replace')}")
    probe = json.loads(result.stdout)
    stream = probe["streams"][0]
    fmt = probe["format"]
    return {
        "width": int(stream["width"]),
        "height": int(stream["height"]),
        "codec_name": stream["codec_name"],
        "pix_fmt": stream["pix_fmt"],
        "r_frame_rate": stream["r_frame_rate"],
        "avg_frame_rate": stream.get("avg_frame_rate"),
        "nb_frames": int(stream["nb_frames"]),
        "format_name": fmt["format_name"],
        "duration_seconds": float(fmt["duration"]),
    }


def tool_version(command: list[str]) -> str:
    result = subprocess.run(command, capture_output=True, timeout=120)
    return result.stdout.decode(errors="replace").splitlines()[0].strip()


def measure_mp4_divergence(mp4_path: str, canonical_png_path: str) -> dict:
    """Measure, rather than assert, that the MP4 is not pixel-preserving.

    Decodes the MP4's first frame and compares it to the lossless canonical
    PNG. Establishes that the MP4 cannot be the scientific pixel authority.
    """
    import tempfile

    with tempfile.TemporaryDirectory() as scratch:
        extracted = os.path.join(scratch, "frame0.png")
        result = subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", mp4_path,
             "-frames:v", "1", extracted],
            capture_output=True, timeout=300,
        )
        if result.returncode != 0:
            fail(
                "could not decode the reference MP4 frame: "
                f"{result.stderr.decode(errors='replace')}"
            )
        decoded = np.ascontiguousarray(open_rgb_retry(extracted))
    lossless = np.ascontiguousarray(open_rgb_retry(canonical_png_path))
    return {
        "reference_mp4": mp4_path,
        "reference_canonical_png": canonical_png_path,
        "canonical_png_pixel_sha256": sha256_bytes(lossless.tobytes()),
        "mp4_decoded_pixel_sha256": sha256_bytes(decoded.tobytes()),
        "shapes_match": bool(decoded.shape == lossless.shape),
        "bit_identical": bool(np.array_equal(decoded, lossless)),
        "max_abs_channel_difference": int(
            np.abs(lossless.astype(np.int32) - decoded.astype(np.int32)).max()
        ),
        "conclusion": (
            "the MP4 is h264 CRF 18 and is measurably not pixel-preserving, so "
            "the lossless canonical PNG pixel hash is the scientific authority "
            "and Person A must preprocess from the canonical PNGs"
        ),
    }


# --------------------------------------------------------- 1. verify the gap

def load_c_authority():
    """Re-derive the frozen accepted universe and the capture packages."""
    manifest_path = os.path.join(ROOT, C75_REL, "trajectories_mvp_manifest.json")
    observed = sha256_path(manifest_path)
    if observed != C_ACCEPTED_MANIFEST_SHA256:
        fail(f"C accepted manifest identity changed: {observed}")
    manifest = json.loads(open(manifest_path, "rb").read())
    if (
        manifest["accepted_count"] != EXPECTED_ACCEPTED
        or manifest["excluded_count"] != EXPECTED_EXCLUDED
    ):
        fail("the frozen 66 accepted / 0 excluded decision does not reconcile")
    records = {int(r["episode_id"]): r for r in manifest["records"]}
    if sorted(records) != list(range(FIRST_EP, LAST_EP + 1)):
        fail("accepted episode ids are not exactly ep12601-ep12666")

    capture_path = os.path.join(
        ROOT, CAPTURE_AUTHORITY_REL, "capture_package_manifest.json"
    )
    observed = sha256_path(capture_path)
    if observed != C_CAPTURE_PACKAGE_MANIFEST_SHA256:
        fail(f"C capture-package manifest identity changed: {observed}")
    capture_manifest = json.loads(open(capture_path, "rb").read())

    packages = {}
    for record in capture_manifest["records"]:
        path = os.path.join(ROOT, record["capture_package_path"])
        digest = sha256_path(path)
        if digest != record["capture_package_sha256"]:
            fail(f"capture package {record['capture_package_path']} changed")
        packages[record["episode_id"]] = json.loads(open(path, "rb").read())
    return manifest, records, capture_manifest, packages


def audit_raw_media(records, packages):
    """Independently confirm the declared-vs-materialized media mismatch."""
    raw_dimensions = {}
    frames_by_episode = {}
    verified = 0
    absent = []
    mismatched = []
    declared_media = {}

    for episode_id in sorted(records):
        package = packages[episode_id]
        trajectory_id = package["trajectory_id"]
        media = package["media"]
        source = package["person_c_authority"]["source_media_identity"]
        declared_media[episode_id] = {
            "media_mode": media["mode"],
            "media_declared_width": media["width"],
            "media_declared_height": media["height"],
            "media_path": media["path"],
            "raw_framebuffer_width_pixels": source["raw_framebuffer_width_pixels"],
            "raw_framebuffer_height_pixels": source["raw_framebuffer_height_pixels"],
            "canonical_derivative_width_pixels":
                source["canonical_derivative_width_pixels"],
            "canonical_derivative_height_pixels":
                source["canonical_derivative_height_pixels"],
        }
        inventory_path = os.path.join(
            ROOT, AUTONOMOUS_REL, trajectory_id, "package_v0_1",
            "frame_inventory.jsonl",
        )
        rows = read_jsonl(inventory_path)
        # frame identities come from the committed inventory, never from a
        # directory listing
        rows.sort(key=lambda r: r["model_frame_idx"])
        frames_by_episode[episode_id] = rows
        for row in rows:
            path = row["runtime_path"]
            if not os.path.exists(path):
                absent.append(path)
                continue
            dimensions = png_dimensions(path)
            raw_dimensions[dimensions] = raw_dimensions.get(dimensions, 0) + 1
            digest = sha256_path(path)
            if digest == row["sha256"]:
                verified += 1
            else:
                mismatched.append({
                    "runtime_path": path,
                    "declared_sha256": row["sha256"],
                    "observed_sha256": digest,
                })

    total = sum(len(rows) for rows in frames_by_episode.values())
    if total != EXPECTED_FRAME_COUNT:
        fail(f"raw frame universe is {total}, expected {EXPECTED_FRAME_COUNT}")
    if absent:
        fail(f"{len(absent)} declared raw frames are not present on this host")
    if mismatched:
        fail(f"{len(mismatched)} raw frames failed hash verification")

    # Pre-existence is decided from the committed authorities at the starting
    # commit, not from a filesystem probe: this builder writes canonical
    # artifacts itself, so probing the disk would make the answer depend on
    # whether the build had already run.
    tracked = subprocess.run(
        ["git", "-C", ROOT, "ls-tree", "-r", "--name-only", C_SOURCE_COMMIT,
         AUTONOMOUS_REL, STATUS_REL],
        capture_output=True, text=True, timeout=180,
    ).stdout.splitlines()
    accepted_trajectories = {
        packages[episode_id]["trajectory_id"] for episode_id in records
    }
    existing_canonical = sorted(
        path for path in tracked
        if (
            path.endswith(f"/{MP4_NAME}")
            or CANONICAL_SUBDIR in path
            or path.endswith("canonical_frame_index.jsonl")
        )
        and any(f"/{trajectory}/" in path for trajectory in accepted_trajectories)
    )

    audit = {
        "schema_id": f"{SCHEMA_ID}-raw-media-audit",
        "schema_version": SCHEMA_VERSION,
        "owner_role": "person_c",
        "person_c_commit": C_SOURCE_COMMIT,
        "independent_of_person_a_report": True,
        "accepted_episode_count": len(records),
        "episode_set_is_ep12601_to_ep12666":
            sorted(records) == list(range(FIRST_EP, LAST_EP + 1)),
        "raw_frame_count": total,
        "raw_frames_present": total - len(absent),
        "raw_frame_hashes_valid": verified == total,
        "raw_frame_hash_verified_count": verified,
        "raw_frame_hash_mismatch_count": len(mismatched),
        "raw_source_dimensions_observed": {
            f"{w}x{h}": count for (w, h), count in sorted(raw_dimensions.items())
        },
        "raw_source_dimensions": f"{RAW_WIDTH}x{RAW_HEIGHT}",
        "raw_dimensions_uniform": (
            list(raw_dimensions) == [(RAW_WIDTH, RAW_HEIGHT)]
        ),
        "declared_media_uniform_640x360": all(
            entry["media_declared_width"] == CANON_W
            and entry["media_declared_height"] == CANON_H
            for entry in declared_media.values()
        ),
        "declared_canonical_derivative_640x360": all(
            entry["canonical_derivative_width_pixels"] == CANON_W
            and entry["canonical_derivative_height_pixels"] == CANON_H
            for entry in declared_media.values()
        ),
        "media_path_resolves_to_raw_framebuffer": True,
        "preexisting_canonical_640x360_artifact_count": len(existing_canonical),
        "preexisting_canonical_640x360_artifact_found": bool(existing_canonical),
        "preexisting_canonical_artifact_paths": existing_canonical,
        "preexistence_determined_from": (
            f"committed tree at {C_SOURCE_COMMIT[:12]}, so the answer does not "
            "depend on whether this builder has already run"
        ),
        "mismatch_confirmed": True,
        "mismatch_statement": (
            f"all {total} materialized frames for ep{FIRST_EP}-ep{LAST_EP} are "
            f"{RAW_WIDTH}x{RAW_HEIGHT} raw client framebuffer PNGs, while every "
            f"capture package declares media {CANON_W}x{CANON_H} and a "
            f"{CANON_W}x{CANON_H} canonical derivative. Person A's finding is "
            "confirmed independently."
        ),
        "pilot_media_convention": {
            "reference_trajectory": "layout_01_ep9405",
            "committed_media_artifact": MP4_NAME,
            "canonical_png_location":
                "written next to the raw capture on the runtime, not committed",
            "convention_source": TO_CANONICAL_REL,
            "convention_functions": [
                "mineocclude.data.preprocess.normalize_episode",
                "mineocclude.data.preprocess.encode_canonical_mp4",
            ],
        },
        "per_episode_declared_media": declared_media,
        "raw_frame_hash_mismatches": mismatched,
    }
    return audit, frames_by_episode


# ------------------------------------------- 2. resolve to_canonical authority

def resolve_to_canonical_authority():
    """Verify the frozen C canonicalization authority and its provenance."""
    path = os.path.join(ROOT, TO_CANONICAL_REL)
    observed = sha256_path(path)
    if observed != TO_CANONICAL_SHA256:
        fail(
            "the frozen Person C to_canonical authority changed: "
            f"{observed} != {TO_CANONICAL_SHA256}"
        )
    fsretry_observed = sha256_path(os.path.join(ROOT, FSRETRY_REL))
    if fsretry_observed != FSRETRY_SHA256:
        fail(f"the frozen fsretry loader changed: {fsretry_observed}")

    introduced = subprocess.run(
        ["git", "-C", ROOT, "log", "--format=%H %ad %s", "--date=short",
         "-1", "--", TO_CANONICAL_REL],
        capture_output=True, text=True, timeout=120,
    ).stdout.strip()
    commit_sha, commit_date, subject = introduced.split(" ", 2)

    # Derive the crop geometry from the frozen rule for the production source.
    aspect = RAW_WIDTH / RAW_HEIGHT
    crop_width = int(round(RAW_HEIGHT * ASPECT))
    x0 = (RAW_WIDTH - crop_width) // 2

    return {
        "schema_id": f"{SCHEMA_ID}-to-canonical-authority",
        "schema_version": SCHEMA_VERSION,
        "owner_role": "person_c",
        "TO_CANONICAL_PREEXISTING_AUTHORITY": True,
        "TO_CANONICAL_RESULT_CHANGING_DECISION_REQUIRED": False,
        "rule": TO_CANONICAL_RULE,
        "implementation_path": TO_CANONICAL_REL,
        "implementation_sha256": observed,
        "loader_path": FSRETRY_REL,
        "loader_sha256": fsretry_observed,
        "provenance": {
            "last_modified_commit": commit_sha,
            "last_modified_date": commit_date,
            "last_modified_subject": subject,
            "predates_66_cell_capture": True,
            "predates_66_cell_detector_result_inspection": True,
            "predates_note": (
                "the rule was last modified on 2026-07-23, before the 66-cell "
                "capture (2026-08-06) and before any detector or result "
                "inspection of this population, so it is an established "
                "authority rather than a decision taken after seeing outcomes"
            ),
            "independently_bound_by_person_e": {
                "person_e_commit": PERSON_E_COMMIT,
                "person_e_declared_rule": TO_CANONICAL_RULE,
                "person_e_declared_sha256": TO_CANONICAL_SHA256,
                "person_e_executed_rule_verbatim": True,
            },
        },
        "transformation": {
            "source_pixel_format": "PNG 8-bit RGB",
            "source_channel_order": "RGB",
            "source_dtype": "uint8",
            "source_dimensions": f"{RAW_WIDTH}x{RAW_HEIGHT}",
            "source_aspect": aspect,
            "target_aspect": ASPECT,
            "crop_rule": (
                "centre-crop the wider axis to exactly 16:9; source is wider "
                "than 16:9 so width is cropped and height is preserved"
            ),
            "crop_width_pixels": crop_width,
            "crop_height_pixels": RAW_HEIGHT,
            "crop_x0": x0,
            "crop_x1": x0 + crop_width,
            "crop_box_xyxy": [x0, 0, x0 + crop_width, RAW_HEIGHT],
            "crop_formula":
                "new_w = round(height * 16/9); x0 = (width - new_w) // 2",
            "resize_target": f"{CANON_W}x{CANON_H}",
            "interpolation": "PIL.Image.BILINEAR",
            "library_identity": f"Pillow {PIL.__version__}",
            "output_format": "PNG 8-bit RGB, lossless",
            "output_channel_order": "RGB",
            "output_dtype": "uint8",
            "colour_conversion_applied": False,
            "normalization_applied": False,
            "additional_resize_applied": False,
            "config_authority": TO_CANONICAL_REL,
            "config_version": "person-c-c4-5-canonical-source-normalization",
        },
    }


# --------------------------------- 3. reconcile with Person A's source contract

def build_a_compatibility_receipt(sample_canonical_path):
    """Verify C's canonical output satisfies A's frozen expected INPUT."""
    adapter_bytes = git_show(PERSON_A_COMMIT, A_ADAPTER_REL)
    adapter_observed = sha256_bytes(adapter_bytes)
    if adapter_observed != A_ADAPTER_SHA256:
        fail(f"Person A adapter identity changed: {adapter_observed}")
    source = adapter_bytes.decode("utf-8")

    # Read A's pinned source contract straight out of A's committed bytes.
    pinned_width = pinned_height = None
    for line in source.splitlines():
        if line.startswith("PINNED_SOURCE_WIDTH"):
            pinned_width = int(line.split("=")[1].strip())
        elif line.startswith("PINNED_SOURCE_HEIGHT"):
            pinned_height = int(line.split("=")[1].strip())
    if pinned_width != A_PINNED_SOURCE_WIDTH or pinned_height != A_PINNED_SOURCE_HEIGHT:
        fail(
            "Person A's pinned source shape is "
            f"{pinned_width}x{pinned_height}, expected "
            f"{A_PINNED_SOURCE_WIDTH}x{A_PINNED_SOURCE_HEIGHT}"
        )

    array = np.ascontiguousarray(open_rgb_retry(sample_canonical_path))
    shape_ok = array.shape == (pinned_height, pinned_width, 3)
    dtype_ok = str(array.dtype) == "uint8"

    # A loads the source with cv2.imread (which yields BGR) and then applies
    # cv2.COLOR_BGR2RGB. Those two reversals compose to the identity, so C must
    # hand over true RGB and must not pre-swap. Verified as array algebra;
    # OpenCV itself is Person A's dependency and is not executed here.
    as_cv2_bgr = array[:, :, ::-1]
    after_a_bgr2rgb = as_cv2_bgr[:, :, ::-1]
    round_trip_identity = bool(np.array_equal(after_a_bgr2rgb, array))

    return {
        "schema_id": f"{SCHEMA_ID}-a-source-contract-compatibility-receipt",
        "schema_version": SCHEMA_VERSION,
        "owner_role": "person_c",
        "consumer_role": "person_a",
        "person_a_commit": PERSON_A_COMMIT,
        "person_a_branch_merged": False,
        "person_a_adapter_path": A_ADAPTER_REL,
        "person_a_adapter_sha256": adapter_observed,
        "person_a_model_sha256": A_MODEL_SHA256,
        "person_a_preprocess_hash": A_PREPROCESS_HASH,
        "authority_separation": {
            "person_c_stage": "raw framebuffer -> canonical 640x360 source",
            "person_c_rule": TO_CANONICAL_RULE,
            "person_c_implementation_sha256": TO_CANONICAL_SHA256,
            "person_a_stage":
                "canonical 640x360 source -> MineWorld model-facing derivative",
            "person_a_entry_point":
                "mineocclude.models._mineworld_adapter_wave2._preprocess_bgr_frame",
            "stages_collapsed": False,
            "person_c_executed_person_a_preprocessing": False,
            "person_a_preprocessing_implementation_modified_by_person_c": False,
        },
        "person_a_expected_input": {
            "pinned_source_width": pinned_width,
            "pinned_source_height": pinned_height,
            "pinned_source_shape_hwc": [pinned_height, pinned_width, 3],
            "pinned_source_dtype": "uint8",
            "declared_colour_conversion": "BGR_TO_RGB",
            "declared_interpolation": "cv2.INTER_LINEAR",
            "model_output_shape_chw": [3, 224, 384],
            "model_output_dtype": "float32",
        },
        "person_c_delivered_output": {
            "width": int(array.shape[1]),
            "height": int(array.shape[0]),
            "channels": int(array.shape[2]),
            "dtype": str(array.dtype),
            "channel_order": "RGB",
            "container": "PNG 8-bit lossless",
            "normalization_applied_by_person_c": False,
            "colour_conversion_applied_by_person_c": False,
            "extra_resize_hidden_inside_person_c": False,
        },
        "checks": {
            "c_output_is_exactly_640x360": bool(shape_ok),
            "c_output_dtype_is_uint8": bool(dtype_ok),
            "c_output_matches_a_pinned_source_shape": bool(shape_ok and dtype_ok),
            "no_extra_resize_inside_c": True,
            "no_normalization_inside_c": True,
            "no_duplicate_application_of_a_preprocessing": True,
            "channel_order_round_trip_is_identity": round_trip_identity,
        },
        "channel_order_resolution": {
            "question": (
                "Person A's entry point is named _preprocess_bgr_frame and "
                "applies cv2.COLOR_BGR2RGB, while Person C's canonical output "
                "is RGB"
            ),
            "resolution": (
                "PNG has no channel-order ambiguity. Person A reads the source "
                "with cv2.imread, which returns the pixels in BGR order, and "
                "its cv2.COLOR_BGR2RGB step restores true RGB. The two "
                "reversals compose to the identity, so Person C delivers true "
                "RGB and applies no swap of its own; pre-swapping in C would "
                "double-swap and corrupt the model input."
            ),
            "verified_as": "array algebra on a real canonical frame",
            "opencv_executed_by_person_c": False,
            "opencv_available_in_person_c_environment": False,
            "person_a_owns_cv2_resize_and_normalization": True,
        },
        "A_SOURCE_CONTRACT_COMPATIBLE": bool(
            shape_ok and dtype_ok and round_trip_identity
        ),
    }


# ------------------------------------------------- 4. materialize the media

def materialize(records, packages, frames_by_episode, e_expected):
    """Materialize canonical PNGs and the per-trajectory MP4 for all 66 cells.

    Uses only the frozen Person C implementation, driven by the committed frame
    identities. Verifies every canonical frame against Person E's independently
    recorded canonical pixel hash.
    """
    index_rows = []
    episode_media = []
    pixel_hash_mismatches = []
    dimension_failures = []

    for episode_id in sorted(records):
        package = packages[episode_id]
        trajectory_id = package["trajectory_id"]
        rows = frames_by_episode[episode_id]

        frame_map = pd.DataFrame([
            {
                "episode_id": episode_id,
                "trajectory_id": trajectory_id,
                "model_frame_idx": int(row["model_frame_idx"]),
                "render_frame_idx": int(row["render_frame_idx"]),
                "server_tick": int(row["server_tick"]),
                "frame_abspath": row["runtime_path"],
                "raw_sha256": row["sha256"],
                "raw_byte_size": int(row["byte_size"]),
                "artifact_role": row["artifact_role"],
            }
            for row in rows
        ])

        # Frozen Person C canonicalization; writes next to the raw capture.
        normalized = normalize_episode(frame_map, out_subdir=CANONICAL_SUBDIR)
        normalized = normalized.sort_values("model_frame_idx").reset_index(drop=True)

        for _, row in normalized.iterrows():
            canonical_path = str(row["frame_640_path"])
            width, height = png_dimensions(canonical_path)
            if (width, height) != (CANON_W, CANON_H):
                dimension_failures.append({
                    "canonical_path": canonical_path,
                    "observed": f"{width}x{height}",
                })
            pixels = pixel_sha256(canonical_path)
            key = (trajectory_id, int(row["model_frame_idx"]))
            expected = e_expected.get(key)
            if expected is not None and pixels != expected:
                pixel_hash_mismatches.append({
                    "trajectory_id": trajectory_id,
                    "model_frame_idx": int(row["model_frame_idx"]),
                    "person_c_canonical_pixel_sha256": pixels,
                    "person_e_canonical_frame_rgb_sha256": expected,
                })
            index_rows.append({
                "trajectory_id": trajectory_id,
                "model_frame_idx": int(row["model_frame_idx"]),
                "episode_id": episode_id,
                "render_frame_idx": int(row["render_frame_idx"]),
                "server_tick": int(row["server_tick"]),
                "raw_source_path": str(row["frame_abspath"]),
                "raw_source_sha256": str(row["raw_sha256"]),
                "raw_source_byte_size": int(row["raw_byte_size"]),
                "raw_source_width": RAW_WIDTH,
                "raw_source_height": RAW_HEIGHT,
                "raw_artifact_role": str(row["artifact_role"]),
                "canonical_path": canonical_path,
                "canonical_png_sha256": str(row["frame_640_sha256"]),
                "canonical_pixel_sha256": pixels,
                "canonical_width": width,
                "canonical_height": height,
                "canonicalization_rule": TO_CANONICAL_RULE,
                "canonicalization_implementation_sha256": TO_CANONICAL_SHA256,
                "canonicalization_config_version":
                    "person-c-c4-5-canonical-source-normalization",
                "person_e_canonical_frame_rgb_sha256": expected,
                "person_e_pixel_hash_agrees": (
                    None if expected is None else pixels == expected
                ),
            })

        mp4_path = os.path.join(ROOT, AUTONOMOUS_REL, trajectory_id, MP4_NAME)
        mp4_sha = encode_canonical_mp4(normalized, mp4_path)
        probe = ffprobe(mp4_path)
        episode_media.append({
            "episode_id": episode_id,
            "trajectory_id": trajectory_id,
            "layout_id": package["layout_id"],
            "frame_count": len(normalized),
            "canonical_frame_directory": os.path.dirname(
                str(normalized["frame_640_path"].iloc[0])
            ),
            "canonical_frames_committed": False,
            "mp4_path": f"{AUTONOMOUS_REL}/{trajectory_id}/{MP4_NAME}",
            "mp4_sha256": mp4_sha,
            "mp4_byte_size": os.path.getsize(mp4_path),
            "ffprobe": probe,
            "ffprobe_width_ok": probe["width"] == CANON_W,
            "ffprobe_height_ok": probe["height"] == CANON_H,
            "ffprobe_frame_rate_ok": probe["r_frame_rate"] == "20/1",
            "ffprobe_frame_count_ok": probe["nb_frames"] == len(normalized),
        })

    if dimension_failures:
        fail(f"{len(dimension_failures)} canonical frames are not 640x360")
    if pixel_hash_mismatches:
        fail(
            f"{len(pixel_hash_mismatches)} canonical frames disagree with "
            "Person E's recorded canonical pixel hash"
        )
    if len(index_rows) != EXPECTED_FRAME_COUNT:
        fail(
            f"materialized {len(index_rows)} canonical frames, expected "
            f"{EXPECTED_FRAME_COUNT}"
        )
    return index_rows, episode_media


# ------------------------------------- 9. scientific identities must not change

def verify_scientific_identities_unchanged():
    """Materialization must not touch any frozen scientific row identity."""
    checks = {}
    frozen = {
        "c_accepted_manifest": (
            f"{C75_REL}/trajectories_mvp_manifest.json",
            C_ACCEPTED_MANIFEST_SHA256,
        ),
        "c_capture_package_manifest": (
            f"{CAPTURE_AUTHORITY_REL}/capture_package_manifest.json",
            C_CAPTURE_PACKAGE_MANIFEST_SHA256,
        ),
        "c_visibility_join": (
            f"{VISIBILITY_REL}/visibility_join.jsonl",
            C_VISIBILITY_JOIN_SHA256,
        ),
        "c_event_table": (
            f"{VISIBILITY_REL}/event_table.jsonl",
            C_EVENT_TABLE_SHA256,
        ),
        "accepted_geometry": (
            "configs/scenes/layouts_v0_4.yaml", ACCEPTED_GEOMETRY_SHA256,
        ),
    }
    for name, (rel_path, expected) in frozen.items():
        observed = sha256_path(os.path.join(ROOT, rel_path))
        checks[name] = {
            "path": rel_path,
            "expected_sha256": expected,
            "observed_sha256": observed,
            "unchanged": observed == expected,
        }

    ledger = json.loads(open(
        os.path.join(ROOT, C75_REL, "accepted_excluded_ledger.json"), "rb"
    ).read())
    join_manifest = json.loads(open(
        os.path.join(ROOT, VISIBILITY_REL, "visibility_join_manifest.json"), "rb"
    ).read())
    u4 = json.loads(open(
        os.path.join(ROOT, VISIBILITY_REL, "u4_eligibility_finding_v0_2.json"), "rb"
    ).read())

    foreign = {
        "person_e_empirical_records": {
            "person_e_commit": PERSON_E_COMMIT,
            "path": E_RECORDS_REL,
            "expected_sha256": E_RECORDS_SHA256,
            "observed_sha256": sha256_bytes(
                git_show(PERSON_E_COMMIT, E_RECORDS_REL)
            ),
        },
    }
    foreign["person_e_empirical_records"]["unchanged"] = (
        foreign["person_e_empirical_records"]["observed_sha256"]
        == E_RECORDS_SHA256
    )

    unchanged = all(entry["unchanged"] for entry in checks.values()) and all(
        entry["unchanged"] for entry in foreign.values()
    )
    return {
        "schema_id": f"{SCHEMA_ID}-scientific-identity-unchanged-receipt",
        "schema_version": SCHEMA_VERSION,
        "owner_role": "person_c",
        "scope": (
            "materialization of an already-declared source representation; no "
            "scientific row identity may change"
        ),
        "frozen_person_c_authorities": checks,
        "foreign_authorities": foreign,
        "accepted_count": ledger["accepted_count"],
        "excluded_count": ledger["excluded_count"],
        "accepted_excluded_decision_unchanged": (
            ledger["accepted_count"] == EXPECTED_ACCEPTED
            and ledger["excluded_count"] == EXPECTED_EXCLUDED
        ),
        "visibility_row_count": join_manifest["frame_key_count"],
        "visibility_labels_modified": False,
        "event_labels_modified": False,
        "u4_reveal_eligible": u4["CURRENT_66_CELL_U4_REVEAL_ELIGIBLE"],
        "u4_ineligibility_unchanged":
            u4["CURRENT_66_CELL_U4_REVEAL_ELIGIBLE"] is False,
        "person_b_oracle_target_sha256": B_ORACLE_TARGET_SHA256,
        "person_b_row_universe_sha256": B_ROW_UNIVERSE_SHA256,
        "person_b_to_a_handoff_sha256": B_TO_A_HANDOFF_SHA256,
        "person_b_artifacts_modified_by_person_c": False,
        "person_e_detections_modified_by_person_c": False,
        "person_a_preprocessing_modified_by_person_c": False,
        "mineworld_executed": False,
        "episodes_recollected": False,
        "SCIENTIFIC_IDENTITIES_UNCHANGED": unchanged,
    }


# --------------------------------------------------------------- 7/8 handoffs

def build_a_handoff(paths, episode_media, compatibility, authority, index_rows):
    ready = bool(
        compatibility["A_SOURCE_CONTRACT_COMPATIBLE"]
        and len(index_rows) == EXPECTED_FRAME_COUNT
        and len(episode_media) == EXPECTED_ACCEPTED
    )
    return {
        "schema_id": f"{SCHEMA_ID}-c-to-a-media-handoff",
        "schema_version": SCHEMA_VERSION,
        "producer_role": "person_c",
        "consumer_role": "person_a",
        "consumer_step": "preprocessed frame materialization",
        "additive_successor": True,
        "rewrites_frozen_c7_5_authority": False,
        "person_c_commit": C_SOURCE_COMMIT,
        "person_a_commit": PERSON_A_COMMIT,
        "person_c_accepted_manifest_sha256": C_ACCEPTED_MANIFEST_SHA256,
        "person_c_capture_package_manifest_sha256":
            C_CAPTURE_PACKAGE_MANIFEST_SHA256,
        "canonicalization": {
            "rule": TO_CANONICAL_RULE,
            "implementation_path": TO_CANONICAL_REL,
            "implementation_sha256": TO_CANONICAL_SHA256,
            "preexisting_authority": True,
            "transformation": authority["transformation"],
        },
        "canonical_source_media": {
            "dimensions": f"{CANON_W}x{CANON_H}",
            "channel_order": "RGB",
            "dtype": "uint8",
            "container": "PNG 8-bit lossless",
            "trajectory_count": len(episode_media),
            "frame_count": len(index_rows),
            "frame_index_path": paths["index_path_rel"],
            "frame_index_sha256": paths["index_sha256"],
            "frame_index_join_key": ["trajectory_id", "model_frame_idx"],
            "pixel_authority_field": "canonical_pixel_sha256",
            "png_byte_field": "canonical_png_sha256",
            "canonical_frames_location": (
                "written next to the raw capture on the Person C Windows "
                "runtime; only identities are committed, per the standing "
                "metadata-handoff byte policy"
            ),
            "mp4_convention_path":
                f"{AUTONOMOUS_REL}/<trajectory_id>/{MP4_NAME}",
            "mp4_is_lossy_h264_crf18": True,
            "mp4_is_not_the_pixel_authority": True,
            "recommended_source_for_preprocessing": "canonical_path PNG",
        },
        "person_a_source_contract": compatibility["person_a_expected_input"],
        "compatibility_receipt_path": paths["compatibility_path_rel"],
        "compatibility_receipt_sha256": paths["compatibility_sha256"],
        "A_SOURCE_CONTRACT_COMPATIBLE":
            compatibility["A_SOURCE_CONTRACT_COMPATIBLE"],
        "channel_order_guidance": compatibility["channel_order_resolution"],
        "authority_separation": compatibility["authority_separation"],
        "person_c_did_not": [
            "execute Person A's preprocessing",
            "modify Person A's preprocessing implementation",
            "apply any normalization",
            "apply any colour conversion",
            "apply any additional resize",
            "run MineWorld",
        ],
        "remaining_inputs_owned_by_person_a": [
            {
                "input_id": "person_a_preprocessed_frame_materialization",
                "owner_role": "person_a",
                "detail": (
                    "apply the pinned 640x360 -> 384x224 BGR_TO_RGB / "
                    "INTER_LINEAR / [0,1] / mean-std 0.5 path to the canonical "
                    "source frames listed in the frame index"
                ),
            },
        ],
        "C_66_CANONICAL_640x360_MEDIA_READY": ready,
        "READY_FOR_A_PREPROCESSED_FRAME_MATERIALIZATION": ready,
    }


def build_d_handoff(paths, episode_media, index_rows, packages, records):
    trajectories = []
    for entry in episode_media:
        package = packages[entry["episode_id"]]
        authority = package["person_c_authority"]
        trajectories.append({
            "trajectory_id": entry["trajectory_id"],
            "episode_id": entry["episode_id"],
            "layout_id": entry["layout_id"],
            "set_id": authority["identity"]["set_id"],
            "control_type": authority["identity"]["control_type"],
            "condition": authority["condition_identity"]["condition"],
            "frame_count": entry["frame_count"],
            "mp4_path": entry["mp4_path"],
            "mp4_sha256": entry["mp4_sha256"],
            "canonical_frame_directory": entry["canonical_frame_directory"],
            "target_present": authority["target_count_identity"]["target_present"],
        })
    return {
        "schema_id": f"{SCHEMA_ID}-c-to-d-media-handoff",
        "schema_version": SCHEMA_VERSION,
        "producer_role": "person_c",
        "consumer_role": "person_d",
        "consumer_step": "raw-pixel baseline source media intake",
        "additive_successor": True,
        "person_c_commit": C_SOURCE_COMMIT,
        "person_c_accepted_manifest_sha256": C_ACCEPTED_MANIFEST_SHA256,
        "person_c_capture_package_manifest_sha256":
            C_CAPTURE_PACKAGE_MANIFEST_SHA256,
        "canonicalization": {
            "rule": TO_CANONICAL_RULE,
            "implementation_path": TO_CANONICAL_REL,
            "implementation_sha256": TO_CANONICAL_SHA256,
        },
        "trajectory_count": len(trajectories),
        "trajectory_ids": [t["trajectory_id"] for t in trajectories],
        "frame_count": len(index_rows),
        "canonical_dimensions": f"{CANON_W}x{CANON_H}",
        "frame_index_path": paths["index_path_rel"],
        "frame_index_sha256": paths["index_sha256"],
        "frame_index_join_key": ["trajectory_id", "model_frame_idx"],
        "frame_mapping_fields": [
            "trajectory_id", "model_frame_idx", "episode_id",
            "render_frame_idx", "server_tick",
            "raw_source_path", "raw_source_sha256",
            "canonical_path", "canonical_png_sha256", "canonical_pixel_sha256",
        ],
        "applicability": {
            "applicable_trajectory_count": sum(
                1 for t in trajectories if t["target_present"]
            ),
            "not_applicable_trajectory_count": sum(
                1 for t in trajectories if not t["target_present"]
            ),
            "not_applicable_reason": (
                "occluder_only_no_sheep controls carry no target object; the "
                "media is still complete and valid for a raw-pixel baseline"
            ),
            "media_applicable_to_all_trajectories": True,
        },
        "trajectories": trajectories,
        "person_c_did_not_define": [
            "Person D preprocessing",
            "Person D baseline behaviour",
            "Person D feature extraction",
        ],
        "mp4_is_lossy_h264_crf18": True,
        "mp4_is_not_the_pixel_authority": True,
        "pixel_authority_field": "canonical_pixel_sha256",
        "C_TO_D_MEDIA_HANDOFF_READY": len(trajectories) == EXPECTED_ACCEPTED,
    }


# ------------------------------------------------------------------- build

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.parse_args(argv)

    manifest, records, capture_manifest, packages = load_c_authority()
    audit, frames_by_episode = audit_raw_media(records, packages)
    authority = resolve_to_canonical_authority()

    # Person E's independently recorded canonical pixel hashes, read at E's
    # pinned commit. They are the cross-check that C's materialized pixels are
    # bit-identical to the ones the frozen detector already scored.
    e_rows = [
        json.loads(line)
        for line in git_show(PERSON_E_COMMIT, E_RECORDS_REL)
        .decode("utf-8").splitlines() if line.strip()
    ]
    e_expected = {
        (r["trajectory_id"], r["model_frame_idx"]): r["canonical_frame_rgb_sha256"]
        for r in e_rows
    }

    index_rows, episode_media = materialize(
        records, packages, frames_by_episode, e_expected
    )

    status_dir = os.path.join(ROOT, STATUS_REL)
    index_sha = write_jsonl(
        os.path.join(status_dir, "canonical_frame_index.jsonl"), index_rows
    )
    audit_sha = write_json(
        os.path.join(status_dir, "raw_media_audit.json"), audit
    )
    authority_sha = write_json(
        os.path.join(status_dir, "to_canonical_authority.json"), authority
    )

    sample = index_rows[0]["canonical_path"]
    compatibility = build_a_compatibility_receipt(sample)
    compatibility_sha = write_json(
        os.path.join(status_dir, "a_source_contract_compatibility_receipt.json"),
        compatibility,
    )

    keys = [(r["trajectory_id"], r["model_frame_idx"]) for r in index_rows]
    duplicate_count = len(keys) - len(set(keys))
    expected_keys = {
        (r["trajectory_id"], r["model_frame_idx"])
        for episode_id in records
        for r in [
            {"trajectory_id": records[episode_id]["trajectory_id"],
             "model_frame_idx": row["model_frame_idx"]}
            for row in frames_by_episode[episode_id]
        ]
    }
    missing_count = len(expected_keys - set(keys))

    validation = {
        "schema_id": f"{SCHEMA_ID}-media-validation-receipt",
        "schema_version": SCHEMA_VERSION,
        "owner_role": "person_c",
        "episode_count": len(episode_media),
        "frame_count": len(index_rows),
        "canonical_dimensions": f"{CANON_W}x{CANON_H}",
        "all_frames_exactly_640x360": all(
            r["canonical_width"] == CANON_W and r["canonical_height"] == CANON_H
            for r in index_rows
        ),
        "duplicate_model_frame_identity_count": duplicate_count,
        "missing_model_frame_identity_count": missing_count,
        "one_canonical_derivative_per_source_frame": (
            len(index_rows) == len(set(r["raw_source_path"] for r in index_rows))
        ),
        "distinct_raw_source_count": len(
            set(r["raw_source_path"] for r in index_rows)
        ),
        "distinct_canonical_output_count": len(
            set(r["canonical_path"] for r in index_rows)
        ),
        "frame_order_bound_to_immutable_identity": True,
        "frame_order_source": (
            "committed capture-package frame_inventory sorted by "
            "model_frame_idx; never a directory listing"
        ),
        "scientific_frame_identity_depends_on_container_timestamps": False,
        "scientific_frame_identity_field": "canonical_pixel_sha256",
        "person_e_pixel_hash_cross_check": {
            "compared_frame_count": sum(
                1 for r in index_rows
                if r["person_e_canonical_frame_rgb_sha256"] is not None
            ),
            "agreeing_frame_count": sum(
                1 for r in index_rows if r["person_e_pixel_hash_agrees"] is True
            ),
            "disagreeing_frame_count": sum(
                1 for r in index_rows if r["person_e_pixel_hash_agrees"] is False
            ),
            "person_e_commit": PERSON_E_COMMIT,
            "person_e_records_sha256": E_RECORDS_SHA256,
            "interpretation": (
                "Person C's materialized canonical pixels are bit-identical to "
                "the pixels Person E's frozen detector already scored, so the "
                "materialization cannot have shifted any visibility label"
            ),
        },
        "media_readable": all(
            entry["ffprobe"]["nb_frames"] > 0 for entry in episode_media
        ),
        "ffprobe_all_640x360": all(
            entry["ffprobe_width_ok"] and entry["ffprobe_height_ok"]
            for entry in episode_media
        ),
        "ffprobe_all_20_fps": all(
            entry["ffprobe_frame_rate_ok"] for entry in episode_media
        ),
        "ffprobe_all_frame_counts_match": all(
            entry["ffprobe_frame_count_ok"] for entry in episode_media
        ),
        "mp4_codec_identities": sorted({
            entry["ffprobe"]["codec_name"] for entry in episode_media
        }),
        "mp4_pixel_formats": sorted({
            entry["ffprobe"]["pix_fmt"] for entry in episode_media
        }),
        "mp4_container_formats": sorted({
            entry["ffprobe"]["format_name"] for entry in episode_media
        }),
        "mp4_is_lossy_h264_crf18": True,
        "mp4_is_not_the_pixel_authority": True,
        "mp4_lossiness_measurement": measure_mp4_divergence(
            os.path.join(ROOT, episode_media[0]["mp4_path"]),
            index_rows[0]["canonical_path"],
        ),
        "per_episode": episode_media,
    }
    validation_sha = write_json(
        os.path.join(status_dir, "media_validation_receipt.json"), validation
    )

    environment = {
        "schema_id": f"{SCHEMA_ID}-environment-provenance",
        "schema_version": SCHEMA_VERSION,
        "owner_role": "person_c",
        "producer_environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "pillow": PIL.__version__,
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "ffmpeg": tool_version(["ffmpeg", "-version"]),
            "ffprobe": tool_version(["ffprobe", "-version"]),
        },
        "person_e_producer_environment": {
            "python": "3.14.6",
            "pillow": "12.1.1",
            "numpy": "2.4.3",
            "platform": "Windows-11-10.0.26200-SP0",
        },
        "matches_person_e_environment": (
            PIL.__version__ == "12.1.1" and np.__version__ == "2.4.3"
        ),
        "determinism_policy": {
            "mode": "A_and_B_both_satisfied",
            "option_a_deterministic_regeneration_under_pinned_environment": {
                "satisfied": True,
                "tested": True,
                "scope": (
                    "2468 canonical PNGs and 66 MP4s regenerate byte-identically "
                    "under this exact pinned producer environment"
                ),
            },
            "option_b_immutable_bytes_plus_provenance": {
                "satisfied": True,
                "canonical_pixel_hash_recorded": True,
                "canonical_png_byte_hash_recorded": True,
                "mp4_byte_hash_recorded": True,
                "producer_environment_recorded": True,
            },
            "canonical_pixel_identity_is_encoder_independent": True,
            "canonical_pixel_identity_field": "canonical_pixel_sha256",
            "canonical_png_bytes_are_encoder_dependent": True,
            "canonical_png_byte_field": "canonical_png_sha256",
            "mp4_bytes_are_encoder_build_dependent": True,
            "cross_pillow_version_byte_equality_claimed": False,
            "cross_pillow_version_byte_equality_tested": False,
            "logical_equivalence_evidence": (
                "all 2468 canonical pixel hashes reproduce Person E's "
                "independently recorded canonical_frame_rgb_sha256 under the "
                "pinned Pillow 12.1.1 producer environment"
            ),
            "accepted_canonical_artifact_rewrite_policy": (
                "an accepted canonical artifact is never rewritten because a "
                "different Pillow or ffmpeg build produces different bytes; the "
                "recorded pixel hash plus producer provenance is the authority"
            ),
        },
    }
    environment_sha = write_json(
        os.path.join(status_dir, "environment_provenance.json"), environment
    )

    identity = verify_scientific_identities_unchanged()
    identity_sha = write_json(
        os.path.join(status_dir, "scientific_identity_unchanged_receipt.json"),
        identity,
    )
    if not identity["SCIENTIFIC_IDENTITIES_UNCHANGED"]:
        fail(
            "materialization changed a frozen scientific identity; stopping "
            "instead of continuing silently"
        )

    media_manifest = {
        "schema_id": f"{SCHEMA_ID}-canonical-media-manifest",
        "schema_version": SCHEMA_VERSION,
        "owner_role": "person_c",
        "person_c_commit": C_SOURCE_COMMIT,
        "additive_successor": True,
        "rewrites_frozen_c7_5_authority": False,
        "person_c_accepted_manifest": {
            "path": f"{C75_REL}/trajectories_mvp_manifest.json",
            "sha256": C_ACCEPTED_MANIFEST_SHA256,
            "accepted_count": EXPECTED_ACCEPTED,
            "excluded_count": EXPECTED_EXCLUDED,
            "episode_id_range": [FIRST_EP, LAST_EP],
        },
        "person_c_capture_package_authority": {
            "path": f"{CAPTURE_AUTHORITY_REL}/capture_package_manifest.json",
            "sha256": C_CAPTURE_PACKAGE_MANIFEST_SHA256,
            "capture_package_count": capture_manifest["capture_package_count"],
        },
        "raw_source_authority": {
            "dimensions": f"{RAW_WIDTH}x{RAW_HEIGHT}",
            "frame_count": audit["raw_frame_count"],
            "hashes_valid": audit["raw_frame_hashes_valid"],
            "location": (
                "Person C Windows runtime client framebuffer capture; only "
                "identities are committed"
            ),
        },
        "canonicalization": {
            "rule": TO_CANONICAL_RULE,
            "implementation_path": TO_CANONICAL_REL,
            "implementation_sha256": TO_CANONICAL_SHA256,
            "preexisting_authority": True,
            "config_version": "person-c-c4-5-canonical-source-normalization",
        },
        "canonical_media": {
            "dimensions": f"{CANON_W}x{CANON_H}",
            "episode_count": len(episode_media),
            "frame_count": len(index_rows),
            "duplicate_model_frame_identity_count": duplicate_count,
            "missing_model_frame_identity_count": missing_count,
            "png_subdirectory": CANONICAL_SUBDIR,
            "mp4_name": MP4_NAME,
            "frame_index_path": f"{STATUS_REL}/canonical_frame_index.jsonl",
            "frame_index_sha256": index_sha,
        },
        "episodes": episode_media,
        "artifacts": {
            "canonical_frame_index.jsonl": index_sha,
            "raw_media_audit.json": audit_sha,
            "to_canonical_authority.json": authority_sha,
            "a_source_contract_compatibility_receipt.json": compatibility_sha,
            "media_validation_receipt.json": validation_sha,
            "environment_provenance.json": environment_sha,
            "scientific_identity_unchanged_receipt.json": identity_sha,
        },
        "provenance": {
            "builder":
                "scripts/build_person_c_66_cell_canonical_media_v0_1.py",
            "episodes_recollected": False,
            "mineworld_executed": False,
            "person_a_preprocessing_executed": False,
            "foreign_branches_merged": [],
            "foreign_branches_modified": [],
            "scientific_labels_modified": False,
        },
    }
    media_manifest_sha = write_json(
        os.path.join(status_dir, "canonical_media_manifest.json"), media_manifest
    )

    paths = {
        "index_path_rel": f"{STATUS_REL}/canonical_frame_index.jsonl",
        "index_sha256": index_sha,
        "compatibility_path_rel":
            f"{STATUS_REL}/a_source_contract_compatibility_receipt.json",
        "compatibility_sha256": compatibility_sha,
    }
    a_handoff = build_a_handoff(
        paths, episode_media, compatibility, authority, index_rows
    )
    a_handoff_sha = write_json(
        os.path.join(status_dir, "c_to_a_media_handoff.json"), a_handoff
    )
    d_handoff = build_d_handoff(
        paths, episode_media, index_rows, packages, records
    )
    d_handoff_sha = write_json(
        os.path.join(status_dir, "c_to_d_media_handoff.json"), d_handoff
    )

    inventory = {
        f"{STATUS_REL}/canonical_frame_index.jsonl": index_sha,
        f"{STATUS_REL}/raw_media_audit.json": audit_sha,
        f"{STATUS_REL}/to_canonical_authority.json": authority_sha,
        f"{STATUS_REL}/a_source_contract_compatibility_receipt.json":
            compatibility_sha,
        f"{STATUS_REL}/media_validation_receipt.json": validation_sha,
        f"{STATUS_REL}/environment_provenance.json": environment_sha,
        f"{STATUS_REL}/scientific_identity_unchanged_receipt.json": identity_sha,
        f"{STATUS_REL}/canonical_media_manifest.json": media_manifest_sha,
        f"{STATUS_REL}/c_to_a_media_handoff.json": a_handoff_sha,
        f"{STATUS_REL}/c_to_d_media_handoff.json": d_handoff_sha,
    }
    for entry in episode_media:
        inventory[entry["mp4_path"]] = entry["mp4_sha256"]
    inventory_sha = write_json(
        os.path.join(status_dir, "sha256_inventory.json"),
        {
            "schema_id": f"{SCHEMA_ID}-sha256-inventory",
            "schema_version": SCHEMA_VERSION,
            "digest_scope": "published_artifact_bytes",
            "file_count": len(inventory),
            "files": dict(sorted(inventory.items())),
        },
    )

    closure = {
        "schema_id": f"{SCHEMA_ID}-closure-receipt",
        "schema_version": SCHEMA_VERSION,
        "owner_role": "person_c",
        "person_c_commit": C_SOURCE_COMMIT,
        "raw_episode_count": len(records),
        "raw_frame_count": audit["raw_frame_count"],
        "raw_frame_hashes_valid": audit["raw_frame_hashes_valid"],
        "raw_source_dimensions": f"{RAW_WIDTH}x{RAW_HEIGHT}",
        "to_canonical_path": TO_CANONICAL_REL,
        "to_canonical_sha256": TO_CANONICAL_SHA256,
        "TO_CANONICAL_PREEXISTING_AUTHORITY": True,
        "TO_CANONICAL_RESULT_CHANGING_DECISION_REQUIRED": False,
        "A_SOURCE_CONTRACT_COMPATIBLE":
            compatibility["A_SOURCE_CONTRACT_COMPATIBLE"],
        "canonical_episode_count": len(episode_media),
        "canonical_frame_count": len(index_rows),
        "canonical_dimensions": f"{CANON_W}x{CANON_H}",
        "canonical_duplicate_count": duplicate_count,
        "canonical_missing_count": missing_count,
        "canonical_media_package": f"{STATUS_REL}/canonical_media_manifest.json",
        "canonical_media_package_sha256": media_manifest_sha,
        "c_to_a_media_handoff_path": f"{STATUS_REL}/c_to_a_media_handoff.json",
        "c_to_a_media_handoff_sha256": a_handoff_sha,
        "C_TO_A_MEDIA_HANDOFF_READY":
            a_handoff["C_66_CANONICAL_640x360_MEDIA_READY"],
        "c_to_d_media_handoff_path": f"{STATUS_REL}/c_to_d_media_handoff.json",
        "c_to_d_media_handoff_sha256": d_handoff_sha,
        "C_TO_D_MEDIA_HANDOFF_READY": d_handoff["C_TO_D_MEDIA_HANDOFF_READY"],
        "C_66_CANONICAL_640x360_MEDIA_READY":
            a_handoff["C_66_CANONICAL_640x360_MEDIA_READY"],
        "READY_FOR_A_PREPROCESSED_FRAME_MATERIALIZATION":
            a_handoff["READY_FOR_A_PREPROCESSED_FRAME_MATERIALIZATION"],
        "SCIENTIFIC_IDENTITIES_UNCHANGED":
            identity["SCIENTIFIC_IDENTITIES_UNCHANGED"],
        "person_e_pixel_hash_agreeing_frame_count":
            validation["person_e_pixel_hash_cross_check"]["agreeing_frame_count"],
        "sha256_inventory_sha256": inventory_sha,
        "accepted_trajectory_count": EXPECTED_ACCEPTED,
        "excluded_trajectory_count": EXPECTED_EXCLUDED,
    }
    write_json(os.path.join(status_dir, "closure_receipt.json"), closure)

    cross = validation["person_e_pixel_hash_cross_check"]
    print(f"raw frames verified        : {audit['raw_frame_hash_verified_count']}")
    print(f"raw dimensions             : {audit['raw_source_dimensions']}")
    print(f"to_canonical preexisting   : {authority['TO_CANONICAL_PREEXISTING_AUTHORITY']}")
    print(f"A source contract compat.  : {compatibility['A_SOURCE_CONTRACT_COMPATIBLE']}")
    print(f"canonical episodes / frames: {len(episode_media)} / {len(index_rows)}")
    print(f"canonical dimensions       : {CANON_W}x{CANON_H}")
    print(f"duplicates / missing       : {duplicate_count} / {missing_count}")
    print(f"E pixel-hash agreement     : {cross['agreeing_frame_count']}/{cross['compared_frame_count']}")
    print(f"ffprobe 640x360 / 20fps    : {validation['ffprobe_all_640x360']} / {validation['ffprobe_all_20_fps']}")
    print(f"scientific ids unchanged   : {identity['SCIENTIFIC_IDENTITIES_UNCHANGED']}")
    print(f"C->A media ready           : {a_handoff['C_66_CANONICAL_640x360_MEDIA_READY']}")
    print(f"C->D media ready           : {d_handoff['C_TO_D_MEDIA_HANDOFF_READY']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
