"""Frozen production capture order (authority 8.1) — the balanced Latin rotation.

25 identities x 5 conditions = 125 captures, executed as five blocks of five
identities. Within a block all five identities are captured under one condition
before the material is switched; condition order follows a cyclic five-period
Latin square across blocks, so each condition appears exactly once per block and
exactly once per period. That yields 25 condition batches and therefore at most
25 wall-material transitions.

Wall switching is minimized **only** by this frozen design. Reordering captures at
runtime to avoid a rebuild is ``CAPTURE_ORDER_VIOLATION``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

from mineocclude.experiment_iii.authority import OUTER_FOLDS
from mineocclude.experiment_iii.conditions import ConditionSpec
from mineocclude.experiment_iii.errors import ExperimentIIIError
from mineocclude.experiment_iii.schema import ConditionId, capture_unit_id

__all__ = [
    "LATIN_SQUARE",
    "CaptureUnit",
    "latin_square",
    "build_capture_schedule",
    "validate_capture_order",
    "condition_batches",
]

#: The cyclic five-period Latin square of authority 8.1. Row = block, column =
#: period. Block k is outer fold k.
LATIN_SQUARE: tuple[tuple[ConditionId, ...], ...] = tuple(
    tuple(tuple(ConditionId)[(block + period) % 5] for period in range(5))
    for block in range(5)
)


def latin_square() -> list[list[str]]:
    return [[condition.value for condition in row] for row in LATIN_SQUARE]


@dataclass(frozen=True)
class CaptureUnit:
    """One production capture, in frozen execution order."""

    order_index: int
    block: int
    period: int
    condition_id: str
    identity: str
    priority_rank: int
    episode_id: int
    capture_unit_id: str
    wall_block_id: str
    scene: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "order_index": self.order_index,
            "block": self.block,
            "period": self.period,
            "condition_id": self.condition_id,
            "identity": self.identity,
            "priority_rank": self.priority_rank,
            "episode_id": self.episode_id,
            "capture_unit_id": self.capture_unit_id,
            "wall_block_id": self.wall_block_id,
            "scene": self.scene,
        }


def build_capture_schedule(
    production: Sequence[Mapping[str, Any]],
    conditions: Mapping[ConditionId, ConditionSpec],
) -> list[CaptureUnit]:
    """The deterministic 125-unit production order.

    Blocks partition the identities by outer fold (block ``k`` = outer fold ``k``);
    identity order inside a block is ascending ``priority_rank``.
    """
    by_fold: dict[int, list[Mapping[str, Any]]] = {}
    for row in production:
        if row.get("outer_fold") is None:
            raise ExperimentIIIError(
                "COHORT_MATRIX_INCONSISTENT",
                f"{row['identity']} has no outer fold; pilots are not scheduled",
            )
        by_fold.setdefault(int(row["outer_fold"]), []).append(row)
    if sorted(by_fold) != list(range(OUTER_FOLDS)):
        raise ExperimentIIIError(
            "COHORT_MATRIX_INCONSISTENT",
            f"expected outer folds 0..{OUTER_FOLDS - 1}, got {sorted(by_fold)}",
        )
    for fold, members in by_fold.items():
        members.sort(key=lambda row: int(row["priority_rank"]))
        if len(members) != 5:
            raise ExperimentIIIError(
                "COHORT_MATRIX_INCONSISTENT",
                f"outer fold {fold} holds {len(members)} identities, expected 5",
            )

    schedule: list[CaptureUnit] = []
    order = 0
    for block in range(OUTER_FOLDS):
        for period in range(5):
            condition = LATIN_SQUARE[block][period]
            spec = conditions[condition]
            for row in by_fold[block]:
                schedule.append(
                    CaptureUnit(
                        order_index=order,
                        block=block,
                        period=period,
                        condition_id=condition.value,
                        identity=str(row["identity"]),
                        priority_rank=int(row["priority_rank"]),
                        episode_id=int(row["episode_id"]),
                        capture_unit_id=capture_unit_id(str(row["identity"]), condition),
                        wall_block_id=spec.wall_block_id,
                        scene=spec.scene,
                    )
                )
                order += 1
    if len(schedule) != 125:
        raise ExperimentIIIError(
            "COHORT_MATRIX_INCONSISTENT",
            f"production schedule holds {len(schedule)} captures, expected 125",
        )
    return schedule


def condition_batches(schedule: Sequence[CaptureUnit]) -> list[dict[str, Any]]:
    """The 25 condition batches, each a (block, period) run of five captures.

    Sentinels are measured before and after each of these boundaries, and each
    boundary is at most one wall-material transition.
    """
    batches: list[dict[str, Any]] = []
    for unit in schedule:
        key = (unit.block, unit.period)
        if not batches or (batches[-1]["block"], batches[-1]["period"]) != key:
            batches.append(
                {
                    "batch_index": len(batches),
                    "block": unit.block,
                    "period": unit.period,
                    "condition_id": unit.condition_id,
                    "wall_block_id": unit.wall_block_id,
                    "scene": unit.scene,
                    "capture_unit_ids": [],
                }
            )
        batches[-1]["capture_unit_ids"].append(unit.capture_unit_id)
    if len(batches) != 25:
        raise ExperimentIIIError(
            "CAPTURE_ORDER_VIOLATION",
            f"expected 25 condition batches, got {len(batches)}",
        )
    return batches


def validate_capture_order(schedule: Sequence[CaptureUnit]) -> dict[str, Any]:
    """Refuse a reordered schedule and prove the Latin balance."""
    if len(schedule) != 125:
        raise ExperimentIIIError(
            "CAPTURE_ORDER_VIOLATION", f"expected 125 captures, got {len(schedule)}"
        )
    if [unit.order_index for unit in schedule] != list(range(125)):
        raise ExperimentIIIError(
            "CAPTURE_ORDER_VIOLATION", "capture order indices are not contiguous"
        )
    seen = {unit.capture_unit_id for unit in schedule}
    if len(seen) != 125:
        raise ExperimentIIIError(
            "CAPTURE_ORDER_VIOLATION", "capture unit ids are not unique"
        )

    # Each condition exactly once per block and exactly once per period.
    for block in range(OUTER_FOLDS):
        per_block = {
            unit.condition_id
            for unit in schedule
            if unit.block == block
        }
        if per_block != {condition.value for condition in ConditionId}:
            raise ExperimentIIIError(
                "CAPTURE_ORDER_VIOLATION",
                f"block {block} does not contain each condition exactly once",
            )
    for period in range(5):
        per_period = {
            unit.condition_id for unit in schedule if unit.period == period
        }
        if per_period != {condition.value for condition in ConditionId}:
            raise ExperimentIIIError(
                "CAPTURE_ORDER_VIOLATION",
                f"period {period} does not contain each condition exactly once",
            )

    # Every identity is captured under all five conditions, exactly once each.
    per_identity: dict[str, list[str]] = {}
    for unit in schedule:
        per_identity.setdefault(unit.identity, []).append(unit.condition_id)
    for identity, seen_conditions in per_identity.items():
        if sorted(seen_conditions) != sorted(c.value for c in ConditionId):
            raise ExperimentIIIError(
                "CAPTURE_ORDER_VIOLATION",
                f"{identity} is not captured under all five conditions exactly once",
            )

    batches = condition_batches(schedule)
    transitions = sum(
        1
        for previous, current in zip(batches, batches[1:], strict=False)
        if previous["wall_block_id"] != current["wall_block_id"]
    )
    return {
        "captures": len(schedule),
        "condition_batches": len(batches),
        "identities": len(per_identity),
        "wall_material_transitions": transitions,
        "max_wall_material_transitions": 25,
        "latin_square": latin_square(),
        "balanced_per_block": True,
        "balanced_per_period": True,
    }
