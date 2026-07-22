"""Validation for Person C Phase C1 controlled-world layouts."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from mineocclude.contracts.identity import SCHEMA_VERSION
from mineocclude.data.capture_contract import PERSON_C_CONTRACT_VERSION


LEGACY_LAYOUT_SCHEMA_VERSION = "0.1"
LEGACY_LAYOUT_CONFIG_VERSION = "person-c-layout-config-v0.1"
LAYOUT_SCHEMA_VERSION = "0.2"
LAYOUT_CONFIG_VERSION = "person-c-layout-config-v0.2"
RUNTIME_EVIDENCE_REQUIRED = "RUNTIME EVIDENCE REQUIRED LATER"

EXPECTED_LAYOUT_IDS = (
    "layout_01",
    "layout_02",
    "layout_03",
    "layout_04",
    "layout_05",
    "layout_06",
)

EXPECTED_CONDITIONS = {
    "core": {"wall_count": 1, "target_count": 1},
    "no_wall_visible": {"wall_count": 0, "target_count": 1},
    "occluder_only_no_sheep": {"wall_count": 1, "target_count": 0},
}

CONDITION_FIELDS = frozenset(
    {
        "condition",
        "identity_source",
        "wall_count",
        "wall_present",
        "target_count",
        "target",
    }
)

MARKER_COUNT = 4
CANONICAL_MARKER_ROLES = frozenset(
    {"north_west", "north_east", "south_east", "south_west"}
)
FORBIDDEN_MARKER_COLORS = frozenset({"magenta"})
RUNTIME_EVIDENCE_FIELDS = (
    "reference_screenshot",
    "minecraft_launch_manifest",
    "coordinate_check",
    "clean_reconstruction",
    "second_operator_reconstruction",
)


class LayoutRejectionCode(str, Enum):
    """Stable C1 layout rejection codes."""

    MISSING_REQUIRED_FIELD = "missing_required_field"
    INVALID_SCHEMA_VERSION = "invalid_schema_version"
    INVALID_LAYOUT_SCHEMA_VERSION = "invalid_layout_schema_version"
    INVALID_LAYOUT_COUNT = "invalid_layout_count"
    INVALID_LAYOUT_ID = "invalid_layout_id"
    DUPLICATE_LAYOUT_ID = "duplicate_layout_id"
    INVALID_GEOMETRY = "invalid_geometry"
    INVALID_MARKER_COUNT = "invalid_marker_count"
    DUPLICATE_MARKER = "duplicate_marker"
    FORBIDDEN_MARKER_COLOR = "forbidden_marker_color"
    INVALID_TARGET_COUNT = "invalid_target_count"
    INVALID_CONDITION = "invalid_condition"
    CONDITION_NOT_EXPLICIT = "condition_not_explicit"
    INVALID_RUNTIME_EVIDENCE = "invalid_runtime_evidence"


@dataclass(frozen=True)
class LayoutRejection:
    """One immutable layout rejection."""

    code: LayoutRejectionCode
    message: str


@dataclass(frozen=True)
class LayoutValidationResult:
    """Validation result for one layouts document."""

    accepted: bool
    rejections: tuple[LayoutRejection, ...]


def load_layout_config(path: str | Path) -> Any:
    """Load the dependency-free JSON-compatible YAML layout document."""

    return json.loads(Path(path).read_text(encoding="utf-8"))


def _reject(
    rejections: list[LayoutRejection],
    code: LayoutRejectionCode,
    message: str,
) -> None:
    rejections.append(LayoutRejection(code=code, message=message))


def _is_non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_finite_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _duplicates(values: Sequence[Any]) -> bool:
    try:
        return len(values) != len(set(values))
    except TypeError:
        return True


def _required_mapping(
    value: Mapping[str, Any],
    field: str,
    label: str,
    rejections: list[LayoutRejection],
) -> Mapping[str, Any] | None:
    item = value.get(field)
    if not isinstance(item, Mapping):
        _reject(
            rejections,
            LayoutRejectionCode.MISSING_REQUIRED_FIELD,
            f"{label}.{field} must be a mapping.",
        )
        return None
    return item


def _bounds_are_valid(
    bounds: Mapping[str, Any],
    *,
    include_y: bool = False,
) -> bool:
    fields = ["min_x", "max_x", "min_z", "max_z"]
    if include_y:
        fields.extend(("min_y", "max_y"))
    if any(not _is_integer(bounds.get(field)) for field in fields):
        return False
    if bounds["min_x"] > bounds["max_x"]:
        return False
    if bounds["min_z"] > bounds["max_z"]:
        return False
    if include_y and bounds["min_y"] > bounds["max_y"]:
        return False
    return all(
        -30_000_000 <= bounds[field] <= 30_000_000
        for field in fields
        if field not in {"min_y", "max_y"}
    ) and (
        not include_y
        or 0 <= bounds["min_y"] <= 255
        and 0 <= bounds["max_y"] <= 255
    )


def _inside_arena(
    bounds: Mapping[str, Any],
    arena: Mapping[str, Any],
) -> bool:
    return (
        arena["min_x"] <= bounds["min_x"] <= bounds["max_x"] <= arena["max_x"]
        and arena["min_z"]
        <= bounds["min_z"]
        <= bounds["max_z"]
        <= arena["max_z"]
    )


def _validate_conditions(
    document: Mapping[str, Any],
    rejections: list[LayoutRejection],
) -> None:
    conditions = document.get("conditions")
    if not isinstance(conditions, list):
        _reject(
            rejections,
            LayoutRejectionCode.MISSING_REQUIRED_FIELD,
            "conditions must be a list.",
        )
        return

    by_name: dict[str, Mapping[str, Any]] = {}
    for index, condition in enumerate(conditions):
        label = f"conditions[{index}]"
        if not isinstance(condition, Mapping):
            _reject(
                rejections,
                LayoutRejectionCode.INVALID_CONDITION,
                f"{label} must be a mapping.",
            )
            continue
        name = condition.get("condition")
        if not _is_non_empty_string(name):
            _reject(
                rejections,
                LayoutRejectionCode.CONDITION_NOT_EXPLICIT,
                f"{label} requires an explicit condition field.",
            )
            continue
        if name in by_name:
            _reject(
                rejections,
                LayoutRejectionCode.INVALID_CONDITION,
                f"Duplicate condition {name!r}.",
            )
            continue
        by_name[name] = condition
        if condition.get("identity_source") != "explicit_condition_field":
            _reject(
                rejections,
                LayoutRejectionCode.CONDITION_NOT_EXPLICIT,
                f"Condition {name!r} cannot be inferred from paths or images.",
            )
        if any(
            key in condition
            for key in ("path", "folder", "screenshot", "inferred_from")
        ):
            _reject(
                rejections,
                LayoutRejectionCode.CONDITION_NOT_EXPLICIT,
                f"Condition {name!r} contains an inference source.",
            )
        unexpected = set(condition).difference(CONDITION_FIELDS)
        if unexpected:
            _reject(
                rejections,
                LayoutRejectionCode.INVALID_CONDITION,
                f"Condition {name!r} contains non-variant overrides: "
                + ", ".join(sorted(unexpected)),
            )

    if set(by_name) != set(EXPECTED_CONDITIONS):
        _reject(
            rejections,
            LayoutRejectionCode.INVALID_CONDITION,
            "The three frozen C1 condition values must appear exactly once.",
        )

    for name, expected in EXPECTED_CONDITIONS.items():
        condition = by_name.get(name)
        if condition is None:
            continue
        wall_count = condition.get("wall_count")
        target_count = condition.get("target_count")
        if (
            not _is_integer(wall_count)
            or wall_count != expected["wall_count"]
        ):
            _reject(
                rejections,
                LayoutRejectionCode.INVALID_TARGET_COUNT,
                f"Condition {name!r} has the wrong wall_count.",
            )
        if (
            not _is_integer(target_count)
            or target_count != expected["target_count"]
        ):
            _reject(
                rejections,
                LayoutRejectionCode.INVALID_TARGET_COUNT,
                f"Condition {name!r} has the wrong target_count.",
            )
        expected_wall_present = expected["wall_count"] == 1
        if condition.get("wall_present") is not expected_wall_present:
            _reject(
                rejections,
                LayoutRejectionCode.INVALID_TARGET_COUNT,
                f"Condition {name!r} has inconsistent wall presence.",
            )

        target = condition.get("target")
        if expected["target_count"] == 0:
            if target is not None:
                _reject(
                    rejections,
                    LayoutRejectionCode.INVALID_TARGET_COUNT,
                    f"Condition {name!r} must not define a sheep target.",
                )
            continue
        if not isinstance(target, Mapping):
            _reject(
                rejections,
                LayoutRejectionCode.INVALID_TARGET_COUNT,
                f"Condition {name!r} requires one target specification.",
            )
            continue
        required_target = {
            "entity_type": "minecraft:sheep",
            "color_id": 2,
            "color_name": "magenta",
            "no_ai": True,
            "silent": True,
            "persistence_required": True,
        }
        if any(target.get(field) != value for field, value in required_target.items()):
            _reject(
                rejections,
                LayoutRejectionCode.INVALID_TARGET_COUNT,
                f"Condition {name!r} does not define the canonical magenta sheep.",
            )

    core = by_name.get("core")
    no_wall = by_name.get("no_wall_visible")
    if core is not None and no_wall is not None:
        if core.get("target") != no_wall.get("target"):
            _reject(
                rejections,
                LayoutRejectionCode.INVALID_TARGET_COUNT,
                "core and no_wall_visible must use the identical sheep target.",
            )


def _validate_arena(
    layout_id: str,
    arena: Mapping[str, Any],
    rejections: list[LayoutRejection],
) -> bool:
    if not _bounds_are_valid(arena) or not _is_integer(arena.get("floor_y")):
        _reject(
            rejections,
            LayoutRejectionCode.INVALID_GEOMETRY,
            f"{layout_id}.arena has invalid bounds or floor_y.",
        )
        return False
    width = arena["max_x"] - arena["min_x"] + 1
    depth = arena["max_z"] - arena["min_z"] + 1
    if width != 40 or depth != 20 or not 0 <= arena["floor_y"] <= 254:
        _reject(
            rejections,
            LayoutRejectionCode.INVALID_GEOMETRY,
            f"{layout_id}.arena must be exactly 40x20 with a valid floor.",
        )
        return False
    return True


def _validate_wall_and_lane(
    layout_id: str,
    layout: Mapping[str, Any],
    arena: Mapping[str, Any],
    rejections: list[LayoutRejection],
) -> tuple[Mapping[str, Any] | None, Mapping[str, Any] | None]:
    wall = _required_mapping(layout, "wall", layout_id, rejections)
    lane = _required_mapping(layout, "lane", layout_id, rejections)
    if wall is None or lane is None:
        return wall, lane
    axis = wall.get("axis")
    wall_valid = (
        axis in {"x", "z"}
        and wall.get("block") == "minecraft:stone"
        and wall.get("height_blocks") == 3
        and _bounds_are_valid(wall, include_y=True)
        and _inside_arena(wall, arena)
        and wall["min_y"] == arena["floor_y"] + 1
        and wall["max_y"] == wall["min_y"] + 2
    )
    if axis == "x" and wall_valid:
        wall_valid = wall["min_z"] == wall["max_z"] and wall["min_x"] < wall["max_x"]
    elif axis == "z" and wall_valid:
        wall_valid = wall["min_x"] == wall["max_x"] and wall["min_z"] < wall["max_z"]
    if not wall_valid:
        _reject(
            rejections,
            LayoutRejectionCode.INVALID_GEOMETRY,
            f"{layout_id}.wall must be a three-block-high axis-aligned stone wall.",
        )

    lane_valid = (
        lane.get("axis") == axis
        and _is_integer(lane.get("fixed_coordinate_blocks"))
        and _is_integer(lane.get("min_scalar_blocks"))
        and _is_integer(lane.get("max_scalar_blocks"))
        and _is_integer(lane.get("y_blocks"))
        and lane.get("width_blocks") == 1
        and lane["min_scalar_blocks"] < lane["max_scalar_blocks"]
        and lane["y_blocks"] == arena["floor_y"] + 1
    )
    if lane_valid and axis == "x":
        lane_valid = (
            arena["min_x"] <= lane["min_scalar_blocks"]
            < lane["max_scalar_blocks"] <= arena["max_x"]
            and arena["min_z"] <= lane["fixed_coordinate_blocks"] <= arena["max_z"]
        )
    elif lane_valid and axis == "z":
        lane_valid = (
            arena["min_z"] <= lane["min_scalar_blocks"]
            < lane["max_scalar_blocks"] <= arena["max_z"]
            and arena["min_x"] <= lane["fixed_coordinate_blocks"] <= arena["max_x"]
        )
    if not lane_valid:
        _reject(
            rejections,
            LayoutRejectionCode.INVALID_GEOMETRY,
            f"{layout_id}.lane must be inside and parallel to the wall.",
        )
    return wall, lane


def _validate_regions(
    layout_id: str,
    layout: Mapping[str, Any],
    arena: Mapping[str, Any],
    lane: Mapping[str, Any] | None,
    rejections: list[LayoutRejection],
) -> None:
    regions: dict[str, Mapping[str, Any]] = {}
    for field in ("shadow", "sheep_start_region", "reset_area", "safe_area"):
        region = _required_mapping(layout, field, layout_id, rejections)
        if region is None:
            continue
        regions[field] = region
        include_y = field == "sheep_start_region"
        if (
            not _bounds_are_valid(region, include_y=include_y)
            or not _inside_arena(region, arena)
        ):
            _reject(
                rejections,
                LayoutRejectionCode.INVALID_GEOMETRY,
                f"{layout_id}.{field} must be an ordered region inside the arena.",
            )

    if lane is None or lane.get("axis") not in {"x", "z"}:
        return
    axis = lane["axis"]
    fixed = lane.get("fixed_coordinate_blocks")
    shadow = regions.get("shadow")
    start = regions.get("sheep_start_region")
    if shadow is not None and _bounds_are_valid(shadow):
        fixed_inside = (
            shadow["min_z"] <= fixed <= shadow["max_z"]
            if axis == "x"
            else shadow["min_x"] <= fixed <= shadow["max_x"]
        )
        if not fixed_inside:
            _reject(
                rejections,
                LayoutRejectionCode.INVALID_GEOMETRY,
                f"{layout_id}.shadow must intersect the motion lane.",
            )
    if start is not None and _bounds_are_valid(start, include_y=True):
        fixed_inside = (
            start["min_z"] <= fixed <= start["max_z"]
            if axis == "x"
            else start["min_x"] <= fixed <= start["max_x"]
        )
        if not fixed_inside or start["min_y"] != arena["floor_y"] + 1:
            _reject(
                rejections,
                LayoutRejectionCode.INVALID_GEOMETRY,
                f"{layout_id}.sheep_start_region must lie on the motion lane.",
            )

    if (
        shadow is None
        or start is None
        or not _bounds_are_valid(shadow)
        or not _bounds_are_valid(start, include_y=True)
    ):
        return
    motion_sign = layout.get("motion_sign")
    scalar_min = "min_x" if axis == "x" else "min_z"
    scalar_max = "max_x" if axis == "x" else "max_z"
    path_enters_and_exits = (
        start[scalar_max] < shadow[scalar_min]
        and shadow[scalar_max] < lane["max_scalar_blocks"]
        if motion_sign == 1
        else start[scalar_min] > shadow[scalar_max]
        and shadow[scalar_min] > lane["min_scalar_blocks"]
    )
    if not path_enters_and_exits:
        _reject(
            rejections,
            LayoutRejectionCode.INVALID_GEOMETRY,
            f"{layout_id} motion must enter and exit the shadow in motion_sign order.",
        )


def _valid_position(position: Any) -> bool:
    return (
        isinstance(position, Mapping)
        and all(_is_finite_number(position.get(axis)) for axis in ("x", "y", "z"))
        and -30_000_000 <= position["x"] <= 30_000_000
        and 0 <= position["y"] <= 256
        and -30_000_000 <= position["z"] <= 30_000_000
    )


def _valid_rotation(rotation: Any) -> bool:
    return (
        isinstance(rotation, Mapping)
        and all(_is_finite_number(rotation.get(axis)) for axis in ("yaw", "pitch", "roll"))
        and -180 <= rotation["yaw"] <= 180
        and -90 <= rotation["pitch"] <= 90
        and rotation["roll"] == 0
    )


def _validate_camera(
    layout_id: str,
    layout: Mapping[str, Any],
    rejections: list[LayoutRejection],
) -> None:
    camera = _required_mapping(layout, "camera", layout_id, rejections)
    pose = _required_mapping(layout, "canonical_pose", layout_id, rejections)
    if camera is None or pose is None:
        return
    anchor = camera.get("anchor_world_blocks")
    anchor_valid = (
        isinstance(anchor, Mapping)
        and all(_is_integer(anchor.get(axis)) for axis in ("x", "y", "z"))
    )
    if (
        not anchor_valid
        or not _valid_position(camera.get("position_blocks"))
        or not _valid_rotation(camera.get("rotation_degrees"))
    ):
        _reject(
            rejections,
            LayoutRejectionCode.INVALID_GEOMETRY,
            f"{layout_id}.camera has invalid coordinates or rotation.",
        )
    if (
        pose.get("pose_id") != f"{layout_id}_canonical_pose_v1"
        or pose.get("position_blocks") != camera.get("position_blocks")
        or pose.get("rotation_degrees") != camera.get("rotation_degrees")
        or not _is_finite_number(pose.get("fov_degrees"))
        or not 30 <= pose.get("fov_degrees", -1) <= 110
    ):
        _reject(
            rejections,
            LayoutRejectionCode.INVALID_GEOMETRY,
            f"{layout_id}.canonical_pose must exactly reproduce the camera pose.",
        )


def _validate_markers(
    layout_id: str,
    layout: Mapping[str, Any],
    arena: Mapping[str, Any],
    rejections: list[LayoutRejection],
) -> None:
    markers = layout.get("markers")
    if not isinstance(markers, list) or len(markers) != MARKER_COUNT:
        _reject(
            rejections,
            LayoutRejectionCode.INVALID_MARKER_COUNT,
            f"{layout_id} must define exactly four markers.",
        )
        return
    marker_ids: list[Any] = []
    marker_roles: list[Any] = []
    coordinates: list[tuple[Any, Any, Any]] = []
    for index, marker in enumerate(markers):
        label = f"{layout_id}.markers[{index}]"
        if not isinstance(marker, Mapping):
            _reject(
                rejections,
                LayoutRejectionCode.INVALID_GEOMETRY,
                f"{label} must be a mapping.",
            )
            continue
        marker_ids.append(marker.get("marker_id"))
        marker_roles.append(marker.get("marker_role"))
        coordinate = marker.get("world_blocks")
        if isinstance(coordinate, Mapping):
            coordinates.append(
                (coordinate.get("x"), coordinate.get("y"), coordinate.get("z"))
            )
        color = marker.get("color")
        block = marker.get("block")
        if (
            not _is_non_empty_string(color)
            or color.lower() in FORBIDDEN_MARKER_COLORS
            or not _is_non_empty_string(block)
            or "magenta" in block.lower()
        ):
            _reject(
                rejections,
                LayoutRejectionCode.FORBIDDEN_MARKER_COLOR,
                f"{label} must use a non-magenta marker.",
            )
        if (
            not isinstance(coordinate, Mapping)
            or any(not _is_integer(coordinate.get(axis)) for axis in ("x", "y", "z"))
            or not arena["min_x"] <= coordinate.get("x", -31_000_000) <= arena["max_x"]
            or not arena["min_z"] <= coordinate.get("z", -31_000_000) <= arena["max_z"]
            or coordinate.get("y") != arena["floor_y"] + 1
        ):
            _reject(
                rejections,
                LayoutRejectionCode.INVALID_GEOMETRY,
                f"{label} must have one valid ground coordinate inside the arena.",
            )
        if marker.get("intended_visible") is not True:
            _reject(
                rejections,
                LayoutRejectionCode.INVALID_GEOMETRY,
                f"{label} must be declared intended-visible.",
            )
        if marker.get("visibility_evidence") != RUNTIME_EVIDENCE_REQUIRED:
            _reject(
                rejections,
                LayoutRejectionCode.INVALID_RUNTIME_EVIDENCE,
                f"{label} cannot claim unverified marker visibility.",
            )
    if _duplicates(marker_ids) or _duplicates(coordinates):
        _reject(
            rejections,
            LayoutRejectionCode.DUPLICATE_MARKER,
            f"{layout_id} marker IDs and coordinates must be unique.",
        )
    if set(marker_roles) != CANONICAL_MARKER_ROLES or _duplicates(marker_roles):
        _reject(
            rejections,
            LayoutRejectionCode.INVALID_GEOMETRY,
            f"{layout_id} must map its four stable marker IDs to each canonical "
            "geometric role exactly once.",
        )


def _validate_scalar_axis(
    layout_id: str,
    layout: Mapping[str, Any],
    lane: Mapping[str, Any] | None,
    rejections: list[LayoutRejection],
) -> None:
    scalar = _required_mapping(layout, "scalar_axis", layout_id, rejections)
    if scalar is None or lane is None:
        return
    axis = lane.get("axis")
    expected_direction = "+x" if axis == "x" else "+z"
    if (
        scalar.get("world_axis") != axis
        or scalar.get("positive_world_direction") != expected_direction
        or scalar.get("unit") != "blocks"
        or not _is_integer(scalar.get("origin_world_coordinate_blocks"))
    ):
        _reject(
            rejections,
            LayoutRejectionCode.INVALID_GEOMETRY,
            f"{layout_id}.scalar_axis must explicitly map the wall-parallel world axis.",
        )


def _validate_runtime_evidence(
    layout_id: str,
    layout: Mapping[str, Any],
    rejections: list[LayoutRejection],
) -> None:
    evidence = layout.get("runtime_evidence")
    if not isinstance(evidence, Mapping):
        _reject(
            rejections,
            LayoutRejectionCode.INVALID_RUNTIME_EVIDENCE,
            f"{layout_id}.runtime_evidence must be explicit.",
        )
        return
    for field in RUNTIME_EVIDENCE_FIELDS:
        if evidence.get(field) != RUNTIME_EVIDENCE_REQUIRED:
            _reject(
                rejections,
                LayoutRejectionCode.INVALID_RUNTIME_EVIDENCE,
                f"{layout_id}.{field} must remain marked for later runtime evidence.",
            )


def _validate_layout(
    layout: Mapping[str, Any],
    rejections: list[LayoutRejection],
) -> None:
    layout_id = layout.get("layout_id")
    label = layout_id if _is_non_empty_string(layout_id) else "layout"
    required = (
        "layout_id",
        "config_version",
        "arena",
        "wall",
        "lane",
        "sheep_start_region",
        "shadow",
        "motion_sign",
        "scalar_axis",
        "camera",
        "canonical_pose",
        "markers",
        "reset_area",
        "safe_area",
        "runtime_evidence",
    )
    missing = [field for field in required if field not in layout]
    if missing:
        _reject(
            rejections,
            LayoutRejectionCode.MISSING_REQUIRED_FIELD,
            f"{label} is missing: " + ", ".join(missing),
        )
        return
    if layout["config_version"] != LAYOUT_CONFIG_VERSION:
        _reject(
            rejections,
            LayoutRejectionCode.INVALID_LAYOUT_SCHEMA_VERSION,
            f"{label} has the wrong config_version.",
        )
    if not _is_integer(layout["motion_sign"]) or layout["motion_sign"] not in {-1, 1}:
        _reject(
            rejections,
            LayoutRejectionCode.INVALID_GEOMETRY,
            f"{label}.motion_sign must be -1 or 1.",
        )

    arena = _required_mapping(layout, "arena", label, rejections)
    if arena is None or not _validate_arena(label, arena, rejections):
        return
    _, lane = _validate_wall_and_lane(label, layout, arena, rejections)
    _validate_regions(label, layout, arena, lane, rejections)
    _validate_camera(label, layout, rejections)
    _validate_markers(label, layout, arena, rejections)
    _validate_scalar_axis(label, layout, lane, rejections)
    _validate_runtime_evidence(label, layout, rejections)


def validate_layout_config(document: Mapping[str, Any]) -> LayoutValidationResult:
    """Validate six C1 layouts without mutating the supplied document."""

    rejections: list[LayoutRejection] = []
    if not isinstance(document, Mapping):
        _reject(
            rejections,
            LayoutRejectionCode.MISSING_REQUIRED_FIELD,
            "Layout document must be a mapping.",
        )
        return LayoutValidationResult(False, tuple(rejections))

    required = (
        "schema_version",
        "person_c_contract_version",
        "layout_schema_version",
        "config_version",
        "common_arena_grammar",
        "conditions",
        "layouts",
    )
    missing = [field for field in required if field not in document]
    if missing:
        _reject(
            rejections,
            LayoutRejectionCode.MISSING_REQUIRED_FIELD,
            "Layout document is missing: " + ", ".join(missing),
        )
        return LayoutValidationResult(False, tuple(rejections))

    if document["schema_version"] != SCHEMA_VERSION:
        _reject(
            rejections,
            LayoutRejectionCode.INVALID_SCHEMA_VERSION,
            "Layouts must preserve shared schema_version '1.0'.",
        )
    if (
        document["person_c_contract_version"] != PERSON_C_CONTRACT_VERSION
        or document["layout_schema_version"] != LAYOUT_SCHEMA_VERSION
        or document["config_version"] != LAYOUT_CONFIG_VERSION
    ):
        _reject(
            rejections,
            LayoutRejectionCode.INVALID_LAYOUT_SCHEMA_VERSION,
            "Person C/layout/config versions do not match C1 layout v0.2.",
        )

    grammar = document["common_arena_grammar"]
    if not isinstance(grammar, Mapping) or any(
        grammar.get(field) != value
        for field, value in {
            "world_type": "superflat",
            "arena_width_blocks": 40,
            "arena_depth_blocks": 20,
            "wall_height_blocks": 3,
            "wall_block": "minecraft:stone",
            "marker_count": 4,
            "coordinate_system": "minecraft_world_x_y_z",
            "scalar_axis_unit": "blocks",
        }.items()
    ):
        _reject(
            rejections,
            LayoutRejectionCode.INVALID_GEOMETRY,
            "common_arena_grammar does not match the frozen C1 grammar.",
        )

    _validate_conditions(document, rejections)

    layouts = document["layouts"]
    if not isinstance(layouts, list):
        _reject(
            rejections,
            LayoutRejectionCode.INVALID_LAYOUT_COUNT,
            "layouts must be a list of six entries.",
        )
        return LayoutValidationResult(False, tuple(rejections))
    if len(layouts) != len(EXPECTED_LAYOUT_IDS):
        _reject(
            rejections,
            LayoutRejectionCode.INVALID_LAYOUT_COUNT,
            "Exactly six layouts are required.",
        )

    layout_ids = [
        layout.get("layout_id") if isinstance(layout, Mapping) else None
        for layout in layouts
    ]
    if _duplicates(layout_ids):
        _reject(
            rejections,
            LayoutRejectionCode.DUPLICATE_LAYOUT_ID,
            "layout_id values must be unique.",
        )
    if set(value for value in layout_ids if isinstance(value, str)) != set(
        EXPECTED_LAYOUT_IDS
    ):
        _reject(
            rejections,
            LayoutRejectionCode.INVALID_LAYOUT_ID,
            "The six stable IDs must be layout_01 through layout_06.",
        )

    for layout in layouts:
        if not isinstance(layout, Mapping):
            _reject(
                rejections,
                LayoutRejectionCode.INVALID_GEOMETRY,
                "Each layout must be a mapping.",
            )
            continue
        _validate_layout(layout, rejections)

    return LayoutValidationResult(
        accepted=not rejections,
        rejections=tuple(rejections),
    )
