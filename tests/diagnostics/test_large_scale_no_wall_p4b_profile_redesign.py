from __future__ import annotations

import hashlib
import importlib.util
import json
from collections import Counter
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = (
    ROOT / "docs/status/integration/exploratory_large_scale_no_wall_scaling_best_k_v0_1"
)
DESIGN_SCRIPT = ROOT / "scripts/design_large_scale_no_wall_profiles_v2.py"
RUNNER_SCRIPT = ROOT / "scripts/run_large_scale_no_wall_campaign.py"


def load_module(name: str, path: Path):
    module_spec = importlib.util.spec_from_file_location(name, path)
    assert module_spec and module_spec.loader
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return module


p4b = load_module("p4b_profile_redesign", DESIGN_SCRIPT)
runner = load_module("p4b_campaign_runner", RUNNER_SCRIPT)


def load(name: str) -> dict:
    return json.loads((PACKAGE / name).read_text())


@pytest.fixture(scope="module")
def campaign() -> dict:
    return load("capture_campaign_v2.json")


@pytest.fixture(scope="module")
def audit() -> dict:
    return load("p4b_offline_profile_audit.json")


@pytest.fixture(scope="module")
def deterministic_replay(tmp_path_factory):
    output = tmp_path_factory.mktemp("p4b-replay")
    result = p4b.generate_artifacts(output)
    return output, result


def test_protected_p1_p4_and_p4a_authorities_are_byte_preserved():
    observed = p4b.verify_protected_authority()
    assert (
        observed[
            "docs/status/integration/"
            "exploratory_large_scale_no_wall_scaling_best_k_v0_1/"
            "capture_campaign.json"
        ]
        == p4b.ORIGINAL_CAMPAIGN_SHA256
    )
    assert load("p4_receipt.json")["status"] == "STOP_AND_REPORT"
    assert load("p4a_receipt.json")["genuine_profile_diversity_failure"] is True


def test_simulator_is_exact_on_all_preserved_runtime_trajectories():
    equivalence = p4b.verify_old_runtime_equivalence()
    assert equivalence["status"] == "EXACT"
    assert equivalence["trajectory_count"] == 120
    assert equivalence["row_count"] == 7200
    assert equivalence["maximum_absolute_error_blocks"] == 0.0
    assert equivalence["old_pair_count"] == 7140
    assert equivalence["old_high_abs_r_ge_0_95_count"] == 3644


def test_repaired_campaign_lock_and_every_spec_hash_replay(campaign):
    source = PACKAGE / "capture_campaign_v2.json"
    lock = load("capture_campaign_v2.lock.json")
    assert p4b.sha256_file(source) == lock["source_sha256"]
    assert source.stat().st_size == lock["source_byte_size"]
    assert lock["source_sha256"] == runner.REPAIRED_CAMPAIGN_SHA256
    assert lock["original_campaign_sha256"] == p4b.ORIGINAL_CAMPAIGN_SHA256
    for spec in campaign["trajectory_specs"]:
        body = dict(spec)
        claimed = body.pop("spec_hash")
        assert p4b.canonical_sha256(body) == claimed


def test_campaign_is_balanced_across_layout_direction_shape_and_reporting_cells(
    campaign,
):
    specs = campaign["trajectory_specs"]
    assert len(specs) == 120
    assert len({spec["trajectory_spec_id"] for spec in specs}) == 120
    assert len({spec["spec_hash"] for spec in specs}) == 120
    assert Counter(spec["layout_id"] for spec in specs) == {
        layout: 20 for layout in p4b.LAYOUTS
    }
    assert Counter((spec["layout_id"], spec["direction"]) for spec in specs) == {
        (layout, direction): 10
        for layout in p4b.LAYOUTS
        for direction in ("LEFT_TO_RIGHT", "RIGHT_TO_LEFT")
    }
    assert set(Counter(spec["trajectory_shape_class"] for spec in specs).values()) == {
        6
    }
    assert set(
        Counter(
            (spec["layout_id"], spec["trajectory_shape_class"]) for spec in specs
        ).values()
    ) == {1}
    assert set(
        Counter(
            (spec["layout_id"], spec["direction"], spec["profile_family"])
            for spec in specs
        ).values()
    ) == {2}


def test_all_specs_are_dense_monotonic_multi_dwell_and_legally_simulated(campaign):
    for spec in campaign["trajectory_specs"]:
        runner.validate_profile_semantics(spec)
        commands = p4b.commands_for_spec(spec)
        nonzero = commands[commands != 0.0]
        sign = 1.0 if spec["direction"] == "LEFT_TO_RIGHT" else -1.0
        assert np.all(np.sign(nonzero) == sign)
        assert spec["commanded_direction_reversal_count"] == 0
        assert len(spec["exact_speed_schedule"]) >= 5
        assert np.any(commands == 0.0)
        profile, clamp_count = p4b.simulate_profile(spec, track_clamps=True)
        assert len(profile) == 60
        assert clamp_count == 0
        assert np.ptp(profile) >= p4b.MIN_TARGET_RANGE
        assert np.var(profile) >= p4b.MIN_TARGET_VARIANCE
        assert np.isclose(
            profile[-1],
            spec["end_position_authority"]["expected_axis_position_blocks"],
            atol=1e-12,
        )


def test_repaired_audit_has_strong_margin_and_stratified_evidence(audit):
    similarity = audit["profile_similarity"]
    assert similarity["all_pairs"]["pair_count"] == 7140
    assert similarity["all_pairs"]["high_abs_r_ge_0_95_count"] == 130
    assert similarity["all_pairs"]["high_abs_r_ge_0_95_proportion"] == pytest.approx(
        0.018207282913165267
    )
    assert similarity["all_pairs"]["high_abs_r_ge_0_95_proportion"] <= 0.10
    assert similarity["command_only_all_pairs_auxiliary"][
        "high_abs_r_ge_0_95_proportion"
    ] == pytest.approx(0.0773109243697479)
    assert similarity["same_direction"]["pair_count"] == 3540
    assert similarity["opposite_direction"]["pair_count"] == 3600
    assert similarity["same_shape_class"]["pair_count"] == 300
    assert similarity["different_shape_class"]["pair_count"] == 6840
    assert abs(audit["time_position_correlation"]["overall"]) <= 0.10
    assert (
        audit["time_position_correlation"]["aggregate_cancellation_not_sole_pass"]
        is True
    )
    assert all(audit["component_gates"].values())


def test_original_camera_no_wall_and_core_experiment_authority_are_unchanged(campaign):
    original = load("capture_campaign.json")
    for layout in p4b.LAYOUTS:
        old = next(
            spec for spec in original["trajectory_specs"] if spec["layout_id"] == layout
        )
        new = next(
            spec for spec in campaign["trajectory_specs"] if spec["layout_id"] == layout
        )
        assert new["camera_viewpoint_authority"] == old["camera_viewpoint_authority"]
        assert (
            new["sheep_camera_distance_authority"]
            == old["sheep_camera_distance_authority"]
        )
        assert new["model_authority_references"] == old["model_authority_references"]
        assert (
            new["expected_source_frame_count"]
            == old["expected_source_frame_count"]
            == 60
        )
        assert (
            new["expected_eligible_row_count"]
            == old["expected_eligible_row_count"]
            == 60
        )
        assert new["scene"] == old["scene"] == "NO_WALL"
        assert new["no_wall"] is old["no_wall"] is True
    assert p4b.sha256_file(PACKAGE / "study_design.json") == p4b.STUDY_SHA256


def test_successor_campaign_is_accepted_by_the_existing_orchestrator_path(campaign):
    authority = runner.CampaignAuthority(PACKAGE / "capture_campaign_v2.json")
    dry_run = runner.dry_run(authority, "D")
    assert dry_run["status"] == "PASS"
    assert dry_run["cumulative_count"] == 120
    assert dry_run["per_layout"] == {layout: 20 for layout in p4b.LAYOUTS}
    assert set(dry_run["profiles"]) == set(p4b.REPORTING_FAMILIES)
    assert len(campaign["campaign_order"]) == 120


def test_full_design_and_lock_generation_are_byte_deterministic(deterministic_replay):
    output, result = deterministic_replay
    assert result["selected_candidate_ids"] == list(p4b.EXPECTED_SELECTED_CANDIDATE_IDS)
    assert result["repaired_high_pair_count"] == 130
    for name in (
        "capture_campaign_v2.json",
        "capture_campaign_v2.lock.json",
        "trajectory_profile_design_v2.json",
        "p4b_offline_profile_audit.json",
        "p4b_receipt.json",
    ):
        assert (
            hashlib.sha256((output / name).read_bytes()).hexdigest()
            == hashlib.sha256((PACKAGE / name).read_bytes()).hexdigest()
        )


def test_receipt_forbids_capture_reuse_and_p5():
    receipt = load("p4b_receipt.json")
    assert receipt["status"] == "PASS_REPAIRED_CAMPAIGN_FROZEN"
    assert receipt["old_capture_reuse_in_primary"] is False
    assert receipt["new_minecraft_capture_started"] is False
    assert receipt["new_trajectories_captured"] == 0
    assert receipt["fresh_activations_extracted"] == 0
    assert receipt["fresh_r2_computed"] is False
    assert receipt["train_test_split_created"] is False
    assert receipt["p5_started"] is False
    assert receipt["safe_for_repaired_capture"] is True
    assert receipt["safe_for_p5"] is False
