"""Additive v2 capture/state adapter with separate literal and canonical hashes."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from mineocclude.analysis.coordinates import build_state_input_from_capture_package
from mineocclude.experiments.registry import canonical_json_bytes

STATE_INPUT_V2_SCHEMA_VERSION = "person-b-state-input-v0.2"


class StateInputV2Error(ValueError):
    """Fail-closed state-lineage error for the v2 bridge."""


def _fail(message: str) -> None:
    raise StateInputV2Error(message)


def _is_sha256(value: Any) -> bool:
    if not isinstance(value, str) or len(value) != 64:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return value == value.lower()


def _strict_capture(payload: bytes) -> Mapping[str, Any]:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                _fail(f"Capture package repeats JSON key {key!r}.")
            result[key] = value
        return result

    try:
        document = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=reject_duplicates,
            parse_constant=lambda value: _fail(
                f"Capture package contains non-finite constant {value!r}."
            ),
        )
    except StateInputV2Error:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        _fail(f"Capture package is not strict UTF-8 JSON: {error}")
    if not isinstance(document, Mapping):
        _fail("Capture package root must be an object.")
    return document


def build_state_input_v2_from_capture_bytes(
    capture_bytes: bytes,
    *,
    expected_literal_capture_package_sha256: str,
    coordinate_frame: Mapping[str, Any],
    model_hash: str,
    preprocess_hash: str,
) -> dict[str, Any]:
    """Build a v2 state input while preserving two non-interchangeable hashes.

    ``literal_capture_package_sha256`` authenticates the exact Person C file
    bytes. ``canonical_state_object_sha256`` authenticates Person B's parsed,
    deterministic JSON object. They are validated independently and are never
    compared with each other.
    """

    if not isinstance(capture_bytes, bytes) or not capture_bytes:
        _fail("capture_bytes must be non-empty literal bytes.")
    if not _is_sha256(expected_literal_capture_package_sha256):
        _fail("Expected literal capture identity must be lowercase SHA-256.")
    literal_hash = hashlib.sha256(capture_bytes).hexdigest()
    if literal_hash != expected_literal_capture_package_sha256:
        _fail("Literal capture-package SHA-256 does not match Person C authority.")

    package = _strict_capture(capture_bytes)
    canonical_state_hash = hashlib.sha256(canonical_json_bytes(package)).hexdigest()
    state_v1 = build_state_input_from_capture_package(
        package,
        coordinate_frame=coordinate_frame,
        model_hash=model_hash,
        preprocess_hash=preprocess_hash,
    )
    trajectory_id = package.get("trajectory_id")
    if not isinstance(trajectory_id, str) or not trajectory_id:
        _fail("Capture package lacks trajectory identity.")
    artifacts = package.get("artifacts")
    if not isinstance(artifacts, Mapping):
        _fail("Capture package lacks artifact identities.")
    frame_map = artifacts.get("frame_map")
    state = artifacts.get("server_state")
    if not isinstance(frame_map, Mapping) or not isinstance(state, Mapping):
        _fail("Capture package lacks frame-map/state artifact identities.")
    c_frame_map_sha256 = frame_map.get("sha256")
    c_state_sha256 = state.get("sha256")
    if not _is_sha256(c_frame_map_sha256) or not _is_sha256(c_state_sha256):
        _fail("C frame-map/state artifact hashes must be lowercase SHA-256.")

    streams = package.get("streams")
    if not isinstance(streams, Mapping):
        _fail("Capture package lacks source streams.")
    frame_rows = streams.get("frame_map")
    state_rows = streams.get("server_state")
    if (
        not isinstance(frame_rows, list)
        or not isinstance(state_rows, list)
        or len(frame_rows) != len(state_rows)
        or len(frame_rows) != len(state_v1["rows"])
    ):
        _fail("C frame-map/state and B state-row cardinalities differ.")

    source_by_global: dict[int, tuple[Mapping[str, Any], Mapping[str, Any]]] = {}
    for frame_row, state_row in zip(frame_rows, state_rows, strict=True):
        if not isinstance(frame_row, Mapping) or not isinstance(state_row, Mapping):
            _fail("C source rows must be objects.")
        global_idx = frame_row.get("model_frame_idx")
        exact = {
            "trajectory_id": trajectory_id,
            "model_frame_idx": global_idx,
            "render_frame_idx": global_idx,
            "server_tick": global_idx,
        }
        if (
            not isinstance(global_idx, int)
            or isinstance(global_idx, bool)
            or global_idx < 0
            or any(frame_row.get(field) != value for field, value in exact.items())
            or any(state_row.get(field) != value for field, value in exact.items())
            or global_idx in source_by_global
        ):
            _fail("C source frame identity is not exact and one-to-one.")
        source_by_global[global_idx] = (frame_row, state_row)
    if sorted(source_by_global) != list(range(len(source_by_global))):
        _fail("C global model-frame identity is not contiguous from zero.")

    rows: list[dict[str, Any]] = []
    for row in state_v1["rows"]:
        global_idx = row["model_frame_idx"]
        frame_row, state_row = source_by_global[global_idx]
        decorated = dict(row)
        decorated.update(
            {
                "accepted_c_manifest_sha256": literal_hash,
                "canonical_episode_manifest_sha256": row["accepted_manifest_hash"],
                "canonical_state_object_sha256": canonical_state_hash,
                "c_frame_map_row_sha256": hashlib.sha256(
                    canonical_json_bytes(frame_row)
                ).hexdigest(),
                "c_frame_map_sha256": c_frame_map_sha256,
                "c_state_row_sha256": hashlib.sha256(
                    canonical_json_bytes(state_row)
                ).hexdigest(),
                "c_state_sha256": c_state_sha256,
                "global_model_frame_idx": global_idx,
                "literal_capture_package_sha256": literal_hash,
                "source_frame_id": f"{trajectory_id}:render_frame:{global_idx}",
                "source_frame_idx": global_idx,
                "source_tick": global_idx,
                "state_input_schema_version": STATE_INPUT_V2_SCHEMA_VERSION,
            }
        )
        rows.append(decorated)

    return {
        "accepted_c_manifest_sha256": literal_hash,
        "canonical_episode_manifest_sha256": state_v1["accepted_manifest_hash"],
        "canonical_state_object_sha256": canonical_state_hash,
        "condition": package.get("condition"),
        "coordinate_frame": dict(coordinate_frame),
        "join_key": ["trajectory_id", "global_model_frame_idx"],
        "literal_capture_package_sha256": literal_hash,
        "producer_role": "person_b",
        "rows": rows,
        "schema_version": "1.0",
        "source_role": "person_c",
        "state_input_schema_version": STATE_INPUT_V2_SCHEMA_VERSION,
        "trajectory_id": trajectory_id,
    }


__all__ = [
    "STATE_INPUT_V2_SCHEMA_VERSION",
    "StateInputV2Error",
    "build_state_input_v2_from_capture_bytes",
]
