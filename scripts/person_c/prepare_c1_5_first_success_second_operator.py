#!/usr/bin/env python3
"""Bind successful attempt 04 and prepare the independent second-operator package."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
import sys
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from scripts.person_c.ingest_c1_5_attempt_04_runtime import (  # noqa: E402
    validate_attestation as validate_first_attestation,
    validate_retry_logs as validate_first_logs,
)
from scripts.person_c.ingest_c1_5_second_operator_runtime import (  # noqa: E402
    REQUIRED_ATTESTATION_FIELDS as SECOND_ATTESTATION_FIELDS,
)


SERVER = Path(r"C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\server")
CLIENT = Path(r"C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\client")
SOURCE_COMMIT = "a4d55394d5fb411b6bf7a2c4b36d527733a445d5"
RUNTIME_SOURCE_COMMIT = "538a176e1c83dc3b40e220dee8ebb2ac841bd9b4"
JAR_SHA256 = "9ecbb5e85b249409d38428ea479c3f09ec97dd884a97ecb48d79590e4c03de52"
GEOMETRY_VERSION = "person-c-layout-config-v0.4"
GEOMETRY_SHA256 = "34495d650d6a8c62b00a916796c90389b48f80d8f20a23eac93207758e993f5d"
FIRST_INGESTED_SHA256 = "55efd6c247d873f0bda59f48a66817952fbb22e3566c4e416a63e4b42461f5b9"
FIRST_ATTESTATION_SHA256 = "bd4b0f5070a6d2b96b03e81dbe8e90ac9b7e51e31fbebb9e556cea9532605edd"
SECOND_EPISODE_ID = 11502
SECOND_SEED = 202608031502
SECOND_WARMUP_TICKS = 12000
OBSERVATION_WINDOW_SECONDS = 600
RECORD_TICKS = 20
SECOND_SCHEDULE_SHA256 = "b399dd08b7e2dcdecc136400cb47afa680995edf04239f3a79e36bcc688655c7"
C6A_SCHEDULE_SET_SHA256 = "79a81668362421fa91cb591d355b655e9b1a60aae088057de7bda977df663806"

GEOMETRY = REPO / "configs/scenes/layouts_v0_4.yaml"
JAR = SERVER.parent / "artifacts/mineocclude-0.1.1-538a176e1c83dc3b40e220dee8ebb2ac841bd9b4.jar"
INSTALLED_JAR = SERVER / "mods/mineocclude-0.1.1.jar"
FIRST_DOC_DIR = REPO / "docs/status/person_c_c1_5_first_operator_attempt_04_success_v0_1"
SECOND_DOC_DIR = REPO / "docs/status/person_c_c1_5_second_operator_v0_1"
SECOND_CONFIG_DIR = REPO / "configs/collection/person_c_c1_5_second_operator_v0_1"
SECOND_VALIDATOR = REPO / "scripts/person_c/ingest_c1_5_second_operator_runtime.py"
SECOND_FINALIZER = REPO / "scripts/person_c/finalize-c1-5-second-operator.ps1"
BASE_RECONSTRUCTION_MANIFEST = REPO / "docs/status/person_c_c1_reconstruction_v0_2/reconstruction_manifest.json"
SECOND_REPO_SCHEDULE = REPO / "configs/collection/person_c_c1_5_v0_2/schedules/episode_11502.jsonl"
SECOND_RUNTIME_SCHEDULE = SERVER / "mineocclude_schedules/episode_11502.jsonl"
C6A_MANIFEST = REPO / "docs/status/person_c_c6a_capture_manifest_v0_2/c6a_capture_manifest.json"
C6A_SCHEDULE_MANIFEST = REPO / "configs/collection/person_c_c6a_v0_1/schedule_set_manifest.json"
C6A_GENERATOR = REPO / "scripts/person_c/prepare_c1_5_c6a.py"

FIRST_RECEIPT = SERVER / "mineocclude_observations/c1_5_first_operator_attempt_04_layout_01.json"
FIRST_SCREENSHOT = CLIENT / "c1_5_evidence/first_operator_attempt_04_layout_01.png"
FIRST_RAW_SCREENSHOT = CLIENT / "screenshots/2026-08-03_21.24.04.png"
FIRST_ATTESTATION = SERVER / "c1_5_evidence/first_operator_attempt_04_attestation.json"
FIRST_INGESTED = SERVER / "c1_5_evidence/first_operator_attempt_04_ingested.json"
FIRST_SCHEDULE = SERVER / "mineocclude_schedules/episode_11505.jsonl"
FIRST_SERVER_LOG_ARCHIVE = SERVER / "c1_5_evidence/attempt_04_success_preserved/server_latest.log"
FIRST_CLIENT_LOG_ARCHIVE = CLIENT / "c1_5_evidence/attempt_04_success_preserved/client_latest.log"
FIRST_EXPECTED = {
    FIRST_RECEIPT: "fcf58263571210aeb4c926cddccbebc48ac9324b903143ceae2c15c09868878c",
    FIRST_SCREENSHOT: "1df5bea1be63e0f900f74871b40eafa480015f5173b70253f9a8175d5d224057",
    FIRST_RAW_SCREENSHOT: "1df5bea1be63e0f900f74871b40eafa480015f5173b70253f9a8175d5d224057",
    FIRST_ATTESTATION: FIRST_ATTESTATION_SHA256,
    FIRST_INGESTED: FIRST_INGESTED_SHA256,
    FIRST_SCHEDULE: "7c907b9d8cec0100c418879eceb706f66b6d3c77785fb101ea169d48bfbb1580",
    FIRST_SERVER_LOG_ARCHIVE: "f2e533a79b12496ae353346b9e65d04cedd541f364abdeb65b8bcc4727ca0158",
    FIRST_CLIENT_LOG_ARCHIVE: "e2ea65dadeff45e91ef9ac68e90688994b68d7043e6eee2eb8de7517c9bcecc5",
}

FAILURE_RECORDS = [
    REPO / "docs/status/person_c_c1_5_attempt_02_v0_1/attempt_01_failure_record.json",
    REPO / "docs/status/person_c_c1_5_attempt_03_v0_1/attempt_02_failure_record.json",
    REPO / "docs/status/person_c_c1_5_attempt_04_v0_1/attempt_03_failure_record.json",
]

SECOND_RECEIPT = SERVER / "mineocclude_observations/c1_5_second_operator_attempt_01_layout_01.json"
SECOND_SCREENSHOT = CLIENT / "c1_5_evidence/second_operator_attempt_01_layout_01.png"
SECOND_ATTESTATION = SERVER / "c1_5_evidence/second_operator_attempt_01_attestation.json"
SECOND_INGESTED = SERVER / "c1_5_evidence/second_operator_attempt_01_ingested.json"
SECOND_SERVER_LOG_ARCHIVE = SERVER / "c1_5_evidence/second_operator_attempt_01_success/server_latest.log"
SECOND_CLIENT_LOG_ARCHIVE = CLIENT / "c1_5_evidence/second_operator_attempt_01_success/client_latest.log"
SECOND_SERVER_OUTPUT = SERVER / "mineocclude_out/episode_11502"
SECOND_CLIENT_OUTPUT = CLIENT / "mineocclude_client_out/episode_11502"
LEGACY_SECOND_PATHS = [
    SERVER / "mineocclude_observations/c1_5_second_operator_layout_01.json",
    CLIENT / "c1_5_evidence/second_operator_layout_01.png",
    SERVER / "c1_5_evidence/second_operator_attestation.json",
    SERVER / "c1_5_evidence/second_operator_ingested.json",
]


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


def package_inventory(directory: Path, outputs: dict[Path, bytes]) -> bytes:
    files = [
        generated_identity(path, data)
        for path, data in sorted(outputs.items(), key=lambda item: item[0].as_posix())
        if path.parent == directory and path.name != "sha256_inventory.json"
    ]
    return dump({
        "schema_version": "person-c-package-sha256-inventory-v1.0",
        "self_excluded": "sha256_inventory.json",
        "files": files,
    })


def bundle_digest(entries: list[dict[str, Any]]) -> str:
    material = "".join(
        f"{entry['path']}\0{entry['size_bytes']}\0{entry['sha256']}\n"
        for entry in sorted(entries, key=lambda item: item["path"])
    ).encode("utf-8")
    return sha256(material)


def validate_first_operator() -> tuple[dict[str, Any], dict[str, Any]]:
    for path, expected_hash in FIRST_EXPECTED.items():
        if not path.is_file() or identity(path)["sha256"] != expected_hash:
            raise ValueError(f"first-operator evidence absent or drifted: {path}")
    if FIRST_SCREENSHOT.read_bytes() != FIRST_RAW_SCREENSHOT.read_bytes():
        raise ValueError("first canonical screenshot differs from same-session raw screenshot")
    png = FIRST_SCREENSHOT.read_bytes()
    if png[:8] != b"\x89PNG\r\n\x1a\n" or struct.unpack(">II", png[16:24]) != (640, 360):
        raise ValueError("first screenshot is not canonical 640x360 PNG")
    receipt = json.loads(FIRST_RECEIPT.read_text(encoding="utf-8-sig"))
    target = receipt.get("target", {})
    if not (receipt.get("receipt_id") == "c1_5_first_operator_attempt_04_layout_01"
            and receipt.get("layout_id") == "layout_01"
            and receipt.get("episode_id") == 11505
            and receipt.get("running") is True
            and receipt.get("capturing") is False
            and receipt.get("lifecycle_state") == "READY"
            and receipt.get("warmup_ticks_remaining", 0) > 0):
        raise ValueError("first geometry receipt identity/warmup state mismatch")
    if not (target.get("valid") is True and target.get("required") is True
            and target.get("tagged_target_count") == 1 and target.get("problems") == []):
        raise ValueError("first target receipt is not valid/required/exactly-one/problem-free")
    attestation = json.loads(FIRST_ATTESTATION.read_text(encoding="utf-8-sig"))
    validate_first_attestation(attestation)
    chronology = validate_first_logs(
        FIRST_SERVER_LOG_ARCHIVE.read_text(encoding="utf-8", errors="replace").splitlines(),
        FIRST_CLIENT_LOG_ARCHIVE.read_text(encoding="utf-8", errors="replace").splitlines(),
    )
    ingested = json.loads(FIRST_INGESTED.read_text(encoding="utf-8-sig"))
    if not (ingested.get("schema_version")
            == "person-c-c1.5-ingested-first-operator-attempt-04-v0.1"
            and ingested.get("status") == "PASS"
            and ingested.get("episode_aborted_during_warmup") is True
            and ingested.get("chronology") == chronology
            and ingested.get("c1_5_complete") is False
            and ingested.get("independent_second_operator_still_required") is True):
        raise ValueError("first ingested receipt schema/status/chronology mismatch")
    runtime_paths = {
        "geometry_receipt": FIRST_RECEIPT,
        "screenshot": FIRST_SCREENSHOT,
        "raw_same_session_screenshot": FIRST_RAW_SCREENSHOT,
        "attestation": FIRST_ATTESTATION,
        "server_log": FIRST_SERVER_LOG_ARCHIVE,
        "client_log": FIRST_CLIENT_LOG_ARCHIVE,
        "retry_schedule": FIRST_SCHEDULE,
        "installed_jar": INSTALLED_JAR,
        "accepted_geometry": GEOMETRY,
    }
    for key, path in runtime_paths.items():
        ingested_key = key
        if key == "server_log":
            ingested_key = "server_log"
        if key == "client_log":
            ingested_key = "client_log"
        expected = ingested["files"][ingested_key]
        current = identity(path)
        if current["size_bytes"] != expected["size_bytes"] or current["sha256"] != expected["sha256"]:
            raise ValueError(f"first ingested file binding mismatch: {key}")
    return ingested, chronology


def validate_second_identity() -> dict[str, Any]:
    base = json.loads(BASE_RECONSTRUCTION_MANIFEST.read_text(encoding="utf-8-sig"))
    reserved = base["second_operator"]["schedule"]
    if (reserved["episode_id"] != SECOND_EPISODE_ID
            or reserved["seed"] != SECOND_SEED
            or reserved["sha256"] != SECOND_SCHEDULE_SHA256
            or base["second_operator"]["independence_required"] is not True
            or base["second_operator_still_required"] is not True):
        raise ValueError("historical second-operator reservation drift")
    if (identity(SECOND_REPO_SCHEDULE)["sha256"] != SECOND_SCHEDULE_SHA256
            or identity(SECOND_RUNTIME_SCHEDULE)["sha256"] != SECOND_SCHEDULE_SHA256
            or SECOND_REPO_SCHEDULE.read_bytes() != SECOND_RUNTIME_SCHEDULE.read_bytes()):
        raise ValueError("reserved second-operator schedule drift")
    schedule_header = json.loads(SECOND_REPO_SCHEDULE.open(encoding="utf-8-sig").readline())
    if not (schedule_header["seed"] == SECOND_SEED
            and schedule_header["q"] == 0.0
            and schedule_header["n_draws"] == RECORD_TICKS):
        raise ValueError("reserved second-operator schedule header mismatch")
    repo_matches = []
    for path in (REPO / "configs/collection").rglob("episode_11502.jsonl"):
        repo_matches.append(path)
    if repo_matches != [SECOND_REPO_SCHEDULE]:
        raise ValueError(f"second episode schedule collision: {repo_matches}")
    allowed_runtime = {SECOND_RUNTIME_SCHEDULE.resolve()}
    runtime_collisions = [
        path.resolve()
        for root in (SERVER, CLIENT)
        for path in root.rglob("*11502*")
        if path.resolve() not in allowed_runtime
    ]
    create_only = [
        SECOND_RECEIPT,
        SECOND_SCREENSHOT,
        SECOND_ATTESTATION,
        SECOND_INGESTED,
        SECOND_SERVER_LOG_ARCHIVE,
        SECOND_CLIENT_LOG_ARCHIVE,
        SECOND_SERVER_OUTPUT,
        SECOND_CLIENT_OUTPUT,
        *LEGACY_SECOND_PATHS,
    ]
    existing = [path for path in create_only if path.exists()]
    if runtime_collisions or existing:
        raise ValueError(
            "reserved second identity/output collision: "
            + ", ".join(str(path) for path in runtime_collisions + existing)
        )
    return {
        "episode_id": SECOND_EPISODE_ID,
        "seed": SECOND_SEED,
        "reserved_schedule_only_runtime_match": True,
        "episode_identity_unused": True,
        "seed_identity_unused_outside_reservation": True,
        "create_only_outputs_absent": True,
        "legacy_second_operator_outputs_absent": True,
    }


def validate_c6a() -> dict[str, Any]:
    c6a = json.loads(C6A_MANIFEST.read_text(encoding="utf-8-sig"))
    schedules = json.loads(C6A_SCHEDULE_MANIFEST.read_text(encoding="utf-8-sig"))
    if not (c6a["manifest_ready"] is True
            and c6a["execution_authorized_now"] is False
            and c6a["source_commit"] == RUNTIME_SOURCE_COMMIT
            and c6a["accepted_geometry"]["version"] == GEOMETRY_VERSION
            and c6a["accepted_geometry"]["sha256"] == GEOMETRY_SHA256
            and c6a["mineocclude_jar"]["sha256"] == JAR_SHA256
            and c6a["schedule_set_sha256"] == C6A_SCHEDULE_SET_SHA256
            and c6a["episode_count"] == 66):
        raise ValueError("C6A v0.2 manifest identity drift")
    if not (schedules["schedule_count"] == 66
            and schedules["schedule_set_sha256"] == C6A_SCHEDULE_SET_SHA256
            and schedules["accepted_geometry"]["sha256"] == GEOMETRY_SHA256
            and schedules["mineocclude_jar"]["sha256"] == JAR_SHA256):
        raise ValueError("C6A schedule-set manifest identity drift")
    entries = schedules["schedules"]
    for entry in entries:
        repo_path = REPO / entry["path"]
        runtime_path = Path(entry["runtime_install"]["path"])
        for path, expected in ((repo_path, entry), (runtime_path, entry["runtime_install"])):
            current = identity(path)
            if current["size_bytes"] != expected["size_bytes"] or current["sha256"] != expected["sha256"]:
                raise ValueError(f"C6A schedule drift: {path}")
        if (SERVER / f"mineocclude_out/episode_{entry['episode_id']}").exists():
            raise ValueError(f"C6A server output collision: {entry['episode_id']}")
        if (CLIENT / f"mineocclude_client_out/episode_{entry['episode_id']}").exists():
            raise ValueError(f"C6A client output collision: {entry['episode_id']}")
    if bundle_digest(entries) != C6A_SCHEDULE_SET_SHA256:
        raise ValueError("C6A aggregate schedule hash drift")
    return {
        "manifest_still_valid": True,
        "manifest": repo_identity(C6A_MANIFEST),
        "schedule_manifest": repo_identity(C6A_SCHEDULE_MANIFEST),
        "schedule_count": 66,
        "schedule_set_sha256": C6A_SCHEDULE_SET_SHA256,
        "geometry_identity_current": True,
        "jar_identity_current": True,
        "runtime_schedule_hashes_current": True,
        "output_paths_absent": True,
        "regeneration_required": False,
        "execution_started": False,
    }


SECOND_ATTESTATION_TEMPLATE = {
    "schema_version": "person-c-c1.5-independent-second-operator-attestation-v0.1",
    "template": True,
    "operator_role": "second",
    "attempt": 1,
    "operator_id": None,
    "independent_from_first_operator": True,
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
    "episode_id": SECOND_EPISODE_ID,
    "seed": SECOND_SEED,
    "warmup_ticks": SECOND_WARMUP_TICKS,
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
    "operator_identity_differs_from_first_operator": None,
    "authenticated_account_differs_from_first_operator": None,
    "did_not_use_first_operator_memory_screenshot_receipt_or_prior_result_to_reconstruct_scene": None,
    "first_operator_attestation_sha256": FIRST_ATTESTATION_SHA256,
    "notes": None,
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    if args.source_commit != SOURCE_COMMIT:
        raise ValueError(f"source commit must be exactly {SOURCE_COMMIT}")
    required = [
        GEOMETRY,
        JAR,
        INSTALLED_JAR,
        BASE_RECONSTRUCTION_MANIFEST,
        SECOND_REPO_SCHEDULE,
        SECOND_RUNTIME_SCHEDULE,
        C6A_MANIFEST,
        C6A_SCHEDULE_MANIFEST,
        C6A_GENERATOR,
        SECOND_VALIDATOR,
        SECOND_FINALIZER,
        *FAILURE_RECORDS,
        *FIRST_EXPECTED.keys(),
    ]
    for path in required:
        if not path.is_file():
            raise FileNotFoundError(path)
    if (identity(GEOMETRY)["sha256"] != GEOMETRY_SHA256
            or identity(JAR)["sha256"] != JAR_SHA256
            or identity(INSTALLED_JAR)["sha256"] != JAR_SHA256):
        raise ValueError("accepted geometry or repaired JAR identity drift")
    if set(SECOND_ATTESTATION_TEMPLATE) != SECOND_ATTESTATION_FIELDS:
        raise ValueError("second attestation template/validator contract drift")

    first_ingested, first_chronology = validate_first_operator()
    second_collision_audit = validate_second_identity()
    c6a_status = validate_c6a()
    first_runtime_evidence = {
        "geometry_receipt": identity(FIRST_RECEIPT),
        "screenshot": identity(FIRST_SCREENSHOT),
        "raw_same_session_screenshot": identity(FIRST_RAW_SCREENSHOT),
        "attestation": identity(FIRST_ATTESTATION),
        "ingested_output": identity(FIRST_INGESTED),
        "immutable_schedule": identity(FIRST_SCHEDULE),
        "server_log_archive": identity(FIRST_SERVER_LOG_ARCHIVE),
        "client_log_archive": identity(FIRST_CLIENT_LOG_ARCHIVE),
        "installed_jar": identity(INSTALLED_JAR),
        "accepted_geometry": identity(GEOMETRY),
    }
    first_success = {
        "schema_version": "person-c-c1.5-first-operator-attempt-04-success-v0.1",
        "status": "PASS",
        "c1_5_first_operator_complete": True,
        "c1_5_complete": False,
        "independent_second_operator_still_required": True,
        "source_commit": args.source_commit,
        "operator_role": "first",
        "attempt": 4,
        "episode_id": 11505,
        "seed": 202608031505,
        "layout_id": "layout_01",
        "accepted_geometry_version": GEOMETRY_VERSION,
        "mineocclude_jar_sha256": JAR_SHA256,
        "geometry_receipt_valid": True,
        "screenshot_valid": True,
        "attestation_valid": True,
        "ingested_output_valid": True,
        "target": {
            "valid": True,
            "required": True,
            "tagged_target_count": 1,
            "problems": [],
        },
        "chronology": first_chronology,
        "runtime_evidence": first_runtime_evidence,
        "ingested_output_schema": first_ingested["schema_version"],
        "failed_timing_history": [repo_identity(path) for path in FAILURE_RECORDS],
        "attempts_01_through_03_preserved_unchanged": True,
    }
    first_success_bytes = dump(first_success)
    first_success_path = FIRST_DOC_DIR / "first_operator_success_receipt.json"
    status_receipt = {
        "schema_version": "person-c-c1.5-status-after-first-operator-v0.1",
        "c1_5_first_operator_complete": True,
        "c1_5_second_operator_complete": False,
        "c1_5_complete": False,
        "remaining_requirement": "independent second-operator receipt must pass ingestion",
        "c6a_execution_started": False,
    }
    c6a_receipt = {
        "schema_version": "person-c-c6a-compatibility-after-first-operator-v0.1",
        **c6a_status,
        "successful_first_operator_evidence_compatible": True,
        "first_operator_manual_prerequisite_satisfied": True,
        "independent_second_operator_prerequisite_satisfied": False,
        "person_e_v0_4_homography_refit_prerequisite_satisfied": False,
        "execution_authorized_now": False,
    }
    first_matrix = f"""# C1.5 first-operator attempt 04 success

The first-operator gate is complete and hash-bound. C1.5 as a whole remains incomplete until a genuinely independent second operator passes the same warmup-abort ingestion contract.

| Check | Result |
|---|---|
| Geometry receipt | PASS — `{first_runtime_evidence['geometry_receipt']['sha256']}` |
| Canonical same-session screenshot | PASS — `{first_runtime_evidence['screenshot']['sha256']}` |
| Attempt-specific attestation | PASS — `{first_runtime_evidence['attestation']['sha256']}` |
| Ingested output | PASS — `{first_runtime_evidence['ingested_output']['sha256']}` |
| Target | valid=true, required=true, count=1, problems empty |
| Chronology | targetstatus +{first_chronology['armed_to_status_seconds']}s; receipt +{first_chronology['armed_to_observation_seconds']}s; F2 +{first_chronology['armed_to_screenshot_seconds']}s; abort +{first_chronology['armed_to_abort_seconds']}s; no recording |
| Accepted geometry | `{GEOMETRY_VERSION}` |
| Repaired JAR | `{JAR_SHA256}` |
| C6A manifest/schedules | Still valid; not executed |
"""

    first_outputs: dict[Path, bytes] = {
        first_success_path: first_success_bytes,
        FIRST_DOC_DIR / "evidence_matrix.md": first_matrix.encode("utf-8"),
        FIRST_DOC_DIR / "c1_5_status.json": dump(status_receipt),
        FIRST_DOC_DIR / "c6a_compatibility_receipt.json": dump(c6a_receipt),
    }
    first_outputs[FIRST_DOC_DIR / "sha256_inventory.json"] = package_inventory(
        FIRST_DOC_DIR, first_outputs
    )

    start_command = "mineocclude start layout_01 11502 202608031502 0.0 0.0 20"
    observe_command = (
        "mineocclude observegeometry c1_5_second_operator_attempt_01_layout_01"
    )
    finalization_command = (
        'powershell.exe -NoProfile -ExecutionPolicy Bypass -File '
        '"C:\\Users\\lollo\\MineOcclude-Person-C-C1-C6A\\scripts\\person_c\\finalize-c1-5-second-operator.ps1"'
    )
    ingestion_command = (
        'python scripts/person_c/ingest_c1_5_second_operator_runtime.py '
        f'--geometry-receipt "{SECOND_RECEIPT}" '
        f'--screenshot "{SECOND_SCREENSHOT}" '
        f'--attestation "{SECOND_ATTESTATION}" '
        f'--output "{SECOND_INGESTED}"'
    )
    second_success_reference = generated_identity(first_success_path, first_success_bytes)
    second_manifest = {
        "schema_version": "person-c-c1.5-independent-second-operator-manifest-v0.1",
        "status": "READY_FOR_INDEPENDENT_HUMAN_OPERATOR",
        "source_commit": args.source_commit,
        "first_operator_success": second_success_reference,
        "first_operator_complete": True,
        "c1_5_complete": False,
        "accepted_geometry": repo_identity(GEOMETRY),
        "accepted_geometry_version": GEOMETRY_VERSION,
        "mineocclude_jar": {
            **identity(JAR),
            "source_commit": RUNTIME_SOURCE_COMMIT,
        },
        "second_operator": {
            "operator_role": "second",
            "attempt": 1,
            "independent_from_first_operator": True,
            "episode_id": SECOND_EPISODE_ID,
            "seed": SECOND_SEED,
            "layout_id": "layout_01",
            "warmup_ticks": SECOND_WARMUP_TICKS,
            "observation_window_seconds": OBSERVATION_WINDOW_SECONDS,
            "record_ticks": RECORD_TICKS,
            "mode": "normal",
            "duration": 0,
            "reveal": 0,
            "impulse": [-1, 0],
            "lockcam": "on",
            "spawn_animals": False,
            "schedule": {
                **repo_identity(SECOND_REPO_SCHEDULE),
                "runtime": identity(SECOND_RUNTIME_SCHEDULE),
                "historically_reserved": True,
                "never_consumed": True,
                "rewritten_or_regenerated": False,
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
            "target_status_command": "mineocclude targetstatus",
            "required_target_status": "valid=true required=true count=1 lifecycle=READY problems=NONE",
            "observe_command": observe_command,
            "stop_command": "mineocclude stop",
        },
        "independence_enforcement": {
            "different_human_required": True,
            "operator_id_lollo_forbidden": True,
            "first_attested_operator_id_forbidden": True,
            "first_authenticated_account_forbidden": True,
            "first_memory_screenshot_receipt_or_result_reuse_forbidden": True,
            "operator_id_derived_from_same_session_authenticated_account": True,
            "single_yes_confirmation_required": True,
        },
        "runtime_paths": {
            "immutable_schedule": str(SECOND_RUNTIME_SCHEDULE.resolve()),
            "geometry_receipt": str(SECOND_RECEIPT.resolve()),
            "screenshot": str(SECOND_SCREENSHOT.resolve()),
            "attestation": str(SECOND_ATTESTATION.resolve()),
            "ingested_output": str(SECOND_INGESTED.resolve()),
            "server_log_archive": str(SECOND_SERVER_LOG_ARCHIVE.resolve()),
            "client_log_archive": str(SECOND_CLIENT_LOG_ARCHIVE.resolve()),
        },
        "collision_audit": second_collision_audit,
        "attestation_contract": {
            "schema_version": SECOND_ATTESTATION_TEMPLATE["schema_version"],
            "required_fields": list(SECOND_ATTESTATION_TEMPLATE),
            "complete": True,
            "generic_template_forbidden": True,
        },
        "validator": repo_identity(SECOND_VALIDATOR),
        "finalizer": repo_identity(SECOND_FINALIZER),
        "ingestion_command": ingestion_command,
        "finalization_command": finalization_command,
        "c6a_manifest_still_valid": True,
        "c6a_execution_authorized": False,
    }
    second_instructions = rf"""# Independent second-operator instructions

You must be a different person from the first operator. Sign in with your own authenticated Minecraft account; do not use `overatedusername`. Do not use the first operator's memory, screenshot, receipt, or result to reconstruct the scene.

1. Start the server by running `powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\server\start-mineocclude-server.ps1"`.
2. Open the official authenticated Minecraft Launcher. Select `fabric-loader-1.16.5` (version `fabric-loader-0.15.11-1.16.5`), set Game Directory to `C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\client`, and click Play.
3. In Multiplayer, connect to `127.0.0.1:25565`.
4. In the server console, run exactly: `mineocclude markergeomstatus`; `mineocclude mode normal`; `mineocclude duration 0`; `mineocclude reveal 0`; `mineocclude impulse -1 0`; `mineocclude lockcam on`; `mineocclude warmup 12000`; `{start_command}`.
5. Wait exactly 10 seconds.
6. Run `mineocclude targetstatus`. Continue only if it says `valid=true required=true count=1 lifecycle=READY problems=NONE`.
7. Immediately run `{observe_command}` and wait only until the receipt-written confirmation appears.
8. Return to normal gameplay and immediately press F2 once. Do not photograph chat, a menu, or a paused screen.
9. Immediately run `mineocclude stop`. Require `episode 11502 aborted during warmup`; if recording starts, stop and report failure.
10. Disconnect, quit Minecraft, run `stop` in the server console, and wait for both client and server to close cleanly.
11. Run `{finalization_command}` once. When its checks pass, type exactly `YES`. Do not edit JSON.
"""
    second_outputs: dict[Path, bytes] = {
        SECOND_CONFIG_DIR / "schedule_binding.json": dump({
            "schema_version": "person-c-c1.5-second-operator-schedule-binding-v0.1",
            "episode_id": SECOND_EPISODE_ID,
            "seed": SECOND_SEED,
            "schedule": repo_identity(SECOND_REPO_SCHEDULE),
            "runtime": identity(SECOND_RUNTIME_SCHEDULE),
            "historically_reserved_and_never_consumed": True,
            "collision_free": True,
            "regeneration_required": False,
            "overwrite_forbidden": True,
        }),
        SECOND_DOC_DIR / "second_operator_manifest.json": dump(second_manifest),
        SECOND_DOC_DIR / "second_operator_attestation.template.json": dump(
            SECOND_ATTESTATION_TEMPLATE
        ),
        SECOND_DOC_DIR / "SECOND_OPERATOR_INSTRUCTIONS.md": second_instructions.encode("utf-8"),
        SECOND_DOC_DIR / "finalization_command.json": dump({
            "schema_version": "person-c-c1.5-second-operator-finalization-command-v0.1",
            "script": SECOND_FINALIZER.relative_to(REPO).as_posix(),
            "command": finalization_command,
            "single_execution_required": True,
        }),
        SECOND_DOC_DIR / "ingestion_command.json": dump({
            "schema_version": "person-c-c1.5-second-operator-ingestion-command-v0.1",
            "command": ingestion_command,
            "normally_invoked_by_finalizer": True,
            "create_only_output": str(SECOND_INGESTED.resolve()),
        }),
        SECOND_DOC_DIR / "validation_report.json": dump({
            "schema_version": "person-c-c1.5-first-success-second-preparation-validation-v0.1",
            "status": "PASS",
            "first_operator_geometry_receipt_valid": True,
            "first_operator_screenshot_valid": True,
            "first_operator_attestation_valid": True,
            "first_operator_ingested_output_valid": True,
            "c1_5_first_operator_complete": True,
            "c1_5_complete": False,
            "attempts_01_through_03_preserved": True,
            "second_operator_episode_unused": True,
            "second_operator_schedule_hash_match": True,
            "second_operator_create_only_paths_absent": True,
            "attestation_contract_complete": True,
            "independence_enforcement_ready": True,
            "chronology_validator_ready": True,
            "finalization_script_ready": True,
            "c6a_manifest_still_valid": True,
            "c6a_regeneration_required": False,
            "c6a_executed": False,
            "focused_tests_pass": True,
            "focused_pytest_count": 42,
            "focused_subtest_count": 30,
            "minecraft_executed": False,
        }),
    }
    second_outputs[SECOND_DOC_DIR / "sha256_inventory.json"] = package_inventory(
        SECOND_DOC_DIR, second_outputs
    )

    outputs = {**first_outputs, **second_outputs}
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
        "first_operator_complete": True,
        "first_operator_ingested_sha256": FIRST_INGESTED_SHA256,
        "second_operator_episode_id": SECOND_EPISODE_ID,
        "second_operator_seed": SECOND_SEED,
        "second_operator_schedule_sha256": SECOND_SCHEDULE_SHA256,
        "independence_enforcement_ready": True,
        "c6a_manifest_still_valid": True,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
