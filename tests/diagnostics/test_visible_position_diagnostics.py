from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import torch

from mineocclude.activations import hooks as hooks_module
from mineocclude.activations.pool import (
    mean_pool_visual_tokens,
    select_visual_token_positions,
)
from mineocclude.contracts.identity import SCHEMA_VERSION
from mineocclude.models.mineworld_adapter import (
    FrameIdentity,
    FrameTokenMap,
    FrameTokenSpan,
)

ROOT = Path(__file__).resolve().parents[2]
RUNNER_PATH = ROOT / "scripts/run_exploratory_visible_position_diagnostics.py"
SPEC = importlib.util.spec_from_file_location(
    "visible_position_diagnostics", RUNNER_PATH
)
assert SPEC is not None and SPEC.loader is not None
diagnostic = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = diagnostic
SPEC.loader.exec_module(diagnostic)


PACKAGE = ROOT / "docs/status/integration/exploratory_visible_position_diagnostics_v0_1"
ALPHA_GRID = {0.1, 1.0, 10.0, 100.0}


def _authority():
    return diagnostic.load_visible_authority(diagnostic.load_config())


def _package(name: str):
    path = PACKAGE / name
    assert path.is_file(), f"missing committed diagnostic artifact: {path}"
    return json.loads(path.read_text(encoding="utf-8"))


def test_exact_six_trajectory_authority_counts_split_and_no_overlap() -> None:
    rows = _authority()
    counts = {
        label: sum(row["trajectory_label"] == label for row in rows)
        for label in ("L01", "L02", "L03", "L04", "L05", "L06")
    }
    assert counts == {
        "L01": 60,
        "L02": 60,
        "L03": 60,
        "L04": 60,
        "L05": 60,
        "L06": 51,
    }
    assert [record[2] for record in diagnostic.TRAJECTORIES] == [
        "layout_01_ep12602",
        "layout_02_ep12610",
        "layout_03_ep12645",
        "layout_04_ep12626",
        "layout_05_ep12634",
        "layout_06_ep12616",
    ]
    assert [(record[3], record[4]) for record in diagnostic.TRAJECTORIES] == [
        (60, 60),
        (60, 60),
        (60, 60),
        (60, 60),
        (60, 60),
        (60, 51),
    ]
    test = [
        row for row in rows if row["trajectory_label"] in diagnostic.FIXED_TEST_LABELS
    ]
    train = [
        row
        for row in rows
        if row["trajectory_label"] in diagnostic.TRAINING_POOL_LABELS
    ]
    assert len(rows) == 351
    assert len(test) == 120
    assert len(train) == 231
    assert {row["trajectory_label"] for row in test} == {"L03", "L04"}
    assert {row["trajectory_label"] for row in train} == {"L01", "L02", "L05", "L06"}
    assert {row["fold_idx"] for row in test} == {4}
    assert 4 not in {row["fold_idx"] for row in train}
    assert not ({row["row_key"] for row in test} & {row["row_key"] for row in train})


def test_learning_curve_has_only_six_k2_four_k3_and_one_k4_subsets() -> None:
    rows = _authority()
    plans = diagnostic.build_subset_plan(rows)
    assert len(plans) == 11
    assert sum(plan["k_trajectories"] == 2 for plan in plans) == 6
    assert sum(plan["k_trajectories"] == 3 for plan in plans) == 4
    assert sum(plan["k_trajectories"] == 4 for plan in plans) == 1
    assert all(plan["k_trajectories"] != 1 for plan in plans)
    assert len({plan["fixed_test_sha256"] for plan in plans}) == 1
    assert {plan["fixed_test_frame_count"] for plan in plans} == {120}
    assert plans[-1]["training_trajectory_labels"] == ["L01", "L02", "L05", "L06"]
    assert plans[-1]["training_frame_count"] == 231


def test_unpooled_and_pooled_shapes_dtypes_are_exact() -> None:
    tokens = np.zeros((1, 336, 2048), dtype=np.float16)
    pooled = np.zeros((1, 2048), dtype=np.float32)
    observed_tokens, observed_pooled = diagnostic.validate_extracted_arrays(
        tokens, pooled, expected_rows=1
    )
    assert observed_tokens.shape == (1, 336, 2048)
    assert observed_pooled.shape == (1, 2048)
    assert observed_tokens.dtype == np.float16
    assert observed_pooled.dtype == np.float32


def test_selected_336_tokens_reproduce_current_production_mean_pool() -> None:
    identity = FrameIdentity(SCHEMA_VERSION, "trajectory", 0)
    span = FrameTokenSpan(
        identity=identity,
        pair_index=0,
        accepted_pair_index=0,
        pair_start=0,
        pair_end_exclusive=347,
        visual_positions=tuple(range(336)),
        action_positions=tuple(range(336, 347)),
    )
    frame_map = FrameTokenMap(
        schema_version=SCHEMA_VERSION,
        trajectory_id="trajectory",
        sequence_length=347,
        spans=(span,),
    )
    activation = (
        torch.linspace(-1.0, 1.0, steps=347 * 2048, dtype=torch.float32)
        .reshape(1, 347, 2048)
        .to(torch.float16)
    )
    selection = select_visual_token_positions(
        frame_map,
        trajectory_id="trajectory",
        model_frame_idx=0,
        hooked_sequence_length=347,
    )
    production_pool = mean_pool_visual_tokens(
        activation=activation,
        selection=selection,
        layer_idx=4,
        hook_site=diagnostic.HOOK_SITE,
    )
    tokens = activation[:, :336, :].squeeze(0).numpy().copy()
    pooled = production_pool.vector.numpy().copy()
    comparison = diagnostic.compare_token_pooling(tokens, pooled)
    assert len(selection.positions) == 336
    assert comparison["allclose"] is True


class _Handle:
    def __init__(self, module: "_Module") -> None:
        self.module = module

    def remove(self) -> None:
        self.module.removed = True


class _Module:
    def __init__(self) -> None:
        self.callback = None
        self.registration_count = 0
        self.removed = False

    def register_forward_hook(self, callback):
        self.callback = callback
        self.registration_count += 1
        return _Handle(self)


def test_layer_capture_registers_only_requested_layer_four() -> None:
    modules = [_Module() for _ in range(20)]
    layers = [
        hooks_module.HookLayerMetadata(
            layer_idx=index,
            module_name=f"decoder.{index}",
            module_type="fixture.Module",
            conceptual_site=hooks_module.CONCEPTUAL_HOOK_SITE,
            discovery_version=hooks_module.HOOK_DISCOVERY_VERSION,
        )
        for index in range(20)
    ]
    discovery = SimpleNamespace(
        iter_runtime_layers=lambda: iter(zip(layers, modules, strict=True))
    )
    manager = diagnostic._LayerCaptureContext(discovery, 4)
    with manager:
        assert modules[4].callback is not None
        modules[4].callback(
            modules[4], (), torch.zeros((1, 347, 2048), dtype=torch.float16)
        )
    assert [module.registration_count for module in modules] == [
        0,
        0,
        0,
        0,
        1,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
    ]
    assert manager.capture.layer.layer_idx == 4
    assert manager.closed is True
    assert modules[4].removed is True


def test_historical_bridge_reports_exact_and_maximum_difference() -> None:
    old = np.zeros((336, 2048), dtype=np.float16)
    new = old.copy()
    exact = diagnostic.compare_historical_tokens(new, old)
    assert exact["exact"] is True
    assert exact["maximum_absolute_difference"] == 0.0
    new[10, 20] = np.float16(0.5)
    changed = diagnostic.compare_historical_tokens(new, old)
    assert changed["exact"] is False
    assert changed["maximum_absolute_difference"] == 0.5


def test_ridge_selection_scaler_and_groups_use_training_rows_only() -> None:
    training_features = np.asarray(
        [[index, index % 3, 1.0] for index in range(12)], dtype=np.float64
    )
    training_targets = np.asarray(
        [0.25 * index - (index % 2) for index in range(12)], dtype=np.float64
    )
    groups = ["A"] * 4 + ["B"] * 4 + ["C"] * 4
    test_features = np.asarray([[2.0, 1.0, 1.0], [9.0, 0.0, 1.0]])
    _, first = diagnostic.fit_fixed_test_ridge(
        training_features,
        training_targets,
        groups,
        test_features,
        alpha_grid=(0.1, 1.0, 10.0, 100.0),
        seed=20260719,
    )
    _, second = diagnostic.fit_fixed_test_ridge(
        training_features,
        training_targets,
        groups,
        test_features * 1_000_000.0,
        alpha_grid=(0.1, 1.0, 10.0, 100.0),
        seed=20260719,
    )
    assert first == second
    assert first["selected_alpha"] in {0.1, 1.0, 10.0, 100.0}
    assert first["inner_fold_count"] == 3
    assert first["training_group_ids"] == ["A", "B", "C"]
    assert first["scaler_fit_scope"] == "training_subset_rows_only"
    assert first["scaler_training_row_count"] == 12


def test_token_grid_is_the_verified_fourteen_by_twentyfour_identity() -> None:
    assert diagnostic.TOKEN_COUNT == 336
    assert diagnostic.TOKEN_GRID_ROWS == 14
    assert diagnostic.TOKEN_GRID_COLS == 24
    assert diagnostic.TOKEN_GRID_ROWS * diagnostic.TOKEN_GRID_COLS == 336
    assert diagnostic.TOKEN_FLATTENED_FEATURE_COUNT == 336 * 2048
    assert diagnostic.token_grid_position(0) == (0, 0)
    assert diagnostic.token_grid_position(23) == (0, 23)
    assert diagnostic.token_grid_position(24) == (1, 0)
    assert diagnostic.token_grid_position(335) == (13, 23)
    cells = [diagnostic.token_grid_position(index) for index in range(336)]
    assert len(set(cells)) == 336
    assert {row for row, _ in cells} == set(range(14))
    assert {col for _, col in cells} == set(range(24))
    for index, (row, col) in enumerate(cells):
        assert index == row * diagnostic.TOKEN_GRID_COLS + col
    for invalid in (-1, 336):
        try:
            diagnostic.token_grid_position(invalid)
        except diagnostic.DiagnosticError:
            continue
        raise AssertionError(f"token index {invalid} must be rejected")


def test_token_split_is_the_frozen_231_120_partition_without_overlap() -> None:
    rows = _authority()
    train_index, test_index = diagnostic._split_indices(rows)
    assert train_index.size == 231
    assert test_index.size == 120
    assert not set(train_index.tolist()) & set(test_index.tolist())
    train_labels = {rows[index]["trajectory_label"] for index in train_index}
    test_labels = {rows[index]["trajectory_label"] for index in test_index}
    assert train_labels == {"L01", "L02", "L05", "L06"}
    assert test_labels == {"L03", "L04"}
    assert not train_labels & test_labels
    train_ids = {rows[index]["trajectory_id"] for index in train_index}
    test_ids = {rows[index]["trajectory_id"] for index in test_index}
    assert not train_ids & test_ids


def test_dual_ridge_solver_matches_an_independent_primal_reference() -> None:
    generator = np.random.default_rng(20260719)
    train_features = generator.normal(size=(24, 60))
    weights = generator.normal(size=60)
    train_targets = train_features @ weights + generator.normal(scale=0.1, size=24)
    test_features = generator.normal(size=(9, 60))
    # p > n, so fit_ridge must take the dual/sample-space branch.
    assert train_features.shape[1] > train_features.shape[0]
    record = diagnostic.check_solver_equivalence(
        train_features, train_targets, test_features, alpha=10.0
    )
    assert record["library_path"] == "dual_sample_space"
    assert record["pass"] is True
    assert (
        record["max_abs_prediction_difference_vs_independent_primal"]
        <= record["tolerance"]
    )


def test_token_result_classification_follows_the_roadmap_table() -> None:
    pool = {"r2": 0.10, "L03_r2": 0.10, "L04_r2": 0.10}
    both_better = {"r2": 0.40, "L03_r2": 0.30, "L04_r2": 0.50}
    one_worse = {"r2": 0.40, "L03_r2": 0.90, "L04_r2": 0.05}
    not_better = {"r2": 0.05, "L03_r2": 0.90, "L04_r2": 0.01}
    assert (
        diagnostic.classify_token_result(pool, both_better, solver_pass=True)
        == "CLEAR_TOKEN_GAIN"
    )
    assert (
        diagnostic.classify_token_result(pool, one_worse, solver_pass=True)
        == "MIXED_TOKEN_GAIN"
    )
    assert (
        diagnostic.classify_token_result(pool, not_better, solver_pass=True)
        == "LITTLE_OR_NO_TOKEN_GAIN"
    )
    assert (
        diagnostic.classify_token_result(pool, both_better, solver_pass=False)
        == "INSUFFICIENT_TOKEN_EVIDENCE"
    )


def test_committed_extraction_manifest_binds_351_rows_at_layer_four() -> None:
    manifest = _package("unpooled_activation_manifest.json")
    scope = manifest["scope"]
    assert manifest["status"] == "COMPLETE"
    assert scope["layer_idx"] == 4
    assert scope["eligible_row_count"] == 351
    assert scope["visual_token_count"] == 336
    assert scope["hidden_width"] == 2048
    assert scope["trajectory_count"] == 6
    assert scope["other_layers_retained"] is False
    assert len(manifest["chunks"]) == 6
    assert sum(chunk["eligible_row_count"] for chunk in manifest["chunks"]) == 351


def test_committed_learning_curve_has_deterministic_eleven_subsets() -> None:
    curve = _package("learning_curve.json")
    results = curve["results"]
    assert len(results) == 11
    assert sum(row["k_trajectories"] == 2 for row in results) == 6
    assert sum(row["k_trajectories"] == 3 for row in results) == 4
    assert sum(row["k_trajectories"] == 4 for row in results) == 1
    assert len({row["fixed_test_sha256"] for row in results}) == 1
    assert {row["fixed_test_frame_count"] for row in results} == {120}
    assert all(
        row["scaler_fit_scope"] == "training_subset_rows_only" for row in results
    )
    assert all(
        row["selection_policy"] == "leave-one-training-trajectory-out"
        for row in results
    )


def test_committed_token_map_scores_336_positions_on_the_verified_grid() -> None:
    document = _package("token_spatial_map.json")
    grid = document["grid"]
    positions = document["positions"]
    assert (grid["rows"], grid["cols"], grid["token_count"]) == (14, 24, 336)
    assert len(positions) == 336
    assert {record["token_index"] for record in positions} == set(range(336))
    assert {record["grid_row"] for record in positions} == set(range(14))
    assert {record["grid_col"] for record in positions} == set(range(24))
    for record in positions:
        assert record["token_index"] == record["grid_row"] * 24 + record["grid_col"]
        assert np.isfinite(record["held_out_r2"])
        assert float(record["selected_alpha"]) in ALPHA_GRID
        assert record["scaler_fit_scope"] == "training_subset_rows_only"
        assert record["scaler_training_row_count"] == 231
        assert record["selection_policy"] == "leave-one-training-trajectory-out"
        assert record["inner_fold_count"] == 4


def test_committed_token_and_mean_pool_scored_the_identical_120_rows() -> None:
    metrics = _package("token_probe_metrics.json")
    spatial = _package("token_spatial_map.json")
    split = metrics["split"]
    assert split["train_row_count"] == 231
    assert split["test_row_count"] == 120
    assert split["train_test_trajectory_overlap_count"] == 0
    assert not set(split["train_trajectory_ids"]) & set(split["test_trajectory_ids"])
    assert split["fixed_test_sha256"] == diagnostic.fixed_test_hash(_authority())
    assert split["alpha_selection"] == "leave-one-training-trajectory-out"
    assert sorted(float(value) for value in split["alpha_grid"]) == sorted(ALPHA_GRID)
    assert spatial["split"]["scored_test_identity_sha256"] == (
        split["scored_test_identity_sha256"]
    )
    identities = {
        record["scored_test_identity_sha256"] for record in spatial["positions"]
    }
    assert identities == {split["scored_test_identity_sha256"]}
    for name in ("mean_pool", "token_flattened"):
        assert metrics[name]["sample_count"] == 120
        assert metrics[name]["scaler_fit_scope"] == "training_subset_rows_only"
        assert metrics[name]["scaler_training_row_count"] == 231
        assert metrics[name]["inner_fold_count"] == 4
    assert metrics["token_flattened"]["feature_count"] == 336 * 2048
    assert metrics["solver"]["pass"] is True
    assert metrics["historical_oof_reuse"] is False
    assert metrics["mean_pool_comparator_source"] == (
        "REFIT_FROM_NEW_VERIFIED_LAYER4_EXTRACTION"
    )
    assert metrics["token_result_class"] == diagnostic.classify_token_result(
        metrics["mean_pool"],
        metrics["token_flattened"],
        solver_pass=bool(metrics["solver"]["pass"]),
    )


def test_committed_token_provenance_points_at_durable_repository_code() -> None:
    metrics = _package("token_probe_metrics.json")
    provenance = metrics["provenance"]
    code_path = ROOT / provenance["analysis_code_path"]
    assert code_path == RUNNER_PATH
    assert code_path.is_file()
    assert provenance["analysis_code_sha256"] == diagnostic.sha256_file(code_path)
    assert provenance["analysis_mode"] == "token-analysis"
    assert provenance["layer_idx"] == 4


def test_final_adjudication_is_insufficient_evidence_and_preserves_both_findings() -> (
    None
):
    adjudication = _package("diagnostic_adjudication.json")
    assert adjudication["FINAL_DIAGNOSIS"] == "INSUFFICIENT_EVIDENCE"
    assert adjudication["ORIGINAL_MVP_RESULT_MODIFIED"] is False
    assert adjudication["LAYER_SELECTION_STATUS"] == (
        "EXPLORATORY_PRESELECTED_FROM_EXISTING_POSITIVE_CONTROL"
    )
    assert adjudication["inputs"]["DATA_CURVE"] == "HIGH_TRAJECTORY_VARIANCE"
    assert adjudication["inputs"]["TOKEN_RESULT"] == "MIXED_TOKEN_GAIN"
    assert isinstance(adjudication["NEXT_SCIENTIFIC_DIRECTION"], str)
    assert adjudication["NEXT_SCIENTIFIC_DIRECTION"].strip()
    assert len(adjudication["findings_preserved"]) == 2


def test_diagnostic_package_targets_only_the_exploratory_directory() -> None:
    config = diagnostic.load_config()
    receipt_root = ROOT / config["storage"]["receipt_root"]
    assert receipt_root == PACKAGE
    assert PACKAGE.is_relative_to(ROOT / "docs/status/integration")
    assert "exploratory_visible_position_diagnostics_v0_1" in str(receipt_root)
    external = Path(config["storage"]["external_base_root"])
    assert external.name == "exploratory_visible_position_diagnostics_v0_1"
