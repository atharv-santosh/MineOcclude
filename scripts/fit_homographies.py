"""Fit config-governed four-marker homographies and held-out QA reports."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Mapping
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mineocclude.analysis.manifests import is_hex_digest
from mineocclude.experiments.registry import (
    hash_json_value,
    load_json_with_sha256,
    write_json_exclusive,
)
from mineocclude.vision.config import validate_person_e_config
from mineocclude.vision.homography import (
    HOMOGRAPHY_ALGORITHM_VERSION,
    HOMOGRAPHY_REPORT_SCHEMA_VERSION,
    fit_marker_homography,
    summarize_localization,
)

HOMOGRAPHY_INPUT_SCHEMA_VERSION = "person-e-homography-input-v0.1"
BOUND_HOMOGRAPHY_INPUT_SCHEMA_VERSION = "person-e-homography-input-v0.2"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fit per-layout homographies and report held-out error."
    )
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--producer-run-id", required=True)
    parser.add_argument("--code-sha", required=True)
    return parser.parse_args()


def _identifier(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(f"{name} must be a non-empty trimmed string.")
    return value


def _sha256(value: object, name: str) -> str:
    if not is_hex_digest(value, 64):
        raise ValueError(f"{name} must be SHA-256.")
    return str(value)


def main() -> None:
    args = parse_args()
    document, input_hash = load_json_with_sha256(args.input)
    config, config_hash = load_json_with_sha256(args.config)
    if not isinstance(config, dict):
        raise ValueError("Person E config must be a mapping.")
    validate_person_e_config(config)
    if not isinstance(document, Mapping):
        raise ValueError("Homography input must be a mapping.")
    input_schema_version = document.get("homography_input_schema_version")
    if input_schema_version not in {
        HOMOGRAPHY_INPUT_SCHEMA_VERSION,
        BOUND_HOMOGRAPHY_INPUT_SCHEMA_VERSION,
    }:
        raise ValueError("Unknown homography-input schema version.")
    layouts = document.get("layouts")
    if not isinstance(layouts, list) or not layouts:
        raise ValueError("Input must contain a non-empty layouts list.")
    producer_run_id = _identifier(args.producer_run_id, "producer_run_id")
    if not is_hex_digest(args.code_sha, 40):
        raise ValueError("code_sha must be a full hexadecimal Git SHA.")

    homography_config = config["homography"]
    settings = {
        "algorithm_version": HOMOGRAPHY_ALGORITHM_VERSION,
        "singular_pivot_tolerance": homography_config["singular_pivot_tolerance"],
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
    output_rows = []
    seen_layout_ids: set[str] = set()
    for index, raw_layout in enumerate(layouts):
        if not isinstance(raw_layout, Mapping):
            raise ValueError(f"Layout {index} must be a mapping.")
        layout_id = _identifier(raw_layout.get("layout_id"), "layout_id")
        pose_id = _identifier(
            raw_layout.get("canonical_camera_pose_id"),
            "canonical_camera_pose_id",
        )
        if layout_id in seen_layout_ids:
            raise ValueError("layout_id values must be unique.")
        seen_layout_ids.add(layout_id)
        marker_source_hash = _sha256(
            raw_layout.get("marker_set_source_hash"), "marker_set_source_hash"
        )
        validation_source_hash = _sha256(
            raw_layout.get("validation_source_hash"), "validation_source_hash"
        )
        binding: dict[str, object] = {}
        if input_schema_version == BOUND_HOMOGRAPHY_INPUT_SCHEMA_VERSION:
            binding = {
                "resolution_id": _identifier(
                    raw_layout.get("resolution_id"), "resolution_id"
                ),
                "image_width_px": raw_layout.get("image_width_px"),
                "image_height_px": raw_layout.get("image_height_px"),
                "source_correspondence_hash": marker_source_hash,
                "detector_version": _identifier(
                    raw_layout.get("detector_version"), "detector_version"
                ),
                "software_runtime_hash": _sha256(
                    raw_layout.get("software_runtime_hash"),
                    "software_runtime_hash",
                ),
            }
        homography = fit_marker_homography(
            raw_layout.get("image_points_by_marker"),
            raw_layout.get("world_points_by_marker"),
            marker_ids=raw_layout.get("marker_ids"),
            layout_id=layout_id,
            canonical_camera_pose_id=pose_id,
            pivot_tolerance=float(settings["singular_pivot_tolerance"]),
            **binding,
        )
        pairs = raw_layout.get("validation_pairs")
        if not isinstance(pairs, list) or not pairs:
            raise ValueError(f"Layout {layout_id!r} requires validation_pairs.")
        if any(not isinstance(item, Mapping) for item in pairs):
            raise ValueError("validation_pairs must contain mappings.")
        report = summarize_localization(
            homography,
            [(item["image_xy"], item["true_world_xz"]) for item in pairs],
            wall_parallel_origin_xz=raw_layout.get("wall_parallel_origin_xz"),
            wall_parallel_positive_unit_xz=raw_layout.get(
                "wall_parallel_positive_unit_xz"
            ),
            image_regions=[item.get("image_region") for item in pairs],
            maximum_median_wall_error_blocks=float(
                settings["maximum_median_wall_parallel_error_blocks"]
            ),
            maximum_p95_wall_error_blocks=float(
                settings["maximum_p95_wall_parallel_error_blocks"]
            ),
            minimum_shift_error_multiplier=float(
                settings["minimum_shift_error_multiplier_on_gate_failure"]
            ),
        )
        output_rows.append(
            {
                "layout_id": layout_id,
                "canonical_camera_pose_id": pose_id,
                "resolution_id": raw_layout.get("resolution_id"),
                "image_width_px": raw_layout.get("image_width_px"),
                "image_height_px": raw_layout.get("image_height_px"),
                "detector_version": raw_layout.get("detector_version"),
                "software_runtime_hash": raw_layout.get(
                    "software_runtime_hash"
                ),
                "marker_set_source_hash": marker_source_hash,
                "validation_source_hash": validation_source_hash,
                "wall_parallel_origin_xz": raw_layout.get(
                    "wall_parallel_origin_xz"
                ),
                "wall_parallel_positive_unit_xz": raw_layout.get(
                    "wall_parallel_positive_unit_xz"
                ),
                "homography": homography.to_record(),
                "heldout_localization": report,
            }
        )
    write_json_exclusive(
        args.output,
        {
            "homography_report_schema_version": HOMOGRAPHY_REPORT_SCHEMA_VERSION,
            "homography_input_schema_version": input_schema_version,
            "input_hash": input_hash,
            "producer_run_id": producer_run_id,
            "code_sha": args.code_sha,
            "config_hash": config_hash,
            "config_instance_version": config["config_instance_version"],
            "settings_hash": hash_json_value(settings),
            **settings,
            "layouts": output_rows,
        },
    )


if __name__ == "__main__":
    main()
