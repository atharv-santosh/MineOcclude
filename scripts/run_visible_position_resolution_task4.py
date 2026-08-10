#!/usr/bin/env python3
"""Run Task 4 replicated visible-position ridge analyses.

The runner joins the frozen original and Task-3 layer-4 authorities, builds the
three development-frozen representations, and evaluates leakage-safe nested
ridge fits at the trajectory and layout levels.  Wide fits use the exact dual
ridge equations with float64, train-only standardization and cached sample-space
kernels.  No capture, extraction, control, or prior-authority mutation occurs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import resource
import statistics
import sys
import time
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.run_exploratory_visible_position_resolution import (  # noqa: E402
    ALPHA_GRID,
    ALPHA_SELECTION_SEED,
    HIDDEN_WIDTH,
    NMAE_STD_DEFINITION,
    TOKEN_COUNT,
    TOKEN_GRID_COLS,
    TOKEN_GRID_ROWS,
    _canonical_sha256,
    fold_metrics,
)

RUNNER_VERSION = "visible-position-resolution-task4-runner-v0.1"
BASE_HEAD = "626dcc00710f2b51cbbe2bfdea86785cb2d70e61"
OUTPUT_ROOT = (
    ROOT / "docs/status/integration/exploratory_visible_position_resolution_v0_1"
)
CACHE_ROOT = Path(
    "/mnt/sagemaker-nvme/mineocclude_task4_visible_position_resolution_v0_1"
)
DEVELOPMENT_FREEZE_EMBEDDED_SHA256 = (
    "3fc436f13b96e47b54e3837d37c0c4ecd20428a23a6c0fda58ee6c570040fc07"
)

FROZEN_FILE_HASHES = {
    "development_freeze.json": (
        "97e68c4981a781053baef4f33a64516208725627bd757e7ffc2eb572951856ce"
    ),
    "expanded_visibility_eligibility.json": (
        "1882ec400159f83e4d09dc7b113907857dca5ad5f7fbd90760ad296fb289d6ea"
    ),
    "metric_decomposition.json": (
        "8c6b193363b8d14f332f8656a1cad377b6dfe51cd7edef7bcf704a3843b4c55c"
    ),
    "replication_authority_decision.json": (
        "8c0d4f07329529ef00e185c9fb880a0f927a8da4d34ebcd4fcc1121fb1ac674a"
    ),
    "replication_inventory.json": (
        "8adc3196663a676047352fa073e97e8cbb6176b3620c3bc0e22f68a1325ef7e4"
    ),
    "runtime_benchmark.json": (
        "baf1bfe4a2405e33d6cb6c73f51a9bfe1d62d77d392c08afa63554ffdc0677a7"
    ),
    "six_layout_generalization.json": (
        "d8fa0beb7c0605694a14d09383c0991a358d21fea913eefaaca7e2504e63d0e4"
    ),
    "spatial_representation_ladder.json": (
        "fc4a6df133bbef2c52714e6ba3379d3632e9db1e259fed06639556e1a928a39c"
    ),
    "capture_manifest.json": (
        "44575ecf539b3d93f50a64d1ae1270ea48a0124753a5d69c1f76f117aea37218"
    ),
    "expanded_activation_manifest.json": (
        "59fc98f1d2d9569d8814140e29827ddf522553b5b207b2116b7f2cf8f6961871"
    ),
}
PREDECESSOR_MANIFEST = (
    ROOT
    / "docs/status/integration/exploratory_visible_position_diagnostics_v0_1"
    / "unpooled_activation_manifest.json"
)
PREDECESSOR_SHA256 = "d7e9615f26856d64c96a55b4d52624dc24d7df5841e3f930a238a7d1c3987482"
MVP_MANIFEST = (
    ROOT / "docs/status/person_c_c7_mvp_handoff_v0_1/trajectories_mvp_manifest.json"
)
MVP_SHA256 = "96ba43e15bc024aeaef7c519fa4ece0a4afe0bb0e877501dffaca44fee927ff7"

ORIGINAL_TRAJECTORIES = {
    "layout_01": "layout_01_ep12602",
    "layout_02": "layout_02_ep12610",
    "layout_03": "layout_03_ep12645",
    "layout_04": "layout_04_ep12626",
    "layout_05": "layout_05_ep12634",
    "layout_06": "layout_06_ep12616",
}
EXPECTED_ROWS_BY_LAYOUT = {
    "layout_01": 180,
    "layout_02": 180,
    "layout_03": 180,
    "layout_04": 180,
    "layout_05": 180,
    "layout_06": 171,
}
REPRESENTATIONS = {
    "GLOBAL_MEAN": {
        "region_rows": 1,
        "region_cols": 1,
        "feature_count": 2048,
    },
    "COARSE_2x6": {
        "region_rows": 2,
        "region_cols": 6,
        "feature_count": 24576,
    },
    "FULL_TOKEN_GRID": {
        "region_rows": 14,
        "region_cols": 24,
        "feature_count": 688128,
    },
}
OPTIMIZATION_EQUIVALENCE_ATOL = 1e-7
OPTIMIZATION_EQUIVALENCE_RTOL = 1e-7


class Task4Error(RuntimeError):
    """Raised when Task 4 authority or leakage constraints fail."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise Task4Error(message)


def sha256_file(path: Path, chunk_size: int = 8 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    document = json.loads(path.read_text(encoding="utf-8"))
    _require(isinstance(document, dict), f"not a JSON mapping: {path}")
    return document


def _jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def _write_json(path: Path, document: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(document, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


@dataclass(frozen=True)
class CombinedAuthority:
    rows: tuple[dict[str, Any], ...]
    chunks: tuple[dict[str, Any], ...]
    identity: dict[str, Any]


def _verify_frozen_files(root: Path) -> dict[str, dict[str, Any]]:
    base = root / "docs/status/integration/exploratory_visible_position_resolution_v0_1"
    records: dict[str, dict[str, Any]] = {}
    for name, expected in FROZEN_FILE_HASHES.items():
        path = base / name
        _require(path.is_file(), f"missing frozen Task 1-3 authority: {path}")
        observed = sha256_file(path)
        _require(observed == expected, f"frozen authority changed: {name}")
        records[name] = {"path": str(path.relative_to(root)), "sha256": observed}
    _require(
        sha256_file(PREDECESSOR_MANIFEST) == PREDECESSOR_SHA256,
        "predecessor activation manifest changed",
    )
    _require(sha256_file(MVP_MANIFEST) == MVP_SHA256, "frozen MVP changed")
    records["predecessor_unpooled_activation_manifest.json"] = {
        "path": str(PREDECESSOR_MANIFEST.relative_to(root)),
        "sha256": PREDECESSOR_SHA256,
    }
    records["trajectories_mvp_manifest.json"] = {
        "path": str(MVP_MANIFEST.relative_to(root)),
        "sha256": MVP_SHA256,
    }
    freeze = _load_json(base / "development_freeze.json")
    embedded = freeze.pop("development_freeze_sha256")
    _require(
        embedded == _canonical_sha256(freeze) == DEVELOPMENT_FREEZE_EMBEDDED_SHA256,
        "development-freeze embedded identity changed",
    )
    return records


def _verify_array_reference(
    reference: Mapping[str, Any], expected_shape: list[int]
) -> None:
    import numpy as np

    path = Path(str(reference["path"]))
    _require(path.is_file(), f"missing activation array: {path}")
    _require(path.stat().st_size == reference["byte_size"], f"size mismatch: {path}")
    _require(sha256_file(path) == reference["sha256"], f"hash mismatch: {path}")
    array = np.load(path, mmap_mode="r", allow_pickle=False)
    _require(list(array.shape) == expected_shape, f"shape mismatch: {path}")
    _require(str(array.dtype) == reference["dtype"], f"dtype mismatch: {path}")


def load_combined_authority(
    *, root: Path = ROOT, verify_activation_hashes: bool = True
) -> CombinedAuthority:
    """Validate and join the exact 18-trajectory, 1,071-row authority."""

    base = root / "docs/status/integration/exploratory_visible_position_resolution_v0_1"
    source_files = _verify_frozen_files(root)
    freeze = _load_json(base / "development_freeze.json")
    _require(
        freeze["representation_set"] == ["GLOBAL_MEAN", "COARSE_2x6", "FULL_TOKEN_GRID"]
        and freeze["layer_idx"] == 4
        and freeze["alpha_grid"] == list(ALPHA_GRID)
        and freeze["scaling"] == "training_rows_only",
        "frozen scientific design mismatch",
    )

    predecessor = _load_json(PREDECESSOR_MANIFEST)
    task3_capture = _load_json(base / "capture_manifest.json")
    task3_activation = _load_json(base / "expanded_activation_manifest.json")
    inventory = _load_json(base / "replication_inventory.json")
    old_eligibility = _load_json(base / "expanded_visibility_eligibility.json")

    _require(
        predecessor["status"] == "COMPLETE"
        and predecessor["scope"]["trajectory_count"] == 6
        and predecessor["scope"]["eligible_row_count"] == 351,
        "original activation authority is incomplete",
    )
    _require(
        task3_activation["status"] == "PASS"
        and task3_activation["scope"]["trajectory_count"] == 12
        and task3_activation["scope"]["eligible_row_count"] == 720,
        "Task 3 activation authority is incomplete",
    )
    _require(
        task3_capture["combined"]["total_new_accepted_trajectory_count"] == 12
        and task3_capture["combined"]["total_new_eligible_row_count"] == 720,
        "Task 3 capture accounting mismatch",
    )

    original_ids = set(ORIGINAL_TRAJECTORIES.values())
    inventory_by_id = {row["trajectory_id"]: row for row in inventory["trajectories"]}
    _require(original_ids <= set(inventory_by_id), "original trajectories missing")
    for trajectory_id in sorted(original_ids):
        record = inventory_by_id[trajectory_id]
        condition = record["condition_fields"]
        _require(
            record["capture_condition"] == "no_wall_visible"
            and record["visibility_regime"]["wall_present"] is False
            and condition["control_type"] == "no_wall_visible_control"
            and condition["set_id"] == "nowall"
            and condition["scene"] == "nowall"
            and condition["context_fraction"] == 0.0
            and condition["hidden_frames"] == 0
            and condition["speed_blocks_per_second"] == 1.0
            and condition["q_blocks_squared_per_second"] == 0.05,
            f"{trajectory_id}: original condition stratum mismatch",
        )

    attempts = {
        attempt["trajectory_id"]: attempt
        for round_name in ("round1", "round2")
        for attempt in task3_capture[round_name]["attempts"]
    }
    _require(len(attempts) == 12, "Task 3 trajectory IDs collide")
    for trajectory_id, attempt in attempts.items():
        reset = _load_json(Path(attempt["path_metadata"]["raw_config"]["path"]))
        _require(
            attempt["status"] == "ACCEPTED"
            and attempt["condition"] == "no_wall_visible"
            and attempt["control_type"] == "no_wall_visible_control"
            and attempt["set_id"] == "nowall"
            and attempt["scene"] == "NO_WALL"
            and attempt["capture_contract"]["no_wall_condition"] == "PASS"
            and reset["scene"] == "NO_WALL"
            and reset["v"] == 1.0
            and reset["q"] == 0.05
            and reset["reveal_ticks"] == 0,
            f"{trajectory_id}: Task 3 condition stratum mismatch",
        )

    old_context = predecessor["sequence_context"]
    new_contract = task3_activation["extraction_contract"]
    new_context = new_contract["context_semantics"]
    _require(
        old_context["all_source_frames_processed"] is True
        and new_context["all_source_frames_processed"] is True
        and old_context["policy"] == new_context["policy"]
        and old_context["teacher_forcing"] == new_context["teacher_forcing"] is True
        and old_context["window_size"] == new_context["window_size"] == 16,
        "context/window semantics differ",
    )
    _require(
        predecessor["scope"]["layer_idx"] == new_contract["layer"] == 4
        and predecessor["scope"]["visual_token_count"]
        == new_contract["token_count"]
        == TOKEN_COUNT
        and predecessor["scope"]["hidden_width"]
        == new_contract["hidden_width"]
        == HIDDEN_WIDTH
        and new_contract["token_grid"] == [TOKEN_GRID_ROWS, TOKEN_GRID_COLS],
        "layer/token/grid/width identity mismatch",
    )
    _require(
        predecessor["runtime_identity"]["checkpoint_sha256"]
        == task3_activation["checkpoint_identity"]["checkpoint_sha256"]
        and predecessor["runtime_identity"]["preprocess_hash"]
        == task3_activation["preprocessing_identity"]["preprocess_hash"]
        and predecessor["runtime_identity"]["preprocessing_identity"]
        == task3_activation["preprocessing_identity"]["identity"],
        "checkpoint/preprocessing identity mismatch",
    )

    old_eligible_rows = old_eligibility["eligible_row_identities"]
    old_eligible_keys = {
        row["row_key"]
        for row in old_eligible_rows
        if row["trajectory_id"] in original_ids
    }
    _require(
        len(old_eligible_keys) == 351,
        "Task 1 original eligibility is not the exact 351-row authority",
    )
    new_eligible_keys = set(task3_activation["row_keys"])
    _require(len(new_eligible_keys) == 720, "Task 3 row keys are not unique")
    _require(not (old_eligible_keys & new_eligible_keys), "old/new row collision")

    chunks: list[dict[str, Any]] = []
    combined_rows: list[dict[str, Any]] = []
    raw_chunks: list[tuple[str, Mapping[str, Any]]] = [
        ("original", chunk) for chunk in predecessor["chunks"]
    ] + [(f"round{chunk['round']}", chunk) for chunk in task3_activation["chunks"]]

    for source, raw_chunk in raw_chunks:
        chunk = dict(raw_chunk)
        trajectory_id = str(chunk["trajectory_id"])
        layout_id = str(chunk["layout_id"])
        layout_label = "L" + layout_id.removeprefix("layout_")
        rows_path = Path(chunk["rows"]["path"])
        _require(rows_path.is_file(), f"missing row authority: {rows_path}")
        _require(
            rows_path.stat().st_size == chunk["rows"]["byte_size"]
            and sha256_file(rows_path) == chunk["rows"]["sha256"],
            f"row authority identity mismatch: {rows_path}",
        )
        source_rows = _jsonl(rows_path)
        row_count = int(chunk["eligible_row_count"])
        _require(
            len(source_rows) == chunk["rows"]["row_count"] == row_count,
            f"{trajectory_id}: activation row count mismatch",
        )
        if verify_activation_hashes:
            _verify_array_reference(
                chunk["token_array"], [row_count, TOKEN_COUNT, HIDDEN_WIDTH]
            )
            _verify_array_reference(chunk["pooled_array"], [row_count, HIDDEN_WIDTH])
        else:
            _require(
                Path(chunk["token_array"]["path"]).is_file()
                and Path(chunk["pooled_array"]["path"]).is_file(),
                f"{trajectory_id}: activation files missing",
            )

        start = len(combined_rows)
        for source_row_index, raw_row in enumerate(source_rows):
            row = dict(raw_row)
            expected_key = f"{trajectory_id}:{row['model_frame_idx']}"
            _require(row["row_key"] == expected_key, f"{expected_key}: key schema")
            _require(
                row["trajectory_id"] == trajectory_id
                and row["layout_id"] == layout_id
                and row["layer_idx"] == 4
                and row["visual_token_count"] == TOKEN_COUNT
                and row["hidden_width"] == HIDDEN_WIDTH
                and row["target_id"] == expected_key + ":regime_a_primary_v1"
                and math.isfinite(float(row["x_true_blocks"])),
                f"{expected_key}: row scientific identity mismatch",
            )
            combined_rows.append(
                {
                    "layout_id": layout_id,
                    "layout_label": layout_label,
                    "model_frame_idx": int(row["model_frame_idx"]),
                    "row_key": expected_key,
                    "source": source,
                    "source_row_index": source_row_index,
                    "target_id": row["target_id"],
                    "trajectory_id": trajectory_id,
                    "x_true_blocks": float(row["x_true_blocks"]),
                }
            )
        stop = len(combined_rows)
        chunks.append(
            {
                "eligible_row_count": row_count,
                "layout_id": layout_id,
                "layout_label": layout_label,
                "pooled_array": dict(chunk["pooled_array"]),
                "row_start": start,
                "row_stop_exclusive": stop,
                "rows": dict(chunk["rows"]),
                "source": source,
                "token_array": dict(chunk["token_array"]),
                "trajectory_id": trajectory_id,
            }
        )

    trajectory_ids = [chunk["trajectory_id"] for chunk in chunks]
    row_keys = [row["row_key"] for row in combined_rows]
    _require(
        len(chunks) == len(set(trajectory_ids)) == 18,
        "combined authority does not contain 18 unique trajectories",
    )
    _require(
        len(combined_rows) == len(set(row_keys)) == 1071,
        "combined authority does not contain 1,071 unique rows",
    )
    _require(
        Counter(chunk["layout_id"] for chunk in chunks)
        == Counter({layout: 3 for layout in EXPECTED_ROWS_BY_LAYOUT}),
        "combined authority is not three trajectories per layout",
    )
    _require(
        Counter(row["layout_id"] for row in combined_rows)
        == Counter(EXPECTED_ROWS_BY_LAYOUT),
        "combined per-layout row counts differ from manifest-derived counts",
    )
    _require(
        {row["row_key"] for row in combined_rows}
        == old_eligible_keys | new_eligible_keys,
        "combined activation and eligibility row authorities differ",
    )
    for chunk in chunks:
        indices = [
            row["model_frame_idx"]
            for row in combined_rows[chunk["row_start"] : chunk["row_stop_exclusive"]]
        ]
        _require(indices == sorted(set(indices)), f"{chunk['trajectory_id']}: rows")

    identity_basis = [
        {
            "layout_id": row["layout_id"],
            "model_frame_idx": row["model_frame_idx"],
            "row_key": row["row_key"],
            "source": row["source"],
            "target_id": row["target_id"],
            "trajectory_id": row["trajectory_id"],
            "x_true_blocks": row["x_true_blocks"],
        }
        for row in combined_rows
    ]
    identity = {
        "status": "PASS",
        "source_authorities": source_files,
        "combined_authority_sha256": _canonical_sha256(identity_basis),
        "row_keys_sha256": _canonical_sha256(row_keys),
        "trajectory_ids_sha256": _canonical_sha256(trajectory_ids),
        "trajectory_count": 18,
        "eligible_row_count": 1071,
        "trajectory_count_by_layout": {layout: 3 for layout in EXPECTED_ROWS_BY_LAYOUT},
        "eligible_rows_by_layout": dict(EXPECTED_ROWS_BY_LAYOUT),
        "trajectory_ids_by_layout": {
            layout: [
                chunk["trajectory_id"]
                for chunk in chunks
                if chunk["layout_id"] == layout
            ]
            for layout in EXPECTED_ROWS_BY_LAYOUT
        },
        "condition_identity": {
            "capture_condition": "no_wall_visible",
            "control_type": "no_wall_visible_control",
            "scene": "NO_WALL/nowall normalized identity",
            "set_id": "nowall",
            "wall_present": False,
            "context_fraction": 0.0,
            "hidden_frames": 0,
            "speed_blocks_per_second": 1.0,
            "q_blocks_squared_per_second": 0.05,
            "status": "PASS",
        },
        "checkpoint_sha256": task3_activation["checkpoint_identity"][
            "checkpoint_sha256"
        ],
        "preprocess_hash": task3_activation["preprocessing_identity"][
            "preprocess_hash"
        ],
        "preprocessing_identity": task3_activation["preprocessing_identity"][
            "identity"
        ],
        "context_semantics": dict(new_context),
        "target_semantics": {
            "field": "x_true_blocks",
            "target_id_suffix": "regime_a_primary_v1",
            "status": "PASS",
        },
        "visibility_semantics": {
            "original": "Task-1 frozen fully-visible eligible rows",
            "round1_and_round2": "Task-3 frozen strict-visible eligible rows",
            "status": "PASS",
        },
        "activation_identity": {
            "layer": 4,
            "layer_count": 1,
            "token_count": TOKEN_COUNT,
            "token_grid": [TOKEN_GRID_ROWS, TOKEN_GRID_COLS],
            "hidden_width": HIDDEN_WIDTH,
            "token_dtype": "float16",
            "status": "PASS",
        },
        "row_key_schema": "{trajectory_id}:{model_frame_idx}",
        "duplicate_row_count": 0,
        "trajectory_collision_count": 0,
        "missing_activation_file_count": 0,
        "wall_condition_trajectory_count": 0,
    }
    return CombinedAuthority(tuple(combined_rows), tuple(chunks), identity)


def _cache_source_identity(authority: CombinedAuthority) -> str:
    return _canonical_sha256(
        {
            "combined_authority_sha256": authority.identity[
                "combined_authority_sha256"
            ],
            "chunks": [
                {
                    "path": chunk["token_array"]["path"],
                    "sha256": chunk["token_array"]["sha256"],
                }
                for chunk in authority.chunks
            ],
            "representations": REPRESENTATIONS,
        }
    )


def build_feature_caches(
    authority: CombinedAuthority, *, cache_root: Path = CACHE_ROOT
) -> dict[str, Any]:
    """Build exact float32 frozen representations once outside Git."""

    import numpy as np

    feature_root = cache_root / "features"
    feature_root.mkdir(parents=True, exist_ok=True)
    metadata_path = feature_root / "feature_cache_metadata.json"
    source_identity = _cache_source_identity(authority)
    paths = {name: feature_root / f"{name.lower()}.f32.npy" for name in REPRESENTATIONS}
    if metadata_path.is_file():
        prior = _load_json(metadata_path)
        valid = prior.get("source_identity_sha256") == source_identity
        for name, definition in REPRESENTATIONS.items():
            path = paths[name]
            valid = valid and path.is_file()
            if valid:
                array = np.load(path, mmap_mode="r", allow_pickle=False)
                valid = (
                    list(array.shape)
                    == [len(authority.rows), definition["feature_count"]]
                    and array.dtype == np.float32
                    and path.stat().st_size == prior["caches"][name]["byte_size"]
                    and sha256_file(path) == prior["caches"][name]["sha256"]
                )
        if valid:
            return {**prior, "cache_reused": True}

    started = time.perf_counter()
    arrays = {
        name: np.lib.format.open_memmap(
            path,
            mode="w+",
            dtype=np.float32,
            shape=(len(authority.rows), definition["feature_count"]),
        )
        for name, (path, definition) in {
            key: (paths[key], value) for key, value in REPRESENTATIONS.items()
        }.items()
    }
    max_pooling_difference = 0.0
    for ordinal, chunk in enumerate(authority.chunks, start=1):
        source = np.load(chunk["token_array"]["path"], mmap_mode="r")
        pooled = np.load(chunk["pooled_array"]["path"], mmap_mode="r")
        start = int(chunk["row_start"])
        for local_start in range(0, source.shape[0], 8):
            local_stop = min(local_start + 8, source.shape[0])
            destination = slice(start + local_start, start + local_stop)
            block = np.asarray(source[local_start:local_stop], dtype=np.float32)
            count = local_stop - local_start
            global_features = (
                block.reshape(count, 1, 14, 1, 24, HIDDEN_WIDTH)
                .mean(axis=(2, 4))
                .reshape(count, HIDDEN_WIDTH)
            )
            coarse_features = (
                block.reshape(count, 2, 7, 6, 4, HIDDEN_WIDTH)
                .mean(axis=(2, 4))
                .reshape(count, 12 * HIDDEN_WIDTH)
            )
            arrays["GLOBAL_MEAN"][destination] = global_features
            arrays["COARSE_2x6"][destination] = coarse_features
            arrays["FULL_TOKEN_GRID"][destination] = block.reshape(count, -1)
            difference = float(
                np.max(
                    np.abs(
                        global_features
                        - np.asarray(pooled[local_start:local_stop], dtype=np.float32)
                    )
                )
            )
            max_pooling_difference = max(max_pooling_difference, difference)
        print(
            f"feature-cache {ordinal:02d}/{len(authority.chunks)} "
            f"{chunk['trajectory_id']}",
            flush=True,
        )
    _require(
        max_pooling_difference <= 1e-6,
        "combined GLOBAL pooling differs from stored pooled activation authority",
    )
    for array in arrays.values():
        array.flush()
    del arrays
    records = {}
    for name, path in paths.items():
        records[name] = {
            "byte_size": path.stat().st_size,
            "dtype": "float32",
            "feature_count": REPRESENTATIONS[name]["feature_count"],
            "path": str(path),
            "sha256": sha256_file(path),
            "shape": [len(authority.rows), REPRESENTATIONS[name]["feature_count"]],
        }
    metadata = {
        "schema_version": "1.0",
        "artifact_id": "visible-position-task4-feature-cache-v0.1",
        "source_identity_sha256": source_identity,
        "cache_build_seconds": time.perf_counter() - started,
        "cache_reused": False,
        "caches": records,
        "global_pooling_max_abs_difference": max_pooling_difference,
        "global_pooling_tolerance": 1e-6,
        "global_pooling_equivalence": "PASS",
        "large_tensors_in_git": False,
    }
    _write_json(metadata_path, metadata)
    return metadata


def within_layout_folds(
    rows: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], ...]:
    """Construct the exact 6 x 3 trajectory outer folds."""

    by_layout: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(list))
    for index, row in enumerate(rows):
        by_layout[str(row["layout_id"])][str(row["trajectory_id"])].append(index)
    _require(len(by_layout) == 6, "within analysis requires six layouts")
    folds = []
    for layout_id in sorted(by_layout):
        trajectories = by_layout[layout_id]
        _require(len(trajectories) == 3, f"{layout_id}: expected three trajectories")
        universe = sorted(
            index for indices in trajectories.values() for index in indices
        )
        for held_out in sorted(trajectories):
            training = sorted(set(trajectories) - {held_out})
            train_index = sorted(
                index
                for trajectory_id in training
                for index in trajectories[trajectory_id]
            )
            test_index = sorted(trajectories[held_out])
            inner_folds = [
                {
                    "training_trajectory_ids": [training[1 - inner]],
                    "validation_trajectory_ids": [training[inner]],
                    "train_index": list(trajectories[training[1 - inner]]),
                    "validation_index": list(trajectories[training[inner]]),
                }
                for inner in range(2)
            ]
            _require(
                not (set(train_index) & set(test_index)),
                f"{held_out}: outer row leakage",
            )
            folds.append(
                {
                    "analysis": "WITHIN_LAYOUT_ACROSS_TRAJECTORY",
                    "fold_id": f"within:{layout_id}:{held_out}",
                    "held_out_layout": layout_id,
                    "held_out_trajectory": held_out,
                    "inner_folds": inner_folds,
                    "test_index": test_index,
                    "train_index": train_index,
                    "training_group_ids": training,
                    "universe_index": universe,
                }
            )
    _require(len(folds) == 18, "within analysis requires exactly 18 outer folds")
    return tuple(folds)


def across_layout_folds(
    rows: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], ...]:
    """Construct six complete held-out-layout outer folds."""

    by_layout: dict[str, list[int]] = defaultdict(list)
    for index, row in enumerate(rows):
        by_layout[str(row["layout_id"])].append(index)
    _require(len(by_layout) == 6, "across analysis requires six layouts")
    universe = list(range(len(rows)))
    folds = []
    for held_out in sorted(by_layout):
        training = sorted(set(by_layout) - {held_out})
        train_index = sorted(
            index for layout in training for index in by_layout[layout]
        )
        test_index = sorted(by_layout[held_out])
        inner_folds = []
        for validation_layout in training:
            inner_training = sorted(set(training) - {validation_layout})
            inner_folds.append(
                {
                    "training_layout_ids": inner_training,
                    "validation_layout_ids": [validation_layout],
                    "train_index": sorted(
                        index
                        for layout in inner_training
                        for index in by_layout[layout]
                    ),
                    "validation_index": list(by_layout[validation_layout]),
                }
            )
        _require(
            not (set(train_index) & set(test_index)),
            f"{held_out}: outer layout rows leaked",
        )
        folds.append(
            {
                "analysis": "ACROSS_LAYOUT_REPLICATED_GENERALIZATION",
                "fold_id": f"across:{held_out}",
                "held_out_layout": held_out,
                "held_out_trajectories": sorted(
                    {str(rows[index]["trajectory_id"]) for index in test_index}
                ),
                "inner_folds": inner_folds,
                "test_index": test_index,
                "train_index": train_index,
                "training_group_ids": training,
                "universe_index": universe,
            }
        )
    _require(len(folds) == 6, "across analysis requires exactly six outer folds")
    return tuple(folds)


@dataclass
class KernelContext:
    train_index: tuple[int, ...]
    scope_index: tuple[int, ...]
    kernel: Any
    timings: dict[str, float]
    scaler_training_row_count: int
    constant_feature_count: int
    target_values: Any
    predictions_by_alpha: dict[float, Any]
    solve_seconds_by_alpha: dict[float, float]

    def predictions(self, alpha: float, requested_indices: Sequence[int]) -> Any:
        import numpy as np

        if alpha not in self.predictions_by_alpha:
            started = time.perf_counter()
            target_mean = float(self.target_values.mean())
            centered = self.target_values - target_mean
            train_count = len(self.train_index)
            system = self.kernel[:train_count] + alpha * np.eye(
                train_count, dtype=np.float64
            )
            dual = np.linalg.solve(system, centered)
            self.predictions_by_alpha[alpha] = self.kernel @ dual + target_mean
            self.solve_seconds_by_alpha[alpha] = time.perf_counter() - started
        positions = {index: position for position, index in enumerate(self.scope_index)}
        _require(
            all(index in positions for index in requested_indices),
            "prediction requested outside standardized context scope",
        )
        return self.predictions_by_alpha[alpha][
            [positions[index] for index in requested_indices]
        ]


class ExactDualRidgeEngine:
    """Exact float64 train-scaled dual ridge with reusable Gram contexts."""

    def __init__(self, features: Any, targets: Any, representation: str):
        import torch

        _require(torch.cuda.is_available(), "Task 4 exact FULL fitting requires CUDA")
        self.features = features
        self.targets = targets
        self.representation = representation
        self.device = torch.device("cuda:0")
        self.contexts: dict[tuple[int, ...], KernelContext] = {}
        self.context_build_count = 0
        self.context_cache_hit_count = 0
        self.counters = Counter()
        torch.backends.cuda.matmul.allow_tf32 = False

    def snapshot(self) -> dict[str, float]:
        return {key: float(value) for key, value in self.counters.items()}

    def _load_matrix(self, indices: Sequence[int]) -> Any:
        import numpy as np
        import torch

        feature_count = int(self.features.shape[1])
        matrix = torch.empty(
            (len(indices), feature_count), dtype=torch.float64, device=self.device
        )
        batch_size = 8 if feature_count >= 100_000 else 64
        for start in range(0, len(indices), batch_size):
            stop = min(start + batch_size, len(indices))
            host = np.asarray(
                self.features[list(indices[start:stop])], dtype=np.float32, order="C"
            )
            matrix[start:stop].copy_(
                torch.as_tensor(host, device=self.device, dtype=torch.float64)
            )
        return matrix

    def context(
        self, train_index: Sequence[int], universe_index: Sequence[int]
    ) -> tuple[KernelContext, bool]:
        import numpy as np
        import torch

        training = tuple(sorted(int(index) for index in train_index))
        _require(len(training) == len(set(training)), "duplicate training row")
        if training in self.contexts:
            self.context_cache_hit_count += 1
            return self.contexts[training], True
        universe = tuple(sorted(set(int(index) for index in universe_index)))
        _require(set(training) <= set(universe), "training rows outside context scope")
        scope = training + tuple(
            index for index in universe if index not in set(training)
        )
        torch.cuda.synchronize()
        load_start = time.perf_counter()
        matrix = self._load_matrix(scope)
        torch.cuda.synchronize()
        load_seconds = time.perf_counter() - load_start

        train_count = len(training)
        scale_start = time.perf_counter()
        mean = matrix[:train_count].mean(dim=0)
        matrix.sub_(mean)
        scale = torch.linalg.vector_norm(matrix[:train_count], dim=0) / math.sqrt(
            train_count
        )
        constant = scale == 0.0
        constant_count = int(constant.sum().item())
        scale[constant] = 1.0
        matrix.div_(scale)
        torch.cuda.synchronize()
        scaling_seconds = time.perf_counter() - scale_start

        kernel_start = time.perf_counter()
        kernel_device = matrix @ matrix[:train_count].T
        kernel = np.asarray(kernel_device.cpu().numpy(), dtype=np.float64)
        torch.cuda.synchronize()
        kernel_seconds = time.perf_counter() - kernel_start
        del kernel_device, matrix, mean, scale, constant
        torch.cuda.empty_cache()

        context = KernelContext(
            train_index=training,
            scope_index=scope,
            kernel=kernel,
            timings={
                "load": load_seconds,
                "scaling": scaling_seconds,
                "kernel": kernel_seconds,
            },
            scaler_training_row_count=train_count,
            constant_feature_count=constant_count,
            target_values=np.asarray(self.targets[list(training)], dtype=np.float64),
            predictions_by_alpha={},
            solve_seconds_by_alpha={},
        )
        self.contexts[training] = context
        self.context_build_count += 1
        self.counters.update(context.timings)
        print(
            f"{self.representation} context {self.context_build_count:02d}: "
            f"train={train_count} scope={len(scope)} load={load_seconds:.3f}s "
            f"scale={scaling_seconds:.3f}s kernel={kernel_seconds:.3f}s",
            flush=True,
        )
        return context, False

    def predict(
        self,
        train_index: Sequence[int],
        predict_index: Sequence[int],
        universe_index: Sequence[int],
        alpha: float,
    ) -> tuple[Any, dict[str, Any]]:
        context, cache_hit = self.context(train_index, universe_index)
        prior = context.solve_seconds_by_alpha.get(alpha)
        prediction = context.predictions(alpha, predict_index)
        if prior is None:
            self.counters["solve"] += context.solve_seconds_by_alpha[alpha]
        return prediction, {
            "cache_hit": cache_hit,
            "constant_feature_count": context.constant_feature_count,
            "context_scope_row_count": len(context.scope_index),
            "scaler_training_row_count": context.scaler_training_row_count,
        }


def _counter_delta(
    after: Mapping[str, float], before: Mapping[str, float]
) -> dict[str, float]:
    return {
        key: float(after.get(key, 0.0) - before.get(key, 0.0))
        for key in sorted(set(after) | set(before))
    }


def fit_outer_fold(
    engine: ExactDualRidgeEngine,
    targets: Any,
    rows: Sequence[Mapping[str, Any]],
    fold: Mapping[str, Any],
) -> dict[str, Any]:
    """Run frozen grouped alpha selection and one untouched outer evaluation."""

    import numpy as np
    import torch

    # The qualified MineWorld Torch build accepts only its current-device form
    # for these helpers; newer releases also accept a ``torch.device`` object.
    torch.cuda.reset_peak_memory_stats()
    before = engine.snapshot()
    started = time.perf_counter()
    losses: dict[float, list[float]] = {float(alpha): [] for alpha in ALPHA_GRID}
    inner_records = []
    inner_start = time.perf_counter()
    for inner_ordinal, inner in enumerate(fold["inner_folds"]):
        validation_index = inner["validation_index"]
        inner_record = {
            "inner_fold": inner_ordinal,
            "train_row_count": len(inner["train_index"]),
            "validation_row_count": len(validation_index),
            "training_group_ids": inner.get(
                "training_trajectory_ids", inner.get("training_layout_ids")
            ),
            "validation_group_ids": inner.get(
                "validation_trajectory_ids", inner.get("validation_layout_ids")
            ),
            "scaler_fit_scope": "inner_training_rows_only",
            "validation_mse_by_alpha": {},
        }
        context_audit = None
        for alpha in ALPHA_GRID:
            predictions, audit = engine.predict(
                inner["train_index"],
                validation_index,
                fold["universe_index"],
                float(alpha),
            )
            mse = float(
                np.mean(
                    (
                        predictions
                        - np.asarray(targets[validation_index], dtype=np.float64)
                    )
                    ** 2
                )
            )
            losses[float(alpha)].append(mse)
            inner_record["validation_mse_by_alpha"][str(float(alpha))] = mse
            context_audit = audit
        inner_record["scaler_training_row_count"] = context_audit[
            "scaler_training_row_count"
        ]
        _require(
            inner_record["scaler_training_row_count"] == len(inner["train_index"]),
            f"{fold['fold_id']}: inner scaler leakage",
        )
        inner_records.append(inner_record)
    mean_mse = {
        alpha: float(sum(values) / len(values)) for alpha, values in losses.items()
    }
    selected_alpha = min(mean_mse, key=lambda alpha: (mean_mse[alpha], alpha))
    inner_seconds = time.perf_counter() - inner_start

    final_start = time.perf_counter()
    predictions, outer_audit = engine.predict(
        fold["train_index"],
        fold["test_index"],
        fold["universe_index"],
        selected_alpha,
    )
    final_seconds = time.perf_counter() - final_start
    _require(
        outer_audit["scaler_training_row_count"] == len(fold["train_index"]),
        f"{fold['fold_id']}: outer scaler leakage",
    )
    actual = np.asarray(targets[fold["test_index"]], dtype=np.float64)
    metrics = fold_metrics(actual, predictions)
    after = engine.snapshot()
    runtime = _counter_delta(after, before)
    runtime.update(
        {
            "inner_alpha_selection_total": inner_seconds,
            "final_fit_predict_total": final_seconds,
            "total": time.perf_counter() - started,
            "peak_gpu_allocated_bytes": int(torch.cuda.max_memory_allocated()),
            "peak_gpu_reserved_bytes": int(torch.cuda.max_memory_reserved()),
            "peak_host_rss_bytes": int(
                resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
            ),
        }
    )
    prediction_rows = [
        {
            "model_frame_idx": int(rows[index]["model_frame_idx"]),
            "prediction": float(prediction),
            "row_key": rows[index]["row_key"],
            "trajectory_id": rows[index]["trajectory_id"],
            "truth": float(targets[index]),
        }
        for index, prediction in zip(fold["test_index"], predictions, strict=True)
    ]
    return {
        "fold_id": fold["fold_id"],
        "held_out_layout": fold["held_out_layout"],
        "held_out_trajectories": fold.get(
            "held_out_trajectories", [fold.get("held_out_trajectory")]
        ),
        "training_group_ids": list(fold["training_group_ids"]),
        "train_row_count": len(fold["train_index"]),
        "test_row_count": len(fold["test_index"]),
        "feature_count": int(engine.features.shape[1]),
        "alpha_grid": [float(alpha) for alpha in ALPHA_GRID],
        "selected_alpha": selected_alpha,
        "alpha_selection_grouping": (
            "training_trajectory"
            if fold["analysis"] == "WITHIN_LAYOUT_ACROSS_TRAJECTORY"
            else "training_layout"
        ),
        "validation_mse_by_alpha": {
            str(alpha): value for alpha, value in mean_mse.items()
        },
        "inner_folds": inner_records,
        "outer_scaler_fit_scope": "outer_training_rows_only",
        "outer_scaler_training_row_count": outer_audit["scaler_training_row_count"],
        "metrics": metrics,
        "predictions": prediction_rows,
        "runtime_seconds": runtime,
    }


def _reference_fit(
    features: Any,
    targets: Any,
    rows: Sequence[Mapping[str, Any]],
    fold: Mapping[str, Any],
) -> tuple[float, Any]:
    """Use the repository implementation for optimization equivalence checks."""

    import numpy as np

    from mineocclude.probes.ridge import (
        fit_ridge,
        fit_standard_scaler,
        select_ridge_alpha_grouped,
    )

    train_index = fold["train_index"]
    test_index = fold["test_index"]
    train_groups = [
        str(
            rows[index][
                (
                    "trajectory_id"
                    if fold["analysis"] == "WITHIN_LAYOUT_ACROSS_TRAJECTORY"
                    else "layout_id"
                )
            ]
        )
        for index in train_index
    ]
    train_features = np.asarray(features[train_index], dtype=np.float64)
    test_features = np.asarray(features[test_index], dtype=np.float64)
    selection = select_ridge_alpha_grouped(
        train_features,
        targets[train_index],
        train_groups,
        alpha_grid=ALPHA_GRID,
        n_splits=len(set(train_groups)),
        seed=ALPHA_SELECTION_SEED,
    )
    scaler = fit_standard_scaler(train_features)
    model = fit_ridge(
        train_features,
        targets[train_index],
        alpha=selection.selected_alpha,
        scaler=scaler,
    )
    return selection.selected_alpha, np.asarray(model.predict(test_features))


def validate_optimization_equivalence(
    feature_arrays: Mapping[str, Any],
    targets: Any,
    rows: Sequence[Mapping[str, Any]],
    within_fold: Mapping[str, Any],
    across_fold: Mapping[str, Any],
    optimized_within_full: Mapping[str, Any],
    optimized_across_coarse: Mapping[str, Any],
) -> dict[str, Any]:
    """Reject the optimization if representative predictions diverge."""

    import numpy as np

    checks = []
    for name, fold, optimized in (
        (
            "representative_within_full",
            within_fold,
            optimized_within_full,
        ),
        (
            "representative_across_coarse",
            across_fold,
            optimized_across_coarse,
        ),
    ):
        representation = "FULL_TOKEN_GRID" if name.endswith("full") else "COARSE_2x6"
        started = time.perf_counter()
        alpha, reference_predictions = _reference_fit(
            feature_arrays[representation], targets, rows, fold
        )
        optimized_predictions = np.asarray(
            [row["prediction"] for row in optimized["predictions"]], dtype=np.float64
        )
        maximum = float(np.max(np.abs(reference_predictions - optimized_predictions)))
        passed = bool(
            alpha == optimized["selected_alpha"]
            and np.allclose(
                reference_predictions,
                optimized_predictions,
                atol=OPTIMIZATION_EQUIVALENCE_ATOL,
                rtol=OPTIMIZATION_EQUIVALENCE_RTOL,
            )
        )
        _require(passed, f"{name}: optimized predictions changed")
        checks.append(
            {
                "check": name,
                "feature_count": REPRESENTATIONS[representation]["feature_count"],
                "maximum_absolute_prediction_difference": maximum,
                "optimized_selected_alpha": optimized["selected_alpha"],
                "reference_selected_alpha": alpha,
                "runtime_seconds": time.perf_counter() - started,
                "status": "PASS",
            }
        )
    return {
        "method": (
            "float64 dual ridge with identical train-only population standardization; "
            "reuse changes computation scheduling only"
        ),
        "atol": OPTIMIZATION_EQUIVALENCE_ATOL,
        "rtol": OPTIMIZATION_EQUIVALENCE_RTOL,
        "checks": checks,
        "status": "PASS",
    }


def _dispersion(values: Sequence[float | None]) -> dict[str, Any]:
    present = [float(value) for value in values if value is not None]
    if not present:
        return {
            "count": 0,
            "population_std": None,
            "range": None,
            "median_absolute_deviation": None,
        }
    median = statistics.median(present)
    return {
        "count": len(present),
        "population_std": float(statistics.pstdev(present)),
        "range": float(max(present) - min(present)),
        "minimum": float(min(present)),
        "maximum": float(max(present)),
        "median_absolute_deviation": float(
            statistics.median(abs(value - median) for value in present)
        ),
    }


def _mean(values: Sequence[float | None]) -> float | None:
    present = [float(value) for value in values if value is not None]
    return None if not present else float(sum(present) / len(present))


def _median(values: Sequence[float | None]) -> float | None:
    present = [float(value) for value in values if value is not None]
    return None if not present else float(statistics.median(present))


def _pooled_prediction_metrics(folds: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    import numpy as np

    predictions = [
        prediction["prediction"] for fold in folds for prediction in fold["predictions"]
    ]
    truth = [
        prediction["truth"] for fold in folds for prediction in fold["predictions"]
    ]
    return {
        "scope": "SECONDARY_ONLY",
        **fold_metrics(np.asarray(truth), np.asarray(predictions)),
    }


def add_representation_deltas(results: Mapping[str, Sequence[dict[str, Any]]]) -> None:
    baseline = {fold["fold_id"]: fold for fold in results["GLOBAL_MEAN"]}
    for representation, folds in results.items():
        for fold in folds:
            reference = baseline[fold["fold_id"]]
            r2 = fold["metrics"]["r2"]
            baseline_r2 = reference["metrics"]["r2"]
            fold["representation_minus_global"] = {
                "delta_r2": (
                    None if r2 is None or baseline_r2 is None else r2 - baseline_r2
                ),
                "delta_mae": fold["metrics"]["mae"] - reference["metrics"]["mae"],
                "representation": representation,
            }


def summarize_within(
    results: Mapping[str, Sequence[Mapping[str, Any]]],
) -> dict[str, Any]:
    summaries = {}
    for representation, folds in results.items():
        by_layout: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
        for fold in folds:
            by_layout[str(fold["held_out_layout"])].append(fold)
        per_layout = {}
        for layout, layout_folds in sorted(by_layout.items()):
            r2_values = [fold["metrics"]["r2"] for fold in layout_folds]
            deltas = [
                fold["representation_minus_global"]["delta_r2"] for fold in layout_folds
            ]
            mae_deltas = [
                fold["representation_minus_global"]["delta_mae"]
                for fold in layout_folds
            ]
            positive = sum(value is not None and value > 0.0 for value in deltas)
            negative = sum(value is not None and value < 0.0 for value in deltas)
            per_layout[layout] = {
                "trajectory_mean_r2": _mean(r2_values),
                "trajectory_median_r2": _median(r2_values),
                "trajectory_r2_dispersion": _dispersion(r2_values),
                "trajectory_mean_mae": _mean(
                    [fold["metrics"]["mae"] for fold in layout_folds]
                ),
                "trajectory_mean_nmae_std": _mean(
                    [fold["metrics"]["nmae_std"] for fold in layout_folds]
                ),
                "delta_r2_values": deltas,
                "delta_r2_dispersion": _dispersion(deltas),
                "delta_r2_median": _median(deltas),
                "delta_mae_values": mae_deltas,
                "delta_mae_dispersion": _dispersion(mae_deltas),
                "delta_mae_median": _median(mae_deltas),
                "delta_sign_count": {
                    "positive": positive,
                    "negative": negative,
                    "zero": len(deltas) - positive - negative,
                },
                "major_sign_instability": positive > 0 and negative > 0,
            }
        all_r2 = [fold["metrics"]["r2"] for fold in folds]
        all_deltas = [fold["representation_minus_global"]["delta_r2"] for fold in folds]
        all_mae_deltas = [
            fold["representation_minus_global"]["delta_mae"] for fold in folds
        ]
        summaries[representation] = {
            "per_layout": per_layout,
            "equal_layout_macro_mean_r2": _mean(
                [value["trajectory_mean_r2"] for value in per_layout.values()]
            ),
            "equal_layout_macro_median_r2": _median(
                [value["trajectory_median_r2"] for value in per_layout.values()]
            ),
            "median_trajectory_r2": _median(all_r2),
            "trajectory_level_r2_dispersion": _dispersion(all_r2),
            "trajectory_level_delta_r2_dispersion": _dispersion(all_deltas),
            "trajectory_level_delta_mae_dispersion": _dispersion(all_mae_deltas),
            "layout_level_r2_dispersion": _dispersion(
                [value["trajectory_mean_r2"] for value in per_layout.values()]
            ),
            "trajectories_beating_global": sum(
                value is not None and value > 0.0 for value in all_deltas
            ),
            "layouts_with_positive_median_delta": sum(
                value["delta_r2_median"] is not None and value["delta_r2_median"] > 0.0
                for value in per_layout.values()
            ),
            "pooled_row_metrics": _pooled_prediction_metrics(folds),
        }
    return summaries


def _layout_macro_trajectory_metrics(
    trajectory_metrics: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    fields = (
        "r2",
        "mae",
        "nmae_std",
        "pearson_r",
        "prediction_slope",
        "prediction_bias",
    )
    return {
        field: {
            "mean": _mean([record[field] for record in trajectory_metrics.values()]),
            "median": _median(
                [record[field] for record in trajectory_metrics.values()]
            ),
        }
        for field in fields
    }


def add_across_trajectory_metrics(
    results: Mapping[str, Sequence[dict[str, Any]]],
) -> None:
    import numpy as np

    baseline = {fold["fold_id"]: fold for fold in results["GLOBAL_MEAN"]}
    for representation, folds in results.items():
        for fold in folds:
            by_trajectory: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
            for prediction in fold["predictions"]:
                by_trajectory[prediction["trajectory_id"]].append(prediction)
            trajectory_metrics = {
                trajectory_id: fold_metrics(
                    np.asarray([row["truth"] for row in prediction_rows]),
                    np.asarray([row["prediction"] for row in prediction_rows]),
                )
                for trajectory_id, prediction_rows in sorted(by_trajectory.items())
            }
            fold["per_trajectory_metrics"] = trajectory_metrics
            fold["layout_macro_trajectory_metrics"] = _layout_macro_trajectory_metrics(
                trajectory_metrics
            )
            reference = baseline[fold["fold_id"]]
            fold["representation_minus_global"] = {
                "delta_r2": (
                    None
                    if fold["metrics"]["r2"] is None
                    or reference["metrics"]["r2"] is None
                    else fold["metrics"]["r2"] - reference["metrics"]["r2"]
                ),
                "delta_mae": fold["metrics"]["mae"] - reference["metrics"]["mae"],
                "per_trajectory_delta_r2": {
                    trajectory_id: (
                        None
                        if metrics["r2"] is None
                        or reference["per_trajectory_metrics"][trajectory_id]["r2"]
                        is None
                        else metrics["r2"]
                        - reference["per_trajectory_metrics"][trajectory_id]["r2"]
                    )
                    for trajectory_id, metrics in trajectory_metrics.items()
                },
                "representation": representation,
            }


def summarize_across(
    results: Mapping[str, Sequence[Mapping[str, Any]]],
) -> dict[str, Any]:
    summaries = {}
    metric_fields = (
        "r2",
        "mae",
        "nmae_std",
        "pearson_r",
        "prediction_slope",
        "prediction_bias",
    )
    for representation, folds in results.items():
        summaries[representation] = {
            "per_layout_r2": {
                fold["held_out_layout"]: fold["metrics"]["r2"] for fold in folds
            },
            "equal_layout_macro_metrics": {
                field: {
                    "mean": _mean([fold["metrics"][field] for fold in folds]),
                    "median": _median([fold["metrics"][field] for fold in folds]),
                    "dispersion": _dispersion(
                        [fold["metrics"][field] for fold in folds]
                    ),
                }
                for field in metric_fields
            },
            "layout_macro_trajectory_metrics": {
                field: {
                    "equal_layout_mean_of_trajectory_means": _mean(
                        [
                            fold["layout_macro_trajectory_metrics"][field]["mean"]
                            for fold in folds
                        ]
                    ),
                    "equal_layout_median_of_trajectory_medians": _median(
                        [
                            fold["layout_macro_trajectory_metrics"][field]["median"]
                            for fold in folds
                        ]
                    ),
                }
                for field in metric_fields
            },
            "per_layout_delta_r2": {
                fold["held_out_layout"]: fold["representation_minus_global"]["delta_r2"]
                for fold in folds
            },
            "per_layout_delta_mae": {
                fold["held_out_layout"]: fold["representation_minus_global"][
                    "delta_mae"
                ]
                for fold in folds
            },
            "layouts_beating_global": sum(
                fold["representation_minus_global"]["delta_r2"] is not None
                and fold["representation_minus_global"]["delta_r2"] > 0.0
                for fold in folds
            ),
            "pooled_row_metrics": _pooled_prediction_metrics(folds),
        }
    return summaries


def hierarchical_comparison(
    within_summary: Mapping[str, Any], across_summary: Mapping[str, Any]
) -> dict[str, Any]:
    """Apply the predeclared descriptive trajectory/layout evidence logic."""

    representation_records = {}
    direction_stable_layouts_intersection = set(EXPECTED_ROWS_BY_LAYOUT)
    layouts_with_any_reversal = set()
    layouts_with_strong_magnitude_heterogeneity = set()
    for representation in ("COARSE_2x6", "FULL_TOKEN_GRID"):
        per_layout = within_summary[representation]["per_layout"]
        medians = [record["delta_r2_median"] for record in per_layout.values()]
        reversals = {
            layout
            for layout, record in per_layout.items()
            if record["major_sign_instability"]
        }
        stable = set(per_layout) - reversals
        direction_stable_layouts_intersection &= stable
        layouts_with_any_reversal |= reversals
        within_spreads = [
            record["delta_r2_dispersion"]["population_std"]
            for record in per_layout.values()
        ]
        within_mae_spreads = [
            record["delta_mae_dispersion"]["population_std"]
            for record in per_layout.values()
        ]
        across_r2_deltas = list(
            across_summary[representation]["per_layout_delta_r2"].values()
        )
        across_mae_deltas = list(
            across_summary[representation]["per_layout_delta_mae"].values()
        )
        across_r2_spread = _dispersion(across_r2_deltas)
        across_mae_spread = _dispersion(across_mae_deltas)
        strong_magnitude = {
            layout
            for layout, record in per_layout.items()
            if record["delta_r2_dispersion"]["population_std"]
            >= across_r2_spread["population_std"]
            and record["delta_mae_dispersion"]["population_std"]
            >= across_mae_spread["population_std"]
        }
        layouts_with_strong_magnitude_heterogeneity |= strong_magnitude
        across_r2_signs = {
            "positive": sum(
                value is not None and value > 0 for value in across_r2_deltas
            ),
            "negative": sum(
                value is not None and value < 0 for value in across_r2_deltas
            ),
            "zero": sum(value == 0 for value in across_r2_deltas),
        }
        across_mae_signs = {
            "improved": sum(
                value is not None and value < 0 for value in across_mae_deltas
            ),
            "worse": sum(
                value is not None and value > 0 for value in across_mae_deltas
            ),
            "zero": sum(value == 0 for value in across_mae_deltas),
        }
        representation_records[representation] = {
            "within_layout_trajectory_spread": {
                "per_layout_population_std": {
                    layout: record["delta_r2_dispersion"]["population_std"]
                    for layout, record in per_layout.items()
                },
                "equal_layout_mean_population_std": _mean(within_spreads),
                "equal_layout_mean_delta_mae_population_std": _mean(within_mae_spreads),
                "layouts_with_sign_reversal": sorted(reversals),
                "layouts_with_complementary_strong_magnitude_heterogeneity": sorted(
                    strong_magnitude
                ),
                "sign_stable_layouts": sorted(stable),
            },
            "between_layout_spread_of_layout_median_delta": _dispersion(medians),
            "across_layout_delta_spread": {
                "r2": across_r2_spread,
                "mae": across_mae_spread,
            },
            "across_layout_delta_sign_count": {
                "r2": across_r2_signs,
                "mae": across_mae_signs,
            },
            "within_layout_sign_consistency": {
                layout: record["delta_sign_count"]
                for layout, record in per_layout.items()
            },
            "between_layout_median_sign_count": {
                "positive": sum(value is not None and value > 0 for value in medians),
                "negative": sum(value is not None and value < 0 for value in medians),
                "zero": sum(value == 0 for value in medians),
            },
        }

    heterogeneous_trajectory_layouts = (
        layouts_with_any_reversal | layouts_with_strong_magnitude_heterogeneity
    )
    if not heterogeneous_trajectory_layouts:
        trajectory_class = "TRAJECTORY_VARIANCE_LOW"
    elif len(heterogeneous_trajectory_layouts) == len(EXPECTED_ROWS_BY_LAYOUT):
        trajectory_class = "TRAJECTORY_VARIANCE_DOMINANT"
    else:
        trajectory_class = "MIXED_TRAJECTORY_EFFECT"
    trajectory_dominant = trajectory_class == "TRAJECTORY_VARIANCE_DOMINANT"

    layout_sign_heterogeneity = any(
        record["across_layout_delta_sign_count"]["r2"]["positive"] > 0
        and record["across_layout_delta_sign_count"]["r2"]["negative"] > 0
        and record["across_layout_delta_sign_count"]["mae"]["improved"] > 0
        and record["across_layout_delta_sign_count"]["mae"]["worse"] > 0
        for record in representation_records.values()
    )
    substantial_trajectory = bool(heterogeneous_trajectory_layouts)
    substantial_layout = layout_sign_heterogeneity
    both = substantial_trajectory and substantial_layout
    layout_dominant = (
        not substantial_trajectory
        and substantial_layout
        and all(
            record["between_layout_spread_of_layout_median_delta"]["population_std"]
            >= record["within_layout_trajectory_spread"][
                "equal_layout_mean_population_std"
            ]
            for record in representation_records.values()
        )
    )
    if both:
        layout_class = "BOTH_TRAJECTORY_AND_LAYOUT_VARIANCE"
    elif layout_dominant:
        layout_class = "LAYOUT_VARIANCE_DOMINANT"
    elif trajectory_dominant:
        layout_class = "TRAJECTORY_VARIANCE_DOMINANT"
    elif substantial_layout:
        layout_class = "LAYOUT_HETEROGENEITY_WITH_MIXED_TRAJECTORY_EFFECT"
    else:
        layout_class = "NEITHER_CLEARLY_DOMINANT"

    layout_specific_plausible = bool(
        substantial_layout and len(direction_stable_layouts_intersection) >= 4
    )
    broad = {}
    for representation in ("COARSE_2x6", "FULL_TOKEN_GRID"):
        within = within_summary[representation]
        across = across_summary[representation]
        broad[representation] = {
            "within_positive_trajectory_majority": within["trajectories_beating_global"]
            > 9,
            "within_positive_layout_median_majority": within[
                "layouts_with_positive_median_delta"
            ]
            > 3,
            "across_positive_layout_majority": across["layouts_beating_global"] > 3,
            "across_positive_macro_r2_delta": (
                across["equal_layout_macro_metrics"]["r2"]["mean"]
                > across_summary["GLOBAL_MEAN"]["equal_layout_macro_metrics"]["r2"][
                    "mean"
                ]
            ),
        }
    token_generalizes_boolean = all(all(record.values()) for record in broad.values())
    within_broadly_positive = all(
        record["within_positive_trajectory_majority"]
        and record["within_positive_layout_median_majority"]
        for record in broad.values()
    )
    across_macro_positive = all(
        record["across_positive_macro_r2_delta"] for record in broad.values()
    )
    token_generalizes: bool | str
    if token_generalizes_boolean:
        token_generalizes = True
    elif within_broadly_positive and across_macro_positive:
        token_generalizes = "UNCLEAR"
    else:
        token_generalizes = False
    return {
        "predeclared_descriptive_logic": {
            "trajectory_variance_low": (
                "no within-layout sign reversal and no layout whose complementary "
                "R2-and-MAE within spread reaches held-out-layout spread"
            ),
            "trajectory_variance_dominant": (
                "every layout has a sign reversal or complementary R2-and-MAE "
                "within spread at least as large as held-out-layout spread"
            ),
            "mixed_trajectory_effect": (
                "some, but not all, layouts have a sign reversal or complementary "
                "within-layout magnitude heterogeneity"
            ),
            "layout_variance_dominant": (
                "no substantial within-layout heterogeneity, held-out-layout R2 and "
                "MAE delta signs differ, and between-layout spread is at least "
                "within-layout spread"
            ),
            "both": (
                "at least one within-layout reversal/strong complementary magnitude "
                "effect and differing R2-and-MAE signs across held-out layouts"
            ),
            "token_preserving_generalizes": (
                "both COARSE and FULL have strict-majority positive trajectory and "
                "layout effects within layout, strict-majority positive held-out "
                "layout effects, and positive across-layout macro R2 delta"
            ),
        },
        "representations": representation_records,
        "coarse_vs_full_stability": {
            "layouts_direction_stable_for_both": sorted(
                direction_stable_layouts_intersection
            ),
            "layouts_with_any_within_sign_reversal": sorted(layouts_with_any_reversal),
            "layouts_with_complementary_strong_magnitude_heterogeneity": sorted(
                layouts_with_strong_magnitude_heterogeneity
            ),
        },
        "trajectory_variance_class": trajectory_class,
        "trajectory_variance_dominant": trajectory_dominant,
        "layout_variance_class": layout_class,
        "layout_variance_dominant": layout_dominant,
        "both_trajectory_and_layout_variance": both,
        "layout_specific_representation_plausible": layout_specific_plausible,
        "token_preserving_broad_evidence": broad,
        "token_preserving_readout_generalizes": token_generalizes,
    }


def _public_fold(fold: Mapping[str, Any]) -> dict[str, Any]:
    return dict(fold)


def run_task4(
    *,
    root: Path = ROOT,
    output_root: Path,
    cache_root: Path = CACHE_ROOT,
    verify_activation_hashes: bool = True,
) -> tuple[Path, Path]:
    import numpy as np

    overall_start = time.perf_counter()
    authority = load_combined_authority(
        root=root, verify_activation_hashes=verify_activation_hashes
    )
    print(
        "combined-authority PASS: 18 trajectories, 1071 rows, 3/layout",
        flush=True,
    )
    cache = build_feature_caches(authority, cache_root=cache_root)
    arrays = {
        name: np.load(record["path"], mmap_mode="r", allow_pickle=False)
        for name, record in cache["caches"].items()
    }
    targets = np.asarray(
        [row["x_true_blocks"] for row in authority.rows], dtype=np.float64
    )
    within_folds = within_layout_folds(authority.rows)
    across_folds = across_layout_folds(authority.rows)

    within_results: dict[str, list[dict[str, Any]]] = {
        name: [] for name in REPRESENTATIONS
    }
    across_results: dict[str, list[dict[str, Any]]] = {
        name: [] for name in REPRESENTATIONS
    }
    engines = {
        name: ExactDualRidgeEngine(arrays[name], targets, name)
        for name in REPRESENTATIONS
    }

    # Required preflight benchmarks run before the remaining FULL matrix.
    benchmark_within_fold = next(
        fold
        for fold in within_folds
        if fold["held_out_layout"] == "layout_01"
        and fold["held_out_trajectory"] == ORIGINAL_TRAJECTORIES["layout_01"]
    )
    benchmark_across_fold = next(
        fold for fold in across_folds if fold["held_out_layout"] == "layout_01"
    )
    print("benchmark FULL within-layout outer fit", flush=True)
    within_benchmark_result = fit_outer_fold(
        engines["FULL_TOKEN_GRID"],
        targets,
        authority.rows,
        benchmark_within_fold,
    )
    print("benchmark FULL across-layout outer fit", flush=True)
    across_benchmark_result = fit_outer_fold(
        engines["FULL_TOKEN_GRID"],
        targets,
        authority.rows,
        benchmark_across_fold,
    )

    for representation in REPRESENTATIONS:
        engine = engines[representation]
        print(f"evaluate {representation}: within-layout folds", flush=True)
        for ordinal, fold in enumerate(within_folds, start=1):
            if (
                representation == "FULL_TOKEN_GRID"
                and fold["fold_id"] == within_benchmark_result["fold_id"]
            ):
                result = within_benchmark_result
            else:
                result = fit_outer_fold(engine, targets, authority.rows, fold)
            within_results[representation].append(result)
            print(
                f"{representation} within {ordinal:02d}/18 {fold['fold_id']}",
                flush=True,
            )
        print(f"evaluate {representation}: across-layout folds", flush=True)
        for ordinal, fold in enumerate(across_folds, start=1):
            if (
                representation == "FULL_TOKEN_GRID"
                and fold["fold_id"] == across_benchmark_result["fold_id"]
            ):
                result = across_benchmark_result
            else:
                result = fit_outer_fold(engine, targets, authority.rows, fold)
            across_results[representation].append(result)
            print(
                f"{representation} across {ordinal:02d}/6 {fold['fold_id']}",
                flush=True,
            )

    add_representation_deltas(within_results)
    add_across_trajectory_metrics(across_results)
    within_summary = summarize_within(within_results)
    across_summary = summarize_across(across_results)
    equivalence = validate_optimization_equivalence(
        arrays,
        targets,
        authority.rows,
        benchmark_within_fold,
        benchmark_across_fold,
        within_benchmark_result,
        next(
            fold
            for fold in across_results["COARSE_2x6"]
            if fold["fold_id"] == benchmark_across_fold["fold_id"]
        ),
    )
    hierarchy = hierarchical_comparison(within_summary, across_summary)

    representation_definitions = {
        name: {
            **definition,
            "dtype": "float32",
            "flattening": "region x hidden, row-block-major region order",
            "pooling": "float32 mean over frozen token partition",
            "token_grid": [TOKEN_GRID_ROWS, TOKEN_GRID_COLS],
        }
        for name, definition in REPRESENTATIONS.items()
    }
    nested_semantics = {
        "alpha_grid": [float(alpha) for alpha in ALPHA_GRID],
        "alpha_selection_loss": (
            "unweighted arithmetic mean of validation-group MSE values"
        ),
        "alpha_tie_break": "lowest numeric alpha",
        "inner_scaler": "fit on inner-training rows only",
        "outer_scaler": "fit on all outer-training rows only after alpha selection",
        "standardization": "per-feature population mean/std; constant scale set to 1",
        "ridge_intercept": "unpenalized training-target mean",
        "optimization": (
            "exact float64 sample-space ridge with standardized Gram reuse"
        ),
    }
    limitations = [
        "Layer 4 remains EXPLORATORY_PRESELECTED_FROM_EXISTING_POSITIVE_CONTROL.",
        "These analyses are exploratory independent no-wall replication, not confirmatory.",
        "No spatial-scramble, target-null, U1, U2, pair-holdout, or condition-shift control was run.",
        "Descriptive hierarchy is reported without a fabricated formal variance-component model.",
        "Pooled-row metrics are secondary; trajectory and equal-layout macros are primary.",
    ]
    runtime = {
        "total_task4_seconds": time.perf_counter() - overall_start,
        "feature_cache": cache,
        "engines": {
            name: {
                "context_build_count": engine.context_build_count,
                "context_cache_hit_count": engine.context_cache_hit_count,
                "cumulative_seconds": engine.snapshot(),
            }
            for name, engine in engines.items()
        },
        "peak_host_rss_bytes": int(
            resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
        ),
    }
    within_benchmark = {
        "fold_id": within_benchmark_result["fold_id"],
        "row_counts": {
            "train": within_benchmark_result["train_row_count"],
            "test": within_benchmark_result["test_row_count"],
        },
        "feature_count": within_benchmark_result["feature_count"],
        "load_seconds": within_benchmark_result["runtime_seconds"].get("load", 0.0),
        "scaling_seconds": within_benchmark_result["runtime_seconds"].get(
            "scaling", 0.0
        ),
        "inner_alpha_selection_seconds": within_benchmark_result["runtime_seconds"][
            "inner_alpha_selection_total"
        ],
        "final_fit_predict_seconds": within_benchmark_result["runtime_seconds"][
            "final_fit_predict_total"
        ],
        "kernel_seconds": within_benchmark_result["runtime_seconds"].get("kernel", 0.0),
        "total_runtime_seconds": within_benchmark_result["runtime_seconds"]["total"],
        "peak_gpu_allocated_bytes": within_benchmark_result["runtime_seconds"][
            "peak_gpu_allocated_bytes"
        ],
        "peak_host_rss_bytes": within_benchmark_result["runtime_seconds"][
            "peak_host_rss_bytes"
        ],
    }
    across_benchmark = {
        "fold_id": across_benchmark_result["fold_id"],
        "row_counts": {
            "train": across_benchmark_result["train_row_count"],
            "test": across_benchmark_result["test_row_count"],
        },
        "feature_count": across_benchmark_result["feature_count"],
        "load_seconds": across_benchmark_result["runtime_seconds"].get("load", 0.0),
        "scaling_seconds": across_benchmark_result["runtime_seconds"].get(
            "scaling", 0.0
        ),
        "inner_alpha_selection_seconds": across_benchmark_result["runtime_seconds"][
            "inner_alpha_selection_total"
        ],
        "final_fit_predict_seconds": across_benchmark_result["runtime_seconds"][
            "final_fit_predict_total"
        ],
        "kernel_seconds": across_benchmark_result["runtime_seconds"].get("kernel", 0.0),
        "total_runtime_seconds": across_benchmark_result["runtime_seconds"]["total"],
        "peak_gpu_allocated_bytes": across_benchmark_result["runtime_seconds"][
            "peak_gpu_allocated_bytes"
        ],
        "peak_host_rss_bytes": across_benchmark_result["runtime_seconds"][
            "peak_host_rss_bytes"
        ],
    }

    generated_at = _utc_now()
    within_document = {
        "schema_version": "1.0",
        "artifact_id": "visible-position-resolution-within-layout-replication-v0.1",
        "status": "PASS",
        "generated_at": generated_at,
        "base_head": BASE_HEAD,
        "runner": {
            "path": "scripts/run_visible_position_resolution_task4.py",
            "sha256": sha256_file(Path(__file__)),
            "version": RUNNER_VERSION,
        },
        "layer_selection_status": (
            "EXPLORATORY_PRESELECTED_FROM_EXISTING_POSITIVE_CONTROL"
        ),
        "combined_authority": authority.identity,
        "representation_definitions": representation_definitions,
        "outer_design": {
            "outer_fold_count": 18,
            "expected_outer_fold_count": 18,
            "outer_group": "trajectory",
            "per_layout_outer_fold_count": 3,
            "test": "one complete trajectory",
            "train": "the other two trajectories from the same layout",
            "leakage_audit": "PASS",
        },
        "nested_scaling_and_alpha_selection": {
            **nested_semantics,
            "inner_group": "training_trajectory",
            "inner_fold_count_per_outer": 2,
            "inner_design": "leave-one-training-trajectory-out",
        },
        "nmae_std_definition": NMAE_STD_DEFINITION,
        "representations": {
            name: {
                "folds": [_public_fold(fold) for fold in folds],
                "summary": within_summary[name],
            }
            for name, folds in within_results.items()
        },
        "hierarchical_within_layout": hierarchy["representations"],
        "trajectory_replication_classification": {
            "predeclared_logic": hierarchy["predeclared_descriptive_logic"],
            "trajectory_variance_class": hierarchy["trajectory_variance_class"],
            "trajectory_variance_dominant": hierarchy["trajectory_variance_dominant"],
        },
        "full_benchmark": within_benchmark,
        "optimization_equivalence": equivalence,
        "runtime": runtime,
        "limitations": limitations,
        "controls_run": [],
    }
    within_path = output_root / "within_layout_replication.json"
    _write_json(within_path, within_document)
    within_hash = sha256_file(within_path)

    across_document = {
        "schema_version": "1.0",
        "artifact_id": "visible-position-resolution-across-layout-generalization-v0.1",
        "status": "PASS",
        "generated_at": generated_at,
        "base_head": BASE_HEAD,
        "runner": within_document["runner"],
        "within_layout_replication": {
            "path": str(within_path),
            "sha256": within_hash,
        },
        "layer_selection_status": (
            "EXPLORATORY_PRESELECTED_FROM_EXISTING_POSITIVE_CONTROL"
        ),
        "combined_authority": authority.identity,
        "representation_definitions": representation_definitions,
        "outer_design": {
            "outer_fold_count": 6,
            "expected_outer_fold_count": 6,
            "outer_group": "layout",
            "test": "all three trajectories from one untouched layout",
            "train": "all trajectories from the other five layouts",
            "leakage_audit": "PASS",
        },
        "nested_scaling_and_alpha_selection": {
            **nested_semantics,
            "inner_group": "training_layout",
            "inner_fold_count_per_outer": 5,
            "inner_design": "leave-one-training-layout-out",
        },
        "nmae_std_definition": NMAE_STD_DEFINITION,
        "representations": {
            name: {
                "folds": [_public_fold(fold) for fold in folds],
                "summary": across_summary[name],
            }
            for name, folds in across_results.items()
        },
        "hierarchical_comparison": hierarchy,
        "classifications": {
            "trajectory_variance_class": hierarchy["trajectory_variance_class"],
            "trajectory_variance_dominant": hierarchy["trajectory_variance_dominant"],
            "layout_variance_class": hierarchy["layout_variance_class"],
            "layout_variance_dominant": hierarchy["layout_variance_dominant"],
            "both_trajectory_and_layout_variance": hierarchy[
                "both_trajectory_and_layout_variance"
            ],
            "layout_specific_representation_plausible": hierarchy[
                "layout_specific_representation_plausible"
            ],
            "token_preserving_readout_generalizes": hierarchy[
                "token_preserving_readout_generalizes"
            ],
        },
        "full_benchmark": across_benchmark,
        "optimization_equivalence": equivalence,
        "runtime": runtime,
        "limitations": limitations,
        "controls_run": [],
    }
    across_path = output_root / "across_layout_generalization.json"
    _write_json(across_path, across_document)
    print(within_path, flush=True)
    print(across_path, flush=True)
    return within_path, across_path


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--cache-root", type=Path, default=CACHE_ROOT)
    parser.add_argument(
        "--skip-activation-hashes",
        action="store_true",
        help="Only for focused tests; scientific runs must verify hashes.",
    )
    args = parser.parse_args(argv)
    run_task4(
        output_root=args.output_root,
        cache_root=args.cache_root,
        verify_activation_hashes=not args.skip_activation_hashes,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
