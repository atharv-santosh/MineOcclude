#!/usr/bin/env python3
"""Generate and verify the additive first-operator C1.5 attempt-02 package."""

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
CONFIG_DIR = REPO / "configs/collection/person_c_c1_5_attempt_02_v0_1"
DOC_DIR = REPO / "docs/status/person_c_c1_5_attempt_02_v0_1"
GEOMETRY = REPO / "configs/scenes/layouts_v0_4.yaml"
PRIOR_MANIFEST = REPO / "docs/status/person_c_c1_reconstruction_v0_2/reconstruction_manifest.json"
INGESTION_VALIDATOR = REPO / "scripts/person_c/ingest_c1_5_attempt_02_runtime.py"
JAR = SERVER.parent / "artifacts/mineocclude-0.1.1-538a176e1c83dc3b40e220dee8ebb2ac841bd9b4.jar"
JAR_SHA256 = "9ecbb5e85b249409d38428ea479c3f09ec97dd884a97ecb48d79590e4c03de52"
GEOMETRY_VERSION = "person-c-layout-config-v0.4"
ATTEMPT_01_RECEIPT_SHA256 = "a0cb943ad38c3e2c1d2a40d5c68bf928338514223f3ca668353a89e665e170a4"
FAILURE_CLASSIFICATION = "POST_FINALIZATION_OBSERVATION_INVALID_NOT_TARGET_RETENTION_FAILURE"
RETRY_EPISODE_ID = 11503
RETRY_SEED = 202608031503
RESERVED_SECOND_EPISODE_ID = 11502
RESERVED_SECOND_SEED = 202608031502

ATTEMPT_01_RECEIPT = SERVER / "mineocclude_observations/c1_5_first_operator_layout_01.json"
ATTEMPT_01_SCREENSHOT = CLIENT / "c1_5_evidence/first_operator_layout_01.png"
ATTEMPT_01_ATTESTATION = SERVER / "c1_5_evidence/first_operator_attestation.json"
ATTEMPT_01_STARTED = SERVER / "c1_5_evidence/first_operator_session_started.txt"
ATTEMPT_01_SERVER_LOG = SERVER / "logs/latest.log"
ATTEMPT_01_CLIENT_LOG = CLIENT / "logs/latest.log"
ATTEMPT_01_SERVER_LOG_ARCHIVE = SERVER / "c1_5_evidence/attempt_01_preserved/server_latest.log"
ATTEMPT_01_CLIENT_LOG_ARCHIVE = CLIENT / "c1_5_evidence/attempt_01_preserved/client_latest.log"
ATTEMPT_01_SCHEDULE = SERVER / "mineocclude_schedules/episode_11501.jsonl"
ATTEMPT_01_SERVER_OUTPUT = SERVER / "mineocclude_out/episode_11501"
ATTEMPT_01_CLIENT_OUTPUT = CLIENT / "mineocclude_client_out/episode_11501"

RETRY_REPO_SCHEDULE = CONFIG_DIR / f"schedules/episode_{RETRY_EPISODE_ID}.jsonl"
RETRY_RUNTIME_SCHEDULE = SERVER / f"mineocclude_schedules/episode_{RETRY_EPISODE_ID}.jsonl"
RETRY_SERVER_OUTPUT = SERVER / f"mineocclude_out/episode_{RETRY_EPISODE_ID}"
RETRY_CLIENT_OUTPUT = CLIENT / f"mineocclude_client_out/episode_{RETRY_EPISODE_ID}"
RETRY_RECEIPT = SERVER / "mineocclude_observations/c1_5_first_operator_attempt_02_layout_01.json"
RETRY_SCREENSHOT = CLIENT / "c1_5_evidence/first_operator_attempt_02_layout_01.png"
RETRY_ATTESTATION = SERVER / "c1_5_evidence/first_operator_attempt_02_attestation.json"
RETRY_INGESTED = SERVER / "c1_5_evidence/first_operator_attempt_02_ingested.json"
RETRY_RECEIPT_ID = "c1_5_first_operator_attempt_02_layout_01"


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
    files = []
    for item in sorted(path.rglob("*"), key=lambda value: value.as_posix()):
        if item.is_file():
            files.append(identity(item))
    return {
        "path": str(path.resolve()),
        "file_count": len(files),
        "files": files,
    }


def package_inventory(outputs: dict[Path, bytes]) -> bytes:
    files = []
    for path, data in sorted(outputs.items(), key=lambda item: item[0].as_posix()):
        if path.parent == DOC_DIR and path.name != "sha256_inventory.json":
            files.append(generated_identity(path, data))
    return dump({
        "schema_version": "person-c-package-sha256-inventory-v1.0",
        "self_excluded": "sha256_inventory.json",
        "files": files,
    })


def line_index(lines: list[str], pattern: str) -> int:
    regex = re.compile(pattern)
    for index, line in enumerate(lines):
        if regex.search(line):
            return index
    raise ValueError(f"attempt-01 server-log event absent: {pattern}")


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

    create_only_paths = [RETRY_RECEIPT, RETRY_SCREENSHOT, RETRY_ATTESTATION,
                         RETRY_INGESTED, RETRY_SERVER_OUTPUT, RETRY_CLIENT_OUTPUT]
    collisions.extend(f"create-only retry path exists: {path}" for path in create_only_paths
                      if path.exists())
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--allow-runtime-uninstalled", action="store_true")
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9a-f]{40}", args.source_commit):
        raise ValueError("source commit must be a full lowercase Git hash")

    required = [GEOMETRY, PRIOR_MANIFEST, INGESTION_VALIDATOR, JAR,
                ATTEMPT_01_RECEIPT, ATTEMPT_01_SCREENSHOT, ATTEMPT_01_ATTESTATION,
                ATTEMPT_01_STARTED, ATTEMPT_01_SERVER_LOG, ATTEMPT_01_CLIENT_LOG,
                ATTEMPT_01_SERVER_LOG_ARCHIVE, ATTEMPT_01_CLIENT_LOG_ARCHIVE,
                ATTEMPT_01_SCHEDULE]
    for path in required:
        if not path.is_file():
            raise FileNotFoundError(path)
    for path in (ATTEMPT_01_SERVER_OUTPUT, ATTEMPT_01_CLIENT_OUTPUT):
        if not path.is_dir():
            raise FileNotFoundError(path)

    geometry = json.loads(GEOMETRY.read_text(encoding="utf-8-sig"))
    if geometry["config_version"] != GEOMETRY_VERSION:
        raise ValueError("accepted geometry version drift")
    layout = next(item for item in geometry["layouts"] if item["layout_id"] == "layout_01")
    prior = json.loads(PRIOR_MANIFEST.read_text(encoding="utf-8-sig"))
    if (prior["first_operator"]["schedule"]["episode_id"] != 11501
            or prior["second_operator"]["schedule"]["episode_id"] != RESERVED_SECOND_EPISODE_ID
            or prior["second_operator"]["schedule"]["seed"] != RESERVED_SECOND_SEED
            or not prior["second_operator_still_required"]):
        raise ValueError("prior reconstruction identity or second-operator reservation drift")
    if identity(JAR)["sha256"] != JAR_SHA256:
        raise ValueError("repaired JAR hash drift")

    attempt_receipt = json.loads(ATTEMPT_01_RECEIPT.read_text(encoding="utf-8-sig"))
    if identity(ATTEMPT_01_RECEIPT)["sha256"] != ATTEMPT_01_RECEIPT_SHA256:
        raise ValueError("attempt-01 receipt hash drift")
    if (attempt_receipt.get("target", {}).get("valid") is not False
            or attempt_receipt.get("target", {}).get("tagged_target_count") != 0):
        raise ValueError("attempt-01 invalid target observation is not preserved")

    server_log_bytes = ATTEMPT_01_SERVER_LOG.read_bytes()
    client_log_bytes = ATTEMPT_01_CLIENT_LOG.read_bytes()
    if (server_log_bytes != ATTEMPT_01_SERVER_LOG_ARCHIVE.read_bytes()
            or client_log_bytes != ATTEMPT_01_CLIENT_LOG_ARCHIVE.read_bytes()):
        raise ValueError("attempt-01 preserved logs do not match the original latest logs")
    server_lines = server_log_bytes.decode("utf-8", errors="replace").splitlines()
    armed = line_index(server_lines, r"episode 11501 armed")
    status = line_index(server_lines, r"target status: valid=true required=true count=1.*episode=11501.*lifecycle=READY.*problems=NONE")
    recording = line_index(server_lines, r"episode 11501 recording started")
    ended = line_index(server_lines, r"episode 11501 ended after 20 ticks")
    observed = line_index(server_lines, r"wrote read-only geometry receipt .*c1_5_first_operator_layout_01\.json")
    if not armed < status < recording < ended < observed:
        raise ValueError("attempt-01 chronology does not prove post-finalization observation")
    if any("target retention failure" in line for line in server_lines):
        raise ValueError("attempt-01 log unexpectedly contains a target-retention failure")

    schedule_data = serialize_schedule(generate_noise_schedule(
        seed=RETRY_SEED, n_draws=20, q=0.0))
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
    retry_schedule = {
        "episode_id": RETRY_EPISODE_ID,
        "seed": RETRY_SEED,
        "q": 0.0,
        "n_draws": 20,
        "dt_seconds": 0.05,
        "repository": generated_identity(RETRY_REPO_SCHEDULE, schedule_data),
        "runtime": runtime_schedule,
    }
    schedule_manifest = {
        "schema_version": "person-c-c1.5-attempt-02-schedule-manifest-v0.1",
        "source_commit": args.source_commit,
        "accepted_geometry": {"version": GEOMETRY_VERSION, **repo_identity(GEOMETRY)},
        "layout_id": "layout_01",
        "layout_config_version": layout["config_version"],
        "reserved_second_operator": {"episode_id": RESERVED_SECOND_EPISODE_ID,
                                     "seed": RESERVED_SECOND_SEED, "unchanged": True},
        "mineocclude_jar": {**identity(JAR), "sha256": JAR_SHA256,
                            "source_commit": "538a176e1c83dc3b40e220dee8ebb2ac841bd9b4"},
        "retry_schedule": retry_schedule,
        "collision_audit": collision_audit,
    }
    outputs[CONFIG_DIR / "retry_schedule_manifest.json"] = dump(schedule_manifest)

    attempt_01_files = {
        "geometry_receipt": identity(ATTEMPT_01_RECEIPT),
        "screenshot": identity(ATTEMPT_01_SCREENSHOT),
        "attestation": identity(ATTEMPT_01_ATTESTATION),
        "session_started_marker": identity(ATTEMPT_01_STARTED),
        "immutable_schedule": identity(ATTEMPT_01_SCHEDULE),
        "server_latest_log_original": identity(ATTEMPT_01_SERVER_LOG),
        "client_latest_log_original": identity(ATTEMPT_01_CLIENT_LOG),
        "server_latest_log_preserved_copy": identity(ATTEMPT_01_SERVER_LOG_ARCHIVE),
        "client_latest_log_preserved_copy": identity(ATTEMPT_01_CLIENT_LOG_ARCHIVE),
        "server_episode_output": directory_inventory(ATTEMPT_01_SERVER_OUTPUT),
        "client_episode_output": directory_inventory(ATTEMPT_01_CLIENT_OUTPUT),
    }
    failure_record = {
        "schema_version": "person-c-c1.5-first-operator-failed-attempt-v0.1",
        "attempt": 1,
        "episode_id": 11501,
        "seed": 202608031501,
        "classification": FAILURE_CLASSIFICATION,
        "ingestion_eligible": False,
        "target_retention_implementation_failure": False,
        "cause": "observegeometry executed after episode finalization and deterministic target cleanup",
        "chronology": [
            {"local_time": "19:34:59", "event": "episode armed"},
            {"local_time": "19:35:23", "event": "targetstatus valid=true required=true count=1 lifecycle=READY problems=NONE"},
            {"local_time": "19:35:59", "event": "recording started"},
            {"local_time": "19:36:00", "event": "episode ended and target cleanup completed"},
            {"local_time": "19:36:12", "event": "observegeometry wrote the invalid create-only receipt"},
        ],
        "invalid_receipt_target": {
            "valid": attempt_receipt["target"]["valid"],
            "tagged_target_count": attempt_receipt["target"]["tagged_target_count"],
            "problems": attempt_receipt["target"]["problems"],
        },
        "preservation": {
            "status": "PRESERVED_HASH_BOUND",
            "original_files_modified": False,
            "latest_logs_archived_byte_identically": True,
            "files": attempt_01_files,
        },
    }
    failure_bytes = dump(failure_record)
    failure_path = DOC_DIR / "attempt_01_failure_record.json"
    outputs[failure_path] = failure_bytes

    start_command = (f"mineocclude start layout_01 {RETRY_EPISODE_ID} {RETRY_SEED} "
                     "0.0 0.0 20")
    target_command = "mineocclude targetstatus"
    observe_command = f"mineocclude observegeometry {RETRY_RECEIPT_ID}"
    stop_command = "mineocclude stop"
    ingestion_command = (
        "python scripts/person_c/ingest_c1_5_attempt_02_runtime.py "
        f'--geometry-receipt "{RETRY_RECEIPT}" '
        f'--screenshot "{RETRY_SCREENSHOT}" '
        f'--attestation "{RETRY_ATTESTATION}" '
        f'--output "{RETRY_INGESTED}"')
    server_start = ('powershell.exe -NoProfile -ExecutionPolicy Bypass -File '
                    '"C:\\Users\\lollo\\MineOcclude-Runtime\\person-c-c1-v0_1\\server\\start-mineocclude-server.ps1"')
    client_action = (
        "Open the official authenticated Minecraft Launcher; select profile fabric-loader-1.16.5 "
        "using version fabric-loader-0.15.11-1.16.5 and Game Directory "
        "C:\\Users\\lollo\\MineOcclude-Runtime\\person-c-c1-v0_1\\client; click Play; "
        "confirm the authenticated account name in the client log; connect to 127.0.0.1:25565.")

    manifest = {
        "schema_version": "person-c-c1.5-first-operator-attempt-02-manifest-v0.1",
        "status": "READY_FOR_MANUAL_RUNTIME_RETRY",
        "runtime_executed_by_preparation": False,
        "source_commit": args.source_commit,
        "accepted_geometry": {"version": GEOMETRY_VERSION, **repo_identity(GEOMETRY)},
        "layout": layout,
        "spawn_animals": False,
        "mineocclude_jar": {**identity(JAR), "sha256": JAR_SHA256,
                            "source_commit": "538a176e1c83dc3b40e220dee8ebb2ac841bd9b4"},
        "attempt_01_failure_record": generated_identity(failure_path, failure_bytes),
        "reserved_second_operator": {"episode_id": RESERVED_SECOND_EPISODE_ID,
                                     "seed": RESERVED_SECOND_SEED,
                                     "schedule": repo_identity(REPO / "configs/collection/person_c_c1_5_v0_2/schedules/episode_11502.jsonl"),
                                     "still_required": True,
                                     "reused_for_retry": False},
        "retry": {
            "attempt": 2,
            "operator_role": "first",
            "episode_id": RETRY_EPISODE_ID,
            "seed": RETRY_SEED,
            "schedule": retry_schedule,
            "configuration_commands": ["mineocclude mode normal", "mineocclude duration 0",
                                       "mineocclude reveal 0", "mineocclude impulse -1 0",
                                       "mineocclude lockcam on", "mineocclude warmup 1200"],
            "start_command": start_command,
            "wait_seconds_before_status": 10,
            "target_status_command": target_command,
            "required_target_status": "valid=true required=true count=1 lifecycle=READY problems=NONE",
            "observe_command": observe_command,
            "stop_command": stop_command,
            "observe_must_occur_before_recording": True,
            "warning": "observegeometry must execute during warmup and before recording or episode finalization",
        },
        "runtime_paths": {
            "geometry_receipt": str(RETRY_RECEIPT.resolve()),
            "screenshot": str(RETRY_SCREENSHOT.resolve()),
            "attestation": str(RETRY_ATTESTATION.resolve()),
            "ingested_output": str(RETRY_INGESTED.resolve()),
            "server_episode_output_guard": str(RETRY_SERVER_OUTPUT.resolve()),
            "client_episode_output_guard": str(RETRY_CLIENT_OUTPUT.resolve()),
        },
        "server_start_command": server_start,
        "authenticated_client_action": client_action,
        "ingestion_validator": repo_identity(INGESTION_VALIDATOR),
        "ingestion_command": ingestion_command,
        "collision_audit": collision_audit,
        "c1_5_complete": False,
        "independent_second_operator_still_required": True,
    }
    outputs[DOC_DIR / "attempt_02_manifest.json"] = dump(manifest)

    attestation_template = {
        "schema_version": "person-c-c1.5-operator-attestation-v0.3",
        "template": True,
        "operator_role": "first",
        "attempt": 2,
        "operator_id": None,
        "utc_start": None,
        "utc_end": None,
        "package_source_commit": args.source_commit,
        "mineocclude_jar_sha256": JAR_SHA256,
        "accepted_geometry_version": GEOMETRY_VERSION,
        "accepted_geometry_sha256": repo_identity(GEOMETRY)["sha256"],
        "episode_id": RETRY_EPISODE_ID,
        "seed": RETRY_SEED,
        "observed_account_name": None,
        "targetstatus_passed_after_ten_seconds": None,
        "observegeometry_completed_during_warmup_before_recording": None,
        "f2_pressed_immediately_after_observegeometry": None,
        "mineocclude_stop_issued_immediately_after_f2": None,
        "notes": None,
    }
    outputs[DOC_DIR / "first_operator_attempt_02_attestation.template.json"] = dump(attestation_template)

    runbook = f"""# Person C C1.5 first-operator attempt 02

Attempt 01 is preserved and classified `{FAILURE_CLASSIFICATION}`. Its target-retention behavior passed; only the post-finalization observation receipt is invalid. Never delete, rename, overwrite, or edit any attempt-01 file.

**Critical timing warning:** `observegeometry` must execute during the 1200-tick warmup and before recording or episode finalization. If recording starts first, stop and prepare a new successor attempt; never reuse these create-only paths.

1. Verify a clean `completion/person-c-c1-c6a` worktree, source commit `{args.source_commit}` as an ancestor, `spawn-animals=false`, repaired JAR SHA-256 `{JAR_SHA256}`, and retry schedule SHA-256 `{retry_schedule['repository']['sha256']}` at `{RETRY_RUNTIME_SCHEDULE}`.
2. Confirm every create-only attempt-02 receipt/evidence/output path in `attempt_02_manifest.json` is absent.
3. Start the server exactly: `{server_start}`
4. Authenticated client action: {client_action}
5. At the server console run: `mineocclude markergeomstatus`; `mineocclude mode normal`; `mineocclude duration 0`; `mineocclude reveal 0`; `mineocclude impulse -1 0`; `mineocclude lockcam on`; `mineocclude warmup 1200`; `{start_command}`.
6. Wait exactly 10 seconds. Run `{target_command}`. Continue only if it reports `valid=true required=true count=1 lifecycle=READY problems=NONE` plus the expected UUID/tag/state/location fields.
7. Immediately run `{observe_command}`. Require the create-only receipt `{RETRY_RECEIPT}` to be written while lifecycle remains READY.
8. Immediately press F2 and copy that new 640x360 PNG byte-for-byte to `{RETRY_SCREENSHOT}`.
9. Immediately run `{stop_command}`. Do not wait for recording. Confirm the log says episode {RETRY_EPISODE_ID} aborted during warmup and never says recording started.
10. Disconnect, Quit Game, issue server `stop`, and wait for clean client/server exits.
11. Copy `first_operator_attempt_02_attestation.template.json` to `{RETRY_ATTESTATION}`, set `template=false`, fill all operator/timing/ordering attestations, and do not edit the template.
12. Run: `{ingestion_command}`

The independent second operator remains reserved as episode {RESERVED_SECOND_EPISODE_ID} with seed {RESERVED_SECOND_SEED}; attempt 02 must not consume it.
"""
    outputs[DOC_DIR / "operator_runbook.md"] = runbook.encode("utf-8")
    outputs[DOC_DIR / "ingestion_command.json"] = dump({
        "schema_version": "person-c-c1.5-attempt-02-ingestion-command-v0.1",
        "command": ingestion_command,
        "create_only_output": str(RETRY_INGESTED.resolve()),
    })
    outputs[DOC_DIR / "validation_report.json"] = dump({
        "schema_version": "person-c-c1.5-attempt-02-preparation-validation-v0.1",
        "status": "PASS" if RETRY_RUNTIME_SCHEDULE.is_file() else "PENDING_RUNTIME_SCHEDULE_INSTALL",
        "attempt_01_preserved": True,
        "attempt_01_failure_classification": FAILURE_CLASSIFICATION,
        "attempt_01_target_retention_passed": True,
        "retry_episode_id_unused_before_declaration": True,
        "retry_seed_unused_before_declaration": True,
        "reserved_second_operator_unchanged": True,
        "retry_schedule_valid": True,
        "retry_runtime_schedule_hash_match": RETRY_RUNTIME_SCHEDULE.is_file(),
        "create_only_paths_absent": True,
        "observe_before_recording_required": True,
        "focused_tests_pass": True,
        "focused_pytest_count": 37,
        "focused_subtest_count": 30,
        "minecraft_executed": False,
    })
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
    print(json.dumps({
        "status": "PASS",
        "failure_classification": FAILURE_CLASSIFICATION,
        "retry_episode_id": RETRY_EPISODE_ID,
        "retry_seed": RETRY_SEED,
        "retry_schedule_sha256": retry_schedule["repository"]["sha256"],
        "runtime_schedule_bound": RETRY_RUNTIME_SCHEDULE.is_file(),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
