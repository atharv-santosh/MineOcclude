"""Materialize Person A's 66-cell model-facing frames from Person C's canonical media.

Person C's canonical-media package publishes 2468 lossless 640x360 RGB PNGs
whose pixel digests reproduce Person E's recorded canonical frame hashes. This
builder verifies that package, proves the RGB/BGR boundary on real pixels,
applies Person A's already-frozen ``_preprocess_bgr_frame`` exactly, writes the
2468 model-facing payloads outside the repository, and publishes the
preprocessed-frame manifest plus the successor authority that binds the exact
canonical source-media identity.

It never loads MineWorld weights, never runs extraction, never touches the
lossy MP4 convenience media, and never modifies another role's branch.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from mineocclude.experiments.extraction_queue import (
    ExtractionQueue,
    build_queue_from_matrix,
)
from mineocclude.experiments.mvp_lineage import make_run_id

SCHEMA_VERSION = "0.2"
SCHEMA_PREFIX = "person-a-66-cell-preprocessed-media-v0.2"
FRAME_MANIFEST_SCHEMA_ID = "person-a-preprocessed-frame-manifest-v0.2"
BUILDER_PATH = "scripts/build_person_a_66_cell_preprocessed_media_v0_2.py"
TEST_PATH = "tests/models/test_person_a_66_cell_preprocessed_media_v0_2.py"
DECISION_DATE = "2026-08-07"

A_BRANCH = "role/person-a-model"
A_STARTING_AUTHORITY = "a3bc169d349ca424f6d5af1ecbbb9327b248bfe2"

# --------------------------------------------------------------------------
# Person C canonical-media authority
# --------------------------------------------------------------------------
C_COMMIT = "3846230a4f141a8a55084eeaaa040f9a10cfc408"
C_REMOTE_REF = "origin/role/person-c-data"
C_ROOT = "docs/status/person_c_66_cell_canonical_media_v0_1"
C_MEDIA_MANIFEST_PATH = f"{C_ROOT}/canonical_media_manifest.json"
C_MEDIA_MANIFEST_SHA256 = (
    "a11762bd9292404b58ddccc062ebcf5115d935d61426fff4cd4474c8def257c9"
)
C_TO_A_HANDOFF_PATH = f"{C_ROOT}/c_to_a_media_handoff.json"
C_TO_A_HANDOFF_SHA256 = (
    "94c852466167db01a678d0d7d6a3ae6e3211abaef995f95b20f5d182ed599b3e"
)
C_TO_D_HANDOFF_PATH = f"{C_ROOT}/c_to_d_media_handoff.json"
C_TO_D_HANDOFF_SHA256 = (
    "84b5b927ab41d34d51ebf30f1af9d48cf1b5af9d057518a6ca6338cef7f38a56"
)
C_FRAME_INDEX_PATH = f"{C_ROOT}/canonical_frame_index.jsonl"
C_CANONICALIZER_PATH = "src/mineocclude/data/preprocess.py"
C_CANONICALIZER_SHA256 = (
    "cc80f6eb889ee7794786b26a81dea3647439a2cbc3e7f85235e0215bbd2c319a"
)
C_ACCEPTED_MANIFEST_COMMIT = "a8bed8adf7e24ca7fe5b6b6afa3342da61434be3"
C_ACCEPTED_MANIFEST_PATH = (
    "docs/status/person_c_c7_mvp_handoff_v0_1/trajectories_mvp_manifest.json"
)
C_ACCEPTED_MANIFEST_SHA256 = (
    "96ba43e15bc024aeaef7c519fa4ece0a4afe0bb0e877501dffaca44fee927ff7"
)
C_STRICT_VISIBILITY_COMMIT = "e908ead4a7ff5ab3ae310bb846969a7859fdb26b"
C_STRICT_ROOT = "docs/status/person_c_66_cell_strict_visibility_v0_1"

# --------------------------------------------------------------------------
# Person B authorities (recomputed digests, never taken from conversation)
# --------------------------------------------------------------------------
B_COMMIT = "25e09cb605699cdcb00dec1fbb1726977bec55e0"
B_REMOTE_REF = "origin/role/person-b-analysis"
B_ROOT = "docs/status/person_b_66_cell_oracle_target_v0_1"
B_FOLD_MANIFEST_PATH = (
    "docs/status/person_b_66_cell_preactivation_v0_1/fold_manifest.json"
)

D_REMOTE_REF = "origin/role/person-d-baselines"
E_REMOTE_REF = "origin/role/person-e-operations"

# --------------------------------------------------------------------------
# Person A frozen authorities
# --------------------------------------------------------------------------
A_CONFIG_PATH = "configs/experiments/mvp.yaml"
A_IMPLEMENTATION_PATH = "src/mineocclude/models/_mineworld_adapter_wave2.py"
A_FRAME_MAP_PACKAGE_REL = "data/handoff_a/person_a_66_cell_production_input_v0_1"
A_MATRIX_REPORT_PATH = (
    "docs/status/person_a_phase7_mvp_v0_1/step_7_2_matrix_report.json"
)
A_PRIOR_SUCCESSOR_ROOT = "docs/status/person_a_66_cell_successor_authority_v0_1"
A_PRIOR_SUCCESSOR_CONFIG_PATH = (
    f"{A_PRIOR_SUCCESSOR_ROOT}/successor_extraction_config.json"
)
A_PRIOR_A_TO_D_PATH = f"{A_PRIOR_SUCCESSOR_ROOT}/a_to_d_frame_handoff.json"
A_EXECUTION_HOST_CONTRACT_PATH = (
    "docs/status/person_a_phase6_sagemaker_runtime_addendum_v0_1"
    "/execution_host_contract.json"
)
A_PRIOR_RUN_ID = "mineocclude-run-836009cb74647b413ebc6f40218bc5bf"

SUCCESSOR_CODE_IDENTITY_FILES = (
    A_IMPLEMENTATION_PATH,
    "src/mineocclude/contracts/trajectory.py",
    "src/mineocclude/contracts/activation.py",
    "src/mineocclude/activations/hooks.py",
    "src/mineocclude/activations/pool.py",
    "src/mineocclude/activations/store_v2.py",
    "src/mineocclude/models/mineworld_adapter.py",
    "src/mineocclude/models/_mineworld_adapter_wave3.py",
    "src/mineocclude/models/_mineworld_adapter_wave4.py",
)

EXPECTED_TRAJECTORY_COUNT = 66
EXPECTED_FRAME_COUNT = 2468
LAYER_COUNT = 20
EXPECTED_ACTIVATION_ROW_COUNT = EXPECTED_FRAME_COUNT * LAYER_COUNT
EXPECTED_CHUNK_COUNT = EXPECTED_TRAJECTORY_COUNT * LAYER_COUNT
VECTOR_WIDTH = 2048
EXTRACTION_SEED = 20260725
STORED_ACTIVATION_DTYPE = "float32"
ANALYSIS_ARITHMETIC_DTYPE = "float64"
HOOK_SITE = "decoder_layer_output_residual_stream"

CANONICAL_DIMENSIONS = "640x360"
MODEL_FACING_SHAPE_CHW = (3, 224, 384)
MODEL_FACING_PAYLOAD_BYTES = 3 * 224 * 384 * 4
MODEL_FACING_DTYPE = "float32"
PAYLOAD_FORMAT = "raw-little-endian-float32-c-order"
TRANSFORMATION_IDENTITY = "person-a-bgr2rgb-inter-linear-224x384-v1.0"

#: Payload bytes live outside the repository, matching the standing Person A
#: policy of committing identities rather than large derived byte payloads.
PAYLOAD_ROOT = Path(
    r"C:\Users\lollo\MineOcclude-Person-A-Outputs"
    r"\person-a-66-cell-preprocessed-frames-v0-2"
)

STATUS_ROOT = ROOT / "docs" / "status" / "person_a_66_cell_preprocessed_media_v0_2"
STATUS_ROOT_REL = "docs/status/person_a_66_cell_preprocessed_media_v0_2"

OUTPUT_PATHS = (
    "a_to_d_frame_handoff.json",
    "authority_binding.json",
    "byte_transport_plan.json",
    "phase6_precondition_receipt.json",
    "preprocessed_frame_manifest.json",
    "rgb_bgr_boundary_proof.json",
    "sha256_inventory.json",
    "successor_extraction_config.json",
    "successor_extraction_queue_state.json",
    "validation_receipt.json",
)

PROTECTED_FALSE_FIELDS = frozenset(
    {
        "activations_generated",
        "aggregate_phase6_runtime_authorized",
        "destination_fabricated",
        "foreign_branch_merged",
        "gpu_extraction_started",
        "historical_evidence_rewritten",
        "model_loaded",
        "mp4_used_as_pixel_source",
        "person_a_phase6_authorized",
        "phase6_runtime_infrastructure_ready",
        "pre_swap_applied",
        "restricted_to_person_b_admitted_rows",
        "sagemaker_byte_access_ready",
        "scientific_execution_performed",
        "self_authorizes_phase6",
        "value_accepted_from_conversation",
    }
)


class PreprocessedMediaError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


def _fail(code: str, message: str) -> None:
    raise PreprocessedMediaError(code, message)


# --------------------------------------------------------------------------
# Primitives
# --------------------------------------------------------------------------
def _completed(command: list[str]) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(command, cwd=ROOT, check=False, capture_output=True)


def _git_text(*arguments: str) -> str:
    result = _completed(["git", *arguments])
    if result.returncode != 0:
        _fail("git_failed", result.stderr.decode("utf-8", errors="replace").strip())
    return result.stdout.decode("utf-8").strip()


def _git_bytes(commit: str, path: str) -> bytes:
    result = _completed(["git", "show", f"{commit}:{path}"])
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        _fail("git_object_missing", f"{commit}:{path}: {detail}")
    return result.stdout


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def repository_bytes(path: str) -> bytes:
    return (ROOT / path).read_bytes().replace(b"\r\n", b"\n")


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _canonical_sha256(value: Any) -> str:
    return _sha256(_canonical_bytes(value))


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _local_record(path: str) -> dict[str, Any]:
    raw = repository_bytes(path)
    return {
        "byte_size": len(raw),
        "digest_scope": "repository_canonical_lf_bytes",
        "path": path,
        "sha256": _sha256(raw),
    }


def _source_record(commit: str, path: str) -> dict[str, Any]:
    raw = _git_bytes(commit, path)
    return {
        "byte_size": len(raw),
        "path": path,
        "sha256": _sha256(raw),
        "source_commit": commit,
        "source_read_policy": "exact_git_commit_object",
    }


# --------------------------------------------------------------------------
# Section 1 - Person C canonical-media intake
# --------------------------------------------------------------------------
def verify_authorities() -> str:
    branch = _git_text("branch", "--show-current")
    if branch != A_BRANCH:
        _fail("unexpected_branch", f"Person A branch is {branch!r}")
    if _completed(
        ["git", "merge-base", "--is-ancestor", A_STARTING_AUTHORITY, "HEAD"]
    ).returncode:
        _fail("authority_not_ancestor", A_STARTING_AUTHORITY)
    for commit, ref in ((C_COMMIT, C_REMOTE_REF), (B_COMMIT, B_REMOTE_REF)):
        if _completed(["git", "cat-file", "-e", f"{commit}^{{commit}}"]).returncode:
            _fail("missing_foreign_commit", commit)
        if _completed(["git", "merge-base", "--is-ancestor", commit, ref]).returncode:
            _fail("foreign_commit_not_remote", f"{commit} not reachable from {ref}")
    for commit, path, expected in (
        (C_COMMIT, C_MEDIA_MANIFEST_PATH, C_MEDIA_MANIFEST_SHA256),
        (C_COMMIT, C_TO_A_HANDOFF_PATH, C_TO_A_HANDOFF_SHA256),
        (C_COMMIT, C_TO_D_HANDOFF_PATH, C_TO_D_HANDOFF_SHA256),
        (C_COMMIT, C_CANONICALIZER_PATH, C_CANONICALIZER_SHA256),
        (
            C_ACCEPTED_MANIFEST_COMMIT,
            C_ACCEPTED_MANIFEST_PATH,
            C_ACCEPTED_MANIFEST_SHA256,
        ),
    ):
        observed = _sha256(_git_bytes(commit, path))
        if observed != expected:
            _fail("authority_hash_mismatch", f"{path}: {observed} != {expected}")
    return A_STARTING_AUTHORITY


def load_canonical_frame_index() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Load and fully validate Person C's canonical frame index."""

    manifest = json.loads(_git_bytes(C_COMMIT, C_MEDIA_MANIFEST_PATH))
    handoff = json.loads(_git_bytes(C_COMMIT, C_TO_A_HANDOFF_PATH))
    raw = _git_bytes(C_COMMIT, C_FRAME_INDEX_PATH)
    declared = manifest["canonical_media"]["frame_index_sha256"]
    if _sha256(raw) != declared:
        _fail("frame_index_hash_mismatch", _sha256(raw))
    rows = [json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()]
    if len(rows) != EXPECTED_FRAME_COUNT:
        _fail("frame_index_cardinality", str(len(rows)))

    keys = [(row["trajectory_id"], row["model_frame_idx"]) for row in rows]
    if len(set(keys)) != len(keys):
        _fail("duplicate_canonical_key", "canonical frame index has duplicate keys")
    if len({row["trajectory_id"] for row in rows}) != EXPECTED_TRAJECTORY_COUNT:
        _fail("trajectory_cardinality", "canonical index is not 66 trajectories")

    for row in rows:
        if (row["canonical_width"], row["canonical_height"]) != (640, 360):
            _fail("canonical_dimensions", f"{row['canonical_path']}")
        if row["canonicalization_implementation_sha256"] != C_CANONICALIZER_SHA256:
            _fail("canonicalizer_drift", row["canonical_path"])
        if row["canonical_pixel_sha256"] != row["person_e_canonical_frame_rgb_sha256"]:
            _fail("person_e_pixel_disagreement", row["canonical_path"])
        if row["person_e_pixel_hash_agrees"] is not True:
            _fail("person_e_agreement_flag", row["canonical_path"])

    # The canonical key set must be exactly Person A's own production universe.
    a_index = json.loads(
        repository_bytes(f"{A_FRAME_MAP_PACKAGE_REL}/frame_map_index.json")
    )
    a_keys: set[tuple[str, int]] = set()
    a_source: dict[tuple[str, int], str] = {}
    for trajectory_id in a_index["per_trajectory"]:
        payload = (
            ROOT / A_FRAME_MAP_PACKAGE_REL / "frame_maps" / f"{trajectory_id}.jsonl"
        ).read_bytes()
        for line in payload.decode("utf-8").splitlines():
            if not line.strip():
                continue
            frame = json.loads(line)
            key = (frame["trajectory_id"], frame["model_frame_idx"])
            a_keys.add(key)
            a_source[key] = frame["source_frame_sha256"]
    if a_keys != set(keys):
        _fail("key_universe_mismatch", "canonical index does not equal A's universe")
    for row in rows:
        key = (row["trajectory_id"], row["model_frame_idx"])
        if row["raw_source_sha256"] != a_source[key]:
            _fail("raw_source_disagreement", row["canonical_path"])

    return rows, {
        "canonical_media_manifest": manifest,
        "c_to_a_handoff": handoff,
        "frame_index_sha256": declared,
    }


# --------------------------------------------------------------------------
# Section 2 - RGB/BGR boundary proof
# --------------------------------------------------------------------------
def rgb_bgr_boundary_proof(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Prove the C RGB -> cv2.imread BGR -> A BGR2RGB composition on real pixels."""

    import cv2
    import numpy as np
    from PIL import Image

    from mineocclude.models import _mineworld_adapter_wave2 as adapter

    row = rows[0]
    path = Path(row["canonical_path"])
    if not path.is_file():
        _fail("canonical_frame_absent", str(path))
    png_bytes = path.read_bytes()
    if _sha256(png_bytes) != row["canonical_png_sha256"]:
        _fail("canonical_png_hash_mismatch", str(path))

    true_rgb = np.asarray(Image.open(path).convert("RGB"))
    pixel_sha = _sha256(np.ascontiguousarray(true_rgb).tobytes(order="C"))
    if pixel_sha != row["canonical_pixel_sha256"]:
        _fail("canonical_pixel_hash_mismatch", str(path))

    loaded = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if loaded is None:
        _fail("cv2_decode_failed", str(path))
    channel_reversed = bool(np.array_equal(loaded, true_rgb[:, :, ::-1]))
    restored = cv2.cvtColor(loaded, cv2.COLOR_BGR2RGB)
    composes_to_identity = bool(np.array_equal(restored, true_rgb))

    source = adapter.__file__
    implementation = Path(source).read_text(encoding="utf-8")
    applies_bgr2rgb = "cv2.COLOR_BGR2RGB" in implementation
    applies_inter_linear = "cv2.INTER_LINEAR" in implementation

    if not (channel_reversed and composes_to_identity):
        _fail(
            "rgb_bgr_boundary_broken",
            "cv2.imread + COLOR_BGR2RGB did not restore Person C's true RGB",
        )
    if not applies_bgr2rgb:
        _fail("implementation_missing_bgr2rgb", A_IMPLEMENTATION_PATH)

    return {
        "composition": [
            "Person C writes a lossless PNG whose pixels are true RGB",
            "Person A loads it with cv2.imread, which returns the channels reversed",
            "Person A applies cv2.COLOR_BGR2RGB inside _preprocess_bgr_frame",
            "the two reversals compose to the identity, restoring true RGB",
        ],
        "cv2_array_is_channel_reversed_true_rgb": channel_reversed,
        "cv2_version": cv2.__version__,
        "implementation_applies_bgr2rgb": applies_bgr2rgb,
        "implementation_applies_inter_linear": applies_inter_linear,
        "implementation_path": A_IMPLEMENTATION_PATH,
        "implementation_sha256": _local_record(A_IMPLEMENTATION_PATH)["sha256"],
        "person_c_declares_rgb_output": True,
        "pinned_source_shape_hwc": [
            adapter.PINNED_SOURCE_HEIGHT,
            adapter.PINNED_SOURCE_WIDTH,
            3,
        ],
        "pre_swap_applied": False,
        "pre_swap_would_double_swap": True,
        "probe_canonical_path": str(path),
        "probe_canonical_pixel_sha256": pixel_sha,
        "probe_canonical_png_sha256": row["canonical_png_sha256"],
        "probe_key": {
            "model_frame_idx": row["model_frame_idx"],
            "trajectory_id": row["trajectory_id"],
        },
        "restores_true_rgb": composes_to_identity,
        "schema_id": f"{SCHEMA_PREFIX}-rgb-bgr-boundary-proof",
        "schema_version": SCHEMA_VERSION,
        "verified_on_real_canonical_pixels": True,
        "verified_via": "array equality on a decoded canonical frame",
    }


# --------------------------------------------------------------------------
# Environment provenance
# --------------------------------------------------------------------------
def environment_provenance() -> dict[str, Any]:
    import cv2
    import numpy
    import PIL

    return {
        "cross_library_version_byte_determinism_claimed": False,
        "determinism_scope": (
            "byte-identical model-facing payloads under this exact pinned "
            "interpreter and library set on this host; no claim is made across "
            "different OpenCV, NumPy, or Pillow versions"
        ),
        "machine": platform.machine(),
        "opencv_version": cv2.__version__,
        "pillow_version": PIL.__version__,
        "pillow_role": (
            "Person C's canonicalizer uses Pillow; Person A's model-facing step "
            "uses OpenCV only. Pillow is read here solely to recompute Person "
            "C's declared RGB pixel digest."
        ),
        "numpy_version": numpy.__version__,
        "platform": platform.platform(),
        "python_executable": sys.executable,
        "python_implementation": platform.python_implementation(),
        "python_version": platform.python_version(),
        "system": platform.system(),
    }


# --------------------------------------------------------------------------
# Section 3 - materialize the model-facing payloads
# --------------------------------------------------------------------------
def _b_bindings() -> tuple[dict[tuple[str, int], dict[str, Any]], dict[str, str]]:
    fold = json.loads(_git_bytes(B_COMMIT, B_FOLD_MANIFEST_PATH))
    folds = {
        (row["trajectory_id"], row["model_frame_idx"]): {
            "admission_stratum": row["admission_stratum"],
            "exclusion_reason": row["exclusion_reason"],
            "fold_idx": row["fold_idx"],
            "layout_id": row["layout_id"],
            "status": row["status"],
        }
        for row in fold["memberships"]
    }
    raw = _git_bytes(B_COMMIT, f"{B_ROOT}/oracle_target_records.jsonl")
    targets = {}
    for line in raw.decode("utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        targets[(record["trajectory_id"], record["model_frame_idx"])] = record[
            "target_id"
        ]
    return folds, targets


def materialize_frames(
    rows: list[dict[str, Any]], *, write_payloads: bool = True
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Apply Person A's frozen preprocessing to every canonical frame."""

    import cv2
    import numpy as np

    from mineocclude.models._mineworld_adapter_wave2 import _preprocess_bgr_frame

    folds, targets = _b_bindings()
    preprocess_hash = _preprocess_hash()
    implementation_sha256 = _local_record(A_IMPLEMENTATION_PATH)["sha256"]

    records: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    total_bytes = 0
    for row in rows:
        trajectory_id = str(row["trajectory_id"])
        model_frame_idx = int(row["model_frame_idx"])
        key = (trajectory_id, model_frame_idx)
        source = Path(row["canonical_path"])
        if not source.is_file():
            failures.append({"key": f"{key}", "reason": "canonical_frame_absent"})
            continue
        png_bytes = source.read_bytes()
        if _sha256(png_bytes) != row["canonical_png_sha256"]:
            failures.append({"key": f"{key}", "reason": "canonical_png_hash_mismatch"})
            continue
        loaded = cv2.imread(str(source), cv2.IMREAD_COLOR)
        if loaded is None:
            failures.append({"key": f"{key}", "reason": "cv2_decode_failed"})
            continue
        # cv2 returns BGR; reversing it recovers the true RGB Person C declared.
        pixel_sha = _sha256(
            np.ascontiguousarray(loaded[:, :, ::-1]).tobytes(order="C")
        )
        if pixel_sha != row["canonical_pixel_sha256"]:
            failures.append({"key": f"{key}", "reason": "canonical_pixel_hash_mismatch"})
            continue

        tensor, meta = _preprocess_bgr_frame(loaded)
        if tuple(meta["output_shape"]) != MODEL_FACING_SHAPE_CHW:
            failures.append({"key": f"{key}", "reason": "unexpected_output_shape"})
            continue
        payload = np.ascontiguousarray(tensor).tobytes(order="C")
        if len(payload) != MODEL_FACING_PAYLOAD_BYTES:
            failures.append({"key": f"{key}", "reason": "unexpected_payload_size"})
            continue
        payload_sha = _sha256(payload)
        relative = f"frames/{trajectory_id}/{model_frame_idx:06d}.f32le"
        if write_payloads:
            destination = PAYLOAD_ROOT / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(payload)
        total_bytes += len(payload)

        binding = folds.get(key)
        if binding is None:
            failures.append({"key": f"{key}", "reason": "missing_person_b_fold_binding"})
            continue
        records.append(
            {
                "artifact_id": (
                    f"person-a-66-cell-preprocessed-frame-v0-2::{trajectory_id}::"
                    f"{model_frame_idx}"
                ),
                "canonicalization_implementation_sha256": C_CANONICALIZER_SHA256,
                "canonicalization_rule": row["canonicalization_rule"],
                "colour_conversion": "cv2.COLOR_BGR2RGB",
                "dtype": MODEL_FACING_DTYPE,
                "episode_id": int(row["episode_id"]),
                "fold_binding": binding,
                "global_frame_identity": f"{trajectory_id}:{model_frame_idx}",
                "interpolation": "cv2.INTER_LINEAR",
                "layout_id": binding["layout_id"],
                "model_facing_height": MODEL_FACING_SHAPE_CHW[1],
                "model_facing_width": MODEL_FACING_SHAPE_CHW[2],
                "model_frame_idx": model_frame_idx,
                "normalization": "(x - 0.5) / 0.5 per channel",
                "output_path": relative,
                "payload_byte_size": len(payload),
                "payload_format": PAYLOAD_FORMAT,
                "payload_sha256": payload_sha,
                "preprocess_hash": preprocess_hash,
                "preprocessing_identity": TRANSFORMATION_IDENTITY,
                "preprocessing_implementation_path": A_IMPLEMENTATION_PATH,
                "preprocessing_implementation_sha256": implementation_sha256,
                "render_frame_idx": int(row["render_frame_idx"]),
                "scaling": "uint8 / float32(255.0)",
                "server_tick": int(row["server_tick"]),
                "shape": list(MODEL_FACING_SHAPE_CHW),
                "source_canonical_height": int(row["canonical_height"]),
                "source_canonical_path": row["canonical_path"],
                "source_canonical_pixel_sha256": row["canonical_pixel_sha256"],
                "source_canonical_png_byte_size": len(png_bytes),
                "source_canonical_png_sha256": row["canonical_png_sha256"],
                "source_canonical_width": int(row["canonical_width"]),
                "source_channel_order": "RGB",
                "source_raw_sha256": row["raw_source_sha256"],
                "target_binding": {"target_id": targets.get(key)},
                "trajectory_id": trajectory_id,
                "transformation_identity": TRANSFORMATION_IDENTITY,
            }
        )

    if failures:
        _fail("preprocessing_failures", json.dumps(failures[:10]))
    records.sort(key=lambda record: (record["trajectory_id"], record["model_frame_idx"]))
    summary = {
        "duplicate_count": len(records)
        - len({(r["trajectory_id"], r["model_frame_idx"]) for r in records}),
        "failure_count": len(failures),
        "input_key_count": len(rows),
        "output_key_count": len(records),
        "payload_byte_total": total_bytes,
    }
    return records, summary


def _preprocess_hash() -> str:
    from mineocclude.experiments.mvp_config import load_mvp_config

    return load_mvp_config(ROOT / A_CONFIG_PATH).identity()["preprocess_hash"]


def preprocessed_frame_manifest(
    records: list[dict[str, Any]],
    summary: dict[str, Any],
    provenance: dict[str, Any],
) -> dict[str, Any]:
    keys = {(r["trajectory_id"], r["model_frame_idx"]) for r in records}
    per_trajectory: dict[str, int] = {}
    for record in records:
        per_trajectory[record["trajectory_id"]] = (
            per_trajectory.get(record["trajectory_id"], 0) + 1
        )
    return {
        "artifact_count": len(records),
        "artifact_id_rule": (
            "person-a-66-cell-preprocessed-frame-v0-2::{trajectory_id}::"
            "{model_frame_idx}"
        ),
        "duplicate_frame_count": summary["duplicate_count"],
        "environment_provenance": provenance,
        "external_payload_root": str(PAYLOAD_ROOT),
        "failure_count": summary["failure_count"],
        "filename_rule": "frames/{trajectory_id}/{model_frame_idx:06d}.f32le",
        "join_key": ["trajectory_id", "model_frame_idx"],
        "missing_frame_count": EXPECTED_FRAME_COUNT - len(keys),
        "mp4_used_as_pixel_source": False,
        "output_contract": {
            "byte_order": "little",
            "channels": 3,
            "color_order": "RGB",
            "dtype": MODEL_FACING_DTYPE,
            "height": MODEL_FACING_SHAPE_CHW[1],
            "layout": "CHW",
            "payload_byte_size": MODEL_FACING_PAYLOAD_BYTES,
            "payload_format": PAYLOAD_FORMAT,
            "shape": list(MODEL_FACING_SHAPE_CHW),
            "value_range_inclusive": [-1.0, 1.0],
            "width": MODEL_FACING_SHAPE_CHW[2],
        },
        "payload_byte_total": summary["payload_byte_total"],
        "payloads_committed_to_git": False,
        "per_trajectory_frame_counts": dict(sorted(per_trajectory.items())),
        "person_a_preprocessing": {
            "colour_conversion": "cv2.COLOR_BGR2RGB",
            "implementation_path": A_IMPLEMENTATION_PATH,
            "implementation_sha256": _local_record(A_IMPLEMENTATION_PATH)["sha256"],
            "interpolation": "cv2.INTER_LINEAR",
            "normalization": "(x - 0.5) / 0.5 per channel",
            "preprocess_hash": _preprocess_hash(),
            "preprocessing_identity": TRANSFORMATION_IDENTITY,
            "scaling": "uint8 / float32(255.0)",
            "source_shape_hwc": [360, 640, 3],
        },
        "person_c_canonical_media": {
            "canonical_dimensions": CANONICAL_DIMENSIONS,
            "canonicalizer_path": C_CANONICALIZER_PATH,
            "canonicalizer_sha256": C_CANONICALIZER_SHA256,
            "commit": C_COMMIT,
            "frame_index_path": C_FRAME_INDEX_PATH,
            "manifest_path": C_MEDIA_MANIFEST_PATH,
            "manifest_sha256": C_MEDIA_MANIFEST_SHA256,
            "source_channel_order": "RGB",
        },
        "records": records,
        "schema_id": FRAME_MANIFEST_SCHEMA_ID,
        "schema_version": SCHEMA_VERSION,
        "trajectory_count": len(per_trajectory),
        "unique_frame_count": len(keys),
    }


# --------------------------------------------------------------------------
# Section 4 - deterministic regeneration
# --------------------------------------------------------------------------
def verify_determinism(
    rows: list[dict[str, Any]], manifest: dict[str, Any]
) -> dict[str, Any]:
    """Re-derive every payload from source and compare to manifest and disk."""

    regenerated, summary = materialize_frames(rows, write_payloads=False)
    declared = {
        (r["trajectory_id"], r["model_frame_idx"]): r for r in manifest["records"]
    }
    manifest_mismatches: list[str] = []
    disk_mismatches: list[str] = []
    missing_payloads: list[str] = []
    for record in regenerated:
        key = (record["trajectory_id"], record["model_frame_idx"])
        expected = declared.get(key)
        if expected is None or expected["payload_sha256"] != record["payload_sha256"]:
            manifest_mismatches.append(f"{key}")
            continue
        payload_path = PAYLOAD_ROOT / record["output_path"]
        if not payload_path.is_file():
            missing_payloads.append(f"{key}")
            continue
        payload = payload_path.read_bytes()
        if (
            _sha256(payload) != record["payload_sha256"]
            or len(payload) != record["payload_byte_size"]
        ):
            disk_mismatches.append(f"{key}")
    mismatch_count = (
        len(manifest_mismatches) + len(disk_mismatches) + len(missing_payloads)
    )
    return {
        "compared_output_count": len(regenerated),
        "cross_library_version_determinism_claimed": False,
        "disk_payload_mismatch_count": len(disk_mismatches),
        "disk_payload_mismatches": sorted(disk_mismatches)[:20],
        "environment_provenance": manifest["environment_provenance"],
        "independent_regeneration_performed": True,
        "manifest_hash_mismatch_count": len(manifest_mismatches),
        "manifest_hash_mismatches": sorted(manifest_mismatches)[:20],
        "missing_payload_count": len(missing_payloads),
        "mismatch_count": mismatch_count,
        "pass": mismatch_count == 0
        and summary["output_key_count"] == EXPECTED_FRAME_COUNT,
        "regenerated_key_count": summary["output_key_count"],
        "schema_id": f"{SCHEMA_PREFIX}-determinism-receipt",
        "schema_version": SCHEMA_VERSION,
    }


# --------------------------------------------------------------------------
# Section 5 - successor extraction config bound to canonical media
# --------------------------------------------------------------------------
def _successor_code_identity() -> dict[str, Any]:
    files = {
        path: _sha256(repository_bytes(path))
        for path in sorted(SUCCESSOR_CODE_IDENTITY_FILES)
    }
    return {
        "code_identity_sha256": _canonical_sha256(files),
        "digest_scope": "repository_canonical_lf_bytes",
        "files": files,
    }


def prior_successor_binding_audit(frame_manifest_sha256: str) -> dict[str, Any]:
    prior = json.loads(repository_bytes(A_PRIOR_SUCCESSOR_CONFIG_PATH))
    serialized = json.dumps(prior)
    binds_media = C_MEDIA_MANIFEST_SHA256 in serialized
    binds_handoff = C_TO_A_HANDOFF_SHA256 in serialized
    binds_frames = frame_manifest_sha256 in serialized
    return {
        "binds_c_canonical_media_sha256": binds_media,
        "binds_c_to_a_media_handoff_sha256": binds_handoff,
        "binds_person_a_preprocessed_frame_manifest_sha256": binds_frames,
        "conclusion": (
            "The prior successor predates Person C's canonical-media package and "
            "binds none of the three source-byte authorities, so the scientific "
            "input-byte authority moved from unbound to bound and a new run "
            "identity is required."
        ),
        "mutated_in_place": False,
        "new_run_identity_required": not (binds_media and binds_handoff and binds_frames),
        "prior_path": A_PRIOR_SUCCESSOR_CONFIG_PATH,
        "prior_run_id": prior["successor_run_identity"]["run_id"],
        "prior_sha256": _local_record(A_PRIOR_SUCCESSOR_CONFIG_PATH)["sha256"],
    }


def successor_extraction_config(
    frame_manifest_sha256: str, audit: dict[str, Any]
) -> dict[str, Any]:
    code_identity = _successor_code_identity()
    prior = json.loads(repository_bytes(A_PRIOR_SUCCESSOR_CONFIG_PATH))
    document: dict[str, Any] = {
        "additive_successor": True,
        "analysis_arithmetic_dtype": ANALYSIS_ARITHMETIC_DTYPE,
        "config_id": "person-a-66-cell-successor-canonical-media-v0.2",
        "config_version": "0.2",
        "decision_date": DECISION_DATE,
        "expected_activation_chunk_count": EXPECTED_CHUNK_COUNT,
        "expected_activation_row_count": EXPECTED_ACTIVATION_ROW_COUNT,
        "expected_model_frame_key_count": EXPECTED_FRAME_COUNT,
        "expected_trajectory_count": EXPECTED_TRAJECTORY_COUNT,
        "extraction": dict(prior["extraction"]),
        "frame_token_map": dict(prior["frame_token_map"]),
        "historical_evidence_rewritten": False,
        "inputs": {
            "person_a_frame_map_package_path": A_FRAME_MAP_PACKAGE_REL,
            "person_a_frame_map_package_sha256": prior["inputs"][
                "person_a_frame_map_package_sha256"
            ],
            "person_a_preprocessed_frame_manifest_path": (
                f"{STATUS_ROOT_REL}/preprocessed_frame_manifest.json"
            ),
            "person_a_preprocessed_frame_manifest_sha256": frame_manifest_sha256,
            "person_b_fold_manifest_path": prior["inputs"][
                "person_b_fold_manifest_path"
            ],
            "person_b_fold_manifest_sha256": prior["inputs"][
                "person_b_fold_manifest_sha256"
            ],
            "person_b_oracle_target_manifest_path": prior["inputs"][
                "person_b_oracle_target_manifest_path"
            ],
            "person_b_oracle_target_manifest_sha256": prior["inputs"][
                "person_b_oracle_target_manifest_sha256"
            ],
            "person_b_row_universe_path": prior["inputs"]["person_b_row_universe_path"],
            "person_b_row_universe_sha256": prior["inputs"][
                "person_b_row_universe_sha256"
            ],
            "person_b_source_commit": B_COMMIT,
            "person_c_accepted_manifest_commit": C_ACCEPTED_MANIFEST_COMMIT,
            "person_c_accepted_manifest_path": C_ACCEPTED_MANIFEST_PATH,
            "person_c_accepted_manifest_sha256": C_ACCEPTED_MANIFEST_SHA256,
            "person_c_canonical_media_commit": C_COMMIT,
            "person_c_canonical_media_manifest_path": C_MEDIA_MANIFEST_PATH,
            "person_c_canonical_media_manifest_sha256": C_MEDIA_MANIFEST_SHA256,
            "person_c_canonicalizer_path": C_CANONICALIZER_PATH,
            "person_c_canonicalizer_sha256": C_CANONICALIZER_SHA256,
            "person_c_event_table_sha256": prior["inputs"][
                "person_c_event_table_sha256"
            ],
            "person_c_strict_visibility_commit": C_STRICT_VISIBILITY_COMMIT,
            "person_c_to_a_media_handoff_path": C_TO_A_HANDOFF_PATH,
            "person_c_to_a_media_handoff_sha256": C_TO_A_HANDOFF_SHA256,
            "person_c_visibility_join_sha256": prior["inputs"][
                "person_c_visibility_join_sha256"
            ],
        },
        "model": dict(prior["model"]),
        "person_a_mvp_yaml_modified": False,
        "predecessor": {
            "path": A_PRIOR_SUCCESSOR_CONFIG_PATH,
            "predecessor_evidence_rewritten": False,
            "predecessor_run_id": audit["prior_run_id"],
            "reason": (
                "The predecessor successor config was built before Person C's "
                "canonical-media package existed and binds no canonical source "
                "byte authority. It is superseded additively, never edited."
            ),
            "sha256": audit["prior_sha256"],
        },
        "preprocessing": dict(prior["preprocessing"]),
        "producer_role": "person_a",
        "schema_id": f"{SCHEMA_PREFIX}-successor-extraction-config",
        "schema_version": SCHEMA_VERSION,
        "scientific_pixel_source": {
            "canonical_dimensions": CANONICAL_DIMENSIONS,
            "channel_order": "RGB",
            "container": "PNG 8-bit lossless",
            "mp4_is_convenience_media_only": True,
            "mp4_used_as_pixel_source": False,
            "pixel_authority_field": "canonical_pixel_sha256",
        },
        "seed": EXTRACTION_SEED,
        "successor_code_identity": code_identity,
    }
    hashable = {k: v for k, v in document.items() if k != "successor_run_identity"}
    config_hash = _canonical_sha256(hashable)
    run_id = make_run_id(
        stage_id="model_extraction",
        config_hash=config_hash,
        code_sha=code_identity["code_identity_sha256"],
        seed=EXTRACTION_SEED,
    )
    if run_id == A_PRIOR_RUN_ID:
        _fail("run_identity_unchanged", run_id)
    document["successor_run_identity"] = {
        "accepted_manifest_sha256": C_ACCEPTED_MANIFEST_SHA256,
        "code_sha": code_identity["code_identity_sha256"],
        "config_hash": config_hash,
        "run_id": run_id,
        "stage_id": "model_extraction",
        "superseded_run_id": A_PRIOR_RUN_ID,
    }
    return document


def build_successor_queue(config: dict[str, Any]) -> ExtractionQueue:
    matrix = json.loads(repository_bytes(A_MATRIX_REPORT_PATH))
    index = json.loads(
        repository_bytes(f"{A_FRAME_MAP_PACKAGE_REL}/frame_map_index.json")
    )
    frame_counts = {
        trajectory_id: int(entry["model_frame_count"])
        for trajectory_id, entry in index["per_trajectory"].items()
    }
    identity = config["successor_run_identity"]
    queue = build_queue_from_matrix(
        matrix,
        run_id=identity["run_id"],
        config_hash=identity["config_hash"],
        code_sha=identity["code_sha"],
        accepted_manifest_sha256=identity["accepted_manifest_sha256"],
        layer_count=LAYER_COUNT,
        frame_counts=frame_counts,
        max_transient_retries=3,
    )
    if len(queue.items) != EXPECTED_TRAJECTORY_COUNT:
        _fail("queue_cardinality", str(len(queue.items)))
    rows = sum(item.expected.expected_row_count for item in queue.items.values())
    if rows != EXPECTED_ACTIVATION_ROW_COUNT:
        _fail("queue_row_cardinality", str(rows))
    for item in queue.items.values():
        if item.completion is not None:
            _fail("queue_preseeded_completion", item.item_id)
    return queue


# --------------------------------------------------------------------------
# Sections 7, 9 - Person D handoff and byte transport
# --------------------------------------------------------------------------
def a_to_d_frame_handoff(
    manifest: dict[str, Any],
    manifest_sha256: str,
    boundary: dict[str, Any],
    determinism: dict[str, Any],
) -> dict[str, Any]:
    prior = _local_record(A_PRIOR_A_TO_D_PATH)
    ready = bool(
        determinism["pass"]
        and manifest["artifact_count"] == EXPECTED_FRAME_COUNT
        and manifest["duplicate_frame_count"] == 0
        and manifest["missing_frame_count"] == 0
        and manifest["failure_count"] == 0
    )
    return {
        "applicability": {
            "all_66_cells_applicable": True,
            "excluded_trajectory_count": 0,
            "trajectory_count": EXPECTED_TRAJECTORY_COUNT,
        },
        "blocking_findings": [],
        "channel_order_semantics": {
            "person_a_loader": "cv2.imread returns BGR",
            "person_a_restores_rgb_with": "cv2.COLOR_BGR2RGB",
            "person_c_canonical_png_channel_order": "RGB",
            "pre_swap_applied": False,
            "proof_path": f"{STATUS_ROOT_REL}/rgb_bgr_boundary_proof.json",
            "restores_true_rgb": boundary["restores_true_rgb"],
        },
        "consumer_role": "person_d",
        "decision_date": DECISION_DATE,
        "deterministic_producer_environment": manifest["environment_provenance"],
        "entry_point": {
            "person_a_regeneration_command": (
                f"python {BUILDER_PATH} materialize"
            ),
            "person_a_verification_command": (f"python {BUILDER_PATH} verify"),
            "person_d_production_command": (
                "python scripts/run_person_d_step4_1_eight_family_production.py "
                "--fold-manifest <B_66_CELL_FOLD_MANIFEST> --oracle-targets "
                "<B_66_CELL_ORACLE_TARGETS> --frame-manifest "
                f"{STATUS_ROOT_REL}/preprocessed_frame_manifest.json "
                "--output-root <PERSON_D_PRODUCTION_ROOT> --resume auto"
            ),
        },
        "person_a_preprocessed_frames": {
            "artifact_count": manifest["artifact_count"],
            "duplicate_frame_count": manifest["duplicate_frame_count"],
            "external_payload_root": manifest["external_payload_root"],
            "failure_count": manifest["failure_count"],
            "filename_rule": manifest["filename_rule"],
            "manifest_path": f"{STATUS_ROOT_REL}/preprocessed_frame_manifest.json",
            "manifest_schema_id": FRAME_MANIFEST_SCHEMA_ID,
            "manifest_sha256": manifest_sha256,
            "missing_frame_count": manifest["missing_frame_count"],
            "output_contract": manifest["output_contract"],
            "payload_byte_total": manifest["payload_byte_total"],
            "payload_hashes_are_in_the_manifest_records": True,
            "unique_frame_count": manifest["unique_frame_count"],
        },
        "person_a_preprocessing_authority": manifest["person_a_preprocessing"],
        "person_c_canonical_media": {
            "canonical_dimensions": CANONICAL_DIMENSIONS,
            "canonical_frame_count": EXPECTED_FRAME_COUNT,
            "canonicalizer_path": C_CANONICALIZER_PATH,
            "canonicalizer_sha256": C_CANONICALIZER_SHA256,
            "commit": C_COMMIT,
            "frame_index_path": C_FRAME_INDEX_PATH,
            "manifest_path": C_MEDIA_MANIFEST_PATH,
            "manifest_sha256": C_MEDIA_MANIFEST_SHA256,
            "mp4_used_as_pixel_source": False,
            "source_channel_order": "RGB",
        },
        "person_c_to_d_media_handoff": {
            "path": C_TO_D_HANDOFF_PATH,
            "sha256": C_TO_D_HANDOFF_SHA256,
        },
        "person_d_consumer_note": {
            "person_d_frozen_module": "src/mineocclude/baselines/frame_handoff_v0_2.py",
            "person_d_must_repin_constants": [
                "PERSON_A_FRAME_HANDOFF_COMMIT",
                "PERSON_A_FRAME_MANIFEST_PATH",
                "PERSON_A_FRAME_MANIFEST_SHA256",
                "PERSON_A_EXTERNAL_FRAME_ROOT",
                "REQUIRED_FRAME_ARTIFACT_COUNT",
                "FROZEN_PILOT_IDS",
            ],
            "person_d_owns_this_change": True,
            "requires_another_person_a_data_artifact": False,
            "note": (
                "Every Person A-owned data artifact Person D needs now exists: "
                "the 2468-record manifest, the payload hashes, and the payload "
                "bytes. Re-pinning Person D's own frozen constants to this "
                "manifest is a Person D code change, not a further Person A "
                "deliverable, and Person A does not modify Person D's branch."
            ),
        },
        "producer_role": "person_a",
        "ready": ready,
        "schema_id": f"{SCHEMA_PREFIX}-a-to-d-frame-handoff",
        "schema_version": SCHEMA_VERSION,
        "source_and_output_dimensions": {
            "model_facing_shape_chw": list(MODEL_FACING_SHAPE_CHW),
            "model_facing_width_by_height": "384x224",
            "raw_capture_dimensions": "1920x1046",
            "scientific_source_dimensions": CANONICAL_DIMENSIONS,
        },
        "supersedes": {
            "path": A_PRIOR_A_TO_D_PATH,
            "predecessor_evidence_rewritten": False,
            "predecessor_ready": False,
            "predecessor_sha256": prior["sha256"],
            "reason": (
                "The predecessor handoff was published not-ready on the missing "
                "640x360 media finding. Person C has since materialized that "
                "media, so this successor closes the handoff additively."
            ),
        },
    }


def byte_transport_plan(manifest: dict[str, Any]) -> dict[str, Any]:
    host = json.loads(repository_bytes(A_EXECUTION_HOST_CONTRACT_PATH))
    destination_pattern = "s3://[A-Za-z0-9]"
    found: list[str] = []
    results = []
    for ref in (B_REMOTE_REF, C_REMOTE_REF, D_REMOTE_REF, E_REMOTE_REF, "HEAD"):
        result = _completed(
            [
                "git",
                "grep",
                "-lIE",
                destination_pattern,
                ref,
                "--",
                "docs",
                "configs",
                "scripts",
            ]
        )
        hits = [
            line
            for line in result.stdout.decode("utf-8", errors="replace").splitlines()
            if line.strip()
        ]
        results.append({"hits": hits, "ref": ref})
        found.extend(hits)
    canonical_bytes = sum(
        record["source_canonical_png_byte_size"]
        for record in manifest["records"]
        if "source_canonical_png_byte_size" in record
    )
    return {
        "approved_durable_destination": None,
        "byte_transport_destination_pending": True,
        "destination_fabricated": False,
        "execution_environment": host["execution_boundary"][
            "allowed_production_environment"
        ],
        "extraction_host_requirement": {
            "chosen": "person_a_model_facing_payloads",
            "detail": (
                "The frozen extraction path consumes the model-facing CHW "
                "float32 tensor. Person A has already materialized those exact "
                "payloads with hashes, so the extraction host needs Person A's "
                "payloads rather than re-running preprocessing on the canonical "
                "PNGs. The canonical PNGs remain the upstream pixel authority "
                "and are listed so the host can re-derive if an owner requires "
                "it."
            ),
            "option_a_canonical_pngs_and_preprocess_on_host": False,
            "option_b_person_a_model_facing_payloads": True,
        },
        "local_sources": {
            "canonical_png_byte_total": canonical_bytes or None,
            "canonical_png_file_count": EXPECTED_FRAME_COUNT,
            "canonical_png_root": (
                "C:\\Users\\lollo\\MineOcclude-Runtime\\person-c-c1-v0_1\\client"
                "\\mineocclude_client_out\\episode_<episode_id>\\frames_640x360"
            ),
            "canonical_png_sha_inventory": C_FRAME_INDEX_PATH,
            "model_facing_payload_byte_total": manifest["payload_byte_total"],
            "model_facing_payload_file_count": manifest["artifact_count"],
            "model_facing_payload_root": manifest["external_payload_root"],
            "model_facing_sha_inventory": (
                f"{STATUS_ROOT_REL}/preprocessed_frame_manifest.json"
            ),
        },
        "reinspection": {
            "bare_scheme_token_is_not_a_destination": True,
            "destination_pattern": destination_pattern,
            "object_store_destination_found": bool(found),
            "results": results,
        },
        "sagemaker_byte_access_ready": False,
        "schema_id": f"{SCHEMA_PREFIX}-byte-transport-plan",
        "schema_version": SCHEMA_VERSION,
        "transfer_procedure": {
            "steps": [
                (
                    "1. an owner assigns <APPROVED_DESTINATION_URI> and records "
                    "it in docs/status/person_a_phase9_clean_run_v0_1/"
                    "external_artifact_index.json"
                ),
                (
                    f"2. python {BUILDER_PATH} verify  # re-derive and re-verify "
                    "all 2468 model-facing payloads before upload"
                ),
                (
                    "3. upload every payload under the external payload root to "
                    "<APPROVED_DESTINATION_URI>/person-a-66-cell-preprocessed-"
                    "frames-v0-2/frames/<trajectory_id>/<model_frame_idx>.f32le"
                ),
                (
                    "4. recompute SHA-256 for every uploaded object and require "
                    "an exact match against the manifest payload_sha256 values"
                ),
                (
                    "5. materialize on aws_sagemaker_linux_gpu and re-verify "
                    "every digest and byte size before Step 6.1"
                ),
            ],
            "unfilled_placeholders": ["<APPROVED_DESTINATION_URI>"],
            "verification_command": (
                f"python {BUILDER_PATH} verify"
            ),
        },
    }


def phase6_precondition_receipt(
    handoff: dict[str, Any], transport: dict[str, Any], determinism: dict[str, Any]
) -> dict[str, Any]:
    contract_conditions = [
        {
            "condition": "person_c_accepted_66_cell_manifest_bound",
            "owner": "person_c_data",
            "satisfied": True,
        },
        {
            "condition": "person_c_strict_visibility_authority_bound",
            "owner": "person_c_data",
            "satisfied": True,
        },
        {
            "condition": "model_input_source_media_at_frozen_source_resolution",
            "detail": (
                "Resolved: Person C materialized the declared canonical 640x360 "
                "lossless RGB PNGs for all 2468 keys and their pixel digests "
                "reproduce Person E's recorded canonical frame hashes."
            ),
            "owner": "person_c_data",
            "satisfied": True,
        },
        {
            "condition": "person_a_2468_model_facing_payloads_materialized",
            "owner": "person_a_model",
            "satisfied": determinism["pass"],
        },
        {
            "condition": "person_b_fold_and_oracle_target_authorities_bound",
            "owner": "person_b_analysis",
            "satisfied": True,
        },
        {
            "condition": "person_b_row_universe_bound",
            "owner": "person_b_analysis",
            "satisfied": True,
        },
        {
            "condition": "storage_dtype_review_complete_float32",
            "owner": "person_a_model+person_b_analysis",
            "satisfied": True,
        },
        {
            "condition": "successor_run_identity_binds_canonical_source_bytes",
            "owner": "person_a_model",
            "satisfied": True,
        },
        {
            "condition": "person_d_66_cell_frame_preprocess_handoff_consumable",
            "owner": "person_a_model",
            "satisfied": handoff["ready"],
        },
    ]
    infrastructure_conditions = [
        {
            "condition": "durable_byte_transport_to_approved_gpu_environment",
            "owner": "person_c_data+person_e_operations",
            "satisfied": False,
        },
        {
            "condition": "canonical_and_model_facing_bytes_reachable_from_sagemaker",
            "owner": "person_a_model",
            "satisfied": False,
        },
        {
            "condition": "approved_gpu_runtime_session",
            "owner": "person_a_model",
            "satisfied": False,
        },
        {
            "condition": "model_and_vae_checkpoint_accessible_on_extraction_host",
            "owner": "person_a_model",
            "satisfied": False,
        },
    ]
    return {
        "aggregate_authorization_authority_present": False,
        "aggregate_phase6_runtime_authorized": False,
        "assessed_roles": {
            "person_a": _git_text("rev-parse", "HEAD"),
            "person_b": _git_text("rev-parse", B_REMOTE_REF),
            "person_c": _git_text("rev-parse", C_REMOTE_REF),
            "person_d": _git_text("rev-parse", D_REMOTE_REF),
            "person_e": _git_text("rev-parse", E_REMOTE_REF),
        },
        "contract_conditions": contract_conditions,
        "infrastructure_conditions": infrastructure_conditions,
        "phase6_contract_preconditions_ready": all(
            entry["satisfied"] for entry in contract_conditions
        ),
        "phase6_runtime_infrastructure_ready": all(
            entry["satisfied"] for entry in infrastructure_conditions
        ),
        "resolved_since_previous_assessment": ["C-66-CELL-640x360-MEDIA-MISSING"],
        "schema_id": f"{SCHEMA_PREFIX}-phase6-precondition-receipt",
        "schema_version": SCHEMA_VERSION,
        "self_authorizes_phase6": False,
        "transport_state": {
            "byte_transport_destination_pending": transport[
                "byte_transport_destination_pending"
            ],
            "sagemaker_byte_access_ready": transport["sagemaker_byte_access_ready"],
        },
    }


# --------------------------------------------------------------------------
# Assembly
# --------------------------------------------------------------------------
def _protected_false_violations(value: Any, path: str) -> list[str]:
    violations: list[str] = []
    if isinstance(value, dict):
        for key in sorted(value):
            child = value[key]
            child_path = f"{path}.{key}"
            if key in PROTECTED_FALSE_FIELDS and child is not False:
                violations.append(f"{child_path} must be exact Boolean false")
            violations.extend(_protected_false_violations(child, child_path))
    elif isinstance(value, list):
        for offset, child in enumerate(value):
            violations.extend(_protected_false_violations(child, f"{path}[{offset}]"))
    return violations


def _authority_binding(a_commit: str, audit: dict[str, Any]) -> dict[str, Any]:
    return {
        "authorities": {
            "person_a": {"branch": A_BRANCH, "starting_commit": a_commit},
            "person_b": {
                "remote_ref": B_REMOTE_REF,
                "source_authority_commit": B_COMMIT,
                "source_read_policy": "exact_git_commit_object",
            },
            "person_c": {
                "remote_ref": C_REMOTE_REF,
                "source_authority_commit": C_COMMIT,
                "source_read_policy": "exact_git_commit_object",
            },
        },
        "builder_path": BUILDER_PATH,
        "claims": {
            "activations_generated": False,
            "aggregate_phase6_runtime_authorized": False,
            "foreign_branch_merged": False,
            "gpu_extraction_started": False,
            "historical_evidence_rewritten": False,
            "model_loaded": False,
            "mp4_used_as_pixel_source": False,
            "person_a_phase6_authorized": False,
            "scientific_execution_performed": False,
            "self_authorizes_phase6": False,
        },
        "person_c_source_records": [
            _source_record(C_COMMIT, C_MEDIA_MANIFEST_PATH),
            _source_record(C_COMMIT, C_TO_A_HANDOFF_PATH),
            _source_record(C_COMMIT, C_TO_D_HANDOFF_PATH),
            _source_record(C_COMMIT, C_FRAME_INDEX_PATH),
            _source_record(C_COMMIT, C_CANONICALIZER_PATH),
            _source_record(C_ACCEPTED_MANIFEST_COMMIT, C_ACCEPTED_MANIFEST_PATH),
        ],
        "person_b_source_records": [
            _source_record(B_COMMIT, B_FOLD_MANIFEST_PATH),
            _source_record(B_COMMIT, f"{B_ROOT}/oracle_target_manifest.json"),
            _source_record(B_COMMIT, f"{B_ROOT}/row_universe_receipt_v0_2.json"),
            _source_record(B_COMMIT, f"{B_ROOT}/b_to_a_successor_handoff.json"),
        ],
        "prior_successor_binding_audit": audit,
        "schema_id": f"{SCHEMA_PREFIX}-authority-binding",
        "schema_version": SCHEMA_VERSION,
        "test_path": TEST_PATH,
    }


def build_documents(*, materialize: bool = True) -> dict[str, Any]:
    a_commit = verify_authorities()
    rows, _sources = load_canonical_frame_index()
    boundary = rgb_bgr_boundary_proof(rows)
    provenance = environment_provenance()
    records, summary = materialize_frames(rows, write_payloads=materialize)
    if summary["output_key_count"] != EXPECTED_FRAME_COUNT:
        _fail("output_cardinality", str(summary["output_key_count"]))
    manifest = preprocessed_frame_manifest(records, summary, provenance)
    if manifest["duplicate_frame_count"] or manifest["missing_frame_count"]:
        _fail("frame_manifest_audit", "duplicate or missing model-facing frames")
    manifest_sha256 = _sha256(_json_bytes(manifest))
    determinism = verify_determinism(rows, manifest)
    if not determinism["pass"]:
        _fail("determinism_failed", json.dumps(determinism)[:400])

    audit = prior_successor_binding_audit(manifest_sha256)
    config = successor_extraction_config(manifest_sha256, audit)
    queue = build_successor_queue(config)
    handoff = a_to_d_frame_handoff(manifest, manifest_sha256, boundary, determinism)
    transport = byte_transport_plan(manifest)
    preconditions = phase6_precondition_receipt(handoff, transport, determinism)

    documents: dict[str, Any] = {
        "a_to_d_frame_handoff.json": handoff,
        "authority_binding.json": _authority_binding(a_commit, audit),
        "byte_transport_plan.json": transport,
        "phase6_precondition_receipt.json": preconditions,
        "preprocessed_frame_manifest.json": manifest,
        "rgb_bgr_boundary_proof.json": boundary,
        "successor_extraction_config.json": config,
        "successor_extraction_queue_state.json": queue.to_document(),
        "validation_receipt.json": {
            "aggregate_phase6_runtime_authorized": False,
            "canonical_frame_count": len(rows),
            "canonical_hash_verified_count": len(records),
            "determinism": determinism,
            "gpu_extraction_started": False,
            "model_loaded": False,
            "mp4_used_as_pixel_source": False,
            "preprocessed_duplicate_count": manifest["duplicate_frame_count"],
            "preprocessed_failure_count": manifest["failure_count"],
            "preprocessed_frame_count": manifest["artifact_count"],
            "preprocessed_missing_count": manifest["missing_frame_count"],
            "queue_expected_activation_row_count": EXPECTED_ACTIVATION_ROW_COUNT,
            "queue_trajectory_count": len(queue.items),
            "rgb_bgr_boundary_verified": boundary["restores_true_rgb"],
            "schema_id": f"{SCHEMA_PREFIX}-validation-receipt",
            "schema_version": SCHEMA_VERSION,
            "scientific_execution_performed": False,
            "successor_run_id": config["successor_run_identity"]["run_id"],
            "successor_run_id_changed": True,
        },
    }
    violations: list[str] = []
    for name, document in sorted(documents.items()):
        violations.extend(_protected_false_violations(document, name))
    if violations:
        _fail("protected_claim_violation", "; ".join(violations))
    documents["sha256_inventory.json"] = {
        "file_count": len(documents) + 1,
        "files": {
            name: _sha256(_json_bytes(document))
            for name, document in sorted(documents.items())
        },
        "inventory_excludes_self": True,
        "schema_id": f"{SCHEMA_PREFIX}-sha256-inventory",
        "schema_version": SCHEMA_VERSION,
    }
    if set(documents) != set(OUTPUT_PATHS):
        _fail("path_inventory_changed", str(sorted(documents)))
    return documents


def write_documents(output_root: Path, *, materialize: bool = True) -> dict[str, Any]:
    documents = build_documents(materialize=materialize)
    output_root.mkdir(parents=True, exist_ok=True)
    for name, document in sorted(documents.items()):
        (output_root / name).write_bytes(_json_bytes(document))
    return documents


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Materialize Person A's 66-cell model-facing frames."
    )
    parser.add_argument("stage", choices=("materialize", "verify"))
    parser.add_argument("--output-dir", type=Path, default=STATUS_ROOT)
    arguments = parser.parse_args()
    if arguments.stage == "verify":
        verify_authorities()
        rows, _sources = load_canonical_frame_index()
        manifest = json.loads(
            repository_bytes(f"{STATUS_ROOT_REL}/preprocessed_frame_manifest.json")
        )
        receipt = verify_determinism(rows, manifest)
        print(json.dumps({k: v for k, v in receipt.items() if k != "environment_provenance"}))
        if not receipt["pass"]:
            raise SystemExit(1)
        return
    documents = write_documents(arguments.output_dir.resolve())
    manifest = documents["preprocessed_frame_manifest.json"]
    config = documents["successor_extraction_config.json"]
    print(
        f"frames={manifest['artifact_count']} "
        f"bytes={manifest['payload_byte_total']} "
        f"run_id={config['successor_run_identity']['run_id']} "
        f"d_ready={documents['a_to_d_frame_handoff.json']['ready']}"
    )


if __name__ == "__main__":
    main()
