"""Person E intake and measurement authority for Person C's 66-cell request.

This module owns three things and nothing else:

1. **Foreign-authority intake.** Person C's capture authority and C-to-E
   empirical-visibility request, and Person B's coordinate-frame co-sign, are
   read at their exact pinned commits through ``git cat-file`` and verified
   byte-for-byte against their pinned SHA-256 digests. No foreign branch is
   merged and no foreign artifact is rewritten.
2. **The frozen Person E detector.** The frozen candidate config/version
   documents are re-verified against their pinned hashes and the detector is
   imported unchanged from :mod:`mineocclude.vision.magenta`. No threshold,
   morphology rule or area bound is read from, derived from, or adjusted by
   the 66-cell population.
3. **Canonical frame derivation.** The raw 1920x1046 capture framebuffer is
   reduced to the contract's 640x360 canonical source frame using Person C's
   own frozen ``to_canonical`` rule, loaded from Person C's commit and pinned
   by SHA-256. Person E does not invent a resampling rule, and the frozen
   detector is never run outside its declared 640x360 applicability.

Geometric visibility and the final ``visible_flag`` are Person C's to compute
after this handoff; neither is produced here.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import types
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

SCHEMA_ID = "person-e-66-cell-empirical-visibility-v0-1"
SCHEMA_VERSION = "1.0"

PERSON_E_BRANCH = "role/person-e-operations"

# ---------------------------------------------------------------------------
# Pinned foreign authorities (read-only, never merged)
# ---------------------------------------------------------------------------

PERSON_C_COMMIT = "aceb319c47af6d494d6e5314049b12ab1a0a002f"
PERSON_B_COMMIT = "a8648514033f8d58887c3b919f02985704aaa310"

C_REQUEST_ROOT = (
    "data/handoff_e/person_c_to_person_e_66_cell_empirical_visibility_request_v0_1"
)
C_REQUEST_MANIFEST_PATH = f"{C_REQUEST_ROOT}/request_manifest.json"
C_REQUEST_MANIFEST_SHA256 = (
    "6934317b6b2723d4dddb5507ba58ef32e6ce39729bd4065751aa76e8ae1fc0ea"
)
C_FRAME_UNIVERSE_PATH = f"{C_REQUEST_ROOT}/frame_universe.jsonl"
C_FRAME_UNIVERSE_SHA256 = (
    "f95d705df50f444bc21541f485b91471ff52c0c0ca8dccf2779c9c4adf1edcfe"
)
C_EXPECTED_RESPONSE_SCHEMA_PATH = f"{C_REQUEST_ROOT}/expected_response_schema.json"
C_EXPECTED_RESPONSE_SCHEMA_SHA256 = (
    "135f6f742d9fc4c71a6e1aa0636b12faa8306d82f037da5b3e564e553935c579"
)

C_AUTHORITY_ROOT = "docs/status/person_c_66_cell_capture_authority_v0_1"
C_CAPTURE_PACKAGE_MANIFEST_PATH = f"{C_AUTHORITY_ROOT}/capture_package_manifest.json"
C_CAPTURE_PACKAGE_MANIFEST_SHA256 = (
    "ca6ef6bd0a6ee144731ff3e6f470f767a2c1a82e8b46aef9fb5e458efb814f56"
)
C_COORDINATE_FRAME_AUTHORITY_PATH = f"{C_AUTHORITY_ROOT}/coordinate_frame_authority.json"
C_COORDINATE_FRAME_AUTHORITY_SHA256 = (
    "1aed95e444f82ab4caf9935c039e87df3aafbf38830bf763a646aba3d62b509b"
)

C_ACCEPTED_MANIFEST_PATH = (
    "docs/status/person_c_c7_mvp_handoff_v0_1/trajectories_mvp_manifest.json"
)
C_ACCEPTED_MANIFEST_SHA256 = (
    "96ba43e15bc024aeaef7c519fa4ece0a4afe0bb0e877501dffaca44fee927ff7"
)

ACCEPTED_GEOMETRY_PATH = "configs/scenes/layouts_v0_4.yaml"
ACCEPTED_GEOMETRY_SHA256 = (
    "34495d650d6a8c62b00a916796c90389b48f80d8f20a23eac93207758e993f5d"
)
ACCEPTED_GEOMETRY_VERSION = "person-c-layout-config-v0.4"

B_COSIGN_PATH = (
    "docs/status/person_b_66_cell_coordinate_frame_cosign_v0_1/coordinate_frame_cosign.json"
)
B_COSIGN_SHA256 = (
    "b40d8ba1103e1638af386cc365ec727ab576d842516accc41d675d4fdb3d6b7d"
)

EXPECTED_TRAJECTORY_COUNT = 66
EXPECTED_FRAME_IDENTITY_COUNT = 2468
EXPECTED_APPLICABLE_COUNT = 2108
EXPECTED_NOT_APPLICABLE_COUNT = 360
LAYOUT_IDS = tuple(f"layout_{index:02d}" for index in range(1, 7))
CANONICAL_CAMERA_POSE_IDS = {
    layout_id: f"{layout_id}_canonical_pose_v1" for layout_id in LAYOUT_IDS
}

# ---------------------------------------------------------------------------
# Frozen Person E detector authority (predates this execution)
# ---------------------------------------------------------------------------

DETECTOR_FREEZE_COMMIT = "3930669eddc026ecb081e947f71f1855a7415904"
DETECTOR_ALGORITHM = "hsv-largest-valid-blob-v1.0-candidate"
DETECTOR_IDENTITY_SHA256 = (
    "0cadf618fca1578196bde4982021c38627ccb9c39e46353812e7da3fce6aa125"
)
DETECTOR_VERSION = f"{DETECTOR_ALGORITHM}:sha256:{DETECTOR_IDENTITY_SHA256}"
DETECTOR_CONFIG_SHA256 = (
    "acfecd659958891eaee0d582c946abdfaaf47d1ab3307a24f7652e634c045bfa"
)
DETECTOR_SETTINGS_SHA256 = (
    "0dbb426adf99f53455eea04c4aaeb56f3cb22cbc351d87269bb605445eb8f2ea"
)
DETECTOR_IMPLEMENTATION_SHA256 = (
    "026f3b9f25c8aef7ac43fada5b8de92662b605af4868f930698651e59a228214"
)
DETECTOR_IMPLEMENTATION_PATH = "src/mineocclude/vision/magenta.py"
DETECTOR_CONFIG_PATH = (
    "docs/status/person_e_phase3_step3_1_candidate_freeze_v0_1/"
    "detector_candidate_config.json"
)
DETECTOR_VERSION_RECORD_PATH = (
    "docs/status/person_e_phase3_step3_1_candidate_freeze_v0_1/"
    "detector_candidate_version_record.json"
)

# ---------------------------------------------------------------------------
# Person C's frozen canonical-derivative rule (read at Person C's commit)
# ---------------------------------------------------------------------------

C_PREPROCESS_PATH = "src/mineocclude/data/preprocess.py"
C_PREPROCESS_SHA256 = (
    "cc80f6eb889ee7794786b26a81dea3647439a2cbc3e7f85235e0215bbd2c319a"
)
C_FSRETRY_PATH = "src/mineocclude/data/fsretry.py"
C_FSRETRY_SHA256 = (
    "35f8b2b3b0f652e46d3d80260ac29dd102890008de8b934990d692649d27d942"
)
CANONICAL_FRAME_WIDTH = 640
CANONICAL_FRAME_HEIGHT = 360
RAW_FRAMEBUFFER_WIDTH = 1920
RAW_FRAMEBUFFER_HEIGHT = 1046

DETECTOR_STATUS_NOT_APPLICABLE = "not_applicable_no_target_object"
DETECTOR_STATUS_UNREADABLE = "unreadable_source_frame"


class EmpiricalVisibilityError(RuntimeError):
    """Raised whenever an exact invariant cannot be proven; always fail closed."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise EmpiricalVisibilityError(message)


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def hash_json_value(value: Any) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    return sha256_bytes(payload)


def json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def jsonl_bytes(rows: Sequence[Mapping[str, Any]]) -> bytes:
    return b"".join(
        (
            json.dumps(
                dict(row), ensure_ascii=False, separators=(",", ":"), sort_keys=True
            )
            + "\n"
        ).encode("utf-8")
        for row in rows
    )


def repository_root() -> Path:
    return Path(__file__).resolve().parents[3]


def git_blob(repository: Path, revision: str, path: str) -> bytes:
    """Read one committed blob without checking out or merging its branch."""

    completed = subprocess.run(
        ["git", "-C", str(repository), "cat-file", "blob", f"{revision}:{path}"],
        check=False,
        capture_output=True,
    )
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise EmpiricalVisibilityError(f"Cannot read {revision}:{path}: {detail}")
    return completed.stdout


def git_text(repository: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repository), *arguments], check=False, capture_output=True
    )
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise EmpiricalVisibilityError(f"Git command failed: {detail}")
    return completed.stdout.decode("utf-8").strip()


def pinned_blob(repository: Path, revision: str, path: str, expected: str) -> bytes:
    payload = git_blob(repository, revision, path)
    observed = sha256_bytes(payload)
    require(
        observed == expected,
        f"{revision}:{path} SHA-256 is {observed}, expected {expected}.",
    )
    return payload


def pinned_json(repository: Path, revision: str, path: str, expected: str) -> Any:
    return json.loads(pinned_blob(repository, revision, path, expected).decode("utf-8"))


# ---------------------------------------------------------------------------
# Foreign-authority intake
# ---------------------------------------------------------------------------


def load_person_c_request(repository: Path) -> dict[str, Any]:
    """Verify and load Person C's C-to-E empirical-visibility request."""

    manifest = pinned_json(
        repository, PERSON_C_COMMIT, C_REQUEST_MANIFEST_PATH, C_REQUEST_MANIFEST_SHA256
    )
    require(
        manifest["accepted_geometry_sha256"] == ACCEPTED_GEOMETRY_SHA256
        and manifest["accepted_geometry_path"] == ACCEPTED_GEOMETRY_PATH
        and manifest["accepted_geometry_version"] == ACCEPTED_GEOMETRY_VERSION,
        "Person C request accepted-geometry binding changed.",
    )
    require(
        manifest["person_c_accepted_manifest_sha256"] == C_ACCEPTED_MANIFEST_SHA256
        and manifest["person_c_accepted_manifest_path"] == C_ACCEPTED_MANIFEST_PATH,
        "Person C accepted-manifest binding changed.",
    )
    require(
        manifest["frame_universe_sha256"] == C_FRAME_UNIVERSE_SHA256,
        "Person C frame-universe binding changed.",
    )
    require(
        manifest["expected_response_schema_sha256"]
        == C_EXPECTED_RESPONSE_SCHEMA_SHA256,
        "Person C expected-response-schema binding changed.",
    )
    require(
        manifest["frame_universe_join_key"] == ["trajectory_id", "model_frame_idx"]
        and manifest["expected_response_key"] == ["trajectory_id", "model_frame_idx"],
        "Person C join key changed.",
    )
    require(
        manifest["trajectory_count"] == EXPECTED_TRAJECTORY_COUNT
        and len(manifest["trajectory_ids"]) == EXPECTED_TRAJECTORY_COUNT
        and len(set(manifest["trajectory_ids"])) == EXPECTED_TRAJECTORY_COUNT,
        "Person C request does not carry exactly 66 unique trajectories.",
    )
    require(
        manifest["expected_model_frame_identity_count"]
        == manifest["model_frame_identity_count"]
        == EXPECTED_FRAME_IDENTITY_COUNT,
        "Person C request does not carry exactly 2468 model-frame identities.",
    )
    applicability = manifest["detector_applicability"]
    require(
        applicability["applicable_row_count"] == EXPECTED_APPLICABLE_COUNT
        and applicability["not_applicable_row_count"] == EXPECTED_NOT_APPLICABLE_COUNT,
        "Person C detector-applicability accounting changed.",
    )
    require(
        manifest["person_c_ran_detector"] is False
        and manifest["person_c_tuned_detector"] is False
        and manifest["person_c_supplied_detector_thresholds"] is False
        and manifest["person_c_supplied_detector_version"] is False
        and manifest["person_c_empirical_channel_supplied"] is False,
        "Person C must not supply or tune the detector.",
    )
    dimensions = manifest["frame_dimensions"]
    require(
        dimensions["canonical_derivative_width_pixels"] == CANONICAL_FRAME_WIDTH
        and dimensions["canonical_derivative_height_pixels"] == CANONICAL_FRAME_HEIGHT
        and dimensions["raw_framebuffer_width_pixels"] == RAW_FRAMEBUFFER_WIDTH
        and dimensions["raw_framebuffer_height_pixels"] == RAW_FRAMEBUFFER_HEIGHT,
        "Person C declared frame dimensions changed.",
    )
    return manifest


def load_frame_universe(repository: Path) -> list[dict[str, Any]]:
    """Verify and load the exact 2468-identity frame universe."""

    payload = pinned_blob(
        repository, PERSON_C_COMMIT, C_FRAME_UNIVERSE_PATH, C_FRAME_UNIVERSE_SHA256
    )
    require(payload.endswith(b"\n"), "Frame universe lacks a final newline.")
    rows = [json.loads(line) for line in payload.decode("utf-8").splitlines()]
    require(
        len(rows) == EXPECTED_FRAME_IDENTITY_COUNT,
        f"Frame universe holds {len(rows)} rows, expected "
        f"{EXPECTED_FRAME_IDENTITY_COUNT}.",
    )
    keys = [(row["trajectory_id"], row["model_frame_idx"]) for row in rows]
    require(
        len(set(keys)) == EXPECTED_FRAME_IDENTITY_COUNT,
        "Frame universe contains duplicate (trajectory_id, model_frame_idx) keys.",
    )
    require(
        len({row["trajectory_id"] for row in rows}) == EXPECTED_TRAJECTORY_COUNT,
        "Frame universe does not span exactly 66 trajectories.",
    )
    applicable = sum(1 for row in rows if row["detector_applicable"])
    require(
        applicable == EXPECTED_APPLICABLE_COUNT
        and len(rows) - applicable == EXPECTED_NOT_APPLICABLE_COUNT,
        "Frame-universe applicability accounting disagrees with the request.",
    )
    for row in rows:
        require(
            row["layout_id"] in CANONICAL_CAMERA_POSE_IDS,
            f"Unknown layout id {row['layout_id']!r} in the frame universe.",
        )
        require(
            row["raw_framebuffer_width_pixels"] == RAW_FRAMEBUFFER_WIDTH
            and row["raw_framebuffer_height_pixels"] == RAW_FRAMEBUFFER_HEIGHT
            and row["canonical_derivative_width_pixels"] == CANONICAL_FRAME_WIDTH
            and row["canonical_derivative_height_pixels"] == CANONICAL_FRAME_HEIGHT,
            "A frame-universe row declares non-contract frame dimensions.",
        )
        require(
            row["detector_applicable"] is bool(row["target_present"]),
            "Applicability and target presence disagree for a requested key.",
        )
        require(
            row["person_e_value_supplied"] is None,
            "Person C pre-supplied a Person E measurement.",
        )
    return rows


def load_person_b_cosign(repository: Path, coordinate_frames: Any) -> dict[str, Any]:
    """Verify Person B's co-sign against Person C's coordinate-frame authority."""

    cosign = pinned_json(repository, PERSON_B_COMMIT, B_COSIGN_PATH, B_COSIGN_SHA256)
    require(
        cosign["person_c_commit"] == PERSON_C_COMMIT,
        "Person B co-signed a different Person C commit.",
    )
    require(
        cosign["person_c_coordinate_frame_sha256"]
        == cosign["input_manifest_hash"]
        == C_COORDINATE_FRAME_AUTHORITY_SHA256,
        "Person B co-sign does not preserve Person C's coordinate-frame hash.",
    )
    require(
        cosign["person_c_coordinate_frame_path"] == C_COORDINATE_FRAME_AUTHORITY_PATH,
        "Person B co-sign points at a different coordinate-frame authority.",
    )
    require(
        cosign["person_c_capture_package_manifest_sha256"]
        == C_CAPTURE_PACKAGE_MANIFEST_SHA256,
        "Person B co-sign capture-package binding changed.",
    )
    require(
        cosign["accepted_geometry_sha256"] == ACCEPTED_GEOMETRY_SHA256,
        "Person B co-sign accepted-geometry binding changed.",
    )
    require(
        cosign["person_c_bytes_modified"] is False
        and cosign["person_c_branch_merged"] is False,
        "Person B co-sign reports modified or merged Person C bytes.",
    )
    result = cosign["compatibility_result"]
    require(
        result["coordinate_frame_compatible"] is True
        and result["all_layouts_compatible"] is True
        and result["projection_replay_pass"] is True
        and not result["failed_layout_ids"],
        "Person B did not report a compatible coordinate frame.",
    )
    require(
        cosign["oracle_target_manifest_built"] is False
        and cosign["activation_analysis_executed"] is False,
        "Person B co-sign exceeds its declared scope.",
    )
    c_by_layout = {frame["layout_id"]: frame for frame in coordinate_frames["frames"]}
    b_by_layout = {frame["layout_id"]: frame for frame in cosign["cosigned_frames"]}
    require(
        sorted(c_by_layout) == sorted(b_by_layout) == list(LAYOUT_IDS),
        "Person B and Person C do not co-sign the same six layouts.",
    )
    for layout_id in LAYOUT_IDS:
        require(
            b_by_layout[layout_id]["coordinate_frame_hash"]
            == c_by_layout[layout_id]["coordinate_frame_hash"],
            f"Person B altered the {layout_id} coordinate-frame hash.",
        )
        require(
            b_by_layout[layout_id]["coordinate_frame_hash_preserved"] is True,
            f"Person B did not preserve the {layout_id} coordinate frame.",
        )
        require(
            b_by_layout[layout_id]["person_c_source_file_sha256"]
            == c_by_layout[layout_id]["sha256"]
            and b_by_layout[layout_id]["path"] == c_by_layout[layout_id]["path"],
            f"Person B and Person C disagree on the {layout_id} frame source.",
        )
    return cosign


def load_coordinate_frame_authority(repository: Path) -> dict[str, Any]:
    authority = pinned_json(
        repository,
        PERSON_C_COMMIT,
        C_COORDINATE_FRAME_AUTHORITY_PATH,
        C_COORDINATE_FRAME_AUTHORITY_SHA256,
    )
    require(
        authority["accepted_geometry_sha256"] == ACCEPTED_GEOMETRY_SHA256,
        "Coordinate-frame authority accepted-geometry binding changed.",
    )
    require(
        len(authority["frames"]) == len(LAYOUT_IDS),
        "Coordinate-frame authority does not carry six frames.",
    )
    return authority


def load_accepted_geometry(repository: Path) -> dict[str, Any]:
    payload = pinned_blob(
        repository, PERSON_C_COMMIT, ACCEPTED_GEOMETRY_PATH, ACCEPTED_GEOMETRY_SHA256
    )
    geometry = json.loads(payload.decode("utf-8"))
    require(
        geometry["config_version"] == ACCEPTED_GEOMETRY_VERSION,
        "Accepted geometry config version changed.",
    )
    require(
        [layout["layout_id"] for layout in geometry["layouts"]] == list(LAYOUT_IDS),
        "Accepted geometry does not declare layout_01 through layout_06.",
    )
    return geometry


# ---------------------------------------------------------------------------
# Frozen detector authority
# ---------------------------------------------------------------------------


def verify_frozen_detector(repository: Path) -> dict[str, Any]:
    """Re-prove the frozen detector identity before any frame is measured."""

    config_path = repository / DETECTOR_CONFIG_PATH
    version_path = repository / DETECTOR_VERSION_RECORD_PATH
    implementation_path = repository / DETECTOR_IMPLEMENTATION_PATH
    config = json.loads(config_path.read_text(encoding="utf-8"))
    version = json.loads(version_path.read_text(encoding="utf-8"))
    configuration = config["configuration"]
    settings = configuration["detector_settings"]
    computed = {
        "config_sha256": hash_json_value(configuration),
        "identity_sha256": hash_json_value(version["identity"]),
        "implementation_sha256": sha256_file(implementation_path),
        "settings_sha256": hash_json_value(settings),
    }
    expected = {
        "config_sha256": DETECTOR_CONFIG_SHA256,
        "identity_sha256": DETECTOR_IDENTITY_SHA256,
        "implementation_sha256": DETECTOR_IMPLEMENTATION_SHA256,
        "settings_sha256": DETECTOR_SETTINGS_SHA256,
    }
    declared = {
        "config_sha256": version["detector_config_sha256"],
        "identity_sha256": version["detector_identity_sha256"],
        "implementation_sha256": version["detector_implementation_sha256"],
        "settings_sha256": version["detector_settings_sha256"],
    }
    require(
        computed == expected == declared,
        f"Frozen detector hashes changed: computed={computed}.",
    )
    require(
        version["detector_version"] == DETECTOR_VERSION
        and version["detector_algorithm_id"] == DETECTOR_ALGORITHM,
        "Frozen detector identity changed.",
    )
    applicability = configuration["applicability"]
    require(
        applicability["image_width_px"] == CANONICAL_FRAME_WIDTH
        and applicability["image_height_px"] == CANONICAL_FRAME_HEIGHT
        and applicability["pixel_format"] == "rgb8"
        and applicability["expected_channel_order"] == "RGB"
        and applicability["mismatched_input_behavior"] == "reject_fail_closed"
        and applicability["layout_ids"] == list(LAYOUT_IDS),
        "Frozen detector applicability changed.",
    )
    require(
        git_text(
            repository,
            "diff",
            "--name-only",
            DETECTOR_FREEZE_COMMIT,
            "HEAD",
            "--",
            DETECTOR_IMPLEMENTATION_PATH,
            DETECTOR_CONFIG_PATH,
            DETECTOR_VERSION_RECORD_PATH,
        )
        == "",
        "A frozen detector authority path changed after the freeze commit.",
    )
    return {
        "algorithm_id": DETECTOR_ALGORITHM,
        "applicability": applicability,
        "config_document_sha256": sha256_file(config_path),
        "config_path": DETECTOR_CONFIG_PATH,
        "config_sha256": DETECTOR_CONFIG_SHA256,
        "freeze_commit": DETECTOR_FREEZE_COMMIT,
        "identity_sha256": DETECTOR_IDENTITY_SHA256,
        "implementation_path": DETECTOR_IMPLEMENTATION_PATH,
        "implementation_sha256": DETECTOR_IMPLEMENTATION_SHA256,
        "settings": settings,
        "settings_sha256": DETECTOR_SETTINGS_SHA256,
        "version": DETECTOR_VERSION,
        "version_document_sha256": sha256_file(version_path),
        "version_record_path": DETECTOR_VERSION_RECORD_PATH,
    }


def detector_arguments(settings: Mapping[str, Any]) -> dict[str, Any]:
    from mineocclude.vision.magenta import HsvRange

    return {
        "close_iterations": settings["close_iterations"],
        "connectivity": settings["connectivity"],
        "hsv_ranges": tuple(HsvRange(*values) for values in settings["hsv_ranges"]),
        "max_area_pixels": settings["max_area_pixels"],
        "min_area_pixels": settings["min_area_pixels"],
        "morphology_radius_pixels": settings["morphology_radius_pixels"],
        "open_iterations": settings["open_iterations"],
    }


# ---------------------------------------------------------------------------
# Person C's frozen canonical-derivative rule
# ---------------------------------------------------------------------------


def load_canonical_rule(repository: Path) -> types.ModuleType:
    """Load Person C's frozen ``to_canonical`` rule at Person C's commit.

    The raw framebuffer is 1920x1046 while the frozen detector is only
    applicable to the contract's 640x360 canonical source frame. The reduction
    is Person C's own published rule; Person E executes it verbatim rather than
    inventing a resampling convention, and pins both source blobs by SHA-256.
    """

    fsretry_source = pinned_blob(
        repository, PERSON_C_COMMIT, C_FSRETRY_PATH, C_FSRETRY_SHA256
    ).decode("utf-8")
    preprocess_source = pinned_blob(
        repository, PERSON_C_COMMIT, C_PREPROCESS_PATH, C_PREPROCESS_SHA256
    ).decode("utf-8")
    # Both sources are committed Person C blobs whose bytes were just proven
    # against their pinned SHA-256 digests, so executing them is equivalent to
    # importing Person C's module without copying or paraphrasing its rule.
    fsretry = types.ModuleType("mineocclude.data.fsretry")
    exec(compile(fsretry_source, C_FSRETRY_PATH, "exec"), fsretry.__dict__)  # noqa: S102
    sys.modules.setdefault("mineocclude.data.fsretry", fsretry)
    preprocess = types.ModuleType("person_c_frozen_preprocess")
    exec(  # noqa: S102
        compile(preprocess_source, C_PREPROCESS_PATH, "exec"), preprocess.__dict__
    )
    require(
        preprocess.CANON_W == CANONICAL_FRAME_WIDTH
        and preprocess.CANON_H == CANONICAL_FRAME_HEIGHT,
        "Person C's canonical frame size changed.",
    )
    return preprocess


def canonical_frame_rgb(
    source_path: str, *, canonical_rule: types.ModuleType
) -> tuple[list[list[list[int]]], str]:
    """Return the canonical 640x360 RGB frame and its deterministic digest."""

    import numpy
    from PIL import Image

    raw = numpy.asarray(Image.open(source_path).convert("RGB"))
    require(
        raw.shape[:2] == (RAW_FRAMEBUFFER_HEIGHT, RAW_FRAMEBUFFER_WIDTH),
        f"{source_path} is {raw.shape[1]}x{raw.shape[0]}, not the declared "
        f"{RAW_FRAMEBUFFER_WIDTH}x{RAW_FRAMEBUFFER_HEIGHT} framebuffer.",
    )
    canonical = numpy.ascontiguousarray(
        canonical_rule.to_canonical(raw), dtype=numpy.uint8
    )
    require(
        canonical.shape == (CANONICAL_FRAME_HEIGHT, CANONICAL_FRAME_WIDTH, 3),
        "Canonical derivation did not produce a 640x360 RGB frame.",
    )
    return canonical.tolist(), sha256_bytes(canonical.tobytes())


# ---------------------------------------------------------------------------
# Record construction
# ---------------------------------------------------------------------------

# Sorted by construction: every schema, record and validation comparison below
# is against ``sorted(record)``, so a hand-written ordering slip must not be
# able to reject an otherwise valid measurement.
EMPIRICAL_RECORD_FIELDS = tuple(
    sorted((
    "bounding_box_x_max_exclusive_px",
    "bounding_box_x_min_px",
    "bounding_box_y_max_exclusive_px",
    "bounding_box_y_min_px",
    "c_accepted_manifest_sha256",
    "c_request_manifest_sha256",
    "canonical_camera_pose_id",
    "canonical_frame_height_px",
    "canonical_frame_rgb_sha256",
    "canonical_frame_width_px",
    "candidate_blob_count",
    "centroid_x_px",
    "centroid_y_px",
    "coordinate_convention",
    "detected_area_pixels",
    "detector_applicable",
    "detector_identity_sha256",
    "detector_status",
    "detector_status_reason",
    "detector_version",
    "empirical_magenta_visible",
    "episode_id",
    "layout_id",
    "marker_layout_authority_id",
    "marker_layout_authority_sha256",
    "model_frame_idx",
    "resolution",
    "selected_blob_fraction_of_threshold_matches",
    "source_frame_reference",
    "source_frame_sha256",
    "threshold_match_pixels",
    "trajectory_id",
    ))
)


def build_record(
    row: Mapping[str, Any],
    outcome: Mapping[str, Any],
    *,
    marker_authority_id: str,
    marker_authority_sha256: str,
) -> dict[str, Any]:
    """Build one explicit Person E record for one requested key."""

    box = outcome["bounding_box_xyxy"]
    centroid = outcome["centroid_xy"]
    record = {
        "bounding_box_x_max_exclusive_px": None if box is None else box[2],
        "bounding_box_x_min_px": None if box is None else box[0],
        "bounding_box_y_max_exclusive_px": None if box is None else box[3],
        "bounding_box_y_min_px": None if box is None else box[1],
        "c_accepted_manifest_sha256": C_ACCEPTED_MANIFEST_SHA256,
        "c_request_manifest_sha256": C_REQUEST_MANIFEST_SHA256,
        "canonical_camera_pose_id": CANONICAL_CAMERA_POSE_IDS[row["layout_id"]],
        "canonical_frame_height_px": CANONICAL_FRAME_HEIGHT,
        "canonical_frame_rgb_sha256": outcome["canonical_frame_rgb_sha256"],
        "canonical_frame_width_px": CANONICAL_FRAME_WIDTH,
        "candidate_blob_count": outcome["candidate_blob_count"],
        "centroid_x_px": None if centroid is None else centroid[0],
        "centroid_y_px": None if centroid is None else centroid[1],
        "coordinate_convention": "pixel_center_xy_zero_based",
        "detected_area_pixels": outcome["area_pixels"],
        "detector_applicable": bool(row["detector_applicable"]),
        "detector_identity_sha256": DETECTOR_IDENTITY_SHA256,
        "detector_status": outcome["detector_status"],
        "detector_status_reason": outcome["detector_status_reason"],
        "detector_version": DETECTOR_VERSION,
        "empirical_magenta_visible": outcome["empirical_magenta_visible"],
        "episode_id": row["episode_id"],
        "layout_id": row["layout_id"],
        "marker_layout_authority_id": marker_authority_id,
        "marker_layout_authority_sha256": marker_authority_sha256,
        "model_frame_idx": row["model_frame_idx"],
        "resolution": f"{CANONICAL_FRAME_WIDTH}x{CANONICAL_FRAME_HEIGHT}",
        "selected_blob_fraction_of_threshold_matches": outcome[
            "selected_blob_fraction_of_threshold_matches"
        ],
        "source_frame_reference": row["source_frame_runtime_path"],
        "source_frame_sha256": row["source_frame_sha256"],
        "threshold_match_pixels": outcome["threshold_match_pixels"],
        "trajectory_id": row["trajectory_id"],
    }
    require(
        tuple(sorted(record)) == EMPIRICAL_RECORD_FIELDS,
        "Empirical record fields changed.",
    )
    return record


def validate_record(record: Mapping[str, Any]) -> None:
    """Fail closed on any record that is not an explicit, coherent status."""

    require(
        tuple(sorted(record)) == EMPIRICAL_RECORD_FIELDS,
        "Empirical record fields changed.",
    )
    status = record["detector_status"]
    visible = record["empirical_magenta_visible"]
    geometry = (
        record["centroid_x_px"],
        record["centroid_y_px"],
        record["detected_area_pixels"],
        record["bounding_box_x_min_px"],
        record["bounding_box_y_min_px"],
        record["bounding_box_x_max_exclusive_px"],
        record["bounding_box_y_max_exclusive_px"],
    )
    if status == "detected":
        require(visible is True, "A detected record must be empirically visible.")
        require(
            all(value is not None for value in geometry),
            "A detected record must carry complete localization.",
        )
        x0, y0 = record["bounding_box_x_min_px"], record["bounding_box_y_min_px"]
        x1 = record["bounding_box_x_max_exclusive_px"]
        y1 = record["bounding_box_y_max_exclusive_px"]
        require(
            0 <= x0 < x1 <= CANONICAL_FRAME_WIDTH
            and 0 <= y0 < y1 <= CANONICAL_FRAME_HEIGHT,
            "A detected bounding box lies outside the canonical frame.",
        )
        require(
            x0 <= record["centroid_x_px"] < x1
            and y0 <= record["centroid_y_px"] < y1,
            "A detected centroid lies outside its bounding box.",
        )
        require(
            0 < record["detected_area_pixels"] <= (x1 - x0) * (y1 - y0),
            "A detected area is inconsistent with its bounding box.",
        )
        require(
            record["detector_status_reason"] is None,
            "A detected record cannot carry a status reason.",
        )
    elif status == "not_detected":
        require(visible is False, "A not-detected record must be empirically hidden.")
        require(
            all(value is None for value in geometry),
            "A not-detected record cannot carry localization.",
        )
        require(
            record["detector_status_reason"]
            in {"no_threshold_match", "no_valid_blob"},
            "A not-detected record needs the frozen rejection code.",
        )
    elif status == DETECTOR_STATUS_NOT_APPLICABLE:
        require(
            visible is None and record["detector_applicable"] is False,
            "A not-applicable record must be null and declared inapplicable.",
        )
        require(
            all(value is None for value in geometry),
            "A not-applicable record cannot carry localization.",
        )
        require(
            record["detector_status_reason"]
            == "no_target_object: no magenta target exists in this control",
            "A not-applicable record needs Person C's declared reason.",
        )
    elif status == DETECTOR_STATUS_UNREADABLE:
        require(visible is None, "An unreadable record cannot assert visibility.")
        require(
            all(value is None for value in geometry),
            "An unreadable record cannot carry localization.",
        )
        require(
            isinstance(record["detector_status_reason"], str)
            and record["detector_status_reason"],
            "An unreadable record needs an explicit failure reason.",
        )
    else:
        raise EmpiricalVisibilityError(f"Unknown detector_status {status!r}.")


def accounting(
    requested: Sequence[tuple[str, int]], records: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    """Complete, explicit accounting over every requested key."""

    produced = [(record["trajectory_id"], record["model_frame_idx"]) for record in records]
    requested_set = set(requested)
    produced_set = set(produced)
    duplicates = len(produced) - len(produced_set)
    return {
        "duplicate_output_key_count": duplicates,
        "empirical_hidden_count": sum(
            1 for record in records if record["detector_status"] == "not_detected"
        ),
        "empirical_visible_count": sum(
            1 for record in records if record["detector_status"] == "detected"
        ),
        "extra_output_key_count": len(produced_set - requested_set),
        "failed_frame_count": sum(
            1
            for record in records
            if record["detector_status"] == DETECTOR_STATUS_UNREADABLE
        ),
        "missing_output_key_count": len(requested_set - produced_set),
        "not_applicable_count": sum(
            1
            for record in records
            if record["detector_status"] == DETECTOR_STATUS_NOT_APPLICABLE
        ),
        "processed_frame_count": len(records),
        "requested_frame_count": len(requested),
        "status_accounted_frame_count": len(records),
    }
