#!/usr/bin/env python3
"""Seal the Regime-A guard-amendment trigger and prospective calibration set."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from mineocclude.regime_a import HashChainLedger, RegimeAError, sha256_file  # noqa: E402
from scripts.build_regime_a_calibration_v2_manifest import build  # noqa: E402

STATUS = ROOT / "docs/status/integration/regime_a_occlusion_extraction_v0_1"
V2 = STATUS / "v2"
AMENDMENT = STATUS / "v2_amendment_1"
SCIENTIFIC_RUNTIME = Path("/mnt/sagemaker-nvme/mineocclude-regime-a-first25-v2")
EXPECTED_HEAD = "419b14d55483bc223f9198fe3e662629c0d48cc8"
T04_ID = "regime_a_v2_t04"
T04_HASH = "b18794dc55774584fa496241e700421602c28617bc4ef8c1cac9240be5aee219"


def json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def jsonl_bytes(rows: list[dict[str, object]]) -> bytes:
    return b"".join(
        json.dumps(row, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        + b"\n"
        for row in rows
    )


def git(*args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(ROOT), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def scientific_state() -> dict[str, object]:
    ledger = HashChainLedger(SCIENTIFIC_RUNTIME / "progress_ledger.jsonl")
    latest: dict[str, str] = {}
    for row in ledger.records:
        latest[str(row["trajectory_spec_id"])] = str(row["state"])
    complete = sorted(ledger.complete_ids())
    expected = [f"regime_a_v2_t{index:02d}" for index in range(1, 4)]
    if complete != expected or latest.get(T04_ID) != "RUNNING":
        raise RegimeAError("scientific trigger ledger state changed")
    if set(latest) != {*expected, T04_ID}:
        raise RegimeAError("t05-t25 have scientific ledger state")
    partial = SCIENTIFIC_RUNTIME / "trajectories" / f".{T04_ID}.{T04_HASH[:16]}.partial"
    if not partial.is_dir():
        raise RegimeAError("t04 trigger partial is absent")
    finals = sorted(
        path.name
        for path in (SCIENTIFIC_RUNTIME / "trajectories").iterdir()
        if path.is_dir() and not path.name.startswith(".")
    )
    if finals != expected:
        raise RegimeAError("scientific final trajectory set changed")
    return {
        "durable_scientific_trajectory_ids": complete,
        "durable_scientific_count": len(complete),
        "t04_ledger_state": latest[T04_ID],
        "t04_partial_path": str(partial),
        "t04_partial_identity_sha256": sha256_file(partial / "partial_identity.json"),
        "t05_t25_executed": False,
    }


def build_extension() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    episode = 63005
    for direction in ("LEFT_TO_RIGHT", "RIGHT_TO_LEFT"):
        for replicate in range(3, 9):
            rows.append(build(direction, replicate, episode))
            episode += 1
    if len(rows) != 12:
        raise AssertionError("extension size drift")
    ids = {str(row["trajectory_spec_id"]) for row in rows}
    seeds = {int(row["seed"]) for row in rows}
    scientific = {
        int(json.loads(line)["seed"])
        for line in (V2 / "trajectory_manifest.jsonl").read_text().splitlines()
        if line.strip()
    }
    if len(ids) != 12 or len(seeds) != 12 or seeds & scientific:
        raise RegimeAError("calibration extension identities/seeds are not isolated")
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=AMENDMENT)
    args = parser.parse_args()
    if git("rev-parse", "HEAD") != EXPECTED_HEAD:
        raise RegimeAError("amendment trigger must bind the authorization-qualified HEAD")
    state = scientific_state()
    rows = build_extension()
    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    trigger = {
        "schema_version": "regime-a-guard-amendment-trigger-v2.1",
        "artifact_id": "regime-a-v2-amendment-1-trigger",
        "status": "SEALED_BEFORE_AUTHORITY_AMENDMENT",
        "scientific_run_id": "mineocclude-regime-a-first25-v2",
        "authorization_qualified_head": EXPECTED_HEAD,
        "scientific_manifest_sha256": sha256_file(V2 / "trajectory_manifest.jsonl"),
        "original_directional_visibility_authority_sha256": sha256_file(
            V2 / "directional_visibility_authority.json"
        ),
        **state,
        "trigger_trajectory_spec_id": T04_ID,
        "trigger_seed": 959353389228382266,
        "trigger_spec_hash": T04_HASH,
        "trigger_direction": "LEFT_TO_RIGHT",
        "trigger_classification": "TRUE_FROZEN_GUARD_EXCEEDANCE",
        "observed_entry_transition_run_frames": 12,
        "frozen_entry_guard_frames": 11,
        "scientific_decoding_outcomes_inspected": False,
        "scientific_decoding_outcomes_computed": 0,
        "collection_stopped_before_amendment": True,
        "t04_excluded_from_numerical_calibration_authority": True,
        "authority_amendment_applied": False,
    }
    manifest_payload = jsonl_bytes(rows)
    manifest_sha = hashlib.sha256(manifest_payload).hexdigest()
    freeze = {
        "schema_version": "regime-a-calibration-extension-freeze-v2.1",
        "artifact_id": "regime-a-v2-amendment-1-calibration-extension-freeze",
        "status": "FROZEN_BEFORE_CAPTURE",
        "NON_SCIENTIFIC_CALIBRATION": True,
        "ELIGIBLE_FOR_REGIME_A_RESULTS": False,
        "sample_size_frozen_before_capture": True,
        "new_crossing_count": 12,
        "new_left_to_right_count": 6,
        "new_right_to_left_count": 6,
        "combined_left_to_right_count": 8,
        "combined_right_to_left_count": 8,
        "replicates": {"LEFT_TO_RIGHT": [3, 4, 5, 6, 7, 8], "RIGHT_TO_LEFT": [3, 4, 5, 6, 7, 8]},
        "calibration_extension_manifest_sha256": manifest_sha,
        "original_calibration_report_sha256": sha256_file(V2 / "fresh_directional_calibration_report.json"),
        "original_authority_sha256": trigger["original_directional_visibility_authority_sha256"],
        "trigger_receipt_sha256": hashlib.sha256(json_bytes(trigger)).hexdigest(),
        "physical_protocol_unchanged": {
            "camera_authority": "layout_01_fixed_v0.4",
            "wall_authority": "layout_01_long_wall_v0.4",
            "speed_blocks_per_second": 1.5,
            "motion_noise_q": 0.05,
            "capture_hz": 20,
            "capture_protocol": "capture_ack_lockstep",
            "visibility_detector_changed": False,
            "motion_semantics_changed": False,
        },
        "t04_used_to_choose_ids_seeds_or_sample_size": False,
        "rows": [
            {
                "trajectory_spec_id": row["trajectory_spec_id"],
                "spec_hash": row["spec_hash"],
                "seed": row["seed"],
                "direction": row["direction"],
                "episode_id": row["episode_id"],
            }
            for row in rows
        ],
    }
    (out / "amendment_trigger_receipt.json").write_bytes(json_bytes(trigger))
    (out / "calibration_extension_manifest.jsonl").write_bytes(manifest_payload)
    (out / "calibration_extension_manifest.sha256").write_text(manifest_sha + "\n")
    (out / "calibration_extension_freeze_receipt.json").write_bytes(json_bytes(freeze))
    print(json.dumps({"trigger": trigger, "freeze": freeze}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RegimeAError, FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"REGIME_A_GUARD_AMENDMENT_FREEZE_REFUSAL: {exc}", file=sys.stderr)
        raise SystemExit(2)
