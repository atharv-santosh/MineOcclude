#!/usr/bin/env python3
"""Run the frozen P4 pre-extraction trajectory-profile design audit.

This program reads only capture/specification authority.  It does not import or
execute MineWorld and never creates train/test assignments.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = (
    ROOT / "docs/status/integration/exploratory_large_scale_no_wall_scaling_best_k_v0_1"
)
RUNTIME_ROOT = Path(
    "/mnt/sagemaker-nvme/mineocclude_large_scale_no_wall_scaling_best_k_v0_1"
)
P3_HEAD = "222c41637381b208b2abd96776d376b428383b60"
CAMPAIGN_SHA256 = "1605f4738840ea531e73fdcee19536d55652a1a05ddef704304adcb1bc41cdd6"
STUDY_SHA256 = "08d77261f70a3d7e554ce6f8fe4a565fa09591ae793a87efd60e4a742c016502"
EXPECTED_ROWS = 60


class AuditError(RuntimeError):
    pass


def read_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(8 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def verify_ledger(path: Path) -> list[dict[str, Any]]:
    rows = read_jsonl(path)
    previous = None
    for index, row in enumerate(rows):
        claimed = row["record_sha256"]
        body = dict(row)
        body.pop("record_sha256")
        if row["previous_record_sha256"] != previous:
            raise AuditError(f"ledger chain break at {index}")
        if canonical_sha256(body) != claimed:
            raise AuditError(f"ledger hash mismatch at {index}")
        previous = claimed
    return rows


def pearson(time_or_profile: np.ndarray, target: np.ndarray) -> float:
    if len(time_or_profile) != len(target):
        raise AuditError("Pearson inputs differ in length")
    if not np.isfinite(time_or_profile).all() or not np.isfinite(target).all():
        raise AuditError("Pearson input is non-finite")
    if np.var(time_or_profile) <= 0 or np.var(target) <= 0:
        raise AuditError("Pearson input has zero variance")
    return float(np.corrcoef(time_or_profile, target)[0, 1])


def summary(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {"count": 0, "min": None, "median": None, "mean": None, "max": None}
    array = np.asarray(values, dtype=np.float64)
    return {
        "count": int(array.size),
        "min": float(np.min(array)),
        "median": float(np.median(array)),
        "mean": float(np.mean(array)),
        "max": float(np.max(array)),
    }


def similarity_summary(values: list[float], threshold: float) -> dict[str, Any]:
    array = np.asarray(values, dtype=np.float64)
    high = int(np.sum(array >= threshold))
    return {
        "count": int(array.size),
        "min": float(np.min(array)),
        "median": float(np.median(array)),
        "mean": float(np.mean(array)),
        "p95": float(np.quantile(array, 0.95, method="linear")),
        "max": float(np.max(array)),
        "high_similarity_count": high,
        "high_similarity_fraction": float(high / array.size),
    }


def expected_commands(spec: dict[str, Any]) -> tuple[list[float], list[int]]:
    commands: list[float] = []
    segments: list[int] = []
    for tick in range(EXPECTED_ROWS):
        matches = [
            (index, row)
            for index, row in enumerate(spec["exact_speed_schedule"])
            if row["start_model_frame_idx"]
            <= tick
            < row["stop_model_frame_idx_exclusive"]
        ]
        if len(matches) != 1:
            raise AuditError(f"invalid command coverage: {spec['trajectory_spec_id']}")
        index, row = matches[0]
        commands.append(float(row["signed_speed_blocks_per_second"]))
        segments.append(index)
    return commands, segments


def expected_start_range(
    study: dict[str, Any], layout: str, direction: str
) -> tuple[float, float]:
    lower, upper = map(float, study["motion_authority"]["start_ranges"][layout])
    if direction == "LEFT_TO_RIGHT":
        return lower, upper
    return -upper, -lower


def pooled_correlation(records: list[dict[str, Any]]) -> float:
    times = np.concatenate([row["normalized_time"] for row in records])
    targets = np.concatenate([row["profile"] for row in records])
    return pearson(times, targets)


def stratified_correlations(
    records: list[dict[str, Any]], key: str
) -> dict[str, float]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in records:
        groups[str(row[key])].append(row)
    return {name: pooled_correlation(groups[name]) for name in sorted(groups)}


def reconstruct() -> dict[str, Any]:
    campaign_path = PACKAGE / "capture_campaign.json"
    study_path = PACKAGE / "study_design.json"
    if sha256_file(campaign_path) != CAMPAIGN_SHA256:
        raise AuditError("campaign hash changed")
    if sha256_file(study_path) != STUDY_SHA256:
        raise AuditError("study design hash changed")
    campaign = read_json(campaign_path)
    study = read_json(study_path)
    contract = read_json(PACKAGE / "profile_audit_contract.json")
    manifest = read_json(PACKAGE / "cohort_capture_manifest.json")
    ledger = verify_ledger(PACKAGE / "p2_capture_ledger.jsonl")
    specs = {row["trajectory_spec_id"]: row for row in campaign["trajectory_specs"]}
    accepted_rows = [
        row
        for row in ledger
        if row["record_type"] == "ATTEMPT_CLASSIFIED"
        and row.get("classification") == "ACCEPTED"
    ]
    accepted = {row["trajectory_spec_id"]: row for row in accepted_rows}
    if len(accepted_rows) != len(accepted) or len(accepted) != 120:
        raise AuditError("accepted cohort is not 120 unique entries")
    if set(accepted) != set(specs):
        raise AuditError("accepted cohort differs from locked campaign")
    manifest_rows = {
        row["trajectory_spec_id"]: row for row in manifest["accepted_specs"]
    }
    if set(manifest_rows) != set(specs):
        raise AuditError("cohort manifest differs from locked campaign")

    profiles = []
    retry_rows = [
        row
        for row in ledger
        if row["record_type"] == "ATTEMPT_CLASSIFIED"
        and row.get("classification") == "REJECTED_WITH_REASON"
    ]
    for spec_id in sorted(specs):
        spec = specs[spec_id]
        accepted_row = accepted[spec_id]
        manifest_row = manifest_rows[spec_id]
        if accepted_row["spec_hash"] != spec["spec_hash"]:
            raise AuditError(f"accepted spec hash mismatch: {spec_id}")
        if manifest_row["spec_hash"] != spec["spec_hash"]:
            raise AuditError(f"manifest spec hash mismatch: {spec_id}")
        attempt = int(accepted_row["attempt_number"])
        root = RUNTIME_ROOT / "attempts" / spec_id / f"attempt_{attempt:02d}"
        state = read_jsonl(root / "raw/server/server_state.jsonl")
        actions = read_jsonl(root / "raw/client/raw_actions.jsonl")
        frame_map = read_jsonl(root / "frame_map.jsonl")
        if not (len(state) == len(actions) == len(frame_map) == EXPECTED_ROWS):
            raise AuditError(f"F != 60: {spec_id}")
        if [row["server_tick"] for row in state] != list(range(EXPECTED_ROWS)):
            raise AuditError(f"non-dense server ticks: {spec_id}")
        if [row["model_frame_idx"] for row in frame_map] != list(range(EXPECTED_ROWS)):
            raise AuditError(f"non-dense model rows: {spec_id}")
        command, segments = expected_commands(spec)
        if any(
            not math.isclose(float(row["commanded_v"]), command[index], abs_tol=1e-12)
            or int(row["motion_segment_index"]) != segments[index]
            for index, row in enumerate(state)
        ):
            raise AuditError(f"motion schedule mismatch: {spec_id}")
        target = np.asarray([float(row["axis_pos"]) for row in state])
        if not np.isfinite(target).all() or float(np.var(target)) <= 0:
            raise AuditError(f"invalid target variance: {spec_id}")
        target_lower, target_upper = map(
            float, study["motion_authority"]["target_ranges"][spec["layout_id"]]
        )
        if (
            float(np.min(target)) < target_lower - 1e-9
            or float(np.max(target)) > target_upper + 1e-9
        ):
            raise AuditError(f"target outside authority: {spec_id}")
        start = float(spec["start_position_authority"]["axis_position_blocks"])
        start_lower, start_upper = expected_start_range(
            study, spec["layout_id"], spec["direction"]
        )
        if not start_lower - 1e-9 <= start <= start_upper + 1e-9:
            raise AuditError(f"start outside authority: {spec_id}")
        end = float(target[-1])
        if not target_lower - 1e-9 <= end <= target_upper + 1e-9:
            raise AuditError(f"end outside authority: {spec_id}")
        camera = spec["camera_viewpoint_authority"]
        feet_x, feet_y, feet_z = map(float, camera["canonical_feet_xyz_blocks"])
        camera_ok = all(
            math.isclose(float(row["player_x"]), feet_x, abs_tol=1e-6)
            and math.isclose(float(row["player_y"]), feet_y + 1.62, abs_tol=1e-6)
            and math.isclose(float(row["player_z"]), feet_z, abs_tol=1e-6)
            and math.isclose(
                float(row["player_yaw"]), float(camera["yaw_degrees"]), abs_tol=1e-6
            )
            and math.isclose(
                float(row["player_pitch"]),
                float(camera["pitch_degrees"]),
                abs_tol=1e-6,
            )
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
        if not camera_ok or not no_wall_ok:
            raise AuditError(f"camera/no-wall mismatch: {spec_id}")
        nonzero = [index for index, value in enumerate(command) if value != 0.0]
        onset = min(nonzero) if nonzero else None
        profiles.append(
            {
                "trajectory_spec_id": spec_id,
                "spec_hash": spec["spec_hash"],
                "layout_id": spec["layout_id"],
                "direction": spec["direction"],
                "profile_family": spec["profile_family"],
                "repeat_id": int(spec["repeat_id"]),
                "capture_seed": int(spec["capture_seed"]),
                "attempt_number": attempt,
                "episode_id": int(accepted_row["episode_id"]),
                "normalized_time": np.arange(EXPECTED_ROWS, dtype=float)
                / (EXPECTED_ROWS - 1),
                "profile": target,
                "command": command,
                "start": start,
                "end": end,
                "target_min": float(np.min(target)),
                "target_max": float(np.max(target)),
                "target_range": float(np.ptp(target)),
                "target_variance": float(np.var(target)),
                "onset": onset,
                "pause_start": (
                    int(spec["pause"]["start_model_frame_idx"])
                    if spec.get("pause")
                    else None
                ),
                "pause_duration": (
                    int(spec["pause"]["duration_ticks"]) if spec.get("pause") else None
                ),
                "speed_change": (
                    int(spec["speed_change_model_frame_idx"])
                    if spec.get("speed_change_model_frame_idx") is not None
                    else None
                ),
                "server_state_path": str(
                    (root / "raw/server/server_state.jsonl").relative_to(RUNTIME_ROOT)
                ),
                "raw_actions_path": str(
                    (root / "raw/client/raw_actions.jsonl").relative_to(RUNTIME_ROOT)
                ),
                "frame_map_path": str(
                    (root / "frame_map.jsonl").relative_to(RUNTIME_ROOT)
                ),
                "server_state_sha256": sha256_file(
                    root / "raw/server/server_state.jsonl"
                ),
                "raw_actions_sha256": sha256_file(
                    root / "raw/client/raw_actions.jsonl"
                ),
                "frame_map_sha256": sha256_file(root / "frame_map.jsonl"),
                "attempt_manifest_sha256": sha256_file(root / "sha256_manifest.json"),
                "capture_provenance_sha256": sha256_file(
                    root / "capture_provenance.json"
                ),
                "camera_authority_pass": camera_ok,
                "no_wall_pass": no_wall_ok,
            }
        )
    return {
        "campaign": campaign,
        "study": study,
        "contract": contract,
        "ledger": ledger,
        "profiles": profiles,
        "rejected": retry_rows,
    }


def compute_audit() -> dict[str, Any]:
    reconstructed = reconstruct()
    profiles = reconstructed["profiles"]
    campaign = reconstructed["campaign"]
    study = reconstructed["study"]
    contract = reconstructed["contract"]

    per_layout = Counter(row["layout_id"] for row in profiles)
    per_direction_layout = Counter(
        (row["layout_id"], row["direction"]) for row in profiles
    )
    cells: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in profiles:
        cells[(row["layout_id"], row["direction"], row["profile_family"])].append(row)
    repeat_ids_distinct = all(
        len({row["repeat_id"] for row in rows}) == 2 for rows in cells.values()
    )
    seeds_distinct = all(
        len({row["capture_seed"] for row in rows}) == 2 for rows in cells.values()
    )
    settings_distinct = all(
        len(
            {
                canonical_sha256(
                    {
                        "capture_seed": row["capture_seed"],
                        "start": row["start"],
                        "command": row["command"],
                    }
                )
                for row in rows
            }
        )
        == 2
        for rows in cells.values()
    )
    balance_pass = (
        len(profiles) == 120
        and per_layout == {f"L{index:02d}": 20 for index in range(1, 7)}
        and len(per_direction_layout) == 12
        and set(per_direction_layout.values()) == {10}
        and len(cells) == 60
        and {len(rows) for rows in cells.values()} == {2}
        and repeat_ids_distinct
        and seeds_distinct
        and settings_distinct
    )

    time_position = {
        "normalized_time_definition": "model_frame_idx / 59 for indices 0..59",
        "overall": pooled_correlation(profiles),
        "by_profile_family": stratified_correlations(profiles, "profile_family"),
        "by_direction": stratified_correlations(profiles, "direction"),
        "by_layout_diagnostic_not_required_by_contract": stratified_correlations(
            profiles, "layout_id"
        ),
    }
    global_limit = float(
        contract["time_target_correlation"]["global_absolute_correlation_max"]
    )
    global_pass = abs(time_position["overall"]) <= global_limit

    threshold = float(
        contract["pairwise_profile_similarity"]["high_similarity_threshold_inclusive"]
    )
    max_fraction = float(
        contract["pairwise_profile_similarity"]["maximum_fraction_high_similarity"]
    )
    all_similarity = []
    same_family = []
    between_family = []
    same_direction = []
    opposite_direction = []
    for left, right in combinations(profiles, 2):
        value = abs(pearson(left["profile"], right["profile"]))
        all_similarity.append(value)
        (
            same_family
            if left["profile_family"] == right["profile_family"]
            else between_family
        ).append(value)
        (
            same_direction
            if left["direction"] == right["direction"]
            else opposite_direction
        ).append(value)
    similarity = {
        "absolute_pearson": True,
        "quantile_method": "numpy linear",
        "all_pairs": similarity_summary(all_similarity, threshold),
        "same_profile_family": similarity_summary(same_family, threshold),
        "between_profile_families": similarity_summary(between_family, threshold),
        "same_direction": similarity_summary(same_direction, threshold),
        "opposite_direction": similarity_summary(opposite_direction, threshold),
        "threshold_inclusive": threshold,
        "maximum_fraction_high_similarity": max_fraction,
    }
    similarity_pass = (
        similarity["all_pairs"]["high_similarity_fraction"] <= max_fraction
    )

    distributions = {}
    for field in (
        "start",
        "end",
        "target_min",
        "target_max",
        "target_range",
        "target_variance",
    ):
        distributions[field] = {
            "overall": summary([float(row[field]) for row in profiles]),
            "by_layout": {
                layout: summary(
                    [
                        float(row[field])
                        for row in profiles
                        if row["layout_id"] == layout
                    ]
                )
                for layout in sorted(per_layout)
            },
            "by_direction": {
                direction: summary(
                    [
                        float(row[field])
                        for row in profiles
                        if row["direction"] == direction
                    ]
                )
                for direction in sorted({row["direction"] for row in profiles})
            },
            "by_profile_family": {
                family: summary(
                    [
                        float(row[field])
                        for row in profiles
                        if row["profile_family"] == family
                    ]
                )
                for family in sorted({row["profile_family"] for row in profiles})
            },
        }
    range_coverage = {}
    for layout in sorted(per_layout):
        rows = [row for row in profiles if row["layout_id"] == layout]
        lower, upper = map(float, study["motion_authority"]["target_ranges"][layout])
        range_coverage[layout] = {
            "authorized_min": lower,
            "authorized_max": upper,
            "observed_min": min(row["target_min"] for row in rows),
            "observed_max": max(row["target_max"] for row in rows),
            "observed_fraction_of_authorized_range": (
                max(row["target_max"] for row in rows)
                - min(row["target_min"] for row in rows)
            )
            / (upper - lower),
            "frozen_minimum_fraction": None,
            "gate_applied": False,
            "reason": "profile_audit_contract.json retained no range-coverage threshold",
        }

    family_stats = {}
    for family in sorted({row["profile_family"] for row in profiles}):
        rows = [row for row in profiles if row["profile_family"] == family]
        family_stats[family] = {
            "count": len(rows),
            "signed_command_speeds": sorted(
                {float(value) for row in rows for value in row["command"]}
            ),
            "absolute_nonzero_command_speeds": sorted(
                {
                    abs(float(value))
                    for row in rows
                    for value in row["command"]
                    if value != 0.0
                }
            ),
            "movement_onset_frames": sorted(
                {int(row["onset"]) for row in rows if row["onset"] is not None}
            ),
            "pause_start_frames": sorted(
                {
                    int(row["pause_start"])
                    for row in rows
                    if row["pause_start"] is not None
                }
            ),
            "pause_duration_ticks": sorted(
                {
                    int(row["pause_duration"])
                    for row in rows
                    if row["pause_duration"] is not None
                }
            ),
            "speed_change_frames": sorted(
                {
                    int(row["speed_change"])
                    for row in rows
                    if row["speed_change"] is not None
                }
            ),
            "start_offset_summary": summary([row["start"] for row in rows]),
            "end_offset_summary": summary([row["end"] for row in rows]),
        }

    rejected = reconstructed["rejected"]
    retry_pass = False
    retry_audit: dict[str, Any] = {
        "schema_version": "large-scale-no-wall-p4-retry-audit-v0.1",
        "rejected_attempt_count": len(rejected),
    }
    if len(rejected) == 1:
        failed = rejected[0]
        spec_id = failed["trajectory_spec_id"]
        accepted = next(row for row in profiles if row["trajectory_spec_id"] == spec_id)
        failed_root = (
            RUNTIME_ROOT
            / "attempts"
            / spec_id
            / f"attempt_{int(failed['attempt_number']):02d}"
        )
        accepted_root = (
            RUNTIME_ROOT
            / "attempts"
            / spec_id
            / f"attempt_{accepted['attempt_number']:02d}"
        )
        failed_metadata = read_json(failed_root / "attempt_metadata.json")
        accepted_metadata = read_json(accepted_root / "attempt_metadata.json")
        exact_same = (
            failed_metadata["exact_scientific_spec"]
            == accepted_metadata["exact_scientific_spec"]
            == next(
                row
                for row in campaign["trajectory_specs"]
                if row["trajectory_spec_id"] == spec_id
            )
        )
        retry_pass = (
            spec_id
            in {row["trajectory_spec_id"] for row in campaign["trajectory_specs"]}
            and int(failed["attempt_number"]) == 1
            and accepted["attempt_number"] == 2
            and failed["spec_hash"] == accepted["spec_hash"]
            and exact_same
        )
        retry_audit.update(
            {
                "status": "PASS" if retry_pass else "FAIL",
                "trajectory_spec_id": spec_id,
                "failure_reason_codes": failed["failure_reason_codes"],
                "failed_attempt_number": int(failed["attempt_number"]),
                "accepted_attempt_number": accepted["attempt_number"],
                "spec_hash_unchanged": failed["spec_hash"] == accepted["spec_hash"],
                "exact_scientific_spec_unchanged": exact_same,
                "failed_attempt_preserved_in_ledger": True,
                "failed_attempt_excluded_from_accepted_cohort": True,
                "accepted_trajectory_duplicated": False,
            }
        )

    component_gates = {
        "balanced_complete_matrix": balance_pass,
        "repeat_authority_non_identical": repeat_ids_distinct
        and seeds_distinct
        and settings_distinct,
        "target_ranges_finite_and_legal": True,
        "target_variance_each_trajectory_gt_zero": all(
            row["target_variance"] > 0 for row in profiles
        ),
        "motion_schedules_legal_and_exact": True,
        "common_f_60": True,
        "camera_authority": all(row["camera_authority_pass"] for row in profiles),
        "no_wall_authority": all(row["no_wall_pass"] for row in profiles),
        "global_time_position_correlation": global_pass,
        "required_stratified_time_position_reporting_complete": True,
        "pairwise_profile_similarity": similarity_pass,
        "retry_immutability": retry_pass,
    }
    controlled = all(component_gates.values())
    blocker = None
    if not controlled:
        blocker = {
            "reason_code": "PROFILE_SIMILARITY_GATE_FAILED",
            "observed_high_similarity_count": similarity["all_pairs"][
                "high_similarity_count"
            ],
            "pair_count": similarity["all_pairs"]["count"],
            "observed_high_similarity_fraction": similarity["all_pairs"][
                "high_similarity_fraction"
            ],
            "maximum_allowed_fraction": max_fraction,
            "bounded_same_spec_recollection_can_repair": False,
            "reason": (
                "The frozen target profiles are deterministic functions of each locked "
                "spec/seed/schedule, so same-spec recollection reproduces the profile. "
                "Passing would require a protocol/spec or threshold change forbidden in P4."
            ),
            "repair_spec_ids": [],
        }

    audit = {
        "schema_version": "large-scale-no-wall-p4-pre-extraction-audit-v0.1",
        "status": "PASS" if controlled else "STOP_AND_REPORT",
        "outcome_blind": True,
        "activation_or_probe_inputs_used": False,
        "accepted_trajectory_count": len(profiles),
        "accepted_per_layout": dict(sorted(per_layout.items())),
        "accepted_per_layout_direction": {
            f"{layout}|{direction}": count
            for (layout, direction), count in sorted(per_direction_layout.items())
        },
        "accepted_per_layout_direction_profile_cell": {
            f"{layout}|{direction}|{family}": len(rows)
            for (layout, direction, family), rows in sorted(cells.items())
        },
        "unique_spec_ids": len({row["trajectory_spec_id"] for row in profiles}),
        "unique_spec_hashes": len({row["spec_hash"] for row in profiles}),
        "repeat_ids_distinct": repeat_ids_distinct,
        "capture_seeds_distinct_within_cell": seeds_distinct,
        "scientific_settings_non_identical_within_repeat_cell": settings_distinct,
        "rows_per_trajectory": EXPECTED_ROWS,
        "f_common": True,
        "time_position_correlation": time_position,
        "global_absolute_correlation_threshold": global_limit,
        "global_absolute_correlation_pass": global_pass,
        "aggregate_cancellation_used_as_sole_pass": False,
        "pairwise_profile_similarity": similarity,
        "pairwise_profile_similarity_pass": similarity_pass,
        "component_gates": component_gates,
        "trajectory_profile_confound_controlled": controlled,
        "accepted_cohort_lock_created": False,
        "train_test_assignments_created": False,
        "blocker": blocker,
    }
    statistics_doc = {
        "schema_version": "large-scale-no-wall-p4-profile-statistics-v0.1",
        "status": audit["status"],
        "distribution_summaries": distributions,
        "target_range_coverage_diagnostic": range_coverage,
        "motion_profile_statistics": family_stats,
        "profile_families_present": sorted(family_stats),
        "motion_profile_audit_pass": True,
        "start_range_audit_pass": True,
        "end_range_audit_pass": True,
        "target_range_audit_pass": True,
        "target_variance_audit_pass": True,
        "per_trajectory": [
            {
                key: row[key]
                for key in (
                    "trajectory_spec_id",
                    "spec_hash",
                    "layout_id",
                    "direction",
                    "profile_family",
                    "repeat_id",
                    "capture_seed",
                    "attempt_number",
                    "episode_id",
                    "start",
                    "end",
                    "target_min",
                    "target_max",
                    "target_range",
                    "target_variance",
                    "onset",
                    "pause_start",
                    "pause_duration",
                    "speed_change",
                    "server_state_path",
                    "raw_actions_path",
                    "frame_map_path",
                    "server_state_sha256",
                    "raw_actions_sha256",
                    "frame_map_sha256",
                    "attempt_manifest_sha256",
                    "capture_provenance_sha256",
                )
            }
            for row in profiles
        ],
    }
    return {
        "audit": audit,
        "statistics": statistics_doc,
        "retry": retry_audit,
        "profiles": profiles,
        "similarity_values": all_similarity,
    }


def write_figures(result: dict[str, Any]) -> list[str]:
    audit = result["audit"]
    time_position = audit["time_position_correlation"]
    labels = ["overall"]
    values = [time_position["overall"]]
    for prefix, field in (
        ("family", "by_profile_family"),
        ("direction", "by_direction"),
        ("layout", "by_layout_diagnostic_not_required_by_contract"),
    ):
        for name, value in time_position[field].items():
            labels.append(f"{prefix}:{name}")
            values.append(value)
    fig, axis = plt.subplots(figsize=(10, 5.5))
    colors = ["#4c78a8" if abs(value) <= 0.1 else "#e45756" for value in values]
    axis.barh(range(len(values)), values, color=colors)
    axis.axvline(0.1, color="black", linestyle="--", linewidth=1)
    axis.axvline(-0.1, color="black", linestyle="--", linewidth=1)
    axis.set_yticks(range(len(labels)), labels=labels, fontsize=8)
    axis.set_xlabel("Pearson r: normalized time vs x_true_blocks")
    axis.set_title("Pre-extraction time-position associations (signed)")
    axis.invert_yaxis()
    fig.tight_layout()
    association_path = PACKAGE / "time_position_association.png"
    fig.savefig(association_path, dpi=150)
    plt.close(fig)

    threshold = audit["pairwise_profile_similarity"]["threshold_inclusive"]
    values_array = np.asarray(result["similarity_values"])
    fig, axis = plt.subplots(figsize=(7.5, 4.5))
    axis.hist(values_array, bins=np.linspace(0, 1, 41), color="#4c78a8", alpha=0.9)
    axis.axvline(threshold, color="#e45756", linewidth=2, label="frozen threshold 0.95")
    fraction = audit["pairwise_profile_similarity"]["all_pairs"][
        "high_similarity_fraction"
    ]
    axis.set_xlabel("Absolute pairwise Pearson similarity")
    axis.set_ylabel("Unordered trajectory pairs")
    axis.set_title(f"Profile similarity: {fraction:.1%} ≥ 0.95 (maximum 20%)")
    axis.legend()
    fig.tight_layout()
    similarity_path = PACKAGE / "profile_similarity_distribution.png"
    fig.savefig(similarity_path, dpi=150)
    plt.close(fig)
    return [association_path.name, similarity_path.name]


def main() -> int:
    result = compute_audit()
    figures = write_figures(result)
    write_json(PACKAGE / "pre_extraction_profile_audit.json", result["audit"])
    write_json(PACKAGE / "p4_profile_statistics.json", result["statistics"])
    write_json(PACKAGE / "p4_retry_audit.json", result["retry"])
    controlled = result["audit"]["trajectory_profile_confound_controlled"]
    lock_path = PACKAGE / "accepted_cohort.lock.json"
    if controlled:
        lock = {
            "schema_version": "large-scale-no-wall-accepted-cohort-lock-v0.1",
            "status": "LOCKED_FOR_P5",
            "entry_count": 120,
            "contains_train_test_assignments": False,
            "contains_model_or_activation_outcomes": False,
            "entries": result["statistics"]["per_trajectory"],
        }
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        descriptor = os.open(lock_path, flags, 0o644)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(lock, stream, indent=2, sort_keys=True, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
    elif lock_path.exists():
        raise AuditError("failed audit must not retain accepted_cohort.lock.json")
    receipt = {
        "schema_version": "large-scale-no-wall-p4-receipt-v0.1",
        "status": result["audit"]["status"],
        "p3_head": P3_HEAD,
        "trajectory_profile_confound_controlled": controlled,
        "accepted_cohort_lock_created": controlled,
        "accepted_cohort_lock_count": 120 if controlled else 0,
        "train_test_assignments_created": False,
        "fresh_activations_extracted": 0,
        "fresh_r2_computed": False,
        "p5_started": False,
        "safe_for_p5": controlled,
        "repair_required": (
            None if controlled else "FROZEN_PROTOCOL_LEVEL_PROFILE_DIVERSITY_REDESIGN"
        ),
        "repair_spec_ids": (
            [] if controlled else result["audit"]["blocker"]["repair_spec_ids"]
        ),
        "blocker": result["audit"]["blocker"],
        "artifact_paths": [
            "pre_extraction_profile_audit.json",
            "p4_profile_statistics.json",
            "p4_retry_audit.json",
            *figures,
            "p4_receipt.json",
        ],
    }
    if controlled:
        receipt["artifact_paths"].append("accepted_cohort.lock.json")
    write_json(PACKAGE / "p4_receipt.json", receipt)
    print(
        f"P4_STATUS={receipt['status']} "
        f"high_similarity_fraction={result['audit']['pairwise_profile_similarity']['all_pairs']['high_similarity_fraction']:.12f}"
    )
    return 0 if controlled else 2


if __name__ == "__main__":
    raise SystemExit(main())
