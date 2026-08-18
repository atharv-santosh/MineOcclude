#!/usr/bin/env python3
"""Build the Regime A' v0.3 Stage-1 manifest and locked Stage-2 template.

Identity is completely fresh: new unit IDs, new episode IDs, new seeds (minted
from the new IDs), new receipt paths, new run namespace and new durable prefix.
No ``560bc01`` unit, episode, capture path or receipt is reachable from here --
those are complete historical evidence and are never recollected.

The trajectory *physics* (speed, noise process, frame count, start positions) is
inherited unchanged from the authority, because v0.3 changes the truth predicate,
not the apparatus.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

PACKAGE = ROOT / ("docs/status/integration/regime_a_prime_qualification_v0_1/"
                  "prospective_development_authority_v0_3")
AUTHORITY = PACKAGE / "authority_parameters.json"
#: The promoted Stage-2 decision rules (B009). Every package with a Stage-2
#: locked manifest carries one: a manifest that describes a terminal decision it
#: cannot reproduce from frozen rules is the defect B009 names. Bound by digest
#: here rather than folded into ``authority_parameters.json``, whose bytes a
#: completed Stage-1 decision already binds.
STAGE2_DECISION_AUTHORITY = PACKAGE / "stage2_decision_authority.json"
DRIVER = ROOT / "scripts/regime_a_prime_qualification_v0_2/stage_unit_driver.py"
BACKEND = ROOT / "scripts/regime_a_prime_qualification_v0_2/stage2_backend.py"
PYTHON = "/home/sagemaker-user/.conda/envs/mineworld/bin/python"
RUNTIME_SOURCE_BINDING = "BOUND_AT_LAUNCH_BY_PREOUTCOME_PROVENANCE_RECEIPT"

STAGE1_NAMESPACE = "mineocclude-regime-a-prime-development-v0-3-stage1"
STAGE2_NAMESPACE = "mineocclude-regime-a-prime-development-v0-3-stage2"
DURABLE_ROOT = ("s3://sagemaker-us-east-1-323206973672/mineocclude/"
                "regime_a_prime_qualification_v0_1/prospective_development_v0_3")

#: v0.3 episode identity block. 560bc01 used 81001-81008 for Stage 1 and the
#: 82xxx band for Stage 2; v0.3 takes disjoint bands so a stale receipt can never
#: be mistaken for a current one.
STAGE1_EPISODE_BASE = 83000
STAGE2_EPISODE_BASE = 84000

from mineocclude.prospective.development_workflow import causal_fir_targets  # noqa: E402


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


#: Seed minting, the noise process and the path integrator are inherited from the
#: v0.2 generator unchanged, so v0.3 differs only where it means to.
_v02 = _load("_a1q_build_manifests",
             ROOT / "scripts/regime_a_prime_qualification_v0_2/build_manifests.py")
unit_seed = _v02.unit_seed
path_for = _v02.path_for
write = _v02.write


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
                # "a1x" -- Stage-1 eXtent. Deliberately not "a1q": no v0.3 unit ID
                # may collide with, or be mistaken for, a 560bc01 unit.
                unit_id = f"a1x_{short}_{scene_short}_r{replicate:02d}"
                receipt = Path(
                    f"/mnt/sagemaker-nvme/regime_a_prime_a1x_v0_3/receipts/{unit_id}.json")
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
        "schema_version": "1.1", "artifact_id": "regime-a-prime-stage1-manifest-v0.3",
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


def stage2_decision_authority_binding() -> dict:
    """Bind the promoted Stage-2 decision rules by identity, path, and digest.

    Read from the file rather than restated here, so the manifest cannot claim a
    decision contract whose bytes it has not seen. ``resolve_package_binding``
    re-checks all three fields against the file on every entrypoint resolution.
    """
    document = json.loads(STAGE2_DECISION_AUTHORITY.read_text())
    return {"artifact_id": document["artifact_id"],
            "path": str(STAGE2_DECISION_AUTHORITY.relative_to(ROOT)),
            "sha256": hashlib.sha256(STAGE2_DECISION_AUTHORITY.read_bytes()).hexdigest()}


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
        trajectory_id = f"a2x_t{index:02d}"
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
            receipt = Path(f"/mnt/sagemaker-nvme/regime_a_prime_a2x_v0_3/receipts/capture/{unit_id}.json")
            captures.append({**identity, "unit_id": unit_id, "scene": scene,
                "episode_id": STAGE2_EPISODE_BASE + index + offset, "receipt_path": str(receipt),
                "pipeline_stage": "capture_and_durability",
                "command": command("stage2-capture", unit_id, stage2_path, receipt)})
            extract_id = f"extract_{unit_id}"
            extract_receipt = Path(
                f"/mnt/sagemaker-nvme/regime_a_prime_a2x_v0_3/receipts/extraction/{extract_id}.json")
            extractions.append({"unit_id": extract_id, "source_capture_unit_id": unit_id,
                "scientific_run_id": STAGE2_NAMESPACE,
                "layer": 4, "receipt_path": str(extract_receipt), "pipeline_stage": "layer4_extraction",
                "command": command("stage2-extract", extract_id, stage2_path, extract_receipt)})
    gate_receipt = Path("/mnt/sagemaker-nvme/regime_a_prime_a2x_v0_3/receipts/physical_gates.json")
    gate = {"unit_id": "stage2_physical_gates", "pipeline_stage": "physical_gates",
            "scientific_run_id": STAGE2_NAMESPACE,
            "receipt_path": str(gate_receipt),
            "command": command("stage2-gates", "stage2_physical_gates", stage2_path, gate_receipt)}
    tails = []
    for stage in ("best_k", "full", "terminal"):
        receipt = Path(f"/mnt/sagemaker-nvme/regime_a_prime_a2x_v0_3/receipts/{stage}.json")
        tails.append({"unit_id": f"stage2_{stage}", "pipeline_stage": stage,
            "scientific_run_id": STAGE2_NAMESPACE,
            "receipt_path": str(receipt),
            "command": command(f"stage2-{stage.replace('_', '-')}", f"stage2_{stage}", stage2_path, receipt)})
    return {"schema_version": "1.1", "artifact_id": "regime-a-prime-stage2-locked-manifest-v0.3",
        "status": "DRAFT_TEMPLATE_AWAITING_STAGE1_TARGET_MATERIALIZATION",
        "classification": "DEVELOPMENT_ONLY",
        "authority_binding": {"path": str(AUTHORITY.relative_to(ROOT)), "sha256": authority_sha},
        "stage2_decision_authority_binding": stage2_decision_authority_binding(),
        "stage1_manifest_binding": stage1_sha,
        "source_commit_binding": RUNTIME_SOURCE_BINDING,
        "run_namespace": STAGE2_NAMESPACE,
        "STAGE_2_COLLECTION_AUTHORIZED": False, "confirmatory_collection_authorized": False,
        "post_stage1_authorization": {"required": True,
            "required_artifact_id": "regime-a-prime-stage2-post-stage1-authorization-v0.3"},
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


def _transition_intervals(decision: dict) -> dict[str, tuple[float, float]]:
    """The measured stable-hidden world-x interval per direction, row-derived.

    The Stage-1 transition gate's detail used to be ``{direction: measurement}``.
    Since the 046b34a builder synchronization it is
    ``{"reported": {...}, "derived_from_rows": {...}}``: the summary the units
    reported, and the same quantities recomputed here from the admitted rows.
    The gate only passes when the two agree on every derived key, so a PASS
    decision carries one interval under two names -- but the flat read this
    function replaces would now raise ``KeyError`` on any current decision, and
    Stage-2 materialization has never run against one.

    The row-derived measurement is what is returned, because it is the one this
    repository recomputed rather than accepted. The reported summary is still
    required to match it: the equality is already a PASS precondition, and
    re-checking it here means a hand-edited decision cannot move the target
    window by rewriting only one of the two copies.
    """
    detail = decision["gates"]["prospective_transition_measurement"]["detail"]
    derived = detail.get("derived_from_rows")
    reported = detail.get("reported")
    if not isinstance(derived, dict) or not isinstance(reported, dict):
        raise RuntimeError(
            "Stage-1 transition detail carries no reported/derived measurement pair")
    intervals = {}
    key = "extent_fully_occluded_world_x_interval"
    for direction, measurement in derived.items():
        interval = measurement.get(key)
        if (not isinstance(interval, list) or len(interval) != 2
                or (reported.get(direction) or {}).get(key) != interval):
            raise RuntimeError(
                f"Stage-1 {key} is absent or disagrees with the reported "
                f"summary for {direction}")
        intervals[direction] = (float(interval[0]), float(interval[1]))
    return intervals


def materialize_stage2(template: dict, decision: dict, *, authority: dict) -> dict:
    """Materialize target windows only from a frozen Stage-1 physical decision.

    From v0.3 onward the stable-occluded interval comes from the *geometric*
    extent transition gate, not from a detector edge, so the Stage-2 target
    windows inherit the same detector-independent truth the Stage-1 gate used.
    That predicate is shared by every successor package, so this function is the
    shared implementation and v0.4 calls it rather than forking it.

    ``authority`` is supplied by the caller and has no default. This module used
    to read the v0.3 ``AUTHORITY`` constant here, which made the *implementation*
    and the *experiment* one object again: v0.4 delegating to this function
    silently materialized its own Stage-2 template against the predecessor's
    authority. Every field consumed below -- the apparatus tick and lane bounds
    ``path_for`` reads, ``required_target_rows_per_capture``, and the frozen
    headroom bounds -- happened to be byte-identical between v0.3 and v0.4, so
    no historical artifact was corrupted; a later v0.4-only ``stage2_policy``
    change would have been. Making the parameter required, rather than
    defaulting it, is what removes the silent fallback: there is no call that
    materializes against an authority the caller did not name.
    """
    if decision.get("status") != "PASS":
        raise RuntimeError("Stage-2 target materialization requires Stage-1 PASS")
    transition = _transition_intervals(decision)
    alignment = decision["gates"]["render_server_temporal_alignment"]["detail"]
    identities = []
    target_count = authority["stage2_policy"]["required_target_rows_per_capture"]
    for identity in template["trajectory_identities"]:
        item = dict(identity); path = path_for(item, authority); direction = item["direction"]
        hidden_low, hidden_high = transition[direction]
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
            raise RuntimeError(
                f"materialized target window leaves measured stable-hidden support: {item['trajectory_id']}")
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
    template["units"] = (template["capture_units"] + [template["physical_gate_unit"]]
                         + template["extraction_units"] + template["readout_and_terminal_units"])
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
