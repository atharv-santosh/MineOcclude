"""C→A trajectory package contract for MineOcclude.

This module validates whether a Person C capture package is structurally
acceptable for Person A processing.

Validation is strict. The validator never repairs, interpolates, reorders,
duplicates, drops, or otherwise modifies capture data.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any

from mineocclude.contracts.identity import SCHEMA_VERSION


TRAJECTORY_SCHEMA_VERSION = SCHEMA_VERSION

EXPECTED_WIDTH = 640
EXPECTED_HEIGHT = 360
EXPECTED_FPS = 20.0


CAPTURE_KEY = (
    "episode_id",
    "trajectory_id",
    "server_tick",
    "render_frame_idx",
    "action_idx",
    "model_frame_idx",
)


INDEX_FIELDS = (
    "server_tick",
    "render_frame_idx",
    "action_idx",
    "model_frame_idx",
)


ROW_STREAMS = (
    "frame_map",
    "raw_actions",
    "normalized_actions",
    "server_state",
    "client_tick_log",
    "visibility",
    "seed_noise",
)


EXPECTED_ARTIFACT_FORMATS = {
    "raw_actions": "jsonl",
    "normalized_actions": "jsonl",
    "server_state": "jsonl",
    "client_tick_log": "jsonl",
    "frame_map": "jsonl",
    "visibility": "jsonl",
    "config": "json",
    "seed_noise": "jsonl",
    "diagnostics": "json",
}


NORMALIZED_ACTION_FIELDS = (
    "camera_component_0",
    "camera_component_1",
    "hotbar",
    "forward_back",
    "left_right",
    "sprint_sneak",
    "use_attack",
    "jump",
    "drop_pick_item",
)


class RejectionCode(str, Enum):
    """Machine-readable C→A trajectory rejection reasons."""

    MISSING_REQUIRED_FIELD = "missing_required_field"
    INVALID_SCHEMA_VERSION = "invalid_schema_version"

    INVALID_MEDIA_SPEC = "invalid_media_spec"

    MISSING_ARTIFACT = "missing_artifact"
    INVALID_ARTIFACT_DESCRIPTOR = "invalid_artifact_descriptor"
    INVALID_HASH = "invalid_hash"

    MISSING_STREAM = "missing_stream"

    INVALID_IDENTITY_TYPE = "invalid_identity_type"
    INVALID_ROW_PAYLOAD = "invalid_row_payload"

    CARDINALITY_MISMATCH = "cardinality_mismatch"
    DUPLICATE_IDENTITY = "duplicate_identity"
    IDENTITY_MISMATCH = "identity_mismatch"
    NON_CONSECUTIVE_SERVER_TICKS = "non_consecutive_server_ticks"

    IMPULSE_ORIENTATION_UNVERIFIED = (
        "impulse_orientation_unverified"
    )

    IMPULSE_ORIENTATION_INCOMPLETE = (
        "impulse_orientation_incomplete"
    )


@dataclass(frozen=True)
class Rejection:
    """One machine-readable reason a package was rejected."""

    code: RejectionCode
    message: str


@dataclass(frozen=True)
class TrajectoryValidationResult:
    """Result returned by the trajectory validator."""

    accepted: bool
    rejections: tuple[Rejection, ...]


def _is_sha256(value: Any) -> bool:
    """Return True for a 64-character hexadecimal SHA-256 value."""

    if not isinstance(value, str):
        return False

    if len(value) != 64:
        return False

    try:
        int(value, 16)
    except ValueError:
        return False

    return True


def _is_non_negative_integer(value: Any) -> bool:
    """Return True for an integer greater than or equal to zero."""

    return (
        isinstance(value, int)
        and not isinstance(value, bool)
        and value >= 0
    )


def _is_finite_number(value: Any) -> bool:
    """Return True for a finite int or float that is not a boolean."""

    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _add_rejection(
    rejections: list[Rejection],
    code: RejectionCode,
    message: str,
) -> None:
    """Append one rejection without modifying the input package."""

    rejections.append(
        Rejection(
            code=code,
            message=message,
        )
    )


def _missing_fields(
    value: Mapping[str, Any],
    required_fields: tuple[str, ...],
) -> list[str]:
    """Return required fields absent from a mapping."""

    return [
        field
        for field in required_fields
        if field not in value
    ]


def _capture_identity_is_valid(
    row: Mapping[str, Any],
) -> bool:
    """Return True when all capture identity fields have valid types."""

    for field in (
        "episode_id",
        "trajectory_id",
    ):
        value = row.get(field)

        if (
            not isinstance(value, str)
            or not value.strip()
        ):
            return False

    for field in INDEX_FIELDS:
        if not _is_non_negative_integer(
            row.get(field)
        ):
            return False

    return True


def _get_capture_key(
    row: Mapping[str, Any],
) -> tuple[Any, ...] | None:
    """Return the capture key only when identity is complete and valid."""

    if not _capture_identity_is_valid(
        row
    ):
        return None

    return tuple(
        row[field]
        for field in CAPTURE_KEY
    )


def _validate_stream_payload(
    stream_name: str,
    row: Mapping[str, Any],
    row_index: int,
    rejections: list[Rejection],
) -> None:
    """Validate one stream-specific row payload."""

    prefix = (
        f"{stream_name}[{row_index}]"
    )

    if stream_name == "frame_map":
        return

    if stream_name == "raw_actions":
        raw_action = row.get(
            "raw_action"
        )

        if (
            not isinstance(raw_action, Mapping)
            or not raw_action
        ):
            _add_rejection(
                rejections,
                RejectionCode.INVALID_ROW_PAYLOAD,
                (
                    f"{prefix}.raw_action must be "
                    "a non-empty mapping."
                ),
            )

    elif stream_name == "normalized_actions":
        normalized_action = row.get(
            "normalized_action"
        )

        if not isinstance(
            normalized_action,
            Mapping,
        ):
            _add_rejection(
                rejections,
                RejectionCode.INVALID_ROW_PAYLOAD,
                (
                    f"{prefix}.normalized_action "
                    "must be a mapping."
                ),
            )

            return

        missing = _missing_fields(
            normalized_action,
            NORMALIZED_ACTION_FIELDS,
        )

        if missing:
            _add_rejection(
                rejections,
                RejectionCode.INVALID_ROW_PAYLOAD,
                (
                    f"{prefix}.normalized_action "
                    "is missing fields: "
                    + ", ".join(missing)
                ),
            )

        for field in NORMALIZED_ACTION_FIELDS:
            if field not in normalized_action:
                continue

            value = normalized_action[
                field
            ]

            if (
                not isinstance(value, int)
                or isinstance(value, bool)
            ):
                _add_rejection(
                    rejections,
                    RejectionCode.INVALID_ROW_PAYLOAD,
                    (
                        f"{prefix}.normalized_action."
                        f"{field} must be an integer."
                    ),
                )

    elif stream_name == "server_state":
        state = row.get(
            "state"
        )

        if (
            not isinstance(state, Mapping)
            or not state
        ):
            _add_rejection(
                rejections,
                RejectionCode.INVALID_ROW_PAYLOAD,
                (
                    f"{prefix}.state must be "
                    "a non-empty mapping."
                ),
            )

    elif stream_name == "client_tick_log":
        client_tick = row.get(
            "client_tick"
        )

        if not _is_non_negative_integer(
            client_tick
        ):
            _add_rejection(
                rejections,
                RejectionCode.INVALID_ROW_PAYLOAD,
                (
                    f"{prefix}.client_tick must be "
                    "a non-negative integer."
                ),
            )

    elif stream_name == "visibility":
        visibility = row.get(
            "visibility"
        )

        if (
            not isinstance(visibility, str)
            or not visibility.strip()
        ):
            _add_rejection(
                rejections,
                RejectionCode.INVALID_ROW_PAYLOAD,
                (
                    f"{prefix}.visibility must be "
                    "a non-empty string."
                ),
            )

    elif stream_name == "seed_noise":
        seed = row.get(
            "seed"
        )

        noise_draw = row.get(
            "noise_draw"
        )

        if (
            not isinstance(seed, int)
            or isinstance(seed, bool)
        ):
            _add_rejection(
                rejections,
                RejectionCode.INVALID_ROW_PAYLOAD,
                (
                    f"{prefix}.seed must be an integer."
                ),
            )

        if not _is_finite_number(
            noise_draw
        ):
            _add_rejection(
                rejections,
                RejectionCode.INVALID_ROW_PAYLOAD,
                (
                    f"{prefix}.noise_draw must be "
                    "a finite numeric value."
                ),
            )


def validate_trajectory_package(
    package: Mapping[str, Any],
) -> TrajectoryValidationResult:
    """Validate one Person C → Person A trajectory package.

    All malformed input must be represented through rejection records.
    The validator must never repair or mutate the submitted package.
    """

    rejections: list[Rejection] = []

    # --------------------------------------------------------------
    # Top-level package structure
    # --------------------------------------------------------------

    if not isinstance(
        package,
        Mapping,
    ):
        _add_rejection(
            rejections,
            RejectionCode.MISSING_REQUIRED_FIELD,
            "Trajectory package must be a mapping.",
        )

        return TrajectoryValidationResult(
            accepted=False,
            rejections=tuple(rejections),
        )

    required_top_level = (
        "schema_version",
        "episode_id",
        "trajectory_id",
        "seed",
        "media",
        "artifacts",
        "streams",
        "impulse_orientation",
    )

    missing = _missing_fields(
        package,
        required_top_level,
    )

    if missing:
        _add_rejection(
            rejections,
            RejectionCode.MISSING_REQUIRED_FIELD,
            "Missing top-level fields: "
            + ", ".join(missing),
        )

        return TrajectoryValidationResult(
            accepted=False,
            rejections=tuple(rejections),
        )

    # --------------------------------------------------------------
    # Schema and package identity
    # --------------------------------------------------------------

    if (
        package["schema_version"]
        != TRAJECTORY_SCHEMA_VERSION
    ):
        _add_rejection(
            rejections,
            RejectionCode.INVALID_SCHEMA_VERSION,
            (
                "Expected trajectory schema version "
                f"{TRAJECTORY_SCHEMA_VERSION!r}."
            ),
        )

    for field in (
        "episode_id",
        "trajectory_id",
    ):
        value = package[
            field
        ]

        if (
            not isinstance(value, str)
            or not value.strip()
        ):
            _add_rejection(
                rejections,
                RejectionCode.INVALID_IDENTITY_TYPE,
                (
                    f"{field} must be "
                    "a non-empty string."
                ),
            )

    if (
        not isinstance(package["seed"], int)
        or isinstance(package["seed"], bool)
    ):
        _add_rejection(
            rejections,
            RejectionCode.INVALID_IDENTITY_TYPE,
            "seed must be an integer.",
        )

    # --------------------------------------------------------------
    # Media contract
    # --------------------------------------------------------------

    media = package[
        "media"
    ]

    media_required = (
        "mode",
        "path",
        "width",
        "height",
        "fps",
        "frame_count",
        "sha256",
    )

    if not isinstance(
        media,
        Mapping,
    ):
        _add_rejection(
            rejections,
            RejectionCode.INVALID_MEDIA_SPEC,
            "media must be a mapping.",
        )

        media = {}

    media_missing = _missing_fields(
        media,
        media_required,
    )

    if media_missing:
        _add_rejection(
            rejections,
            RejectionCode.INVALID_MEDIA_SPEC,
            "Missing media fields: "
            + ", ".join(media_missing),
        )

    else:
        mode = media[
            "mode"
        ]

        if (
            not isinstance(mode, str)
            or mode not in {
                "mp4",
                "numbered_frames",
            }
        ):
            _add_rejection(
                rejections,
                RejectionCode.INVALID_MEDIA_SPEC,
                (
                    "media.mode must be either "
                    "'mp4' or 'numbered_frames'."
                ),
            )

        path = media[
            "path"
        ]

        if (
            not isinstance(path, str)
            or not path.strip()
        ):
            _add_rejection(
                rejections,
                RejectionCode.INVALID_MEDIA_SPEC,
                (
                    "media.path must be "
                    "a non-empty string."
                ),
            )

        elif (
            mode == "mp4"
            and not path.lower().endswith(
                ".mp4"
            )
        ):
            _add_rejection(
                rejections,
                RejectionCode.INVALID_MEDIA_SPEC,
                (
                    "MP4 capture path "
                    "must end with .mp4."
                ),
            )

        width = media[
            "width"
        ]

        height = media[
            "height"
        ]

        if (
            not _is_non_negative_integer(width)
            or not _is_non_negative_integer(height)
            or width != EXPECTED_WIDTH
            or height != EXPECTED_HEIGHT
        ):
            _add_rejection(
                rejections,
                RejectionCode.INVALID_MEDIA_SPEC,
                (
                    "Capture resolution must "
                    "be exactly 640x360."
                ),
            )

        fps = media[
            "fps"
        ]

        if (
            not _is_finite_number(fps)
            or float(fps) != EXPECTED_FPS
        ):
            _add_rejection(
                rejections,
                RejectionCode.INVALID_MEDIA_SPEC,
                (
                    "Capture rate must "
                    "be exactly 20 Hz."
                ),
            )

        frame_count = media[
            "frame_count"
        ]

        if (
            not _is_non_negative_integer(
                frame_count
            )
            or frame_count == 0
        ):
            _add_rejection(
                rejections,
                RejectionCode.INVALID_MEDIA_SPEC,
                (
                    "media.frame_count must "
                    "be a positive integer."
                ),
            )

        if not _is_sha256(
            media["sha256"]
        ):
            _add_rejection(
                rejections,
                RejectionCode.INVALID_HASH,
                (
                    "media.sha256 must be "
                    "a valid SHA-256 value."
                ),
            )

    # --------------------------------------------------------------
    # Required artifact descriptors
    # --------------------------------------------------------------

    artifacts = package[
        "artifacts"
    ]

    if not isinstance(
        artifacts,
        Mapping,
    ):
        _add_rejection(
            rejections,
            RejectionCode.MISSING_ARTIFACT,
            "artifacts must be a mapping.",
        )

        artifacts = {}

    for (
        artifact_name,
        expected_format,
    ) in EXPECTED_ARTIFACT_FORMATS.items():

        if artifact_name not in artifacts:
            _add_rejection(
                rejections,
                RejectionCode.MISSING_ARTIFACT,
                (
                    "Missing required artifact: "
                    f"{artifact_name}."
                ),
            )

            continue

        descriptor = artifacts[
            artifact_name
        ]

        if not isinstance(
            descriptor,
            Mapping,
        ):
            _add_rejection(
                rejections,
                RejectionCode.INVALID_ARTIFACT_DESCRIPTOR,
                (
                    f"Artifact {artifact_name!r} "
                    "must use a mapping descriptor."
                ),
            )

            continue

        descriptor_missing = _missing_fields(
            descriptor,
            (
                "path",
                "format",
                "sha256",
            ),
        )

        if descriptor_missing:
            _add_rejection(
                rejections,
                RejectionCode.INVALID_ARTIFACT_DESCRIPTOR,
                (
                    f"Artifact {artifact_name!r} "
                    "is missing: "
                    + ", ".join(
                        descriptor_missing
                    )
                ),
            )

            continue

        artifact_path = descriptor[
            "path"
        ]

        if (
            not isinstance(
                artifact_path,
                str,
            )
            or not artifact_path.strip()
        ):
            _add_rejection(
                rejections,
                RejectionCode.INVALID_ARTIFACT_DESCRIPTOR,
                (
                    f"Artifact {artifact_name!r} "
                    "requires a non-empty path."
                ),
            )

        if (
            descriptor[
                "format"
            ]
            != expected_format
        ):
            _add_rejection(
                rejections,
                RejectionCode.INVALID_ARTIFACT_DESCRIPTOR,
                (
                    f"Artifact {artifact_name!r} "
                    f"must use format "
                    f"{expected_format!r}."
                ),
            )

        if not _is_sha256(
            descriptor[
                "sha256"
            ]
        ):
            _add_rejection(
                rejections,
                RejectionCode.INVALID_HASH,
                (
                    f"Artifact {artifact_name!r} "
                    "has an invalid SHA-256 value."
                ),
            )

    # --------------------------------------------------------------
    # Required row streams
    # --------------------------------------------------------------

    streams = package[
        "streams"
    ]

    if not isinstance(
        streams,
        Mapping,
    ):
        _add_rejection(
            rejections,
            RejectionCode.MISSING_STREAM,
            "streams must be a mapping.",
        )

        streams = {}

    valid_streams: dict[
        str,
        list[Mapping[str, Any]],
    ] = {}

    frame_count = media.get(
        "frame_count"
    )

    frame_count_is_valid = (
        _is_non_negative_integer(
            frame_count
        )
        and frame_count > 0
    )

    for stream_name in ROW_STREAMS:

        if stream_name not in streams:
            _add_rejection(
                rejections,
                RejectionCode.MISSING_STREAM,
                (
                    "Missing required stream: "
                    f"{stream_name}."
                ),
            )

            continue

        rows = streams[
            stream_name
        ]

        if not isinstance(
            rows,
            list,
        ):
            _add_rejection(
                rejections,
                RejectionCode.MISSING_STREAM,
                (
                    f"Stream {stream_name!r} "
                    "must be a list."
                ),
            )

            continue

        valid_streams[
            stream_name
        ] = rows

        if (
            frame_count_is_valid
            and len(rows) != frame_count
        ):
            _add_rejection(
                rejections,
                RejectionCode.CARDINALITY_MISMATCH,
                (
                    f"Stream {stream_name!r} "
                    f"has {len(rows)} rows but "
                    "media.frame_count is "
                    f"{frame_count}."
                ),
            )

        for row_index, row in enumerate(
            rows
        ):
            if not isinstance(
                row,
                Mapping,
            ):
                _add_rejection(
                    rejections,
                    RejectionCode.INVALID_ROW_PAYLOAD,
                    (
                        f"{stream_name}[{row_index}] "
                        "must be a mapping."
                    ),
                )

                continue

            missing_identity = _missing_fields(
                row,
                CAPTURE_KEY,
            )

            if missing_identity:
                _add_rejection(
                    rejections,
                    RejectionCode.MISSING_REQUIRED_FIELD,
                    (
                        f"{stream_name}[{row_index}] "
                        "is missing identity fields: "
                        + ", ".join(
                            missing_identity
                        )
                    ),
                )

            elif not _capture_identity_is_valid(
                row
            ):
                _add_rejection(
                    rejections,
                    RejectionCode.INVALID_IDENTITY_TYPE,
                    (
                        f"{stream_name}[{row_index}] "
                        "contains invalid capture "
                        "identity types."
                    ),
                )

            if (
                row.get("episode_id")
                != package["episode_id"]
                or row.get("trajectory_id")
                != package["trajectory_id"]
            ):
                _add_rejection(
                    rejections,
                    RejectionCode.IDENTITY_MISMATCH,
                    (
                        f"{stream_name}[{row_index}] "
                        "does not match the package "
                        "episode/trajectory identity."
                    ),
                )

            _validate_stream_payload(
                stream_name,
                row,
                row_index,
                rejections,
            )

    # --------------------------------------------------------------
    # One-to-one identity and uniqueness
    # --------------------------------------------------------------

    if "frame_map" in valid_streams:
        frame_map = valid_streams[
            "frame_map"
        ]

        reference_keys = [
            key
            for row in frame_map
            if isinstance(
                row,
                Mapping,
            )
            for key in [
                _get_capture_key(
                    row
                )
            ]
            if key is not None
        ]

        if len(
            reference_keys
        ) != len(
            set(reference_keys)
        ):
            _add_rejection(
                rejections,
                RejectionCode.DUPLICATE_IDENTITY,
                (
                    "frame_map contains duplicate "
                    "capture identities."
                ),
            )

        reference_key_set = set(
            reference_keys
        )

        # These indexes must each uniquely identify one row
        # within a trajectory.
        for field in INDEX_FIELDS:
            values = [
                row[field]
                for row in frame_map
                if (
                    isinstance(
                        row,
                        Mapping,
                    )
                    and _capture_identity_is_valid(
                        row
                    )
                )
            ]

            if len(values) != len(
                set(values)
            ):
                _add_rejection(
                    rejections,
                    RejectionCode.DUPLICATE_IDENTITY,
                    (
                        "frame_map contains "
                        f"duplicate {field} values."
                    ),
                )

        for (
            stream_name,
            rows,
        ) in valid_streams.items():

            usable_keys = [
                key
                for row in rows
                if isinstance(
                    row,
                    Mapping,
                )
                for key in [
                    _get_capture_key(
                        row
                    )
                ]
                if key is not None
            ]

            if len(
                usable_keys
            ) != len(
                set(usable_keys)
            ):
                _add_rejection(
                    rejections,
                    RejectionCode.DUPLICATE_IDENTITY,
                    (
                        f"Stream {stream_name!r} "
                        "contains duplicate "
                        "capture identities."
                    ),
                )

            if set(
                usable_keys
            ) != reference_key_set:
                _add_rejection(
                    rejections,
                    RejectionCode.IDENTITY_MISMATCH,
                    (
                        f"Stream {stream_name!r} "
                        "does not match frame_map "
                        "identities."
                    ),
                )

        # Only valid integer identities participate
        # in consecutive-tick arithmetic.
        ordered_frame_map = sorted(
            (
                row
                for row in frame_map
                if (
                    isinstance(
                        row,
                        Mapping,
                    )
                    and _capture_identity_is_valid(
                        row
                    )
                )
            ),
            key=lambda row: row[
                "model_frame_idx"
            ],
        )

        server_ticks = [
            row[
                "server_tick"
            ]
            for row in ordered_frame_map
        ]

        for (
            previous,
            current,
        ) in zip(
            server_ticks,
            server_ticks[1:],
        ):
            if (
                current
                != previous + 1
            ):
                _add_rejection(
                    rejections,
                    RejectionCode.NON_CONSECUTIVE_SERVER_TICKS,
                    (
                        "Authoritative server ticks "
                        "must be consecutive."
                    ),
                )

                break

    # --------------------------------------------------------------
    # Seed consistency
    # --------------------------------------------------------------

    if (
        "seed_noise"
        in valid_streams
    ):
        for (
            row_index,
            row,
        ) in enumerate(
            valid_streams[
                "seed_noise"
            ]
        ):
            if (
                isinstance(
                    row,
                    Mapping,
                )
                and isinstance(
                    row.get("seed"),
                    int,
                )
                and not isinstance(
                    row.get("seed"),
                    bool,
                )
                and row.get("seed")
                != package["seed"]
            ):
                _add_rejection(
                    rejections,
                    RejectionCode.IDENTITY_MISMATCH,
                    (
                        f"seed_noise[{row_index}] "
                        "seed does not match "
                        "the package seed."
                    ),
                )

    # --------------------------------------------------------------
    # Camera impulse-orientation evidence
    # --------------------------------------------------------------

    orientation = package[
        "impulse_orientation"
    ]

    orientation_required = (
        "status",
        "fixture_id",
        "camera_component_0_observed_effect",
        "camera_component_1_observed_effect",
        "evidence_hash",
    )

    if not isinstance(
        orientation,
        Mapping,
    ):
        _add_rejection(
            rejections,
            RejectionCode.IMPULSE_ORIENTATION_INCOMPLETE,
            (
                "impulse_orientation "
                "must be a mapping."
            ),
        )

    else:
        orientation_missing = _missing_fields(
            orientation,
            orientation_required,
        )

        if orientation_missing:
            _add_rejection(
                rejections,
                RejectionCode.IMPULSE_ORIENTATION_INCOMPLETE,
                (
                    "Missing impulse-orientation fields: "
                    + ", ".join(
                        orientation_missing
                    )
                ),
            )

        else:
            status = orientation[
                "status"
            ]

            if status != "verified":
                _add_rejection(
                    rejections,
                    RejectionCode.IMPULSE_ORIENTATION_UNVERIFIED,
                    (
                        "Camera-axis impulse "
                        "orientation must be verified "
                        "before acceptance."
                    ),
                )

            for field in (
                "fixture_id",
                "camera_component_0_observed_effect",
                "camera_component_1_observed_effect",
            ):
                value = orientation[
                    field
                ]

                if (
                    not isinstance(
                        value,
                        str,
                    )
                    or not value.strip()
                ):
                    _add_rejection(
                        rejections,
                        RejectionCode.IMPULSE_ORIENTATION_INCOMPLETE,
                        (
                            "Impulse-orientation field "
                            f"{field!r} cannot be blank."
                        ),
                    )

            if not _is_sha256(
                orientation[
                    "evidence_hash"
                ]
            ):
                _add_rejection(
                    rejections,
                    RejectionCode.INVALID_HASH,
                    (
                        "Impulse-orientation "
                        "evidence_hash must be "
                        "a valid SHA-256 value."
                    ),
                )

    return TrajectoryValidationResult(
        accepted=not rejections,
        rejections=tuple(
            rejections
        ),
    )