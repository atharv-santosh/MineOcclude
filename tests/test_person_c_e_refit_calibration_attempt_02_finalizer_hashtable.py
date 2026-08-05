from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
FINALIZER = REPO / "scripts/person_c/finalize-e-refit-calibration-v0-4-attempt-02.ps1"
MODULE = REPO / "scripts/person_c/ERefitCalibrationAttempt02Authority.psm1"
MANIFEST = REPO / "docs/status/person_c_to_person_e_calibration_images_v0_4_attempt_02_v0_1/session_manifest.json"
BASELINE_COMMIT = "1588cc373401e74369b8d767bae816199bafd187"
ATTEMPT_NAME = "e_refit_calibration_v0_4_attempt_02"
CLIENT_ROOT = Path(r"C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\client")
SERVER_ROOT = Path(r"C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\server")


def ps_quote(value: Path | str) -> str:
    return str(value).replace("'", "''")


def run_powershell(command: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
        cwd=REPO,
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
    )


def extracted_functions(*names: str) -> str:
    quoted_names = ", ".join(f"'{name}'" for name in names)
    return (
        "$tokens = $null; $errors = $null; "
        f"$ast = [System.Management.Automation.Language.Parser]::ParseFile('{ps_quote(FINALIZER)}', "
        "[ref]$tokens, [ref]$errors); "
        f"foreach ($functionName in @({quoted_names})) {{ "
        "$function = $ast.Find({ param($node) "
        "$node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and "
        "$node.Name -ceq $functionName }, $true); "
        "if ($null -eq $function) { throw \"Function absent: $functionName\" }; "
        "Invoke-Expression $function.Extent.Text; "
        "}; "
    )


def file_identity(path: Path) -> tuple[int, int, str]:
    stat = path.stat()
    return stat.st_size, stat.st_mtime_ns, hashlib.sha256(path.read_bytes()).hexdigest()


def relevant_runtime_evidence(manifest: dict, preflight: dict) -> list[Path]:
    paths = {
        Path(preflight["external_preflight_evidence"]["path"]),
        Path(preflight["source_screenshot"]["path"]),
        Path(preflight["client_options"]["path"]),
        Path(preflight["server_session_prefix"]["path"]),
        Path(preflight["client_session_prefix"]["path"]),
        Path(manifest["preflight"]["receipt_path"]),
        SERVER_ROOT / "server.properties",
    }
    paths.update(Path(row["runtime_paths"]["geometry_receipt"]) for row in manifest["layouts"])
    client_log = (CLIENT_ROOT / "logs" / "latest.log").read_text(encoding="utf-8", errors="strict")
    screenshot_names = re.findall(r"Saved screenshot as ([^\\/\s]+\.png)", client_log)
    paths.update(CLIENT_ROOT / "screenshots" / name for name in screenshot_names)
    return sorted(paths, key=lambda path: str(path).casefold())


def test_exact_matches_automatic_variable_collision_is_fixed_with_typed_list() -> None:
    finalizer = FINALIZER.read_text(encoding="utf-8")
    assert "$matches += [pscustomobject]" not in finalizer
    assert "$eventMatches = [System.Collections.Generic.List[object]]::new()" in finalizer
    assert "[void]$eventMatches.Add([pscustomobject]" in finalizer
    assert "+=" not in finalizer
    assert "@($attempt01.geometry_receipts) + @($attempt01.raw_screenshots)" not in finalizer

    command = (
        f"Import-Module -Force -Name '{ps_quote(MODULE)}'; "
        + extracted_functions("Find-UniqueAttempt02LogEvent")
        + "$lines = [string[]]@('unrelated', '[MineOcclude] exact event'); "
        "$event = Find-UniqueAttempt02LogEvent -Lines $lines -Pattern '\\[MineOcclude\\] exact event' -Label 'typed fixture'; "
        "[pscustomobject]@{ index = $event.Index; line = $event.Line; type = $event.GetType().FullName } | ConvertTo-Json -Compress"
    )
    result = run_powershell(command)
    assert result.returncode == 0, result.stdout + result.stderr
    event = json.loads(result.stdout)
    assert event == {
        "index": 1,
        "line": "[MineOcclude] exact event",
        "type": "System.Management.Automation.PSCustomObject",
    }


def test_malformed_duplicate_log_event_still_fails_closed() -> None:
    command = (
        f"Import-Module -Force -Name '{ps_quote(MODULE)}'; "
        + extracted_functions("Find-UniqueAttempt02LogEvent")
        + "$lines = [string[]]@('[MineOcclude] duplicate', '[MineOcclude] duplicate'); "
        "Find-UniqueAttempt02LogEvent -Lines $lines -Pattern '\\[MineOcclude\\] duplicate' -Label 'malformed fixture'"
    )
    result = run_powershell(command)
    assert result.returncode != 0
    assert "malformed fixture must occur exactly once; observed 2" in result.stdout + result.stderr


def test_existing_preflight_receipt_is_accepted_without_modifying_evidence() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    finalizer = FINALIZER.read_text(encoding="utf-8")
    before = hashlib.sha256(FINALIZER.read_bytes()).hexdigest()
    assert manifest["preflight"]["mandatory_before_any_episode"] is True
    assert manifest["preflight"]["required_framebuffer"] == {
        "width_pixels": 1920,
        "height_pixels": 1046,
    }
    receipt_read = finalizer.index("$preflight = Get-Content -Raw -LiteralPath $preflightReceiptPath")
    acceptance = finalizer.index("Mandatory framebuffer preflight did not pass for Attempt 02")
    first_write = finalizer.index("Copy-ERefitAttempt02CreateOnly")
    assert receipt_read < acceptance < first_write
    assert hashlib.sha256(FINALIZER.read_bytes()).hexdigest() == before


def test_all_six_layouts_and_original_validation_contracts_remain_required() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert len(manifest["layouts"]) == 6
    finalizer = FINALIZER.read_text(encoding="utf-8")
    baseline = subprocess.run(
        ["git", "show", f"{BASELINE_COMMIT}:scripts/person_c/finalize-e-refit-calibration-v0-4-attempt-02.ps1"],
        cwd=REPO,
        text=True,
        capture_output=True,
        timeout=30,
        check=True,
    ).stdout
    protected_needles = [
        "'Attempt 02 does not contain all six layouts'",
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
        "'All six distinct 1920x1046 Attempt 02 screenshots were not validated'",
        "'Exactly six layout F2 events must occur from first arm through sixth warmup abort; the preflight F2 is excluded'",
    ]
    for needle in protected_needles:
        assert needle in baseline
        assert needle in finalizer

    preflight_path = Path(manifest["preflight"]["external_evidence_path"])
    command = (
        f"Import-Module -Force -Name '{ps_quote(MODULE)}'; "
        "$rows = [object[]]@(1..5 | ForEach-Object { [pscustomobject]@{ layout_id = ('layout_{0:d2}' -f $_); path = 'absent.png' } }); "
        f"Assert-ERefitAttempt02LayoutScreenshotSet -Layouts $rows -PreflightEvidencePath '{ps_quote(preflight_path)}'"
    )
    result = run_powershell(command)
    assert result.returncode != 0
    assert "Attempt 02 requires exactly six layout screenshots" in result.stdout + result.stderr


def test_partial_create_only_output_is_rejected_before_any_write() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    server_evidence = SERVER_ROOT / f"{ATTEMPT_NAME}_v0_1"
    client_evidence = CLIENT_ROOT / f"{ATTEMPT_NAME}_v0_1"
    output_paths = [
        server_evidence / f"{ATTEMPT_NAME}_server_latest.log",
        client_evidence / f"{ATTEMPT_NAME}_client_latest.log",
        server_evidence / f"{ATTEMPT_NAME}_operator_attestation.json",
        server_evidence / f"{ATTEMPT_NAME}_screenshot_inventory.json",
        server_evidence / f"{ATTEMPT_NAME}_geometry_receipt_inventory.json",
        server_evidence / f"{ATTEMPT_NAME}_e_image_point_annotation_template.json",
        server_evidence / f"{ATTEMPT_NAME}_e_independent_validation_pair_template.json",
        server_evidence / f"{ATTEMPT_NAME}_person_c_to_e_calibration_handoff.json",
        server_evidence / f"{ATTEMPT_NAME}_finalization_result.json",
        *(Path(row["runtime_paths"]["canonical_screenshot"]) for row in manifest["layouts"]),
    ]
    assert len(output_paths) == 15
    command = (
        f"Import-Module -Force -Name '{ps_quote(MODULE)}'; "
        + extracted_functions("Assert-Attempt02CreateOnlyPathsAbsent")
        + "$paths = [System.Collections.Generic.List[string]]::new(); "
        f"[void]$paths.Add('{ps_quote(FINALIZER)}'); "
        "Assert-Attempt02CreateOnlyPathsAbsent -Paths $paths"
    )
    result = run_powershell(command)
    assert result.returncode != 0
    assert "Create-only Attempt 02 output already exists" in result.stdout + result.stderr

    finalizer = FINALIZER.read_text(encoding="utf-8")
    precheck = finalizer.index("Assert-Attempt02CreateOnlyPathsAbsent -Paths $createOnlyPaths")
    attestation = finalizer.index("$confirmation = Read-Host")
    first_copy = finalizer.index("Copy-ERefitAttempt02CreateOnly $serverLogPath $serverLogArchive")
    assert precheck < attestation < first_copy
