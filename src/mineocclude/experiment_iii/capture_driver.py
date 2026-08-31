"""Driving one capture unit against a live apparatus (authority 7.2, 7.10f, 8.2).

This is the seam between the frozen plan and the running Minecraft server. It
issues the server commands for a unit, waits for the frames to land, and hands
the result to the liveness contract. It never decides anything scientific: the
condition, material, placement, ordering and frame counts all arrive from the
authority-derived plan.

Two behaviours here exist because of specific, previously observed failures:

* **A material change is followed by an explicit transition probe.** The arena
  cache key includes the material (``WallCondition.cacheKeyFragment``), but a
  cache key is a claim about intent; the probe is evidence about pixels. Without
  it a stale wall can stand through a whole batch with every receipt still green.
* **Every unit begins with a mandatory pre-capture liveness probe** (authority
  7.10f). P0 captures a static scene, so a frozen renderer produces exactly the
  observation a correct static capture produces. The probe is the only moment at
  which the two are distinguishable, so it is not optional.
"""

from __future__ import annotations

import hashlib
import time
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from mineocclude.experiment_iii.authority import (
    FRAMEBUFFER_HEIGHT,
    FRAMEBUFFER_WIDTH,
)
from mineocclude.experiment_iii.capture_liveness import (
    LivenessProbe,
    verify_unit_liveness,
)
from mineocclude.experiment_iii.capture_runtime import CaptureRuntime
from mineocclude.experiment_iii.errors import ExperimentIIIError

__all__ = [
    "FrameSink",
    "P0SlotResult",
    "capture_p0_unit",
    "p0_slot_command",
    "prepare_condition",
    "startspec_command",
]


def p0_slot_command(
    *,
    episode_id: int,
    lane_x: float,
    ticks: int,
    condition_id: str,
    wall_block_id: str,
    target_present: bool,
) -> str:
    """``/mineocclude p0`` — one static P0 slot (mod command of authority 7.11)."""
    return (
        f"mineocclude p0 {episode_id} {lane_x} {ticks} "
        f"{condition_id} \"{wall_block_id}\" {str(bool(target_present)).lower()}"
    )


def startspec_command(
    *,
    layout_id: str,
    episode_id: int,
    seed: int,
    q: float,
    ticks: int,
    start_pos: float,
    spec_id: str,
    spec_hash: str,
    condition_id: str,
    wall_block_id: str,
) -> str:
    """``/mineocclude startspec`` — one dynamic P1/production capture."""
    return (
        f"mineocclude startspec {layout_id} {episode_id} {seed} {q} {ticks} "
        f"{start_pos} {spec_id} {spec_hash} {condition_id} \"{wall_block_id}\""
    )


class FrameSink:
    """Where captured frames land, and how they are read back for evidence.

    The client writes PNGs into its own output tree; the sink locates a unit's
    frames and hashes them. Hashes are diagnostics under authority 7.10f, never a
    verdict on their own.
    """

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def episode_dir(self, episode_id: int) -> Path:
        return self.root / f"episode_{episode_id}"

    def frames(self, episode_id: int) -> list[Path]:
        directory = self.episode_dir(episode_id)
        for candidate in ("frames_640x360", "frames"):
            sub = directory / candidate
            if sub.is_dir():
                return sorted(sub.glob("*.png"))
        return []

    def frame_records(self, episode_id: int, *, first_tick: int = 0) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for index, path in enumerate(self.frames(episode_id)):
            payload = path.read_bytes()
            records.append(
                {
                    "tick": first_tick + index,
                    "path": path.as_posix(),
                    "bytes": len(payload),
                    "frame_sha256": hashlib.sha256(payload).hexdigest(),
                    "width": FRAMEBUFFER_WIDTH,
                    "height": FRAMEBUFFER_HEIGHT,
                    "read_succeeded": True,
                }
            )
        return records

    def wait_for_frames(
        self, episode_id: int, expected: int, *, timeout: float
    ) -> list[Path]:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            frames = self.frames(episode_id)
            if len(frames) >= expected:
                return frames
            time.sleep(0.25)
        raise ExperimentIIIError(
            "TIMING_CARDINALITY_MISMATCH",
            f"episode {episode_id} produced {len(self.frames(episode_id))} frames "
            f"within {timeout}s, expected {expected}",
        )


class P0SlotResult:
    def __init__(self, slot: Mapping[str, Any], episode_id: int, frames: Sequence[Mapping[str, Any]]):
        self.slot = dict(slot)
        self.episode_id = episode_id
        self.frames = [dict(frame) for frame in frames]

    @property
    def settled_hash(self) -> str:
        """The last settled frame's hash — what a transition probe compares."""
        if not self.frames:
            raise ExperimentIIIError(
                "CAPTURE_STALE_FRAME", f"slot {self.slot} captured no frame"
            )
        return str(self.frames[-1]["frame_sha256"])

    def as_dict(self) -> dict[str, Any]:
        return {
            "slot_index": self.slot["slot_index"],
            "state": self.slot["state"],
            "target_present": self.slot["target_present"],
            "episode_id": self.episode_id,
            "frames": len(self.frames),
            "frame_hashes": [frame["frame_sha256"] for frame in self.frames],
        }


def prepare_condition(
    runtime: CaptureRuntime,
    *,
    wall_block_id: str,
    previous_wall_block_id: str | None,
) -> dict[str, Any]:
    """Announce a material transition so the driver can probe it explicitly."""
    changed = previous_wall_block_id is not None and previous_wall_block_id != wall_block_id
    return {
        "wall_block_id": wall_block_id,
        "previous_wall_block_id": previous_wall_block_id,
        "material_changed": changed,
        "forces_arena_rebuild": changed,
        "probe_required": changed,
    }


def capture_p0_unit(
    runtime: CaptureRuntime,
    sink: FrameSink,
    unit: Any,
    *,
    frames_per_slot: int,
    warmup_ticks: int,
    episode_id_for_slot: Callable[[Any, int], int],
    previous_wall_block_id: str | None = None,
    settle_seconds: float = 1.0,
    frame_timeout_seconds: float = 180.0,
) -> dict[str, Any]:
    """Capture one (condition, placement, block) unit as its full ABBA sequence.

    Returns the unit's evidence: the realised ABBA order, every slot's frames and
    hashes, the transition probes, and the liveness verdict.
    """
    transition = prepare_condition(
        runtime,
        wall_block_id=unit.wall_block_id,
        previous_wall_block_id=previous_wall_block_id,
    )

    results: list[P0SlotResult] = []
    probes: list[LivenessProbe] = []
    all_frames: list[dict[str, Any]] = []
    tick_cursor = 0

    for slot in unit.slots(frames_per_slot):
        episode_id = episode_id_for_slot(unit, slot["slot_index"])
        runtime.send(
            p0_slot_command(
                episode_id=episode_id,
                lane_x=unit.lane_x,
                ticks=frames_per_slot,
                condition_id=unit.condition_id,
                wall_block_id=unit.wall_block_id,
                target_present=bool(slot["target_present"]),
            )
        )
        if not runtime.dry_run:
            sink.wait_for_frames(
                episode_id, frames_per_slot, timeout=frame_timeout_seconds
            )
            time.sleep(settle_seconds)
        records = sink.frame_records(episode_id, first_tick=tick_cursor)
        if not runtime.dry_run and len(records) < frames_per_slot:
            raise ExperimentIIIError(
                "TIMING_CARDINALITY_MISMATCH",
                f"slot {slot['slot_index']} of {unit.unit_id} produced "
                f"{len(records)} frames, expected {frames_per_slot}",
            )
        tick_cursor += len(records)
        all_frames.extend(records)
        results.append(P0SlotResult(slot, episode_id, records))

    if not runtime.dry_run:
        # The mandatory pre-capture probe, plus one probe per realised target
        # transition inside the ABBA order. A static scene is indistinguishable
        # from a frozen renderer anywhere else, so these are the only places the
        # renderer can actually be held to account.
        probes.append(
            LivenessProbe(
                "MANDATORY_PRE_CAPTURE_LIVENESS_PROBE",
                before_hash=results[0].settled_hash,
                after_hash=results[1].settled_hash,
                before_tick=0,
                after_tick=frames_per_slot,
            )
        )
        for index in range(len(results) - 1):
            before, after = results[index], results[index + 1]
            if before.slot["target_present"] == after.slot["target_present"]:
                continue
            kind = (
                "TARGET_PRESENT_TO_ABSENT"
                if before.slot["target_present"]
                else "TARGET_ABSENT_TO_PRESENT"
            )
            probes.append(
                LivenessProbe(
                    kind,
                    before_hash=before.settled_hash,
                    after_hash=after.settled_hash,
                    before_tick=index * frames_per_slot,
                    after_tick=(index + 1) * frames_per_slot,
                )
            )

    liveness = (
        verify_unit_liveness(
            frames=all_frames,
            probes=probes,
            process_alive=runtime.alive(),
            expected_frames=frames_per_slot * len(unit.abba_order),
        )
        if not runtime.dry_run
        else {"dry_run": True, "passed": None}
    )

    return {
        "unit_id": unit.unit_id,
        "condition_key": unit.condition_key,
        "condition_id": unit.condition_id,
        "wall_block_id": unit.wall_block_id,
        "placement_index": unit.placement_index,
        "lane_x": unit.lane_x,
        "block_index": unit.block_index,
        "abba_order_planned": list(unit.abba_order),
        "abba_order_realised": [result.slot["state"] for result in results],
        "material_transition": transition,
        "slots": [result.as_dict() for result in results],
        "frames_captured": len(all_frames),
        "liveness": liveness,
        "warmup_ticks": warmup_ticks,
    }
