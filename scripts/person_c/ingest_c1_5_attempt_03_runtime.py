#!/usr/bin/env python3
"""Fail-closed ingestion for the first-operator C1.5 attempt-03 receipt."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[2]
SERVER = Path(r"C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\server")
CLIENT = Path(r"C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\client")
CONFIG = REPO / "configs/scenes/layouts_v0_4.yaml"
MANIFEST = REPO / "docs/status/person_c_c1_5_attempt_03_v0_1/attempt_03_manifest.json"
FAILURE_RECORD = REPO / "docs/status/person_c_c1_5_attempt_03_v0_1/attempt_02_failure_record.json"
RUNTIME_SCHEDULE = SERVER / "mineocclude_schedules/episode_11504.jsonl"
INSTALLED_JAR = SERVER / "mods/mineocclude-0.1.1.jar"
EXPECTED_JAR_SHA256 = "9ecbb5e85b249409d38428ea479c3f09ec97dd884a97ecb48d79590e4c03de52"
EXPECTED_GEOMETRY_VERSION = "person-c-layout-config-v0.4"
EXPECTED_LAYOUT = "layout_01"
EXPECTED_EPISODE = 11504
EXPECTED_SEED = 202608031504
EXPECTED_WARMUP_TICKS = 2400
EXPECTED_RECEIPT = "c1_5_first_operator_attempt_03_layout_01"


def identity(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    return {"path": str(path.resolve()), "size_bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest()}


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def find_line(lines: list[str], pattern: str) -> int:
    regex = re.compile(pattern)
    for index, line in enumerate(lines):
        if regex.search(line):
            return index
    raise ValueError(f"required server-log event absent: {pattern}")


def line_time(line: str) -> datetime:
    match = re.match(r"\[(\d{2}:\d{2}:\d{2})\]", line)
    if not match:
        raise ValueError(f"server-log line has no HH:MM:SS timestamp: {line}")
    return datetime.strptime(match.group(1), "%H:%M:%S")


def validate_retry_log(lines: list[str]) -> dict[str, Any]:
    warmup = find_line(lines, r"Warmup delay set to 2400 ticks \(120\.0s\)")
    armed = find_line(lines, r"episode 11504 armed \(layout=layout_01, 2400 warmup \+ 20 record ticks")
    status = find_line(
        lines,
        r"target status: valid=true required=true count=1.*episode=11504.*lifecycle=READY.*problems=NONE",
    )
    observed = find_line(
        lines,
        r"wrote read-only geometry receipt .*c1_5_first_operator_attempt_03_layout_01\.json",
    )
    aborted = find_line(lines, r"episode 11504 aborted during warmup")
    stopping = find_line(lines, r"Stopping server")
    require(warmup < armed < status < observed < aborted < stopping,
            "retry event order is not warmup2400 < armed < targetstatus < observe < warmup abort < shutdown")
    require(not any("episode 11504 recording started" in line for line in lines),
            "retry entered recording before stop")
    require(not any("target retention failure" in line for line in lines),
            "retry log contains target-retention failure")
    armed_time = line_time(lines[armed])
    status_time = line_time(lines[status])
    if status_time < armed_time:
        status_time += timedelta(days=1)
    delay = int((status_time - armed_time).total_seconds())
    require(10 <= delay <= 15,
            "targetstatus was not issued approximately 10 seconds after arming")
    return {
        "warmup_ticks": EXPECTED_WARMUP_TICKS,
        "observation_window_seconds": 120,
        "armed_line_index": armed,
        "target_status_line_index": status,
        "observation_line_index": observed,
        "warmup_abort_line_index": aborted,
        "shutdown_line_index": stopping,
        "armed_to_status_seconds": delay,
        "recording_started": False,
        "observation_before_recording": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--geometry-receipt", type=Path, required=True)
    parser.add_argument("--screenshot", type=Path, required=True)
    parser.add_argument("--attestation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    server_log_path = SERVER / "logs/latest.log"
    client_log_path = CLIENT / "logs/latest.log"
    server_properties = SERVER / "server.properties"
    client_options = CLIENT / "options.txt"
    required = [CONFIG, MANIFEST, FAILURE_RECORD, RUNTIME_SCHEDULE, INSTALLED_JAR,
                args.geometry_receipt, args.screenshot, args.attestation,
                server_log_path, client_log_path, server_properties, client_options]
    for path in required:
        require(path.is_file(), f"required evidence file absent: {path}")
    require(not args.output.exists(), f"create-only output already exists: {args.output}")

    manifest = load(MANIFEST)
    config = load(CONFIG)
    receipt = load(args.geometry_receipt)
    attestation = load(args.attestation)
    failure_record = load(FAILURE_RECORD)
    require(config["config_version"] == EXPECTED_GEOMETRY_VERSION,
            "accepted geometry version mismatch")
    require(manifest["retry"]["episode_id"] == EXPECTED_EPISODE
            and manifest["retry"]["seed"] == EXPECTED_SEED
            and manifest["retry"]["warmup_ticks"] == EXPECTED_WARMUP_TICKS,
            "attempt-03 manifest identity/warmup mismatch")
    require(manifest["retry"]["ordered_start_commands"][-2:]
            == ["mineocclude warmup 2400",
                "mineocclude start layout_01 11504 202608031504 0.0 0.0 20"],
            "attempt-03 start sequence does not bind warmup 2400 immediately before start")
    require(manifest["reserved_second_operator"]["episode_id"] == 11502
            and manifest["reserved_second_operator"]["still_required"] is True,
            "independent second-operator reservation mismatch")
    require(failure_record["classification"]
            == "POST_FINALIZATION_OBSERVATION_INVALID_NOT_TARGET_RETENTION_FAILURE",
            "attempt-02 failure classification mismatch")
    require(failure_record["preservation"]["status"] == "PRESERVED_HASH_BOUND",
            "attempt-02 preservation record is not valid")
    require(identity(INSTALLED_JAR)["sha256"] == EXPECTED_JAR_SHA256,
            "installed MineOcclude JAR hash mismatch")
    require(identity(RUNTIME_SCHEDULE)["sha256"]
            == manifest["retry"]["schedule"]["repository"]["sha256"],
            "runtime retry schedule hash mismatch")
    schedule_header = json.loads(RUNTIME_SCHEDULE.open(encoding="utf-8-sig").readline())
    require(schedule_header["seed"] == EXPECTED_SEED
            and schedule_header["q"] == 0.0
            and schedule_header["n_draws"] == 20,
            "retry schedule header mismatch")

    require(receipt.get("receipt_id") == EXPECTED_RECEIPT, "receipt identity mismatch")
    require(receipt.get("layout_id") == EXPECTED_LAYOUT, "layout identity mismatch")
    require(receipt.get("episode_id") == EXPECTED_EPISODE, "episode identity mismatch")
    require(receipt.get("observation_only") is True, "receipt is not observation-only")
    require(receipt.get("scientific_use") == "forbidden", "receipt scientific-use field mismatch")
    target = receipt.get("target", {})
    require(target.get("valid") is True and target.get("tagged_target_count") == 1,
            "target status is not valid/exactly-one")
    for key, value in {
        "required": True, "tag": "mineocclude_experimental_target",
        "entity_type": "minecraft:sheep", "color": "magenta",
        "no_ai": True, "silent": True, "persistent": True,
        "invulnerable": True, "adult": True, "alive": True, "removed": False,
    }.items():
        require(target.get(key) == value, f"target field mismatch: {key}")
    require(target.get("actual_xyz") == target.get("expected_xyz"), "target location mismatch")
    require(target.get("problems") == [], "target receipt contains problems")

    layout = next(item for item in config["layouts"] if item["layout_id"] == EXPECTED_LAYOUT)
    receipt_markers = {row["color"]: row for row in receipt["markers"]}
    for expected in layout["markers"]:
        actual = receipt_markers[expected["color"]]
        require(actual["block_pos_xyz"] == expected["block_pos_xyz"],
                f"marker BlockPos mismatch: {expected['color']}")
        require(actual["top_face_centre_world_xyz"] == expected["top_face_centre_world_xyz"],
                f"marker top-face centre mismatch: {expected['color']}")
        require(actual["matches"] is True, f"marker block mismatch: {expected['color']}")
    require(receipt["camera"]["observed_players"], "no observed player camera")
    camera = receipt["camera"]["observed_players"][0]
    expected_camera = layout["camera"]
    require(camera["feet_xyz"] == expected_camera["feet_xyz"], "camera position mismatch")
    require(camera["yaw_degrees"] == expected_camera["yaw_degrees"], "camera yaw mismatch")
    require(camera["pitch_degrees"] == expected_camera["pitch_degrees"], "camera pitch mismatch")

    require(attestation.get("template") is False, "attestation remains a template")
    require(attestation.get("operator_role") == "first" and attestation.get("attempt") == 3,
            "attestation role/attempt mismatch")
    require(bool(attestation.get("operator_id")), "operator identity missing")
    for key in ("targetstatus_passed_after_ten_seconds",
                "observegeometry_completed_during_warmup_before_recording",
                "receipt_write_confirmed_before_f2",
                "f2_pressed_immediately_after_receipt_confirmation",
                "mineocclude_stop_issued_immediately_after_f2"):
        require(attestation.get(key) is True, f"operator ordering attestation missing: {key}")

    server_lines = server_log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    chronology = validate_retry_log(server_lines)
    require(any("loaded immutable noise schedule (20 draws)" in line
                and "episode_11504.jsonl" in line for line in server_lines),
            "immutable attempt-03 schedule load missing from server log")
    client_log = client_log_path.read_text(encoding="utf-8", errors="replace")
    require("Connecting to 127.0.0.1, 25565" in client_log and "Stopping!" in client_log,
            "client connection/exit evidence incomplete")
    require("spawn-animals=false" in server_properties.read_text(encoding="utf-8-sig").splitlines(),
            "spawn-animals=false not retained")

    png = args.screenshot.read_bytes()
    require(png[:8] == b"\x89PNG\r\n\x1a\n" and png[12:16] == b"IHDR",
            "screenshot is not PNG")
    width, height = struct.unpack(">II", png[16:24])
    require((width, height) == (640, 360), "screenshot is not the canonical 640x360 resolution")

    result = {
        "schema_version": "person-c-c1.5-ingested-first-operator-attempt-03-v0.1",
        "operator_role": "first", "attempt": 3,
        "accepted_geometry_version": EXPECTED_GEOMETRY_VERSION,
        "layout_id": EXPECTED_LAYOUT, "episode_id": EXPECTED_EPISODE,
        "seed": EXPECTED_SEED, "warmup_ticks": EXPECTED_WARMUP_TICKS,
        "observation_window_seconds": 120, "status": "PASS",
        "observation_during_warmup_before_recording": True,
        "chronology": chronology, "c1_5_complete": False,
        "independent_second_operator_still_required": True,
        "files": {
            "geometry_receipt": identity(args.geometry_receipt),
            "screenshot": {**identity(args.screenshot), "width": width, "height": height},
            "attestation": identity(args.attestation),
            "server_log": identity(server_log_path), "client_log": identity(client_log_path),
            "server_properties": identity(server_properties), "client_options": identity(client_options),
            "retry_schedule": identity(RUNTIME_SCHEDULE), "installed_jar": identity(INSTALLED_JAR),
            "accepted_geometry": identity(CONFIG), "attempt_02_failure_record": identity(FAILURE_RECORD),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("xb") as handle:
        handle.write((json.dumps(result, indent=2) + "\n").encode("utf-8"))
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
