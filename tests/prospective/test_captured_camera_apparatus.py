"""Regression coverage for the Stage-1 BLOCKED camera-apparatus repair.

The live defect: ``verify_captured_apparatus`` read ``server_state`` column
``player_y`` as the camera FEET. ``EpisodeManager`` logs that column as
``player.getEyeY()`` -- the sightline origin it hands to
``GeometryUtil.segmentHitsWall`` -- so every unit was blocked by a constant
+1.6200000047683716 (the 1.62f standing eye height) with the apparatus sitting
exactly where the frozen authority requires it.

The values below are the literal bytes of the three blocked attempts of
``a1q_ltr_wall_r01`` (collection_launch_01_20260817T072000Z); all three were
numerically identical.

A second defect in the same function is covered here too: the FOV check read
``row["fov_degrees"]``, a key no captured stream carries. FOV is a client
property -- the server reports ``fov_status: not_server_observable`` -- so it is
now verified from the per-episode client authority record.

Nothing here starts Minecraft or collects data.
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

import importlib.util

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = (ROOT / "docs/status/integration/regime_a_prime_qualification_v0_1"
           / "prospective_development_authority_v0_2")
AUTHORITY_PATH = PACKAGE / "authority_parameters.json"
DRIVER_PATH = ROOT / "scripts/regime_a_prime_qualification_v0_2/stage_unit_driver.py"

# The exact binary64 eye the runtime produced: 4.0 + (double)1.62f. Written as
# the arithmetic rather than the literal so the relationship stays visible.
CAPTURED_EYE_Y = 4.0 + float(np.float32(1.62))
BLOCKED_EYE_Y = 5.620000004768372
EYE_HEIGHT_1_62F = float(np.float32(1.62))


def _load_driver():
    spec = importlib.util.spec_from_file_location("stage_unit_driver", DRIVER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


driver = _load_driver()
load_json = driver.load_json


@pytest.fixture
def authority():
    return load_json(AUTHORITY_PATH)


@pytest.fixture
def policy(authority):
    return authority["apparatus_observation_policy"]


@pytest.fixture
def unit():
    return {"unit_id": "a1q_ltr_wall_r01", "scene": "WALL", "episode_id": 81001}


def _state_rows(policy, n=180):
    """Rows shaped exactly like the captured server_state.jsonl."""
    return [
        {
            "server_tick": i,
            "target_entity_uuid": "b9128b22-34aa-4a19-9a95-f49d415f6a2e",
            "target_respawn_count": 0,
            "player_x": 0.5,
            "player_y": CAPTURED_EYE_Y,
            "player_z": -5.5,
            "player_yaw": 0.0,
            "player_pitch": 0.0,
        }
        for i in range(n)
    ]


def _visibility_rows(n=180):
    # A WALL unit must exhibit both regimes.
    return [{"geometric_status": "visible" if i < 60 else "occluded"} for i in range(n)]


def _client_authority(policy, episode_id=81001):
    return {
        "schema_version": "mineocclude-client-authority-v0.1",
        "episode_id": episode_id,
        "fov_degrees": policy["fov_degrees"],
        "fov_effect_scale": 0.0,
        "framebuffer_width": policy["canonical_frame_pixels"][0],
        "framebuffer_height": policy["canonical_frame_pixels"][1],
        "hud_hidden": True,
    }


@pytest.fixture
def destination(tmp_path, policy):
    raw = tmp_path / "raw"
    (raw / "frames").mkdir(parents=True)
    Image.new("RGB", tuple(policy["canonical_frame_pixels"])).save(raw / "frames/000000.png")
    (raw / "client_authority.json").write_text(json.dumps(_client_authority(policy)))
    return tmp_path


@pytest.fixture
def artifacts(policy):
    return {"state": _state_rows(policy), "visibility": _visibility_rows()}


def _verify(authority, unit, artifacts, destination):
    return driver.verify_captured_apparatus(authority, unit, artifacts, destination)


# ------------------------------------------------- the live blocked failure


def test_captured_eye_is_bitwise_four_plus_the_1_62f_eye_height():
    """The blocked runs' player_y is exactly feet 4.0 raised by 1.62f."""
    assert CAPTURED_EYE_Y == BLOCKED_EYE_Y
    assert BLOCKED_EYE_Y - EYE_HEIGHT_1_62F == 4.0


def test_the_old_feet_comparison_reproduces_the_blocked_failure(policy):
    """Reading player_y as feet is off by the eye height -- the live block."""
    feet = policy["camera_feet_world_xyz"]
    misread_as_feet = [0.5, BLOCKED_EYE_Y, -5.5]
    assert not np.allclose(misread_as_feet, feet, rtol=0, atol=1e-9)
    assert misread_as_feet[1] - feet[1] == pytest.approx(1.6200000047683716, abs=0.0)


def test_the_blocked_capture_now_passes(authority, unit, artifacts, destination):
    """The exact bytes that blocked all three attempts are now accepted."""
    receipt = _verify(authority, unit, artifacts, destination)
    assert receipt["status"] == "PASS"
    assert receipt["camera_feet_world_xyz"] == authority[
        "apparatus_observation_policy"]["camera_feet_world_xyz"]
    assert receipt["camera_eye_world_xyz"] == authority[
        "apparatus_observation_policy"]["camera_eye_world_xyz"]


def test_declared_eye_is_the_ten_decimal_rounding_of_the_captured_eye(policy):
    """The 1e-9 atol is an encoding tolerance, not a scientific loosening."""
    declared = policy["camera_eye_world_xyz"][1]
    assert round(CAPTURED_EYE_Y, 10) == declared
    assert abs(CAPTURED_EYE_Y - declared) < 1e-9
    # And it is genuinely tight: the discrepancy is ~3.2e-11, not near the bound.
    assert abs(CAPTURED_EYE_Y - declared) < 1e-10


# ------------------------------------------------- genuine displacement fails


@pytest.mark.parametrize("axis,delta,message", [
    (0, 0.5, "captured camera eye mismatch"),
    (1, 0.5, "captured camera eye mismatch"),
    (2, 0.5, "captured camera eye mismatch"),
    (0, -1.0, "captured camera eye mismatch"),
    (2, 1.0, "captured camera eye mismatch"),
])
def test_displaced_camera_still_fails(authority, unit, artifacts, destination,
                                      axis, delta, message):
    field = ("player_x", "player_y", "player_z")[axis]
    artifacts["state"][7][field] = artifacts["state"][7][field] + delta
    with pytest.raises(RuntimeError, match=message):
        _verify(authority, unit, artifacts, destination)


def test_wrong_axis_is_not_absorbed(authority, unit, artifacts, destination):
    """Swapping x and z is a real displacement and must fail."""
    for row in artifacts["state"]:
        row["player_x"], row["player_z"] = row["player_z"], row["player_x"]
    with pytest.raises(RuntimeError, match="captured camera eye mismatch"):
        _verify(authority, unit, artifacts, destination)


def test_eye_for_feet_confusion_fails(authority, unit, artifacts, destination):
    """A runtime that logged FEET into player_y must now fail, symmetrically."""
    for row in artifacts["state"]:
        row["player_y"] = 4.0
    with pytest.raises(RuntimeError, match="captured camera eye mismatch"):
        _verify(authority, unit, artifacts, destination)


def test_double_eye_height_fails(authority, unit, artifacts, destination):
    """Applying the eye offset twice must not be accepted."""
    for row in artifacts["state"]:
        row["player_y"] = 4.0 + 2 * EYE_HEIGHT_1_62F
    with pytest.raises(RuntimeError, match="captured camera eye mismatch"):
        _verify(authority, unit, artifacts, destination)


def test_no_tolerance_loophole_just_above_the_encoding_bound(authority, unit,
                                                            artifacts, destination):
    """A displacement above the encoding tolerance is rejected."""
    artifacts["state"][3]["player_y"] += 1e-8
    with pytest.raises(RuntimeError, match="captured camera eye mismatch"):
        _verify(authority, unit, artifacts, destination)


def test_a_single_bad_row_out_of_180_fails(authority, unit, artifacts, destination):
    """Every row is checked -- a mid-episode drift cannot hide."""
    artifacts["state"][179]["player_x"] = 0.6
    with pytest.raises(RuntimeError, match="captured camera eye mismatch"):
        _verify(authority, unit, artifacts, destination)


# ------------------------------------------------- orientation


@pytest.mark.parametrize("field", ["player_yaw", "player_pitch"])
def test_orientation_drift_fails(authority, unit, artifacts, destination, field):
    artifacts["state"][11][field] = 10.0
    with pytest.raises(RuntimeError, match="captured camera orientation mismatch"):
        _verify(authority, unit, artifacts, destination)


# ------------------------------------------------- FOV, from captured bytes


def test_fov_is_verified_from_the_captured_client_record(authority, unit, artifacts,
                                                         destination, policy):
    """The former row-based read was a KeyError against every real capture."""
    assert "fov_degrees" not in artifacts["state"][0]
    assert _verify(authority, unit, artifacts, destination)["fov_degrees"] == policy["fov_degrees"]


def test_missing_client_authority_record_fails(authority, unit, artifacts, destination):
    (destination / "raw/client_authority.json").unlink()
    with pytest.raises(RuntimeError, match="captured client authority record is missing"):
        _verify(authority, unit, artifacts, destination)


def test_stale_client_authority_record_fails(authority, unit, artifacts, destination, policy):
    """A record left behind by a previous episode must not satisfy this unit."""
    stale = _client_authority(policy, episode_id=81000)
    (destination / "raw/client_authority.json").write_text(json.dumps(stale))
    with pytest.raises(RuntimeError, match="captured client authority record is stale"):
        _verify(authority, unit, artifacts, destination)


def test_wrong_fov_fails(authority, unit, artifacts, destination, policy):
    record = _client_authority(policy)
    record["fov_degrees"] = 90.0
    (destination / "raw/client_authority.json").write_text(json.dumps(record))
    with pytest.raises(RuntimeError, match="captured FOV mismatch"):
        _verify(authority, unit, artifacts, destination)


def test_unpinned_fov_effect_scale_fails(authority, unit, artifacts, destination, policy):
    """A live FOV effect means the pinned FOV is not the rendered FOV."""
    record = _client_authority(policy)
    record["fov_effect_scale"] = 1.0
    (destination / "raw/client_authority.json").write_text(json.dumps(record))
    with pytest.raises(RuntimeError, match="captured FOV effect scale is not pinned"):
        _verify(authority, unit, artifacts, destination)


def test_wrong_framebuffer_dimensions_fail(authority, unit, artifacts, destination, policy):
    record = _client_authority(policy)
    record["framebuffer_width"] = 1280
    (destination / "raw/client_authority.json").write_text(json.dumps(record))
    with pytest.raises(RuntimeError, match="captured framebuffer dimensions mismatch"):
        _verify(authority, unit, artifacts, destination)


def test_wrong_frame_pixels_fail(authority, unit, artifacts, destination, policy):
    Image.new("RGB", (320, 180)).save(destination / "raw/frames/000000.png")
    with pytest.raises(RuntimeError, match="captured frame dimensions mismatch"):
        _verify(authority, unit, artifacts, destination)


# ------------------------------------------------- unit / spec identity


def test_target_identity_drift_fails(authority, unit, artifacts, destination):
    artifacts["state"][5]["target_entity_uuid"] = "00000000-0000-0000-0000-000000000000"
    with pytest.raises(RuntimeError, match="captured target identity/respawn mismatch"):
        _verify(authority, unit, artifacts, destination)


def test_respawned_target_fails(authority, unit, artifacts, destination):
    artifacts["state"][5]["target_respawn_count"] = 1
    with pytest.raises(RuntimeError, match="captured target identity/respawn mismatch"):
        _verify(authority, unit, artifacts, destination)


def test_wall_unit_without_both_regimes_fails(authority, unit, artifacts, destination):
    artifacts["visibility"] = [{"geometric_status": "visible"}] * 180
    with pytest.raises(RuntimeError, match="WALL layout evidence lacks visible/hidden regimes"):
        _verify(authority, unit, artifacts, destination)


def test_no_wall_unit_with_occlusion_fails(authority, unit, artifacts, destination):
    unit["scene"] = "NO_WALL"
    with pytest.raises(RuntimeError, match="NO_WALL layout evidence contains point occlusion"):
        _verify(authority, unit, artifacts, destination)


def test_incomplete_evidence_fails(authority, unit, destination):
    with pytest.raises(RuntimeError, match="captured apparatus evidence is incomplete"):
        _verify(authority, unit, {"state": [], "visibility": []}, destination)


# ------------------------------------------------- every frozen Stage-1 spec


def test_all_eight_frozen_units_satisfy_the_camera_contract(authority, artifacts, destination):
    """The repaired contract holds for all 8 authorized Stage-1 units."""
    stage1 = load_json(PACKAGE / "stage1_manifest.json")
    units = stage1["units"]
    assert len(units) == 8
    for frozen in units:
        rows = deepcopy(artifacts["state"])
        visibility = (_visibility_rows() if frozen["scene"] == "WALL"
                      else [{"geometric_status": "visible"}] * 180)
        record = _client_authority(authority["apparatus_observation_policy"],
                                   episode_id=frozen["episode_id"])
        (destination / "raw/client_authority.json").write_text(json.dumps(record))
        receipt = _verify(authority, frozen,
                          {"state": rows, "visibility": visibility}, destination)
        assert receipt["status"] == "PASS"
        assert receipt["scene"] == frozen["scene"]


def test_the_authority_eye_height_matches_the_runtime_eye_height(policy):
    """The declared feet/eye pair is consistent with Minecraft's 1.62f."""
    declared_offset = policy["camera_eye_world_xyz"][1] - policy["camera_feet_world_xyz"][1]
    assert abs(declared_offset - EYE_HEIGHT_1_62F) < 1e-9
