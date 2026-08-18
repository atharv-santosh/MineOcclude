#!/usr/bin/env python3
"""Build the Regime A' v0.4 Stage-1 manifest and locked Stage-2 template.

Identity is completely fresh: new unit IDs (``a1y_*``), new episode block
(85001-85008 for Stage 1, 86xxx for Stage 2), new seeds minted from the new IDs,
new receipt paths, new run namespace and new durable prefix. No ``134a242``
unit, episode, capture path or receipt is reachable from here -- those are
complete historical evidence and are never recollected. Nor is any ``560bc01``
one: the 81xxx/82xxx, 83xxx/84xxx and 85xxx/86xxx episode bands are pairwise
disjoint, so a stale receipt can never be mistaken for a current one.

The trajectory *physics* -- speed, noise process, frame count, start positions,
factorial design -- is inherited unchanged from the authority, because v0.4
changes the unit inventory, not the experiment. Seeds are minted deterministically
as ``unit_seed(unit_id)``, so the new identities fully determine the new noise
realizations and nothing here is a free numeric choice.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

PACKAGE = ROOT / ("docs/status/integration/regime_a_prime_qualification_v0_1/"
                  "prospective_development_authority_v0_4")
AUTHORITY = PACKAGE / "authority_parameters.json"
# The unit driver and the Stage-2 backend are shared implementations, not
# versioned experiments. v0.4 parameterises them with its own manifest exactly as
# v0.3 did; it does not fork them. A v0_4 wrapper shim would additionally break
# the authority's independent-probe-producer allow-list.
DRIVER = ROOT / "scripts/regime_a_prime_qualification_v0_2/stage_unit_driver.py"
BACKEND = ROOT / "scripts/regime_a_prime_qualification_v0_2/stage2_backend.py"
PYTHON = "/home/sagemaker-user/.conda/envs/mineworld/bin/python"
RUNTIME_SOURCE_BINDING = "BOUND_AT_LAUNCH_BY_PREOUTCOME_PROVENANCE_RECEIPT"

STAGE1_NAMESPACE = "mineocclude-regime-a-prime-development-v0-4-stage1"
STAGE2_NAMESPACE = "mineocclude-regime-a-prime-development-v0-4-stage2"
DURABLE_ROOT = ("s3://sagemaker-us-east-1-323206973672/mineocclude/"
                "regime_a_prime_qualification_v0_1/prospective_development_v0_4")

#: v0.4 episode identity block, disjoint from 81xxx/82xxx (v0.2) and 83xxx/84xxx
#: (v0.3). Both predecessor inventories terminated in scientific FAIL and are
#: closed; disjoint bands make a cross-generation receipt collision impossible.
STAGE1_EPISODE_BASE = 85000
STAGE2_EPISODE_BASE = 86000

#: "a1y" -- the v0.4 Stage-1 inventory. Deliberately neither "a1q" (v0.2) nor
#: "a1x" (v0.3): no v0.4 unit ID may collide with, or be mistaken for, a unit
#: from either closed inventory.
UNIT_PREFIX = "a1y"

from scripts.regime_a_prime_qualification_v0_2.build_manifests import (  # noqa: E402
    path_for, unit_seed, write,
)


def command(stage: str, unit: str, manifest: Path, receipt: Path) -> list[str]:
    return [PYTHON, str(DRIVER), "--stage", stage, "--manifest", str(manifest),
            "--unit-id", unit, "--receipt", str(receipt)]


def build_stage1(authority_sha: str, authority: dict) -> dict:
    stage1_path = PACKAGE / "stage1_manifest.json"
    policy = authority["stage1_policy"]
    fixed = authority["fixed_development_configuration"]
    units, episode = [], STAGE1_EPISODE_BASE
    for direction in policy["directions"]:
        for scene in policy["scenes"]:
            for replicate_text, role in policy["replicate_roles"].items():
                replicate = int(replicate_text)
                episode += 1
                short = "ltr" if direction == "LEFT_TO_RIGHT" else "rtl"
                scene_short = "wall" if scene == "WALL" else "nowall"
                unit_id = f"{UNIT_PREFIX}_{short}_{scene_short}_r{replicate:02d}"
                receipt = Path(
                    f"/mnt/sagemaker-nvme/regime_a_prime_{UNIT_PREFIX}_v0_4/receipts/{unit_id}.json")
                identity_seed = unit_seed(unit_id)
                units.append({
                    "unit_id": unit_id,
                    "classification": "NONCONFIRMATORY_DEVELOPMENT_QUALIFICATION",
                    "confirmatory_membership": False, "direction": direction, "scene": scene,
                    "scientific_run_id": STAGE1_NAMESPACE,
                    "replicate": replicate, "design_role": role, "episode_id": episode,
                    # One seed identity per unit: seed and noise_seed are two names
                    # for a single value, and the server refuses to arm otherwise.
                    "seed": identity_seed, "noise_seed": identity_seed,
                    "speed_blocks_per_second": fixed["speed_blocks_per_second"],
                    "motion_noise_q": fixed["motion_noise_q"],
                    "start_world_x": fixed["start_world_x_by_direction"][direction],
                    "expected_frames": fixed["expected_frames_per_run"],
                    "receipt_path": str(receipt),
                    "command": command("stage1-capture", unit_id, stage1_path, receipt)})
    return {
        "schema_version": "1.1", "artifact_id": "regime-a-prime-stage1-manifest-v0.4",
        "status": "DRAFT_UNFROZEN_NOT_AUTHORIZED", "classification": "DEVELOPMENT_ONLY",
        "authority_binding": {"path": str(AUTHORITY.relative_to(ROOT)), "sha256": authority_sha},
        "source_commit_binding": RUNTIME_SOURCE_BINDING,
        "run_namespace": STAGE1_NAMESPACE,
        "STAGE_1_COLLECTION_AUTHORIZED": False, "STAGE_2_COLLECTION_AUTHORIZED": False,
        "confirmatory_collection_authorized": False, "run_count": policy["run_count"],
        "run_count_derivation": "2 directions x 2 scenes x measurement/held-out roles",
        "speed_blocks_per_second": fixed["speed_blocks_per_second"], "units": units,
        "predecessor_units_reused": False,
        "predecessor_freeze_sha": authority["predecessor_authority"]["freeze_sha"],
        "terminal_behavior": "evaluate Stage 1, write decision, and stop; never invoke Stage 2",
        "durable_prefix": f"{DURABLE_ROOT}/stage1"}


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
        trajectory_id = f"a2y_t{index:02d}"
        direction = "LEFT_TO_RIGHT" if phase_index in ltr_by_fold[fold] else "RIGHT_TO_LEFT"
        identity_seed = unit_seed(trajectory_id)
        identity = {"trajectory_id": trajectory_id, "seed": identity_seed,
            "noise_seed": identity_seed, "direction": direction,
            "outer_fold": fold, "phase_frames": phase,
            "speed_blocks_per_second": fixed["speed_blocks_per_second"],
            "motion_noise_q": fixed["motion_noise_q"],
            "start_world_x": fixed["start_world_x_by_direction"][direction],
            "expected_frames": fixed["expected_frames_per_run"], "confirmatory_membership": False,
            "scientific_run_id": STAGE2_NAMESPACE,
            "target_window_status": "TO_BE_MATERIALIZED_FROM_FROZEN_STAGE1_DECISION"}
        path = path_for(identity, authority)
        identity["expected_path_sha256"] = hashlib.sha256(
            np.asarray(path, dtype="<f8").tobytes()).hexdigest()
        identities.append(identity)
        for scene, offset in (("WALL", 0), ("NO_WALL", 500)):
            unit_id = f"{trajectory_id}_{scene.lower()}"
            receipt = Path(f"/mnt/sagemaker-nvme/regime_a_prime_a2y_v0_4/receipts/capture/{unit_id}.json")
            captures.append({**identity, "unit_id": unit_id, "scene": scene,
                "episode_id": STAGE2_EPISODE_BASE + index + offset, "receipt_path": str(receipt),
                "pipeline_stage": "capture_and_durability",
                "command": command("stage2-capture", unit_id, stage2_path, receipt)})
            extract_id = f"extract_{unit_id}"
            extract_receipt = Path(
                f"/mnt/sagemaker-nvme/regime_a_prime_a2y_v0_4/receipts/extraction/{extract_id}.json")
            extractions.append({"unit_id": extract_id, "source_capture_unit_id": unit_id,
                "layer": 4, "receipt_path": str(extract_receipt), "pipeline_stage": "layer4_extraction",
                "command": command("stage2-extract", extract_id, stage2_path, extract_receipt)})
    gate_receipt = Path("/mnt/sagemaker-nvme/regime_a_prime_a2y_v0_4/receipts/physical_gates.json")
    gate = {"unit_id": "stage2_physical_gates", "pipeline_stage": "physical_gates",
            "receipt_path": str(gate_receipt),
            "command": command("stage2-gates", "stage2_physical_gates", stage2_path, gate_receipt)}
    tails = []
    for stage in ("best_k", "full", "terminal"):
        receipt = Path(f"/mnt/sagemaker-nvme/regime_a_prime_a2y_v0_4/receipts/{stage}.json")
        tails.append({"unit_id": f"stage2_{stage}", "pipeline_stage": stage,
            "receipt_path": str(receipt),
            "command": command(f"stage2-{stage.replace('_', '-')}", f"stage2_{stage}", stage2_path, receipt)})
    return {"schema_version": "1.1", "artifact_id": "regime-a-prime-stage2-locked-manifest-v0.4",
        "status": "DRAFT_TEMPLATE_AWAITING_STAGE1_TARGET_MATERIALIZATION",
        "classification": "DEVELOPMENT_ONLY",
        "authority_binding": {"path": str(AUTHORITY.relative_to(ROOT)), "sha256": authority_sha},
        "stage1_manifest_binding": stage1_sha,
        "source_commit_binding": RUNTIME_SOURCE_BINDING,
        "run_namespace": STAGE2_NAMESPACE,
        "STAGE_2_COLLECTION_AUTHORIZED": False, "confirmatory_collection_authorized": False,
        "post_stage1_authorization": {"required": True,
            "required_artifact_id": "regime-a-prime-stage2-post-stage1-authorization-v0.4"},
        "trajectory_identity_count": policy["paired_trajectory_identities"],
        "scientific_capture_count": policy["scientific_capture_count"],
        "required_target_rows_per_capture": policy["required_target_rows_per_capture"],
        "trajectory_identities": identities,
        "capture_units": captures, "physical_gate_unit": gate, "extraction_units": extractions,
        "readout_and_terminal_units": tails, "units": captures + [gate] + extractions + tails,
        "pipeline_order": ["capture_and_durability", "physical_gates", "layer4_extraction",
                           "best_k", "full", "terminal"],
        "fail_closed_before_extraction": True,
        "locked_stage_commands": {
            "stage2-gates": [PYTHON, str(BACKEND), "gates", str(stage2_path)],
            "stage2-extract": [PYTHON, str(BACKEND), "extract", str(stage2_path)],
            "stage2-best-k": [PYTHON, str(BACKEND), "best-k", str(stage2_path)],
            "stage2-full": [PYTHON, str(BACKEND), "full", str(stage2_path)],
            "stage2-terminal": [PYTHON, str(BACKEND), "terminal", str(stage2_path)]},
        "durable_prefix": f"{DURABLE_ROOT}/stage2"}


def materialize_stage2(template: dict, decision: dict, *, authority: dict) -> dict:
    """Materialize target windows only from a frozen Stage-1 physical decision.

    The predicate is shared with v0.3 unchanged -- the stable-occluded interval
    comes from the *geometric* extent transition gate, not from a detector edge,
    so the Stage-2 target windows inherit the same detector-independent truth the
    Stage-1 gate used -- and the implementation is therefore shared rather than
    forked.

    What is *not* shared is which authority the shared implementation reads. It
    used to read v0.3's, because that constant was baked into the function; the
    v0.4 authority is passed explicitly here instead. The two authorities'
    materialization inputs are currently byte-identical, so this changes no
    materialized byte today -- it removes the path by which a future v0.4-only
    ``stage2_policy`` edit would have been silently ignored in favour of the
    predecessor's frozen numbers.
    """
    from scripts.regime_a_prime_qualification_v0_3.build_manifests import (
        materialize_stage2 as _materialize)
    return _materialize(template, decision, authority=authority)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage1-decision", type=Path)
    args = parser.parse_args()
    authority = json.loads(AUTHORITY.read_text())
    authority_sha = hashlib.sha256(AUTHORITY.read_bytes()).hexdigest()
    stage1_path = PACKAGE / "stage1_manifest.json"
    stage1 = build_stage1(authority_sha, authority); write(stage1_path, stage1)
    stage2 = build_stage2_template(
        authority_sha, hashlib.sha256(stage1_path.read_bytes()).hexdigest(), authority)
    if args.stage1_decision:
        stage2 = materialize_stage2(stage2, json.loads(args.stage1_decision.read_text()),
                                    authority=authority)
    stage2_path = PACKAGE / "stage2_locked_manifest.json"
    write(stage2_path, stage2)
    for path in (AUTHORITY, stage1_path, stage2_path):
        print(f"{path.name} sha256 = {hashlib.sha256(path.read_bytes()).hexdigest()}")


if __name__ == "__main__":
    main()
