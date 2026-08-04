#!/usr/bin/env python3
"""Fail-closed ingestion for the final first-operator C1.5 attempt-04 receipt."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
from datetime import datetime
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[2]
SERVER = Path(r"C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\server")
CLIENT = Path(r"C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\client")
CONFIG = REPO / "configs/scenes/layouts_v0_4.yaml"
MANIFEST = REPO / "docs/status/person_c_c1_5_attempt_04_v0_1/attempt_04_manifest.json"
FAILURE_RECORD = REPO / "docs/status/person_c_c1_5_attempt_04_v0_1/attempt_03_failure_record.json"
RUNTIME_SCHEDULE = SERVER / "mineocclude_schedules/episode_11505.jsonl"
INSTALLED_JAR = SERVER / "mods/mineocclude-0.1.1.jar"
EXPECTED_JAR_SHA256 = "9ecbb5e85b249409d38428ea479c3f09ec97dd884a97ecb48d79590e4c03de52"
EXPECTED_RUNTIME_SOURCE_COMMIT = "538a176e1c83dc3b40e220dee8ebb2ac841bd9b4"
EXPECTED_PACKAGE_SOURCE_COMMIT = "a2c1544a528ed0b96bea6d1213f1d79ceb508dc0"
EXPECTED_GEOMETRY_VERSION = "person-c-layout-config-v0.4"
EXPECTED_GEOMETRY_SHA256 = "34495d650d6a8c62b00a916796c90389b48f80d8f20a23eac93207758e993f5d"
EXPECTED_LAYOUT = "layout_01"
EXPECTED_EPISODE = 11505
EXPECTED_SEED = 202608031505
EXPECTED_WARMUP_TICKS = 12000
OBSERVATION_WINDOW_SECONDS = 600
EXPECTED_RECEIPT = "c1_5_first_operator_attempt_04_layout_01"
FAILURE_CLASSIFICATION = (
    "GEOMETRY_RECEIPT_VALID_BUT_SCREENSHOT_AND_ABORT_OCCURRED_AFTER_RECORDING_STARTED"
)


def identity(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    return {
        "path": str(path.resolve()),
        "size_bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def find_line(lines: list[str], pattern: str, source: str) -> int:
    regex = re.compile(pattern)
    for index, line in enumerate(lines):
        if regex.search(line):
            return index
    raise ValueError(f"required {source}-log event absent: {pattern}")


def line_seconds(line: str, source: str) -> int:
    match = re.match(r"\[(\d{2}):(\d{2}):(\d{2})\]", line)
    if not match:
        raise ValueError(f"{source}-log line has no HH:MM:SS timestamp: {line}")
    hour, minute, second = (int(value) for value in match.groups())
    return hour * 3600 + minute * 60 + second


def offset_after(base_seconds: int, event_seconds: int) -> int:
    return (event_seconds - base_seconds) % (24 * 60 * 60)


def validate_retry_logs(server_lines: list[str], client_lines: list[str]) -> dict[str, Any]:
    """Validate the cross-log attempt-04 chronology and return the F2 source name."""
    warmup = find_line(
        server_lines, r"Warmup delay set to 12000 ticks \(600\.0s\)", "server"
    )
    armed = find_line(
        server_lines,
        r"episode 11505 armed \(layout=layout_01, 12000 warmup \+ 20 record ticks",
        "server",
    )
    status = find_line(
        server_lines,
        r"target status: valid=true required=true count=1.*episode=11505.*lifecycle=READY.*problems=NONE",
        "server",
    )
    observed = find_line(
        server_lines,
        r"wrote read-only geometry receipt .*c1_5_first_operator_attempt_04_layout_01\.json",
        "server",
    )
    aborted = find_line(server_lines, r"episode 11505 aborted during warmup", "server")
    stopping = find_line(server_lines, r"Stopping server", "server")
    client_stopping = find_line(client_lines, r"Stopping!", "client")

    require(warmup < armed < status < observed < aborted < stopping,
            "server event order is not warmup12000 < armed < targetstatus < observe < warmup abort < shutdown")
    require(not any("episode 11505 recording started" in line for line in server_lines),
            "episode recording started before warmup abort")
    require(not any("target retention failure" in line.lower() for line in server_lines),
            "retry log contains target-retention failure")

    armed_s = line_seconds(server_lines[armed], "server")
    status_offset = offset_after(armed_s, line_seconds(server_lines[status], "server"))
    observation_offset = offset_after(armed_s, line_seconds(server_lines[observed], "server"))
    abort_offset = offset_after(armed_s, line_seconds(server_lines[aborted], "server"))
    shutdown_offset = offset_after(armed_s, line_seconds(server_lines[stopping], "server"))
    client_shutdown_offset = offset_after(
        armed_s, line_seconds(client_lines[client_stopping], "client")
    )
    require(status_offset >= 10, "targetstatus occurred less than ten seconds after arming")
    screenshot_events: list[tuple[int, int, str]] = []
    for index, line in enumerate(client_lines):
        match = re.search(r"Saved screenshot as ([^\\/\s]+\.png)", line)
        if match:
            event_offset = offset_after(armed_s, line_seconds(line, "client"))
            if observation_offset < event_offset < abort_offset:
                screenshot_events.append((index, event_offset, match.group(1)))
    require(
        len(screenshot_events) == 1,
        "cross-log order is not armed < targetstatus >=10s < receipt < F2 screenshot < warmup abort < server shutdown",
    )
    screenshot, screenshot_offset, screenshot_name = screenshot_events[0]
    require(
        10 <= status_offset < observation_offset < screenshot_offset < abort_offset < shutdown_offset,
        "cross-log order is not armed < targetstatus >=10s < receipt < F2 screenshot < warmup abort < server shutdown",
    )
    require(client_shutdown_offset > abort_offset,
            "client shutdown did not occur after warmup abort")

    return {
        "warmup_ticks": EXPECTED_WARMUP_TICKS,
        "observation_window_seconds": OBSERVATION_WINDOW_SECONDS,
        "armed_line_index": armed,
        "target_status_line_index": status,
        "observation_line_index": observed,
        "screenshot_line_index": screenshot,
        "warmup_abort_line_index": aborted,
        "shutdown_line_index": stopping,
        "armed_to_status_seconds": status_offset,
        "armed_to_observation_seconds": observation_offset,
        "armed_to_screenshot_seconds": screenshot_offset,
        "armed_to_abort_seconds": abort_offset,
        "screenshot_file_name": screenshot_name,
        "recording_started": False,
        "episode_aborted_during_warmup": True,
        "screenshot_after_receipt_before_abort": True,
    }


REQUIRED_ATTESTATION_FIELDS = {
    "schema_version",
    "template",
    "operator_role",
    "attempt",
    "operator_id",
    "independent_from_first_operator",
    "utc_start",
    "utc_end",
    "package_source_commit",
    "preparation_commit",
    "source_commit",
    "runtime_source_commit",
    "mineocclude_jar_sha256",
    "accepted_geometry_version",
    "accepted_geometry_sha256",
    "layout_id",
    "episode_id",
    "seed",
    "warmup_ticks",
    "observed_account_name",
    "fresh_runtime_session",
    "all_runbook_steps_performed_without_memory_or_prior_artifact_reuse",
    "targetstatus_passed_after_ten_seconds",
    "observegeometry_completed_during_warmup_before_recording",
    "receipt_write_confirmed_before_f2",
    "f2_pressed_immediately_after_receipt_confirmation",
    "mineocclude_stop_issued_immediately_after_f2",
    "screenshot_from_same_session",
    "server_stopped_cleanly",
    "notes",
}


def validate_attestation(attestation: dict[str, Any]) -> None:
    missing = sorted(REQUIRED_ATTESTATION_FIELDS - set(attestation))
    require(not missing, f"attestation fields missing: {missing}")
    require(attestation["schema_version"] == "person-c-c1.5-operator-attestation-v0.5",
            "attestation schema mismatch")
    require(attestation["template"] is False, "attestation remains a template")
    require(attestation["operator_role"] == "first" and attestation["attempt"] == 4,
            "attestation role/attempt mismatch")
    require(attestation["independent_from_first_operator"] is False,
            "first-operator independence field mismatch")
    require(bool(attestation["operator_id"]), "operator identity missing")
    require(bool(attestation["observed_account_name"]), "observed account missing")
    require(attestation["package_source_commit"] == EXPECTED_PACKAGE_SOURCE_COMMIT,
            "package source commit mismatch")
    require(re.fullmatch(r"[0-9a-f]{40}", attestation["preparation_commit"] or "") is not None,
            "preparation commit is not a full Git hash")
    require(attestation["source_commit"] == EXPECTED_RUNTIME_SOURCE_COMMIT,
            "source commit mismatch")
    require(attestation["runtime_source_commit"] == EXPECTED_RUNTIME_SOURCE_COMMIT,
            "runtime source commit mismatch")
    require(attestation["mineocclude_jar_sha256"] == EXPECTED_JAR_SHA256,
            "attested MineOcclude JAR mismatch")
    require(attestation["accepted_geometry_version"] == EXPECTED_GEOMETRY_VERSION,
            "attested geometry version mismatch")
    require(attestation["accepted_geometry_sha256"] == EXPECTED_GEOMETRY_SHA256,
            "attested geometry hash mismatch")
    require(attestation["layout_id"] == EXPECTED_LAYOUT,
            "attested layout mismatch")
    require(
        attestation["episode_id"] == EXPECTED_EPISODE
        and attestation["seed"] == EXPECTED_SEED
        and attestation["warmup_ticks"] == EXPECTED_WARMUP_TICKS,
        "attested retry identity mismatch",
    )
    for key in (
        "fresh_runtime_session",
        "all_runbook_steps_performed_without_memory_or_prior_artifact_reuse",
        "targetstatus_passed_after_ten_seconds",
        "observegeometry_completed_during_warmup_before_recording",
        "receipt_write_confirmed_before_f2",
        "f2_pressed_immediately_after_receipt_confirmation",
        "mineocclude_stop_issued_immediately_after_f2",
        "screenshot_from_same_session",
        "server_stopped_cleanly",
    ):
        require(attestation[key] is True, f"operator attestation missing: {key}")
    try:
        start = datetime.fromisoformat(attestation["utc_start"].replace("Z", "+00:00"))
        end = datetime.fromisoformat(attestation["utc_end"].replace("Z", "+00:00"))
    except (AttributeError, ValueError) as exc:
        raise ValueError("attestation UTC times are invalid") from exc
    require(start <= end, "attestation UTC interval is reversed")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--geometry-receipt", type=Path, required=True)
    parser.add_argument("--screenshot", type=Path, required=True)
    parser.add_argument("--attestation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()

    server_log_path = SERVER / "logs/latest.log"
    client_log_path = CLIENT / "logs/latest.log"
    server_properties = SERVER / "server.properties"
    client_options = CLIENT / "options.txt"
    required = [
        CONFIG,
        MANIFEST,
        FAILURE_RECORD,
        RUNTIME_SCHEDULE,
        INSTALLED_JAR,
        args.geometry_receipt,
        args.screenshot,
        args.attestation,
        server_log_path,
        client_log_path,
        server_properties,
        client_options,
    ]
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
    require(identity(CONFIG)["sha256"] == EXPECTED_GEOMETRY_SHA256,
            "accepted geometry hash mismatch")
    retry = manifest["retry"]
    require(
        retry["episode_id"] == EXPECTED_EPISODE
        and retry["seed"] == EXPECTED_SEED
        and retry["warmup_ticks"] == EXPECTED_WARMUP_TICKS
        and retry["record_ticks"] == 20,
        "attempt-04 manifest identity/warmup mismatch",
    )
    require(
        retry["ordered_start_commands"][-2:]
        == [
            "mineocclude warmup 12000",
            "mineocclude start layout_01 11505 202608031505 0.0 0.0 20",
        ],
        "attempt-04 start sequence does not bind warmup 12000 immediately before start",
    )
    require(manifest["reserved_second_operator"]["episode_id"] == 11502
            and manifest["reserved_second_operator"]["still_required"] is True,
            "independent second-operator reservation mismatch")
    require(failure_record["classification"] == FAILURE_CLASSIFICATION,
            "attempt-03 failure classification mismatch")
    require(failure_record["preservation"]["status"] == "PRESERVED_HASH_BOUND",
            "attempt-03 preservation record is not valid")
    require(identity(INSTALLED_JAR)["sha256"] == EXPECTED_JAR_SHA256,
            "installed MineOcclude JAR hash mismatch")
    require(identity(RUNTIME_SCHEDULE)["sha256"] == retry["schedule"]["repository"]["sha256"],
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
    require(receipt.get("running") is True and receipt.get("capturing") is False
            and receipt.get("lifecycle_state") == "READY",
            "receipt was not taken during READY warmup")
    require(isinstance(receipt.get("warmup_ticks_remaining"), int)
            and receipt["warmup_ticks_remaining"] > 0,
            "receipt has no remaining warmup window")
    target = receipt.get("target", {})
    require(target.get("valid") is True
            and target.get("required") is True
            and target.get("tagged_target_count") == 1,
            "target status is not valid/required/exactly-one")
    for key, value in {
        "tag": "mineocclude_experimental_target",
        "entity_type": "minecraft:sheep",
        "color": "magenta",
        "no_ai": True,
        "silent": True,
        "persistent": True,
        "invulnerable": True,
        "adult": True,
        "alive": True,
        "removed": False,
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

    validate_attestation(attestation)
    server_lines = server_log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    client_lines = client_log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    chronology = validate_retry_logs(server_lines, client_lines)
    require(any("loaded immutable noise schedule (20 draws)" in line
                and "episode_11505.jsonl" in line for line in server_lines),
            "immutable attempt-04 schedule load missing from server log")
    client_log = "\n".join(client_lines)
    require("Connecting to 127.0.0.1, 25565" in client_log and "Stopping!" in client_log,
            "client connection/exit evidence incomplete")
    account_match = re.search(r"Setting user: ([A-Za-z0-9_]+)", client_log)
    require(account_match is not None, "authenticated account name missing from client log")
    require(attestation["observed_account_name"] == account_match.group(1),
            "attested account does not match same-session client log")
    require("spawn-animals=false" in server_properties.read_text(encoding="utf-8-sig").splitlines(),
            "spawn-animals=false not retained")

    png = args.screenshot.read_bytes()
    require(png[:8] == b"\x89PNG\r\n\x1a\n" and png[12:16] == b"IHDR",
            "screenshot is not PNG")
    width, height = struct.unpack(">II", png[16:24])
    require((width, height) == (640, 360), "screenshot is not the canonical 640x360 resolution")
    raw_screenshot = CLIENT / "screenshots" / chronology["screenshot_file_name"]
    require(raw_screenshot.is_file(), f"same-session raw screenshot absent: {raw_screenshot}")
    require(identity(raw_screenshot)["sha256"] == identity(args.screenshot)["sha256"],
            "canonical screenshot differs from the same-session F2 screenshot")

    result = {
        "schema_version": "person-c-c1.5-ingested-first-operator-attempt-04-v0.1",
        "operator_role": "first",
        "attempt": 4,
        "accepted_geometry_version": EXPECTED_GEOMETRY_VERSION,
        "layout_id": EXPECTED_LAYOUT,
        "episode_id": EXPECTED_EPISODE,
        "seed": EXPECTED_SEED,
        "warmup_ticks": EXPECTED_WARMUP_TICKS,
        "observation_window_seconds": OBSERVATION_WINDOW_SECONDS,
        "status": "PASS",
        "observation_during_warmup_before_recording": True,
        "episode_aborted_during_warmup": True,
        "chronology": chronology,
        "c1_5_complete": False,
        "independent_second_operator_still_required": True,
        "files": {
            "geometry_receipt": identity(args.geometry_receipt),
            "screenshot": {**identity(args.screenshot), "width": width, "height": height},
            "raw_same_session_screenshot": identity(raw_screenshot),
            "attestation": identity(args.attestation),
            "server_log": identity(server_log_path),
            "client_log": identity(client_log_path),
            "server_properties": identity(server_properties),
            "client_options": identity(client_options),
            "retry_schedule": identity(RUNTIME_SCHEDULE),
            "installed_jar": identity(INSTALLED_JAR),
            "accepted_geometry": identity(CONFIG),
            "attempt_03_failure_record": identity(FAILURE_RECORD),
        },
    }
    if not args.validate_only:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("xb") as handle:
            handle.write((json.dumps(result, indent=2) + "\n").encode("utf-8"))
    print(json.dumps({
        "status": "PASS",
        "validate_only": args.validate_only,
        "episode_id": EXPECTED_EPISODE,
        "screenshot_file_name": chronology["screenshot_file_name"],
        "output": None if args.validate_only else str(args.output.resolve()),
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
