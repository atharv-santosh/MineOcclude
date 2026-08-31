"""Synthetic III-B held-out predictions for the Group-B and Group-D suites.

No GPU, no model, no Minecraft: the "decoder" here is an explicit analytic
function of the frozen oracle, so every planted effect is known exactly and the
statistics can be checked against it rather than against themselves.

The frozen cohort shape -- 13 ``LEFT_TO_RIGHT`` and 12 ``RIGHT_TO_LEFT``
identities -- is reproduced, because ``U2-S2``'s 30-cell nuisance structure and
the ``D.11`` reference value both depend on it.
"""

from __future__ import annotations

import math
from typing import Any, Sequence

import numpy as np

from mineocclude.experiment_iii.authority import (
    LEFT_TO_RIGHT_COUNT,
    PRODUCTION_IDENTITY_IDS,
    RIGHT_TO_LEFT_COUNT,
)
from mineocclude.experiment_iii.iii_b_cells import Q_HIGH, Q_LOW, Q_MID
from mineocclude.experiment_iii.iii_b_oracle import mu_tau, sigma

Q_LEVELS = (Q_LOW, Q_MID, Q_HIGH)
TAU_PRIMARY = tuple(range(1, 16))
TAU_ALL = tuple(range(1, 20))

#: The frozen direction split, in identity order.
DIRECTIONS = tuple(
    ["LEFT_TO_RIGHT"] * LEFT_TO_RIGHT_COUNT + ["RIGHT_TO_LEFT"] * RIGHT_TO_LEFT_COUNT
)
IDENTITY_DIRECTION = dict(zip(PRODUCTION_IDENTITY_IDS, DIRECTIONS))


def synthetic_predictions(
    *,
    scale: float = 1.0,
    offset: float = 0.0,
    noise_sd: float = 0.0,
    seed: int = 20260830,
    q_levels: Sequence[float] = Q_LEVELS,
    tau_values: Sequence[int] = TAU_ALL,
    mu_error_sd: float = 0.0,
    baseline_mu_error_sd: float = 0.0,
    sigma_shift: float = 0.0,
) -> list[dict[str, Any]]:
    """Locked held-out predictions with a PLANTED, known response.

    ``sigma_hat = scale * sigma_oracle + offset + N(0, noise_sd) + sigma_shift``.
    With the defaults the planted response is the oracle itself, so every U2/U3
    statistic must recover the oracle's own structure.
    """
    rng = np.random.default_rng(seed)
    rows: list[dict[str, Any]] = []
    for identity, direction in IDENTITY_DIRECTION.items():
        for q in q_levels:
            for tau in tau_values:
                oracle = sigma(direction, float(q), int(tau))
                sigma_hat = scale * oracle + offset + sigma_shift
                if noise_sd:
                    sigma_hat += float(rng.normal(0.0, noise_sd))
                mu_oracle = mu_tau(0.0, direction, int(tau))
                y_true = mu_oracle
                mu_hat = mu_oracle + (
                    float(rng.normal(0.0, mu_error_sd)) if mu_error_sd else 0.0
                )
                baseline_mu = mu_oracle + (
                    float(rng.normal(0.0, baseline_mu_error_sd))
                    if baseline_mu_error_sd
                    else 0.0
                )
                rows.append(
                    {
                        "identity": identity,
                        "direction": direction,
                        "q": float(q),
                        "tau": int(tau),
                        "sigma_oracle": oracle,
                        "sigma_hat": float(sigma_hat),
                        "mu_hat": float(mu_hat),
                        "mu_oracle_compatible": float(mu_oracle),
                        "mu_baseline_constant_velocity": float(baseline_mu),
                        "y_true": float(y_true),
                        "sigma_tau_only_baseline": float(
                            np.mean([sigma(direction, level, int(tau)) for level in q_levels])
                        ),
                    }
                )
    return rows


def direction_confound_fixture(
    *, q_levels: Sequence[float] = Q_LEVELS, tau_values: Sequence[int] = TAU_PRIMARY
) -> list[dict[str, Any]]:
    """The frozen ``D.11`` negative control: the ``q``-AVERAGED oracle.

    ``sigma_hat(identity, q, tau) := mean over q' of sigma_oracle(direction, q', tau)``
    -- a function of ``(tau, direction)`` only, identical across ``q`` at fixed
    ``(identity, tau)``, so it carries literally zero ``q`` information.
    """
    rows: list[dict[str, Any]] = []
    for identity, direction in IDENTITY_DIRECTION.items():
        for q in q_levels:
            for tau in tau_values:
                fixture = float(
                    np.mean([sigma(direction, float(level), int(tau)) for level in q_levels])
                )
                rows.append(
                    {
                        "identity": identity,
                        "direction": direction,
                        "q": float(q),
                        "tau": int(tau),
                        "sigma_oracle": sigma(direction, float(q), int(tau)),
                        "sigma_hat": fixture,
                    }
                )
    return rows


def no_effect_predictions(
    *, seed: int = 4242, q_levels: Sequence[float] = Q_LEVELS
) -> list[dict[str, Any]]:
    """A dataset with NO ``q`` effect: sigma_hat depends on tau and noise only."""
    rng = np.random.default_rng(seed)
    rows: list[dict[str, Any]] = []
    for identity, direction in IDENTITY_DIRECTION.items():
        for q in q_levels:
            for tau in TAU_ALL:
                rows.append(
                    {
                        "identity": identity,
                        "direction": direction,
                        "q": float(q),
                        "tau": int(tau),
                        "sigma_oracle": sigma(direction, float(q), int(tau)),
                        "sigma_hat": 0.01 * tau + float(rng.normal(0.0, 0.001)),
                    }
                )
    return rows


def identity_rows(count: int = 25) -> list[dict[str, Any]]:
    """Minimal III-A identity rows for the ``B-GEN`` manifest builder."""
    from mineocclude.experiment_iii.cohort import candidate_at

    rows: list[dict[str, Any]] = []
    per_direction = {"LEFT_TO_RIGHT": 0, "RIGHT_TO_LEFT": 0}
    for ordinal, identity in enumerate(PRODUCTION_IDENTITY_IDS[:count]):
        direction = IDENTITY_DIRECTION[identity]
        index = per_direction[direction]
        per_direction[direction] += 1
        candidate = candidate_at(direction, index)
        rows.append(
            {
                "identity": identity,
                "direction": direction,
                "candidate_index": candidate.index,
                "seed": candidate.seed,
                "start_world_x": candidate.start_world_x,
                "outer_fold": ordinal % 5,
                "inner_rotation": ordinal % 4,
                "priority_rank": ordinal + 1,
            }
        )
    return rows
