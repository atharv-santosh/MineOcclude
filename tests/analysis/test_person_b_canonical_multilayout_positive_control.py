from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/run_person_b_canonical_multilayout_positive_control.py"
SPEC = importlib.util.spec_from_file_location(
    "run_person_b_canonical_multilayout_positive_control", SCRIPT
)
assert SPEC is not None and SPEC.loader is not None
runner = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = runner
SPEC.loader.exec_module(runner)


def test_frozen_successor_identities_and_settings_are_exact() -> None:
    assert runner.TRAJECTORIES == (
        "layout_01_ep12602",
        "layout_02_ep12610",
        "layout_03_ep12645",
        "layout_04_ep12626",
        "layout_05_ep12634",
    )
    assert runner.LAYOUTS == (
        "layout_01",
        "layout_02",
        "layout_03",
        "layout_04",
        "layout_05",
    )
    assert runner.ALPHA_GRID == (0.1, 1.0, 10.0, 100.0)
    assert runner.OUTER_FOLD_COUNT == 5
    assert runner.INNER_FOLD_COUNT == 4
    assert runner.SPLIT_SEED == 20260719
    assert runner.PERMUTATION_COUNT == 999
    assert runner.PERMUTATION_SEED == 20260720


def test_frozen_human_review_rule_selects_strongest_qualified_layer() -> None:
    def row(layer: int, r2: float, global_r: float, fold_values: list[float]):
        return {
            "global": {"r2": r2, "pearson_r": global_r},
            "layer_idx": layer,
            "per_fold": [{"pearson_r": value} for value in fold_values],
        }

    results = [
        row(1, 0.2, 0.4, [0.1] * 5),
        row(2, 0.4, 0.5, [0.2] * 5),
        row(3, 0.8, 0.9, [0.4, 0.4, -0.1, 0.4, 0.4]),
    ]

    assert runner._review_real_metrics(results)["layer_idx"] == 2
    assert runner._review_real_metrics([results[2]]) is None


def test_frozen_grouped_folds_cover_one_layout_each() -> None:
    metadata = [
        {
            "layout_id": layout,
            "model_frame_idx": frame,
            "status": "accepted",
            "trajectory_id": trajectory,
        }
        for layout, trajectory in zip(runner.LAYOUTS, runner.TRAJECTORIES)
        for frame in range(60)
    ]

    assignments = runner.assign_layout_grouped_folds(
        metadata,
        n_splits=runner.OUTER_FOLD_COUNT,
        seed=runner.SPLIT_SEED,
    )

    assert assignments == {
        "layout_01": 1,
        "layout_02": 0,
        "layout_03": 4,
        "layout_04": 3,
        "layout_05": 2,
    }


def test_completed_control_results_preserve_single_execution() -> None:
    path = (
        ROOT
        / "docs/status/person_b_canonical_multilayout_positive_control_v0_1/"
        "completed_control_results.json"
    )

    document = runner._load_completed_control_results(path)

    assert document["adaptive_rerun_performed"] is False
    assert document["execution_semantics"]["real_label_execution_count"] == 1
    assert document["execution_semantics"]["shuffled_execution_count"] == 1
    assert document["shuffled_control"]["metrics"]["p_value"] == 0.24


def test_committed_successor_receipt_is_valid() -> None:
    path = (
        ROOT
        / "docs/status/person_b_canonical_multilayout_positive_control_v0_1/"
        "b_to_a_successor_receipt.json"
    )
    document = json.loads(path.read_text(encoding="utf-8"))

    runner.validate_receipt(document)
    assert document["decision"]["positive_control_pass"] is True
    assert document["source_identity_join"]["identity_error_count"] == 0
