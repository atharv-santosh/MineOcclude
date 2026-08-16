import math

import pytest

from mineocclude.prospective.calibration_support import (
    SupportRequirements,
    SupportWindow,
    evaluate_support,
    wall_relative,
)


REQ = SupportRequirements(maximum_gap=1.0, endpoint_tolerance=0.0, minimum_samples=3)


def test_window_requires_named_coordinate_finite_ordered_bounds():
    for args in (("", -1, 1), ("x", 1, 1), ("x", math.nan, 1), ("x", -1, math.inf)):
        with pytest.raises((ValueError, TypeError)):
            SupportWindow(*args)


def test_no_requirements_means_measured_not_adjudicated():
    coverage = evaluate_support([-1.0, 0.0, 1.0], SupportWindow("world_x", -1, 1))
    assert coverage.fully_covered is None
    assert coverage.to_dict()["adjudication"] == "UNADJUDICATED"


def test_caller_supplied_requirements_can_pass_same_physical_support_at_different_counts():
    window = SupportWindow("world_x", -2, 2)
    dense = evaluate_support([-2, -1, 0, 1, 2], window, requirements=REQ)
    sparse = evaluate_support([-2, -1, 0, 1, 2, 3], window, requirements=REQ)
    assert dense.fully_covered is True and sparse.fully_covered is True
    assert dense.total != sparse.total


@pytest.mark.parametrize("bad", [[math.nan], [math.inf], [-math.inf], [0.0, math.nan]])
def test_nonfinite_input_never_passes_and_is_reported(bad):
    coverage = evaluate_support(bad, SupportWindow("x", -1, 1), requirements=REQ)
    assert coverage.fully_covered is False
    assert coverage.non_finite_count >= 1
    assert coverage.to_dict()["adjudication"] == "INVALID"


@pytest.mark.parametrize("bad", [["0"], [True], [object()], [[0.0]]])
def test_malformed_coordinate_observations_never_pass(bad):
    coverage = evaluate_support(bad, SupportWindow("x", -1, 1), requirements=REQ)
    assert coverage.fully_covered is False
    assert coverage.malformed_count == 1


def test_empty_observations_are_explicitly_invalid():
    coverage = evaluate_support([], SupportWindow("x", -1, 1), requirements=REQ)
    assert coverage.fully_covered is False
    assert coverage.sample_count == 0
    assert coverage.observed_min is None and coverage.observed_max is None


def test_material_internal_gap_fails_only_against_caller_requirement():
    window = SupportWindow("world_x", -2, 2)
    values = [-2.0, -1.75, 1.75, 2.0]
    strict = evaluate_support(
        values,
        window,
        requirements=SupportRequirements(1.0, 0.0, 4),
    )
    permissive = evaluate_support(
        values,
        window,
        requirements=SupportRequirements(4.0, 0.0, 4),
    )
    assert strict.largest_gap == pytest.approx(3.5)
    assert strict.fully_covered is False
    assert len(strict.coverage_intervals) == 2
    assert permissive.fully_covered is True


def test_endpoint_shortfall_and_outside_counts_reported():
    coverage = evaluate_support(
        [-9, -1, 0, 4, 9],
        SupportWindow("world_x", -5, 5),
        requirements=SupportRequirements(5, 0, 3),
    )
    assert coverage.inside == 3 and coverage.outside == 2
    assert coverage.uncovered_low == pytest.approx(4.0)
    assert coverage.uncovered_high == pytest.approx(1.0)
    # Outside observations establish observed range, but not in-window endpoint samples.
    assert coverage.fully_covered is False


def test_outside_observations_cannot_satisfy_minimum_in_support_count():
    values = [-1.0, 1.0] + [-100.0] * 98
    coverage = evaluate_support(
        values,
        SupportWindow("world_x", -1, 1),
        requirements=SupportRequirements(2.0, 0.0, 100),
    )
    receipt = coverage.to_dict()
    assert coverage.fully_covered is False
    assert receipt["total_valid_samples"] == 100
    assert receipt["in_support_samples"] == 2
    assert receipt["samples_outside"] == 98
    assert any("in-support sample count" in reason for reason in coverage.reasons)


def test_wall_relative_rejects_nonfinite_and_bool():
    assert wall_relative(-4.83, 0.5) == pytest.approx(-5.33)
    with pytest.raises(ValueError):
        wall_relative(math.nan, 0.5)
    with pytest.raises(TypeError):
        wall_relative(True, 0.5)
