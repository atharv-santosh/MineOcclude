"""Known-answer synthetic inputs for rehearsing the Step 7.1 measurement path.

These are deliberately tiny and deliberately synthetic. Their purpose is to let
the frozen measurement entry points be executed end to end, in order, on a
machine that has no rollout clips — proving the workflow, the commands, and the
schema handoffs are operable before real data exists.

Nothing here is scientific evidence. Every receipt produced from these inputs
carries ``evidence_class = "synthetic_fixture"`` and is barred from claiming a
real clean reproduction.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from mineocclude.experiments.registry import hash_json_value
from mineocclude.vision.config import DEFAULT_PERSON_E_CONFIG_PATH


CODE_SHA = "a" * 40
CONFIG_HASH = "b" * 64
MODEL_HASH = "c" * 64
PREPROCESS_HASH = "d" * 64
CONTEXT_HASH = "e" * 64
REQUEST_HASH = "f" * 64
CLIP_HASH = "1" * 64

REHEARSAL_RUN_ID = "person_e_measurement_run_1"
REHEARSAL_FIXTURE_VERSION = "person-e-step7-1-rehearsal-fixture-v0.1"

#: The synthetic sheep sits at image (1.5, 1.5) under an identity-scale
#: homography, so the expected wall-parallel answer is exactly 1.5 blocks.
EXPECTED_WALL_PARALLEL_BLOCKS = 1.5


def write_live_config(directory: Path) -> Path:
    """Write a calibrated, live-ready config with known-answer thresholds."""

    config = json.loads(DEFAULT_PERSON_E_CONFIG_PATH.read_text(encoding="utf-8"))
    config["status"] = "calibrated_live_ready"
    config["config_instance_version"] = "person-e-phase1-live-known-answer-v0.1"
    detector = config["detector"]
    detector.update(
        {
            "threshold_status": "frozen_calibration_only",
            "threshold_version": "magenta-known-answer-v1",
            "calibration_dataset_hash": "1" * 64,
            "heldout_report_hash": "2" * 64,
            "hsv_ranges": [
                {
                    "h_min": 280.0,
                    "h_max": 320.0,
                    "s_min": 0.5,
                    "s_max": 1.0,
                    "v_min": 0.5,
                    "v_max": 1.0,
                }
            ],
        }
    )
    detector["blob"]["min_area_pixels"] = 1
    detector["blob"]["max_area_pixels"] = 10_000
    ssim = config["ssim"]
    ssim["ssim_version"] = "global-ssim-known-answer-v1"
    ssim["background_mask_margin_pixels"] = 0
    ssim["mask_status"] = "frozen_person_b_person_e_signed"
    path = directory / "person_e_live_config.json"
    path.write_text(
        json.dumps(config, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return path


def _artifact(
    artifact_id: str, artifact_type: str, sha256: str, producer_run_id: str, uri: str
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "artifact_id": artifact_id,
        "artifact_type": artifact_type,
        "uri": uri,
        "sha256": sha256,
        "producer_run_id": producer_run_id,
        "status": "accepted",
        "exclusion_reason": None,
        "superseded_by": None,
    }


def registry_bundle(config_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return a minimal accepted rollout manifest and its registry."""

    runs = [
        {
            "run_id": "run_inputs",
            "command": ["register-inputs"],
            "owner": "person_a",
            "parent_run_id": None,
            "input_artifact_ids": [],
            "output_artifact_ids": ["context_1", "request_1"],
            "code_sha": CODE_SHA,
            "config_hash": CONFIG_HASH,
            "model_hash": MODEL_HASH,
            "preprocess_hash": PREPROCESS_HASH,
            "execution_status": "completed",
            "failure_reason": None,
        },
        {
            "run_id": "run_rollout",
            "command": ["generate", "--rollout", "rollout_zero"],
            "owner": "person_a",
            "parent_run_id": "run_inputs",
            "input_artifact_ids": ["context_1", "request_1"],
            "output_artifact_ids": ["clip_zero"],
            "code_sha": CODE_SHA,
            "config_hash": CONFIG_HASH,
            "model_hash": MODEL_HASH,
            "preprocess_hash": PREPROCESS_HASH,
            "execution_status": "completed",
            "failure_reason": None,
        },
        {
            "run_id": REHEARSAL_RUN_ID,
            "command": ["person-e-known-answer"],
            "owner": "person_e",
            "parent_run_id": "run_rollout",
            "input_artifact_ids": ["clip_zero"],
            "output_artifact_ids": [],
            "code_sha": CODE_SHA,
            "config_hash": hashlib.sha256(config_path.read_bytes()).hexdigest(),
            "model_hash": MODEL_HASH,
            "preprocess_hash": PREPROCESS_HASH,
            "execution_status": "completed",
            "failure_reason": None,
        },
    ]
    registry = {
        "schema_version": "1.0",
        "registry_id": "registry_1",
        "handoff_id": "handoff_1",
        "runs": runs,
        "artifacts": [
            _artifact(
                "context_1",
                "input_context",
                CONTEXT_HASH,
                "run_inputs",
                "memory://inputs/context_1",
            ),
            _artifact(
                "request_1",
                "intervention_request",
                REQUEST_HASH,
                "run_inputs",
                "memory://inputs/request_1",
            ),
            _artifact(
                "clip_zero",
                "rollout_clip",
                CLIP_HASH,
                "run_rollout",
                "memory://rollouts/clip_zero",
            ),
        ],
    }
    rollout = {
        "schema_version": "1.0",
        "rollout_id": "rollout_zero",
        "event_id": "event_1",
        "episode_id": "episode_1",
        "trajectory_id": "trajectory_1",
        "server_tick": 10,
        "render_frame_idx": 10,
        "action_idx": 10,
        "layout_id": "layout_1",
        "model_frame_idx": 10,
        "regime": "A",
        "visibility": "occluded",
        "tau": 0.5,
        "v": 1.0,
        "q": 0.05,
        "duration": 1.0,
        "seed": 7,
        "dose_id": "dose_zero",
        "alpha_requested": 0.0,
        "alpha_applied": 0.0,
        "cap_reduced": False,
        "intended_block_shift": 0.0,
        "direction_version": "direction_v1",
        "layer_idx": 3,
        "hook_site": "decoder_output",
        "timestep_idx": 15,
        "control_type": "alpha_zero",
        "input_context_id": "input_context_1",
        "input_context_artifact_id": "context_1",
        "input_context_hash": CONTEXT_HASH,
        "intervention_request_artifact_id": "request_1",
        "output_artifact_id": "clip_zero",
        "output_uri": "memory://rollouts/clip_zero",
        "output_hash": CLIP_HASH,
        "code_sha": CODE_SHA,
        "model_hash": MODEL_HASH,
        "config_hash": CONFIG_HASH,
        "preprocess_hash": PREPROCESS_HASH,
        "run_id": "run_rollout",
        "outcome": "measurable_continuation",
        "outcome_detail": None,
        "measurable": True,
        "status": "accepted",
        "exclusion_reason": None,
        "superseded_by": None,
    }
    manifest = {
        "schema_version": "1.0",
        "manifest_id": "manifest_1",
        "handoff_id": "handoff_1",
        "rollout_rows": [rollout],
    }
    return manifest, registry


def homography_input() -> dict[str, Any]:
    """Four exact correspondences whose recovered mapping is the identity."""

    corners = {"nw": [0, 0], "ne": [4, 0], "se": [4, 4], "sw": [0, 4]}
    return {
        "homography_input_schema_version": "person-e-homography-input-v0.1",
        "layouts": [
            {
                "layout_id": "layout_1",
                "canonical_camera_pose_id": "pose_1",
                "marker_set_source_hash": "1" * 64,
                "validation_source_hash": "2" * 64,
                "marker_ids": ["nw", "ne", "se", "sw"],
                "image_points_by_marker": dict(corners),
                "world_points_by_marker": dict(corners),
                "validation_pairs": [
                    {
                        "image_xy": [1.5, 1.5],
                        "true_world_xz": [1.5, 1.5],
                        "image_region": "center",
                    }
                ],
                "wall_parallel_origin_xz": [0, 0],
                "wall_parallel_positive_unit_xz": [1, 0],
            }
        ],
    }


def frame_input() -> dict[str, Any]:
    """Three frames: absent, then present for two consecutive frames.

    That sequence is exactly what the locked primary event rule requires, so
    the rehearsal exercises the real reappearance logic rather than a shortcut.
    """

    black = [[[0, 0, 0] for _ in range(4)] for _ in range(4)]
    magenta = [[[0, 0, 0] for _ in range(4)] for _ in range(4)]
    for y in (1, 2):
        for x in (1, 2):
            magenta[y][x] = [255, 0, 255]
    frames = []
    for frame_idx, rgb in ((1, black), (2, magenta), (3, magenta)):
        frames.append(
            {
                "rollout_id": "rollout_zero",
                "reveal_frame_idx": 1,
                "frame_idx": frame_idx,
                "layout_id": "layout_1",
                "canonical_camera_pose_id": "pose_1",
                "source_frame_hash": f"{frame_idx}" * 64,
                "decoded_rgb_hash": hash_json_value(rgb),
                "rgb": rgb,
            }
        )
    return {
        "u4_frame_input_schema_version": "person-e-u4-frame-input-v0.1",
        "frames": frames,
    }


def ssim_report(localization: dict[str, Any]) -> dict[str, Any]:
    """A self-comparison SSIM report bound to the localization run identity."""

    settings = {
        "algorithm": "global_ssim_per_channel_mean_v0.1",
        "ssim_version": "global-ssim-known-answer-v1",
        "data_range": 255.0,
        "channel_handling": "rgb_per_channel_mean",
        "sample_covariance": True,
        "k1": 0.01,
        "k2": 0.03,
        "background_margin_pixels": 0,
    }
    return {
        "ssim_report_schema_version": "person-e-ssim-report-v0.2",
        "accepted_rollout_manifest_hash": localization[
            "accepted_rollout_manifest_hash"
        ],
        "accepted_registry_hash": localization["accepted_registry_hash"],
        "config_hash": localization["config_hash"],
        "settings_hash": hash_json_value(settings),
        **settings,
        "comparisons": [
            {
                "comparison_id": "comparison_zero",
                "pushed_metadata": {
                    "rollout_id": "rollout_zero",
                    "event_id": "event_1",
                    "seed": 7,
                    "rollout_frame_idx": 2,
                    "clip_hash": CLIP_HASH,
                },
                "baseline_metadata": {
                    "rollout_id": "rollout_zero",
                    "clip_hash": CLIP_HASH,
                },
                "ssim_version": "global-ssim-known-answer-v1",
                "alignment_checked": True,
                "algorithm": "global_ssim_per_channel_mean_v0.1",
                "full_frame_ssim": 1.0,
                "background_masked_ssim": 1.0,
                "full_frame_pixel_count": 16,
                "background_pixel_count": 12,
                "data_range": 255.0,
                "channel_handling": "rgb_per_channel_mean",
            }
        ],
    }


def write_json(path: Path, document: Any) -> Path:
    path.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return path
