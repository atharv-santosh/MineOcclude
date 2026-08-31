"""Production drift sentinels (authority 7.9).

Three frozen sentinel placements — a fixed subset of the nine P0 placements — are
re-measured before AND after each production condition batch. Two things are
checked: the image-only RVE **order** across the sentinel placements matches P0,
and each sentinel score lies inside the Phase-1-frozen **repeatability envelope**
derived from the P0 replicate spread.

A sentinel failure is **technical, never scientific**. It invalidates only the
affected, as-yet-unmodeled capture batch and permits an exact technical retry of
that batch. It cannot change materials, target rows, the RVE definition or any
statistic, and it is never a condition-selection mechanism.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

import numpy as np

from mineocclude.experiment_iii.errors import ExperimentIIIError

__all__ = [
    "SENTINEL_PLACEMENT_COUNT",
    "SentinelEnvelope",
    "SentinelReading",
    "derive_envelope",
    "check_order",
    "check_envelope",
    "evaluate_batch_boundary",
    "invalidation_scope",
]

SENTINEL_PLACEMENT_COUNT = 3


@dataclass(frozen=True)
class SentinelEnvelope:
    """The frozen repeatability envelope for the three sentinel placements."""

    placements: tuple[int, ...]
    bounds: dict[int, tuple[float, float]]
    p0_order: tuple[int, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "placements": list(self.placements),
            "bounds": {str(k): list(v) for k, v in sorted(self.bounds.items())},
            "p0_order": list(self.p0_order),
        }


@dataclass(frozen=True)
class SentinelReading:
    """One measured sentinel batch boundary."""

    batch_index: int
    boundary: str  # "before" or "after"
    scores: dict[int, float]


def derive_envelope(
    placements: Sequence[int],
    p0_replicates: Mapping[int, Sequence[float]],
    *,
    tolerance: float = 3.0,
) -> SentinelEnvelope:
    """Derive the envelope from the P0 replicate spread at those placements."""
    chosen = tuple(sorted(placements))
    if len(chosen) != SENTINEL_PLACEMENT_COUNT:
        raise ExperimentIIIError(
            "SENTINEL_ENVELOPE_VIOLATION",
            f"exactly {SENTINEL_PLACEMENT_COUNT} sentinel placements are frozen, "
            f"got {len(chosen)}",
        )
    bounds: dict[int, tuple[float, float]] = {}
    medians: dict[int, float] = {}
    for placement in chosen:
        replicates = np.asarray(
            [float(value) for value in p0_replicates[placement]], dtype=np.float64
        )
        if replicates.size < 2:
            raise ExperimentIIIError(
                "SENTINEL_ENVELOPE_VIOLATION",
                f"placement {placement} has too few P0 replicates to derive a spread",
            )
        centre = float(np.median(replicates))
        spread = float(replicates.std(ddof=0))
        medians[placement] = centre
        half = max(tolerance * spread, 1e-9)
        bounds[placement] = (centre - half, centre + half)
    order = tuple(sorted(chosen, key=lambda p: (-medians[p], p)))
    return SentinelEnvelope(placements=chosen, bounds=bounds, p0_order=order)


def check_order(
    reading: Mapping[int, float], envelope: SentinelEnvelope
) -> bool:
    """The image-only RVE order across sentinels must match P0."""
    observed = tuple(
        sorted(envelope.placements, key=lambda p: (-float(reading[p]), p))
    )
    return observed == envelope.p0_order


def check_envelope(
    reading: Mapping[int, float], envelope: SentinelEnvelope
) -> list[int]:
    """Placements whose score falls outside the frozen envelope."""
    outside = []
    for placement in envelope.placements:
        low, high = envelope.bounds[placement]
        if not (low <= float(reading[placement]) <= high):
            outside.append(placement)
    return outside


def evaluate_batch_boundary(
    reading: SentinelReading,
    envelope: SentinelEnvelope,
    *,
    batch_capture_unit_ids: Sequence[str],
    batch_already_modeled: bool = False,
) -> dict[str, Any]:
    """Evaluate one boundary and produce the ``sentinel_receipt.json`` body."""
    missing = [p for p in envelope.placements if p not in reading.scores]
    if missing:
        raise ExperimentIIIError(
            "SENTINEL_ENVELOPE_VIOLATION",
            f"sentinel reading is missing placements {missing}",
        )
    order_ok = check_order(reading.scores, envelope)
    outside = check_envelope(reading.scores, envelope)
    blocker = None
    if not order_ok:
        blocker = "SENTINEL_ORDER_VIOLATION"
    elif outside:
        blocker = "SENTINEL_ENVELOPE_VIOLATION"

    receipt = {
        "schema_version": "mineocclude-experiment-iii-sentinel-receipt-v1",
        "authority_section": "7.9",
        "batch_index": reading.batch_index,
        "boundary": reading.boundary,
        "placements": list(envelope.placements),
        "measured_rve": {str(k): float(v) for k, v in sorted(reading.scores.items())},
        "envelope_bounds": {
            str(k): list(v) for k, v in sorted(envelope.bounds.items())
        },
        "order_check_passed": order_ok,
        "placements_outside_envelope": outside,
        "passed": blocker is None,
        "blocker": blocker,
        "failure_is_technical_not_scientific": True,
        "may_change_materials": False,
        "may_change_target_rows": False,
        "may_change_rve_definition": False,
        "may_change_any_statistic": False,
        "is_a_condition_selection_mechanism": False,
    }
    receipt["invalidation"] = invalidation_scope(
        blocker,
        batch_capture_unit_ids=batch_capture_unit_ids,
        batch_already_modeled=batch_already_modeled,
    )
    return receipt


def invalidation_scope(
    blocker: str | None,
    *,
    batch_capture_unit_ids: Sequence[str],
    batch_already_modeled: bool,
) -> dict[str, Any]:
    """A failure invalidates ONLY the affected, as-yet-unmodeled batch."""
    if blocker is None:
        return {
            "invalidated_capture_unit_ids": [],
            "exact_technical_retry_permitted": False,
            "scope": "NONE",
        }
    if batch_already_modeled:
        # Authority 7.9 scopes invalidation to the as-yet-unmodeled batch; a
        # batch that has already been modeled is escalated rather than silently
        # rewritten.
        return {
            "invalidated_capture_unit_ids": [],
            "exact_technical_retry_permitted": False,
            "scope": "ESCALATE_BATCH_ALREADY_MODELED",
            "note": (
                "sentinel invalidation applies to the as-yet-unmodeled batch "
                "only; this batch has been modeled and requires adjudication"
            ),
        }
    return {
        "invalidated_capture_unit_ids": list(batch_capture_unit_ids),
        "exact_technical_retry_permitted": True,
        "scope": "AFFECTED_UNMODELED_BATCH_ONLY",
        "other_batches_unaffected": True,
    }
