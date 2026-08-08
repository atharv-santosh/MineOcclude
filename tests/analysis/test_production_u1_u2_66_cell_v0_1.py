"""Focused checks for the real 66-cell U1/U2 production runner."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from mineocclude.analysis.production_u1_u2_66_cell_v0_1 import (
    BOOTSTRAP_COUNT,
    HIDDEN_FRAME_COUNT,
    LAYERS,
    PERMUTATION_COUNT,
    ProductionAnalysisError,
    ProductionPaths,
    _calibration_summary,
    _hierarchical_partial_bootstrap,
    _paired_comparison,
    publish_results,
    validate_result_package,
)
from mineocclude.analysis.step4_1_final_comparison_v0_1 import (
    shared_sign_flip_max_t,
)
from mineocclude.probes.ridge import fit_ridge_oof

METADATA_DTYPE = np.dtype(
    [
        ("trajectory_id", "U32"),
        ("global_model_frame_idx", "i4"),
        ("layout_id", "U16"),
        ("fold_idx", "i2"),
    ]
)


def _hierarchical_fixture() -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    rows = []
    decoded = []
    oracle = []
    tau = []
    folds = (3, 2, 4, 4, 1, 0)
    for layout_index in range(6):
        for trajectory_index in range(3):
            for frame in range(5):
                clock = 0.1 * (frame + 1)
                spread = 1.0 + clock * clock + 0.2 * trajectory_index
                rows.append(
                    (
                        f"layout_{layout_index + 1:02d}_ep{trajectory_index}",
                        frame,
                        f"layout_{layout_index + 1:02d}",
                        folds[layout_index],
                    )
                )
                oracle.append(spread)
                decoded.append(2.0 * spread + 0.3 * clock)
                tau.append(clock)
    return (
        np.asarray(decoded),
        np.asarray(oracle),
        np.asarray(tau),
        np.asarray(rows, dtype=METADATA_DTYPE),
    )


def test_frozen_ridge_is_grouped_and_out_of_fold() -> None:
    rows = []
    features = []
    targets = []
    folds = (3, 2, 4, 4, 1, 0)
    for layout_index in range(6):
        for frame in range(6):
            value = layout_index + frame / 10.0
            rows.append((f"layout_{layout_index:02d}", folds[layout_index]))
            features.append([value, value * value])
            targets.append(1.5 * value - 0.2)
    result = fit_ridge_oof(
        features,
        targets,
        [fold for _, fold in rows],
        [layout for layout, _ in rows],
    )
    assert len(result.predictions) == len(rows)
    assert np.isfinite(result.predictions).all()
    assert {fit.outer_fold_idx for fit in result.fits} == set(range(5))
    for fit in result.fits:
        assert set(fit.training_indices).isdisjoint(fit.test_indices)
        assert set(fit.training_indices) | set(fit.test_indices) == set(
            range(len(rows))
        )
        assert all(rows[index][1] == fit.outer_fold_idx for index in fit.test_indices)


def test_shared_layout_permutation_is_frozen_and_deterministic() -> None:
    hypotheses = {
        f"u1:test_{index:02d}": {
            f"layout_{layout + 1:02d}": 0.5 + index / 100.0 + layout / 20.0
            for layout in range(6)
        }
        for index in range(40)
    }
    first = shared_sign_flip_max_t(hypotheses)
    second = shared_sign_flip_max_t(hypotheses)
    assert first == second
    assert len(first) == 40
    assert all(
        1.0 / (PERMUTATION_COUNT + 1) <= row["max_t_adjusted_p_value"] <= 1.0
        for row in first.values()
    )


def test_hierarchical_partial_bootstrap_is_layout_then_trajectory() -> None:
    decoded, oracle, tau, metadata = _hierarchical_fixture()
    first = _hierarchical_partial_bootstrap(decoded, oracle, tau, metadata)
    second = _hierarchical_partial_bootstrap(decoded, oracle, tau, metadata)
    assert first == second
    assert BOOTSTRAP_COUNT == 2000
    assert first[0] > 0.99
    assert first[1] <= 1.0
    assert first[2] + first[3] == BOOTSTRAP_COUNT


def test_u2_calibration_uses_frozen_50_80_95_intervals() -> None:
    _, _, _, metadata = _hierarchical_fixture()
    truth = np.linspace(-1.0, 1.0, len(metadata))
    summary = _calibration_summary(
        truth,
        truth,
        np.full(len(metadata), 0.1),
        metadata,
    )
    assert summary["nominal_coverage"] == [0.5, 0.8, 0.95]
    assert summary["layout_macro_observed_coverage"] == {
        "0.5": 1.0,
        "0.8": 1.0,
        "0.95": 1.0,
    }
    assert summary["expected_calibration_error"] == pytest.approx(0.25)


def test_person_d_comparison_consumes_only_applicable_exact_rows() -> None:
    rows = []
    d_rows = {}
    truth = []
    prediction = []
    for layout in range(6):
        for trajectory in range(2):
            for frame in range(2):
                trajectory_id = f"layout_{layout + 1:02d}_ep{trajectory}"
                rows.append(
                    (trajectory_id, frame, f"layout_{layout + 1:02d}", layout % 5)
                )
                value = float(layout + trajectory + frame)
                truth.append(value)
                prediction.append(value)
                applicable = not (layout == 0 and trajectory == 0 and frame == 0)
                d_rows[("last_seen", "mu_oracle_blocks", trajectory_id, frame)] = {
                    "applicable": applicable,
                    "prediction": value + 1.0 if applicable else None,
                }
    metadata = np.asarray(rows, dtype=METADATA_DTYPE)
    comparison, layouts = _paired_comparison(
        family="last_seen",
        target="mu_oracle_blocks",
        truth=np.asarray(truth),
        prediction=np.asarray(prediction),
        metadata=metadata,
        d_rows=d_rows,
    )
    assert comparison["applicable_intersection_count"] == len(rows) - 1
    assert comparison["beats_baseline"] is True
    assert comparison["paired_layout_macro_loss_improvement"] == pytest.approx(1.0)
    assert len(layouts) == 6


def _synthetic_publication_payload() -> tuple[dict, dict, dict[str, np.ndarray]]:
    u1_layers = []
    u2_layers = []
    for layer in LAYERS:
        u1_layers.append(
            {
                "baseline_comparisons": [
                    {"baseline_family": "last_seen", "beats_baseline": True},
                    {
                        "baseline_family": "grouped_shuffled",
                        "permutation": {"max_t_adjusted_p_value": 0.02},
                    },
                ],
                "gate": {"qualifies_layer": False, "p_gate": False},
                "layer_idx": layer,
                "layout_macro": {"mae": 0.1, "r2": 0.2 + layer / 100.0},
            }
        )
        u2_layers.append(
            {
                "association": {
                    "layout_macro_partial_correlation_controlling_tau": 0.1
                    + layer / 100.0
                },
                "baseline_comparisons": [
                    {
                        "baseline_family": "time_only",
                        "calibration": {"expected_calibration_error": 0.2},
                    },
                    {
                        "baseline_family": "visible_history_q",
                        "calibration": {"expected_calibration_error": 0.2},
                    },
                ],
                "bootstrap": {"ci_high": 0.3, "ci_low": 0.01},
                "calibration": {
                    "layout_macro_observed_coverage": {
                        "0.5": 0.5,
                        "0.8": 0.8,
                        "0.95": 0.95,
                    }
                },
                "gate": {
                    "calibration_ece_at_most_0_10": True,
                    "coverage_error_better_than_time_only": True,
                    "coverage_error_better_than_visible_history_q": True,
                    "qualifies_layer": True,
                },
                "layer_idx": layer,
            }
        )
    scientific = {
        "provenance": {"source_commit": "a" * 40},
        "schema_id": "mineocclude-66-cell-production-u1-u2-results-v0-1",
        "u1": {
            "best_layer": 19,
            "layer_results": u1_layers,
            "qualifying_contiguous_bands": [],
            "verdict": "FAIL",
        },
        "u2": {
            "best_layer": 19,
            "layer_results": u2_layers,
            "qualifying_contiguous_bands": [list(LAYERS)],
            "verdict": "PASS",
        },
        "u3": {
            "blocker": "NO_VALID_TERMINAL_REVEAL_EVENTS",
            "status": "BLOCKED_NOT_EVALUATED",
        },
    }
    fits = {
        "fitted_probe_count": 40,
        "records": [{"fit": index} for index in range(40)],
        "schema_id": "mineocclude-66-cell-production-u1-u2-fit-provenance-v0-1",
    }
    arrays = {
        "fold_idx": np.zeros(HIDDEN_FRAME_COUNT, dtype=np.int16),
        "global_model_frame_idx": np.arange(HIDDEN_FRAME_COUNT, dtype=np.int32),
        "layer_idx": np.asarray(LAYERS, dtype=np.int16),
        "layout_id": np.asarray(["layout_01"] * HIDDEN_FRAME_COUNT),
        "trajectory_id": np.asarray(["trajectory_01"] * HIDDEN_FRAME_COUNT),
        "u1_mu_oof_prediction": np.zeros((20, HIDDEN_FRAME_COUNT)),
        "u2_log_sigma_oof_prediction": np.zeros((20, HIDDEN_FRAME_COUNT)),
    }
    return scientific, fits, arrays


def test_result_publication_is_sha_bound_and_validated(tmp_path: Path) -> None:
    scientific, fits, arrays = _synthetic_publication_payload()
    git_root = tmp_path / "git-results"
    external_root = tmp_path / "external-results"
    publish_results(
        ProductionPaths(tmp_path, tmp_path, external_root, git_root),
        scientific,
        fits,
        arrays,
    )
    validate_result_package(git_root, external_root)
    result_path = git_root / "scientific_results.json"
    document = json.loads(result_path.read_text())
    document["u3"]["status"] = "PASS"
    result_path.write_text(json.dumps(document))
    with pytest.raises(ProductionAnalysisError, match="inventory"):
        validate_result_package(git_root, external_root)
