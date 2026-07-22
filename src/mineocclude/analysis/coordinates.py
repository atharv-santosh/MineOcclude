"""Canonical wall-parallel coordinate contract for Person B targets."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any

from mineocclude.contracts.identity import FRAME_KEY, SCHEMA_VERSION
from mineocclude.contracts.trajectory import CAPTURE_KEY
from mineocclude.data.capture_contract import (
    TICK_INTERVAL_SECONDS,
    validate_capture_package,
)

from .manifests import is_hex_digest, sha256_value


COORDINATE_FRAME_SCHEMA_VERSION = "person-b-wall-parallel-frame-v0.1"


class CoordinateContractError(ValueError):
    """Raised when wall-parallel position or direction is ambiguous."""


class CaptureStateHandoffCode(str, Enum):
    """Stable fail-closed C-to-B adapter rejection codes."""

    INVALID_CAPTURE_PACKAGE = "invalid_capture_package"
    INVALID_COORDINATE_FRAME = "invalid_coordinate_frame"
    LAYOUT_BINDING_MISMATCH = "layout_binding_mismatch"
    MISSING_A_PROVENANCE = "missing_a_provenance"
    NO_OBJECT_NOT_ORACLE_ELIGIBLE = "no_object_not_oracle_eligible"
    STREAM_IDENTITY_MISMATCH = "stream_identity_mismatch"
    COORDINATE_PROJECTION_MISMATCH = "coordinate_projection_mismatch"
    INVALID_VISIBILITY_SEQUENCE = "invalid_visibility_sequence"
    INVALID_STATE_OUTPUT = "invalid_state_output"


class CaptureStateHandoffError(ValueError):
    """Raised instead of repairing an incompatible C capture package."""

    def __init__(self, code: CaptureStateHandoffCode, message: str) -> None:
        self.code = code
        super().__init__(f"{code.value}: {message}")


def _vector3(name: str, value: Any) -> tuple[float, float, float]:
    if (
        not isinstance(value, Sequence)
        or isinstance(value, (str, bytes))
        or len(value) != 3
    ):
        raise CoordinateContractError(f"{name} must contain three numbers.")
    result: list[float] = []
    for component in value:
        if (
            isinstance(component, bool)
            or not isinstance(component, (int, float))
            or not math.isfinite(float(component))
        ):
            raise CoordinateContractError(f"{name} must be finite numeric data.")
        result.append(float(component))
    return result[0], result[1], result[2]


@dataclass(frozen=True)
class WallParallelCoordinateFrame:
    coordinate_frame_id: str
    coordinate_frame_hash: str
    origin_world_xyz: tuple[float, float, float]
    positive_unit_vector_world_xyz: tuple[float, float, float]
    source_layout_manifest_hash: str

    def project(self, world_position_xyz: Sequence[float]) -> float:
        position = _vector3("world_position_xyz", world_position_xyz)
        return sum(
            (position[index] - self.origin_world_xyz[index])
            * self.positive_unit_vector_world_xyz[index]
            for index in range(3)
        )


def coordinate_frame_hash(document: Mapping[str, Any]) -> str:
    """Hash the coordinate-defining content, excluding approvals and its hash."""

    fields = (
        "coordinate_frame_schema_version",
        "coordinate_frame_id",
        "wall_parallel_origin_world_xyz",
        "wall_parallel_positive_unit_vector_world_xyz",
        "source_layout_manifest_hash",
    )
    missing = [field for field in fields if field not in document]
    if missing:
        raise CoordinateContractError(
            "Coordinate frame is missing: " + ", ".join(missing)
        )
    return sha256_value({field: document[field] for field in fields})


def validate_coordinate_frame(
    document: Mapping[str, Any],
    *,
    require_cross_role_signoff: bool = True,
) -> WallParallelCoordinateFrame:
    """Validate the signed scalar projection used by all B target values."""

    if not isinstance(document, Mapping):
        raise CoordinateContractError("coordinate_frame must be a mapping.")
    required = (
        "coordinate_frame_schema_version",
        "coordinate_frame_id",
        "coordinate_frame_hash",
        "wall_parallel_origin_world_xyz",
        "wall_parallel_positive_unit_vector_world_xyz",
        "source_layout_manifest_hash",
        "adapter_signoff",
    )
    missing = [field for field in required if field not in document]
    if missing:
        raise CoordinateContractError(
            "Coordinate frame is missing: " + ", ".join(missing)
        )
    if document["coordinate_frame_schema_version"] != COORDINATE_FRAME_SCHEMA_VERSION:
        raise CoordinateContractError("Coordinate frame schema version mismatch.")
    frame_id = document["coordinate_frame_id"]
    if not isinstance(frame_id, str) or not frame_id.strip():
        raise CoordinateContractError("coordinate_frame_id must be non-empty.")
    origin = _vector3(
        "wall_parallel_origin_world_xyz",
        document["wall_parallel_origin_world_xyz"],
    )
    direction = _vector3(
        "wall_parallel_positive_unit_vector_world_xyz",
        document["wall_parallel_positive_unit_vector_world_xyz"],
    )
    norm = math.hypot(*direction)
    if not math.isclose(norm, 1.0, rel_tol=0.0, abs_tol=1e-9):
        raise CoordinateContractError(
            "wall_parallel_positive_unit_vector_world_xyz must have unit norm."
        )
    source_hash = document["source_layout_manifest_hash"]
    if not is_hex_digest(source_hash, 64):
        raise CoordinateContractError(
            "source_layout_manifest_hash must be SHA-256."
        )
    expected_hash = coordinate_frame_hash(document)
    if document["coordinate_frame_hash"] != expected_hash:
        raise CoordinateContractError(
            "coordinate_frame_hash does not match coordinate-defining fields."
        )
    signoff = document["adapter_signoff"]
    if not isinstance(signoff, Mapping):
        raise CoordinateContractError("adapter_signoff must be a mapping.")
    if require_cross_role_signoff and (
        signoff.get("person_b") is not True or signoff.get("person_c") is not True
    ):
        raise CoordinateContractError(
            "Live coordinate frames require explicit Person B and Person C signoff."
        )
    return WallParallelCoordinateFrame(
        coordinate_frame_id=frame_id,
        coordinate_frame_hash=expected_hash,
        origin_world_xyz=origin,
        positive_unit_vector_world_xyz=direction,
        source_layout_manifest_hash=source_hash,
    )


def _handoff_fail(code: CaptureStateHandoffCode, message: str) -> None:
    raise CaptureStateHandoffError(code, message)


def _capture_key(row: Mapping[str, Any]) -> tuple[Any, ...]:
    if not isinstance(row, Mapping) or any(field not in row for field in CAPTURE_KEY):
        _handoff_fail(
            CaptureStateHandoffCode.STREAM_IDENTITY_MISMATCH,
            "Every joined C row must contain the complete capture identity.",
        )
    return tuple(row[field] for field in CAPTURE_KEY)


def _rows_by_capture_key(
    rows: Any,
    *,
    stream_name: str,
) -> dict[tuple[Any, ...], Mapping[str, Any]]:
    if not isinstance(rows, list) or not rows:
        _handoff_fail(
            CaptureStateHandoffCode.STREAM_IDENTITY_MISMATCH,
            f"C stream {stream_name!r} must be a non-empty row list.",
        )
    indexed: dict[tuple[Any, ...], Mapping[str, Any]] = {}
    for row in rows:
        key = _capture_key(row)
        if key in indexed:
            _handoff_fail(
                CaptureStateHandoffCode.STREAM_IDENTITY_MISMATCH,
                f"C stream {stream_name!r} duplicates capture identity {key!r}.",
            )
        indexed[key] = row
    return indexed


def build_state_input_from_capture_package(
    package: Mapping[str, Any],
    *,
    coordinate_frame: Mapping[str, Any],
    model_hash: str,
    preprocess_hash: str,
    projection_tolerance_blocks: float = 1e-9,
) -> dict[str, Any]:
    """Build B's frozen state input from one fully validated C package.

    C remains authoritative for capture/state truth.  This consumer adapter
    applies B's signed wall-parallel projection and emits no partial document
    when any source identity or semantic check fails.
    """

    validation = validate_capture_package(package)
    if not validation.accepted:
        codes = sorted({item.code.value for item in validation.rejections})
        _handoff_fail(
            CaptureStateHandoffCode.INVALID_CAPTURE_PACKAGE,
            "C package failed its authoritative validator: " + ", ".join(codes),
        )
    try:
        frame = validate_coordinate_frame(coordinate_frame)
    except (CoordinateContractError, TypeError, ValueError) as error:
        _handoff_fail(
            CaptureStateHandoffCode.INVALID_COORDINATE_FRAME,
            str(error),
        )
    if not is_hex_digest(model_hash, 64) or not is_hex_digest(preprocess_hash, 64):
        _handoff_fail(
            CaptureStateHandoffCode.MISSING_A_PROVENANCE,
            "Explicit A model_hash and preprocess_hash must both be SHA-256.",
        )
    if (
        isinstance(projection_tolerance_blocks, bool)
        or not isinstance(projection_tolerance_blocks, (int, float))
        or not math.isfinite(float(projection_tolerance_blocks))
        or projection_tolerance_blocks < 0
    ):
        _handoff_fail(
            CaptureStateHandoffCode.COORDINATE_PROJECTION_MISMATCH,
            "projection_tolerance_blocks must be finite and nonnegative.",
        )

    manifest = package.get("episode_manifest")
    streams = package.get("streams")
    if not isinstance(manifest, Mapping) or not isinstance(streams, Mapping):
        _handoff_fail(
            CaptureStateHandoffCode.INVALID_CAPTURE_PACKAGE,
            "C package manifest and streams must be mappings.",
        )
    layout_hash = manifest.get("layout_config_hash")
    if frame.source_layout_manifest_hash != layout_hash:
        _handoff_fail(
            CaptureStateHandoffCode.LAYOUT_BINDING_MISMATCH,
            "B coordinate frame is not bound to C's layout_config_hash.",
        )

    frame_rows = _rows_by_capture_key(streams.get("frame_map"), stream_name="frame_map")
    state_rows = _rows_by_capture_key(streams.get("server_state"), stream_name="server_state")
    visibility_rows = _rows_by_capture_key(streams.get("visibility"), stream_name="visibility")
    if set(frame_rows) != set(state_rows) or set(frame_rows) != set(visibility_rows):
        _handoff_fail(
            CaptureStateHandoffCode.STREAM_IDENTITY_MISMATCH,
            "C frame, state, and visibility capture identities must match exactly.",
        )

    if package.get("condition") == "occluder_only_no_sheep" or any(
        not row.get("state", {}).get("target_present", False)
        for row in state_rows.values()
    ):
        _handoff_fail(
            CaptureStateHandoffCode.NO_OBJECT_NOT_ORACLE_ELIGIBLE,
            "The C package has no target object and is intentionally ineligible "
            "for B oracle-target construction.",
        )

    accepted_manifest_hash = sha256_value(manifest)
    synthetic = package.get("synthetic") is True
    analysis_regime = "synthetic_test" if synthetic else manifest.get("regime")
    if not synthetic and analysis_regime != "regime_a":
        _handoff_fail(
            CaptureStateHandoffCode.INVALID_STATE_OUTPUT,
            "Non-synthetic oracle handoffs must explicitly declare regime_a.",
        )

    output_rows: list[dict[str, Any]] = []
    last_visible_tick_by_trajectory: dict[str, int] = {}
    for key in sorted(frame_rows, key=lambda value: (value[1], value[5])):
        source = frame_rows[key]
        state = state_rows[key].get("state")
        visibility = visibility_rows[key].get("visibility")
        if not isinstance(state, Mapping) or visibility not in {"visible", "occluded"}:
            _handoff_fail(
                CaptureStateHandoffCode.INVALID_VISIBILITY_SEQUENCE,
                f"Capture identity {key!r} has invalid state or visibility.",
            )
        position = (
            state.get("position_x_blocks"),
            state.get("position_y_blocks"),
            state.get("position_z_blocks"),
        )
        try:
            projected = frame.project(position)
        except CoordinateContractError as error:
            _handoff_fail(
                CaptureStateHandoffCode.COORDINATE_PROJECTION_MISMATCH,
                str(error),
            )
        declared = state.get("wall_parallel_position_blocks")
        if (
            isinstance(declared, bool)
            or not isinstance(declared, (int, float))
            or not math.isfinite(float(declared))
            or not math.isclose(
                projected,
                float(declared),
                rel_tol=0.0,
                abs_tol=float(projection_tolerance_blocks),
            )
        ):
            _handoff_fail(
                CaptureStateHandoffCode.COORDINATE_PROJECTION_MISMATCH,
                f"C and B wall-parallel coordinates disagree for {key!r}.",
            )
        trajectory_id = source["trajectory_id"]
        server_tick = source["server_tick"]
        if visibility == "visible":
            last_visible_tick_by_trajectory[trajectory_id] = server_tick
            tau = 0.0
        else:
            anchor_tick = last_visible_tick_by_trajectory.get(trajectory_id)
            if anchor_tick is None or server_tick <= anchor_tick:
                _handoff_fail(
                    CaptureStateHandoffCode.INVALID_VISIBILITY_SEQUENCE,
                    f"Occluded row {key!r} lacks an earlier visible anchor.",
                )
            tau = (server_tick - anchor_tick) / (1.0 / TICK_INTERVAL_SECONDS)

        row = {
            "episode_id": source["episode_id"],
            "trajectory_id": trajectory_id,
            "server_tick": server_tick,
            "render_frame_idx": source["render_frame_idx"],
            "action_idx": source["action_idx"],
            "model_frame_idx": source["model_frame_idx"],
            "layout_id": package["layout_id"],
            "regime": analysis_regime,
            "visibility": visibility,
            "tau": tau,
            "v": manifest["v"],
            "q": manifest["q"],
            "duration": manifest["duration"],
            "code_sha": manifest["code_sha"],
            "config_hash": manifest["config_hash"],
            "model_hash": model_hash,
            "preprocess_hash": preprocess_hash,
            "seed": package["seed"],
            "schema_version": SCHEMA_VERSION,
            "run_id": package["run_id"],
            "status": "accepted",
            "exclusion_reason": None,
            "superseded_by": None,
            "accepted_manifest_hash": accepted_manifest_hash,
            "x_true_blocks": projected,
            "observed_position_blocks": projected if visibility == "visible" else None,
            "source_capture_regime": manifest.get("regime"),
            "synthetic": synthetic,
            "scientific_use": package.get("scientific_use"),
        }
        output_rows.append(row)

    result = {
        "schema_version": SCHEMA_VERSION,
        "state_input_schema_version": "person-b-state-input-v0.1",
        "producer_role": "person_c",
        "join_key": list(FRAME_KEY),
        "accepted_manifest_hash": accepted_manifest_hash,
        "coordinate_frame": dict(coordinate_frame),
        "rows": output_rows,
    }
    if synthetic:
        result["fixture_metadata"] = {
            "synthetic": True,
            "scientific_use": "forbidden",
            "source_capture_manifest_hash": accepted_manifest_hash,
        }
    # Local import prevents the frozen B contract's coordinate dependency from
    # creating a module-initialization cycle.
    from mineocclude.contracts.analysis_inputs import validate_state_input

    b_validation = validate_state_input(result)
    if not b_validation.accepted:
        codes = sorted({item.code.value for item in b_validation.rejections})
        _handoff_fail(
            CaptureStateHandoffCode.INVALID_STATE_OUTPUT,
            "Produced B state input was rejected: " + ", ".join(codes),
        )
    return result
