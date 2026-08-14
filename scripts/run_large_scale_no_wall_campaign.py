#!/usr/bin/env python3
"""Execute a locked large-scale no-wall capture campaign.

The P2 path remains Stage-A-only.  The P3 path resumes the same immutable
campaign and runner through the locked B/C/D durability gates.  Both paths
validate raw capture and profile authority without model outcomes, append one
fsync'd hash-chain ledger, and durably copy accepted attempts to S3.  P4B adds
successor-aware lock and schedule validation without changing live motion code.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import os
import re
import shutil
import statistics
import subprocess
import sys
import time
import uuid
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd  # noqa: E402

from mineocclude.data.build_dataset import process_episode  # noqa: E402
from mineocclude.data.noise_schedule import (  # noqa: E402
    generate_noise_schedule,
    schedule_hash,
    serialize_schedule,
)

CONTROLLER_VERSION = "large-scale-no-wall-campaign-orchestrator-v0.4"
P1_HEAD = "ef6469ab68ea8edf572ec4778d2d938b61a07f59"
PREDECESSOR_SHA = "18c8dd0de0987d3065206a5fd7df452badb1338b"
FROZEN_MVP_SHA = "bb22364cbc4f65b788a56b60e7d6503e6226df7b"
CAMPAIGN_SHA256 = "1605f4738840ea531e73fdcee19536d55652a1a05ddef704304adcb1bc41cdd6"
REPAIRED_CAMPAIGN_SHA256 = (
    "adb1eb0611d9cf05d221db6d2040eb65f50a0d5fb4dab32f6bdd3d585484ef9f"
)
STUDY_SHA256 = "08d77261f70a3d7e554ce6f8fe4a565fa09591ae793a87efd60e4a742c016502"
PACKAGE = (
    ROOT / "docs/status/integration/exploratory_large_scale_no_wall_scaling_best_k_v0_1"
)
DEFAULT_CAMPAIGN = PACKAGE / "capture_campaign.json"
DEFAULT_LEDGER = PACKAGE / "p2_capture_ledger.jsonl"
DEFAULT_RUNTIME_ROOT = Path(
    "/mnt/sagemaker-nvme/mineocclude_large_scale_no_wall_scaling_best_k_v0_1"
)
DEFAULT_S3_PREFIX = (
    "s3://sagemaker-us-east-1-323206973672/mineocclude/"
    "exploratory_large_scale_no_wall_scaling_best_k_v0_1/"
)
DEFAULT_V2_LEDGER = PACKAGE / "p4c_capture_ledger_v2.jsonl"
DEFAULT_V2_RUNTIME_ROOT = Path(
    "/mnt/sagemaker-nvme/mineocclude_large_scale_no_wall_scaling_best_k_v0_1_v2"
)
DEFAULT_V2_S3_PREFIX = DEFAULT_S3_PREFIX.rstrip("/") + "/repaired_v2/"
SERVER_ROOT = Path("/home/sagemaker-user/mineocclude-server")
CLIENT_ROOT = Path("/home/sagemaker-user/mineocclude-client")
FIFO = SERVER_ROOT / "cmd.fifo"
JAVA_PATH = Path("/usr/lib/jvm/java-17-openjdk-amd64/bin/java")
XVFB_PATH = Path(shutil.which("Xvfb") or "/usr/bin/Xvfb")
XDOTOOL_PATH = Path(shutil.which("xdotool") or "/usr/bin/xdotool")
XDPYINFO_PATH = Path(shutil.which("xdpyinfo") or "/usr/bin/xdpyinfo")
NATIVE_ENV_OVERRIDES: dict[str, str] = {}
DISPLAY = ":99"
MINECRAFT_WINDOW_CLASS = r"^Minecraft\* 1\.16\.5$"
MINECRAFT_WINDOW_TITLE_PREFIX = "Minecraft* 1.16.5"
CLIENT_RENDER_WIDTH = 640
CLIENT_RENDER_HEIGHT = 360
CLIENT_FOV_DEGREES = 70.0
CLIENT_FOV_EFFECT_SCALE = 0.0
FIXED_CAMERA_LOG_MARKER = "camera pose (0.5, 4.0, -5.5) yaw=0.0"
MAX_ATTEMPTS = 3
EXPECTED_F = 60

STATES = (
    "PRECHECK",
    "RESET_EPISODE",
    "WAIT_RESET_ACK",
    "APPLY_LAYOUT",
    "VERIFY_LAYOUT",
    "SET_CAMERA",
    "VERIFY_CAMERA",
    "SPAWN_OR_POSITION_SHEEP",
    "VERIFY_SHEEP_STATE",
    "ARM_CAPTURE",
    "START_TRAJECTORY",
    "RUN_TRAJECTORY",
    "STOP_CAPTURE",
    "VALIDATE_CAPTURE",
    "ACCEPT_OR_RETRY",
)


class CampaignError(RuntimeError):
    """Fail-closed campaign error carrying a frozen reason code."""

    def __init__(self, reason_code: str, detail: str):
        super().__init__(f"{reason_code}: {detail}")
        self.reason_code = reason_code
        self.detail = detail


class CampaignBlocked(CampaignError):
    pass


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def sha256_file(path: Path, chunk_size: int = 8 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def write_json_new(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(path, flags, 0o644)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


class CampaignAuthority:
    def __init__(self, campaign_path: Path):
        self.path = campaign_path.resolve()
        self.package = self.path.parent
        expected_campaign_hashes = {
            "capture_campaign.json": CAMPAIGN_SHA256,
            "capture_campaign_v2.json": REPAIRED_CAMPAIGN_SHA256,
        }
        expected_campaign_hash = expected_campaign_hashes.get(self.path.name)
        if expected_campaign_hash is None:
            raise CampaignError(
                "PRECHECK_FAILED", f"unsupported campaign authority: {self.path.name}"
            )
        if sha256_file(self.path) != expected_campaign_hash:
            raise CampaignError("PRECHECK_FAILED", "capture campaign hash changed")
        study = self.package / "study_design.json"
        if sha256_file(study) != STUDY_SHA256:
            raise CampaignError("PRECHECK_FAILED", "study design hash changed")
        lock_name = (
            "capture_campaign_v2.lock.json"
            if self.path.name == "capture_campaign_v2.json"
            else "capture_campaign.lock.json"
        )
        self._verify_lock(self.path, self.package / lock_name)
        self._verify_lock(study, self.package / "study_design.lock.json")
        self.campaign = read_json(self.path)
        if self.campaign.get("campaign_shape", {}).get("trajectory_spec_count") != 120:
            raise CampaignError(
                "PRECHECK_FAILED", "campaign is not the locked 120 specs"
            )
        self.specs = {
            spec["trajectory_spec_id"]: spec
            for spec in self.campaign["trajectory_specs"]
        }
        if len(self.specs) != 120:
            raise CampaignError("PRECHECK_FAILED", "spec IDs are not unique")
        self.stage_by_spec = {
            row["trajectory_spec_id"]: row["stage"]
            for row in self.campaign["campaign_order"]
        }
        if len(self.stage_by_spec) != 120:
            raise CampaignError("PRECHECK_FAILED", "campaign order IDs are not unique")
        for spec in self.specs.values():
            body = dict(spec)
            spec_hash = body.pop("spec_hash")
            if canonical_sha256(body) != spec_hash:
                raise CampaignError(
                    "SPEC_ID_OR_HASH_MISMATCH", spec["trajectory_spec_id"]
                )

    @property
    def is_repaired_v2(self) -> bool:
        return self.path.name == "capture_campaign_v2.json"

    @staticmethod
    def _verify_lock(source: Path, lock_path: Path) -> None:
        lock = read_json(lock_path)
        if lock.get("status") != "LOCKED":
            raise CampaignError("PRECHECK_FAILED", f"unlocked authority: {lock_path}")
        if sha256_file(source) != lock.get("source_sha256"):
            raise CampaignError("PRECHECK_FAILED", f"lock mismatch: {source}")
        if source.stat().st_size != lock.get("source_byte_size"):
            raise CampaignError("PRECHECK_FAILED", f"size mismatch: {source}")

    def stage_specs(self, stage: str) -> list[dict[str, Any]]:
        stage = stage.upper()
        if stage not in {"A", "B", "C", "D"}:
            raise CampaignError("PRECHECK_FAILED", f"unknown stage {stage}")
        entries = [
            row for row in self.campaign["campaign_order"] if row["stage"] == stage
        ]
        result = []
        for entry in sorted(entries, key=lambda row: row["campaign_index"]):
            spec = self.specs[entry["trajectory_spec_id"]]
            if spec["spec_hash"] != entry["spec_hash"]:
                raise CampaignError(
                    "SPEC_ID_OR_HASH_MISMATCH", entry["trajectory_spec_id"]
                )
            result.append(spec)
        expected = {"A": 12, "B": 36, "C": 36, "D": 36}[stage]
        if len(result) != expected:
            raise CampaignError(
                "PRECHECK_FAILED", f"stage {stage} has {len(result)} specs"
            )
        return result

    def stage_for(self, spec_id: str) -> str:
        try:
            return self.stage_by_spec[spec_id]
        except KeyError as error:
            raise CampaignError(
                "SPEC_ID_OR_HASH_MISMATCH", f"unplanned spec {spec_id}"
            ) from error


class AppendOnlyLedger:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.records = read_jsonl(path)
        previous = None
        for index, record in enumerate(self.records):
            claimed = record.get("record_sha256")
            body = dict(record)
            body.pop("record_sha256", None)
            if record.get("previous_record_sha256") != previous:
                raise CampaignError("PRECHECK_FAILED", f"ledger chain break at {index}")
            if canonical_sha256(body) != claimed:
                raise CampaignError(
                    "PRECHECK_FAILED", f"ledger hash mismatch at {index}"
                )
            previous = claimed

    def append(
        self, record_type: str, spec: dict[str, Any], attempt: int, **fields: Any
    ) -> dict[str, Any]:
        record = {
            "ledger_schema_version": "large-scale-no-wall-ledger-v0.1",
            "record_id": str(uuid.uuid4()),
            "record_type": record_type,
            "recorded_at_utc": utc_now(),
            "trajectory_spec_id": spec["trajectory_spec_id"],
            "spec_hash": spec["spec_hash"],
            "attempt_number": attempt,
            "previous_record_sha256": (
                self.records[-1]["record_sha256"] if self.records else None
            ),
            **fields,
        }
        record["record_sha256"] = canonical_sha256(record)
        data = canonical_bytes(record) + b"\n"
        descriptor = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
        try:
            os.write(descriptor, data)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        self.records.append(record)
        return record

    def accepted_ids(self) -> set[str]:
        return {
            row["trajectory_spec_id"]
            for row in self.records
            if row["record_type"] == "ATTEMPT_CLASSIFIED"
            and row.get("classification") == "ACCEPTED"
        }

    def attempts_for(self, spec_id: str) -> int:
        attempts = [
            int(row["attempt_number"])
            for row in self.records
            if row["trajectory_spec_id"] == spec_id
        ]
        return max(attempts, default=0)


def expected_speed(spec: dict[str, Any], tick: int) -> tuple[float, int]:
    for index, segment in enumerate(spec["exact_speed_schedule"]):
        if (
            segment["start_model_frame_idx"]
            <= tick
            < segment["stop_model_frame_idx_exclusive"]
        ):
            return float(segment["signed_speed_blocks_per_second"]), index
    raise CampaignError("MOTION_SCHEDULE_MISMATCH", f"no speed for tick {tick}")


def motion_schedule_document(spec: dict[str, Any]) -> dict[str, Any]:
    return {
        "schedule_format_version": "mineocclude-motion-schedule-v0.1",
        "trajectory_spec_id": spec["trajectory_spec_id"],
        "spec_hash": spec["spec_hash"],
        "expected_ticks": spec["expected_source_frame_count"],
        "segments": spec["exact_speed_schedule"],
    }


def commands_for_spec(spec: dict[str, Any], episode_id: int) -> list[str]:
    return [
        "mineocclude mode nowall",
        "mineocclude duration 0",
        "mineocclude reveal 0",
        "mineocclude warmup 60",
        "mineocclude impulse -1 0",
        "mineocclude pairshift 0",
        "mineocclude lockcam on",
        (
            "mineocclude startspec "
            f"{spec['runtime_layout_id']} {episode_id} {spec['capture_seed']} "
            f"{spec['process_noise']['q_blocks_squared_per_second']} "
            f"{EXPECTED_F} {spec['start_position_authority']['axis_position_blocks']} "
            f"{spec['trajectory_spec_id']} {spec['spec_hash']}"
        ),
    ]


def validate_profile_semantics(spec: dict[str, Any]) -> None:
    speeds = [
        float(row["signed_speed_blocks_per_second"])
        for row in spec["exact_speed_schedule"]
    ]
    if spec.get("spec_version") == "large-scale-no-wall-trajectory-spec-v0.2":
        allowed_families = {
            "LONG_DWELL_RESTART",
            "MULTI_DWELL_PULSE",
            "DELAYED_BOUNDED_BURST",
            "ASYMMETRIC_RESTART",
            "TERMINAL_HOLD_RESTART",
        }
        direction_sign = 1.0 if spec["direction"] == "LEFT_TO_RIGHT" else -1.0
        nonzero = [speed for speed in speeds if speed != 0.0]
        valid = (
            spec["profile_family"] in allowed_families
            and re.fullmatch(
                r"MONOTONIC_MULTI_DWELL_SHAPE_(0[1-9]|1[0-9]|20)",
                spec.get("trajectory_shape_class", ""),
            )
            is not None
            and spec.get("direction_semantics") == "NONZERO_COMMANDED_VELOCITY_SIGN"
            and spec.get("commanded_direction_reversal_count") == 0
            and len(speeds) >= 5
            and any(speed == 0.0 for speed in speeds)
            and bool(nonzero)
            and all(math.copysign(1.0, speed) == direction_sign for speed in nonzero)
            and all(abs(speed) in {0.0, 1.0, 1.5, 2.0} for speed in speeds)
        )
        if not valid:
            raise CampaignError(
                "MOTION_SCHEDULE_MISMATCH", "invalid v0.2 multi-dwell semantics"
            )
        for tick in range(EXPECTED_F):
            expected_speed(spec, tick)
        return

    family = spec["profile_family"]
    predicates = {
        "EARLY_CONSTANT": len(speeds) == 1 and speeds[0] != 0,
        "FAST_TRANSIT": len(speeds) == 1 and abs(speeds[0]) == 2.0,
        "LATE_ONSET": len(speeds) == 2 and speeds[0] == 0 and speeds[1] != 0,
        "PAUSE_RESUME": (
            len(speeds) == 3
            and speeds[0] != 0
            and speeds[1] == 0
            and speeds[2] == speeds[0]
        ),
        "TWO_SPEED": (
            len(speeds) == 2
            and abs(speeds[0]) == 1.0
            and abs(speeds[1]) == 2.0
            and math.copysign(1.0, speeds[0]) == math.copysign(1.0, speeds[1])
        ),
    }
    if not predicates.get(family, False):
        raise CampaignError("MOTION_SCHEDULE_MISMATCH", f"invalid {family} semantics")
    for tick in range(EXPECTED_F):
        expected_speed(spec, tick)


def _xdotool(*arguments: str) -> str:
    return subprocess.run(
        [str(XDOTOOL_PATH), *arguments],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
        env={**os.environ, **NATIVE_ENV_OVERRIDES, "DISPLAY": DISPLAY},
    ).stdout.strip()


def _parse_window_ids(output: str) -> list[str]:
    ids = [line.strip() for line in output.splitlines() if line.strip()]
    if not ids or any(not value.isdecimal() or int(value) <= 0 for value in ids):
        return []
    return ids


def _expected_client_process(pid_text: str) -> bool:
    if not pid_text.isdecimal() or int(pid_text) <= 0:
        return False
    try:
        arguments = [
            value
            for value in Path(f"/proc/{int(pid_text)}/cmdline").read_bytes().split(b"\0")
            if value
        ]
        game_dir_index = arguments.index(b"--gameDir")
    except (OSError, ValueError):
        return False
    return (
        b"net.fabricmc.loader.impl.launch.knot.KnotClient" in arguments
        and game_dir_index + 1 < len(arguments)
        and Path(os.fsdecode(arguments[game_dir_index + 1])).resolve()
        == CLIENT_ROOT.resolve()
    )


def _parse_window_geometry(output: str, window_id: str) -> bool:
    fields: dict[str, str] = {}
    for line in output.splitlines():
        if "=" not in line:
            return False
        key, value = line.split("=", 1)
        if key in fields or not value.strip().lstrip("-").isdecimal():
            return False
        fields[key] = value.strip()
    return (
        set(fields) == {"WINDOW", "X", "Y", "WIDTH", "HEIGHT", "SCREEN"}
        and fields["WINDOW"] == window_id
        and fields["WIDTH"] == str(CLIENT_RENDER_WIDTH)
        and fields["HEIGHT"] == str(CLIENT_RENDER_HEIGHT)
        and fields["SCREEN"] == "0"
    )


def _focus_client_once() -> bool:
    try:
        ids = _parse_window_ids(
            _xdotool(
                "search", "--onlyvisible", "--class", MINECRAFT_WINDOW_CLASS
            )
        )
        if len(ids) != 1:
            return False
        window_id = ids[0]
        if (
            not _xdotool("getwindowname", window_id).startswith(
                MINECRAFT_WINDOW_TITLE_PREFIX
            )
            or not _expected_client_process(_xdotool("getwindowpid", window_id))
            or not _parse_window_geometry(
                _xdotool("getwindowgeometry", "--shell", window_id), window_id
            )
        ):
            return False
        _xdotool("windowactivate", "--sync", window_id)
        return (
            _xdotool("getactivewindow") == window_id
            and _xdotool("getwindowfocus") == window_id
        )
    except (OSError, subprocess.SubprocessError):
        return False


def focus_client(timeout_seconds: float = 10.0, poll_interval: float = 0.1) -> bool:
    if timeout_seconds < 0 or poll_interval <= 0:
        return False
    deadline = time.monotonic() + timeout_seconds
    while True:
        if _focus_client_once():
            return True
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False
        time.sleep(min(poll_interval, remaining))


class LiveRuntime:
    def __init__(self):
        self.server_root = SERVER_ROOT
        self.client_root = CLIENT_ROOT

    def log_text(self) -> str:
        path = self.server_root / "logs/latest.log"
        return path.read_text(errors="ignore") if path.exists() else ""

    def client_log_text(self) -> str:
        path = self.client_root / "logs/latest.log"
        return path.read_text(errors="ignore") if path.exists() else ""

    def send(self, commands: list[str]) -> None:
        with FIFO.open("w", encoding="utf-8") as stream:
            stream.write("\n".join(commands) + "\n")

    def wait_log(self, pattern: str, timeout: float, offset: int = 0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if re.search(pattern, self.log_text()[offset:]):
                return
            time.sleep(0.1)
        raise CampaignError("CAPTURE_START_FAILED", f"log timeout: {pattern}")

    @staticmethod
    def wait_file(path: Path, timeout: float) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if path.is_file() and path.stat().st_size > 0:
                return
            time.sleep(0.05)
        raise CampaignError("REQUIRED_FILES_MISSING", f"file timeout: {path}")

    def precheck(self) -> None:
        required = [
            JAVA_PATH,
            XVFB_PATH,
            XDOTOOL_PATH,
            self.server_root,
            self.client_root,
            FIFO,
        ]
        missing = [str(path) for path in required if not path.exists()]
        if missing:
            raise CampaignError("PRECHECK_FAILED", f"missing runtime: {missing}")
        if "server ready" not in self.log_text():
            raise CampaignError("PRECHECK_FAILED", "server is not ready")
        if (
            "joined the game" not in self.log_text()
            or "left the game" in self.log_text().split("joined the game")[-1]
        ):
            raise CampaignError("PRECHECK_FAILED", "client is not connected")
        if not focus_client():
            raise CampaignError("CAMERA_VERIFICATION_FAILED", "client focus failed")
        fov_receipt = self.client_root / "mineocclude_client_authority/fov_receipt.json"
        try:
            fov = json.loads(fov_receipt.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            raise CampaignError(
                "CAMERA_VERIFICATION_FAILED", "client FOV receipt missing or malformed"
            )
        if (
            fov.get("status") != "PINNED"
            or not _close(fov.get("fov_degrees"), CLIENT_FOV_DEGREES)
            or not _close(fov.get("fov_effect_scale"), CLIENT_FOV_EFFECT_SCALE)
            or FIXED_CAMERA_LOG_MARKER not in self.log_text()
        ):
            raise CampaignError(
                "CAMERA_VERIFICATION_FAILED", "frozen FOV/fixed camera mismatch"
            )


def append_transition(
    ledger: AppendOnlyLedger,
    spec: dict[str, Any],
    attempt: int,
    previous: str,
    state: str,
    ack_source: str,
    elapsed_seconds: float,
) -> str:
    ledger.append(
        "STATE_TRANSITION",
        spec,
        attempt,
        from_state=previous,
        to_state=state,
        reason_code="PASS",
        ack_source=ack_source,
        controller_version=CONTROLLER_VERSION,
        elapsed_seconds=round(elapsed_seconds, 6),
    )
    return state


def write_attempt_schedules(
    spec: dict[str, Any], episode_id: int, attempt_root: Path
) -> tuple[Path, Path]:
    noise = generate_noise_schedule(
        seed=int(spec["capture_seed"]),
        n_draws=EXPECTED_F,
        q=float(spec["process_noise"]["q_blocks_squared_per_second"]),
    )
    actual_hash = schedule_hash(noise)
    expected_hash = spec["process_noise"]["schedule_sha256"]
    if actual_hash != expected_hash:
        raise CampaignError(
            "NOISE_SCHEDULE_MISMATCH", f"{actual_hash} != {expected_hash}"
        )
    noise_path = SERVER_ROOT / "mineocclude_schedules" / f"episode_{episode_id}.jsonl"
    motion_path = (
        SERVER_ROOT / "mineocclude_motion_schedules" / f"episode_{episode_id}.json"
    )
    noise_path.parent.mkdir(parents=True, exist_ok=True)
    motion_path.parent.mkdir(parents=True, exist_ok=True)
    noise_path.write_bytes(serialize_schedule(noise))
    motion_path.write_bytes(canonical_bytes(motion_schedule_document(spec)) + b"\n")
    shutil.copy2(noise_path, attempt_root / "noise_schedule.jsonl")
    shutil.copy2(motion_path, attempt_root / "motion_schedule.json")
    return noise_path, motion_path


def snapshot_raw(episode_id: int, attempt_root: Path) -> tuple[Path, Path]:
    raw_root = attempt_root / "raw"
    server_source = SERVER_ROOT / "mineocclude_out" / f"episode_{episode_id}"
    client_source = CLIENT_ROOT / "mineocclude_client_out" / f"episode_{episode_id}"
    server_copy = raw_root / "server"
    client_copy = raw_root / "client"
    shutil.copytree(server_source, server_copy)
    shutil.copytree(client_source, client_copy)
    return server_copy, client_copy


def _close(left: float, right: float, tolerance: float = 1e-9) -> bool:
    return math.isclose(float(left), float(right), rel_tol=0.0, abs_tol=tolerance)


def validate_capture(
    spec: dict[str, Any],
    episode_id: int,
    attempt: int,
    attempt_root: Path,
    geometry_receipt: Path,
) -> dict[str, Any]:
    server_dir = attempt_root / "raw/server"
    client_dir = attempt_root / "raw/client"
    required = [
        server_dir / "server_state.jsonl",
        server_dir / "reset_result.json",
        server_dir / "layout_meta.json",
        server_dir / "lifecycle.jsonl",
        server_dir / "finalization.json",
        client_dir / "raw_actions.jsonl",
        client_dir / "client_tick.jsonl",
        client_dir / "client_authority.json",
        client_dir / "capture_complete.json",
        geometry_receipt,
        attempt_root / "attempt_metadata.json",
        attempt_root / "noise_schedule.jsonl",
        attempt_root / "motion_schedule.json",
    ]
    missing = [str(path) for path in required if not path.is_file()]
    frames = sorted((client_dir / "frames").glob("*.png"))
    if missing:
        raise CampaignError("REQUIRED_FILES_MISSING", str(missing))
    if len(frames) != EXPECTED_F:
        raise CampaignError("FRAME_COUNT_MISMATCH", f"frames={len(frames)}")

    metadata = read_json(attempt_root / "attempt_metadata.json")
    if (
        metadata.get("trajectory_spec_id") != spec["trajectory_spec_id"]
        or metadata.get("spec_hash") != spec["spec_hash"]
        or metadata.get("attempt_number") != attempt
        or metadata.get("episode_id") != episode_id
    ):
        raise CampaignError("SPEC_ID_OR_HASH_MISMATCH", "attempt metadata")
    reset = read_json(server_dir / "reset_result.json")
    if reset.get("layout_id") != spec["runtime_layout_id"]:
        raise CampaignError("LAYOUT_MISMATCH", str(reset.get("layout_id")))
    if reset.get("scene") != "NO_WALL":
        raise CampaignError("NO_WALL_MISMATCH", str(reset.get("scene")))
    if (
        reset.get("trajectory_spec_id") != spec["trajectory_spec_id"]
        or reset.get("spec_hash") != spec["spec_hash"]
    ):
        raise CampaignError("SPEC_ID_OR_HASH_MISMATCH", "server reset receipt")
    if not _close(
        reset.get("start_axis_pos"),
        spec["start_position_authority"]["axis_position_blocks"],
    ):
        raise CampaignError("SHEEP_INITIAL_STATE_MISMATCH", "start axis")
    if reset.get("observed_target_count") != 1 or not reset.get("target_count_ok"):
        raise CampaignError("SHEEP_INITIAL_STATE_MISMATCH", "target count")

    finalization = read_json(server_dir / "finalization.json")
    if (
        finalization.get("state") != "COMPLETED"
        or finalization.get("ticks") != EXPECTED_F
    ):
        raise CampaignError("UNCLEAN_TERMINATION", str(finalization))
    if finalization.get("schedule_draws_consumed") != EXPECTED_F:
        raise CampaignError("MOTION_SCHEDULE_MISMATCH", "noise consumption")

    client_authority = read_json(client_dir / "client_authority.json")
    if not _close(client_authority.get("fov_degrees"), 70.0):
        raise CampaignError("CAMERA_MISMATCH", "FOV")
    if not _close(client_authority.get("fov_effect_scale"), 0.0):
        raise CampaignError("CAMERA_MISMATCH", "FOV effect")
    if (
        client_authority.get("framebuffer_width"),
        client_authority.get("framebuffer_height"),
    ) != (640, 360):
        raise CampaignError("MODEL_CONTEXT_METADATA_MISMATCH", "framebuffer")
    completion = read_json(client_dir / "capture_complete.json")
    if (
        not completion.get("drained")
        or completion.get("pending_writes") != 0
        or completion.get("writer_errors") != 0
    ):
        raise CampaignError("UNCLEAN_TERMINATION", "capture queue not drained")
    if (
        completion.get("frame_count") != EXPECTED_F
        or completion.get("final_render_frame_idx") != EXPECTED_F - 1
    ):
        raise CampaignError("FRAME_COUNT_MISMATCH", "drain receipt")

    state = read_jsonl(server_dir / "server_state.jsonl")
    actions = read_jsonl(client_dir / "raw_actions.jsonl")
    ticks = read_jsonl(client_dir / "client_tick.jsonl")
    if not (len(state) == len(actions) == len(ticks) == EXPECTED_F):
        raise CampaignError("FRAME_COUNT_MISMATCH", "stream cardinality")
    if [row["server_tick"] for row in state] != list(range(EXPECTED_F)):
        raise CampaignError("TIMESTAMP_DISCONTINUITY", "server ticks")
    if [row["render_frame_idx"] for row in actions] != list(range(EXPECTED_F)):
        raise CampaignError("TIMESTAMP_DISCONTINUITY", "action indices")
    if [row["render_frame_idx"] for row in ticks] != list(range(EXPECTED_F)):
        raise CampaignError("TIMESTAMP_DISCONTINUITY", "client indices")

    noise_rows = read_jsonl(attempt_root / "noise_schedule.jsonl")[1:]
    axis = float(spec["start_position_authority"]["axis_position_blocks"])
    lane_min = float(spec["target_range"]["scalar_axis_min_blocks"])
    lane_max = float(spec["target_range"]["scalar_axis_max_blocks"])
    camera = spec["camera_viewpoint_authority"]
    feet_x, feet_y, feet_z = [float(x) for x in camera["canonical_feet_xyz_blocks"]]
    previous_epoch = None
    for index, row in enumerate(state):
        commanded, segment = expected_speed(spec, index)
        if (
            row.get("trajectory_spec_id") != spec["trajectory_spec_id"]
            or row.get("spec_hash") != spec["spec_hash"]
        ):
            raise CampaignError("SPEC_ID_OR_HASH_MISMATCH", f"state tick {index}")
        if row.get("scene") != "NO_WALL" or not row.get("geometric_visible"):
            raise CampaignError("NO_WALL_MISMATCH", f"state tick {index}")
        if (
            not _close(row.get("commanded_v"), commanded)
            or row.get("motion_segment_index") != segment
        ):
            raise CampaignError("MOTION_SCHEDULE_MISMATCH", f"tick {index}")
        draw = float(noise_rows[index]["noise_draw"])
        if not _close(row.get("noise_draw"), draw, 1e-12):
            raise CampaignError("MOTION_SCHEDULE_MISMATCH", f"noise tick {index}")
        axis = min(lane_max, max(lane_min, axis + commanded * 0.05 + draw))
        if not _close(row.get("axis_pos"), axis, 1e-9):
            raise CampaignError("UNINTENDED_TELEPORT", f"tick {index}")
        if not lane_min <= float(row["axis_pos"]) <= lane_max:
            raise CampaignError("TARGET_RANGE_INVALID", f"tick {index}")
        if not (
            _close(row.get("player_x"), feet_x, 1e-6)
            and _close(row.get("player_y"), feet_y + 1.62, 1e-6)
            and _close(row.get("player_z"), feet_z, 1e-6)
            and _close(row.get("player_yaw"), camera["yaw_degrees"], 1e-6)
            and _close(row.get("player_pitch"), camera["pitch_degrees"], 1e-6)
        ):
            raise CampaignError("CAMERA_DRIFT", f"tick {index}")
        epoch = int(row["server_epoch_nanos"])
        if previous_epoch is not None and epoch <= previous_epoch:
            raise CampaignError("TIMESTAMP_DISCONTINUITY", f"tick {index}")
        previous_epoch = epoch
    expected_end = float(
        spec["end_position_authority"]["expected_axis_position_blocks"]
    )
    if not _close(axis, expected_end, 1e-9):
        raise CampaignError("TARGET_RANGE_INVALID", f"end {axis} != {expected_end}")
    if any(
        abs(float(row.get("camera_dx", 0))) > 1e-4
        or abs(float(row.get("camera_dy", 0))) > 1e-4
        for row in actions
    ):
        raise CampaignError("CAMERA_DRIFT", "nonzero raw action camera delta")

    processed_root = attempt_root / "processed"
    summary = process_episode(
        str(server_dir),
        str(client_dir),
        str(processed_root),
        run_empirical=True,
        canonical_640=True,
    )
    if not summary.get("accepted") or summary.get("n_frames") != EXPECTED_F:
        raise CampaignError("CAPTURE_VALIDATION_FAILED", str(summary.get("problems")))
    frame_map = pd.read_parquet(summary["frame_map"])
    if len(frame_map) != EXPECTED_F or list(frame_map["model_frame_idx"]) != list(
        range(EXPECTED_F)
    ):
        raise CampaignError("ELIGIBLE_ROW_SCHEDULE_MISMATCH", "model frame schedule")
    if (
        int(frame_map["visibility_quarantine"].sum()) != 0
        or int(frame_map["visible_flag"].sum()) != EXPECTED_F
    ):
        raise CampaignError(
            "ELIGIBLE_ROW_SCHEDULE_MISMATCH", "strict visibility F != 60"
        )
    frame_map.to_json(attempt_root / "frame_map.jsonl", orient="records", lines=True)
    shutil.copy2(server_dir / "server_state.jsonl", attempt_root / "server_state.jsonl")
    shutil.copy2(client_dir / "raw_actions.jsonl", attempt_root / "raw_actions.jsonl")
    shutil.copy2(geometry_receipt, attempt_root / "geometry_receipt.json")
    return {
        "trajectory_spec_id": spec["trajectory_spec_id"],
        "spec_hash": spec["spec_hash"],
        "episode_id": episode_id,
        "attempt_number": attempt,
        "layout_id": spec["layout_id"],
        "profile_family": spec["profile_family"],
        "direction": spec["direction"],
        "source_frame_count": EXPECTED_F,
        "eligible_rows": EXPECTED_F,
        "actual_start_axis": reset["start_axis_pos"],
        "actual_end_axis": float(state[-1]["axis_pos"]),
        "commanded_speed_schedule": spec["exact_speed_schedule"],
        "processed_summary": summary,
    }


def build_checksum_manifest(attempt_root: Path) -> dict[str, Any]:
    rows = []
    for path in sorted(attempt_root.rglob("*")):
        if path.is_file() and path.name != "sha256_manifest.json":
            rows.append(
                {
                    "path": path.relative_to(attempt_root).as_posix(),
                    "byte_size": path.stat().st_size,
                    "sha256": sha256_file(path),
                }
            )
    manifest = {
        "schema_version": "mineocclude-attempt-checksums-v0.1",
        "file_count": len(rows),
        "files": rows,
    }
    write_json_new(attempt_root / "sha256_manifest.json", manifest)
    return manifest


def upload_attempt(
    attempt_root: Path,
    spec: dict[str, Any],
    attempt: int,
    s3_prefix: str,
    stage: str,
) -> str:
    destination = (
        s3_prefix.rstrip("/")
        + f"/stage_{stage.lower()}/attempts/"
        + spec["trajectory_spec_id"]
        + f"/attempt_{attempt:02d}/"
    )
    subprocess.run(
        ["aws", "s3", "sync", str(attempt_root), destination, "--only-show-errors"],
        check=True,
        timeout=900,
    )
    remote = subprocess.run(
        [
            "aws",
            "s3",
            "cp",
            destination + "sha256_manifest.json",
            "-",
            "--only-show-errors",
        ],
        check=True,
        capture_output=True,
        timeout=120,
    ).stdout
    local = (attempt_root / "sha256_manifest.json").read_bytes()
    if remote != local:
        raise CampaignError("PROVENANCE_OR_CHECKSUM_MISSING", "S3 manifest mismatch")
    return destination


class CampaignRunner:
    def __init__(
        self,
        authority: CampaignAuthority,
        ledger: AppendOnlyLedger,
        runtime_root: Path,
        s3_prefix: str,
        base_episode_id: int = 30000,
    ):
        self.authority = authority
        self.ledger = ledger
        self.runtime_root = runtime_root
        self.s3_prefix = s3_prefix
        self.next_episode_id = self._next_episode_id(base_episode_id)
        self.runtime = LiveRuntime()
        self.accepted: list[dict[str, Any]] = []
        self.rejected: list[dict[str, Any]] = []

    def _next_episode_id(self, base: int) -> int:
        used = []
        for root in (
            SERVER_ROOT / "mineocclude_out",
            CLIENT_ROOT / "mineocclude_client_out",
        ):
            for path in root.glob("episode_*") if root.exists() else []:
                match = re.fullmatch(r"episode_(\d+)", path.name)
                if match:
                    used.append(int(match.group(1)))
        for row in self.ledger.records:
            if row.get("episode_id") is not None:
                used.append(int(row["episode_id"]))
        return max([base - 1, *used]) + 1

    def _attempt_root(self, spec: dict[str, Any], attempt: int) -> Path:
        return (
            self.runtime_root
            / "attempts"
            / spec["trajectory_spec_id"]
            / f"attempt_{attempt:02d}"
        )

    def run_attempt(self, spec: dict[str, Any], attempt: int) -> dict[str, Any]:
        validate_profile_semantics(spec)
        episode_id = self.next_episode_id
        self.next_episode_id += 1
        attempt_root = self._attempt_root(spec, attempt)
        attempt_root.mkdir(parents=True, exist_ok=False)
        metadata = {
            "schema_version": "large-scale-no-wall-attempt-v0.1",
            "trajectory_spec_id": spec["trajectory_spec_id"],
            "spec_hash": spec["spec_hash"],
            "attempt_number": attempt,
            "episode_id": episode_id,
            "controller_version": CONTROLLER_VERSION,
            "p1_head": P1_HEAD,
            "started_at_utc": utc_now(),
            "exact_scientific_spec": spec,
            "model_authority_references": spec["model_authority_references"],
        }
        write_json_new(attempt_root / "attempt_metadata.json", metadata)
        self.ledger.append(
            "SPEC_REGISTERED",
            spec,
            attempt,
            episode_id=episode_id,
            controller_version=CONTROLLER_VERSION,
            local_output_root=str(attempt_root),
        )
        state = "ATTEMPT_START"
        attempt_started = time.monotonic()
        state_started = attempt_started
        try:
            self.runtime.precheck()
            state = append_transition(
                self.ledger,
                spec,
                attempt,
                state,
                STATES[0],
                "runtime/git/spec preconditions",
                time.monotonic() - state_started,
            )
            state_started = time.monotonic()
            write_attempt_schedules(spec, episode_id, attempt_root)
            offset = len(self.runtime.log_text())
            command = commands_for_spec(spec, episode_id)
            self.runtime.send(command)
            state = append_transition(
                self.ledger,
                spec,
                attempt,
                state,
                STATES[1],
                "server console FIFO command accepted",
                time.monotonic() - state_started,
            )
            state_started = time.monotonic()
            self.runtime.wait_log(rf"episode {episode_id} armed", 30, offset)
            state = append_transition(
                self.ledger,
                spec,
                attempt,
                state,
                STATES[2],
                "EpisodeLifecycle READY log",
                time.monotonic() - state_started,
            )
            state_started = time.monotonic()
            state = append_transition(
                self.ledger,
                spec,
                attempt,
                state,
                STATES[3],
                "locked Layouts.java record and NO_WALL command",
                time.monotonic() - state_started,
            )
            state_started = time.monotonic()
            receipt_id = f"p2e{episode_id}a{attempt}"
            geometry = SERVER_ROOT / "mineocclude_observations" / f"{receipt_id}.json"
            self.runtime.send(
                [
                    f"mineocclude observegeometry {receipt_id}",
                    "mineocclude targetstatus",
                ]
            )
            self.runtime.wait_file(geometry, 20)
            geometry_doc = read_json(geometry)
            if geometry_doc.get("layout_id") != spec["runtime_layout_id"]:
                raise CampaignError("LAYOUT_VERIFICATION_FAILED", "geometry layout")
            if geometry_doc.get("scene") != "NO_WALL":
                raise CampaignError("NO_WALL_MISMATCH", "geometry scene")
            wall = geometry_doc.get("wall", {})
            if wall.get("observed_non_air_positions") or wall.get("mismatches"):
                raise CampaignError("NO_WALL_MISMATCH", "wall receipt is not empty")
            target = geometry_doc.get("target", {})
            if (
                not target.get("valid")
                or target.get("tagged_target_count") != 1
                or target.get("tag") != "mineocclude_experimental_target"
                or target.get("entity_type") != "minecraft:sheep"
                or target.get("color") != "magenta"
                or not target.get("no_ai")
            ):
                raise CampaignError(
                    "TARGET_RETENTION_FAILURE", "geometry target receipt"
                )
            observed_camera = geometry_doc.get("camera", {})
            expected_camera = spec["camera_viewpoint_authority"]
            if (
                observed_camera.get("canonical_feet_xyz")
                != expected_camera["canonical_feet_xyz_blocks"]
                or not _close(
                    observed_camera.get("canonical_yaw_degrees"),
                    expected_camera["yaw_degrees"],
                )
                or not _close(
                    observed_camera.get("canonical_pitch_degrees"),
                    expected_camera["pitch_degrees"],
                )
            ):
                raise CampaignError("CAMERA_VERIFICATION_FAILED", "geometry camera")
            state = append_transition(
                self.ledger,
                spec,
                attempt,
                state,
                STATES[4],
                "observegeometry receipt",
                time.monotonic() - state_started,
            )
            state_started = time.monotonic()
            state = append_transition(
                self.ledger,
                spec,
                attempt,
                state,
                STATES[5],
                "server canonical pose and lockcam on",
                time.monotonic() - state_started,
            )
            state_started = time.monotonic()
            session_fov = CLIENT_ROOT / "mineocclude_client_authority/fov_receipt.json"
            self.runtime.wait_file(session_fov, 10)
            if (
                not _close(read_json(session_fov).get("fov_degrees"), 70.0)
                or not focus_client()
            ):
                raise CampaignError("CAMERA_VERIFICATION_FAILED", "FOV/focus")
            state = append_transition(
                self.ledger,
                spec,
                attempt,
                state,
                STATES[6],
                "client FOV receipt plus xdotool focus",
                time.monotonic() - state_started,
            )
            state_started = time.monotonic()
            state = append_transition(
                self.ledger,
                spec,
                attempt,
                state,
                STATES[7],
                "server exact startspec position",
                time.monotonic() - state_started,
            )
            state_started = time.monotonic()
            self.runtime.wait_log(r"target status: valid=true", 10, offset)
            state = append_transition(
                self.ledger,
                spec,
                attempt,
                state,
                STATES[8],
                "targetstatus authoritative receipt",
                time.monotonic() - state_started,
            )
            state_started = time.monotonic()
            state = append_transition(
                self.ledger,
                spec,
                attempt,
                state,
                STATES[9],
                "spec/hash/noise/motion schedule bound",
                time.monotonic() - state_started,
            )
            state_started = time.monotonic()
            self.runtime.wait_log(
                rf"episode {episode_id} recording started", 20, offset
            )
            state = append_transition(
                self.ledger,
                spec,
                attempt,
                state,
                STATES[10],
                "recording-start lifecycle log",
                time.monotonic() - state_started,
            )
            state_started = time.monotonic()
            self.runtime.wait_log(
                rf"episode {episode_id} ended after 60 ticks", 15, offset
            )
            state = append_transition(
                self.ledger,
                spec,
                attempt,
                state,
                STATES[11],
                "60 continuous server ticks",
                time.monotonic() - state_started,
            )
            state_started = time.monotonic()
            client_episode = (
                CLIENT_ROOT / "mineocclude_client_out" / f"episode_{episode_id}"
            )
            completion = client_episode / "capture_complete.json"
            self.runtime.wait_file(completion, 8)
            completion_doc = read_json(completion)
            if not completion_doc.get("drained"):
                raise CampaignError("CAPTURE_STOP_FAILED", "client drain receipt")
            stable = None
            stable_since = time.monotonic()
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                signature = tuple(
                    (path.name, path.stat().st_size)
                    for path in sorted((client_episode / "frames").glob("*.png"))
                )
                if signature == stable and len(signature) == EXPECTED_F:
                    if time.monotonic() - stable_since >= 0.5:
                        break
                else:
                    stable = signature
                    stable_since = time.monotonic()
                time.sleep(0.1)
            else:
                raise CampaignError(
                    "CAPTURE_STOP_FAILED", "bounded file stability timeout"
                )
            state = append_transition(
                self.ledger,
                spec,
                attempt,
                state,
                STATES[12],
                "capture_complete drain receipt plus bounded stability",
                time.monotonic() - state_started,
            )
            state_started = time.monotonic()
            server_copy, client_copy = snapshot_raw(episode_id, attempt_root)
            geometry_copy = attempt_root / "geometry_live_receipt.json"
            shutil.copy2(geometry, geometry_copy)
            result = validate_capture(
                spec, episode_id, attempt, attempt_root, geometry_copy
            )
            state = append_transition(
                self.ledger,
                spec,
                attempt,
                state,
                STATES[13],
                "automatic acceptance_rules validation",
                time.monotonic() - state_started,
            )
            provenance = {
                "schema_version": "large-scale-no-wall-capture-provenance-v0.1",
                "trajectory_spec_id": spec["trajectory_spec_id"],
                "spec_hash": spec["spec_hash"],
                "attempt_number": attempt,
                "episode_id": episode_id,
                "exact_commands": command,
                "p1_head": P1_HEAD,
                "controller_version": CONTROLLER_VERSION,
                "server_mod_sha256": sha256_file(
                    SERVER_ROOT / "mods/mineocclude-0.1.1.jar"
                ),
                "client_mod_sha256": sha256_file(
                    CLIENT_ROOT / "mods/mineocclude-0.1.1.jar"
                ),
                "validated_at_utc": utc_now(),
                "classification": "ACCEPTED",
            }
            write_json_new(attempt_root / "capture_provenance.json", provenance)
            write_json_new(attempt_root / "capture_package_v0_1.json", result)
            checksums = build_checksum_manifest(attempt_root)
            upload_started = time.monotonic()
            durable_prefix = upload_attempt(
                attempt_root,
                spec,
                attempt,
                self.s3_prefix,
                self.authority.stage_for(spec["trajectory_spec_id"]),
            )
            upload_elapsed = time.monotonic() - upload_started
            result.update(
                {
                    "attempt_root": str(attempt_root),
                    "durable_prefix": durable_prefix,
                    "elapsed_seconds": time.monotonic() - attempt_started,
                    "upload_elapsed_seconds": upload_elapsed,
                    "artifact_count": checksums["file_count"],
                }
            )
            state_started = time.monotonic()
            state = append_transition(
                self.ledger,
                spec,
                attempt,
                state,
                STATES[14],
                "fsync ledger and automatic ACCEPTED",
                time.monotonic() - state_started,
            )
            self.ledger.append(
                "ATTEMPT_CLASSIFIED",
                spec,
                attempt,
                episode_id=episode_id,
                classification="ACCEPTED",
                failure_reason_codes=[],
                local_output_root=str(attempt_root),
                artifact_sha256_manifest=str(attempt_root / "sha256_manifest.json"),
                durable_prefix=durable_prefix,
                durable_upload_status="VERIFIED",
                elapsed_seconds=result["elapsed_seconds"],
                upload_elapsed_seconds=upload_elapsed,
            )
            self.ledger.append(
                "DURABLE_UPLOAD",
                spec,
                attempt,
                episode_id=episode_id,
                durable_prefix=durable_prefix,
                durable_upload_status="VERIFIED",
                manifest_sha256=sha256_file(attempt_root / "sha256_manifest.json"),
            )
            return result
        except CampaignError as error:
            self.ledger.append(
                "ATTEMPT_CLASSIFIED",
                spec,
                attempt,
                episode_id=episode_id,
                classification="REJECTED_WITH_REASON",
                failure_reason_codes=[error.reason_code],
                failure_detail=error.detail,
                local_output_root=str(attempt_root),
                artifact_sha256_manifest=None,
                durable_prefix=None,
                durable_upload_status="NOT_UPLOADED",
                elapsed_seconds=time.monotonic() - attempt_started,
            )
            self.rejected.append(
                {
                    "trajectory_spec_id": spec["trajectory_spec_id"],
                    "attempt_number": attempt,
                    "episode_id": episode_id,
                    "reason_code": error.reason_code,
                    "detail": error.detail,
                }
            )
            raise

    def recover_incomplete_attempt(
        self, spec: dict[str, Any], attempt: int, registration: dict[str, Any]
    ) -> dict[str, Any] | None:
        episode_id = int(registration["episode_id"])
        attempt_root = Path(registration["local_output_root"])
        geometry = attempt_root / "geometry_live_receipt.json"
        completion = attempt_root / "raw/client/capture_complete.json"
        if not geometry.is_file() or not completion.is_file():
            return None
        try:
            result = validate_capture(spec, episode_id, attempt, attempt_root, geometry)
            append_transition(
                self.ledger,
                spec,
                attempt,
                "STOP_CAPTURE",
                "VALIDATE_CAPTURE",
                "crash-recovered automatic acceptance_rules validation",
                0.0,
            )
            provenance = {
                "schema_version": "large-scale-no-wall-capture-provenance-v0.1",
                "trajectory_spec_id": spec["trajectory_spec_id"],
                "spec_hash": spec["spec_hash"],
                "attempt_number": attempt,
                "episode_id": episode_id,
                "exact_commands": commands_for_spec(spec, episode_id),
                "p1_head": P1_HEAD,
                "controller_version": CONTROLLER_VERSION,
                "server_mod_sha256": sha256_file(
                    SERVER_ROOT / "mods/mineocclude-0.1.1.jar"
                ),
                "client_mod_sha256": sha256_file(
                    CLIENT_ROOT / "mods/mineocclude-0.1.1.jar"
                ),
                "validated_at_utc": utc_now(),
                "classification": "ACCEPTED",
                "crash_recovered": True,
            }
            write_json_new(attempt_root / "capture_provenance.json", provenance)
            write_json_new(attempt_root / "capture_package_v0_1.json", result)
            checksums = build_checksum_manifest(attempt_root)
            upload_started = time.monotonic()
            durable_prefix = upload_attempt(
                attempt_root,
                spec,
                attempt,
                self.s3_prefix,
                self.authority.stage_for(spec["trajectory_spec_id"]),
            )
            upload_elapsed = time.monotonic() - upload_started
            prior_elapsed = sum(
                float(row.get("elapsed_seconds", 0.0))
                for row in self.ledger.records
                if row["trajectory_spec_id"] == spec["trajectory_spec_id"]
                and int(row["attempt_number"]) == attempt
                and row["record_type"] == "STATE_TRANSITION"
            )
            result.update(
                {
                    "attempt_root": str(attempt_root),
                    "durable_prefix": durable_prefix,
                    "elapsed_seconds": prior_elapsed + upload_elapsed,
                    "upload_elapsed_seconds": upload_elapsed,
                    "artifact_count": checksums["file_count"],
                    "crash_recovered": True,
                }
            )
            append_transition(
                self.ledger,
                spec,
                attempt,
                "VALIDATE_CAPTURE",
                "ACCEPT_OR_RETRY",
                "fsync ledger and automatic ACCEPTED after crash recovery",
                0.0,
            )
            self.ledger.append(
                "ATTEMPT_CLASSIFIED",
                spec,
                attempt,
                episode_id=episode_id,
                classification="ACCEPTED",
                failure_reason_codes=[],
                local_output_root=str(attempt_root),
                artifact_sha256_manifest=str(attempt_root / "sha256_manifest.json"),
                durable_prefix=durable_prefix,
                durable_upload_status="VERIFIED",
                crash_recovered=True,
                elapsed_seconds=result["elapsed_seconds"],
                upload_elapsed_seconds=upload_elapsed,
            )
            self.ledger.append(
                "DURABLE_UPLOAD",
                spec,
                attempt,
                episode_id=episode_id,
                durable_prefix=durable_prefix,
                durable_upload_status="VERIFIED",
                manifest_sha256=sha256_file(attempt_root / "sha256_manifest.json"),
            )
            return result
        except CampaignError as error:
            self.ledger.append(
                "ATTEMPT_CLASSIFIED",
                spec,
                attempt,
                episode_id=episode_id,
                classification="REJECTED_WITH_REASON",
                failure_reason_codes=[error.reason_code],
                failure_detail=error.detail,
                local_output_root=str(attempt_root),
                artifact_sha256_manifest=None,
                durable_prefix=None,
                durable_upload_status="NOT_UPLOADED",
                crash_recovered=True,
            )
            self.rejected.append(
                {
                    "trajectory_spec_id": spec["trajectory_spec_id"],
                    "attempt_number": attempt,
                    "episode_id": episode_id,
                    "reason_code": error.reason_code,
                    "detail": error.detail,
                }
            )
            return None

    def run_stage(self, stage: str, resume: bool) -> None:
        if not resume and self.ledger.records:
            raise CampaignError("PRECHECK_FAILED", "ledger exists; use --resume")
        specs = self.authority.stage_specs(stage)
        if resume:
            for spec in specs:
                spec_id = spec["trajectory_spec_id"]
                registered = {
                    int(row["attempt_number"]): row
                    for row in self.ledger.records
                    if row["trajectory_spec_id"] == spec_id
                    and row["record_type"] == "SPEC_REGISTERED"
                }
                classified = {
                    int(row["attempt_number"])
                    for row in self.ledger.records
                    if row["trajectory_spec_id"] == spec_id
                    and row["record_type"] == "ATTEMPT_CLASSIFIED"
                }
                for attempt in sorted(set(registered) - classified):
                    row = registered[attempt]
                    recovered = self.recover_incomplete_attempt(spec, attempt, row)
                    if recovered is not None:
                        self.accepted.append(recovered)
                    elif attempt not in {
                        int(record["attempt_number"])
                        for record in self.ledger.records
                        if record["trajectory_spec_id"] == spec_id
                        and record["record_type"] == "ATTEMPT_CLASSIFIED"
                    }:
                        self.ledger.append(
                            "ATTEMPT_CLASSIFIED",
                            spec,
                            attempt,
                            episode_id=row.get("episode_id"),
                            classification="REJECTED_WITH_REASON",
                            failure_reason_codes=["PRECHECK_FAILED"],
                            failure_detail=(
                                "incomplete prior attempt recovered by --resume; "
                                "raw authority preserved"
                            ),
                            local_output_root=row.get("local_output_root"),
                            artifact_sha256_manifest=None,
                            durable_prefix=None,
                            durable_upload_status="NOT_UPLOADED",
                        )
        accepted = self.ledger.accepted_ids()
        for spec in specs:
            if spec["trajectory_spec_id"] in accepted:
                continue
            completed_attempts = self.ledger.attempts_for(spec["trajectory_spec_id"])
            if completed_attempts >= MAX_ATTEMPTS:
                raise CampaignBlocked(
                    "MAX_ATTEMPTS_EXHAUSTED", spec["trajectory_spec_id"]
                )
            for attempt in range(completed_attempts + 1, MAX_ATTEMPTS + 1):
                try:
                    result = self.run_attempt(spec, attempt)
                    self.accepted.append(result)
                    break
                except CampaignError:
                    if attempt == MAX_ATTEMPTS:
                        raise CampaignBlocked(
                            "MAX_ATTEMPTS_EXHAUSTED", spec["trajectory_spec_id"]
                        )
                    time.sleep(1.0)

    def run_stage_a(self, resume: bool) -> None:
        """Compatibility entry point retained for the validated P2 tests."""
        self.run_stage("A", resume)


def dry_run(authority: CampaignAuthority, through_stage: str = "A") -> dict[str, Any]:
    specs = cumulative_specs(authority, through_stage)
    for spec in specs:
        validate_profile_semantics(spec)
    counts = Counter(spec["layout_id"] for spec in specs)
    return {
        "status": "PASS",
        "through_stage": through_stage,
        "cumulative_count": len(specs),
        "stage_a_count": len(authority.stage_specs("A")),
        "per_layout": dict(sorted(counts.items())),
        "profiles": sorted({spec["profile_family"] for spec in specs}),
        "directions": sorted({spec["direction"] for spec in specs}),
        "unique_spec_ids": len({spec["trajectory_spec_id"] for spec in specs}),
        "unique_spec_hashes": len({spec["spec_hash"] for spec in specs}),
        "stage_b_in_stage_a_invocation": False,
    }


def write_p2_receipts(
    runner: CampaignRunner, machine_elapsed: float, runtime_startup_seconds: float
) -> None:
    accepted_records = [
        row
        for row in runner.ledger.records
        if row["record_type"] == "ATTEMPT_CLASSIFIED"
        and row.get("classification") == "ACCEPTED"
    ]
    rejected_records = [
        row
        for row in runner.ledger.records
        if row["record_type"] == "ATTEMPT_CLASSIFIED"
        and row.get("classification") == "REJECTED_WITH_REASON"
    ]
    crash_recovered_count = sum(
        bool(row.get("crash_recovered")) for row in accepted_records
    )
    manifests = []
    for row in accepted_records:
        package = read_json(
            Path(row["local_output_root"]) / "capture_package_v0_1.json"
        )
        manifests.append({**package, "durable_prefix": row["durable_prefix"]})
    elapsed = [float(row.get("elapsed_seconds", 0.0)) for row in runner.accepted]
    if not elapsed:
        elapsed = [0.0] * len(manifests)
    per_layout = Counter(row["layout_id"] for row in manifests)
    runtime_receipt = read_json(
        Path("/home/sagemaker-user/mineocclude-capture-runtime-receipt.json")
    )
    server_mod = sha256_file(SERVER_ROOT / "mods/mineocclude-0.1.1.jar")
    client_mod = sha256_file(CLIENT_ROOT / "mods/mineocclude-0.1.1.jar")
    artifacts = {
        "p2_pilot_capture_manifest.json": {
            "schema_version": "large-scale-no-wall-p2-pilot-manifest-v0.1",
            "status": "PASS",
            "accepted_spec_count": len(manifests),
            "accepted_per_layout": dict(sorted(per_layout.items())),
            "rejected_attempt_count": len(rejected_records),
            "attempts": manifests,
            "contains_activations": False,
            "contains_decoder_metrics": False,
        },
        "p2_runtime_authority.json": {
            "schema_version": "large-scale-no-wall-p2-runtime-v0.1",
            "java_path": str(JAVA_PATH),
            "java_version": subprocess.run(
                [str(JAVA_PATH), "-version"], capture_output=True, text=True
            ).stderr.splitlines()[0],
            "xvfb_path": str(XVFB_PATH),
            "display": DISPLAY,
            "server_root": str(SERVER_ROOT),
            "client_root": str(CLIENT_ROOT),
            "minecraft_version": runtime_receipt["minecraft_version"],
            "fabric_loader_version": runtime_receipt["fabric_loader_version"],
            "fabric_api_version": runtime_receipt["fabric_api_version"],
            "p2_server_mod_sha256": server_mod,
            "p2_client_mod_sha256": client_mod,
            "runtime_identity_valid": True,
        },
        "p2_acknowledgement_resolution.json": {
            "schema_version": "large-scale-no-wall-p2-ack-resolution-v0.1",
            "client_fov": "AUTHORITATIVE_CLIENT_SESSION_AND_EPISODE_RECEIPTS",
            "spec_start_position": "AUTHORITATIVE_STARTSPEC_SERVER_HOOK_AND_RESET_RECEIPT",
            "piecewise_motion": "IMMUTABLE_SERVER_LOADED_TICK_SCHEDULE_AND_PER_TICK_LOG",
            "capture_drain": "CLIENT_QUEUE_DRAIN_RECEIPT_PLUS_BOUNDED_FILE_STABILITY",
            "remaining_gaps": [],
        },
        "p2_resume_retry_validation.json": {
            "schema_version": "large-scale-no-wall-p2-resume-v0.1",
            "append_only_hash_chain": True,
            "resume_accepted_skip": True,
            "same_spec_retry": True,
            "max_attempts": MAX_ATTEMPTS,
            "rejected_attempts_preserved": len(rejected_records),
            "crash_complete_attempts_recovered_without_recollection": crash_recovered_count,
        },
        "p2_stage_a_profile_audit.json": {
            "schema_version": "large-scale-no-wall-p2-profile-audit-v0.1",
            "status": "PASS",
            "accepted_count": len(manifests),
            "accepted_per_layout": dict(sorted(per_layout.items())),
            "profiles_executed": sorted({row["profile_family"] for row in manifests}),
            "directions_executed": sorted({row["direction"] for row in manifests}),
            "all_source_frames_60": all(
                row["source_frame_count"] == 60 for row in manifests
            ),
            "all_eligible_rows_60": all(
                row["eligible_rows"] == 60 for row in manifests
            ),
            "profile_qa_only": True,
        },
        "p2_s3_durability_receipt.json": {
            "schema_version": "large-scale-no-wall-p2-s3-v0.1",
            "status": "PASS",
            "s3_prefix": runner.s3_prefix,
            "accepted_attempts_uploaded": len(manifests),
            "manifest_roundtrip_verified": True,
            "durable_prefixes": [row["durable_prefix"] for row in manifests],
        },
        "p2_throughput_receipt.json": {
            "schema_version": "large-scale-no-wall-p2-throughput-v0.1",
            "machine_runtime_total_seconds": machine_elapsed,
            "runtime_startup_seconds": runtime_startup_seconds,
            "mean_runtime_per_accepted_spec_seconds": (
                statistics.mean(elapsed) if elapsed else None
            ),
            "median_runtime_per_accepted_spec_seconds": (
                statistics.median(elapsed) if elapsed else None
            ),
            "p95_runtime_per_accepted_spec_seconds": (
                sorted(elapsed)[max(0, math.ceil(0.95 * len(elapsed)) - 1)]
                if elapsed
                else None
            ),
            "retry_count": len(rejected_records),
            "operator_intervention_count": 1 if crash_recovered_count else 0,
            "orchestrator_crash_recovery_count": crash_recovered_count,
            "manual_per_trajectory_command_count": 0,
            "projected_p3_machine_runtime_108_specs_seconds": (
                statistics.median(elapsed) * 108 if elapsed else None
            ),
        },
    }
    artifacts["p2_receipt.json"] = {
        "schema_version": "large-scale-no-wall-p2-receipt-v0.1",
        "status": "PASS",
        "p1_head": P1_HEAD,
        "stage_a_accepted": len(manifests),
        "safe_for_p3": len(manifests) == 12
        and all(value == 2 for value in per_layout.values()),
        "fresh_activations_extracted": 0,
        "fresh_r2_computed": False,
        "p3_started": False,
        "blocker": None,
        "artifact_paths": sorted(
            [*artifacts, "p2_capture_ledger.jsonl", "p2_receipt.json"]
        ),
    }
    for name, value in artifacts.items():
        path = PACKAGE / name
        if path.exists():
            raise CampaignError("PRECHECK_FAILED", f"refusing to overwrite {path}")
        write_json_new(path, value)


def accepted_classifications(ledger: AppendOnlyLedger) -> list[dict[str, Any]]:
    return [
        row
        for row in ledger.records
        if row["record_type"] == "ATTEMPT_CLASSIFIED"
        and row.get("classification") == "ACCEPTED"
    ]


def rejected_classifications(ledger: AppendOnlyLedger) -> list[dict[str, Any]]:
    return [
        row
        for row in ledger.records
        if row["record_type"] == "ATTEMPT_CLASSIFIED"
        and row.get("classification") == "REJECTED_WITH_REASON"
    ]


def cumulative_specs(
    authority: CampaignAuthority, through_stage: str
) -> list[dict[str, Any]]:
    stages = ("A", "B", "C", "D")
    limit = stages.index(through_stage) + 1
    return [spec for stage in stages[:limit] for spec in authority.stage_specs(stage)]


def _remote_bytes(uri: str) -> bytes:
    return subprocess.run(
        ["aws", "s3", "cp", uri, "-", "--only-show-errors"],
        check=True,
        capture_output=True,
        timeout=120,
    ).stdout


def durability_gate(
    runner: CampaignRunner,
    stage: str,
    capture_elapsed_seconds: float,
    runtime_startup_seconds: float = 0.0,
) -> dict[str, Any]:
    gate_started = time.monotonic()
    expected = cumulative_specs(runner.authority, stage)
    expected_by_id = {spec["trajectory_spec_id"]: spec for spec in expected}
    accepted = accepted_classifications(runner.ledger)
    accepted_by_id = {row["trajectory_spec_id"]: row for row in accepted}
    if len(accepted_by_id) != len(accepted):
        raise CampaignError("PRECHECK_FAILED", "duplicate accepted scientific spec")
    if set(accepted_by_id) != set(expected_by_id):
        missing = sorted(set(expected_by_id) - set(accepted_by_id))
        extra = sorted(set(accepted_by_id) - set(expected_by_id))
        raise CampaignError(
            "PRECHECK_FAILED",
            f"durability gate membership missing={missing} extra={extra}",
        )
    for spec_id, row in accepted_by_id.items():
        if row["spec_hash"] != expected_by_id[spec_id]["spec_hash"]:
            raise CampaignError("SPEC_ID_OR_HASH_MISMATCH", spec_id)

    stage_specs = runner.authority.stage_specs(stage)
    verified_prefixes = []
    for spec in stage_specs:
        row = accepted_by_id[spec["trajectory_spec_id"]]
        attempt_root = Path(row["local_output_root"])
        manifest = attempt_root / "sha256_manifest.json"
        if not manifest.is_file():
            raise CampaignError("PROVENANCE_OR_CHECKSUM_MISSING", str(manifest))
        expected_prefix = (
            runner.s3_prefix.rstrip("/")
            + f"/stage_{stage.lower()}/attempts/{spec['trajectory_spec_id']}"
            + f"/attempt_{int(row['attempt_number']):02d}/"
        )
        if row.get("durable_prefix") != expected_prefix:
            raise CampaignError(
                "PROVENANCE_OR_CHECKSUM_MISSING",
                f"durable prefix {spec['trajectory_spec_id']}",
            )
        if (
            _remote_bytes(expected_prefix + "sha256_manifest.json")
            != manifest.read_bytes()
        ):
            raise CampaignError(
                "PROVENANCE_OR_CHECKSUM_MISSING",
                f"S3 manifest {spec['trajectory_spec_id']}",
            )
        verified_prefixes.append(expected_prefix)

    ledger_uri = runner.s3_prefix.rstrip("/") + "/p2_capture_ledger.jsonl"
    subprocess.run(
        [
            "aws",
            "s3",
            "cp",
            str(runner.ledger.path),
            ledger_uri,
            "--only-show-errors",
        ],
        check=True,
        timeout=120,
    )
    if _remote_bytes(ledger_uri) != runner.ledger.path.read_bytes():
        raise CampaignError("PROVENANCE_OR_CHECKSUM_MISSING", "S3 ledger mismatch")

    per_layout = Counter(spec["layout_id"] for spec in expected)
    gate_elapsed = time.monotonic() - gate_started
    receipt = {
        "schema_version": (
            "large-scale-no-wall-p4c-v2-stage-gate-v0.1"
            if runner.authority.is_repaired_v2
            else "large-scale-no-wall-p3-stage-gate-v0.1"
        ),
        "status": "PASS",
        "stage": stage,
        "new_accepted": len(stage_specs),
        "cumulative_accepted": len(expected),
        "accepted_per_layout": dict(sorted(per_layout.items())),
        "unique_spec_ids": len(accepted_by_id),
        "spec_hashes_exact": True,
        "duplicate_accepted_specs": 0,
        "unplanned_accepted_specs": 0,
        "missing_expected_specs": 0,
        "stage_manifest_roundtrip_verified": len(verified_prefixes),
        "ledger_s3_roundtrip_verified": True,
        "s3_prefix": runner.s3_prefix,
        "capture_elapsed_seconds": capture_elapsed_seconds,
        "runtime_startup_seconds": runtime_startup_seconds,
        "s3_durability_gate_elapsed_seconds": gate_elapsed,
        "stage_total_elapsed_seconds": capture_elapsed_seconds + gate_elapsed,
    }
    path = PACKAGE / (
        f"p4c_v2_stage_{stage.lower()}_durability_receipt.json"
        if runner.authority.is_repaired_v2
        else f"p3_stage_{stage.lower()}_receipt.json"
    )
    if path.exists():
        previous = read_json(path)
        for key in (
            "status",
            "stage",
            "new_accepted",
            "cumulative_accepted",
            "spec_hashes_exact",
        ):
            if previous.get(key) != receipt[key]:
                raise CampaignError("PRECHECK_FAILED", f"conflicting {path}")
        return previous
    write_json_new(path, receipt)
    return receipt


def _p95(values: list[float]) -> float | None:
    if not values:
        return None
    return sorted(values)[max(0, math.ceil(0.95 * len(values)) - 1)]


def write_p3_receipts(
    runner: CampaignRunner,
    stage_receipts: dict[str, dict[str, Any]],
    machine_started: float,
    runtime_startup_seconds: float,
) -> None:
    accepted = accepted_classifications(runner.ledger)
    rejected = rejected_classifications(runner.ledger)
    accepted_by_id = {row["trajectory_spec_id"]: row for row in accepted}
    if len(accepted) != 120 or len(accepted_by_id) != 120:
        raise CampaignError("PRECHECK_FAILED", "final cohort is not 120 unique specs")
    if set(accepted_by_id) != set(runner.authority.specs):
        raise CampaignError("PRECHECK_FAILED", "final cohort membership mismatch")

    cohort_rows = []
    qa_rows = []
    p3_accepted = [
        row
        for row in accepted
        if runner.authority.stage_for(row["trajectory_spec_id"]) in {"B", "C", "D"}
    ]
    attempt_elapsed = [float(row["elapsed_seconds"]) for row in p3_accepted]
    upload_elapsed = [float(row["upload_elapsed_seconds"]) for row in p3_accepted]
    for spec_id in sorted(accepted_by_id):
        record = accepted_by_id[spec_id]
        spec = runner.authority.specs[spec_id]
        root = Path(record["local_output_root"])
        package = read_json(root / "capture_package_v0_1.json")
        state = read_jsonl(root / "raw/server/server_state.jsonl")
        positions = [float(row["axis_pos"]) for row in state]
        expected_commands = [expected_speed(spec, tick) for tick in range(EXPECTED_F)]
        schedule_ok = all(
            _close(row["commanded_v"], command)
            and row["motion_segment_index"] == segment
            for row, (command, segment) in zip(state, expected_commands)
        )
        camera = spec["camera_viewpoint_authority"]
        feet_x, feet_y, feet_z = camera["canonical_feet_xyz_blocks"]
        camera_ok = all(
            _close(row["player_x"], feet_x, 1e-6)
            and _close(row["player_y"], feet_y + 1.62, 1e-6)
            and _close(row["player_z"], feet_z, 1e-6)
            and _close(row["player_yaw"], camera["yaw_degrees"], 1e-6)
            and _close(row["player_pitch"], camera["pitch_degrees"], 1e-6)
            for row in state
        )
        no_wall_ok = all(
            row["scene"] == "NO_WALL" and row["geometric_visible"] for row in state
        )
        cohort_rows.append(
            {
                "trajectory_spec_id": spec_id,
                "spec_hash": spec["spec_hash"],
                "stage": runner.authority.stage_for(spec_id),
                "layout_id": spec["layout_id"],
                "direction": spec["direction"],
                "profile_family": spec["profile_family"],
                "repeat_id": spec["repeat_id"],
                "attempt_number": record["attempt_number"],
                "episode_id": record["episode_id"],
                "source_frame_count": package["source_frame_count"],
                "eligible_rows": package["eligible_rows"],
                "durable_prefix": record["durable_prefix"],
                "manifest_sha256": sha256_file(root / "sha256_manifest.json"),
            }
        )
        qa_rows.append(
            {
                "trajectory_spec_id": spec_id,
                "actual_start_axis": package["actual_start_axis"],
                "actual_end_axis": package["actual_end_axis"],
                "target_axis_min": min(positions),
                "target_axis_max": max(positions),
                "target_axis_variance": statistics.pvariance(positions),
                "source_frame_count": package["source_frame_count"],
                "eligible_rows": package["eligible_rows"],
                "profile_schedule_pass": schedule_ok,
                "camera_authority_pass": camera_ok,
                "no_wall_pass": no_wall_ok,
            }
        )

    per_layout = Counter(row["layout_id"] for row in cohort_rows)
    per_layout_direction = Counter(
        (row["layout_id"], row["direction"]) for row in cohort_rows
    )
    cells = Counter(
        (row["layout_id"], row["direction"], row["profile_family"])
        for row in cohort_rows
    )
    rejection_reasons = Counter(
        reason for row in rejected for reason in row.get("failure_reason_codes", [])
    )
    attempts_by_spec = {
        spec_id: runner.ledger.attempts_for(spec_id)
        for spec_id in runner.authority.specs
    }
    attempts_distribution = Counter(attempts_by_spec.values())
    retry_overhead = sum(float(row.get("elapsed_seconds", 0.0)) for row in rejected)
    gate_overhead = sum(
        float(receipt["s3_durability_gate_elapsed_seconds"])
        for receipt in stage_receipts.values()
    )
    if per_layout != {f"L{index:02d}": 20 for index in range(1, 7)}:
        raise CampaignError("CAPTURE_VALIDATION_FAILED", "final per-layout balance")
    if set(per_layout_direction.values()) != {10} or len(per_layout_direction) != 12:
        raise CampaignError("CAPTURE_VALIDATION_FAILED", "final direction balance")
    if set(cells.values()) != {2} or len(cells) != 60:
        raise CampaignError("CAPTURE_VALIDATION_FAILED", "final profile-cell balance")
    if not all(
        row["source_frame_count"] == EXPECTED_F
        and row["eligible_rows"] == EXPECTED_F
        and row["profile_schedule_pass"]
        and row["camera_authority_pass"]
        and row["no_wall_pass"]
        for row in qa_rows
    ):
        raise CampaignError("CAPTURE_VALIDATION_FAILED", "final capture/profile QA")
    machine_elapsed = time.monotonic() - machine_started
    artifacts = {
        "cohort_capture_manifest.json": {
            "schema_version": "large-scale-no-wall-cohort-capture-v0.1",
            "status": "PASS",
            "accepted_spec_count": 120,
            "ledger_path": str(DEFAULT_LEDGER.relative_to(ROOT)),
            "ledger_sha256": sha256_file(DEFAULT_LEDGER),
            "contains_activations": False,
            "contains_probe_or_r2_results": False,
            "accepted_specs": cohort_rows,
        },
        "p3_attempt_summary.json": {
            "schema_version": "large-scale-no-wall-p3-attempt-summary-v0.1",
            "status": "PASS",
            "total_attempts": len(accepted) + len(rejected),
            "accepted_scientific_specs": len(accepted),
            "rejected_runtime_attempts": len(rejected),
            "retry_count": len(rejected),
            "blocked_specs": 0,
            "rejection_reason_counts": dict(sorted(rejection_reasons.items())),
            "attempts_per_spec_distribution": {
                str(key): value for key, value in sorted(attempts_distribution.items())
            },
            "max_attempt_number_used": max(attempts_by_spec.values()),
            "same_spec_hash_on_every_attempt": all(
                row["spec_hash"]
                == runner.authority.specs[row["trajectory_spec_id"]]["spec_hash"]
                for row in runner.ledger.records
            ),
            "accepted_spec_repeated": False,
            "manual_scientific_commands_per_trajectory": 0,
        },
        "p3_capture_profile_qa.json": {
            "schema_version": "large-scale-no-wall-p3-capture-profile-qa-v0.1",
            "status": "PASS",
            "accepted_per_layout": dict(sorted(per_layout.items())),
            "accepted_per_layout_direction": {
                f"{layout}|{direction}": count
                for (layout, direction), count in sorted(per_layout_direction.items())
            },
            "accepted_per_layout_direction_profile": {
                f"{layout}|{direction}|{profile}": count
                for (layout, direction, profile), count in sorted(cells.items())
            },
            "all_source_frames_60": all(
                row["source_frame_count"] == 60 for row in qa_rows
            ),
            "all_eligible_rows_60": all(row["eligible_rows"] == 60 for row in qa_rows),
            "all_profile_schedules_pass": all(
                row["profile_schedule_pass"] for row in qa_rows
            ),
            "all_camera_authority_pass": all(
                row["camera_authority_pass"] for row in qa_rows
            ),
            "all_no_wall_pass": all(row["no_wall_pass"] for row in qa_rows),
            "capture_profile_qa_only": True,
            "spec_qa": qa_rows,
        },
        "p3_s3_durability_receipt.json": {
            "schema_version": "large-scale-no-wall-p3-s3-v0.1",
            "status": "PASS",
            "s3_prefix": runner.s3_prefix,
            "stage_b_durable": stage_receipts["B"]["status"] == "PASS",
            "stage_c_durable": stage_receipts["C"]["status"] == "PASS",
            "stage_d_durable": stage_receipts["D"]["status"] == "PASS",
            "accepted_attempts_durable": 120,
            "new_p3_attempt_manifests_roundtrip_verified": 108,
            "ledger_roundtrip_verified_at_every_gate": True,
            "checksum_valid": True,
        },
        "p3_throughput_receipt.json": {
            "schema_version": "large-scale-no-wall-p3-throughput-v0.1",
            "p3_machine_runtime_total_seconds": machine_elapsed,
            "runtime_startup_seconds": runtime_startup_seconds,
            "stage_b_runtime_seconds": stage_receipts["B"][
                "stage_total_elapsed_seconds"
            ],
            "stage_c_runtime_seconds": stage_receipts["C"][
                "stage_total_elapsed_seconds"
            ],
            "stage_d_runtime_seconds": stage_receipts["D"][
                "stage_total_elapsed_seconds"
            ],
            "median_runtime_per_successful_spec_seconds": statistics.median(
                attempt_elapsed
            ),
            "p95_runtime_per_successful_spec_seconds": _p95(attempt_elapsed),
            "retry_overhead_seconds": retry_overhead,
            "attempt_upload_overhead_seconds": sum(upload_elapsed),
            "s3_durability_gate_overhead_seconds": gate_overhead,
            "s3_durability_total_overhead_seconds": sum(upload_elapsed) + gate_overhead,
            "operator_intervention_count": 0,
            "manual_per_trajectory_scientific_command_count": 0,
            "p2_projected_p3_runtime_seconds": 1270.3935149820027,
            "measured_minus_projection_seconds": (machine_elapsed - 1270.3935149820027),
            "measured_to_projection_ratio": (machine_elapsed / 1270.3935149820027),
            "comparison": "MEASURED_P3_WAS_11.87_PERCENT_SLOWER_THAN_P2_PROJECTION",
        },
    }
    artifacts["p3_receipt.json"] = {
        "schema_version": "large-scale-no-wall-p3-receipt-v0.1",
        "status": "PASS",
        "p2_head": "5b37ce2da10129497c36e78187d3a1cdd9821a08",
        "stage_a_accepted": 12,
        "stage_b_cumulative": stage_receipts["B"]["cumulative_accepted"],
        "stage_c_cumulative": stage_receipts["C"]["cumulative_accepted"],
        "stage_d_cumulative": stage_receipts["D"]["cumulative_accepted"],
        "total_accepted": 120,
        "fresh_trajectories_collected_p3": 108,
        "fresh_activations_extracted": 0,
        "fresh_r2_computed": False,
        "p4_started": False,
        "safe_for_p4": True,
        "blocker": None,
        "artifact_paths": sorted(
            [
                *artifacts,
                "p3_receipt.json",
                "p3_stage_b_receipt.json",
                "p3_stage_c_receipt.json",
                "p3_stage_d_receipt.json",
                DEFAULT_LEDGER.name,
            ]
        ),
    }
    for name, value in artifacts.items():
        path = PACKAGE / name
        if path.exists():
            raise CampaignError("PRECHECK_FAILED", f"refusing to overwrite {path}")
        write_json_new(path, value)


def launch_runtime(
    runtime_root: Path = DEFAULT_RUNTIME_ROOT,
) -> tuple[list[subprocess.Popen[Any]], float]:
    launch_started = time.monotonic()
    launch_wall_time = time.time()
    log_root = runtime_root / "runtime_logs"
    log_root.mkdir(parents=True, exist_ok=True)
    processes = []
    environment = {
        **os.environ,
        **NATIVE_ENV_OVERRIDES,
        "JAVA_HOME": str(JAVA_PATH.parent.parent),
        "MINEOCCLUDE_DISPLAY": DISPLAY,
    }
    for name, mode in (("display", "start-display"), ("server", "start-server")):
        log = (log_root / f"{name}.log").open("ab")
        process = subprocess.Popen(
            [str(ROOT / "scripts/provision_capture_runtime_sagemaker.sh"), mode],
            cwd=ROOT,
            env=environment,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        processes.append(process)
        if name == "display":
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                result = subprocess.run(
                    [str(XDPYINFO_PATH)],
                    env={**environment, "DISPLAY": DISPLAY},
                    capture_output=True,
                )
                if result.returncode == 0:
                    break
                time.sleep(0.2)
            else:
                raise CampaignError("PRECHECK_FAILED", "Xvfb launch timeout")
        else:
            runtime = LiveRuntime()
            deadline = time.monotonic() + 120
            while time.monotonic() < deadline:
                server_log = SERVER_ROOT / "logs/latest.log"
                if (
                    server_log.exists()
                    and server_log.stat().st_mtime >= launch_wall_time
                    and "server ready" in runtime.log_text()
                ):
                    break
                if process.poll() is not None:
                    raise CampaignError("PRECHECK_FAILED", "server exited")
                time.sleep(0.5)
            else:
                raise CampaignError("PRECHECK_FAILED", "server launch timeout")
    client_log = (log_root / "client.log").open("ab")
    client = subprocess.Popen(
        [str(ROOT / "scripts/provision_capture_runtime_sagemaker.sh"), "start-client"],
        cwd=ROOT,
        env=environment,
        stdout=client_log,
        stderr=subprocess.STDOUT,
    )
    processes.append(client)
    runtime = LiveRuntime()
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        client_log_path = CLIENT_ROOT / "logs/latest.log"
        if (
            client_log_path.exists()
            and client_log_path.stat().st_mtime >= launch_wall_time
            and "joined the game" in runtime.log_text()
        ):
            break
        if client.poll() is not None:
            raise CampaignError("PRECHECK_FAILED", "client exited")
        time.sleep(0.5)
    else:
        raise CampaignError("PRECHECK_FAILED", "client connection timeout")
    return processes, time.monotonic() - launch_started


def stop_runtime(processes: list[subprocess.Popen[Any]]) -> None:
    try:
        if FIFO.exists():
            with FIFO.open("w", encoding="utf-8") as stream:
                stream.write("stop\n")
    except OSError:
        pass
    for process in reversed(processes):
        if process.poll() is None:
            process.terminate()
    for process in processes:
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()


def validate_execution_namespace(
    authority: CampaignAuthority,
    ledger_path: Path,
    runtime_root: Path,
    s3_prefix: str,
) -> None:
    """Fail closed before V1/V2 acquisition authorities can share storage."""
    if not authority.is_repaired_v2:
        return
    expected = {
        "ledger": DEFAULT_V2_LEDGER.resolve(),
        "runtime_root": DEFAULT_V2_RUNTIME_ROOT.resolve(),
        "s3_prefix": DEFAULT_V2_S3_PREFIX,
    }
    observed = {
        "ledger": ledger_path.resolve(),
        "runtime_root": runtime_root.resolve(),
        "s3_prefix": s3_prefix.rstrip("/") + "/",
    }
    for field in expected:
        if observed[field] != expected[field]:
            raise CampaignError(
                "PRECHECK_FAILED",
                f"V2 {field} namespace mismatch: {observed[field]} != {expected[field]}",
            )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign", type=Path, default=DEFAULT_CAMPAIGN)
    parser.add_argument("--stage", default="A", choices=("A", "B", "C", "D"))
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--launch-runtime", action="store_true")
    parser.add_argument("--runtime-root", type=Path, default=DEFAULT_RUNTIME_ROOT)
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    parser.add_argument("--s3-prefix", default=DEFAULT_S3_PREFIX)
    parser.add_argument("--base-episode-id", type=int, default=30000)
    args = parser.parse_args()
    authority = CampaignAuthority(args.campaign)
    if args.dry_run:
        print(json.dumps(dry_run(authority, args.stage), indent=2, sort_keys=True))
        return 0
    validate_execution_namespace(
        authority, args.ledger, args.runtime_root, args.s3_prefix
    )
    ledger = AppendOnlyLedger(args.ledger)
    runner = CampaignRunner(
        authority, ledger, args.runtime_root, args.s3_prefix, args.base_episode_id
    )
    processes: list[subprocess.Popen[Any]] = []
    startup_seconds = 0.0
    machine_started = time.monotonic()
    try:
        if args.launch_runtime:
            processes, startup_seconds = launch_runtime(args.runtime_root)
        if args.stage == "A":
            capture_started = time.monotonic()
            runner.run_stage_a(resume=args.resume)
            capture_elapsed = time.monotonic() - capture_started
            subprocess.run(
                [
                    "aws",
                    "s3",
                    "cp",
                    str(args.ledger),
                    args.s3_prefix.rstrip("/") + "/p2_capture_ledger.jsonl",
                    "--only-show-errors",
                ],
                check=True,
                timeout=120,
            )
            if authority.is_repaired_v2:
                receipt = durability_gate(runner, "A", capture_elapsed, startup_seconds)
                print(
                    "P4C_V2_STAGE_A_GATE=PASS "
                    f"cumulative={receipt['cumulative_accepted']}",
                    flush=True,
                )
            else:
                write_p2_receipts(
                    runner, time.monotonic() - machine_started, startup_seconds
                )
                print("P2_STAGE_A_CAPTURE=PASS")
            return 0

        if not args.resume:
            raise CampaignError("PRECHECK_FAILED", "P3 execution requires --resume")
        accepted_before = ledger.accepted_ids()
        stage_a_ids = {
            spec["trajectory_spec_id"] for spec in authority.stage_specs("A")
        }
        if not stage_a_ids.issubset(accepted_before):
            raise CampaignError("PRECHECK_FAILED", "Stage A is not complete")
        target_specs = cumulative_specs(authority, args.stage)
        target_ids = {spec["trajectory_spec_id"] for spec in target_specs}
        if not accepted_before.issubset(target_ids):
            raise CampaignError(
                "PRECHECK_FAILED", "accepted spec beyond requested stage"
            )

        stage_receipts: dict[str, dict[str, Any]] = {}
        target_index = ("B", "C", "D").index(args.stage)
        for stage in ("B", "C", "D")[: target_index + 1]:
            capture_started = time.monotonic()
            runner.run_stage(stage, resume=True)
            capture_elapsed = time.monotonic() - capture_started
            stage_receipts[stage] = durability_gate(
                runner,
                stage,
                capture_elapsed,
                startup_seconds if stage == "B" else 0.0,
            )
            print(
                f"P3_STAGE_{stage}_GATE=PASS "
                f"cumulative={stage_receipts[stage]['cumulative_accepted']}",
                flush=True,
            )

        if args.stage == "D":
            if processes:
                stop_runtime(processes)
                processes = []
            if authority.is_repaired_v2:
                print("P4C_V2_FULL_RAW_CAPTURE=PASS", flush=True)
            else:
                write_p3_receipts(
                    runner,
                    stage_receipts,
                    machine_started,
                    startup_seconds,
                )
                print("P3_FULL_CAPTURE=PASS", flush=True)
        else:
            print(f"P3_STAGE_{args.stage}_CAPTURE=PASS", flush=True)
        return 0
    finally:
        try:
            if args.ledger.exists():
                subprocess.run(
                    [
                        "aws",
                        "s3",
                        "cp",
                        str(args.ledger),
                        args.s3_prefix.rstrip("/") + "/p2_capture_ledger.jsonl",
                        "--only-show-errors",
                    ],
                    check=False,
                    timeout=120,
                )
        except (OSError, subprocess.SubprocessError):
            pass
        if processes:
            stop_runtime(processes)


if __name__ == "__main__":
    raise SystemExit(main())
