"""Tests for the deferred random-weight MineWorld baseline interface."""

from __future__ import annotations

from mineocclude.baselines.random_weight import BASELINE_NAME, fit_predict_random_weight
from mineocclude.baselines.raw_pixel import (
    BASELINE_NAME as RAW_PIXEL_BASELINE_NAME,
    fit_predict_raw_pixel,
)
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
    activation_by_key: dict[tuple[str, int], list[float]] = {}

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
            # Stand-in "random-weight activation" -- an arbitrary small
            # vector, since no real random-weight checkpoint exists yet.
            activation_by_key[key] = [true_mu * 3.0, -1.0, 0.5]

    return contexts, mu_oracle_by_key, activation_by_key


def test_random_weight_baseline_matches_raw_pixel_fit_under_relabeling():
    contexts, mu_oracle_by_key, activation_by_key = _build_fixture()

    random_weight_rows = fit_predict_random_weight(
        contexts,
        mu_oracle_by_key,
        activation_by_key,
        alpha_grid=(0.1, 1.0, 10.0),
        inner_fold_count=2,
    )
    raw_pixel_rows = fit_predict_raw_pixel(
        contexts,
        mu_oracle_by_key,
        activation_by_key,
        alpha_grid=(0.1, 1.0, 10.0),
        inner_fold_count=2,
    )

    assert all(row.baseline_name == BASELINE_NAME for row in random_weight_rows)
    assert BASELINE_NAME != RAW_PIXEL_BASELINE_NAME

    random_weight_predictions = [row.prediction for row in random_weight_rows]
    raw_pixel_predictions = [row.prediction for row in raw_pixel_rows]
    assert random_weight_predictions == raw_pixel_predictions
