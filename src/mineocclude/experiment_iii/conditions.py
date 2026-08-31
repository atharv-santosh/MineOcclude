"""The five frozen conditions and the wall-material seam (authority 4.1-4.3, 3.3).

The material seam spans builder, config, command, cache key, receipt and
validator. Authority 4.1 warns that they must change together or the apparatus
fails silently, so every one of them resolves its material through this module.

Two fail-closed properties are load-bearing:

* an **unsupported registry ID refuses the episode** rather than defaulting to
  stone (``P0_CANDIDATE_ID_UNSUPPORTED`` / ``WALL_MATERIAL_MISMATCH``);
* the arena cache key **includes** ``condition_id`` and ``wall_block_id``, so a
  material transition always forces a rebuild. Without that, a stone->glass
  switch hits the cache and leaves the previous wall standing, producing a whole
  batch of captures under the wrong condition with no error
  (``WALL_CACHE_KEY_STALE`` — the highest-severity latent defect in the rig).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

from mineocclude.experiment_iii.authority import LAYOUT_01
from mineocclude.experiment_iii.errors import ExperimentIIIError
from mineocclude.experiment_iii.schema import ConditionId

__all__ = [
    "AIR",
    "STONE",
    "ELIGIBLE_STAINED_GLASS",
    "PROSPECTIVELY_EXCLUDED_MATERIALS",
    "SUPPORTED_WALL_BLOCK_IDS",
    "ConditionSpec",
    "validate_wall_block_id",
    "build_condition_map",
    "arena_cache_key",
    "as_built_wall_cells",
    "build_wall_receipt",
    "validate_wall_receipt",
]

AIR = "minecraft:air"
STONE = "minecraft:stone"

#: Authority 4.2 — exactly twelve eligible P0 stained-glass candidates.
ELIGIBLE_STAINED_GLASS = (
    "minecraft:white_stained_glass",
    "minecraft:orange_stained_glass",
    "minecraft:light_blue_stained_glass",
    "minecraft:yellow_stained_glass",
    "minecraft:lime_stained_glass",
    "minecraft:gray_stained_glass",
    "minecraft:light_gray_stained_glass",
    "minecraft:cyan_stained_glass",
    "minecraft:blue_stained_glass",
    "minecraft:brown_stained_glass",
    "minecraft:green_stained_glass",
    "minecraft:black_stained_glass",
)

#: Authority 4.3 — frozen, not reopenable. Never eligible as a scientific level.
PROSPECTIVELY_EXCLUDED_MATERIALS = (
    "minecraft:magenta_stained_glass",
    "minecraft:pink_stained_glass",
    "minecraft:purple_stained_glass",
    "minecraft:red_stained_glass",
    "minecraft:glass",
    "minecraft:glass_pane",
    "minecraft:white_stained_glass_pane",
)

#: The complete set an Experiment III episode may declare.
SUPPORTED_WALL_BLOCK_IDS = frozenset({AIR, STONE, *ELIGIBLE_STAINED_GLASS})


@dataclass(frozen=True)
class ConditionSpec:
    """One frozen condition, resolved to the runtime scene and registry ID."""

    condition_id: ConditionId
    scene: str
    wall_block_id: str
    wall_present: bool
    role: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "condition_id": self.condition_id.value,
            "scene": self.scene,
            "wall_block_id": self.wall_block_id,
            "wall_present": self.wall_present,
            "role": self.role,
        }


_ROLES = {
    ConditionId.L0: "FULLY_VISIBLE_ANCHOR",
    ConditionId.L1: "HIGH_PARTIAL_EVIDENCE",
    ConditionId.L2: "MEDIUM_PARTIAL_EVIDENCE",
    ConditionId.L3: "LOW_BUT_MEASURABLE_PARTIAL_EVIDENCE",
    ConditionId.L4: "OPAQUE_ANCHOR",
}


def validate_wall_block_id(
    block_id: str, *, condition: ConditionId | None = None
) -> str:
    """Refuse an unsupported registry ID rather than defaulting to stone."""
    if not isinstance(block_id, str) or ":" not in block_id:
        raise ExperimentIIIError(
            "P0_CANDIDATE_ID_UNSUPPORTED",
            f"wall_block_id must be a registry ID, got {block_id!r}",
        )
    if block_id in PROSPECTIVELY_EXCLUDED_MATERIALS:
        raise ExperimentIIIError(
            "P0_CANDIDATE_ID_UNSUPPORTED",
            f"{block_id} is prospectively excluded by authority 4.3 and is never "
            "eligible as an Experiment III scientific level",
        )
    if block_id not in SUPPORTED_WALL_BLOCK_IDS:
        raise ExperimentIIIError(
            "P0_CANDIDATE_ID_UNSUPPORTED",
            f"{block_id} is not a supported Experiment III wall material; the "
            "episode is refused rather than defaulting to stone",
        )
    if condition is ConditionId.L0 and block_id != AIR:
        raise ExperimentIIIError(
            "WALL_CONDITION_SCENE_MISMATCH",
            f"L0 is the no-wall anchor and must declare {AIR}, not {block_id}",
        )
    if condition is ConditionId.L4 and block_id != STONE:
        raise ExperimentIIIError(
            "WALL_CONDITION_SCENE_MISMATCH",
            f"L4 is the opaque anchor and must declare {STONE}, not {block_id}",
        )
    if condition in (ConditionId.L1, ConditionId.L2, ConditionId.L3):
        if block_id not in ELIGIBLE_STAINED_GLASS:
            raise ExperimentIIIError(
                "P0_CANDIDATE_ID_UNSUPPORTED",
                f"{condition.value} must be a P0-selected stained glass from the "
                f"twelve-candidate roster, not {block_id}",
            )
    return block_id


def build_condition_map(
    selected_ladder: Mapping[str, str] | None = None,
) -> dict[ConditionId, ConditionSpec]:
    """The five conditions of authority 4.1.

    ``selected_ladder`` supplies the P0-selected ``L1``/``L2``/``L3`` registry IDs.
    Until P0 has run they are unresolved and the partial conditions are refused
    rather than silently defaulted.
    """
    ladder = dict(selected_ladder or {})
    specs: dict[ConditionId, ConditionSpec] = {}
    for condition in ConditionId:
        if condition is ConditionId.L0:
            block_id = AIR
        elif condition is ConditionId.L4:
            block_id = STONE
        else:
            block_id = ladder.get(condition.value)
            if block_id is None:
                raise ExperimentIIIError(
                    "P0_CANDIDATE_ID_UNSUPPORTED",
                    f"{condition.value} has no P0-selected material; run P0 before "
                    "resolving the partial conditions",
                )
        validate_wall_block_id(block_id, condition=condition)
        specs[condition] = ConditionSpec(
            condition_id=condition,
            scene=condition.expected_scene,
            wall_block_id=block_id,
            wall_present=condition.wall_present,
            role=_ROLES[condition],
        )
    return specs


def arena_cache_key(
    *,
    layout_id: str,
    scene: str,
    condition_id: ConditionId | str,
    wall_block_id: str,
    wall_ortho: float,
    ortho_min: float,
    ortho_max: float,
    marker_geom_signature: str,
) -> str:
    """The arena-rebuild cache key, which MUST bind the material (C07).

    The legacy key was
    ``layoutId | scene | wallOrtho | orthoMin | orthoMax | markerGeomSignature``
    and omitted the material entirely.
    """
    condition = ConditionId(condition_id)
    validate_wall_block_id(wall_block_id, condition=condition)
    return "|".join(
        [
            layout_id,
            scene,
            condition.value,
            wall_block_id,
            repr(float(wall_ortho)),
            repr(float(ortho_min)),
            repr(float(ortho_max)),
            marker_geom_signature,
        ]
    )


def as_built_wall_cells(
    layout: Mapping[str, object] = LAYOUT_01,
) -> list[tuple[int, int, int]]:
    """The as-built wall cell set, computed from the layout (authority 3.2).

    Material-independent by construction: nothing here reads a registry ID, so
    A.8's invariance under material change holds trivially and is still tested.
    """
    import math

    axis_min = math.floor(float(layout["wall_seg_min"]))
    axis_max = math.ceil(float(layout["wall_seg_max"]))
    ortho = math.floor(
        float(layout["wall_ortho_const"]) + float(layout["wall_ortho_offset"])
    )
    lane_y = int(math.floor(float(layout["lane_y"])))
    height = 3  # ArenaBuilder.WALL_HEIGHT
    return [
        (axis, lane_y + level, ortho)
        for axis in range(axis_min, axis_max + 1)
        for level in range(height)
    ]


def build_wall_receipt(
    condition: ConditionSpec,
    observed: Mapping[tuple[int, int, int], str],
    *,
    layout: Mapping[str, object] = LAYOUT_01,
) -> dict[str, Any]:
    """Assemble the authority 3.3 wall receipt from observed per-cell states."""
    cells = as_built_wall_cells(layout)
    expected = condition.wall_block_id if condition.wall_present else AIR
    per_cell = []
    mismatches = []
    unexpected_non_air = []
    for cell in cells:
        actual = observed.get(cell, AIR)
        per_cell.append(
            {
                "cell": list(cell),
                "expected_block_id": expected,
                "observed_block_id": actual,
                "matches": actual == expected,
            }
        )
        if actual != expected:
            mismatches.append({"cell": list(cell), "expected": expected, "observed": actual})
        if not condition.wall_present and actual != AIR:
            unexpected_non_air.append({"cell": list(cell), "observed": actual})
    return {
        "schema_version": "mineocclude-experiment-iii-wall-receipt-v1",
        "condition_id": condition.condition_id.value,
        "scene": condition.scene,
        "declared_block_id": condition.wall_block_id,
        "wall_present": condition.wall_present,
        "scanned_cell_count": len(cells),
        "observed_cells": per_cell,
        "mismatch_count": len(mismatches),
        "mismatches": mismatches,
        "unexpected_non_air_count": len(unexpected_non_air),
        "unexpected_non_air": unexpected_non_air,
    }


def validate_wall_receipt(receipt: Mapping[str, Any]) -> None:
    """Zero mismatches, zero unexpected non-air, exact declared registry ID."""
    condition = ConditionId(receipt["condition_id"])
    declared = receipt["declared_block_id"]
    validate_wall_block_id(declared, condition=condition)
    if receipt["scene"] != condition.expected_scene:
        raise ExperimentIIIError(
            "WALL_CONDITION_SCENE_MISMATCH",
            f"{condition.value} expects scene {condition.expected_scene}, receipt "
            f"records {receipt['scene']}",
        )
    if receipt["mismatch_count"]:
        raise ExperimentIIIError(
            "WALL_RECEIPT_MISMATCH",
            f"{receipt['mismatch_count']} wall cells do not match {declared}: "
            f"{receipt['mismatches'][:4]}",
        )
    if receipt["unexpected_non_air_count"]:
        raise ExperimentIIIError(
            "WALL_CELL_MISMATCH",
            f"{receipt['unexpected_non_air_count']} unexpected non-air cells in a "
            f"{condition.value} arena: {receipt['unexpected_non_air'][:4]}",
        )
    if receipt["scanned_cell_count"] != len(as_built_wall_cells()):
        raise ExperimentIIIError(
            "WALL_RECEIPT_MISMATCH",
            "the wall receipt did not scan the full as-built span",
        )
