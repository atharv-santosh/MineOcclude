"""I06 — FIR kernel recovery, normalization, and the target manifest (A.7, A.12, A.13)."""

from __future__ import annotations

import math

import pytest

from mineocclude.experiment_iii import aprime_reference as aprime
from mineocclude.experiment_iii.authority import TARGET_ROWS_PER_CAPTURE
from mineocclude.experiment_iii.errors import ExperimentIIIError
from mineocclude.experiment_iii.fir import (
    ACCEPTANCE_GATES,
    FIRST_FULLY_RESOLVED_TICK,
    KERNEL_LAGS,
    KERNEL_LENGTH,
    RECOVERED_TAPS,
    assert_normalized,
    causal_fir_targets,
    fir_labels,
    frozen_kernel,
    kernel_group_delay_ticks,
    kernel_is_effectively_pure_delay,
    kernel_mode_lag,
    kernel_positive_mass_support,
    normalized_kernel,
    recover_fir_kernels,
)
from mineocclude.experiment_iii.schema import ConditionId, ExtentClassName
from mineocclude.experiment_iii.target_manifest import (
    TargetWindow,
    assert_rows_identical_across_conditions,
    build_target_window,
    context_ages,
    evidence_in_context,
    select_target_window,
)


@pytest.fixture(scope="module")
def recovery():
    return recover_fir_kernels()


# --------------------------------------------------------------------------
# A.12 — normalized_kernel contract
# --------------------------------------------------------------------------

def test_normalized_kernel_rejects_short_negative_and_massless_kernels():
    with pytest.raises(ExperimentIIIError):
        normalized_kernel([1.0])
    with pytest.raises(ExperimentIIIError):
        normalized_kernel([0.5, -0.1, 0.6])
    with pytest.raises(ExperimentIIIError):
        normalized_kernel([0.0, 0.0])


def test_normalized_kernel_rescales_with_fsum():
    taps = [0.1] * 3 + [0.7]
    kernel = normalized_kernel(taps)
    assert math.fsum(kernel) == 1.0
    expected_total = math.fsum(taps)
    assert kernel == [value / expected_total for value in taps]


def test_pure_delay_kernel_is_refused():
    delay = [0.0, 0.0, 1.0, 0.0]
    assert kernel_is_effectively_pure_delay(delay)
    with pytest.raises(ExperimentIIIError) as caught:
        causal_fir_targets(list(range(10)), [5], delay)
    assert caught.value.blocker == "FIR_KERNEL_RECOVERY_FAILED"
    # A kernel that is a bare delay plus a subnormal tap is still a bare delay.
    assert kernel_is_effectively_pure_delay([1e-300, 0.0, 0.0, 1.0, 0.0])


def test_causal_fir_targets_requires_complete_history():
    taps = list(frozen_kernel("LEFT_TO_RIGHT"))
    positions = [float(index) for index in range(40)]
    causal_fir_targets(positions, [FIRST_FULLY_RESOLVED_TICK], taps)
    with pytest.raises(ExperimentIIIError) as caught:
        causal_fir_targets(positions, [FIRST_FULLY_RESOLVED_TICK - 1], taps)
    assert caught.value.blocker == "FIR_INCOMPLETE_HISTORY"


# --------------------------------------------------------------------------
# A.12 — kernel recovery
# --------------------------------------------------------------------------

def test_recovery_reproduces_all_fifty_path_hashes(recovery):
    verification = recovery["verification"]
    assert verification["path_hashes_checked"] == 50
    assert verification["path_hashes_reproduced"] == 50


def test_recovery_reproduces_all_950_labels(recovery):
    verification = recovery["verification"]
    assert verification["labels_reproduced"] == 950
    assert verification["max_abs_label_error_rounded_10dp"] < 1e-11


@pytest.mark.parametrize("direction", ["LEFT_TO_RIGHT", "RIGHT_TO_LEFT"])
def test_recovery_acceptance_gates(recovery, direction):
    diagnostics = recovery["diagnostics"][direction]
    assert diagnostics["design_rank"] == ACCEPTANCE_GATES["design_rank"] == 9
    assert diagnostics["min_tap_exact_solution"] >= ACCEPTANCE_GATES["min_tap"]
    assert abs(diagnostics["tap_sum_exact_solution"] - 1.0) <= (
        ACCEPTANCE_GATES["tap_sum_tolerance"]
    )
    assert diagnostics["max_abs_residual_exact_solution"] <= (
        ACCEPTANCE_GATES["max_abs_residual_blocks"]
    )
    low, high = ACCEPTANCE_GATES["positive_support_within"]
    support = diagnostics["positive_mass_support"]
    assert low <= support[0] and support[1] <= high


def test_aggregate_mode_lag_matches_the_aprime_forensic_reference(recovery):
    assert recovery["aggregate_diagnostics"]["mode_lag"] == 2


def test_recovered_taps_equal_the_authority_values(recovery):
    assert recovery["recovered_kernels"] == {
        direction: list(taps) for direction, taps in RECOVERED_TAPS.items()
    }
    assert len(RECOVERED_TAPS["LEFT_TO_RIGHT"]) == KERNEL_LENGTH == 9
    assert KERNEL_LAGS == tuple(range(9))


def test_per_direction_diagnostics_match_the_frozen_reference(recovery):
    left = recovery["diagnostics"]["LEFT_TO_RIGHT"]
    right = recovery["diagnostics"]["RIGHT_TO_LEFT"]
    assert left["mode_lag"] == 3
    assert right["mode_lag"] == 2
    assert left["group_delay_ticks"] == pytest.approx(3.339950418234, abs=1e-12)
    assert right["group_delay_ticks"] == pytest.approx(2.6704961914, abs=1e-12)
    assert left["design_rows"] == 494
    assert right["design_rows"] == 456


# --------------------------------------------------------------------------
# Normalization is applied once at load (authority 5.3, blocker FIR_KERNEL_NOT_NORMALIZED)
# --------------------------------------------------------------------------

def test_raw_left_to_right_taps_are_short_of_unit_mass():
    assert math.fsum(RECOVERED_TAPS["LEFT_TO_RIGHT"]) == 0.9999999999
    assert math.fsum(RECOVERED_TAPS["RIGHT_TO_LEFT"]) == 1.0


def test_frozen_kernel_is_normalized_for_every_direction():
    for direction in RECOVERED_TAPS:
        taps = frozen_kernel(direction)
        assert math.fsum(taps) == 1.0
        assert_normalized(taps)


def test_unnormalized_taps_are_refused_by_the_normalization_guard():
    with pytest.raises(ExperimentIIIError) as caught:
        assert_normalized(RECOVERED_TAPS["LEFT_TO_RIGHT"])
    assert caught.value.blocker == "FIR_KERNEL_NOT_NORMALIZED"
    # RIGHT_TO_LEFT already sums to exactly 1.0 and is unchanged by normalization.
    assert_normalized(RECOVERED_TAPS["RIGHT_TO_LEFT"])
    assert list(frozen_kernel("RIGHT_TO_LEFT")) == list(
        RECOVERED_TAPS["RIGHT_TO_LEFT"]
    )


def test_normalization_changes_left_to_right_taps_measurably():
    raw = RECOVERED_TAPS["LEFT_TO_RIGHT"]
    normalized = frozen_kernel("LEFT_TO_RIGHT")
    deltas = [abs(a - b) for a, b in zip(raw, normalized, strict=True)]
    assert max(deltas) > 0.0
    # The shift is invisible at the 1e-9 label tolerance but not at 1e-12.
    assert max(deltas) < 1e-9


def test_negative_zero_tap_is_treated_as_positive_zero():
    assert RECOVERED_TAPS["RIGHT_TO_LEFT"][8] == 0.0
    assert math.copysign(1.0, RECOVERED_TAPS["RIGHT_TO_LEFT"][8]) == 1.0
    assert kernel_positive_mass_support(RECOVERED_TAPS["RIGHT_TO_LEFT"]) == (0, 7)
    assert kernel_mode_lag(RECOVERED_TAPS["RIGHT_TO_LEFT"]) == 2
    assert kernel_group_delay_ticks(RECOVERED_TAPS["RIGHT_TO_LEFT"]) == pytest.approx(
        2.6704961914, abs=1e-12
    )


# --------------------------------------------------------------------------
# Target manifest (authority 2.5, 4.6, 5.4)
# --------------------------------------------------------------------------

@pytest.fixture(scope="module")
def aprime_wall_window():
    unit = next(
        candidate
        for candidate in aprime.aprime_materialized_units()
        if candidate.unit_id.endswith("_wall")
    )
    positions, _ = aprime.aprime_generate_path(
        noise_seed=unit.noise_seed,
        start_world_x=unit.start_world_x,
        direction=unit.direction,
        q=unit.motion_noise_q,
        speed=unit.speed_blocks_per_second,
        frames=unit.expected_frames,
    )
    return unit, [float(value) for value in positions]


def test_target_window_is_nineteen_consecutive_rows(aprime_wall_window):
    unit, positions = aprime_wall_window
    window = build_target_window(unit.trajectory_id, unit.direction, positions)
    indices = window.target_model_frame_indices
    assert len(indices) == TARGET_ROWS_PER_CAPTURE == 19
    assert list(indices) == list(range(indices[0], indices[0] + 19))
    assert indices[0] >= FIRST_FULLY_RESOLVED_TICK


def test_target_window_has_no_phase_offset(aprime_wall_window):
    """The window is the EARLIEST eligible run; A-prime's phase offsets are gone."""
    unit, positions = aprime_wall_window
    selected = select_target_window(positions)
    window = build_target_window(unit.trajectory_id, unit.direction, positions)
    assert selected == (
        window.target_model_frame_indices[0],
        window.target_model_frame_indices[-1] + 1,
    )
    for offset in (3, 6, 9, 12):
        assert window.target_model_frame_indices[0] != selected[0] + offset


def test_every_target_row_is_counterfactually_fully_occluded(aprime_wall_window):
    unit, positions = aprime_wall_window
    window = build_target_window(unit.trajectory_id, unit.direction, positions)
    assert set(window.extent_classes) == {
        ExtentClassName.EXTENT_FULLY_OCCLUDED.value
    }


def test_context_ages_run_one_to_nineteen(aprime_wall_window):
    unit, positions = aprime_wall_window
    window = build_target_window(unit.trajectory_id, unit.direction, positions)
    assert list(window.context_ages) == list(range(1, 20))
    anchor = window.last_preocclusion_model_frame_idx
    assert anchor == window.target_model_frame_indices[0] - 1


def test_context_boundary_is_at_fifteen_sixteen():
    assert [evidence_in_context(age) for age in (14, 15)] == [True, True]
    assert [evidence_in_context(age) for age in (16, 19)] == [False, False]


def test_shifted_window_refuses_rather_than_reporting_a_shifted_age():
    occluded = ExtentClassName.EXTENT_FULLY_OCCLUDED
    visible = ExtentClassName.EXTENT_FULLY_VISIBLE
    classes = [visible] * 10 + [occluded] * 30
    # A window starting one row after the onset would give ages 2..20.
    with pytest.raises(ExperimentIIIError) as caught:
        context_ages(classes, list(range(11, 30)))
    assert caught.value.blocker == "TOKEN_CONTEXT_AGE_UNVERIFIED"
    assert context_ages(classes, list(range(10, 29))) == tuple(range(1, 20))


# --------------------------------------------------------------------------
# A.7 — same target rows and labels across all five conditions
# --------------------------------------------------------------------------

def _window_per_condition(unit, positions) -> dict[str, TargetWindow]:
    return {
        condition.value: build_target_window(
            unit.trajectory_id, unit.direction, positions
        )
        for condition in ConditionId
    }


def test_target_rows_are_identical_across_all_five_conditions(aprime_wall_window):
    unit, positions = aprime_wall_window
    per_condition = _window_per_condition(unit, positions)
    assert_rows_identical_across_conditions(per_condition)
    reference = per_condition["L0"]
    for condition in ConditionId:
        assert (
            per_condition[condition.value].target_model_frame_indices
            == reference.target_model_frame_indices
        )
        assert per_condition[condition.value].labels == reference.labels


def test_mutated_condition_rows_are_detected(aprime_wall_window):
    unit, positions = aprime_wall_window
    per_condition = _window_per_condition(unit, positions)
    reference = per_condition["L2"]
    shifted = tuple(
        index + 1 for index in reference.target_model_frame_indices
    )
    per_condition["L2"] = TargetWindow(
        identity=reference.identity,
        direction=reference.direction,
        target_model_frame_indices=shifted,
        labels=reference.labels,
        context_ages=reference.context_ages,
        last_preocclusion_model_frame_idx=reference.last_preocclusion_model_frame_idx,
        extent_classes=reference.extent_classes,
    )
    with pytest.raises(ExperimentIIIError) as caught:
        assert_rows_identical_across_conditions(per_condition)
    assert caught.value.blocker == "TARGET_ROW_CONDITION_DIVERGENCE"


def test_labels_use_the_normalized_kernel(aprime_wall_window):
    unit, positions = aprime_wall_window
    window = build_target_window(unit.trajectory_id, unit.direction, positions)
    expected = causal_fir_targets(
        positions,
        list(window.target_model_frame_indices),
        list(frozen_kernel(unit.direction)),
    )
    assert list(window.labels) == expected
    assert list(window.labels) == fir_labels(
        positions, window.target_model_frame_indices, unit.direction
    )
