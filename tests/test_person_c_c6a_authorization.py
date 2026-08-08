from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
AUTHORIZATION = ROOT / "docs/status/person_c_c6a_e_refit_authorization_v0_1/c6a_execution_authorization.json"
SCHEDULE_MANIFEST = ROOT / "configs/collection/person_c_c6a_v0_1/schedule_set_manifest.json"
CAPTURE_MANIFEST = ROOT / "docs/status/person_c_c6a_capture_manifest_v0_2/c6a_capture_manifest.json"
EXPECTED_GEOMETRY_SHA256 = "34495d650d6a8c62b00a916796c90389b48f80d8f20a23eac93207758e993f5d"
EXPECTED_COMMAND = (
    'powershell.exe -NoProfile -ExecutionPolicy Bypass -File '
    '"C:\\Users\\lollo\\MineOcclude-Person-C-C1-C6A\\scripts\\person_c\\run-c6a-after-e-refit.ps1" '
    "-ExecuteScientificCapture"
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_authorization_binds_successful_e_refit_and_exact_command() -> None:
    record = json.loads(AUTHORIZATION.read_text(encoding="utf-8"))
    assert record["status"] == "AUTHORIZED"
    assert record["person_e"]["commit"] == "c46d838b5a277e71a39090900f9e8ca814b743a7"
    assert record["person_e"]["package"]["sha256"] == "f5a90bb97d0f54e754cfa11c971532d8d2e29cbe6ce0151dfeb17faae61a17bc"
    assert record["person_e"]["handoff"]["sha256"] == "0937dcc6335927a1c724e8e3f1510be94b76ff91e3583c10d59d10ec60fb38ca"
    assert record["accepted_geometry"]["sha256"] == EXPECTED_GEOMETRY_SHA256
    assert [row["layout_id"] for row in record["certification"]["layout_results"]] == [f"layout_{index:02d}" for index in range(1, 7)]
    assert all(row["pass"] for row in record["certification"]["layout_results"])
    assert record["c6a_execution_authorized"] is True
    assert record["unresolved_blockers"] == []
    assert record["execution_command"] == EXPECTED_COMMAND


def test_existing_schedule_and_capture_manifests_remain_bound() -> None:
    record = json.loads(AUTHORIZATION.read_text(encoding="utf-8"))
    schedule = json.loads(SCHEDULE_MANIFEST.read_text(encoding="utf-8"))
    capture = json.loads(CAPTURE_MANIFEST.read_text(encoding="utf-8"))
    assert _sha256(SCHEDULE_MANIFEST) == record["c6a_schedule_manifest"]["sha256"]
    assert _sha256(CAPTURE_MANIFEST) == record["c6a_capture_manifest"]["sha256"]
    assert schedule["schedule_set_sha256"] == capture["schedule_set_sha256"] == record["c6a_schedule_manifest"]["schedule_set_sha256"]
    assert len(schedule["schedules"]) == len(capture["episodes"]) == 66
    capture_by_episode = {row["episode_id"]: row for row in capture["episodes"]}
    for row in schedule["schedules"]:
        schedule_path = ROOT / row["path"]
        assert schedule_path.stat().st_size == row["size_bytes"]
        assert _sha256(schedule_path) == row["sha256"]
        capture_row = capture_by_episode[row["episode_id"]]
        assert capture_row["noise_schedule"]["path"] == row["path"]
        assert capture_row["noise_schedule"]["sha256"] == row["sha256"]


def test_authorized_command_preflight_passes_without_c6a_execution() -> None:
    record = json.loads(AUTHORIZATION.read_text(encoding="utf-8"))
    wrapper = (ROOT / "scripts/person_c/run-c6a-after-e-refit.ps1").read_text(
        encoding="utf-8"
    )
    assert record["c6a_execution_authorized"] is True
    assert record["execution_command"] == EXPECTED_COMMAND
    assert record["unresolved_blockers"] == []
    assert "-PreflightOnly" in wrapper
    assert "C6A_AUTHORIZATION_PREFLIGHT_PASS=True" in wrapper
