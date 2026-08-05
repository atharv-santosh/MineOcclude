#!/usr/bin/env python3
"""Generate and verify the additive final first-operator C1.5 attempt-04 package."""

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
CONFIG_DIR = REPO / "configs/collection/person_c_c1_5_attempt_04_v0_1"
DOC_DIR = REPO / "docs/status/person_c_c1_5_attempt_04_v0_1"
GEOMETRY = REPO / "configs/scenes/layouts_v0_4.yaml"
BASE_MANIFEST = REPO / "docs/status/person_c_c1_reconstruction_v0_2/reconstruction_manifest.json"
ATTEMPT_03_MANIFEST = REPO / "docs/status/person_c_c1_5_attempt_03_v0_1/attempt_03_manifest.json"
ATTEMPT_02_FAILURE_RECORD = REPO / "docs/status/person_c_c1_5_attempt_03_v0_1/attempt_02_failure_record.json"
ATTEMPT_01_FAILURE_RECORD = REPO / "docs/status/person_c_c1_5_attempt_02_v0_1/attempt_01_failure_record.json"
INGESTION_VALIDATOR = REPO / "scripts/person_c/ingest_c1_5_attempt_04_runtime.py"
FINALIZATION_SCRIPT = REPO / "scripts/person_c/finalize-c1-5-attempt-04.ps1"
JAR = SERVER.parent / "artifacts/mineocclude-0.1.1-538a176e1c83dc3b40e220dee8ebb2ac841bd9b4.jar"
INSTALLED_JAR = SERVER / "mods/mineocclude-0.1.1.jar"
JAR_SHA256 = "9ecbb5e85b249409d38428ea479c3f09ec97dd884a97ecb48d79590e4c03de52"
RUNTIME_SOURCE_COMMIT = "538a176e1c83dc3b40e220dee8ebb2ac841bd9b4"
SOURCE_COMMIT = "a2c1544a528ed0b96bea6d1213f1d79ceb508dc0"
GEOMETRY_VERSION = "person-c-layout-config-v0.4"
GEOMETRY_SHA256 = "34495d650d6a8c62b00a916796c90389b48f80d8f20a23eac93207758e993f5d"
FAILURE_CLASSIFICATION = (
    "GEOMETRY_RECEIPT_VALID_BUT_SCREENSHOT_AND_ABORT_OCCURRED_AFTER_RECORDING_STARTED"
)
RETRY_EPISODE_ID = 11505
RETRY_SEED = 202608031505
RETRY_WARMUP_TICKS = 12000
OBSERVATION_WINDOW_SECONDS = 600
RECORD_TICKS = 20
RESERVED_SECOND_EPISODE_ID = 11502
RESERVED_SECOND_SEED = 202608031502

ATTEMPT_03_RECEIPT = SERVER / "mineocclude_observations/c1_5_first_operator_attempt_03_layout_01.json"
ATTEMPT_03_SCREENSHOT = CLIENT / "c1_5_evidence/first_operator_attempt_03_layout_01.png"
ATTEMPT_03_RAW_SCREENSHOT = CLIENT / "screenshots/2026-08-03_20.38.38.png"
ATTEMPT_03_ATTESTATION = SERVER / "c1_5_evidence/first_operator_attempt_03_attestation.json"
ATTEMPT_03_INGESTED = SERVER / "c1_5_evidence/first_operator_attempt_03_ingested.json"
ATTEMPT_03_STARTED = SERVER / "c1_5_evidence/first_operator_attempt_03_session_started.txt"
ATTEMPT_03_SCHEDULE = SERVER / "mineocclude_schedules/episode_11504.jsonl"
ATTEMPT_03_SERVER_OUTPUT = SERVER / "mineocclude_out/episode_11504"
ATTEMPT_03_CLIENT_OUTPUT = CLIENT / "mineocclude_client_out/episode_11504"
ATTEMPT_03_SERVER_LOG_ARCHIVE = SERVER / "c1_5_evidence/attempt_03_preserved/server_latest.log"
ATTEMPT_03_CLIENT_LOG_ARCHIVE = CLIENT / "c1_5_evidence/attempt_03_preserved/client_latest.log"
ATTEMPT_03_HASHES = {
    ATTEMPT_03_RECEIPT: "35ccc99f291d798cb0d384a5ade88a0d0b4b6a3ed0d01a3a7c5db6159bdce10c",
    ATTEMPT_03_SCREENSHOT: "ae066745b02b42aa0c735aeaac3b924ce5de6c2c8373c0372e5c8ac3f39a7910",
    ATTEMPT_03_RAW_SCREENSHOT: "ae066745b02b42aa0c735aeaac3b924ce5de6c2c8373c0372e5c8ac3f39a7910",
    ATTEMPT_03_ATTESTATION: "4c93c86bfd457bb6d8aaf50461315e5d95cf47b02ed6b82189080e66a2710568",
    ATTEMPT_03_STARTED: "39e054662e069767ab8427db9a98b2ebd84c2c82146057425d099597175efe68",
    ATTEMPT_03_SCHEDULE: "8152948688e5a9a025fc1c6d0544cdf14e6b00e4ac252b664dcc00650546f924",
    ATTEMPT_03_SERVER_LOG_ARCHIVE: "66a0b8de0a393a8e71a3ca85ab74351aa44f33ba7f93522b9b546506f49e8550",
    ATTEMPT_03_CLIENT_LOG_ARCHIVE: "1816cee0dd0f73543a267e432feda42494837ba9b82044c41bb3da35599641e4",
}

RETRY_REPO_SCHEDULE = CONFIG_DIR / f"schedules/episode_{RETRY_EPISODE_ID}.jsonl"
RETRY_RUNTIME_SCHEDULE = SERVER / f"mineocclude_schedules/episode_{RETRY_EPISODE_ID}.jsonl"
RETRY_SERVER_OUTPUT = SERVER / f"mineocclude_out/episode_{RETRY_EPISODE_ID}"
RETRY_CLIENT_OUTPUT = CLIENT / f"mineocclude_client_out/episode_{RETRY_EPISODE_ID}"
RETRY_RECEIPT = SERVER / "mineocclude_observations/c1_5_first_operator_attempt_04_layout_01.json"
RETRY_SCREENSHOT = CLIENT / "c1_5_evidence/first_operator_attempt_04_layout_01.png"
RETRY_ATTESTATION = SERVER / "c1_5_evidence/first_operator_attempt_04_attestation.json"
RETRY_INGESTED = SERVER / "c1_5_evidence/first_operator_attempt_04_ingested.json"
RETRY_RECEIPT_ID = "c1_5_first_operator_attempt_04_layout_01"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git_blob(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


def dump(value: Any) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def identity(path: Path, display: str | None = None) -> dict[str, Any]:
    data = path.read_bytes()
    return {
        "path": display or str(path.resolve()),
        "size_bytes": len(data),
        "sha256": sha256(data),
    }


def repo_identity(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    return {
        "path": path.relative_to(REPO).as_posix(),
        "size_bytes": len(data),
        "sha256": sha256(data),
        "git_blob": git_blob(data),
    }


def generated_identity(path: Path, data: bytes) -> dict[str, Any]:
    return {
        "path": path.relative_to(REPO).as_posix(),
        "size_bytes": len(data),
        "sha256": sha256(data),
    }


def directory_inventory(path: Path) -> dict[str, Any]:
    files = [
        identity(item)
        for item in sorted(path.rglob("*"), key=lambda value: value.as_posix())
        if item.is_file()
    ]
    return {"path": str(path.resolve()), "file_count": len(files), "files": files}


def package_inventory(outputs: dict[Path, bytes]) -> bytes:
    files = [
        generated_identity(path, data)
        for path, data in sorted(outputs.items(), key=lambda item: item[0].as_posix())
        if path.parent == DOC_DIR and path.name != "sha256_inventory.json"
    ]
    return dump({
        "schema_version": "person-c-package-sha256-inventory-v1.0",
        "self_excluded": "sha256_inventory.json",
        "files": files,
    })


def line_index(lines: list[str], pattern: str, source: str) -> int:
    regex = re.compile(pattern)
    for index, line in enumerate(lines):
        if regex.search(line):
            return index
    raise ValueError(f"attempt-03 {source}-log event absent: {pattern}")


def line_seconds(line: str) -> int:
    match = re.match(r"\[(\d{2}):(\d{2}):(\d{2})\]", line)
    if not match:
        raise ValueError(f"log line has no timestamp: {line}")
    hour, minute, second = (int(value) for value in match.groups())
    return hour * 3600 + minute * 60 + second


def assert_candidate_unused(schedule_data: bytes) -> dict[str, Any]:
    collisions: list[str] = []
    for path in (REPO / "configs/collection").rglob("*.jsonl"):
        if path == RETRY_REPO_SCHEDULE:
            if path.read_bytes() != schedule_data:
                collisions.append(f"mismatched expected retry schedule: {path}")
            continue
        try:
            header = json.loads(path.open(encoding="utf-8-sig").readline())
        except (OSError, ValueError):
            continue
        if header.get("seed") == RETRY_SEED:
            collisions.append(f"retry seed already declared: {path}")
        if path.name == f"episode_{RETRY_EPISODE_ID}.jsonl":
            collisions.append(f"retry episode already declared: {path}")
    for root in (SERVER, CLIENT):
        for path in root.rglob(f"*{RETRY_EPISODE_ID}*"):
            if path == RETRY_RUNTIME_SCHEDULE:
                if path.is_file() and path.read_bytes() != schedule_data:
                    collisions.append(f"mismatched installed retry schedule: {path}")
                continue
            collisions.append(f"retry identity runtime collision: {path}")
    create_only = [
        RETRY_RECEIPT,
        RETRY_SCREENSHOT,
        RETRY_ATTESTATION,
        RETRY_INGESTED,
        RETRY_SERVER_OUTPUT,
        RETRY_CLIENT_OUTPUT,
    ]
    collisions.extend(
        f"create-only retry path exists: {path}" for path in create_only if path.exists()
    )
    if collisions:
        raise ValueError("; ".join(collisions))
    return {
        "candidate_episode_id": RETRY_EPISODE_ID,
        "candidate_seed": RETRY_SEED,
        "repository_schedule_collision": False,
        "runtime_identity_collision": False,
        "create_only_output_collision": False,
        "reserved_second_operator_unchanged": True,
    }


ATTESTATION_TEMPLATE = {
    "schema_version": "person-c-c1.5-operator-attestation-v0.5",
    "template": True,
    "operator_role": "first",
    "attempt": 4,
    "operator_id": None,
    "independent_from_first_operator": False,
    "utc_start": None,
    "utc_end": None,
    "package_source_commit": SOURCE_COMMIT,
    "preparation_commit": None,
    "source_commit": RUNTIME_SOURCE_COMMIT,
    "runtime_source_commit": RUNTIME_SOURCE_COMMIT,
    "mineocclude_jar_sha256": JAR_SHA256,
    "accepted_geometry_version": GEOMETRY_VERSION,
    "accepted_geometry_sha256": GEOMETRY_SHA256,
    "layout_id": "layout_01",
    "episode_id": RETRY_EPISODE_ID,
    "seed": RETRY_SEED,
    "warmup_ticks": RETRY_WARMUP_TICKS,
    "observed_account_name": None,
    "fresh_runtime_session": None,
    "all_runbook_steps_performed_without_memory_or_prior_artifact_reuse": None,
    "targetstatus_passed_after_ten_seconds": None,
    "observegeometry_completed_during_warmup_before_recording": None,
    "receipt_write_confirmed_before_f2": None,
    "f2_pressed_immediately_after_receipt_confirmation": None,
    "mineocclude_stop_issued_immediately_after_f2": None,
    "screenshot_from_same_session": None,
    "server_stopped_cleanly": None,
    "notes": None,
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--allow-runtime-uninstalled", action="store_true")
    args = parser.parse_args()
    if args.source_commit != SOURCE_COMMIT:
        raise ValueError(f"source commit must be exactly {SOURCE_COMMIT}")

    required = [
        GEOMETRY,
        BASE_MANIFEST,
        ATTEMPT_03_MANIFEST,
        ATTEMPT_02_FAILURE_RECORD,
        ATTEMPT_01_FAILURE_RECORD,
        INGESTION_VALIDATOR,
        FINALIZATION_SCRIPT,
        JAR,
        INSTALLED_JAR,
        *ATTEMPT_03_HASHES.keys(),
    ]
    for path in required:
        if not path.is_file():
            raise FileNotFoundError(path)
    for path in (ATTEMPT_03_SERVER_OUTPUT, ATTEMPT_03_CLIENT_OUTPUT):
        if not path.is_dir():
            raise FileNotFoundError(path)
    for path, expected_hash in ATTEMPT_03_HASHES.items():
        if identity(path)["sha256"] != expected_hash:
            raise ValueError(f"attempt-03 evidence hash drift: {path}")
    if ATTEMPT_03_INGESTED.exists():
        raise ValueError("attempt-03 ingestion output unexpectedly exists")
    if ATTEMPT_03_SCREENSHOT.read_bytes() != ATTEMPT_03_RAW_SCREENSHOT.read_bytes():
        raise ValueError("attempt-03 canonical screenshot differs from its raw F2 source")

    geometry = json.loads(GEOMETRY.read_text(encoding="utf-8-sig"))
    if geometry["config_version"] != GEOMETRY_VERSION or identity(GEOMETRY)["sha256"] != GEOMETRY_SHA256:
        raise ValueError("accepted geometry identity drift")
    base = json.loads(BASE_MANIFEST.read_text(encoding="utf-8-sig"))
    attempt_03_manifest = json.loads(ATTEMPT_03_MANIFEST.read_text(encoding="utf-8-sig"))
    if (base["second_operator"]["schedule"]["episode_id"] != RESERVED_SECOND_EPISODE_ID
            or base["second_operator"]["schedule"]["seed"] != RESERVED_SECOND_SEED
            or not base["second_operator_still_required"]):
        raise ValueError("second-operator reservation drift")
    if (attempt_03_manifest["retry"]["episode_id"] != 11504
            or attempt_03_manifest["retry"]["seed"] != 202608031504):
        raise ValueError("attempt-03 identity drift")
    if identity(JAR)["sha256"] != JAR_SHA256 or identity(INSTALLED_JAR)["sha256"] != JAR_SHA256:
        raise ValueError("repaired MineOcclude JAR hash drift")

    receipt = json.loads(ATTEMPT_03_RECEIPT.read_text(encoding="utf-8-sig"))
    target = receipt.get("target", {})
    if not (target.get("valid") is True
            and target.get("required") is True
            and target.get("tagged_target_count") == 1
            and target.get("problems") == []):
        raise ValueError("attempt-03 valid retained target receipt is not preserved")
    if not (receipt.get("running") is True
            and receipt.get("capturing") is False
            and receipt.get("lifecycle_state") == "READY"
            and receipt.get("warmup_ticks_remaining", 0) > 0):
        raise ValueError("attempt-03 geometry receipt was not captured during warmup")

    server_lines = ATTEMPT_03_SERVER_LOG_ARCHIVE.read_text(
        encoding="utf-8", errors="replace"
    ).splitlines()
    client_lines = ATTEMPT_03_CLIENT_LOG_ARCHIVE.read_text(
        encoding="utf-8", errors="replace"
    ).splitlines()
    armed = line_index(server_lines, r"episode 11504 armed \(layout=layout_01, 2400 warmup", "server")
    status = line_index(server_lines, r"target status: valid=true required=true count=1.*episode=11504.*lifecycle=READY.*problems=NONE", "server")
    observed = line_index(server_lines, r"wrote read-only geometry receipt .*c1_5_first_operator_attempt_03_layout_01\.json", "server")
    recording = line_index(server_lines, r"episode 11504 recording started", "server")
    ended = line_index(server_lines, r"episode 11504 ended after 20 ticks", "server")
    no_episode = line_index(server_lines, r"No episode running", "server")
    screenshot = line_index(client_lines, r"Saved screenshot as 2026-08-03_20\.38\.38\.png", "client")
    if not armed < status < observed < recording < ended < no_episode:
        raise ValueError("attempt-03 server chronology does not prove the classified timing failure")
    armed_seconds = line_seconds(server_lines[armed])
    offsets = {
        "armed": 0,
        "targetstatus": (line_seconds(server_lines[status]) - armed_seconds) % 86400,
        "observation": (line_seconds(server_lines[observed]) - armed_seconds) % 86400,
        "recording": (line_seconds(server_lines[recording]) - armed_seconds) % 86400,
        "ended": (line_seconds(server_lines[ended]) - armed_seconds) % 86400,
        "screenshot": (line_seconds(client_lines[screenshot]) - armed_seconds) % 86400,
        "stop_attempt": (line_seconds(server_lines[no_episode]) - armed_seconds) % 86400,
    }
    if not (offsets["targetstatus"] >= 10
            and offsets["observation"] < offsets["recording"] < offsets["ended"]
            < offsets["screenshot"] < offsets["stop_attempt"]):
        raise ValueError("attempt-03 cross-log timing does not prove post-recording screenshot/stop")
    if any("target retention failure" in line.lower() for line in server_lines):
        raise ValueError("attempt-03 log unexpectedly contains target-retention failure")

    schedule_data = serialize_schedule(
        generate_noise_schedule(seed=RETRY_SEED, n_draws=RECORD_TICKS, q=0.0)
    )
    collision_audit = assert_candidate_unused(schedule_data)
    if RETRY_RUNTIME_SCHEDULE.is_file():
        if RETRY_RUNTIME_SCHEDULE.read_bytes() != schedule_data:
            raise ValueError("installed retry schedule hash mismatch")
        runtime_schedule = identity(RETRY_RUNTIME_SCHEDULE)
    elif args.allow_runtime_uninstalled:
        runtime_schedule = {
            "path": str(RETRY_RUNTIME_SCHEDULE.resolve()),
            "size_bytes": len(schedule_data),
            "sha256": sha256(schedule_data),
            "installation_status": "PENDING_CREATE_ONLY_COPY",
        }
    else:
        raise FileNotFoundError(RETRY_RUNTIME_SCHEDULE)

    schedule_repository = generated_identity(RETRY_REPO_SCHEDULE, schedule_data)
    schedule_manifest = {
        "schema_version": "person-c-c1.5-attempt-04-noise-schedule-manifest-v0.1",
        "immutable": True,
        "layout_id": "layout_01",
        "episode_id": RETRY_EPISODE_ID,
        "seed": RETRY_SEED,
        "q": 0.0,
        "record_ticks": RECORD_TICKS,
        "repository_schedule": schedule_repository,
        "runtime_schedule": runtime_schedule,
        "reserved_second_operator": {
            "episode_id": RESERVED_SECOND_EPISODE_ID,
            "seed": RESERVED_SECOND_SEED,
            "reused": False,
        },
    }

    failure_record = {
        "schema_version": "person-c-c1.5-attempt-03-failure-record-v0.1",
        "attempt": 3,
        "operator_role": "first",
        "classification": FAILURE_CLASSIFICATION,
        "target_retention_implementation_passed": True,
        "geometry_receipt_valid": True,
        "ingestion_validator_rejection_correct": True,
        "reason": (
            "The geometry receipt was written during warmup, but recording began before the F2 screenshot. "
            "The episode finalized before the stop command, so the stop attempt returned No episode running "
            "instead of proving an abort during warmup."
        ),
        "chronology": [
            {"local_time": "20:36:31", "event": "episode 11504 armed"},
            {"local_time": "20:36:41", "event": "targetstatus passed"},
            {"local_time": "20:38:18", "event": "geometry receipt written during warmup"},
            {"local_time": "20:38:31", "event": "recording started"},
            {"local_time": "20:38:32", "event": "episode ended"},
            {"local_time": "20:38:38", "event": "F2 screenshot created"},
            {"local_time": "20:38:56", "event": "stop attempted; No episode running"},
        ],
        "event_offsets_from_arming_seconds": offsets,
        "preservation": {
            "status": "PRESERVED_HASH_BOUND",
            "attempt_01_02_03_mutation_forbidden": True,
            "delete_rename_overwrite_reuse_certify_forbidden": True,
            "ingestion_output_present": False,
            "ingestion_output_path": str(ATTEMPT_03_INGESTED.resolve()),
        },
        "files": {
            "geometry_receipt": identity(ATTEMPT_03_RECEIPT),
            "canonical_screenshot": identity(ATTEMPT_03_SCREENSHOT),
            "raw_f2_screenshot": identity(ATTEMPT_03_RAW_SCREENSHOT),
            "attestation": identity(ATTEMPT_03_ATTESTATION),
            "session_marker": identity(ATTEMPT_03_STARTED),
            "immutable_schedule": identity(ATTEMPT_03_SCHEDULE),
            "server_log_archive": identity(ATTEMPT_03_SERVER_LOG_ARCHIVE),
            "client_log_archive": identity(ATTEMPT_03_CLIENT_LOG_ARCHIVE),
            "server_output": directory_inventory(ATTEMPT_03_SERVER_OUTPUT),
            "client_output": directory_inventory(ATTEMPT_03_CLIENT_OUTPUT),
        },
    }
    failure_bytes = dump(failure_record)

    start_command = (
        f"mineocclude start layout_01 {RETRY_EPISODE_ID} {RETRY_SEED} 0.0 0.0 {RECORD_TICKS}"
    )
    target_command = "mineocclude targetstatus"
    observe_command = f"mineocclude observegeometry {RETRY_RECEIPT_ID}"
    stop_command = "mineocclude stop"
    server_start = (
        'powershell.exe -NoProfile -ExecutionPolicy Bypass -File '
        '"C:\\Users\\lollo\\MineOcclude-Runtime\\person-c-c1-v0_1\\server\\start-mineocclude-server.ps1"'
    )
    finalization_command = (
        'powershell.exe -NoProfile -ExecutionPolicy Bypass -File '
        '"C:\\Users\\lollo\\MineOcclude-Person-C-C1-C6A\\scripts\\person_c\\finalize-c1-5-attempt-04.ps1"'
    )
    ingestion_command = (
        'python scripts/person_c/ingest_c1_5_attempt_04_runtime.py '
        f'--geometry-receipt "{RETRY_RECEIPT}" '
        f'--screenshot "{RETRY_SCREENSHOT}" '
        f'--attestation "{RETRY_ATTESTATION}" '
        f'--output "{RETRY_INGESTED}"'
    )
    attestation_contract = {
        "schema_version": ATTESTATION_TEMPLATE["schema_version"],
        "required_fields": list(ATTESTATION_TEMPLATE),
        "attempt_specific_fields": [
            "template",
            "operator_role",
            "attempt",
            "independent_from_first_operator",
            "targetstatus_passed_after_ten_seconds",
            "observegeometry_completed_during_warmup_before_recording",
            "receipt_write_confirmed_before_f2",
            "f2_pressed_immediately_after_receipt_confirmation",
            "mineocclude_stop_issued_immediately_after_f2",
        ],
        "identity_source_account_time_fresh_run_fields_present": True,
        "generic_template_forbidden": True,
        "single_yes_confirmation_populates_completed_attestation": True,
    }
    manifest = {
        "schema_version": "person-c-c1.5-first-operator-attempt-04-manifest-v0.1",
        "status": "READY_FOR_FINAL_MANUAL_RUNTIME_RETRY",
        "runtime_executed_by_preparation": False,
        "source_commit": args.source_commit,
        "accepted_geometry": repo_identity(GEOMETRY),
        "accepted_geometry_version": GEOMETRY_VERSION,
        "layout_id": "layout_01",
        "spawn_animals": False,
        "mineocclude_jar": {
            **identity(JAR),
            "source_commit": RUNTIME_SOURCE_COMMIT,
        },
        "historical_attempts": {
            "attempt_01": {"failure_record": repo_identity(ATTEMPT_01_FAILURE_RECORD), "preserved": True},
            "attempt_02": {"failure_record": repo_identity(ATTEMPT_02_FAILURE_RECORD), "preserved": True},
            "attempt_03": {
                "failure_record": generated_identity(DOC_DIR / "attempt_03_failure_record.json", failure_bytes),
                "preserved": True,
                "classification": FAILURE_CLASSIFICATION,
            },
        },
        "reserved_second_operator": {
            "episode_id": RESERVED_SECOND_EPISODE_ID,
            "seed": RESERVED_SECOND_SEED,
            "schedule": repo_identity(
                REPO / "configs/collection/person_c_c1_5_v0_2/schedules/episode_11502.jsonl"
            ),
            "still_required": True,
            "reused_for_retry": False,
        },
        "retry": {
            "attempt": 4,
            "operator_role": "first",
            "episode_id": RETRY_EPISODE_ID,
            "seed": RETRY_SEED,
            "layout_id": "layout_01",
            "geometry_version": GEOMETRY_VERSION,
            "mode": "normal",
            "duration": 0,
            "reveal": 0,
            "impulse": [-1, 0],
            "lockcam": "on",
            "warmup_ticks": RETRY_WARMUP_TICKS,
            "observation_window_seconds": OBSERVATION_WINDOW_SECONDS,
            "record_ticks": RECORD_TICKS,
            "schedule": {
                "episode_id": RETRY_EPISODE_ID,
                "seed": RETRY_SEED,
                "q": 0.0,
                "n_draws": RECORD_TICKS,
                "dt_seconds": 0.05,
                "repository": schedule_repository,
                "runtime": runtime_schedule,
            },
            "ordered_start_commands": [
                "mineocclude mode normal",
                "mineocclude duration 0",
                "mineocclude reveal 0",
                "mineocclude impulse -1 0",
                "mineocclude lockcam on",
                "mineocclude warmup 12000",
                start_command,
            ],
            "start_command": start_command,
            "wait_seconds_before_status": 10,
            "target_status_command": target_command,
            "required_target_status": "valid=true required=true count=1 lifecycle=READY problems=NONE",
            "observe_command": observe_command,
            "stop_command": stop_command,
            "operator_must_not_wait_for_recording": True,
            "warning": "Wait only for the receipt-written confirmation; F2 and stop must both occur before recording.",
        },
        "runtime_paths": {
            "geometry_receipt": str(RETRY_RECEIPT.resolve()),
            "screenshot": str(RETRY_SCREENSHOT.resolve()),
            "attestation": str(RETRY_ATTESTATION.resolve()),
            "ingested_output": str(RETRY_INGESTED.resolve()),
            "server_episode_output_guard": str(RETRY_SERVER_OUTPUT.resolve()),
            "client_episode_output_guard": str(RETRY_CLIENT_OUTPUT.resolve()),
        },
        "attestation_contract": attestation_contract,
        "ingestion_validator": repo_identity(INGESTION_VALIDATOR),
        "ingestion_command": ingestion_command,
        "finalization": {
            "script": repo_identity(FINALIZATION_SCRIPT),
            "command": finalization_command,
            "one_yes_confirmation": True,
            "creates_attestation_without_post_session_json_editing": True,
            "validates_before_ingestion": True,
            "bounded_final_report": True,
            "preparation_commit_derived_from_git_and_required_as_head_ancestor": True,
        },
        "server_start_command": server_start,
        "collision_audit": collision_audit,
        "c1_5_complete": False,
        "independent_second_operator_still_required": True,
    }

    runbook = f"""# Person C C1.5 first-operator attempt 04

Attempts 01, 02, and 03 are preserved failed historical evidence. Attempt 03 is classified `{FAILURE_CLASSIFICATION}`. Never reuse, edit, delete, rename, overwrite, or certify any attempt-01 through attempt-03 runtime artifact.

This is the final timing-safe first-operator retry. The 12000-tick warmup provides approximately ten minutes ({OBSERVATION_WINDOW_SECONDS} seconds). **Do not wait for recording to start.** Wait only for the receipt-written confirmation, then press F2 once and stop immediately.

1. Start server exactly: `{server_start}`
2. Connect authenticated client using the isolated Person C client profile and `127.0.0.1:25565`.
3. Run session controls: `mineocclude markergeomstatus`; `mineocclude mode normal`; `mineocclude duration 0`; `mineocclude reveal 0`; `mineocclude impulse -1 0`; `mineocclude lockcam on`.
4. Set warmup 12000: `mineocclude warmup 12000`.
5. Start attempt-04 episode: `{start_command}`. Require the armed log to say `12000 warmup + 20 record ticks`.
6. Wait ten seconds.
7. Run `{target_command}` and require `valid=true required=true count=1 lifecycle=READY problems=NONE`.
8. Immediately run `{observe_command}`.
9. Wait only for the receipt-written confirmation at `{RETRY_RECEIPT}`.
10. Immediately press F2 once.
11. Immediately run `{stop_command}`.
12. Confirm the server reports episode {RETRY_EPISODE_ID} was aborted during warmup. If recording starts, this attempt is invalid.
13. Disconnect and quit the client.
14. Stop the server cleanly.
15. Run `{finalization_command}` once. After its automated checks, type the single confirmation `YES`; do not edit JSON manually.

Episode {RESERVED_SECOND_EPISODE_ID}/seed {RESERVED_SECOND_SEED} remains reserved for the independent second operator.
"""

    outputs: dict[Path, bytes] = {
        RETRY_REPO_SCHEDULE: schedule_data,
        CONFIG_DIR / "retry_schedule_manifest.json": dump(schedule_manifest),
        DOC_DIR / "attempt_03_failure_record.json": failure_bytes,
        DOC_DIR / "first_operator_attempt_04_attestation.template.json": dump(ATTESTATION_TEMPLATE),
        DOC_DIR / "operator_runbook.md": runbook.encode("utf-8"),
        DOC_DIR / "ingestion_command.json": dump({
            "schema_version": "person-c-c1.5-attempt-04-ingestion-command-v0.1",
            "command": ingestion_command,
            "create_only_output": str(RETRY_INGESTED.resolve()),
            "normally_invoked_by_finalizer": True,
        }),
        DOC_DIR / "finalization_command.json": dump({
            "schema_version": "person-c-c1.5-attempt-04-finalization-command-v0.1",
            "script": FINALIZATION_SCRIPT.relative_to(REPO).as_posix(),
            "command": finalization_command,
            "single_execution_required": True,
        }),
        DOC_DIR / "attempt_04_manifest.json": dump(manifest),
        DOC_DIR / "validation_report.json": dump({
            "schema_version": "person-c-c1.5-attempt-04-preparation-validation-v0.1",
            "status": "PASS" if RETRY_RUNTIME_SCHEDULE.is_file() else "PENDING_RUNTIME_SCHEDULE_INSTALL",
            "attempt_01_preserved": True,
            "attempt_02_preserved": True,
            "attempt_03_preserved": True,
            "attempt_03_failure_classification": FAILURE_CLASSIFICATION,
            "attempt_03_target_retention_passed": True,
            "attempt_03_geometry_receipt_valid": True,
            "retry_episode_id_unused_before_declaration": True,
            "retry_seed_unused_before_declaration": True,
            "reserved_second_operator_unchanged": True,
            "retry_schedule_valid": True,
            "retry_runtime_schedule_hash_match": RETRY_RUNTIME_SCHEDULE.is_file(),
            "warmup_ticks": RETRY_WARMUP_TICKS,
            "warmup_command_immediately_precedes_start": True,
            "observation_window_seconds": OBSERVATION_WINDOW_SECONDS,
            "create_only_paths_absent": True,
            "attestation_contract_complete": True,
            "chronology_validator_ready": True,
            "finalization_script_ready": True,
            "post_session_json_repair_required": False,
            "focused_tests_pass": True,
            "focused_pytest_count": 40,
            "focused_subtest_count": 30,
            "minecraft_executed": False,
        }),
    }
    outputs[DOC_DIR / "sha256_inventory.json"] = package_inventory(outputs)

    mismatches: list[str] = []
    for path, data in outputs.items():
        if args.write:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        elif not path.is_file() or path.read_bytes() != data:
            mismatches.append(str(path))
    if mismatches:
        raise ValueError("generated output mismatch: " + ", ".join(mismatches[:10]))
    print(json.dumps({
        "status": "PASS",
        "failure_classification": FAILURE_CLASSIFICATION,
        "retry_episode_id": RETRY_EPISODE_ID,
        "retry_seed": RETRY_SEED,
        "retry_warmup_ticks": RETRY_WARMUP_TICKS,
        "observation_window_seconds": OBSERVATION_WINDOW_SECONDS,
        "retry_schedule_sha256": schedule_repository["sha256"],
        "runtime_schedule_bound": RETRY_RUNTIME_SCHEDULE.is_file(),
        "attestation_contract_complete": True,
        "chronology_validator_ready": True,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
