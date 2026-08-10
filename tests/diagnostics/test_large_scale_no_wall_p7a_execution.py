"""Focused checks for the prospective exact P7A execution amendment."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest
import torch

from mineocclude.probes.p7_ridge import (
    ridge_predictions_all_alphas_from_features,
    standardized_kernel_numpy,
)
from mineocclude.probes.p7a_execution import (
    batched_ridge_predictions_all_alphas_from_features,
    batched_ridge_predictions_all_alphas_from_features_cuda,
    standardized_token_kernel_sum_cuda,
)

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = (
    ROOT / "docs/status/integration/exploratory_large_scale_no_wall_scaling_best_k_v0_1"
)
SCRIPT = ROOT / "scripts/optimize_large_scale_no_wall_p7a_execution.py"
ALPHAS = (0.1, 1.0, 10.0, 100.0)


def load_module():
    specification = importlib.util.spec_from_file_location("p7a_execution", SCRIPT)
    assert specification and specification.loader
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


p7a = load_module()


def load(name: str) -> dict:
    return json.loads((PACKAGE / name).read_text())


def test_batched_cpu_schedule_retains_independent_exact_token_models():
    generator = np.random.default_rng(20260810)
    tokens = generator.normal(size=(19, 4, 13)).astype(np.float16)
    targets = generator.normal(size=12)
    serial = batched_ridge_predictions_all_alphas_from_features(
        tokens,
        targets,
        training_row_count=12,
        alphas=ALPHAS,
        parallelism=1,
    )
    parallel = batched_ridge_predictions_all_alphas_from_features(
        tokens,
        targets,
        training_row_count=12,
        alphas=ALPHAS,
        parallelism=2,
    )
    for token in range(4):
        literal = ridge_predictions_all_alphas_from_features(
            tokens[:12, token],
            tokens[:, token],
            targets,
            alphas=ALPHAS,
            prediction_scope_positions=range(12, 19),
        )
        for alpha in ALPHAS:
            assert np.array_equal(
                serial.predictions_by_token[token][alpha],
                literal.predictions_by_alpha[alpha],
            )
            assert np.array_equal(
                parallel.predictions_by_token[token][alpha],
                literal.predictions_by_alpha[alpha],
            )


@pytest.mark.skipif(not torch.cuda.is_available(), reason="CUDA unavailable")
def test_batched_cuda_solve_and_summed_kernel_match_frozen_cpu_semantics():
    generator = np.random.default_rng(41)
    tokens = generator.normal(size=(18, 3, 11)).astype(np.float16)
    targets = generator.normal(size=12)
    cpu = batched_ridge_predictions_all_alphas_from_features(
        tokens, targets, training_row_count=12, alphas=ALPHAS
    )
    cuda = batched_ridge_predictions_all_alphas_from_features_cuda(
        tokens, targets, training_row_count=12, alphas=ALPHAS
    )
    for token in range(3):
        for alpha in ALPHAS:
            assert np.allclose(
                cuda.predictions_by_token[token][alpha],
                cpu.predictions_by_token[token][alpha],
                atol=1e-7,
                rtol=1e-7,
            )
    summed = standardized_token_kernel_sum_cuda(tokens, training_row_count=12)
    reference = sum(
        standardized_kernel_numpy(tokens[:12, token], tokens[:, token]).kernel
        for token in range(3)
    )
    assert np.allclose(summed.kernel, reference, atol=1e-7, rtol=1e-7)


def test_p7_and_predecessor_authorities_remain_byte_identical():
    authority = p7a.verify_authority()
    assert authority["manifest"]["trajectory_count"] == 120
    assert authority["split"]["train_test_overlap"] == 0
    assert authority["split"]["v1_primary_intersection"] == 0


def test_p7a_amendment_is_exact_training_only_and_material():
    audit = load("p7a_execution_optimization.json")
    benchmark = load("solver_benchmark.p7a.json")
    execution = load("execution_budget.p7a.lock.json")
    assert audit["status"] == "PASS_P7A_EXACT_EXECUTION_PLAN_OPTIMIZED"
    assert audit["execution_plan_changed"] is True
    assert audit["scientific_authority_changed"] is False
    assert audit["logical_budgets_unchanged"] is True
    assert audit["maximum_prediction_difference"] <= 1e-7
    assert benchmark["fixed_test_targets_used"] is False
    assert benchmark["fixed_test_predictions_computed"] is False
    assert benchmark["fixed_test_scores_opened"] is False
    assert benchmark["model_outcomes_used_for_optimization"] is False
    assert execution["token_batch_size"] == 4
    assert execution["wide_kernel_token_batch_size"] == 16
    assert execution["bounded_parallelism"] == 1
    assert execution["numerical_computation_dtype"] == "float64"
    assert execution["expected_machine_runtime"]["relative_reduction"] >= 0.20
    assert execution["host_memory_ceiling_bytes"] == 14 * (1 << 30)
    assert execution["gpu_memory_ceiling_bytes"] == 20 * (1 << 30)
    assert "subset_id/selection_fold" in execution["resume_granularity"]


def test_training_only_cache_is_reconstructable_and_excludes_fixed_test_rows():
    manifest = load("cache_manifest.p7a.json")
    cache_record = manifest["token_cache"]
    cache_path = Path(cache_record["path"])
    assert manifest["full_float32_cache_materialized"] is False
    assert manifest["reconstructable_cache_s3_upload_skipped"] is True
    assert cache_record["durability"] == "RECONSTRUCTABLE_NVME_ONLY"
    assert cache_path.is_file()
    cache = np.load(cache_path, mmap_mode="r", allow_pickle=False)
    assert cache.shape == (336, 6120, 2048)
    assert cache.dtype == np.float16
    assert cache_path.stat().st_size == cache_record["maximum_measured_byte_count"]


def test_no_p8_or_full_covariance_artifact_exists():
    source = (ROOT / "src/mineocclude/probes/p7a_execution.py").read_text()
    runner = SCRIPT.read_text()
    assert "688128 x 688128" not in source + runner
    assert "np.eye(FULL_DIM" not in source + runner
    assert not (PACKAGE / "learning_curve_results.json").exists()
    assert not (PACKAGE / "best_k_results.json").exists()
    assert not (PACKAGE / "target_null_results.json").exists()
    audit = load("p7a_execution_optimization.json")
    assert audit["p8_started"] is False
    assert audit["safe_for_p8"] is True


def test_focused_validate_only_contract_passes():
    p7a.validate_existing()
