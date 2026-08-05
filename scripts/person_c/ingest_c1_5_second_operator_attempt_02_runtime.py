#!/usr/bin/env python3
"""Fail-closed validator/ingester for C1.5 second-operator attempt 02."""

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
MANIFEST = REPO / "docs/status/person_c_c1_5_second_operator_attempt_02_v0_1/attempt_02_manifest.json"
FAILURE_RECORD = REPO / "docs/status/person_c_c1_5_second_operator_attempt_02_v0_1/attempt_01_failure_record.json"
FIRST_SUCCESS = REPO / "docs/status/person_c_c1_5_first_operator_attempt_04_success_v0_1/first_operator_success_receipt.json"
RUNTIME_SCHEDULE = SERVER / "mineocclude_schedules/episode_11506.jsonl"
INSTALLED_JAR = SERVER / "mods/mineocclude-0.1.1.jar"
SERVER_LOG_ARCHIVE = SERVER / "c1_5_evidence/second_operator_attempt_02_success/server_latest.log"
CLIENT_LOG_ARCHIVE = CLIENT / "c1_5_evidence/second_operator_attempt_02_success/client_latest.log"
FIRST_ATTESTATION = SERVER / "c1_5_evidence/first_operator_attempt_04_attestation.json"
FIRST_INGESTED = SERVER / "c1_5_evidence/first_operator_attempt_04_ingested.json"
ATTEMPT_01_RECEIPT = SERVER / "mineocclude_observations/c1_5_second_operator_attempt_01_layout_01.json"
ATTEMPT_01_SCREENSHOT = CLIENT / "screenshots/2026-08-03_22.25.53.png"
ATTEMPT_01_SERVER_LOG = SERVER / "c1_5_evidence/second_operator_attempt_01_preserved/server_latest.log"
ATTEMPT_01_CLIENT_LOG = CLIENT / "c1_5_evidence/second_operator_attempt_01_preserved/client_latest.log"

EXPECTED_JAR_SHA256 = "9ecbb5e85b249409d38428ea479c3f09ec97dd884a97ecb48d79590e4c03de52"
EXPECTED_RUNTIME_SOURCE_COMMIT = "538a176e1c83dc3b40e220dee8ebb2ac841bd9b4"
EXPECTED_PACKAGE_SOURCE_COMMIT = "75f6515aead5755f1f47a3cddea354102eead328"
EXPECTED_GEOMETRY_VERSION = "person-c-layout-config-v0.4"
EXPECTED_GEOMETRY_SHA256 = "34495d650d6a8c62b00a916796c90389b48f80d8f20a23eac93207758e993f5d"
EXPECTED_FAILURE_CLASSIFICATION = "SCREENSHOT_CAPTURED_BEFORE_GEOMETRY_RECEIPT_CONFIRMATION"
EXPECTED_ATTEMPT_01_ACCOUNT = "Santa313"
EXPECTED_FIRST_ATTESTATION_SHA256 = "bd4b0f5070a6d2b96b03e81dbe8e90ac9b7e51e31fbebb9e556cea9532605edd"
EXPECTED_FIRST_INGESTED_SHA256 = "55efd6c247d873f0bda59f48a66817952fbb22e3566c4e416a63e4b42461f5b9"
EXPECTED_LAYOUT = "layout_01"
EXPECTED_EPISODE = 11506
EXPECTED_SEED = 202608031506
EXPECTED_WARMUP_TICKS = 12000
OBSERVATION_WINDOW_SECONDS = 600
EXPECTED_RECEIPT = "c1_5_second_operator_attempt_02_layout_01"

ATTEMPT_01_HASHES = {
    ATTEMPT_01_RECEIPT: "7625fd454b71acedcd42524cab64bb799147020e21e7e78e888f3d31e092b630",
    ATTEMPT_01_SCREENSHOT: "ebcde38bf4b2e8edd313d26de5bf95efabda0a183354ad09d03593565c063c21",
    ATTEMPT_01_SERVER_LOG: "2dd9c8aa26c1e15f1b9331991d13d24b73bbaa13ce98ff18348283af4248b513",
    ATTEMPT_01_CLIENT_LOG: "155ad971f724ac5f5db81a13d7eae42e032011eb8c70ea4c8e2cb3c0a2249812",
}

REQUIRED_ATTESTATION_FIELDS = {
    "schema_version", "template", "operator_role", "attempt", "operator_id",
    "independent_from_first_operator", "same_human_as_second_operator_attempt_01",
    "utc_start", "utc_end", "package_source_commit", "preparation_commit",
    "source_commit", "runtime_source_commit", "mineocclude_jar_sha256",
    "accepted_geometry_version", "accepted_geometry_sha256", "layout_id",
    "episode_id", "seed", "warmup_ticks", "observed_account_name",
    "attempt_01_observed_account_name", "attempt_01_geometry_receipt_sha256",
    "attempt_01_failure_record_sha256", "fresh_runtime_session",
    "targetstatus_passed_after_at_least_ten_seconds",
    "observegeometry_completed_before_receipt_confirmation",
    "receipt_write_confirmed_before_f2", "exactly_one_f2_after_receipt_confirmation",
    "mineocclude_stop_aborted_during_warmup", "recording_never_started",
    "screenshot_from_same_session", "server_stopped_cleanly",
    "operator_identity_differs_from_first_operator",
    "authenticated_account_differs_from_first_operator", "notes",
}


def identity(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    return {"path": str(path.resolve()), "size_bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


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
    if match is None:
        raise ValueError(f"{source}-log line has no HH:MM:SS timestamp: {line}")
    hour, minute, second = (int(value) for value in match.groups())
    return hour * 3600 + minute * 60 + second


def offset_after(base_seconds: int, event_seconds: int) -> int:
    return (event_seconds - base_seconds) % 86400


def validate_attempt_02_logs(server_lines: list[str], client_lines: list[str]) -> dict[str, Any]:
    warmup = find_line(server_lines, r"Warmup delay set to 12000 ticks \(600\.0s\)", "server")
    armed = find_line(server_lines, r"episode 11506 armed \(layout=layout_01, 12000 warmup \+ 20 record ticks", "server")
    status = find_line(server_lines, r"target status: valid=true required=true count=1.*episode=11506.*lifecycle=READY.*problems=NONE", "server")
    observed = find_line(server_lines, r"wrote read-only geometry receipt .*c1_5_second_operator_attempt_02_layout_01\.json", "server")
    confirmed = find_line(server_lines, r"Wrote observation-only geometry receipt: .*c1_5_second_operator_attempt_02_layout_01\.json", "server")
    aborted = find_line(server_lines, r"episode 11506 aborted during warmup", "server")
    stopping = find_line(server_lines, r"Stopping server", "server")
    client_stopping = find_line(client_lines, r"Stopping!", "client")
    require(
        warmup < armed < status < observed < confirmed < aborted < stopping,
        "server order is not warmup < armed < targetstatus < observegeometry < receipt confirmation < warmup abort < shutdown",
    )
    require(not any("episode 11506 recording started" in line for line in server_lines), "episode 11506 recording started")
    require(not any("target retention failure" in line.lower() for line in server_lines), "attempt-02 log contains target-retention failure")

    armed_s = line_seconds(server_lines[armed], "server")
    status_offset = offset_after(armed_s, line_seconds(server_lines[status], "server"))
    observed_offset = offset_after(armed_s, line_seconds(server_lines[observed], "server"))
    confirmation_offset = offset_after(armed_s, line_seconds(server_lines[confirmed], "server"))
    abort_offset = offset_after(armed_s, line_seconds(server_lines[aborted], "server"))
    shutdown_offset = offset_after(armed_s, line_seconds(server_lines[stopping], "server"))
    client_shutdown_offset = offset_after(armed_s, line_seconds(client_lines[client_stopping], "client"))
    require(status_offset >= 10, "targetstatus occurred less than ten seconds after arming")

    episode_screenshots: list[tuple[int, int, str]] = []
    for index, line in enumerate(client_lines):
        match = re.search(r"Saved screenshot as ([^\\/\s]+\.png)", line)
        if match:
            event_offset = offset_after(armed_s, line_seconds(line, "client"))
            if 0 < event_offset < abort_offset:
                episode_screenshots.append((index, event_offset, match.group(1)))
    require(len(episode_screenshots) == 1, "exactly one F2 screenshot must occur after arming and before warmup abort")
    screenshot, screenshot_offset, screenshot_name = episode_screenshots[0]
    require(
        10 <= status_offset < observed_offset <= confirmation_offset < screenshot_offset < abort_offset < shutdown_offset,
        "cross-log order is not armed < targetstatus >=10s < observegeometry < receipt confirmation < exactly-one F2 < warmup abort < shutdown",
    )
    require(client_shutdown_offset > abort_offset, "client shutdown did not occur after warmup abort")
    return {
        "warmup_ticks": EXPECTED_WARMUP_TICKS,
        "observation_window_seconds": OBSERVATION_WINDOW_SECONDS,
        "armed_line_index": armed,
        "target_status_line_index": status,
        "observegeometry_completion_line_index": observed,
        "receipt_confirmation_line_index": confirmed,
        "screenshot_line_index": screenshot,
        "warmup_abort_line_index": aborted,
        "shutdown_line_index": stopping,
        "armed_to_status_seconds": status_offset,
        "armed_to_observegeometry_seconds": observed_offset,
        "armed_to_receipt_confirmation_seconds": confirmation_offset,
        "armed_to_screenshot_seconds": screenshot_offset,
        "armed_to_abort_seconds": abort_offset,
        "screenshot_file_name": screenshot_name,
        "screenshot_count_during_episode": 1,
        "recording_started": False,
        "episode_aborted_during_warmup": True,
    }


def validate_attestation(attestation: dict[str, Any], first_attestation: dict[str, Any], failure_record: dict[str, Any]) -> None:
    missing = sorted(REQUIRED_ATTESTATION_FIELDS - set(attestation))
    require(not missing, f"attestation fields missing: {missing}")
    require(attestation["schema_version"] == "person-c-c1.5-independent-second-operator-attempt-02-attestation-v0.1", "attestation schema mismatch")
    require(attestation["template"] is False, "attestation remains a template")
    require(attestation["operator_role"] == "second" and attestation["attempt"] == 2, "attestation role/attempt mismatch")
    require(attestation["independent_from_first_operator"] is True, "second operator is not independent from first")
    require(attestation["same_human_as_second_operator_attempt_01"] is True, "attempt 02 is not attested as the same second human")
    operator_id = str(attestation.get("operator_id") or "").strip()
    first_operator_id = str(first_attestation.get("operator_id") or "").strip()
    require(bool(operator_id), "operator identity missing")
    require(operator_id.casefold() != "lollo", "operator_id=lollo is forbidden")
    require(operator_id.casefold() != first_operator_id.casefold(), "second operator identity matches first operator")
    account = str(attestation.get("observed_account_name") or "").strip()
    first_account = str(first_attestation.get("observed_account_name") or "").strip()
    require(account == EXPECTED_ATTEMPT_01_ACCOUNT, "attempt-02 account does not match attempt-01 second account")
    require(account.casefold() != first_account.casefold(), "second authenticated account matches first operator")
    require(attestation["attempt_01_observed_account_name"] == EXPECTED_ATTEMPT_01_ACCOUNT, "attempt-01 account binding mismatch")
    require(attestation["attempt_01_geometry_receipt_sha256"] == ATTEMPT_01_HASHES[ATTEMPT_01_RECEIPT], "attempt-01 receipt binding mismatch")
    require(attestation["attempt_01_failure_record_sha256"] == identity(FAILURE_RECORD)["sha256"], "attempt-01 failure-record binding mismatch")
    require(failure_record["classification"] == EXPECTED_FAILURE_CLASSIFICATION, "attempt-01 failure classification mismatch")
    require(attestation["package_source_commit"] == EXPECTED_PACKAGE_SOURCE_COMMIT, "package source commit mismatch")
    require(re.fullmatch(r"[0-9a-f]{40}", attestation.get("preparation_commit") or "") is not None, "preparation commit is not a full Git hash")
    require(attestation["source_commit"] == EXPECTED_RUNTIME_SOURCE_COMMIT and attestation["runtime_source_commit"] == EXPECTED_RUNTIME_SOURCE_COMMIT, "runtime source commit mismatch")
    require(attestation["mineocclude_jar_sha256"] == EXPECTED_JAR_SHA256, "attested MineOcclude JAR mismatch")
    require(attestation["accepted_geometry_version"] == EXPECTED_GEOMETRY_VERSION and attestation["accepted_geometry_sha256"] == EXPECTED_GEOMETRY_SHA256, "attested geometry mismatch")
    require(attestation["layout_id"] == EXPECTED_LAYOUT, "attested layout mismatch")
    require(attestation["episode_id"] == EXPECTED_EPISODE and attestation["seed"] == EXPECTED_SEED and attestation["warmup_ticks"] == EXPECTED_WARMUP_TICKS, "attested retry identity mismatch")
    for key in (
        "fresh_runtime_session", "targetstatus_passed_after_at_least_ten_seconds",
        "observegeometry_completed_before_receipt_confirmation", "receipt_write_confirmed_before_f2",
        "exactly_one_f2_after_receipt_confirmation", "mineocclude_stop_aborted_during_warmup",
        "recording_never_started", "screenshot_from_same_session", "server_stopped_cleanly",
        "operator_identity_differs_from_first_operator", "authenticated_account_differs_from_first_operator",
    ):
        require(attestation[key] is True, f"timing/identity attestation missing: {key}")
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

    server_properties = SERVER / "server.properties"
    client_options = CLIENT / "options.txt"
    required = [CONFIG, MANIFEST, FAILURE_RECORD, FIRST_SUCCESS, RUNTIME_SCHEDULE, INSTALLED_JAR,
                FIRST_ATTESTATION, FIRST_INGESTED, SERVER_LOG_ARCHIVE, CLIENT_LOG_ARCHIVE,
                args.geometry_receipt, args.screenshot, args.attestation, server_properties, client_options]
    for path in required:
        require(path.is_file(), f"required evidence file absent: {path}")
    require(not args.output.exists(), f"create-only output already exists: {args.output}")
    for path, expected_hash in ATTEMPT_01_HASHES.items():
        require(path.is_file() and identity(path)["sha256"] == expected_hash, f"attempt-01 evidence drift: {path}")
    require(identity(FIRST_ATTESTATION)["sha256"] == EXPECTED_FIRST_ATTESTATION_SHA256, "first-operator attestation drift")
    require(identity(FIRST_INGESTED)["sha256"] == EXPECTED_FIRST_INGESTED_SHA256, "first-operator ingested evidence drift")

    config = load(CONFIG)
    manifest = load(MANIFEST)
    failure_record = load(FAILURE_RECORD)
    first_success = load(FIRST_SUCCESS)
    first_attestation = load(FIRST_ATTESTATION)
    receipt = load(args.geometry_receipt)
    attestation = load(args.attestation)
    require(first_success["c1_5_first_operator_complete"] is True, "first-operator success no longer complete")
    require(failure_record["classification"] == EXPECTED_FAILURE_CLASSIFICATION and failure_record["preservation"]["status"] == "PRESERVED_HASH_BOUND_NOT_CERTIFIED", "attempt-01 failure record mismatch")
    require(config["config_version"] == EXPECTED_GEOMETRY_VERSION and identity(CONFIG)["sha256"] == EXPECTED_GEOMETRY_SHA256, "accepted geometry drift")
    retry = manifest["retry"]
    require(retry["episode_id"] == EXPECTED_EPISODE and retry["seed"] == EXPECTED_SEED and retry["warmup_ticks"] == EXPECTED_WARMUP_TICKS and retry["record_ticks"] == 20, "attempt-02 manifest identity mismatch")
    require(retry["ordered_start_commands"][-2:] == ["mineocclude warmup 12000", "mineocclude start layout_01 11506 202608031506 0.0 0.0 20"], "start sequence does not bind warmup 12000 immediately before start")
    require(identity(INSTALLED_JAR)["sha256"] == EXPECTED_JAR_SHA256, "installed MineOcclude JAR hash mismatch")
    require(identity(RUNTIME_SCHEDULE)["sha256"] == retry["schedule"]["runtime"]["sha256"], "runtime schedule hash mismatch")
    header = json.loads(RUNTIME_SCHEDULE.open(encoding="utf-8-sig").readline())
    require(header["seed"] == EXPECTED_SEED and header["q"] == 0.0 and header["n_draws"] == 20, "attempt-02 schedule header mismatch")

    require(receipt.get("receipt_id") == EXPECTED_RECEIPT, "receipt identity mismatch")
    require(receipt.get("layout_id") == EXPECTED_LAYOUT and receipt.get("episode_id") == EXPECTED_EPISODE, "receipt layout/episode mismatch")
    require(receipt.get("observation_only") is True and receipt.get("scientific_use") == "forbidden", "receipt observation/scientific-use mismatch")
    require(receipt.get("running") is True and receipt.get("capturing") is False and receipt.get("lifecycle_state") == "READY" and receipt.get("warmup_ticks_remaining", 0) > 0, "receipt was not taken during READY warmup")
    target = receipt.get("target", {})
    require(target.get("valid") is True and target.get("required") is True and target.get("tagged_target_count") == 1 and target.get("problems") == [], "target is not valid/required/exactly-one/problem-free")
    require(target.get("actual_xyz") == target.get("expected_xyz"), "target location mismatch")
    layout = next(item for item in config["layouts"] if item["layout_id"] == EXPECTED_LAYOUT)
    receipt_markers = {row["color"]: row for row in receipt["markers"]}
    for expected in layout["markers"]:
        actual = receipt_markers[expected["color"]]
        require(actual["block_pos_xyz"] == expected["block_pos_xyz"] and actual["top_face_centre_world_xyz"] == expected["top_face_centre_world_xyz"] and actual["matches"] is True, f"marker mismatch: {expected['color']}")
    camera = receipt["camera"]["observed_players"][0]
    require(camera["feet_xyz"] == layout["camera"]["feet_xyz"] and camera["yaw_degrees"] == layout["camera"]["yaw_degrees"] and camera["pitch_degrees"] == layout["camera"]["pitch_degrees"], "camera mismatch")

    validate_attestation(attestation, first_attestation, failure_record)
    server_lines = SERVER_LOG_ARCHIVE.read_text(encoding="utf-8", errors="replace").splitlines()
    client_lines = CLIENT_LOG_ARCHIVE.read_text(encoding="utf-8", errors="replace").splitlines()
    chronology = validate_attempt_02_logs(server_lines, client_lines)
    require(any("loaded immutable noise schedule (20 draws)" in line and "episode_11506.jsonl" in line for line in server_lines), "immutable attempt-02 schedule load missing")
    client_log = "\n".join(client_lines)
    require("Connecting to 127.0.0.1, 25565" in client_log and "Stopping!" in client_log, "client connection/exit evidence incomplete")
    account_match = re.search(r"Setting user: ([A-Za-z0-9_]+)", client_log)
    require(account_match is not None and account_match.group(1) == EXPECTED_ATTEMPT_01_ACCOUNT, "same second-operator authenticated account missing")
    require(attestation["observed_account_name"] == account_match.group(1), "attested account does not match same-session client log")
    require("spawn-animals=false" in server_properties.read_text(encoding="utf-8-sig").splitlines(), "spawn-animals=false not retained")

    png = args.screenshot.read_bytes()
    require(png[:8] == b"\x89PNG\r\n\x1a\n" and png[12:16] == b"IHDR", "screenshot is not PNG")
    width, height = struct.unpack(">II", png[16:24])
    require((width, height) == (640, 360), "screenshot is not canonical 640x360")
    raw_screenshot = CLIENT / "screenshots" / chronology["screenshot_file_name"]
    require(raw_screenshot.is_file(), f"same-session raw screenshot absent: {raw_screenshot}")
    require(identity(raw_screenshot)["sha256"] == identity(args.screenshot)["sha256"], "canonical screenshot differs from same-session F2 screenshot")

    result = {
        "schema_version": "person-c-c1.5-ingested-independent-second-operator-attempt-02-v0.1",
        "status": "PASS",
        "operator_role": "second",
        "attempt": 2,
        "same_human_as_second_operator_attempt_01": True,
        "independent_from_first_operator": True,
        "accepted_geometry_version": EXPECTED_GEOMETRY_VERSION,
        "layout_id": EXPECTED_LAYOUT,
        "episode_id": EXPECTED_EPISODE,
        "seed": EXPECTED_SEED,
        "warmup_ticks": EXPECTED_WARMUP_TICKS,
        "chronology": chronology,
        "attempt_01_failure_classification": EXPECTED_FAILURE_CLASSIFICATION,
        "c1_5_first_operator_complete": True,
        "c1_5_second_operator_complete": True,
        "c1_5_complete": True,
        "files": {
            "geometry_receipt": identity(args.geometry_receipt),
            "screenshot": {**identity(args.screenshot), "width": width, "height": height},
            "raw_same_session_screenshot": identity(raw_screenshot),
            "attestation": identity(args.attestation),
            "server_log_archive": identity(SERVER_LOG_ARCHIVE),
            "client_log_archive": identity(CLIENT_LOG_ARCHIVE),
            "schedule": identity(RUNTIME_SCHEDULE),
            "installed_jar": identity(INSTALLED_JAR),
            "accepted_geometry": identity(CONFIG),
            "attempt_01_failure_record": identity(FAILURE_RECORD),
            "first_operator_success_receipt": identity(FIRST_SUCCESS),
        },
    }
    if not args.validate_only:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("xb") as handle:
            handle.write((json.dumps(result, indent=2) + "\n").encode("utf-8"))
    print(json.dumps({"status": "PASS", "validate_only": args.validate_only, "episode_id": EXPECTED_EPISODE, "c1_5_complete": True, "output": None if args.validate_only else str(args.output.resolve())}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
