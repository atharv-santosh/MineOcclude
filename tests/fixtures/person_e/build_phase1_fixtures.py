"""Build deterministic Person E Phase 1.3 synthetic contract fixtures."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

from mineocclude.experiments.figure_inputs import build_figure_input as _build_figure_input
from mineocclude.experiments.registry import (
    formatted_json_bytes,
    trace_phase1_figure_lineage,
)


ROOT = Path(__file__).resolve().parents[3]
FIXTURE_DIRECTORY = Path(__file__).resolve().parent
ROLLOUT_FIXTURE_DIRECTORY = ROOT / "tests" / "fixtures" / "rollout_registry"


def _load(name: str) -> dict[str, Any]:
    return json.loads((ROLLOUT_FIXTURE_DIRECTORY / name).read_text(encoding="utf-8"))


def _write(name: str, document: Any) -> None:
    (FIXTURE_DIRECTORY / name).write_bytes(formatted_json_bytes(document))


def build_calibration_plan() -> dict[str, Any]:
    samples = []
    source_kinds = (
        "visible_magenta_sheep",
        "negative_wall",
        "negative_marker",
    )
    for split_index, split in enumerate(("calibration", "heldout")):
        for kind_index, source_kind in enumerate(source_kinds):
            number = split_index * len(source_kinds) + kind_index
            samples.append(
                {
                    "sample_id": f"sample_{split}_{source_kind}",
                    "event_id": f"event_{split}_{source_kind}",
                    "trajectory_id": f"trajectory_{split}_{source_kind}",
                    "model_frame_idx": number,
                    "frame_id": f"frame_{split}_{source_kind}",
                    "source_artifact_id": f"capture_{split}_{source_kind}",
                    "source_frame_idx": number,
                    "layout_id": "layout_1",
                    "canonical_camera_pose_id": "pose_1",
                    "resolution_id": "resolution_640x360_rgb",
                    "image_width_px": 640,
                    "image_height_px": 360,
                    "image_coordinate_system": "pixel_center_xy_zero_based",
                    "split": split,
                    "source_kind": source_kind,
                    "threshold_selection_eligible": split == "calibration",
                }
            )
    return {
        "schema_version": "1.0",
        "calibration_plan_schema_version": (
            "person-e-detector-calibration-plan-v1.0"
        ),
        "plan_id": "synthetic_person_e_calibration_plan",
        "synthetic": True,
        "scientific_use": "forbidden",
        "threshold_selection_inputs": {
            "hsv_ranges": [
                {
                    "hue_min_degrees": 280.0,
                    "hue_max_degrees": 320.0,
                    "saturation_min": 0.5,
                    "saturation_max": 1.0,
                    "value_min": 0.5,
                    "value_max": 1.0,
                }
            ],
            "min_area_pixels": [1, 4],
            "max_area_pixels": [None, 256],
            "morphology_iterations": [0, 1],
            "morphology_radius_pixels": [1],
            "connectivity": [8],
        },
        "requested_c_inputs": {
            "visible_magenta_sheep_frames": True,
            "negative_wall_frames": True,
            "negative_marker_frames": True,
            "layout_identity": True,
            "canonical_camera_pose_identity": True,
            "resolution_identity": True,
        },
        "samples": samples,
    }


def build_detection_document() -> dict[str, Any]:
    contexts = []
    records = []
    definitions = (
        ("detected", True, "detected"),
        ("negative", True, "not_detected"),
        ("missing", False, "rejected"),
    )
    for index, (label, available, status) in enumerate(definitions):
        context = {
            "source_frame_id": f"source_frame_{label}",
            "source_artifact_id": f"rollout_clip_{label}",
            "rollout_id": f"synthetic_rollout_{index + 1:03d}",
            "event_id": f"event_{label}",
            "trajectory_id": f"trajectory_{label}",
            "model_frame_idx": index,
            "rollout_frame_idx": index + 10,
            "layout_id": "layout_1",
            "canonical_camera_pose_id": "pose_1",
            "resolution_id": "resolution_640x360_rgb",
            "image_width_px": 640,
            "image_height_px": 360,
            "image_coordinate_system": "pixel_center_xy_zero_based",
            "frame_available": available,
        }
        record = {
            "detection_id": f"detection_{label}",
            **{key: value for key, value in context.items() if key != "frame_available"},
            "detector_version": "synthetic_magenta_detector_v1",
            "threshold_version": "synthetic_threshold_v1",
            "status": status,
            "centroid_xy": [11.5, 13.5] if status == "detected" else None,
            "area_pixels": 16 if status == "detected" else None,
            "bounding_box_xyxy": [10, 12, 14, 16] if status == "detected" else None,
            "quality_status": "accepted" if status != "rejected" else "rejected",
            "rejection_reason": (
                None
                if status == "detected"
                else "no_threshold_match"
                if status == "not_detected"
                else "missing_frame"
            ),
        }
        contexts.append(context)
        records.append(record)
    return {
        "schema_version": "1.0",
        "detection_schema_version": "person-e-detection-records-v1.0",
        "document_id": "synthetic_person_e_detections",
        "synthetic": True,
        "scientific_use": "forbidden",
        "detector_version": "synthetic_magenta_detector_v1",
        "threshold_version": "synthetic_threshold_v1",
        "source_contexts": contexts,
        "records": records,
    }


def build_homography_fixture() -> dict[str, Any]:
    points = (
        ("north_west", [100.0, 80.0], [0.0, 0.0]),
        ("north_east", [500.0, 80.0], [4.0, 0.0]),
        ("south_east", [500.0, 280.0], [4.0, 4.0]),
        ("south_west", [100.0, 280.0], [0.0, 4.0]),
    )
    return {
        "schema_version": "1.0",
        "homography_fixture_schema_version": "person-e-homography-fixture-v1.0",
        "fixture_id": "synthetic_person_e_homography",
        "synthetic": True,
        "scientific_use": "forbidden",
        "layout_id": "layout_1",
        "canonical_camera_pose_id": "pose_1",
        "resolution_id": "resolution_640x360_rgb",
        "image_width_px": 640,
        "image_height_px": 360,
        "image_coordinate_system": "pixel_center_xy_zero_based",
        "world_coordinate_system": "ground_plane_world_xz_blocks",
        "marker_correspondences": [
            {
                "marker_id": marker_id,
                "marker_role": marker_id,
                "marker_kind": "non_magenta_geometry_marker",
                "image_xy": image_xy,
                "world_xz_blocks": world_xz,
            }
            for marker_id, image_xy, world_xz in points
        ],
        "expected_probe": {
            "image_xy": [300.0, 180.0],
            "world_xz_blocks": [2.0, 2.0],
            "absolute_tolerance_blocks": 1e-9,
        },
    }


def _clone_rollout(
    source: dict[str, Any],
    *,
    suffix: str,
    alpha: float,
    control_type: str,
    direction_version: str,
    seed: int,
    hash_character: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    row = copy.deepcopy(source)
    row.update(
        {
            "rollout_id": f"synthetic_person_e_rollout_{suffix}",
            "event_id": f"synthetic_person_e_event_{suffix}",
            "episode_id": f"synthetic_person_e_episode_{suffix}",
            "trajectory_id": f"synthetic_person_e_trajectory_{suffix}",
            "server_tick": seed,
            "render_frame_idx": seed,
            "action_idx": seed,
            "model_frame_idx": 8,
            "seed": seed,
            "dose_id": suffix,
            "alpha_requested": alpha,
            "alpha_applied": alpha,
            "cap_reduced": False,
            "intended_block_shift": alpha,
            "direction_version": direction_version,
            "control_type": control_type,
            "input_context_id": f"synthetic_person_e_context_{suffix}",
            "output_artifact_id": f"synthetic_person_e_clip_artifact_{suffix}",
            "output_uri": f"synthetic://person-e-phase1/rollouts/{suffix}.mp4",
            "output_hash": hash_character * 64,
            "outcome": "measurable_continuation",
            "outcome_detail": None,
            "measurable": True,
            "status": "accepted",
            "exclusion_reason": None,
            "superseded_by": None,
        }
    )
    artifact = {
        "artifact_id": row["output_artifact_id"],
        "artifact_type": "rollout_clip",
        "exclusion_reason": None,
        "producer_run_id": row["run_id"],
        "schema_version": "1.0",
        "sha256": row["output_hash"],
        "status": "accepted",
        "superseded_by": None,
        "uri": row["output_uri"],
    }
    return row, artifact


def build_rollout_measurement_fixture() -> dict[str, Any]:
    manifest = _load("accepted_rollout_manifest.json")
    registry = _load("accepted_registry.json")
    manifest["manifest_id"] = "synthetic_person_e_phase1_rollouts"
    manifest["handoff_id"] = "synthetic_person_e_phase1_handoff"
    registry["registry_id"] = "synthetic_person_e_phase1_rollout_registry"
    registry["handoff_id"] = manifest["handoff_id"]
    source = manifest["rollout_rows"][0]
    negative, negative_artifact = _clone_rollout(
        source,
        suffix="negative",
        alpha=-0.5,
        control_type="intervention",
        direction_version="synthetic_direction_v1",
        seed=104,
        hash_character="7",
    )
    random, random_artifact = _clone_rollout(
        source,
        suffix="random",
        alpha=0.5,
        control_type="random_direction",
        direction_version="synthetic_random_direction_v1",
        seed=105,
        hash_character="8",
    )
    manifest["rollout_rows"].extend([negative, random])
    registry["artifacts"].extend([negative_artifact, random_artifact])
    producing_run = next(
        run for run in registry["runs"] if run["run_id"] == source["run_id"]
    )
    producing_run["output_artifact_ids"].extend(
        [negative["output_artifact_id"], random["output_artifact_id"]]
    )

    rollout_by_id = {row["rollout_id"]: row for row in manifest["rollout_rows"]}

    def control_id(rollout_id: str, kind: str) -> str:
        row = rollout_by_id[rollout_id]
        return f"{row['event_id']}:{row['seed']}:{kind}"

    zero_id = manifest["rollout_rows"][0]["rollout_id"]
    positive_id = manifest["rollout_rows"][1]["rollout_id"]
    negative_id = negative["rollout_id"]
    random_id = random["rollout_id"]
    cases = [
        {
            "case_id": "case_alpha_zero",
            "scenario_kind": "alpha_zero",
            "rollout_id": zero_id,
            "declared_control_id": control_id(zero_id, "alpha_zero"),
            "expected_frame_id": "frame_zero_10",
            "observed_frame_id": "frame_zero_10",
            "measurement_status": "measured",
            "displacement_blocks": 0.0,
            "expected_result": "accepted_measurement",
        },
        {
            "case_id": "case_positive",
            "scenario_kind": "positive_signed_dose",
            "rollout_id": positive_id,
            "declared_control_id": control_id(positive_id, "primary"),
            "expected_frame_id": "frame_positive_10",
            "observed_frame_id": "frame_positive_10",
            "measurement_status": "non_persistence",
            "displacement_blocks": None,
            "expected_result": "accepted_non_persistence",
        },
        {
            "case_id": "case_negative",
            "scenario_kind": "negative_signed_dose",
            "rollout_id": negative_id,
            "declared_control_id": control_id(negative_id, "primary"),
            "expected_frame_id": "frame_negative_10",
            "observed_frame_id": "frame_negative_10",
            "measurement_status": "measured",
            "displacement_blocks": -0.4,
            "expected_result": "accepted_measurement",
        },
        {
            "case_id": "case_random",
            "scenario_kind": "random_control",
            "rollout_id": random_id,
            "declared_control_id": control_id(random_id, "random_direction"),
            "expected_frame_id": "frame_random_10",
            "observed_frame_id": "frame_random_10",
            "measurement_status": "measured",
            "displacement_blocks": 0.1,
            "expected_result": "accepted_measurement",
        },
        {
            "case_id": "case_non_persistence",
            "scenario_kind": "non_persistence",
            "rollout_id": positive_id,
            "declared_control_id": control_id(positive_id, "primary"),
            "expected_frame_id": "frame_positive_10",
            "observed_frame_id": "frame_positive_10",
            "measurement_status": "non_persistence",
            "displacement_blocks": None,
            "expected_result": "accepted_non_persistence",
        },
        {
            "case_id": "case_missing_frame",
            "scenario_kind": "missing_frame",
            "rollout_id": negative_id,
            "declared_control_id": control_id(negative_id, "primary"),
            "expected_frame_id": "frame_negative_11",
            "observed_frame_id": None,
            "measurement_status": "rejected",
            "displacement_blocks": None,
            "expected_result": "rejected_missing_frame",
        },
        {
            "case_id": "case_misaligned_frame",
            "scenario_kind": "misaligned_frame",
            "rollout_id": negative_id,
            "declared_control_id": control_id(negative_id, "primary"),
            "expected_frame_id": "frame_negative_12",
            "observed_frame_id": "frame_other_12",
            "measurement_status": "rejected",
            "displacement_blocks": None,
            "expected_result": "rejected_misaligned_frame",
        },
    ]
    return {
        "schema_version": "1.0",
        "scenario_schema_version": "person-e-rollout-measurement-fixture-v1.0",
        "fixture_id": "synthetic_person_e_rollout_measurement_cases",
        "synthetic": True,
        "scientific_use": "forbidden",
        "rollout_manifest": manifest,
        "registry": registry,
        "cases": cases,
    }


def build_figure_input() -> dict[str, Any]:
    return _build_figure_input(
        [
            {
                "series_id": "synthetic_ridge",
                "source_result_id": "synthetic_metric_layer_3",
                "source_artifact_id": "artifact_metric",
                "source_artifact_hash": (
                    "26b2a2147573596334e92a7fae79badd4854d66a7fa1ccf3e82ddb076b8234d7"
                ),
                "source_run_id": "run_metric",
                "source_lifecycle": "accepted",
                "source_superseded_by": None,
                "accepted_manifest_hash": "a" * 64,
                "fold_manifest_hash": "b" * 64,
                "x": 3,
                "y": 0.42,
                "x_unit": "layer_index",
                "y_unit": "r_squared",
                "sample_count": 3,
                "uncertainty_type": "none",
                "lower": None,
                "upper": None,
                "status": "valid",
                "diagnostic": None,
            }
        ],
        figure_id="synthetic_person_e_phase1_figure_input",
        figure_family="layer_curve",
        code_sha="f" * 40,
        result_scope="known_answer",
    )


def build_trace_registry(figure_input: dict[str, Any]) -> dict[str, Any]:
    registry = json.loads(
        (FIXTURE_DIRECTORY / "immutable_registry_v1.json").read_text(encoding="utf-8")
    )
    figure_bytes = formatted_json_bytes(figure_input)
    registry["registry_id"] = "synthetic_person_e_phase1_trace_registry"
    registry["runs"].append(
        {
            "schema_version": "1.0",
            "run_id": "run_figure_input",
            "code_sha": "f" * 40,
            "git_dirty": False,
            "config_snapshot_hash": figure_input["config_hash"],
            "checkpoint_hash": "3" * 64,
            "data_identity_hash": "4" * 64,
            "preprocess_hash": "5" * 64,
            "environment_hash": "6" * 64,
            "seeds": {"figure_input": 606},
            "command": ["synthetic-figure-input"],
            "owner": "person_e",
            "started_at": "2026-01-01T00:00:10Z",
            "ended_at": "2026-01-01T00:00:11Z",
            "status": "completed",
            "parent_run_id": "run_metric",
            "input_artifact_ids": ["artifact_metric"],
            "output_artifact_ids": ["artifact_figure_input"],
            "failure_reason": None,
            "supersedes_run_id": None,
            "supersession_reason": None,
        }
    )
    registry["artifacts"].append(
        {
            "schema_version": "1.0",
            "artifact_schema_version": "person-e-figure-input-v0.2",
            "artifact_id": "artifact_figure_input",
            "direct_input_artifact_ids": ["artifact_metric"],
            "creator_run_id": "run_figure_input",
            "artifact_type": "figure_input",
            "uri": "memory://person-e-phase1/figure-input",
            "sha256": hashlib.sha256(figure_bytes).hexdigest(),
            "size_bytes": len(figure_bytes),
            "status": "accepted",
            "status_authority": "person_e",
            "status_reason": None,
            "superseded_by": None,
        }
    )
    return registry


def build_superseded_figure_sources(
    trace_registry: dict[str, Any],
) -> dict[str, Any]:
    registry = copy.deepcopy(trace_registry)
    old_metric = next(
        item for item in registry["artifacts"] if item["artifact_id"] == "artifact_metric"
    )
    old_metric.update(
        {
            "status": "superseded",
            "status_reason": "Synthetic corrected metric serialization.",
            "superseded_by": "artifact_metric_corrected",
        }
    )
    old_run = next(item for item in registry["runs"] if item["run_id"] == "run_metric")
    corrected_run = copy.deepcopy(old_run)
    corrected_run.update(
        {
            "run_id": "run_metric_corrected",
            "code_sha": "9" * 40,
            "command": ["synthetic-metric-correction"],
            "started_at": "2026-01-01T00:00:12Z",
            "ended_at": "2026-01-01T00:00:13Z",
            "parent_run_id": "run_metric",
            "output_artifact_ids": ["artifact_metric_corrected"],
            "supersedes_run_id": "run_metric",
            "supersession_reason": "Corrected synthetic metric serialization.",
        }
    )
    registry["runs"].append(corrected_run)
    corrected_metric = copy.deepcopy(old_metric)
    corrected_metric.update(
        {
            "artifact_id": "artifact_metric_corrected",
            "creator_run_id": "run_metric_corrected",
            "sha256": "7" * 64,
            "size_bytes": 34,
            "status": "accepted",
            "status_reason": None,
            "superseded_by": None,
            "uri": "memory://person-e-phase1/metric-table-corrected",
        }
    )
    registry["artifacts"].append(corrected_metric)

    current_row = {
        **build_figure_input()["rows"][0],
        "source_result_id": "synthetic_metric_layer_3_corrected",
        "source_artifact_id": "artifact_metric_corrected",
        "source_artifact_hash": "7" * 64,
        "source_run_id": "run_metric_corrected",
    }
    current_figure = _build_figure_input(
        [current_row],
        figure_id="synthetic_person_e_phase1_current_figure_input",
        figure_family="layer_curve",
        code_sha="f" * 40,
        result_scope="known_answer",
    )
    stale_row = {
        **build_figure_input()["rows"][0],
        "source_lifecycle": "superseded",
        "source_superseded_by": "artifact_metric_corrected",
        "y": None,
        "sample_count": 0,
        "uncertainty_type": "none",
        "lower": None,
        "upper": None,
        "status": "invalid",
        "diagnostic": "source artifact is superseded",
    }
    stale_figure = _build_figure_input(
        [stale_row],
        figure_id="synthetic_person_e_phase1_stale_figure_input",
        figure_family="layer_curve",
        code_sha="f" * 40,
        result_scope="known_answer",
    )
    figure_run = next(
        item for item in registry["runs"] if item["run_id"] == "run_figure_input"
    )
    figure_run["parent_run_id"] = "run_metric_corrected"
    figure_run["input_artifact_ids"] = ["artifact_metric_corrected"]
    figure_artifact = next(
        item
        for item in registry["artifacts"]
        if item["artifact_id"] == "artifact_figure_input"
    )
    current_bytes = formatted_json_bytes(current_figure)
    figure_artifact["direct_input_artifact_ids"] = ["artifact_metric_corrected"]
    figure_artifact["sha256"] = hashlib.sha256(current_bytes).hexdigest()
    figure_artifact["size_bytes"] = len(current_bytes)
    return {
        "registry": registry,
        "current_figure_input": current_figure,
        "stale_figure_input": stale_figure,
    }


def build_all() -> dict[str, Any]:
    calibration = build_calibration_plan()
    detection = build_detection_document()
    homography = build_homography_fixture()
    rollout_measurement = build_rollout_measurement_fixture()
    figure_input = build_figure_input()
    trace_registry = build_trace_registry(figure_input)
    trace = trace_phase1_figure_lineage(trace_registry, "artifact_figure_input")

    rejected_calibration = copy.deepcopy(calibration)
    rejected_calibration["samples"][3]["event_id"] = calibration["samples"][0][
        "event_id"
    ]
    rejected_detection = copy.deepcopy(detection)
    rejected_detection["records"][0]["event_id"] = "wrong_event"
    rejected_homography = copy.deepcopy(homography)
    for index, marker in enumerate(rejected_homography["marker_correspondences"]):
        marker["image_xy"] = [100.0 + index * 100.0, 80.0]
    missing_direct_input_registry = copy.deepcopy(trace_registry)
    missing_direct_input_registry["artifacts"][-1]["direct_input_artifact_ids"] = [
        "missing_metric"
    ]
    missing_direct_input_registry["runs"][-1]["input_artifact_ids"] = [
        "missing_metric"
    ]
    identity_mismatch_figure = _build_figure_input(
        [
            {
                **figure_input["rows"][0],
                "source_run_id": "wrong_metric_run",
            }
        ],
        figure_id="synthetic_person_e_phase1_identity_mismatch",
        figure_family="layer_curve",
        code_sha="f" * 40,
        result_scope="known_answer",
    )
    return {
        "calibration_plan_v1.json": calibration,
        "rejected_calibration_overlap_event_v1.json": rejected_calibration,
        "detection_records_v1.json": detection,
        "rejected_detection_identity_v1.json": rejected_detection,
        "homography_fixture_v1.json": homography,
        "rejected_homography_degenerate_v1.json": rejected_homography,
        "rollout_measurement_scenarios_v1.json": rollout_measurement,
        "figure_input_v1.json": figure_input,
        "phase1_trace_registry_v1.json": trace_registry,
        "phase1_lineage_trace_v1.json": trace,
        "figure_supersession_scenarios_v1.json": build_superseded_figure_sources(
            trace_registry
        ),
        "rejected_registry_missing_direct_input_v1.json": (
            missing_direct_input_registry
        ),
        "rejected_figure_identity_mismatch_v1.json": identity_mismatch_figure,
    }


def main() -> None:
    for name, document in build_all().items():
        _write(name, document)


if __name__ == "__main__":
    main()
