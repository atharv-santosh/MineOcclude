"""Deterministic feasible-subset admission (amended authority 2.3, repair B-prime).

Gate 9 is a *pairwise* constraint, and the frozen ascending first-qualifying rule
resolves it greedily: an early admission can permanently exclude a candidate that
would have been compatible with a different early choice. That order dependence,
not the gate itself, is what made the cohort infeasible once authority 2.5 removed
A-prime's target-window phase offsets.

This module removes the order dependence and nothing else:

* the candidate universe is unchanged (indices ``0`` to the frozen
  ``CANDIDATE_INDEX_BOUND_PER_DIRECTION`` per direction, raised to 2000 by
  Authority Amendment 2);
* every gate is unchanged, including gate 9 at exactly ``0.10``;
* compatibility is the exact frozen gate-9 formula, required at **every** binding
  ``q``, because gate 12 applies gates 1-11 at each ``q`` on that cell's own path;
* among all feasible subsets of the required size, the **lexicographically
  smallest ascending candidate-index tuple** is selected.

There is deliberately **no objective**. The rule does not maximize RMS, minimum
separation, variance or any target statistic, and it reads no image, activation,
prediction or outcome. Its only purpose is to satisfy an already-frozen pairwise
gate without letting arrival order decide feasibility.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

import numpy as np

from mineocclude.experiment_iii.authority import (
    BETWEEN_IDENTITY_DIVERSITY_RMS_BLOCKS,
    BINDING_Q_SET,
    CANDIDATE_INDEX_BOUND_PER_DIRECTION,
    DIAGNOSTIC_Q_FALLBACK,
    MOTION_NOISE_Q,
)
from mineocclude.experiment_iii.cohort import candidate_at
from mineocclude.experiment_iii.errors import ExperimentIIIError
from mineocclude.experiment_iii.qualification import evaluate_gates_1_to_11

__all__ = [
    "GATE_9_THRESHOLD",
    "build_candidate_evaluation_cache",
    "compatibility_matrix",
    "lexicographically_smallest_feasible_subset",
    "verify_selection",
]

GATE_9_THRESHOLD = BETWEEN_IDENTITY_DIVERSITY_RMS_BLOCKS

#: Every ``q`` whose cell is evaluated. The binding set decides admission; the
#: fallback is recorded as a diagnostic and never rejects a candidate.
_ALL_Q = (*BINDING_Q_SET, DIAGNOSTIC_Q_FALLBACK)


def _rms(left: Sequence[float], right: Sequence[float]) -> float:
    """The exact frozen gate-9 formula."""
    a = np.asarray(left, dtype=np.float64)
    b = np.asarray(right, dtype=np.float64)
    return math.sqrt(float(np.mean((a - b) ** 2)))


def build_candidate_evaluation_cache(
    *,
    bound: int = CANDIDATE_INDEX_BOUND_PER_DIRECTION,
    historical: Iterable[int],
    cache_path: Path | None = None,
    progress: Callable[[str, int], None] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Evaluate every candidate under the peer-independent gates, at every ``q``.

    "Peer-independent" means every gate whose verdict does not depend on which
    other candidates have already been admitted: gates 1-8, 10 and 11. Gate 9 is
    handled by :func:`compatibility_matrix`; gate 10 (seed uniqueness within
    Experiment III) is re-checked across the final selection.
    """
    historical = frozenset(int(seed) for seed in historical)
    if cache_path is not None and Path(cache_path).is_file():
        cached = json.loads(Path(cache_path).read_text(encoding="utf-8"))
        if cached.get("bound") == bound and cached.get(
            "historical_seed_count"
        ) == len(historical):
            return cached["per_direction"]

    per_direction: dict[str, list[dict[str, Any]]] = {}
    for direction in ("LEFT_TO_RIGHT", "RIGHT_TO_LEFT"):
        entries: list[dict[str, Any]] = []
        for index in range(bound):
            candidate = candidate_at(direction, index)
            cells: dict[str, Any] = {}
            passed = True
            first_failing: dict[str, int | None] = {}
            for q in _ALL_Q:
                cell = evaluate_gates_1_to_11(
                    candidate,
                    float(q),
                    admitted_labels_same_direction=(),
                    admitted_seeds=(),
                    historical_seeds=historical,
                )
                key = f"{q:.4f}"
                first_failing[key] = cell.first_failing_gate
                cells[key] = {
                    "passed": cell.passed,
                    "labels": list(cell.labels),
                    "path_sha256": cell.path_sha256,
                    "noise_schedule_sha256": cell.noise_schedule_sha256,
                    "target_model_frame_indices": list(
                        cell.target_model_frame_indices
                    ),
                    "target_sd_blocks": cell.target_sd_blocks,
                    "tail_clamped": cell.tail_clamped,
                }
                if q in BINDING_Q_SET and not cell.passed:
                    passed = False
            entries.append(
                {
                    "candidate_index": index,
                    "direction": direction,
                    "seed": candidate.seed,
                    "start_world_x": candidate.start_world_x,
                    "peer_independent_gates_passed": passed,
                    "first_failing_gate_per_q": first_failing,
                    "cells": cells,
                    "diagnostic_q_passed": cells[f"{DIAGNOSTIC_Q_FALLBACK:.4f}"][
                        "passed"
                    ],
                }
            )
            if progress is not None:
                progress(direction, index)
        per_direction[direction] = entries

    if cache_path is not None:
        Path(cache_path).parent.mkdir(parents=True, exist_ok=True)
        Path(cache_path).write_text(
            json.dumps(
                {
                    "bound": bound,
                    "historical_seed_count": len(historical),
                    "per_direction": per_direction,
                },
            ),
            encoding="utf-8",
        )
    return per_direction


def compatibility_matrix(
    eligible: Sequence[Mapping[str, Any]],
    *,
    threshold: float = GATE_9_THRESHOLD,
    binding_q: Sequence[float] = BINDING_Q_SET,
) -> tuple[np.ndarray, list[int]]:
    """``compatible(i,j)`` iff gate 9 holds at EVERY binding ``q``.

    Returns the boolean matrix and the candidate indices it is indexed by, in
    ascending order.
    """
    ordered = sorted(eligible, key=lambda entry: int(entry["candidate_index"]))
    indices = [int(entry["candidate_index"]) for entry in ordered]
    size = len(ordered)
    matrix = np.ones((size, size), dtype=bool)
    np.fill_diagonal(matrix, False)
    for a in range(size):
        for b in range(a + 1, size):
            ok = True
            for q in binding_q:
                key = f"{q:.4f}"
                if (
                    _rms(ordered[a]["cells"][key]["labels"], ordered[b]["cells"][key]["labels"])
                    < threshold
                ):
                    ok = False
                    break
            matrix[a, b] = matrix[b, a] = ok
    return matrix, indices


def lexicographically_smallest_feasible_subset(
    matrix: np.ndarray, indices: Sequence[int], size: int
) -> tuple[list[int] | None, int]:
    """The lexicographically smallest ascending index tuple that is a clique.

    Depth-first in ascending candidate order, so the first complete subset found
    IS the lexicographically smallest one; there is no scoring and no tie-break
    beyond index order. Pruned by the count of still-compatible successors.
    """
    total = len(indices)
    if size > total:
        return None, 0
    explored = 0
    chosen: list[int] = []

    def search(start: int, allowed: np.ndarray) -> bool:
        nonlocal explored
        if len(chosen) == size:
            return True
        for position in range(start, total):
            if not allowed[position]:
                continue
            # Prune: not enough compatible successors remain to finish.
            remaining = int(allowed[position + 1 :].sum())
            if len(chosen) + 1 + remaining < size:
                continue
            explored += 1
            chosen.append(position)
            if search(position + 1, allowed & matrix[position]):
                return True
            chosen.pop()
        return False

    found = search(0, np.ones(total, dtype=bool))
    if not found:
        return None, explored
    return [int(indices[position]) for position in chosen], explored


def verify_selection(
    eligible: Sequence[Mapping[str, Any]],
    selection: Sequence[int],
    *,
    threshold: float = GATE_9_THRESHOLD,
    binding_q: Sequence[float] = BINDING_Q_SET,
) -> dict[str, Any]:
    """Prove the selection satisfies gate 9 at every binding ``q``, pairwise."""
    by_index = {int(entry["candidate_index"]): entry for entry in eligible}
    missing = [index for index in selection if index not in by_index]
    if missing:
        raise ExperimentIIIError(
            "COHORT_MATRIX_INCONSISTENT",
            f"selected candidates are not eligible: {missing}",
        )
    if list(selection) != sorted(selection):
        raise ExperimentIIIError(
            "COHORT_MATRIX_INCONSISTENT",
            "the selected tuple must be in ascending candidate-index order",
        )
    minima: dict[str, float] = {}
    for q in binding_q:
        key = f"{q:.4f}"
        worst = None
        for position, left in enumerate(selection):
            for right in selection[position + 1 :]:
                value = _rms(
                    by_index[left]["cells"][key]["labels"],
                    by_index[right]["cells"][key]["labels"],
                )
                worst = value if worst is None else min(worst, value)
                if value < threshold:
                    raise ExperimentIIIError(
                        "COHORT_MATRIX_INCONSISTENT",
                        f"gate 9 violated at q={key} between candidates "
                        f"{left} and {right}: RMS {value} < {threshold}",
                    )
        minima[key] = float(worst) if worst is not None else float("nan")
    seeds = [int(by_index[index]["seed"]) for index in selection]
    if len(set(seeds)) != len(seeds):
        raise ExperimentIIIError(
            "COHORT_SEED_COLLISION", "selected candidates do not have unique seeds"
        )
    return {
        "pairwise_gate_9_satisfied_at_every_binding_q": True,
        "min_pairwise_rms_by_q": minima,
        "min_pairwise_rms_overall": min(minima.values()),
        "threshold": threshold,
        "selection_is_ascending": True,
    }
