"""The P0 capture campaign: unit enumeration, ordering, state and resume.

Authority 7.2 fixes the shape of the campaign and A4 fixes its resume unit:
``PER_(CONDITION, PLACEMENT, BLOCK); completed verified units are not
re-measured``. This module owns that structure so the runner script stays a thin
driver.

```
14 conditions  x  9 placements  x  2 ABBA replicate blocks  =  252 units
each unit = one ABBA slot sequence, P A A P or A P P A
```

**Ordering is condition-major, and that is load-bearing.** A wall material change
forces an arena rebuild (``WallCondition.cacheKeyFragment`` is in the cache key),
and a rebuild is both the slowest operation in the campaign and the one that can
leave a stale wall standing. Condition-major ordering performs exactly 14 material
transitions instead of up to 252, and every transition becomes an explicit
liveness probe rather than an unnoticed cache hit.

Within a unit the ABBA order is itself load-bearing (authority 7.2): it balances
any monotone drift in client state across the present/absent contrast. The
realised order is recorded per slot, never assumed.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence

from mineocclude.experiment_iii.authority import canonical_sha256, machine_authority
from mineocclude.experiment_iii.conditions import (
    AIR,
    ELIGIBLE_STAINED_GLASS,
    STONE,
)
from mineocclude.experiment_iii.errors import ExperimentIIIError
from mineocclude.experiment_iii.placements import PLACEMENT_COUNT, placement_coordinates
from mineocclude.experiment_iii.rve import ABBA_BLOCKS
from mineocclude.experiment_iii.schema import write_json_atomic

__all__ = [
    "MEASURED_CONDITION_COUNT",
    "P0Unit",
    "UNIT_COUNT",
    "campaign_units",
    "measured_conditions",
    "settled_frames_per_state_per_block",
    "unit_states",
    "P0CampaignState",
]

#: L0 + the twelve candidates + stone (authority 7.2).
MEASURED_CONDITION_COUNT = 14
UNIT_COUNT = MEASURED_CONDITION_COUNT * PLACEMENT_COUNT * len(ABBA_BLOCKS)


def measured_conditions() -> tuple[dict[str, str], ...]:
    """The fourteen measured conditions, in the frozen campaign order.

    L0 is measured **first** and that is required, not cosmetic: every placement's
    support mask is derived from L0 (authority 7.3 step 3) and must exist before
    any candidate is scored against it.
    """
    rows = [{"condition_key": "L0", "condition_id": "L0", "wall_block_id": AIR}]
    for block in ELIGIBLE_STAINED_GLASS:
        # A candidate is measured in the L1 slot; its scientific level is only
        # assigned later, by the deterministic selection of authority 7.6.
        rows.append(
            {"condition_key": block, "condition_id": "L1", "wall_block_id": block}
        )
    rows.append({"condition_key": "L4", "condition_id": "L4", "wall_block_id": STONE})
    if len(rows) != MEASURED_CONDITION_COUNT:
        raise ExperimentIIIError(
            "AUTHORITY_INTERNAL_INCONSISTENCY",
            f"authority 7.2 measures {MEASURED_CONDITION_COUNT} conditions, "
            f"built {len(rows)}",
        )
    return tuple(rows)


def settled_frames_per_state_per_block() -> int:
    return int(machine_authority()["p0_rve"]["min_settled_frames_per_state_per_block"])


@dataclass(frozen=True)
class P0Unit:
    """One (condition, placement, replicate block) — the A4 resume unit."""

    unit_id: str
    condition_key: str
    condition_id: str
    wall_block_id: str
    placement_index: int
    lane_x: float
    lane_y: float
    lane_z: float
    block_index: int
    abba_order: tuple[str, ...]
    order_index: int

    def as_dict(self) -> dict[str, Any]:
        body = asdict(self)
        body["abba_order"] = list(self.abba_order)
        return body

    def slots(self, frames_per_slot: int) -> list[dict[str, Any]]:
        """The ABBA slot sequence, with target presence resolved per slot."""
        return [
            {
                "slot_index": index,
                "state": state,
                "target_present": state == "P",
                "frames": frames_per_slot,
            }
            for index, state in enumerate(self.abba_order)
        ]


def campaign_units() -> tuple[P0Unit, ...]:
    """Every P0 unit, deterministically ordered condition-major."""
    placements = placement_coordinates()
    units: list[P0Unit] = []
    order = 0
    for condition in measured_conditions():
        for placement in placements:
            for block_index, abba in enumerate(ABBA_BLOCKS):
                units.append(
                    P0Unit(
                        unit_id=(
                            f"{condition['condition_key']}"
                            f"__p{placement['placement_index']}"
                            f"__b{block_index}"
                        ),
                        condition_key=condition["condition_key"],
                        condition_id=condition["condition_id"],
                        wall_block_id=condition["wall_block_id"],
                        placement_index=placement["placement_index"],
                        lane_x=placement["lane_x"],
                        lane_y=placement["lane_y"],
                        lane_z=placement["lane_z"],
                        block_index=block_index,
                        abba_order=tuple(abba),
                        order_index=order,
                    )
                )
                order += 1
    if len(units) != UNIT_COUNT:
        raise ExperimentIIIError(
            "P0_TECHNICAL_FAIL",
            f"the campaign must enumerate {UNIT_COUNT} units, built {len(units)}",
        )
    return tuple(units)


def unit_states(units: Sequence[P0Unit]) -> dict[str, int]:
    """Total settled frames the campaign will capture, for the storage plan."""
    per_state = settled_frames_per_state_per_block()
    per_slot = per_state // 2
    return {
        "units": len(units),
        "slots": len(units) * len(ABBA_BLOCKS[0]),
        "frames_per_slot": per_slot,
        "settled_frames_per_state_per_block": per_state,
        "total_settled_frames": len(units) * len(ABBA_BLOCKS[0]) * per_slot,
    }


class P0CampaignState:
    """Durable per-unit campaign state with fail-closed resume.

    A resumed campaign must not silently continue against different source or a
    different authority, so the state file records both and refuses a mismatch.
    That is the whole point of the A4 resume rule: completed *verified* units are
    not re-measured, and nothing else is trusted.
    """

    SCHEMA = "mineocclude-experiment-iii-p0-campaign-state-v1"

    def __init__(
        self,
        path: Path,
        *,
        authority_sha256: str,
        source_closure: str,
        namespace_root: Path | None = None,
    ) -> None:
        self.path = Path(path)
        self.namespace_root = namespace_root
        self.authority_sha256 = authority_sha256
        self.source_closure = source_closure
        self.units: dict[str, dict[str, Any]] = {}
        if self.path.is_file():
            self._load()

    def _load(self) -> None:
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        if raw.get("schema_version") != self.SCHEMA:
            raise ExperimentIIIError(
                "P0_TECHNICAL_FAIL",
                f"unrecognised campaign state schema {raw.get('schema_version')!r}",
            )
        if raw.get("authority_sha256") != self.authority_sha256:
            raise ExperimentIIIError(
                "PROVENANCE_AUTHORITY_DRIFT",
                "the campaign state was written under a different authority; "
                "resuming would mix two authorities in one measurement",
            )
        if raw.get("source_closure") != self.source_closure:
            raise ExperimentIIIError(
                "SOURCE_CLOSURE_DRIFT",
                "the campaign state was written by a different source closure; "
                "resuming would mix two implementations in one measurement",
            )
        self.units = dict(raw.get("units") or {})

    def save(self) -> str:
        return write_json_atomic(
            self.path,
            {
                "schema_version": self.SCHEMA,
                "authority_sha256": self.authority_sha256,
                "source_closure": self.source_closure,
                "units": self.units,
            },
            root=self.namespace_root,
        )

    def is_complete(self, unit_id: str) -> bool:
        return self.units.get(unit_id, {}).get("state") == "COMPLETE_VALIDATED_DURABLE"

    def mark_complete(self, unit: P0Unit, evidence: Mapping[str, Any]) -> None:
        self.units[unit.unit_id] = {
            "state": "COMPLETE_VALIDATED_DURABLE",
            "order_index": unit.order_index,
            "condition_key": unit.condition_key,
            "wall_block_id": unit.wall_block_id,
            "placement_index": unit.placement_index,
            "block_index": unit.block_index,
            "abba_order": list(unit.abba_order),
            "evidence": dict(evidence),
        }

    def mark_attempt(self, unit: P0Unit, blocker: str, detail: str) -> None:
        """Retained failed-attempt provenance; never overwrites a completed unit."""
        if self.is_complete(unit.unit_id):
            return
        record = self.units.setdefault(
            unit.unit_id, {"state": "ATTEMPTED", "attempts": []}
        )
        record["state"] = "ATTEMPTED"
        record.setdefault("attempts", []).append({"blocker": blocker, "detail": detail})

    def pending(self, units: Sequence[P0Unit]) -> list[P0Unit]:
        return [unit for unit in units if not self.is_complete(unit.unit_id)]

    def summary(self, units: Sequence[P0Unit]) -> dict[str, Any]:
        complete = [unit for unit in units if self.is_complete(unit.unit_id)]
        return {
            "units_total": len(units),
            "units_complete": len(complete),
            "units_pending": len(units) - len(complete),
            "resume_unit": "CONDITION_PLACEMENT_BLOCK",
            "completed_units_are_not_remeasured": True,
        }


def campaign_manifest(*, frames_per_slot: int | None = None) -> dict[str, Any]:
    """The deterministic campaign plan, hashable and reproducible."""
    units = campaign_units()
    per_state = settled_frames_per_state_per_block()
    per_slot = frames_per_slot if frames_per_slot is not None else per_state // 2
    if per_slot * 2 < per_state:
        raise ExperimentIIIError(
            "P0_TECHNICAL_FAIL",
            f"{per_slot} frames per slot gives {per_slot * 2} settled frames per "
            f"state per block, below the frozen minimum {per_state}",
        )
    rows = [unit.as_dict() for unit in units]
    total = len(units) * len(ABBA_BLOCKS[0]) * per_slot
    minimum = int(machine_authority()["p0_rve"]["min_total_settled_frames"])
    if total < minimum:
        raise ExperimentIIIError(
            "P0_TECHNICAL_FAIL",
            f"the plan captures {total} settled frames, below the frozen minimum "
            f"{minimum}",
        )
    return {
        "schema_version": "mineocclude-experiment-iii-p0-campaign-v1",
        "authority_section": "7.2, 7.10",
        "conditions_measured": MEASURED_CONDITION_COUNT,
        "placements": PLACEMENT_COUNT,
        "replicate_blocks": len(ABBA_BLOCKS),
        "unit_count": len(units),
        "abba_blocks": [list(block) for block in ABBA_BLOCKS],
        "ordering": "CONDITION_MAJOR_THEN_PLACEMENT_THEN_BLOCK",
        "ordering_rationale": (
            "a material change forces an arena rebuild; condition-major ordering "
            "performs 14 material transitions rather than up to 252, and makes "
            "every transition an explicit liveness probe"
        ),
        "l0_measured_first": True,
        "frames_per_slot": per_slot,
        "settled_frames_per_state_per_block": per_slot * 2,
        "min_settled_frames_per_state_per_block": per_state,
        "total_settled_frames": total,
        "min_total_settled_frames": minimum,
        "wall_material_transitions": MEASURED_CONDITION_COUNT,
        "units": rows,
        "units_sha256": canonical_sha256(rows),
    }
