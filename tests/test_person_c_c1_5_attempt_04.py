from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from mineocclude.data.noise_schedule import generate_noise_schedule, load_schedule, serialize_schedule
from scripts.person_c.ingest_c1_5_attempt_04_runtime import (
    REQUIRED_ATTESTATION_FIELDS,
    validate_attestation,
    validate_retry_logs,
)
from scripts.person_c.prepare_c1_5_attempt_04 import (
    ATTESTATION_TEMPLATE,
    DOC_DIR,
    FAILURE_CLASSIFICATION,
    FINALIZATION_SCRIPT,
    OBSERVATION_WINDOW_SECONDS,
    RESERVED_SECOND_EPISODE_ID,
    RETRY_ATTESTATION,
    RETRY_CLIENT_OUTPUT,
    RETRY_EPISODE_ID,
    RETRY_INGESTED,
    RETRY_RECEIPT,
    RETRY_REPO_SCHEDULE,
    RETRY_RUNTIME_SCHEDULE,
    RETRY_SCREENSHOT,
    RETRY_SEED,
    RETRY_SERVER_OUTPUT,
    RETRY_WARMUP_TICKS,
    assert_candidate_unused,
)


def _valid_logs(
    *,
    screenshot_second: int = 13,
    include_abort: bool = True,
    include_recording: bool = False,
) -> tuple[list[str], list[str]]:
    server = [
        "[12:00:00] [Server thread/INFO]: Warmup delay set to 12000 ticks (600.0s)",
        "[12:00:01] [Server thread/INFO]: [MineOcclude] loaded immutable noise schedule (20 draws) from .\\mineocclude_schedules\\episode_11505.jsonl",
        "[12:00:01] [Server thread/INFO]: [MineOcclude] episode 11505 armed (layout=layout_01, 12000 warmup + 20 record ticks, v=0.0, q=0.0, seed=202608031505)",
        "[12:00:11] [Server thread/INFO]: target status: valid=true required=true count=1 episode=11505 lifecycle=READY problems=NONE",
        "[12:00:12] [Server thread/INFO]: [MineOcclude/observation] wrote read-only geometry receipt .\\mineocclude_observations\\c1_5_first_operator_attempt_04_layout_01.json",
    ]
    if include_recording:
        server.append(
            "[12:00:14] [Server thread/INFO]: [MineOcclude] episode 11505 recording started"
        )
    if include_abort:
        server.append(
            "[12:00:15] [Server thread/INFO]: [MineOcclude] episode 11505 aborted during warmup"
        )
    server.append("[12:00:16] [Server thread/INFO]: Stopping server")
    client = [
        "[11:59:50] [main/INFO]: Setting user: test_account",
        "[11:59:55] [main/INFO]: Connecting to 127.0.0.1, 25565",
        f"[12:00:{screenshot_second:02d}] [main/INFO]: [CHAT] Saved screenshot as 2026-08-04_12.00.{screenshot_second:02d}.png",
        "[12:00:17] [main/INFO]: Stopping!",
    ]
    return server, client


def _completed_attestation() -> dict[str, object]:
    value = dict(ATTESTATION_TEMPLATE)
    value.update({
        "template": False,
        "operator_id": "operator",
        "utc_start": "2026-08-04T16:00:00+00:00",
        "utc_end": "2026-08-04T16:01:00+00:00",
        "preparation_commit": "1" * 40,
        "observed_account_name": "test_account",
        "fresh_runtime_session": True,
        "all_runbook_steps_performed_without_memory_or_prior_artifact_reuse": True,
        "targetstatus_passed_after_ten_seconds": True,
        "observegeometry_completed_during_warmup_before_recording": True,
        "receipt_write_confirmed_before_f2": True,
        "f2_pressed_immediately_after_receipt_confirmation": True,
        "mineocclude_stop_issued_immediately_after_f2": True,
        "screenshot_from_same_session": True,
        "server_stopped_cleanly": True,
        "notes": "validated",
    })
    return value


def test_retry_identity_skips_reserved_second_operator_and_uses_ten_minutes() -> None:
    assert RESERVED_SECOND_EPISODE_ID == 11502
    assert RETRY_EPISODE_ID == 11505
    assert RETRY_SEED == 202608031505
    assert RETRY_WARMUP_TICKS == 12000
    assert OBSERVATION_WINDOW_SECONDS == 600
    assert FAILURE_CLASSIFICATION == (
        "GEOMETRY_RECEIPT_VALID_BUT_SCREENSHOT_AND_ABORT_OCCURRED_AFTER_RECORDING_STARTED"
    )


def test_retry_schedule_is_deterministic_and_loadable(tmp_path: Path) -> None:
    # These historical schedule bytes were generated under the recorded NumPy
    # 2.4.3 environment.  Validate the frozen bytes and manifest identity; do
    # not regenerate them under the qualified NumPy 1.26.4 runner.
    data = RETRY_REPO_SCHEDULE.read_bytes()
    loaded = load_schedule(str(RETRY_REPO_SCHEDULE))
    assert loaded.seed == RETRY_SEED
    assert loaded.n_draws == 20
    assert loaded.q == 0.0
    assert json.loads(data.splitlines()[0])["numpy_version"] == "2.4.3"


def test_full_attempt_specific_attestation_contract() -> None:
    assert set(ATTESTATION_TEMPLATE) == REQUIRED_ATTESTATION_FIELDS
    assert ATTESTATION_TEMPLATE["attempt"] == 4
    assert ATTESTATION_TEMPLATE["independent_from_first_operator"] is False
    validate_attestation(_completed_attestation())
    for field in (
        "targetstatus_passed_after_ten_seconds",
        "observegeometry_completed_during_warmup_before_recording",
        "receipt_write_confirmed_before_f2",
        "f2_pressed_immediately_after_receipt_confirmation",
        "mineocclude_stop_issued_immediately_after_f2",
    ):
        broken = _completed_attestation()
        broken[field] = None
        with pytest.raises(ValueError, match="operator attestation missing"):
            validate_attestation(broken)


def test_chronology_accepts_receipt_then_screenshot_then_warmup_abort() -> None:
    server, client = _valid_logs()
    result = validate_retry_logs(server, client)
    assert result["armed_to_status_seconds"] == 10
    assert result["armed_to_observation_seconds"] == 11
    assert result["armed_to_screenshot_seconds"] == 12
    assert result["armed_to_abort_seconds"] == 14
    assert result["episode_aborted_during_warmup"] is True
    assert result["recording_started"] is False


def test_chronology_rejects_recording_before_abort() -> None:
    server, client = _valid_logs(include_recording=True)
    with pytest.raises(ValueError, match="recording started before warmup abort"):
        validate_retry_logs(server, client)


def test_chronology_rejects_absent_abort_log() -> None:
    server, client = _valid_logs(include_abort=False)
    with pytest.raises(ValueError, match="episode 11505 aborted during warmup"):
        validate_retry_logs(server, client)


def test_chronology_rejects_screenshot_predating_receipt() -> None:
    server, client = _valid_logs(screenshot_second=11)
    with pytest.raises(ValueError, match="receipt < F2 screenshot"):
        validate_retry_logs(server, client)


def test_generated_package_binds_schedule_warmup_and_create_only_guards() -> None:
    schedule_data = RETRY_REPO_SCHEDULE.read_bytes()
    manifest = json.loads((DOC_DIR / "attempt_04_manifest.json").read_text())
    failure = (DOC_DIR / "attempt_03_failure_record.json").read_bytes()
    assert manifest["retry"]["episode_id"] == RETRY_EPISODE_ID
    assert manifest["retry"]["seed"] == RETRY_SEED
    assert manifest["retry"]["warmup_ticks"] == 12000
    assert manifest["retry"]["observation_window_seconds"] == 600
    assert manifest["retry"]["ordered_start_commands"][-2:] == [
        "mineocclude warmup 12000",
        "mineocclude start layout_01 11505 202608031505 0.0 0.0 20",
    ]
    assert manifest["reserved_second_operator"]["episode_id"] == 11502
    assert manifest["reserved_second_operator"]["reused_for_retry"] is False
    assert manifest["historical_attempts"]["attempt_03"]["failure_record"]["sha256"] == hashlib.sha256(failure).hexdigest()
    expected_sha = hashlib.sha256(schedule_data).hexdigest()
    assert manifest["retry"]["schedule"]["repository"]["sha256"] == expected_sha
    assert manifest["retry"]["schedule"]["runtime"]["sha256"] == expected_sha
    assert manifest["collision_audit"] == {
        "candidate_episode_id": RETRY_EPISODE_ID,
        "candidate_seed": RETRY_SEED,
        "repository_schedule_collision": False,
        "runtime_identity_collision": False,
        "create_only_output_collision": False,
        "reserved_second_operator_unchanged": True,
    }


def test_finalizer_is_single_confirmation_create_only_and_attempt_04_scoped() -> None:
    content = FINALIZATION_SCRIPT.read_text(encoding="utf-8")
    assert content.count("Read-Host") == 1
    assert "[System.IO.FileMode]::CreateNew" in content
    assert "--validate-only" in content
    assert "episode 11505 aborted during warmup" in content
    assert "episode 11505 recording started" in content
    assert "attempt_01" not in content
    assert "attempt_02" not in content
    assert "attempt_03" not in content


def test_attempt_04_sha256_inventory_is_self_consistent() -> None:
    inventory = json.loads((DOC_DIR / "sha256_inventory.json").read_text())
    listed = {entry["path"] for entry in inventory["files"]}
    disk = {
        path.relative_to(Path.cwd()).as_posix()
        for path in DOC_DIR.iterdir()
        if path.is_file() and path.name != "sha256_inventory.json"
    }
    assert listed == disk
    for entry in inventory["files"]:
        data = Path(entry["path"]).read_bytes()
        assert len(data) == entry["size_bytes"]
        assert hashlib.sha256(data).hexdigest() == entry["sha256"]
