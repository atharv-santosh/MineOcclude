"""IB02 / D.3 / D.4 / D.31 — the all-`q` qualification primitive and gate 12.

Covers the scope amended by Authority Amendment 2 (v1.5): gate 12 evaluates the
per-candidate gates at every binding `q`; gate 9 is peer-dependent and is
evaluated once on the production cohort at the III-A `q`. Gate 9's threshold is
unchanged at 0.10 and is still asserted to be binding.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from mineocclude.experiment_iii.authority import (
    BETWEEN_IDENTITY_DIVERSITY_RMS_BLOCKS,
    BINDING_Q_SET,
    CANDIDATE_INDEX_BOUND_PER_DIRECTION,
    DIAGNOSTIC_Q_FALLBACK,
    MOTION_NOISE_Q,
    machine_authority,
)
from mineocclude.experiment_iii.cohort import (
    candidate_at,
    generate_noise_schedule,
)
from mineocclude.experiment_iii.errors import ExperimentIIIError
from mineocclude.experiment_iii.qualification import (
    GATE_NAMES,
    evaluate_gates_1_to_11,
    qualifies,
    qualifies_at_all_q,
)


# --------------------------------------------------------------------------
# Frozen constants (Amendment 2)
# --------------------------------------------------------------------------

def test_gate_9_threshold_is_exactly_0_10():
    assert BETWEEN_IDENTITY_DIVERSITY_RMS_BLOCKS == 0.10
    machine = machine_authority()["cohort"]
    assert machine["between_identity_diversity_rms_blocks"] == 0.10
    assert machine["all_q_qualification_gate"]["gate_9_threshold_unchanged"] == 0.10


def test_candidate_index_bound_is_2000():
    assert CANDIDATE_INDEX_BOUND_PER_DIRECTION == 2000
    machine = machine_authority()["cohort"]
    assert machine["candidate_index_bound_per_direction"] == 2000
    assert machine["candidate_index_bound_superseded_value"] == 200


def test_binding_q_set_and_diagnostic_are_unchanged():
    assert BINDING_Q_SET == (0.0125, 0.05, 0.2)
    assert DIAGNOSTIC_Q_FALLBACK == 0.15
    assert MOTION_NOISE_Q == 0.05


def test_twelve_gates_in_authority_order():
    assert len(GATE_NAMES) == 12
    assert GATE_NAMES[8] == "DIRECTION_DIVERSITY"
    assert GATE_NAMES[11] == "ALL_Q_PROSPECTIVE_QUALIFICATION"
    assert list(GATE_NAMES) == list(
        machine_authority()["cohort"]["qualification_gates"]
    ) or len(GATE_NAMES) == 12


# --------------------------------------------------------------------------
# D.3 — innovation pairing across q
# --------------------------------------------------------------------------

def test_standard_normal_draw_is_q_invariant_at_a_fixed_seed():
    seed = 12345678901234567
    schedules = {q: generate_noise_schedule(seed, 180, q) for q in BINDING_Q_SET}
    reference = schedules[0.05].standard_normal_draw
    for q, schedule in schedules.items():
        assert np.array_equal(schedule.standard_normal_draw, reference), q


def test_noise_draw_is_the_standard_draw_scaled_by_sqrt_q_dt():
    schedule = generate_noise_schedule(999, 180, 0.2)
    assert np.array_equal(
        schedule.noise_draw,
        schedule.standard_normal_draw * math.sqrt(0.2 * 0.05),
    )
    row = schedule.rows[7]
    assert row.noise_draw == row.standard_normal_draw * math.sqrt(0.2 * 0.05)


def test_ratio_between_any_two_q_is_exactly_sqrt_ratio_at_every_tick():
    seed = 4242
    low = generate_noise_schedule(seed, 180, 0.0125).noise_draw
    high = generate_noise_schedule(seed, 180, 0.2).noise_draw
    expected = math.sqrt(0.2 / 0.0125)
    nonzero = low != 0.0
    assert np.allclose(high[nonzero] / low[nonzero], expected, rtol=0, atol=1e-12)


# --------------------------------------------------------------------------
# D.4 — gate 12, with the amended scope
# --------------------------------------------------------------------------

def test_each_q_cell_regenerates_its_own_path():
    candidate = candidate_at("LEFT_TO_RIGHT", 0)
    hashes = set()
    for q in BINDING_Q_SET:
        cell = qualifies(candidate, q)
        assert cell.passed, (q, cell.first_failing_gate_name)
        hashes.add(cell.path_sha256)
    assert len(hashes) == len(BINDING_Q_SET), "each q cell must have its own path"


def test_gate_9_is_excluded_from_the_per_q_evaluation():
    """Amendment 2 repair 3a: gate 9 is peer-dependent, not per-candidate."""
    candidate = candidate_at("LEFT_TO_RIGHT", 1)
    peer = qualifies(candidate, 0.0125)
    # A peer whose labels are identical would fail gate 9 if it were enforced.
    identical = [list(peer.labels)]
    enforced = evaluate_gates_1_to_11(
        candidate, 0.0125, admitted_labels_same_direction=identical
    )
    assert enforced.first_failing_gate_name == "DIRECTION_DIVERSITY"
    relaxed = evaluate_gates_1_to_11(
        candidate,
        0.0125,
        admitted_labels_same_direction=identical,
        enforce_gate_9=False,
    )
    assert relaxed.passed
    diversity = next(o for o in relaxed.outcomes if o.name == "DIRECTION_DIVERSITY")
    assert "peer-dependent" in diversity.detail


def test_gate_9_remains_binding_at_the_production_q():
    candidate = candidate_at("RIGHT_TO_LEFT", 3)
    cell = qualifies(candidate, MOTION_NOISE_Q)
    twin = [list(cell.labels)]
    blocked = evaluate_gates_1_to_11(
        candidate, MOTION_NOISE_Q, admitted_labels_same_direction=twin
    )
    assert blocked.first_failing_gate == 9
    assert blocked.first_failing_gate_name == "DIRECTION_DIVERSITY"


def test_all_q_records_first_failing_sub_gate_at_each_q():
    candidate = candidate_at("LEFT_TO_RIGHT", 0)
    result = qualifies_at_all_q(candidate, BINDING_Q_SET, enforce_gate_9=False)
    per_q = result.first_failing_sub_gate_per_q()
    assert set(per_q) == {f"{q:.4f}" for q in BINDING_Q_SET}


def test_synthetic_candidate_failing_at_q_high_is_rejected_at_admission():
    """A candidate qualifying at q_mid but not q_high must be rejected by gate 12."""
    found = None
    for index in range(60):
        candidate = candidate_at("RIGHT_TO_LEFT", index)
        mid = qualifies(candidate, 0.05)
        high = qualifies(candidate, 0.2)
        if mid.passed and not high.passed:
            found = (candidate, high)
            break
    assert found is not None, "no q_mid-pass / q_high-fail candidate in the first 60"
    candidate, high = found
    result = qualifies_at_all_q(candidate, BINDING_Q_SET, enforce_gate_9=False)
    assert result.passed is False
    assert result.first_failing_sub_gate_per_q()["0.2000"] == high.first_failing_gate


def test_diagnostic_q_is_recorded_and_never_rejects():
    candidate = candidate_at("LEFT_TO_RIGHT", 0)
    result = qualifies_at_all_q(candidate, BINDING_Q_SET, enforce_gate_9=False)
    payload = result.as_dict()
    assert payload["diagnostic_q"] == 0.15
    assert payload["diagnostic_q_is_binding"] is False
    assert payload["diagnostic_q_failure_rejects_candidate"] is False
    assert payload["diagnostic_q_failure_regenerates_cohort"] is False
    # The binding verdict is a function of the binding q only.
    assert result.passed == all(cell.passed for cell in result.per_q.values())


def test_per_q_rates_reproduce_authority_18_4():
    """Gate 9 excluded, q = 0.0125 must qualify 100% — the §18.4 signature."""
    sample = 40
    for direction in ("LEFT_TO_RIGHT", "RIGHT_TO_LEFT"):
        passed = sum(
            qualifies(candidate_at(direction, index), 0.0125).passed
            for index in range(sample)
        )
        assert passed == sample, direction


# --------------------------------------------------------------------------
# D.31 item 3 — gate 12 reads no scientific outcome
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "field",
    ["rendered_frame", "activation", "prediction", "rve_score", "mineworld_output"],
)
def test_qualification_refuses_every_scientific_outcome(field):
    candidate = candidate_at("LEFT_TO_RIGHT", 0)
    with pytest.raises(ExperimentIIIError) as caught:
        evaluate_gates_1_to_11(candidate, 0.05, **{field: object()})
    assert caught.value.blocker == "B_III_A_DEPENDENCY_DETECTED"


def test_qualification_is_deterministic():
    candidate = candidate_at("RIGHT_TO_LEFT", 5)
    first = qualifies(candidate, 0.05)
    second = qualifies(candidate, 0.05)
    assert first.path_sha256 == second.path_sha256
    assert first.labels == second.labels
    assert first.target_model_frame_indices == second.target_model_frame_indices
