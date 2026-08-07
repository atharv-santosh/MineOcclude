"""Focused validation for the Person B 66-cell production oracle targets.

Every assertion runs against real, hash-bound Person C, Person E, and Person A
evidence.  Negative controls are included so that a passing run means the
policy actually discriminates: an ambiguous row, a channel disagreement, a
quarantined row, and a no-object row must each be rejected for its own named
reason, and the oracle must refuse a tampered authority.
"""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import math
from pathlib import Path

import pytest

from mineocclude.analysis.config import (
    hash_core_analysis_config,
    load_core_analysis_config,
)
from mineocclude.analysis.manifests import validate_sealed_artifact
from mineocclude.analysis.oracle_target_66_cell_v0_1 import (
    ACCEPTED_GEOMETRY_SHA256,
    ALWAYS_REQUIRED_TARGET_FIELDS,
    ANALYSIS_ARITHMETIC_DTYPE,
    C_ACCEPTED_MANIFEST_SHA256,
    C_EVENT_TABLE_SHA256,
    C_ORACLE_HANDOFF_PATH,
    C_ORACLE_HANDOFF_SHA256,
    C_VISIBILITY_JOIN_SHA256,
    CONTROL_TYPE_NO_OBJECT,
    EXPECTED_MODEL_FRAME_KEY_COUNT,
    EXPECTED_NO_OBJECT_COUNT,
    EXPECTED_TARGET_BEARING_COUNT,
    EXPECTED_TRAJECTORY_COUNT,
    FROZEN_FOLD_ASSIGNMENT,
    HIDDEN_ONLY_TARGET_FIELDS,
    ORACLE_PACKAGE_DIRECTORY,
    PERSON_A_COMMIT,
    PERSON_B_FOLD_MANIFEST_SHA256,
    PERSON_C_COMMIT,
    ROW_EXCLUSION_AMBIGUOUS_GEOMETRY,
    ROW_EXCLUSION_CHANNEL_DISAGREEMENT,
    ROW_EXCLUSION_NO_OBJECT,
    ROW_EXCLUSION_OUTSIDE_SELECTION,
    STORED_ACTIVATION_DTYPE,
    OracleTargetError,
    build_production_oracle_targets,
    build_successor_row_universe,
    derive_oracle_code_sha,
    load_person_c_oracle_inputs,
    read_bound_blob,
    resolve_person_a_identity,
    summarize_row_universe,
    validate_fold_compatibility,
)
from mineocclude.oracle.closed_form import closed_form_posterior

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PACKAGE = REPOSITORY_ROOT / ORACLE_PACKAGE_DIRECTORY
BUILDER = (
    REPOSITORY_ROOT / "scripts" / "build_person_b_66_cell_oracle_target_v0_1.py"
)
VALIDATOR = (
    REPOSITORY_ROOT / "scripts" / "validate_person_b_66_cell_oracle_target_v0_1.py"
)


def _module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def code_sha() -> str:
    return derive_oracle_code_sha(REPOSITORY_ROOT)


@pytest.fixture(scope="module")
def c_inputs() -> dict:
    return load_person_c_oracle_inputs(repository_root=REPOSITORY_ROOT)


@pytest.fixture(scope="module")
def person_a() -> dict:
    return resolve_person_a_identity(repository_root=REPOSITORY_ROOT)


@pytest.fixture(scope="module")
def oracle(person_a, code_sha) -> dict:
    return build_production_oracle_targets(
        person_a, code_sha=code_sha, repository_root=REPOSITORY_ROOT
    )


@pytest.fixture(scope="module")
def row_universe(c_inputs, oracle) -> dict:
    return build_successor_row_universe(
        c_inputs, oracle, repository_root=REPOSITORY_ROOT
    )


@pytest.fixture(scope="module")
def summary(row_universe) -> dict:
    return summarize_row_universe(row_universe)


def _published(name: str) -> dict:
    return json.loads((PACKAGE / name).read_text(encoding="utf-8"))


def _published_jsonl(name: str) -> list[dict]:
    return [
        json.loads(line)
        for line in (PACKAGE / name).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


# ------------------------------------------------ C oracle-handoff intake
def test_person_c_oracle_handoff_is_hash_bound(c_inputs):
    handoff = c_inputs["handoff"]
    assert handoff["C_TO_B_ORACLE_INPUT_READY"] is True
    assert handoff["person_c_generated_person_b_target_values"] is False
    assert handoff["person_c_modified_person_b_oracle_logic"] is False
    assert handoff["person_c_accepted_manifest"]["sha256"] == C_ACCEPTED_MANIFEST_SHA256
    assert handoff["accepted_geometry"]["sha256"] == ACCEPTED_GEOMETRY_SHA256


def test_intake_rejects_a_wrong_handoff_hash():
    with pytest.raises(OracleTargetError):
        read_bound_blob(
            C_ORACLE_HANDOFF_PATH,
            commit=PERSON_C_COMMIT,
            expected_sha256="0" * 64,
            repository_root=REPOSITORY_ROOT,
        )


def test_strict_visibility_accounting_matches_person_c(c_inputs):
    rows = c_inputs["visibility_rows"]
    assert len(rows) == EXPECTED_MODEL_FRAME_KEY_COUNT
    applicable = [row for row in rows if row["visibility_applicable"]]
    assert len(applicable) == EXPECTED_TARGET_BEARING_COUNT
    assert len(rows) - len(applicable) == EXPECTED_NO_OBJECT_COUNT
    assert c_inputs["disagreement_census"] == {
        "agreement": 1_696,
        "detector_not_applicable": 360,
        "geometry_ambiguous": 42,
        "geometry_hidden_detector_visible": 313,
        "geometry_visible_detector_hidden": 57,
    }
    assert sum(1 for row in applicable if row["visible_flag"] is True) == 1_413
    assert sum(1 for row in applicable if row["visible_flag"] is not True) == 695


def test_event_table_declares_no_valid_terminal_reveal(c_inputs):
    event_table = c_inputs["handoff"]["event_table"]
    assert event_table["valid_terminal_reveal_count"] == 0
    assert event_table["stable_occlusion_event_count"] == 55
    assert event_table["stable_reveal_event_count"] == 1
    assert all(row["valid_terminal_reveal"] is False for row in c_inputs["event_rows"])


# ---------------------------------------------- A model/preprocess authority
def test_model_hash_is_bound_to_the_frozen_checkpoint_equation(person_a):
    assert person_a["model_hash"] == person_a["checkpoint_sha256"]
    assert person_a["model_hash_definition"] == "model_hash == checkpoint_sha256"
    assert len(person_a["model_hash_definition_evidence"]) == 3
    for item in person_a["model_hash_definition_evidence"]:
        source = (REPOSITORY_ROOT / item["path"]).read_text(encoding="utf-8")
        assert "checkpoint_hash" in source, item["path"]


def test_preprocess_hash_is_not_the_implementation_file_digest(person_a):
    assert person_a["preprocess_hash"] != person_a["preprocessing_implementation_sha256"]
    assert person_a["preprocess_hash"] != person_a["preprocessing_config_hash"]
    assert len(person_a["preprocess_hash"]) == 64
    assert person_a["preprocess_hash_source"]["commit"] == PERSON_A_COMMIT


def test_person_a_authority_is_fully_resolved(person_a):
    assert person_a["authority_valid"] is True
    for field in (
        "model_hash",
        "preprocess_hash",
        "frame_map_schema_sha256",
        "action_converter_sha256",
        "checkpoint_sha256",
    ):
        assert len(person_a[field]) == 64, field
    assert person_a["model_identity"] == "mineworld-700m"
    assert person_a["activation_index_key"] == [
        "trajectory_id",
        "model_frame_idx",
        "layer_idx",
        "hook_site",
    ]


# ------------------------------------------------- oracle formulas and units
def test_oracle_covers_every_target_bearing_row(oracle):
    assert len(oracle["target_rows"]) == EXPECTED_TARGET_BEARING_COUNT
    assert len(oracle["per_trajectory"]) == 60
    assert len(oracle["oracle_ineligible_trajectories"]) == 6
    assert {
        item["adapter_rejection_code"]
        for item in oracle["oracle_ineligible_trajectories"]
    } == {"no_object_not_oracle_eligible"}
    assert {
        item["control_type"] for item in oracle["oracle_ineligible_trajectories"]
    } == {CONTROL_TYPE_NO_OBJECT}


def test_oracle_units_and_identities_are_frozen(oracle):
    for row in oracle["target_rows"][:200]:
        assert row["target_source"] == "authoritative_visible_state_known_v_q"
        assert row["oracle_method"] == "primary_scalar_kalman_crosschecked_closed_form"
        assert row["regime"] == "regime_a"
        assert row["target_id"] == (
            f"{row['trajectory_id']}:{row['model_frame_idx']}:regime_a_primary_v1"
        )
        assert math.isfinite(row["mu_oracle_blocks"])
        assert row["var_oracle_blocks2"] >= 0.0
        assert math.isclose(
            row["sigma_oracle_blocks"], math.sqrt(row["var_oracle_blocks2"]), abs_tol=1e-9
        )


def test_oracle_variance_matches_the_closed_form_on_real_rows(oracle):
    checked = 0
    for row in oracle["target_rows"]:
        if row["visibility"] != "occluded":
            continue
        expected = closed_form_posterior(
            row["last_visible_position_blocks"], row["v"], row["q"], row["tau"]
        )
        assert math.isclose(
            row["mu_oracle_blocks"], expected.mean_blocks, rel_tol=0.0, abs_tol=1e-6
        )
        assert math.isclose(
            row["var_oracle_blocks2"],
            expected.variance_blocks2,
            rel_tol=0.0,
            abs_tol=1e-6,
        )
        checked += 1
        if checked >= 300:
            break
    assert checked >= 300


def test_log_sigma_follows_the_frozen_null_policy(oracle):
    config = load_core_analysis_config()["targets"]["log_sigma_oracle"]
    assert config["null_policy"] == "null_outside_eligibility"
    for row in oracle["target_rows"]:
        if row["visibility"] == "visible":
            assert row["tau"] == 0.0
            assert row["log_sigma_oracle"] is None
        else:
            assert row["log_sigma_oracle"] is not None
            assert math.isclose(
                row["log_sigma_oracle"],
                math.log(row["sigma_oracle_blocks"]),
                rel_tol=0.0,
                abs_tol=1e-9,
            )


def test_oracle_never_uses_detector_position_as_truth(oracle, c_inputs):
    by_key = {
        (row["trajectory_id"], row["model_frame_idx"]): row
        for row in c_inputs["visibility_rows"]
    }
    for row in oracle["target_rows"][:300]:
        joined = by_key[(row["trajectory_id"], row["model_frame_idx"])]
        assert math.isclose(
            row["x_true_blocks"],
            joined["wall_parallel_position_blocks"],
            rel_tol=0.0,
            abs_tol=1e-12,
        )


def test_oracle_generation_is_deterministic(person_a, code_sha):
    first = build_production_oracle_targets(
        person_a, code_sha=code_sha, repository_root=REPOSITORY_ROOT
    )
    second = build_production_oracle_targets(
        person_a, code_sha=code_sha, repository_root=REPOSITORY_ROOT
    )
    assert first["target_rows"] == second["target_rows"]
    assert [item["oracle_document_hash"] for item in first["per_trajectory"]] == [
        item["oracle_document_hash"] for item in second["per_trajectory"]
    ]


def test_oracle_refuses_a_tampered_person_a_identity(person_a, code_sha):
    """A bad model_hash must stop the build, not be reclassified as an
    ineligible trajectory."""

    tampered = dict(person_a)
    tampered["model_hash"] = "z" * 64
    with pytest.raises(OracleTargetError, match="missing_a_provenance"):
        build_production_oracle_targets(
            tampered, code_sha=code_sha, repository_root=REPOSITORY_ROOT
        )


def test_only_the_no_object_verdict_is_treated_as_ineligibility(person_a, code_sha):
    """Any adapter rejection other than no-object must propagate."""

    tampered = dict(person_a)
    tampered["preprocess_hash"] = "not-a-sha256"
    with pytest.raises(OracleTargetError, match="refusing to treat this as an"):
        build_production_oracle_targets(
            tampered, code_sha=code_sha, repository_root=REPOSITORY_ROOT
        )


# ------------------------------------------- ambiguity and disagreement policy
def test_all_42_ambiguous_rows_are_excluded_for_their_own_reason(row_universe):
    ambiguous = row_universe["ambiguous_rows"]
    assert len(ambiguous) == 42
    assert row_universe["ambiguous_admitted"] == []
    assert len(row_universe["ambiguous_excluded"]) == 42
    assert {row["exclusion_reason"] for row in ambiguous} == {
        ROW_EXCLUSION_AMBIGUOUS_GEOMETRY
    }


def test_channel_disagreements_are_excluded_and_preserved(row_universe, summary):
    disagreeing = [
        row
        for row in row_universe["rows"]
        if row["disagreement_class"]
        in ("geometry_visible_detector_hidden", "geometry_hidden_detector_visible")
    ]
    assert len(disagreeing) == 57 + 313
    assert {row["exclusion_reason"] for row in disagreeing} == {
        ROW_EXCLUSION_CHANNEL_DISAGREEMENT
    }
    assert summary["no_wall_control_rows_excluded_by_channel_disagreement"] == 9
    # the raw channels are preserved on every excluded row
    for row in disagreeing[:50]:
        assert row["geometric_visible"] is not None
        assert row["empirical_magenta_visible"] is not None


def test_no_quarantined_or_ambiguous_row_is_admitted(row_universe):
    for row in row_universe["admitted_rows"]:
        assert row["quarantined"] is False
        assert row["geometric_ambiguous"] is False
        assert row["disagreement_class"] == "agreement"


def test_no_object_rows_are_never_admitted(row_universe):
    no_object = [
        row
        for row in row_universe["rows"]
        if row["control_type"] == CONTROL_TYPE_NO_OBJECT
    ]
    assert len(no_object) == EXPECTED_NO_OBJECT_COUNT
    assert {row["status"] for row in no_object} == {"excluded"}
    assert {row["exclusion_reason"] for row in no_object} == {ROW_EXCLUSION_NO_OBJECT}
    assert all(row["oracle_target_present"] is False for row in no_object)


# ------------------------------------------------ row admission and exclusion
def test_successor_accounting_reconciles(summary):
    assert summary["total_model_frame_key_count"] == EXPECTED_MODEL_FRAME_KEY_COUNT
    assert summary["target_bearing_key_count"] == EXPECTED_TARGET_BEARING_COUNT
    assert summary["no_object_not_applicable_key_count"] == EXPECTED_NO_OBJECT_COUNT
    assert summary["admitted_analysis_row_count"] == 662
    assert summary["excluded_analysis_row_count"] == 1_806
    total = summary["admitted_analysis_row_count"] + sum(
        item["row_count"] for item in summary["excluded_counts_by_reason"]
    )
    assert total == EXPECTED_MODEL_FRAME_KEY_COUNT
    assert summary["person_c_accepted_trajectory_count"] == EXPECTED_TRAJECTORY_COUNT
    assert summary["person_c_rejected_trajectory_count"] == 0
    assert summary["person_c_quarantined_admitted_count"] == 0


def test_admitted_rows_carry_complete_oracle_fields(row_universe, oracle):
    targets = oracle["target_by_key"]
    for row in row_universe["admitted_rows"]:
        target = targets[(row["trajectory_id"], row["model_frame_idx"])]
        for field in ALWAYS_REQUIRED_TARGET_FIELDS:
            assert target[field] is not None, (row["trajectory_id"], field)
        if "hidden_spread" in row["analysis_scopes"]:
            for field in HIDDEN_ONLY_TARGET_FIELDS:
                assert target[field] is not None
        else:
            for field in HIDDEN_ONLY_TARGET_FIELDS:
                assert target[field] is None


def test_every_row_has_an_explicit_disposition(row_universe):
    for row in row_universe["rows"]:
        assert row["status"] in {"accepted", "excluded"}
        if row["status"] == "excluded":
            assert row["exclusion_reason"]
        else:
            assert row["exclusion_reason"] is None
            assert row["analysis_scopes"]
            assert row["admission_stratum"]


def test_hidden_and_visible_scopes_use_the_strict_flag(row_universe):
    for row in row_universe["admitted_rows"]:
        if "hidden_mean" in row["analysis_scopes"]:
            assert row["visible_flag"] is False
            assert row["geometric_visible"] is False
        else:
            assert row["analysis_scopes"] == ["visible_no_wall_control"]
            assert row["visible_flag"] is True


def test_visible_rows_outside_the_no_wall_control_are_excluded(row_universe):
    excluded = [
        row
        for row in row_universe["excluded_rows"]
        if row["exclusion_reason"] == ROW_EXCLUSION_OUTSIDE_SELECTION
    ]
    assert excluded
    for row in excluded:
        assert row["visible_flag"] is True
        assert row["control_type"] != "no_wall_visible_control"


# --------------------------------------------------------- fold compatibility
def test_existing_fold_manifest_remains_valid(row_universe):
    fold = validate_fold_compatibility(row_universe, repository_root=REPOSITORY_ROOT)
    assert fold["fold_compatibility_pass"] is True
    assert fold["leakage_audit_pass"] is True
    assert fold["fold_manifest_sha256"] == PERSON_B_FOLD_MANIFEST_SHA256
    assert fold["unresolved_frame_keys"] == []
    assert fold["fold_disagreements"] == []
    assert fold["leaking_layout_ids"] == []
    assert fold["leaking_trajectory_ids"] == []
    assert {
        item["layout_id"]: item["fold_idx"] for item in fold["layout_assignments"]
    } == FROZEN_FOLD_ASSIGNMENT
    assert all(item["row_count"] > 0 for item in fold["admitted_row_counts_by_fold"])


def test_fold_compatibility_detects_a_reassigned_layout(row_universe):
    tampered = copy.deepcopy(dict(row_universe))
    tampered["rows"] = [dict(row) for row in row_universe["rows"]]
    tampered["rows"][0]["fold_idx"] = (tampered["rows"][0]["fold_idx"] + 1) % 5
    tampered["admitted_rows"] = [
        row for row in tampered["rows"] if row["status"] == "accepted"
    ]
    fold = validate_fold_compatibility(tampered, repository_root=REPOSITORY_ROOT)
    assert fold["fold_compatibility_pass"] is False
    assert fold["fold_disagreements"]


# ------------------------------------------------------- published artifacts
def test_published_oracle_manifest_is_complete():
    manifest = _published("oracle_target_manifest.json")
    validate_sealed_artifact(
        manifest, expected_type="person_b_66_cell_oracle_target_manifest"
    )
    provenance = manifest["provenance"]
    assert provenance["person_c_commit"] == PERSON_C_COMMIT
    assert provenance["person_c_oracle_handoff_sha256"] == C_ORACLE_HANDOFF_SHA256
    assert provenance["person_c_visibility_join_sha256"] == C_VISIBILITY_JOIN_SHA256
    assert provenance["person_c_event_table_sha256"] == C_EVENT_TABLE_SHA256
    assert provenance["person_c_accepted_manifest_sha256"] == C_ACCEPTED_MANIFEST_SHA256
    assert provenance["person_b_fold_manifest_sha256"] == PERSON_B_FOLD_MANIFEST_SHA256
    assert manifest["oracle_target_row_count"] == EXPECTED_TARGET_BEARING_COUNT
    assert manifest["dtype_contract"]["stored_activation_dtype"] == (
        STORED_ACTIVATION_DTYPE
    )
    assert manifest["dtype_contract"]["analysis_arithmetic_dtype"] == (
        ANALYSIS_ARITHMETIC_DTYPE
    )
    assert manifest["oracle_implementation"]["formulas_changed_after_seeing_output"] is (
        False
    )
    assert manifest["oracle_implementation"][
        "target_truth_reconstructed_from_pixels"
    ] is False
    assert manifest["oracle_implementation"][
        "detector_position_used_as_hidden_truth"
    ] is False
    assert manifest["person_c_visibility_labels_modified"] is False
    assert manifest["person_e_detector_outputs_modified"] is False
    assert manifest["person_a_authorities_modified"] is False
    assert manifest["frozen_step_4_1_decision"] == "FAIL"
    assert manifest["config_hash"] == hash_core_analysis_config()


def test_published_records_match_the_manifest():
    manifest = _published("oracle_target_manifest.json")
    payload = (PACKAGE / "oracle_target_records.jsonl").read_bytes()
    assert hashlib.sha256(payload).hexdigest() == manifest["target_records_sha256"]
    records = _published_jsonl("oracle_target_records.jsonl")
    assert len(records) == manifest["oracle_target_row_count"]
    keys = {(row["trajectory_id"], row["model_frame_idx"]) for row in records}
    assert len(keys) == len(records)


def test_published_row_universe_records_cover_every_key():
    rows = _published_jsonl("row_universe_records.jsonl")
    assert len(rows) == EXPECTED_MODEL_FRAME_KEY_COUNT
    keys = {(row["trajectory_id"], row["model_frame_idx"]) for row in rows}
    assert len(keys) == EXPECTED_MODEL_FRAME_KEY_COUNT


def test_published_admission_ledger_documents_both_policies():
    ledger = _published("admission_exclusion_ledger.json")
    validate_sealed_artifact(
        ledger, expected_type="person_b_66_cell_admission_exclusion_ledger"
    )
    ambiguity = ledger["ambiguity_policy"]
    assert ambiguity["row_count"] == 42
    assert ambiguity["admitted_count"] == 0
    assert ambiguity["person_b_chose_a_geometry_interpretation"] is False
    disagreement = ledger["disagreement_policy"]
    assert disagreement["person_b_retuned_detector"] is False
    assert disagreement["person_b_modified_geometric_visibility"] is False
    assert disagreement["person_b_replaced_visible_flag_rule"] is False
    assert disagreement["no_wall_disagreement_cause_invented"] is False
    assert (
        disagreement["no_wall_control_rows_excluded_by_channel_disagreement"] == 9
    )
    assert ledger["quarantine_policy"]["person_c_quarantined_admitted_count"] == 0
    assert ledger["trajectory_acceptance_unchanged"][
        "person_c_accepted_trajectory_count"
    ] == EXPECTED_TRAJECTORY_COUNT


def test_published_handoffs_are_complete():
    b_to_a = _published("b_to_a_successor_handoff.json")
    validate_sealed_artifact(
        b_to_a, expected_type="person_b_to_person_a_66_cell_successor_handoff"
    )
    assert b_to_a["extraction_row_policy"][
        "person_a_must_restrict_to_person_b_admitted_rows"
    ] is False
    assert b_to_a["extraction_row_policy"]["model_frame_key_count"] == (
        EXPECTED_MODEL_FRAME_KEY_COUNT
    )
    assert b_to_a["dtype_decision"]["stored_activation_dtype"] == (
        STORED_ACTIVATION_DTYPE
    )
    assert b_to_a["model_preprocess_resolution"]["authority_valid"] is True
    assert b_to_a["downstream_acceptance_claimed"] is False

    b_to_d = _published("b_to_d_successor_handoff.json")
    validate_sealed_artifact(
        b_to_d, expected_type="person_b_to_person_d_66_cell_successor_handoff"
    )
    assert b_to_d["eligible_baseline_universe"]["admitted_analysis_row_count"] == 662
    assert b_to_d["metric_contract_after_person_d_predictions_exist"][
        "config_hash"
    ] == hash_core_analysis_config()
    assert b_to_d["ambiguity_and_disagreement_policy"][
        "person_d_must_not_reinstate_excluded_rows"
    ] is True
    assert b_to_d["downstream_acceptance_claimed"] is False


def test_published_u4_status_remains_ineligible():
    u4 = _published("u4_status.json")
    validate_sealed_artifact(u4, expected_type="person_b_66_cell_u4_status")
    assert u4["CURRENT_66_CELL_U4_REVEAL_ELIGIBLE"] is False
    assert u4["U4_SUPPLEMENTAL_CAPTURE_REQUIRED"] is True
    assert u4["VALID_TERMINAL_REVEAL_COUNT"] == 0
    assert u4["heldout_event_ids_frozen"] is False
    assert u4["frozen_heldout_event_ids"] is None
    assert u4["reveal_window_requirement_changed"] is False
    assert u4["reveal_window_seconds"] == [-1.0, 1.0]


def test_published_inventory_matches_published_bytes():
    inventory = _published("sha256_inventory.json")
    assert inventory["inventory_excludes_self"] is True
    for item in inventory["files"]:
        payload = (REPOSITORY_ROOT / item["path"]).read_bytes()
        assert hashlib.sha256(payload).hexdigest() == item["sha256"], item["path"]
        assert len(payload) == item["byte_size"], item["path"]


def test_package_passes_the_deterministic_validator():
    module = _module(VALIDATOR, "person_b_66_cell_oracle_target_validator")
    result = module.validate()
    assert result["validated"] is True
    assert result["deterministic"] is True
    assert result["oracle_target_row_count"] == EXPECTED_TARGET_BEARING_COUNT
    assert result["fold_compatibility_pass"] is True


def test_predecessor_preactivation_evidence_is_not_rewritten():
    predecessor = json.loads(
        (
            REPOSITORY_ROOT
            / "docs"
            / "status"
            / "person_b_66_cell_preactivation_v0_1"
            / "row_universe_receipt.json"
        ).read_text(encoding="utf-8")
    )
    assert predecessor["admitted_analysis_row_count"] == 984
    assert predecessor["excluded_analysis_row_count"] == 1_484
    successor = _published("row_universe_receipt_v0_2.json")
    assert successor["supersedes"]["predecessor_admitted_analysis_row_count"] == 984
    assert successor["supersedes"]["predecessor_evidence_rewritten"] is False
