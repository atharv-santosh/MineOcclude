"""Build the fail-closed Person E Phase 2 Step 2.4 correction evidence."""

# ruff: noqa: I001

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
    localize_ground_contact_from_background_pair,
    summarize_localization,
)
from mineocclude.vision.magenta import HsvRange, detect_magenta
from mineocclude.vision.markers import (
    MARKER_COLOUR_GATES,
    MARKER_DETECTOR_VERSION,
    MarkerDetectionError,
    detect_marker_point,
)
from mineocclude.vision.png_decode import PNG_DECODER_VERSION, decode_png_rgb


PERSON_E_BASE_SHA = "e9af9394b93674dc735be38bb7c0c519c66cc135"
PERSON_C_REVISION = "00784756f21895d19aff44572496c956cc5d932f"
PERSON_C_INPUT_PATH = "data/handoff_e/detector_calibration_inputs.json"
PERSON_C_PROBE_PATH = "data/handoff_e/independent_probe_points.json"
BASE_EVIDENCE = ROOT / "docs" / "status" / "person_e_phase2_v0_1"
CORRECTION_SCHEMA_VERSION = "person-e-phase2-step2.4-correction-v0.2"
RESOLUTION_ID = "resolution_640x360_rgb8"
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
EXPECTED_WHITE_GATE = (0.0, 360.0, 0.0, 0.10, 0.60, 1.0)
EXPECTED_LAYOUT_IDS = tuple(f"layout_{index:02d}" for index in range(6))
EXPECTED_BLOCKED_LAYOUT = "layout_02"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Recompute Step 2.4 with the public PNG and ground-marker "
            "implementations while preserving the frozen split and detector."
        )
    )
    parser.add_argument("output_dir", type=Path)
    parser.add_argument(
        "--base-evidence",
        type=Path,
        default=BASE_EVIDENCE,
    )
    parser.add_argument(
        "--person-c-revision",
        default=PERSON_C_REVISION,
    )
    return parser.parse_args()


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _git_blob(revision: str, path: str) -> bytes:
    completed = subprocess.run(
        ["git", "-C", str(ROOT), "cat-file", "blob", f"{revision}:{path}"],
        check=False,
        capture_output=True,
    )
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise ValueError(f"Missing committed input {revision}:{path}: {detail}")
    return completed.stdout


def _git_json(revision: str, path: str) -> tuple[dict[str, Any], bytes]:
    payload = _git_blob(revision, path)
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


def _percentile(values: Sequence[float], probability: float) -> float:
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


def _metric_summary(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    signed = [
        float(record["signed_wall_parallel_error_blocks"])
        for record in records
    ]
    absolute = [abs(value) for value in signed]
    euclidean = [
        float(record["euclidean_error_blocks"]) for record in records
    ]
    return {
        "sample_count": len(records),
        "signed_wall_parallel_error_blocks": {
            "minimum": min(signed),
            "maximum": max(signed),
            "mean": sum(signed) / len(signed),
            "median": _percentile(signed, 0.5),
        },
        "median_absolute_wall_parallel_error_blocks": _percentile(
            absolute, 0.5
        ),
        "p95_absolute_wall_parallel_error_blocks": _percentile(
            absolute, 0.95
        ),
        "median_euclidean_error_blocks": _percentile(euclidean, 0.5),
        "p95_euclidean_error_blocks": _percentile(euclidean, 0.95),
    }


def _runtime_identity() -> tuple[dict[str, Any], str]:
    source_paths = (
        "src/mineocclude/vision/png_decode.py",
        "src/mineocclude/vision/markers.py",
        "src/mineocclude/vision/magenta.py",
        "src/mineocclude/vision/homography.py",
        "scripts/correct_person_e_phase2_step2_4_evidence.py",
    )
    identity = {
        "implementation_base_sha": PERSON_E_BASE_SHA,
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


def _detector_kwargs(config: Mapping[str, Any]) -> dict[str, Any]:
    detector = config["detector"]
    return {
        "hsv_ranges": [
            HsvRange(
                row["h_min"],
                row["h_max"],
                row["s_min"],
                row["s_max"],
                row["v_min"],
                row["v_max"],
            )
            for row in detector["hsv_ranges"]
        ],
        "min_area_pixels": detector["blob"]["min_area_pixels"],
        "max_area_pixels": detector["blob"]["max_area_pixels"],
        "open_iterations": detector["morphology"]["open_iterations"],
        "close_iterations": detector["morphology"]["close_iterations"],
        "morphology_radius_pixels": detector["morphology"][
            "radius_pixels"
        ],
        "connectivity": detector["blob"]["connectivity"],
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
        if float(image_xy[1]) < 120.0
        else "lower"
        if float(image_xy[1]) >= 240.0
        else "middle"
    )
    return f"{horizontal}_{vertical}"


def _marker_failure(
    *,
    role: str,
    colour: str,
    error: MarkerDetectionError,
) -> dict[str, Any]:
    return {
        "marker_role": role,
        "marker_color": colour,
        "status": "rejected",
        "reason": str(error),
    }


def _assert_sha256(value: Any, name: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{name} must be a lowercase SHA-256.")
    return value


def validate_correction_documents(
    documents: Mapping[str, Mapping[str, Any]],
) -> None:
    """Validate fail-closed coverage, binding, and correspondence ordering."""

    required = {
        "source_and_ground_contact_validation.json",
        "homography_correspondences.json",
        "homography_record.json",
        "localization_validation_report.json",
        "provenance_index.json",
        "phase2_status.json",
    }
    if set(documents) != required:
        raise ValueError("Step 2.4 correction document set changed.")
    source = documents["source_and_ground_contact_validation.json"]
    correspondences = documents["homography_correspondences.json"]
    homographies = documents["homography_record.json"]
    localization = documents["localization_validation_report.json"]
    provenance = documents["provenance_index.json"]
    status = documents["phase2_status.json"]
    if (
        source.get("schema_version") != "1.0"
        or correspondences.get("schema_version") != "1.0"
        or homographies.get("schema_version") != "1.0"
        or localization.get("schema_version") != "1.0"
        or provenance.get("schema_version") != "1.0"
        or status.get("schema_version") != "1.0"
    ):
        raise ValueError("Schema version must remain 1.0.")
    if source.get("png_decoder_version") != PNG_DECODER_VERSION:
        raise ValueError("Public PNG decoder binding changed.")
    if source.get("validated_png_count") != 72:
        raise ValueError("Every one of the 72 PNGs must be validated.")
    if len(source.get("ground_contact_pairs", [])) != 36:
        raise ValueError("All 36 visible/background pairs are required.")
    if source.get("ground_contact_method_assessment", {}).get(
        "selected_method_version"
    ) != GROUND_CONTACT_LOCALIZATION_METHOD_VERSION:
        raise ValueError("Ground-contact method binding changed.")
    source_records = source.get("source_png_records", [])
    if len(source_records) != 72:
        raise ValueError("Exactly 72 source PNG records are required.")
    source_by_frame = {}
    for record in source_records:
        frame_id = record.get("frame_id")
        if not isinstance(frame_id, str) or frame_id in source_by_frame:
            raise ValueError("Source PNG frame identities changed.")
        _assert_sha256(record.get("source_frame_hash"), "source_frame_hash")
        _assert_sha256(record.get("decoded_rgb_hash"), "decoded_rgb_hash")
        source_by_frame[frame_id] = record
    pair_by_visible_frame = {}
    for pair in source["ground_contact_pairs"]:
        if (
            pair["visible"]["layout_id"] != pair["background"]["layout_id"]
            or pair["visible"]["split"] != pair["background"]["split"]
            or pair["visible"]["source_frame_idx"]
            != pair["background"]["source_frame_idx"]
            or pair["visible"]["truth_class"] != "visible"
            or pair["background"]["truth_class"] != "negative"
        ):
            raise ValueError("Ground-contact pair identity changed.")
        _assert_sha256(
            pair["visible"]["source_frame_hash"],
            "visible source_frame_hash",
        )
        _assert_sha256(
            pair["background"]["source_frame_hash"],
            "background source_frame_hash",
        )
        for side in ("visible", "background"):
            frame = pair[side]
            source_record = source_by_frame.get(frame["frame_id"])
            if source_record is None or any(
                frame[field] != source_record[field]
                for field in (
                    "source_git_revision",
                    "source_git_path",
                    "source_frame_hash",
                    "decoded_rgb_hash",
                )
            ):
                raise ValueError(
                    "Ground-contact pair source binding changed."
                )
        visible_id = pair["visible"]["frame_id"]
        if visible_id in pair_by_visible_frame:
            raise ValueError("Ground-contact pair identity is duplicated.")
        if pair["selected_ground_contact"].get(
            "localization_method_version"
        ) != GROUND_CONTACT_LOCALIZATION_METHOD_VERSION:
            raise ValueError("Ground-contact pair method binding changed.")
        pair_by_visible_frame[visible_id] = pair
    if correspondences.get("marker_order") != list(MARKER_ORDER):
        raise ValueError("Canonical marker order changed.")
    if correspondences.get("marker_detector_version") != (
        MARKER_DETECTOR_VERSION
    ):
        raise ValueError("Public marker detector binding changed.")
    if correspondences.get("white_marker_gate") != list(EXPECTED_WHITE_GATE):
        raise ValueError("Committed white marker gate changed.")
    corrected = correspondences.get("corrected_layouts")
    blocked = correspondences.get("blocked_layouts")
    if (
        not isinstance(corrected, list)
        or len(corrected) != 5
        or not isinstance(blocked, list)
        or len(blocked) != 1
        or blocked[0].get("layout_id") != EXPECTED_BLOCKED_LAYOUT
    ):
        raise ValueError("Fail-closed layout coverage changed.")
    corrected_ids = []
    correspondence_hashes = {}
    corrected_by_id = {}
    for layout in corrected:
        if layout.get("marker_order") != list(MARKER_ORDER):
            raise ValueError("A layout changed canonical marker ordering.")
        if [marker["marker_role"] for marker in layout["markers"]] != list(
            MARKER_ORDER
        ):
            raise ValueError("Marker rows changed canonical ordering.")
        source = dict(layout)
        claimed = source.pop("correspondence_hash")
        if claimed != hash_json_value(source):
            raise ValueError("A correspondence checksum changed.")
        corrected_ids.append(layout["layout_id"])
        correspondence_hashes[layout["layout_id"]] = claimed
        corrected_by_id[layout["layout_id"]] = layout
        for marker in layout["markers"]:
            _assert_sha256(
                marker.get("source_frame_hash"), "marker source_frame_hash"
            )
            source_record = source_by_frame.get(marker["source_frame_id"])
            if source_record is None or any(
                marker[field] != source_record[field]
                for field in ("source_frame_hash", "decoded_rgb_hash")
            ):
                raise ValueError("Marker source binding changed.")
    if corrected_ids != [
        layout_id
        for layout_id in EXPECTED_LAYOUT_IDS
        if layout_id != EXPECTED_BLOCKED_LAYOUT
    ]:
        raise ValueError("Corrected layout ordering changed.")
    blocked_layout = blocked[0]
    if {
        failure.get("marker_role")
        for failure in blocked_layout.get("marker_failures", [])
    } != {"north_west", "north_east"}:
        raise ValueError("Blocked marker failure identity changed.")
    marker_results = blocked_layout.get("marker_results", [])
    if [result.get("marker_role") for result in marker_results] != list(
        MARKER_ORDER
    ):
        raise ValueError("Blocked marker result ordering changed.")
    expected_status_by_role = {
        "north_west": "rejected",
        "north_east": "rejected",
        "south_east": "accepted",
        "south_west": "accepted",
    }
    for result in marker_results:
        if result.get("status") != expected_status_by_role[
            result["marker_role"]
        ]:
            raise ValueError("Blocked marker result status changed.")
        source_record = source_by_frame.get(result.get("source_frame_id"))
        if (
            source_record is None
            or result.get("source_frame_hash")
            != source_record["source_frame_hash"]
        ):
            raise ValueError("Blocked marker result source binding changed.")
    assessments = blocked_layout.get(
        "declared_negative_frame_assessments", []
    )
    if len(assessments) != 6:
        raise ValueError("Every blocked-layout negative frame is required.")
    for assessment in assessments:
        source_record = source_by_frame.get(assessment.get("frame_id"))
        if (
            source_record is None
            or assessment.get("source_frame_hash")
            != source_record["source_frame_hash"]
            or set(assessment.get("rejected_marker_roles", []))
            != {"north_west", "north_east"}
        ):
            raise ValueError("Blocked-layout source assessment changed.")
    records = homographies.get("records")
    if not isinstance(records, list) or len(records) != 5:
        raise ValueError("Exactly five fail-closed homographies are expected.")
    correspondence_document_hash, _ = _artifact_hash(correspondences)
    if (
        homographies.get("correspondence_document_hash")
        != correspondence_document_hash
    ):
        raise ValueError("Correspondence document binding changed.")
    runtime_identity, runtime_hash = _runtime_identity()
    if (
        homographies.get("software_runtime") != runtime_identity
        or homographies.get("software_runtime_hash") != runtime_hash
        or homographies.get("fitting_method_version")
        != HOMOGRAPHY_ALGORITHM_VERSION
        or homographies.get("png_decoder_version") != PNG_DECODER_VERSION
        or homographies.get("marker_detector_version")
        != MARKER_DETECTOR_VERSION
    ):
        raise ValueError("Homography implementation binding changed.")
    for record in records:
        layout_id = record["layout_id"]
        layout = corrected_by_id[layout_id]
        if record["source_correspondence_hash"] != correspondence_hashes[
            layout_id
        ]:
            raise ValueError("Homography correspondence binding changed.")
        if (
            record["canonical_camera_pose_id"]
            != layout["canonical_camera_pose_id"]
            or
            record["resolution_id"] != RESOLUTION_ID
            or record["image_width_px"] != 640
            or record["image_height_px"] != 360
            or record["detector_version"]
            != homographies["frozen_detector_version"]
            or record["software_runtime_hash"] != runtime_hash
            or record["algorithm_version"] != HOMOGRAPHY_ALGORITHM_VERSION
        ):
            raise ValueError("Homography resolution binding changed.")
    homography_document_hash, _ = _artifact_hash(homographies)
    if (
        localization.get("homography_document_hash")
        != homography_document_hash
        or localization.get("png_decoder_version") != PNG_DECODER_VERSION
        or localization.get("marker_detector_version")
        != MARKER_DETECTOR_VERSION
        or localization.get("ground_contact_localization_method_version")
        != GROUND_CONTACT_LOCALIZATION_METHOD_VERSION
        or
        localization.get("required_sample_count") != 36
        or localization.get("evaluated_sample_count") != 30
        or localization.get("planning_gate_passed") is not False
        or localization.get("all_required_probes_evaluated") is not False
        or localization.get("probe_targets_used_for_fitting") is not False
        or localization.get("probe_targets_used_for_method_selection")
        is not False
    ):
        raise ValueError("Fail-closed probe gate declaration changed.")
    if {
        record["layout_id"] for record in localization.get("records", [])
    } != set(corrected_ids):
        raise ValueError("Localization records include a blocked layout.")
    localization_records = localization["records"]
    if (
        len(localization_records) != 30
        or len({record["frame_id"] for record in localization_records}) != 30
        or sum(
            record["split"] == "calibration"
            for record in localization_records
        )
        != 15
        or sum(
            record["split"] == "heldout" for record in localization_records
        )
        != 15
    ):
        raise ValueError("Independent-probe split coverage changed.")
    for record in localization_records:
        pair = pair_by_visible_frame.get(record["frame_id"])
        if (
            pair is None
            or record["source_frame_hash"]
            != pair["visible"]["source_frame_hash"]
            or record["decoded_rgb_hash"]
            != pair["visible"]["decoded_rgb_hash"]
            or record["paired_background_frame_id"]
            != pair["background"]["frame_id"]
            or record["ground_contact"] != pair["selected_ground_contact"]
        ):
            raise ValueError("Localization source identity binding changed.")
    primary_paths = {
        "source_and_ground_contact_validation.json",
        "homography_correspondences.json",
        "homography_record.json",
        "localization_validation_report.json",
    }
    provenance_records = provenance.get("records", [])
    if {
        record.get("path") for record in provenance_records
    } != primary_paths:
        raise ValueError("Correction provenance coverage changed.")
    for record in provenance_records:
        digest, size = _artifact_hash(documents[record["path"]])
        if record.get("sha256") != digest or record.get(
            "size_bytes"
        ) != size:
            raise ValueError("Correction provenance binding changed.")
    provenance_hash, _ = _artifact_hash(provenance)
    if status.get("provenance_index_hash") != provenance_hash:
        raise ValueError("Phase 2 status provenance binding changed.")
    step = next(
        row for row in status.get("steps", []) if row.get("step") == "2.4"
    )
    if (
        status.get("overall_status") != "PARTIAL"
        or step.get("status") != "PARTIAL"
        or status.get("homography_planning_gate_passed") is not False
    ):
        raise ValueError("Step 2.4 status overclaims completion.")


def build_documents(
    *,
    base_evidence: Path,
    person_c_revision: str,
) -> dict[str, dict[str, Any]]:
    """Build only correction evidence that depends on Step 2.4."""

    split, split_hash = _load_json(
        base_evidence / "frozen_split_manifest.json"
    )
    config, config_hash = _load_json(
        base_evidence / "frozen_detector_config.json"
    )
    detector_record, detector_record_hash = _load_json(
        base_evidence / "detector_version_record.json"
    )
    old_correspondences, old_correspondence_hash = _load_json(
        base_evidence / "homography_correspondences.json"
    )
    _, old_homography_hash = _load_json(
        base_evidence / "homography_record.json"
    )
    old_localization, old_localization_hash = _load_json(
        base_evidence / "localization_validation_report.json"
    )
    old_status, old_status_hash = _load_json(
        base_evidence / "phase2_status.json"
    )
    old_provenance, old_provenance_hash = _load_json(
        base_evidence / "provenance_index.json"
    )
    if split.get("split_version") != detector_record.get("split_version"):
        raise ValueError("Frozen split and detector version no longer agree.")
    if detector_record.get("config_hash") != config_hash:
        raise ValueError("Frozen detector config checksum changed.")
    source, source_payload = _git_json(
        person_c_revision, PERSON_C_INPUT_PATH
    )
    probes, probe_payload = _git_json(person_c_revision, PERSON_C_PROBE_PATH)
    if len(source.get("frames", [])) != 72:
        raise ValueError("Person C source must contain exactly 72 frames.")
    if len(probes.get("points", [])) != 36:
        raise ValueError("Person C source must contain exactly 36 probes.")

    runtime_identity, runtime_hash = _runtime_identity()
    frozen_frames = {
        frame["frame_id"]: frame for frame in split["frames"]
    }
    source_frames = {
        frame["frame_id"]: frame for frame in source["frames"]
    }
    if set(frozen_frames) != set(source_frames):
        raise ValueError("Frozen/source frame identities changed.")
    rgb_by_frame: dict[str, list[list[list[int]]]] = {}
    source_png_records = []
    for frame_id in sorted(frozen_frames):
        frozen = frozen_frames[frame_id]
        source_frame = source_frames[frame_id]
        payload = _git_blob(
            frozen["source_git_revision"], frozen["source_git_path"]
        )
        source_hash = _sha256(payload)
        if (
            source_hash != frozen["source_frame_hash"]
            or source_hash != source_frame["source_frame_hash"]
        ):
            raise ValueError(f"{frame_id} source PNG checksum changed.")
        rgb = decode_png_rgb(payload)
        if len(rgb) != 360 or len(rgb[0]) != 640:
            raise ValueError(f"{frame_id} resolution changed.")
        decoded_hash = hash_json_value(rgb)
        if decoded_hash != frozen["decoded_rgb_hash"]:
            raise ValueError(f"{frame_id} decoded RGB checksum changed.")
        rgb_by_frame[frame_id] = rgb
        source_png_records.append(
            {
                "frame_id": frame_id,
                "source_git_revision": frozen["source_git_revision"],
                "source_git_path": frozen["source_git_path"],
                "source_frame_hash": source_hash,
                "decoded_rgb_hash": decoded_hash,
                "image_width_px": 640,
                "image_height_px": 360,
                "pixel_format": "rgb8",
            }
        )

    detector_kwargs = _detector_kwargs(config)
    ground_contact_pairs = []
    ground_contact_by_visible_id = {}
    magenta_vertical_gaps = []
    for visible in sorted(
        (
            frame
            for frame in split["frames"]
            if frame["truth_class"] == "visible"
        ),
        key=lambda item: item["frame_id"],
    ):
        background_id = visible["paired_background_frame_id"]
        background = frozen_frames[background_id]
        if (
            background["layout_id"] != visible["layout_id"]
            or background["split"] != visible["split"]
            or background["source_frame_idx"]
            != visible["source_frame_idx"]
            or background["truth_class"] != "negative"
        ):
            raise ValueError(
                f"{visible['frame_id']} background identity changed."
            )
        ground_contact = localize_ground_contact_from_background_pair(
            rgb_by_frame[visible["frame_id"]],
            rgb_by_frame[background_id],
        )
        visible_detection = detect_magenta(
            rgb_by_frame[visible["frame_id"]], **detector_kwargs
        )
        background_detection = detect_magenta(
            rgb_by_frame[background_id], **detector_kwargs
        )
        if not visible_detection.detected:
            raise ValueError(
                f"{visible['frame_id']} frozen detector no longer detects."
            )
        if background_detection.detected:
            raise ValueError(
                f"{background_id} unexpectedly contains a magenta detection."
            )
        bbox = visible_detection.bounding_box_xyxy
        if bbox is None:
            raise ValueError("Detected magenta blob requires a bounding box.")
        magenta_base = [
            (bbox[0] + bbox[2] - 1) / 2.0,
            float(bbox[3] - 1),
        ]
        vertical_gap = ground_contact["image_xy"][1] - magenta_base[1]
        if vertical_gap <= 0.0:
            raise ValueError("Magenta blob does not sit above silhouette base.")
        magenta_vertical_gaps.append(vertical_gap)
        ground_contact_by_visible_id[visible["frame_id"]] = ground_contact
        ground_contact_pairs.append(
            {
                "visible": {
                    key: visible[key]
                    for key in (
                        "frame_id",
                        "layout_id",
                        "split",
                        "truth_class",
                        "source_artifact_id",
                        "source_frame_idx",
                        "source_frame_hash",
                        "decoded_rgb_hash",
                        "source_git_revision",
                        "source_git_path",
                    )
                },
                "background": {
                    key: background[key]
                    for key in (
                        "frame_id",
                        "layout_id",
                        "split",
                        "truth_class",
                        "source_artifact_id",
                        "source_frame_idx",
                        "source_frame_hash",
                        "decoded_rgb_hash",
                        "source_git_revision",
                        "source_git_path",
                    )
                },
                "selected_ground_contact": ground_contact,
                "visible_magenta_detection": visible_detection.to_record(),
                "background_magenta_detection": (
                    background_detection.to_record()
                ),
                "discarded_magenta_blob_base_xy": magenta_base,
                "magenta_base_to_silhouette_base_vertical_gap_px": (
                    vertical_gap
                ),
            }
        )

    source_and_ground = {
        "schema_version": "1.0",
        "correction_schema_version": CORRECTION_SCHEMA_VERSION,
        "source_validation_schema_version": (
            "person-e-step2.4-source-ground-validation-v0.2"
        ),
        "source_revision": person_c_revision,
        "source_document_path": PERSON_C_INPUT_PATH,
        "source_document_hash": _sha256(source_payload),
        "frozen_split_path": (
            "../person_e_phase2_v0_1/frozen_split_manifest.json"
        ),
        "frozen_split_hash": split_hash,
        "frozen_split_version": split["split_version"],
        "frozen_detector_config_path": (
            "../person_e_phase2_v0_1/frozen_detector_config.json"
        ),
        "frozen_detector_config_hash": config_hash,
        "frozen_detector_version": detector_record["detector_version"],
        "png_decoder_version": PNG_DECODER_VERSION,
        "validated_png_count": len(source_png_records),
        "source_png_records": source_png_records,
        "ground_contact_method_assessment": {
            "selected_method_version": (
                GROUND_CONTACT_LOCALIZATION_METHOD_VERSION
            ),
            "selection_basis": (
                "paired visible/background silhouette base preserves the "
                "rendered lower sheep/foot pixels and is selected without "
                "probe world coordinates"
            ),
            "discarded_method": "frozen_magenta_blob_bottom_center",
            "discarded_reason": (
                "the magenta blob excludes lower non-magenta rendered "
                "sheep/foot pixels and terminates above the paired silhouette"
            ),
            "minimum_vertical_gap_px": min(magenta_vertical_gaps),
            "maximum_vertical_gap_px": max(magenta_vertical_gaps),
            "probe_targets_used_for_method_selection": False,
        },
        "ground_contact_pair_count": len(ground_contact_pairs),
        "ground_contact_pairs": ground_contact_pairs,
    }

    old_layouts = {
        layout["layout_id"]: layout
        for layout in old_correspondences["layouts"]
    }
    split_layouts = {
        layout["layout_id"]: layout for layout in split["layouts"]
    }
    corrected_layouts = []
    blocked_layouts = []
    homography_records = []
    homography_by_layout = {}
    for layout_id in EXPECTED_LAYOUT_IDS:
        layout = split_layouts[layout_id]
        marker_source_id = f"{layout_id}_negative_000"
        marker_source = frozen_frames[marker_source_id]
        marker_by_role = {
            marker["marker_role"]: marker for marker in layout["markers"]
        }
        old_marker_by_role = {
            marker["marker_role"]: marker
            for marker in old_layouts[layout_id]["markers"]
        }
        detected = {}
        failures = []
        for role in MARKER_ORDER:
            colour = MARKER_COLOURS[role]
            try:
                detected[role] = detect_marker_point(
                    rgb_by_frame[marker_source_id], colour
                )
            except MarkerDetectionError as error:
                failures.append(
                    _marker_failure(
                        role=role,
                        colour=colour,
                        error=error,
                    )
                )
        if failures:
            failure_by_role = {
                failure["marker_role"]: failure for failure in failures
            }
            marker_results = []
            for role in MARKER_ORDER:
                result = {
                    "marker_role": role,
                    "marker_color": MARKER_COLOURS[role],
                    "source_frame_id": marker_source_id,
                    "source_frame_hash": marker_source[
                        "source_frame_hash"
                    ],
                    "old_image_xy": old_marker_by_role[role]["image_xy"],
                }
                if role in detected:
                    detail = detected[role]
                    result.update(
                        {
                            "status": "accepted",
                            "image_xy": detail["image_xy"],
                            "delta_xy_px": [
                                detail["image_xy"][0]
                                - old_marker_by_role[role]["image_xy"][0],
                                detail["image_xy"][1]
                                - old_marker_by_role[role]["image_xy"][1],
                            ],
                            "detector_diagnostics": detail,
                        }
                    )
                else:
                    result.update(
                        {
                            "status": "rejected",
                            "reason": failure_by_role[role]["reason"],
                        }
                    )
                marker_results.append(result)
            negative_frame_assessments = []
            for negative in sorted(
                (
                    frame
                    for frame in split["frames"]
                    if frame["layout_id"] == layout_id
                    and frame["truth_class"] == "negative"
                ),
                key=lambda frame: frame["frame_id"],
            ):
                rejected_roles = []
                for role in MARKER_ORDER:
                    try:
                        detect_marker_point(
                            rgb_by_frame[negative["frame_id"]],
                            MARKER_COLOURS[role],
                        )
                    except MarkerDetectionError:
                        rejected_roles.append(role)
                negative_frame_assessments.append(
                    {
                        "frame_id": negative["frame_id"],
                        "source_frame_hash": negative[
                            "source_frame_hash"
                        ],
                        "rejected_marker_roles": rejected_roles,
                    }
                )
            blocked_layouts.append(
                {
                    "layout_id": layout_id,
                    "canonical_camera_pose_id": layout[
                        "canonical_camera_pose_id"
                    ],
                    "resolution_id": RESOLUTION_ID,
                    "source_frame_id": marker_source_id,
                    "source_frame_hash": marker_source[
                        "source_frame_hash"
                    ],
                    "status": "BLOCKED",
                    "reason": (
                        "public marker detector rejected clipped source "
                        "correspondences"
                    ),
                    "marker_failures": failures,
                    "marker_results": marker_results,
                    "declared_negative_frame_assessments": (
                        negative_frame_assessments
                    ),
                    "old_marker_coordinates": [
                        {
                            "marker_role": role,
                            "marker_color": MARKER_COLOURS[role],
                            "image_xy": old_marker_by_role[role]["image_xy"],
                        }
                        for role in MARKER_ORDER
                    ],
                }
            )
            continue
        markers = []
        image_points = {}
        world_points = {}
        for role in MARKER_ORDER:
            detail = detected[role]
            new_xy = detail["image_xy"]
            old_xy = old_marker_by_role[role]["image_xy"]
            world_xy = marker_by_role[role]["world_xz_blocks"]
            markers.append(
                {
                    "marker_role": role,
                    "marker_color": MARKER_COLOURS[role],
                    "source_frame_id": marker_source_id,
                    "source_frame_hash": marker_source[
                        "source_frame_hash"
                    ],
                    "decoded_rgb_hash": marker_source[
                        "decoded_rgb_hash"
                    ],
                    "image_xy": new_xy,
                    "old_image_xy": old_xy,
                    "delta_xy_px": [
                        new_xy[0] - old_xy[0],
                        new_xy[1] - old_xy[1],
                    ],
                    "delta_euclidean_px": math.hypot(
                        new_xy[0] - old_xy[0],
                        new_xy[1] - old_xy[1],
                    ),
                    "world_xz_blocks": world_xy,
                    "coordinate_source_hash": marker_by_role[role][
                        "coordinate_source_hash"
                    ],
                    "detector_diagnostics": detail,
                }
            )
            image_points[role] = new_xy
            world_points[role] = world_xy
        correspondence = {
            "layout_id": layout_id,
            "canonical_camera_pose_id": layout[
                "canonical_camera_pose_id"
            ],
            "resolution_id": RESOLUTION_ID,
            "image_width_px": 640,
            "image_height_px": 360,
            "image_coordinate_system": "pixel_center_xy_zero_based",
            "image_axes": {"x": "right", "y": "down"},
            "world_coordinate_system": "ground_plane_world_xz_blocks",
            "world_unit": "blocks",
            "marker_order": list(MARKER_ORDER),
            "marker_detector_version": MARKER_DETECTOR_VERSION,
            "png_decoder_version": PNG_DECODER_VERSION,
            "source_frame_id": marker_source_id,
            "source_frame_hash": marker_source["source_frame_hash"],
            "markers": markers,
        }
        correspondence_hash = hash_json_value(correspondence)
        correspondence["correspondence_hash"] = correspondence_hash
        corrected_layouts.append(correspondence)
        homography = fit_marker_homography(
            image_points,
            world_points,
            marker_ids=MARKER_ORDER,
            layout_id=layout_id,
            canonical_camera_pose_id=layout[
                "canonical_camera_pose_id"
            ],
            resolution_id=RESOLUTION_ID,
            image_width_px=640,
            image_height_px=360,
            source_correspondence_hash=correspondence_hash,
            detector_version=detector_record["detector_version"],
            software_runtime_hash=runtime_hash,
        )
        homography_by_layout[layout_id] = homography
        homography_records.append(homography.to_record())

    correspondences = {
        "schema_version": "1.0",
        "correction_schema_version": CORRECTION_SCHEMA_VERSION,
        "homography_correspondence_schema_version": (
            "person-e-real-homography-correspondences-v0.2"
        ),
        "source_revision": person_c_revision,
        "source_document_hash": _sha256(source_payload),
        "frozen_split_version": split["split_version"],
        "frozen_detector_version": detector_record["detector_version"],
        "png_decoder_version": PNG_DECODER_VERSION,
        "marker_detector_version": MARKER_DETECTOR_VERSION,
        "white_marker_gate": list(MARKER_COLOUR_GATES["white"]),
        "white_marker_gate_decision": "PE-P2-002",
        "marker_order": list(MARKER_ORDER),
        "old_correspondence_evidence": {
            "path": (
                "../person_e_phase2_v0_1/"
                "homography_correspondences.json"
            ),
            "sha256": old_correspondence_hash,
            "status": "superseded_for_step2_4_correction_not_deleted",
        },
        "corrected_layout_count": len(corrected_layouts),
        "blocked_layout_count": len(blocked_layouts),
        "corrected_layouts": corrected_layouts,
        "blocked_layouts": blocked_layouts,
    }
    correspondence_hash, _ = _artifact_hash(correspondences)
    homographies = {
        "schema_version": "1.0",
        "correction_schema_version": CORRECTION_SCHEMA_VERSION,
        "homography_record_schema_version": (
            "person-e-bound-homography-records-v0.2"
        ),
        "correspondence_document_hash": correspondence_hash,
        "frozen_detector_version": detector_record["detector_version"],
        "png_decoder_version": PNG_DECODER_VERSION,
        "marker_detector_version": MARKER_DETECTOR_VERSION,
        "software_runtime": runtime_identity,
        "software_runtime_hash": runtime_hash,
        "fitting_method_version": HOMOGRAPHY_ALGORITHM_VERSION,
        "corrected_layout_count": len(homography_records),
        "blocked_layout_ids": [
            layout["layout_id"] for layout in blocked_layouts
        ],
        "old_homography_evidence": {
            "path": "../person_e_phase2_v0_1/homography_record.json",
            "sha256": old_homography_hash,
            "status": "superseded_for_step2_4_correction_not_deleted",
        },
        "records": homography_records,
    }
    homography_hash, _ = _artifact_hash(homographies)

    probes_by_layout: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for probe in probes["points"]:
        probes_by_layout[probe["layout_id"]].append(probe)
    localization_records = []
    per_layout = []
    for layout_id in sorted(homography_by_layout):
        layout = split_layouts[layout_id]
        marker_by_role = {
            marker["marker_role"]: marker for marker in layout["markers"]
        }
        north_west = marker_by_role["north_west"]["world_xz_blocks"]
        north_east = marker_by_role["north_east"]["world_xz_blocks"]
        direction = [
            north_east[0] - north_west[0],
            north_east[1] - north_west[1],
        ]
        norm = math.hypot(*direction)
        wall_unit = [direction[0] / norm, direction[1] / norm]
        layout_probes = sorted(
            probes_by_layout[layout_id],
            key=lambda item: item["frame_id"],
        )
        pairs = []
        regions = []
        sources = []
        for probe in layout_probes:
            frozen = frozen_frames[probe["frame_id"]]
            if (
                frozen["layout_id"] != probe["layout_id"]
                or frozen["split"] != probe["split"]
                or frozen["source_artifact_id"]
                != probe["source_artifact_id"]
                or frozen["source_frame_idx"] != probe["source_frame_idx"]
            ):
                raise ValueError(
                    f"{probe['frame_id']} validation identity changed."
                )
            contact = ground_contact_by_visible_id[probe["frame_id"]]
            pairs.append(
                (contact["image_xy"], probe["probe_point_world_xz_blocks"])
            )
            regions.append(_image_region(contact["image_xy"]))
            sources.append(
                {
                    "frame_id": probe["frame_id"],
                    "layout_id": layout_id,
                    "split": probe["split"],
                    "source_artifact_id": probe["source_artifact_id"],
                    "source_frame_idx": probe["source_frame_idx"],
                    "source_frame_hash": frozen["source_frame_hash"],
                    "decoded_rgb_hash": frozen["decoded_rgb_hash"],
                    "paired_background_frame_id": frozen[
                        "paired_background_frame_id"
                    ],
                    "ground_contact": contact,
                    "true_world_xz_blocks": probe[
                        "probe_point_world_xz_blocks"
                    ],
                    "world_y_blocks": probe[
                        "probe_point_world_y_blocks"
                    ],
                }
            )
        summary = summarize_localization(
            homography_by_layout[layout_id],
            pairs,
            wall_parallel_origin_xz=north_west,
            wall_parallel_positive_unit_xz=wall_unit,
            image_regions=regions,
        )
        for record, source_record in zip(
            summary["records"], sources, strict=True
        ):
            record.update(source_record)
            record["canonical_camera_pose_id"] = layout[
                "canonical_camera_pose_id"
            ]
        localization_records.extend(summary["records"])
        per_layout.append(
            {
                "layout_id": layout_id,
                "canonical_camera_pose_id": layout[
                    "canonical_camera_pose_id"
                ],
                "homography_version_id": homography_by_layout[
                    layout_id
                ].to_record()["homography_version_id"],
                "wall_parallel_origin_xz": north_west,
                "wall_parallel_positive_unit_xz": wall_unit,
                "summary": _metric_summary(summary["records"]),
            }
        )

    new_summary = _metric_summary(localization_records)
    corrected_ids = set(homography_by_layout)
    old_same_layout_records = [
        record
        for record in old_localization["records"]
        if record["layout_id"] in corrected_ids
    ]
    old_same_layout_summary = _metric_summary(old_same_layout_records)
    old_all_summary = _metric_summary(old_localization["records"])
    region_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in localization_records:
        region_groups[record["image_region"]].append(record)
    subset_gate_passed = (
        new_summary["median_absolute_wall_parallel_error_blocks"] <= 0.2
        and new_summary["p95_absolute_wall_parallel_error_blocks"] < 0.5
    )
    localization = {
        "schema_version": "1.0",
        "correction_schema_version": CORRECTION_SCHEMA_VERSION,
        "localization_report_schema_version": (
            "person-e-real-localization-report-v0.2"
        ),
        "source_probe_revision": person_c_revision,
        "source_probe_document_path": PERSON_C_PROBE_PATH,
        "source_probe_document_hash": _sha256(probe_payload),
        "homography_document_hash": homography_hash,
        "frozen_detector_version": detector_record["detector_version"],
        "png_decoder_version": PNG_DECODER_VERSION,
        "marker_detector_version": MARKER_DETECTOR_VERSION,
        "ground_contact_localization_method_version": (
            GROUND_CONTACT_LOCALIZATION_METHOD_VERSION
        ),
        "probe_targets_used_for_fitting": False,
        "probe_targets_used_for_method_selection": False,
        "required_sample_count": 36,
        "evaluated_sample_count": len(localization_records),
        "blocked_sample_count": 36 - len(localization_records),
        "blocked_layout_ids": [
            layout["layout_id"] for layout in blocked_layouts
        ],
        "all_required_probes_evaluated": False,
        "required_gate": {
            "maximum_median_absolute_wall_parallel_error_blocks": 0.2,
            "maximum_p95_absolute_wall_parallel_error_blocks_exclusive": 0.5,
        },
        "evaluated_subset_gate_passed": subset_gate_passed,
        "planning_gate_passed": False,
        "gate_decision": (
            "not_passed_incomplete_layout_coverage_and_evaluated_subset_failed"
        ),
        **new_summary,
        "per_layout": per_layout,
        "by_image_region": [
            {
                "image_region": region,
                **_metric_summary(records),
            }
            for region, records in sorted(region_groups.items())
        ],
        "worst_cases": sorted(
            (
                {
                    "frame_id": record["frame_id"],
                    "layout_id": record["layout_id"],
                    "image_region": record["image_region"],
                    "signed_wall_parallel_error_blocks": record[
                        "signed_wall_parallel_error_blocks"
                    ],
                    "absolute_wall_parallel_error_blocks": abs(
                        record["signed_wall_parallel_error_blocks"]
                    ),
                    "euclidean_error_blocks": record[
                        "euclidean_error_blocks"
                    ],
                }
                for record in localization_records
            ),
            key=lambda record: (
                -record["absolute_wall_parallel_error_blocks"],
                record["frame_id"],
            ),
        )[:5],
        "old_versus_corrected": {
            "old_all_36": old_all_summary,
            "old_same_five_layouts": old_same_layout_summary,
            "corrected_same_five_layouts": new_summary,
            "median_absolute_wall_parallel_delta_blocks": (
                new_summary[
                    "median_absolute_wall_parallel_error_blocks"
                ]
                - old_same_layout_summary[
                    "median_absolute_wall_parallel_error_blocks"
                ]
            ),
            "p95_absolute_wall_parallel_delta_blocks": (
                new_summary[
                    "p95_absolute_wall_parallel_error_blocks"
                ]
                - old_same_layout_summary[
                    "p95_absolute_wall_parallel_error_blocks"
                ]
            ),
            "old_evidence": {
                "path": (
                    "../person_e_phase2_v0_1/"
                    "localization_validation_report.json"
                ),
                "sha256": old_localization_hash,
                "status": "retained_failed_baseline",
            },
        },
        "remaining_blockers": [
            {
                "blocker_id": "layout_02_clipped_near_markers",
                "kind": "source_evidence",
                "detail": (
                    "layout_02 blue and yellow marker blobs touch the image "
                    "border in every declared no-sheep frame; a recapture or "
                    "authoritative exclusion ruling is required"
                ),
            },
            {
                "blocker_id": "five_layout_error_gate_still_failed",
                "kind": "method_or_capture_geometry",
                "detail": (
                    "public sub-pixel markers plus the probe-independent "
                    "paired-silhouette ground contact still exceed the wall "
                    "error gate on the 30 evaluable probes; changing pixels "
                    "further would require an independent method or new "
                    "capture geometry rather than probe tuning"
                ),
            },
        ],
        "records": localization_records,
    }

    primary_documents = {
        "source_and_ground_contact_validation.json": source_and_ground,
        "homography_correspondences.json": correspondences,
        "homography_record.json": homographies,
        "localization_validation_report.json": localization,
    }
    direct_inputs = {
        "source_and_ground_contact_validation.json": [
            "../person_e_phase2_v0_1/frozen_split_manifest.json",
            "../person_e_phase2_v0_1/frozen_detector_config.json",
            f"git:{person_c_revision}:{PERSON_C_INPUT_PATH}",
        ],
        "homography_correspondences.json": [
            "source_and_ground_contact_validation.json",
            "../person_e_phase2_v0_1/homography_correspondences.json",
        ],
        "homography_record.json": [
            "homography_correspondences.json",
            "../person_e_phase2_v0_1/detector_version_record.json",
        ],
        "localization_validation_report.json": [
            "source_and_ground_contact_validation.json",
            "homography_record.json",
            f"git:{person_c_revision}:{PERSON_C_PROBE_PATH}",
            (
                "../person_e_phase2_v0_1/"
                "localization_validation_report.json"
            ),
        ],
    }
    provenance_records = []
    for path, document in sorted(primary_documents.items()):
        digest, size = _artifact_hash(document)
        provenance_records.append(
            {
                "artifact_id": f"person_e_phase2_step2_4_v0_2:{path}",
                "path": path,
                "sha256": digest,
                "size_bytes": size,
                "direct_inputs": direct_inputs[path],
                "status": "accepted_correction_evidence",
                "shared_immutable_registry_emitted": False,
            }
        )
    provenance = {
        "schema_version": "1.0",
        "correction_schema_version": CORRECTION_SCHEMA_VERSION,
        "provenance_index_schema_version": (
            "person-e-phase2-step2.4-provenance-index-v0.2"
        ),
        "source_revisions": {
            "person_c": person_c_revision,
            "person_e_base": PERSON_E_BASE_SHA,
        },
        "unchanged_upstream_evidence": {
            "frozen_split_manifest_hash": split_hash,
            "frozen_detector_config_hash": config_hash,
            "detector_version_record_hash": detector_record_hash,
        },
        "superseded_step2_4_evidence_retained": {
            "homography_correspondences_hash": old_correspondence_hash,
            "homography_record_hash": old_homography_hash,
            "localization_validation_report_hash": old_localization_hash,
        },
        "previous_phase2_records": {
            "status_hash": old_status_hash,
            "provenance_hash": old_provenance_hash,
            "shared_immutable_registry_status": old_provenance[
                "shared_immutable_registry_status"
            ],
        },
        "shared_immutable_registry_status": old_provenance[
            "shared_immutable_registry_status"
        ],
        "records": provenance_records,
    }
    provenance_hash, _ = _artifact_hash(provenance)
    status = copy.deepcopy(old_status)
    status.update(
        {
            "correction_schema_version": CORRECTION_SCHEMA_VERSION,
            "status_schema_version": "person-e-phase2-status-v0.2",
            "overall_status": "PARTIAL",
            "previous_status": {
                "path": "../person_e_phase2_v0_1/phase2_status.json",
                "sha256": old_status_hash,
                "status": "retained_not_overwritten",
            },
            "provenance_index_hash": provenance_hash,
            "homography_planning_gate_passed": False,
        }
    )
    for step in status["steps"]:
        if step["step"] == "2.4":
            step.update(
                {
                    "status": "PARTIAL",
                    "evidence": "localization_validation_report.json",
                    "remaining_blocker": (
                        "layout_02_clipped_markers_and_"
                        "five_layout_measured_gate_failure"
                    ),
                }
            )
    documents = {
        **primary_documents,
        "provenance_index.json": provenance,
        "phase2_status.json": status,
    }
    validate_correction_documents(documents)
    return documents


def main() -> None:
    args = parse_args()
    documents = build_documents(
        base_evidence=args.base_evidence,
        person_c_revision=args.person_c_revision,
    )
    for relative_path, document in sorted(documents.items()):
        write_json_exclusive(args.output_dir / relative_path, document)


if __name__ == "__main__":
    main()
