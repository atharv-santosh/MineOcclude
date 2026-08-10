#!/usr/bin/env python3
"""Finalize the repaired V2 capture and run the outcome-blind P4C audit.

This successor consumes capture/specification authority only.  It never imports
MineWorld, creates split assignments, extracts activations, or computes probes.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import subprocess
import sys
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path
from typing import Any, Callable

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from design_large_scale_no_wall_profiles_v2 import (  # noqa: E402
    DESIGN_SAFETY_TARGET,
    F,
    FROZEN_MAX_HIGH_FRACTION,
    MIN_TARGET_RANGE,
    MIN_TARGET_VARIANCE,
    PAIR_R_THRESHOLD,
    commands_for_spec,
    simulate_profile,
)

PACKAGE = (
    ROOT / "docs/status/integration/exploratory_large_scale_no_wall_scaling_best_k_v0_1"
)
RUNTIME_ROOT = Path(
    "/mnt/sagemaker-nvme/mineocclude_large_scale_no_wall_scaling_best_k_v0_1_v2"
)
S3_PREFIX = (
    "s3://sagemaker-us-east-1-323206973672/mineocclude/"
    "exploratory_large_scale_no_wall_scaling_best_k_v0_1/repaired_v2/"
)
P4B_HEAD = "cd3764ad9b11f763fcf7687d938b04a4de11c0ce"
SIMULATOR_TOLERANCE = 1e-12
EXPECTED_STAGE_COUNTS = {"A": 12, "B": 48, "C": 84, "D": 120}
PROTECTED_HASHES = {
    "capture_campaign.json": "1605f4738840ea531e73fdcee19536d55652a1a05ddef704304adcb1bc41cdd6",
    "capture_campaign.lock.json": "479471d468598d93d861767ffa83b3e0bd1c401dbd3310cfcb509ecf7ced22aa",
    "study_design.json": "08d77261f70a3d7e554ce6f8fe4a565fa09591ae793a87efd60e4a742c016502",
    "study_design.lock.json": "05b337e81ffea6c6d3bb3f92ca76b7774c980f9c462565f5c50a71ad9f629f41",
    "p4_receipt.json": "91642203ff2b4d4318d953e1d97b44ccf82049c257fe4d2e6025fd31519a942e",
    "p4a_receipt.json": "6e9b4edafb8df5da4a517bcf930dfdbb69998cd80a4cbc5708f5ef45e4b326f3",
    "p4b_receipt.json": "e8c3919cb9773cc08ff36638f0ea052985ef73a45131afc94a0414fde0acee65",
    "capture_campaign_v2.json": "adb1eb0611d9cf05d221db6d2040eb65f50a0d5fb4dab32f6bdd3d585484ef9f",
    "capture_campaign_v2.lock.json": "1acdc0fdd593c5f6f90f2d5dd2173f0d1db2199bff6e4741c3a3c019bec0b759",
}
OUTPUT_NAMES = (
    "cohort_capture_manifest_v2.json",
    "p4c_v2_pilot_runtime_qa.json",
    "p4c_capture_reconciliation_v2.json",
    "p4c_actual_profile_audit_v2.json",
    "accepted_cohort_v2.lock.json",
    "p4c_receipt.json",
)


class P4CError(RuntimeError):
    """Raised when actual V2 capture authority cannot pass a frozen gate."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise P4CError(message)


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"JSON authority is not an object: {path}")
    return value


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(8 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode(
        "utf-8"
    )


def write_json_new(path: Path, value: Any) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(path, flags, 0o644)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(json_bytes(value))
        stream.flush()
        os.fsync(stream.fileno())


def verify_protected_authority() -> None:
    for name, expected in PROTECTED_HASHES.items():
        actual = sha256_file(PACKAGE / name)
        require(actual == expected, f"protected authority changed: {name}")
    lock = read_json(PACKAGE / "capture_campaign_v2.lock.json")
    require(lock["status"] == "LOCKED", "V2 campaign is not locked")
    require(lock["old_capture_reuse_in_primary"] is False, "V1 reuse is enabled")


def verify_ledger(path: Path) -> list[dict[str, Any]]:
    rows = read_jsonl(path)
    previous = None
    for index, row in enumerate(rows):
        claimed = row.get("record_sha256")
        body = dict(row)
        body.pop("record_sha256", None)
        require(
            row.get("previous_record_sha256") == previous,
            f"ledger chain break: {index}",
        )
        require(canonical_sha256(body) == claimed, f"ledger hash mismatch: {index}")
        previous = claimed
    return rows


def pearson(left: np.ndarray, right: np.ndarray) -> float:
    require(len(left) == len(right), "Pearson inputs differ in length")
    require(
        np.isfinite(left).all() and np.isfinite(right).all(), "non-finite Pearson input"
    )
    require(
        float(np.var(left)) > 0 and float(np.var(right)) > 0,
        "zero-variance Pearson input",
    )
    return float(np.corrcoef(left, right)[0, 1])


def similarity_summary(
    records: list[dict[str, Any]],
    predicate: Callable[[dict[str, Any], dict[str, Any]], bool],
) -> dict[str, Any]:
    signed = np.asarray(
        [
            pearson(left["profile"], right["profile"])
            for left, right in combinations(records, 2)
            if predicate(left, right)
        ],
        dtype=np.float64,
    )
    require(signed.size > 0, "empty pairwise similarity stratum")
    absolute = np.abs(signed)
    high = int(np.count_nonzero(absolute >= PAIR_R_THRESHOLD))
    return {
        "pair_count": int(signed.size),
        "high_abs_r_ge_0_95_count": high,
        "high_abs_r_ge_0_95_proportion": float(high / signed.size),
        "minimum_signed_r": float(np.min(signed)),
        "maximum_signed_r": float(np.max(signed)),
        "mean_abs_r": float(np.mean(absolute)),
        "median_abs_r": float(np.median(absolute)),
        "p95_abs_r": float(np.quantile(absolute, 0.95, method="linear")),
        "maximum_abs_r": float(np.max(absolute)),
    }


def pooled_time_correlation(records: list[dict[str, Any]]) -> float:
    time = np.tile(np.arange(F, dtype=np.float64) / (F - 1), len(records))
    profile = np.concatenate([row["profile"] for row in records])
    return pearson(time, profile)


def stratified_time(records: list[dict[str, Any]], key: str) -> dict[str, float]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in records:
        groups[str(row[key])].append(row)
    return {name: pooled_time_correlation(groups[name]) for name in sorted(groups)}


def manifest_map(root: Path) -> tuple[dict[str, dict[str, Any]], str]:
    path = root / "sha256_manifest.json"
    manifest = read_json(path)
    rows = manifest["files"]
    require(manifest["file_count"] == len(rows), f"manifest count mismatch: {root}")
    mapped = {row["path"]: row for row in rows}
    require(len(mapped) == len(rows), f"manifest duplicate path: {root}")
    critical = (
        "attempt_metadata.json",
        "capture_package_v0_1.json",
        "capture_provenance.json",
        "frame_map.jsonl",
        "raw/client/raw_actions.jsonl",
        "raw/client/capture_complete.json",
        "raw/server/server_state.jsonl",
        "raw/server/finalization.json",
        "noise_schedule.jsonl",
        "motion_schedule.json",
    )
    for relative in critical:
        local = root / relative
        require(
            relative in mapped and local.is_file(),
            f"manifest missing {relative}: {root}",
        )
        require(
            local.stat().st_size == mapped[relative]["byte_size"],
            f"size mismatch: {local}",
        )
        require(
            sha256_file(local) == mapped[relative]["sha256"],
            f"checksum mismatch: {local}",
        )
    return mapped, sha256_file(path)


def _close(left: Any, right: Any, tolerance: float = 1e-9) -> bool:
    return math.isclose(float(left), float(right), rel_tol=0.0, abs_tol=tolerance)


def reconstruct() -> dict[str, Any]:
    verify_protected_authority()
    campaign = read_json(PACKAGE / "capture_campaign_v2.json")
    study = read_json(PACKAGE / "study_design.json")
    specs = {row["trajectory_spec_id"]: row for row in campaign["trajectory_specs"]}
    require(len(specs) == 120, "frozen V2 campaign does not contain 120 unique specs")
    ledger_path = PACKAGE / "p4c_capture_ledger_v2.jsonl"
    ledger = verify_ledger(ledger_path)
    accepted_rows = [
        row
        for row in ledger
        if row.get("record_type") == "ATTEMPT_CLASSIFIED"
        and row.get("classification") == "ACCEPTED"
    ]
    rejected = [
        row
        for row in ledger
        if row.get("record_type") == "ATTEMPT_CLASSIFIED"
        and row.get("classification") == "REJECTED_WITH_REASON"
    ]
    accepted = {row["trajectory_spec_id"]: row for row in accepted_rows}
    require(
        len(accepted_rows) == len(accepted) == 120,
        "accepted V2 cohort is not 120 unique specs",
    )
    require(
        set(accepted) == set(specs),
        "accepted V2 membership differs from frozen campaign",
    )

    stage_receipts = {}
    for stage, expected_count in EXPECTED_STAGE_COUNTS.items():
        receipt = read_json(
            PACKAGE / f"p4c_v2_stage_{stage.lower()}_durability_receipt.json"
        )
        require(receipt["status"] == "PASS", f"stage {stage} durability failed")
        require(
            receipt["cumulative_accepted"] == expected_count,
            f"stage {stage} count changed",
        )
        require(
            receipt["s3_prefix"] == S3_PREFIX, f"stage {stage} V2 namespace changed"
        )
        require(
            receipt["ledger_s3_roundtrip_verified"] is True,
            f"stage {stage} ledger not durable",
        )
        stage_receipts[stage] = receipt

    records = []
    for spec_id in sorted(specs):
        spec = specs[spec_id]
        accepted_row = accepted[spec_id]
        require(
            accepted_row["spec_hash"] == spec["spec_hash"],
            f"spec hash mismatch: {spec_id}",
        )
        attempt = int(accepted_row["attempt_number"])
        root = Path(accepted_row["local_output_root"])
        require(
            root.is_relative_to(RUNTIME_ROOT),
            f"accepted attempt outside V2 root: {spec_id}",
        )
        expected_root = RUNTIME_ROOT / "attempts" / spec_id / f"attempt_{attempt:02d}"
        require(root == expected_root, f"attempt path mismatch: {spec_id}")
        stage = next(
            row["stage"]
            for row in campaign["campaign_order"]
            if row["trajectory_spec_id"] == spec_id
        )
        expected_prefix = (
            S3_PREFIX.rstrip("/")
            + f"/stage_{stage.lower()}/attempts/{spec_id}/attempt_{attempt:02d}/"
        )
        require(
            accepted_row["durable_prefix"] == expected_prefix,
            f"durable prefix mismatch: {spec_id}",
        )
        require(
            accepted_row["durable_upload_status"] == "VERIFIED",
            f"not durable: {spec_id}",
        )
        mapped_manifest, manifest_sha = manifest_map(root)
        require(
            manifest_sha
            == next(
                row["manifest_sha256"]
                for row in ledger
                if row.get("record_type") == "DURABLE_UPLOAD"
                and row.get("trajectory_spec_id") == spec_id
                and int(row["attempt_number"]) == attempt
            ),
            f"ledger manifest mismatch: {spec_id}",
        )
        metadata = read_json(root / "attempt_metadata.json")
        provenance = read_json(root / "capture_provenance.json")
        package = read_json(root / "capture_package_v0_1.json")
        state = read_jsonl(root / "raw/server/server_state.jsonl")
        actions = read_jsonl(root / "raw/client/raw_actions.jsonl")
        frame_map = read_jsonl(root / "frame_map.jsonl")
        completion = read_json(root / "raw/client/capture_complete.json")
        finalization = read_json(root / "raw/server/finalization.json")
        frames = sorted((root / "raw/client/frames").glob("*.png"))
        require(
            metadata["exact_scientific_spec"] == spec,
            f"scientific spec changed: {spec_id}",
        )
        require(
            provenance["classification"] == "ACCEPTED",
            f"provenance not accepted: {spec_id}",
        )
        require(
            package["source_frame_count"] == F and package["eligible_rows"] == F,
            f"F != 60: {spec_id}",
        )
        require(
            len(state) == len(actions) == len(frame_map) == len(frames) == F,
            f"row/frame count != 60: {spec_id}",
        )
        require(
            [row["server_tick"] for row in state] == list(range(F)),
            f"server ticks not dense: {spec_id}",
        )
        require(
            [row["action_idx"] for row in actions] == list(range(F)),
            f"actions not dense: {spec_id}",
        )
        require(
            [row["model_frame_idx"] for row in frame_map] == list(range(F)),
            f"model rows not dense: {spec_id}",
        )
        require(
            completion["drained"]
            and completion["pending_writes"] == 0
            and completion["writer_errors"] == 0,
            f"capture not drained: {spec_id}",
        )
        require(
            finalization["state"] == "COMPLETED" and finalization["ticks"] == F,
            f"server not finalized: {spec_id}",
        )

        commands = np.asarray(commands_for_spec(spec), dtype=np.float64)
        expected_segments = []
        for tick in range(F):
            matches = [
                index
                for index, segment in enumerate(spec["exact_speed_schedule"])
                if segment["start_model_frame_idx"]
                <= tick
                < segment["stop_model_frame_idx_exclusive"]
            ]
            require(
                len(matches) == 1, f"schedule does not cover tick: {spec_id}:{tick}"
            )
            expected_segments.append(matches[0])
        require(
            all(
                _close(row["commanded_v"], commands[index], 1e-12)
                and int(row["motion_segment_index"]) == expected_segments[index]
                for index, row in enumerate(state)
            ),
            f"motion schedule mismatch: {spec_id}",
        )
        camera = spec["camera_viewpoint_authority"]
        feet_x, feet_y, feet_z = map(float, camera["canonical_feet_xyz_blocks"])
        camera_ok = all(
            _close(row["player_x"], feet_x, 1e-6)
            and _close(row["player_y"], feet_y + 1.62, 1e-6)
            and _close(row["player_z"], feet_z, 1e-6)
            and _close(row["player_yaw"], camera["yaw_degrees"], 1e-6)
            and _close(row["player_pitch"], camera["pitch_degrees"], 1e-6)
            for row in state
        ) and all(
            abs(float(row["camera_dx"])) <= 1e-4
            and abs(float(row["camera_dy"])) <= 1e-4
            for row in actions
        )
        no_wall_ok = all(
            row["scene"] == "NO_WALL" and bool(row["geometric_visible"])
            for row in state
        )
        require(
            camera_ok and no_wall_ok, f"camera/no-wall authority mismatch: {spec_id}"
        )
        actual = np.asarray([float(row["axis_pos"]) for row in state], dtype=np.float64)
        simulated, clamp_count = simulate_profile(spec, track_clamps=True)
        simulated = np.asarray(simulated, dtype=np.float64)
        errors = np.abs(actual - simulated)
        require(
            float(np.max(errors)) <= SIMULATOR_TOLERANCE,
            f"simulator/live mismatch: {spec_id}",
        )
        lower = float(spec["target_range"]["scalar_axis_min_blocks"])
        upper = float(spec["target_range"]["scalar_axis_max_blocks"])
        start = float(spec["start_position_authority"]["axis_position_blocks"])
        expected_end = float(
            spec["end_position_authority"]["expected_axis_position_blocks"]
        )
        require(lower <= start <= upper, f"start authority outside bounds: {spec_id}")
        require(
            _close(package["actual_start_axis"], start),
            f"actual start mismatch: {spec_id}",
        )
        require(
            _close(package["actual_end_axis"], actual[-1]),
            f"actual end mismatch: {spec_id}",
        )
        require(_close(actual[-1], expected_end), f"end authority mismatch: {spec_id}")
        require(
            float(np.min(actual)) >= lower and float(np.max(actual)) <= upper,
            f"bounds fail: {spec_id}",
        )
        require(
            float(np.ptp(actual)) >= MIN_TARGET_RANGE, f"target range fail: {spec_id}"
        )
        require(
            float(np.var(actual)) >= MIN_TARGET_VARIANCE,
            f"target variance fail: {spec_id}",
        )
        require(clamp_count == 0, f"planned/actual clamp: {spec_id}")
        records.append(
            {
                "trajectory_spec_id": spec_id,
                "spec_hash": spec["spec_hash"],
                "attempt_number": attempt,
                "episode_id": int(accepted_row["episode_id"]),
                "layout_id": spec["layout_id"],
                "direction": spec["direction"],
                "trajectory_shape_class": spec["trajectory_shape_class"],
                "profile_family": spec["profile_family"],
                "repeat_id": int(spec["repeat_id"]),
                "capture_seed": int(spec["capture_seed"]),
                "profile": actual,
                "simulated_profile": simulated,
                "absolute_error": errors,
                "target_range": float(np.ptp(actual)),
                "target_variance": float(np.var(actual)),
                "camera_authority_pass": camera_ok,
                "no_wall_pass": no_wall_ok,
                "local_attempt_root": str(root),
                "durable_prefix": expected_prefix,
                "server_state_path": "raw/server/server_state.jsonl",
                "raw_actions_path": "raw/client/raw_actions.jsonl",
                "frame_map_path": "frame_map.jsonl",
                "server_state_sha256": mapped_manifest["raw/server/server_state.jsonl"][
                    "sha256"
                ],
                "raw_actions_sha256": mapped_manifest["raw/client/raw_actions.jsonl"][
                    "sha256"
                ],
                "frame_map_sha256": mapped_manifest["frame_map.jsonl"]["sha256"],
                "attempt_manifest_sha256": manifest_sha,
                "capture_provenance_sha256": mapped_manifest["capture_provenance.json"][
                    "sha256"
                ],
            }
        )
    for row in rejected:
        spec = specs[row["trajectory_spec_id"]]
        root = Path(row["local_output_root"])
        require(root.is_relative_to(RUNTIME_ROOT), "rejected attempt outside V2 root")
        metadata = read_json(root / "attempt_metadata.json")
        require(
            metadata["exact_scientific_spec"] == spec
            and row["spec_hash"] == spec["spec_hash"],
            f"retry mutated frozen scientific spec: {row['trajectory_spec_id']}",
        )
    return {
        "campaign": campaign,
        "study": study,
        "ledger": ledger,
        "ledger_path": ledger_path,
        "accepted": accepted_rows,
        "rejected": rejected,
        "records": records,
        "stage_receipts": stage_receipts,
    }


def compute() -> dict[str, Any]:
    source = reconstruct()
    records = source["records"]
    per_layout = Counter(row["layout_id"] for row in records)
    per_direction = Counter(row["direction"] for row in records)
    per_shape = Counter(row["trajectory_shape_class"] for row in records)
    per_family = Counter(row["profile_family"] for row in records)
    per_layout_direction = Counter(
        (row["layout_id"], row["direction"]) for row in records
    )
    per_layout_shape = Counter(
        (row["layout_id"], row["trajectory_shape_class"]) for row in records
    )
    per_cell = Counter(
        (row["layout_id"], row["direction"], row["profile_family"]) for row in records
    )
    repeat_cells: dict[tuple[str, str, str], set[int]] = defaultdict(set)
    for row in records:
        repeat_cells[(row["layout_id"], row["direction"], row["profile_family"])].add(
            row["repeat_id"]
        )
    all_pairs = similarity_summary(records, lambda _left, _right: True)
    same_direction = similarity_summary(
        records, lambda left, right: left["direction"] == right["direction"]
    )
    opposite_direction = similarity_summary(
        records, lambda left, right: left["direction"] != right["direction"]
    )
    same_shape = similarity_summary(
        records,
        lambda left, right: left["trajectory_shape_class"]
        == right["trajectory_shape_class"],
    )
    different_shape = similarity_summary(
        records,
        lambda left, right: left["trajectory_shape_class"]
        != right["trajectory_shape_class"],
    )
    same_family = similarity_summary(
        records, lambda left, right: left["profile_family"] == right["profile_family"]
    )
    different_family = similarity_summary(
        records, lambda left, right: left["profile_family"] != right["profile_family"]
    )
    all_errors = np.concatenate([row["absolute_error"] for row in records])
    retry_immutable = all(
        row["trajectory_spec_id"] in {item["trajectory_spec_id"] for item in records}
        and row["spec_hash"]
        == next(
            item["spec_hash"]
            for item in records
            if item["trajectory_spec_id"] == row["trajectory_spec_id"]
        )
        and int(row["attempt_number"])
        < next(
            item["attempt_number"]
            for item in records
            if item["trajectory_spec_id"] == row["trajectory_spec_id"]
        )
        for row in source["rejected"]
    )
    aggregate_not_sole = (
        same_direction["high_abs_r_ge_0_95_proportion"] <= DESIGN_SAFETY_TARGET
        and different_shape["high_abs_r_ge_0_95_proportion"] <= DESIGN_SAFETY_TARGET
    )
    gates = {
        "exact_frozen_membership_120": len(records) == 120,
        "layout_balance": per_layout
        == Counter({f"L{index:02d}": 20 for index in range(1, 7)}),
        "direction_balance": per_direction
        == Counter({"LEFT_TO_RIGHT": 60, "RIGHT_TO_LEFT": 60})
        and set(per_layout_direction.values()) == {10},
        "shape_class_balance": len(per_shape) == 20
        and set(per_shape.values()) == {6}
        and len(per_layout_shape) == 120
        and set(per_layout_shape.values()) == {1},
        "reporting_stratum_balance": len(per_family) == 5
        and set(per_family.values()) == {24}
        and len(per_cell) == 60
        and set(per_cell.values()) == {2},
        "unique_repeats_specs_and_seeds": len(
            {row["trajectory_spec_id"] for row in records}
        )
        == 120
        and len({row["spec_hash"] for row in records}) == 120
        and len({row["capture_seed"] for row in records}) == 120
        and len(repeat_cells) == 60
        and all(repeats == {1, 2} for repeats in repeat_cells.values()),
        "start_end_and_target_bounds": True,
        "target_range": all(row["target_range"] >= MIN_TARGET_RANGE for row in records),
        "target_variance": all(
            row["target_variance"] >= MIN_TARGET_VARIANCE for row in records
        ),
        "motion_schedule_compliance": True,
        "camera_authority": all(row["camera_authority_pass"] for row in records),
        "no_wall_authority": all(row["no_wall_pass"] for row in records),
        "f_60": True,
        "retry_immutability": retry_immutable,
        "capture_validity": True,
        "raw_authority_durable": True,
        "simulator_live_equivalence": float(np.max(all_errors)) <= SIMULATOR_TOLERANCE,
        "overall_time_position": abs(pooled_time_correlation(records))
        <= DESIGN_SAFETY_TARGET,
        "profile_similarity_frozen_gate": all_pairs["high_abs_r_ge_0_95_proportion"]
        <= FROZEN_MAX_HIGH_FRACTION,
        "aggregate_cancellation_not_sole_pass": aggregate_not_sole,
    }
    require(all(gates.values()), f"actual V2 P4 gate failed: {gates}")
    profile_similarity = {
        "absolute_pearson_gate_with_signed_r_reported": True,
        "threshold_inclusive": PAIR_R_THRESHOLD,
        "frozen_maximum_fraction": FROZEN_MAX_HIGH_FRACTION,
        "design_safety_target": DESIGN_SAFETY_TARGET,
        "all_pairs": all_pairs,
        "same_direction": same_direction,
        "opposite_direction": opposite_direction,
        "same_shape_class": same_shape,
        "different_shape_class": different_shape,
        "same_reporting_family": same_family,
        "different_reporting_family": different_family,
    }
    audit = {
        "schema_version": "large-scale-no-wall-p4c-actual-profile-audit-v0.1",
        "status": "PASS",
        "phase": "P4C_REPAIRED_CAPTURE_AND_PRE_EXTRACTION_VALIDATION",
        "outcome_blind": True,
        "activation_or_probe_inputs_used": False,
        "train_test_assignments_created": False,
        "counts": {
            "accepted": len(records),
            "per_layout": dict(sorted(per_layout.items())),
            "per_direction": dict(sorted(per_direction.items())),
            "per_shape_class": dict(sorted(per_shape.items())),
            "per_reporting_stratum": dict(sorted(per_family.items())),
            "unique_spec_ids": len({row["trajectory_spec_id"] for row in records}),
            "unique_spec_hashes": len({row["spec_hash"] for row in records}),
        },
        "profile_similarity": profile_similarity,
        "time_position_correlation": {
            "normalized_time_definition": "model_frame_idx / 59 for indices 0..59",
            "overall": pooled_time_correlation(records),
            "by_direction": stratified_time(records, "direction"),
            "by_shape_class": stratified_time(records, "trajectory_shape_class"),
            "by_reporting_stratum": stratified_time(records, "profile_family"),
            "aggregate_cancellation_not_sole_pass": aggregate_not_sole,
        },
        "target_distribution": {
            "minimum_required_range_blocks": MIN_TARGET_RANGE,
            "observed_minimum_range_blocks": min(
                row["target_range"] for row in records
            ),
            "minimum_required_variance_blocks_squared": MIN_TARGET_VARIANCE,
            "observed_minimum_variance_blocks_squared": min(
                row["target_variance"] for row in records
            ),
            "planned_or_actual_unintended_clamp_count": 0,
        },
        "simulated_vs_actual_qa": {
            "trajectory_count": len(records),
            "row_count": len(all_errors),
            "tolerance_blocks": SIMULATOR_TOLERANCE,
            "maximum_absolute_error_blocks": float(np.max(all_errors)),
            "mean_absolute_error_blocks": float(np.mean(all_errors)),
            "p95_absolute_error_blocks": float(
                np.quantile(all_errors, 0.95, method="linear")
            ),
            "bounds_variance_similarity_or_acceptance_changed": False,
        },
        "component_gates": gates,
        "v2_profile_diversity_accepted": True,
        "trajectory_profile_confound_controlled": True,
        "safe_for_p5": True,
        "blocker": None,
    }
    pilot_ids = [
        row["trajectory_spec_id"] for row in source["campaign"]["campaign_order"][:12]
    ]
    pilot = [row for row in records if row["trajectory_spec_id"] in set(pilot_ids)]
    pilot_errors = np.concatenate([row["absolute_error"] for row in pilot])
    pilot_qa = {
        "schema_version": "large-scale-no-wall-p4c-v2-pilot-runtime-qa-v0.1",
        "status": "PASS",
        "planned": 12,
        "accepted": 12,
        "accepted_per_layout": dict(
            sorted(Counter(row["layout_id"] for row in pilot).items())
        ),
        "directions": sorted({row["direction"] for row in pilot}),
        "shape_classes": sorted({row["trajectory_shape_class"] for row in pilot}),
        "simulated_live_maximum_absolute_error_blocks": float(np.max(pilot_errors)),
        "simulated_live_mean_absolute_error_blocks": float(np.mean(pilot_errors)),
        "tolerance_blocks": SIMULATOR_TOLERANCE,
        "motion_breakpoints_dwells_velocity_segments_and_timing_match": True,
        "runtime_compatibility": "PASS",
        "scientific_profile_similarity_decision_from_pilot": False,
    }
    rejection_counts = Counter(
        reason
        for row in source["rejected"]
        for reason in row.get("failure_reason_codes", [])
    )
    stage_receipts = source["stage_receipts"]
    pilot_runtime = (
        stage_receipts["A"]["runtime_startup_seconds"]
        + stage_receipts["A"]["stage_total_elapsed_seconds"]
    )
    remaining_runtime = stage_receipts["B"]["runtime_startup_seconds"] + sum(
        stage_receipts[stage]["stage_total_elapsed_seconds"]
        for stage in ("B", "C", "D")
    )
    upload_overhead = sum(
        float(row.get("upload_elapsed_seconds", 0.0)) for row in source["accepted"]
    )
    gate_overhead = sum(
        float(row["s3_durability_gate_elapsed_seconds"])
        for row in stage_receipts.values()
    )
    reconciliation = {
        "schema_version": "large-scale-no-wall-p4c-capture-reconciliation-v0.1",
        "status": "PASS",
        "v1_captured_trajectories": 120,
        "v1_primary_status": "EXCLUDED_PROFILE_DIVERSITY_FAIL",
        "v2_captured_trajectories": 120,
        "v2_primary_status": "ACCEPTED_REPAIRED_PRIMARY_COHORT",
        "accepted": 120,
        "accepted_per_layout": dict(sorted(per_layout.items())),
        "unique_spec_ids": 120,
        "unique_spec_hashes": 120,
        "unplanned_accepted_specs": 0,
        "missing_locked_specs": 0,
        "total_attempts": len(source["accepted"]) + len(source["rejected"]),
        "rejected_attempts": len(source["rejected"]),
        "retry_count": len(source["rejected"]),
        "blocked_specs": 0,
        "maximum_attempt_used": max(
            int(row["attempt_number"])
            for row in source["accepted"] + source["rejected"]
        ),
        "rejection_reason_counts": dict(sorted(rejection_counts.items())),
        "source_frames_per_spec": F,
        "eligible_rows_f": F,
        "raw_authority_durable": True,
        "s3_prefix": S3_PREFIX,
        "stage_durability_receipts": {
            stage: receipt for stage, receipt in sorted(stage_receipts.items())
        },
        "resource_accounting_seconds": {
            "v2_capture_machine_runtime": pilot_runtime + remaining_runtime,
            "pilot_runtime": pilot_runtime,
            "remaining_108_runtime": remaining_runtime,
            "retry_overhead": sum(
                float(row.get("elapsed_seconds", 0.0)) for row in source["rejected"]
            ),
            "accepted_attempt_upload_overhead": upload_overhead,
            "durability_gate_overhead": gate_overhead,
            "s3_durability_overhead": upload_overhead + gate_overhead,
        },
        "operator_intervention_count": 0,
        "manual_scientific_commands_per_trajectory": 0,
    }
    lock_entries = []
    manifest_entries = []
    for row in records:
        common = {
            "trajectory_spec_id": row["trajectory_spec_id"],
            "spec_hash": row["spec_hash"],
            "accepted_attempt": row["attempt_number"],
            "episode_id": row["episode_id"],
            "layout_id": row["layout_id"],
            "direction": row["direction"],
            "trajectory_shape_class": row["trajectory_shape_class"],
            "reporting_stratum": row["profile_family"],
            "repeat_id": row["repeat_id"],
            "capture_seed": row["capture_seed"],
            "local_attempt_root": row["local_attempt_root"],
            "durable_prefix": row["durable_prefix"],
            "raw_server_state_reference": row["server_state_path"],
            "raw_actions_reference": row["raw_actions_path"],
            "frame_map_reference": row["frame_map_path"],
            "checksums": {
                "server_state_sha256": row["server_state_sha256"],
                "raw_actions_sha256": row["raw_actions_sha256"],
                "frame_map_sha256": row["frame_map_sha256"],
                "attempt_manifest_sha256": row["attempt_manifest_sha256"],
                "capture_provenance_sha256": row["capture_provenance_sha256"],
            },
        }
        manifest_entries.append(common)
        lock_entries.append(
            {
                **common,
                "target_authority": {
                    "source": "accepted authoritative raw/server/server_state.jsonl axis_pos",
                    "row_count": F,
                    "x_true_blocks": [float(value) for value in row["profile"]],
                    "x_true_blocks_canonical_sha256": canonical_sha256(
                        [float(value) for value in row["profile"]]
                    ),
                },
            }
        )
    manifest = {
        "schema_version": "large-scale-no-wall-cohort-capture-manifest-v0.2",
        "status": "PASS_DURABLE_V2",
        "campaign_version": "0.2",
        "entry_count": 120,
        "v1_entries_included": 0,
        "s3_prefix": S3_PREFIX,
        "accepted_specs": manifest_entries,
    }
    lock = {
        "schema_version": "large-scale-no-wall-accepted-cohort-v2-lock-v0.1",
        "status": "LOCKED_FOR_P5",
        "entry_count": 120,
        "campaign_version": "0.2",
        "source_campaign_sha256": PROTECTED_HASHES["capture_campaign_v2.json"],
        "source_ledger_sha256": sha256_file(source["ledger_path"]),
        "v1_entries_included": 0,
        "contains_train_test_assignments": False,
        "contains_model_activation_or_probe_outcomes": False,
        "entries": lock_entries,
    }
    return {
        "source": source,
        "audit": audit,
        "pilot": pilot_qa,
        "reconciliation": reconciliation,
        "manifest": manifest,
        "lock": lock,
    }


def load_accepted_cohort_v2(path: Path | None = None) -> dict[str, Any]:
    """Load only the repaired V2 cohort, refusing mixed or split-bearing input."""
    lock = read_json(path or PACKAGE / "accepted_cohort_v2.lock.json")
    require(
        lock["schema_version"] == "large-scale-no-wall-accepted-cohort-v2-lock-v0.1",
        "not a V2 cohort lock",
    )
    require(
        lock["entry_count"] == len(lock["entries"]) == 120, "V2 lock count mismatch"
    )
    require(lock["v1_entries_included"] == 0, "V1 entries present in V2 lock")
    require(
        lock["contains_train_test_assignments"] is False,
        "split authority leaked into V2 lock",
    )
    require(
        all(
            row["trajectory_spec_id"].startswith("fresh_vp_v2_")
            for row in lock["entries"]
        ),
        "non-V2 entry present",
    )
    return lock


def verify_remote_ledger(local_path: Path) -> None:
    remote_uri = S3_PREFIX.rstrip("/") + "/p2_capture_ledger.jsonl"
    remote = subprocess.run(
        ["aws", "s3", "cp", remote_uri, "-", "--only-show-errors"],
        check=True,
        capture_output=True,
        timeout=120,
    ).stdout
    require(remote == local_path.read_bytes(), "final S3 ledger roundtrip mismatch")


def main() -> int:
    for name in OUTPUT_NAMES:
        require(not (PACKAGE / name).exists(), f"refusing to overwrite {name}")
    result = compute()
    verify_remote_ledger(result["source"]["ledger_path"])
    write_json_new(PACKAGE / "cohort_capture_manifest_v2.json", result["manifest"])
    write_json_new(PACKAGE / "p4c_v2_pilot_runtime_qa.json", result["pilot"])
    write_json_new(
        PACKAGE / "p4c_capture_reconciliation_v2.json", result["reconciliation"]
    )
    write_json_new(PACKAGE / "p4c_actual_profile_audit_v2.json", result["audit"])
    write_json_new(PACKAGE / "accepted_cohort_v2.lock.json", result["lock"])
    load_accepted_cohort_v2()
    receipt = {
        "schema_version": "large-scale-no-wall-p4c-receipt-v0.1",
        "status": "PASS_REPAIRED_CAPTURE_COHORT_LOCKED",
        "p4b_head": P4B_HEAD,
        "protected_authority_sha256": dict(sorted(PROTECTED_HASHES.items())),
        "old_capture_reuse_in_primary": False,
        "v2_profile_diversity_accepted": True,
        "trajectory_profile_confound_controlled": True,
        "accepted_cohort_v2_lock_created": True,
        "accepted_cohort_v2_lock_count": 120,
        "train_test_assignments_created": False,
        "fresh_activations_extracted": 0,
        "fresh_r2_computed": False,
        "p5_started": False,
        "safe_for_p5": True,
        "blocker": None,
        "artifact_paths": [
            "p4c_capture_ledger_v2.jsonl",
            "p4c_v2_stage_a_durability_receipt.json",
            "p4c_v2_stage_b_durability_receipt.json",
            "p4c_v2_stage_c_durability_receipt.json",
            "p4c_v2_stage_d_durability_receipt.json",
            "cohort_capture_manifest_v2.json",
            "p4c_v2_pilot_runtime_qa.json",
            "p4c_capture_reconciliation_v2.json",
            "p4c_actual_profile_audit_v2.json",
            "accepted_cohort_v2.lock.json",
            "p4c_receipt.json",
        ],
    }
    write_json_new(PACKAGE / "p4c_receipt.json", receipt)
    print(
        "P4C_STATUS=PASS_REPAIRED_CAPTURE_COHORT_LOCKED "
        f"high_similarity_fraction={result['audit']['profile_similarity']['all_pairs']['high_abs_r_ge_0_95_proportion']:.12f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
