from __future__ import annotations

import hashlib
import os
import subprocess
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


REPO = Path(__file__).resolve().parents[1]
MODULE = REPO / "scripts/person_c/ERefitCalibrationAttempt02Authority.psm1"


def ps_quote(value: Path | str) -> str:
    return str(value).replace("'", "''")


def run_powershell(command: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
        cwd=REPO,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )


def hash_command(path: Path) -> str:
    return (
        f"Import-Module -Force -Name '{ps_quote(MODULE)}'; "
        f"Get-ERefitAttempt02Sha256 -Path '{ps_quote(path)}'"
    )


@contextmanager
def workspace_temp_files(count: int) -> Iterator[list[Path]]:
    paths: list[Path] = []
    try:
        for _ in range(count):
            descriptor, name = tempfile.mkstemp(prefix=".attempt02_live_hash_", dir=REPO)
            os.close(descriptor)
            paths.append(Path(name))
        yield paths
    finally:
        for path in paths:
            path.unlink(missing_ok=True)


def test_unlocked_file_hashing_matches_ordinary_sha256() -> None:
    with workspace_temp_files(1) as paths:
        path = paths[0]
        data = b"ordinary unlocked SHA-256 behavior\x00\xff"
        path.write_bytes(data)
        result = run_powershell(hash_command(path))
        assert result.returncode == 0, result.stdout + result.stderr
        assert result.stdout.strip() == hashlib.sha256(data).hexdigest()


def test_file_held_open_for_writing_with_shared_read_can_be_hashed() -> None:
    with workspace_temp_files(2) as paths:
        path, ready = paths
        ready.unlink()
        data = b"[server/INFO] live Log4j-compatible bytes\n"
        path.write_bytes(data)
        writer_command = (
            "$share = [System.IO.FileShare]::ReadWrite -bor [System.IO.FileShare]::Delete; "
            f"$stream = [System.IO.FileStream]::new('{ps_quote(path)}', "
            "[System.IO.FileMode]::Open, [System.IO.FileAccess]::Write, $share); "
            f"[System.IO.File]::WriteAllText('{ps_quote(ready)}', 'ready'); "
            "try { [void][Console]::In.ReadLine() } finally { $stream.Dispose() }"
        )
        writer = subprocess.Popen(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", writer_command],
            cwd=REPO,
            text=True,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        try:
            deadline = time.monotonic() + 10
            while not ready.exists() and time.monotonic() < deadline:
                time.sleep(0.02)
            assert ready.exists(), "writer did not acquire its shared-write handle"
            result = run_powershell(hash_command(path))
            assert result.returncode == 0, result.stdout + result.stderr
            assert result.stdout.strip() == hashlib.sha256(data).hexdigest()
        finally:
            if writer.stdin is not None:
                writer.stdin.write("\n")
                writer.stdin.flush()
            writer.communicate(timeout=10)


def test_incorrect_expected_hash_still_fails_closed() -> None:
    with workspace_temp_files(1) as paths:
        path = paths[0]
        path.write_bytes(b"actual bytes")
        command = (
            f"Import-Module -Force -Name '{ps_quote(MODULE)}'; "
            f"$actual = Get-ERefitAttempt02Sha256 -Path '{ps_quote(path)}'; "
            "Assert-ERefitAttempt02Condition ($actual -ceq ('0' * 64)) 'Expected SHA-256 mismatch'"
        )
        result = run_powershell(command)
        assert result.returncode != 0
        assert "Expected SHA-256 mismatch" in result.stdout + result.stderr


def test_missing_file_hashing_fails_closed() -> None:
    with workspace_temp_files(1) as paths:
        missing = paths[0]
        missing.unlink()
        result = run_powershell(hash_command(missing))
        assert result.returncode != 0
        assert "File is absent" in result.stdout + result.stderr
