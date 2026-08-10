from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = (
    ROOT / "docs/status/integration/exploratory_large_scale_no_wall_scaling_best_k_v0_1"
)
SCRIPT = ROOT / "scripts/diagnose_large_scale_no_wall_profile_gate.py"
SPEC = importlib.util.spec_from_file_location("p4a_diagnosis", SCRIPT)
assert SPEC and SPEC.loader
p4a = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(p4a)


@pytest.fixture(scope="module")
def diagnosis():
    return p4a.compute_diagnosis()["diagnosis"]


def test_all_pairs_are_exhaustively_direction_decomposed(diagnosis):
    strata = diagnosis["pair_strata"]
    assert diagnosis["total_pairs"] == 7140
    assert strata["same_direction"]["pair_count"] == 3540
    assert strata["opposite_direction"]["pair_count"] == 3600
    assert 3540 + 3600 == 7140
    assert diagnosis["high_abs_r_total"] == 3644
    assert diagnosis["high_abs_r_same_direction"] == 1805
    assert diagnosis["high_abs_r_opposite_direction"] == 1839
    assert 1805 + 1839 == 3644


def test_signed_direction_results_disprove_conflation_as_primary_cause(diagnosis):
    same = diagnosis["pair_strata"]["same_direction"]
    opposite = diagnosis["pair_strata"]["opposite_direction"]
    assert same["r_ge_positive_0_95_count"] == 1805
    assert same["r_ge_positive_0_95_proportion"] == pytest.approx(0.5098870056497176)
    assert same["r_le_negative_0_95_count"] == 0
    assert opposite["r_le_negative_0_95_count"] == 1839
    assert opposite["r_le_negative_0_95_proportion"] == pytest.approx(
        0.5108333333333334
    )
    assert opposite["r_ge_positive_0_95_count"] == 0
    assert (
        diagnosis["direction_conflation_hypothesis"]["supported_as_primary_explanation"]
        is False
    )


def test_within_direction_redundancy_is_high_within_and_between_families(diagnosis):
    strata = diagnosis["pair_strata"]
    same_family = strata["same_direction_same_profile_family"]
    different_family = strata["same_direction_different_profile_family"]
    assert same_family["pair_count"] == 660
    assert same_family["r_ge_positive_0_95_count"] == 422
    assert same_family["r_ge_positive_0_95_proportion"] == pytest.approx(
        0.6393939393939394
    )
    assert different_family["pair_count"] == 2880
    assert different_family["r_ge_positive_0_95_count"] == 1383
    assert different_family["r_ge_positive_0_95_proportion"] == pytest.approx(
        0.48020833333333335
    )
    assert (
        diagnosis["scientific_intent_assessment"][
            "five_families_remain_too_stereotyped_within_direction"
        ]
        is True
    )


def test_optional_layout_and_repeat_decompositions_are_complete(diagnosis):
    strata = diagnosis["pair_strata"]
    assert strata["same_layout"]["pair_count"] == 1140
    assert strata["different_layout"]["pair_count"] == 6000
    assert strata["same_layout_same_direction"]["pair_count"] == 540
    assert strata["same_layout_opposite_direction"]["pair_count"] == 600
    assert strata["same_repeat_index_descriptive_only"]["pair_count"] == 3540
    assert strata["different_repeat_index_descriptive_only"]["pair_count"] == 3600


def test_plausible_same_direction_amendment_also_fails_frozen_threshold(diagnosis):
    candidate = diagnosis["plausible_amended_rule_diagnostic"]
    assert candidate["result_count"] == 1805
    assert candidate["pair_count"] == 3540
    assert candidate["result_fraction"] == pytest.approx(0.5098870056497176)
    assert candidate["status"] == "FAIL"
    assert candidate["amendment_not_justified"] is True
    assert diagnosis["selected_response"] == (
        "ORIGINAL_GATE_VALID_REAL_DIVERSITY_FAILURE"
    )
    assert diagnosis["genuine_profile_diversity_failure"] is True
    assert diagnosis["abs_correlation_direction_conflation"] == (
        "PRESENT_BUT_NOT_GATE_DECISIVE"
    )


def test_no_amendment_lock_capture_or_later_phase_work_was_created(diagnosis):
    receipt = json.loads((PACKAGE / "p4a_receipt.json").read_text())
    assert receipt["status"] == "STOP_AND_REPORT"
    assert receipt["amendment_created"] is False
    assert receipt["accepted_cohort_lock_created"] is False
    assert receipt["capture_cohort_changed"] is False
    assert receipt["trajectory_specs_changed"] is False
    assert receipt["model_outcomes_available"] is False
    assert receipt["fresh_activations_extracted"] == 0
    assert receipt["fresh_r2_computed"] is False
    assert receipt["train_test_split_created"] is False
    assert receipt["safe_for_p5"] is False
    assert receipt["recapture_required"] is False
    assert not (PACKAGE / "accepted_cohort.lock.json").exists()
    assert not list(PACKAGE.glob("*amendment*.json"))
    assert (
        diagnosis["pair_rows_sha256"]
        == p4a.compute_diagnosis()["diagnosis"]["pair_rows_sha256"]
    )


def test_original_p4_and_frozen_authorities_are_preserved(diagnosis):
    p4 = p4a.load_p4_module()
    persisted = json.loads((PACKAGE / "p4a_profile_gate_diagnosis.json").read_text())
    for name, expected in persisted["original_p4_artifact_sha256"].items():
        assert p4.sha256_file(PACKAGE / name) == expected
    changed_authority = subprocess.run(
        [
            "git",
            "diff",
            "--name-only",
            "222c41637381b208b2abd96776d376b428383b60",
            "--",
            str(PACKAGE / "profile_audit_contract.json"),
            str(PACKAGE / "capture_campaign.json"),
            str(PACKAGE / "study_design.json"),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert changed_authority == ""
