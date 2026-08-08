from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/run_person_b_canonical_positive_control.py"
SPEC = importlib.util.spec_from_file_location(
    "run_person_b_canonical_positive_control", SCRIPT
)
assert SPEC is not None and SPEC.loader is not None
runner = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = runner
SPEC.loader.exec_module(runner)


def test_single_canonical_layout_fails_closed_before_both_controls() -> None:
    blockers, real, shuffled = runner.execution_eligibility(
        ["layout_01"], ["layout_01_ep12602"]
    )

    assert blockers == [runner.BLOCKER_LAYOUTS, runner.BLOCKER_SHUFFLE]
    assert real == {
        "attempted": True,
        "complete": False,
        "metrics": [],
        "status": "NOT_RUN_INSUFFICIENT_FROZEN_LAYOUT_GROUPS",
    }
    assert shuffled == {
        "attempted": True,
        "complete": False,
        "metrics": [],
        "status": "NOT_RUN_INSUFFICIENT_WHOLE_TRAJECTORY_GROUPS",
    }


def test_receipt_schema_preserves_frozen_fold_and_decision() -> None:
    document = {
        "schema_version": runner.RECEIPT_SCHEMA,
        "immutable": True,
        "a_output_bundle_valid": True,
        "a_to_b_handoff_valid": True,
        "activation_index_valid": True,
        "activation_row_count": 1200,
        "source_identity_join_pass": True,
        "trajectory_id": "layout_01_ep12602",
        "episode_id": 12602,
        "decision": {
            "positive_control_pass": False,
            "status": "STOP_FOR_DIAGNOSIS_INSUFFICIENT_FROZEN_GROUPS",
        },
        "real_label_positive_control": {"complete": False, "metrics": []},
        "shuffled_control": {"complete": False, "metrics": []},
        "remaining_blockers": [runner.BLOCKER_LAYOUTS, runner.BLOCKER_SHUFFLE],
        "fold_identities": {
            "grouping_key": "layout_id",
            "available_outer_fold_indices": [2],
            "unavailable_outer_fold_indices": [0, 1, 3, 4],
        },
    }

    runner.validate_receipt(document)


def test_receipt_rejects_invented_single_layout_pass() -> None:
    document = {
        "schema_version": runner.RECEIPT_SCHEMA,
        "immutable": True,
        "a_output_bundle_valid": True,
        "a_to_b_handoff_valid": True,
        "activation_index_valid": True,
        "activation_row_count": 1200,
        "source_identity_join_pass": True,
        "trajectory_id": "layout_01_ep12602",
        "episode_id": 12602,
        "decision": {
            "positive_control_pass": True,
            "status": "PASS",
        },
        "real_label_positive_control": {"complete": True, "metrics": []},
        "shuffled_control": {"complete": True, "metrics": []},
        "remaining_blockers": [],
        "fold_identities": {
            "grouping_key": "layout_id",
            "available_outer_fold_indices": [2],
            "unavailable_outer_fold_indices": [0, 1, 3, 4],
        },
    }

    with pytest.raises(
        runner.CanonicalPositiveControlError,
        match="fail-closed execution decision",
    ):
        runner.validate_receipt(document)


def test_committed_b_to_a_receipt_is_valid_and_canonical() -> None:
    path = (
        ROOT
        / "docs/status/"
        "person_b_canonical_positive_control_layout_01_ep12602_v0_1/"
        "b_to_a_receipt.json"
    )
    document = runner._load_object(path, "committed B-to-A receipt")

    runner.validate_receipt(document)
    assert document["activation_artifact_count"] == 21
    assert document["source_hashes"]["activation_index_sha256"] == (
        runner.EXPECTED_INDEX_SHA256
    )
    assert document["execution"]["scientific_fit_performed"] is False
