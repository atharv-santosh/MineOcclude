"""A5 / I22 — the P1 capture executor, its receipts, and its resume contract.

Every test here would have failed on the source state that entered this sprint,
because ``run_p1_pilot.py --execute`` wrote a plan and printed
``P1_EXECUTED=false``: there was no executor to test. They are written against
the authority — 3.3's receipts, 8.2's inventory, 4.4's visibility schema, 4.6's
target rows, and the Recovery Runbook's A5/A7 state machine — rather than against
the implementation.

The apparatus is simulated by a fixture that writes exactly what the mod writes
(``server_state.jsonl``, ``client_tick.jsonl``, ``raw_actions.jsonl``,
``capture_complete.json``, ``client_authority.json``, ``physical_receipt.json``
and the PNGs). That is deliberate: it lets the *evidence-reading* half be tested
without a renderer, and it means a receipt that silently stopped reading the
apparatus would fail here rather than during a live pilot.
"""

from __future__ import annotations

import json
import struct
import zlib
from pathlib import Path

import numpy as np
import pytest

from mineocclude.experiment_iii.a5_capture import (
    CAMERA_EYE_Y,
    CAMERA_FEET,
    CAMERA_FOV_DEGREES,
    PILOT_EPISODE_IDS,
    CaptureUnitSpec,
    assemble_unit_inventory,
    build_unit_spec,
    capture_a5_unit,
    capture_unit_directory,
    validate_capture_unit,
)
from mineocclude.experiment_iii.a5_pilot import (
    PilotCampaign,
    plan_specs,
    unit_durable_receipt,
    verify_no_production_identity,
)
from mineocclude.experiment_iii.authority import (
    FRAMES_PER_CAPTURE,
    PILOT_IDENTITY_IDS,
    TARGET_ROWS_PER_CAPTURE,
)
from mineocclude.experiment_iii.capture_driver import FrameSink
from mineocclude.experiment_iii.conditions import build_condition_map
from mineocclude.experiment_iii.errors import ExperimentIIIError
from mineocclude.experiment_iii.schema import ConditionId, read_jsonl

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
P0 = REPOSITORY_ROOT / "docs" / "experiment_iii" / "p0"
COHORT = REPOSITORY_ROOT / "docs" / "experiment_iii" / "cohort"


# --------------------------------------------------------------------------
# Fixtures: the frozen inputs, and a simulated apparatus
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def ladder() -> dict:
    return json.loads((P0 / "P0_SELECTED_LADDER.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def identity_rows() -> list[dict]:
    return read_jsonl(COHORT / "pilot_identity_manifest.jsonl")


@pytest.fixture(scope="module")
def plan() -> dict:
    return json.loads(
        (REPOSITORY_ROOT / "docs" / "experiment_iii" / "p1" / "p1_pilot_plan.json")
        .read_text(encoding="utf-8")
    )


@pytest.fixture(scope="module")
def specs(plan, identity_rows, ladder) -> list[CaptureUnitSpec]:
    return plan_specs(plan, identity_rows, ladder)


def _png(width: int = 640, height: int = 360, *, seed: int = 0) -> bytes:
    """A real, decodable PNG whose IHDR carries the frozen dimensions."""

    def chunk(tag: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + tag
            + payload
            + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    row = bytes([0]) + bytes([(seed + i) % 256 for i in range(width * 3)])
    raw = row * height
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


class FakeRuntime:
    """Records the commands a capture issues; writes what the mod would write."""

    dry_run = False

    def __init__(
        self,
        client_root: Path,
        server_root: Path,
        specs_by_unit: dict[tuple[int, str], CaptureUnitSpec],
    ):
        # Two roots, because the apparatus has two: the dedicated server owns
        # mineocclude_out and the client owns mineocclude_client_out. A fixture
        # that merged them would hide exactly the defect this split fixed.
        self.client_root = Path(client_root)
        self.server_root = Path(server_root)
        self.specs = specs_by_unit
        self.commands: list[str] = []
        self.fail_after: int | None = None
        self.captured_episodes: list[tuple[int, str]] = []
        self.witness_episodes: list[int] = []

    def send(self, command: str, **_: object) -> str:
        self.commands.append(command)
        if command.startswith("mineocclude p0 "):
            # Amendment 4's liveness witness: a static NO_WALL slot at the centre
            # calibration placement. Each leg is its own episode; the middle leg
            # is target-absent, so its frames must differ from the two present
            # legs or the witness has not proven the renderer is live.
            parts = command.split()
            witness_episode = int(parts[2])
            # p0 <episodeId> <placementX> <ticks> <conditionId> "<wallBlockId>"
            # <targetPresent> -- the quoted block id is parts[6].
            present = parts[7] == "true"
            self.witness_episodes.append(witness_episode)
            self._write_witness(witness_episode, present=present)
            return ""
        if command.startswith("mineocclude startspec"):
            parts = command.split()
            episode_id = int(parts[3])
            condition_id = parts[10]
            if (
                self.fail_after is not None
                and len(self.captured_episodes) >= self.fail_after
            ):
                raise KeyboardInterrupt("deliberate interruption")
            # Authority 8.2: a unit is addressable by (episode_id, condition_id),
            # because all five conditions of one identity share the episode id.
            self._write_episode(self.specs[(episode_id, condition_id)])
            self.captured_episodes.append((episode_id, condition_id))
        return ""

    def _write_witness(self, episode_id: int, *, present: bool) -> None:
        client_dir = self.client_root / f"episode_{episode_id}"
        (client_dir / "frames").mkdir(parents=True, exist_ok=True)
        frames = 8
        for tick in range(frames):
            # Present and absent legs must render differently; the seed offset is
            # what makes the settled hashes differ across the toggle.
            (client_dir / "frames" / f"{tick:06d}.png").write_bytes(
                _png(seed=tick + (0 if present else 128))
            )
        rows = [
            {
                "episode_id": episode_id,
                "server_tick": tick,
                "render_frame_idx": tick,
                "server_epoch_nanos": 1_000_000 * tick,
                "client_recv_nanos": 1_000_000 * tick,
                "client_capture_nanos": 1_000_000 * tick,
                "tick_queue_depth_at_capture": 0,
                "frame_path": f"frames/{tick:06d}.png",
            }
            for tick in range(frames)
        ]
        (client_dir / "client_tick.jsonl").write_text(
            "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
            encoding="utf-8",
        )
        (client_dir / "capture_complete.json").write_text(
            json.dumps(
                {
                    "schema_version": "mineocclude-capture-drain-v0.1",
                    "episode_id": episode_id,
                    "frame_count": frames,
                    "final_render_frame_idx": frames - 1,
                    "pending_writes": 0,
                    "writer_errors": 0,
                    "drained": True,
                }
            ),
            encoding="utf-8",
        )
        (client_dir / "client_authority.json").write_text(
            json.dumps(
                {
                    "schema_version": "mineocclude-client-authority-v0.1",
                    "episode_id": episode_id,
                    "fov_degrees": CAMERA_FOV_DEGREES,
                    "fov_effect_scale": 0.0,
                    "framebuffer_width": 640,
                    "framebuffer_height": 360,
                    "hud_hidden": True,
                }
            ),
            encoding="utf-8",
        )

    def _write_episode(self, spec: CaptureUnitSpec) -> None:
        client_dir = self.client_root / f"episode_{spec.episode_id}"
        server_dir = self.server_root / f"episode_{spec.episode_id}"
        (client_dir / "frames").mkdir(parents=True, exist_ok=True)
        server_dir.mkdir(parents=True, exist_ok=True)
        positions, noise = spec.replay()

        server_state = []
        client_tick = []
        actions = []
        for tick in range(spec.frames):
            frame_name = f"{tick:06d}.png"
            (client_dir / "frames" / frame_name).write_bytes(_png(seed=tick))
            server_state.append(
                {
                    "episode_id": spec.episode_id,
                    "server_tick": tick,
                    "layout_id": spec.layout_id,
                    "scene": spec.condition.scene,
                    "seed": spec.seed,
                    "q": spec.motion_noise_q,
                    "trajectory_spec_id": spec.capture_unit_id,
                    "spec_hash": spec.identity_spec_hash,
                    "target_entity_uuid": "11111111-2222-3333-4444-555555555555",
                    "target_present": True,
                    "target_respawn_count": 0,
                    "noise_draw": float(noise[tick]),
                    "axis_pos": float(positions[tick]),
                    "axis_velocity": 2.0,
                    "sheep_x": float(positions[tick]),
                    "sheep_y": 4.0,
                    "sheep_z": 6.0,
                    "geometric_visible": False,
                    "player_x": CAMERA_FEET[0],
                    "player_y": CAMERA_FEET[1],
                    "player_z": CAMERA_FEET[2],
                    "player_yaw": 0.0,
                    "player_pitch": 0.0,
                    "server_epoch_nanos": 1_000_000 * tick,
                }
            )
            client_tick.append(
                {
                    "episode_id": spec.episode_id,
                    "server_tick": tick,
                    "render_frame_idx": tick,
                    "server_epoch_nanos": 1_000_000 * tick,
                    "client_recv_nanos": 1_000_000 * tick,
                    "client_capture_nanos": 1_000_000 * tick,
                    "tick_queue_depth_at_capture": 0,
                    "frame_path": f"frames/{frame_name}",
                }
            )
            actions.append(
                {
                    "episode_id": spec.episode_id,
                    "server_tick": tick,
                    "render_frame_idx": tick,
                    "action_idx": tick,
                    "forward": False,
                    "camera_dx": 0.0,
                    "camera_dy": 0.0,
                }
            )

        def jsonl(directory: Path, name: str, rows: list[dict]) -> None:
            (directory / name).write_text(
                "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
                encoding="utf-8",
            )

        jsonl(server_dir, "server_state.jsonl", server_state)
        jsonl(client_dir, "client_tick.jsonl", client_tick)
        jsonl(client_dir, "raw_actions.jsonl", actions)
        (client_dir / "capture_complete.json").write_text(
            json.dumps(
                {
                    "schema_version": "mineocclude-capture-drain-v0.1",
                    "episode_id": spec.episode_id,
                    "frame_count": spec.frames,
                    "final_render_frame_idx": spec.frames - 1,
                    "pending_writes": 0,
                    "writer_errors": 0,
                    "drained": True,
                }
            ),
            encoding="utf-8",
        )
        (client_dir / "client_authority.json").write_text(
            json.dumps(
                {
                    "schema_version": "mineocclude-client-authority-v0.1",
                    "episode_id": spec.episode_id,
                    "fov_degrees": CAMERA_FOV_DEGREES,
                    "fov_effect_scale": 0.0,
                    "framebuffer_width": 640,
                    "framebuffer_height": 360,
                    "hud_hidden": True,
                }
            ),
            encoding="utf-8",
        )
        (server_dir / "physical_receipt.json").write_text(
            json.dumps(_physical_receipt(spec)), encoding="utf-8"
        )


def _physical_receipt(spec: CaptureUnitSpec) -> dict:
    from mineocclude.experiment_iii.conditions import AIR, as_built_wall_cells

    expected = spec.condition.wall_block_id if spec.condition.wall_present else AIR
    return {
        "schema_version": "mineocclude-experiment-iii-physical-receipt-v1",
        "authority_section": "3.3",
        "observation_only": False,
        "scientific_use": "required",
        "episode_id": spec.episode_id,
        "condition_id": spec.condition.condition_id.value,
        "declared_block_id": spec.condition.wall_block_id,
        "scene": spec.condition.scene,
        "wall_present": spec.condition.wall_present,
        "arena_cache_key": f"layout_01|{spec.condition.condition_id.value}|"
        f"{spec.condition.wall_block_id}",
        "wall": {
            "scanned_cell_count": len(as_built_wall_cells()),
            "mismatch_count": 0,
            "unexpected_non_air_count": 0,
            "observed_cells": [
                {
                    "cell_xyz": list(cell),
                    "expected_block_id": expected,
                    "observed_block_id": expected,
                    "matches": True,
                }
                for cell in as_built_wall_cells()
            ],
        },
        "camera": {
            "lock_camera": True,
            "observed": {
                "feet_x": CAMERA_FEET[0],
                "feet_y": CAMERA_FEET[1],
                "feet_z": CAMERA_FEET[2],
                "eye_y": CAMERA_EYE_Y,
                "yaw_degrees": 0.0,
                "pitch_degrees": 0.0,
            },
            "fov_status": "not_server_observable",
        },
        "target": {
            "target_required": True,
            "tagged_target_count": 1,
            "entity_type": "minecraft:sheep",
            "color": "magenta",
            "alive": True,
            "removed": False,
            "tagged": True,
            "adult": True,
            "ai_disabled": True,
            "silent": True,
            "persistent": True,
            "invulnerable": True,
            "uuid_matches": True,
            "world_matches": True,
            "target_entity_uuid": "11111111-2222-3333-4444-555555555555",
            "target_respawn_count": 0,
            "problems": [],
            "valid": True,
        },
    }


def _campaign(tmp_path: Path, specs, ladder) -> tuple[PilotCampaign, FakeRuntime, FrameSink]:
    client_episodes = tmp_path / "runtime" / "client" / "mineocclude_client_out"
    server_episodes = tmp_path / "runtime" / "server" / "mineocclude_out"
    client_episodes.mkdir(parents=True, exist_ok=True)
    server_episodes.mkdir(parents=True, exist_ok=True)
    runtime = FakeRuntime(
        client_episodes,
        server_episodes,
        {
            (spec.episode_id, spec.condition.condition_id.value): spec
            for spec in specs
        },
    )
    sink = FrameSink(client_episodes)
    scores = dict(ladder.get("V_c") or {})
    scores.setdefault("L0", 1.0)
    # The namespace guard admits writes only under an Experiment III root, so the
    # fixture mirrors the production layout inside tmp_path rather than disabling
    # the guard -- the guard is part of what these tests exercise.
    p1_root = tmp_path / "data" / "experiment_iii" / "p1"
    campaign = PilotCampaign(
        specs,
        output_root=p1_root / "captures",
        ledger_path=p1_root / "p1_capture_ledger.jsonl",
        status_root=tmp_path / "status_root",
        namespace_root=tmp_path,
        server_episode_root=server_episodes,
        server_run_root=tmp_path / "runtime" / "server",
        rve_condition_scores=scores,
        source_closure="0" * 64,
    )
    return campaign, runtime, sink


# --------------------------------------------------------------------------
# Plan consumption and identity safety
# --------------------------------------------------------------------------


def test_the_plan_resolves_exactly_ten_pilot_units(specs) -> None:
    assert len(specs) == 10
    assert sorted({spec.identity for spec in specs}) == sorted(PILOT_IDENTITY_IDS)
    for identity in PILOT_IDENTITY_IDS:
        conditions = sorted(
            spec.condition.condition_id.value
            for spec in specs
            if spec.identity == identity
        )
        assert conditions == ["L0", "L1", "L2", "L3", "L4"]


def test_every_unit_carries_nineteen_target_rows(specs) -> None:
    for spec in specs:
        assert len(spec.target_model_frame_indices) == TARGET_ROWS_PER_CAPTURE
    assert sum(len(spec.target_model_frame_indices) for spec in specs) == 190


def test_materials_come_from_the_p0_selection(specs, ladder) -> None:
    """L1-L3 are the P0-selected glasses; L0 is air and L4 is stone."""
    by_condition = {
        spec.condition.condition_id.value: spec.condition.wall_block_id
        for spec in specs
    }
    assert by_condition["L0"] == "minecraft:air"
    assert by_condition["L1"] == ladder["L1"]
    assert by_condition["L2"] == ladder["L2"]
    assert by_condition["L3"] == ladder["L3"]
    assert by_condition["L4"] == "minecraft:stone"
    assert "PENDING_P0_SELECTION" not in set(by_condition.values())


def test_a_production_identity_is_refused(plan) -> None:
    poisoned = json.loads(json.dumps(plan))
    poisoned["units"][0]["identity"] = "e3_t01"
    with pytest.raises(ExperimentIIIError) as error:
        verify_no_production_identity(poisoned)
    assert error.value.blocker == "P1_INCOMPLETE"
    assert "e3_t01" in error.value.message


def test_an_unknown_identity_is_refused(plan) -> None:
    poisoned = json.loads(json.dumps(plan))
    poisoned["units"][3]["identity"] = "e3_p99"
    with pytest.raises(ExperimentIIIError):
        verify_no_production_identity(poisoned)


def test_plan_and_ladder_must_agree_on_the_material(plan, identity_rows, ladder) -> None:
    """A plan naming a material the ladder does not resolve is a refusal."""
    poisoned = json.loads(json.dumps(plan))
    for unit in poisoned["units"]:
        if unit["condition_id"] == "L2":
            unit["wall_block_id"] = "minecraft:lime_stained_glass"
    with pytest.raises(ExperimentIIIError) as error:
        plan_specs(poisoned, identity_rows, ladder)
    assert error.value.blocker == "WALL_MATERIAL_MISMATCH"


def test_pilot_episode_ids_are_the_frozen_pair(specs) -> None:
    assert PILOT_EPISODE_IDS == {"e3_p90": 86901, "e3_p91": 86902}
    for spec in specs:
        assert spec.episode_id == PILOT_EPISODE_IDS[spec.identity]
        assert spec.episode_dir_name.startswith(f"episode_{spec.episode_id}_")


# --------------------------------------------------------------------------
# One unit, end to end
# --------------------------------------------------------------------------


def test_a_unit_captures_validates_and_banks(tmp_path, specs, ladder) -> None:
    campaign, runtime, sink = _campaign(tmp_path, specs[:1], ladder)
    result = campaign.run(runtime, sink, warmup_ticks=10)

    assert result["inventory"]["completed_units"] == 1
    spec = specs[0]
    unit_dir = capture_unit_directory(campaign.output_root, spec)

    # Authority 8.2's inventory, all present.
    for relative in (
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
        "durable_receipt.json",
    ):
        assert (unit_dir / relative).is_file(), relative
    assert len(list((unit_dir / "raw" / "frames").glob("*.png"))) == FRAMES_PER_CAPTURE

    # The 180-row streams really are 180 rows.
    for relative in (
        "raw/server_state.jsonl",
        "raw/client_tick.jsonl",
        "raw/actions.jsonl",
        "raw/frame_map.jsonl",
        "raw/visibility.jsonl",
        "coordinates.jsonl",
    ):
        assert len(read_jsonl(unit_dir / relative)) == FRAMES_PER_CAPTURE, relative


def test_the_startspec_command_carries_the_frozen_spec(tmp_path, specs, ladder) -> None:
    """Python issues the trajectory; the server steps it. The seed must travel."""
    campaign, runtime, sink = _campaign(tmp_path, specs[:1], ladder)
    campaign.run(runtime, sink, warmup_ticks=10)
    spec = specs[0]
    issued = [c for c in runtime.commands if c.startswith("mineocclude startspec")]
    assert len(issued) == 1
    parts = issued[0].split()
    assert parts[2] == spec.layout_id
    assert int(parts[3]) == spec.episode_id
    assert int(parts[4]) == spec.seed
    assert float(parts[5]) == spec.motion_noise_q
    assert int(parts[6]) == spec.frames
    assert spec.condition.wall_block_id in issued[0]


def test_the_visibility_rows_are_the_frozen_schema(tmp_path, specs, ladder) -> None:
    campaign, runtime, sink = _campaign(tmp_path, specs[:1], ladder)
    campaign.run(runtime, sink, warmup_ticks=10)
    spec = specs[0]
    rows = read_jsonl(
        capture_unit_directory(campaign.output_root, spec) / "raw" / "visibility.jsonl"
    )
    assert len(rows) == FRAMES_PER_CAPTURE
    for row in rows:
        assert set(row) >= {
            "condition_id",
            "wall_present",
            "wall_block_id",
            "counterfactual_extent_class",
            "server_geometric_status",
            "magenta_status",
            "magenta_area_pixels",
            "rve_condition_score",
            "target_eligible",
        }
    eligible = [index for index, row in enumerate(rows) if row["target_eligible"]]
    assert eligible == list(spec.target_model_frame_indices)
    assert len(eligible) == TARGET_ROWS_PER_CAPTURE


def test_target_rows_are_identical_across_all_five_conditions(specs) -> None:
    """Authority 4.6: the same 19 rows in L0-L4. The material cannot move them."""
    for identity in PILOT_IDENTITY_IDS:
        rows = {
            spec.condition.condition_id.value: spec.target_model_frame_indices
            for spec in specs
            if spec.identity == identity
        }
        assert len(set(rows.values())) == 1, rows


def test_the_path_receipt_proves_the_server_agreed(tmp_path, specs, ladder) -> None:
    campaign, runtime, sink = _campaign(tmp_path, specs[:1], ladder)
    campaign.run(runtime, sink, warmup_ticks=10)
    receipt = json.loads(
        (
            capture_unit_directory(campaign.output_root, specs[0]) / "path_receipt.json"
        ).read_text(encoding="utf-8")
    )
    assert receipt["max_abs_position_deviation"] <= 1e-9
    assert receipt["replayed_path_sha256"] == receipt["expected_path_sha256"]
    assert receipt["replayed_noise_sha256"] == receipt["expected_noise_sha256"]
    assert receipt["lane_clamp_engaged_in_protected_prefix"] is False


def test_a_drifting_server_path_is_refused(tmp_path, specs, ladder) -> None:
    """The replay check is real: perturb one logged position and it fails."""
    campaign, runtime, sink = _campaign(tmp_path, specs[:1], ladder)
    campaign.run(runtime, sink, warmup_ticks=10)
    spec = specs[0]
    unit_dir = capture_unit_directory(campaign.output_root, spec)
    receipt = json.loads((unit_dir / "path_receipt.json").read_text(encoding="utf-8"))
    receipt["max_abs_position_deviation"] = 1e-3
    (unit_dir / "path_receipt.json").write_text(json.dumps(receipt), encoding="utf-8")
    with pytest.raises(ExperimentIIIError) as error:
        validate_capture_unit(unit_dir, spec)
    assert error.value.blocker == "CAPTURE_PATH_HASH_MISMATCH"


def test_a_wall_mismatch_is_refused(tmp_path, specs, ladder) -> None:
    """The wall receipt is the only independent evidence of what stood there."""
    l4 = [spec for spec in specs if spec.condition.condition_id is ConditionId.L4][:1]
    campaign, runtime, sink = _campaign(tmp_path, l4, ladder)
    campaign.run(runtime, sink, warmup_ticks=10)
    unit_dir = capture_unit_directory(campaign.output_root, l4[0])
    receipt = json.loads((unit_dir / "wall_receipt.json").read_text(encoding="utf-8"))
    receipt["mismatch_count"] = 2
    receipt["mismatches"] = [{"cell": [0, 4, 2], "expected": "x", "observed": "y"}]
    (unit_dir / "wall_receipt.json").write_text(json.dumps(receipt), encoding="utf-8")
    with pytest.raises(ExperimentIIIError) as error:
        validate_capture_unit(unit_dir, l4[0])
    assert error.value.blocker == "WALL_RECEIPT_MISMATCH"


def test_camera_drift_is_refused(tmp_path, specs, ladder) -> None:
    campaign, runtime, sink = _campaign(tmp_path, specs[:1], ladder)
    campaign.run(runtime, sink, warmup_ticks=10)
    unit_dir = capture_unit_directory(campaign.output_root, specs[0])
    receipt = json.loads((unit_dir / "camera_receipt.json").read_text(encoding="utf-8"))
    receipt["max_deviation"] = 0.01
    (unit_dir / "camera_receipt.json").write_text(json.dumps(receipt), encoding="utf-8")
    with pytest.raises(ExperimentIIIError) as error:
        validate_capture_unit(unit_dir, specs[0])
    assert error.value.blocker == "CAMERA_POSE_DRIFT"


def test_a_target_respawn_is_refused(tmp_path, specs, ladder) -> None:
    campaign, runtime, sink = _campaign(tmp_path, specs[:1], ladder)
    campaign.run(runtime, sink, warmup_ticks=10)
    unit_dir = capture_unit_directory(campaign.output_root, specs[0])
    receipt = json.loads((unit_dir / "target_receipt.json").read_text(encoding="utf-8"))
    receipt["target_respawn_count"] = 1
    (unit_dir / "target_receipt.json").write_text(json.dumps(receipt), encoding="utf-8")
    with pytest.raises(ExperimentIIIError) as error:
        validate_capture_unit(unit_dir, specs[0])
    assert error.value.blocker == "TARGET_IDENTITY_FAILURE"


def test_a_short_capture_is_refused(tmp_path, specs, ladder) -> None:
    campaign, runtime, sink = _campaign(tmp_path, specs[:1], ladder)
    campaign.run(runtime, sink, warmup_ticks=10)
    unit_dir = capture_unit_directory(campaign.output_root, specs[0])
    frames = sorted((unit_dir / "raw" / "frames").glob("*.png"))
    frames[-1].unlink()
    with pytest.raises(ExperimentIIIError) as error:
        validate_capture_unit(unit_dir, specs[0])
    assert error.value.blocker == "TIMING_CARDINALITY_MISMATCH"


# --------------------------------------------------------------------------
# Durability
# --------------------------------------------------------------------------


def test_the_durable_receipt_hashes_every_banked_file(tmp_path, specs, ladder) -> None:
    campaign, runtime, sink = _campaign(tmp_path, specs[:1], ladder)
    campaign.run(runtime, sink, warmup_ticks=10)
    unit_dir = capture_unit_directory(campaign.output_root, specs[0])
    receipt = json.loads((unit_dir / "durable_receipt.json").read_text(encoding="utf-8"))
    assert receipt["readback_verified"] is True
    assert receipt["file_count"] >= FRAMES_PER_CAPTURE
    assert receipt["total_bytes"] > 0
    import hashlib

    for relative, entry in receipt["files"].items():
        payload = (unit_dir / relative).read_bytes()
        assert hashlib.sha256(payload).hexdigest() == entry["sha256"], relative
        assert len(payload) == entry["bytes"]


# --------------------------------------------------------------------------
# Resume (Recovery Runbook A5/A7)
# --------------------------------------------------------------------------


def test_completed_units_are_skipped_and_not_recaptured(tmp_path, specs, ladder) -> None:
    """The heart of the resume contract: COMPLETE work is never redone."""
    campaign, runtime, sink = _campaign(tmp_path, specs[:3], ladder)
    first = campaign.run(runtime, sink, warmup_ticks=10)
    assert len(first["captured"]) == 3
    assert first["skipped"] == []
    episodes_after_first = list(runtime.captured_episodes)

    # A second campaign over the same ledger and output root: same spec, so every
    # unit is already COMPLETE and nothing is issued to the apparatus again.
    resumed, runtime2, sink2 = _campaign(tmp_path, specs[:3], ladder)
    second = resumed.run(runtime2, sink2, warmup_ticks=10)
    assert len(second["skipped"]) == 3
    assert second["captured"] == []
    assert runtime2.captured_episodes == []
    assert second["inventory"]["completed_units"] == 3
    assert episodes_after_first  # the first run really did capture


def test_an_interrupted_campaign_resumes_at_the_failed_unit(
    tmp_path, specs, ladder
) -> None:
    """Interrupt mid-run, restart on the same spec, finish without duplicates."""
    campaign, runtime, sink = _campaign(tmp_path, specs[:4], ladder)
    runtime.fail_after = 2
    with pytest.raises(KeyboardInterrupt):
        campaign.run(runtime, sink, warmup_ticks=10)

    banked = campaign.inventory()
    assert banked["completed_units"] == 2, "two units should have survived"

    resumed, runtime2, sink2 = _campaign(tmp_path, specs[:4], ladder)
    result = resumed.run(runtime2, sink2, warmup_ticks=10)
    assert len(result["skipped"]) == 2
    assert len(result["captured"]) == 2
    # The two survivors were never re-issued to the apparatus.
    assert len(runtime2.captured_episodes) == 2
    inventory = resumed.inventory()
    assert inventory["completed_units"] == 4
    assert inventory["complete"] is True
    assert inventory["duplicate_accepted_units"] == []


def test_spec_drift_refuses_to_adopt_the_partial(tmp_path, specs, ladder) -> None:
    """Same-spec resume only: a changed spec must recapture, never resume."""
    campaign, runtime, sink = _campaign(tmp_path, specs[:1], ladder)
    campaign.run(runtime, sink, warmup_ticks=10)

    drifted = CaptureUnitSpec(
        **{
            **{
                field: getattr(specs[0], field)
                for field in specs[0].__dataclass_fields__
            },
            "seed": specs[0].seed + 1,
        }
    )
    assert drifted.spec_sha256 != specs[0].spec_sha256

    resumed, _runtime2, _sink2 = _campaign(tmp_path, [drifted], ladder)
    decision = resumed.resume_decision(drifted)
    assert decision["action"] == "RECAPTURE"
    assert decision["reason"] == "SPEC_DRIFT"


def test_the_ledger_is_hash_chained_and_tamper_evident(tmp_path, specs, ladder) -> None:
    campaign, runtime, sink = _campaign(tmp_path, specs[:1], ladder)
    campaign.run(runtime, sink, warmup_ticks=10)
    campaign.ledger.verify_chain()

    path = tmp_path / "data" / "experiment_iii" / "p1" / "p1_capture_ledger.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    record = json.loads(lines[0])
    record["state"] = "COMPLETE"
    lines[0] = json.dumps(record, sort_keys=True, separators=(",", ":"))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    from mineocclude.experiment_iii.execution import HashChainLedger

    with pytest.raises(ExperimentIIIError):
        HashChainLedger(path)


def test_no_unit_is_accepted_twice(tmp_path, specs, ladder) -> None:
    campaign, runtime, sink = _campaign(tmp_path, specs, ladder)
    campaign.run(runtime, sink, warmup_ticks=10)
    completions = [
        record["unit_id"]
        for record in campaign.ledger.records
        if record["state"] == "COMPLETE"
    ]
    assert len(completions) == len(set(completions)) == 10
    assert campaign.inventory()["duplicate_accepted_units"] == []


# --------------------------------------------------------------------------
# The whole pilot
# --------------------------------------------------------------------------


def test_the_full_pilot_produces_ten_units_and_190_rows(tmp_path, specs, ladder) -> None:
    campaign, runtime, sink = _campaign(tmp_path, specs, ladder)
    result = campaign.run(runtime, sink, warmup_ticks=10)
    inventory = result["inventory"]
    assert inventory["complete"] is True
    assert inventory["completed_units"] == 10
    assert inventory["target_rows_total"] == 190
    assert inventory["production_identities_used"] is False
    assert inventory["identities"] == ["e3_p90", "e3_p91"]
    assert inventory["conditions"] == ["L0", "L1", "L2", "L3", "L4"]
    for unit in inventory["units"]:
        assert unit["complete"] and unit["durable_receipt"]
        assert unit["ledger_state"] == "COMPLETE"


# --------------------------------------------------------------------------
# The status surface is observational only
# --------------------------------------------------------------------------


def test_the_campaign_writes_the_authority_status_document(
    tmp_path, specs, ladder
) -> None:
    campaign, runtime, sink = _campaign(tmp_path, specs[:2], ladder)
    campaign.run(runtime, sink, warmup_ticks=10)
    path = tmp_path / "status_root" / "docs" / "experiment_iii" / "status" / "A5_status.json"
    assert path.is_file(), "A5 must publish the authority-defined status document"
    document = json.loads(path.read_text(encoding="utf-8"))
    for field in (
        "PROCESS_ALIVE",
        "STAGE",
        "STAGE_STATUS",
        "TOTAL_UNITS",
        "COMPLETED_UNITS",
        "REMAINING_UNITS",
        "CURRENT_UNIT",
        "LAST_COMPLETED_UNIT",
        "ELAPSED_TIME",
        "LAST_MESSAGE_AT",
        "RETRY_COUNT",
        "CURRENT_BLOCKER",
    ):
        assert field in document, field
    assert document["STAGE"] == "A5"
    assert document["TOTAL_UNITS"] == 2
    assert document["COMPLETED_UNITS"] == 2
    assert document["REMAINING_UNITS"] == 0


def test_deleting_the_status_document_changes_nothing(tmp_path, specs, ladder) -> None:
    """LIVE_STATUS_CONTRACT: losing it must never affect resume or results."""
    campaign, runtime, sink = _campaign(tmp_path, specs[:2], ladder)
    campaign.run(runtime, sink, warmup_ticks=10)
    status = tmp_path / "status_root" / "docs" / "experiment_iii" / "status" / "A5_status.json"
    status.unlink()

    resumed, runtime2, sink2 = _campaign(tmp_path, specs[:2], ladder)
    result = resumed.run(runtime2, sink2, warmup_ticks=10)
    assert len(result["skipped"]) == 2
    assert runtime2.captured_episodes == []


def test_status_cannot_steer_scientific_control_flow(tmp_path, specs, ladder) -> None:
    """A tampered status claiming everything is done must not skip a unit.

    Control flow comes from the hash-chained ledger. This writes a status
    document asserting the campaign is COMPLETE with every unit finished, then
    runs anyway: the units must still be captured.
    """
    campaign, runtime, sink = _campaign(tmp_path, specs[:2], ladder)
    status_dir = tmp_path / "status_root" / "docs" / "experiment_iii" / "status"
    status_dir.mkdir(parents=True, exist_ok=True)
    (status_dir / "A5_status.json").write_text(
        json.dumps(
            {
                "PROCESS_ALIVE": False,
                "STAGE": "A5",
                "STAGE_STATUS": "COMPLETE",
                "TOTAL_UNITS": 2,
                "COMPLETED_UNITS": 2,
                "REMAINING_UNITS": 0,
                "CURRENT_UNIT": None,
                "LAST_COMPLETED_UNIT": specs[1].capture_unit_id,
                "ELAPSED_TIME": 1.0,
                "LAST_MESSAGE_AT": "2026-09-01T00:00:00+00:00",
                "LAST_MESSAGE": "fabricated",
                "ERRORS_SEEN": 0,
                "CURRENT_BLOCKER": None,
                "RETRY_COUNT": 0,
                "POST_STAGE_VALIDATOR_STATUS": "PASS",
                "NEXT_STAGE": "A6",
                "PROGRAM_STAGE": "III_A",
                "III_A_STATUS": "RUNNING",
                "III_B_STATUS": "NOT_STARTED",
            }
        ),
        encoding="utf-8",
    )
    result = campaign.run(runtime, sink, warmup_ticks=10)
    assert len(result["captured"]) == 2, "status must not have skipped any unit"
    assert len(runtime.captured_episodes) == 2


def test_the_campaign_source_never_reads_a_status_document() -> None:
    """The cardinal rule, enforced structurally rather than by inspection."""
    source = (
        REPOSITORY_ROOT
        / "src"
        / "mineocclude"
        / "experiment_iii"
        / "a5_pilot.py"
    ).read_text(encoding="utf-8")
    for forbidden in ("status_path(", "read_status", "json.load", "_status.to_dict()"):
        assert forbidden not in source, f"a5_pilot reads status: {forbidden}"


# --------------------------------------------------------------------------
# The engineering witness stays out of the scientific inventory
# --------------------------------------------------------------------------


def test_no_witness_artifact_enters_a_capture_unit(tmp_path, specs, ladder) -> None:
    """Amendment 4's witness is apparatus evidence, never measurement."""
    campaign, runtime, sink = _campaign(tmp_path, specs[:2], ladder)
    campaign.run(runtime, sink, warmup_ticks=10)
    for spec in specs[:2]:
        unit_dir = capture_unit_directory(campaign.output_root, spec)
        # Relative to the unit, not absolute: the tmp_path itself is named after
        # this test and would otherwise match the very substring being excluded.
        banked = [
            path.relative_to(unit_dir).as_posix()
            for path in unit_dir.rglob("*")
            if path.is_file()
        ]
        assert not [name for name in banked if "WITNESS" in name.upper()]
        assert not [name for name in banked if "LIVENESS" in name.upper()]
        receipt = json.loads(
            (unit_dir / "durable_receipt.json").read_text(encoding="utf-8")
        )
        assert not [
            name for name in receipt["files"] if "witness" in name.lower()
        ]


# --------------------------------------------------------------------------
# Amendment 4 -- the mandatory pre-capture liveness witness
# --------------------------------------------------------------------------


def test_every_unit_is_preceded_by_the_liveness_witness(tmp_path, specs, ladder) -> None:
    """Amendment 4 requires it before each authority-required capture unit."""
    campaign, runtime, sink = _campaign(tmp_path, specs[:2], ladder)
    campaign.run(runtime, sink, warmup_ticks=10)

    # Three legs per unit: PRESENT -> ABSENT -> PRESENT.
    assert len(runtime.witness_episodes) == 6
    for spec in specs[:2]:
        completion = json.loads(
            (
                capture_unit_directory(campaign.output_root, spec)
                / "capture_completion.json"
            ).read_text(encoding="utf-8")
        )
        witness = completion["liveness_witness"]
        assert witness is not None
        assert witness["classification"] == "ENGINEERING_ONLY"
        assert witness["scene"] == "NO_WALL"
        assert witness["wall_block_id"] == "minecraft:air"
        assert witness["transition"] == [
            "TARGET_PRESENT",
            "TARGET_ABSENT",
            "TARGET_PRESENT",
        ]
        assert len(completion["liveness_probes"]) == 2


def test_the_witness_is_material_independent(tmp_path, specs, ladder) -> None:
    """It runs NO_WALL for L4 stone exactly as it does for L0 air.

    This is the whole point of Amendment 4: under v1.6 the witness inherited the
    unit's own wall, so an opaque condition rendered PRESENT and ABSENT
    identically and every L4 unit was refused on a physically correct
    observation. The witness must not depend on the material being measured.
    """
    l4 = [spec for spec in specs if spec.condition.condition_id is ConditionId.L4][:1]
    campaign, runtime, sink = _campaign(tmp_path, l4, ladder)
    campaign.run(runtime, sink, warmup_ticks=10)
    witness_commands = [c for c in runtime.commands if c.startswith("mineocclude p0 ")]
    assert len(witness_commands) == 3
    for command in witness_commands:
        assert "minecraft:air" in command
        assert "L0" in command
        assert "minecraft:stone" not in command


def test_witness_episodes_never_collide_with_capture_episodes(
    tmp_path, specs, ladder
) -> None:
    campaign, runtime, sink = _campaign(tmp_path, specs, ladder)
    campaign.run(runtime, sink, warmup_ticks=10)
    captured = {episode for episode, _condition in runtime.captured_episodes}
    assert captured == {86901, 86902}
    assert not (set(runtime.witness_episodes) & captured)
    assert all(episode >= 900_000 for episode in runtime.witness_episodes)


# --------------------------------------------------------------------------
# The motion schedule startspec refuses to run without
# --------------------------------------------------------------------------


def test_the_motion_schedule_is_written_before_startspec(tmp_path, specs, ladder) -> None:
    """The live pilot's first unit died on exactly this file being absent.

    ``/mineocclude startspec`` loads
    ``<server run dir>/mineocclude_motion_schedules/episode_<id>.json``
    synchronously and refuses the episode when it is missing -- the server will
    not synthesize a scientific schedule. The executor must therefore serialize
    it first, and it must exist by the time the command is issued.
    """
    from mineocclude.experiment_iii.a5_capture import (
        MOTION_SCHEDULE_FORMAT_VERSION,
        write_motion_schedule,
    )

    campaign, runtime, sink = _campaign(tmp_path, specs[:1], ladder)
    campaign.run(runtime, sink, warmup_ticks=10)

    spec = specs[0]
    schedule_path = (
        campaign.server_run_root
        / "mineocclude_motion_schedules"
        / f"episode_{spec.episode_id}.json"
    )
    assert schedule_path.is_file(), "startspec would have refused this episode"
    body = json.loads(schedule_path.read_text(encoding="utf-8"))
    assert body["schedule_format_version"] == MOTION_SCHEDULE_FORMAT_VERSION
    assert body["trajectory_spec_id"] == spec.capture_unit_id
    assert body["spec_hash"] == spec.identity_spec_hash
    assert body["expected_ticks"] == spec.frames


def test_the_motion_schedule_covers_every_tick_without_gaps(tmp_path, specs) -> None:
    """MotionSchedule.load refuses a schedule that does not cover [0, ticks)."""
    from mineocclude.experiment_iii.a5_capture import write_motion_schedule

    for spec in specs:
        body = write_motion_schedule(tmp_path, spec)["body"]
        expected_start = 0
        for segment in body["segments"]:
            assert segment["start_model_frame_idx"] == expected_start
            assert segment["stop_model_frame_idx_exclusive"] > expected_start
            expected_start = segment["stop_model_frame_idx_exclusive"]
        assert expected_start == spec.frames, spec.capture_unit_id


def test_the_commanded_speed_matches_the_frozen_direction(tmp_path, specs) -> None:
    """Authority 3.1 freezes 2.0 blocks/s; the manifest freezes the sign.

    A wrong sign would still produce 180 frames and a plausible-looking unit, so
    this is checked here as well as by the 1e-9 path replay in the receipt.
    """
    from mineocclude.experiment_iii.a5_capture import write_motion_schedule

    for spec in specs:
        body = write_motion_schedule(tmp_path, spec)["body"]
        speed = body["segments"][0]["signed_speed_blocks_per_second"]
        assert abs(speed) == 2.0 == spec.speed_blocks_per_second
        expected_sign = 1.0 if spec.direction == "LEFT_TO_RIGHT" else -1.0
        assert speed == expected_sign * 2.0, (spec.capture_unit_id, spec.direction)


def test_a_died_attempt_is_recorded_as_a_retry_not_a_first_attempt(
    tmp_path, specs, ladder
) -> None:
    """Ledger history with nothing on disk is a discarded partial, not a fresh unit.

    The live pilot produced exactly this state: e3_p90__L0 reached RUNNING and
    then the driver died with no capture directory. Recovery Runbook step 5 says
    discard the partial and append PLANNED with retry_same_spec=true; recording
    it as a first attempt would hide a retry that authority 8.3 requires to stay
    visible.
    """
    campaign, runtime, sink = _campaign(tmp_path, specs[:1], ladder)
    spec = specs[0]
    campaign.ledger.append(spec.capture_unit_id, "PLANNED", spec_sha256=spec.spec_sha256)
    campaign.ledger.append(spec.capture_unit_id, "RUNNING", spec_sha256=spec.spec_sha256)

    decision = campaign.resume_decision(spec)
    assert decision["action"] == "RECAPTURE"
    assert decision["reason"] == "DISCARDED_PARTIAL_FROM_RUNNING"

    campaign.run(runtime, sink, warmup_ticks=10)
    planned = [
        record
        for record in campaign.ledger.records
        if record["unit_id"] == spec.capture_unit_id and record["state"] == "PLANNED"
    ]
    assert planned[-1]["retry_same_spec"] is True
    assert campaign.inventory()["completed_units"] == 1
    assert campaign.inventory()["duplicate_accepted_units"] == []
