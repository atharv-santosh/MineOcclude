#!/usr/bin/env python3
"""Outcome-blind CPU, cache, and durability benchmarks for Regime-A A2."""

from __future__ import annotations

import json
import resource
import tempfile
import time
from pathlib import Path

import numpy as np

from mineocclude.regime_a import (
    FULL_DIMENSION,
    activation_bytes_per_trajectory,
    best_k_features,
    rank_best_k_tokens,
    ridge_fit_predict,
    simulate_path,
    verified_local_durable_copy,
)


def elapsed(call):
    start = time.perf_counter()
    value = call()
    return value, time.perf_counter() - start


def main() -> int:
    rng = np.random.default_rng(20260814)

    (_path, _noise), state_generation = elapsed(
        lambda: simulate_path(20260814, "LEFT_TO_RIGHT", -7.8, 260)
    )

    x_full, full_prepare = elapsed(lambda: rng.normal(size=(20, FULL_DIMENSION)).astype(np.float32))
    z_full = rng.normal(size=(5, FULL_DIMENSION)).astype(np.float32)
    y = rng.normal(size=20)
    full_prediction, full_fit = elapsed(lambda: ridge_fit_predict(x_full, y, z_full, 10.0))

    tensor = rng.normal(size=(20, 336, 2048)).astype(np.float32)
    heldout_tensor = rng.normal(size=(5, 336, 2048)).astype(np.float32)
    ranking, best_k_ranking = elapsed(lambda: rank_best_k_tokens(tensor, y))
    selected_train, best_k_prepare = elapsed(lambda: best_k_features(tensor, ranking, 128))
    selected_test = best_k_features(heldout_tensor, ranking, 128)
    best_k_prediction, best_k_fit = elapsed(lambda: ridge_fit_predict(selected_train, y, selected_test, 10.0))

    xc = selected_train.astype(np.float64) - selected_train.mean(axis=0, dtype=np.float64)
    zc = selected_test.astype(np.float64) - selected_train.mean(axis=0, dtype=np.float64)
    gram = xc @ xc.T + 10.0 * np.eye(xc.shape[0])
    donor = np.roll(y, 1)
    donor_centered = donor - donor.mean()
    cached_prediction, cached_null = elapsed(
        lambda: zc @ xc.T @ np.linalg.solve(gram, donor_centered) + donor.mean()
    )
    direct_prediction, direct_null = elapsed(
        lambda: ridge_fit_predict(selected_train, donor, selected_test, 10.0)
    )

    with tempfile.TemporaryDirectory(dir="/mnt/sagemaker-nvme") as temporary:
        temporary_root = Path(temporary)
        source = temporary_root / "source.bin"
        with source.open("wb") as stream:
            stream.truncate(64 * 1024 * 1024)
        durable_receipt, durable_seconds = elapsed(
            lambda: verified_local_durable_copy(source, temporary_root / "object" / "source.bin")
        )

    result = {
        "schema_version": "regime-a-a2-cpu-benchmark-v1.0",
        "status": "PASS",
        "scientific_data": False,
        "scientific_decoding": False,
        "state_geometry_trajectory_generation_seconds": state_generation,
        "exact_runtime_capture_reference_seconds": 3.0,
        "exact_runtime_capture_reference_frames": 60,
        "projected_260_frame_exact_runtime_capture_seconds": 13.0,
        "full_dimension": FULL_DIMENSION,
        "full_training_rows": 20,
        "full_heldout_rows": 5,
        "full_feature_preparation_seconds": full_prepare,
        "full_fit_seconds": full_fit,
        "best_k_ranking_seconds": best_k_ranking,
        "best_k_feature_preparation_seconds": best_k_prepare,
        "best_k_fit_seconds": best_k_fit,
        "best_k": 128,
        "cached_null_seconds": cached_null,
        "direct_null_seconds": direct_null,
        "cache_equivalence_max_abs_error": float(np.max(np.abs(cached_prediction - direct_prediction))),
        "cache_equivalence": bool(np.allclose(cached_prediction, direct_prediction, rtol=1e-10, atol=1e-10)),
        "finite_predictions": bool(np.isfinite(full_prediction).all() and np.isfinite(best_k_prediction).all()),
        "durable_copy_hash_seconds_64_mib": durable_seconds,
        "durable_copy_receipt": durable_receipt,
        "activation_bytes_per_trajectory": activation_bytes_per_trajectory(),
        "peak_cpu_ram_bytes_maxrss": int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024),
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
