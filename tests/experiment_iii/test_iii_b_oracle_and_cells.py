"""Group D — D.1, D.5-D.10: amendment binding, folds, the oracle and VIS6.

CPU only. No Minecraft, no model, no GPU.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from mineocclude.experiment_iii.authority import (
    BINDING_Q_SET,
    DIAGNOSTIC_Q_FALLBACK,
    DT_SECONDS,
    LANE_MAX,
    LANE_MIN,
    SPEED_BLOCKS_PER_SECOND,
    direction_sign,
    machine_authority,
)
from mineocclude.experiment_iii.cohort import candidate_at, generate_path
from mineocclude.experiment_iii.errors import ExperimentIIIError
from mineocclude.experiment_iii.fir import RECOVERED_TAPS, frozen_kernel
from mineocclude.experiment_iii.iii_b_cells import (
    Q_HIGH,
    Q_LOW,
    Q_MID,
    assert_no_cross_q_fold_leakage,
    build_iii_b_cell,
)
from mineocclude.experiment_iii.iii_b_oracle import (
    TAU_MAX,
    affine_first_positive_tau,
    affine_last_negative_tau,
    affine_sigma2,
    assert_no_fitted_input,
    c_direction,
    cumulative_mass,
    gbar,
    mu_tau,
    oracle_specification,
    oracle_validation_receipt,
    s_tau,
    sigma,
    sigma2,
)
from mineocclude.experiment_iii.iii_b_package import amendment_hash_binding
from mineocclude.experiment_iii.iii_b_vis import (
    VIS_ROWS,
    clamp_free_mask,
    select_vis_window,
    vis_coverage,
)
from mineocclude.experiment_iii.schema import ExtentClassName
from mineocclude.experiment_iii.target_manifest import eligibility_mask

from tests.experiment_iii._iii_b_synthetic import identity_rows

DIRECTIONS = ("LEFT_TO_RIGHT", "RIGHT_TO_LEFT")
ALL_Q = (*BINDING_Q_SET, DIAGNOSTIC_Q_FALLBACK)


def _s_tau_from_taps(taps, tau: int) -> float:
    """``S(tau)`` from an arbitrary tap vector, under the frozen ``H`` rule."""
    masses = [math.fsum(taps[: index + 1]) for index in range(len(taps))]
    return math.fsum(
        (masses[m] if m < len(masses) else 1.0) ** 2 for m in range(tau)
    )


# --------------------------------------------------------------------------
# D.1 — Amendment hash binding
# --------------------------------------------------------------------------

def test_d1_machine_authority_records_both_amendment_hashes():
    machine = machine_authority()
    amendment = machine["amendments"][0]
    assert "phase0_amendment_md_sha256" in amendment
    assert "phase0_amendment_json_sha256" in amendment


def test_d1_both_amendment_files_exist_and_recompute_to_the_recorded_hashes():
    binding = amendment_hash_binding()
    assert binding["both_files_exist"] is True
    assert binding["recomputed_hashes_match_the_machine_authority"] is True
    machine = machine_authority()["amendments"][0]
    assert binding["phase0_amendment_md_sha256"] == machine["phase0_amendment_md_sha256"]
    assert (
        binding["phase0_amendment_json_sha256"]
        == machine["phase0_amendment_json_sha256"]
    )


# --------------------------------------------------------------------------
# D.5 — Cross-`q` fold identity
# --------------------------------------------------------------------------

@pytest.fixture(scope="module")
def cells():
    rows = identity_rows(6)
    return [build_iii_b_cell(row, q) for row in rows for q in (Q_LOW, Q_MID, Q_HIGH)]


def test_d5_every_q_variant_shares_the_identity_outer_fold_and_inner_rotation(cells):
    by_identity: dict[str, set[tuple[int, int]]] = {}
    for cell in cells:
        by_identity.setdefault(cell.identity, set()).add(
            (cell.outer_fold, cell.inner_rotation)
        )
    assert by_identity, "the fixture produced no cells"
    assert all(len(folds) == 1 for folds in by_identity.values())
    assert_no_cross_q_fold_leakage(cells)


def test_d5_q_appears_nowhere_in_fold_assignment(cells):
    machine = machine_authority()["experiment_iii_b"]["folds"]
    assert machine["q_enters_fold_assignment"] is False
    assert machine["cross_q_identity_leakage_possible"] is False
    # The fold is a property of the identity: the same identity at three q values
    # yields one fold, and the assignment never reads q.
    folds = {cell.identity: cell.outer_fold for cell in cells}
    for cell in cells:
        assert cell.outer_fold == folds[cell.identity]


def test_d5_a_deliberately_leaking_assignment_is_detected(cells):
    leaking = list(cells)
    victim = leaking[0]
    leaking[0] = type(victim)(
        **{
            **{field: getattr(victim, field) for field in victim.__dataclass_fields__},
            "outer_fold": victim.outer_fold + 1,
        }
    )
    with pytest.raises(ExperimentIIIError) as error:
        assert_no_cross_q_fold_leakage(leaking)
    assert error.value.blocker == "B_CROSS_Q_FOLD_LEAKAGE"


def test_d5_no_identity_appears_in_its_own_training_set_across_q(cells):
    for cell in cells:
        training = [other for other in cells if other.outer_fold != cell.outer_fold]
        assert cell.identity not in {other.identity for other in training}


# --------------------------------------------------------------------------
# D.6 — Oracle exactness on FSUM-NORMALIZED taps
# --------------------------------------------------------------------------

def test_d6_taps_are_fsum_normalized_at_load_before_any_H_or_S():
    for direction in DIRECTIONS:
        normalized = frozen_kernel(direction)
        raw = RECOVERED_TAPS[direction]
        total = math.fsum(raw)
        assert math.fsum(normalized) == 1.0
        assert normalized == tuple(value / total for value in raw)
        # H is the cumulative mass of the NORMALIZED kernel.
        assert cumulative_mass(direction)[-1] == 1.0


def test_d6_unnormalized_left_to_right_taps_fail_the_1e_12_tolerance():
    spec = oracle_specification()
    expected = spec["max_S_tau_error_if_unnormalized"]
    assert math.fsum(RECOVERED_TAPS["LEFT_TO_RIGHT"]) == 0.9999999999
    assert math.fsum(RECOVERED_TAPS["RIGHT_TO_LEFT"]) == 1.0
    for direction in DIRECTIONS:
        frozen = spec["per_direction"][direction]["S_tau_exact_tau_0_to_19"]
        raw_error = max(
            abs(_s_tau_from_taps(RECOVERED_TAPS[direction], tau) - frozen[tau])
            for tau in range(len(frozen))
        )
        assert raw_error == expected[direction]
    assert expected["LEFT_TO_RIGHT"] > 1e-12
    assert expected["RIGHT_TO_LEFT"] == 0.0


def test_d6_normalized_taps_reproduce_S_tau_exactly():
    spec = oracle_specification()
    for direction in DIRECTIONS:
        frozen = spec["per_direction"][direction]["S_tau_exact_tau_0_to_19"]
        for tau, value in enumerate(frozen):
            assert abs(s_tau(direction, tau) - value) <= 1e-12
        assert max(abs(s_tau(direction, tau) - frozen[tau]) for tau in range(20)) == 0.0


def test_d6_sigma_is_strictly_positive_for_every_tau_at_every_q():
    for direction in DIRECTIONS:
        for q in ALL_Q:
            for tau in range(1, TAU_MAX + 1):
                assert sigma(direction, q, tau) > 0.0


def test_d6_mu_uses_the_frozen_gbar_offset():
    for direction in DIRECTIONS:
        offset = gbar(direction)
        assert offset == oracle_specification()["per_direction"][direction][
            "fir_group_delay_ticks_gbar"
        ]
        for tau in range(0, TAU_MAX + 1):
            expected = 0.25 + direction_sign(direction) * SPEED_BLOCKS_PER_SECOND * DT_SECONDS * (
                tau - offset
            )
            assert mu_tau(0.25, direction, tau) == expected


def test_d6_no_oracle_quantity_reads_an_activation_prediction_or_fitted_parameter():
    for label in ("activation", "prediction", "fitted_parameter", "sigma_hat"):
        with pytest.raises(ExperimentIIIError) as error:
            assert_no_fitted_input(**{label: 1.0})
        assert error.value.blocker == "B_ORACLE_MISMATCH"
    assert_no_fitted_input(activation=None, prediction=None)


def test_d6_oracle_validation_receipt_passes():
    receipt = oracle_validation_receipt()
    assert receipt["passed"] is True
    assert receipt["max_abs_S_tau_error"] == 0.0
    assert receipt["max_abs_sigma_error"] == 0.0
    assert receipt["affine_form_evaluated_below_tau_8"] is False


# --------------------------------------------------------------------------
# D.7 — Affine-form rejection and the DIRECTION-SPECIFIC boundary
# --------------------------------------------------------------------------

def test_d7_left_to_right_affine_is_negative_at_1_to_4_and_positive_from_5():
    for tau in (1, 2, 3, 4):
        assert affine_sigma2("LEFT_TO_RIGHT", Q_MID, tau, allow_below_tau_8=True) < 0.0
    for tau in range(5, TAU_MAX + 1):
        assert affine_sigma2("LEFT_TO_RIGHT", Q_MID, tau, allow_below_tau_8=True) > 0.0


def test_d7_right_to_left_affine_is_negative_at_1_to_3_and_POSITIVE_at_4():
    for tau in (1, 2, 3):
        assert affine_sigma2("RIGHT_TO_LEFT", Q_MID, tau, allow_below_tau_8=True) < 0.0
    # tau = 4 is POSITIVE in this direction. A test demanding negativity at
    # tau = 1..4 in BOTH directions would fail a correct implementation.
    for tau in range(4, TAU_MAX + 1):
        assert affine_sigma2("RIGHT_TO_LEFT", Q_MID, tau, allow_below_tau_8=True) > 0.0


def test_d7_no_integer_tau_makes_the_affine_form_exactly_zero():
    for direction in DIRECTIONS:
        for q in ALL_Q:
            for tau in range(1, TAU_MAX + 1):
                assert affine_sigma2(direction, q, tau, allow_below_tau_8=True) != 0.0


def test_d7_boundary_integers_match_the_specification_and_the_machine_authority():
    spec = oracle_specification()
    machine = machine_authority()["experiment_iii_b"]["oracle"]
    assert spec["affine_last_negative_tau"] == {"LEFT_TO_RIGHT": 4, "RIGHT_TO_LEFT": 3}
    assert spec["affine_first_positive_tau"] == {"LEFT_TO_RIGHT": 5, "RIGHT_TO_LEFT": 4}
    assert machine["affine_last_negative_tau"] == spec["affine_last_negative_tau"]
    assert machine["affine_first_positive_tau"] == spec["affine_first_positive_tau"]
    for direction in DIRECTIONS:
        assert affine_last_negative_tau(direction) == spec["affine_last_negative_tau"][
            direction
        ]
        assert affine_first_positive_tau(direction) == spec[
            "affine_first_positive_tau"
        ][direction]
        assert c_direction(direction) < 0.0
        assert -c_direction(direction) == pytest.approx(
            spec["affine_sign_change_tau"][direction], abs=1e-12
        )


def test_d7_the_implementation_refuses_the_affine_form_below_tau_8():
    for direction in DIRECTIONS:
        for tau in range(0, 8):
            with pytest.raises(ExperimentIIIError) as error:
                affine_sigma2(direction, Q_MID, tau)
            assert error.value.blocker == "B_ORACLE_MISMATCH"


def test_d7_the_exact_form_is_strictly_positive_everywhere_and_agrees_from_tau_8():
    for direction in DIRECTIONS:
        for q in ALL_Q:
            for tau in range(1, TAU_MAX + 1):
                assert sigma2(direction, q, tau) > 0.0
            for tau in range(8, TAU_MAX + 1):
                assert abs(
                    affine_sigma2(direction, q, tau) - sigma2(direction, q, tau)
                ) <= 1e-12


# --------------------------------------------------------------------------
# D.8 — Cross-`q` sigma ratio
# --------------------------------------------------------------------------

def test_d8_sigma_ratio_is_sqrt_of_the_q_ratio_and_tau_independent():
    pairs = ((Q_HIGH, Q_LOW, 4.0), (Q_HIGH, Q_MID, 2.0), (Q_MID, Q_LOW, 2.0))
    for direction in DIRECTIONS:
        for q_high, q_low, expected in pairs:
            ratios = [
                sigma(direction, q_high, tau) / sigma(direction, q_low, tau)
                for tau in range(1, TAU_MAX + 1)
            ]
            for ratio in ratios:
                assert abs(ratio - expected) <= 1e-12
                assert abs(ratio - math.sqrt(q_high / q_low)) <= 1e-12
            assert max(ratios) - min(ratios) <= 1e-12


# --------------------------------------------------------------------------
# D.9 / D.10 — VIS6
# --------------------------------------------------------------------------

@pytest.fixture(scope="module")
def vis_paths():
    paths = {}
    for direction in DIRECTIONS:
        for index in range(4):
            candidate = candidate_at(direction, index)
            positions, _ = generate_path(
                candidate.seed,
                Q_MID,
                direction=direction,
                start_world_x=candidate.start_world_x,
            )
            paths[(direction, index)] = positions
    return paths


def test_d9_vis6_is_six_consecutive_fully_visible_clamp_free_rows(vis_paths):
    found = 0
    for (direction, index), positions in vis_paths.items():
        window = select_vis_window(f"e3_p9{index % 2}", positions, q=Q_MID)
        if not window.available:
            assert window.blocker == "B_VIS_UNAVAILABLE"
            continue
        found += 1
        indices = window.model_frame_indices
        assert len(indices) == VIS_ROWS == 6
        assert list(indices) == list(range(indices[0], indices[0] + 6))
        _, classes = eligibility_mask(positions)
        clamp_free = clamp_free_mask(positions)
        for row in indices:
            assert classes[row] is ExtentClassName.EXTENT_FULLY_VISIBLE
            assert clamp_free[row] is True
            assert row >= 15
    assert found > 0, "no path in the fixture produced a VIS6 window"


def test_d9_a_pre_occlusion_window_is_never_returned(vis_paths):
    from mineocclude.experiment_iii.target_manifest import select_target_window

    for positions in vis_paths.values():
        window = select_vis_window("e3_p90", positions, q=Q_MID)
        target = select_target_window(positions)
        if window.available and target is not None:
            assert window.model_frame_indices[0] >= target[1]


def test_d9_fewer_than_six_eligible_rows_records_the_blocker_without_failing():
    # A path pinned at the lane bound for its entire tail has no clamp-free
    # visible run; the selector must return empty and record the blocker.
    positions = np.full(180, LANE_MAX, dtype=np.float64)
    window = select_vis_window("e3_p90", positions, q=Q_MID)
    assert window.available is False
    assert window.model_frame_indices == ()
    assert window.blocker == "B_VIS_UNAVAILABLE"
    coverage = vis_coverage([window])
    assert coverage["cells_with_vis6"] == 0
    assert coverage["is_a_qualification_gate"] is False
    assert coverage["blocker_severity"] == "INFORMATIONAL"


def test_d10_pinned_rows_are_excluded_and_the_window_has_nonzero_variance(vis_paths):
    for positions in vis_paths.values():
        window = select_vis_window("e3_p90", positions, q=Q_MID)
        if not window.available:
            continue
        values = np.asarray(
            [positions[row] for row in window.model_frame_indices], dtype=np.float64
        )
        assert float(values.var()) > 0.0
        assert not np.any(values == LANE_MAX)
        assert not np.any(values == LANE_MIN)


def test_d10_a_tail_pinned_path_excludes_every_pinned_row():
    candidate = candidate_at("LEFT_TO_RIGHT", 0)
    positions, _ = generate_path(
        candidate.seed,
        Q_MID,
        direction="LEFT_TO_RIGHT",
        start_world_x=candidate.start_world_x,
    )
    pinned = np.array(positions, dtype=np.float64)
    pinned[150:] = LANE_MAX
    window = select_vis_window("e3_p90", pinned, q=Q_MID)
    if window.available:
        assert max(window.model_frame_indices) < 150
    clamp_free = clamp_free_mask(pinned)
    assert not any(clamp_free[150:])


def test_d10_vis_rows_is_frozen_at_six_and_the_provisional_eight_is_refused():
    machine = machine_authority()["experiment_iii_b"]["visible_controls"]
    assert machine["VIS_ROWS"] == 6
    assert machine["provisional_superseded_value"] == 8
    positions = np.zeros(180, dtype=np.float64)
    with pytest.raises(ExperimentIIIError) as error:
        select_vis_window("e3_p90", positions, q=Q_MID, rows=8)
    assert error.value.blocker == "B_VIS_UNAVAILABLE"
