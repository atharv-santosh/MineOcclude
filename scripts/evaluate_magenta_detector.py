"""Evaluate one versioned HSV detector on a validated calibration split."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mineocclude.experiments.registry import (  # noqa: E402
    ProvenanceError,
    hash_json_value,
    load_json_with_sha256,
    write_json_exclusive,
)
from mineocclude.vision.calibration import (  # noqa: E402
    CALIBRATION_SPLITS,
    frames_for_split,
    load_detector_calibration_dataset,
)
from mineocclude.vision.config import (  # noqa: E402
    PersonEConfigError,
    validate_person_e_config,
)
from mineocclude.vision.magenta import (  # noqa: E402
    HsvRange,
    PresenceMetrics,
    detect_magenta,
    evaluate_presence,
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
        required=True,
        help="Evaluation role; only heldout results can claim the planning gate.",
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
        required=True,
        help="Unique detector-threshold version; filenames are not identity.",
    )
    parser.add_argument("--producer-run-id", required=True)
    parser.add_argument("--code-sha", required=True)
    parser.add_argument(
        "--calibration-report",
        type=Path,
        help="Required for heldout; settings are loaded from this calibration report.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        required=True,
        help="Validated Person E config whose literal bytes are recorded.",
    )
    return parser.parse_args()


def _require_identifier(value: str, name: str) -> str:
    if not value.strip() or value != value.strip() or any(
        character.isspace() for character in value
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
            metrics.precision >= minimum_precision
            and metrics.recall >= minimum_recall
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
        raise ValueError("Calibration report must be a mapping.")
    if (
        report.get("detector_report_schema_version")
        != "person-e-detector-report-v0.2"
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


def main() -> None:
    args = parse_args()
    threshold_version = _require_identifier(
        args.threshold_version, "threshold_version"
    )
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
            "threshold_version": threshold_version,
            "settings_hash": settings_hash,
        }
    )

    output_rows: list[dict[str, Any]] = []
    labeled_results = []
    by_layout: dict[tuple[str, str], list[tuple[bool, Any]]] = {}
    for frame in frames:
        result = detect_magenta(
            frame["rgb"],
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
                "threshold_version": threshold_version,
                **result.to_record(),
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
    write_json_exclusive(
        args.output,
        {
            "detector_report_schema_version": "person-e-detector-report-v0.2",
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
            "detector_identity_hash": detector_identity_hash,
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
