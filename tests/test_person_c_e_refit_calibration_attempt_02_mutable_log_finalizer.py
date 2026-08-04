from __future__ import annotations

import hashlib
import os
import subprocess
import tempfile
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
FINALIZER = REPO / "scripts/person_c/finalize-e-refit-calibration-v0-4-attempt-02.ps1"
MODULE = REPO / "scripts/person_c/ERefitCalibrationAttempt02Authority.psm1"
BASELINE_COMMIT = "d73d35424b599366d151c02cc3bafbd94fb3b237"


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


def assert_identity_command(path: Path, size: int, sha256: str) -> str:
    return (
        f"Import-Module -Force -Name '{ps_quote(MODULE)}'; "
        "$identity = [pscustomobject]@{ "
        f"path = '{ps_quote(path)}'; size_bytes = [int64]{size}; sha256 = '{sha256}' "
        "}; "
        "Assert-ERefitAttempt02Identity -Identity $identity -Label 'Immutable archive'"
    )


def test_mutable_latest_logs_are_recorded_only_not_attempt_01_immutable_evidence() -> None:
    finalizer = FINALIZER.read_text(encoding="utf-8")
    assert (
        "foreach ($row in @($attempt01.geometry_receipts) + @($attempt01.raw_screenshots))"
        in finalizer
    )
    assert (
        "@($attempt01.geometry_receipts) + @($attempt01.raw_screenshots) + @($attempt01.logs)"
        not in finalizer
    )
    assert "$attempt01MutableLatestLogIdentitiesRecordedOnly = @($attempt01.logs)" in finalizer
    assert "mutable_latest_log_paths_are_preserved_artifacts = $false" in finalizer
    assert "current_latest_logs_classification = 'ATTEMPT_02_SESSION_EVIDENCE_ONLY'" in finalizer


def test_existing_immutable_attempt_01_archive_is_validated_and_alteration_fails() -> None:
    finalizer = FINALIZER.read_text(encoding="utf-8")
    assert "if (Test-Path -LiteralPath $mapping.ArchivePath -PathType Leaf)" in finalizer
    assert (
        "Assert-ERefitAttempt02Identity -Identity $archiveIdentity -Label "
        "'Immutable Attempt 01 archived log evidence'"
    ) in finalizer

    descriptor, name = tempfile.mkstemp(prefix=".attempt02_immutable_archive_", dir=REPO)
    os.close(descriptor)
    archive = Path(name)
    try:
        original = b"immutable historical Attempt 01 archive\n"
        archive.write_bytes(original)
        expected_hash = hashlib.sha256(original).hexdigest()
        accepted = run_powershell(assert_identity_command(archive, len(original), expected_hash))
        assert accepted.returncode == 0, accepted.stdout + accepted.stderr

        archive.write_bytes(original + b"altered")
        rejected = run_powershell(assert_identity_command(archive, len(original), expected_hash))
        assert rejected.returncode != 0
        assert "Immutable archive identity drift" in rejected.stdout + rejected.stderr
    finally:
        archive.unlink(missing_ok=True)


def test_attempt_02_current_logs_are_copied_to_create_only_archives_and_hash_bound() -> None:
    finalizer = FINALIZER.read_text(encoding="utf-8")
    assert "Copy-ERefitAttempt02CreateOnly $serverLogPath $serverLogArchive" in finalizer
    assert "Copy-ERefitAttempt02CreateOnly $clientLogPath $clientLogArchive" in finalizer
    assert (
        "Assert-ERefitAttempt02Condition ((Get-ERefitAttempt02Sha256 $serverLogPath) -ceq "
        "(Get-ERefitAttempt02Sha256 $serverLogArchive)) 'Server log archive hash mismatch'"
    ) in finalizer
    assert (
        "Assert-ERefitAttempt02Condition ((Get-ERefitAttempt02Sha256 $clientLogPath) -ceq "
        "(Get-ERefitAttempt02Sha256 $clientLogArchive)) 'Client log archive hash mismatch'"
    ) in finalizer
    assert "server_log = Get-ERefitAttempt02Identity $serverLogArchive" in finalizer
    assert "client_log = Get-ERefitAttempt02Identity $clientLogArchive" in finalizer
    assert "$createOnlyPaths = @(\n        $serverLogArchive, $clientLogArchive" in finalizer


def test_original_chronology_framebuffer_and_runtime_checks_remain_enforced() -> None:
    current = FINALIZER.read_text(encoding="utf-8")
    baseline_result = subprocess.run(
        ["git", "show", f"{BASELINE_COMMIT}:scripts/person_c/finalize-e-refit-calibration-v0-4-attempt-02.ps1"],
        cwd=REPO,
        text=True,
        capture_output=True,
        timeout=30,
        check=True,
    )
    baseline = baseline_result.stdout
    protected_needles = [
        "'Installed server JAR drift'",
        "'Installed client JAR drift'",
        "'Client options drift'",
        "'Runtime server.properties is not the accepted Minecraft auto-expansion of the strict authority'",
        "'Mandatory framebuffer preflight receipt is not 1920x1046'",
        "'accepted FOV 70.0 client event'",
        "'Attempt 02 server session must contain exactly six armed episodes'",
        '"$layoutId targetstatus occurred less than ten seconds after arming"',
        '"$layoutId requires exactly one in-window F2 screenshot after receipt confirmation and before abort"',
        '"$layoutId entered recording"',
        '"$layoutId receipt schema/ID mismatch"',
        '"$layoutId target status failed"',
        '"$layoutId floor mismatch"',
        '"$layoutId wall mismatch"',
        '"$layoutId marker count mismatch"',
        "Assert-ERefitAttempt02LayoutScreenshotSet",
        "'Exactly six layout F2 events must occur from first arm through sixth warmup abort; the preflight F2 is excluded'",
    ]
    for needle in protected_needles:
        assert needle in baseline
        assert needle in current

    chronology_start = "    $serverLines = @(Get-Content -LiteralPath $serverLogPath)"
    chronology_end = "    $confirmation = Read-Host"
    baseline_block = baseline[
        baseline.index(chronology_start) : baseline.index(chronology_end)
    ]
    current_block = current[current.index(chronology_start) : current.index(chronology_end)]
    assert current_block == baseline_block
