#!/usr/bin/env python3
"""Autonomous, resumable P3 sequential development qualification.

The frozen P3 authority makes candidate progression mechanical.  This program
therefore owns the complete C01 -> optional C02 -> optional C03 state machine:
fresh calibration, paired NORMAL/NO_WALL capture, non-neural gates, layer-4
extraction, frozen BEST-K/FULL readouts, and terminal adjudication.  It stops
before launching a later candidate whenever an earlier candidate qualifies.

Large artifacts live on NVMe and are copied to the prospectively isolated P3
S3 prefix with checksum/receipt readback.  Compact progress and append-only
events live beside the frozen authority.  A completed durable unit is never
recollected or re-extracted after restart.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from PIL import Image

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "src"))

from mineocclude.regime_a_first25_analysis import scalar_metrics  # noqa: E402
from mineocclude.vision.magenta import HsvRange, detect_magenta  # noqa: E402
from scripts.run_regime_a import detector_rgb_rows, project_world_to_coordinates  # noqa: E402
from p2_common import (  # noqa: E402
    BRANCH,
    CaptureSession,
    sha256_file,
    write_json,
)
from p2c_capture import package as package_capture  # noqa: E402
from p2c_capture import verify_renderer_identity  # noqa: E402
from mineocclude.prospective.activation_binding import (  # noqa: E402
    TARGET_ROWS_NOT_AUTHORITY_BOUND,
)
from p2d_extract import Layer4Extractor  # noqa: E402
from p2e_analyze import best_k_readout, full_readout  # noqa: E402

OUT = REPO / "docs/status/integration/regime_a_prime_qualification_v0_1"
AUTHORITY_PATH = OUT / "p3_preoutcome_authority.json"
MANIFEST_PATH = OUT / "p3_development_manifest.json"
VALIDATION_PATH = OUT / "p3_authority_validation_receipt.json"
AUTHORITY_SHA256 = "bd391bd6f1bae0c90ea1ae74ee60c1315c5a3a171a91f98df14098e4232c9e23"
MANIFEST_SHA256 = "bb74f9ae761647e49cddf24f334bd1329843304259643688f6735029170f6b32"
AUTHORITY_HEAD = "e56d90b3da11966e30119dc0efe39fa3b13f1b5c"

WORK = Path("/mnt/sagemaker-nvme/p3_sequential_development_v0_1")
CAPTURES = WORK / "captures"
CALIBRATIONS = WORK / "calibrations"
ACTIVATIONS = WORK / "activations"
LOGS = WORK / "logs"
PROGRESS = OUT / "p3_progress.json"
EVENTS = OUT / "p3_events.jsonl"
PID_FILE = OUT / "p3_controller.pid"
TERMINAL = OUT / "p3_terminal_result.json"
S3_PREFIX = (
    "s3://sagemaker-us-east-1-323206973672/mineocclude/"
    "regime_a_prime_qualification_v0_1/p3_sequential_development_v0_1"
)
MINEWORLD_PYTHON = Path("/home/sagemaker-user/.conda/envs/mineworld/bin/python")
DETECTOR_CONFIG = REPO / (
    "docs/status/person_e_phase3_step3_1_candidate_freeze_v0_1/"
    "detector_candidate_config.json"
)
HOMOGRAPHY = REPO / (
    "data/handoff_e/person_e_v0_4_homography_refit_v0_2/"
    "layout_01_homography.json"
)
MOD_SOURCE = REPO / (
    "fabric/mineocclude-mod/src/main/java/com/mineocclude/server/"
    "MineOccludeServer.java"
)
SERVER_MOD = Path("/home/sagemaker-user/mineocclude-server/mods/mineocclude-0.1.1.jar")
MOD_SOURCE_SHA256 = "3c37227654415956ab34a0c3245fe25697ed8c2b8d18dcbca7373a21f5c32de0"
SERVER_MOD_SHA256 = "febf31cad7c6de003a6d2d87ed9183c6a6739e086e293b30e92999520e3bfaba"
MAX_ATTEMPTS = 3
LAYER = 4


def utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def canonical_sha256(value: Any) -> str:
    data = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(data.encode()).hexdigest()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, allow_nan=False) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    tmp.replace(path)


def append_event(candidate: str | None, stage: str, event: str, status: str, **extra: Any) -> None:
    row = {"timestamp": utc(), "candidate": candidate, "stage": stage,
           "event": event, "status": status, **extra}
    EVENTS.parent.mkdir(parents=True, exist_ok=True)
    with EVENTS.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True, allow_nan=False) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def subprocess_ok(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kwargs)
    if result.returncode:
        err = result.stderr.decode() if isinstance(result.stderr, bytes) else result.stderr
        raise RuntimeError(f"command failed ({result.returncode}): {' '.join(command)}: {err[-500:]}")
    return result


def base_progress() -> dict[str, Any]:
    return {
        "artifact_id": "regime-a-prime-p3-sequential-progress-v0.1",
        "p3_status": "NOT_STARTED",
        "current_candidate": None,
        "current_candidate_speed": None,
        "current_stage": "preflight",
        "total_candidates": 3,
        "selected_candidate": None,
        "stopping_rule_triggered": False,
        "candidate_capture_expected": 50,
        "candidate_capture_complete": 0,
        "candidate_capture_failed": 0,
        "current_run_id": None,
        "last_completed_run_id": None,
        "candidate_extraction_expected": 50,
        "candidate_extraction_complete": 0,
        "candidate_extraction_failed": 0,
        "path_status": "NOT_REACHED",
        "visibility_status": "NOT_REACHED",
        "headroom_status": "NOT_REACHED",
        "extraction_status": "NOT_REACHED",
        "best_k_status": "NOT_REACHED",
        "full_status": "NOT_REACHED",
        "qualification_status": "NOT_REACHED",
        "next_candidate_authorized": "P3DEV_C01",
        "remaining_candidate_count": 3,
        "last_error_code": None,
        "heartbeat_utc": utc(),
        "capture_retries": 0,
        "extraction_retries": 0,
        "hard_failures": 0,
        "gpu_used": False,
        "layers_extracted": [],
        "autonomous_p3_used": True,
        "codex_active_interventions": 1,
        "p3_confirmatory_membership": False,
        "p4_started": False,
        "REGIME_A_PRIME_COLLECTION_AUTHORIZED": "NO",
        "contamination_detected": False,
        "candidate_history": [],
        "controller_pid": os.getpid(),
        "controller_log": str(LOGS / "p3_controller.log"),
        "progress_file": str(PROGRESS),
        "event_ledger": str(EVENTS),
    }


class State:
    def __init__(self) -> None:
        self.data = read_json(PROGRESS) if PROGRESS.exists() else base_progress()
        self.data["controller_pid"] = os.getpid()

    def update(self, **values: Any) -> None:
        self.data.update(values)
        self.data["heartbeat_utc"] = utc()
        write_json(PROGRESS, self.data)

    def candidate_reset(self, candidate: dict[str, Any], index: int) -> None:
        cid = candidate["candidate_id"]
        self.update(
            p3_status="RUNNING",
            current_candidate=cid,
            current_candidate_speed=candidate["motion_parameter"]["speed_blocks_per_second"],
            current_stage="calibration",
            candidate_capture_expected=50,
            candidate_capture_complete=capture_complete_count(cid),
            candidate_capture_failed=0,
            current_run_id=None,
            candidate_extraction_expected=50,
            candidate_extraction_complete=extraction_complete_count(cid),
            candidate_extraction_failed=0,
            path_status="NOT_REACHED",
            visibility_status="NOT_REACHED",
            headroom_status="NOT_REACHED",
            extraction_status="NOT_REACHED",
            best_k_status="NOT_REACHED",
            full_status="NOT_REACHED",
            qualification_status="NOT_REACHED",
            next_candidate_authorized=None,
            remaining_candidate_count=3 - index,
        )


def validate_authority() -> tuple[dict[str, Any], dict[str, Any]]:
    if sha256_file(AUTHORITY_PATH) != AUTHORITY_SHA256:
        raise RuntimeError("AUTHORITY_HASH_MISMATCH")
    if sha256_file(MANIFEST_PATH) != MANIFEST_SHA256:
        raise RuntimeError("MANIFEST_HASH_MISMATCH")
    authority, manifest, receipt = map(read_json, (AUTHORITY_PATH, MANIFEST_PATH, VALIDATION_PATH))
    if receipt.get("status") != "PASS" or not all(receipt.get("checks", {}).values()):
        raise RuntimeError("AUTHORITY_VALIDATION_RECEIPT_FAILED")
    sequence = [(r["candidate_id"], float(r["speed_blocks_per_second"]))
                for r in authority["ordered_search"]["candidate_sequence"]]
    if sequence != [("P3DEV_C01", 2.0), ("P3DEV_C02", 2.5), ("P3DEV_C03", 3.0)]:
        raise RuntimeError("CANDIDATE_SEQUENCE_MISMATCH")
    if "STOP immediately at the first PASS" not in authority["ordered_search"]["stop_rule"]:
        raise RuntimeError("STOP_RULE_MISMATCH")
    if authority["activation_and_readout"]["activation_layers"] != [4]:
        raise RuntimeError("LAYER_AUTHORITY_MISMATCH")
    if authority["confirmatory_membership"] is not False or manifest["confirmatory_membership"] is not False:
        raise RuntimeError("CONFIRMATORY_EXCLUSION_MISMATCH")
    candidates = manifest["candidates"]
    if len(candidates) != 3 or sum(len(c["specs"]) for c in candidates) != 75:
        raise RuntimeError("MANIFEST_CARDINALITY_MISMATCH")
    seen: set[str] = set()
    for candidate, expected in zip(candidates, sequence, strict=True):
        if (candidate["candidate_id"], float(candidate["motion_parameter"]["speed_blocks_per_second"])) != expected:
            raise RuntimeError("CANDIDATE_MANIFEST_SEQUENCE_MISMATCH")
        if len(candidate["specs"]) != 25 or len(candidate["visibility_calibration_specs"]) != 4:
            raise RuntimeError("CANDIDATE_CARDINALITY_MISMATCH")
        for spec in candidate["specs"]:
            body = dict(spec)
            claimed = body.pop("spec_hash")
            if canonical_sha256(body) != claimed:
                raise RuntimeError(f"SPEC_HASH_MISMATCH:{spec.get('trajectory_spec_id')}")
            if spec["confirmatory_membership"] is not False or spec["candidate_id"] != candidate["candidate_id"]:
                raise RuntimeError("SPEC_IDENTITY_MISMATCH")
            if len(spec["target_server_ticks"]) != 19 or spec["target_tau"] != list(range(1, 20)):
                raise RuntimeError("TARGET_IDENTITY_MISMATCH")
            if spec["trajectory_spec_id"] in seen:
                raise RuntimeError("DUPLICATE_IDENTITY")
            seen.add(spec["trajectory_spec_id"])
    for binding in authority["source_bindings"].values():
        path = REPO / binding["path"]
        if sha256_file(path) != binding["sha256"]:
            raise RuntimeError(f"SOURCE_BINDING_MISMATCH:{binding['path']}")
    return authority, manifest


def static_preflight() -> dict[str, Any]:
    branch = subprocess_ok(["git", "branch", "--show-current"], cwd=REPO, text=True).stdout.strip()
    head = subprocess_ok(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).stdout.strip()
    remote = subprocess_ok(["git", "rev-parse", f"origin/{BRANCH}"], cwd=REPO, text=True).stdout.strip()
    if branch != BRANCH or head != AUTHORITY_HEAD or remote != AUTHORITY_HEAD:
        raise RuntimeError(f"GIT_IDENTITY_MISMATCH:{branch}:{head}:{remote}")
    if Path(sys.executable).resolve() != MINEWORLD_PYTHON.resolve():
        raise RuntimeError(f"WRONG_PYTHON:{sys.executable}")
    if sha256_file(MOD_SOURCE) != MOD_SOURCE_SHA256 or sha256_file(SERVER_MOD) != SERVER_MOD_SHA256:
        raise RuntimeError("RUNTIME_MOD_PROVENANCE_MISMATCH")
    home = shutil.disk_usage("/home/sagemaker-user")
    nvme = shutil.disk_usage("/mnt/sagemaker-nvme")
    home_vfs = os.statvfs("/home/sagemaker-user")
    nvme_vfs = os.statvfs("/mnt/sagemaker-nvme")
    if home.free < 700 * (1 << 20) or nvme.free < 50 * (1 << 30):
        raise RuntimeError(f"BLOCKED_DISK:home={home.free}:nvme={nvme.free}")
    import torch
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA_UNAVAILABLE")
    subprocess_ok(["aws", "sts", "get-caller-identity", "--output", "json"])
    return {
        "branch": branch, "head": head, "remote_head": remote,
        "python": sys.executable, "cuda_available": True,
        "cuda_device": torch.cuda.get_device_name(0),
        "home_free_bytes": home.free, "nvme_free_bytes": nvme.free,
        "home_free_inodes": home_vfs.f_favail, "nvme_free_inodes": nvme_vfs.f_favail,
        "mod_source_sha256": MOD_SOURCE_SHA256, "installed_mod_sha256": SERVER_MOD_SHA256,
    }


def normalized_spec(spec: dict[str, Any]) -> dict[str, Any]:
    row = dict(spec)
    row["start_world_x"] = float(spec["start_world_xyz"][0])
    return row


def calibration_spec(spec: dict[str, Any]) -> dict[str, Any]:
    row = dict(spec)
    row["trajectory_spec_id"] = row["calibration_id"]
    row["start_world_x"] = float(row["start_world_xyz"][0])
    row["spec_hash"] = canonical_sha256(spec)
    rng = np.random.default_rng(int(row["noise_seed"]))
    noise = (rng.standard_normal(int(row["expected_max_frames"]))
             * np.sqrt(float(row["motion_noise_q"]) * 0.05)).astype("<f8")
    row["noise_schedule_sha256"] = hashlib.sha256(noise.tobytes()).hexdigest()
    return row


def detector_settings() -> tuple[dict[str, Any], tuple[HsvRange, ...], dict[str, Any]]:
    config = read_json(DETECTOR_CONFIG)["configuration"]["detector_settings"]
    thresholds = tuple(HsvRange(*values) for values in config["hsv_ranges"])
    return config, thresholds, read_json(HOMOGRAPHY)


def derive_artifacts(spec: dict[str, Any], destination: Path, scene: str,
                     target_ticks: list[int] | None) -> dict[str, Any]:
    raw = destination / "raw"
    state = read_jsonl(raw / "server_state.jsonl")
    ticks = read_jsonl(raw / "client_tick.jsonl")
    actions = read_jsonl(raw / "actions.jsonl")
    frames = int(spec["expected_max_frames"])
    if not (len(state) == len(ticks) == len(actions) == frames):
        raise RuntimeError("CAPTURE_STREAM_CARDINALITY_MISMATCH")
    config, thresholds, homography = detector_settings()
    expected_id, expected_hash = spec["trajectory_spec_id"], spec["spec_hash"]
    uuids = {row.get("target_entity_uuid") for row in state}
    if len(uuids) != 1 or None in uuids:
        raise RuntimeError("TARGET_UUID_IDENTITY_MISMATCH")
    tau_by_tick = {tick: i + 1 for i, tick in enumerate(target_ticks or [])}
    visibility, frame_map, coordinates = [], [], []
    for index, row in enumerate(state):
        if (row.get("server_tick") != index or ticks[index].get("server_tick") != index
                or actions[index].get("server_tick") != index
                or ticks[index].get("render_frame_idx") != index
                or actions[index].get("action_idx") != index
                or row.get("trajectory_spec_id") != expected_id
                or row.get("spec_hash") != expected_hash
                or int(row.get("seed")) != int(spec["seed"])
                or row.get("scene") != scene
                or row.get("target_respawn_count") != 0):
            raise RuntimeError(f"CAPTURE_IDENTITY_MISMATCH:{expected_id}:{scene}:{index}")
        result = detect_magenta(
            detector_rgb_rows(raw / f"frames/{index:06d}.png", expected_size=(640, 360)),
            hsv_ranges=thresholds, min_area_pixels=config["min_area_pixels"],
            max_area_pixels=config["max_area_pixels"], open_iterations=config["open_iterations"],
            close_iterations=config["close_iterations"],
            morphology_radius_pixels=config["morphology_radius_pixels"],
            connectivity=config["connectivity"])
        key = {"trajectory_id": expected_id, "model_frame_idx": index,
               "server_tick": index, "render_frame_idx": index, "action_idx": index}
        visibility.append({**key, "geometric_status": "visible" if row["geometric_visible"] else "occluded",
                           "magenta_status": result.status, "magenta_area_pixels": result.area_pixels,
                           "scene": scene, "tau": tau_by_tick.get(index)})
        frame_map.append({**key, "target_entity_uuid": next(iter(uuids)),
                          "frame_path": f"raw/frames/{index:06d}.png"})
        coordinates.append({**key, **project_world_to_coordinates(
            float(row["sheep_x"]), float(row["sheep_z"]), homography["inverse_matrix"])})
    write_jsonl(raw / "visibility.jsonl", visibility)
    write_jsonl(raw / "frame_map.jsonl", frame_map)
    write_jsonl(destination / "coordinates.jsonl", coordinates)
    return {"state": state, "visibility": visibility, "coordinates": coordinates}


def checksum_manifest(destination: Path, identity: str) -> Path:
    files = sorted(p for p in destination.rglob("*") if p.is_file() and p.name != "sha256_manifest.json")
    payload = {"artifact_id": "regime-a-prime-p3-unit-checksums-v0.1", "identity": identity,
               "file_count": len(files), "files": [{"path": p.relative_to(destination).as_posix(),
               "byte_size": p.stat().st_size, "sha256": sha256_file(p)} for p in files]}
    path = destination / "sha256_manifest.json"
    write_json(path, payload)
    return path


def persist_directory(candidate: str, identity: str, destination: Path, kind: str) -> dict[str, Any]:
    manifest = checksum_manifest(destination, identity)
    uri = f"{S3_PREFIX}/{candidate}/{kind}/{identity}"
    subprocess_ok(["aws", "s3", "sync", str(destination), uri, "--only-show-errors"])
    remote = subprocess_ok(["aws", "s3", "cp", f"{uri}/sha256_manifest.json", "-", "--only-show-errors"])
    if remote.stdout != manifest.read_bytes():
        raise RuntimeError("DURABLE_MANIFEST_READBACK_MISMATCH")
    return {"durable_uri": uri, "checksum_manifest_sha256": sha256_file(manifest),
            "checksum_manifest_remote_readback_exact": True,
            "object_count": 1 + read_json(manifest)["file_count"]}


def purge_runtime_episode(session: CaptureSession, episode: int) -> None:
    live = session.live
    for path in (live.SERVER_ROOT / f"mineocclude_out/episode_{episode}",
                 live.CLIENT_ROOT / f"mineocclude_client_out/episode_{episode}"):
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)


def unit_ledger(candidate: str, kind: str) -> Path:
    return OUT / f"p3_{candidate.lower()}_{kind}_ledger.jsonl"


def completed(candidate: str, kind: str) -> dict[str, dict[str, Any]]:
    key = "identity"
    return {row[key]: row for row in read_jsonl(unit_ledger(candidate, kind))
            if row.get("status") == "COMPLETE_VALIDATED_DURABLE"}


def append_unit(candidate: str, kind: str, row: dict[str, Any]) -> None:
    path = unit_ledger(candidate, kind)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True, allow_nan=False) + "\n")
        handle.flush(); os.fsync(handle.fileno())


def capture_complete_count(candidate: str) -> int:
    return len(completed(candidate, "capture"))


def extraction_complete_count(candidate: str) -> int:
    return len(completed(candidate, "extraction"))


def capture_one(session: CaptureSession, candidate: str, spec: dict[str, Any], scene: str,
                run_id: str, episode: int, destination: Path, targets: list[int] | None,
                package: bool) -> dict[str, Any]:
    session.scene_mode = "normal" if scene == "NORMAL" else "nowall"
    session.expected_scene = scene
    info = session.capture(spec, episode, destination)
    artifacts = derive_artifacts(spec, destination, scene, targets)
    if package:
        package_capture(spec, destination, episode, session.live)
    state = artifacts["state"]
    observed = np.asarray([float(row["sheep_x"]) for row in state], dtype="<f8")
    # A captured path mismatch is an authority-defined candidate gate failure,
    # not an operational excuse to recollect or substitute the unit.  Preserve
    # it durably and let ``non_neural_gates`` adjudicate FAIL_PATH_STATE.
    durable = persist_directory(candidate, run_id, destination,
                                "capture" if package else "calibration")
    purge_runtime_episode(session, episode)
    return {"identity": run_id, "candidate_id": candidate, "scene": scene,
            "episode_id": episode, "trajectory_spec_id": spec["trajectory_spec_id"],
            "spec_hash": spec["spec_hash"], "seed": int(spec["seed"]),
            "frames": info["frames"], "capture_seconds": info["capture_seconds"],
            "observed_path_sha256": hashlib.sha256(observed.tobytes()).hexdigest(),
            "visibility_sha256": sha256_file(destination / "raw/visibility.jsonl"),
            "coordinates_sha256": sha256_file(destination / "coordinates.jsonl"),
            "local_root": str(destination), "durable": durable,
            "status": "COMPLETE_VALIDATED_DURABLE", "timestamp": utc()}


def capture_candidate(state: State, candidate: dict[str, Any]) -> None:
    cid = candidate["candidate_id"]
    complete = completed(cid, "capture")
    cal_complete = completed(cid, "calibration")
    with CaptureSession("normal") as session:
        verify_renderer_identity()
        append_event(cid, "calibration", "runtime_provenance_verified", "PASS")
        for frozen in candidate["visibility_calibration_specs"]:
            spec = calibration_spec(frozen); identity = frozen["calibration_id"]
            if identity in cal_complete:
                continue
            destination = CALIBRATIONS / cid / identity
            for attempt in range(1, MAX_ATTEMPTS + 1):
                state.update(current_stage="calibration", current_run_id=identity)
                append_event(cid, "calibration", "unit_started", "RUNNING", run_id=identity, attempt=attempt)
                try:
                    if destination.exists(): shutil.rmtree(destination)
                    destination.mkdir(parents=True)
                    record = capture_one(session, cid, spec, "NORMAL", identity,
                                         int(frozen["episode_id"]), destination, None, False)
                    record["attempt"] = attempt
                    append_unit(cid, "calibration", record); cal_complete[identity] = record
                    append_event(cid, "calibration", "unit_complete", record["status"], run_id=identity)
                    break
                except Exception as exc:
                    purge_runtime_episode(session, int(frozen["episode_id"]))
                    failure = {"identity": identity, "status": "FAILED_RETRYABLE",
                               "attempt": attempt, "error": f"{type(exc).__name__}:{exc}"[:500], "timestamp": utc()}
                    append_unit(cid, "calibration", failure)
                    if attempt == MAX_ATTEMPTS: raise RuntimeError(f"CALIBRATION_RETRY_EXHAUSTED:{identity}") from exc
                    state.update(capture_retries=state.data["capture_retries"] + 1)

        for frozen in candidate["specs"]:
            spec = normalized_spec(frozen)
            for scene in ("NORMAL", "NO_WALL"):
                run = frozen["paired_runs"][scene]
                run_id = run["run_id"]
                if run_id in complete:
                    continue
                destination = CAPTURES / cid / run_id
                for attempt in range(1, MAX_ATTEMPTS + 1):
                    state.update(current_stage="capture", current_run_id=run_id,
                                 candidate_capture_complete=len(complete))
                    append_event(cid, "capture", "trajectory_started", "RUNNING",
                                 run_id=run_id, scene=scene, attempt=attempt)
                    try:
                        if destination.exists(): shutil.rmtree(destination)
                        destination.mkdir(parents=True)
                        record = capture_one(session, cid, spec, scene, run_id,
                                             int(run["episode_id"]), destination,
                                             list(frozen["target_server_ticks"]), True)
                        record.update({"attempt": attempt, "outer_fold": int(frozen["outer_fold"]),
                                       "direction": frozen["direction"]})
                        append_unit(cid, "capture", record); complete[run_id] = record
                        state.update(candidate_capture_complete=len(complete), last_completed_run_id=run_id)
                        append_event(cid, "capture", "trajectory_complete", record["status"], run_id=run_id)
                        break
                    except Exception as exc:
                        purge_runtime_episode(session, int(run["episode_id"]))
                        failure = {"identity": run_id, "status": "FAILED_RETRYABLE", "attempt": attempt,
                                   "error": f"{type(exc).__name__}:{exc}"[:500], "timestamp": utc()}
                        append_unit(cid, "capture", failure)
                        if attempt == MAX_ATTEMPTS: raise RuntimeError(f"CAPTURE_RETRY_EXHAUSTED:{run_id}") from exc
                        state.update(capture_retries=state.data["capture_retries"] + 1)
    if len(complete) != 50 or len(cal_complete) != 4:
        raise RuntimeError("CAPTURE_COMPLETION_CARDINALITY_MISMATCH")


def calibration_gate(candidate: dict[str, Any]) -> dict[str, Any]:
    cid = candidate["candidate_id"]
    tp = fp = tn = fn = ambiguous = rows = 0
    for frozen in candidate["visibility_calibration_specs"]:
        path = CALIBRATIONS / cid / frozen["calibration_id"] / "raw/visibility.jsonl"
        for row in read_jsonl(path):
            truth = row["geometric_status"] == "visible"
            predicted = row["magenta_status"] == "detected"
            tp += truth and predicted; fp += (not truth) and predicted
            tn += (not truth) and (not predicted); fn += truth and (not predicted)
            ambiguous += row["magenta_status"] not in ("detected", "not_detected")
            rows += 1
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    return {"status": "PASS" if precision >= .95 and recall >= .95 and ambiguous == 0 else "FAIL",
            "precision": precision, "recall": recall, "true_positive": tp, "false_positive": fp,
            "true_negative": tn, "false_negative": fn, "ambiguous_rows": ambiguous, "rows": rows,
            "geometric_component_status": "PASS" if (tp + fn) > 0 and (tn + fp) > 0 else "FAIL",
            "rendered_magenta_component_status": "PASS" if precision >= .95 and recall >= .95 else "FAIL"}


def non_neural_gates(authority: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    cid = candidate["candidate_id"]
    captures = completed(cid, "capture")
    path_failures, paired_failures, normal_ok = [], [], 0
    nowall_ok = ambiguous = 0
    for spec in candidate["specs"]:
        paths = {}
        for scene in ("NORMAL", "NO_WALL"):
            run_id = spec["paired_runs"][scene]["run_id"]
            if run_id not in captures:
                path_failures.append(f"missing:{run_id}"); continue
            state_rows = read_jsonl(CAPTURES / cid / run_id / "raw/server_state.jsonl")
            observed = np.asarray([float(r["sheep_x"]) for r in state_rows], dtype="<f8")
            paths[scene] = observed
            if hashlib.sha256(observed.tobytes()).hexdigest() != spec["expected_path_sha256"]:
                path_failures.append(run_id)
            visibility = {int(r["server_tick"]): r for r in read_jsonl(
                CAPTURES / cid / run_id / "raw/visibility.jsonl")}
            for tick in spec["target_server_ticks"]:
                row = visibility[int(tick)]
                geo = row["geometric_status"] == "visible"
                mag = row["magenta_status"] == "detected"
                if scene == "NORMAL": normal_ok += (not geo) and (not mag)
                else: nowall_ok += geo and mag
                ambiguous += geo != mag
        if set(paths) == {"NORMAL", "NO_WALL"} and not np.array_equal(paths["NORMAL"], paths["NO_WALL"]):
            paired_failures.append(spec["trajectory_spec_id"])
    calibration = calibration_gate(candidate)
    path_status = "PASS" if not path_failures and not paired_failures else "FAIL"
    visibility_status = "PASS" if (calibration["status"] == "PASS" and normal_ok == 475
                                    and nowall_ok == 475 and ambiguous == 0) else "FAIL"
    h = candidate["prospective_path_headroom"]
    headroom_status = "PASS" if (h["minimum_target_sd_blocks"] >= authority["prospective_headroom_gate"]["minimum_each_trajectory_target_sd_blocks"]
                                 and h["median_target_sd_blocks"] >= authority["prospective_headroom_gate"]["minimum_candidate_median_target_sd_blocks"]
                                 and h["passes_deterministic_design_check"] is True) else "FAIL"
    receipt = {"artifact_id": "regime-a-prime-p3-non-neural-gates-v0.1", "candidate_id": cid,
               "status": "PASS_TO_EXTRACTION" if {path_status, visibility_status, headroom_status} == {"PASS"} else "FAIL_ADVANCE_ALLOWED",
               "capture_status": "PASS" if len(captures) == 50 else "FAIL",
               "path_status": path_status, "path_failures": path_failures,
               "paired_path_failures": paired_failures, "epsilon_path": 0.0,
               "visibility_status": visibility_status, "visibility_calibration": calibration,
               "normal_geometric_occluded_and_magenta_absent": normal_ok,
               "no_wall_geometric_visible_and_magenta_detected": nowall_ok,
               "target_visibility_ambiguous": ambiguous, "target_rows_per_scene": 475,
               "headroom_status": headroom_status, "headroom": h,
               "confirmatory_membership": False, "timestamp": utc()}
    write_json(OUT / f"p3_{cid.lower()}_non_neural_gates.json", receipt)
    return receipt


def persist_activation(candidate: str, run_id: str, record: dict[str, Any]) -> dict[str, Any]:
    activation = Path(record["activation_path"])
    receipt_path = activation.with_suffix(".receipt.json")
    durable = {**record, "identity": run_id, "candidate_id": candidate,
               "status": "COMPLETE_VALIDATED_DURABLE", "timestamp": utc()}
    write_json(receipt_path, durable)
    uri = f"{S3_PREFIX}/{candidate}/activation/{run_id}/layer4"
    activation_uri, receipt_uri = f"{uri}/{activation.name}", f"{uri}/{receipt_path.name}"
    subprocess_ok(["aws", "s3", "cp", str(activation), activation_uri, "--only-show-errors"])
    subprocess_ok(["aws", "s3", "cp", str(receipt_path), receipt_uri, "--only-show-errors"])
    remote = subprocess_ok(["aws", "s3", "cp", receipt_uri, "-", "--only-show-errors"])
    if remote.stdout != receipt_path.read_bytes():
        raise RuntimeError("ACTIVATION_RECEIPT_READBACK_MISMATCH")
    durable.update({"durable_activation_uri": activation_uri, "durable_receipt_uri": receipt_uri,
                    "durable_receipt_readback_exact": True})
    return durable


def extract_candidate(state: State, candidate: dict[str, Any]) -> dict[str, Any]:
    cid = candidate["candidate_id"]
    complete = completed(cid, "extraction")
    extractor = Layer4Extractor()
    if len(complete) < 50:
        extractor.ensure_loaded(); state.update(gpu_used=True, layers_extracted=[4])
    for spec in candidate["specs"]:
        for scene in ("NORMAL", "NO_WALL"):
            run_id = spec["paired_runs"][scene]["run_id"]
            if run_id in complete: continue
            state.update(current_stage="extraction", current_run_id=run_id,
                         candidate_extraction_complete=len(complete))
            append_event(cid, "extraction", "unit_started", "RUNNING", run_id=run_id, layer=4)
            try:
                # The completed P3 sequential campaign predates the Stage-2
                # manifest and has no authority-selected row set to prove its
                # tau lookup against; it declares that rather than passing its
                # own derivation off as an authority. Records produced this way
                # carry ``target_rows_authority_bound: false`` and are refused
                # by every Stage-2 consumer.
                record = extractor.extract(
                    run_id, CAPTURES / cid / run_id, ACTIVATIONS / cid,
                    expected_target_model_frame_indices=TARGET_ROWS_NOT_AUTHORITY_BOUND)
                record.pop("p2_no_wall_run_id", None)
                if record["shape"] != [19, 336, 2048] or record["layer"] != 4:
                    raise RuntimeError("ACTIVATION_IDENTITY_MISMATCH")
            except Exception as exc:
                append_unit(cid, "extraction", {"identity": run_id, "status": "FAILED_HARD",
                            "error": f"{type(exc).__name__}:{exc}"[:500], "timestamp": utc()})
                raise
            durable = None
            for attempt in range(1, MAX_ATTEMPTS + 1):
                try:
                    durable = persist_activation(cid, run_id, record); durable["persist_attempt"] = attempt; break
                except Exception as exc:
                    append_unit(cid, "extraction", {"identity": run_id, "status": "FAILED_RETRYABLE",
                                "attempt": attempt, "error": f"{type(exc).__name__}:{exc}"[:500], "timestamp": utc()})
                    if attempt < MAX_ATTEMPTS:
                        state.update(extraction_retries=state.data["extraction_retries"] + 1)
            if durable is None: raise RuntimeError(f"EXTRACTION_PERSIST_RETRY_EXHAUSTED:{run_id}")
            durable.update({"trajectory_spec_id": spec["trajectory_spec_id"], "scene": scene,
                            "outer_fold": int(spec["outer_fold"]), "direction": spec["direction"]})
            append_unit(cid, "extraction", durable); complete[run_id] = durable
            state.update(candidate_extraction_complete=len(complete), last_completed_run_id=run_id)
            append_event(cid, "extraction", "unit_complete", durable["status"], run_id=run_id, layer=4)
    records = [complete[spec["paired_runs"][scene]["run_id"]]
               for spec in candidate["specs"] for scene in ("NORMAL", "NO_WALL")]
    if len(records) != 50 or sum(r["rows"] for r in records) != 950:
        raise RuntimeError("EXTRACTION_CARDINALITY_MISMATCH")
    receipt = {"artifact_id": "regime-a-prime-p3-layer4-extraction-v0.1", "candidate_id": cid,
               "status": "PASS", "layers_extracted": [4], "all_layer_extraction_performed": False,
               "run_count": 50, "total_activation_rows": 950,
               "checkpoint_load_count": extractor.load_count, "records": records}
    write_json(OUT / f"p3_{cid.lower()}_activation_manifest.json", receipt)
    return receipt


def load_scene(candidate: dict[str, Any], scene: str) -> tuple[np.ndarray, np.ndarray, list[dict[str, Any]], list[str], dict[str, int], dict[str, str]]:
    cid = candidate["candidate_id"]; extraction = completed(cid, "extraction")
    arrays, rows, ids, outer, directions = [], [], [], {}, {}
    for spec in candidate["specs"]:
        identity = spec["trajectory_spec_id"]; run_id = spec["paired_runs"][scene]["run_id"]
        record = extraction[run_id]
        array = np.load(record["activation_path"], mmap_mode="r")
        if array.shape != (19, 336, 2048) or array.dtype != np.float16 or sha256_file(Path(record["activation_path"])) != record["activation_sha256"]:
            raise RuntimeError(f"ACTIVATION_READBACK_IDENTITY_MISMATCH:{run_id}")
        for offset, (tick, expected_x) in enumerate(zip(spec["target_server_ticks"], spec["expected_target_world_x_blocks"], strict=True)):
            rows.append({"trajectory_id": identity, "run_id": run_id, "scene": scene,
                         "activation_row": offset, "model_frame_idx": int(tick), "server_tick": int(tick),
                         "tau": offset + 1, "outer_fold": int(spec["outer_fold"]),
                         "direction": spec["direction"], "world_x": float(expected_x)})
        arrays.append(array); ids.append(identity); outer[identity] = int(spec["outer_fold"]); directions[identity] = spec["direction"]
    features = np.concatenate(arrays, axis=0)
    target = np.asarray([r["world_x"] for r in rows], dtype=np.float64)
    if features.shape != (475, 336, 2048): raise RuntimeError("ANALYSIS_TENSOR_SHAPE_MISMATCH")
    return features, target, rows, ids, outer, directions


def summarize(rows: list[dict[str, Any]], key: str, seed: int, resamples: int) -> dict[str, Any]:
    base = scalar_metrics(rows, key)
    y = np.asarray([r["world_x"] for r in rows]); pred = np.asarray([r[key] for r in rows])
    per = base["per_trajectory"]; ordered = sorted(per)
    values = np.asarray([per[i]["r2"] for i in ordered]); rmses = np.asarray([per[i]["rmse"] for i in ordered])
    rng = np.random.default_rng(seed); draws = rng.integers(0, len(values), size=(resamples, len(values)))
    stats = values[draws].mean(axis=1)
    return {"trajectory_count": base["trajectory_count"], "row_count": base["row_count"],
            "rmse_blocks": base["trajectory_aggregated_rmse"],
            "mae_blocks": base["trajectory_aggregated_mae"],
            "signed_bias_blocks": float(np.mean(pred-y)), "macro_r2": base["macro_r2"],
            "pooled_r2_descriptive": base["pooled_row_r2_secondary"],
            "trajectory_rmse_mean": float(rmses.mean()), "trajectory_rmse_median": float(np.median(rmses)),
            "bootstrap": {"metric": "trajectory-equal macro R2", "unit": "WHOLE_TRAJECTORY",
                          "resamples": resamples, "seed": seed, "estimate": float(values.mean()),
                          "lower_2_5": float(np.percentile(stats, 2.5)),
                          "upper_97_5": float(np.percentile(stats, 97.5))},
            "per_trajectory": per}


def time_only(candidate: dict[str, Any], seed: int, resamples: int) -> dict[str, Any]:
    rows = []
    for spec in candidate["specs"]:
        sign = 1.0 if spec["direction"] == "LEFT_TO_RIGHT" else -1.0
        for tau, x in zip(spec["target_tau"], spec["expected_target_world_x_blocks"], strict=True):
            rows.append({"trajectory_id": spec["trajectory_spec_id"], "outer_fold": int(spec["outer_fold"]),
                         "direction_sign": sign, "tau": int(tau), "world_x": float(x)})
    predictions: dict[int, float] = {}
    for fold in range(5):
        train = [i for i,r in enumerate(rows) if r["outer_fold"] != fold and r["tau"] <= 15]
        test = [i for i,r in enumerate(rows) if r["outer_fold"] == fold]
        def matrix(index: list[int]) -> np.ndarray:
            return np.asarray([[1., rows[i]["direction_sign"], rows[i]["tau"],
                                rows[i]["tau"]*rows[i]["direction_sign"]] for i in index])
        beta = np.linalg.lstsq(matrix(train), np.asarray([rows[i]["world_x"] for i in train]), rcond=None)[0]
        predictions.update(dict(zip(test, matrix(test) @ beta, strict=True)))
    for i,row in enumerate(rows): row["predicted_time_only"] = float(predictions[i])
    return {"all_tau": summarize(rows, "predicted_time_only", seed, resamples),
            "tau_1_15": summarize([r for r in rows if r["tau"] <= 15], "predicted_time_only", seed, resamples)}


def analyze_candidate(authority: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    cid = candidate["candidate_id"]; boot = authority["candidate_qualification_rule"]["bootstrap"]
    results, prediction_rows = {}, []
    for scene in ("NORMAL", "NO_WALL"):
        features, target, rows, ids, outer, directions = load_scene(candidate, scene)
        best_oof, best_selection, best_gpu = best_k_readout(features, target, rows, ids, outer, directions)
        full_oof, full_selection, full_gpu = full_readout(features, target, rows, ids, outer, directions)
        if set(best_oof) != set(range(475)) or set(full_oof) != set(range(475)):
            raise RuntimeError("OOF_COVERAGE_MISMATCH")
        for i,row in enumerate(rows):
            row["predicted_layer4_best_k"] = float(best_oof[i]); row["predicted_layer4_full"] = float(full_oof[i])
        results[scene] = {
            "BEST_K": {"status": "PASS", "metrics": summarize(rows, "predicted_layer4_best_k", int(boot["seed"]), int(boot["resamples"])),
                       "primary_tau_1_15": summarize([r for r in rows if r["tau"] <= 15], "predicted_layer4_best_k", int(boot["seed"]), int(boot["resamples"])),
                       "selection_by_outer_fold": best_selection, "gpu_seconds": best_gpu},
            "FULL_TOKEN_GRID": {"status": "PASS", "metrics": summarize(rows, "predicted_layer4_full", int(boot["seed"]), int(boot["resamples"])),
                                "primary_tau_1_15": summarize([r for r in rows if r["tau"] <= 15], "predicted_layer4_full", int(boot["seed"]), int(boot["resamples"])),
                                "selection_by_outer_fold": full_selection, "gpu_seconds": full_gpu}}
        prediction_rows.extend(rows)
    baseline = time_only(candidate, int(boot["seed"]), int(boot["resamples"]))
    ceiling = float(authority["candidate_qualification_rule"]["absolute_rmse_ceiling_blocks"])
    checks = {
        "normal_best_k_macro_r2_gt_0": results["NORMAL"]["BEST_K"]["metrics"]["macro_r2"] > 0,
        "normal_best_k_bootstrap_lower_gt_0": results["NORMAL"]["BEST_K"]["metrics"]["bootstrap"]["lower_2_5"] > 0,
        "no_wall_best_k_macro_r2_gt_0": results["NO_WALL"]["BEST_K"]["metrics"]["macro_r2"] > 0,
        "no_wall_best_k_bootstrap_lower_gt_0": results["NO_WALL"]["BEST_K"]["metrics"]["bootstrap"]["lower_2_5"] > 0,
        "normal_best_k_rmse_at_or_below_ceiling": results["NORMAL"]["BEST_K"]["metrics"]["rmse_blocks"] <= ceiling,
        "no_wall_best_k_rmse_at_or_below_ceiling": results["NO_WALL"]["BEST_K"]["metrics"]["rmse_blocks"] <= ceiling,
        "normal_best_k_rmse_strictly_less_than_time_only": results["NORMAL"]["BEST_K"]["metrics"]["rmse_blocks"] < baseline["all_tau"]["rmse_blocks"],
        "time_only_macro_r2_tau_1_15_at_or_below_0_10": baseline["tau_1_15"]["macro_r2"] <= 0.10,
    }
    payload = {"artifact_id": "regime-a-prime-p3-candidate-readouts-v0.1", "candidate_id": cid,
               "status": "PASS", "layer": 4, "BEST_K_controls_progression": True,
               "FULL_TOKEN_GRID_may_rescue_or_advance": False, "scenes": results,
               "time_only_baseline": baseline, "qualification_checks": checks,
               "qualification_status": "PASS" if all(checks.values()) else "FAIL",
               "authority_sha256": AUTHORITY_SHA256, "manifest_sha256": MANIFEST_SHA256,
               "timestamp": utc()}
    write_json(OUT / f"p3_{cid.lower()}_readout_results.json", payload)
    pd.DataFrame(prediction_rows).to_parquet(OUT / f"p3_{cid.lower()}_predictions.parquet",
                                             index=False, compression="zstd")
    return payload


def candidate_summary(candidate: dict[str, Any], gates: dict[str, Any], readout: dict[str, Any] | None) -> dict[str, Any]:
    summary = {"CANDIDATE_ID": candidate["candidate_id"],
               "SPEED_BLOCKS_PER_SECOND": candidate["motion_parameter"]["speed_blocks_per_second"],
               "CAPTURE_STATUS": gates["capture_status"], "PATH_STATUS": gates["path_status"],
               "VISIBILITY_STATUS": gates["visibility_status"], "HEADROOM_STATUS": gates["headroom_status"],
               "EXTRACTION_STATUS": "PASS" if readout else "NOT_AUTHORIZED",
               "BEST_K_STATUS": "PASS" if readout else "NOT_REACHED",
               "FULL_STATUS": "PASS" if readout else "NOT_REACHED",
               "QUALIFICATION_STATUS": readout["qualification_status"] if readout else "FAIL_NOT_QUALIFIED"}
    for scene in ("NORMAL", "NO_WALL"):
        prefix = scene
        if readout:
            for name, label in (("BEST_K", "BEST_K"), ("FULL_TOKEN_GRID", "FULL")):
                m = readout["scenes"][scene][name]["metrics"]
                summary[f"{prefix}_{label}_RMSE_BLOCKS"] = m["rmse_blocks"]
                summary[f"{prefix}_{label}_MACRO_R2"] = m["macro_r2"]
                summary[f"{prefix}_{label}_BOOTSTRAP_95"] = [m["bootstrap"]["lower_2_5"], m["bootstrap"]["upper_97_5"]]
    return summary


def terminalize(state: State, status: str, preflight: dict[str, Any], authority: dict[str, Any]) -> None:
    artifacts = []
    for path in sorted(OUT.glob("p3_*")):
        if path.is_file() and path not in (PROGRESS, TERMINAL):
            artifacts.append({"path": str(path.relative_to(REPO)), "sha256": sha256_file(path), "byte_size": path.stat().st_size})
    payload = {"artifact_id": "regime-a-prime-p3-terminal-result-v0.1", "p3_final_status": status,
               "candidate_history": state.data["candidate_history"], "candidate_selected": state.data["selected_candidate"],
               "selected_speed": state.data["current_candidate_speed"] if state.data["selected_candidate"] else None,
               "stopping_rule_triggered": state.data["stopping_rule_triggered"],
               "authority_sha256": AUTHORITY_SHA256, "manifest_sha256": MANIFEST_SHA256,
               "candidate_artifacts": artifacts, "compute_cost_totals": {
                   "capture_retries": state.data["capture_retries"], "extraction_retries": state.data["extraction_retries"],
                   "gpu_used": state.data["gpu_used"], "layers_extracted": state.data["layers_extracted"]},
               "contamination_status": "CLEAN" if not state.data["contamination_detected"] else "DETECTED",
               "preflight": preflight, "p3_confirmatory_membership": False, "p4_started": False,
               "REGIME_A_PRIME_COLLECTION_AUTHORIZED": "NO", "timestamp": utc()}
    write_json(TERMINAL, payload)


def run() -> int:
    authority, manifest = validate_authority()
    preflight = static_preflight()
    for path in (WORK, CAPTURES, CALIBRATIONS, ACTIVATIONS, LOGS): path.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(f"{os.getpid()}\n", encoding="utf-8")
    state = State(); state.update(p3_status="RUNNING", current_stage="preflight", last_error_code=None)
    append_event(None, "preflight", "authority_accepted", "PASS",
                 authority_sha256=AUTHORITY_SHA256, manifest_sha256=MANIFEST_SHA256)
    history_ids = {r["CANDIDATE_ID"] for r in state.data.get("candidate_history", [])}
    for index, candidate in enumerate(manifest["candidates"]):
        cid = candidate["candidate_id"]
        if state.data.get("stopping_rule_triggered"):
            break
        if cid in history_ids:
            continue
        state.candidate_reset(candidate, index)
        append_event(cid, "candidate", "candidate_entered", "RUNNING",
                     speed_blocks_per_second=candidate["motion_parameter"]["speed_blocks_per_second"])
        capture_candidate(state, candidate)
        state.update(current_stage="non_neural_gates", current_run_id=None)
        gates = non_neural_gates(authority, candidate)
        state.update(path_status=gates["path_status"], visibility_status=gates["visibility_status"],
                     headroom_status=gates["headroom_status"])
        append_event(cid, "non_neural_gates", "candidate_gated", gates["status"])
        readout = None
        if gates["status"] == "PASS_TO_EXTRACTION":
            state.update(current_stage="extraction")
            extract_candidate(state, candidate)
            state.update(extraction_status="PASS", current_stage="readout", best_k_status="RUNNING", full_status="RUNNING")
            readout = analyze_candidate(authority, candidate)
            state.update(best_k_status="PASS", full_status="PASS")
        summary = candidate_summary(candidate, gates, readout)
        history = [*state.data["candidate_history"], summary]
        qualified = summary["QUALIFICATION_STATUS"] == "PASS"
        if qualified:
            state.update(p3_status="PASS_FIRST_QUALIFIED_CANDIDATE", current_stage="terminal",
                         selected_candidate=cid, stopping_rule_triggered=True,
                         qualification_status="PASS", next_candidate_authorized=None,
                         remaining_candidate_count=2-index, candidate_history=history)
            append_event(cid, "qualification", "candidate_adjudicated", "PASS_FIRST_QUALIFIED_CANDIDATE",
                         next_candidate_authorized=None)
            terminalize(state, state.data["p3_status"], preflight, authority)
            return 0
        next_id = manifest["candidates"][index+1]["candidate_id"] if index < 2 else None
        final_status = "RUNNING" if next_id else "BLOCKED_REQUIRES_NEW_PROSPECTIVE_AUTHORITY"
        state.update(p3_status=final_status, current_stage="advancement" if next_id else "terminal",
                     qualification_status="FAIL_NOT_QUALIFIED", next_candidate_authorized=next_id,
                     candidate_history=history, remaining_candidate_count=2-index)
        append_event(cid, "qualification", "candidate_adjudicated", "FAIL_NOT_QUALIFIED",
                     next_candidate_authorized=next_id)
        if not next_id:
            terminalize(state, final_status, preflight, authority)
            return 2
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    if args.validate_only:
        authority, manifest = validate_authority(); preflight = static_preflight()
        print(json.dumps({"status": "PASS", "authority": authority["artifact_id"],
                          "candidates": len(manifest["candidates"]), "preflight": preflight}, sort_keys=True))
        return 0
    try:
        return run()
    except Exception as exc:
        state = State()
        state.update(p3_status="STOPPED_HARD_FAILURE", current_stage="hard_failure",
                     last_error_code=f"{type(exc).__name__}:{exc}"[:500],
                     hard_failures=state.data.get("hard_failures", 0) + 1)
        append_event(state.data.get("current_candidate"), state.data.get("current_stage", "unknown"),
                     "controller_stopped", "FAILED_HARD", error=state.data["last_error_code"],
                     traceback=traceback.format_exc()[-4000:])
        raise
    finally:
        if PID_FILE.exists() and PID_FILE.read_text().strip() == str(os.getpid()):
            PID_FILE.unlink()


if __name__ == "__main__":
    raise SystemExit(main())
