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
from mineocclude.experiment_iii.p0_bindings import sentinel_envelope
from mineocclude.experiment_iii.placements import sentinel_placement_indices

__all__ = [
    "SENTINEL_PLACEMENT_COUNT",
    "SentinelEnvelope",
    "SentinelReading",
    "derive_envelope",
    "check_order",
    "check_envelope",
    "envelope_from_artifact",
    "evaluate_batch_boundary",
    "invalidation_scope",
    "measure_batch_boundary",
    "sentinel_envelope_artifact",
]

SENTINEL_PLACEMENT_COUNT = 3


@dataclass(frozen=True)
class SentinelEnvelope:
    """The frozen repeatability envelope for the three sentinel placements."""

    placements: tuple[int, ...]
    bounds: dict[int, tuple[float, float]]
    p0_order: tuple[int, ...]
    derivations: dict[int, dict[str, Any]] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "placements": list(self.placements),
            "bounds": {str(k): list(v) for k, v in sorted(self.bounds.items())},
            "p0_order": list(self.p0_order),
            "derivations": {
                str(k): v for k, v in sorted(self.derivations.items())
            },
            "envelope_rule": "AUTHORITY_7_10E_K_TIMES_MAX_RANGE_OR_FLOOR",
            "single_implementation_of_record": "p0_bindings.sentinel_envelope",
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
) -> SentinelEnvelope:
    """Derive the envelope from the P0 replicate spread at those placements.

    The arithmetic is **not** written here. Authority 7.10e froze one formula --
    ``half_width = k * max(range, floor_fraction * centre)`` over the P0 replicate
    blocks, with ``k`` and the floor read from the machine authority -- and
    :func:`p0_bindings.sentinel_envelope` is its single implementation of record.
    An earlier version of this function used a ``3 * stdev`` envelope instead,
    which is a different rule and would have produced different production
    invalidations from the same P0 data.
    """
    chosen = tuple(sorted(int(placement) for placement in placements))
    if len(chosen) != SENTINEL_PLACEMENT_COUNT:
        raise ExperimentIIIError(
            "SENTINEL_ENVELOPE_VIOLATION",
            f"exactly {SENTINEL_PLACEMENT_COUNT} sentinel placements are frozen, "
            f"got {len(chosen)}",
        )
    bounds: dict[int, tuple[float, float]] = {}
    medians: dict[int, float] = {}
    derivations: dict[int, dict[str, Any]] = {}
    for placement in chosen:
        if placement not in p0_replicates:
            raise ExperimentIIIError(
                "SENTINEL_ENVELOPE_VIOLATION",
                f"placement {placement} has no P0 replicate scores; the envelope "
                f"cannot be derived from data that does not exist",
            )
        derived = sentinel_envelope(p0_replicates[placement])
        medians[placement] = float(derived["centre"])
        bounds[placement] = (float(derived["lower"]), float(derived["upper"]))
        derivations[placement] = derived
    order = tuple(sorted(chosen, key=lambda p: (-medians[p], p)))
    return SentinelEnvelope(
        placements=chosen, bounds=bounds, p0_order=order, derivations=derivations
    )


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


# --------------------------------------------------------------------------
# The live path: P0 produces the envelope; production consumes it
# --------------------------------------------------------------------------


def sentinel_envelope_artifact(
    placement_block_scores: Mapping[int, Sequence[float]],
    *,
    authority_binding: Mapping[str, Any],
    p0_selection_receipt_sha256: str,
) -> dict[str, Any]:
    """``P0_SENTINEL_ENVELOPE`` -- the A4 producer for the sentinel envelope.

    Called from the P0 analysis with the per-replicate-block RVE of the ladder's
    ``L1`` at each of the three frozen sentinel placements. Amendment 3 3e freezes
    the *formula* before P0 and binds the *numbers* in P2; this emits the numbers
    the moment P0 replicates exist, and marks them unbound until P2 does so.
    """
    frozen = tuple(sentinel_placement_indices())
    supplied = tuple(sorted(int(key) for key in placement_block_scores))
    if supplied != frozen:
        raise ExperimentIIIError(
            "SENTINEL_ENVELOPE_VIOLATION",
            f"the sentinel envelope must be derived at the frozen placements "
            f"{list(frozen)}, not {list(supplied)}; sentinel selection is the "
            f"deterministic left/centre/right rule of 7.10e and is never chosen "
            f"from which placements later looked steadiest",
        )
    envelope = derive_envelope(frozen, placement_block_scores)
    return {
        "schema_version": "mineocclude-experiment-iii-p0-sentinel-envelope-v1",
        "authority_section": "7.9, 7.10e",
        "authority_binding": dict(authority_binding),
        "p0_selection_receipt_sha256": p0_selection_receipt_sha256,
        "sentinel_placement_indices": list(frozen),
        "sentinel_selection_rule": (
            "DETERMINISTIC_COVERAGE_LEFT_CENTRE_RIGHT_OF_THE_NINE_FROZEN_PLACEMENTS"
        ),
        "sentinel_selection_is_outcome_independent": True,
        "envelope": envelope.as_dict(),
        "inputs": "P0_REPLICATE_VARIATION_ONLY",
        "derived_from_production_measurement": False,
        "formula_frozen_before_p0": True,
        "numeric_envelope_bound_in": "P2",
        "numeric_envelope_bound": False,
    }


def envelope_from_artifact(artifact: Mapping[str, Any]) -> SentinelEnvelope:
    """Rehydrate the frozen envelope from ``P0_SENTINEL_ENVELOPE.json``.

    Production may not invent an envelope: without a P0-derived one there is no
    reference to compare a batch boundary against, and a boundary that cannot
    fail is not a check. Hence the fail-closed refusals here.
    """
    if not isinstance(artifact, Mapping) or "envelope" not in artifact:
        raise ExperimentIIIError(
            "SENTINEL_ENVELOPE_VIOLATION",
            "no P0-derived sentinel envelope was supplied; a batch boundary "
            "cannot be validated without one",
        )
    body = artifact["envelope"]
    placements = tuple(int(value) for value in body["placements"])
    frozen = tuple(sentinel_placement_indices())
    if placements != frozen:
        raise ExperimentIIIError(
            "SENTINEL_ENVELOPE_VIOLATION",
            f"the envelope names placements {list(placements)}, not the frozen "
            f"{list(frozen)}",
        )
    bounds = {
        int(key): (float(value[0]), float(value[1]))
        for key, value in body["bounds"].items()
    }
    return SentinelEnvelope(
        placements=placements,
        bounds=bounds,
        p0_order=tuple(int(value) for value in body["p0_order"]),
        derivations={
            int(key): dict(value)
            for key, value in (body.get("derivations") or {}).items()
        },
    )


def measure_batch_boundary(
    *,
    batch_index: int,
    boundary: str,
    scores: Mapping[int, float],
    envelope_artifact: Mapping[str, Any] | None,
    batch_capture_unit_ids: Sequence[str],
    authority_sha256: str,
    batch_already_modeled: bool = False,
) -> dict[str, Any]:
    """The live production-capture entry point for one condition-batch boundary.

    This is what a capture runner calls before and after each condition batch. It
    fails closed on a missing envelope, on an envelope bound to a different
    authority, and on a reading that omits a frozen sentinel placement -- none of
    which may be waved through, because a sentinel check that cannot fail is not
    evidence that the apparatus has not drifted.
    """
    if boundary not in ("before", "after"):
        raise ExperimentIIIError(
            "SENTINEL_ENVELOPE_VIOLATION",
            f"a sentinel boundary is 'before' or 'after', not {boundary!r}",
        )
    if envelope_artifact is None:
        raise ExperimentIIIError(
            "SENTINEL_ENVELOPE_VIOLATION",
            "production capture requires the P0-derived sentinel envelope bound "
            "in P2; it does not exist, so no batch boundary can be validated",
        )
    bound_authority = str(
        (envelope_artifact.get("authority_binding") or {}).get("AUTHORITY_SHA256", "")
    )
    if bound_authority and bound_authority != authority_sha256:
        raise ExperimentIIIError(
            "PROVENANCE_AUTHORITY_DRIFT",
            f"the sentinel envelope was derived under authority {bound_authority} "
            f"and this capture runs under {authority_sha256}",
        )
    envelope = envelope_from_artifact(envelope_artifact)
    reading = SentinelReading(
        batch_index=int(batch_index),
        boundary=boundary,
        scores={int(key): float(value) for key, value in scores.items()},
    )
    receipt = evaluate_batch_boundary(
        reading,
        envelope,
        batch_capture_unit_ids=batch_capture_unit_ids,
        batch_already_modeled=batch_already_modeled,
    )
    receipt["authority_sha256"] = authority_sha256
    receipt["envelope_source"] = "P0_SENTINEL_ENVELOPE"
    return receipt
