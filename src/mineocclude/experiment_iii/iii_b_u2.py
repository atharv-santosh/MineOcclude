"""U2 -- does the representation carry ``q``-dependent uncertainty? (authority 22-23).

Three statistics, one frozen family, one frozen declaration conjunction:

===========  ====================================================================
``U2-S1``    matched-tau contrast ``sigma_hat(q_high) - sigma_hat(q_low)``
``U2-S2``    partial rank association ``rho(sigma_hat, sigma_oracle | tau x direction)``
``U2-S3``    three-``q`` monotone dose response against chance ``1/6``
===========  ====================================================================

Every statistic uses **raw** ``sigma_hat``; the calibration positivity guard
(authority 27.0) never reaches them. Matching across ``q`` is by occlusion age
``tau`` and never by absolute frame index.

The subtle one is ``U2-S2``. Conditioning is on **tau x direction**, not tau
alone: the oracle sigma depends on direction through ``H_direction(m)``, so after
tau-only residualization a decoder reading direction alone -- carrying literally
zero ``q`` sensitivity -- can produce a positive association. Ranking happens over
the **pooled** set first and residualization second; reversing that order, or
ranking within cells, is a different statistic and is refused.
"""

from __future__ import annotations

import math
from typing import Any, Iterable, Mapping, Sequence

import numpy as np

from mineocclude.experiment_iii.errors import ExperimentIIIError
from mineocclude.experiment_iii.iii_b_cells import Q_HIGH, Q_LOW, Q_MID
from mineocclude.experiment_iii.iii_b_inference import (
    ALPHA,
    BOOTSTRAP_B,
    U2_FAMILY_AT_DROP_LEVEL_1,
    U2_FAMILY_ORDER,
    bootstrap_inversion,
    holm,
    percentile_interval,
    whole_identity_replicates,
    within_identity_q_permutation_p_value,
)
from mineocclude.experiment_iii.iii_b_oracle import TAU_PRIMARY_SUPPORT

__all__ = [
    "CONFOUND_CONTROLS",
    "NUISANCE_CELLS",
    "U2_S3_CHANCE",
    "WORDING_AFTER_CONTROLS_PASS",
    "WORDING_BEFORE_CONTROLS_PASS",
    "ZERO_VARIANCE_TOLERANCE_RELATIVE",
    "assert_confound_controls_present",
    "context_boundary_secondary",
    "average_ranks",
    "matched_tau_differences",
    "partial_rank_association",
    "u2_analysis",
    "u2_s1",
    "u2_s2",
    "u2_s3",
    "wording_for",
]

#: tau = 1..15 crossed with the two directions (authority 22.2).
NUISANCE_CELLS = 30
U2_S3_CHANCE = 1.0 / 6.0
ZERO_VARIANCE_TOLERANCE_RELATIVE = 1e-15

WORDING_BEFORE_CONTROLS_PASS = "Q_REGIME_RELEVANT_INFORMATION"
WORDING_AFTER_CONTROLS_PASS = (
    "UNCERTAINTY_RELEVANT_INFORMATION_TRACKING_ORACLE_POSTERIOR_SPREAD"
)

#: Authority 23, in frozen order. All eight are mandatory.
CONFOUND_CONTROLS = (
    "TAU_ONLY_BASELINE",
    "Q_ONLY_CATEGORICAL_BASELINE",
    "ANALYTIC_TAU_PLUS_Q_ORACLE_REFERENCE",
    "RAW_CURRENT_FRAME_PIXEL_BASELINE",
    "WITHIN_IDENTITY_Q_PERMUTATION_NULL",
    "MATCHED_TAU_EVALUATION",
    "U3_Q_DEPENDENT_RATE_INTERACTION",
    "TAU_GE_16_BOUNDARY_COLLAPSE",
)

_DIRECTIONS = ("LEFT_TO_RIGHT", "RIGHT_TO_LEFT")


# --------------------------------------------------------------------------
# Row plumbing
# --------------------------------------------------------------------------

def _require(row: Mapping[str, Any], field: str) -> Any:
    if field not in row:
        raise ExperimentIIIError(
            "B_U2_ANALYSIS_FAIL", f"held-out prediction row lacks {field!r}"
        )
    return row[field]


def _tau_of(row: Mapping[str, Any]) -> int:
    tau = _require(row, "tau")
    if isinstance(tau, bool) or not isinstance(tau, int):
        raise ExperimentIIIError(
            "B_TAU_ALIGNMENT_ERROR",
            f"tau must be an int occlusion age, got {tau!r}; matching by absolute "
            "model-frame index is forbidden",
        )
    return tau


# --------------------------------------------------------------------------
# U2-S1 -- matched-tau contrast
# --------------------------------------------------------------------------

def matched_tau_differences(
    rows: Sequence[Mapping[str, Any]],
    *,
    q_low: float = Q_LOW,
    q_high: float = Q_HIGH,
    tau_support: Sequence[int] = TAU_PRIMARY_SUPPORT,
) -> tuple[list[str], np.ndarray]:
    """``D_i,tau = sigma_hat(q_high,i,tau) - sigma_hat(q_low,i,tau)`` at equal tau."""
    table: dict[tuple[str, int, float], float] = {}
    for row in rows:
        q = float(_require(row, "q"))
        if not (math.isclose(q, q_low) or math.isclose(q, q_high)):
            continue
        key = (str(row["identity"]), _tau_of(row), q_high if math.isclose(q, q_high) else q_low)
        if key in table:
            raise ExperimentIIIError(
                "B_U2_ANALYSIS_FAIL",
                f"duplicate held-out prediction for {key}; exactly one per cell",
            )
        table[key] = float(_require(row, "sigma_hat"))
    identities = sorted({key[0] for key in table})
    matrix = np.empty((len(identities), len(tau_support)), dtype=np.float64)
    for i, identity in enumerate(identities):
        for j, tau in enumerate(tau_support):
            try:
                matrix[i, j] = table[(identity, int(tau), q_high)] - table[
                    (identity, int(tau), q_low)
                ]
            except KeyError as error:
                raise ExperimentIIIError(
                    "B_TAU_ALIGNMENT_ERROR",
                    f"{identity} lacks a matched-tau pair at tau={tau}: {error}",
                ) from None
    return identities, matrix


def u2_s1(
    rows: Sequence[Mapping[str, Any]],
    *,
    seed: int,
    q_low: float = Q_LOW,
    q_high: float = Q_HIGH,
    replicates: int = BOOTSTRAP_B,
) -> dict[str, Any]:
    """Matched-tau contrast: interval by bootstrap, p-value by permutation."""
    identities, matrix = matched_tau_differences(rows, q_low=q_low, q_high=q_high)
    per_identity = matrix.mean(axis=1)
    draws = whole_identity_replicates(identities, seed=seed, replicates=replicates)
    samples = per_identity[draws].mean(axis=1)
    low, high = percentile_interval(samples)
    permutation = within_identity_q_permutation_p_value(matrix, seed=seed)
    return {
        "statistic": "U2-S1",
        "name": "MATCHED_TAU_CONTRAST",
        "observed": float(per_identity.mean()),
        "per_identity": {name: float(value) for name, value in zip(identities, per_identity)},
        "ci_low": low,
        "ci_high": high,
        "ci_is_unadjusted": True,
        "p_value": permutation["p_value"],
        "p_value_construction": permutation["construction"],
        "permutations": permutation["permutations"],
        "matching": "OCCLUSION_AGE_TAU",
        "uses_raw_sigma_hat": True,
        "replicates": replicates,
        "seed": seed,
    }


# --------------------------------------------------------------------------
# U2-S2 -- partial rank association
# --------------------------------------------------------------------------

def average_ranks(values: Sequence[float]) -> np.ndarray:
    """Ranks over the pooled set, ties averaged. 1-based, like ``scipy``."""
    sample = np.asarray(values, dtype=np.float64)
    if sample.size == 0:
        return np.empty(0, dtype=np.float64)
    order = np.argsort(sample, kind="mergesort")
    ordered = sample[order]
    starts_group = np.empty(sample.size, dtype=bool)
    starts_group[0] = True
    np.not_equal(ordered[1:], ordered[:-1], out=starts_group[1:])
    group = np.cumsum(starts_group) - 1
    counts = np.bincount(group)
    starts = np.concatenate(([0], np.cumsum(counts)[:-1]))
    group_rank = starts + (counts - 1) / 2.0 + 1.0
    ranks = np.empty(sample.size, dtype=np.float64)
    ranks[order] = group_rank[group]
    return ranks


def _cell_codes(tau: np.ndarray, direction: np.ndarray, conditioning: str) -> np.ndarray:
    if conditioning == "TAU_X_DIRECTION":
        return (tau.astype(np.int64) - 1) * 2 + direction.astype(np.int64)
    if conditioning == "TAU_ONLY":
        return tau.astype(np.int64) - 1
    raise ExperimentIIIError(
        "B_U2_S2_CONDITIONING_MISMATCH",
        f"conditioning must be TAU_X_DIRECTION (frozen) or the superseded "
        f"TAU_ONLY demonstration form, got {conditioning!r}",
    )


def _residualize(ranks: np.ndarray, codes: np.ndarray) -> np.ndarray:
    """``rank - mean(rank within its own nuisance cell)`` -- the canonical form.

    Numerically identical to the minimum-norm ``lstsq`` fit on
    ``[1 | cell indicators]``, and it makes the singleton-cell rule
    (residual exactly ``0.0``, retained) obvious rather than incidental.
    """
    sums = np.bincount(codes, weights=ranks)
    counts = np.bincount(codes)
    means = np.divide(sums, counts, out=np.zeros_like(sums), where=counts > 0)
    return ranks - means[codes]


def partial_rank_association(
    sigma_hat: Sequence[float],
    sigma_oracle: Sequence[float],
    tau: Sequence[int],
    direction_code: Sequence[int],
    *,
    conditioning: str = "TAU_X_DIRECTION",
) -> dict[str, Any]:
    """``rho`` with the frozen zero-variance rule. Never returns ``NaN``."""
    hat = np.asarray(sigma_hat, dtype=np.float64)
    oracle = np.asarray(sigma_oracle, dtype=np.float64)
    taus = np.asarray(tau, dtype=np.int64)
    directions = np.asarray(direction_code, dtype=np.int64)
    if not (hat.size == oracle.size == taus.size == directions.size) or hat.size == 0:
        raise ExperimentIIIError(
            "B_U2_S2_CONDITIONING_MISMATCH", "U2-S2 inputs must be equal-length and non-empty"
        )
    # STEP 2: rank over the POOLED set first.
    rank_hat = average_ranks(hat)
    rank_oracle = average_ranks(oracle)
    # STEP 3: residualize the ranks second.
    codes = _cell_codes(taus, directions, conditioning)
    residual_hat = _residualize(rank_hat, codes)
    residual_oracle = _residualize(rank_oracle, codes)

    tol_hat = ZERO_VARIANCE_TOLERANCE_RELATIVE * float(np.var(rank_hat))
    tol_oracle = ZERO_VARIANCE_TOLERANCE_RELATIVE * float(np.var(rank_oracle))
    var_hat = float(np.var(residual_hat))
    var_oracle = float(np.var(residual_oracle))
    zero_variance = var_hat <= tol_hat or var_oracle <= tol_oracle
    if zero_variance:
        rho = 0.0
    else:
        # STEP 4: Pearson correlation of the two residual vectors.
        centred_hat = residual_hat - residual_hat.mean()
        centred_oracle = residual_oracle - residual_oracle.mean()
        rho = float(
            np.dot(centred_hat, centred_oracle)
            / math.sqrt(float(np.dot(centred_hat, centred_hat)) * float(np.dot(centred_oracle, centred_oracle)))
        )
        if not math.isfinite(rho):  # pragma: no cover - the guard above precludes it
            raise ExperimentIIIError(
                "B_U2_S2_CONDITIONING_MISMATCH",
                "rho is not finite despite passing the zero-variance guard",
            )
    return {
        "rho": rho,
        "conditioning": conditioning,
        "nuisance_cells": NUISANCE_CELLS if conditioning == "TAU_X_DIRECTION" else 15,
        "zero_variance_case": zero_variance,
        "var_residual_sigma_hat": var_hat,
        "var_residual_sigma_oracle": var_oracle,
        "tolerance_sigma_hat": tol_hat,
        "tolerance_sigma_oracle": tol_oracle,
        "order": "RANK_POOLED_FIRST_THEN_RESIDUALIZE",
        "observations": int(hat.size),
    }


def _u2_s2_arrays(
    rows: Sequence[Mapping[str, Any]], tau_support: Sequence[int]
) -> tuple[list[str], dict[str, np.ndarray], dict[str, np.ndarray]]:
    """Flat pooled arrays plus per-identity row indices into them.

    The bootstrap draws whole identities, so a replicate is one concatenation of
    index blocks; keeping the payload flat is what makes recomputing ranking and
    residualization inside all 10,000 replicates affordable.
    """
    support = set(int(value) for value in tau_support)
    identities: list[str] = []
    positions: dict[str, list[int]] = {}
    sigma_hat: list[float] = []
    sigma_oracle: list[float] = []
    taus: list[int] = []
    directions: list[int] = []
    for row in rows:
        tau = _tau_of(row)
        if tau not in support:
            continue
        identity = str(_require(row, "identity"))
        direction = str(_require(row, "direction"))
        if direction not in _DIRECTIONS:
            raise ExperimentIIIError(
                "B_U2_S2_CONDITIONING_MISMATCH", f"unknown direction {direction!r}"
            )
        if identity not in positions:
            positions[identity] = []
            identities.append(identity)
        positions[identity].append(len(sigma_hat))
        sigma_hat.append(float(_require(row, "sigma_hat")))
        sigma_oracle.append(float(_require(row, "sigma_oracle")))
        taus.append(tau)
        directions.append(_DIRECTIONS.index(direction))
    flat = {
        "sigma_hat": np.asarray(sigma_hat, dtype=np.float64),
        "sigma_oracle": np.asarray(sigma_oracle, dtype=np.float64),
        "tau": np.asarray(taus, dtype=np.int64),
        "direction": np.asarray(directions, dtype=np.int64),
    }
    blocks = {
        identity: np.asarray(index, dtype=np.int64)
        for identity, index in positions.items()
    }
    return sorted(identities), flat, blocks


def u2_s2(
    rows: Sequence[Mapping[str, Any]],
    *,
    seed: int,
    conditioning: str = "TAU_X_DIRECTION",
    tau_support: Sequence[int] = TAU_PRIMARY_SUPPORT,
    replicates: int = BOOTSTRAP_B,
) -> dict[str, Any]:
    """Partial rank association, with ranking and residualization inside every replicate."""
    identities, flat, blocks = _u2_s2_arrays(rows, tau_support)
    if len(identities) < 2:
        raise ExperimentIIIError(
            "B_U2_ANALYSIS_FAIL", "U2-S2 needs at least two identities"
        )
    direction_of = {
        identity: int(flat["direction"][index[0]]) for identity, index in blocks.items()
    }

    def statistic(index: np.ndarray) -> dict[str, Any]:
        return partial_rank_association(
            flat["sigma_hat"][index],
            flat["sigma_oracle"][index],
            flat["tau"][index],
            flat["direction"][index],
            conditioning=conditioning,
        )

    observed = statistic(np.concatenate([blocks[name] for name in identities]))
    draws = whole_identity_replicates(identities, seed=seed, replicates=replicates)
    samples = np.empty(replicates, dtype=np.float64)
    zero_variance_replicates = 0
    single_direction_replicates = 0
    for row_index, row in enumerate(draws):
        names = [identities[position] for position in row]
        result = statistic(np.concatenate([blocks[name] for name in names]))
        samples[row_index] = result["rho"]
        zero_variance_replicates += int(result["zero_variance_case"])
        single_direction_replicates += int(
            len({direction_of[name] for name in names}) == 1
        )

    if observed["zero_variance_case"]:
        # Every replicate maps to rho* = 0.0 as well, so the inversion formula
        # gives p = (1 + B)/(B + 1) = 1.0 exactly. Replicates are RETAINED.
        p_value = 1.0
        rho = 0.0
        low, high = percentile_interval(samples)
    else:
        low, high = percentile_interval(samples)
        floor = 1.0 / (replicates + 1)
        p_value = min(
            1.0,
            max(floor, (1 + int(np.count_nonzero(samples <= 0.0))) / (replicates + 1)),
        )
        rho = observed["rho"]
    return {
        "statistic": "U2-S2",
        "name": "PROPOSAL_ALIGNED_CONDITIONAL_ASSOCIATION",
        "observed": rho,
        "rho": rho,
        "ci_low": low,
        "ci_high": high,
        "ci_is_unadjusted": True,
        "p_value": p_value,
        "p_value_construction": "WHOLE_IDENTITY_BOOTSTRAP_INVERSION",
        "conditioning": conditioning,
        "nuisance_cells": observed["nuisance_cells"],
        "U2_S2_ZERO_VARIANCE_CASE": observed["zero_variance_case"],
        "zero_variance_replicates": zero_variance_replicates,
        "zero_variance_replicate_fraction": zero_variance_replicates / replicates,
        "single_direction_replicates": single_direction_replicates,
        "var_residual_sigma_hat": observed["var_residual_sigma_hat"],
        "var_residual_sigma_oracle": observed["var_residual_sigma_oracle"],
        "tolerance_sigma_hat": observed["tolerance_sigma_hat"],
        "tolerance_sigma_oracle": observed["tolerance_sigma_oracle"],
        "order": observed["order"],
        "uses_raw_sigma_hat": True,
        "replicates": replicates,
        "seed": seed,
    }


# --------------------------------------------------------------------------
# U2-S3 -- three-q monotone dose response
# --------------------------------------------------------------------------

def u2_s3(
    rows: Sequence[Mapping[str, Any]],
    *,
    seed: int,
    q_levels: Sequence[float] = (Q_LOW, Q_MID, Q_HIGH),
    tau_support: Sequence[int] = TAU_PRIMARY_SUPPORT,
    replicates: int = BOOTSTRAP_B,
) -> dict[str, Any]:
    """Proportion of identities whose tau-averaged sigma_hat is strictly ordered."""
    if len(q_levels) != 3:
        raise ExperimentIIIError(
            "B_U2_FAMILY_ALTERED",
            "U2-S3 is the THREE-q dose response; at drop LEVEL_1 it is not "
            "estimable and leaves the family rather than being redefined",
        )
    support = set(int(value) for value in tau_support)
    sums: dict[tuple[str, float], list[float]] = {}
    for row in rows:
        if _tau_of(row) not in support:
            continue
        q = float(_require(row, "q"))
        match = next((level for level in q_levels if math.isclose(q, level)), None)
        if match is None:
            continue
        sums.setdefault((str(row["identity"]), match), []).append(
            float(_require(row, "sigma_hat"))
        )
    identities = sorted({key[0] for key in sums})
    agreement: dict[str, int] = {}
    for identity in identities:
        try:
            means = [float(np.mean(sums[(identity, level)])) for level in q_levels]
        except KeyError:
            raise ExperimentIIIError(
                "B_U2_ANALYSIS_FAIL", f"{identity} lacks one of the three q levels"
            ) from None
        if means[0] < means[1] < means[2]:
            agreement[identity] = 1
        elif means[0] > means[1] > means[2]:
            agreement[identity] = -1
        else:
            agreement[identity] = 0
    flags = np.asarray([agreement[name] == 1 for name in identities], dtype=np.float64)

    position = {name: index for index, name in enumerate(identities)}

    def statistic(sample: Sequence[str]) -> float:
        return float(flags[[position[name] for name in sample]].mean())

    result = bootstrap_inversion(
        identities,
        statistic,
        seed=seed,
        t_null=U2_S3_CHANCE,
        replicates=replicates,
        label="U2-S3",
    )
    result.update(
        {
            "name": "THREE_Q_MONOTONE_DOSE_RESPONSE",
            "chance_level": U2_S3_CHANCE,
            "per_identity_agreement": agreement,
            "uses_raw_sigma_hat": True,
            "q_levels": [float(level) for level in q_levels],
        }
    )
    return result


# --------------------------------------------------------------------------
# The family, the controls and the declaration conjunction
# --------------------------------------------------------------------------

def assert_confound_controls_present(reported: Iterable[str]) -> None:
    """All eight authority-23 controls are mandatory; a missing one fails the stage."""
    present = set(str(name) for name in reported)
    missing = [name for name in CONFOUND_CONTROLS if name not in present]
    if missing:
        raise ExperimentIIIError(
            "B_U2_ANALYSIS_FAIL",
            f"the eight frozen clock and category confound controls are mandatory; "
            f"missing {missing}",
        )
    extra = sorted(present - set(CONFOUND_CONTROLS))
    if extra:
        raise ExperimentIIIError(
            "B_U2_ANALYSIS_FAIL",
            f"the control set is frozen at eight; {extra} is not one of them",
        )


def context_boundary_secondary(
    rows: Sequence[Mapping[str, Any]],
    *,
    seed: int,
    q_low: float = Q_LOW,
    q_high: float = Q_HIGH,
    replicates: int = BOOTSTRAP_B,
) -> dict[str, Any]:
    """The authority-25 boundary secondary: the same D statistic on tau = 16..19.

    At ``tau >= 16`` the last potentially informative pre-occlusion frame has
    left the 16-pair context, so the finite-context interpretation predicts the
    separation falls to about zero. This is **not** a technical pass gate: a
    nonzero result is reportable scientific evidence under the already-frozen
    analyses, and it is never a reason to modify the experiment.
    """
    identities, matrix = matched_tau_differences(
        rows, q_low=q_low, q_high=q_high, tau_support=tuple(range(16, 20))
    )
    per_identity = matrix.mean(axis=1)
    draws = whole_identity_replicates(identities, seed=seed, replicates=replicates)
    low, high = percentile_interval(per_identity[draws].mean(axis=1))
    return {
        "statistic": "CONTEXT_BOUNDARY_SECONDARY",
        "tau_support": [16, 17, 18, 19],
        "observed": float(per_identity.mean()),
        "ci_low": low,
        "ci_high": high,
        "ci_is_unadjusted": True,
        "is_a_technical_pass_gate": False,
        "enters_holm_family": False,
        "uses_raw_sigma_hat": True,
        "expected_under_finite_context": "SEPARATION_APPROACHES_ZERO",
        "modify_experiment_if_prediction_fails": False,
        "replicates": replicates,
        "seed": seed,
    }


def wording_for(*, controls_passed: bool, ladder_rung: int | None = None) -> str:
    """The frozen authority-23 wording gate."""
    if not controls_passed:
        return WORDING_BEFORE_CONTROLS_PASS
    if ladder_rung == 4:
        return "CALIBRATED_GAUSSIAN_BELIEF_STATE_UNDER_THIS_APPARATUS"
    return WORDING_AFTER_CONTROLS_PASS


def u2_analysis(
    rows: Sequence[Mapping[str, Any]],
    *,
    seed: int,
    controls_passed: bool,
    drop_level: str = "NORMAL",
    conditioning: str = "TAU_X_DIRECTION",
    replicates: int = BOOTSTRAP_B,
) -> dict[str, Any]:
    """The frozen U2 family, Holm decision and positive-declaration conjunction.

    At drop ``LEVEL_1`` the ladder drops ``q_low`` and retains ``q_mid`` plus
    ``q_high`` (authority 29.6). ``U2-S3`` is then not estimable and leaves the
    family, which shrinks to two -- the only permitted family change. ``U2-S1``
    remains the matched-tau contrast between the two *retained* doses, because
    ``q_low`` no longer exists to contrast against; the statistic is unchanged in
    form, only in which pair of doses it reads.
    """
    if drop_level == "LEVEL_1":
        family_order = U2_FAMILY_AT_DROP_LEVEL_1
        members = {
            "U2-S1": u2_s1(rows, seed=seed, q_low=Q_MID, replicates=replicates),
            "U2-S2": u2_s2(
                rows, seed=seed, conditioning=conditioning, replicates=replicates
            ),
        }
    else:
        family_order = U2_FAMILY_ORDER
        members = {
            "U2-S1": u2_s1(rows, seed=seed, replicates=replicates),
            "U2-S2": u2_s2(
                rows, seed=seed, conditioning=conditioning, replicates=replicates
            ),
            "U2-S3": u2_s3(rows, seed=seed, replicates=replicates),
        }
    adjusted = holm(
        {name: member["p_value"] for name, member in members.items()},
        family_order=family_order,
    )
    thresholds = {"U2-S1": 0.0, "U2-S2": 0.0, "U2-S3": U2_S3_CHANCE}
    clauses = {
        name: bool(adjusted[name] <= ALPHA and members[name]["ci_low"] > thresholds[name])
        for name in family_order
    }
    declared = bool(controls_passed and all(clauses.values()))
    return {
        "schema_version": "mineocclude-experiment-iii-b-u2-results-v1",
        "family": list(family_order),
        "family_size": len(family_order),
        "drop_level": drop_level,
        "alpha": ALPHA,
        "members": members,
        "holm_adjusted_p_values": adjusted,
        "significant": {name: bool(adjusted[name] <= ALPHA) for name in family_order},
        "conjunction_clauses": clauses,
        "confound_controls_passed": controls_passed,
        "U2_POSITIVE": declared,
        "wording": wording_for(controls_passed=controls_passed),
        "ci_role": "EFFECT_SIZE_REPORTING",
        "holm_role": "FAMILYWISE_HYPOTHESIS_DECISION",
        "intervals_are_unadjusted": True,
    }
