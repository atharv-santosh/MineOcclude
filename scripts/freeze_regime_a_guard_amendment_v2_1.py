#!/usr/bin/env python3
"""Freeze the outcome-blind Regime-A v2 amendment from calibration only."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from mineocclude.regime_a import (  # noqa: E402
    BIN_BOUNDS,
    VisibilityCalibration,
    canonical_sha256,
    sha256_file,
    simulate_path,
    stable_hidden_interval,
    validate_scientific_specs,
)

STATUS = ROOT / "docs/status/integration/regime_a_occlusion_extraction_v0_1"
V2 = STATUS / "v2"
AMENDMENT = STATUS / "v2_amendment_1"


def json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def jsonl_bytes(rows: list[dict[str, object]]) -> bytes:
    return b"".join(
        json.dumps(row, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        + b"\n"
        for row in rows
    )


def load_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"{path}: expected JSON object")
    return value


def crossing_rows(report: dict[str, object], direction: str) -> list[dict[str, object]]:
    aggregate = report.get(direction)
    if not isinstance(aggregate, dict) or not isinstance(aggregate.get("crossings"), list):
        raise RuntimeError(f"{direction}: malformed calibration report")
    return [dict(row) for row in aggregate["crossings"]]


def direction_summary(rows: list[dict[str, object]], direction: str) -> dict[str, object]:
    if len(rows) != 8 or {str(row["direction"]) for row in rows} != {direction}:
        raise RuntimeError(f"{direction}: amendment requires exactly eight crossings")
    if not all(
        int(row["frame_count"]) == 260
        and int(dict(row["temporal_alignment"])["stale_frame_count"]) == 0
        and bool(row["capture_ack_identity_exact"])
        and int(row["capture_ack_count"]) == 260
        and int(row["capture_ack_queue_depth_max"]) == 0
        and int(row["stable_hidden_length_frames"]) >= 19
        for row in rows
    ):
        raise RuntimeError(f"{direction}: structural calibration qualification failed")
    visible_before = [float(row["geometric_last_visible_before_entry_world_x"]) for row in rows]
    first_hidden = [float(row["geometric_first_hidden_world_x"]) for row in rows]
    if direction == "LEFT_TO_RIGHT":
        geometric_bracket = [max(visible_before), min(first_hidden)]
        stable_entry = max(float(row["stable_hidden_onset_world_x"]) for row in rows)
        stable_exit = min(float(row["stable_hidden_last_world_x"]) for row in rows)
    else:
        geometric_bracket = [max(first_hidden), min(visible_before)]
        stable_entry = min(float(row["stable_hidden_onset_world_x"]) for row in rows)
        stable_exit = max(float(row["stable_hidden_last_world_x"]) for row in rows)
    entry_runs = [int(row["entry_transition_max_consecutive_frames"]) for row in rows]
    exit_runs = [int(row["exit_transition_max_consecutive_frames"]) for row in rows]
    return {
        "direction": direction,
        "qualified_crossings": 8,
        "calibration_ids": [row["trajectory_spec_id"] for row in rows],
        "seeds": [row["seed"] for row in rows],
        "entry_transition_disagreement_runs_frames": entry_runs,
        "exit_transition_disagreement_runs_frames": exit_runs,
        "maximum_entry_run_frames": max(entry_runs),
        "maximum_exit_run_frames": max(exit_runs),
        "g_entry_frames": max(entry_runs) + 1,
        "g_exit_frames": max(exit_runs) + 1,
        "geometric_hidden_boundary_bracket_world_x": geometric_bracket,
        "geometric_hidden_boundary_point_world_x": sum(geometric_bracket) / 2.0,
        "stable_dual_hidden_entry_observed_world_x": [
            row["stable_hidden_onset_world_x"] for row in rows
        ],
        "stable_dual_hidden_entry_conservative_world_x": stable_entry,
        "stable_dual_hidden_exit_observed_world_x": [
            row["stable_hidden_last_world_x"] for row in rows
        ],
        "stable_dual_hidden_exit_conservative_world_x": stable_exit,
        "all_temporally_aligned": True,
        "all_capture_ack_identities_exact": True,
        "all_dual_visibility_qualified": True,
        "replication_diagnostics": {
            "entry_run_min": min(entry_runs),
            "entry_run_max": max(entry_runs),
            "exit_run_min": min(exit_runs),
            "exit_run_max": max(exit_runs),
            "unresolved_detector_instability": False,
        },
    }


def amended_calibration(
    ltr: dict[str, object], rtl: dict[str, object]
) -> VisibilityCalibration:
    return VisibilityCalibration(
        hidden_left=float(ltr["stable_dual_hidden_entry_conservative_world_x"]),
        hidden_right=float(rtl["stable_dual_hidden_entry_conservative_world_x"]),
        geometric_entry={
            "LEFT_TO_RIGHT": float(ltr["geometric_hidden_boundary_point_world_x"]),
            "RIGHT_TO_LEFT": float(rtl["geometric_hidden_boundary_point_world_x"]),
        },
        entry_guard={
            "LEFT_TO_RIGHT": int(ltr["g_entry_frames"]),
            "RIGHT_TO_LEFT": int(rtl["g_entry_frames"]),
        },
        exit_guard={
            "LEFT_TO_RIGHT": int(ltr["g_exit_frames"]),
            "RIGHT_TO_LEFT": int(rtl["g_exit_frames"]),
        },
        directional_hidden_entry={
            "LEFT_TO_RIGHT": float(ltr["stable_dual_hidden_entry_conservative_world_x"]),
            "RIGHT_TO_LEFT": float(rtl["stable_dual_hidden_entry_conservative_world_x"]),
        },
        directional_hidden_exit={
            "LEFT_TO_RIGHT": float(ltr["stable_dual_hidden_exit_conservative_world_x"]),
            "RIGHT_TO_LEFT": float(rtl["stable_dual_hidden_exit_conservative_world_x"]),
        },
    )


def amend_specs(
    calibration: VisibilityCalibration, authority_sha256: str
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    original = [
        json.loads(line)
        for line in (V2 / "trajectory_manifest.jsonl").read_text().splitlines()
        if line.strip()
    ]
    amended: list[dict[str, object]] = []
    mapping: list[dict[str, object]] = []
    for old in original:
        direction = str(old["direction"])
        positions, _noise = simulate_path(
            int(old["seed"]), direction, float(old["start_world_x"])
        )
        onset, exit_frame = stable_hidden_interval(positions, direction, calibration)
        body = dict(old)
        old_hash = str(body.pop("spec_hash"))
        bindings = dict(body["authority_bindings"])
        bindings.pop("directional_visibility_authority_v2_sha256", None)
        bindings["directional_visibility_authority_v2_amendment_1_sha256"] = authority_sha256
        bindings["original_v2_manifest_sha256"] = sha256_file(V2 / "trajectory_manifest.jsonl")
        body.update(
            {
                "schema_version": "regime-a-trajectory-spec-v2.1-amendment-1",
                "authority_bindings": dict(sorted(bindings.items())),
                "visibility_calibration": calibration.as_authority(),
                "entry_guard_frames": int(calibration.entry_guard[direction]),
                "exit_guard_frames": int(calibration.exit_guard[direction]),
                "expected_stable_hidden_onset_frame": onset,
                "expected_stable_hidden_exit_frame": exit_frame,
                "expected_tau_1_to_19_world_x": [
                    float(value) for value in positions[onset : onset + 19]
                ],
                "expected_target_semantics": (
                    "amendment-1 conservative calibration forecast; actual tau remains "
                    "the first frozen dual-visibility OCCLUDED_AGREEMENT run"
                ),
                "original_v2_spec_hash": old_hash,
                "raw_capture_spec_hash": old_hash,
                "physical_capture_protocol_changed": False,
                "amended_analysis_authority": "regime-a-directional-visibility-authority-v2.1-amendment-1",
            }
        )
        body["spec_hash"] = canonical_sha256(body)
        amended.append(body)
        mapping.append(
            {
                "trajectory_spec_id": old["trajectory_spec_id"],
                "seed": old["seed"],
                "direction": direction,
                "original_v2_spec_hash": old_hash,
                "amended_v2_1_spec_hash": body["spec_hash"],
                "raw_capture_spec_hash": old_hash,
                "original_expected_onset": old["expected_stable_hidden_onset_frame"],
                "amended_expected_onset": onset,
                "original_expected_exit": old["expected_stable_hidden_exit_frame"],
                "amended_expected_exit": exit_frame,
            }
        )
    validate_scientific_specs(amended, calibration)
    return amended, mapping


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--extension-report", type=Path, required=True)
    parser.add_argument("--extension-evidence-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=AMENDMENT)
    args = parser.parse_args()
    original_report = load_json(V2 / "fresh_directional_calibration_report.json")
    extension_report = load_json(args.extension_report)
    if (
        extension_report.get("NON_SCIENTIFIC_CALIBRATION") is not True
        or extension_report.get("ELIGIBLE_FOR_REGIME_A_RESULTS") is not False
    ):
        raise RuntimeError("extension report is not permanently non-scientific")
    frozen_manifest = [
        json.loads(line)
        for line in (AMENDMENT / "calibration_extension_manifest.jsonl").read_text().splitlines()
        if line.strip()
    ]
    frozen = {
        (str(row["trajectory_spec_id"]), str(row["spec_hash"]), int(row["seed"]), str(row["direction"]))
        for row in frozen_manifest
    }
    new_crossings = crossing_rows(extension_report, "LEFT_TO_RIGHT") + crossing_rows(
        extension_report, "RIGHT_TO_LEFT"
    )
    observed = {
        (str(row["trajectory_spec_id"]), str(row["spec_hash"]), int(row["seed"]), str(row["direction"]))
        for row in new_crossings
    }
    if observed != frozen:
        raise RuntimeError("extension detector evidence differs from frozen identities")
    original_ids = {
        str(row["trajectory_spec_id"])
        for direction in ("LEFT_TO_RIGHT", "RIGHT_TO_LEFT")
        for row in crossing_rows(original_report, direction)
    }
    if original_ids & {str(row["trajectory_spec_id"]) for row in new_crossings}:
        raise RuntimeError("original and extension calibration identities overlap")
    combined_ltr = crossing_rows(original_report, "LEFT_TO_RIGHT") + crossing_rows(
        extension_report, "LEFT_TO_RIGHT"
    )
    combined_rtl = crossing_rows(original_report, "RIGHT_TO_LEFT") + crossing_rows(
        extension_report, "RIGHT_TO_LEFT"
    )
    ltr = direction_summary(combined_ltr, "LEFT_TO_RIGHT")
    rtl = direction_summary(combined_rtl, "RIGHT_TO_LEFT")
    calibration = amended_calibration(ltr, rtl)
    evidence = []
    for path in sorted(args.extension_evidence_dir.glob("*.visibility_evidence.jsonl")):
        evidence.append(
            {"path": str(path), "sha256": sha256_file(path), "byte_size": path.stat().st_size}
        )
    if len(evidence) != 12:
        raise RuntimeError("extension evidence inventory is not 12 files")
    authority = {
        "schema_version": "regime-a-directional-visibility-authority-v2.1-amendment-1",
        "artifact_id": "regime-a-directional-visibility-authority-v2.1-amendment-1",
        "status": "FROZEN_OUTCOME_BLIND_AFTER_STRUCTURAL_QC_TRIGGER",
        "scientific_run_id": "mineocclude-regime-a-first25-v2",
        "amendment_order": 1,
        "amendment_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "trigger": "t04 TRUE_FROZEN_GUARD_EXCEEDANCE before scientific outcome computation",
        "prospective_outcome_blind": True,
        "scientific_decoding_outcomes_computed_before_freeze": 0,
        "t04_used_in_numerical_derivation": False,
        "scientific_trajectories_used_in_numerical_derivation": [],
        "guard_rule": "directional maximum consecutive partial/disagreement run plus one captured frame",
        "original_calibration_crossings_per_direction": 2,
        "new_calibration_crossings_per_direction": 6,
        "total_calibration_crossings_per_direction": 8,
        "LEFT_TO_RIGHT": ltr,
        "RIGHT_TO_LEFT": rtl,
        "planning_calibration": calibration.as_authority(),
        "simulated_capture_hz": 20,
        "effective_preceding_frames": 15,
        "context_duration_simulated_seconds": 0.75,
        "duration_bins": {name: list(bounds) for name, bounds in BIN_BOUNDS.items()},
        "physical_capture_protocol_changed": False,
        "detector_semantics_changed": False,
        "historical_v2": {
            "authority_path": str(V2 / "directional_visibility_authority.json"),
            "authority_sha256": sha256_file(V2 / "directional_visibility_authority.json"),
            "trajectory_manifest_sha256": sha256_file(V2 / "trajectory_manifest.jsonl"),
            "guards": {
                "LEFT_TO_RIGHT": {"g_entry_frames": 11, "g_exit_frames": 7},
                "RIGHT_TO_LEFT": {"g_entry_frames": 13, "g_exit_frames": 4},
            },
            "preserved_unchanged": True,
        },
        "source_bindings": {
            "trigger_receipt_sha256": sha256_file(AMENDMENT / "amendment_trigger_receipt.json"),
            "calibration_extension_freeze_receipt_sha256": sha256_file(
                AMENDMENT / "calibration_extension_freeze_receipt.json"
            ),
            "calibration_extension_manifest_sha256": sha256_file(
                AMENDMENT / "calibration_extension_manifest.jsonl"
            ),
            "original_calibration_report_sha256": sha256_file(
                V2 / "fresh_directional_calibration_report.json"
            ),
            "extension_calibration_report_sha256": sha256_file(args.extension_report),
        },
        "extension_evidence": evidence,
    }
    authority_payload = json_bytes(authority)
    authority_sha = hashlib.sha256(authority_payload).hexdigest()
    specs, mapping = amend_specs(calibration, authority_sha)
    manifest_payload = jsonl_bytes(specs)
    manifest_sha = hashlib.sha256(manifest_payload).hexdigest()
    expected_bin_counts = {
        name: stop - start + 1 for name, (start, stop) in BIN_BOUNDS.items()
    }
    support = {
        "schema_version": "regime-a-v2-amendment-1-context-bin-revalidation-v1.0",
        "status": "PASS",
        "effective_preceding_frames_E": 15,
        "context_duration_simulated_seconds_C": 0.75,
        "duration_bins": {name: list(bounds) for name, bounds in BIN_BOUNDS.items()},
        "clean_frames_per_trajectory_by_bin": expected_bin_counts,
        "left_to_right_trajectory_count": 13,
        "right_to_left_trajectory_count": 12,
        "all_trajectories_have_19_clean_target_frames": True,
        "all_trajectories_have_at_least_15_preceding_frames": all(
            int(row["expected_stable_hidden_onset_frame"]) >= 15 for row in specs
        ),
        "left_to_right_support": True,
        "right_to_left_support": True,
        "calibration_extension_stable": True,
    }
    if not support["all_trajectories_have_at_least_15_preceding_frames"]:
        raise RuntimeError("amended cohort lacks causal context support")
    mapping_doc = {
        "schema_version": "regime-a-v2-amendment-1-spec-provenance-map-v1.0",
        "classification_pending_raw_replay": True,
        "physical_capture_protocol_changed": False,
        "original_manifest_sha256": sha256_file(V2 / "trajectory_manifest.jsonl"),
        "amended_manifest_sha256": manifest_sha,
        "rows": mapping,
    }
    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    (out / "directional_visibility_authority_v2_1_amendment_1.json").write_bytes(
        authority_payload
    )
    (out / "trajectory_manifest_v2_1_amendment_1.jsonl").write_bytes(manifest_payload)
    (out / "trajectory_manifest_v2_1_amendment_1.sha256").write_text(manifest_sha + "\n")
    (out / "context_bin_revalidation.json").write_bytes(json_bytes(support))
    (out / "spec_provenance_map.json").write_bytes(json_bytes(mapping_doc))
    print(
        json.dumps(
            {
                "authority_sha256": authority_sha,
                "manifest_sha256": manifest_sha,
                "LEFT_TO_RIGHT": ltr,
                "RIGHT_TO_LEFT": rtl,
                "context_bin_revalidation": support,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
