"""Strict additive Person C capture-package contract.

This validator layers Person C producer checks on top of Person A's frozen
schema-v1.0 trajectory validator. It does not modify, relax, repair, reorder,
or coerce the submitted package.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any

from mineocclude.contracts.identity import SCHEMA_VERSION
from mineocclude.contracts.trajectory import (
    CAPTURE_KEY,
    ROW_STREAMS,
    validate_trajectory_package,
)


PERSON_C_CONTRACT_VERSION = "0.1"
TICK_RATE_HZ = 20.0
TICK_INTERVAL_SECONDS = 0.05
RUNTIME_PIN_SENTINEL = "PIN_REQUIRED_BEFORE_RUNTIME"

ACTION_STREAMS = (
    "raw_actions",
    "normalized_actions",
)

STATE_FIELDS = (
    "target_entity_id",
    "target_present",
    "position_x_blocks",
    "position_y_blocks",
    "position_z_blocks",
    "wall_parallel_position_blocks",
    "velocity_x_blocks_per_second",
    "velocity_y_blocks_per_second",
    "velocity_z_blocks_per_second",
)


class CaptureRejectionCode(str, Enum):
    """Stable Person C capture rejection codes."""

    MISSING_REQUIRED_FIELD = "missing_required_field"
    INVALID_SCHEMA_VERSION = "invalid_schema_version"
    INVALID_PERSON_C_CONTRACT_VERSION = (
        "invalid_person_c_contract_version"
    )
    INVALID_MANIFEST = "invalid_manifest"
    INVALID_EXCLUSION_LEDGER = "invalid_exclusion_ledger"
    INVALID_NOISE_SCHEDULE = "invalid_noise_schedule"
    UNRESOLVED_RUNTIME_PIN = "unresolved_runtime_pin"

    MISSING_ACTION = "missing_action"
    MISSING_FRAME = "missing_frame"
    DUPLICATE_FRAME = "duplicate_frame"
    DUPLICATE_STATE = "duplicate_state"
    SKIPPED_TICK = "skipped_tick"
    MIXED_EPISODE_ID = "mixed_episode_id"
    NON_MONOTONIC_INDEX = "non_monotonic_index"
    SHIFTED_ACTION = "shifted_action"
    INVALID_MEDIA_METADATA = "invalid_media_metadata"

    INVALID_STATE_PAYLOAD = "invalid_state_payload"
    INVALID_TEMPORAL_ALIGNMENT = "invalid_temporal_alignment"
    UPSTREAM_TRAJECTORY_REJECTED = "upstream_trajectory_rejected"


@dataclass(frozen=True)
class CaptureRejection:
    """One immutable Person C rejection."""

    code: CaptureRejectionCode
    message: str


@dataclass(frozen=True)
class CaptureValidationResult:
    """Result of validating one Person C package."""

    accepted: bool
    rejections: tuple[CaptureRejection, ...]


def _reject(
    rejections: list[CaptureRejection],
    code: CaptureRejectionCode,
    message: str,
) -> None:
    rejections.append(CaptureRejection(code=code, message=message))


def _is_non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_non_negative_integer(value: Any) -> bool:
    return (
        isinstance(value, int)
        and not isinstance(value, bool)
        and value >= 0
    )


def _is_finite_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _is_sha256(value: Any) -> bool:
    if not isinstance(value, str) or len(value) != 64:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return True


def _is_git_sha(value: Any) -> bool:
    if not isinstance(value, str) or len(value) != 40:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return True


def _capture_key(row: Mapping[str, Any]) -> tuple[Any, ...] | None:
    if any(field not in row for field in CAPTURE_KEY):
        return None
    if (
        not _is_non_empty_string(row["episode_id"])
        or not _is_non_empty_string(row["trajectory_id"])
        or any(
            not _is_non_negative_integer(row[field])
            for field in CAPTURE_KEY[2:]
        )
    ):
        return None
    return tuple(row[field] for field in CAPTURE_KEY)


def _mapping_rows(
    streams: Mapping[str, Any],
    stream_name: str,
) -> list[Mapping[str, Any]]:
    value = streams.get(stream_name)
    if not isinstance(value, list):
        return []
    return [row for row in value if isinstance(row, Mapping)]


def _duplicates(values: Sequence[Any]) -> bool:
    try:
        return len(values) != len(set(values))
    except TypeError:
        return True


def _validate_manifest(
    package: Mapping[str, Any],
    rejections: list[CaptureRejection],
) -> Mapping[str, Any] | None:
    manifest = package.get("episode_manifest")
    if not isinstance(manifest, Mapping):
        _reject(
            rejections,
            CaptureRejectionCode.INVALID_MANIFEST,
            "episode_manifest must be a mapping.",
        )
        return None

    required = (
        "schema_version",
        "person_c_contract_version",
        "episode_id",
        "trajectory_id",
        "layout_id",
        "run_id",
        "condition",
        "regime",
        "seed",
        "tick_rate_hz",
        "dt_seconds",
        "q",
        "v",
        "duration",
        "code_sha",
        "config_hash",
        "layout_config_hash",
        "environment_lock_hash",
        "noise_schedule_hash",
        "rng",
        "lifecycle_version",
        "status",
    )
    missing = [field for field in required if field not in manifest]
    if missing:
        _reject(
            rejections,
            CaptureRejectionCode.INVALID_MANIFEST,
            "episode_manifest is missing: " + ", ".join(missing),
        )
        return manifest

    for field in (
        "episode_id",
        "trajectory_id",
        "layout_id",
        "run_id",
        "condition",
        "regime",
        "lifecycle_version",
        "status",
    ):
        if not _is_non_empty_string(manifest[field]):
            _reject(
                rejections,
                CaptureRejectionCode.INVALID_MANIFEST,
                f"episode_manifest.{field} must be a non-empty string.",
            )
    if manifest["status"] not in {"accepted", "excluded", "superseded"}:
        _reject(
            rejections,
            CaptureRejectionCode.INVALID_MANIFEST,
            "episode_manifest.status has an invalid lifecycle value.",
        )

    if manifest["schema_version"] != SCHEMA_VERSION:
        _reject(
            rejections,
            CaptureRejectionCode.INVALID_SCHEMA_VERSION,
            "episode_manifest must retain schema_version '1.0'.",
        )
    if manifest["person_c_contract_version"] != PERSON_C_CONTRACT_VERSION:
        _reject(
            rejections,
            CaptureRejectionCode.INVALID_PERSON_C_CONTRACT_VERSION,
            "episode_manifest must use Person C contract version '0.1'.",
        )

    matching_fields = (
        "episode_id",
        "trajectory_id",
        "layout_id",
        "run_id",
        "condition",
        "seed",
    )
    for field in matching_fields:
        if manifest[field] != package.get(field):
            _reject(
                rejections,
                CaptureRejectionCode.INVALID_MANIFEST,
                f"episode_manifest.{field} does not match the package.",
            )

    for field in ("q", "v", "duration"):
        if not _is_finite_number(manifest[field]):
            _reject(
                rejections,
                CaptureRejectionCode.INVALID_MANIFEST,
                f"episode_manifest.{field} must be finite numeric data.",
            )
    if _is_finite_number(manifest["q"]) and manifest["q"] < 0:
        _reject(
            rejections,
            CaptureRejectionCode.INVALID_MANIFEST,
            "episode_manifest.q cannot be negative.",
        )
    if _is_finite_number(manifest["duration"]) and manifest["duration"] < 0:
        _reject(
            rejections,
            CaptureRejectionCode.INVALID_MANIFEST,
            "episode_manifest.duration cannot be negative.",
        )
    if (
        not _is_finite_number(manifest["tick_rate_hz"])
        or float(manifest["tick_rate_hz"]) != TICK_RATE_HZ
        or not _is_finite_number(manifest["dt_seconds"])
        or float(manifest["dt_seconds"]) != TICK_INTERVAL_SECONDS
    ):
        _reject(
            rejections,
            CaptureRejectionCode.INVALID_MANIFEST,
            "The capture clock must be 20 Hz with dt=0.05 seconds.",
        )

    if not _is_git_sha(manifest["code_sha"]):
        _reject(
            rejections,
            CaptureRejectionCode.INVALID_MANIFEST,
            "episode_manifest.code_sha must be a full Git SHA.",
        )
    for field in (
        "config_hash",
        "layout_config_hash",
        "environment_lock_hash",
        "noise_schedule_hash",
    ):
        if not _is_sha256(manifest[field]):
            _reject(
                rejections,
                CaptureRejectionCode.INVALID_MANIFEST,
                f"episode_manifest.{field} must be SHA-256.",
            )

    rng = manifest["rng"]
    if not isinstance(rng, Mapping):
        _reject(
            rejections,
            CaptureRejectionCode.INVALID_MANIFEST,
            "episode_manifest.rng must be a mapping.",
        )
    else:
        rng_required = (
            "producer",
            "bit_generator",
            "numpy_version",
            "immutable_schedule",
            "java_consumption",
        )
        rng_missing = [field for field in rng_required if field not in rng]
        if rng_missing:
            _reject(
                rejections,
                CaptureRejectionCode.INVALID_MANIFEST,
                "episode_manifest.rng is missing: " + ", ".join(rng_missing),
            )
        else:
            if rng["producer"] != "numpy.random.Generator":
                _reject(
                    rejections,
                    CaptureRejectionCode.INVALID_MANIFEST,
                    "The noise producer must be numpy.random.Generator.",
                )
            if not _is_non_empty_string(rng["bit_generator"]):
                _reject(
                    rejections,
                    CaptureRejectionCode.INVALID_MANIFEST,
                    "rng.bit_generator must be explicit.",
                )
            elif rng["bit_generator"] != "PCG64":
                _reject(
                    rejections,
                    CaptureRejectionCode.INVALID_MANIFEST,
                    "The Person C v0.1 bit generator must be PCG64.",
                )
            if not _is_non_empty_string(rng["numpy_version"]):
                _reject(
                    rejections,
                    CaptureRejectionCode.INVALID_MANIFEST,
                    "rng.numpy_version must be explicit.",
                )
            if rng["immutable_schedule"] is not True:
                _reject(
                    rejections,
                    CaptureRejectionCode.INVALID_MANIFEST,
                    "The noise schedule must be immutable.",
                )
            if rng["java_consumption"] != "stored_draws_in_draw_idx_order":
                _reject(
                    rejections,
                    CaptureRejectionCode.INVALID_MANIFEST,
                    "Java must consume stored draws in draw_idx order.",
                )
            if (
                rng["numpy_version"] == RUNTIME_PIN_SENTINEL
                and package.get("synthetic") is not True
            ):
                _reject(
                    rejections,
                    CaptureRejectionCode.UNRESOLVED_RUNTIME_PIN,
                    "Real capture requires an exact NumPy version pin.",
                )

    return manifest


def _validate_ledger(
    package: Mapping[str, Any],
    rejections: list[CaptureRejection],
) -> None:
    ledger = package.get("exclusion_ledger")
    if not isinstance(ledger, list):
        _reject(
            rejections,
            CaptureRejectionCode.INVALID_EXCLUSION_LEDGER,
            "exclusion_ledger must be a list.",
        )
        return

    seen_ids: set[str] = set()
    for index, entry in enumerate(ledger):
        label = f"exclusion_ledger[{index}]"
        if not isinstance(entry, Mapping):
            _reject(
                rejections,
                CaptureRejectionCode.INVALID_EXCLUSION_LEDGER,
                f"{label} must be a mapping.",
            )
            continue
        required = (
            "exclusion_id",
            "schema_version",
            "person_c_contract_version",
            "episode_id",
            "trajectory_id",
            "run_id",
            "status",
            "exclusion_reason",
            "rejection_codes",
            "recorded_at_utc",
            "source_artifact_hash",
            "superseded_by",
        )
        missing = [field for field in required if field not in entry]
        if missing:
            _reject(
                rejections,
                CaptureRejectionCode.INVALID_EXCLUSION_LEDGER,
                f"{label} is missing: " + ", ".join(missing),
            )
            continue
        exclusion_id = entry["exclusion_id"]
        if not _is_non_empty_string(exclusion_id) or exclusion_id in seen_ids:
            _reject(
                rejections,
                CaptureRejectionCode.INVALID_EXCLUSION_LEDGER,
                f"{label}.exclusion_id must be non-empty and unique.",
            )
        else:
            seen_ids.add(exclusion_id)
        if (
            entry["schema_version"] != SCHEMA_VERSION
            or entry["person_c_contract_version"]
            != PERSON_C_CONTRACT_VERSION
            or entry["episode_id"] != package.get("episode_id")
            or entry["trajectory_id"] != package.get("trajectory_id")
            or entry["run_id"] != package.get("run_id")
            or entry["status"] != "excluded"
            or not _is_non_empty_string(entry["exclusion_reason"])
            or entry["superseded_by"] is not None
        ):
            _reject(
                rejections,
                CaptureRejectionCode.INVALID_EXCLUSION_LEDGER,
                f"{label} violates identity or excluded-lifecycle rules.",
            )
        codes = entry["rejection_codes"]
        if (
            not isinstance(codes, list)
            or not codes
            or any(not _is_non_empty_string(code) for code in codes)
        ):
            _reject(
                rejections,
                CaptureRejectionCode.INVALID_EXCLUSION_LEDGER,
                f"{label}.rejection_codes must be a non-empty string list.",
            )
        if not _is_non_empty_string(entry["recorded_at_utc"]):
            _reject(
                rejections,
                CaptureRejectionCode.INVALID_EXCLUSION_LEDGER,
                f"{label}.recorded_at_utc must be explicit.",
            )
        if not _is_sha256(entry["source_artifact_hash"]):
            _reject(
                rejections,
                CaptureRejectionCode.INVALID_EXCLUSION_LEDGER,
                f"{label}.source_artifact_hash must be SHA-256.",
            )


def _validate_media(
    package: Mapping[str, Any],
    rejections: list[CaptureRejection],
) -> int | None:
    media = package.get("media")
    if not isinstance(media, Mapping):
        _reject(
            rejections,
            CaptureRejectionCode.INVALID_MEDIA_METADATA,
            "media must be a mapping.",
        )
        return None
    expected = {
        "width": 640,
        "height": 360,
        "fps": 20.0,
    }
    for field, value in expected.items():
        actual = media.get(field)
        if (
            not _is_finite_number(actual)
            or float(actual) != float(value)
        ):
            _reject(
                rejections,
                CaptureRejectionCode.INVALID_MEDIA_METADATA,
                f"media.{field} must equal {value}.",
            )
    frame_count = media.get("frame_count")
    if not _is_non_negative_integer(frame_count) or frame_count == 0:
        _reject(
            rejections,
            CaptureRejectionCode.INVALID_MEDIA_METADATA,
            "media.frame_count must be a positive integer.",
        )
        return None
    return frame_count


def _validate_frame_map(
    frame_map: list[Mapping[str, Any]],
    frame_count: int | None,
    rejections: list[CaptureRejection],
) -> bool:
    """Validate frame identity and return whether it is complete."""

    if frame_count is None:
        return False
    render_values = [row.get("render_frame_idx") for row in frame_map]
    valid_render_values = [
        value
        for value in render_values
        if _is_non_negative_integer(value)
    ]
    if (
        len(frame_map) < frame_count
        or len(valid_render_values) != len(frame_map)
        or set(valid_render_values) != set(range(frame_count))
    ):
        if not _duplicates(render_values):
            _reject(
                rejections,
                CaptureRejectionCode.MISSING_FRAME,
                "frame_map does not cover every declared render frame.",
            )
    if _duplicates(render_values):
        _reject(
            rejections,
            CaptureRejectionCode.DUPLICATE_FRAME,
            "frame_map contains a duplicate render_frame_idx.",
        )

    valid_timeline = all(
        _is_non_negative_integer(row.get("server_tick"))
        and _is_non_negative_integer(row.get("render_frame_idx"))
        and _is_non_negative_integer(row.get("action_idx"))
        and _is_non_negative_integer(row.get("model_frame_idx"))
        for row in frame_map
    )
    if not valid_timeline:
        return False

    ordered = sorted(frame_map, key=lambda row: row["server_tick"])
    ticks = [row["server_tick"] for row in ordered]
    if any(current != previous + 1 for previous, current in zip(ticks, ticks[1:])):
        _reject(
            rejections,
            CaptureRejectionCode.SKIPPED_TICK,
            "server_tick must advance by exactly one tick.",
        )

    expected_indices = list(range(frame_count))
    for field in (
        "render_frame_idx",
        "action_idx",
        "model_frame_idx",
    ):
        values = [row[field] for row in ordered]
        if values != expected_indices:
            _reject(
                rejections,
                CaptureRejectionCode.NON_MONOTONIC_INDEX,
                f"{field} must increase with server_tick independent of row order.",
            )
            break

    return (
        len(frame_map) == frame_count
        and len(valid_render_values) == len(frame_map)
        and set(valid_render_values) == set(range(frame_count))
        and not _duplicates(render_values)
    )


def _validate_stream_relationships(
    package: Mapping[str, Any],
    frame_count: int | None,
    rejections: list[CaptureRejection],
) -> tuple[Mapping[str, Any], list[Mapping[str, Any]]]:
    streams = package.get("streams")
    if not isinstance(streams, Mapping):
        return {}, []
    frame_map = _mapping_rows(streams, "frame_map")
    complete_frame_map = _validate_frame_map(
        frame_map,
        frame_count,
        rejections,
    )
    frame_keys = {
        key
        for row in frame_map
        for key in [_capture_key(row)]
        if key is not None
    }

    episode_values = [
        row.get("episode_id")
        for stream_name in ROW_STREAMS
        for row in _mapping_rows(streams, stream_name)
        if "episode_id" in row
    ]
    if (
        any(not _is_non_empty_string(value) for value in episode_values)
        or set(episode_values) != {package.get("episode_id")}
    ):
        _reject(
            rejections,
            CaptureRejectionCode.MIXED_EPISODE_ID,
            "All row streams must use the package episode_id.",
        )

    if complete_frame_map:
        for stream_name in ACTION_STREAMS:
            rows = _mapping_rows(streams, stream_name)
            keys = {
                key
                for row in rows
                for key in [_capture_key(row)]
                if key is not None
            }
            if len(rows) < len(frame_map) or len(keys) < len(frame_keys):
                _reject(
                    rejections,
                    CaptureRejectionCode.MISSING_ACTION,
                    f"{stream_name} is missing an action identity.",
                )
            elif keys != frame_keys:
                _reject(
                    rejections,
                    CaptureRejectionCode.SHIFTED_ACTION,
                    f"{stream_name} action identities are shifted from frame_map.",
                )

    state_rows = _mapping_rows(streams, "server_state")
    state_keys = [
        key
        for row in state_rows
        for key in [_capture_key(row)]
        if key is not None
    ]
    state_ticks = [row.get("server_tick") for row in state_rows]
    if _duplicates(state_keys) or _duplicates(state_ticks):
        _reject(
            rejections,
            CaptureRejectionCode.DUPLICATE_STATE,
            "server_state contains a duplicate state identity.",
        )

    for index, row in enumerate(state_rows):
        state = row.get("state")
        if not isinstance(state, Mapping):
            continue
        missing = [field for field in STATE_FIELDS if field not in state]
        if missing:
            _reject(
                rejections,
                CaptureRejectionCode.INVALID_STATE_PAYLOAD,
                f"server_state[{index}].state is missing: " + ", ".join(missing),
            )
            continue
        if not _is_non_empty_string(state["target_entity_id"]):
            _reject(
                rejections,
                CaptureRejectionCode.INVALID_STATE_PAYLOAD,
                f"server_state[{index}] target_entity_id must be non-empty.",
            )
        if not isinstance(state["target_present"], bool):
            _reject(
                rejections,
                CaptureRejectionCode.INVALID_STATE_PAYLOAD,
                f"server_state[{index}] target_present must be boolean.",
            )
        for field in STATE_FIELDS[2:]:
            if not _is_finite_number(state[field]):
                _reject(
                    rejections,
                    CaptureRejectionCode.INVALID_STATE_PAYLOAD,
                    f"server_state[{index}].state.{field} must be finite.",
                )

    return streams, frame_map


def _validate_noise_schedule(
    package: Mapping[str, Any],
    manifest: Mapping[str, Any] | None,
    streams: Mapping[str, Any],
    frame_map: list[Mapping[str, Any]],
    rejections: list[CaptureRejection],
) -> None:
    if manifest is None:
        return
    artifacts = package.get("artifacts")
    seed_descriptor = (
        artifacts.get("seed_noise")
        if isinstance(artifacts, Mapping)
        else None
    )
    if (
        not isinstance(seed_descriptor, Mapping)
        or manifest.get("noise_schedule_hash")
        != seed_descriptor.get("sha256")
    ):
        _reject(
            rejections,
            CaptureRejectionCode.INVALID_NOISE_SCHEDULE,
            "Manifest noise_schedule_hash must match the seed_noise artifact.",
        )
    rows = _mapping_rows(streams, "seed_noise")
    if len(rows) != len(frame_map):
        _reject(
            rejections,
            CaptureRejectionCode.INVALID_NOISE_SCHEDULE,
            "The noise schedule must contain exactly one draw per frame tick.",
        )
        return
    required = (
        "draw_idx",
        "standard_normal_draw",
        "noise_std_blocks",
        "dt_seconds",
        "q",
        "noise_draw",
    )
    usable: list[Mapping[str, Any]] = []
    for index, row in enumerate(rows):
        missing = [field for field in required if field not in row]
        if missing:
            _reject(
                rejections,
                CaptureRejectionCode.INVALID_NOISE_SCHEDULE,
                f"seed_noise[{index}] is missing: " + ", ".join(missing),
            )
            continue
        if not _is_non_negative_integer(row["draw_idx"]):
            _reject(
                rejections,
                CaptureRejectionCode.INVALID_NOISE_SCHEDULE,
                f"seed_noise[{index}].draw_idx must be non-negative.",
            )
            continue
        if any(
            not _is_finite_number(row[field])
            for field in required[1:]
        ):
            _reject(
                rejections,
                CaptureRejectionCode.INVALID_NOISE_SCHEDULE,
                f"seed_noise[{index}] contains non-finite schedule data.",
            )
            continue
        usable.append(row)

    ordered = sorted(usable, key=lambda row: row["draw_idx"])
    if [row["draw_idx"] for row in ordered] != list(range(len(frame_map))):
        _reject(
            rejections,
            CaptureRejectionCode.INVALID_NOISE_SCHEDULE,
            "draw_idx must be the complete zero-based tick schedule.",
        )

    q = manifest.get("q")
    dt = manifest.get("dt_seconds")
    if not _is_finite_number(q) or not _is_finite_number(dt) or q < 0:
        return
    expected_std = math.sqrt(float(q) * float(dt))
    for index, row in enumerate(ordered):
        if (
            not math.isclose(float(row["q"]), float(q), rel_tol=0.0, abs_tol=1e-12)
            or not math.isclose(
                float(row["dt_seconds"]),
                float(dt),
                rel_tol=0.0,
                abs_tol=1e-12,
            )
            or not math.isclose(
                float(row["noise_std_blocks"]),
                expected_std,
                rel_tol=0.0,
                abs_tol=1e-12,
            )
            or not math.isclose(
                float(row["noise_draw"]),
                float(row["standard_normal_draw"]) * expected_std,
                rel_tol=0.0,
                abs_tol=1e-12,
            )
        ):
            _reject(
                rejections,
                CaptureRejectionCode.INVALID_NOISE_SCHEDULE,
                f"seed_noise[{index}] violates sqrt(q * dt) scaling.",
            )

def _validate_temporal_alignment(
    package: Mapping[str, Any],
    frame_map: list[Mapping[str, Any]],
    rejections: list[CaptureRejection],
) -> None:
    evidence = package.get("temporal_alignment")
    if not isinstance(evidence, Mapping):
        _reject(
            rejections,
            CaptureRejectionCode.INVALID_TEMPORAL_ALIGNMENT,
            "temporal_alignment must be a mapping.",
        )
        return
    required = (
        "status",
        "evidence_scope",
        "action_idx",
        "visual_before_model_frame_idx",
        "visual_after_model_frame_idx",
        "effect_server_tick",
        "evidence_hash",
    )
    missing = [field for field in required if field not in evidence]
    if missing:
        _reject(
            rejections,
            CaptureRejectionCode.INVALID_TEMPORAL_ALIGNMENT,
            "temporal_alignment is missing: " + ", ".join(missing),
        )
        return
    if (
        evidence["status"] != "verified"
        or evidence["evidence_scope"] != "synthetic_contract_only"
        or not _is_sha256(evidence["evidence_hash"])
    ):
        _reject(
            rejections,
            CaptureRejectionCode.INVALID_TEMPORAL_ALIGNMENT,
            "Temporal evidence must be verified, hashed, and synthetic-only.",
        )
    index_fields = (
        "action_idx",
        "visual_before_model_frame_idx",
        "visual_after_model_frame_idx",
        "effect_server_tick",
    )
    if any(not _is_non_negative_integer(evidence[field]) for field in index_fields):
        _reject(
            rejections,
            CaptureRejectionCode.INVALID_TEMPORAL_ALIGNMENT,
            "Temporal alignment indices must be non-negative integers.",
        )
        return
    before = evidence["visual_before_model_frame_idx"]
    after = evidence["visual_after_model_frame_idx"]
    if evidence["action_idx"] != before or after != before + 1:
        _reject(
            rejections,
            CaptureRejectionCode.INVALID_TEMPORAL_ALIGNMENT,
            "action_i must sit between visual_i and visual_(i+1).",
        )
    after_rows = [
        row
        for row in frame_map
        if row.get("model_frame_idx") == after
    ]
    if (
        len(after_rows) != 1
        or after_rows[0].get("server_tick") != evidence["effect_server_tick"]
    ):
        _reject(
            rejections,
            CaptureRejectionCode.INVALID_TEMPORAL_ALIGNMENT,
            "Temporal impulse effect tick does not resolve through frame_map.",
        )


def validate_capture_package(package: Mapping[str, Any]) -> CaptureValidationResult:
    """Validate C0 requirements without mutating or repairing ``package``."""

    rejections: list[CaptureRejection] = []
    if not isinstance(package, Mapping):
        _reject(
            rejections,
            CaptureRejectionCode.MISSING_REQUIRED_FIELD,
            "Capture package must be a mapping.",
        )
        return CaptureValidationResult(False, tuple(rejections))

    required = (
        "schema_version",
        "person_c_contract_version",
        "episode_id",
        "trajectory_id",
        "layout_id",
        "run_id",
        "condition",
        "seed",
        "synthetic",
        "scientific_use",
        "media",
        "artifacts",
        "streams",
        "episode_manifest",
        "exclusion_ledger",
        "temporal_alignment",
    )
    missing = [field for field in required if field not in package]
    if missing:
        _reject(
            rejections,
            CaptureRejectionCode.MISSING_REQUIRED_FIELD,
            "Capture package is missing: " + ", ".join(missing),
        )
        return CaptureValidationResult(False, tuple(rejections))

    if package["schema_version"] != SCHEMA_VERSION:
        _reject(
            rejections,
            CaptureRejectionCode.INVALID_SCHEMA_VERSION,
            "Person C must preserve shared schema_version '1.0'.",
        )
    if package["person_c_contract_version"] != PERSON_C_CONTRACT_VERSION:
        _reject(
            rejections,
            CaptureRejectionCode.INVALID_PERSON_C_CONTRACT_VERSION,
            "Expected person_c_contract_version '0.1'.",
        )
    for field in (
        "episode_id",
        "trajectory_id",
        "layout_id",
        "run_id",
        "condition",
    ):
        if not _is_non_empty_string(package[field]):
            _reject(
                rejections,
                CaptureRejectionCode.MISSING_REQUIRED_FIELD,
                f"{field} must be a non-empty string.",
            )
    if not isinstance(package["synthetic"], bool):
        _reject(
            rejections,
            CaptureRejectionCode.MISSING_REQUIRED_FIELD,
            "synthetic must be boolean.",
        )
    if package["synthetic"] is True and package["scientific_use"] != "forbidden":
        _reject(
            rejections,
            CaptureRejectionCode.MISSING_REQUIRED_FIELD,
            "Synthetic evidence must set scientific_use='forbidden'.",
        )

    manifest = _validate_manifest(package, rejections)
    _validate_ledger(package, rejections)
    frame_count = _validate_media(package, rejections)
    streams, frame_map = _validate_stream_relationships(
        package,
        frame_count,
        rejections,
    )
    _validate_noise_schedule(package, manifest, streams, frame_map, rejections)
    _validate_temporal_alignment(package, frame_map, rejections)

    upstream = validate_trajectory_package(package)
    for rejection in upstream.rejections:
        _reject(
            rejections,
            CaptureRejectionCode.UPSTREAM_TRAJECTORY_REJECTED,
            f"A schema v1.0 {rejection.code.value}: {rejection.message}",
        )

    return CaptureValidationResult(
        accepted=not rejections,
        rejections=tuple(rejections),
    )
