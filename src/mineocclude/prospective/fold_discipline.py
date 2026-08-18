#!/usr/bin/env python3
"""Independent verification of Stage-2 fold and model-selection discipline (B001).

Why this module exists
======================

The Stage-2 readout records, per outer fold, which identities it trained on,
which it held out, and which ``K``/``alpha`` it selected. Before this module the
terminal *read* those fields and judged none of them, so a terminal PASS could
survive a readout that had trained and tested on all 25 identities, selected
``K=999``, used the same trajectory as the held-out set in every outer fold, or
named a training identity that does not exist. The honest implementation does
none of those things -- the defect was that the terminal could not tell.

What is verified, and against what
==================================

Nothing here trusts a boolean. The rules come from the frozen Stage-2 decision
authority (``K_GRID``, ``ALPHAS``, the outer-fold count, the inner-fold shape,
``each_row_predicted_exactly_once``); the expected fold membership comes from
the frozen manifest's own trajectory identities, carried into evidence; and the
inner-fold partition is *re-derived* by running the authority's named function
:func:`mineocclude.regime_a_first25_analysis.inner_fold_assignment` over the
recorded training identities, then compared to what the readout recorded.

Row coverage is verified exactly rather than approximately. A readout records,
per outer fold, a canonical digest over the ``(trajectory_id, tau)`` keys it
actually predicted; the verifier recomputes the digest the frozen design
*requires* for that fold's held-out identities and refuses on any difference.
Five digests per scene therefore establish exact membership, complete coverage,
and the absence of duplicate or missing held-out predictions, without carrying
475 row keys per scene through every artifact.

Everything raises :class:`FoldDisciplineError`, an ``EvidenceError``, so the
terminal converts it into BLOCKED -- an operational refusal to reach a verdict,
never a scientific FAIL.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from typing import Any

from mineocclude.prospective.development_workflow import (
    EvidenceError, canonical_json_bytes,
)


class FoldDisciplineError(EvidenceError):
    """A fold, coverage, or model-selection property could not be established."""


def row_key_digest(row_keys: Sequence[tuple[str, int]]) -> str:
    """Canonical digest over a set of ``(trajectory_id, tau)`` prediction keys.

    Sorted before hashing so the digest is a property of the *set* of rows a
    fold predicted, not of the order a particular implementation happened to
    emit them in. Duplicates are preserved by the sort and therefore change the
    digest, which is what makes a duplicated held-out prediction detectable.
    """
    canonical = sorted([str(identity), int(tau)] for identity, tau in row_keys)
    return hashlib.sha256(canonical_json_bytes(canonical)).hexdigest()


def expected_row_keys(trajectory_ids: Sequence[str], rows_per_trajectory: int) -> list[tuple[str, int]]:
    """The row keys the frozen design requires for a set of held-out identities."""
    return [(str(identity), tau)
            for identity in sorted(trajectory_ids)
            for tau in range(1, int(rows_per_trajectory) + 1)]


def _string_list(value: Any, label: str) -> list[str]:
    if not isinstance(value, (list, tuple)) or not all(
            isinstance(item, str) and item for item in value):
        raise FoldDisciplineError(f"{label} is not a list of identity strings")
    return [str(item) for item in value]


def _positive_integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise FoldDisciplineError(f"{label} is not a non-negative integer: {value!r}")
    return int(value)


def verify_selection_discipline(
        selection: Mapping[str, Any], *, kind: str,
        identity_outer_folds: Mapping[str, int],
        identity_directions: Mapping[str, str],
        rows_per_trajectory: int, outer_fold_count: int,
        k_grid: Sequence[Any] | None, alpha_grid: Sequence[Any],
        training_identities_required: int, inner_fold_count: int,
        identities_per_inner_fold: int, selection_training_tau_maximum: int,
        label: str) -> dict[str, Any]:
    """Re-derive and refuse. Returns the facts it established, for the record.

    ``identity_outer_folds`` and ``identity_directions`` are the frozen design's,
    carried from the manifest through evidence; they are the expectation, never
    something the readout gets to supply. ``kind`` is ``"BEST_K"`` or ``"FULL"``:
    only BEST_K selects a token count, so only BEST_K is required to record one,
    and a FULL readout that reports one anyway is refused rather than ignored.
    """
    from mineocclude.regime_a_first25_analysis import inner_fold_assignment

    if kind not in ("BEST_K", "FULL"):
        raise FoldDisciplineError(f"{label}: unknown readout kind {kind!r}")
    if not isinstance(selection, Mapping):
        raise FoldDisciplineError(f"{label}: selection_by_outer_fold is malformed")
    expected_folds = [str(index) for index in range(outer_fold_count)]
    if sorted(selection) != sorted(expected_folds):
        raise FoldDisciplineError(
            f"{label}: outer folds are {sorted(selection)}, expected {expected_folds}")

    universe = set(identity_outer_folds)
    if set(identity_directions) != universe:
        raise FoldDisciplineError(f"{label}: identity direction inventory is incomplete")
    alphas = [float(value) for value in alpha_grid]
    grid = None if k_grid is None else [int(value) for value in k_grid]

    held_out_seen: dict[str, str] = {}
    pooled_keys: list[tuple[str, int]] = []
    facts: dict[str, Any] = {}
    for fold_name in expected_folds:
        entry = selection[fold_name]
        if not isinstance(entry, Mapping):
            raise FoldDisciplineError(f"{label} fold {fold_name}: selection record is malformed")
        fold = int(fold_name)
        training = _string_list(entry.get("training_trajectory_ids"),
                                f"{label} fold {fold_name} training_trajectory_ids")
        test = _string_list(entry.get("test_trajectory_ids"),
                            f"{label} fold {fold_name} test_trajectory_ids")

        # -- identity legitimacy ------------------------------------------
        unknown = sorted((set(training) | set(test)) - universe)
        if unknown:
            raise FoldDisciplineError(
                f"{label} fold {fold_name}: unknown trajectory identities {unknown}")
        if len(set(training)) != len(training) or len(set(test)) != len(test):
            raise FoldDisciplineError(
                f"{label} fold {fold_name}: an identity appears twice in one fold")
        overlap = sorted(set(training) & set(test))
        if overlap:
            raise FoldDisciplineError(
                f"{label} fold {fold_name}: training and test overlap on {overlap}")
        if set(training) | set(test) != universe:
            raise FoldDisciplineError(
                f"{label} fold {fold_name}: training and test do not partition the "
                "frozen identity inventory")

        # -- the frozen fold rule -----------------------------------------
        required_test = {identity for identity, assigned in identity_outer_folds.items()
                         if assigned == fold}
        if set(test) != required_test:
            raise FoldDisciplineError(
                f"{label} fold {fold_name}: held-out identities are not the frozen "
                f"outer fold's ({sorted(test)} != {sorted(required_test)})")
        if len(training) != training_identities_required:
            raise FoldDisciplineError(
                f"{label} fold {fold_name}: {len(training)} training identities, "
                f"authority requires {training_identities_required}")
        for identity in test:
            if identity in held_out_seen:
                raise FoldDisciplineError(
                    f"{label}: {identity!r} is held out in both fold "
                    f"{held_out_seen[identity]} and fold {fold_name}")
            held_out_seen[identity] = fold_name

        # -- inner folds, re-derived from the authority's named function ---
        recorded_inner = entry.get("inner_fold_assignment")
        if not isinstance(recorded_inner, Mapping) or not recorded_inner:
            raise FoldDisciplineError(
                f"{label} fold {fold_name}: no inner-fold assignment was recorded")
        if set(recorded_inner) != set(training):
            raise FoldDisciplineError(
                f"{label} fold {fold_name}: inner folds do not cover exactly the "
                "training identities")
        try:
            derived_inner = inner_fold_assignment(
                training, {identity: identity_directions[identity] for identity in training},
                fold)
        except (ValueError, KeyError) as exc:
            raise FoldDisciplineError(
                f"{label} fold {fold_name}: the frozen inner-fold rule refuses these "
                f"training identities: {exc}") from exc
        if {str(key): int(value) for key, value in recorded_inner.items()} != derived_inner:
            raise FoldDisciplineError(
                f"{label} fold {fold_name}: recorded inner folds are not the frozen "
                "direction-stratified assignment")
        sizes: dict[int, int] = {}
        for assigned in derived_inner.values():
            sizes[assigned] = sizes.get(assigned, 0) + 1
        if len(sizes) != inner_fold_count or set(sizes.values()) != {identities_per_inner_fold}:
            raise FoldDisciplineError(
                f"{label} fold {fold_name}: inner-fold shape is {sorted(sizes.items())}, "
                f"authority requires {inner_fold_count} folds of {identities_per_inner_fold}")

        # -- model selection ------------------------------------------------
        # The tau ceiling the fold applied when choosing K and alpha. Recorded by
        # the readout, required to equal the authority's, so a fold that widened
        # its selection scope to rows the frozen rule excludes is refusable.
        if entry.get("selection_training_tau_maximum") != int(selection_training_tau_maximum):
            raise FoldDisciplineError(
                f"{label} fold {fold_name}: selection used tau maximum "
                f"{entry.get('selection_training_tau_maximum')!r}, authority requires "
                f"{int(selection_training_tau_maximum)}")
        alpha = entry.get("selected_alpha")
        if isinstance(alpha, bool) or not isinstance(alpha, (int, float)) \
                or float(alpha) not in alphas:
            raise FoldDisciplineError(
                f"{label} fold {fold_name}: selected alpha {alpha!r} is outside the "
                f"frozen grid {alphas}")
        if kind == "BEST_K":
            selected_k = entry.get("selected_k")
            if isinstance(selected_k, bool) or not isinstance(selected_k, int) \
                    or grid is None or selected_k not in grid:
                raise FoldDisciplineError(
                    f"{label} fold {fold_name}: selected K {selected_k!r} is outside "
                    f"the frozen grid {grid}")
            tokens = _positive_integer(entry.get("selected_token_count"),
                                       f"{label} fold {fold_name} selected_token_count")
            if tokens != selected_k:
                raise FoldDisciplineError(
                    f"{label} fold {fold_name}: {tokens} tokens were selected but K is "
                    f"{selected_k}")
        elif "selected_k" in entry:
            raise FoldDisciplineError(
                f"{label} fold {fold_name}: a FULL readout selects no token count")

        # -- held-out row coverage, verified by exact digest -----------------
        required_keys = expected_row_keys(test, rows_per_trajectory)
        count = _positive_integer(entry.get("predicted_row_count"),
                                  f"{label} fold {fold_name} predicted_row_count")
        if count != len(required_keys):
            raise FoldDisciplineError(
                f"{label} fold {fold_name}: {count} rows were predicted, the frozen "
                f"design requires {len(required_keys)}")
        recorded_digest = entry.get("predicted_row_keys_sha256")
        if recorded_digest != row_key_digest(required_keys):
            raise FoldDisciplineError(
                f"{label} fold {fold_name}: the predicted row inventory is not the "
                "frozen held-out row set for this fold")
        pooled_keys.extend(required_keys)
        facts[fold_name] = {"training_identity_count": len(training),
                            "test_identity_count": len(test),
                            "predicted_row_count": count,
                            "selected_alpha": float(alpha),
                            **({"selected_k": int(entry["selected_k"])}
                               if kind == "BEST_K" else {})}

    # -- pooled coverage across the five folds ------------------------------
    if set(held_out_seen) != universe:
        missing = sorted(universe - set(held_out_seen))
        raise FoldDisciplineError(
            f"{label}: these identities are never held out: {missing}")
    complete = expected_row_keys(sorted(universe), rows_per_trajectory)
    if sorted(pooled_keys) != sorted(complete):
        raise FoldDisciplineError(
            f"{label}: pooled out-of-fold rows do not cover each row exactly once")
    return {"outer_folds_verified": len(facts),
            "identities_held_out_exactly_once": len(held_out_seen),
            "pooled_predicted_row_count": len(pooled_keys),
            "each_row_predicted_exactly_once": True,
            "by_outer_fold": facts}
