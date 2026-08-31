"""Outer folds, inner rotations, and the identity priority order (authority 2.6).

Five identity-disjoint outer folds of five, direction-balanced
``[[3,2],[2,3],[3,2],[2,3],[3,2]]``, dealt by ``(seed, identity_id)`` within
direction. **Four** fixed inner rotations operate only inside each outer training
set and only for ridge-alpha selection.

The legacy ``inner_fold_assignment``
(``src/mineocclude/regime_a_first25_analysis.py:27-70``) hard-requires 20
identities and produces **five** inner folds of four; Experiment III requires
four rotations, so it is reimplemented here rather than reused.

Every ordering key is a SHA-256 of identifiers. No target and no feature value
may influence any assignment.
"""

from __future__ import annotations

import hashlib
from collections import Counter, defaultdict
from typing import Any, Mapping, Sequence

from mineocclude.experiment_iii.authority import (
    FOLD_DIRECTION_COUNTS,
    IDENTITIES_PER_OUTER_FOLD,
    INNER_ROTATIONS,
    LEFT_TO_RIGHT_COUNT,
    OUTER_FOLDS,
    PRODUCTION_IDENTITY_COUNT,
    RIGHT_TO_LEFT_COUNT,
)
from mineocclude.experiment_iii.errors import ExperimentIIIError

__all__ = [
    "outer_fold_assignment",
    "inner_rotation_assignment",
    "build_folds",
    "identity_priority_order",
    "assert_no_identity_in_its_own_training_set",
]


def _sort_key(prefix: str, outer: int, identity: str) -> str:
    return hashlib.sha256(
        f"{prefix}|outer={outer}|{identity}".encode("utf-8")
    ).hexdigest()


def outer_fold_assignment(
    identities: Sequence[Mapping[str, Any]],
) -> dict[str, int]:
    """Deal identities to five outer folds by ``(seed, identity_id)``."""
    if len(identities) != PRODUCTION_IDENTITY_COUNT:
        raise ExperimentIIIError(
            "COHORT_MATRIX_INCONSISTENT",
            f"outer folds require {PRODUCTION_IDENTITY_COUNT} identities, got "
            f"{len(identities)}",
        )
    grouped = {
        direction: sorted(
            (row for row in identities if row["direction"] == direction),
            key=lambda row: (int(row["seed"]), str(row["identity"])),
        )
        for direction in ("LEFT_TO_RIGHT", "RIGHT_TO_LEFT")
    }
    counts = [len(grouped["LEFT_TO_RIGHT"]), len(grouped["RIGHT_TO_LEFT"])]
    if counts != [LEFT_TO_RIGHT_COUNT, RIGHT_TO_LEFT_COUNT]:
        raise ExperimentIIIError(
            "COHORT_MATRIX_INCONSISTENT",
            f"direction balance must be {LEFT_TO_RIGHT_COUNT}/{RIGHT_TO_LEFT_COUNT}, "
            f"got {counts[0]}/{counts[1]}",
        )
    assignment: dict[str, int] = {}
    offset = {direction: 0 for direction in grouped}
    for fold, (left, right) in enumerate(FOLD_DIRECTION_COUNTS):
        for direction, count in (("LEFT_TO_RIGHT", left), ("RIGHT_TO_LEFT", right)):
            window = grouped[direction][offset[direction] : offset[direction] + count]
            for row in window:
                assignment[str(row["identity"])] = fold
            offset[direction] += count
    if len(assignment) != PRODUCTION_IDENTITY_COUNT:
        raise ExperimentIIIError(
            "COHORT_MATRIX_INCONSISTENT", "outer fold assignment is not exhaustive"
        )
    sizes = Counter(assignment.values())
    if sorted(sizes.values()) != [IDENTITIES_PER_OUTER_FOLD] * OUTER_FOLDS:
        raise ExperimentIIIError(
            "COHORT_MATRIX_INCONSISTENT",
            f"outer folds are not five of five: {sorted(sizes.values())}",
        )
    return assignment


def inner_rotation_assignment(
    training_identities: Sequence[str],
    directions: Mapping[str, str],
    outer_fold: int,
) -> dict[str, int]:
    """Four deterministic inner rotations inside one outer training set.

    Within each direction, sort by ``sha256("E3_INNER_ROTATION_V1|outer=..|id")``
    and deal round-robin, offsetting the second direction by one rotation. If the
    sizes are not as equal as arithmetically possible, move the identity with the
    lowest ``E3_INNER_REBALANCE_V1`` key from the largest rotation to the
    smallest, repeating until balanced.
    """
    identities = sorted(training_identities)
    if len(identities) != len(set(identities)):
        raise ExperimentIIIError(
            "COHORT_MATRIX_INCONSISTENT", "inner rotation identities must be unique"
        )
    if not identities:
        raise ExperimentIIIError(
            "COHORT_MATRIX_INCONSISTENT", "an outer training set cannot be empty"
        )
    missing = [identity for identity in identities if identity not in directions]
    if missing:
        raise ExperimentIIIError(
            "COHORT_MATRIX_INCONSISTENT",
            f"inner rotation needs a direction for every identity: {missing}",
        )
    grouped: dict[str, list[str]] = defaultdict(list)
    for identity in identities:
        grouped[directions[identity]].append(identity)

    result: dict[str, int] = {}
    for offset, direction in enumerate(("LEFT_TO_RIGHT", "RIGHT_TO_LEFT")):
        ordered = sorted(
            grouped.get(direction, ()),
            key=lambda identity: _sort_key(
                "E3_INNER_ROTATION_V1", outer_fold, identity
            ),
        )
        for index, identity in enumerate(ordered):
            result[identity] = (index + offset) % INNER_ROTATIONS

    total = len(identities)
    base, remainder = divmod(total, INNER_ROTATIONS)
    target_sizes = sorted([base + 1] * remainder + [base] * (INNER_ROTATIONS - remainder))
    for _ in range(total):
        sizes = Counter({rotation: 0 for rotation in range(INNER_ROTATIONS)})
        sizes.update(result.values())
        if sorted(sizes.values()) == target_sizes:
            break
        largest = max(sorted(sizes), key=lambda rotation: (sizes[rotation], -rotation))
        smallest = min(sorted(sizes), key=lambda rotation: (sizes[rotation], rotation))
        movable = sorted(
            (identity for identity, rotation in result.items() if rotation == largest),
            key=lambda identity: _sort_key(
                "E3_INNER_REBALANCE_V1", outer_fold, identity
            ),
        )
        if not movable:
            break
        result[movable[0]] = smallest
    else:  # pragma: no cover - the loop always terminates well before this
        raise ExperimentIIIError(
            "COHORT_MATRIX_INCONSISTENT", "inner rotations could not be balanced"
        )

    sizes = Counter({rotation: 0 for rotation in range(INNER_ROTATIONS)})
    sizes.update(result.values())
    if sorted(sizes.values()) != target_sizes:
        raise ExperimentIIIError(
            "COHORT_MATRIX_INCONSISTENT",
            f"inner rotations are not as equal as possible: {sorted(sizes.values())}",
        )
    return result


def build_folds(identities: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """``folds.json``: outer membership plus four inner rotations per outer fold."""
    outer = outer_fold_assignment(identities)
    directions = {str(row["identity"]): str(row["direction"]) for row in identities}
    folds: list[dict[str, Any]] = []
    for fold in range(OUTER_FOLDS):
        held_out = sorted(
            identity for identity, assigned in outer.items() if assigned == fold
        )
        training = sorted(
            identity for identity, assigned in outer.items() if assigned != fold
        )
        rotations = inner_rotation_assignment(training, directions, fold)
        folds.append(
            {
                "outer_fold": fold,
                "held_out_identities": held_out,
                "training_identities": training,
                "direction_counts": {
                    "LEFT_TO_RIGHT": sum(
                        directions[identity] == "LEFT_TO_RIGHT" for identity in held_out
                    ),
                    "RIGHT_TO_LEFT": sum(
                        directions[identity] == "RIGHT_TO_LEFT" for identity in held_out
                    ),
                },
                "inner_rotations": {
                    str(rotation): sorted(
                        identity
                        for identity, assigned in rotations.items()
                        if assigned == rotation
                    )
                    for rotation in range(INNER_ROTATIONS)
                },
            }
        )
    assert_no_identity_in_its_own_training_set(folds)
    return {
        "schema_version": "mineocclude-experiment-iii-folds-v1",
        "authority_section": "2.6",
        "outer_folds": OUTER_FOLDS,
        "identities_per_outer_fold": IDENTITIES_PER_OUTER_FOLD,
        "inner_rotations": INNER_ROTATIONS,
        "fold_direction_counts_ltr_rtl": [list(pair) for pair in FOLD_DIRECTION_COUNTS],
        "outer_fold_assignment": dict(sorted(outer.items())),
        "folds": folds,
    }


def assert_no_identity_in_its_own_training_set(folds: Sequence[Mapping[str, Any]]) -> None:
    for fold in folds:
        held_out = set(fold["held_out_identities"])
        training = set(fold["training_identities"])
        leaked = held_out & training
        if leaked:
            raise ExperimentIIIError(
                "FOLD_LEAKAGE_DETECTED",
                f"outer fold {fold['outer_fold']} trains on its own held-out "
                f"identities: {sorted(leaked)}",
            )
        for rotation, members in fold["inner_rotations"].items():
            escaped = set(members) - training
            if escaped:
                raise ExperimentIIIError(
                    "FOLD_LEAKAGE_DETECTED",
                    f"inner rotation {rotation} of outer fold "
                    f"{fold['outer_fold']} contains non-training identities: "
                    f"{sorted(escaped)}",
                )


def identity_priority_order(identities: Sequence[str]) -> dict[str, Any]:
    """The frozen total order ``e3_t01 < ... < e3_t25`` (authority 2.6).

    Used ONLY by the deadline fallbacks to choose the first N identities. It may
    never be reordered by observed performance.
    """
    ordered = sorted(identities)
    return {
        "schema_version": "mineocclude-experiment-iii-identity-priority-order-v1",
        "authority_section": "2.6",
        "order": ordered,
        "priority_rank": {identity: rank for rank, identity in enumerate(ordered)},
        "reorderable_by_performance": False,
        "used_only_by": "DEADLINE_FALLBACKS",
    }
