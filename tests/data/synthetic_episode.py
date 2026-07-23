"""Shared helper: synthesize one on-disk capture episode for C4/C5 tests.

Every artifact is synthetic and never scientific evidence; it exists so the
strict alignment, visibility, conversion, and QA paths can be exercised on
CPU without Minecraft.
"""
from __future__ import annotations

import json
import os

import numpy as np
from PIL import Image


def write_jsonl(path, rows):
    with open(path, "w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")


def make_episode(
    root,
    episode_id: int = 1,
    layout_id: str = "layout_01",
    n: int = 8,
    visible_pattern: list[bool] | None = None,
    scene: str = "NORMAL",
    yaw_impulses: dict[int, float] | None = None,
    frame_size: tuple[int, int] = (64, 36),
):
    """Create server_dir and client_dir for one consistent synthetic episode.

    ``visible_pattern[i]`` controls both the server's geometric flag and
    whether the frame PNG contains a magenta patch (so the interim detector
    agrees). ``yaw_impulses`` maps tick -> yaw delta in degrees, recorded
    consistently in both the server yaw sequence and the client camera_dx.
    """
    if visible_pattern is None:
        if n >= 6:
            visible_pattern = [True] * 3 + [False] * 3 + [True] * (n - 6)
        else:
            visible_pattern = [True] * n
    assert len(visible_pattern) == n
    yaw_impulses = yaw_impulses or {}

    server_dir = os.path.join(root, "server", f"episode_{episode_id}")
    client_dir = os.path.join(root, "client", f"episode_{episode_id}")
    os.makedirs(server_dir, exist_ok=True)
    os.makedirs(os.path.join(client_dir, "frames"), exist_ok=True)

    width, height = frame_size
    state_rows, action_rows, tick_rows = [], [], []
    yaw = 0.0
    for tick in range(n):
        yaw_delta = yaw_impulses.get(tick, 0.0)
        yaw += yaw_delta
        state_rows.append({
            "episode_id": episode_id,
            "server_tick": tick,
            "layout_id": layout_id,
            "regime": "A",
            "scene": scene,
            "seed": 42,
            "v": 1.0,
            "q": 0.05,
            "hidden_frames": 3,
            "noise_draw": 0.0,
            "axis_pos": float(tick) * 0.05,
            "axis_velocity": 1.0,
            "sheep_x": 10.0 + tick * 0.05,
            "sheep_y": 64.0,
            "sheep_z": 11.0,
            "geometric_visible": bool(visible_pattern[tick]),
            "player_x": 20.0,
            "player_y": 65.62,
            "player_z": 2.5,
            "player_yaw": yaw,
            "player_pitch": 10.0,
            "server_epoch_nanos": 1_000_000 * tick,
        })
        action_rows.append({
            "episode_id": episode_id,
            "server_tick": tick,
            "render_frame_idx": tick,
            "action_idx": tick,
            "forward": False, "back": False, "left": False, "right": False,
            "jump": False, "sneak": False, "sprint": False,
            "use": False, "attack": False, "drop": False, "pick_item": False,
            "hotbar": 0,
            "camera_dx": yaw_delta,
            "camera_dy": 0.0,
        })
        frame_rel = f"frames/{tick:06d}.png"
        tick_rows.append({
            "episode_id": episode_id,
            "server_tick": tick,
            "render_frame_idx": tick,
            "server_epoch_nanos": 1_000_000 * tick,
            "client_recv_nanos": 1_000_000 * tick + 100,
            "client_capture_nanos": 1_000_000 * tick + 200,
            "frame_path": frame_rel,
        })
        image = np.full((height, width, 3), 90, dtype=np.uint8)
        if visible_pattern[tick]:
            image[height // 2 - 4:height // 2 + 4,
                  width // 2 - 4:width // 2 + 4] = (191, 76, 201)
        Image.fromarray(image).save(os.path.join(client_dir, frame_rel))

    # Server-side sidecar records, mirroring the real mod's outputs.
    with open(os.path.join(server_dir, "layout_meta.json"), "w") as handle:
        json.dump({"layout_id": layout_id, "wall_axis": "X",
                   "wall_ortho": 2.0, "scene": scene,
                   "markers": [
                       {"role": "near_west", "color": "blue",
                        "x": -7, "y": 3, "z": 1},
                       {"role": "near_east", "color": "yellow",
                        "x": 7, "y": 3, "z": 1},
                       {"role": "far_west", "color": "lime",
                        "x": -7, "y": 3, "z": -4},
                       {"role": "far_east", "color": "white",
                        "x": 7, "y": 3, "z": -4},
                   ]}, handle)
    with open(os.path.join(server_dir, "reset_result.json"), "w") as handle:
        json.dump({"episode_id": episode_id, "layout_id": layout_id,
                   "scene": scene, "seed": 42, "v": 1.0, "q": 0.05,
                   "expected_target_count": 0 if scene == "NO_SHEEP" else 1,
                   "observed_target_count": 0 if scene == "NO_SHEEP" else 1,
                   "start_axis_pos": 0.0,
                   "rng_source": "immutable_numpy_schedule",
                   "schedule_draws": n, "target_count_ok": True,
                   "lock_camera": True, "impulse_tick": -1,
                   "impulse_yaw_deg": 0.0, "reveal_ticks": 0}, handle)

    write_jsonl(os.path.join(server_dir, "server_state.jsonl"), state_rows)
    write_jsonl(os.path.join(client_dir, "raw_actions.jsonl"), action_rows)
    write_jsonl(os.path.join(client_dir, "client_tick.jsonl"), tick_rows)
    return server_dir, client_dir
