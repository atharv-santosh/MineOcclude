from __future__ import annotations

import copy
from pathlib import Path

import pytest

from mineocclude.analysis.config import hash_core_analysis_config
from mineocclude.analysis.coordinates import coordinate_frame_hash
from mineocclude.analysis.manifests import seal_artifact
from mineocclude.contracts.rollout_registry import (
    IMMUTABLE_REGISTRY_SCHEMA_VERSION,
    validate_immutable_run_artifact_registry,
)
from mineocclude.analysis.handoffs import (
    build_d_baseline_request,
    build_e_registration_request,
    build_phase6_handoff_report,
)
from mineocclude.analysis.pilot import (
    build_positive_control_gate,
    build_pilot_failure_artifact,
    build_u2_pilot_metrics,
    prepare_pilot_inputs,
    require_positive_control_pass,
    run_plumbing_smoke,
    run_probe_scope,
)
from mineocclude.analysis.selection import (
    SCOPE_HIDDEN_MEAN,
    SCOPE_HIDDEN_SPREAD,
    SCOPE_VISIBLE_NO_WALL,
    build_analysis_selection_manifest,
)
from mineocclude.probes.bridge import derive_probe_code_sha
from mineocclude.probes.bridge import (
    ProbeBridgeError,
    build_frame_fold_manifest,
    build_joined_frame_table,
    build_probe_ready_matrices,
)
from tests.probes.test_probe_bridge import make_multilayout_a_b_fixture


ROOT = Path(__file__).resolve().parents[2]


def _pilot_inputs():
    activation, targets, chunk_payloads, *_ = make_multilayout_a_b_fixture()
    preparation = prepare_pilot_inputs(
        activation,
        targets,
        chunk_payloads,
        artifact_id_prefix="known_answer_pilot",
    )
    selections = []
    for trajectory_id in sorted(
        {row["trajectory_id"] for row in preparation.frame_table["rows"]}
    ):
        trajectory_rows = [
            row
            for row in preparation.frame_table["rows"]
            if row["trajectory_id"] == trajectory_id
        ]
        visible = next(row for row in trajectory_rows if row["visibility"] == "visible")
        hidden = next(
            row
            for row in trajectory_rows
            if row["visibility"] == "occluded"
            and row["log_sigma_oracle"] is not None
        )
        selections.extend(
            [
                {
                    "trajectory_id": visible["trajectory_id"],
                    "model_frame_idx": visible["model_frame_idx"],
                    "layout_id": visible["layout_id"],
                    "scope": SCOPE_VISIBLE_NO_WALL,
                    "condition_role": "no_wall_visible_control",
                },
                {
                    "trajectory_id": hidden["trajectory_id"],
                    "model_frame_idx": hidden["model_frame_idx"],
                    "layout_id": hidden["layout_id"],
                    "scope": SCOPE_HIDDEN_MEAN,
                    "condition_role": "regime_a_core",
                },
                {
                    "trajectory_id": hidden["trajectory_id"],
                    "model_frame_idx": hidden["model_frame_idx"],
                    "layout_id": hidden["layout_id"],
                    "scope": SCOPE_HIDDEN_SPREAD,
                    "condition_role": "regime_a_core",
                },
            ]
        )
    selection = build_analysis_selection_manifest(
        preparation.frame_table,
        selections,
        artifact_id="known_answer_pilot:selection",
        code_sha=derive_probe_code_sha(),
        source_condition_manifest_hash="7" * 64,
    )
    return activation, targets, chunk_payloads, preparation, selection


def test_pilot_preparation_and_control_scope_are_fully_provenanced() -> None:
    activation, targets, chunks, preparation, selection = _pilot_inputs()
    assert preparation.execution_class == "evaluative_grouped_oof"
    assert preparation.fold_manifest is not None
    assert preparation.filter_result.accepted_count == len(targets["rows"])
    assert preparation.oracle_audit["status"] == "pass"

    control = run_probe_scope(
        preparation,
        activation,
        targets,
        chunks,
        selection,
        scope=SCOPE_VISIBLE_NO_WALL,
        artifact_id_prefix="known_answer_pilot",
        permutation_count=3,
    )
    assert len(control.ridge_runs) == 2
    assert all(len(run.scaler_artifacts) == 5 for run in control.ridge_runs)
    assert all(len(run.fit_artifacts) == 5 for run in control.ridge_runs)
    assert control.bundle["selection_manifest_hash"] == selection["artifact_hash"]
    assert control.bundle["scientific_use"] == "forbidden"

    gate = build_positive_control_gate(
        control,
        decision="pass",
        approver="known_answer_test",
        rationale="Exercises the explicit gate boundary only.",
    )
    require_positive_control_pass(gate, control_run=control)
    mean_run = run_probe_scope(
        preparation,
        activation,
        targets,
        chunks,
        selection,
        scope=SCOPE_HIDDEN_MEAN,
        artifact_id_prefix="known_answer_pilot",
        permutation_count=3,
    )
    spread_run = run_probe_scope(
        preparation,
        activation,
        targets,
        chunks,
        selection,
        scope=SCOPE_HIDDEN_SPREAD,
        artifact_id_prefix="known_answer_pilot",
        permutation_count=3,
    )
    u2 = build_u2_pilot_metrics(
        mean_run,
        spread_run,
        control_run=control,
        control_gate=gate,
        artifact_id_prefix="known_answer_pilot",
    )
    assert len(u2.result_artifacts) == 2
    assert all(
        artifact["analysis_family"] == "U2"
        for artifact in u2.result_artifacts
    )


def test_d_request_and_e_registration_packet_are_ready_without_receipts() -> None:
    activation, targets, chunks, preparation, selection = _pilot_inputs()
    request = build_d_baseline_request(
        preparation.frame_table,
        preparation.fold_manifest,
        selection,
        artifact_id="known_answer_pilot:d_request",
    )
    assert request["requested_baseline_families"] == [
        "time_only",
        "last_seen",
        "shuffled",
    ]
    assert {row["fold_idx"] for row in request["rows"]} == {0, 1, 2, 3, 4}
    assert "x_true_blocks" not in request["rows"][0]

    control = run_probe_scope(
        preparation,
        activation,
        targets,
        chunks,
        selection,
        scope=SCOPE_VISIBLE_NO_WALL,
        artifact_id_prefix="known_answer_registration",
        permutation_count=2,
    )
    analysis_artifacts = []
    for ridge, permutation in zip(
        control.ridge_runs,
        control.permutation_runs,
    ):
        analysis_artifacts.extend(
            [
                ridge.matrix_artifact,
                *ridge.scaler_artifacts,
                *ridge.fit_artifacts,
                ridge.prediction_artifact,
                ridge.u1_result_artifact,
                permutation.result_artifact,
            ]
        )
    analysis_artifacts.append(control.bundle)
    registration_sources = [
        targets,
        preparation.frame_table,
        preparation.oracle_audit,
        preparation.intake_receipt,
        preparation.filter_audit,
        preparation.fold_manifest,
        selection,
        request,
        *analysis_artifacts,
    ]
    registration = build_e_registration_request(
        registration_sources,
        run_id="known_answer_person_b_run",
        checkpoint_hash="2" * 64,
        data_identity_hash="3" * 64,
        preprocess_hash="4" * 64,
        environment_hash="5" * 64,
        command=["python", "scripts/run_person_b_pilot.py"],
        started_at="2026-07-23T12:00:00Z",
        ended_at="2026-07-23T12:01:00Z",
        uri_prefix="memory://known-answer/person-b/",
        git_dirty=True,
    )
    assert registration["status"] == "ready_for_e_validation_and_append"
    assert registration["is_registry_receipt"] is False
    assert len(registration["artifact_records"]) == len(registration_sources)
    assert len(registration["run_records"]) == len(registration_sources)
    registry = {
        "schema_version": "1.0",
        "immutable_registry_schema_version": IMMUTABLE_REGISTRY_SCHEMA_VERSION,
        "registry_id": "known_answer_person_b_registry",
        "synthetic": True,
        "scientific_use": "forbidden",
        "runs": registration["run_records"],
        "artifacts": registration["artifact_records"],
    }
    validation = validate_immutable_run_artifact_registry(registry)
    assert validation.accepted, validation.rejections
    report = build_phase6_handoff_report(
        request,
        registration,
        artifact_id="known_answer_pilot:phase6_handoffs",
        repository_root=ROOT,
    )
    assert report["person_a"]["status"].endswith("awaiting_acknowledgement")
    assert report["receipts"] == {
        "person_a": None,
        "person_d": None,
        "person_e": None,
    }


def test_live_signed_targets_are_permitted_but_require_sealed_selection() -> None:
    activation, targets, chunks, *_ = make_multilayout_a_b_fixture()
    activation = copy.deepcopy(activation)
    targets = copy.deepcopy(targets)
    activation.pop("source_fixture_lineage", None)
    for row in activation["index_rows"]:
        row["regime"] = "regime_a"
    targets.pop("fixture_metadata")
    for row in targets["rows"]:
        row["regime"] = "regime_a"
        row["config_hash"] = hash_core_analysis_config()
        row.pop("synthetic", None)
        row.pop("scientific_use", None)
    coordinate_frame = {
        "coordinate_frame_schema_version": "person-b-wall-parallel-frame-v0.1",
        "coordinate_frame_id": "known_answer_live_signed_frame",
        "wall_parallel_origin_world_xyz": [0.0, 0.0, 0.0],
        "wall_parallel_positive_unit_vector_world_xyz": [1.0, 0.0, 0.0],
        "source_layout_manifest_hash": "7" * 64,
        "adapter_signoff": {"person_b": True, "person_c": True},
    }
    coordinate_frame["coordinate_frame_hash"] = coordinate_frame_hash(
        coordinate_frame
    )
    targets["coordinate_frame"] = coordinate_frame
    target_payload = dict(targets)
    target_payload.pop("artifact_hash")
    target_payload.update(
        {
            "config_hash": hash_core_analysis_config(),
            "synthetic": False,
            "scientific_use": "permitted",
        }
    )
    targets = seal_artifact(target_payload)

    frame_table = build_joined_frame_table(activation, targets)
    assert frame_table["synthetic"] is False
    assert frame_table["scientific_use"] == "permitted"
    folds = build_frame_fold_manifest(
        frame_table,
        artifact_id="known_answer_live:folds",
    )
    with pytest.raises(ProbeBridgeError, match="explicit sealed row selection"):
        build_probe_ready_matrices(
            activation,
            targets,
            frame_table,
            folds,
            chunks,
        )


def test_single_layout_smoke_emits_no_scientific_metrics() -> None:
    activation, targets, chunks, *_ = make_multilayout_a_b_fixture()
    activation = copy.deepcopy(activation)
    targets = copy.deepcopy(targets)
    retained_layout = activation["index_rows"][0]["layout_id"]
    retained_rows = [
        row for row in activation["index_rows"] if row["layout_id"] == retained_layout
    ]
    retained_chunk_ids = {row["activation_chunk_id"] for row in retained_rows}
    activation["index_rows"] = retained_rows
    activation["chunks"] = [
        row for row in activation["chunks"] if row["chunk_id"] in retained_chunk_ids
    ]
    activation["cardinality_report"] = {
        "accepted_manifest_rows": 3,
        "expected_activation_rows": 6,
        "actual_activation_rows": 6,
        "expected_rows_by_layer": {"5": 3, "12": 3},
        "actual_rows_by_layer": {"5": 3, "12": 3},
    }
    chunks = {key: value for key, value in chunks.items() if key in retained_chunk_ids}
    targets["rows"] = [
        row for row in targets["rows"] if row["layout_id"] == retained_layout
    ]
    target_payload = dict(targets)
    target_payload.pop("artifact_hash")
    targets = seal_artifact(target_payload)
    preparation = prepare_pilot_inputs(
        activation,
        targets,
        chunks,
        artifact_id_prefix="known_answer_single_layout",
    )
    assert preparation.fold_manifest is None
    visible = next(
        row
        for row in preparation.frame_table["rows"]
        if row["visibility"] == "visible"
    )
    selection = build_analysis_selection_manifest(
        preparation.frame_table,
        [
            {
                "trajectory_id": visible["trajectory_id"],
                "model_frame_idx": visible["model_frame_idx"],
                "layout_id": visible["layout_id"],
                "scope": SCOPE_VISIBLE_NO_WALL,
                "condition_role": "no_wall_visible_control",
            }
        ],
        artifact_id="known_answer_single_layout:selection",
        code_sha=derive_probe_code_sha(),
        source_condition_manifest_hash="7" * 64,
    )
    smoke = run_plumbing_smoke(
        preparation,
        activation,
        targets,
        chunks,
        selection,
        scope=SCOPE_VISIBLE_NO_WALL,
        artifact_id="known_answer_single_layout:smoke",
    )
    assert smoke["reported_metrics"] == []
    assert smoke["scientific_use"] == "forbidden"
    assert smoke["interpretation"] == "plumbing_only_not_a_population_claim"


def test_pilot_failure_is_null_and_never_a_scientific_zero() -> None:
    failure = build_pilot_failure_artifact(
        artifact_id="known_answer_pilot:failure",
        stage="join",
        input_manifest_hash="8" * 64,
        error=ValueError("shifted activation row"),
        source_synthetic=False,
    )
    assert failure["outcome_value"] is None
    assert failure["status"] == "failed"
    assert failure["scientific_use"] == "forbidden"
