#!/usr/bin/env python3
"""Verify the canonical A bundle and fail closed at the frozen Step 6.6 gate.

The canonical handoff contains one visible no-wall trajectory.  Person B's
frozen positive control requires five outer folds grouped by ``layout_id`` and
its shuffled comparison requires at least two whole trajectories.  This
entrypoint authenticates all available evidence, proves the exact source-row
join, and emits an immutable B-to-A receipt without weakening either rule.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import subprocess
import sys
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mineocclude.contracts.activation_v2 import (  # noqa: E402
    ExternalChunkBinding,
    PERSON_A_ACTIVATION_INDEX_V2_CANONICALIZATION_CONTRACT,
    PERSON_A_ACTIVATION_SOURCE_ROW_V2_ARTIFACT_TYPE,
    PERSON_A_ACTIVATION_SOURCE_ROW_V2_CANONICALIZATION_CONTRACT,
    canonical_json_bytes_for_artifact,
    load_activation_index_v2,
)


REQUIRED_BRANCH = "role/person-b-analysis"
REQUIRED_STARTING_ANCESTOR = "8c5374d00983e6fec22f560a9fd5849e92060f3e"
PERSON_A_COMMIT = "89c1949976f8b8db6efaace66fd2ada4d1b93b3d"
TRAJECTORY_ID = "layout_01_ep12602"
LAYOUT_ID = "layout_01"
EPISODE_ID = 12602
EXPECTED_ACTIVATION_ROWS = 1_200
EXPECTED_CHUNK_COUNT = 20
EXPECTED_OUTPUT_BUNDLE_SHA256 = (
    "e03251f2a8e7f7546b354db411f801c0908739d5929e0a9475ee04ddc903b72b"
)
EXPECTED_HANDOFF_SHA256 = (
    "da875c21a2875338eb432ba85f0c185ee02f4676178b3a3487fe95b55f4c50da"
)
EXPECTED_INDEX_SHA256 = (
    "a6ba07a50ff20e9b90f0b036a0acd18783bad4fa3aacbebc0dd70df825f00a27"
)
EXPECTED_ACCEPTED_MANIFEST_SHA256 = (
    "e6716f4fbe015ebb098da2a6fb800c636cc9eac1a56dcbe1d7543ab377c7a40d"
)
EXPECTED_CAPTURE_PACKAGE_SHA256 = (
    "e7ef5026dd170754fc7b2dd22bbb4893e5d47571111bdd3db8d021ffe62c6fa8"
)
PERSON_A_SAGEMAKER_SOURCE_ROOT = PurePosixPath(
    "/home/sagemaker-user/MineOcclude/data/handoff_a/"
    "person_a_canonical_c6a_sagemaker_input_v0_1"
)
FOLD_PLAN_RELATIVE = Path("data/person_b/phase6_c_intake/layout_fold_plan.json")
CORE_CONFIG_RELATIVE = Path("configs/analysis/core.yaml")
RECEIPT_SCHEMA = "person-b-canonical-positive-control-b-to-a-receipt-v0.1"
BLOCKER_LAYOUTS = (
    "FROZEN_LAYOUT_GROUPED_OOF_REQUIRES_5_LAYOUTS_BUT_CANONICAL_BUNDLE_HAS_1"
)
BLOCKER_SHUFFLE = (
    "GROUPED_SHUFFLED_CONTROL_REQUIRES_AT_LEAST_2_TRAJECTORIES_"
    "BUT_CANONICAL_BUNDLE_HAS_1"
)


class CanonicalPositiveControlError(RuntimeError):
    """Fail-closed canonical receipt error."""


def _fail(message: str) -> None:
    raise CanonicalPositiveControlError(message)


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _load_object(path: Path, label: str) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_bytes())
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        _fail(f"Could not read {label}: {error}")
    if not isinstance(value, Mapping):
        _fail(f"{label} must be a JSON object.")
    return value


def _jsonl_rows(path: Path, label: str) -> list[Mapping[str, Any]]:
    try:
        values = [json.loads(line) for line in path.read_bytes().splitlines() if line]
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        _fail(f"Could not read {label}: {error}")
    if any(not isinstance(value, Mapping) for value in values):
        _fail(f"{label} contains a non-object row.")
    return values


def _git(repository: Path, *arguments: str) -> str:
    try:
        return subprocess.run(
            ["git", "-C", str(repository), *arguments],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as error:
        _fail(f"Git preflight failed: {error}")


def require_clean_repository(repository: Path) -> str:
    """Require the named branch, required ancestry, and a clean worktree."""

    if _git(repository, "branch", "--show-current") != REQUIRED_BRANCH:
        _fail(f"Execution requires branch {REQUIRED_BRANCH}.")
    if _git(repository, "status", "--porcelain=v1", "-uall"):
        _fail("Execution requires a clean Person B worktree.")
    _git(repository, "merge-base", "--is-ancestor", REQUIRED_STARTING_ANCESTOR, "HEAD")
    if _git(repository, "cat-file", "-t", PERSON_A_COMMIT) != "commit":
        _fail("The canonical Person A commit object is unavailable.")
    return _git(repository, "rev-parse", "HEAD")


def _safe_bundle_path(bundle_root: Path, relative: str) -> Path:
    pure = PurePosixPath(relative)
    if not relative or pure.is_absolute() or ".." in pure.parts:
        _fail(f"Unsafe bundle-relative path: {relative!r}.")
    path = (bundle_root / Path(*pure.parts)).resolve()
    try:
        path.relative_to(bundle_root)
    except ValueError as error:
        raise CanonicalPositiveControlError(
            f"Bundle path escapes its root: {relative!r}."
        ) from error
    return path


def verify_output_bundle(bundle_root: Path) -> tuple[Mapping[str, Any], list[dict[str, Any]]]:
    """Verify the exact bundle manifest plus every inventoried output byte."""

    bundle_root = bundle_root.resolve()
    manifest_path = bundle_root / "output_bundle_manifest.json"
    if _sha256_file(manifest_path) != EXPECTED_OUTPUT_BUNDLE_SHA256:
        _fail("Output bundle manifest SHA-256 differs from canonical authority.")
    manifest = _load_object(manifest_path, "output bundle manifest")
    if any(
        manifest.get(key) != expected
        for key, expected in {
            "schema_version": "person-a-canonical-sagemaker-output-bundle-v0.1",
            "status": "READY_FOR_LOCAL_RETRIEVAL",
            "trajectory_id": TRAJECTORY_ID,
            "episode_id": EPISODE_ID,
            "activation_chunk_count": EXPECTED_CHUNK_COUNT,
        }.items()
    ):
        _fail("Output bundle manifest conflicts with canonical authority.")

    inventory = _load_object(bundle_root / "sha256_inventory.json", "bundle inventory")
    rows = inventory.get("files")
    if not isinstance(rows, list) or not rows:
        _fail("Output bundle inventory is empty or malformed.")
    verified: list[dict[str, Any]] = []
    observed: set[str] = set()
    for row in rows:
        if not isinstance(row, Mapping):
            _fail("Output bundle inventory contains a malformed descriptor.")
        relative = row.get("path")
        if not isinstance(relative, str) or relative in observed:
            _fail("Output bundle inventory path is missing or duplicated.")
        path = _safe_bundle_path(bundle_root, relative)
        if (
            not path.is_file()
            or path.is_symlink()
            or path.stat().st_size != row.get("size_bytes")
            or _sha256_file(path) != row.get("sha256")
        ):
            _fail(f"Output bundle artifact differs: {relative}.")
        observed.add(relative)
        verified.append(
            {
                "path": str(path),
                "sha256": str(row["sha256"]),
                "size_bytes": int(row["size_bytes"]),
            }
        )
    return manifest, verified


def verify_handoff_and_activations(
    bundle_root: Path,
) -> tuple[Mapping[str, Any], Mapping[str, Any], Any, list[dict[str, Any]]]:
    """Verify the exact handoff, manifest, index, and every declared chunk."""

    handoff_path = bundle_root / "person_a_to_person_b_canonical_pilot_handoff.json"
    if _sha256_file(handoff_path) != EXPECTED_HANDOFF_SHA256:
        _fail("A-to-B handoff SHA-256 differs from canonical authority.")
    handoff = _load_object(handoff_path, "A-to-B handoff")
    required = {
        "schema_version": "person-a-to-person-b-canonical-pilot-handoff-v0.1",
        "status": "READY_FOR_PERSON_B_CONSUMPTION",
        "trajectory_id": TRAJECTORY_ID,
        "episode_id": EPISODE_ID,
        "expected_activation_row_count": EXPECTED_ACTIVATION_ROWS,
        "direct_pooling_validation": "PASS",
        "no_wall_visible_positive_control": True,
        "shuffled_comparison_required": True,
    }
    if any(handoff.get(key) != value for key, value in required.items()):
        _fail("A-to-B handoff conflicts with canonical task identity.")
    if handoff.get("grouping") != {"key": "layout_id", "value": LAYOUT_ID}:
        _fail("A-to-B handoff grouping differs from layout_id/layout_01.")

    accepted_path = bundle_root / "accepted_pilot_manifest.json"
    if _sha256_file(accepted_path) != EXPECTED_ACCEPTED_MANIFEST_SHA256:
        _fail("Accepted-manifest SHA-256 differs from canonical authority.")
    accepted = _load_object(accepted_path, "accepted pilot manifest")
    if (
        accepted.get("status") != "ACCEPTED_FOR_FROZEN_A6_1_TO_A6_5"
        or accepted.get("selected_trajectory_id") != TRAJECTORY_ID
        or accepted.get("selected_episode_id") != EPISODE_ID
        or accepted.get("grouping") != {"key": "layout_id", "value": LAYOUT_ID}
    ):
        _fail("Accepted pilot manifest conflicts with the handoff.")

    artifacts = handoff.get("activation_artifacts")
    if not isinstance(artifacts, list) or len(artifacts) != EXPECTED_CHUNK_COUNT + 1:
        _fail("Handoff activation artifact count differs.")
    chunks = [row for row in artifacts if row.get("type") == "activation_chunk"]
    indexes = [row for row in artifacts if row.get("type") == "activation_index"]
    if len(chunks) != EXPECTED_CHUNK_COUNT or len(indexes) != 1:
        _fail("Handoff must contain exactly 20 chunks and one index.")
    index_claim = indexes[0]
    if index_claim.get("sha256") != EXPECTED_INDEX_SHA256:
        _fail("Activation-index SHA-256 differs from canonical authority.")
    index_path = bundle_root / "activation_store" / "indexes" / Path(
        str(index_claim["path"])
    ).name
    index_document = _load_object(index_path, "activation index")
    descriptors = {
        str(row.get("chunk_id")): row
        for row in index_document.get("chunks", [])
        if isinstance(row, Mapping)
    }
    chunk_claim_by_name = {Path(str(row["path"])).name: row for row in chunks}
    bindings: dict[str, ExternalChunkBinding] = {}
    verified: list[dict[str, Any]] = []
    for chunk_id, descriptor in descriptors.items():
        filename = Path(str(descriptor["path"])).name
        claim = chunk_claim_by_name.get(filename)
        path = bundle_root / "activation_store" / "chunks" / filename
        if (
            claim is None
            or claim.get("sha256") != descriptor.get("sha256")
            or claim.get("byte_size") != descriptor.get("byte_size")
            or _sha256_file(path) != claim.get("sha256")
            or path.stat().st_size != claim.get("byte_size")
        ):
            _fail(f"Activation chunk differs: {filename}.")
        bindings[chunk_id] = ExternalChunkBinding(
            chunk_id=chunk_id,
            path=path,
            sha256=str(claim["sha256"]),
            byte_size=int(claim["byte_size"]),
            row_count=int(descriptor["row_count"]),
        )
        verified.append(
            {
                "byte_size": int(claim["byte_size"]),
                "path": str(path.resolve()),
                "sha256": str(claim["sha256"]),
                "type": "activation_chunk",
            }
        )
    if set(chunk_claim_by_name) != {
        Path(str(value["path"])).name for value in descriptors.values()
    }:
        _fail("Handoff and index chunk sets differ.")
    loaded = load_activation_index_v2(
        index_path,
        canonicalization_contract=(
            PERSON_A_ACTIVATION_INDEX_V2_CANONICALIZATION_CONTRACT
        ),
        expected_index_sha256=EXPECTED_INDEX_SHA256,
        expected_index_byte_size=int(index_claim["byte_size"]),
        expected_trajectory_id=TRAJECTORY_ID,
        expected_manifest_sha256=EXPECTED_CAPTURE_PACKAGE_SHA256,
        chunk_bindings=bindings,
        retain_vectors=False,
    )
    if loaded.activation_row_count != EXPECTED_ACTIVATION_ROWS:
        _fail("Loaded activation row count differs from 1,200.")
    verified.append(
        {
            "byte_size": int(index_claim["byte_size"]),
            "path": str(index_path.resolve()),
            "sha256": EXPECTED_INDEX_SHA256,
            "type": "activation_index",
        }
    )
    return handoff, accepted, loaded, sorted(verified, key=lambda row: row["path"])


def _source_descriptor(
    accepted: Mapping[str, Any], relative_path: str
) -> Mapping[str, Any]:
    rows = accepted.get("direct_episode_artifacts")
    matches = [
        row
        for row in rows
        if isinstance(row, Mapping) and row.get("relative_path") == relative_path
    ] if isinstance(rows, list) else []
    if len(matches) != 1:
        _fail(f"Accepted manifest lacks one exact {relative_path} descriptor.")
    return matches[0]


def _verify_source_file(descriptor: Mapping[str, Any], label: str) -> Path:
    path = Path(str(descriptor.get("path", ""))).resolve()
    if (
        not path.is_file()
        or path.is_symlink()
        or path.stat().st_size != descriptor.get("size_bytes")
        or _sha256_file(path) != descriptor.get("sha256")
    ):
        _fail(f"Canonical {label} source bytes differ from accepted authority.")
    return path


def _person_a_source_row_digest(row: Mapping[str, Any]) -> str:
    return _sha256_bytes(
        canonical_json_bytes_for_artifact(
            row,
            artifact_type=PERSON_A_ACTIVATION_SOURCE_ROW_V2_ARTIFACT_TYPE,
            canonicalization_contract=(
                PERSON_A_ACTIVATION_SOURCE_ROW_V2_CANONICALIZATION_CONTRACT
            ),
        )
    )


def verify_source_identity_join(
    accepted: Mapping[str, Any], loaded: Any
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Rebuild Person A's exact frame/state rows and join all activation rows."""

    client_descriptor = _source_descriptor(accepted, "client_tick.jsonl")
    state_descriptor = _source_descriptor(accepted, "server_state.jsonl")
    client_path = _verify_source_file(client_descriptor, "client-tick")
    state_path = _verify_source_file(state_descriptor, "server-state")
    clients = _jsonl_rows(client_path, "client-tick source")
    states = _jsonl_rows(state_path, "server-state source")
    if len(clients) != 60 or len(states) != 60:
        _fail("Canonical source streams must each contain exactly 60 rows.")

    activation_rows_by_frame: dict[int, list[Mapping[str, Any]]] = defaultdict(list)
    for row in loaded.rows:
        activation_rows_by_frame[int(row["global_model_frame_idx"])].append(row)
    if set(activation_rows_by_frame) != set(range(60)):
        _fail("Activation rows do not cover all 60 global frames exactly.")

    labels: list[dict[str, Any]] = []
    matched_rows = 0
    layer_ids = set(loaded.store_identity["requested_layers"])
    for index, (client, state) in enumerate(zip(clients, states, strict=True)):
        if (
            client.get("episode_id") != EPISODE_ID
            or client.get("server_tick") != index
            or client.get("render_frame_idx") != index
            or state.get("episode_id") != EPISODE_ID
            or state.get("server_tick") != index
            or state.get("layout_id") != LAYOUT_ID
            or state.get("scene") != "NO_WALL"
            or state.get("geometric_visible") is not True
            or client.get("server_epoch_nanos") != state.get("server_epoch_nanos")
        ):
            _fail(f"Canonical source identity differs at global frame {index}.")
        position = state.get("axis_pos")
        if (
            isinstance(position, bool)
            or not isinstance(position, (int, float))
            or not math.isfinite(float(position))
        ):
            _fail(f"Canonical label is invalid at global frame {index}.")
        identity = {
            "action_idx": index,
            "episode_id": str(EPISODE_ID),
            "model_frame_idx": index,
            "render_frame_idx": index,
            "server_tick": index,
            "trajectory_id": TRAJECTORY_ID,
        }
        source_client_hash = _sha256_bytes(_canonical_json_bytes(client))
        source_state_hash = _sha256_bytes(_canonical_json_bytes(state))
        frame_descriptor = _source_descriptor(
            accepted, f"frames/{index:06d}.png"
        )
        frame_row = {
            **identity,
            "source_client_tick_row_sha256": source_client_hash,
            "source_frame_path": str(
                PERSON_A_SAGEMAKER_SOURCE_ROOT
                / "episode"
                / "client"
                / "frames"
                / f"{index:06d}.png"
            ),
            "source_frame_sha256": frame_descriptor["sha256"],
            "source_server_epoch_nanos": client["server_epoch_nanos"],
        }
        state_row = {
            **identity,
            "source_server_state_row_sha256": source_state_hash,
            "state": {
                "position_x_blocks": float(state["sheep_x"]),
                "position_y_blocks": float(state["sheep_y"]),
                "position_z_blocks": float(state["sheep_z"]),
                "target_entity_id": f"canonical_sheep_{EPISODE_ID}",
                "target_present": True,
                "velocity_x_blocks_per_second": float(state["axis_velocity"]),
                "velocity_y_blocks_per_second": 0.0,
                "velocity_z_blocks_per_second": 0.0,
                "wall_parallel_position_blocks": float(position),
            },
        }
        frame_digest = _person_a_source_row_digest(frame_row)
        state_digest = _person_a_source_row_digest(state_row)
        frame_activations = activation_rows_by_frame[index]
        if (
            len(frame_activations) != len(layer_ids)
            or {row["layer_idx"] for row in frame_activations} != layer_ids
        ):
            _fail(f"Layer coverage differs at global frame {index}.")
        for row in frame_activations:
            expected = {
                "c_frame_map_row_sha256": frame_digest,
                "c_frame_map_sha256": client_descriptor["sha256"],
                "c_state_row_sha256": state_digest,
                "c_state_sha256": state_descriptor["sha256"],
                "global_model_frame_idx": index,
                "source_frame_id": f"{TRAJECTORY_ID}:render_frame:{index}",
                "source_frame_idx": index,
                "source_tick": index,
                "trajectory_id": TRAJECTORY_ID,
            }
            if any(row.get(key) != value for key, value in expected.items()):
                _fail(f"Activation/source-row join differs at frame {index}.")
            matched_rows += 1
        labels.append(
            {
                "global_model_frame_idx": index,
                "layout_id": LAYOUT_ID,
                "source_state_row_sha256": source_state_hash,
                "target_name": "x_true_blocks",
                "target_value": float(position),
                "trajectory_id": TRAJECTORY_ID,
            }
        )
    if matched_rows != EXPECTED_ACTIVATION_ROWS:
        _fail("Exact source-row join did not cover all activation rows.")
    return labels, {
        "activation_rows_matched": matched_rows,
        "client_tick_path": str(client_path),
        "client_tick_sha256": str(client_descriptor["sha256"]),
        "frame_rows_matched": 60,
        "server_state_path": str(state_path),
        "server_state_sha256": str(state_descriptor["sha256"]),
        "source_identity_join_pass": True,
        "state_rows_matched": 60,
    }


def execution_eligibility(
    layout_ids: Sequence[str], trajectory_ids: Sequence[str]
) -> tuple[list[str], dict[str, Any], dict[str, Any]]:
    """Apply the frozen grouped-OOF and whole-trajectory shuffle gates."""

    layout_count = len(set(layout_ids))
    trajectory_count = len(set(trajectory_ids))
    blockers = []
    if layout_count < 5:
        blockers.append(BLOCKER_LAYOUTS)
    if trajectory_count < 2:
        blockers.append(BLOCKER_SHUFFLE)
    real = {
        "attempted": True,
        "complete": layout_count >= 5,
        "metrics": [],
        "status": "NOT_RUN_INSUFFICIENT_FROZEN_LAYOUT_GROUPS",
    }
    shuffled = {
        "attempted": True,
        "complete": layout_count >= 5 and trajectory_count >= 2,
        "metrics": [],
        "status": "NOT_RUN_INSUFFICIENT_WHOLE_TRAJECTORY_GROUPS",
    }
    if real["complete"] or shuffled["complete"]:
        _fail("Canonical single-pilot eligibility unexpectedly expanded.")
    return blockers, real, shuffled


def _fold_authority(repository: Path) -> tuple[Mapping[str, Any], Mapping[str, Any], int]:
    fold_plan_path = repository / FOLD_PLAN_RELATIVE
    config_path = repository / CORE_CONFIG_RELATIVE
    fold_plan = _load_object(fold_plan_path, "frozen layout fold plan")
    config = _load_object(config_path, "frozen analysis config")
    assignments = fold_plan.get("layout_assignments")
    matches = [
        row
        for row in assignments
        if isinstance(row, Mapping) and row.get("layout_id") == LAYOUT_ID
    ] if isinstance(assignments, list) else []
    if len(matches) != 1 or matches[0].get("fold_idx") != 2:
        _fail("Frozen layout plan does not assign layout_01 exclusively to fold 2.")
    cross_validation = config.get("cross_validation")
    ridge = config.get("ridge")
    resampling = config.get("resampling")
    if (
        not isinstance(cross_validation, Mapping)
        or not isinstance(ridge, Mapping)
        or not isinstance(resampling, Mapping)
        or cross_validation.get("strategy") != "layout_grouped"
        or cross_validation.get("fold_count") != 5
        or cross_validation.get("inner_strategy") != "layout_grouped"
        or cross_validation.get("inner_fold_count") != 4
        or ridge.get("alpha_grid") != [0.1, 1.0, 10.0, 100.0]
        or resampling.get("permutation_count_mvp") != 999
        or resampling.get("permutation_unit") != "whole_trajectory_block"
    ):
        _fail("Frozen positive-control configuration differs.")
    return fold_plan, config, 2


def build_receipt(
    *,
    repository: Path,
    bundle_root: Path,
    execution_commit: str,
) -> dict[str, Any]:
    manifest, bundle_files = verify_output_bundle(bundle_root)
    handoff, accepted, loaded, activation_artifacts = verify_handoff_and_activations(
        bundle_root
    )
    labels, source_join = verify_source_identity_join(accepted, loaded)
    fold_plan, config, fold_idx = _fold_authority(repository)
    blockers, real, shuffled = execution_eligibility(
        [LAYOUT_ID], [TRAJECTORY_ID]
    )
    layer_counts = Counter(int(row["layer_idx"]) for row in loaded.rows)
    target_values = [float(row["target_value"]) for row in labels]
    return {
        "activation_artifact_count": len(activation_artifacts),
        "activation_artifacts": activation_artifacts,
        "activation_index_valid": True,
        "activation_row_count": loaded.activation_row_count,
        "a_output_bundle_valid": True,
        "a_to_b_handoff_valid": True,
        "decision": {
            "automatic_hidden_state_transition": False,
            "positive_control_pass": False,
            "status": "STOP_FOR_DIAGNOSIS_INSUFFICIENT_FROZEN_GROUPS",
        },
        "episode_id": EPISODE_ID,
        "execution": {
            "branch": REQUIRED_BRANCH,
            "person_a_commit": PERSON_A_COMMIT,
            "person_b_execution_commit": execution_commit,
            "required_starting_ancestor": REQUIRED_STARTING_ANCESTOR,
            "scientific_fit_performed": False,
        },
        "fold_identities": {
            "available_outer_fold_indices": [fold_idx],
            "fold_count_required": 5,
            "grouping_key": handoff["grouping"]["key"],
            "grouping_value": handoff["grouping"]["value"],
            "layout_assignments": [{"fold_idx": fold_idx, "layout_id": LAYOUT_ID}],
            "unavailable_outer_fold_indices": [0, 1, 3, 4],
        },
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "immutable": True,
        "label_authority": {
            "label_count_per_layer": 60,
            "label_source": "canonical_server_state.axis_pos",
            "maximum_x_true_blocks": max(target_values),
            "minimum_x_true_blocks": min(target_values),
            "target_name": "x_true_blocks",
            "target_unit": "blocks",
        },
        "layer_row_counts": [
            {"layer_idx": layer, "row_count": layer_counts[layer]}
            for layer in sorted(layer_counts)
        ],
        "probe_configuration": {
            "alpha_grid": list(config["ridge"]["alpha_grid"]),
            "inner_fold_count": config["cross_validation"]["inner_fold_count"],
            "inner_strategy": config["cross_validation"]["inner_strategy"],
            "outer_fold_count": config["cross_validation"]["fold_count"],
            "outer_split_seed": config["cross_validation"]["split_seed"],
            "outer_strategy": config["cross_validation"]["strategy"],
            "target_name": "x_true_blocks",
        },
        "real_label_positive_control": real,
        "remaining_blockers": blockers,
        "schema_version": RECEIPT_SCHEMA,
        "shuffled_control": {
            **shuffled,
            "permutation_count": config["resampling"]["permutation_count_mvp"],
            "permutation_p_value": config["resampling"]["permutation_p_value"],
            "permutation_seed": config["resampling"]["permutation_seed"],
            "permutation_unit": config["resampling"]["permutation_unit"],
        },
        "source_hashes": {
            "accepted_manifest_sha256": EXPECTED_ACCEPTED_MANIFEST_SHA256,
            "activation_index_sha256": EXPECTED_INDEX_SHA256,
            "a_to_b_handoff_sha256": EXPECTED_HANDOFF_SHA256,
            "bundle_inventory_file_count": len(bundle_files),
            "capture_package_sha256": EXPECTED_CAPTURE_PACKAGE_SHA256,
            "fold_plan_artifact_hash": fold_plan.get("artifact_hash"),
            "fold_plan_file_sha256": _sha256_file(repository / FOLD_PLAN_RELATIVE),
            "output_bundle_manifest_sha256": EXPECTED_OUTPUT_BUNDLE_SHA256,
            **source_join,
        },
        "source_identity_join_pass": True,
        "thresholds": {
            "numeric_pass_threshold_added": False,
            "policy": "human_scientific_gate_no_unfrozen_numeric_threshold",
        },
        "trajectory_id": TRAJECTORY_ID,
    }


def validate_receipt(document: Mapping[str, Any]) -> None:
    """Validate the canonical fail-closed receipt schema and invariants."""

    if (
        document.get("schema_version") != RECEIPT_SCHEMA
        or document.get("immutable") is not True
        or document.get("a_output_bundle_valid") is not True
        or document.get("a_to_b_handoff_valid") is not True
        or document.get("activation_index_valid") is not True
        or document.get("activation_row_count") != EXPECTED_ACTIVATION_ROWS
        or document.get("source_identity_join_pass") is not True
        or document.get("trajectory_id") != TRAJECTORY_ID
        or document.get("episode_id") != EPISODE_ID
    ):
        _fail("Receipt identity, bundle, activation, or join status is invalid.")
    decision = document.get("decision")
    real = document.get("real_label_positive_control")
    shuffled = document.get("shuffled_control")
    if (
        not isinstance(decision, Mapping)
        or decision.get("positive_control_pass") is not False
        or decision.get("status")
        != "STOP_FOR_DIAGNOSIS_INSUFFICIENT_FROZEN_GROUPS"
        or not isinstance(real, Mapping)
        or real.get("complete") is not False
        or real.get("metrics") != []
        or not isinstance(shuffled, Mapping)
        or shuffled.get("complete") is not False
        or shuffled.get("metrics") != []
        or document.get("remaining_blockers") != [BLOCKER_LAYOUTS, BLOCKER_SHUFFLE]
    ):
        _fail("Receipt does not preserve the fail-closed execution decision.")
    folds = document.get("fold_identities")
    if (
        not isinstance(folds, Mapping)
        or folds.get("grouping_key") != "layout_id"
        or folds.get("available_outer_fold_indices") != [2]
        or folds.get("unavailable_outer_fold_indices") != [0, 1, 3, 4]
    ):
        _fail("Receipt fold identities differ from frozen authority.")


def _write_exclusive(path: Path, document: Mapping[str, Any]) -> None:
    if path.exists() or path.is_symlink():
        _fail(f"Immutable receipt already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _canonical_json_bytes(document)
    try:
        with path.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as error:
        _fail(f"Could not write immutable receipt: {error}")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--bundle-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    repository = args.repository_root.resolve()
    bundle_root = args.bundle_root.resolve()
    execution_commit = require_clean_repository(repository)
    receipt = build_receipt(
        repository=repository,
        bundle_root=bundle_root,
        execution_commit=execution_commit,
    )
    validate_receipt(receipt)
    output = args.output.resolve()
    _write_exclusive(output, receipt)
    print(
        json.dumps(
            {
                "receipt": str(output),
                "sha256": _sha256_file(output),
                "status": receipt["decision"]["status"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
