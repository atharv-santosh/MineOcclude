"""Tests for the repaired Step 4.1 production CLI's preparation logic.

Covers all five repaired defects: (1) production run mode now has real
fit/export/persist logic (``run_production``/``fit_and_export_family``),
tested directly, never through ``main()``'s ``run`` mode, which the CLI
itself cannot safely wire to real data on this machine; (2) the
exporter commit binding points at the real implementation commit, not
the historical branch-starting authority; (3) branch/HEAD/ancestor/
clean-worktree authorization is required and fails closed; (4) the
frame manifest's raw bytes are verified before its contents are
trusted; (5) every frame payload is verified against the manifest by
recomputing its actual on-disk size and SHA-256.

No baseline is fit against real data, no metric is computed, and no
U4 path is touched anywhere in this file.
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

from mineocclude.baselines.baseline_family_input_v0_2 import (
    FROZEN_BASELINE_FAMILY_IDS,
    FROZEN_DIRECT_INPUTS,
    FROZEN_PILOT_IDS,
)
from mineocclude.baselines.frame_handoff_v0_2 import (
    REQUIRED_PAYLOAD_COLOR_ORDER,
    REQUIRED_PAYLOAD_DTYPE,
    REQUIRED_PAYLOAD_FORMAT,
    REQUIRED_PAYLOAD_LAYOUT,
    REQUIRED_PAYLOAD_SHAPE,
)


def _synthetic_frame_manifest_and_payloads(tmp_path: Path, *, record_count: int = 1695):
    frame_root = tmp_path / "frames"
    per_pilot = record_count // len(FROZEN_PILOT_IDS)
    extra = record_count % len(FROZEN_PILOT_IDS)
    records = []
    for pilot_index, pilot in enumerate(FROZEN_PILOT_IDS):
        count = per_pilot + (1 if pilot_index < extra else 0)
        for frame in range(count):
            payload = bytes([frame % 256]) * 100
            relative_path = f"{pilot}/{frame:06d}.f32le"
            path = frame_root / relative_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
            records.append(
                {
                    "artifact_id": f"{pilot}::{frame}",
                    "trajectory_id": pilot,
                    "model_frame_idx": frame,
                    "payload_sha256": hashlib.sha256(payload).hexdigest(),
                    "payload_byte_size": len(payload),
                    "output_relative_path": relative_path,
                    "global_frame_identity": f"{pilot}:{frame}",
                    "target_binding": {"target_id": f"{pilot}:{frame}:regime_a_primary_v1"},
                    "fold_binding": {"fold_idx": pilot_index % 5, "status": "admitted"},
                    "dtype": REQUIRED_PAYLOAD_DTYPE,
                    "layout": REQUIRED_PAYLOAD_LAYOUT,
                    "color_order": REQUIRED_PAYLOAD_COLOR_ORDER,
                    "payload_format": REQUIRED_PAYLOAD_FORMAT,
                    "shape": list(REQUIRED_PAYLOAD_SHAPE),
                }
            )
    manifest = {
        "artifact_count": len(records),
        "unique_frame_count": len(records),
        "duplicate_frame_count": 0,
        "missing_frame_count": 0,
        "fold_manifest_sha256": FROZEN_DIRECT_INPUTS["fold_manifest"]["sha256"],
        "target_manifest_sha256": FROZEN_DIRECT_INPUTS["oracle_target"]["sha256"],
        "records": records,
    }
    return manifest, frame_root


def _write_manifest_and_patch_expected_hash(tmp_path: Path, manifest: dict, monkeypatch) -> Path:
    manifest_bytes = json.dumps(manifest).encode("utf-8")
    manifest_path = tmp_path / "preprocessed_frame_manifest.json"
    manifest_path.write_bytes(manifest_bytes)
    real_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
    monkeypatch.setattr(cli, "PERSON_A_FRAME_MANIFEST_SHA256", real_sha256, raising=False)

    import mineocclude.baselines.frame_handoff_v0_2 as frame_handoff_module

    monkeypatch.setattr(frame_handoff_module, "PERSON_A_FRAME_MANIFEST_SHA256", real_sha256)
    return manifest_path


def _valid_document():
    from mineocclude.baselines.baseline_family_input_v0_2 import (
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
# Defect 2: exporter commit binding no longer points at the historical authority
# --------------------------------------------------------------------------


def test_exporter_commit_is_the_real_implementation_not_the_historical_authority():
    assert cli.PERSON_D_EXPORTER_IMPLEMENTATION_COMMIT == "fd9302e5d218193211f2f96986ca32dc1a365e66"
    old_historical_authority = "853e0acadf050a0b1f318b399b524e57379d03bf"
    assert cli.PERSON_D_EXPORTER_IMPLEMENTATION_COMMIT != old_historical_authority


def test_person_b_schema_correction_commit_is_bound():
    assert cli.PERSON_B_V0_2_SCHEMA_CORRECTION_COMMIT == "4e0e0f49d4642cf069de8c66c3a8fee47806c4b0"


# --------------------------------------------------------------------------
# Defect 3: branch / HEAD / ancestor / clean-worktree authorization
# --------------------------------------------------------------------------


def test_authorization_passes_when_every_fact_is_correct():
    errors = cli.verify_branch_and_authorization(
        branch="role/person-d-baselines",
        head="abc123",
        worktree_dirty=False,
        exporter_commit_is_ancestor=True,
        authorized_runner_commit="abc123",
    )
    assert errors == ()


def test_authorization_rejects_the_wrong_branch():
    errors = cli.verify_branch_and_authorization(
        branch="role/person-b-analysis",
        head="abc123",
        worktree_dirty=False,
        exporter_commit_is_ancestor=True,
        authorized_runner_commit="abc123",
    )
    assert any("wrong_branch" in error for error in errors)


def test_authorization_rejects_a_dirty_worktree():
    errors = cli.verify_branch_and_authorization(
        branch="role/person-d-baselines",
        head="abc123",
        worktree_dirty=True,
        exporter_commit_is_ancestor=True,
        authorized_runner_commit="abc123",
    )
    assert "dirty_worktree" in errors


def test_authorization_rejects_a_missing_exporter_ancestor():
    errors = cli.verify_branch_and_authorization(
        branch="role/person-d-baselines",
        head="abc123",
        worktree_dirty=False,
        exporter_commit_is_ancestor=False,
        authorized_runner_commit="abc123",
    )
    assert "exporter_commit_not_ancestor" in errors


def test_authorization_rejects_an_unrecorded_authorization():
    errors = cli.verify_branch_and_authorization(
        branch="role/person-d-baselines",
        head="abc123",
        worktree_dirty=False,
        exporter_commit_is_ancestor=True,
        authorized_runner_commit=None,
    )
    assert "no_authorized_runner_commit_recorded" in errors


def test_authorization_rejects_a_head_that_does_not_match_the_authorized_commit():
    errors = cli.verify_branch_and_authorization(
        branch="role/person-d-baselines",
        head="current-head",
        worktree_dirty=False,
        exporter_commit_is_ancestor=True,
        authorized_runner_commit="some-other-authorized-commit",
    )
    assert any("head_not_authorized" in error for error in errors)


def test_authorization_rejects_the_old_historical_starting_authority_as_head():
    # The old starting authority (853e0a...) must never be mistaken for
    # the authorized implementation binding.
    old_historical_authority = "853e0acadf050a0b1f318b399b524e57379d03bf"
    errors = cli.verify_branch_and_authorization(
        branch="role/person-d-baselines",
        head=old_historical_authority,
        worktree_dirty=False,
        exporter_commit_is_ancestor=True,
        authorized_runner_commit=cli.PERSON_D_EXPORTER_IMPLEMENTATION_COMMIT,
    )
    assert any("head_not_authorized" in error for error in errors)


def test_load_authorized_runner_commit_returns_none_when_file_absent(tmp_path):
    assert cli.load_authorized_runner_commit(tmp_path / "does_not_exist.json") is None


def test_load_authorized_runner_commit_reads_the_recorded_hash(tmp_path):
    path = tmp_path / "authorized_runner_commit.json"
    path.write_text(json.dumps({"authorized_runner_commit": "deadbeef"}), encoding="utf-8")
    assert cli.load_authorized_runner_commit(path) == "deadbeef"


def test_resolve_git_facts_against_the_real_repository_reports_the_real_branch():
    facts = cli.resolve_git_facts(cli.ROOT)
    assert facts["branch"] == "role/person-d-baselines"
    assert isinstance(facts["head"], str) and len(facts["head"]) == 40
    assert facts["exporter_commit_is_ancestor"] is True


def test_main_fails_closed_when_no_authorization_record_exists(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "AUTHORIZATION_RECORD_PATH", tmp_path / "does_not_exist.json")
    monkeypatch.setattr(
        sys, "argv",
        [
            "run_person_d_step4_1_eight_family_production.py",
            "preflight",
            "--frame-manifest-path", str(tmp_path / "missing.json"),
        ],
    )
    exit_code = cli.main()
    assert exit_code == 1
    assert "authorization checks failed" in capsys.readouterr().err


# --------------------------------------------------------------------------
# Defect 4: frame manifest raw-byte verification
# --------------------------------------------------------------------------


def test_preflight_verifies_raw_bytes_before_trusting_manifest_contents(tmp_path, monkeypatch):
    manifest, _ = _synthetic_frame_manifest_and_payloads(tmp_path)
    manifest_path = _write_manifest_and_patch_expected_hash(tmp_path, manifest, monkeypatch)
    report = cli.run_preflight(frame_manifest_path=manifest_path)
    assert report["status"] == "PREFLIGHT_PASSED"


def test_preflight_fails_closed_on_a_raw_byte_tampered_manifest(tmp_path, monkeypatch):
    manifest, _ = _synthetic_frame_manifest_and_payloads(tmp_path)
    manifest_path = _write_manifest_and_patch_expected_hash(tmp_path, manifest, monkeypatch)
    # Append a byte after the expected hash was recorded: raw bytes no
    # longer match, even though the JSON still parses.
    with manifest_path.open("ab") as handle:
        handle.write(b" ")
    with pytest.raises(cli.ProductionRunnerError, match="raw-byte checks failed"):
        cli.run_preflight(frame_manifest_path=manifest_path)


def test_preflight_fails_closed_on_a_tampered_summary_count(tmp_path, monkeypatch):
    manifest, _ = _synthetic_frame_manifest_and_payloads(tmp_path)
    manifest["duplicate_frame_count"] = 1
    manifest_path = _write_manifest_and_patch_expected_hash(tmp_path, manifest, monkeypatch)
    with pytest.raises(cli.ProductionRunnerError, match="summary checks failed"):
        cli.run_preflight(frame_manifest_path=manifest_path)


# --------------------------------------------------------------------------
# Defect 5: every one of the 1,695 frame payloads verified on disk
# --------------------------------------------------------------------------


def test_preflight_verifies_every_frame_payload_on_disk(tmp_path, monkeypatch):
    manifest, frame_root = _synthetic_frame_manifest_and_payloads(tmp_path)
    manifest_path = _write_manifest_and_patch_expected_hash(tmp_path, manifest, monkeypatch)
    report = cli.run_preflight(
        frame_manifest_path=manifest_path, frame_root=frame_root, verify_payloads=True
    )
    assert report["status"] == "PREFLIGHT_PASSED"
    assert report["frame_payload_verification_performed"] is True


def test_preflight_fails_closed_on_a_missing_frame_payload_file(tmp_path, monkeypatch):
    manifest, frame_root = _synthetic_frame_manifest_and_payloads(tmp_path)
    manifest_path = _write_manifest_and_patch_expected_hash(tmp_path, manifest, monkeypatch)
    # Delete one real payload file the manifest still claims exists.
    first_relative_path = manifest["records"][0]["output_relative_path"]
    (frame_root / first_relative_path).unlink()
    with pytest.raises(cli.ProductionRunnerError, match="frame payload verification failed"):
        cli.run_preflight(
            frame_manifest_path=manifest_path, frame_root=frame_root, verify_payloads=True
        )


def test_preflight_fails_closed_on_a_changed_payload_byte_size(tmp_path, monkeypatch):
    manifest, frame_root = _synthetic_frame_manifest_and_payloads(tmp_path)
    manifest_path = _write_manifest_and_patch_expected_hash(tmp_path, manifest, monkeypatch)
    first_relative_path = manifest["records"][0]["output_relative_path"]
    (frame_root / first_relative_path).write_bytes(b"short")
    with pytest.raises(cli.ProductionRunnerError, match="frame payload verification failed"):
        cli.run_preflight(
            frame_manifest_path=manifest_path, frame_root=frame_root, verify_payloads=True
        )


def test_preflight_fails_closed_on_a_changed_payload_sha256(tmp_path, monkeypatch):
    manifest, frame_root = _synthetic_frame_manifest_and_payloads(tmp_path)
    manifest_path = _write_manifest_and_patch_expected_hash(tmp_path, manifest, monkeypatch)
    first_relative_path = manifest["records"][0]["output_relative_path"]
    original_size = manifest["records"][0]["payload_byte_size"]
    (frame_root / first_relative_path).write_bytes(b"x" * original_size)
    with pytest.raises(cli.ProductionRunnerError, match="frame payload verification failed"):
        cli.run_preflight(
            frame_manifest_path=manifest_path, frame_root=frame_root, verify_payloads=True
        )


def test_all_1695_manifest_rows_are_covered_by_payload_verification(tmp_path):
    from mineocclude.baselines.frame_handoff_v0_2 import verify_frame_payloads_on_disk

    manifest, frame_root = _synthetic_frame_manifest_and_payloads(tmp_path, record_count=1695)
    result = verify_frame_payloads_on_disk(manifest, frame_root=frame_root)
    assert result.expected_frame_count == 1695
    assert result.actual_frame_count == 1695
    assert result.all_clear


def test_duplicate_frame_identity_on_disk_is_detected(tmp_path):
    from mineocclude.baselines.frame_handoff_v0_2 import verify_frame_payloads_on_disk

    manifest, frame_root = _synthetic_frame_manifest_and_payloads(tmp_path, record_count=10)
    manifest["records"].append(dict(manifest["records"][0]))
    result = verify_frame_payloads_on_disk(manifest, frame_root=frame_root)
    assert result.duplicate_frame_count == 1


# --------------------------------------------------------------------------
# Defect 1: production run mode has real fit/export/persist logic
# --------------------------------------------------------------------------


def test_run_production_actually_fits_and_persists_a_family(tmp_path):
    from tests.baselines.conftest import build_trajectory_contexts

    layout_folds = {"layout_00": 1, "layout_01": 2, "layout_02": 4, "layout_03": 0, "layout_04": 3}
    pilots = {
        "layout_00_ep9403": ("layout_00", (0.0, 1.0, 2.0)),
        "layout_00_ep9441": ("layout_00", (0.0, 2.0, 4.0)),
        "layout_01_ep9405": ("layout_01", (0.0, 1.5, 3.0)),
        "layout_02_ep9407": ("layout_02", (0.0, 0.5, 1.0)),
        "layout_03_ep9404": ("layout_03", (0.0, 1.0, 0.5)),
        "layout_04_ep9406": ("layout_04", (0.0, 2.0, 1.0)),
    }
    contexts = []
    mu_oracle_by_key = {}
    log_sigma_oracle_by_key = {}
    visible_positions_by_trajectory = {}
    pixel_features_by_key = {}
    for trajectory_id, (layout_id, positions) in pilots.items():
        ctx_list = build_trajectory_contexts(
            trajectory_id=trajectory_id, layout_id=layout_id, fold=layout_folds[layout_id],
            visible_positions=positions, dt=1.0, hidden_taus=(1.0,), duration_seconds=2.0,
            q_scripted=0.02,
        )
        contexts.extend(ctx_list)
        visible_positions_by_trajectory[trajectory_id] = positions
        last_seen = ctx_list[-1].last_seen_position_blocks
        velocity = ctx_list[-1].last_seen_velocity_blocks_per_s
        for ctx in ctx_list:
            key = (ctx.trajectory_id, ctx.model_frame_idx)
            mu_oracle_by_key[key] = last_seen + velocity * ctx.tau_seconds
            log_sigma_oracle_by_key[key] = 0.1 * ctx.tau_seconds + 0.01
            pixel_features_by_key[key] = [float(ctx.model_frame_idx), 1.0]

    from mineocclude.baselines.frame_handoff_v0_2 import (
        build_frame_manifest_direct_input_reference,
    )

    output_root = tmp_path / "out"
    state = cli.run_production(
        contexts=contexts,
        mu_oracle_by_key=mu_oracle_by_key,
        log_sigma_oracle_by_key=log_sigma_oracle_by_key,
        visible_positions_by_trajectory=visible_positions_by_trajectory,
        pixel_features_by_key=pixel_features_by_key,
        config_hash=FROZEN_DIRECT_INPUTS["analysis_config"]["sha256"],
        input_manifest_hash="e" * 64,
        fit_manifest_hash="f" * 64,
        preprocessed_frame_manifest_reference=build_frame_manifest_direct_input_reference(
            byte_size=6460547
        ),
        output_root=output_root,
    )
    for family_id in FROZEN_BASELINE_FAMILY_IDS:
        assert state["families"][family_id]["status"] == "completed", family_id
    # Every produced document is real, on disk, and independently valid.
    from mineocclude.baselines.baseline_family_input_v0_2 import (
        validate_baseline_document_v0_2,
    )

    produced_files = list(output_root.glob("*.json"))
    assert any("last_seen" in path.name for path in produced_files)
    for path in produced_files:
        if path.name == "run_state.json":
            continue
        document = json.loads(path.read_text(encoding="utf-8"))
        assert validate_baseline_document_v0_2(document) == ()


def test_run_production_is_resume_aware_and_does_not_refit_a_completed_family(tmp_path):
    from tests.baselines.conftest import build_trajectory_contexts

    layout_folds = {"layout_00": 1, "layout_01": 2, "layout_02": 4, "layout_03": 0, "layout_04": 3}
    pilots = {
        "layout_00_ep9403": ("layout_00", (0.0, 1.0, 2.0)),
        "layout_00_ep9441": ("layout_00", (0.0, 2.0, 4.0)),
        "layout_01_ep9405": ("layout_01", (0.0, 1.5, 3.0)),
        "layout_02_ep9407": ("layout_02", (0.0, 0.5, 1.0)),
        "layout_03_ep9404": ("layout_03", (0.0, 1.0, 0.5)),
        "layout_04_ep9406": ("layout_04", (0.0, 2.0, 1.0)),
    }
    contexts, mu_oracle_by_key, log_sigma_oracle_by_key = [], {}, {}
    visible_positions_by_trajectory, pixel_features_by_key = {}, {}
    for trajectory_id, (layout_id, positions) in pilots.items():
        ctx_list = build_trajectory_contexts(
            trajectory_id=trajectory_id, layout_id=layout_id, fold=layout_folds[layout_id],
            visible_positions=positions, dt=1.0, hidden_taus=(1.0,), duration_seconds=2.0,
            q_scripted=0.02,
        )
        contexts.extend(ctx_list)
        visible_positions_by_trajectory[trajectory_id] = positions
        last_seen = ctx_list[-1].last_seen_position_blocks
        velocity = ctx_list[-1].last_seen_velocity_blocks_per_s
        for ctx in ctx_list:
            key = (ctx.trajectory_id, ctx.model_frame_idx)
            mu_oracle_by_key[key] = last_seen + velocity * ctx.tau_seconds
            log_sigma_oracle_by_key[key] = 0.1 * ctx.tau_seconds + 0.01
            pixel_features_by_key[key] = [float(ctx.model_frame_idx), 1.0]

    from mineocclude.baselines.frame_handoff_v0_2 import (
        build_frame_manifest_direct_input_reference,
    )

    output_root = tmp_path / "out"
    kwargs = {
        "contexts": contexts,
        "mu_oracle_by_key": mu_oracle_by_key,
        "log_sigma_oracle_by_key": log_sigma_oracle_by_key,
        "visible_positions_by_trajectory": visible_positions_by_trajectory,
        "pixel_features_by_key": pixel_features_by_key,
        "config_hash": FROZEN_DIRECT_INPUTS["analysis_config"]["sha256"],
        "input_manifest_hash": "e" * 64,
        "fit_manifest_hash": "f" * 64,
        "preprocessed_frame_manifest_reference": build_frame_manifest_direct_input_reference(
            byte_size=6460547
        ),
        "output_root": output_root,
    }
    cli.run_production(**kwargs)
    first_last_seen_output = output_root / "last_seen__mu_oracle_blocks.json"
    first_mtime = first_last_seen_output.stat().st_mtime_ns

    plan_before_second_run = cli.determine_family_execution_plan(
        cli.load_run_state(output_root), output_root=output_root
    )
    assert plan_before_second_run["last_seen"] == "skip_already_verified"

    cli.run_production(**kwargs)
    assert first_last_seen_output.stat().st_mtime_ns == first_mtime, (
        "resume must not rewrite an already-verified family output"
    )


def test_main_never_reaches_run_production_without_authorization(tmp_path, monkeypatch, capsys):
    manifest, _ = _synthetic_frame_manifest_and_payloads(tmp_path, record_count=10)
    manifest_path = tmp_path / "preprocessed_frame_manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(cli, "AUTHORIZATION_RECORD_PATH", tmp_path / "does_not_exist.json")
    monkeypatch.setattr(
        sys, "argv",
        [
            "run_person_d_step4_1_eight_family_production.py",
            "run",
            "--frame-manifest-path", str(manifest_path),
            "--output-root", str(tmp_path / "out"),
        ],
    )
    exit_code = cli.main()
    assert exit_code == 1
    assert "authorization checks failed" in capsys.readouterr().err
    assert not (tmp_path / "out").exists()


# --------------------------------------------------------------------------
# Resume planning (unchanged from the prior preparation, re-confirmed here)
# --------------------------------------------------------------------------


def test_empty_state_marks_every_family_must_run(tmp_path):
    plan = cli.determine_family_execution_plan({"families": {}}, output_root=tmp_path)
    assert plan == {family: "must_run" for family in FROZEN_BASELINE_FAMILY_IDS}


def test_a_completed_and_still_valid_family_output_is_skipped(tmp_path):
    document = _valid_document()
    output_path = tmp_path / "last_seen_mu_oracle_blocks.json"
    output_path.write_text(json.dumps(document), encoding="utf-8")
    state = {"families": {"last_seen": {"status": "completed", "output_path": output_path.name}}}
    plan = cli.determine_family_execution_plan(state, output_root=tmp_path)
    assert plan["last_seen"] == "skip_already_verified"
    assert plan["constant_velocity"] == "must_run"


def test_a_completed_family_whose_output_file_is_missing_must_rerun(tmp_path):
    state = {"families": {"last_seen": {"status": "completed", "output_path": "does_not_exist.json"}}}
    plan = cli.determine_family_execution_plan(state, output_root=tmp_path)
    assert plan["last_seen"] == "must_run"


def test_a_completed_family_whose_output_no_longer_validates_must_rerun(tmp_path):
    document = _valid_document()
    document["fold_manifest_hash"] = "0" * 64
    output_path = tmp_path / "last_seen_mu_oracle_blocks.json"
    output_path.write_text(json.dumps(document), encoding="utf-8")
    state = {"families": {"last_seen": {"status": "completed", "output_path": output_path.name}}}
    plan = cli.determine_family_execution_plan(state, output_root=tmp_path)
    assert plan["last_seen"] == "must_run"


def test_a_failed_family_must_rerun_not_skip(tmp_path):
    state = {"families": {"last_seen": {"status": "failed"}}}
    plan = cli.determine_family_execution_plan(state, output_root=tmp_path)
    assert plan["last_seen"] == "must_run"


def test_run_state_round_trips_through_save_and_load(tmp_path):
    state = {"schema_version": "1.0", "families": {"last_seen": {"status": "completed"}}}
    cli.save_run_state(tmp_path, state)
    assert cli.load_run_state(tmp_path) == state


def test_load_run_state_on_a_fresh_output_root_is_empty(tmp_path):
    assert cli.load_run_state(tmp_path / "never_created") == {"schema_version": "1.0", "families": {}}


# --------------------------------------------------------------------------
# Historical behavior intact; no U4 import
# --------------------------------------------------------------------------


def test_historical_preflight_still_works_without_payload_verification(tmp_path, monkeypatch):
    manifest, _ = _synthetic_frame_manifest_and_payloads(tmp_path)
    manifest_path = _write_manifest_and_patch_expected_hash(tmp_path, manifest, monkeypatch)
    report = cli.run_preflight(frame_manifest_path=manifest_path)
    assert report["status"] == "PREFLIGHT_PASSED"
    assert report["frame_payload_verification_performed"] is False


def test_no_u4_import_in_the_cli_module():
    source = CLI_PATH.read_text(encoding="utf-8")
    import_lines = [
        line for line in source.splitlines()
        if line.strip().startswith(("import ", "from "))
    ]
    assert not any("u4" in line.lower() for line in import_lines)
