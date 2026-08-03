from __future__ import annotations

import json
import hashlib
from pathlib import Path

import pytest

from mineocclude.data.noise_schedule import generate_noise_schedule, load_schedule, serialize_schedule
from scripts.person_c.ingest_c1_5_attempt_02_runtime import validate_retry_log
from scripts.person_c.prepare_c1_5_attempt_02 import (
    DOC_DIR,
    FAILURE_CLASSIFICATION,
    RESERVED_SECOND_EPISODE_ID,
    RETRY_ATTESTATION,
    RETRY_CLIENT_OUTPUT,
    RETRY_EPISODE_ID,
    RETRY_INGESTED,
    RETRY_RECEIPT,
    RETRY_REPO_SCHEDULE,
    RETRY_SCREENSHOT,
    RETRY_SEED,
    RETRY_SERVER_OUTPUT,
    RETRY_RUNTIME_SCHEDULE,
    assert_candidate_unused,
)


def _valid_log(status_second: int = 10) -> list[str]:
    return [
        "[12:00:00] [Server thread/INFO]: [MineOcclude] episode 11503 armed (layout=layout_01)",
        f"[12:00:{status_second:02d}] [Server thread/INFO]: target status: valid=true required=true count=1 episode=11503 lifecycle=READY problems=NONE",
        f"[12:00:{status_second + 1:02d}] [Server thread/INFO]: [MineOcclude/observation] wrote read-only geometry receipt .\\mineocclude_observations\\c1_5_first_operator_attempt_02_layout_01.json",
        f"[12:00:{status_second + 2:02d}] [Server thread/INFO]: [MineOcclude] episode 11503 aborted during warmup",
        f"[12:00:{status_second + 3:02d}] [Server thread/INFO]: Stopping server",
    ]


def test_retry_identity_skips_reserved_second_operator() -> None:
    assert RESERVED_SECOND_EPISODE_ID == 11502
    assert RETRY_EPISODE_ID == 11503
    assert RETRY_SEED == 202608031503
    assert FAILURE_CLASSIFICATION == "POST_FINALIZATION_OBSERVATION_INVALID_NOT_TARGET_RETENTION_FAILURE"


def test_retry_schedule_is_deterministic_and_loadable(tmp_path) -> None:
    data = serialize_schedule(generate_noise_schedule(seed=RETRY_SEED, n_draws=20, q=0.0))
    path = tmp_path / "episode_11503.jsonl"
    path.write_bytes(data)
    loaded = load_schedule(str(path))
    assert loaded.seed == RETRY_SEED
    assert loaded.n_draws == 20
    assert loaded.q == 0.0
    assert json.loads(data.splitlines()[0])["seed"] == RETRY_SEED


def test_retry_log_requires_observation_during_warmup() -> None:
    result = validate_retry_log(_valid_log())
    assert result["armed_to_status_seconds"] == 10
    assert result["observation_before_recording"] is True


def test_retry_log_rejects_status_before_ten_seconds() -> None:
    with pytest.raises(ValueError, match="at least 10 seconds"):
        validate_retry_log(_valid_log(status_second=9))


def test_retry_log_rejects_any_recording_start() -> None:
    lines = _valid_log()
    lines.insert(3, "[12:00:11] [Server thread/INFO]: [MineOcclude] episode 11503 recording started")
    with pytest.raises(ValueError, match="entered recording"):
        validate_retry_log(lines)


def test_generated_package_binds_schedule_and_collision_guards() -> None:
    schedule_data = RETRY_REPO_SCHEDULE.read_bytes()
    manifest = json.loads((DOC_DIR / "attempt_02_manifest.json").read_text())
    failure = (DOC_DIR / "attempt_01_failure_record.json").read_bytes()
    assert manifest["retry"]["episode_id"] == RETRY_EPISODE_ID
    assert manifest["retry"]["seed"] == RETRY_SEED
    assert manifest["retry"]["observe_must_occur_before_recording"] is True
    assert manifest["reserved_second_operator"]["episode_id"] == 11502
    assert manifest["reserved_second_operator"]["reused_for_retry"] is False
    assert manifest["attempt_01_failure_record"]["sha256"] == hashlib.sha256(failure).hexdigest()
    expected_schedule_sha = hashlib.sha256(schedule_data).hexdigest()
    assert manifest["retry"]["schedule"]["repository"]["sha256"] == expected_schedule_sha
    assert hashlib.sha256(RETRY_RUNTIME_SCHEDULE.read_bytes()).hexdigest() == expected_schedule_sha
    assert assert_candidate_unused(schedule_data)["create_only_output_collision"] is False
    assert all(not path.exists() for path in (
        RETRY_RECEIPT, RETRY_SCREENSHOT, RETRY_ATTESTATION, RETRY_INGESTED,
        RETRY_SERVER_OUTPUT, RETRY_CLIENT_OUTPUT,
    ))


def test_attempt_02_sha256_inventory_is_self_consistent() -> None:
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
