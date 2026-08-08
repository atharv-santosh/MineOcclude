#!/usr/bin/env python3
"""Production 66-trajectory activation extraction for the successor run
``mineocclude-run-ea6169430d693f8adcd16a23a62c4422``.

This is orchestration only. It reuses the existing adapter (teacher-forced
inference, action conversion, tokenization), hook (``ScopedHookManager``),
pooling (``extract_complete_pooled_context``), and storage (``store_v2``)
machinery unmodified. The only new logic here is:

* cloning the immutable queue seed from
  ``docs/status/person_a_66_cell_preprocessed_media_v0_2`` into an external
  production-runtime status package, then draining that runtime copy instead
  of mutating the committed authority or using a hardcoded pilot list;
* constructing ``PreprocessedFrame`` objects directly from the already
  materialized ``.f32le`` payloads (v0.2 preprocessing successor), instead of
  decoding video and calling ``adapter.preprocess_frame``;
* windowing each trajectory into <=16-frame contexts while preserving global
  frame identity, and resuming a partially published per-trajectory store.

Person C source streams (frame_map / server_state / raw_actions) are read as
exact Git blobs from the frozen canonical-media commit
``3846230a4f141a8a55084eeaaa040f9a10cfc408``, matching
``successor_extraction_config.json``'s ``person_c_canonical_media_commit``.
"""

from __future__ import annotations

import argparse
import dataclasses
import functools
import hashlib
import json
import platform
import subprocess
import sys
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402

from mineocclude.activations.store_v2 import (  # noqa: E402
    ACTIVATION_STORE_V2_FORMAT_VERSION,
    FROZEN_PHASE6_LAYERS,
    ActivationIndexSnapshotV2,
    ActivationStoreIdentityV2,
    build_source_frame_bindings_v2,
    candidate_row_from_frame_token_span_v2,
    load_activation_index_snapshot_v2,
    publish_activation_chunk_v2,
    validate_activation_index_snapshot_v2,
)
from mineocclude.activations import store as store_v1  # noqa: E402
from mineocclude.contracts.identity import SCHEMA_VERSION  # noqa: E402
from mineocclude.experiments.extraction_queue import (  # noqa: E402
    CompletionRecord,
    ExtractionQueue,
)
from mineocclude.models import mineworld_adapter as adapter_module  # noqa: E402
from mineocclude.models import _mineworld_adapter_wave2 as wave2  # noqa: E402
from mineocclude.models import _mineworld_adapter_wave4 as wave4  # noqa: E402
from mineocclude.models import _mineworld_adapter_wave5 as wave5  # noqa: E402
from mineocclude.activations import hooks as hooks_module  # noqa: E402

RUNNER_VERSION = "person-a-66-cell-production-extraction-runner-v1.0"

RUN_ID = "mineocclude-run-ea6169430d693f8adcd16a23a62c4422"
CONFIG_HASH = "8f6434d403f896439d4f3ff7b86410232a837606866a63e0ac9a81917874e399"
QUEUE_CODE_IDENTITY_SHA256 = (
    "03d0b06bdad97abbe9b78b919ab192cc0e921ee46ff12e62ae7d91216d6b8358"
)
ACCEPTED_MANIFEST_SHA256 = (
    "96ba43e15bc024aeaef7c519fa4ece0a4afe0bb0e877501dffaca44fee927ff7"
)
HOOK_SITE = "decoder_layer_output_residual_stream"
HIDDEN_WIDTH = 2048
REQUIRED_DEVICE = "cuda:0"
PRECISION = "float16"
SEED = 20260725
MODEL_CONFIG_RELATIVE_PATH = "configs/700M_16f.yaml"
C_CANONICAL_MEDIA_COMMIT = "3846230a4f141a8a55084eeaaa040f9a10cfc408"

REPO_ROOT = ROOT
MINEWORLD_ROOT = Path("/home/sagemaker-user/MineWorld-Upstream")
ASSET_ROOT = Path("/home/sagemaker-user/MineWorld-Assets-Pinned")
MAIN_CHECKPOINT = ASSET_ROOT / "checkpoints" / "700M_16f.ckpt"
VAE_CONFIG = ASSET_ROOT / "checkpoints" / "vae" / "config.json"
VAE_CHECKPOINT = ASSET_ROOT / "checkpoints" / "vae" / "vae.ckpt"

SEED_QUEUE_STATE_PATH = (
    REPO_ROOT
    / "docs/status/person_a_66_cell_preprocessed_media_v0_2"
    / "successor_extraction_queue_state.json"
)
SEED_QUEUE_STATE_SHA256 = (
    "3422655c6a627c6b55028f74c9aa3896aa624c32927e88d923dac05a63973309"
)
FRAME_MANIFEST_PATH = (
    REPO_ROOT
    / "docs/status/person_a_66_cell_preprocessed_media_v0_2"
    / "preprocessed_frame_manifest.json"
)
FRAME_PAYLOAD_ROOT = Path(
    "/mnt/sagemaker-nvme/mineocclude/phase6/"
    f"{RUN_ID}/input/person-a-66-cell-preprocessed-frames-v0-2/frames"
)
STORE_OUTPUT_ROOT = Path(
    f"/mnt/sagemaker-nvme/mineocclude/phase6/{RUN_ID}/output/activation-store-v2"
)
SESSION_LOG_ROOT = Path(
    f"/mnt/sagemaker-nvme/mineocclude/phase6/{RUN_ID}/runner-sessions"
)
RUNTIME_STATUS_ROOT = (
    STORE_OUTPUT_ROOT.parent / "status/person_a_66_cell_production_runtime_v0_1"
)
RUNTIME_QUEUE_STATE_PATH = RUNTIME_STATUS_ROOT / "extraction_queue_state.json"
QUEUE_STATE_PATH = RUNTIME_QUEUE_STATE_PATH


class ExtractionFailure(RuntimeError):
    """A classified extraction failure, mapped onto ExtractionQueue kinds."""

    def __init__(self, kind: str, message: str) -> None:
        self.kind = kind
        super().__init__(message)


def _run_git(*args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(REPO_ROOT), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _git_object_bytes(revspec: str) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "cat-file", "-p", revspec],
        check=True,
        capture_output=True,
    )
    return result.stdout


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


@functools.lru_cache(maxsize=1)
def _frame_manifest_index() -> dict[tuple[str, int], dict[str, Any]]:
    document = json.loads(FRAME_MANIFEST_PATH.read_text(encoding="utf-8"))
    index: dict[tuple[str, int], dict[str, Any]] = {}
    for record in document["records"]:
        index[(record["trajectory_id"], record["model_frame_idx"])] = record
    return index


def _capture_package_bytes(trajectory_id: str) -> bytes:
    return _git_object_bytes(
        f"{C_CANONICAL_MEDIA_COMMIT}:data/autonomous/{trajectory_id}/"
        "capture_package_v0_1.json"
    )


def _capture_package_declared_sha256(trajectory_id: str) -> str:
    raw = _git_object_bytes(
        f"{C_CANONICAL_MEDIA_COMMIT}:data/autonomous/{trajectory_id}/"
        "capture_package_v0_1.json.sha256"
    )
    return raw.decode("utf-8").strip()


def _c_stream_bytes(trajectory_id: str, name: str) -> bytes:
    return _git_object_bytes(
        f"{C_CANONICAL_MEDIA_COMMIT}:data/autonomous/{trajectory_id}/"
        f"package_v0_1/{name}.jsonl"
    )


def _jsonl_rows(payload: bytes) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in payload.decode("utf-8").splitlines()
        if line.strip()
    ]


def _load_preprocessed_frame(
    identity: Any,
    record: Mapping[str, Any],
    runtime_identity: Any,
) -> Any:
    if (
        record["preprocessing_identity"]
        != wave5.PERSON_A_66_CELL_V0_2_PREPROCESSING_PROFILE
    ):
        raise ExtractionFailure(
            "identity_failure",
            f"{identity}: manifest preprocessing_identity does not match v0.2",
        )
    payload_path = (
        FRAME_PAYLOAD_ROOT
        / record["trajectory_id"]
        / (f"{record['model_frame_idx']:06d}.f32le")
    )
    if not payload_path.is_file():
        raise ExtractionFailure(
            "io_failure", f"{identity}: missing payload {payload_path}"
        )
    payload = payload_path.read_bytes()
    if len(payload) != record["payload_byte_size"]:
        raise ExtractionFailure(
            "checksum_failure", f"{identity}: payload byte-size mismatch"
        )
    array = np.frombuffer(payload, dtype="<f4").reshape(3, 224, 384).copy()
    content_sha256 = hashlib.sha256(array.tobytes(order="C")).hexdigest()
    if content_sha256 != record["payload_sha256"]:
        raise ExtractionFailure(
            "checksum_failure", f"{identity}: payload sha256 mismatch"
        )
    return adapter_module.PreprocessedFrame(
        identity=identity,
        source_frame_idx=record["render_frame_idx"],
        shape=(3, 224, 384),
        dtype="float32",
        color_order="RGB",
        content_sha256=content_sha256,
        frame=array,
        preprocessing_profile=wave5.PERSON_A_66_CELL_V0_2_PREPROCESSING_PROFILE,
        adapter_code_sha256=runtime_identity.adapter_code_sha256,
        mineocclude_revision=runtime_identity.mineocclude_revision,
    )


def _assets_preflight() -> None:
    checks = {
        "main_checkpoint": (MAIN_CHECKPOINT, wave2.PINNED_MAIN_CHECKPOINT_SHA256),
        "vae_config": (VAE_CONFIG, wave2.PINNED_VAE_CONFIG_SHA256),
        "vae_checkpoint": (VAE_CHECKPOINT, wave2.PINNED_VAE_CHECKPOINT_SHA256),
        "model_config": (
            MINEWORLD_ROOT / MODEL_CONFIG_RELATIVE_PATH,
            wave2.PINNED_MODEL_CONFIG_SHA256,
        ),
    }
    for name, (path, expected) in checks.items():
        if not path.is_file():
            raise ExtractionFailure("identity_failure", f"missing asset: {path}")
        observed = _sha256_file(path)
        if observed != expected:
            raise ExtractionFailure(
                "identity_failure",
                f"{name} hash mismatch: expected {expected}, got {observed}",
            )


def _environment_report() -> dict[str, Any]:
    import torch

    properties = (
        torch.cuda.get_device_properties(0) if torch.cuda.is_available() else None
    )
    return {
        "python_version": sys.version,
        "torch_version": torch.__version__,
        "torch_cuda_version": str(torch.version.cuda),
        "cuda_available": bool(torch.cuda.is_available()),
        "device_name": str(properties.name) if properties else None,
        "total_memory_bytes": int(properties.total_memory) if properties else None,
        "platform": platform.platform(),
        "mineocclude_revision": _run_git("rev-parse", "HEAD"),
        "generated_at": _now_iso(),
    }


class Runtime:
    """Holds the once-loaded adapter/runtime identity for the whole run."""

    def __init__(self) -> None:
        self.adapter = None
        self.runtime_identity = None
        self.environment_report_sha256: str | None = None

    def ensure_loaded(self) -> None:
        if self.adapter is not None:
            return
        _assets_preflight()
        import torch

        if not torch.cuda.is_available():
            raise ExtractionFailure("host_oom", "CUDA is required and unavailable")
        torch.cuda.set_device(0)

        env_report = _environment_report()
        env_bytes = (json.dumps(env_report, sort_keys=True, indent=2) + "\n").encode(
            "utf-8"
        )
        env_sha256 = _sha256_bytes(env_bytes)
        SESSION_LOG_ROOT.mkdir(parents=True, exist_ok=True)
        (SESSION_LOG_ROOT / f"environment_report_{env_sha256[:16]}.json").write_bytes(
            env_bytes
        )

        adapter = adapter_module.create_mineworld_adapter(
            preprocessing_identity=wave5.PERSON_A_66_CELL_V0_2_PREPROCESSING_PROFILE,
        )
        runtime_identity = adapter.load_runtime(
            adapter_module.RuntimeLoadRequest(
                schema_version=SCHEMA_VERSION,
                runtime_id=f"{RUN_ID}:runtime",
                mineocclude_revision=_run_git("rev-parse", "HEAD"),
                mineworld_source_revision=wave2.PINNED_SOURCE_REVISION,
                modelscope_asset_revision=wave2.PINNED_ASSET_REVISION,
                mineworld_source_root=MINEWORLD_ROOT,
                model_config_path=MINEWORLD_ROOT / MODEL_CONFIG_RELATIVE_PATH,
                main_checkpoint_path=MAIN_CHECKPOINT,
                vae_config_path=VAE_CONFIG,
                vae_checkpoint_path=VAE_CHECKPOINT,
                model_config_sha256=wave2.PINNED_MODEL_CONFIG_SHA256,
                main_checkpoint_sha256=wave2.PINNED_MAIN_CHECKPOINT_SHA256,
                vae_config_sha256=wave2.PINNED_VAE_CONFIG_SHA256,
                vae_checkpoint_sha256=wave2.PINNED_VAE_CHECKPOINT_SHA256,
                environment_report_sha256=env_sha256,
                precision=PRECISION,
                device=REQUIRED_DEVICE,
                expected_adapter_code_sha256=wave4._adapter_code_identity().sha256,
            )
        )
        if (
            runtime_identity.layer_count != len(FROZEN_PHASE6_LAYERS)
            or runtime_identity.hidden_size != HIDDEN_WIDTH
            or runtime_identity.device != REQUIRED_DEVICE
            or runtime_identity.preprocessing_identity
            != wave5.PERSON_A_66_CELL_V0_2_PREPROCESSING_PROFILE
        ):
            raise ExtractionFailure(
                "model_failure",
                "loaded runtime identity does not match the frozen v0.2 contract",
            )
        self.adapter = adapter
        self.runtime_identity = runtime_identity
        self.environment_report_sha256 = env_sha256


_RUNTIME = Runtime()


def _discovery_from_modules(modules: tuple[tuple[str, object], ...]) -> Any:
    if len(modules) != len(FROZEN_PHASE6_LAYERS):
        raise ExtractionFailure(
            "model_failure", "teacher boundary did not expose 20 decoder modules"
        )
    names = tuple(name for name, _module in modules)
    layers = tuple(
        hooks_module.HookLayerMetadata(
            layer_idx=index,
            module_name=name,
            module_type=f"{type(module).__module__}.{type(module).__qualname__}",
            conceptual_site=hooks_module.CONCEPTUAL_HOOK_SITE,
            discovery_version=hooks_module.HOOK_DISCOVERY_VERSION,
        )
        for index, (name, module) in enumerate(modules)
    )
    parent = names[0].rsplit(".", 1)[0]
    if names != tuple(f"{parent}.{index}" for index in FROZEN_PHASE6_LAYERS):
        raise ExtractionFailure(
            "model_failure", "decoder module identities are not one frozen 0..19 set"
        )
    return hooks_module.FrozenHookDiscovery(
        layers=layers,
        module_name_pattern=f"{parent}.{{layer_idx}}",
        conceptual_site=hooks_module.CONCEPTUAL_HOOK_SITE,
        discovery_version=hooks_module.HOOK_DISCOVERY_VERSION,
        _modules=tuple(module for _name, module in modules),
    )


def _capture_mapping(captures: tuple[Any, ...]) -> dict[int, Any]:
    return {capture.layer.layer_idx: capture for capture in captures}


def _teacher_capture(
    adapter: Any,
    runtime_identity: Any,
    tokenized: Any,
    accepted_manifest_sha256: str,
) -> tuple[Any, tuple[Any, ...]]:
    holder: dict[str, Any] = {}

    def factory(modules: tuple[tuple[str, object], ...]) -> Any:
        manager = hooks_module.ScopedHookManager(_discovery_from_modules(modules))
        holder["manager"] = manager
        return manager

    result = adapter.teacher_forced(
        adapter_module.TeacherForcedRequest(
            runtime_identity=runtime_identity,
            trajectory=tokenized,
            seed=SEED,
            precision=PRECISION,
            batch_size=1,
            hook_context_factory=factory,
            expected_adapter_code_sha256=wave4._adapter_code_identity().sha256,
            accepted_manifest_sha256=accepted_manifest_sha256,
        )
    )
    manager = holder.get("manager")
    if manager is None or not manager.closed:
        raise ExtractionFailure(
            "model_failure", "scoped hook manager did not close cleanly"
        )
    captures = manager.require_complete()
    return result, tuple(captures[index] for index in FROZEN_PHASE6_LAYERS)


def _existing_snapshot(
    store_root: Path,
    source_bindings: tuple[Any, ...],
) -> ActivationIndexSnapshotV2 | None:
    index_dir = store_root / "indexes"
    if not index_dir.is_dir():
        return None
    best: ActivationIndexSnapshotV2 | None = None
    for path in sorted(index_dir.glob("index-*.json")):
        snapshot = load_activation_index_snapshot_v2(
            path, store_root=store_root, source_bindings=source_bindings
        )
        if best is None or len(snapshot.index_rows) > len(best.index_rows):
            best = snapshot
    return best


@dataclasses.dataclass
class TrajectoryResult:
    completion: CompletionRecord
    snapshot: ActivationIndexSnapshotV2
    store_root: Path
    skipped_gpu_work: bool


def process_trajectory(
    trajectory_id: str, expected_frame_count: int
) -> TrajectoryResult:
    """Extract and store all 20 layers for one trajectory (resume-safe)."""

    started = time.monotonic()
    _RUNTIME.ensure_loaded()
    adapter = _RUNTIME.adapter
    runtime_identity = _RUNTIME.runtime_identity

    package_bytes = _capture_package_bytes(trajectory_id)
    declared_sha256 = _capture_package_declared_sha256(trajectory_id)
    observed_sha256 = _sha256_bytes(package_bytes)
    if observed_sha256 != declared_sha256:
        raise ExtractionFailure(
            "checksum_failure",
            f"{trajectory_id}: capture package hash does not match Person C's "
            "own declared sha256",
        )
    document = json.loads(package_bytes)
    if document.get("trajectory_id") != trajectory_id:
        raise ExtractionFailure(
            "identity_failure", f"{trajectory_id}: document trajectory_id mismatch"
        )

    frame_map_bytes = _c_stream_bytes(trajectory_id, "frame_map")
    state_bytes = _c_stream_bytes(trajectory_id, "server_state")
    frame_map_rows = sorted(
        _jsonl_rows(frame_map_bytes), key=lambda row: row["model_frame_idx"]
    )
    state_rows = sorted(
        _jsonl_rows(state_bytes), key=lambda row: row["model_frame_idx"]
    )
    if (
        len(frame_map_rows) != expected_frame_count
        or len(state_rows) != expected_frame_count
    ):
        raise ExtractionFailure(
            "data_failure",
            f"{trajectory_id}: expected {expected_frame_count} C rows, got "
            f"{len(frame_map_rows)} frame_map / {len(state_rows)} state",
        )

    source_bindings = build_source_frame_bindings_v2(
        trajectory_id=trajectory_id,
        frame_map_rows=frame_map_rows,
        state_rows=state_rows,
        c_frame_map_sha256=_sha256_bytes(frame_map_bytes),
        c_state_sha256=_sha256_bytes(state_bytes),
    )

    store_identity = ActivationStoreIdentityV2(
        schema_version=SCHEMA_VERSION,
        format_version=ACTIVATION_STORE_V2_FORMAT_VERSION,
        run_id=RUN_ID,
        checkpoint_hash=wave2.PINNED_MAIN_CHECKPOINT_SHA256,
        model_hash=wave2.PINNED_MAIN_CHECKPOINT_SHA256,
        config_hash=CONFIG_HASH,
        preprocess_hash=wave5.PERSON_A_66_CELL_V0_2_PREPROCESS_HASH,
        accepted_manifest_hash=ACCEPTED_MANIFEST_SHA256,
        code_sha=_run_git("rev-parse", "HEAD"),
        hook_site=HOOK_SITE,
        requested_layers=FROZEN_PHASE6_LAYERS,
        dtype="float32",
        hidden_width=HIDDEN_WIDTH,
    )

    store_root = STORE_OUTPUT_ROOT / f"{trajectory_id}-activation-store-v2"
    if store_root.exists():
        snapshot = _existing_snapshot(store_root, source_bindings)
    else:
        store_root.mkdir(parents=True)
        snapshot = None
    completed_layers = (
        {row["layer_idx"] for row in snapshot.index_rows} if snapshot else set()
    )
    remaining_layers = [
        layer for layer in FROZEN_PHASE6_LAYERS if layer not in completed_layers
    ]
    expected_rows = expected_frame_count * len(FROZEN_PHASE6_LAYERS)

    if not remaining_layers:
        if snapshot is None or len(snapshot.index_rows) != expected_rows:
            raise ExtractionFailure(
                "data_failure",
                f"{trajectory_id}: no remaining layers but row count is wrong",
            )
        record = CompletionRecord(
            activation_index_sha256=snapshot.snapshot_id,
            activation_row_count=len(snapshot.index_rows),
            chunk_count=len(snapshot.chunks),
            chunk_sha256=tuple(chunk.sha256 for chunk in snapshot.chunks),
            activation_bytes=sum(chunk.byte_size for chunk in snapshot.chunks),
            elapsed_seconds=time.monotonic() - started,
            completed_at=_now_iso(),
        )
        return TrajectoryResult(record, snapshot, store_root, skipped_gpu_work=True)

    validated = adapter.validate_trajectory(
        adapter_module.AcceptedTrajectoryInput(
            schema_version=SCHEMA_VERSION,
            trajectory_id=trajectory_id,
            accepted_manifest_sha256=observed_sha256,
            document=document,
        )
    )
    if len(validated.frame_identities) != expected_frame_count:
        raise ExtractionFailure(
            "data_failure",
            f"{trajectory_id}: adapter preserved "
            f"{len(validated.frame_identities)} of {expected_frame_count} frames",
        )

    manifest_index = _frame_manifest_index()
    frames = []
    for identity in validated.frame_identities:
        record = manifest_index.get((identity.trajectory_id, identity.model_frame_idx))
        if record is None:
            raise ExtractionFailure(
                "data_failure",
                f"{trajectory_id}: no preprocessed-frame manifest record for "
                f"frame {identity.model_frame_idx}",
            )
        frames.append(_load_preprocessed_frame(identity, record, runtime_identity))
    frames = tuple(frames)

    raw_action_rows = {
        row["model_frame_idx"]: row for row in document["streams"]["raw_actions"]
    }
    actions = tuple(
        adapter.convert_action(
            adapter_module.ActionConversionRequest(
                identity=identity,
                action_idx=raw_action_rows[identity.model_frame_idx]["action_idx"],
                raw_action=raw_action_rows[identity.model_frame_idx]["raw_action"],
            )
        )
        for identity in validated.frame_identities
    )

    windows = []
    for start in range(0, expected_frame_count, 16):
        stop = min(start + 16, expected_frame_count)
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
            raise ExtractionFailure(
                "model_failure",
                f"{trajectory_id}: window {start}:{stop} lost global/local identity",
            )
        windows.append(tokenized)

    import torch

    rows_by_layer: dict[int, list[dict[str, Any]]] = {
        layer: [] for layer in remaining_layers
    }
    vectors_by_layer: dict[int, list[Any]] = {layer: [] for layer in remaining_layers}
    remaining_set = set(remaining_layers)
    for tokenized in windows:
        _, captures = _teacher_capture(
            adapter, runtime_identity, tokenized, observed_sha256
        )
        candidates = store_v1.extract_complete_pooled_context(
            captures=_capture_mapping(captures),
            frame_token_map=tokenized.frame_token_map,
            hook_site=HOOK_SITE,
        )
        for candidate in candidates:
            if candidate.layer_idx not in remaining_set:
                continue
            source = source_bindings[candidate.model_frame_idx]
            row = candidate_row_from_frame_token_span_v2(
                store_identity=store_identity,
                source_identity=source,
                frame_token_map=tokenized.frame_token_map,
                frame_token_map_sha256=tokenized.frame_token_map_sha256,
                layer_idx=candidate.layer_idx,
            )
            rows_by_layer[candidate.layer_idx].append(row)
            vectors_by_layer[candidate.layer_idx].append(candidate.vector)
        del captures, candidates
        torch.cuda.empty_cache()

    creation_timestamp = _now_iso()
    for layer in remaining_layers:
        rows = rows_by_layer[layer]
        vectors = np.stack(
            [
                vector.detach().cpu().contiguous().numpy()
                for vector in vectors_by_layer[layer]
            ],
            axis=0,
        ).astype(np.float32, copy=False)
        snapshot = publish_activation_chunk_v2(
            store_root=store_root,
            store_identity=store_identity,
            source_bindings=source_bindings,
            rows=rows,
            vectors=vectors,
            creation_timestamp=creation_timestamp,
            prior_snapshot=snapshot,
        )

    if snapshot is None or len(snapshot.index_rows) != expected_rows:
        raise ExtractionFailure(
            "data_failure",
            f"{trajectory_id}: expected {expected_rows} rows, got "
            f"{0 if snapshot is None else len(snapshot.index_rows)}",
        )
    validate_activation_index_snapshot_v2(
        snapshot, store_root=store_root, source_bindings=source_bindings
    )

    record = CompletionRecord(
        activation_index_sha256=snapshot.snapshot_id,
        activation_row_count=len(snapshot.index_rows),
        chunk_count=len(snapshot.chunks),
        chunk_sha256=tuple(chunk.sha256 for chunk in snapshot.chunks),
        activation_bytes=sum(chunk.byte_size for chunk in snapshot.chunks),
        elapsed_seconds=time.monotonic() - started,
        completed_at=creation_timestamp,
    )
    return TrajectoryResult(record, snapshot, store_root, skipped_gpu_work=False)


def _initialize_runtime_queue() -> None:
    """Clone the exact committed seed once; never mutate it in place."""

    if RUNTIME_QUEUE_STATE_PATH.is_file():
        return
    seed_bytes = SEED_QUEUE_STATE_PATH.read_bytes()
    if _sha256_bytes(seed_bytes) != SEED_QUEUE_STATE_SHA256:
        raise ExtractionFailure(
            "identity_failure",
            "committed extraction queue seed does not match its frozen SHA256",
        )
    RUNTIME_STATUS_ROOT.mkdir(parents=True, exist_ok=True)
    try:
        with RUNTIME_QUEUE_STATE_PATH.open("xb") as handle:
            handle.write(seed_bytes)
    except FileExistsError:
        # A concurrent initializer won the race. The identity-checked load
        # below decides whether its bytes are legitimate.
        pass


def load_queue() -> ExtractionQueue:
    _initialize_runtime_queue()
    expected_identity = {
        "run_id": RUN_ID,
        "config_hash": CONFIG_HASH,
        "code_sha": QUEUE_CODE_IDENTITY_SHA256,
        "accepted_manifest_sha256": ACCEPTED_MANIFEST_SHA256,
    }
    return ExtractionQueue.load(QUEUE_STATE_PATH, expected_identity=expected_identity)


def _classify_exception(error: BaseException) -> tuple[str, str]:
    if isinstance(error, ExtractionFailure):
        return error.kind, str(error)
    return "runtime_interrupted", f"{type(error).__name__}: {error}"


def drain_queue(limit: int | None = None) -> dict[str, Any]:
    queue = load_queue()
    resume_report = queue.resume()
    queue.save(QUEUE_STATE_PATH)
    processed = 0
    results = []
    while True:
        if limit is not None and processed >= limit:
            break
        item = queue.next_pending()
        if item is None:
            break
        queue.mark_running(item.item_id)
        queue.save(QUEUE_STATE_PATH)
        try:
            result = process_trajectory(
                item.expected.trajectory_id, item.expected.frame_count
            )
        except BaseException as error:  # noqa: BLE001
            kind, detail = _classify_exception(error)
            queue.fail(item.item_id, failure_kind=kind, detail=detail)
            queue.save(QUEUE_STATE_PATH)
            results.append(
                {"item_id": item.item_id, "status": "failed", "detail": detail}
            )
            processed += 1
            if kind not in (
                "transient_failure",
                "host_oom",
                "io_failure",
                "runtime_interrupted",
            ):
                # Quarantined: a real defect, not a retry-worthy blip. Stop the
                # drain so it can be triaged rather than burning the whole queue.
                break
            continue
        queue.complete(item.item_id, result.completion)
        queue.save(QUEUE_STATE_PATH)
        results.append(
            {
                "item_id": item.item_id,
                "status": "completed",
                "activation_row_count": result.completion.activation_row_count,
                "chunk_count": result.completion.chunk_count,
                "skipped_gpu_work": result.skipped_gpu_work,
            }
        )
        processed += 1
    return {
        "resume_report": resume_report,
        "processed": processed,
        "results": results,
        "status": queue.status(),
    }


def _print(document: Any) -> None:
    print(json.dumps(document, indent=2, sort_keys=True, default=str))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    smoke_parser = commands.add_parser("smoke", help="run exactly one smoke trajectory")
    smoke_parser.add_argument("--trajectory-id", default="layout_03_ep12622")

    rollover_parser = commands.add_parser(
        "rollover", help="run one >16-frame trajectory and verify window rollover"
    )
    rollover_parser.add_argument("--trajectory-id", default="layout_06_ep12625")

    drain_parser = commands.add_parser("drain", help="drain the full extraction queue")
    drain_parser.add_argument("--limit", type=int, default=None)

    commands.add_parser("status", help="print current queue status")

    args = parser.parse_args(argv)
    queue = load_queue()

    if args.command == "status":
        _print(queue.status())
        return 0

    if args.command == "smoke":
        item = queue.items[args.trajectory_id]
        result_first = process_trajectory(args.trajectory_id, item.expected.frame_count)
        result_second = process_trajectory(
            args.trajectory_id, item.expected.frame_count
        )
        ok = (
            result_first.completion.activation_row_count
            == result_second.completion.activation_row_count
            == item.expected.expected_row_count
            and result_first.completion.chunk_count
            == result_second.completion.chunk_count
            == item.expected.expected_chunk_count
            and result_second.skipped_gpu_work
        )
        _print(
            {
                "trajectory_id": args.trajectory_id,
                "first_run": dataclasses.asdict(result_first.completion),
                "second_run": dataclasses.asdict(result_second.completion),
                "second_run_skipped_gpu_work": result_second.skipped_gpu_work,
                "expected_activation_row_count": item.expected.expected_row_count,
                "dedup_and_resume_ok": ok,
            }
        )
        return 0 if ok else 1

    if args.command == "rollover":
        item = queue.items[args.trajectory_id]
        if item.expected.frame_count <= 16:
            print(
                f"error: {args.trajectory_id} has only {item.expected.frame_count} "
                "frames; need >16 to exercise a rollover",
                file=sys.stderr,
            )
            return 2
        result = process_trajectory(args.trajectory_id, item.expected.frame_count)
        rows = result.snapshot.index_rows
        checks = {}
        for global_idx, expected_local in ((15, 15), (16, 0), (17, 1)):
            matching = [
                row
                for row in rows
                if row["global_model_frame_idx"] == global_idx and row["layer_idx"] == 0
            ]
            checks[f"global_{global_idx}"] = {
                "found": len(matching) == 1,
                "context_local_pair_idx": (
                    matching[0]["context_local_pair_idx"] if matching else None
                ),
                "expected_local": expected_local,
                "pass": bool(matching)
                and matching[0]["context_local_pair_idx"] == expected_local,
            }
        final_window_start = ((item.expected.frame_count - 1) // 16) * 16
        for offset, global_idx in enumerate(
            range(final_window_start, item.expected.frame_count)
        ):
            matching = [
                row
                for row in rows
                if row["global_model_frame_idx"] == global_idx and row["layer_idx"] == 0
            ]
            checks[f"final_window_global_{global_idx}"] = {
                "found": len(matching) == 1,
                "context_local_pair_idx": (
                    matching[0]["context_local_pair_idx"] if matching else None
                ),
                "expected_local": offset,
                "pass": bool(matching)
                and matching[0]["context_local_pair_idx"] == offset,
            }
        all_pass = all(check["pass"] for check in checks.values())
        _print(
            {
                "trajectory_id": args.trajectory_id,
                "frame_count": item.expected.frame_count,
                "activation_row_count": result.completion.activation_row_count,
                "checks": checks,
                "rollover_test_pass": all_pass,
            }
        )
        return 0 if all_pass else 1

    if args.command == "drain":
        report = drain_queue(limit=args.limit)
        _print(report)
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
