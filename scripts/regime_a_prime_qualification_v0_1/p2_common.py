"""Shared helpers for Regime A prime P2 matched no-wall diagnostic.

P2 classification: EXPLORATORY_MATCHED_DIAGNOSTIC.

P2 creates 25 NEW no-wall counterparts of the existing 25 Regime A wall
specifications. The historical wall runs are NEVER recollected. P2 trajectories
are permanently NONCONFIRMATORY and may not enter a future confirmatory
Regime A prime cohort.

The only experimental manipulation is the scene command:
    wall   (historical) -> "mineocclude mode normal"   -> scene NORMAL
    no-wall (P2)        -> "mineocclude mode nowall"   -> scene NO_WALL
Everything else -- seed, noise schedule, direction, speed, start position,
camera, cadence, frame/action semantics, checkpoint -- is held identical.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

REPO = Path("/home/sagemaker-user/MineOcclude")
INTEG = REPO / "docs/status/integration/regime_a_occlusion_extraction_v0_1"
CONF = INTEG / "first25_analysis"
PM = INTEG / "postmortem_v0_1"
AMEND = INTEG / "v2_amendment_1"
OUT = REPO / "docs/status/integration/regime_a_prime_qualification_v0_1"

# Historical wall capture metadata cached during P1 (hash-bound to the closed
# Regime A durable receipts). Used as the wall-side path ground truth.
WALL_META = Path("/home/sagemaker-user/.mineocclude_cache/p1_qualification_v0_1/meta")

# P2 working + durable roots. Large artifacts never enter Git.
WORK = Path("/mnt/sagemaker-nvme/p2_no_wall_v0_1")
RUNTIME_ROOT = Path("/mnt/sagemaker-nvme/p2_runtime")
S3_PREFIX = (
    "s3://sagemaker-us-east-1-323206973672/mineocclude/"
    "regime_a_prime_qualification_v0_1/p2_no_wall_diagnostic_v0_1"
)

BRANCH = "exploration/regime-a-prime-qualification-v0-1"
P1_HEAD = "4ba4794a0bc22a218358fdc710c6a9b1663887dd"

# Restored capture runtime. Corretto 17.0.20.8.1 is one of the two JVMs the
# frozen provisioning gate approves; the original NVMe runtime was wiped, so the
# gate is satisfied rather than weakened. Path identity is verified empirically
# by the P2.3 non-scientific wall replay.
JAVA_HOME = Path("/usr/lib/jvm/amazon-corretto-17.0.20.8.1-linux-x64")

MANIFEST = AMEND / "trajectory_manifest_v2_1_amendment_1.jsonl"

# P2 episode ids are offset far from the historical 52001..52025 so a P2 episode
# can never be confused with, or overwrite, a historical wall episode.
P2_EPISODE_BASE = 61000

TAUS = list(range(1, 20))
LAYER = 4


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_obj(obj: Any) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def write_json(path: Path, payload: Any) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True, default=_default) + "\n"
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _default(value: Any) -> Any:
    import numpy as np

    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    raise TypeError(repr(value))


def read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def run_git(*args: str) -> str:
    proc = subprocess.run(["git", *args], cwd=REPO, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout.strip()


def source_specs() -> list[dict]:
    """The 25 controlling Regime A specifications (v2.1 amendment 1)."""
    specs = read_jsonl(MANIFEST)
    if len(specs) != 25:
        raise RuntimeError(f"expected 25 source specs, got {len(specs)}")
    return sorted(specs, key=lambda s: s["trajectory_spec_id"])


def p2_run_id(spec_id: str) -> str:
    """New, unambiguous P2 run id. Never reuses a historical wall run id."""
    return f"p2_nowall_{spec_id}"


def p2_episode_id(spec: dict) -> int:
    index = int(str(spec["trajectory_spec_id"]).rsplit("t", 1)[1])
    return P2_EPISODE_BASE + index


def raw_capture_spec_hash(spec: dict) -> str:
    return str(spec.get("raw_capture_spec_hash", spec["spec_hash"]))


def expected_path(spec: dict, schedule: Any) -> list[float]:
    """Analytic sheep path implied by the frozen spec and immutable noise draws.

    Mirrors the validated recurrence in scripts/run_regime_a.py: the target's
    world x is a clamped cumulative sum of signed speed per tick plus the
    immutable noise draw. The wall sits at z=2 and the lane at z=6, so removing
    the wall cannot influence this recurrence.
    """
    signed = float(spec["speed_blocks_per_second"]) * (
        1 if spec["direction"] == "LEFT_TO_RIGHT" else -1
    )
    position = float(spec["start_world_x"])
    out: list[float] = []
    for row in schedule.rows:
        position = min(8.0, max(-8.0, position + signed * 0.05 + float(row.noise_draw)))
        out.append(position)
    return out


def capture_context(spec: dict, episode_id: int, server_root: Path) -> dict[str, Any]:
    """Frozen noise/motion documents for one capture, identical to Regime A."""
    import numpy as np
    from mineocclude.data.noise_schedule import generate_noise_schedule, serialize_schedule

    frames = int(spec["expected_max_frames"])
    schedule = generate_noise_schedule(
        int(spec["noise_seed"]), frames, float(spec["motion_noise_q"])
    )
    noise_values = np.asarray([r.noise_draw for r in schedule.rows], dtype="<f8")
    if hashlib.sha256(noise_values.tobytes()).hexdigest() != spec["noise_schedule_sha256"]:
        raise RuntimeError(f"noise schedule hash mismatch for {spec['trajectory_spec_id']}")
    signed = float(spec["speed_blocks_per_second"]) * (
        1 if spec["direction"] == "LEFT_TO_RIGHT" else -1
    )
    motion = {
        "schedule_format_version": "mineocclude-motion-schedule-v0.1",
        "trajectory_spec_id": spec["trajectory_spec_id"],
        "spec_hash": raw_capture_spec_hash(spec),
        "expected_ticks": frames,
        "segments": [{
            "start_model_frame_idx": 0,
            "stop_model_frame_idx_exclusive": frames,
            "signed_speed_blocks_per_second": signed,
        }],
    }
    return {
        "episode_id": episode_id,
        "frames": frames,
        "schedule": schedule,
        "signed_speed": signed,
        "noise_path": server_root / f"mineocclude_schedules/episode_{episode_id}.jsonl",
        "motion_path": server_root / f"mineocclude_motion_schedules/episode_{episode_id}.json",
        "noise_bytes": serialize_schedule(schedule),
        "motion_bytes": (json.dumps(motion, sort_keys=True) + "\n").encode(),
    }


def load_live():
    """Import and configure the validated live capture runtime."""
    sys.path.insert(0, str(REPO))
    sys.path.insert(0, str(REPO / "src"))
    os.environ["JAVA_HOME"] = str(JAVA_HOME)
    from scripts import run_large_scale_no_wall_campaign as live

    live.JAVA_PATH = JAVA_HOME / "bin/java"
    if not live.JAVA_PATH.is_file():
        raise RuntimeError("approved JDK absent")
    return live


class CaptureSession:
    """One launched Minecraft runtime driving many episodes.

    The checkpoint-free capture runtime is launched once and reused across
    episodes, which is how the historical Regime A campaign ran. Every episode
    re-arms from its own frozen spec, and per-episode identity is asserted from
    the server state stream.
    """

    def __init__(self, scene_mode: str):
        if scene_mode not in ("normal", "nowall"):
            raise ValueError(scene_mode)
        self.scene_mode = scene_mode
        self.expected_scene = "NORMAL" if scene_mode == "normal" else "NO_WALL"
        self.live = load_live()
        self.processes: list[Any] = []
        self.runtime = None

    def __enter__(self) -> CaptureSession:
        RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)
        self.processes, self.launch_seconds = self.live.launch_runtime(RUNTIME_ROOT)
        self.runtime = self.live.LiveRuntime()
        return self

    def __exit__(self, *exc: Any) -> None:
        if self.processes:
            self.live.stop_runtime(self.processes)
        self.processes = []

    def capture(self, spec: dict, episode_id: int, destination: Path) -> dict[str, Any]:
        """Run one episode and copy its raw streams to ``destination``."""
        live = self.live
        server_root, client_root = live.SERVER_ROOT, live.CLIENT_ROOT
        context = capture_context(spec, episode_id, server_root)
        frames = context["frames"]

        server_episode = server_root / f"mineocclude_out/episode_{episode_id}"
        client_episode = client_root / f"mineocclude_client_out/episode_{episode_id}"
        for path in (server_episode, client_episode):
            if path.exists():
                shutil.rmtree(path)

        context["noise_path"].parent.mkdir(parents=True, exist_ok=True)
        context["motion_path"].parent.mkdir(parents=True, exist_ok=True)
        context["noise_path"].write_bytes(context["noise_bytes"])
        context["motion_path"].write_bytes(context["motion_bytes"])

        offset = len(self.runtime.log_text())
        started = time.monotonic()
        self.runtime.send([
            f"mineocclude mode {self.scene_mode}",
            "mineocclude duration 0",
            "mineocclude reveal 0",
            "mineocclude warmup 60",
            "mineocclude impulse -1 0",
            "mineocclude pairshift 0",
            "mineocclude lockcam on",
            (
                f"mineocclude startspec layout_01 {episode_id} {spec['seed']} "
                f"{spec['motion_noise_q']} {frames} {spec['start_world_x']} "
                f"{spec['trajectory_spec_id']} {raw_capture_spec_hash(spec)}"
            ),
        ])
        self.runtime.wait_log(rf"episode {episode_id} armed", 60, offset)
        self.runtime.wait_log(rf"episode {episode_id} recording started", 60, offset)
        self.runtime.wait_log(
            rf"episode {episode_id} ended after {frames} ticks", 120, offset
        )
        self.runtime.wait_file(client_episode / "capture_complete.json", 30)

        raw = destination / "raw"
        if raw.exists():
            shutil.rmtree(raw)
        raw.mkdir(parents=True)
        shutil.copytree(client_episode / "frames", raw / "frames")
        shutil.copy2(server_episode / "server_state.jsonl", raw / "server_state.jsonl")
        shutil.copy2(client_episode / "client_tick.jsonl", raw / "client_tick.jsonl")
        shutil.copy2(client_episode / "raw_actions.jsonl", raw / "actions.jsonl")
        return {
            "episode_id": episode_id,
            "frames": frames,
            "capture_seconds": time.monotonic() - started,
            "schedule": context["schedule"],
            "signed_speed": context["signed_speed"],
        }


def wall_coordinates(spec_id: str) -> dict[int, float]:
    """Historical wall-run world x per model frame, from the P1-bound cache."""
    rows = read_jsonl(WALL_META / spec_id / "coordinates.jsonl")
    return {int(r["model_frame_idx"]): float(r["world_x"]) for r in rows}


def wall_target_frames(spec_id: str) -> tuple[list[int], list[int]]:
    """Frozen wall target frames and taus from the bound activation inventory."""
    inv = json.loads((WALL_META / spec_id / "activation_inventory.json").read_text())
    return list(inv["target_model_frame_indices"]), list(inv["target_tau"])
