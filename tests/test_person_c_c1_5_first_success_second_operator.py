from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest

from mineocclude.data.noise_schedule import load_schedule
from scripts.person_c.ingest_c1_5_second_operator_runtime import (
    REQUIRED_ATTESTATION_FIELDS,
    validate_attestation,
    validate_second_logs,
)
from scripts.person_c.prepare_c1_5_first_success_second_operator import (
    C6A_SCHEDULE_SET_SHA256,
    FIRST_ATTESTATION,
    FIRST_DOC_DIR,
    FIRST_INGESTED_SHA256,
    OBSERVATION_WINDOW_SECONDS,
    SECOND_ATTESTATION,
    SECOND_ATTESTATION_TEMPLATE,
    SECOND_CLIENT_LOG_ARCHIVE,
    SECOND_CLIENT_OUTPUT,
    SECOND_CONFIG_DIR,
    SECOND_DOC_DIR,
    SECOND_EPISODE_ID,
    SECOND_FINALIZER,
    SECOND_INGESTED,
    SECOND_RECEIPT,
    SECOND_REPO_SCHEDULE,
    SECOND_RUNTIME_SCHEDULE,
    SECOND_SCHEDULE_SHA256,
    SECOND_SCREENSHOT,
    SECOND_SEED,
    SECOND_SERVER_LOG_ARCHIVE,
    SECOND_SERVER_OUTPUT,
    SECOND_WARMUP_TICKS,
    validate_c6a,
    validate_first_operator,
    validate_second_identity,
)


def _valid_logs(
    *,
    screenshot_second: int = 13,
    include_abort: bool = True,
    include_recording: bool = False,
) -> tuple[list[str], list[str]]:
    server = [
        "[12:00:00] [Server thread/INFO]: Warmup delay set to 12000 ticks (600.0s)",
        "[12:00:01] [Server thread/INFO]: [MineOcclude] loaded immutable noise schedule (20 draws) from .\\mineocclude_schedules\\episode_11502.jsonl",
        "[12:00:01] [Server thread/INFO]: [MineOcclude] episode 11502 armed (layout=layout_01, 12000 warmup + 20 record ticks, v=0.0, q=0.0, seed=202608031502)",
        "[12:00:11] [Server thread/INFO]: target status: valid=true required=true count=1 episode=11502 lifecycle=READY problems=NONE",
        "[12:00:12] [Server thread/INFO]: [MineOcclude/observation] wrote read-only geometry receipt .\\mineocclude_observations\\c1_5_second_operator_attempt_01_layout_01.json",
    ]
    if include_recording:
        server.append(
            "[12:00:14] [Server thread/INFO]: [MineOcclude] episode 11502 recording started"
        )
    if include_abort:
        server.append(
            "[12:00:15] [Server thread/INFO]: [MineOcclude] episode 11502 aborted during warmup"
        )
    server.append("[12:00:16] [Server thread/INFO]: Stopping server")
    client = [
        "[11:59:50] [main/INFO]: Setting user: independent_account",
        "[11:59:55] [main/INFO]: Connecting to 127.0.0.1, 25565",
        f"[12:00:{screenshot_second:02d}] [main/INFO]: [CHAT] Saved screenshot as 2026-08-04_12.00.{screenshot_second:02d}.png",
        "[12:00:17] [main/INFO]: Stopping!",
    ]
    return server, client


def _completed_attestation() -> tuple[dict[str, object], dict[str, object]]:
    first = json.loads(FIRST_ATTESTATION.read_text(encoding="utf-8-sig"))
    value = dict(SECOND_ATTESTATION_TEMPLATE)
    value.update({
        "template": False,
        "operator_id": "independent_account",
        "utc_start": "2026-08-04T16:00:00+00:00",
        "utc_end": "2026-08-04T16:01:00+00:00",
        "preparation_commit": "1" * 40,
        "observed_account_name": "independent_account",
        "fresh_runtime_session": True,
        "all_runbook_steps_performed_without_memory_or_prior_artifact_reuse": True,
        "targetstatus_passed_after_ten_seconds": True,
        "observegeometry_completed_during_warmup_before_recording": True,
        "receipt_write_confirmed_before_f2": True,
        "f2_pressed_immediately_after_receipt_confirmation": True,
        "mineocclude_stop_issued_immediately_after_f2": True,
        "screenshot_from_same_session": True,
        "server_stopped_cleanly": True,
        "operator_identity_differs_from_first_operator": True,
        "authenticated_account_differs_from_first_operator": True,
        "did_not_use_first_operator_memory_screenshot_receipt_or_prior_result_to_reconstruct_scene": True,
        "notes": "independent run",
    })
    return value, first


def test_first_operator_success_revalidates_and_is_complete() -> None:
    _, chronology = validate_first_operator()
    receipt = json.loads(
        (FIRST_DOC_DIR / "first_operator_success_receipt.json").read_text()
    )
    assert receipt["c1_5_first_operator_complete"] is True
    assert receipt["c1_5_complete"] is False
    assert receipt["chronology"] == chronology
    assert receipt["runtime_evidence"]["ingested_output"]["sha256"] == FIRST_INGESTED_SHA256


def test_reserved_second_identity_is_unused_and_collision_free() -> None:
    result = validate_second_identity()
    assert result["episode_id"] == 11502
    assert result["seed"] == 202608031502
    assert result["episode_identity_unused"] is True
    assert result["create_only_outputs_absent"] is True
    assert all(not path.exists() for path in (
        SECOND_RECEIPT,
        SECOND_SCREENSHOT,
        SECOND_ATTESTATION,
        SECOND_INGESTED,
        SECOND_SERVER_LOG_ARCHIVE,
        SECOND_CLIENT_LOG_ARCHIVE,
        SECOND_SERVER_OUTPUT,
        SECOND_CLIENT_OUTPUT,
    ))


def test_reserved_schedule_is_hash_bound_and_loadable() -> None:
    assert SECOND_EPISODE_ID == 11502
    assert SECOND_SEED == 202608031502
    assert SECOND_WARMUP_TICKS == 12000
    assert OBSERVATION_WINDOW_SECONDS == 600
    assert hashlib.sha256(SECOND_REPO_SCHEDULE.read_bytes()).hexdigest() == SECOND_SCHEDULE_SHA256
    assert SECOND_REPO_SCHEDULE.read_bytes() == SECOND_RUNTIME_SCHEDULE.read_bytes()
    loaded = load_schedule(str(SECOND_REPO_SCHEDULE))
    assert loaded.seed == SECOND_SEED
    assert loaded.n_draws == 20
    assert loaded.q == 0.0


def test_independent_attestation_contract_is_complete() -> None:
    assert set(SECOND_ATTESTATION_TEMPLATE) == REQUIRED_ATTESTATION_FIELDS
    completed, first = _completed_attestation()
    validate_attestation(completed, first)


def test_independence_rejects_lollo_and_first_operator_identity() -> None:
    completed, first = _completed_attestation()
    completed["operator_id"] = "lollo"
    with pytest.raises(ValueError, match="operator_id=lollo"):
        validate_attestation(completed, first)
    completed, first = _completed_attestation()
    first = dict(first)
    first["operator_id"] = "first_human"
    completed["operator_id"] = first["operator_id"]
    with pytest.raises(ValueError, match="matches first operator"):
        validate_attestation(completed, first)


def test_independence_rejects_first_account_or_prior_result_reuse() -> None:
    completed, first = _completed_attestation()
    completed["observed_account_name"] = first["observed_account_name"]
    with pytest.raises(ValueError, match="account matches first"):
        validate_attestation(completed, first)
    completed, first = _completed_attestation()
    completed[
        "did_not_use_first_operator_memory_screenshot_receipt_or_prior_result_to_reconstruct_scene"
    ] = False
    with pytest.raises(ValueError, match="independence/timing attestation missing"):
        validate_attestation(completed, first)


def test_second_chronology_accepts_strict_warmup_abort_sequence() -> None:
    server, client = _valid_logs()
    result = validate_second_logs(server, client)
    assert result["armed_to_status_seconds"] == 10
    assert result["armed_to_observation_seconds"] == 11
    assert result["armed_to_screenshot_seconds"] == 12
    assert result["armed_to_abort_seconds"] == 14
    assert result["recording_started"] is False


def test_second_chronology_rejects_recording_before_abort() -> None:
    server, client = _valid_logs(include_recording=True)
    with pytest.raises(ValueError, match="recording started before warmup abort"):
        validate_second_logs(server, client)


def test_second_chronology_rejects_absent_abort() -> None:
    server, client = _valid_logs(include_abort=False)
    with pytest.raises(ValueError, match="episode 11502 aborted during warmup"):
        validate_second_logs(server, client)


def test_second_chronology_rejects_screenshot_before_receipt() -> None:
    server, client = _valid_logs(screenshot_second=11)
    with pytest.raises(ValueError, match="receipt < F2 screenshot"):
        validate_second_logs(server, client)


def test_turnkey_instructions_manifest_and_finalizer_enforce_independence() -> None:
    manifest = json.loads((SECOND_DOC_DIR / "second_operator_manifest.json").read_text())
    instructions = (SECOND_DOC_DIR / "SECOND_OPERATOR_INSTRUCTIONS.md").read_text()
    finalizer = SECOND_FINALIZER.read_text(encoding="utf-8")
    assert manifest["second_operator"]["ordered_start_commands"][-2:] == [
        "mineocclude warmup 12000",
        "mineocclude start layout_01 11502 202608031502 0.0 0.0 20",
    ]
    assert manifest["independence_enforcement"]["operator_id_lollo_forbidden"] is True
    assert len(re.findall(r"(?m)^\d+\.", instructions)) == 11
    assert "Do not edit JSON" in instructions
    assert finalizer.count("Read-Host") == 1
    assert "operator_id=lollo is forbidden" in finalizer
    assert "Copy-CreateOnly $first" not in finalizer


def test_c6a_and_generated_package_inventories_remain_valid() -> None:
    c6a = validate_c6a()
    assert c6a["manifest_still_valid"] is True
    assert c6a["schedule_set_sha256"] == C6A_SCHEDULE_SET_SHA256
    binding = json.loads((SECOND_CONFIG_DIR / "schedule_binding.json").read_text())
    assert binding["historically_reserved_and_never_consumed"] is True
    for directory in (FIRST_DOC_DIR, SECOND_DOC_DIR):
        inventory = json.loads((directory / "sha256_inventory.json").read_text())
        listed = {entry["path"] for entry in inventory["files"]}
        disk = {
            path.relative_to(Path.cwd()).as_posix()
            for path in directory.iterdir()
            if path.is_file() and path.name != "sha256_inventory.json"
        }
        assert listed == disk
        for entry in inventory["files"]:
            data = Path(entry["path"]).read_bytes()
            assert len(data) == entry["size_bytes"]
            assert hashlib.sha256(data).hexdigest() == entry["sha256"]
