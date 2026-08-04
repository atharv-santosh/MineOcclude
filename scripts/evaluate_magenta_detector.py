"""Evaluate one versioned HSV detector on a validated calibration split."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mineocclude.experiments.registry import (
    ProvenanceError,
    hash_file_bytes,
    hash_json_value,
    load_json_with_sha256,
    write_bytes_exclusive,
    write_json_exclusive,
)
from mineocclude.vision.calibration import (
    CALIBRATION_SPLITS,
    FROZEN_DETECTOR_CALIBRATION_SCHEMA_VERSION,
    frames_for_split,
    load_committed_frame_rgb,
    load_detector_calibration_dataset,
)
from mineocclude.vision.config import (
    PersonEConfigError,
    validate_person_e_config,
)
from mineocclude.vision.detection_records import (
    validate_test_evaluation_request,
)
from mineocclude.vision.magenta import (
    CALIBRATION_DETECTION_DOCUMENT_SCHEMA_VERSION,
    DETECTOR_ALGORITHM_VERSION,
    HsvRange,
    PresenceMetrics,
    detect_magenta,
    evaluate_presence,
    validate_detection_document,
)
from mineocclude.vision.phase3_detector_candidate import (
    PERSON_C_DEVELOPMENT_SOURCE_REVISION,
    evaluate_frozen_candidate_records,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate declared HSV settings on one validated calibration or "
            "held-out split. Never tune settings on held-out or U4 outcomes."
        )
    )
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument(
        "--split",
        choices=tuple(sorted(CALIBRATION_SPLITS)),
        help="Legacy Phase 2 split. Historical heldout is not an untouched test.",
    )
    parser.add_argument(
        "--evaluation-mode",
        choices=("development", "test"),
        help=(
            "Phase 3 frozen-candidate mode. Test requires an immutable manifest "
            "and explicit --one-shot-test."
        ),
    )
    parser.add_argument(
        "--hsv-range",
        action="append",
        nargs=6,
        type=float,
        metavar=("H_MIN", "H_MAX", "S_MIN", "S_MAX", "V_MIN", "V_MAX"),
        help="Repeat to declare multiple hue intervals under one detector version.",
    )
    parser.add_argument("--min-area", type=int)
    parser.add_argument("--max-area", type=int)
    parser.add_argument("--open-iterations", type=int)
    parser.add_argument("--close-iterations", type=int)
    parser.add_argument("--morphology-radius", type=int)
    parser.add_argument("--connectivity", type=int, choices=(4, 8))
    parser.add_argument(
        "--threshold-version",
        help="Unique detector-threshold version; filenames are not identity.",
    )
    parser.add_argument("--producer-run-id")
    parser.add_argument("--code-sha")
    parser.add_argument(
        "--calibration-report",
        type=Path,
        help="Required for heldout; settings are loaded from this calibration report.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        help="Validated Person E config whose literal bytes are recorded.",
    )
    parser.add_argument(
        "--detections-output",
        type=Path,
        help=(
            "Calibration-only authoritative detection document. Required when "
            "publishing real frozen-split evidence."
        ),
    )
    parser.add_argument(
        "--detections-parquet-output",
        type=Path,
        help="Required exact-schema Parquet output in Phase 3 evaluation mode.",
    )
    parser.add_argument("--frozen-candidate-config", type=Path)
    parser.add_argument("--frozen-candidate-version-record", type=Path)
    parser.add_argument("--development-reclassification-receipt", type=Path)
    parser.add_argument("--one-shot-test", action="store_true")
    parser.add_argument("--candidate-comparison", action="store_true")
    return parser.parse_args()


def _require_identifier(value: str, name: str) -> str:
    if (
        not value.strip()
        or value != value.strip()
        or any(character.isspace() for character in value)
    ):
        raise ValueError(f"{name} must be a non-empty identifier without whitespace.")
    return value


def _require_code_sha(value: str) -> str:
    if (
        len(value) != 40
        or value != value.lower()
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError("code_sha must be a full lowercase hexadecimal Git SHA.")
    return value


def _load_config_once(path: Path) -> tuple[dict[str, Any], str]:
    try:
        config, config_hash = load_json_with_sha256(path)
    except ProvenanceError as error:
        raise PersonEConfigError(
            f"Could not load Person E config {path}: {error}"
        ) from error
    if not isinstance(config, dict):
        raise PersonEConfigError("Person E config must contain one mapping.")
    validate_person_e_config(config)
    return config, config_hash


def _metrics_record(
    metrics: PresenceMetrics,
    *,
    split: str,
    minimum_precision: float,
    minimum_recall: float,
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "true_positive": metrics.true_positive,
        "false_positive": metrics.false_positive,
        "true_negative": metrics.true_negative,
        "false_negative": metrics.false_negative,
        "precision": metrics.precision,
        "recall": metrics.recall,
    }
    if split == "heldout":
        record["planning_gate_passed"] = (
            metrics.precision >= minimum_precision and metrics.recall >= minimum_recall
        )
    return record


def _layout_key(frame: Mapping[str, Any]) -> tuple[str, str]:
    return frame["layout_id"], frame["canonical_camera_pose_id"]


def _detector_settings(
    args: argparse.Namespace,
    *,
    threshold_version: str,
    dataset_hash: str,
    config_hash: str,
) -> tuple[dict[str, Any], str | None]:
    setting_arguments = (
        args.hsv_range,
        args.min_area,
        args.max_area,
        args.open_iterations,
        args.close_iterations,
        args.morphology_radius,
        args.connectivity,
    )
    if args.split == "calibration":
        if args.calibration_report is not None:
            raise ValueError("Calibration runs cannot consume a calibration report.")
        if args.hsv_range is None or args.min_area is None:
            raise ValueError("Calibration requires --hsv-range and --min-area.")
        return (
            {
                "threshold_version": threshold_version,
                "hsv_ranges": [list(values) for values in args.hsv_range],
                "min_area_pixels": args.min_area,
                "max_area_pixels": args.max_area,
                "open_iterations": (
                    0 if args.open_iterations is None else args.open_iterations
                ),
                "close_iterations": (
                    0 if args.close_iterations is None else args.close_iterations
                ),
                "morphology_radius_pixels": (
                    1 if args.morphology_radius is None else args.morphology_radius
                ),
                "connectivity": 8 if args.connectivity is None else args.connectivity,
            },
            None,
        )
    if args.calibration_report is None:
        raise ValueError("Heldout evaluation requires --calibration-report.")
    if any(value is not None for value in setting_arguments):
        raise ValueError("Heldout settings must come only from --calibration-report.")
    report, report_hash = load_json_with_sha256(args.calibration_report)
    if not isinstance(report, Mapping):
        raise TypeError("Calibration report must be a mapping.")
    if (
        report.get("detector_report_schema_version")
        not in {"person-e-detector-report-v0.2", "person-e-detector-report-v0.3"}
        or report.get("evaluation_split") != "calibration"
        or report.get("dataset_hash") != dataset_hash
        or report.get("config_hash") != config_hash
        or report.get("threshold_version") != threshold_version
    ):
        raise ValueError("Calibration report identity does not match heldout input.")
    settings = {
        field: report.get(field)
        for field in (
            "threshold_version",
            "hsv_ranges",
            "min_area_pixels",
            "max_area_pixels",
            "open_iterations",
            "close_iterations",
            "morphology_radius_pixels",
            "connectivity",
        )
    }
    if report.get("settings_hash") != hash_json_value(settings):
        raise ValueError("Calibration settings_hash does not match report settings.")
    return settings, report_hash


def _load_mapping(path: Path, name: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"Could not load {name}: {error}") from error
    if not isinstance(value, dict):
        raise TypeError(f"{name} must contain one mapping.")
    return value


def _development_frames(
    receipt: Mapping[str, Any],
) -> list[dict[str, Any]]:
    if (
        receipt.get("reclassification_schema_version")
        != "person-e-phase3-development-reclassification-v1.0"
        or receipt.get("current_split_role") != "development"
        or receipt.get("untouched_test_claim_permitted") is not False
        or receipt.get("person_c_source_revision")
        != PERSON_C_DEVELOPMENT_SOURCE_REVISION
    ):
        raise ValueError("Development reclassification receipt is invalid.")
    frames = receipt.get("frames")
    if not isinstance(frames, list) or len(frames) != receipt.get("frame_count"):
        raise ValueError("Development reclassification frame coverage is incomplete.")
    return [dict(frame) for frame in frames]


def _normalize_test_frames(
    frames: list[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    return [
        {
            **dict(frame),
            "source_git_path": frame["source_path"],
            "source_frame_hash": frame["source_sha256"],
            "historical_phase2_split_role": None,
            "split_role": "test",
        }
        for frame in frames
    ]


def _phase3_main(args: argparse.Namespace) -> None:
    required_paths = {
        "--frozen-candidate-config": args.frozen_candidate_config,
        "--frozen-candidate-version-record": (args.frozen_candidate_version_record),
        "--development-reclassification-receipt": (
            args.development_reclassification_receipt
        ),
        "--detections-parquet-output": args.detections_parquet_output,
    }
    missing = [name for name, value in required_paths.items() if value is None]
    if missing:
        raise ValueError(f"Phase 3 evaluation requires: {', '.join(missing)}.")
    if args.split is not None:
        raise ValueError("Phase 3 evaluation cannot also declare a Phase 2 split.")
    if args.detections_output is not None:
        raise ValueError("Phase 3 writes only --detections-parquet-output.")
    phase3_setting_overrides = {
        "--hsv-range": args.hsv_range,
        "--min-area": args.min_area,
        "--max-area": args.max_area,
        "--open-iterations": args.open_iterations,
        "--close-iterations": args.close_iterations,
        "--morphology-radius": args.morphology_radius,
        "--connectivity": args.connectivity,
        "--threshold-version": args.threshold_version,
        "--calibration-report": args.calibration_report,
        "--config": args.config,
    }
    requested_overrides = {
        name: value
        for name, value in phase3_setting_overrides.items()
        if value is not None
    }
    if args.evaluation_mode == "development" and requested_overrides:
        raise ValueError(
            "Frozen development evaluation rejects detector-setting overrides."
        )
    candidate_config = _load_mapping(
        args.frozen_candidate_config, "frozen candidate config"
    )
    candidate_version = _load_mapping(
        args.frozen_candidate_version_record,
        "frozen candidate version record",
    )
    reclassification = _load_mapping(
        args.development_reclassification_receipt,
        "development reclassification receipt",
    )
    development_frames = _development_frames(reclassification)
    if args.evaluation_mode == "development":
        if args.one_shot_test:
            raise ValueError("Development evaluation cannot use one-shot test mode.")
        manifest = _load_mapping(args.input, "development manifest")
        if manifest != reclassification:
            raise ValueError(
                "Development input must be the exact reclassification receipt."
            )
        frames = development_frames
        source_revision = PERSON_C_DEVELOPMENT_SOURCE_REVISION
    else:
        manifest = _load_mapping(args.input, "test manifest")
        test_frames = validate_test_evaluation_request(
            manifest,
            frozen_candidate=candidate_version,
            forbidden_development_hashes=reclassification["unique_source_sha256"],
            output_paths=(args.output, args.detections_parquet_output),
            one_shot_test=args.one_shot_test,
            candidate_comparison_requested=args.candidate_comparison,
            proposed_settings=requested_overrides or None,
        )
        frames = _normalize_test_frames(test_frames)
        source_revision = manifest["source_revision"]
    _, report, _, parquet_payload = evaluate_frozen_candidate_records(
        ROOT,
        frames=frames,
        candidate_config=candidate_config,
        candidate_version=candidate_version,
        split_role=args.evaluation_mode,
        person_c_source_revision=source_revision,
    )
    report.update(
        {
            "one_shot_test_mode": (
                args.evaluation_mode == "test" and args.one_shot_test
            ),
            "candidate_comparison_requested": args.candidate_comparison,
            "test_result_overwrite_forbidden": True,
            "tuning_permitted": args.evaluation_mode == "development",
        }
    )
    write_bytes_exclusive(args.detections_parquet_output, parquet_payload)
    write_json_exclusive(args.output, report)


def main() -> None:
    args = parse_args()
    if args.evaluation_mode is not None:
        _phase3_main(args)
        return
    legacy_required = {
        "--split": args.split,
        "--threshold-version": args.threshold_version,
        "--producer-run-id": args.producer_run_id,
        "--code-sha": args.code_sha,
        "--config": args.config,
    }
    missing = [name for name, value in legacy_required.items() if value is None]
    if missing:
        raise ValueError(f"Legacy evaluation requires: {', '.join(missing)}.")
    threshold_version = _require_identifier(args.threshold_version, "threshold_version")
    producer_run_id = _require_identifier(args.producer_run_id, "producer_run_id")
    code_sha = _require_code_sha(args.code_sha)
    dataset, dataset_hash = load_detector_calibration_dataset(args.input)
    config, config_hash = _load_config_once(args.config)
    frames = frames_for_split(dataset, args.split)
    settings, calibration_report_hash = _detector_settings(
        args,
        threshold_version=threshold_version,
        dataset_hash=dataset_hash,
        config_hash=config_hash,
    )
    thresholds = [HsvRange(*values) for values in settings["hsv_ranges"]]
    settings_hash = hash_json_value(settings)
    detector_identity_hash = hash_json_value(
        {
            "algorithm_version": DETECTOR_ALGORITHM_VERSION,
            "threshold_version": threshold_version,
            "settings_hash": settings_hash,
        }
    )
    detector_version = f"{DETECTOR_ALGORITHM_VERSION}:sha256:{detector_identity_hash}"

    output_rows: list[dict[str, Any]] = []
    source_contexts: list[dict[str, Any]] = []
    detection_records: list[dict[str, Any]] = []
    labeled_results = []
    by_layout: dict[tuple[str, str], list[tuple[bool, Any]]] = {}
    for frame in frames:
        rgb = frame.get("rgb")
        if rgb is None:
            rgb = load_committed_frame_rgb(frame, repository=ROOT)
        result = detect_magenta(
            rgb,
            hsv_ranges=thresholds,
            min_area_pixels=settings["min_area_pixels"],
            max_area_pixels=settings["max_area_pixels"],
            open_iterations=settings["open_iterations"],
            close_iterations=settings["close_iterations"],
            morphology_radius_pixels=settings["morphology_radius_pixels"],
            connectivity=settings["connectivity"],
        )
        truth_present = frame["truth_present"]
        labeled_results.append((truth_present, result))
        by_layout.setdefault(_layout_key(frame), []).append((truth_present, result))
        output_rows.append(
            {
                "frame_id": frame["frame_id"],
                "layout_id": frame["layout_id"],
                "canonical_camera_pose_id": frame["canonical_camera_pose_id"],
                "split": args.split,
                "truth_class": frame["truth_class"],
                "truth_present": truth_present,
                "source_artifact_id": frame["source_artifact_id"],
                "source_frame_idx": frame["source_frame_idx"],
                "source_frame_hash": frame["source_frame_hash"],
                "decoded_rgb_hash": frame["decoded_rgb_hash"],
                "detector_version": detector_version,
                "threshold_version": threshold_version,
                "presence": result.detected,
                "quality_status": "accepted",
                **result.to_record(),
            }
        )
        if (
            dataset["detector_calibration_schema_version"]
            == FROZEN_DETECTOR_CALIBRATION_SCHEMA_VERSION
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
                "canonical_camera_pose_id": frame["canonical_camera_pose_id"],
                "resolution_id": frame["resolution_id"],
                "image_width_px": frame["image_width_px"],
                "image_height_px": frame["image_height_px"],
                "pixel_format": frame["pixel_format"],
                "image_coordinate_system": "pixel_center_xy_zero_based",
                "truth_class": frame["truth_class"],
                "truth_present": frame["truth_present"],
                "frame_available": True,
            }
            source_contexts.append(context)
            detection_records.append(
                {
                    **{
                        field: value
                        for field, value in context.items()
                        if field != "frame_available"
                    },
                    "detection_id": (f"{detector_version}:{frame['frame_id']}"),
                    "detector_version": detector_version,
                    "threshold_version": threshold_version,
                    "status": result.status,
                    "presence": result.detected,
                    "centroid_xy": (
                        None if result.centroid_xy is None else list(result.centroid_xy)
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

    gate_config = config["detector"]["heldout_gates"]
    minimum_precision = float(gate_config["minimum_precision"])
    minimum_recall = float(gate_config["minimum_recall"])
    overall_metrics = _metrics_record(
        evaluate_presence(labeled_results),
        split=args.split,
        minimum_precision=minimum_precision,
        minimum_recall=minimum_recall,
    )
    per_layout_metrics = []
    for (layout_id, pose_id), results in sorted(by_layout.items()):
        per_layout_metrics.append(
            {
                "layout_id": layout_id,
                "canonical_camera_pose_id": pose_id,
                "sample_count": len(results),
                **_metrics_record(
                    evaluate_presence(results),
                    split=args.split,
                    minimum_precision=minimum_precision,
                    minimum_recall=minimum_recall,
                ),
            }
        )

    marker_sets = [
        {
            "layout_id": layout["layout_id"],
            "canonical_camera_pose_id": layout["canonical_camera_pose_id"],
            "marker_set_id": layout["marker_set_id"],
            "marker_set_source_hash": layout["marker_set_source_hash"],
        }
        for layout in dataset["layouts"]
    ]
    detection_document_hash = None
    if args.detections_output is not None:
        if args.split != "calibration":
            raise ValueError(
                "--detections-output is reserved for calibration-only evidence."
            )
        if not source_contexts:
            raise ValueError(
                "--detections-output requires the frozen calibration schema."
            )
        detection_document = {
            "schema_version": dataset["schema_version"],
            "detection_schema_version": (CALIBRATION_DETECTION_DOCUMENT_SCHEMA_VERSION),
            "document_id": (f"calibration_detections_{detector_identity_hash}"),
            "synthetic": False,
            "scientific_use": "permitted",
            "detector_version": detector_version,
            "threshold_version": threshold_version,
            "split_version": dataset["split_version"],
            "settings_hash": settings_hash,
            "source_contexts": source_contexts,
            "records": detection_records,
        }
        validate_detection_document(detection_document)
        write_json_exclusive(args.detections_output, detection_document)
        detection_document_hash = hash_file_bytes(args.detections_output)

    write_json_exclusive(
        args.output,
        {
            "detector_report_schema_version": "person-e-detector-report-v0.3",
            "schema_version": dataset["schema_version"],
            "dataset_id": dataset["dataset_id"],
            "detector_calibration_schema_version": dataset[
                "detector_calibration_schema_version"
            ],
            "dataset_hash": dataset_hash,
            "evaluation_split": args.split,
            "calibration_report_hash": calibration_report_hash,
            "producer_run_id": producer_run_id,
            "code_sha": code_sha,
            "config_schema_version": config["config_schema_version"],
            "config_instance_version": config["config_instance_version"],
            "config_hash": config_hash,
            "settings_hash": settings_hash,
            "detector_algorithm_version": DETECTOR_ALGORITHM_VERSION,
            "detector_version": detector_version,
            "detector_identity_hash": detector_identity_hash,
            "detection_document_hash": detection_document_hash,
            **settings,
            "heldout_gate": {
                "minimum_precision": minimum_precision,
                "minimum_recall": minimum_recall,
                "eligible": args.split == "heldout",
            },
            "metrics": overall_metrics,
            "per_layout_metrics": per_layout_metrics,
            "marker_sets": marker_sets,
            "rows": output_rows,
        },
    )


if __name__ == "__main__":
    main()
