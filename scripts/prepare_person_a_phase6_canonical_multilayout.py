#!/usr/bin/env python3
"""Prepare and collect the minimal canonical C6A multi-layout successor.

The local ``prepare`` and ``verify-input`` operations never import torch, query
CUDA, decode media, or extract activations.  ``run-missing`` is the explicit
SageMaker-only continuation: it reuses the certified layout_01 result, runs
only the four missing trajectories through the existing one-trajectory
runner, and publishes a collection of five immutable activation indexes.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import time
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from types import SimpleNamespace
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SINGLE_RUNNER_PATH = ROOT / "scripts/run_person_a_phase6_single_pilot_sagemaker.py"
SINGLE_PREP_PATH = ROOT / "scripts/prepare_person_a_phase6_canonical_sagemaker.py"


def _load_module(path: Path, name: str) -> Any:
    specification = importlib.util.spec_from_file_location(name, path)
    if specification is None or specification.loader is None:
        raise RuntimeError(f"module is unavailable: {path}")
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


single_runner = _load_module(SINGLE_RUNNER_PATH, "person_a_multilayout_single_runner")
single_prep = _load_module(SINGLE_PREP_PATH, "person_a_multilayout_single_prep")

SCHEMA_VERSION = "person-a-canonical-c6a-multilayout-preparation-v0.1"
SELECTION_SCHEMA = "person-a-canonical-c6a-multilayout-selection-v0.1"
INPUT_SCHEMA = "person-a-canonical-c6a-multilayout-sagemaker-input-v0.1"
COLLECTION_SCHEMA = "person-a-canonical-c6a-multirun-collection-v0.1"
B_HANDOFF_SCHEMA = "person-a-to-person-b-canonical-multilayout-handoff-v0.1"
E_HANDOFF_SCHEMA = "person-a-to-person-e-canonical-multilayout-handoff-v0.1"

PERSON_A_BRANCH = "role/person-a-model"
PERSON_A_STARTING_HEAD = "89c1949976f8b8db6efaace66fd2ada4d1b93b3d"
PERSON_B_BRANCH = "role/person-b-analysis"
PERSON_B_BLOCKER_COMMIT = "66279eee242a353423e1b084bdfa39f480274909"
PERSON_C_BRANCH = "completion/person-c-c1-c6a"
PERSON_C_COMMIT = "b810bae554ba4f31018d39beb304c9b936387ca4"
PERSON_E_BRANCH = "completion/person-e-homography-refit-v0.4"
PERSON_E_RECEIPT_COMMIT = "14ff11b25b8a740e490b680a16c8473ebb7c7dc6"

C6A_ID = "person-c-c6a-post-c1-v0.1"
C6A_PACKAGE_SHA256 = "612b03fea372d10c5f5b87cb581dd5f993035112e16aa1de7341801bdc35a9ef"
E_REGISTRY_SHA256 = "77c105176bdb4d93382b36b3131267848acab6fbdc181f1d8272080e0ad5d588"
E_C6A_HANDOFF_SHA256 = (
    "e2897aac65a8b51893f1ef397af26cdc7958fe89e6d2bd0159082a9547d253d1"
)
E_CURRENT_RECEIPT_SHA256 = (
    "1d4fb69ec6b5693cfafc56eaeb11fe6bedbb1bfa9fe420de5f288a9ad544c7f4"
)
B_BLOCKER_RECEIPT_SHA256 = (
    "6e777d11273bf25267b694b551eb2627dc6dc30f6226988cced4bc0134a45fe8"
)
CURRENT_OUTPUT_MANIFEST_SHA256 = (
    "e03251f2a8e7f7546b354db411f801c0908739d5929e0a9475ee04ddc903b72b"
)
CURRENT_ACTIVATION_INDEX_SHA256 = (
    "a6ba07a50ff20e9b90f0b036a0acd18783bad4fa3aacbebc0dd70df825f00a27"
)
CURRENT_ACCEPTED_MANIFEST_SHA256 = (
    "e6716f4fbe015ebb098da2a6fb800c636cc9eac1a56dcbe1d7543ab377c7a40d"
)
CURRENT_A_TO_B_SHA256 = (
    "da875c21a2875338eb432ba85f0c185ee02f4676178b3a3487fe95b55f4c50da"
)
CURRENT_A_TO_E_SHA256 = (
    "7414956699d9d37f0b4b486b7c800ff2482b453ffd634cb2bf99d92bcb042cfe"
)

CURRENT_TRAJECTORY = "layout_01_ep12602"
CURRENT_EPISODE = 12602
CURRENT_LAYOUT = "layout_01"
NEW_TRAJECTORIES = (
    ("layout_02", 12610),
    ("layout_03", 12645),
    ("layout_04", 12626),
    ("layout_05", 12634),
)
SELECTED_TRAJECTORIES = ((CURRENT_LAYOUT, CURRENT_EPISODE), *NEW_TRAJECTORIES)
EXPECTED_ROWS_PER_TRAJECTORY = 1_200
EXPECTED_CHUNKS_PER_TRAJECTORY = 20
EXPECTED_TOTAL_ROWS = 6_000
EXPECTED_TOTAL_CHUNKS = 100

REQUIRED_LAYOUT_COUNT = 5
REQUIRED_TRAJECTORY_COUNT = 5
GROUPING_KEY = "layout_id"
TARGET_NAME = "x_true_blocks"
LABEL_SOURCE = "canonical_server_state.axis_pos"


class MultilayoutPreparationError(RuntimeError):
    """One fail-closed preparation or collection error."""


def _fail(message: str) -> None:
    raise MultilayoutPreparationError(message)


def _json_bytes(document: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(
            dict(document),
            allow_nan=False,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_object(path: Path, label: str) -> dict[str, Any]:
    try:
        document = json.loads(path.read_bytes())
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise MultilayoutPreparationError(f"could not read {label}: {error}") from error
    if not isinstance(document, dict):
        _fail(f"{label} must be a JSON object")
    return document


def _write_exclusive(path: Path, document: Mapping[str, Any]) -> None:
    if path.exists() or path.is_symlink():
        raise FileExistsError(f"immutable output already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(_json_bytes(document))
        handle.flush()
        os.fsync(handle.fileno())


def _copy_exclusive(source: Path, destination: Path) -> None:
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(f"immutable output already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with source.open("rb") as source_handle, destination.open("xb") as target:
        shutil.copyfileobj(source_handle, target, length=1024 * 1024)
        target.flush()
        os.fsync(target.fileno())
    if source.stat().st_size != destination.stat().st_size or _sha256_file(
        source
    ) != _sha256_file(destination):
        _fail(f"copied bytes differ: {source}")


def _descriptor(root: Path, path: Path, role: str) -> dict[str, Any]:
    return {
        "path": path.relative_to(root).as_posix(),
        "role": role,
        "sha256": _sha256_file(path),
        "size_bytes": path.stat().st_size,
    }


def _git(repository: Path, *arguments: str, check: bool = True) -> str:
    result = subprocess.run(
        ["git", "-C", str(repository), *arguments],
        check=False,
        capture_output=True,
        text=True,
    )
    if check and result.returncode != 0:
        _fail(
            f"git {' '.join(arguments)} failed in {repository}: {result.stderr.strip()}"
        )
    return result.stdout.strip()


def _require_branch_and_ancestor(
    repository: Path,
    *,
    branch: str,
    authority: str,
) -> dict[str, Any]:
    observed_branch = _git(repository, "branch", "--show-current")
    if observed_branch != branch:
        _fail(f"{repository} must be on {branch}, observed {observed_branch}")
    result = subprocess.run(
        [
            "git",
            "-C",
            str(repository),
            "merge-base",
            "--is-ancestor",
            authority,
            "HEAD",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        _fail(f"{repository} does not contain authority {authority}")
    return {
        "authority_commit": authority,
        "branch": branch,
        "head": _git(repository, "rev-parse", "HEAD"),
    }


def _component_path(package: Mapping[str, Any], c_root: Path, suffix: str) -> Path:
    rows = package.get("component_files")
    matches = (
        [
            row
            for row in rows
            if isinstance(row, Mapping) and str(row.get("path", "")).endswith(suffix)
        ]
        if isinstance(rows, list)
        else []
    )
    if len(matches) != 1:
        _fail(f"canonical package lacks one {suffix} descriptor")
    row = matches[0]
    path = (c_root / str(row["path"]).replace("/", os.sep)).resolve()
    if (
        not path.is_file()
        or path.is_symlink()
        or path.stat().st_size != row.get("size_bytes")
        or _sha256_file(path) != row.get("sha256")
    ):
        _fail(f"canonical component differs: {suffix}")
    return path


def _direct_arguments(
    *,
    trajectory_id: str,
    episode_id: int,
    c_package: Path,
    e_registry: Path,
    e_handoff: Path,
) -> Any:
    placeholder = SINGLE_RUNNER_PATH
    return single_runner.RunnerArguments(
        repository_root=ROOT,
        mineworld_root=ROOT,
        asset_root=ROOT,
        main_checkpoint=placeholder,
        vae_config=placeholder,
        vae_checkpoint=placeholder,
        approved_input_root=ROOT,
        approved_output_root=ROOT.parent,
        activation_store_v2_ratification_object="",
        session_id="multilayout-preparation-only",
        seed=single_runner.DETERMINISTIC_SEED,
        device=single_runner.REQUIRED_DEVICE,
        precision="float16",
        runtime_host=single_runner.CANONICAL_WINDOWS_RUNTIME_HOST,
        canonical_c6a_package=c_package,
        canonical_c6a_package_sha256=C6A_PACKAGE_SHA256,
        trajectory_id=trajectory_id,
        episode_id=episode_id,
        episode_artifact_manifest=e_registry,
        episode_artifact_manifest_sha256=E_REGISTRY_SHA256,
        person_e_provenance_handoff=e_handoff,
        person_e_provenance_handoff_sha256=E_C6A_HANDOFF_SHA256,
    )


def _preliminary_rejections(
    capture: Mapping[str, Any],
    inventory: Mapping[str, Any],
    registry: Mapping[str, Any],
) -> list[str]:
    reasons: list[str] = []
    if capture.get("scene") != "nowall" or capture.get("set") != "nowall":
        reasons.append("NOT_NO_WALL_VISIBLE_CONTROL")
    if inventory.get("status") != "PASS":
        reasons.append("EPISODE_NOT_COMPLETED_PASS")
    if any(
        inventory.get(field) != 60
        for field in (
            "frame_count",
            "client_tick_count",
            "action_row_count",
            "server_row_count",
        )
    ):
        reasons.append("SOURCE_CARDINALITY_NOT_60")
    if (
        inventory.get("target_check_valid") is not True
        or inventory.get("target_expected_count") != 1
        or inventory.get("target_observed_count") != 1
    ):
        reasons.append("TARGET_IDENTITY_OR_COUNT_INVALID")
    if (
        registry.get("record_status") != "accepted"
        or registry.get("byte_hashes_valid") is not True
        or registry.get("output_counts_valid") is not True
        or registry.get("output_schemas_valid") is not True
    ):
        reasons.append("PERSON_E_REGISTRY_RECORD_NOT_ACCEPTED")
    return reasons


def build_selection_record(
    *,
    a_root: Path,
    b_root: Path,
    c_root: Path,
    e_root: Path,
) -> dict[str, Any]:
    """Select exactly four missing trajectories by the frozen deterministic rule."""

    authorities = {
        "person_a": _require_branch_and_ancestor(
            a_root, branch=PERSON_A_BRANCH, authority=PERSON_A_STARTING_HEAD
        ),
        "person_b": _require_branch_and_ancestor(
            b_root, branch=PERSON_B_BRANCH, authority=PERSON_B_BLOCKER_COMMIT
        ),
        "person_c": _require_branch_and_ancestor(
            c_root, branch=PERSON_C_BRANCH, authority=PERSON_C_COMMIT
        ),
        "person_e": _require_branch_and_ancestor(
            e_root, branch=PERSON_E_BRANCH, authority=PERSON_E_RECEIPT_COMMIT
        ),
    }
    b_receipt = (
        b_root
        / "docs/status/person_b_canonical_positive_control_layout_01_ep12602_v0_1/b_to_a_receipt.json"
    )
    e_current_receipt = (
        e_root
        / "docs/status/person_e_a_activation_provenance_acceptance_v0_1/person_e_to_person_a_activation_provenance_receipt.json"
    )
    if _sha256_file(b_receipt) != B_BLOCKER_RECEIPT_SHA256:
        _fail("Person B blocker receipt hash differs")
    if _sha256_file(e_current_receipt) != E_CURRENT_RECEIPT_SHA256:
        _fail("Person E current receipt hash differs")
    blocker = _read_object(b_receipt, "Person B blocker receipt")
    if blocker.get("remaining_blockers") != [
        "FROZEN_LAYOUT_GROUPED_OOF_REQUIRES_5_LAYOUTS_BUT_CANONICAL_BUNDLE_HAS_1",
        "GROUPED_SHUFFLED_CONTROL_REQUIRES_AT_LEAST_2_TRAJECTORIES_BUT_CANONICAL_BUNDLE_HAS_1",
    ]:
        _fail("Person B blocker identities differ")
    if (
        blocker.get("fold_identities", {}).get("fold_count_required") != 5
        or blocker.get("fold_identities", {}).get("grouping_key") != GROUPING_KEY
        or blocker.get("label_authority", {}).get("label_source") != LABEL_SOURCE
        or blocker.get("label_authority", {}).get("target_name") != TARGET_NAME
        or blocker.get("probe_configuration", {}).get("inner_fold_count") != 4
        or blocker.get("shuffled_control", {}).get("permutation_unit")
        != "whole_trajectory_block"
    ):
        _fail("Person B frozen minimum differs")

    c_package = (
        c_root / "docs/status/person_c_c6a_completion_v0_1/package_manifest.json"
    )
    if _sha256_file(c_package) != C6A_PACKAGE_SHA256:
        _fail("canonical C6A package hash differs")
    package = _read_object(c_package, "canonical C6A package")
    if (
        package.get("canonical_c6a_id") != C6A_ID
        or package.get("status") != "PASS"
        or package.get("immutable") is not True
        or package.get("completed_episode_count") != 66
    ):
        _fail("canonical C6A package fields differ")
    capture_path = c_root / str(package["capture_manifest"]["path"]).replace(
        "/", os.sep
    )
    if (
        _sha256_file(capture_path) != package["capture_manifest"]["sha256"]
        or capture_path.stat().st_size != package["capture_manifest"]["size_bytes"]
    ):
        _fail("canonical C6A capture manifest differs")
    inventory_path = _component_path(package, c_root, "episode_inventory.json")
    capture_document = _read_object(capture_path, "canonical capture manifest")
    inventory_document = _read_object(inventory_path, "canonical episode inventory")
    capture_by_episode = {
        int(row["episode_id"]): row
        for row in capture_document.get("episodes", [])
        if isinstance(row, Mapping)
    }
    inventory_by_episode = {
        int(row["episode_id"]): row
        for row in inventory_document.get("episodes", [])
        if isinstance(row, Mapping)
    }
    if len(capture_by_episode) != 66 or len(inventory_by_episode) != 66:
        _fail("canonical C6A episode authorities must contain 66 unique episodes")

    e_registry = (
        e_root
        / "docs/status/person_e_c6a_provenance_closure_v0_1/canonical_registry_records.json"
    )
    e_handoff = (
        e_root
        / "docs/status/person_e_c6a_provenance_closure_v0_1/person_e_to_person_a_c6a_provenance_handoff.json"
    )
    if _sha256_file(e_registry) != E_REGISTRY_SHA256:
        _fail("Person E canonical registry hash differs")
    if _sha256_file(e_handoff) != E_C6A_HANDOFF_SHA256:
        _fail("Person E canonical C6A handoff hash differs")
    registry_document = _read_object(e_registry, "Person E canonical registry")
    registry_by_episode = {
        int(row["episode_id"]): row
        for row in registry_document.get("records", [])
        if isinstance(row, Mapping)
    }
    if len(registry_by_episode) != 66:
        _fail("Person E canonical registry must contain 66 unique records")

    episode_rows = sorted(
        inventory_by_episode.values(),
        key=lambda row: (str(row["layout_id"]), int(row["episode_id"])),
    )
    layouts = sorted({str(row["layout_id"]) for row in episode_rows})
    candidates_inspected: list[dict[str, Any]] = []
    selected_bindings: list[Any] = []
    for layout_id in layouts:
        if layout_id == CURRENT_LAYOUT:
            continue
        rows = [row for row in episode_rows if row["layout_id"] == layout_id]
        for inventory_row in rows:
            episode_id = int(inventory_row["episode_id"])
            capture_row = capture_by_episode[episode_id]
            registry_row = registry_by_episode[episode_id]
            reasons = _preliminary_rejections(capture_row, inventory_row, registry_row)
            binding = None
            if not reasons:
                try:
                    binding = single_runner.load_canonical_pilot_binding(
                        _direct_arguments(
                            trajectory_id=f"{layout_id}_ep{episode_id}",
                            episode_id=episode_id,
                            c_package=c_package,
                            e_registry=e_registry,
                            e_handoff=e_handoff,
                        )
                    )
                except single_runner.Phase6RunnerError as error:
                    reasons.append(f"CANONICAL_BINDING_REJECTED:{error.code}")
            candidates_inspected.append(
                {
                    "episode_id": episode_id,
                    "layout_id": layout_id,
                    "rejection_reasons": reasons,
                    "selected": binding is not None,
                    "trajectory_id": f"{layout_id}_ep{episode_id}",
                }
            )
            if binding is not None:
                selected_bindings.append(binding)
                break
        if len(selected_bindings) == REQUIRED_LAYOUT_COUNT - 1:
            break

    observed = tuple((item.layout_id, item.episode_id) for item in selected_bindings)
    if observed != NEW_TRAJECTORIES:
        _fail(
            "deterministic selection differs from the frozen expected successor: "
            f"{observed!r}"
        )

    direct_source_identities: set[tuple[int, str, str]] = set()
    direct_source_paths: set[str] = set()
    selected_records: list[dict[str, Any]] = []
    for binding in selected_bindings:
        positions = [float(row["axis_pos"]) for row in binding.state_rows]
        artifacts: list[dict[str, Any]] = []
        for row in binding.direct_artifacts:
            identity = (
                binding.episode_id,
                str(row["side"]),
                str(row["relative_path"]),
            )
            path = str(Path(str(row["path"])).resolve())
            if identity in direct_source_identities or path in direct_source_paths:
                _fail(f"duplicate direct source identity: {identity}")
            direct_source_identities.add(identity)
            direct_source_paths.add(path)
            artifacts.append(
                {
                    "path": path,
                    "relative_path": str(row["relative_path"]),
                    "sha256": str(row["sha256"]),
                    "side": str(row["side"]),
                    "size_bytes": int(row["size_bytes"]),
                }
            )
        selected_records.append(
            {
                "direct_source_artifacts": artifacts,
                "episode_id": binding.episode_id,
                "expected_activation_chunk_count": EXPECTED_CHUNKS_PER_TRAJECTORY,
                "expected_activation_row_count": binding.expected_activation_rows,
                "frame_count": binding.frame_count,
                "label_position_audit": {
                    "finite_count": len(positions),
                    "maximum_axis_pos_blocks": max(positions),
                    "minimum_axis_pos_blocks": min(positions),
                    "nonzero_range": max(positions) > min(positions),
                    "unique_position_count": len(set(positions)),
                },
                "layout_id": binding.layout_id,
                "person_e_registry_record_id": binding.registry_record_id,
                "person_e_registry_record_sha256": binding.registry_record_sha256,
                "trajectory_id": binding.trajectory_id,
            }
        )

    current_bundle = (
        ROOT
        / "data/handoff_a/person_a_canonical_c6a_sagemaker_input_v0_1/bundle_manifest.json"
    )
    current_output = ROOT / (
        "docs/status/phase6_runtime/"
        "person-a-canonical-c6a-layout-01-ep12602-seed-20260725-retry-"
        "20260804T193204Z-package-retry-20260804T193627Z/output_bundle_manifest.json"
    )
    if _sha256_file(current_output) != CURRENT_OUTPUT_MANIFEST_SHA256:
        _fail("current certified output bundle manifest differs")
    current_input_document = _read_object(current_bundle, "current input bundle")
    if (
        current_input_document.get("trajectory_id") != CURRENT_TRAJECTORY
        or current_input_document.get("episode_id") != CURRENT_EPISODE
    ):
        _fail("current certified trajectory identity differs")

    b_runner = b_root / "scripts/run_person_b_canonical_positive_control.py"
    b_test = b_root / "tests/analysis/test_person_b_canonical_positive_control.py"
    b_config = b_root / "configs/analysis/core.yaml"
    b_fold = b_root / "data/person_b/phase6_c_intake/layout_fold_plan.json"
    return {
        "authorities": {
            **authorities,
            "canonical_c6a": {
                "canonical_c6a_id": C6A_ID,
                "package_manifest_path": str(c_package.resolve()),
                "package_manifest_sha256": C6A_PACKAGE_SHA256,
            },
            "person_b_blocker": {
                "configuration_path": str(b_config.resolve()),
                "configuration_sha256": _sha256_file(b_config),
                "focused_test_path": str(b_test.resolve()),
                "focused_test_sha256": _sha256_file(b_test),
                "fold_plan_path": str(b_fold.resolve()),
                "fold_plan_sha256": _sha256_file(b_fold),
                "implementation_path": str(b_runner.resolve()),
                "implementation_sha256": _sha256_file(b_runner),
                "receipt_path": str(b_receipt.resolve()),
                "receipt_sha256": B_BLOCKER_RECEIPT_SHA256,
            },
            "person_e_current_receipt": {
                "acceptance_scope": "EXISTING_SINGLE_TRAJECTORY_ONLY",
                "path": str(e_current_receipt.resolve()),
                "sha256": E_CURRENT_RECEIPT_SHA256,
                "successor_acceptance_claimed": False,
            },
        },
        "candidates_inspected": candidates_inspected,
        "current_certified_trajectory": {
            "activation_chunk_count": EXPECTED_CHUNKS_PER_TRAJECTORY,
            "activation_index_sha256": CURRENT_ACTIVATION_INDEX_SHA256,
            "activation_row_count": EXPECTED_ROWS_PER_TRAJECTORY,
            "episode_id": CURRENT_EPISODE,
            "layout_id": CURRENT_LAYOUT,
            "output_bundle_manifest_path": str(current_output.resolve()),
            "output_bundle_manifest_sha256": CURRENT_OUTPUT_MANIFEST_SHA256,
            "reused_without_extraction": True,
            "trajectory_id": CURRENT_TRAJECTORY,
        },
        "expected_cardinality": {
            "new_activation_chunk_count": 80,
            "new_activation_row_count": 4_800,
            "new_trajectory_count": 4,
            "total_activation_chunk_count": EXPECTED_TOTAL_CHUNKS,
            "total_activation_row_count": EXPECTED_TOTAL_ROWS,
            "total_layout_count": REQUIRED_LAYOUT_COUNT,
            "total_trajectory_count": REQUIRED_TRAJECTORY_COUNT,
        },
        "frozen_person_b_requirements": {
            "five_layouts_and_five_trajectories_sufficient": True,
            "grouping_key": GROUPING_KEY,
            "inner_fold_count": 4,
            "label_requirements": (
                "x_true_blocks from finite canonical_server_state.axis_pos on "
                "60 fully geometric-visible NO_WALL frames with nonzero position range"
            ),
            "outer_fold_count": 5,
            "required_distinct_layout_count": REQUIRED_LAYOUT_COUNT,
            "required_distinct_trajectory_count": REQUIRED_TRAJECTORY_COUNT,
            "shuffled_control": {
                "minimum_trajectory_count": 2,
                "permutation_count": 999,
                "permutation_p_value": "add_one_greater_or_equal",
                "permutation_seed": 20260720,
                "permutation_unit": "whole_trajectory_block",
            },
        },
        "immutable": True,
        "no_label_leakage_statement": (
            "Episode ordering and selection use only canonical predeclared layout, "
            "NO_WALL/visibility/target eligibility, completeness, identity integrity, "
            "and the frozen finite nonzero-position eligibility gate. Label magnitude, "
            "activation values, probe metrics, and scientific outcomes are never used "
            "to rank candidates."
        ),
        "schema_version": SELECTION_SCHEMA,
        "selected_new_trajectories": selected_records,
        "selected_trajectory_order": [
            f"{layout_id}_ep{episode_id}"
            for layout_id, episode_id in SELECTED_TRAJECTORIES
        ],
        "selection_rule": {
            "fixed_first": CURRENT_TRAJECTORY,
            "layout_order": "ascending_layout_id",
            "within_layout_order": "ascending_numeric_episode_id",
            "stop_rule": "stop_at_exact_frozen_minimum_of_five_layouts_and_trajectories",
        },
        "status": "PASS",
    }


def stage_multilayout_input(
    *,
    selection_record_path: Path,
    output_root: Path,
    b_root: Path,
    c_root: Path,
    e_root: Path,
) -> dict[str, Any]:
    """Stage four relocatable child bundles in one immutable parent package."""

    selection = _read_object(selection_record_path, "selection record")
    if (
        selection.get("schema_version") != SELECTION_SCHEMA
        or selection.get("status") != "PASS"
    ):
        _fail("selection record is not valid")
    if output_root.exists() or output_root.is_symlink():
        raise FileExistsError(f"create-only multilayout input exists: {output_root}")
    output_root.mkdir(parents=True)

    c_package = (
        c_root / "docs/status/person_c_c6a_completion_v0_1/package_manifest.json"
    )
    e_base = e_root / "docs/status/person_e_c6a_provenance_closure_v0_1"
    e_registry = e_base / "canonical_registry_records.json"
    e_handoff = e_base / "person_e_to_person_a_c6a_provenance_handoff.json"
    child_bundles: list[dict[str, Any]] = []
    for layout_id, episode_id in NEW_TRAJECTORIES:
        trajectory_id = f"{layout_id}_ep{episode_id}"
        child_root = output_root / "trajectories" / trajectory_id
        result = single_prep.stage_input(
            SimpleNamespace(
                canonical_c6a_package=c_package,
                canonical_c6a_package_sha256=C6A_PACKAGE_SHA256,
                trajectory_id=trajectory_id,
                episode_id=episode_id,
                episode_artifact_manifest=e_registry,
                episode_artifact_manifest_sha256=E_REGISTRY_SHA256,
                person_e_provenance_handoff=e_handoff,
                person_e_provenance_handoff_sha256=E_C6A_HANDOFF_SHA256,
                output_root=child_root,
            )
        )
        manifest_path = Path(result["bundle_manifest"])
        child_bundles.append(
            {
                "bundle_manifest": manifest_path.relative_to(output_root).as_posix(),
                "bundle_manifest_sha256": result["bundle_manifest_sha256"],
                "direct_artifact_count": result["direct_artifact_count"],
                "episode_id": episode_id,
                "expected_activation_chunk_count": EXPECTED_CHUNKS_PER_TRAJECTORY,
                "expected_activation_row_count": EXPECTED_ROWS_PER_TRAJECTORY,
                "layout_id": layout_id,
                "trajectory_id": trajectory_id,
            }
        )

    authority_sources = {
        "selection_record": selection_record_path,
        "person_b_blocker_receipt": b_root
        / "docs/status/person_b_canonical_positive_control_layout_01_ep12602_v0_1/b_to_a_receipt.json",
        "person_b_core_config": b_root / "configs/analysis/core.yaml",
        "person_b_fold_plan": b_root
        / "data/person_b/phase6_c_intake/layout_fold_plan.json",
        "person_e_current_single_trajectory_receipt": e_root
        / "docs/status/person_e_a_activation_provenance_acceptance_v0_1/person_e_to_person_a_activation_provenance_receipt.json",
    }
    authority: dict[str, Any] = {}
    for name, source in authority_sources.items():
        destination = output_root / "authority" / name / source.name
        _copy_exclusive(source, destination)
        authority[name] = _descriptor(output_root, destination, "selection_authority")

    inventory_rows = [
        _descriptor(output_root, path, "staged_input")
        for path in sorted(item for item in output_root.rglob("*") if item.is_file())
    ]
    inventory_path = output_root / "sha256_inventory.json"
    _write_exclusive(
        inventory_path,
        {
            "files": inventory_rows,
            "schema_version": (
                "person-a-canonical-c6a-multilayout-input-sha256-inventory-v0.1"
            ),
        },
    )
    manifest = {
        "authority": authority,
        "canonical_c6a_id": C6A_ID,
        "current_certified_trajectory": {
            "output_bundle_manifest_sha256": CURRENT_OUTPUT_MANIFEST_SHA256,
            "reuse_required": True,
            "trajectory_id": CURRENT_TRAJECTORY,
        },
        "expected_new_activation_chunk_count": 80,
        "expected_new_activation_row_count": 4_800,
        "expected_total_activation_chunk_count": EXPECTED_TOTAL_CHUNKS,
        "expected_total_activation_row_count": EXPECTED_TOTAL_ROWS,
        "immutable": True,
        "new_trajectory_bundles": child_bundles,
        "schema_version": INPUT_SCHEMA,
        "scientific_identities": selection["frozen_person_b_requirements"],
        "selection_record_sha256": _sha256_file(selection_record_path),
        "sha256_inventory": {
            "path": inventory_path.relative_to(output_root).as_posix(),
            "sha256": _sha256_file(inventory_path),
        },
        "status": "IMMUTABLE_READY_FOR_SAGEMAKER",
    }
    manifest_path = output_root / "bundle_manifest.json"
    _write_exclusive(manifest_path, manifest)
    return {
        "bundle_manifest": str(manifest_path.resolve()),
        "bundle_manifest_sha256": _sha256_file(manifest_path),
        "file_count": len(inventory_rows),
        "new_trajectory_count": len(child_bundles),
        "status": "PASS",
    }


def verify_multilayout_input(
    manifest_path: Path, expected_sha256: str
) -> dict[str, Any]:
    manifest_path = manifest_path.resolve()
    if _sha256_file(manifest_path) != expected_sha256:
        _fail("multilayout bundle manifest hash differs")
    root = manifest_path.parent
    document = _read_object(manifest_path, "multilayout input manifest")
    if (
        document.get("schema_version") != INPUT_SCHEMA
        or document.get("status") != "IMMUTABLE_READY_FOR_SAGEMAKER"
        or document.get("immutable") is not True
        or document.get("canonical_c6a_id") != C6A_ID
        or document.get("expected_new_activation_row_count") != 4_800
        or document.get("expected_total_activation_row_count") != EXPECTED_TOTAL_ROWS
    ):
        _fail("multilayout input manifest fields differ")
    inventory_descriptor = document.get("sha256_inventory")
    if not isinstance(inventory_descriptor, Mapping):
        _fail("multilayout input inventory descriptor is missing")
    inventory_path = root / str(inventory_descriptor.get("path", ""))
    if _sha256_file(inventory_path) != inventory_descriptor.get("sha256"):
        _fail("multilayout input inventory hash differs")
    inventory = _read_object(inventory_path, "multilayout input inventory")
    rows = inventory.get("files")
    if not isinstance(rows, list) or not rows:
        _fail("multilayout input inventory is empty")
    observed: set[str] = set()
    for row in rows:
        if not isinstance(row, Mapping):
            _fail("multilayout input inventory row is invalid")
        relative = str(row.get("path", ""))
        path = (root / relative.replace("/", os.sep)).resolve()
        try:
            path.relative_to(root)
        except ValueError as error:
            raise MultilayoutPreparationError("staged path escapes bundle") from error
        if (
            not relative
            or relative in observed
            or not path.is_file()
            or path.is_symlink()
            or path.stat().st_size != row.get("size_bytes")
            or _sha256_file(path) != row.get("sha256")
        ):
            _fail(f"staged input file differs: {relative}")
        observed.add(relative)
    actual = {
        path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()
    }
    if actual != observed | {"bundle_manifest.json", "sha256_inventory.json"}:
        _fail("multilayout input contains missing or extra files")

    verified: list[dict[str, Any]] = []
    expected_pairs = list(NEW_TRAJECTORIES)
    child_rows = document.get("new_trajectory_bundles")
    if not isinstance(child_rows, list) or len(child_rows) != len(expected_pairs):
        _fail("multilayout child bundle count differs")
    for child, (layout_id, episode_id) in zip(child_rows, expected_pairs, strict=True):
        trajectory_id = f"{layout_id}_ep{episode_id}"
        if (
            child.get("trajectory_id") != trajectory_id
            or child.get("episode_id") != episode_id
            or child.get("layout_id") != layout_id
        ):
            _fail("multilayout child order or identity differs")
        child_manifest = root / str(child["bundle_manifest"]).replace("/", os.sep)
        binding = single_runner.load_staged_canonical_pilot_binding(
            single_runner.RunnerArguments(
                repository_root=ROOT,
                mineworld_root=ROOT,
                asset_root=ROOT,
                main_checkpoint=SINGLE_RUNNER_PATH,
                vae_config=SINGLE_RUNNER_PATH,
                vae_checkpoint=SINGLE_RUNNER_PATH,
                approved_input_root=ROOT,
                approved_output_root=ROOT.parent,
                activation_store_v2_ratification_object="",
                session_id="multilayout-verification-only",
                seed=single_runner.DETERMINISTIC_SEED,
                device=single_runner.REQUIRED_DEVICE,
                precision="float16",
                runtime_host=single_runner.HISTORICAL_RUNTIME_HOST,
                canonical_c6a_package_sha256=C6A_PACKAGE_SHA256,
                trajectory_id=trajectory_id,
                episode_id=episode_id,
                episode_artifact_manifest_sha256=E_REGISTRY_SHA256,
                person_e_provenance_handoff_sha256=E_C6A_HANDOFF_SHA256,
                canonical_input_bundle_manifest=child_manifest,
                canonical_input_bundle_manifest_sha256=str(
                    child["bundle_manifest_sha256"]
                ),
            )
        )
        verified.append(
            {
                "direct_artifact_count": len(binding.direct_artifacts),
                "episode_id": binding.episode_id,
                "expected_activation_rows": binding.expected_activation_rows,
                "frame_count": binding.frame_count,
                "layout_id": binding.layout_id,
                "trajectory_id": binding.trajectory_id,
            }
        )
    return {
        "bundle_manifest_sha256": expected_sha256,
        "file_count": len(rows),
        "status": "PASS",
        "trajectories": verified,
    }


def _validate_output_bundle(root: Path, expected_trajectory: str) -> dict[str, Any]:
    root = root.resolve()
    single_prep.verify_output(SimpleNamespace(bundle_root=root))
    manifest_path = root / "output_bundle_manifest.json"
    manifest = _read_object(manifest_path, "per-run output manifest")
    if manifest.get("trajectory_id") != expected_trajectory:
        _fail(f"per-run output trajectory differs: {root}")
    index_path = (root / str(manifest.get("activation_index", ""))).resolve()
    try:
        index_path.relative_to(root)
    except ValueError as error:
        raise MultilayoutPreparationError(
            "activation index escapes output bundle"
        ) from error
    index = _read_object(index_path, "per-run activation index")
    rows = index.get("index_rows")
    chunks = index.get("chunks")
    if (
        index.get("format_version") != single_runner.ACTIVATION_INDEX_V2_FORMAT_VERSION
        or index.get("run_status") != "completed"
        or not isinstance(rows, list)
        or len(rows) != EXPECTED_ROWS_PER_TRAJECTORY
        or not isinstance(chunks, list)
        or len(chunks) != EXPECTED_CHUNKS_PER_TRAJECTORY
    ):
        _fail(f"per-run activation index cardinality differs: {root}")
    layer_counts = Counter()
    frame_layers: dict[int, set[int]] = defaultdict(set)
    scientific_keys: set[tuple[Any, ...]] = set()
    physical_keys: set[tuple[Any, ...]] = set()
    source_frames: set[tuple[str, str]] = set()
    for row in rows:
        if (
            not isinstance(row, Mapping)
            or row.get("trajectory_id") != expected_trajectory
        ):
            _fail(f"per-run activation row trajectory differs: {root}")
        layer = int(row["layer_idx"])
        frame = int(row["global_model_frame_idx"])
        layer_counts[layer] += 1
        frame_layers[frame].add(layer)
        source_frames.add((expected_trajectory, str(row["source_frame_id"])))
        scientific_keys.add(
            (
                expected_trajectory,
                frame,
                layer,
                row["hook_site"],
                row["run_id"],
            )
        )
        physical_keys.add(
            (
                row["activation_chunk_id"],
                row["chunk_row_idx"],
                row["run_id"],
            )
        )
    if (
        set(frame_layers) != set(range(60))
        or any(
            layers != set(single_runner.FROZEN_PHASE6_LAYERS)
            for layers in frame_layers.values()
        )
        or set(layer_counts.values()) != {60}
        or len(scientific_keys) != EXPECTED_ROWS_PER_TRAJECTORY
        or len(physical_keys) != EXPECTED_ROWS_PER_TRAJECTORY
        or len(source_frames) != 60
    ):
        _fail(
            f"per-run activation identities are missing, duplicate, or reordered: {root}"
        )

    b_path = root / "person_a_to_person_b_canonical_pilot_handoff.json"
    e_path = root / "person_a_to_person_e_canonical_provenance_handoff.json"
    certification_path = root / "step6_5.json"
    b_handoff = _read_object(b_path, "per-run A-to-B handoff")
    e_handoff = _read_object(e_path, "per-run A-to-E handoff")
    certification = _read_object(certification_path, "per-run certification")
    result = certification.get("result")
    layout_id = expected_trajectory.split("_ep", 1)[0]
    if (
        b_handoff.get("status") != "READY_FOR_PERSON_B_CONSUMPTION"
        or b_handoff.get("trajectory_id") != expected_trajectory
        or b_handoff.get("grouping") != {"key": GROUPING_KEY, "value": layout_id}
        or b_handoff.get("expected_activation_row_count")
        != EXPECTED_ROWS_PER_TRAJECTORY
        or b_handoff.get("direct_pooling_validation") != "PASS"
        or b_handoff.get("exact_source_identity_joins", {}).get("status") != "PASS"
        or e_handoff.get("status") != "READY_FOR_PERSON_E_PROVENANCE_CONSUMPTION"
        or e_handoff.get("trajectory_id") != expected_trajectory
        or not isinstance(result, Mapping)
        or result.get("status") != "PASS"
        or result.get("direct_pooling_audit") != "PASS"
        or result.get("source_identity_join_failure_count") != 0
        or "repeatability_maximum_absolute_difference" not in result
    ):
        _fail(f"per-run pooling, repeatability, join, or handoff differs: {root}")

    activation_artifacts: list[dict[str, Any]] = []
    for descriptor in chunks:
        path = root / "activation_store/chunks" / Path(str(descriptor["path"])).name
        if (
            not path.is_file()
            or path.stat().st_size != descriptor.get("byte_size")
            or _sha256_file(path) != descriptor.get("sha256")
        ):
            _fail(f"retrieved activation chunk differs: {path}")
        activation_artifacts.append(
            {
                "byte_size": path.stat().st_size,
                "path": str(path.resolve()),
                "sha256": _sha256_file(path),
                "type": "activation_chunk",
            }
        )
    activation_artifacts.append(
        {
            "byte_size": index_path.stat().st_size,
            "path": str(index_path),
            "sha256": _sha256_file(index_path),
            "type": "activation_index",
        }
    )
    return {
        "accepted_manifest": {
            "path": str((root / "accepted_pilot_manifest.json").resolve()),
            "sha256": _sha256_file(root / "accepted_pilot_manifest.json"),
        },
        "activation_artifacts": activation_artifacts,
        "activation_chunk_count": EXPECTED_CHUNKS_PER_TRAJECTORY,
        "activation_index": activation_artifacts[-1],
        "activation_row_count": EXPECTED_ROWS_PER_TRAJECTORY,
        "a_to_b_handoff": {
            "path": str(b_path.resolve()),
            "sha256": _sha256_file(b_path),
        },
        "a_to_e_handoff": {
            "path": str(e_path.resolve()),
            "sha256": _sha256_file(e_path),
        },
        "certification": {
            "direct_pooling_audit": "PASS",
            "path": str(certification_path.resolve()),
            "repeatability_maximum_absolute_difference": result[
                "repeatability_maximum_absolute_difference"
            ],
            "sha256": _sha256_file(certification_path),
            "source_identity_join_failure_count": 0,
            "status": "PASS",
        },
        "episode_id": int(manifest["episode_id"]),
        "layout_id": layout_id,
        "output_bundle_manifest": {
            "path": str(manifest_path.resolve()),
            "sha256": _sha256_file(manifest_path),
        },
        "output_bundle_root": str(root),
        "source_frame_count": 60,
        "trajectory_id": expected_trajectory,
    }


def collect_successor(
    *,
    existing_output: Path,
    new_outputs: Sequence[Path],
    selection_record_path: Path,
    input_bundle_manifest: Path,
    destination: Path,
) -> dict[str, Any]:
    """Create a fail-closed multi-index package; never synthesize one index."""

    if destination.exists() or destination.is_symlink():
        raise FileExistsError(f"create-only successor package exists: {destination}")
    selection = _read_object(selection_record_path, "selection record")
    if (
        _sha256_file(existing_output / "output_bundle_manifest.json")
        != CURRENT_OUTPUT_MANIFEST_SHA256
    ):
        _fail("existing certified output was not preserved exactly")
    existing_manifest = _read_object(
        existing_output / "output_bundle_manifest.json",
        "existing certified output manifest",
    )
    preserved_hashes = {
        existing_output
        / "accepted_pilot_manifest.json": CURRENT_ACCEPTED_MANIFEST_SHA256,
        existing_output / str(existing_manifest["activation_index"]): (
            CURRENT_ACTIVATION_INDEX_SHA256
        ),
        existing_output / "person_a_to_person_b_canonical_pilot_handoff.json": (
            CURRENT_A_TO_B_SHA256
        ),
        existing_output / "person_a_to_person_e_canonical_provenance_handoff.json": (
            CURRENT_A_TO_E_SHA256
        ),
    }
    if any(
        _sha256_file(path) != expected for path, expected in preserved_hashes.items()
    ):
        _fail("existing accepted manifest, index, or handoff was not preserved exactly")
    roots_by_trajectory: dict[str, Path] = {CURRENT_TRAJECTORY: existing_output}
    for root in new_outputs:
        manifest = _read_object(
            root / "output_bundle_manifest.json", "new output manifest"
        )
        trajectory_id = str(manifest.get("trajectory_id", ""))
        if trajectory_id in roots_by_trajectory:
            _fail(f"duplicate output trajectory: {trajectory_id}")
        roots_by_trajectory[trajectory_id] = root
    expected_order = [
        f"{layout_id}_ep{episode_id}" for layout_id, episode_id in SELECTED_TRAJECTORIES
    ]
    if set(roots_by_trajectory) != set(expected_order):
        _fail("successor output trajectory set differs")
    run_records = [
        _validate_output_bundle(roots_by_trajectory[trajectory_id], trajectory_id)
        for trajectory_id in expected_order
    ]
    if (
        len({row["layout_id"] for row in run_records}) != REQUIRED_LAYOUT_COUNT
        or len({row["trajectory_id"] for row in run_records})
        != REQUIRED_TRAJECTORY_COUNT
        or sum(row["activation_row_count"] for row in run_records)
        != EXPECTED_TOTAL_ROWS
        or sum(row["activation_chunk_count"] for row in run_records)
        != EXPECTED_TOTAL_CHUNKS
    ):
        _fail("successor aggregate cardinality differs")
    all_artifacts = [
        artifact for run in run_records for artifact in run["activation_artifacts"]
    ]
    artifact_paths = [row["path"] for row in all_artifacts]
    if len(artifact_paths) != len(set(artifact_paths)):
        _fail("successor contains a duplicate physical activation artifact")

    destination.mkdir(parents=True)
    external_inventory_path = destination / "external_activation_inventory.json"
    _write_exclusive(
        external_inventory_path,
        {
            "artifact_count": len(all_artifacts),
            "artifacts": all_artifacts,
            "physical_combined_activation_index_created": False,
            "schema_version": "person-a-canonical-c6a-multirun-external-inventory-v0.1",
            "status": "PASS",
        },
    )
    logical_order = []
    offset = 0
    for run in run_records:
        logical_order.append(
            {
                "activation_index_sha256": run["activation_index"]["sha256"],
                "logical_row_start_inclusive": offset,
                "logical_row_stop_exclusive": offset + EXPECTED_ROWS_PER_TRAJECTORY,
                "trajectory_id": run["trajectory_id"],
            }
        )
        offset += EXPECTED_ROWS_PER_TRAJECTORY

    supersession = {
        "preserved_predecessors": [
            {"kind": "a_to_b", "sha256": CURRENT_A_TO_B_SHA256},
            {"kind": "a_to_e", "sha256": CURRENT_A_TO_E_SHA256},
        ],
        "scope": "five-layout canonical positive-control successor",
        "supersedes_without_modification": True,
    }
    b_handoff = {
        "activation_chunk_count": EXPECTED_TOTAL_CHUNKS,
        "activation_row_count": EXPECTED_TOTAL_ROWS,
        "canonical_c6a_id": C6A_ID,
        "certification": {
            "all_direct_pooling_audits": "PASS",
            "all_repeatability_checks": "PASS",
            "all_source_identity_joins": "PASS",
            "missing_extra_duplicate_stale_or_reordered_rows": 0,
        },
        "episode_ids": [episode for _layout, episode in SELECTED_TRAJECTORIES],
        "grouping": {
            "key": GROUPING_KEY,
            "values": [layout for layout, _episode in SELECTED_TRAJECTORIES],
        },
        "immutable": True,
        "label_authority": {
            "source": LABEL_SOURCE,
            "target_name": TARGET_NAME,
            "unit": "blocks",
        },
        "multi_index_collection": {
            "index_count": REQUIRED_TRAJECTORY_COUNT,
            "logical_order": logical_order,
            "physical_combined_index_created": False,
        },
        "person_b_frozen_execution": selection["frozen_person_b_requirements"],
        "per_run_handoffs": [run["a_to_b_handoff"] for run in run_records],
        "schema_version": B_HANDOFF_SCHEMA,
        "scientific_use_acceptance_claimed": False,
        "status": "READY_FOR_PERSON_B_FROZEN_POSITIVE_CONTROL",
        "supersession": supersession,
        "trajectory_ids": expected_order,
    }
    b_path = destination / "person_a_to_person_b_canonical_multilayout_handoff.json"
    _write_exclusive(b_path, b_handoff)
    e_handoff = {
        "activation_chunk_count": EXPECTED_TOTAL_CHUNKS,
        "activation_row_count": EXPECTED_TOTAL_ROWS,
        "canonical_c6a_id": C6A_ID,
        "certification": b_handoff["certification"],
        "episode_ids": [episode for _layout, episode in SELECTED_TRAJECTORIES],
        "immutable": True,
        "multi_index_collection": b_handoff["multi_index_collection"],
        "per_run_handoffs": [run["a_to_e_handoff"] for run in run_records],
        "person_e_successor_acceptance_claimed": False,
        "requires_new_person_e_receipt": True,
        "schema_version": E_HANDOFF_SCHEMA,
        "status": "READY_FOR_NEW_PERSON_E_PROVENANCE_REVIEW",
        "supersession": supersession,
        "trajectory_ids": expected_order,
    }
    e_path = destination / "person_a_to_person_e_canonical_multilayout_handoff.json"
    _write_exclusive(e_path, e_handoff)
    collection = {
        "activation_chunk_count": EXPECTED_TOTAL_CHUNKS,
        "activation_index_count": REQUIRED_TRAJECTORY_COUNT,
        "activation_row_count": EXPECTED_TOTAL_ROWS,
        "canonical_c6a_id": C6A_ID,
        "collection_contract": {
            "index_semantics": "five_independent_immutable_person_a_activation_index_v2_documents",
            "logical_order_is_not_a_physical_index": True,
            "physical_combined_index_created": False,
        },
        "external_activation_inventory": {
            "path": external_inventory_path.name,
            "sha256": _sha256_file(external_inventory_path),
        },
        "immutable": True,
        "input_bundle_manifest": {
            "path": str(input_bundle_manifest.resolve()),
            "sha256": _sha256_file(input_bundle_manifest),
        },
        "layout_count": REQUIRED_LAYOUT_COUNT,
        "logical_order": logical_order,
        "no_missing_extra_duplicate_stale_or_reordered_rows": True,
        "person_a_to_person_b_handoff": {
            "path": b_path.name,
            "sha256": _sha256_file(b_path),
        },
        "person_a_to_person_e_handoff": {
            "path": e_path.name,
            "sha256": _sha256_file(e_path),
        },
        "runs": run_records,
        "schema_version": COLLECTION_SCHEMA,
        "selection_record": {
            "path": str(selection_record_path.resolve()),
            "sha256": _sha256_file(selection_record_path),
        },
        "status": "READY_FOR_PERSON_B_AND_PERSON_E_REVIEW",
        "trajectory_count": REQUIRED_TRAJECTORY_COUNT,
    }
    collection_path = destination / "collection_manifest.json"
    _write_exclusive(collection_path, collection)
    inventory_rows = [
        _descriptor(destination, path, "successor_collection_document")
        for path in sorted(item for item in destination.rglob("*") if item.is_file())
    ]
    inventory_path = destination / "sha256_inventory.json"
    _write_exclusive(
        inventory_path,
        {
            "files": inventory_rows,
            "schema_version": "person-a-canonical-c6a-multirun-package-inventory-v0.1",
        },
    )
    return {
        "activation_chunk_count": EXPECTED_TOTAL_CHUNKS,
        "activation_index_count": REQUIRED_TRAJECTORY_COUNT,
        "activation_row_count": EXPECTED_TOTAL_ROWS,
        "collection_manifest": str(collection_path.resolve()),
        "collection_manifest_sha256": _sha256_file(collection_path),
        "person_a_to_person_b_handoff_sha256": _sha256_file(b_path),
        "person_a_to_person_e_handoff_sha256": _sha256_file(e_path),
        "sha256_inventory": str(inventory_path.resolve()),
        "status": "PASS",
    }


def _find_verified_output(runtime_root: Path, trajectory_id: str) -> Path | None:
    matches: list[Path] = []
    for manifest_path in sorted(runtime_root.glob("*/output_bundle_manifest.json")):
        try:
            manifest = _read_object(manifest_path, "candidate output manifest")
            if manifest.get("trajectory_id") == trajectory_id:
                _validate_output_bundle(manifest_path.parent, trajectory_id)
                matches.append(manifest_path.parent)
        except (OSError, ValueError, MultilayoutPreparationError):
            continue
    return matches[0] if matches else None


def _additive_session_id(
    approved_input: Path, approved_output: Path, trajectory_id: str
) -> str:
    stem = (
        "person-a-canonical-c6a-"
        + trajectory_id.replace("_", "-")
        + "-seed-20260725-multilayout-v0-1"
    )
    paths = (
        approved_input / stem,
        approved_output / stem,
        approved_output / f"{stem}-activation-store-v2",
    )
    if not any(path.exists() or path.is_symlink() for path in paths):
        return stem
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    return f"{stem}-retry-{stamp}"


def _find_successful_external_session(
    approved_input: Path,
    approved_output: Path,
    trajectory_id: str,
) -> str | None:
    """Reuse a completed external session after an interrupted four-run task."""

    prefix = (
        "person-a-canonical-c6a-"
        + trajectory_id.replace("_", "-")
        + "-seed-20260725-multilayout-v0-1"
    )
    for session_root in sorted(approved_output.glob(prefix + "*")):
        session_id = session_root.name
        if session_id.endswith("-activation-store-v2") or not session_root.is_dir():
            continue
        input_root = approved_input / session_id
        store_root = approved_output / f"{session_id}-activation-store-v2"
        try:
            final_report = _read_object(
                session_root / "final_report.json", "external final report"
            )
            step6_5 = _read_object(
                session_root / "step6_5.json", "external certification"
            )
            step6_4 = _read_object(session_root / "step6_4.json", "external extraction")
            index_path = Path(
                str(step6_4.get("result", {}).get("activation_index_path", ""))
            )
            if (
                final_report.get("status") == "PASS"
                and final_report.get("selected_pilot") == trajectory_id
                and step6_5.get("result", {}).get("status") == "PASS"
                and step6_5.get("result", {}).get("direct_pooling_audit") == "PASS"
                and step6_5.get("result", {}).get("source_identity_join_failure_count")
                == 0
                and input_root.is_dir()
                and (input_root / "accepted_pilot_manifest.json").is_file()
                and store_root.is_dir()
                and index_path.is_file()
            ):
                return session_id
        except (OSError, MultilayoutPreparationError):
            continue
    return None


def run_missing(namespace: argparse.Namespace) -> dict[str, Any]:
    """SageMaker-only orchestration for the four missing immutable runs."""

    repository = namespace.repository_root.resolve()
    if _git(repository, "branch", "--show-current") != PERSON_A_BRANCH:
        _fail(f"SageMaker execution requires {PERSON_A_BRANCH}")
    if _git(repository, "rev-parse", "HEAD") != namespace.preparation_commit:
        _fail("SageMaker repository HEAD differs from the preparation commit")
    if _git(repository, "status", "--porcelain=v1", "-uall"):
        _fail("SageMaker execution requires a clean worktree")
    verification = verify_multilayout_input(
        namespace.bundle_manifest,
        namespace.bundle_manifest_sha256,
    )
    manifest = _read_object(namespace.bundle_manifest, "multilayout input manifest")
    bundle_root = namespace.bundle_manifest.resolve().parent
    runtime_root = namespace.runtime_output_root.resolve()
    runtime_root.mkdir(parents=True, exist_ok=True)
    successful: list[Path] = []
    pending_retrievals: list[tuple[str, str]] = []
    executed: list[str] = []
    reused: list[str] = [CURRENT_TRAJECTORY]
    for child in manifest["new_trajectory_bundles"]:
        trajectory_id = str(child["trajectory_id"])
        episode_id = int(child["episode_id"])
        existing = _find_verified_output(runtime_root, trajectory_id)
        if existing is not None:
            successful.append(existing)
            reused.append(trajectory_id)
            continue
        session_id = _find_successful_external_session(
            namespace.approved_input_root.resolve(),
            namespace.approved_output_root.resolve(),
            trajectory_id,
        )
        if session_id is not None:
            pending_retrievals.append((trajectory_id, session_id))
            reused.append(trajectory_id)
            continue
        session_id = _additive_session_id(
            namespace.approved_input_root.resolve(),
            namespace.approved_output_root.resolve(),
            trajectory_id,
        )
        child_manifest = bundle_root / str(child["bundle_manifest"]).replace(
            "/", os.sep
        )
        arguments = single_runner.RunnerArguments(
            repository_root=repository,
            mineworld_root=namespace.mineworld_root.resolve(),
            asset_root=namespace.asset_root.resolve(),
            main_checkpoint=namespace.main_checkpoint.resolve(),
            vae_config=namespace.vae_config.resolve(),
            vae_checkpoint=namespace.vae_checkpoint.resolve(),
            approved_input_root=namespace.approved_input_root.resolve(),
            approved_output_root=namespace.approved_output_root.resolve(),
            activation_store_v2_ratification_object="",
            session_id=session_id,
            seed=single_runner.DETERMINISTIC_SEED,
            device=single_runner.REQUIRED_DEVICE,
            precision="float16",
            runtime_host=single_runner.HISTORICAL_RUNTIME_HOST,
            canonical_c6a_package_sha256=C6A_PACKAGE_SHA256,
            trajectory_id=trajectory_id,
            episode_id=episode_id,
            episode_artifact_manifest_sha256=E_REGISTRY_SHA256,
            person_e_provenance_handoff_sha256=E_C6A_HANDOFF_SHA256,
            canonical_input_bundle_manifest=child_manifest,
            canonical_input_bundle_manifest_sha256=str(child["bundle_manifest_sha256"]),
            ffmpeg=namespace.ffmpeg.resolve(),
            ffprobe=namespace.ffprobe.resolve(),
        )
        status = single_runner.run(arguments)
        if status != 0:
            _fail(
                f"GPU extraction failed for {trajectory_id}; immutable evidence is "
                f"preserved under session {session_id}"
            )
        pending_retrievals.append((trajectory_id, session_id))
        executed.append(trajectory_id)

    # Delay all Git-worktree retrieval until every GPU extraction has passed.
    # An interrupted extraction task therefore leaves the repository clean and
    # can reuse completed external sessions on the next additive invocation.
    for trajectory_id, session_id in pending_retrievals:
        retrieved = runtime_root / session_id
        single_prep.collect_output(
            SimpleNamespace(
                input_session_root=namespace.approved_input_root.resolve() / session_id,
                output_session_root=namespace.approved_output_root.resolve()
                / session_id,
                activation_store_root=namespace.approved_output_root.resolve()
                / f"{session_id}-activation-store-v2",
                destination=retrieved,
            )
        )
        _validate_output_bundle(retrieved, trajectory_id)
        successful.append(retrieved)
    if len(successful) != 4:
        _fail("four successful missing trajectory outputs are required")
    successor_stem = "person-a-canonical-c6a-multilayout-successor-seed-20260725"
    destination = runtime_root / successor_stem
    if destination.exists() or destination.is_symlink():
        destination = runtime_root / (
            successor_stem + "-retry-" + time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        )
    collection = collect_successor(
        existing_output=namespace.existing_output.resolve(),
        new_outputs=successful,
        selection_record_path=namespace.selection_record.resolve(),
        input_bundle_manifest=namespace.bundle_manifest.resolve(),
        destination=destination,
    )
    return {
        "collection": collection,
        "executed_trajectories": executed,
        "input_verification": verification,
        "reused_trajectories": reused,
        "status": "PASS",
        "successor_root": str(destination),
    }


def _add_common_authorities(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--a-root", type=Path, default=ROOT)
    parser.add_argument("--b-root", type=Path, required=True)
    parser.add_argument("--c-root", type=Path, required=True)
    parser.add_argument("--e-root", type=Path, required=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="operation", required=True)
    select = commands.add_parser("select")
    _add_common_authorities(select)
    select.add_argument("--output", type=Path, required=True)
    stage = commands.add_parser("stage-input")
    _add_common_authorities(stage)
    stage.add_argument("--selection-record", type=Path, required=True)
    stage.add_argument("--output-root", type=Path, required=True)
    verify = commands.add_parser("verify-input")
    verify.add_argument("--bundle-manifest", type=Path, required=True)
    verify.add_argument("--bundle-manifest-sha256", required=True)
    collect = commands.add_parser("collect-successor")
    collect.add_argument("--existing-output", type=Path, required=True)
    collect.add_argument("--new-output", type=Path, action="append", required=True)
    collect.add_argument("--selection-record", type=Path, required=True)
    collect.add_argument("--input-bundle-manifest", type=Path, required=True)
    collect.add_argument("--destination", type=Path, required=True)
    run = commands.add_parser("run-missing")
    run.add_argument("--repository-root", type=Path, default=ROOT)
    run.add_argument("--preparation-commit", required=True)
    run.add_argument("--bundle-manifest", type=Path, required=True)
    run.add_argument("--bundle-manifest-sha256", required=True)
    run.add_argument("--selection-record", type=Path, required=True)
    run.add_argument("--existing-output", type=Path, required=True)
    run.add_argument("--runtime-output-root", type=Path, required=True)
    run.add_argument("--mineworld-root", type=Path, required=True)
    run.add_argument("--asset-root", type=Path, required=True)
    run.add_argument("--main-checkpoint", type=Path, required=True)
    run.add_argument("--vae-config", type=Path, required=True)
    run.add_argument("--vae-checkpoint", type=Path, required=True)
    run.add_argument("--approved-input-root", type=Path, required=True)
    run.add_argument("--approved-output-root", type=Path, required=True)
    run.add_argument("--ffmpeg", type=Path, required=True)
    run.add_argument("--ffprobe", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    namespace = _parser().parse_args(argv)
    if namespace.operation == "select":
        document = build_selection_record(
            a_root=namespace.a_root.resolve(),
            b_root=namespace.b_root.resolve(),
            c_root=namespace.c_root.resolve(),
            e_root=namespace.e_root.resolve(),
        )
        _write_exclusive(namespace.output.resolve(), document)
        result = {
            "selection_record": str(namespace.output.resolve()),
            "selection_record_sha256": _sha256_file(namespace.output.resolve()),
            "status": "PASS",
        }
    elif namespace.operation == "stage-input":
        result = stage_multilayout_input(
            selection_record_path=namespace.selection_record.resolve(),
            output_root=namespace.output_root.resolve(),
            b_root=namespace.b_root.resolve(),
            c_root=namespace.c_root.resolve(),
            e_root=namespace.e_root.resolve(),
        )
    elif namespace.operation == "verify-input":
        result = verify_multilayout_input(
            namespace.bundle_manifest,
            namespace.bundle_manifest_sha256,
        )
    elif namespace.operation == "collect-successor":
        result = collect_successor(
            existing_output=namespace.existing_output.resolve(),
            new_outputs=[path.resolve() for path in namespace.new_output],
            selection_record_path=namespace.selection_record.resolve(),
            input_bundle_manifest=namespace.input_bundle_manifest.resolve(),
            destination=namespace.destination.resolve(),
        )
    else:
        result = run_missing(namespace)
    print(json.dumps(result, allow_nan=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
