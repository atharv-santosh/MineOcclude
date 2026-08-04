from __future__ import annotations

import os
from pathlib import Path
import subprocess
import threading
import time
from collections.abc import Iterator
from uuid import uuid4

import pytest


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "scripts/person_c/C6ALiveLog.psm1"
CAPTURE_SCRIPT = ROOT / "scripts/person_c/run-c6a-capture.ps1"
EVENT = (
    "[05:24:30] [Server thread/INFO]: [MineOcclude] loaded immutable noise "
    "schedule (300 draws) from .\\mineocclude_schedules\\episode_12601.jsonl"
)


@pytest.fixture
def workspace_tmp_path() -> Iterator[Path]:
    test_root = ROOT / "tests/.c6a_live_log_test_work"
    test_root.mkdir(exist_ok=True)
    directory = test_root / uuid4().hex
    directory.mkdir()
    try:
        yield directory
    finally:
        for path in list(directory.iterdir()):
            path.unlink()
        directory.rmdir()
        try:
            test_root.rmdir()
        except OSError:
            pass


def _ps_quote(value: str | Path) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _powershell(body: str, timeout: float = 10) -> subprocess.CompletedProcess[str]:
    command = f"Import-Module -Force {_ps_quote(MODULE)}; {body}"
    return subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _assert_success(result: subprocess.CompletedProcess[str]) -> None:
    assert result.returncode == 0, result.stdout + result.stderr


def _semantic_check(episode: int, draws: int, filename: str, expect: bool) -> None:
    expected = "$true" if expect else "$false"
    body = (
        f"$text={_ps_quote(EVENT)}; "
        f"if ((Test-C6AScheduleLoadEvent -Text $text -EpisodeId {episode} -DrawCount {draws} "
        f"-ScheduleFileName {_ps_quote(filename)}) -ne {expected}) {{ exit 9 }}"
    )
    _assert_success(_powershell(body))


def test_existing_episode_12601_schedule_line_is_recognized_semantically() -> None:
    _semantic_check(12601, 300, "episode_12601.jsonl", True)


@pytest.mark.parametrize(
    ("episode", "draws", "filename"),
    [
        (12602, 300, "episode_12601.jsonl"),
        (12601, 60, "episode_12601.jsonl"),
        (12601, 300, "episode_12602.jsonl"),
    ],
)
def test_wrong_schedule_identity_fails_semantic_match(episode: int, draws: int, filename: str) -> None:
    _semantic_check(episode, draws, filename, False)


def test_delayed_live_log_flush_is_detected_by_bounded_poll(workspace_tmp_path: Path) -> None:
    log = workspace_tmp_path / "latest.log"
    log.write_text("[05:24:29] [MineOcclude] server ready\n", encoding="utf-8")
    start_offset = log.stat().st_size
    with log.open("a", encoding="utf-8", buffering=8192) as writer:
        writer.write(EVENT + "\n")

        def delayed_flush() -> None:
            time.sleep(0.25)
            writer.flush()
            os.fsync(writer.fileno())

        thread = threading.Thread(target=delayed_flush)
        thread.start()
        body = (
            f"if (-not (Wait-C6AScheduleLoadEvent -Path {_ps_quote(log)} -EpisodeId 12601 -DrawCount 300 "
            f"-ScheduleFileName 'episode_12601.jsonl' -StartOffset {start_offset} "
            "-TimeoutMilliseconds 2000 -PollIntervalMilliseconds 25)) { exit 9 }"
        )
        result = _powershell(body)
        thread.join(timeout=2)
    _assert_success(result)


def test_timeout_fails_closed_when_event_never_appears(workspace_tmp_path: Path) -> None:
    log = workspace_tmp_path / "latest.log"
    log.write_text("[05:24:29] [MineOcclude] server ready\n", encoding="utf-8")
    started = time.monotonic()
    body = (
        f"if (Wait-C6AScheduleLoadEvent -Path {_ps_quote(log)} -EpisodeId 12601 -DrawCount 300 "
        "-ScheduleFileName 'episode_12601.jsonl' -StartOffset 0 "
        "-TimeoutMilliseconds 200 -PollIntervalMilliseconds 25) { exit 9 }"
    )
    result = _powershell(body)
    elapsed = time.monotonic() - started
    _assert_success(result)
    assert 0.15 <= elapsed < 3


def test_live_log_can_be_read_while_writer_handle_remains_open(workspace_tmp_path: Path) -> None:
    log = workspace_tmp_path / "latest.log"
    with log.open("w", encoding="utf-8") as writer:
        writer.write(EVENT + "\n")
        writer.flush()
        os.fsync(writer.fileno())
        body = (
            f"$text=Read-C6ALiveLogText -Path {_ps_quote(log)}; "
            "if (-not (Test-C6AScheduleLoadEvent -Text $text -EpisodeId 12601 -DrawCount 300 "
            "-ScheduleFileName 'episode_12601.jsonl')) { exit 9 }"
        )
        result = _powershell(body)
    _assert_success(result)


def test_capture_script_uses_post_command_semantic_bounded_poll() -> None:
    script = CAPTURE_SCRIPT.read_text(encoding="utf-8")
    offset = script.index("$scheduleLogOffset = Get-C6ALiveLogLength")
    command = script.index("$process.StandardInput.Flush()", offset)
    poll = script.index("Wait-C6AScheduleLoadEvent", command)
    assert offset < command < poll
    assert "-DrawCount $episode.noise_schedule.n_draws" in script
    assert "-ScheduleFileName $scheduleFileName" in script
    assert "-TimeoutMilliseconds 60000" in script
