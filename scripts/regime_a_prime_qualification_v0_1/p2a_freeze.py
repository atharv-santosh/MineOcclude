"""P2.1/P2.2/P2.4/P2.5: prospective P2 authority freeze.

Emits, before any P2 no-wall capture or neural outcome exists:
  * p2_source_spec_binding.json  -- the 25 controlling Regime A specifications
  * p2_target_row_manifest.json  -- target ticks frozen from the WALL runs
  * p2_preoutcome_authority.json -- conditions, gates, procedures, qualification

The target rows are taken from the historical wall runs and may never be added
to, removed, or shifted because of a P2 decoder outcome.
"""

from __future__ import annotations

import json
from typing import Any

from p2_common import (
    AMEND,
    CONF,
    INTEG,
    LAYER,
    OUT,
    P1_HEAD,
    PM,
    REPO,
    S3_PREFIX,
    TAUS,
    WALL_META,
    WORK,
    p2_episode_id,
    p2_run_id,
    raw_capture_spec_hash,
    run_git,
    sha256_file,
    sha256_obj,
    source_specs,
    wall_target_frames,
    write_json,
)

# Fields carried verbatim from the controlling manifest into the P2 binding.
BOUND_FIELDS = [
    "trajectory_spec_id", "scientific_run_id", "episode_id", "seed", "noise_seed",
    "direction", "speed_blocks_per_second", "motion_noise_q", "initial_motion_phase",
    "start_world_x", "start_world_y", "start_world_z", "expected_max_frames",
    "outer_fold", "spec_hash", "raw_capture_spec_hash", "original_v2_spec_hash",
    "noise_schedule_sha256", "expected_profile_sha256", "camera_authority",
    "wall_authority", "target_entity_logical_id", "entry_guard_frames",
    "exit_guard_frames", "expected_stable_hidden_onset_frame",
    "expected_stable_hidden_exit_frame", "amended_analysis_authority",
    "retry_policy", "schema_version",
]


def main() -> int:
    head = run_git("rev-parse", "HEAD")
    if head != P1_HEAD:
        raise RuntimeError(f"unexpected HEAD {head}")
    specs = source_specs()

    # ---- P2.1 source specification binding --------------------------------
    bindings: list[dict[str, Any]] = []
    for spec in specs:
        spec_id = str(spec["trajectory_spec_id"])
        frames, taus = wall_target_frames(spec_id)
        bindings.append({
            "source_regime_a_spec_id": spec_id,
            "source_regime_a_wall_run_id": spec_id,
            "source_wall_episode_id": int(spec["episode_id"]),
            "p2_no_wall_run_id": p2_run_id(spec_id),
            "p2_no_wall_episode_id": p2_episode_id(spec),
            "classification": "EXPLORATORY_MATCHED_DIAGNOSTIC",
            "confirmatory_membership": False,
            "wall_run_recollected": False,
            "source_spec": {k: spec[k] for k in BOUND_FIELDS if k in spec},
            "wall_target_model_frame_indices": frames,
            "wall_target_tau": taus,
            "durable_source_receipt_sha256": sha256_file(
                WALL_META / spec_id / "durable_receipt.json"
            ),
            "wall_coordinates_sha256": sha256_file(
                WALL_META / spec_id / "coordinates.jsonl"
            ),
            "wall_visibility_sha256": sha256_file(
                WALL_META / spec_id / "visibility.jsonl"
            ),
        })

    ids = [b["p2_no_wall_run_id"] for b in bindings]
    if len(set(ids)) != 25:
        raise RuntimeError("P2 run ids are not unique")
    if set(ids) & {b["source_regime_a_wall_run_id"] for b in bindings}:
        raise RuntimeError("P2 run id collides with a historical wall run id")

    binding_payload = {
        "artifact_id": "regime-a-prime-p2-source-spec-binding-v0.1",
        "schema_version": "1.0",
        "phase": "P2",
        "classification": "EXPLORATORY_MATCHED_DIAGNOSTIC",
        "status": "FROZEN_PRE_OUTCOME",
        "source_p1_commit": head,
        "controlling_manifest": {
            "path": str((AMEND / "trajectory_manifest_v2_1_amendment_1.jsonl").relative_to(REPO)),
            "sha256": sha256_file(AMEND / "trajectory_manifest_v2_1_amendment_1.jsonl"),
            "why_controlling": "v2.1 amendment 1 supersedes the original v2 manifest "
                               "for analysis identity while preserving the physical "
                               "capture contract via raw_capture_spec_hash",
        },
        "spec_provenance_map_sha256": sha256_file(AMEND / "spec_provenance_map.json"),
        "amended_visibility_authority_sha256": sha256_file(
            AMEND / "directional_visibility_authority_v2_1_amendment_1.json"
        ),
        "source_spec_count": len(bindings),
        "mapping": bindings,
        "mapping_integrity_sha256": sha256_obj(bindings),
    }
    write_json(OUT / "p2_source_spec_binding.json", binding_payload)

    # ---- P2.2 target row manifest (frozen from the WALL runs) -------------
    rows: list[dict[str, Any]] = []
    for b in bindings:
        frames, taus = b["wall_target_model_frame_indices"], b["wall_target_tau"]
        if taus != TAUS:
            raise RuntimeError(f"unexpected tau set for {b['source_regime_a_spec_id']}")
        for order, (frame, tau) in enumerate(zip(frames, taus)):
            rows.append({
                "source_regime_a_spec_id": b["source_regime_a_spec_id"],
                "p2_no_wall_run_id": b["p2_no_wall_run_id"],
                "tau": tau,
                "target_model_frame_idx": frame,
                "target_server_tick": frame,
                "target_order": order,
                "outer_fold": int(b["source_spec"]["outer_fold"]),
                "direction": b["source_spec"]["direction"],
            })

    target_payload = {
        "artifact_id": "regime-a-prime-p2-target-row-manifest-v0.1",
        "schema_version": "1.0",
        "phase": "P2",
        "status": "FROZEN_PRE_OUTCOME",
        "frozen_before_any_p2_capture_or_outcome": True,
        "selection_rule": "the exact target model frames / server ticks of the "
                          "HISTORICAL WALL run, taken from its bound activation "
                          "inventory; the no-wall counterpart is sampled at the same "
                          "physical target times",
        "target_times_may_change_after_outcomes": False,
        "rows_per_spec": len(TAUS),
        "spec_count": len(bindings),
        "total_target_rows": len(rows),
        "tau_set": TAUS,
        "rows": rows,
        "manifest_integrity_sha256": sha256_obj(rows),
        "quality_recovery_rule": "a row may only be dropped for an operational defect "
                                 "declared under the frozen recovery policy, never for "
                                 "decoder performance; any drop must be disclosed",
    }
    write_json(OUT / "p2_target_row_manifest.json", target_payload)

    # ---- P2.4 visible qualification rule + P2.5 pre-outcome authority -----
    path_authority = json.loads((OUT / "p2_path_equivalence_authority.json").read_text())

    authority = {
        "artifact_id": "regime-a-prime-p2-preoutcome-authority-v0.1",
        "schema_version": "1.0",
        "phase": "P2",
        "classification": "EXPLORATORY_MATCHED_DIAGNOSTIC",
        "status": "FROZEN_PRE_OUTCOME",
        "source_p1_commit": head,
        "branch": run_git("branch", "--show-current"),
        "purpose": "Test whether the exact low-N layer-4 readout recovers sheep "
                   "position when the sheep is VISIBLE at the SAME physical target "
                   "times under mechanically matched trajectory conditions.",
        "p2_is_not_the_confirmatory_experiment": True,
        "p2_trajectories_are_permanently_nonconfirmatory": True,
        "condition_definition": {
            "historical_wall": {"server_command": "mineocclude mode normal",
                                "scene": "NORMAL", "recollected": False},
            "p2_no_wall": {"server_command": "mineocclude mode nowall",
                           "scene": "NO_WALL", "newly_collected": True},
            "only_manipulated_factor": "presence of the occluding wall",
            "held_identical": [
                "seed", "noise schedule", "direction", "nominal speed",
                "motion policy", "initial state", "camera", "FOV", "cadence",
                "frame/action semantics", "target timestamps", "fold assignment",
                "checkpoint", "preprocessing",
            ],
            "known_limitation": "removing the wall changes scene pixels as well as "
                                "visibility; P2 is therefore a COMPOUND contrast and "
                                "cannot attribute effects to occlusion alone",
        },
        "source_specifications": {
            "count": 25,
            "binding_artifact": "p2_source_spec_binding.json",
            "mapping_integrity_sha256": binding_payload["mapping_integrity_sha256"],
        },
        "target_rows": {
            "artifact": "p2_target_row_manifest.json",
            "total": len(rows),
            "per_spec": len(TAUS),
            "integrity_sha256": target_payload["manifest_integrity_sha256"],
            "frozen_pre_outcome": True,
        },
        "path_identity_rules": {
            "epsilon_path": path_authority["epsilon_path"],
            "epsilon_path_basis": path_authority["epsilon_path_basis"],
            "rule": path_authority["path_equivalence_rule"],
            "authority_artifact": "p2_path_equivalence_authority.json",
            "frozen_before_outcomes": True,
            "exact_agreement_required_fields": [
                "source specification identity/mapping", "seed", "motion policy",
                "direction", "nominal speed", "noise draws", "target tick ids",
                "capture cadence", "frame/action mapping", "target row count",
                "target row ordering",
            ],
        },
        "extraction": {
            "layers": [LAYER],
            "all_layer_extraction_forbidden": True,
            "gated_on_path_equivalence_pass": True,
            "visual_tokens_per_target": 336,
            "context_pairs": 16,
            "context_rule": "indices = range(target-15, target+1), teacher forced",
        },
        "frozen_readouts": {
            "BEST_K": {
                "procedure": "frozen nested TRAINING-ONLY BEST-K from the closed "
                             "Regime A analysis; k/alpha selected inside the training "
                             "split of each outer fold only",
                "authority": "docs/.../first25_analysis/slice_best_k_results.json",
                "authority_sha256": sha256_file(CONF / "slice_best_k_results.json"),
                "k_or_alpha_may_be_tuned_on_p2_outcomes": False,
            },
            "FULL": {
                "procedure": "frozen FULL_TOKEN_GRID ridge readout",
                "secondary": True,
                "may_be_restored_as_primary_by_passing_here": False,
            },
            "evaluation": "existing trajectory-grouped outer folds; no frame-level "
                          "splitting; standardization fit on outer-training rows only",
        },
        "p2_visible_qualification_rule": {
            "id": "P2_BEST_K_VISIBLE_QUALIFICATION_v0.1",
            "pre_existing_project_rule_found": False,
            "frozen_before_any_p2_neural_outcome": True,
            "criteria": [
                "frozen layer-4 BEST-K procedure used without test leakage",
                "trajectory-equal visible macro R2 > 0",
                "deterministic whole-trajectory 95% bootstrap lower bound for "
                "visible macro R2 > 0",
                "RMSE and MAE in world blocks reported continuously",
                "no pooled-row metric may override the trajectory-equal result",
                "all path/identity/quality gates pass",
            ],
            "bootstrap": {"resamples": 10000, "seed": 20260815,
                          "unit": "WHOLE_TRAJECTORY"},
            "scope_limits": {
                "is_future_a_prime_primary_success_criterion": False,
                "is_E_vis_max": False,
                "is_final_a_prime_rmse_margin": False,
                "is_confirmatory_threshold": False,
            },
            "full_readout_treatment": "report the same continuous diagnostics and "
                                      "classify against the same criterion; FULL "
                                      "remains secondary regardless of outcome",
        },
        "recovery_policy": {
            "atomic_unit": "one P2 no-wall run",
            "on_operational_failure": "retry the SAME frozen spec/seed",
            "seed_substitution_forbidden": True,
            "favorable_unit_duplication_forbidden": True,
            "skipping_difficult_units_forbidden": True,
            "max_attempts_per_unit": 3,
            "ledger": "p2_capture_ledger.jsonl",
        },
        "expected_artifact_inventory": {
            "no_wall_runs": 25,
            "target_rows": len(rows),
            "activation_rows": len(rows),
            "activation_shape_per_run": [len(TAUS), 336, 2048],
            "activation_dtype": "float16",
            "layers": [LAYER],
        },
        "durability": {
            "working_root": str(WORK),
            "durable_prefix": S3_PREFIX,
            "large_artifacts_in_git": False,
        },
        "runtime_rebuild_disclosure": path_authority["runtime_rebuild"],
        "contamination_status": {
            "p2_data_confirmatory_membership": False,
            "p2_is_diagnostic_tier_3": True,
            "diagnostic_to_confirmatory_reuse": "PROHIBITED",
            "historical_wall_runs_recollected": 0,
        },
        "P3_NOT_STARTED": True,
        "REGIME_A_PRIME_COLLECTION_AUTHORIZED": "NO",
    }
    digest = write_json(OUT / "p2_preoutcome_authority.json", authority)

    print("P2_FREEZE_STATUS=FROZEN_PRE_OUTCOME")
    print(f"P2_SOURCE_SPEC_COUNT={len(bindings)}")
    print(f"P2_TOTAL_TARGET_ROWS={len(rows)}")
    print(f"P2_EPSILON_PATH={path_authority['epsilon_path']}")
    print(f"P2_PREOUTCOME_AUTHORITY_SHA256={digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
