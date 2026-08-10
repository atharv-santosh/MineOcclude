"""Focused validation for replicated visible-position Task 4 outputs."""

from __future__ import annotations

import hashlib
import json
import statistics
import subprocess
from collections import Counter
from pathlib import Path

import pytest

from scripts.run_visible_position_resolution_task4 import (
    FROZEN_FILE_HASHES,
    MVP_MANIFEST,
    MVP_SHA256,
    PREDECESSOR_MANIFEST,
    PREDECESSOR_SHA256,
    fold_metrics,
)

ROOT = Path(__file__).resolve().parents[2]
OUTPUT_ROOT = (
    ROOT / "docs/status/integration/exploratory_visible_position_resolution_v0_1"
)
WITHIN_PATH = OUTPUT_ROOT / "within_layout_replication.json"
ACROSS_PATH = OUTPUT_ROOT / "across_layout_generalization.json"
REPRESENTATIONS = ("GLOBAL_MEAN", "COARSE_2x6", "FULL_TOKEN_GRID")


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture(scope="module")
def reports() -> tuple[dict, dict]:
    return _load(WITHIN_PATH), _load(ACROSS_PATH)


def test_combined_authority_is_exact_balanced_no_wall_scope(reports) -> None:
    within, across = reports
    for report in (within, across):
        authority = report["combined_authority"]
        assert authority["status"] == "PASS"
        assert authority["trajectory_count"] == 18
        assert authority["eligible_row_count"] == 1071
        assert authority["trajectory_count_by_layout"] == {
            f"layout_{index:02d}": 3 for index in range(1, 7)
        }
        assert authority["eligible_rows_by_layout"] == {
            "layout_01": 180,
            "layout_02": 180,
            "layout_03": 180,
            "layout_04": 180,
            "layout_05": 180,
            "layout_06": 171,
        }
        assert authority["wall_condition_trajectory_count"] == 0
        assert authority["condition_identity"]["status"] == "PASS"
        assert authority["condition_identity"]["wall_present"] is False
        assert authority["duplicate_row_count"] == 0
        assert authority["trajectory_collision_count"] == 0


def test_combined_semantics_match_across_reports(reports) -> None:
    within, across = reports
    left = within["combined_authority"]
    right = across["combined_authority"]
    assert left == right
    assert left["activation_identity"] == {
        "hidden_width": 2048,
        "layer": 4,
        "layer_count": 1,
        "status": "PASS",
        "token_count": 336,
        "token_dtype": "float16",
        "token_grid": [14, 24],
    }
    assert left["target_semantics"]["status"] == "PASS"
    assert left["visibility_semantics"]["status"] == "PASS"
    assert left["context_semantics"]["teacher_forcing"] is True
    assert left["context_semantics"]["window_size"] == 16


def test_representation_set_and_row_authority_are_identical(reports) -> None:
    within, across = reports
    for report in (within, across):
        assert set(report["representations"]) == set(REPRESENTATIONS)
        assert set(report["representation_definitions"]) == set(REPRESENTATIONS)
        assert (
            report["representation_definitions"]["GLOBAL_MEAN"]["feature_count"] == 2048
        )
        assert (
            report["representation_definitions"]["COARSE_2x6"]["feature_count"] == 24576
        )
        assert (
            report["representation_definitions"]["FULL_TOKEN_GRID"]["feature_count"]
            == 688128
        )
        row_keys_by_representation = {
            representation: [
                prediction["row_key"]
                for fold in report["representations"][representation]["folds"]
                for prediction in fold["predictions"]
            ]
            for representation in REPRESENTATIONS
        }
        assert len({tuple(keys) for keys in row_keys_by_representation.values()}) == 1
        assert len(next(iter(row_keys_by_representation.values()))) == 1071


def test_within_has_exactly_eighteen_outer_trajectory_folds(reports) -> None:
    within, _ = reports
    assert within["outer_design"]["outer_fold_count"] == 18
    fold_ids = {
        representation: [
            fold["fold_id"]
            for fold in within["representations"][representation]["folds"]
        ]
        for representation in REPRESENTATIONS
    }
    assert len({tuple(ids) for ids in fold_ids.values()}) == 1
    assert len(set(fold_ids["GLOBAL_MEAN"])) == 18
    assert Counter(
        fold["held_out_layout"]
        for fold in within["representations"]["GLOBAL_MEAN"]["folds"]
    ) == Counter({f"layout_{index:02d}": 3 for index in range(1, 7)})


def test_within_outer_and_inner_trajectory_leakage_is_absent(reports) -> None:
    within, _ = reports
    for representation in REPRESENTATIONS:
        for fold in within["representations"][representation]["folds"]:
            held_out = set(fold["held_out_trajectories"])
            training = set(fold["training_group_ids"])
            assert len(held_out) == 1
            assert len(training) == 2
            assert held_out.isdisjoint(training)
            assert fold["outer_scaler_training_row_count"] == fold["train_row_count"]
            assert len(fold["inner_folds"]) == 2
            for inner in fold["inner_folds"]:
                inner_train = set(inner["training_group_ids"])
                validation = set(inner["validation_group_ids"])
                assert len(inner_train) == len(validation) == 1
                assert inner_train.isdisjoint(validation)
                assert inner_train | validation == training
                assert held_out.isdisjoint(inner_train | validation)
                assert inner["scaler_training_row_count"] == inner["train_row_count"]


def test_across_has_exactly_six_complete_held_out_layout_folds(reports) -> None:
    _, across = reports
    assert across["outer_design"]["outer_fold_count"] == 6
    for representation in REPRESENTATIONS:
        folds = across["representations"][representation]["folds"]
        assert len(folds) == 6
        assert {fold["held_out_layout"] for fold in folds} == {
            f"layout_{index:02d}" for index in range(1, 7)
        }
        assert all(len(fold["held_out_trajectories"]) == 3 for fold in folds)


def test_across_outer_and_inner_layout_leakage_is_absent(reports) -> None:
    _, across = reports
    for representation in REPRESENTATIONS:
        for fold in across["representations"][representation]["folds"]:
            held_out = fold["held_out_layout"]
            training = set(fold["training_group_ids"])
            assert len(training) == 5
            assert held_out not in training
            assert fold["outer_scaler_training_row_count"] == fold["train_row_count"]
            assert len(fold["inner_folds"]) == 5
            for inner in fold["inner_folds"]:
                inner_train = set(inner["training_group_ids"])
                validation = set(inner["validation_group_ids"])
                assert len(inner_train) == 4
                assert len(validation) == 1
                assert inner_train.isdisjoint(validation)
                assert inner_train | validation == training
                assert held_out not in inner_train | validation
                assert inner["scaler_training_row_count"] == inner["train_row_count"]


def test_representation_deltas_are_recomputed_from_matching_folds(reports) -> None:
    within, across = reports
    for report in (within, across):
        baseline = {
            fold["fold_id"]: fold
            for fold in report["representations"]["GLOBAL_MEAN"]["folds"]
        }
        for representation in ("COARSE_2x6", "FULL_TOKEN_GRID"):
            for fold in report["representations"][representation]["folds"]:
                reference = baseline[fold["fold_id"]]
                delta = fold["representation_minus_global"]
                assert delta["delta_r2"] == pytest.approx(
                    fold["metrics"]["r2"] - reference["metrics"]["r2"]
                )
                assert delta["delta_mae"] == pytest.approx(
                    fold["metrics"]["mae"] - reference["metrics"]["mae"]
                )


def test_fold_and_per_trajectory_metrics_derive_from_stored_predictions(
    reports,
) -> None:
    import numpy as np

    within, across = reports
    for report in (within, across):
        for representation in REPRESENTATIONS:
            for fold in report["representations"][representation]["folds"]:
                predictions = fold["predictions"]
                recomputed = fold_metrics(
                    np.asarray([row["truth"] for row in predictions]),
                    np.asarray([row["prediction"] for row in predictions]),
                )
                for field, value in recomputed.items():
                    if value is None:
                        assert fold["metrics"][field] is None
                    else:
                        assert fold["metrics"][field] == pytest.approx(value)
                if report is across:
                    for trajectory_id, expected in fold[
                        "per_trajectory_metrics"
                    ].items():
                        selected = [
                            row
                            for row in predictions
                            if row["trajectory_id"] == trajectory_id
                        ]
                        actual = fold_metrics(
                            np.asarray([row["truth"] for row in selected]),
                            np.asarray([row["prediction"] for row in selected]),
                        )
                        for field, value in actual.items():
                            if value is None:
                                assert expected[field] is None
                            else:
                                assert expected[field] == pytest.approx(value)


def test_equal_layout_and_equal_trajectory_macros_are_unweighted(reports) -> None:
    within, across = reports
    for representation in REPRESENTATIONS:
        summary = within["representations"][representation]["summary"]
        layout_means = [
            record["trajectory_mean_r2"] for record in summary["per_layout"].values()
        ]
        layout_medians = [
            record["trajectory_median_r2"] for record in summary["per_layout"].values()
        ]
        assert summary["equal_layout_macro_mean_r2"] == pytest.approx(
            statistics.mean(layout_means)
        )
        assert summary["equal_layout_macro_median_r2"] == pytest.approx(
            statistics.median(layout_medians)
        )
        across_folds = across["representations"][representation]["folds"]
        assert across["representations"][representation]["summary"][
            "equal_layout_macro_metrics"
        ]["r2"]["mean"] == pytest.approx(
            statistics.mean(fold["metrics"]["r2"] for fold in across_folds)
        )


def test_full_optimization_equivalence_is_preserved_without_refit(reports) -> None:
    within, across = reports
    assert within["optimization_equivalence"] == across["optimization_equivalence"]
    evidence = across["optimization_equivalence"]
    assert evidence["status"] == "PASS"
    full = next(
        check
        for check in evidence["checks"]
        if check["check"] == "representative_within_full"
    )
    assert full["feature_count"] == 688128
    assert full["maximum_absolute_prediction_difference"] == pytest.approx(
        3.4217251254631265e-10
    )
    assert full["maximum_absolute_prediction_difference"] < evidence["atol"]


def test_corrected_hierarchy_uses_separate_trajectory_and_layout_evidence(
    reports,
) -> None:
    _, across = reports
    hierarchy = across["hierarchical_comparison"]
    assert hierarchy["trajectory_variance_class"] == "MIXED_TRAJECTORY_EFFECT"
    assert hierarchy["layout_variance_class"] == ("BOTH_TRAJECTORY_AND_LAYOUT_VARIANCE")
    assert hierarchy["both_trajectory_and_layout_variance"] is True
    assert hierarchy["coarse_vs_full_stability"][
        "layouts_with_complementary_strong_magnitude_heterogeneity"
    ] == ["layout_04"]
    for representation in ("COARSE_2x6", "FULL_TOKEN_GRID"):
        record = hierarchy["representations"][representation]
        assert record["across_layout_delta_sign_count"]["r2"] == {
            "negative": 3,
            "positive": 3,
            "zero": 0,
        }
        assert "across_layout_delta_spread" in record
        assert "within_layout_trajectory_spread" in record


def test_coarse_and_full_evidence_remain_separate(reports) -> None:
    within, across = reports
    coarse = within["representations"]["COARSE_2x6"]["summary"]
    full = within["representations"]["FULL_TOKEN_GRID"]["summary"]
    assert coarse["trajectories_beating_global"] == 18
    assert full["trajectories_beating_global"] == 18
    assert coarse["layouts_with_positive_median_delta"] == 6
    assert full["layouts_with_positive_median_delta"] == 6
    assert (
        across["representations"]["COARSE_2x6"]["summary"]["per_layout_delta_r2"]
        != across["representations"]["FULL_TOKEN_GRID"]["summary"][
            "per_layout_delta_r2"
        ]
    )


def test_no_controls_or_confirmatory_relabeling_occurred(reports) -> None:
    within, across = reports
    for report in (within, across):
        assert report["controls_run"] == []
        assert report["layer_selection_status"] == (
            "EXPLORATORY_PRESELECTED_FROM_EXISTING_POSITIVE_CONTROL"
        )
        assert all("exploratory" in item.lower() for item in report["limitations"][:2])


def test_cross_report_hash_binding_and_runner_identity(reports) -> None:
    within, across = reports
    runner = ROOT / within["runner"]["path"]
    assert _sha256(runner) == within["runner"]["sha256"]
    assert within["runner"] == across["runner"]
    assert across["within_layout_replication"]["sha256"] == _sha256(WITHIN_PATH)
    assert across["within_layout_replication"]["path"] == str(
        WITHIN_PATH.relative_to(ROOT)
    )


def test_task_1_2_3_freeze_predecessor_and_mvp_are_unchanged() -> None:
    for name, expected in FROZEN_FILE_HASHES.items():
        assert _sha256(OUTPUT_ROOT / name) == expected
    assert _sha256(PREDECESSOR_MANIFEST) == PREDECESSOR_SHA256
    assert _sha256(MVP_MANIFEST) == MVP_SHA256


def test_feature_caches_are_external_and_untracked(reports) -> None:
    _, across = reports
    cache = across["runtime"]["feature_cache"]
    assert cache["large_tensors_in_git"] is False
    assert cache["global_pooling_equivalence"] == "PASS"
    tracked = set(
        subprocess.run(
            ["git", "ls-files"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.splitlines()
    )
    for record in cache["caches"].values():
        path = Path(record["path"])
        assert path.is_file()
        assert not path.is_relative_to(ROOT)
        assert (
            str(path.relative_to(ROOT)) not in tracked
            if path.is_relative_to(ROOT)
            else True
        )
