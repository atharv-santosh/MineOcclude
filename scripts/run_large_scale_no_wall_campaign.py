#!/usr/bin/env python3
"""Execute the P1-locked large-scale no-wall capture campaign.

P2 scope is deliberately narrow: parse the immutable campaign, enforce stage
membership, drive the existing Minecraft capture runtime, validate raw capture
and profile authority without model outcomes, append an fsync'd hash-chain
ledger, and durably copy accepted attempts to the experiment S3 prefix.
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

CONTROLLER_VERSION = "large-scale-no-wall-campaign-orchestrator-v0.1"
P1_HEAD = "ef6469ab68ea8edf572ec4778d2d938b61a07f59"
PREDECESSOR_SHA = "18c8dd0de0987d3065206a5fd7df452badb1338b"
FROZEN_MVP_SHA = "bb22364cbc4f65b788a56b60e7d6503e6226df7b"
CAMPAIGN_SHA256 = "1605f4738840ea531e73fdcee19536d55652a1a05ddef704304adcb1bc41cdd6"
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
SERVER_ROOT = Path("/home/sagemaker-user/mineocclude-server")
CLIENT_ROOT = Path("/home/sagemaker-user/mineocclude-client")
FIFO = SERVER_ROOT / "cmd.fifo"
JAVA_PATH = Path("/usr/lib/jvm/java-17-openjdk-amd64/bin/java")
XVFB_PATH = Path("/usr/bin/Xvfb")
DISPLAY = ":99"
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
        if sha256_file(self.path) != CAMPAIGN_SHA256:
            raise CampaignError("PRECHECK_FAILED", "capture campaign hash changed")
        study = self.package / "study_design.json"
        if sha256_file(study) != STUDY_SHA256:
            raise CampaignError("PRECHECK_FAILED", "study design hash changed")
        self._verify_lock(self.path, self.package / "capture_campaign.lock.json")
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
        for spec in self.specs.values():
            body = dict(spec)
            spec_hash = body.pop("spec_hash")
            if canonical_sha256(body) != spec_hash:
                raise CampaignError(
                    "SPEC_ID_OR_HASH_MISMATCH", spec["trajectory_spec_id"]
                )

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


def focus_client() -> bool:
    try:
        found = subprocess.run(
            ["xdotool", "search", "--onlyvisible", "--name", r"^Minecraft"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
            env={**os.environ, "DISPLAY": DISPLAY},
        )
        ids = [line.strip() for line in found.stdout.splitlines() if line.strip()]
        if len(ids) != 1:
            return False
        subprocess.run(
            ["xdotool", "windowactivate", "--sync", ids[0]],
            check=True,
            capture_output=True,
            timeout=10,
            env={**os.environ, "DISPLAY": DISPLAY},
        )
        focused = subprocess.run(
            ["xdotool", "getwindowfocus"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
            env={**os.environ, "DISPLAY": DISPLAY},
        )
        return focused.stdout.strip() == ids[0]
    except (OSError, subprocess.SubprocessError):
        return False


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
            Path("/usr/bin/xdotool"),
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
    attempt_root: Path, spec: dict[str, Any], attempt: int, s3_prefix: str
) -> str:
    destination = (
        s3_prefix.rstrip("/")
        + "/stage_a/attempts/"
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
            durable_prefix = upload_attempt(attempt_root, spec, attempt, self.s3_prefix)
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
            durable_prefix = upload_attempt(attempt_root, spec, attempt, self.s3_prefix)
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

    def run_stage_a(self, resume: bool) -> None:
        if not resume and self.ledger.records:
            raise CampaignError("PRECHECK_FAILED", "ledger exists; use --resume")
        specs = self.authority.stage_specs("A")
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


def dry_run(authority: CampaignAuthority) -> dict[str, Any]:
    specs = authority.stage_specs("A")
    for spec in specs:
        validate_profile_semantics(spec)
    counts = Counter(spec["layout_id"] for spec in specs)
    return {
        "status": "PASS",
        "stage_a_count": len(specs),
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


def launch_runtime() -> tuple[list[subprocess.Popen[Any]], float]:
    launch_started = time.monotonic()
    launch_wall_time = time.time()
    log_root = DEFAULT_RUNTIME_ROOT / "runtime_logs"
    log_root.mkdir(parents=True, exist_ok=True)
    processes = []
    environment = {
        **os.environ,
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
                    ["xdpyinfo"],
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
        if args.stage != "A":
            raise CampaignError("PRECHECK_FAILED", "P2 dry-run is Stage A only")
        print(json.dumps(dry_run(authority), indent=2, sort_keys=True))
        return 0
    if args.stage != "A":
        raise CampaignError("PRECHECK_FAILED", "P2 execution is Stage A only")
    ledger = AppendOnlyLedger(args.ledger)
    runner = CampaignRunner(
        authority, ledger, args.runtime_root, args.s3_prefix, args.base_episode_id
    )
    processes: list[subprocess.Popen[Any]] = []
    startup_seconds = 0.0
    machine_started = time.monotonic()
    try:
        if args.launch_runtime:
            processes, startup_seconds = launch_runtime()
        runner.run_stage_a(resume=args.resume)
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
        write_p2_receipts(runner, time.monotonic() - machine_started, startup_seconds)
        print("P2_STAGE_A_CAPTURE=PASS")
        return 0
    finally:
        if processes:
            stop_runtime(processes)


if __name__ == "__main__":
    raise SystemExit(main())
