from __future__ import annotations

import hashlib
import json
import shutil
import struct
import subprocess
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[1]
RECOVERY_SCRIPT = REPO / "scripts/person_c/recover-e-refit-calibration-attempt-02-preflight-receipt.ps1"
PRODUCTION_IMAGE = Path(
    r"C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\client"
    r"\e_refit_calibration_v0_4_attempt_02_preflight_v0_1"
    r"\e_refit_calibration_v0_4_attempt_02_framebuffer_preflight_1920x1046.png"
)
ATTEMPT_NAME = "e_refit_calibration_v0_4_attempt_02"
EXPECTED_SHA256 = "ec3b4d101ba1ef5e7145c0c27ae92c9ff32b3d742b4116be24429206a1e79ca4"
EXPECTED_SIZE = 847670


@pytest.fixture
def recovery_tmp_path() -> Iterator[Path]:
    path = REPO / f".preflight_receipt_recovery_{uuid.uuid4().hex}"
    path.mkdir(mode=0o777)
    try:
        yield path
    finally:
        shutil.rmtree(path)


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def minimal_png(width: int, height: int, discriminator: bytes = b"") -> bytes:
    return b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + struct.pack(">II", width, height) + discriminator


def make_fixture(tmp_path: Path) -> tuple[Path, Path, Path, Path, Path]:
    client = tmp_path / "client"
    server = tmp_path / "server"
    screenshots = client / "screenshots"
    evidence = client / f"{ATTEMPT_NAME}_preflight_v0_1"
    (client / "logs").mkdir(parents=True)
    (server / "logs").mkdir(parents=True)
    screenshots.mkdir()
    evidence.mkdir()

    old = screenshots / "old.png"
    old.write_bytes(minimal_png(640, 360, b"baseline"))
    source = screenshots / "2026-08-04_01.25.10.png"
    canonical = evidence / f"{ATTEMPT_NAME}_framebuffer_preflight_1920x1046.png"
    shutil.copyfile(PRODUCTION_IMAGE, source)
    shutil.copyfile(PRODUCTION_IMAGE, canonical)
    baseline = tmp_path / "preflight_screenshot_baseline.json"
    baseline.write_text(
        json.dumps(
            {
                "schema_version": "person-c-e-refit-calibration-attempt-02-preflight-screenshot-baseline-v0.1",
                "attempt_name": ATTEMPT_NAME,
                "screenshot_count": 1,
                "screenshots": [
                    {
                        "path": str(old),
                        "size_bytes": old.stat().st_size,
                        "sha256": file_hash(old),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    options = client / "options.txt"
    options.write_text(
        "fullscreen:false\nfov:0.0\nguiScale:2\noverrideWidth:0\noverrideHeight:0\n",
        encoding="utf-8",
    )
    (client / "logs" / "latest.log").write_text(
        "[01:24:21] [main/INFO]: Setting user: TestOperator\n"
        "[01:25:05] [main/INFO]: Connecting to 127.0.0.1, 25565\n"
        "[01:25:10] [main/INFO]: [CHAT] Saved screenshot as 2026-08-04_01.25.10.png\n",
        encoding="utf-8",
    )
    (server / "logs" / "latest.log").write_text(
        "[01:25:00] [Server thread/INFO]: Done\n", encoding="utf-8"
    )
    return client, server, baseline, canonical, source


def run_recovery(
    client: Path,
    server: Path,
    baseline: Path,
    *,
    expected_hash: str = EXPECTED_SHA256,
    expected_size: int = EXPECTED_SIZE,
) -> subprocess.CompletedProcess[str]:
    options_hash = file_hash(client / "options.txt")
    return subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(RECOVERY_SCRIPT),
            "-RepoRoot",
            str(REPO),
            "-ClientRoot",
            str(client),
            "-ServerRoot",
            str(server),
            "-BaselineInventoryPath",
            str(baseline),
            "-ExpectedImageSha256",
            expected_hash,
            "-ExpectedImageSizeBytes",
            str(expected_size),
            "-ExpectedOptionsSha256",
            options_hash,
        ],
        cwd=REPO,
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
    )


def receipt_path(client: Path) -> Path:
    return (
        client
        / f"{ATTEMPT_NAME}_preflight_v0_1"
        / f"{ATTEMPT_NAME}_framebuffer_preflight_receipt.json"
    )


def test_valid_recovery_from_exact_existing_image_is_create_only(recovery_tmp_path: Path) -> None:
    client, server, baseline, canonical, source = make_fixture(recovery_tmp_path)
    before = {
        canonical: file_hash(canonical),
        source: file_hash(source),
        client / "logs" / "latest.log": file_hash(client / "logs" / "latest.log"),
        server / "logs" / "latest.log": file_hash(server / "logs" / "latest.log"),
    }
    result = run_recovery(client, server, baseline)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "RECOVERY_PROVABLE=True" in result.stdout
    receipt = json.loads(receipt_path(client).read_text(encoding="utf-8"))
    assert receipt["schema_version"] == "person-c-e-refit-calibration-attempt-02-framebuffer-preflight-v0.1"
    assert receipt["status"] == "PASS"
    assert receipt["observed_framebuffer"] == {"width_pixels": 1920, "height_pixels": 1046}
    assert receipt["external_preflight_evidence"]["sha256"] == EXPECTED_SHA256
    assert receipt["source_screenshot"]["sha256"] == EXPECTED_SHA256
    assert receipt["recovery"]["original_failure"] == "LIVE_SERVER_LOG_HASH_LOCK_FAILURE"
    assert receipt["recovery"]["live_log_hashing_repair_commit"] == "d73d35424b599366d151c02cc3bafbd94fb3b237"
    assert receipt["recovery"]["original_preflight_verified_utc_reconstructed"] is False
    assert {path: file_hash(path) for path in before} == before


def test_wrong_image_hash_fails_without_receipt(recovery_tmp_path: Path) -> None:
    client, server, baseline, canonical, _ = make_fixture(recovery_tmp_path)
    altered = bytearray(canonical.read_bytes())
    altered[-1] ^= 1
    canonical.write_bytes(altered)
    result = run_recovery(client, server, baseline)
    assert result.returncode != 0
    assert "Canonical preflight image SHA-256 mismatch" in result.stdout + result.stderr
    assert not receipt_path(client).exists()


def test_wrong_dimensions_fail_without_receipt(recovery_tmp_path: Path) -> None:
    client, server, baseline, canonical, source = make_fixture(recovery_tmp_path)
    wrong = minimal_png(640, 360, b"wrong-dimensions")
    canonical.write_bytes(wrong)
    source.write_bytes(wrong)
    result = run_recovery(
        client,
        server,
        baseline,
        expected_hash=hashlib.sha256(wrong).hexdigest(),
        expected_size=len(wrong),
    )
    assert result.returncode != 0
    assert "dimensions are not 1920x1046" in result.stdout + result.stderr
    assert not receipt_path(client).exists()


def test_existing_receipt_fails_create_only(recovery_tmp_path: Path) -> None:
    client, server, baseline, _, _ = make_fixture(recovery_tmp_path)
    receipt_path(client).write_text("{}\n", encoding="utf-8")
    result = run_recovery(client, server, baseline)
    assert result.returncode != 0
    assert "Create-only preflight receipt already exists" in result.stdout + result.stderr
    assert receipt_path(client).read_text(encoding="utf-8") == "{}\n"


def test_unprovable_partial_execution_fails_without_receipt(recovery_tmp_path: Path) -> None:
    client, server, baseline, _, source = make_fixture(recovery_tmp_path)
    source.unlink()
    result = run_recovery(client, server, baseline)
    assert result.returncode != 0
    assert "Expected exactly one exact-hash source screenshot; observed 0" in result.stdout + result.stderr
    assert not receipt_path(client).exists()
