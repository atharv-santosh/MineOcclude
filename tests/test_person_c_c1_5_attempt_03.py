from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from mineocclude.data.noise_schedule import generate_noise_schedule, load_schedule, serialize_schedule
from scripts.person_c.ingest_c1_5_attempt_03_runtime import validate_retry_log
from scripts.person_c.prepare_c1_5_attempt_03 import (
    DOC_DIR,
    FAILURE_CLASSIFICATION,
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


def _valid_log(status_second: int = 10) -> list[str]:
    return [
        "[12:00:00] [Server thread/INFO]: Warmup delay set to 2400 ticks (120.0s)",
        "[12:00:01] [Server thread/INFO]: [MineOcclude] episode 11504 armed (layout=layout_01, 2400 warmup + 20 record ticks, v=0.0, q=0.0, seed=202608031504)",
        f"[12:00:{status_second + 1:02d}] [Server thread/INFO]: target status: valid=true required=true count=1 episode=11504 lifecycle=READY problems=NONE",
        f"[12:00:{status_second + 2:02d}] [Server thread/INFO]: [MineOcclude/observation] wrote read-only geometry receipt .\\mineocclude_observations\\c1_5_first_operator_attempt_03_layout_01.json",
        f"[12:00:{status_second + 3:02d}] [Server thread/INFO]: [MineOcclude] episode 11504 aborted during warmup",
        f"[12:00:{status_second + 4:02d}] [Server thread/INFO]: Stopping server",
    ]


def test_retry_identity_skips_reserved_second_operator_and_extends_warmup() -> None:
    assert RESERVED_SECOND_EPISODE_ID == 11502
    assert RETRY_EPISODE_ID == 11504
    assert RETRY_SEED == 202608031504
    assert RETRY_WARMUP_TICKS == 2400
    assert OBSERVATION_WINDOW_SECONDS == 120
    assert FAILURE_CLASSIFICATION == "POST_FINALIZATION_OBSERVATION_INVALID_NOT_TARGET_RETENTION_FAILURE"


def test_retry_schedule_is_deterministic_and_loadable(tmp_path) -> None:
    data = serialize_schedule(generate_noise_schedule(seed=RETRY_SEED, n_draws=20, q=0.0))
    path = tmp_path / "episode_11504.jsonl"
    path.write_bytes(data)
    loaded = load_schedule(str(path))
    assert loaded.seed == RETRY_SEED
    assert loaded.n_draws == 20
    assert loaded.q == 0.0


def test_retry_log_binds_2400_warmup_and_ten_second_status() -> None:
    result = validate_retry_log(_valid_log())
    assert result["warmup_ticks"] == 2400
    assert result["observation_window_seconds"] == 120
    assert result["armed_to_status_seconds"] == 10
    assert result["observation_before_recording"] is True


def test_retry_log_rejects_wrong_warmup() -> None:
    lines = [line.replace("2400", "1200").replace("120.0s", "60.0s") for line in _valid_log()]
    with pytest.raises(ValueError, match="Warmup delay set to 2400"):
        validate_retry_log(lines)


def test_retry_log_rejects_late_status_or_recording_start() -> None:
    with pytest.raises(ValueError, match="approximately 10 seconds"):
        validate_retry_log(_valid_log(status_second=20))
    lines = _valid_log()
    lines.insert(4, "[12:00:13] [Server thread/INFO]: [MineOcclude] episode 11504 recording started")
    with pytest.raises(ValueError, match="entered recording"):
        validate_retry_log(lines)


def test_generated_package_binds_warmup_schedule_and_collision_guards() -> None:
    schedule_data = RETRY_REPO_SCHEDULE.read_bytes()
    manifest = json.loads((DOC_DIR / "attempt_03_manifest.json").read_text())
    failure = (DOC_DIR / "attempt_02_failure_record.json").read_bytes()
    assert manifest["retry"]["episode_id"] == RETRY_EPISODE_ID
    assert manifest["retry"]["seed"] == RETRY_SEED
    assert manifest["retry"]["warmup_ticks"] == 2400
    assert manifest["retry"]["observation_window_seconds"] == 120
    assert manifest["retry"]["ordered_start_commands"][-2:] == [
        "mineocclude warmup 2400",
        "mineocclude start layout_01 11504 202608031504 0.0 0.0 20",
    ]
    assert manifest["reserved_second_operator"]["episode_id"] == 11502
    assert manifest["reserved_second_operator"]["reused_for_retry"] is False
    assert manifest["historical_attempts"]["attempt_02"]["failure_record"]["sha256"] == hashlib.sha256(failure).hexdigest()
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


def test_attempt_03_sha256_inventory_is_self_consistent() -> None:
    inventory = json.loads((DOC_DIR / "sha256_inventory.json").read_text())
    listed = {entry["path"] for entry in inventory["files"]}
    disk = {path.relative_to(Path.cwd()).as_posix() for path in DOC_DIR.iterdir()
            if path.is_file() and path.name != "sha256_inventory.json"}
    assert listed == disk
    for entry in inventory["files"]:
        data = Path(entry["path"]).read_bytes()
        assert len(data) == entry["size_bytes"]
        assert hashlib.sha256(data).hexdigest() == entry["sha256"]
