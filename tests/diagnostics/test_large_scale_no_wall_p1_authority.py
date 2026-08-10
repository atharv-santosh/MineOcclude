from __future__ import annotations

import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNNER_PATH = ROOT / "scripts/build_large_scale_no_wall_p1_authority.py"
SPEC = importlib.util.spec_from_file_location("large_scale_no_wall_p1", RUNNER_PATH)
assert SPEC is not None and SPEC.loader is not None
p1 = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = p1
SPEC.loader.exec_module(p1)

PACKAGE = (
    ROOT / "docs/status/integration/"
    "exploratory_large_scale_no_wall_scaling_best_k_v0_1"
)


def artifact(name: str):
    return json.loads((PACKAGE / name).read_text(encoding="utf-8"))


def test_generated_authority_replays_byte_semantically() -> None:
    p1.check_committed_outputs()


def test_literal_model_ridge_and_row_authorities_are_frozen() -> None:
    design = artifact("study_design.json")
    assert design["model_authority"] == {
        "checkpoint_path": "/home/sagemaker-user/MineWorld-Assets-Pinned/checkpoints/700M_16f.ckpt",
        "checkpoint_sha256_inherited_not_recomputed": "a92c311baf49bbf31338da2caaadc9e4f947b94df8abcf75da350c4ae41319c5",
        "fixed_layer": 4,
        "full_feature_dimension": 688128,
        "hidden_width": 2048,
        "vae_path": "/home/sagemaker-user/MineWorld-Assets-Pinned/checkpoints/vae/vae.ckpt",
        "vae_sha256_inherited_not_recomputed": "370d06be427e034476b6b95ba0080a4b48266e876c4776a757b944b87b87d9ab",
        "visual_token_count": 336,
        "visual_token_grid": [14, 24],
    }
    assert design["ridge"]["alpha_grid"] == [0.1, 1.0, 10.0, 100.0]
    assert design["ridge"]["literal_authority_verified"]
    rows = design["capture_rows"]
    assert rows["expected_source_frame_count"] == 60
    assert rows["eligible_rows_per_trajectory"] == 60
    assert rows["model_frame_idx"] == list(range(60))
    assert rows["common_across_all_layouts"]
    assert "51..59" in rows["historical_l06_51_row_cause"]


def test_campaign_has_exact_balanced_120_spec_factorial() -> None:
    campaign = artifact("capture_campaign.json")
    specs = campaign["trajectory_specs"]
    assert len(specs) == 120
    assert len({row["trajectory_spec_id"] for row in specs}) == 120
    assert len({row["spec_hash"] for row in specs}) == 120
    assert len({row["capture_seed"] for row in specs}) == 120
    assert Counter(row["layout_id"] for row in specs) == {
        layout: 20 for layout in p1.LAYOUTS
    }
    for layout in p1.LAYOUTS:
        for direction in p1.DIRECTIONS:
            assert (
                sum(
                    row["layout_id"] == layout and row["direction"] == direction
                    for row in specs
                )
                == 10
            )
            for profile in p1.PROFILES:
                cell = [
                    row
                    for row in specs
                    if row["layout_id"] == layout
                    and row["direction"] == direction
                    and row["profile_family"] == profile
                ]
                assert len(cell) == 2
                assert {row["repeat_id"] for row in cell} == {1, 2}
                assert cell[0]["capture_seed"] != cell[1]["capture_seed"]
                assert (
                    cell[0]["start_position_authority"]
                    != cell[1]["start_position_authority"]
                    or cell[0]["exact_speed_schedule"]
                    != cell[1]["exact_speed_schedule"]
                )


def test_motion_parameters_are_legal_complete_and_common_f() -> None:
    specs = artifact("capture_campaign.json")["trajectory_specs"]
    allowed_speeds = {-2.0, -1.5, -1.0, 0.0, 1.0, 1.5, 2.0}
    for row in specs:
        lo = row["target_range"]["scalar_axis_min_blocks"]
        hi = row["target_range"]["scalar_axis_max_blocks"]
        assert lo <= row["start_position_authority"]["axis_position_blocks"] <= hi
        assert (
            lo <= row["end_position_authority"]["expected_axis_position_blocks"] <= hi
        )
        assert row["expected_source_frame_count"] == 60
        assert row["expected_eligible_row_count"] == 60
        assert row["expected_model_frame_idx_schedule"] == list(range(60))
        assert row["process_noise"]["draw_count"] == 60
        assert row["process_noise"]["q_blocks_squared_per_second"] == 0.2
        segments = row["exact_speed_schedule"]
        assert segments[0]["start_model_frame_idx"] == 0
        assert segments[-1]["stop_model_frame_idx_exclusive"] == 60
        assert all(
            segment["signed_speed_blocks_per_second"] in allowed_speeds
            for segment in segments
        )
        assert all(
            left["stop_model_frame_idx_exclusive"] == right["start_model_frame_idx"]
            for left, right in zip(segments, segments[1:])
        )


def test_viewpoint_is_singleton_and_part_of_layout_identity() -> None:
    design = artifact("study_design.json")
    assert design["viewpoint_authority"]["status"] == (
        "PART_OF_LAYOUT_IDENTITY_FIXED_WITHIN_LAYOUT"
    )
    assert not design["viewpoint_authority"]["variation_within_layout"]
    assert design["viewpoint_authority"]["strata"] == ["CANONICAL_LAYOUT_POSE"]
    specs = artifact("capture_campaign.json")["trajectory_specs"]
    for layout in p1.LAYOUTS:
        poses = {
            json.dumps(row["camera_viewpoint_authority"], sort_keys=True)
            for row in specs
            if row["layout_id"] == layout
        }
        assert len(poses) == 1


def test_campaign_order_and_stage_boundaries_are_balanced() -> None:
    campaign = artifact("capture_campaign.json")
    by_id = {row["trajectory_spec_id"]: row for row in campaign["trajectory_specs"]}
    order = campaign["campaign_order"]
    assert len(order) == len({row["trajectory_spec_id"] for row in order}) == 120
    assert Counter(row["stage"] for row in order) == {
        "A": 12,
        "B": 36,
        "C": 36,
        "D": 36,
    }
    stage_a = [by_id[row["trajectory_spec_id"]] for row in order[:12]]
    for layout in p1.LAYOUTS:
        rows = [row for row in stage_a if row["layout_id"] == layout]
        assert len(rows) == 2
        assert len({row["direction"] for row in rows}) == 2
        assert len({row["profile_family"] for row in rows}) == 2
    assert {row["profile_family"] for row in stage_a} == set(p1.PROFILES)


def test_state_machine_has_explicit_ack_and_valid_graph() -> None:
    machine = artifact("state_machine_contract.json")
    required = {
        "PRECHECK",
        "RESET_EPISODE",
        "WAIT_RESET_ACK",
        "APPLY_LAYOUT",
        "VERIFY_LAYOUT",
        "SET_CAMERA",
        "VERIFY_CAMERA",
        "SPAWN_OR_POSITION_SHEEP",
        "VERIFY_SHEEP_STATE",
        "ARM_CAPTURE",
        "START_TRAJECTORY",
        "RUN_TRAJECTORY",
        "STOP_CAPTURE",
        "VALIDATE_CAPTURE",
        "ACCEPT_OR_RETRY",
    }
    by_name = {row["state"]: row for row in machine["states"]}
    assert set(by_name) == required
    for row in machine["states"]:
        assert row["ack_mode"]
        assert row["authoritative_acknowledgement_source"]
        assert row["success_predicate_or_implementation_hook"]
        assert row["timeout_policy"]["seconds"] > 0
        assert row["failure_reason_codes"]
        assert row["next_legal_states"]
        assert all(
            target in required or target.startswith("TERMINAL_")
            for target in row["next_legal_states"]
        )
    assert by_name["STOP_CAPTURE"]["ack_mode"] == ("ACK_MODE=BOUNDED_TIMING_FALLBACK")
    assert by_name["STOP_CAPTURE"]["fixed_sleep_necessary"]
    assert len(machine["acknowledgement_gaps"]) == 4


def test_acceptance_and_resume_contract_are_outcome_blind_append_only() -> None:
    acceptance = artifact("acceptance_rules.json")
    assert acceptance["classification_enum"] == [
        "ACCEPTED",
        "REJECTED_WITH_REASON",
    ]
    assert acceptance["maximum_attempts_per_trajectory_spec"] == 3
    assert not acceptance["acceptance_uses_decoding_outcome"]
    rule_fields = " ".join(row["fields"] for row in acceptance["rules"]).lower()
    for forbidden in ("activation", "probe", "prediction", "r2", "token score"):
        assert forbidden not in rule_fields

    ledger = artifact("capture_campaign.json")["resume_ledger_contract"]
    assert "append-only" in ledger["storage_format"]
    assert not ledger["resume_semantics"]["old_rows_mutable"]
    assert "ACCEPTED" in ledger["resume_semantics"]["skip"]
    assert "earliest campaign-order" in ledger["resume_semantics"]["continue"]
    assert "never regenerate" in ledger["resume_semantics"]["identity"]


def test_split_algorithm_synthetic_counts_coverage_and_nesting() -> None:
    specs = artifact("capture_campaign.json")["trajectory_specs"]
    seeds = artifact("seed_manifest.json")
    result = p1.build_synthetic_split(
        specs,
        seeds["split_fixed_test_seed"],
        seeds["split_master_seeds"],
    )
    replay = p1.build_synthetic_split(
        specs,
        seeds["split_fixed_test_seed"],
        seeds["split_master_seeds"],
    )
    assert p1.canonical_sha256(result) == p1.canonical_sha256(replay)
    assert len(result["test"]) == 18
    assert len(result["training"]) == 102
    assert Counter(row["layout_id"] for row in result["test"]) == {
        layout: 3 for layout in p1.LAYOUTS
    }
    assert len(result["schedules"]) == 62
    exposure = list(result["training_exposure"].values())
    assert min(exposure) == 17
    assert max(exposure) == 22
    n5 = [row for row in result["schedules"] if row["size"] == 5]
    omissions = Counter()
    for subset in n5:
        present = {row["layout_id"] for row in subset["members"]}
        assert len(present) == 5
        omissions.update(set(p1.LAYOUTS) - present)
    assert max(omissions.values()) - min(omissions.values()) <= 1
    assert all(
        {row["layout_id"] for row in subset["members"]} == set(p1.LAYOUTS)
        for subset in result["schedules"]
        if subset["size"] >= 15
    )
    n100 = [row for row in result["schedules"] if row["size"] == 100]
    training_ids = {row["trajectory_spec_id"] for row in result["training"]}
    omitted_pairs = {
        frozenset(
            training_ids - {row["trajectory_spec_id"] for row in subset["members"]}
        )
        for subset in n100
    }
    assert len(omitted_pairs) == 6


def test_prospective_null_has_49_valid_within_layout_derangements() -> None:
    specs = artifact("capture_campaign.json")["trajectory_specs"]
    seeds = artifact("seed_manifest.json")
    split = p1.build_synthetic_split(
        specs,
        seeds["split_fixed_test_seed"],
        seeds["split_master_seeds"],
    )
    canonical_n100 = next(
        row["members"]
        for row in split["schedules"]
        if row["size"] == 100 and row["replicate"] == 0
    )
    by_id = {row["trajectory_spec_id"]: row for row in canonical_n100}
    assert min(Counter(row["layout_id"] for row in canonical_n100).values()) >= 16
    assert len(seeds["prospective_null_seeds"]) == 49
    for seed in seeds["prospective_null_seeds"]:
        assignments = p1.within_layout_derangement(canonical_n100, seed)
        assert len(assignments) == 100
        assert all(recipient != donor for recipient, donor in assignments.items())
        assert all(
            by_id[recipient]["layout_id"] == by_id[donor]["layout_id"]
            for recipient, donor in assignments.items()
        )
        synthetic_blocks = {
            identity: [f"{identity}:{index}" for index in range(60)]
            for identity in by_id
        }
        for recipient, donor in assignments.items():
            copied = list(synthetic_blocks[donor])
            assert copied == synthetic_blocks[donor]
            assert [value.rsplit(":", 1)[1] for value in copied] == [
                str(index) for index in range(60)
            ]
    authority = artifact("prospective_null_authority.json")
    assert authority["artifact_id"] == (
        "PROSPECTIVE_WITHIN_LAYOUT_TRAJECTORY_DERANGEMENT_NULL_V0_1"
    )
    assert not authority["target_null_identical_to_prior_audited_null"]
    assert authority["B"] == 49


def test_study_counts_best_k_and_profile_audit_reconcile() -> None:
    design = artifact("study_design.json")
    assert design["cohort"]["fresh_total"] == 120
    assert design["cohort"]["future_fixed_test"] == 18
    assert design["cohort"]["future_train_pool"] == 102
    assert not design["cohort"]["historical_18_included_in_primary"]
    assert design["learning_curve"]["training_sizes"] == [5, 15, 40, 70, 100]
    assert design["learning_curve"]["subset_replicates"] == [20, 16, 12, 8, 6]
    assert design["learning_curve"]["total_subsets"] == 62
    assert design["best_k"]["candidates"] == [1, 4, 8, 16, 32, 64, 128]
    assert design["fresh_outcome_blind"]
    audit = artifact("profile_audit_contract.json")
    assert audit["time_target_correlation"]["global_absolute_correlation_max"] == 0.10
    assert not audit["time_target_correlation"]["aggregate_cancellation_is_sufficient"]
    assert (
        audit["pairwise_profile_similarity"]["high_similarity_threshold_inclusive"]
        == 0.95
    )
    assert (
        audit["pairwise_profile_similarity"]["maximum_fraction_high_similarity"] == 0.20
    )
