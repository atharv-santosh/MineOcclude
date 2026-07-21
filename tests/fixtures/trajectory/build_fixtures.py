"""Build synthetic fixtures for the C→A trajectory contract.

These fixtures are structural test data only.
They are not scientific data and do not contain real MineWorld captures.
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path


OUTPUT_DIR = Path(__file__).parent

SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64
SHA_D = "d" * 64
SHA_E = "e" * 64
SHA_F = "f" * 64


def make_identity_row(
    *,
    server_tick: int,
    frame_idx: int,
) -> dict:
    """Create one shared synthetic capture identity row."""

    return {
        "episode_id": "synthetic_episode_0001",
        "trajectory_id": "synthetic_trajectory_0001",
        "server_tick": server_tick,
        "render_frame_idx": frame_idx,
        "action_idx": frame_idx,
        "model_frame_idx": frame_idx,
    }


def make_accepted_package() -> dict:
    """Create one structurally valid synthetic C→A package."""

    identities = [
        make_identity_row(
            server_tick=100,
            frame_idx=0,
        ),
        make_identity_row(
            server_tick=101,
            frame_idx=1,
        ),
        make_identity_row(
            server_tick=102,
            frame_idx=2,
        ),
    ]

    frame_map = [
        dict(row)
        for row in identities
    ]

    raw_actions = [
        {
            **row,
            "raw_action": {
                "camera": [0.0, 0.0],
                "forward": False,
                "back": False,
                "left": False,
                "right": False,
                "jump": False,
                "attack": False,
            },
        }
        for row in identities
    ]

    normalized_actions = [
        {
            **row,
            "normalized_action": {
                "camera_component_0": 0,
                "camera_component_1": 0,
                "hotbar": 0,
                "forward_back": 0,
                "left_right": 0,
                "sprint_sneak": 0,
                "use_attack": 0,
                "jump": 0,
                "drop_pick_item": 0,
            },
        }
        for row in identities
    ]

    server_state = [
        {
            **row,
            "state": {
                "synthetic_object_x": float(
                    row["model_frame_idx"]
                ),
                "synthetic_object_y": 0.0,
                "synthetic_object_z": 0.0,
            },
        }
        for row in identities
    ]

    client_tick_log = [
        {
            **row,
            "client_tick": 200
            + row["model_frame_idx"],
        }
        for row in identities
    ]

    visibility = [
        {
            **row,
            "visibility": (
                "visible"
                if row["model_frame_idx"] == 0
                else "occluded"
            ),
        }
        for row in identities
    ]

    seed_noise = [
        {
            **row,
            "seed": 42,
            "noise_draw": float(
                row["model_frame_idx"]
            )
            / 10.0,
        }
        for row in identities
    ]

    return {
        "schema_version": "0.1-draft",
        "episode_id": "synthetic_episode_0001",
        "trajectory_id": "synthetic_trajectory_0001",
        "seed": 42,

        "media": {
            "mode": "mp4",
            "path": "synthetic/scene.mp4",
            "width": 640,
            "height": 360,
            "fps": 20.0,
            "frame_count": 3,
            "sha256": SHA_A,
        },

        "artifacts": {
            "raw_actions": {
                "path": "synthetic/raw_actions.jsonl",
                "format": "jsonl",
                "sha256": SHA_B,
            },
            "normalized_actions": {
                "path": "synthetic/normalized_actions.jsonl",
                "format": "jsonl",
                "sha256": SHA_C,
            },
            "server_state": {
                "path": "synthetic/server_state.jsonl",
                "format": "jsonl",
                "sha256": SHA_D,
            },
            "client_tick_log": {
                "path": "synthetic/client_tick_log.jsonl",
                "format": "jsonl",
                "sha256": SHA_E,
            },
            "frame_map": {
                "path": "synthetic/frame_map.jsonl",
                "format": "jsonl",
                "sha256": SHA_F,
            },
            "visibility": {
                "path": "synthetic/visibility.jsonl",
                "format": "jsonl",
                "sha256": SHA_A,
            },
            "config": {
                "path": "synthetic/config.json",
                "format": "json",
                "sha256": SHA_B,
            },
            "seed_noise": {
                "path": "synthetic/seed_noise.jsonl",
                "format": "jsonl",
                "sha256": SHA_C,
            },
            "diagnostics": {
                "path": "synthetic/diagnostics.json",
                "format": "json",
                "sha256": SHA_D,
            },
        },

        "streams": {
            "frame_map": frame_map,
            "raw_actions": raw_actions,
            "normalized_actions": normalized_actions,
            "server_state": server_state,
            "client_tick_log": client_tick_log,
            "visibility": visibility,
            "seed_noise": seed_noise,
        },

        "impulse_orientation": {
            "status": "verified",
            "fixture_id": "synthetic_camera_impulse_001",
            "camera_component_0_observed_effect":
                "synthetic_axis_effect_0",
            "camera_component_1_observed_effect":
                "synthetic_axis_effect_1",
            "evidence_hash": SHA_E,
        },
    }


def write_fixture(
    filename: str,
    package: dict,
) -> None:
    """Write one fixture as formatted JSON."""

    path = OUTPUT_DIR / filename

    with path.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            package,
            file,
            indent=2,
            sort_keys=True,
        )

        file.write("\n")


def main() -> None:
    """Generate accepted and intentionally rejected fixtures."""

    accepted = make_accepted_package()

    # Valid package
    write_fixture(
        "accepted_package.json",
        accepted,
    )

    # Rejected: stream cardinality mismatch
    cardinality = deepcopy(
        accepted
    )

    cardinality[
        "streams"
    ][
        "raw_actions"
    ].pop()

    write_fixture(
        "rejected_cardinality.json",
        cardinality,
    )

    # Rejected: skipped authoritative server tick
    nonconsecutive = deepcopy(
        accepted
    )

    for stream in nonconsecutive[
        "streams"
    ].values():
        stream[2][
            "server_tick"
        ] = 103

    write_fixture(
        "rejected_nonconsecutive_tick.json",
        nonconsecutive,
    )

    # Rejected: duplicate capture identity
    duplicate = deepcopy(
        accepted
    )

    for stream in duplicate[
        "streams"
    ].values():
        stream[1] = deepcopy(
            stream[0]
        )

    write_fixture(
        "rejected_duplicate_identity.json",
        duplicate,
    )

    # Rejected: camera orientation not verified
    orientation = deepcopy(
        accepted
    )

    orientation[
        "impulse_orientation"
    ][
        "status"
    ] = "unverified"

    write_fixture(
        "rejected_impulse_orientation.json",
        orientation,
    )

    # Rejected: one stream has mismatched capture identity
    mismatched_stream = deepcopy(
        accepted
    )

    mismatched_stream[
        "streams"
    ][
        "raw_actions"
    ][
        1
    ][
        "render_frame_idx"
    ] = 999

    write_fixture(
        "rejected_mismatched_stream_identity.json",
        mismatched_stream,
    )

    # Rejected: invalid capture identity type
    invalid_identity_type = deepcopy(
        accepted
    )

    invalid_identity_type[
        "streams"
    ][
        "frame_map"
    ][
        1
    ][
        "server_tick"
    ] = "not-an-integer"

    write_fixture(
        "rejected_invalid_identity_type.json",
        invalid_identity_type,
    )

    # Rejected: malformed normalized-action payload
    invalid_payload = deepcopy(
        accepted
    )

    invalid_payload[
        "streams"
    ][
        "normalized_actions"
    ][
        1
    ][
        "normalized_action"
    ] = None

    write_fixture(
        "rejected_invalid_payload.json",
        invalid_payload,
    )

    # Rejected: malformed media field type
    malformed_media = deepcopy(
        accepted
    )

    malformed_media[
        "media"
    ][
        "mode"
    ] = []

    write_fixture(
        "rejected_malformed_media.json",
        malformed_media,
    )

    # Rejected: invalid authoritative state
    invalid_state = deepcopy(
        accepted
    )

    invalid_state[
        "streams"
    ][
        "server_state"
    ][
        1
    ][
        "state"
    ] = None

    write_fixture(
        "rejected_invalid_state.json",
        invalid_state,
    )

    # Rejected: invalid client tick
    invalid_client_tick = deepcopy(
        accepted
    )

    invalid_client_tick[
        "streams"
    ][
        "client_tick_log"
    ][
        1
    ][
        "client_tick"
    ] = "not-an-integer"

    write_fixture(
        "rejected_invalid_client_tick.json",
        invalid_client_tick,
    )

    print(
        "Generated Step 1.3 trajectory fixtures."
    )


if __name__ == "__main__":
    main()