"""Explicit-feature ceiling baseline.

Roadmap D2: "Explicit features | Last-seen position, estimated speed,
elapsed time; declared interactions | Ceiling/reference for known
belief ingredients."

This predicts ``mu_oracle_blocks`` from a small set of legally
observable, declared features -- last-seen position, the *estimated*
visible-window velocity (never the privileged scripted ``v``), elapsed
hidden time (``tau``), and duration -- plus two fixed interaction
terms. It is fit with the same leakage-safe layout-grouped ridge OOF
machinery Person B uses for the real probe
(:mod:`mineocclude.probes.ridge`), so this ceiling is judged by the
same rules as the probe it is meant to bound, not a looser one.

The declared feature list below is fixed, not learned or searched.
Changing it (adding/removing an interaction, swapping in scripted
v/q) is a result-affecting change to baseline logic and requires A/B
review, per the project's ownership rules.
"""

from __future__ import annotations

from typing import Mapping, Sequence, Tuple

from mineocclude.baselines.interface import BaselineRow, TrajectoryContext, make_baseline_row
from mineocclude.probes.ridge import fit_ridge_oof

BASELINE_NAME = "explicit_feature"

RowKey = Tuple[str, int]
"""(trajectory_id, model_frame_idx), matching how oracle targets are
keyed until Person B's real schema is merged."""

#: Declared feature order. Changing this list is a result-affecting
#: baseline change (see module docstring).
FEATURE_NAMES: tuple[str, ...] = (
    "last_seen_position_blocks",
    "estimated_velocity_blocks_per_s",
    "tau_seconds",
    "duration_seconds",
    "velocity_times_tau",
    "velocity_times_duration",
)


def _features_for(ctx: TrajectoryContext) -> list[float] | None:
    """Return the declared feature row, or ``None`` if an input is missing."""

    position = ctx.last_seen_position_blocks
    velocity = ctx.last_seen_velocity_blocks_per_s
    duration = ctx.duration_seconds
    if position is None or velocity is None or duration is None:
        return None
    return [
        position,
        velocity,
        ctx.tau_seconds,
        duration,
        velocity * ctx.tau_seconds,
        velocity * duration,
    ]


def fit_predict_explicit_feature(
    contexts: Sequence[TrajectoryContext],
    mu_oracle_by_key: Mapping[RowKey, float],
    *,
    alpha_grid: Sequence[float] = (0.1, 1.0, 10.0, 100.0),
    inner_fold_count: int = 4,
    seed: int = 20260719,
) -> list[BaselineRow]:
    """Fit the explicit-feature ridge ceiling with leakage-safe OOF folds.

    ``mu_oracle_by_key`` supplies Person B's oracle-mean target for
    every frame that should enter fitting -- exactly the same
    supervisory role activations play for the real probe. A row is
    applicable only when every declared feature and a target are both
    available; this baseline defines no spread prediction, since a
    pointwise feature ceiling carries no distributional claim.
    """

    fit_contexts: list[TrajectoryContext] = []
    feature_rows: list[list[float]] = []
    targets: list[float] = []
    applicable_keys: set[RowKey] = set()

    for ctx in contexts:
        features = _features_for(ctx)
        key = (ctx.trajectory_id, ctx.model_frame_idx)
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
                "feature_names": list(FEATURE_NAMES),
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
                    else {
                        "reason": (
                            "missing last-seen position, estimated velocity, "
                            "duration, or oracle-mean fit target"
                        )
                    }
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
                    "reason": "explicit-feature ceiling defines no spread prediction"
                },
            )
        )
    return rows
