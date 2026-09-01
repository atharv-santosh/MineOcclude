"""A5 / I22 — driving one dynamic P1 capture unit and assembling its evidence.

This is the execution half of the pilot. ``run_p1_pilot.py`` owned a plan and a
host qualifier but no way to actually capture: ``--execute`` wrote the plan and
printed ``P1_EXECUTED=false``. The frozen contract for what a capture unit *is*
was complete long before this module existed — authority 8.2 fixes the file
inventory and the binding fields, 3.3 fixes the seven receipts, 4.4 fixes the
visibility row schema, 2.5 and 5 fix the target rows and their labels — so
nothing here decides anything scientific. It issues the frozen episode, waits for
the apparatus, and writes down what the apparatus reported.

The distinction that matters throughout: a receipt states what was **observed**.
Where the mod can see something the validator needs, the value is read out of the
mod's own output (``server_state.jsonl``, ``physical_receipt.json``,
``client_authority.json``, the PNG headers). Where Python derives something, it
derives it from the frozen spec and says so. Nothing is proven by restating what
was requested — that failure mode already cost this program one audit.

Unit of work is one ``(pilot identity x condition)`` capture, matching the
Recovery Runbook's A5/A7 state machine::

    PLANNED -> RUNNING -> CAPTURED -> VALIDATED -> DURABLE
            -> COMPLETE_VALIDATED_DURABLE
"""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from mineocclude.experiment_iii.authority import (
    CAPTURE_HZ,
    DT_SECONDS,
    FRAMES_PER_CAPTURE,
    LANE_MAX,
    LANE_MIN,
    MOTION_NOISE_Q,
    SPEED_BLOCKS_PER_SECOND,
    TARGET_ROWS_PER_CAPTURE,
)
from mineocclude.experiment_iii.capture_driver import (
    FrameSink,
    capture_liveness_witness,
    prepare_condition,
    startspec_command,
    warmup_command,
)
from mineocclude.experiment_iii.capture_liveness import assert_transition_observed
from mineocclude.experiment_iii.capture_evidence import read_client_authority
from mineocclude.experiment_iii.conditions import (
    AIR,
    ConditionSpec,
    as_built_wall_cells,
    build_wall_receipt,
    validate_wall_receipt,
)
from mineocclude.experiment_iii.cohort import (
    direction_sign,
    generate_path,
    noise_sha256,
    path_sha256,
)
from mineocclude.experiment_iii.errors import ExperimentIIIError
from mineocclude.experiment_iii.schema import VisibilityRow, read_jsonl
from mineocclude.experiment_iii.target_manifest import build_target_window

__all__ = [
    "PILOT_EPISODE_IDS",
    "CaptureUnitSpec",
    "capture_unit_directory",
    "capture_a5_unit",
    "write_motion_schedule",
    "assemble_unit_inventory",
    "validate_capture_unit",
    "REQUIRED_UNIT_FILES",
]

#: Authority 8.2: ``86901 / 86902 (pilots)``. Production ranks map to 86001+rank
#: and are deliberately not reachable from this module.
PILOT_EPISODE_IDS = {"e3_p90": 86901, "e3_p91": 86902}

#: Authority 8.2's required per-unit inventory. ``durable_receipt.json`` is
#: required only before ``COMPLETE_VALIDATED_DURABLE`` and is checked separately.
REQUIRED_UNIT_FILES = (
    "raw/server_state.jsonl",
    "raw/client_tick.jsonl",
    "raw/actions.jsonl",
    "raw/frame_map.jsonl",
    "raw/visibility.jsonl",
    "coordinates.jsonl",
    "wall_receipt.json",
    "camera_receipt.json",
    "target_receipt.json",
    "condition_receipt.json",
    "capture_completion.json",
)

#: Authority 3.1. The camera the geometry is computed against.
CAMERA_FEET = (0.5, 4.0, -5.5)
CAMERA_EYE_Y = 5.6200000048
CAMERA_YAW = 0.0
CAMERA_PITCH = 0.0
CAMERA_ROLL = 0.0
CAMERA_FOV_DEGREES = 70.0
CAMERA_TOLERANCE = 1e-6

#: Authority 3.3: replayed positions must equal the logged ``sheep_x`` to this.
PATH_REPLAY_TOLERANCE = 1e-9

FRAMEBUFFER_WIDTH = 640
FRAMEBUFFER_HEIGHT = 360

#: Witness episodes must not collide with the pilot's own 86901/86902, nor with
#: P0's. The offset keeps them in their own band and makes them obvious in a
#: directory listing.
WITNESS_EPISODE_OFFSET = 900_000

#: Settled frames per witness leg. The witness is a static three-slot toggle, not
#: a trajectory, so it needs only enough frames to settle and hash.
WITNESS_FRAMES_PER_SLOT = 8


class _A5WitnessView:
    """The unit view the shared witness captures under.

    ``capture_liveness_witness`` reads ``unit_id`` off whatever it is given and
    substitutes the frozen NO_WALL/centre configuration for everything else, so
    a P1 unit only has to name itself.
    """

    __slots__ = ("unit_id",)

    def __init__(self, spec: "CaptureUnitSpec") -> None:
        self.unit_id = spec.capture_unit_id


# --------------------------------------------------------------------------
# The frozen spec of one unit
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class CaptureUnitSpec:
    """Everything about one capture unit that is frozen before it runs.

    Assembled from the P1 plan (identity x condition, material) and the identity
    manifest (seed, direction, start position, path and noise hashes). Nothing
    here is chosen at capture time; ``spec_sha256`` is what a resume compares.
    """

    capture_unit_id: str
    identity: str
    condition: ConditionSpec
    episode_id: int
    seed: int
    direction: str
    start_world_x: float
    motion_noise_q: float
    speed_blocks_per_second: float
    dt_seconds: float
    frames: int
    path_sha256: str
    noise_schedule_sha256: str
    target_model_frame_indices: tuple[int, ...]
    identity_spec_hash: str
    layout_id: str = "layout_01"

    @property
    def episode_dir_name(self) -> str:
        """Authority 8.2: ``episode_{episode_id}_{condition_id}``."""
        return f"episode_{self.episode_id}_{self.condition.condition_id.value}"

    def as_dict(self) -> dict[str, Any]:
        return {
            "capture_unit_id": self.capture_unit_id,
            "identity": self.identity,
            "condition_id": self.condition.condition_id.value,
            "scene": self.condition.scene,
            "wall_block_id": self.condition.wall_block_id,
            "wall_present": self.condition.wall_present,
            "episode_id": self.episode_id,
            "seed": self.seed,
            "direction": self.direction,
            "start_world_x": self.start_world_x,
            "motion_noise_q": self.motion_noise_q,
            "speed_blocks_per_second": self.speed_blocks_per_second,
            "dt_seconds": self.dt_seconds,
            "frames": self.frames,
            "path_sha256": self.path_sha256,
            "noise_schedule_sha256": self.noise_schedule_sha256,
            "target_model_frame_indices": list(self.target_model_frame_indices),
            "identity_spec_hash": self.identity_spec_hash,
            "layout_id": self.layout_id,
        }

    @property
    def spec_sha256(self) -> str:
        """The same-spec resume key (Recovery Runbook: spec hash)."""
        payload = json.dumps(self.as_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def replay(self) -> tuple[np.ndarray, np.ndarray]:
        """Regenerate the frozen path and noise for this unit."""
        return generate_path(
            self.seed,
            self.motion_noise_q,
            direction=self.direction,
            start_world_x=self.start_world_x,
            speed=self.speed_blocks_per_second,
            dt=self.dt_seconds,
            frames=self.frames,
        )


def build_unit_spec(
    plan_unit: Mapping[str, Any],
    identity_row: Mapping[str, Any],
    condition: ConditionSpec,
) -> CaptureUnitSpec:
    """Bind one plan unit to its identity spec, refusing any disagreement."""
    identity = str(plan_unit["identity"])
    if str(identity_row["identity"]) != identity:
        raise ExperimentIIIError(
            "PROVENANCE_BINDING_MISSING",
            f"identity manifest row is {identity_row['identity']!r}, plan unit is "
            f"{identity!r}",
        )
    if identity not in PILOT_EPISODE_IDS:
        raise ExperimentIIIError(
            "P1_INCOMPLETE",
            f"{identity!r} is not a pilot identity; A5 spends e3_p90/e3_p91 only",
        )
    episode_id = int(identity_row["episode_id"])
    if episode_id != PILOT_EPISODE_IDS[identity]:
        raise ExperimentIIIError(
            "PROVENANCE_BINDING_MISMATCH",
            f"{identity} carries episode {episode_id}; authority 8.2 freezes "
            f"{PILOT_EPISODE_IDS[identity]}",
        )
    if str(plan_unit["wall_block_id"]) != condition.wall_block_id:
        raise ExperimentIIIError(
            "WALL_MATERIAL_MISMATCH",
            f"{plan_unit['capture_unit_id']} plans {plan_unit['wall_block_id']!r} "
            f"but the P0-bound condition map resolves {condition.wall_block_id!r}",
        )
    return CaptureUnitSpec(
        capture_unit_id=str(plan_unit["capture_unit_id"]),
        identity=identity,
        condition=condition,
        episode_id=episode_id,
        seed=int(identity_row["seed"]),
        direction=str(identity_row["direction"]),
        start_world_x=float(identity_row["start_world_x"]),
        motion_noise_q=float(identity_row["motion_noise_q"]),
        speed_blocks_per_second=float(identity_row["speed_blocks_per_second"]),
        dt_seconds=float(identity_row["dt_seconds"]),
        frames=int(identity_row["frames"]),
        path_sha256=str(identity_row["path_sha256"]),
        noise_schedule_sha256=str(identity_row["noise_schedule_sha256"]),
        target_model_frame_indices=tuple(
            int(index) for index in identity_row["target_model_frame_indices"]
        ),
        identity_spec_hash=str(identity_row["spec_hash"]),
    )


def capture_unit_directory(root: Path, spec: CaptureUnitSpec) -> Path:
    return Path(root) / spec.capture_unit_id


# --------------------------------------------------------------------------
# Driving the apparatus
# --------------------------------------------------------------------------



#: The mod's frozen motion-schedule format (MotionSchedule.FORMAT_VERSION).
MOTION_SCHEDULE_FORMAT_VERSION = "mineocclude-motion-schedule-v0.1"

#: Where the server looks for it: <server run dir>/mineocclude_motion_schedules/
#: episode_<id>.json, resolved by MineOccludeServer.startSpecCmd. The path is not
#: configurable in the mod.
MOTION_SCHEDULE_DIRECTORY = "mineocclude_motion_schedules"


def write_motion_schedule(server_root: Path, spec: CaptureUnitSpec) -> dict[str, Any]:
    """Serialize the unit's frozen commanded-speed schedule for the server.

    ``/mineocclude startspec`` does not synthesize motion. It loads this file and
    refuses the episode if it is absent, names a different spec, or fails to
    cover every tick -- which is the correct division of labour: the server will
    not invent a scientific schedule, and Python does not get to change one at
    capture time. The mod's own words: "The Python campaign controller serializes
    the already-frozen P1 segments; the server validates complete, gap-free tick
    coverage and never synthesizes or repairs a scientific schedule."

    Every value here is already frozen before this runs. Authority 3.1 fixes the
    speed magnitude at 2.0 blocks/s; the identity manifest fixes the direction,
    and therefore the sign; the frame count is 180. Experiment III's trajectory is
    a constant commanded velocity for the whole capture, so that is exactly one
    segment covering ``[0, frames)``. The per-tick process noise is NOT here: the
    server draws it from the seed and q, and the replayed path is checked against
    the server's own logged positions to 1e-9 afterwards.
    """
    signed_speed = direction_sign(spec.direction) * spec.speed_blocks_per_second
    body = {
        "schedule_format_version": MOTION_SCHEDULE_FORMAT_VERSION,
        "trajectory_spec_id": spec.capture_unit_id,
        "spec_hash": spec.identity_spec_hash,
        "expected_ticks": spec.frames,
        "segments": [
            {
                "start_model_frame_idx": 0,
                "stop_model_frame_idx_exclusive": spec.frames,
                "signed_speed_blocks_per_second": signed_speed,
            }
        ],
    }
    directory = Path(server_root) / MOTION_SCHEDULE_DIRECTORY
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"episode_{spec.episode_id}.json"
    payload = json.dumps(body, indent=2, sort_keys=True, allow_nan=False) + "\n"
    temporary = target.with_name(target.name + ".tmp")
    temporary.write_text(payload, encoding="utf-8", newline="\n")
    temporary.replace(target)
    return {"path": target, "signed_speed_blocks_per_second": signed_speed, "body": body}


def capture_a5_unit(
    runtime: Any,
    sink: FrameSink,
    spec: CaptureUnitSpec,
    *,
    warmup_ticks: int,
    frame_timeout_seconds: float = 600.0,
    previous_wall_block_id: str | None = None,
    server_episode_root: Path | None = None,
    server_run_root: Path | None = None,
    witness_frames: int = WITNESS_FRAMES_PER_SLOT,
) -> dict[str, Any]:
    """Issue one dynamic capture and return what the apparatus reported.

    The episode is started through ``/mineocclude startspec``, which is the mod's
    own trajectory entry point: the seed, q, tick count and start position travel
    to the server, and the server -- not Python -- steps the dynamics. Python
    never tells the sheep where to be; it replays the path afterwards and checks
    that the server agreed to 1e-9.
    """
    transition = prepare_condition(
        runtime,
        wall_block_id=spec.condition.wall_block_id,
        previous_wall_block_id=previous_wall_block_id,
    )

    warmup_issued = False
    if warmup_ticks:
        runtime.send(warmup_command(ticks=warmup_ticks))
        warmup_issued = True

    # Authority 8.2 gives all five of an identity's conditions the SAME episode
    # id -- a unit is addressable by (episode_id, condition_id) -- but the mod
    # writes into ``episode_<id>`` with no condition suffix, so L1 lands on top
    # of L0's output. Harvesting happens immediately after each capture, so the
    # collision is transient; clearing the directory first is what makes it
    # harmless, because it removes any chance of joining this unit's frames to a
    # previous condition's leftover ledger or physical receipt.
    # Amendment 4: the MANDATORY pre-capture liveness witness, before the unit's
    # own episode. It runs NO_WALL at the fixed calibration placement, so its
    # framebuffer change is guaranteed independently of this unit's material --
    # which is the whole point, and is why an opaque L4 unit can no longer be
    # refused for a physically correct identical present/absent pair. Its
    # episodes are apparatus evidence and are never banked into the unit.
    witness: dict[str, Any] | None = None
    if not getattr(runtime, "dry_run", False) and witness_frames:
        witness = capture_liveness_witness(
            runtime,
            sink,
            _A5WitnessView(spec),
            witness_episode_id=spec.episode_id + WITNESS_EPISODE_OFFSET,
            frames_per_slot=witness_frames,
            frame_timeout_seconds=frame_timeout_seconds,
        )
        for probe in witness["probes"]:
            assert_transition_observed(probe)

    for stale in (
        sink.episode_dir(spec.episode_id),
        server_episode_root / f"episode_{spec.episode_id}"
        if server_episode_root is not None
        else None,
    ):
        if stale is not None and stale.exists():
            shutil.rmtree(stale)

    # The schedule must exist before the command is issued: startspec loads it
    # synchronously and refuses the episode if it is missing.
    schedule = (
        write_motion_schedule(server_run_root, spec)
        if server_run_root is not None
        else None
    )

    runtime.send(
        startspec_command(
            layout_id=spec.layout_id,
            episode_id=spec.episode_id,
            seed=spec.seed,
            q=spec.motion_noise_q,
            ticks=spec.frames,
            start_pos=spec.start_world_x,
            spec_id=spec.capture_unit_id,
            spec_hash=spec.identity_spec_hash,
            condition_id=spec.condition.condition_id.value,
            wall_block_id=spec.condition.wall_block_id,
        )
    )

    if getattr(runtime, "dry_run", False):
        return {
            "capture_unit_id": spec.capture_unit_id,
            "episode_id": spec.episode_id,
            "transition": transition,
            "warmup_issued": warmup_issued,
            "dry_run": True,
            "frame_records": [],
            "liveness_witness": None,
        }

    sink.wait_for_frames(spec.episode_id, spec.frames, timeout=frame_timeout_seconds)
    records = sink.frame_records(spec.episode_id)
    if len(records) != spec.frames:
        raise ExperimentIIIError(
            "TIMING_CARDINALITY_MISMATCH",
            f"{spec.capture_unit_id} produced {len(records)} frames, authority 3.1 "
            f"freezes {spec.frames}",
        )
    return {
        "capture_unit_id": spec.capture_unit_id,
        "episode_id": spec.episode_id,
        "transition": transition,
        "warmup_issued": warmup_issued,
        "dry_run": False,
        "frame_records": records,
        "motion_schedule": (
            {
                "path": schedule["path"].as_posix(),
                "signed_speed_blocks_per_second": schedule[
                    "signed_speed_blocks_per_second"
                ],
            }
            if schedule
            else None
        ),
        "liveness_witness": witness["witness"] if witness else None,
        "liveness_probes": (
            [probe.as_dict() for probe in witness["probes"]] if witness else []
        ),
    }


# --------------------------------------------------------------------------
# Assembling authority 8.2's inventory from apparatus output
# --------------------------------------------------------------------------


def _require(path: Path, blocker: str = "CAPTURE_INCOMPLETE") -> Path:
    if not path.is_file():
        raise ExperimentIIIError(blocker, f"the apparatus wrote no {path.name}")
    return path


def assemble_unit_inventory(
    client_episode_dir: Path,
    server_episode_dir: Path,
    unit_dir: Path,
    spec: CaptureUnitSpec,
    frame_records: Sequence[Mapping[str, Any]],
    *,
    rve_condition_score: float | None,
    liveness_witness: Mapping[str, Any] | None = None,
    liveness_probes: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Materialise authority 8.2's file inventory for one unit.

    The apparatus writes into **two** trees, and this is not incidental: the
    dedicated server owns ``mineocclude_out`` under its run directory and the
    client owns ``mineocclude_client_out`` under its own. So the authoritative
    state stream and the physical receipt come from the server's episode
    directory, while the frames, the tick ledger, the action stream and the drain
    receipt come from the client's. Reading both from one root silently produces
    a unit missing half its evidence.

    Four streams are copied verbatim. Three -- ``frame_map``, ``visibility`` and
    ``coordinates`` -- are *derived*, each from a frozen rule rather than a
    judgement call:

    * ``frame_map`` is the mod's own join key, projected out of the tick ledger.
    * ``coordinates`` is the server's authoritative ``sheep_x/y/z`` per tick.
    * ``visibility`` is authority 4.4's row schema. Its only selector-bearing
      field, ``counterfactual_extent_class``, comes from the counterfactual wall
      geometry and the replayed path -- never from the material actually built,
      never from the rendered image.
    """
    client_episode_dir = Path(client_episode_dir)
    server_episode_dir = Path(server_episode_dir)
    unit_dir = Path(unit_dir)
    raw = unit_dir / "raw"
    (raw / "frames").mkdir(parents=True, exist_ok=True)

    server_state = read_jsonl(_require(server_episode_dir / "server_state.jsonl"))
    client_tick = read_jsonl(_require(client_episode_dir / "client_tick.jsonl"))
    actions = read_jsonl(_require(client_episode_dir / "raw_actions.jsonl"))
    completion = json.loads(
        _require(client_episode_dir / "capture_complete.json").read_text(
            encoding="utf-8"
        )
    )
    physical = json.loads(
        _require(
            server_episode_dir / "physical_receipt.json", "WALL_RECEIPT_MISMATCH"
        ).read_text(encoding="utf-8")
    )
    client_authority = read_client_authority(client_episode_dir)

    for name, rows in (
        ("server_state", server_state),
        ("client_tick", client_tick),
        ("actions", actions),
    ):
        if len(rows) != spec.frames:
            raise ExperimentIIIError(
                "TIMING_CARDINALITY_MISMATCH",
                f"{spec.capture_unit_id}: {name} has {len(rows)} rows, "
                f"authority 3.3 requires {spec.frames}",
            )

    # ---- raw streams, copied verbatim from the apparatus -------------------
    shutil.copyfile(
        server_episode_dir / "server_state.jsonl", raw / "server_state.jsonl"
    )
    shutil.copyfile(client_episode_dir / "client_tick.jsonl", raw / "client_tick.jsonl")
    # Authority 8.2 names this stream ``actions.jsonl``; the mod writes it as
    # ``raw_actions.jsonl``. Same bytes, authority's name.
    shutil.copyfile(client_episode_dir / "raw_actions.jsonl", raw / "actions.jsonl")
    # The server's physical receipt is banked as-is: it is the apparatus's own
    # statement about the wall, camera and target, and the derived receipts below
    # must remain checkable against it.
    shutil.copyfile(
        server_episode_dir / "physical_receipt.json", unit_dir / "physical_receipt.json"
    )

    for record in frame_records:
        source = Path(record["path"])
        shutil.copyfile(source, raw / "frames" / f"{int(record['render_frame_idx']):06d}.png")

    # ---- derived: frame_map ------------------------------------------------
    _write_jsonl(
        raw / "frame_map.jsonl",
        [
            {
                "episode_id": int(row["episode_id"]),
                "server_tick": int(row["server_tick"]),
                "render_frame_idx": int(row["render_frame_idx"]),
                "frame_path": f"raw/frames/{int(row['render_frame_idx']):06d}.png",
                "frame_sha256": record["frame_sha256"],
                "width": record["width"],
                "height": record["height"],
            }
            for row, record in zip(client_tick, frame_records)
        ],
    )

    # ---- derived: coordinates ---------------------------------------------
    _write_jsonl(
        raw.parent / "coordinates.jsonl",
        [
            {
                "server_tick": int(row["server_tick"]),
                "sheep_x": row["sheep_x"],
                "sheep_y": row["sheep_y"],
                "sheep_z": row["sheep_z"],
                "axis_pos": row["axis_pos"],
                "axis_velocity": row["axis_velocity"],
                "noise_draw": row["noise_draw"],
            }
            for row in server_state
        ],
    )

    # ---- derived: visibility (authority 4.4) -------------------------------
    positions, _noise = spec.replay()
    window = build_target_window(
        spec.identity, spec.direction, [float(value) for value in positions]
    )
    target_rows = set(window.target_model_frame_indices)
    _write_jsonl(
        raw / "visibility.jsonl",
        [
            VisibilityRow(
                model_frame_idx=index,
                condition_id=spec.condition.condition_id.value,
                wall_present=spec.condition.wall_present,
                wall_block_id=spec.condition.wall_block_id,
                counterfactual_extent_class=extent,
                server_geometric_status=(
                    "visible" if bool(row["geometric_visible"]) else "occluded"
                ),
                # The magenta detector is an image diagnostic and authority 4.4
                # forbids it from selecting anything. It is not run here: the
                # pilot's target rows are already fixed by the counterfactual
                # geometry, and a detector reading pilot frames could not change
                # one of them. Recorded as not run rather than fabricated.
                magenta_status="not_detected",
                magenta_area_pixels=0,
                rve_condition_score=rve_condition_score,
                target_eligible=index in target_rows,
            ).to_dict()
            for index, (row, extent) in enumerate(
                zip(server_state, _extent_classes(positions))
            )
        ],
    )

    receipts = _build_receipts(
        spec,
        server_state=server_state,
        physical=physical,
        completion=completion,
        client_authority=client_authority,
        frame_records=frame_records,
        window=window,
        positions=positions,
        liveness_witness=liveness_witness,
        liveness_probes=liveness_probes,
    )
    for name, body in receipts.items():
        _write_json(unit_dir / name, body)

    return {"receipts": receipts, "target_window": window}


def _extent_classes(positions: Sequence[float]) -> list[str]:
    from mineocclude.experiment_iii.target_manifest import eligibility_mask

    _mask, classes = eligibility_mask([float(value) for value in positions])
    return [value.value for value in classes]


def _build_receipts(
    spec: CaptureUnitSpec,
    *,
    server_state: Sequence[Mapping[str, Any]],
    physical: Mapping[str, Any],
    completion: Mapping[str, Any],
    client_authority: Mapping[str, Any],
    frame_records: Sequence[Mapping[str, Any]],
    window: Any,
    positions: np.ndarray,
    liveness_witness: Mapping[str, Any] | None = None,
    liveness_probes: Sequence[Mapping[str, Any]] = (),
) -> dict[str, dict[str, Any]]:
    """The authority 3.3 receipts, every value read from apparatus output."""

    # ---- wall (3.3) --------------------------------------------------------
    observed_cells = {
        (int(cell["cell_xyz"][0]), int(cell["cell_xyz"][1]), int(cell["cell_xyz"][2])):
        str(cell["observed_block_id"])
        for cell in physical["wall"]["observed_cells"]
    }
    wall_receipt = build_wall_receipt(spec.condition, observed_cells)
    wall_receipt["observed_by"] = "mod:physical_receipt.json"
    wall_receipt["arena_cache_key"] = physical.get("arena_cache_key")
    wall_receipt["mod_scanned_cell_count"] = int(physical["wall"]["scanned_cell_count"])
    wall_receipt["mod_mismatch_count"] = int(physical["wall"]["mismatch_count"])

    # ---- camera (3.3) ------------------------------------------------------
    observed = physical["camera"].get("observed")
    if observed is None:
        raise ExperimentIIIError(
            "CAMERA_POSE_DRIFT", "the physical receipt observed no camera player"
        )
    fov = float(client_authority["fov_degrees"])
    deviations = {
        "feet_x": abs(float(observed["feet_x"]) - CAMERA_FEET[0]),
        "feet_y": abs(float(observed["feet_y"]) - CAMERA_FEET[1]),
        "feet_z": abs(float(observed["feet_z"]) - CAMERA_FEET[2]),
        "eye_y": abs(float(observed["eye_y"]) - CAMERA_EYE_Y),
        "yaw": abs(float(observed["yaw_degrees"]) - CAMERA_YAW),
        "pitch": abs(float(observed["pitch_degrees"]) - CAMERA_PITCH),
        "fov": abs(fov - CAMERA_FOV_DEGREES),
    }
    camera_receipt = {
        "schema_version": "mineocclude-experiment-iii-camera-receipt-v1",
        "authority_section": "3.1, 3.3",
        "expected": {
            "feet": list(CAMERA_FEET),
            "eye_y": CAMERA_EYE_Y,
            "yaw": CAMERA_YAW,
            "pitch": CAMERA_PITCH,
            "roll": CAMERA_ROLL,
            "fov_degrees": CAMERA_FOV_DEGREES,
        },
        "observed": {
            "feet": [
                float(observed["feet_x"]),
                float(observed["feet_y"]),
                float(observed["feet_z"]),
            ],
            "eye_y": float(observed["eye_y"]),
            "yaw": float(observed["yaw_degrees"]),
            "pitch": float(observed["pitch_degrees"]),
            "fov_degrees": fov,
        },
        "deviations": deviations,
        "tolerance": CAMERA_TOLERANCE,
        "camera_lock_active": bool(physical["camera"]["lock_camera"]),
        "max_deviation": max(deviations.values()),
        "observed_by": "mod:physical_receipt.json + client_authority.json",
    }

    # ---- target (3.3) ------------------------------------------------------
    uuids = {
        str(row["target_entity_uuid"])
        for row in server_state
        if row.get("target_entity_uuid") is not None
    }
    respawns = max(int(row["target_respawn_count"]) for row in server_state)
    target = physical["target"]
    target_receipt = {
        "schema_version": "mineocclude-experiment-iii-target-receipt-v1",
        "authority_section": "3.3",
        "target_required": bool(target["target_required"]),
        "distinct_target_uuids": sorted(uuids),
        "target_entity_uuid": target.get("target_entity_uuid"),
        "target_respawn_count": respawns,
        "tagged_target_count": int(target["tagged_target_count"]),
        "entity_type": target["entity_type"],
        "color": target["color"],
        "flags": {
            "adult": bool(target["adult"]),
            "ai_disabled": bool(target["ai_disabled"]),
            "silent": bool(target["silent"]),
            "persistent": bool(target["persistent"]),
            "invulnerable": bool(target["invulnerable"]),
        },
        "uuid_matches": bool(target["uuid_matches"]),
        "problems": list(target["problems"]),
        "valid": bool(target["valid"]),
        "observed_by": "mod:physical_receipt.json + raw/server_state.jsonl",
    }

    # ---- condition / scene (3.3, 4.1) --------------------------------------
    observed_scenes = {str(row["scene"]) for row in server_state}
    condition_receipt = {
        "schema_version": "mineocclude-experiment-iii-condition-receipt-v1",
        "authority_section": "4.1, 3.3",
        "condition_id": spec.condition.condition_id.value,
        "expected_scene": spec.condition.scene,
        "observed_scenes": sorted(observed_scenes),
        "wall_block_id": spec.condition.wall_block_id,
        "wall_present": spec.condition.wall_present,
        "declared_block_id": physical["declared_block_id"],
        "observed_by": "raw/server_state.jsonl + mod:physical_receipt.json",
    }

    # ---- path (3.3) --------------------------------------------------------
    logged = np.asarray([float(row["sheep_x"]) for row in server_state], dtype="<f8")
    replay_positions = np.asarray(positions, dtype="<f8")
    max_abs = float(np.max(np.abs(replay_positions - logged))) if len(logged) else float("inf")
    clamped = [
        index
        for index, value in enumerate(replay_positions)
        if value <= LANE_MIN or value >= LANE_MAX
    ]
    last_target_row = max(window.target_model_frame_indices)
    path_receipt = {
        "schema_version": "mineocclude-experiment-iii-path-receipt-v1",
        "authority_section": "3.3",
        "max_abs_position_deviation": max_abs,
        "tolerance": PATH_REPLAY_TOLERANCE,
        "replayed_path_sha256": path_sha256(replay_positions),
        "expected_path_sha256": spec.path_sha256,
        "replayed_noise_sha256": noise_sha256(spec.replay()[1]),
        "expected_noise_sha256": spec.noise_schedule_sha256,
        "lane_clamp_indices": clamped,
        "lane_clamp_engaged_in_protected_prefix": any(
            index <= last_target_row for index in clamped
        ),
        "last_scored_target_row": last_target_row,
        "observed_by": "raw/server_state.jsonl",
    }

    # ---- timing (3.3) ------------------------------------------------------
    ticks = [int(row["server_tick"]) for row in server_state]
    timing_receipt = {
        "schema_version": "mineocclude-experiment-iii-timing-receipt-v1",
        "authority_section": "3.3",
        "server_state_rows": len(server_state),
        "frame_count": len(frame_records),
        "expected": spec.frames,
        "server_tick_equals_index": ticks == list(range(len(ticks))),
        "capture_hz": CAPTURE_HZ,
        "dt_seconds": DT_SECONDS,
        "observed_by": "raw/server_state.jsonl + raw/client_tick.jsonl",
    }

    # ---- framebuffer (3.3) -------------------------------------------------
    dimensions = {(int(r["width"]), int(r["height"])) for r in frame_records}
    framebuffer_receipt = {
        "schema_version": "mineocclude-experiment-iii-framebuffer-receipt-v1",
        "authority_section": "3.3, 7.10",
        "frame_count": len(frame_records),
        "observed_dimensions": sorted(list(pair) for pair in dimensions),
        "expected_dimensions": [FRAMEBUFFER_WIDTH, FRAMEBUFFER_HEIGHT],
        "all_reads_succeeded": all(bool(r["read_succeeded"]) for r in frame_records),
        "distinct_frame_hashes": len({r["frame_sha256"] for r in frame_records}),
        "writer_drained": bool(completion["drained"]),
        "writer_errors": int(completion["writer_errors"]),
        "observed_by": "PNG IHDR + capture_complete.json",
    }

    completion_receipt = {
        "schema_version": "mineocclude-experiment-iii-capture-completion-v1",
        "authority_section": "8.2",
        "capture_unit_id": spec.capture_unit_id,
        "identity": spec.identity,
        "condition_id": spec.condition.condition_id.value,
        "episode_id": spec.episode_id,
        "spec_sha256": spec.spec_sha256,
        "spec": spec.as_dict(),
        "frames": len(frame_records),
        "target_model_frame_indices": list(window.target_model_frame_indices),
        "fir_labels": [float(label) for label in window.labels],
        "context_ages": list(window.context_ages),
        "extent_classes": list(window.extent_classes),
        "last_preocclusion_model_frame_idx": window.last_preocclusion_model_frame_idx,
        "writer_drained": bool(completion["drained"]),
        "writer_errors": int(completion["writer_errors"]),
        # Amendment 4 §5: the witness is ENGINEERING_ONLY. Its verdict is recorded
        # here so the unit can prove the apparatus was live, and its frames stay
        # in the apparatus tree -- no scientific consumer reads them.
        "liveness_witness": dict(liveness_witness) if liveness_witness else None,
        "liveness_probes": [dict(probe) for probe in liveness_probes],
        "liveness_witness_classification": "ENGINEERING_ONLY",
        "liveness_witness_excluded_from_scientific_evidence": True,
    }

    return {
        "wall_receipt.json": wall_receipt,
        "camera_receipt.json": camera_receipt,
        "target_receipt.json": target_receipt,
        "condition_receipt.json": condition_receipt,
        "path_receipt.json": path_receipt,
        "timing_receipt.json": timing_receipt,
        "framebuffer_receipt.json": framebuffer_receipt,
        "capture_completion.json": completion_receipt,
    }


# --------------------------------------------------------------------------
# Validation (authority 3.3 blockers)
# --------------------------------------------------------------------------


def validate_capture_unit(unit_dir: Path, spec: CaptureUnitSpec) -> dict[str, Any]:
    """Every authority 3.3 check, each raising its own frozen blocker."""
    unit_dir = Path(unit_dir)
    missing = [name for name in REQUIRED_UNIT_FILES if not (unit_dir / name).is_file()]
    if missing:
        raise ExperimentIIIError(
            "CAPTURE_INCOMPLETE",
            f"{spec.capture_unit_id} is missing authority 8.2 files: {missing}",
        )
    frames = sorted((unit_dir / "raw" / "frames").glob("*.png"))
    if len(frames) != spec.frames:
        raise ExperimentIIIError(
            "TIMING_CARDINALITY_MISMATCH",
            f"{spec.capture_unit_id} banked {len(frames)} frames, expected {spec.frames}",
        )

    def load(name: str) -> dict[str, Any]:
        return json.loads((unit_dir / name).read_text(encoding="utf-8"))

    wall = load("wall_receipt.json")
    validate_wall_receipt(wall)

    camera = load("camera_receipt.json")
    if float(camera["max_deviation"]) > CAMERA_TOLERANCE:
        raise ExperimentIIIError(
            "CAMERA_POSE_DRIFT",
            f"{spec.capture_unit_id} camera deviates by {camera['max_deviation']} "
            f"(tolerance {CAMERA_TOLERANCE}): {camera['deviations']}",
        )
    if not camera["camera_lock_active"]:
        raise ExperimentIIIError(
            "CAMERA_POSE_DRIFT", f"{spec.capture_unit_id} ran without the camera lock"
        )

    target = load("target_receipt.json")
    if target["target_required"]:
        if len(target["distinct_target_uuids"]) != 1:
            raise ExperimentIIIError(
                "TARGET_IDENTITY_FAILURE",
                f"{spec.capture_unit_id} saw target UUIDs "
                f"{target['distinct_target_uuids']}; authority 3.3 requires one",
            )
        if int(target["target_respawn_count"]) != 0:
            raise ExperimentIIIError(
                "TARGET_IDENTITY_FAILURE",
                f"{spec.capture_unit_id} respawned its target "
                f"{target['target_respawn_count']} times",
            )
        if not all(target["flags"].values()) or not target["valid"]:
            raise ExperimentIIIError(
                "TARGET_IDENTITY_FAILURE",
                f"{spec.capture_unit_id} target flags {target['flags']} "
                f"problems={target['problems']}",
            )

    condition = load("condition_receipt.json")
    if condition["observed_scenes"] != [spec.condition.scene]:
        raise ExperimentIIIError(
            "WALL_CONDITION_SCENE_MISMATCH",
            f"{spec.capture_unit_id} observed scenes {condition['observed_scenes']}, "
            f"expected only {spec.condition.scene}",
        )

    path = load("path_receipt.json")
    if float(path["max_abs_position_deviation"]) > PATH_REPLAY_TOLERANCE:
        raise ExperimentIIIError(
            "CAPTURE_PATH_HASH_MISMATCH",
            f"{spec.capture_unit_id} replay differs from the server by "
            f"{path['max_abs_position_deviation']}",
        )
    if path["replayed_path_sha256"] != path["expected_path_sha256"]:
        raise ExperimentIIIError(
            "CAPTURE_PATH_HASH_MISMATCH",
            f"{spec.capture_unit_id} path hash {path['replayed_path_sha256']} != "
            f"manifest {path['expected_path_sha256']}",
        )
    if path["replayed_noise_sha256"] != path["expected_noise_sha256"]:
        raise ExperimentIIIError(
            "CAPTURE_NOISE_HASH_MISMATCH",
            f"{spec.capture_unit_id} noise hash differs from the manifest",
        )
    if path["lane_clamp_engaged_in_protected_prefix"]:
        raise ExperimentIIIError(
            "CAPTURE_LANE_CLAMP_ENGAGED",
            f"{spec.capture_unit_id} clamped at or before its last scored target row",
        )

    timing = load("timing_receipt.json")
    if not timing["server_tick_equals_index"]:
        raise ExperimentIIIError(
            "TIMING_CARDINALITY_MISMATCH",
            f"{spec.capture_unit_id} server ticks are not 0..n-1",
        )
    for key in ("server_state_rows", "frame_count"):
        if int(timing[key]) != spec.frames:
            raise ExperimentIIIError(
                "TIMING_CARDINALITY_MISMATCH",
                f"{spec.capture_unit_id} {key}={timing[key]}, expected {spec.frames}",
            )

    framebuffer = load("framebuffer_receipt.json")
    if framebuffer["observed_dimensions"] != [[FRAMEBUFFER_WIDTH, FRAMEBUFFER_HEIGHT]]:
        raise ExperimentIIIError(
            "CAPTURE_FRAMEBUFFER_DIMENSION_MISMATCH",
            f"{spec.capture_unit_id} framebuffer dimensions "
            f"{framebuffer['observed_dimensions']}",
        )
    if not framebuffer["all_reads_succeeded"] or framebuffer["writer_errors"]:
        raise ExperimentIIIError(
            "CAPTURE_WRITER_ERROR",
            f"{spec.capture_unit_id} writer errors={framebuffer['writer_errors']}",
        )
    if not framebuffer["writer_drained"]:
        raise ExperimentIIIError(
            "CAPTURE_WRITER_NOT_DRAINED", f"{spec.capture_unit_id} writer did not drain"
        )

    completion = load("capture_completion.json")
    if completion["spec_sha256"] != spec.spec_sha256:
        raise ExperimentIIIError(
            "PROVENANCE_BINDING_MISMATCH",
            f"{spec.capture_unit_id} was captured under a different frozen spec",
        )
    rows = completion["target_model_frame_indices"]
    if len(rows) != TARGET_ROWS_PER_CAPTURE:
        raise ExperimentIIIError(
            "TARGET_ROW_MISMATCH",
            f"{spec.capture_unit_id} has {len(rows)} target rows, authority freezes "
            f"{TARGET_ROWS_PER_CAPTURE}",
        )
    if list(rows) != list(spec.target_model_frame_indices):
        raise ExperimentIIIError(
            "TARGET_ROW_MISMATCH",
            f"{spec.capture_unit_id} target rows {rows} differ from the identity "
            f"manifest {list(spec.target_model_frame_indices)}",
        )

    visibility = read_jsonl(unit_dir / "raw" / "visibility.jsonl")
    if len(visibility) != spec.frames:
        raise ExperimentIIIError(
            "TIMING_CARDINALITY_MISMATCH",
            f"{spec.capture_unit_id} visibility has {len(visibility)} rows",
        )
    eligible = [index for index, row in enumerate(visibility) if row["target_eligible"]]
    if eligible != list(rows):
        raise ExperimentIIIError(
            "TARGET_ROW_MISMATCH",
            f"{spec.capture_unit_id} visibility marks {len(eligible)} eligible rows "
            f"which do not match the target window",
        )

    return {
        "capture_unit_id": spec.capture_unit_id,
        "validated": True,
        "frames": len(frames),
        "target_rows": len(rows),
        "spec_sha256": spec.spec_sha256,
    }


# --------------------------------------------------------------------------


def _write_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = "".join(
        json.dumps(row, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
        for row in rows
    )
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(payload, encoding="utf-8", newline="\n")
    temporary.replace(path)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _write_json(path: Path, body: Mapping[str, Any]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(body, indent=2, sort_keys=True, allow_nan=False) + "\n"
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(payload, encoding="utf-8", newline="\n")
    temporary.replace(path)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
