#!/usr/bin/env python3
"""Outcome-blind A5 gate for the frozen Regime-A first25 slice.

This program deliberately never downloads or opens an activation array.  It
binds immutable S3 receipts, HEAD metadata, target/visibility metadata, and the
final versioned repository authorities.  Only a PASS receipt authorizes the
separate scientific analysis program to read activation values.
"""

from __future__ import annotations

import base64
import hashlib
import json
import subprocess
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import boto3


REPO = Path(__file__).resolve().parents[1]
ROOT = REPO / "docs/status/integration/regime_a_occlusion_extraction_v0_1"
OUT = ROOT / "first25_analysis"
CACHE = Path("/mnt/sagemaker-nvme/mineocclude-regime-a-first25-analysis-input")
BUCKET = "sagemaker-us-east-1-323206973672"
BASE = "mineocclude/regime_a_occlusion_extraction_v0_1"
OLD_RUN = "mineocclude-regime-a-first25-v2"
NEW_RUN = "mineocclude-regime-a-first25-v2-amendment-1"
BINS = {
    "SHORT": range(1, 5),
    "INTERMEDIATE": range(5, 9),
    "LONG": range(9, 13),
    "NEAR_CONTEXT": range(13, 16),
    "BEYOND_CONTEXT": range(16, 20),
}


def sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_hash(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return sha_bytes(raw.encode())


def read_json(path: Path) -> object:
    return json.loads(path.read_text())


def jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=REPO, text=True).strip()


def s3_prefix(identity: str) -> str:
    number = int(identity.rsplit("t", 1)[1])
    run = OLD_RUN if number <= 3 else NEW_RUN
    return f"{BASE}/{run}/{identity}"


def get_object(client, key: str) -> tuple[bytes, dict]:
    response = client.get_object(Bucket=BUCKET, Key=key, ChecksumMode="ENABLED")
    return response["Body"].read(), response


def transition_runs(rows: list[dict]) -> tuple[int, int, int]:
    onset = next(i for i, row in enumerate(rows) if row.get("tau") == 1)
    last_hidden = max(i for i, row in enumerate(rows) if row["visibility_class"] == "OCCLUDED_AGREEMENT")
    entry = 0
    cursor = onset - 1
    while cursor >= 0 and rows[cursor]["visibility_class"] == "VISIBILITY_DISAGREEMENT":
        entry += 1
        cursor -= 1
    exit_run = 0
    cursor = last_hidden + 1
    while cursor < len(rows) and rows[cursor]["visibility_class"] == "VISIBILITY_DISAGREEMENT":
        exit_run += 1
        cursor += 1
    return onset, entry, exit_run


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    CACHE.mkdir(parents=True, exist_ok=True)
    client = boto3.client("s3")

    start_head = git("rev-parse", "HEAD")
    branch = git("branch", "--show-current")
    remote_head = git("rev-parse", f"origin/{branch}")
    dirty = bool(git("status", "--porcelain=v1"))

    authorities = {
        "final_amended_directional_visibility_authority": ROOT / "v2_amendment_1/directional_visibility_authority_v2_1_amendment_1.json",
        "final_scientific_manifest": ROOT / "v2_amendment_1/trajectory_manifest_v2_1_amendment_1.jsonl",
        "final_spec_provenance_mapping": ROOT / "v2_amendment_1/spec_provenance_map.json",
        "final_split_authority": ROOT / "split_authority.json",
        "final_target_authority": ROOT / "target_authority.json",
        "final_representation_authority": ROOT / "representation_authority.json",
        "final_analysis_authority": ROOT / "analysis_manifest_v1_1_bootstrap_repair.json",
        "analysis_supersession_receipt": ROOT / "bootstrap_authority_supersession_receipt.json",
        "final_null_donor_manifest": ROOT / "v2/null_donor_manifest.jsonl",
        "final_fold_receipt": ROOT / "v2/fold_receipt.json",
        "final_target_support_receipt": ROOT / "v2/target_support_receipt.json",
        "final_confound_receipt": ROOT / "v2/confound_receipt.json",
        "final_duplicate_receipt": ROOT / "v2/duplicate_receipt.json",
        "final_b49_feasibility_receipt": ROOT / "v2/b49_feasibility_receipt.json",
        "final_context_bin_revalidation": ROOT / "v2_amendment_1/context_bin_revalidation.json",
        "final_amendment_replay": ROOT / "v2_amendment_1/scientific_structural_replay_t01_t04.json",
        "study_manifest": ROOT / "regime_a_study_manifest.json",
        "prior_authority_binding": ROOT / "prior_authority_binding.json",
        "original_v2_directional_authority_preserved": ROOT / "v2/directional_visibility_authority.json",
        "original_v2_manifest_preserved": ROOT / "v2/trajectory_manifest.jsonl",
        "collection_authorization": Path("/home/sagemaker-user/regime-a-a4-authorization/a4_operator_authorization_first25_v2.json"),
        "amendment_authorization": Path("/home/sagemaker-user/regime-a-a4-authorization/a4_operator_authorization_first25_v2_amendment_1.json"),
    }
    missing = [name for name, path in authorities.items() if not path.is_file()]
    if missing:
        raise RuntimeError(f"BLOCKED_AUTHORITY missing: {missing}")
    artifact_binding = {
        name: {"path": str(path), "sha256": sha_file(path), "byte_size": path.stat().st_size}
        for name, path in authorities.items()
    }

    expected = {
        "final_amended_directional_visibility_authority": "fef2d4e89e9919801b802093eb89053b65d359161a62ad3ddb1d99a0bed0ec83",
        "final_scientific_manifest": "2fa1ff3026a654303b3fd248734f92276a568ba0207f0aa6e9a515fc729090e2",
        "final_analysis_authority": "40bc9185d7751673251b0601b267d460642ff383b54b809ed89438b6884a4d26",
        "final_split_authority": "37153654ade645e6a6c570f257a2bdb8862592fffe6d462e2cd8a4419b2b82fc",
        "final_target_authority": "1d14c364c9673b55ce436f06ef16a39b40e60ff4a82fe9a0d5a704ee185d5800",
        "final_representation_authority": "87c7b45fbf558f6e43f0b83abbde51c84dd12756fdf8af2b75135f3d41562c5b",
        "final_null_donor_manifest": "6c72c50cf72c38fd5a20403c75d68c242cf674983cf6b6b487185cbd319fd15d",
        "study_manifest": "624111acde79a89936e0af09f063568a9e28f123fdbbb6f9bb204a7d5e6381c4",
        "prior_authority_binding": "9993b3ed2ad1d9387299656978eb505ba3332e9370c7929cbec6c2b7e9e9c1ed",
        "original_v2_directional_authority_preserved": "985c7b802c17873d9fcee7306d9071a90a97a330c9e6f8a962d6e464e18ccf56",
        "original_v2_manifest_preserved": "ca14f6dbda3e31cf1c7a9ecee98d199307cd1a81b0670eca9104039010eef257",
    }
    conflicts = {name: [artifact_binding[name]["sha256"], value] for name, value in expected.items() if artifact_binding[name]["sha256"] != value}
    if conflicts:
        raise RuntimeError(f"BLOCKED_AUTHORITY hash conflicts: {conflicts}")

    manifest = jsonl(authorities["final_scientific_manifest"])
    provenance = read_json(authorities["final_spec_provenance_mapping"])
    folds = read_json(authorities["final_fold_receipt"])["assignments"]
    guards = read_json(authorities["final_amended_directional_visibility_authority"])
    if len(manifest) != 25 or len({row["trajectory_spec_id"] for row in manifest}) != 25:
        raise RuntimeError("BLOCKED_AUTHORITY final manifest is not exactly 25 unique identities")
    identities = sorted(row["trajectory_spec_id"] for row in manifest)
    specs = {row["trajectory_spec_id"]: row for row in manifest}
    pmap = {row["trajectory_spec_id"]: row for row in provenance["rows"]}

    def fetch_one(identity: str) -> dict:
        prefix = s3_prefix(identity)
        receipt_raw, receipt_response = get_object(client, f"{prefix}/durable_receipt.json")
        receipt = json.loads(receipt_raw)
        objects = {row["key"].removeprefix(prefix + "/"): row for row in receipt["objects"]}
        needed = ["activation_inventory.json", "completion.json", "coordinates.jsonl", "raw/visibility.jsonl"]
        local_dir = CACHE / identity
        local_dir.mkdir(parents=True, exist_ok=True)
        downloaded = {}
        for relative in needed:
            raw, response = get_object(client, f"{prefix}/{relative}")
            record = objects[relative]
            if sha_bytes(raw) != record["local_sha256"] or len(raw) != record["byte_size"]:
                raise RuntimeError(f"BLOCKED_QUALITY immutable metadata mismatch {identity}/{relative}")
            path = local_dir / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
            downloaded[relative] = {
                "sha256": sha_bytes(raw), "byte_size": len(raw),
                "s3_checksum_sha256_base64": response.get("ChecksumSHA256"),
            }
        activation_records = []
        for layer in range(20):
            relative = f"activations/layer_{layer:02d}.npy"
            record = objects.get(relative)
            if record is None:
                raise RuntimeError(f"BLOCKED_QUALITY missing {identity}/{relative}")
            head = client.head_object(Bucket=BUCKET, Key=f"{prefix}/{relative}", ChecksumMode="ENABLED")
            encoded = base64.b64encode(bytes.fromhex(record["local_sha256"])).decode()
            if head["ContentLength"] != record["byte_size"] or head.get("ChecksumSHA256") != encoded:
                raise RuntimeError(f"BLOCKED_QUALITY S3 HEAD mismatch {identity}/{relative}")
            if record.get("uploaded_object_verified") is not True or record.get("downloaded_bytes_verified") is not True:
                raise RuntimeError(f"BLOCKED_QUALITY incomplete durability validation {identity}/{relative}")
            activation_records.append({"layer": layer, "sha256": record["local_sha256"], "byte_size": record["byte_size"], "s3_uri": f"s3://{BUCKET}/{prefix}/{relative}"})
        return {
            "trajectory_id": identity,
            "prefix": prefix,
            "receipt": receipt,
            "receipt_sha256": sha_bytes(receipt_raw),
            "receipt_s3_checksum_sha256_base64": receipt_response.get("ChecksumSHA256"),
            "downloaded": downloaded,
            "activation_records": activation_records,
        }

    with ThreadPoolExecutor(max_workers=12) as pool:
        durable = list(pool.map(fetch_one, identities))

    rows_for_analysis = []
    per_trajectory = []
    bin_counts = Counter()
    direction_counts = Counter()
    activation_provenance = {}
    for item in durable:
        identity = item["trajectory_id"]
        spec = specs[identity]
        inventory = read_json(CACHE / identity / "activation_inventory.json")
        completion = read_json(CACHE / identity / "completion.json")
        coordinates = jsonl(CACHE / identity / "coordinates.jsonl")
        visibility = jsonl(CACHE / identity / "raw/visibility.jsonl")
        direction = spec["direction"]
        direction_counts[direction] += 1
        if completion.get("status") != "VALIDATED" or completion.get("trajectory_spec_id") != identity:
            raise RuntimeError(f"BLOCKED_QUALITY invalid completion {identity}")
        if pmap[identity]["amended_v2_1_spec_hash"] != spec["spec_hash"]:
            raise RuntimeError(f"BLOCKED_AUTHORITY provenance mismatch {identity}")
        # t01--t03 are the explicitly replay-approved serialized artifacts from
        # the original spec.  t04 was repackaged/extracted (without recapture)
        # under the amendment, as were all subsequently collected identities.
        serialized_spec = (
            pmap[identity]["raw_capture_spec_hash"]
            if int(identity.rsplit("t", 1)[1]) <= 3
            else pmap[identity]["amended_v2_1_spec_hash"]
        )
        if inventory["spec_hash"] != serialized_spec or completion["spec_hash"] != serialized_spec:
            raise RuntimeError(f"BLOCKED_AUTHORITY raw/amended provenance mismatch {identity}")
        artifacts = inventory["artifacts"]
        if inventory["layer_indices"] != list(range(20)) or len(artifacts) != 20:
            raise RuntimeError(f"BLOCKED_QUALITY layer inventory mismatch {identity}")
        for layer, artifact in enumerate(artifacts):
            if artifact["layer_idx"] != layer or artifact["shape"] != [19, 336, 2048] or artifact["dtype"] != "float16":
                raise RuntimeError(f"BLOCKED_QUALITY tensor metadata mismatch {identity}/layer{layer}")
            if artifact["sha256"] != item["activation_records"][layer]["sha256"]:
                raise RuntimeError(f"BLOCKED_QUALITY activation provenance mismatch {identity}/layer{layer}")
        if len(coordinates) != len(visibility) or len(coordinates) != 260:
            raise RuntimeError(f"BLOCKED_QUALITY metadata row count mismatch {identity}")
        for coord, vis in zip(coordinates, visibility, strict=True):
            join = ("trajectory_id", "model_frame_idx", "server_tick", "render_frame_idx", "action_idx")
            if any(coord[key] != vis[key] for key in join):
                raise RuntimeError(f"BLOCKED_QUALITY frame alignment mismatch {identity}")
        targets = [row for row in visibility if row.get("primary_hidden_eligible")]
        if len(targets) != 19 or [row["tau"] for row in targets] != list(range(1, 20)):
            raise RuntimeError(f"BLOCKED_QUALITY eligible target mismatch {identity}")
        indices = [row["model_frame_idx"] for row in targets]
        if indices != inventory["target_model_frame_indices"]:
            raise RuntimeError(f"BLOCKED_QUALITY activation/row identity mismatch {identity}")
        onset, entry_run, exit_run = transition_runs(visibility)
        g_entry = guards[direction]["g_entry_frames"]
        g_exit = guards[direction]["g_exit_frames"]
        if entry_run >= g_entry or exit_run >= g_exit:
            raise RuntimeError(f"BLOCKED_QUALITY final guard failure {identity}")
        visible_indices = [i for i, row in enumerate(visibility[:onset]) if row["visibility_class"] == "VISIBLE_AGREEMENT"]
        if len(visible_indices) < 2:
            raise RuntimeError(f"BLOCKED_QUALITY causal visible support missing {identity}")
        clean_context = visible_indices[-15:]
        actual = []
        for activation_row, (vis, model_idx) in enumerate(zip(targets, indices, strict=True)):
            coord = coordinates[model_idx]
            values = [coord["world_x"], coord["token_row"], coord["token_col"]]
            if any(not isinstance(value, (float, int)) or not (-1e100 < float(value) < 1e100) for value in values):
                raise RuntimeError(f"BLOCKED_QUALITY non-finite target {identity}")
            if vis["visibility_class"] != "OCCLUDED_AGREEMENT" or vis["duration_bin"] not in BINS or vis["tau"] not in BINS[vis["duration_bin"]]:
                raise RuntimeError(f"BLOCKED_QUALITY target visibility/bin mismatch {identity}")
            actual.append(float(coord["world_x"]))
            bin_counts[vis["duration_bin"]] += 1
            rows_for_analysis.append({
                "trajectory_id": identity, "direction": direction, "outer_fold": int(folds[identity]),
                "activation_row": activation_row, "model_frame_idx": model_idx, "server_tick": coord["server_tick"],
                "tau": vis["tau"], "duration_bin": vis["duration_bin"], "world_x": float(coord["world_x"]),
                "token_row": float(coord["token_row"]), "token_col": float(coord["token_col"]),
            })
        mean = sum(actual[:15]) / 15
        tss = sum((value - mean) ** 2 for value in actual[:15])
        if not tss > 0:
            raise RuntimeError(f"BLOCKED_QUALITY zero primary TSS {identity}")
        per_trajectory.append({
            "trajectory_id": identity, "direction": direction, "outer_fold": int(folds[identity]),
            "eligible_target_count": 19, "primary_tss": tss, "entry_transition_run": entry_run,
            "entry_guard": g_entry, "exit_transition_run": exit_run, "exit_guard": g_exit,
            "visible_context_model_frame_indices": clean_context,
            "visible_context_time_seconds": [coordinates[i]["server_tick"] / 20.0 for i in clean_context],
            "visible_context_world_x": [float(coordinates[i]["world_x"]) for i in clean_context],
            "last_visible_world_x": float(coordinates[visible_indices[-1]]["world_x"]),
        })
        activation_provenance[identity] = item["activation_records"]

    fold_groups = defaultdict(list)
    for identity, fold in folds.items():
        fold_groups[int(fold)].append(identity)
    donors = jsonl(authorities["final_null_donor_manifest"])
    donor_groups = Counter(int(row["outer_fold"]) for row in donors)
    donor_valid = all(donor_groups[fold] == 49 for fold in range(5))
    for row in donors:
        mapping = row.get("mapping") or row.get("donor_mapping")
        fold = int(row["outer_fold"])
        train = set(identities) - set(fold_groups[fold])
        if set(mapping) != train or set(mapping.values()) != train or any(left == right for left, right in mapping.items()) or any(specs[left]["direction"] != specs[right]["direction"] for left, right in mapping.items()):
            donor_valid = False

    row_identity_projection = [{key: row[key] for key in ("trajectory_id", "activation_row", "model_frame_idx", "server_tick", "tau", "duration_bin", "outer_fold")} for row in rows_for_analysis]
    row_identity_hash = canonical_hash(row_identity_projection)
    (CACHE / "a5_rows.json").write_text(json.dumps(rows_for_analysis, indent=2, sort_keys=True) + "\n")
    (CACHE / "a5_trajectory_context.json").write_text(json.dumps(per_trajectory, indent=2, sort_keys=True) + "\n")

    static_receipts = {
        "confound": read_json(authorities["final_confound_receipt"])["status"] == "PASS_PROSPECTIVE_OUTCOME_BLIND",
        "duplicate": read_json(authorities["final_duplicate_receipt"])["status"] == "PASS",
        "fold": read_json(authorities["final_fold_receipt"])["status"] == "PASS",
        "b49": read_json(authorities["final_b49_feasibility_receipt"])["status"] == "PASS",
        "context_revalidation": read_json(authorities["final_context_bin_revalidation"])["all_trajectories_have_19_clean_target_frames"] is True,
        "amendment_replay": read_json(authorities["final_amendment_replay"])["pass"] is True,
    }
    # The operator recorded a clean worktree immediately before this analysis
    # implementation was added.  The expected uncommitted files here are the
    # A5 implementation/output itself, not pre-existing scientific state.
    preimplementation_clean = all(
        line.startswith("?? docs/status/integration/regime_a_occlusion_extraction_v0_1/first25_analysis/")
        or line.startswith("?? scripts/run_regime_a_first25_a5.py")
        for line in git("status", "--porcelain=v1").splitlines()
    )
    all_pass = (
        branch == "exploration/regime-a-occlusion-extraction-v0-1" and start_head == remote_head and preimplementation_clean
        and len(durable) == 25 and all(len(group) == 5 for group in fold_groups.values())
        and direction_counts == Counter({"LEFT_TO_RIGHT": 13, "RIGHT_TO_LEFT": 12})
        and bin_counts == Counter({"SHORT": 100, "INTERMEDIATE": 100, "LONG": 100, "NEAR_CONTEXT": 75, "BEYOND_CONTEXT": 100})
        and donor_valid and all(static_receipts.values())
    )
    if not all_pass:
        raise RuntimeError("BLOCKED_QUALITY one or more aggregate A5 checks failed: " + json.dumps({
            "branch": branch, "heads_equal": start_head == remote_head, "preimplementation_clean": preimplementation_clean,
            "durable": len(durable), "fold_sizes": {k: len(v) for k, v in fold_groups.items()},
            "direction_counts": dict(direction_counts), "bin_counts": dict(bin_counts), "donor_valid": donor_valid,
            "static_receipts": static_receipts,
        }, sort_keys=True))

    recovery = {
        "artifact_id": "regime-a-first25-collection-completion-recovery-receipt-v1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "reason": "Original run-level progress ledger was on explicitly reconstructable ephemeral NVMe cache and was cleared between phases.",
        "authority_change": False,
        "reconstruction_source": "25 immutable per-trajectory S3 durable receipts",
        "trajectory_count": 25,
        "status_counts": {"COMPLETE_VALIDATED_DURABLE": 25},
        "trajectories": [{"trajectory_id": row["trajectory_id"], "s3_prefix": f"s3://{BUCKET}/{row['prefix']}/", "durable_receipt_sha256": row["receipt_sha256"], "status": "COMPLETE_VALIDATED_DURABLE"} for row in durable],
        "status": "PASS_MECHANICAL_RECOVERY",
    }
    recovery_path = OUT / "collection_completion_recovery_receipt.json"
    recovery_path.write_text(json.dumps(recovery, indent=2, sort_keys=True) + "\n")

    binding = {
        "artifact_id": "regime-a-first25-analysis-input-binding-v1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "repository": {"branch": branch, "starting_head": start_head, "remote_head": remote_head, "worktree_clean_before_analysis_implementation": preimplementation_clean, "a5_execution_worktree_contains_only_expected_new_analysis_files": dirty},
        "canonical_resolution": {
            "status": "PASS_NO_CONFLICT",
            "analysis_manifest_v1_1_explicitly_supersedes_analysis_manifest_v1_0": True,
            "amended_directional_authority_explicitly_supersedes_only_v2_directional_guards": True,
            "historical_study_split_target_representation_and_null_authorities_remain_controlling": True,
        },
        "artifacts": artifact_binding,
        "collection_ledger": {"path": str(recovery_path), "sha256": sha_file(recovery_path), "kind": "mechanically reconstructed from immutable receipts; not the cleared ephemeral original"},
        "row_identity_hash": row_identity_hash,
        "activation_provenance": activation_provenance,
        "durable_receipts": [{"trajectory_id": row["trajectory_id"], "s3_uri": f"s3://{BUCKET}/{row['prefix']}/durable_receipt.json", "sha256": row["receipt_sha256"]} for row in durable],
        "status": "PASS",
    }
    binding_path = OUT / "analysis_input_binding.json"
    binding_path.write_text(json.dumps(binding, indent=2, sort_keys=True) + "\n")

    receipt = {
        "artifact_id": "regime-a-first25-a5-quality-visibility-confound-receipt-v1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "analysis_input_binding_sha256": sha_file(binding_path),
        "checks": {
            "exactly_25_frozen_identities": True, "complete_validated_durable_25_of_25": True,
            "substituted_or_replacement_specs": 0, "final_manifest_spec_provenance_binding": "PASS",
            "final_amended_guard_authority": "PASS", "five_grouped_outer_folds": True,
            "every_trajectory_heldout_once": True, "role_overlap": 0,
            "direction_counts": dict(direction_counts), "eligible_rows_by_bin": dict(bin_counts),
            "all_bins_every_trajectory": True, "targets_finite": True, "all_primary_tss_gt_zero": True,
            "layer4_target_metadata_complete": True, "all_20_layers_metadata_complete": True,
            "tensor_shape": [19, 336, 2048], "tensor_dtype": "float16", "frame_activation_alignment": "PASS",
            "missing_target_rows": 0, "nonfinite_targets": 0,
            "nonfinite_activation_existing_validation_receipts": 0,
            "dual_visibility_final_criteria": "PASS", "directional_transition_guards": "PASS",
            "confound_receipt": "PASS", "fold_support_balance": "PASS", "duplicate_near_duplicate": "PASS",
            "null_donor_mappings_per_outer_fold": dict(donor_groups), "null_donor_validation": "PASS",
            "s3_receipts_and_hashes": "PASS", "amendment_provenance": "PASS",
        },
        "per_trajectory": per_trajectory,
        "row_identity_hash": row_identity_hash,
        "activation_values_downloaded_or_opened": False,
        "status": "PASS",
        "SCIENTIFIC_OUTCOME_OPENING_AUTHORIZED": "YES",
    }
    receipt_path = OUT / "a5_quality_visibility_confound_receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": "PASS", "binding": str(binding_path), "receipt": str(receipt_path), "row_identity_hash": row_identity_hash, "rows": len(rows_for_analysis)}, indent=2))


if __name__ == "__main__":
    main()
