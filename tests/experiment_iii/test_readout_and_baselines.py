"""I13 / I14 / I15 — ridge readout, prediction lock, and the baselines.

Covers A.24, A.25, A.27, the alpha-grid and window contracts, and the
oracle-leakage guard.
"""

from __future__ import annotations

import numpy as np
import pytest

from mineocclude.experiment_iii.baselines_motion import (
    CONSTANT_VELOCITY_WINDOW,
    LEGACY_CONSTANT_VELOCITY_WINDOW_NOT_REUSED,
    ORACLE_BASELINES,
    assert_no_oracle_input_in_model_features,
    constant_velocity,
    fit_time_only,
    last_seen,
    predict_time_only,
    time_only_design,
    training_mean,
)
from mineocclude.experiment_iii.baselines_pixel import (
    CHANNELS,
    PIXEL_BASELINE_NAME,
    PIXEL_FEATURE_DIM,
    RESIZE_HEIGHT,
    RESIZE_WIDTH,
    pixel_features,
    resize_area,
)
from mineocclude.experiment_iii.errors import ExperimentIIIError
from mineocclude.experiment_iii.prediction_lock import PredictionCell, PredictionLock
from mineocclude.experiment_iii.readout import (
    ALPHA_GRID,
    LEGACY_ALPHA_GRID_NOT_REUSED,
    AlphaSelection,
    FoldData,
    cross_validated_predictions,
    fit_outer_fold,
    identity_macro_rmse,
    select_alpha,
)


# --------------------------------------------------------------------------
# A.24 — pixel baseline
# --------------------------------------------------------------------------

def test_pixel_baseline_dimension_and_name():
    assert RESIZE_WIDTH * RESIZE_HEIGHT * CHANNELS == PIXEL_FEATURE_DIM == 4_032
    assert (RESIZE_WIDTH, RESIZE_HEIGHT) == (48, 28)
    assert PIXEL_BASELINE_NAME == "linear current-frame pixel baseline"


def test_pixel_features_are_deterministic():
    rng = np.random.default_rng(7)
    frame = rng.integers(0, 256, size=(360, 640, 3), dtype=np.uint8)
    first = pixel_features(frame)
    second = pixel_features(frame)
    assert first.shape == (PIXEL_FEATURE_DIM,)
    assert np.array_equal(first, second)
    assert first.tobytes() == second.tobytes()


def test_area_resize_averages_its_box():
    """A 2x2-block constant image must resize to those constants exactly."""
    frame = np.zeros((RESIZE_HEIGHT * 4, RESIZE_WIDTH * 4, 3), dtype=np.float64)
    for row in range(RESIZE_HEIGHT):
        for col in range(RESIZE_WIDTH):
            frame[row * 4 : (row + 1) * 4, col * 4 : (col + 1) * 4] = row * 100 + col
    resized = resize_area(frame)
    for row in range(RESIZE_HEIGHT):
        for col in range(RESIZE_WIDTH):
            assert resized[row, col, 0] == pytest.approx(row * 100 + col)


def test_uniform_frame_survives_the_resize():
    frame = np.full((360, 640, 3), 42.0)
    assert np.allclose(resize_area(frame), 42.0)


def test_flatten_order_is_stable_and_row_major():
    frame = np.arange(RESIZE_HEIGHT * RESIZE_WIDTH * 3, dtype=np.float64).reshape(
        RESIZE_HEIGHT, RESIZE_WIDTH, 3
    )
    flat = pixel_features(frame)
    assert np.array_equal(flat, frame.reshape(-1))


def test_non_rgb_frame_is_refused():
    with pytest.raises(ExperimentIIIError) as caught:
        pixel_features(np.zeros((360, 640)))
    assert caught.value.blocker == "BASELINE_FORMULA_MISMATCH"


# --------------------------------------------------------------------------
# I14 — motion and clock baselines
# --------------------------------------------------------------------------

def _series(n: int = 40):
    positions = [float(index) * 0.1 - 4.0 for index in range(n)]
    occluded = [index >= 20 for index in range(n)]
    return positions, occluded


def test_last_seen_holds_the_last_preocclusion_position():
    positions, occluded = _series()
    assert last_seen(positions, occluded, 25) == pytest.approx(positions[19])
    assert last_seen(positions, occluded, 39) == pytest.approx(positions[19])


def test_constant_velocity_window_is_exactly_ten():
    assert CONSTANT_VELOCITY_WINDOW == 10
    assert LEGACY_CONSTANT_VELOCITY_WINDOW_NOT_REUSED == 15
    assert CONSTANT_VELOCITY_WINDOW != LEGACY_CONSTANT_VELOCITY_WINDOW_NOT_REUSED


def test_constant_velocity_extrapolates_a_linear_track_exactly():
    positions, occluded = _series()
    predicted = constant_velocity(positions, occluded, 25)
    # The track is exactly linear, so extrapolation must be exact.
    assert predicted == pytest.approx(0.1 * 25 - 4.0, abs=1e-9)


def test_constant_velocity_refuses_a_different_window():
    positions, occluded = _series()
    with pytest.raises(ExperimentIIIError) as caught:
        constant_velocity(positions, occluded, 25, window=15)
    assert caught.value.blocker == "BASELINE_FORMULA_MISMATCH"


def test_constant_velocity_uses_only_the_last_ten():
    positions, occluded = _series()
    perturbed = list(positions)
    # Disturbing a pre-occlusion sample OUTSIDE the last 10 must not change it.
    perturbed[3] = 99.0
    assert constant_velocity(positions, occluded, 25) == pytest.approx(
        constant_velocity(perturbed, occluded, 25)
    )
    # Disturbing one INSIDE the last 10 must change it.
    perturbed2 = list(positions)
    perturbed2[15] = 99.0
    assert constant_velocity(positions, occluded, 25) != pytest.approx(
        constant_velocity(perturbed2, occluded, 25)
    )


def test_training_mean_is_outer_training_only():
    assert training_mean({"a": [1.0, 3.0], "b": [5.0, 7.0]}) == pytest.approx(4.0)


def test_stratified_mean_refuses_when_not_estimable():
    with pytest.raises(ExperimentIIIError) as caught:
        training_mean(
            {"a": [1.0]},
            directions={"a": "LEFT_TO_RIGHT"},
            stratify_by_direction=True,
        )
    assert caught.value.blocker == "BASELINE_MISSING"


def test_time_only_design_is_the_frozen_four_column_form():
    design = time_only_design([1, 2], ["LEFT_TO_RIGHT", "RIGHT_TO_LEFT"])
    assert design.shape == (2, 4)
    assert np.array_equal(design[0], [1.0, 1.0, 1.0, 1.0])
    assert np.array_equal(design[1], [1.0, -1.0, 2.0, -2.0])


def test_time_only_recovers_a_known_linear_law():
    ages = list(range(1, 20)) * 2
    directions = ["LEFT_TO_RIGHT"] * 19 + ["RIGHT_TO_LEFT"] * 19
    truth = np.array([2.0, -0.5, 0.25, 0.125])
    targets = time_only_design(ages, directions) @ truth
    fitted = fit_time_only(ages, directions, targets)
    assert np.allclose(fitted, truth)
    assert np.allclose(predict_time_only(fitted, ages, directions), targets)


def test_oracle_baselines_are_declared_and_refused_as_model_inputs():
    assert ORACLE_BASELINES == {"last_seen", "constant_velocity"}
    assert_no_oracle_input_in_model_features(["coarse_0", "coarse_1"])
    with pytest.raises(ExperimentIIIError) as caught:
        assert_no_oracle_input_in_model_features(["coarse_0", "last_seen"])
    assert caught.value.blocker == "BASELINE_ORACLE_USED_AS_MODEL_INPUT"


# --------------------------------------------------------------------------
# I15 — alpha grid, nested selection, leakage
# --------------------------------------------------------------------------

def test_alpha_grid_has_five_values_and_is_not_the_legacy_four():
    assert ALPHA_GRID == (0.1, 1.0, 10.0, 100.0, 1000.0)
    assert len(ALPHA_GRID) == 5
    assert len(LEGACY_ALPHA_GRID_NOT_REUSED) == 4
    assert ALPHA_GRID != LEGACY_ALPHA_GRID_NOT_REUSED
    assert list(ALPHA_GRID) == sorted(ALPHA_GRID), "ascending, for the tie-break"


def _synthetic(identities, *, rows=19, features=8, seed=0):
    rng = np.random.default_rng(seed)
    truth = rng.standard_normal(features)
    data = {}
    for offset, name in enumerate(identities):
        matrix = rng.standard_normal((rows, features))
        targets = matrix @ truth + rng.standard_normal(rows) * 0.01 + offset * 0.001
        data[name] = FoldData(name, matrix, targets)
    return data


def test_alpha_selection_is_identity_macro_with_smallest_alpha_tie_break():
    identities = [f"e3_t{index:02d}" for index in range(1, 9)]
    data = _synthetic(identities)
    rotations = {0: identities[:2], 1: identities[2:4], 2: identities[4:6], 3: identities[6:]}
    selection = select_alpha(data, rotations)
    assert selection.alpha in ALPHA_GRID
    assert set(selection.scores) == set(ALPHA_GRID)
    assert selection.rotations == 4
    payload = selection.as_dict()
    assert payload["tie_break"] == "SMALLEST_ALPHA"
    assert payload["criterion"] == "IDENTITY_MACRO_INNER_VALIDATION_MEAN_RMSE"


def test_tie_break_prefers_the_smallest_alpha():
    tied = AlphaSelection(alpha=0.1, scores={a: 1.0 for a in ALPHA_GRID}, rotations=4)
    best = min(tied.scores.values())
    assert next(a for a in ALPHA_GRID if tied.scores[a] == best) == 0.1


def test_a_four_value_grid_is_refused():
    identities = [f"e3_t{index:02d}" for index in range(1, 9)]
    data = _synthetic(identities)
    rotations = {0: identities[:2], 1: identities[2:4], 2: identities[4:6], 3: identities[6:]}
    with pytest.raises(ExperimentIIIError) as caught:
        select_alpha(data, rotations, alpha_grid=LEGACY_ALPHA_GRID_NOT_REUSED)
    assert caught.value.blocker == "ANALYSIS_FAMILY_ALTERED"


def test_identity_macro_is_not_row_pooled():
    per_identity = {"a": 1.0, "b": 3.0}
    assert identity_macro_rmse(per_identity) == 2.0


def test_no_identity_appears_in_its_own_training_set():
    identities = [f"e3_t{index:02d}" for index in range(1, 9)]
    data = _synthetic(identities)
    rotations = {0: identities[:2], 1: identities[2:4], 2: identities[4:6], 3: identities[6:]}
    with pytest.raises(ExperimentIIIError) as caught:
        fit_outer_fold(data, {identities[0]: data[identities[0]]}, rotations)
    assert caught.value.blocker == "FOLD_LEAKAGE_DETECTED"


def test_inner_rotation_containing_a_heldout_identity_is_refused():
    identities = [f"e3_t{index:02d}" for index in range(1, 11)]
    data = _synthetic(identities)
    training = {name: data[name] for name in identities[:8]}
    held_out = {name: data[name] for name in identities[8:]}
    leaking = {0: identities[:2], 1: identities[2:4], 2: identities[4:6], 3: [identities[9]]}
    with pytest.raises(ExperimentIIIError) as caught:
        fit_outer_fold(training, held_out, leaking)
    assert caught.value.blocker == "FOLD_LEAKAGE_DETECTED"


def test_cross_validated_predictions_cover_each_identity_exactly_once():
    identities = [f"e3_t{index:02d}" for index in range(1, 11)]
    data = _synthetic(identities)
    folds = []
    for outer in range(5):
        held = identities[outer * 2 : outer * 2 + 2]
        train = [name for name in identities if name not in held]
        folds.append(
            {
                "outer_fold": outer,
                "held_out_identities": held,
                "training_identities": train,
                "inner_rotations": {
                    "0": train[:2],
                    "1": train[2:4],
                    "2": train[4:6],
                    "3": train[6:],
                },
            }
        )
    predictions, selections = cross_validated_predictions(data, folds)
    assert set(predictions) == set(identities)
    assert len(selections) == 5
    for name in identities:
        assert predictions[name].shape == data[name].targets.shape


# --------------------------------------------------------------------------
# A.27 — prediction locking order
# --------------------------------------------------------------------------

def _cells(models=("MW_CURRENT",), identities=("e3_t01",), conditions=("L0", "L1"), rows=2):
    for model in models:
        for identity in identities:
            for condition in conditions:
                for row in range(rows):
                    yield PredictionCell(identity, condition, row, model, 0.5, 0.4)


def test_lock_seals_and_hashes():
    lock = PredictionLock()
    lock.extend(_cells())
    digest = lock.seal()
    assert lock.sealed is True
    assert digest == lock.sealed_hash
    assert len(digest) == 64


def test_duplicate_cell_is_refused():
    lock = PredictionLock()
    cell = PredictionCell("e3_t01", "L0", 0, "MW_CURRENT", 0.1, 0.2)
    lock.add(cell)
    with pytest.raises(ExperimentIIIError) as caught:
        lock.add(cell)
    assert caught.value.blocker == "PREDICTION_DUPLICATE_CELL"


def test_statistics_before_the_lock_are_refused():
    lock = PredictionLock()
    lock.extend(_cells())
    with pytest.raises(ExperimentIIIError) as caught:
        lock.require_sealed("the primary estimand")
    assert caught.value.blocker == "PREDICTION_LOCK_MISSING"


def test_sealing_after_statistics_are_opened_is_refused():
    lock = PredictionLock()
    lock.extend(_cells())
    lock.statistics_opened = True
    with pytest.raises(ExperimentIIIError) as caught:
        lock.seal()
    assert caught.value.blocker == "PREDICTION_LOCK_AFTER_STATISTICS"


def test_post_lock_modification_is_detected():
    lock = PredictionLock()
    lock.extend(_cells())
    lock.seal()
    lock.verify_unmodified()
    lock._cells[("e3_t01", "L0", 0, "MW_CURRENT")] = PredictionCell(
        "e3_t01", "L0", 0, "MW_CURRENT", 9.9, 0.4
    )
    with pytest.raises(ExperimentIIIError) as caught:
        lock.verify_unmodified()
    assert caught.value.blocker == "PREDICTION_LOCK_AFTER_STATISTICS"


def test_feature_block_cannot_be_rebound_after_sealing():
    lock = PredictionLock()
    lock.note_feature_block("L19_CURRENT", "a" * 64)
    lock.extend(_cells())
    lock.seal()
    with pytest.raises(ExperimentIIIError) as caught:
        lock.note_feature_block("L19_CURRENT", "b" * 64)
    assert caught.value.blocker == "PREDICTION_LOCK_AFTER_STATISTICS"


def test_completeness_detects_a_missing_cell():
    lock = PredictionLock()
    cells = list(_cells())
    lock.extend(cells[:-1])
    with pytest.raises(ExperimentIIIError) as caught:
        lock.assert_complete(
            identities=["e3_t01"], conditions=["L0", "L1"], rows=2, models=["MW_CURRENT"]
        )
    assert caught.value.blocker == "PREDICTION_LOCK_MISSING"


def test_completeness_accepts_exactly_one_prediction_per_cell():
    lock = PredictionLock()
    lock.extend(_cells())
    lock.assert_complete(
        identities=["e3_t01"], conditions=["L0", "L1"], rows=2, models=["MW_CURRENT"]
    )
    assert len(lock) == 4


def test_lock_refuses_a_nonfinite_prediction():
    lock = PredictionLock()
    with pytest.raises(ExperimentIIIError) as caught:
        lock.add(PredictionCell("e3_t01", "L0", 0, "MW_CURRENT", float("nan"), 0.1))
    assert caught.value.blocker == "PREDICTION_NONFINITE"
