"""Generate a production-SHAPED synthetic capture corpus for the A8->A19 shadow.

25 identities x 5 conditions x 180 frames, 19 target rows each -- the frozen
production shape, with fabricated physics. It exists to prove the software
contract between stages, never to produce a number anyone reads: no MineWorld
weights are loaded and no scientific claim is derived from it.

Frames are not written: the shadow's extraction seam supplies a synthetic frame
loader, exactly as the qualified A5 stub does.
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

SHADOW = Path(sys.argv[1] if len(sys.argv) > 1 else "/home/sagemaker-user/exp3-shadow-pipeline")
sys.path.insert(0, str(SHADOW / "src"))

from mineocclude.experiment_iii.authority import verify_authority_binding
from mineocclude.experiment_iii.execution import HashChainLedger
from mineocclude.experiment_iii.schema import read_jsonl

PROD = SHADOW / "data/experiment_iii/production"
CAPTURES = PROD / "captures"
CONDITIONS = ("L0", "L1", "L2", "L3", "L4")
FRAMES = 180
WALL = {"L0": "minecraft:air", "L1": "minecraft:glass", "L2": "minecraft:oak_planks",
        "L3": "minecraft:stone", "L4": "minecraft:obsidian"}
EXTENT = {"L0": "EXTENT_FULLY_VISIBLE", "L1": "EXTENT_PARTIAL_25",
          "L2": "EXTENT_PARTIAL_50", "L3": "EXTENT_PARTIAL_75", "L4": "EXTENT_FULLY_OCCLUDED"}


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        for row in rows:
            fh.write(json.dumps(row, sort_keys=True) + "\n")


def main() -> int:
    binding = verify_authority_binding()
    manifest = read_jsonl(SHADOW / "docs/experiment_iii/cohort/production_identity_manifest.jsonl")
    ledger = HashChainLedger(PROD / "production_capture_ledger.jsonl")
    units = 0
    for row in manifest:
        identity = str(row["identity"])
        episode = int(row["episode_id"])
        seed = int(row["seed"])
        spec = str(row["spec_hash"])
        for condition in CONDITIONS:
            unit_id = f"{identity}__{condition}"
            unit = CAPTURES / unit_id
            rng = random.Random(f"{unit_id}")
            frame_map, actions, server, ticks, vis, coords = [], [], [], [], [], []
            for i in range(FRAMES):
                pos = -7.9 + 0.1 * i + rng.uniform(-0.01, 0.01)
                frame_map.append({"episode_id": episode, "frame_path": f"raw/frames/{i:06d}.png",
                                  "frame_sha256": f"{i:064x}", "height": 360,
                                  "render_frame_idx": i, "server_tick": i, "width": 640})
                actions.append({"episode_id": episode, "server_tick": i, "render_frame_idx": i,
                                "action_idx": i, "forward": False, "back": False, "left": False,
                                "right": False, "jump": False, "sneak": False, "sprint": False,
                                "use": False, "attack": False, "drop": False, "pick_item": False,
                                "hotbar": 0, "camera_dx": 0.0, "camera_dy": 0.0})
                server.append({"episode_id": episode, "server_tick": i, "layout_id": "layout_01",
                               "regime": "A", "scene": "SHADOW", "seed": seed, "v": 2.0,
                               "commanded_v": 2.0, "motion_segment_index": 0,
                               "trajectory_spec_id": unit_id, "spec_hash": spec, "q": 0.05,
                               "hidden_frames": FRAMES, "target_present": True,
                               "geometric_visible": condition != "L4",
                               "axis_pos": pos, "axis_velocity": 2.0, "noise_draw": 0.0,
                               "sheep_x": pos, "sheep_y": 4.0, "sheep_z": 6.0,
                               "player_x": 0.5, "player_y": 5.62, "player_z": -5.5,
                               "player_yaw": 0.0, "player_pitch": 0.0,
                               "server_epoch_nanos": 1_000_000 + i})
                ticks.append({"episode_id": episode, "server_tick": i, "render_frame_idx": i,
                              "server_epoch_nanos": 1_000_000 + i,
                              "client_recv_nanos": 1_000_001 + i,
                              "client_capture_nanos": 1_000_002 + i,
                              "tick_queue_depth_at_capture": 0,
                              "frame_path": f"frames/{i:06d}.png"})
                vis.append({"condition_id": condition, "counterfactual_extent_class": EXTENT[condition],
                            "magenta_area_pixels": 0, "magenta_status": "not_detected",
                            "model_frame_idx": i, "rve_condition_score": None,
                            "server_geometric_status": "visible",
                            "target_eligible": False, "wall_block_id": WALL[condition],
                            "wall_present": condition != "L0"})
                coords.append({"axis_pos": pos, "axis_velocity": 2.0, "noise_draw": 0.0,
                               "server_tick": i, "sheep_x": pos, "sheep_y": 4.0, "sheep_z": 6.0})
            write_jsonl(unit / "raw/frame_map.jsonl", frame_map)
            write_jsonl(unit / "raw/actions.jsonl", actions)
            write_jsonl(unit / "raw/server_state.jsonl", server)
            write_jsonl(unit / "raw/client_tick.jsonl", ticks)
            write_jsonl(unit / "raw/visibility.jsonl", vis)
            write_jsonl(unit / "coordinates.jsonl", coords)
            (unit / "capture_completion.json").write_text(json.dumps({
                "capture_unit_id": unit_id, "identity": identity, "condition_id": condition,
                "spec_sha256": spec, "seed": seed, "episode_id": episode,
                "target_model_frame_indices": [int(v) for v in row["target_model_frame_indices"]],
                "spec": {"seed": seed}, "frames": FRAMES, "shadow_fixture": True,
            }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            (unit / "durable_receipt.json").write_text(json.dumps({
                "capture_unit_id": unit_id, "authority_section": "8.2",
                "durability_mode": "SHADOW_FIXTURE", "file_count": 8,
                "shadow_fixture": True,
            }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            for state in ("PLANNED", "RUNNING", "CAPTURED", "VALIDATED", "DURABLE", "COMPLETE"):
                ledger.append(unit_id, state, spec_sha256=spec,
                              authority_sha256=binding["AUTHORITY_SHA256"],
                              source_closure="shadow", retry_same_spec=False)
            units += 1
    print(f"SHADOW_UNITS={units}")
    print(f"SHADOW_LEDGER_RECORDS={len(ledger.records)}")
    print(f"SHADOW_COMPLETE_UNITS={len(ledger.complete_units())}")
    return 0


raise SystemExit(main())
