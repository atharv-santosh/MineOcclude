from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/run_large_scale_no_wall_campaign.py"
SPEC = importlib.util.spec_from_file_location("p2_campaign", SCRIPT)
assert SPEC and SPEC.loader
p2 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(p2)


@pytest.fixture(scope="module")
def authority():
    return p2.CampaignAuthority(p2.DEFAULT_CAMPAIGN)


def test_p1_locks_and_all_120_spec_hashes_validate(authority):
    assert len(authority.specs) == 120
    assert len({row["spec_hash"] for row in authority.specs.values()}) == 120


def test_stage_a_is_exact_locked_twelve_and_two_per_layout(authority):
    stage_a = authority.stage_specs("A")
    assert len(stage_a) == 12
    assert Counter(row["layout_id"] for row in stage_a) == {
        f"L{index:02d}": 2 for index in range(1, 7)
    }
    assert {row["profile_family"] for row in stage_a} == {
        "EARLY_CONSTANT",
        "LATE_ONSET",
        "FAST_TRANSIT",
        "PAUSE_RESUME",
        "TWO_SPEED",
    }
    assert {row["direction"] for row in stage_a} == {
        "LEFT_TO_RIGHT",
        "RIGHT_TO_LEFT",
    }


def test_stage_a_has_no_later_stage_member(authority):
    stage_a = {row["trajectory_spec_id"] for row in authority.stage_specs("A")}
    later = {
        row["trajectory_spec_id"]
        for stage in ("B", "C", "D")
        for row in authority.stage_specs(stage)
    }
    assert stage_a.isdisjoint(later)


def test_all_five_motion_profile_semantics_and_dense_ticks(authority):
    for spec in authority.specs.values():
        p2.validate_profile_semantics(spec)
        assert [p2.expected_speed(spec, tick)[0] for tick in range(60)]


def test_motion_schedule_document_is_identity_bound(authority):
    spec = authority.stage_specs("A")[4]
    document = p2.motion_schedule_document(spec)
    assert document["trajectory_spec_id"] == spec["trajectory_spec_id"]
    assert document["spec_hash"] == spec["spec_hash"]
    assert document["segments"] == spec["exact_speed_schedule"]
    assert document["expected_ticks"] == 60


def test_state_machine_contract_is_exactly_fifteen_states():
    frozen = p2.read_json(p2.PACKAGE / "state_machine_contract.json")
    assert tuple(row["state"] for row in frozen["states"]) == p2.STATES
    assert len(p2.STATES) == 15


def test_ledger_is_append_only_hash_chain_and_resume_skips_accepted(
    tmp_path, authority
):
    path = tmp_path / "ledger.jsonl"
    ledger = p2.AppendOnlyLedger(path)
    spec = authority.stage_specs("A")[0]
    ledger.append("SPEC_REGISTERED", spec, 1, episode_id=30000)
    ledger.append(
        "ATTEMPT_CLASSIFIED",
        spec,
        1,
        episode_id=30000,
        classification="ACCEPTED",
    )
    replay = p2.AppendOnlyLedger(path)
    assert replay.accepted_ids() == {spec["trajectory_spec_id"]}
    assert replay.attempts_for(spec["trajectory_spec_id"]) == 1
    lines = path.read_text().splitlines()
    assert len(lines) == 2
    assert (
        json.loads(lines[1])["previous_record_sha256"]
        == json.loads(lines[0])["record_sha256"]
    )


def test_ledger_detects_mutation(tmp_path, authority):
    path = tmp_path / "ledger.jsonl"
    ledger = p2.AppendOnlyLedger(path)
    spec = authority.stage_specs("A")[0]
    ledger.append("SPEC_REGISTERED", spec, 1, episode_id=30000)
    record = json.loads(path.read_text())
    record["episode_id"] = 999
    path.write_text(json.dumps(record) + "\n")
    with pytest.raises(p2.CampaignError, match="ledger hash mismatch"):
        p2.AppendOnlyLedger(path)


def test_crash_restart_increments_attempt_without_mutating_spec(tmp_path, authority):
    path = tmp_path / "ledger.jsonl"
    ledger = p2.AppendOnlyLedger(path)
    spec = authority.stage_specs("A")[0]
    ledger.append("SPEC_REGISTERED", spec, 1, episode_id=30000)
    replay = p2.AppendOnlyLedger(path)
    assert replay.attempts_for(spec["trajectory_spec_id"]) + 1 == 2
    assert replay.records[0]["spec_hash"] == spec["spec_hash"]


def test_rejected_retry_keeps_identical_scientific_identity(tmp_path, authority):
    ledger = p2.AppendOnlyLedger(tmp_path / "ledger.jsonl")
    spec = authority.stage_specs("A")[0]
    for attempt in (1, 2):
        ledger.append("SPEC_REGISTERED", spec, attempt, episode_id=30000 + attempt)
        ledger.append(
            "ATTEMPT_CLASSIFIED",
            spec,
            attempt,
            classification="REJECTED_WITH_REASON",
            failure_reason_codes=["PRECHECK_FAILED"],
        )
    assert ledger.attempts_for(spec["trajectory_spec_id"]) == 2
    assert {row["spec_hash"] for row in ledger.records} == {spec["spec_hash"]}


def test_max_attempts_is_three(authority):
    assert p2.MAX_ATTEMPTS == 3
    assert all(spec["maximum_attempts"] == 3 for spec in authority.specs.values())


def test_modified_campaign_is_refused(tmp_path):
    package = tmp_path / "package"
    package.mkdir()
    for name in (
        "capture_campaign.json",
        "capture_campaign.lock.json",
        "study_design.json",
        "study_design.lock.json",
    ):
        (package / name).write_bytes((p2.PACKAGE / name).read_bytes())
    campaign = json.loads((package / "capture_campaign.json").read_text())
    campaign["campaign_shape"]["trajectory_spec_count"] = 119
    (package / "capture_campaign.json").write_text(json.dumps(campaign))
    with pytest.raises(p2.CampaignError, match="capture campaign hash changed"):
        p2.CampaignAuthority(package / "capture_campaign.json")


def test_dry_run_passes_without_runtime_or_scientific_capture(authority):
    result = p2.dry_run(authority)
    assert result["status"] == "PASS"
    assert result["stage_a_count"] == 12
    assert result["stage_b_in_stage_a_invocation"] is False


def test_cli_dry_run_validates_locked_p3_cumulative_membership():
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--stage", "D", "--dry-run"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    receipt = json.loads(result.stdout)
    assert receipt["through_stage"] == "D"
    assert receipt["cumulative_count"] == 120
    assert receipt["per_layout"] == {f"L{index:02d}": 20 for index in range(1, 7)}


def test_write_json_new_never_overwrites(tmp_path):
    path = tmp_path / "immutable.json"
    p2.write_json_new(path, {"value": 1})
    with pytest.raises(FileExistsError):
        p2.write_json_new(path, {"value": 2})
    assert p2.read_json(path) == {"value": 1}
