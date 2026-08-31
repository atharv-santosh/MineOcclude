"""The nine frozen P0 placements (authority 7.2, 7.10a, 7.10e).

Authority Amendment 3 froze the nine scripted Phase 0 calibration positions on
the frozen sheep lane, ascending world-x:

```
-2.0  -1.5  -1.0  -0.5  0.0  +0.5  +1.0  +1.5  +2.0
```

They are **read from the machine authority**, never restated here, so an
authority edit changes the placements and an implementation edit cannot. The
digest is recomputed from the records and checked against the frozen
``placements_sha256``, so a silent coordinate change is
``PROVENANCE_AUTHORITY_DRIFT`` rather than a quietly different campaign.

A superseded implementation-side derivation (the endpoint-inclusive uniform
partition of the occluded corridor, digest ``a3deb1df…``) is retained in the
authority only as superseded engineering evidence.
:func:`assert_not_the_superseded_derivation` exists so nothing downstream can
pick it up by accident: it captured no frame and must never enter P2.

Sentinel selection is the deterministic left/centre/right coverage rule of
7.10e -- indices 0, 4, 8 -- fixed before any measurement existed.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from mineocclude.experiment_iii.authority import canonical_sha256, machine_authority
from mineocclude.experiment_iii.errors import ExperimentIIIError

__all__ = [
    "PLACEMENT_COUNT",
    "SUPERSEDED_PLACEMENTS_SHA256",
    "assert_not_the_superseded_derivation",
    "corridor_interval",
    "placement_coordinates",
    "placement_manifest",
    "sentinel_placement_indices",
    "sentinel_placements",
]

#: Authority 7.2 -- nine placements, frozen.
PLACEMENT_COUNT = 9

#: The derivation Amendment 3 superseded. Named so it can be refused, not used.
SUPERSEDED_PLACEMENTS_SHA256 = (
    "a3deb1df619d39ac4f1df1d54c082f61115b9a11bbbcab85b12f799755e03f6e"
)


def _p0() -> dict[str, Any]:
    return machine_authority()["p0_rve"]


def corridor_interval() -> tuple[float, float]:
    """The verified counterfactually fully occluded lane interval (authority 4.5)."""
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
    """The nine frozen placements, read from the authority and hash-checked."""
    p0 = _p0()
    xs = list(p0["placement_coordinates_lane_x"])
    if len(xs) != PLACEMENT_COUNT or p0["placements"] != PLACEMENT_COUNT:
        raise ExperimentIIIError(
            "AUTHORITY_INTERNAL_INCONSISTENCY",
            f"authority 7.10a must freeze exactly {PLACEMENT_COUNT} placements; "
            f"found {len(xs)} coordinates and placements={p0['placements']}",
        )
    if xs != sorted(xs):
        raise ExperimentIIIError(
            "AUTHORITY_INTERNAL_INCONSISTENCY",
            f"authority 7.10a freezes ASCENDING_LANE_X order; found {xs}",
        )

    low, high = corridor_interval()
    lane_y = float(p0["placement_lane_y"])
    lane_z = float(p0["placement_lane_z"])
    records: list[dict[str, Any]] = []
    for index, x in enumerate(xs):
        value = float(x)
        # Every placement must be a genuine occluded-corridor position; a frozen
        # coordinate outside it would silently measure a partially visible target.
        if not low <= value <= high:
            raise ExperimentIIIError(
                "P0_PLACEMENT_GROSS_ERROR",
                f"placement {index} at x={value} lies outside the verified "
                f"counterfactually fully occluded corridor [{low}, {high}]",
            )
        records.append(
            {
                "placement_index": index,
                "placement_id": f"P{index}",
                "lane_x": value,
                "lane_y": lane_y,
                "lane_z": lane_z,
            }
        )

    digest = canonical_sha256(records)
    frozen = str(p0["placements_sha256"])
    if digest != frozen:
        raise ExperimentIIIError(
            "PROVENANCE_AUTHORITY_DRIFT",
            f"the placement records digest to {digest}, but authority 7.10a "
            f"freezes {frozen}",
        )
    return tuple(records)


def sentinel_placement_indices() -> tuple[int, ...]:
    """The three prospectively selected sentinel placements (authority 7.10e)."""
    p0 = _p0()
    indices = tuple(int(index) for index in p0["sentinel_placement_indices"])
    expected = int(p0["sentinel_placements"])
    if len(indices) != expected:
        raise ExperimentIIIError(
            "AUTHORITY_INTERNAL_INCONSISTENCY",
            f"authority freezes {expected} sentinel placements, not {len(indices)}",
        )
    if sorted(indices) != list(indices) or not all(
        0 <= index < PLACEMENT_COUNT for index in indices
    ):
        raise ExperimentIIIError(
            "AUTHORITY_INTERNAL_INCONSISTENCY",
            f"sentinel indices must be ascending and within range; got {indices}",
        )
    return indices


def sentinel_placements() -> tuple[dict[str, Any], ...]:
    placements = placement_coordinates()
    return tuple(placements[index] for index in sentinel_placement_indices())


def assert_not_the_superseded_derivation(digest: str) -> None:
    """Refuse the superseded pre-amendment placement derivation."""
    if digest == SUPERSEDED_PLACEMENTS_SHA256:
        raise ExperimentIIIError(
            "PROVENANCE_AUTHORITY_DRIFT",
            "this is the placement derivation Authority Amendment 3 superseded; "
            "it captured no frame and may never enter P2",
        )


def placement_manifest() -> dict[str, Any]:
    """The hash-bound placement manifest P2 binds."""
    p0 = _p0()
    placements = [dict(record) for record in placement_coordinates()]
    body = {
        "schema_version": "mineocclude-experiment-iii-p0-placements-v2",
        "authority_section": "7.2, 7.10a, 7.10e",
        "authority_version": machine_authority()["authority_version"],
        "placement_count": PLACEMENT_COUNT,
        "placement_source": p0["placement_source"],
        "placement_order": p0["placement_order"],
        "placement_representation": p0["placement_representation"],
        "read_from_authority_not_restated": True,
        "outcome_blind": True,
        "corridor_min_blocks": corridor_interval()[0],
        "corridor_max_blocks": corridor_interval()[1],
        "all_placements_inside_occluded_corridor": True,
        "sentinel_placement_indices": list(sentinel_placement_indices()),
        "sentinel_selection_rule": p0["sentinel_selection_rule"],
        "sentinel_selection_is_outcome_independent": True,
        "superseded_placements_sha256": SUPERSEDED_PLACEMENTS_SHA256,
        "superseded_may_enter_p2": False,
        "placements": placements,
    }
    body["placements_sha256"] = canonical_sha256(placements)
    return body
