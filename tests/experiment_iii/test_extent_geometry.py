"""I05 — counterfactual extent logic (A.10, A.11, port equivalence).

The 475/475 agreement and the ``present=False`` trap are reconstructed from the
bound git objects, not from a regenerated fixture: a fixture regenerated to match
new behavior would defeat the check.
"""

from __future__ import annotations

import math

import pytest

from mineocclude.experiment_iii import aprime_reference as aprime
from mineocclude.experiment_iii._aprime_extent_geometry import (
    ReferenceAgreementError,
    classify_extent,
)
from mineocclude.experiment_iii.authority import CAMERA_EYE, LAYOUT_01
from mineocclude.experiment_iii.errors import ExperimentIIIError
from mineocclude.experiment_iii.extent_geometry import (
    EXTENT_SAMPLES_PER_AXIS,
    REFERENCE_MARCH_SAMPLES,
    TARGET_EXTENT_HALF_BLOCKS,
    WallGeometry,
    aprime_port_receipt,
    classify_counterfactual_extent,
    counterfactual_extent_classes,
    counterfactual_wall,
    derive_target_extent_half_blocks,
    extent_sample_points,
    first_fully_occluded_run,
    fully_occluded_runs,
    segment_hits_wall,
    target_centre,
    verify_port_blob,
    verify_reference_agreement,
)
from mineocclude.experiment_iii.schema import ConditionId, ExtentClassName

FULLY_OCCLUDED = ExtentClassName.EXTENT_FULLY_OCCLUDED


def _absent_counterfactual() -> WallGeometry:
    """The forbidden construction the L0 trap fixture exists to demonstrate."""
    return WallGeometry.from_layout(
        wall_axis=str(LAYOUT_01["wall_axis"]),
        wall_seg_min=float(LAYOUT_01["wall_seg_min"]),
        wall_seg_max=float(LAYOUT_01["wall_seg_max"]),
        wall_ortho_const=float(LAYOUT_01["wall_ortho_const"]),
        wall_ortho_offset=float(LAYOUT_01["wall_ortho_offset"]),
        lane_y=float(LAYOUT_01["lane_y"]),
        present=False,
    )


@pytest.fixture(scope="module")
def aprime_wall_rows():
    """(unit_id, position) for all 475 A-prime WALL materialized target rows."""
    rows = []
    for unit in aprime.aprime_materialized_units():
        if unit.scene != "WALL":
            continue
        positions, _ = aprime.aprime_generate_path(
            noise_seed=unit.noise_seed,
            start_world_x=unit.start_world_x,
            direction=unit.direction,
            q=unit.motion_noise_q,
            speed=unit.speed_blocks_per_second,
            frames=unit.expected_frames,
        )
        assert aprime.path_sha256(positions) == unit.expected_path_sha256
        rows.extend(
            (unit.unit_id, float(positions[index]))
            for index in unit.target_model_frame_indices
        )
    return rows


# --------------------------------------------------------------------------
# A.11 — extent port equivalence
# --------------------------------------------------------------------------

def test_port_blob_reproduces_the_bound_sha1():
    provenance = verify_port_blob()
    assert provenance["blob_sha1"] == "45889b6bc9ed07129f5fd2f15167b694206eab31"
    assert provenance["source_commit"].startswith("a5d763a")


def test_target_extent_half_blocks_constant_and_closed_form():
    assert TARGET_EXTENT_HALF_BLOCKS == 0.8727621336620037
    assert derive_target_extent_half_blocks() == TARGET_EXTENT_HALF_BLOCKS
    assert (7 + math.sqrt(48.5)) / 16 == TARGET_EXTENT_HALF_BLOCKS


def test_as_built_wall_is_computed_from_the_layout():
    wall = counterfactual_wall()
    assert (wall.wall_ortho, wall.wall_axis_min, wall.wall_axis_max) == (2.5, -3, 4.0)
    assert (wall.wall_y_min, wall.wall_y_max, wall.half) == (4.0, 7.0, 0.5)
    assert wall.present is True


def test_wall_cells_move_under_a_perturbed_layout():
    """A.8's derivation check: the geometry is computed, not hard-coded."""
    perturbed = dict(LAYOUT_01, wall_seg_min=-4.5, wall_seg_max=4.5)
    shifted = counterfactual_wall(perturbed)
    # floor(-4.5) = -5 and ceil(4.5) + 1.0 = 6.0, exactly as ArenaBuilder places
    # whole blocks; the cells move with the layout rather than staying put.
    assert (shifted.wall_axis_min, shifted.wall_axis_max) == (-5, 6.0)


def test_all_475_aprime_wall_target_rows_are_fully_occluded(aprime_wall_rows):
    assert len(aprime_wall_rows) == 475
    classified = [
        classify_counterfactual_extent(position) for _, position in aprime_wall_rows
    ]
    assert classified.count(FULLY_OCCLUDED) == 475


def test_segment_hits_wall_marches_exactly_63_interior_samples():
    """The march is ``t = i/64`` for ``i in [1, 64)`` — endpoints untested.

    The camera-to-target segment below spans 64 blocks of ortho, so sample ``i``
    lands exactly on ortho ``i``. A needle-thin slab centred on an integer is hit;
    the same slab centred half a block away is missed; and slabs centred on the
    two endpoints are missed because neither endpoint is sampled.
    """
    assert REFERENCE_MARCH_SAMPLES == 64

    def hits(wall_ortho: float, half: float = 0.1) -> bool:
        return segment_hits_wall(
            0.0, 5.0, 0.0,
            0.0, 5.0, 64.0,
            wall_ortho, -3.0, 4.0, 4.0, 7.0, half,
            wall_axis="X",
        )

    assert hits(32.0) is True
    assert hits(32.5) is False
    # i = 0 and i = 64 are never evaluated.
    assert hits(0.0) is False
    assert hits(64.0) is False
    # The first and last sampled positions are 1 and 63.
    assert hits(1.0) is True
    assert hits(63.0) is True


def test_segment_hits_wall_bounds_are_inclusive():
    wall = counterfactual_wall()
    # Ortho distance exactly ``half`` and axis exactly at the max face are hits.
    hit = segment_hits_wall(
        0.0,
        5.5,
        wall.wall_ortho - 1.0,
        0.0,
        5.5,
        wall.wall_ortho + 1.0,
        wall.wall_ortho,
        wall.wall_axis_min,
        wall.wall_axis_max,
        wall.wall_y_min,
        wall.wall_y_max,
        wall.half,
        wall_axis=wall.wall_axis,
    )
    assert hit is True


def test_extent_lattice_is_closed_and_contains_the_corners():
    points = extent_sample_points((1.0, 4.5, 6.0), TARGET_EXTENT_HALF_BLOCKS)
    assert len(points) == EXTENT_SAMPLES_PER_AXIS**2 == 25
    for corner_x in (1.0 - TARGET_EXTENT_HALF_BLOCKS, 1.0 + TARGET_EXTENT_HALF_BLOCKS):
        for corner_z in (
            6.0 - TARGET_EXTENT_HALF_BLOCKS,
            6.0 + TARGET_EXTENT_HALF_BLOCKS,
        ):
            assert (corner_x, 4.5, corner_z) in points


def test_verify_reference_agreement_detects_a_disagreement():
    wall = counterfactual_wall()
    samples = [
        {
            "axis_position": position,
            "occluded": wall.occludes(CAMERA_EYE, target_centre(float(position))),
        }
        for position in range(-8, 9)
    ]
    report = verify_reference_agreement(
        CAMERA_EYE,
        wall,
        samples,
        target_centre_y=float(LAYOUT_01["lane_y"]) + 0.5,
        lane_ortho_const=float(LAYOUT_01["wall_ortho_const"]),
    )
    assert report["disagreements"] == 0
    assert report["reference_lane_samples_checked"] == 17

    corrupted = [dict(row) for row in samples]
    corrupted[8]["occluded"] = not corrupted[8]["occluded"]
    with pytest.raises(ReferenceAgreementError):
        verify_reference_agreement(
            CAMERA_EYE,
            wall,
            corrupted,
            target_centre_y=float(LAYOUT_01["lane_y"]) + 0.5,
            lane_ortho_const=float(LAYOUT_01["wall_ortho_const"]),
        )


# --------------------------------------------------------------------------
# A.10 — the counterfactual is present for all five conditions, L0 included
# --------------------------------------------------------------------------

def test_counterfactual_wall_is_present_for_every_condition():
    for condition in ConditionId:
        wall = counterfactual_wall()
        assert wall.present is True, condition
    # Physical presence and counterfactual presence are different things.
    assert ConditionId.L0.wall_present is False
    assert counterfactual_wall().present is True


def test_l0_classification_is_identical_to_every_other_condition():
    positions = [-4.0, -2.0, 0.0, 2.0, 4.0]
    reference = counterfactual_extent_classes(positions)
    for condition in ConditionId:
        assert counterfactual_extent_classes(positions) == reference, condition


def test_absent_counterfactual_collapses_l0_eligibility_to_zero(aprime_wall_rows):
    """The negative control: ``present=False`` yields zero eligible L0 rows."""
    absent = _absent_counterfactual()
    occluded = sum(
        classify_extent(CAMERA_EYE, target_centre(position), absent).name
        == "EXTENT_FULLY_OCCLUDED"
        for _, position in aprime_wall_rows
    )
    assert occluded == 0
    # And the public entry point refuses the construction outright.
    with pytest.raises(ExperimentIIIError) as caught:
        classify_counterfactual_extent(0.0, wall=absent)
    assert caught.value.blocker == "FIR_COUNTERFACTUAL_PRESENCE_ERROR"


def test_counterfactual_occluded_interval_is_wide_enough_for_gate_6():
    step = 0.002
    occluded = [
        position
        for index in range(int(16.0 / step) + 1)
        if (position := -8.0 + index * step) <= 8.0
        and classify_counterfactual_extent(position) is FULLY_OCCLUDED
    ]
    width = max(occluded) - min(occluded)
    # Authority 4.5: about 7.98 blocks, roughly 79 ticks at 2.0 blocks/s.
    assert 7.9 <= width <= 8.05
    assert min(occluded) == pytest.approx(-3.49, abs=0.02)
    assert max(occluded) == pytest.approx(4.49, abs=0.02)
    assert width / (2.0 * 0.05) > 19


# --------------------------------------------------------------------------
# Run selection (authority 2.5)
# --------------------------------------------------------------------------

def test_first_run_is_the_earliest_and_has_no_phase_offset():
    visible = ExtentClassName.EXTENT_FULLY_VISIBLE
    classes = [visible] * 3 + [FULLY_OCCLUDED] * 5 + [visible] + [FULLY_OCCLUDED] * 9
    assert fully_occluded_runs(classes) == [(3, 8), (9, 18)]
    assert first_fully_occluded_run(classes, 5) == (3, 8)
    assert first_fully_occluded_run(classes, 6) == (9, 15)
    assert first_fully_occluded_run(classes, 10) is None


def test_port_receipt_records_the_required_provenance():
    receipt = aprime_port_receipt()
    assert receipt["provenance"]["blob_sha1"] == (
        "45889b6bc9ed07129f5fd2f15167b694206eab31"
    )
    assert receipt["counterfactual_present_for_all_conditions_including_L0"] is True
    assert receipt["target_extent_half_blocks"] == TARGET_EXTENT_HALF_BLOCKS
    assert receipt["as_built_wall"]["present"] is True
