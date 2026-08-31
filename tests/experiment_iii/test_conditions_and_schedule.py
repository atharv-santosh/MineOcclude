"""I03 / I04 — the wall-material seam and the frozen capture order.

Covers A.8, A.9, the cache-key and material-switch defects (C07), the wall
receipt, the Latin balance and capture-order determinism.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from mineocclude.experiment_iii.authority import LAYOUT_01, REPOSITORY_ROOT
from mineocclude.experiment_iii.capture_schedule import (
    LATIN_SQUARE,
    build_capture_schedule,
    condition_batches,
    latin_square,
    validate_capture_order,
)
from mineocclude.experiment_iii.conditions import (
    AIR,
    ELIGIBLE_STAINED_GLASS,
    PROSPECTIVELY_EXCLUDED_MATERIALS,
    STONE,
    arena_cache_key,
    as_built_wall_cells,
    build_condition_map,
    build_wall_receipt,
    validate_wall_block_id,
    validate_wall_receipt,
)
from mineocclude.experiment_iii.errors import ExperimentIIIError
from mineocclude.experiment_iii.schema import ConditionId, read_jsonl

LADDER = {
    "L1": "minecraft:white_stained_glass",
    "L2": "minecraft:lime_stained_glass",
    "L3": "minecraft:blue_stained_glass",
}
FABRIC = (
    REPOSITORY_ROOT
    / "fabric"
    / "mineocclude-mod"
    / "src"
    / "main"
    / "java"
    / "com"
    / "mineocclude"
    / "server"
)


@pytest.fixture(scope="module")
def conditions():
    return build_condition_map(LADDER)


# --------------------------------------------------------------------------
# Authority 4.1-4.3 — the five conditions and the roster
# --------------------------------------------------------------------------

def test_five_conditions_with_the_frozen_scenes_and_materials(conditions):
    assert set(conditions) == set(ConditionId)
    assert conditions[ConditionId.L0].scene == "NO_WALL"
    assert conditions[ConditionId.L0].wall_block_id == AIR
    assert conditions[ConditionId.L0].wall_present is False
    assert conditions[ConditionId.L4].scene == "NORMAL"
    assert conditions[ConditionId.L4].wall_block_id == STONE
    for level in (ConditionId.L1, ConditionId.L2, ConditionId.L3):
        assert conditions[level].scene == "NORMAL"
        assert conditions[level].wall_block_id in ELIGIBLE_STAINED_GLASS
        assert conditions[level].wall_present is True


def test_roster_has_exactly_twelve_candidates():
    assert len(ELIGIBLE_STAINED_GLASS) == 12
    assert len(set(ELIGIBLE_STAINED_GLASS)) == 12
    assert all(name.endswith("_stained_glass") for name in ELIGIBLE_STAINED_GLASS)


@pytest.mark.parametrize("excluded", PROSPECTIVELY_EXCLUDED_MATERIALS)
def test_prospectively_excluded_materials_are_refused(excluded):
    with pytest.raises(ExperimentIIIError) as caught:
        validate_wall_block_id(excluded, condition=ConditionId.L2)
    assert caught.value.blocker == "P0_CANDIDATE_ID_UNSUPPORTED"


def test_target_adjacent_hues_are_excluded():
    for hue in ("magenta", "pink", "purple", "red"):
        assert f"minecraft:{hue}_stained_glass" not in ELIGIBLE_STAINED_GLASS


# --------------------------------------------------------------------------
# A.9 — unsupported ID refuses rather than defaulting to stone
# --------------------------------------------------------------------------

def test_unsupported_registry_id_refuses_the_episode():
    with pytest.raises(ExperimentIIIError) as caught:
        validate_wall_block_id("minecraft:obsidian", condition=ConditionId.L2)
    assert caught.value.blocker == "P0_CANDIDATE_ID_UNSUPPORTED"
    assert "defaulting to stone" in caught.value.message


def test_malformed_registry_id_is_refused():
    for bad in ("stone", "", "minecraft-stone", None):
        with pytest.raises(ExperimentIIIError):
            validate_wall_block_id(bad, condition=ConditionId.L2)


def test_anchor_conditions_pin_their_materials():
    with pytest.raises(ExperimentIIIError) as caught:
        validate_wall_block_id(STONE, condition=ConditionId.L0)
    assert caught.value.blocker == "WALL_CONDITION_SCENE_MISMATCH"
    with pytest.raises(ExperimentIIIError):
        validate_wall_block_id(AIR, condition=ConditionId.L4)
    with pytest.raises(ExperimentIIIError):
        validate_wall_block_id(STONE, condition=ConditionId.L2)


def test_partial_conditions_refuse_when_p0_has_not_run():
    with pytest.raises(ExperimentIIIError) as caught:
        build_condition_map({})
    assert caught.value.blocker == "P0_CANDIDATE_ID_UNSUPPORTED"


# --------------------------------------------------------------------------
# A.8 — wall coordinates are invariant under material change
# --------------------------------------------------------------------------

def test_wall_cells_are_identical_for_every_material():
    reference = as_built_wall_cells()
    # ArenaBuilder places whole blocks at axis floor(-2.5)..ceil(2.5) = -3..3,
    # i.e. 7 columns x 3 levels. Those 7 blocks occupy the continuous span
    # [-3, 4), which is why the extent geometry's face bound is 4.0.
    assert len(reference) == 7 * 3 == 21
    assert min(cell[0] for cell in reference) == -3
    assert max(cell[0] for cell in reference) == 3
    assert sorted({cell[1] for cell in reference}) == [4, 5, 6]
    for _material in (STONE, AIR, *ELIGIBLE_STAINED_GLASS):
        assert as_built_wall_cells() == reference


def test_wall_cells_move_under_a_perturbed_layout():
    shifted = as_built_wall_cells(dict(LAYOUT_01, wall_seg_min=-4.5, wall_seg_max=4.5))
    assert shifted != as_built_wall_cells()
    assert min(cell[0] for cell in shifted) == -5


# --------------------------------------------------------------------------
# C07 — the arena cache key binds the material
# --------------------------------------------------------------------------

def _key(condition: ConditionId, block_id: str) -> str:
    return arena_cache_key(
        layout_id="layout_01",
        scene=condition.expected_scene,
        condition_id=condition,
        wall_block_id=block_id,
        wall_ortho=2.5,
        ortho_min=-8.5,
        ortho_max=9.0,
        marker_geom_signature="null/null/null/null",
    )


def test_cache_key_includes_condition_and_wall_block_id():
    key = _key(ConditionId.L2, "minecraft:lime_stained_glass")
    assert "L2" in key
    assert "minecraft:lime_stained_glass" in key


def test_material_switch_forces_a_rebuild():
    """A stone->glass switch must NOT hit the cache (WALL_CACHE_KEY_STALE)."""
    stone = _key(ConditionId.L4, STONE)
    glass = _key(ConditionId.L2, "minecraft:lime_stained_glass")
    assert stone != glass


def test_two_glass_conditions_are_distinguished():
    first = _key(ConditionId.L1, "minecraft:white_stained_glass")
    second = _key(ConditionId.L2, "minecraft:lime_stained_glass")
    assert first != second


def test_legacy_cache_key_shape_would_have_collided():
    """The superseded key omitted material, so L2-glass and L4-stone collided."""
    legacy = "layout_01|NORMAL|2.5|-8.5|9.0|null/null/null/null"
    assert _key(ConditionId.L4, STONE) != legacy
    assert _key(ConditionId.L2, "minecraft:lime_stained_glass") != legacy


def test_cache_key_refuses_an_unsupported_material():
    with pytest.raises(ExperimentIIIError):
        _key(ConditionId.L2, "minecraft:obsidian")


# --------------------------------------------------------------------------
# Authority 3.3 — the wall receipt
# --------------------------------------------------------------------------

def test_wall_receipt_is_clean_for_a_correct_arena(conditions):
    spec = conditions[ConditionId.L2]
    observed = {cell: spec.wall_block_id for cell in as_built_wall_cells()}
    receipt = build_wall_receipt(spec, observed)
    validate_wall_receipt(receipt)
    assert receipt["declared_block_id"] == spec.wall_block_id
    assert receipt["mismatch_count"] == 0
    assert receipt["unexpected_non_air_count"] == 0
    assert receipt["scanned_cell_count"] == len(as_built_wall_cells())


def test_a_single_mismatched_cell_is_detected(conditions):
    spec = conditions[ConditionId.L2]
    cells = as_built_wall_cells()
    observed = {cell: spec.wall_block_id for cell in cells}
    observed[cells[7]] = STONE
    receipt = build_wall_receipt(spec, observed)
    with pytest.raises(ExperimentIIIError) as caught:
        validate_wall_receipt(receipt)
    assert caught.value.blocker == "WALL_RECEIPT_MISMATCH"
    assert receipt["mismatch_count"] == 1


def test_stale_wall_standing_under_l0_is_detected(conditions):
    """The exact failure C07 exists to prevent: a wall left standing for L0."""
    spec = conditions[ConditionId.L0]
    observed = {cell: STONE for cell in as_built_wall_cells()}
    receipt = build_wall_receipt(spec, observed)
    with pytest.raises(ExperimentIIIError) as caught:
        validate_wall_receipt(receipt)
    assert caught.value.blocker == "WALL_RECEIPT_MISMATCH"


def test_l0_receipt_is_clean_when_the_cells_are_air(conditions):
    spec = conditions[ConditionId.L0]
    observed = {cell: AIR for cell in as_built_wall_cells()}
    receipt = build_wall_receipt(spec, observed)
    validate_wall_receipt(receipt)
    assert receipt["declared_block_id"] == AIR
    assert receipt["unexpected_non_air_count"] == 0


# --------------------------------------------------------------------------
# The Fabric seam changed together (authority 4.1 warning)
# --------------------------------------------------------------------------

def test_fabric_wall_condition_class_exists_and_holds_the_roster():
    source = (FABRIC / "WallCondition.java").read_text(encoding="utf-8")
    for material in ELIGIBLE_STAINED_GLASS:
        assert material in source, material
    assert "refusing the episode rather than defaulting to stone" in source


def test_fabric_arena_builder_no_longer_hardcodes_stone():
    source = (FABRIC / "ArenaBuilder.java").read_text(encoding="utf-8")
    assert "cfg.condition.wallState()" in source
    assert "BlockState wall = Blocks.STONE.getDefaultState()" not in source


def test_fabric_cache_key_includes_the_condition_fragment():
    source = (FABRIC / "EpisodeManager.java").read_text(encoding="utf-8")
    key_line = next(
        line for line in source.splitlines() if "String key = cfg.layoutId" in line
    )
    assert "cfg.condition.cacheKeyFragment()" in key_line


def test_fabric_wall_receipt_declares_the_condition_material():
    source = (FABRIC / "EpisodeManager.java").read_text(encoding="utf-8")
    assert 'wall.addProperty("declared_block_id", cfg.condition.wallBlockId);' in source
    assert 'cfg.buildWall() ? "minecraft:stone" : "minecraft:air"' not in source


def test_fabric_startspec_no_longer_refuses_non_normal_scenes():
    source = (FABRIC / "MineOccludeServer.java").read_text(encoding="utf-8")
    assert "startspec requires scene mode normal" not in source
    assert "WallCondition.of(conditionId, wallBlockId)" in source
    assert "condition.scene" in source


# --------------------------------------------------------------------------
# Authority 8.1 — the frozen capture order
# --------------------------------------------------------------------------

@pytest.fixture(scope="module")
def production():
    path = REPOSITORY_ROOT / "docs" / "experiment_iii" / "cohort"
    manifest = path / "production_identity_manifest.jsonl"
    if not manifest.is_file():
        pytest.skip("cohort not materialized")
    return read_jsonl(manifest)


def test_latin_square_is_the_frozen_cyclic_square():
    assert latin_square() == [
        ["L0", "L1", "L2", "L3", "L4"],
        ["L1", "L2", "L3", "L4", "L0"],
        ["L2", "L3", "L4", "L0", "L1"],
        ["L3", "L4", "L0", "L1", "L2"],
        ["L4", "L0", "L1", "L2", "L3"],
    ]


def test_schedule_is_125_captures_in_25_batches(production, conditions):
    schedule = build_capture_schedule(production, conditions)
    report = validate_capture_order(schedule)
    assert report["captures"] == 125
    assert report["condition_batches"] == 25
    assert report["identities"] == 25
    assert report["wall_material_transitions"] <= report["max_wall_material_transitions"]


def test_schedule_is_deterministic(production, conditions):
    first = build_capture_schedule(production, conditions)
    second = build_capture_schedule(production, conditions)
    assert [unit.as_dict() for unit in first] == [unit.as_dict() for unit in second]


def test_each_batch_is_one_condition_over_five_identities(production, conditions):
    schedule = build_capture_schedule(production, conditions)
    for batch in condition_batches(schedule):
        assert len(batch["capture_unit_ids"]) == 5
        suffix = "__" + batch["condition_id"]
        assert all(unit.endswith(suffix) for unit in batch["capture_unit_ids"])


def test_identity_order_within_a_block_is_ascending_priority_rank(
    production, conditions
):
    schedule = build_capture_schedule(production, conditions)
    for batch_index in range(25):
        units = [unit for unit in schedule if unit.order_index // 5 == batch_index]
        ranks = [unit.priority_rank for unit in units]
        assert ranks == sorted(ranks)


def test_reordered_schedule_is_refused(production, conditions):
    schedule = build_capture_schedule(production, conditions)
    shuffled = list(reversed(schedule))
    with pytest.raises(ExperimentIIIError) as caught:
        validate_capture_order(shuffled)
    assert caught.value.blocker == "CAPTURE_ORDER_VIOLATION"


def test_block_partitions_by_outer_fold(production, conditions):
    schedule = build_capture_schedule(production, conditions)
    fold_of = {row["identity"]: row["outer_fold"] for row in production}
    for unit in schedule:
        assert fold_of[unit.identity] == unit.block
