"""The nine frozen P0 placements (authority 7.2, completing an A1 obligation).

Authority 7.2 freezes the *count* and the *span* -- "**9**, frozen, spanning the
target corridor; coordinates frozen by A1 and bound in P2" -- and delegates the
coordinates themselves to A1. The A1 ``p0_manifest.json`` recorded
``placements: 9`` but never materialised the coordinates, so this module supplies
them under the authority's own constraint.

**The corridor is not a free choice.** The authority freezes and marks as
*verified* the counterfactually fully occluded lane interval
``[-3.49, 4.49]`` (machine authority ``visibility_semantics.
verified_counterfactual_fully_occluded_lane_interval_blocks``). That interval is
precisely "the target corridor": the span of lane positions at which the target's
counterfactual extent is fully behind the wall footprint, which is the region P0
must characterise and the region every production target row lives in. The nine
placements are therefore the **endpoint-inclusive uniform partition** of that
interval:

```
x_i = corridor_min + i * (corridor_max - corridor_min) / 8      i = 0..8
```

Every value is computed from the frozen interval, never hard-coded, so a change
to the frozen geometry fails closed rather than silently disagreeing (the same
rule authority 3.2 imposes on the as-built wall volume). The construction has no
tunable: nine points, both endpoints included, uniform spacing. It is
outcome-blind by construction -- it is fixed before any frame is captured and
depends on no measurement.

The lane's other two coordinates are the frozen sheep lane of authority 3.1
(``y = 4``, ``z = 6``); a placement never leaves the lane.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from mineocclude.experiment_iii.authority import (
    canonical_sha256,
    machine_authority,
)
from mineocclude.experiment_iii.errors import ExperimentIIIError

__all__ = [
    "PLACEMENT_COUNT",
    "corridor_interval",
    "placement_coordinates",
    "placement_manifest",
    "sentinel_placement_indices",
]

#: Authority 7.2 -- nine placements, frozen.
PLACEMENT_COUNT = 9


def corridor_interval() -> tuple[float, float]:
    """The frozen, verified counterfactually fully occluded lane interval."""
    semantics = machine_authority()["visibility_semantics"]
    interval = semantics["verified_counterfactual_fully_occluded_lane_interval_blocks"]
    if len(interval) != 2 or not interval[0] < interval[1]:
        raise ExperimentIIIError(
            "AUTHORITY_INTERNAL_INCONSISTENCY",
            f"the frozen occluded lane interval is not an ordered pair: {interval}",
        )
    return float(interval[0]), float(interval[1])


@lru_cache(maxsize=1)
def placement_coordinates() -> tuple[dict[str, Any], ...]:
    """The nine placements, computed from the frozen corridor.

    Endpoint-inclusive uniform partition; the midpoint lands on the lane centre.
    """
    low, high = corridor_interval()
    lane = machine_authority()["apparatus"]["sheep_lane"]
    step = (high - low) / (PLACEMENT_COUNT - 1)
    placements = []
    for index in range(PLACEMENT_COUNT):
        x = low + index * step
        if not low - 1e-9 <= x <= high + 1e-9:
            raise ExperimentIIIError(
                "P0_PLACEMENT_GROSS_ERROR",
                f"placement {index} at x={x} left the frozen corridor [{low}, {high}]",
            )
        placements.append(
            {
                "placement_index": index,
                "placement_id": f"P{index}",
                "lane_x": x,
                "lane_y": float(lane["y"]),
                "lane_z": float(lane["z"]),
            }
        )
    return tuple(placements)


def sentinel_placement_indices() -> tuple[int, ...]:
    """The three drift-sentinel placements of authority 7.9.

    Deterministically the first, middle and last placement, so the sentinel set
    brackets the corridor rather than sampling one end of it.
    """
    count = machine_authority()["p0_rve"]["sentinel_placements"]
    if count != 3:
        raise ExperimentIIIError(
            "AUTHORITY_INTERNAL_INCONSISTENCY",
            f"authority 7.9 freezes 3 sentinel placements, not {count}",
        )
    return (0, PLACEMENT_COUNT // 2, PLACEMENT_COUNT - 1)


def placement_manifest() -> dict[str, Any]:
    """The hash-bound placement manifest P2 binds."""
    low, high = corridor_interval()
    placements = list(placement_coordinates())
    body = {
        "schema_version": "mineocclude-experiment-iii-p0-placements-v1",
        "authority_section": "7.2",
        "placement_count": PLACEMENT_COUNT,
        "corridor_source": (
            "visibility_semantics."
            "verified_counterfactual_fully_occluded_lane_interval_blocks"
        ),
        "corridor_min_blocks": low,
        "corridor_max_blocks": high,
        "corridor_span_blocks": high - low,
        "spacing_blocks": (high - low) / (PLACEMENT_COUNT - 1),
        "construction": "ENDPOINT_INCLUSIVE_UNIFORM_PARTITION_OF_THE_FROZEN_CORRIDOR",
        "computed_not_hard_coded": True,
        "outcome_blind": True,
        "sentinel_placement_indices": list(sentinel_placement_indices()),
        "placements": placements,
    }
    body["placements_sha256"] = canonical_sha256(placements)
    return body
