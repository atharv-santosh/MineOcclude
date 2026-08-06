"""Run the frozen detector and homography on decoded U4 rollout frames."""

from __future__ import annotations

import argparse
import math
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mineocclude.analysis.manifests import is_hex_digest  # noqa: E402
from mineocclude.experiments.registry import (  # noqa: E402
    RegistryIndex,
    hash_json_value,
    load_json_with_sha256,
    write_json_exclusive,
)
from mineocclude.vision.config import (  # noqa: E402
    DEFAULT_PERSON_E_CONFIG_PATH,
    hash_person_e_config,
    require_live_ready_person_e_config,
)
from mineocclude.vision.homography import (  # noqa: E402
    HOMOGRAPHY_ALGORITHM_VERSION,
    HOMOGRAPHY_REPORT_SCHEMA_VERSION,
    homography_from_record,
    summarize_localization,
)
from mineocclude.vision.magenta import HsvRange, detect_magenta  # noqa: E402
from mineocclude.vision.measurement import (  # noqa: E402
    EVIDENCE_INPUT_SCHEMA_VERSION,
)


U4_FRAME_INPUT_SCHEMA_VERSION = "person-e-u4-frame-input-v0.1"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create versioned localization evidence from decoded U4 RGB frames."
    )
    parser.add_argument("input", type=Path)
    parser.add_argument("homography_report", type=Path)
    parser.add_argument("rollout_manifest", type=Path)
    parser.add_argument("registry", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--config", type=Path, default=DEFAULT_PERSON_E_CONFIG_PATH)
    parser.add_argument("--run-id", required=True)
    return parser.parse_args()


def _mapping(value: object, name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be a mapping.")
    return value


def _pair(value: object, name: str) -> tuple[float, float]:
    if (
        not isinstance(value, Sequence)
        or isinstance(value, (str, bytes))
        or len(value) != 2
        or any(
            not isinstance(item, (int, float))
            or isinstance(item, bool)
            or not math.isfinite(float(item))
            for item in value
        )
    ):
        raise ValueError(f"{name} must contain two finite numbers.")
    return float(value[0]), float(value[1])


def _wall_coordinate(
    world_xz: tuple[float, float],
    *,
    origin: tuple[float, float],
    positive_unit: tuple[float, float],
) -> float:
    norm = math.hypot(*positive_unit)
    if not math.isclose(norm, 1.0, rel_tol=0.0, abs_tol=1e-9):
        raise ValueError("Wall-parallel positive direction must be a unit vector.")
    return (
        (world_xz[0] - origin[0]) * positive_unit[0]
        + (world_xz[1] - origin[1]) * positive_unit[1]
    )


def main() -> None:
    args = parse_args()
    frame_document, frame_input_hash = load_json_with_sha256(args.input)
    homography_report, homography_report_hash = load_json_with_sha256(
        args.homography_report
    )
    rollout_manifest, _ = load_json_with_sha256(args.rollout_manifest)
    registry, _ = load_json_with_sha256(args.registry)
    frame_document = _mapping(frame_document, "U4 frame input")
    homography_report = _mapping(homography_report, "homography report")
    rollout_manifest = _mapping(rollout_manifest, "rollout manifest")
    registry = _mapping(registry, "registry")
    registry_index = RegistryIndex(rollout_manifest, registry)
    accepted_rollout_manifest_hash = hash_json_value(rollout_manifest)
    accepted_registry_hash = hash_json_value(registry)

    config = require_live_ready_person_e_config(args.config)
    config_hash = hash_person_e_config(args.config)
    producer_run = registry_index.require_completed_run(
        args.run_id,
        owner="person_e",
        config_hash=config_hash,
    )
    if (
        frame_document.get("u4_frame_input_schema_version")
        != U4_FRAME_INPUT_SCHEMA_VERSION
    ):
        raise ValueError("Unknown U4 frame-input schema version.")
    if (
        homography_report.get("homography_report_schema_version")
        != HOMOGRAPHY_REPORT_SCHEMA_VERSION
    ):
        raise ValueError("Unknown homography-report schema version.")
    if homography_report.get("config_hash") != config_hash:
        raise ValueError("Homography report was produced under a different config.")
    homography_config = config["homography"]
    report_settings = {
        "algorithm_version": HOMOGRAPHY_ALGORITHM_VERSION,
        "singular_pivot_tolerance": homography_config[
            "singular_pivot_tolerance"
        ],
        "maximum_median_wall_parallel_error_blocks": homography_config[
            "maximum_median_wall_parallel_error_blocks"
        ],
        "maximum_p95_wall_parallel_error_blocks": homography_config[
            "maximum_p95_wall_parallel_error_blocks"
        ],
        "minimum_shift_error_multiplier_on_gate_failure": homography_config[
            "minimum_shift_error_multiplier_on_gate_failure"
        ],
    }
    if homography_report.get("settings_hash") != hash_json_value(report_settings):
        raise ValueError("Homography settings_hash does not match the live config.")

    report_layouts = homography_report.get("layouts")
    if not isinstance(report_layouts, list) or not report_layouts:
        raise ValueError("Homography report requires layouts.")
    homographies: dict[tuple[str, str], tuple[object, Mapping[str, object]]] = {}
    for raw_layout in report_layouts:
        layout = _mapping(raw_layout, "homography layout")
        key = (str(layout.get("layout_id")), str(layout.get("canonical_camera_pose_id")))
        if key in homographies:
            raise ValueError("Duplicate homography layout/pose identity.")
        heldout = _mapping(layout.get("heldout_localization"), "heldout localization")
        homography = homography_from_record(
            _mapping(layout.get("homography"), "homography")
        )
        heldout_records = heldout.get("records")
        if (
            not isinstance(heldout_records, list)
            or not heldout_records
            or any(not isinstance(record, Mapping) for record in heldout_records)
        ):
            raise ValueError("Homography held-out report requires records.")
        recomputed = summarize_localization(
            homography,
            [
                (record["image_xy"], record["true_world_xz"])
                for record in heldout_records
            ],
            wall_parallel_origin_xz=layout.get("wall_parallel_origin_xz"),
            wall_parallel_positive_unit_xz=layout.get(
                "wall_parallel_positive_unit_xz"
            ),
            image_regions=[record.get("image_region") for record in heldout_records],
            maximum_median_wall_error_blocks=float(
                homography_config[
                    "maximum_median_wall_parallel_error_blocks"
                ]
            ),
            maximum_p95_wall_error_blocks=float(
                homography_config["maximum_p95_wall_parallel_error_blocks"]
            ),
            minimum_shift_error_multiplier=float(
                homography_config[
                    "minimum_shift_error_multiplier_on_gate_failure"
                ]
            ),
        )
        if hash_json_value(recomputed) != hash_json_value(heldout):
            raise ValueError("Homography held-out report does not recompute exactly.")
        if recomputed["planning_gate_passed"] is not True:
            raise ValueError(f"Homography {key!r} did not pass the planning gate.")
        homographies[key] = (
            homography,
            layout,
        )

    rollout_rows = rollout_manifest.get("rollout_rows")
    if not isinstance(rollout_rows, list):
        raise ValueError("Validated manifest unexpectedly lacks rollout rows.")
    rollout_by_id = {row["rollout_id"]: row for row in rollout_rows}
    frames = frame_document.get("frames")
    if not isinstance(frames, list) or not frames:
        raise ValueError("U4 frame input requires a non-empty frames list.")

    detector = config["detector"]
    thresholds = [
        HsvRange(
            hsv["h_min"],
            hsv["h_max"],
            hsv["s_min"],
            hsv["s_max"],
            hsv["v_min"],
            hsv["v_max"],
        )
        for hsv in detector["hsv_ranges"]
    ]
    morphology = detector["morphology"]
    blob = detector["blob"]
    grouped: dict[str, dict[str, object]] = {}
    seen_frame_keys: set[tuple[str, int]] = set()
    for index, raw_frame in enumerate(frames):
        frame = _mapping(raw_frame, f"frames[{index}]")
        required = {
            "rollout_id",
            "reveal_frame_idx",
            "frame_idx",
            "layout_id",
            "canonical_camera_pose_id",
            "source_frame_hash",
            "decoded_rgb_hash",
            "rgb",
        }
        missing = required - set(frame)
        if missing:
            raise ValueError(f"Frame {index} is missing: {', '.join(sorted(missing))}.")
        rollout_id = frame["rollout_id"]
        if not isinstance(rollout_id, str) or rollout_id not in rollout_by_id:
            raise ValueError("Frame rollout_id is outside the accepted manifest.")
        rollout = rollout_by_id[rollout_id]
        if frame["layout_id"] != rollout["layout_id"]:
            raise ValueError("Frame layout_id differs from rollout manifest.")
        frame_idx = frame["frame_idx"]
        if not isinstance(frame_idx, int) or isinstance(frame_idx, bool) or frame_idx < 0:
            raise ValueError("frame_idx must be a non-negative integer.")
        key = (rollout_id, frame_idx)
        if key in seen_frame_keys:
            raise ValueError("Rollout/frame identities must be unique.")
        seen_frame_keys.add(key)
        for field in ("source_frame_hash", "decoded_rgb_hash"):
            if not is_hex_digest(frame[field], 64):
                raise ValueError(f"{field} must be SHA-256.")
        if frame["decoded_rgb_hash"] != hash_json_value(frame["rgb"]):
            raise ValueError("decoded_rgb_hash does not match decoded RGB values.")
        pose_id = frame["canonical_camera_pose_id"]
        homography_key = (str(frame["layout_id"]), str(pose_id))
        if homography_key not in homographies:
            raise ValueError("Frame references an unqualified homography layout/pose.")
        homography, layout_report = homographies[homography_key]
        result = detect_magenta(
            frame["rgb"],
            hsv_ranges=thresholds,
            min_area_pixels=blob["min_area_pixels"],
            max_area_pixels=blob["max_area_pixels"],
            open_iterations=morphology["open_iterations"],
            close_iterations=morphology["close_iterations"],
            morphology_radius_pixels=morphology["radius_pixels"],
            connectivity=blob["connectivity"],
        )
        world_coordinate = None
        if result.detected:
            if result.centroid_xy is None:
                raise ValueError("Detected blob unexpectedly lacks a centroid.")
            world_xz = homography.transform(result.centroid_xy)
            world_coordinate = _wall_coordinate(
                world_xz,
                origin=_pair(layout_report["wall_parallel_origin_xz"], "origin"),
                positive_unit=_pair(
                    layout_report["wall_parallel_positive_unit_xz"],
                    "positive direction",
                ),
            )
        localization = {
            "frame_idx": frame_idx,
            "wall_parallel_blocks": world_coordinate,
            "detection_valid": result.detected,
            "bounding_box_xyxy": (
                None
                if result.bounding_box_xyxy is None
                else list(result.bounding_box_xyxy)
            ),
            "rejection_reason": result.rejection_reason,
            "source_frame_hash": frame["source_frame_hash"],
            "detector_result_hash": hash_json_value(
                {
                    "detector": result.to_record(),
                    "homography_version_id": homography.to_record()[
                        "homography_version_id"
                    ],
                    "wall_parallel_blocks": world_coordinate,
                }
            ),
        }
        group = grouped.setdefault(
            rollout_id,
            {
                "rollout_id": rollout_id,
                "reveal_frame_idx": frame["reveal_frame_idx"],
                "layout_id": frame["layout_id"],
                "canonical_camera_pose_id": pose_id,
                "detector_report_hash": detector["heldout_report_hash"],
                "detector_version": detector["threshold_version"],
                "homography_report_hash": homography_report_hash,
                "homography_version_id": homography.to_record()[
                    "homography_version_id"
                ],
                "localizations": [],
                "ssim": None,
            },
        )
        for field in (
            "reveal_frame_idx",
            "layout_id",
            "canonical_camera_pose_id",
            "homography_version_id",
        ):
            expected = (
                homography.to_record()["homography_version_id"]
                if field == "homography_version_id"
                else frame[field]
            )
            if group[field] != expected:
                raise ValueError(f"Rollout frames disagree on {field}.")
        group["localizations"].append(localization)

    for group in grouped.values():
        group["localizations"].sort(key=lambda row: row["frame_idx"])
    write_json_exclusive(
        args.output,
        {
            "measurement_evidence_input_schema_version": EVIDENCE_INPUT_SCHEMA_VERSION,
            "localization_report_schema_version": "person-e-localization-report-v0.1",
            "frame_input_hash": frame_input_hash,
            "homography_report_hash": homography_report_hash,
            "accepted_rollout_manifest_hash": accepted_rollout_manifest_hash,
            "accepted_registry_hash": accepted_registry_hash,
            "producer_run_id": args.run_id,
            "code_sha": producer_run["code_sha"],
            "config_hash": config_hash,
            "rows": [grouped[rollout_id] for rollout_id in sorted(grouped)],
        },
    )


if __name__ == "__main__":
    main()
