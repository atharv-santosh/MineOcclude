from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from mineocclude.data.noise_schedule import load_schedule
from scripts.person_c.ingest_c1_5_second_operator_attempt_02_runtime import (
    EXPECTED_FAILURE_CLASSIFICATION,
    REQUIRED_ATTESTATION_FIELDS,
    validate_attempt_02_logs,
    validate_attestation,
)
from scripts.person_c.prepare_c1_5_second_operator_attempt_02 import (
    ATTEMPT_01_ACCOUNT,
    ATTESTATION_TEMPLATE,
    CLIENT,
    DOC_DIR,
    FAILURE_CLASSIFICATION,
    FINALIZER,
    REPO_SCHEDULE,
    RETRY_ATTESTATION,
    RETRY_CLIENT_LOG,
    RETRY_CLIENT_OUTPUT,
    RETRY_EPISODE_ID,
    RETRY_INGESTED,
    RETRY_RECEIPT,
    RETRY_SCREENSHOT,
    RETRY_SEED,
    RETRY_SERVER_LOG,
    RETRY_SERVER_OUTPUT,
    RETRY_WARMUP_TICKS,
    RUNTIME_SCHEDULE,
    SERVER,
    validate_attempt_01,
    validate_candidate,
)


def _logs(*, screenshot_seconds: tuple[int, ...] = (13,), status_second: int = 11,
          include_recording: bool = False) -> tuple[list[str], list[str]]:
    server = [
        "[12:00:00] [Server thread/INFO]: Warmup delay set to 12000 ticks (600.0s)",
        "[12:00:01] [Server thread/INFO]: [MineOcclude] episode 11506 armed (layout=layout_01, 12000 warmup + 20 record ticks, v=0.0, q=0.0, seed=202608031506)",
        f"[12:00:{status_second:02d}] [Server thread/INFO]: target status: valid=true required=true count=1 episode=11506 lifecycle=READY problems=NONE",
        "[12:00:12] [Server thread/INFO]: [MineOcclude/observation] wrote read-only geometry receipt .\\mineocclude_observations\\c1_5_second_operator_attempt_02_layout_01.json",
        "[12:00:12] [Server thread/INFO]: Wrote observation-only geometry receipt: .\\mineocclude_observations\\c1_5_second_operator_attempt_02_layout_01.json",
    ]
    if include_recording:
        server.append("[12:00:14] [Server thread/INFO]: [MineOcclude] episode 11506 recording started")
    server.extend([
        "[12:00:15] [Server thread/INFO]: [MineOcclude] episode 11506 aborted during warmup",
        "[12:00:16] [Server thread/INFO]: Stopping server",
    ])
    client = [
        "[11:59:50] [main/INFO]: Setting user: Santa313",
        "[11:59:55] [main/INFO]: Connecting to 127.0.0.1, 25565",
    ]
    client.extend(
        f"[12:00:{second:02d}] [main/INFO]: [CHAT] Saved screenshot as 2026-08-04_12.00.{second:02d}.png"
        for second in screenshot_seconds
    )
    client.append("[12:00:17] [main/INFO]: Stopping!")
    return server, client


def _completed_attestation() -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    failure = json.loads((DOC_DIR / "attempt_01_failure_record.json").read_text())
    first = json.loads(
        (SERVER / "c1_5_evidence/first_operator_attempt_04_attestation.json").read_text()
    )
    value = json.loads(
        (DOC_DIR / "second_operator_attempt_02_attestation.template.json").read_text()
    )
    value.update({
        "template": False,
        "operator_id": ATTEMPT_01_ACCOUNT,
        "same_human_as_second_operator_attempt_01": True,
        "utc_start": "2026-08-04T17:00:00+00:00",
        "utc_end": "2026-08-04T17:01:00+00:00",
        "preparation_commit": "1" * 40,
        "observed_account_name": ATTEMPT_01_ACCOUNT,
        "fresh_runtime_session": True,
        "targetstatus_passed_after_at_least_ten_seconds": True,
        "observegeometry_completed_before_receipt_confirmation": True,
        "receipt_write_confirmed_before_f2": True,
        "exactly_one_f2_after_receipt_confirmation": True,
        "mineocclude_stop_aborted_during_warmup": True,
        "recording_never_started": True,
        "screenshot_from_same_session": True,
        "server_stopped_cleanly": True,
        "operator_identity_differs_from_first_operator": True,
        "authenticated_account_differs_from_first_operator": True,
        "notes": "same independent second human",
    })
    return value, first, failure


def test_attempt_01_is_hash_bound_and_classified_without_certification() -> None:
    chronology = validate_attempt_01()
    record = json.loads((DOC_DIR / "attempt_01_failure_record.json").read_text())
    assert record["classification"] == FAILURE_CLASSIFICATION
    assert record["classification"] == EXPECTED_FAILURE_CLASSIFICATION
    assert record["target_retention_implementation_passed"] is True
    assert record["preservation"]["status"] == "PRESERVED_HASH_BOUND_NOT_CERTIFIED"
    assert chronology["screenshot_preceded_receipt_confirmation_seconds"] == 12


def test_retry_identity_schedule_and_collision_guards() -> None:
    assert RETRY_EPISODE_ID == 11506
    assert RETRY_SEED == 202608031506
    assert RETRY_WARMUP_TICKS == 12000
    assert hashlib.sha256(REPO_SCHEDULE.read_bytes()).hexdigest() == "9c1753aca561a245c2be5015072ab0278c6c6abcb35d74b276c0fd37b9ab0172"
    manifest = json.loads((DOC_DIR / "attempt_02_manifest.json").read_text())
    assert manifest["retry"]["schedule"]["sha256"] == hashlib.sha256(REPO_SCHEDULE.read_bytes()).hexdigest()
    assert manifest["retry"]["schedule"]["runtime"]["sha256"] == manifest["retry"]["schedule"]["sha256"]
    schedule = load_schedule(str(REPO_SCHEDULE))
    assert schedule.seed == RETRY_SEED
    assert schedule.q == 0.0
    assert schedule.n_draws == 20
    audit = manifest["collision_audit"]
    assert audit["runtime_schedule_installed"] is True
    assert audit["create_only_outputs_absent"] is True
    assert audit["server_client_episode_outputs_absent"] is True
    assert audit["collisions"] == []


def test_strict_chronology_accepts_exact_required_order() -> None:
    server, client = _logs()
    result = validate_attempt_02_logs(server, client)
    assert result["armed_to_status_seconds"] == 10
    assert result["armed_to_receipt_confirmation_seconds"] == 11
    assert result["armed_to_screenshot_seconds"] == 12
    assert result["screenshot_count_during_episode"] == 1
    assert result["episode_aborted_during_warmup"] is True
    assert result["recording_started"] is False


def test_strict_chronology_rejects_f2_before_confirmation() -> None:
    server, client = _logs(screenshot_seconds=(11,))
    with pytest.raises(ValueError, match="receipt confirmation"):
        validate_attempt_02_logs(server, client)


def test_strict_chronology_rejects_more_than_one_f2() -> None:
    server, client = _logs(screenshot_seconds=(13, 14))
    with pytest.raises(ValueError, match="exactly one F2"):
        validate_attempt_02_logs(server, client)


def test_strict_chronology_rejects_early_status_and_recording() -> None:
    server, client = _logs(status_second=10)
    with pytest.raises(ValueError, match="less than ten seconds"):
        validate_attempt_02_logs(server, client)
    server, client = _logs(include_recording=True)
    with pytest.raises(ValueError, match="recording started"):
        validate_attempt_02_logs(server, client)


def test_attestation_requires_same_second_human_and_independence() -> None:
    assert set(ATTESTATION_TEMPLATE) == REQUIRED_ATTESTATION_FIELDS
    completed, first, failure = _completed_attestation()
    validate_attestation(completed, first, failure)
    completed["same_human_as_second_operator_attempt_01"] = False
    with pytest.raises(ValueError, match="same second human"):
        validate_attestation(completed, first, failure)
    completed, first, failure = _completed_attestation()
    completed["observed_account_name"] = "overatedusername"
    with pytest.raises(ValueError, match="does not match attempt-01"):
        validate_attestation(completed, first, failure)


def test_manifest_instructions_finalizer_and_inventory_are_turnkey() -> None:
    manifest = json.loads((DOC_DIR / "attempt_02_manifest.json").read_text())
    instructions = (DOC_DIR / "SECOND_OPERATOR_ATTEMPT_02_INSTRUCTIONS.md").read_text()
    finalizer = FINALIZER.read_text(encoding="utf-8")
    assert manifest["retry"]["ordered_start_commands"][-2:] == [
        "mineocclude warmup 12000",
        "mineocclude start layout_01 11506 202608031506 0.0 0.0 20",
    ]
    assert manifest["operator_requirements"]["same_human_as_second_operator_attempt_01_required"] is True
    assert "Do not press F2 before" in instructions
    assert "Exactly one F2 screenshot" in finalizer
    assert "episode 11506 recording started" in finalizer
    assert finalizer.count("Read-Host") == 1
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
