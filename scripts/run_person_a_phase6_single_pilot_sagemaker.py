#!/usr/bin/env python3
"""Fail-closed one-pilot SageMaker runner for Person A Phase 6.

Importing this module and using ``plan`` perform no CUDA query, model load,
media decode, or scientific operation.  ``run`` is restricted to the exact
ratified Linux GPU workflow and executes Steps 6.1 through 6.5 in order.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import importlib
import json
import os
import platform
import shutil
import subprocess
import sys
import time
import traceback
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mineocclude.activations.store_v2 import (
    ACTIVATION_INDEX_V2_FORMAT_VERSION,
    ACTIVATION_STORE_V2_FORMAT_VERSION,
    FROZEN_PHASE6_LAYERS,
    ActivationIndexSnapshotV2,
    ActivationStoreIdentityV2,
    build_source_frame_bindings_v2,
    candidate_row_from_frame_token_span_v2,
    canonical_json_bytes,
    publish_activation_chunk_v2,
    validate_activation_index_snapshot_v2,
)

RUNNER_VERSION = "person-a-phase6-single-pilot-sagemaker-runner-v0.2"
REQUIRED_BRANCH = "role/person-a-model"
PERSON_A_STARTING_AUTHORITY = "5cbb42179e9069e25eac44ef5e1746b9f3b4a96c"
PERSON_A_ACKNOWLEDGEMENT = "ca3f5695dc37f9f2c8066e323b25485c042b6cf7"
PERSON_B_RUNTIME_AUTHORIZATION = "43e5ac83004cce2145384c1383f2c3820311af14"
PERSON_B_SAGEMAKER_RATIFICATION = "bf2640ed4680475da337aae40ef2982ea7d3833c"
PERSON_C_ACCEPTED_PILOT = "f0d4e895b56fc4ca3f4805aa13b73545744af1b0"
PERSON_E_REGISTRY_V2_VALIDATOR = "b27d404c6aa913bac559754fa8b7accdff46e886"
MINEWORLD_REVISION = "9f49efbcc68a5f0cf60e78f0abc566eac409282f"
SELECTED_PILOT = "layout_00_ep9403"
DETERMINISTIC_SEED = 20260725
REQUIRED_DEVICE = "cuda:0"
GLOBAL_MODEL_FRAME_COUNT = 248
EXPECTED_ACTIVATION_ROW_COUNT = 4960
HOOK_SITE = "decoder_layer_output_residual_stream"
HIDDEN_WIDTH = 2048
MODEL_CONFIG_PATH = "configs/700M_16f.yaml"
EXPECTED_SAGEMAKER_MINEWORLD_ROOT = Path(
    "/home/sagemaker-user/MineWorld-Upstream"
)
EXPECTED_SAGEMAKER_MODEL_CONFIG_PATH = (
    EXPECTED_SAGEMAKER_MINEWORLD_ROOT / MODEL_CONFIG_PATH
)
MODEL_CONFIG_GIT_BLOB_SHA256 = (
    "e13b3a80fb370547a05852809c2c8f02d05ebe2fce3b3bb2fd1ee54eee78c018"
)
MAIN_CHECKPOINT_SHA256 = (
    "a92c311baf49bbf31338da2caaadc9e4f947b94df8abcf75da350c4ae41319c5"
)
VAE_CONFIG_SHA256 = (
    "32ca759d5b90f0c5aa5df0e312a81e03dd4d3af68896863c88f910d19f2526cb"
)
VAE_CHECKPOINT_SHA256 = (
    "370d06be427e034476b6b95ba0080a4b48266e876c4776a757b944b87b87d9ab"
)
PREPROCESS_HASH = (
    "036fa0b4899285e5499f88581f6e02426a25f732fcc26bd63c0f5b3863a9d9ab"
)
PHASE6_CONFIG_HASH = (
    "eb634c1e81c65a724b7cf32cbfe03f62e80a4428afda605071e1a43c6d0f4c10"
)
C_CAPTURE_PACKAGE_SHA256 = (
    "21ea1dba91cf92ad82080088f70905fba053557392437b19591cad1333667213"
)
C_FRAME_MAP_SHA256 = (
    "eb1ff07b794a5f4aab6fb1ce6cfcca784cb3dc233a786c67d565f1f3efcd645b"
)
C_STATE_SHA256 = (
    "ef6213e4e67ecec4164bd405e8e9520464d5fd6a985d46cd847eb97165352ea4"
)
C_ACCEPTED_MANIFEST_PATH = (
    "docs/status/person_c_phase4_step4_1_registry_v2_handoff_v0_1/"
    "accepted_pilot_manifest.json"
)
C_CAPTURE_PACKAGE_PATH = (
    "data/autonomous/layout_00_ep9403/capture_package_v0_1.json"
)
C_INPUT_PATHS = {
    "frame_map": (
        "data/autonomous/layout_00_ep9403/package_v0_1/frame_map.jsonl"
    ),
    "media": "data/autonomous/layout_00_ep9403/video_640x360.mp4",
    "normalized_actions": (
        "data/autonomous/layout_00_ep9403/package_v0_1/"
        "normalized_actions.jsonl"
    ),
    "raw_actions": (
        "data/autonomous/layout_00_ep9403/package_v0_1/raw_actions.jsonl"
    ),
    "state": (
        "data/autonomous/layout_00_ep9403/package_v0_1/server_state.jsonl"
    ),
    "visibility": (
        "data/autonomous/layout_00_ep9403/package_v0_1/visibility.jsonl"
    ),
}
PHASE6_STEPS = ("6.1", "6.2", "6.3", "6.4", "6.5")
MINIMUM_FREE_DISK_BYTES = 10 * 1024**3
MINIMUM_GPU_MEMORY_BYTES = 12 * 1024**3


class Phase6RunnerError(RuntimeError):
    """One actionable hard-gate failure."""

    def __init__(self, code: str, message: str, *, step: str) -> None:
        self.code = code
        self.step = step
        super().__init__(f"{code}[step={step}]: {message}")


def _fail(code: str, message: str, *, step: str) -> None:
    raise Phase6RunnerError(code, message, step=step)


def _run_git(
    repository: Path,
    *arguments: str,
    binary: bool = False,
    check: bool = True,
) -> bytes | str:
    result = subprocess.run(
        ["git", "-C", str(repository), *arguments],
        check=False,
        capture_output=True,
    )
    if check and result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(
            f"git {' '.join(arguments)} failed with {result.returncode}: {detail}"
        )
    if binary:
        return result.stdout
    return result.stdout.decode("utf-8", errors="strict").strip()


def _git_object_bytes(repository: Path, expression: str) -> bytes:
    return _run_git(repository, "show", expression, binary=True)  # type: ignore[return-value]


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validated_physical_model_config_path(
    *,
    mineworld_root: Path,
    git_blob_bytes: bytes,
    expected_path: Path = EXPECTED_SAGEMAKER_MODEL_CONFIG_PATH,
    expected_sha256: str = MODEL_CONFIG_GIT_BLOB_SHA256,
) -> Path:
    """Return only the exact ordinary config whose bytes match the Git blob."""

    physical_path = mineworld_root / MODEL_CONFIG_PATH
    if physical_path.is_symlink() or not physical_path.is_file():
        _fail(
            "model_config_physical_path_invalid",
            "runtime model configuration must be an existing ordinary file",
            step="preflight",
        )
    try:
        resolved = physical_path.resolve(strict=True)
    except OSError as error:
        _fail(
            "model_config_physical_path_invalid",
            f"runtime model configuration cannot be resolved: {error}",
            step="preflight",
        )
    if resolved != expected_path:
        _fail(
            "model_config_physical_path_invalid",
            (
                "runtime model configuration must resolve exactly to "
                f"{expected_path}"
            ),
            step="preflight",
        )
    physical_bytes = resolved.read_bytes()
    if physical_bytes != git_blob_bytes:
        _fail(
            "model_config_byte_mismatch",
            "physical model configuration differs from frozen Git-object bytes",
            step="preflight",
        )
    physical_sha256 = _sha256_bytes(physical_bytes)
    if (
        physical_sha256 != expected_sha256
        or _sha256_bytes(git_blob_bytes) != expected_sha256
    ):
        _fail(
            "model_config_identity_mismatch",
            "physical and Git-object configuration hashes must match the freeze",
            step="preflight",
        )
    return resolved


def _canonical_document_bytes(value: Mapping[str, Any]) -> bytes:
    return canonical_json_bytes(dict(value))


def _exclusive_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def _write_json(path: Path, document: Mapping[str, Any]) -> None:
    _exclusive_write(path, _canonical_document_bytes(document))


def _json_lines(payload: bytes, *, label: str) -> list[dict[str, Any]]:
    try:
        text = payload.decode("utf-8")
        rows = [
            json.loads(line)
            for line in text.splitlines()
            if line.strip()
        ]
    except (UnicodeError, json.JSONDecodeError) as error:
        _fail(
            "invalid_jsonl",
            f"{label} is not valid UTF-8 JSONL: {error}",
            step="6.1",
        )
    if not rows or any(not isinstance(row, dict) for row in rows):
        _fail(
            "invalid_jsonl",
            f"{label} must contain JSON objects",
            step="6.1",
        )
    return rows


def _git_commit_exists(repository: Path, revision: str) -> bool:
    result = subprocess.run(
        [
            "git",
            "-C",
            str(repository),
            "cat-file",
            "-e",
            f"{revision}^{{commit}}",
        ],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return result.returncode == 0


@dataclass(frozen=True)
class RunnerArguments:
    repository_root: Path
    mineworld_root: Path
    asset_root: Path
    main_checkpoint: Path
    vae_config: Path
    vae_checkpoint: Path
    approved_input_root: Path
    approved_output_root: Path
    activation_store_v2_ratification_object: str
    session_id: str
    seed: int
    device: str
    precision: str


@dataclass
class RunContext:
    arguments: RunnerArguments
    session_root: Path
    runtime_receipt: dict[str, Any]
    state: dict[str, Any] = dataclass_field(default_factory=dict)
    step_receipts: list[dict[str, Any]] = dataclass_field(default_factory=list)


def plan_document() -> dict[str, Any]:
    """Return the preparation-only plan without touching CUDA or the model."""

    return {
        "activation_index_format_version": ACTIVATION_INDEX_V2_FORMAT_VERSION,
        "activation_store_format_version": ACTIVATION_STORE_V2_FORMAT_VERSION,
        "b_activation_store_v2_ratification_required": True,
        "deterministic_seed": DETERMINISTIC_SEED,
        "device": REQUIRED_DEVICE,
        "expected_activation_rows": EXPECTED_ACTIVATION_ROW_COUNT,
        "global_model_frame_count": GLOBAL_MODEL_FRAME_COUNT,
        "local_scientific_execution_performed": False,
        "runner_version": RUNNER_VERSION,
        "selected_pilot": SELECTED_PILOT,
        "sequential_steps": list(PHASE6_STEPS),
        "step6_6_mode": "handoff_preparation_only",
    }


def _validate_ratification_document(
    document: object,
    *,
    current_commit: str,
    module_sha256: str,
) -> None:
    if not isinstance(document, Mapping):
        _fail(
            "missing_b_v2_ratification",
            "B ratification object must contain a JSON object",
            step="preflight",
        )
    expected = {
        "activation_index_format_version": ACTIVATION_INDEX_V2_FORMAT_VERSION,
        "activation_store_format_version": ACTIVATION_STORE_V2_FORMAT_VERSION,
        "decision": "ratified",
        "expected_activation_row_count": EXPECTED_ACTIVATION_ROW_COUNT,
        "person_a_activation_store_v2_commit": current_commit,
        "person_a_activation_store_v2_module_sha256": module_sha256,
        "scientific_execution_authorized": True,
        "selected_pilot": SELECTED_PILOT,
    }
    for field, value in expected.items():
        if document.get(field) != value:
            _fail(
                "missing_b_v2_ratification",
                f"B ratification field {field!r} must equal {value!r}",
                step="preflight",
            )
    if document.get("owner") != "person_b":
        _fail(
            "missing_b_v2_ratification",
            "activation-store v2 ratification must be owned by Person B",
            step="preflight",
        )


def verify_activation_store_v2_ratification(
    *,
    repository: Path,
    object_expression: str,
    current_commit: str,
    module_sha256: str,
) -> dict[str, Any]:
    """Require a future exact B-owned Git object ratifying this v2 commit."""

    if not object_expression or ":" not in object_expression:
        _fail(
            "missing_b_v2_ratification",
            "an exact <commit>:<path> B ratification object is required",
            step="preflight",
        )
    commit, _separator, path = object_expression.partition(":")
    if (
        len(commit) != 40
        or len(path) == 0
        or not _git_commit_exists(repository, commit)
    ):
        _fail(
            "missing_b_v2_ratification",
            "B ratification commit/path does not resolve exactly",
            step="preflight",
        )
    try:
        payload = _git_object_bytes(repository, object_expression)
        document = json.loads(payload)
    except (RuntimeError, UnicodeError, json.JSONDecodeError) as error:
        _fail(
            "missing_b_v2_ratification",
            f"B ratification object could not be verified: {error}",
            step="preflight",
        )
    _validate_ratification_document(
        document,
        current_commit=current_commit,
        module_sha256=module_sha256,
    )
    return {
        "commit": commit,
        "git_object": object_expression,
        "sha256": _sha256_bytes(payload),
        "verified": True,
    }


def _verify_git_authorities(repository: Path) -> dict[str, bool]:
    revisions = {
        "person_a_starting_authority": PERSON_A_STARTING_AUTHORITY,
        "person_a_acknowledgement": PERSON_A_ACKNOWLEDGEMENT,
        "person_b_runtime_authorization": PERSON_B_RUNTIME_AUTHORIZATION,
        "person_b_sagemaker_ratification": PERSON_B_SAGEMAKER_RATIFICATION,
        "person_c_accepted_pilot": PERSON_C_ACCEPTED_PILOT,
        "person_e_registry_v2_validator": PERSON_E_REGISTRY_V2_VALIDATOR,
    }
    result = {
        name: _git_commit_exists(repository, revision)
        for name, revision in revisions.items()
    }
    if not all(result.values()):
        missing = sorted(name for name, exists in result.items() if not exists)
        _fail(
            "missing_authority",
            f"required committed authorities are absent: {missing!r}",
            step="preflight",
        )
    return result


def _validate_runtime_arguments(arguments: RunnerArguments) -> None:
    if arguments.seed != DETERMINISTIC_SEED:
        _fail(
            "seed_mismatch",
            f"seed must equal {DETERMINISTIC_SEED}",
            step="preflight",
        )
    if arguments.device != REQUIRED_DEVICE:
        _fail(
            "device_mismatch",
            f"device must equal {REQUIRED_DEVICE}",
            step="preflight",
        )
    if arguments.precision != "float16":
        _fail(
            "precision_mismatch",
            "the frozen single-pilot precision is float16",
            step="preflight",
        )
    for field_name in (
        "repository_root",
        "mineworld_root",
        "asset_root",
        "approved_input_root",
        "approved_output_root",
    ):
        value = getattr(arguments, field_name)
        if not value.is_absolute() or not value.is_dir() or value.is_symlink():
            _fail(
                "invalid_path",
                f"{field_name} must be an existing absolute ordinary directory",
                step="preflight",
            )
    for field_name in (
        "main_checkpoint",
        "vae_config",
        "vae_checkpoint",
    ):
        value = getattr(arguments, field_name)
        if not value.is_absolute() or not value.is_file() or value.is_symlink():
            _fail(
                "invalid_path",
                f"{field_name} must be an existing absolute ordinary file",
                step="preflight",
            )
    try:
        arguments.approved_output_root.resolve().relative_to(
            arguments.repository_root.resolve()
        )
    except ValueError:
        pass
    else:
        _fail(
            "invalid_path",
            "large scientific outputs must remain outside the Git worktree",
            step="preflight",
        )


def runtime_preflight(arguments: RunnerArguments) -> dict[str, Any]:
    """Run the complete fail-closed SageMaker gate before Step 6.1."""

    _validate_runtime_arguments(arguments)
    if platform.system() != "Linux":
        _fail(
            "linux_required",
            "scientific execution is restricted to Linux SageMaker",
            step="preflight",
        )
    repository = arguments.repository_root
    branch = _run_git(repository, "branch", "--show-current")
    current_commit = _run_git(repository, "rev-parse", "HEAD")
    status = _run_git(repository, "status", "--porcelain=v1", "-uall")
    if branch != REQUIRED_BRANCH or status:
        _fail(
            "git_checkout_invalid",
            "Person A checkout must be on the exact clean role branch",
            step="preflight",
        )
    authorities = _verify_git_authorities(repository)
    module_path = (
        repository / "src" / "mineocclude" / "activations" / "store_v2.py"
    )
    ratification = verify_activation_store_v2_ratification(
        repository=repository,
        object_expression=(
            arguments.activation_store_v2_ratification_object
        ),
        current_commit=str(current_commit),
        module_sha256=_sha256_file(module_path),
    )
    mineworld_commit = _run_git(
        arguments.mineworld_root,
        "rev-parse",
        "HEAD",
    )
    mineworld_status = _run_git(
        arguments.mineworld_root,
        "status",
        "--porcelain=v1",
        "-uall",
    )
    if mineworld_commit != MINEWORLD_REVISION or mineworld_status:
        _fail(
            "mineworld_checkout_invalid",
            "MineWorld checkout must be exact and clean",
            step="preflight",
        )
    model_config_blob = _git_object_bytes(
        arguments.mineworld_root,
        f"{MINEWORLD_REVISION}:{MODEL_CONFIG_PATH}",
    )
    if _sha256_bytes(model_config_blob) != MODEL_CONFIG_GIT_BLOB_SHA256:
        _fail(
            "model_config_identity_mismatch",
            "authoritative Git-blob model configuration hash differs",
            step="preflight",
        )
    physical_model_config = validated_physical_model_config_path(
        mineworld_root=arguments.mineworld_root,
        git_blob_bytes=model_config_blob,
    )
    file_hashes = {
        "main_checkpoint": _sha256_file(arguments.main_checkpoint),
        "vae_config": _sha256_file(arguments.vae_config),
        "vae_checkpoint": _sha256_file(arguments.vae_checkpoint),
    }
    expected_file_hashes = {
        "main_checkpoint": MAIN_CHECKPOINT_SHA256,
        "vae_config": VAE_CONFIG_SHA256,
        "vae_checkpoint": VAE_CHECKPOINT_SHA256,
    }
    if file_hashes != expected_file_hashes:
        _fail(
            "checkpoint_identity_mismatch",
            "checkpoint or VAE bytes differ from frozen identities",
            step="preflight",
        )
    free_disk = shutil.disk_usage(arguments.approved_output_root).free
    if free_disk < MINIMUM_FREE_DISK_BYTES:
        _fail(
            "insufficient_disk",
            f"at least {MINIMUM_FREE_DISK_BYTES} free bytes are required",
            step="preflight",
        )
    torch = importlib.import_module("torch")
    if not torch.cuda.is_available() or torch.cuda.device_count() < 1:
        _fail(
            "cuda_unavailable",
            "torch.cuda.is_available() and cuda:0 are required",
            step="preflight",
        )
    properties = torch.cuda.get_device_properties(0)
    if int(properties.total_memory) < MINIMUM_GPU_MEMORY_BYTES:
        _fail(
            "insufficient_gpu_memory",
            f"cuda:0 must expose at least {MINIMUM_GPU_MEMORY_BYTES} bytes",
            step="preflight",
        )
    torch.cuda.set_device(0)
    if torch.cuda.current_device() != 0:
        _fail(
            "cuda_device_mismatch",
            "selected CUDA device is not cuda:0",
            step="preflight",
        )
    nvidia = subprocess.run(
        [
            "nvidia-smi",
            "--query-gpu=name,uuid,memory.total,driver_version",
            "--format=csv,noheader",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if nvidia.returncode != 0 or not nvidia.stdout.strip():
        _fail(
            "nvidia_identity_unavailable",
            "nvidia-smi identity query must succeed",
            step="preflight",
        )
    environment = {
        key: value
        for key, value in sorted(os.environ.items())
        if key.startswith(("AWS_", "SM_", "SAGEMAKER_"))
        and "SECRET" not in key
        and "TOKEN" not in key
        and "KEY" not in key
    }
    return {
        "authorities": authorities,
        "aws_sagemaker_environment": environment,
        "b_activation_store_v2_ratification": ratification,
        "branch": branch,
        "cuda": {
            "available": True,
            "device": REQUIRED_DEVICE,
            "device_count": int(torch.cuda.device_count()),
            "device_name": str(properties.name),
            "total_memory_bytes": int(properties.total_memory),
            "torch_cuda_version": str(torch.version.cuda),
        },
        "dependency_identities": {
            "numpy": importlib.import_module("numpy").__version__,
            "torch": torch.__version__,
        },
        "free_disk_bytes": free_disk,
        "frozen_file_sha256": file_hashes,
        "git_commit": current_commit,
        "git_worktree_clean": True,
        "host": {
            "machine": platform.machine(),
            "node": platform.node(),
            "platform": platform.platform(),
            "python": platform.python_version(),
            "system": platform.system(),
        },
        "mineworld_commit": mineworld_commit,
        "model_config_git_blob_sha256": _sha256_bytes(model_config_blob),
        "model_config_physical_path": str(physical_model_config),
        "model_config_physical_sha256": _sha256_file(
            physical_model_config
        ),
        "nvidia_smi": nvidia.stdout.strip().splitlines(),
        "runner_version": RUNNER_VERSION,
        "seed": arguments.seed,
        "status": "PASS",
    }


def _source_object_payloads(repository: Path) -> dict[str, bytes]:
    payloads = {
        "accepted_manifest": _git_object_bytes(
            repository,
            f"{PERSON_C_ACCEPTED_PILOT}:{C_ACCEPTED_MANIFEST_PATH}",
        ),
        "capture_package": _git_object_bytes(
            repository,
            f"{PERSON_C_ACCEPTED_PILOT}:{C_CAPTURE_PACKAGE_PATH}",
        ),
    }
    payloads.update(
        {
            name: _git_object_bytes(
                repository,
                f"{PERSON_C_ACCEPTED_PILOT}:{path}",
            )
            for name, path in C_INPUT_PATHS.items()
        }
    )
    return payloads


def step6_1_intake(context: RunContext) -> dict[str, Any]:
    """Resolve the one C-accepted pilot through exact committed objects."""

    payloads = _source_object_payloads(context.arguments.repository_root)
    if _sha256_bytes(payloads["capture_package"]) != C_CAPTURE_PACKAGE_SHA256:
        _fail(
            "capture_package_hash_mismatch",
            "accepted C capture package bytes do not match",
            step="6.1",
        )
    try:
        accepted_manifest = json.loads(payloads["accepted_manifest"])
        package = json.loads(payloads["capture_package"])
    except (UnicodeError, json.JSONDecodeError) as error:
        _fail(
            "invalid_c_package",
            f"accepted C JSON could not be parsed: {error}",
            step="6.1",
        )
    if (
        accepted_manifest.get("accepted_pilot_count") != 1
        or accepted_manifest.get("intake_row", {}).get("artifact_id")
        != SELECTED_PILOT
        or package.get("trajectory_id") != SELECTED_PILOT
    ):
        _fail(
            "pilot_selection_mismatch",
            "C manifest must select exactly layout_00_ep9403",
            step="6.1",
        )
    intake = accepted_manifest["intake_row"]
    declared = {
        "frame_map": intake["frame_map_sha256"],
        "media": intake["media_sha256"],
        "normalized_actions": intake["normalized_actions_sha256"],
        "raw_actions": intake["raw_actions_sha256"],
        "state": intake["state_sha256"],
        "visibility": intake["visibility_sha256"],
    }
    observed = {name: _sha256_bytes(payloads[name]) for name in declared}
    if observed != declared:
        _fail(
            "direct_input_hash_mismatch",
            "one or more C direct inputs differ from the accepted manifest",
            step="6.1",
        )
    intake_root = (
        context.arguments.approved_input_root / context.arguments.session_id
    )
    if intake_root.exists() or intake_root.is_symlink():
        _fail(
            "output_exists",
            "immutable approved intake directory already exists",
            step="6.1",
        )
    intake_root.mkdir(parents=False)
    output_names = {
        "accepted_manifest": "accepted_pilot_manifest.json",
        "capture_package": "capture_package_v0_1.json",
        "frame_map": "frame_map.jsonl",
        "media": "video_640x360.mp4",
        "normalized_actions": "normalized_actions.jsonl",
        "raw_actions": "raw_actions.jsonl",
        "state": "server_state.jsonl",
        "visibility": "visibility.jsonl",
    }
    materialized: dict[str, Path] = {}
    for name, filename in output_names.items():
        destination = intake_root / filename
        _exclusive_write(destination, payloads[name])
        materialized[name] = destination
    model_config_bytes = _git_object_bytes(
        context.arguments.mineworld_root,
        f"{MINEWORLD_REVISION}:{MODEL_CONFIG_PATH}",
    )
    model_config_provenance_path = intake_root / "700M_16f.git-blob.yaml"
    _exclusive_write(model_config_provenance_path, model_config_bytes)
    context.state.update(
        {
            "accepted_manifest": accepted_manifest,
            "capture_package": package,
            "input_paths": materialized,
            "model_config_provenance_path": model_config_provenance_path,
            "payloads": payloads,
        }
    )
    return {
        "accepted_manifest_sha256": _sha256_bytes(
            payloads["accepted_manifest"]
        ),
        "capture_package_sha256": C_CAPTURE_PACKAGE_SHA256,
        "direct_input_hashes": observed,
        "input_root": str(intake_root),
        "model_config_git_blob_sha256": _sha256_bytes(
            model_config_bytes
        ),
        "model_config_provenance_path": str(
            model_config_provenance_path
        ),
        "pilot": SELECTED_PILOT,
        "status": "PASS",
    }


def _stream_rows(package: Mapping[str, Any], name: str) -> list[dict[str, Any]]:
    streams = package.get("streams")
    rows = streams.get(name) if isinstance(streams, Mapping) else None
    if not isinstance(rows, list) or any(
        not isinstance(row, dict) for row in rows
    ):
        _fail(
            "invalid_stream",
            f"capture stream {name!r} is unavailable",
            step="6.2",
        )
    return rows


def step6_2_model_boundary(context: RunContext) -> dict[str, Any]:
    """Re-run the locked C-to-A media and one-to-one identity checks."""

    package = context.state["capture_package"]
    media = package.get("media")
    if (
        not isinstance(media, Mapping)
        or media.get("width") != 640
        or media.get("height") != 360
        or float(media.get("fps", -1)) != 20.0
        or media.get("frame_count") != GLOBAL_MODEL_FRAME_COUNT
    ):
        _fail(
            "media_contract_mismatch",
            "media must be exactly 640x360, 20 Hz, and 248 frames",
            step="6.2",
        )
    names = (
        "frame_map",
        "raw_actions",
        "normalized_actions",
        "server_state",
        "visibility",
    )
    streams = {name: _stream_rows(package, name) for name in names}
    if any(
        len(rows) != GLOBAL_MODEL_FRAME_COUNT for rows in streams.values()
    ):
        _fail(
            "stream_cardinality_mismatch",
            "every required stream must contain exactly 248 rows",
            step="6.2",
        )
    expected = list(range(GLOBAL_MODEL_FRAME_COUNT))
    for name, rows in streams.items():
        for field in (
            "model_frame_idx",
            "render_frame_idx",
            "server_tick",
        ):
            if [row.get(field) for row in rows] != expected:
                _fail(
                    "identity_ambiguity",
                    f"{name}.{field} must equal exact consecutive identity",
                    step="6.2",
                )
        if any(row.get("trajectory_id") != SELECTED_PILOT for row in rows):
            _fail(
                "identity_ambiguity",
                f"{name} contains a mismatched trajectory",
                step="6.2",
            )
    adapter_module = importlib.import_module(
        "mineocclude.models.mineworld_adapter"
    )
    identity_module = importlib.import_module(
        "mineocclude.contracts.identity"
    )
    adapter = adapter_module.create_mineworld_adapter()
    validated = adapter.validate_trajectory(
        adapter_module.AcceptedTrajectoryInput(
            schema_version=identity_module.SCHEMA_VERSION,
            trajectory_id=SELECTED_PILOT,
            accepted_manifest_sha256=C_CAPTURE_PACKAGE_SHA256,
            document=package,
        )
    )
    if len(validated.frame_identities) != GLOBAL_MODEL_FRAME_COUNT:
        _fail(
            "adapter_identity_mismatch",
            "adapter did not preserve all 248 global frame identities",
            step="6.2",
        )
    context.state.update(
        {
            "adapter": adapter,
            "streams": streams,
            "validated_trajectory": validated,
        }
    )
    return {
        "frame_count": GLOBAL_MODEL_FRAME_COUNT,
        "identity_ambiguity_count": 0,
        "pilot": SELECTED_PILOT,
        "status": "PASS",
        "stream_counts": {
            name: len(rows) for name, rows in sorted(streams.items())
        },
    }


def _runtime_load_request(context: RunContext) -> Any:
    adapter_module = importlib.import_module(
        "mineocclude.models.mineworld_adapter"
    )
    wave2 = importlib.import_module(
        "mineocclude.models._mineworld_adapter_wave2"
    )
    wave4 = importlib.import_module(
        "mineocclude.models._mineworld_adapter_wave4"
    )
    identity_module = importlib.import_module(
        "mineocclude.contracts.identity"
    )
    environment_receipt = (
        context.session_root / "runtime_preflight_receipt.json"
    )
    model_config_blob = _git_object_bytes(
        context.arguments.mineworld_root,
        f"{MINEWORLD_REVISION}:{MODEL_CONFIG_PATH}",
    )
    physical_model_config_path = validated_physical_model_config_path(
        mineworld_root=context.arguments.mineworld_root,
        git_blob_bytes=model_config_blob,
    )
    return adapter_module.RuntimeLoadRequest(
        schema_version=identity_module.SCHEMA_VERSION,
        runtime_id=f"{context.arguments.session_id}:runtime",
        mineocclude_revision=_run_git(
            context.arguments.repository_root,
            "rev-parse",
            "HEAD",
        ),
        mineworld_source_revision=MINEWORLD_REVISION,
        modelscope_asset_revision=wave2.PINNED_ASSET_REVISION,
        mineworld_source_root=context.arguments.mineworld_root,
        model_config_path=physical_model_config_path,
        main_checkpoint_path=context.arguments.main_checkpoint,
        vae_config_path=context.arguments.vae_config,
        vae_checkpoint_path=context.arguments.vae_checkpoint,
        model_config_sha256=MODEL_CONFIG_GIT_BLOB_SHA256,
        main_checkpoint_sha256=MAIN_CHECKPOINT_SHA256,
        vae_config_sha256=VAE_CONFIG_SHA256,
        vae_checkpoint_sha256=VAE_CHECKPOINT_SHA256,
        environment_report_sha256=_sha256_file(environment_receipt),
        precision=context.arguments.precision,
        device=context.arguments.device,
        expected_adapter_code_sha256=wave4._adapter_code_identity().sha256,
    )


def step6_3_tokenize(context: RunContext) -> dict[str, Any]:
    """Load the frozen runtime and build bounded 16-frame contexts."""

    adapter_module = importlib.import_module(
        "mineocclude.models.mineworld_adapter"
    )
    phase3 = importlib.import_module(
        "mineocclude.models.phase3_certification"
    )
    adapter = context.state["adapter"]
    validated = context.state["validated_trajectory"]
    runtime = adapter.load_runtime(_runtime_load_request(context))
    if (
        runtime.layer_count != len(FROZEN_PHASE6_LAYERS)
        or runtime.hidden_size != HIDDEN_WIDTH
        or runtime.device != REQUIRED_DEVICE
    ):
        _fail(
            "runtime_identity_mismatch",
            "runtime must expose 20 layers, hidden width 2048, and cuda:0",
            step="6.3",
        )
    frame_rows = context.state["streams"]["frame_map"]
    decoded = phase3._decode_frames(
        context.state["input_paths"]["media"],
        [row["render_frame_idx"] for row in frame_rows],
    )
    frames = tuple(
        adapter.preprocess_frame(
            adapter_module.FramePreprocessRequest(
                identity=identity,
                source_frame_idx=row["render_frame_idx"],
                frame=frame,
            )
        )
        for identity, row, frame in zip(
            validated.frame_identities,
            frame_rows,
            decoded,
            strict=True,
        )
    )
    raw_by_index = {
        row["model_frame_idx"]: row
        for row in context.state["streams"]["raw_actions"]
    }
    actions = tuple(
        adapter.convert_action(
            adapter_module.ActionConversionRequest(
                identity=identity,
                action_idx=row["action_idx"],
                raw_action=raw_by_index[identity.model_frame_idx][
                    "raw_action"
                ],
            )
        )
        for identity, row in zip(
            validated.frame_identities,
            frame_rows,
            strict=True,
        )
    )
    tokenized_windows = []
    for start in range(0, GLOBAL_MODEL_FRAME_COUNT, 16):
        stop = min(start + 16, GLOBAL_MODEL_FRAME_COUNT)
        window_trajectory = dataclasses.replace(
            validated,
            frame_identities=validated.frame_identities[start:stop],
        )
        tokenized = adapter.tokenize_trajectory(
            adapter_module.TrajectoryTokenizationRequest(
                runtime_identity=runtime,
                trajectory=window_trajectory,
                frames=frames[start:stop],
                actions=actions[start:stop],
            )
        )
        spans = tokenized.frame_token_map.spans
        if (
            [span.identity.model_frame_idx for span in spans]
            != list(range(start, stop))
            or [span.pair_index for span in spans]
            != list(range(stop - start))
        ):
            _fail(
                "frame_token_map_identity_mismatch",
                "window must preserve global identity and local 0..15 pairs",
                step="6.3",
            )
        tokenized_windows.append(tokenized)
    expected_context_count = (GLOBAL_MODEL_FRAME_COUNT + 15) // 16
    if len(tokenized_windows) != expected_context_count:
        _fail(
            "context_count_mismatch",
            (
                f"{GLOBAL_MODEL_FRAME_COUNT} frames must produce exactly "
                f"{expected_context_count} bounded contexts"
            ),
            step="6.3",
        )
    context.state.update(
        {
            "actions": actions,
            "frames": frames,
            "runtime": runtime,
            "tokenized_windows": tuple(tokenized_windows),
        }
    )
    del decoded
    return {
        "context_count": len(tokenized_windows),
        "context_pair_counts": [
            len(item.frame_token_map.spans) for item in tokenized_windows
        ],
        "global_frame_count": sum(
            len(item.frame_token_map.spans) for item in tokenized_windows
        ),
        "rollover": {
            "global_15_local": 15,
            "global_16_local": 0,
        },
        "status": "PASS",
        "tokens_per_pair": 347,
    }


def _discovery_from_modules(modules: tuple[tuple[str, object], ...]) -> Any:
    hooks = importlib.import_module("mineocclude.activations.hooks")
    if len(modules) != len(FROZEN_PHASE6_LAYERS):
        _fail(
            "hook_layer_count_mismatch",
            "teacher boundary must expose exactly twenty decoder modules",
            step="6.4",
        )
    names = tuple(name for name, _module in modules)
    layers = tuple(
        hooks.HookLayerMetadata(
            layer_idx=index,
            module_name=name,
            module_type=f"{type(module).__module__}.{type(module).__qualname__}",
            conceptual_site=hooks.CONCEPTUAL_HOOK_SITE,
            discovery_version=hooks.HOOK_DISCOVERY_VERSION,
        )
        for index, (name, module) in enumerate(modules)
    )
    parent = names[0].rsplit(".", 1)[0]
    if names != tuple(f"{parent}.{index}" for index in FROZEN_PHASE6_LAYERS):
        _fail(
            "hook_layer_identity_mismatch",
            "decoder module identities are not one consecutive frozen layer set",
            step="6.4",
        )
    return hooks.FrozenHookDiscovery(
        layers=layers,
        module_name_pattern=f"{parent}.{{layer_idx}}",
        conceptual_site=hooks.CONCEPTUAL_HOOK_SITE,
        discovery_version=hooks.HOOK_DISCOVERY_VERSION,
        _modules=tuple(module for _name, module in modules),
    )


def _teacher_capture(
    context: RunContext,
    tokenized: Any,
) -> tuple[Any, tuple[Any, ...]]:
    adapter_module = importlib.import_module(
        "mineocclude.models.mineworld_adapter"
    )
    hooks = importlib.import_module("mineocclude.activations.hooks")
    wave4 = importlib.import_module(
        "mineocclude.models._mineworld_adapter_wave4"
    )
    holder: dict[str, Any] = {}

    def factory(modules: tuple[tuple[str, object], ...]) -> Any:
        manager = hooks.ScopedHookManager(_discovery_from_modules(modules))
        holder["manager"] = manager
        return manager

    result = context.state["adapter"].teacher_forced(
        adapter_module.TeacherForcedRequest(
            runtime_identity=context.state["runtime"],
            trajectory=tokenized,
            seed=context.arguments.seed,
            precision=context.arguments.precision,
            batch_size=1,
            hook_context_factory=factory,
            expected_adapter_code_sha256=(
                wave4._adapter_code_identity().sha256
            ),
            accepted_manifest_sha256=C_CAPTURE_PACKAGE_SHA256,
        )
    )
    manager = holder.get("manager")
    if manager is None or not manager.closed:
        _fail(
            "hook_cleanup_failed",
            "scoped hook manager did not close",
            step="6.4",
        )
    captures = manager.require_complete()
    return result, tuple(captures[index] for index in FROZEN_PHASE6_LAYERS)


def _capture_mapping(captures: Sequence[Any]) -> dict[int, Any]:
    return {
        capture.layer.layer_idx: capture
        for capture in captures
    }


def _candidate_vectors_equal(
    first: Sequence[Any],
    second: Sequence[Any],
) -> tuple[bool, float]:
    torch = importlib.import_module("torch")
    if len(first) != len(second):
        return False, float("inf")
    maximum = 0.0
    for left, right in zip(first, second, strict=True):
        if left.key != right.key:
            return False, float("inf")
        difference = float((left.vector - right.vector).abs().max().item())
        maximum = max(maximum, difference)
        if not torch.allclose(
            left.vector,
            right.vector,
            rtol=1e-3,
            atol=1e-3,
        ):
            return False, maximum
    return True, maximum


def step6_4_extract_store(context: RunContext) -> dict[str, Any]:
    """Teacher-force twice, pool verified visual tokens, and publish v2."""

    store_v1 = importlib.import_module("mineocclude.activations.store")
    torch = importlib.import_module("torch")
    numpy = importlib.import_module("numpy")
    frame_map_rows = context.state["streams"]["frame_map"]
    state_rows = context.state["streams"]["server_state"]
    source_bindings = build_source_frame_bindings_v2(
        trajectory_id=SELECTED_PILOT,
        frame_map_rows=frame_map_rows,
        state_rows=state_rows,
        c_frame_map_sha256=C_FRAME_MAP_SHA256,
        c_state_sha256=C_STATE_SHA256,
    )
    current_commit = _run_git(
        context.arguments.repository_root,
        "rev-parse",
        "HEAD",
    )
    identity = ActivationStoreIdentityV2(
        schema_version="1.0",
        format_version=ACTIVATION_STORE_V2_FORMAT_VERSION,
        run_id=context.arguments.session_id,
        checkpoint_hash=MAIN_CHECKPOINT_SHA256,
        model_hash=MAIN_CHECKPOINT_SHA256,
        config_hash=PHASE6_CONFIG_HASH,
        preprocess_hash=PREPROCESS_HASH,
        accepted_manifest_hash=C_CAPTURE_PACKAGE_SHA256,
        code_sha=str(current_commit),
        hook_site=HOOK_SITE,
        requested_layers=FROZEN_PHASE6_LAYERS,
        dtype="float32",
        hidden_width=HIDDEN_WIDTH,
    )
    rows_by_layer: dict[int, list[dict[str, Any]]] = {
        layer: [] for layer in FROZEN_PHASE6_LAYERS
    }
    vectors_by_layer: dict[int, list[Any]] = {
        layer: [] for layer in FROZEN_PHASE6_LAYERS
    }
    repeat_maximum = 0.0
    limited_unpooled = None
    for window_index, tokenized in enumerate(
        context.state["tokenized_windows"]
    ):
        first_result, first_captures = _teacher_capture(context, tokenized)
        second_result, second_captures = _teacher_capture(context, tokenized)
        first_candidates = store_v1.extract_complete_pooled_context(
            captures=_capture_mapping(first_captures),
            frame_token_map=tokenized.frame_token_map,
            hook_site=HOOK_SITE,
        )
        second_candidates = store_v1.extract_complete_pooled_context(
            captures=_capture_mapping(second_captures),
            frame_token_map=tokenized.frame_token_map,
            hook_site=HOOK_SITE,
        )
        equal, maximum = _candidate_vectors_equal(
            first_candidates,
            second_candidates,
        )
        repeat_maximum = max(repeat_maximum, maximum)
        if (
            not equal
            or first_result.output_sha256 != second_result.output_sha256
        ):
            _fail(
                "repeatability_failed",
                f"context {window_index} repeated extraction differs",
                step="6.4",
            )
        for candidate in first_candidates:
            global_idx = candidate.model_frame_idx
            source = source_bindings[global_idx]
            rows_by_layer[candidate.layer_idx].append(
                candidate_row_from_frame_token_span_v2(
                    store_identity=identity,
                    source_identity=source,
                    frame_token_map=tokenized.frame_token_map,
                    frame_token_map_sha256=(
                        tokenized.frame_token_map_sha256
                    ),
                    layer_idx=candidate.layer_idx,
                )
            )
            vectors_by_layer[candidate.layer_idx].append(candidate.vector)
        if window_index == 0:
            selection_module = importlib.import_module(
                "mineocclude.activations.pool"
            )
            span = tokenized.frame_token_map.spans[0]
            selection = selection_module.select_visual_token_positions(
                tokenized.frame_token_map,
                trajectory_id=span.identity.trajectory_id,
                model_frame_idx=span.identity.model_frame_idx,
                hooked_sequence_length=tokenized.frame_token_map.sequence_length,
            )
            runtime = context.state["runtime"]
            bounded_audit_root = context.session_root / "bounded_audit"
            bounded_audit_root.mkdir()
            limited_unpooled = store_v1.write_limited_unpooled_pilot(
                captures=_capture_mapping(first_captures),
                frame_token_map=tokenized.frame_token_map,
                selection=selection,
                pooled_candidates=first_candidates,
                identity=store_v1.UnpooledPilotIdentity(
                    session_id=context.arguments.session_id,
                    trajectory_id=SELECTED_PILOT,
                    model_frame_idx=span.identity.model_frame_idx,
                    hook_site=HOOK_SITE,
                    frame_token_map_sha256=tokenized.frame_token_map_sha256,
                    mineocclude_revision=runtime.mineocclude_revision,
                    mineworld_revision=runtime.mineworld_source_revision,
                    asset_revision=runtime.modelscope_asset_revision,
                    model_config_sha256=MODEL_CONFIG_GIT_BLOB_SHA256,
                    main_checkpoint_sha256=MAIN_CHECKPOINT_SHA256,
                    vae_config_sha256=VAE_CONFIG_SHA256,
                    vae_checkpoint_sha256=VAE_CHECKPOINT_SHA256,
                    environment_report_sha256=_sha256_file(
                        context.session_root
                        / "runtime_preflight_receipt.json"
                    ),
                    preprocessing_profile=runtime.preprocessing_identity,
                    action_conversion_profile=(
                        runtime.action_conversion_identity
                    ),
                    tokenization_profile=tokenized.tokenization_profile,
                    accepted_trajectory_package_sha256=(
                        C_CAPTURE_PACKAGE_SHA256
                    ),
                    input_mp4_sha256=_sha256_file(
                        context.state["input_paths"]["media"]
                    ),
                ),
                output_directory=bounded_audit_root,
                artifact_stem="limited_unpooled_frame_0",
                enabled=True,
            )
        del first_candidates, second_candidates
        del first_captures, second_captures
        torch.cuda.empty_cache()
    store_root = context.arguments.approved_output_root / (
        f"{context.arguments.session_id}-activation-store-v2"
    )
    if store_root.exists() or store_root.is_symlink():
        _fail(
            "output_exists",
            "immutable activation store already exists",
            step="6.4",
        )
    store_root.mkdir()
    snapshot: ActivationIndexSnapshotV2 | None = None
    creation_timestamp = time.strftime(
        "%Y-%m-%dT%H:%M:%SZ",
        time.gmtime(),
    )
    for layer in FROZEN_PHASE6_LAYERS:
        rows = rows_by_layer[layer]
        vectors = numpy.stack(
            [
                vector.detach().cpu().contiguous().numpy()
                for vector in vectors_by_layer[layer]
            ],
            axis=0,
        ).astype(numpy.float32, copy=False)
        snapshot = publish_activation_chunk_v2(
            store_root=store_root,
            store_identity=identity,
            source_bindings=source_bindings,
            rows=rows,
            vectors=vectors,
            creation_timestamp=creation_timestamp,
            prior_snapshot=snapshot,
        )
    if snapshot is None or len(snapshot.index_rows) != EXPECTED_ACTIVATION_ROW_COUNT:
        _fail(
            "activation_cardinality_mismatch",
            "v2 publication did not produce exactly 4960 rows",
            step="6.4",
        )
    validate_activation_index_snapshot_v2(
        snapshot,
        store_root=store_root,
        source_bindings=source_bindings,
    )
    context.state.update(
        {
            "activation_snapshot": snapshot,
            "activation_store_identity": identity,
            "activation_store_root": store_root,
            "source_bindings": source_bindings,
            "repeatability_maximum_absolute_difference": repeat_maximum,
        }
    )
    return {
        "activation_index_path": str(store_root / snapshot.relative_path),
        "activation_row_count": len(snapshot.index_rows),
        "activation_store_format_version": ACTIVATION_STORE_V2_FORMAT_VERSION,
        "bounded_unpooled_artifact": (
            None
            if limited_unpooled is None
            else {
                "artifact_path": str(limited_unpooled.artifact_path),
                "artifact_sha256": limited_unpooled.artifact_sha256,
                "manifest_path": str(limited_unpooled.manifest_path),
                "manifest_sha256": limited_unpooled.manifest_sha256,
            }
        ),
        "chunk_count": len(snapshot.chunks),
        "repeatability_maximum_absolute_difference": repeat_maximum,
        "status": "PASS",
        "store_identity_digest": identity.digest,
    }


def step6_5_certify(context: RunContext) -> dict[str, Any]:
    """Certify pooling repeatability and exact C source identity joins."""

    snapshot = context.state["activation_snapshot"]
    sources = context.state["source_bindings"]
    validate_activation_index_snapshot_v2(
        snapshot,
        store_root=context.state["activation_store_root"],
        source_bindings=sources,
    )
    frame_layers: dict[int, set[int]] = {}
    source_join_failures = 0
    physical_keys = set()
    scientific_keys = set()
    for row in snapshot.index_rows:
        frame_layers.setdefault(
            int(row["global_model_frame_idx"]),
            set(),
        ).add(int(row["layer_idx"]))
        source = sources[int(row["global_model_frame_idx"])]
        if (
            row["source_frame_id"] != source.source_frame_id
            or row["source_tick"] != source.source_tick
            or row["c_frame_map_row_sha256"]
            != source.c_frame_map_row_sha256
            or row["c_state_row_sha256"] != source.c_state_row_sha256
        ):
            source_join_failures += 1
        scientific = (
            row["trajectory_id"],
            row["global_model_frame_idx"],
            row["source_frame_id"],
            row["source_tick"],
            row["layer_idx"],
            row["hook_site"],
            row["checkpoint_hash"],
            row["preprocess_hash"],
            row["run_id"],
        )
        physical = (
            *scientific,
            row["activation_chunk_id"],
            row["chunk_row_idx"],
        )
        scientific_keys.add(scientific)
        physical_keys.add(physical)
    if (
        source_join_failures
        or len(frame_layers) != GLOBAL_MODEL_FRAME_COUNT
        or any(
            layers != set(FROZEN_PHASE6_LAYERS)
            for layers in frame_layers.values()
        )
        or len(scientific_keys) != EXPECTED_ACTIVATION_ROW_COUNT
        or len(physical_keys) != EXPECTED_ACTIVATION_ROW_COUNT
    ):
        _fail(
            "certification_failed",
            "pooling/index/source identity certification failed",
            step="6.5",
        )
    return {
        "activation_key_collision_count": 0,
        "activation_row_count": len(snapshot.index_rows),
        "direct_pooling_audit": "PASS",
        "global_model_frame_count": len(frame_layers),
        "repeatability_maximum_absolute_difference": context.state[
            "repeatability_maximum_absolute_difference"
        ],
        "source_identity_join_failure_count": source_join_failures,
        "status": "PASS",
    }


def _prepare_step6_6_handoff(context: RunContext) -> dict[str, Any]:
    snapshot = context.state["activation_snapshot"]
    store_root = context.state["activation_store_root"]
    artifacts = []
    for chunk in snapshot.chunks:
        artifacts.append(
            {
                "byte_size": chunk.byte_size,
                "path": str(store_root / chunk.path),
                "sha256": chunk.sha256,
                "type": "activation_chunk",
            }
        )
    index_path = store_root / snapshot.relative_path
    artifacts.append(
        {
            "byte_size": index_path.stat().st_size,
            "path": str(index_path),
            "sha256": _sha256_file(index_path),
            "type": "activation_index",
        }
    )
    handoff = {
        "artifacts": artifacts,
        "expected_activation_row_count": EXPECTED_ACTIVATION_ROW_COUNT,
        "person_e_registry_v2_validator_commit": (
            PERSON_E_REGISTRY_V2_VALIDATOR
        ),
        "registry_v2_acceptance_claimed": False,
        "runner_version": RUNNER_VERSION,
        "schema_version": "1.0",
        "scientific_use_acceptance_claimed": False,
        "selected_pilot": SELECTED_PILOT,
        "status": "HANDOFF_PREPARED_NOT_ACCEPTED",
        "step": "6.6_handoff_preparation_only",
    }
    _write_json(context.session_root / "step6_6_handoff.json", handoff)
    return handoff


StepHandler = Callable[[RunContext], Mapping[str, Any]]


def execute_step_sequence(
    context: RunContext,
    handlers: Mapping[str, StepHandler],
) -> dict[str, Any]:
    """Execute hard gates in order and never continue after a failure."""

    completed: list[str] = []
    failed_step: str | None = None
    failure: dict[str, Any] | None = None
    for step in PHASE6_STEPS:
        if step not in handlers:
            _fail(
                "missing_step_handler",
                f"no handler exists for Step {step}",
                step=step,
            )
        started = time.perf_counter()
        try:
            result = dict(handlers[step](context))
            if result.get("status") != "PASS":
                _fail(
                    "step_gate_failed",
                    f"Step {step} did not emit status PASS",
                    step=step,
                )
            receipt = {
                "elapsed_seconds": time.perf_counter() - started,
                "result": result,
                "status": "PASS",
                "step": step,
            }
            context.step_receipts.append(receipt)
            completed.append(step)
            _write_json(
                context.session_root / f"step{step.replace('.', '_')}.json",
                receipt,
            )
        except BaseException as error:  # noqa: BLE001
            failed_step = step
            failure = {
                "exception_message": str(error),
                "exception_type": type(error).__name__,
                "status": "FAIL",
                "step": step,
                "traceback": traceback.format_exc(),
            }
            break
    return {
        "completed_steps": completed,
        "failed_step": failed_step,
        "failure": failure,
        "later_steps_executed_after_failure": False,
        "status": "PASS" if failed_step is None else "FAIL",
    }


def _final_report(
    context: RunContext,
    sequence: Mapping[str, Any],
    handoff: Mapping[str, Any] | None,
) -> dict[str, Any]:
    return {
        "activation_store_format_version": ACTIVATION_STORE_V2_FORMAT_VERSION,
        "b_activation_store_v2_ratification": context.runtime_receipt[
            "b_activation_store_v2_ratification"
        ],
        "deterministic_seed": context.arguments.seed,
        "device": context.arguments.device,
        "expected_activation_row_count": EXPECTED_ACTIVATION_ROW_COUNT,
        "global_model_frame_count": GLOBAL_MODEL_FRAME_COUNT,
        "handoff": None if handoff is None else dict(handoff),
        "runner_version": RUNNER_VERSION,
        "scientific_execution_environment": "aws_sagemaker_linux_gpu",
        "selected_pilot": SELECTED_PILOT,
        "sequence": dict(sequence),
        "status": sequence["status"],
        "step_receipts": context.step_receipts,
    }


def run(arguments: RunnerArguments) -> int:
    """Execute the authorized one-pilot workflow on SageMaker only."""

    receipt = runtime_preflight(arguments)
    session_root = arguments.approved_output_root / arguments.session_id
    if session_root.exists() or session_root.is_symlink():
        _fail(
            "output_exists",
            "immutable run session directory already exists",
            step="preflight",
        )
    session_root.mkdir()
    _write_json(session_root / "runtime_preflight_receipt.json", receipt)
    context = RunContext(
        arguments=arguments,
        session_root=session_root,
        runtime_receipt=receipt,
    )
    sequence = execute_step_sequence(
        context,
        {
            "6.1": step6_1_intake,
            "6.2": step6_2_model_boundary,
            "6.3": step6_3_tokenize,
            "6.4": step6_4_extract_store,
            "6.5": step6_5_certify,
        },
    )
    handoff = (
        _prepare_step6_6_handoff(context)
        if sequence["status"] == "PASS"
        else None
    )
    report = _final_report(context, sequence, handoff)
    _write_json(session_root / "final_report.json", report)
    print(json.dumps(report, sort_keys=True, allow_nan=False))
    return 0 if sequence["status"] == "PASS" else 1


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="operation", required=True)
    subparsers.add_parser(
        "plan",
        help="print the preparation-only plan; imports no torch and queries no CUDA",
    )
    execute = subparsers.add_parser(
        "run",
        help="execute once in the ratified SageMaker Linux GPU environment",
    )
    execute.add_argument("--repository-root", type=Path, default=ROOT)
    execute.add_argument("--mineworld-root", type=Path, required=True)
    execute.add_argument("--asset-root", type=Path, required=True)
    execute.add_argument("--main-checkpoint", type=Path, required=True)
    execute.add_argument("--vae-config", type=Path, required=True)
    execute.add_argument("--vae-checkpoint", type=Path, required=True)
    execute.add_argument("--approved-input-root", type=Path, required=True)
    execute.add_argument("--approved-output-root", type=Path, required=True)
    execute.add_argument(
        "--activation-store-v2-ratification-object",
        default=os.environ.get(
            "PERSON_B_ACTIVATION_STORE_V2_RATIFICATION_OBJECT",
            "",
        ),
    )
    execute.add_argument(
        "--session-id",
        default="person-a-phase6-layout-00-ep9403-seed-20260725",
    )
    execute.add_argument("--seed", type=int, default=DETERMINISTIC_SEED)
    execute.add_argument("--device", default=REQUIRED_DEVICE)
    execute.add_argument(
        "--precision",
        choices=("float16",),
        default="float16",
    )
    return parser


def _arguments(namespace: argparse.Namespace) -> RunnerArguments:
    return RunnerArguments(
        repository_root=namespace.repository_root.resolve(),
        mineworld_root=namespace.mineworld_root.resolve(),
        asset_root=namespace.asset_root.resolve(),
        main_checkpoint=namespace.main_checkpoint.resolve(),
        vae_config=namespace.vae_config.resolve(),
        vae_checkpoint=namespace.vae_checkpoint.resolve(),
        approved_input_root=namespace.approved_input_root.resolve(),
        approved_output_root=namespace.approved_output_root.resolve(),
        activation_store_v2_ratification_object=(
            namespace.activation_store_v2_ratification_object
        ),
        session_id=namespace.session_id,
        seed=namespace.seed,
        device=namespace.device,
        precision=namespace.precision,
    )


def main(argv: list[str] | None = None) -> int:
    namespace = _parser().parse_args(argv)
    if namespace.operation == "plan":
        print(json.dumps(plan_document(), sort_keys=True, allow_nan=False))
        return 0
    try:
        return run(_arguments(namespace))
    except BaseException as error:  # noqa: BLE001
        report = {
            "exception_message": str(error),
            "exception_type": type(error).__name__,
            "runner_version": RUNNER_VERSION,
            "status": "FAIL",
            "traceback": traceback.format_exc(),
        }
        print(json.dumps(report, sort_keys=True, allow_nan=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
