"""Build Person E Phase 2 Step 2.4 v0.3 from corrected Person C inputs."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import platform
import subprocess
import sys
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mineocclude.experiments.registry import (
    formatted_json_bytes,
    hash_json_value,
    write_json_exclusive,
)
from mineocclude.vision.homography import (
    GROUND_CONTACT_LOCALIZATION_METHOD_VERSION,
    HOMOGRAPHY_ALGORITHM_VERSION,
    fit_marker_homography,
    homography_from_record,
    localize_ground_contact_from_background_pair,
    summarize_localization,
)
from mineocclude.vision.markers import (
    MARKER_DETECTOR_VERSION,
    MarkerDetectionError,
    detect_marker_point,
)
from mineocclude.vision.png_decode import (
    PNG_DECODER_VERSION,
    decode_png_rgb,
)

PERSON_E_STARTING_REVISION = "4950fee1d43ae3e853faf2123904a918035d20c7"
PERSON_C_REVISION = "aa2e8ed127b829092e866af1f2c099acc3a20051"
PERSON_C_REMOTE_REF = "origin/role/person-c-data"
PERSON_C_DEFAULT_REPOSITORY = Path(r"C:\Users\lollo\MineOcclude-Person-C")
PERSON_C_INPUT_PATH = "data/handoff_e/detector_calibration_inputs.json"
PERSON_C_PROBE_PATH = "data/handoff_e/independent_probe_points.json"
PERSON_C_CORRECTION_PATH = (
    "docs/reports/person_c_marker_worldcoord_convention_correction_v0_1.md"
)
BASE_EVIDENCE = ROOT / "docs" / "status" / "person_e_phase2_v0_1"
V0_2_EVIDENCE = ROOT / "docs" / "status" / "person_e_phase2_step2_4_v0_2"
CORRECTION_SCHEMA_VERSION = "person-e-phase2-step2.4-correction-v0.3"
RESOLUTION_ID = "resolution_640x360_rgb8"
WORLD_COORDINATE_SYSTEM = "ground_plane_world_xz_blocks_topface_centre"
WORLD_POINT_CONVENTION = "block_top_face_centre"
MAXIMUM_MEDIAN_WALL_ERROR_BLOCKS = 0.2
MAXIMUM_P95_WALL_ERROR_BLOCKS = 0.5
EXPECTED_LAYOUT_IDS = tuple(f"layout_{index:02d}" for index in range(1, 7))
MARKER_ORDER = (
    "north_west",
    "north_east",
    "south_east",
    "south_west",
)
MARKER_COLOURS = {
    "north_west": "blue",
    "north_east": "yellow",
    "south_east": "white",
    "south_west": "lime",
}
CORE_DOCUMENT_NAMES = (
    "detector_outputs.json",
    "homography_correspondences.json",
    "homography_record.json",
    "localization_validation_report.json",
    "phase2_status.json",
    "provenance_index.json",
    "source_validation.json",
    "step2_4_v0_3_receipt.json",
)
DOCUMENT_NAMES = frozenset((*CORE_DOCUMENT_NAMES, "deterministic_generation.json"))
IMMUTABLE_HISTORICAL_PATHS = (
    "docs/status/person_e_phase2_v0_1/homography_correspondences.json",
    "docs/status/person_e_phase2_v0_1/homography_record.json",
    "docs/status/person_e_phase2_v0_1/localization_validation_report.json",
    "docs/status/person_e_phase2_step2_4_v0_2/homography_correspondences.json",
    "docs/status/person_e_phase2_step2_4_v0_2/homography_record.json",
    "docs/status/person_e_phase2_step2_4_v0_2/localization_validation_report.json",
    "docs/status/person_e_phase2_step2_4_v0_2/phase2_status.json",
    "docs/status/person_e_phase2_step2_4_v0_2/provenance_index.json",
    (
        "docs/status/person_e_phase2_step2_4_v0_2/"
        "source_and_ground_contact_validation.json"
    ),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build or attest deterministic Person E Phase 2 Step 2.4 v0.3 evidence."
        )
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    generate = subparsers.add_parser(
        "generate",
        help="Generate the eight core v0.3 evidence documents.",
    )
    generate.add_argument("output_dir", type=Path)
    generate.add_argument(
        "--person-c-repository",
        type=Path,
        default=PERSON_C_DEFAULT_REPOSITORY,
    )
    generate.add_argument(
        "--person-c-revision",
        default=PERSON_C_REVISION,
    )
    generate.add_argument(
        "--base-evidence",
        type=Path,
        default=BASE_EVIDENCE,
    )
    generate.add_argument(
        "--v0-2-evidence",
        type=Path,
        default=V0_2_EVIDENCE,
    )

    attest = subparsers.add_parser(
        "attest-determinism",
        help=(
            "Compare two core generations and append the same deterministic "
            "attestation to an output generation."
        ),
    )
    attest.add_argument("first_dir", type=Path)
    attest.add_argument("second_dir", type=Path)
    attest.add_argument("output_dir", type=Path)
    return parser.parse_args()


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _run_git(repository: Path, arguments: Sequence[str]) -> bytes:
    completed = subprocess.run(
        ["git", "-C", str(repository), *arguments],
        check=False,
        capture_output=True,
    )
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise ValueError(f"Git command failed in {repository}: {detail}")
    return completed.stdout


def _git_blob(repository: Path, revision: str, path: str) -> bytes:
    return _run_git(
        repository,
        ["cat-file", "blob", f"{revision}:{path}"],
    )


def _git_json(
    repository: Path,
    revision: str,
    path: str,
) -> tuple[dict[str, Any], bytes]:
    payload = _git_blob(repository, revision, path)
    try:
        document = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"Invalid committed JSON {revision}:{path}.") from error
    if not isinstance(document, dict):
        raise TypeError(f"Committed JSON {revision}:{path} must be a mapping.")
    return document, payload


def _load_json(path: Path) -> tuple[dict[str, Any], str]:
    payload = path.read_bytes()
    try:
        document = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"Invalid JSON evidence {path}.") from error
    if not isinstance(document, dict):
        raise TypeError(f"Evidence {path} must be a mapping.")
    return document, _sha256(payload)


def _artifact_hash(document: Mapping[str, Any]) -> tuple[str, int]:
    payload = formatted_json_bytes(document)
    return _sha256(payload), len(payload)


def _percentile(
    values: Sequence[float],
    probability: float,
) -> float:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        raise ValueError("A percentile requires at least one value.")
    position = (len(ordered) - 1) * probability
    low = math.floor(position)
    high = math.ceil(position)
    if low == high:
        return ordered[low]
    weight = position - low
    return ordered[low] * (1.0 - weight) + ordered[high] * weight


def _metric_summary(
    records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    if not records:
        raise ValueError("Localization summary requires records.")
    signed = [float(record["signed_wall_parallel_error_blocks"]) for record in records]
    absolute = [abs(value) for value in signed]
    euclidean = [float(record["euclidean_error_blocks"]) for record in records]
    median_wall = _percentile(absolute, 0.5)
    p95_wall = _percentile(absolute, 0.95)
    return {
        "sample_count": len(records),
        "signed_wall_parallel_error_blocks": {
            "minimum": min(signed),
            "maximum": max(signed),
            "mean": sum(signed) / len(signed),
            "median": _percentile(signed, 0.5),
        },
        "median_absolute_wall_parallel_error_blocks": median_wall,
        "p95_absolute_wall_parallel_error_blocks": p95_wall,
        "median_euclidean_error_blocks": _percentile(euclidean, 0.5),
        "p95_euclidean_error_blocks": _percentile(euclidean, 0.95),
        "planning_gate_passed": (
            median_wall <= MAXIMUM_MEDIAN_WALL_ERROR_BLOCKS
            and p95_wall < MAXIMUM_P95_WALL_ERROR_BLOCKS
        ),
    }


def _image_region(image_xy: Sequence[float]) -> str:
    horizontal = (
        "left"
        if float(image_xy[0]) < 640 / 3.0
        else "right"
        if float(image_xy[0]) >= 1280 / 3.0
        else "center"
    )
    vertical = (
        "upper"
        if float(image_xy[1]) < 120
        else "lower"
        if float(image_xy[1]) >= 240
        else "middle"
    )
    return f"{horizontal}_{vertical}"


def _runtime_identity() -> tuple[dict[str, Any], str]:
    source_paths = (
        "src/mineocclude/vision/png_decode.py",
        "src/mineocclude/vision/markers.py",
        "src/mineocclude/vision/homography.py",
        "scripts/build_person_e_phase2_step2_4_v0_3.py",
    )
    identity = {
        "implementation_base_sha": PERSON_E_STARTING_REVISION,
        "python_implementation": platform.python_implementation(),
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "source_file_sha256": {
            path: _sha256((ROOT / path).read_bytes()) for path in source_paths
        },
        "png_decoder_version": PNG_DECODER_VERSION,
        "marker_detector_version": MARKER_DETECTOR_VERSION,
        "ground_contact_localization_method_version": (
            GROUND_CONTACT_LOCALIZATION_METHOD_VERSION
        ),
        "homography_algorithm_version": HOMOGRAPHY_ALGORITHM_VERSION,
    }
    return identity, hash_json_value(identity)


def _verify_person_c_revision(
    repository: Path,
    revision: str,
) -> None:
    remote = (
        _run_git(
            repository,
            ["rev-parse", f"{PERSON_C_REMOTE_REF}^{{commit}}"],
        )
        .decode("ascii")
        .strip()
    )
    if remote != PERSON_C_REVISION or revision != PERSON_C_REVISION:
        raise ValueError(
            "Person C remote or requested revision is not the exact "
            f"authoritative revision {PERSON_C_REVISION}."
        )
    _run_git(repository, ["cat-file", "-e", f"{revision}^{{commit}}"])


def _historical_hashes() -> dict[str, str]:
    hashes: dict[str, str] = {}
    for path in IMMUTABLE_HISTORICAL_PATHS:
        committed = _git_blob(ROOT, PERSON_E_STARTING_REVISION, path)
        current = (ROOT / path).read_bytes()
        if current != committed:
            raise ValueError(f"Historical Step 2.4 evidence changed: {path}.")
        hashes[path] = _sha256(current)
    return hashes


def _validate_authoritative_inputs(
    source: Mapping[str, Any],
    probes: Mapping[str, Any],
    marker_documents: Mapping[str, Mapping[str, Any]],
) -> tuple[
    dict[str, Mapping[str, Any]],
    dict[str, Mapping[str, Any]],
]:
    frames = source.get("frames")
    points = probes.get("points")
    if not isinstance(frames, list) or len(frames) != 72:
        raise ValueError("Person C detector source must contain exactly 72 frames.")
    if not isinstance(points, list) or len(points) != 36:
        raise ValueError("Person C probe source must contain exactly 36 probes.")
    if set(marker_documents) != set(EXPECTED_LAYOUT_IDS):
        raise ValueError("Exactly six corrected marker documents are required.")

    frame_by_id: dict[str, Mapping[str, Any]] = {}
    frame_counts: defaultdict[tuple[str, str, str], int] = defaultdict(int)
    for frame in frames:
        frame_id = frame.get("frame_id")
        if not isinstance(frame_id, str) or frame_id in frame_by_id:
            raise ValueError("Source frame IDs must be unique strings.")
        layout_id = frame.get("layout_id")
        split = frame.get("split")
        truth_class = frame.get("truth_class")
        if layout_id not in EXPECTED_LAYOUT_IDS:
            raise ValueError(f"{frame_id} has an unexpected layout.")
        if split not in {"calibration", "heldout"}:
            raise ValueError(f"{frame_id} has an invalid frozen split.")
        if truth_class not in {"visible", "negative"}:
            raise ValueError(f"{frame_id} has an invalid truth class.")
        expected_truth = truth_class == "visible"
        if frame.get("truth_present") is not expected_truth:
            raise ValueError(f"{frame_id} truth presence changed.")
        path = frame.get("png_path")
        if (
            not isinstance(path, str)
            or path
            != "data/handoff_e/calibration_frames/"
            f"{truth_class}/{layout_id}/"
            f"{frame_id.rsplit('_', 1)[1]}.png"
        ):
            raise ValueError(f"{frame_id} PNG binding changed.")
        frame_counts[(layout_id, split, truth_class)] += 1
        frame_by_id[frame_id] = frame
    expected_counts = {
        (layout_id, split, truth_class): 3
        for layout_id in EXPECTED_LAYOUT_IDS
        for split in ("calibration", "heldout")
        for truth_class in ("visible", "negative")
    }
    if dict(frame_counts) != expected_counts:
        raise ValueError("The predeclared 3/3 source split changed.")

    probe_by_frame: dict[str, Mapping[str, Any]] = {}
    probe_counts: defaultdict[tuple[str, str], int] = defaultdict(int)
    for point in points:
        frame_id = point.get("frame_id")
        if (
            not isinstance(frame_id, str)
            or frame_id in probe_by_frame
            or frame_id not in frame_by_id
        ):
            raise ValueError("Probe frame identities changed.")
        frame = frame_by_id[frame_id]
        for field in (
            "layout_id",
            "split",
            "source_artifact_id",
            "source_frame_idx",
        ):
            if point.get(field) != frame.get(field):
                raise ValueError(f"{frame_id} probe/source {field} changed.")
        if frame["truth_class"] != "visible":
            raise ValueError("Probes must bind only to visible frames.")
        world = point.get("probe_point_world_xz_blocks")
        if (
            not isinstance(world, list)
            or len(world) != 2
            or any(
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not math.isfinite(float(value))
                for value in world
            )
            or point.get("probe_point_world_y_blocks") != 4.0
        ):
            raise ValueError(f"{frame_id} probe coordinates changed.")
        probe_counts[(point["layout_id"], point["split"])] += 1
        probe_by_frame[frame_id] = point
    expected_probe_counts = {
        (layout_id, split): 3
        for layout_id in EXPECTED_LAYOUT_IDS
        for split in ("calibration", "heldout")
    }
    if dict(probe_counts) != expected_probe_counts:
        raise ValueError("The predeclared 3/3 probe split changed.")

    for layout_id, document in marker_documents.items():
        if (
            document.get("schema_version") != "1.0"
            or document.get("layout_id") != layout_id
            or document.get("world_coordinate_system") != WORLD_COORDINATE_SYSTEM
            or document.get("image_coordinate_system") != "pixel_center_xy_zero_based"
            or document.get("image_width_px") != 640
            or document.get("image_height_px") != 360
        ):
            raise ValueError(f"{layout_id} marker document conventions changed.")
        markers = document.get("marker_correspondences")
        if (
            not isinstance(markers, list)
            or len(markers) != 4
            or [marker.get("marker_role") for marker in markers] != list(MARKER_ORDER)
        ):
            raise ValueError(f"{layout_id} requires four canonical marker roles.")
        for marker in markers:
            role = marker["marker_role"]
            if (
                marker.get("marker_id") != role
                or marker.get("marker_color") != MARKER_COLOURS[role]
                or marker.get("world_point_convention") != WORLD_POINT_CONVENTION
                or marker.get("image_xy") is not None
            ):
                raise ValueError(f"{layout_id} {role} marker identity changed.")
            world = marker.get("world_xz_blocks")
            if (
                not isinstance(world, list)
                or len(world) != 2
                or any(
                    not isinstance(value, (int, float))
                    or isinstance(value, bool)
                    or not math.isfinite(float(value))
                    for value in world
                )
            ):
                raise ValueError(f"{layout_id} {role} world coordinate changed.")
            previous = marker.get("world_xz_blocks_previous_corner")
            if previous is not None and [
                float(previous[0]) + 0.5,
                float(previous[1]) + 0.5,
            ] != [float(world[0]), float(world[1])]:
                raise ValueError(f"{layout_id} {role} is not corner plus 0.5.")
        correction = document.get("marker_convention_correction")
        if (
            not isinstance(correction, Mapping)
            or correction.get("eval_probe_untouched") is not True
        ):
            raise ValueError(f"{layout_id} lacks the no-probe correction declaration.")
    return frame_by_id, probe_by_frame


def _source_record(
    frame: Mapping[str, Any],
    *,
    source_hash: str,
    decoded_hash: str,
) -> dict[str, Any]:
    return {
        "frame_id": frame["frame_id"],
        "layout_id": frame["layout_id"],
        "canonical_camera_pose_id": frame["canonical_camera_pose_id"],
        "split": frame["split"],
        "truth_class": frame["truth_class"],
        "truth_present": frame["truth_present"],
        "source_artifact_id": frame["source_artifact_id"],
        "source_frame_idx": frame["source_frame_idx"],
        "source_git_revision": PERSON_C_REVISION,
        "source_git_path": frame["png_path"],
        "source_frame_hash": source_hash,
        "decoded_rgb_hash": decoded_hash,
        "image_width_px": 640,
        "image_height_px": 360,
        "pixel_format": "rgb8",
    }


def build_core_documents(
    *,
    person_c_repository: Path,
    person_c_revision: str,
    base_evidence: Path,
    v0_2_evidence: Path,
) -> dict[str, dict[str, Any]]:
    """Build v0.3 without writing or using evaluation probes for selection."""

    _verify_person_c_revision(person_c_repository, person_c_revision)
    source, source_payload = _git_json(
        person_c_repository,
        person_c_revision,
        PERSON_C_INPUT_PATH,
    )
    probes, probe_payload = _git_json(
        person_c_repository,
        person_c_revision,
        PERSON_C_PROBE_PATH,
    )
    correction_payload = _git_blob(
        person_c_repository,
        person_c_revision,
        PERSON_C_CORRECTION_PATH,
    )
    marker_documents: dict[str, dict[str, Any]] = {}
    marker_payloads: dict[str, bytes] = {}
    for layout_id in EXPECTED_LAYOUT_IDS:
        path = f"data/handoff_e/markers_{layout_id}.json"
        document, payload = _git_json(person_c_repository, person_c_revision, path)
        marker_documents[layout_id] = document
        marker_payloads[layout_id] = payload
    frame_by_id, probe_by_frame = _validate_authoritative_inputs(
        source, probes, marker_documents
    )

    _config, config_hash = _load_json(base_evidence / "frozen_detector_config.json")
    detector_record, detector_record_hash = _load_json(
        base_evidence / "detector_version_record.json"
    )
    old_status, old_status_hash = _load_json(base_evidence / "phase2_status.json")
    old_provenance, old_provenance_hash = _load_json(
        base_evidence / "provenance_index.json"
    )
    _, v0_2_status_hash = _load_json(v0_2_evidence / "phase2_status.json")
    if detector_record.get("config_hash") != config_hash:
        raise ValueError("Frozen detector configuration hash changed.")
    historical_hashes = _historical_hashes()
    runtime_identity, runtime_hash = _runtime_identity()

    decoded_by_source_hash: dict[str, list[list[list[int]]]] = {}
    rgb_by_frame: dict[str, list[list[list[int]]]] = {}
    source_records: list[dict[str, Any]] = []
    source_record_by_id: dict[str, dict[str, Any]] = {}
    for frame_id, frame in sorted(frame_by_id.items()):
        payload = _git_blob(
            person_c_repository,
            person_c_revision,
            frame["png_path"],
        )
        source_hash = _sha256(payload)
        if source_hash != frame["source_frame_hash"]:
            raise ValueError(f"{frame_id} source PNG checksum changed.")
        if source_hash not in decoded_by_source_hash:
            decoded_by_source_hash[source_hash] = decode_png_rgb(payload)
        rgb = decoded_by_source_hash[source_hash]
        if len(rgb) != 360 or len(rgb[0]) != 640:
            raise ValueError(f"{frame_id} resolution changed.")
        decoded_hash = hash_json_value(rgb)
        record = _source_record(
            frame,
            source_hash=source_hash,
            decoded_hash=decoded_hash,
        )
        rgb_by_frame[frame_id] = rgb
        source_records.append(record)
        source_record_by_id[frame_id] = record

    marker_document_records = []
    marker_detection_layouts = []
    primary_detections: dict[str, dict[str, dict[str, Any]]] = {}
    marker_detection_cache: dict[
        tuple[str, tuple[tuple[str, str], ...]],
        tuple[dict[str, dict[str, Any]], list[dict[str, str]]],
    ] = {}
    blocked_layout_ids = []
    detector_failures = []
    for layout_id in EXPECTED_LAYOUT_IDS:
        document = marker_documents[layout_id]
        marker_path = f"data/handoff_e/markers_{layout_id}.json"
        marker_document_records.append(
            {
                "layout_id": layout_id,
                "source_git_path": marker_path,
                "source_document_hash": _sha256(marker_payloads[layout_id]),
                "world_coordinate_system": WORLD_COORDINATE_SYSTEM,
                "world_point_convention": WORLD_POINT_CONVENTION,
                "marker_count": 4,
                "canonical_camera_pose_id": document["canonical_camera_pose_id"],
                "marker_convention_correction": document[
                    "marker_convention_correction"
                ],
            }
        )
        colour_by_id = {
            marker["marker_id"]: marker["marker_color"]
            for marker in document["marker_correspondences"]
        }
        colour_key = tuple(sorted(colour_by_id.items()))
        negative_results = []
        primary_candidate: dict[str, dict[str, Any]] | None = None
        for index in range(6):
            frame_id = f"{layout_id}_negative_{index:03d}"
            source_record = source_record_by_id[frame_id]
            cache_key = (
                source_record["source_frame_hash"],
                colour_key,
            )
            if cache_key not in marker_detection_cache:
                detected: dict[str, dict[str, Any]] = {}
                failures = []
                for role in MARKER_ORDER:
                    try:
                        detected[role] = detect_marker_point(
                            rgb_by_frame[frame_id],
                            colour_by_id[role],
                        )
                    except MarkerDetectionError as error:
                        failures.append(
                            {
                                "marker_id": role,
                                "marker_role": role,
                                "marker_color": colour_by_id[role],
                                "reason": str(error),
                            }
                        )
                marker_detection_cache[cache_key] = (
                    detected,
                    failures,
                )
            detected, failures = marker_detection_cache[cache_key]
            frame_status = "detected" if not failures else "rejected"
            negative_results.append(
                {
                    "frame_id": frame_id,
                    "source_frame_hash": source_record["source_frame_hash"],
                    "source_git_path": source_record["source_git_path"],
                    "marker_count": len(detected),
                    "status": frame_status,
                    "markers": [
                        {
                            "marker_id": role,
                            "marker_role": role,
                            "marker_color": MARKER_COLOURS[role],
                            **detected[role],
                        }
                        for role in MARKER_ORDER
                        if role in detected
                    ],
                    "failures": failures,
                }
            )
            if failures:
                detector_failures.append(
                    {
                        "layout_id": layout_id,
                        "frame_id": frame_id,
                        "source_frame_hash": source_record["source_frame_hash"],
                        "failures": failures,
                    }
                )
            elif index == 0:
                primary_candidate = detected
        all_negative_frames_detected = all(
            row["status"] == "detected" for row in negative_results
        )
        if all_negative_frames_detected and primary_candidate is not None:
            primary_detections[layout_id] = primary_candidate
        else:
            blocked_layout_ids.append(layout_id)
        marker_detection_layouts.append(
            {
                "layout_id": layout_id,
                "canonical_camera_pose_id": document["canonical_camera_pose_id"],
                "primary_correspondence_frame_id": (f"{layout_id}_negative_000"),
                "all_negative_frames_detected": (all_negative_frames_detected),
                "negative_frame_count": 6,
                "negative_frame_results": negative_results,
            }
        )

    ground_contact_cache: dict[tuple[str, str], dict[str, Any]] = {}
    ground_contact_by_frame: dict[str, dict[str, Any]] = {}
    ground_contact_records = []
    for frame_id, probe in sorted(probe_by_frame.items()):
        visible = source_record_by_id[frame_id]
        suffix = frame_id.rsplit("_", 1)[1]
        background_id = f"{probe['layout_id']}_negative_{suffix}"
        background = source_record_by_id[background_id]
        if (
            visible["layout_id"] != background["layout_id"]
            or visible["split"] != background["split"]
            or visible["canonical_camera_pose_id"]
            != background["canonical_camera_pose_id"]
            or background["truth_class"] != "negative"
        ):
            raise ValueError(f"{frame_id} visible/background binding changed.")
        cache_key = (
            visible["source_frame_hash"],
            background["source_frame_hash"],
        )
        if cache_key not in ground_contact_cache:
            ground_contact_cache[cache_key] = (
                localize_ground_contact_from_background_pair(
                    rgb_by_frame[frame_id],
                    rgb_by_frame[background_id],
                )
            )
        ground_contact = ground_contact_cache[cache_key]
        ground_contact_by_frame[frame_id] = ground_contact
        ground_contact_records.append(
            {
                "frame_id": frame_id,
                "layout_id": visible["layout_id"],
                "split": visible["split"],
                "visible_source": visible,
                "paired_background_frame_id": background_id,
                "pairing_authority": ("person_c_predeclared_layout_split_ordinal_pair"),
                "background_source": background,
                "ground_contact": ground_contact,
            }
        )

    source_validation = {
        "schema_version": "1.0",
        "correction_schema_version": CORRECTION_SCHEMA_VERSION,
        "source_validation_schema_version": ("person-e-step2.4-source-validation-v0.3"),
        "source_revision": person_c_revision,
        "source_remote_ref": PERSON_C_REMOTE_REF,
        "source_document_path": PERSON_C_INPUT_PATH,
        "source_document_hash": _sha256(source_payload),
        "probe_document_path": PERSON_C_PROBE_PATH,
        "probe_document_hash": _sha256(probe_payload),
        "correction_report_path": PERSON_C_CORRECTION_PATH,
        "correction_report_hash": _sha256(correction_payload),
        "png_decoder_version": PNG_DECODER_VERSION,
        "validated_png_count": len(source_records),
        "unique_source_png_hash_count": len(decoded_by_source_hash),
        "source_split": {
            "authority": "person_c_predeclared_source_document",
            "calibration_visible_count": 18,
            "calibration_negative_count": 18,
            "heldout_visible_count": 18,
            "heldout_negative_count": 18,
            "changed_after_evaluation": False,
        },
        "probe_split": {
            "authority": "person_c_predeclared_probe_document",
            "calibration_count": 18,
            "heldout_count": 18,
            "changed_after_evaluation": False,
        },
        "marker_document_records": marker_document_records,
        "source_png_records": source_records,
    }

    detector_outputs = {
        "schema_version": "1.0",
        "correction_schema_version": CORRECTION_SCHEMA_VERSION,
        "detector_output_schema_version": ("person-e-step2.4-detector-outputs-v0.3"),
        "source_revision": person_c_revision,
        "png_decoder_version": PNG_DECODER_VERSION,
        "marker_detector_version": MARKER_DETECTOR_VERSION,
        "ground_contact_localization_method_version": (
            GROUND_CONTACT_LOCALIZATION_METHOD_VERSION
        ),
        "output_bias_adjustment_applied": False,
        "probe_targets_used_for_detector_selection": False,
        "probe_targets_used_for_ground_contact_selection": False,
        "layout_count": len(marker_detection_layouts),
        "detected_layout_count": len(primary_detections),
        "blocked_layout_count": len(blocked_layout_ids),
        "blocked_layout_ids": blocked_layout_ids,
        "all_layouts_detected": not blocked_layout_ids,
        "detector_failure_count": len(detector_failures),
        "detector_failures": detector_failures,
        "marker_layouts": marker_detection_layouts,
        "ground_contact_record_count": len(ground_contact_records),
        "ground_contact_records": ground_contact_records,
    }
    detector_outputs_hash, _ = _artifact_hash(detector_outputs)

    correspondence_layouts = []
    homography_by_layout = {}
    homography_records = []
    for layout_id in sorted(primary_detections):
        marker_document = marker_documents[layout_id]
        primary_frame_id = f"{layout_id}_negative_000"
        primary_source = source_record_by_id[primary_frame_id]
        detected = primary_detections[layout_id]
        image_points: dict[str, Sequence[float]] = {}
        world_points: dict[str, Sequence[float]] = {}
        markers = []
        marker_by_role = {
            marker["marker_role"]: marker
            for marker in marker_document["marker_correspondences"]
        }
        for role in MARKER_ORDER:
            marker = marker_by_role[role]
            image_xy = detected[role]["image_xy"]
            world_xz = marker["world_xz_blocks"]
            image_points[role] = image_xy
            world_points[role] = world_xz
            record = {
                "marker_id": role,
                "marker_role": role,
                "marker_color": MARKER_COLOURS[role],
                "world_point_convention": WORLD_POINT_CONVENTION,
                "world_xz_blocks": world_xz,
                "image_xy": image_xy,
                "source_frame_id": primary_frame_id,
                "source_frame_hash": primary_source["source_frame_hash"],
                "source_git_path": primary_source["source_git_path"],
                "detector_diagnostics": detected[role],
            }
            if "world_xz_blocks_previous_corner" in marker:
                record["world_xz_blocks_previous_corner"] = marker[
                    "world_xz_blocks_previous_corner"
                ]
            markers.append(record)
        correspondence = {
            "layout_id": layout_id,
            "canonical_camera_pose_id": marker_document["canonical_camera_pose_id"],
            "resolution_id": RESOLUTION_ID,
            "image_width_px": 640,
            "image_height_px": 360,
            "image_coordinate_system": ("pixel_center_xy_zero_based"),
            "world_coordinate_system": WORLD_COORDINATE_SYSTEM,
            "world_point_convention": WORLD_POINT_CONVENTION,
            "marker_order": list(MARKER_ORDER),
            "marker_detector_version": MARKER_DETECTOR_VERSION,
            "source_marker_document_path": (f"data/handoff_e/markers_{layout_id}.json"),
            "source_marker_document_hash": _sha256(marker_payloads[layout_id]),
            "source_frame_id": primary_frame_id,
            "source_frame_hash": primary_source["source_frame_hash"],
            "markers": markers,
            "output_bias_adjustment_applied": False,
        }
        correspondence_hash = hash_json_value(correspondence)
        correspondence["correspondence_hash"] = correspondence_hash
        correspondence_layouts.append(correspondence)
        homography = fit_marker_homography(
            image_points,
            world_points,
            marker_ids=MARKER_ORDER,
            layout_id=layout_id,
            canonical_camera_pose_id=marker_document["canonical_camera_pose_id"],
            resolution_id=RESOLUTION_ID,
            image_width_px=640,
            image_height_px=360,
            source_correspondence_hash=correspondence_hash,
            detector_version=MARKER_DETECTOR_VERSION,
            software_runtime_hash=runtime_hash,
        )
        homography_by_layout[layout_id] = homography
        homography_records.append(homography.to_record())

    correspondences = {
        "schema_version": "1.0",
        "correction_schema_version": CORRECTION_SCHEMA_VERSION,
        "homography_correspondence_schema_version": (
            "person-e-real-homography-correspondences-v0.3"
        ),
        "source_revision": person_c_revision,
        "source_world_coordinate_system": WORLD_COORDINATE_SYSTEM,
        "world_point_convention": WORLD_POINT_CONVENTION,
        "marker_detector_version": MARKER_DETECTOR_VERSION,
        "png_decoder_version": PNG_DECODER_VERSION,
        "marker_order": list(MARKER_ORDER),
        "layout_count": len(correspondence_layouts),
        "output_bias_adjustment_applied": False,
        "probe_targets_used_for_fitting": False,
        "layouts": correspondence_layouts,
    }
    correspondences_hash, _ = _artifact_hash(correspondences)

    homographies = {
        "schema_version": "1.0",
        "correction_schema_version": CORRECTION_SCHEMA_VERSION,
        "homography_record_schema_version": ("person-e-bound-homography-records-v0.3"),
        "source_revision": person_c_revision,
        "source_world_coordinate_system": WORLD_COORDINATE_SYSTEM,
        "world_point_convention": WORLD_POINT_CONVENTION,
        "correspondence_document_hash": correspondences_hash,
        "fitting_method_version": HOMOGRAPHY_ALGORITHM_VERSION,
        "marker_detector_version": MARKER_DETECTOR_VERSION,
        "png_decoder_version": PNG_DECODER_VERSION,
        "software_runtime": runtime_identity,
        "software_runtime_hash": runtime_hash,
        "layout_count": len(homography_records),
        "output_bias_adjustment_applied": False,
        "probe_targets_used_for_fitting": False,
        "records": homography_records,
    }
    homography_hash, _ = _artifact_hash(homographies)

    records = []
    per_layout = []
    for layout_id in EXPECTED_LAYOUT_IDS:
        if layout_id not in homography_by_layout:
            per_layout.append(
                {
                    "layout_id": layout_id,
                    "canonical_camera_pose_id": marker_documents[layout_id][
                        "canonical_camera_pose_id"
                    ],
                    "homography_version_id": None,
                    "wall_parallel_origin_xz": None,
                    "wall_parallel_positive_unit_xz": None,
                    "required_probe_count": 6,
                    "evaluated_probe_count": 0,
                    "coverage_passed": False,
                    "summary": None,
                    "blocker": ("public_marker_detector_rejected_source"),
                }
            )
            continue
        marker_by_role = {
            marker["marker_role"]: marker
            for marker in marker_documents[layout_id]["marker_correspondences"]
        }
        north_west = marker_by_role["north_west"]["world_xz_blocks"]
        north_east = marker_by_role["north_east"]["world_xz_blocks"]
        direction = [
            north_east[0] - north_west[0],
            north_east[1] - north_west[1],
        ]
        norm = math.hypot(*direction)
        wall_unit = [
            direction[0] / norm,
            direction[1] / norm,
        ]
        layout_probes = sorted(
            (
                probe
                for probe in probe_by_frame.values()
                if probe["layout_id"] == layout_id
            ),
            key=lambda probe: probe["frame_id"],
        )
        pairs = []
        regions = []
        sources = []
        for probe in layout_probes:
            frame_id = probe["frame_id"]
            contact = ground_contact_by_frame[frame_id]
            pairs.append(
                (
                    contact["image_xy"],
                    probe["probe_point_world_xz_blocks"],
                )
            )
            regions.append(_image_region(contact["image_xy"]))
            source_record = source_record_by_id[frame_id]
            sources.append(
                {
                    "frame_id": frame_id,
                    "layout_id": layout_id,
                    "split": probe["split"],
                    "source_artifact_id": probe["source_artifact_id"],
                    "source_frame_idx": probe["source_frame_idx"],
                    "source_frame_hash": source_record["source_frame_hash"],
                    "decoded_rgb_hash": source_record["decoded_rgb_hash"],
                    "paired_background_frame_id": (
                        f"{layout_id}_negative_{frame_id.rsplit('_', 1)[1]}"
                    ),
                    "ground_contact": contact,
                    "true_world_xz_blocks": probe["probe_point_world_xz_blocks"],
                    "world_y_blocks": probe["probe_point_world_y_blocks"],
                }
            )
        summary = summarize_localization(
            homography_by_layout[layout_id],
            pairs,
            wall_parallel_origin_xz=north_west,
            wall_parallel_positive_unit_xz=wall_unit,
            image_regions=regions,
            maximum_median_wall_error_blocks=(MAXIMUM_MEDIAN_WALL_ERROR_BLOCKS),
            maximum_p95_wall_error_blocks=(MAXIMUM_P95_WALL_ERROR_BLOCKS),
        )
        for record, source_record in zip(summary["records"], sources, strict=True):
            record.update(source_record)
            record["canonical_camera_pose_id"] = marker_documents[layout_id][
                "canonical_camera_pose_id"
            ]
        layout_records = summary["records"]
        records.extend(layout_records)
        layout_summary = _metric_summary(layout_records)
        per_layout.append(
            {
                "layout_id": layout_id,
                "canonical_camera_pose_id": marker_documents[layout_id][
                    "canonical_camera_pose_id"
                ],
                "homography_version_id": homography_by_layout[layout_id].to_record()[
                    "homography_version_id"
                ],
                "wall_parallel_origin_xz": north_west,
                "wall_parallel_positive_unit_xz": wall_unit,
                "required_probe_count": 6,
                "evaluated_probe_count": len(layout_records),
                "coverage_passed": len(layout_records) == 6,
                "summary": layout_summary,
            }
        )

    global_summary = _metric_summary(records)
    evaluated_subset_error_gate_passed = global_summary.pop("planning_gate_passed")
    calibration_records = [
        record for record in records if record["split"] == "calibration"
    ]
    heldout_records = [record for record in records if record["split"] == "heldout"]
    coverage_passed = len(records) == 36 and all(
        row["coverage_passed"] for row in per_layout
    )
    formal_gate_passed = coverage_passed and evaluated_subset_error_gate_passed
    region_groups: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        region_groups[record["image_region"]].append(record)
    localization = {
        "schema_version": "1.0",
        "correction_schema_version": CORRECTION_SCHEMA_VERSION,
        "localization_report_schema_version": (
            "person-e-real-localization-report-v0.3"
        ),
        "source_revision": person_c_revision,
        "source_probe_document_path": PERSON_C_PROBE_PATH,
        "source_probe_document_hash": _sha256(probe_payload),
        "homography_document_hash": homography_hash,
        "detector_output_document_hash": detector_outputs_hash,
        "png_decoder_version": PNG_DECODER_VERSION,
        "marker_detector_version": MARKER_DETECTOR_VERSION,
        "ground_contact_localization_method_version": (
            GROUND_CONTACT_LOCALIZATION_METHOD_VERSION
        ),
        "world_coordinate_system": WORLD_COORDINATE_SYSTEM,
        "world_point_convention": WORLD_POINT_CONVENTION,
        "output_bias_adjustment_applied": False,
        "output_offset_blocks": None,
        "probe_targets_used_for_fitting": False,
        "probe_targets_used_for_detector_selection": False,
        "probe_targets_used_for_ground_contact_selection": False,
        "probe_targets_used_for_exclusion_selection": False,
        "excluded_layout_ids": [],
        "blocked_layout_ids": blocked_layout_ids,
        "required_layout_count": 6,
        "evaluated_layout_count": len(homography_by_layout),
        "required_probe_count": 36,
        "evaluated_probe_count": len(records),
        "calibration_probe_count": len(calibration_records),
        "heldout_probe_count": len(heldout_records),
        "coverage_passed": coverage_passed,
        "all_required_probes_evaluated": coverage_passed,
        "evaluated_subset_error_gate_passed": (evaluated_subset_error_gate_passed),
        "formal_population": ("all_36_predeclared_independent_probes"),
        "required_gate": {
            "maximum_median_absolute_wall_parallel_error_blocks": (
                MAXIMUM_MEDIAN_WALL_ERROR_BLOCKS
            ),
            "maximum_p95_absolute_wall_parallel_error_blocks_exclusive": (
                MAXIMUM_P95_WALL_ERROR_BLOCKS
            ),
        },
        **global_summary,
        "planning_gate_passed": formal_gate_passed,
        "formal_planning_gate_passed": formal_gate_passed,
        "gate_decision": (
            "passed_complete_coverage_and_error_thresholds"
            if formal_gate_passed
            else (
                "not_passed_incomplete_probe_coverage"
                if not coverage_passed
                else "not_passed_error_thresholds"
            )
        ),
        "remaining_blockers": (
            [
                {
                    "blocker_id": ("layout_03_clipped_ground_markers"),
                    "kind": "source_evidence",
                    "blocked_probe_count": 6,
                    "detail": (
                        "The public marker detector rejects layout_03 "
                        "north-west/blue and north-east/yellow because both "
                        "touch the image border in all six negative frames."
                    ),
                }
            ]
            if blocked_layout_ids == ["layout_03"]
            else []
        ),
        "calibration_summary": _metric_summary(calibration_records),
        "heldout_summary": _metric_summary(heldout_records),
        "per_layout": per_layout,
        "by_image_region": [
            {
                "image_region": region,
                **_metric_summary(region_records),
            }
            for region, region_records in sorted(region_groups.items())
        ],
        "worst_cases": sorted(
            (
                {
                    "frame_id": record["frame_id"],
                    "layout_id": record["layout_id"],
                    "split": record["split"],
                    "image_region": record["image_region"],
                    "signed_wall_parallel_error_blocks": record[
                        "signed_wall_parallel_error_blocks"
                    ],
                    "absolute_wall_parallel_error_blocks": abs(
                        record["signed_wall_parallel_error_blocks"]
                    ),
                    "euclidean_error_blocks": record["euclidean_error_blocks"],
                }
                for record in records
            ),
            key=lambda row: (
                -row["absolute_wall_parallel_error_blocks"],
                row["frame_id"],
            ),
        )[:5],
        "records": records,
    }

    receipt = {
        "schema_version": "1.0",
        "correction_schema_version": CORRECTION_SCHEMA_VERSION,
        "receipt_schema_version": ("person-e-phase2-step2.4-receipt-v0.3"),
        "person_e_starting_revision": PERSON_E_STARTING_REVISION,
        "person_c_source_revision": person_c_revision,
        "person_c_remote_ref": PERSON_C_REMOTE_REF,
        "corner_to_top_face_centre_correction": {
            "correction_id": ("person-c-marker-worldcoord-topface-centre-v1"),
            "source_world_coordinate_system": (WORLD_COORDINATE_SYSTEM),
            "world_point_convention": WORLD_POINT_CONVENTION,
            "source_document_hashes": {
                layout_id: _sha256(marker_payloads[layout_id])
                for layout_id in EXPECTED_LAYOUT_IDS
            },
            "corrected_existing_layout_count": sum(
                any(
                    "world_xz_blocks_previous_corner" in marker
                    for marker in marker_documents[layout_id]["marker_correspondences"]
                )
                for layout_id in EXPECTED_LAYOUT_IDS
            ),
            "born_correct_recapture_layout_ids": ["layout_02"],
            "evaluation_probe_coordinates_changed": False,
            "description": (
                "Person C corrected marker world points from BlockPos "
                "corners to the detected block top-face centres. Person E "
                "re-detected image points from committed PNG bytes."
            ),
        },
        "method_integrity": {
            "marker_image_coordinates_recomputed": True,
            "marker_image_coordinates_copied_from_reports": False,
            "homographies_fit_from_marker_correspondences_only": True,
            "frozen_ground_contact_localizer_used": True,
            "output_bias_adjustment_applied": False,
            "output_offset_blocks": None,
            "probe_derived_tuning_applied": False,
            "probe_filtering_applied": False,
            "exclusions_applied": False,
            "blocked_layout_ids": blocked_layout_ids,
            "source_split_changed_after_evaluation": False,
        },
        "formal_gate": {
            "required_probe_count": 36,
            "evaluated_probe_count": len(records),
            "coverage_passed": coverage_passed,
            "blocked_layout_ids": blocked_layout_ids,
            "evaluated_subset_error_gate_passed": (evaluated_subset_error_gate_passed),
            "median_absolute_wall_parallel_error_blocks": (
                global_summary["median_absolute_wall_parallel_error_blocks"]
            ),
            "p95_absolute_wall_parallel_error_blocks": (
                global_summary["p95_absolute_wall_parallel_error_blocks"]
            ),
            "maximum_median_absolute_wall_parallel_error_blocks": (
                MAXIMUM_MEDIAN_WALL_ERROR_BLOCKS
            ),
            "maximum_p95_absolute_wall_parallel_error_blocks_exclusive": (
                MAXIMUM_P95_WALL_ERROR_BLOCKS
            ),
            "planning_gate_passed": formal_gate_passed,
        },
        "historical_step2_4_evidence_immutable": True,
        "historical_step2_4_sha256": historical_hashes,
        "unchanged_step_evidence": {
            "step_2_1": ("../person_e_phase2_v0_1/step2_1_registry_receipt.json"),
            "step_2_2": ("../person_e_phase2_v0_1/frozen_split_manifest.json"),
            "step_2_3": ("../person_e_phase2_v0_1/calibration_report.json"),
        },
        "deterministic_generation_evidence": ("deterministic_generation.json"),
    }

    primary_documents = {
        "source_validation.json": source_validation,
        "detector_outputs.json": detector_outputs,
        "homography_correspondences.json": correspondences,
        "homography_record.json": homographies,
        "localization_validation_report.json": localization,
        "step2_4_v0_3_receipt.json": receipt,
    }
    direct_inputs = {
        "source_validation.json": [
            f"git:{person_c_revision}:{PERSON_C_INPUT_PATH}",
            f"git:{person_c_revision}:{PERSON_C_PROBE_PATH}",
            *[
                f"git:{person_c_revision}:data/handoff_e/markers_{layout_id}.json"
                for layout_id in EXPECTED_LAYOUT_IDS
            ],
        ],
        "detector_outputs.json": [
            "source_validation.json",
            "../person_e_phase2_v0_1/frozen_detector_config.json",
        ],
        "homography_correspondences.json": [
            "source_validation.json",
            "detector_outputs.json",
        ],
        "homography_record.json": ["homography_correspondences.json"],
        "localization_validation_report.json": [
            "detector_outputs.json",
            "homography_record.json",
            f"git:{person_c_revision}:{PERSON_C_PROBE_PATH}",
        ],
        "step2_4_v0_3_receipt.json": [
            "source_validation.json",
            "detector_outputs.json",
            "homography_record.json",
            "localization_validation_report.json",
        ],
    }
    provenance_records = []
    for path, document in sorted(primary_documents.items()):
        digest, size = _artifact_hash(document)
        provenance_records.append(
            {
                "artifact_id": (f"person_e_phase2_step2_4_v0_3:{path}"),
                "path": path,
                "sha256": digest,
                "size_bytes": size,
                "direct_inputs": direct_inputs[path],
                "status": "accepted_v0_3_evidence",
            }
        )
    provenance = {
        "schema_version": "1.0",
        "correction_schema_version": CORRECTION_SCHEMA_VERSION,
        "provenance_index_schema_version": (
            "person-e-phase2-step2.4-provenance-index-v0.3"
        ),
        "source_revisions": {
            "person_c": person_c_revision,
            "person_e_starting_head": PERSON_E_STARTING_REVISION,
        },
        "source_document_hashes": {
            "detector_calibration_inputs": _sha256(source_payload),
            "independent_probe_points": _sha256(probe_payload),
            "person_c_correction_report": _sha256(correction_payload),
        },
        "unchanged_upstream_evidence": {
            "frozen_detector_config_hash": config_hash,
            "detector_version_record_hash": detector_record_hash,
            "previous_phase2_status_hash": old_status_hash,
            "previous_phase2_provenance_hash": old_provenance_hash,
            "previous_v0_2_status_hash": v0_2_status_hash,
            "shared_immutable_registry_status": old_provenance[
                "shared_immutable_registry_status"
            ],
        },
        "historical_step2_4_sha256": historical_hashes,
        "records": provenance_records,
    }
    provenance_hash, _ = _artifact_hash(provenance)

    status = copy.deepcopy(old_status)
    status.update(
        {
            "correction_schema_version": CORRECTION_SCHEMA_VERSION,
            "status_schema_version": "person-e-phase2-status-v0.3",
            "previous_status": {
                "path": "../person_e_phase2_v0_1/phase2_status.json",
                "sha256": old_status_hash,
                "status": "retained_not_overwritten",
            },
            "provenance_index_hash": provenance_hash,
            "homography_planning_gate_passed": formal_gate_passed,
        }
    )
    for step in status["steps"]:
        if step["step"] in {"2.1", "2.2", "2.3"}:
            step["evidence"] = "../person_e_phase2_v0_1/" + step["evidence"]
        elif step["step"] == "2.4":
            step.update(
                {
                    "status": ("PASS" if formal_gate_passed else "PARTIAL"),
                    "evidence": ("localization_validation_report.json"),
                    "remaining_blocker": (
                        None
                        if formal_gate_passed
                        else ("layout_03_clipped_markers_block_complete_probe_coverage")
                    ),
                }
            )
    status["overall_status"] = (
        "PASS"
        if all(step["status"] == "PASS" for step in status["steps"])
        else "PARTIAL"
    )
    documents = {
        **primary_documents,
        "provenance_index.json": provenance,
        "phase2_status.json": status,
    }
    validate_v0_3_documents(documents, require_determinism=False)
    return documents


def _require_exact_document_names(
    documents: Mapping[str, Mapping[str, Any]],
    *,
    require_determinism: bool,
) -> None:
    expected = DOCUMENT_NAMES if require_determinism else frozenset(CORE_DOCUMENT_NAMES)
    if set(documents) != expected:
        raise ValueError("The v0.3 evidence document set changed.")


def validate_v0_3_documents(
    documents: Mapping[str, Mapping[str, Any]],
    *,
    require_determinism: bool = True,
) -> None:
    """Validate v0.3 semantics without trusting claimed gate fields."""

    _require_exact_document_names(documents, require_determinism=require_determinism)
    source = documents["source_validation.json"]
    detector = documents["detector_outputs.json"]
    correspondences = documents["homography_correspondences.json"]
    homographies = documents["homography_record.json"]
    localization = documents["localization_validation_report.json"]
    receipt = documents["step2_4_v0_3_receipt.json"]
    provenance = documents["provenance_index.json"]
    status = documents["phase2_status.json"]

    for document in documents.values():
        if (
            document.get("schema_version") != "1.0"
            or document.get("correction_schema_version") != CORRECTION_SCHEMA_VERSION
        ):
            raise ValueError("A v0.3 schema binding changed.")
    if (
        source.get("source_revision") != PERSON_C_REVISION
        or source.get("source_remote_ref") != PERSON_C_REMOTE_REF
        or source.get("validated_png_count") != 72
        or len(source.get("source_png_records", [])) != 72
    ):
        raise ValueError("The exact Person C source binding changed.")
    marker_documents = source.get("marker_document_records")
    if (
        not isinstance(marker_documents, list)
        or len(marker_documents) != 6
        or [row.get("layout_id") for row in marker_documents]
        != list(EXPECTED_LAYOUT_IDS)
        or any(
            row.get("world_coordinate_system") != WORLD_COORDINATE_SYSTEM
            or row.get("world_point_convention") != WORLD_POINT_CONVENTION
            or row.get("marker_count") != 4
            for row in marker_documents
        )
    ):
        raise ValueError("Top-face-centre marker authority changed.")
    if (
        source.get("source_split", {}).get("changed_after_evaluation") is not False
        or source.get("probe_split", {}).get("changed_after_evaluation") is not False
        or source.get("probe_split", {}).get("calibration_count") != 18
        or source.get("probe_split", {}).get("heldout_count") != 18
    ):
        raise ValueError("The predeclared source split changed.")

    marker_layouts = detector.get("marker_layouts")
    if (
        detector.get("source_revision") != PERSON_C_REVISION
        or detector.get("marker_detector_version") != MARKER_DETECTOR_VERSION
        or detector.get("output_bias_adjustment_applied") is not False
        or not isinstance(marker_layouts, list)
        or len(marker_layouts) != 6
    ):
        raise ValueError("Detector output identity changed.")
    detected_layout_ids = [
        layout["layout_id"]
        for layout in marker_layouts
        if layout.get("all_negative_frames_detected") is True
    ]
    blocked_layout_ids = [
        layout["layout_id"]
        for layout in marker_layouts
        if layout.get("all_negative_frames_detected") is False
    ]
    if (
        detector.get("detected_layout_count") != len(detected_layout_ids)
        or detector.get("blocked_layout_count") != len(blocked_layout_ids)
        or detector.get("blocked_layout_ids") != blocked_layout_ids
        or detector.get("all_layouts_detected") is not (not blocked_layout_ids)
    ):
        raise ValueError("Detector coverage summary changed.")
    for layout in marker_layouts:
        if (
            layout.get("layout_id") not in EXPECTED_LAYOUT_IDS
            or layout.get("negative_frame_count") != 6
            or len(layout.get("negative_frame_results", [])) != 6
        ):
            raise ValueError("Four-marker coverage changed.")
        for frame in layout["negative_frame_results"]:
            detected = frame.get("status") == "detected"
            if (
                detected
                and (
                    frame.get("marker_count") != 4
                    or len(frame.get("markers", [])) != 4
                    or frame.get("failures") != []
                )
            ) or (
                not detected
                and (
                    frame.get("status") != "rejected"
                    or not frame.get("failures")
                    or frame.get("marker_count", 4) >= 4
                )
            ):
                raise ValueError("A marker frame did not fail closed.")
    layout_02 = next(row for row in marker_layouts if row["layout_id"] == "layout_02")
    if layout_02.get("all_negative_frames_detected") is not True or any(
        len(frame["markers"]) != 4 for frame in layout_02["negative_frame_results"]
    ):
        raise ValueError("Layout 02 marker coverage changed.")
    if (
        detector.get("ground_contact_record_count") != 36
        or len(detector.get("ground_contact_records", [])) != 36
    ):
        raise ValueError("Ground-contact coverage changed.")

    if (
        correspondences.get("source_revision") != PERSON_C_REVISION
        or correspondences.get("source_world_coordinate_system")
        != WORLD_COORDINATE_SYSTEM
        or correspondences.get("world_point_convention") != WORLD_POINT_CONVENTION
        or correspondences.get("marker_order") != list(MARKER_ORDER)
        or correspondences.get("layout_count") != len(detected_layout_ids)
        or [layout.get("layout_id") for layout in correspondences.get("layouts", [])]
        != detected_layout_ids
        or correspondences.get("output_bias_adjustment_applied") is not False
        or correspondences.get("probe_targets_used_for_fitting") is not False
    ):
        raise ValueError("Homography correspondence binding changed.")
    for layout in correspondences["layouts"]:
        if (
            layout.get("world_coordinate_system") != WORLD_COORDINATE_SYSTEM
            or layout.get("world_point_convention") != WORLD_POINT_CONVENTION
            or len(layout.get("markers", [])) != 4
            or any(
                marker.get("world_point_convention") != WORLD_POINT_CONVENTION
                for marker in layout["markers"]
            )
        ):
            raise ValueError("A marker correspondence changed.")
        unhashed = dict(layout)
        claimed_hash = unhashed.pop("correspondence_hash")
        if hash_json_value(unhashed) != claimed_hash:
            raise ValueError("A correspondence hash changed.")

    if (
        homographies.get("source_revision") != PERSON_C_REVISION
        or homographies.get("source_world_coordinate_system") != WORLD_COORDINATE_SYSTEM
        or homographies.get("world_point_convention") != WORLD_POINT_CONVENTION
        or homographies.get("layout_count") != len(detected_layout_ids)
        or homographies.get("output_bias_adjustment_applied") is not False
        or homographies.get("probe_targets_used_for_fitting") is not False
        or len(homographies.get("records", [])) != len(detected_layout_ids)
    ):
        raise ValueError("Homography records changed.")
    for record in homographies["records"]:
        homography_from_record(record)

    required_gate = localization.get("required_gate", {})
    records = localization.get("records")
    expected_evaluated_count = 6 * len(detected_layout_ids)
    expected_split_count = 3 * len(detected_layout_ids)
    expected_coverage = expected_evaluated_count == 36
    if (
        localization.get("source_revision") != PERSON_C_REVISION
        or required_gate.get("maximum_median_absolute_wall_parallel_error_blocks")
        != MAXIMUM_MEDIAN_WALL_ERROR_BLOCKS
        or required_gate.get(
            "maximum_p95_absolute_wall_parallel_error_blocks_exclusive"
        )
        != MAXIMUM_P95_WALL_ERROR_BLOCKS
        or localization.get("required_probe_count") != 36
        or localization.get("evaluated_probe_count") != expected_evaluated_count
        or localization.get("calibration_probe_count") != expected_split_count
        or localization.get("heldout_probe_count") != expected_split_count
        or localization.get("coverage_passed") is not expected_coverage
        or localization.get("all_required_probes_evaluated") is not expected_coverage
        or localization.get("blocked_layout_ids") != blocked_layout_ids
        or not isinstance(records, list)
        or len(records) != expected_evaluated_count
    ):
        raise ValueError("Localization coverage or thresholds changed.")
    if (
        localization.get("output_bias_adjustment_applied") is not False
        or localization.get("output_offset_blocks") is not None
        or localization.get("probe_targets_used_for_fitting") is not False
        or localization.get("probe_targets_used_for_detector_selection") is not False
        or localization.get("probe_targets_used_for_ground_contact_selection")
        is not False
        or localization.get("probe_targets_used_for_exclusion_selection") is not False
        or localization.get("excluded_layout_ids") != []
    ):
        raise ValueError("A prohibited output adjustment was introduced.")
    recomputed = _metric_summary(records)
    for field in (
        "median_absolute_wall_parallel_error_blocks",
        "p95_absolute_wall_parallel_error_blocks",
        "median_euclidean_error_blocks",
        "p95_euclidean_error_blocks",
    ):
        if localization.get(field) != recomputed[field]:
            raise ValueError("Localization summary was not measured.")
    measured_subset_pass = recomputed["planning_gate_passed"]
    measured_pass = expected_coverage and measured_subset_pass
    if (
        localization.get("planning_gate_passed") is not measured_pass
        or localization.get("formal_planning_gate_passed") is not measured_pass
        or localization.get("evaluated_subset_error_gate_passed")
        is not measured_subset_pass
    ):
        raise ValueError("Formal gate is not derived from measurements.")
    per_layout = localization.get("per_layout", [])
    if (
        not isinstance(per_layout, list)
        or len(per_layout) != 6
        or [row.get("layout_id") for row in per_layout] != list(EXPECTED_LAYOUT_IDS)
    ):
        raise ValueError("Per-layout coverage changed.")
    for row in per_layout:
        blocked = row["layout_id"] in blocked_layout_ids
        if (
            row.get("required_probe_count") != 6
            or row.get("evaluated_probe_count") != (0 if blocked else 6)
            or row.get("coverage_passed") is not (not blocked)
            or (row.get("summary") is None) is not blocked
        ):
            raise ValueError("Per-layout coverage changed.")

    method = receipt.get("method_integrity", {})
    if (
        receipt.get("person_c_source_revision") != PERSON_C_REVISION
        or method.get("marker_image_coordinates_recomputed") is not True
        or method.get("marker_image_coordinates_copied_from_reports") is not False
        or method.get("homographies_fit_from_marker_correspondences_only") is not True
        or method.get("output_bias_adjustment_applied") is not False
        or method.get("output_offset_blocks") is not None
        or method.get("probe_derived_tuning_applied") is not False
        or method.get("probe_filtering_applied") is not False
        or method.get("exclusions_applied") is not False
    ):
        raise ValueError("Receipt method-integrity declaration changed.")
    receipt_gate = receipt.get("formal_gate", {})
    if (
        receipt_gate.get("planning_gate_passed") is not measured_pass
        or receipt_gate.get("median_absolute_wall_parallel_error_blocks")
        != recomputed["median_absolute_wall_parallel_error_blocks"]
        or receipt_gate.get("p95_absolute_wall_parallel_error_blocks")
        != recomputed["p95_absolute_wall_parallel_error_blocks"]
    ):
        raise ValueError("Receipt gate was not measured.")
    if provenance.get("source_revisions", {}).get("person_c") != (PERSON_C_REVISION):
        raise ValueError("Provenance source revision changed.")

    step_by_id = {step["step"]: step for step in status.get("steps", [])}
    if (
        set(step_by_id) != {"2.1", "2.2", "2.3", "2.4"}
        or any(step_by_id[step]["status"] != "PASS" for step in ("2.1", "2.2", "2.3"))
        or step_by_id["2.4"]["status"] != ("PASS" if measured_pass else "PARTIAL")
        or status.get("homography_planning_gate_passed") is not measured_pass
        or status.get("overall_status") != ("PASS" if measured_pass else "PARTIAL")
    ):
        raise ValueError("Phase 2 status is not measurement-derived.")

    if require_determinism:
        determinism = documents["deterministic_generation.json"]
        if (
            determinism.get("byte_identical") is not True
            or determinism.get("compared_document_count") != len(CORE_DOCUMENT_NAMES)
            or determinism.get("first_generation_sha256")
            != determinism.get("second_generation_sha256")
        ):
            raise ValueError("Deterministic-generation evidence changed.")
        expected_hashes = {
            name: _sha256(formatted_json_bytes(documents[name]))
            for name in CORE_DOCUMENT_NAMES
        }
        if determinism.get("first_generation_sha256") != expected_hashes:
            raise ValueError("Deterministic hashes do not match the evidence.")


def attest_determinism(
    first_dir: Path,
    second_dir: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """Compare two core generations and write a stable attestation."""

    first_hashes = {}
    second_hashes = {}
    for name in CORE_DOCUMENT_NAMES:
        first = (first_dir / name).read_bytes()
        second = (second_dir / name).read_bytes()
        output = (output_dir / name).read_bytes()
        if first != second or first != output:
            raise ValueError(f"Deterministic regeneration mismatch: {name}.")
        first_hashes[name] = _sha256(first)
        second_hashes[name] = _sha256(second)
    document = {
        "schema_version": "1.0",
        "correction_schema_version": CORRECTION_SCHEMA_VERSION,
        "deterministic_generation_schema_version": (
            "person-e-deterministic-generation-v0.3"
        ),
        "generation_labels": [
            "independent_regeneration_a",
            "independent_regeneration_b",
        ],
        "compared_document_count": len(CORE_DOCUMENT_NAMES),
        "first_generation_sha256": first_hashes,
        "second_generation_sha256": second_hashes,
        "byte_identical": first_hashes == second_hashes,
        "canonical_json_required": True,
    }
    write_json_exclusive(
        output_dir / "deterministic_generation.json",
        document,
    )
    documents = {
        path.name: json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(output_dir.glob("*.json"))
    }
    validate_v0_3_documents(documents)
    return document


def main() -> None:
    args = parse_args()
    if args.command == "generate":
        documents = build_core_documents(
            person_c_repository=args.person_c_repository,
            person_c_revision=args.person_c_revision,
            base_evidence=args.base_evidence,
            v0_2_evidence=args.v0_2_evidence,
        )
        for relative_path, document in sorted(documents.items()):
            write_json_exclusive(
                args.output_dir / relative_path,
                document,
            )
        return
    attest_determinism(
        args.first_dir,
        args.second_dir,
        args.output_dir,
    )


if __name__ == "__main__":
    main()
