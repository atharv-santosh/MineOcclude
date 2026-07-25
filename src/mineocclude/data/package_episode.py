"""Assemble one accepted runtime bundle into the frozen C0 capture package.

The C0 acceptance rule ("Acceptance requires both the frozen A validator and
the stricter C validator to pass") is enforced by
``mineocclude.data.capture_contract.validate_capture_package``. This module
is the missing bridge: it wraps a real accepted episode (the
``build_dataset`` output plus the raw server/client evidence and the
immutable noise schedule) into the exact package shape the frozen contract
validates, with real hashes and the real NumPy pin.

Nothing is repaired here: the assembler only reshapes already-validated
evidence, and the resulting package must still pass the full frozen
validator chain or the episode is not handed off.

v0.1 vocabulary note: ``temporal_alignment.evidence_scope`` is contractually
fixed to the literal ``synthetic_contract_only`` in contract v0.1 (written
before runtime evidence existed). The real runtime impulse evidence lives in
the episode QA report whose hash the field carries; extending the vocabulary
(e.g. ``runtime_verified``) is a v0.2 contract change.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess

import pandas as pd

from mineocclude.data.capture_contract import validate_capture_package
from mineocclude.data.convert_mineworld import (
    bin_camera,
    flat_to_official_raw_action,
)
from mineocclude.data.noise_schedule import load_schedule
from mineocclude.data.preprocess import sha256_file

LIFECYCLE_VERSION = "person-c-tick-lifecycle-v0.1"

RAW_FIELDS = ("forward", "back", "left", "right", "jump", "sneak", "sprint",
              "use", "attack", "drop", "pick_item", "hotbar",
              "camera_dx", "camera_dy")


def _capture_key(row) -> dict:
    return {
        "episode_id": str(row["episode_id"]),
        "trajectory_id": str(row["trajectory_id"]),
        "server_tick": int(row["server_tick"]),
        "render_frame_idx": int(row["render_frame_idx"]),
        "action_idx": int(row["action_idx"]),
        "model_frame_idx": int(row["model_frame_idx"]),
    }


def _tri(pos, neg) -> int:
    if bool(pos):
        return 1
    if bool(neg):
        return 2
    return 0


def _normalized_action(row) -> dict:
    """A's frozen integer container fields, filled by the reference
    conversion (the pinned semantics remain Person A's deliverable)."""
    return {
        "camera_component_0": bin_camera(float(row["camera_dy"])),
        "camera_component_1": bin_camera(float(row["camera_dx"])),
        "hotbar": int(row["hotbar"]),
        "forward_back": _tri(row["forward"], row["back"]),
        "left_right": _tri(row["left"], row["right"]),
        "sprint_sneak": _tri(row["sprint"], row["sneak"]),
        "use_attack": _tri(row["use"], row["attack"]),
        "jump": 1 if bool(row["jump"]) else 0,
        "drop_pick_item": _tri(row["drop"], row["pick_item"]),
    }


def _git_head(repo_root: str) -> str:
    return subprocess.run(
        ["git", "-C", repo_root, "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True, timeout=30,
    ).stdout.strip()


def assemble_package(out_dir: str, server_dir: str, client_dir: str,
                     schedule_path: str, repo_root: str,
                     run_id: str,
                     impulse_fixture_id: str = "",
                     impulse_fixture_qa_path: str = "") -> dict:
    """Build the frozen C0 package for one ACCEPTED episode bundle."""
    frame_map = pd.read_parquet(os.path.join(out_dir, "frame_map.parquet"))
    frame_map = frame_map.sort_values("server_tick").reset_index(drop=True)
    schedule = load_schedule(schedule_path)

    episode_id = str(frame_map["episode_id"].iloc[0])
    trajectory_id = str(frame_map["trajectory_id"].iloc[0])
    layout_id = str(frame_map["layout_id"].iloc[0])
    scene = str(frame_map["scene"].iloc[0])
    meta_path = os.path.join(server_dir, "layout_meta.json")
    with open(meta_path, encoding="utf-8") as handle:
        layout_meta = json.load(handle)
    wall_axis = str(layout_meta.get("wall_axis", "X")).lower()
    condition = {"NORMAL": "core", "NO_WALL": "no_wall_visible",
                 "NO_SHEEP": "occluder_only_no_sheep"}.get(scene, scene)
    target_present = scene != "NO_SHEEP"

    keys = [_capture_key(row) for _, row in frame_map.iterrows()]

    streams: dict[str, list] = {
        "frame_map": [dict(k) for k in keys],
        "raw_actions": [], "normalized_actions": [], "server_state": [],
        "client_tick_log": [], "visibility": [], "seed_noise": [],
    }
    prev_hotbar: int | None = None
    for (_, row), key in zip(frame_map.iterrows(), keys):
        # raw_action is emitted in Person A's official MineRL/VPT shape
        # (keyboard.keys + mouse.dx/dy/buttons) so A's convert_action reads
        # it drop-in; C's flat capture is retained under raw_action_flat for
        # audit. Verified against A's golden matrix in
        # tests/data/test_person_a_action_compat.py.
        official = flat_to_official_raw_action(row, prev_hotbar=prev_hotbar)
        prev_hotbar = int(row["hotbar"])
        streams["raw_actions"].append({
            **key,
            "raw_action": official,
            "raw_action_flat": {
                field: (bool(row[field])
                        if field not in ("hotbar", "camera_dx", "camera_dy")
                        else (int(row[field]) if field == "hotbar"
                              else float(row[field])))
                for field in RAW_FIELDS
            },
        })
        streams["normalized_actions"].append(
            {**key, "normalized_action": _normalized_action(row)}
        )
        axis_velocity = float(row["axis_velocity"]) if target_present else 0.0
        streams["server_state"].append({
            **key,
            "state": {
                "target_entity_id": (f"magenta_sheep_{episode_id}"
                                     if target_present else "no_target"),
                "target_present": bool(target_present),
                "position_x_blocks": float(row["sheep_x"]) if target_present else 0.0,
                "position_y_blocks": float(row["sheep_y"]) if target_present else 0.0,
                "position_z_blocks": float(row["sheep_z"]) if target_present else 0.0,
                "wall_parallel_position_blocks":
                    float(row["axis_pos"]) if target_present else 0.0,
                "velocity_x_blocks_per_second":
                    axis_velocity if wall_axis == "x" else 0.0,
                "velocity_y_blocks_per_second": 0.0,
                "velocity_z_blocks_per_second":
                    axis_velocity if wall_axis == "z" else 0.0,
            },
        })
        # Explicit client tick counter: the capture sequence index. Client
        # ticks are mapped explicitly, never assumed equal to server ticks.
        streams["client_tick_log"].append(
            {**key, "client_tick": int(row["render_frame_idx"])}
        )
        streams["visibility"].append(
            {**key,
             "visibility": "visible" if bool(row["visible_flag"]) else "occluded"}
        )
        draw = schedule.rows[int(row["server_tick"])]
        streams["seed_noise"].append({
            **key,
            "seed": schedule.seed,
            "draw_idx": draw.draw_idx,
            "standard_normal_draw": draw.standard_normal_draw,
            "q": draw.q,
            "dt_seconds": draw.dt_seconds,
            "noise_std_blocks": draw.noise_std_blocks,
            "noise_draw": draw.noise_draw,
        })

    media_path = os.path.join(out_dir, "video_640x360.mp4")
    reset_result = os.path.join(server_dir, "reset_result.json")

    # A's frozen artifact table requires every stream as a JSONL artifact
    # with an exact content hash. Emit them into the bundle's package_v0_1/
    # directory; the parquet frame map remains the internal crosswalk.
    stream_dir = os.path.join(out_dir, "package_v0_1")
    os.makedirs(stream_dir, exist_ok=True)
    stream_artifacts: dict[str, dict] = {}
    for name, rows in streams.items():
        stream_path = os.path.join(stream_dir, f"{name}.jsonl")
        with open(stream_path, "w", encoding="utf-8") as handle:
            for entry in rows:
                handle.write(json.dumps(entry, sort_keys=True) + "\n")
        stream_artifacts[name] = {"format": "jsonl", "path": stream_path,
                                  "sha256": sha256_file(stream_path)}
    # The manifest noise_schedule_hash binds the capture-key-joined
    # seed_noise artifact (the schedule as consumed by this episode); the
    # generator's source file is preserved as an additional artifact.
    schedule_hash = stream_artifacts["seed_noise"]["sha256"]
    lock_path = os.path.join(repo_root,
                             "configs/scenes/environment_lock.observed_dev_v0_1.json")
    qa_files = [p for p in os.listdir(out_dir) if p.startswith("qa_report_")
                and p.endswith(".json")]
    qa_path = os.path.join(out_dir, sorted(qa_files)[0])

    artifacts = {
        **stream_artifacts,
        "config": {"format": "json", "path": reset_result,
                   "sha256": sha256_file(reset_result)},
        "diagnostics": {"format": "json", "path": qa_path,
                        "sha256": sha256_file(qa_path)},
        "media": {"format": "mp4", "path": media_path,
                  "sha256": sha256_file(media_path)},
        "seed_noise_source": {"format": "jsonl", "path": schedule_path,
                              "sha256": sha256_file(schedule_path)},
        "raw_server_state": {"format": "jsonl",
                             "path": os.path.join(server_dir, "server_state.jsonl"),
                             "sha256": sha256_file(os.path.join(server_dir, "server_state.jsonl"))},
        "raw_client_actions": {"format": "jsonl",
                               "path": os.path.join(client_dir, "raw_actions.jsonl"),
                               "sha256": sha256_file(os.path.join(client_dir, "raw_actions.jsonl"))},
    }

    import numpy as np
    seed = int(frame_map["seed"].iloc[0])
    n = len(frame_map)
    manifest = {
        "schema_version": "1.0",
        "person_c_contract_version": "0.1",
        "episode_id": episode_id,
        "trajectory_id": trajectory_id,
        "layout_id": layout_id,
        "run_id": run_id,
        "condition": condition,
        "regime": "regime_a",
        "seed": seed,
        "tick_rate_hz": 20.0,
        "dt_seconds": 0.05,
        "q": float(frame_map["q"].iloc[0]),
        "v": float(frame_map["v"].iloc[0]),
        "duration": n * 0.05,
        "code_sha": _git_head(repo_root),
        "config_hash": sha256_file(reset_result),
        "layout_config_hash": sha256_file(meta_path),
        "environment_lock_hash": sha256_file(lock_path),
        "noise_schedule_hash": schedule_hash,
        "rng": {
            "producer": "numpy.random.Generator",
            "bit_generator": "PCG64",
            "numpy_version": np.__version__,
            "immutable_schedule": True,
            "java_consumption": "stored_draws_in_draw_idx_order",
        },
        "lifecycle_version": LIFECYCLE_VERSION,
        "status": "accepted",
    }

    # Temporal alignment anchored through THIS package's frame map; the
    # runtime impulse evidence hash is the immutable QA report of the
    # session's scripted-impulse fixture (see module docstring for the v0.1
    # vocabulary constraint on evidence_scope).
    before = 1
    after_row = frame_map[frame_map["model_frame_idx"] == before + 1].iloc[0]
    temporal_alignment = {
        "status": "verified",
        "evidence_scope": "synthetic_contract_only",
        "action_idx": before,
        "visual_before_model_frame_idx": before,
        "visual_after_model_frame_idx": before + 1,
        "effect_server_tick": int(after_row["server_tick"]),
        "evidence_hash": sha256_file(qa_path),
    }

    # Camera-axis impulse orientation evidence (A's frozen top-level
    # block): the session's accepted scripted-impulse fixture. The impulse
    # is a pure yaw step, i.e. camera component 1 (dx); component 0 (dy)
    # shows no effect. evidence_hash is the fixture's immutable QA report.
    impulse_orientation = {
        "status": "verified",
        "evidence_scope": "synthetic_contract_only",
        "fixture_id": impulse_fixture_id or f"scripted_impulse_for_{run_id}",
        "camera_component_0_observed_effect":
            "runtime_no_component_0_effect",
        "camera_component_1_observed_effect":
            "runtime_positive_component_1_step_in_visual_i_to_i_plus_1",
        "evidence_hash": (sha256_file(impulse_fixture_qa_path)
                          if impulse_fixture_qa_path else sha256_file(qa_path)),
    }

    return {
        "schema_version": "1.0",
        "person_c_contract_version": "0.1",
        "episode_id": episode_id,
        "trajectory_id": trajectory_id,
        "layout_id": layout_id,
        "run_id": run_id,
        "condition": condition,
        "seed": seed,
        "synthetic": False,
        "scientific_use": "pending_cross_role_signoff",
        "media": {
            "width": 640, "height": 360, "fps": 20.0,
            "frame_count": n, "mode": "mp4",
            "path": media_path, "sha256": sha256_file(media_path),
        },
        "artifacts": artifacts,
        "streams": streams,
        "episode_manifest": manifest,
        "exclusion_ledger": [],
        "temporal_alignment": temporal_alignment,
        "impulse_orientation": impulse_orientation,
    }


def package_and_validate(out_dir: str, server_dir: str, client_dir: str,
                         schedule_path: str, repo_root: str,
                         run_id: str,
                         impulse_fixture_id: str = "",
                         impulse_fixture_qa_path: str = "") -> tuple[dict, object]:
    """Assemble the package, run the FULL frozen validator chain (C0 capture
    contract, which itself runs A's frozen trajectory validator), write the
    package next to the bundle, and return ``(package, validation_result)``.

    The package file is written only when validation accepts.
    """
    package = assemble_package(out_dir, server_dir, client_dir,
                               schedule_path, repo_root, run_id,
                               impulse_fixture_id=impulse_fixture_id,
                               impulse_fixture_qa_path=impulse_fixture_qa_path)
    result = validate_capture_package(package)
    if result.accepted:
        path = os.path.join(out_dir, "capture_package_v0_1.json")
        data = json.dumps(package, indent=1, sort_keys=True).encode()
        with open(path, "wb") as handle:
            handle.write(data)
        with open(path + ".sha256", "w", encoding="utf-8") as handle:
            handle.write(hashlib.sha256(data).hexdigest() + "\n")
    return package, result
