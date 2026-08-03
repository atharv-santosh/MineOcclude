"""Preparation-only tests for Person A's ten-pilot expansion runner."""
from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from unittest import mock

import pytest

ROOT = Path(__file__).resolve().parents[2]
RUNNER_PATH = ROOT / "scripts" / "run_person_a_phase6_ten_pilot_sagemaker.py"
WRAPPER_PATH = ROOT / "scripts" / "run_person_a_phase6_ten_pilot_sagemaker.sh"


def load_runner():
    specification = importlib.util.spec_from_file_location(
        "person_a_phase6_ten_pilot_sagemaker_runner_v0_1", RUNNER_PATH
    )
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


runner = load_runner()


def test_exact_selected_set_and_additional_count():
    plan = runner.plan_document()
    assert plan["ordered_pilot_ids"] == [
        "layout_00_ep9403",
        "layout_00_ep9441",
        "layout_01_ep9405",
        "layout_01_ep9442",
        "layout_02_ep9407",
        "layout_02_ep9432",
        "layout_03_ep9404",
        "layout_03_ep9443",
        "layout_04_ep9406",
        "layout_04_ep9444",
    ]
    assert plan["total_pilot_count"] == 10
    assert plan["additional_pilot_count"] == 9
    assert plan["combined_expected_activation_row_count"] == 37480


def test_existing_pilot_is_reused_and_never_in_extraction_sequence():
    plan = runner.plan_document()
    assert plan["existing_pilot_reused"] == "layout_00_ep9403"
    assert plan["existing_pilot_reextraction_authorized"] is False
    assert [spec.trajectory_id for spec in runner.additional_pilot_specs()] == plan[
        "ordered_pilot_ids"
    ][1:]
    assert all(
        spec.trajectory_id != runner.EXISTING_PILOT
        for spec in runner.additional_pilot_specs()
    )


def test_exact_five_no_wall_controls_and_frozen_folds():
    assert runner.no_wall_control_ids() == [
        "layout_00_ep9441",
        "layout_01_ep9442",
        "layout_02_ep9432",
        "layout_03_ep9443",
        "layout_04_ep9444",
    ]
    assert [(spec.layout_id, spec.fold_idx) for spec in runner.PILOT_SPECS[::2]] == [
        ("layout_00", 1),
        ("layout_01", 2),
        ("layout_02", 4),
        ("layout_03", 0),
        ("layout_04", 3),
    ]


def test_plan_and_authority_reads_never_load_model_or_torch():
    tree = ast.parse(RUNNER_PATH.read_text(encoding="utf-8"))
    top_imports = {
        alias.name
        for node in tree.body
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    assert "torch" not in top_imports
    with mock.patch.object(
        runner.importlib,
        "import_module",
        side_effect=AssertionError("preparation must not import a model runtime"),
    ):
        assert runner.plan_document()["local_scientific_execution_performed"] is False
        authorities = runner.load_authority_documents(ROOT)
    assert authorities["b_selection"]["ordered_pilot_ids"] == runner.ordered_pilot_ids()


def test_full_248_frame_cardinality_is_4960():
    assert runner.PILOT_SPECS[0].frame_count == 248
    assert runner.PILOT_SPECS[0].expected_activation_rows == 4960
    assert all(
        spec.expected_activation_rows
        == spec.frame_count * len(runner.single.FROZEN_PHASE6_LAYERS)
        for spec in runner.PILOT_SPECS
    )


def test_existing_store_validation_uses_hash_size_rows_and_chunks():
    root = mock.Mock(spec=Path)
    root.is_symlink.return_value = False
    root.is_dir.return_value = True
    index_path = mock.Mock(spec=Path)
    chunk_path = mock.Mock(spec=Path)
    chunk_bytes = b"existing immutable activation bytes"
    row = {"trajectory_id": runner.EXISTING_PILOT}
    document = {
        "chunks": [{
            "byte_size": len(chunk_bytes),
            "chunk_id": "chunk-1",
            "path": "chunks/chunk.npy",
            "row_count": 1,
            "sha256": hashlib.sha256(chunk_bytes).hexdigest(),
        }],
        "format_version": runner.single.ACTIVATION_INDEX_V2_FORMAT_VERSION,
        "index_rows": [row],
        "run_status": "completed",
    }
    index_bytes = json.dumps(document).encode("utf-8")
    index_path.read_bytes.return_value = index_bytes
    chunk_path.stat.return_value.st_size = len(chunk_bytes)
    with mock.patch.object(
        runner,
        "_safe_store_file",
        side_effect=[index_path, chunk_path],
    ), mock.patch.object(
        runner,
        "_sha256_file",
        return_value=hashlib.sha256(chunk_bytes).hexdigest(),
    ):
        result = runner.validate_existing_artifacts(
            root,
            expected_index_sha256=hashlib.sha256(index_bytes).hexdigest(),
            expected_index_byte_size=len(index_bytes),
            expected_row_count=1,
        )
    assert result["inventory"]["existing_pilot_reextracted"] is False
    assert result["inventory"]["chunks"][0]["sha256"] == hashlib.sha256(
        chunk_bytes
    ).hexdigest()


def test_pilot_failure_stops_later_pilots_and_preserves_prior_success():
    calls = []
    specs = runner.additional_pilot_specs()[:3]

    def execute(spec):
        calls.append(spec.trajectory_id)
        status = "FAIL" if len(calls) == 2 else "PASS"
        return {"report": {"pilot": spec.trajectory_id, "status": status}}

    result = runner.execute_additional_pilot_sequence(specs, execute)
    assert calls == [specs[0].trajectory_id, specs[1].trajectory_id]
    assert result["successful_pilots"] == [specs[0].trajectory_id]
    assert result["failed_pilot"] == specs[1].trajectory_id
    assert result["later_pilots_executed_after_failure"] is False


def fake_source(spec, *, duplicate=False):
    rows = []
    for layer in ((0, 0) if duplicate else (0,)):
        rows.append({
            "trajectory_id": spec.trajectory_id,
            "global_model_frame_idx": 0,
            "context_local_pair_idx": 0,
            "source_frame_id": f"{spec.trajectory_id}:render_frame:0",
            "source_tick": 0,
            "layer_idx": layer,
            "hook_site": runner.single.HOOK_SITE,
            "checkpoint_hash": runner.single.MAIN_CHECKPOINT_SHA256,
            "preprocess_hash": runner.single.PREPROCESS_HASH,
        })
    return {
        "index_rows": rows,
        "inventory": {"activation_index": {"sha256": spec.capture_package_sha256}},
        "trajectory_id": spec.trajectory_id,
    }


def test_combined_index_order_and_uniqueness_are_deterministic():
    sources = [fake_source(spec) for spec in runner.PILOT_SPECS]
    combined = runner.build_combined_index(sources, expected_row_count=10)
    assert combined["ordered_pilot_ids"] == runner.ordered_pilot_ids()
    assert [row["trajectory_id"] for row in combined["index_rows"]] == runner.ordered_pilot_ids()
    assert combined["scientific_identity_collision_count"] == 0


def test_combined_index_rejects_duplicate_identity():
    sources = [fake_source(spec) for spec in runner.PILOT_SPECS]
    sources[1] = fake_source(runner.PILOT_SPECS[1], duplicate=True)
    with pytest.raises(runner.MultiPilotRunnerError, match="collision"):
        runner.build_combined_index(sources, expected_row_count=11)


def test_authorization_schema_binds_exact_runner_commit_and_command():
    current = "a" * 40
    document = {
        "decision": "AUTHORIZE_PERSON_A_PHASE6_TEN_PILOT_EXPANSION_EXECUTION",
        "owner": "person_b",
        "person_a_expansion_execution_authorized": True,
        "person_a_expansion_runner_commit": current,
        "person_b_selection_commit": runner.PERSON_B_SELECTION_COMMIT,
        "person_c_expansion_acceptance_commit": runner.PERSON_C_ACCEPTANCE_COMMIT,
        "ordered_pilot_ids": runner.ordered_pilot_ids(),
        "authorized_additional_pilot_ids": [
            spec.trajectory_id for spec in runner.additional_pilot_specs()
        ],
        "authorized_steps": list(runner.PHASE6_STEPS),
        "execution_host": "aws_sagemaker_linux_gpu",
        "device": "cuda:0",
        "seed": 20260725,
        "existing_pilot_reused": runner.EXISTING_PILOT,
        "existing_pilot_reextraction_authorized": False,
        "hidden_state_interpretation_authorized": False,
        "step_6_6_complete": False,
        "future_registry_v2_output_acceptance_authorized": False,
        "u4_output_inspected": False,
        "sagemaker_command": runner.SAGEMAKER_COMMAND,
    }
    runner.validate_authorization_document(document, current_commit=current)
    changed = dict(document, seed=0)
    with pytest.raises(runner.MultiPilotRunnerError):
        runner.validate_authorization_document(changed, current_commit=current)


def test_wrapper_is_sagemaker_tmux_ready_and_propagates_failure():
    wrapper = WRAPPER_PATH.read_text(encoding="utf-8")
    assert "run_person_a_phase6_ten_pilot_sagemaker.py\" run" in wrapper
    assert "PERSON_A_PHASE6_EXISTING_ARTIFACT_ROOT" in wrapper
    assert "PERSON_B_PHASE6_EXPANSION_AUTHORIZATION_OBJECT" in wrapper
    assert "--seed 20260725" in wrapper
    assert "--device cuda:0" in wrapper
    assert "PIPESTATUS[0]" in wrapper
    assert runner.SAGEMAKER_COMMAND == (
        "tmux new-session -d -s person-a-phase6-ten-pilot "
        "'bash scripts/run_person_a_phase6_ten_pilot_sagemaker.sh'"
    )
