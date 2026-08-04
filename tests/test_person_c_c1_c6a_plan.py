from __future__ import annotations

from scripts.person_c.prepare_c1_5_c6a import (
    bundle_digest,
    derive_c6a_rows,
    target_configuration,
    validate_c6a_rows,
)


def _source_row(order: int, layout: str = "layout_01") -> dict[str, str]:
    return {"collection_order": str(order), "set": "core", "scene": "normal",
            "layout_id": layout, "v": "1.0", "q": "0.05",
            "hidden_frames": "4", "max_ticks": "300", "warmup": "60"}


def test_new_episode_ids_and_seeds_are_deterministic_and_unique() -> None:
    rows = derive_c6a_rows([_source_row(index) for index in range(66)])
    assert len({row["episode_id"] for row in rows}) == 66
    assert len({row["seed"] for row in rows}) == 66
    assert rows[0]["episode_id"] == 12601


def test_plan_rejects_duplicate_ids() -> None:
    rows = derive_c6a_rows([_source_row(index) for index in range(66)])
    rows[1]["episode_id"] = rows[0]["episode_id"]
    assert "duplicate episode ids" in validate_c6a_rows(rows, {"layout_01"})


def test_plan_rejects_unknown_layouts() -> None:
    rows = derive_c6a_rows([_source_row(index) for index in range(66)])
    rows[5]["layout_id"] = "layout_99"
    assert "unknown layout" in validate_c6a_rows(rows, {"layout_01"})


def test_plan_rejects_c6b_rows() -> None:
    rows = derive_c6a_rows([_source_row(index) for index in range(66)])
    rows[0]["set"] = "c6b_pilot"
    assert "C6B row included" in validate_c6a_rows(rows, {"layout_01"})


def test_bundle_digest_is_order_independent_but_content_bound() -> None:
    a = {"path": "a", "size_bytes": 1, "sha256": "1" * 64}
    b = {"path": "b", "size_bytes": 2, "sha256": "2" * 64}
    assert bundle_digest([a, b]) == bundle_digest([b, a])
    changed = dict(b, size_bytes=3)
    assert bundle_digest([a, b]) != bundle_digest([a, changed])


def test_target_configuration_is_bound_to_the_named_layout() -> None:
    layout = {"target_start": {"world_xyz": [-6.0, 4.0, 6.0]}}
    assert target_configuration(layout, True)["start_world_xyz"] == [-6.0, 4.0, 6.0]
    assert target_configuration(layout, True)["exact_count"] == 1
    assert target_configuration(layout, False)["exact_count"] == 0
