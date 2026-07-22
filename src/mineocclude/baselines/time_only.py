"""Time-only ("is it just a clock?") baseline.

Roadmap D2: "Time only | tau and declared tau^2 sensitivity | Tests
whether uncertainty decoding is just a clock; receives no q, speed,
pixels, state, or activations."

This baseline fits ``log_sigma ~ poly(tau, degree)`` by ordinary least
squares using *only* rows from folds other than the one being
predicted (grouped hold-out, matching Person B's layout-grouped CV
discipline in D1.3: "Any learned preprocessing ... happens inside the
outer training fold"). It defines no mean prediction at all -- tau
alone carries zero positional information, so a mean prediction would
have to smuggle in something else.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Mapping, Sequence, Tuple

import numpy as np

from mineocclude.baselines.interface import BaselineRow, TrajectoryContext, make_baseline_row

BASELINE_NAME = "time_only"

RowKey = Tuple[str, int]
"""Authoritative ``(trajectory_id, model_frame_idx)`` analysis identity."""


def fit_predict_time_only(
    contexts: Sequence[TrajectoryContext],
    train_log_sigma: Mapping[RowKey, float],
    *,
    degree: int = 1,
) -> list[BaselineRow]:
    """Predict log_sigma from tau alone, fit per held-out fold.

    ``degree=1`` fits an intercept + linear tau term; ``degree=2``
    exercises the roadmap's "declared tau^2 sensitivity" variant. Only
    hidden-target rows (``visibility is False``) are applicable, since
    the oracle only defines a spread while the target is occluded.
    """

    if degree < 1:
        raise ValueError(f"degree must be >= 1, got {degree}")

    contexts_by_fold: dict[int, list[TrajectoryContext]] = defaultdict(list)
    for ctx in contexts:
        contexts_by_fold[ctx.fold].append(ctx)

    rows: list[BaselineRow] = []
    for fold, fold_contexts in contexts_by_fold.items():
        train_taus: list[float] = []
        train_targets: list[float] = []
        for ctx in contexts:
            if ctx.fold == fold:
                continue  # held out -- never used to fit this fold's predictions
            key = (ctx.trajectory_id, ctx.model_frame_idx)
            if key in train_log_sigma:
                train_taus.append(ctx.tau_seconds)
                train_targets.append(train_log_sigma[key])

        coeffs = None
        if len(train_taus) >= degree + 1:
            coeffs = np.polyfit(np.asarray(train_taus), np.asarray(train_targets), degree)

        train_row_count = len(train_taus)
        for ctx in fold_contexts:
            applicable = coeffs is not None and not ctx.visibility
            prediction = float(np.polyval(coeffs, ctx.tau_seconds)) if applicable else None
            rows.append(
                make_baseline_row(
                    ctx,
                    baseline_name=BASELINE_NAME,
                    target_name="log_sigma_oracle",
                    prediction=prediction,
                    applicable=applicable,
                    fit_metadata={
                        "degree": degree,
                        "held_out_fold": fold,
                        "train_row_count": train_row_count,
                    }
                    if applicable
                    else {
                        "degree": degree,
                        "held_out_fold": fold,
                        "train_row_count": train_row_count,
                        "reason": (
                            "target is visible (no spread defined)"
                            if coeffs is not None
                            else "insufficient training rows to fit"
                        ),
                    },
                )
            )
            rows.append(
                make_baseline_row(
                    ctx,
                    baseline_name=BASELINE_NAME,
                    target_name="mu_oracle_blocks",
                    prediction=None,
                    applicable=False,
                    fit_metadata={"reason": "tau alone carries no positional information"},
                )
            )
    return rows
