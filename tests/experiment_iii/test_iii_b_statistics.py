"""Group D — D.11-D.20, D.32, D.33: U2, U3, the calibration battery and inference.

CPU only. Every "decoder" is an explicit analytic function of the frozen oracle,
so each planted effect is known exactly.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from mineocclude.experiment_iii.authority import machine_authority
from mineocclude.experiment_iii.errors import ExperimentIIIError
from mineocclude.experiment_iii.iii_b_calibration import (
    EPS,
    GUARDED_STATISTICS,
    MATERIAL_CLIPPING_THRESHOLD,
    RAW_SIGMA_STATISTICS,
    assert_guard_scope,
    assert_no_equivalence_claim,
    assert_positivity_rule_unchanged,
    assert_predictions_store_raw_sigma_hat,
    coverage,
    mean_gate,
    monotonicity,
    nll,
    positivity_report,
    scale_agreement,
    sigma_tilde,
)
from mineocclude.experiment_iii.iii_b_cells import Q_HIGH, Q_LOW, Q_MID
from mineocclude.experiment_iii.iii_b_inference import (
    ALPHA,
    BOOTSTRAP_B,
    PERMUTATION_B,
    U2_FAMILY_AT_DROP_LEVEL_1,
    U2_FAMILY_ORDER,
    U3_FAMILY_ORDER,
    assert_family,
    assert_no_holm_adjusted_interval_language,
    bootstrap_inversion,
    holm,
    within_identity_q_permutation_p_value,
)
from mineocclude.experiment_iii.iii_b_oracle import sigma
from mineocclude.experiment_iii.iii_b_package import LADDER_RUNGS, assert_claim_within_rung
from mineocclude.experiment_iii.iii_b_u2 import (
    CONFOUND_CONTROLS,
    NUISANCE_CELLS,
    U2_S3_CHANCE,
    WORDING_AFTER_CONTROLS_PASS,
    WORDING_BEFORE_CONTROLS_PASS,
    assert_confound_controls_present,
    context_boundary_secondary,
    matched_tau_differences,
    partial_rank_association,
    u2_analysis,
    u2_s1,
    u2_s2,
    u2_s3,
    wording_for,
)
from mineocclude.experiment_iii.iii_b_u3 import (
    ORACLE_SLOPE_RATIOS,
    identity_slopes,
    u3_analysis,
    u3_s1,
    u3_s2,
    u3_s3,
)

from tests.experiment_iii._iii_b_synthetic import (
    IDENTITY_DIRECTION,
    Q_LEVELS,
    TAU_PRIMARY,
    direction_confound_fixture,
    no_effect_predictions,
    synthetic_predictions,
)

SEED = 20260830


@pytest.fixture(scope="module")
def planted():
    """sigma_hat = 1.0 * sigma_oracle: the planted response IS the oracle."""
    return synthetic_predictions(mu_error_sd=0.0, baseline_mu_error_sd=0.0)


@pytest.fixture(scope="module")
def confound_rows():
    return direction_confound_fixture()


# --------------------------------------------------------------------------
# D.11 — U2 statistics and the U2-S2 direction control
# --------------------------------------------------------------------------

def test_d11_u2_s1_recovers_the_planted_matched_tau_contrast(planted):
    identities, matrix = matched_tau_differences(planted)
    expected = float(
        np.mean(
            [
                sigma(IDENTITY_DIRECTION[name], Q_HIGH, tau)
                - sigma(IDENTITY_DIRECTION[name], Q_LOW, tau)
                for name in identities
                for tau in TAU_PRIMARY
            ]
        )
    )
    assert float(matrix.mean()) == pytest.approx(expected, abs=1e-12)
    result = u2_s1(planted, seed=SEED)
    assert result["observed"] == pytest.approx(expected, abs=1e-12)
    assert result["ci_low"] > 0.0
    assert result["matching"] == "OCCLUSION_AGE_TAU"


def test_d11_tau_matching_is_by_occlusion_age_never_by_absolute_frame_index(planted):
    rows = [dict(row) for row in planted]
    rows[0]["tau"] = float(rows[0]["tau"])
    with pytest.raises(ExperimentIIIError) as error:
        matched_tau_differences(rows)
    assert error.value.blocker == "B_TAU_ALIGNMENT_ERROR"


def test_d11_u2_s3_recovers_the_planted_ordering_proportion(planted):
    result = u2_s3(planted, seed=SEED)
    # The planted response is monotone in q for every identity.
    assert result["observed"] == 1.0
    assert all(value == 1 for value in result["per_identity_agreement"].values())
    assert result["chance_level"] == pytest.approx(1.0 / 6.0)


def test_d11_fixture_has_exactly_zero_q_sensitivity(confound_rows):
    table: dict[tuple[str, int], set[float]] = {}
    for row in confound_rows:
        table.setdefault((row["identity"], row["tau"]), set()).add(row["sigma_hat"])
    spreads = [max(values) - min(values) for values in table.values()]
    assert max(spreads) == 0.0


@pytest.fixture(scope="module")
def confound_tau_only(confound_rows):
    return u2_s2(confound_rows, seed=SEED, conditioning="TAU_ONLY")


@pytest.fixture(scope="module")
def confound_tau_by_direction(confound_rows):
    return u2_s2(confound_rows, seed=SEED, conditioning="TAU_X_DIRECTION")


def test_d11_the_false_positive_pathway_exists_under_tau_only(confound_tau_only):
    reference = machine_authority()["experiment_iii_b"]["u2_family"]["S2"][
        "negative_control_fixture"
    ]
    assert confound_tau_only["rho"] == pytest.approx(
        reference["reference_rho_tau_only"],
        abs=reference["reference_rho_tau_only_tolerance"],
    )
    assert confound_tau_only["ci_low"] > 0.0


def test_d11_tau_by_direction_residual_is_degenerate_and_the_rule_fires(
    confound_rows, confound_tau_by_direction
):
    hat = [row["sigma_hat"] for row in confound_rows]
    oracle = [row["sigma_oracle"] for row in confound_rows]
    tau = [row["tau"] for row in confound_rows]
    code = [0 if row["direction"] == "LEFT_TO_RIGHT" else 1 for row in confound_rows]
    detail = partial_rank_association(hat, oracle, tau, code)
    assert detail["var_residual_sigma_hat"] <= detail["tolerance_sigma_hat"]
    assert detail["tolerance_sigma_hat"] == pytest.approx(1.0535e-10, rel=1e-3)
    assert confound_tau_by_direction["U2_S2_ZERO_VARIANCE_CASE"] is True


def test_d11_the_zero_variance_rule_maps_rho_to_zero_and_p_to_one(
    confound_tau_by_direction,
):
    assert confound_tau_by_direction["rho"] == 0.0
    assert confound_tau_by_direction["p_value"] == 1.0
    assert confound_tau_by_direction["zero_variance_replicates"] == BOOTSTRAP_B
    assert confound_tau_by_direction["zero_variance_replicate_fraction"] == 1.0


def test_d11_no_nan_is_produced_or_compared_in_the_decision_path(
    confound_tau_by_direction,
):
    for key in ("rho", "ci_low", "ci_high", "p_value"):
        assert math.isfinite(confound_tau_by_direction[key])
        assert not math.isnan(confound_tau_by_direction[key])


def test_d11_no_positive_declaration_on_the_negative_control(confound_rows):
    # U2-S2 fails its clause, so U2_POSITIVE cannot be declared even with the
    # controls nominally passing.
    result = u2_analysis(confound_rows, seed=SEED, controls_passed=True)
    assert result["conjunction_clauses"]["U2-S2"] is False
    assert result["U2_POSITIVE"] is False
    assert result["holm_adjusted_p_values"]["U2-S2"] == 1.0


def test_d11_nuisance_structure_is_exactly_thirty_cells(confound_tau_by_direction):
    assert NUISANCE_CELLS == 30
    assert confound_tau_by_direction["nuisance_cells"] == 30
    machine = machine_authority()["experiment_iii_b"]["u2_family"]["S2"]
    assert machine["nuisance_cells"] == 30
    assert machine["conditioning"] == "tau_x_direction"


def test_d11_ranking_happens_over_the_pooled_set_first(confound_tau_by_direction):
    assert confound_tau_by_direction["order"] == "RANK_POOLED_FIRST_THEN_RESIDUALIZE"


def test_d11_a_singleton_cell_yields_residual_zero_and_is_retained():
    # One observation in its own (tau, direction) cell: residual exactly 0.0,
    # retained rather than dropped.
    result = partial_rank_association(
        [1.0, 2.0, 3.0, 9.0],
        [1.0, 2.0, 3.0, 4.0],
        [1, 1, 1, 2],
        [0, 0, 0, 1],
    )
    assert result["observations"] == 4
    assert math.isfinite(result["rho"])


def test_d11_an_unknown_conditioning_is_refused():
    with pytest.raises(ExperimentIIIError) as error:
        partial_rank_association([1.0, 2.0], [1.0, 2.0], [1, 2], [0, 1], conditioning="Q")
    assert error.value.blocker == "B_U2_S2_CONDITIONING_MISMATCH"


# --------------------------------------------------------------------------
# D.12 — Within-identity permutation null
# --------------------------------------------------------------------------

def test_d12_permutation_b_and_denominator_are_frozen(planted):
    result = u2_s1(planted, seed=SEED)
    assert result["permutations"] == PERMUTATION_B == 9999
    assert result["p_value"] == pytest.approx(
        (1 + 0) / 10_000
    ) or result["p_value"] >= 1 / 10_000


def test_d12_the_null_holds_tau_identity_and_fold_fixed():
    matrix = np.tile(np.arange(1.0, 16.0), (25, 1))
    result = within_identity_q_permutation_p_value(matrix, seed=1)
    assert result["stratum"] == "IDENTITY_X_TAU"
    assert result["denominator"] == 10_000
    assert result["p_value"] == 1 / 10_000


def test_d12_p_value_is_approximately_uniform_under_no_effect():
    rng = np.random.default_rng(99)
    p_values = []
    for draw in range(24):
        matrix = rng.normal(0.0, 1.0, size=(25, 15))
        p_values.append(
            within_identity_q_permutation_p_value(matrix, seed=1000 + draw)["p_value"]
        )
    sample = np.asarray(p_values)
    assert 0.25 <= float(sample.mean()) <= 0.75
    assert float(sample.min()) < 0.5 < float(sample.max())


def test_d12_a_matrix_with_a_non_finite_difference_is_refused():
    matrix = np.zeros((3, 4))
    matrix[0, 0] = np.nan
    with pytest.raises(ExperimentIIIError) as error:
        within_identity_q_permutation_p_value(matrix, seed=1)
    assert error.value.blocker == "B_INFERENCE_PROCEDURE_MISMATCH"


# --------------------------------------------------------------------------
# D.13 — Holm family sizes
# --------------------------------------------------------------------------

def test_d13_u2_family_is_exactly_three_and_two_at_drop_level_1():
    assert U2_FAMILY_ORDER == ("U2-S1", "U2-S2", "U2-S3")
    assert U2_FAMILY_AT_DROP_LEVEL_1 == ("U2-S1", "U2-S2")
    machine = machine_authority()["experiment_iii_b"]["inferential_procedure"]["families"]
    assert machine["U2"]["size"] == 3
    assert machine["U2"]["size_at_drop_LEVEL_1"] == 2
    assert machine["U3"]["size"] == 2


def test_d13_u3_family_is_exactly_two():
    assert U3_FAMILY_ORDER == ("U3-S1", "U3-S2")
    adjusted = holm({"U3-S1": 0.01, "U3-S2": 0.02}, family_order=U3_FAMILY_ORDER)
    assert adjusted["U3-S1"] == pytest.approx(0.02)
    assert adjusted["U3-S2"] == pytest.approx(0.02)


def test_d13_adding_or_removing_a_statistic_is_rejected():
    with pytest.raises(ExperimentIIIError) as error:
        holm(
            {"U2-S1": 0.01, "U2-S2": 0.02, "U2-S3": 0.03, "U2-S4": 0.04},
            family_order=U2_FAMILY_ORDER,
        )
    assert error.value.blocker == "B_U2_FAMILY_ALTERED"
    with pytest.raises(ExperimentIIIError):
        holm({"U2-S1": 0.01, "U2-S2": 0.02}, family_order=U2_FAMILY_ORDER)


def test_d13_statistics_outside_every_family_are_never_holm_corrected(planted):
    outside = u3_s3(planted)
    assert outside["enters_family"] is False
    assert outside["holm_corrected"] is False
    boundary = context_boundary_secondary(planted, seed=SEED)
    assert boundary["enters_holm_family"] is False
    battery = machine_authority()["experiment_iii_b"]["calibration_battery"]
    assert battery["calibration_holm_corrected"] is False


# --------------------------------------------------------------------------
# D.14 — All eight confound controls present
# --------------------------------------------------------------------------

def test_d14_all_eight_controls_are_named_and_frozen():
    assert len(CONFOUND_CONTROLS) == 8
    machine = machine_authority()["experiment_iii_b"]["confound_controls"]
    assert machine["count"] == 8
    assert tuple(machine["controls"]) == CONFOUND_CONTROLS
    assert_confound_controls_present(CONFOUND_CONTROLS)


def test_d14_a_missing_control_fails_the_stage():
    for omitted in CONFOUND_CONTROLS:
        reported = [name for name in CONFOUND_CONTROLS if name != omitted]
        with pytest.raises(ExperimentIIIError) as error:
            assert_confound_controls_present(reported)
        assert error.value.blocker == "B_U2_ANALYSIS_FAIL"
        assert omitted in str(error.value)


def test_d14_an_extra_control_is_also_refused():
    with pytest.raises(ExperimentIIIError):
        assert_confound_controls_present([*CONFOUND_CONTROLS, "AD_HOC_CONTROL"])


# --------------------------------------------------------------------------
# D.15 — Wording gate
# --------------------------------------------------------------------------

def test_d15_wording_before_the_controls_pass():
    assert wording_for(controls_passed=False) == WORDING_BEFORE_CONTROLS_PASS
    assert WORDING_BEFORE_CONTROLS_PASS == "Q_REGIME_RELEVANT_INFORMATION"


def test_d15_wording_after_the_controls_pass():
    assert wording_for(controls_passed=True) == WORDING_AFTER_CONTROLS_PASS
    machine = machine_authority()["experiment_iii_b"]["confound_controls"]
    assert machine["wording_before_controls_pass"] == WORDING_BEFORE_CONTROLS_PASS
    assert machine["wording_after_controls_pass"] == WORDING_AFTER_CONTROLS_PASS


def test_d15_calibrated_belief_state_is_never_emitted_outside_rung_4():
    assert "CALIBRATED" in wording_for(controls_passed=True, ladder_rung=4)
    for rung in (1, 2, 3, 5, 6, 7):
        assert wording_for(controls_passed=True, ladder_rung=rung) == (
            WORDING_AFTER_CONTROLS_PASS
        )
        with pytest.raises(ExperimentIIIError):
            assert_claim_within_rung("a calibrated belief state", rung)
    assert LADDER_RUNGS[4]["is_strongest"] is True


# --------------------------------------------------------------------------
# D.16 / D.17 — U3
# --------------------------------------------------------------------------

@pytest.fixture(scope="module")
def u3_result(planted):
    return u3_analysis(planted, seed=SEED, u2_passed=True)


def test_d16_u3_s1_recovers_the_planted_per_identity_slopes(planted):
    slopes = identity_slopes(planted)
    for identity, direction in IDENTITY_DIRECTION.items():
        for level in Q_LEVELS:
            taus = np.asarray(TAU_PRIMARY, dtype=np.float64)
            values = np.asarray(
                [sigma(direction, level, int(tau)) for tau in TAU_PRIMARY],
                dtype=np.float64,
            )
            centred = taus - taus.mean()
            expected = float(np.dot(centred, values - values.mean()) / np.dot(centred, centred))
            assert slopes[identity][level] == pytest.approx(expected, abs=1e-12)


def test_d16_u3_s2_recovers_the_planted_slope_interaction(u3_result):
    member = u3_result["members"]["U3-S2"]
    assert member["observed"] > 0.0
    assert member["ci_low"] > 0.0
    assert member["role"] == "MAIN_PROTECTION_AGAINST_ADDITIVE_CLOCK_PLUS_Q_CATEGORY"


def test_d16_u3_s3_is_descriptive_and_matches_the_oracle_sqrt_q_ratios(planted):
    result = u3_s3(planted)
    assert result["enters_family"] is False
    assert result["oracle_ratios"] == ORACLE_SLOPE_RATIOS
    for name, expected in ORACLE_SLOPE_RATIOS.items():
        assert result["observed_ratios"][name] == pytest.approx(expected, rel=1e-9)


def test_d17_u3_claims_are_scientific_only_when_u2_passes(planted):
    passing = u3_analysis(planted, seed=SEED, u2_passed=True)
    assert passing["claim_status"] == "SCIENTIFIC"
    assert passing["scientific_claims_permitted"] is True
    failing = u3_analysis(planted, seed=SEED, u2_passed=False)
    assert failing["claim_status"] == "DESCRIPTIVE"
    assert failing["scientific_claims_permitted"] is False
    # U3 is still COMPUTED when U2 does not pass.
    assert failing["members"]["U3-S1"]["observed"] == passing["members"]["U3-S1"]["observed"]
    assert failing["members"]["U3-S2"]["observed"] == passing["members"]["U3-S2"]["observed"]


def test_d17_an_additive_clock_plus_q_category_model_yields_delta_zero():
    rows = []
    for identity, direction in IDENTITY_DIRECTION.items():
        for level, offset in zip(Q_LEVELS, (0.0, 0.1, 0.2)):
            for tau in TAU_PRIMARY:
                rows.append(
                    {
                        "identity": identity,
                        "direction": direction,
                        "q": level,
                        "tau": tau,
                        "sigma_oracle": sigma(direction, level, tau),
                        "sigma_hat": 0.01 * tau + offset,
                    }
                )
    result = u3_s2(rows, seed=SEED)
    assert result["observed"] == pytest.approx(0.0, abs=1e-12)
    assert result["ci_low"] <= 0.0 <= result["ci_high"]


# --------------------------------------------------------------------------
# D.18 — Scale agreement
# --------------------------------------------------------------------------

@pytest.mark.parametrize("scale,offset", [(1.0, 0.0), (2.5, 0.3)])
def test_d18_recovered_slope_and_intercept_match_the_planted_values(scale, offset):
    rows = synthetic_predictions(scale=scale, offset=offset)
    result = scale_agreement(rows, seed=SEED)
    assert result["slope"] == pytest.approx(scale, abs=1e-9)
    assert result["intercept"] == pytest.approx(offset, abs=1e-9)
    assert result["uses_raw_sigma_hat"] is True


def test_d18_the_strong_criterion_fires_only_on_slope_1_and_intercept_0():
    identity_fit = scale_agreement(synthetic_predictions(), seed=SEED)
    assert identity_fit["strong_criterion_passes"] is True
    mismatched = scale_agreement(synthetic_predictions(scale=2.5, offset=0.3), seed=SEED)
    assert mismatched["strong_criterion_passes"] is False


def test_d18_the_regression_runs_on_raw_sigma_hat_with_no_positivity_guard():
    rows = synthetic_predictions(sigma_shift=-0.5)
    assert min(row["sigma_hat"] for row in rows) < 0.0
    result = scale_agreement(rows, seed=SEED)
    assert result["intercept"] == pytest.approx(-0.5, abs=1e-9)
    with pytest.raises(ExperimentIIIError):
        assert_guard_scope("A_SCALE_AGREEMENT")


def test_d18_a_passing_criterion_is_worded_as_a_non_rejection():
    result = scale_agreement(synthetic_predictions(), seed=SEED)
    assert "not detected at this power" in result["wording"]
    assert result["equivalence_test_run"] is False
    assert_no_equivalence_claim(result["wording"])
    for refused in ("proven scale-calibrated", "equivalent to the oracle scale"):
        with pytest.raises(ExperimentIIIError):
            assert_no_equivalence_claim(refused)


# --------------------------------------------------------------------------
# D.19 — Conditional coverage gate
# --------------------------------------------------------------------------

def test_d19_coverage_is_not_interpretable_when_the_mean_gate_fails(planted):
    result = coverage(planted, mean_gate_passes=False)
    assert result["status"] == "NOT_INTERPRETABLE"
    assert result["is_a_calibration_failure"] is False
    assert "empirical_coverage" not in result


def test_d19_coverage_is_computed_only_when_the_mean_gate_passes(planted):
    result = coverage(planted, mean_gate_passes=True)
    assert result["status"] == "INTERPRETABLE"
    assert result["uses_sigma_tilde"] is True
    assert 0.0 <= result["empirical_coverage"] <= 1.0
    assert "fraction_clipped" in result["positivity"]


def test_d19_the_mean_gate_reads_the_constant_velocity_baseline():
    identities = [f"e3_t{index:02d}" for index in range(1, 26)]
    decoded = {name: 0.10 for name in identities}
    baseline = {name: 0.20 for name in identities}
    gate = mean_gate(decoded, baseline, seed=SEED)
    assert gate["passes"] is True
    assert gate["ci_low"] > 0.0
    worse = mean_gate(baseline, decoded, seed=SEED)
    assert worse["passes"] is False


# --------------------------------------------------------------------------
# D.20 — Hybrid NLL
# --------------------------------------------------------------------------

def test_d20_both_variants_are_computed_and_the_hybrid_is_primary(planted):
    result = nll(planted, mean_gate_passes=True)
    assert result["primary_variant"] == "HYBRID_ORACLE_COMPATIBLE_MEAN_PLUS_DECODED_SIGMA"
    assert result["variants"]["HYBRID_ORACLE_COMPATIBLE_MEAN_PLUS_DECODED_SIGMA"] is not None
    assert result["variants"]["DECODED_MU_PLUS_DECODED_SIGMA"] is not None


def test_d20_the_decoded_mu_variant_is_withheld_when_the_mean_gate_fails(planted):
    result = nll(planted, mean_gate_passes=False)
    assert result["variants"]["DECODED_MU_PLUS_DECODED_SIGMA"] is None
    assert result["variants"]["HYBRID_ORACLE_COMPATIBLE_MEAN_PLUS_DECODED_SIGMA"] is not None


def test_d20_both_variants_are_compared_against_the_two_frozen_baselines(planted):
    result = nll(planted, mean_gate_passes=True)
    assert set(result["baselines"]) == {"TAU_ONLY_SPREAD", "ORACLE_SPREAD_CEILING"}
    # The planted sigma_hat IS the oracle, so the hybrid matches the ceiling and
    # beats the tau-only spread baseline.
    hybrid = result["variants"]["HYBRID_ORACLE_COMPATIBLE_MEAN_PLUS_DECODED_SIGMA"]
    assert hybrid == pytest.approx(result["baselines"]["ORACLE_SPREAD_CEILING"], abs=1e-12)
    assert hybrid < result["baselines"]["TAU_ONLY_SPREAD"]
    assert result["enters_holm_family"] is False


def test_d20_the_hybrid_uses_the_frozen_oracle_compatible_mean(planted):
    machine = machine_authority()["experiment_iii_b"]["calibration_battery"]["D_nll"]
    assert machine["primary_variant"] == "HYBRID"
    assert machine["uses_sigma_tilde"] is True
    assert machine["reports_fraction_clipped"] is True
    assert nll(planted, mean_gate_passes=True)["uses_sigma_tilde"] is True


# --------------------------------------------------------------------------
# D.32 — Negative `sigma_hat` handling
# --------------------------------------------------------------------------

@pytest.fixture(scope="module")
def negative_rows():
    rows = synthetic_predictions(sigma_shift=-0.002)
    assert min(row["sigma_hat"] for row in rows) < 0.0
    return rows


def test_d32_eps_is_exactly_1e_4_read_from_the_authority():
    assert EPS == 1e-4
    machine = machine_authority()["experiment_iii_b"]["calibration_battery"][
        "sigma_positivity_rule"
    ]
    assert machine["EPS_blocks"] == EPS
    assert machine["rule"] == "sigma_tilde = max(sigma_hat, EPS)"
    values = np.asarray([-1.0, 0.0, 1e-5, 1e-4, 0.5])
    assert list(sigma_tilde(values)) == [EPS, EPS, EPS, EPS, 0.5]
    with pytest.raises(ExperimentIIIError):
        sigma_tilde(values, eps=1e-3)


def test_d32_the_guard_never_leaks_into_the_raw_statistics(negative_rows):
    clipped = [
        {**row, "sigma_hat": max(float(row["sigma_hat"]), EPS)} for row in negative_rows
    ]
    # The guard WOULD change these answers, which is what makes the test
    # discriminating rather than vacuous.
    raw_scale = scale_agreement(negative_rows, seed=SEED)
    clipped_scale = scale_agreement(clipped, seed=SEED)
    assert raw_scale["intercept"] != clipped_scale["intercept"]
    assert raw_scale["intercept"] == pytest.approx(-0.002, abs=1e-9)

    raw_s1 = u2_s1(negative_rows, seed=SEED)["observed"]
    clipped_s1 = u2_s1(clipped, seed=SEED)["observed"]
    assert raw_s1 != clipped_s1
    unshifted = u2_s1(synthetic_predictions(), seed=SEED)["observed"]
    # A constant shift cancels in the matched-tau contrast on RAW sigma_hat.
    assert raw_s1 == pytest.approx(unshifted, abs=1e-12)


def test_d32_every_raw_statistic_refuses_the_guard():
    for name in (
        "U2-S1",
        "U2-S2",
        "U2-S3",
        "U3-S1",
        "U3-S2",
        "U3-S3",
        "A_SCALE_AGREEMENT",
        "B_MONOTONICITY",
        "CONFOUND_CONTROLS",
        "CONTEXT_BOUNDARY_SECONDARY",
    ):
        assert name in RAW_SIGMA_STATISTICS
        with pytest.raises(ExperimentIIIError) as error:
            assert_guard_scope(name)
        assert error.value.blocker == "B_CALIBRATION_POSITIVITY_RULE_ALTERED"


def test_d32_probabilistic_uses_accept_the_guard():
    for name in ("C_COVERAGE", "D_NLL_HYBRID", "LOG_SIGMA_AXIS", "GAUSSIAN_DENSITY_SCORE"):
        assert name in GUARDED_STATISTICS
        assert_guard_scope(name) is None
    with pytest.raises(ExperimentIIIError):
        assert_guard_scope("SOMETHING_ELSE")


def test_d32_reporting_is_mandatory_overall_and_split_by_q_and_tau(negative_rows):
    report = positivity_report(negative_rows)
    assert report["count_negative"] > 0
    assert report["min_sigma_hat"] < 0.0
    assert 0.0 < report["fraction_clipped"] <= 1.0
    assert set(report["fraction_clipped_by_q"]) == {f"{q:.4f}" for q in Q_LEVELS}
    assert len(report["fraction_clipped_by_tau"]) == 19
    for analysis in (
        coverage(negative_rows, mean_gate_passes=True),
        nll(negative_rows, mean_gate_passes=True),
    ):
        assert "fraction_clipped" in analysis["positivity"]


def test_d32_material_clipping_is_a_disclosure_never_a_failure():
    rows = synthetic_predictions(sigma_shift=-1.0)
    report = positivity_report(rows)
    assert report["fraction_clipped"] > MATERIAL_CLIPPING_THRESHOLD
    assert report["POSITIVITY_GUARD_MATERIAL"] is True
    assert report["is_a_disclosure_not_a_failure"] is True
    assert report["is_a_reason_to_refit"] is False


def test_d32_locked_predictions_store_raw_sigma_hat(negative_rows):
    assert_predictions_store_raw_sigma_hat(negative_rows)
    with pytest.raises(ExperimentIIIError) as error:
        assert_predictions_store_raw_sigma_hat(
            [{**negative_rows[0], "sigma_hat_clipped": True}]
        )
    assert error.value.blocker == "B_CALIBRATION_POSITIVITY_RULE_ALTERED"


def test_d32_the_rule_may_not_be_changed_after_prediction_lock():
    locked = {"EPS_blocks": EPS, "applies_to": sorted(GUARDED_STATISTICS)}
    assert_positivity_rule_unchanged(locked, dict(locked))
    with pytest.raises(ExperimentIIIError):
        assert_positivity_rule_unchanged(locked, {**locked, "EPS_blocks": 1e-3})
    with pytest.raises(ExperimentIIIError):
        assert_positivity_rule_unchanged(locked, {**locked, "applies_to": ["U2-S1"]})


# --------------------------------------------------------------------------
# D.33 — Holm procedure executability
# --------------------------------------------------------------------------

def test_d33_significance_is_declared_only_from_the_adjusted_p_value(planted):
    result = u2_analysis(planted, seed=SEED, controls_passed=True)
    assert result["holm_role"] == "FAMILYWISE_HYPOTHESIS_DECISION"
    assert result["ci_role"] == "EFFECT_SIZE_REPORTING"
    for name in U2_FAMILY_ORDER:
        assert result["significant"][name] == (
            result["holm_adjusted_p_values"][name] <= ALPHA
        )


def test_d33_the_phrase_holm_adjusted_ci_is_refused():
    assert_no_holm_adjusted_interval_language("an ordinary unadjusted 95% CI")
    for phrase in (
        "Holm-adjusted CI",
        "holm adjusted confidence interval",
        "the Holm-adjusted interval excludes zero",
    ):
        with pytest.raises(ExperimentIIIError) as error:
            assert_no_holm_adjusted_interval_language(phrase)
        assert error.value.blocker == "B_INFERENCE_PROCEDURE_MISMATCH"


def test_d33_u2_s1_uses_the_permutation_p_value(planted):
    result = u2_s1(planted, seed=SEED)
    assert result["p_value_construction"] == "WITHIN_IDENTITY_Q_ASSIGNMENT_PERMUTATION"
    assert result["permutations"] == 9999


def test_d33_inversion_p_values_use_the_frozen_formula_and_never_reach_zero():
    identities = [f"e3_t{index:02d}" for index in range(1, 26)]
    strong = bootstrap_inversion(
        identities, lambda sample: 5.0, seed=1, t_null=0.0, label="strong"
    )
    assert strong["p_value"] == pytest.approx(1.0 / (BOOTSTRAP_B + 1))
    assert strong["p_value"] > 0.0
    null = bootstrap_inversion(
        identities, lambda sample: -5.0, seed=1, t_null=0.0, label="null"
    )
    assert null["p_value"] == 1.0


def test_d33_u2_s3_inverts_against_one_sixth(planted):
    result = u2_s3(planted, seed=SEED)
    assert result["p_null"] == pytest.approx(U2_S3_CHANCE)
    assert result["p_value"] >= 1.0 / (BOOTSTRAP_B + 1)


def test_d33_inversion_is_uniform_under_no_effect_and_at_the_floor_under_a_strong_one():
    identities = [f"e3_t{index:02d}" for index in range(1, 26)]
    rng = np.random.default_rng(7)
    p_values = []
    for draw in range(16):
        values = rng.normal(0.0, 1.0, size=len(identities))
        position = {name: index for index, name in enumerate(identities)}
        p_values.append(
            bootstrap_inversion(
                identities,
                lambda sample, values=values, position=position: float(
                    values[[position[name] for name in sample]].mean()
                ),
                seed=500 + draw,
                t_null=0.0,
                label="null",
            )["p_value"]
        )
    sample = np.asarray(p_values)
    assert 0.15 <= float(sample.mean()) <= 0.85
    assert float(sample.min()) < 0.3
    assert float(sample.max()) > 0.3


def test_d33_holm_matches_a_hand_computed_table():
    # p = (0.010, 0.020, 0.030), m = 3, ties broken by the frozen member order.
    #   padj_(1) = min(1, 3*0.010) = 0.030
    #   padj_(2) = min(1, max(0.030, 2*0.020)) = 0.040
    #   padj_(3) = min(1, max(0.040, 1*0.030)) = 0.040
    adjusted = holm(
        {"U2-S1": 0.010, "U2-S2": 0.020, "U2-S3": 0.030}, family_order=U2_FAMILY_ORDER
    )
    assert adjusted["U2-S1"] == pytest.approx(0.030)
    assert adjusted["U2-S2"] == pytest.approx(0.040)
    assert adjusted["U2-S3"] == pytest.approx(0.040)
    # Monotonicity is enforced: a smaller later term never lowers an earlier one.
    monotone = holm(
        {"U2-S1": 0.040, "U2-S2": 0.041, "U2-S3": 0.042}, family_order=U2_FAMILY_ORDER
    )
    assert monotone["U2-S1"] <= monotone["U2-S2"] <= monotone["U2-S3"]
    # Ties resolve by frozen member order, deterministically.
    tied = holm(
        {"U2-S1": 0.02, "U2-S2": 0.02, "U2-S3": 0.02}, family_order=U2_FAMILY_ORDER
    )
    assert tied["U2-S1"] == tied["U2-S2"] == tied["U2-S3"] == pytest.approx(0.06)


def test_d33_intervals_are_ordinary_unadjusted_percentile_intervals(planted):
    result = u2_analysis(planted, seed=SEED, controls_passed=True)
    assert result["intervals_are_unadjusted"] is True
    for member in result["members"].values():
        assert member["ci_is_unadjusted"] is True
        assert member["ci_low"] <= member["ci_high"]


def test_d33_the_positive_declaration_conjunction_needs_p_and_a_directional_ci(planted):
    declared = u2_analysis(planted, seed=SEED, controls_passed=True)
    assert declared["U2_POSITIVE"] is True
    assert all(declared["conjunction_clauses"].values())
    # The same evidence with the section-23 controls failing may not declare.
    blocked = u2_analysis(planted, seed=SEED, controls_passed=False)
    assert blocked["U2_POSITIVE"] is False
    assert blocked["wording"] == WORDING_BEFORE_CONTROLS_PASS


def test_d33_at_drop_level_1_the_family_reduces_to_two(planted):
    result = u2_analysis(planted, seed=SEED, controls_passed=True, drop_level="LEVEL_1")
    assert result["family"] == list(U2_FAMILY_AT_DROP_LEVEL_1)
    assert result["family_size"] == 2
    assert "U2-S3" not in result["members"]


def test_d33_assert_family_refuses_a_reordered_or_resized_family():
    assert_family(U2_FAMILY_ORDER, U2_FAMILY_ORDER)
    with pytest.raises(ExperimentIIIError) as error:
        assert_family(("U2-S2", "U2-S1", "U2-S3"), U2_FAMILY_ORDER)
    assert error.value.blocker == "B_U2_FAMILY_ALTERED"


# --------------------------------------------------------------------------
# Monotonicity and the context boundary (authority 27.B / 25)
# --------------------------------------------------------------------------

def test_monotonicity_is_computed_on_raw_sigma_hat_and_beats_chance(planted):
    result = monotonicity(planted)
    assert result["uses_raw_sigma_hat"] is True
    assert result["chance"] == 0.5
    assert result["agreement_fraction"] == 1.0


def test_context_boundary_secondary_is_not_a_pass_gate(planted):
    result = context_boundary_secondary(planted, seed=SEED)
    assert result["tau_support"] == [16, 17, 18, 19]
    assert result["is_a_technical_pass_gate"] is False
    assert result["modify_experiment_if_prediction_fails"] is False
