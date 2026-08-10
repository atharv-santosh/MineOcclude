from __future__ import annotations

import hashlib
import importlib.util
import json
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = (
    ROOT / "docs/status/integration/exploratory_large_scale_no_wall_scaling_best_k_v0_1"
)
SCRIPT = ROOT / "scripts/audit_repair_large_scale_no_wall_p5a_exposure.py"
SPEC = importlib.util.spec_from_file_location("p5a_exposure", SCRIPT)
assert SPEC and SPEC.loader
p5a = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(p5a)


def load(name: str) -> dict:
    return json.loads((PACKAGE / name).read_text())


@pytest.fixture(scope="module")
def repaired():
    return p5a.build_repaired_documents()


def test_arithmetic_lower_bound_is_range_one_at_every_n():
    assert p5a.arithmetic_lower_bounds() == {
        "5": {
            "pool_size": 102,
            "replicate_count": 20,
            "total_selections": 100,
            "ideal_low_exposure": 0,
            "ideal_high_exposure": 1,
            "ideal_low_exposure_trajectory_count": 2,
            "ideal_high_exposure_trajectory_count": 100,
            "unconstrained_minimum_range": 1,
        },
        "15": {
            "pool_size": 102,
            "replicate_count": 16,
            "total_selections": 240,
            "ideal_low_exposure": 2,
            "ideal_high_exposure": 3,
            "ideal_low_exposure_trajectory_count": 66,
            "ideal_high_exposure_trajectory_count": 36,
            "unconstrained_minimum_range": 1,
        },
        "40": {
            "pool_size": 102,
            "replicate_count": 12,
            "total_selections": 480,
            "ideal_low_exposure": 4,
            "ideal_high_exposure": 5,
            "ideal_low_exposure_trajectory_count": 30,
            "ideal_high_exposure_trajectory_count": 72,
            "unconstrained_minimum_range": 1,
        },
        "70": {
            "pool_size": 102,
            "replicate_count": 8,
            "total_selections": 560,
            "ideal_low_exposure": 5,
            "ideal_high_exposure": 6,
            "ideal_low_exposure_trajectory_count": 52,
            "ideal_high_exposure_trajectory_count": 50,
            "unconstrained_minimum_range": 1,
        },
        "100": {
            "pool_size": 102,
            "replicate_count": 6,
            "total_selections": 600,
            "ideal_low_exposure": 5,
            "ideal_high_exposure": 6,
            "ideal_low_exposure_trajectory_count": 12,
            "ideal_high_exposure_trajectory_count": 90,
            "unconstrained_minimum_range": 1,
        },
    }


def test_full_constraint_milp_constructs_optimal_range_one_schedule(repaired):
    audit = repaired["p5a_exposure_feasibility_audit.json"]
    assert audit["full_constraint_feasibility_result"] == (
        "FEASIBLE_RANGE_ONE_AT_EVERY_N_WITH_ALL_FROZEN_CONSTRAINTS"
    )
    assert audit["selected_response"] == (
        "CURRENT_SCHEDULE_EXPOSURE_IMBALANCE_AVOIDABLE"
    )
    assert audit["repair_performed"] is True
    assert audit["optimization"]["optimal"] is True
    assert audit["optimization"]["variable_count"] == 6324
    assert audit["optimization"]["constraint_count"] == 5787
    assert audit["optimization"]["retained_original_memberships"] == 1955
    assert audit["optimization"]["total_anchor_memberships"] == 1980
    assert all(value["range"] == 1 for value in audit["final_exposure_by_n"].values())


def test_repaired_materialized_artifacts_are_byte_deterministic(repaired):
    for name, value in repaired.items():
        assert (PACKAGE / name).read_bytes() == p5a.json_bytes(value)


def test_fixed_test_training_pool_guard_and_null_are_byte_unchanged():
    for name in (
        "split_authority.json",
        "test_guard.lock",
        "canonical_null_authority.json",
    ):
        assert p5a.sha256_file(PACKAGE / name) == p5a.ORIGINAL_P5_HASHES[name]
    split = load("split_authority.json")
    assert split["fixed_test"]["count"] == 18
    assert split["training_pool"]["count"] == 102
    assert split["train_test_overlap"] == 0
    assert split["v1_primary_intersection"] == 0


def test_every_repaired_subset_is_nested_and_preserves_balance_envelope(repaired):
    historical = p5a.p5.build_documents()
    original_subsets = {
        row["subset_id"]: row for row in historical["subset_schedule.json"]["subsets"]
    }
    schedule = repaired["subset_schedule.json"]
    split = historical["split_authority.json"]
    index = split["member_index"]
    masters = {
        row["master_id"]: row["trajectory_spec_ids"]
        for row in schedule["master_orderings"]
    }
    fields = ("layout_id", "direction", "reporting_stratum", "repeat_id")
    for subset in schedule["subsets"]:
        assert (
            subset["trajectory_spec_ids"]
            == masters[subset["master_id"]][: subset["training_size"]]
        )
        old_rows = [
            index[identity]
            for identity in original_subsets[subset["subset_id"]]["trajectory_spec_ids"]
        ]
        new_rows = [index[identity] for identity in subset["trajectory_spec_ids"]]
        for field in fields:
            categories = {row[field] for row in index.values()}
            old = Counter(row[field] for row in old_rows)
            new = Counter(row[field] for row in new_rows)
            low = min(old[category] for category in categories)
            high = max(old[category] for category in categories)
            assert all(low <= new[category] <= high for category in categories)


def test_layout_coverage_and_n100_pairs_remain_frozen(repaired):
    schedule = repaired["subset_schedule.json"]
    split = load("split_authority.json")
    index = split["member_index"]
    train_ids = {row["trajectory_spec_id"] for row in split["training_pool"]["members"]}
    omitted_layouts: Counter[str] = Counter()
    omitted_pairs = []
    for subset in schedule["subsets"]:
        layouts = {
            index[identity]["layout_id"] for identity in subset["trajectory_spec_ids"]
        }
        if subset["training_size"] == 5:
            assert len(layouts) == 5
            omitted_layouts.update(set(p5a.p5.LAYOUTS) - layouts)
        else:
            assert layouts == set(p5a.p5.LAYOUTS)
        if subset["training_size"] == 100:
            omitted_pairs.append(
                frozenset(train_ids - set(subset["trajectory_spec_ids"]))
            )
    assert omitted_layouts == {
        "L01": 4,
        "L02": 4,
        "L03": 3,
        "L04": 3,
        "L05": 3,
        "L06": 3,
    }
    assert len(omitted_pairs) == len(set(omitted_pairs)) == 6
    original = p5a.p5.build_documents()["p5_balance_audit.json"]
    assert {frozenset(pair) for pair in original["n100_omitted_pairs"]} == set(
        omitted_pairs
    )


def test_grouped_and_best_k_fold_authority_tracks_repaired_subsets(repaired):
    schedule = {
        row["subset_id"]: row for row in repaired["subset_schedule.json"]["subsets"]
    }
    grouped = repaired["grouped_fold_authority.json"]
    assert grouped["frame_level_split_used"] is False
    assert grouped["group_unit"] == "whole_trajectory_spec_id"
    for authority in grouped["subsets"]:
        source = schedule[authority["subset_id"]]
        folds = authority["selection_folds"]
        validation = [
            identity for fold in folds for identity in fold["validation_trajectory_ids"]
        ]
        assert len(folds) == 5
        assert len(validation) == len(set(validation)) == source["training_size"]
        assert set(validation) == set(source["trajectory_spec_ids"])
        ranking = authority["best_k_ranking_subfolds_by_outer_selection_fold"]
        assert len(ranking) == 5
        assert {len(rows) for rows in ranking.values()} == {4}


def test_p5a_provenance_hashes_original_and_repaired_authorities(repaired):
    receipt = repaired["p5a_receipt.json"]
    assert receipt["status"] == "PASS_PROSPECTIVE_EXPOSURE_SCHEDULE_REPAIRED"
    assert receipt["original_p5_artifact_sha256"] == dict(
        sorted(p5a.ORIGINAL_P5_HASHES.items())
    )
    for name, expected in receipt["resulting_p5_artifact_sha256"].items():
        assert hashlib.sha256((PACKAGE / name).read_bytes()).hexdigest() == expected
    assert receipt["model_outcomes_available"] is False
    assert receipt["fresh_activations_extracted"] == 0
    assert receipt["fresh_r2_computed"] is False
    assert receipt["p6_started"] is False
    assert receipt["safe_for_p6"] is True
    assert not list(PACKAGE.glob("p6*"))
