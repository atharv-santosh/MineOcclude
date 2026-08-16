"""Fail-closed future path/state gate over the complete declared scope."""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np

__all__ = ["FieldCheck", "PathStateResult", "CHECKS", "check_unit", "check_pair"]

# This is an encoding tolerance, not a scientific threshold: the historical
# authority serializes eye coordinates to 10 decimal places.
CAMERA_ROUNDING_TOLERANCE = 1e-9
VALID_DIRECTIONS = frozenset({"LEFT_TO_RIGHT", "RIGHT_TO_LEFT"})


@dataclass(frozen=True)
class FieldCheck:
    name: str
    predicate: Callable[[list[dict], dict, str], bool] | None
    authority_field: str


@dataclass
class PathStateResult:
    unit_id: str
    passed: bool
    rows_checked: int
    failures: list[str] = field(default_factory=list)
    details: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "artifact_id": "prospective-path-state-gate-result-v0.2",
            "unit_id": self.unit_id,
            "passed": self.passed,
            "rows_checked": self.rows_checked,
            "failures": self.failures,
            "details": self.details,
        }


CHECKS: tuple[FieldCheck, ...] = (
    FieldCheck("scientific_run_id", None, "episode/spec identity"),
    FieldCheck("episode_id", None, "episode/spec identity"),
    FieldCheck("trajectory_spec_id", None, "trajectory_spec_id"),
    FieldCheck("seed", None, "seed"),
    FieldCheck("noise_seed", None, "noise_seed"),
    FieldCheck("spec_hash", None, "trajectory_spec_id"),
    FieldCheck("direction_sign", None, "direction"),
    FieldCheck("speed_magnitude", None, "speed_blocks_per_second"),
    FieldCheck("commanded_velocity_agrees", None, "speed_blocks_per_second"),
    FieldCheck("motion_noise_q", None, "motion_noise_q"),
    FieldCheck("noise_schedule", None, "noise schedule"),
    FieldCheck("scene_identity", None, "scene identity"),
    FieldCheck("frame_action_server_tick_mapping", None, "frame/action/server-tick identity"),
    FieldCheck("row_count", None, "capture cadence"),
    FieldCheck("start_state", None, "start state"),
    FieldCheck("world_path", None, "world x/y/z"),
    FieldCheck("camera_eye_position", None, "camera/FOV"),
    FieldCheck("camera_bitwise_constant", None, "camera/FOV"),
    FieldCheck("camera_yaw", None, "camera/FOV"),
    FieldCheck("camera_pitch", None, "camera/FOV"),
    FieldCheck("camera_fov", None, "camera/FOV"),
    FieldCheck("target_identity", None, "target identity"),
    FieldCheck("target_ticks_ordered_unique", None, "target tick IDs and order"),
)


REQUIRED_SPEC_FIELDS = {
    "scientific_run_id",
    "episode_id",
    "trajectory_spec_id",
    "seed",
    "noise_seed",
    "spec_hash",
    "expected_scenes",
    "direction",
    "speed_blocks_per_second",
    "motion_noise_q",
    "expected_index_mapping",
    "expected_max_frames",
    "start_world_xyz",
    "target_server_ticks",
    "target_entity_uuid",
    "target_respawn_count",
    "camera_eye_world_xyz",
    "camera_yaw_degrees",
    "camera_pitch_degrees",
    "fov_degrees",
    "expected_path_sha256",
    "expected_noise_schedule_sha256",
}

REQUIRED_ROW_FIELDS = {
    "scientific_run_id",
    "episode_id",
    "trajectory_spec_id",
    "seed",
    "noise_seed",
    "spec_hash",
    "scene",
    "server_tick",
    "render_frame_idx",
    "action_idx",
    "model_frame_idx",
    "sheep_x",
    "sheep_y",
    "sheep_z",
    "q",
    "noise_draw",
    "v",
    "commanded_v",
    "target_respawn_count",
    "target_entity_uuid",
    "player_x",
    "player_y",
    "player_z",
    "player_yaw",
    "player_pitch",
    "fov_degrees",
}


def _finite_number(value: object) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float, np.integer, np.floating))
        and math.isfinite(float(value))
    )


def _plain_index(value: object) -> bool:
    return type(value) is int and value >= 0


def _nonempty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _sha256_hex(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _xyz(value: object) -> bool:
    return (
        isinstance(value, (list, tuple))
        and len(value) == 3
        and all(_finite_number(component) for component in value)
    )


def _valid_index_mapping(value: object) -> bool:
    fields = {"server_tick", "render_frame_idx", "action_idx", "model_frame_idx"}
    return (
        isinstance(value, list)
        and bool(value)
        and all(
            isinstance(row, dict)
            and set(row) == fields
            and all(_plain_index(row[field]) for field in fields)
            for row in value
        )
    )


def _invalid_spec_fields(spec: dict) -> list[str]:
    validators: dict[str, Callable[[object], bool]] = {
        "scientific_run_id": _nonempty_string,
        "episode_id": _plain_index,
        "trajectory_spec_id": _nonempty_string,
        "seed": _plain_index,
        "noise_seed": _plain_index,
        "spec_hash": _nonempty_string,
        "expected_scenes": lambda value: (
            isinstance(value, (list, tuple, set, frozenset))
            and bool(value)
            and all(_nonempty_string(scene) for scene in value)
        ),
        "direction": lambda value: isinstance(value, str) and value in VALID_DIRECTIONS,
        "speed_blocks_per_second": lambda value: _finite_number(value) and float(value) > 0,
        "motion_noise_q": lambda value: _finite_number(value) and float(value) >= 0,
        "expected_index_mapping": _valid_index_mapping,
        "expected_max_frames": lambda value: _plain_index(value) and value > 0,
        "start_world_xyz": _xyz,
        "target_server_ticks": lambda value: (
            isinstance(value, list)
            and bool(value)
            and all(_plain_index(tick) for tick in value)
            and value == sorted(value)
            and len(set(value)) == len(value)
        ),
        "target_entity_uuid": _nonempty_string,
        "target_respawn_count": _plain_index,
        "camera_eye_world_xyz": _xyz,
        "camera_yaw_degrees": _finite_number,
        "camera_pitch_degrees": lambda value: (
            _finite_number(value) and -90.0 <= float(value) <= 90.0
        ),
        "fov_degrees": lambda value: (
            _finite_number(value) and 0.0 < float(value) <= 180.0
        ),
        "expected_path_sha256": _sha256_hex,
        "expected_noise_schedule_sha256": _sha256_hex,
    }
    return sorted(field for field, validate in validators.items() if not validate(spec[field]))


def _invalid_row_fields(rows: list[dict]) -> dict[int, list[str]]:
    string_fields = (
        "scientific_run_id",
        "trajectory_spec_id",
        "spec_hash",
        "scene",
        "target_entity_uuid",
    )
    integer_fields = (
        "episode_id",
        "seed",
        "noise_seed",
        "server_tick",
        "render_frame_idx",
        "action_idx",
        "model_frame_idx",
        "target_respawn_count",
    )
    numeric_fields = (
        "sheep_x",
        "sheep_y",
        "sheep_z",
        "q",
        "noise_draw",
        "v",
        "commanded_v",
        "player_x",
        "player_y",
        "player_z",
        "player_yaw",
        "player_pitch",
        "fov_degrees",
    )
    invalid: dict[int, list[str]] = {}
    for index, row in enumerate(rows):
        fields = [field for field in string_fields if not _nonempty_string(row[field])]
        fields.extend(field for field in integer_fields if not _plain_index(row[field]))
        fields.extend(field for field in numeric_fields if not _finite_number(row[field]))
        if _finite_number(row["q"]) and float(row["q"]) < 0:
            fields.append("q")
        if _finite_number(row["player_pitch"]) and not -90 <= float(row["player_pitch"]) <= 90:
            fields.append("player_pitch")
        if _finite_number(row["fov_degrees"]) and not 0 < float(row["fov_degrees"]) <= 180:
            fields.append("fov_degrees")
        if fields:
            invalid[index] = sorted(set(fields))
    return invalid


def _digest_f64(values: list[float]) -> str:
    array = np.asarray(values, dtype="<f8")
    return hashlib.sha256(array.tobytes()).hexdigest()


def _all_equal(rows: list[dict], field: str, expected: Any) -> bool:
    return all(row[field] == expected for row in rows)


def check_unit(unit_id: str, rows: list[dict], spec: dict, scene: str) -> PathStateResult:
    """Verify every declared invariant and return failure details, never a false PASS."""
    failures: list[str] = []
    missing_spec = sorted(REQUIRED_SPEC_FIELDS - set(spec))
    if missing_spec:
        failures.append("missing_spec_fields")
    missing_rows = {
        index: sorted(REQUIRED_ROW_FIELDS - set(row))
        for index, row in enumerate(rows)
        if REQUIRED_ROW_FIELDS - set(row)
    }
    if not rows:
        failures.append("empty_rows")
    if missing_rows:
        failures.append("missing_row_fields")
    if failures:
        return PathStateResult(
            unit_id,
            False,
            len(rows),
            failures,
            {"missing_spec_fields": missing_spec, "missing_row_fields": missing_rows},
        )

    invalid_spec = _invalid_spec_fields(spec)
    invalid_rows = _invalid_row_fields(rows)
    if not _nonempty_string(unit_id):
        failures.append("invalid_unit_id")
    if not _nonempty_string(scene):
        failures.append("invalid_scene_argument")
    if invalid_spec:
        failures.append("invalid_spec_fields")
    if invalid_rows:
        failures.append("invalid_row_fields")
    if "direction" in invalid_spec:
        failures.append("direction_domain")
    if "speed_blocks_per_second" in invalid_spec:
        failures.append("speed_domain")
    if "target_server_ticks" in invalid_spec:
        failures.append("target_ticks_ordered_unique")
    if any(
        field
        in {
            "sheep_x", "sheep_y", "sheep_z", "q", "noise_draw", "v",
            "commanded_v", "player_x", "player_y", "player_z", "player_yaw",
            "player_pitch", "fov_degrees",
        }
        for fields in invalid_rows.values()
        for field in fields
    ):
        failures.append("non_finite_or_invalid_numeric_field")
    if any(
        field in {"server_tick", "render_frame_idx", "action_idx", "model_frame_idx"}
        for fields in invalid_rows.values()
        for field in fields
    ):
        failures.append("invalid_index_type")
    if failures:
        return PathStateResult(
            unit_id,
            False,
            len(rows),
            failures,
            {"invalid_spec_fields": invalid_spec, "invalid_row_fields": invalid_rows},
        )

    numeric_fields = {
        "sheep_x", "sheep_y", "sheep_z", "q", "noise_draw", "v", "commanded_v",
        "player_x", "player_y", "player_z", "player_yaw", "player_pitch", "fov_degrees",
    }
    if any(not _finite_number(row[field]) for row in rows for field in numeric_fields):
        failures.append("non_finite_or_invalid_numeric_field")
    index_fields = ("server_tick", "render_frame_idx", "action_idx", "model_frame_idx")
    if any(not _plain_index(row[field]) for row in rows for field in index_fields):
        failures.append("invalid_index_type")
    if failures:
        return PathStateResult(unit_id, False, len(rows), failures, {})

    expected_constants = (
        ("scientific_run_id", "scientific_run_id"),
        ("episode_id", "episode_id"),
        ("trajectory_spec_id", "trajectory_spec_id"),
        ("seed", "seed"),
        ("noise_seed", "noise_seed"),
        ("spec_hash", "spec_hash"),
    )
    for failure, spec_field in expected_constants:
        if not _all_equal(rows, failure, spec[spec_field]):
            failures.append(failure)

    direction = spec["direction"]
    if direction not in VALID_DIRECTIONS:
        failures.append("direction_domain")
        sign = None
    else:
        sign = 1.0 if direction == "LEFT_TO_RIGHT" else -1.0
    speed = spec["speed_blocks_per_second"]
    if not _finite_number(speed) or float(speed) <= 0:
        failures.append("speed_domain")
    else:
        if sign is not None and not all(float(row["v"]) * sign > 0 for row in rows):
            failures.append("direction_sign")
        if not all(abs(float(row["v"])) == float(speed) for row in rows):
            failures.append("speed_magnitude")
    if not all(float(row["commanded_v"]) == float(row["v"]) for row in rows):
        failures.append("commanded_velocity_agrees")
    if not _finite_number(spec["motion_noise_q"]) or not all(
        float(row["q"]) == float(spec["motion_noise_q"]) for row in rows
    ):
        failures.append("motion_noise_q")

    noise_digest = _digest_f64([float(row["noise_draw"]) for row in rows])
    if noise_digest != spec["expected_noise_schedule_sha256"]:
        failures.append("noise_schedule")
    expected_scenes = spec["expected_scenes"]
    if (
        not isinstance(expected_scenes, (list, tuple, set, frozenset))
        or not expected_scenes
        or any(not isinstance(value, str) or not value for value in expected_scenes)
        or scene not in expected_scenes
        or not _all_equal(rows, "scene", scene)
    ):
        failures.append("scene_identity")

    observed_mapping = [
        {
            "server_tick": int(row["server_tick"]),
            "render_frame_idx": int(row["render_frame_idx"]),
            "action_idx": int(row["action_idx"]),
            "model_frame_idx": int(row["model_frame_idx"]),
        }
        for row in rows
    ]
    if observed_mapping != spec["expected_index_mapping"]:
        failures.append("frame_action_server_tick_mapping")
    if len(rows) != spec["expected_max_frames"] or len(rows) != len(spec["expected_index_mapping"]):
        failures.append("row_count")

    start = spec["start_world_xyz"]
    if (
        not isinstance(start, (list, tuple))
        or len(start) != 3
        or any(not _finite_number(value) for value in start)
        or any(float(rows[0][field]) != float(value) for field, value in zip(("sheep_x", "sheep_y", "sheep_z"), start))
    ):
        failures.append("start_state")
    if isinstance(start, (list, tuple)) and len(start) == 3:
        if not all(float(row["sheep_y"]) == float(start[1]) for row in rows):
            failures.append("world_y_constant")
        if not all(float(row["sheep_z"]) == float(start[2]) for row in rows):
            failures.append("world_z_constant")
    path_digest = _digest_f64([float(row["sheep_x"]) for row in rows])
    if path_digest != spec["expected_path_sha256"]:
        failures.append("world_x_sha256")

    eye = spec["camera_eye_world_xyz"]
    if (
        not isinstance(eye, (list, tuple))
        or len(eye) != 3
        or any(not _finite_number(value) for value in eye)
        or not all(
            all(
                abs(float(row[field]) - float(value)) <= CAMERA_ROUNDING_TOLERANCE
                for field, value in zip(("player_x", "player_y", "player_z"), eye)
            )
            for row in rows
        )
    ):
        failures.append("camera_eye_position")
    if len(
        {
            (
                row["player_x"], row["player_y"], row["player_z"],
                row["player_yaw"], row["player_pitch"], row["fov_degrees"],
            )
            for row in rows
        }
    ) != 1:
        failures.append("camera_bitwise_constant")
    if not all(float(row["player_yaw"]) == float(spec["camera_yaw_degrees"]) for row in rows):
        failures.append("camera_yaw")
    if not all(float(row["player_pitch"]) == float(spec["camera_pitch_degrees"]) for row in rows):
        failures.append("camera_pitch")
    if not all(float(row["fov_degrees"]) == float(spec["fov_degrees"]) for row in rows):
        failures.append("camera_fov")

    if not all(
        row["target_entity_uuid"] == spec["target_entity_uuid"]
        and row["target_entity_uuid"] not in (None, "")
        and type(row["target_respawn_count"]) is int
        and row["target_respawn_count"] == spec["target_respawn_count"]
        for row in rows
    ):
        failures.append("target_identity")
    targets = spec["target_server_ticks"]
    observed_ticks = {mapping["server_tick"] for mapping in observed_mapping}
    if (
        not isinstance(targets, list)
        or not targets
        or any(not _plain_index(value) for value in targets)
        or targets != sorted(targets)
        or len(set(targets)) != len(targets)
        or not set(targets) <= observed_ticks
    ):
        failures.append("target_ticks_ordered_unique")

    # Preserve first occurrence order while avoiding duplicate failure labels.
    failures = list(dict.fromkeys(failures))
    return PathStateResult(
        unit_id=unit_id,
        passed=not failures,
        rows_checked=len(rows),
        failures=failures,
        details={
            "observed_path_sha256": path_digest,
            "expected_path_sha256": spec["expected_path_sha256"],
            "observed_noise_schedule_sha256": noise_digest,
            "expected_noise_schedule_sha256": spec["expected_noise_schedule_sha256"],
            "observed_index_mapping": observed_mapping,
            "authority_fields_checked": sorted({check.authority_field for check in CHECKS}),
        },
    )


def check_pair(
    spec: dict,
    normal_rows: list[dict],
    nowall_rows: list[dict],
    *,
    normal_unit_id: str,
    nowall_unit_id: str,
) -> dict:
    results = {
        "NORMAL": check_unit(normal_unit_id, normal_rows, spec, "NORMAL"),
        "NO_WALL": check_unit(nowall_unit_id, nowall_rows, spec, "NO_WALL"),
    }
    paired_fields = (
        "server_tick", "render_frame_idx", "action_idx", "model_frame_idx",
        "sheep_x", "sheep_y", "sheep_z", "q", "noise_draw", "v", "commanded_v",
        "player_x", "player_y", "player_z", "player_yaw", "player_pitch", "fov_degrees",
        "trajectory_spec_id", "seed", "noise_seed", "spec_hash",
    )
    units_passed = all(result.passed for result in results.values())
    paired_equal = (
        units_passed
        and len(normal_rows) == len(nowall_rows)
        and all(
            all(
                field in normal
                and field in nowall
                and normal[field] == nowall[field]
                for field in paired_fields
            )
            for normal, nowall in zip(normal_rows, nowall_rows)
        )
    )
    return {
        "artifact_id": "prospective-path-state-pair-result-v0.2",
        "trajectory_spec_id": spec.get("trajectory_spec_id"),
        "paired_exact_equality": paired_equal,
        "paired_fields": list(paired_fields),
        "epsilon_path": 0.0,
        "rows_checked_total": sum(result.rows_checked for result in results.values()),
        "passed": paired_equal and all(result.passed for result in results.values()),
        "per_scene": {key: value.to_dict() for key, value in results.items()},
    }
