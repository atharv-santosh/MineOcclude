"""Focused prospective checks for the P11 derangement null."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/run_large_scale_no_wall_p11_null.py"
P1_SCRIPT = ROOT / "scripts/build_large_scale_no_wall_p1_authority.py"


def load(path: Path, name: str):
    specification = importlib.util.spec_from_file_location(name, path)
    assert specification and specification.loader
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


p11 = load(SCRIPT, "p11_runner")
p1 = load(P1_SCRIPT, "p1_authority")


def test_all_49_assignments_exactly_match_frozen_p1_algorithm_and_have_no_self_donor():
    prospective, canonical, layout_by_id = p11.authority_context()
    synthetic_rows = [
        {"trajectory_spec_id": identity, "layout_id": layout_by_id[identity]}
        for identity in canonical["canonical_training_trajectory_ids"]
    ]
    assert len(prospective["seeds"]) == 49
    for seed in prospective["seeds"]:
        observed = p11.within_layout_derangement(
            canonical["canonical_training_trajectory_ids"], layout_by_id, seed
        )
        assert observed == p1.within_layout_derangement(synthetic_rows, seed)
        assert all(recipient != donor for recipient, donor in observed.items())
        assert all(layout_by_id[recipient] == layout_by_id[donor] for recipient, donor in observed.items())


def test_null_context_copies_complete_profiles_and_leaves_test_targets_true():
    _prospective, canonical, layout_by_id = p11.authority_context()
    assignment = p11.within_layout_derangement(
        canonical["canonical_training_trajectory_ids"], layout_by_id, 6703626055086664819
    )
    context = p11.NullJobContext(assignment)
    recipient = canonical["canonical_training_trajectory_ids"][0]
    donor = assignment[recipient]
    observed = context.targets([recipient])
    expected = np.asarray(context.entry_by_id[donor]["target_authority"]["x_true_blocks"])
    assert observed.shape == (60,)
    assert np.array_equal(observed, expected)
    assert np.array_equal(context.targets(list(context.test_ids)), context.true_targets(list(context.test_ids)))


def test_manifest_scope_is_exactly_49_seeds_by_four_representations():
    prospective, canonical, _layout_by_id = p11.authority_context()
    assert prospective["B"] == 49
    assert len(prospective["seeds"]) == 49
    assert canonical["canonical_subset_id"] == "n100_r00"
    assert p11.REPRESENTATIONS == (
        "GLOBAL_MEAN",
        "FULL_TOKEN_GRID",
        "BEST_K_TOKENS",
        "COARSE_2x6",
    )
    assert p11.EXPECTED_JOBS == 196


def test_empirical_upper_tail_formula_has_frozen_plus_one_correction():
    null = [0.1] * 48 + [0.9]
    observed = 0.8
    count = sum(value >= observed for value in null)
    assert count == 1
    assert (1 + count) / (49 + 1) == 0.04
