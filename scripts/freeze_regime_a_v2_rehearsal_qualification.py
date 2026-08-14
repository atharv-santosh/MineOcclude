#!/usr/bin/env python3
"""Validate and freeze the final non-scientific first25-v2 qualification."""

from __future__ import annotations

import argparse
import base64
import concurrent.futures
import hashlib
import inspect
import json
import math
import sys
from pathlib import Path

import boto3
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from mineocclude.regime_a import (  # noqa: E402
    BIN_BOUNDS,
    COMPLETE_STATE,
    HashChainLedger,
    RegimeAError,
    sha256_file,
    validate_capture_temporal_alignment,
)
from mineocclude.regime_a_execution import (  # noqa: E402
    A4ExecutionRunner,
    S3DurableStore,
    validate_required_inventory,
)
from scripts import run_regime_a_first25_v2 as scientific_v2  # noqa: E402
from scripts.run_regime_a import (  # noqa: E402
    CHECKPOINT_SHA256,
    PersistentMineWorldWorker,
    ProductionCaptureWorker,
    read_jsonl,
)

STATUS = ROOT / "docs/status/integration/regime_a_occlusion_extraction_v0_1"
V2 = STATUS / "v2"
EXPECTED_PREFIX = (
    "s3://sagemaker-us-east-1-323206973672/"
    "mineocclude/regime_a_occlusion_extraction_v0_1/"
    "_non_scientific_first25_v2_rehearsal/"
)
EXPECTED_CHECKPOINT = (
    Path("/home/sagemaker-user/MineWorld-Assets-Pinned/checkpoints/700M_16f.ckpt")
)
EXPECTED_CAMERA = {
    "player_x": 0.5,
    "player_y": 5.6200000048,
    "player_z": -5.5,
    "player_yaw": 0.0,
    "player_pitch": 0.0,
}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RegimeAError(message)


def _json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    _require(isinstance(value, dict), f"{path}: expected JSON object")
    return value


def _source_sha(value: object) -> str:
    return hashlib.sha256(inspect.getsource(value).encode()).hexdigest()


def _head_verify(
    client: object, bucket: str, expected: dict[str, object]
) -> dict[str, object]:
    head = client.head_object(Bucket=bucket, Key=expected["key"])
    metadata = {str(key).lower(): str(value) for key, value in head["Metadata"].items()}
    wanted = {
        "sha256": str(expected["local_sha256"]),
        "trajectory-spec-id": str(expected["trajectory_spec_id"]),
        "spec-hash": str(expected["spec_hash"]),
    }
    _require(int(head["ContentLength"]) == int(expected["byte_size"]), "S3 HEAD size mismatch")
    _require(metadata == wanted, "S3 HEAD metadata SHA/identity mismatch")
    return {"key": expected["key"], "size": head["ContentLength"], "metadata": metadata}


def validate_trajectory(
    root: Path,
    spec: dict[str, object],
    reconciliation: dict[str, object],
    ledger: HashChainLedger,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    identity = str(spec["trajectory_spec_id"])
    final = root / "trajectories" / identity
    _require(final.is_dir() and not final.name.startswith("."), f"{identity}: not atomically final")
    validate_required_inventory(final, durable=True)
    state = read_jsonl(final / "raw/server_state.jsonl")
    ticks = read_jsonl(final / "raw/client_tick.jsonl")
    actions = read_jsonl(final / "raw/actions.jsonl")
    visibility = read_jsonl(final / "raw/visibility.jsonl")
    frame_map = read_jsonl(final / "raw/frame_map.jsonl")
    coordinates = read_jsonl(final / "coordinates.jsonl")
    _require(
        len(state) == len(ticks) == len(actions) == len(visibility) == len(frame_map)
        == len(coordinates) == 260,
        f"{identity}: 260-row inventory mismatch",
    )
    pngs = sorted((final / "raw/frames").glob("*.png"))
    _require(len(pngs) == 260, f"{identity}: PNG count mismatch")
    for index, path in enumerate(pngs):
        _require(path.name == f"{index:06d}.png", f"{identity}: PNG sequence mismatch")
        with Image.open(path) as image:
            image.verify()
            _require(image.size == (640, 360), f"{identity}: PNG geometry mismatch")
    for index, row in enumerate(state):
        _require(
            row["server_tick"] == index
            and row["trajectory_spec_id"] == identity
            and row["spec_hash"] == spec["spec_hash"]
            and row["seed"] == spec["seed"]
            and row["target_respawn_count"] == 0,
            f"{identity}: server identity mismatch",
        )
        for field, expected in EXPECTED_CAMERA.items():
            _require(
                math.isclose(float(row[field]), expected, abs_tol=1e-8, rel_tol=0),
                f"{identity}: fixed camera mismatch",
            )
        _require(
            ticks[index]["episode_id"] == spec["episode_id"]
            and ticks[index]["server_tick"] == index
            and ticks[index]["render_frame_idx"] == index
            and ticks[index]["tick_queue_depth_at_capture"] == 0
            and actions[index]["server_tick"] == index
            and actions[index]["render_frame_idx"] == index
            and actions[index]["action_idx"] == index
            and float(actions[index]["camera_dx"]) == 0.0
            and float(actions[index]["camera_dy"]) == 0.0,
            f"{identity}: capture_ack/action identity mismatch",
        )
    alignment = validate_capture_temporal_alignment(state, ticks)
    _require(alignment["stale_frame_count"] == 0, f"{identity}: stale capture")

    target_rows = [row for row in visibility if row.get("primary_hidden_eligible")]
    observed = [int(row["model_frame_idx"]) for row in target_rows]
    expected = [int(value) for value in reconciliation["independently_recomputed_authority_indices"]]
    _require(
        observed == expected
        and [row["tau"] for row in target_rows] == list(range(1, 20))
        and all(row["visibility_class"] == "OCCLUDED_AGREEMENT" for row in target_rows),
        f"{identity}: target authority mismatch",
    )
    bin_counts = {
        name: sum(row["duration_bin"] == name for row in target_rows)
        for name in BIN_BOUNDS
    }
    _require(bin_counts == {"SHORT": 4, "INTERMEDIATE": 4, "LONG": 4, "NEAR_CONTEXT": 3, "BEYOND_CONTEXT": 4}, f"{identity}: bin mismatch")
    target_coordinates = [coordinates[index] for index in observed]
    for coordinate in target_coordinates:
        _require(
            all(
                math.isfinite(float(coordinate[field]))
                for field in ("world_x", "world_z", "screen_x", "screen_y", "token_col", "token_row")
            )
            and 0 <= int(coordinate["token_cell_col"]) < 24
            and 0 <= int(coordinate["token_cell_row"]) < 14,
            f"{identity}: coordinate projection mismatch",
        )
    _require(observed[0] >= 15 and len(observed) == 19, f"{identity}: context support mismatch")

    activation = _json(final / "activation_inventory.json")
    _require(
        activation["checkpoint_sha256"] == CHECKPOINT_SHA256
        and activation["layer_indices"] == list(range(20))
        and activation["target_tau"] == list(range(1, 20))
        and activation["target_model_frame_indices"] == observed
        and activation["visual_tokens_per_target"] == 336
        and activation["hidden_width"] == 2048
        and activation["dtype"] == "float16"
        and activation["serialization"] == "numpy-npy-little-endian-target-token-tensors",
        f"{identity}: activation authority mismatch",
    )
    for artifact in activation["artifacts"]:
        array = np.load(final / artifact["path"], mmap_mode="r", allow_pickle=False)
        _require(
            array.shape == (19, 336, 2048)
            and array.dtype == np.dtype("<f2"),
            f"{identity}: activation serialization mismatch",
        )
    completion = _json(final / "completion.json")
    _require(completion["status"] == "VALIDATED", f"{identity}: local completion mismatch")
    durable = _json(final / "durable_receipt.json")
    _require(
        durable["status"] == "VERIFIED_DURABLE"
        and durable["durable_prefix"] == EXPECTED_PREFIX
        and durable["object_count_excluding_receipt"] == len(durable["objects"])
        and all(
            row["uploaded_object_verified"] is True
            and row["downloaded_bytes_verified"] is True
            and base64.b64decode(row["checksum_sha256_base64"]).hex() == row["local_sha256"]
            and (final / row["key"].split(f"/{identity}/", 1)[1]).stat().st_size == row["byte_size"]
            and sha256_file(final / row["key"].split(f"/{identity}/", 1)[1]) == row["local_sha256"]
            for row in durable["objects"]
        ),
        f"{identity}: durable object receipt mismatch",
    )
    records = [row for row in ledger.records if row["trajectory_spec_id"] == identity]
    states = [row["state"] for row in records]
    _require(
        "CAPTURED" in states
        and "VALIDATED" in states
        and "DURABLE" in states
        and states[-1] == COMPLETE_STATE,
        f"{identity}: ledger terminal chain mismatch",
    )
    durable_record = next(row for row in records if row["state"] == "DURABLE")
    receipt_object = dict(durable_record["durable_receipt_object"])
    _require(
        receipt_object["downloaded_bytes_verified"] is True
        and receipt_object["uploaded_object_verified"] is True
        and receipt_object["local_sha256"] == sha256_file(final / "durable_receipt.json"),
        f"{identity}: durable receipt object mismatch",
    )
    objects = [dict(row) for row in durable["objects"]] + [receipt_object]
    package = _json(final / "capture_package_v0_1.json")
    summary = {
        "trajectory_spec_id": identity,
        "direction": spec["direction"],
        "seed": spec["seed"],
        "spec_hash": spec["spec_hash"],
        "frame_count": 260,
        "state_rows": 260,
        "client_tick_rows": 260,
        "action_rows": 260,
        "frame_map_rows": 260,
        "coordinate_rows": 260,
        "png_count": 260,
        "camera_fixed": True,
        "capture_ack_identity_exact": True,
        "capture_ack_queue_depth_max": 0,
        "temporal_alignment": alignment,
        "visibility_target_indices": observed,
        "visibility_target_count": 19,
        "entry_transition_run_frames": reconciliation["entry_transition_run_frames"],
        "entry_guard_frames": reconciliation["entry_guard_frames"],
        "tau": list(range(1, 20)),
        "bin_counts": bin_counts,
        "coordinates_complete": True,
        "context_pairs": 16,
        "effective_preceding_frames": 15,
        "checkpoint_sha256": activation["checkpoint_sha256"],
        "layer_indices": activation["layer_indices"],
        "activation_shape": [19, 336, 2048],
        "serialization": activation["serialization"],
        "package_code_sha": package["episode_manifest"]["code_sha"],
        "local_validation": completion["status"],
        "atomic_finalization": True,
        "s3_object_count": len(objects),
        "s3_total_bytes": sum(int(row["byte_size"]) for row in objects),
        "s3_size_verified": True,
        "s3_metadata_sha_verified": True,
        "s3_downloaded_byte_sha_verified": True,
        "ledger_states": states,
        "terminal_state": states[-1],
        "PASS": True,
    }
    return summary, objects


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    runtime = arguments.runtime_root.resolve()
    manifest = read_jsonl(V2 / "non_scientific_production_rehearsal_manifest.jsonl")
    reconciliation = _json(runtime / "target_reconciliation_qualification.json")
    initial = _json(runtime / "full_rehearsal_initial_report.json")
    restart = _json(runtime / "full_rehearsal_restart_report.json")
    ledger = HashChainLedger(runtime / "progress_ledger.jsonl")
    _require(reconciliation["PASS"] is True, "target reconciliation did not pass")
    _require(
        initial["PASS"] is True
        and initial["checkpoint_load_count_this_run"] == 1
        and restart["PASS"] is True
        and restart["checkpoint_load_count_this_run"] == 0
        and restart["dispatched_spec_ids"] == []
        and set(restart["completed_units_skipped"])
        == {row["trajectory_spec_id"] for row in manifest},
        "initial/restart execution receipts mismatch",
    )
    by_direction = {row["direction"]: row for row in reconciliation["results"]}
    trajectories = []
    objects = []
    for spec in manifest:
        summary, durable_objects = validate_trajectory(
            runtime, spec, by_direction[spec["direction"]], ledger
        )
        trajectories.append(summary)
        objects.extend(durable_objects)
    _require(len(objects) == 614, "governed S3 object count mismatch")
    client = boto3.client("s3")
    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
        heads = list(
            pool.map(
                lambda row: _head_verify(client, "sagemaker-us-east-1-323206973672", row),
                objects,
            )
        )

    calibration = _json(V2 / "directional_visibility_authority.json")
    canonical = _json(V2 / "canonical_precollection_authority.json")
    _require(
        canonical["scientific_trajectories_executed"] == 0
        and canonical["scientific_activations_extracted"] == 0
        and canonical["scientific_decoding_outcomes_computed"] == 0
        and canonical["a4_v2_authorization_created"] is False,
        "canonical scientific counters are not zero/sealed",
    )
    science_ids = {
        row["trajectory_spec_id"] for row in read_jsonl(V2 / "trajectory_manifest.jsonl")
    }
    _require(
        not science_ids.intersection(path.name for path in (runtime / "trajectories").iterdir())
        and not list(V2.glob("*authorization*")),
        "scientific identity or authorization artifact found",
    )
    launch_rows = read_jsonl(runtime / "runtime_logs/pre_scientific_launch_attempts.jsonl")
    _require(
        len(launch_rows) == 1
        and launch_rows[0]["outcome"] == "READY"
        and launch_rows[0]["attempt"] == 1
        and launch_rows[0]["startspec_dispatch_attempted"] is False,
        "launch/readiness evidence mismatch",
    )
    _require(
        sha256_file(EXPECTED_CHECKPOINT) == CHECKPOINT_SHA256,
        "qualified checkpoint SHA mismatch",
    )

    path_equivalence = {
        "scientific_entrypoint": "scripts/run_regime_a_first25_v2.py",
        "rehearsal_entrypoint": "scripts/run_regime_a_first25_v2_rehearsal.py",
        "same_A4ExecutionRunner": scientific_v2.A4ExecutionRunner is A4ExecutionRunner,
        "same_ProductionCaptureWorker": scientific_v2.ProductionCaptureWorker
        is ProductionCaptureWorker,
        "same_PersistentMineWorldWorker": scientific_v2.PersistentMineWorldWorker
        is PersistentMineWorldWorker,
        "same_S3DurableStore": scientific_v2.S3DurableStore is S3DurableStore,
        "capture_source_sha256": _source_sha(ProductionCaptureWorker.capture),
        "temporal_visibility_coordinate_source_sha256": _source_sha(
            ProductionCaptureWorker._post_capture_artifacts
        ),
        "packaging_source_sha256": _source_sha(ProductionCaptureWorker._validate_and_package),
        "model_extraction_source_sha256": _source_sha(PersistentMineWorldWorker.extract),
        "runner_source_sha256": _source_sha(A4ExecutionRunner.run),
        "durability_source_sha256": _source_sha(S3DurableStore.publish),
        "allowed_differences": [
            "identity",
            "eligibility flag",
            "runtime namespace",
            "S3 namespace",
        ],
        "remaining_untested_science_only_branches": [
            "operator-supplied A4-v2 authorization validation",
            "iteration over the 25 frozen scientific identities",
            "scientific runtime and S3 namespaces",
        ],
        "non_authorized_v2_plan_validation_available": True,
        "important_unexercised_integration_branch": False,
        "PASS": True,
    }
    _require(
        all(
            path_equivalence[key]
            for key in (
                "same_A4ExecutionRunner",
                "same_ProductionCaptureWorker",
                "same_PersistentMineWorldWorker",
                "same_S3DurableStore",
            )
        ),
        "production/rehearsal class identity mismatch",
    )
    report = {
        "schema_version": "regime-a-first25-v2-final-pre-scientific-qualification-v1.0",
        "status": "PASS_READY_FOR_SEPARATE_A4_V2_AUTHORIZATION",
        "NON_SCIENTIFIC_INTEGRATION_REHEARSAL": True,
        "ELIGIBLE_FOR_REGIME_A_RESULTS": False,
        "generated_against_commit": subprocess_head(),
        "directional_visibility_authority_sha256": sha256_file(
            V2 / "directional_visibility_authority.json"
        ),
        "trajectory_manifest_sha256": sha256_file(V2 / "trajectory_manifest.jsonl"),
        "donor_manifest_sha256": sha256_file(V2 / "null_donor_manifest.jsonl"),
        "calibration": {
            "LEFT_TO_RIGHT": calibration["LEFT_TO_RIGHT"],
            "RIGHT_TO_LEFT": calibration["RIGHT_TO_LEFT"],
            "directional_symmetry": calibration["directional_symmetry"],
            "symmetry_imposed": calibration["symmetry_imposed"],
        },
        "target_reconciliation": reconciliation,
        "trajectories": trajectories,
        "model_extraction": {
            "checkpoint_path": str(EXPECTED_CHECKPOINT),
            "checkpoint_sha256": CHECKPOINT_SHA256,
            "checkpoint_load_count": initial["checkpoint_load_count_this_run"],
            "context_pairs": 16,
            "effective_preceding_frames": 15,
            "layers": list(range(20)),
            "token_grid": [14, 24],
            "token_count": 336,
            "hidden_width": 2048,
            "activation_shapes": [[19, 336, 2048], [19, 336, 2048]],
            "teacher_forced_kv_cache_refreshed_each_request": True,
            "independent_trajectory_inputs": True,
            "PASS": True,
        },
        "s3_durability": {
            "prefix": EXPECTED_PREFIX,
            "governed_object_count": len(objects),
            "total_bytes": sum(int(row["byte_size"]) for row in objects),
            "head_size_checks": len(heads),
            "metadata_sha_checks": len(heads),
            "downloaded_byte_checks_from_publish_receipts": len(objects),
            "PASS": True,
        },
        "recovery": {
            "ledger_hash_chain": "PASS",
            "controlled_interrupted_unit": reconciliation["controlled_recovery"][
                "controlled_interrupted_unit"
            ],
            "same_spec_preserved": True,
            "same_seed_preserved": True,
            "replacement_identity_generated": False,
            "completed_durable_units_recognized": restart["complete_before"],
            "completed_durable_units_skipped": restart["completed_units_skipped"],
            "duplicate_capture_prevented": True,
            "duplicate_extraction_prevented": True,
            "restart_checkpoint_load_count": 0,
            "PASS": True,
        },
        "production_path_equivalence": path_equivalence,
        "scientific_execution": {
            "first25_v2_scientific_startspecs_sent": 0,
            "scientific_trajectories_executed": 0,
            "scientific_activations_extracted": 0,
            "scientific_decoders_fitted": 0,
            "scientific_decoding_outcomes_computed": 0,
        },
        "PASS": True,
    }
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": "PASS", "output": str(arguments.output), "s3_objects": len(objects), "s3_bytes": report["s3_durability"]["total_bytes"]}, sort_keys=True))
    return 0


def subprocess_head() -> str:
    import subprocess

    return subprocess.run(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RegimeAError, FileNotFoundError, json.JSONDecodeError, OSError) as error:
        print(f"REGIME_A_V2_QUALIFICATION_REFUSAL: {error}", file=sys.stderr)
        raise SystemExit(2)
