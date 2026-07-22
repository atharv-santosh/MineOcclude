"""Build synthetic fixtures for the A→B activation contract.

These fixtures are structural test data only.
They are synthetic and must not be used for scientific claims.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path


OUTPUT_DIR = Path(__file__).parent

CODE_SHA = "0" * 40

CONFIG_HASH = "1" * 64
CHECKPOINT_HASH = "2" * 64
PREPROCESS_HASH = "3" * 64
MANIFEST_HASH = "5" * 64

SCHEMA_VERSION = "1.0"

TRAJECTORY_ID = "synthetic_trajectory_0001"
EPISODE_ID = "synthetic_episode_0001"

RUN_ID = "synthetic_activation_run_001"
HANDOFF_ID = "synthetic_activation_handoff_001"

HOOK_SITE = "residual_stream"

LAYERS = (
    5,
    12,
)

MODEL_FRAMES = (
    0,
    1,
    2,
)

VECTOR_SIZE = 2048

VISUAL_TOKENS_PER_FRAME = 336
TOKENS_PER_FRAME_ACTION_PAIR = 347


def visual_token_positions(
    model_frame_idx: int,
) -> list[int]:
    """Return the exact 336 visual-token positions for one model frame."""

    start = (
        model_frame_idx
        * TOKENS_PER_FRAME_ACTION_PAIR
    )

    return list(
        range(
            start,
            start + VISUAL_TOKENS_PER_FRAME,
        )
    )


def make_base_identity(
    model_frame_idx: int,
) -> dict:
    """Create the universal identity for one synthetic model frame."""

    visibility = (
        "visible"
        if model_frame_idx == 0
        else "occluded"
    )

    return {
        "episode_id": EPISODE_ID,
        "trajectory_id": TRAJECTORY_ID,
        "server_tick": 100 + model_frame_idx,
        "render_frame_idx": model_frame_idx,
        "action_idx": model_frame_idx,
        "model_frame_idx": model_frame_idx,

        "layout_id": "synthetic_layout_01",
        "regime": "synthetic_test",
        "visibility": visibility,
        "tau": model_frame_idx * 0.05,
        "v": 1.0,
        "q": 0.5,
        "duration": 3.0,

        "code_sha": CODE_SHA,
        "config_hash": CONFIG_HASH,
        "model_hash": CHECKPOINT_HASH,
        "preprocess_hash": PREPROCESS_HASH,
        "seed": 42,
        "schema_version": SCHEMA_VERSION,
        "run_id": RUN_ID,

        "status": "accepted",
        "exclusion_reason": None,
        "superseded_by": None,
    }


def make_activation_index_rows() -> list[dict]:
    """Create six activation-index rows: three frames × two layers."""

    rows = []

    chunk_row_idx = 0

    for layer_idx in LAYERS:
        for model_frame_idx in MODEL_FRAMES:
            row = {
                **make_base_identity(
                    model_frame_idx
                ),

                "activation_chunk_id":
                    "synthetic_activation_chunk_0001",

                "chunk_row_idx":
                    chunk_row_idx,

                "layer_idx":
                    layer_idx,

                "hook_site":
                    HOOK_SITE,

                "frame_token_positions":
                    visual_token_positions(
                        model_frame_idx
                    ),

                "token_region":
                    "visual",

                "pooling_method":
                    "mean",

                "dtype":
                    "float32",

                "vector_shape":
                    [VECTOR_SIZE],

                "checkpoint_hash":
                    CHECKPOINT_HASH,

                "accepted_manifest_hash":
                    MANIFEST_HASH,

                "run_status":
                    "completed",
            }

            rows.append(
                row
            )

            chunk_row_idx += 1

    return rows


def make_activation_chunk() -> dict:
    """Create synthetic activation vectors matching the chunk descriptor."""

    vectors = []

    for layer_idx in LAYERS:
        for model_frame_idx in MODEL_FRAMES:
            # The vectors have the realistic expected hidden dimension.
            # Their values are synthetic and intentionally simple.
            vector = [
                float(layer_idx),
                float(model_frame_idx),
            ] + [
                0.0
            ] * (
                VECTOR_SIZE - 2
            )

            vectors.append(
                {
                    "chunk_row_idx": len(
                        vectors
                    ),
                    "vector": vector,
                }
            )

    return {
        "chunk_id":
            "synthetic_activation_chunk_0001",

        "dtype":
            "float32",

        "vector_shape":
            [VECTOR_SIZE],

        "rows":
            vectors,
    }


def make_accepted_handoff() -> dict:
    """Create one structurally valid synthetic A→B activation handoff."""

    index_rows = make_activation_index_rows()

    chunk_hash = hashlib.sha256(
        serialize_json(
            make_activation_chunk()
        ).encode(
            "utf-8"
        )
    ).hexdigest()

    return {
        "schema_version":
            SCHEMA_VERSION,

        "handoff_id":
            HANDOFF_ID,

        "accepted_manifest_hash":
            MANIFEST_HASH,

        "checkpoint_hash":
            CHECKPOINT_HASH,

        "preprocess_hash":
            PREPROCESS_HASH,

        "run_id":
            RUN_ID,

        "run_status":
            "completed",

        "selection_policy": {
            "uses_target_labels":
                False,

            "uses_heldout_labels":
                False,

            "description":
                (
                    "Synthetic extraction selection is based only "
                    "on accepted input identity and configured layers."
                ),
        },

        "chunks": [
            {
                "chunk_id":
                    "synthetic_activation_chunk_0001",

                "path":
                    "synthetic_activation_chunk.json",

                "sha256":
                    chunk_hash,

                "row_count":
                    len(index_rows),

                "dtype":
                    "float32",

                "vector_shape":
                    [VECTOR_SIZE],
            }
        ],

        "index_rows":
            index_rows,

        "cardinality_report": {
            "accepted_manifest_rows":
                3,

            "expected_activation_rows":
                6,

            "actual_activation_rows":
                6,

            "expected_rows_by_layer": {
                "5": 3,
                "12": 3,
            },

            "actual_rows_by_layer": {
                "5": 3,
                "12": 3,
            },
        },
    }


def make_synthetic_targets() -> list[dict]:
    """Create a shuffled synthetic target table for Person B join tests."""

    targets = []

    for model_frame_idx in (
        2,
        0,
        1,
    ):
        targets.append(
            {
                "trajectory_id":
                    TRAJECTORY_ID,

                "model_frame_idx":
                    model_frame_idx,

                "synthetic_target_mean":
                    10.0
                    + model_frame_idx,

                "synthetic_target_uncertainty":
                    0.5
                    + (
                        model_frame_idx
                        * 0.1
                    ),
            }
        )

    return targets


def serialize_json(value) -> str:
    """Return the canonical on-disk JSON representation for fixtures."""

    return (
        json.dumps(
            value,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def write_json(
    filename: str,
    value,
) -> None:
    """Write one formatted JSON fixture."""

    path = (
        OUTPUT_DIR
        / filename
    )

    with path.open(
        "w",
        encoding="utf-8",
        newline="\n",
    ) as file:
        file.write(
            serialize_json(
                value
            )
        )


def main() -> None:
    """Generate valid and intentionally invalid Step 1.4 fixtures."""

    accepted = (
        make_accepted_handoff()
    )

    # --------------------------------------------------------------
    # Valid synthetic fixtures
    # --------------------------------------------------------------

    write_json(
        "accepted_activation_handoff.json",
        accepted,
    )

    write_json(
        "synthetic_activation_chunk.json",
        make_activation_chunk(),
    )

    write_json(
        "synthetic_targets.json",
        make_synthetic_targets(),
    )

    # --------------------------------------------------------------
    # Rejected: extraction policy uses target labels
    # --------------------------------------------------------------

    leakage = deepcopy(
        accepted
    )

    leakage[
        "selection_policy"
    ][
        "uses_target_labels"
    ] = True

    write_json(
        "rejected_label_leakage.json",
        leakage,
    )

    # --------------------------------------------------------------
    # Rejected: cardinality report does not match index rows
    # --------------------------------------------------------------

    cardinality = deepcopy(
        accepted
    )

    cardinality[
        "cardinality_report"
    ][
        "actual_activation_rows"
    ] = 5

    write_json(
        "rejected_cardinality.json",
        cardinality,
    )

    # --------------------------------------------------------------
    # Rejected: wrong visual-token positions
    # --------------------------------------------------------------

    invalid_token_positions = deepcopy(
        accepted
    )

    invalid_token_positions[
        "index_rows"
    ][
        0
    ][
        "frame_token_positions"
    ] = list(
        range(
            1,
            337,
        )
    )

    write_json(
        "rejected_token_positions.json",
        invalid_token_positions,
    )

    # --------------------------------------------------------------
    # Rejected: duplicate scientific activation identity
    # --------------------------------------------------------------

    duplicate_identity = deepcopy(
        accepted
    )

    first_row = (
        duplicate_identity[
            "index_rows"
        ][
            0
        ]
    )

    second_row = (
        duplicate_identity[
            "index_rows"
        ][
            1
        ]
    )

    second_row[
        "trajectory_id"
    ] = first_row[
        "trajectory_id"
    ]

    second_row[
        "model_frame_idx"
    ] = first_row[
        "model_frame_idx"
    ]

    second_row[
        "layer_idx"
    ] = first_row[
        "layer_idx"
    ]

    second_row[
        "hook_site"
    ] = first_row[
        "hook_site"
    ]

    second_row[
        "frame_token_positions"
    ] = list(
        first_row[
            "frame_token_positions"
        ]
    )

    write_json(
        "rejected_duplicate_activation_identity.json",
        duplicate_identity,
    )

    # --------------------------------------------------------------
    # Rejected: row provenance disagrees with package metadata
    # --------------------------------------------------------------

    metadata_mismatch = deepcopy(
        accepted
    )

    metadata_mismatch[
        "index_rows"
    ][
        0
    ][
        "checkpoint_hash"
    ] = "9" * 64

    write_json(
        "rejected_metadata_mismatch.json",
        metadata_mismatch,
    )

    print(
        "Generated Step 1.4 activation fixtures."
    )


if __name__ == "__main__":
    main()
