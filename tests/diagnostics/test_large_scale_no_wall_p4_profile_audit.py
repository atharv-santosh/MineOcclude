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
SCRIPT = ROOT / "scripts/audit_large_scale_no_wall_profiles.py"
SPEC = importlib.util.spec_from_file_location("p4_audit", SCRIPT)
assert SPEC and SPEC.loader
p4 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(p4)


@pytest.fixture(scope="module")
def result():
    return p4.compute_audit()


def test_p4_reconstruction_is_complete_balanced_and_outcome_blind(result):
    audit = result["audit"]
    assert audit["accepted_trajectory_count"] == 120
    assert audit["accepted_per_layout"] == {
        f"L{index:02d}": 20 for index in range(1, 7)
    }
    assert set(audit["accepted_per_layout_direction"].values()) == {10}
    assert set(audit["accepted_per_layout_direction_profile_cell"].values()) == {2}
    assert audit["unique_spec_ids"] == audit["unique_spec_hashes"] == 120
    assert audit["activation_or_probe_inputs_used"] is False


def test_rows_ranges_variance_motion_camera_and_no_wall_all_pass(result):
    audit = result["audit"]
    gates = audit["component_gates"]
    assert audit["rows_per_trajectory"] == 60 and audit["f_common"] is True
    for key in (
        "target_ranges_finite_and_legal",
        "target_variance_each_trajectory_gt_zero",
        "motion_schedules_legal_and_exact",
        "common_f_60",
        "camera_authority",
        "no_wall_authority",
    ):
        assert gates[key] is True
    stats = result["statistics"]
    assert stats["start_range_audit_pass"] is True
    assert stats["end_range_audit_pass"] is True
    assert stats["motion_profile_audit_pass"] is True
    assert stats["profile_families_present"] == [
        "EARLY_CONSTANT",
        "FAST_TRANSIT",
        "LATE_ONSET",
        "PAUSE_RESUME",
        "TWO_SPEED",
    ]


def test_repeat_authority_is_nonidentical(result):
    audit = result["audit"]
    assert audit["repeat_ids_distinct"] is True
    assert audit["capture_seeds_distinct_within_cell"] is True
    assert audit["scientific_settings_non_identical_within_repeat_cell"] is True


def test_time_position_metrics_are_exact_and_fully_stratified(result):
    audit = result["audit"]
    correlations = audit["time_position_correlation"]
    assert correlations["normalized_time_definition"] == (
        "model_frame_idx / 59 for indices 0..59"
    )
    assert correlations["overall"] == pytest.approx(-0.0015339906194107886)
    assert set(correlations["by_profile_family"]) == {
        "EARLY_CONSTANT",
        "FAST_TRANSIT",
        "LATE_ONSET",
        "PAUSE_RESUME",
        "TWO_SPEED",
    }
    assert correlations["by_direction"] == pytest.approx(
        {
            "LEFT_TO_RIGHT": 0.6971236027712353,
            "RIGHT_TO_LEFT": -0.6928967340763685,
        }
    )
    assert len(correlations["by_layout_diagnostic_not_required_by_contract"]) == 6
    assert audit["global_absolute_correlation_pass"] is True
    assert audit["aggregate_cancellation_used_as_sole_pass"] is False


def test_frozen_similarity_calculation_is_deterministic_and_fails_exact_gate(result):
    audit = result["audit"]
    similarity = audit["pairwise_profile_similarity"]
    all_pairs = similarity["all_pairs"]
    assert all_pairs["count"] == 7140
    assert all_pairs["median"] == pytest.approx(0.9518676405187019)
    assert all_pairs["p95"] == pytest.approx(0.9907108011017317)
    assert all_pairs["max"] == pytest.approx(0.9969407626273319)
    assert all_pairs["high_similarity_count"] == 3644
    assert all_pairs["high_similarity_fraction"] == pytest.approx(0.5103641456582633)
    assert similarity["threshold_inclusive"] == 0.95
    assert similarity["maximum_fraction_high_similarity"] == 0.2
    assert audit["pairwise_profile_similarity_pass"] is False
    assert audit["trajectory_profile_confound_controlled"] is False
    repeated = p4.compute_audit()["audit"]["pairwise_profile_similarity"]
    assert repeated == similarity


def test_retry_is_immutable_and_rejected_attempt_is_excluded(result):
    retry = result["retry"]
    assert retry["status"] == "PASS"
    assert retry["rejected_attempt_count"] == 1
    assert retry["failed_attempt_number"] == 1
    assert retry["accepted_attempt_number"] == 2
    assert retry["spec_hash_unchanged"] is True
    assert retry["exact_scientific_spec_unchanged"] is True
    assert retry["failed_attempt_excluded_from_accepted_cohort"] is True
    assert retry["accepted_trajectory_duplicated"] is False


def test_stop_receipt_has_no_lock_split_or_later_phase_outputs():
    receipt = json.loads((PACKAGE / "p4_receipt.json").read_text())
    assert receipt["status"] == "STOP_AND_REPORT"
    assert receipt["accepted_cohort_lock_created"] is False
    assert receipt["safe_for_p5"] is False
    assert receipt["fresh_activations_extracted"] == 0
    assert receipt["fresh_r2_computed"] is False
    assert receipt["p5_started"] is False
    assert not (PACKAGE / "accepted_cohort.lock.json").exists()

    def nested_keys(value):
        if isinstance(value, dict):
            return set(value) | {
                key for child in value.values() for key in nested_keys(child)
            }
        if isinstance(value, list):
            return {key for child in value for key in nested_keys(child)}
        return set()

    for name in receipt["artifact_paths"]:
        path = PACKAGE / name
        assert not any(
            token in name.lower()
            for token in ("activation", "hidden_state", "probe_result", "r2_result")
        )
        if path.suffix == ".json":
            keys = nested_keys(json.loads(path.read_text()))
            assert keys.isdisjoint(
                {
                    "train_assignment",
                    "test_assignment",
                    "train_ids",
                    "test_ids",
                    "split",
                }
            )


def test_p1_p3_authority_and_protected_refs_remain_unchanged():
    assert p4.sha256_file(PACKAGE / "capture_campaign.json") == p4.CAMPAIGN_SHA256
    assert p4.sha256_file(PACKAGE / "study_design.json") == p4.STUDY_SHA256
    assert (
        subprocess.run(
            [
                "git",
                "diff",
                "--name-only",
                p4.P3_HEAD,
                "--",
                str(PACKAGE / "capture_campaign.json"),
                str(PACKAGE / "study_design.json"),
                str(PACKAGE / "capture_campaign.lock.json"),
                str(PACKAGE / "study_design.lock.json"),
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        == ""
    )
    remote = subprocess.run(
        [
            "git",
            "ls-remote",
            "origin",
            "refs/heads/exploration/visible-position-resolution-v0-1",
            "refs/heads/integration/mvp-final",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert "18c8dd0de0987d3065206a5fd7df452badb1338b" in remote
    assert "bb22364cbc4f65b788a56b60e7d6503e6226df7b" in remote
