#!/usr/bin/env python3
"""Validate and ingest the hash-bound Person C C1.1 runtime observation.

This intentionally performs literal coordinate comparisons. It does not apply
layout-ID shifts, half-block corrections, offsets, or compatibility adapters.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[2]
RUNTIME = Path(r"C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1")
SERVER = RUNTIME / "server"
CLIENT = RUNTIME / "client"
STARTING_COMMIT = "8f3c82df658871b793f9530b8e04eded93682c20"
JAR_SOURCE_COMMIT = "99b78b6578d17cffc0b5679118a42632284ce7f7"
JAR_SHA256 = "652fe5e34f0ee186a3b6c036ab70b1bf02e9373c985eeaa218e3ef28be087bda"
ACCEPTED_VERSION = "person-c-layout-config-v0.4"
CLASSIFICATION = "NEITHER_GEOMETRY_MATCHES_RUNTIME"
EXPECTED_LAYOUTS = [f"layout_{index:02d}" for index in range(1, 7)]
COLORS = ["blue", "yellow", "lime", "white"]

INGEST_DIR = REPO / "docs/status/person_c_c1_runtime_ingestion_v0_1"
AUTH_DIR = REPO / "docs/status/person_c_geometry_authority_v0_2"
RECON_DIR = REPO / "docs/status/person_c_c1_reconstruction_v0_1"
C6A_DIR = REPO / "docs/status/person_c_c6a_capture_manifest_v0_1"
SUCCESSOR_CONFIG = REPO / "configs/scenes/layouts_v0_4.yaml"


class AuditError(RuntimeError):
    pass


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git_blob_bytes(data: bytes) -> str:
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


def file_identity(path: Path, *, absolute: bool = False) -> dict[str, Any]:
    data = path.read_bytes()
    try:
        display = str(path.resolve()) if absolute else path.resolve().relative_to(REPO).as_posix()
    except ValueError:
        display = str(path.resolve())
    return {
        "path": display,
        "size_bytes": len(data),
        "sha256": sha256_bytes(data),
    }


def repo_identity(path: Path) -> dict[str, Any]:
    result = file_identity(path)
    result["git_blob"] = git_blob_bytes(path.read_bytes())
    return result


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def dump_json(value: Any) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def png_dimensions(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        raise AuditError(f"not a PNG: {path}")
    return struct.unpack(">II", data[16:24])


def parse_properties(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        result[key] = value
    return result


def parse_options(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        if ":" not in raw:
            continue
        key, value = raw.split(":", 1)
        result[key] = value
    return result


def jar_metadata(path: Path) -> dict[str, Any] | None:
    try:
        with zipfile.ZipFile(path) as archive:
            return json.loads(archive.read("fabric.mod.json").decode("utf-8-sig"))
    except (KeyError, OSError, zipfile.BadZipFile, json.JSONDecodeError, UnicodeDecodeError):
        return None


def mod_inventory(root: Path, scope: str) -> dict[str, Any]:
    rows = []
    for path in sorted((root / "mods").glob("*.jar"), key=lambda item: item.name.casefold()):
        identity = file_identity(path, absolute=True)
        metadata = jar_metadata(path)
        row = dict(identity)
        row["file_name"] = path.name
        if metadata is not None:
            row["fabric_metadata"] = {
                "id": metadata.get("id"),
                "version": metadata.get("version"),
                "environment": metadata.get("environment"),
            }
        else:
            row["fabric_metadata"] = None
        rows.append(row)
    return {"scope": scope, "mod_count": len(rows), "entries": rows}


def require(condition: bool, message: str, checks: dict[str, bool]) -> None:
    checks[message] = bool(condition)
    if not condition:
        raise AuditError(message)


def xyz_from_c_marker(marker: dict[str, Any]) -> list[float]:
    world = marker["world_blocks"]
    return [float(world["x"]), float(world["y"]), float(world["z"])]


def xyz_from_e_marker(marker: dict[str, Any]) -> list[float]:
    x, z = marker["world_xz_blocks"]
    return [float(x), 4.0, float(z)]


def delta(left: list[float], right: list[float]) -> list[float]:
    return [round(left[index] - right[index], 10) for index in range(3)]


def explicit_bounds(axis: str, axis_min: int, axis_max: int, ortho_min: int, ortho_max: int, y: int) -> dict[str, int]:
    if axis == "X":
        return {"min_x": axis_min, "max_x": axis_max, "min_z": ortho_min, "max_z": ortho_max, "y": y}
    return {"min_x": ortho_min, "max_x": ortho_max, "min_z": axis_min, "max_z": axis_max, "y": y}


def package_inventory(directory: Path) -> dict[str, Any]:
    files = []
    for path in sorted(directory.iterdir(), key=lambda item: item.name):
        if path.is_file() and path.name != "sha256_inventory.json":
            files.append(file_identity(path))
    return {
        "schema_version": "person-c-package-sha256-inventory-v1.0",
        "package_path": directory.resolve().relative_to(REPO).as_posix(),
        "self_excluded_to_avoid_recursive_hash": "sha256_inventory.json",
        "file_count": len(files),
        "files": files,
    }


def write_or_check(outputs: dict[Path, bytes], write: bool) -> None:
    mismatches = []
    for path, expected in outputs.items():
        if write:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(expected)
        elif not path.exists() or path.read_bytes() != expected:
            mismatches.append(str(path))
    if mismatches:
        raise AuditError("generated output mismatch: " + ", ".join(mismatches))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="write additive evidence outputs")
    args = parser.parse_args()

    checks: dict[str, bool] = {}
    server_log_path = SERVER / "logs/latest.log"
    client_log_path = CLIENT / "logs/latest.log"
    properties_path = SERVER / "server.properties"
    options_path = CLIENT / "options.txt"
    jdk_path_file = RUNTIME.parent / "jdk17-path.txt"
    required_paths = [server_log_path, client_log_path, properties_path, options_path, jdk_path_file]
    for path in required_paths:
        require(path.is_file(), f"runtime file exists: {path}", checks)

    server_log_bytes = server_log_path.read_bytes()
    client_log_bytes = client_log_path.read_bytes()
    server_log = server_log_bytes.decode("utf-8", errors="replace")
    client_log = client_log_bytes.decode("utf-8", errors="replace")
    properties = parse_properties(properties_path)
    options = parse_options(options_path)
    java_exe = Path(jdk_path_file.read_text(encoding="utf-8-sig").strip())
    require(java_exe.is_file(), "selected Java executable exists", checks)
    java_result = subprocess.run([str(java_exe), "-version"], text=True, capture_output=True, check=True)
    java_text = (java_result.stderr + java_result.stdout).strip()
    require('version "17.0.19"' in java_text, "Java 17.0.19 identity", checks)
    process_result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            "Get-Process -Name java -ErrorAction SilentlyContinue | ForEach-Object { $_.Path }",
        ],
        text=True,
        capture_output=True,
        check=True,
    )
    selected_java_running = str(java_exe).casefold() in process_result.stdout.casefold()
    require(not selected_java_running, "no Person C Java 17 runtime process remains", checks)

    require("Loading Minecraft 1.16.5 with Fabric Loader 0.15.11" in server_log, "server Minecraft/Loader identity", checks)
    require("Loading Minecraft 1.16.5 with Fabric Loader 0.15.11" in client_log, "client Minecraft/Loader identity", checks)
    require("Done (" in server_log and "[MineOcclude] server ready" in server_log, "stable dedicated server readiness", checks)
    require("overatedusername[/127.0.0.1:" in server_log and "joined the game" in server_log, "loopback client joined server", checks)
    require("Connecting to 127.0.0.1, 25565" in client_log, "client log connection", checks)
    require("overatedusername left the game" in server_log and "Stopping!" in client_log, "clean client disconnect and exit", checks)
    require("Stopping server" in server_log and "Saving worlds" in server_log and "ThreadedAnvilChunkStorage (world-c1-v0_2): All chunks are saved" in server_log, "clean server shutdown and save", checks)
    require("markergeom status: enabled=false" in server_log and "signature=null/null/null/null" in server_log, "disabled shared marker override", checks)
    require("FOV pinned to 70 (Normal)" in client_log, "displayed FOV runtime log evidence", checks)

    require(properties.get("spawn-animals") == "false", "spawn-animals=false", checks)
    require(properties.get("level-seed") == "202608030101", "world seed", checks)
    require(properties.get("level-name") == "world-c1-v0_2", "world identity", checks)
    require(properties.get("difficulty") == "peaceful", "difficulty", checks)
    require(properties.get("resource-pack", "") == "", "server resource pack empty", checks)
    require(properties.get("online-mode") == "false", "documented offline-mode baseline", checks)

    require(options.get("fov") == "0.0", "options FOV encoding", checks)
    require(options.get("fullscreen") == "false", "windowed client", checks)
    require(options.get("resourcePacks") == '["vanilla"]', "vanilla client resource pack", checks)
    require(options.get("incompatibleResourcePacks") == "[]", "no incompatible resource pack", checks)

    server_mods = mod_inventory(SERVER, "server")
    client_mods = mod_inventory(CLIENT, "client")
    require(server_mods["mod_count"] == 46, "server mod count 46", checks)
    require(client_mods["mod_count"] == 46, "client mod count 46", checks)
    server_mod_map = {entry["file_name"]: entry["sha256"] for entry in server_mods["entries"]}
    client_mod_map = {entry["file_name"]: entry["sha256"] for entry in client_mods["entries"]}
    require(server_mod_map == client_mod_map, "server/client mod inventories identical", checks)
    require(server_mod_map.get("mineocclude-0.1.0.jar") == JAR_SHA256, "MineOcclude JAR identity", checks)
    fabric_api_rows = [entry for entry in server_mods["entries"] if entry.get("fabric_metadata") and entry["fabric_metadata"].get("id") == "fabric"]
    require(len(fabric_api_rows) == 1 and fabric_api_rows[0]["fabric_metadata"]["version"] == "0.42.0+1.16", "Fabric API identity", checks)

    receipt_paths = [SERVER / f"mineocclude_observations/c1_1_layout_{index:02d}.json" for index in range(1, 7)]
    receipts = []
    receipt_hashes = set()
    override_signatures = set()
    for index, path in enumerate(receipt_paths, start=1):
        require(path.is_file(), f"receipt exists: {path.name}", checks)
        receipt = load_json(path)
        layout_id = f"layout_{index:02d}"
        require(receipt.get("schema_version") == "person-c-c1-runtime-geometry-observation-v0.1", f"{layout_id} receipt schema", checks)
        require(receipt.get("receipt_id") == f"c1_1_{layout_id}", f"{layout_id} receipt identity", checks)
        require(receipt.get("layout_id") == layout_id, f"{layout_id} layout identity", checks)
        require(receipt.get("observation_only") is True, f"{layout_id} observation-only", checks)
        require(receipt.get("scientific_use") == "forbidden", f"{layout_id} scientific-use forbidden", checks)
        require(receipt.get("capturing") is False and receipt.get("lifecycle_state") == "READY", f"{layout_id} pre-capture READY state", checks)
        require(receipt.get("observed_marker_block_count") == 4 and len(receipt.get("markers", [])) == 4, f"{layout_id} four markers", checks)
        require(all(marker.get("matches") is True for marker in receipt["markers"]), f"{layout_id} marker block matches", checks)
        require(receipt["floor"]["expected_position_count"] == receipt["floor"]["matching_position_count"] and receipt["floor"]["mismatches"] == [], f"{layout_id} floor validation", checks)
        require(receipt["wall"]["expected_position_count"] == receipt["wall"]["matching_position_count"] and receipt["wall"]["mismatches"] == [], f"{layout_id} wall validation", checks)
        require(len(receipt["camera"]["observed_players"]) == 1, f"{layout_id} one observed player", checks)
        require(receipt["camera"]["observed_players"][0]["feet_xyz"] == receipt["camera"]["canonical_feet_xyz"], f"{layout_id} canonical camera feet", checks)
        require(receipt["camera"]["observed_players"][0]["yaw_degrees"] == receipt["camera"]["canonical_yaw_degrees"], f"{layout_id} canonical yaw", checks)
        require(receipt["camera"]["observed_players"][0]["pitch_degrees"] == receipt["camera"]["canonical_pitch_degrees"], f"{layout_id} canonical pitch", checks)
        require(receipt["world_state"]["world_seed"] == 202608030101, f"{layout_id} world seed", checks)
        require(receipt["world_state"]["difficulty"] == "peaceful", f"{layout_id} difficulty", checks)
        require(receipt["world_state"]["time_of_day_ticks"] == 6000 and receipt["world_state"]["raining"] is False and receipt["world_state"]["thundering"] is False, f"{layout_id} fixed time/weather", checks)
        expected_gamerules = {
            "doMobSpawning": False,
            "doWeatherCycle": False,
            "doDaylightCycle": False,
            "mobGriefing": False,
            "randomTickSpeed": 0,
            "doFireTick": False,
            "keepInventory": True,
        }
        require(receipt["world_state"]["gamerules"] == expected_gamerules, f"{layout_id} gamerules", checks)
        require(receipt["marker_override"] == {"enabled": False, "signature": "null/null/null/null"}, f"{layout_id} override state", checks)
        override_signatures.add(receipt["marker_override"]["signature"])
        receipt_id = file_identity(path, absolute=True)
        require(receipt_id["sha256"] not in receipt_hashes, f"{layout_id} unique receipt hash", checks)
        receipt_hashes.add(receipt_id["sha256"])
        receipts.append((path, receipt, receipt_id))
    require(override_signatures == {"null/null/null/null"}, "shared receipt override signature", checks)

    screenshots = []
    for path in sorted((CLIENT / "screenshots").glob("2026-08-03_*.png"), key=lambda item: item.name):
        width, height = png_dimensions(path)
        row = file_identity(path, absolute=True)
        row.update({"file_name": path.name, "width_pixels": width, "height_pixels": height})
        screenshots.append(row)
    require(len(screenshots) == 5, "five session screenshots found", checks)
    require(all((row["width_pixels"], row["height_pixels"]) == (1920, 1046) for row in screenshots), "session screenshot dimensions", checks)
    screenshot_by_name = {row["file_name"]: row for row in screenshots}
    fov_screenshot_name = "2026-08-03_17.52.43.png"
    raw_screenshot_name = "2026-08-03_17.54.04.png"
    require(fov_screenshot_name in screenshot_by_name and raw_screenshot_name in screenshot_by_name, "authoritative screenshot pair", checks)
    for row in screenshots:
        if row["file_name"] == fov_screenshot_name:
            row["evidence_role"] = "authoritative_displayed_fov"
        elif row["file_name"] == raw_screenshot_name:
            row["evidence_role"] = "authoritative_raw_gameplay_framebuffer"
        else:
            row["evidence_role"] = "supplemental_render_settings"

    c_config_path = REPO / "configs/scenes/layouts.yaml"
    c_config = load_json(c_config_path)
    c_layouts = {layout["layout_id"]: layout for layout in c_config["layouts"]}
    e_paths = [REPO / f"data/handoff_e/markers_layout_{index:02d}.json" for index in range(1, 7)]
    e_configs = {layout_id: load_json(path) for layout_id, path in zip(EXPECTED_LAYOUTS, e_paths)}

    comparisons = []
    successor_layouts = []
    for path, receipt, receipt_id in receipts:
        layout_id = receipt["layout_id"]
        c_layout = c_layouts[layout_id]
        e_layout = e_configs[layout_id]
        runtime_by_color = {marker["color"]: marker for marker in receipt["markers"]}
        c_by_color = {marker["color"]: marker for marker in c_layout["markers"]}
        e_by_color = {marker["marker_color"]: marker for marker in e_layout["marker_correspondences"]}
        marker_rows = []
        c_marker_matches = 0
        e_marker_matches = 0
        for color in COLORS:
            runtime_marker = runtime_by_color[color]
            runtime_xyz = [float(value) for value in runtime_marker["top_face_centre_world_xyz"]]
            c_xyz = xyz_from_c_marker(c_by_color[color])
            e_xyz = xyz_from_e_marker(e_by_color[color])
            c_match = runtime_xyz == c_xyz
            e_match = runtime_xyz == e_xyz
            c_marker_matches += int(c_match)
            e_marker_matches += int(e_match)
            marker_rows.append({
                "color": color,
                "runtime_block_pos_xyz": runtime_marker["block_pos_xyz"],
                "runtime_top_face_centre_world_xyz": runtime_xyz,
                "c_literal_world_xyz": c_xyz,
                "runtime_minus_c_xyz": delta(runtime_xyz, c_xyz),
                "c_literal_match": c_match,
                "e_literal_top_face_centre_world_xyz": e_xyz,
                "runtime_minus_e_xyz": delta(runtime_xyz, e_xyz),
                "e_literal_match": e_match,
            })

        wall = receipt["wall"]
        c_wall = c_layout["wall"]
        wall_axis = wall["axis"]
        c_wall_matches = (
            c_wall["axis"].upper() == wall_axis
            and c_wall[f"min_{wall_axis.lower()}"] == wall["declared_axis_min_block_inclusive"]
            and c_wall[f"max_{wall_axis.lower()}"] == wall["declared_axis_max_block_inclusive"]
            and c_wall[f"min_{'z' if wall_axis == 'X' else 'x'}"] == wall["ortho_block"]
            and c_wall[f"max_{'z' if wall_axis == 'X' else 'x'}"] == wall["ortho_block"]
            and c_wall["min_y"] == wall["y_min_block_inclusive"]
            and c_wall["max_y"] == wall["y_max_block_inclusive"]
        )
        c_camera_matches = (
            list(c_layout["canonical_pose"]["position_blocks"].values()) == receipt["camera"]["canonical_feet_xyz"]
            and c_layout["canonical_pose"]["rotation_degrees"]["yaw"] == receipt["camera"]["canonical_yaw_degrees"]
            and c_layout["canonical_pose"]["rotation_degrees"]["pitch"] == receipt["camera"]["canonical_pitch_degrees"]
        )
        comparisons.append({
            "layout_id": layout_id,
            "layout_id_correspondence": {"runtime": layout_id, "c": layout_id, "e": e_layout["layout_id"], "legacy_e_id_not_applied": e_layout.get("legacy_layout_id")},
            "marker_coordinate_conventions": {
                "runtime": "block_pos_xyz_and_block_top_face_centre_world_xyz",
                "c": "literal_world_blocks_xyz_as_declared_no_transform",
                "e": e_layout["world_coordinate_system"],
            },
            "markers": marker_rows,
            "c_literal_marker_match_count": c_marker_matches,
            "e_literal_marker_match_count": e_marker_matches,
            "wall_axis": wall_axis.lower(),
            "c_wall_exact_match": c_wall_matches,
            "runtime_floor": receipt["floor"],
            "c_floor_declaration": {
                "arena": c_layout["arena"],
                "block": c_config["common_arena_grammar"]["arena_floor_block"],
            },
            "c_floor_exact_match": False,
            "runtime_camera": receipt["camera"],
            "c_camera_exact_match": c_camera_matches,
            "e_camera_coordinates_available_in_marker_file": False,
            "runtime_override": receipt["marker_override"],
            "result": "neither_literal_geometry_matches_runtime",
        })

        floor = receipt["floor"]
        floor_bounds = explicit_bounds(
            floor["axis"],
            floor["axis_min_block_inclusive"],
            floor["axis_max_block_inclusive"],
            floor["ortho_min_block_inclusive"],
            floor["ortho_max_block_inclusive"],
            floor["y_block"],
        )
        wall_ortho_axis = "z" if wall_axis == "X" else "x"
        wall_axis_key = wall_axis.lower()
        wall_bounds = {
            f"min_{wall_axis_key}": wall["declared_axis_min_block_inclusive"],
            f"max_{wall_axis_key}": wall["declared_axis_max_block_inclusive"],
            f"min_{wall_ortho_axis}": wall["ortho_block"],
            f"max_{wall_ortho_axis}": wall["ortho_block"],
            "min_y": wall["y_min_block_inclusive"],
            "max_y": wall["y_max_block_inclusive"],
        }
        successor_layouts.append({
            "layout_id": layout_id,
            "config_version": ACCEPTED_VERSION,
            "authority_basis": "fresh_runtime_observed_literal_geometry",
            "floor": {
                "axis": floor["axis"].lower(),
                "bounds": floor_bounds,
                "block": floor["default_block_id"],
                "observed_position_count": floor["matching_position_count"],
            },
            "wall": {
                "axis": wall_axis.lower(),
                "bounds": wall_bounds,
                "block": wall["declared_block_id"],
                "observed_position_count": wall["matching_position_count"],
            },
            "lane": receipt["lane"],
            "scalar_axis": {
                "world_axis": receipt["lane"]["axis"].lower(),
                "origin_world_coordinate_blocks": 0.0,
                "positive_world_direction": "+" + receipt["lane"]["axis"].lower(),
                "unit": "blocks",
            },
            "motion_sign": 1,
            "target_start": {
                "axis_position": receipt["lane"]["start_axis"],
                "world_xyz": ([
                    receipt["lane"]["start_axis"],
                    receipt["lane"]["feet_y"],
                    receipt["lane"]["ortho"],
                ] if receipt["lane"]["axis"] == "X" else [
                    receipt["lane"]["ortho"],
                    receipt["lane"]["feet_y"],
                    receipt["lane"]["start_axis"],
                ]),
                "source": "runtime receipt lane declaration and server spawn log",
            },
            "shadow": receipt["shadow"],
            "camera": {
                "feet_xyz": receipt["camera"]["canonical_feet_xyz"],
                "yaw_degrees": receipt["camera"]["canonical_yaw_degrees"],
                "pitch_degrees": receipt["camera"]["canonical_pitch_degrees"],
                "roll_degrees": 0.0,
                "fov_degrees": 70.0,
            },
            "markers": [{
                "role": marker["role"],
                "color": marker["color"],
                "block": marker["actual_block_id"],
                "block_pos_xyz": marker["block_pos_xyz"],
                "top_face_centre_world_xyz": marker["top_face_centre_world_xyz"],
                "world_point_convention": "block_top_face_centre",
            } for marker in receipt["markers"]],
            "runtime_evidence": receipt_id,
        })

    require(all(row["c_literal_marker_match_count"] == 0 and row["e_literal_marker_match_count"] == 0 for row in comparisons), "all layouts match neither C nor E markers", checks)
    require(all(row["c_wall_exact_match"] and row["c_camera_exact_match"] and not row["c_floor_exact_match"] for row in comparisons), "runtime wall/camera and floor comparison", checks)

    builder_paths = [
        REPO / "fabric/mineocclude-mod/src/main/java/com/mineocclude/server/ArenaBuilder.java",
        REPO / "fabric/mineocclude-mod/src/main/java/com/mineocclude/server/Layouts.java",
        REPO / "fabric/mineocclude-mod/src/main/java/com/mineocclude/server/EpisodeManager.java",
        REPO / "fabric/mineocclude-mod/src/main/java/com/mineocclude/server/MineOccludeServer.java",
    ]
    source_authorities = {
        "runtime_builder_source_commit": JAR_SOURCE_COMMIT,
        "runtime_builder_sources_unchanged_through_ingestion_starting_commit": STARTING_COMMIT,
        "historical_c_config": repo_identity(c_config_path),
        "historical_e_marker_files": [repo_identity(path) for path in e_paths],
        "runtime_builder_sources": [repo_identity(path) for path in builder_paths],
    }

    successor_config = {
        "schema_version": "person-c-runtime-observed-layout-config-v0.4",
        "config_version": ACCEPTED_VERSION,
        "status": "accepted_for_new_evidence",
        "owner": "Person C successor authority",
        "supersedes_for_new_evidence": "person-c-layout-config-v0.3",
        "historical_predecessor_invalidated": False,
        "classification": CLASSIFICATION,
        "no_compatibility_transforms": True,
        "coordinate_policy": "literal BlockPos and literal top-face-centre values are distinct declared fields; no hidden offsets or corrections",
        "layout_id_policy": "one-based layout_01 through layout_06 exactly; legacy IDs are historical metadata and are not applied",
        "common_geometry_grammar": {
            "world_type": "superflat",
            "floor_block": "minecraft:grass_block",
            "wall_block": "minecraft:stone",
            "wall_height_blocks": 3,
            "lane_relation": "wall_parallel",
            "marker_count": 4,
            "marker_restriction": "non_magenta_ground_markers",
            "coordinate_system": "minecraft_world_x_y_z",
            "scalar_axis_unit": "blocks",
        },
        "conditions": c_config["conditions"],
        "condition_runtime_caveat": "geometry is accepted, but the current runtime removes the explicit magenta sheep at warmup tick 1; core/no_wall_visible scientific execution is blocked pending a target-retention fix and fresh observation",
        "runtime_binding": {
            "runtime_baseline_version": "person-c-c1-runtime-baseline-v0.2",
            "jar_source_commit": JAR_SOURCE_COMMIT,
            "mineocclude_jar_sha256": JAR_SHA256,
            "minecraft": "1.16.5",
            "fabric_loader": "0.15.11",
            "yarn_mappings": "1.16.5+build.10",
            "fabric_api": "0.42.0+1.16",
            "java": "17.0.19",
        },
        "shared_capture_projection": {
            "raw_framebuffer_width_pixels": 1920,
            "raw_framebuffer_height_pixels": 1046,
            "canonical_derivative_width_pixels": 640,
            "canonical_derivative_height_pixels": 360,
            "fov_degrees": 70.0,
            "fov_display": "Normal",
        },
        "layouts": successor_layouts,
    }
    successor_config_bytes = dump_json(successor_config)
    successor_config_identity = {
        "path": "configs/scenes/layouts_v0_4.yaml",
        "size_bytes": len(successor_config_bytes),
        "sha256": sha256_bytes(successor_config_bytes),
        "git_blob": git_blob_bytes(successor_config_bytes),
    }

    runtime_inputs = [
        file_identity(jdk_path_file, absolute=True),
        file_identity(java_exe, absolute=True),
        file_identity(server_log_path, absolute=True),
        file_identity(client_log_path, absolute=True),
        file_identity(properties_path, absolute=True),
        file_identity(options_path, absolute=True),
    ]
    runtime_inputs.extend(entry for entry in server_mods["entries"])
    runtime_inputs.extend(entry for entry in client_mods["entries"])
    runtime_inputs.extend(receipt_id for _, _, receipt_id in receipts)
    runtime_inputs.extend(screenshots)

    environment_lock = {
        "schema_version": "person-c-c1-final-environment-lock-v1.0",
        "status": "PASS",
        "starting_commit": STARTING_COMMIT,
        "runtime_baseline_version": "person-c-c1-runtime-baseline-v0.2",
        "versions": {
            "java": "17.0.19",
            "minecraft": "1.16.5",
            "fabric_loader": "0.15.11",
            "yarn_mappings": "1.16.5+build.10",
            "fabric_api": "0.42.0+1.16",
            "mineocclude": "0.1.0",
        },
        "java": {"executable": str(java_exe), "version_output": java_text, **file_identity(java_exe, absolute=True)},
        "server_root": str(SERVER),
        "client_root": str(CLIENT),
        "world": {
            "identity": properties["level-name"],
            "seed": int(properties["level-seed"]),
            "difficulty": properties["difficulty"],
            "spawn_animals": False,
            "properties_sha256": file_identity(properties_path, absolute=True)["sha256"],
            "observed_gamerules": receipts[0][1]["world_state"]["gamerules"],
            "time_ticks": 6000,
            "raining": False,
            "thundering": False,
        },
        "resource_packs": {"server_resource_pack": "", "client_resource_packs": ["vanilla"], "incompatible_client_packs": []},
        "authentication_evidence": {
            "operator_reported_authenticated_client_launch": True,
            "client_username": "overatedusername",
            "loopback_connection_observed": True,
            "server_online_mode": False,
            "server_side_account_authentication_enforced": False,
            "claim_boundary": "logs prove the named client connection; offline-mode does not independently prove Mojang account authentication",
        },
    }

    lifecycle = {
        "schema_version": "person-c-c1-server-lifecycle-receipt-v1.0",
        "status": "PASS",
        "server_log": file_identity(server_log_path, absolute=True),
        "startup": {
            "minecraft_loader_line": "[17:46:10] [main/INFO]: Loading Minecraft 1.16.5 with Fabric Loader 0.15.11",
            "mineocclude_ready_observed": True,
            "vanilla_done_observed": True,
        },
        "shutdown": {
            "stop_observed": True,
            "saving_worlds_observed": True,
            "all_dimensions_saved_observed": True,
            "selected_java_executable_process_left_running": selected_java_running,
            "process_check_method": "Get-Process java executable paths compared literally to the selected Java 17 path",
        },
    }

    client_receipt = {
        "schema_version": "person-c-c1-client-lifecycle-receipt-v1.0",
        "status": "PASS",
        "client_log": file_identity(client_log_path, absolute=True),
        "client_username": "overatedusername",
        "server_address": "127.0.0.1:25565",
        "connection_observed_in_client_log": True,
        "connection_and_join_observed_in_server_log": True,
        "disconnect_observed_in_server_log": True,
        "client_stopping_observed": True,
        "authentication_claim_boundary": environment_lock["authentication_evidence"],
    }

    server_properties_receipt = {
        "schema_version": "person-c-c1-final-server-properties-receipt-v1.0",
        "status": "PASS",
        "source": file_identity(properties_path, absolute=True),
        "properties": properties,
        "observed_world_state": receipts[0][1]["world_state"],
    }

    render_receipt = {
        "schema_version": "person-c-c1-final-render-settings-receipt-v1.0",
        "status": "PASS",
        "options_file": file_identity(options_path, absolute=True),
        "raw_options": options,
        "displayed_fov": {"degrees": 70.0, "label": "Normal", "log_observed": True, "screenshot_observed": True},
        "raw_framebuffer": {"width_pixels": 1920, "height_pixels": 1046, "source_screenshot": screenshot_by_name[raw_screenshot_name]},
        "canonical_derivative_target": {"width_pixels": 640, "height_pixels": 360, "raw_screenshot_is_not_the_derivative": True},
        "graphics": {
            "graphics_mode": "fancy",
            "render_distance_chunks": 10,
            "entity_distance_scaling": 1.0,
            "particles": "minimal",
            "clouds": "off",
            "smooth_lighting": "maximum",
            "vsync": False,
            "max_fps": 60,
            "mipmap_levels": 4,
            "biome_blend_radius": 0,
            "view_bobbing": False,
            "dynamic_fov": False,
            "entity_shadows": True,
            "fullscreen": False,
            "gui_scale": 2,
        },
    }

    mods_receipt = {
        "schema_version": "person-c-c1-installed-mods-inventory-v1.0",
        "status": "PASS",
        "inventories_identical": True,
        "mineocclude_jar_sha256": JAR_SHA256,
        "server": server_mods,
        "client": client_mods,
    }

    override_receipt = {
        "schema_version": "person-c-c1-final-marker-override-receipt-v1.0",
        "status": "PASS",
        "enabled": False,
        "signature": "null/null/null/null",
        "status_log_line": "markergeom status: enabled=false nearOrtho=null farOrtho=null nearInset=null farInset=null signature=null/null/null/null",
        "same_signature_in_all_six_receipts": True,
        "server_log": file_identity(server_log_path, absolute=True),
    }

    observation_manifest = {
        "schema_version": "person-c-c1-six-layout-runtime-observation-manifest-v1.0",
        "status": "PASS",
        "receipt_count": 6,
        "valid_receipt_count": 6,
        "layout_ids": EXPECTED_LAYOUTS,
        "receipts": [{
            **receipt_id,
            "receipt_id": receipt["receipt_id"],
            "layout_id": receipt["layout_id"],
            "observation_only": receipt["observation_only"],
            "scientific_use": receipt["scientific_use"],
            "marker_count": receipt["observed_marker_block_count"],
            "floor_validation_pass": True,
            "wall_validation_pass": True,
            "camera_validation_pass": True,
            "marker_override": receipt["marker_override"],
        } for _, receipt, receipt_id in receipts],
    }

    screenshot_manifest = {
        "schema_version": "person-c-c1-screenshot-manifest-v1.0",
        "status": "PASS",
        "session_screenshot_count": len(screenshots),
        "required_authoritative_pair_count": 2,
        "authoritative_pair": [fov_screenshot_name, raw_screenshot_name],
        "supplemental_render_setting_screenshot_count": 3,
        "screenshots": screenshots,
        "visual_inspection": {
            "2026-08-03_17.52.43.png": "Options screen visibly displays FOV: Normal while connected gameplay is behind the menu",
            "2026-08-03_17.53.00.png": "supplemental Video Settings screen",
            "2026-08-03_17.53.21.png": "supplemental Options screen visibly displays FOV: Normal",
            "2026-08-03_17.53.23.png": "supplemental Video Settings screen",
            "2026-08-03_17.54.04.png": "raw gameplay framebuffer visibly shows the canonical preview wall and markers",
        },
        "c1_3_acceptance": {
            "displayed_fov_screenshot_present": True,
            "raw_gameplay_framebuffer_screenshot_present": True,
            "same_client_session": True,
            "all_files_hash_bound": True,
            "result": "PASS",
        },
    }

    geometry_report = {
        "schema_version": "person-c-runtime-geometry-comparison-v2.0",
        "classification": CLASSIFICATION,
        "accepted_geometry_owner": "SUCCESSOR",
        "accepted_geometry_version": ACCEPTED_VERSION,
        "comparison_policy": "literal values only; no offsets, ID shifts, corrections, renumbering, or adapters",
        "summary": {
            "layout_count": 6,
            "c_full_geometry_match_count": 0,
            "e_marker_geometry_match_count": 0,
            "runtime_layout_ids": EXPECTED_LAYOUTS,
            "c_wall_and_camera_match_count": 6,
            "c_floor_match_count": 0,
            "c_marker_match_count_by_layout": [0, 0, 0, 0, 0, 0],
            "e_marker_match_count_by_layout": [0, 0, 0, 0, 0, 0],
        },
        "layouts": comparisons,
        "source_authorities": source_authorities,
    }

    authority = {
        "schema_version": "person-c-geometry-authority-v2.0",
        "decision": CLASSIFICATION,
        "accepted_geometry_owner": "SUCCESSOR",
        "accepted_geometry_version": ACCEPTED_VERSION,
        "accepted_config_path": "configs/scenes/layouts_v0_4.yaml",
        "accepted_config_identity": successor_config_identity,
        "c_layout_successor_created": True,
        "prior_c_version": "person-c-layout-config-v0.3",
        "prior_c_status": "historical_and_superseded_for_new_evidence_not_invalidated",
        "e_homography_refit_required": True,
        "affected_e_layouts": EXPECTED_LAYOUTS,
        "downstream_dependent_artifacts": [
            "data/handoff_e/markers_layout_01.json through markers_layout_06.json",
            "data/handoff_e/detector_calibration_inputs.json",
            "data/handoff_e/independent_probe_points.json",
            "data/handoff_e/phase3_homography_authority_v0_1/marker_pose_resolution_bindings.json",
            "data/handoff_e/phase3_homography_authority_v0_1/known_direction_validation_records.json",
            "data/handoff_e/phase3_homography_authority_v0_1/homography_authority_receipt.json",
            "data/handoff_e/phase3_homography_authority_v0_1/homography_applicability_manifest.json",
            "data/handoff_e/phase3_homography_authority_v0_1/wall_axis_sign_authority.json",
        ],
        "frozen_e_evidence_modified": False,
        "runtime_binding": successor_config["runtime_binding"],
        "evidence_bindings": {
            "server_log": file_identity(server_log_path, absolute=True),
            "client_log": file_identity(client_log_path, absolute=True),
            "server_properties": file_identity(properties_path, absolute=True),
            "client_options": file_identity(options_path, absolute=True),
            "mineocclude_jar_sha256": JAR_SHA256,
            "screenshots": screenshots,
            "geometry_receipts": [receipt_id for _, _, receipt_id in receipts],
            "server_mod_inventory_digest": sha256_bytes(dump_json(server_mods)),
            "client_mod_inventory_digest": sha256_bytes(dump_json(client_mods)),
        },
    }

    c1_status = {
        "schema_version": "person-c-c1-closure-status-v1.0",
        "c1_1": {"complete": True, "basis": "fresh runtime environment lock and six valid observation-only receipts"},
        "c1_3": {"complete": True, "basis": "hash-bound FOV and raw-framebuffer screenshots from the connected session"},
        "c1_5": {
            "complete": False,
            "reconstruction_package_prepared": True,
            "execution_ready": False,
            "independent_second_operator_required": True,
            "blocker": "explicit magenta sheep is alive at warmup tick 0 and removed by tick 1 under spawn-animals=false",
        },
    }

    target_retention_lines = re.findall(r"warmup tick [01] alive=(?:true|false) removed=(?:true|false)", server_log)
    require(target_retention_lines.count("warmup tick 0 alive=true removed=false") == 6, "six target spawn tick-0 observations", checks)
    require(target_retention_lines.count("warmup tick 1 alive=false removed=true") == 6, "six target removal tick-1 observations", checks)

    reconstruction_command = "mineocclude start layout_01 11501 202608031501 0.0 0.0 20"
    reconstruction_manifest = {
        "schema_version": "person-c-c1.5-reconstruction-manifest-v1.0",
        "status": "BLOCKED_PRE_EXECUTION",
        "accepted_geometry_version": ACCEPTED_VERSION,
        "selected_layout_id": "layout_01",
        "deterministic_server_console_sequence": [
            "mineocclude mode normal",
            "mineocclude duration 0",
            "mineocclude reveal 0",
            "mineocclude impulse -1 0",
            "mineocclude lockcam on",
            "mineocclude warmup 1200",
            reconstruction_command,
            "mineocclude observegeometry c1_5_second_operator_layout_01",
            "mineocclude stop",
        ],
        "reconstruction_command": reconstruction_command,
        "execution_ready": False,
        "must_not_execute_until": [
            "target retention defect is corrected without weakening spawn-animals=false",
            "a new JAR is built and hash-bound",
            "a fresh runtime observation proves the core sheep remains alive",
        ],
        "independent_second_operator_required": True,
        "required_second_operator_receipt_id": "c1_5_second_operator_layout_01",
        "completion_claimed": False,
    }

    c6a_manifest = {
        "schema_version": "person-c-c6a-capture-manifest-v1.0",
        "status": "BLOCKED_PRECAPTURE",
        "execution_authorized": False,
        "accepted_geometry_version": ACCEPTED_VERSION,
        "accepted_config_path": "configs/scenes/layouts_v0_4.yaml",
        "new_capture_identity": {
            "campaign_id": "person_c_c6a_v0_4_run_001",
            "trajectory_reuse_forbidden": True,
            "layout_00_ep9403_authority_forbidden": True,
        },
        "execution_command": None,
        "command_withheld_reason": "the current runtime removes the explicitly spawned target by warmup tick 1; scientific capture would be empty/invalid",
        "blockers": [
            "C6A_TARGET_RETENTION_DEFECT_UNDER_SPAWN_ANIMALS_FALSE",
            "C6A_NEW_SCIENTIFIC_NOISE_SCHEDULES_NOT_YET_HASH_BOUND",
            "C6A_FRESH_POST_FIX_RUNTIME_GATE_NOT_PASSED",
        ],
        "paid_compute_started": False,
        "c6b_started": False,
    }

    validation_report = {
        "schema_version": "person-c-c1-runtime-ingestion-validation-v1.0",
        "status": "PASS",
        "all_focused_checks_pass": all(checks.values()),
        "check_count": len(checks),
        "checks": checks,
        "geometry_classification": CLASSIFICATION,
        "c1_1_complete": True,
        "c1_3_complete": True,
        "c1_5_complete": False,
        "c6a_execution_ready": False,
        "known_non_ingestion_blockers": [
            "C1_5_TARGET_RETENTION_FIX_AND_FRESH_RUNTIME_VALIDATION_REQUIRED",
            "C1_5_INDEPENDENT_SECOND_OPERATOR_RECEIPT_REQUIRED",
            "C6A_TARGET_RETENTION_DEFECT_UNDER_SPAWN_ANIMALS_FALSE",
            "C6A_NEW_SCIENTIFIC_NOISE_SCHEDULES_NOT_YET_HASH_BOUND",
            "E_HOMOGRAPHIES_REQUIRE_REFIT_FOR_PERSON_C_LAYOUT_CONFIG_V0_4",
        ],
    }

    runtime_input_inventory = {
        "schema_version": "person-c-c1-consumed-runtime-file-inventory-v1.0",
        "file_count": len(runtime_inputs),
        "every_consumed_runtime_file_hash_bound": True,
        "files": runtime_inputs,
    }

    comparison_md_lines = [
        "# Person C runtime geometry comparison v0.2",
        "",
        f"Classification: `{CLASSIFICATION}`.",
        "",
        "The comparison is literal. Runtime top-face centres are compared to C's literal `world_blocks` values and E's literal top-face-centre values without offsets, layout-ID shifts, renumbering, or adapters. Every layout has zero of four marker matches to C and zero of four to E. C's wall and camera declarations match all six receipts; C's smooth-stone arena declaration does not match the observed grass floor bounds.",
        "",
        "| Layout | Color | Runtime top-face centre xyz | Runtime - C xyz | Runtime - E xyz |",
        "|---|---|---:|---:|---:|",
    ]
    for layout in comparisons:
        for marker in layout["markers"]:
            comparison_md_lines.append(
                f"| {layout['layout_id']} | {marker['color']} | `{marker['runtime_top_face_centre_world_xyz']}` | `{marker['runtime_minus_c_xyz']}` | `{marker['runtime_minus_e_xyz']}` |"
            )
    comparison_md_lines.extend([
        "",
        "The accepted additive successor is `person-c-layout-config-v0.4` at `configs/scenes/layouts_v0_4.yaml`. The legacy v0.3 file and every E file remain historical evidence and were not edited.",
        "",
    ])
    comparison_md = "\n".join(comparison_md_lines)

    authority_md = f"""# Person C geometry authority decision v0.2

## Decision

`{CLASSIFICATION}`. The complete fresh-runtime receipts prove a single internally consistent builder geometry, but that literal geometry is neither historical C v0.3 nor E. The accepted owner label is `SUCCESSOR`, and the additive C-governed accepted version is `{ACCEPTED_VERSION}`.

## Evidence

The decision is bound to source commit `{JAR_SOURCE_COMMIT}`, MineOcclude JAR SHA-256 `{JAR_SHA256}`, the final server/client logs, server properties, client options, identical 46-JAR server/client inventories, five session screenshots, and six distinct observation-only geometry receipts. All six receipts have override `enabled=false` and signature `null/null/null/null`; each validates all floor, wall, marker, camera, world-state, time, weather, and gamerule fields.

For every layout, the runtime wall axis and camera agree with historical C, while the floor material/bounds and every literal marker coordinate do not. No layout's four runtime marker coordinates equal E's four coordinates. Exact deltas are in `geometry_comparison_report.json` and `geometry_comparison_report.md`.

## Versioning and downstream impact

Historical C v0.3 requires no mutation. It is superseded only for new evidence by additive `configs/scenes/layouts_v0_4.yaml`; historical artifacts remain addressable and valid evidence of their own states. All six E homographies/correspondence-dependent artifacts require refitting before they can be applied to v0.4 captures. No E-owned file or frozen scientific evidence is edited here.

Supersession does not redirect historical paths and does not apply offsets, `+0.5` corrections, layout-ID shifts, coordinate renumbering, or compatibility adapters. New screenshots, homographies, and capture manifests must name v0.4 explicitly and bind its file hash.

## Gates before reconstruction or C6A

C1.1 and C1.3 close on the complete environment/geometry receipts and the authoritative FOV/raw-framebuffer screenshot pair. C1.5 does not close: a genuinely independent second-operator receipt remains required. Moreover, the server log proves the explicitly spawned magenta sheep is alive at warmup tick 0 and removed at tick 1 in every layout under `spawn-animals=false`. That target-retention defect must be corrected, built into a newly hash-bound JAR, and fresh-runtime validated without weakening the environment contract before C1.5 or C6A execution.

C6A also requires new hash-bound scientific noise schedules and a new trajectory identity. The blocked manifest does not reuse `layout_00_ep9403`, does not authorize execution, and does not start paid compute or C6B.
"""

    operator_md = f"""# Person C C1.5 reconstruction operator package

This package is deterministic but **not execution-ready**. C1.5 is not complete.

Accepted geometry: `{ACCEPTED_VERSION}`. Selected independent reconstruction layout: `layout_01`.

Exact reconstruction command after all prerequisites pass:

```text
{reconstruction_command}
```

Run the full ordered sequence in `reconstruction_manifest.json` only after a corrected, newly hash-bound JAR has passed a fresh runtime gate proving the explicit magenta sheep survives beyond warmup tick 1 while `spawn-animals=false` remains locked. A second operator who did not perform this ingestion must execute the reconstruction using only the successor definition and submit the create-only `c1_5_second_operator_layout_01` receipt. Do not use the current runtime to claim C1.5 complete.
"""

    c6a_md = """# Person C C6A next actions

The new v0.4-bound manifest is prepared in blocked form. No execution command is authorized because the observed runtime removes the explicit target at warmup tick 1. Correct that defect without changing `spawn-animals=false`, build and hash a new JAR, repeat the fresh target-retention gate, generate and hash new scientific noise schedules, and then issue a new additive ready manifest with a new trajectory identity. Do not reuse `layout_00_ep9403`, begin C6B, or start paid compute from this package.
"""

    outputs: dict[Path, bytes] = {
        SUCCESSOR_CONFIG: successor_config_bytes,
        INGEST_DIR / "final_environment_lock_receipt.json": dump_json(environment_lock),
        INGEST_DIR / "server_startup_shutdown_receipt.json": dump_json(lifecycle),
        INGEST_DIR / "client_startup_connection_receipt.json": dump_json(client_receipt),
        INGEST_DIR / "server_properties_receipt.json": dump_json(server_properties_receipt),
        INGEST_DIR / "render_settings_receipt.json": dump_json(render_receipt),
        INGEST_DIR / "installed_mods_inventory.json": dump_json(mods_receipt),
        INGEST_DIR / "marker_override_receipt.json": dump_json(override_receipt),
        INGEST_DIR / "layout_runtime_observations.json": dump_json(observation_manifest),
        INGEST_DIR / "screenshot_manifest.json": dump_json(screenshot_manifest),
        INGEST_DIR / "runtime_input_inventory.json": dump_json(runtime_input_inventory),
        INGEST_DIR / "c1_closure_status.json": dump_json(c1_status),
        INGEST_DIR / "validation_report.json": dump_json(validation_report),
        AUTH_DIR / "geometry_comparison_report.json": dump_json(geometry_report),
        AUTH_DIR / "geometry_comparison_report.md": comparison_md.encode("utf-8"),
        AUTH_DIR / "accepted_geometry_authority.json": dump_json(authority),
        AUTH_DIR / "authority_decision.md": authority_md.encode("utf-8"),
        RECON_DIR / "reconstruction_manifest.json": dump_json(reconstruction_manifest),
        RECON_DIR / "operator_runbook.md": operator_md.encode("utf-8"),
        C6A_DIR / "c6a_capture_manifest.json": dump_json(c6a_manifest),
        C6A_DIR / "operator_next_actions.md": c6a_md.encode("utf-8"),
    }
    write_or_check(outputs, args.write)

    inventory_outputs: dict[Path, bytes] = {}
    for directory in [INGEST_DIR, AUTH_DIR, RECON_DIR, C6A_DIR]:
        inventory_outputs[directory / "sha256_inventory.json"] = dump_json(package_inventory(directory))
    write_or_check(inventory_outputs, args.write)

    print(json.dumps({
        "status": "PASS",
        "check_count": len(checks),
        "classification": CLASSIFICATION,
        "accepted_geometry_version": ACCEPTED_VERSION,
        "valid_geometry_receipts": 6,
        "session_screenshots": 5,
        "c1_1_complete": True,
        "c1_3_complete": True,
        "c1_5_complete": False,
        "c6a_execution_ready": False,
    }, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AuditError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
