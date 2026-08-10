from __future__ import annotations

import importlib.util
import json
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = (
    ROOT / "docs/status/integration/exploratory_large_scale_no_wall_scaling_best_k_v0_1"
)
SCRIPT = ROOT / "scripts/freeze_large_scale_no_wall_p5_authority.py"
P1_SCRIPT = ROOT / "scripts/build_large_scale_no_wall_p1_authority.py"


def load_module(name: str, path: Path):
    module_spec = importlib.util.spec_from_file_location(name, path)
    assert module_spec and module_spec.loader
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return module


p5 = load_module("p5_authority", SCRIPT)
p1 = load_module("p1_replay_for_p5", P1_SCRIPT)


@pytest.fixture(scope="module")
def documents():
    return p5.build_documents()


def load(name: str) -> dict:
    return json.loads((PACKAGE / name).read_text())


def test_p4c_and_frozen_predecessor_authorities_are_preserved():
    p5.verify_protected_authority()
    assert load("p4c_receipt.json")["safe_for_p5"] is True
    assert load("p4c_receipt.json")["fresh_activations_extracted"] == 0


def test_primary_split_is_exact_v2_only_18_plus_102(documents):
    split = documents["split_authority.json"]
    test = split["fixed_test"]
    training = split["training_pool"]
    test_ids = {row["trajectory_spec_id"] for row in test["members"]}
    train_ids = {row["trajectory_spec_id"] for row in training["members"]}
    assert test["count"] == len(test_ids) == 18
    assert training["count"] == len(train_ids) == 102
    assert test_ids.isdisjoint(train_ids)
    assert len(test_ids | train_ids) == 120
    assert split["v1_primary_intersection"] == 0
    assert all(identity.startswith("fresh_vp_v2_") for identity in test_ids | train_ids)
    assert Counter(row["layout_id"] for row in test["members"]) == {
        layout: 3 for layout in p5.LAYOUTS
    }
    assert Counter(row["layout_id"] for row in training["members"]) == {
        layout: 17 for layout in p5.LAYOUTS
    }


def test_v2_compatibility_mapping_replays_literal_p1_split(documents):
    lock = load("accepted_cohort_v2.lock.json")
    algorithm = load("split_algorithm.json")
    rows = p5.split_metadata(lock["entries"])
    expected = p1.build_synthetic_split(
        rows,
        algorithm["fixed_test"]["seed"],
        algorithm["master_orderings"]["seeds"],
    )
    schedule = documents["subset_schedule.json"]
    split = documents["split_authority.json"]
    assert {row["trajectory_spec_id"] for row in expected["test"]} == {
        row["trajectory_spec_id"] for row in split["fixed_test"]["members"]
    }
    assert expected["master_rotations"] == [
        row["selected_rotation"] for row in schedule["master_orderings"]
    ]
    assert [
        [member["trajectory_spec_id"] for member in ordering]
        for ordering in expected["masters"]
    ] == [row["trajectory_spec_ids"] for row in schedule["master_orderings"]]
    assert (
        split["compatibility_mapping"][
            "detailed_shape_classes_used_as_selection_criterion"
        ]
        is False
    )


def test_fixed_test_direction_and_reporting_balance_is_frozen_output(documents):
    audit = documents["p5_balance_audit.json"]["fixed_test"]
    assert audit["direction"] == {"LEFT_TO_RIGHT": 9, "RIGHT_TO_LEFT": 9}
    assert audit["reporting_stratum"] == {
        "ASYMMETRIC_RESTART": 5,
        "DELAYED_BOUNDED_BURST": 5,
        "LONG_DWELL_RESTART": 2,
        "MULTI_DWELL_PULSE": 3,
        "TERMINAL_HOLD_RESTART": 3,
    }


def test_all_20_masters_are_complete_training_permutations(documents):
    split = documents["split_authority.json"]
    schedule = documents["subset_schedule.json"]
    training = {row["trajectory_spec_id"] for row in split["training_pool"]["members"]}
    assert len(schedule["master_orderings"]) == 20
    for master in schedule["master_orderings"]:
        assert len(master["trajectory_spec_ids"]) == 102
        assert len(set(master["trajectory_spec_ids"])) == 102
        assert set(master["trajectory_spec_ids"]) == training
        assert master["ordering_hash"] == p5.canonical_sha256(
            master["trajectory_spec_ids"]
        )


def test_62_nested_prefix_subsets_and_coverage_are_exact(documents):
    schedule = documents["subset_schedule.json"]
    audit = documents["p5_balance_audit.json"]
    masters = {
        row["master_id"]: row["trajectory_spec_ids"]
        for row in schedule["master_orderings"]
    }
    assert schedule["training_sizes"] == [5, 15, 40, 70, 100]
    assert schedule["subset_replicates"] == [20, 16, 12, 8, 6]
    assert len(schedule["subsets"]) == 62
    assert Counter(row["training_size"] for row in schedule["subsets"]) == {
        5: 20,
        15: 16,
        40: 12,
        70: 8,
        100: 6,
    }
    index = documents["split_authority.json"]["member_index"]
    for subset in schedule["subsets"]:
        assert (
            subset["trajectory_spec_ids"]
            == masters[subset["master_id"]][: subset["training_size"]]
        )
        layouts = {
            index[identity]["layout_id"] for identity in subset["trajectory_spec_ids"]
        }
        assert len(layouts) == (5 if subset["training_size"] == 5 else 6)
    assert audit["n5_omitted_layout_counts"] == {
        "L01": 4,
        "L02": 4,
        "L03": 3,
        "L04": 3,
        "L05": 3,
        "L06": 3,
    }
    assert audit["n5_omission_balance_valid"] is True
    assert audit["n_ge_15_all_layouts"] is True


def test_training_exposure_is_the_literal_frozen_schedule(documents):
    assert documents["subset_schedule.json"]["training_exposure_by_n"] == {
        "5": {"minimum": 0, "maximum": 2, "range": 2},
        "15": {"minimum": 1, "maximum": 3, "range": 2},
        "40": {"minimum": 3, "maximum": 6, "range": 3},
        "70": {"minimum": 4, "maximum": 6, "range": 2},
        "100": {"minimum": 5, "maximum": 6, "range": 1},
    }


def test_n100_has_six_distinct_predeclared_omitted_pairs(documents):
    audit = documents["p5_balance_audit.json"]
    pairs = audit["n100_omitted_pairs"]
    assert len(pairs) == 6
    assert len({tuple(pair) for pair in pairs}) == 6
    assert all(len(pair) == 2 for pair in pairs)
    assert audit["n100_distinct_omitted_pair_count"] == 6


def test_grouped_folds_partition_each_subset_without_frame_leakage(documents):
    grouped = documents["grouped_fold_authority.json"]
    subsets = {
        row["subset_id"]: row for row in documents["subset_schedule.json"]["subsets"]
    }
    assert grouped["group_unit"] == "whole_trajectory_spec_id"
    assert grouped["frame_level_split_used"] is False
    assert grouped["expected_validation_trajectories_per_fold"] == {
        "5": 1,
        "15": 3,
        "40": 8,
        "70": 14,
        "100": 20,
    }
    assert len(grouped["subsets"]) == 62
    for authority in grouped["subsets"]:
        source = subsets[authority["subset_id"]]
        folds = authority["selection_folds"]
        assert len(folds) == 5
        validation = [
            identity for fold in folds for identity in fold["validation_trajectory_ids"]
        ]
        assert len(validation) == len(set(validation)) == source["training_size"]
        assert set(validation) == set(source["trajectory_spec_ids"])
        assert {fold["validation_count"] for fold in folds} == {
            source["training_size"] // 5
        }
        ranking = authority["best_k_ranking_subfolds_by_outer_selection_fold"]
        assert len(ranking) == 5
        assert {len(subfolds) for subfolds in ranking.values()} == {4}
    assert grouped["best_k_candidates"] == [1, 4, 8, 16, 32, 64, 128]
    assert grouped["alpha_grid"] == [0.1, 1.0, 10.0, 100.0]


def test_test_guard_blocks_training_and_allows_training_pool(tmp_path, documents):
    guard = documents["test_guard.lock"]
    path = tmp_path / "test_guard.lock"
    path.write_text(json.dumps(guard))
    training_ids = [
        row["trajectory_spec_id"]
        for row in documents["split_authority.json"]["training_pool"]["members"]
    ]
    p5.enforce_test_guard(training_ids, path)
    with pytest.raises(p5.P5Error, match="fixed-test IDs"):
        p5.enforce_test_guard([guard["test_trajectory_ids"][0]], path)
    assert guard["test_count"] == len(guard["test_trajectory_ids"]) == 18


def test_canonical_null_is_master_zero_n100_and_not_executed(documents):
    null = documents["canonical_null_authority.json"]
    subset = next(
        row
        for row in documents["subset_schedule.json"]["subsets"]
        if row["subset_id"] == "n100_r00"
    )
    assert null["canonical_n"] == 100
    assert null["canonical_training_trajectory_ids"] == subset["trajectory_spec_ids"]
    assert null["canonical_subset_hash"] == subset["subset_hash"]
    assert min(null["within_layout_counts"].values()) >= 16
    assert null["within_layout_derangement_feasible"] is True
    assert null["target_null_b"] == len(null["prospective_null_seeds"]) == 49
    assert null["null_executed"] is False


def test_generated_artifacts_are_byte_deterministic_and_p6_not_started(documents):
    for name, value in documents.items():
        assert (PACKAGE / name).read_bytes() == p5.json_bytes(value)
    receipt = documents["p5_receipt.json"]
    assert receipt["fresh_activations_extracted"] == 0
    assert receipt["fresh_r2_computed"] is False
    assert receipt["p6_started"] is False
    assert receipt["safe_for_p6"] is True
    assert not list(PACKAGE.glob("p6*"))
