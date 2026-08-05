from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[1]
FINALIZER = REPO / "scripts/person_c/finalize-e-refit-calibration-v0-4-attempt-02.ps1"
MODULE = REPO / "scripts/person_c/ERefitCalibrationAttempt02Authority.psm1"
MANIFEST = REPO / "docs/status/person_c_to_person_e_calibration_images_v0_4_attempt_02_v0_1/session_manifest.json"
SERVER_LOG = Path(r"C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\server\logs\latest.log")
LAYOUT_ID = "layout_01"
EPISODE_ID = 12711
SEED = 202608041701
RECEIPT_ID = "e_refit_calibration_v0_4_attempt_02_layout_01"


def ps_quote(value: Path | str) -> str:
    return str(value).replace("'", "''")


def extracted_chronology_functions() -> str:
    names = [
        "Find-UniqueAttempt02LogEvent",
        "Get-Attempt02LineSeconds",
        "Get-Attempt02OffsetSeconds",
        "New-Attempt02SemanticRepresentation",
        "Get-Attempt02SemanticEvent",
        "Get-Attempt02LayoutChronology",
    ]
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


def run_powershell(command: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
        cwd=REPO,
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
    )


def base_lines() -> list[str]:
    return [
        "[01:39:48] [Server thread/INFO]: [MineOcclude] /start requested: layout=layout_01 ep=12711 seed=202608041701 v=0.0 q=0.0 ticks=20 warmup=12000",
        "[01:39:48] [Server thread/INFO]: [MineOcclude] loaded immutable noise schedule (20 draws) from .\\mineocclude_schedules\\episode_12711.jsonl",
        "[01:39:48] [Server thread/INFO]: [MineOcclude] episode 12711 armed (layout=layout_01, 12000 warmup + 20 record ticks, v=0.0, q=0.0, seed=202608041701, rng=immutable_numpy_schedule)",
        "[01:39:48] [Server thread/INFO]: Armed episode 12711 (layout_01, scene NORMAL, warmup 12000t, record 20t, hiddenTarget 0)",
        "[01:40:01] [Server thread/INFO]: [MineOcclude/target] target status: valid=true required=true count=1 layout=layout_01 episode=12711 lifecycle=READY problems=NONE",
        "[01:40:01] [Server thread/INFO]: target status: valid=true required=true count=1 layout=layout_01 episode=12711 lifecycle=READY problems=NONE",
        "[01:40:09] [Server thread/INFO]: [MineOcclude/observation] wrote read-only geometry receipt .\\mineocclude_observations\\e_refit_calibration_v0_4_attempt_02_layout_01.json",
        "[01:40:09] [Server thread/INFO]: Wrote observation-only geometry receipt: .\\mineocclude_observations\\e_refit_calibration_v0_4_attempt_02_layout_01.json",
        "[01:40:25] [Server thread/INFO]: [MineOcclude] episode 12711 aborted during warmup",
        "[01:40:30] [Server thread/INFO]: Stopping server",
    ]


def run_fixture(lines: list[str]) -> subprocess.CompletedProcess[str]:
    lines_json = json.dumps(lines, separators=(",", ":"))
    command = (
        f"Import-Module -Force -Name '{ps_quote(MODULE)}'; "
        + extracted_chronology_functions()
        + f"$lines = [string[]](ConvertFrom-Json '{ps_quote(lines_json)}'); "
        f"$chronology = Get-Attempt02LayoutChronology -Lines $lines -LayoutId '{LAYOUT_ID}' "
        f"-EpisodeId {EPISODE_ID} -Seed ([int64]{SEED}) -ReceiptId '{RECEIPT_ID}' "
        "-PreviousAbortIndex -1 -ServerStopIndex ($lines.Count - 1); "
        "$chronology | ConvertTo-Json -Depth 8 -Compress"
    )
    return run_powershell(command)


def test_informational_and_console_duplicates_pass_as_one_semantic_event() -> None:
    result = run_fixture(base_lines())
    assert result.returncode == 0, result.stdout + result.stderr
    chronology = json.loads(result.stdout)
    assert chronology["ArmToTargetSeconds"] == 13
    assert chronology["Armed"]["RepresentationCount"] == 2
    assert chronology["TargetStatus"]["RepresentationCount"] == 2
    assert chronology["Receipt"]["RepresentationCount"] == 2
    assert chronology["DuplicateRepresentationCount"] == 3


@pytest.mark.parametrize("duplicate_kind", ["command", "receipt"])
def test_genuinely_separate_duplicate_events_fail(duplicate_kind: str) -> None:
    lines = base_lines()
    if duplicate_kind == "command":
        lines.insert(
            1,
            "[01:39:49] [Server thread/INFO]: [MineOcclude] /start requested: layout=layout_01 ep=12711 seed=202608041701 v=0.0 q=0.0 ticks=20 warmup=12000",
        )
        expected = "start command must occur exactly once by semantic identity; observed 2"
    else:
        abort_index = next(index for index, line in enumerate(lines) if "aborted during warmup" in line)
        lines.insert(
            abort_index,
            "[01:40:10] [Server thread/INFO]: [MineOcclude/observation] wrote read-only geometry receipt .\\mineocclude_observations\\e_refit_calibration_v0_4_attempt_02_layout_01.json",
        )
        expected = "geometry receipt must occur exactly once by semantic identity; observed 2"
    result = run_fixture(lines)
    assert result.returncode != 0
    assert expected in result.stdout + result.stderr


def test_all_six_existing_layout_chronologies_pass_read_only() -> None:
    before = (SERVER_LOG.stat().st_size, SERVER_LOG.stat().st_mtime_ns, hashlib.sha256(SERVER_LOG.read_bytes()).hexdigest())
    command = (
        f"Import-Module -Force -Name '{ps_quote(MODULE)}'; "
        + extracted_chronology_functions()
        + f"$lines = [string[]]@(Get-Content -LiteralPath '{ps_quote(SERVER_LOG)}'); "
        "$serverStop = Find-UniqueAttempt02LogEvent $lines 'Stopping server' 'clean server stop'; "
        f"$manifest = Get-Content -Raw -LiteralPath '{ps_quote(MANIFEST)}' | ConvertFrom-Json; "
        "$previousAbort = -1; $results = [System.Collections.Generic.List[object]]::new(); "
        "foreach ($layout in @($manifest.layouts)) { "
        "$layoutId = [string]$layout.layout_id; $episodeId = [int]$layout.episode_id; "
        "$receiptId = \"e_refit_calibration_v0_4_attempt_02_$layoutId\"; "
        "$chronology = Get-Attempt02LayoutChronology -Lines $lines -LayoutId $layoutId -EpisodeId $episodeId "
        "-Seed ([int64]$layout.seed) -ReceiptId $receiptId -PreviousAbortIndex $previousAbort -ServerStopIndex $serverStop.Index; "
        "[void]$results.Add([pscustomobject]@{ layout_id = $layoutId; episode_id = $episodeId; "
        "arm_to_target_seconds = $chronology.ArmToTargetSeconds; duplicates = $chronology.DuplicateRepresentationCount }); "
        "$previousAbort = $chronology.Abort.LastIndex; }; "
        "[object[]]$results.ToArray() | ConvertTo-Json -Compress"
    )
    result = run_powershell(command)
    assert result.returncode == 0, result.stdout + result.stderr
    rows = json.loads(result.stdout)
    assert [row["episode_id"] for row in rows] == list(range(12711, 12717))
    assert [row["arm_to_target_seconds"] for row in rows] == [13, 12, 12, 12, 11, 11]
    assert [row["duplicates"] for row in rows] == [3, 3, 3, 3, 3, 3]
    after = (SERVER_LOG.stat().st_size, SERVER_LOG.stat().st_mtime_ns, hashlib.sha256(SERVER_LOG.read_bytes()).hexdigest())
    assert after == before


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        ("missing_target", "layout_01 targetstatus is absent"),
        ("wrong_order", "layout_01 server chronology failed"),
        ("short_target_delay", "layout_01 targetstatus occurred less than ten seconds after arming"),
        ("failed_target", "layout_01 targetstatus did not pass"),
        ("wrong_receipt", "layout_01 receipt belongs to another layout or episode"),
        ("missing_abort", "layout_01 warmup abort is absent"),
    ],
)
def test_invalid_chronologies_fail_closed(mutation: str, expected: str) -> None:
    lines = base_lines()
    if mutation == "missing_target":
        lines = [line for line in lines if "target status:" not in line]
    elif mutation == "wrong_order":
        receipts = [line for line in lines if "geometry receipt" in line]
        lines = [line for line in lines if "geometry receipt" not in line]
        arm_console_index = next(index for index, line in enumerate(lines) if "Armed episode" in line)
        lines[arm_console_index + 1 : arm_console_index + 1] = receipts
    elif mutation == "short_target_delay":
        lines = [line.replace("[01:40:01]", "[01:39:55]") if "target status:" in line else line for line in lines]
    elif mutation == "failed_target":
        lines = [line.replace("valid=true", "valid=false") if "target status:" in line else line for line in lines]
    elif mutation == "wrong_receipt":
        lines = [line.replace("layout_01.json", "layout_02.json") if "geometry receipt" in line else line for line in lines]
    elif mutation == "missing_abort":
        lines = [line for line in lines if "aborted during warmup" not in line]
    result = run_fixture(lines)
    assert result.returncode != 0
    assert expected in result.stdout + result.stderr


def test_recording_start_fails_closed() -> None:
    lines = base_lines()
    receipt_index = next(index for index, line in enumerate(lines) if "wrote read-only geometry receipt" in line)
    lines.insert(receipt_index, "[01:40:05] [Server thread/INFO]: [MineOcclude] episode 12711 recording started")
    result = run_fixture(lines)
    assert result.returncode != 0
    assert "layout_01 entered recording" in result.stdout + result.stderr
