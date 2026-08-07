#!/usr/bin/env python3
"""Prepare the six-layout, non-scientific v0.4 calibration-image session."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from mineocclude.data.noise_schedule import generate_noise_schedule, serialize_schedule  # noqa: E402


SERVER = Path(r"C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\server")
CLIENT = Path(r"C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\client")
SOURCE_COMMIT = "8ed87e80cd809a7b8b97861dda6bbc79d29e2aac"
RUNTIME_SOURCE_COMMIT = "538a176e1c83dc3b40e220dee8ebb2ac841bd9b4"
GEOMETRY_VERSION = "person-c-layout-config-v0.4"
GEOMETRY_SHA256 = "34495d650d6a8c62b00a916796c90389b48f80d8f20a23eac93207758e993f5d"
JAR_SHA256 = "9ecbb5e85b249409d38428ea479c3f09ec97dd884a97ecb48d79590e4c03de52"
OPTIONS_SHA256 = "13a43adde78280041f7adc29367b0a61ced6a9549f2430d9083a88665a0d9895"
SERVER_PROPERTIES_SHA256 = "fbe750e18b1040eaf4d22ff73fa3492638822c726825c50fb249be240eea4c6e"
WARMUP_TICKS = 12000
RECORD_TICKS = 20
FRAMEBUFFER = {"width_pixels": 1920, "height_pixels": 1046}
FOV_DEGREES = 70.0

EPISODES = [
    ("layout_01", 12701, 202608031701),
    ("layout_02", 12702, 202608031702),
    ("layout_03", 12703, 202608031703),
    ("layout_04", 12704, 202608031704),
    ("layout_05", 12705, 202608031705),
    ("layout_06", 12706, 202608031706),
]
MARKER_ORDER = ["near_west", "near_east", "far_east", "far_west"]

GEOMETRY = REPO / "configs/scenes/layouts_v0_4.yaml"
CLOSURE = REPO / "docs/status/person_c_c1_closure_v0_1/c1_closure_status.json"
ENVIRONMENT_LOCK = REPO / "docs/status/person_c_c1_runtime_ingestion_v0_1/final_environment_lock_receipt.json"
RENDER_SETTINGS = REPO / "docs/status/person_c_c1_runtime_ingestion_v0_1/render_settings_receipt.json"
SERVER_MANIFEST = REPO / "docs/status/person_c_c1_runtime_provisioning_v0_2/server_runtime_manifest.json"
CLIENT_MANIFEST = REPO / "docs/status/person_c_c1_runtime_provisioning_v0_2/client_runtime_manifest.json"
REFIT_HANDOFF = REPO / "docs/status/person_c_to_person_e_homography_refit_v0_1/refit_input_authority.json"
REFIT_HANDOFF_INVENTORY = REPO / "docs/status/person_c_to_person_e_homography_refit_v0_1/sha256_inventory.json"
FINALIZER = REPO / "scripts/person_c/finalize-e-refit-calibration-v0-4.ps1"
DOC_DIR = REPO / "docs/status/person_c_to_person_e_calibration_images_v0_4_v0_1"
CONFIG_DIR = REPO / "configs/collection/person_c_e_refit_calibration_v0_4_v0_1"
REPO_SCHEDULE_DIR = CONFIG_DIR / "schedules"
RUNTIME_SCHEDULE_DIR = SERVER / "mineocclude_schedules"
SERVER_EVIDENCE_DIR = SERVER / "e_refit_calibration_v0_4_v0_1"
CLIENT_EVIDENCE_DIR = CLIENT / "e_refit_calibration_v0_4_v0_1"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git_blob(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


def dump(value: Any) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def identity(path: Path, *, display: str | None = None) -> dict[str, Any]:
    data = path.read_bytes()
    return {"path": display or str(path.resolve()), "size_bytes": len(data), "sha256": sha256(data)}


def repo_identity(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    return {
        "path": path.relative_to(REPO).as_posix(),
        "size_bytes": len(data),
        "sha256": sha256(data),
        "git_blob": git_blob(data),
    }


def generated_identity(path: Path, data: bytes, *, repo_relative: bool = True) -> dict[str, Any]:
    display = path.relative_to(REPO).as_posix() if repo_relative else str(path.resolve())
    return {"path": display, "size_bytes": len(data), "sha256": sha256(data)}


def marker_rows(layout: dict[str, Any]) -> list[dict[str, Any]]:
    by_role = {row["role"]: row for row in layout["markers"]}
    return [
        {
            "marker_id": role,
            "color": by_role[role]["color"],
            "block_pos_xyz": by_role[role]["block_pos_xyz"],
            "top_face_centre_world_xyz": by_role[role]["top_face_centre_world_xyz"],
            "world_xz_blocks": [
                by_role[role]["top_face_centre_world_xyz"][0],
                by_role[role]["top_face_centre_world_xyz"][2],
            ],
            "image_xy_pixels": None,
        }
        for role in MARKER_ORDER
    ]


def expected_receipt_geometry(layout: dict[str, Any]) -> dict[str, Any]:
    floor = layout["floor"]
    wall = layout["wall"]
    floor_bounds = floor["bounds"]
    wall_bounds = wall["bounds"]
    axis = floor["axis"].upper()
    if axis == "X":
        receipt_floor = {
            "axis": "X",
            "axis_min_block_inclusive": floor_bounds["min_x"],
            "axis_max_block_inclusive": floor_bounds["max_x"],
            "ortho_min_block_inclusive": floor_bounds["min_z"],
            "ortho_max_block_inclusive": floor_bounds["max_z"],
            "y_block": floor_bounds["y"],
            "default_block_id": floor["block"],
            "expected_position_count": floor["observed_position_count"],
        }
        receipt_wall = {
            "axis": "X",
            "declared_axis_min_block_inclusive": wall_bounds["min_x"],
            "declared_axis_max_block_inclusive": wall_bounds["max_x"],
            "ortho_block": wall_bounds["min_z"],
            "y_min_block_inclusive": wall_bounds["min_y"],
            "y_max_block_inclusive": wall_bounds["max_y"],
            "declared_block_id": wall["block"],
            "expected_position_count": wall["observed_position_count"],
        }
    else:
        receipt_floor = {
            "axis": "Z",
            "axis_min_block_inclusive": floor_bounds["min_z"],
            "axis_max_block_inclusive": floor_bounds["max_z"],
            "ortho_min_block_inclusive": floor_bounds["min_x"],
            "ortho_max_block_inclusive": floor_bounds["max_x"],
            "y_block": floor_bounds["y"],
            "default_block_id": floor["block"],
            "expected_position_count": floor["observed_position_count"],
        }
        receipt_wall = {
            "axis": "Z",
            "declared_axis_min_block_inclusive": wall_bounds["min_z"],
            "declared_axis_max_block_inclusive": wall_bounds["max_z"],
            "ortho_block": wall_bounds["min_x"],
            "y_min_block_inclusive": wall_bounds["min_y"],
            "y_max_block_inclusive": wall_bounds["max_y"],
            "declared_block_id": wall["block"],
            "expected_position_count": wall["observed_position_count"],
        }
    return {"floor": receipt_floor, "wall": receipt_wall}


def validation_points(layout: dict[str, Any]) -> list[dict[str, Any]]:
    wall = layout["wall"]["bounds"]
    camera = layout["camera"]["feet_xyz"]
    if layout["wall"]["axis"] == "x":
        near = wall["min_z"] if camera[2] <= wall["min_z"] else wall["max_z"] + 1
        negative = [float(wall["min_x"]), float(near)]
        positive = [float(wall["max_x"] + 1), float(near)]
    else:
        near = wall["min_x"] if camera[0] <= wall["min_x"] else wall["max_x"] + 1
        negative = [float(near), float(wall["min_z"])]
        positive = [float(near), float(wall["max_z"] + 1)]
    midpoint = [(negative[0] + positive[0]) / 2.0, (negative[1] + positive[1]) / 2.0]
    target = layout["target_start"]["world_xyz"]
    return [
        {
            "point_id": "target_ground_contact",
            "feature": "magenta target feet/ground-contact point",
            "world_xyz_blocks": target,
            "world_xz_blocks": [target[0], target[2]],
            "image_xy_pixels": None,
            "person_e_visibility_and_annotation_required": True,
        },
        {
            "point_id": "wall_near_face_ground_negative_end",
            "feature": "negative wall-axis endpoint at the near-face/ground-plane intersection",
            "world_xyz_blocks": [negative[0], 4.0, negative[1]],
            "world_xz_blocks": negative,
            "image_xy_pixels": None,
            "person_e_visibility_and_annotation_required": True,
        },
        {
            "point_id": "wall_near_face_ground_midpoint",
            "feature": "wall-axis midpoint at the near-face/ground-plane intersection",
            "world_xyz_blocks": [midpoint[0], 4.0, midpoint[1]],
            "world_xz_blocks": midpoint,
            "image_xy_pixels": None,
            "person_e_visibility_and_annotation_required": True,
        },
        {
            "point_id": "wall_near_face_ground_positive_end",
            "feature": "positive wall-axis endpoint at the near-face/ground-plane intersection",
            "world_xyz_blocks": [positive[0], 4.0, positive[1]],
            "world_xz_blocks": positive,
            "image_xy_pixels": None,
            "person_e_visibility_and_annotation_required": True,
        },
    ]


def validate_authorities() -> tuple[dict[str, Any], dict[str, Any]]:
    require(sha256(GEOMETRY.read_bytes()) == GEOMETRY_SHA256, "accepted geometry hash drift")
    geometry = load(GEOMETRY)
    require(geometry["config_version"] == GEOMETRY_VERSION, "accepted geometry version drift")
    require([row["layout_id"] for row in geometry["layouts"]] == [row[0] for row in EPISODES], "layout IDs drift")
    closure = load(CLOSURE)
    require(
        closure["c1_1_complete"] is True
        and closure["c1_3_complete"] is True
        and closure["c1_5_complete"] is True
        and closure["person_c_c1_stop_gate_closed"] is True,
        "Person C C1 stop gate is not closed",
    )
    require(
        closure["accepted_geometry_version"] == GEOMETRY_VERSION
        and closure["accepted_geometry_sha256"] == GEOMETRY_SHA256,
        "closure geometry identity drift",
    )
    server_jar = SERVER / "mods/mineocclude-0.1.1.jar"
    client_jar = CLIENT / "mods/mineocclude-0.1.1.jar"
    options = CLIENT / "options.txt"
    properties = SERVER / "server.properties"
    require(sha256(server_jar.read_bytes()) == JAR_SHA256, "server repaired JAR drift")
    require(sha256(client_jar.read_bytes()) == JAR_SHA256, "client repaired JAR drift")
    require(sha256(options.read_bytes()) == OPTIONS_SHA256, "client options drift")
    require(sha256(properties.read_bytes()) == SERVER_PROPERTIES_SHA256, "server.properties drift")
    properties_text = properties.read_text(encoding="utf-8-sig")
    require(re.search(r"(?m)^spawn-animals=false$", properties_text) is not None, "spawn-animals is not false")
    require(re.search(r"(?m)^fov:0\.0$", options.read_text(encoding="utf-8-sig")) is not None, "options FOV is not Normal/70 degrees")
    return geometry, closure


def audit_collisions(schedule_data: dict[int, bytes]) -> dict[str, Any]:
    expected_repo = {REPO_SCHEDULE_DIR / f"episode_{episode}.jsonl" for _, episode, _ in EPISODES}
    expected_runtime = {RUNTIME_SCHEDULE_DIR / f"episode_{episode}.jsonl" for _, episode, _ in EPISODES}
    for path in [*expected_repo, *expected_runtime]:
        if path.exists():
            episode = int(path.stem.split("_")[1])
            require(path.read_bytes() == schedule_data[episode], f"schedule collision or drift: {path}")
    create_only = []
    for layout_id, _, _ in EPISODES:
        create_only.extend(
            [
                SERVER / "mineocclude_observations" / f"e_refit_calibration_v0_4_{layout_id}.json",
                CLIENT_EVIDENCE_DIR / f"{layout_id}.png",
            ]
        )
    create_only.extend(
        [
            SERVER_EVIDENCE_DIR / "operator_attestation.json",
            SERVER_EVIDENCE_DIR / "server_latest.log",
            CLIENT_EVIDENCE_DIR / "client_latest.log",
            SERVER_EVIDENCE_DIR / "screenshot_inventory.json",
            SERVER_EVIDENCE_DIR / "geometry_receipt_inventory.json",
            SERVER_EVIDENCE_DIR / "e_image_point_annotation_template.json",
            SERVER_EVIDENCE_DIR / "e_independent_validation_pair_template.json",
            SERVER_EVIDENCE_DIR / "person_c_to_e_calibration_handoff_v0_4.json",
            SERVER_EVIDENCE_DIR / "finalization_result.json",
        ]
    )
    collisions = [str(path.resolve()) for path in create_only if path.exists()]
    require(not collisions, f"create-only calibration output collisions: {collisions}")
    reserved_ids = sorted(
        int(path.stem.split("_")[1])
        for path in RUNTIME_SCHEDULE_DIR.glob("episode_*.jsonl")
        if int(path.stem.split("_")[1]) not in schedule_data
    )
    return {
        "candidate_episode_ids": [row[1] for row in EPISODES],
        "candidate_seeds": [row[2] for row in EPISODES],
        "candidate_ids_distinct": len({row[1] for row in EPISODES}) == 6,
        "candidate_seeds_distinct": len({row[2] for row in EPISODES}) == 6,
        "known_reserved_runtime_episode_ids": reserved_ids,
        "c1_5_episode_ids_not_reused": all(row[1] not in range(11501, 11507) for row in EPISODES),
        "c6a_episode_ids_not_reused": all(row[1] not in range(12601, 12667) for row in EPISODES),
        "create_only_outputs_absent": True,
        "collisions": [],
    }


def install_runtime_schedules(schedule_data: dict[int, bytes]) -> None:
    RUNTIME_SCHEDULE_DIR.mkdir(parents=True, exist_ok=True)
    for episode, data in schedule_data.items():
        path = RUNTIME_SCHEDULE_DIR / f"episode_{episode}.jsonl"
        if path.exists():
            require(path.read_bytes() == data, f"runtime schedule exists with different bytes: {path}")
            continue
        with path.open("xb") as stream:
            stream.write(data)


def package_inventory(outputs: dict[Path, bytes]) -> tuple[bytes, str]:
    rows = [
        generated_identity(path, data)
        for path, data in sorted(outputs.items(), key=lambda item: item[0].as_posix())
        if path.parent == DOC_DIR and path.name != "sha256_inventory.json"
    ]
    bundle = sha256("".join(f"{row['path']}\0{row['sha256']}\n" for row in rows).encode())
    return dump(
        {
            "schema_version": "person-c-package-sha256-inventory-v1.0",
            "self_excluded": "sha256_inventory.json",
            "package_bundle_sha256": bundle,
            "files": rows,
        }
    ), bundle


def write_outputs(outputs: dict[Path, bytes]) -> None:
    for path, data in outputs.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--install-runtime-schedules", action="store_true")
    args = parser.parse_args()

    geometry, closure = validate_authorities()
    refit_handoff = load(REFIT_HANDOFF)
    require(
        refit_handoff["accepted_geometry_version"] == GEOMETRY_VERSION
        and refit_handoff["accepted_geometry_sha256"] == GEOMETRY_SHA256
        and refit_handoff["e_homography_refit_required"] is True,
        "Person E refit handoff authority drift",
    )
    refit_by_layout = {row["layout_id"]: row for row in refit_handoff["layouts"]}
    require(set(refit_by_layout) == {row[0] for row in EPISODES}, "Person E refit layout set drift")
    schedule_data = {
        episode: serialize_schedule(generate_noise_schedule(seed=seed, n_draws=RECORD_TICKS, q=0.0))
        for _, episode, seed in EPISODES
    }
    collision = audit_collisions(schedule_data)
    if args.install_runtime_schedules:
        install_runtime_schedules(schedule_data)
    runtime_ready = all(
        (RUNTIME_SCHEDULE_DIR / f"episode_{episode}.jsonl").is_file()
        and (RUNTIME_SCHEDULE_DIR / f"episode_{episode}.jsonl").read_bytes() == schedule_data[episode]
        for _, episode, _ in EPISODES
    )

    schedule_rows = []
    schedule_outputs: dict[Path, bytes] = {}
    for layout_id, episode, seed in EPISODES:
        data = schedule_data[episode]
        repo_path = REPO_SCHEDULE_DIR / f"episode_{episode}.jsonl"
        runtime_path = RUNTIME_SCHEDULE_DIR / f"episode_{episode}.jsonl"
        schedule_outputs[repo_path] = data
        schedule_rows.append(
            {
                "layout_id": layout_id,
                "episode_id": episode,
                "seed": seed,
                "q": 0.0,
                "record_ticks": RECORD_TICKS,
                "repository_schedule": generated_identity(repo_path, data),
                "runtime_schedule": {
                    **generated_identity(runtime_path, data, repo_relative=False),
                    "installation_status": "INSTALLED_HASH_MATCH" if runtime_path.is_file() else "PENDING_CREATE_ONLY_INSTALL",
                },
            }
        )
    schedule_manifest = {
        "schema_version": "person-c-e-refit-calibration-schedule-set-v0.1",
        "immutable": True,
        "non_scientific_calibration_only": True,
        "source_commit": SOURCE_COMMIT,
        "schedule_count": 6,
        "schedules": schedule_rows,
    }
    schedule_manifest_bytes = dump(schedule_manifest)
    schedule_outputs[CONFIG_DIR / "schedule_set_manifest.json"] = schedule_manifest_bytes

    by_layout = {row["layout_id"]: row for row in geometry["layouts"]}
    layouts = []
    layout_outputs: dict[Path, bytes] = {}
    annotation_layouts = []
    validation_layouts = []
    screenshot_rows = []
    receipt_rows = []
    for layout_id, episode, seed in EPISODES:
        layout = by_layout[layout_id]
        markers = marker_rows(layout)
        receipt_path = SERVER / "mineocclude_observations" / f"e_refit_calibration_v0_4_{layout_id}.json"
        screenshot_path = CLIENT_EVIDENCE_DIR / f"{layout_id}.png"
        schedule = next(row for row in schedule_rows if row["episode_id"] == episode)
        record = {
            "schema_version": "person-c-e-refit-layout-calibration-preparation-v0.1",
            "status": "READY_FOR_RUNTIME_CALIBRATION",
            "scientific_capture": False,
            "layout_id": layout_id,
            "episode_id": episode,
            "seed": seed,
            "geometry_version": GEOMETRY_VERSION,
            "geometry_sha256": GEOMETRY_SHA256,
            "mode": "normal",
            "duration": 0,
            "reveal": 0,
            "impulse": [-1, 0],
            "lockcam": "on",
            "warmup_ticks": WARMUP_TICKS,
            "record_ticks": RECORD_TICKS,
            "spawn_animals": False,
            "layout_geometry": {
                "floor": layout["floor"],
                "wall": layout["wall"],
                "lane": layout["lane"],
                "target_start": layout["target_start"],
                "camera": layout["camera"],
                "markers": markers,
                "expected_receipt_geometry": expected_receipt_geometry(layout),
            },
            "projection": {**FRAMEBUFFER, "fov_degrees": FOV_DEGREES},
            "schedule": schedule,
            "commands": {
                "start": f"mineocclude start {layout_id} {episode} {seed} 0.0 0.0 20",
                "targetstatus": "mineocclude targetstatus",
                "observegeometry": f"mineocclude observegeometry e_refit_calibration_v0_4_{layout_id}",
                "stop": "mineocclude stop",
            },
            "runtime_paths": {
                "geometry_receipt": str(receipt_path.resolve()),
                "canonical_screenshot": str(screenshot_path.resolve()),
                "server_log": str((SERVER / "logs/latest.log").resolve()),
                "client_log": str((CLIENT / "logs/latest.log").resolve()),
            },
            "source_commit": SOURCE_COMMIT,
        }
        layouts.append(record)
        layout_outputs[DOC_DIR / f"{layout_id}_calibration.json"] = dump(record)
        annotation_layouts.append(
            {
                "layout_id": layout_id,
                "episode_id": episode,
                "screenshot": {
                    "path": str(screenshot_path.resolve()),
                    "width_pixels": 1920,
                    "height_pixels": 1046,
                    "size_bytes": None,
                    "sha256": None,
                },
                "marker_set_source_hash": refit_by_layout[layout_id]["marker_set_source_hash"],
                "fit_correspondences": markers,
            }
        )
        validation_layouts.append(
            {
                "layout_id": layout_id,
                "episode_id": episode,
                "screenshot": {
                    "path": str(screenshot_path.resolve()),
                    "width_pixels": 1920,
                    "height_pixels": 1046,
                    "size_bytes": None,
                    "sha256": None,
                },
                "validation_points": validation_points(layout),
            }
        )
        screenshot_rows.append(
            {
                "layout_id": layout_id,
                "episode_id": episode,
                "create_only_destination": str(screenshot_path.resolve()),
                "required_width_pixels": 1920,
                "required_height_pixels": 1046,
                "observed_source_path": None,
                "size_bytes": None,
                "sha256": None,
                "status": "PENDING_RUNTIME_FINALIZATION",
            }
        )
        receipt_rows.append(
            {
                "layout_id": layout_id,
                "episode_id": episode,
                "receipt_id": f"e_refit_calibration_v0_4_{layout_id}",
                "create_only_path": str(receipt_path.resolve()),
                "size_bytes": None,
                "sha256": None,
                "status": "PENDING_RUNTIME_OBSERVATION",
            }
        )

    coordinate_convention = {
        "schema_version": "person-c-to-person-e-v0.4-calibration-coordinate-convention-v0.1",
        "image_coordinates": {
            "convention": "pixel_center_xy_zero_based",
            "origin": "top_left_pixel_center",
            "positive_x": "right",
            "positive_y": "down",
            "width_pixels": 1920,
            "height_pixels": 1046,
            "valid_x_center_range": [0, 1919],
            "valid_y_center_range": [0, 1045],
        },
        "world_coordinates": {
            "system": "minecraft_world_x_y_z",
            "homography_plane": "world_y_equals_4_blocks",
            "homography_output_axes": ["world_x", "world_z"],
            "fit_marker_point": "literal top-face centre declared by person-c-layout-config-v0.4",
            "wall_validation_point": "literal near-face/ground-plane intersection; block boundary, not block centre",
        },
        "forbidden": [
            "hidden_offsets",
            "plus_0.5_corrections",
            "layout_id_shifts",
            "coordinate_renumbering",
            "compatibility_adapters",
            "invented_image_pixel_coordinates",
        ],
    }
    annotation_template = {
        "schema_version": "person-e-v0.4-image-point-annotation-template-v0.1",
        "status": "PENDING_PERSON_E_IMAGE_ANNOTATION",
        "owner_of_image_coordinates": "Person E",
        "person_c_invented_image_coordinates": False,
        "accepted_geometry_version": GEOMETRY_VERSION,
        "accepted_geometry_sha256": GEOMETRY_SHA256,
        "image_coordinate_convention": "pixel_center_xy_zero_based",
        "world_coordinate_convention": "ground_plane_world_xz_blocks_top_face_centre",
        "layouts": annotation_layouts,
    }
    validation_template = {
        "schema_version": "person-e-v0.4-independent-validation-pair-template-v0.1",
        "status": "PENDING_PERSON_E_INDEPENDENT_IMAGE_ANNOTATION",
        "owner_of_image_coordinates_and_visibility_decisions": "Person E",
        "independence_rule": "These slots are not any of the four marker top-face centres used for fitting. Person E must independently annotate only visible, unambiguous points and document exclusions.",
        "accepted_geometry_version": GEOMETRY_VERSION,
        "accepted_geometry_sha256": GEOMETRY_SHA256,
        "image_coordinate_convention": "pixel_center_xy_zero_based",
        "world_coordinate_convention": "ground_plane_world_xz_blocks",
        "layouts": validation_layouts,
    }
    attestation_template = {
        "schema_version": "person-c-e-refit-calibration-operator-attestation-v0.1",
        "template": True,
        "operator_id": None,
        "observed_authenticated_account": None,
        "single_authenticated_operator": None,
        "normal_gameplay_no_pause_chat_inventory_or_f3_for_all_screenshots": None,
        "exactly_one_f2_per_layout_after_receipt_confirmation": None,
        "all_six_episodes_aborted_during_warmup": None,
        "recording_never_started": None,
        "same_server_client_options_render_and_log_session": None,
        "preparation_commit": None,
        "accepted_geometry_version": GEOMETRY_VERSION,
        "accepted_geometry_sha256": GEOMETRY_SHA256,
        "mineocclude_jar_sha256": JAR_SHA256,
        "layout_ids": [row[0] for row in EPISODES],
        "episode_ids": [row[1] for row in EPISODES],
        "utc_start": None,
        "utc_end": None,
        "notes": None,
    }

    runtime_identity = {
        "schema_version": "person-c-e-refit-calibration-runtime-identity-v0.1",
        "status": "PASS_PREPARATION_RUNTIME_IDENTITIES",
        "source_commit": SOURCE_COMMIT,
        "accepted_geometry": repo_identity(GEOMETRY),
        "accepted_geometry_version": GEOMETRY_VERSION,
        "person_c_c1_closure": repo_identity(CLOSURE),
        "environment_lock": {"version": "person-c-c1-final-environment-lock-v1.0", **repo_identity(ENVIRONMENT_LOCK)},
        "render_settings": repo_identity(RENDER_SETTINGS),
        "server_runtime_manifest": repo_identity(SERVER_MANIFEST),
        "client_runtime_manifest": repo_identity(CLIENT_MANIFEST),
        "person_e_refit_input_authority": repo_identity(REFIT_HANDOFF),
        "person_e_refit_handoff_inventory": repo_identity(REFIT_HANDOFF_INVENTORY),
        "server_jar": {**identity(SERVER / "mods/mineocclude-0.1.1.jar"), "source_commit": RUNTIME_SOURCE_COMMIT},
        "client_jar": {**identity(CLIENT / "mods/mineocclude-0.1.1.jar"), "source_commit": RUNTIME_SOURCE_COMMIT},
        "server_properties": identity(SERVER / "server.properties"),
        "spawn_animals": False,
        "client_options": identity(CLIENT / "options.txt"),
        "fov_degrees": FOV_DEGREES,
        "framebuffer": FRAMEBUFFER,
        "server_log_for_session": str((SERVER / "logs/latest.log").resolve()),
        "client_log_for_session": str((CLIENT / "logs/latest.log").resolve()),
    }
    controls = [
        "mineocclude markergeomstatus",
        "mineocclude mode normal",
        "mineocclude duration 0",
        "mineocclude reveal 0",
        "mineocclude impulse -1 0",
        "mineocclude lockcam on",
        "mineocclude warmup 12000",
    ]
    finalization_command = (
        'powershell.exe -NoProfile -ExecutionPolicy Bypass -File '
        '"C:\\Users\\lollo\\MineOcclude-Person-C-C1-C6A\\scripts\\person_c\\finalize-e-refit-calibration-v0-4.ps1"'
    )
    session_manifest = {
        "schema_version": "person-c-to-person-e-calibration-image-session-v0.4-v0.1",
        "status": "READY_FOR_ONE_AUTHENTICATED_OPERATOR" if runtime_ready else "PENDING_RUNTIME_SCHEDULE_INSTALL",
        "source_commit": SOURCE_COMMIT,
        "purpose": "non-scientific six-layout calibration evidence for Person E v0.4 homography refit",
        "scientific_capture": False,
        "c1_5_reconstruction": False,
        "c6a_or_c6b": False,
        "operator_count_required": 1,
        "accepted_geometry_version": GEOMETRY_VERSION,
        "accepted_geometry_sha256": GEOMETRY_SHA256,
        "mineocclude_jar_sha256": JAR_SHA256,
        "person_e_refit_input_authority": repo_identity(REFIT_HANDOFF),
        "person_e_refit_handoff_inventory": repo_identity(REFIT_HANDOFF_INVENTORY),
        "runtime_identity": runtime_identity,
        "session_controls_apply_once_in_order": controls,
        "layout_count": 6,
        "layouts": layouts,
        "strict_per_layout_chronology": [
            "episode_armed",
            "wait_at_least_10_seconds",
            "one_passing_targetstatus",
            "observegeometry_completes",
            "receipt_written_confirmation",
            "exactly_one_f2_after_confirmation",
            "mineocclude_stop_aborts_during_warmup",
            "recording_does_not_begin",
        ],
        "logs": {
            "server_source": str((SERVER / "logs/latest.log").resolve()),
            "client_source": str((CLIENT / "logs/latest.log").resolve()),
            "server_create_only_archive": str((SERVER_EVIDENCE_DIR / "server_latest.log").resolve()),
            "client_create_only_archive": str((CLIENT_EVIDENCE_DIR / "client_latest.log").resolve()),
        },
        "finalizer": repo_identity(FINALIZER),
        "finalization_command": finalization_command,
        "collision_audit": collision,
        "runtime_schedules_ready": runtime_ready,
        "schedule_set_manifest": generated_identity(CONFIG_DIR / "schedule_set_manifest.json", schedule_manifest_bytes),
        "runtime_executed_by_preparation": False,
    }
    screenshot_inventory = {
        "schema_version": "person-c-e-refit-calibration-screenshot-inventory-preparation-v0.1",
        "status": "PENDING_RUNTIME_FINALIZATION",
        "create_only": True,
        "screenshots": screenshot_rows,
    }
    receipt_inventory = {
        "schema_version": "person-c-e-refit-calibration-geometry-receipt-inventory-preparation-v0.1",
        "status": "PENDING_RUNTIME_OBSERVATION",
        "create_only": True,
        "receipts": receipt_rows,
    }
    runbook_lines = [
        "# Person E v0.4 six-layout calibration-image session",
        "",
        "This is one non-scientific calibration session for one authenticated operator. It is not C1.5, C6A, C6B, or a second-operator task. Do not start if any create-only receipt or screenshot destination in `session_manifest.json` exists.",
        "",
        "1. Start the isolated server with `C:\\Users\\lollo\\MineOcclude-Runtime\\person-c-c1-v0_1\\server\\start-mineocclude-server.ps1`.",
        "2. Launch the isolated authenticated Fabric client with `C:\\Users\\lollo\\MineOcclude-Runtime\\person-c-c1-v0_1\\client\\start-mineocclude-client.ps1`.",
        "3. Connect to `127.0.0.1:25565`. Confirm normal gameplay at 1920x1046, FOV Normal (70.0), with no pause menu, chat, inventory, or F3 overlay.",
        "4. In the server console apply these session controls exactly once, in order: " + "; ".join(f"`{row}`" for row in controls) + ".",
        "5. For each row below, do not press F2 until the receipt-written confirmation appears. If targetstatus fails, recording starts, or any destination already exists, stop and preserve the session as failed; do not reuse paths.",
        "",
        "| Layout | Start | Observe | Receipt | Screenshot destination |",
        "|---|---|---|---|---|",
    ]
    for row in layouts:
        runbook_lines.append(
            f"| `{row['layout_id']}` | `{row['commands']['start']}` | `{row['commands']['observegeometry']}` | `{row['runtime_paths']['geometry_receipt']}` | `{row['runtime_paths']['canonical_screenshot']}` |"
        )
    runbook_lines.extend(
        [
            "",
            "For every layout: run the Start command; wait at least 10 seconds; run `mineocclude targetstatus`; require `valid=true required=true count=1 lifecycle=READY problems=NONE`; immediately run Observe; wait for the receipt-written confirmation; return to normal unobstructed gameplay; press F2 exactly once; immediately run `mineocclude stop`; require `episode <id> aborted during warmup`; then continue to the next row. Recording must never begin.",
            "",
            "After layout_06: disconnect and quit the client, then stop the server cleanly. Preserve both `logs\\latest.log` files. Run the finalizer once and type `YES` only if all six screenshots meet the unobstructed-gameplay rule and the client was authenticated:",
            "",
            f"`{finalization_command}`",
            "",
            "The finalizer discovers the six raw F2 files from the same client log, validates chronology and literal v0.4 receipts, copies them create-only, fills hashes automatically, and leaves all Person E image-coordinate fields null. Do not manually edit preparation JSON.",
        ]
    )
    validation_md = """# Calibration preparation validation

PASS for preparation. The exact required branch ancestry, closed C1 stop gate, accepted v0.4 geometry, repaired server/client JARs, current options, 1920x1046 framebuffer authority, 70.0-degree FOV authority, `spawn-animals=false`, collision-free episodes/seeds, six immutable schedules, create-only evidence paths, coordinate templates, and fail-closed finalizer are bound here.

Runtime calibration has not been executed. Screenshot/receipt hashes and all Person E image pixel coordinates remain pending. This package does not authorize or execute C6A and does not fit a homography.
"""

    outputs: dict[Path, bytes] = {
        **schedule_outputs,
        **layout_outputs,
        DOC_DIR / "session_manifest.json": dump(session_manifest),
        DOC_DIR / "runtime_identity.json": dump(runtime_identity),
        DOC_DIR / "screenshot_inventory.json": dump(screenshot_inventory),
        DOC_DIR / "geometry_receipt_inventory.json": dump(receipt_inventory),
        DOC_DIR / "e_image_point_annotation_template.json": dump(annotation_template),
        DOC_DIR / "e_independent_validation_pair_template.json": dump(validation_template),
        DOC_DIR / "coordinate_convention.json": dump(coordinate_convention),
        DOC_DIR / "operator_attestation_template.json": dump(attestation_template),
        DOC_DIR / "operator_runbook.md": ("\n".join(runbook_lines) + "\n").encode("utf-8"),
        DOC_DIR / "validation_report.md": validation_md.encode("utf-8"),
    }
    inventory, bundle = package_inventory(outputs)
    outputs[DOC_DIR / "sha256_inventory.json"] = inventory
    write_outputs(outputs)

    require(runtime_ready, "runtime schedules are not installed; rerun with --install-runtime-schedules")
    print(
        json.dumps(
            {
                "status": "PASS",
                "layout_count": 6,
                "episode_ids": [row[1] for row in EPISODES],
                "seeds": [row[2] for row in EPISODES],
                "runtime_schedules_ready": True,
                "package_bundle_sha256": bundle,
                "runtime_executed": False,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
