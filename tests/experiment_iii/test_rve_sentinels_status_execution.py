"""I07 / I08 / I16 / I17 / I18 — RVE, sentinels, statistics, status, resume.

Covers A.14, A.15, A.26, A.29, A.30, the Holm family sizes, the no-success-gate
guard, the status contract and the same-spec resume rules.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from mineocclude.experiment_iii.blockers import (
    blocker,
    blocker_codes,
    is_terminal,
    validate_blocker_code,
)
from mineocclude.experiment_iii.errors import ExperimentIIIError
from mineocclude.experiment_iii.execution import (
    EXTRACTION_STATES,
    ExtractionPlan,
    ExtractionUnit,
    HashChainLedger,
    plan_extraction_units,
    resume_decision,
)
from mineocclude.experiment_iii.prediction_lock import PredictionCell, PredictionLock
from mineocclude.experiment_iii.rve import (
    ADJACENT_SEPARATION_MIN,
    LADDER_ZONES,
    PLACEMENT_COUNT,
    TARGET_RVE_POINTS,
    aggregate_condition,
    background_residual,
    excess_energy,
    masked_energy,
    placement_mask,
    robust_median_image,
    rve,
    select_ladder,
    split_half_noise,
    srgb_to_linear,
)
from mineocclude.experiment_iii.sentinels import (
    SENTINEL_PLACEMENT_COUNT,
    SentinelReading,
    check_order,
    derive_envelope,
    evaluate_batch_boundary,
)
from mineocclude.experiment_iii.statistics import (
    BOOTSTRAP_REPLICATES,
    CONTEXT_AGE_BINS,
    PRIMARY_FAMILY,
    REMOVED_GATES,
    assert_identity_level_unit,
    assert_no_success_gate,
    boundary_interaction,
    context_age_bin,
    evidence_coordinate,
    holm_adjust,
    identity_bootstrap_interval,
    identity_metrics,
    l0_interpretability_control,
    one_sided_t_test,
    primary_analysis,
    primary_estimands,
    slope_on_evidence,
)
from mineocclude.experiment_iii.status import (
    REQUIRED_FIELDS,
    STAGES_REQUIRING_STATUS,
    StatusDocument,
    assert_observational_only,
    validate_status_document,
)


# --------------------------------------------------------------------------
# A.14 — RVE arithmetic
# --------------------------------------------------------------------------

def test_srgb_to_linear_matches_the_piecewise_formula():
    assert srgb_to_linear(np.array([[[0]]], dtype=np.uint8))[0, 0, 0] == 0.0
    at_255 = srgb_to_linear(np.array([[[255]]], dtype=np.uint8))[0, 0, 0]
    assert at_255 == pytest.approx(1.0)
    at_128 = srgb_to_linear(np.array([[[128]]], dtype=np.uint8))[0, 0, 0]
    s = 128 / 255
    assert at_128 == pytest.approx(((s + 0.055) / 1.055) ** 2.4)
    # The 0.04045 breakpoint: 10/255 = 0.0392 uses the linear leg.
    low = srgb_to_linear(np.array([[[10]]], dtype=np.uint8))[0, 0, 0]
    assert low == pytest.approx((10 / 255) / 12.92)


def test_coordinate_wise_median_over_settled_frames():
    frames = [np.full((2, 2, 3), value, dtype=np.float64) for value in (1.0, 5.0, 3.0)]
    assert np.allclose(robust_median_image(frames), 3.0)


def test_masked_energy_matches_an_independent_computation():
    present = np.zeros((4, 4, 3))
    absent = np.zeros((4, 4, 3))
    present[1, 1] = [1.0, 2.0, 2.0]  # squared norm 9
    present[3, 3] = [1.0, 0.0, 0.0]  # outside the mask
    mask = np.zeros((4, 4), dtype=bool)
    mask[1, 1] = True
    assert masked_energy(present, absent, mask) == pytest.approx(9.0)
    assert background_residual(present, absent, mask) == pytest.approx(1.0)


def test_split_half_noise_is_deterministic_under_a_fixed_frame_order():
    frames = [np.full((2, 2, 3), float(i)) for i in range(6)]
    mask = np.ones((2, 2), dtype=bool)
    first = split_half_noise(frames, mask)
    second = split_half_noise(frames, mask)
    assert first == second
    # first half median 1.0, second half median 4.0 -> 3^2 * 3 channels * 4 px
    assert first == pytest.approx(9.0 * 3 * 4)


def test_excess_energy_clamps_at_zero_and_rve_of_l0_is_one():
    assert excess_energy(10.0, 3.0) == 7.0
    assert excess_energy(2.0, 5.0) == 0.0
    assert rve(7.0, 7.0) == 1.0


def test_zero_l0_energy_is_refused():
    with pytest.raises(ExperimentIIIError):
        rve(1.0, 0.0)


# --------------------------------------------------------------------------
# A.15 — mask, shared across candidates, dilated by exactly two
# --------------------------------------------------------------------------

def _l0_block(size=20):
    present = np.zeros((size, size, 3))
    absent = np.zeros((size, size, 3))
    present[9:11, 9:11] = 1.0
    return present, absent


def test_mask_is_dilated_by_exactly_two_pixels():
    mask = placement_mask([_l0_block()], noise_threshold=0.5, dilation=2)
    # The 2x2 core dilates by 2 in a plus-shaped structuring element.
    assert mask[9, 9] and mask[10, 10]
    assert mask[7, 9] and mask[12, 10]
    assert not mask[6, 9]
    undilated = placement_mask([_l0_block()], noise_threshold=0.5, dilation=0)
    assert undilated.sum() == 4
    assert mask.sum() > undilated.sum()


def test_mask_unions_over_replicate_blocks():
    first = _l0_block()
    second_present = np.zeros((20, 20, 3))
    second_absent = np.zeros((20, 20, 3))
    second_present[2:4, 2:4] = 1.0
    mask = placement_mask([first, (second_present, second_absent)], 0.5, dilation=0)
    assert mask[9, 9] and mask[2, 2]


def test_empty_mask_is_refused():
    with pytest.raises(ExperimentIIIError) as caught:
        placement_mask([_l0_block()], noise_threshold=1e9)
    assert caught.value.blocker == "RVE_MASK_DEGENERATE"


def test_implausibly_large_mask_is_refused():
    present = np.ones((10, 10, 3))
    absent = np.zeros((10, 10, 3))
    with pytest.raises(ExperimentIIIError) as caught:
        placement_mask([(present, absent)], noise_threshold=0.5)
    assert caught.value.blocker == "RVE_MASK_DEGENERATE"


# --------------------------------------------------------------------------
# A.15 — deterministic triple selection and the tie-break
# --------------------------------------------------------------------------

def _ladder_inputs(values):
    placement_scores = {
        name: [value] * PLACEMENT_COUNT for name, value in values.items()
    }
    snr = {name: [10.0] * PLACEMENT_COUNT for name in values}
    replicate_blocks = {name: [[value, value]] for name, value in values.items()}
    background_ok = {name: True for name in values}
    return placement_scores, snr, replicate_blocks, background_ok


def test_selection_minimizes_distance_to_the_frozen_target_points():
    values = {
        "minecraft:white_stained_glass": 0.725,
        "minecraft:lime_stained_glass": 0.425,
        "minecraft:blue_stained_glass": 0.165,
        "minecraft:black_stained_glass": 0.10,
    }
    scores, snr, blocks, background = _ladder_inputs(values)
    result = select_ladder(
        list(values), scores, snr=snr, replicate_blocks=blocks,
        background_ok=background, bootstrap_seed=17,
    )
    assert result["P0_RESULT"] == "P0_PASS"
    assert result["selected"]["L1"] == "minecraft:white_stained_glass"
    assert result["selected"]["L2"] == "minecraft:lime_stained_glass"
    assert result["selected"]["L3"] == "minecraft:blue_stained_glass"
    assert TARGET_RVE_POINTS == (0.725, 0.425, 0.165)


def test_exact_distance_tie_breaks_lexicographically_by_registry_id():
    # Two candidates with identical scores; the earlier registry ID must win L3.
    values = {
        "minecraft:white_stained_glass": 0.725,
        "minecraft:lime_stained_glass": 0.425,
        "minecraft:blue_stained_glass": 0.165,
        "minecraft:cyan_stained_glass": 0.165,
    }
    scores, snr, blocks, background = _ladder_inputs(values)
    result = select_ladder(
        list(values), scores, snr=snr, replicate_blocks=blocks,
        background_ok=background, bootstrap_seed=17,
    )
    assert result["selected"]["L3"] == "minecraft:blue_stained_glass"
    assert "minecraft:blue_stained_glass" < "minecraft:cyan_stained_glass"


def test_no_valid_ladder_is_returned_not_an_approximation():
    values = {
        "minecraft:white_stained_glass": 0.9,
        "minecraft:lime_stained_glass": 0.88,
        "minecraft:blue_stained_glass": 0.86,
    }
    scores, snr, blocks, background = _ladder_inputs(values)
    result = select_ladder(
        list(values), scores, snr=snr, replicate_blocks=blocks,
        background_ok=background, bootstrap_seed=17,
    )
    assert result["P0_RESULT"] == "NO_VALID_LADDER"
    assert result["P0_LADDER_ACCEPTED"] is False
    assert result["selected"] is None


def test_ladder_zones_and_separation_are_the_frozen_values():
    assert LADDER_ZONES == {"L1": (0.60, 0.85), "L2": (0.30, 0.55), "L3": (0.08, 0.25)}
    assert ADJACENT_SEPARATION_MIN == 0.12
    assert PLACEMENT_COUNT == 9


def test_candidate_outside_the_roster_is_refused():
    with pytest.raises(ExperimentIIIError) as caught:
        select_ladder(
            ["minecraft:obsidian"], {}, snr={}, replicate_blocks={},
            background_ok={}, bootstrap_seed=1,
        )
    assert caught.value.blocker == "P0_CANDIDATE_ID_UNSUPPORTED"


# --------------------------------------------------------------------------
# I08 — sentinels
# --------------------------------------------------------------------------

@pytest.fixture
def envelope():
    return derive_envelope(
        [0, 4, 8],
        {0: [0.90, 0.92, 0.91], 4: [0.50, 0.52, 0.51], 8: [0.16, 0.17, 0.165]},
    )


def test_exactly_three_sentinel_placements(envelope):
    assert SENTINEL_PLACEMENT_COUNT == 3
    assert len(envelope.placements) == 3
    with pytest.raises(ExperimentIIIError):
        derive_envelope([0, 4], {0: [0.9, 0.9], 4: [0.5, 0.5]})


def test_clean_boundary_passes(envelope):
    reading = SentinelReading(3, "before", {0: 0.91, 4: 0.51, 8: 0.166})
    receipt = evaluate_batch_boundary(
        reading, envelope, batch_capture_unit_ids=["e3_t01__L2"]
    )
    assert receipt["passed"] is True
    assert receipt["blocker"] is None
    assert receipt["invalidation"]["invalidated_capture_unit_ids"] == []


def test_order_violation_is_detected(envelope):
    reading = SentinelReading(3, "after", {0: 0.16, 4: 0.51, 8: 0.91})
    receipt = evaluate_batch_boundary(
        reading, envelope, batch_capture_unit_ids=["e3_t01__L2"]
    )
    assert receipt["blocker"] == "SENTINEL_ORDER_VIOLATION"
    assert check_order(reading.scores, envelope) is False


def test_envelope_violation_is_detected(envelope):
    reading = SentinelReading(3, "after", {0: 0.91, 4: 0.51, 8: 0.60})
    receipt = evaluate_batch_boundary(
        reading, envelope, batch_capture_unit_ids=["e3_t01__L2", "e3_t02__L2"]
    )
    assert receipt["blocker"] in {
        "SENTINEL_ENVELOPE_VIOLATION",
        "SENTINEL_ORDER_VIOLATION",
    }
    assert receipt["passed"] is False


def test_failure_invalidates_only_the_affected_unmodeled_batch(envelope):
    reading = SentinelReading(2, "after", {0: 0.16, 4: 0.51, 8: 0.91})
    receipt = evaluate_batch_boundary(
        reading, envelope, batch_capture_unit_ids=["e3_t01__L2", "e3_t02__L2"]
    )
    invalidation = receipt["invalidation"]
    assert invalidation["scope"] == "AFFECTED_UNMODELED_BATCH_ONLY"
    assert invalidation["invalidated_capture_unit_ids"] == [
        "e3_t01__L2",
        "e3_t02__L2",
    ]
    assert invalidation["exact_technical_retry_permitted"] is True
    assert receipt["failure_is_technical_not_scientific"] is True
    assert receipt["may_change_materials"] is False
    assert receipt["may_change_target_rows"] is False
    assert receipt["may_change_any_statistic"] is False
    assert receipt["is_a_condition_selection_mechanism"] is False


def test_already_modeled_batch_escalates_rather_than_rewrites(envelope):
    reading = SentinelReading(2, "after", {0: 0.16, 4: 0.51, 8: 0.91})
    receipt = evaluate_batch_boundary(
        reading,
        envelope,
        batch_capture_unit_ids=["e3_t01__L2"],
        batch_already_modeled=True,
    )
    assert receipt["invalidation"]["scope"] == "ESCALATE_BATCH_ALREADY_MODELED"
    assert receipt["invalidation"]["invalidated_capture_unit_ids"] == []


# --------------------------------------------------------------------------
# I16 — statistics
# --------------------------------------------------------------------------

def _lock():
    lock = PredictionLock()
    lock.add(PredictionCell("e3_t01", "L0", 0, "MW_CURRENT", 0.1, 0.2))
    lock.seal()
    return lock


def test_identity_metrics_and_zero_tss_refusal():
    metrics = identity_metrics("e3_t01", "L0", [1.0, 2.0, 3.0], [1.0, 2.0, 4.0])
    assert metrics.rmse == pytest.approx(np.sqrt(1 / 3))
    assert metrics.mae == pytest.approx(1 / 3)
    with pytest.raises(ExperimentIIIError) as caught:
        identity_metrics("e3_t01", "L0", [2.0, 2.0], [1.0, 3.0])
    assert caught.value.blocker == "STATS_ZERO_TSS"


def test_evidence_coordinate_and_slope():
    v_c = {"L0": 1.0, "L1": 0.725, "L2": 0.425, "L3": 0.165, "L4": 0.05}
    o_c = evidence_coordinate(v_c)
    assert o_c["L0"] == 0.0
    assert o_c["L4"] == pytest.approx(0.95)
    rmse = {name: 1.0 + 2.0 * o_c[name] for name in o_c}
    assert slope_on_evidence(rmse, o_c) == pytest.approx(2.0)


def test_three_primary_estimands_only():
    v_c = {"L0": 1.0, "L1": 0.725, "L2": 0.425, "L3": 0.165, "L4": 0.05}
    o_c = evidence_coordinate(v_c)
    rmse = {"L0": 1.0, "L1": 1.2, "L2": 1.4, "L3": 1.6, "L4": 2.0}
    estimands = primary_estimands(rmse, o_c)
    assert set(estimands) == set(PRIMARY_FAMILY)
    assert len(PRIMARY_FAMILY) == 3
    assert estimands["Dpartial_i"] == pytest.approx(np.mean([1.2, 1.4, 1.6]) - 1.0)
    assert estimands["Dopaque_i"] == pytest.approx(2.0 - 1.6)


def test_holm_family_sizes_three_and_two():
    three = holm_adjust({"a": 0.01, "b": 0.02, "c": 0.03})
    assert len(three) == 3
    assert three["a"] == pytest.approx(0.03)
    two = holm_adjust({"x": 0.01, "y": 0.04})
    assert len(two) == 2
    assert two["x"] == pytest.approx(0.02)
    assert two["y"] == pytest.approx(0.04)


def test_holm_is_monotone():
    adjusted = holm_adjust({"a": 0.001, "b": 0.4, "c": 0.02})
    ordered = sorted(adjusted.items(), key=lambda kv: kv[1])
    assert [name for name, _ in ordered] == ["a", "c", "b"]
    assert all(0.0 <= value <= 1.0 for value in adjusted.values())


def test_bootstrap_is_whole_identity_at_ten_thousand():
    assert BOOTSTRAP_REPLICATES == 10_000
    values = {f"e3_t{i:02d}": float(i) for i in range(1, 11)}
    first = identity_bootstrap_interval(values, seed=99)
    second = identity_bootstrap_interval(values, seed=99)
    assert first == second
    assert first["resampling_unit"] == "WHOLE_IDENTITY"
    assert first["replicates"] == 10_000
    assert first["seed"] == 99
    # The seed genuinely drives the draws. A heavy-tailed sample is used because
    # evenly spaced values put the 2.5th percentile on the same discrete step for
    # many seeds, which would make this check pass for the wrong reason.
    skewed = {f"e3_t{i:02d}": float(i) ** 4 for i in range(1, 11)}
    a = identity_bootstrap_interval(skewed, seed=99)
    b = identity_bootstrap_interval(skewed, seed=100)
    assert (a["ci_low"], a["ci_high"]) != (b["ci_low"], b["ci_high"])
    assert a == identity_bootstrap_interval(skewed, seed=99)


def test_row_resampling_is_refused():
    values = {f"e3_t{i:02d}": float(i) for i in range(1, 11)}
    with pytest.raises(ExperimentIIIError) as caught:
        identity_bootstrap_interval(values, seed=1, replicates=199)
    assert caught.value.blocker == "STATS_BOOTSTRAP_UNIT_VIOLATION"
    with pytest.raises(ExperimentIIIError) as caught:
        assert_identity_level_unit("ROW")
    assert caught.value.blocker == "STATS_BOOTSTRAP_UNIT_VIOLATION"


def test_one_sided_test_is_positive_directional():
    _, _, p_low = one_sided_t_test([1.0, 1.1, 0.9, 1.2, 1.05])
    _, _, p_high = one_sided_t_test([-1.0, -1.1, -0.9, -1.2, -1.05])
    assert p_low < 0.01
    assert p_high > 0.99


def test_statistics_refuse_to_run_before_the_prediction_lock():
    lock = PredictionLock()
    lock.add(PredictionCell("e3_t01", "L0", 0, "MW_CURRENT", 0.1, 0.2))
    with pytest.raises(ExperimentIIIError) as caught:
        primary_analysis({}, lock=lock, bootstrap_seed=1)
    assert caught.value.blocker == "PREDICTION_LOCK_MISSING"


def test_primary_analysis_emits_no_overall_verdict():
    per_identity = {
        f"e3_t{i:02d}": {"S_i": 0.5 + i * 0.01, "Dpartial_i": 0.3, "Dopaque_i": 0.2}
        for i in range(1, 11)
    }
    payload = primary_analysis(per_identity, lock=_lock(), bootstrap_seed=7)
    assert payload["family_size"] == 3
    assert payload["multiplicity"] == "HOLM_ACROSS_3"
    assert payload["decisions_come_from"] == "HOLM_ADJUSTED_P_VALUES"
    assert payload["inferential_unit"] == "IDENTITY"
    assert "experiment_passed" not in payload
    assert "overall_verdict" not in payload
    for name in PRIMARY_FAMILY:
        assert "holm_adjusted_p_value" in payload["estimands"][name]
        assert "interval" in payload["estimands"][name]


def test_altered_primary_family_is_refused():
    per_identity = {
        "e3_t01": {"S_i": 0.5, "Dpartial_i": 0.3, "Dopaque_i": 0.2, "Pixel_i": 0.1},
        "e3_t02": {"S_i": 0.5, "Dpartial_i": 0.3, "Dopaque_i": 0.2, "Pixel_i": 0.1},
    }
    with pytest.raises(ExperimentIIIError) as caught:
        primary_analysis(per_identity, lock=_lock(), bootstrap_seed=7)
    assert caught.value.blocker == "ANALYSIS_FAMILY_ALTERED"


@pytest.mark.parametrize(
    "payload",
    [
        {"experiment_passed": True},
        {"overall_verdict": "PASS"},
        {"discontinuity_ratio": 3.1},
        {"B_49_SELECTION_AWARE_DERANGEMENT_NULL": {}},
    ],
)
def test_success_gates_are_refused(payload):
    with pytest.raises(ExperimentIIIError) as caught:
        assert_no_success_gate(payload)
    assert caught.value.blocker == "ANALYSIS_SUCCESS_GATE_REINTRODUCED"


def test_removed_gates_are_enumerated():
    assert "B_49_SELECTION_AWARE_DERANGEMENT_NULL" in REMOVED_GATES
    assert "OVERALL_EXPERIMENT_PASS_FAIL_QUALIFICATION" in REMOVED_GATES
    assert "MLP_STRETCH_RESCUE" in REMOVED_GATES


def test_l0_control_reports_without_gating():
    model = {f"e3_t{i:02d}": 0.5 for i in range(1, 11)}
    baseline = {f"e3_t{i:02d}": 0.9 for i in range(1, 11)}
    result = l0_interpretability_control(
        model, baseline, lock=_lock(), bootstrap_seed=5
    )
    assert result["excludes_zero_in_the_favorable_direction"] is True
    assert result["experiment_can_still_close"] is True
    assert result["on_failure_retune_allowed"] is False


def test_context_bins_and_boundary_interaction_windows():
    assert CONTEXT_AGE_BINS == ((1, 5), (6, 10), (11, 15), (16, 19))
    assert context_age_bin(1) == "1-5"
    assert context_age_bin(19) == "16-19"
    with pytest.raises(ExperimentIIIError) as caught:
        context_age_bin(20)
    assert caught.value.blocker == "ANALYSIS_CONTEXT_BIN_MISMATCH"
    value = boundary_interaction(
        {(12, 15): 1.0, (16, 19): 2.0}, {(12, 15): 1.0, (16, 19): 1.5}
    )
    assert value == pytest.approx(0.5)


def test_boundary_interaction_refuses_the_reporting_bins():
    with pytest.raises(ExperimentIIIError) as caught:
        boundary_interaction({(11, 15): 1.0}, {(11, 15): 1.0})
    assert caught.value.blocker == "ANALYSIS_CONTEXT_BIN_MISMATCH"


# --------------------------------------------------------------------------
# I17 — status and blockers
# --------------------------------------------------------------------------

def test_blocker_taxonomy_is_loaded_and_codes_validate():
    codes = blocker_codes()
    assert len(codes) == 146
    assert "WALL_CACHE_KEY_STALE" in codes
    assert validate_blocker_code(None) is None
    assert validate_blocker_code("CAPTURE_STALE_FRAME") == "CAPTURE_STALE_FRAME"
    assert blocker("CAPTURE_STALE_FRAME")["severity"]
    assert isinstance(is_terminal("AUTHORITY_INCOMPLETE"), bool)


def test_invented_blocker_code_is_refused():
    with pytest.raises(ExperimentIIIError) as caught:
        validate_blocker_code("SOMETHING_WENT_WRONG")
    assert caught.value.blocker == "STATUS_BLOCKER_CODE_UNKNOWN"


def test_status_document_carries_every_required_field():
    document = StatusDocument(
        stage="A7", total_units=125, completed_units=61, stage_status="RUNNING"
    ).to_dict()
    for name in REQUIRED_FIELDS:
        assert name in document, name
    assert document["REMAINING_UNITS"] == 64
    validate_status_document(document)


def test_status_refuses_a_scientific_outcome():
    with pytest.raises(ExperimentIIIError) as caught:
        assert_observational_only({"rmse": 0.5})
    assert caught.value.blocker == "STATUS_DOCUMENT_MALFORMED"
    with pytest.raises(ExperimentIIIError):
        StatusDocument(stage="A7", extra={"prediction": 1.0}).to_dict()


def test_status_refuses_an_unknown_blocker():
    with pytest.raises(ExperimentIIIError) as caught:
        StatusDocument(stage="A7", current_blocker="NOPE").to_dict()
    assert caught.value.blocker == "STATUS_BLOCKER_CODE_UNKNOWN"


def test_blocked_status_requires_a_blocker():
    document = StatusDocument(stage="A7", stage_status="RUNNING").to_dict()
    document["STAGE_STATUS"] = "BLOCKED"
    with pytest.raises(ExperimentIIIError) as caught:
        validate_status_document(document)
    assert caught.value.blocker == "STATUS_DOCUMENT_MALFORMED"


def test_clean_skip_is_an_honourable_outcome_not_an_error():
    document = StatusDocument(
        stage="A7", iii_a_status="RUNNING", iii_b_status="CLEAN_SKIP"
    ).to_dict()
    validate_status_document(document)
    assert document["III_B_STATUS"] == "CLEAN_SKIP"
    assert document["III_A_STATUS"] == "RUNNING"


def test_iii_a_status_is_independent_of_iii_b():
    for iii_b in ("CLEAN_SKIP", "BLOCKED", "RUNNING", "NOT_STARTED"):
        document = StatusDocument(
            stage="A7", iii_a_status="RUNNING", iii_b_status=iii_b
        ).to_dict()
        assert document["III_A_STATUS"] == "RUNNING"


def test_unknown_stage_is_refused():
    with pytest.raises(ExperimentIIIError):
        StatusDocument(stage="A99")
    assert "A7" in STAGES_REQUIRING_STATUS


def test_status_writes_atomically(tmp_path, monkeypatch):
    import mineocclude.experiment_iii.namespace as namespace_module

    monkeypatch.setattr(namespace_module, "REPOSITORY_ROOT", tmp_path)
    document = StatusDocument(stage="A7", total_units=5)
    target = document.write(root=tmp_path)
    assert target.is_file()
    assert not target.with_name(target.name + ".tmp").exists()
    assert json.loads(target.read_text())["STAGE"] == "A7"


# --------------------------------------------------------------------------
# I18 — resume and recovery
# --------------------------------------------------------------------------

SOURCE = "a" * 64
SPEC = "b" * 64


def _units(capture="e3_t01__L2", source=SOURCE, spec=SPEC):
    return plan_extraction_units(
        capture, source_capture_hash=source, extraction_spec_hash=spec
    )


def test_six_extraction_units_per_capture():
    units = _units()
    assert len(units) == 6
    assert {unit.layer for unit in units} == {4, 10, 19}
    assert {unit.temporal_slice for unit in units} == {"PREVIOUS", "CURRENT"}
    assert EXTRACTION_STATES == (
        "PLANNED", "RUNNING", "EXTRACTED", "VALIDATED", "DURABLE", "COMPLETE"
    )


def test_ledger_is_hash_chained_and_tamper_evident():
    ledger = HashChainLedger()
    ledger.append("u1", "PLANNED")
    ledger.append("u1", "RUNNING")
    ledger.verify_chain()
    ledger.records[0]["state"] = "COMPLETE"
    with pytest.raises(ExperimentIIIError) as caught:
        ledger.verify_chain()
    assert caught.value.blocker == "PROVENANCE_AUTHORITY_DRIFT"


def test_complete_units_are_skipped_without_reading_bytes():
    ledger = HashChainLedger()
    unit = _units()[0]
    ledger.append(
        unit.unit_id, "COMPLETE",
        source_capture_hash=SOURCE, extraction_spec_hash=SPEC,
    )
    decision = resume_decision(unit, ledger)
    assert decision["action"] == "SKIP"
    assert decision["reads_bytes"] is False


def test_durable_units_are_resealed_and_extracted_units_revalidated():
    ledger = HashChainLedger()
    durable, extracted = _units()[0], _units()[1]
    ledger.append(
        durable.unit_id, "DURABLE",
        source_capture_hash=SOURCE, extraction_spec_hash=SPEC,
    )
    ledger.append(
        extracted.unit_id, "EXTRACTED",
        source_capture_hash=SOURCE, extraction_spec_hash=SPEC,
    )
    assert resume_decision(durable, ledger)["action"] == "RESEAL"
    assert resume_decision(extracted, ledger)["action"] == "REVALIDATE"


def test_source_capture_drift_discards_and_replans():
    ledger = HashChainLedger()
    unit = _units()[0]
    ledger.append(
        unit.unit_id, "VALIDATED",
        source_capture_hash="c" * 64, extraction_spec_hash=SPEC,
    )
    decision = resume_decision(unit, ledger)
    assert decision["action"] == "DISCARD_AND_REPLAN"
    assert decision["blocker"] == "EXTRACTION_SOURCE_CAPTURE_DRIFT"
    assert decision["forces_recapture"] is False


def test_extraction_spec_drift_discards_and_replans():
    ledger = HashChainLedger()
    unit = _units()[0]
    ledger.append(
        unit.unit_id, "VALIDATED",
        source_capture_hash=SOURCE, extraction_spec_hash="d" * 64,
    )
    decision = resume_decision(unit, ledger)
    assert decision["action"] == "DISCARD_AND_REPLAN"
    assert decision["blocker"] == "EXTRACTION_SPEC_DRIFT"


def test_extraction_failure_does_not_force_recapture():
    """Capture and extraction stay separable (authority 8.6)."""
    ledger = HashChainLedger()
    plan = ExtractionPlan(ledger)
    plan.add_capture(
        "e3_t01__L2", source_capture_hash=SOURCE, extraction_spec_hash=SPEC
    )
    for unit in plan.units[:5]:
        ledger.append(
            unit.unit_id, "COMPLETE",
            source_capture_hash=SOURCE, extraction_spec_hash=SPEC,
        )
    actions = plan.resume()
    assert len(actions["SKIP"]) == 5
    assert len(actions["EXTRACT"]) == 1
    # The capture needs its ONE shared forward set, not a recapture.
    assert plan.captures_requiring_forwards() == ["e3_t01__L2"]
    for decision in (resume_decision(u, ledger) for u in plan.units):
        assert decision.get("forces_recapture") is not True


def test_fully_complete_capture_requires_no_forwards():
    ledger = HashChainLedger()
    plan = ExtractionPlan(ledger)
    plan.add_capture(
        "e3_t01__L2", source_capture_hash=SOURCE, extraction_spec_hash=SPEC
    )
    for unit in plan.units:
        ledger.append(
            unit.unit_id, "COMPLETE",
            source_capture_hash=SOURCE, extraction_spec_hash=SPEC,
        )
    assert plan.captures_requiring_forwards() == []
    assert len(ledger.complete_units()) == 6


def test_ledger_round_trips_through_a_file(tmp_path, monkeypatch):
    import mineocclude.experiment_iii.namespace as namespace_module

    monkeypatch.setattr(namespace_module, "REPOSITORY_ROOT", tmp_path)
    path = tmp_path / "data" / "experiment_iii" / "ledger.jsonl"
    ledger = HashChainLedger(path, root=tmp_path)
    ledger.append("u1", "PLANNED", source_capture_hash=SOURCE, extraction_spec_hash=SPEC)
    ledger.append("u1", "COMPLETE", source_capture_hash=SOURCE, extraction_spec_hash=SPEC)
    reloaded = HashChainLedger(path, root=tmp_path)
    assert len(reloaded.records) == 2
    assert reloaded.last_state("u1") == "COMPLETE"
    reloaded.verify_chain()
