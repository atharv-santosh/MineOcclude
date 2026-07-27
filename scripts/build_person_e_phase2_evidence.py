"""Build the bounded, provenance-preserving Person E Phase 2 evidence batch."""

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
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mineocclude.experiments.registry import (
    PHASE2_STEP2_1_BLOCKER_SCHEMA_VERSION,
    formatted_json_bytes,
    hash_json_value,
    validate_phase2_step2_1_blocker_record,
    write_json_exclusive,
)
from mineocclude.vision.calibration import (
    FROZEN_DETECTOR_CALIBRATION_SCHEMA_VERSION,
    PNG_DECODER_VERSION,
    decode_png_rgb_bytes,
    validate_detector_calibration_dataset,
)
from mineocclude.vision.config import (
    PERSON_E_CONFIG_SCHEMA_VERSION,
    PHASE2_CALIBRATED_STATUS,
    validate_person_e_config,
)
from mineocclude.vision.homography import (
    GROUND_CONTACT_LOCALIZATION_METHOD_VERSION,
    HOMOGRAPHY_ALGORITHM_VERSION,
    MARKER_LOCALIZATION_METHOD_VERSION,
    fit_marker_homography,
    localize_ground_contact_from_background_pair,
    localize_marker_top_face,
    summarize_localization,
)
from mineocclude.vision.magenta import (
    CALIBRATION_DETECTION_DOCUMENT_SCHEMA_VERSION,
    DETECTOR_ALGORITHM_VERSION,
    HsvRange,
    detect_magenta,
    evaluate_presence,
    validate_detection_document,
)


PERSON_E_BASE_SHA = "24e4556fa03b25fd7256474593b518bdf03cdbe2"
PERSON_C_REVISION = "00784756f21895d19aff44572496c956cc5d932f"
PERSON_B_REVISION = "03a2c4663ce73873b4fed0369943c1f43edcd742"
PERSON_C_INPUT_PATH = "data/handoff_e/detector_calibration_inputs.json"
PERSON_C_PROVENANCE_PATH = "data/handoff_e/provenance_calibration_clean.json"
PERSON_C_PROBE_PATH = "data/handoff_e/independent_probe_points.json"
EVIDENCE_SCHEMA_VERSION = "person-e-phase2-evidence-v0.1"
RESOLUTION_ID = "resolution_640x360_rgb8"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Materialize the real C split, calibration-only detector, and "
            "measured homography evidence without using held-out detector "
            "outcomes for parameter selection."
        )
    )
    parser.add_argument("output_dir", type=Path)
    parser.add_argument(
        "--config-template",
        type=Path,
        default=ROOT / "configs" / "vision" / "person_e_phase1.yaml",
    )
    parser.add_argument("--person-c-revision", default=PERSON_C_REVISION)
    parser.add_argument("--person-b-revision", default=PERSON_B_REVISION)
    return parser.parse_args()


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


def _json_blob(revision: str, path: str) -> tuple[dict[str, Any], bytes]:
    payload = _git_blob(revision, path)
    try:
        document = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"Invalid committed JSON {revision}:{path}: {error}") from error
    if not isinstance(document, dict):
        raise TypeError(f"Committed JSON {revision}:{path} must be a mapping.")
    return document, payload


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _artifact_hash(document: Mapping[str, Any]) -> tuple[str, int]:
    payload = formatted_json_bytes(document)
    return _sha256(payload), len(payload)


def _runtime_identity() -> tuple[dict[str, Any], str]:
    source_paths = (
        "src/mineocclude/vision/calibration.py",
        "src/mineocclude/vision/magenta.py",
        "src/mineocclude/vision/homography.py",
        "scripts/build_person_e_phase2_evidence.py",
    )
    identity = {
        "python_implementation": platform.python_implementation(),
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "implementation_base_sha": PERSON_E_BASE_SHA,
        "source_file_sha256": {
            path: _sha256((ROOT / path).read_bytes()) for path in source_paths
        },
        "png_decoder_version": PNG_DECODER_VERSION,
        "detector_algorithm_version": DETECTOR_ALGORITHM_VERSION,
        "marker_localization_method_version": (
            MARKER_LOCALIZATION_METHOD_VERSION
        ),
        "ground_contact_localization_method_version": (
            GROUND_CONTACT_LOCALIZATION_METHOD_VERSION
        ),
        "homography_algorithm_version": HOMOGRAPHY_ALGORITHM_VERSION,
    }
    return identity, hash_json_value(identity)


def _image_region(image_xy: Sequence[float], width: int, height: int) -> str:
    horizontal = (
        "left"
        if float(image_xy[0]) < width / 3.0
        else "right"
        if float(image_xy[0]) >= 2.0 * width / 3.0
        else "center"
    )
    vertical = (
        "upper"
        if float(image_xy[1]) < height / 3.0
        else "lower"
        if float(image_xy[1]) >= 2.0 * height / 3.0
        else "middle"
    )
    return f"{horizontal}_{vertical}"


def _percentile(values: Sequence[float], probability: float) -> float:
    ordered = sorted(float(value) for value in values)
    position = (len(ordered) - 1) * probability
    low = math.floor(position)
    high = math.ceil(position)
    if low == high:
        return ordered[low]
    weight = position - low
    return ordered[low] * (1.0 - weight) + ordered[high] * weight


def _step2_1_blocker_record() -> dict[str, Any]:
    document = {
        "schema_version": "1.0",
        "blocker_schema_version": PHASE2_STEP2_1_BLOCKER_SCHEMA_VERSION,
        "record_id": "person_e_phase2_step2_1_blockers_v0_1",
        "step": "2.1",
        "status": "BLOCKED",
        "pass_claimed": False,
        "real_completed_records_emitted": False,
        "located_committed_metadata": {"person_a": True, "person_c": True},
        "source_revisions": {
            "person_a_execution_revision": (
                "35baf673312af5c21ae3f22168de405bd4ee8bd9"
            ),
            "person_a_evidence_revision": (
                "e5032cc00dd83716df6f8e1b863659477adddb95"
            ),
            "person_c_pilot_revision": (
                "82ef1212091b3f32eac02d7eabe25d55376086f2"
            ),
        },
        "missing_authoritative_fields": [
            {
                "authority": "person_a",
                "record_id": (
                    "person-a-phase2-aws-20260725-055616-step2.6"
                ),
                "fields": ["started_at", "ended_at"],
            },
            {
                "authority": "person_c",
                "record_id": "layout_00_ep9410",
                "fields": ["started_at", "ended_at"],
            },
            {
                "authority": "person_a",
                "record_id": (
                    "person-a-phase2-aws-20260725-055616-step2.6"
                ),
                "fields": ["external_artifact_byte_verification_authority"],
            },
            {
                "authority": "person_a",
                "record_id": "failed_attempts",
                "fields": ["authoritative_failed_attempt_registry_metadata"],
            },
        ],
        "non_inference": {
            "timestamps_inferred": False,
            "external_byte_authority_inferred": False,
            "failed_attempts_manufactured": False,
        },
        "decision": "blocked_not_failed",
    }
    validate_phase2_step2_1_blocker_record(document)
    return document


def _candidate_settings() -> list[dict[str, Any]]:
    return [
        {
            "candidate_id": "candidate_00_primary",
            "hsv_ranges": [[280.0, 320.0, 0.5, 1.0, 0.35, 1.0]],
            "min_area_pixels": 20,
            "max_area_pixels": 5000,
            "open_iterations": 0,
            "close_iterations": 0,
            "morphology_radius_pixels": 1,
            "connectivity": 8,
        },
        {
            "candidate_id": "candidate_01_broad",
            "hsv_ranges": [[275.0, 325.0, 0.4, 1.0, 0.25, 1.0]],
            "min_area_pixels": 20,
            "max_area_pixels": 5000,
            "open_iterations": 0,
            "close_iterations": 0,
            "morphology_radius_pixels": 1,
            "connectivity": 8,
        },
        {
            "candidate_id": "candidate_02_narrow",
            "hsv_ranges": [[285.0, 315.0, 0.55, 1.0, 0.4, 1.0]],
            "min_area_pixels": 20,
            "max_area_pixels": 5000,
            "open_iterations": 0,
            "close_iterations": 0,
            "morphology_radius_pixels": 1,
            "connectivity": 8,
        },
    ]


def _detect(
    rgb: Sequence[Sequence[Sequence[float]]],
    settings: Mapping[str, Any],
):
    return detect_magenta(
        rgb,
        hsv_ranges=[HsvRange(*values) for values in settings["hsv_ranges"]],
        min_area_pixels=settings["min_area_pixels"],
        max_area_pixels=settings["max_area_pixels"],
        open_iterations=settings["open_iterations"],
        close_iterations=settings["close_iterations"],
        morphology_radius_pixels=settings["morphology_radius_pixels"],
        connectivity=settings["connectivity"],
    )


def _metrics(results: Sequence[tuple[bool, Any]]) -> dict[str, Any]:
    metrics = evaluate_presence(results)
    return {
        "true_positive": metrics.true_positive,
        "false_positive": metrics.false_positive,
        "true_negative": metrics.true_negative,
        "false_negative": metrics.false_negative,
        "precision": metrics.precision,
        "recall": metrics.recall,
    }


def _build_documents(
    *,
    config_template: Path,
    person_c_revision: str,
    person_b_revision: str,
) -> dict[str, dict[str, Any]]:
    source, source_payload = _json_blob(person_c_revision, PERSON_C_INPUT_PATH)
    provenance, provenance_payload = _json_blob(
        person_c_revision, PERSON_C_PROVENANCE_PATH
    )
    probes, probe_payload = _json_blob(person_c_revision, PERSON_C_PROBE_PATH)
    if len(source.get("frames", [])) != 72 or len(source.get("layouts", [])) != 6:
        raise ValueError("Person C calibration input count changed.")
    if len(provenance.get("trajectories", [])) != 12:
        raise ValueError("Person C clean-capture provenance count changed.")
    if len(probes.get("points", [])) != 36:
        raise ValueError("Person C independent-probe count changed.")

    runtime_identity, runtime_hash = _runtime_identity()
    rgb_by_frame: dict[str, list[list[list[int]]]] = {}
    input_frame_by_id = {frame["frame_id"]: frame for frame in source["frames"]}
    for frame in source["frames"]:
        payload = _git_blob(person_c_revision, frame["png_path"])
        if _sha256(payload) != frame["source_frame_hash"]:
            raise ValueError(f"{frame['frame_id']} source_frame_hash changed.")
        rgb = decode_png_rgb_bytes(payload)
        if len(rgb) != 360 or len(rgb[0]) != 640:
            raise ValueError(f"{frame['frame_id']} resolution changed.")
        rgb_by_frame[frame["frame_id"]] = rgb

    pair_id_by_visible_id: dict[str, str] = {}
    ground_contact_by_visible_id: dict[str, dict[str, Any]] = {}
    for frame in source["frames"]:
        if frame["truth_class"] != "visible":
            continue
        background_id = (
            f"{frame['layout_id']}_negative_{frame['source_frame_idx']:03d}"
        )
        background = input_frame_by_id.get(background_id)
        if (
            background is None
            or background["split"] != frame["split"]
            or background["truth_class"] != "negative"
        ):
            raise ValueError(f"{frame['frame_id']} lacks a same-split background.")
        pair_id_by_visible_id[frame["frame_id"]] = background_id
        ground_contact_by_visible_id[frame["frame_id"]] = (
            localize_ground_contact_from_background_pair(
                rgb_by_frame[frame["frame_id"]],
                rgb_by_frame[background_id],
            )
        )

    marker_colors = {
        "north_west": "blue",
        "north_east": "yellow",
        "south_east": "white",
        "south_west": "lime",
    }
    frozen_layouts = []
    marker_details_by_layout: dict[str, list[dict[str, Any]]] = {}
    for layout in sorted(source["layouts"], key=lambda item: item["layout_id"]):
        layout_id = layout["layout_id"]
        marker_source_id = f"{layout_id}_negative_000"
        marker_source = input_frame_by_id[marker_source_id]
        localized_markers = []
        detail_rows = []
        for marker in layout["markers"]:
            role = marker["marker_id"]
            detail = localize_marker_top_face(
                rgb_by_frame[marker_source_id],
                marker_color=marker_colors[role],
            )
            detail_rows.append(
                {
                    "marker_id": role,
                    "marker_role": role,
                    "marker_color": marker_colors[role],
                    "source_frame_id": marker_source_id,
                    "source_frame_hash": marker_source["source_frame_hash"],
                    **detail,
                    "world_xz_blocks": marker["world_xz_blocks"],
                    "coordinate_source_hash": marker[
                        "coordinate_source_hash"
                    ],
                }
            )
            localized_markers.append(
                {
                    "marker_id": role,
                    "marker_role": role,
                    "marker_color": marker_colors[role],
                    "image_xy": detail["image_xy"],
                    "world_xz_blocks": marker["world_xz_blocks"],
                    "coordinate_source_hash": marker[
                        "coordinate_source_hash"
                    ],
                    "source_frame_id": marker_source_id,
                    "source_frame_hash": marker_source["source_frame_hash"],
                    "localization_method_version": detail[
                        "localization_method_version"
                    ],
                    "segmentation_pixel_count": detail[
                        "segmentation_pixel_count"
                    ],
                    "bounding_box_xyxy": detail["bounding_box_xyxy"],
                }
            )
        marker_details_by_layout[layout_id] = detail_rows
        frozen_layouts.append(
            {
                "layout_id": layout_id,
                "canonical_camera_pose_id": layout[
                    "canonical_camera_pose_id"
                ],
                "marker_set_id": layout["marker_set_id"],
                "marker_set_source_hash": layout["marker_set_source_hash"],
                "image_width_px": 640,
                "image_height_px": 360,
                "resolution_id": RESOLUTION_ID,
                "pixel_format": "rgb8",
                "markers": localized_markers,
            }
        )

    frozen_frames = []
    for frame in sorted(source["frames"], key=lambda item: item["frame_id"]):
        visible = frame["truth_class"] == "visible"
        region = (
            _image_region(
                ground_contact_by_visible_id[frame["frame_id"]]["image_xy"],
                640,
                360,
            )
            if visible
            else "full_frame_negative"
        )
        frozen_frames.append(
            {
                "frame_id": frame["frame_id"],
                "layout_id": frame["layout_id"],
                "canonical_camera_pose_id": frame[
                    "canonical_camera_pose_id"
                ],
                "split": frame["split"],
                "truth_class": frame["truth_class"],
                "truth_present": frame["truth_present"],
                "source_artifact_id": frame["source_artifact_id"],
                "source_frame_idx": frame["source_frame_idx"],
                "source_frame_hash": frame["source_frame_hash"],
                "source_git_revision": person_c_revision,
                "source_git_path": frame["png_path"],
                "decoded_rgb_hash": hash_json_value(
                    rgb_by_frame[frame["frame_id"]]
                ),
                "image_width_px": 640,
                "image_height_px": 360,
                "pixel_format": "rgb8",
                "resolution_id": RESOLUTION_ID,
                "image_region": region,
                "threshold_selection_eligible": (
                    frame["split"] == "calibration"
                ),
                "paired_background_frame_id": (
                    pair_id_by_visible_id[frame["frame_id"]]
                    if visible
                    else None
                ),
            }
        )
    split = {
        "schema_version": "1.0",
        "detector_calibration_schema_version": (
            FROZEN_DETECTOR_CALIBRATION_SCHEMA_VERSION
        ),
        "dataset_id": "person_e_phase2_c_frames_v0_1",
        "split_version": None,
        "freeze": {
            "status": "frozen_before_threshold_selection",
            "split_frozen_before_threshold_selection": True,
            "threshold_selection_eligible_split": "calibration",
            "heldout_parameter_selection_forbidden": True,
        },
        "source_document": {
            "git_revision": person_c_revision,
            "path": PERSON_C_INPUT_PATH,
            "sha256": _sha256(source_payload),
        },
        "capture_provenance": {
            "git_revision": person_c_revision,
            "path": PERSON_C_PROVENANCE_PATH,
            "sha256": _sha256(provenance_payload),
            "trajectory_count": len(provenance["trajectories"]),
        },
        "partition_authority": {
            "person_b_revision": person_b_revision,
            "u4_partition_schema_version": "person-b-u4-partition-v0.1",
            "real_final_u4_manifest_status": "not_available",
            "available_u4_artifact_ids": [],
            "included_u4_artifact_ids": [],
        },
        "layouts": frozen_layouts,
        "frames": frozen_frames,
    }
    split["split_version"] = "sha256:" + hash_json_value(
        {key: value for key, value in split.items() if key != "split_version"}
    )
    validate_detector_calibration_dataset(split)
    split_hash, _ = _artifact_hash(split)

    coverage_counts = Counter(
        (
            frame["layout_id"],
            frame["split"],
            frame["truth_class"],
            frame["image_region"],
        )
        for frame in frozen_frames
    )
    calibration_ids = {
        (frame["source_artifact_id"], frame["source_frame_idx"])
        for frame in frozen_frames
        if frame["split"] == "calibration"
    }
    heldout_ids = {
        (frame["source_artifact_id"], frame["source_frame_idx"])
        for frame in frozen_frames
        if frame["split"] == "heldout"
    }
    coverage = {
        "schema_version": "1.0",
        "coverage_schema_version": "person-e-phase2-split-coverage-v0.1",
        "split_version": split["split_version"],
        "frame_count": len(frozen_frames),
        "layout_count": len(frozen_layouts),
        "calibration_frame_count": sum(
            frame["split"] == "calibration" for frame in frozen_frames
        ),
        "heldout_frame_count": sum(
            frame["split"] == "heldout" for frame in frozen_frames
        ),
        "visible_frame_count": sum(
            frame["truth_class"] == "visible" for frame in frozen_frames
        ),
        "negative_frame_count": sum(
            frame["truth_class"] == "negative" for frame in frozen_frames
        ),
        "source_identity_intersection": [
            list(item) for item in sorted(calibration_ids & heldout_ids)
        ],
        "source_identities_disjoint": not (calibration_ids & heldout_ids),
        "anonymous_frame_copies_used": False,
        "heldout_used_for_parameter_selection": False,
        "real_final_u4_manifest_available": False,
        "available_u4_artifacts_included": [],
        "counts": [
            {
                "layout_id": key[0],
                "split": key[1],
                "truth_class": key[2],
                "image_region": key[3],
                "count": count,
            }
            for key, count in sorted(coverage_counts.items())
        ],
    }

    calibration_frames = [
        frame for frame in frozen_frames if frame["split"] == "calibration"
    ]
    candidate_audit = []
    candidate_results: dict[str, list[tuple[bool, Any]]] = {}
    for candidate in _candidate_settings():
        results = [
            (
                frame["truth_present"],
                _detect(rgb_by_frame[frame["frame_id"]], candidate),
            )
            for frame in calibration_frames
        ]
        metrics = _metrics(results)
        candidate_results[candidate["candidate_id"]] = results
        candidate_audit.append(
            {
                **copy.deepcopy(candidate),
                "metrics": metrics,
            }
        )
    selected_audit = min(
        candidate_audit,
        key=lambda item: (
            -item["metrics"]["true_positive"],
            item["metrics"]["false_positive"],
            item["metrics"]["false_negative"],
            item["candidate_id"],
        ),
    )
    selected_settings = {
        key: copy.deepcopy(value)
        for key, value in selected_audit.items()
        if key not in {"candidate_id", "metrics"}
    }
    settings_hash = hash_json_value(selected_settings)
    threshold_version = (
        f"person-e-magenta-threshold-sha256-{settings_hash}"
    )
    detector_identity_hash = hash_json_value(
        {
            "detector_algorithm_version": DETECTOR_ALGORITHM_VERSION,
            "threshold_version": threshold_version,
            "settings_hash": settings_hash,
            "split_version": split["split_version"],
            "software_runtime_hash": runtime_hash,
        }
    )
    detector_version = (
        f"{DETECTOR_ALGORITHM_VERSION}:sha256:{detector_identity_hash}"
    )
    selected_results = candidate_results[selected_audit["candidate_id"]]
    contexts = []
    records = []
    by_layout_results: dict[str, list[tuple[bool, Any]]] = defaultdict(list)
    for frame, (_, result) in zip(
        calibration_frames, selected_results, strict=True
    ):
        context = {
            "source_frame_id": frame["frame_id"],
            "source_artifact_id": frame["source_artifact_id"],
            "source_frame_idx": frame["source_frame_idx"],
            "source_frame_hash": frame["source_frame_hash"],
            "decoded_rgb_hash": frame["decoded_rgb_hash"],
            "source_git_revision": frame["source_git_revision"],
            "source_git_path": frame["source_git_path"],
            "split": frame["split"],
            "layout_id": frame["layout_id"],
            "canonical_camera_pose_id": frame[
                "canonical_camera_pose_id"
            ],
            "resolution_id": frame["resolution_id"],
            "image_width_px": frame["image_width_px"],
            "image_height_px": frame["image_height_px"],
            "pixel_format": frame["pixel_format"],
            "image_coordinate_system": "pixel_center_xy_zero_based",
            "truth_class": frame["truth_class"],
            "truth_present": frame["truth_present"],
            "frame_available": True,
        }
        contexts.append(context)
        records.append(
            {
                **{
                    key: value
                    for key, value in context.items()
                    if key != "frame_available"
                },
                "detection_id": (
                    f"{detector_identity_hash}:{frame['frame_id']}"
                ),
                "detector_version": detector_version,
                "threshold_version": threshold_version,
                "status": result.status,
                "presence": result.detected,
                "centroid_xy": (
                    None
                    if result.centroid_xy is None
                    else list(result.centroid_xy)
                ),
                "area_pixels": result.area_pixels,
                "bounding_box_xyxy": (
                    None
                    if result.bounding_box_xyxy is None
                    else list(result.bounding_box_xyxy)
                ),
                "quality_status": "accepted",
                "rejection_reason": result.rejection_reason,
                "threshold_match_pixels": result.threshold_match_pixels,
                "candidate_blob_count": result.candidate_blob_count,
            }
        )
        by_layout_results[frame["layout_id"]].append(
            (frame["truth_present"], result)
        )
    detections = {
        "schema_version": "1.0",
        "detection_schema_version": (
            CALIBRATION_DETECTION_DOCUMENT_SCHEMA_VERSION
        ),
        "document_id": f"person_e_phase2_calibration_{detector_identity_hash}",
        "synthetic": False,
        "scientific_use": "permitted",
        "detector_version": detector_version,
        "threshold_version": threshold_version,
        "split_version": split["split_version"],
        "settings_hash": settings_hash,
        "source_contexts": contexts,
        "records": records,
    }
    validate_detection_document(detections)
    detections_hash, _ = _artifact_hash(detections)

    config = json.loads(config_template.read_text(encoding="utf-8"))
    config["config_schema_version"] = PERSON_E_CONFIG_SCHEMA_VERSION
    config["config_instance_version"] = (
        f"person-e-phase2-calibration-sha256-{detector_identity_hash}"
    )
    config["status"] = PHASE2_CALIBRATED_STATUS
    detector_config = config["detector"]
    detector_config.update(
        {
            "threshold_status": "frozen_calibration_only",
            "threshold_version": threshold_version,
            "calibration_dataset_hash": split_hash,
            "heldout_report_hash": None,
            "detector_algorithm_version": DETECTOR_ALGORITHM_VERSION,
            "split_version": split["split_version"],
            "settings_hash": settings_hash,
            "software_runtime_hash": runtime_hash,
            "hsv_ranges": [
                {
                    "h_min": values[0],
                    "h_max": values[1],
                    "s_min": values[2],
                    "s_max": values[3],
                    "v_min": values[4],
                    "v_max": values[5],
                }
                for values in selected_settings["hsv_ranges"]
            ],
        }
    )
    detector_config["morphology"] = {
        "open_iterations": selected_settings["open_iterations"],
        "close_iterations": selected_settings["close_iterations"],
        "radius_pixels": selected_settings["morphology_radius_pixels"],
    }
    detector_config["blob"] = {
        "connectivity": selected_settings["connectivity"],
        "min_area_pixels": selected_settings["min_area_pixels"],
        "max_area_pixels": selected_settings["max_area_pixels"],
        "selection": "largest_valid_area_then_top_left",
    }
    validate_person_e_config(config)
    config_hash, _ = _artifact_hash(config)

    calibration_report = {
        "schema_version": "1.0",
        "detector_report_schema_version": "person-e-detector-report-v0.3",
        "report_id": f"person_e_phase2_calibration_{detector_identity_hash}",
        "evaluation_split": "calibration",
        "split_version": split["split_version"],
        "split_manifest_hash": split_hash,
        "detector_version": detector_version,
        "threshold_version": threshold_version,
        "settings_hash": settings_hash,
        "selected_candidate_id": selected_audit["candidate_id"],
        "selected_settings": selected_settings,
        "selection_objective": (
            "maximize_true_positive_then_minimize_false_positive_"
            "then_false_negative_then_candidate_id"
        ),
        "candidate_audit": candidate_audit,
        "metrics": selected_audit["metrics"],
        "per_layout_metrics": [
            {
                "layout_id": layout_id,
                **_metrics(results),
            }
            for layout_id, results in sorted(by_layout_results.items())
        ],
        "calibration_detection_document_hash": detections_hash,
        "heldout_frame_count": sum(
            frame["split"] == "heldout" for frame in frozen_frames
        ),
        "heldout_opened_for_parameter_selection": False,
        "heldout_performance_reported": False,
        "software_runtime": runtime_identity,
        "software_runtime_hash": runtime_hash,
    }
    calibration_report_hash, _ = _artifact_hash(calibration_report)
    detector_version_record = {
        "schema_version": "1.0",
        "detector_version_schema_version": (
            "person-e-detector-version-record-v0.1"
        ),
        "detector_version": detector_version,
        "detector_algorithm_version": DETECTOR_ALGORITHM_VERSION,
        "threshold_version": threshold_version,
        "settings_hash": settings_hash,
        "split_version": split["split_version"],
        "split_manifest_hash": split_hash,
        "config_hash": config_hash,
        "calibration_report_hash": calibration_report_hash,
        "detection_document_hash": detections_hash,
        "software_runtime_hash": runtime_hash,
        "heldout_used_for_parameter_selection": False,
        "phase3_heldout_performance_claimed": False,
    }

    correspondence_layouts = []
    homography_records = []
    localization_layouts = []
    all_localization_records = []
    for layout in frozen_layouts:
        layout_id = layout["layout_id"]
        marker_details = marker_details_by_layout[layout_id]
        correspondence = {
            "layout_id": layout_id,
            "canonical_camera_pose_id": layout[
                "canonical_camera_pose_id"
            ],
            "resolution_id": RESOLUTION_ID,
            "image_width_px": 640,
            "image_height_px": 360,
            "image_coordinate_system": "pixel_center_xy_zero_based",
            "world_coordinate_system": "ground_plane_world_xz_blocks",
            "marker_order": [
                "north_west",
                "north_east",
                "south_east",
                "south_west",
            ],
            "marker_localization_method_version": (
                MARKER_LOCALIZATION_METHOD_VERSION
            ),
            "markers": marker_details,
        }
        correspondence_hash = hash_json_value(correspondence)
        correspondence["correspondence_hash"] = correspondence_hash
        correspondence_layouts.append(correspondence)
        image_points = {
            marker["marker_id"]: marker["image_xy"]
            for marker in marker_details
        }
        world_points = {
            marker["marker_id"]: marker["world_xz_blocks"]
            for marker in marker_details
        }
        marker_ids = correspondence["marker_order"]
        homography = fit_marker_homography(
            image_points,
            world_points,
            marker_ids=marker_ids,
            layout_id=layout_id,
            canonical_camera_pose_id=layout[
                "canonical_camera_pose_id"
            ],
            resolution_id=RESOLUTION_ID,
            image_width_px=640,
            image_height_px=360,
            source_correspondence_hash=correspondence_hash,
            detector_version=detector_version,
            software_runtime_hash=runtime_hash,
        )
        homography_records.append(homography.to_record())
        layout_probe_rows = [
            point
            for point in probes["points"]
            if point["layout_id"] == layout_id
        ]
        validation_pairs = []
        image_regions = []
        validation_sources = []
        for point in layout_probe_rows:
            frozen_frame = next(
                frame
                for frame in frozen_frames
                if frame["frame_id"] == point["frame_id"]
            )
            ground = ground_contact_by_visible_id[point["frame_id"]]
            validation_pairs.append(
                (
                    ground["image_xy"],
                    point["probe_point_world_xz_blocks"],
                )
            )
            image_regions.append(frozen_frame["image_region"])
            validation_sources.append(
                {
                    "frame_id": point["frame_id"],
                    "source_artifact_id": point["source_artifact_id"],
                    "source_frame_idx": point["source_frame_idx"],
                    "source_frame_hash": frozen_frame["source_frame_hash"],
                    "decoded_rgb_hash": frozen_frame["decoded_rgb_hash"],
                    "paired_background_frame_id": frozen_frame[
                        "paired_background_frame_id"
                    ],
                    "split": point["split"],
                    "ground_contact": ground,
                    "true_world_xz_blocks": point[
                        "probe_point_world_xz_blocks"
                    ],
                    "world_y_blocks": point[
                        "probe_point_world_y_blocks"
                    ],
                }
            )
        north_west = world_points["north_west"]
        north_east = world_points["north_east"]
        direction = [
            north_east[0] - north_west[0],
            north_east[1] - north_west[1],
        ]
        norm = math.hypot(*direction)
        wall_unit = [direction[0] / norm, direction[1] / norm]
        summary = summarize_localization(
            homography,
            validation_pairs,
            wall_parallel_origin_xz=north_west,
            wall_parallel_positive_unit_xz=wall_unit,
            image_regions=image_regions,
        )
        for record, source_record in zip(
            summary["records"], validation_sources, strict=True
        ):
            record.update(source_record)
            record["layout_id"] = layout_id
            record["canonical_camera_pose_id"] = layout[
                "canonical_camera_pose_id"
            ]
        all_localization_records.extend(summary["records"])
        localization_layouts.append(
            {
                "layout_id": layout_id,
                "canonical_camera_pose_id": layout[
                    "canonical_camera_pose_id"
                ],
                "wall_parallel_origin_xz": north_west,
                "wall_parallel_positive_unit_xz": wall_unit,
                "homography_version_id": homography.to_record()[
                    "homography_version_id"
                ],
                "summary": summary,
            }
        )
    correspondences = {
        "schema_version": "1.0",
        "homography_correspondence_schema_version": (
            "person-e-real-homography-correspondences-v0.1"
        ),
        "source_revision": person_c_revision,
        "source_document_hash": _sha256(source_payload),
        "probe_document_hash": _sha256(probe_payload),
        "detector_version": detector_version,
        "software_runtime_hash": runtime_hash,
        "layouts": correspondence_layouts,
    }
    correspondence_document_hash, _ = _artifact_hash(correspondences)
    homography_document = {
        "schema_version": "1.0",
        "homography_record_schema_version": (
            "person-e-bound-homography-records-v0.1"
        ),
        "correspondence_document_hash": correspondence_document_hash,
        "detector_version": detector_version,
        "software_runtime": runtime_identity,
        "software_runtime_hash": runtime_hash,
        "records": homography_records,
    }
    homography_document_hash, _ = _artifact_hash(homography_document)

    signed = [
        record["signed_wall_parallel_error_blocks"]
        for record in all_localization_records
    ]
    absolute_wall = [abs(value) for value in signed]
    euclidean = [
        record["euclidean_error_blocks"]
        for record in all_localization_records
    ]
    region_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in all_localization_records:
        region_groups[record["image_region"]].append(record)
    localization = {
        "schema_version": "1.0",
        "localization_report_schema_version": (
            "person-e-real-localization-report-v0.1"
        ),
        "source_probe_revision": person_c_revision,
        "source_probe_document_hash": _sha256(probe_payload),
        "homography_document_hash": homography_document_hash,
        "detector_version": detector_version,
        "ground_contact_localization_method_version": (
            GROUND_CONTACT_LOCALIZATION_METHOD_VERSION
        ),
        "sample_count": len(all_localization_records),
        "signed_wall_parallel_error_blocks": {
            "minimum": min(signed),
            "maximum": max(signed),
            "mean": sum(signed) / len(signed),
            "median": _percentile(signed, 0.5),
        },
        "median_absolute_wall_parallel_error_blocks": _percentile(
            absolute_wall, 0.5
        ),
        "p95_absolute_wall_parallel_error_blocks": _percentile(
            absolute_wall, 0.95
        ),
        "median_euclidean_error_blocks": _percentile(euclidean, 0.5),
        "p95_euclidean_error_blocks": _percentile(euclidean, 0.95),
        "planning_gate_passed": (
            _percentile(absolute_wall, 0.5) <= 0.2
            and _percentile(absolute_wall, 0.95) < 0.5
        ),
        "per_layout": localization_layouts,
        "by_image_region": [
            {
                "image_region": region,
                "sample_count": len(rows),
                "median_absolute_wall_parallel_error_blocks": _percentile(
                    [
                        abs(row["signed_wall_parallel_error_blocks"])
                        for row in rows
                    ],
                    0.5,
                ),
                "p95_absolute_wall_parallel_error_blocks": _percentile(
                    [
                        abs(row["signed_wall_parallel_error_blocks"])
                        for row in rows
                    ],
                    0.95,
                ),
                "median_euclidean_error_blocks": _percentile(
                    [row["euclidean_error_blocks"] for row in rows], 0.5
                ),
                "p95_euclidean_error_blocks": _percentile(
                    [row["euclidean_error_blocks"] for row in rows], 0.95
                ),
            }
            for region, rows in sorted(region_groups.items())
        ],
        "by_location": [
            {
                "location_id": record["frame_id"],
                "layout_id": record["layout_id"],
                "image_region": record["image_region"],
                "true_world_xz_blocks": record["true_world_xz_blocks"],
                "signed_wall_parallel_error_blocks": record[
                    "signed_wall_parallel_error_blocks"
                ],
                "absolute_wall_parallel_error_blocks": abs(
                    record["signed_wall_parallel_error_blocks"]
                ),
                "euclidean_error_blocks": record[
                    "euclidean_error_blocks"
                ],
                "sample_count": 1,
            }
            for record in sorted(
                all_localization_records,
                key=lambda row: (row["layout_id"], row["frame_id"]),
            )
        ],
        "records": all_localization_records,
    }

    documents = {
        "step2_1_blockers.json": _step2_1_blocker_record(),
        "frozen_split_manifest.json": split,
        "split_coverage_report.json": coverage,
        "frozen_detector_config.json": config,
        "calibration_detection_records.json": detections,
        "calibration_report.json": calibration_report,
        "detector_version_record.json": detector_version_record,
        "homography_correspondences.json": correspondences,
        "homography_record.json": homography_document,
        "localization_validation_report.json": localization,
    }
    provenance_records = []
    direct_inputs = {
        "frozen_split_manifest.json": [
            f"git:{person_c_revision}:{PERSON_C_INPUT_PATH}",
            f"git:{person_c_revision}:{PERSON_C_PROVENANCE_PATH}",
            f"git:{person_b_revision}:src/mineocclude/probes/splits.py",
        ],
        "split_coverage_report.json": ["frozen_split_manifest.json"],
        "frozen_detector_config.json": ["frozen_split_manifest.json"],
        "calibration_detection_records.json": [
            "frozen_split_manifest.json",
            "frozen_detector_config.json",
        ],
        "calibration_report.json": [
            "calibration_detection_records.json",
            "frozen_detector_config.json",
        ],
        "detector_version_record.json": [
            "frozen_detector_config.json",
            "calibration_report.json",
        ],
        "homography_correspondences.json": [
            "frozen_split_manifest.json",
            f"git:{person_c_revision}:{PERSON_C_PROBE_PATH}",
        ],
        "homography_record.json": [
            "homography_correspondences.json",
            "detector_version_record.json",
        ],
        "localization_validation_report.json": [
            "homography_record.json",
            f"git:{person_c_revision}:{PERSON_C_PROBE_PATH}",
        ],
    }
    for path, document in sorted(documents.items()):
        digest, size = _artifact_hash(document)
        provenance_records.append(
            {
                "artifact_id": f"person_e_phase2_v0_1:{path}",
                "path": path,
                "sha256": digest,
                "size_bytes": size,
                "direct_inputs": direct_inputs.get(path, []),
                "status": "accepted",
                "shared_immutable_registry_emitted": False,
            }
        )
    provenance_index = {
        "schema_version": "1.0",
        "provenance_index_schema_version": (
            "person-e-phase2-provenance-index-v0.1"
        ),
        "evidence_schema_version": EVIDENCE_SCHEMA_VERSION,
        "source_revisions": {
            "person_c": person_c_revision,
            "person_b": person_b_revision,
            "person_e_base": PERSON_E_BASE_SHA,
        },
        "shared_immutable_registry_status": (
            "pending_step2_1_authoritative_inputs"
        ),
        "records": provenance_records,
    }
    documents["provenance_index.json"] = provenance_index
    provenance_index_hash, _ = _artifact_hash(provenance_index)
    documents["phase2_status.json"] = {
        "schema_version": "1.0",
        "status_schema_version": "person-e-phase2-status-v0.1",
        "evidence_schema_version": EVIDENCE_SCHEMA_VERSION,
        "overall_status": "PARTIAL",
        "steps": [
            {
                "step": "2.1",
                "status": "BLOCKED",
                "evidence": "step2_1_blockers.json",
                "remaining_blocker": "authoritative_A_and_C_registry_fields",
            },
            {
                "step": "2.2",
                "status": "PASS",
                "evidence": "frozen_split_manifest.json",
                "remaining_blocker": None,
            },
            {
                "step": "2.3",
                "status": "PASS",
                "evidence": "calibration_report.json",
                "remaining_blocker": None,
            },
            {
                "step": "2.4",
                "status": "PARTIAL",
                "evidence": "localization_validation_report.json",
                "remaining_blocker": (
                    "measured_independent_probe_localization_gate_failed"
                    if not localization["planning_gate_passed"]
                    else None
                ),
            },
        ],
        "provenance_index_hash": provenance_index_hash,
        "real_completed_a_or_c_pilot_records_emitted": False,
        "detector_heldout_performance_claimed": False,
        "homography_planning_gate_passed": localization[
            "planning_gate_passed"
        ],
    }
    return documents


def main() -> None:
    args = parse_args()
    documents = _build_documents(
        config_template=args.config_template,
        person_c_revision=args.person_c_revision,
        person_b_revision=args.person_b_revision,
    )
    for relative_path, document in sorted(documents.items()):
        write_json_exclusive(args.output_dir / relative_path, document)


if __name__ == "__main__":
    main()
