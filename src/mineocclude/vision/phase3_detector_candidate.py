"""Freeze and publish the Person E Phase 3 Detector v1 candidate."""

from __future__ import annotations

import hashlib
import json
import subprocess
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from mineocclude.experiments.registry import (
    formatted_json_bytes,
    hash_file_bytes,
    hash_json_value,
    write_bytes_exclusive,
)
from mineocclude.vision.calibration import (
    decode_png_rgb_bytes,
    load_committed_frame_rgb,
)
from mineocclude.vision.detection_records import (
    DETECTION_RECORD_SCHEMA_VERSION,
    PARQUET_WRITER_SETTINGS,
    PERSON_A_PARQUET_AUTHORITY_REVISION,
    PERSON_C_DEVELOPMENT_SOURCE_REVISION,
    PYARROW_VERSION,
    arrow_schema_record,
    detection_arrow_schema,
    detection_parquet_bytes,
    read_detection_parquet_bytes,
    require_complete_frame_identities,
    sort_detection_records,
)
from mineocclude.vision.magenta import (
    DETECTOR_ALGORITHM_VERSION,
    DetectionResult,
    HsvRange,
    detect_magenta,
)

PERSON_E_REQUIRED_BASE_REVISION = "44af0d06c47a8270991bd1b1d70031d116dd5e00"
PHASE3_CANDIDATE_ALGORITHM_ID = "hsv-largest-valid-blob-v1.0-candidate"
HISTORICAL_DETECTOR_VERSION = (
    "hsv-largest-valid-blob-v0.1:sha256:"
    "1ff40286e68007b06d160a0b8eb91c4adabed00873675cbfd888d4a8d5ad1b37"
)
EVIDENCE_ROOT_NAME = "person_e_phase3_step3_1_candidate_freeze_v0_1"
SOURCE_VALIDATION_PATH = (
    "docs/status/person_e_phase2_step2_4_v0_4/source_validation.json"
)
GROUND_CONTACT_PATH = "docs/status/person_e_phase2_step2_4_v0_4/detector_outputs.json"
HISTORICAL_CONFIG_PATH = "docs/status/person_e_phase2_v0_1/frozen_detector_config.json"


class CandidateFreezeError(ValueError):
    """Raised when the candidate cannot be frozen without weakening provenance."""


_HISTORICAL_SETTINGS: dict[str, Any] = {
    "hsv_ranges": [[280.0, 320.0, 0.5, 1.0, 0.35, 1.0]],
    "min_area_pixels": 20,
    "max_area_pixels": 5000,
    "open_iterations": 0,
    "close_iterations": 0,
    "morphology_radius_pixels": 1,
    "connectivity": 8,
    "component_filter": "inclusive_area_bounds",
    "selection_rule": "largest_valid_area",
    "tie_breaking_rule": "topmost_then_leftmost",
    "expected_channel_order": "RGB",
    "pixel_format": "rgb8",
    "image_coordinate_system": "pixel_center_xy_zero_based",
    "centroid_convention": "arithmetic_mean_of_selected_pixel_centres",
    "bounding_box_convention": "xyxy_half_open",
}

_CANDIDATES: tuple[dict[str, Any], ...] = (
    {
        "candidate_id": "historical_v0_1_min_area_20",
        "algorithm_id": DETECTOR_ALGORITHM_VERSION,
        "settings": _HISTORICAL_SETTINGS,
        "parameter_changes_from_historical_v0_1": [],
        "candidate_order": 0,
    },
    {
        "candidate_id": "phase3_v1_min_area_19",
        "algorithm_id": PHASE3_CANDIDATE_ALGORITHM_ID,
        "settings": {
            **_HISTORICAL_SETTINGS,
            "min_area_pixels": 19,
        },
        "parameter_changes_from_historical_v0_1": [
            {
                "parameter": "min_area_pixels",
                "historical_value": 20,
                "candidate_value": 19,
                "justification": (
                    "The sole documented development false negative contains "
                    "19 threshold-matching connected pixels; no other detector "
                    "parameter or algorithmic operation is changed."
                ),
            }
        ],
        "candidate_order": 1,
    },
)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CandidateFreezeError(f"Could not load {path}: {error}") from error
    if not isinstance(value, dict):
        raise CandidateFreezeError(f"{path} must contain one mapping.")
    return value


def _git_output(repository: Path, arguments: Sequence[str]) -> bytes:
    completed = subprocess.run(
        ["git", "-C", str(repository), *arguments],
        check=False,
        capture_output=True,
    )
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise CandidateFreezeError(f"Git command failed: {detail}")
    return completed.stdout


def _git_text(repository: Path, arguments: Sequence[str]) -> str:
    return _git_output(repository, arguments).decode("utf-8").strip()


def _require_repository_preconditions(repository: Path) -> None:
    if (
        _git_text(repository, ["branch", "--show-current"])
        != "role/person-e-operations"
    ):
        raise CandidateFreezeError("Person E branch changed.")
    if _git_text(repository, ["rev-parse", "HEAD"]) != PERSON_E_REQUIRED_BASE_REVISION:
        raise CandidateFreezeError("Person E starting HEAD changed.")
    if (
        _git_text(repository, ["rev-parse", "refs/remotes/origin/role/person-a-model"])
        != PERSON_A_PARQUET_AUTHORITY_REVISION
    ):
        raise CandidateFreezeError("Person A Parquet authority revision changed.")
    if (
        _git_text(repository, ["rev-parse", "refs/remotes/origin/role/person-c-data"])
        != PERSON_C_DEVELOPMENT_SOURCE_REVISION
    ):
        raise CandidateFreezeError("Person C development source revision changed.")
    dependency_path = repository / "requirements.txt"
    committed_dependency = _git_output(
        repository,
        [
            "cat-file",
            "blob",
            f"HEAD:{dependency_path.relative_to(repository).as_posix()}",
        ],
    )
    if dependency_path.read_bytes() != committed_dependency:
        raise CandidateFreezeError("Person E requirements.txt was modified.")


def _historical_evidence_hashes(repository: Path) -> dict[str, str]:
    paths = _git_text(repository, ["ls-files", "docs"]).splitlines()
    selected = sorted(
        path for path in paths if "person_e_phase1" in path or "person_e_phase2" in path
    )
    hashes: dict[str, str] = {}
    for path in selected:
        committed = _git_output(repository, ["cat-file", "blob", f"HEAD:{path}"])
        working_path = repository / path
        if not working_path.is_file() or working_path.read_bytes() != committed:
            raise CandidateFreezeError(f"Historical evidence changed: {path}")
        hashes[path] = _sha256(committed)
    if not hashes:
        raise CandidateFreezeError("No historical Phase 1/2 evidence was found.")
    return hashes


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


def _development_frames(
    repository: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    source_path = repository / SOURCE_VALIDATION_PATH
    ground_path = repository / GROUND_CONTACT_PATH
    source = _load_json(source_path)
    ground = _load_json(ground_path)
    if (
        source.get("source_revision") != PERSON_C_DEVELOPMENT_SOURCE_REVISION
        or ground.get("source_revision") != PERSON_C_DEVELOPMENT_SOURCE_REVISION
        or source.get("validated_png_count") != 72
        or source.get("source_document_path")
        != "data/handoff_e/detector_calibration_inputs.json"
    ):
        raise CandidateFreezeError("Phase 2 v0.4 source binding changed.")
    region_by_visible_id = {
        record["frame_id"]: _image_region(
            record["ground_contact"]["image_xy"],
            record["visible_source"]["image_width_px"],
            record["visible_source"]["image_height_px"],
        )
        for record in ground["ground_contact_records"]
    }
    raw_frames = source.get("source_png_records")
    if not isinstance(raw_frames, list) or len(raw_frames) != 72:
        raise CandidateFreezeError("Development source must contain exactly 72 frames.")
    frames: list[dict[str, Any]] = []
    for raw_frame in raw_frames:
        frame = dict(raw_frame)
        frame_id = frame["frame_id"]
        truth_present = frame["truth_present"]
        if truth_present and frame_id not in region_by_visible_id:
            raise CandidateFreezeError(
                f"Missing independent image region for {frame_id}."
            )
        frame.update(
            {
                "trajectory_id": frame["source_artifact_id"],
                "model_frame_idx": None,
                "resolution_id": "resolution_640x360_rgb8",
                "image_coordinate_system": "pixel_center_xy_zero_based",
                "historical_phase2_split_role": frame["split"],
                "split_role": "development",
                "image_region": (
                    region_by_visible_id[frame_id]
                    if truth_present
                    else "full_frame_negative"
                ),
                "background_stratum": None,
                "background_stratum_status": "unavailable_owner_authored",
            }
        )
        frames.append(frame)
    ordered = sorted(frames, key=lambda frame: (frame["layout_id"], frame["frame_id"]))
    if len({frame["frame_id"] for frame in ordered}) != 72:
        raise CandidateFreezeError("Development frame identities are not unique.")
    if Counter(frame["historical_phase2_split_role"] for frame in ordered) != {
        "calibration": 36,
        "heldout": 36,
    }:
        raise CandidateFreezeError("Historical Phase 2 roles changed.")
    return ordered, {
        "source_validation_path": SOURCE_VALIDATION_PATH,
        "source_validation_sha256": hash_file_bytes(source_path),
        "ground_contact_path": GROUND_CONTACT_PATH,
        "ground_contact_sha256": hash_file_bytes(ground_path),
        "source_document_path": source["source_document_path"],
        "source_document_sha256": source["source_document_hash"],
        "source_revision": source["source_revision"],
    }


def _detector_arguments(settings: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "hsv_ranges": [HsvRange(*values) for values in settings["hsv_ranges"]],
        "min_area_pixels": settings["min_area_pixels"],
        "max_area_pixels": settings["max_area_pixels"],
        "open_iterations": settings["open_iterations"],
        "close_iterations": settings["close_iterations"],
        "morphology_radius_pixels": settings["morphology_radius_pixels"],
        "connectivity": settings["connectivity"],
    }


def _classification(truth_present: bool, detected_present: bool) -> str:
    if truth_present:
        return "TP" if detected_present else "FN"
    return "FP" if detected_present else "TN"


def _confusion(
    frame_results: Sequence[tuple[Mapping[str, Any], DetectionResult]],
) -> dict[str, Any]:
    classifications = Counter(
        _classification(frame["truth_present"], result.detected)
        for frame, result in frame_results
    )
    tp = classifications["TP"]
    fp = classifications["FP"]
    tn = classifications["TN"]
    fn = classifications["FN"]
    precision_denominator = tp + fp
    recall_denominator = tp + fn
    return {
        "sample_count": len(frame_results),
        "positive_count": tp + fn,
        "negative_count": tn + fp,
        "true_positive": tp,
        "false_positive": fp,
        "true_negative": tn,
        "false_negative": fn,
        "precision": tp / precision_denominator if precision_denominator else None,
        "recall": tp / recall_denominator if recall_denominator else None,
    }


def _failure_inventory(
    frame_results: Sequence[tuple[Mapping[str, Any], DetectionResult]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    false_positives: list[dict[str, Any]] = []
    false_negatives: list[dict[str, Any]] = []
    for frame, result in frame_results:
        classification = _classification(frame["truth_present"], result.detected)
        if classification not in {"FP", "FN"}:
            continue
        record = {
            "frame_id": frame["frame_id"],
            "layout_id": frame["layout_id"],
            "historical_phase2_split_role": frame["historical_phase2_split_role"],
            "source_path": frame["source_git_path"],
            "source_sha256": frame["source_frame_hash"],
            "status": result.status,
            "reason": result.rejection_reason,
            "threshold_match_pixels": result.threshold_match_pixels,
            "candidate_blob_count": result.candidate_blob_count,
            "area_pixels": result.area_pixels,
        }
        (false_positives if classification == "FP" else false_negatives).append(record)
    return false_positives, false_negatives


def _evaluate_candidates(
    repository: Path,
    frames: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, dict[str, DetectionResult]]]:
    """Evaluate min-area 19 once, deriving min-area 20 exactly except at 19."""

    representative_by_hash: dict[str, Mapping[str, Any]] = {}
    for frame in frames:
        representative_by_hash.setdefault(frame["source_frame_hash"], frame)
    result_19_by_hash: dict[str, DetectionResult] = {}
    result_20_by_hash: dict[str, DetectionResult] = {}
    settings_19 = _CANDIDATES[1]["settings"]
    settings_20 = _CANDIDATES[0]["settings"]
    for source_hash, frame in sorted(representative_by_hash.items()):
        rgb = load_committed_frame_rgb(frame, repository=repository)
        result_19 = detect_magenta(rgb, **_detector_arguments(settings_19))
        result_19_by_hash[source_hash] = result_19
        if result_19.detected and result_19.area_pixels == 19:
            result_20 = detect_magenta(rgb, **_detector_arguments(settings_20))
        else:
            # With every other setting fixed, increasing the inclusive minimum
            # from 19 to 20 changes the selected result only when the selected
            # largest component has area exactly 19.
            result_20 = result_19
        result_20_by_hash[source_hash] = result_20

    results_by_candidate = {
        _CANDIDATES[0]["candidate_id"]: {
            frame["frame_id"]: result_20_by_hash[frame["source_frame_hash"]]
            for frame in frames
        },
        _CANDIDATES[1]["candidate_id"]: {
            frame["frame_id"]: result_19_by_hash[frame["source_frame_hash"]]
            for frame in frames
        },
    }
    candidate_records: list[dict[str, Any]] = []
    for candidate in _CANDIDATES:
        candidate_results = results_by_candidate[candidate["candidate_id"]]
        paired = [(frame, candidate_results[frame["frame_id"]]) for frame in frames]
        false_positives, false_negatives = _failure_inventory(paired)
        split_results: dict[str, list[tuple[Mapping[str, Any], DetectionResult]]] = (
            defaultdict(list)
        )
        for frame_result in paired:
            split_results[frame_result[0]["historical_phase2_split_role"]].append(
                frame_result
            )
        candidate_records.append(
            {
                "candidate_id": candidate["candidate_id"],
                "candidate_order": candidate["candidate_order"],
                "algorithm_id": candidate["algorithm_id"],
                "settings": candidate["settings"],
                "settings_sha256": hash_json_value(candidate["settings"]),
                "parameter_changes_from_historical_v0_1": candidate[
                    "parameter_changes_from_historical_v0_1"
                ],
                "metrics": _confusion(paired),
                "historical_role_diagnostic_metrics": {
                    split: _confusion(values)
                    for split, values in sorted(split_results.items())
                },
                "false_positives": false_positives,
                "false_negatives": false_negatives,
            }
        )
    return candidate_records, results_by_candidate


def _selected_candidate(
    candidate_records: Sequence[Mapping[str, Any]],
) -> Mapping[str, Any]:
    return min(
        candidate_records,
        key=lambda candidate: (
            -candidate["metrics"]["true_positive"],
            candidate["metrics"]["false_positive"],
            candidate["metrics"]["false_negative"],
            len(candidate["parameter_changes_from_historical_v0_1"]),
            candidate["candidate_order"],
        ),
    )


def _candidate_configuration(
    *,
    repository: Path,
    selected: Mapping[str, Any],
    frames: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], str, str, str]:
    implementation_path = repository / "src/mineocclude/vision/magenta.py"
    implementation_sha256 = hash_file_bytes(implementation_path)
    settings_sha256 = hash_json_value(selected["settings"])
    configuration = {
        "algorithm_id": selected["algorithm_id"],
        "detector_core_algorithm_version": DETECTOR_ALGORITHM_VERSION,
        "detector_core_implementation_path": ("src/mineocclude/vision/magenta.py"),
        "detector_implementation_sha256": implementation_sha256,
        "detector_settings": selected["settings"],
        "detector_settings_sha256": settings_sha256,
        "person_e_source_base_revision": PERSON_E_REQUIRED_BASE_REVISION,
        "person_c_development_source_revision": (PERSON_C_DEVELOPMENT_SOURCE_REVISION),
        "person_a_parquet_authority_revision": (PERSON_A_PARQUET_AUTHORITY_REVISION),
        "pyarrow_version": PYARROW_VERSION,
        "formal_test_gates": {
            "minimum_precision": 0.95,
            "minimum_recall": 0.95,
        },
        "applicability": {
            "layout_ids": sorted({frame["layout_id"] for frame in frames}),
            "canonical_camera_pose_ids": sorted(
                {frame["canonical_camera_pose_id"] for frame in frames}
            ),
            "resolution_id": "resolution_640x360_rgb8",
            "image_width_px": 640,
            "image_height_px": 360,
            "pixel_format": "rgb8",
            "expected_channel_order": "RGB",
            "image_coordinate_system": "pixel_center_xy_zero_based",
            "mismatched_input_behavior": "reject_fail_closed",
        },
    }
    config_sha256 = hash_json_value(configuration)
    return (
        {
            "schema_version": "1.0",
            "candidate_config_schema_version": (
                "person-e-phase3-detector-candidate-config-v1.0"
            ),
            "configuration": configuration,
            "detector_config_sha256": config_sha256,
        },
        config_sha256,
        settings_sha256,
        implementation_sha256,
    )


def _version_record(
    *,
    selected: Mapping[str, Any],
    config_sha256: str,
    settings_sha256: str,
    implementation_sha256: str,
    freeze_timestamp_utc: str,
    development_source_manifest_sha256: str,
) -> dict[str, Any]:
    identity = {
        "algorithm_id": selected["algorithm_id"],
        "detector_config_sha256": config_sha256,
        "detector_settings_sha256": settings_sha256,
        "detector_implementation_sha256": implementation_sha256,
        "person_e_source_base_revision": PERSON_E_REQUIRED_BASE_REVISION,
        "person_c_development_source_revision": (PERSON_C_DEVELOPMENT_SOURCE_REVISION),
        "person_a_parquet_authority_revision": (PERSON_A_PARQUET_AUTHORITY_REVISION),
        "pyarrow_version": PYARROW_VERSION,
    }
    identity_sha256 = hash_json_value(identity)
    detector_version = f"{selected['algorithm_id']}:sha256:{identity_sha256}"
    return {
        "schema_version": "1.0",
        "candidate_version_schema_version": (
            "person-e-phase3-detector-candidate-version-v1.0"
        ),
        "candidate_status": "frozen_awaiting_new_untouched_test",
        "detector_version": detector_version,
        "detector_identity_sha256": identity_sha256,
        "detector_algorithm_id": selected["algorithm_id"],
        "detector_config_sha256": config_sha256,
        "detector_settings_sha256": settings_sha256,
        "detector_implementation_sha256": implementation_sha256,
        "development_source_manifest_sha256": (development_source_manifest_sha256),
        "development_source_revision": PERSON_C_DEVELOPMENT_SOURCE_REVISION,
        "person_e_source_base_revision": PERSON_E_REQUIRED_BASE_REVISION,
        "person_e_candidate_commit_status": "not_committed_by_task_restriction",
        "person_a_parquet_authority_revision": (PERSON_A_PARQUET_AUTHORITY_REVISION),
        "pyarrow_version": PYARROW_VERSION,
        "freeze_timestamp_utc": freeze_timestamp_utc,
        "freeze_timestamp_policy": (
            "explicit_utc_task_freeze_value_reused_for_all_regenerations"
        ),
        "identity": identity,
    }


def _development_record(
    frame: Mapping[str, Any],
    result: DetectionResult,
    *,
    version_record: Mapping[str, Any],
    person_c_source_revision: str = PERSON_C_DEVELOPMENT_SOURCE_REVISION,
) -> dict[str, Any]:
    width = frame["image_width_px"]
    height = frame["image_height_px"]
    box = result.bounding_box_xyxy
    centroid = result.centroid_xy
    selected_fraction = (
        None
        if result.area_pixels is None or result.threshold_match_pixels == 0
        else result.area_pixels / result.threshold_match_pixels
    )
    return {
        "schema_version": DETECTION_RECORD_SCHEMA_VERSION,
        "record_id": (
            "person-e-detection-"
            + hash_json_value(
                {
                    "detector_version": version_record["detector_version"],
                    "frame_id": frame["frame_id"],
                }
            )
        ),
        "frame_id": frame["frame_id"],
        "trajectory_id": frame["trajectory_id"],
        "model_frame_idx": frame["model_frame_idx"],
        "source_artifact_id": frame["source_artifact_id"],
        "source_frame_idx": frame["source_frame_idx"],
        "layout_id": frame["layout_id"],
        "canonical_camera_pose_id": frame["canonical_camera_pose_id"],
        "resolution_id": frame["resolution_id"],
        "image_width_px": width,
        "image_height_px": height,
        "pixel_format": frame["pixel_format"],
        "image_coordinate_system": frame["image_coordinate_system"],
        "split_role": "development",
        "historical_phase2_split_role": frame["historical_phase2_split_role"],
        "truth_present": frame["truth_present"],
        "detected_present": result.detected,
        "classification": _classification(frame["truth_present"], result.detected),
        "centroid_x": None if centroid is None else centroid[0],
        "centroid_y": None if centroid is None else centroid[1],
        "area_pixels": result.area_pixels,
        "bbox_x_min": None if box is None else box[0],
        "bbox_y_min": None if box is None else box[1],
        "bbox_x_max_exclusive": None if box is None else box[2],
        "bbox_y_max_exclusive": None if box is None else box[3],
        "threshold_match_pixels": result.threshold_match_pixels,
        "threshold_match_fraction": (result.threshold_match_pixels / (width * height)),
        "candidate_blob_count": result.candidate_blob_count,
        "selected_blob_fraction_of_threshold_matches": selected_fraction,
        "quality_status": "accepted",
        "detector_algorithm_id": version_record["detector_algorithm_id"],
        "detector_version": version_record["detector_version"],
        "detector_config_sha256": version_record["detector_config_sha256"],
        "detector_settings_sha256": version_record["detector_settings_sha256"],
        "detector_implementation_sha256": version_record[
            "detector_implementation_sha256"
        ],
        "status": result.status,
        "reason": result.rejection_reason,
        "image_region": frame["image_region"],
        "background_stratum": frame["background_stratum"],
        "background_stratum_status": frame["background_stratum_status"],
        "source_path": frame["source_git_path"],
        "source_sha256": frame["source_frame_hash"],
        "person_c_source_revision": person_c_source_revision,
        "person_a_parquet_authority_revision": (PERSON_A_PARQUET_AUTHORITY_REVISION),
    }


def _validate_frozen_candidate_documents(
    repository: Path,
    candidate_config: Mapping[str, Any],
    candidate_version: Mapping[str, Any],
) -> Mapping[str, Any]:
    if set(candidate_config) != {
        "schema_version",
        "candidate_config_schema_version",
        "configuration",
        "detector_config_sha256",
    }:
        raise CandidateFreezeError("Frozen candidate config fields changed.")
    configuration = candidate_config["configuration"]
    if (
        candidate_config["schema_version"] != "1.0"
        or not isinstance(configuration, Mapping)
        or candidate_config["detector_config_sha256"] != hash_json_value(configuration)
    ):
        raise CandidateFreezeError("Frozen candidate config hash is invalid.")
    settings = configuration.get("detector_settings")
    if not isinstance(settings, Mapping) or configuration.get(
        "detector_settings_sha256"
    ) != hash_json_value(settings):
        raise CandidateFreezeError("Frozen candidate settings hash is invalid.")
    implementation_path = configuration.get("detector_core_implementation_path")
    if not isinstance(implementation_path, str) or hash_file_bytes(
        repository / implementation_path
    ) != configuration.get("detector_implementation_sha256"):
        raise CandidateFreezeError("Frozen detector implementation hash changed.")
    required_version_fields = {
        "detector_version",
        "detector_config_sha256",
        "detector_settings_sha256",
        "detector_implementation_sha256",
        "detector_algorithm_id",
        "development_source_revision",
        "freeze_timestamp_utc",
        "person_a_parquet_authority_revision",
        "pyarrow_version",
    }
    if not isinstance(candidate_version, Mapping) or not required_version_fields <= set(
        candidate_version
    ):
        raise CandidateFreezeError("Frozen candidate version record is incomplete.")
    expected = {
        "detector_config_sha256": candidate_config["detector_config_sha256"],
        "detector_settings_sha256": configuration["detector_settings_sha256"],
        "detector_implementation_sha256": configuration[
            "detector_implementation_sha256"
        ],
        "detector_algorithm_id": configuration["algorithm_id"],
        "development_source_revision": PERSON_C_DEVELOPMENT_SOURCE_REVISION,
        "person_a_parquet_authority_revision": (PERSON_A_PARQUET_AUTHORITY_REVISION),
        "pyarrow_version": PYARROW_VERSION,
    }
    if any(candidate_version.get(field) != value for field, value in expected.items()):
        raise CandidateFreezeError("Frozen candidate config/version binding changed.")
    return settings


def _load_generic_committed_rgb(
    repository: Path,
    frame: Mapping[str, Any],
) -> list[list[list[int]]]:
    source_revision = frame["source_git_revision"]
    source_path = frame["source_git_path"]
    payload = _git_output(
        repository,
        ["cat-file", "blob", f"{source_revision}:{source_path}"],
    )
    if _sha256(payload) != frame["source_frame_hash"]:
        raise CandidateFreezeError("Committed source PNG hash changed.")
    rgb = decode_png_rgb_bytes(payload)
    if (
        len(rgb) != frame["image_height_px"]
        or len(rgb[0]) != frame["image_width_px"]
        or frame["pixel_format"] != "rgb8"
    ):
        raise CandidateFreezeError("Committed source PNG applicability changed.")
    return rgb


def evaluate_frozen_candidate_records(
    repository: Path | str,
    *,
    frames: Sequence[Mapping[str, Any]],
    candidate_config: Mapping[str, Any],
    candidate_version: Mapping[str, Any],
    split_role: str,
    person_c_source_revision: str,
) -> tuple[list[dict[str, Any]], dict[str, Any], Any, bytes]:
    """Evaluate one exact frozen candidate on a complete development/test manifest."""

    root = Path(repository).resolve()
    if split_role not in {"development", "test"}:
        raise CandidateFreezeError(
            "Frozen evaluation role must be development or test."
        )
    settings = _validate_frozen_candidate_documents(
        root, candidate_config, candidate_version
    )
    ordered_frames = sorted(
        (dict(frame) for frame in frames),
        key=lambda frame: (frame["layout_id"], frame["frame_id"]),
    )
    expected_ids = [frame["frame_id"] for frame in ordered_frames]
    require_complete_frame_identities(expected_ids, expected_ids)
    result_by_hash: dict[str, DetectionResult] = {}
    results_by_frame: dict[str, DetectionResult] = {}
    for frame in ordered_frames:
        source_hash = frame["source_frame_hash"]
        result = result_by_hash.get(source_hash)
        if result is None:
            rgb = _load_generic_committed_rgb(root, frame)
            result = detect_magenta(rgb, **_detector_arguments(settings))
            result_by_hash[source_hash] = result
        results_by_frame[frame["frame_id"]] = result
    require_complete_frame_identities(expected_ids, list(results_by_frame))
    records = sort_detection_records(
        [
            _development_record(
                {
                    **frame,
                    "split_role": split_role,
                    "historical_phase2_split_role": (
                        frame.get("historical_phase2_split_role")
                        if split_role == "development"
                        else None
                    ),
                },
                results_by_frame[frame["frame_id"]],
                version_record=candidate_version,
                person_c_source_revision=person_c_source_revision,
            )
            for frame in ordered_frames
        ]
    )
    if split_role == "test":
        for record in records:
            record["split_role"] = "test"
            record["historical_phase2_split_role"] = None
    schema = detection_arrow_schema(
        detector_version=candidate_version["detector_version"],
        detector_config_sha256=candidate_version["detector_config_sha256"],
        detector_settings_sha256=candidate_version["detector_settings_sha256"],
        detector_implementation_sha256=candidate_version[
            "detector_implementation_sha256"
        ],
        person_c_source_revision=person_c_source_revision,
    )
    parquet_payload = detection_parquet_bytes(records, schema=schema)
    if read_detection_parquet_bytes(parquet_payload, schema=schema) != records:
        raise CandidateFreezeError("Frozen evaluation Parquet read-back changed.")
    paired = [(frame, results_by_frame[frame["frame_id"]]) for frame in ordered_frames]
    metrics = _confusion(paired)
    gates = candidate_config["configuration"]["formal_test_gates"]
    report = {
        "schema_version": "1.0",
        "evaluation_report_schema_version": (
            "person-e-phase3-frozen-detector-evaluation-v1.0"
        ),
        "evaluation_role": split_role,
        "detector_version": candidate_version["detector_version"],
        "person_c_source_revision": person_c_source_revision,
        "record_count": len(records),
        "complete_identity_coverage": True,
        "metrics": metrics,
        "formal_gate_eligible": split_role == "test",
        "formal_gate": (
            {
                "minimum_precision": gates["minimum_precision"],
                "minimum_recall": gates["minimum_recall"],
                "passed": (
                    metrics["precision"] is not None
                    and metrics["recall"] is not None
                    and metrics["precision"] >= gates["minimum_precision"]
                    and metrics["recall"] >= gates["minimum_recall"]
                ),
            }
            if split_role == "test"
            else None
        ),
        "per_layout": _group_metrics(ordered_frames, results_by_frame, "layout_id"),
        "per_image_region": _group_metrics(
            ordered_frames, results_by_frame, "image_region"
        ),
        "parquet_sha256": _sha256(parquet_payload),
    }
    return records, report, schema, parquet_payload


def _group_metrics(
    frames: Sequence[Mapping[str, Any]],
    results: Mapping[str, DetectionResult],
    field: str,
) -> list[dict[str, Any]]:
    groups: dict[str, list[tuple[Mapping[str, Any], DetectionResult]]] = defaultdict(
        list
    )
    for frame in frames:
        groups[str(frame[field])].append((frame, results[frame["frame_id"]]))
    return [
        {field: value, **_confusion(paired)} for value, paired in sorted(groups.items())
    ]


def _software_hashes(repository: Path) -> dict[str, str]:
    paths = (
        "src/mineocclude/vision/magenta.py",
        "src/mineocclude/vision/detection_records.py",
        "src/mineocclude/vision/phase3_detector_candidate.py",
        "scripts/evaluate_magenta_detector.py",
        "scripts/build_person_e_phase3_detector_candidate.py",
    )
    return {
        path: hash_file_bytes(repository / path)
        for path in paths
        if (repository / path).is_file()
    }


def build_candidate_evidence(
    repository: Path | str,
    *,
    freeze_timestamp_utc: str,
) -> dict[str, bytes]:
    """Build the full evidence bundle in memory without opening a test set."""

    root = Path(repository).resolve()
    _require_repository_preconditions(root)
    historical_hashes = _historical_evidence_hashes(root)
    frames, source_binding = _development_frames(root)
    candidate_records, results_by_candidate = _evaluate_candidates(root, frames)
    selected = _selected_candidate(candidate_records)
    if selected["candidate_id"] != "phase3_v1_min_area_19":
        raise CandidateFreezeError(
            "The narrowly justified candidate selection changed."
        )
    config, config_hash, settings_hash, implementation_hash = _candidate_configuration(
        repository=root, selected=selected, frames=frames
    )
    version_record = _version_record(
        selected=selected,
        config_sha256=config_hash,
        settings_sha256=settings_hash,
        implementation_sha256=implementation_hash,
        freeze_timestamp_utc=freeze_timestamp_utc,
        development_source_manifest_sha256=source_binding["source_document_sha256"],
    )
    selected_results = results_by_candidate[selected["candidate_id"]]
    records = sort_detection_records(
        [
            _development_record(
                frame,
                selected_results[frame["frame_id"]],
                version_record=version_record,
            )
            for frame in frames
        ]
    )
    schema = detection_arrow_schema(
        detector_version=version_record["detector_version"],
        detector_config_sha256=config_hash,
        detector_settings_sha256=settings_hash,
        detector_implementation_sha256=implementation_hash,
        person_c_source_revision=PERSON_C_DEVELOPMENT_SOURCE_REVISION,
    )
    parquet_payload = detection_parquet_bytes(records, schema=schema)
    if read_detection_parquet_bytes(parquet_payload, schema=schema) != records:
        raise CandidateFreezeError("Parquet semantic read-back changed records.")

    paired = [(frame, selected_results[frame["frame_id"]]) for frame in frames]
    false_positives, false_negatives = _failure_inventory(paired)
    reason_counts = Counter(
        result.rejection_reason
        for _, result in paired
        if result.rejection_reason is not None
    )
    source_hashes = sorted({frame["source_frame_hash"] for frame in frames})
    reclassification_receipt = {
        "schema_version": "1.0",
        "reclassification_schema_version": (
            "person-e-phase3-development-reclassification-v1.0"
        ),
        "decision": (
            "All historical Phase 2 calibration and held-out frames are retired "
            "from untouched-test status and may be used only as development data."
        ),
        "historical_phase2_evidence_rewritten": False,
        "historical_phase2_roles_preserved_per_frame": True,
        "current_split_role": "development",
        "untouched_test_claim_permitted": False,
        "frame_count": len(frames),
        "original_role_counts": dict(
            sorted(
                Counter(
                    frame["historical_phase2_split_role"] for frame in frames
                ).items()
            )
        ),
        "truth_counts": {
            "negative": sum(not frame["truth_present"] for frame in frames),
            "positive": sum(frame["truth_present"] for frame in frames),
        },
        "unique_source_sha256": source_hashes,
        "person_c_source_revision": PERSON_C_DEVELOPMENT_SOURCE_REVISION,
        "source_binding": source_binding,
        "frames": [
            {
                key: frame[key]
                for key in (
                    "frame_id",
                    "trajectory_id",
                    "model_frame_idx",
                    "source_artifact_id",
                    "source_frame_idx",
                    "layout_id",
                    "canonical_camera_pose_id",
                    "resolution_id",
                    "image_width_px",
                    "image_height_px",
                    "pixel_format",
                    "image_coordinate_system",
                    "split_role",
                    "historical_phase2_split_role",
                    "truth_present",
                    "image_region",
                    "background_stratum",
                    "background_stratum_status",
                    "source_git_path",
                    "source_git_revision",
                    "source_frame_hash",
                    "decoded_rgb_hash",
                )
            }
            for frame in frames
        ],
    }
    candidate_selection = {
        "schema_version": "1.0",
        "candidate_selection_schema_version": (
            "person-e-phase3-detector-candidate-selection-v1.0"
        ),
        "evaluation_role": "development",
        "formal_test_gate_result": None,
        "future_test_data_used": False,
        "u4_results_used": False,
        "candidate_count": len(candidate_records),
        "candidate_order": [
            candidate["candidate_id"] for candidate in candidate_records
        ],
        "selection_objective": (
            "maximize development true positives, minimize false positives and "
            "false negatives, then minimize parameter changes and preserve "
            "declared candidate order"
        ),
        "evaluation_method": (
            "Exact min-area monotonic reuse: evaluate 19 pixels once per unique "
            "source byte hash and rerun the unchanged 20-pixel detector for each "
            "selected boundary component of area exactly 19."
        ),
        "candidates": candidate_records,
        "selected_candidate_id": selected["candidate_id"],
        "selected_candidate_is_formal_gate_result": False,
    }
    performance_report = {
        "schema_version": "1.0",
        "development_report_schema_version": (
            "person-e-phase3-detector-development-report-v1.0"
        ),
        "evaluation_role": "development",
        "formal_untouched_test_evaluation": False,
        "formal_precision_recall_gate_evaluated": False,
        "detector_version": version_record["detector_version"],
        "record_count": len(records),
        "metrics": _confusion(paired),
        "per_layout": _group_metrics(frames, selected_results, "layout_id"),
        "per_image_region": _group_metrics(frames, selected_results, "image_region"),
        "false_positives": false_positives,
        "false_negatives": false_negatives,
        "reason_counts": {
            str(reason): count for reason, count in sorted(reason_counts.items())
        },
        "rejected_frame_count": sum(
            result.status == "rejected" for _, result in paired
        ),
        "background_strata": {
            "status": "unavailable_owner_authored",
            "available_record_count": 0,
            "unavailable_record_count": len(records),
            "disclosure": (
                "Person C did not author marker/wall/background strata for this "
                "historical population. Person E does not infer or invent them."
            ),
        },
        "confidence_intervals": {
            "status": "not_reported",
            "reason": "no_repository_approved_versioned_method",
        },
        "limitations": [
            "The entire population is development data.",
            "Development precision and recall are not the Phase 3 formal gate.",
            "No owner-authored background strata are available.",
            "A new post-freeze untouched Person C test package is required.",
        ],
    }
    schema_record = arrow_schema_record(schema)
    parquet_hash = _sha256(parquet_payload)
    parquet_record = {
        "schema_version": "1.0",
        "parquet_writer_record_schema_version": (
            "person-e-phase3-detection-parquet-writer-v1.0"
        ),
        "engine": "pyarrow",
        "pyarrow_version": PYARROW_VERSION,
        "person_a_parquet_authority_revision": (PERSON_A_PARQUET_AUTHORITY_REVISION),
        "pandas_required_for_writing": False,
        "pickle_used": False,
        "custom_binary_format_used": False,
        "writer_settings": PARQUET_WRITER_SETTINGS,
        "column_order": schema.names,
        "row_ordering_key": ["layout_id", "frame_id"],
        "row_count": len(records),
        "semantic_readback_equal": True,
        "parquet_sha256": parquet_hash,
        "unsupported_object_policy": "reject_fail_closed",
        "nan_and_infinity_policy": "reject_fail_closed",
        "unavailable_value_policy": "schema_nullable_fields_only",
    }
    chronology = {
        "schema_version": "1.0",
        "chronology_schema_version": (
            "person-e-phase3-detector-freeze-chronology-v1.0"
        ),
        "freeze_timestamp_utc": freeze_timestamp_utc,
        "freeze_timestamp_policy": version_record["freeze_timestamp_policy"],
        "historical_phase2_heldout_untouched_status": "retired",
        "historical_population_current_role": "development",
        "historical_evidence_rewritten": False,
        "future_test_requirement": (
            "Person C must create and commit a new non-overlapping test package "
            "after this frozen candidate is committed."
        ),
        "future_test_tuning_forbidden": True,
        "future_test_outcome_disclosure_before_one_shot_record_forbidden": True,
        "u4_result_content_inspected": False,
        "new_untouched_test_bytes_inspected": False,
    }
    new_test_requirements = {
        "schema_version": "1.0",
        "untouched_test_requirements_schema_version": (
            "person-e-phase3-new-untouched-test-requirements-v1.0"
        ),
        "owner": "Person C",
        "consumer": "Person E",
        "required_after_detector_version": version_record["detector_version"],
        "required_after_freeze_timestamp_utc": freeze_timestamp_utc,
        "requirements": [
            "Image bytes produced after the frozen Person E candidate commit.",
            "No overlap with development images, capture episodes, or SHA-256 hashes.",
            "Immutable literal source-byte SHA-256 hashes.",
            "Owner-authored binary positive and negative truth labels.",
            "One immutable test-only manifest with explicit frame identities.",
            "Layout and canonical camera-pose identities.",
            "Image width, height, pixel format, and coordinate convention.",
            "Owner-authored image-region and marker/wall/background strata.",
            "Enough positive and negative cases to make both precision and recall gates meaningful.",
            "No detector outcomes disclosed before Person E records the one-shot evaluation.",
            "A clean committed and pushed Person C source revision.",
            "An explicit statement that the package was created after the frozen E candidate.",
        ],
        "forbidden_development_source_sha256": source_hashes,
        "test_mode_safeguards": {
            "candidate_comparison_forbidden": True,
            "detector_tuning_forbidden": True,
            "exact_frozen_detector_required": True,
            "missing_duplicate_or_extra_frame_behavior": "reject_fail_closed",
            "overwrite_forbidden": True,
            "partial_evaluation_forbidden": True,
            "source_revision_must_differ": True,
            "source_commit_must_postdate_freeze": True,
        },
    }
    phase3_status = {
        "schema_version": "1.0",
        "phase3_status_schema_version": "person-e-phase3-status-v0.1",
        "phase_3_status": "INCOMPLETE",
        "step_3_1_status": "AWAITING_NEW_UNTOUCHED_TEST",
        "step_3_1_pass_claimed": False,
        "development_metrics_are_formal_gate_result": False,
        "step_3_2_status": "INCOMPLETE_NOT_MODIFIED",
        "step_3_3_status": "BLOCKED_OWNER_CONTRACTS_NOT_MODIFIED",
        "remaining_step_3_1_blocker": (
            "A new, non-overlapping Person C test package produced after the "
            "candidate freeze must undergo one immutable one-shot evaluation."
        ),
    }
    freeze_receipt = {
        "schema_version": "1.0",
        "candidate_freeze_receipt_schema_version": (
            "person-e-phase3-detector-candidate-freeze-receipt-v1.0"
        ),
        "candidate_frozen": True,
        "detector_version": version_record["detector_version"],
        "detector_parameters_changed": True,
        "changed_parameter_count": 1,
        "changed_parameters": selected["parameter_changes_from_historical_v0_1"],
        "historical_detector_version": HISTORICAL_DETECTOR_VERSION,
        "development_source_revision": PERSON_C_DEVELOPMENT_SOURCE_REVISION,
        "person_a_parquet_authority_revision": (PERSON_A_PARQUET_AUTHORITY_REVISION),
        "person_e_source_base_revision": PERSON_E_REQUIRED_BASE_REVISION,
        "implementation_sha256": implementation_hash,
        "config_sha256": config_hash,
        "settings_sha256": settings_hash,
        "development_detections_parquet_sha256": parquet_hash,
        "phase1_and_phase2_evidence_immutable": True,
        "dependency_files_changed": False,
        "u4_result_content_inspected": False,
        "new_untouched_test_bytes_inspected": False,
        "step_3_1_pass_claimed": False,
    }

    documents: dict[str, Any] = {
        "detector_candidate_config.json": config,
        "detector_candidate_version_record.json": version_record,
        "development_reclassification_receipt.json": reclassification_receipt,
        "candidate_selection_record.json": candidate_selection,
        "development_performance_report.json": performance_report,
        "detections_schema.json": schema_record,
        "parquet_writer_record.json": parquet_record,
        "freeze_chronology_receipt.json": chronology,
        "new_untouched_test_requirements.json": new_test_requirements,
        "phase3_status.json": phase3_status,
        "candidate_freeze_receipt.json": freeze_receipt,
    }
    core_payloads = {
        name: formatted_json_bytes(document) for name, document in documents.items()
    }
    core_payloads["development_detections.parquet"] = parquet_payload
    first_hashes = {
        name: _sha256(payload) for name, payload in sorted(core_payloads.items())
    }
    second_payloads = {
        name: (
            bytes(payload)
            if name.endswith(".parquet")
            else formatted_json_bytes(json.loads(payload.decode("utf-8")))
        )
        for name, payload in core_payloads.items()
    }
    second_hashes = {
        name: _sha256(payload) for name, payload in sorted(second_payloads.items())
    }
    if core_payloads != second_payloads:
        raise CandidateFreezeError("Independent core serialization changed bytes.")
    deterministic = {
        "schema_version": "1.0",
        "deterministic_generation_schema_version": (
            "person-e-phase3-detector-candidate-determinism-v1.0"
        ),
        "generation_labels": [
            "independent_serialization_a",
            "independent_serialization_b",
        ],
        "byte_identical": True,
        "json_byte_identical": True,
        "parquet_byte_identical": True,
        "parquet_semantic_readback_equal": True,
        "first_generation_sha256": first_hashes,
        "second_generation_sha256": second_hashes,
        "full_bundle_external_regeneration_required": True,
    }
    core_payloads["deterministic_generation.json"] = formatted_json_bytes(deterministic)
    direct_inputs = {
        "detector_candidate_config.json": [
            "src/mineocclude/vision/magenta.py",
            SOURCE_VALIDATION_PATH,
        ],
        "detector_candidate_version_record.json": ["detector_candidate_config.json"],
        "development_reclassification_receipt.json": [
            SOURCE_VALIDATION_PATH,
            GROUND_CONTACT_PATH,
        ],
        "candidate_selection_record.json": [
            "development_reclassification_receipt.json"
        ],
        "development_performance_report.json": [
            "candidate_selection_record.json",
            "detector_candidate_version_record.json",
        ],
        "development_detections.parquet": [
            "detector_candidate_version_record.json",
            "development_reclassification_receipt.json",
        ],
        "detections_schema.json": ["src/mineocclude/vision/detection_records.py"],
        "parquet_writer_record.json": [
            "detections_schema.json",
            "development_detections.parquet",
        ],
        "freeze_chronology_receipt.json": ["development_reclassification_receipt.json"],
        "new_untouched_test_requirements.json": [
            "detector_candidate_version_record.json"
        ],
        "phase3_status.json": [
            "development_performance_report.json",
            "new_untouched_test_requirements.json",
        ],
        "candidate_freeze_receipt.json": [
            "detector_candidate_version_record.json",
            "parquet_writer_record.json",
            "phase3_status.json",
        ],
        "deterministic_generation.json": sorted(core_payloads),
    }
    provenance = {
        "schema_version": "1.0",
        "provenance_index_schema_version": (
            "person-e-phase3-detector-candidate-provenance-v1.0"
        ),
        "person_e_source_base_revision": PERSON_E_REQUIRED_BASE_REVISION,
        "person_c_development_source_revision": (PERSON_C_DEVELOPMENT_SOURCE_REVISION),
        "person_a_parquet_authority_revision": (PERSON_A_PARQUET_AUTHORITY_REVISION),
        "software_sha256": _software_hashes(root),
        "historical_phase1_phase2_evidence_sha256": historical_hashes,
        "records": [
            {
                "artifact_id": f"{EVIDENCE_ROOT_NAME}:{name}",
                "path": name,
                "sha256": _sha256(payload),
                "size_bytes": len(payload),
                "status": "candidate_freeze_evidence",
                "direct_inputs": direct_inputs[name],
            }
            for name, payload in sorted(core_payloads.items())
        ],
    }
    core_payloads["provenance_index.json"] = formatted_json_bytes(provenance)
    return core_payloads


def write_candidate_evidence(
    output_directory: Path | str,
    payloads: Mapping[str, bytes],
) -> None:
    """Publish a complete evidence directory without overwriting artifacts."""

    destination = Path(output_directory)
    if destination.exists() and any(destination.iterdir()):
        raise CandidateFreezeError(
            f"Refusing to overwrite non-empty evidence directory: {destination}"
        )
    for name, payload in sorted(payloads.items()):
        write_bytes_exclusive(destination / name, payload)
