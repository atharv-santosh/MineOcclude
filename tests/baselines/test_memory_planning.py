"""Tests for the deterministic, non-scientific memory-plan preflight.

Covers the repair of the confirmed production OOM (exit 137, 437,391,360
raw_pixel feature values boxed as Python floats, >=13.035 GiB before any
family fit) -- this module never fits a baseline, computes a metric, or
reads real frame/capture data anywhere in this file.
"""

from __future__ import annotations

import pytest

from mineocclude.baselines.memory_planning import (
    COMPACT_FEATURE_ITEMSIZE_BYTES,
    RIDGE_WORKING_DTYPE_ITEMSIZE_BYTES,
    MemoryPlanError,
    build_raw_pixel_memory_plan,
    detect_host_memory,
    estimate_raw_pixel_ridge_working_copy_bytes,
)

#: The real Step 4.1 production shape: 1,695 admitted frames, 258,048
#: (3x224x384) float32 values each -- 437,391,360 total, matching the
#: confirmed incident report exactly.
REAL_ROW_COUNT = 1695
REAL_FEATURE_DIM = 3 * 224 * 384
REAL_OUTER_FOLD_ROW_COUNTS = [292, 409, 387, 272, 335]
REAL_INNER_FOLD_COUNT = 4


def test_feature_dim_times_row_count_matches_the_confirmed_incident_report():
    assert REAL_ROW_COUNT * REAL_FEATURE_DIM == 437_391_360


def test_detect_host_memory_returns_a_plausible_physical_value():
    host = detect_host_memory()
    assert set(host) == {"physical_bytes", "available_bytes"}
    # POSIX sysconf on Linux/macOS, Win32 GlobalMemoryStatusEx on Windows:
    # detection must succeed on any machine running this suite, so a
    # `host_memory_undetected` plan rejection always means a real budget
    # shortfall rather than an unportable probe.
    assert isinstance(host["physical_bytes"], int)
    assert host["physical_bytes"] > 0
    assert host["available_bytes"] is None or isinstance(host["available_bytes"], int)


def test_estimate_reports_compact_and_upcast_bytes_for_the_real_shape():
    breakdown = estimate_raw_pixel_ridge_working_copy_bytes(
        row_count=REAL_ROW_COUNT,
        feature_dim=REAL_FEATURE_DIM,
        outer_fold_row_counts=REAL_OUTER_FOLD_ROW_COUNTS,
        inner_fold_count=REAL_INNER_FOLD_COUNT,
    )
    expected_compact = REAL_ROW_COUNT * REAL_FEATURE_DIM * COMPACT_FEATURE_ITEMSIZE_BYTES
    expected_upcast = REAL_ROW_COUNT * REAL_FEATURE_DIM * RIDGE_WORKING_DTYPE_ITEMSIZE_BYTES
    assert breakdown["compact_source_bytes"] == expected_compact
    assert breakdown["upcast_matrix_bytes"] == expected_upcast
    # ~1.63 GiB compact, matching the confirmed-incident report's own
    # "approximately 1.63 GiB" mention of the primary float32 matrix.
    assert expected_compact / (1024**3) == pytest.approx(1.629, abs=0.01)
    # Every subsequent working-copy layer must be smaller than the full
    # upcast matrix (each is a strict subset of training rows).
    assert 0 < breakdown["outer_training_bytes"] < expected_upcast
    assert 0 < breakdown["inner_training_bytes"] < breakdown["outer_training_bytes"]
    assert breakdown["outer_standardized_bytes"] == breakdown["outer_training_bytes"]
    assert breakdown["inner_standardized_bytes"] == breakdown["inner_training_bytes"]
    assert breakdown["working_copy_bytes"] == (
        breakdown["upcast_matrix_bytes"]
        + breakdown["outer_training_bytes"]
        + breakdown["outer_standardized_bytes"]
        + breakdown["inner_training_bytes"]
        + breakdown["inner_standardized_bytes"]
    )


def test_estimate_uses_the_smallest_test_fold_for_the_largest_training_split():
    # Excluding the smallest fold (272 rows) as the held-out test fold
    # yields the largest possible outer-training set (1423 rows) --
    # the conservative (largest) working-copy scenario.
    breakdown = estimate_raw_pixel_ridge_working_copy_bytes(
        row_count=REAL_ROW_COUNT,
        feature_dim=REAL_FEATURE_DIM,
        outer_fold_row_counts=REAL_OUTER_FOLD_ROW_COUNTS,
        inner_fold_count=REAL_INNER_FOLD_COUNT,
    )
    upcast = REAL_ROW_COUNT * REAL_FEATURE_DIM * RIDGE_WORKING_DTYPE_ITEMSIZE_BYTES
    expected_outer_training = int(upcast * (1695 - 272) / 1695)
    assert breakdown["outer_training_bytes"] == expected_outer_training


@pytest.mark.parametrize(
    "kwargs",
    [
        {"row_count": 0, "feature_dim": 10, "outer_fold_row_counts": [0], "inner_fold_count": 4},
        {"row_count": 10, "feature_dim": 0, "outer_fold_row_counts": [10], "inner_fold_count": 4},
        {"row_count": 10, "feature_dim": 5, "outer_fold_row_counts": [], "inner_fold_count": 4},
        {"row_count": 10, "feature_dim": 5, "outer_fold_row_counts": [3, 3], "inner_fold_count": 4},
        {"row_count": 10, "feature_dim": 5, "outer_fold_row_counts": [10], "inner_fold_count": 1},
    ],
)
def test_estimate_rejects_inconsistent_inputs(kwargs):
    with pytest.raises(MemoryPlanError):
        estimate_raw_pixel_ridge_working_copy_bytes(**kwargs)


def test_build_raw_pixel_memory_plan_reports_feature_value_count_and_dtype():
    plan = build_raw_pixel_memory_plan(
        row_count=REAL_ROW_COUNT,
        feature_dim=REAL_FEATURE_DIM,
        outer_fold_row_counts=REAL_OUTER_FOLD_ROW_COUNTS,
        inner_fold_count=REAL_INNER_FOLD_COUNT,
        host_memory={"physical_bytes": 1024**4, "available_bytes": None},
    )
    assert plan.feature_value_count == 437_391_360
    assert plan.source_dtype == "float32"
    assert plan.compact_payload_bytes == 437_391_360 * 4


def test_build_raw_pixel_memory_plan_admits_when_budget_is_ample():
    plan = build_raw_pixel_memory_plan(
        row_count=REAL_ROW_COUNT,
        feature_dim=REAL_FEATURE_DIM,
        outer_fold_row_counts=REAL_OUTER_FOLD_ROW_COUNTS,
        inner_fold_count=REAL_INNER_FOLD_COUNT,
        host_memory={"physical_bytes": 64 * 1024**3, "available_bytes": None},
    )
    assert plan.admitted is True
    assert plan.reasons == ()


def test_build_raw_pixel_memory_plan_rejects_when_budget_is_insufficient():
    plan = build_raw_pixel_memory_plan(
        row_count=REAL_ROW_COUNT,
        feature_dim=REAL_FEATURE_DIM,
        outer_fold_row_counts=REAL_OUTER_FOLD_ROW_COUNTS,
        inner_fold_count=REAL_INNER_FOLD_COUNT,
        host_memory={"physical_bytes": 2 * 1024**3, "available_bytes": None},
    )
    assert plan.admitted is False
    assert any("exceeds" in reason for reason in plan.reasons)


def test_build_raw_pixel_memory_plan_prefers_available_over_physical_when_known():
    plan = build_raw_pixel_memory_plan(
        row_count=REAL_ROW_COUNT,
        feature_dim=REAL_FEATURE_DIM,
        outer_fold_row_counts=REAL_OUTER_FOLD_ROW_COUNTS,
        inner_fold_count=REAL_INNER_FOLD_COUNT,
        host_memory={"physical_bytes": 64 * 1024**3, "available_bytes": 1 * 1024**3},
    )
    assert plan.admitted is False


def test_build_raw_pixel_memory_plan_fails_closed_when_host_memory_undetected():
    plan = build_raw_pixel_memory_plan(
        row_count=REAL_ROW_COUNT,
        feature_dim=REAL_FEATURE_DIM,
        outer_fold_row_counts=REAL_OUTER_FOLD_ROW_COUNTS,
        inner_fold_count=REAL_INNER_FOLD_COUNT,
        host_memory={"physical_bytes": None, "available_bytes": None},
    )
    assert plan.admitted is False
    assert "host_memory_undetected" in plan.reasons


def test_the_real_shape_estimated_peak_matches_hand_derived_value():
    """Documents the exact honest estimate this repair produces for the
    real Step 4.1 shape -- the number reported to Person B for
    reauthorization, not just an internal implementation detail."""

    plan = build_raw_pixel_memory_plan(
        row_count=REAL_ROW_COUNT,
        feature_dim=REAL_FEATURE_DIM,
        outer_fold_row_counts=REAL_OUTER_FOLD_ROW_COUNTS,
        inner_fold_count=REAL_INNER_FOLD_COUNT,
        host_memory={"physical_bytes": 1024**4, "available_bytes": None},
    )
    assert plan.estimated_peak_gib == pytest.approx(14.96, abs=0.05)
