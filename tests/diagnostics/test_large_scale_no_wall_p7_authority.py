"""Focused P7 representation and solver authority checks.

These tests never compute a fixed-test prediction or scientific score.  They
exercise only transformation identity, training-only scaling, exact ridge
equivalence, frozen grouped ID flow, and compact P7 receipts.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

from mineocclude.probes.p7_ridge import (
    accumulate_standardized_kernel,
    batched_ridge_predictions_all_alphas,
    batched_token_kernels_numpy,
    cumulative_token_kernel_snapshots,
    ridge_predictions_all_alphas_from_kernel,
    standardized_kernel_numpy,
)
from mineocclude.probes.ridge import fit_ridge, fit_standard_scaler

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = (
    ROOT / "docs/status/integration/exploratory_large_scale_no_wall_scaling_best_k_v0_1"
)
SCRIPT = ROOT / "scripts/build_large_scale_no_wall_p7_authority.py"


def load_module():
    specification = importlib.util.spec_from_file_location("p7_authority", SCRIPT)
    assert specification and specification.loader
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


p7 = load_module()


def load(name: str) -> dict:
    return json.loads((PACKAGE / name).read_text())


def test_literal_standard_scaler_and_dual_predictions_match_repository_reference():
    generator = np.random.default_rng(20260810)
    features = generator.normal(size=(18, 47))
    targets = generator.normal(size=13)
    training = features[:13]
    validation = features[13:]
    kernel_result = standardized_kernel_numpy(training, features)
    optimized = ridge_predictions_all_alphas_from_kernel(
        kernel_result.kernel,
        targets,
        alphas=p7.ALPHAS,
        prediction_scope_positions=range(13, 18),
    )
    scaler = fit_standard_scaler(training)
    assert kernel_result.scaler.training_row_count == 13
    assert np.array_equal(kernel_result.scaler.mean, np.asarray(scaler.mean))
    assert np.array_equal(kernel_result.scaler.scale, np.asarray(scaler.scale))
    for alpha in p7.ALPHAS:
        reference = np.asarray(
            fit_ridge(training, targets, alpha=alpha, scaler=scaler).predict(validation)
        )
        assert np.allclose(optimized[alpha], reference, atol=1e-7, rtol=1e-7)


def test_validation_rows_cannot_change_training_scaler_or_training_kernel():
    generator = np.random.default_rng(41)
    training = generator.normal(size=(9, 12))
    validation = generator.normal(size=(4, 12))
    first = standardized_kernel_numpy(training, np.concatenate([training, validation]))
    second = standardized_kernel_numpy(
        training, np.concatenate([training, validation * 1_000_000.0])
    )
    assert np.array_equal(first.scaler.mean, second.scaler.mean)
    assert np.array_equal(first.scaler.scale, second.scaler.scale)
    assert np.array_equal(first.kernel[:9], second.kernel[:9])


def test_constant_features_follow_repository_unit_scale_semantics():
    matrix = np.arange(30, dtype=np.float64).reshape(6, 5)
    matrix[:, 2] = 7.0
    result = standardized_kernel_numpy(matrix[:4], matrix)
    reference = fit_standard_scaler(matrix[:4])
    assert result.scaler.constant_feature_count == 1
    assert result.scaler.scale[2] == reference.scale[2] == 1.0


def test_feature_block_kernel_accumulation_equals_explicit_concatenation():
    generator = np.random.default_rng(7)
    training_a = generator.normal(size=(8, 9))
    scope_a = generator.normal(size=(12, 9))
    scope_a[:8] = training_a
    training_b = generator.normal(size=(8, 11))
    scope_b = generator.normal(size=(12, 11))
    scope_b[:8] = training_b
    accumulated, records = accumulate_standardized_kernel(
        [(training_a, scope_a), (training_b, scope_b)], device="cpu"
    )
    explicit = standardized_kernel_numpy(
        np.concatenate([training_a, training_b], axis=1),
        np.concatenate([scope_a, scope_b], axis=1),
    ).kernel
    assert len(records) == 2
    assert np.allclose(accumulated, explicit, atol=1e-12, rtol=1e-12)


def test_batched_token_and_cumulative_best_k_kernels_are_exact():
    generator = np.random.default_rng(9)
    tokens = generator.normal(size=(14, 8, 17))
    batched, scalers = batched_token_kernels_numpy(tokens[:10], tokens)
    assert batched.shape == (8, 14, 10)
    assert len(scalers) == 8
    mapping = {token: batched[token] for token in range(8)}
    ranking = [6, 1, 7, 2, 0, 5, 4, 3]
    snapshots = cumulative_token_kernel_snapshots(mapping, ranking, (1, 4, 8))
    assert np.array_equal(snapshots[1], mapping[6])
    assert np.allclose(snapshots[4], sum(mapping[token] for token in ranking[:4]))
    assert np.allclose(snapshots[8], sum(mapping[token] for token in ranking))
    predictions = batched_ridge_predictions_all_alphas(
        batched[:2], np.arange(10, dtype=np.float64), alphas=p7.ALPHAS
    )
    assert len(predictions) == 2
    assert all(set(record) == set(p7.ALPHAS) for record in predictions)


def test_frozen_predecessors_and_p6_local_manifest_identity_are_preserved():
    authority = p7.verify_start_authority()
    assert authority["manifest"]["trajectory_count"] == 120
    assert authority["manifest"]["frame_count"] == 7200
    assert authority["split"]["train_test_overlap"] == 0
    assert authority["split"]["v1_primary_intersection"] == 0


def test_canonical_row_authority_has_one_shared_v2_only_order():
    rows = p7.read_jsonl(p7.CANONICAL_ROWS)
    assert len(rows) == 7200
    keys = [tuple(row["scientific_row_key"]) for row in rows]
    assert len(set(keys)) == 7200
    assert [row["row_ordinal"] for row in rows] == list(range(7200))
    assert all(key[0].startswith("fresh_vp_v2_") for key in keys)
    assert sum(row["membership"] == "training_pool" for row in rows) == 6120
    assert sum(row["membership"] == "fixed_test" for row in rows) == 1080
    receipt = load("p7_receipt.json")
    assert p7.canonical_sha256(rows) == receipt["canonical_row_hash"]


def test_manifest_addressed_representation_dimensions_and_orders_are_frozen():
    authority = load("representation_authority.json")
    assert authority["global_mean"]["dimension"] == 2048
    assert authority["global_mean"]["equivalence_max_abs_difference"] == 0.0
    assert authority["full_token_grid"]["dimension"] == 688128
    assert authority["best_k_tokens"]["candidate_k"] == [1, 4, 8, 16, 32, 64, 128]
    assert authority["best_k_tokens"]["feature_concatenation_order"] == (
        "ascending visual_token_index"
    )
    assert authority["coarse_2x6"]["dimension"] == 24576
    assert authority["coarse_2x6"]["validation"] == "PASS"


def test_actual_full_best_k_and_coarse_access_views_preserve_geometry():
    rows = p7.read_jsonl(p7.CANONICAL_ROWS)
    access = p7.ActivationAccess(rows)
    cache = load("cache_manifest.json")["entries"]["COARSE_2x6"]
    checks = p7.validate_representation_views(access, cache)
    assert checks["full_token_order"] == "PASS"
    assert checks["best_k_ascending_order"] == "PASS"
    assert checks["coarse_geometry"] == "PASS"


def test_nested_best_k_grouping_and_logical_budgets_replay_exactly():
    authority = p7.verify_start_authority()
    nested = p7.validate_nested_grouping(authority)
    assert nested == {
        "fixed_test_ids_used": 0,
        "nested_ranking_subfold_records": 1240,
        "status": "PASS",
        "subset_count": 62,
    }
    budgets = p7.validate_logical_budgets(authority)
    assert budgets["nested_token_ranking_logical_evaluations"] == 1666560
    assert budgets["best_k_candidate_logical_evaluations"] == 8680
    assert budgets["final_token_ranking_logical_evaluations"] == 416640
    assert budgets["status"] == "PASS"


def test_benchmarks_are_training_only_and_freeze_runtime_not_outcomes():
    benchmark = load("solver_benchmark.json")
    assert benchmark["status"] == "PASS_TRAINING_ONLY"
    assert benchmark["fixed_test_targets_used"] is False
    assert benchmark["fixed_test_predictions_computed"] is False
    assert benchmark["fixed_test_scores_opened"] is False
    assert benchmark["no_scientific_r2_values_persisted"] is True
    assert benchmark["n5"]["subset_id"] == "n005_r00"
    assert benchmark["n100"]["subset_id"] == "n100_r00"
    assert benchmark["n5"]["fixed_test_target_count_loaded"] == 0
    assert benchmark["n100"]["fixed_test_target_count_loaded"] == 0
    assert benchmark["solver_equivalence"]["status"] == "PASS"
    assert (
        benchmark["solver_equivalence"]["maximum_absolute_prediction_difference"]
        <= 1e-7
    )


def test_execution_budget_and_cache_policy_are_locked_before_p8():
    budget = load("execution_budget.lock.json")
    cache = load("cache_manifest.json")
    assert budget["status"] == "LOCKED_FOR_P8"
    assert budget["frozen_before_fixed_test_outcomes"] is True
    assert budget["numerical_computation_dtype"] == "float64"
    assert budget["token_batch_size"] == 4
    assert budget["feature_chunk_size"] == 8192
    assert budget["bounded_parallelism"] == 1
    assert cache["entries"]["FULL_TOKEN_GRID"]["cache_materialized"] is False
    assert cache["entries"]["GLOBAL_MEAN"]["cache_materialized"] is False
    assert cache["entries"]["COARSE_2x6"]["durability_status"] == (
        "RECONSTRUCTABLE_NVME_ONLY"
    )
    assert cache["reconstructable_cache_s3_upload_skipped"] is True


def test_no_full_feature_covariance_or_p8_scientific_artifact_exists():
    source = (ROOT / "src/mineocclude/probes/p7_ridge.py").read_text()
    runner = SCRIPT.read_text()
    assert "688128 x 688128" not in source
    assert "np.eye(FULL_DIM" not in source + runner
    assert not (PACKAGE / "learning_curve_results.json").exists()
    assert not (PACKAGE / "best_k_results.json").exists()
    assert not (PACKAGE / "target_null_results.json").exists()
    receipt = load("p7_receipt.json")
    assert receipt["mineworld_rerun"] is False
    assert receipt["fresh_activations_extracted"] is False
    assert receipt["fresh_r2_computed"] is False
    assert receipt["p8_started"] is False
    assert receipt["safe_for_p8"] is True


@pytest.mark.skipif(not p7.CACHE_ROOT.exists(), reason="P7 runtime cache not built")
def test_focused_validate_only_contract_passes():
    p7.validate_existing_documents()
