#!/usr/bin/env python3
"""Run the frozen Person B control on the canonical five-layout successor.

This is the additive successor to ``run_person_b_canonical_positive_control``.
It authenticates the exact Person A collection, rebuilds every source-row join,
runs the frozen layout-grouped ridge control, runs the 999 whole-trajectory
label permutations, and writes one create-only B-to-A receipt.
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
from mineocclude.analysis.config import load_core_analysis_config  # noqa: E402
from mineocclude.metrics.resampling import (  # noqa: E402
    permutation_p_value,
    permute_trajectory_blocks,
)
from mineocclude.probes.ridge import (  # noqa: E402
    _group_fold_assignments,
    fit_ridge_oof,
)
from mineocclude.probes.splits import assign_layout_grouped_folds  # noqa: E402


REQUIRED_BRANCH = "role/person-b-analysis"
REQUIRED_STARTING_ANCESTOR = "66279eee242a353423e1b084bdfa39f480274909"
PERSON_A_COMMIT = "1858ea12513f833b62ea916e0691ae994f117428"
COLLECTION_MANIFEST_SHA256 = (
    "a672c834e8af3fd12c735e4042951b7b90d0aeeed5b0b62790aacdf3a58c0db0"
)
A_TO_B_HANDOFF_SHA256 = (
    "9d932df3aec859b17a4bbdd2afaa31d81dcb21c2bb62db668ed4158cbb855d94"
)
TRAJECTORIES = (
    "layout_01_ep12602",
    "layout_02_ep12610",
    "layout_03_ep12645",
    "layout_04_ep12626",
    "layout_05_ep12634",
)
LAYOUTS = ("layout_01", "layout_02", "layout_03", "layout_04", "layout_05")
EPISODES = (12602, 12610, 12645, 12626, 12634)
EXPECTED_ACTIVATION_ROWS = 6_000
EXPECTED_CHUNK_COUNT = 100
EXPECTED_INDEX_COUNT = 5
EXPECTED_FRAMES = 300
EXPECTED_LAYERS = tuple(range(20))
ROWS_PER_TRAJECTORY = 1_200
FRAMES_PER_TRAJECTORY = 60
ALPHA_GRID = (0.1, 1.0, 10.0, 100.0)
OUTER_FOLD_COUNT = 5
INNER_FOLD_COUNT = 4
SPLIT_SEED = 20260719
PERMUTATION_COUNT = 999
PERMUTATION_SEED = 20260720
RECEIPT_SCHEMA = (
    "person-b-canonical-multilayout-positive-control-b-to-a-receipt-v0.1"
)
COMPLETED_RESULTS_SCHEMA = (
    "person-b-canonical-multilayout-completed-control-results-v0.1"
)
FROZEN_THRESHOLD_POLICY = "human_scientific_gate_no_unfrozen_numeric_threshold"
PREDECESSOR_RECEIPT_RELATIVE = Path(
    "docs/status/person_b_canonical_positive_control_layout_01_ep12602_v0_1/"
    "b_to_a_receipt.json"
)
PREDECESSOR_RECEIPT_SHA256 = (
    "6e777d11273bf25267b694b551eb2627dc6dc30f6226988cced4bc0134a45fe8"
)
CORE_CONFIG_RELATIVE = Path("configs/analysis/core.yaml")
FROZEN_REVIEW_RULE = (
    "at_least_one_reviewed_layer_has_positive_global_r2_and_positive_global_"
    "pearson_r_and_positive_pearson_r_in_every_one_of_five_held_out_layouts"
)


class CanonicalMultilayoutPositiveControlError(RuntimeError):
    """Fail-closed successor positive-control error."""


def _fail(message: str) -> None:
    raise CanonicalMultilayoutPositiveControlError(message)


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


def require_clean_repository(repository: Path, person_a_repository: Path) -> str:
    """Require the exact role branch, ancestry, clean tree, and A commit."""

    if _git(repository, "branch", "--show-current") != REQUIRED_BRANCH:
        _fail(f"Execution requires branch {REQUIRED_BRANCH}.")
    if _git(repository, "status", "--porcelain=v1", "-uall"):
        _fail("Execution requires a clean Person B worktree.")
    _git(
        repository,
        "merge-base",
        "--is-ancestor",
        REQUIRED_STARTING_ANCESTOR,
        "HEAD",
    )
    if _git(person_a_repository, "rev-parse", "HEAD") != PERSON_A_COMMIT:
        _fail("Person A worktree is not at the exact successor commit.")
    if _git(person_a_repository, "status", "--porcelain=v1", "-uall"):
        _fail("Person A successor worktree must remain clean.")
    return _git(repository, "rev-parse", "HEAD")


def _verify_file(path: Path, descriptor: Mapping[str, Any], label: str) -> None:
    if (
        not path.is_file()
        or path.is_symlink()
        or (
            "size_bytes" in descriptor
            and path.stat().st_size != descriptor.get("size_bytes")
        )
        or _sha256_file(path) != descriptor.get("sha256")
    ):
        _fail(f"{label} bytes differ: {path}")


def _verify_package_inventory(collection_root: Path) -> Mapping[str, Any]:
    inventory = _load_object(
        collection_root / "sha256_inventory.json", "collection inventory"
    )
    rows = inventory.get("files")
    if not isinstance(rows, list) or len(rows) != 4:
        _fail("Collection inventory must contain exactly four package files.")
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, Mapping):
            _fail("Collection inventory contains a malformed descriptor.")
        relative = row.get("path")
        if (
            not isinstance(relative, str)
            or not relative
            or relative in seen
            or PurePosixPath(relative).is_absolute()
            or ".." in PurePosixPath(relative).parts
        ):
            _fail("Collection inventory path is invalid or duplicated.")
        seen.add(relative)
        _verify_file(collection_root / relative, row, "collection artifact")
    return inventory


def _verify_collection(
    collection_root: Path,
) -> tuple[Mapping[str, Any], Mapping[str, Any], Mapping[str, Any]]:
    manifest_path = collection_root / "collection_manifest.json"
    handoff_path = (
        collection_root / "person_a_to_person_b_canonical_multilayout_handoff.json"
    )
    if _sha256_file(manifest_path) != COLLECTION_MANIFEST_SHA256:
        _fail("Collection-manifest SHA-256 differs from successor authority.")
    if _sha256_file(handoff_path) != A_TO_B_HANDOFF_SHA256:
        _fail("A-to-B handoff SHA-256 differs from successor authority.")
    _verify_package_inventory(collection_root)
    manifest = _load_object(manifest_path, "collection manifest")
    handoff = _load_object(handoff_path, "successor A-to-B handoff")
    required_manifest = {
        "activation_chunk_count": EXPECTED_CHUNK_COUNT,
        "activation_index_count": EXPECTED_INDEX_COUNT,
        "activation_row_count": EXPECTED_ACTIVATION_ROWS,
        "canonical_c6a_id": "person-c-c6a-post-c1-v0.1",
        "layout_count": len(LAYOUTS),
        "no_missing_extra_duplicate_stale_or_reordered_rows": True,
        "status": "READY_FOR_PERSON_B_AND_PERSON_E_REVIEW",
        "trajectory_count": len(TRAJECTORIES),
    }
    if any(manifest.get(key) != value for key, value in required_manifest.items()):
        _fail("Collection manifest identity or cardinality differs.")
    required_handoff = {
        "activation_chunk_count": EXPECTED_CHUNK_COUNT,
        "activation_row_count": EXPECTED_ACTIVATION_ROWS,
        "canonical_c6a_id": "person-c-c6a-post-c1-v0.1",
        "scientific_use_acceptance_claimed": False,
        "status": "READY_FOR_PERSON_B_FROZEN_POSITIVE_CONTROL",
    }
    if (
        any(handoff.get(key) != value for key, value in required_handoff.items())
        or tuple(handoff.get("trajectory_ids", ())) != TRAJECTORIES
        or handoff.get("grouping")
        != {"key": "layout_id", "values": list(LAYOUTS)}
        or handoff.get("label_authority")
        != {
            "source": "canonical_server_state.axis_pos",
            "target_name": "x_true_blocks",
            "unit": "blocks",
        }
    ):
        _fail("Successor A-to-B handoff changes a frozen identity.")
    certification = handoff.get("certification")
    if certification != {
        "all_direct_pooling_audits": "PASS",
        "all_repeatability_checks": "PASS",
        "all_source_identity_joins": "PASS",
        "missing_extra_duplicate_stale_or_reordered_rows": 0,
    }:
        _fail("Successor A-to-B certification differs.")
    frozen = handoff.get("person_b_frozen_execution")
    if (
        not isinstance(frozen, Mapping)
        or frozen.get("grouping_key") != "layout_id"
        or frozen.get("outer_fold_count") != OUTER_FOLD_COUNT
        or frozen.get("inner_fold_count") != INNER_FOLD_COUNT
        or frozen.get("required_distinct_layout_count") != len(LAYOUTS)
        or frozen.get("required_distinct_trajectory_count") != len(TRAJECTORIES)
        or frozen.get("shuffled_control")
        != {
            "minimum_trajectory_count": 2,
            "permutation_count": PERMUTATION_COUNT,
            "permutation_p_value": "add_one_greater_or_equal",
            "permutation_seed": PERMUTATION_SEED,
            "permutation_unit": "whole_trajectory_block",
        }
    ):
        _fail("Successor handoff differs from frozen Person B execution settings.")
    runs = manifest.get("runs")
    if (
        not isinstance(runs, list)
        or len(runs) != len(TRAJECTORIES)
        or tuple(row.get("trajectory_id") for row in runs) != TRAJECTORIES
        or tuple(row.get("layout_id") for row in runs) != LAYOUTS
        or tuple(row.get("episode_id") for row in runs) != EPISODES
    ):
        _fail("Collection run order or identities differ.")
    logical = manifest.get("logical_order")
    if not isinstance(logical, list) or len(logical) != EXPECTED_INDEX_COUNT:
        _fail("Collection logical multi-index order is malformed.")
    for index, (row, trajectory_id) in enumerate(zip(logical, TRAJECTORIES)):
        if (
            not isinstance(row, Mapping)
            or row.get("trajectory_id") != trajectory_id
            or row.get("logical_row_start_inclusive") != index * ROWS_PER_TRAJECTORY
            or row.get("logical_row_stop_exclusive")
            != (index + 1) * ROWS_PER_TRAJECTORY
        ):
            _fail("Collection logical row order differs.")
    return manifest, handoff, _load_object(
        collection_root / "external_activation_inventory.json",
        "external activation inventory",
    )


def _verify_frozen_authorities(repository: Path) -> dict[str, Any]:
    predecessor_path = repository / PREDECESSOR_RECEIPT_RELATIVE
    config_path = repository / CORE_CONFIG_RELATIVE
    if _sha256_file(predecessor_path) != PREDECESSOR_RECEIPT_SHA256:
        _fail("Predecessor blocker receipt SHA-256 differs.")
    predecessor = _load_object(predecessor_path, "predecessor blocker receipt")
    config = load_core_analysis_config(config_path)
    cv = config.get("cross_validation")
    ridge = config.get("ridge")
    resampling = config.get("resampling")
    if (
        predecessor.get("thresholds")
        != {
            "numeric_pass_threshold_added": False,
            "policy": FROZEN_THRESHOLD_POLICY,
        }
        or predecessor.get("probe_configuration", {}).get("target_name")
        != "x_true_blocks"
        or not isinstance(cv, Mapping)
        or cv.get("strategy") != "layout_grouped"
        or cv.get("fold_count") != OUTER_FOLD_COUNT
        or cv.get("split_seed") != SPLIT_SEED
        or cv.get("inner_strategy") != "layout_grouped"
        or cv.get("inner_fold_count") != INNER_FOLD_COUNT
        or not isinstance(ridge, Mapping)
        or tuple(ridge.get("alpha_grid", ())) != ALPHA_GRID
        or not isinstance(resampling, Mapping)
        or resampling.get("permutation_count_mvp") != PERMUTATION_COUNT
        or resampling.get("permutation_seed") != PERMUTATION_SEED
        or resampling.get("permutation_unit") != "whole_trajectory_block"
        or resampling.get("permutation_p_value") != "add_one_greater_or_equal"
    ):
        _fail("Predecessor receipt or frozen core configuration differs.")
    return {
        "core_config_path": str(config_path.resolve()),
        "core_config_sha256": _sha256_file(config_path),
        "predecessor_blocker_receipt_path": str(predecessor_path.resolve()),
        "predecessor_blocker_receipt_sha256": PREDECESSOR_RECEIPT_SHA256,
        "predecessor_preserved_unchanged": True,
    }


def _source_descriptor(
    accepted: Mapping[str, Any], relative_path: str
) -> Mapping[str, Any]:
    rows = accepted.get("direct_episode_artifacts")
    matches = (
        [
            row
            for row in rows
            if isinstance(row, Mapping) and row.get("relative_path") == relative_path
        ]
        if isinstance(rows, list)
        else []
    )
    if len(matches) != 1:
        _fail(f"Accepted manifest lacks one exact {relative_path} descriptor.")
    return matches[0]


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


def _verify_run(
    person_a_repository: Path,
    run: Mapping[str, Any],
) -> tuple[
    dict[str, Any],
    list[float],
    list[dict[str, Any]],
]:
    trajectory_id = str(run["trajectory_id"])
    layout_id = str(run["layout_id"])
    episode_id = int(run["episode_id"])
    root = (
        person_a_repository
        / "docs/status/phase6_runtime"
        / PurePosixPath(str(run["output_bundle_root"])).name
    ).resolve()
    if not root.is_dir() or root.is_symlink():
        _fail(f"Local Person A output root is unavailable: {root}")
    descriptors = {
        "accepted_pilot_manifest.json": run["accepted_manifest"],
        "output_bundle_manifest.json": run["output_bundle_manifest"],
        "person_a_to_person_b_canonical_pilot_handoff.json": run["a_to_b_handoff"],
        "step6_5.json": run["certification"],
    }
    for name, descriptor in descriptors.items():
        _verify_file(root / name, descriptor, f"{trajectory_id} {name}")
    accepted = _load_object(root / "accepted_pilot_manifest.json", "accepted manifest")
    handoff = _load_object(
        root / "person_a_to_person_b_canonical_pilot_handoff.json",
        "per-run A-to-B handoff",
    )
    if (
        accepted.get("status") != "ACCEPTED_FOR_FROZEN_A6_1_TO_A6_5"
        or accepted.get("selected_trajectory_id") != trajectory_id
        or accepted.get("selected_episode_id") != episode_id
        or accepted.get("grouping") != {"key": "layout_id", "value": layout_id}
        or handoff.get("status") != "READY_FOR_PERSON_B_CONSUMPTION"
        or handoff.get("trajectory_id") != trajectory_id
        or handoff.get("episode_id") != episode_id
        or handoff.get("grouping") != {"key": "layout_id", "value": layout_id}
        or handoff.get("expected_activation_row_count") != ROWS_PER_TRAJECTORY
        or handoff.get("direct_pooling_validation") != "PASS"
        or handoff.get("no_wall_visible_positive_control") is not True
        or handoff.get("shuffled_comparison_required") is not True
        or handoff.get("exact_source_identity_joins", {}).get("status") != "PASS"
    ):
        _fail(f"Per-run accepted or A-to-B authority differs for {trajectory_id}.")
    direct_rows = accepted.get("direct_episode_artifacts")
    if not isinstance(direct_rows, list) or len(direct_rows) != 64:
        _fail(f"Direct canonical source inventory differs for {trajectory_id}.")
    for descriptor in direct_rows:
        if not isinstance(descriptor, Mapping):
            _fail("Direct canonical source descriptor is malformed.")
        _verify_file(
            Path(str(descriptor.get("path", ""))).resolve(),
            descriptor,
            f"{trajectory_id} canonical source",
        )
    index_claim = run.get("activation_index")
    artifacts = run.get("activation_artifacts")
    if (
        not isinstance(index_claim, Mapping)
        or not isinstance(artifacts, list)
        or len(artifacts) != 21
    ):
        _fail(f"Activation artifact envelope differs for {trajectory_id}.")
    index_path = root / "activation_store/indexes" / PurePosixPath(
        str(index_claim["path"])
    ).name
    _verify_file(index_path, index_claim, f"{trajectory_id} activation index")
    index_document = _load_object(index_path, "activation index")
    chunk_descriptors = index_document.get("chunks")
    if not isinstance(chunk_descriptors, list) or len(chunk_descriptors) != 20:
        _fail(f"Activation chunk count differs for {trajectory_id}.")
    bindings: dict[str, ExternalChunkBinding] = {}
    chunk_receipt_rows: list[dict[str, Any]] = []
    for descriptor in chunk_descriptors:
        if not isinstance(descriptor, Mapping):
            _fail("Activation index contains a malformed chunk descriptor.")
        path = root / "activation_store/chunks" / PurePosixPath(
            str(descriptor["path"])
        ).name
        _verify_file(path, descriptor, f"{trajectory_id} activation chunk")
        chunk_id = str(descriptor["chunk_id"])
        bindings[chunk_id] = ExternalChunkBinding(
            chunk_id=chunk_id,
            path=path,
            sha256=str(descriptor["sha256"]),
            byte_size=int(descriptor["byte_size"]),
            row_count=int(descriptor["row_count"]),
        )
        chunk_receipt_rows.append(
            {
                "byte_size": int(descriptor["byte_size"]),
                "chunk_id": chunk_id,
                "sha256": str(descriptor["sha256"]),
            }
        )
    loaded = load_activation_index_v2(
        index_path,
        canonicalization_contract=(
            PERSON_A_ACTIVATION_INDEX_V2_CANONICALIZATION_CONTRACT
        ),
        expected_index_sha256=str(index_claim["sha256"]),
        expected_index_byte_size=int(index_claim["byte_size"]),
        expected_trajectory_id=trajectory_id,
        expected_manifest_sha256=str(handoff["capture_package"]["sha256"]),
        chunk_bindings=bindings,
        retain_vectors=False,
    )
    if loaded.activation_row_count != ROWS_PER_TRAJECTORY:
        _fail(f"Loaded activation row count differs for {trajectory_id}.")
    client_descriptor = _source_descriptor(accepted, "client_tick.jsonl")
    state_descriptor = _source_descriptor(accepted, "server_state.jsonl")
    clients = _jsonl_rows(Path(str(client_descriptor["path"])), "client-tick source")
    states = _jsonl_rows(Path(str(state_descriptor["path"])), "server-state source")
    if len(clients) != FRAMES_PER_TRAJECTORY or len(states) != FRAMES_PER_TRAJECTORY:
        _fail(f"Canonical source row count differs for {trajectory_id}.")
    rows_by_frame: dict[int, list[Mapping[str, Any]]] = defaultdict(list)
    for row in loaded.rows:
        rows_by_frame[int(row["global_model_frame_idx"])].append(row)
    if set(rows_by_frame) != set(range(FRAMES_PER_TRAJECTORY)):
        _fail(f"Activation frame coverage differs for {trajectory_id}.")
    targets: list[float] = []
    metadata: list[dict[str, Any]] = []
    matched = 0
    source_root = PurePosixPath(str(handoff["capture_package"]["path"])).parent
    for frame_idx, (client, state) in enumerate(zip(clients, states, strict=True)):
        if (
            client.get("episode_id") != episode_id
            or client.get("server_tick") != frame_idx
            or client.get("render_frame_idx") != frame_idx
            or state.get("episode_id") != episode_id
            or state.get("server_tick") != frame_idx
            or state.get("layout_id") != layout_id
            or state.get("scene") != "NO_WALL"
            or state.get("geometric_visible") is not True
            or client.get("server_epoch_nanos") != state.get("server_epoch_nanos")
        ):
            _fail(f"Canonical source identity differs for {trajectory_id}:{frame_idx}.")
        position = state.get("axis_pos")
        if (
            isinstance(position, bool)
            or not isinstance(position, (int, float))
            or not math.isfinite(float(position))
        ):
            _fail(f"Canonical x_true_blocks is invalid for {trajectory_id}:{frame_idx}.")
        frame_descriptor = _source_descriptor(accepted, f"frames/{frame_idx:06d}.png")
        identity = {
            "action_idx": frame_idx,
            "episode_id": str(episode_id),
            "model_frame_idx": frame_idx,
            "render_frame_idx": frame_idx,
            "server_tick": frame_idx,
            "trajectory_id": trajectory_id,
        }
        client_hash = _sha256_bytes(_canonical_json_bytes(client))
        state_hash = _sha256_bytes(_canonical_json_bytes(state))
        frame_row = {
            **identity,
            "source_client_tick_row_sha256": client_hash,
            "source_frame_path": str(
                source_root
                / "episode"
                / "client"
                / "frames"
                / f"{frame_idx:06d}.png"
            ),
            "source_frame_sha256": frame_descriptor["sha256"],
            "source_server_epoch_nanos": client["server_epoch_nanos"],
        }
        state_row = {
            **identity,
            "source_server_state_row_sha256": state_hash,
            "state": {
                "position_x_blocks": float(state["sheep_x"]),
                "position_y_blocks": float(state["sheep_y"]),
                "position_z_blocks": float(state["sheep_z"]),
                "target_entity_id": f"canonical_sheep_{episode_id}",
                "target_present": True,
                "velocity_x_blocks_per_second": float(state["axis_velocity"]),
                "velocity_y_blocks_per_second": 0.0,
                "velocity_z_blocks_per_second": 0.0,
                "wall_parallel_position_blocks": float(position),
            },
        }
        frame_digest = _person_a_source_row_digest(frame_row)
        state_digest = _person_a_source_row_digest(state_row)
        activation_rows = sorted(rows_by_frame[frame_idx], key=lambda row: row["layer_idx"])
        if tuple(int(row["layer_idx"]) for row in activation_rows) != EXPECTED_LAYERS:
            _fail(f"Layer coverage differs for {trajectory_id}:{frame_idx}.")
        for row in activation_rows:
            expected = {
                "c_frame_map_row_sha256": frame_digest,
                "c_frame_map_sha256": client_descriptor["sha256"],
                "c_state_row_sha256": state_digest,
                "c_state_sha256": state_descriptor["sha256"],
                "global_model_frame_idx": frame_idx,
                "source_frame_id": f"{trajectory_id}:render_frame:{frame_idx}",
                "source_frame_idx": frame_idx,
                "source_tick": frame_idx,
                "trajectory_id": trajectory_id,
            }
            if any(row.get(key) != value for key, value in expected.items()):
                _fail(f"Activation/source join differs for {trajectory_id}:{frame_idx}.")
            matched += 1
        targets.append(float(position))
        metadata.append(
            {
                "layout_id": layout_id,
                "model_frame_idx": frame_idx,
                "status": "accepted",
                "trajectory_id": trajectory_id,
            }
        )
    if matched != ROWS_PER_TRAJECTORY or max(targets) - min(targets) <= 0.0:
        _fail(f"Source join or nonzero position range differs for {trajectory_id}.")
    return (
        {
            "accepted_manifest_sha256": str(run["accepted_manifest"]["sha256"]),
            "activation_index_byte_size": int(index_claim["byte_size"]),
            "activation_index_sha256": str(index_claim["sha256"]),
            "activation_rows_matched": matched,
            "chunk_count": len(chunk_receipt_rows),
            "chunk_inventory_sha256": _sha256_bytes(
                _canonical_json_bytes(chunk_receipt_rows)
            ),
            "episode_id": episode_id,
            "frame_count": FRAMES_PER_TRAJECTORY,
            "layout_id": layout_id,
            "maximum_x_true_blocks": max(targets),
            "minimum_x_true_blocks": min(targets),
            "output_bundle_root": str(root),
            "source_client_tick_sha256": str(client_descriptor["sha256"]),
            "source_identity_join_pass": True,
            "source_server_state_sha256": str(state_descriptor["sha256"]),
            "trajectory_id": trajectory_id,
        },
        targets,
        metadata,
    )


def _pearson(left: Any, right: Any) -> float:
    import numpy as np

    x = np.asarray(left, dtype=np.float64)
    y = np.asarray(right, dtype=np.float64)
    if x.size < 2 or float(x.std()) == 0.0 or float(y.std()) == 0.0:
        _fail("Pearson correlation is undefined for a frozen metric group.")
    value = float(np.corrcoef(x, y)[0, 1])
    if not math.isfinite(value):
        _fail("Pearson correlation is non-finite.")
    return value


def _metrics(actual: Any, predicted: Any) -> dict[str, Any]:
    import numpy as np

    truth = np.asarray(actual, dtype=np.float64)
    estimate = np.asarray(predicted, dtype=np.float64)
    residual = estimate - truth
    total = float(np.sum((truth - truth.mean()) ** 2))
    if total <= 0.0:
        _fail("R-squared is undefined for constant frozen truth.")
    return {
        "mae_blocks": float(np.mean(np.abs(residual))),
        "mse_blocks2": float(np.mean(residual * residual)),
        "pearson_r": _pearson(truth, estimate),
        "prediction_mean": float(estimate.mean()),
        "r2": 1.0 - float(np.sum(residual * residual)) / total,
        "row_count": int(truth.size),
        "target_max": float(truth.max()),
        "target_mean": float(truth.mean()),
        "target_min": float(truth.min()),
    }


def _run_real_label_control(
    features_by_layer: Mapping[int, Sequence[Sequence[float]]],
    targets: Sequence[float],
    folds: Sequence[int],
    layouts: Sequence[str],
) -> list[dict[str, Any]]:
    import numpy as np

    results: list[dict[str, Any]] = []
    truth = np.asarray(targets, dtype=np.float64)
    fold_vector = np.asarray(folds, dtype=np.int64)
    for layer_idx in EXPECTED_LAYERS:
        matrix = np.asarray(features_by_layer[layer_idx], dtype=np.float64)
        fitted = fit_ridge_oof(
            matrix,
            truth,
            folds,
            layouts,
            alpha_grid=ALPHA_GRID,
            inner_fold_count=INNER_FOLD_COUNT,
            seed=SPLIT_SEED,
        )
        predictions = np.asarray(fitted.predictions, dtype=np.float64)
        per_fold = []
        for fold_idx in range(OUTER_FOLD_COUNT):
            selected = fold_vector == fold_idx
            layout_values = sorted(set(np.asarray(layouts)[selected].tolist()))
            if len(layout_values) != 1:
                _fail("Each successor outer fold must contain exactly one layout.")
            per_fold.append(
                {
                    "fold_idx": fold_idx,
                    "layout_id": layout_values[0],
                    **_metrics(truth[selected], predictions[selected]),
                }
            )
        results.append(
            {
                "feature_matrix_sha256": _sha256_bytes(
                    matrix.astype("<f8", copy=False).tobytes(order="C")
                ),
                "fold_fits": [
                    {
                        "inner_fold_count": fit.alpha_selection.inner_fold_count,
                        "mean_mse_by_alpha": [
                            {"alpha": alpha, "mean_mse": loss}
                            for alpha, loss in sorted(
                                fit.alpha_selection.mean_mse_by_alpha.items()
                            )
                        ],
                        "outer_fold_idx": fit.outer_fold_idx,
                        "selected_alpha": fit.alpha_selection.selected_alpha,
                        "test_row_count": len(fit.test_indices),
                        "training_row_count": len(fit.training_indices),
                    }
                    for fit in fitted.fits
                ],
                "global": _metrics(truth, predictions),
                "hook_site": "decoder_layer_output_residual_stream",
                "layer_idx": layer_idx,
                "per_fold": per_fold,
            }
        )
    return results


def _review_real_metrics(results: Sequence[Mapping[str, Any]]) -> Mapping[str, Any] | None:
    qualified = []
    for row in results:
        global_metrics = row.get("global")
        fold_metrics = row.get("per_fold")
        if (
            isinstance(global_metrics, Mapping)
            and isinstance(fold_metrics, list)
            and len(fold_metrics) == OUTER_FOLD_COUNT
            and float(global_metrics.get("r2", -math.inf)) > 0.0
            and float(global_metrics.get("pearson_r", -math.inf)) > 0.0
            and all(
                isinstance(fold, Mapping)
                and float(fold.get("pearson_r", -math.inf)) > 0.0
                for fold in fold_metrics
            )
        ):
            qualified.append(row)
    if not qualified:
        return None
    return max(qualified, key=lambda row: (float(row["global"]["r2"]), -int(row["layer_idx"])))


def _load_completed_control_results(path: Path) -> Mapping[str, Any]:
    document = _load_object(path, "completed control results")
    frozen = document.get("frozen_configuration")
    execution = document.get("execution_semantics")
    real = document.get("real_label_positive_control")
    shuffled = document.get("shuffled_control")
    if (
        document.get("schema_version") != COMPLETED_RESULTS_SCHEMA
        or document.get("immutable") is not True
        or document.get("adaptive_rerun_performed") is not False
        or document.get("results_selected_for_preference") is not False
        or not isinstance(frozen, Mapping)
        or frozen.get("alpha_grid") != list(ALPHA_GRID)
        or frozen.get("outer_fold_count") != OUTER_FOLD_COUNT
        or frozen.get("inner_fold_count") != INNER_FOLD_COUNT
        or frozen.get("split_seed") != SPLIT_SEED
        or frozen.get("permutation_count") != PERMUTATION_COUNT
        or frozen.get("permutation_seed") != PERMUTATION_SEED
        or frozen.get("permutation_unit") != "whole_trajectory_block"
        or frozen.get("target_name") != "x_true_blocks"
        or not isinstance(execution, Mapping)
        or execution.get("real_label_execution_count") != 1
        or execution.get("shuffled_execution_count") != 1
        or not isinstance(real, Mapping)
        or real.get("complete") is not True
        or real.get("status") != "COMPLETE_FROZEN_LAYOUT_GROUPED_OOF"
        or not isinstance(shuffled, Mapping)
        or shuffled.get("complete") is not True
        or shuffled.get("status")
        != "COMPLETE_FROZEN_WHOLE_TRAJECTORY_GROUPED_SHUFFLE"
    ):
        _fail("Completed control result identity or execution semantics differ.")
    metrics = real.get("metrics")
    if (
        not isinstance(metrics, list)
        or len(metrics) != len(EXPECTED_LAYERS)
        or tuple(row.get("layer_idx") for row in metrics) != EXPECTED_LAYERS
    ):
        _fail("Completed real-label layer metrics are incomplete or reordered.")
    qualified = []
    for row in metrics:
        if not isinstance(row, Mapping):
            _fail("Completed real-label metric row is malformed.")
        numeric = [
            row.get("global_r2"),
            row.get("global_pearson_r"),
            row.get("minimum_fold_pearson_r"),
            row.get("maximum_fold_pearson_r"),
        ]
        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            for value in numeric
        ):
            _fail("Completed real-label metric contains a non-finite value.")
        alphas = row.get("selected_alphas_by_outer_fold")
        if (
            not isinstance(alphas, list)
            or len(alphas) != OUTER_FOLD_COUNT
            or any(float(alpha) not in ALPHA_GRID for alpha in alphas)
        ):
            _fail("Completed real-label selected alpha identities differ.")
        if (
            row.get("all_five_fold_correlations_positive") is True
            and float(row["global_r2"]) > 0.0
            and float(row["global_pearson_r"]) > 0.0
            and float(row["minimum_fold_pearson_r"]) > 0.0
        ):
            qualified.append(row)
    qualified_ids = [int(row["layer_idx"]) for row in qualified]
    if real.get("qualified_layer_indices") != qualified_ids or not qualified:
        _fail("Completed real-label frozen review decision differs.")
    strongest = max(
        qualified,
        key=lambda row: (float(row["global_r2"]), -int(row["layer_idx"])),
    )
    if real.get("strongest_reviewed_layer") != {
        "all_five_fold_correlations_positive": True,
        "global_pearson_r": strongest["global_pearson_r"],
        "global_r2": strongest["global_r2"],
        "layer_idx": strongest["layer_idx"],
        "maximum_fold_pearson_r": strongest["maximum_fold_pearson_r"],
        "minimum_fold_pearson_r": strongest["minimum_fold_pearson_r"],
    }:
        _fail("Completed strongest reviewed layer differs.")
    shuffled_metrics = shuffled.get("metrics")
    if (
        not isinstance(shuffled_metrics, Mapping)
        or shuffled_metrics.get("reviewed_layer_idx") != strongest["layer_idx"]
        or shuffled_metrics.get("observed_r2") != strongest["global_r2"]
        or shuffled_metrics.get("permutation_count") != PERMUTATION_COUNT
        or shuffled_metrics.get("permutation_seed") != PERMUTATION_SEED
        or shuffled_metrics.get("permutation_unit") != "whole_trajectory_block"
        or shuffled_metrics.get("p_value_rule") != "add_one_greater_or_equal"
        or shuffled_metrics.get("permutation_refit_policy")
        != "refit_scaler_alpha_and_ridge_inside_each_permutation"
    ):
        _fail("Completed grouped shuffled-control identities differ.")
    extreme = shuffled_metrics.get("extreme_null_count")
    p_value = shuffled_metrics.get("p_value")
    null_values = [
        shuffled_metrics.get("null_r2_minimum"),
        shuffled_metrics.get("null_r2_mean"),
        shuffled_metrics.get("null_r2_maximum"),
    ]
    if (
        not isinstance(extreme, int)
        or isinstance(extreme, bool)
        or not 0 <= extreme <= PERMUTATION_COUNT
        or p_value != (extreme + 1.0) / (PERMUTATION_COUNT + 1.0)
        or any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            for value in null_values
        )
        or not float(null_values[0]) <= float(null_values[1]) <= float(null_values[2])
    ):
        _fail("Completed grouped shuffled-control metrics are invalid.")
    return document


def _run_vectorized_grouped_permutations(
    features: Sequence[Sequence[float]],
    targets: Sequence[float],
    folds: Sequence[int],
    layouts: Sequence[str],
    trajectories: Sequence[str],
) -> dict[str, Any]:
    """Execute the same scaler/alpha/ridge refit for all frozen permutations.

    The linear solves use all permutation targets as multiple right-hand sides.
    This is algebraically identical to calling ``fit_ridge_oof`` 999 times;
    no fit, scaler, alpha choice, fold, seed, or target block is reused.
    """

    import numpy as np

    matrix = np.asarray(features, dtype=np.float64)
    truth = np.asarray(targets, dtype=np.float64)
    fold_vector = np.asarray(folds, dtype=np.int64)
    alpha_values = np.asarray(ALPHA_GRID, dtype=np.float64)
    shuffled = np.asarray(
        [
            permute_trajectory_blocks(
                trajectories,
                truth.tolist(),
                seed=PERMUTATION_SEED + permutation_index,
            )
            for permutation_index in range(PERMUTATION_COUNT)
        ],
        dtype=np.float64,
    )
    shuffled_predictions = np.full(shuffled.shape, np.nan, dtype=np.float64)
    selected_alpha_counts = {
        str(fold_idx): {str(alpha): 0 for alpha in ALPHA_GRID}
        for fold_idx in range(OUTER_FOLD_COUNT)
    }
    for outer_fold in range(OUTER_FOLD_COUNT):
        training = np.flatnonzero(fold_vector != outer_fold)
        test = np.flatnonzero(fold_vector == outer_fold)
        training_groups = [layouts[index] for index in training]
        inner_assignments = _group_fold_assignments(
            training_groups,
            n_splits=INNER_FOLD_COUNT,
            seed=SPLIT_SEED + outer_fold,
        )
        losses = np.zeros((PERMUTATION_COUNT, len(ALPHA_GRID)), dtype=np.float64)
        for validation_fold in range(INNER_FOLD_COUNT):
            inner_training = np.asarray(
                [
                    training[index]
                    for index, group in enumerate(training_groups)
                    if inner_assignments[group] != validation_fold
                ],
                dtype=np.int64,
            )
            validation = np.asarray(
                [
                    training[index]
                    for index, group in enumerate(training_groups)
                    if inner_assignments[group] == validation_fold
                ],
                dtype=np.int64,
            )
            mean = matrix[inner_training].mean(axis=0)
            scale = matrix[inner_training].std(axis=0, ddof=0)
            scale[scale == 0.0] = 1.0
            standardized_training = (matrix[inner_training] - mean) / scale
            standardized_validation = (matrix[validation] - mean) / scale
            gram = standardized_training @ standardized_training.T
            cross = standardized_validation @ standardized_training.T
            target_mean = shuffled[:, inner_training].mean(axis=1)
            centered = (
                shuffled[:, inner_training] - target_mean[:, np.newaxis]
            ).T
            for alpha_index, alpha in enumerate(alpha_values):
                coefficients = np.linalg.solve(
                    gram
                    + float(alpha)
                    * np.eye(len(inner_training), dtype=np.float64),
                    centered,
                )
                prediction = (cross @ coefficients).T + target_mean[:, np.newaxis]
                losses[:, alpha_index] += np.mean(
                    (prediction - shuffled[:, validation]) ** 2,
                    axis=1,
                )
        choices = np.argmin(losses / INNER_FOLD_COUNT, axis=1)
        mean = matrix[training].mean(axis=0)
        scale = matrix[training].std(axis=0, ddof=0)
        scale[scale == 0.0] = 1.0
        standardized_training = (matrix[training] - mean) / scale
        standardized_test = (matrix[test] - mean) / scale
        gram = standardized_training @ standardized_training.T
        cross = standardized_test @ standardized_training.T
        target_mean = shuffled[:, training].mean(axis=1)
        centered = (shuffled[:, training] - target_mean[:, np.newaxis]).T
        for alpha_index, alpha in enumerate(alpha_values):
            selected = np.flatnonzero(choices == alpha_index)
            selected_alpha_counts[str(outer_fold)][str(float(alpha))] = int(
                selected.size
            )
            if selected.size == 0:
                continue
            coefficients = np.linalg.solve(
                gram
                + float(alpha) * np.eye(len(training), dtype=np.float64),
                centered[:, selected],
            )
            shuffled_predictions[np.ix_(selected, test)] = (
                (cross @ coefficients).T + target_mean[selected, np.newaxis]
            )
    if not np.isfinite(shuffled_predictions).all():
        _fail("The grouped shuffled control did not predict every row.")
    denominator = np.sum(
        (shuffled - shuffled.mean(axis=1)[:, np.newaxis]) ** 2,
        axis=1,
    )
    null_r2 = 1.0 - np.sum(
        (shuffled - shuffled_predictions) ** 2,
        axis=1,
    ) / denominator
    if not np.isfinite(null_r2).all():
        _fail("The grouped shuffled-control distribution is non-finite.")
    observed = fit_ridge_oof(
        matrix,
        truth,
        folds,
        layouts,
        alpha_grid=ALPHA_GRID,
        inner_fold_count=INNER_FOLD_COUNT,
        seed=SPLIT_SEED,
    )
    observed_r2 = float(_metrics(truth, observed.predictions)["r2"])
    values = [float(value) for value in null_r2]
    p_value = permutation_p_value(observed_r2, values)
    return {
        "extreme_null_count": sum(value >= observed_r2 for value in values),
        "null_r2": values,
        "null_r2_maximum": max(values),
        "null_r2_mean": sum(values) / len(values),
        "null_r2_minimum": min(values),
        "observed_r2": observed_r2,
        "p_value": p_value,
        "p_value_rule": "add_one_greater_or_equal",
        "permutation_count": PERMUTATION_COUNT,
        "permutation_refit_policy": (
            "refit_scaler_alpha_and_ridge_inside_each_permutation"
        ),
        "permutation_seed": PERMUTATION_SEED,
        "permutation_seeds": list(
            range(PERMUTATION_SEED, PERMUTATION_SEED + PERMUTATION_COUNT)
        ),
        "permutation_unit": "whole_trajectory_block",
        "selected_alpha_counts_by_outer_fold": selected_alpha_counts,
        "vectorized_multiple_rhs_exact_ridge_execution": True,
    }


def build_receipt(
    *,
    repository: Path,
    person_a_repository: Path,
    collection_root: Path,
    completed_control_results_path: Path,
    execution_commit: str,
) -> dict[str, Any]:
    frozen_authorities = _verify_frozen_authorities(repository)
    manifest, handoff, external_inventory = _verify_collection(collection_root)
    completed = _load_completed_control_results(completed_control_results_path)
    targets: list[float] = []
    metadata: list[dict[str, Any]] = []
    trajectory_identities = []
    for run in manifest["runs"]:
        identity, run_targets, run_metadata = _verify_run(
            person_a_repository, run
        )
        trajectory_identities.append(identity)
        targets.extend(run_targets)
        metadata.extend(run_metadata)
    if (
        len(targets) != EXPECTED_FRAMES
        or len(metadata) != EXPECTED_FRAMES
        or sum(row["activation_rows_matched"] for row in trajectory_identities)
        != EXPECTED_ACTIVATION_ROWS
        or sum(row["chunk_count"] for row in trajectory_identities)
        != EXPECTED_CHUNK_COUNT
    ):
        _fail("Successor aggregate matrix or source-join cardinality differs.")
    assignments = assign_layout_grouped_folds(
        metadata,
        n_splits=OUTER_FOLD_COUNT,
        seed=SPLIT_SEED,
    )
    if set(assignments) != set(LAYOUTS) or set(assignments.values()) != set(range(5)):
        _fail("Frozen grouped-fold assignment does not yield five held-out layouts.")
    layouts = [row["layout_id"] for row in metadata]
    if Counter(layouts) != Counter({layout: FRAMES_PER_TRAJECTORY for layout in LAYOUTS}):
        _fail("Authenticated source rows differ from the completed fold population.")
    real = {"attempted": True, **dict(completed["real_label_positive_control"])}
    shuffled = {"attempted": True, **dict(completed["shuffled_control"])}
    strongest = real["strongest_reviewed_layer"]
    passed = strongest is not None and shuffled["complete"] is True
    blockers = [] if passed else ["FROZEN_REAL_LABEL_POSITIVE_CONTROL_FAILED"]
    activation_index_identities = [
        {
            "activation_index_byte_size": row["activation_index_byte_size"],
            "activation_index_sha256": row["activation_index_sha256"],
            "trajectory_id": row["trajectory_id"],
        }
        for row in trajectory_identities
    ]
    source_matched = sum(
        row["activation_rows_matched"] for row in trajectory_identities
    )
    return {
        "a_to_b_handoff": {
            "path": str(
                (
                    collection_root
                    / "person_a_to_person_b_canonical_multilayout_handoff.json"
                ).resolve()
            ),
            "sha256": A_TO_B_HANDOFF_SHA256,
            "valid": True,
        },
        "activation_chunk_count": EXPECTED_CHUNK_COUNT,
        "activation_index_count": EXPECTED_INDEX_COUNT,
        "activation_index_identities": activation_index_identities,
        "activation_row_count": EXPECTED_ACTIVATION_ROWS,
        "collection_manifest": {
            "path": str((collection_root / "collection_manifest.json").resolve()),
            "sha256": COLLECTION_MANIFEST_SHA256,
            "valid": True,
        },
        "completed_control_results": {
            "path": str(completed_control_results_path.resolve()),
            "sha256": _sha256_file(completed_control_results_path),
            "valid": True,
        },
        "decision": {
            "automatic_hidden_state_transition": False,
            "frozen_acceptance_rule": FROZEN_REVIEW_RULE,
            "positive_control_pass": passed,
            "status": (
                "PASS_FROZEN_CANONICAL_MULTILAYOUT_VISIBLE_POSITION_POSITIVE_CONTROL"
                if passed
                else "STOP_FOR_DIAGNOSIS_FROZEN_POSITIVE_CONTROL_FAILED"
            ),
        },
        "execution": {
            "branch": REQUIRED_BRANCH,
            "person_a_commit": PERSON_A_COMMIT,
            "person_b_execution_commit": execution_commit,
            "required_starting_ancestor": REQUIRED_STARTING_ANCESTOR,
            "receipt_generation_recomputed_scientific_control": False,
            "scientific_fit_performed": True,
            "scientific_execution_semantics": completed["execution_semantics"],
        },
        "external_activation_inventory": {
            "artifact_count": external_inventory.get("artifact_count"),
            "sha256": str(manifest["external_activation_inventory"]["sha256"]),
            "valid": True,
        },
        "fold_identities": {
            "assignment_implementation": (
                "mineocclude.probes.splits.assign_layout_grouped_folds"
            ),
            "grouping_key": "layout_id",
            "inner_fold_count": INNER_FOLD_COUNT,
            "inner_strategy": "layout_grouped",
            "layout_assignments": [
                {"fold_idx": assignments[layout], "layout_id": layout}
                for layout in sorted(assignments)
            ],
            "outer_fold_count": OUTER_FOLD_COUNT,
            "outer_split_seed": SPLIT_SEED,
            "outer_strategy": "layout_grouped",
        },
        "frozen_authorities": frozen_authorities,
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "immutable": True,
        "label_authority": {
            "frame_count_per_trajectory": FRAMES_PER_TRAJECTORY,
            "label_source": "canonical_server_state.axis_pos",
            "maximum_x_true_blocks": max(targets),
            "minimum_x_true_blocks": min(targets),
            "nonzero_position_range_per_trajectory": True,
            "target_name": "x_true_blocks",
            "target_unit": "blocks",
        },
        "layout_count": len(LAYOUTS),
        "real_label_positive_control": real,
        "remaining_blockers": blockers,
        "schema_version": RECEIPT_SCHEMA,
        "shuffled_control": shuffled,
        "source_identity_join": {
            "activation_rows_matched": source_matched,
            "frame_rows_matched": EXPECTED_FRAMES,
            "identity_error_count": 0,
            "pass": True,
            "trajectory_results": [
                {
                    "activation_rows_matched": row["activation_rows_matched"],
                    "frame_count": row["frame_count"],
                    "source_client_tick_sha256": row["source_client_tick_sha256"],
                    "source_server_state_sha256": row["source_server_state_sha256"],
                    "trajectory_id": row["trajectory_id"],
                }
                for row in trajectory_identities
            ],
        },
        "thresholds": {
            "numeric_pass_threshold_added": False,
            "policy": FROZEN_THRESHOLD_POLICY,
        },
        "trajectory_count": len(TRAJECTORIES),
        "trajectory_identities": trajectory_identities,
    }


def validate_receipt(document: Mapping[str, Any]) -> None:
    """Validate the successor receipt's frozen identities and completion."""

    decision = document.get("decision")
    real = document.get("real_label_positive_control")
    shuffled = document.get("shuffled_control")
    source_join = document.get("source_identity_join")
    collection = document.get("collection_manifest")
    handoff = document.get("a_to_b_handoff")
    completed = document.get("completed_control_results")
    if (
        document.get("schema_version") != RECEIPT_SCHEMA
        or document.get("immutable") is not True
        or document.get("layout_count") != len(LAYOUTS)
        or document.get("trajectory_count") != len(TRAJECTORIES)
        or document.get("activation_index_count") != EXPECTED_INDEX_COUNT
        or document.get("activation_row_count") != EXPECTED_ACTIVATION_ROWS
        or document.get("activation_chunk_count") != EXPECTED_CHUNK_COUNT
        or not isinstance(collection, Mapping)
        or collection.get("sha256") != COLLECTION_MANIFEST_SHA256
        or collection.get("valid") is not True
        or not isinstance(handoff, Mapping)
        or handoff.get("sha256") != A_TO_B_HANDOFF_SHA256
        or handoff.get("valid") is not True
        or not isinstance(completed, Mapping)
        or completed.get("valid") is not True
        or not isinstance(completed.get("sha256"), str)
        or len(completed["sha256"]) != 64
        or not isinstance(source_join, Mapping)
        or source_join.get("pass") is not True
        or source_join.get("activation_rows_matched") != EXPECTED_ACTIVATION_ROWS
        or source_join.get("frame_rows_matched") != EXPECTED_FRAMES
        or source_join.get("identity_error_count") != 0
        or not isinstance(real, Mapping)
        or real.get("complete") is not True
        or len(real.get("metrics", ())) != len(EXPECTED_LAYERS)
        or not isinstance(shuffled, Mapping)
        or not isinstance(decision, Mapping)
    ):
        _fail("Successor receipt identity, completion, or source join is invalid.")
    identities = document.get("trajectory_identities")
    indexes = document.get("activation_index_identities")
    folds = document.get("fold_identities")
    if (
        not isinstance(identities, list)
        or tuple(row.get("trajectory_id") for row in identities) != TRAJECTORIES
        or tuple(row.get("layout_id") for row in identities) != LAYOUTS
        or tuple(row.get("episode_id") for row in identities) != EPISODES
        or not isinstance(indexes, list)
        or tuple(row.get("trajectory_id") for row in indexes) != TRAJECTORIES
        or not isinstance(folds, Mapping)
        or folds.get("grouping_key") != "layout_id"
        or folds.get("outer_fold_count") != OUTER_FOLD_COUNT
        or folds.get("inner_fold_count") != INNER_FOLD_COUNT
        or sorted(row["fold_idx"] for row in folds.get("layout_assignments", ()))
        != list(range(OUTER_FOLD_COUNT))
    ):
        _fail("Successor receipt trajectory, index, or fold identities differ.")
    if decision.get("positive_control_pass") is True:
        metrics = shuffled.get("metrics")
        if (
            real.get("strongest_reviewed_layer") is None
            or shuffled.get("complete") is not True
            or not isinstance(metrics, Mapping)
            or metrics.get("permutation_count") != PERMUTATION_COUNT
            or metrics.get("permutation_seed") != PERMUTATION_SEED
            or document.get("remaining_blockers") != []
            or decision.get("status")
            != "PASS_FROZEN_CANONICAL_MULTILAYOUT_VISIBLE_POSITION_POSITIVE_CONTROL"
        ):
            _fail("Passing successor receipt lacks complete frozen control evidence.")
    elif (
        decision.get("status") != "STOP_FOR_DIAGNOSIS_FROZEN_POSITIVE_CONTROL_FAILED"
        or document.get("remaining_blockers") != [
            "FROZEN_REAL_LABEL_POSITIVE_CONTROL_FAILED"
        ]
    ):
        _fail("Failing successor receipt does not preserve the scientific blocker.")


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
    parser.add_argument("--person-a-repository", type=Path, required=True)
    parser.add_argument("--collection-root", type=Path, required=True)
    parser.add_argument("--completed-control-results", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    repository = args.repository_root.resolve()
    person_a_repository = args.person_a_repository.resolve()
    collection_root = args.collection_root.resolve()
    execution_commit = require_clean_repository(repository, person_a_repository)
    receipt = build_receipt(
        repository=repository,
        person_a_repository=person_a_repository,
        collection_root=collection_root,
        completed_control_results_path=args.completed_control_results.resolve(),
        execution_commit=execution_commit,
    )
    validate_receipt(receipt)
    output = args.output.resolve()
    _write_exclusive(output, receipt)
    print(
        json.dumps(
            {
                "positive_control_pass": receipt["decision"]["positive_control_pass"],
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
