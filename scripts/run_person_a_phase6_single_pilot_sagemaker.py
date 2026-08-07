#!/usr/bin/env python3
"""Fail-closed one-pilot GPU runner for Person A Phase 6.

Importing this module and using ``plan`` perform no CUDA query, model load,
media decode, or scientific operation. ``run`` preserves the ratified Linux
pilot and adds the manifest-bound canonical Windows CUDA successor; both
execute Steps 6.1 through 6.5 in order.
"""

from __future__ import annotations

import argparse
import contextlib
import dataclasses
import hashlib
import importlib
import json
import math
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

RUNNER_VERSION = "person-a-phase6-single-pilot-sagemaker-runner-v0.4"
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
EXPECTED_SAGEMAKER_REPOSITORY_ROOT = Path("/home/sagemaker-user/MineOcclude")
EXPECTED_SAGEMAKER_ASSET_ROOT = Path("/home/sagemaker-user/MineWorld-Assets-Pinned")
EXPECTED_SAGEMAKER_INPUT_ROOT = Path(
    "/home/sagemaker-user/person-a-phase6-approved-inputs"
)
EXPECTED_SAGEMAKER_OUTPUT_ROOT = Path(
    "/home/sagemaker-user/person-a-phase6-approved-outputs"
)
EXPECTED_SAGEMAKER_FFMPEG = Path("/home/sagemaker-user/tools/ffmpeg/bin/ffmpeg")
EXPECTED_SAGEMAKER_FFPROBE = Path("/home/sagemaker-user/tools/ffmpeg/bin/ffprobe")
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

HISTORICAL_RUNTIME_HOST = "aws_sagemaker_linux_gpu"
CANONICAL_WINDOWS_RUNTIME_HOST = "windows_cuda"
CANONICAL_SAGEMAKER_BUNDLE_SCHEMA = (
    "person-a-canonical-sagemaker-input-bundle-v0.1"
)
CANONICAL_C6A_ID = "person-c-c6a-post-c1-v0.1"
CANONICAL_PERSON_C_COMMIT = "b810bae554ba4f31018d39beb304c9b936387ca4"
CANONICAL_PERSON_E_COMMIT = "d76f2df885d6b0e2e6cc5ade7025e799030ecea1"
CANONICAL_GEOMETRY_VERSION = "person-c-layout-config-v0.4"
CANONICAL_GEOMETRY_SHA256 = (
    "34495d650d6a8c62b00a916796c90389b48f80d8f20a23eac93207758e993f5d"
)
CANONICAL_SELECTION_RULE = (
    "LOWEST_EPISODE_ID_SATISFYING_ALL_REPOSITORY_REQUIRED_"
    "VISIBLE_POSITION_POSITIVE_CONTROL_CONDITIONS"
)
CANONICAL_CONDITION_ROLE = "no_wall_visible_control"
CANONICAL_GROUPING_KEY = "layout_id"
CANONICAL_POOLING_METHOD = "mean"
CANONICAL_TOKEN_REGION = "visual"
CANONICAL_ACTION_CONVERSION_IDENTITY = (
    "mineworld_mcdataset_json_action_to_env_action@1.0:"
    "7e8d16db01f085481d41d340e5a0b84669b8e163f3338d5fd572731532c52746"
)
CANONICAL_PREPROCESSING_IDENTITY = (
    "mineworld_gradio_step_video_preprocessing@1.0:"
    "036fa0b4899285e5499f88581f6e02426a25f732fcc26bd63c0f5b3863a9d9ab"
)
CANONICAL_IMPULSE_ORIENTATION = {
    "camera_component_0_observed_effect": "runtime_no_component_0_effect",
    "camera_component_1_observed_effect": (
        "runtime_positive_component_1_step_in_visual_i_to_i_plus_1"
    ),
    "evidence_hash": (
        "9b8d58c383cee1e37de0119acd23794719d1892d14e2186c3e0585e6769a3914"
    ),
    "evidence_scope": "frozen_person_a_runtime_scripted_impulse",
    "fixture_id": "runtime_scripted_impulse",
    "status": "verified",
}


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


def _git_commit_is_ancestor(repository: Path, revision: str) -> bool:
    """Accept additive authority receipts without weakening the pinned source."""

    result = subprocess.run(
        [
            "git",
            "-C",
            str(repository),
            "merge-base",
            "--is-ancestor",
            revision,
            "HEAD",
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
    runtime_host: str = HISTORICAL_RUNTIME_HOST
    canonical_c6a_package: Path | None = None
    canonical_c6a_package_sha256: str = ""
    trajectory_id: str = SELECTED_PILOT
    episode_id: int | None = None
    episode_artifact_manifest: Path | None = None
    episode_artifact_manifest_sha256: str = ""
    person_e_provenance_handoff: Path | None = None
    person_e_provenance_handoff_sha256: str = ""
    expected_model_config_sha256: str = MODEL_CONFIG_GIT_BLOB_SHA256
    expected_main_checkpoint_sha256: str = MAIN_CHECKPOINT_SHA256
    expected_vae_config_sha256: str = VAE_CONFIG_SHA256
    expected_vae_checkpoint_sha256: str = VAE_CHECKPOINT_SHA256
    expected_preprocessing_identity: str = CANONICAL_PREPROCESSING_IDENTITY
    expected_action_conversion_identity: str = (
        CANONICAL_ACTION_CONVERSION_IDENTITY
    )
    expected_hook_site: str = HOOK_SITE
    expected_pooling_method: str = CANONICAL_POOLING_METHOD
    expected_token_region: str = CANONICAL_TOKEN_REGION
    expected_activation_store_format: str = ACTIVATION_STORE_V2_FORMAT_VERSION
    expected_activation_index_format: str = ACTIVATION_INDEX_V2_FORMAT_VERSION
    ffmpeg: Path | None = None
    ffprobe: Path | None = None
    canonical_input_bundle_manifest: Path | None = None
    canonical_input_bundle_manifest_sha256: str = ""

    @property
    def canonical_mode(self) -> bool:
        return (
            self.canonical_c6a_package is not None
            or self.canonical_input_bundle_manifest is not None
        )

    @property
    def staged_canonical_mode(self) -> bool:
        return self.canonical_input_bundle_manifest is not None


@dataclass(frozen=True)
class CanonicalPilotBinding:
    """Validated, read-only post-C1 C6A and Person E pilot authority."""

    canonical_c6a_id: str
    trajectory_id: str
    episode_id: int
    layout_id: str
    frame_count: int
    package_path: Path
    package_sha256: str
    person_c_commit: str
    person_e_handoff_path: Path
    person_e_handoff_sha256: str
    person_e_commit: str
    artifact_manifest_path: Path
    artifact_manifest_sha256: str
    registry_record_id: str
    registry_record_sha256: str
    capture_row: Mapping[str, Any]
    inventory_row: Mapping[str, Any]
    registry_record: Mapping[str, Any]
    direct_artifacts: tuple[Mapping[str, Any], ...]
    direct_paths: Mapping[str, Path]
    direct_hashes: Mapping[str, str]
    frame_paths: tuple[Path, ...]
    frame_hashes: tuple[str, ...]
    client_tick_rows: tuple[Mapping[str, Any], ...]
    raw_action_rows: tuple[Mapping[str, Any], ...]
    state_rows: tuple[Mapping[str, Any], ...]

    @property
    def expected_activation_rows(self) -> int:
        return self.frame_count * len(FROZEN_PHASE6_LAYERS)


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


def _require_sha256(value: object, label: str, *, step: str = "preflight") -> str:
    if not isinstance(value, str) or len(value) != 64:
        _fail("invalid_identity", f"{label} must be one SHA-256", step=step)
    try:
        int(value, 16)
    except ValueError:
        _fail("invalid_identity", f"{label} must be hexadecimal", step=step)
    return value.lower()


def _read_json_object(path: Path, label: str) -> dict[str, Any]:
    if not path.is_absolute() or not path.is_file() or path.is_symlink():
        _fail(
            "invalid_path",
            f"{label} must be an existing absolute ordinary file",
            step="preflight",
        )
    try:
        document = json.loads(path.read_bytes())
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        _fail("invalid_json", f"{label} is not valid JSON: {error}", step="preflight")
    if not isinstance(document, dict):
        _fail("invalid_json", f"{label} must contain one JSON object", step="preflight")
    return document


def _repository_root_for(path: Path, label: str) -> Path:
    result = _run_git(path.parent, "rev-parse", "--show-toplevel", check=False)
    if not result:
        _fail(
            "authority_repository_missing",
            f"{label} is not inside a Git worktree",
            step="preflight",
        )
    return Path(str(result)).resolve()


def _component_path(
    package: Mapping[str, Any],
    repository: Path,
    suffix: str,
) -> Path:
    rows = package.get("component_files")
    if not isinstance(rows, list):
        _fail("invalid_c6a_package", "component_files must be a list", step="preflight")
    matches = [
        row
        for row in rows
        if isinstance(row, Mapping) and str(row.get("path", "")).endswith(suffix)
    ]
    if len(matches) != 1:
        _fail(
            "invalid_c6a_package",
            f"package must name exactly one {suffix}",
            step="preflight",
        )
    row = matches[0]
    path = repository / str(row["path"]).replace("/", os.sep)
    if (
        not path.is_file()
        or path.is_symlink()
        or path.stat().st_size != row.get("size_bytes")
        or _sha256_file(path) != row.get("sha256")
    ):
        _fail(
            "c6a_component_identity_mismatch",
            f"C6A component identity differs: {suffix}",
            step="preflight",
        )
    return path


def _validate_component_inventory(
    package: Mapping[str, Any], repository: Path
) -> None:
    rows = package.get("component_files")
    if not isinstance(rows, list) or not rows:
        _fail("invalid_c6a_package", "component_files must be non-empty", step="preflight")
    for position, row in enumerate(rows):
        if not isinstance(row, Mapping):
            _fail(
                "invalid_c6a_package",
                f"component_files[{position}] must be a mapping",
                step="preflight",
            )
        path = repository / str(row.get("path", "")).replace("/", os.sep)
        if (
            not path.is_file()
            or path.is_symlink()
            or path.stat().st_size != row.get("size_bytes")
            or _sha256_file(path) != row.get("sha256")
        ):
            _fail(
                "c6a_component_identity_mismatch",
                f"C6A component identity differs: {row.get('path')!r}",
                step="preflight",
            )


def _artifact_key(row: Mapping[str, Any]) -> tuple[str, str]:
    return str(row.get("side", "")), str(row.get("relative_path", ""))


def _validate_direct_artifact(row: Mapping[str, Any]) -> Path:
    path = Path(str(row.get("path", ""))).resolve()
    expected_hash = _require_sha256(row.get("sha256"), "episode artifact sha256")
    if (
        not path.is_absolute()
        or not path.is_file()
        or path.is_symlink()
        or path.stat().st_size != row.get("size_bytes")
        or _sha256_file(path) != expected_hash
    ):
        _fail(
            "episode_artifact_identity_mismatch",
            f"episode artifact bytes differ: {path}",
            step="preflight",
        )
    return path


def _staged_bundle_files(
    manifest_path: Path,
    manifest: Mapping[str, Any],
) -> dict[str, Path]:
    bundle_root = manifest_path.parent.resolve()
    rows = manifest.get("files")
    if not isinstance(rows, list) or not rows:
        _fail("invalid_input_bundle", "bundle files must be non-empty", step="preflight")
    resolved: dict[str, Path] = {}
    for position, row in enumerate(rows):
        if not isinstance(row, Mapping):
            _fail(
                "invalid_input_bundle",
                f"bundle files[{position}] must be a mapping",
                step="preflight",
            )
        relative = str(row.get("path", ""))
        path = (bundle_root / relative.replace("/", os.sep)).resolve()
        try:
            path.relative_to(bundle_root)
        except ValueError:
            _fail("invalid_input_bundle", "bundle path escapes its root", step="preflight")
        if (
            not relative
            or relative in resolved
            or not path.is_file()
            or path.is_symlink()
            or path.stat().st_size != row.get("size_bytes")
            or _sha256_file(path) != row.get("sha256")
        ):
            _fail(
                "input_bundle_file_mismatch",
                f"staged bundle file differs: {relative!r}",
                step="preflight",
            )
        resolved[relative] = path
    return resolved


def _staged_authority_path(
    authority: Mapping[str, Any],
    files: Mapping[str, Path],
    name: str,
) -> Path:
    descriptor = authority.get(name)
    if not isinstance(descriptor, Mapping):
        _fail("invalid_input_bundle", f"bundle authority {name} is missing", step="preflight")
    relative = str(descriptor.get("path", ""))
    path = files.get(relative)
    if path is None or _sha256_file(path) != descriptor.get("file_sha256"):
        _fail(
            "input_bundle_authority_mismatch",
            f"staged authority differs: {name}",
            step="preflight",
        )
    return path


def load_staged_canonical_pilot_binding(
    arguments: RunnerArguments,
) -> CanonicalPilotBinding:
    """Load one independently hashed, relocatable SageMaker input bundle."""

    assert arguments.canonical_input_bundle_manifest is not None
    manifest_path = arguments.canonical_input_bundle_manifest.resolve()
    manifest_hash = _require_sha256(
        arguments.canonical_input_bundle_manifest_sha256,
        "canonical input bundle manifest sha256",
    )
    if _sha256_file(manifest_path) != manifest_hash:
        _fail("input_bundle_hash_mismatch", "input bundle manifest differs", step="preflight")
    manifest = _read_json_object(manifest_path, "canonical SageMaker input bundle")
    if (
        manifest.get("schema_version") != CANONICAL_SAGEMAKER_BUNDLE_SCHEMA
        or manifest.get("status") != "IMMUTABLE_READY_FOR_SAGEMAKER"
        or manifest.get("canonical_c6a_id") != CANONICAL_C6A_ID
        or manifest.get("trajectory_id") != arguments.trajectory_id
        or manifest.get("episode_id") != arguments.episode_id
        or manifest.get("person_c_commit") != CANONICAL_PERSON_C_COMMIT
        or manifest.get("person_e_commit") != CANONICAL_PERSON_E_COMMIT
        or manifest.get("selection_rule") != CANONICAL_SELECTION_RULE
    ):
        _fail("invalid_input_bundle", "bundle identity fields differ", step="preflight")
    files = _staged_bundle_files(manifest_path, manifest)
    authority = manifest.get("authority")
    if not isinstance(authority, Mapping):
        _fail("invalid_input_bundle", "bundle authority is missing", step="preflight")
    package_path = _staged_authority_path(authority, files, "canonical_c6a_package")
    handoff_path = _staged_authority_path(authority, files, "person_e_handoff")
    registry_path = _staged_authority_path(authority, files, "episode_registry_record")
    capture_path = _staged_authority_path(authority, files, "capture_episode_record")
    inventory_path = _staged_authority_path(authority, files, "episode_inventory_record")
    package_hash = _require_sha256(
        arguments.canonical_c6a_package_sha256,
        "canonical C6A package sha256",
    )
    handoff_hash = _require_sha256(
        arguments.person_e_provenance_handoff_sha256,
        "Person E handoff sha256",
    )
    registry_hash = _require_sha256(
        arguments.episode_artifact_manifest_sha256,
        "episode artifact manifest sha256",
    )
    if (
        authority["canonical_c6a_package"].get("source_sha256") != package_hash
        or _sha256_file(package_path) != package_hash
        or authority["person_e_handoff"].get("source_sha256") != handoff_hash
        or _sha256_file(handoff_path) != handoff_hash
        or authority["episode_registry_record"].get("source_manifest_sha256")
        != registry_hash
    ):
        _fail("input_bundle_authority_mismatch", "source authority hashes differ", step="preflight")
    package = _read_json_object(package_path, "staged canonical C6A package")
    handoff = _read_json_object(handoff_path, "staged Person E handoff")
    record = _read_json_object(registry_path, "staged episode registry record")
    capture_row = _read_json_object(capture_path, "staged capture episode record")
    inventory_row = _read_json_object(inventory_path, "staged episode inventory record")
    registry_record_hash = str(
        authority["episode_registry_record"].get("registry_record_sha256", "")
    )
    if (
        package.get("canonical_c6a_id") != CANONICAL_C6A_ID
        or package.get("status") != "PASS"
        or package.get("immutable") is not True
        or handoff.get("canonical_c6a_id") != CANONICAL_C6A_ID
        or handoff.get("status") != "READY_FOR_A6_6_PROVENANCE_CONSUMPTION"
        or handoff.get("person_c_certification_commit") != CANONICAL_PERSON_C_COMMIT
        or handoff.get("person_c_c6a_package", {}).get("sha256") != package_hash
        or handoff.get("canonical_registry", {}).get("sha256") != registry_hash
        or _sha256_file(registry_path) != registry_record_hash
        or record.get("registry_record_id")
        != authority["episode_registry_record"].get("registry_record_id")
        or record.get("episode_id") != arguments.episode_id
        or capture_row.get("episode_id") != arguments.episode_id
        or inventory_row.get("episode_id") != arguments.episode_id
    ):
        _fail("input_bundle_authority_mismatch", "staged authority content differs", step="preflight")
    expected_layout = str(capture_row.get("layout_id", ""))
    if (
        arguments.trajectory_id != f"{expected_layout}_ep{arguments.episode_id}"
        or capture_row.get("scene") != "nowall"
        or capture_row.get("set") != "nowall"
        or capture_row.get("accepted_geometry_version") != CANONICAL_GEOMETRY_VERSION
        or capture_row.get("accepted_geometry_sha256") != CANONICAL_GEOMETRY_SHA256
        or inventory_row.get("status") != "PASS"
        or inventory_row.get("target_check_valid") is not True
        or inventory_row.get("target_expected_count") != 1
        or inventory_row.get("target_observed_count") != 1
        or record.get("layout_id") != expected_layout
        or record.get("record_status") != "accepted"
        or record.get("byte_hashes_valid") is not True
        or record.get("output_counts_valid") is not True
        or record.get("output_schemas_valid") is not True
    ):
        _fail("canonical_authority_mismatch", "staged selected pilot differs", step="preflight")
    direct_rows = manifest.get("direct_artifacts")
    if not isinstance(direct_rows, list) or len(direct_rows) != 67:
        _fail("episode_artifact_set_mismatch", "bundle must contain 67 artifacts", step="preflight")
    record_outputs = record.get("outputs")
    record_by_key = {
        _artifact_key(row): row
        for row in record_outputs
        if isinstance(row, Mapping)
    } if isinstance(record_outputs, list) else {}
    staged_by_key: dict[tuple[str, str], tuple[Mapping[str, Any], Path]] = {}
    for row in direct_rows:
        if not isinstance(row, Mapping) or not isinstance(row.get("source"), Mapping):
            _fail("invalid_input_bundle", "direct artifact descriptor differs", step="preflight")
        source = row["source"]
        key = _artifact_key(source)
        path = files.get(str(row.get("bundle_path", "")))
        if path is None or key in staged_by_key:
            _fail("episode_artifact_set_mismatch", "staged artifact key differs", step="preflight")
        expected = record_by_key.get(key)
        if expected is None or any(
            source.get(field) != expected.get(field)
            for field in ("path", "relative_path", "sha256", "side", "size_bytes")
        ) or path.stat().st_size != source.get("size_bytes") or _sha256_file(path) != source.get("sha256"):
            _fail("episode_artifact_identity_mismatch", f"staged artifact differs: {key}", step="preflight")
        staged_by_key[key] = (source, path)
    if set(staged_by_key) != set(record_by_key):
        _fail("episode_artifact_set_mismatch", "registry and staged sets differ", step="preflight")
    required = {
        ("client", "client_tick.jsonl"),
        ("client", "raw_actions.jsonl"),
        ("server", "server_state.jsonl"),
        ("server", "reset_result.json"),
    }
    if not required.issubset(staged_by_key):
        _fail("episode_artifact_set_mismatch", "required staged records are missing", step="preflight")
    frame_rows = sorted(
        (
            (int(Path(key[1]).stem), path, source)
            for key, (source, path) in staged_by_key.items()
            if key[0] == "client" and key[1].startswith("frames/")
        ),
        key=lambda item: item[0],
    )
    frame_count = int(inventory_row.get("frame_count", -1))
    if [index for index, _path, _row in frame_rows] != list(range(frame_count)):
        _fail("frame_identity_mismatch", "staged frame identities differ", step="preflight")
    direct_paths = {
        name: staged_by_key[key][1]
        for name, key in {
            "client_tick": ("client", "client_tick.jsonl"),
            "raw_actions": ("client", "raw_actions.jsonl"),
            "server_state": ("server", "server_state.jsonl"),
            "reset_result": ("server", "reset_result.json"),
        }.items()
    }
    client_rows = tuple(_json_lines(direct_paths["client_tick"].read_bytes(), label="client_tick"))
    action_rows = tuple(_json_lines(direct_paths["raw_actions"].read_bytes(), label="raw_actions"))
    state_rows = tuple(_json_lines(direct_paths["server_state"].read_bytes(), label="server_state"))
    if not (len(client_rows) == len(action_rows) == len(state_rows) == frame_count):
        _fail("source_cardinality_mismatch", "staged record counts differ", step="preflight")
    positions: list[float] = []
    for index, (client, action, state) in enumerate(zip(client_rows, action_rows, state_rows, strict=True)):
        if (
            client.get("episode_id") != arguments.episode_id
            or action.get("episode_id") != arguments.episode_id
            or state.get("episode_id") != arguments.episode_id
            or client.get("server_tick") != index
            or client.get("render_frame_idx") != index
            or action.get("server_tick") != index
            or action.get("render_frame_idx") != index
            or action.get("action_idx") != index
            or state.get("server_tick") != index
            or state.get("layout_id") != expected_layout
            or state.get("scene") != "NO_WALL"
            or state.get("geometric_visible") is not True
            or client.get("server_epoch_nanos") != state.get("server_epoch_nanos")
        ):
            _fail("source_identity_mismatch", f"staged row {index} does not join", step="preflight")
        position = state.get("axis_pos")
        if isinstance(position, bool) or not isinstance(position, (int, float)) or not math.isfinite(float(position)):
            _fail("visible_position_invalid", f"staged row {index} is invalid", step="preflight")
        positions.append(float(position))
    if max(positions) - min(positions) <= 0.0:
        _fail("visible_position_movement_missing", "staged movement is zero", step="preflight")
    direct_hashes = {
        name: str(staged_by_key[key][0]["sha256"])
        for name, key in {
            "client_tick": ("client", "client_tick.jsonl"),
            "raw_actions": ("client", "raw_actions.jsonl"),
            "server_state": ("server", "server_state.jsonl"),
            "reset_result": ("server", "reset_result.json"),
        }.items()
    }
    return CanonicalPilotBinding(
        canonical_c6a_id=CANONICAL_C6A_ID,
        trajectory_id=arguments.trajectory_id,
        episode_id=int(arguments.episode_id),
        layout_id=expected_layout,
        frame_count=frame_count,
        package_path=package_path,
        package_sha256=package_hash,
        person_c_commit=CANONICAL_PERSON_C_COMMIT,
        person_e_handoff_path=handoff_path,
        person_e_handoff_sha256=handoff_hash,
        person_e_commit=CANONICAL_PERSON_E_COMMIT,
        artifact_manifest_path=registry_path,
        artifact_manifest_sha256=registry_hash,
        registry_record_id=str(record["registry_record_id"]),
        registry_record_sha256=registry_record_hash,
        capture_row=capture_row,
        inventory_row=inventory_row,
        registry_record=record,
        direct_artifacts=tuple(dict(record_by_key[key]) for key in sorted(record_by_key)),
        direct_paths=direct_paths,
        direct_hashes=direct_hashes,
        frame_paths=tuple(path for _index, path, _row in frame_rows),
        frame_hashes=tuple(str(row["sha256"]) for _index, _path, row in frame_rows),
        client_tick_rows=client_rows,
        raw_action_rows=action_rows,
        state_rows=state_rows,
    )


def load_canonical_pilot_binding(arguments: RunnerArguments) -> CanonicalPilotBinding:
    """Validate the selected post-C1 C6A pilot without creating outputs."""

    if not arguments.canonical_mode:
        _fail("canonical_mode_required", "canonical package is required", step="preflight")
    if arguments.staged_canonical_mode:
        return load_staged_canonical_pilot_binding(arguments)
    assert arguments.canonical_c6a_package is not None
    assert arguments.episode_artifact_manifest is not None
    assert arguments.person_e_provenance_handoff is not None

    package_path = arguments.canonical_c6a_package.resolve()
    package_hash = _require_sha256(
        arguments.canonical_c6a_package_sha256,
        "canonical C6A package sha256",
    )
    if _sha256_file(package_path) != package_hash:
        _fail("c6a_package_hash_mismatch", "canonical C6A package differs", step="preflight")
    package = _read_json_object(package_path, "canonical C6A package")
    if (
        package.get("canonical_c6a_id") != CANONICAL_C6A_ID
        or package.get("status") != "PASS"
        or package.get("immutable") is not True
        or package.get("required_episode_count") != 66
        or package.get("completed_episode_count") != 66
    ):
        _fail("invalid_c6a_package", "canonical C6A completion fields differ", step="preflight")
    c_repository = _repository_root_for(package_path, "canonical C6A package")
    if not _git_commit_is_ancestor(c_repository, CANONICAL_PERSON_C_COMMIT):
        _fail(
            "person_c_commit_mismatch",
            "Person C worktree lacks the canonical authority ancestry",
            step="preflight",
        )
    _validate_component_inventory(package, c_repository)

    capture_descriptor = package.get("capture_manifest")
    if not isinstance(capture_descriptor, Mapping):
        _fail("invalid_c6a_package", "capture_manifest descriptor is missing", step="preflight")
    capture_path = c_repository / str(capture_descriptor.get("path", "")).replace("/", os.sep)
    if (
        not capture_path.is_file()
        or capture_path.stat().st_size != capture_descriptor.get("size_bytes")
        or _sha256_file(capture_path) != capture_descriptor.get("sha256")
    ):
        _fail("c6a_capture_manifest_mismatch", "capture manifest differs", step="preflight")
    capture = _read_json_object(capture_path.resolve(), "C6A capture manifest")
    capture_rows = capture.get("episodes")
    matches = [
        row
        for row in capture_rows if isinstance(row, Mapping)
        and row.get("episode_id") == arguments.episode_id
    ] if isinstance(capture_rows, list) else []
    if len(matches) != 1:
        _fail("episode_identity_mismatch", "capture manifest episode is not unique", step="preflight")
    capture_row = matches[0]

    inventory_path = _component_path(package, c_repository, "episode_inventory.json")
    output_path = _component_path(package, c_repository, "output_inventory.json")
    inventory = _read_json_object(inventory_path.resolve(), "C6A episode inventory")
    output = _read_json_object(output_path.resolve(), "C6A output inventory")
    inventory_rows = inventory.get("episodes")
    inventory_matches = [
        row
        for row in inventory_rows if isinstance(row, Mapping)
        and row.get("episode_id") == arguments.episode_id
    ] if isinstance(inventory_rows, list) else []
    if len(inventory_matches) != 1:
        _fail("episode_identity_mismatch", "episode inventory row is not unique", step="preflight")
    inventory_row = inventory_matches[0]
    output_rows = output.get("files")
    c_artifacts = tuple(
        row for row in output_rows
        if isinstance(row, Mapping) and row.get("episode_id") == arguments.episode_id
    ) if isinstance(output_rows, list) else ()

    e_handoff_path = arguments.person_e_provenance_handoff.resolve()
    e_handoff_hash = _require_sha256(
        arguments.person_e_provenance_handoff_sha256,
        "Person E handoff sha256",
    )
    if _sha256_file(e_handoff_path) != e_handoff_hash:
        _fail("person_e_handoff_hash_mismatch", "Person E handoff differs", step="preflight")
    e_handoff = _read_json_object(e_handoff_path, "Person E provenance handoff")
    e_repository = _repository_root_for(e_handoff_path, "Person E provenance handoff")
    if not _git_commit_is_ancestor(e_repository, CANONICAL_PERSON_E_COMMIT):
        _fail(
            "person_e_commit_mismatch",
            "Person E worktree lacks the canonical authority ancestry",
            step="preflight",
        )

    artifact_manifest_path = arguments.episode_artifact_manifest.resolve()
    artifact_manifest_hash = _require_sha256(
        arguments.episode_artifact_manifest_sha256,
        "episode artifact manifest sha256",
    )
    if _sha256_file(artifact_manifest_path) != artifact_manifest_hash:
        _fail("artifact_manifest_hash_mismatch", "episode artifact manifest differs", step="preflight")
    registry = _read_json_object(artifact_manifest_path, "episode artifact manifest")
    records = registry.get("records")
    record_matches = [
        row for row in records
        if isinstance(row, Mapping) and row.get("episode_id") == arguments.episode_id
    ] if isinstance(records, list) else []
    if len(record_matches) != 1:
        _fail("episode_identity_mismatch", "E registry episode is not unique", step="preflight")
    record = record_matches[0]
    identities = e_handoff.get("canonical_registry", {}).get("record_identities", [])
    identity_matches = [
        row for row in identities
        if isinstance(row, Mapping) and row.get("episode_id") == arguments.episode_id
    ] if isinstance(identities, list) else []
    if len(identity_matches) != 1:
        _fail("episode_identity_mismatch", "E handoff episode identity is not unique", step="preflight")
    registry_identity = identity_matches[0]

    expected_layout = str(capture_row.get("layout_id", ""))
    expected_trajectory = f"{expected_layout}_ep{arguments.episode_id}"
    if (
        arguments.trajectory_id != expected_trajectory
        or capture_row.get("scene") != "nowall"
        or capture_row.get("set") != "nowall"
        or capture_row.get("accepted_geometry_version") != CANONICAL_GEOMETRY_VERSION
        or capture_row.get("accepted_geometry_sha256") != CANONICAL_GEOMETRY_SHA256
        or inventory_row.get("status") != "PASS"
        or inventory_row.get("target_check_valid") is not True
        or inventory_row.get("target_expected_count") != 1
        or inventory_row.get("target_observed_count") != 1
        or record.get("record_status") != "accepted"
        or record.get("byte_hashes_valid") is not True
        or record.get("output_counts_valid") is not True
        or record.get("output_schemas_valid") is not True
        or e_handoff.get("canonical_c6a_id") != CANONICAL_C6A_ID
        or e_handoff.get("status") != "READY_FOR_A6_6_PROVENANCE_CONSUMPTION"
        or e_handoff.get("person_c_certification_commit") != CANONICAL_PERSON_C_COMMIT
        or e_handoff.get("person_c_c6a_package", {}).get("sha256") != package_hash
        or e_handoff.get("canonical_registry", {}).get("sha256") != artifact_manifest_hash
        or registry_identity.get("registry_record_id") != record.get("registry_record_id")
    ):
        _fail(
            "canonical_authority_mismatch",
            "selected pilot, geometry, target, or provenance authority differs",
            step="preflight",
        )

    e_outputs = record.get("outputs")
    e_by_key = {
        _artifact_key(row): row
        for row in e_outputs if isinstance(row, Mapping)
    } if isinstance(e_outputs, list) else {}
    c_by_key = {_artifact_key(row): row for row in c_artifacts}
    if set(e_by_key) != set(c_by_key) or len(c_by_key) != len(c_artifacts):
        _fail("episode_artifact_set_mismatch", "C and E artifact sets differ", step="preflight")
    direct_paths_by_key: dict[tuple[str, str], Path] = {}
    for key, c_row in c_by_key.items():
        e_row = e_by_key[key]
        for field in ("path", "sha256", "size_bytes"):
            if c_row.get(field) != e_row.get(field):
                _fail(
                    "episode_artifact_identity_mismatch",
                    f"C and E differ for {key!r}.{field}",
                    step="preflight",
                )
        direct_paths_by_key[key] = _validate_direct_artifact(c_row)

    required_keys = {
        ("client", "client_tick.jsonl"),
        ("client", "raw_actions.jsonl"),
        ("server", "server_state.jsonl"),
        ("server", "reset_result.json"),
    }
    if not required_keys.issubset(direct_paths_by_key):
        _fail("episode_artifact_set_mismatch", "required episode records are missing", step="preflight")
    frame_rows = sorted(
        (
            (int(Path(relative).stem), direct_paths_by_key[(side, relative)], c_by_key[(side, relative)])
            for side, relative in direct_paths_by_key
            if side == "client" and relative.startswith("frames/")
        ),
        key=lambda item: item[0],
    )
    frame_count = int(inventory_row.get("frame_count", -1))
    if [index for index, _path, _row in frame_rows] != list(range(frame_count)):
        _fail("frame_identity_mismatch", "frame identities are not consecutive", step="preflight")

    client_tick_path = direct_paths_by_key[("client", "client_tick.jsonl")]
    raw_action_path = direct_paths_by_key[("client", "raw_actions.jsonl")]
    state_path = direct_paths_by_key[("server", "server_state.jsonl")]
    client_rows = tuple(_json_lines(client_tick_path.read_bytes(), label="client_tick"))
    action_rows = tuple(_json_lines(raw_action_path.read_bytes(), label="raw_actions"))
    state_rows = tuple(_json_lines(state_path.read_bytes(), label="server_state"))
    if not (len(client_rows) == len(action_rows) == len(state_rows) == frame_count):
        _fail("source_cardinality_mismatch", "episode record counts differ", step="preflight")
    positions: list[float] = []
    for index, (client, action, state) in enumerate(
        zip(client_rows, action_rows, state_rows, strict=True)
    ):
        if (
            client.get("episode_id") != arguments.episode_id
            or action.get("episode_id") != arguments.episode_id
            or state.get("episode_id") != arguments.episode_id
            or client.get("server_tick") != index
            or client.get("render_frame_idx") != index
            or action.get("server_tick") != index
            or action.get("render_frame_idx") != index
            or action.get("action_idx") != index
            or state.get("server_tick") != index
            or state.get("layout_id") != expected_layout
            or state.get("scene") != "NO_WALL"
            or state.get("geometric_visible") is not True
            or client.get("server_epoch_nanos") != state.get("server_epoch_nanos")
        ):
            _fail("source_identity_mismatch", f"source row {index} does not join exactly", step="preflight")
        position = state.get("axis_pos")
        if isinstance(position, bool) or not isinstance(position, (int, float)) or not math.isfinite(float(position)):
            _fail("visible_position_invalid", f"source row {index} lacks a finite label", step="preflight")
        positions.append(float(position))
    if max(positions) - min(positions) <= 0.0:
        _fail("visible_position_movement_missing", "wall-parallel movement is zero", step="preflight")

    direct_paths = {
        "client_tick": client_tick_path,
        "raw_actions": raw_action_path,
        "server_state": state_path,
        "reset_result": direct_paths_by_key[("server", "reset_result.json")],
    }
    direct_hashes = {
        name: str(c_by_key[key]["sha256"])
        for name, key in {
            "client_tick": ("client", "client_tick.jsonl"),
            "raw_actions": ("client", "raw_actions.jsonl"),
            "server_state": ("server", "server_state.jsonl"),
            "reset_result": ("server", "reset_result.json"),
        }.items()
    }
    return CanonicalPilotBinding(
        canonical_c6a_id=CANONICAL_C6A_ID,
        trajectory_id=arguments.trajectory_id,
        episode_id=int(arguments.episode_id),
        layout_id=expected_layout,
        frame_count=frame_count,
        package_path=package_path,
        package_sha256=package_hash,
        person_c_commit=CANONICAL_PERSON_C_COMMIT,
        person_e_handoff_path=e_handoff_path,
        person_e_handoff_sha256=e_handoff_hash,
        person_e_commit=CANONICAL_PERSON_E_COMMIT,
        artifact_manifest_path=artifact_manifest_path,
        artifact_manifest_sha256=artifact_manifest_hash,
        registry_record_id=str(record["registry_record_id"]),
        registry_record_sha256=str(registry_identity["registry_record_sha256"]),
        capture_row=dict(capture_row),
        inventory_row=dict(inventory_row),
        registry_record=dict(record),
        direct_artifacts=tuple(dict(c_by_key[key]) for key in sorted(c_by_key)),
        direct_paths=direct_paths,
        direct_hashes=direct_hashes,
        frame_paths=tuple(path for _index, path, _row in frame_rows),
        frame_hashes=tuple(str(row["sha256"]) for _index, _path, row in frame_rows),
        client_tick_rows=client_rows,
        raw_action_rows=action_rows,
        state_rows=state_rows,
    )


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
    if arguments.runtime_host not in {
        HISTORICAL_RUNTIME_HOST,
        CANONICAL_WINDOWS_RUNTIME_HOST,
    }:
        _fail(
            "runtime_host_invalid",
            "runtime_host must identify the frozen historical or Windows CUDA host",
            step="preflight",
        )
    if (
        arguments.runtime_host == CANONICAL_WINDOWS_RUNTIME_HOST
        and not arguments.canonical_mode
    ):
        _fail(
            "runtime_mode_mismatch",
            "the canonical C6A package and Windows CUDA runtime must be selected together",
            step="preflight",
        )
    for field_name in (
        "repository_root",
        "mineworld_root",
        "asset_root",
    ):
        value = getattr(arguments, field_name)
        if not value.is_absolute() or not value.is_dir() or value.is_symlink():
            _fail(
                "invalid_path",
                f"{field_name} must be an existing absolute ordinary directory",
                step="preflight",
            )
    if arguments.canonical_mode:
        required_paths = ["ffmpeg", "ffprobe"]
        if arguments.staged_canonical_mode:
            required_paths.append("canonical_input_bundle_manifest")
        else:
            required_paths.extend(
                (
                    "canonical_c6a_package",
                    "episode_artifact_manifest",
                    "person_e_provenance_handoff",
                )
            )
        for field_name in required_paths:
            value = getattr(arguments, field_name)
            if (
                not isinstance(value, Path)
                or not value.is_absolute()
                or not value.is_file()
                or value.is_symlink()
            ):
                _fail(
                    "invalid_path",
                    f"{field_name} must be an existing absolute ordinary file",
                    step="preflight",
                )
        if arguments.episode_id is None or arguments.episode_id < 0:
            _fail(
                "episode_identity_invalid",
                "canonical episode_id must be a non-negative integer",
                step="preflight",
            )
        expected_identities = {
            "expected_model_config_sha256": MODEL_CONFIG_GIT_BLOB_SHA256,
            "expected_main_checkpoint_sha256": MAIN_CHECKPOINT_SHA256,
            "expected_vae_config_sha256": VAE_CONFIG_SHA256,
            "expected_vae_checkpoint_sha256": VAE_CHECKPOINT_SHA256,
            "expected_preprocessing_identity": CANONICAL_PREPROCESSING_IDENTITY,
            "expected_action_conversion_identity": CANONICAL_ACTION_CONVERSION_IDENTITY,
            "expected_hook_site": HOOK_SITE,
            "expected_pooling_method": CANONICAL_POOLING_METHOD,
            "expected_token_region": CANONICAL_TOKEN_REGION,
            "expected_activation_store_format": ACTIVATION_STORE_V2_FORMAT_VERSION,
            "expected_activation_index_format": ACTIVATION_INDEX_V2_FORMAT_VERSION,
        }
        mismatches = [
            name
            for name, expected in expected_identities.items()
            if getattr(arguments, name) != expected
        ]
        if mismatches:
            _fail(
                "scientific_identity_mismatch",
                "frozen identities differ: " + ", ".join(mismatches),
                step="preflight",
            )
        if arguments.runtime_host == CANONICAL_WINDOWS_RUNTIME_HOST:
            _validate_create_only_roots(arguments)
        else:
            _validate_sagemaker_canonical_paths(arguments)
    else:
        for field_name in ("approved_input_root", "approved_output_root"):
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
        if arguments.canonical_mode:
            try:
                value.resolve().relative_to(arguments.asset_root.resolve())
            except ValueError:
                _fail(
                    "invalid_path",
                    f"{field_name} must be contained by the pinned asset root",
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


def _existing_parent(path: Path) -> Path:
    candidate = path
    while not candidate.exists() and candidate != candidate.parent:
        candidate = candidate.parent
    if not candidate.is_dir() or candidate.is_symlink():
        _fail(
            "invalid_path",
            f"no ordinary existing parent directory exists for {path}",
            step="preflight",
        )
    return candidate


def _validate_create_only_roots(arguments: RunnerArguments) -> None:
    """Prove all canonical roots are absent without creating anything."""

    for field_name in ("approved_input_root", "approved_output_root"):
        path = getattr(arguments, field_name)
        if not path.is_absolute():
            _fail(
                "invalid_path",
                f"{field_name} must be absolute",
                step="preflight",
            )
        if path.exists() or path.is_symlink():
            _fail(
                "output_exists",
                f"create-only {field_name} already exists: {path}",
                step="preflight",
            )
        _existing_parent(path)
    if arguments.approved_input_root == arguments.approved_output_root:
        _fail(
            "invalid_path",
            "approved input and output roots must differ",
            step="preflight",
        )


def _validate_sagemaker_canonical_paths(arguments: RunnerArguments) -> None:
    """Bind the successor to the existing SageMaker layout and absent outputs."""

    expected = {
        "repository_root": EXPECTED_SAGEMAKER_REPOSITORY_ROOT,
        "mineworld_root": EXPECTED_SAGEMAKER_MINEWORLD_ROOT,
        "asset_root": EXPECTED_SAGEMAKER_ASSET_ROOT,
        "main_checkpoint": EXPECTED_SAGEMAKER_ASSET_ROOT / "checkpoints/700M_16f.ckpt",
        "vae_config": EXPECTED_SAGEMAKER_ASSET_ROOT / "checkpoints/vae/config.json",
        "vae_checkpoint": EXPECTED_SAGEMAKER_ASSET_ROOT / "checkpoints/vae/vae.ckpt",
        "approved_input_root": EXPECTED_SAGEMAKER_INPUT_ROOT,
        "approved_output_root": EXPECTED_SAGEMAKER_OUTPUT_ROOT,
        "ffmpeg": EXPECTED_SAGEMAKER_FFMPEG,
        "ffprobe": EXPECTED_SAGEMAKER_FFPROBE,
    }
    mismatches = [
        name
        for name, path in expected.items()
        if getattr(arguments, name).resolve() != path.resolve()
    ]
    if mismatches:
        _fail(
            "sagemaker_path_mismatch",
            "existing SageMaker paths differ: " + ", ".join(mismatches),
            step="preflight",
        )
    for path in (arguments.approved_input_root, arguments.approved_output_root):
        if not path.is_dir() or path.is_symlink():
            _fail(
                "invalid_path",
                f"existing SageMaker root is unavailable: {path}",
                step="preflight",
            )
    for path in (
        arguments.approved_input_root / arguments.session_id,
        arguments.approved_output_root / arguments.session_id,
        arguments.approved_output_root
        / f"{arguments.session_id}-activation-store-v2",
    ):
        if path.exists() or path.is_symlink():
            _fail(
                "output_exists",
                f"create-only SageMaker path already exists: {path}",
                step="preflight",
            )


def cuda_preflight(torch_module: Any | None = None) -> dict[str, Any]:
    """Read-only visibility and capacity gate for the required CUDA device."""

    torch = torch_module or importlib.import_module("torch")
    if not torch.cuda.is_available() or int(torch.cuda.device_count()) < 1:
        _fail(
            "cuda_unavailable",
            "torch.cuda.is_available() and visible cuda:0 are required",
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
    if int(torch.cuda.current_device()) != 0:
        _fail(
            "cuda_device_mismatch",
            "selected CUDA device is not cuda:0",
            step="preflight",
        )
    return {
        "available": True,
        "device": REQUIRED_DEVICE,
        "device_count": int(torch.cuda.device_count()),
        "device_name": str(properties.name),
        "total_memory_bytes": int(properties.total_memory),
        "torch_cuda_version": str(torch.version.cuda),
    }


def model_assets_preflight(arguments: RunnerArguments) -> tuple[bytes, dict[str, str]]:
    """Validate all frozen model/config bytes without importing the runtime."""

    model_config_blob = _git_object_bytes(
        arguments.mineworld_root,
        f"{MINEWORLD_REVISION}:{MODEL_CONFIG_PATH}",
    )
    if _sha256_bytes(model_config_blob) != arguments.expected_model_config_sha256:
        _fail(
            "model_config_identity_mismatch",
            "authoritative Git-blob model configuration hash differs",
            step="preflight",
        )
    file_hashes = {
        "main_checkpoint": _sha256_file(arguments.main_checkpoint),
        "vae_config": _sha256_file(arguments.vae_config),
        "vae_checkpoint": _sha256_file(arguments.vae_checkpoint),
    }
    expected_file_hashes = {
        "main_checkpoint": arguments.expected_main_checkpoint_sha256,
        "vae_config": arguments.expected_vae_config_sha256,
        "vae_checkpoint": arguments.expected_vae_checkpoint_sha256,
    }
    if file_hashes != expected_file_hashes:
        _fail(
            "checkpoint_identity_mismatch",
            "checkpoint or VAE bytes differ from frozen identities",
            step="preflight",
        )
    return model_config_blob, file_hashes


def runtime_preflight(
    arguments: RunnerArguments,
    canonical_binding: CanonicalPilotBinding | None = None,
) -> dict[str, Any]:
    """Run the complete fail-closed SageMaker gate before Step 6.1."""

    _validate_runtime_arguments(arguments)
    expected_system = (
        "Windows"
        if arguments.runtime_host == CANONICAL_WINDOWS_RUNTIME_HOST
        else "Linux"
    )
    if platform.system() != expected_system:
        _fail(
            "runtime_host_mismatch",
            f"{arguments.runtime_host} execution requires {expected_system}",
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
    if arguments.canonical_mode:
        if canonical_binding is None:
            _fail(
                "canonical_binding_missing",
                "validated canonical authority binding is required",
                step="preflight",
            )
        ratification: dict[str, Any] = {
            "canonical_c6a_id": canonical_binding.canonical_c6a_id,
            "mode": "canonical_manifest_driven_successor",
            "status": "BOUND",
        }
    else:
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
    model_config_blob, file_hashes = model_assets_preflight(arguments)
    physical_model_config = None
    if arguments.runtime_host != CANONICAL_WINDOWS_RUNTIME_HOST:
        physical_model_config = validated_physical_model_config_path(
            mineworld_root=arguments.mineworld_root,
            git_blob_bytes=model_config_blob,
        )
    disk_probe = (
        _existing_parent(arguments.approved_output_root)
        if arguments.canonical_mode
        else arguments.approved_output_root
    )
    free_disk = shutil.disk_usage(disk_probe).free
    if free_disk < MINIMUM_FREE_DISK_BYTES:
        _fail(
            "insufficient_disk",
            f"at least {MINIMUM_FREE_DISK_BYTES} free bytes are required",
            step="preflight",
        )
    torch = importlib.import_module("torch")
    cuda = cuda_preflight(torch)
    nvidia_binary = shutil.which("nvidia-smi")
    nvidia = None
    if nvidia_binary is not None:
        nvidia = subprocess.run(
            [
                nvidia_binary,
                "--query-gpu=name,uuid,memory.total,driver_version",
                "--format=csv,noheader",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
    if not arguments.canonical_mode and (
        nvidia is None or nvidia.returncode != 0 or not nvidia.stdout.strip()
    ):
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
        "canonical_authority": None if canonical_binding is None else {
            "canonical_c6a_id": canonical_binding.canonical_c6a_id,
            "c6a_package_sha256": canonical_binding.package_sha256,
            "episode_artifact_manifest_sha256": canonical_binding.artifact_manifest_sha256,
            "person_e_handoff_sha256": canonical_binding.person_e_handoff_sha256,
            "trajectory_id": canonical_binding.trajectory_id,
            "episode_id": canonical_binding.episode_id,
            "direct_artifact_count": len(canonical_binding.direct_artifacts),
        },
        "cuda": cuda,
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
        "model_config_physical_path": (
            None if physical_model_config is None else str(physical_model_config)
        ),
        "model_config_physical_sha256": (
            None if physical_model_config is None else _sha256_file(physical_model_config)
        ),
        "nvidia_smi": (
            nvidia.stdout.strip().splitlines()
            if nvidia is not None and nvidia.returncode == 0
            else []
        ),
        "runtime_host": arguments.runtime_host,
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


@contextlib.contextmanager
def _canonical_pilot_constants(binding: CanonicalPilotBinding) -> Any:
    """Temporarily bind the frozen successor pipeline to one validated pilot."""

    global SELECTED_PILOT
    global GLOBAL_MODEL_FRAME_COUNT
    global EXPECTED_ACTIVATION_ROW_COUNT
    global C_CAPTURE_PACKAGE_SHA256
    global C_FRAME_MAP_SHA256
    global C_STATE_SHA256
    old = (
        SELECTED_PILOT,
        GLOBAL_MODEL_FRAME_COUNT,
        EXPECTED_ACTIVATION_ROW_COUNT,
        C_CAPTURE_PACKAGE_SHA256,
        C_FRAME_MAP_SHA256,
        C_STATE_SHA256,
    )
    SELECTED_PILOT = binding.trajectory_id
    GLOBAL_MODEL_FRAME_COUNT = binding.frame_count
    EXPECTED_ACTIVATION_ROW_COUNT = binding.expected_activation_rows
    C_CAPTURE_PACKAGE_SHA256 = binding.artifact_manifest_sha256
    C_FRAME_MAP_SHA256 = binding.direct_hashes["client_tick"]
    C_STATE_SHA256 = binding.direct_hashes["server_state"]
    try:
        yield
    finally:
        (
            SELECTED_PILOT,
            GLOBAL_MODEL_FRAME_COUNT,
            EXPECTED_ACTIVATION_ROW_COUNT,
            C_CAPTURE_PACKAGE_SHA256,
            C_FRAME_MAP_SHA256,
            C_STATE_SHA256,
        ) = old


def _canonical_jsonl_bytes(rows: Sequence[Mapping[str, Any]]) -> bytes:
    return b"".join(_canonical_document_bytes(row) + b"\n" for row in rows)


def _canonical_raw_action(source: Mapping[str, Any]) -> dict[str, Any]:
    key_map = {
        "back": "key.keyboard.s",
        "drop": "key.keyboard.q",
        "forward": "key.keyboard.w",
        "jump": "key.keyboard.space",
        "left": "key.keyboard.a",
        "right": "key.keyboard.d",
        "sneak": "key.keyboard.left.shift",
        "sprint": "key.keyboard.left.control",
    }
    keys = [value for name, value in key_map.items() if source.get(name) is True]
    hotbar = source.get("hotbar")
    if isinstance(hotbar, int) and not isinstance(hotbar, bool) and 1 <= hotbar <= 9:
        keys.append(f"key.keyboard.{hotbar}")
    buttons = [
        button
        for name, button in (("attack", 0), ("use", 1), ("pick_item", 2))
        if source.get(name) is True
    ]
    return {
        "keyboard": {"keys": keys},
        "mouse": {
            "buttons": buttons,
            "dx": float(source.get("camera_dx", 0.0)),
            "dy": float(source.get("camera_dy", 0.0)),
        },
    }


def _canonical_streams(binding: CanonicalPilotBinding) -> dict[str, list[dict[str, Any]]]:
    """Create the contract streams while retaining every direct source join."""

    streams = {
        name: []
        for name in (
            "frame_map",
            "raw_actions",
            "normalized_actions",
            "server_state",
            "client_tick_log",
            "visibility",
            "seed_noise",
        )
    }
    episode = str(binding.episode_id)
    for index, (client, source_action, source_state) in enumerate(
        zip(
            binding.client_tick_rows,
            binding.raw_action_rows,
            binding.state_rows,
            strict=True,
        )
    ):
        identity = {
            "action_idx": index,
            "episode_id": episode,
            "model_frame_idx": index,
            "render_frame_idx": index,
            "server_tick": index,
            "trajectory_id": binding.trajectory_id,
        }
        client_hash = _sha256_bytes(_canonical_document_bytes(client))
        action_hash = _sha256_bytes(_canonical_document_bytes(source_action))
        state_hash = _sha256_bytes(_canonical_document_bytes(source_state))
        streams["frame_map"].append(
            {
                **identity,
                "source_client_tick_row_sha256": client_hash,
                "source_frame_path": str(binding.frame_paths[index]),
                "source_frame_sha256": binding.frame_hashes[index],
                "source_server_epoch_nanos": client["server_epoch_nanos"],
            }
        )
        streams["raw_actions"].append(
            {
                **identity,
                "raw_action": _canonical_raw_action(source_action),
                "raw_action_flat": dict(source_action),
                "source_raw_action_row_sha256": action_hash,
            }
        )
        if any(
            source_action.get(name) not in (False, 0, 0.0)
            for name in (
                "forward", "back", "left", "right", "jump", "sneak",
                "sprint", "use", "attack", "drop", "pick_item", "hotbar",
                "camera_dx", "camera_dy",
            )
        ):
            _fail(
                "canonical_action_profile_mismatch",
                "the selected canonical positive control must retain its no-op action rows",
                step="6.1",
            )
        streams["normalized_actions"].append(
            {
                **identity,
                "normalized_action": {
                    "camera_component_0": 5,
                    "camera_component_1": 5,
                    "drop_pick_item": 0,
                    "forward_back": 0,
                    "hotbar": 0,
                    "jump": 0,
                    "left_right": 0,
                    "sprint_sneak": 0,
                    "use_attack": 0,
                },
                "source_raw_action_row_sha256": action_hash,
            }
        )
        streams["server_state"].append(
            {
                **identity,
                "source_server_state_row_sha256": state_hash,
                "state": {
                    "position_x_blocks": float(source_state["sheep_x"]),
                    "position_y_blocks": float(source_state["sheep_y"]),
                    "position_z_blocks": float(source_state["sheep_z"]),
                    "target_entity_id": f"canonical_sheep_{binding.episode_id}",
                    "target_present": True,
                    "velocity_x_blocks_per_second": float(source_state["axis_velocity"]),
                    "velocity_y_blocks_per_second": 0.0,
                    "velocity_z_blocks_per_second": 0.0,
                    "wall_parallel_position_blocks": float(source_state["axis_pos"]),
                },
            }
        )
        streams["client_tick_log"].append(
            {
                **identity,
                "client_capture_nanos": client["client_capture_nanos"],
                "client_recv_nanos": client["client_recv_nanos"],
                "client_tick": index,
                "server_epoch_nanos": client["server_epoch_nanos"],
                "source_client_tick_row_sha256": client_hash,
            }
        )
        streams["visibility"].append(
            {
                **identity,
                "source_geometric_visible": True,
                "source_server_state_row_sha256": state_hash,
                "visibility": "visible",
            }
        )
        noise = float(source_state["noise_draw"])
        q = float(source_state["q"])
        noise_std = math.sqrt(q * 0.05)
        streams["seed_noise"].append(
            {
                **identity,
                "draw_idx": index,
                "dt_seconds": 0.05,
                "noise_draw": noise,
                "noise_std_blocks": noise_std,
                "q": q,
                "seed": int(source_state["seed"]),
                "standard_normal_draw": noise / noise_std,
            }
        )
    return streams


def _encode_canonical_media(
    binding: CanonicalPilotBinding,
    intake_root: Path,
    ffmpeg: Path,
    ffprobe: Path,
) -> tuple[Path, list[dict[str, Any]], dict[str, Any]]:
    """Apply Person C's established center-crop/resize and fixed MP4 encode."""

    image_module = importlib.import_module("PIL.Image")
    frame_root = intake_root / "frames_640x360"
    frame_root.mkdir()
    rows: list[dict[str, Any]] = []
    list_lines: list[str] = []
    target_aspect = 640.0 / 360.0
    for index, source in enumerate(binding.frame_paths):
        with image_module.open(source) as opened:
            image = opened.convert("RGB")
            width, height = image.size
            aspect = width / height
            if aspect > target_aspect:
                new_width = round(height * target_aspect)
                left = (width - new_width) // 2
                image = image.crop((left, 0, left + new_width, height))
            elif aspect < target_aspect:
                new_height = round(width / target_aspect)
                top = (height - new_height) // 2
                image = image.crop((0, top, width, top + new_height))
            resized = image.resize((640, 360), image_module.Resampling.BILINEAR)
            destination = frame_root / f"{index:06d}.png"
            with destination.open("xb") as handle:
                resized.save(handle, format="PNG")
        rows.append(
            {
                "model_frame_idx": index,
                "path": str(destination),
                "sha256": _sha256_file(destination),
                "source_path": str(source),
                "source_sha256": binding.frame_hashes[index],
            }
        )
        escaped = str(destination).replace("'", "'\\''")
        list_lines.extend((f"file '{escaped}'", "duration 0.05"))
    concat_path = intake_root / "canonical_frames.ffconcat"
    _exclusive_write(concat_path, ("\n".join(list_lines) + "\n").encode("utf-8"))
    media_path = intake_root / "video_640x360.mp4"
    encoded = subprocess.run(
        [
            str(ffmpeg), "-n", "-loglevel", "error", "-f", "concat",
            "-safe", "0", "-i", str(concat_path), "-fps_mode", "cfr",
            "-r", "20", "-c:v", "libx264", "-preset", "veryfast",
            "-crf", "18", "-pix_fmt", "yuv420p", str(media_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if encoded.returncode != 0 or not media_path.is_file():
        _fail("canonical_media_encode_failed", encoded.stderr.strip(), step="6.1")
    probed = subprocess.run(
        [
            str(ffprobe), "-v", "error", "-select_streams", "v:0",
            "-count_frames", "-show_entries",
            "stream=width,height,r_frame_rate,nb_read_frames", "-of", "json",
            str(media_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    try:
        stream = json.loads(probed.stdout)["streams"][0]
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as error:
        _fail("canonical_media_probe_failed", str(error), step="6.1")
    if (
        probed.returncode != 0
        or stream.get("width") != 640
        or stream.get("height") != 360
        or stream.get("r_frame_rate") != "20/1"
        or int(stream.get("nb_read_frames", -1)) != binding.frame_count
    ):
        _fail("canonical_media_contract_mismatch", "ffprobe contract differs", step="6.1")
    return media_path, rows, dict(stream)


def _materialize_exact_mineworld_checkout(
    source_root: Path,
    intake_root: Path,
) -> tuple[Path, Path]:
    """Create an LF-exact pinned checkout without modifying the source checkout."""

    runtime_root = intake_root / "MineWorld-Upstream-exact"
    if runtime_root.exists() or runtime_root.is_symlink():
        _fail("output_exists", "exact MineWorld runtime checkout exists", step="6.1")
    clone = subprocess.run(
        [
            "git", "clone", "--quiet", "--no-local", "--no-checkout",
            str(source_root), str(runtime_root),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if clone.returncode != 0:
        _fail("mineworld_materialization_failed", clone.stderr.strip(), step="6.1")
    _run_git(runtime_root, "config", "core.autocrlf", "false")
    _run_git(runtime_root, "checkout", "--quiet", "--detach", MINEWORLD_REVISION)
    model_config = runtime_root / MODEL_CONFIG_PATH
    if (
        _run_git(runtime_root, "rev-parse", "HEAD") != MINEWORLD_REVISION
        or _run_git(runtime_root, "status", "--porcelain=v1", "-uall")
        or _sha256_file(model_config) != MODEL_CONFIG_GIT_BLOB_SHA256
    ):
        _fail(
            "mineworld_materialization_failed",
            "isolated MineWorld checkout is not exact and clean",
            step="6.1",
        )
    return runtime_root, model_config


def canonical_step6_1_intake(context: RunContext) -> dict[str, Any]:
    """Materialize one validated post-C1 C6A pilot into the frozen contract."""

    global C_CAPTURE_PACKAGE_SHA256
    binding: CanonicalPilotBinding = context.state["canonical_binding"]
    intake_root = context.arguments.approved_input_root / context.arguments.session_id
    if intake_root.exists() or intake_root.is_symlink():
        _fail("output_exists", "immutable approved intake already exists", step="6.1")
    intake_root.mkdir()
    if context.arguments.runtime_host == CANONICAL_WINDOWS_RUNTIME_HOST:
        runtime_root, model_config_path = _materialize_exact_mineworld_checkout(
            context.arguments.mineworld_root,
            intake_root,
        )
    else:
        runtime_root = context.arguments.mineworld_root
        model_config_path = runtime_root / MODEL_CONFIG_PATH
    assert context.arguments.ffmpeg is not None
    assert context.arguments.ffprobe is not None
    media_path, canonical_frames, media_probe = _encode_canonical_media(
        binding,
        intake_root,
        context.arguments.ffmpeg,
        context.arguments.ffprobe,
    )
    streams = _canonical_streams(binding)
    output_names = {
        "frame_map": "frame_map.jsonl",
        "raw_actions": "raw_actions.jsonl",
        "normalized_actions": "normalized_actions.jsonl",
        "server_state": "server_state.jsonl",
        "client_tick_log": "client_tick_log.jsonl",
        "visibility": "visibility.jsonl",
        "seed_noise": "seed_noise.jsonl",
    }
    input_paths: dict[str, Path] = {"media": media_path}
    artifacts: dict[str, dict[str, Any]] = {}
    for name, filename in output_names.items():
        path = intake_root / filename
        payload = _canonical_jsonl_bytes(streams[name])
        _exclusive_write(path, payload)
        input_paths[name] = path
        artifacts[name] = {
            "format": "jsonl",
            "path": str(path),
            "sha256": _sha256_bytes(payload),
        }
    config_path = intake_root / "reset_result.json"
    _exclusive_write(config_path, binding.direct_paths["reset_result"].read_bytes())
    diagnostics = {
        "canonical_frame_derivatives": canonical_frames,
        "direct_artifact_count": len(binding.direct_artifacts),
        "exact_source_identity_joins": "PASS",
        "media_probe": media_probe,
        "selection_rule": CANONICAL_SELECTION_RULE,
        "status": "PASS",
    }
    diagnostics_path = intake_root / "canonical_intake_diagnostics.json"
    _write_json(diagnostics_path, diagnostics)
    artifacts["config"] = {
        "format": "json",
        "path": str(config_path),
        "sha256": _sha256_file(config_path),
    }
    artifacts["diagnostics"] = {
        "format": "json",
        "path": str(diagnostics_path),
        "sha256": _sha256_file(diagnostics_path),
    }
    package = {
        "artifacts": artifacts,
        "episode_id": str(binding.episode_id),
        "impulse_orientation": dict(CANONICAL_IMPULSE_ORIENTATION),
        "media": {
            "fps": 20.0,
            "frame_count": binding.frame_count,
            "height": 360,
            "mode": "mp4",
            "path": str(media_path),
            "sha256": _sha256_file(media_path),
            "width": 640,
        },
        "schema_version": "1.0",
        "seed": int(binding.state_rows[0]["seed"]),
        "streams": streams,
        "trajectory_id": binding.trajectory_id,
    }
    trajectory_contract = importlib.import_module("mineocclude.contracts.trajectory")
    validation = trajectory_contract.validate_trajectory_package(package)
    if not validation.accepted:
        _fail(
            "canonical_package_validation_failed",
            "; ".join(item.code.value for item in validation.rejections),
            step="6.1",
        )
    package_path = intake_root / "capture_package_v0_1.json"
    _write_json(package_path, package)
    C_CAPTURE_PACKAGE_SHA256 = _sha256_file(package_path)
    accepted_manifest = {
        "accepted_pilot_count": 1,
        "canonical_c6a_id": binding.canonical_c6a_id,
        "direct_episode_artifacts": list(binding.direct_artifacts),
        "episode_artifact_manifest": {
            "path": str(binding.artifact_manifest_path),
            "sha256": binding.artifact_manifest_sha256,
        },
        "expected_identities": {
            "activation_index_format": context.arguments.expected_activation_index_format,
            "activation_store_format": context.arguments.expected_activation_store_format,
            "action_conversion": context.arguments.expected_action_conversion_identity,
            "hook_site": context.arguments.expected_hook_site,
            "pooling_method": context.arguments.expected_pooling_method,
            "preprocessing": context.arguments.expected_preprocessing_identity,
            "token_region": context.arguments.expected_token_region,
        },
        "grouping": {"key": CANONICAL_GROUPING_KEY, "value": binding.layout_id},
        "person_c": {
            "commit": binding.person_c_commit,
            "package_path": str(binding.package_path),
            "package_sha256": binding.package_sha256,
        },
        "person_e": {
            "handoff_path": str(binding.person_e_handoff_path),
            "handoff_sha256": binding.person_e_handoff_sha256,
            "registry_record_id": binding.registry_record_id,
            "registry_record_sha256": binding.registry_record_sha256,
        },
        "schema_version": "person-a-canonical-pilot-accepted-manifest-v0.1",
        "selection_rule": CANONICAL_SELECTION_RULE,
        "selected_episode_id": binding.episode_id,
        "selected_trajectory_id": binding.trajectory_id,
        "status": "ACCEPTED_FOR_FROZEN_A6_1_TO_A6_5",
    }
    accepted_path = intake_root / "accepted_pilot_manifest.json"
    _write_json(accepted_path, accepted_manifest)
    input_paths["accepted_manifest"] = accepted_path
    input_paths["capture_package"] = package_path
    context.state.update(
        {
            "accepted_manifest": accepted_manifest,
            "capture_package": package,
            "input_paths": input_paths,
            "model_config_provenance_path": model_config_path,
            "mineworld_runtime_root": runtime_root,
            "payloads": {},
        }
    )
    return {
        "accepted_manifest_path": str(accepted_path),
        "accepted_manifest_sha256": _sha256_file(accepted_path),
        "capture_package_sha256": C_CAPTURE_PACKAGE_SHA256,
        "direct_artifact_count": len(binding.direct_artifacts),
        "exact_source_identity_joins": "PASS",
        "input_root": str(intake_root),
        "pilot": binding.trajectory_id,
        "status": "PASS",
    }


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
    if context.arguments.runtime_host == CANONICAL_WINDOWS_RUNTIME_HOST:
        physical_model_config_path = context.state["model_config_provenance_path"]
        mineworld_source_root = context.state["mineworld_runtime_root"]
    else:
        model_config_blob = _git_object_bytes(
            context.arguments.mineworld_root,
            f"{MINEWORLD_REVISION}:{MODEL_CONFIG_PATH}",
        )
        physical_model_config_path = validated_physical_model_config_path(
            mineworld_root=context.arguments.mineworld_root,
            git_blob_bytes=model_config_blob,
        )
        mineworld_source_root = context.arguments.mineworld_root
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
        mineworld_source_root=mineworld_source_root,
        model_config_path=physical_model_config_path,
        main_checkpoint_path=context.arguments.main_checkpoint,
        vae_config_path=context.arguments.vae_config,
        vae_checkpoint_path=context.arguments.vae_checkpoint,
        model_config_sha256=context.arguments.expected_model_config_sha256,
        main_checkpoint_sha256=context.arguments.expected_main_checkpoint_sha256,
        vae_config_sha256=context.arguments.expected_vae_config_sha256,
        vae_checkpoint_sha256=context.arguments.expected_vae_checkpoint_sha256,
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
        or runtime.preprocessing_identity
        != context.arguments.expected_preprocessing_identity
        or runtime.action_conversion_identity
        != context.arguments.expected_action_conversion_identity
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
        checkpoint_hash=context.arguments.expected_main_checkpoint_sha256,
        model_hash=context.arguments.expected_main_checkpoint_sha256,
        config_hash=PHASE6_CONFIG_HASH,
        preprocess_hash=PREPROCESS_HASH,
        accepted_manifest_hash=C_CAPTURE_PACKAGE_SHA256,
        code_sha=str(current_commit),
        hook_site=context.arguments.expected_hook_site,
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
                    model_config_sha256=context.arguments.expected_model_config_sha256,
                    main_checkpoint_sha256=context.arguments.expected_main_checkpoint_sha256,
                    vae_config_sha256=context.arguments.expected_vae_config_sha256,
                    vae_checkpoint_sha256=context.arguments.expected_vae_checkpoint_sha256,
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
            "bounded_unpooled_artifact": limited_unpooled,
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
    if context.arguments.canonical_mode:
        binding: CanonicalPilotBinding = context.state["canonical_binding"]
        audit = context.state["bounded_unpooled_artifact"]
        audit_artifacts = []
        if audit is not None:
            for kind, path, digest in (
                ("bounded_unpooled_activation", audit.artifact_path, audit.artifact_sha256),
                ("bounded_unpooled_manifest", audit.manifest_path, audit.manifest_sha256),
            ):
                audit_artifacts.append(
                    {
                        "byte_size": path.stat().st_size,
                        "path": str(path),
                        "sha256": digest,
                        "type": kind,
                    }
                )
        certification_path = context.session_root / "step6_5.json"
        certification_artifact = {
            "byte_size": certification_path.stat().st_size,
            "path": str(certification_path),
            "sha256": _sha256_file(certification_path),
            "type": "direct_pooling_repeatability_source_join_validation",
        }
        accepted_path = context.state["input_paths"]["accepted_manifest"]
        package_path = context.state["input_paths"]["capture_package"]
        common = {
            "accepted_manifest": {
                "path": str(accepted_path),
                "sha256": _sha256_file(accepted_path),
            },
            "activation_artifacts": artifacts,
            "bounded_unpooled_audit_artifacts": audit_artifacts,
            "canonical_c6a_id": binding.canonical_c6a_id,
            "capture_package": {
                "path": str(package_path),
                "sha256": _sha256_file(package_path),
            },
            "certification_artifact": certification_artifact,
            "episode_id": binding.episode_id,
            "exact_source_identity_joins": {
                "c_frame_map_source_sha256": C_FRAME_MAP_SHA256,
                "c_server_state_source_sha256": C_STATE_SHA256,
                "failure_count": 0,
                "status": "PASS",
            },
            "expected_activation_row_count": EXPECTED_ACTIVATION_ROW_COUNT,
            "grouping": {
                "key": CANONICAL_GROUPING_KEY,
                "value": binding.layout_id,
            },
            "identities": {
                "activation_index_format": context.arguments.expected_activation_index_format,
                "activation_store_format": context.arguments.expected_activation_store_format,
                "action_conversion": context.arguments.expected_action_conversion_identity,
                "hook_site": context.arguments.expected_hook_site,
                "model_config_sha256": context.arguments.expected_model_config_sha256,
                "model_sha256": context.arguments.expected_main_checkpoint_sha256,
                "pooling_method": context.arguments.expected_pooling_method,
                "preprocessing": context.arguments.expected_preprocessing_identity,
                "token_region": context.arguments.expected_token_region,
            },
            "repeatability_validation": {
                "atol": 1e-3,
                "maximum_absolute_difference": context.state[
                    "repeatability_maximum_absolute_difference"
                ],
                "rtol": 1e-3,
                "status": "PASS",
            },
            "runner_version": RUNNER_VERSION,
            "trajectory_id": binding.trajectory_id,
        }
        b_handoff = {
            **common,
            "direct_pooling_validation": "PASS",
            "no_wall_visible_positive_control": True,
            "schema_version": "person-a-to-person-b-canonical-pilot-handoff-v0.1",
            "scientific_use_acceptance_claimed": False,
            "shuffled_comparison_required": True,
            "status": "READY_FOR_PERSON_B_CONSUMPTION",
        }
        e_handoff = {
            **common,
            "direct_episode_artifacts": list(binding.direct_artifacts),
            "person_c": {
                "commit": binding.person_c_commit,
                "package_sha256": binding.package_sha256,
            },
            "person_e_source": {
                "handoff_sha256": binding.person_e_handoff_sha256,
                "registry_record_id": binding.registry_record_id,
                "registry_record_sha256": binding.registry_record_sha256,
            },
            "schema_version": "person-a-to-person-e-canonical-provenance-handoff-v0.1",
            "status": "READY_FOR_PERSON_E_PROVENANCE_CONSUMPTION",
        }
        b_path = context.session_root / "person_a_to_person_b_canonical_pilot_handoff.json"
        e_path = context.session_root / "person_a_to_person_e_canonical_provenance_handoff.json"
        _write_json(b_path, b_handoff)
        _write_json(e_path, e_handoff)
        handoff = {
            "b_facing_handoff": {
                "path": str(b_path),
                "sha256": _sha256_file(b_path),
            },
            "e_facing_handoff": {
                "path": str(e_path),
                "sha256": _sha256_file(e_path),
            },
            "schema_version": "person-a-canonical-dual-handoff-summary-v0.1",
            "status": "HANDOFF_PREPARED_NOT_ACCEPTED",
        }
        _write_json(context.session_root / "step6_6_handoff.json", handoff)
        return handoff
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
        "scientific_execution_environment": context.arguments.runtime_host,
        "selected_pilot": SELECTED_PILOT,
        "sequence": dict(sequence),
        "status": sequence["status"],
        "step_receipts": context.step_receipts,
    }


def run(arguments: RunnerArguments) -> int:
    """Execute the historical or canonical manifest-bound one-pilot workflow."""

    _validate_runtime_arguments(arguments)
    binding = load_canonical_pilot_binding(arguments) if arguments.canonical_mode else None
    receipt = runtime_preflight(arguments, binding)
    if arguments.runtime_host == CANONICAL_WINDOWS_RUNTIME_HOST:
        arguments.approved_input_root.mkdir()
        arguments.approved_output_root.mkdir()
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
    if binding is not None:
        context.state["canonical_binding"] = binding
    manager = (
        _canonical_pilot_constants(binding)
        if binding is not None
        else contextlib.nullcontext()
    )
    with manager:
        sequence = execute_step_sequence(
            context,
            {
                "6.1": canonical_step6_1_intake if binding else step6_1_intake,
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
        help="execute once on the selected frozen GPU runtime host",
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
        "--runtime-host",
        choices=(HISTORICAL_RUNTIME_HOST, CANONICAL_WINDOWS_RUNTIME_HOST),
        default=HISTORICAL_RUNTIME_HOST,
    )
    execute.add_argument("--canonical-c6a-package", type=Path)
    execute.add_argument("--canonical-c6a-package-sha256", default="")
    execute.add_argument("--trajectory-id", default=SELECTED_PILOT)
    execute.add_argument("--episode-id", type=int)
    execute.add_argument("--episode-artifact-manifest", type=Path)
    execute.add_argument("--episode-artifact-manifest-sha256", default="")
    execute.add_argument("--person-e-provenance-handoff", type=Path)
    execute.add_argument("--person-e-provenance-handoff-sha256", default="")
    execute.add_argument(
        "--expected-model-config-sha256",
        default=MODEL_CONFIG_GIT_BLOB_SHA256,
    )
    execute.add_argument(
        "--expected-main-checkpoint-sha256",
        default=MAIN_CHECKPOINT_SHA256,
    )
    execute.add_argument("--expected-vae-config-sha256", default=VAE_CONFIG_SHA256)
    execute.add_argument(
        "--expected-vae-checkpoint-sha256",
        default=VAE_CHECKPOINT_SHA256,
    )
    execute.add_argument(
        "--expected-preprocessing-identity",
        default=CANONICAL_PREPROCESSING_IDENTITY,
    )
    execute.add_argument(
        "--expected-action-conversion-identity",
        default=CANONICAL_ACTION_CONVERSION_IDENTITY,
    )
    execute.add_argument("--expected-hook-site", default=HOOK_SITE)
    execute.add_argument("--expected-pooling-method", default=CANONICAL_POOLING_METHOD)
    execute.add_argument("--expected-token-region", default=CANONICAL_TOKEN_REGION)
    execute.add_argument(
        "--expected-activation-store-format",
        default=ACTIVATION_STORE_V2_FORMAT_VERSION,
    )
    execute.add_argument(
        "--expected-activation-index-format",
        default=ACTIVATION_INDEX_V2_FORMAT_VERSION,
    )
    execute.add_argument("--ffmpeg", type=Path)
    execute.add_argument("--ffprobe", type=Path)
    execute.add_argument("--canonical-input-bundle-manifest", type=Path)
    execute.add_argument("--canonical-input-bundle-manifest-sha256", default="")
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
        runtime_host=namespace.runtime_host,
        canonical_c6a_package=(
            None
            if namespace.canonical_c6a_package is None
            else namespace.canonical_c6a_package.resolve()
        ),
        canonical_c6a_package_sha256=namespace.canonical_c6a_package_sha256,
        trajectory_id=namespace.trajectory_id,
        episode_id=namespace.episode_id,
        episode_artifact_manifest=(
            None
            if namespace.episode_artifact_manifest is None
            else namespace.episode_artifact_manifest.resolve()
        ),
        episode_artifact_manifest_sha256=namespace.episode_artifact_manifest_sha256,
        person_e_provenance_handoff=(
            None
            if namespace.person_e_provenance_handoff is None
            else namespace.person_e_provenance_handoff.resolve()
        ),
        person_e_provenance_handoff_sha256=namespace.person_e_provenance_handoff_sha256,
        expected_model_config_sha256=namespace.expected_model_config_sha256,
        expected_main_checkpoint_sha256=namespace.expected_main_checkpoint_sha256,
        expected_vae_config_sha256=namespace.expected_vae_config_sha256,
        expected_vae_checkpoint_sha256=namespace.expected_vae_checkpoint_sha256,
        expected_preprocessing_identity=namespace.expected_preprocessing_identity,
        expected_action_conversion_identity=namespace.expected_action_conversion_identity,
        expected_hook_site=namespace.expected_hook_site,
        expected_pooling_method=namespace.expected_pooling_method,
        expected_token_region=namespace.expected_token_region,
        expected_activation_store_format=namespace.expected_activation_store_format,
        expected_activation_index_format=namespace.expected_activation_index_format,
        ffmpeg=None if namespace.ffmpeg is None else namespace.ffmpeg.resolve(),
        ffprobe=None if namespace.ffprobe is None else namespace.ffprobe.resolve(),
        canonical_input_bundle_manifest=(
            None
            if namespace.canonical_input_bundle_manifest is None
            else namespace.canonical_input_bundle_manifest.resolve()
        ),
        canonical_input_bundle_manifest_sha256=(
            namespace.canonical_input_bundle_manifest_sha256
        ),
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
