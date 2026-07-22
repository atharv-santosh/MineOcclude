"""Canonical wall-parallel coordinate contract for Person B targets."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .manifests import is_hex_digest, sha256_value


COORDINATE_FRAME_SCHEMA_VERSION = "person-b-wall-parallel-frame-v0.1"


class CoordinateContractError(ValueError):
    """Raised when wall-parallel position or direction is ambiguous."""


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
