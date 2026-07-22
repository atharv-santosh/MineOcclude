"""Raw-pixel ridge baseline.

Roadmap D2: "Raw pixel | Exact current preprocessed occluded frame |
Checks visual leakage or current-frame scene cues."

This baseline fits ``mu_oracle_blocks`` (only) from the exact current
frame's preprocessed pixels -- never activations, never other frames --
using the same leakage-safe layout-grouped ridge OOF machinery as the
explicit-feature ceiling and Person B's own probe
(:mod:`mineocclude.probes.ridge`). A well-above-floor score here is a
warning sign, not a positive result: it means the current occluded
frame's raw pixels alone carry decodable position information (a
visual-leakage or scene-cue confound), which the main probe's score
must be interpreted against, not something to be proud of.

Pixel data is not a field on ``TrajectoryContext`` -- that type is
Person D's legally-observable-scalar abstraction and stays that way
(see interface.py). Pixel features are supplied by the caller as an
explicit frame-key -> feature-vector mapping, already flattened/
downsampled through whatever preprocessing pipeline produced them, so
this module never has to invent its own image handling.
"""

from __future__ import annotations

from typing import Mapping, Sequence, Tuple

from mineocclude.baselines.interface import BaselineRow, TrajectoryContext, make_baseline_row
from mineocclude.probes.ridge import fit_ridge_oof

BASELINE_NAME = "raw_pixel"

RowKey = Tuple[str, int]
"""Authoritative ``(trajectory_id, model_frame_idx)`` analysis identity."""


def fit_predict_raw_pixel(
    contexts: Sequence[TrajectoryContext],
    mu_oracle_by_key: Mapping[RowKey, float],
    pixel_features_by_key: Mapping[RowKey, Sequence[float]],
    *,
    alpha_grid: Sequence[float] = (0.1, 1.0, 10.0, 100.0),
    inner_fold_count: int = 4,
    seed: int = 20260719,
) -> list[BaselineRow]:
    """Fit the raw-pixel ridge baseline with leakage-safe OOF folds.

    Applicable only for frames with both a pixel feature vector and an
    oracle-mean fit target. Defines no spread prediction: a pointwise
    pixel feature carries no distributional claim, matching the
    explicit-feature ceiling's role split.
    """

    fit_contexts: list[TrajectoryContext] = []
    feature_rows: list[Sequence[float]] = []
    targets: list[float] = []
    applicable_keys: set[RowKey] = set()

    for ctx in contexts:
        key = (ctx.trajectory_id, ctx.model_frame_idx)
        features = pixel_features_by_key.get(key)
        target = mu_oracle_by_key.get(key)
        if features is None or target is None:
            continue
        fit_contexts.append(ctx)
        feature_rows.append(features)
        targets.append(target)
        applicable_keys.add(key)

    predictions_by_key: dict[RowKey, float] = {}
    fit_metadata_by_key: dict[RowKey, dict[str, object]] = {}

    if fit_contexts:
        result = fit_ridge_oof(
            feature_rows,
            targets,
            [ctx.fold for ctx in fit_contexts],
            [ctx.layout_id for ctx in fit_contexts],
            alpha_grid=alpha_grid,
            inner_fold_count=inner_fold_count,
            seed=seed,
        )
        alpha_by_fold = {
            fit.outer_fold_idx: fit.alpha_selection.selected_alpha
            for fit in result.fits
        }
        for ctx, prediction in zip(fit_contexts, result.predictions):
            key = (ctx.trajectory_id, ctx.model_frame_idx)
            predictions_by_key[key] = prediction
            fit_metadata_by_key[key] = {
                "selected_alpha": alpha_by_fold[ctx.fold],
                "feature_dim": len(pixel_features_by_key[key]),
                "held_out_fold": ctx.fold,
            }

    rows: list[BaselineRow] = []
    for ctx in contexts:
        key = (ctx.trajectory_id, ctx.model_frame_idx)
        applicable = key in applicable_keys
        rows.append(
            make_baseline_row(
                ctx,
                baseline_name=BASELINE_NAME,
                target_name="mu_oracle_blocks",
                prediction=predictions_by_key.get(key) if applicable else None,
                applicable=applicable,
                fit_metadata=(
                    fit_metadata_by_key.get(key, {})
                    if applicable
                    else {"reason": "missing pixel features or oracle-mean fit target"}
                ),
            )
        )
        rows.append(
            make_baseline_row(
                ctx,
                baseline_name=BASELINE_NAME,
                target_name="log_sigma_oracle",
                prediction=None,
                applicable=False,
                fit_metadata={
                    "reason": "raw-pixel baseline defines no spread prediction"
                },
            )
        )
    return rows
