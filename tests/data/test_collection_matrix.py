"""Locked MVP matrix construction tests (C7.1 preparation)."""

import mineocclude.contracts  # noqa: F401  (pre-existing import-order cycle)
from mineocclude.data.collection_matrix import build_matrix, command_blocks


def test_matrix_has_exactly_66_planned_cells_with_correct_factors():
    matrix = build_matrix()
    assert len(matrix) == 66
    counts = matrix.set.value_counts().to_dict()
    assert counts == {"core": 48, "nowall": 6, "nosheep": 6, "sentinel": 6}
    core = matrix[matrix.set == "core"]
    assert sorted(core.v.unique()) == [1.0, 2.0]
    assert sorted(core.q.unique()) == [0.02, 0.20]
    assert sorted(core.hidden_frames.unique()) == [4, 16]
    assert sorted(matrix.layout_id.unique()) == [
        f"layout_0{i}" for i in range(1, 7)
    ]


def test_identities_and_seeds_are_unique_and_deterministic():
    a, b = build_matrix(), build_matrix()
    assert a.episode_id.nunique() == 66
    assert a.seed.nunique() == 66
    assert list(a.episode_id) == list(b.episode_id)  # deterministic order
    assert list(a.seed) == list(b.seed)


def test_collection_order_is_shuffled_not_planned_order():
    matrix = build_matrix()
    # The balanced interleave must not equal the raw construction order
    # (episode_id ascending) — the historical bug this guards against.
    assert list(matrix.episode_id) != sorted(matrix.episode_id)
    assert list(matrix.collection_order) == list(range(66))


def test_command_blocks_cover_every_trajectory():
    matrix = build_matrix()
    text = command_blocks(matrix)
    assert text.count("mineocclude start ") == 66
    for layout in matrix.layout_id.unique():
        assert layout in text
