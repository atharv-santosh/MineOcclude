#!/usr/bin/env python3
"""Freeze the outcome-blind Regime A-prime P3 development authority.

This script performs deterministic design work only.  It does not launch
Minecraft, capture pixels, extract activations, use a GPU, or score a neural
readout.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
from pathlib import Path
from typing import Any

import numpy as np


REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "docs/status/integration/regime_a_prime_qualification_v0_1"
P2_COMMIT = "c2ca2472e77934ba4780139f3f9743e8bcf74b78"
BRANCH = "exploration/regime-a-prime-qualification-v0-1"
DESIGN_NAMESPACE = "MINEOCCLUDE_P3_DEV_V0_1"
SPEEDS = (2.0, 2.5, 3.0)
PHASE_OFFSETS = (0, 3, 6, 9, 12)
FRAMES = 180
DT_SECONDS = 0.05
CAPTURE_HZ = 20
MOTION_NOISE_Q = 0.05
TARGET_TAUS = tuple(range(1, 20))
P2_BEST_K_RMSE_BLOCKS = 0.1660274234445584
MIN_TRAJECTORY_SD_BLOCKS = 2.0 * P2_BEST_K_RMSE_BLOCKS
MIN_MEDIAN_SD_BLOCKS = 3.0 * P2_BEST_K_RMSE_BLOCKS
ABSOLUTE_RMSE_CEILING_BLOCKS = 2.0 * P2_BEST_K_RMSE_BLOCKS
TIME_ONLY_MACRO_R2_MAX = 0.10
HIDDEN_BOUNDS = {
    "LEFT_TO_RIGHT": (-3.7309960703951197, 5.42739195539593),
    "RIGHT_TO_LEFT": (4.837594280703691, -4.4614025063149105),
}


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=REPO, check=True, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    return result.stdout.strip()


def seed_for(label: str) -> int:
    material = f"{DESIGN_NAMESPACE}|{P2_COMMIT}|{label}".encode()
    return int.from_bytes(hashlib.sha256(material).digest()[:8], "big") & ((1 << 63) - 1)


def noise_and_path(seed: int, direction: str, speed: float) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    noise = rng.standard_normal(FRAMES) * math.sqrt(MOTION_NOISE_Q * DT_SECONDS)
    sign = 1.0 if direction == "LEFT_TO_RIGHT" else -1.0
    position = -7.8 if sign > 0 else 7.8
    path: list[float] = []
    for draw in noise:
        position = min(8.0, max(-8.0, position + sign * speed * DT_SECONDS + float(draw)))
        path.append(position)
    return noise.astype("<f8"), np.asarray(path, dtype="<f8")


def first_stable_hidden_onset(path: np.ndarray, direction: str) -> int:
    entry, exit_ = HIDDEN_BOUNDS[direction]
    inside = ((path >= entry) & (path <= exit_)) if direction == "LEFT_TO_RIGHT" else (
        (path <= entry) & (path >= exit_)
    )
    # Thirty-one frames cover the maximum phase offset plus all 19 targets.
    for index in range(15, len(path) - 31):
        if bool(inside[index:index + 31].all()):
            return index
    raise RuntimeError("path lacks the prospectively required stable-hidden span")


def design_cells() -> list[dict[str, Any]]:
    """Five folds x five phases, with 13/12 direction balance."""
    ltr_phases = {
        0: {0, 1, 2},
        1: {2, 3},
        2: {4, 0, 1},
        3: {1, 2},
        4: {3, 4, 0},
    }
    cells: list[dict[str, Any]] = []
    for fold in range(5):
        for phase_index, phase in enumerate(PHASE_OFFSETS):
            cells.append({
                "outer_fold": fold,
                "occlusion_phase_frames": phase,
                "direction": (
                    "LEFT_TO_RIGHT" if phase_index in ltr_phases[fold]
                    else "RIGHT_TO_LEFT"
                ),
            })
    assert len(cells) == 25
    assert sum(row["direction"] == "LEFT_TO_RIGHT" for row in cells) == 13
    return cells


def build_manifest() -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    all_seeds: set[int] = set()
    cells = design_cells()
    for candidate_index, speed in enumerate(SPEEDS, 1):
        candidate_id = f"P3DEV_C{candidate_index:02d}"
        specs: list[dict[str, Any]] = []
        for spec_index, cell in enumerate(cells, 1):
            spec_id = f"p3dev_c{candidate_index:02d}_t{spec_index:02d}"
            seed = seed_for(f"C{candidate_index:02d}|T{spec_index:02d}")
            if seed in all_seeds:
                raise RuntimeError("seed collision")
            all_seeds.add(seed)
            noise, path = noise_and_path(seed, cell["direction"], speed)
            onset = first_stable_hidden_onset(path, cell["direction"])
            target_start = onset + int(cell["occlusion_phase_frames"])
            ticks = list(range(target_start, target_start + len(TARGET_TAUS)))
            targets = path[ticks]
            spec: dict[str, Any] = {
                "schema_version": "regime-a-prime-p3-development-spec-v0.1",
                "candidate_id": candidate_id,
                "trajectory_spec_id": spec_id,
                "classification": "DEVELOPMENT_PREFLIGHT",
                "confirmatory_membership": False,
                "permanently_excluded_from_confirmatory_a_prime": True,
                "execution_state": "FROZEN_NOT_EXECUTED",
                "seed": seed,
                "noise_seed": seed,
                "direction": cell["direction"],
                "outer_fold": cell["outer_fold"],
                "speed_blocks_per_second": speed,
                "motion_noise_q": MOTION_NOISE_Q,
                "start_world_xyz": [-7.8 if cell["direction"] == "LEFT_TO_RIGHT" else 7.8, 4.0, 6.0],
                "expected_max_frames": FRAMES,
                "occlusion_phase_frames": cell["occlusion_phase_frames"],
                "expected_stable_hidden_onset_server_tick": onset,
                "target_tau": list(TARGET_TAUS),
                "target_server_ticks": ticks,
                "target_timestamps_seconds": [tick * DT_SECONDS for tick in ticks],
                "expected_target_world_x_blocks": [float(value) for value in targets],
                "expected_target_sd_blocks": float(np.std(targets)),
                "expected_target_range_blocks": float(np.ptp(targets)),
                "noise_schedule_sha256": hashlib.sha256(noise.tobytes()).hexdigest(),
                "expected_path_sha256": hashlib.sha256(path.tobytes()).hexdigest(),
                "paired_runs": {
                    "NORMAL": {
                        "run_id": f"{spec_id}_wall",
                        "episode_id": 71000 + candidate_index * 1000 + spec_index,
                        "scene": "NORMAL",
                    },
                    "NO_WALL": {
                        "run_id": f"{spec_id}_nowall",
                        "episode_id": 71500 + candidate_index * 1000 + spec_index,
                        "scene": "NO_WALL",
                    },
                },
            }
            body = dict(spec)
            spec["spec_hash"] = canonical_sha256(body)
            specs.append(spec)

        calibration_specs = []
        for direction_index, direction in enumerate(("LEFT_TO_RIGHT", "RIGHT_TO_LEFT")):
            for replicate in (1, 2):
                short = "ltr" if direction == "LEFT_TO_RIGHT" else "rtl"
                calibration_id = f"p3dev_c{candidate_index:02d}_viscal_{short}_r{replicate:02d}"
                calibration_seed = seed_for(
                    f"C{candidate_index:02d}|VISCAL|{direction}|R{replicate:02d}"
                )
                if calibration_seed in all_seeds:
                    raise RuntimeError("calibration seed collision")
                all_seeds.add(calibration_seed)
                calibration_specs.append({
                    "calibration_id": calibration_id,
                    "episode_id": 75000 + candidate_index * 100 + direction_index * 10 + replicate,
                    "seed": calibration_seed,
                    "noise_seed": calibration_seed,
                    "direction": direction,
                    "speed_blocks_per_second": speed,
                    "motion_noise_q": MOTION_NOISE_Q,
                    "start_world_xyz": [-7.8 if direction == "LEFT_TO_RIGHT" else 7.8, 4.0, 6.0],
                    "expected_max_frames": FRAMES,
                    "classification": "NON_SCIENTIFIC_VISIBILITY_CALIBRATION",
                    "confirmatory_membership": False,
                })

        sds = [row["expected_target_sd_blocks"] for row in specs]
        candidates.append({
            "candidate_id": candidate_id,
            "order": candidate_index,
            "motion_parameter": {"speed_blocks_per_second": speed},
            "status": "FROZEN_NOT_EXECUTED",
            "trajectory_count": len(specs),
            "paired_capture_count": 2 * len(specs),
            "visibility_calibration_specs": calibration_specs,
            "prospective_path_headroom": {
                "minimum_target_sd_blocks": min(sds),
                "median_target_sd_blocks": float(np.median(sds)),
                "maximum_target_sd_blocks": max(sds),
                "minimum_threshold_blocks": MIN_TRAJECTORY_SD_BLOCKS,
                "median_threshold_blocks": MIN_MEDIAN_SD_BLOCKS,
                "passes_deterministic_design_check": (
                    min(sds) >= MIN_TRAJECTORY_SD_BLOCKS
                    and float(np.median(sds)) >= MIN_MEDIAN_SD_BLOCKS
                ),
            },
            "specs": specs,
        })

    return {
        "artifact_id": "regime-a-prime-p3-development-manifest-v0.1",
        "schema_version": "1.0",
        "status": "FROZEN_NOT_EXECUTED",
        "classification": "DEVELOPMENT_PREFLIGHT",
        "confirmatory_membership": False,
        "source_p2_closeout_commit": P2_COMMIT,
        "design_namespace": DESIGN_NAMESPACE,
        "candidate_count": len(candidates),
        "development_trajectory_specs": sum(len(row["specs"]) for row in candidates),
        "paired_development_runs_if_all_candidates_needed": sum(row["paired_capture_count"] for row in candidates),
        "visibility_calibration_runs_if_all_candidates_needed": sum(len(row["visibility_calibration_specs"]) for row in candidates),
        "candidate_execution_is_sequential_not_parallel": True,
        "candidates": candidates,
    }


def source_binding(path: str) -> dict[str, str]:
    target = REPO / path
    return {"path": path, "sha256": sha256_file(target)}


def build_authority(manifest_sha256: str) -> dict[str, Any]:
    sources = {
        "p2_closeout": source_binding("docs/status/integration/regime_a_prime_qualification_v0_1/p2_closeout_receipt.json"),
        "p2_preoutcome": source_binding("docs/status/integration/regime_a_prime_qualification_v0_1/p2_preoutcome_authority.json"),
        "p2_readout": source_binding("docs/status/integration/regime_a_prime_qualification_v0_1/p2_readout_authority_receipt.json"),
        "p2_best_k": source_binding("docs/status/integration/regime_a_prime_qualification_v0_1/p2_best_k_results.json"),
        "p2_full": source_binding("docs/status/integration/regime_a_prime_qualification_v0_1/p2_full_results.json"),
        "closed_postmortem": source_binding("docs/status/integration/regime_a_occlusion_extraction_v0_1/postmortem_v0_1/postmortem_report.md"),
        "d1_headroom": source_binding("docs/status/integration/regime_a_occlusion_extraction_v0_1/postmortem_v0_1/d1_headroom.json"),
        "camera_geometry": source_binding("docs/status/integration/regime_a_occlusion_extraction_v0_1/geometry_camera_authority.json"),
        "directional_visibility": source_binding("docs/status/integration/regime_a_occlusion_extraction_v0_1/v2_amendment_1/directional_visibility_authority_v2_1_amendment_1.json"),
        "magenta_detector": source_binding("docs/status/person_e_phase3_step3_1_candidate_freeze_v0_1/detector_candidate_config.json"),
    }
    return {
        "artifact_id": "regime-a-prime-p3-development-preoutcome-authority-v0.1",
        "schema_version": "1.0",
        "phase": "P3",
        "status": "FROZEN_BEFORE_P3_EXECUTION_OR_OUTCOMES",
        "classification": "DEVELOPMENT_PREFLIGHT",
        "confirmatory_membership": False,
        "source_p2_closeout_commit": P2_COMMIT,
        "source_bindings": sources,
        "purpose": "Find the first and therefore minimum member of a prospectively ordered motion-headroom sequence that qualifies the fixed apparatus for later, entirely new confirmatory Regime A-prime design.",
        "scope_boundary": {
            "p3_started": False,
            "minecraft_started_by_this_freeze": False,
            "gpu_used_by_this_freeze": False,
            "p3_may_authorize_confirmatory_collection": False,
            "REGIME_A_PRIME_COLLECTION_AUTHORIZED": "NO",
            "all_p3_calibration_and_trajectory_data_permanently_excluded_from_confirmatory_a_prime": True,
            "eventual_confirmatory_cohort_must_be_entirely_new": True,
            "eventual_confirmatory_wall_and_no_wall_renderer_apparatus_must_be_one_prospectively_pinned_runtime": True,
        },
        "development_manifest": {
            "path": "docs/status/integration/regime_a_prime_qualification_v0_1/p3_development_manifest.json",
            "sha256": manifest_sha256,
            "candidate_count": 3,
            "specs_per_candidate": 25,
            "paired_scenes": ["NORMAL", "NO_WALL"],
        },
        "ordered_search": {
            "only_variable": "speed_blocks_per_second",
            "candidate_sequence": [
                {"order": 1, "candidate_id": "P3DEV_C01", "speed_blocks_per_second": 2.0},
                {"order": 2, "candidate_id": "P3DEV_C02", "speed_blocks_per_second": 2.5},
                {"order": 3, "candidate_id": "P3DEV_C03", "speed_blocks_per_second": 3.0},
            ],
            "initial_candidate": "P3DEV_C01",
            "advance_rule": "Advance exactly one candidate only after the prior candidate has a terminal FAIL against this frozen rule; operational failures retry only the identical unit and do not authorize advancement or substitution.",
            "stop_rule": "STOP immediately at the first PASS. If P3DEV_C03 fails, stop BLOCKED_REQUIRES_NEW_PROSPECTIVE_AUTHORITY.",
            "parallel_candidate_execution_forbidden": True,
            "candidate_skipping_forbidden": True,
            "candidate_reordering_forbidden": True,
            "new_candidates_or_threshold_changes_after_outcomes_forbidden": True,
            "broad_grid_search_forbidden": True,
        },
        "fixed_apparatus": {
            "layout_id": "layout_01",
            "camera_authority": "layout_01_fixed_v0.4",
            "camera_fixed": True,
            "camera_feet_world_xyz": [0.5, 4.0, -5.5],
            "camera_eye_world_xyz": [0.5, 5.6200000048, -5.5],
            "yaw_pitch_roll_degrees": [0.0, 0.0, 0.0],
            "fov_degrees": 70.0,
            "canonical_frame_pixels": [640, 360],
            "model_input_pixels": [384, 224],
            "visual_token_grid": [14, 24],
            "visual_token_count": 336,
            "wall_authority": "layout_01_long_wall_v0.4",
            "lane": {"axis": "x", "min_blocks": -8.0, "max_blocks": 8.0, "y": 4.0, "z": 6.0},
            "camera_or_fov_change_in_sequence_allowed": False,
            "camera_change_rule": "Any camera, FOV, resolution, projection, renderer, or layout change invalidates this authority and requires a new prospective authority plus fresh dual-detector visibility calibration before capture.",
        },
        "motion_and_sampling": {
            "motion_noise_q": MOTION_NOISE_Q,
            "motion_recurrence": "x[t] = clamp(-8, 8, x[t-1] + signed_speed*0.05 + frozen_noise_draw[t])",
            "capture_hz": CAPTURE_HZ,
            "seconds_per_server_tick": DT_SECONDS,
            "capture_stride_server_ticks": 1,
            "one_action_one_frame_one_server_tick_lockstep": True,
            "context_pairs": 16,
            "effective_preceding_frames": 15,
            "target_rows_per_trajectory": 19,
            "target_tau": list(TARGET_TAUS),
            "target_timestamp_authority": "Exact per-spec server ticks and seconds are frozen in p3_development_manifest.json; no shifting, adding, dropping, or reordering after capture or neural outcomes.",
            "occlusion_phase_offsets_frames": list(PHASE_OFFSETS),
            "phase_design": "Each outer fold contains every phase once; phase changes target-window placement relative to stable hidden onset and is fixed, not searched.",
        },
        "visibility_authority": {
            "pre_candidate_calibration": "Run only the four frozen candidate-specific visibility-calibration specs (two per direction) before that candidate's paired cohort.",
            "calibration_gate": "At least 0.95 precision and 0.95 recall for the frozen magenta detector against geometric visibility, with no identity/timestamp ambiguity; otherwise candidate FAIL_VISIBILITY.",
            "normal_target_rule": "Every target row must be geometrically occluded AND rendered-magenta not detected.",
            "no_wall_target_rule": "Every target row must be geometrically visible AND rendered-magenta detected.",
            "qualified_target_rows_required": 475,
            "ambiguous_target_rows_allowed": 0,
            "zero_evidence_no_wall_target_rows_allowed": 0,
            "detector_alone_may_not_qualify": True,
            "fresh_calibration_required_after_any_camera_or_apparatus_change": True,
        },
        "path_and_state_gate": {
            "epsilon_path": 0.0,
            "paired_exact_equality_required": True,
            "rows_checked_per_scene_per_candidate": 25 * FRAMES,
            "exact_fields": [
                "trajectory_spec_id", "seed", "noise_seed", "direction", "speed_blocks_per_second",
                "motion_noise_q", "noise schedule", "start state", "target tick IDs and order",
                "camera/FOV", "capture cadence", "frame/action/server-tick identity", "world x/y/z",
            ],
            "substitution_or_clamping_mismatch_allowed": False,
            "any_mismatch_result": "FAIL_PATH_STATE; no activation extraction for that candidate",
        },
        "prospective_headroom_gate": {
            "reference_p2_best_k_visible_rmse_blocks": P2_BEST_K_RMSE_BLOCKS,
            "minimum_each_trajectory_target_sd_blocks": MIN_TRAJECTORY_SD_BLOCKS,
            "minimum_each_trajectory_formula": "2 * P2 BEST-K visible RMSE",
            "minimum_candidate_median_target_sd_blocks": MIN_MEDIAN_SD_BLOCKS,
            "minimum_candidate_median_formula": "3 * P2 BEST-K visible RMSE",
            "computed_from_frozen physical target paths_before_capture": True,
        },
        "activation_and_readout": {
            "activation_layers": [4],
            "all_layer_extraction_forbidden": True,
            "extraction_gated_on_capture_path_visibility_pass": True,
            "BEST_K": {
                "role": "LEADING_QUALIFICATION_READOUT",
                "k_grid": [1, 4, 8, 16, 32, 64, 128],
                "alpha_grid": [0.1, 1.0, 10.0, 100.0],
                "selection": "Nested training-only trajectory-grouped selection; exact ties choose smaller K then smaller alpha.",
                "token_ranking": "absolute maximum hidden-dimension training correlation",
                "feature_standardization": "training rows only",
            },
            "FULL_TOKEN_GRID": {
                "role": "QUALIFIED_SECONDARY_REPORT_ONLY",
                "procedure": "exact standardized summed-token kernel ridge",
                "may_rescue_or_advance_candidate": False,
            },
            "outer_evaluation": "Five frozen trajectory-grouped folds; no row/frame splitting.",
            "selection_scope": "tau 1..15 outer-training rows only",
            "evaluation_scope": "all qualified tau 1..19 rows; primary qualification metrics also reported for tau 1..15",
            "representation_search_forbidden": True,
            "k_adaptation_outside_frozen_training_only_procedure_forbidden": True,
        },
        "time_confound_gate": {
            "baseline": "Outer-training least squares with frozen features [1, direction_sign, tau, tau*direction_sign], fit on tau 1..15 only.",
            "maximum_trajectory_equal_macro_r2_tau_1_to_15": TIME_ONLY_MACRO_R2_MAX,
            "interpretation": "At or below 0.10 is the prospectively frozen operational meaning of approximately zero for this development gate.",
            "rmse_blocks_and_whole_trajectory_bootstrap_interval_reported": True,
        },
        "candidate_qualification_rule": {
            "BEST_K_controls_progression": True,
            "all_required": [
                "capture, durability, identity, path/state, and dual visibility gates PASS",
                "prospective headroom gate PASS",
                "layer-4-only extraction validation PASS",
                "NORMAL BEST-K trajectory-equal macro R2 > 0 and whole-trajectory bootstrap 95% lower bound > 0",
                "NO_WALL BEST-K trajectory-equal macro R2 > 0 and whole-trajectory bootstrap 95% lower bound > 0",
                f"NORMAL and NO_WALL BEST-K trajectory-equal RMSE each <= {ABSOLUTE_RMSE_CEILING_BLOCKS:.16f} blocks",
                "NORMAL BEST-K RMSE strictly less than frozen time-only RMSE",
                f"time-only trajectory-equal macro R2 on tau 1..15 <= {TIME_ONLY_MACRO_R2_MAX:.2f}",
            ],
            "absolute_rmse_ceiling_blocks": ABSOLUTE_RMSE_CEILING_BLOCKS,
            "absolute_rmse_ceiling_formula": "2 * completed P2 BEST-K visible RMSE",
            "bootstrap": {"resamples": 10000, "seed": 2026081503, "unit": "WHOLE_TRAJECTORY"},
            "natural_unit_metrics_required": ["RMSE_BLOCKS", "MAE_BLOCKS", "SIGNED_BIAS_BLOCKS"],
            "full_token_grid_reported_against_same_continuous_metrics_but_noncontrolling": True,
            "pooled_row_metrics_cannot_override": True,
        },
        "recovery": {
            "atomic_unit": "one frozen calibration or paired trajectory run",
            "max_attempts_per_unit": 3,
            "retry": "identical candidate/spec/seed/scene only",
            "seed_or_spec_substitution_forbidden": True,
            "favorable_duplication_or_row_dropping_forbidden": True,
        },
        "post_p3_boundary": {
            "p3_pass_does_not_authorize_regime_a_prime_collection": True,
            "required_next_document": "A separate outcome-informed but prospectively frozen confirmatory Regime A-prime authority using wholly new identities/seeds.",
            "p4_p5_p6_not_started": True,
        },
    }


def validate(manifest: dict[str, Any], authority: dict[str, Any]) -> dict[str, Any]:
    candidates = manifest["candidates"]
    specs = [spec for candidate in candidates for spec in candidate["specs"]]
    calibrations = [row for candidate in candidates for row in candidate["visibility_calibration_specs"]]
    ids = [row["trajectory_spec_id"] for row in specs]
    seeds = [row["seed"] for row in specs] + [row["seed"] for row in calibrations]
    run_ids = [scene["run_id"] for row in specs for scene in row["paired_runs"].values()]
    episode_ids = [scene["episode_id"] for row in specs for scene in row["paired_runs"].values()] + [row["episode_id"] for row in calibrations]
    p2_closeout = json.loads((OUT / "p2_closeout_receipt.json").read_text())
    p2_best_k = json.loads((OUT / "p2_best_k_results.json").read_text())
    path_reproductions = []
    for row in specs:
        noise, path = noise_and_path(
            int(row["seed"]), str(row["direction"]),
            float(row["speed_blocks_per_second"]),
        )
        onset = first_stable_hidden_onset(path, str(row["direction"]))
        ticks = [int(value) for value in row["target_server_ticks"]]
        lower, upper = HIDDEN_BOUNDS[str(row["direction"])]
        target = path[ticks]
        inside = ((target >= lower) & (target <= upper)) if row["direction"] == "LEFT_TO_RIGHT" else (
            (target <= lower) & (target >= upper)
        )
        path_reproductions.append(
            hashlib.sha256(noise.tobytes()).hexdigest() == row["noise_schedule_sha256"]
            and hashlib.sha256(path.tobytes()).hexdigest() == row["expected_path_sha256"]
            and onset == row["expected_stable_hidden_onset_server_tick"]
            and ticks == list(range(ticks[0], ticks[0] + 19))
            and ticks[0] == onset + row["occlusion_phase_frames"]
            and row["target_timestamps_seconds"] == [tick * DT_SECONDS for tick in ticks]
            and row["expected_target_world_x_blocks"] == [float(value) for value in target]
            and bool(inside.all())
        )
    checks = {
        "branch_exact": git("branch", "--show-current") == BRANCH,
        "p2_closeout_is_local_ancestor": git("merge-base", "--is-ancestor", P2_COMMIT, "HEAD") == "",
        "p2_closeout_is_remote_ancestor": git("merge-base", "--is-ancestor", P2_COMMIT, f"origin/{BRANCH}") == "",
        "candidate_sequence_exact": [row["motion_parameter"]["speed_blocks_per_second"] for row in candidates] == list(SPEEDS),
        "candidate_counts_exact": len(candidates) == 3 and all(len(row["specs"]) == 25 for row in candidates),
        "candidate_fold_direction_phase_balance_exact": all(
            sorted(spec["outer_fold"] for spec in candidate["specs"]) == sorted(list(range(5)) * 5)
            and sum(spec["direction"] == "LEFT_TO_RIGHT" for spec in candidate["specs"]) == 13
            and sorted(spec["occlusion_phase_frames"] for spec in candidate["specs"]) == sorted(list(PHASE_OFFSETS) * 5)
            and all(
                sorted(spec["occlusion_phase_frames"] for spec in candidate["specs"] if spec["outer_fold"] == fold) == list(PHASE_OFFSETS)
                for fold in range(5)
            )
            for candidate in candidates
        ),
        "all_ids_unique": len(ids) == len(set(ids)) == 75,
        "all_seeds_unique": len(seeds) == len(set(seeds)) == 87,
        "all_run_ids_unique": len(run_ids) == len(set(run_ids)) == 150,
        "all_episode_ids_unique": len(episode_ids) == len(set(episode_ids)) == 162,
        "all_nonconfirmatory": all(row["confirmatory_membership"] is False for row in specs + calibrations),
        "all_unexecuted": all(row["execution_state"] == "FROZEN_NOT_EXECUTED" for row in specs),
        "all_target_rows_exact": all(len(row["target_server_ticks"]) == 19 and row["target_tau"] == list(TARGET_TAUS) for row in specs),
        "all_paths_targets_and_timestamps_reproduce": all(path_reproductions),
        "all_spec_hashes_exact": all(canonical_sha256({k: v for k, v in row.items() if k != "spec_hash"}) == row["spec_hash"] for row in specs),
        "all_headroom_design_checks_pass": all(row["prospective_path_headroom"]["passes_deterministic_design_check"] for row in candidates),
        "authority_nonconfirmatory": authority["confirmatory_membership"] is False,
        "p3_not_started": authority["scope_boundary"]["p3_started"] is False,
        "regime_a_prime_not_authorized": authority["scope_boundary"]["REGIME_A_PRIME_COLLECTION_AUTHORIZED"] == "NO",
        "layer_4_only": authority["activation_and_readout"]["activation_layers"] == [4],
        "best_k_leading_full_secondary": authority["candidate_qualification_rule"]["BEST_K_controls_progression"] is True and authority["activation_and_readout"]["FULL_TOKEN_GRID"]["may_rescue_or_advance_candidate"] is False,
        "single_dimension_search": authority["ordered_search"]["only_variable"] == "speed_blocks_per_second",
        "stop_first_pass": authority["ordered_search"]["stop_rule"].startswith("STOP immediately at the first PASS"),
        "p2_decision_and_boundary_exact": (
            p2_closeout["p2_decision"] == "GO_BEST_K_FULL_VISIBLE"
            and p2_closeout["p3_allowed"] is True
            and p2_closeout["p3_started"] is False
            and p2_closeout["REGIME_A_PRIME_COLLECTION_AUTHORIZED"] == "NO"
        ),
        "p2_rmse_threshold_source_exact": p2_best_k["visible_metrics"]["rmse_blocks"] == P2_BEST_K_RMSE_BLOCKS,
    }
    if not all(checks.values()):
        failed = [name for name, value in checks.items() if not value]
        raise RuntimeError(f"P3 authority validation failed: {failed}")
    return {
        "artifact_id": "regime-a-prime-p3-development-authority-validation-v0.1",
        "schema_version": "1.0",
        "status": "PASS",
        "classification": "DEVELOPMENT_PREFLIGHT",
        "p3_authority_prepared": True,
        "p3_started": False,
        "REGIME_A_PRIME_COLLECTION_AUTHORIZED": "NO",
        "scientific_or_neural_outcomes_observed": False,
        "minecraft_started": False,
        "gpu_used": False,
        "checks": checks,
        "counts": {
            "candidates": 3,
            "development_specs": 75,
            "paired_development_runs_if_all_needed": 150,
            "visibility_calibration_specs": 12,
            "target_rows_if_all_candidates_needed_per_scene": 1425,
        },
        "manifest_sha256": sha256_file(OUT / "p3_development_manifest.json"),
        "authority_sha256": sha256_file(OUT / "p3_preoutcome_authority.json"),
        "next_allowed_action": "Execute P3DEV_C01 development preflight under p3_preoutcome_authority.json; do not execute later candidates unless the frozen progression rule permits it.",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    manifest = build_manifest()
    manifest_payload = json_bytes(manifest)
    authority = build_authority(hashlib.sha256(manifest_payload).hexdigest())
    authority_payload = json_bytes(authority)
    manifest_path = OUT / "p3_development_manifest.json"
    authority_path = OUT / "p3_preoutcome_authority.json"
    validation_path = OUT / "p3_authority_validation_receipt.json"
    if args.check:
        if manifest_path.read_bytes() != manifest_payload:
            raise RuntimeError("frozen P3 development manifest does not reproduce")
        if authority_path.read_bytes() != authority_payload:
            raise RuntimeError("frozen P3 authority does not reproduce")
    else:
        manifest_path.write_bytes(manifest_payload)
        authority_path.write_bytes(authority_payload)
    receipt = validate(manifest, authority)
    receipt_payload = json_bytes(receipt)
    if args.check:
        if validation_path.read_bytes() != receipt_payload:
            raise RuntimeError("frozen P3 validation receipt does not reproduce")
    else:
        validation_path.write_bytes(receipt_payload)
    print("P3_AUTHORITY_VALIDATION_STATUS=PASS")
    print("P3_AUTHORITY_PREPARED=true")
    print("P3_STARTED=false")
    print("REGIME_A_PRIME_COLLECTION_AUTHORIZED=NO")
    print(f"P3_DEVELOPMENT_MANIFEST_SHA256={sha256_file(manifest_path)}")
    print(f"P3_PREOUTCOME_AUTHORITY_SHA256={sha256_file(authority_path)}")
    print(f"P3_VALIDATION_RECEIPT_SHA256={sha256_file(validation_path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
