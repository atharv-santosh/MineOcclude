"""Focused validation for Person B's coordinate-frame co-sign.

These tests exercise projection, sign convention, and unit compatibility
against real hash-bound Person C evidence, and they include negative cases so
that a passing co-sign means something: a flipped sign, a swapped axis, a
shifted origin, or a denormalized unit vector must all be rejected.
"""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import math
from pathlib import Path

import pytest

from mineocclude.analysis.config import load_core_analysis_config
from mineocclude.analysis.coordinate_frame_cosign_v0_1 import (
    ACCEPTED_GEOMETRY_PATH,
    ACCEPTED_GEOMETRY_SHA256,
    ACCEPTED_GEOMETRY_VERSION,
    COSIGN_PACKAGE_DIRECTORY,
    COSIGNED_FRAME_DIRECTORY,
    EXPECTED_LAYOUT_COUNT,
    EXPECTED_LAYOUT_IDS,
    PERSON_C_COMMIT,
    PERSON_C_COORDINATE_FRAME_AUTHORITY_PATH,
    PERSON_C_COORDINATE_FRAME_AUTHORITY_SHA256,
    CoordinateCosignError,
    cosign_frame,
    load_accepted_geometry,
    load_person_c_authority,
    read_bound_blob,
    replay_projection_against_capture_packages,
    validate_layout_frame,
)
from mineocclude.analysis.coordinates import (
    COORDINATE_FRAME_SCHEMA_VERSION,
    CoordinateContractError,
    coordinate_frame_hash,
    validate_coordinate_frame,
)
from mineocclude.analysis.manifests import validate_sealed_artifact

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PACKAGE = REPOSITORY_ROOT / COSIGN_PACKAGE_DIRECTORY
FRAMES = REPOSITORY_ROOT / COSIGNED_FRAME_DIRECTORY
BUILDER = (
    REPOSITORY_ROOT / "scripts" / "build_person_b_coordinate_frame_cosign_v0_1.py"
)


@pytest.fixture(scope="module")
def intake() -> dict:
    return load_person_c_authority(repository_root=REPOSITORY_ROOT)


@pytest.fixture(scope="module")
def geometry() -> dict:
    return load_accepted_geometry(repository_root=REPOSITORY_ROOT)


@pytest.fixture(scope="module")
def layout_results(intake, geometry) -> list[dict]:
    return [
        validate_layout_frame(layout_id, intake["frames"][layout_id], geometry[layout_id])
        for layout_id in sorted(intake["frames"])
    ]


def _published(name: str) -> dict:
    return json.loads((PACKAGE / name).read_text(encoding="utf-8"))


# ------------------------------------------------------- byte identity
def test_person_c_coordinate_frame_bytes_are_unchanged(intake):
    assert intake["authority_sha256"] == PERSON_C_COORDINATE_FRAME_AUTHORITY_SHA256
    payload = read_bound_blob(
        PERSON_C_COORDINATE_FRAME_AUTHORITY_PATH,
        expected_sha256=PERSON_C_COORDINATE_FRAME_AUTHORITY_SHA256,
        repository_root=REPOSITORY_ROOT,
    )
    assert hashlib.sha256(payload).hexdigest() == (
        PERSON_C_COORDINATE_FRAME_AUTHORITY_SHA256
    )


def test_intake_rejects_a_wrong_authority_hash():
    with pytest.raises(CoordinateCosignError):
        read_bound_blob(
            PERSON_C_COORDINATE_FRAME_AUTHORITY_PATH,
            expected_sha256="0" * 64,
            repository_root=REPOSITORY_ROOT,
        )


def test_accepted_geometry_hash_is_the_declared_authority():
    payload = read_bound_blob(
        ACCEPTED_GEOMETRY_PATH,
        expected_sha256=ACCEPTED_GEOMETRY_SHA256,
        repository_root=REPOSITORY_ROOT,
    )
    document = json.loads(payload.decode("utf-8"))
    assert document["config_version"] == ACCEPTED_GEOMETRY_VERSION
    assert len(document["layouts"]) == EXPECTED_LAYOUT_COUNT


def test_six_layouts_are_present_and_person_c_signed(intake):
    assert tuple(sorted(intake["frames"])) == EXPECTED_LAYOUT_IDS
    for frame in intake["frames"].values():
        assert frame["adapter_signoff"]["person_c"] is True
        assert frame["adapter_signoff"]["person_b"] is False
        assert frame["source_layout_manifest_hash"] == ACCEPTED_GEOMETRY_SHA256


# ------------------------------------------------- per-layout validation
def test_every_layout_frame_is_compatible(layout_results):
    assert len(layout_results) == EXPECTED_LAYOUT_COUNT
    for item in layout_results:
        assert item["compatible"] is True, (item["layout_id"], item["failed_checks"])
        assert item["failed_checks"] == []
        assert len(item["checks"]) >= 30


def test_scalar_axis_is_x_or_z_and_never_the_vertical_axis(layout_results):
    axes = {item["layout_id"]: item["wall_parallel_scalar_axis"] for item in layout_results}
    assert set(axes.values()) <= {"x", "z"}
    assert axes["layout_02"] == "z"
    assert axes["layout_06"] == "z"
    assert axes["layout_01"] == axes["layout_03"] == axes["layout_04"] == "x"
    assert axes["layout_05"] == "x"


def test_unit_vector_is_a_unit_length_positive_basis_vector(layout_results):
    for item in layout_results:
        vector = item["positive_unit_vector_world_xyz"]
        assert math.isclose(math.hypot(*vector), 1.0, rel_tol=0.0, abs_tol=1e-9)
        assert sorted(vector) == [0.0, 0.0, 1.0]
        assert item["positive_world_direction"] == f"+{item['wall_parallel_scalar_axis']}"
        assert item["motion_sign"] == 1


def test_coordinate_frame_hash_reproduces_for_every_layout(intake):
    for layout_id, frame in intake["frames"].items():
        assert coordinate_frame_hash(frame) == frame["coordinate_frame_hash"], layout_id


def test_person_b_validator_accepts_each_c_side_frame(intake):
    for layout_id, frame in intake["frames"].items():
        resolved = validate_coordinate_frame(frame, require_cross_role_signoff=False)
        assert resolved.coordinate_frame_id.endswith(f"{layout_id}-v0.1")
        assert resolved.source_layout_manifest_hash == ACCEPTED_GEOMETRY_SHA256


def test_person_b_validator_refuses_an_unsigned_frame_for_live_use(intake):
    frame = intake["frames"]["layout_01"]
    with pytest.raises(CoordinateContractError):
        validate_coordinate_frame(frame, require_cross_role_signoff=True)


# --------------------------------------------------- negative controls
def _mutate(frame: dict, **changes) -> dict:
    mutated = copy.deepcopy(frame)
    mutated.update(changes)
    mutated["coordinate_frame_hash"] = coordinate_frame_hash(mutated)
    return mutated


def test_flipped_sign_convention_is_rejected(intake, geometry):
    frame = _mutate(
        intake["frames"]["layout_01"],
        wall_parallel_positive_unit_vector_world_xyz=[-1.0, 0.0, 0.0],
    )
    result = validate_layout_frame("layout_01", frame, geometry["layout_01"])
    assert result["compatible"] is False
    assert "unit_vector_is_positive_basis_of_scalar_axis" in result["failed_checks"]
    assert "positive_world_direction_agrees" in result["failed_checks"]


def test_swapped_axis_is_rejected(intake, geometry):
    frame = _mutate(
        intake["frames"]["layout_01"],
        wall_parallel_positive_unit_vector_world_xyz=[0.0, 0.0, 1.0],
    )
    result = validate_layout_frame("layout_01", frame, geometry["layout_01"])
    assert result["compatible"] is False
    assert "unit_vector_is_positive_basis_of_scalar_axis" in result["failed_checks"]


def test_shifted_origin_is_rejected(intake, geometry):
    frame = _mutate(
        intake["frames"]["layout_01"],
        wall_parallel_origin_world_xyz=[1.0, 4.0, 6.0],
    )
    result = validate_layout_frame("layout_01", frame, geometry["layout_01"])
    assert result["compatible"] is False
    assert "origin_is_lane_anchor_with_declared_scalar_component" in (
        result["failed_checks"]
    )


def test_denormalized_unit_vector_is_rejected(intake, geometry):
    frame = _mutate(
        intake["frames"]["layout_01"],
        wall_parallel_positive_unit_vector_world_xyz=[2.0, 0.0, 0.0],
    )
    result = validate_layout_frame("layout_01", frame, geometry["layout_01"])
    assert result["compatible"] is False
    assert "unit_vector_norm_is_one" in result["failed_checks"]


def test_wrong_geometry_hash_is_rejected(intake, geometry):
    frame = _mutate(intake["frames"]["layout_01"], source_layout_manifest_hash="a" * 64)
    result = validate_layout_frame("layout_01", frame, geometry["layout_01"])
    assert result["compatible"] is False
    assert "source_layout_manifest_hash_is_accepted_geometry" in result["failed_checks"]


def test_altered_wall_bounds_are_rejected(intake, geometry):
    frame = copy.deepcopy(intake["frames"]["layout_01"])
    frame["person_c_authority"]["wall_bounds"]["max_x"] = 99
    result = validate_layout_frame("layout_01", frame, geometry["layout_01"])
    assert result["compatible"] is False
    assert "wall_bounds_match_accepted_geometry" in result["failed_checks"]


def test_altered_lane_bounds_are_rejected(intake, geometry):
    frame = copy.deepcopy(intake["frames"]["layout_01"])
    frame["person_c_authority"]["lane_bounds"]["axis_max"] = 99.0
    result = validate_layout_frame("layout_01", frame, geometry["layout_01"])
    assert result["compatible"] is False
    assert "lane_bounds_match_accepted_geometry" in result["failed_checks"]


def test_altered_shadow_bounds_are_rejected(intake, geometry):
    frame = copy.deepcopy(intake["frames"]["layout_01"])
    frame["person_c_authority"]["shadow_bounds"]["occluded_integer_axis_max"] = 99
    result = validate_layout_frame("layout_01", frame, geometry["layout_01"])
    assert result["compatible"] is False
    assert "shadow_occluded_interval_is_rederived" in result["failed_checks"]


def test_a_frame_validated_against_another_layouts_geometry_is_rejected(
    intake, geometry
):
    result = validate_layout_frame(
        "layout_01", intake["frames"]["layout_01"], geometry["layout_02"]
    )
    assert result["compatible"] is False


# --------------------------------------- projection replay on real state
def test_projection_replay_matches_person_c_exactly(intake):
    replay = replay_projection_against_capture_packages(
        intake["frames"], repository_root=REPOSITORY_ROOT
    )
    assert replay["replay_pass"] is True
    assert replay["capture_package_count"] == 66
    assert replay["state_row_count"] == 2_468
    assert replay["target_bearing_row_count"] == 2_108
    assert replay["mismatches"] == []
    assert all(replay["checks"].values())
    for item in replay["per_layout"]:
        assert item["trajectory_count"] == 11
        assert item["target_bearing_row_count"] > 0
        assert item["max_abs_projection_error_blocks"] == 0.0
        assert item["max_abs_orthogonal_deviation_blocks"] == 0.0
        assert item["monotone_step_sign_disagreement_count"] == 0
        assert item["occluded_row_outside_shadow_bracket_count"] == 0


def test_projection_replay_rejects_a_resealed_flipped_sign(intake):
    """A flipped axis that reseals its own hash no longer matches the capture
    packages, which name the coordinate frame hash Person C actually captured
    under."""

    frames = copy.deepcopy(intake["frames"])
    frame = frames["layout_01"]
    frame["wall_parallel_positive_unit_vector_world_xyz"] = [-1.0, 0.0, 0.0]
    frame["coordinate_frame_hash"] = coordinate_frame_hash(frame)
    with pytest.raises(CoordinateCosignError, match="different coordinate frame hash"):
        replay_projection_against_capture_packages(
            frames, repository_root=REPOSITORY_ROOT
        )


def test_projection_replay_rejects_a_flipped_sign_under_its_original_hash(intake):
    """Flipping the axis without resealing breaks the frame's own hash, so
    Person B's coordinate validator refuses to build a projector at all."""

    frames = copy.deepcopy(intake["frames"])
    frames["layout_01"]["wall_parallel_positive_unit_vector_world_xyz"] = [
        -1.0,
        0.0,
        0.0,
    ]
    with pytest.raises(CoordinateContractError):
        replay_projection_against_capture_packages(
            frames, repository_root=REPOSITORY_ROOT
        )


def test_a_flipped_unit_vector_negates_the_projected_scalar(intake):
    """The arithmetic the replay compares against: a sign flip changes the
    scalar the oracle would treat as position."""

    frame = copy.deepcopy(intake["frames"]["layout_01"])
    upright = validate_coordinate_frame(frame, require_cross_role_signoff=False)
    frame["wall_parallel_positive_unit_vector_world_xyz"] = [-1.0, 0.0, 0.0]
    frame["coordinate_frame_hash"] = coordinate_frame_hash(frame)
    flipped = validate_coordinate_frame(frame, require_cross_role_signoff=False)
    for position in ([-6.5, 4.0, 6.0], [2.25, 4.0, 6.0], [7.0, 4.0, 6.0]):
        assert flipped.project(position) == -upright.project(position)
        assert upright.project(position) == position[0]


# ------------------------------------------------------- units contract
def test_units_match_person_b_oracle_contract(intake):
    contract = load_core_analysis_config()["coordinate_contract"]
    assert contract["unit"] == "blocks"
    assert contract["quantity"] == "signed_wall_parallel_position"
    assert contract["silent_axis_inference_forbidden"] is True
    for frame in intake["frames"].values():
        authority = frame["person_c_authority"]
        assert authority["scalar_axis_unit"] == contract["unit"]
        assert authority["silent_axis_inference"] is False
        assert authority["private_axis_reinterpretation"] is False
        assert frame["coordinate_frame_schema_version"] == COORDINATE_FRAME_SCHEMA_VERSION


def test_projection_matches_the_frozen_positive_direction_rule(intake):
    contract = load_core_analysis_config()["coordinate_contract"]
    assert contract["positive_direction_rule"] == (
        "increasing dot(world_position - origin, positive_unit_vector)"
    )
    frame = validate_coordinate_frame(
        intake["frames"]["layout_01"], require_cross_role_signoff=False
    )
    origin = frame.origin_world_xyz
    unit = frame.positive_unit_vector_world_xyz
    for position in ([-6.5, 4.0, 6.0], [0.0, 4.0, 6.0], [7.25, 4.0, 6.0]):
        expected = sum(
            (position[index] - origin[index]) * unit[index] for index in range(3)
        )
        assert frame.project(position) == expected


# ------------------------------------------------------------- co-sign
def test_cosign_preserves_the_coordinate_frame_hash(intake):
    for layout_id, frame in intake["frames"].items():
        cosigned = cosign_frame(
            frame,
            person_b_branch="role/person-b-analysis",
            person_b_commit=None,
            cosign_receipt_id="test",
        )
        assert cosigned["coordinate_frame_hash"] == frame["coordinate_frame_hash"]
        assert coordinate_frame_hash(cosigned) == frame["coordinate_frame_hash"], layout_id
        assert cosigned["adapter_signoff"]["person_b"] is True
        assert cosigned["adapter_signoff"]["person_c"] is True
        assert frame["adapter_signoff"]["person_b"] is False


def test_cosign_refuses_to_resign_an_already_signed_frame(intake):
    cosigned = cosign_frame(
        intake["frames"]["layout_01"],
        person_b_branch="role/person-b-analysis",
        person_b_commit=None,
        cosign_receipt_id="test",
    )
    with pytest.raises(CoordinateCosignError):
        cosign_frame(
            cosigned,
            person_b_branch="role/person-b-analysis",
            person_b_commit=None,
            cosign_receipt_id="test",
        )


def test_published_cosigned_frames_pass_live_use_validation(intake):
    assert sorted(path.stem for path in FRAMES.glob("*.json")) == list(
        EXPECTED_LAYOUT_IDS
    )
    for layout_id in EXPECTED_LAYOUT_IDS:
        document = json.loads((FRAMES / f"{layout_id}.json").read_text(encoding="utf-8"))
        resolved = validate_coordinate_frame(document, require_cross_role_signoff=True)
        assert resolved.source_layout_manifest_hash == ACCEPTED_GEOMETRY_SHA256
        assert document["coordinate_frame_hash"] == (
            intake["frames"][layout_id]["coordinate_frame_hash"]
        )
        assert document["person_b_cosign"]["person_c_bytes_modified"] is False
        assert document["person_b_cosign"]["coordinate_frame_hash_preserved"] is True
        assert document["person_b_cosign"]["scientific_result_inspected"] is False
        assert document["person_b_cosign"]["outcome_dependent_change"] is False


# ------------------------------------------------- published sign-off
def test_published_cosign_document_is_complete():
    document = _published("coordinate_frame_cosign.json")
    validate_sealed_artifact(document, expected_type="person_b_coordinate_frame_cosign")
    assert document["person_c_commit"] == PERSON_C_COMMIT
    assert document["person_c_coordinate_frame_path"] == (
        PERSON_C_COORDINATE_FRAME_AUTHORITY_PATH
    )
    assert document["person_c_coordinate_frame_sha256"] == (
        PERSON_C_COORDINATE_FRAME_AUTHORITY_SHA256
    )
    assert document["accepted_geometry_sha256"] == ACCEPTED_GEOMETRY_SHA256
    assert document["layout_ids"] == list(EXPECTED_LAYOUT_IDS)
    assert document["layout_count"] == EXPECTED_LAYOUT_COUNT
    assert document["adapter_signoff"]["person_b"] is True
    assert document["compatibility_result"]["coordinate_frame_compatible"] is True
    assert document["person_b_branch"] == "role/person-b-analysis"
    assert document["person_c_bytes_modified"] is False
    assert document["person_c_branch_merged"] is False
    assert document["scientific_result_inspected"] is False
    assert document["outcome_dependent_change"] is False
    assert document["oracle_target_manifest_built"] is False
    assert document["activation_analysis_executed"] is False
    interpretation = document["person_b_wall_parallel_interpretation"]
    assert interpretation["unit"] == "blocks"
    assert interpretation["quantity"] == "signed_wall_parallel_position"


def test_published_inventory_matches_published_bytes():
    inventory = _published("sha256_inventory.json")
    assert inventory["inventory_excludes_self"] is True
    assert inventory["file_count"] == 2 + EXPECTED_LAYOUT_COUNT
    for item in inventory["files"]:
        payload = (REPOSITORY_ROOT / item["path"]).read_bytes()
        assert hashlib.sha256(payload).hexdigest() == item["sha256"], item["path"]
        assert len(payload) == item["byte_size"], item["path"]


def test_builder_is_byte_reproducible():
    spec = importlib.util.spec_from_file_location(
        "person_b_coordinate_frame_cosign_builder", BUILDER
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    before = {
        path: path.read_bytes()
        for path in sorted(PACKAGE.glob("*.json")) + sorted(FRAMES.glob("*.json"))
    }
    result = module.build()
    after = {path: path.read_bytes() for path in before}
    assert before == after
    assert result["coordinate_frame_compatible"] is True
    assert result["person_b_coordinate_frame_signed"] is True
    assert result["coordinate_frame_hash_unchanged"] is True
