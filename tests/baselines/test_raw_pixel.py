"""Tests for the raw-pixel ridge baseline."""

from __future__ import annotations

import math

from mineocclude.baselines.raw_pixel import fit_predict_raw_pixel
from tests.baselines.conftest import build_trajectory_contexts

_LAYOUT_SPECS = {
    "layout-1": (0.0, 1.0, 2.0),
    "layout-2": (0.0, 2.0, 4.0),
    "layout-3": (0.0, 1.5, 3.0),
    "layout-4": (0.0, 0.5, 1.0),
}


def _build_fixture():
    contexts = []
    mu_oracle_by_key: dict[tuple[str, int], float] = {}
    pixel_features_by_key: dict[tuple[str, int], list[float]] = {}

    for fold, (layout_id, positions) in enumerate(_LAYOUT_SPECS.items()):
        layout_contexts = build_trajectory_contexts(
            trajectory_id=f"traj-{layout_id}",
            layout_id=layout_id,
            fold=fold % 2,
            visible_positions=positions,
            dt=1.0,
            hidden_taus=(1.0, 2.0),
            duration_seconds=2.0,
        )
        contexts.extend(layout_contexts)
        velocity = layout_contexts[-1].last_seen_velocity_blocks_per_s
        last_seen = layout_contexts[-1].last_seen_position_blocks

        for ctx in layout_contexts:
            key = (ctx.trajectory_id, ctx.model_frame_idx)
            true_mu = last_seen + velocity * ctx.tau_seconds
            mu_oracle_by_key[key] = true_mu
            # Synthetic "pixel" feature that leaks position plus a
            # fixed decorative channel -- simulates a visual-leakage
            # scene cue a real occluded frame might contain.
            pixel_features_by_key[key] = [true_mu * 10.0, 1.0]

    return contexts, mu_oracle_by_key, pixel_features_by_key


def test_fit_predict_raw_pixel_fits_leaky_pixel_features():
    contexts, mu_oracle_by_key, pixel_features_by_key = _build_fixture()

    rows = fit_predict_raw_pixel(
        contexts,
        mu_oracle_by_key,
        pixel_features_by_key,
        alpha_grid=(0.1, 1.0, 10.0),
        inner_fold_count=2,
    )

    mu_rows = [row for row in rows if row.target_name == "mu_oracle_blocks"]
    log_sigma_rows = [row for row in rows if row.target_name == "log_sigma_oracle"]

    assert all(not row.applicable and row.prediction is None for row in log_sigma_rows)

    applicable_rows = [row for row in mu_rows if row.applicable]
    assert applicable_rows
    for row in applicable_rows:
        assert row.prediction is not None and math.isfinite(row.prediction)
        assert row.fit_metadata["feature_dim"] == 2


def test_fit_predict_raw_pixel_marks_missing_features_not_applicable():
    contexts, mu_oracle_by_key, pixel_features_by_key = _build_fixture()

    # Drop pixel features for one frame entirely -- must not silently
    # get scored, and must never fall back to zero.
    dropped_key = next(iter(pixel_features_by_key))
    del pixel_features_by_key[dropped_key]

    rows = fit_predict_raw_pixel(
        contexts,
        mu_oracle_by_key,
        pixel_features_by_key,
        alpha_grid=(1.0,),
        inner_fold_count=2,
    )

    dropped_rows = [
        row
        for row in rows
        if row.target_name == "mu_oracle_blocks"
        and (row.trajectory_id, row.model_frame_idx) == dropped_key
    ]
    assert len(dropped_rows) == 1
    assert not dropped_rows[0].applicable
    assert dropped_rows[0].prediction is None
