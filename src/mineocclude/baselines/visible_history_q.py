"""Visible-history-q spread baseline (fair, no privileged q).

Roadmap D2: "Visible-history spread | Only pre-occlusion visible
positions/actions; estimate q_hat within training data, then combine
with tau | Fair same-information spread baseline; no scripted q and
no hidden truth."

Person B, Day 4 (U2): "compare with... a fair visible-history baseline
that estimates q from pre-occlusion residuals inside each training
fold without scripted q or hidden truth."

For each held-out fold, this pools one-step position-increment
residuals (``x_(k+1) - x_k - v_hat*dt``, from a constant-velocity fit
over each trajectory's *own* visible window) across every trajectory in
the *other* folds, and estimates ``q_hat = var(residuals) / dt``. Every
hidden row in the held-out fold then receives
``log_sigma_hat = ln(sqrt(q_hat * tau))`` -- the oracle's own
``variance = q*tau`` form (docs/contracts/person_b_oracle_target_v0_1.md),
but with an estimated, not privileged, q. This mirrors time_only.py's
per-fold pooled-refit pattern so the two floors are judged the same way.
"""

from __future__ import annotations

import math
from typing import Mapping, Sequence

from mineocclude.baselines.interface import BaselineRow, TrajectoryContext, make_baseline_row

BASELINE_NAME = "visible_history_q"

REGIME_A_DT_SECONDS = 0.05

#: Stable identity of the estimator and of the exact legal feature this
#: baseline consumes. Recorded on every emitted row so a later audit can
#: confirm from the rows alone that no privileged input (scripted q,
#: hidden state, target truth) was ever in scope -- the estimator reads
#: one-step increments of the pre-occlusion visible position sequence and
#: nothing else.
ESTIMATOR_ID = "pooled_training_fold_visible_residual_variance_v0_1"
FEATURE_ID = "pre_occlusion_visible_position_increments_v0_1"


class VisibleHistoryQError(ValueError):
    """Raised when input contexts violate this baseline's fold invariants."""


def _trajectory_q_residuals(
    visible_positions: Sequence[float], dt_seconds: float
) -> list[float]:
    """One-step residuals from a constant-velocity fit over one
    trajectory's own visible window -- never another trajectory's,
    never hidden/occluded truth."""

    if len(visible_positions) < 3:
        return []
    steps = [
        (visible_positions[i + 1] - visible_positions[i]) / dt_seconds
        for i in range(len(visible_positions) - 1)
    ]
    mean_velocity = sum(steps) / len(steps)
    return [
        visible_positions[i + 1] - visible_positions[i] - mean_velocity * dt_seconds
        for i in range(len(visible_positions) - 1)
    ]


def fit_predict_visible_history_q(
    contexts: Sequence[TrajectoryContext],
    visible_positions_by_trajectory: Mapping[str, Sequence[float]],
    *,
    dt_seconds: float = REGIME_A_DT_SECONDS,
) -> list[BaselineRow]:
    """Predict ``log_sigma_oracle`` from a per-fold, training-only q_hat.

    Applicable only for hidden rows (``visibility`` is ``False``)
    whose fold has at least one pooled training-fold residual pair;
    defines no mean prediction -- q_hat and tau alone carry no
    positional information, matching time_only.py's role split.

    Raises :class:`VisibleHistoryQError` if any trajectory's contexts
    disagree on ``fold`` -- B's layout-grouped folds mean one
    trajectory can never legitimately span two folds, so silently
    taking whichever fold value appeared first (as this function used
    to) would mask a real upstream data bug instead of surfacing it.
    """

    trajectory_fold: dict[str, int] = {}
    for ctx in contexts:
        existing_fold = trajectory_fold.setdefault(ctx.trajectory_id, ctx.fold)
        if existing_fold != ctx.fold:
            raise VisibleHistoryQError(
                f"trajectory {ctx.trajectory_id!r} has conflicting fold "
                f"assignments ({existing_fold} vs {ctx.fold}); one trajectory "
                "must belong to exactly one fold"
            )

    unknown_trajectories = sorted(
        set(visible_positions_by_trajectory) - set(trajectory_fold)
    )
    if unknown_trajectories:
        raise VisibleHistoryQError(
            f"visible history supplied for trajectories {unknown_trajectories} "
            "that carry no fold assignment in the requested rows; a trajectory "
            "with no authoritative fold cannot be safely pooled into any "
            "training fold, and silently dropping it would change the fit "
            "without any record of it"
        )

    residuals_by_trajectory: dict[str, list[float]] = {
        trajectory_id: _trajectory_q_residuals(positions, dt_seconds)
        for trajectory_id, positions in visible_positions_by_trajectory.items()
    }

    q_hat_by_fold: dict[int, float] = {}
    fit_provenance_by_fold: dict[int, dict[str, object]] = {}
    for held_out_fold in sorted(set(trajectory_fold.values())):
        pooled_residuals: list[float] = []
        training_trajectory_ids: list[str] = []
        for trajectory_id, fold in sorted(trajectory_fold.items()):
            if fold == held_out_fold:
                continue
            trajectory_residuals = residuals_by_trajectory.get(trajectory_id, [])
            if trajectory_residuals:
                training_trajectory_ids.append(trajectory_id)
            pooled_residuals.extend(trajectory_residuals)
        fit_provenance_by_fold[held_out_fold] = {
            "fit_row_count": len(pooled_residuals),
            "fit_trajectory_ids": tuple(training_trajectory_ids),
            "held_out_trajectory_ids": tuple(
                sorted(t for t, f in trajectory_fold.items() if f == held_out_fold)
            ),
        }
        if len(pooled_residuals) >= 2:
            mean_residual = sum(pooled_residuals) / len(pooled_residuals)
            variance = sum((r - mean_residual) ** 2 for r in pooled_residuals) / (
                len(pooled_residuals) - 1
            )
            if variance > 0.0:
                q_hat_by_fold[held_out_fold] = variance / dt_seconds

    rows: list[BaselineRow] = []
    for ctx in contexts:
        q_hat = q_hat_by_fold.get(ctx.fold)
        applicable = not ctx.visibility and q_hat is not None and ctx.tau_seconds > 0.0
        prediction = (
            math.log(math.sqrt(q_hat * ctx.tau_seconds)) if applicable else None
        )
        provenance = fit_provenance_by_fold.get(ctx.fold, {})
        fit_metadata: dict[str, object] = {
            "held_out_fold": ctx.fold,
            "estimator_id": ESTIMATOR_ID,
            "feature_id": FEATURE_ID,
            "dt_seconds": dt_seconds,
            "fit_row_count": provenance.get("fit_row_count", 0),
            "fit_trajectory_ids": provenance.get("fit_trajectory_ids", ()),
        }
        if applicable:
            fit_metadata["q_hat"] = q_hat
        else:
            fit_metadata["reason"] = (
                "target is visible (no spread defined)"
                if ctx.visibility
                else "insufficient training-fold visible-history residuals"
            )
        rows.append(
            make_baseline_row(
                ctx,
                baseline_name=BASELINE_NAME,
                target_name="log_sigma_oracle",
                prediction=prediction,
                applicable=applicable,
                fit_metadata=fit_metadata,
            )
        )
        rows.append(
            make_baseline_row(
                ctx,
                baseline_name=BASELINE_NAME,
                target_name="mu_oracle_blocks",
                prediction=None,
                applicable=False,
                fit_metadata={
                    "reason": "q_hat and tau alone carry no positional information"
                },
            )
        )
    return rows
