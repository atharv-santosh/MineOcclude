"""Focused validation for the Person B 66-cell pre-activation package.

These tests run only against real, hash-bound Person C and Person A evidence.
They never materialize activation bytes, never execute a scientific metric, and
never regenerate the frozen ten-pilot artifacts.
"""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

from mineocclude.analysis.config import (
    hash_core_analysis_config,
    load_core_analysis_config,
)
from mineocclude.analysis.manifests import (
    canonical_json_bytes,
    validate_sealed_artifact,
)
from mineocclude.analysis.preactivation_66_cell_v0_1 import (
    ADMISSION_STRATUM_CORE,
    ADMISSION_STRATUM_SENTINEL,
    ADMISSION_STRATUM_VISIBLE_CONTROL,
    EXPECTED_ACTIVATION_CHUNK_COUNT,
    EXPECTED_ACTIVATION_ROW_COUNT,
    EXPECTED_LAYER_COUNT,
    EXPECTED_LAYOUT_COUNT,
    EXPECTED_MODEL_FRAME_KEY_COUNT,
    EXPECTED_TRAJECTORY_COUNT,
    ORACLE_STAGE_BLOCKED,
    PERSON_A_COMMIT,
    PERSON_A_FRAME_MAP_PACKAGE_PATH,
    PERSON_A_FRAME_MAP_PACKAGE_SHA256,
    PERSON_A_STORAGE_DTYPE_PROPOSAL_PATH,
    PERSON_A_STORAGE_DTYPE_PROPOSAL_SHA256,
    PERSON_C_ACCEPTED_MANIFEST_PATH,
    PERSON_C_ACCEPTED_MANIFEST_SHA256,
    PERSON_C_COMMIT,
    PREACTIVATION_PACKAGE_DIRECTORY,
    ROW_EXCLUSION_NO_OBJECT,
    ROW_EXCLUSION_OUTSIDE_SELECTION,
    ROW_EXCLUSION_PRE_FIRST_SEEN,
    PreactivationError,
    assess_oracle_target_inputs,
    audit_fold_leakage,
    build_66_cell_fold_manifest,
    build_row_universe,
    build_row_universe_receipt,
    build_u4_heldout_partition,
    derive_preactivation_code_sha,
    load_person_a_frame_map_package,
    load_person_c_accepted_manifest,
    read_bound_blob,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PACKAGE = REPOSITORY_ROOT / PREACTIVATION_PACKAGE_DIRECTORY
BUILDER = REPOSITORY_ROOT / "scripts" / "build_person_b_66_cell_preactivation_v0_1.py"


def _load_builder():
    spec = importlib.util.spec_from_file_location(
        "person_b_66_cell_preactivation_builder", BUILDER
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def builder():
    return _load_builder()


@pytest.fixture(scope="module")
def code_sha() -> str:
    return derive_preactivation_code_sha(REPOSITORY_ROOT)


@pytest.fixture(scope="module")
def c_manifest() -> dict:
    return load_person_c_accepted_manifest(repository_root=REPOSITORY_ROOT)


@pytest.fixture(scope="module")
def a_package() -> dict:
    return load_person_a_frame_map_package(repository_root=REPOSITORY_ROOT)


@pytest.fixture(scope="module")
def universe(c_manifest, a_package) -> dict:
    return build_row_universe(c_manifest, a_package)


@pytest.fixture(scope="module")
def fold_manifest(universe, code_sha) -> dict:
    return build_66_cell_fold_manifest(universe, code_sha=code_sha)


def _published(name: str) -> dict:
    return json.loads((PACKAGE / name).read_text(encoding="utf-8"))


# ---------------------------------------------------------------- C intake
def test_person_c_66_cell_intake_is_hash_bound(c_manifest):
    assert c_manifest["accepted_count"] == EXPECTED_TRAJECTORY_COUNT
    assert c_manifest["excluded_count"] == 0
    assert len(c_manifest["records"]) == EXPECTED_TRAJECTORY_COUNT
    assert all(record["accepted"] is True for record in c_manifest["records"])
    assert all(record["status"] == "PASS" for record in c_manifest["records"])
    cells = {record["planned_cell_id"] for record in c_manifest["records"]}
    assert len(cells) == EXPECTED_TRAJECTORY_COUNT
    layouts = {record["layout_id"] for record in c_manifest["records"]}
    assert len(layouts) == EXPECTED_LAYOUT_COUNT


def test_person_c_intake_rejects_a_wrong_manifest_hash():
    with pytest.raises(PreactivationError):
        read_bound_blob(
            PERSON_C_COMMIT,
            PERSON_C_ACCEPTED_MANIFEST_PATH,
            expected_sha256="0" * 64,
            repository_root=REPOSITORY_ROOT,
        )


def test_bound_blob_rejects_path_traversal():
    with pytest.raises(PreactivationError):
        read_bound_blob(
            PERSON_C_COMMIT, "../escape.json", repository_root=REPOSITORY_ROOT
        )


# ---------------------------------------------------------------- A intake
def test_person_a_frame_map_intake_declares_the_bound_universe(a_package):
    index = a_package["index"]
    assert index["c_accepted_manifest_sha256"] == PERSON_C_ACCEPTED_MANIFEST_SHA256
    assert index["c_source_commit"] == PERSON_C_COMMIT
    assert index["model_frame_key_count"] == EXPECTED_MODEL_FRAME_KEY_COUNT
    assert index["duplicate_model_frame_key_count"] == 0
    assert index["missing_trajectory_count"] == 0
    assert index["layer_count"] == EXPECTED_LAYER_COUNT
    assert index["expected_activation_row_count_total"] == EXPECTED_ACTIVATION_ROW_COUNT
    assert index["expected_chunk_count_total"] == EXPECTED_ACTIVATION_CHUNK_COUNT
    assert len(a_package["frame_maps"]) == EXPECTED_TRAJECTORY_COUNT


def test_person_a_package_sha256_matches_the_declared_authority():
    payload = read_bound_blob(
        PERSON_A_COMMIT,
        PERSON_A_FRAME_MAP_PACKAGE_PATH,
        repository_root=REPOSITORY_ROOT,
    )
    assert hashlib.sha256(payload).hexdigest() == PERSON_A_FRAME_MAP_PACKAGE_SHA256


# -------------------------------------------------------- row universe
def test_row_universe_has_exactly_the_declared_frame_keys(universe):
    keys = {(row["trajectory_id"], row["model_frame_idx"]) for row in universe["rows"]}
    assert len(universe["rows"]) == EXPECTED_MODEL_FRAME_KEY_COUNT
    assert len(keys) == EXPECTED_MODEL_FRAME_KEY_COUNT
    assert len(universe["layout_by_trajectory"]) == EXPECTED_TRAJECTORY_COUNT
    assert len(universe["layouts"]) == EXPECTED_LAYOUT_COUNT


def test_row_universe_is_not_the_historical_ten_pilot_universe(universe):
    trajectories = set(universe["layout_by_trajectory"])
    assert not any(
        trajectory_id.endswith(("ep9403", "ep9441", "ep9405", "ep9442", "ep9407"))
        for trajectory_id in trajectories
    )
    assert len(trajectories) == EXPECTED_TRAJECTORY_COUNT


def test_row_universe_join_is_one_to_many_and_condition_consistent(universe, c_manifest):
    by_id = {record["trajectory_id"]: record for record in c_manifest["records"]}
    for row in universe["rows"]:
        record = by_id[row["trajectory_id"]]
        assert row["layout_id"] == record["layout_id"]
        assert row["planned_cell_id"] == record["planned_cell_id"]
        assert row["control_type"] == record["control_type"]
        assert row["episode_id"] == record["episode_id"]
        assert isinstance(row["geometric_visible"], bool)


def test_row_universe_rejects_a_duplicated_frame_key(c_manifest, a_package):
    corrupted = copy.deepcopy(a_package)
    trajectory_id = min(corrupted["frame_maps"])
    rows = corrupted["frame_maps"][trajectory_id]
    rows.append(copy.deepcopy(rows[0]))
    with pytest.raises(PreactivationError):
        build_row_universe(c_manifest, corrupted)


def test_row_universe_rejects_a_layout_identity_disagreement(c_manifest, a_package):
    corrupted = copy.deepcopy(a_package)
    trajectory_id = min(corrupted["frame_maps"])
    corrupted["frame_maps"][trajectory_id][0]["layout_id"] = "layout_99"
    with pytest.raises(PreactivationError):
        build_row_universe(c_manifest, corrupted)


def test_row_universe_rejects_a_missing_trajectory(c_manifest, a_package):
    corrupted = copy.deepcopy(a_package)
    del corrupted["frame_maps"][min(corrupted["frame_maps"])]
    with pytest.raises(PreactivationError):
        build_row_universe(c_manifest, corrupted)


# ------------------------------------------------ admission / exclusion
def test_admission_and_exclusion_partition_the_universe(universe):
    admitted = universe["admitted_rows"]
    excluded = universe["excluded_rows"]
    assert len(admitted) + len(excluded) == EXPECTED_MODEL_FRAME_KEY_COUNT
    assert len(admitted) == 984
    assert len(excluded) == 1_484
    assert {row["status"] for row in admitted} == {"accepted"}
    assert {row["status"] for row in excluded} == {"excluded"}


def test_exclusion_reasons_are_drawn_only_from_the_frozen_set(universe):
    reasons = {row["exclusion_reason"] for row in universe["excluded_rows"]}
    assert reasons <= {
        ROW_EXCLUSION_NO_OBJECT,
        ROW_EXCLUSION_PRE_FIRST_SEEN,
        ROW_EXCLUSION_OUTSIDE_SELECTION,
    }
    # In this universe the only never-visible trajectories are the six
    # no_object_control cells, which the earlier rule already excludes, so the
    # post_first_seen filter is declared but binds zero additional rows.
    assert reasons == {ROW_EXCLUSION_NO_OBJECT, ROW_EXCLUSION_OUTSIDE_SELECTION}
    for row in universe["rows"]:
        if row["control_type"] != "no_object_control":
            assert row["first_visible_model_frame_idx"] == 0


def test_no_object_control_rows_are_never_admitted(universe):
    for row in universe["rows"]:
        if row["control_type"] == "no_object_control":
            assert row["status"] == "excluded"
            assert row["analysis_scopes"] == []


def test_admitted_hidden_rows_are_occluded_and_stratified(universe):
    for row in universe["admitted_rows"]:
        if row["admission_stratum"] in (
            ADMISSION_STRATUM_CORE,
            ADMISSION_STRATUM_SENTINEL,
        ):
            assert row["geometric_visible"] is False
            assert row["analysis_scopes"] == ["hidden_mean", "hidden_spread"]
        else:
            assert row["admission_stratum"] == ADMISSION_STRATUM_VISIBLE_CONTROL
            assert row["control_type"] == "no_wall_visible_control"
            assert row["analysis_scopes"] == ["visible_no_wall_control"]


def test_row_exclusion_is_not_a_trajectory_rejection(universe, code_sha):
    receipt = build_row_universe_receipt(universe, code_sha=code_sha)
    assert receipt["accepted_trajectory_count"] == EXPECTED_TRAJECTORY_COUNT
    assert receipt["excluded_trajectory_count"] == 0
    detail = receipt["trajectory_acceptance_vs_row_admission"]
    assert detail["rejected_trajectories"] == 0
    assert detail["row_level_exclusions_are_not_trajectory_rejections"] is True
    excluded_trajectories = {row["trajectory_id"] for row in universe["excluded_rows"]}
    assert excluded_trajectories.issubset(set(universe["layout_by_trajectory"]))


# ------------------------------------------------------------ folds
def test_fold_manifest_uses_the_frozen_grouped_layout_policy(fold_manifest):
    config = load_core_analysis_config()
    assert fold_manifest["strategy"] == "layout_grouped"
    assert fold_manifest["n_splits"] == config["cross_validation"]["fold_count"]
    assert fold_manifest["seed"] == config["cross_validation"]["split_seed"]
    assert fold_manifest["config_hash"] == hash_core_analysis_config()
    assert fold_manifest["random_split_used"] is False
    assert fold_manifest["grouping_policy_changed_after_results"] is False
    assert fold_manifest["u4_output_inspected"] is False
    validate_sealed_artifact(fold_manifest, expected_type="person_b_66_cell_fold_manifest")


def test_fold_manifest_covers_every_row_exactly_once(fold_manifest, universe):
    keys = [
        (row["trajectory_id"], row["model_frame_idx"])
        for row in fold_manifest["memberships"]
    ]
    assert len(keys) == EXPECTED_MODEL_FRAME_KEY_COUNT
    assert len(set(keys)) == EXPECTED_MODEL_FRAME_KEY_COUNT
    assert set(keys) == {
        (row["trajectory_id"], row["model_frame_idx"]) for row in universe["rows"]
    }


def test_fold_generation_is_deterministic_and_row_order_independent(universe, code_sha):
    first = build_66_cell_fold_manifest(universe, code_sha=code_sha)
    shuffled = dict(universe)
    shuffled["rows"] = list(reversed(universe["rows"]))
    second = build_66_cell_fold_manifest(shuffled, code_sha=code_sha)
    assert first["artifact_hash"] == second["artifact_hash"]


def test_fold_counts_reconcile(fold_manifest):
    by_fold = {item["fold_idx"]: item for item in fold_manifest["row_counts_by_fold"]}
    assert sum(item["model_frame_row_count"] for item in by_fold.values()) == (
        EXPECTED_MODEL_FRAME_KEY_COUNT
    )
    assert sum(item["admitted_row_count"] for item in by_fold.values()) == (
        fold_manifest["admitted_analysis_row_count"]
    )
    assert sum(item["excluded_row_count"] for item in by_fold.values()) == (
        fold_manifest["excluded_analysis_row_count"]
    )
    trajectories = sum(
        item["trajectory_count"] for item in fold_manifest["trajectory_counts_by_fold"]
    )
    assert trajectories == EXPECTED_TRAJECTORY_COUNT
    layouts = sum(
        item["layout_count"] for item in fold_manifest["layout_counts_by_fold"]
    )
    assert layouts == EXPECTED_LAYOUT_COUNT


def test_leakage_audit_passes_on_the_real_fold_manifest(fold_manifest, universe, code_sha):
    audit = audit_fold_leakage(fold_manifest, universe, code_sha=code_sha)
    assert audit["leakage_audit_pass"] is True
    assert audit["leaking_layout_ids"] == []
    assert audit["leaking_trajectory_ids"] == []
    assert audit["unresolved_frame_keys"] == []
    assert audit["extraneous_frame_keys"] == []
    assert all(audit["checks"].values())


def test_leakage_audit_rejects_a_layout_split_across_folds(
    fold_manifest, universe, code_sha
):
    leaking = copy.deepcopy(fold_manifest)
    target = leaking["memberships"][0]
    target["fold_idx"] = (target["fold_idx"] + 1) % leaking["n_splits"]
    audit = audit_fold_leakage(leaking, universe, code_sha=code_sha)
    assert audit["leakage_audit_pass"] is False
    assert target["layout_id"] in audit["leaking_layout_ids"]
    assert target["trajectory_id"] in audit["leaking_trajectory_ids"]


def test_leakage_audit_rejects_an_unresolved_row(fold_manifest, universe, code_sha):
    truncated = copy.deepcopy(fold_manifest)
    truncated["memberships"] = truncated["memberships"][:-1]
    audit = audit_fold_leakage(truncated, universe, code_sha=code_sha)
    assert audit["leakage_audit_pass"] is False
    assert audit["unresolved_frame_keys"]


# ----------------------------------------------------------- oracle
def test_oracle_stage_fails_closed_with_exact_missing_inputs(universe, code_sha):
    oracle = assess_oracle_target_inputs(
        universe, code_sha=code_sha, repository_root=REPOSITORY_ROOT
    )
    assert oracle["stage_status"] == ORACLE_STAGE_BLOCKED
    assert oracle["oracle_target_manifest_produced"] is False
    assert oracle["target_truth_reconstructed_from_pixels"] is False
    assert oracle["hidden_truth_silently_substituted"] is False
    assert oracle["partial_oracle_document_emitted"] is False
    assert oracle["independent_tasks_continued"] is True
    blocker_ids = {blocker["blocker_id"] for blocker in oracle["blockers"]}
    assert blocker_ids == {
        "person_c_capture_package_v0_1_absent_for_66_cells",
        "wall_parallel_coordinate_frame_unsigned_for_c6a_layouts",
        "empirical_magenta_visibility_absent_for_66_cells",
    }
    assert len(oracle["missing_capture_packages"]) == EXPECTED_TRAJECTORY_COUNT
    assert all(
        item["present_at_bound_person_c_commit"] is False
        for item in oracle["missing_capture_packages"]
    )


def test_oracle_preflight_reports_state_payload_byte_identity(universe, code_sha):
    oracle = assess_oracle_target_inputs(
        universe, code_sha=code_sha, repository_root=REPOSITORY_ROOT
    )
    inventory = oracle["state_payload_inventory"]
    assert len(inventory) == 2 * EXPECTED_TRAJECTORY_COUNT
    for item in inventory:
        assert item["artifact_role"] in {"server_state.jsonl", "layout_meta.json"}
        assert len(item["declared_sha256"]) == 64
        if item["present_on_this_host"]:
            assert item["observed_sha256"] is not None


# -------------------------------------------------------- U4 partition
def test_u4_heldout_partition_is_layout_only_and_frozen(universe, code_sha):
    partition = build_u4_heldout_partition(universe, code_sha=code_sha)
    config = load_core_analysis_config()["cross_validation"]["u4_development_partition"]
    assert len(partition["fit_layout_ids"]) == config["fit_layout_count"]
    assert len(partition["validation_layout_ids"]) == config["validation_layout_count"]
    assert len(partition["heldout_layout_ids"]) == config["test_layout_count"]
    assert partition["selection_source"] == "layout_manifest_only"
    assert partition["layout_partition_frozen"] is True
    assert partition["event_ids_frozen"] is False
    assert partition["frozen_heldout_event_ids"] is None
    proofs = partition["non_use_proofs"]
    assert proofs["not_used_in_probe_fit"] is True
    assert proofs["not_used_in_layer_selection"] is True
    assert proofs["not_used_in_direction_construction"] is True
    assert proofs["not_used_in_dose_selection"] is True
    assert proofs["not_used_to_tune_person_e_detector"] is True
    assert proofs["activation_direction_constructed"] is False
    assert proofs["u4_outcomes_inspected"] is False


def test_u4_partition_is_deterministic(universe, code_sha):
    first = build_u4_heldout_partition(universe, code_sha=code_sha)
    second = build_u4_heldout_partition(universe, code_sha=code_sha)
    assert first["artifact_hash"] == second["artifact_hash"]


def test_heldout_layouts_are_disjoint_from_fit_and_validation(universe, code_sha):
    partition = build_u4_heldout_partition(universe, code_sha=code_sha)
    fit = set(partition["fit_layout_ids"])
    validation = set(partition["validation_layout_ids"])
    heldout = set(partition["heldout_layout_ids"])
    assert not fit & validation
    assert not fit & heldout
    assert not validation & heldout
    assert fit | validation | heldout == set(universe["layouts"])


def test_heldout_candidate_events_are_geometric_only(universe, code_sha):
    partition = build_u4_heldout_partition(universe, code_sha=code_sha)
    for candidate in partition["geometric_only_candidate_events"]:
        assert candidate["authority"] == "geometric_visible_only"
        assert candidate["layout_id"] in partition["heldout_layout_ids"]
        assert candidate["post_model_frame_idx"] == candidate["pre_model_frame_idx"] + 1


# ------------------------------------------------------ dtype review
def test_person_a_dtype_proposal_hash_is_independently_verified():
    payload = read_bound_blob(
        PERSON_A_COMMIT,
        PERSON_A_STORAGE_DTYPE_PROPOSAL_PATH,
        expected_sha256=PERSON_A_STORAGE_DTYPE_PROPOSAL_SHA256,
        repository_root=REPOSITORY_ROOT,
    )
    proposal = json.loads(payload.decode("utf-8"))
    assert proposal["decision"] == "PENDING_COORDINATED_A_B_REVIEW"
    assert proposal["person_a_unilateral_change_made"] is False
    assert proposal["mvp_yaml_modified_by_this_package"] is False


def test_storage_dtype_review_schema_and_decision(builder):
    review = _published(builder.STORAGE_DTYPE_REVIEW)
    validate_sealed_artifact(review, expected_type="person_b_storage_dtype_review")
    assert review["review_complete"] is True
    assert review["resolution_option"] == "A"
    assert review["chosen_stored_activation_dtype"] == "float32"
    assert review["chosen_analysis_arithmetic_dtype"] == "float64"
    approvals = review["person_b_approvals"]
    assert approvals["approves_successor_extraction_contract"] is True
    assert approvals["person_a_may_create_new_successor_config_and_run_identity"] is True
    assert approvals["new_run_identity_required"] is True
    assert approvals["additional_scientific_review_required"] is False
    assert approvals["in_place_edit_of_accepted_run_authorized"] is False
    assert approvals["historical_ten_pilot_artifacts_may_be_rewritten"] is False
    assert approvals["person_b_edited_person_a_mvp_yaml"] is False
    assessment = review["result_changing_assessment"]
    assert assessment["result_changing_by_person_a_step_7_1_register"] is True
    assert assessment["numerically_result_changing_versus_executed_artifacts"] is False
    for name, item in review["evidence"].items():
        assert len(item["sha256"]) == 64, name
        assert item["byte_size"] > 0, name


def test_person_b_did_not_edit_person_a_mvp_yaml():
    text = (REPOSITORY_ROOT / "configs" / "experiments" / "mvp.yaml").read_text(
        encoding="utf-8"
    )
    assert "stored_dtype" not in text


def test_pooling_implementation_still_requires_float32():
    source = (
        REPOSITORY_ROOT / "src" / "mineocclude" / "activations" / "pool.py"
    ).read_text(encoding="utf-8")
    assert "selected.to(dtype=torch.float32)" in source
    assert "pooled.dtype != torch.float32" in source


def test_accepted_activation_contract_pins_float32_and_float64():
    contract = json.loads(
        (
            REPOSITORY_ROOT
            / "docs"
            / "status"
            / "person_a_phase4_step4_1_production_handoff_preflight_v0_1"
            / "activation_contract.json"
        ).read_text(encoding="utf-8")
    )
    pooled = contract["pooled_representation"]
    assert pooled["stored_dtype"] == "float32"
    assert pooled["analysis_dtype"] == "float64"
    assert pooled["vector_shape"] == [2048]


# ------------------------------------------------------------ handoffs
def test_b_to_a_handoff_identifies_every_required_authority(builder):
    handoff = _published(builder.B_TO_A_HANDOFF)
    validate_sealed_artifact(
        handoff, expected_type="person_b_to_person_a_66_cell_handoff"
    )
    assert handoff["person_c_accepted_manifest_sha256"] == PERSON_C_ACCEPTED_MANIFEST_SHA256
    assert handoff["person_a_frame_map_package_sha256"] == PERSON_A_FRAME_MAP_PACKAGE_SHA256
    assert len(handoff["person_b_fold_manifest"]["artifact_hash"]) == 64
    assert handoff["person_b_oracle_target_manifest"]["artifact_hash"] is None
    assert handoff["person_b_oracle_target_manifest"]["status"] == ORACLE_STAGE_BLOCKED
    assert handoff["analysis_row_universe"]["admitted_analysis_row_count"] == 984
    assert {rule["exclusion_reason"] for rule in handoff["exclusion_rules"]} == {
        ROW_EXCLUSION_NO_OBJECT,
        ROW_EXCLUSION_PRE_FIRST_SEEN,
        ROW_EXCLUSION_OUTSIDE_SELECTION,
    }
    assert handoff["dtype_decision"]["approved_stored_activation_dtype"] == "float32"
    assert handoff["heldout_partition_status"]["event_ids_frozen"] is False
    required = handoff["required_activation_index_fields"]
    assert required["row_key"] == [
        "trajectory_id",
        "model_frame_idx",
        "layer_idx",
        "hook_site",
    ]
    assert required["required_values"]["stored_dtype"] == "float32"
    assert required["activation_paths_or_hashes_supplied_by_person_b"] is False
    assert handoff["downstream_acceptance_claimed"] is False
    assert handoff["consumer_receipt_present"] is False


def test_b_to_d_handoff_identifies_every_required_authority(builder):
    handoff = _published(builder.B_TO_D_HANDOFF)
    validate_sealed_artifact(
        handoff, expected_type="person_b_to_person_d_66_cell_handoff"
    )
    assert handoff["person_c_accepted_manifest_sha256"] == PERSON_C_ACCEPTED_MANIFEST_SHA256
    assert len(handoff["person_b_fold_manifest"]["artifact_hash"]) == 64
    assert handoff["person_b_oracle_target_manifest"]["status"] == ORACLE_STAGE_BLOCKED
    assert (
        handoff["person_b_oracle_target_manifest"][
            "baselines_requiring_oracle_targets_are_blocked"
        ]
        is True
    )
    universe_block = handoff["eligible_baseline_row_universe"]
    assert universe_block["admitted_analysis_row_count"] == 984
    assert len(universe_block["row_universe_canonical_hash"]) == 64
    grouping = handoff["sample_and_grouping_identity"]
    assert grouping["fold_strategy"] == "layout_grouped"
    assert grouping["grouping_hierarchy"] == ["layout_id", "trajectory_id"]
    metric = handoff["metric_api_identity"]
    assert metric["config_hash"] == hash_core_analysis_config()
    assert metric["config_path"] == "configs/analysis/core.yaml"
    assert handoff["dtype_decision_affecting_person_d_inputs"]["stored_activation_dtype"] == (
        "float32"
    )
    assert handoff["downstream_acceptance_claimed"] is False


# -------------------------------------------------- post-activation
def test_post_activation_preflight_declares_no_remaining_schema_decision(builder):
    preflight = _published(builder.POST_ACTIVATION_PREFLIGHT)
    validate_sealed_artifact(
        preflight, expected_type="person_b_66_cell_post_activation_preflight"
    )
    assert preflight["executed"] is False
    assert preflight["activation_paths_fabricated"] is False
    assert preflight["activation_hashes_fabricated"] is False
    assert preflight["metrics_executed_against_synthetic_activations"] is False
    assert preflight["schema_decisions_remaining"] == []
    assert preflight["no_further_schema_decision_required_after_activation_index"] is True
    validation = preflight["expected_activation_key_validation"]
    assert validation["expected_activation_row_count"] == EXPECTED_ACTIVATION_ROW_COUNT
    assert validation["expected_activation_chunk_count"] == EXPECTED_ACTIVATION_CHUNK_COUNT
    assert validation["expected_model_frame_key_count"] == EXPECTED_MODEL_FRAME_KEY_COUNT
    assert validation["expected_layer_count"] == EXPECTED_LAYER_COUNT
    assert validation["duplicate_activation_key_tolerance"] == 0
    assert validation["missing_activation_key_tolerance"] == 0
    assert (
        EXPECTED_MODEL_FRAME_KEY_COUNT * EXPECTED_LAYER_COUNT
        == EXPECTED_ACTIVATION_ROW_COUNT
    )


# --------------------------------------------------- published package
def test_published_package_is_byte_reproducible(builder, code_sha, universe):
    receipt = build_row_universe_receipt(universe, code_sha=code_sha)
    published = _published(builder.ROW_UNIVERSE_RECEIPT)
    assert canonical_json_bytes(receipt) == canonical_json_bytes(published)


def test_published_inventory_matches_published_bytes(builder):
    inventory = _published(builder.SHA256_INVENTORY)
    assert inventory["inventory_excludes_self"] is True
    assert inventory["file_count"] == len(builder.ORDERED_FILES)
    for item in inventory["files"]:
        path = REPOSITORY_ROOT / item["path"]
        payload = path.read_bytes()
        assert hashlib.sha256(payload).hexdigest() == item["sha256"], item["path"]
        assert len(payload) == item["byte_size"], item["path"]


def test_successor_decision_preserves_the_predecessor_evidence(builder):
    decision = _published(builder.SUCCESSOR_DECISION)
    validate_sealed_artifact(
        decision, expected_type="person_b_66_cell_successor_authority_decision"
    )
    predecessor = decision["superseded_predecessor"]
    assert predecessor["trajectory_count"] == 10
    assert predecessor["admitted_row_count"] == 1_695
    assert predecessor["excluded_row_count"] == 179
    assert predecessor["activation_row_count"] == 37_480
    assert predecessor["activation_chunk_count"] == 200
    assert predecessor["evidence_overwritten"] is False
    assert predecessor["evidence_relabelled"] is False
    assert predecessor["evidence_regenerated"] is False
    assert predecessor["row_ids_reused_as_66_cell_universe"] is False


def test_frozen_step_4_1_decision_remains_fail(builder):
    decision = _published(builder.SUCCESSOR_DECISION)
    frozen = decision["frozen_decisions_not_reopened"]
    assert frozen["step_4_1_decision"] == "FAIL"
    assert frozen["step_4_1_rerun_authorized"] is False


def test_published_package_passes_the_fail_closed_validator():
    spec = importlib.util.spec_from_file_location(
        "person_b_66_cell_preactivation_validator",
        REPOSITORY_ROOT / "scripts" / "validate_person_b_66_cell_preactivation_v0_1.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    result = module.validate()
    assert result["validated"] is True
    assert result["fold_leakage_audit_pass"] is True
    assert result["oracle_stage_status"] == ORACLE_STAGE_BLOCKED
    assert result["model_frame_key_count"] == EXPECTED_MODEL_FRAME_KEY_COUNT


def test_b_to_c_u4_receipt_names_the_remaining_inputs(builder):
    receipt = _published(builder.B_TO_C_U4_RECEIPT)
    validate_sealed_artifact(
        receipt, expected_type="person_b_to_person_c_u4_selection_receipt"
    )
    assert receipt["selection_ready_for_c8_2"] is False
    assert receipt["event_ids_frozen"] is False
    assert receipt["frozen_heldout_event_ids"] is None
    input_ids = {item["input_id"] for item in receipt["remaining_inputs_required"]}
    assert input_ids == {
        "person_e_empirical_magenta_visibility_for_c6a_66_cells",
        "person_c_strict_join_visible_flag_for_c6a_66_cells",
        "u4_heldout_event_count_contract_reconciliation",
    }
    assert receipt["u4_outcomes_inspected"] is False
    assert receipt["activation_direction_constructed"] is False
