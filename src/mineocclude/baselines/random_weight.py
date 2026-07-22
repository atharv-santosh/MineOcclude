"""Random-weight MineWorld baseline (deferred; interface only).

Roadmap D2: "Random-weight model | Config-matched random activations
from A | Measures architecture/random-feature decodability." Roadmap
Day 3 (Person D): "Leave random-weight MineWorld for Week 2 if GPU
time is tight, but keep the interface ready."

This baseline is explicitly deferred: it requires Person A to run a
config-matched MineWorld checkpoint with *randomly initialized*
weights and hand off pooled activations from it, exactly like the real
A-to-B activation handoff (docs/contracts/activation_v1.md) but from
an untrained model. That has not happened as of this Phase 1 pass, so
there is nothing real to fit against yet.

The fitting logic itself needs no MineWorld access -- it is the same
leakage-safe layout-grouped ridge OOF machinery as
:mod:`mineocclude.baselines.raw_pixel`, just fed random-weight
activation vectors instead of pixels. Keeping this module a thin,
already-working wrapper (rather than a bare NotImplementedError stub)
is what "keep the interface ready" means in practice: whoever wires up
real random-weight activations in Week 2 only has to supply the
feature mapping, not design a new fitting path.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Mapping, Sequence, Tuple

from mineocclude.baselines.interface import BaselineRow, TrajectoryContext
from mineocclude.baselines.raw_pixel import fit_predict_raw_pixel

BASELINE_NAME = "random_weight_mineworld"

RowKey = Tuple[str, int]
"""(trajectory_id, model_frame_idx), matching how oracle targets are
keyed until Person B's real schema is merged."""


def fit_predict_random_weight(
    contexts: Sequence[TrajectoryContext],
    mu_oracle_by_key: Mapping[RowKey, float],
    random_weight_activation_by_key: Mapping[RowKey, Sequence[float]],
    *,
    alpha_grid: Sequence[float] = (0.1, 1.0, 10.0, 100.0),
    inner_fold_count: int = 4,
    seed: int = 20260719,
) -> list[BaselineRow]:
    """Fit ``mu_oracle_blocks`` from config-matched random-weight activations.

    Deferred until Person A hands off real random-weight-checkpoint
    activations (roadmap Week 2); until then there is simply nothing
    real to pass for ``random_weight_activation_by_key``. Delegates
    entirely to
    :func:`mineocclude.baselines.raw_pixel.fit_predict_raw_pixel`'s
    fitting logic -- the ridge/fold machinery does not care whether a
    feature vector came from pixels or activations -- then relabels
    the rows under this baseline's own name so a comparison table can
    tell the two apart.
    """

    rows = fit_predict_raw_pixel(
        contexts,
        mu_oracle_by_key,
        random_weight_activation_by_key,
        alpha_grid=alpha_grid,
        inner_fold_count=inner_fold_count,
        seed=seed,
    )
    return [replace(row, baseline_name=BASELINE_NAME) for row in rows]
