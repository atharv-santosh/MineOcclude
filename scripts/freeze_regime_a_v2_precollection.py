#!/usr/bin/env python3
"""Freeze the prospective Regime-A first25-v2 precollection authority."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mineocclude.regime_a import (  # noqa: E402
    BIN_BOUNDS,
    V2_CALIBRATION,
    build_null_mappings,
    canonical_sha256,
    deterministic_seed,
    generate_scientific_specs,
    sha256_file,
    validate_null_mappings,
    validate_scientific_specs,
)

STATUS = ROOT / "docs/status/integration/regime_a_occlusion_extraction_v0_1"
V1_MANIFEST = STATUS / "trajectory_manifest.jsonl"
V1_DONORS = STATUS / "null_donor_manifest.jsonl"
RUN_ID = "mineocclude-regime-a-first25-v2"
A2_FILES = (
    "implementation_test_receipt.json",
    "benchmark_receipt.json",
    "cache_equivalence_receipt.json",
    "restart_recovery_receipt.json",
    "cost_projection.json",
)


def json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def jsonl_bytes(rows: list[dict[str, object]]) -> bytes:
    return b"".join(
        json.dumps(row, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        + b"\n"
        for row in rows
    )


def _crossing_summary(report: dict[str, object], direction: str) -> dict[str, object]:
    aggregate = report[direction]
    assert isinstance(aggregate, dict)
    crossings = aggregate["crossings"]
    assert isinstance(crossings, list)
    geometric_hidden = [float(row["geometric_first_hidden_world_x"]) for row in crossings]
    geometric_visible_before = [
        float(row["geometric_last_visible_before_entry_world_x"]) for row in crossings
    ]
    if direction == "LEFT_TO_RIGHT":
        geometric_bracket = [max(geometric_visible_before), min(geometric_hidden)]
    else:
        geometric_bracket = [max(geometric_hidden), min(geometric_visible_before)]
    geometric_point = sum(geometric_bracket) / 2.0
    expected_point = float(V2_CALIBRATION.geometric_entry[direction])
    if not np.isclose(geometric_point, expected_point, atol=1e-15, rtol=0):
        raise RuntimeError(f"{direction} calibrated geometric point drift")
    entry_values = [float(row["stable_hidden_onset_world_x"]) for row in crossings]
    exit_values = [float(row["stable_hidden_last_world_x"]) for row in crossings]
    return {
        "calibration_ids": [row["trajectory_spec_id"] for row in crossings],
        "seeds": [row["seed"] for row in crossings],
        "qualified_crossings": len(crossings),
        "geometric_hidden_boundary_bracket_world_x": geometric_bracket,
        "geometric_hidden_boundary_point_world_x": geometric_point,
        "stable_dual_hidden_entry_observed_world_x": entry_values,
        "stable_dual_hidden_entry_conservative_world_x": float(
            V2_CALIBRATION.directional_hidden_entry[direction]  # type: ignore[index]
        ),
        "stable_dual_hidden_exit_observed_world_x": exit_values,
        "stable_dual_hidden_exit_conservative_world_x": float(
            V2_CALIBRATION.directional_hidden_exit[direction]  # type: ignore[index]
        ),
        "entry_transition_disagreement_runs_frames": [
            row["entry_transition_max_consecutive_frames"] for row in crossings
        ],
        "exit_transition_disagreement_runs_frames": [
            row["exit_transition_max_consecutive_frames"] for row in crossings
        ],
        "maximum_entry_run_frames": aggregate["entry_transition_max_consecutive_frames"],
        "maximum_exit_run_frames": aggregate["exit_transition_max_consecutive_frames"],
        "g_entry_frames": aggregate["derived_g_entry"],
        "g_exit_frames": aggregate["derived_g_exit"],
        "replication_stability": "PASS_BOUNDED_DIRECTIONAL_REPLICATION",
        "temporal_alignment": aggregate["all_temporally_aligned"],
        "capture_ack_identity": aggregate["all_capture_ack_identities_exact"],
        "dual_visibility": aggregate["dual_visibility_qualified"],
    }


def _v2_specs(authority_hash: str) -> tuple[list[dict[str, object]], int]:
    study_hash = sha256_file(STATUS / "regime_a_study_manifest.json")
    a2_hashes = {
        f"a2_{name.removesuffix('.json')}_sha256": sha256_file(STATUS / name)
        for name in A2_FILES
    }
    generated = generate_scientific_specs(
        study_hash,
        {**a2_hashes, "directional_visibility_authority_v2_sha256": authority_hash},
        V2_CALIBRATION,
    )
    old_rows = [
        json.loads(line)
        for line in V1_MANIFEST.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    old_fold_by_seed = {row["seed"]: row["outer_fold"] for row in old_rows}
    target_direction_counts = {
        0: {"LEFT_TO_RIGHT": 3, "RIGHT_TO_LEFT": 2},
        1: {"LEFT_TO_RIGHT": 2, "RIGHT_TO_LEFT": 3},
        2: {"LEFT_TO_RIGHT": 3, "RIGHT_TO_LEFT": 2},
        3: {"LEFT_TO_RIGHT": 2, "RIGHT_TO_LEFT": 3},
        4: {"LEFT_TO_RIGHT": 3, "RIGHT_TO_LEFT": 2},
    }
    used = {
        fold: {"LEFT_TO_RIGHT": 0, "RIGHT_TO_LEFT": 0} for fold in range(5)
    }
    for row in generated:
        if row["seed"] in old_fold_by_seed:
            row["outer_fold"] = old_fold_by_seed[row["seed"]]
            used[int(row["outer_fold"])][str(row["direction"])] += 1
    for direction in ("LEFT_TO_RIGHT", "RIGHT_TO_LEFT"):
        replacements = sorted(
            (
                row
                for row in generated
                if row["direction"] == direction and row["seed"] not in old_fold_by_seed
            ),
            key=lambda row: (row["seed"], row["trajectory_spec_id"]),
        )
        for row in replacements:
            fold = next(
                fold
                for fold in range(5)
                if used[fold][direction] < target_direction_counts[fold][direction]
            )
            row["outer_fold"] = fold
            used[fold][direction] += 1
    if used != target_direction_counts:
        raise RuntimeError("could not preserve valid v1 folds while balancing v2")
    result: list[dict[str, object]] = []
    for index, row in enumerate(generated):
        body = dict(row)
        body.pop("spec_hash")
        identity = f"regime_a_v2_t{index + 1:02d}"
        body.update(
            {
                "schema_version": "regime-a-trajectory-spec-v2.0",
                "trajectory_spec_id": identity,
                "scientific_run_id": RUN_ID,
                "episode_id": 52001 + index,
                "target_entity_logical_id": f"{identity}:magenta_sheep",
                "visibility_calibration": V2_CALIBRATION.as_authority(),
                "expected_target_semantics": (
                    "prospective conservative dual-hidden support forecast; actual tau is "
                    "the first frozen dual-visibility OCCLUDED_AGREEMENT run"
                ),
            }
        )
        body["spec_hash"] = canonical_sha256(body)
        result.append(body)
    validation = validate_scientific_specs(result, V2_CALIBRATION)
    if validation["trajectory_count"] != 25:
        raise RuntimeError("v2 validation count drift")
    return result, sum(row["seed"] in old_fold_by_seed for row in result)


def build_documents(
    calibration_report_path: Path, raw_recovery_receipt_path: Path
) -> dict[str, bytes]:
    report_bytes = calibration_report_path.read_bytes()
    report = json.loads(report_bytes)
    if (
        report.get("NON_SCIENTIFIC_CALIBRATION") is not True
        or report.get("ELIGIBLE_FOR_REGIME_A_RESULTS") is not False
        or report.get("time_reversal_assumed") is not False
    ):
        raise RuntimeError("calibration report is not qualified prospective evidence")
    ltr = _crossing_summary(report, "LEFT_TO_RIGHT")
    rtl = _crossing_summary(report, "RIGHT_TO_LEFT")
    authority = {
        "artifact_id": "regime-a-directional-visibility-authority-v2.0",
        "status": "FROZEN_PROSPECTIVE_BEFORE_SCIENTIFIC_V2_COLLECTION",
        "scientific_run_id": RUN_ID,
        "prospective": True,
        "outcome_independent": True,
        "time_reversal_assumed": False,
        "guard_rule": "directional maximum consecutive partial/disagreement run plus one captured frame, minimum one",
        "simulated_capture_hz": 20,
        "effective_preceding_frames": 15,
        "context_duration_simulated_seconds": 0.75,
        "wall_clock_time_does_not_define_context": True,
        "duration_bins": {name: list(bounds) for name, bounds in BIN_BOUNDS.items()},
        "LEFT_TO_RIGHT": ltr,
        "RIGHT_TO_LEFT": rtl,
        "planning_calibration": V2_CALIBRATION.as_authority(),
        "replication_interpretation": (
            "geometric boundary brackets overlap tightly; pixel transition widths vary "
            "but are deterministically bounded by the directional observed maxima"
        ),
        "directional_symmetry": "ASYMMETRIC",
        "symmetry_imposed": False,
        "source_calibration_report_sha256": hashlib.sha256(report_bytes).hexdigest(),
        "source_raw_recovery_receipt_sha256": sha256_file(raw_recovery_receipt_path),
        "historical_v1": {
            "trajectory_manifest_sha256": sha256_file(V1_MANIFEST),
            "donor_manifest_sha256": sha256_file(V1_DONORS),
            "LTR": {"entry_guard_frames": 20, "exit_guard_frames": 8},
            "RTL": {"entry_guard_frames": 8, "exit_guard_frames": 20},
            "status": "SUPERSEDED_PRESERVED_INVALID_PREQUALIFICATION_CAPTURE",
        },
        "supersession_reason": [
            "v1 capture had a render/state temporal join defect",
            "v1 RTL authority relied on unsupported time-reversal symmetry",
            "fresh capture_ack lockstep directional calibration independently measured both directions",
        ],
        "scientific_activations_existed_at_correction": False,
        "scientific_decoding_outcomes_existed_at_correction": False,
    }
    authority_payload = json_bytes(authority)
    authority_hash = hashlib.sha256(authority_payload).hexdigest()
    specs, preserved_seeds = _v2_specs(authority_hash)
    validation = validate_scientific_specs(specs, V2_CALIBRATION)
    manifest = jsonl_bytes(specs)
    manifest_hash = hashlib.sha256(manifest).hexdigest()

    pair_rows = []
    for left, right in itertools.combinations(specs, 2):
        a = np.asarray(left["expected_tau_1_to_19_world_x"], dtype=np.float64)
        b = np.asarray(right["expected_tau_1_to_19_world_x"], dtype=np.float64)
        pair_rows.append(
            {
                "left": left["trajectory_spec_id"],
                "right": right["trajectory_spec_id"],
                "rms_blocks": float(np.sqrt(np.mean((a - b) ** 2))),
            }
        )
    near_count = sum(row["rms_blocks"] < 0.10 for row in pair_rows)
    if near_count:
        raise RuntimeError("v2 near-duplicate requirement failed")

    support = []
    for fold in range(5):
        for direction in ("LEFT_TO_RIGHT", "RIGHT_TO_LEFT"):
            train = [
                row for row in specs if row["outer_fold"] != fold and row["direction"] == direction
            ]
            heldout = [
                row for row in specs if row["outer_fold"] == fold and row["direction"] == direction
            ]
            for name, (start, stop) in BIN_BOUNDS.items():
                train_values = [
                    value
                    for row in train
                    for value in row["expected_tau_1_to_19_world_x"][start - 1 : stop]
                ]
                heldout_values = [
                    value
                    for row in heldout
                    for value in row["expected_tau_1_to_19_world_x"][start - 1 : stop]
                ]
                overlap = min(max(train_values), max(heldout_values)) - max(
                    min(train_values), min(heldout_values)
                )
                support.append(
                    {
                        "outer_fold": fold,
                        "direction": direction,
                        "duration_bin": name,
                        "train_range": [min(train_values), max(train_values)],
                        "heldout_range": [min(heldout_values), max(heldout_values)],
                        "overlap_width_blocks": overlap,
                        "clean_frames_per_trajectory": stop - start + 1,
                        "pass": overlap > 0 and stop - start + 1 >= 3,
                    }
                )
    if not all(row["pass"] for row in support):
        raise RuntimeError("v2 grouped-fold target support failed")

    null_rows = []
    null_summary = []
    for fold in range(5):
        training = [row for row in specs if row["outer_fold"] != fold]
        heldout = sorted(row["trajectory_spec_id"] for row in specs if row["outer_fold"] == fold)
        ids = [row["trajectory_spec_id"] for row in training]
        strata = {row["trajectory_spec_id"]: row["direction"] for row in training}
        mappings = build_null_mappings(
            ids,
            strata,
            b=49,
            seed=deterministic_seed("A3_V2_NULL_FOLD", manifest_hash, fold),
        )
        validate_null_mappings(mappings, set(ids), strata)
        mapping_hashes = []
        for replicate, mapping in enumerate(mappings):
            body = {
                "schema_version": "regime-a-null-donor-map-v2.0",
                "outer_fold": fold,
                "replicate": replicate,
                "training_ids": sorted(ids),
                "heldout_ids": heldout,
                "stratum": "direction",
                "temporal_order_preserved": True,
                "heldout_true_targets_untouched": True,
                "mapping": dict(sorted(mapping.items())),
            }
            body["mapping_sha256"] = canonical_sha256(body)
            mapping_hashes.append(body["mapping_sha256"])
            null_rows.append(body)
        null_summary.append(
            {
                "outer_fold": fold,
                "training_count": 20,
                "heldout_count": 5,
                "unique_valid_mapping_count": len(set(mapping_hashes)),
                "B": 49,
                "no_self": True,
                "outer_training_only": True,
                "direction_stratified": True,
                "pass": len(set(mapping_hashes)) == 49,
            }
        )
    if not all(row["pass"] for row in null_summary):
        raise RuntimeError("v2 B49 feasibility failed")
    donor_payload = jsonl_bytes(null_rows)
    donor_hash = hashlib.sha256(donor_payload).hexdigest()

    folds = {
        "artifact_id": "regime-a-first25-v2-fold-receipt",
        "status": "PASS",
        "fold_counts": validation["fold_counts"],
        "direction_counts": validation["direction_counts"],
        "assignments": {row["trajectory_spec_id"]: row["outer_fold"] for row in specs},
    }
    target_support = {
        "artifact_id": "regime-a-first25-v2-target-support-receipt",
        "status": "PASS",
        "all_five_bins_every_trajectory": True,
        "minimum_clean_frames_per_bin": 3,
        "both_directions_feasible": True,
        "outer_train_heldout_support": support,
    }
    duplicates = {
        "artifact_id": "regime-a-first25-v2-duplicate-receipt",
        "status": "PASS",
        "exact_duplicate_count": 0,
        "near_duplicate_definition": "complete tau1..19 profile RMS world-x distance < 0.10 block",
        "near_duplicate_count": near_count,
        "minimum_pairwise_rms_blocks": min(row["rms_blocks"] for row in pair_rows),
        "pair_count": len(pair_rows),
    }
    starts = np.asarray([row["start_world_x"] for row in specs])
    onsets = [int(row["expected_stable_hidden_onset_frame"]) for row in specs]
    confound = {
        "artifact_id": "regime-a-first25-v2-confound-receipt",
        "status": "PASS_PROSPECTIVE_OUTCOME_BLIND",
        "trajectory_manifest_sha256": manifest_hash,
        "trajectory_count": 25,
        "direction_counts": validation["direction_counts"],
        "start_position": {
            "unique_count": len(set(starts.tolist())),
            "minimum": float(starts.min()),
            "maximum": float(starts.max()),
            "standard_deviation": float(starts.std()),
        },
        "stable_hidden_onset": {
            "unique_count": len(set(onsets)),
            "minimum_frame": min(onsets),
            "maximum_frame": max(onsets),
        },
        "unique_noise_schedule_count": len({row["noise_schedule_sha256"] for row in specs}),
        "grouped_fold_support_overlap": "PASS",
        "duplicate_control": "PASS",
        "time_only_reporting_required": True,
        "mandatory_target_specific_B49_null": True,
        "inherited_profile_thresholds_nontransferable": True,
        "neural_activations_used": False,
        "neural_outcomes_used": False,
    }
    b49 = {
        "artifact_id": "regime-a-first25-v2-b49-feasibility-receipt",
        "status": "PASS",
        "donor_manifest_sha256": donor_hash,
        "folds": null_summary,
    }
    precollection = {
        "artifact_id": "regime-a-first25-v2-canonical-precollection-authority",
        "status": "FROZEN_NOT_AUTHORIZED_FOR_EXECUTION",
        "scientific_run_id": RUN_ID,
        "trajectory_manifest_sha256": manifest_hash,
        "donor_manifest_sha256": donor_hash,
        "directional_visibility_authority_sha256": authority_hash,
        "trajectory_count": 25,
        "LTR_count": 13,
        "RTL_count": 12,
        "original_v1_seeds_preserved_count": preserved_seeds,
        "historical_v1_manifest_preserved_sha256": sha256_file(V1_MANIFEST),
        "historical_v1_donor_preserved_sha256": sha256_file(V1_DONORS),
        "scientific_trajectories_executed": 0,
        "scientific_activations_extracted": 0,
        "scientific_decoding_outcomes_computed": 0,
        "a4_v2_authorization_created": False,
    }
    return {
        "fresh_directional_calibration_report.json": report_bytes,
        "directional_visibility_authority.json": authority_payload,
        "trajectory_manifest.jsonl": manifest,
        "trajectory_manifest.sha256": (manifest_hash + "\n").encode(),
        "null_donor_manifest.jsonl": donor_payload,
        "null_donor_manifest.sha256": (donor_hash + "\n").encode(),
        "fold_receipt.json": json_bytes(folds),
        "target_support_receipt.json": json_bytes(target_support),
        "duplicate_receipt.json": json_bytes(duplicates),
        "confound_receipt.json": json_bytes(confound),
        "b49_feasibility_receipt.json": json_bytes(b49),
        "canonical_precollection_authority.json": json_bytes(precollection),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--calibration-report", type=Path, required=True)
    parser.add_argument("--raw-recovery-receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    documents = build_documents(args.calibration_report, args.raw_recovery_receipt)
    args.output.mkdir(parents=True, exist_ok=True)
    for name, payload in documents.items():
        (args.output / name).write_bytes(payload)
    print(
        json.dumps(
            {
                "status": "PASS",
                "files": {
                    name: hashlib.sha256(payload).hexdigest()
                    for name, payload in documents.items()
                },
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
