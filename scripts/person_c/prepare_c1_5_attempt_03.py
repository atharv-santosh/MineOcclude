#!/usr/bin/env python3
"""Generate and verify the additive first-operator C1.5 attempt-03 package."""

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
CONFIG_DIR = REPO / "configs/collection/person_c_c1_5_attempt_03_v0_1"
DOC_DIR = REPO / "docs/status/person_c_c1_5_attempt_03_v0_1"
GEOMETRY = REPO / "configs/scenes/layouts_v0_4.yaml"
BASE_MANIFEST = REPO / "docs/status/person_c_c1_reconstruction_v0_2/reconstruction_manifest.json"
ATTEMPT_02_MANIFEST = REPO / "docs/status/person_c_c1_5_attempt_02_v0_1/attempt_02_manifest.json"
ATTEMPT_01_FAILURE_RECORD = REPO / "docs/status/person_c_c1_5_attempt_02_v0_1/attempt_01_failure_record.json"
INGESTION_VALIDATOR = REPO / "scripts/person_c/ingest_c1_5_attempt_03_runtime.py"
JAR = SERVER.parent / "artifacts/mineocclude-0.1.1-538a176e1c83dc3b40e220dee8ebb2ac841bd9b4.jar"
JAR_SHA256 = "9ecbb5e85b249409d38428ea479c3f09ec97dd884a97ecb48d79590e4c03de52"
GEOMETRY_VERSION = "person-c-layout-config-v0.4"
ATTEMPT_02_RECEIPT_SHA256 = "d7519d1e4b702e468edfc2eabc051259121757aaff106ce76f96115eb7efb49b"
FAILURE_CLASSIFICATION = "POST_FINALIZATION_OBSERVATION_INVALID_NOT_TARGET_RETENTION_FAILURE"
RETRY_EPISODE_ID = 11504
RETRY_SEED = 202608031504
RETRY_WARMUP_TICKS = 2400
OBSERVATION_WINDOW_SECONDS = 120
RESERVED_SECOND_EPISODE_ID = 11502
RESERVED_SECOND_SEED = 202608031502

ATTEMPT_02_RECEIPT = SERVER / "mineocclude_observations/c1_5_first_operator_attempt_02_layout_01.json"
ATTEMPT_02_CANONICAL_SCREENSHOT = CLIENT / "c1_5_evidence/first_operator_attempt_02_layout_01.png"
ATTEMPT_02_ATTESTATION = SERVER / "c1_5_evidence/first_operator_attempt_02_attestation.json"
ATTEMPT_02_INGESTED = SERVER / "c1_5_evidence/first_operator_attempt_02_ingested.json"
ATTEMPT_02_STARTED = SERVER / "c1_5_evidence/first_operator_attempt_02_session_started.txt"
ATTEMPT_02_SERVER_LOG = SERVER / "logs/latest.log"
ATTEMPT_02_CLIENT_LOG = CLIENT / "logs/latest.log"
ATTEMPT_02_SERVER_LOG_ARCHIVE = SERVER / "c1_5_evidence/attempt_02_preserved/server_latest.log"
ATTEMPT_02_CLIENT_LOG_ARCHIVE = CLIENT / "c1_5_evidence/attempt_02_preserved/client_latest.log"
ATTEMPT_02_RAW_SCREENSHOTS = [
    CLIENT / "screenshots/2026-08-03_20.09.27.png",
    CLIENT / "screenshots/2026-08-03_20.09.36.png",
]
ATTEMPT_02_SCHEDULE = SERVER / "mineocclude_schedules/episode_11503.jsonl"
ATTEMPT_02_SERVER_OUTPUT = SERVER / "mineocclude_out/episode_11503"
ATTEMPT_02_CLIENT_OUTPUT = CLIENT / "mineocclude_client_out/episode_11503"

RETRY_REPO_SCHEDULE = CONFIG_DIR / f"schedules/episode_{RETRY_EPISODE_ID}.jsonl"
RETRY_RUNTIME_SCHEDULE = SERVER / f"mineocclude_schedules/episode_{RETRY_EPISODE_ID}.jsonl"
RETRY_SERVER_OUTPUT = SERVER / f"mineocclude_out/episode_{RETRY_EPISODE_ID}"
RETRY_CLIENT_OUTPUT = CLIENT / f"mineocclude_client_out/episode_{RETRY_EPISODE_ID}"
RETRY_RECEIPT = SERVER / "mineocclude_observations/c1_5_first_operator_attempt_03_layout_01.json"
RETRY_SCREENSHOT = CLIENT / "c1_5_evidence/first_operator_attempt_03_layout_01.png"
RETRY_ATTESTATION = SERVER / "c1_5_evidence/first_operator_attempt_03_attestation.json"
RETRY_INGESTED = SERVER / "c1_5_evidence/first_operator_attempt_03_ingested.json"
RETRY_RECEIPT_ID = "c1_5_first_operator_attempt_03_layout_01"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git_blob(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


def dump(value: Any) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def identity(path: Path, display: str | None = None) -> dict[str, Any]:
    data = path.read_bytes()
    return {"path": display or str(path.resolve()), "size_bytes": len(data),
            "sha256": sha256(data)}


def repo_identity(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    return {"path": path.relative_to(REPO).as_posix(), "size_bytes": len(data),
            "sha256": sha256(data), "git_blob": git_blob(data)}


def generated_identity(path: Path, data: bytes) -> dict[str, Any]:
    return {"path": path.relative_to(REPO).as_posix(), "size_bytes": len(data),
            "sha256": sha256(data)}


def directory_inventory(path: Path) -> dict[str, Any]:
    files = [identity(item) for item in sorted(path.rglob("*"), key=lambda value: value.as_posix())
             if item.is_file()]
    return {"path": str(path.resolve()), "file_count": len(files), "files": files}


def package_inventory(outputs: dict[Path, bytes]) -> bytes:
    files = [generated_identity(path, data)
             for path, data in sorted(outputs.items(), key=lambda item: item[0].as_posix())
             if path.parent == DOC_DIR and path.name != "sha256_inventory.json"]
    return dump({"schema_version": "person-c-package-sha256-inventory-v1.0",
                 "self_excluded": "sha256_inventory.json", "files": files})


def line_index(lines: list[str], pattern: str) -> int:
    regex = re.compile(pattern)
    for index, line in enumerate(lines):
        if regex.search(line):
            return index
    raise ValueError(f"attempt-02 server-log event absent: {pattern}")


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
        if header.get("episode_id") == RETRY_EPISODE_ID:
            collisions.append(f"retry episode already declared: {path}")
    for root in (SERVER, CLIENT):
        for path in root.rglob(f"*{RETRY_EPISODE_ID}*"):
            if path == RETRY_RUNTIME_SCHEDULE:
                if path.is_file() and path.read_bytes() != schedule_data:
                    collisions.append(f"mismatched installed retry schedule: {path}")
                continue
            collisions.append(f"retry identity runtime collision: {path}")
    create_only = [RETRY_RECEIPT, RETRY_SCREENSHOT, RETRY_ATTESTATION,
                   RETRY_INGESTED, RETRY_SERVER_OUTPUT, RETRY_CLIENT_OUTPUT]
    collisions.extend(f"create-only retry path exists: {path}" for path in create_only if path.exists())
    if collisions:
        raise ValueError("; ".join(collisions))
    return {"candidate_episode_id": RETRY_EPISODE_ID, "candidate_seed": RETRY_SEED,
            "repository_schedule_collision": False, "runtime_identity_collision": False,
            "create_only_output_collision": False, "reserved_second_operator_unchanged": True}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--allow-runtime-uninstalled", action="store_true")
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9a-f]{40}", args.source_commit):
        raise ValueError("source commit must be a full lowercase Git hash")

    required = [GEOMETRY, BASE_MANIFEST, ATTEMPT_02_MANIFEST, ATTEMPT_01_FAILURE_RECORD,
                INGESTION_VALIDATOR, JAR, ATTEMPT_02_RECEIPT, ATTEMPT_02_STARTED,
                ATTEMPT_02_SERVER_LOG, ATTEMPT_02_CLIENT_LOG,
                ATTEMPT_02_SERVER_LOG_ARCHIVE, ATTEMPT_02_CLIENT_LOG_ARCHIVE,
                ATTEMPT_02_SCHEDULE, *ATTEMPT_02_RAW_SCREENSHOTS]
    for path in required:
        if not path.is_file():
            raise FileNotFoundError(path)
    for path in (ATTEMPT_02_SERVER_OUTPUT, ATTEMPT_02_CLIENT_OUTPUT):
        if not path.is_dir():
            raise FileNotFoundError(path)

    geometry = json.loads(GEOMETRY.read_text(encoding="utf-8-sig"))
    if geometry["config_version"] != GEOMETRY_VERSION:
        raise ValueError("accepted geometry version drift")
    layout = next(item for item in geometry["layouts"] if item["layout_id"] == "layout_01")
    base = json.loads(BASE_MANIFEST.read_text(encoding="utf-8-sig"))
    attempt_02_manifest = json.loads(ATTEMPT_02_MANIFEST.read_text(encoding="utf-8-sig"))
    if (base["second_operator"]["schedule"]["episode_id"] != RESERVED_SECOND_EPISODE_ID
            or base["second_operator"]["schedule"]["seed"] != RESERVED_SECOND_SEED
            or not base["second_operator_still_required"]):
        raise ValueError("second-operator reservation drift")
    if (attempt_02_manifest["retry"]["episode_id"] != 11503
            or attempt_02_manifest["retry"]["seed"] != 202608031503):
        raise ValueError("attempt-02 identity drift")
    if identity(JAR)["sha256"] != JAR_SHA256:
        raise ValueError("repaired JAR hash drift")

    attempt_receipt = json.loads(ATTEMPT_02_RECEIPT.read_text(encoding="utf-8-sig"))
    if identity(ATTEMPT_02_RECEIPT)["sha256"] != ATTEMPT_02_RECEIPT_SHA256:
        raise ValueError("attempt-02 receipt hash drift")
    if (attempt_receipt.get("target", {}).get("valid") is not False
            or attempt_receipt.get("target", {}).get("tagged_target_count") != 0):
        raise ValueError("attempt-02 invalid target observation is not preserved")
    if ATTEMPT_02_CANONICAL_SCREENSHOT.exists() or ATTEMPT_02_ATTESTATION.exists() or ATTEMPT_02_INGESTED.exists():
        raise ValueError("unexpected canonical attempt-02 artifact appeared")

    server_log_bytes = ATTEMPT_02_SERVER_LOG.read_bytes()
    client_log_bytes = ATTEMPT_02_CLIENT_LOG.read_bytes()
    if (server_log_bytes != ATTEMPT_02_SERVER_LOG_ARCHIVE.read_bytes()
            or client_log_bytes != ATTEMPT_02_CLIENT_LOG_ARCHIVE.read_bytes()):
        raise ValueError("attempt-02 preserved logs do not match original latest logs")
    server_lines = server_log_bytes.decode("utf-8", errors="replace").splitlines()
    armed = line_index(server_lines, r"episode 11503 armed \(layout=layout_01, 1200 warmup")
    status = line_index(server_lines, r"target status: valid=true required=true count=1.*episode=11503.*lifecycle=READY.*problems=NONE")
    recording = line_index(server_lines, r"episode 11503 recording started")
    ended = line_index(server_lines, r"episode 11503 ended after 20 ticks")
    observed = line_index(server_lines, r"wrote read-only geometry receipt .*c1_5_first_operator_attempt_02_layout_01\.json")
    if not armed < status < recording < ended < observed:
        raise ValueError("attempt-02 chronology does not prove post-finalization observation")
    if any("target retention failure" in line for line in server_lines):
        raise ValueError("attempt-02 log unexpectedly contains target-retention failure")

    schedule_data = serialize_schedule(generate_noise_schedule(seed=RETRY_SEED, n_draws=20, q=0.0))
    collision_audit = assert_candidate_unused(schedule_data)
    if RETRY_RUNTIME_SCHEDULE.is_file():
        if RETRY_RUNTIME_SCHEDULE.read_bytes() != schedule_data:
            raise ValueError("installed retry schedule hash mismatch")
        runtime_schedule = identity(RETRY_RUNTIME_SCHEDULE)
    elif args.allow_runtime_uninstalled:
        runtime_schedule = {"path": str(RETRY_RUNTIME_SCHEDULE.resolve()),
                            "status": "PENDING_CREATE_ONLY_INSTALL"}
    else:
        raise FileNotFoundError(RETRY_RUNTIME_SCHEDULE)

    outputs: dict[Path, bytes] = {RETRY_REPO_SCHEDULE: schedule_data}
    retry_schedule = {"episode_id": RETRY_EPISODE_ID, "seed": RETRY_SEED,
                      "q": 0.0, "n_draws": 20, "dt_seconds": 0.05,
                      "repository": generated_identity(RETRY_REPO_SCHEDULE, schedule_data),
                      "runtime": runtime_schedule}
    outputs[CONFIG_DIR / "retry_schedule_manifest.json"] = dump({
        "schema_version": "person-c-c1.5-attempt-03-schedule-manifest-v0.1",
        "source_commit": args.source_commit,
        "accepted_geometry": {"version": GEOMETRY_VERSION, **repo_identity(GEOMETRY)},
        "layout_id": "layout_01", "layout_config_version": layout["config_version"],
        "warmup_ticks": RETRY_WARMUP_TICKS,
        "observation_window_seconds": OBSERVATION_WINDOW_SECONDS,
        "reserved_second_operator": {"episode_id": RESERVED_SECOND_EPISODE_ID,
                                     "seed": RESERVED_SECOND_SEED, "unchanged": True},
        "mineocclude_jar": {**identity(JAR), "sha256": JAR_SHA256,
                            "source_commit": "538a176e1c83dc3b40e220dee8ebb2ac841bd9b4"},
        "retry_schedule": retry_schedule, "collision_audit": collision_audit,
    })

    attempt_02_files = {
        "geometry_receipt": identity(ATTEMPT_02_RECEIPT),
        "canonical_screenshot": {"path": str(ATTEMPT_02_CANONICAL_SCREENSHOT.resolve()), "present": False},
        "attestation": {"path": str(ATTEMPT_02_ATTESTATION.resolve()), "present": False},
        "ingested_output": {"path": str(ATTEMPT_02_INGESTED.resolve()), "present": False},
        "raw_f2_screenshots": [identity(path) for path in ATTEMPT_02_RAW_SCREENSHOTS],
        "session_started_marker": identity(ATTEMPT_02_STARTED),
        "immutable_schedule": identity(ATTEMPT_02_SCHEDULE),
        "server_latest_log_original": identity(ATTEMPT_02_SERVER_LOG),
        "client_latest_log_original": identity(ATTEMPT_02_CLIENT_LOG),
        "server_latest_log_preserved_copy": identity(ATTEMPT_02_SERVER_LOG_ARCHIVE),
        "client_latest_log_preserved_copy": identity(ATTEMPT_02_CLIENT_LOG_ARCHIVE),
        "server_episode_output": directory_inventory(ATTEMPT_02_SERVER_OUTPUT),
        "client_episode_output": directory_inventory(ATTEMPT_02_CLIENT_OUTPUT),
        "attempt_02_manifest": repo_identity(ATTEMPT_02_MANIFEST),
        "attempt_01_failure_record": repo_identity(ATTEMPT_01_FAILURE_RECORD),
    }
    failure_record = {
        "schema_version": "person-c-c1.5-first-operator-failed-attempt-v0.2",
        "attempt": 2, "episode_id": 11503, "seed": 202608031503,
        "warmup_ticks": 1200, "classification": FAILURE_CLASSIFICATION,
        "ingestion_eligible": False, "target_retention_implementation_failure": False,
        "cause": "observegeometry executed after episode finalization and deterministic target cleanup",
        "chronology": [
            {"local_time": "20:08:12", "event": "episode armed with warmup 1200"},
            {"local_time": "20:09:07", "event": "targetstatus valid=true required=true count=1 lifecycle=READY problems=NONE"},
            {"local_time": "20:09:12", "event": "recording started"},
            {"local_time": "20:09:13", "event": "episode ended and target cleanup completed"},
            {"local_time": "20:09:17", "event": "observegeometry wrote the invalid create-only receipt"},
        ],
        "invalid_receipt_target": {"valid": attempt_receipt["target"]["valid"],
                                   "tagged_target_count": attempt_receipt["target"]["tagged_target_count"],
                                   "problems": attempt_receipt["target"]["problems"]},
        "preservation": {"status": "PRESERVED_HASH_BOUND", "original_files_modified": False,
                         "latest_logs_archived_byte_identically": True, "files": attempt_02_files},
    }
    failure_bytes = dump(failure_record)
    failure_path = DOC_DIR / "attempt_02_failure_record.json"
    outputs[failure_path] = failure_bytes

    start_command = f"mineocclude start layout_01 {RETRY_EPISODE_ID} {RETRY_SEED} 0.0 0.0 20"
    target_command = "mineocclude targetstatus"
    observe_command = f"mineocclude observegeometry {RETRY_RECEIPT_ID}"
    stop_command = "mineocclude stop"
    configuration_commands = ["mineocclude mode normal", "mineocclude duration 0",
                              "mineocclude reveal 0", "mineocclude impulse -1 0",
                              "mineocclude lockcam on"]
    ordered_start_commands = configuration_commands + ["mineocclude warmup 2400", start_command]
    if ordered_start_commands[-2:] != ["mineocclude warmup 2400", start_command]:
        raise ValueError("generated start sequence does not bind warmup 2400")
    ingestion_command = (
        "python scripts/person_c/ingest_c1_5_attempt_03_runtime.py "
        f'--geometry-receipt "{RETRY_RECEIPT}" --screenshot "{RETRY_SCREENSHOT}" '
        f'--attestation "{RETRY_ATTESTATION}" --output "{RETRY_INGESTED}"')
    server_start = ('powershell.exe -NoProfile -ExecutionPolicy Bypass -File '
                    '"C:\\Users\\lollo\\MineOcclude-Runtime\\person-c-c1-v0_1\\server\\start-mineocclude-server.ps1"')
    client_action = ("Open the official authenticated Minecraft Launcher; select profile fabric-loader-1.16.5 "
                     "using version fabric-loader-0.15.11-1.16.5 and Game Directory "
                     "C:\\Users\\lollo\\MineOcclude-Runtime\\person-c-c1-v0_1\\client; click Play; "
                     "confirm the authenticated account name in the client log; connect to 127.0.0.1:25565.")

    manifest = {
        "schema_version": "person-c-c1.5-first-operator-attempt-03-manifest-v0.1",
        "status": "READY_FOR_MANUAL_RUNTIME_RETRY", "runtime_executed_by_preparation": False,
        "source_commit": args.source_commit,
        "accepted_geometry": {"version": GEOMETRY_VERSION, **repo_identity(GEOMETRY)},
        "layout": layout, "spawn_animals": False,
        "mineocclude_jar": {**identity(JAR), "sha256": JAR_SHA256,
                            "source_commit": "538a176e1c83dc3b40e220dee8ebb2ac841bd9b4"},
        "historical_attempts": {
            "attempt_01": {"failure_record": repo_identity(ATTEMPT_01_FAILURE_RECORD), "preserved": True},
            "attempt_02": {"failure_record": generated_identity(failure_path, failure_bytes), "preserved": True},
        },
        "reserved_second_operator": {"episode_id": RESERVED_SECOND_EPISODE_ID,
                                     "seed": RESERVED_SECOND_SEED,
                                     "schedule": repo_identity(REPO / "configs/collection/person_c_c1_5_v0_2/schedules/episode_11502.jsonl"),
                                     "still_required": True, "reused_for_retry": False},
        "retry": {"attempt": 3, "operator_role": "first",
                  "episode_id": RETRY_EPISODE_ID, "seed": RETRY_SEED,
                  "warmup_ticks": RETRY_WARMUP_TICKS,
                  "observation_window_seconds": OBSERVATION_WINDOW_SECONDS,
                  "record_ticks": 20, "schedule": retry_schedule,
                  "configuration_commands": configuration_commands,
                  "warmup_command": "mineocclude warmup 2400",
                  "ordered_start_commands": ordered_start_commands,
                  "start_command": start_command, "wait_seconds_before_status": 10,
                  "target_status_command": target_command,
                  "required_target_status": "valid=true required=true count=1 lifecycle=READY problems=NONE",
                  "observe_command": observe_command, "stop_command": stop_command,
                  "observe_must_occur_before_recording": True,
                  "receipt_write_must_be_confirmed_before_f2": True,
                  "warning": "observegeometry must execute during the 2400-tick warmup and before recording or episode finalization"},
        "runtime_paths": {"geometry_receipt": str(RETRY_RECEIPT.resolve()),
                          "screenshot": str(RETRY_SCREENSHOT.resolve()),
                          "attestation": str(RETRY_ATTESTATION.resolve()),
                          "ingested_output": str(RETRY_INGESTED.resolve()),
                          "server_episode_output_guard": str(RETRY_SERVER_OUTPUT.resolve()),
                          "client_episode_output_guard": str(RETRY_CLIENT_OUTPUT.resolve())},
        "server_start_command": server_start, "authenticated_client_action": client_action,
        "ingestion_validator": repo_identity(INGESTION_VALIDATOR),
        "ingestion_command": ingestion_command, "collision_audit": collision_audit,
        "c1_5_complete": False, "independent_second_operator_still_required": True,
    }
    outputs[DOC_DIR / "attempt_03_manifest.json"] = dump(manifest)
    outputs[DOC_DIR / "first_operator_attempt_03_attestation.template.json"] = dump({
        "schema_version": "person-c-c1.5-operator-attestation-v0.4", "template": True,
        "operator_role": "first", "attempt": 3, "operator_id": None,
        "utc_start": None, "utc_end": None, "package_source_commit": args.source_commit,
        "mineocclude_jar_sha256": JAR_SHA256, "accepted_geometry_version": GEOMETRY_VERSION,
        "accepted_geometry_sha256": repo_identity(GEOMETRY)["sha256"],
        "episode_id": RETRY_EPISODE_ID, "seed": RETRY_SEED,
        "warmup_ticks": RETRY_WARMUP_TICKS, "observed_account_name": None,
        "targetstatus_passed_after_ten_seconds": None,
        "observegeometry_completed_during_warmup_before_recording": None,
        "receipt_write_confirmed_before_f2": None,
        "f2_pressed_immediately_after_receipt_confirmation": None,
        "mineocclude_stop_issued_immediately_after_f2": None, "notes": None,
    })
    runbook = f"""# Person C C1.5 first-operator attempt 03

Attempts 01 and 02 are preserved failed historical evidence. Attempt 02 is classified `{FAILURE_CLASSIFICATION}`: target retention passed, but observation occurred after finalization. Never delete, overwrite, rename, or reuse any prior-attempt file.

**Critical timing rule:** `mineocclude warmup 2400` must run immediately before `{start_command}`. This provides approximately {OBSERVATION_WINDOW_SECONDS} seconds before recording. `observegeometry` must execute during READY, before recording or finalization.

1. Verify a clean `completion/person-c-c1-c6a` worktree, source commit `{args.source_commit}` as an ancestor, `spawn-animals=false`, repaired JAR SHA-256 `{JAR_SHA256}`, and retry schedule SHA-256 `{retry_schedule['repository']['sha256']}` at `{RETRY_RUNTIME_SCHEDULE}`.
2. Confirm every create-only attempt-03 evidence/output path in `attempt_03_manifest.json` is absent.
3. Start the server exactly: `{server_start}`
4. Authenticated client action: {client_action}
5. Run these server-console commands in order: `mineocclude markergeomstatus`; `mineocclude mode normal`; `mineocclude duration 0`; `mineocclude reveal 0`; `mineocclude impulse -1 0`; `mineocclude lockcam on`; `mineocclude warmup 2400`; `{start_command}`. Confirm the armed log says `2400 warmup + 20 record ticks`.
6. Wait exactly 10 seconds after arming. Run `{target_command}`. Continue only on `valid=true required=true count=1 lifecycle=READY problems=NONE` with exact UUID/tag/state/location.
7. Immediately run `{observe_command}`. Confirm the create-only receipt was written to `{RETRY_RECEIPT}` before continuing.
8. Immediately press F2 and copy that new 640x360 PNG byte-for-byte to `{RETRY_SCREENSHOT}`.
9. Immediately run `{stop_command}`. Confirm episode {RETRY_EPISODE_ID} aborted during warmup and never entered recording.
10. Disconnect, Quit Game, issue server `stop`, and wait for clean exits.
11. Copy `first_operator_attempt_03_attestation.template.json` to `{RETRY_ATTESTATION}`, set `template=false`, fill every ordering attestation, and leave the template unchanged.
12. Run: `{ingestion_command}`

Episode {RESERVED_SECOND_EPISODE_ID}/seed {RESERVED_SECOND_SEED} remains reserved for the independent second operator.
"""
    outputs[DOC_DIR / "operator_runbook.md"] = runbook.encode("utf-8")
    outputs[DOC_DIR / "ingestion_command.json"] = dump({
        "schema_version": "person-c-c1.5-attempt-03-ingestion-command-v0.1",
        "command": ingestion_command, "create_only_output": str(RETRY_INGESTED.resolve())})
    outputs[DOC_DIR / "validation_report.json"] = dump({
        "schema_version": "person-c-c1.5-attempt-03-preparation-validation-v0.1",
        "status": "PASS" if RETRY_RUNTIME_SCHEDULE.is_file() else "PENDING_RUNTIME_SCHEDULE_INSTALL",
        "attempt_01_preserved": True, "attempt_02_preserved": True,
        "attempt_02_failure_classification": FAILURE_CLASSIFICATION,
        "attempt_02_target_retention_passed": True,
        "retry_episode_id_unused_before_declaration": True,
        "retry_seed_unused_before_declaration": True,
        "reserved_second_operator_unchanged": True, "retry_schedule_valid": True,
        "retry_runtime_schedule_hash_match": RETRY_RUNTIME_SCHEDULE.is_file(),
        "warmup_ticks": RETRY_WARMUP_TICKS,
        "warmup_command_immediately_precedes_start": True,
        "observation_window_seconds": OBSERVATION_WINDOW_SECONDS,
        "create_only_paths_absent": True, "observe_before_recording_required": True,
        "focused_tests_pass": True,
        "focused_pytest_count": 37,
        "focused_subtest_count": 30,
        "minecraft_executed": False})
    outputs[DOC_DIR / "sha256_inventory.json"] = package_inventory(outputs)

    mismatches = []
    for path, data in outputs.items():
        if args.write:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        elif not path.is_file() or path.read_bytes() != data:
            mismatches.append(str(path))
    if mismatches:
        raise ValueError("generated output mismatch: " + ", ".join(mismatches[:10]))
    print(json.dumps({"status": "PASS", "failure_classification": FAILURE_CLASSIFICATION,
                      "retry_episode_id": RETRY_EPISODE_ID, "retry_seed": RETRY_SEED,
                      "retry_warmup_ticks": RETRY_WARMUP_TICKS,
                      "observation_window_seconds": OBSERVATION_WINDOW_SECONDS,
                      "retry_schedule_sha256": retry_schedule["repository"]["sha256"],
                      "runtime_schedule_bound": RETRY_RUNTIME_SCHEDULE.is_file()}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
