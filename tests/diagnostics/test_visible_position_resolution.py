from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNNER_PATH = ROOT / "scripts/run_exploratory_visible_position_resolution.py"
SPEC = importlib.util.spec_from_file_location(
    "visible_position_resolution", RUNNER_PATH
)
assert SPEC is not None and SPEC.loader is not None
resolution = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = resolution
SPEC.loader.exec_module(resolution)

PACKAGE = ROOT / "docs/status/integration/exploratory_visible_position_resolution_v0_1"


def _package(name: str):
    path = PACKAGE / name
    assert path.is_file(), f"missing Task-1 artifact: {path}"
    return json.loads(path.read_text(encoding="utf-8"))


def test_exact_66_accepted_trajectories_are_accounted_for_once() -> None:
    inventory = _package("replication_inventory.json")
    trajectories = inventory["trajectories"]
    trajectory_ids = [row["trajectory_id"] for row in trajectories]
    assert inventory["counts"]["accepted_trajectory_count"] == 66
    assert len(trajectories) == len(trajectory_ids) == 66
    assert len(set(trajectory_ids)) == 66
    assert all(row["accepted_trajectory_status"] == "PASS" for row in trajectories)
    assert sum(row["frame_count"] for row in trajectories) == 2468


def test_eligibility_is_deterministic_complete_and_matches_committed_output() -> None:
    first = resolution.build_resolution_documents()
    second = resolution.build_resolution_documents()
    assert first == second
    assert first[0] == _package("replication_inventory.json")
    assert first[1] == _package("expanded_visibility_eligibility.json")
    assert first[2] == _package("replication_authority_decision.json")

    eligibility = first[1]
    rows = eligibility["eligible_row_identities"]
    excluded = eligibility["excluded_rows"]
    assert eligibility["deterministic_eligibility_rule"]["all_satisfying_rows_included"]
    assert len(rows) == eligibility["counts"]["eligible_row_count"] == 1413
    assert len(excluded) == eligibility["counts"]["excluded_row_count"] == 1055
    assert len(rows) + len(excluded) == 2468
    assert len({row["row_key"] for row in rows}) == len(rows)
    assert len({row["row_key"] for row in excluded}) == len(excluded)
    assert not ({row["row_key"] for row in rows} & {row["row_key"] for row in excluded})
    assert all(len(row["frozen_row_sha256"]) == 64 for row in rows)


def test_eligibility_sources_do_not_include_decoding_result_artifacts() -> None:
    eligibility = _package("expanded_visibility_eligibility.json")
    source_paths = {
        source["path"] for source in eligibility["source_authorities"].values()
    }
    disallowed_names = {
        "diagnostic_adjudication.json",
        "diagnostic_receipt.json",
        "learning_curve.json",
        "learning_curve_subsets.json",
        "token_probe_metrics.json",
        "token_spatial_map.json",
    }
    assert not ({Path(path).name for path in source_paths} & disallowed_names)
    rule_text = json.dumps(
        eligibility["deterministic_eligibility_rule"], sort_keys=True
    ).lower()
    assert "r2" not in rule_text
    assert "mae" not in rule_text
    assert "prediction" not in rule_text


def test_compatibility_strata_and_threshold_semantics_are_deterministic() -> None:
    eligibility = _package("expanded_visibility_eligibility.json")
    strata = eligibility["stratum_identities"]
    assert len(strata) == 60
    assert len({row["stratum_id"] for row in strata}) == 60
    assert all(
        row["stratum_id"]
        == f"visible-compat-v0.1:{resolution._canonical_sha256(row['compatibility_basis'])}"
        for row in strata
    )
    assert all(row["compatible_eligible_trajectory_count"] < 2 for row in strata)
    assert resolution.classify_replication_count(3) == resolution.CLASS_GE3
    assert resolution.classify_replication_count(7) == resolution.CLASS_GE3
    assert resolution.classify_replication_count(2) == resolution.CLASS_EQ2
    assert resolution.classify_replication_count(1) == resolution.CLASS_LT2
    assert resolution.classify_replication_count(0) == resolution.CLASS_LT2


def test_condition_shifts_are_kept_out_of_no_wall_replication_counts() -> None:
    inventory = _package("replication_inventory.json")
    eligibility = _package("expanded_visibility_eligibility.json")
    decision = _package("replication_authority_decision.json")
    shift_ids = set(decision["condition_shift_trajectories_kept_separate"])
    assert len(shift_ids) == 53
    shift_rows = [
        row for row in inventory["trajectories"] if row["trajectory_id"] in shift_ids
    ]
    assert all(
        row["replication_classification"] == resolution.CLASS_SHIFT
        for row in shift_rows
    )
    assert all(row["visibility_regime"]["wall_present"] is True for row in shift_rows)

    no_wall_strata = [
        row
        for row in eligibility["stratum_identities"]
        if row["compatibility_basis"]["trajectory_category"]["value"]
        == resolution.NO_WALL_CONTROL
    ]
    assert len(no_wall_strata) == 6
    assert all(
        row["compatible_eligible_trajectory_count"] == 1 for row in no_wall_strata
    )
    assert not any(
        shift_ids & set(row["compatible_eligible_trajectory_ids"])
        for row in no_wall_strata
    )


def test_classifications_and_primary_path_follow_authority_structure() -> None:
    inventory = _package("replication_inventory.json")
    decision = _package("replication_authority_decision.json")
    assert inventory["classification_counts"] == {
        resolution.CLASS_SHIFT: 53,
        resolution.CLASS_INVALID: 6,
        resolution.CLASS_LT2: 7,
    }
    assert decision["compatible_strata_counts"] == {"EQ2": 0, "GE3": 0, "LT2": 60}
    assert decision["PRIMARY_PATH"] == "BALANCED_NEW_CAPTURE"
    assert decision["new_capture_required"] is True
    assert decision["exact_trajectories_proposed_for_expanded_extraction"] == []
    assert decision["selection_uses_decoder_results"] is False


def test_context_preprocessing_checkpoint_and_segments_are_complete() -> None:
    inventory = _package("replication_inventory.json")
    for row in inventory["trajectories"]:
        assert row["model_frame_idx_status"] == "VALID_CONTIGUOUS_ZERO_BASED"
        assert (
            row["sequence_context_status"]
            == "RECONSTRUCTIBLE_COMPLETE_CHRONOLOGICAL_CONTEXT"
        )
        assert (
            row["preprocessing_authority_status"]
            == "HASHED_IMMUTABLE_RESTORATION_POINTER_COMPLETE"
        )
        assert row["checkpoint_preprocessing_identity_status"] == "COMPLETE"
        assert (
            sum(
                segment["row_count"]
                for segment in row["continuous_visible_segment_summary"]
            )
            == row["eligible_visible_row_count"]
        )


# ---------------------------------------------------------------------------
# Task 2 development analyses.
# ---------------------------------------------------------------------------

EXPECTED_FEATURE_COUNTS = {
    "GLOBAL_1x1": 2048,
    "COARSE_2x3": 12288,
    "COARSE_2x6": 24576,
    "MEDIUM_14x6": 172032,
    "FULL_14x24": 688128,
    "ROW_14x1": 28672,
    "COLUMN_1x24": 49152,
}
LAYOUT_LABELS = ("L01", "L02", "L03", "L04", "L05", "L06")


def _approx(value: float):
    import pytest

    return pytest.approx(value, rel=1e-12, abs=1e-12)


def _ladder_folds() -> dict[str, list[dict]]:
    ladder = _package("spatial_representation_ladder.json")
    return {name: block["folds"] for name, block in ladder["representations"].items()}


def test_partition_covers_the_14x24_grid_exactly_with_no_overlap() -> None:
    definitions = resolution.representation_definitions()
    assert set(definitions) == set(EXPECTED_FEATURE_COUNTS)
    for name, definition in definitions.items():
        regions = resolution.region_token_partition(
            definition["region_rows"], definition["region_cols"]
        )
        flattened = [token for region in regions for token in region]
        assert sorted(flattened) == list(range(336))
        assert len(flattened) == len(set(flattened)) == 336
        assert len(regions) == definition["region_count"]
        assert all(len(region) == definition["tokens_per_region"] for region in regions)
        assert definition["region_count"] * 2048 == definition["feature_count"]


def test_feature_counts_are_exactly_the_prespecified_ladder() -> None:
    definitions = resolution.representation_definitions()
    observed = {
        name: definition["feature_count"] for name, definition in definitions.items()
    }
    assert observed == EXPECTED_FEATURE_COUNTS

    ladder = _package("spatial_representation_ladder.json")
    for name, block in ladder["representations"].items():
        assert block["definition"]["feature_count"] == EXPECTED_FEATURE_COUNTS[name]
        for fold in block["folds"]:
            assert fold["feature_count"] == EXPECTED_FEATURE_COUNTS[name]


def test_partition_rejects_factor_incompatible_region_grids() -> None:
    import pytest

    for region_rows, region_cols in ((3, 24), (14, 5), (0, 1), (15, 24)):
        with pytest.raises(resolution.ResolutionError):
            resolution.region_token_partition(region_rows, region_cols)


def test_region_pooling_is_deterministic_and_preserves_region_identity() -> None:
    import numpy as np

    rng = np.random.default_rng(20260809)
    block = rng.standard_normal((5, 336, 2048)).astype(np.float16)
    first = resolution.build_representation_features(block, 2, 3)
    second = resolution.build_representation_features(block, 2, 3)
    assert np.array_equal(first, second)
    assert first.shape == (5, 12288)

    regions = resolution.region_token_partition(2, 3)
    reference = np.stack(
        [
            np.concatenate(
                [
                    block[row, list(region), :].astype(np.float32).mean(axis=0)
                    for region in regions
                ]
            )
            for row in range(5)
        ]
    )
    assert np.allclose(first, reference, rtol=0, atol=1e-3)


def test_exactly_six_outer_layout_folds_with_no_held_out_leakage() -> None:
    generalization = _package("six_layout_generalization.json")
    assert generalization["outer_design"]["outer_fold_count"] == 6
    assert generalization["row_authority"]["row_count"] == 351
    assert generalization["outer_design"]["alpha_grid"] == [0.1, 1, 10, 100]
    assert "NOT independent replications" in (
        generalization["outer_design"]["independence_caveat"]
    )

    for block in generalization["representations"].values():
        folds = block["folds"]
        assert [fold["held_out_layout"] for fold in folds] == list(LAYOUT_LABELS)
        for fold in folds:
            # Held-out layout is absent from training, from the scaler, and
            # from every alpha-selection group.
            assert fold["held_out_layout"] not in fold["training_group_ids"]
            assert len(fold["training_group_ids"]) == 5
            assert fold["train_row_count"] + fold["test_row_count"] == 351
            assert fold["scaler_training_row_count"] == fold["train_row_count"]
            assert fold["scaler_fit_scope"] == "training_layout_rows_only"
            assert fold["alpha_selection_grouping"] == "training_layout"
            assert fold["inner_fold_count"] == 5
            assert fold["selected_alpha"] in (0.1, 1, 10, 100)


def test_every_representation_shares_one_outer_row_authority() -> None:
    ladder = _package("spatial_representation_ladder.json")
    generalization = _package("six_layout_generalization.json")
    assert ladder["row_authority"] == generalization["row_authority"]

    folds = _ladder_folds()
    reference = {
        fold["held_out_layout"]: (
            fold["train_row_count"],
            fold["test_row_count"],
            tuple(fold["training_group_ids"]),
            fold["target_mean"],
            fold["target_std"],
            fold["target_sst"],
        )
        for fold in folds["GLOBAL_1x1"]
    }
    for name, records in folds.items():
        observed = {
            fold["held_out_layout"]: (
                fold["train_row_count"],
                fold["test_row_count"],
                tuple(fold["training_group_ids"]),
                fold["target_mean"],
                fold["target_std"],
                fold["target_sst"],
            )
            for fold in records
        }
        assert observed == reference, name

    # GLOBAL_MEAN and FULL_TOKEN_GRID in Task 2.2 are the ladder rungs.
    for alias, name in (
        ("GLOBAL_MEAN", "GLOBAL_1x1"),
        ("FULL_TOKEN_GRID", "FULL_14x24"),
    ):
        assert (
            generalization["representations"][alias]["folds"]
            == ladder["representations"][name]["folds"]
        )


def test_nmae_std_definition_and_zero_variance_handling() -> None:
    import numpy as np

    generalization = _package("six_layout_generalization.json")
    assert "MAE / test_target_std" in generalization["nmae_std_definition"]
    for block in generalization["representations"].values():
        for fold in block["folds"]:
            assert fold["nmae_std"] == _approx(fold["mae"] / fold["target_std"])

    constant = resolution.fold_metrics(np.full(4, 2.5), np.array([1.0, 2.0, 3.0, 4.0]))
    assert constant["target_std"] == 0.0
    assert constant["target_sst"] == 0.0
    assert constant["nmae_std"] is None
    assert constant["r2"] is None
    assert constant["pearson_r"] is None


def test_survivor_selection_is_deterministic_and_follows_the_declared_rule() -> None:
    ladder = _package("spatial_representation_ladder.json")
    folds = _ladder_folds()
    first = resolution.select_surviving_intermediate(folds)
    second = resolution.select_surviving_intermediate(folds)
    assert first == second
    assert first == ladder["survivor_selection"]

    surviving = first["surviving_intermediate"]
    assert surviving in resolution.INTERMEDIATE_CANDIDATES
    best = first["candidates"][0]
    assert best["representation"] == surviving
    # Rule 1 dominates: nothing beats the survivor on layouts above GLOBAL.
    assert all(
        candidate["layouts_above_global"] <= best["layouts_above_global"]
        for candidate in first["candidates"]
    )
    assert first["selection_metric_scope"] == "per_layout_outer_folds_only"


def test_development_freeze_is_deterministic_and_precedes_new_performance() -> None:
    freeze = _package("development_freeze.json")
    ladder = _package("spatial_representation_ladder.json")
    rebuilt = resolution.build_development_freeze(
        ladder["survivor_selection"], resolution.representation_definitions()
    )
    assert rebuilt == freeze
    assert (
        resolution.build_development_freeze(
            ladder["survivor_selection"], resolution.representation_definitions()
        )
        == freeze
    )

    assert freeze["layer_idx"] == 4
    assert (
        freeze["layer_selection_status"]
        == "EXPLORATORY_PRESELECTED_FROM_EXISTING_POSITIVE_CONTROL"
    )
    assert freeze["representation_set"] == [
        "GLOBAL_MEAN",
        ladder["survivor_selection"]["surviving_intermediate"],
        "FULL_TOKEN_GRID",
    ]
    assert freeze["alpha_grid"] == [0.1, 1, 10, 100]
    assert freeze["scaling"] == "training_rows_only"
    assert freeze["future_within_layout_outer_group"] == "trajectory"
    assert freeze["future_within_layout_ge3_alpha_group"] == "training_trajectory"
    assert freeze["future_across_layout_alpha_group"] == "training_layout"
    assert len(freeze["sample_specific_spatial_scramble"]["seeds"]) == 5
    assert len(set(freeze["sample_specific_spatial_scramble"]["seeds"])) == 5
    assert freeze["sample_specific_spatial_scramble"]["results_inspected"] is False
    assert freeze["target_null_semantics"]["status"] == "PLACEHOLDER"
    assert freeze["frozen_before_any_new_trajectory_performance_exists"] is True
    assert (
        freeze["task_1_eligibility"]["eligible_row_keys_sha256"]
        == _package("expanded_visibility_eligibility.json")["eligible_row_keys_sha256"]
    )
    assert len(freeze["development_freeze_sha256"]) == 64


def test_metric_decomposition_reuses_predictions_without_refitting() -> None:
    decomposition = _package("metric_decomposition.json")
    assert decomposition["no_refit"] is True
    assert decomposition["prediction_source"] == "task_2_2_outer_fold_predictions"
    assert decomposition["target_metric_instability_contributes"] in (
        True,
        False,
        "UNCLEAR",
    )
    assert decomposition["target_metric_instability_reason"]
    assert [item["held_out_layout"] for item in decomposition["per_layout"]] == list(
        LAYOUT_LABELS
    )

    generalization = _package("six_layout_generalization.json")
    full = {
        fold["held_out_layout"]: fold
        for fold in generalization["representations"]["FULL_TOKEN_GRID"]["folds"]
    }
    for item in decomposition["per_layout"]:
        assert item["full_r2"] == full[item["held_out_layout"]]["r2"]
        assert item["target_sst"] == full[item["held_out_layout"]]["target_sst"]


def test_runtime_benchmark_does_not_gate_scientific_scope() -> None:
    benchmark = _package("runtime_benchmark.json")
    assert benchmark["representation"] == "FULL_TOKEN_GRID"
    assert benchmark["feature_count"] == 688128
    assert benchmark["held_out_layout"] in LAYOUT_LABELS
    assert benchmark["train_row_count"] + benchmark["test_row_count"] == 351
    assert benchmark["total_runtime_seconds"] > 0
    assert "OPTIONAL" in benchmark["benchmark_authority_note"]


def test_frozen_mvp_and_predecessor_inputs_are_untouched() -> None:
    frozen = (
        "configs/experiments/mvp.yaml",
        "configs/experiments/exploratory_visible_position_diagnostics_v0_1.yaml",
        "docs/status/person_c_c7_mvp_handoff_v0_1",
        "docs/status/person_b_66_cell_oracle_target_v0_1",
        "docs/status/person_a_66_cell_preprocessed_media_v0_2",
        "scripts/run_exploratory_visible_position_diagnostics.py",
        "scripts/run_person_a_66_cell_production_extraction.py",
    )
    completed = subprocess.run(
        ["git", "status", "--porcelain=v1", "--", *frozen],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert completed.stdout == ""


def test_frozen_packages_have_no_worktree_changes() -> None:
    predecessor = (
        "docs/status/integration/exploratory_visible_position_diagnostics_v0_1"
    )
    completed = subprocess.run(
        ["git", "status", "--porcelain=v1", "--", predecessor],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert completed.stdout == ""

    status = subprocess.run(
        ["git", "status", "--porcelain=v1"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    # The complete successor-program footprint: Task 1-5 scientific outputs and
    # runners, the closeout package builder, and the capture-runtime
    # portability work that produced the Task 3 replication authority.  Any
    # path outside this set is an unexpected worktree change.
    allowed = (
        "docs/status/integration/exploratory_visible_position_resolution_v0_1/",
        "docs/status/capture_runtime_sagemaker_v0_1/",
        "scripts/run_exploratory_visible_position_resolution.py",
        "scripts/run_visible_position_resolution_task4.py",
        "scripts/run_visible_position_resolution_task5.py",
        "scripts/build_visible_position_resolution_closeout.py",
        "scripts/provision_capture_runtime_sagemaker.sh",
        "scripts/run_autonomous_pilot.py",
        "fabric/mineocclude-mod/src/main/java/com/mineocclude/client/"
        "MineOccludeClient.java",
        "tests/diagnostics/test_visible_position_resolution.py",
        "tests/diagnostics/test_visible_position_resolution_task4.py",
        "tests/diagnostics/test_visible_position_resolution_task5.py",
        "tests/diagnostics/test_visible_position_resolution_closeout.py",
        "tests/test_autonomous_pilot_portability.py",
    )
    changed_paths = [line[3:] for line in status]
    assert changed_paths
    unexpected = [path for path in changed_paths if not path.startswith(allowed)]
    assert not unexpected, unexpected
