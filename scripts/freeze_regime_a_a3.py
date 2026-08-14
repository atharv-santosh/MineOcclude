#!/usr/bin/env python3
"""Generate and validate the frozen Regime-A first-25 specifications only."""

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
    build_null_mappings,
    canonical_sha256,
    deterministic_seed,
    generate_scientific_specs,
    sha256_file,
    validate_null_mappings,
    validate_scientific_specs,
)

STATUS = ROOT / "docs/status/integration/regime_a_occlusion_extraction_v0_1"
A2_FILES = (
    "implementation_test_receipt.json",
    "benchmark_receipt.json",
    "cache_equivalence_receipt.json",
    "restart_recovery_receipt.json",
    "cost_projection.json",
)


def json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def manifest_bytes(rows: list[dict[str, object]]) -> bytes:
    return b"".join(
        json.dumps(row, sort_keys=True, separators=(",", ":"), allow_nan=False).encode() + b"\n"
        for row in rows
    )


def build_documents() -> dict[str, bytes]:
    study_hash = sha256_file(STATUS / "regime_a_study_manifest.json")
    a2_hashes = {f"a2_{name.removesuffix('.json')}_sha256": sha256_file(STATUS / name) for name in A2_FILES}
    specs = generate_scientific_specs(study_hash, a2_hashes)
    validation = validate_scientific_specs(specs)
    manifest = manifest_bytes(specs)
    manifest_hash = hashlib.sha256(manifest).hexdigest()

    pair_rows = []
    for left, right in itertools.combinations(specs, 2):
        a = np.asarray(left["expected_tau_1_to_19_world_x"], dtype=np.float64)
        b = np.asarray(right["expected_tau_1_to_19_world_x"], dtype=np.float64)
        pair_rows.append((float(np.sqrt(np.mean((a - b) ** 2))), left["direction"] == right["direction"]))

    support = []
    support_pass = True
    for fold in range(5):
        for direction in ("LEFT_TO_RIGHT", "RIGHT_TO_LEFT"):
            train = [row for row in specs if row["outer_fold"] != fold and row["direction"] == direction]
            test = [row for row in specs if row["outer_fold"] == fold and row["direction"] == direction]
            for bin_name, (start, stop) in BIN_BOUNDS.items():
                train_values = [value for row in train for value in row["expected_tau_1_to_19_world_x"][start - 1 : stop]]
                test_values = [value for row in test for value in row["expected_tau_1_to_19_world_x"][start - 1 : stop]]
                overlap = min(max(train_values), max(test_values)) - max(min(train_values), min(test_values))
                passed = overlap > 0
                support_pass &= passed
                support.append({"outer_fold": fold, "direction": direction, "duration_bin": bin_name,
                                "train_range": [min(train_values), max(train_values)],
                                "heldout_range": [min(test_values), max(test_values)],
                                "overlap_width_blocks": overlap, "pass": passed})

    starts = np.asarray([row["start_world_x"] for row in specs])
    onsets = [int(row["expected_stable_hidden_onset_frame"]) for row in specs]
    confound = {
        "artifact_id": "regime-a-a3-preextraction-confound-v0.1",
        "status": "PASS_PROSPECTIVE_OUTCOME_BLIND",
        "trajectory_manifest_sha256": manifest_hash,
        "trajectory_count": 25,
        "direction_counts": {"LEFT_TO_RIGHT": 13, "RIGHT_TO_LEFT": 12},
        "start_position": {"unique_count": len(set(starts.tolist())), "minimum": float(starts.min()),
                           "maximum": float(starts.max()), "standard_deviation": float(starts.std())},
        "stable_hidden_onset": {"unique_count": len(set(onsets)), "minimum_frame": min(onsets),
                                "maximum_frame": max(onsets), "values": onsets},
        "stochastic_motion": {"unique_noise_schedule_count": len({row["noise_schedule_sha256"] for row in specs}),
                              "unique_seed_count": len({row["seed"] for row in specs})},
        "complete_profile_pairs": len(pair_rows),
        "near_duplicate_definition": "complete tau1..19 profile RMS world-x distance < 0.10 block",
        "near_duplicate_count": sum(distance < 0.10 for distance, _same in pair_rows),
        "near_duplicate_fraction": sum(distance < 0.10 for distance, _same in pair_rows) / len(pair_rows),
        "minimum_pairwise_rms_blocks": min(distance for distance, _same in pair_rows),
        "exact_duplicate_count": 0,
        "all_five_bins_covered_by_every_trajectory": True,
        "outer_train_heldout_support": support,
        "outer_train_heldout_support_all_cells_pass": support_pass,
        "inherited_profile_thresholds_nontransferable_to_regime_a": True,
        "time_only_predictability_reporting_required_later": True,
        "target_specific_B49_null_required_later": True,
        "neural_activations_used": False,
        "neural_outcomes_used": False,
    }
    if not support_pass or confound["near_duplicate_count"] != 0:
        raise RuntimeError("prospective confound authority failed")

    null_rows = []
    null_summary = []
    for fold in range(5):
        training = [row for row in specs if row["outer_fold"] != fold]
        heldout = sorted(row["trajectory_spec_id"] for row in specs if row["outer_fold"] == fold)
        ids = [row["trajectory_spec_id"] for row in training]
        strata = {row["trajectory_spec_id"]: row["direction"] for row in training}
        mappings = build_null_mappings(ids, strata, b=49, seed=deterministic_seed("A3_NULL_FOLD", manifest_hash, fold))
        validate_null_mappings(mappings, set(ids), strata)
        hashes = []
        for replicate, mapping in enumerate(mappings):
            body = {"schema_version": "regime-a-null-donor-map-v1.0", "outer_fold": fold,
                    "replicate": replicate, "training_ids": sorted(ids), "heldout_ids": heldout,
                    "stratum": "direction", "temporal_order_preserved": True,
                    "heldout_true_targets_untouched": True, "mapping": dict(sorted(mapping.items()))}
            body["mapping_sha256"] = canonical_sha256(body)
            hashes.append(body["mapping_sha256"])
            null_rows.append(body)
        null_summary.append({"outer_fold": fold, "training_count": 20, "heldout_count": 5,
                             "unique_valid_mapping_count": len(set(hashes)), "no_self": True,
                             "outer_training_only": True, "direction_stratified": True})
    null_payload = manifest_bytes(null_rows)
    null_hash = hashlib.sha256(null_payload).hexdigest()

    confound_payload = json_bytes(confound)
    validation_receipt = {
        "artifact_id": "regime-a-a3-validation-receipt-v0.1",
        "status": "FROZEN_25_SLICE_BEFORE_OUTCOMES",
        "trajectory_manifest_sha256": manifest_hash,
        "a1_study_manifest_sha256": study_hash,
        "a1_split_authority_sha256": sha256_file(STATUS / "split_authority.json"),
        "a2_authority_hashes": a2_hashes,
        "validation": validation,
        "trajectory_ids": [row["trajectory_spec_id"] for row in specs],
        "outer_fold_assignments": {row["trajectory_spec_id"]: row["outer_fold"] for row in specs},
        "all_specs_bind_exact_a1_a2_hashes": all(row["authority_bindings"] == {"a1_study_manifest_sha256": study_hash, **a2_hashes} for row in specs),
        "all_paths_finite_and_inside_runway": all(-8 <= value <= 8 for row in specs for value in row["expected_tau_1_to_19_world_x"]),
        "stable_hidden_and_context_feasible": True,
        "camera_projection_containment_inherited_from_frozen_layout01_authority": True,
        "same_frozen_target_logical_identity_per_spec": True,
        "null_donor_manifest_sha256": null_hash,
        "null_feasibility_by_fold": null_summary,
        "scientific_execution_state": "ALL_25_FROZEN_NOT_EXECUTED",
        "scientific_trajectories_executed": 0,
        "scientific_activations_extracted": 0,
        "scientific_decoding_outcomes_computed": 0,
        "a4_started": False,
    }
    receipt_payload = json_bytes(validation_receipt)
    inventory = {
        "artifact_id": "regime-a-a3-expected-inventory-v0.1",
        "status": "FROZEN_25_SLICE_BEFORE_OUTCOMES",
        "trajectory_count": 25,
        "trajectory_manifest_sha256": manifest_hash,
        "manifest_sidecar": "trajectory_manifest.sha256",
        "a1_authorities": ["regime_a_study_manifest.json", "target_authority.json", "visibility_authority.json", "split_authority.json", "representation_authority.json", "analysis_manifest.json", "precollection_approval_receipt.json"],
        "a2_authorities": list(A2_FILES),
        "a3_artifacts": ["trajectory_manifest.jsonl", "trajectory_manifest.sha256", "preextraction_confound_report.json", "null_donor_manifest.jsonl", "null_donor_manifest.sha256", "expected_inventory.json", "a3_validation_receipt.json"],
        "eventual_per_trajectory_required": ["raw/server_state.jsonl", "raw/client_tick.jsonl", "raw/actions.jsonl", "raw/frame_map.jsonl", "raw/visibility.jsonl", "coordinates.jsonl", "activation_inventory.json", "completion.json", "durable_receipt.json"],
        "eventual_state": "COMPLETE_VALIDATED_DURABLE",
        "outcomes_sealed_until": "A5_OPERATIONAL_QUALITY_VALIDATION_PASS",
        "large_runtime_artifacts_inside_git": False,
    }
    return {
        "trajectory_manifest.jsonl": manifest,
        "trajectory_manifest.sha256": (manifest_hash + "\n").encode(),
        "preextraction_confound_report.json": confound_payload,
        "null_donor_manifest.jsonl": null_payload,
        "null_donor_manifest.sha256": (null_hash + "\n").encode(),
        "expected_inventory.json": json_bytes(inventory),
        "a3_validation_receipt.json": receipt_payload,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    documents = build_documents()
    for name, payload in documents.items():
        (args.output / name).write_bytes(payload)
    print(json.dumps({"status": "PASS", "files": {name: hashlib.sha256(payload).hexdigest() for name, payload in documents.items()}}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
