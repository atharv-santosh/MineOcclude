"""Focused regression checks for bounded-repair forensic receipts."""

import json
from pathlib import Path

import numpy as np
import pytest
from scipy.stats import t


ROOT = Path(__file__).resolve().parents[2]
FORENSIC = (
    ROOT
    / "docs/status/integration/regime_a_prime_qualification_v0_1"
    / "p2_temporal_alignment_forensic_v0_1"
)


def test_small_sample_t_interval_and_bootstrap_are_explicit():
    document = json.loads((FORENSIC / "impulse_response_raw.json").read_text())
    delays = np.asarray([row["group_delay"] for row in document["units"]])
    mean = delays.mean()
    half = t.ppf(0.975, len(delays) - 1) * delays.std(ddof=1) / np.sqrt(len(delays))
    assert document["group_delay_t_interval_95"] == pytest.approx(
        [mean - half, mean + half]
    )
    assert document["group_delay_trajectory_bootstrap_interval_95"] == pytest.approx(
        [3.2187625523392898, 3.522819291615068]
    )
    assert document["bootstrap"] == {
        "replicates": 100000,
        "seed": 20260816,
        "unit": "trajectory",
    }


def test_direct_regime_a_reanalysis_preserves_conclusion_without_bound():
    document = json.loads((FORENSIC / "regime_a_blast_radius.json").read_text())
    full = document["domains"]["FULL_TAU1_15"]
    assert document["regime_a_conclusion_stable"] is True
    assert document["corrected_primary_gate_still_fails"] is True
    assert full["neural_full_corrected"]["macro_r2"] < 0
    for neural in ("neural_full_corrected", "neural_best_k_corrected"):
        neural_rmse = full[neural]["trajectory_aggregated_rmse"]
        assert full["time_only_corrected"]["trajectory_aggregated_rmse"] < neural_rmse
        assert full["training_mean_corrected"]["trajectory_aggregated_rmse"] < neural_rmse


def test_short_last_seen_comparison_materially_flips_when_target_is_fixed():
    document = json.loads((FORENSIC / "regime_a_blast_radius.json").read_text())
    short = document["historical_target_last_seen_sensitivity"]["SHORT"]
    neural = short["neural_best_k_historical"]["trajectory_aggregated_rmse"]
    historical = short["last_seen_historical_logged"]["trajectory_aggregated_rmse"]
    corrected = short["last_seen_fir_corrected_depicted"]["trajectory_aggregated_rmse"]
    assert historical < neural < corrected
    assert corrected - historical > 0.25
