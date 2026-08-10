from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = (
    ROOT / "docs/status/integration/exploratory_large_scale_no_wall_scaling_best_k_v0_1"
)
SCRIPT = ROOT / "scripts/run_large_scale_no_wall_campaign.py"
SPEC = importlib.util.spec_from_file_location("p3_results", SCRIPT)
assert SPEC and SPEC.loader
p3 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(p3)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(8 << 20):
            digest.update(chunk)
    return digest.hexdigest()


@pytest.fixture(scope="module")
def authority():
    return p3.CampaignAuthority(p3.DEFAULT_CAMPAIGN)


@pytest.fixture(scope="module")
def ledger():
    return p3.AppendOnlyLedger(p3.DEFAULT_LEDGER)


@pytest.fixture(scope="module")
def accepted(ledger):
    return p3.accepted_classifications(ledger)


def test_p1_locks_and_p2_runtime_semantics_are_unchanged():
    assert sha256(PACKAGE / "capture_campaign.json") == p3.CAMPAIGN_SHA256
    assert sha256(PACKAGE / "study_design.json") == p3.STUDY_SHA256
    changed_fabric = subprocess.run(
        [
            "git",
            "diff",
            "--name-only",
            "5b37ce2da10129497c36e78187d3a1cdd9821a08",
            "--",
            "fabric",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert changed_fabric == ""


def test_ledger_has_120_unique_locked_acceptances_and_one_preserved_rejection(
    authority, ledger, accepted
):
    rejected = p3.rejected_classifications(ledger)
    assert len(accepted) == len({row["trajectory_spec_id"] for row in accepted}) == 120
    assert {row["trajectory_spec_id"] for row in accepted} == set(authority.specs)
    assert all(
        row["spec_hash"] == authority.specs[row["trajectory_spec_id"]]["spec_hash"]
        for row in ledger.records
    )
    assert len(rejected) == 1
    assert rejected[0]["failure_reason_codes"] == ["CAPTURE_VALIDATION_FAILED"]
    assert rejected[0]["attempt_number"] == 1
    retry_id = rejected[0]["trajectory_spec_id"]
    assert (
        next(row for row in accepted if row["trajectory_spec_id"] == retry_id)[
            "attempt_number"
        ]
        == 2
    )


def test_stage_boundaries_and_final_balance_are_exact(authority, accepted):
    counts = Counter(authority.stage_for(row["trajectory_spec_id"]) for row in accepted)
    assert counts == {"A": 12, "B": 36, "C": 36, "D": 36}
    specs = [authority.specs[row["trajectory_spec_id"]] for row in accepted]
    assert Counter(row["layout_id"] for row in specs) == {
        f"L{index:02d}": 20 for index in range(1, 7)
    }
    assert set(
        Counter((row["layout_id"], row["direction"]) for row in specs).values()
    ) == {10}
    assert set(
        Counter(
            (row["layout_id"], row["direction"], row["profile_family"]) for row in specs
        ).values()
    ) == {2}


def test_every_accepted_capture_is_f60_and_automatically_classified(ledger, accepted):
    accepted_attempts = {
        (row["trajectory_spec_id"], int(row["attempt_number"])) for row in accepted
    }
    validation_transitions = {
        (row["trajectory_spec_id"], int(row["attempt_number"]))
        for row in ledger.records
        if row["record_type"] == "STATE_TRANSITION"
        and row.get("to_state") == "VALIDATE_CAPTURE"
    }
    assert accepted_attempts <= validation_transitions
    for row in accepted:
        root = Path(row["local_output_root"])
        package = json.loads((root / "capture_package_v0_1.json").read_text())
        assert package["source_frame_count"] == 60
        assert package["eligible_rows"] == 60
        assert package["processed_summary"]["accepted"] is True
        assert package["processed_summary"]["n_frames"] == 60


def test_all_local_accepted_manifests_reconcile_and_frames_change(accepted):
    for row in accepted:
        root = Path(row["local_output_root"])
        manifest = json.loads((root / "sha256_manifest.json").read_text())
        for item in manifest["files"]:
            path = root / item["path"]
            assert path.stat().st_size == item["byte_size"]
            assert sha256(path) == item["sha256"]
        frames = sorted((root / "raw/client/frames").glob("*.png"))
        assert len(frames) == 60
        assert sha256(frames[0]) != sha256(frames[-1])


def test_compact_p3_receipts_report_capture_only_success():
    receipt = json.loads((PACKAGE / "p3_receipt.json").read_text())
    qa = json.loads((PACKAGE / "p3_capture_profile_qa.json").read_text())
    attempts = json.loads((PACKAGE / "p3_attempt_summary.json").read_text())
    assert receipt["status"] == "PASS" and receipt["total_accepted"] == 120
    assert receipt["fresh_activations_extracted"] == 0
    assert receipt["fresh_r2_computed"] is False
    assert receipt["p4_started"] is False
    assert attempts["blocked_specs"] == 0
    assert attempts["manual_scientific_commands_per_trajectory"] == 0
    assert all(
        qa[key]
        for key in (
            "all_source_frames_60",
            "all_eligible_rows_60",
            "all_profile_schedules_pass",
            "all_camera_authority_pass",
            "all_no_wall_pass",
        )
    )


def test_s3_inventory_has_exact_120_manifests_and_no_later_phase_outputs():
    listing = subprocess.run(
        ["aws", "s3", "ls", p3.DEFAULT_S3_PREFIX, "--recursive"],
        check=True,
        capture_output=True,
        text=True,
        timeout=120,
    ).stdout.splitlines()
    keys = [
        line.split(maxsplit=3)[3]
        for line in listing
        if len(line.split(maxsplit=3)) == 4
    ]
    assert sum(key.endswith("sha256_manifest.json") for key in keys) == 120
    forbidden_parts = {
        "activation",
        "activations",
        "hidden_states",
        "features",
        "probe",
        "probes",
        "r2_results",
        "final_split",
    }
    assert not any(forbidden_parts.intersection(key.lower().split("/")) for key in keys)


def test_protected_remote_refs_remain_unchanged():
    output = subprocess.run(
        [
            "git",
            "ls-remote",
            "origin",
            "refs/heads/exploration/visible-position-resolution-v0-1",
            "refs/heads/integration/mvp-final",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    refs = {line.split()[1]: line.split()[0] for line in output.splitlines()}
    assert (
        refs["refs/heads/exploration/visible-position-resolution-v0-1"]
        == p3.PREDECESSOR_SHA
    )
    assert refs["refs/heads/integration/mvp-final"] == p3.FROZEN_MVP_SHA
