"""Metadata-only leakage diagnostics (Person D).

Roadmap Day 2 (Person D): "Run metadata-only leakage diagnostics for
layout, filename, wall length, frame count, ordering, padding, q,
duration, and target predictability." Roadmap D3.1: "Test whether
layout IDs, wall lengths, file order/names, padding, frame counts,
output paths, or exclusion patterns encode conditions/targets."

Two different kinds of check live here, matching the two kinds of
field the roadmap lists:

1. Identity/structural checks (:func:`audit_identity_not_filename_derived`,
   :func:`audit_layout_fold_isolation`) -- cheap, no fitting, directly
   verify the universal identity rule ("directory order and filenames
   alone must never define scientific identity") and the layout-grouped
   fold invariant.

2. Numeric predictability checks (:func:`check_metadata_predictability`)
   -- one general leakage-safe grouped-ridge tool. Feed it whichever
   metadata-only feature you want to interrogate (frame_count, row
   ordering / model_frame_idx, a padding flag, an output-path hash
   bucket...) as ``feature_rows``, and whichever quantity it should have
   no legitimate access to (wall_length, q, duration, or the oracle
   target itself) as ``targets``. A HIGH out-of-fold R^2 here is a bad
   sign, not a good one: it means the metadata carries information it
   should not, not that a real signal was found. Every call is a
   separate named diagnostic; this module does not hard-code one
   function per roadmap-listed field because the leakage-safe fitting
   logic is identical regardless of which two columns are being tested
   against each other.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence, Tuple

from mineocclude.probes.ridge import fit_ridge_oof

FrameKey = Tuple[str, int]

_FILENAME_MARKERS = (".mp4", ".json", ".jsonl", ".png", ".parquet", "/", "\\")


@dataclass(frozen=True)
class IdentityLeakageFinding:
    check_name: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class PredictabilityFinding:
    diagnostic_name: str
    r2: float
    suspicious: bool
    threshold: float
    detail: str


def audit_identity_not_filename_derived(
    trajectory_ids: Sequence[str],
) -> IdentityLeakageFinding:
    """Verify trajectory identities are not literally filenames or paths.

    Roadmap universal identity rule: "Directory order and filenames
    alone must never define scientific identity." A ``trajectory_id``
    containing a path separator or media extension suggests row
    identity was derived from a filename rather than an explicit ID
    field.
    """

    offenders = sorted(
        {
            trajectory_id
            for trajectory_id in trajectory_ids
            if any(marker in trajectory_id for marker in _FILENAME_MARKERS)
        }
    )
    if offenders:
        return IdentityLeakageFinding(
            "identity_not_filename_derived",
            False,
            f"{len(offenders)} trajectory_id values look filename/path-derived: "
            f"{offenders[:5]}",
        )
    return IdentityLeakageFinding(
        "identity_not_filename_derived",
        True,
        f"all {len(trajectory_ids)} trajectory_id values are free of path "
        "separators and media extensions",
    )


def audit_layout_fold_isolation(
    layout_fold_pairs: Iterable[Tuple[str, int]],
) -> IdentityLeakageFinding:
    """Verify no ``layout_id`` is ever split across more than one fold.

    An independent re-check of the layout-grouped split invariant B's
    own fold assignment already enforces
    (:mod:`mineocclude.probes.splits`) -- defense in depth, since D's
    job is to *consume*, never construct, the fold assignment.
    """

    fold_by_layout: dict[str, set[int]] = defaultdict(set)
    for layout_id, fold in layout_fold_pairs:
        fold_by_layout[layout_id].add(fold)

    offenders = {
        layout: sorted(folds) for layout, folds in fold_by_layout.items() if len(folds) > 1
    }
    if offenders:
        return IdentityLeakageFinding(
            "layout_fold_isolation",
            False,
            f"{len(offenders)} layouts span multiple folds: {offenders}",
        )
    return IdentityLeakageFinding(
        "layout_fold_isolation",
        True,
        f"all {len(fold_by_layout)} layouts stay within a single fold",
    )


def check_metadata_predictability(
    feature_rows: Sequence[Sequence[float]],
    targets: Sequence[float],
    layout_ids: Sequence[str],
    folds: Sequence[int],
    *,
    diagnostic_name: str,
    r2_threshold: float = 0.1,
    alpha_grid: Sequence[float] = (0.1, 1.0, 10.0, 100.0),
    inner_fold_count: int = 4,
    seed: int = 20260719,
) -> PredictabilityFinding:
    """Flag suspiciously high metadata-only out-of-fold predictability.

    Fits a leakage-safe layout-grouped ridge OOF model (the same
    machinery as every other ridge baseline in this package) from
    ``feature_rows`` to ``targets``, then reports the out-of-fold R^2.
    A result above ``r2_threshold`` is *suspicious*, not good: it means
    the supplied metadata-only features predict something they have no
    legitimate causal path to (e.g. wall length, scripted q/duration,
    or the oracle target itself from row ordering/padding/frame count),
    which points at a leakage channel rather than a real result.
    """

    result = fit_ridge_oof(
        feature_rows,
        targets,
        folds,
        layout_ids,
        alpha_grid=alpha_grid,
        inner_fold_count=inner_fold_count,
        seed=seed,
    )
    predictions = result.predictions
    mean_target = sum(targets) / len(targets)
    ss_res = sum((target - prediction) ** 2 for target, prediction in zip(targets, predictions))
    ss_tot = sum((target - mean_target) ** 2 for target in targets)
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0.0 else 0.0
    suspicious = r2 > r2_threshold

    return PredictabilityFinding(
        diagnostic_name=diagnostic_name,
        r2=r2,
        suspicious=suspicious,
        threshold=r2_threshold,
        detail=(
            f"metadata-only out-of-fold R^2={r2:.4f} "
            f"{'EXCEEDS' if suspicious else 'is within'} the {r2_threshold} "
            f"suspicion threshold for predicting {diagnostic_name!r}"
        ),
    )
