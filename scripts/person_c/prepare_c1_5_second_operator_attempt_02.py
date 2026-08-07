#!/usr/bin/env python3
"""Prepare the additive C1.5 independent second-operator attempt-02 package."""

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
SOURCE_COMMIT = "75f6515aead5755f1f47a3cddea354102eead328"
RUNTIME_SOURCE_COMMIT = "538a176e1c83dc3b40e220dee8ebb2ac841bd9b4"
JAR_SHA256 = "9ecbb5e85b249409d38428ea479c3f09ec97dd884a97ecb48d79590e4c03de52"
GEOMETRY_VERSION = "person-c-layout-config-v0.4"
GEOMETRY_SHA256 = "34495d650d6a8c62b00a916796c90389b48f80d8f20a23eac93207758e993f5d"
FAILURE_CLASSIFICATION = "SCREENSHOT_CAPTURED_BEFORE_GEOMETRY_RECEIPT_CONFIRMATION"
ATTEMPT_01_ACCOUNT = "Santa313"
RETRY_EPISODE_ID = 11506
RETRY_SEED = 202608031506
RETRY_WARMUP_TICKS = 12000
OBSERVATION_WINDOW_SECONDS = 600
RECORD_TICKS = 20

DOC_DIR = REPO / "docs/status/person_c_c1_5_second_operator_attempt_02_v0_1"
CONFIG_DIR = REPO / "configs/collection/person_c_c1_5_second_operator_attempt_02_v0_1"
REPO_SCHEDULE = CONFIG_DIR / "schedules/episode_11506.jsonl"
RUNTIME_SCHEDULE = SERVER / "mineocclude_schedules/episode_11506.jsonl"
GEOMETRY = REPO / "configs/scenes/layouts_v0_4.yaml"
INSTALLED_JAR = SERVER / "mods/mineocclude-0.1.1.jar"
VALIDATOR = REPO / "scripts/person_c/ingest_c1_5_second_operator_attempt_02_runtime.py"
FINALIZER = REPO / "scripts/person_c/finalize-c1-5-second-operator-attempt-02.ps1"

ATTEMPT_01_RECEIPT = SERVER / "mineocclude_observations/c1_5_second_operator_attempt_01_layout_01.json"
ATTEMPT_01_RAW_SCREENSHOT = CLIENT / "screenshots/2026-08-03_22.25.53.png"
ATTEMPT_01_SERVER_LOG = SERVER / "c1_5_evidence/second_operator_attempt_01_preserved/server_latest.log"
ATTEMPT_01_CLIENT_LOG = CLIENT / "c1_5_evidence/second_operator_attempt_01_preserved/client_latest.log"
ATTEMPT_01_SCHEDULE = SERVER / "mineocclude_schedules/episode_11502.jsonl"
ATTEMPT_01_CANONICAL = CLIENT / "c1_5_evidence/second_operator_attempt_01_layout_01.png"
ATTEMPT_01_ATTESTATION = SERVER / "c1_5_evidence/second_operator_attempt_01_attestation.json"
ATTEMPT_01_INGESTED = SERVER / "c1_5_evidence/second_operator_attempt_01_ingested.json"
ATTEMPT_01_HASHES = {
    ATTEMPT_01_RECEIPT: "7625fd454b71acedcd42524cab64bb799147020e21e7e78e888f3d31e092b630",
    ATTEMPT_01_RAW_SCREENSHOT: "ebcde38bf4b2e8edd313d26de5bf95efabda0a183354ad09d03593565c063c21",
    ATTEMPT_01_SERVER_LOG: "2dd9c8aa26c1e15f1b9331991d13d24b73bbaa13ce98ff18348283af4248b513",
    ATTEMPT_01_CLIENT_LOG: "155ad971f724ac5f5db81a13d7eae42e032011eb8c70ea4c8e2cb3c0a2249812",
    ATTEMPT_01_SCHEDULE: "b399dd08b7e2dcdecc136400cb47afa680995edf04239f3a79e36bcc688655c7",
}

RETRY_RECEIPT_ID = "c1_5_second_operator_attempt_02_layout_01"
RETRY_RECEIPT = SERVER / f"mineocclude_observations/{RETRY_RECEIPT_ID}.json"
RETRY_SCREENSHOT = CLIENT / "c1_5_evidence/second_operator_attempt_02_layout_01.png"
RETRY_ATTESTATION = SERVER / "c1_5_evidence/second_operator_attempt_02_attestation.json"
RETRY_INGESTED = SERVER / "c1_5_evidence/second_operator_attempt_02_ingested.json"
RETRY_SERVER_LOG = SERVER / "c1_5_evidence/second_operator_attempt_02_success/server_latest.log"
RETRY_CLIENT_LOG = CLIENT / "c1_5_evidence/second_operator_attempt_02_success/client_latest.log"
RETRY_SERVER_OUTPUT = SERVER / "mineocclude_out/episode_11506"
RETRY_CLIENT_OUTPUT = CLIENT / "mineocclude_client_out/episode_11506"

ATTESTATION_TEMPLATE: dict[str, Any] = {
    "schema_version": "person-c-c1.5-independent-second-operator-attempt-02-attestation-v0.1",
    "template": True,
    "operator_role": "second",
    "attempt": 2,
    "operator_id": None,
    "independent_from_first_operator": True,
    "same_human_as_second_operator_attempt_01": None,
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
    "attempt_01_observed_account_name": ATTEMPT_01_ACCOUNT,
    "attempt_01_geometry_receipt_sha256": ATTEMPT_01_HASHES[ATTEMPT_01_RECEIPT],
    "attempt_01_failure_record_sha256": None,
    "fresh_runtime_session": None,
    "targetstatus_passed_after_at_least_ten_seconds": None,
    "observegeometry_completed_before_receipt_confirmation": None,
    "receipt_write_confirmed_before_f2": None,
    "exactly_one_f2_after_receipt_confirmation": None,
    "mineocclude_stop_aborted_during_warmup": None,
    "recording_never_started": None,
    "screenshot_from_same_session": None,
    "server_stopped_cleanly": None,
    "operator_identity_differs_from_first_operator": None,
    "authenticated_account_differs_from_first_operator": None,
    "notes": None,
}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git_blob(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


def dump(value: Any) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


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


def generated_identity(path: Path, data: bytes) -> dict[str, Any]:
    return {
        "path": path.relative_to(REPO).as_posix(),
        "size_bytes": len(data),
        "sha256": sha256(data),
    }


def find_line(lines: list[str], pattern: str, label: str) -> int:
    regex = re.compile(pattern)
    for index, line in enumerate(lines):
        if regex.search(line):
            return index
    raise ValueError(f"attempt-01 required event absent: {label}")


def line_seconds(line: str) -> int:
    match = re.match(r"\[(\d{2}):(\d{2}):(\d{2})\]", line)
    if not match:
        raise ValueError(f"log line has no timestamp: {line}")
    hour, minute, second = (int(value) for value in match.groups())
    return hour * 3600 + minute * 60 + second


def offset(base: int, event: int) -> int:
    return (event - base) % 86400


def validate_attempt_01() -> dict[str, Any]:
    for path, expected in ATTEMPT_01_HASHES.items():
        if not path.is_file() or identity(path)["sha256"] != expected:
            raise ValueError(f"attempt-01 evidence absent or drifted: {path}")
    if any(path.exists() for path in (ATTEMPT_01_CANONICAL, ATTEMPT_01_ATTESTATION, ATTEMPT_01_INGESTED)):
        raise ValueError("attempt-01 invalid evidence was finalized or certified after failure")

    receipt = json.loads(ATTEMPT_01_RECEIPT.read_text(encoding="utf-8-sig"))
    target = receipt.get("target", {})
    if not (
        receipt.get("receipt_id") == "c1_5_second_operator_attempt_01_layout_01"
        and receipt.get("episode_id") == 11502
        and receipt.get("layout_id") == "layout_01"
        and receipt.get("running") is True
        and receipt.get("capturing") is False
        and receipt.get("lifecycle_state") == "READY"
        and target.get("valid") is True
        and target.get("required") is True
        and target.get("tagged_target_count") == 1
        and target.get("problems") == []
    ):
        raise ValueError("attempt-01 geometry/target receipt does not match the established facts")
    observed_players = receipt.get("camera", {}).get("observed_players", [])
    if len(observed_players) != 1 or observed_players[0].get("name") != ATTEMPT_01_ACCOUNT:
        raise ValueError("attempt-01 observed account does not match Santa313")

    server = ATTEMPT_01_SERVER_LOG.read_text(encoding="utf-8", errors="replace").splitlines()
    client = ATTEMPT_01_CLIENT_LOG.read_text(encoding="utf-8", errors="replace").splitlines()
    armed = find_line(server, r"episode 11502 armed \(layout=layout_01, 12000 warmup \+ 20 record ticks", "armed")
    status = find_line(server, r"target status: valid=true required=true count=1.*episode=11502.*lifecycle=READY.*problems=NONE", "targetstatus")
    observed = find_line(server, r"wrote read-only geometry receipt .*c1_5_second_operator_attempt_01_layout_01\.json", "observegeometry completion")
    confirmed = find_line(server, r"Wrote observation-only geometry receipt: .*c1_5_second_operator_attempt_01_layout_01\.json", "receipt confirmation")
    aborted = find_line(server, r"episode 11502 aborted during warmup", "warmup abort")
    if not (armed < status < observed < confirmed < aborted):
        raise ValueError("attempt-01 server chronology mismatch")
    if any("episode 11502 recording started" in line for line in server):
        raise ValueError("attempt-01 unexpectedly entered recording")
    armed_seconds = line_seconds(server[armed])
    offsets = {
        "targetstatus": offset(armed_seconds, line_seconds(server[status])),
        "observegeometry_completed": offset(armed_seconds, line_seconds(server[observed])),
        "receipt_confirmation": offset(armed_seconds, line_seconds(server[confirmed])),
        "warmup_abort": offset(armed_seconds, line_seconds(server[aborted])),
    }
    screenshots: list[tuple[int, int, str]] = []
    for index, line in enumerate(client):
        match = re.search(r"Saved screenshot as ([^\\/\s]+\.png)", line)
        if match:
            screenshots.append((index, offset(armed_seconds, line_seconds(line)), match.group(1)))
    if len(screenshots) != 1 or screenshots[0][2] != ATTEMPT_01_RAW_SCREENSHOT.name:
        raise ValueError("attempt-01 screenshot event inventory mismatch")
    screenshot_line, screenshot_offset, screenshot_name = screenshots[0]
    if not (offsets["targetstatus"] >= 10 and screenshot_offset < offsets["receipt_confirmation"] < offsets["warmup_abort"]):
        raise ValueError("attempt-01 failure chronology is not screenshot-before-receipt")
    account = re.search(r"Setting user: ([A-Za-z0-9_]+)", "\n".join(client))
    if account is None or account.group(1) != ATTEMPT_01_ACCOUNT:
        raise ValueError("attempt-01 client account mismatch")
    return {
        "armed_line_index": armed,
        "target_status_line_index": status,
        "screenshot_line_index": screenshot_line,
        "observegeometry_completion_line_index": observed,
        "receipt_confirmation_line_index": confirmed,
        "warmup_abort_line_index": aborted,
        "armed_to_targetstatus_seconds": offsets["targetstatus"],
        "armed_to_screenshot_seconds": screenshot_offset,
        "armed_to_receipt_confirmation_seconds": offsets["receipt_confirmation"],
        "armed_to_warmup_abort_seconds": offsets["warmup_abort"],
        "screenshot_preceded_receipt_confirmation_seconds": offsets["receipt_confirmation"] - screenshot_offset,
        "screenshot_file_name": screenshot_name,
        "recording_started": False,
    }


def validate_candidate(schedule_data: bytes, *, allow_runtime_uninstalled: bool) -> dict[str, Any]:
    collisions: list[str] = []
    for path in (RETRY_RECEIPT, RETRY_SCREENSHOT, RETRY_ATTESTATION, RETRY_INGESTED, RETRY_SERVER_LOG, RETRY_CLIENT_LOG, RETRY_SERVER_OUTPUT, RETRY_CLIENT_OUTPUT):
        if path.exists():
            collisions.append(str(path.resolve()))
    repo_matches = list((REPO / "configs/collection").glob("**/episode_11506.jsonl"))
    unexpected_repo = [path for path in repo_matches if path.resolve() != REPO_SCHEDULE.resolve()]
    collisions.extend(str(path.resolve()) for path in unexpected_repo)
    if REPO_SCHEDULE.exists() and REPO_SCHEDULE.read_bytes() != schedule_data:
        collisions.append(f"drifted:{REPO_SCHEDULE.resolve()}")
    if RUNTIME_SCHEDULE.exists():
        if RUNTIME_SCHEDULE.read_bytes() != schedule_data:
            collisions.append(f"drifted:{RUNTIME_SCHEDULE.resolve()}")
    elif not allow_runtime_uninstalled:
        collisions.append(f"missing:{RUNTIME_SCHEDULE.resolve()}")
    if collisions:
        raise ValueError(f"attempt-02 collision/installation failures: {collisions}")
    return {
        "candidate_episode_id": RETRY_EPISODE_ID,
        "candidate_seed": RETRY_SEED,
        "repository_episode_name_unique": len(repo_matches) <= 1,
        "runtime_schedule_installed": RUNTIME_SCHEDULE.is_file(),
        "create_only_outputs_absent": True,
        "server_client_episode_outputs_absent": True,
        "collisions": [],
    }


def package_inventory(outputs: dict[Path, bytes]) -> bytes:
    rows = [
        generated_identity(path, data)
        for path, data in sorted(outputs.items(), key=lambda item: item[0].as_posix())
        if path.parent == DOC_DIR and path.name != "sha256_inventory.json"
    ]
    return dump({
        "schema_version": "person-c-package-sha256-inventory-v1.0",
        "self_excluded": "sha256_inventory.json",
        "files": rows,
    })


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--allow-runtime-uninstalled", action="store_true")
    args = parser.parse_args()

    if sha256(GEOMETRY.read_bytes()) != GEOMETRY_SHA256:
        raise ValueError("accepted geometry hash drift")
    if sha256(INSTALLED_JAR.read_bytes()) != JAR_SHA256:
        raise ValueError("installed MineOcclude JAR hash drift")
    chronology = validate_attempt_01()
    schedule_data = serialize_schedule(
        generate_noise_schedule(seed=RETRY_SEED, n_draws=RECORD_TICKS, q=0.0)
    )
    collision = validate_candidate(schedule_data, allow_runtime_uninstalled=args.allow_runtime_uninstalled)
    runtime_schedule = {
        "path": str(RUNTIME_SCHEDULE.resolve()),
        "size_bytes": len(schedule_data),
        "sha256": sha256(schedule_data),
        "installation_status": "INSTALLED_HASH_MATCH" if RUNTIME_SCHEDULE.is_file() else "PENDING_CREATE_ONLY_INSTALL",
    }

    failure_record = {
        "schema_version": "person-c-c1.5-independent-second-operator-attempt-01-failure-v0.1",
        "operator_role": "second",
        "attempt": 1,
        "episode_id": 11502,
        "seed": 202608031502,
        "classification": FAILURE_CLASSIFICATION,
        "status": "INVALID_FOR_C1_5_INGESTION",
        "targetstatus_passed": True,
        "target_retention_implementation_passed": True,
        "geometry_receipt_created": True,
        "episode_aborted_during_warmup": True,
        "recording_started": False,
        "reason": "The only F2 screenshot occurred approximately 12 seconds before the geometry receipt-written confirmation. The attempt is timing-invalid, not a target-retention failure.",
        "chronology": chronology,
        "observed_authenticated_account": ATTEMPT_01_ACCOUNT,
        "preservation": {
            "status": "PRESERVED_HASH_BOUND_NOT_CERTIFIED",
            "delete_rename_overwrite_edit_or_certify_forbidden": True,
            "canonical_screenshot_created": False,
            "attestation_created": False,
            "ingestion_output_created": False,
        },
        "files": {
            "geometry_receipt": identity(ATTEMPT_01_RECEIPT),
            "raw_f2_screenshot": identity(ATTEMPT_01_RAW_SCREENSHOT),
            "immutable_schedule": identity(ATTEMPT_01_SCHEDULE),
            "preserved_server_log": identity(ATTEMPT_01_SERVER_LOG),
            "preserved_client_log": identity(ATTEMPT_01_CLIENT_LOG),
            "canonical_screenshot_path_not_created": str(ATTEMPT_01_CANONICAL.resolve()),
            "attestation_path_not_created": str(ATTEMPT_01_ATTESTATION.resolve()),
            "ingested_path_not_created": str(ATTEMPT_01_INGESTED.resolve()),
        },
    }
    failure_bytes = dump(failure_record)
    failure_hash = sha256(failure_bytes)
    attestation = dict(ATTESTATION_TEMPLATE)
    attestation["attempt_01_failure_record_sha256"] = failure_hash
    attestation_bytes = dump(attestation)

    start_command = "mineocclude start layout_01 11506 202608031506 0.0 0.0 20"
    observe_command = "mineocclude observegeometry c1_5_second_operator_attempt_02_layout_01"
    finalization_command = (
        'powershell.exe -NoProfile -ExecutionPolicy Bypass -File '
        '"C:\\Users\\lollo\\MineOcclude-Person-C-C1-C6A\\scripts\\person_c\\finalize-c1-5-second-operator-attempt-02.ps1"'
    )
    ingestion_command = (
        'python scripts/person_c/ingest_c1_5_second_operator_attempt_02_runtime.py '
        f'--geometry-receipt "{RETRY_RECEIPT}" --screenshot "{RETRY_SCREENSHOT}" '
        f'--attestation "{RETRY_ATTESTATION}" --output "{RETRY_INGESTED}"'
    )
    schedule_manifest = {
        "schema_version": "person-c-c1.5-independent-second-operator-attempt-02-schedule-v0.1",
        "immutable": True,
        "episode_id": RETRY_EPISODE_ID,
        "seed": RETRY_SEED,
        "q": 0.0,
        "record_ticks": RECORD_TICKS,
        "repository_schedule": generated_identity(REPO_SCHEDULE, schedule_data),
        "runtime_schedule": runtime_schedule,
        "attempt_01_episode_reused": False,
    }
    manifest = {
        "schema_version": "person-c-c1.5-independent-second-operator-attempt-02-manifest-v0.1",
        "status": "READY_FOR_SAME_INDEPENDENT_SECOND_HUMAN",
        "runtime_executed_by_preparation": False,
        "source_commit": SOURCE_COMMIT,
        "attempt_01": {
            "classification": FAILURE_CLASSIFICATION,
            "failure_record": generated_identity(DOC_DIR / "attempt_01_failure_record.json", failure_bytes),
            "preserved_unchanged": True,
            "certified": False,
        },
        "operator_requirements": {
            "same_human_as_second_operator_attempt_01_required": True,
            "different_human_from_first_operator_required": True,
            "observed_attempt_01_account": ATTEMPT_01_ACCOUNT,
            "first_operator_id_forbidden": "lollo",
            "first_operator_account_forbidden": "overatedusername",
        },
        "accepted_geometry": repo_identity(GEOMETRY),
        "accepted_geometry_version": GEOMETRY_VERSION,
        "mineocclude_jar": {**identity(INSTALLED_JAR), "source_commit": RUNTIME_SOURCE_COMMIT},
        "retry": {
            "operator_role": "second",
            "attempt": 2,
            "episode_id": RETRY_EPISODE_ID,
            "seed": RETRY_SEED,
            "layout_id": "layout_01",
            "geometry_version": GEOMETRY_VERSION,
            "mode": "normal",
            "duration": 0,
            "reveal": 0,
            "impulse": [-1, 0],
            "lockcam": "on",
            "spawn_animals": False,
            "warmup_ticks": RETRY_WARMUP_TICKS,
            "observation_window_seconds": OBSERVATION_WINDOW_SECONDS,
            "record_ticks": RECORD_TICKS,
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
            "wait_at_least_seconds": 10,
            "target_status_command": "mineocclude targetstatus",
            "required_target_status": "valid=true required=true count=1 lifecycle=READY problems=NONE",
            "observe_command": observe_command,
            "required_receipt_confirmation": "Wrote observation-only geometry receipt",
            "stop_command": "mineocclude stop",
            "schedule": {**generated_identity(REPO_SCHEDULE, schedule_data), "runtime": runtime_schedule},
        },
        "runtime_paths": {
            "geometry_receipt": str(RETRY_RECEIPT.resolve()),
            "screenshot": str(RETRY_SCREENSHOT.resolve()),
            "attestation": str(RETRY_ATTESTATION.resolve()),
            "ingested_output": str(RETRY_INGESTED.resolve()),
            "server_log_archive": str(RETRY_SERVER_LOG.resolve()),
            "client_log_archive": str(RETRY_CLIENT_LOG.resolve()),
        },
        "strict_chronology_contract": [
            "episode_armed",
            "wait_at_least_10_seconds",
            "targetstatus_passes",
            "observegeometry_completes",
            "receipt_written_confirmation_appears",
            "exactly_one_f2_screenshot_after_receipt_confirmation",
            "mineocclude_stop_aborts_during_warmup",
            "recording_does_not_begin",
        ],
        "collision_audit": collision,
        "validator": repo_identity(VALIDATOR),
        "finalizer": repo_identity(FINALIZER),
        "ingestion_command": ingestion_command,
        "finalization_command": finalization_command,
    }
    instructions = f"""# Second operator attempt 02 — exact instructions

You must be the same second human who performed attempt 01, and you must remain a different human from the first operator. Use the same authenticated account `{ATTEMPT_01_ACCOUNT}`. Attempt 01 is preserved but invalid as `{FAILURE_CLASSIFICATION}`; do not edit or certify it.

1. Start a fresh isolated server/client session and connect to `127.0.0.1:25565`.
2. Run, in order: `mineocclude mode normal`; `mineocclude duration 0`; `mineocclude reveal 0`; `mineocclude impulse -1 0`; `mineocclude lockcam on`; `mineocclude warmup 12000`; `{start_command}`.
3. Wait at least 10 seconds after the episode-armed message.
4. Run `mineocclude targetstatus`. Continue only for `valid=true required=true count=1 lifecycle=READY problems=NONE`.
5. Run `{observe_command}`.
6. Wait until the server prints the receipt-written confirmation for `{RETRY_RECEIPT}`.
7. **Do not press F2 before that receipt-written confirmation.** After it appears, return to normal gameplay and press F2 exactly once.
8. Immediately run `mineocclude stop`. Require `episode 11506 aborted during warmup`.
9. If `episode 11506 recording started` appears, stop and report failure; do not finalize.
10. Quit the client and stop the server cleanly, preserving `logs\\latest.log` in both roots.
11. Run `{finalization_command}` and type `YES` only if you are the same attempt-01 second human and remain independent from the first operator.

The 12000-tick warmup is approximately 600 seconds. The receipt, F2 screenshot, and stop must all occur during warmup. All attempt-02 runtime output paths are create-only.
"""
    validation = {
        "schema_version": "person-c-c1.5-independent-second-operator-attempt-02-preparation-validation-v0.1",
        "status": "PASS" if RUNTIME_SCHEDULE.is_file() else "PENDING_RUNTIME_SCHEDULE_INSTALL",
        "attempt_01_preserved_hash_bound": True,
        "attempt_01_failure_classification": FAILURE_CLASSIFICATION,
        "retry_episode_seed_collision_free": True,
        "warmup_12000_bound_immediately_before_start": manifest["retry"]["ordered_start_commands"][-2] == "mineocclude warmup 12000",
        "strict_chronology_validator_ready": True,
        "create_only_guards_ready": True,
        "runtime_executed": False,
        "runtime_schedule_installed": RUNTIME_SCHEDULE.is_file(),
    }
    outputs: dict[Path, bytes] = {
        REPO_SCHEDULE: schedule_data,
        CONFIG_DIR / "retry_schedule_manifest.json": dump(schedule_manifest),
        DOC_DIR / "attempt_01_failure_record.json": failure_bytes,
        DOC_DIR / "attempt_02_manifest.json": dump(manifest),
        DOC_DIR / "second_operator_attempt_02_attestation.template.json": attestation_bytes,
        DOC_DIR / "SECOND_OPERATOR_ATTEMPT_02_INSTRUCTIONS.md": instructions.encode("utf-8"),
        DOC_DIR / "ingestion_command.json": dump({"command": ingestion_command}),
        DOC_DIR / "finalization_command.json": dump({"command": finalization_command}),
        DOC_DIR / "validation_report.json": dump(validation),
    }
    outputs[DOC_DIR / "sha256_inventory.json"] = package_inventory(outputs)
    for path, data in outputs.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    print(json.dumps({
        "status": validation["status"],
        "episode_id": RETRY_EPISODE_ID,
        "seed": RETRY_SEED,
        "schedule_sha256": sha256(schedule_data),
        "attempt_01_failure_record_sha256": failure_hash,
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
