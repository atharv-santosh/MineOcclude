"""Build deterministic synthetic Person C C0 episode fixtures.

The fixtures exercise contract mechanics only. They are not real Minecraft
captures, screenshots, runtime evidence, or scientific data.
"""

from __future__ import annotations

import argparse
import json
from copy import deepcopy
from pathlib import Path


OUTPUT_DIR = Path(__file__).parent

EPISODE_ID = "synthetic_person_c_episode_0001"
TRAJECTORY_ID = "synthetic_person_c_trajectory_0001"
LAYOUT_ID = "synthetic_layout_pending_c1"
RUN_ID = "synthetic_person_c_capture_run_0001"
CONDITION = "synthetic_contract_test"
SEED = 20260721

SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64
SHA_D = "d" * 64
SHA_E = "e" * 64
SHA_F = "f" * 64
CODE_SHA = "0" * 40

FRAME_COUNT = 4
START_SERVER_TICK = 100
Q_BLOCKS2_PER_SECOND = 0.2
DT_SECONDS = 0.05
NOISE_STD_BLOCKS = 0.1
STANDARD_NORMAL_DRAWS = (-1.0, 0.5, 1.25, -0.75)


def identity(frame_idx: int) -> dict:
    """Return one shared explicit capture identity."""

    return {
        "episode_id": EPISODE_ID,
        "trajectory_id": TRAJECTORY_ID,
        "server_tick": START_SERVER_TICK + frame_idx,
        "render_frame_idx": frame_idx,
        "action_idx": frame_idx,
        "model_frame_idx": frame_idx,
    }


def shuffled(rows: list[dict], order: tuple[int, ...]) -> list[dict]:
    """Return deliberately reordered rows without changing identity."""

    return [deepcopy(rows[index]) for index in order]


def normalized_action(frame_idx: int) -> dict:
    """Return A's frozen normalized-action fields.

    The single synthetic impulse at action 1 proves alignment mechanics only;
    it does not establish real camera-axis meaning.
    """

    return {
        "camera_component_0": 1 if frame_idx == 1 else 0,
        "camera_component_1": 0,
        "hotbar": 0,
        "forward_back": 0,
        "left_right": 0,
        "sprint_sneak": 0,
        "use_attack": 0,
        "jump": 0,
        "drop_pick_item": 0,
    }


def make_accepted_episode() -> dict:
    """Create one valid four-tick synthetic Person C episode."""

    identities = [identity(index) for index in range(FRAME_COUNT)]

    frame_map = [dict(row) for row in identities]
    raw_actions = [
        {
            **row,
            "raw_action": {
                "synthetic_action_code": (
                    "camera_impulse" if row["action_idx"] == 1 else "no_op"
                ),
                "source_vocabulary": "UNRESOLVED_A_C_RAW_ACTION_VOCABULARY",
            },
        }
        for row in identities
    ]
    normalized_actions = [
        {
            **row,
            "normalized_action": normalized_action(row["action_idx"]),
        }
        for row in identities
    ]
    server_state = [
        {
            **row,
            "state": {
                "target_entity_id": "synthetic_target_0001",
                "target_present": True,
                "position_x_blocks": 10.0 + 0.05 * row["model_frame_idx"],
                "position_y_blocks": 64.0,
                "position_z_blocks": 5.0,
                "wall_parallel_position_blocks": (
                    10.0 + 0.05 * row["model_frame_idx"]
                ),
                "velocity_x_blocks_per_second": 1.0,
                "velocity_y_blocks_per_second": 0.0,
                "velocity_z_blocks_per_second": 0.0,
            },
        }
        for row in identities
    ]
    client_tick_log = [
        {
            **row,
            "client_tick": 500 + row["model_frame_idx"],
        }
        for row in identities
    ]
    visibility = [
        {
            **row,
            "visibility": (
                "visible" if row["model_frame_idx"] == 0 else "occluded"
            ),
        }
        for row in identities
    ]
    seed_noise = [
        {
            **row,
            "seed": SEED,
            "draw_idx": row["model_frame_idx"],
            "standard_normal_draw": STANDARD_NORMAL_DRAWS[
                row["model_frame_idx"]
            ],
            "q": Q_BLOCKS2_PER_SECOND,
            "dt_seconds": DT_SECONDS,
            "noise_std_blocks": NOISE_STD_BLOCKS,
            "noise_draw": STANDARD_NORMAL_DRAWS[row["model_frame_idx"]]
            * NOISE_STD_BLOCKS,
        }
        for row in identities
    ]

    artifacts = {
        "raw_actions": {
            "path": "synthetic/person_c/raw_actions.jsonl",
            "format": "jsonl",
            "sha256": SHA_A,
        },
        "normalized_actions": {
            "path": "synthetic/person_c/normalized_actions.jsonl",
            "format": "jsonl",
            "sha256": SHA_B,
        },
        "server_state": {
            "path": "synthetic/person_c/server_state.jsonl",
            "format": "jsonl",
            "sha256": SHA_C,
        },
        "client_tick_log": {
            "path": "synthetic/person_c/client_tick_log.jsonl",
            "format": "jsonl",
            "sha256": SHA_D,
        },
        "frame_map": {
            "path": "synthetic/person_c/frame_map.jsonl",
            "format": "jsonl",
            "sha256": SHA_E,
        },
        "visibility": {
            "path": "synthetic/person_c/visibility.jsonl",
            "format": "jsonl",
            "sha256": SHA_F,
        },
        "config": {
            "path": "synthetic/person_c/config.json",
            "format": "json",
            "sha256": SHA_A,
        },
        "seed_noise": {
            "path": "synthetic/person_c/seed_noise.jsonl",
            "format": "jsonl",
            "sha256": SHA_B,
        },
        "diagnostics": {
            "path": "synthetic/person_c/diagnostics.json",
            "format": "json",
            "sha256": SHA_C,
        },
    }

    return {
        "schema_version": "1.0",
        "person_c_contract_version": "0.1",
        "episode_id": EPISODE_ID,
        "trajectory_id": TRAJECTORY_ID,
        "layout_id": LAYOUT_ID,
        "run_id": RUN_ID,
        "condition": CONDITION,
        "seed": SEED,
        "synthetic": True,
        "scientific_use": "forbidden",
        "media": {
            "mode": "mp4",
            "path": "synthetic/person_c/scene.mp4",
            "width": 640,
            "height": 360,
            "fps": 20.0,
            "frame_count": FRAME_COUNT,
            "sha256": SHA_D,
        },
        "artifacts": artifacts,
        "streams": {
            "frame_map": shuffled(frame_map, (2, 0, 3, 1)),
            "raw_actions": shuffled(raw_actions, (1, 3, 0, 2)),
            "normalized_actions": shuffled(normalized_actions, (3, 0, 2, 1)),
            "server_state": shuffled(server_state, (0, 3, 1, 2)),
            "client_tick_log": shuffled(client_tick_log, (2, 1, 3, 0)),
            "visibility": shuffled(visibility, (3, 2, 0, 1)),
            "seed_noise": shuffled(seed_noise, (1, 0, 3, 2)),
        },
        "impulse_orientation": {
            "status": "verified",
            "fixture_id": "synthetic_person_c_camera_impulse_0001",
            "camera_component_0_observed_effect": (
                "synthetic_positive_component_0_only"
            ),
            "camera_component_1_observed_effect": (
                "synthetic_no_component_1_effect"
            ),
            "evidence_hash": SHA_E,
            "evidence_scope": "synthetic_contract_only",
        },
        "temporal_alignment": {
            "status": "verified",
            "evidence_scope": "synthetic_contract_only",
            "action_idx": 1,
            "visual_before_model_frame_idx": 1,
            "visual_after_model_frame_idx": 2,
            "effect_server_tick": 102,
            "evidence_hash": SHA_F,
        },
        "episode_manifest": {
            "schema_version": "1.0",
            "person_c_contract_version": "0.1",
            "episode_id": EPISODE_ID,
            "trajectory_id": TRAJECTORY_ID,
            "layout_id": LAYOUT_ID,
            "run_id": RUN_ID,
            "condition": CONDITION,
            "regime": "synthetic_contract_test",
            "seed": SEED,
            "tick_rate_hz": 20.0,
            "dt_seconds": DT_SECONDS,
            "q": Q_BLOCKS2_PER_SECOND,
            "v": 1.0,
            "duration": 0.2,
            "code_sha": CODE_SHA,
            "config_hash": SHA_A,
            "layout_config_hash": SHA_C,
            "environment_lock_hash": SHA_D,
            "noise_schedule_hash": artifacts["seed_noise"]["sha256"],
            "rng": {
                "producer": "numpy.random.Generator",
                "bit_generator": "PCG64",
                "numpy_version": "PIN_REQUIRED_BEFORE_RUNTIME",
                "immutable_schedule": True,
                "java_consumption": "stored_draws_in_draw_idx_order",
            },
            "lifecycle_version": "person-c-tick-lifecycle-v0.1",
            "status": "accepted",
        },
        "exclusion_ledger": [],
    }


def row_for_model_idx(rows: list[dict], model_frame_idx: int) -> dict:
    """Resolve one row explicitly without relying on physical row order."""

    matches = [
        row
        for row in rows
        if row["model_frame_idx"] == model_frame_idx
    ]
    if len(matches) != 1:
        raise ValueError("Fixture source no longer has one explicit model key.")
    return matches[0]


def make_fixtures() -> dict[str, dict]:
    """Return the valid fixture and nine isolated corruptions."""

    accepted = make_accepted_episode()
    fixtures = {"accepted_episode.json": accepted}

    missing_action = deepcopy(accepted)
    rows = missing_action["streams"]["normalized_actions"]
    rows.remove(row_for_model_idx(rows, 2))
    fixtures["rejected_missing_action.json"] = missing_action

    missing_frame = deepcopy(accepted)
    rows = missing_frame["streams"]["frame_map"]
    rows.remove(row_for_model_idx(rows, 2))
    fixtures["rejected_missing_frame.json"] = missing_frame

    duplicate_frame = deepcopy(accepted)
    for rows in duplicate_frame["streams"].values():
        row_for_model_idx(rows, 2)["render_frame_idx"] = 1
    fixtures["rejected_duplicate_frame.json"] = duplicate_frame

    duplicate_state = deepcopy(accepted)
    rows = duplicate_state["streams"]["server_state"]
    replacement_index = rows.index(row_for_model_idx(rows, 2))
    rows[replacement_index] = deepcopy(row_for_model_idx(rows, 1))
    fixtures["rejected_duplicate_state.json"] = duplicate_state

    skipped_tick = deepcopy(accepted)
    for rows in skipped_tick["streams"].values():
        row_for_model_idx(rows, 3)["server_tick"] = 104
    fixtures["rejected_skipped_tick.json"] = skipped_tick

    mixed_episode = deepcopy(accepted)
    row_for_model_idx(
        mixed_episode["streams"]["visibility"],
        2,
    )["episode_id"] = "synthetic_wrong_episode"
    fixtures["rejected_mixed_episode_id.json"] = mixed_episode

    non_monotonic = deepcopy(accepted)
    for rows in non_monotonic["streams"].values():
        first = row_for_model_idx(rows, 1)
        second = row_for_model_idx(rows, 2)
        first["render_frame_idx"], second["render_frame_idx"] = (
            second["render_frame_idx"],
            first["render_frame_idx"],
        )
    fixtures["rejected_non_monotonic_index.json"] = non_monotonic

    shifted_action = deepcopy(accepted)
    rows = shifted_action["streams"]["normalized_actions"]
    first = row_for_model_idx(rows, 1)
    second = row_for_model_idx(rows, 2)
    first["action_idx"], second["action_idx"] = (
        second["action_idx"],
        first["action_idx"],
    )
    fixtures["rejected_shifted_action.json"] = shifted_action

    invalid_media = deepcopy(accepted)
    invalid_media["media"]["width"] = 641
    fixtures["rejected_invalid_media_metadata.json"] = invalid_media

    return fixtures


def rendered(document: dict) -> str:
    """Return the canonical checked fixture representation."""

    return json.dumps(document, indent=2, sort_keys=True) + "\n"


def write_fixtures(fixtures: dict[str, dict]) -> None:
    """Write generated fixture files."""

    for filename, document in fixtures.items():
        (OUTPUT_DIR / filename).write_text(
            rendered(document),
            encoding="utf-8",
            newline="\n",
        )


def check_fixtures(fixtures: dict[str, dict]) -> None:
    """Fail if checked fixtures differ from deterministic generation."""

    stale: list[str] = []
    for filename, document in fixtures.items():
        path = OUTPUT_DIR / filename
        if not path.exists() or path.read_text(encoding="utf-8") != rendered(document):
            stale.append(filename)
    if stale:
        raise SystemExit("Fixture drift: " + ", ".join(stale))


def main() -> None:
    """Generate or check the C0 fixture set."""

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check committed fixtures without writing them.",
    )
    args = parser.parse_args()
    fixtures = make_fixtures()
    if args.check:
        check_fixtures(fixtures)
        print("Person C C0 fixtures are current.")
    else:
        write_fixtures(fixtures)
        print("Generated Person C C0 fixtures.")


if __name__ == "__main__":
    main()
