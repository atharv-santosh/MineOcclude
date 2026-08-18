#!/usr/bin/env python3
"""Build the draft Stage-1 manifest and post-Stage-1 Stage-2 template."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
PACKAGE = ROOT / "docs/status/integration/regime_a_prime_qualification_v0_1/prospective_development_authority_v0_2"
AUTHORITY = PACKAGE / "authority_parameters.json"
DRIVER = ROOT / "scripts/regime_a_prime_qualification_v0_2/stage_unit_driver.py"
PYTHON = "/home/sagemaker-user/.conda/envs/mineworld/bin/python"
RUNTIME_SOURCE_BINDING = "BOUND_AT_LAUNCH_BY_PREOUTCOME_PROVENANCE_RECEIPT"

from mineocclude.prospective.development_workflow import causal_fir_targets  # noqa: E402


def seed(label: str) -> int:
    return int.from_bytes(hashlib.sha256(label.encode()).digest()[:8], "big") & ((1 << 63) - 1)


def unit_seed(label: str) -> int:
    """The ONE seed identity a capture unit carries.

    ``seed`` and ``noise_seed`` are two names for a single value, not two
    independent draws. The apparatus enforces this end to end:

      * Python generates the schedule from ``noise_seed`` and the server is
        handed ``seed`` on the ``startspec`` line;
      * ``NoiseSchedule.load(schedulePath, cfg.seed)`` refuses any schedule whose
        header seed differs from the episode seed, so a scientific episode cannot
        even arm unless the two agree;
      * the server logs that same ``cfg.seed`` into every ``server_state`` row,
        and ``p3_run_sequential.derive_artifacts`` re-checks each row against
        ``spec["seed"]`` -- so sending the noise seed instead would merely move
        the refusal from arming to frame 0.

    Every manifest that ever produced a real capture satisfies it: all 25 Regime
    A v2.1 amendment-1 specs and all P3 development specs carry
    ``seed == noise_seed``. Minting the two from different labels was a
    generator defect, not a two-seed design.

    The noise label is the surviving derivation deliberately. The seed value is
    scientifically inert -- with a schedule loaded the server never draws from it
    (``SheepController.rng`` is the ``java_util_random_nonscientific`` fallback
    only) -- whereas the noise seed determines the physical trajectory. Keeping
    the noise derivation leaves every noise realization, ``noise_schedule_sha256``
    and Stage-2 ``expected_path_sha256`` byte-identical.
    """
    return seed(label + ":noise")


def write(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


def command(stage: str, unit: str, manifest: Path, receipt: Path) -> list[str]:
    return [PYTHON, str(DRIVER), "--stage", stage, "--manifest", str(manifest),
            "--unit-id", unit, "--receipt", str(receipt)]


def path_for(identity: dict, authority: dict) -> list[float]:
    seconds_per_tick = authority["apparatus"]["seconds_per_server_tick"]
    lane_low, lane_high = authority["apparatus"]["lane_world_x_blocks"]
    rng = np.random.default_rng(identity["noise_seed"])
    noise = rng.standard_normal(identity["expected_frames"]) * np.sqrt(
        identity["motion_noise_q"] * seconds_per_tick)
    signed = identity["speed_blocks_per_second"] * seconds_per_tick * (
        1 if identity["direction"] == "LEFT_TO_RIGHT" else -1)
    position = identity["start_world_x"]
    values = []
    for draw in noise:
        position = min(lane_high, max(lane_low, position + signed + float(draw)))
        values.append(position)
    return values


def build_stage1(authority_sha: str, authority: dict) -> dict:
    stage1_path = PACKAGE / "stage1_manifest.json"
    policy = authority["stage1_policy"]
    fixed = authority["fixed_development_configuration"]
    units, episode = [], 81000
    for direction in policy["directions"]:
        for scene in policy["scenes"]:
            for replicate_text, role in policy["replicate_roles"].items():
                replicate = int(replicate_text)
                episode += 1
                short = "ltr" if direction == "LEFT_TO_RIGHT" else "rtl"
                scene_short = "wall" if scene == "WALL" else "nowall"
                unit_id = f"a1q_{short}_{scene_short}_r{replicate:02d}"
                receipt = Path(f"/mnt/sagemaker-nvme/regime_a_prime_a1q_v0_2/receipts/{unit_id}.json")
                identity_seed = unit_seed(unit_id)
                units.append({"unit_id": unit_id, "classification": "NONCONFIRMATORY_DEVELOPMENT_QUALIFICATION",
                    "confirmatory_membership": False, "direction": direction, "scene": scene,
                    "scientific_run_id": "mineocclude-regime-a-prime-development-v0-2-stage1",
                    "replicate": replicate, "design_role": role, "episode_id": episode, "seed": identity_seed,
                    "noise_seed": identity_seed,
                    "speed_blocks_per_second": fixed["speed_blocks_per_second"],
                    "motion_noise_q": fixed["motion_noise_q"],
                    "start_world_x": fixed["start_world_x_by_direction"][direction],
                    "expected_frames": fixed["expected_frames_per_run"], "receipt_path": str(receipt),
                    "command": command("stage1-capture", unit_id, stage1_path, receipt)})
    return {"schema_version": "1.1", "artifact_id": "regime-a-prime-stage1-manifest-v0.2",
        "status": "DRAFT_UNFROZEN_NOT_AUTHORIZED", "classification": "DEVELOPMENT_ONLY",
        "authority_binding": {"path": str(AUTHORITY.relative_to(ROOT)), "sha256": authority_sha},
        "source_commit_binding": RUNTIME_SOURCE_BINDING,
        "run_namespace": "mineocclude-regime-a-prime-development-v0-2-stage1",
        "STAGE_1_COLLECTION_AUTHORIZED": False, "STAGE_2_COLLECTION_AUTHORIZED": False,
        "confirmatory_collection_authorized": False, "run_count": policy["run_count"],
        "run_count_derivation": "2 directions x 2 scenes x measurement/held-out roles",
        "speed_blocks_per_second": fixed["speed_blocks_per_second"], "units": units,
        "terminal_behavior": "evaluate Stage 1, write decision, and stop; never invoke Stage 2",
        "durable_prefix": "s3://sagemaker-us-east-1-323206973672/mineocclude/regime_a_prime_qualification_v0_1/prospective_development_v0_2/stage1"}


def build_stage2_template(authority_sha: str, stage1_sha: str, authority: dict) -> dict:
    stage2_path = PACKAGE / "stage2_locked_manifest.json"
    policy = authority["stage2_policy"]
    fixed = authority["fixed_development_configuration"]
    phases = policy["phase_offsets_frames"]
    ltr_by_fold = {int(fold): set(indices)
                   for fold, indices in policy["left_to_right_phase_indices_by_fold"].items()}
    cells = [(fold, phase_index, phase)
             for fold in range(policy["outer_folds"])
             for phase_index, phase in enumerate(phases)]
    if len(cells) != policy["paired_trajectory_identities"]:
        raise RuntimeError("authority Stage-2 fold/phase allocation does not produce 25 identities")
    identities, captures, extractions = [], [], []
    for index, (fold, phase_index, phase) in enumerate(cells, start=1):
        trajectory_id = f"a2dev_t{index:02d}"
        direction = "LEFT_TO_RIGHT" if phase_index in ltr_by_fold[fold] else "RIGHT_TO_LEFT"
        identity_seed = unit_seed(trajectory_id)
        identity = {"trajectory_id": trajectory_id, "seed": identity_seed,
            "noise_seed": identity_seed, "direction": direction,
            "outer_fold": fold, "phase_frames": phase,
            "speed_blocks_per_second": fixed["speed_blocks_per_second"],
            "motion_noise_q": fixed["motion_noise_q"],
            "start_world_x": fixed["start_world_x_by_direction"][direction],
            "expected_frames": fixed["expected_frames_per_run"], "confirmatory_membership": False,
            "scientific_run_id": "mineocclude-regime-a-prime-development-v0-2-stage2",
            "target_window_status": "TO_BE_MATERIALIZED_FROM_FROZEN_STAGE1_DECISION"}
        path = path_for(identity, authority)
        identity["expected_path_sha256"] = hashlib.sha256(np.asarray(path, dtype="<f8").tobytes()).hexdigest()
        identities.append(identity)
        for scene, offset in (("WALL", 0), ("NO_WALL", 500)):
            unit_id = f"{trajectory_id}_{scene.lower()}"
            receipt = Path(f"/mnt/sagemaker-nvme/regime_a_prime_a2dev_v0_2/receipts/capture/{unit_id}.json")
            captures.append({**identity, "unit_id": unit_id, "scene": scene,
                "episode_id": 82000 + index + offset, "receipt_path": str(receipt),
                "pipeline_stage": "capture_and_durability",
                "command": command("stage2-capture", unit_id, stage2_path, receipt)})
            extract_id = f"extract_{unit_id}"
            extract_receipt = Path(f"/mnt/sagemaker-nvme/regime_a_prime_a2dev_v0_2/receipts/extraction/{extract_id}.json")
            extractions.append({"unit_id": extract_id, "source_capture_unit_id": unit_id,
                "scientific_run_id": "mineocclude-regime-a-prime-development-v0-2-stage2",
                "layer": 4, "receipt_path": str(extract_receipt), "pipeline_stage": "layer4_extraction",
                "command": command("stage2-extract", extract_id, stage2_path, extract_receipt)})
    gate_receipt = Path("/mnt/sagemaker-nvme/regime_a_prime_a2dev_v0_2/receipts/physical_gates.json")
    gate = {"unit_id": "stage2_physical_gates", "pipeline_stage": "physical_gates",
            "scientific_run_id": "mineocclude-regime-a-prime-development-v0-2-stage2",
            "receipt_path": str(gate_receipt),
            "command": command("stage2-gates", "stage2_physical_gates", stage2_path, gate_receipt)}
    tails = []
    for stage in ("best_k", "full", "terminal"):
        receipt = Path(f"/mnt/sagemaker-nvme/regime_a_prime_a2dev_v0_2/receipts/{stage}.json")
        tails.append({"unit_id": f"stage2_{stage}", "pipeline_stage": stage,
            "scientific_run_id": "mineocclude-regime-a-prime-development-v0-2-stage2",
            "receipt_path": str(receipt),
            "command": command(f"stage2-{stage.replace('_', '-')}", f"stage2_{stage}", stage2_path, receipt)})
    return {"schema_version": "1.1", "artifact_id": "regime-a-prime-stage2-locked-manifest-v0.2",
        "status": "DRAFT_TEMPLATE_AWAITING_STAGE1_TARGET_MATERIALIZATION",
        "classification": "DEVELOPMENT_ONLY",
        "authority_binding": {"path": str(AUTHORITY.relative_to(ROOT)), "sha256": authority_sha},
        "stage1_manifest_binding": stage1_sha,
        "source_commit_binding": RUNTIME_SOURCE_BINDING,
        "run_namespace": "mineocclude-regime-a-prime-development-v0-2-stage2",
        "STAGE_2_COLLECTION_AUTHORIZED": False, "confirmatory_collection_authorized": False,
        "post_stage1_authorization": {"required": True,
            "required_artifact_id": "regime-a-prime-stage2-post-stage1-authorization-v0.2"},
        "trajectory_identity_count": policy["paired_trajectory_identities"],
        "scientific_capture_count": policy["scientific_capture_count"],
        "required_target_rows_per_capture": policy["required_target_rows_per_capture"],
        "trajectory_identities": identities,
        "capture_units": captures, "physical_gate_unit": gate, "extraction_units": extractions,
        "readout_and_terminal_units": tails, "units": captures + [gate] + extractions + tails,
        "pipeline_order": ["capture_and_durability", "physical_gates", "layer4_extraction", "best_k", "full", "terminal"],
        "fail_closed_before_extraction": True,
        "locked_stage_commands": {
            "stage2-gates": [PYTHON, str(ROOT / "scripts/regime_a_prime_qualification_v0_2/stage2_backend.py"), "gates", str(stage2_path)],
            "stage2-extract": [PYTHON, str(ROOT / "scripts/regime_a_prime_qualification_v0_2/stage2_backend.py"), "extract", str(stage2_path)],
            "stage2-best-k": [PYTHON, str(ROOT / "scripts/regime_a_prime_qualification_v0_2/stage2_backend.py"), "best-k", str(stage2_path)],
            "stage2-full": [PYTHON, str(ROOT / "scripts/regime_a_prime_qualification_v0_2/stage2_backend.py"), "full", str(stage2_path)],
            "stage2-terminal": [PYTHON, str(ROOT / "scripts/regime_a_prime_qualification_v0_2/stage2_backend.py"), "terminal", str(stage2_path)]},
        "durable_prefix": "s3://sagemaker-us-east-1-323206973672/mineocclude/regime_a_prime_qualification_v0_1/prospective_development_v0_2/stage2"}


def materialize_stage2(template: dict, decision: dict) -> dict:
    """Materialize target windows only from a frozen Stage-1 physical decision."""
    authority = json.loads(AUTHORITY.read_text())
    if decision.get("status") != "PASS":
        raise RuntimeError("Stage-2 target materialization requires Stage-1 PASS")
    transition = decision["gates"]["prospective_transition_measurement"]["detail"]
    alignment = decision["gates"]["render_server_temporal_alignment"]["detail"]
    identities = []
    target_count = authority["stage2_policy"]["required_target_rows_per_capture"]
    for identity in template["trajectory_identities"]:
        item = dict(identity); path = path_for(item, authority); direction = item["direction"]
        hidden_low, hidden_high = transition[direction]["stable_occluded_world_x_interval"]
        fir = next(m for m in alignment[direction]["methods"] if m["method_id"] == "causal_fir_group_delay")
        first_valid = len(fir["kernel"]) - 1
        candidate_ticks = list(range(first_valid, len(path)))
        candidate_labels = causal_fir_targets(path, candidate_ticks, fir["kernel"])
        first = next(tick for tick, label in zip(candidate_ticks, candidate_labels, strict=True)
                     if hidden_low <= label <= hidden_high)
        ticks = list(range(first + item["phase_frames"], first + item["phase_frames"] + target_count))
        if ticks[-1] >= len(path):
            raise RuntimeError(f"target window exceeds path: {item['trajectory_id']}")
        targets = causal_fir_targets(path, ticks, fir["kernel"])
        if not all(hidden_low <= target <= hidden_high for target in targets):
            raise RuntimeError(f"materialized target window leaves measured stable-hidden support: {item['trajectory_id']}")
        item.update(target_window_status="MATERIALIZED_FROM_STAGE1", target_model_frame_indices=ticks,
                    expected_causal_fir_target_world_x_blocks=targets,
                    expected_target_sd_blocks=float(np.std(np.asarray(targets), ddof=0)))
        identities.append(item)
    by_id = {item["trajectory_id"]: item for item in identities}
    template["trajectory_identities"] = identities
    headroom = authority["stage2_policy"]["headroom"]
    standard_deviations = [item["expected_target_sd_blocks"] for item in identities]
    if (min(standard_deviations) < headroom["minimum_each_trajectory_target_sd_blocks"]
            or float(np.median(standard_deviations)) < headroom["minimum_candidate_median_target_sd_blocks"]):
        raise RuntimeError("materialized Stage-2 paths fail frozen corrected headroom gates")
    template["capture_units"] = [{**unit, **by_id[unit["trajectory_id"]]} for unit in template["capture_units"]]
    template["units"] = template["capture_units"] + [template["physical_gate_unit"]] + template["extraction_units"] + template["readout_and_terminal_units"]
    template["status"] = "POST_STAGE1_MATERIALIZED_AWAITING_SEPARATE_FREEZE_AND_AUTHORIZATION"
    template["stage1_evidence_sha256"] = decision["stage1_evidence_sha256"]
    template["stage1_decision_sha256"] = hashlib.sha256(
        (json.dumps(decision, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()).hexdigest()
    return template


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage1-decision", type=Path)
    args = parser.parse_args()
    authority = json.loads(AUTHORITY.read_text())
    authority_sha = hashlib.sha256(AUTHORITY.read_bytes()).hexdigest()
    stage1_path = PACKAGE / "stage1_manifest.json"
    stage1 = build_stage1(authority_sha, authority); write(stage1_path, stage1)
    stage2 = build_stage2_template(authority_sha, hashlib.sha256(stage1_path.read_bytes()).hexdigest(), authority)
    if args.stage1_decision:
        stage2 = materialize_stage2(stage2, json.loads(args.stage1_decision.read_text()))
    write(PACKAGE / "stage2_locked_manifest.json", stage2)


if __name__ == "__main__":
    main()
