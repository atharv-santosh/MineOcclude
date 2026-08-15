"""Narrow unit tests for the P1 invariants that would silently corrupt the science.

Scope is deliberately tight: causal last-seen indexing, metadata-only matching,
trajectory-grouped bootstrap, and join/row identity. Run with:

    PYTHONPATH=scripts/regime_a_prime_qualification_v0_1 \
        python -m pytest scripts/regime_a_prime_qualification_v0_1/test_p1_invariants.py -q
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from p1_common import (
    CONF,
    EFFECTIVE_PRECEDING,
    OUT,
    PM,
    build_rows,
    trajectory_bootstrap,
)
from p1c_visible_vs_short import build_match_manifest


@pytest.fixture(scope="module")
def table() -> pd.DataFrame:
    return build_rows()


# --- LAST_SEEN_CAUSAL_INDEXING ------------------------------------------------

def test_last_seen_frame_is_strictly_prior_to_target(table):
    evid = table[table["any_rendered_pixel_evidence"]]
    assert (evid["last_rendered_evidence_frame"] < evid["model_frame_idx"]).all()
    assert (evid["frames_since_last_rendered_evidence"] >= 1).all()


def test_last_seen_frame_is_inside_the_frozen_model_input_window(table):
    evid = table[table["any_rendered_pixel_evidence"]]
    lower = evid["model_frame_idx"] - EFFECTIVE_PRECEDING
    assert (evid["last_rendered_evidence_frame"] >= lower).all()
    assert (evid["frames_since_last_rendered_evidence"] <= EFFECTIVE_PRECEDING).all()


def test_no_future_frame_is_ever_consulted(table):
    """The clean-visible baseline must obey the same causal bound."""
    clean = table[table["any_clean_visible"]]
    assert (clean["last_clean_visible_frame"] < clean["model_frame_idx"]).all()


def test_causal_indexing_reconciles_with_frozen_postmortem_d2(table):
    """Independent reconstruction must equal the postmortem's stored columns."""
    d2 = pd.read_parquet(PM / "d2_context_visibility.parquet")
    merged = table.merge(
        d2[["trajectory_id", "tau", "frames_since_last_rendered_evidence",
            "frames_since_last_clean_visible", "n_rendered_pixel_evidence",
            "n_clean_visible"]],
        on=["trajectory_id", "tau"], suffixes=("_p1", "_d2"),
    )
    assert len(merged) == 475
    for base in ("frames_since_last_rendered_evidence", "frames_since_last_clean_visible",
                 "n_rendered_pixel_evidence", "n_clean_visible"):
        a, b = merged[f"{base}_p1"], merged[f"{base}_d2"]
        assert ((a == b) | (a.isna() & b.isna())).all(), base


def test_target_frame_never_carries_rendered_evidence(table):
    """A baseline reading the target frame would be an oracle, not a baseline."""
    assert (table["frames_since_last_rendered_evidence"].dropna() > 0).all()


# --- ROW_IDENTITY / TRAJECTORY_ID RECONCILIATION ------------------------------

def test_row_and_trajectory_identity_match_frozen_package(table):
    preds = pd.read_parquet(CONF / "slice_predictions.parquet")
    assert len(table) == len(preds) == 475
    assert table["trajectory_id"].nunique() == 25
    key = ["trajectory_id", "tau"]
    assert set(map(tuple, table[key].values)) == set(map(tuple, preds[key].values))
    joined = table.merge(preds, on=key, suffixes=("_p1", "_frozen"))
    assert len(joined) == 475
    for column in ("world_x", "predicted_layer4_best_k", "model_frame_idx",
                   "activation_row", "server_tick", "outer_fold"):
        assert (joined[f"{column}_p1"] == joined[f"{column}_frozen"]).all(), column


def test_frozen_predictions_are_reused_not_recomputed(table):
    """The BEST-K column must be byte-equal to the frozen package column."""
    preds = pd.read_parquet(CONF / "slice_predictions.parquet")
    a = table.sort_values(["trajectory_id", "tau"])["predicted_layer4_best_k"].to_numpy()
    b = preds.sort_values(["trajectory_id", "tau"])["predicted_layer4_best_k"].to_numpy()
    assert np.array_equal(a, b)


# --- METADATA_ONLY_MATCHING ---------------------------------------------------

def test_match_manifest_is_invariant_to_outcome_columns(table):
    """Perturbing every prediction column must not change the manifest."""
    visible = pd.DataFrame(
        json.loads((PM / "visible_positive_control_manifest.json").read_text())["rows"]
    )
    short = table[table["duration_bin"] == "SHORT"].copy()
    baseline = build_match_manifest(visible, short)

    perturbed = short.copy()
    rng = np.random.default_rng(7)
    for column in [c for c in perturbed.columns if c.startswith("predicted_")]:
        perturbed[column] = rng.normal(size=len(perturbed)) * 1e6
    perturbed["world_x_outcome_noise"] = rng.normal(size=len(perturbed))
    after = build_match_manifest(visible, perturbed)

    assert baseline["manifest_integrity_sha256"] == after["manifest_integrity_sha256"]


def test_match_manifest_pairs_equal_boundary_offsets(table):
    visible = pd.DataFrame(
        json.loads((PM / "visible_positive_control_manifest.json").read_text())["rows"]
    )
    short = table[table["duration_bin"] == "SHORT"].copy()
    manifest = build_match_manifest(visible, short)
    assert manifest["matched_pair_count"] == 100
    assert manifest["matched_trajectory_count"] == 25
    for pair in manifest["pairs"]:
        assert pair["short_row_identity"]["tau"] == pair["boundary_offset_k"]
        assert 1 <= pair["boundary_offset_k"] <= 4
    assert all(u["reason"] for u in manifest["unmatched"])


def test_matching_is_deterministic(table):
    visible = pd.DataFrame(
        json.loads((PM / "visible_positive_control_manifest.json").read_text())["rows"]
    )
    short = table[table["duration_bin"] == "SHORT"].copy()
    first = build_match_manifest(visible, short)
    second = build_match_manifest(visible.sample(frac=1, random_state=3), short)
    assert first["manifest_integrity_sha256"] == second["manifest_integrity_sha256"]


# --- TRAJECTORY_GROUPED_BOOTSTRAP ---------------------------------------------

def test_bootstrap_resamples_whole_trajectories_only():
    values = {f"t{i:02d}": float(i) for i in range(1, 26)}
    result = trajectory_bootstrap(values, seed=1, resamples=500)
    assert result["resampling_unit"] == "WHOLE_TRAJECTORY"
    assert result["frame_level_resampling"] is False
    assert result["n_units_resampled"] == 25
    assert result["point_estimate"] == pytest.approx(np.mean(list(values.values())))
    assert result["ci95_low"] <= result["point_estimate"] <= result["ci95_high"]


def test_bootstrap_is_deterministic_under_fixed_seed():
    values = {f"t{i:02d}": float(i % 7) for i in range(1, 26)}
    a = trajectory_bootstrap(values, seed=42, resamples=1000)
    b = trajectory_bootstrap(values, seed=42, resamples=1000)
    assert a == b
    c = trajectory_bootstrap(values, seed=43, resamples=1000)
    assert (a["ci95_low"], a["ci95_high"]) != (c["ci95_low"], c["ci95_high"])


def test_bootstrap_ci_is_insensitive_to_within_trajectory_ordering():
    """Trajectory keys are sorted internally, so input order cannot matter."""
    values = {f"t{i:02d}": float(i) for i in range(1, 26)}
    shuffled = dict(reversed(list(values.items())))
    assert trajectory_bootstrap(values, seed=5) == trajectory_bootstrap(shuffled, seed=5)


# --- OUTPUT INTEGRITY ---------------------------------------------------------

def test_generated_p1_json_parses_and_declares_scope():
    for name in ("p1_input_binding.json", "p1_matching_manifest.json",
                 "p1_best_k_vs_last_seen.json", "p1_visible_vs_short.json",
                 "p1_displacement_diagnostic.json"):
        payload = json.loads((OUT / name).read_text())
        assert payload["phase"] == "P1"


# --- EXACT_ROW_LEVEL_VISIBLE_SCORING LABELLING --------------------------------

UNSUPPORTED = "UNSUPPORTED_FROM_PERSISTED_PREDICTIONS"
PINNED_MANIFEST_INTEGRITY = (
    "9e441b7287e8d3f7dcf4a9273be0ff4fd6ab369e44fb1ed8558a5f0ccedec3fb"
)


def test_matching_decisions_survive_the_relabelling():
    """Schema labels may be added; matching decisions may not change."""
    manifest = json.loads((OUT / "p1_matching_manifest.json").read_text())
    assert manifest["manifest_integrity_sha256"] == PINNED_MANIFEST_INTEGRITY
    assert manifest["matched_pair_count"] == 100
    assert manifest["unmatched_count"] == 100
    assert manifest["matched_trajectory_count"] == 25


def test_visible_row_level_scoring_is_declared_unsupported():
    manifest = json.loads((OUT / "p1_matching_manifest.json").read_text())
    payload = json.loads((OUT / "p1_visible_vs_short.json").read_text())
    assert manifest["scoring_support"][
        "exact_row_level_visible_scoring_status"] == UNSUPPORTED
    assert manifest["scoring_support"][
        "these_pairs_were_not_used_to_compute_any_visible_rmse"] is True
    assert payload["exact_row_level_visible_scoring_status"] == UNSUPPORTED
    assert payload["sub_analysis_status"] == "PARTIAL_UNSUPPORTED_ROW_LEVEL_SCORING"
    assert payload["status"] == "PASS"


def test_d6_visible_window_is_never_labelled_as_matched_rows():
    """The 0.1098 figure must be named by its true population everywhere."""
    payload = json.loads((OUT / "p1_visible_vs_short.json").read_text())
    side = payload["d6_visible_window_side"]
    assert side["is_the_100_matched_visible_rows"] is False
    assert side["rows_per_trajectory"] == 8
    assert "d6_visible_window_trajectory_equal_rmse_blocks" in side
    # The ambiguous names must be gone.
    assert "visible_side" not in payload
    assert "visible_vs_short_trajectory_paired" not in payload
    assert "visible_vs_matched_span_hidden" not in payload
    for key in side:
        assert not key.startswith("trajectory_equal_"), key


def test_report_cannot_be_read_as_matched_row_visible_rmse():
    """Every appearance of the D6 figure must name its true population."""
    report = (OUT / "p1_report.md").read_text()
    payload = json.loads((OUT / "p1_visible_vs_short.json").read_text())
    assert UNSUPPORTED in report
    assert "PARTIAL_UNSUPPORTED_ROW_LEVEL_SCORING" in report

    value = "{:.4f}".format(payload["d6_visible_window_side"][
        "d6_visible_window_trajectory_equal_rmse_blocks"])
    lines = [ln for ln in report.splitlines() if value in ln]
    assert lines, f"{value} absent from report"
    for line in lines:
        assert "D6 visible-window" in line, line


def test_receipt_separates_matched_pairs_from_scored_pairs():
    receipt = json.loads((OUT / "p1_receipt.json").read_text())
    counts = receipt["counts"]
    assert counts["metadata_matched_visible_short_pairs"] == 100
    assert counts["metadata_matched_visible_short_pairs_row_level_scored"] == 0
    assert "matched_visible_short_pairs" not in counts
    sub = receipt["visible_vs_short_sub_analysis"]
    assert sub["exact_row_level_visible_scoring_status"] == UNSUPPORTED
    assert sub["no_visible_rmse_derived_from_matched_pairs"] is True
    # The overall receipt status is asserted by p1_finalize itself, not here:
    # p1_finalize invokes these tests before writing the receipt, so asserting
    # it here would read the previous run's artifact.
