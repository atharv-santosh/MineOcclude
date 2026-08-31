"""Group D — D.21-D.30: status, vocabulary, capture binding, arrays, ladder, gates.

CPU only. No Minecraft, no model, no GPU.
"""

from __future__ import annotations

import datetime as dt

import pytest

from mineocclude.experiment_iii.authority import machine_authority
from mineocclude.experiment_iii.errors import ExperimentIIIError
from mineocclude.experiment_iii.iii_b_cells import (
    III_B_CONDITION,
    III_B_EPISODE_ID_BLOCK,
    III_B_WALL_BLOCK_ID,
    Q_HIGH,
    Q_LOW,
    Q_MID,
    build_iii_b_cell,
    capture_unit_id,
    episode_id_for_cell,
)
from mineocclude.experiment_iii.iii_b_extraction import (
    OCCLUDED_NPY_BYTES,
    OCCLUDED_SHAPE,
    VIS_NPY_BYTES,
    VIS_SHAPE,
    assert_only_l19_serialized,
    expected_bytes_for,
    iii_b_extraction_inventory,
    validate_iii_b_array,
)
from mineocclude.experiment_iii.iii_b_gate import (
    ABSOLUTE_EXPERIMENT_DEADLINE,
    DROP_LEVELS,
    LAUNCH_GATE_EVALUATIONS,
    LAUNCH_GATE_REQUIREMENTS,
    POOL_DURABLE_FREE_GATE_BYTES,
    POOL_WORKING_FREE_GATE_BYTES,
    LaunchGate,
    assert_absolute_stop,
    assert_no_scientific_outcome_input,
    select_drop_level,
)
from mineocclude.experiment_iii.iii_b_package import (
    LADDER_RUNGS,
    assert_claim_within_rung,
    assert_iii_a_independence,
    iii_b_closure_receipt,
    select_ladder_rung,
    simulate_total_iii_b_failure,
)
from mineocclude.experiment_iii.iii_b_status import (
    III_B_BLOCKER_CODES,
    III_B_LIFECYCLE_STATES,
    OUTCOME_VOCABULARY,
    assert_iii_a_status_independent,
    assert_not_a_blocker,
    iii_b_status_document,
    validate_iii_b_status_document,
)
from mineocclude.experiment_iii.blockers import blocker_codes

from tests.experiment_iii._iii_b_synthetic import identity_rows

GO_INPUTS = {
    "iii_a_capture_closed": True,
    "iii_a_on_schedule": True,
    "pool_working_free_bytes": 20 * (1 << 30),
    "pool_durable_free_bytes": 8 * (1 << 30),
    "pool_durable_is_distinct_local_filesystem": True,
    "iii_b_tests_pass": True,
    "iii_b_pilot_pass": True,
    "shared_rig_blocker": None,
    "does_not_threaten_iii_a_lock": True,
}


# --------------------------------------------------------------------------
# D.21 — Status schema
# --------------------------------------------------------------------------

def test_d21_status_document_validates_against_the_extended_contract():
    document = iii_b_status_document(
        iii_a_status="A7_RUNNING",
        iii_b_status="B_GEN",
        iii_b_state="B-GEN",
        completed_units=10,
        remaining_units=40,
        total_units=50,
    )
    validate_iii_b_status_document(document)
    assert document["OBSERVATIONAL_ONLY"] is True
    assert set(III_B_LIFECYCLE_STATES) == set(
        machine_authority()["experiment_iii_b"]["lifecycle_states"]
    )


def test_d21_iii_b_blocker_is_a_taxonomy_code_or_null():
    assert set(III_B_BLOCKER_CODES) <= blocker_codes()
    document = iii_b_status_document(
        iii_a_status="A7_RUNNING",
        iii_b_status="B_CAP",
        iii_b_state="B-CAP",
        iii_b_blocker="B_CAPTURE_ATTRITION",
    )
    assert document["III_B_BLOCKER"] == "B_CAPTURE_ATTRITION"
    with pytest.raises(ExperimentIIIError):
        iii_b_status_document(
            iii_a_status="A7_RUNNING",
            iii_b_status="B_CAP",
            iii_b_blocker="NOT_A_TAXONOMY_CODE",
        )


def test_d21_iii_a_status_is_not_a_function_of_iii_b_status():
    document = iii_b_status_document(iii_a_status="A19_CLOSED", iii_b_status="CLEAN_SKIP")
    assert_iii_a_status_independent(document)
    with pytest.raises(ExperimentIIIError) as error:
        assert_iii_a_status_independent(
            {"III_A_STATUS_DERIVED_FROM": ["III_B_STATUS"]}
        )
    assert error.value.blocker == "B_III_A_DEPENDENCY_DETECTED"


def test_d21_unit_arithmetic_must_balance():
    with pytest.raises(ExperimentIIIError):
        iii_b_status_document(
            iii_a_status="A7_RUNNING",
            iii_b_status="B_CAP",
            completed_units=10,
            remaining_units=10,
            total_units=50,
        )


# --------------------------------------------------------------------------
# D.22 — Outcome vocabulary
# --------------------------------------------------------------------------

def test_d22_three_outcomes_are_distinguished():
    assert set(OUTCOME_VOCABULARY) == {"CLEAN_SKIP", "TECHNICAL_FAIL", "SCIENTIFIC_NULL"}
    machine = machine_authority()["experiment_iii_b"]["outcome_vocabulary"]
    assert set(machine) == set(OUTCOME_VOCABULARY)
    assert "NOT a failure" in machine["CLEAN_SKIP"]
    assert "NOT a result" in machine["TECHNICAL_FAIL"]
    assert "NOT a blocker" in machine["SCIENTIFIC_NULL"]


def test_d22_a_scientific_null_is_never_emitted_as_a_blocker():
    with pytest.raises(ExperimentIIIError) as error:
        assert_not_a_blocker("SCIENTIFIC_NULL")
    assert "publishable" in str(error.value)
    assert "SCIENTIFIC_NULL" not in III_B_BLOCKER_CODES
    with pytest.raises(ExperimentIIIError):
        assert_not_a_blocker("CLEAN_SKIP")
    assert_not_a_blocker("TECHNICAL_FAIL")


def test_d22_a_clean_skip_closure_receipt_is_not_a_failure():
    receipt = iii_b_closure_receipt(
        outcome="CLEAN_SKIP",
        rung=None,
        claim=None,
        iii_a_closure_conditions=["A0_THROUGH_A18_PASS", "PREDICTION_LOCK_WRITTEN"],
    )
    assert receipt["outcome"] == "CLEAN_SKIP"
    assert receipt["iii_a_independence"]["iii_a_closure_unaffected"] is True


# --------------------------------------------------------------------------
# D.23 — Capture unit binding
# --------------------------------------------------------------------------

@pytest.fixture(scope="module")
def cell():
    return build_iii_b_cell(identity_rows(1)[0], Q_HIGH)


def test_d23_capture_unit_id_format(cell):
    assert cell.capture_unit_id == "e3_t01__L4__q0.2000"
    assert capture_unit_id("e3_t01", Q_LOW) == "e3_t01__L4__q0.0125"
    assert capture_unit_id("e3_t01", Q_MID) == "e3_t01__L4__q0.0500"
    assert (
        machine_authority()["experiment_iii_b"]["capture_unit_id_format"]
        == "{identity}__L4__q{q:.4f}"
    )


def test_d23_the_unit_binds_every_required_field(cell):
    body = cell.as_dict()
    assert body["identity"] == "e3_t01"
    assert body["condition_id"] == III_B_CONDITION.value == "L4"
    assert body["wall_block_id"] == III_B_WALL_BLOCK_ID == "minecraft:stone"
    assert body["q"] == Q_HIGH
    assert body["seed"] == body["noise_seed"] == cell.seed
    assert body["direction"] in ("LEFT_TO_RIGHT", "RIGHT_TO_LEFT")
    assert len(body["path_sha256"]) == 64
    assert len(body["noise_schedule_sha256"]) == 64
    assert body["outer_fold"] == cell.outer_fold
    assert body["inner_rotation"] == cell.inner_rotation


def test_d23_episode_ids_lie_inside_the_reserved_iii_b_block():
    low, high = III_B_EPISODE_ID_BLOCK
    assert (low, high) == (87001, 87999)
    assert tuple(machine_authority()["experiment_iii_b"]["episode_id_block"]) == (low, high)
    seen = set()
    for index in range(1, 26):
        for q in (Q_LOW, Q_MID, Q_HIGH):
            episode = episode_id_for_cell(f"e3_t{index:02d}", q)
            assert low <= episode <= high
            assert episode not in seen
            seen.add(episode)
    # Disjoint from the III-A block 86001-86999.
    assert all(not 86001 <= episode <= 86999 for episode in seen)


def test_d23_each_cell_carries_its_own_19_target_rows_and_its_own_vis_window():
    row = identity_rows(1)[0]
    windows = {}
    for q in (Q_LOW, Q_MID, Q_HIGH):
        built = build_iii_b_cell(row, q)
        assert len(built.target_model_frame_indices) == 19
        assert sorted(built.tau_by_model_frame_index.values()) == list(range(1, 20))
        windows[q] = built.target_model_frame_indices
    # q rescales the innovations, so the windows genuinely differ across q.
    assert len({window for window in windows.values()}) == 3


def test_d23_an_unknown_q_level_is_refused():
    with pytest.raises(ExperimentIIIError) as error:
        episode_id_for_cell("e3_t01", 0.07)
    assert error.value.blocker == "B_Q_PAIRING_MISMATCH"


# --------------------------------------------------------------------------
# D.24 — Array shapes and byte sizes
# --------------------------------------------------------------------------

def test_d24_occluded_and_vis_shapes_and_byte_counts_are_exact():
    assert OCCLUDED_SHAPE == (19, 336, 2048)
    assert VIS_SHAPE == (6, 336, 2048)
    assert OCCLUDED_NPY_BYTES == 26_148_992
    assert VIS_NPY_BYTES == 8_257_664
    workload = machine_authority()["experiment_iii_b"]["workload"]
    assert workload["bytes_per_npy_19_rows"] == OCCLUDED_NPY_BYTES
    assert workload["bytes_per_npy_6_rows"] == VIS_NPY_BYTES
    assert expected_bytes_for(19) == OCCLUDED_NPY_BYTES
    assert expected_bytes_for(6) == VIS_NPY_BYTES


def test_d24_arrays_are_little_endian_float16():
    record = {
        "layer": 19,
        "temporal_slice": "CURRENT",
        "shape": list(OCCLUDED_SHAPE),
        "dtype": "<f2",
        "byte_size": OCCLUDED_NPY_BYTES,
    }
    validate_iii_b_array(record)
    with pytest.raises(ExperimentIIIError) as error:
        validate_iii_b_array({**record, "dtype": "float16"})
    assert error.value.blocker == "B_EXTRACTION_FAIL"


def test_d24_only_layer_19_is_serialized():
    assert_only_l19_serialized([19])
    for forbidden in (4, 10):
        with pytest.raises(ExperimentIIIError) as error:
            assert_only_l19_serialized([19, forbidden])
        assert error.value.blocker == "B_EXTRACTION_FAIL"
    assert machine_authority()["experiment_iii_b"]["workload"]["layers"] == [19]


def test_d24_a_wrong_byte_count_is_refused():
    with pytest.raises(ExperimentIIIError):
        validate_iii_b_array(
            {
                "layer": 19,
                "temporal_slice": "PREVIOUS",
                "shape": list(VIS_SHAPE),
                "dtype": "<f2",
                "byte_size": VIS_NPY_BYTES - 128,
            }
        )


def test_d24_the_inventory_has_two_slices_per_window_per_unit():
    inventory = iii_b_extraction_inventory(["e3_t01__L4__q0.2000", "e3_t02__L4__q0.2000"])
    assert inventory["array_count"] == 8
    assert inventory["temporal_slices"] == ["PREVIOUS", "CURRENT"]
    assert inventory["total_bytes"] == 2 * 2 * (OCCLUDED_NPY_BYTES + VIS_NPY_BYTES)


# --------------------------------------------------------------------------
# D.25 — Belief-state ladder coverage
# --------------------------------------------------------------------------

def test_d25_all_seven_rungs_are_defined():
    assert sorted(LADDER_RUNGS) == [1, 2, 3, 4, 5, 6, 7]
    machine = machine_authority()["experiment_iii_b"]["belief_state_ladder"]
    assert machine["rungs"] == 7
    assert machine["only_rung_4_licenses_calibrated_belief_state"] is True
    assert machine["no_rung_licenses_u4_causal_use_steering_or_object_permanence"] is True


@pytest.mark.parametrize(
    "pattern,expected",
    [
        (dict(mu_decodable=True, sigma_decodable=False, scale_calibrated=False, mean_gate_passes=True), 1),
        (dict(mu_decodable=False, sigma_decodable=True, scale_calibrated=False, mean_gate_passes=False), 2),
        (dict(mu_decodable=True, sigma_decodable=True, scale_calibrated=False, mean_gate_passes=True), 3),
        (dict(mu_decodable=True, sigma_decodable=True, scale_calibrated=True, mean_gate_passes=True), 4),
        (dict(mu_decodable=False, sigma_decodable=False, scale_calibrated=False, mean_gate_passes=False), 5),
        (
            dict(
                mu_decodable=True,
                sigma_decodable=True,
                scale_calibrated=False,
                mean_gate_passes=True,
                tau_only_baseline_matches_probe=True,
                delta_ci_contains_zero=True,
            ),
            6,
        ),
        (
            dict(
                mu_decodable=True,
                sigma_decodable=True,
                scale_calibrated=False,
                mean_gate_passes=True,
                q_only_baseline_matches_probe=True,
                delta_ci_contains_zero=True,
            ),
            7,
        ),
    ],
)
def test_d25_exactly_one_rung_is_selected_for_any_result_pattern(pattern, expected):
    assert select_ladder_rung(**pattern) == expected


def test_d25_a_claim_outside_the_selected_rung_is_rejected():
    assert_claim_within_rung(LADDER_RUNGS[4]["claim"], 4)
    with pytest.raises(ExperimentIIIError):
        assert_claim_within_rung("a calibrated Gaussian belief state", 3)
    for rung in LADDER_RUNGS:
        for refused in ("this licenses U4", "supports causal use", "object permanence"):
            with pytest.raises(ExperimentIIIError):
                assert_claim_within_rung(refused, rung)


# --------------------------------------------------------------------------
# D.26 — III-A independence (the invariant test)
# --------------------------------------------------------------------------

def test_d26_no_iii_a_lifecycle_state_lists_a_b_state_in_its_entry_conditions():
    report = assert_iii_a_independence()
    assert report["iii_a_states_referencing_a_b_state"] == 0
    assert report["iii_a_states_checked"] > 0


def test_d26_iii_a_closure_makes_no_reference_to_iii_b():
    conditions = machine_authority()["closure"]["conditions"]
    result = simulate_total_iii_b_failure(conditions)
    assert result["iii_a_closure_unaffected"] is True
    assert result["iii_a_closure_delayed_for_iii_b"] is False


def test_d26_a_contaminated_closure_condition_is_detected():
    with pytest.raises(ExperimentIIIError) as error:
        simulate_total_iii_b_failure(["A18_PASS", "III_B_RESULT_LOCKED"])
    assert error.value.blocker == "B_III_A_DEPENDENCY_DETECTED"


def test_d26_the_only_iii_a_dependency_on_iii_b_is_i02_to_ib02_ib03():
    import json
    from pathlib import Path

    from mineocclude.experiment_iii.authority import AUTHORITY_ROOT

    graph = json.loads(
        (AUTHORITY_ROOT / "IMPLEMENTATION_TASK_GRAPH.json").read_text(encoding="utf-8")
    )
    runtime_stages = set(III_B_LIFECYCLE_STATES)
    for task in graph["tasks"]:
        if task["id"].startswith("IB"):
            continue
        dependencies = set(task["dependencies"])
        iii_b = {name for name in dependencies if name.startswith("IB")}
        assert iii_b <= {"IB02", "IB03"}, f"{task['id']} depends on {iii_b}"
        assert task["lifecycle_stage"] not in runtime_stages


# --------------------------------------------------------------------------
# D.27 — Launch-gate inputs are outcome-independent
# --------------------------------------------------------------------------

def test_d27_the_gate_reads_time_technical_state_and_resources_only():
    gate = LaunchGate()
    verdict = gate.evaluate(now=LAUNCH_GATE_EVALUATIONS[0], **GO_INPUTS)
    assert verdict["verdict"] == "GO"
    assert verdict["scientific_outcome_consulted"] is False
    assert verdict["decision_inputs"] == "TIME_TECHNICAL_STATE_AND_RESOURCES_ONLY"


def test_d27_a_scientific_outcome_field_is_refused_not_ignored():
    gate = LaunchGate()
    with pytest.raises(ExperimentIIIError) as error:
        gate.evaluate(now=LAUNCH_GATE_EVALUATIONS[0], **GO_INPUTS, u2_positive=True)
    assert error.value.blocker == "B_Q_FALLBACK_OUTCOME_DRIVEN"
    assert gate.evaluations == []
    for field in ("rho", "p_value", "effect_size", "observed_performance"):
        with pytest.raises(ExperimentIIIError):
            assert_no_scientific_outcome_input({field: 1.0})


def test_d27_pool_working_requirement_is_15_gib_in_bytes():
    assert POOL_WORKING_FREE_GATE_BYTES == 15 * (1 << 30) == 16_106_127_360
    machine = machine_authority()["experiment_iii_b"]["launch_gate"]
    assert machine["pool_working_free_gate_bytes"] == POOL_WORKING_FREE_GATE_BYTES
    gate = LaunchGate()
    verdict = gate.evaluate(
        now=LAUNCH_GATE_EVALUATIONS[0],
        **{**GO_INPUTS, "pool_working_free_bytes": POOL_WORKING_FREE_GATE_BYTES - 1},
    )
    assert verdict["results"]["POOL_WORKING_FREE_GE_15_GIB"] is False
    assert verdict["verdict"] == "NO_GO"


def test_d27_pool_durable_is_evaluated_only_when_it_is_a_distinct_filesystem():
    assert POOL_DURABLE_FREE_GATE_BYTES == 5 * (1 << 30)
    shared = LaunchGate().evaluate(
        now=LAUNCH_GATE_EVALUATIONS[0],
        **{
            **GO_INPUTS,
            "pool_durable_is_distinct_local_filesystem": False,
            "pool_durable_free_bytes": 0,
        },
    )
    assert shared["pool_durable_requirement"] == "N/A"
    assert shared["verdict"] == "GO"
    distinct = LaunchGate().evaluate(
        now=LAUNCH_GATE_EVALUATIONS[0],
        **{**GO_INPUTS, "pool_durable_free_bytes": 0},
    )
    assert distinct["pool_durable_requirement"] == "EVALUATED"
    assert distinct["verdict"] == "NO_GO"


def test_d27_the_eight_requirements_are_unchanged_in_count():
    assert len(LAUNCH_GATE_REQUIREMENTS) == 8
    machine = machine_authority()["experiment_iii_b"]["launch_gate"]
    assert machine["requirement_count"] == 8
    assert tuple(machine["requirements"]) == LAUNCH_GATE_REQUIREMENTS


# --------------------------------------------------------------------------
# D.28 — Two evaluations only
# --------------------------------------------------------------------------

def test_d28_the_gate_evaluates_at_1200_then_at_most_once_at_1700():
    assert LAUNCH_GATE_EVALUATIONS == (
        dt.datetime(2026, 9, 2, 12, 0),
        dt.datetime(2026, 9, 2, 17, 0),
    )
    gate = LaunchGate()
    no_go = {**GO_INPUTS, "iii_a_capture_closed": False}
    first = gate.evaluate(now=LAUNCH_GATE_EVALUATIONS[0], **no_go)
    assert first["verdict"] == "NO_GO"
    second = gate.evaluate(now=LAUNCH_GATE_EVALUATIONS[1], **no_go)
    assert second["verdict"] == "NO_GO"
    assert second["outcome"] == "CLEAN_SKIP"
    assert second["blocker"] == "B_GATE_NOT_MET"


def test_d28_a_third_evaluation_is_refused():
    gate = LaunchGate()
    no_go = {**GO_INPUTS, "iii_a_on_schedule": False}
    gate.evaluate(now=LAUNCH_GATE_EVALUATIONS[0], **no_go)
    gate.evaluate(now=LAUNCH_GATE_EVALUATIONS[1], **no_go)
    with pytest.raises(ExperimentIIIError) as error:
        gate.evaluate(now=dt.datetime(2026, 9, 2, 19, 0), **no_go)
    assert error.value.blocker == "B_GATE_NOT_MET"
    assert gate.receipt()["third_reconsideration_permitted"] is False


def test_d28_a_friday_launch_is_refused():
    friday = dt.datetime(2026, 9, 4, 12, 0)
    assert friday.weekday() == 4
    gate = LaunchGate()
    with pytest.raises(ExperimentIIIError):
        gate.evaluate(now=friday, **GO_INPUTS)
    assert gate.receipt()["friday_launch_permitted"] is False


# --------------------------------------------------------------------------
# D.29 — Drop-level inputs
# --------------------------------------------------------------------------

PRIORITY = [f"e3_t{index:02d}" for index in range(1, 26)]


def test_d29_the_level_is_selected_from_time_completion_and_resources_only():
    result = select_drop_level(
        now=dt.datetime(2026, 9, 2, 13, 0),
        complete_identity_triples=25,
        remaining_capture_hours=6.0,
        pool_working_free_bytes=20 * (1 << 30),
        identity_priority_order=PRIORITY,
    )
    assert result["level"] == "NORMAL"
    assert result["selection_inputs"] == "TIME_TECHNICAL_COMPLETION_AND_RESOURCES_ONLY"
    assert result["outcome_based_selection_allowed"] is False
    assert set(DROP_LEVELS) == {"NORMAL", "LEVEL_1", "LEVEL_2", "LEVEL_3", "LEVEL_4"}


def test_d29_a_scientific_outcome_is_refused():
    with pytest.raises(ExperimentIIIError) as error:
        select_drop_level(
            now=dt.datetime(2026, 9, 2, 13, 0),
            complete_identity_triples=25,
            remaining_capture_hours=6.0,
            pool_working_free_bytes=20 * (1 << 30),
            u2_positive=True,
        )
    assert error.value.blocker == "B_Q_FALLBACK_OUTCOME_DRIVEN"


def test_d29_level_3_orders_identities_by_priority_never_by_performance():
    result = select_drop_level(
        now=dt.datetime(2026, 9, 2, 13, 0),
        complete_identity_triples=18,
        remaining_capture_hours=6.0,
        pool_working_free_bytes=20 * (1 << 30),
        identity_priority_order=PRIORITY,
    )
    assert result["level"] == "LEVEL_3"
    assert result["ordering"] == "identity_priority_order"
    assert result["selected_identities"] == PRIORITY[:15]


def test_d29_level_1_reduces_the_u2_family_to_two():
    result = select_drop_level(
        now=dt.datetime(2026, 9, 3, 10, 0),
        complete_identity_triples=25,
        remaining_capture_hours=2.5,
        pool_working_free_bytes=20 * (1 << 30),
        identity_priority_order=PRIORITY,
    )
    assert result["level"] == "LEVEL_1"
    assert result["u2_family_size"] == 2
    assert result["u2_s3_estimable"] is False
    assert result["q_set"] == [0.05, 0.2]


def test_d29_insufficient_storage_or_time_selects_the_clean_skip():
    starved = select_drop_level(
        now=dt.datetime(2026, 9, 2, 13, 0),
        complete_identity_triples=25,
        remaining_capture_hours=6.0,
        pool_working_free_bytes=1 << 30,
        identity_priority_order=PRIORITY,
    )
    assert starved["level"] == "LEVEL_4"
    assert starved["is_an_honourable_pre_registered_outcome"] is True
    assert starved["new_captures"] == 0


# --------------------------------------------------------------------------
# D.30 — Absolute stop
# --------------------------------------------------------------------------

def test_d30_no_new_scientific_execution_may_begin_at_the_absolute_deadline():
    assert ABSOLUTE_EXPERIMENT_DEADLINE == dt.datetime(2026, 9, 3, 20, 0)
    machine = machine_authority()["absolute_deadline"]
    assert "2026-09-03" in str(machine)
    before = assert_absolute_stop(
        now=dt.datetime(2026, 9, 3, 19, 59), starting_new_scientific_execution=True
    )
    assert before["past_deadline"] is False
    with pytest.raises(ExperimentIIIError) as error:
        assert_absolute_stop(
            now=ABSOLUTE_EXPERIMENT_DEADLINE, starting_new_scientific_execution=True
        )
    assert error.value.blocker == "B_DEADLINE_DROP"


def test_d30_no_friday_experiment_execution_is_planned():
    state = assert_absolute_stop(
        now=dt.datetime(2026, 9, 4, 9, 0), starting_new_scientific_execution=False
    )
    assert state["friday_experiment_execution_planned"] is False
    assert state["past_deadline"] is True


def test_d30_iii_a_closure_is_never_delayed_for_iii_b():
    state = assert_absolute_stop(
        now=dt.datetime(2026, 9, 3, 12, 0), starting_new_scientific_execution=False
    )
    assert state["iii_a_closure_delayed_for_iii_b"] is False


def test_d30_a_clean_skip_leaves_iii_a_closure_conditions_satisfied():
    conditions = machine_authority()["closure"]["conditions"]
    receipt = iii_b_closure_receipt(
        outcome="CLEAN_SKIP", rung=None, claim=None, iii_a_closure_conditions=conditions
    )
    assert receipt["iii_a_independence"]["iii_a_closure_unaffected"] is True
    assert receipt["iii_a_independence"]["iii_a_closure_conditions"] == list(conditions)
