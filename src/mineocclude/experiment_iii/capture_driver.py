"""Driving one capture unit against a live apparatus (authority 7.2, 7.10f, 8.2).

This is the seam between the frozen plan and the running Minecraft server. It
issues the server commands for a unit, waits for the frames to land, and hands
the result to the liveness contract. It never decides anything scientific: the
condition, material, placement, ordering and frame counts all arrive from the
authority-derived plan.

Three behaviours here exist because of specific, previously observed failures:

* **A material change is followed by an explicit transition probe.** The arena
  cache key includes the material (``WallCondition.cacheKeyFragment``), but a
  cache key is a claim about intent; the probe is evidence about pixels. Without
  it a stale wall can stand through a whole batch with every receipt still green.
* **Every unit begins with a mandatory pre-capture liveness probe** (authority
  7.10f). P0 captures a static scene, so a frozen renderer produces exactly the
  observation a correct static capture produces. The probe is the only moment at
  which the two are distinguishable, so it is not optional -- and it is issued
  *before* the unit's four ABBA slots, as a controlled toggle of its own, so a
  dead renderer costs one probe rather than a whole unit.
* **Every evidence field comes from the apparatus.** The tick is the mod's
  ``server_tick``, the dimensions are the PNG's own IHDR chunk, and the read
  succeeded because ``capture_complete.json`` says the writer drained with zero
  errors. Nothing here is proven by restating what was requested.
"""

from __future__ import annotations

import hashlib
import time
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from mineocclude.experiment_iii.capture_evidence import (
    MAX_TICK_QUEUE_DEPTH_AT_CAPTURE,
    evidence_binding_matrix,
    join_frames_to_ticks,
    png_dimensions,
    read_capture_complete,
    read_client_authority,
    read_client_tick_ledger,
)
from mineocclude.experiment_iii.capture_liveness import (
    LivenessProbe,
    verify_unit_liveness,
)
from mineocclude.experiment_iii.capture_runtime import CaptureRuntime
from mineocclude.experiment_iii.conditions import AIR
from mineocclude.experiment_iii.errors import ExperimentIIIError
from mineocclude.experiment_iii.placements import placement_coordinates

#: Authority 7.10f (Amendment 4). The witness scene is NO_WALL, so its visual
#: change cannot depend on any candidate material.
WITNESS_WALL_BLOCK_ID = AIR
WITNESS_CONDITION_ID = "L0"

#: The fixed authority-bound visible calibration position: the CENTRE of the nine
#: placements frozen by authority 7.2 (index 4, a frozen sentinel index). It is
#: authority-bound rather than invented, and with no wall in front of it the
#: target is visible there by construction -- that is precisely the L0 anchor.
WITNESS_PLACEMENT_INDEX = 4
WITNESS_LANE_X = float(placement_coordinates()[WITNESS_PLACEMENT_INDEX]["lane_x"])


class _WitnessUnit:
    """The unit view the witness captures under: NO_WALL, calibration position.

    ``_capture_slot`` reads ``lane_x``, ``condition_id``, ``wall_block_id`` and
    ``unit_id`` off the unit it is given. The witness must not inherit the
    scientific unit's material or placement -- that is exactly what made liveness
    conditional on the measurement -- so it is captured under this fixed view.
    """

    __slots__ = ("unit_id", "condition_id", "wall_block_id", "lane_x", "abba_order")

    def __init__(self, unit: Any) -> None:
        self.unit_id = f"{unit.unit_id}::LIVENESS_WITNESS"
        self.condition_id = WITNESS_CONDITION_ID
        self.wall_block_id = WITNESS_WALL_BLOCK_ID
        self.lane_x = WITNESS_LANE_X
        self.abba_order = ("P", "A", "P")


__all__ = [
    "FrameSink",
    "WITNESS_LANE_X",
    "WITNESS_WALL_BLOCK_ID",
    "P0SlotResult",
    "capture_p0_unit",
    "p0_slot_command",
    "prepare_condition",
    "startspec_command",
    "warmup_command",
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
    """``/mineocclude p0`` -- one static P0 slot (mod command of authority 7.11)."""
    return (
        f"mineocclude p0 {episode_id} {lane_x} {ticks} "
        f"{condition_id} \"{wall_block_id}\" {str(bool(target_present)).lower()}"
    )


def warmup_command(*, ticks: int) -> str:
    """``/mineocclude warmup`` -- settle the client before a unit is measured."""
    return f"mineocclude warmup {int(ticks)}"


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
    """``/mineocclude startspec`` -- one dynamic P1/production capture."""
    return (
        f"mineocclude startspec {layout_id} {episode_id} {seed} {q} {ticks} "
        f"{start_pos} {spec_id} {spec_hash} {condition_id} \"{wall_block_id}\""
    )


class FrameSink:
    """Where captured frames land, and how they are read back for evidence.

    The client writes PNGs into its own output tree; the sink locates a unit's
    frames, joins each one to the mod's tick ledger, reads its real dimensions
    from the image header, and hashes it. Hashes are diagnostics under authority
    7.10f, never a verdict on their own -- but the tick and the dimensions are
    evidence, and they are read from the apparatus.
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

    def frame_records(self, episode_id: int) -> list[dict[str, Any]]:
        """One evidence row per frame, every field observed rather than assumed.

        ``tick`` is the mod's ``server_tick``; ``width``/``height`` come from the
        PNG's IHDR chunk; ``read_succeeded`` comes from the episode's drain
        receipt. Frame order does not determine tick identity -- the ledger does,
        and a frame with no ledger row is a cardinality failure.
        """
        episode_dir = self.episode_dir(episode_id)
        frames = self.frames(episode_id)
        completion = read_capture_complete(
            episode_dir, episode_id=episode_id, expected_frames=len(frames)
        )
        ledger = read_client_tick_ledger(episode_dir, episode_id=episode_id)
        read_client_authority(episode_dir)
        joined = join_frames_to_ticks(frames, ledger, episode_dir=episode_dir)

        records: list[dict[str, Any]] = []
        for entry in joined:
            path: Path = entry["frame"]
            row = entry["tick_row"]
            payload = path.read_bytes()
            width, height = png_dimensions(path)
            depth = int(row["tick_queue_depth_at_capture"])
            if depth > MAX_TICK_QUEUE_DEPTH_AT_CAPTURE:
                raise ExperimentIIIError(
                    "TIMING_CARDINALITY_MISMATCH",
                    f"frame {row['frame_path']} was captured with {depth} ticks "
                    f"still queued; the world advanced past the state this frame "
                    f"is joined to",
                )
            records.append(
                {
                    # The mod's tick identity is the PAIR (episodeId, serverTick)
                    # -- EpisodeManager: "(episodeId, serverTick) is complete".
                    # Every capture restarts its own tick counter at 0, so the
                    # episode is half of the identity and must travel with the
                    # frame; dropping it is what made a unit's four captures look
                    # like one impossible tick sequence.
                    "episode_id": int(episode_id),
                    "tick": int(row["server_tick"]),
                    "render_frame_idx": int(row["render_frame_idx"]),
                    "tick_queue_depth_at_capture": depth,
                    "path": path.as_posix(),
                    "frame_path": row["frame_path"],
                    "bytes": len(payload),
                    "frame_sha256": hashlib.sha256(payload).hexdigest(),
                    "width": width,
                    "height": height,
                    # Observed: the writer drained with zero errors, so every
                    # framebuffer read that produced a file completed.
                    "read_succeeded": bool(completion["drained"])
                    and int(completion["writer_errors"]) == 0,
                    "evidence_source": "OBSERVED_PHYSICAL_EVIDENCE",
                }
            )
        return records

    def wait_for_frames(
        self, episode_id: int, expected: int, *, timeout: float
    ) -> list[Path]:
        """Wait for the episode's **drain receipt**, not for a file count.

        A PNG appears at ``open``, not at completion: the mod encodes and writes
        on a background IO thread. Waiting on ``len(glob)`` can therefore hash a
        half-written image. ``capture_complete.json`` is published only after
        ``awaitDrained``, so it is the correct completion signal, and it carries
        ``writer_errors`` besides.
        """
        episode_dir = self.episode_dir(episode_id)
        deadline = time.monotonic() + timeout
        marker = episode_dir / "capture_complete.json"
        while time.monotonic() < deadline:
            if marker.is_file():
                # Raises on drained=false, writer_errors>0 or a short capture.
                read_capture_complete(
                    episode_dir, episode_id=episode_id, expected_frames=expected
                )
                return self.frames(episode_id)
            time.sleep(0.25)
        raise ExperimentIIIError(
            "TIMING_CARDINALITY_MISMATCH",
            f"episode {episode_id} published no completion receipt within "
            f"{timeout}s; {len(self.frames(episode_id))} frames are on disk and "
            f"{expected} were expected",
        )


class P0SlotResult:
    def __init__(
        self,
        slot: Mapping[str, Any],
        episode_id: int,
        frames: Sequence[Mapping[str, Any]],
        sequence: int = 0,
    ):
        self.slot = dict(slot)
        self.episode_id = episode_id
        self.frames = [dict(frame) for frame in frames]
        #: Position in the order this unit's captures were actually taken. The
        #: episode id cannot serve: the P0 runner numbers the witness at
        #: ``slot_0 + 900_000``, so the capture that runs first has the largest id.
        self.sequence = int(sequence)

    @property
    def settled_hash(self) -> str:
        """The last settled frame's hash -- what a transition probe compares."""
        if not self.frames:
            raise ExperimentIIIError(
                "CAPTURE_STALE_FRAME", f"slot {self.slot} captured no frame"
            )
        return str(self.frames[-1]["frame_sha256"])

    @property
    def first_hash(self) -> str:
        if not self.frames:
            raise ExperimentIIIError(
                "CAPTURE_STALE_FRAME", f"slot {self.slot} captured no frame"
            )
        return str(self.frames[0]["frame_sha256"])

    @property
    def first_tick(self) -> int:
        return int(self.frames[0]["tick"])

    @property
    def last_tick(self) -> int:
        return int(self.frames[-1]["tick"])

    def as_dict(self) -> dict[str, Any]:
        return {
            "slot_index": self.slot["slot_index"],
            "state": self.slot["state"],
            "target_present": self.slot["target_present"],
            "episode_id": self.episode_id,
            "frames": len(self.frames),
            "first_server_tick": self.first_tick if self.frames else None,
            "last_server_tick": self.last_tick if self.frames else None,
            # The analysis half reads the pixels back through these paths, so the
            # unit evidence must carry them, not only their hashes.
            "frame_paths": [frame["path"] for frame in self.frames],
            "frame_hashes": [frame["frame_sha256"] for frame in self.frames],
            "server_ticks": [frame["tick"] for frame in self.frames],
        }


def prepare_condition(
    runtime: CaptureRuntime,
    *,
    wall_block_id: str,
    previous_wall_block_id: str | None,
) -> dict[str, Any]:
    """Announce a material transition so the driver can probe it explicitly.

    Amendment 4 changed what "previous" means. The mandatory liveness witness runs
    NO_WALL immediately before every unit, so the arena a unit rebuilds FROM is
    always the witness's, never the preceding unit's. A unit therefore changes the
    material exactly when it declares something other than air, and the probe is
    bracketed by two real captures -- the witness's last settled frame and the
    unit's first -- instead of by a hash carried across units.
    """
    changed = wall_block_id != AIR
    return {
        "wall_block_id": wall_block_id,
        "previous_wall_block_id": AIR,
        "preceding_unit_wall_block_id": previous_wall_block_id,
        "material_changed": changed,
        "forces_arena_rebuild": changed,
        "probe_required": changed,
        "probed_against": "MANDATORY_PRE_CAPTURE_LIVENESS_WITNESS_NO_WALL",
    }


def _capture_slot(
    runtime: CaptureRuntime,
    sink: FrameSink,
    unit: Any,
    slot: Mapping[str, Any],
    episode_id: int,
    *,
    frames_per_slot: int,
    frame_timeout_seconds: float,
    sequence: int = 0,
) -> P0SlotResult:
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
    if runtime.dry_run:
        return P0SlotResult(slot, episode_id, [], sequence=sequence)
    sink.wait_for_frames(episode_id, frames_per_slot, timeout=frame_timeout_seconds)
    records = sink.frame_records(episode_id)
    if len(records) < frames_per_slot:
        raise ExperimentIIIError(
            "TIMING_CARDINALITY_MISMATCH",
            f"slot {slot['slot_index']} of {unit.unit_id} produced "
            f"{len(records)} frames, expected {frames_per_slot}",
        )
    return P0SlotResult(slot, episode_id, records, sequence=sequence)


def capture_p0_unit(
    runtime: CaptureRuntime,
    sink: FrameSink,
    unit: Any,
    *,
    frames_per_slot: int,
    warmup_ticks: int,
    episode_id_for_slot: Callable[[Any, int], int],
    previous_wall_block_id: str | None = None,
    previous_unit_settled_hash: str | None = None,
    settle_seconds: float = 1.0,
    frame_timeout_seconds: float = 180.0,
    probe_episode_id_for_unit: Callable[[Any], int] | None = None,
) -> dict[str, Any]:
    """Capture one (condition, placement, block) unit as its full ABBA sequence.

    Returns the unit's evidence: the realised ABBA order, every slot's frames and
    observed ticks, the transition probes, and the liveness verdict.
    """
    transition = prepare_condition(
        runtime,
        wall_block_id=unit.wall_block_id,
        previous_wall_block_id=previous_wall_block_id,
    )

    # 7.10f: the warmup is issued, not merely recorded. A receipt claiming a
    # warmup that never reached the server is worse than no warmup at all.
    warmup_issued = False
    if warmup_ticks:
        runtime.send(warmup_command(ticks=warmup_ticks))
        warmup_issued = True

    probes: list[LivenessProbe] = []
    pre_capture: dict[str, Any] | None = None
    witness_results: list[P0SlotResult] = []

    # Authority 7.10f, Amendment 4 -- the MANDATORY PRE-CAPTURE LIVENESS WITNESS.
    #
    # The witness is a fixed ENGINEERING_ONLY observation whose visual change is
    # guaranteed INDEPENDENTLY of the candidate wall material and of P0
    # visibility: NO_WALL, the target at a fixed authority-bound visible
    # calibration position, toggled PRESENT -> ABSENT -> PRESENT. One frozen
    # configuration, common to every P0 unit.
    #
    # It replaces the v1.6 probe, which toggled the target inside the unit's OWN
    # wall configuration. That made liveness conditional on the very visibility
    # P0 exists to measure: the nine frozen placements all lie inside the wall
    # extent, so an occluding condition renders PRESENT and ABSENT identically
    # and every one of its units was refused on a physically correct observation.
    #
    # Its frames are never added to ``all_frames``: they are apparatus evidence,
    # not measurement, and no scientific consumer may read them.
    if not runtime.dry_run:
        witness_id = (
            probe_episode_id_for_unit(unit)
            if probe_episode_id_for_unit is not None
            else episode_id_for_slot(unit, 0) + 900_000
        )
        witness_slots = [
            {"slot_index": -3, "state": "P", "target_present": True,
             "frames": frames_per_slot},
            {"slot_index": -2, "state": "A", "target_present": False,
             "frames": frames_per_slot},
            {"slot_index": -1, "state": "P", "target_present": True,
             "frames": frames_per_slot},
        ]
        witness_unit = _WitnessUnit(unit)
        witness_results = [
            _capture_slot(
                runtime,
                sink,
                witness_unit,
                witness_slot,
                witness_id + offset,
                frames_per_slot=frames_per_slot,
                frame_timeout_seconds=frame_timeout_seconds,
                sequence=offset,
            )
            for offset, witness_slot in enumerate(witness_slots)
        ]
        # Both legs must change: with no wall in front of it, the calibration
        # target is visible by construction, so PRESENT -> ABSENT -> PRESENT is a
        # transition the authority guarantees must alter the framebuffer.
        for before, after in zip(witness_results, witness_results[1:]):
            probes.append(
                LivenessProbe(
                    "MANDATORY_PRE_CAPTURE_LIVENESS_WITNESS",
                    before_hash=before.settled_hash,
                    after_hash=after.settled_hash,
                    before_tick=before.last_tick,
                    after_tick=after.last_tick,
                    before_episode=before.episode_id,
                    after_episode=after.episode_id,
                    before_sequence=before.sequence,
                    after_sequence=after.sequence,
                )
            )
        pre_capture = {
            "kind": "MANDATORY_PRE_CAPTURE_LIVENESS_WITNESS",
            "classification": "ENGINEERING_ONLY",
            "scene": "NO_WALL",
            "wall_block_id": WITNESS_WALL_BLOCK_ID,
            "condition_id": WITNESS_CONDITION_ID,
            "calibration_lane_x": WITNESS_LANE_X,
            "transition": ["TARGET_PRESENT", "TARGET_ABSENT", "TARGET_PRESENT"],
            "episode_ids": [result.episode_id for result in witness_results],
            "issued_before_measured_slots": True,
            "visual_change_guaranteed_independently_of_wall_material": True,
            "frozen_configuration_common_to_every_p0_unit": True,
            "excluded_from_scientific_consumers": True,
        }

    results: list[P0SlotResult] = []
    all_frames: list[dict[str, Any]] = []
    for slot in unit.slots(frames_per_slot):
        episode_id = episode_id_for_slot(unit, slot["slot_index"])
        result = _capture_slot(
            runtime,
            sink,
            unit,
            slot,
            episode_id,
            frames_per_slot=frames_per_slot,
            frame_timeout_seconds=frame_timeout_seconds,
            # The measured slots continue the sequence the witness started, so a
            # probe spanning the witness and the first slot orders correctly.
            sequence=len(witness_results) + slot["slot_index"],
        )
        if not runtime.dry_run:
            time.sleep(settle_seconds)
        all_frames.extend(result.frames)
        results.append(result)
        # The wall material change is bracketed by the witness's last settled
        # frame (NO_WALL) and this unit's first measured frame (its material).
        # Both sides are real captures; the arena cache key is a claim about
        # intent, not evidence about pixels.
        if (
            not runtime.dry_run
            and transition["probe_required"]
            and slot["slot_index"] == 0
            and witness_results
        ):
            probes.append(
                LivenessProbe(
                    "WALL_MATERIAL_CHANGE",
                    before_hash=witness_results[-1].settled_hash,
                    after_hash=result.first_hash,
                    before_tick=witness_results[-1].last_tick,
                    after_tick=result.first_tick,
                    before_episode=witness_results[-1].episode_id,
                    after_episode=result.episode_id,
                    before_sequence=witness_results[-1].sequence,
                    after_sequence=result.sequence,
                )
            )

    if not runtime.dry_run:
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
                    before_tick=before.last_tick,
                    after_tick=after.first_tick,
                    before_episode=before.episode_id,
                    after_episode=after.episode_id,
                    before_sequence=before.sequence,
                    after_sequence=after.sequence,
                )
            )

    if runtime.dry_run:
        # A dry run measured nothing. It must not occupy the same evidence shape
        # as a real verdict, or a planning artefact can be persisted into campaign
        # state looking structurally like a measured unit.
        liveness = {
            "schema_version": "mineocclude-experiment-iii-capture-liveness-dryrun-v1",
            "dry_run": True,
            "measured": False,
            "passed": None,
            "verdict": "NOT_MEASURED_DRY_RUN",
            "may_be_persisted_as_complete": False,
        }
    else:
        liveness = verify_unit_liveness(
            frames=all_frames,
            probes=probes,
            process_alive=runtime.alive(),
            expected_frames=frames_per_slot * len(unit.abba_order),
            material_transition=bool(transition["probe_required"]),
        )
        liveness["evidence_binding"] = evidence_binding_matrix()
        liveness["pre_capture_probe"] = pre_capture

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
        "warmup_issued": warmup_issued,
        "settled_hash": results[-1].settled_hash if all_frames else None,
        "dry_run": bool(runtime.dry_run),
    }
