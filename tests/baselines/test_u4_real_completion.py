"""Tests for the real Steps 7.1-7.3 (U4) CLI wiring.

``run_person_d_phase6to8_completion.py``'s own blocker documents tell the
reader to run this repository's CLI with ``--u4-direction-record`` and
``--u4-measurements`` flags once Person B/E publish real data -- but
until ``run_person_d_u4_real_completion.py`` existed, no script actually
defined those flags. These tests build small, explicitly-synthetic
test fixtures (never claimed as real evidence) shaped exactly like the
real handoffs Person B/E would publish, and verify the wiring actually
produces real (``evidence_kind="real"``), valid, fail-closed documents.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_script():
    spec = importlib.util.spec_from_file_location(
        "run_person_d_u4_real_completion",
        REPO_ROOT / "scripts" / "run_person_d_u4_real_completion.py",
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


SCRIPT = _load_script()

_EVIDENCE = {
    "direction_id": "test_primary_direction",
    "direction_version": "v1.0",
    "direction_hash": "a" * 64,
    "space": "raw_activation",
    "dimension": 2048,
    "seed": 20260720,
    "residual_norm_before_normalization": 3.5,
    "near_zero_threshold": 1e-6,
    "pre_projection_norm": 3.5,
    "post_projection_norm": 1.0,
    "standardized_during_fit": False,
    "inverse_transformed_before_export": False,
    "raw_space_equivalence_verified": True,
    "max_relative_activation_norm": 0.25,
    "typical_activation_norm": 20.0,
    "target_layer_idx": 12,
    "target_timestep_idx": 7,
    "hook_site": "decoder_layer_output_residual_stream",
    "held_out_partition_id": "heldout_v1",
    "used_test_data_to_select_direction": False,
    "used_heldout_outcomes_to_select_direction": False,
    "supersession_status": "current",
}


def _direction_record(**overrides) -> dict:
    document = {
        "held_out_events": [
            {"event_id": "test:reveal:1", "trajectory_id": "layout_01_ep99001", "layout_id": "layout_01"},
        ],
        "rollout_seeds": [20260720],
        "doses": [
            {"dose_id": "pos_1", "alpha_requested": 4.0, "alpha_applied": 4.0, "cap_reduced": False},
        ],
        "primary_direction": {
            "direction_id": "test_primary_direction",
            "direction_version": "v1.0",
            "direction_sha256": "a" * 64,
        },
        "random_directions": [
            {"direction_id": "test_random_1", "direction_version": "v1.0", "direction_sha256": "b" * 64, "seed": 1},
        ],
        "orthogonal_directions": [
            {"direction_id": "test_orthogonal_1", "direction_version": "v1.0", "direction_sha256": "c" * 64, "seed": 2},
        ],
        "target_layer_idx": 12,
        "target_timestep_idx": 7,
        "wrong_layer_idx": 3,
        "wrong_timestep_idx": 1,
        "source_commit": "0" * 40,
    }
    document.update(overrides)
    return document


def _write_json(path: Path, document) -> Path:
    path.write_text(json.dumps(document, indent=2), encoding="utf-8")
    return path


# --------------------------------------------------------------------------
# Real wiring, incrementally more complete evidence
# --------------------------------------------------------------------------


def test_minimal_real_direction_record_builds_a_real_manifest(tmp_path):
    record_path = _write_json(tmp_path / "direction_record.json", _direction_record())
    output_root = tmp_path / "out"

    document = SCRIPT.build_all(output_root, record_path, None, "person_a_commit", "person_b_commit")

    assert document["evidence_kind"] == "real"
    assert document["real_execution_performed"] is True
    assert document["measurements_supplied"] is False

    manifest = json.loads((output_root / "step7_1_u4_control_manifest.json").read_text())
    assert manifest["evidence_kind"] == "real"
    assert manifest["status"] == "frozen"
    assert manifest["source_authorities"]["real_direction_available"] == "YES"

    handoff = json.loads((output_root / "step7_1_control_handoff_to_a_and_e.json").read_text())
    assert handoff["real_manifest_status"] == "FROZEN_AS_REAL_EVIDENCE"
    assert handoff["blocking_inputs"] == []


def test_direction_record_without_evidence_block_is_honestly_blocked_not_failed(tmp_path):
    record_path = _write_json(tmp_path / "direction_record.json", _direction_record())
    output_root = tmp_path / "out"

    SCRIPT.build_all(output_root, record_path, None, "a", "b")

    audit = json.loads((output_root / "step7_2_direction_control_audit.json").read_text())
    assert audit["evidence_kind"] == "real"
    assert audit["decision"] == "BLOCKED"
    assert audit["result_counts"]["fail"] == 0


def test_complete_real_evidence_with_vectors_reaches_a_genuine_pass(tmp_path):
    record_path = _write_json(
        tmp_path / "direction_record.json",
        _direction_record(
            direction_construction_evidence=_EVIDENCE,
            real_direction_values=[1.0, 0.0, 0.0],
            control_direction_values=[0.0, 1.0, 0.0],
        ),
    )
    output_root = tmp_path / "out"

    SCRIPT.build_all(output_root, record_path, None, "a", "b")

    audit = json.loads((output_root / "step7_2_direction_control_audit.json").read_text())
    assert audit["decision"] == "PASS"
    assert audit["result_counts"]["blocked"] == 0
    assert audit["result_counts"]["fail"] == 0


def test_real_measurements_join_to_the_real_manifest(tmp_path):
    record_path = _write_json(tmp_path / "direction_record.json", _direction_record())
    output_root = tmp_path / "out"
    SCRIPT.build_all(output_root, record_path, None, "a", "b")

    manifest = json.loads((output_root / "step7_1_u4_control_manifest.json").read_text())
    alpha_zero_row = next(row for row in manifest["rows"] if row["control_type"] == "alpha_zero")

    measurements_path = _write_json(
        tmp_path / "measurements.json",
        [
            {
                "clip_id": alpha_zero_row["clip_id"],
                "outcome": "measured",
                "event_id": alpha_zero_row["event_id"],
                "rollout_seed": alpha_zero_row["rollout_seed"],
                "dose_id": alpha_zero_row["dose_id"],
                "control_type": alpha_zero_row["control_type"],
                "target_layer_idx": alpha_zero_row["target_layer_idx"],
                "target_timestep_idx": alpha_zero_row["target_timestep_idx"],
                "direction_id": alpha_zero_row["direction_id"],
                "pair_key": alpha_zero_row["pair_key"],
                "detector_version": "v1",
                "homography_version": "v1",
                "ssim_version": "v1",
                "displacement_blocks": 0.1,
                "masked_ssim": 0.9,
            }
        ],
    )

    output_root_2 = tmp_path / "out2"
    document = SCRIPT.build_all(output_root_2, record_path, measurements_path, "a", "b")
    assert document["measurements_supplied"] is True

    matrix = json.loads((output_root_2 / "step7_3_u4_control_matrix.json").read_text())
    assert matrix["evidence_kind"] == "real"
    assert matrix["measurement_row_count"] == 1
    assert matrix["outcome_counts"].get("measured") == 1


# --------------------------------------------------------------------------
# Fail-closed on incomplete/malformed real input
# --------------------------------------------------------------------------


def test_missing_required_field_in_direction_record_fails_closed(tmp_path):
    broken = _direction_record()
    del broken["target_layer_idx"]
    record_path = _write_json(tmp_path / "direction_record.json", broken)

    with pytest.raises(SCRIPT.U4RealCompletionError, match="target_layer_idx"):
        SCRIPT.load_direction_record(record_path)


def test_measurement_table_must_be_a_json_list(tmp_path):
    path = _write_json(tmp_path / "measurements.json", {"not": "a list"})
    with pytest.raises(SCRIPT.U4RealCompletionError, match="must be a JSON list"):
        SCRIPT.load_measurements(path)


def test_measurement_row_missing_required_field_fails_closed(tmp_path):
    path = _write_json(tmp_path / "measurements.json", [{"clip_id": "x"}])
    with pytest.raises(SCRIPT.U4RealCompletionError, match="missing required field"):
        SCRIPT.load_measurements(path)


def test_invalid_direction_sha256_fails_closed(tmp_path):
    record_path = _write_json(
        tmp_path / "direction_record.json",
        _direction_record(primary_direction={
            "direction_id": "x", "direction_version": "v1", "direction_sha256": "not-a-hash",
        }),
    )
    with pytest.raises(SCRIPT.ControlManifestError):
        SCRIPT.build_all(tmp_path / "out", record_path, None, "a", "b")


# --------------------------------------------------------------------------
# Deterministic regeneration
# --------------------------------------------------------------------------


def test_regeneration_is_byte_identical(tmp_path):
    record_path = _write_json(tmp_path / "direction_record.json", _direction_record())
    first = tmp_path / "first"
    second = tmp_path / "second"
    SCRIPT.build_all(first, record_path, None, "a", "b")
    SCRIPT.build_all(second, record_path, None, "a", "b")

    names = sorted(p.name for p in first.iterdir())
    assert names == sorted(p.name for p in second.iterdir())
    for name in names:
        assert (first / name).read_bytes() == (second / name).read_bytes(), name
