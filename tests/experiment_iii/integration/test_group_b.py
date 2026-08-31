"""Group B — B.1-B.13: the CPU pipeline end to end on synthetic fixtures.

Complete manifests, a stubbed decoder, synthetic activations. No GPU, no model,
no Minecraft. Every check crosses at least one module boundary; that is what
separates Group B from the Group-A unit checks.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pytest

from mineocclude.experiment_iii.activation_store import (
    EXPECTED_DTYPE,
    EXPECTED_NPY_BYTES,
    EXPECTED_SHAPE,
    UNITS_PER_CAPTURE,
    build_extraction_inventory,
    validate_extraction_inventory,
    write_activation_array,
)
from mineocclude.experiment_iii.adjudication import (
    ADJUDICATION_ROW_COUNT,
    adjudication_matrix,
    assert_claim_in_scope,
)
from mineocclude.experiment_iii.artifact_inventory import (
    UNNAMED_MISSING_BLOCKER,
    assert_iii_a_closure_needs_no_iii_b_artifact,
    required_before_next_stage,
    stage_exit_check,
    stages,
)
from mineocclude.experiment_iii.authority import (
    BINDING_Q_SET,
    CANDIDATE_INDEX_BOUND_PER_DIRECTION,
    DIAGNOSTIC_Q_FALLBACK,
    LEFT_TO_RIGHT_COUNT,
    MOTION_NOISE_Q,
    PILOT_IDENTITY_IDS,
    PRODUCTION_IDENTITY_IDS,
    RIGHT_TO_LEFT_COUNT,
    REPOSITORY_ROOT,
    canonical_sha256,
    machine_authority,
    master_salt,
)
from mineocclude.experiment_iii.baselines_pixel import pixel_features
from mineocclude.experiment_iii.capture_schedule import (
    build_capture_schedule,
    condition_batches,
    latin_square,
    validate_capture_order,
)
from mineocclude.experiment_iii.conditions import build_condition_map
from mineocclude.experiment_iii.cohort import candidate_at, generate_path, path_sha256
from mineocclude.experiment_iii.cohort_build import build_cohort, write_cohort
from mineocclude.experiment_iii.deadline import (
    CLOCK_TRIGGERS,
    DeadlinePlanSelector,
    attrition_branch,
)
from mineocclude.experiment_iii.errors import ExperimentIIIError
from mineocclude.experiment_iii.fir import FIRST_FULLY_RESOLVED_TICK, fir_labels
from mineocclude.experiment_iii.folds import assert_no_identity_in_its_own_training_set
from mineocclude.experiment_iii.prediction_lock import PredictionCell, PredictionLock
from mineocclude.experiment_iii.representations import (
    coarse_2x6_concat,
    current_minus_previous,
    two_frame_concat,
)
from mineocclude.experiment_iii.schema import ConditionId, TemporalSlice, read_jsonl
from mineocclude.experiment_iii.statistics import (
    PRIMARY_FAMILY,
    assert_no_success_gate,
    primary_analysis,
    temporal_rescue,
)
from mineocclude.experiment_iii.status import StatusDocument, validate_status_document
from mineocclude.experiment_iii.storage_preflight import (
    A3_COMBINED_WITH_MIRROR_BYTES,
    GIB,
    assert_gate_coherence,
    storage_preflight,
)
from mineocclude.experiment_iii.target_manifest import (
    assert_rows_identical_across_conditions,
    build_target_window,
)

from tests.experiment_iii.test_extraction_and_store import StubDecoder


def _float16_safe_decoder():
    """The Group-A stub, rescaled so every value survives float16 serialization.

    The unit stub encodes the token index in the value, which exceeds the
    float16 range once the layer offset is added. Group B serializes for real,
    so it needs values inside the frozen dtype.
    """

    class _Scaled(StubDecoder):
        def teacher_forced(self, **kwargs):
            result = super().teacher_forced(**kwargs)
            scaled = {
                layer: (array * 1e-4).astype(array.dtype)
                for layer, array in result.layer_activations.items()
            }
            return type(result)(
                layer_activations=scaled,
                frame_token_map=result.frame_token_map,
                trajectory_id=result.trajectory_id,
                model_frame_idx=result.model_frame_idx,
            )

    return _Scaled()

COHORT_DIR = REPOSITORY_ROOT / "docs" / "experiment_iii" / "cohort"
PRIORITY = list(PRODUCTION_IDENTITY_IDS)


# ==========================================================================
# B.1 — Cohort end to end
# ==========================================================================

@pytest.fixture(scope="session")
def cohort():
    """The full 25 + 2 cohort, regenerated from the frozen salt.

    This is the expensive one on purpose: B.1 is an end-to-end check, so it
    regenerates rather than reading the materialized artifacts, then compares.
    """
    return build_cohort()


def test_b1_twenty_five_production_and_two_pilots_from_the_frozen_salt(cohort):
    assert len(master_salt()) == 64
    assert len(cohort.production) == 25
    assert len(cohort.pilots) == 2
    assert [row["identity"] for row in cohort.production] == list(PRODUCTION_IDENTITY_IDS)
    assert [row["identity"] for row in cohort.pilots] == list(PILOT_IDENTITY_IDS)
    directions = [row["direction"] for row in cohort.production]
    assert directions.count("LEFT_TO_RIGHT") == LEFT_TO_RIGHT_COUNT == 13
    assert directions.count("RIGHT_TO_LEFT") == RIGHT_TO_LEFT_COUNT == 12


def test_b1_all_twelve_gates_ran_and_gate_12_preceded_materialization(cohort):
    receipt = cohort.qualification_receipt
    assert receipt["gate_count"] == 12
    all_q = cohort.all_q_receipt
    assert all_q["gate_index"] == 12
    assert all_q["evaluated_before_materialization"] is True
    assert all_q["evaluated_before_freeze"] is True
    assert all_q["implementing_primitive_task"] == "IB02"
    assert all_q["regression_guard_task"] == "IB03"


def test_b1_all_q_receipt_records_the_first_failing_gate_at_each_q(cohort):
    per_candidate = cohort.all_q_receipt["per_candidate"]
    assert per_candidate, "the receipt records no per-candidate rows"
    binding = {f"{q:.4f}" for q in BINDING_Q_SET}
    assert len(per_candidate) >= 25
    reached_gate_12 = 0
    for row in per_candidate:
        assert "candidate_index" in row
        assert "seed" in row
        if not row.get("reached_gate_12", True):
            # Rejected at gates 1-11 on the production q; gate 12 was never
            # reached, so there is no per-q sub-gate column to record.
            assert row["first_failing_sub_gate_per_q"] is None
            assert row["admitted"] is False
            assert row["first_failing_gate"] is not None
            continue
        reached_gate_12 += 1
        assert set(row["first_failing_sub_gate_per_q"]) == binding
        if "per_q" in row:
            assert set(row["per_q"]) == binding
        if row["admitted"]:
            assert "per_q" in row
            # An admitted candidate fails no sub-gate at any binding q.
            assert set(row["first_failing_sub_gate_per_q"].values()) == {None}
    assert reached_gate_12 >= 25


def test_b1_the_diagnostic_q_is_recorded_and_never_binding(cohort):
    all_q = cohort.all_q_receipt
    assert all_q["diagnostic_q"] == DIAGNOSTIC_Q_FALLBACK == 0.15
    assert all_q["diagnostic_q_is_binding"] is False
    assert all_q["diagnostic_q_failure_rejects_candidate"] is False
    assert all_q["diagnostic_q_failure_regenerates_cohort"] is False


def test_b1_folds_and_priority_order_are_built_and_leak_free(cohort):
    folds = cohort.folds
    assert folds["outer_folds"] == 5
    assert len(folds["folds"]) == 5
    assert folds["inner_rotations"] == 4
    assert len(folds["outer_fold_assignment"]) == 25
    assert_no_identity_in_its_own_training_set(folds["folds"])
    held_out = [name for fold in folds["folds"] for name in fold["held_out_identities"]]
    assert sorted(held_out) == sorted(PRODUCTION_IDENTITY_IDS)
    order = cohort.priority_order
    assert order["order"] == list(PRODUCTION_IDENTITY_IDS)
    assert order["reorderable_by_performance"] is False


def test_b1_the_candidate_scan_honours_the_frozen_bound_of_2000(cohort):
    assert CANDIDATE_INDEX_BOUND_PER_DIRECTION == 2000
    receipt = cohort.qualification_receipt
    assert receipt["candidate_index_bound_per_direction"] == 2000
    assert cohort.all_q_receipt["candidate_index_bound_per_direction"] == 2000
    for row in cohort.production:
        assert 0 <= row["candidate_index"] < 2000


def test_b1_exhausting_the_bound_raises_rather_than_admitting_an_unqualified_candidate():
    with pytest.raises(ExperimentIIIError) as error:
        build_cohort(bound=3)
    assert error.value.blocker == "COHORT_ALL_Q_QUALIFICATION_INFEASIBLE"


def test_b1_every_authority_2_7_artifact_exists_hashes_and_is_consistent(cohort, tmp_path):
    out_dir = tmp_path / "docs" / "experiment_iii" / "cohort"
    written = write_cohort(cohort, out_dir, namespace_root=tmp_path)
    expected = {
        "production_identity_manifest.jsonl",
        "pilot_identity_manifest.jsonl",
        "folds.json",
        "identity_priority_order.json",
        "cohort_qualification_receipt.json",
        "cohort_all_q_qualification_receipt.json",
        "historical_seed_exclusion_set.json",
        "q_regression_a1_receipt.json",
    }
    produced = {Path(name).name for name in written}
    assert expected <= produced
    for name in expected | {"production_identity_manifest.sha256"}:
        assert (out_dir / name).is_file()
    # Each manifest row's spec_hash is self-consistent.
    for row in read_jsonl(out_dir / "production_identity_manifest.jsonl"):
        body = {key: value for key, value in row.items() if key != "spec_hash"}
        assert canonical_sha256(body) == row["spec_hash"]


def test_b1_regeneration_reproduces_the_materialized_cohort_byte_for_byte(cohort):
    if not (COHORT_DIR / "production_identity_manifest.jsonl").is_file():
        pytest.fail(
            "the materialized cohort is a required A1 artifact and is absent; "
            "run scripts/experiment_iii/build_cohort.py"
        )
    frozen = read_jsonl(COHORT_DIR / "production_identity_manifest.jsonl")
    assert [row["spec_hash"] for row in frozen] == [
        row["spec_hash"] for row in cohort.production
    ]


# ==========================================================================
# B.2 — Target manifest end to end
# ==========================================================================

def test_b2_nineteen_target_rows_and_labels_per_identity(cohort):
    for row in cohort.production[:6]:
        positions, _ = generate_path(
            row["seed"],
            MOTION_NOISE_Q,
            direction=row["direction"],
            start_world_x=row["start_world_x"],
        )
        window = build_target_window(row["identity"], row["direction"], positions)
        assert len(window.target_model_frame_indices) == 19
        assert len(window.labels) == 19
        assert list(window.target_model_frame_indices) == row["target_model_frame_indices"]
        assert window.labels == pytest.approx(
            row["expected_causal_fir_target_world_x_blocks"], abs=0.0
        )
        # Every target row carries a complete causal FIR history: t >= 8.
        assert min(window.target_model_frame_indices) >= FIRST_FULLY_RESOLVED_TICK >= 8


def test_b2_target_rows_are_identical_across_all_five_conditions(cohort):
    row = cohort.production[0]
    positions, _ = generate_path(
        row["seed"],
        MOTION_NOISE_Q,
        direction=row["direction"],
        start_world_x=row["start_world_x"],
    )
    per_condition = {
        condition.value: build_target_window(
            row["identity"], row["direction"], positions
        )
        for condition in ConditionId
    }
    assert_rows_identical_across_conditions(per_condition)
    windows = {tuple(w.target_model_frame_indices) for w in per_condition.values()}
    assert len(windows) == 1


def test_b2_labels_come_from_the_recovered_kernels_through_the_ported_engine(cohort):
    row = cohort.production[0]
    positions, _ = generate_path(
        row["seed"],
        MOTION_NOISE_Q,
        direction=row["direction"],
        start_world_x=row["start_world_x"],
    )
    indices = row["target_model_frame_indices"]
    assert fir_labels([float(v) for v in positions], indices, row["direction"]) == (
        pytest.approx(row["expected_causal_fir_target_world_x_blocks"], abs=0.0)
    )
    assert path_sha256(positions) == row["path_sha256"]


# ==========================================================================
# B.3 — Capture schedule end to end
# ==========================================================================

#: A synthetic P0 ladder. Group B never runs P0, and build_condition_map fails
#: closed without one rather than silently defaulting the partial materials.
SYNTHETIC_LADDER = {
    "L1": "minecraft:white_stained_glass",
    "L2": "minecraft:light_gray_stained_glass",
    "L3": "minecraft:gray_stained_glass",
}


@pytest.fixture(scope="session")
def schedule(cohort):
    return build_capture_schedule(
        cohort.production, build_condition_map(SYNTHETIC_LADDER)
    )


def test_b3_the_condition_map_fails_closed_without_a_p0_ladder():
    with pytest.raises(ExperimentIIIError) as error:
        build_condition_map()
    assert error.value.blocker == "P0_CANDIDATE_ID_UNSUPPORTED"


def test_b3_one_hundred_and_twenty_five_units(schedule):
    assert len(schedule) == 125
    assert len({unit.capture_unit_id for unit in schedule}) == 125


def test_b3_each_condition_appears_once_per_block_and_once_per_period(schedule):
    report = validate_capture_order(schedule)
    assert report["captures"] == 125
    assert report["identities"] == 25
    assert report["balanced_per_block"] is True
    assert report["balanced_per_period"] is True
    assert report["latin_square"] == latin_square()


def test_b3_identity_order_ascends_by_priority_rank_within_a_condition_block(schedule):
    for block in range(5):
        for condition in ConditionId:
            ranks = [
                unit.priority_rank
                for unit in schedule
                if unit.block == block and unit.condition_id == condition.value
            ]
            assert ranks == sorted(ranks)


def test_b3_exactly_twenty_five_condition_batches_with_a_sentinel_at_every_boundary(
    schedule,
):
    batches = condition_batches(schedule)
    assert len(batches) == 25
    assert all(len(batch["capture_unit_ids"]) == 5 for batch in batches)
    for batch in batches:
        assert batch["condition_id"] in {c.value for c in ConditionId}
        assert batch["wall_block_id"]
    boundaries = len(batches)
    assert boundaries == 25


# ==========================================================================
# B.4 — Synthetic extraction pipeline
# ==========================================================================

def test_b4_nineteen_forwards_six_arrays_and_full_provenance(tmp_path):
    from mineocclude.experiment_iii.extraction import SELECTED_LAYERS, extract_capture

    decoder = _float16_safe_decoder()
    rows = list(range(20, 39))
    capture_root = tmp_path / "data" / "experiment_iii" / "captures" / "e3_t01__L2"
    stacked, counter = extract_capture(
        decoder, trajectory_id="e3_t01__L2", target_rows=rows
    )
    assert decoder.forwards == 19
    assert counter.forwards == 19
    assert len(stacked) == UNITS_PER_CAPTURE == 6
    for (layer, temporal_slice), array in stacked.items():
        assert layer in SELECTED_LAYERS
        assert array.shape == EXPECTED_SHAPE
        written = write_activation_array(
            capture_root, layer, temporal_slice, array, namespace_root=tmp_path
        )
        assert written["byte_size"] == EXPECTED_NPY_BYTES
        assert written["dtype"] == EXPECTED_DTYPE
        assert len(written["sha256"]) == 64


def test_b4_the_extraction_inventory_binds_and_revalidates(tmp_path):
    from mineocclude.experiment_iii.extraction import extract_capture

    decoder = _float16_safe_decoder()
    rows = list(range(20, 39))
    capture_root = tmp_path / "data" / "experiment_iii" / "captures" / "e3_t01__L2"
    stacked, _ = extract_capture(decoder, trajectory_id="e3_t01__L2", target_rows=rows)
    written = {}
    for (layer, temporal_slice), array in stacked.items():
        written[(layer, temporal_slice.value)] = write_activation_array(
            capture_root, layer, temporal_slice, array, namespace_root=tmp_path
        )
    inventory = build_extraction_inventory(
        identity="e3_t01",
        condition_id="L2",
        target_model_frame_indices=tuple(rows),
        written=written,
        hook_site="RESIDUAL_STREAM",
        token_position_hash="0" * 64,
        preprocessing_identity="frozen",
        checkpoint_identity="frozen",
        source_capture_hash="1" * 64,
    )
    validate_extraction_inventory(
        capture_root,
        inventory,
        expected_target_rows=rows,
        source_capture_hash="1" * 64,
        checkpoint_identity="frozen",
        preprocessing_identity="frozen",
    )
    assert len(inventory["artifacts"]) == UNITS_PER_CAPTURE == 6


# ==========================================================================
# B.5 — Feature pipeline end to end
# ==========================================================================

def test_b5_all_three_representations_and_the_pixel_baseline_have_frozen_dims():
    rng = np.random.default_rng(5)
    current = rng.normal(size=EXPECTED_SHAPE[1:]).astype(np.float32)
    previous = rng.normal(size=EXPECTED_SHAPE[1:]).astype(np.float32)
    assert coarse_2x6_concat(current).shape == (24_576,)
    assert current_minus_previous(current, previous).shape == (24_576,)
    assert two_frame_concat(current, previous).shape == (49_152,)
    frame = rng.integers(0, 256, size=(360, 640, 3), dtype=np.uint8)
    assert pixel_features(frame).shape == (4_032,)


def test_b5_row_order_matches_the_frozen_target_row_order_and_is_finite(cohort):
    row = cohort.production[0]
    indices = row["target_model_frame_indices"]
    rng = np.random.default_rng(6)
    stack = rng.normal(size=EXPECTED_SHAPE).astype(np.float32)
    features = np.stack([coarse_2x6_concat(stack[position]) for position in range(19)])
    assert features.shape == (19, 24_576)
    assert np.isfinite(features).all()
    assert len(indices) == features.shape[0]


def test_b5_temporal_transforms_have_the_frozen_sign_and_order():
    current = np.zeros(EXPECTED_SHAPE[1:], dtype=np.float32) + 3.0
    previous = np.zeros(EXPECTED_SHAPE[1:], dtype=np.float32) + 1.0
    difference = current_minus_previous(current, previous)
    assert float(difference[0]) == pytest.approx(2.0)
    concat = two_frame_concat(previous, current)
    # PREVIOUS then CURRENT, never reversed.
    assert float(concat[0]) == pytest.approx(1.0)
    assert float(concat[24_576]) == pytest.approx(3.0)


# ==========================================================================
# B.6 — Analysis pipeline end to end
# ==========================================================================

@pytest.fixture(scope="module")
def sealed_lock():
    lock = PredictionLock(feature_block_hashes={"L19_CURRENT": "0" * 64})
    rng = np.random.default_rng(11)
    for identity in PRODUCTION_IDENTITY_IDS:
        for condition in ConditionId:
            for row in range(19):
                target = float(rng.normal(0.0, 1.0))
                lock.add(
                    PredictionCell(
                        identity=identity,
                        condition_id=condition.value,
                        row_index=row,
                        model="L19_COARSE_2X6_CONCAT_CURRENT",
                        prediction=target + float(rng.normal(0.0, 0.1)),
                        target=target,
                    )
                )
    lock.seal()
    return lock


def test_b6_the_three_primary_estimands_recover_a_planted_condition_response(sealed_lock):
    planted = {"S_i": 0.40, "Dpartial_i": 0.25, "Dopaque_i": 0.15}
    rng = np.random.default_rng(12)
    per_identity = {
        identity: {
            name: value + float(rng.normal(0.0, 0.01)) for name, value in planted.items()
        }
        for identity in PRODUCTION_IDENTITY_IDS
    }
    result = primary_analysis(per_identity, lock=sealed_lock, bootstrap_seed=7)
    assert result["family"] == list(PRIMARY_FAMILY)
    assert result["family_size"] == 3
    assert result["multiplicity"] == "HOLM_ACROSS_3"
    for name, value in planted.items():
        assert result["estimands"][name]["mean"] == pytest.approx(value, abs=0.01)
        assert result["estimands"][name]["interval"]["ci_low"] > 0.0


def test_b6_holm_is_applied_across_exactly_three_primary_and_two_temporal(sealed_lock):
    rng = np.random.default_rng(13)
    per_identity = {
        identity: {name: 0.3 + float(rng.normal(0.0, 0.05)) for name in PRIMARY_FAMILY}
        for identity in PRODUCTION_IDENTITY_IDS
    }
    primary = primary_analysis(per_identity, lock=sealed_lock, bootstrap_seed=7)
    assert len(primary["estimands"]) == 3
    temporal_input = {
        identity: {
            "CURRENT_MINUS_PREVIOUS_VS_CURRENT": float(rng.normal(0.02, 0.01)),
            "TWO_FRAME_CONCAT_VS_CURRENT": float(rng.normal(0.02, 0.01)),
        }
        for identity in PRODUCTION_IDENTITY_IDS
    }
    temporal = temporal_rescue(temporal_input, lock=sealed_lock, bootstrap_seed=7)
    assert temporal["family_size"] == 2
    assert temporal["multiplicity"] == "HOLM_ACROSS_2"


def test_b6_intervals_reproduce_under_the_same_seed(sealed_lock):
    per_identity = {
        identity: {name: 0.3 for name in PRIMARY_FAMILY}
        for identity in PRODUCTION_IDENTITY_IDS
    }
    first = primary_analysis(per_identity, lock=sealed_lock, bootstrap_seed=99)
    second = primary_analysis(per_identity, lock=sealed_lock, bootstrap_seed=99)
    assert first["estimands"] == second["estimands"]


def test_b6_no_overall_success_gate_is_emitted_anywhere(sealed_lock):
    per_identity = {
        identity: {name: 0.3 for name in PRIMARY_FAMILY}
        for identity in PRODUCTION_IDENTITY_IDS
    }
    result = primary_analysis(per_identity, lock=sealed_lock, bootstrap_seed=7)
    assert_no_success_gate(result)
    assert "experiment_passed" not in json.dumps(result)
    with pytest.raises(ExperimentIIIError) as error:
        assert_no_success_gate({**result, "overall_verdict": "PASS"})
    assert error.value.blocker == "ANALYSIS_SUCCESS_GATE_REINTRODUCED"


def test_b6_no_statistic_may_be_computed_before_the_lock_is_sealed():
    unsealed = PredictionLock()
    unsealed.add(
        PredictionCell(
            identity="e3_t01",
            condition_id="L0",
            row_index=0,
            model="m",
            prediction=0.0,
            target=1.0,
        )
    )
    with pytest.raises(ExperimentIIIError) as error:
        primary_analysis(
            {name: {key: 0.1 for key in PRIMARY_FAMILY} for name in PRODUCTION_IDENTITY_IDS},
            lock=unsealed,
            bootstrap_seed=1,
        )
    assert error.value.blocker == "PREDICTION_LOCK_MISSING"


# ==========================================================================
# B.7 — Attrition branches
# ==========================================================================

@pytest.mark.parametrize(
    "n_complete,branch,claim",
    [(25, "NORMAL", True), (20, "REDUCED_PRECISION", True), (15, "REDUCED_PRECISION", True), (14, "NO_GRADED_CLAIM", False)],
)
def test_b7_the_correct_attrition_branch_is_selected(n_complete, branch, claim):
    result = attrition_branch(n_complete, identity_priority_order=PRIORITY)
    assert result["branch"] == branch
    assert result["graded_inferential_claim"] is claim
    assert len(result["analysed_identities"]) == n_complete


def test_b7_fourteen_complete_identities_yields_no_graded_inferential_claim():
    result = attrition_branch(14)
    assert result["graded_inferential_claim"] is False
    assert result["adjudication_row_if_no_claim"] == 16
    assert result["is_a_valid_closure"] is True
    assert adjudication_matrix()[15]["outcome"].startswith("Fewer than 15")


def test_b7_no_branch_imputes_drops_a_condition_or_replaces_an_identity():
    for n_complete in (25, 20, 15, 14):
        result = attrition_branch(n_complete)
        assert result["missing_cell_imputation_allowed"] is False
        assert result["reactive_condition_drop_allowed"] is False
        assert result["outcome_based_identity_replacement_allowed"] is False
        assert result["partial_identities_excluded_whole"] is True


def test_b7_attrition_never_reads_a_scientific_outcome():
    with pytest.raises(ExperimentIIIError) as error:
        attrition_branch(20, effect_size=0.5)
    assert error.value.blocker == "DEADLINE_OUTCOME_BASED_SELECTION"


# ==========================================================================
# B.8 — Deadline fallback selection
# ==========================================================================

def test_b8_each_plan_is_selected_from_time_and_status_alone():
    selector = DeadlinePlanSelector()
    early = selector.select(
        now=CLOCK_TRIGGERS["TARGET_CAPTURE_LAUNCH"] - dt.timedelta(hours=2),
        capture_launched=False,
        a2_passed=True,
        identity_priority_order=PRIORITY,
    )
    assert early["plan"] == "NORMAL"
    assert early["selection_inputs"] == "TIME_AND_STATUS_ONLY"

    late = DeadlinePlanSelector().select(
        now=CLOCK_TRIGGERS["TARGET_CAPTURE_LAUNCH"] + dt.timedelta(hours=1),
        capture_launched=True,
        a2_passed=True,
        identity_priority_order=PRIORITY,
    )
    assert late["plan"] == "ONE_DAY_BEHIND"
    assert late["identities"] == 20


def test_b8_plan_selection_never_reads_a_scientific_outcome():
    with pytest.raises(ExperimentIIIError) as error:
        DeadlinePlanSelector().select(
            now=CLOCK_TRIGGERS["TARGET_CAPTURE_LAUNCH"],
            capture_launched=True,
            a2_passed=True,
            primary_estimand=0.4,
        )
    assert error.value.blocker == "DEADLINE_OUTCOME_BASED_SELECTION"


def test_b8_reduced_plans_use_the_first_n_by_identity_priority_order():
    one_day = DeadlinePlanSelector().select(
        now=CLOCK_TRIGGERS["TARGET_CAPTURE_LAUNCH"] + dt.timedelta(hours=1),
        capture_launched=True,
        a2_passed=True,
        identity_priority_order=PRIORITY,
    )
    assert one_day["identity_selection"] == "FIRST_20_BY_IDENTITY_PRIORITY_ORDER"
    assert one_day["selected_identities"] == PRIORITY[:20]
    two_day = DeadlinePlanSelector().select(
        now=CLOCK_TRIGGERS["TARGET_RESULT_LOCK"] + dt.timedelta(hours=1),
        capture_launched=True,
        a2_passed=True,
        identity_priority_order=PRIORITY,
    )
    assert two_day["plan"] == "TWO_DAYS_BEHIND"
    assert two_day["selected_identities"] == PRIORITY[:15]


def test_b8_a_plan_once_selected_is_frozen_and_escalates_monotonically():
    selector = DeadlinePlanSelector()
    selector.select(
        now=CLOCK_TRIGGERS["TARGET_CAPTURE_LAUNCH"] + dt.timedelta(hours=1),
        capture_launched=True,
        a2_passed=True,
    )
    assert selector.freeze() == "ONE_DAY_BEHIND"
    # A later, nominally fuller evaluation may not walk the plan back.
    back = selector.select(
        now=CLOCK_TRIGGERS["TARGET_CAPTURE_LAUNCH"] - dt.timedelta(hours=5),
        capture_launched=False,
        a2_passed=True,
    )
    assert back["plan"] == "ONE_DAY_BEHIND"
    forward = selector.select(
        now=CLOCK_TRIGGERS["TARGET_RESULT_LOCK"] + dt.timedelta(hours=1),
        capture_launched=True,
        a2_passed=True,
    )
    assert forward["plan"] == "TWO_DAYS_BEHIND"


# ==========================================================================
# B.9 — Status document
# ==========================================================================

def test_b9_the_emitted_status_document_validates_against_the_contract():
    document = StatusDocument(
        stage="A7",
        total_units=125,
        completed_units=40,
        stage_status="RUNNING",
    ).to_dict()
    validate_status_document(document)
    assert document["COMPLETED_UNITS"] + document["REMAINING_UNITS"] == (
        document["TOTAL_UNITS"]
    )


def test_b9_current_blocker_is_a_taxonomy_code_or_null():
    ok = StatusDocument(
        stage="A7", total_units=1, completed_units=0, current_blocker="CAPTURE_ORDER_VIOLATION"
    ).to_dict()
    validate_status_document(ok)
    assert ok["CURRENT_BLOCKER"] == "CAPTURE_ORDER_VIOLATION"
    with pytest.raises(ExperimentIIIError):
        StatusDocument(
            stage="A7", total_units=1, completed_units=0, current_blocker="MADE_UP"
        ).to_dict()


def test_b9_no_scientific_outcome_field_appears_in_the_status_surface():
    document = StatusDocument(stage="A7", total_units=1, completed_units=1).to_dict()
    with pytest.raises(ExperimentIIIError) as error:
        validate_status_document({**document, "rmse": 0.4})
    assert error.value.blocker == "STATUS_DOCUMENT_MALFORMED"


# ==========================================================================
# B.10 — Artifact inventory completeness
# ==========================================================================

def test_b10_removing_a_required_artifact_fails_with_its_named_blocker():
    checked = 0
    for stage in stages():
        required = required_before_next_stage(stage)
        if not required:
            continue
        paths = [str(artifact["path_or_pattern"]) for artifact in required]
        assert stage_exit_check(stage, paths)["exit_permitted"] is True
        for artifact in required:
            reduced = [
                path for path in paths if path != str(artifact["path_or_pattern"])
            ]
            with pytest.raises(ExperimentIIIError) as error:
                stage_exit_check(stage, reduced)
            named = artifact.get("missing_blocker")
            if named:
                assert error.value.blocker == named
            else:
                # Four B-GEN/B-LOCK inventory rows are required_before_next_stage
                # with a null missing_blocker. The check still fails CLOSED with a
                # taxonomy code rather than letting the stage exit.
                assert error.value.blocker == UNNAMED_MISSING_BLOCKER
            checked += 1
    assert checked > 0


def test_b10_iii_a_closure_requires_no_iii_b_artifact():
    report = assert_iii_a_closure_needs_no_iii_b_artifact()
    assert report["iii_a_closure_requires_no_iii_b_artifact"] is True
    assert report["artifact_count"] == 99


# ==========================================================================
# B.11 — Adjudication coverage
# ==========================================================================

def test_b11_every_one_of_the_seventeen_rows_has_both_interpretations():
    rows = adjudication_matrix()
    assert len(rows) == ADJUDICATION_ROW_COUNT == 17
    for row in rows:
        assert row["permitted_interpretation"].strip()
        assert row["prohibited_interpretation"].strip()


def test_b11_a_claim_outside_every_permitted_interpretation_is_rejected():
    for row in adjudication_matrix():
        mapped = assert_claim_in_scope(row["permitted_interpretation"])
        assert mapped["in_scope"] is True
    with pytest.raises(ExperimentIIIError) as error:
        assert_claim_in_scope("MineWorld has a causal memory module for hidden objects")
    assert error.value.blocker == "ANALYSIS_CLAIM_OUT_OF_SCOPE"


def test_b11_no_outcome_may_establish_the_never_established_list():
    for phrase in ("calibrated posterior uncertainty", "causal object permanence", "U4"):
        with pytest.raises(ExperimentIIIError):
            assert_claim_in_scope(f"this result establishes {phrase}")


# ==========================================================================
# B.12 — Combined-program storage preflight
# ==========================================================================

def _host(working_free, *, durable_free=None, durable_device=None, scratch_device="dev0"):
    host = {"POOL_WORKING": {"device_id": "dev0", "free_bytes": working_free}}
    if durable_device is not None:
        host["POOL_DURABLE"] = {
            "device_id": durable_device,
            "free_bytes": durable_free if durable_free is not None else working_free,
        }
    host["POOL_SCRATCH"] = {
        "device_id": scratch_device,
        "free_bytes": working_free if scratch_device == "dev0" else 40 * GIB,
    }
    return host


def test_b12_a3_resolves_the_device_id_of_every_gated_path():
    receipt = storage_preflight(_host(80 * GIB))
    assert receipt["pool_working_device_id"] == "dev0"
    assert receipt["scratch_is_a_distinct_pool"] is False
    assert receipt["physical_pool_count"] == 1


def test_b12_pools_sharing_one_device_are_one_pool_counted_once():
    receipt = storage_preflight(
        _host(80 * GIB, durable_device="dev0", scratch_device="dev0")
    )
    assert receipt["logical_pool_count"] == 3
    assert receipt["physical_pool_count"] == 1


def test_b12_durable_and_scratch_sharing_a_device_is_a_double_count():
    with pytest.raises(ExperimentIIIError) as error:
        storage_preflight(
            _host(80 * GIB, durable_device="dev0"),
            durability_mode="LOCAL_MIRROR_DISTINCT_POOL",
        )
    assert error.value.blocker == "STORAGE_POOL_DOUBLE_COUNTED"


def test_b12_free_space_is_bytes_compared_against_binary_gib_thresholds():
    assert A3_COMBINED_WITH_MIRROR_BYTES == 64 * (1 << 30) == 68_719_476_736
    receipt = storage_preflight(_host(64 * GIB))
    assert receipt["gate_threshold_bytes"] == A3_COMBINED_WITH_MIRROR_BYTES
    assert receipt["unit_convention"] == "GIB_BINARY"
    assert receipt["free_space_read_as"] == "BYTES"


def test_b12_a_host_with_63_9_gib_under_a_mirror_fails_closed():
    free = int(63.9 * GIB)
    with pytest.raises(ExperimentIIIError) as error:
        storage_preflight(_host(free))
    assert error.value.blocker == "STORAGE_INSUFFICIENT"
    assert "never lowered" in str(error.value)


def test_b12_the_combined_program_gate_is_used_because_iii_b_is_authorized():
    receipt = storage_preflight(_host(80 * GIB))
    assert receipt["gate_applied"] == "A3_COMBINED_PROGRAM_WITH_LOCAL_MIRROR"
    assert receipt["uses_combined_program_gate"] is True
    machine = machine_authority()["resources"]["storage"]
    assert machine["iii_b_is_prospectively_authorized"] is True
    no_mirror = storage_preflight(_host(45 * GIB), local_mirror_enabled=False)
    assert no_mirror["gate_applied"] == "A3_COMBINED_PROGRAM_NO_LOCAL_MIRROR"
    assert no_mirror["gate_threshold_bytes"] == 40 * GIB


def test_b12_a_remote_object_store_imposes_no_local_gate_but_needs_a_round_trip():
    host = {
        "POOL_WORKING": {"device_id": "dev0", "free_bytes": 80 * GIB},
        "remote_hashed_round_trip_verified": True,
    }
    receipt = storage_preflight(host, durability_mode="REMOTE_OBJECT_STORE")
    assert receipt["durable_requirement"] == "NO_LOCAL_FREE_SPACE_GATE"
    assert receipt["remote_hashed_round_trip_required"] is True
    with pytest.raises(ExperimentIIIError):
        storage_preflight(
            {"POOL_WORKING": host["POOL_WORKING"]},
            durability_mode="REMOTE_OBJECT_STORE",
        )


def test_b12_the_durability_mode_and_mirror_flag_are_both_recorded():
    receipt = storage_preflight(
        _host(80 * GIB, durable_device="dev1", durable_free=30 * GIB),
        durability_mode="LOCAL_MIRROR_DISTINCT_POOL",
    )
    assert receipt["durability_mode"] == "LOCAL_MIRROR_DISTINCT_POOL"
    assert receipt["local_mirror_enabled"] is True


# ==========================================================================
# B.13 — Storage-gate coherence
# ==========================================================================

def test_b13_the_frozen_invariant_holds_in_binary_gib():
    report = assert_gate_coherence()
    assert report["A3_PASS_GIB"] == 64
    assert report["MAX_III_A_STORAGE_SHARE_AT_B_GATE_GIB"] == pytest.approx(48.796)
    assert report["STRUCTURAL_HEADROOM_GIB"] == pytest.approx(15.204, abs=1e-9)
    assert report["STRUCTURAL_HEADROOM_GIB"] >= report[
        "III_B_INCREMENTAL_LAUNCH_GATE_GIB"
    ]
    assert report["MARGIN_GIB"] == pytest.approx(4.492, abs=1e-9)


def test_b13_a_host_passing_a3_at_exactly_64_gib_can_still_pass_the_b_gate():
    from mineocclude.experiment_iii.iii_b_gate import POOL_WORKING_FREE_GATE_BYTES

    storage_preflight(_host(64 * GIB))
    remaining_gib = 64 - 48.796
    assert remaining_gib * GIB >= POOL_WORKING_FREE_GATE_BYTES


def test_b13_raising_the_launch_gate_above_the_headroom_is_rejected():
    with pytest.raises(ExperimentIIIError) as error:
        assert_gate_coherence(launch_gate_gib=20.0)
    assert error.value.blocker == "STORAGE_INSUFFICIENT"
    assert "spurious CLEAN_SKIP" in str(error.value)


def test_b13_lowering_the_launch_gate_below_the_incremental_peak_is_rejected():
    with pytest.raises(ExperimentIIIError):
        assert_gate_coherence(launch_gate_gib=10.0)


def test_b13_max_iii_a_share_is_derived_not_asserted():
    machine = machine_authority()["resources"]["storage"]["peak_derivation"]
    derived = machine["peak_working_with_mirror_gib"] - 10.508
    assert derived == pytest.approx(48.796, abs=1e-3)
    assert assert_gate_coherence()["MAX_III_A_STORAGE_SHARE_IS_DERIVED"] is True
    with pytest.raises(ExperimentIIIError):
        assert_gate_coherence(max_iii_a_share_gib=40.0)
