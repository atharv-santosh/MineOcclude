"""U4 intervention control-matrix verification (Person D).

Roadmap Day 5 (Person D -- "Verify the U4 control matrix"):

1. Create stable IDs for alpha=0, seeded norm-matched random
   directions, orthogonal direction, wrong layer, and wrong timestep.
2. Check that the random direction is norm-matched after projection/
   cap and that no control clips were omitted or overwritten.
3. Compare completeness and paired event/seed coverage across primary
   and control conditions.
4. Report control failures: random slope suggests generic damage;
   wrong-site effects weaken localization; SSIM damage weakens causal
   specificity.

D does not derive the real intervention direction (Person B, see
:mod:`mineocclude.intervention.directions`) or inject it
(Person A, ``src/mineocclude/intervention/inject.py``). D's job is to
define what the *complete* control matrix should look like for every
held-out event/seed pair, verify every expected row actually exists
exactly once (no omission, no duplicate/overwrite -- D3.4), and check
the norm/orthogonality properties the frozen B-to-A intervention
request contract requires
(docs/contracts/intervention_request_v1.md). A failed check here is a
control failure and must stay visible in interpretation, never be
silently dropped.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Sequence

from mineocclude.intervention.directions import DirectionError, dot, l2_norm, normalize


class ControlKind(str, Enum):
    """Every condition the U4 control matrix must cover per event/seed."""

    PRIMARY = "primary"
    ALPHA_ZERO = "alpha_zero"
    RANDOM_DIRECTION = "random_direction"
    ORTHOGONAL_DIRECTION = "orthogonal_direction"
    WRONG_LAYER = "wrong_layer"
    WRONG_TIMESTEP = "wrong_timestep"


@dataclass(frozen=True)
class ControlConditionSpec:
    """One planned row of the U4 control matrix."""

    control_id: str
    kind: ControlKind
    event_id: str
    seed: int


@dataclass(frozen=True)
class ControlMatrixFinding:
    check_name: str
    passed: bool
    detail: str


def build_control_matrix(
    held_out_events: Sequence[str],
    seeds: Sequence[int],
) -> list[ControlConditionSpec]:
    """Build the expected control-matrix rows for every event/seed pair.

    One row per (event, seed, control kind) -- including the primary
    signed-dose condition itself, so paired event/seed coverage between
    primary and controls can be checked in one place. This defines what
    *should* exist; :func:`audit_control_matrix_completeness` checks it
    against what a real rollout registry actually produced.
    """

    matrix: list[ControlConditionSpec] = []
    for event_id in held_out_events:
        for seed in seeds:
            for kind in ControlKind:
                matrix.append(
                    ControlConditionSpec(
                        control_id=f"{event_id}:{seed}:{kind.value}",
                        kind=kind,
                        event_id=event_id,
                        seed=seed,
                    )
                )
    return matrix


def audit_control_matrix_completeness(
    expected: Sequence[ControlConditionSpec],
    produced_control_ids: Sequence[str],
) -> ControlMatrixFinding:
    """Verify every expected control ID exists exactly once.

    Flags missing rows (omitted controls) and duplicated rows
    (overwritten controls) separately, since the roadmap calls out
    both failure modes by name. Unexpected extra IDs are reported but
    do not by themselves fail the check.
    """

    expected_ids = [spec.control_id for spec in expected]
    expected_set = set(expected_ids)

    produced_counts: dict[str, int] = {}
    for control_id in produced_control_ids:
        produced_counts[control_id] = produced_counts.get(control_id, 0) + 1

    missing = sorted(expected_set - produced_counts.keys())
    duplicated = sorted(
        control_id for control_id, count in produced_counts.items() if count > 1
    )
    extra = sorted(set(produced_counts) - expected_set)

    if missing or duplicated:
        parts = []
        if missing:
            parts.append(f"{len(missing)} missing: {missing[:5]}")
        if duplicated:
            parts.append(f"{len(duplicated)} duplicated/overwritten: {duplicated[:5]}")
        if extra:
            parts.append(f"{len(extra)} unexpected extra IDs: {extra[:5]}")
        return ControlMatrixFinding(
            "control_matrix_completeness", False, "; ".join(parts)
        )

    detail = f"all {len(expected_ids)} expected control rows are present exactly once"
    if extra:
        detail += f" ({len(extra)} unexpected extra IDs: {extra[:5]})"
    return ControlMatrixFinding("control_matrix_completeness", True, detail)


def audit_random_direction_norm_matched(
    direction_values: Sequence[float],
    *,
    tolerance: float = 1e-5,
) -> ControlMatrixFinding:
    """Verify a random/orthogonal control direction is unit-norm.

    Matches the frozen B-to-A intervention_request contract's own
    requirement (docs/contracts/intervention_request_v1.md: raw-space,
    approximately unit L2 norm) -- a random control that is not
    actually norm-matched after projection/cap would make "norm-
    matched random direction" a false label.
    """

    norm = l2_norm(direction_values)
    passed = abs(norm - 1.0) <= tolerance
    return ControlMatrixFinding(
        "random_direction_norm_matched",
        passed,
        f"direction L2 norm={norm:.8f} "
        f"{'is within' if passed else 'is NOT within'} tolerance {tolerance} of 1.0",
    )


def audit_orthogonal_to_real_direction(
    candidate_direction: Sequence[float],
    real_direction: Sequence[float],
    *,
    tolerance: float = 1e-6,
) -> ControlMatrixFinding:
    """Verify an orthogonal-direction control is actually orthogonal.

    A stricter check than plain "norm-matched random": this control is
    meant to rule out the real direction's own effect specifically, so
    it must have near-zero cosine similarity to Person B's real
    fitted direction, not just be "some other random vector" that
    could coincidentally overlap with it.
    """

    try:
        cosine = dot(normalize(candidate_direction), normalize(real_direction))
    except DirectionError as error:
        return ControlMatrixFinding("orthogonal_to_real_direction", False, str(error))
    passed = abs(cosine) <= tolerance
    return ControlMatrixFinding(
        "orthogonal_to_real_direction",
        passed,
        f"cosine similarity to the real direction={cosine:.8f} "
        f"{'is within' if passed else 'exceeds'} tolerance {tolerance} of 0.0",
    )
