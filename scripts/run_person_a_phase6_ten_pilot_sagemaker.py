#!/usr/bin/env python3
"""Fail-closed multi-pilot SageMaker runner for the Phase 6 expansion.

``plan`` is preparation-only and never imports a model runtime.  ``run``
requires Person B's future exact authorization object, validates the existing
layout_00_ep9403 activation store without extracting it again, and processes
only the nine additional Person C inputs in frozen order.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import importlib
import json
import platform
import shutil
import subprocess
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import run_person_a_phase6_single_pilot_sagemaker as single

RUNNER_VERSION = "person-a-phase6-ten-pilot-sagemaker-runner-v0.1"
REQUIRED_BRANCH = "role/person-a-model"
PERSON_A_STARTING_COMMIT = "e6e0340f301abb84c127034b154be55a38bdc8f6"
PERSON_B_SELECTION_COMMIT = "19f08b2e27217b781961da8f7299e1396a3ab703"
PERSON_C_ACCEPTANCE_COMMIT = "c6bff25b5ef4f5fdb0e1ef0ce0d22e3f8b5e4960"
PERSON_E_REGISTRY_V2_COMMIT = "b27d404c6aa913bac559754fa8b7accdff46e886"

B_SELECTION_REL = (
    "docs/status/person_b_phase6_ten_pilot_expansion_selection_v0_1/"
    "expansion_selection_manifest.json"
)
C_PACKAGE_ROOT = (
    "docs/status/person_c_phase6_ten_pilot_expansion_acceptance_v0_1"
)
C_ACCEPTED_MANIFEST_REL = f"{C_PACKAGE_ROOT}/accepted_pilot_manifest.json"
C_DECISION_REL = f"{C_PACKAGE_ROOT}/expansion_acceptance_decision.json"
C_VALIDATION_REL = f"{C_PACKAGE_ROOT}/validation_receipt.json"
C_INVENTORY_REL = f"{C_PACKAGE_ROOT}/sha256_inventory.json"

EXISTING_PILOT = "layout_00_ep9403"
EXISTING_ACTIVATION_INDEX_REL = (
    "indexes/index-82dc0e18607a1a89135a1a88cbec5d53531682db970e9a1323672e7f4d28677b.json"
)
EXISTING_ACTIVATION_INDEX_SHA256 = (
    "473efef1eb52514c097051ec8f4501cb621f92c9ceaeb847249c7e3ae042ad55"
)
EXISTING_ACTIVATION_INDEX_BYTE_SIZE = 32502224
EXISTING_ACTIVATION_ROW_COUNT = 4960
DETERMINISTIC_SEED = 20260725
REQUIRED_DEVICE = "cuda:0"
PHASE6_STEPS = ("6.1", "6.2", "6.3", "6.4", "6.5")
SAGEMAKER_COMMAND = (
    "tmux new-session -d -s person-a-phase6-ten-pilot "
    "'bash scripts/run_person_a_phase6_ten_pilot_sagemaker.sh'"
)


class MultiPilotRunnerError(RuntimeError):
    """One fail-closed multi-pilot preparation or runtime error."""


def fail(message: str) -> None:
    raise MultiPilotRunnerError(message)


@dataclass(frozen=True)
class PilotSpec:
    trajectory_id: str
    layout_id: str
    fold_idx: int
    condition_role: str
    control: bool
    frame_count: int
    capture_package_sha256: str
    capture_package_byte_size: int
    requires_processing: bool

    @property
    def expected_activation_rows(self) -> int:
        return self.frame_count * len(single.FROZEN_PHASE6_LAYERS)


PILOT_SPECS = (
    PilotSpec("layout_00_ep9403", "layout_00", 1, "core_occluded", False, 248,
              "21ea1dba91cf92ad82080088f70905fba053557392437b19591cad1333667213", 662116, False),
    PilotSpec("layout_00_ep9441", "layout_00", 1, "no_wall_visible_control", True, 200,
              "5e5d5d8cbeecaa07bd93af1faab23d6bdd0643df4f59e9b72397842efc3d3664", 531375, True),
    PilotSpec("layout_01_ep9405", "layout_01", 2, "core_occluded", False, 230,
              "c139247e3be9132ddf2781f6d8abbe7d4498fa158464e3f47c534cf19b5c614f", 610140, True),
    PilotSpec("layout_01_ep9442", "layout_01", 2, "no_wall_visible_control", True, 200,
              "4cb40c2b8b62268fba0556ed38f25644710dede5c1be9cf579e3aea445ab4096", 531371, True),
    PilotSpec("layout_02_ep9407", "layout_02", 4, "core_occluded", False, 158,
              "ed7884bcc5e72db1d8b1c642f0ce668544c7cb348567b0ec820d69db6016004f", 422479, True),
    PilotSpec("layout_02_ep9432", "layout_02", 4, "no_wall_visible_control", True, 200,
              "fae0107e2ceb60e62dbc5a89fe459b4d7a952ce8c28cb97faa490d3fde4d4d0c", 531379, True),
    PilotSpec("layout_03_ep9404", "layout_03", 0, "core_occluded", False, 125,
              "c9bc91d934643a53c5b3c39d519e5b3533788021adac57373af5edea12795ac7", 332665, True),
    PilotSpec("layout_03_ep9443", "layout_03", 0, "no_wall_visible_control", True, 200,
              "affb4273939c84a869548633f51888a8c2e429466360d906049b63e9e0f6bb83", 531261, True),
    PilotSpec("layout_04_ep9406", "layout_04", 3, "core_occluded", False, 113,
              "3cc2917fb0698d83d4ec12aa7cd7288e4a929dd5f13e810d303fbd1cc348f021", 302914, True),
    PilotSpec("layout_04_ep9444", "layout_04", 3, "no_wall_visible_control", True, 200,
              "4fe5bd8bedfdb78be17c580662dda5511b1314d7ee522c64db529d50dfc7c0a0", 531250, True),
)


@dataclass(frozen=True)
class MultiRunnerArguments:
    repository_root: Path
    mineworld_root: Path
    asset_root: Path
    main_checkpoint: Path
    vae_config: Path
    vae_checkpoint: Path
    approved_input_root: Path
    approved_output_root: Path
    existing_artifact_root: Path
    person_b_expansion_authorization_object: str
    session_id: str
    seed: int
    device: str
    precision: str


def ordered_pilot_ids() -> list[str]:
    return [spec.trajectory_id for spec in PILOT_SPECS]


def additional_pilot_specs() -> tuple[PilotSpec, ...]:
    return tuple(spec for spec in PILOT_SPECS if spec.requires_processing)


def no_wall_control_ids() -> list[str]:
    return [spec.trajectory_id for spec in PILOT_SPECS if spec.control]


def plan_document() -> dict[str, Any]:
    """Return the complete static plan without importing torch or a model."""

    return {
        "activation_index_format_version": single.ACTIVATION_INDEX_V2_FORMAT_VERSION,
        "activation_store_format_version": single.ACTIVATION_STORE_V2_FORMAT_VERSION,
        "additional_pilot_count": len(additional_pilot_specs()),
        "combined_expected_activation_row_count": sum(
            spec.expected_activation_rows for spec in PILOT_SPECS
        ),
        "deterministic_seed": DETERMINISTIC_SEED,
        "device": REQUIRED_DEVICE,
        "existing_activation_index": {
            "byte_size": EXISTING_ACTIVATION_INDEX_BYTE_SIZE,
            "row_count": EXISTING_ACTIVATION_ROW_COUNT,
            "sha256": EXISTING_ACTIVATION_INDEX_SHA256,
        },
        "existing_pilot_reextraction_authorized": False,
        "existing_pilot_reused": EXISTING_PILOT,
        "hidden_state_interpretation_authorized": False,
        "local_scientific_execution_performed": False,
        "no_wall_control_pilot_ids": no_wall_control_ids(),
        "ordered_pilot_ids": ordered_pilot_ids(),
        "person_b_selection_commit": PERSON_B_SELECTION_COMMIT,
        "person_c_acceptance_commit": PERSON_C_ACCEPTANCE_COMMIT,
        "runner_version": RUNNER_VERSION,
        "sagemaker_command": SAGEMAKER_COMMAND,
        "sequential_steps_per_additional_pilot": list(PHASE6_STEPS),
        "step_6_6_complete": False,
        "total_pilot_count": len(PILOT_SPECS),
    }


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    return single._sha256_file(path)


def _git_bytes(repository: Path, expression: str) -> bytes:
    return single._git_object_bytes(repository, expression)


def _git_json(repository: Path, expression: str) -> tuple[bytes, dict[str, Any]]:
    raw = _git_bytes(repository, expression)
    try:
        document = json.loads(raw)
    except (UnicodeError, json.JSONDecodeError) as error:
        fail(f"Git object is not valid JSON ({expression}): {error}")
    if not isinstance(document, dict):
        fail(f"Git object must contain one JSON object: {expression}")
    return raw, document


def _validate_package_inventory(
    repository: Path,
    *,
    commit: str,
    package_root: str,
    inventory: Mapping[str, Any],
) -> None:
    files = inventory.get("files")
    if not isinstance(files, Mapping):
        fail("Person C package inventory must be a name-to-SHA256 mapping")
    for name, expected in files.items():
        raw = _git_bytes(repository, f"{commit}:{package_root}/{name}")
        if _sha256_bytes(raw) != expected:
            fail(f"Person C package inventory mismatch: {name}")


def load_authority_documents(repository: Path) -> dict[str, Any]:
    """Read and validate the exact B and C authority objects."""

    for revision in (
        PERSON_A_STARTING_COMMIT,
        PERSON_B_SELECTION_COMMIT,
        PERSON_C_ACCEPTANCE_COMMIT,
        PERSON_E_REGISTRY_V2_COMMIT,
    ):
        if not single._git_commit_exists(repository, revision):
            fail(f"required authority commit is unavailable: {revision}")

    b_raw, selection = _git_json(
        repository, f"{PERSON_B_SELECTION_COMMIT}:{B_SELECTION_REL}"
    )
    c_manifest_raw, accepted = _git_json(
        repository, f"{PERSON_C_ACCEPTANCE_COMMIT}:{C_ACCEPTED_MANIFEST_REL}"
    )
    _decision_raw, decision = _git_json(
        repository, f"{PERSON_C_ACCEPTANCE_COMMIT}:{C_DECISION_REL}"
    )
    _validation_raw, validation = _git_json(
        repository, f"{PERSON_C_ACCEPTANCE_COMMIT}:{C_VALIDATION_REL}"
    )
    _inventory_raw, inventory = _git_json(
        repository, f"{PERSON_C_ACCEPTANCE_COMMIT}:{C_INVENTORY_REL}"
    )
    _validate_package_inventory(
        repository,
        commit=PERSON_C_ACCEPTANCE_COMMIT,
        package_root=C_PACKAGE_ROOT,
        inventory=inventory,
    )

    if selection.get("ordered_pilot_ids") != ordered_pilot_ids():
        fail("Person B ordered selection differs from the frozen runner plan")
    if selection.get("no_wall_control_pilot_ids") != no_wall_control_ids():
        fail("Person B no-wall control identities differ from the runner plan")
    selected_rows = selection.get("pilots")
    if not isinstance(selected_rows, list) or len(selected_rows) != len(PILOT_SPECS):
        fail("Person B detailed selection rows are incomplete")
    for spec, row in zip(PILOT_SPECS, selected_rows, strict=True):
        expected = {
            "trajectory_id": spec.trajectory_id,
            "layout_id": spec.layout_id,
            "fold_idx": spec.fold_idx,
            "condition_role": spec.condition_role,
            "control": spec.control,
            "frame_count": spec.frame_count,
            "requires_person_a_processing": spec.requires_processing,
        }
        if any(row.get(key) != value for key, value in expected.items()):
            fail(f"Person B pilot metadata drift: {spec.trajectory_id}")
        capture = row.get("capture_package", {})
        if (
            capture.get("sha256") != spec.capture_package_sha256
            or capture.get("byte_size") != spec.capture_package_byte_size
        ):
            fail(f"Person B capture identity drift: {spec.trajectory_id}")

    if (
        accepted.get("accepted_pilot_count") != 10
        or accepted.get("newly_accepted_pilot_count") != 9
        or accepted.get("accepted_placeholder_count") != 0
        or accepted.get("ordered_pilot_ids") != ordered_pilot_ids()
    ):
        fail("Person C accepted manifest does not exactly match Person B")
    intakes = accepted.get("intake_rows")
    if not isinstance(intakes, list) or len(intakes) != 10:
        fail("Person C accepted manifest has an incomplete intake list")
    for spec, row in zip(PILOT_SPECS, intakes, strict=True):
        if (
            row.get("trajectory_id") != spec.trajectory_id
            or row.get("capture_package_sha256") != spec.capture_package_sha256
            or row.get("capture_package_byte_size") != spec.capture_package_byte_size
            or row.get("frame_count") != spec.frame_count
            or row.get("strict_capture_validator_accepted") is not True
        ):
            fail(f"Person C intake identity drift: {spec.trajectory_id}")
    if (
        decision.get("ordered_accepted_pilot_ids") != ordered_pilot_ids()
        or decision.get("person_a_expansion_execution_authorized") is not False
        or validation.get("status") != "PASS"
        or validation.get("accepted_placeholder_count") != 0
        or validation.get("all_required_pilots_accepted") is not True
    ):
        fail("Person C acceptance decision or validation boundary is invalid")
    return {
        "accepted_manifest": accepted,
        "accepted_manifest_bytes": c_manifest_raw,
        "b_selection": selection,
        "b_selection_sha256": _sha256_bytes(b_raw),
    }


def validate_authorization_document(
    document: Mapping[str, Any], *, current_commit: str
) -> None:
    expected = {
        "decision": "AUTHORIZE_PERSON_A_PHASE6_TEN_PILOT_EXPANSION_EXECUTION",
        "owner": "person_b",
        "person_a_expansion_execution_authorized": True,
        "person_a_expansion_runner_commit": current_commit,
        "person_b_selection_commit": PERSON_B_SELECTION_COMMIT,
        "person_c_expansion_acceptance_commit": PERSON_C_ACCEPTANCE_COMMIT,
        "ordered_pilot_ids": ordered_pilot_ids(),
        "authorized_additional_pilot_ids": [
            spec.trajectory_id for spec in additional_pilot_specs()
        ],
        "authorized_steps": list(PHASE6_STEPS),
        "execution_host": "aws_sagemaker_linux_gpu",
        "device": REQUIRED_DEVICE,
        "seed": DETERMINISTIC_SEED,
        "existing_pilot_reused": EXISTING_PILOT,
        "existing_pilot_reextraction_authorized": False,
        "hidden_state_interpretation_authorized": False,
        "step_6_6_complete": False,
        "future_registry_v2_output_acceptance_authorized": False,
        "u4_output_inspected": False,
        "sagemaker_command": SAGEMAKER_COMMAND,
    }
    for field, value in expected.items():
        if document.get(field) != value:
            fail(f"Person B expansion authorization field {field!r} must equal {value!r}")


def verify_authorization_object(
    repository: Path, expression: str, *, current_commit: str
) -> dict[str, Any]:
    if not expression or ":" not in expression:
        fail("exact <commit>:<path> Person B expansion authorization is required")
    commit, _, path = expression.partition(":")
    if len(commit) != 40 or not path or not single._git_commit_exists(repository, commit):
        fail("Person B expansion authorization commit/path does not resolve")
    raw, document = _git_json(repository, expression)
    validate_authorization_document(document, current_commit=current_commit)
    return {
        "commit": commit,
        "git_object": expression,
        "sha256": _sha256_bytes(raw),
        "verified": True,
    }


def _safe_store_file(root: Path, relative: str) -> Path:
    path = root / Path(relative)
    if path.is_symlink() or not path.is_file():
        fail(f"existing activation artifact is missing or not an ordinary file: {relative}")
    try:
        path.resolve(strict=True).relative_to(root.resolve(strict=True))
    except ValueError:
        fail(f"existing activation artifact escapes its approved root: {relative}")
    return path


def validate_existing_artifacts(
    root: Path,
    *,
    expected_index_sha256: str = EXISTING_ACTIVATION_INDEX_SHA256,
    expected_index_byte_size: int = EXISTING_ACTIVATION_INDEX_BYTE_SIZE,
    expected_row_count: int = EXISTING_ACTIVATION_ROW_COUNT,
    expected_pilot: str = EXISTING_PILOT,
) -> dict[str, Any]:
    """Validate the existing pilot index and every referenced chunk exactly."""

    if root.is_symlink() or not root.is_dir():
        fail("existing activation-store root must be an ordinary directory")
    index_path = _safe_store_file(root, EXISTING_ACTIVATION_INDEX_REL)
    raw = index_path.read_bytes()
    if len(raw) != expected_index_byte_size or _sha256_bytes(raw) != expected_index_sha256:
        fail("existing activation index hash or size differs from the completed pilot")
    try:
        index = json.loads(raw)
    except (UnicodeError, json.JSONDecodeError) as error:
        fail(f"existing activation index is invalid JSON: {error}")
    rows = index.get("index_rows")
    chunks = index.get("chunks")
    if (
        index.get("format_version") != single.ACTIVATION_INDEX_V2_FORMAT_VERSION
        or index.get("run_status") != "completed"
        or not isinstance(rows, list)
        or len(rows) != expected_row_count
        or not isinstance(chunks, list)
    ):
        fail("existing activation index structure or cardinality is invalid")
    if any(row.get("trajectory_id") != expected_pilot for row in rows):
        fail("existing activation index contains an unexpected pilot")
    verified_chunks = []
    for chunk in chunks:
        path = _safe_store_file(root, chunk["path"])
        if path.stat().st_size != chunk["byte_size"] or _sha256_file(path) != chunk["sha256"]:
            fail(f"existing activation chunk identity mismatch: {chunk['path']}")
        verified_chunks.append({
            "byte_size": chunk["byte_size"],
            "chunk_id": chunk["chunk_id"],
            "path": str(path),
            "row_count": chunk["row_count"],
            "sha256": chunk["sha256"],
        })
    return {
        "index": index,
        "inventory": {
            "activation_index": {
                "byte_size": len(raw),
                "path": str(index_path),
                "sha256": _sha256_bytes(raw),
            },
            "activation_row_count": len(rows),
            "chunks": verified_chunks,
            "existing_pilot_reextracted": False,
            "status": "REUSED_EXACT_EXISTING_ARTIFACTS",
            "trajectory_id": expected_pilot,
        },
    }


def _single_arguments(arguments: MultiRunnerArguments, session_id: str) -> single.RunnerArguments:
    return single.RunnerArguments(
        repository_root=arguments.repository_root,
        mineworld_root=arguments.mineworld_root,
        asset_root=arguments.asset_root,
        main_checkpoint=arguments.main_checkpoint,
        vae_config=arguments.vae_config,
        vae_checkpoint=arguments.vae_checkpoint,
        approved_input_root=arguments.approved_input_root,
        approved_output_root=arguments.approved_output_root,
        activation_store_v2_ratification_object=(
            arguments.person_b_expansion_authorization_object
        ),
        session_id=session_id,
        seed=arguments.seed,
        device=arguments.device,
        precision=arguments.precision,
    )


def runtime_preflight(arguments: MultiRunnerArguments) -> tuple[dict[str, Any], dict[str, Any]]:
    """Verify every authority, existing artifact, and SageMaker runtime gate."""

    single._validate_runtime_arguments(_single_arguments(arguments, arguments.session_id))
    if arguments.existing_artifact_root.is_symlink() or not arguments.existing_artifact_root.is_dir():
        fail("existing_artifact_root must be an existing absolute ordinary directory")
    if platform.system() != "Linux":
        fail("scientific execution is restricted to Linux SageMaker")
    repository = arguments.repository_root
    branch = single._run_git(repository, "branch", "--show-current")
    current_commit = str(single._run_git(repository, "rev-parse", "HEAD"))
    status = single._run_git(repository, "status", "--porcelain=v1", "-uall")
    if branch != REQUIRED_BRANCH or status:
        fail("Person A checkout must be the exact clean role branch")
    authorities = load_authority_documents(repository)
    authorization = verify_authorization_object(
        repository,
        arguments.person_b_expansion_authorization_object,
        current_commit=current_commit,
    )
    existing = validate_existing_artifacts(arguments.existing_artifact_root)

    mineworld_commit = single._run_git(arguments.mineworld_root, "rev-parse", "HEAD")
    mineworld_status = single._run_git(
        arguments.mineworld_root, "status", "--porcelain=v1", "-uall"
    )
    if mineworld_commit != single.MINEWORLD_REVISION or mineworld_status:
        fail("MineWorld checkout must be exact and clean")
    model_config_blob = _git_bytes(
        arguments.mineworld_root,
        f"{single.MINEWORLD_REVISION}:{single.MODEL_CONFIG_PATH}",
    )
    physical_model_config = single.validated_physical_model_config_path(
        mineworld_root=arguments.mineworld_root,
        git_blob_bytes=model_config_blob,
    )
    observed_files = {
        "main_checkpoint": _sha256_file(arguments.main_checkpoint),
        "vae_config": _sha256_file(arguments.vae_config),
        "vae_checkpoint": _sha256_file(arguments.vae_checkpoint),
    }
    expected_files = {
        "main_checkpoint": single.MAIN_CHECKPOINT_SHA256,
        "vae_config": single.VAE_CONFIG_SHA256,
        "vae_checkpoint": single.VAE_CHECKPOINT_SHA256,
    }
    if observed_files != expected_files:
        fail("checkpoint or VAE bytes differ from frozen identities")
    free_disk = shutil.disk_usage(arguments.approved_output_root).free
    if free_disk < single.MINIMUM_FREE_DISK_BYTES:
        fail("approved output root has insufficient free disk")
    torch = importlib.import_module("torch")
    if not torch.cuda.is_available() or torch.cuda.device_count() < 1:
        fail("torch cuda:0 is required")
    properties = torch.cuda.get_device_properties(0)
    if int(properties.total_memory) < single.MINIMUM_GPU_MEMORY_BYTES:
        fail("cuda:0 exposes insufficient memory")
    torch.cuda.set_device(0)
    if torch.cuda.current_device() != 0:
        fail("selected CUDA device is not cuda:0")
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
        fail("nvidia-smi identity query must succeed")
    receipt = {
        "authorization": authorization,
        "branch": branch,
        "cuda": {
            "device": REQUIRED_DEVICE,
            "device_count": int(torch.cuda.device_count()),
            "device_name": str(properties.name),
            "total_memory_bytes": int(properties.total_memory),
        },
        "existing_pilot_validation": existing["inventory"],
        "frozen_file_sha256": observed_files,
        "free_disk_bytes": free_disk,
        "git_commit": current_commit,
        "git_worktree_clean": True,
        "mineworld_commit": mineworld_commit,
        "model_config_physical_path": str(physical_model_config),
        "nvidia_smi": nvidia.stdout.strip().splitlines(),
        "person_b_selection_commit": PERSON_B_SELECTION_COMMIT,
        "person_c_acceptance_commit": PERSON_C_ACCEPTANCE_COMMIT,
        "runner_version": RUNNER_VERSION,
        "seed": arguments.seed,
        "status": "PASS",
    }
    return receipt, {**authorities, "existing": existing}


def _repo_relative_from_declared(declared_path: str) -> str:
    normalized = declared_path.replace("\\", "/")
    marker = "/data/autonomous/"
    if marker not in normalized:
        fail(f"C direct input does not resolve to the autonomous data tree: {declared_path}")
    return "data/autonomous/" + normalized.split(marker, 1)[1]


def step6_1_intake(
    context: single.RunContext,
    *,
    spec: PilotSpec,
    accepted_manifest: Mapping[str, Any],
    accepted_manifest_bytes: bytes,
) -> dict[str, Any]:
    """Materialize exactly one newly accepted C pilot from Git objects."""

    intake = next(
        row for row in accepted_manifest["intake_rows"]
        if row["trajectory_id"] == spec.trajectory_id
    )
    capture_path = intake["capture_package_path"]
    capture_bytes = _git_bytes(
        context.arguments.repository_root,
        f"{PERSON_C_ACCEPTANCE_COMMIT}:{capture_path}",
    )
    if (
        len(capture_bytes) != spec.capture_package_byte_size
        or _sha256_bytes(capture_bytes) != spec.capture_package_sha256
    ):
        fail(f"C capture package identity drift: {spec.trajectory_id}")
    package = json.loads(capture_bytes)
    role_map = {
        "frame_map": "frame_map",
        "media": "media",
        "normalized_actions": "normalized_actions",
        "raw_actions": "raw_actions",
        "state": "server_state",
        "visibility": "visibility",
    }
    payloads = {
        "accepted_manifest": accepted_manifest_bytes,
        "capture_package": capture_bytes,
    }
    observed = {}
    for output_role, artifact_role in role_map.items():
        evidence = intake["verified_artifacts"][artifact_role]
        relative = _repo_relative_from_declared(evidence["declared_path"])
        raw = _git_bytes(
            context.arguments.repository_root,
            f"{PERSON_C_ACCEPTANCE_COMMIT}:{relative}",
        )
        if len(raw) != evidence["byte_size"] or _sha256_bytes(raw) != evidence["sha256"]:
            fail(f"C direct input identity drift: {spec.trajectory_id}:{artifact_role}")
        payloads[output_role] = raw
        observed[output_role] = evidence["sha256"]

    intake_root = context.arguments.approved_input_root / context.arguments.session_id
    if intake_root.exists() or intake_root.is_symlink():
        fail(f"immutable approved intake already exists: {intake_root}")
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
    materialized = {}
    for name, filename in output_names.items():
        destination = intake_root / filename
        single._exclusive_write(destination, payloads[name])
        materialized[name] = destination
    model_config_bytes = _git_bytes(
        context.arguments.mineworld_root,
        f"{single.MINEWORLD_REVISION}:{single.MODEL_CONFIG_PATH}",
    )
    config_path = intake_root / "700M_16f.git-blob.yaml"
    single._exclusive_write(config_path, model_config_bytes)
    context.state.update({
        "accepted_manifest": dict(accepted_manifest),
        "capture_package": package,
        "input_paths": materialized,
        "model_config_provenance_path": config_path,
        "payloads": payloads,
    })
    return {
        "capture_package_sha256": spec.capture_package_sha256,
        "direct_input_hashes": observed,
        "frame_count": spec.frame_count,
        "input_root": str(intake_root),
        "pilot": spec.trajectory_id,
        "status": "PASS",
    }


@contextlib.contextmanager
def _single_pilot_constants(spec: PilotSpec, intake: Mapping[str, Any]):
    replacements = {
        "SELECTED_PILOT": spec.trajectory_id,
        "GLOBAL_MODEL_FRAME_COUNT": spec.frame_count,
        "EXPECTED_ACTIVATION_ROW_COUNT": spec.expected_activation_rows,
        "C_CAPTURE_PACKAGE_SHA256": spec.capture_package_sha256,
        "C_FRAME_MAP_SHA256": intake["verified_artifacts"]["frame_map"]["sha256"],
        "C_STATE_SHA256": intake["verified_artifacts"]["server_state"]["sha256"],
    }
    prior = {name: getattr(single, name) for name in replacements}
    for name, value in replacements.items():
        setattr(single, name, value)
    try:
        yield
    finally:
        for name, value in prior.items():
            setattr(single, name, value)


def _new_pilot_inventory(
    spec: PilotSpec, context: single.RunContext
) -> tuple[dict[str, Any], dict[str, Any]]:
    snapshot = context.state["activation_snapshot"]
    store_root = context.state["activation_store_root"]
    index_path = store_root / snapshot.relative_path
    chunks = [
        {
            "byte_size": chunk.byte_size,
            "chunk_id": chunk.chunk_id,
            "path": str(store_root / chunk.path),
            "row_count": chunk.row_count,
            "sha256": chunk.sha256,
        }
        for chunk in snapshot.chunks
    ]
    inventory = {
        "activation_index": {
            "byte_size": index_path.stat().st_size,
            "path": str(index_path),
            "sha256": _sha256_file(index_path),
        },
        "activation_row_count": len(snapshot.index_rows),
        "chunks": chunks,
        "condition_role": spec.condition_role,
        "control": spec.control,
        "expected_activation_row_count": spec.expected_activation_rows,
        "fold_idx": spec.fold_idx,
        "frame_count": spec.frame_count,
        "layout_id": spec.layout_id,
        "status": "PASS",
        "trajectory_id": spec.trajectory_id,
    }
    source = {
        "index_rows": [dict(row) for row in snapshot.index_rows],
        "inventory": inventory,
        "trajectory_id": spec.trajectory_id,
    }
    return inventory, source


def run_additional_pilot(
    arguments: MultiRunnerArguments,
    multi_root: Path,
    runtime_receipt: Mapping[str, Any],
    authorities: Mapping[str, Any],
    spec: PilotSpec,
) -> dict[str, Any]:
    """Run Steps 6.1-6.5 for one new pilot and stop at its first failure."""

    session_id = f"{arguments.session_id}-{spec.trajectory_id}"
    pilot_root = multi_root / "pilots" / spec.trajectory_id
    pilot_root.mkdir(parents=True)
    pilot_receipt = {**runtime_receipt, "selected_pilot": spec.trajectory_id}
    single._write_json(pilot_root / "runtime_preflight_receipt.json", pilot_receipt)
    single_arguments = _single_arguments(arguments, session_id)
    context = single.RunContext(
        arguments=single_arguments,
        session_root=pilot_root,
        runtime_receipt=dict(pilot_receipt),
    )
    accepted = authorities["accepted_manifest"]
    intake = next(
        row for row in accepted["intake_rows"]
        if row["trajectory_id"] == spec.trajectory_id
    )
    with _single_pilot_constants(spec, intake):
        sequence = single.execute_step_sequence(
            context,
            {
                "6.1": lambda ctx: step6_1_intake(
                    ctx,
                    spec=spec,
                    accepted_manifest=accepted,
                    accepted_manifest_bytes=authorities["accepted_manifest_bytes"],
                ),
                "6.2": single.step6_2_model_boundary,
                "6.3": single.step6_3_tokenize,
                "6.4": single.step6_4_extract_store,
                "6.5": single.step6_5_certify,
            },
        )
    report = {
        "completed_steps": sequence["completed_steps"],
        "failed_step": sequence["failed_step"],
        "failure": sequence["failure"],
        "later_steps_executed_after_failure": False,
        "pilot": spec.trajectory_id,
        "status": sequence["status"],
        "step_receipts": context.step_receipts,
    }
    inventory = None
    source = None
    if sequence["status"] == "PASS":
        inventory, source = _new_pilot_inventory(spec, context)
        report["inventory"] = inventory
    single._write_json(pilot_root / "final_report.json", report)
    return {"report": report, "inventory": inventory, "source": source}


def execute_additional_pilot_sequence(
    specs: Sequence[PilotSpec],
    executor: Callable[[PilotSpec], Mapping[str, Any]],
) -> dict[str, Any]:
    """Stop the expansion at the first failed pilot and preserve prior passes."""

    successful = []
    results = []
    failed_pilot = None
    for spec in specs:
        result = dict(executor(spec))
        results.append(result)
        report = result.get("report", result)
        if report.get("status") != "PASS":
            failed_pilot = spec.trajectory_id
            break
        successful.append(spec.trajectory_id)
    return {
        "failed_pilot": failed_pilot,
        "later_pilots_executed_after_failure": False,
        "results": results,
        "status": "PASS" if failed_pilot is None else "FAIL",
        "successful_pilots": successful,
    }


def build_combined_index(
    sources: Sequence[Mapping[str, Any]],
    *,
    expected_row_count: int | None = None,
) -> dict[str, Any]:
    """Combine exact per-pilot rows in B order and reject identity collisions."""

    expected_order = ordered_pilot_ids()
    if [source["trajectory_id"] for source in sources] != expected_order:
        fail("combined activation sources do not preserve exact Person B order")
    rows = []
    seen = set()
    per_pilot = []
    for source in sources:
        pilot_id = source["trajectory_id"]
        source_rows = sorted(
            (dict(row) for row in source["index_rows"]),
            key=lambda row: (
                int(row["global_model_frame_idx"]),
                int(row["layer_idx"]),
                int(row["context_local_pair_idx"]),
            ),
        )
        for row in source_rows:
            if row.get("trajectory_id") != pilot_id:
                fail(f"combined index row pilot mismatch: {pilot_id}")
            local_idx = row.get("context_local_pair_idx")
            if not isinstance(local_idx, int) or not 0 <= local_idx <= 15:
                fail(f"combined index lost context-local identity: {pilot_id}")
            key = (
                row["trajectory_id"],
                row["global_model_frame_idx"],
                row["source_frame_id"],
                row["source_tick"],
                row["layer_idx"],
                row["hook_site"],
                row["checkpoint_hash"],
                row["preprocess_hash"],
            )
            if key in seen:
                fail(f"combined activation identity collision: {key}")
            seen.add(key)
            rows.append(row)
        per_pilot.append({
            "activation_index": source["inventory"]["activation_index"],
            "activation_row_count": len(source_rows),
            "trajectory_id": pilot_id,
        })
    expected_rows = (
        sum(spec.expected_activation_rows for spec in PILOT_SPECS)
        if expected_row_count is None
        else expected_row_count
    )
    if len(rows) != expected_rows:
        fail(f"combined activation cardinality {len(rows)} != {expected_rows}")
    return {
        "activation_index_format_version": "person-a-multi-pilot-activation-index-v1",
        "activation_store_format_version": single.ACTIVATION_STORE_V2_FORMAT_VERSION,
        "combined_activation_row_count": len(rows),
        "creation_timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "index_rows": rows,
        "no_wall_control_pilot_ids": no_wall_control_ids(),
        "ordered_pilot_ids": expected_order,
        "per_pilot_indexes": per_pilot,
        "schema_version": "1.0",
        "scientific_identity_collision_count": 0,
    }


def _existing_source(existing: Mapping[str, Any]) -> dict[str, Any]:
    spec = PILOT_SPECS[0]
    inventory = {
        **existing["inventory"],
        "condition_role": spec.condition_role,
        "control": spec.control,
        "expected_activation_row_count": spec.expected_activation_rows,
        "fold_idx": spec.fold_idx,
        "frame_count": spec.frame_count,
        "layout_id": spec.layout_id,
    }
    return {
        "index_rows": [dict(row) for row in existing["index"]["index_rows"]],
        "inventory": inventory,
        "trajectory_id": EXISTING_PILOT,
    }


def _write_success_handoffs(
    multi_root: Path,
    combined: Mapping[str, Any],
    sources: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    combined_path = multi_root / "combined_activation_index.json"
    single._write_json(combined_path, combined)
    combined_identity = {
        "byte_size": combined_path.stat().st_size,
        "path": str(combined_path),
        "sha256": _sha256_file(combined_path),
    }
    inventory_root = multi_root / "per_pilot_inventories"
    inventory_root.mkdir()
    inventory_identities = []
    for source in sources:
        path = inventory_root / f"{source['trajectory_id']}.json"
        single._write_json(path, source["inventory"])
        inventory_identities.append({
            "byte_size": path.stat().st_size,
            "path": str(path),
            "sha256": _sha256_file(path),
            "trajectory_id": source["trajectory_id"],
        })
    by_id = {source["trajectory_id"]: source for source in sources}
    b_handoff = {
        "combined_activation_index": combined_identity,
        "hidden_state_interpretation_authorized": False,
        "no_wall_control_inputs": [
            by_id[pilot_id]["inventory"] for pilot_id in no_wall_control_ids()
        ],
        "person_b_step_6_6_control_execution_complete": False,
        "schema_version": "1.0",
        "status": "READY_FOR_PERSON_B_POSITIVE_CONTROL_NOT_EXECUTED",
        "step": "6.6_positive_control_handoff",
    }
    b_path = multi_root / "person_b_step6_6_positive_control_handoff.json"
    single._write_json(b_path, b_handoff)
    e_handoff = {
        "combined_activation_index": combined_identity,
        "future_registry_v2_output_acceptance_authorized": False,
        "per_pilot_inventories": inventory_identities,
        "person_e_registry_v2_validator_commit": PERSON_E_REGISTRY_V2_COMMIT,
        "registry_v2_acceptance_claimed": False,
        "schema_version": "1.0",
        "status": "PROVENANCE_HANDOFF_PREPARED_NOT_ACCEPTED",
    }
    e_path = multi_root / "person_e_provenance_handoff.json"
    single._write_json(e_path, e_handoff)
    return {
        "combined_activation_index": combined_identity,
        "person_b_handoff": {
            "path": str(b_path), "sha256": _sha256_file(b_path)
        },
        "person_e_handoff": {
            "path": str(e_path), "sha256": _sha256_file(e_path)
        },
    }


def run(arguments: MultiRunnerArguments) -> int:
    """Execute the exact authorized nine-pilot expansion on SageMaker."""

    runtime_receipt, authorities = runtime_preflight(arguments)
    multi_root = arguments.approved_output_root / arguments.session_id
    if multi_root.exists() or multi_root.is_symlink():
        fail("immutable multi-pilot session directory already exists")
    multi_root.mkdir()
    single._write_json(multi_root / "runtime_preflight_receipt.json", runtime_receipt)

    existing_source = _existing_source(authorities["existing"])
    sequence = execute_additional_pilot_sequence(
        additional_pilot_specs(),
        lambda spec: run_additional_pilot(
            arguments, multi_root, runtime_receipt, authorities, spec
        ),
    )
    handoffs = None
    if sequence["status"] == "PASS":
        new_sources = [result["source"] for result in sequence["results"]]
        sources = [existing_source, *new_sources]
        combined = build_combined_index(sources)
        handoffs = _write_success_handoffs(multi_root, combined, sources)
    report = {
        "additional_pilot_count": len(additional_pilot_specs()),
        "existing_pilot_reextracted": False,
        "existing_pilot_reused": EXISTING_PILOT,
        "handoffs": handoffs,
        "hidden_state_interpretation_authorized": False,
        "ordered_pilot_ids": ordered_pilot_ids(),
        "person_b_step_6_6_control_execution_complete": False,
        "runner_version": RUNNER_VERSION,
        "scientific_execution_environment": "aws_sagemaker_linux_gpu",
        "sequence": sequence,
        "status": sequence["status"],
    }
    single._write_json(multi_root / "final_report.json", report)
    print(json.dumps(report, sort_keys=True, allow_nan=False))
    return 0 if sequence["status"] == "PASS" else 1


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="operation", required=True)
    subparsers.add_parser("plan", help="print preparation-only multi-pilot plan")
    execute = subparsers.add_parser("run", help="execute on authorized SageMaker GPU only")
    execute.add_argument("--repository-root", type=Path, required=True)
    execute.add_argument("--mineworld-root", type=Path, required=True)
    execute.add_argument("--asset-root", type=Path, required=True)
    execute.add_argument("--main-checkpoint", type=Path, required=True)
    execute.add_argument("--vae-config", type=Path, required=True)
    execute.add_argument("--vae-checkpoint", type=Path, required=True)
    execute.add_argument("--approved-input-root", type=Path, required=True)
    execute.add_argument("--approved-output-root", type=Path, required=True)
    execute.add_argument("--existing-artifact-root", type=Path, required=True)
    execute.add_argument("--person-b-expansion-authorization-object", required=True)
    execute.add_argument("--session-id", required=True)
    execute.add_argument("--seed", type=int, required=True)
    execute.add_argument("--device", required=True)
    execute.add_argument("--precision", required=True)
    return parser


def _arguments(namespace: argparse.Namespace) -> MultiRunnerArguments:
    return MultiRunnerArguments(
        repository_root=namespace.repository_root.resolve(),
        mineworld_root=namespace.mineworld_root.resolve(),
        asset_root=namespace.asset_root.resolve(),
        main_checkpoint=namespace.main_checkpoint.resolve(),
        vae_config=namespace.vae_config.resolve(),
        vae_checkpoint=namespace.vae_checkpoint.resolve(),
        approved_input_root=namespace.approved_input_root.resolve(),
        approved_output_root=namespace.approved_output_root.resolve(),
        existing_artifact_root=namespace.existing_artifact_root.resolve(),
        person_b_expansion_authorization_object=(
            namespace.person_b_expansion_authorization_object
        ),
        session_id=namespace.session_id,
        seed=namespace.seed,
        device=namespace.device,
        precision=namespace.precision,
    )


def main(argv: list[str] | None = None) -> int:
    namespace = _parser().parse_args(argv)
    if namespace.operation == "plan":
        print(json.dumps(plan_document(), indent=2, sort_keys=True, allow_nan=False))
        return 0
    try:
        return run(_arguments(namespace))
    except (MultiPilotRunnerError, single.Phase6RunnerError) as error:
        failure = {
            "error": str(error),
            "runner_version": RUNNER_VERSION,
            "status": "FAIL",
        }
        print(json.dumps(failure, sort_keys=True, allow_nan=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
