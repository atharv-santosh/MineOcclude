#!/usr/bin/env python3
"""Produce the repaired-V2 layer-4 activation authority for P6.

The runner is intentionally narrow: it consumes only the locked repaired-V2
accepted attempts, applies the frozen production preprocessing implementation
once, and reuses the validated MineWorld teacher-forced extraction bridge while
retaining only layer 4.  It does not import or execute probe/selection code.
"""

from __future__ import annotations

import argparse
import base64
import dataclasses
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from mineocclude.activations.pool import (  # noqa: E402
    select_visual_token_positions,
)
from mineocclude.contracts.identity import SCHEMA_VERSION  # noqa: E402
from mineocclude.contracts.trajectory import (  # noqa: E402
    EXPECTED_ARTIFACT_FORMATS,
    ROW_STREAMS,
    validate_trajectory_package,
)
from mineocclude.data.convert_mineworld import (  # noqa: E402
    bin_camera,
    flat_to_official_raw_action,
)
from mineocclude.models import mineworld_adapter as adapter_module  # noqa: E402
from mineocclude.models import _mineworld_adapter_wave2 as wave2  # noqa: E402
from mineocclude.models import _mineworld_adapter_wave4 as wave4  # noqa: E402
from mineocclude.models import _mineworld_adapter_wave5 as wave5  # noqa: E402
from scripts import (
    run_person_a_66_cell_production_extraction as production,
)  # noqa: E402
from scripts.run_exploratory_visible_position_diagnostics import (  # noqa: E402
    _teacher_capture_layer4,
)

RUNNER_VERSION = "large-scale-no-wall-p6-layer4-runner-v0.1"
P5A_HEAD = "f9823c63b9c316c3849a6d18ef664faaad8c24e5"
BRANCH = "exploration/large-scale-no-wall-scaling-best-k-v0-1"
STUDY_REL = Path(
    "docs/status/integration/" "exploratory_large_scale_no_wall_scaling_best_k_v0_1"
)
STUDY_ROOT = ROOT / STUDY_REL
COHORT_LOCK = STUDY_ROOT / "accepted_cohort_v2.lock.json"
COHORT_LOCK_SHA256 = "b73d1b6bbedc1ca72dab480ba6f4bafb22aa7c6675bc7a2f0dabf33fff2d8501"
SPLIT_AUTHORITY = STUDY_ROOT / "split_authority.json"
SPLIT_SHA256 = "b39c81454ea18125c373fb3c777ac4c1668882c9c1ad188a7d0f20e0cab43de5"
TEST_GUARD = STUDY_ROOT / "test_guard.lock"
TEST_GUARD_SHA256 = "0adc85a5d90eb92361ba0775d58a6ccc2eb674a8ae5ffd2e816b89d9d9b48ac5"
P5A_RECEIPT = STUDY_ROOT / "p5a_receipt.json"
PRODUCTION_FRAME_MANIFEST = (
    ROOT / "docs/status/person_a_66_cell_preprocessed_media_v0_2/"
    "preprocessed_frame_manifest.json"
)
PRODUCTION_FRAME_MANIFEST_SHA256 = (
    "dda2220d1e388253c671f7a7d879987e53d4c0a1a1e815fbc8da6a19356de5a1"
)
PREPROCESSING_IMPLEMENTATION = (
    ROOT / "src/mineocclude/models/_mineworld_adapter_wave2.py"
)
PREPROCESSING_IMPLEMENTATION_SHA256 = (
    "02fd79fe5cd8463dc0117c3207f8d37c6c4f69b9f7017a9aaa4e8ef5e77609f8"
)
PREPROCESSING_PROFILE = "person-a-bgr2rgb-inter-linear-224x384-v1.0"
PREPROCESS_HASH = "8b585e1ffe7d9b7c7bf549f8b5695825bbd2a5b2579e4adf607ca5fa5786635c"
CHECKPOINT_SHA256 = "a92c311baf49bbf31338da2caaadc9e4f947b94df8abcf75da350c4ae41319c5"
VAE_SHA256 = "370d06be427e034476b6b95ba0080a4b48266e876c4776a757b944b87b87d9ab"

EXTERNAL_ROOT = Path(
    "/mnt/sagemaker-nvme/"
    "mineocclude_large_scale_no_wall_scaling_best_k_v0_1_v2/"
    "p6_layer4_activations_v0_1"
)
INPUT_ROOT = EXTERNAL_ROOT / "model_inputs"
ACTIVATION_ROOT = EXTERNAL_ROOT / "activations"
RUNTIME_ROOT = EXTERNAL_ROOT / "runtime"
EXTERNAL_INPUT_MANIFEST = EXTERNAL_ROOT / "model_input_manifest.json"
EXTERNAL_ACTIVATION_MANIFEST = EXTERNAL_ROOT / "activation_manifest.json"
EXTERNAL_PREP_RECEIPT = EXTERNAL_ROOT / "input_preparation_receipt.json"
EXTERNAL_RUNTIME_RECEIPT = EXTERNAL_ROOT / "runtime_receipt.json"
REPO_INPUT_MANIFEST = STUDY_ROOT / "p6_model_input_manifest.json"
REPO_ACTIVATION_MANIFEST = STUDY_ROOT / "p6_activation_manifest.json"
REPO_DURABILITY_RECEIPT = STUDY_ROOT / "p6_s3_durability_receipt.json"
REPO_RECEIPT = STUDY_ROOT / "p6_receipt.json"
S3_BUCKET = "sagemaker-us-east-1-323206973672"
S3_PREFIX = (
    "mineocclude/exploratory_large_scale_no_wall_scaling_best_k_v0_1/"
    "repaired_v2/p6_layer4_activations_v0_1"
)
S3_URI = f"s3://{S3_BUCKET}/{S3_PREFIX}/"

LAYER_IDX = 4
HOOK_SITE = "decoder_layer_output_residual_stream"
TOKEN_GRID = (14, 24)
TOKEN_COUNT = 336
HIDDEN_WIDTH = 2048
FRAME_COUNT = 60
TRAJECTORY_COUNT = 120
ROW_COUNT = 7200
WINDOW_SCHEDULE = ((0, 16), (16, 32), (32, 48), (48, 60))
INPUT_SHAPE = (FRAME_COUNT, 3, 224, 384)
TOKEN_SHAPE = (FRAME_COUNT, TOKEN_COUNT, HIDDEN_WIDTH)
POOLED_SHAPE = (FRAME_COUNT, HIDDEN_WIDTH)
POOL_TOLERANCE = 1e-3


class P6Error(RuntimeError):
    """Fail-closed P6 authority or extraction error."""


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return sha256_bytes(canonical_bytes(value))


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise P6Error(f"JSON authority is not a mapping: {path}")
    return value


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    with temporary.open("wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def write_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    payload = b"".join(canonical_bytes(dict(row)) + b"\n" for row in rows)
    with path.open("wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def run_git(*args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(ROOT), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def require_hash(path: Path, expected: str, label: str) -> None:
    if not path.is_file():
        raise P6Error(f"missing {label}: {path}")
    observed = sha256_file(path)
    if observed != expected:
        raise P6Error(f"{label} SHA-256 mismatch: expected {expected}, got {observed}")


def verify_repository_authority() -> None:
    if run_git("branch", "--show-current") != BRANCH:
        raise P6Error("branch differs from frozen P6 start authority")
    if run_git("rev-parse", "HEAD") != P5A_HEAD:
        raise P6Error("HEAD differs from frozen P5A authority")
    if run_git("rev-parse", f"origin/{BRANCH}") != P5A_HEAD:
        raise P6Error("origin differs from frozen P5A authority")
    require_hash(COHORT_LOCK, COHORT_LOCK_SHA256, "V2 cohort lock")
    require_hash(SPLIT_AUTHORITY, SPLIT_SHA256, "P5 split authority")
    require_hash(TEST_GUARD, TEST_GUARD_SHA256, "P5 test guard")
    require_hash(
        PRODUCTION_FRAME_MANIFEST,
        PRODUCTION_FRAME_MANIFEST_SHA256,
        "production preprocessing manifest",
    )
    require_hash(
        PREPROCESSING_IMPLEMENTATION,
        PREPROCESSING_IMPLEMENTATION_SHA256,
        "preprocessing implementation",
    )
    p5a = read_json(P5A_RECEIPT)
    if p5a.get("safe_for_p6") is not True:
        raise P6Error("P5A does not authorize P6")
    split = read_json(SPLIT_AUTHORITY)
    if (
        split.get("primary_split_total") != 120
        or split.get("v1_primary_intersection") != 0
        or split.get("train_test_overlap") != 0
        or split.get("fixed_test", {}).get("count") != 18
        or split.get("training_pool", {}).get("count") != 102
    ):
        raise P6Error("P5/P5A split authority is inconsistent")
    profile = read_json(PRODUCTION_FRAME_MANIFEST).get("person_a_preprocessing", {})
    expected_profile = {
        "colour_conversion": "cv2.COLOR_BGR2RGB",
        "implementation_sha256": PREPROCESSING_IMPLEMENTATION_SHA256,
        "interpolation": "cv2.INTER_LINEAR",
        "preprocess_hash": PREPROCESS_HASH,
        "preprocessing_identity": PREPROCESSING_PROFILE,
        "source_shape_hwc": [360, 640, 3],
    }
    if any(profile.get(key) != value for key, value in expected_profile.items()):
        raise P6Error("production preprocessing authority is inconsistent")


def cohort_entries() -> tuple[dict[str, Any], ...]:
    lock = read_json(COHORT_LOCK)
    entries = tuple(dict(entry) for entry in lock.get("entries", []))
    spec_ids = [entry.get("trajectory_spec_id") for entry in entries]
    if (
        lock.get("entry_count") != TRAJECTORY_COUNT
        or len(entries) != TRAJECTORY_COUNT
        or lock.get("v1_entries_included") != 0
        or len(set(spec_ids)) != TRAJECTORY_COUNT
        or not all(str(value).startswith("fresh_vp_v2_") for value in spec_ids)
    ):
        raise P6Error("accepted repaired-V2 cohort membership is invalid")
    if sorted(entry["layout_id"] for entry in entries).count("L01") != 20:
        raise P6Error("V2 cohort layout balance is invalid")
    for layout_number in range(1, 7):
        layout = f"L{layout_number:02d}"
        if sum(entry["layout_id"] == layout for entry in entries) != 20:
            raise P6Error(f"V2 cohort does not contain 20 rows for {layout}")
    return entries


def inventory_index(attempt_root: Path, entry: Mapping[str, Any]) -> dict[str, Any]:
    manifest_path = attempt_root / "sha256_manifest.json"
    require_hash(
        manifest_path,
        entry["checksums"]["attempt_manifest_sha256"],
        f"{entry['trajectory_spec_id']} attempt manifest",
    )
    manifest = read_json(manifest_path)
    records = manifest.get("files", [])
    index = {record["path"]: record for record in records}
    if len(index) != manifest.get("file_count") or len(index) != len(records):
        raise P6Error(f"{entry['trajectory_spec_id']}: invalid attempt inventory")
    return index


def verify_inventory_file(
    attempt_root: Path, inventory: Mapping[str, Any], relative: str
) -> Path:
    record = inventory.get(relative)
    path = attempt_root / relative
    if record is None or not path.is_file():
        raise P6Error(f"accepted source file is absent: {path}")
    payload_size = path.stat().st_size
    if payload_size != record["byte_size"] or sha256_file(path) != record["sha256"]:
        raise P6Error(f"accepted source file checksum mismatch: {path}")
    return path


def entry_context(entry: Mapping[str, Any], *, verify_pixels: bool) -> dict[str, Any]:
    spec_id = entry["trajectory_spec_id"]
    attempt_root = Path(entry["local_attempt_root"])
    expected_attempt_name = f"attempt_{int(entry['accepted_attempt']):02d}"
    if not attempt_root.is_dir() or attempt_root.name != expected_attempt_name:
        raise P6Error(f"{spec_id}: accepted local attempt is absent")
    inventory = inventory_index(attempt_root, entry)
    authority_files = (
        ("capture_provenance.json", "capture_provenance_sha256"),
        ("frame_map.jsonl", "frame_map_sha256"),
        ("raw/client/raw_actions.jsonl", "raw_actions_sha256"),
        ("raw/server/server_state.jsonl", "server_state_sha256"),
    )
    for relative, key in authority_files:
        path = verify_inventory_file(attempt_root, inventory, relative)
        if sha256_file(path) != entry["checksums"][key]:
            raise P6Error(f"{spec_id}: {key} differs from cohort lock")
    frame_map = read_jsonl(attempt_root / "frame_map.jsonl")
    if (
        len(frame_map) != FRAME_COUNT
        or [row["model_frame_idx"] for row in frame_map] != list(range(FRAME_COUNT))
        or [row["render_frame_idx"] for row in frame_map] != list(range(FRAME_COUNT))
    ):
        raise P6Error(f"{spec_id}: frame map is not exact contiguous 0..59")
    trajectory_ids = {row["trajectory_id"] for row in frame_map}
    if len(trajectory_ids) != 1:
        raise P6Error(f"{spec_id}: frame map has multiple trajectory IDs")
    trajectory_id = trajectory_ids.pop()
    for index, row in enumerate(frame_map):
        relative = f"raw/client/frames_640x360/{index:06d}.png"
        path = verify_inventory_file(attempt_root, inventory, relative)
        if row.get("frame_640_sha256") != inventory[relative]["sha256"]:
            raise P6Error(f"{spec_id}:{index}: frame-map checksum mismatch")
        if verify_pixels:
            image = cv2.imread(str(path), cv2.IMREAD_COLOR)
            if image is None or image.shape != (360, 640, 3) or image.dtype != np.uint8:
                raise P6Error(f"{spec_id}:{index}: invalid 640x360 PNG")
    return {
        "entry": dict(entry),
        "attempt_root": attempt_root,
        "inventory": inventory,
        "frame_map": frame_map,
        "trajectory_id": trajectory_id,
    }


def capture_key(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "episode_id": str(row["episode_id"]),
        "trajectory_id": str(row["trajectory_id"]),
        "server_tick": int(row["server_tick"]),
        "render_frame_idx": int(row["render_frame_idx"]),
        "action_idx": int(row["action_idx"]),
        "model_frame_idx": int(row["model_frame_idx"]),
    }


def tri(positive: Any, negative: Any) -> int:
    if bool(positive):
        return 1
    if bool(negative):
        return 2
    return 0


def adapter_package(context: Mapping[str, Any]) -> dict[str, Any]:
    root = context["attempt_root"]
    inventory = context["inventory"]
    trajectory_id = context["trajectory_id"]
    processed = root / "processed" / trajectory_id
    frame_map = context["frame_map"]
    streams: dict[str, list[dict[str, Any]]] = {name: [] for name in ROW_STREAMS}
    previous_hotbar: int | None = None
    seed = int(context["entry"]["capture_seed"])
    for row in frame_map:
        key = capture_key(row)
        official = flat_to_official_raw_action(row, prev_hotbar=previous_hotbar)
        previous_hotbar = int(row["hotbar"])
        streams["frame_map"].append(dict(key))
        streams["raw_actions"].append({**key, "raw_action": official})
        streams["normalized_actions"].append(
            {
                **key,
                "normalized_action": {
                    "camera_component_0": bin_camera(float(row["camera_dy"])),
                    "camera_component_1": bin_camera(float(row["camera_dx"])),
                    "hotbar": int(row["hotbar"]),
                    "forward_back": tri(row["forward"], row["back"]),
                    "left_right": tri(row["left"], row["right"]),
                    "sprint_sneak": tri(row["sprint"], row["sneak"]),
                    "use_attack": tri(row["use"], row["attack"]),
                    "jump": 1 if bool(row["jump"]) else 0,
                    "drop_pick_item": tri(row["drop"], row["pick_item"]),
                },
            }
        )
        streams["server_state"].append(
            {
                **key,
                "state": {
                    "axis_pos": float(row["axis_pos"]),
                    "axis_velocity": float(row["axis_velocity"]),
                },
            }
        )
        streams["client_tick_log"].append(
            {**key, "client_tick": int(row["render_frame_idx"])}
        )
        streams["visibility"].append(
            {**key, "visibility": "visible" if row["visible_flag"] else "occluded"}
        )
        streams["seed_noise"].append(
            {**key, "seed": seed, "noise_draw": float(row["noise_draw"])}
        )
    artifacts: dict[str, dict[str, str]] = {}
    artifact_sources = {
        "frame_map": "frame_map.jsonl",
        "raw_actions": "raw/client/raw_actions.jsonl",
        "normalized_actions": "frame_map.jsonl",
        "server_state": "raw/server/server_state.jsonl",
        "client_tick_log": "raw/client/client_tick.jsonl",
        "visibility": "frame_map.jsonl",
        "seed_noise": "noise_schedule.jsonl",
    }
    for name, relative in artifact_sources.items():
        path = verify_inventory_file(root, inventory, relative)
        artifacts[name] = {
            "path": str(path),
            "format": EXPECTED_ARTIFACT_FORMATS[name],
            "sha256": inventory[relative]["sha256"],
        }
    qa_candidates = sorted(processed.glob("qa_report_*.json"))
    if len(qa_candidates) != 1:
        raise P6Error(f"{trajectory_id}: expected one QA report")
    extra = {
        "config": root / "raw/server/reset_result.json",
        "diagnostics": qa_candidates[0],
    }
    for name, path in extra.items():
        relative = str(path.relative_to(root))
        verify_inventory_file(root, inventory, relative)
        artifacts[name] = {
            "path": str(path),
            "format": EXPECTED_ARTIFACT_FORMATS[name],
            "sha256": inventory[relative]["sha256"],
        }
    video = processed / "video_640x360.mp4"
    video_relative = str(video.relative_to(root))
    verify_inventory_file(root, inventory, video_relative)
    frame0 = streams["frame_map"][0]
    qa_sha = sha256_file(qa_candidates[0])
    package = {
        "schema_version": SCHEMA_VERSION,
        "episode_id": str(frame0["episode_id"]),
        "trajectory_id": trajectory_id,
        "seed": seed,
        "media": {
            "mode": "mp4",
            "path": str(video),
            "width": 640,
            "height": 360,
            "fps": 20.0,
            "frame_count": FRAME_COUNT,
            "sha256": inventory[video_relative]["sha256"],
        },
        "artifacts": artifacts,
        "streams": streams,
        "impulse_orientation": {
            "status": "verified",
            "fixture_id": "p1-designated-camera-axis-impulse-authority",
            "camera_component_0_observed_effect": "runtime_no_component_0_effect",
            "camera_component_1_observed_effect": (
                "runtime_positive_component_1_step_in_visual_i_to_i_plus_1"
            ),
            "evidence_hash": qa_sha,
        },
    }
    validation = validate_trajectory_package(package)
    if not validation.accepted:
        detail = "; ".join(
            f"{item.code.value}:{item.message}" for item in validation.rejections[:3]
        )
        raise P6Error(f"{trajectory_id}: adapter package rejected: {detail}")
    return package


def validate_input_chunk(path: Path, entry: Mapping[str, Any]) -> dict[str, Any]:
    completion = read_json(path / "completion.json")
    if (
        completion.get("trajectory_spec_id") != entry["trajectory_spec_id"]
        or completion.get("spec_hash") != entry["spec_hash"]
        or completion.get("accepted_attempt") != entry["accepted_attempt"]
    ):
        raise P6Error(f"{entry['trajectory_spec_id']}: input completion identity drift")
    payload_path = path / "frames.f32.npy"
    rows_path = path / "rows.jsonl"
    if (
        sha256_file(payload_path) != completion["payload_sha256"]
        or sha256_file(rows_path) != completion["rows_sha256"]
    ):
        raise P6Error(f"{entry['trajectory_spec_id']}: input chunk hash mismatch")
    frames = np.load(payload_path, mmap_mode="r", allow_pickle=False)
    rows = read_jsonl(rows_path)
    if (
        frames.shape != INPUT_SHAPE
        or frames.dtype != np.float32
        or len(rows) != FRAME_COUNT
        or [row["model_frame_idx"] for row in rows] != list(range(FRAME_COUNT))
        or not np.isfinite(frames).all()
    ):
        raise P6Error(f"{entry['trajectory_spec_id']}: invalid model-input chunk")
    return completion


def prepare_one(context: Mapping[str, Any]) -> dict[str, Any]:
    entry = context["entry"]
    spec_id = entry["trajectory_spec_id"]
    destination = INPUT_ROOT / spec_id
    if (destination / "completion.json").is_file():
        return validate_input_chunk(destination, entry)
    partial = INPUT_ROOT / f".{spec_id}.partial"
    if partial.exists():
        shutil.rmtree(partial)
    partial.mkdir(parents=True)
    rows: list[dict[str, Any]] = []
    frames: np.memmap | None = np.lib.format.open_memmap(
        partial / "frames.f32.npy", mode="w+", dtype=np.float32, shape=INPUT_SHAPE
    )
    try:
        for index, frame_row in enumerate(context["frame_map"]):
            source = (
                context["attempt_root"]
                / "raw/client/frames_640x360"
                / f"{index:06d}.png"
            )
            image = cv2.imread(str(source), cv2.IMREAD_COLOR)
            if image is None:
                raise P6Error(f"{spec_id}:{index}: OpenCV decode failed")
            tensor, evidence = wave2._preprocess_bgr_frame(image)
            frames[index] = tensor
            rows.append(
                {
                    "accepted_attempt": entry["accepted_attempt"],
                    "layout_id": entry["layout_id"],
                    "model_frame_idx": index,
                    "payload_sha256": evidence["output_sha256"],
                    "raw_source_sha256": frame_row["frame_640_sha256"],
                    "render_frame_idx": frame_row["render_frame_idx"],
                    "reporting_stratum": entry["reporting_stratum"],
                    "spec_hash": entry["spec_hash"],
                    "trajectory_id": context["trajectory_id"],
                    "trajectory_shape_class": entry["trajectory_shape_class"],
                    "trajectory_spec_id": spec_id,
                }
            )
        frames.flush()
        del frames
        frames = None
        write_jsonl(partial / "rows.jsonl", rows)
        payload_path = partial / "frames.f32.npy"
        rows_path = partial / "rows.jsonl"
        completion = {
            "accepted_attempt": entry["accepted_attempt"],
            "frame_count": FRAME_COUNT,
            "payload_byte_size": payload_path.stat().st_size,
            "payload_dtype": "float32",
            "payload_sha256": sha256_file(payload_path),
            "payload_shape": list(INPUT_SHAPE),
            "preprocess_hash": PREPROCESS_HASH,
            "preprocessing_identity": PREPROCESSING_PROFILE,
            "rows_sha256": sha256_file(rows_path),
            "spec_hash": entry["spec_hash"],
            "trajectory_id": context["trajectory_id"],
            "trajectory_spec_id": spec_id,
        }
        write_json(partial / "completion.json", completion)
        os.replace(partial, destination)
        return validate_input_chunk(destination, entry)
    except BaseException:
        if frames is not None:
            del frames
        raise


def compact_input_manifest(chunks: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": "large-scale-no-wall-p6-model-input-v0.1",
        "status": "COMPLETE",
        "primary_cohort_version": "V2_ACCEPTED_REPAIRED_PRIMARY",
        "primary_cohort_lock_sha256": COHORT_LOCK_SHA256,
        "trajectory_count": TRAJECTORY_COUNT,
        "frames_per_trajectory": FRAME_COUNT,
        "frame_count": ROW_COUNT,
        "model_frame_indices": [0, FRAME_COUNT - 1],
        "preprocessing": {
            "identity": PREPROCESSING_PROFILE,
            "preprocess_hash": PREPROCESS_HASH,
            "production_manifest_sha256": PRODUCTION_FRAME_MANIFEST_SHA256,
            "implementation_sha256": PREPROCESSING_IMPLEMENTATION_SHA256,
            "source_shape_hwc": [360, 640, 3],
            "output_shape_chw": [3, 224, 384],
            "output_dtype": "float32",
            "colour_conversion": "cv2.COLOR_BGR2RGB",
            "interpolation": "cv2.INTER_LINEAR",
            "normalization": "(x - 0.5) / 0.5 per channel",
            "preprocessed_once": True,
        },
        "v1_trajectory_count": 0,
        "chunks": list(chunks),
    }


def prepare_inputs() -> dict[str, Any]:
    started = time.monotonic()
    verify_repository_authority()
    INPUT_ROOT.mkdir(parents=True, exist_ok=True)
    chunks = []
    trajectory_ids: set[str] = set()
    for number, entry in enumerate(cohort_entries(), start=1):
        context = entry_context(entry, verify_pixels=True)
        if context["trajectory_id"] in trajectory_ids:
            raise P6Error("duplicate accepted runtime trajectory ID")
        trajectory_ids.add(context["trajectory_id"])
        adapter_package(context)
        completion = prepare_one(context)
        chunks.append(completion)
        print(
            f"PREPARED {number}/{TRAJECTORY_COUNT} {entry['trajectory_spec_id']}",
            flush=True,
        )
    manifest = compact_input_manifest(chunks)
    if len(chunks) != TRAJECTORY_COUNT:
        raise P6Error("model-input manifest does not contain 120 trajectories")
    write_json(EXTERNAL_INPUT_MANIFEST, manifest)
    write_json(REPO_INPUT_MANIFEST, manifest)
    return {
        "status": "PASS",
        "manifest": str(EXTERNAL_INPUT_MANIFEST),
        "manifest_sha256": sha256_file(EXTERNAL_INPUT_MANIFEST),
        "elapsed_seconds": time.monotonic() - started,
        "input_bytes": sum(int(chunk["payload_byte_size"]) for chunk in chunks),
    }


def configure_runtime() -> None:
    production.RUN_ID = "large-scale-no-wall-p6-layer4-v0-1"
    production.SESSION_LOG_ROOT = RUNTIME_ROOT / "runner-sessions"
    production.SEED = 20260725
    production.PRECISION = "float16"
    production._RUNTIME = production.Runtime()


def input_frames(context: Mapping[str, Any], runtime_identity: Any) -> tuple[Any, ...]:
    entry = context["entry"]
    root = INPUT_ROOT / entry["trajectory_spec_id"]
    validate_input_chunk(root, entry)
    array = np.load(root / "frames.f32.npy", mmap_mode="r", allow_pickle=False)
    rows = read_jsonl(root / "rows.jsonl")
    result = []
    for identity, row in zip(context["validated"].frame_identities, rows):
        if identity.model_frame_idx != row["model_frame_idx"]:
            raise P6Error(f"{identity}: model-input row order mismatch")
        result.append(
            adapter_module.PreprocessedFrame(
                identity=identity,
                source_frame_idx=row["render_frame_idx"],
                shape=(3, 224, 384),
                dtype="float32",
                color_order="RGB",
                content_sha256=row["payload_sha256"],
                frame=np.asarray(array[identity.model_frame_idx]),
                preprocessing_profile=PREPROCESSING_PROFILE,
                adapter_code_sha256=runtime_identity.adapter_code_sha256,
                mineocclude_revision=runtime_identity.mineocclude_revision,
            )
        )
    return tuple(result)


def save_npy(path: Path, value: np.ndarray) -> None:
    with path.open("wb") as handle:
        np.save(handle, value, allow_pickle=False)
        handle.flush()
        os.fsync(handle.fileno())


def validate_activation_chunk(
    path: Path, entry: Mapping[str, Any], *, full_values: bool
) -> dict[str, Any]:
    completion = read_json(path / "completion.json")
    if (
        completion.get("trajectory_spec_id") != entry["trajectory_spec_id"]
        or completion.get("spec_hash") != entry["spec_hash"]
        or completion.get("accepted_attempt") != entry["accepted_attempt"]
    ):
        raise P6Error(f"{entry['trajectory_spec_id']}: activation identity drift")
    tokens_path = path / "layer4_visual_tokens.f16.npy"
    pooled_path = path / "layer4_global_mean.f32.npy"
    rows_path = path / "rows.jsonl"
    for item, item_path in (
        ("unpooled", tokens_path),
        ("pooled", pooled_path),
        ("rows", rows_path),
    ):
        if (
            item_path.stat().st_size != completion[item]["byte_size"]
            or sha256_file(item_path) != completion[item]["sha256"]
        ):
            raise P6Error(f"{entry['trajectory_spec_id']}: {item} hash mismatch")
    tokens = np.load(tokens_path, mmap_mode="r", allow_pickle=False)
    pooled = np.load(pooled_path, mmap_mode="r", allow_pickle=False)
    rows = read_jsonl(rows_path)
    if (
        tokens.shape != TOKEN_SHAPE
        or tokens.dtype != np.float16
        or pooled.shape != POOLED_SHAPE
        or pooled.dtype != np.float32
        or len(rows) != FRAME_COUNT
        or [row["model_frame_idx"] for row in rows] != list(range(FRAME_COUNT))
        or any(row.get("layer") != LAYER_IDX for row in rows)
    ):
        raise P6Error(f"{entry['trajectory_spec_id']}: activation structure invalid")
    if full_values:
        if not np.isfinite(tokens).all() or not np.isfinite(pooled).all():
            raise P6Error(f"{entry['trajectory_spec_id']}: non-finite activation")
        reproduction = tokens.astype(np.float32).mean(axis=1)
        difference = np.abs(reproduction - pooled)
        maximum = float(difference.max(initial=0.0))
        if maximum > POOL_TOLERANCE:
            raise P6Error(f"{entry['trajectory_spec_id']}: pooled equivalence failed")
    return completion


def extract_one(context: dict[str, Any]) -> dict[str, Any]:
    entry = context["entry"]
    spec_id = entry["trajectory_spec_id"]
    destination = ACTIVATION_ROOT / spec_id
    if (destination / "completion.json").is_file():
        result = validate_activation_chunk(destination, entry, full_values=True)
        return {**result, "skipped_gpu_work": True}
    partial = ACTIVATION_ROOT / f".{spec_id}.partial"
    if partial.exists():
        shutil.rmtree(partial)
    partial.mkdir(parents=True)
    adapter = production._RUNTIME.adapter
    runtime_identity = production._RUNTIME.runtime_identity
    package = adapter_package(context)
    accepted_manifest_sha = entry["checksums"]["attempt_manifest_sha256"]
    validated = adapter.validate_trajectory(
        adapter_module.AcceptedTrajectoryInput(
            schema_version=SCHEMA_VERSION,
            trajectory_id=context["trajectory_id"],
            accepted_manifest_sha256=accepted_manifest_sha,
            document=package,
        )
    )
    if len(validated.frame_identities) != FRAME_COUNT:
        raise P6Error(f"{spec_id}: adapter dropped frames")
    context["validated"] = validated
    frames = input_frames(context, runtime_identity)
    raw_actions = {
        row["model_frame_idx"]: row for row in package["streams"]["raw_actions"]
    }
    actions = tuple(
        adapter.convert_action(
            adapter_module.ActionConversionRequest(
                identity=identity,
                action_idx=raw_actions[identity.model_frame_idx]["action_idx"],
                raw_action=raw_actions[identity.model_frame_idx]["raw_action"],
            )
        )
        for identity in validated.frame_identities
    )
    token_rows: list[np.ndarray] = []
    pooled_rows: list[np.ndarray] = []
    row_records: list[dict[str, Any]] = []
    windows: list[dict[str, Any]] = []
    forward_seconds = 0.0
    import torch

    for start, stop in WINDOW_SCHEDULE:
        window_trajectory = dataclasses.replace(
            validated, frame_identities=validated.frame_identities[start:stop]
        )
        tokenized = adapter.tokenize_trajectory(
            adapter_module.TrajectoryTokenizationRequest(
                runtime_identity=runtime_identity,
                trajectory=window_trajectory,
                frames=frames[start:stop],
                actions=actions[start:stop],
            )
        )
        spans = tokenized.frame_token_map.spans
        if [span.identity.model_frame_idx for span in spans] != list(
            range(start, stop)
        ) or [span.pair_index for span in spans] != list(range(stop - start)):
            raise P6Error(f"{spec_id}: window {start}:{stop} identity drift")
        forward_started = time.monotonic()
        teacher_result, capture = _teacher_capture_layer4(
            production, adapter, runtime_identity, tokenized, accepted_manifest_sha
        )
        forward_seconds += time.monotonic() - forward_started
        activation = capture.output.tensor
        if str(activation.dtype) != "torch.float16":
            raise P6Error(f"{spec_id}: layer-4 output is not float16")
        windows.append(
            {
                "frame_token_map_sha256": tokenized.frame_token_map_sha256,
                "sequence_length": capture.output.sequence_length,
                "start_model_frame_idx": start,
                "stop_model_frame_idx_exclusive": stop,
                "teacher_result_sha256": teacher_result.result_sha256,
            }
        )
        for span in spans:
            selection = select_visual_token_positions(
                tokenized.frame_token_map,
                trajectory_id=span.identity.trajectory_id,
                model_frame_idx=span.identity.model_frame_idx,
                hooked_sequence_length=capture.output.sequence_length,
            )
            if len(selection.positions) != TOKEN_COUNT:
                raise P6Error(f"{spec_id}: visual-token count mismatch")
            position_index = torch.tensor(
                selection.positions, dtype=torch.long, device=activation.device
            )
            selected = (
                activation.detach()
                .index_select(1, position_index)
                .squeeze(0)
                .to(device="cpu", dtype=torch.float16)
                .contiguous()
                .numpy()
                .copy()
            )
            if selected.shape != (TOKEN_COUNT, HIDDEN_WIDTH):
                raise P6Error(f"{spec_id}: visual-token shape mismatch")
            pooled = selected.astype(np.float32).mean(axis=0)
            token_rows.append(selected)
            pooled_rows.append(pooled)
            row_records.append(
                {
                    "accepted_attempt": entry["accepted_attempt"],
                    "frame_token_map_sha256": tokenized.frame_token_map_sha256,
                    "hidden_width": HIDDEN_WIDTH,
                    "layer": LAYER_IDX,
                    "model_frame_idx": span.identity.model_frame_idx,
                    "pooled_dtype": "float32",
                    "spec_hash": entry["spec_hash"],
                    "token_dtype": "float16",
                    "token_grid": list(TOKEN_GRID),
                    "trajectory_id": context["trajectory_id"],
                    "trajectory_spec_id": spec_id,
                    "visual_token_count": TOKEN_COUNT,
                }
            )
        del capture, activation, teacher_result
        torch.cuda.empty_cache()
    tokens = np.stack(token_rows).astype(np.float16, copy=False)
    pooled = np.stack(pooled_rows).astype(np.float32, copy=False)
    if (
        tokens.shape != TOKEN_SHAPE
        or pooled.shape != POOLED_SHAPE
        or not np.isfinite(tokens).all()
        or not np.isfinite(pooled).all()
    ):
        raise P6Error(f"{spec_id}: extracted tensor integrity failed")
    save_npy(partial / "layer4_visual_tokens.f16.npy", tokens)
    save_npy(partial / "layer4_global_mean.f32.npy", pooled)
    write_jsonl(partial / "rows.jsonl", row_records)
    token_path = partial / "layer4_visual_tokens.f16.npy"
    pooled_path = partial / "layer4_global_mean.f32.npy"
    rows_path = partial / "rows.jsonl"
    completion = {
        "accepted_attempt": entry["accepted_attempt"],
        "adapter_package_sha256": canonical_sha256(package),
        "forward_seconds": forward_seconds,
        "forward_window_count": len(windows),
        "pooled": {
            "byte_size": pooled_path.stat().st_size,
            "dtype": "float32",
            "sha256": sha256_file(pooled_path),
            "shape": list(POOLED_SHAPE),
        },
        "pooled_equivalence_max_abs_diff": 0.0,
        "rows": {
            "byte_size": rows_path.stat().st_size,
            "row_count": FRAME_COUNT,
            "sha256": sha256_file(rows_path),
        },
        "spec_hash": entry["spec_hash"],
        "trajectory_id": context["trajectory_id"],
        "trajectory_spec_id": spec_id,
        "unpooled": {
            "byte_size": token_path.stat().st_size,
            "dtype": "float16",
            "sha256": sha256_file(token_path),
            "shape": list(TOKEN_SHAPE),
        },
        "windows": windows,
    }
    write_json(partial / "completion.json", completion)
    os.replace(partial, destination)
    return validate_activation_chunk(destination, entry, full_values=True)


def extract() -> dict[str, Any]:
    started = time.monotonic()
    if not EXTERNAL_INPUT_MANIFEST.is_file():
        raise P6Error("model-input manifest is absent; run prepare first")
    require_hash(
        EXTERNAL_INPUT_MANIFEST,
        sha256_file(REPO_INPUT_MANIFEST),
        "external model-input manifest",
    )
    ACTIVATION_ROOT.mkdir(parents=True, exist_ok=True)
    configure_runtime()
    load_started = time.monotonic()
    production._RUNTIME.ensure_loaded()
    model_load_seconds = time.monotonic() - load_started
    import torch

    torch.cuda.reset_peak_memory_stats()
    completions = []
    retries = 0
    for number, entry in enumerate(cohort_entries(), start=1):
        context = entry_context(entry, verify_pixels=False)
        try:
            completion = extract_one(context)
        except Exception:
            retries += 1
            print(f"RETRY {entry['trajectory_spec_id']}", flush=True)
            context = entry_context(entry, verify_pixels=False)
            completion = extract_one(context)
        completions.append(completion)
        print(
            f"EXTRACTED {number}/{TRAJECTORY_COUNT} {entry['trajectory_spec_id']}",
            flush=True,
        )
    elapsed = time.monotonic() - started
    runtime = {
        "status": "COMPLETE",
        "cuda_version": str(torch.version.cuda),
        "extraction_elapsed_seconds": elapsed - model_load_seconds,
        "forward_window_count": sum(
            item["forward_window_count"] for item in completions
        ),
        "gpu_model": torch.cuda.get_device_properties(0).name,
        "model_load_seconds": model_load_seconds,
        "peak_cuda_allocated_bytes": int(torch.cuda.max_memory_allocated()),
        "torch_version": torch.__version__,
        "total_elapsed_seconds": elapsed,
        "trajectory_retry_count": retries,
    }
    write_json(EXTERNAL_RUNTIME_RECEIPT, runtime)
    return runtime


def activation_manifest() -> tuple[dict[str, Any], dict[str, Any]]:
    started = time.monotonic()
    entries = cohort_entries()
    chunks = []
    row_keys: set[tuple[str, int]] = set()
    max_difference = 0.0
    absolute_sum = 0.0
    difference_count = 0
    nonfinite_count = 0
    for number, entry in enumerate(entries, start=1):
        path = ACTIVATION_ROOT / entry["trajectory_spec_id"]
        completion = validate_activation_chunk(path, entry, full_values=False)
        tokens = np.load(
            path / "layer4_visual_tokens.f16.npy", mmap_mode="r", allow_pickle=False
        )
        pooled = np.load(
            path / "layer4_global_mean.f32.npy", mmap_mode="r", allow_pickle=False
        )
        difference = np.abs(tokens.astype(np.float32).mean(axis=1) - pooled)
        if not np.isfinite(tokens).all() or not np.isfinite(pooled).all():
            raise P6Error(f"{entry['trajectory_spec_id']}: non-finite activation")
        max_difference = max(max_difference, float(difference.max(initial=0.0)))
        absolute_sum += float(difference.sum(dtype=np.float64))
        difference_count += int(difference.size)
        rows = read_jsonl(path / "rows.jsonl")
        for row in rows:
            key = (row["trajectory_spec_id"], row["model_frame_idx"])
            if key in row_keys:
                raise P6Error(f"duplicate activation row key: {key}")
            row_keys.add(key)
        chunks.append(
            {
                "accepted_attempt": entry["accepted_attempt"],
                "layout_id": entry["layout_id"],
                "pooled": {
                    **completion["pooled"],
                    "path": str(
                        Path(entry["trajectory_spec_id"]) / "layer4_global_mean.f32.npy"
                    ),
                },
                "reporting_stratum": entry["reporting_stratum"],
                "rows": {
                    **completion["rows"],
                    "path": str(Path(entry["trajectory_spec_id"]) / "rows.jsonl"),
                },
                "spec_hash": entry["spec_hash"],
                "trajectory_id": completion["trajectory_id"],
                "trajectory_shape_class": entry["trajectory_shape_class"],
                "trajectory_spec_id": entry["trajectory_spec_id"],
                "unpooled": {
                    **completion["unpooled"],
                    "path": str(
                        Path(entry["trajectory_spec_id"])
                        / "layer4_visual_tokens.f16.npy"
                    ),
                },
                "windows": completion["windows"],
            }
        )
        print(f"VALIDATED {number}/{TRAJECTORY_COUNT}", flush=True)
    if len(row_keys) != ROW_COUNT:
        raise P6Error("activation row-key universe is not exactly 7,200")
    runtime = read_json(EXTERNAL_RUNTIME_RECEIPT)
    manifest = {
        "schema_version": "large-scale-no-wall-p6-activation-manifest-v0.1",
        "status": "COMPLETE",
        "experiment": "exploratory_large_scale_no_wall_scaling_best_k_v0_1",
        "cohort_version": "V2_ACCEPTED_REPAIRED_PRIMARY",
        "primary_cohort_lock_sha256": COHORT_LOCK_SHA256,
        "checkpoint": {
            "path": str(production.MAIN_CHECKPOINT),
            "sha256": CHECKPOINT_SHA256,
        },
        "vae": {"path": str(production.VAE_CHECKPOINT), "sha256": VAE_SHA256},
        "preprocessing": {
            "identity": PREPROCESSING_PROFILE,
            "preprocess_hash": PREPROCESS_HASH,
            "production_manifest_sha256": PRODUCTION_FRAME_MANIFEST_SHA256,
        },
        "representation": {
            "hidden_width": HIDDEN_WIDTH,
            "layer": LAYER_IDX,
            "other_layers_retained": False,
            "pooled_dtype": "float32",
            "pooled_shape_per_trajectory": list(POOLED_SHAPE),
            "teacher_forcing": True,
            "token_count": TOKEN_COUNT,
            "token_grid": list(TOKEN_GRID),
            "unpooled_dtype": "float16",
            "unpooled_shape_per_trajectory": list(TOKEN_SHAPE),
            "window_schedule": [list(pair) for pair in WINDOW_SCHEDULE],
        },
        "trajectory_count": TRAJECTORY_COUNT,
        "frames_per_trajectory": FRAME_COUNT,
        "frame_count": ROW_COUNT,
        "row_key": ["trajectory_spec_id", "model_frame_idx"],
        "row_order": "cohort-lock entry order, then ascending model_frame_idx",
        "test_rows_extracted": True,
        "test_rows_used_for_selection": False,
        "checkpoint_hash_prompt_typo_resolved": True,
        "checkpoint_hash_prompt_typo_note": (
            "The original P6 continuation transcribed c0e4 instead of c9e4; "
            "the typo was superseded before model/GPU execution."
        ),
        "chunks": chunks,
    }
    validation = {
        "activation_rows": len(row_keys),
        "duplicate_activation_rows": 0,
        "missing_activation_rows": 0,
        "nonfinite_value_count": nonfinite_count,
        "pooled_equivalence_max_abs_diff": max_difference,
        "pooled_equivalence_mean_abs_diff": absolute_sum / difference_count,
        "pooled_equivalence_tolerance": POOL_TOLERANCE,
        "pooled_equivalence_pass": max_difference <= POOL_TOLERANCE,
        "validation_seconds": time.monotonic() - started,
        "unpooled_bytes": sum(chunk["unpooled"]["byte_size"] for chunk in chunks),
        "pooled_bytes": sum(chunk["pooled"]["byte_size"] for chunk in chunks),
        "runtime": runtime,
    }
    return manifest, validation


def s3_objects() -> list[dict[str, Any]]:
    command = [
        "aws",
        "s3api",
        "list-objects-v2",
        "--bucket",
        S3_BUCKET,
        "--prefix",
        f"{S3_PREFIX}/",
        "--output",
        "json",
    ]
    document = json.loads(
        subprocess.run(command, check=True, capture_output=True, text=True).stdout
    )
    return list(document.get("Contents", []))


def publish() -> dict[str, Any]:
    manifest, validation = activation_manifest()
    write_json(EXTERNAL_ACTIVATION_MANIFEST, manifest)
    manifest_sha = sha256_file(EXTERNAL_ACTIVATION_MANIFEST)
    write_json(REPO_ACTIVATION_MANIFEST, manifest)
    checksum_path = EXTERNAL_ROOT / "activation_manifest.sha256"
    checksum_path.write_text(
        f"{manifest_sha}  activation_manifest.json\n", encoding="utf-8"
    )
    upload_started = time.monotonic()
    subprocess.run(
        [
            "aws",
            "s3",
            "sync",
            str(ACTIVATION_ROOT),
            f"{S3_URI}activations/",
            "--only-show-errors",
            "--checksum-algorithm",
            "SHA256",
        ],
        check=True,
    )
    for source, name in (
        (EXTERNAL_ACTIVATION_MANIFEST, "activation_manifest.json"),
        (checksum_path, "activation_manifest.sha256"),
        (EXTERNAL_RUNTIME_RECEIPT, "runtime_receipt.json"),
    ):
        subprocess.run(
            [
                "aws",
                "s3",
                "cp",
                str(source),
                f"{S3_URI}{name}",
                "--only-show-errors",
                "--checksum-algorithm",
                "SHA256",
            ],
            check=True,
        )
    upload_seconds = time.monotonic() - upload_started
    expected: dict[str, int] = {}
    for path in ACTIVATION_ROOT.rglob("*"):
        if path.is_file():
            key = f"{S3_PREFIX}/activations/{path.relative_to(ACTIVATION_ROOT)}"
            expected[key] = path.stat().st_size
    for path in (EXTERNAL_ACTIVATION_MANIFEST, checksum_path, EXTERNAL_RUNTIME_RECEIPT):
        expected[f"{S3_PREFIX}/{path.name}"] = path.stat().st_size
    observed = {item["Key"]: int(item["Size"]) for item in s3_objects()}
    missing = sorted(key for key, size in expected.items() if observed.get(key) != size)
    unexpected = sorted(key for key in observed if key not in expected)
    if missing or unexpected:
        raise P6Error(
            f"S3 durability inventory mismatch: missing={missing[:3]}, "
            f"unexpected={unexpected[:3]}"
        )
    head = json.loads(
        subprocess.run(
            [
                "aws",
                "s3api",
                "head-object",
                "--bucket",
                S3_BUCKET,
                "--key",
                f"{S3_PREFIX}/activation_manifest.json",
                "--checksum-mode",
                "ENABLED",
                "--output",
                "json",
            ],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    )
    expected_manifest_checksum = base64.b64encode(bytes.fromhex(manifest_sha)).decode(
        "ascii"
    )
    s3_checksum_valid = head.get("ChecksumSHA256") == expected_manifest_checksum
    if not s3_checksum_valid:
        raise P6Error("S3 activation-manifest SHA-256 metadata mismatch")
    durability = {
        "schema_version": "large-scale-no-wall-p6-s3-durability-v0.1",
        "status": "PASS",
        "s3_prefix": S3_URI,
        "activation_manifest_sha256": manifest_sha,
        "expected_object_count": len(expected),
        "observed_object_count": len(observed),
        "missing_object_count": 0,
        "unexpected_object_count": 0,
        "object_sizes_valid": True,
        "manifest_checksum_sha256_valid": True,
        "s3_bytes": sum(expected.values()),
        "upload_seconds": upload_seconds,
    }
    write_json(REPO_DURABILITY_RECEIPT, durability)
    prep_runtime = read_json(EXTERNAL_PREP_RECEIPT)
    runtime = validation["runtime"]
    receipt = {
        "schema_version": "large-scale-no-wall-p6-receipt-v0.1",
        "status": "PASS_AUTHORITATIVE_V2_LAYER4_ACTIVATIONS_DURABLE",
        "p5a_head": P5A_HEAD,
        "checkpoint_hash_prompt_typo_resolved": True,
        "authorities_preserved": {
            "p1": True,
            "p4b_v2_campaign": True,
            "p4c_accepted_cohort": True,
            "p5_p5a_split": True,
        },
        "scope": {
            "cohort": "V2_ACCEPTED_REPAIRED_PRIMARY",
            "trajectory_count": TRAJECTORY_COUNT,
            "frames_per_trajectory": FRAME_COUNT,
            "activation_rows": ROW_COUNT,
            "layer": LAYER_IDX,
            "token_grid": list(TOKEN_GRID),
            "token_count": TOKEN_COUNT,
            "hidden_width": HIDDEN_WIDTH,
            "teacher_forcing": True,
            "window_schedule": [list(pair) for pair in WINDOW_SCHEDULE],
            "v1_rows_extracted": 0,
        },
        "validation": validation,
        "model_input_manifest_sha256": sha256_file(REPO_INPUT_MANIFEST),
        "activation_manifest_sha256": manifest_sha,
        "durability_receipt_sha256": sha256_file(REPO_DURABILITY_RECEIPT),
        "input_preparation_seconds": prep_runtime["elapsed_seconds"],
        "test_rows_extracted": True,
        "test_rows_used_for_selection": False,
        "fresh_activations_extracted": True,
        "fresh_r2_computed": False,
        "token_ranking_performed": False,
        "alpha_selection_performed": False,
        "k_selection_performed": False,
        "target_null_executed": False,
        "p7_started": False,
        "safe_for_p7": True,
        "blocker": None,
        "manual_per_trajectory_commands": 0,
        "operator_intervention_count": 0,
        "runtime": runtime,
    }
    write_json(REPO_RECEIPT, receipt)
    return {
        "status": "PASS",
        "activation_manifest_sha256": manifest_sha,
        "activation_rows": validation["activation_rows"],
        "pooled_equivalence_max_abs_diff": validation[
            "pooled_equivalence_max_abs_diff"
        ],
        "s3_object_count": durability["observed_object_count"],
        "s3_bytes": durability["s3_bytes"],
    }


def gpu_preflight() -> dict[str, Any]:
    import torch

    if not torch.cuda.is_available():
        raise P6Error("CUDA is unavailable")
    properties = torch.cuda.get_device_properties(0)
    return {
        "cuda_available": True,
        "cuda_version": str(torch.version.cuda),
        "gpu_model": properties.name,
        "torch_version": torch.__version__,
        "total_vram_bytes": int(properties.total_memory),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "mode", choices=("prepare", "gpu-preflight", "extract", "publish")
    )
    args = parser.parse_args(argv)
    if args.mode == "prepare":
        result = prepare_inputs()
        write_json(EXTERNAL_PREP_RECEIPT, result)
    elif args.mode == "gpu-preflight":
        result = gpu_preflight()
    elif args.mode == "extract":
        result = extract()
    else:
        result = publish()
    print(json.dumps(result, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
