#!/usr/bin/env python3
"""Build the prospective P1 authority for the large-scale no-wall study.

This module is design-only.  It reads frozen repository authority, creates the
120 prospective specifications and analysis contracts, and performs synthetic
metadata checks.  It never starts Minecraft, loads MineWorld, reads fresh
activations, fits a probe, or computes a scientific outcome.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import random
import subprocess
import sys
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mineocclude.data.noise_schedule import (  # noqa: E402
    generate_noise_schedule,
    schedule_hash,
)

PACKAGE = (
    ROOT / "docs/status/integration/"
    "exploratory_large_scale_no_wall_scaling_best_k_v0_1"
)
PREDECESSOR_PACKAGE = (
    ROOT / "docs/status/integration/exploratory_visible_position_resolution_v0_1"
)

P1_FROZEN_AT = "2026-08-10T05:39:37Z"
P0_HEAD = "4c240be1d19f95c508dedb31567c933dda9187b5"
PREDECESSOR_SHA = "18c8dd0de0987d3065206a5fd7df452badb1338b"
FROZEN_MVP_SHA = "bb22364cbc4f65b788a56b60e7d6503e6226df7b"
BRANCH = "exploration/large-scale-no-wall-scaling-best-k-v0-1"
SPEC_VERSION = "large-scale-no-wall-trajectory-spec-v0.1"

LAYOUTS = ("L01", "L02", "L03", "L04", "L05", "L06")
DIRECTIONS = ("LEFT_TO_RIGHT", "RIGHT_TO_LEFT")
PROFILES = (
    "EARLY_CONSTANT",
    "LATE_ONSET",
    "FAST_TRANSIT",
    "PAUSE_RESUME",
    "TWO_SPEED",
)
REPEATS = (1, 2)
F = 60
TICK_HZ = 20
DT_SECONDS = 0.05
MAX_ATTEMPTS = 3
PROCESS_Q = 0.2
ALPHA_GRID = (0.1, 1.0, 10.0, 100.0)
BEST_K = (1, 4, 8, 16, 32, 64, 128)
TRAINING_SIZES = (5, 15, 40, 70, 100)
SUBSET_REPLICATES = (20, 16, 12, 8, 6)

SOURCE_SHA256 = {
    "docs/status/integration/exploratory_large_scale_no_wall_scaling_best_k_v0_1/branch_authority.json": "e4afd4924d1afb200aae45411945083f11f94670ec29505abf89813f6cfc1a2a",
    "docs/status/integration/exploratory_large_scale_no_wall_scaling_best_k_v0_1/predecessor_inventory.json": "17dc9f77878b63750a7064e321f067f930461f04e6907fd609ba003e5cdbbbb9",
    "docs/status/integration/exploratory_large_scale_no_wall_scaling_best_k_v0_1/p0_receipt.json": "060b88328ad788c4948e4ccc170a27b1c842c6d3b7d64f78dd68f1ccf7e15373",
    "docs/status/integration/exploratory_visible_position_resolution_v0_1/development_freeze.json": "97e68c4981a781053baef4f33a64516208725627bd757e7ffc2eb572951856ce",
    "docs/status/integration/exploratory_visible_position_resolution_v0_1/capture_manifest.json": "44575ecf539b3d93f50a64d1ae1270ea48a0124753a5d69c1f76f117aea37218",
    "docs/status/integration/exploratory_visible_position_resolution_v0_1/expanded_activation_manifest.json": "59fc98f1d2d9569d8814140e29827ddf522553b5b207b2116b7f2cf8f6961871",
    "docs/status/integration/exploratory_visible_position_resolution_v0_1/expanded_visibility_eligibility.json": "1882ec400159f83e4d09dc7b113907857dca5ad5f7fbd90760ad296fb289d6ea",
    "docs/status/integration/exploratory_visible_position_resolution_v0_1/provenance.json": "fa95cb64261160720d768d38cc4fdf4177d10e4270ddf8d411b39c90d5941cae",
    "configs/scenes/layouts.yaml": "5a39d2dcae44d72f07b0e645dcc3e64ea6178ef79f1c9e3f12bff11f857f82cb",
    "fabric/mineocclude-mod/src/main/java/com/mineocclude/server/Layouts.java": "316da835f696c4c5dc53b5abc7a7e9f6e566e6948f15db3b063b00a121bd0c0f",
    "fabric/mineocclude-mod/src/main/java/com/mineocclude/server/MineOccludeServer.java": "530b28613101d678ad9b91e697b792761ffc4e9f831176a0cd76a719cd62f4f8",
    "fabric/mineocclude-mod/src/main/java/com/mineocclude/server/EpisodeConfig.java": "34414fb739a74dd75d4155ad56bd6b9eebcf92aaae1bd775abac3e62580652fc",
    "fabric/mineocclude-mod/src/main/java/com/mineocclude/server/SheepController.java": "3bc7c3dbf26215a23f88c6cafae143986baa721877d8570cb1dda90104e55341",
    "fabric/mineocclude-mod/src/main/java/com/mineocclude/server/TargetRetentionPolicy.java": "f05990895d79fd1b81a3cd5d3a318664d3f4c764335fb13295484f47680ba289",
    "fabric/mineocclude-mod/src/main/java/com/mineocclude/server/NoiseSchedule.java": "e42472090a645aecae617d11c0ae6e961b2b52cdc7d1898b5496d299d50b0993",
    "src/mineocclude/data/noise_schedule.py": "97f813b5a80914d443832bfd4c33b23738c2db2bbc93e3bf27812d0e14dac603",
    "scripts/run_autonomous_pilot.py": "69dcc731cb5640b3dd475fe0c8215e918109c588a8d4a1c4751ead26d952d235",
    "scripts/run_visible_position_resolution_task4.py": "dd554f453710986d379a65b3824f4a61f7a0978ca0a81be32fc96a2c757d4d01",
    "src/mineocclude/probes/ridge.py": "3488f9e19896538e32d9b5ff532520995c1cc37704abe64a4b0712169dbe21d8",
    "scripts/run_person_a_66_cell_production_extraction.py": "06f0a9d55352688fa789f18ab0072dcbed612f32a3d81d11dba1aa26f80977f0",
}

# Layouts.java is the runtime authority.  The YAML contract supplies matching
# canonical pose/start-region evidence.  Camera distance is part of layout
# identity and therefore cannot vary within layout.
LAYOUT_AUTHORITY: dict[str, dict[str, Any]] = {
    "L01": {
        "runtime_layout_id": "layout_01",
        "axis": "x",
        "lane": [-8.0, 8.0],
        "start_region_ltr": [-7.0, -5.0],
        "lane_ortho": 6.0,
        "wall_ortho_offset": -4.0,
        "camera_dist": 8.0,
        "camera_xyz": [0.5, 4.0, -5.5],
        "yaw": 0.0,
    },
    "L02": {
        "runtime_layout_id": "layout_02",
        "axis": "z",
        "lane": [-8.0, 8.0],
        "start_region_ltr": [-7.0, -5.0],
        "lane_ortho": 6.0,
        "wall_ortho_offset": -4.0,
        "camera_dist": 8.0,
        "camera_xyz": [-5.5, 4.0, 0.5],
        "yaw": -90.0,
    },
    "L03": {
        "runtime_layout_id": "layout_03",
        "axis": "x",
        "lane": [-9.0, 9.0],
        "start_region_ltr": [-8.0, -6.0],
        "lane_ortho": 6.0,
        "wall_ortho_offset": -4.0,
        "camera_dist": 8.0,
        "camera_xyz": [0.5, 4.0, -5.5],
        "yaw": 0.0,
    },
    "L04": {
        "runtime_layout_id": "layout_04",
        "axis": "x",
        "lane": [-8.0, 8.0],
        "start_region_ltr": [-7.0, -5.0],
        "lane_ortho": 8.0,
        "wall_ortho_offset": -5.0,
        "camera_dist": 9.0,
        "camera_xyz": [0.5, 4.0, -5.5],
        "yaw": 0.0,
    },
    "L05": {
        "runtime_layout_id": "layout_05",
        "axis": "x",
        "lane": [-7.0, 7.0],
        "start_region_ltr": [-7.0, -5.0],
        "lane_ortho": 5.0,
        "wall_ortho_offset": -3.0,
        "camera_dist": 7.0,
        "camera_xyz": [0.5, 4.0, -4.5],
        "yaw": 0.0,
    },
    "L06": {
        "runtime_layout_id": "layout_06",
        "axis": "z",
        "lane": [-9.0, 9.0],
        "start_region_ltr": [-8.0, -6.0],
        "lane_ortho": 7.0,
        "wall_ortho_offset": -4.0,
        "camera_dist": 10.0,
        "camera_xyz": [-6.5, 4.0, 0.5],
        "yaw": -90.0,
    },
}


class P1AuthorityError(RuntimeError):
    """Raised when prospective authority cannot be frozen consistently."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise P1AuthorityError(message)


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def sha256_file(path: Path, chunk_size: int = 8 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"JSON authority is not an object: {path}")
    return value


def write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def source_references() -> list[dict[str, Any]]:
    refs = []
    for relative, expected in SOURCE_SHA256.items():
        path = ROOT / relative
        require(path.is_file(), f"missing authority source: {relative}")
        observed = sha256_file(path)
        require(observed == expected, f"authority SHA mismatch: {relative}")
        refs.append(
            {"path": relative, "sha256": observed, "byte_size": path.stat().st_size}
        )
    return refs


def verify_literal_authority() -> dict[str, Any]:
    refs = source_references()
    freeze = load_json(PREDECESSOR_PACKAGE / "development_freeze.json")
    activation = load_json(PREDECESSOR_PACKAGE / "expanded_activation_manifest.json")
    capture = load_json(PREDECESSOR_PACKAGE / "capture_manifest.json")
    eligibility = load_json(
        PREDECESSOR_PACKAGE / "expanded_visibility_eligibility.json"
    )
    provenance = load_json(PREDECESSOR_PACKAGE / "provenance.json")
    contract = activation["extraction_contract"]

    require(freeze["layer_idx"] == 4, "literal layer authority differs")
    require(tuple(freeze["alpha_grid"]) == ALPHA_GRID, "literal alpha grid differs")
    require(contract["token_grid"] == [14, 24], "token grid differs")
    require(contract["token_count"] == 336, "token count differs")
    require(contract["hidden_width"] == 2048, "hidden width differs")
    require(336 * 2048 == 688128, "full feature dimension arithmetic differs")
    require(
        capture["round1"]["eligible_rows_by_layout"]
        == {f"layout_{i:02d}": 60 for i in range(1, 7)},
        "round-1 common F authority differs",
    )
    require(
        capture["round2"]["eligible_rows_by_layout"]
        == {f"layout_{i:02d}": 60 for i in range(1, 7)},
        "round-2 common F authority differs",
    )
    l06_excluded = [
        row
        for row in eligibility["excluded_rows"]
        if row["trajectory_id"] == "layout_06_ep12616"
    ]
    require(
        [row["model_frame_idx"] for row in l06_excluded] == list(range(51, 60)),
        "historical L06 exclusion authority differs",
    )
    model = provenance["model_identity"]
    require(Path(model["checkpoint_path"]).is_file(), "MineWorld checkpoint missing")
    require(Path(model["vae_path"]).is_file(), "VAE checkpoint missing")
    return {
        "source_references": refs,
        "model_identity": model,
        "preprocessing_identity": provenance["preprocessing_identity"],
        "context_semantics": contract["context_semantics"],
        "f_resolution": {
            "expected_source_frame_count": 60,
            "eligible_rows_per_trajectory": 60,
            "model_frame_idx": list(range(60)),
            "common_across_all_layouts": True,
            "fresh_predecessor_evidence": "Two accepted 60-row captures per layout, including two for L06.",
            "historical_l06_51_row_cause": "Historical layout_06_ep12616 had 60 source frames; strict visibility quarantined only model_frame_idx 51..59 as not fully visible. This was trajectory-specific empirical visibility loss, not a layout duration or context-window limit.",
        },
    }


def seed_from(namespace: str, identity: str) -> int:
    digest = hashlib.sha256(f"{namespace}|{identity}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") & ((1 << 63) - 1)


def blocked_hash(seed: int, *parts: object) -> str:
    joined = "|".join([str(seed), *(str(part) for part in parts)])
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def speed_segments(
    profile: str, repeat: int, layout_index: int
) -> list[dict[str, Any]]:
    # 1.0 and 2.0 are the literal prior validated endpoints.  1.5 is their
    # exact midpoint and is frozen, not tuned.  Zero is accepted by the
    # non-negative-q, signed-double runtime domain and represents commanded rest.
    if profile == "EARLY_CONSTANT":
        return [{"start": 0, "stop": F, "speed_magnitude": 1.5}]
    if profile == "LATE_ONSET":
        onset = (14, 18, 22, 26, 16, 24)[layout_index] + (repeat - 1) * 2
        return [
            {"start": 0, "stop": onset, "speed_magnitude": 0.0},
            {"start": onset, "stop": F, "speed_magnitude": 1.5},
        ]
    if profile == "FAST_TRANSIT":
        return [{"start": 0, "stop": F, "speed_magnitude": 2.0}]
    if profile == "PAUSE_RESUME":
        pause_start = (12, 16, 20, 24, 14, 22)[layout_index] + (repeat - 1) * 2
        pause_duration = 16 + (repeat - 1) * 4
        pause_stop = pause_start + pause_duration
        return [
            {"start": 0, "stop": pause_start, "speed_magnitude": 1.5},
            {"start": pause_start, "stop": pause_stop, "speed_magnitude": 0.0},
            {"start": pause_stop, "stop": F, "speed_magnitude": 1.5},
        ]
    if profile == "TWO_SPEED":
        change = (14, 20, 26, 32, 38, 44)[layout_index] + (repeat - 1) * 2
        return [
            {"start": 0, "stop": change, "speed_magnitude": 1.0},
            {"start": change, "stop": F, "speed_magnitude": 2.0},
        ]
    raise P1AuthorityError(f"unknown profile: {profile}")


def start_axis(layout: str, direction: str, repeat: int) -> tuple[float, str]:
    authority = LAYOUT_AUTHORITY[layout]
    lo, hi = authority["lane"]
    if repeat == 1:
        value = 0.75 * (lo if direction == "LEFT_TO_RIGHT" else hi)
        rule = "Layouts.java pickVisibleStart primary candidate: 0.75 * upstream lane bound"
    else:
        outer = authority["start_region_ltr"][0]
        value = outer if direction == "LEFT_TO_RIGHT" else -outer
        rule = "configs/scenes/layouts.yaml outer authorized start-region bound, mirrored by direction"
    return float(value), rule


def world_position(layout: str, axis_position: float) -> list[float]:
    authority = LAYOUT_AUTHORITY[layout]
    if authority["axis"] == "x":
        return [axis_position, 4.0, authority["lane_ortho"]]
    return [authority["lane_ortho"], 4.0, axis_position]


def build_spec(
    layout: str, direction: str, profile: str, repeat: int
) -> dict[str, Any]:
    layout_index = LAYOUTS.index(layout)
    sign = 1.0 if direction == "LEFT_TO_RIGHT" else -1.0
    direction_slug = "ltr" if sign > 0 else "rtl"
    profile_slug = profile.lower()
    spec_id = f"fresh_vp_{layout.lower()}_{direction_slug}_{profile_slug}_r{repeat}"
    capture_seed = seed_from("mineocclude-large-scale-no-wall-capture-v0.1", spec_id)
    segments = speed_segments(profile, repeat, layout_index)
    signed_segments = [
        {
            "start_model_frame_idx": row["start"],
            "stop_model_frame_idx_exclusive": row["stop"],
            "signed_speed_blocks_per_second": sign * row["speed_magnitude"],
        }
        for row in segments
    ]
    start, start_rule = start_axis(layout, direction, repeat)
    noise = generate_noise_schedule(capture_seed, F, PROCESS_Q, DT_SECONDS)
    speed_by_tick = [0.0] * F
    for segment in signed_segments:
        for index in range(
            segment["start_model_frame_idx"],
            segment["stop_model_frame_idx_exclusive"],
        ):
            speed_by_tick[index] = segment["signed_speed_blocks_per_second"]
    lo, hi = LAYOUT_AUTHORITY[layout]["lane"]
    position = start
    expected_profile = []
    for index, speed in enumerate(speed_by_tick):
        position += speed * DT_SECONDS + noise.rows[index].noise_draw
        position = min(hi, max(lo, position))
        expected_profile.append(round(position, 12))
    movement_ticks = [i for i, value in enumerate(speed_by_tick) if value != 0.0]
    zero_segments = [
        row for row in signed_segments if row["signed_speed_blocks_per_second"] == 0
    ]
    changes = [row["start_model_frame_idx"] for row in signed_segments[1:]]
    camera = LAYOUT_AUTHORITY[layout]
    spec: dict[str, Any] = {
        "trajectory_spec_id": spec_id,
        "spec_version": SPEC_VERSION,
        "layout_id": layout,
        "runtime_layout_id": camera["runtime_layout_id"],
        "direction": direction,
        "profile_family": profile,
        "repeat_id": repeat,
        "capture_seed": capture_seed,
        "no_wall": True,
        "scene": "NO_WALL",
        "process_noise": {
            "q_blocks_squared_per_second": PROCESS_Q,
            "dt_seconds": DT_SECONDS,
            "format_version": "person-c-noise-schedule-v0.1",
            "producer": "numpy.random.Generator/PCG64",
            "numpy_version": noise.numpy_version,
            "schedule_sha256": schedule_hash(noise),
            "draw_count": F,
        },
        "start_position_authority": {
            "scalar_axis": camera["axis"],
            "axis_position_blocks": start,
            "world_xyz_blocks": world_position(layout, start),
            "rule": start_rule,
        },
        "end_position_authority": {
            "expected_axis_position_blocks": expected_profile[-1],
            "expected_world_xyz_blocks": world_position(layout, expected_profile[-1]),
            "expected_profile_sha256": canonical_sha256(expected_profile),
            "derivation": "exact frozen signed speed schedule plus immutable PCG64 noise schedule, clamped each tick to layout lane",
        },
        "target_range": {
            "scalar_axis_min_blocks": lo,
            "scalar_axis_max_blocks": hi,
            "clamp_required": True,
        },
        "speed_category": (
            "FAST"
            if profile == "FAST_TRANSIT"
            else "TWO_SPEED" if profile == "TWO_SPEED" else "STANDARD"
        ),
        "exact_speed_schedule": signed_segments,
        "movement_onset_model_frame_idx": min(movement_ticks),
        "stationary_segments": [
            {
                "start_model_frame_idx": row["start_model_frame_idx"],
                "stop_model_frame_idx_exclusive": row["stop_model_frame_idx_exclusive"],
                "duration_ticks": row["stop_model_frame_idx_exclusive"]
                - row["start_model_frame_idx"],
                "semantics": "zero commanded drift; frozen process-noise draw remains authoritative",
            }
            for row in zero_segments
        ],
        "pause": (
            None
            if profile != "PAUSE_RESUME"
            else {
                "start_model_frame_idx": zero_segments[0]["start_model_frame_idx"],
                "duration_ticks": zero_segments[0]["stop_model_frame_idx_exclusive"]
                - zero_segments[0]["start_model_frame_idx"],
            }
        ),
        "speed_change_model_frame_idx": (
            changes[0] if profile == "TWO_SPEED" else None
        ),
        "camera_viewpoint_authority": {
            "classification": "PART_OF_LAYOUT_IDENTITY_FIXED_WITHIN_LAYOUT",
            "viewpoint_stratum": "CANONICAL_LAYOUT_POSE",
            "canonical_feet_xyz_blocks": camera["camera_xyz"],
            "yaw_degrees": camera["yaw"],
            "pitch_degrees": 0.0,
            "fov_degrees": 70.0,
            "server_lock_required_each_recorded_tick": True,
        },
        "sheep_camera_distance_authority": {
            "configured_camera_distance_in_front_of_wall_blocks": camera["camera_dist"],
            "sheep_lane_ortho_blocks": camera["lane_ortho"],
            "variation_within_layout": False,
        },
        "expected_source_frame_count": F,
        "expected_eligible_row_count": F,
        "expected_model_frame_idx_schedule": list(range(F)),
        "expected_server_state_semantics": {
            "one_row_per_model_frame": True,
            "model_frame_idx_dense_zero_based": True,
            "layout_spec_and_attempt_identity_required": True,
            "scene": "NO_WALL",
            "wall_present": False,
            "target_count": 1,
            "target_entity": "minecraft:sheep",
            "target_color": "magenta",
            "target_no_ai": True,
            "target_tag_required": "mineocclude_experimental_target",
            "x_true_blocks_source": "authoritative wall-parallel sheep axis position",
            "speed_and_noise_consumption_must_match_spec": True,
        },
        "expected_raw_actions_semantics": {
            "one_row_per_model_frame": True,
            "action_idx_aligned_to_model_frame_idx": True,
            "camera_dx_dy_zero_except_no_scripted_impulse": True,
            "scripted_impulse": False,
            "camera_locked": True,
        },
        "model_authority_references": {
            "checkpoint": "study_design.json#/model_authority",
            "preprocessing": "study_design.json#/preprocessing_context_authority",
            "context": "study_design.json#/preprocessing_context_authority/context_semantics",
        },
        "expected_capture_artifact_patterns": {
            "attempt_root": "{experiment_runtime_root}/attempts/{trajectory_spec_id}/attempt_{attempt_number:02d}/",
            "frame_map": "frame_map.jsonl",
            "server_state": "server_state.jsonl",
            "raw_actions": "raw_actions.jsonl",
            "capture_provenance": "capture_provenance.json",
            "attempt_metadata": "attempt_metadata.json",
            "capture_package": "capture_package_v0_1.json",
            "checksums": "sha256_manifest.json",
        },
        "maximum_attempts": MAX_ATTEMPTS,
    }
    spec["spec_hash"] = canonical_sha256(spec)
    return spec


def combination_sequence() -> list[tuple[str, str, int]]:
    result = []
    for repeat in REPEATS:
        for index in range(10):
            direction = DIRECTIONS[index % 2]
            profile = PROFILES[index % len(PROFILES)]
            result.append((direction, profile, repeat))
    require(len(set(result)) == 20, "combination sequence is not complete")
    return result


def build_campaign_specs() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    by_key = {
        (layout, direction, profile, repeat): build_spec(
            layout, direction, profile, repeat
        )
        for layout in LAYOUTS
        for direction in DIRECTIONS
        for profile in PROFILES
        for repeat in REPEATS
    }
    combinations = combination_sequence()
    order = []
    ordered_specs = []
    for round_index in range(20):
        rotated_layouts = LAYOUTS[round_index % 6 :] + LAYOUTS[: round_index % 6]
        for layout in rotated_layouts:
            layout_index = LAYOUTS.index(layout)
            combo = combinations[(round_index + 2 * layout_index) % 20]
            spec = by_key[(layout, *combo)]
            position = len(order)
            stage = (
                "A"
                if position < 12
                else "B" if position < 48 else "C" if position < 84 else "D"
            )
            order.append(
                {
                    "campaign_index": position,
                    "round_index": round_index,
                    "stage": stage,
                    "trajectory_spec_id": spec["trajectory_spec_id"],
                    "spec_hash": spec["spec_hash"],
                }
            )
            ordered_specs.append(spec)
    require(len(ordered_specs) == len(by_key) == 120, "campaign is not 120 specs")
    require(
        {row["trajectory_spec_id"] for row in ordered_specs}
        == {row["trajectory_spec_id"] for row in by_key.values()},
        "campaign order is not a permutation of specs",
    )
    return sorted(by_key.values(), key=lambda row: row["trajectory_spec_id"]), order


def choose_fixed_test(
    metadata: Sequence[Mapping[str, Any]], seed: int
) -> tuple[list[Mapping[str, Any]], list[Mapping[str, Any]]]:
    selected = []
    for layout in LAYOUTS:
        rows = [row for row in metadata if row["layout_id"] == layout]
        require(len(rows) == 20, f"synthetic split requires 20 rows for {layout}")

        def score(group: tuple[Mapping[str, Any], ...]) -> tuple[Any, ...]:
            directions = Counter(row["direction"] for row in group)
            repeats = Counter(row["repeat_id"] for row in group)
            profile_duplicate_penalty = 3 - len(
                {row["profile_family"] for row in group}
            )
            direction_imbalance = abs(
                directions["LEFT_TO_RIGHT"] - directions["RIGHT_TO_LEFT"]
            )
            repeat_imbalance = abs(repeats[1] - repeats[2])
            identity = ",".join(sorted(row["trajectory_spec_id"] for row in group))
            return (
                profile_duplicate_penalty,
                direction_imbalance,
                repeat_imbalance,
                blocked_hash(seed, layout, identity),
            )

        chosen = min(itertools.combinations(rows, 3), key=score)
        selected.extend(chosen)
    selected_ids = {row["trajectory_spec_id"] for row in selected}
    training = [
        row for row in metadata if row["trajectory_spec_id"] not in selected_ids
    ]
    return selected, training


def master_ordering(
    training: Sequence[Mapping[str, Any]],
    master_index: int,
    rank_seed: int,
    rotation: int,
) -> list[Mapping[str, Any]]:
    queues: dict[str, list[Mapping[str, Any]]] = {}
    for layout in LAYOUTS:
        rows = [row for row in training if row["layout_id"] == layout]
        require(len(rows) == 17, f"training pool is not 17 for {layout}")
        queues[layout] = sorted(
            rows,
            key=lambda row: blocked_hash(
                rank_seed, "training-rank", layout, row["trajectory_spec_id"]
            ),
        )
        shift = (rotation + 3 * LAYOUTS.index(layout)) % len(rows)
        queues[layout] = queues[layout][shift:] + queues[layout][:shift]
    omitted_at_five = LAYOUTS[master_index % len(LAYOUTS)]
    other_layouts = [layout for layout in LAYOUTS if layout != omitted_at_five]
    shift = master_index % len(other_layouts)
    layout_order = other_layouts[shift:] + other_layouts[:shift] + [omitted_at_five]
    tail_pair = (LAYOUTS[master_index % 6], LAYOUTS[(master_index + 1) % 6])
    reserved = [queues[layout].pop() for layout in tail_pair]
    result = []
    while any(queues.values()):
        for layout in layout_order:
            if queues[layout]:
                result.append(queues[layout].pop(0))
    result.extend(reserved)
    require(len(result) == 102, "master ordering length differs")
    return result


def build_synthetic_split(
    metadata: Sequence[Mapping[str, Any]], split_seed: int, master_seeds: Sequence[int]
) -> dict[str, Any]:
    test, training = choose_fixed_test(metadata, split_seed)
    training_ids = [str(row["trajectory_spec_id"]) for row in training]
    exposure: Counter[str] = Counter({identity: 0 for identity in training_ids})
    masters = []
    rotations = []
    for index in range(20):
        active_sizes = [
            size
            for size, replicate_count in zip(
                TRAINING_SIZES, SUBSET_REPLICATES, strict=True
            )
            if index < replicate_count
        ]
        candidates = []
        for rotation in range(17):
            ordering = master_ordering(training, index, split_seed, rotation)
            contribution: Counter[str] = Counter()
            for size in active_sizes:
                contribution.update(
                    str(row["trajectory_spec_id"]) for row in ordering[:size]
                )
            projected = [
                exposure[identity] + contribution[identity] for identity in training_ids
            ]
            total = sum(projected)
            score = (
                max(projected) - min(projected),
                sum((value * len(projected) - total) ** 2 for value in projected),
                blocked_hash(master_seeds[index], "rotation", rotation),
            )
            candidates.append((score, rotation, ordering, contribution))
        _, selected_rotation, selected_ordering, selected_contribution = min(
            candidates, key=lambda row: row[0]
        )
        rotations.append(selected_rotation)
        masters.append(selected_ordering)
        exposure.update(selected_contribution)
    schedules = []
    for size, replicate_count in zip(TRAINING_SIZES, SUBSET_REPLICATES, strict=True):
        for replicate in range(replicate_count):
            schedules.append(
                {
                    "size": size,
                    "replicate": replicate,
                    "master_id": f"master_{replicate:02d}",
                    "members": masters[replicate][:size],
                }
            )
    return {
        "test": test,
        "training": training,
        "masters": masters,
        "master_rotations": rotations,
        "training_exposure": dict(exposure),
        "schedules": schedules,
    }


def within_layout_derangement(
    rows: Sequence[Mapping[str, Any]], seed: int
) -> dict[str, str]:
    assignments: dict[str, str] = {}
    by_layout: defaultdict[str, list[str]] = defaultdict(list)
    for row in rows:
        by_layout[str(row["layout_id"])].append(str(row["trajectory_spec_id"]))
    for layout in sorted(by_layout):
        recipients = sorted(by_layout[layout])
        require(len(recipients) >= 2, f"cannot derange singleton layout {layout}")
        donors = list(recipients)
        layout_seed = seed_from(f"prospective-null-{seed}", layout)
        rng = random.Random(layout_seed)
        # Sattolo's algorithm: one cycle, hence no fixed point for n >= 2.
        for index in range(len(donors) - 1, 0, -1):
            other = rng.randrange(index)
            donors[index], donors[other] = donors[other], donors[index]
        require(
            all(recipient != donor for recipient, donor in zip(recipients, donors)),
            f"derangement has a fixed point for {layout}",
        )
        assignments.update(dict(zip(recipients, donors)))
    return assignments


def state_machine_contract() -> dict[str, Any]:
    def state(
        name: str,
        preconditions: list[str],
        responsibility: str,
        ack_source: str,
        ack_mode: str,
        predicate: str,
        timeout_seconds: int,
        retryable: bool,
        failures: list[str],
        next_states: list[str],
        fixed_sleep: bool = False,
    ) -> dict[str, Any]:
        return {
            "state": name,
            "entry_preconditions": preconditions,
            "controller_responsibility": responsibility,
            "authoritative_acknowledgement_source": ack_source,
            "ack_mode": ack_mode,
            "success_predicate_or_implementation_hook": predicate,
            "timeout_policy": {"seconds": timeout_seconds, "on_timeout": failures[0]},
            "retryable": retryable,
            "failure_reason_codes": failures,
            "next_legal_states": next_states,
            "fixed_sleep_necessary": fixed_sleep,
        }

    states = [
        state(
            "PRECHECK",
            ["immutable spec and hash loaded", "attempt_number <= 3"],
            "P2 orchestrator",
            "local process/filesystem checks plus current git/runtime identity",
            "LOCAL_PRECONDITION",
            "all binaries, directories, ports, qualified Python, spec hash, and prior ledger state pass",
            30,
            True,
            ["PRECHECK_FAILED"],
            ["RESET_EPISODE"],
        ),
        state(
            "RESET_EPISODE",
            ["PRECHECK passed", "no capture active"],
            "P2 orchestrator issues reset/start preparation",
            "EpisodeLifecycle transition log; no separate structured reset API exists",
            "AUTHORITATIVE_SIGNAL",
            "server reaches RESETTING for this attempt identity; P2 must bind trajectory_spec_id/spec_hash",
            30,
            True,
            ["RESET_COMMAND_FAILED", "RESET_TIMEOUT"],
            ["WAIT_RESET_ACK"],
        ),
        state(
            "WAIT_RESET_ACK",
            ["reset requested"],
            "P2 orchestrator polls lifecycle and target state",
            "EpisodeLifecycle READY transition plus targetstatus",
            "AUTHORITATIVE_SIGNAL",
            "READY for intended attempt with no retention problems",
            45,
            True,
            ["RESET_ACK_TIMEOUT", "TARGET_RETENTION_INVALID"],
            ["APPLY_LAYOUT"],
        ),
        state(
            "APPLY_LAYOUT",
            ["reset acknowledged"],
            "server runtime applies immutable Layouts.java record and NO_WALL scene",
            "start command result and server lifecycle log",
            "AUTHORITATIVE_SIGNAL",
            "requested runtime_layout_id and NO_WALL are accepted; no fallback layout",
            30,
            True,
            ["LAYOUT_APPLY_REFUSED", "UNKNOWN_LAYOUT"],
            ["VERIFY_LAYOUT"],
        ),
        state(
            "VERIFY_LAYOUT",
            ["layout applied"],
            "P2 orchestrator requests read-only geometry receipt",
            "observegeometry receipt",
            "AUTHORITATIVE_SIGNAL",
            "receipt matches layout contract and proves wall absent, target lane/markers exact",
            30,
            True,
            ["LAYOUT_RECEIPT_MISSING", "LAYOUT_GEOMETRY_MISMATCH", "WALL_PRESENT"],
            ["SET_CAMERA"],
        ),
        state(
            "SET_CAMERA",
            ["layout verified", "one client connected"],
            "server applies canonical layout pose and per-tick lock",
            "server camera placement log; FOV is not server-observable",
            "AUTHORITATIVE_SIGNAL",
            "canonical feet xyz/yaw/pitch applied and lockcam on; P2 must capture client FOV=70 receipt",
            30,
            True,
            ["CAMERA_SET_FAILED", "CLIENT_FOV_ACK_UNAVAILABLE"],
            ["VERIFY_CAMERA"],
        ),
        state(
            "VERIFY_CAMERA",
            ["canonical camera requested"],
            "P2 verifies geometry receipt, client focus, and client metadata",
            "observegeometry camera fields, xdotool focus assertion, future P2 client FOV receipt",
            "AUTHORITATIVE_SIGNAL",
            "pose exact, one Minecraft window focused, FOV receipt exact; fail closed if P2 does not add FOV receipt",
            30,
            True,
            [
                "CAMERA_POSE_MISMATCH",
                "CAMERA_FOCUS_MISMATCH",
                "CLIENT_FOV_ACK_UNAVAILABLE",
            ],
            ["SPAWN_OR_POSITION_SHEEP"],
        ),
        state(
            "SPAWN_OR_POSITION_SHEEP",
            ["camera verified", "NO_WALL layout verified"],
            "server target controller creates/positions exactly one tagged magenta sheep",
            "server target retention log",
            "AUTHORITATIVE_SIGNAL",
            "target spawn/reset operation completes for exact spec start position; explicit-start hook must be implemented by P2",
            30,
            True,
            ["TARGET_SPAWN_FAILED", "SPEC_START_POSITION_HOOK_UNAVAILABLE"],
            ["VERIFY_SHEEP_STATE"],
        ),
        state(
            "VERIFY_SHEEP_STATE",
            ["target positioned"],
            "P2 polls targetstatus and compares pose",
            "targetstatus and observegeometry target fields",
            "AUTHORITATIVE_SIGNAL",
            "one valid adult tagged magenta no-AI target at exact start xyz",
            20,
            True,
            [
                "TARGET_COUNT_MISMATCH",
                "TARGET_IDENTITY_MISMATCH",
                "TARGET_START_POSE_MISMATCH",
            ],
            ["ARM_CAPTURE"],
        ),
        state(
            "ARM_CAPTURE",
            ["layout/camera/target verified", "noise schedule hash matches spec"],
            "P2 arms capture and binds immutable piecewise speed schedule",
            "server lifecycle READY plus capture provenance preamble",
            "AUTHORITATIVE_SIGNAL",
            "spec/hash/seed/noise/speed schedule bound; current constant-drift controller lacks piecewise hook and P2 must add it",
            30,
            True,
            [
                "CAPTURE_ARM_FAILED",
                "NOISE_SCHEDULE_MISMATCH",
                "PIECEWISE_MOTION_HOOK_UNAVAILABLE",
            ],
            ["START_TRAJECTORY"],
        ),
        state(
            "START_TRAJECTORY",
            ["capture armed"],
            "server transitions after 60-tick warmup",
            "episode recording started lifecycle log and first tick-sync packet",
            "AUTHORITATIVE_SIGNAL",
            "recording starts once for intended attempt and model_frame_idx 0 arrives",
            20,
            True,
            ["RECORDING_START_TIMEOUT", "FIRST_TICK_MISSING"],
            ["RUN_TRAJECTORY"],
        ),
        state(
            "RUN_TRAJECTORY",
            ["recording started"],
            "server advances exact speed/noise schedule; client captures each tick",
            "server_state, tick-sync, frame_map, raw_actions streams",
            "AUTHORITATIVE_SIGNAL",
            "exactly 60 continuous ticks follow spec with target/camera retention valid",
            10,
            True,
            [
                "TICK_GAP",
                "MOTION_SCHEDULE_MISMATCH",
                "CAMERA_DRIFT",
                "TARGET_RETENTION_FAILURE",
                "UNINTENDED_TELEPORT",
            ],
            ["STOP_CAPTURE"],
        ),
        state(
            "STOP_CAPTURE",
            ["60th tick emitted"],
            "server ends episode and client drains asynchronous PNG queue",
            "episode ended log; current client exposes no queue-drained acknowledgement",
            "ACK_MODE=BOUNDED_TIMING_FALLBACK",
            "end log observed, then bounded <=5s stability poll confirms 60 immutable frames and no new writes",
            10,
            True,
            ["STOP_TIMEOUT", "ASYNC_CAPTURE_DRAIN_TIMEOUT"],
            ["VALIDATE_CAPTURE"],
            True,
        ),
        state(
            "VALIDATE_CAPTURE",
            ["capture stopped and files stable"],
            "P2 applies acceptance_rules.json without model outcomes",
            "capture package, provenance, checksums, streams, geometry and schedule receipts",
            "DERIVED_VALIDATION",
            "every mandatory acceptance predicate passes",
            120,
            True,
            ["CAPTURE_VALIDATION_FAILED"],
            ["ACCEPT_OR_RETRY"],
        ),
        state(
            "ACCEPT_OR_RETRY",
            ["validation classification complete"],
            "P2 appends one ledger event and selects legal continuation",
            "fsync-complete append-only ledger record",
            "AUTHORITATIVE_SIGNAL",
            "ACCEPTED advances schedule; rejection retries identical spec if attempts remain; otherwise blocks",
            15,
            False,
            ["LEDGER_APPEND_FAILED", "MAX_ATTEMPTS_EXHAUSTED"],
            ["PRECHECK", "RESET_EPISODE", "TERMINAL_ACCEPTED", "TERMINAL_BLOCKED"],
        ),
    ]
    return {
        "artifact_id": "large-scale-no-wall-state-machine-contract-v0.1",
        "schema_version": "1.0",
        "frozen_at": P1_FROZEN_AT,
        "status": "FROZEN_PROSPECTIVE",
        "states": states,
        "acknowledgement_gaps": [
            "CLIENT_FOV_ACK_UNAVAILABLE: server records fov_status=not_server_observable; P2 must add/consume a client-side FOV receipt.",
            "SPEC_START_POSITION_HOOK_UNAVAILABLE: current start command chooses start position internally; P2 must bind exact spec start position.",
            "PIECEWISE_MOTION_HOOK_UNAVAILABLE: current SheepController exposes constant driftV only; P2 must add immutable per-tick speed consumption and logging.",
            "ASYNC_CAPTURE_QUEUE_DRAIN_ACK_UNAVAILABLE: current pilot uses a fixed sleep; P2 must use bounded file-stability polling and the declared timing fallback.",
        ],
        "fixed_sleep_policy": "Forbidden except STOP_CAPTURE bounded asynchronous-write fallback; polling and hard timeout remain mandatory.",
        "implementation_phase": "P2",
    }


def acceptance_rules() -> dict[str, Any]:
    rules = [
        (
            "REQUIRED_FILES_MISSING",
            "required_files",
            "all expected artifact paths exist and are regular files",
        ),
        (
            "SPEC_ID_OR_HASH_MISMATCH",
            "trajectory_spec_id/spec_hash",
            "attempt metadata and every bound receipt match immutable spec",
        ),
        (
            "ATTEMPT_METADATA_MISSING",
            "attempt_metadata",
            "attempt number, timestamps, controller version and exact commands exist",
        ),
        ("LAYOUT_MISMATCH", "runtime_layout_id", "layout receipt matches spec"),
        (
            "NO_WALL_MISMATCH",
            "scene/wall_present",
            "scene=NO_WALL and wall_present=false",
        ),
        (
            "CAMERA_MISMATCH",
            "camera receipt and raw_actions",
            "pose/FOV/focus/lock match and no unexplained drift",
        ),
        (
            "SHEEP_INITIAL_STATE_MISMATCH",
            "target receipt",
            "one valid tagged target at exact start xyz",
        ),
        (
            "DIRECTION_MISMATCH",
            "server_state x_true_blocks",
            "net commanded and realized direction matches spec, allowing only frozen noise",
        ),
        (
            "MOTION_SCHEDULE_MISMATCH",
            "server_state speed/noise fields",
            "every tick matches signed speed segment and noise draw",
        ),
        (
            "ONSET_MISMATCH",
            "server_state",
            "first nonzero commanded-drift tick matches spec",
        ),
        (
            "PAUSE_OR_CHANGE_MISMATCH",
            "server_state",
            "pause/change timing and duration match when applicable",
        ),
        (
            "FRAME_COUNT_MISMATCH",
            "frame_map/server_state/raw_actions/media",
            "each stream contains exactly 60 dense rows/frames",
        ),
        (
            "ELIGIBLE_ROW_SCHEDULE_MISMATCH",
            "strict visibility and preprocessing eligibility",
            "all model_frame_idx 0..59 are eligible; partial acceptance forbidden",
        ),
        (
            "TIMESTAMP_DISCONTINUITY",
            "all streams",
            "monotonic continuous tick-aligned timestamps within frozen tolerance",
        ),
        (
            "ACCIDENTAL_RESET",
            "lifecycle/server_state",
            "no reset transition during recording",
        ),
        (
            "UNINTENDED_TELEPORT",
            "server_state",
            "target motion equals schedule and clamp; no extra position jump",
        ),
        (
            "CAMERA_DRIFT",
            "server_state/raw_actions",
            "canonical pose reasserted and camera deltas zero",
        ),
        (
            "TARGET_RANGE_INVALID",
            "server_state",
            "every x_true_blocks value finite and inside layout lane",
        ),
        (
            "MODEL_CONTEXT_METADATA_MISMATCH",
            "capture metadata",
            "checkpoint/preprocessing/context references equal study authority",
        ),
        (
            "UNCLEAN_TERMINATION",
            "lifecycle/provenance",
            "one normal stop after model_frame_idx 59",
        ),
        (
            "PROVENANCE_OR_CHECKSUM_MISSING",
            "provenance/checksum manifest",
            "required hashes exist and verify",
        ),
    ]
    return {
        "artifact_id": "large-scale-no-wall-acceptance-rules-v0.1",
        "schema_version": "1.0",
        "frozen_at": P1_FROZEN_AT,
        "status": "FROZEN_PROSPECTIVE",
        "classification_enum": ["ACCEPTED", "REJECTED_WITH_REASON"],
        "maximum_attempts_per_trajectory_spec": MAX_ATTEMPTS,
        "retry_semantics": "A retry changes only attempt_number and operational timestamps/paths; it executes byte-identical scientific spec content and spec_hash.",
        "rules": [
            {"reason_code": code, "fields": fields, "acceptance_predicate": predicate}
            for code, fields, predicate in rules
        ],
        "reason_codes": [code for code, _, _ in rules]
        + [
            "PRECHECK_FAILED",
            "RESET_FAILED",
            "LAYOUT_VERIFICATION_FAILED",
            "CAMERA_VERIFICATION_FAILED",
            "TARGET_RETENTION_FAILURE",
            "CAPTURE_START_FAILED",
            "CAPTURE_STOP_FAILED",
            "MAX_ATTEMPTS_EXHAUSTED",
        ],
        "forbidden_acceptance_inputs": [
            "model activations",
            "probe predictions",
            "R2 or any decoding metric",
            "token scores/rankings",
            "future test performance",
        ],
        "acceptance_uses_decoding_outcome": False,
    }


def split_algorithm_document(
    split_seed: int, master_seeds: list[int]
) -> dict[str, Any]:
    return {
        "artifact_id": "large-scale-no-wall-future-split-algorithm-v0.1",
        "schema_version": "1.0",
        "frozen_at": P1_FROZEN_AT,
        "status": "FROZEN_ALGORITHM_NO_ACTUAL_MEMBERSHIPS",
        "apply_only_after": "P4 accepted-120 cohort lock",
        "outcome_blind": True,
        "fixed_test": {
            "count": 18,
            "per_layout": 3,
            "algorithm": "For each layout exhaustively score 3-combinations by profile duplicates, direction imbalance, repeat imbalance, then SHA-256 tie-break; choose lexicographic minimum.",
            "seed": split_seed,
            "viewpoint_balance": "singleton canonical viewpoint by design",
        },
        "training_pool": {"count": 102, "per_layout": 17},
        "blocked_hash": "SHA256(decimal_seed|'|'|ordered identity fields), lowercase hex lexical order",
        "master_orderings": {
            "count": 20,
            "seeds": master_seeds,
            "algorithm": "Create one blocked-hash base rank per layout, then for each master greedily choose one of the 17 cyclic rotations that minimizes projected cross-schedule exposure range and squared imbalance; the master seed breaks rotation-score ties. Interleave round-robin. master_index mod 6 is sixth so each N=5 prefix omits exactly that layout. Reserve one final member from each predeclared tail-pair layout at positions 100 and 101.",
            "n5_omitted_layout_sequence": [LAYOUTS[index % 6] for index in range(20)],
            "n5_omitted_layout_counts": dict(
                Counter(LAYOUTS[index % 6] for index in range(20))
            ),
            "n100_tail_pairs_first_six": [
                [LAYOUTS[index], LAYOUTS[(index + 1) % 6]] for index in range(6)
            ],
        },
        "subset_schedules": [
            {
                "training_size": size,
                "replicate_count": count,
                "master_ids": [f"master_{index:02d}" for index in range(count)],
                "membership_rule": "nested prefix of referenced master ordering",
            }
            for size, count in zip(TRAINING_SIZES, SUBSET_REPLICATES, strict=True)
        ],
        "total_subsets": sum(SUBSET_REPLICATES),
        "constraints": {
            "n5_layout_coverage": "exactly 5 of 6, one trajectory per represented layout",
            "n5_omitted_layout_balance": "counts differ by at most one across 20 subsets",
            "n_ge_15_all_six_layouts": True,
            "n100_distinct_omitted_pairs": 6,
            "training_exposure_balance": "greedy outcome-blind cyclic-rotation selection minimizes projected exposure range, then squared imbalance; deterministic master-seed hash is the final tie-break",
            "no_actual_ids_before_p4": True,
        },
        "tie_breaking": "All ties use ascending trajectory_spec_id after the seeded SHA-256 key.",
    }


def prospective_null_document(null_seeds: list[int]) -> dict[str, Any]:
    return {
        "artifact_id": "PROSPECTIVE_WITHIN_LAYOUT_TRAJECTORY_DERANGEMENT_NULL_V0_1",
        "schema_version": "1.0",
        "frozen_at": P1_FROZEN_AT,
        "status": "FROZEN_NOT_EXECUTED",
        "target_null_identical_to_prior_audited_null": False,
        "difference_from_prior": "The completed predecessor null allowed fixed points and preserved a singleton length stratum; this prospective null is a no-self-assignment derangement within each layout on a common F=60 cohort.",
        "canonical_training_subset": "split_algorithm.json master_00 N=100 nested prefix",
        "test_targets": "fixed-test true targets unchanged",
        "training_target_unit": "complete 60-row trajectory profile",
        "assignment_scope": "within layout only",
        "derangement_algorithm": "For each sorted layout recipient list, seed random.Random with the SHA-derived layout seed and apply Sattolo swaps i=n-1..1 with j=randrange(i); copy the donor's complete target profile in original row order.",
        "no_self_assignment": True,
        "temporal_order_and_frame_alignment_preserved": True,
        "refit_inside_each_replicate": [
            "training-only scaler",
            "training-only token ranking",
            "BEST-K selection",
            "ridge alpha selection",
            "final ridge fit",
        ],
        "B": 49,
        "seeds": null_seeds,
        "empirical_upper_tail": "(1 + count(null_equal_layout_macro_R2 >= observed_equal_layout_macro_R2)) / 50",
        "tail_alpha": 0.05,
        "minimum_layout_count_required": 2,
        "expected_canonical_n100_layout_counts": "four layouts with 17 and two with 16; minimum 16",
        "execution_phase": "P7_or_roadmap_designated_analysis_phase_not_P1",
    }


def profile_audit_document() -> dict[str, Any]:
    return {
        "artifact_id": "large-scale-no-wall-profile-diversity-audit-contract-v0.1",
        "schema_version": "1.0",
        "frozen_at": P1_FROZEN_AT,
        "status": "FROZEN_FOR_P4",
        "activation_or_probe_inputs_forbidden": True,
        "required_counts": {
            "total": 120,
            "per_layout": 20,
            "per_direction_per_layout": 10,
            "per_layout_direction_profile_cell": 2,
            "unique_repeat_settings_per_cell": 2,
            "viewpoint_strata": ["CANONICAL_LAYOUT_POSE"],
        },
        "distribution_audits": [
            "start and end axis positions",
            "finite target range and target variance overall/by layout",
            "signed and absolute speed distributions",
            "movement onset distributions",
            "pause start/duration distributions",
            "speed-change distributions",
            "process-noise schedule uniqueness",
        ],
        "time_target_correlation": {
            "variables": "normalized model_frame_idx versus x_true_blocks",
            "report": ["overall", "by profile family", "by direction"],
            "global_absolute_correlation_max": 0.10,
            "aggregate_cancellation_is_sufficient": False,
            "required_companion_reporting": "family and direction strata plus pairwise profile similarity",
        },
        "pairwise_profile_similarity": {
            "profile": "the complete 60-row x_true_blocks vector after per-trajectory finite-value validation; Pearson is invariant to affine start/range differences",
            "pairs": "all unordered off-diagonal accepted trajectory pairs",
            "statistic": "absolute Pearson correlation",
            "high_similarity_threshold_inclusive": 0.95,
            "maximum_fraction_high_similarity": 0.20,
            "zero_variance_policy": "reject trajectory before similarity audit",
        },
        "additional_validity_thresholds": {
            "all_layout_direction_profile_repeat_cells_present": True,
            "all_target_profiles_finite": True,
            "target_variance_each_trajectory_gt": 0.0,
            "all_expected_model_frame_indices_present": True,
            "no_unplanned_clamp_plateau": True,
        },
    }


def ledger_contract() -> dict[str, Any]:
    return {
        "storage_format": "append-only JSONL, one canonical JSON object per line, fsync after append",
        "record_types": [
            "SPEC_REGISTERED",
            "STATE_TRANSITION",
            "ATTEMPT_CLASSIFIED",
            "DURABLE_UPLOAD",
        ],
        "common_required_fields": [
            "ledger_schema_version",
            "record_id",
            "record_type",
            "recorded_at_utc",
            "trajectory_spec_id",
            "spec_hash",
            "attempt_number",
            "previous_record_sha256",
            "record_sha256",
        ],
        "state_transition_fields": [
            "from_state",
            "to_state",
            "reason_code",
            "ack_source",
            "controller_version",
        ],
        "attempt_classification_fields": [
            "classification",
            "failure_reason_codes",
            "local_output_root",
            "artifact_sha256_manifest",
            "durable_prefix",
            "durable_upload_status",
        ],
        "immutability": "CREATE/APPEND only; record_sha256 hashes the canonical row without record_sha256; previous_record_sha256 forms a chain; old rows may never be edited or deleted.",
        "resume_semantics": {
            "skip": "all specs with a valid ACCEPTED ATTEMPT_CLASSIFIED record",
            "continue": "earliest campaign-order spec without ACCEPTED, unless it has three rejected attempts, which is BLOCKED",
            "identity": "never regenerate or mutate trajectory_spec_id/spec_hash",
            "attempt_number": "one plus highest prior attempt for the exact spec",
            "old_rows_mutable": False,
        },
    }


def study_design_document(authority: Mapping[str, Any]) -> dict[str, Any]:
    model = authority["model_identity"]
    return {
        "artifact_id": "large-scale-no-wall-study-design-v0.1",
        "schema_version": "1.0",
        "frozen_at": P1_FROZEN_AT,
        "status": "FROZEN_PROSPECTIVE_NO_FRESH_OUTCOMES",
        "lineage": {
            "branch": BRANCH,
            "p0_head": P0_HEAD,
            "predecessor_sha": PREDECESSOR_SHA,
            "frozen_mvp_sha": FROZEN_MVP_SHA,
        },
        "cohort": {
            "fresh_total": 120,
            "layouts": list(LAYOUTS),
            "trajectories_per_layout": 20,
            "future_fixed_test": 18,
            "future_fixed_test_per_layout": 3,
            "future_train_pool": 102,
            "future_train_pool_per_layout": 17,
            "historical_18_included_in_primary": False,
            "fresh_layout_generalization": "DEFERRED_BY_DESIGN",
        },
        "capture_rows": authority["f_resolution"],
        "viewpoint_authority": {
            "status": "PART_OF_LAYOUT_IDENTITY_FIXED_WITHIN_LAYOUT",
            "variation_within_layout": False,
            "strata": ["CANONICAL_LAYOUT_POSE"],
            "layout_authority": LAYOUT_AUTHORITY,
        },
        "motion_authority": {
            "same_plainly_visible_no_wall_task": True,
            "tick_hz": TICK_HZ,
            "dt_seconds": DT_SECONDS,
            "process_q_blocks_squared_per_second": PROCESS_Q,
            "signed_speed_runtime_domain": "finite signed double; lane-clamped each tick",
            "validated_prior_speed_endpoints": [1.0, 2.0],
            "speed_strata": {
                "SLOW": 1.0,
                "STANDARD": 1.5,
                "FAST": 2.0,
                "STATIONARY_COMMANDED_DRIFT": 0.0,
            },
            "standard_derivation": "exact arithmetic midpoint of validated 1.0 and 2.0 endpoints; not tuned from outcomes",
            "start_ranges": {
                layout: values["start_region_ltr"]
                for layout, values in LAYOUT_AUTHORITY.items()
            },
            "reverse_start_rule": "mirror the LTR start region and use the negative-drift branch already present in pickVisibleStart",
            "target_ranges": {
                layout: values["lane"] for layout, values in LAYOUT_AUTHORITY.items()
            },
            "onset_tick_range": [0, 28],
            "pause_start_tick_range": [12, 26],
            "pause_duration_tick_values": [16, 20],
            "two_speed_values": [1.0, 2.0],
            "two_speed_change_tick_range": [14, 46],
            "piecewise_motion_runtime_hook_status": "REQUIRED_P2_ADDITIVE_IMPLEMENTATION_GAP",
        },
        "model_authority": {
            "fixed_layer": 4,
            "visual_token_grid": [14, 24],
            "visual_token_count": 336,
            "hidden_width": 2048,
            "full_feature_dimension": 688128,
            "checkpoint_path": model["checkpoint_path"],
            "checkpoint_sha256_inherited_not_recomputed": model["checkpoint_sha256"],
            "vae_path": model["vae_path"],
            "vae_sha256_inherited_not_recomputed": model["vae_sha256"],
        },
        "preprocessing_context_authority": {
            **authority["preprocessing_identity"],
            "context_semantics": authority["context_semantics"],
        },
        "representations": {
            "core": ["GLOBAL_MEAN", "FULL_TOKEN_GRID", "BEST_K_TOKENS"],
            "secondary": ["COARSE_2x6"],
            "feature_dimensions": {
                "GLOBAL_MEAN": 2048,
                "FULL_TOKEN_GRID": 688128,
                "COARSE_2x6": 24576,
                "BEST_K_TOKENS": {str(k): k * 2048 for k in BEST_K},
            },
        },
        "ridge": {
            "alpha_grid": list(ALPHA_GRID),
            "literal_authority_verified": True,
            "scaling": "fit on training rows only",
            "intercept": True,
            "alpha_tie_break": "smallest alpha among equal validation scores",
        },
        "best_k": {
            "candidates": list(BEST_K),
            "token_unit_features": 2048,
            "selection_scope": "repeat independently inside every training subset and every null replicate",
            "ranking": "Within each inner training fold, fit one 2048-feature ridge per token using inner-training-only scaling/alpha selection; score by equal-layout macro validation R2; aggregate token score by mean across inner folds; ties use ascending token index.",
            "joint_selection": "For each K, take top K training-ranked tokens, choose alpha by grouped inner CV equal-layout macro R2; select K then alpha by score, smaller K, then smaller alpha.",
            "refit": "Recompute ranking and selected K/alpha using training data only, refit on all subset rows, evaluate untouched fixed test.",
            "leakage_prohibitions": [
                "no fixed-test rows or targets in scaling, ranking, K selection, alpha selection, or stopping",
                "no token ranking reused across subset replicates",
                "no observed/null selection state reused across null replicates",
                "no historical 18 trajectories in primary fit or evaluation",
            ],
        },
        "learning_curve": {
            "training_sizes": list(TRAINING_SIZES),
            "subset_replicates": list(SUBSET_REPLICATES),
            "total_subsets": sum(SUBSET_REPLICATES),
            "n5_layout_coverage": "5_OF_6",
            "n5_omitted_layout_balanced": True,
            "n15_n40_n70_n100_all_six_layouts": True,
            "nested_prefixes": True,
        },
        "targets_and_metrics": {
            "primary_target": "x_true_blocks",
            "primary_generalization": "fresh held-out trajectories from six known layouts",
            "primary_metric": "equal-layout macro held-out R2",
            "secondary_metrics": [
                "pooled held-out R2",
                "per-layout held-out R2",
                "equal-layout macro held-out MAE",
                "equal-layout macro held-out NMAE using training-target standard deviation",
                "per-trajectory held-out R2 where defined",
                "selected alpha/K/token identities and runtime/resource accounting",
            ],
        },
        "adjudication": {
            "rule_ids": [
                "PROFILE_DIVERSITY_GATE_V0_1",
                "PROSPECTIVE_DERANGEMENT_NULL_SEPARATION_V0_1",
                "SCALING_CURVE_DESCRIPTIVE_V0_1",
                "BEST_K_VS_FULL_DESCRIPTIVE_V0_1",
            ],
            "profile_global_abs_time_target_correlation_max": 0.10,
            "profile_high_similarity_fraction_max": 0.20,
            "profile_high_similarity_abs_pearson_threshold": 0.95,
            "prospective_null_upper_tail_alpha": 0.05,
            "performance_effect_thresholds": "No additional confirmatory effect-size threshold was supplied; scaling and BEST-K contrasts remain predeclared descriptive estimates with uncertainty, never silently converted to pass/fail.",
        },
        "fresh_outcome_blind": True,
        "source_authority": authority["source_references"],
    }


def capture_campaign_document(
    specs: list[dict[str, Any]], order: list[dict[str, Any]]
) -> dict[str, Any]:
    return {
        "artifact_id": "large-scale-no-wall-capture-campaign-v0.1",
        "schema_version": "1.0",
        "frozen_at": P1_FROZEN_AT,
        "status": "FROZEN_PROSPECTIVE",
        "campaign_shape": {
            "layouts": 6,
            "directions": 2,
            "profile_families": 5,
            "repeats_per_cell": 2,
            "trajectory_spec_count": 120,
            "capture_replicates_are_not_command_identical_duplicates": True,
        },
        "stage_cumulative_counts": {"A": 12, "B": 48, "C": 84, "D": 120},
        "stage_a_semantics": "First two balanced rounds: exactly two specs/layout, opposite directions within layout, distinct profiles, and all five profile families represented overall.",
        "campaign_order_algorithm": "20 balanced rounds; rotate layout order by round; map each layout through its even-offset permutation of the complete 20 direction/profile/repeat combinations.",
        "campaign_order": order,
        "trajectory_specs": specs,
        "retry_policy": {
            "maximum_attempts_per_spec": MAX_ATTEMPTS,
            "retry_identical_spec_hash": True,
            "attempt_number_not_part_of_spec_id": True,
        },
        "resume_ledger_contract": ledger_contract(),
        "implementation_phase": "P2",
    }


def seed_manifest_document(specs: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    split_seed = seed_from("mineocclude-large-scale-split-v0.1", "fixed-test")
    master_seeds = [
        seed_from("mineocclude-large-scale-split-master-v0.1", str(index))
        for index in range(20)
    ]
    null_seeds = [
        seed_from("mineocclude-prospective-null-v0.1", str(index))
        for index in range(49)
    ]
    return {
        "artifact_id": "large-scale-no-wall-seed-manifest-v0.1",
        "schema_version": "1.0",
        "frozen_at": P1_FROZEN_AT,
        "seed_algorithm": "unsigned lower-63-bit big-endian integer from first eight SHA256 bytes of '<namespace>|<identity>'",
        "capture_seeds": [
            {
                "trajectory_spec_id": row["trajectory_spec_id"],
                "seed": row["capture_seed"],
            }
            for row in specs
        ],
        "split_fixed_test_seed": split_seed,
        "split_master_seeds": master_seeds,
        "prospective_null_seeds": null_seeds,
        "all_capture_seeds_unique": len({row["capture_seed"] for row in specs}) == 120,
        "outcome_dependent": False,
    }


def validate_documents(documents: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    campaign = documents["capture_campaign.json"]
    specs = campaign["trajectory_specs"]
    order = campaign["campaign_order"]
    require(len(specs) == 120, "spec count")
    require(len({row["trajectory_spec_id"] for row in specs}) == 120, "spec ids")
    require(len({row["spec_hash"] for row in specs}) == 120, "spec hashes")
    for spec in specs:
        body = dict(spec)
        spec_hash = body.pop("spec_hash")
        require(canonical_sha256(body) == spec_hash, "spec hash verification")
        require(
            spec["expected_model_frame_idx_schedule"] == list(range(F)), "F schedule"
        )
        require(spec["expected_eligible_row_count"] == F, "F count")
        lo = spec["target_range"]["scalar_axis_min_blocks"]
        hi = spec["target_range"]["scalar_axis_max_blocks"]
        start = spec["start_position_authority"]["axis_position_blocks"]
        end = spec["end_position_authority"]["expected_axis_position_blocks"]
        require(lo <= start <= hi and lo <= end <= hi, "motion outside lane")
        require(spec["maximum_attempts"] == 3, "retry limit")
    counts = Counter(row["layout_id"] for row in specs)
    require(counts == {layout: 20 for layout in LAYOUTS}, "layout counts")
    for layout in LAYOUTS:
        for direction in DIRECTIONS:
            require(
                sum(
                    row["layout_id"] == layout and row["direction"] == direction
                    for row in specs
                )
                == 10,
                "direction/layout count",
            )
            for profile in PROFILES:
                cell = [
                    row
                    for row in specs
                    if row["layout_id"] == layout
                    and row["direction"] == direction
                    and row["profile_family"] == profile
                ]
                require(len(cell) == 2, "cell count")
                require(
                    cell[0]["capture_seed"] != cell[1]["capture_seed"], "repeat seeds"
                )
                require(
                    canonical_bytes(cell[0]["exact_speed_schedule"])
                    != canonical_bytes(cell[1]["exact_speed_schedule"])
                    or cell[0]["start_position_authority"]
                    != cell[1]["start_position_authority"],
                    "command-identical repeat",
                )
    require(
        len(order) == 120 and len({row["trajectory_spec_id"] for row in order}) == 120,
        "order permutation",
    )
    stage_a_ids = {row["trajectory_spec_id"] for row in order if row["stage"] == "A"}
    stage_a = [row for row in specs if row["trajectory_spec_id"] in stage_a_ids]
    require(len(stage_a) == 12, "stage A count")
    for layout in LAYOUTS:
        rows = [row for row in stage_a if row["layout_id"] == layout]
        require(
            len(rows) == 2
            and len({row["direction"] for row in rows}) == 2
            and len({row["profile_family"] for row in rows}) == 2,
            "stage A balance",
        )
    require(
        Counter(row["stage"] for row in order) == {"A": 12, "B": 36, "C": 36, "D": 36},
        "stage cumulative shape",
    )

    machine = documents["state_machine_contract.json"]
    state_names = {row["state"] for row in machine["states"]}
    for row in machine["states"]:
        require(
            row["ack_mode"]
            in {
                "LOCAL_PRECONDITION",
                "AUTHORITATIVE_SIGNAL",
                "DERIVED_VALIDATION",
                "ACK_MODE=BOUNDED_TIMING_FALLBACK",
            },
            "ack mode",
        )
        require(row["authoritative_acknowledgement_source"], "ack source")
        for next_state in row["next_legal_states"]:
            require(
                next_state in state_names or next_state.startswith("TERMINAL_"),
                "state graph",
            )
    acceptance = documents["acceptance_rules.json"]
    require(acceptance["maximum_attempts_per_trajectory_spec"] == 3, "acceptance retry")
    require(not acceptance["acceptance_uses_decoding_outcome"], "acceptance leakage")

    seeds = documents["seed_manifest.json"]
    require(
        len(seeds["capture_seeds"])
        == len({row["seed"] for row in seeds["capture_seeds"]})
        == 120,
        "capture seed count",
    )
    require(len(seeds["prospective_null_seeds"]) == 49, "null seeds")
    synthetic = build_synthetic_split(
        specs, seeds["split_fixed_test_seed"], seeds["split_master_seeds"]
    )
    synthetic_replay = build_synthetic_split(
        specs, seeds["split_fixed_test_seed"], seeds["split_master_seeds"]
    )
    require(
        canonical_sha256(synthetic) == canonical_sha256(synthetic_replay),
        "split algorithm is not deterministic",
    )
    require(
        len(synthetic["test"]) == 18 and len(synthetic["training"]) == 102,
        "split counts",
    )
    require(
        Counter(row["layout_id"] for row in synthetic["test"])
        == {layout: 3 for layout in LAYOUTS},
        "test balance",
    )
    require(len(synthetic["schedules"]) == 62, "subset count")
    exposure_values = list(synthetic["training_exposure"].values())
    require(
        max(exposure_values) - min(exposure_values) <= 5,
        "training exposure balancing differs",
    )
    n5 = [row for row in synthetic["schedules"] if row["size"] == 5]
    omitted = Counter()
    for subset in n5:
        present = {row["layout_id"] for row in subset["members"]}
        require(len(present) == 5, "N5 layout coverage")
        omitted.update(set(LAYOUTS) - present)
    require(max(omitted.values()) - min(omitted.values()) <= 1, "N5 omission balance")
    for subset in synthetic["schedules"]:
        if subset["size"] >= 15:
            require(
                {row["layout_id"] for row in subset["members"]} == set(LAYOUTS),
                "N>=15 coverage",
            )
    n100 = [row for row in synthetic["schedules"] if row["size"] == 100]
    training_ids = {row["trajectory_spec_id"] for row in synthetic["training"]}
    omitted_pairs = []
    for subset in n100:
        member_ids = {row["trajectory_spec_id"] for row in subset["members"]}
        omitted_pairs.append(frozenset(training_ids - member_ids))
    require(len(set(omitted_pairs)) == 6, "N100 omitted pair distinctness")
    canonical_n100 = n100[0]["members"]
    layout_counts = Counter(row["layout_id"] for row in canonical_n100)
    require(min(layout_counts.values()) >= 16, "null layout size")
    for null_seed in seeds["prospective_null_seeds"]:
        assignments = within_layout_derangement(canonical_n100, null_seed)
        require(len(assignments) == 100, "null assignment count")
        row_by_id = {row["trajectory_spec_id"]: row for row in canonical_n100}
        require(
            all(
                recipient != donor
                and row_by_id[recipient]["layout_id"] == row_by_id[donor]["layout_id"]
                for recipient, donor in assignments.items()
            ),
            "null derangement",
        )
    return {
        "status": "PASS",
        "trajectory_spec_count": 120,
        "unique_spec_ids": 120,
        "unique_spec_hashes": 120,
        "stage_a_count": 12,
        "subset_count": 62,
        "split_determinism": "PASS",
        "training_exposure_min": min(exposure_values),
        "training_exposure_max": max(exposure_values),
        "n5_omitted_counts": dict(omitted),
        "n100_distinct_omitted_pairs": 6,
        "null_seed_count": 49,
        "synthetic_derangement": "PASS",
    }


def build_documents() -> dict[str, dict[str, Any]]:
    authority = verify_literal_authority()
    specs, order = build_campaign_specs()
    seed_manifest = seed_manifest_document(specs)
    documents: dict[str, dict[str, Any]] = {
        "study_design.json": study_design_document(authority),
        "capture_campaign.json": capture_campaign_document(specs, order),
        "state_machine_contract.json": state_machine_contract(),
        "acceptance_rules.json": acceptance_rules(),
        "seed_manifest.json": seed_manifest,
        "split_algorithm.json": split_algorithm_document(
            seed_manifest["split_fixed_test_seed"], seed_manifest["split_master_seeds"]
        ),
        "prospective_null_authority.json": prospective_null_document(
            seed_manifest["prospective_null_seeds"]
        ),
        "profile_audit_contract.json": profile_audit_document(),
    }
    validation = validate_documents(documents)
    return documents | {"_validation": validation}


def lock_document(
    artifact_id: str, source_name: str, source_path: Path
) -> dict[str, Any]:
    return {
        "artifact_id": artifact_id,
        "schema_version": "1.0",
        "frozen_at": P1_FROZEN_AT,
        "status": "LOCKED",
        "source_path": str(source_path.relative_to(ROOT)),
        "source_sha256": sha256_file(source_path),
        "source_byte_size": source_path.stat().st_size,
        "p0_head": P0_HEAD,
        "fresh_outcomes_used": False,
    }


def artifact_reference(path: Path) -> dict[str, Any]:
    return {
        "path": str(path.relative_to(ROOT)),
        "sha256": sha256_file(path),
        "byte_size": path.stat().st_size,
    }


def write_documents() -> dict[str, Any]:
    built = build_documents()
    validation = built.pop("_validation")
    for name, document in built.items():
        write_json(PACKAGE / name, document)
    study_lock = lock_document(
        "large-scale-no-wall-study-design-lock-v0.1",
        "study_design.json",
        PACKAGE / "study_design.json",
    )
    campaign_lock = lock_document(
        "large-scale-no-wall-capture-campaign-lock-v0.1",
        "capture_campaign.json",
        PACKAGE / "capture_campaign.json",
    )
    write_json(PACKAGE / "study_design.lock.json", study_lock)
    write_json(PACKAGE / "capture_campaign.lock.json", campaign_lock)
    artifact_names = [
        "study_design.json",
        "study_design.lock.json",
        "capture_campaign.json",
        "capture_campaign.lock.json",
        "state_machine_contract.json",
        "acceptance_rules.json",
        "seed_manifest.json",
        "split_algorithm.json",
        "prospective_null_authority.json",
        "profile_audit_contract.json",
    ]
    receipt = {
        "artifact_id": "large-scale-no-wall-p1-receipt-v0.1",
        "schema_version": "1.0",
        "recorded_at": P1_FROZEN_AT,
        "phase": "P1",
        "status": "PASS",
        "branch": BRANCH,
        "p0_head": P0_HEAD,
        "predecessor_sha": PREDECESSOR_SHA,
        "frozen_mvp_sha": FROZEN_MVP_SHA,
        "qualified_python": "/home/sagemaker-user/.conda/envs/mineworld/bin/python",
        "durable_s3_root": "s3://sagemaker-us-east-1-323206973672/mineocclude/",
        "experiment_s3_prefix": "s3://sagemaker-us-east-1-323206973672/mineocclude/exploratory_large_scale_no_wall_scaling_best_k_v0_1/",
        "authority_resolution": {
            "layer": 4,
            "token_grid": [14, 24],
            "token_count": 336,
            "hidden_width": 2048,
            "full_feature_dimension": 688128,
            "alpha_grid": list(ALPHA_GRID),
            "alpha_authority_verified": True,
            "expected_source_frame_count": 60,
            "eligible_rows_per_trajectory_f": 60,
            "f_common_across_all_layouts": True,
            "historical_l06_51_row_cause": "source frames 0..59 existed; strict visibility quarantined 51..59 only",
        },
        "viewpoint": {
            "status": "PART_OF_LAYOUT_IDENTITY_FIXED_WITHIN_LAYOUT",
            "variation_within_layout": False,
            "strata": ["CANONICAL_LAYOUT_POSE"],
        },
        "campaign": {
            "trajectory_spec_count": 120,
            "specs_per_layout": 20,
            "directions": list(DIRECTIONS),
            "profile_families": list(PROFILES),
            "repeats_per_cell": 2,
            "non_identical_repeats": True,
            "stage_cumulative": {"A": 12, "B": 48, "C": 84, "D": 120},
        },
        "acknowledgement_gaps": documents_ack_gaps(built),
        "validation": validation,
        "validation_execution": {
            "generator_replay_check": "PASS",
            "focused_tests": {
                "command": "/home/sagemaker-user/.conda/envs/mineworld/bin/python -m pytest -q tests/diagnostics/test_large_scale_no_wall_p1_authority.py",
                "result": "11 passed",
            },
            "python_compile": {
                "interpreter": "/home/sagemaker-user/.conda/envs/mineworld/bin/python",
                "files": [
                    "scripts/build_large_scale_no_wall_p1_authority.py",
                    "tests/diagnostics/test_large_scale_no_wall_p1_authority.py",
                ],
                "result": "PASS",
            },
            "format": {
                "formatter": "/opt/conda/bin/black 26.5.1",
                "files": [
                    "scripts/build_large_scale_no_wall_p1_authority.py",
                    "tests/diagnostics/test_large_scale_no_wall_p1_authority.py",
                ],
                "result": "PASS",
            },
            "git_diff_check": "PASS",
        },
        "artifacts": [artifact_reference(PACKAGE / name) for name in artifact_names],
        "scope": {
            "fresh_trajectories_collected": 0,
            "minecraft_started": False,
            "java_xvfb_provisioned": False,
            "fresh_activations_extracted": 0,
            "fresh_r2_computed": False,
            "predecessor_modified": False,
            "frozen_mvp_modified": False,
            "p2_started": False,
        },
        "safe_for_p2_after_commit_push": True,
        "blocker": None,
    }
    write_json(PACKAGE / "p1_receipt.json", receipt)
    return receipt


def documents_ack_gaps(documents: Mapping[str, Mapping[str, Any]]) -> list[str]:
    return list(documents["state_machine_contract.json"]["acknowledgement_gaps"])


def check_committed_outputs() -> None:
    built = build_documents()
    built.pop("_validation")
    for name, expected in built.items():
        observed = load_json(PACKAGE / name)
        require(observed == expected, f"generated artifact differs: {name}")
    study = load_json(PACKAGE / "study_design.lock.json")
    campaign = load_json(PACKAGE / "capture_campaign.lock.json")
    require(
        study["source_sha256"] == sha256_file(PACKAGE / "study_design.json"),
        "study lock",
    )
    require(
        campaign["source_sha256"] == sha256_file(PACKAGE / "capture_campaign.json"),
        "campaign lock",
    )
    receipt = load_json(PACKAGE / "p1_receipt.json")
    for ref in receipt["artifacts"]:
        require(
            sha256_file(ROOT / ref["path"]) == ref["sha256"],
            f"receipt artifact mismatch: {ref['path']}",
        )


def git_output(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        check_committed_outputs()
        print("P1_AUTHORITY_REPLAY_CHECK=PASS")
        return 0
    require(git_output("branch", "--show-current") == BRANCH, "wrong branch")
    require(
        git_output("rev-parse", "HEAD") == P0_HEAD, "P1 must begin at exact P0 HEAD"
    )
    receipt = write_documents()
    print(
        json.dumps(
            {
                "status": receipt["status"],
                "artifacts": len(receipt["artifacts"]) + 1,
                "validation": receipt["validation"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
