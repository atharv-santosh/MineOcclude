from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/build_person_a_canonical_multilayout_a6_6_closure.py"
PACKAGE = ROOT / "docs/status/person_a_canonical_multilayout_a6_6_closure_v0_1"


def _load_module():
    specification = importlib.util.spec_from_file_location(
        "person_a_canonical_multilayout_a6_6_closure_test", SCRIPT
    )
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


closure = _load_module()


def test_frozen_closure_identities_are_exact() -> None:
    assert closure.EXPECTED_TRAJECTORIES == (
        "layout_01_ep12602",
        "layout_02_ep12610",
        "layout_03_ep12645",
        "layout_04_ep12626",
        "layout_05_ep12634",
    )
    assert closure.EXPECTED_LAYOUTS == (
        "layout_01",
        "layout_02",
        "layout_03",
        "layout_04",
        "layout_05",
    )
    assert closure.COLLECTION_SHA256 == (
        "a672c834e8af3fd12c735e4042951b7b90d0aeeed5b0b62790aacdf3a58c0db0"
    )
    assert closure.A_TO_B_SHA256 == (
        "9d932df3aec859b17a4bbdd2afaa31d81dcb21c2bb62db668ed4158cbb855d94"
    )
    assert closure.A_TO_E_SHA256 == (
        "75d35991f34dabc3851dd2e31dc9e2b2912fa66a776034b7ecb7932bc854575b"
    )


def test_committed_closure_package_is_self_contained_and_valid() -> None:
    if not PACKAGE.is_dir():
        pytest.skip("immutable closure is created only after the B and E receipts exist")
    result = closure.validate_closure_package(PACKAGE)
    assert result["status"] == "PASS"
    document = json.loads((PACKAGE / "a6_6_closure.json").read_bytes())
    assert document["a6_6_complete"] is True
    assert document["decision"] == {
        "person_b_positive_control_pass": True,
        "person_e_provenance_consumption_authorized": True,
        "status": "CLOSE_A6_6",
    }
    assert document["remaining_blockers"] == []


def test_b_receipt_consumer_fails_closed_on_incomplete_controls() -> None:
    document = {
        "a_to_b_handoff": {"sha256": closure.A_TO_B_SHA256},
        "activation_chunk_count": 100,
        "activation_index_count": 5,
        "activation_index_identities": [
            {"sha256": digest} for digest in closure.EXPECTED_INDEX_SHA256
        ],
        "activation_row_count": 6000,
        "collection_manifest": {"sha256": closure.COLLECTION_SHA256},
        "decision": {
            "positive_control_pass": True,
            "status": (
                "PASS_FROZEN_CANONICAL_MULTILAYOUT_VISIBLE_POSITION_"
                "POSITIVE_CONTROL"
            ),
        },
        "execution": {
            "person_a_commit": closure.PERSON_A_SUCCESSOR_COMMIT,
            "receipt_generation_recomputed_scientific_control": False,
            "scientific_execution_semantics": {
                "real_label_execution_count": 1,
                "shuffled_execution_count": 1,
            },
            "scientific_fit_performed": True,
        },
        "fold_identities": {
            "grouping_key": "layout_id",
            "inner_fold_count": 4,
            "layout_assignments": [
                {"fold_idx": fold_idx} for fold_idx in range(5)
            ],
            "outer_fold_count": 5,
        },
        "immutable": True,
        "layout_count": 5,
        "real_label_positive_control": {
            "complete": False,
            "metrics": [{} for _ in range(20)],
            "status": "COMPLETE_FROZEN_LAYOUT_GROUPED_OOF",
        },
        "remaining_blockers": [],
        "schema_version": closure.B_RECEIPT_SCHEMA,
        "shuffled_control": {
            "complete": True,
            "metrics": {
                "null_r2": [0.0] * 999,
                "extreme_null_count": 0,
                "null_r2_maximum": 0.0,
                "null_r2_mean": 0.0,
                "null_r2_minimum": 0.0,
                "p_value": 0.001,
                "p_value_rule": "add_one_greater_or_equal",
                "permutation_count": 999,
                "permutation_refit_policy": (
                    "refit_scaler_alpha_and_ridge_inside_each_permutation"
                ),
                "permutation_seed": 20260720,
                "permutation_unit": "whole_trajectory_block",
            },
            "status": "COMPLETE_FROZEN_WHOLE_TRAJECTORY_GROUPED_SHUFFLE",
        },
        "source_identity_join": {
            "activation_rows_matched": 6000,
            "frame_rows_matched": 300,
            "identity_error_count": 0,
            "pass": True,
        },
        "trajectory_count": 5,
        "trajectory_identities": [
            {"layout_id": layout, "trajectory_id": trajectory}
            for layout, trajectory in zip(
                closure.EXPECTED_LAYOUTS, closure.EXPECTED_TRAJECTORIES, strict=True
            )
        ],
    }
    with pytest.raises(closure.A66ClosureError, match="incomplete"):
        closure._validate_b_receipt(document)
