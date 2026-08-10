from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = (
    ROOT / "docs/status/integration/exploratory_large_scale_no_wall_scaling_best_k_v0_1"
)
RUNTIME = Path(
    "/mnt/sagemaker-nvme/mineocclude_large_scale_no_wall_scaling_best_k_v0_1"
)
CAMPAIGN_SHA = "1605f4738840ea531e73fdcee19536d55652a1a05ddef704304adcb1bc41cdd6"
STUDY_SHA = "08d77261f70a3d7e554ce6f8fe4a565fa09591ae793a87efd60e4a742c016502"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(8 << 20):
            digest.update(block)
    return digest.hexdigest()


def load(path: Path):
    return json.loads(path.read_text())


def ledger_rows():
    return [
        json.loads(line)
        for line in (PACKAGE / "p2_capture_ledger.jsonl").read_text().splitlines()
    ]


def test_p1_locks_remain_byte_identical():
    assert sha256(PACKAGE / "capture_campaign.json") == CAMPAIGN_SHA
    assert sha256(PACKAGE / "study_design.json") == STUDY_SHA
    assert load(PACKAGE / "capture_campaign.lock.json")["source_sha256"] == CAMPAIGN_SHA
    assert load(PACKAGE / "study_design.lock.json")["source_sha256"] == STUDY_SHA


def test_live_ledger_hash_chain_is_valid():
    previous = None
    for row in ledger_rows():
        assert row["previous_record_sha256"] == previous
        claimed = row["record_sha256"]
        body = dict(row)
        body.pop("record_sha256")
        encoded = json.dumps(
            body, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
        assert hashlib.sha256(encoded).hexdigest() == claimed
        previous = claimed


def test_exactly_locked_stage_a_was_accepted_and_no_later_stage():
    campaign = load(PACKAGE / "capture_campaign.json")
    expected = {
        row["trajectory_spec_id"]
        for row in campaign["campaign_order"]
        if row["stage"] == "A"
    }
    accepted_rows = [
        row
        for row in ledger_rows()
        if row["record_type"] == "ATTEMPT_CLASSIFIED"
        and row.get("classification") == "ACCEPTED"
    ]
    assert len(accepted_rows) == 12
    assert {row["trajectory_spec_id"] for row in accepted_rows} == expected
    assert len({row["trajectory_spec_id"] for row in accepted_rows}) == 12
    assert not [
        row for row in ledger_rows() if row["trajectory_spec_id"] not in expected
    ]


def test_all_accepted_attempts_are_durable_and_balanced():
    manifest = load(PACKAGE / "p2_pilot_capture_manifest.json")
    assert manifest["status"] == "PASS"
    assert manifest["accepted_spec_count"] == 12
    assert manifest["rejected_attempt_count"] == 0
    assert manifest["accepted_per_layout"] == {
        f"L{index:02d}": 2 for index in range(1, 7)
    }
    assert all(
        row["durable_prefix"].startswith("s3://") for row in manifest["attempts"]
    )


def test_every_capture_has_exact_f60_and_fully_visible_schedule():
    manifest = load(PACKAGE / "p2_pilot_capture_manifest.json")
    assert all(row["source_frame_count"] == 60 for row in manifest["attempts"])
    assert all(row["eligible_rows"] == 60 for row in manifest["attempts"])
    for row in manifest["attempts"]:
        frame_map = Path(row["processed_summary"]["frame_map"])
        assert frame_map.is_file()


def test_raw_full_frames_are_not_frozen():
    manifest = load(PACKAGE / "p2_pilot_capture_manifest.json")
    for row in manifest["attempts"]:
        attempt_root = Path(row["processed_summary"]["client_dir"]).parents[1]
        frames = sorted((attempt_root / "raw/client/frames").glob("*.png"))
        hashes = [sha256(path) for path in frames]
        assert len(frames) == 60
        assert len(set(hashes)) >= 58
        assert hashes[0] != hashes[-1]


def test_local_checksum_manifests_reconcile():
    manifest = load(PACKAGE / "p2_pilot_capture_manifest.json")
    for row in manifest["attempts"]:
        root = Path(row["processed_summary"]["client_dir"]).parents[1]
        checksums = load(root / "sha256_manifest.json")
        assert checksums["file_count"] == len(checksums["files"])
        for item in checksums["files"]:
            path = root / item["path"]
            assert path.stat().st_size == item["byte_size"]
            assert sha256(path) == item["sha256"]


def test_profile_and_direction_coverage():
    audit = load(PACKAGE / "p2_stage_a_profile_audit.json")
    assert audit["profiles_executed"] == [
        "EARLY_CONSTANT",
        "FAST_TRANSIT",
        "LATE_ONSET",
        "PAUSE_RESUME",
        "TWO_SPEED",
    ]
    assert audit["directions_executed"] == ["LEFT_TO_RIGHT", "RIGHT_TO_LEFT"]


def test_all_four_acknowledgement_gaps_are_resolved():
    receipt = load(PACKAGE / "p2_acknowledgement_resolution.json")
    assert receipt["remaining_gaps"] == []
    assert set(receipt) >= {
        "client_fov",
        "spec_start_position",
        "piecewise_motion",
        "capture_drain",
    }


def test_no_activation_probe_or_decoder_outputs_exist():
    forbidden = []
    for path in RUNTIME.rglob("*"):
        lowered = path.name.lower()
        if path.is_file() and (
            "activation" in lowered
            or "hidden_state" in lowered
            or lowered.startswith("r2")
            or "probe_result" in lowered
        ):
            forbidden.append(path)
    assert forbidden == []
    receipt = load(PACKAGE / "p2_receipt.json")
    assert receipt["fresh_activations_extracted"] == 0
    assert receipt["fresh_r2_computed"] is False
    assert receipt["p3_started"] is False


def test_no_retries_or_blocked_specs_and_one_crash_recovery():
    rows = ledger_rows()
    assert not [
        row
        for row in rows
        if row["record_type"] == "ATTEMPT_CLASSIFIED"
        and row.get("classification") == "REJECTED_WITH_REASON"
    ]
    accepted = [
        row
        for row in rows
        if row["record_type"] == "ATTEMPT_CLASSIFIED"
        and row.get("classification") == "ACCEPTED"
    ]
    assert Counter(row["attempt_number"] for row in accepted) == {1: 12}
    assert sum(bool(row.get("crash_recovered")) for row in accepted) == 1
