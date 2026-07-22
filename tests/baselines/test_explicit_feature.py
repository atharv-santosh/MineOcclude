"""Tests for the explicit-feature ceiling baseline."""

from __future__ import annotations

import math

from mineocclude.baselines.explicit_feature import (
    FEATURE_NAMES,
    fit_predict_explicit_feature,
)
from tests.baselines.conftest import build_trajectory_contexts

# Four layouts with distinct visible-window speeds, enough for a
# layout-grouped outer/inner ridge fit (outer n_splits=2, inner=2 needs
# at least 2 layouts left after removing the outer-test layout).
_LAYOUT_SPECS = {
    "layout-1": (0.0, 1.0, 2.0),
    "layout-2": (0.0, 2.0, 4.0),
    "layout-3": (0.0, 1.5, 3.0),
    "layout-4": (0.0, 0.5, 1.0),
}


def _build_contexts_with_oracle_targets():
    contexts = []
    mu_oracle_by_key: dict[tuple[str, int], float] = {}
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
            if ctx.last_seen_velocity_blocks_per_s is not None:
                key = (ctx.trajectory_id, ctx.model_frame_idx)
                # Synthetic oracle mean consistent with the estimated
                # velocity, so a correctly-fit ridge should track it well.
                mu_oracle_by_key[key] = last_seen + velocity * ctx.tau_seconds
    return contexts, mu_oracle_by_key


def test_fit_predict_explicit_feature_produces_oof_predictions_for_fittable_rows():
    contexts, mu_oracle_by_key = _build_contexts_with_oracle_targets()

    rows = fit_predict_explicit_feature(
        contexts,
        mu_oracle_by_key,
        alpha_grid=(0.1, 1.0, 10.0),
        inner_fold_count=2,
    )

    mu_rows = [row for row in rows if row.target_name == "mu_oracle_blocks"]
    log_sigma_rows = [row for row in rows if row.target_name == "log_sigma_oracle"]

    # log_sigma is never applicable: this is a pointwise ceiling only.
    assert all(not row.applicable and row.prediction is None for row in log_sigma_rows)

    applicable_mu_rows = [row for row in mu_rows if row.applicable]
    # Every context has velocity defined (2nd visible frame onward), so
    # every row except the very first frame per trajectory is applicable.
    assert applicable_mu_rows
    for row in applicable_mu_rows:
        assert row.prediction is not None and math.isfinite(row.prediction)
        assert row.fit_metadata["feature_names"] == list(FEATURE_NAMES)

    # The never-seen-velocity first frame of each trajectory must be
    # marked non-applicable, never scored as if prediction == 0.
    inapplicable_mu_rows = [row for row in mu_rows if not row.applicable]
    assert inapplicable_mu_rows
    assert all(row.prediction is None for row in inapplicable_mu_rows)


def test_fit_predict_explicit_feature_never_touches_scripted_v_or_q():
    contexts, mu_oracle_by_key = _build_contexts_with_oracle_targets()
    # Poison every context's scripted fields with an obviously wrong
    # value; if the baseline is honest, predictions must not change,
    # because _features_for never reads v_scripted/q_scripted.
    from dataclasses import replace

    poisoned = [
        replace(ctx, v_scripted_blocks_per_s=999.0, q_scripted_blocks2_per_s=999.0)
        for ctx in contexts
    ]

    clean_rows = fit_predict_explicit_feature(
        contexts, mu_oracle_by_key, alpha_grid=(1.0,), inner_fold_count=2
    )
    poisoned_rows = fit_predict_explicit_feature(
        poisoned, mu_oracle_by_key, alpha_grid=(1.0,), inner_fold_count=2
    )

    clean_predictions = [
        row.prediction for row in clean_rows if row.target_name == "mu_oracle_blocks"
    ]
    poisoned_predictions = [
        row.prediction for row in poisoned_rows if row.target_name == "mu_oracle_blocks"
    ]
    assert clean_predictions == poisoned_predictions
