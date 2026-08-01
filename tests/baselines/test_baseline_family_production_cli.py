"""Tests for the frozen Step 4.1 production CLI's pure preparation logic.

These tests exercise ``determine_family_execution_plan`` and
``run_preflight`` directly -- the CLI's ``main()`` is never invoked in
``run`` mode here or anywhere in this preparation pass, matching the
task's explicit "do not execute the production CLI locally" scope. No
baseline is fit, no metric is computed, and no U4 path is touched.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CLI_PATH = ROOT / "scripts" / "run_person_d_step4_1_eight_family_production.py"


def _load_cli_module():
    spec = importlib.util.spec_from_file_location(
        "run_person_d_step4_1_eight_family_production", CLI_PATH
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


cli = _load_cli_module()


def _synthetic_frame_manifest(*, record_count: int = 1695):
    from mineocclude.baselines.baseline_family_input_v0_2 import (
        FROZEN_DIRECT_INPUTS,
        FROZEN_PILOT_IDS,
    )

    per_pilot = record_count // len(FROZEN_PILOT_IDS)
    extra = record_count % len(FROZEN_PILOT_IDS)
    records = []
    for pilot_index, pilot in enumerate(FROZEN_PILOT_IDS):
        count = per_pilot + (1 if pilot_index < extra else 0)
        for frame in range(count):
            records.append(
                {
                    "artifact_id": f"synthetic::{pilot}::{frame}",
                    "payload_sha256": hashlib.sha256(f"{pilot}:{frame}".encode()).hexdigest(),
                    "payload_byte_size": 1032192,
                    "trajectory_id": pilot,
                    "model_frame_idx": frame,
                    "fold_binding": {"fold_idx": pilot_index % 5, "status": "admitted"},
                }
            )
    return {
        "artifact_count": len(records),
        "unique_frame_count": len(records),
        "duplicate_frame_count": 0,
        "missing_frame_count": 0,
        "fold_manifest_sha256": FROZEN_DIRECT_INPUTS["fold_manifest"]["sha256"],
        "target_manifest_sha256": FROZEN_DIRECT_INPUTS["oracle_target"]["sha256"],
        "records": records,
    }


def _valid_document():
    from mineocclude.baselines.baseline_family_input_v0_2 import (
        FROZEN_DIRECT_INPUTS,
        build_baseline_document_v0_2,
    )
    from mineocclude.baselines.interface import make_baseline_row
    from tests.baselines.conftest import build_trajectory_contexts

    ctx = build_trajectory_contexts(
        trajectory_id="layout_00_ep9403", layout_id="layout_00", fold=1,
        visible_positions=(0.0, 1.0), dt=1.0, hidden_taus=(),
    )[0]
    row = make_baseline_row(
        ctx, baseline_name="last_seen", target_name="mu_oracle_blocks",
        prediction=1.0, applicable=True,
    )
    return build_baseline_document_v0_2(
        [row], baseline_id="last_seen_v1", baseline_family="last_seen",
        target_name="mu_oracle_blocks",
        config_hash=FROZEN_DIRECT_INPUTS["analysis_config"]["sha256"],
        input_manifest_hash="e" * 64, fit_manifest_hash="f" * 64,
        default_fit_id="last_seen:mu_oracle_blocks:closed_form",
    )


# --------------------------------------------------------------------------
# Preflight: never fits anything, verifies identities only
# --------------------------------------------------------------------------


def test_preflight_passes_on_a_genuinely_valid_synthetic_frame_manifest(tmp_path):
    manifest_path = tmp_path / "preprocessed_frame_manifest.json"
    manifest_path.write_text(json.dumps(_synthetic_frame_manifest()), encoding="utf-8")

    report = cli.run_preflight(
        frame_manifest_path=manifest_path,
        frame_manifest_byte_size=manifest_path.stat().st_size,
    )
    assert report["status"] == "PREFLIGHT_PASSED"
    assert report["baseline_execution_performed"] is False
    assert report["u4_output_inspected"] is False


def test_preflight_fails_closed_on_a_tampered_frame_manifest(tmp_path):
    manifest = _synthetic_frame_manifest()
    manifest["duplicate_frame_count"] = 1  # tamper: claims a duplicate exists
    manifest_path = tmp_path / "preprocessed_frame_manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(cli.ProductionRunnerError, match="summary checks failed"):
        cli.run_preflight(
            frame_manifest_path=manifest_path,
            frame_manifest_byte_size=manifest_path.stat().st_size,
        )


def test_main_never_reaches_execution_without_a_frame_manifest(tmp_path, monkeypatch, capsys):
    missing_path = tmp_path / "does_not_exist.json"
    monkeypatch.setattr(
        sys, "argv",
        [
            "run_person_d_step4_1_eight_family_production.py",
            "preflight",
            "--frame-manifest-path", str(missing_path),
            "--output-root", str(tmp_path / "out"),
        ],
    )
    exit_code = cli.main()
    assert exit_code == 1
    assert "FAIL-CLOSED" in capsys.readouterr().err


# --------------------------------------------------------------------------
# Resume: does not duplicate already-verified family outputs
# --------------------------------------------------------------------------


def test_empty_state_marks_every_family_must_run(tmp_path):
    from mineocclude.baselines.baseline_family_input_v0_2 import (
        FROZEN_BASELINE_FAMILY_IDS,
    )

    plan = cli.determine_family_execution_plan({"families": {}}, output_root=tmp_path)
    assert plan == {family: "must_run" for family in FROZEN_BASELINE_FAMILY_IDS}


def test_a_completed_and_still_valid_family_output_is_skipped(tmp_path):
    document = _valid_document()
    output_path = tmp_path / "last_seen_mu_oracle_blocks.json"
    output_path.write_text(json.dumps(document), encoding="utf-8")

    state = {
        "families": {
            "last_seen": {"status": "completed", "output_path": output_path.name}
        }
    }
    plan = cli.determine_family_execution_plan(state, output_root=tmp_path)
    assert plan["last_seen"] == "skip_already_verified"
    assert plan["constant_velocity"] == "must_run"


def test_a_completed_family_whose_output_file_is_missing_must_rerun(tmp_path):
    state = {
        "families": {
            "last_seen": {"status": "completed", "output_path": "does_not_exist.json"}
        }
    }
    plan = cli.determine_family_execution_plan(state, output_root=tmp_path)
    assert plan["last_seen"] == "must_run"


def test_a_completed_family_whose_output_no_longer_validates_must_rerun(tmp_path):
    document = _valid_document()
    document["fold_manifest_hash"] = "0" * 64  # corrupted since it was recorded
    output_path = tmp_path / "last_seen_mu_oracle_blocks.json"
    output_path.write_text(json.dumps(document), encoding="utf-8")

    state = {
        "families": {
            "last_seen": {"status": "completed", "output_path": output_path.name}
        }
    }
    plan = cli.determine_family_execution_plan(state, output_root=tmp_path)
    assert plan["last_seen"] == "must_run"


def test_a_failed_family_must_rerun_not_skip(tmp_path):
    state = {"families": {"last_seen": {"status": "failed"}}}
    plan = cli.determine_family_execution_plan(state, output_root=tmp_path)
    assert plan["last_seen"] == "must_run"


def test_resume_never_re_marks_an_earlier_valid_family_as_must_run_when_a_later_one_is_pending(tmp_path):
    document = _valid_document()
    output_path = tmp_path / "last_seen_mu_oracle_blocks.json"
    output_path.write_text(json.dumps(document), encoding="utf-8")

    state = {
        "families": {
            "last_seen": {"status": "completed", "output_path": output_path.name},
            "constant_velocity": {"status": "failed"},
        }
    }
    plan = cli.determine_family_execution_plan(state, output_root=tmp_path)
    assert plan["last_seen"] == "skip_already_verified"
    assert plan["constant_velocity"] == "must_run"
    # Every family after a failed one is still independently planned,
    # never assumed blocked by an earlier failure.
    assert plan["time_only"] == "must_run"


def test_run_state_round_trips_through_save_and_load(tmp_path):
    state = {"schema_version": "1.0", "families": {"last_seen": {"status": "completed"}}}
    cli.save_run_state(tmp_path, state)
    loaded = cli.load_run_state(tmp_path)
    assert loaded == state


def test_load_run_state_on_a_fresh_output_root_is_empty(tmp_path):
    state = cli.load_run_state(tmp_path / "never_created")
    assert state == {"schema_version": "1.0", "families": {}}


# --------------------------------------------------------------------------
# No baseline execution / no U4 access anywhere in this module
# --------------------------------------------------------------------------


def test_run_mode_never_silently_executes_a_baseline(tmp_path):
    manifest_path = tmp_path / "preprocessed_frame_manifest.json"
    manifest_path.write_text(json.dumps(_synthetic_frame_manifest()), encoding="utf-8")
    output_root = tmp_path / "out"

    import sys as _sys
    old_argv = _sys.argv
    try:
        _sys.argv = [
            "run_person_d_step4_1_eight_family_production.py",
            "run",
            "--frame-manifest-path", str(manifest_path),
            "--output-root", str(output_root),
        ]
        with pytest.raises(cli.ProductionRunnerError, match="real execution is not implemented"):
            cli.main()
    finally:
        _sys.argv = old_argv


def test_no_u4_import_in_the_cli_module():
    source = CLI_PATH.read_text(encoding="utf-8")
    import_lines = [
        line for line in source.splitlines()
        if line.strip().startswith(("import ", "from "))
    ]
    assert not any("u4" in line.lower() for line in import_lines)
