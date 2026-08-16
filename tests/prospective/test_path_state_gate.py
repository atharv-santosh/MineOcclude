import copy
import hashlib

import numpy as np
import pytest

from mineocclude.prospective.path_state_gate import CHECKS, check_pair, check_unit


def _digest(values):
    return hashlib.sha256(np.asarray(values, dtype="<f8").tobytes()).hexdigest()


def _rows(n=180, scene="NORMAL", speed=2.0, direction="LEFT_TO_RIGHT"):
    sign = 1.0 if direction == "LEFT_TO_RIGHT" else -1.0
    start = -7.8 if sign > 0 else 7.8
    return [
        {
            "scientific_run_id": "run-a",
            "episode_id": 17,
            "server_tick": i,
            "render_frame_idx": i,
            "action_idx": i,
            "model_frame_idx": i,
            "sheep_x": start + sign * speed * 0.05 * i,
            "sheep_y": 4.0,
            "sheep_z": 6.0,
            "scene": scene,
            "seed": 12345,
            "noise_seed": 67890,
            "noise_draw": (i % 7 - 3) * 0.001,
            "spec_hash": "abc",
            "trajectory_spec_id": "t01",
            "q": 0.05,
            "v": sign * speed,
            "commanded_v": sign * speed,
            "target_respawn_count": 0,
            "target_entity_uuid": "uuid-1",
            "player_x": 0.5,
            "player_y": 5.620000004768372,
            "player_z": -5.5,
            "player_yaw": 0.0,
            "player_pitch": 0.0,
            "fov_degrees": 70.0,
        }
        for i in range(n)
    ]


def _spec(rows, speed=2.0, direction="LEFT_TO_RIGHT"):
    return {
        "scientific_run_id": "run-a",
        "episode_id": 17,
        "trajectory_spec_id": "t01",
        "seed": 12345,
        "noise_seed": 67890,
        "spec_hash": "abc",
        "expected_scenes": ["NORMAL", "NO_WALL"],
        "direction": direction,
        "speed_blocks_per_second": speed,
        "motion_noise_q": 0.05,
        "expected_max_frames": len(rows),
        "expected_index_mapping": [
            {
                "server_tick": i,
                "render_frame_idx": i,
                "action_idx": i,
                "model_frame_idx": i,
            }
            for i in range(len(rows))
        ],
        "start_world_xyz": [rows[0]["sheep_x"], 4.0, 6.0],
        "target_server_ticks": list(range(40, 59)),
        "target_entity_uuid": "uuid-1",
        "target_respawn_count": 0,
        "camera_eye_world_xyz": [0.5, 5.6200000048, -5.5],
        "camera_yaw_degrees": 0.0,
        "camera_pitch_degrees": 0.0,
        "fov_degrees": 70.0,
        "expected_path_sha256": _digest([row["sheep_x"] for row in rows]),
        "expected_noise_schedule_sha256": _digest([row["noise_draw"] for row in rows]),
    }


def test_gate_scope_covers_every_declared_and_review_required_field():
    covered = {check.authority_field for check in CHECKS}
    declared = {
        "trajectory_spec_id", "seed", "noise_seed", "direction",
        "speed_blocks_per_second", "motion_noise_q", "noise schedule", "start state",
        "target tick IDs and order", "camera/FOV", "capture cadence",
        "frame/action/server-tick identity", "world x/y/z", "episode/spec identity",
        "scene identity", "target identity",
    }
    assert declared <= covered


def test_clean_unit_passes_and_exposes_exact_mapping():
    rows = _rows()
    result = check_unit("u", rows, _spec(rows), "NORMAL")
    assert result.passed, result.failures
    assert result.rows_checked == 180
    assert result.details["observed_index_mapping"][5] == {
        "server_tick": 5, "render_frame_idx": 5, "action_idx": 5, "model_frame_idx": 5
    }


def test_camera_eye_rounding_difference_is_benign():
    rows = _rows()
    assert "camera_eye_position" not in check_unit("u", rows, _spec(rows), "NORMAL").failures


def test_signed_velocity_uses_direction_and_unsigned_speed_magnitude():
    rows = _rows(direction="RIGHT_TO_LEFT")
    assert check_unit("u", rows, _spec(rows, direction="RIGHT_TO_LEFT"), "NORMAL").passed


@pytest.mark.parametrize(
    "mutation,expected",
    [
        (lambda rows: rows[5].update(scientific_run_id="wrong"), "scientific_run_id"),
        (lambda rows: rows[5].update(episode_id=99), "episode_id"),
        (lambda rows: rows[5].update(trajectory_spec_id="wrong"), "trajectory_spec_id"),
        (lambda rows: rows[5].update(seed=999), "seed"),
        (lambda rows: rows[5].update(noise_seed=999), "noise_seed"),
        (lambda rows: rows[5].update(spec_hash="wrong"), "spec_hash"),
        (lambda rows: rows[5].update(v=-2.0), "direction_sign"),
        (lambda rows: rows[5].update(v=3.0), "speed_magnitude"),
        (lambda rows: rows[5].update(commanded_v=0.0), "commanded_velocity_agrees"),
        (lambda rows: rows[5].update(q=0.09), "motion_noise_q"),
        (lambda rows: rows[5].update(noise_draw=0.9), "noise_schedule"),
        (lambda rows: rows[5].update(scene="NO_WALL"), "scene_identity"),
        (lambda rows: rows[5].update(server_tick=99), "frame_action_server_tick_mapping"),
        (lambda rows: rows[5].update(render_frame_idx=99), "frame_action_server_tick_mapping"),
        (lambda rows: rows[5].update(action_idx=99), "frame_action_server_tick_mapping"),
        (lambda rows: rows[5].update(model_frame_idx=99), "frame_action_server_tick_mapping"),
        (lambda rows: rows[5].update(sheep_x=12.0), "world_x_sha256"),
        (lambda rows: rows[5].update(sheep_y=4.5), "world_y_constant"),
        (lambda rows: rows[5].update(sheep_z=6.5), "world_z_constant"),
        (lambda rows: rows[5].update(player_x=0.6), "camera_eye_position"),
        (lambda rows: rows[5].update(player_y=rows[5]["player_y"] + 1e-10), "camera_bitwise_constant"),
        (lambda rows: rows[5].update(player_yaw=10.0), "camera_yaw"),
        (lambda rows: rows[5].update(player_pitch=10.0), "camera_pitch"),
        (lambda rows: rows[5].update(fov_degrees=90.0), "camera_fov"),
        (lambda rows: rows[5].update(target_entity_uuid="other"), "target_identity"),
        (lambda rows: rows[5].update(target_respawn_count=1), "target_identity"),
    ],
)
def test_each_declared_invariant_mutation_fails_independently(mutation, expected):
    rows = _rows()
    spec = _spec(rows)
    mutated = copy.deepcopy(rows)
    mutation(mutated)
    result = check_unit("u", mutated, spec, "NORMAL")
    assert not result.passed
    assert expected in result.failures


def test_row_deletion_and_missing_fields_fail_closed():
    rows = _rows()
    spec = _spec(rows)
    assert "row_count" in check_unit("u", rows[:-1], spec, "NORMAL").failures
    broken = copy.deepcopy(rows)
    broken[0].pop("player_yaw")
    assert "missing_row_fields" in check_unit("u", broken, spec, "NORMAL").failures


def test_invalid_direction_and_nonfinite_values_fail_closed():
    rows = _rows()
    spec = _spec(rows)
    spec["direction"] = "SIDEWAYS"
    assert "direction_domain" in check_unit("u", rows, spec, "NORMAL").failures
    rows[2]["sheep_x"] = np.nan
    assert "non_finite_or_invalid_numeric_field" in check_unit("u", rows, _spec(_rows()), "NORMAL").failures


@pytest.mark.parametrize(
    "field,bad,also_rows",
    [
        ("episode_id", True, True),
        ("seed", "12345", True),
        ("expected_max_frames", 180.0, False),
        ("target_respawn_count", True, False),
        ("scientific_run_id", True, True),
        ("noise_seed", False, True),
        ("trajectory_spec_id", 17, True),
        ("speed_blocks_per_second", np.inf, False),
        ("motion_noise_q", np.nan, False),
        ("camera_yaw_degrees", "0", False),
        ("fov_degrees", 181.0, False),
        ("expected_path_sha256", "not-a-digest", False),
    ],
)
def test_wrong_typed_or_out_of_domain_authority_fields_never_pass(field, bad, also_rows):
    rows = _rows()
    spec = _spec(rows)
    spec[field] = bad
    if also_rows:
        for row in rows:
            row[field] = bad
    result = check_unit("u", rows, spec, "NORMAL")
    assert not result.passed
    assert "invalid_spec_fields" in result.failures
    assert field in result.details["invalid_spec_fields"]


def test_float_index_in_authority_mapping_never_passes():
    rows = _rows()
    spec = _spec(rows)
    spec["expected_index_mapping"][0]["server_tick"] = 0.0
    result = check_unit("u", rows, spec, "NORMAL")
    assert not result.passed
    assert "expected_index_mapping" in result.details["invalid_spec_fields"]


def test_wrong_typed_row_identity_never_passes_even_if_other_values_match():
    rows = _rows()
    spec = _spec(rows)
    rows[0]["episode_id"] = True
    result = check_unit("u", rows, spec, "NORMAL")
    assert not result.passed
    assert result.details["invalid_row_fields"][0] == ["episode_id"]


def test_unknown_scene_fails_closed_even_when_rows_repeat_it():
    rows = _rows(scene="UNKNOWN")
    spec = _spec(rows)
    assert "scene_identity" in check_unit("u", rows, spec, "UNKNOWN").failures


def test_target_ticks_must_be_ordered_unique_and_present():
    rows = _rows()
    for targets in ([45, 44, 46], [40, 40, 41], [178, 179, 180]):
        spec = _spec(rows)
        spec["target_server_ticks"] = targets
        assert "target_ticks_ordered_unique" in check_unit("u", rows, spec, "NORMAL").failures


def test_pair_requires_exact_equality_for_all_path_state_fields():
    normal = _rows(scene="NORMAL")
    nowall = _rows(scene="NO_WALL")
    spec = _spec(normal)
    ok = check_pair(spec, normal, nowall, normal_unit_id="a", nowall_unit_id="b")
    assert ok["passed"] and ok["paired_exact_equality"] and ok["epsilon_path"] == 0.0
    for field in ("sheep_x", "player_yaw", "action_idx", "noise_draw"):
        mutated = copy.deepcopy(nowall)
        value = mutated[9][field]
        mutated[9][field] = value + (1e-12 if isinstance(value, float) else 1)
        bad = check_pair(spec, normal, mutated, normal_unit_id="a", nowall_unit_id="b")
        assert not bad["paired_exact_equality"] and not bad["passed"]
