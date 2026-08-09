#!/usr/bin/env python3
"""Bounded layer-4 extraction and fixed-test visible-position learning curve.

The extraction path deliberately delegates model loading, frozen-frame loading,
trajectory validation, action conversion, windowing, tokenization, and
teacher-forced execution to the production 66-cell runner.  This wrapper only
narrows capture to layer 4 and retains the selected 336 visual-token rows plus
their production mean pool for the predeclared 351-row authority.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import importlib.util
import itertools
import json
import os
import sys
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402

from mineocclude.activations import hooks as hooks_module  # noqa: E402
from mineocclude.activations.pool import (  # noqa: E402
    MEAN_POOLING_IDENTITY,
    mean_pool_visual_tokens,
    select_visual_token_positions,
)
from mineocclude.activations.store import (  # noqa: E402
    UNPOOLED_REPRODUCTION_ATOL,
    UNPOOLED_REPRODUCTION_RTOL,
)
from mineocclude.metrics.u1_mean import regression_metrics  # noqa: E402
from mineocclude.probes.ridge import (  # noqa: E402
    fit_ridge,
    fit_standard_scaler,
    select_ridge_alpha_grouped,
)

RUNNER_VERSION = "exploratory-visible-position-diagnostics-runner-v0.1"
DEFAULT_CONFIG = (
    ROOT / "configs/experiments/exploratory_visible_position_diagnostics_v0_1.yaml"
)
PRODUCTION_RUNNER = ROOT / "scripts/run_person_a_66_cell_production_extraction.py"

LAYER_IDX = 4
TOKEN_COUNT = 336
HIDDEN_WIDTH = 2048
TOKEN_DTYPE = np.dtype("float16")
POOLED_DTYPE = np.dtype("float32")
EXPECTED_ELIGIBLE_ROWS = 351
EXPECTED_TEST_ROWS = 120
EXPECTED_TRAINING_ROWS = 231
EXPECTED_SUBSET_COUNT = 11
HOOK_SITE = "decoder_layer_output_residual_stream"

TRAJECTORIES = (
    ("L01", "layout_01", "layout_01_ep12602", 60, 60),
    ("L02", "layout_02", "layout_02_ep12610", 60, 60),
    ("L03", "layout_03", "layout_03_ep12645", 60, 60),
    ("L04", "layout_04", "layout_04_ep12626", 60, 60),
    ("L05", "layout_05", "layout_05_ep12634", 60, 60),
    ("L06", "layout_06", "layout_06_ep12616", 60, 51),
)
FIXED_TEST_LABELS = ("L03", "L04")
TRAINING_POOL_LABELS = ("L01", "L02", "L05", "L06")

# The adapter pins the VAE output to (frames, 14, 24) reshaped row-major to
# (frames, 336); the VQ encoder maps the 224x384 model-facing frame to a 14x24
# latent at downsample 16.  Token order is the verified extraction order.
TOKEN_GRID_ROWS = 14
TOKEN_GRID_COLS = 24
TOKEN_FLATTENED_FEATURE_COUNT = TOKEN_COUNT * HIDDEN_WIDTH


class DiagnosticError(RuntimeError):
    """Raised when a diagnostic identity or invariant is violated."""


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")


def _canonical_sha256(value: Any) -> str:
    return _sha256_bytes(_canonical_bytes(value))


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise DiagnosticError(f"refusing to overwrite existing artifact: {path}")
    payload = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    try:
        with temporary.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _write_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    if path.exists():
        raise DiagnosticError(f"refusing to overwrite existing artifact: {path}")
    payload = b"".join(_canonical_bytes(dict(row)) + b"\n" for row in rows)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    try:
        with temporary.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def load_config(path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    try:
        import yaml
    except ImportError as error:  # pragma: no cover - environment gate
        raise DiagnosticError(
            "PyYAML is required to read the diagnostic config"
        ) from error
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise DiagnosticError("diagnostic config must be a mapping")
    return document


def _resolved(root: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def _require_file_hash(path: Path, expected: str, name: str) -> str:
    if not path.is_file():
        raise DiagnosticError(f"missing {name}: {path}")
    observed = sha256_file(path)
    if observed != expected:
        raise DiagnosticError(
            f"{name} SHA-256 mismatch: expected {expected}, got {observed}"
        )
    return observed


def _trajectory_config(config: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    records = tuple(dict(record) for record in config["trajectories"])
    observed = tuple(
        (
            record["label"],
            record["layout_id"],
            record["trajectory_id"],
            record["source_frame_count"],
            record["eligible_frame_count"],
        )
        for record in records
    )
    if observed != TRAJECTORIES:
        raise DiagnosticError(
            "config trajectories differ from the frozen six-row authority"
        )
    if tuple(config["fixed_test_trajectory_labels"]) != FIXED_TEST_LABELS:
        raise DiagnosticError("fixed-test trajectory labels differ from L03/L04")
    if tuple(config["training_pool_trajectory_labels"]) != TRAINING_POOL_LABELS:
        raise DiagnosticError("training pool differs from L01/L02/L05/L06")
    scope = config["scientific_scope"]
    expected_scope = {
        "layer_idx": LAYER_IDX,
        "hook_site": HOOK_SITE,
        "hidden_width": HIDDEN_WIDTH,
        "visual_token_count": TOKEN_COUNT,
        "pooling_identity": MEAN_POOLING_IDENTITY,
        "window_size": 16,
    }
    if any(scope.get(key) != value for key, value in expected_scope.items()):
        raise DiagnosticError(
            "scientific scope differs from the frozen layer-4 contract"
        )
    return records


def load_visible_authority(
    config: Mapping[str, Any], *, root: Path = ROOT
) -> tuple[dict[str, Any], ...]:
    """Load and exact-join the predeclared 351 visible rows to oracle targets."""

    trajectories = _trajectory_config(config)
    authority = config["authority"]
    row_path = _resolved(root, authority["row_universe_path"])
    target_path = _resolved(root, authority["oracle_target_path"])
    _require_file_hash(
        row_path, authority["row_universe_sha256"], "row-universe authority"
    )
    _require_file_hash(
        target_path, authority["oracle_target_sha256"], "oracle-target authority"
    )

    wanted = {record["trajectory_id"]: record for record in trajectories}
    selected = [
        row
        for row in _jsonl(row_path)
        if row.get("trajectory_id") in wanted
        and row.get("status") == "accepted"
        and row.get("visible_flag") is True
        and row.get("admission_stratum") == "no_wall_visible_control"
        and row.get("control_type") == "no_wall_visible_control"
    ]
    target_index: dict[tuple[str, int], dict[str, Any]] = {}
    for target in _jsonl(target_path):
        key = (target.get("trajectory_id"), target.get("model_frame_idx"))
        if key in target_index:
            raise DiagnosticError(f"duplicate oracle target key: {key}")
        target_index[key] = target

    label_order = {record["label"]: index for index, record in enumerate(trajectories)}
    result: list[dict[str, Any]] = []
    for row in selected:
        trajectory = wanted[row["trajectory_id"]]
        key = (row["trajectory_id"], row["model_frame_idx"])
        target = target_index.get(key)
        if target is None or target.get("status") != "accepted":
            raise DiagnosticError(f"missing accepted oracle target for {key}")
        if target.get("layout_id") != trajectory["layout_id"]:
            raise DiagnosticError(f"layout mismatch for {key}")
        result.append(
            {
                "row_key": f"{key[0]}:{key[1]}",
                "trajectory_label": trajectory["label"],
                "trajectory_id": key[0],
                "layout_id": trajectory["layout_id"],
                "model_frame_idx": key[1],
                "render_frame_idx": row["model_frame_idx"],
                "fold_idx": row["fold_idx"],
                "x_true_blocks": float(target["x_true_blocks"]),
                "target_id": target["target_id"],
            }
        )
    result.sort(
        key=lambda row: (label_order[row["trajectory_label"]], row["model_frame_idx"])
    )

    expected_counts = {
        record["label"]: record["eligible_frame_count"] for record in trajectories
    }
    observed_counts = {
        label: sum(row["trajectory_label"] == label for row in result)
        for label in expected_counts
    }
    if observed_counts != expected_counts or len(result) != EXPECTED_ELIGIBLE_ROWS:
        raise DiagnosticError(
            f"visible authority counts differ: expected {expected_counts}, got {observed_counts}"
        )
    for record in trajectories:
        frames = [
            row["model_frame_idx"]
            for row in result
            if row["trajectory_label"] == record["label"]
        ]
        if frames != list(range(record["eligible_frame_count"])):
            raise DiagnosticError(
                f"{record['label']} eligible frames are not the exact contiguous prefix"
            )
    test = [row for row in result if row["trajectory_label"] in FIXED_TEST_LABELS]
    train = [row for row in result if row["trajectory_label"] in TRAINING_POOL_LABELS]
    if len(test) != EXPECTED_TEST_ROWS or len(train) != EXPECTED_TRAINING_ROWS:
        raise DiagnosticError("fixed test/training counts differ from 120/231")
    if {row["fold_idx"] for row in test} != {4} or 4 in {
        row["fold_idx"] for row in train
    }:
        raise DiagnosticError("fold-4 authority is not exactly L03/L04")
    if {row["row_key"] for row in test} & {row["row_key"] for row in train}:
        raise DiagnosticError("fixed test and training pool overlap")
    return tuple(result)


def fixed_test_hash(rows: Sequence[Mapping[str, Any]]) -> str:
    test_rows = [
        {
            "row_key": row["row_key"],
            "trajectory_label": row["trajectory_label"],
            "x_true_blocks": float(row["x_true_blocks"]),
        }
        for row in rows
        if row["trajectory_label"] in FIXED_TEST_LABELS
    ]
    if len(test_rows) != EXPECTED_TEST_ROWS:
        raise DiagnosticError("fixed test must contain exactly 120 rows")
    return _canonical_sha256(test_rows)


def enumerate_learning_curve_subsets() -> tuple[tuple[str, ...], ...]:
    return tuple(
        subset
        for size in (2, 3, 4)
        for subset in itertools.combinations(TRAINING_POOL_LABELS, size)
    )


def build_subset_plan(
    rows: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], ...]:
    test_sha256 = fixed_test_hash(rows)
    plans = []
    for subset in enumerate_learning_curve_subsets():
        training_rows = [row for row in rows if row["trajectory_label"] in subset]
        plans.append(
            {
                "subset_id": "+".join(subset),
                "k_trajectories": len(subset),
                "training_trajectory_labels": list(subset),
                "training_trajectory_ids": sorted(
                    {row["trajectory_id"] for row in training_rows}
                ),
                "training_frame_count": len(training_rows),
                "fixed_test_trajectory_labels": list(FIXED_TEST_LABELS),
                "fixed_test_frame_count": EXPECTED_TEST_ROWS,
                "fixed_test_sha256": test_sha256,
            }
        )
    if len(plans) != EXPECTED_SUBSET_COUNT:
        raise DiagnosticError("learning curve must contain exactly 11 subsets")
    return tuple(plans)


def validate_extracted_arrays(
    token_values: Any, pooled_values: Any, *, expected_rows: int
) -> tuple[np.ndarray, np.ndarray]:
    tokens = np.asarray(token_values)
    pooled = np.asarray(pooled_values)
    if tokens.shape != (expected_rows, TOKEN_COUNT, HIDDEN_WIDTH):
        raise DiagnosticError(
            f"unpooled shape must be [{expected_rows},{TOKEN_COUNT},{HIDDEN_WIDTH}]"
        )
    if pooled.shape != (expected_rows, HIDDEN_WIDTH):
        raise DiagnosticError(f"pooled shape must be [{expected_rows},{HIDDEN_WIDTH}]")
    if tokens.dtype != TOKEN_DTYPE or pooled.dtype != POOLED_DTYPE:
        raise DiagnosticError("unpooled/pooled dtypes must be float16/float32")
    if not np.isfinite(tokens).all() or not np.isfinite(pooled).all():
        raise DiagnosticError("extracted arrays contain non-finite values")
    return tokens, pooled


def compare_token_pooling(
    token_values: Any,
    pooled_value: Any,
    *,
    rtol: float = UNPOOLED_REPRODUCTION_RTOL,
    atol: float = UNPOOLED_REPRODUCTION_ATOL,
) -> dict[str, Any]:
    tokens = np.asarray(token_values)
    pooled = np.asarray(pooled_value)
    if tokens.shape != (TOKEN_COUNT, HIDDEN_WIDTH) or pooled.shape != (HIDDEN_WIDTH,):
        raise DiagnosticError("pooling comparison shapes must be [336,2048] and [2048]")
    recomputed = tokens.astype(np.float32).mean(axis=0)
    difference = np.abs(recomputed - pooled.astype(np.float32, copy=False))
    return {
        "allclose": bool(np.allclose(recomputed, pooled, rtol=rtol, atol=atol)),
        "maximum_absolute_difference": float(difference.max(initial=0.0)),
        "rtol": float(rtol),
        "atol": float(atol),
        "cpu_recomputed_mean_sha256": _sha256_bytes(recomputed.tobytes(order="C")),
        "production_pooled_sha256": _sha256_bytes(
            pooled.astype(np.float32, copy=False).tobytes(order="C")
        ),
    }


def compare_historical_tokens(
    new_tokens: Any, historical_tokens: Any
) -> dict[str, Any]:
    new = np.asarray(new_tokens)
    old = np.asarray(historical_tokens)
    if new.shape != old.shape or new.shape != (TOKEN_COUNT, HIDDEN_WIDTH):
        raise DiagnosticError("historical bridge requires matching [336,2048] arrays")
    if new.dtype != TOKEN_DTYPE or old.dtype != TOKEN_DTYPE:
        raise DiagnosticError("historical bridge token arrays must both be float16")
    maximum = float(np.max(np.abs(new.astype(np.float32) - old.astype(np.float32))))
    new_hash = _sha256_bytes(new.tobytes(order="C"))
    old_hash = _sha256_bytes(old.tobytes(order="C"))
    return {
        "exact": bool(np.array_equal(new, old)),
        "maximum_absolute_difference": maximum,
        "new_token_sha256": new_hash,
        "historical_token_sha256": old_hash,
        "sha256_equal": new_hash == old_hash,
    }


def fit_fixed_test_ridge(
    training_features: Any,
    training_targets: Any,
    training_groups: Sequence[str],
    test_features: Any,
    *,
    alpha_grid: Sequence[float],
    seed: int,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Fit using only training data; the API intentionally accepts no test targets."""

    train_x = np.asarray(training_features)
    train_y = np.asarray(training_targets)
    test_x = np.asarray(test_features)
    groups = tuple(training_groups)
    unique_groups = tuple(sorted(set(groups)))
    if len(unique_groups) < 2 or not (
        train_x.ndim == test_x.ndim == 2
        and train_y.ndim == 1
        and train_x.shape[0] == train_y.shape[0] == len(groups)
        and train_x.shape[1] == test_x.shape[1]
    ):
        raise DiagnosticError("ridge train/test feature identities are invalid")
    selection = select_ridge_alpha_grouped(
        train_x,
        train_y,
        groups,
        alpha_grid=alpha_grid,
        n_splits=len(unique_groups),
        seed=seed,
    )
    model = fit_ridge(train_x, train_y, alpha=selection.selected_alpha)
    predictions = np.asarray(model.predict(test_x), dtype=np.float64)
    return predictions, {
        "selected_alpha": selection.selected_alpha,
        "validation_mse_by_alpha": {
            str(alpha): mse for alpha, mse in selection.mean_mse_by_alpha.items()
        },
        "selection_policy": "leave-one-training-trajectory-out",
        "inner_fold_count": selection.inner_fold_count,
        "training_group_ids": list(unique_groups),
        "scaler_fit_scope": "training_subset_rows_only",
        "scaler_training_row_count": model.scaler.training_row_count,
    }


class _LayerCaptureContext:
    """Single-use context manager retaining exactly one validated decoder layer."""

    def __init__(self, discovery: Any, layer_idx: int) -> None:
        runtime_layers = tuple(discovery.iter_runtime_layers())
        matches = [item for item in runtime_layers if item[0].layer_idx == layer_idx]
        if len(runtime_layers) != 20 or len(matches) != 1:
            raise DiagnosticError(
                "decoder discovery is not the exact frozen 20-layer set"
            )
        self.layer, self.module = matches[0]
        self.capture: Any | None = None
        self.handle: Any | None = None
        self.closed = False

    def _callback(self, _module: object, _inputs: object, output: object) -> None:
        if self.closed:
            raise DiagnosticError("layer-4 hook callback arrived after close")
        if self.capture is not None:
            raise DiagnosticError("layer-4 hook emitted more than one callback")
        normalized = hooks_module.normalize_hook_output(output)
        if normalized.batch_size != 1 or normalized.hidden_size != HIDDEN_WIDTH:
            raise DiagnosticError("layer-4 output shape differs from [1,sequence,2048]")
        self.capture = hooks_module.HookCapture(self.layer, normalized)

    def __enter__(self) -> "_LayerCaptureContext":
        if self.handle is not None or self.closed:
            raise DiagnosticError("layer-4 hook context is single-use")
        register = getattr(self.module, "register_forward_hook", None)
        if not callable(register):
            raise DiagnosticError("layer-4 decoder module cannot register a hook")
        self.handle = register(self._callback)
        if not callable(getattr(self.handle, "remove", None)):
            raise DiagnosticError("layer-4 hook handle has no remove()")
        return self

    def __exit__(self, error_type: object, error: object, traceback: object) -> bool:
        try:
            if self.handle is not None:
                self.handle.remove()
        finally:
            self.closed = True
        if error_type is None and self.capture is None:
            raise DiagnosticError("layer-4 hook emitted no callback")
        return False


def _load_production_runner() -> Any:
    module_name = "_mineocclude_person_a_66_cell_production_extraction"
    existing = sys.modules.get(module_name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(module_name, PRODUCTION_RUNNER)
    if spec is None or spec.loader is None:
        raise DiagnosticError(f"cannot import production runner: {PRODUCTION_RUNNER}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _production_bridge(
    config: Mapping[str, Any],
    *,
    run_id: str,
    external_root: Path,
    frame_payload_root: Path,
) -> Any:
    production = _load_production_runner()
    authority = config["authority"]
    frame_manifest_path = _resolved(ROOT, authority["preprocessed_frame_manifest_path"])
    _require_file_hash(
        frame_manifest_path,
        authority["preprocessed_frame_manifest_sha256"],
        "preprocessed-frame manifest",
    )
    if not frame_payload_root.is_dir():
        raise DiagnosticError(
            "exact frozen .f32le payload root is missing; lossy repository MP4s are "
            f"not permitted as a substitute: {frame_payload_root}"
        )
    production.RUN_ID = run_id
    production.CONFIG_HASH = _canonical_sha256(config)
    production.FRAME_MANIFEST_PATH = frame_manifest_path
    production.FRAME_PAYLOAD_ROOT = frame_payload_root
    production.SESSION_LOG_ROOT = external_root / "runner-sessions"
    production.C_CANONICAL_MEDIA_COMMIT = authority["person_c_canonical_media_commit"]
    production._frame_manifest_index.cache_clear()
    production._RUNTIME = production.Runtime()
    return production


def _teacher_capture_layer4(
    production: Any,
    adapter: Any,
    runtime_identity: Any,
    tokenized: Any,
    accepted_manifest_sha256: str,
) -> tuple[Any, Any]:
    holder: dict[str, _LayerCaptureContext] = {}

    def factory(modules: tuple[tuple[str, object], ...]) -> _LayerCaptureContext:
        manager = _LayerCaptureContext(
            production._discovery_from_modules(modules), LAYER_IDX
        )
        holder["manager"] = manager
        return manager

    result = adapter.teacher_forced(
        production.adapter_module.TeacherForcedRequest(
            runtime_identity=runtime_identity,
            trajectory=tokenized,
            seed=production.SEED,
            precision=production.PRECISION,
            batch_size=1,
            hook_context_factory=factory,
            expected_adapter_code_sha256=production.wave4._adapter_code_identity().sha256,
            accepted_manifest_sha256=accepted_manifest_sha256,
        )
    )
    manager = holder.get("manager")
    if manager is None or not manager.closed or manager.capture is None:
        raise DiagnosticError("layer-4 capture context did not close with one capture")
    return result, manager.capture


def _save_npy_exclusive(path: Path, array: np.ndarray) -> None:
    with path.open("xb") as handle:
        np.save(handle, array, allow_pickle=False)
        handle.flush()
        os.fsync(handle.fileno())


def _historical_bridge(
    bridge_config: Mapping[str, Any], new_tokens: np.ndarray
) -> dict[str, Any]:
    manifest_path = _resolved(ROOT, bridge_config["manifest_path"])
    if not manifest_path.is_file():
        return {
            "trajectory_id": bridge_config["trajectory_id"],
            "model_frame_idx": bridge_config["model_frame_idx"],
            "status": "UNAVAILABLE",
            "reason": f"missing historical manifest: {manifest_path}",
        }
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected_identity = {
        "trajectory_id": bridge_config["trajectory_id"],
        "model_frame_idx": bridge_config["model_frame_idx"],
        "hook_site": HOOK_SITE,
    }
    if (
        manifest.get("status") != "PASS"
        or manifest.get("scientific_identity") != expected_identity
    ):
        raise DiagnosticError(f"historical bridge identity failed: {manifest_path}")
    artifact_path = manifest_path.parent / manifest["artifact"]["path"]
    _require_file_hash(
        artifact_path, manifest["artifact"]["sha256"], "historical unpooled artifact"
    )
    with np.load(artifact_path, allow_pickle=False) as archive:
        layers = archive["layer_indices"]
        indices = np.flatnonzero(layers == LAYER_IDX)
        if indices.tolist() != [LAYER_IDX]:
            raise DiagnosticError(
                f"historical artifact layer-4 index failed: {artifact_path}"
            )
        old_tokens = archive["token_values"][int(indices[0])]
        if tuple(archive["visual_positions"].tolist()) != tuple(range(TOKEN_COUNT)):
            raise DiagnosticError(
                f"historical visual positions failed: {artifact_path}"
            )
    comparison = compare_historical_tokens(new_tokens, old_tokens)
    return {
        "trajectory_id": bridge_config["trajectory_id"],
        "model_frame_idx": bridge_config["model_frame_idx"],
        "layer_idx": LAYER_IDX,
        "status": "COMPARED",
        "historical_manifest_path": str(manifest_path.relative_to(ROOT)),
        "historical_manifest_sha256": sha256_file(manifest_path),
        "historical_artifact_path": str(artifact_path.relative_to(ROOT)),
        "historical_artifact_sha256": sha256_file(artifact_path),
        "historical_preprocessing_profile": manifest["provenance"][
            "preprocessing_profile"
        ],
        **comparison,
    }


def _extract_trajectory(
    production: Any,
    trajectory_config: Mapping[str, Any],
    authority_rows: Sequence[Mapping[str, Any]],
    output_root: Path,
    bridge_config: Mapping[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    trajectory_id = trajectory_config["trajectory_id"]
    source_frame_count = int(trajectory_config["source_frame_count"])
    eligible = [row for row in authority_rows if row["trajectory_id"] == trajectory_id]
    eligible_keys = {
        (row["trajectory_id"], row["model_frame_idx"]): row for row in eligible
    }
    if len(eligible) != trajectory_config["eligible_frame_count"]:
        raise DiagnosticError(f"{trajectory_id}: eligible authority count changed")

    production._RUNTIME.ensure_loaded()
    adapter = production._RUNTIME.adapter
    runtime_identity = production._RUNTIME.runtime_identity
    package_bytes = production._capture_package_bytes(trajectory_id)
    declared = production._capture_package_declared_sha256(trajectory_id)
    package_sha256 = _sha256_bytes(package_bytes)
    if package_sha256 != declared:
        raise DiagnosticError(f"{trajectory_id}: Person C package SHA-256 mismatch")
    document = json.loads(package_bytes)
    if document.get("trajectory_id") != trajectory_id:
        raise DiagnosticError(f"{trajectory_id}: capture-package identity mismatch")

    frame_map_bytes = production._c_stream_bytes(trajectory_id, "frame_map")
    state_bytes = production._c_stream_bytes(trajectory_id, "server_state")
    frame_map_rows = sorted(
        production._jsonl_rows(frame_map_bytes), key=lambda row: row["model_frame_idx"]
    )
    state_rows = sorted(
        production._jsonl_rows(state_bytes), key=lambda row: row["model_frame_idx"]
    )
    if (
        len(frame_map_rows) != source_frame_count
        or len(state_rows) != source_frame_count
    ):
        raise DiagnosticError(f"{trajectory_id}: source context is not exactly 60 rows")
    production.build_source_frame_bindings_v2(
        trajectory_id=trajectory_id,
        frame_map_rows=frame_map_rows,
        state_rows=state_rows,
        c_frame_map_sha256=_sha256_bytes(frame_map_bytes),
        c_state_sha256=_sha256_bytes(state_bytes),
    )

    validated = adapter.validate_trajectory(
        production.adapter_module.AcceptedTrajectoryInput(
            schema_version=production.SCHEMA_VERSION,
            trajectory_id=trajectory_id,
            accepted_manifest_sha256=package_sha256,
            document=document,
        )
    )
    if len(validated.frame_identities) != source_frame_count:
        raise DiagnosticError(f"{trajectory_id}: validation dropped source frames")

    manifest_index = production._frame_manifest_index()
    frames = []
    for identity in validated.frame_identities:
        record = manifest_index.get((identity.trajectory_id, identity.model_frame_idx))
        if record is None:
            raise DiagnosticError(f"{trajectory_id}: missing frozen frame {identity}")
        frames.append(
            production._load_preprocessed_frame(identity, record, runtime_identity)
        )
    frames = tuple(frames)
    raw_action_rows = {
        row["model_frame_idx"]: row for row in document["streams"]["raw_actions"]
    }
    actions = tuple(
        adapter.convert_action(
            production.adapter_module.ActionConversionRequest(
                identity=identity,
                action_idx=raw_action_rows[identity.model_frame_idx]["action_idx"],
                raw_action=raw_action_rows[identity.model_frame_idx]["raw_action"],
            )
        )
        for identity in validated.frame_identities
    )

    token_rows: list[np.ndarray] = []
    pooled_rows: list[np.ndarray] = []
    row_records: list[dict[str, Any]] = []
    window_records = []
    for start in range(0, source_frame_count, 16):
        stop = min(start + 16, source_frame_count)
        window_trajectory = dataclasses.replace(
            validated, frame_identities=validated.frame_identities[start:stop]
        )
        tokenized = adapter.tokenize_trajectory(
            production.adapter_module.TrajectoryTokenizationRequest(
                runtime_identity=runtime_identity,
                trajectory=window_trajectory,
                frames=frames[start:stop],
                actions=actions[start:stop],
            )
        )
        spans = tokenized.frame_token_map.spans
        if [span.identity.model_frame_idx for span in spans] != list(
            range(start, stop)
        ):
            raise DiagnosticError(
                f"{trajectory_id}: window {start}:{stop} lost identity"
            )
        if [span.pair_index for span in spans] != list(range(stop - start)):
            raise DiagnosticError(
                f"{trajectory_id}: window {start}:{stop} lost pair order"
            )
        teacher_result, capture = _teacher_capture_layer4(
            production, adapter, runtime_identity, tokenized, package_sha256
        )
        activation = capture.output.tensor
        if str(activation.dtype) != "torch.float16":
            raise DiagnosticError(
                f"{trajectory_id}: layer-4 source dtype must be torch.float16"
            )
        window_records.append(
            {
                "start_model_frame_idx": start,
                "stop_model_frame_idx_exclusive": stop,
                "source_frame_count": stop - start,
                "sequence_length": capture.output.sequence_length,
                "frame_token_map_sha256": tokenized.frame_token_map_sha256,
                "teacher_result_sha256": teacher_result.result_sha256,
            }
        )
        for span in spans:
            key = (span.identity.trajectory_id, span.identity.model_frame_idx)
            authority_row = eligible_keys.get(key)
            if authority_row is None:
                continue
            selection = select_visual_token_positions(
                tokenized.frame_token_map,
                trajectory_id=key[0],
                model_frame_idx=key[1],
                hooked_sequence_length=capture.output.sequence_length,
            )
            pooled = mean_pool_visual_tokens(
                activation=activation,
                selection=selection,
                layer_idx=LAYER_IDX,
                hook_site=HOOK_SITE,
            )
            import torch

            position_index = torch.tensor(
                selection.positions, dtype=torch.long, device=activation.device
            )
            selected_tokens = (
                activation.detach()
                .index_select(1, position_index)
                .squeeze(0)
                .to(device="cpu", dtype=torch.float16)
                .contiguous()
                .numpy()
                .copy()
            )
            pooled_vector = (
                pooled.vector.detach()
                .cpu()
                .contiguous()
                .numpy()
                .astype(np.float32, copy=False)
            )
            pooling_check = compare_token_pooling(selected_tokens, pooled_vector)
            if not pooling_check["allclose"]:
                raise DiagnosticError(
                    f"{authority_row['row_key']}: token mean mismatch"
                )
            token_rows.append(selected_tokens)
            pooled_rows.append(pooled_vector.copy())
            row_records.append(
                {
                    **authority_row,
                    "layer_idx": LAYER_IDX,
                    "hook_site": HOOK_SITE,
                    "frame_token_map_sha256": tokenized.frame_token_map_sha256,
                    "visual_positions_sha256": _canonical_sha256(
                        list(selection.positions)
                    ),
                    "visual_token_count": TOKEN_COUNT,
                    "hidden_width": HIDDEN_WIDTH,
                    "source_dtype": capture.output.tensor.dtype.__str__(),
                    "token_dtype": "float16",
                    "pooled_dtype": "float32",
                    "pooling_identity": MEAN_POOLING_IDENTITY,
                    "pooling_reproduction": pooling_check,
                }
            )
        del capture, activation, teacher_result
        import torch

        torch.cuda.empty_cache()

    if [row["row_key"] for row in row_records] != [row["row_key"] for row in eligible]:
        raise DiagnosticError(
            f"{trajectory_id}: retained row order differs from authority"
        )
    tokens, pooled = validate_extracted_arrays(
        np.stack(token_rows, axis=0).astype(np.float16, copy=False),
        np.stack(pooled_rows, axis=0).astype(np.float32, copy=False),
        expected_rows=len(eligible),
    )
    stem = trajectory_config["label"].lower()
    token_path = output_root / f"{stem}_layer4_visual_tokens.f16.npy"
    pooled_path = output_root / f"{stem}_layer4_mean_pooled.f32.npy"
    rows_path = output_root / f"{stem}_rows.jsonl"
    _save_npy_exclusive(token_path, tokens)
    _save_npy_exclusive(pooled_path, pooled)
    _write_jsonl(rows_path, row_records)
    chunk = {
        "trajectory_label": trajectory_config["label"],
        "trajectory_id": trajectory_id,
        "layout_id": trajectory_config["layout_id"],
        "source_frame_count": source_frame_count,
        "eligible_row_count": len(eligible),
        "token_array": {
            "path": str(token_path),
            "shape": list(tokens.shape),
            "dtype": str(tokens.dtype),
            "byte_size": token_path.stat().st_size,
            "sha256": sha256_file(token_path),
        },
        "pooled_array": {
            "path": str(pooled_path),
            "shape": list(pooled.shape),
            "dtype": str(pooled.dtype),
            "byte_size": pooled_path.stat().st_size,
            "sha256": sha256_file(pooled_path),
        },
        "rows": {
            "path": str(rows_path),
            "row_count": len(row_records),
            "byte_size": rows_path.stat().st_size,
            "sha256": sha256_file(rows_path),
        },
        "person_c_capture_package_sha256": package_sha256,
        "person_c_frame_map_sha256": _sha256_bytes(frame_map_bytes),
        "person_c_server_state_sha256": _sha256_bytes(state_bytes),
        "windows": window_records,
    }
    bridge = _historical_bridge(bridge_config, tokens[0]) if bridge_config else None
    return chunk, bridge


def run_extract(
    config: Mapping[str, Any], *, run_id: str, frame_payload_root: Path
) -> Path:
    if not run_id or run_id in {".", ".."} or Path(run_id).name != run_id:
        raise DiagnosticError("run_id must be one non-empty path-safe component")
    trajectories = _trajectory_config(config)
    authority_rows = load_visible_authority(config)
    storage = config["storage"]
    external_root = Path(storage["external_base_root"]) / run_id
    receipt_root = _resolved(ROOT, storage["receipt_root"])
    receipt_path = receipt_root / "unpooled_activation_manifest.json"
    if external_root.exists():
        raise DiagnosticError(
            f"refusing to reuse external run directory: {external_root}"
        )
    if receipt_path.exists():
        raise DiagnosticError(f"refusing to overwrite receipt: {receipt_path}")
    external_root.mkdir(parents=True)
    production = _production_bridge(
        config,
        run_id=run_id,
        external_root=external_root,
        frame_payload_root=frame_payload_root,
    )

    bridge_by_trajectory = {
        record["trajectory_id"]: record for record in config["historical_bridge"]
    }
    chunks = []
    bridges = []
    for trajectory in trajectories:
        chunk, bridge = _extract_trajectory(
            production,
            trajectory,
            authority_rows,
            external_root,
            bridge_by_trajectory.get(trajectory["trajectory_id"]),
        )
        chunks.append(chunk)
        if bridge is not None:
            bridges.append(bridge)

    runtime_identity = production._RUNTIME.runtime_identity
    all_row_keys = [row["row_key"] for row in authority_rows]
    token_bytes = sum(chunk["token_array"]["byte_size"] for chunk in chunks)
    pooled_bytes = sum(chunk["pooled_array"]["byte_size"] for chunk in chunks)
    manifest = {
        "schema_version": "1.0",
        "artifact_version": "exploratory-visible-position-unpooled-v0.1",
        "status": "COMPLETE",
        "run_id": run_id,
        "generated_at": _now_iso(),
        "runner_version": RUNNER_VERSION,
        "runner_path": str(Path(__file__).resolve().relative_to(ROOT)),
        "runner_sha256": sha256_file(Path(__file__).resolve()),
        "config_path": str(DEFAULT_CONFIG.relative_to(ROOT)),
        "config_sha256": sha256_file(DEFAULT_CONFIG),
        "base_head": config["base_head"],
        "external_root": str(external_root),
        "scope": {
            "layer_idx": LAYER_IDX,
            "hook_site": HOOK_SITE,
            "eligible_row_count": EXPECTED_ELIGIBLE_ROWS,
            "trajectory_count": len(TRAJECTORIES),
            "trajectory_labels": [record[0] for record in TRAJECTORIES],
            "trajectory_ids": [record[2] for record in TRAJECTORIES],
            "visual_token_count": TOKEN_COUNT,
            "hidden_width": HIDDEN_WIDTH,
            "token_dtype": "float16",
            "pooled_dtype": "float32",
            "pooling_identity": MEAN_POOLING_IDENTITY,
            "other_layers_retained": False,
            "action_tokens_retained": False,
            "noneligible_frames_retained": False,
        },
        "sequence_context": {
            "policy": "production-66-cell-contiguous-windowing",
            "window_size": 16,
            "all_source_frames_processed": True,
            "source_frame_count_per_trajectory": {
                record["trajectory_id"]: record["source_frame_count"]
                for record in trajectories
            },
            "teacher_forcing": True,
        },
        "authority": {
            **dict(config["authority"]),
            "eligible_row_keys_sha256": _canonical_sha256(all_row_keys),
            "fixed_test_sha256": fixed_test_hash(authority_rows),
        },
        "runtime_identity": {
            "runtime_id": runtime_identity.runtime_id,
            "mineocclude_revision": runtime_identity.mineocclude_revision,
            "mineworld_source_revision": runtime_identity.mineworld_source_revision,
            "modelscope_asset_revision": runtime_identity.modelscope_asset_revision,
            "checkpoint_sha256": production.wave2.PINNED_MAIN_CHECKPOINT_SHA256,
            "model_config_sha256": production.wave2.PINNED_MODEL_CONFIG_SHA256,
            "vae_config_sha256": production.wave2.PINNED_VAE_CONFIG_SHA256,
            "vae_checkpoint_sha256": production.wave2.PINNED_VAE_CHECKPOINT_SHA256,
            "adapter_code_sha256": runtime_identity.adapter_code_sha256,
            "preprocessing_identity": runtime_identity.preprocessing_identity,
            "preprocess_hash": production.wave5.PERSON_A_66_CELL_V0_2_PREPROCESS_HASH,
            "tokenization_profile": production.wave4.TOKENIZATION_PROFILE,
            "precision": production.PRECISION,
            "device": runtime_identity.device,
            "environment_report_sha256": production._RUNTIME.environment_report_sha256,
        },
        "chunks": chunks,
        "historical_frame0_bridge": {
            "comparison_scope": "layer-4 visual tokens only",
            "comparison": "float16 exact equality plus float32 maximum absolute difference",
            "records": bridges,
        },
        "storage": {
            "token_array_file_bytes": token_bytes,
            "pooled_array_file_bytes": pooled_bytes,
            "array_file_bytes": token_bytes + pooled_bytes,
        },
    }
    _write_json(receipt_path, manifest)
    return receipt_path


def _load_extracted_pooled(
    manifest_path: Path,
    authority_rows: Sequence[Mapping[str, Any]],
) -> tuple[np.ndarray, tuple[dict[str, Any], ...], dict[str, Any]]:
    if not manifest_path.is_file():
        raise DiagnosticError(f"missing extraction manifest: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    scope = manifest.get("scope", {})
    if (
        manifest.get("status") != "COMPLETE"
        or manifest.get("config_sha256") != sha256_file(DEFAULT_CONFIG)
        or scope.get("layer_idx") != LAYER_IDX
        or scope.get("eligible_row_count") != EXPECTED_ELIGIBLE_ROWS
        or scope.get("visual_token_count") != TOKEN_COUNT
        or scope.get("hidden_width") != HIDDEN_WIDTH
    ):
        raise DiagnosticError("extraction manifest scope is not the exact diagnostic")
    pooled_parts = []
    extracted_rows: list[dict[str, Any]] = []
    expected_by_label = {row[0]: row[4] for row in TRAJECTORIES}
    for chunk in manifest.get("chunks", []):
        label = chunk["trajectory_label"]
        expected_rows = expected_by_label.get(label)
        if expected_rows is None:
            raise DiagnosticError(f"unexpected extraction chunk: {label}")
        token_meta = chunk["token_array"]
        pooled_meta = chunk["pooled_array"]
        rows_meta = chunk["rows"]
        token_path = Path(token_meta["path"])
        pooled_path = Path(pooled_meta["path"])
        rows_path = Path(rows_meta["path"])
        _require_file_hash(token_path, token_meta["sha256"], f"{label} token array")
        _require_file_hash(pooled_path, pooled_meta["sha256"], f"{label} pooled array")
        _require_file_hash(rows_path, rows_meta["sha256"], f"{label} row records")
        tokens = np.load(token_path, mmap_mode="r", allow_pickle=False)
        pooled = np.load(pooled_path, allow_pickle=False)
        if (
            tokens.shape != (expected_rows, TOKEN_COUNT, HIDDEN_WIDTH)
            or tokens.dtype != TOKEN_DTYPE
            or pooled.shape != (expected_rows, HIDDEN_WIDTH)
            or pooled.dtype != POOLED_DTYPE
        ):
            raise DiagnosticError(f"{label} extracted array shape/dtype mismatch")
        rows = _jsonl(rows_path)
        if len(rows) != expected_rows:
            raise DiagnosticError(f"{label} extracted row count mismatch")
        pooled_parts.append(pooled)
        extracted_rows.extend(rows)
    if len(pooled_parts) != len(TRAJECTORIES):
        raise DiagnosticError("extraction manifest must contain six chunks")
    if [row["row_key"] for row in extracted_rows] != [
        row["row_key"] for row in authority_rows
    ]:
        raise DiagnosticError(
            "extracted rows differ from current authority identity/order"
        )
    features = np.concatenate(pooled_parts, axis=0).astype(np.float32, copy=False)
    if features.shape != (EXPECTED_ELIGIBLE_ROWS, HIDDEN_WIDTH):
        raise DiagnosticError("joined pooled feature shape differs from [351,2048]")
    return features, tuple(extracted_rows), manifest


def _save_learning_curve_plot(path: Path, results: Sequence[Mapping[str, Any]]) -> None:
    if path.exists():
        raise DiagnosticError(f"refusing to overwrite existing artifact: {path}")
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as error:  # pragma: no cover - environment gate
        raise DiagnosticError(
            "matplotlib is required for the learning-curve plot"
        ) from error
    ordered = sorted(
        results,
        key=lambda row: (
            row["k_trajectories"],
            row["training_frame_count"],
            row["subset_id"],
        ),
    )
    figure, (axis_r2, axis_mae) = plt.subplots(1, 2, figsize=(11, 5.2))
    # Primary x-axis is the number of whole training trajectories; a deterministic
    # offset inside each k keeps every subset visible without hiding the
    # within-size spread.
    by_k: dict[int, list[Mapping[str, Any]]] = {}
    for row in ordered:
        by_k.setdefault(row["k_trajectories"], []).append(row)
    x = []
    for row in ordered:
        group = by_k[row["k_trajectories"]]
        rank = group.index(row)
        spread = 0.0 if len(group) == 1 else (rank / (len(group) - 1) - 0.5) * 0.5
        x.append(row["k_trajectories"] + spread)
    for axis, key, color, label in (
        (axis_r2, "r2", "#3366aa", "Fixed-test R²"),
        (axis_mae, "mae", "#aa5533", "Fixed-test MAE (blocks)"),
    ):
        values = [row[key] for row in ordered]
        axis.scatter(x, values, color=color, zorder=3)
        for position, value, row in zip(x, values, ordered):
            axis.annotate(
                f"{row['training_frame_count']}f",
                (position, value),
                textcoords="offset points",
                xytext=(0, 6),
                ha="center",
                fontsize=6.5,
                color="#444444",
            )
        axis.set(ylabel=label, xlabel="Training trajectories (k)")
        axis.set_xticks(sorted(by_k))
        axis.set_xticklabels([f"k={k}\n({len(by_k[k])} subsets)" for k in sorted(by_k)])
        axis.grid(axis="y", linewidth=0.4, alpha=0.3)
    axis_r2.axhline(0.0, color="black", linewidth=0.8, alpha=0.5)
    figure.suptitle(
        "Layer-4 visible-position trajectory learning curve\n"
        "Fixed test: L03 + L04 (120 rows, identical for every fit); "
        f"training pool L01/L02/L05/L06; {len(ordered)} subsets",
        fontsize=10,
    )
    figure.text(
        0.5,
        0.015,
        "Point labels give the training frame count. Adjacent frames within a "
        "trajectory are strongly correlated, so frame counts overstate the "
        "independent sample size; k is the independent unit.",
        ha="center",
        fontsize=7.5,
        color="#444444",
    )
    figure.tight_layout(rect=(0, 0.06, 1, 0.94))
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    try:
        figure.savefig(temporary, format="png", dpi=160)
        os.link(temporary, path)
    finally:
        plt.close(figure)
        temporary.unlink(missing_ok=True)


def run_learning_curve(
    config: Mapping[str, Any], *, manifest_path: Path
) -> tuple[Path, Path, Path]:
    authority_rows = load_visible_authority(config)
    features, extracted_rows, extraction_manifest = _load_extracted_pooled(
        manifest_path, authority_rows
    )
    plans = build_subset_plan(authority_rows)
    receipt_root = _resolved(ROOT, config["storage"]["receipt_root"])
    subset_path = receipt_root / "learning_curve_subsets.json"
    result_path = receipt_root / "learning_curve.json"
    plot_path = receipt_root / "visible_position_learning_curve.png"
    if any(path.exists() for path in (subset_path, result_path, plot_path)):
        raise DiagnosticError("refusing to overwrite existing learning-curve artifacts")

    row_indices = {row["row_key"]: index for index, row in enumerate(authority_rows)}
    fixed_test_rows = [
        row for row in authority_rows if row["trajectory_label"] in FIXED_TEST_LABELS
    ]
    fixed_test_indices = [row_indices[row["row_key"]] for row in fixed_test_rows]
    test_features = features[fixed_test_indices]
    test_targets = np.asarray(
        [row["x_true_blocks"] for row in fixed_test_rows], dtype=np.float64
    )
    ridge_config = config["ridge"]
    results = []
    for plan in plans:
        labels = set(plan["training_trajectory_labels"])
        training_rows = [
            row for row in authority_rows if row["trajectory_label"] in labels
        ]
        training_indices = [row_indices[row["row_key"]] for row in training_rows]
        predictions, fit_record = fit_fixed_test_ridge(
            features[training_indices],
            np.asarray(
                [row["x_true_blocks"] for row in training_rows], dtype=np.float64
            ),
            [row["trajectory_label"] for row in training_rows],
            test_features,
            alpha_grid=ridge_config["alpha_grid"],
            seed=int(ridge_config["seed"]),
        )
        metrics = regression_metrics(test_targets.tolist(), predictions.tolist())
        if fit_record["scaler_training_row_count"] != len(training_rows):
            raise DiagnosticError(f"{plan['subset_id']}: scaler row count leaked")
        results.append(
            {
                **plan,
                "r2": metrics.r2,
                "mae": metrics.mae,
                "mse": metrics.mse,
                "prediction_sha256": _sha256_bytes(
                    predictions.astype("<f8", copy=False).tobytes(order="C")
                ),
                **fit_record,
            }
        )
    if len({row["fixed_test_sha256"] for row in results}) != 1:
        raise DiagnosticError(
            "learning-curve subsets did not use one identical test hash"
        )

    extraction_identity = {
        "manifest_path": str(manifest_path),
        "manifest_sha256": sha256_file(manifest_path),
        "run_id": extraction_manifest["run_id"],
        "eligible_row_keys_sha256": extraction_manifest["authority"][
            "eligible_row_keys_sha256"
        ],
    }
    subset_document = {
        "schema_version": "1.0",
        "artifact_version": "visible-position-learning-curve-subsets-v0.1",
        "fixed_test_trajectory_labels": list(FIXED_TEST_LABELS),
        "fixed_test_frame_count": EXPECTED_TEST_ROWS,
        "fixed_test_sha256": fixed_test_hash(authority_rows),
        "training_pool_trajectory_labels": list(TRAINING_POOL_LABELS),
        "training_pool_frame_count": EXPECTED_TRAINING_ROWS,
        "subset_count": len(plans),
        "subsets": list(plans),
        "extraction_identity": extraction_identity,
    }
    result_document = {
        "schema_version": "1.0",
        "artifact_version": "visible-position-learning-curve-v0.1",
        "generated_at": _now_iso(),
        "layer_idx": LAYER_IDX,
        "pooling_identity": MEAN_POOLING_IDENTITY,
        "feature_source": "freshly_extracted_layer4_mean_pool",
        "fixed_test_trajectory_labels": list(FIXED_TEST_LABELS),
        "fixed_test_frame_count": EXPECTED_TEST_ROWS,
        "fixed_test_sha256": fixed_test_hash(authority_rows),
        "alpha_grid": list(ridge_config["alpha_grid"]),
        "alpha_selection": "leave-one-training-trajectory-out",
        "scaler_fit_scope": "each_training_subset_only",
        "subset_count": len(results),
        "results": results,
        "extraction_identity": extraction_identity,
        "extracted_row_record_count": len(extracted_rows),
    }
    _write_json(subset_path, subset_document)
    _write_json(result_path, result_document)
    _save_learning_curve_plot(plot_path, results)
    return subset_path, result_path, plot_path


def token_grid_position(token_index: int) -> tuple[int, int]:
    """Map a flat visual-token index onto its verified 14x24 grid cell."""

    if not 0 <= token_index < TOKEN_COUNT:
        raise DiagnosticError(f"token index outside the frozen 336 set: {token_index}")
    return divmod(token_index, TOKEN_GRID_COLS)


def classify_token_result(
    pool_metrics: Mapping[str, Any],
    token_metrics: Mapping[str, Any],
    *,
    solver_pass: bool,
) -> str:
    """Apply the roadmap's conservative token-result table, nothing more."""

    if not solver_pass:
        return "INSUFFICIENT_TOKEN_EVIDENCE"
    if token_metrics["r2"] - pool_metrics["r2"] <= 0.0:
        return "LITTLE_OR_NO_TOKEN_GAIN"
    if all(
        token_metrics[f"{label}_r2"] > pool_metrics[f"{label}_r2"]
        for label in FIXED_TEST_LABELS
    ):
        return "CLEAR_TOKEN_GAIN"
    return "MIXED_TOKEN_GAIN"


def _split_indices(
    rows: Sequence[Mapping[str, Any]],
) -> tuple[np.ndarray, np.ndarray]:
    labels = np.array([row["trajectory_label"] for row in rows])
    train = np.flatnonzero(np.isin(labels, list(TRAINING_POOL_LABELS)))
    test = np.flatnonzero(np.isin(labels, list(FIXED_TEST_LABELS)))
    if train.size != EXPECTED_TRAINING_ROWS or test.size != EXPECTED_TEST_ROWS:
        raise DiagnosticError("token split is not the frozen 231/120 partition")
    if set(labels[train]) & set(labels[test]):
        raise DiagnosticError("token split leaked a trajectory across train/test")
    return train, test


def _scored_metrics(
    truth: np.ndarray, predictions: np.ndarray, test_labels: np.ndarray
) -> dict[str, Any]:
    metrics = regression_metrics(truth.tolist(), [float(v) for v in predictions])
    record: dict[str, Any] = {
        "r2": metrics.r2,
        "mae": metrics.mae,
        "mse": metrics.mse,
        "sample_count": metrics.sample_count,
    }
    for label in FIXED_TEST_LABELS:
        selection = test_labels == label
        per_layout = regression_metrics(
            truth[selection].tolist(),
            [float(v) for v in predictions[selection]],
        )
        record[f"{label}_r2"] = per_layout.r2
        record[f"{label}_mae"] = per_layout.mae
        record[f"{label}_sample_count"] = per_layout.sample_count
    return record


def check_solver_equivalence(
    train_features: np.ndarray,
    train_targets: np.ndarray,
    test_features: np.ndarray,
    *,
    alpha: float,
) -> dict[str, Any]:
    """Validate the dual ridge path against an independent primal reference.

    ``fit_ridge`` dispatches to the exact dual/sample-space system whenever
    p > n, so both the 2,048-dimension mean pool and the 688,128-dimension
    flattened fit use it and never form a p-by-p covariance matrix.  The primal
    closed form is computed here only because 2,048 features make a p-by-p
    solve tractable as a reference.
    """

    scaler = fit_standard_scaler(train_features)
    model = fit_ridge(train_features, train_targets, alpha=alpha, scaler=scaler)
    library = np.asarray(model.predict(test_features), dtype=np.float64)

    standardized_train = scaler.transform(train_features)
    standardized_test = scaler.transform(test_features)
    target_mean = float(np.asarray(train_targets, dtype=np.float64).mean())
    centered = np.asarray(train_targets, dtype=np.float64) - target_mean
    primal_weights = np.linalg.solve(
        standardized_train.T @ standardized_train
        + alpha * np.eye(standardized_train.shape[1]),
        standardized_train.T @ centered,
    )
    primal = standardized_test @ primal_weights + target_mean
    primal_difference = float(np.max(np.abs(library - primal)))

    scale = float(np.max(np.abs(library)))
    tolerance = 1e-6 * max(scale, 1.0)
    record = {
        "fixture": "layer4_mean_pool_2048d_training_rows",
        "library_path": "dual_sample_space",
        "alpha": float(alpha),
        "max_abs_prediction_difference_vs_independent_primal": primal_difference,
        "tolerance": tolerance,
        "tolerance_basis": "1e-6 * max(|prediction|, 1.0), float64 solve",
    }
    passed = primal_difference <= tolerance
    try:  # optional third-party cross-check; absence must not fail the run
        from sklearn.linear_model import Ridge
    except ImportError:
        record["max_abs_prediction_difference_vs_sklearn_cholesky"] = None
        record["sklearn_available"] = False
    else:
        reference = Ridge(alpha=alpha, fit_intercept=False, solver="cholesky")
        reference.fit(standardized_train, centered)
        sklearn_difference = float(
            np.max(
                np.abs(library - (reference.predict(standardized_test) + target_mean))
            )
        )
        record["max_abs_prediction_difference_vs_sklearn_cholesky"] = sklearn_difference
        record["sklearn_available"] = True
        passed = passed and sklearn_difference <= tolerance
    record["pass"] = bool(passed)
    return record


def _verified_token_chunk_paths(manifest: Mapping[str, Any]) -> tuple[Path, ...]:
    paths = []
    for chunk in manifest["chunks"]:
        meta = chunk["token_array"]
        path = Path(meta["path"])
        _require_file_hash(
            path, meta["sha256"], f"{chunk['trajectory_label']} token array"
        )
        paths.append(path)
    if len(paths) != len(TRAJECTORIES):
        raise DiagnosticError("token analysis requires six extraction chunks")
    return tuple(paths)


def _load_token_block(paths: Sequence[Path]) -> np.ndarray:
    block = np.concatenate(
        [np.load(path, mmap_mode="r", allow_pickle=False) for path in paths], axis=0
    )
    if (
        block.shape
        != (
            EXPECTED_ELIGIBLE_ROWS,
            TOKEN_COUNT,
            HIDDEN_WIDTH,
        )
        or block.dtype != TOKEN_DTYPE
    ):
        raise DiagnosticError("token block is not [351,336,2048] float16")
    return block


def _build_flattened_split(
    paths: Sequence[Path], train_index: np.ndarray, test_index: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Materialize the flattened split one row at a time to bound memory."""

    train = np.empty(
        (train_index.size, TOKEN_FLATTENED_FEATURE_COUNT), dtype=np.float64
    )
    test = np.empty((test_index.size, TOKEN_FLATTENED_FEATURE_COUNT), dtype=np.float64)
    train_slots = {int(value): position for position, value in enumerate(train_index)}
    test_slots = {int(value): position for position, value in enumerate(test_index)}
    offset = 0
    for path in paths:
        part = np.load(path, mmap_mode="r", allow_pickle=False)
        for local in range(part.shape[0]):
            absolute = offset + local
            flattened = np.asarray(part[local], dtype=np.float64).reshape(-1)
            if absolute in train_slots:
                train[train_slots[absolute]] = flattened
            else:
                test[test_slots[absolute]] = flattened
        offset += part.shape[0]
        del part
    if offset != EXPECTED_ELIGIBLE_ROWS:
        raise DiagnosticError("flattened split did not consume all 351 rows")
    return train, test


def _save_token_r2_map_plot(path: Path, positions: Sequence[Mapping[str, Any]]) -> None:
    if path.exists():
        raise DiagnosticError(f"refusing to overwrite existing artifact: {path}")
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as error:  # pragma: no cover - environment gate
        raise DiagnosticError("matplotlib is required for the token map") from error
    grid = np.full((TOKEN_GRID_ROWS, TOKEN_GRID_COLS), np.nan, dtype=np.float64)
    for record in positions:
        grid[record["grid_row"], record["grid_col"]] = record["held_out_r2"]
    if not np.isfinite(grid).all():
        raise DiagnosticError("token map has an unscored grid cell")
    values = grid.ravel()
    # Clip the colour scale to the positive dynamic range: a single strongly
    # negative position would otherwise wash out all decodable structure. The
    # clipping and the true minimum are stated on the figure itself.
    limit = float(values.max())
    minimum = float(values.min())
    best = max(positions, key=lambda record: record["held_out_r2"])

    figure, axis = plt.subplots(figsize=(11.5, 6.4))
    image = axis.imshow(
        grid, cmap="RdBu_r", vmin=-limit, vmax=limit, aspect="equal", origin="upper"
    )
    axis.set_xlabel(f"Token grid column (0-{TOKEN_GRID_COLS - 1})")
    axis.set_ylabel(f"Token grid row (0-{TOKEN_GRID_ROWS - 1})")
    axis.set_xticks(range(0, TOKEN_GRID_COLS, 2))
    axis.set_yticks(range(0, TOKEN_GRID_ROWS, 2))
    axis.set_xticks(np.arange(-0.5, TOKEN_GRID_COLS, 1), minor=True)
    axis.set_yticks(np.arange(-0.5, TOKEN_GRID_ROWS, 1), minor=True)
    axis.grid(which="minor", color="#ffffff", linewidth=0.4)
    axis.tick_params(which="minor", length=0)
    axis.scatter(
        [best["grid_col"]],
        [best["grid_row"]],
        marker="o",
        s=90,
        facecolors="none",
        edgecolors="#111111",
        linewidths=1.4,
    )
    bar = figure.colorbar(image, ax=axis, fraction=0.030, pad=0.02, extend="min")
    bar.set_label("Held-out R² (fixed test L03+L04, 120 rows)")
    axis.set_title(
        "Layer-4 token map: where visible-position information is most linearly "
        "decodable",
        fontsize=12,
    )
    axis.text(
        best["grid_col"] + 0.7,
        best["grid_row"] - 0.6,
        f"best: idx {best['token_index']} "
        f"(r{best['grid_row']},c{best['grid_col']}) "
        f"R²={best['held_out_r2']:.3f}",
        fontsize=7.5,
        color="#111111",
    )
    figure.text(
        0.5,
        0.075,
        "One independent ridge probe per token position (that position's 2048-d "
        "hidden vector). Identical train L01/L02/L05/L06 (231 rows) and fixed "
        "test L03/L04 (120 rows) for every position;",
        ha="center",
        fontsize=8,
        color="#444444",
    )
    figure.text(
        0.5,
        0.045,
        "training-only scaling and leave-one-training-trajectory-out alpha "
        f"selection. Grid {TOKEN_GRID_ROWS}x{TOKEN_GRID_COLS}={TOKEN_COUNT} from "
        "the 224x384 model-facing frame (VAE downsample 16).",
        ha="center",
        fontsize=8,
        color="#444444",
    )
    figure.text(
        0.5,
        0.013,
        f"Colour scale clipped to ±{limit:.2f} to show the positive range; "
        f"{int((values < -limit).sum())} positions fall below it, true minimum "
        f"{minimum:.2f}. Negative R² means worse than predicting the training "
        "mean.",
        ha="center",
        fontsize=7.5,
        color="#777777",
    )
    figure.tight_layout(rect=(0, 0.105, 1, 1))
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    try:
        figure.savefig(temporary, format="png", dpi=160)
        os.link(temporary, path)
    finally:
        plt.close(figure)
        temporary.unlink(missing_ok=True)


def run_token_analysis(
    config: Mapping[str, Any], *, manifest_path: Path
) -> tuple[Path, Path, Path]:
    """Matched mean-pool comparator, flattened token ridge, and 336-token map."""

    authority_rows = load_visible_authority(config)
    pooled, extracted_rows, extraction_manifest = _load_extracted_pooled(
        manifest_path, authority_rows
    )
    receipt_root = _resolved(ROOT, config["storage"]["receipt_root"])
    metrics_path = receipt_root / "token_probe_metrics.json"
    map_path = receipt_root / "token_spatial_map.json"
    figure_path = receipt_root / "visible_position_token_r2_map.png"
    if any(path.exists() for path in (metrics_path, map_path, figure_path)):
        raise DiagnosticError("refusing to overwrite existing token artifacts")

    train_index, test_index = _split_indices(extracted_rows)
    labels = np.array([row["trajectory_label"] for row in extracted_rows])
    targets = np.array(
        [float(row["x_true_blocks"]) for row in extracted_rows], dtype=np.float64
    )
    train_groups = [str(value) for value in labels[train_index]]
    train_targets = targets[train_index]
    test_targets = targets[test_index]
    test_labels = labels[test_index]
    ridge_config = config["ridge"]
    alpha_grid = list(ridge_config["alpha_grid"])
    seed = int(ridge_config["seed"])
    scored_test_identity = _canonical_sha256(
        [
            {
                "row_key": extracted_rows[index]["row_key"],
                "x_true_blocks": float(targets[index]),
            }
            for index in test_index
        ]
    )

    def fit_and_score(
        train_features: np.ndarray, test_features: np.ndarray
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        predictions, record = fit_fixed_test_ridge(
            train_features,
            train_targets,
            train_groups,
            test_features,
            alpha_grid=alpha_grid,
            seed=seed,
        )
        return (
            _scored_metrics(
                test_targets, np.asarray(predictions, dtype=np.float64), test_labels
            ),
            record,
        )

    # Part A - matched mean-pool comparator refit from the new layer-4 authority.
    pooled = np.asarray(pooled, dtype=np.float64)
    pool_train = np.ascontiguousarray(pooled[train_index])
    pool_test = np.ascontiguousarray(pooled[test_index])
    pool_metrics, pool_record = fit_and_score(pool_train, pool_test)

    solver = check_solver_equivalence(
        pool_train,
        train_targets,
        pool_test,
        alpha=float(pool_record["selected_alpha"]),
    )
    del pooled

    # Part C - one probe per verified token position.
    token_paths = _verified_token_chunk_paths(extraction_manifest)
    tokens = _load_token_block(token_paths)
    positions: list[dict[str, Any]] = []
    for token_index in range(TOKEN_COUNT):
        grid_row, grid_col = token_grid_position(token_index)
        feature = np.asarray(tokens[:, token_index, :], dtype=np.float64)
        metrics, record = fit_and_score(
            np.ascontiguousarray(feature[train_index]),
            np.ascontiguousarray(feature[test_index]),
        )
        positions.append(
            {
                "token_index": token_index,
                "grid_row": grid_row,
                "grid_col": grid_col,
                "held_out_r2": metrics["r2"],
                "held_out_mae": metrics["mae"],
                "selected_alpha": record["selected_alpha"],
                "L03_r2": metrics["L03_r2"],
                "L04_r2": metrics["L04_r2"],
                "scaler_training_row_count": record["scaler_training_row_count"],
                "scaler_fit_scope": record["scaler_fit_scope"],
                "selection_policy": record["selection_policy"],
                "inner_fold_count": record["inner_fold_count"],
                "scored_test_identity_sha256": scored_test_identity,
            }
        )
    del tokens
    if len(positions) != TOKEN_COUNT:
        raise DiagnosticError("token map must score all 336 positions")

    # Part B - flattened token ridge; fit_ridge takes the exact dual path.
    train_features, test_features = _build_flattened_split(
        token_paths, train_index, test_index
    )
    token_metrics, token_record = fit_and_score(train_features, test_features)
    del train_features, test_features

    delta_r2 = token_metrics["r2"] - pool_metrics["r2"]
    token_class = classify_token_result(
        pool_metrics, token_metrics, solver_pass=bool(solver["pass"])
    )

    r2_values = np.array(
        [record["held_out_r2"] for record in positions], dtype=np.float64
    )
    ranked = sorted(positions, key=lambda record: record["held_out_r2"], reverse=True)

    def _brief(record: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "token_index": record["token_index"],
            "grid_row": record["grid_row"],
            "grid_col": record["grid_col"],
            "held_out_r2": record["held_out_r2"],
        }

    provenance = {
        "extraction_manifest_path": str(manifest_path.relative_to(ROOT)),
        "extraction_manifest_sha256": sha256_file(manifest_path),
        "extraction_run_id": extraction_manifest["run_id"],
        "layer_idx": LAYER_IDX,
        "hook_site": HOOK_SITE,
        "base_head": config["base_head"],
        "config_path": str(DEFAULT_CONFIG.relative_to(ROOT)),
        "config_sha256": sha256_file(DEFAULT_CONFIG),
        "analysis_code_path": str(Path(__file__).resolve().relative_to(ROOT)),
        "analysis_code_sha256": sha256_file(Path(__file__).resolve()),
        "analysis_mode": "token-analysis",
        "runner_version": RUNNER_VERSION,
        "interpreter": sys.executable,
        "numpy_version": np.__version__,
    }
    split = {
        "train_trajectory_labels": list(TRAINING_POOL_LABELS),
        "train_trajectory_ids": sorted(
            {extracted_rows[index]["trajectory_id"] for index in train_index}
        ),
        "train_row_count": int(train_index.size),
        "test_trajectory_labels": list(FIXED_TEST_LABELS),
        "test_trajectory_ids": sorted(
            {extracted_rows[index]["trajectory_id"] for index in test_index}
        ),
        "test_row_count": int(test_index.size),
        "train_test_trajectory_overlap_count": 0,
        "fixed_test_sha256": fixed_test_hash(authority_rows),
        "scored_test_identity_sha256": scored_test_identity,
        "alpha_grid": alpha_grid,
        "alpha_selection": "leave-one-training-trajectory-out",
        "scaler_fit_scope": "training_rows_only",
        "seed": seed,
    }

    _write_json(
        metrics_path,
        {
            "schema_version": "1.0",
            "artifact_version": "visible-position-token-probe-metrics-v0.1",
            "generated_at": _now_iso(),
            "mean_pool_comparator_source": (
                "REFIT_FROM_NEW_VERIFIED_LAYER4_EXTRACTION"
            ),
            "historical_oof_reuse": False,
            "historical_oof_reuse_reason": "PAYLOAD_UNAVAILABLE",
            "split": split,
            "mean_pool": {**pool_metrics, **pool_record},
            "token_flattened": {
                **token_metrics,
                **token_record,
                "feature_count": TOKEN_FLATTENED_FEATURE_COUNT,
                "flatten_order": (
                    "row-major over (token_index, hidden_unit); token order is "
                    "the verified extraction order"
                ),
            },
            "delta": {
                "delta_r2": delta_r2,
                "delta_mae": token_metrics["mae"] - pool_metrics["mae"],
                "L03_delta_r2": token_metrics["L03_r2"] - pool_metrics["L03_r2"],
                "L04_delta_r2": token_metrics["L04_r2"] - pool_metrics["L04_r2"],
            },
            "token_result_class": token_class,
            "solver": solver,
            "provenance": provenance,
        },
    )
    _write_json(
        map_path,
        {
            "schema_version": "1.0",
            "artifact_version": "visible-position-token-spatial-map-v0.1",
            "generated_at": _now_iso(),
            "description": (
                "where visible-position information is most linearly decodable"
            ),
            "grid": {
                "rows": TOKEN_GRID_ROWS,
                "cols": TOKEN_GRID_COLS,
                "token_count": TOKEN_COUNT,
                "index_rule": "token_index = grid_row * cols + grid_col",
                "geometry_authority": (
                    "adapter _coerce_visual_rows pins the VAE output to "
                    "(frames, 14, 24) reshaped row-major to (frames, 336); the "
                    "VQ encoder maps the 224x384 model-facing frame to a 14x24 "
                    "latent"
                ),
                "model_facing_height": 224,
                "model_facing_width": 384,
                "vae_downsample_factor": 16,
            },
            "split": split,
            "summary": {
                "token_r2_max": float(r2_values.max()),
                "token_r2_median": float(np.median(r2_values)),
                "token_r2_min": float(r2_values.min()),
                "token_r2_mean": float(r2_values.mean()),
                "positive_r2_token_count": int((r2_values > 0).sum()),
                "top_10_token_positions": [_brief(record) for record in ranked[:10]],
                "bottom_10_token_positions": [
                    _brief(record) for record in ranked[-10:]
                ],
            },
            "positions": positions,
            "provenance": provenance,
        },
    )
    _save_token_r2_map_plot(figure_path, positions)
    return metrics_path, map_path, figure_path


NEXT_SCIENTIFIC_DIRECTION = (
    "Increase independent visible/no-wall trajectory and layout coverage, then "
    "evaluate the token-preserving visible-position readout on a new untouched "
    "grouped evaluation authority before deciding whether mean pooling should "
    "be replaced for any future hidden-state study."
)
PACKAGE_ARTIFACTS = (
    "diagnostic_receipt.json",
    "learning_curve.json",
    "learning_curve_subsets.json",
    "unpooled_activation_manifest.json",
    "token_probe_metrics.json",
    "token_spatial_map.json",
    "diagnostic_adjudication.json",
    "provenance.json",
    "visible_position_learning_curve.png",
    "visible_position_token_r2_map.png",
)


def classify_learning_curve(results: Sequence[Mapping[str, Any]]) -> str:
    """Descriptive roadmap class only; no significance gate is applied."""

    by_k: dict[int, list[float]] = {}
    for row in results:
        by_k.setdefault(int(row["k_trajectories"]), []).append(float(row["r2"]))
    if len(by_k) < 2:
        return "INSUFFICIENT_INDEPENDENT_TRAINING_SIZES"
    sizes = sorted(by_k)
    medians = [float(np.median(by_k[size])) for size in sizes]
    spread = max(
        (max(values) - min(values)) for values in by_k.values() if len(values) > 1
    )
    movement = max(medians) - min(medians)
    if spread > movement:
        return "HIGH_TRAJECTORY_VARIANCE"
    if all(later > earlier for earlier, later in zip(medians, medians[1:])):
        return "CLEAR_UPWARD_TREND"
    if medians[-1] > medians[0]:
        return "WEAK_UPWARD_TREND"
    return "PLATEAU"


def run_finalize(config: Mapping[str, Any]) -> tuple[Path, Path, Path]:
    """Assemble the adjudication, provenance, and receipt for the package."""

    receipt_root = _resolved(ROOT, config["storage"]["receipt_root"])
    adjudication_path = receipt_root / "diagnostic_adjudication.json"
    provenance_path = receipt_root / "provenance.json"
    receipt_path = receipt_root / "diagnostic_receipt.json"
    if any(
        path.exists() for path in (adjudication_path, provenance_path, receipt_path)
    ):
        raise DiagnosticError("refusing to overwrite existing package artifacts")

    def _read(name: str) -> dict[str, Any]:
        path = receipt_root / name
        if not path.is_file():
            raise DiagnosticError(f"package is missing a required input: {path}")
        return json.loads(path.read_text(encoding="utf-8"))

    extraction = _read("unpooled_activation_manifest.json")
    curve = _read("learning_curve.json")
    token_metrics = _read("token_probe_metrics.json")
    token_map = _read("token_spatial_map.json")

    curve_class = classify_learning_curve(curve["results"])
    token_class = token_metrics["token_result_class"]
    # DATA_LIMITATION_PLAUSIBLE is true only for a clear coherent upward
    # pattern, false for a plateau, and null for weak or high-variance or
    # insufficient evidence.
    if curve_class == "CLEAR_UPWARD_TREND":
        data_limitation_plausible: bool | None = True
    elif curve_class == "PLATEAU":
        data_limitation_plausible = False
    else:
        data_limitation_plausible = None

    if curve_class == "CLEAR_UPWARD_TREND" and token_class == "CLEAR_TOKEN_GAIN":
        final_diagnosis = "POOLING_BOTTLENECK_AND_DATA_LIMITATION"
    elif token_class == "CLEAR_TOKEN_GAIN":
        final_diagnosis = "POOLING_BOTTLENECK_SUPPORTED"
    else:
        final_diagnosis = "INSUFFICIENT_EVIDENCE"

    by_k: dict[str, Any] = {}
    for row in curve["results"]:
        by_k.setdefault(str(row["k_trajectories"]), []).append(float(row["r2"]))
    curve_medians = {
        size: float(np.median(values)) for size, values in sorted(by_k.items())
    }

    adjudication = {
        "schema_version": "1.0",
        "artifact_version": "visible-position-diagnostic-adjudication-v0.1",
        "generated_at": _now_iso(),
        "ORIGINAL_MVP_RESULT_MODIFIED": False,
        "LAYER_SELECTION_STATUS": (
            "EXPLORATORY_PRESELECTED_FROM_EXISTING_POSITIVE_CONTROL"
        ),
        "FINAL_DIAGNOSIS": final_diagnosis,
        "NEXT_SCIENTIFIC_DIRECTION": NEXT_SCIENTIFIC_DIRECTION,
        "inputs": {
            "DATA_CURVE": curve_class,
            "DATA_LIMITATION_PLAUSIBLE": data_limitation_plausible,
            "TOKEN_RESULT": token_class,
        },
        "findings_preserved": [
            {
                "finding": "trajectory_scaling",
                "statement": (
                    "Current trajectory scaling does not show a coherent upward "
                    "trend and is dominated by trajectory composition."
                ),
                "evidence": {
                    "fixed_test_r2_median_by_k": curve_medians,
                    "subset_count": len(curve["results"]),
                    "learning_curve_class": curve_class,
                },
            },
            {
                "finding": "token_preserving_readout",
                "statement": (
                    "Token-preserving decoding materially improves aggregate "
                    "held-out R2 over mean pooling, but the improvement "
                    "reverses direction across the two held-out layouts, so a "
                    "stable pooling bottleneck is not established."
                ),
                "evidence": {
                    "mean_pool_r2": token_metrics["mean_pool"]["r2"],
                    "token_flattened_r2": token_metrics["token_flattened"]["r2"],
                    "delta_r2": token_metrics["delta"]["delta_r2"],
                    "L03_delta_r2": token_metrics["delta"]["L03_delta_r2"],
                    "L04_delta_r2": token_metrics["delta"]["L04_delta_r2"],
                    "token_r2_max": token_map["summary"]["token_r2_max"],
                    "positive_r2_token_count": token_map["summary"][
                        "positive_r2_token_count"
                    ],
                    "token_result_class": token_class,
                },
            },
        ],
        "interpretation_note": (
            "This is not a failed token probe. The token diagnostic found "
            "substantial exploratory evidence that spatial token identity can "
            "matter for visible-position readout; under the current authority "
            "that evidence is layout-dependent, which is why the adjudication "
            "is INSUFFICIENT_EVIDENCE rather than a negative result."
        ),
        "scope_limitations": [
            "Layer 4 was preselected from an existing positive control, not "
            "searched under this authority.",
            "Two held-out layouts (L03, L04) cannot separate layout identity "
            "from sample size.",
            "Adjacent frames within a trajectory are correlated, so frame "
            "counts overstate independent sample size.",
        ],
        "not_rerun": ["U1", "U2"],
    }

    _write_json(adjudication_path, adjudication)

    authority = dict(config["authority"])
    provenance = {
        "schema_version": "1.0",
        "artifact_version": "visible-position-diagnostic-provenance-v0.1",
        "generated_at": _now_iso(),
        "ORIGINAL_MVP_RESULT_MODIFIED": False,
        "frozen_base_sha": config["base_head"],
        "exploration_branch": "exploration/mentor-visible-position-diagnostics-v0-1",
        "experiment_id": config["experiment_id"],
        "scientific_scope": {
            "layer_idx": LAYER_IDX,
            "hook_site": HOOK_SITE,
            "visual_token_count": TOKEN_COUNT,
            "token_grid_rows": TOKEN_GRID_ROWS,
            "token_grid_cols": TOKEN_GRID_COLS,
            "hidden_width": HIDDEN_WIDTH,
            "eligible_row_count": EXPECTED_ELIGIBLE_ROWS,
            "pooling_identity": MEAN_POOLING_IDENTITY,
        },
        "layer_selection_status": (
            "EXPLORATORY_PRESELECTED_FROM_EXISTING_POSITIVE_CONTROL"
        ),
        "layer_selection_limitation": (
            "Layer 4 was carried over from an existing positive control; no "
            "layer search was performed under this authority, so the layer "
            "choice is exploratory and not itself evidence."
        ),
        "split": {
            "fixed_test_trajectory_labels": list(FIXED_TEST_LABELS),
            "fixed_test_trajectory_ids": [
                record[2] for record in TRAJECTORIES if record[0] in FIXED_TEST_LABELS
            ],
            "fixed_test_row_count": EXPECTED_TEST_ROWS,
            "training_pool_trajectory_labels": list(TRAINING_POOL_LABELS),
            "training_pool_trajectory_ids": [
                record[2]
                for record in TRAJECTORIES
                if record[0] in TRAINING_POOL_LABELS
            ],
            "training_pool_row_count": EXPECTED_TRAINING_ROWS,
            "fixed_test_sha256": token_metrics["split"]["fixed_test_sha256"],
        },
        "row_authority": authority,
        "frozen_preprocessing_authority": {
            "preprocessed_frame_manifest_path": authority[
                "preprocessed_frame_manifest_path"
            ],
            "preprocessed_frame_manifest_sha256": authority[
                "preprocessed_frame_manifest_sha256"
            ],
            "preprocessing_identity": extraction["runtime_identity"][
                "preprocessing_identity"
            ],
            "preprocess_hash": extraction["runtime_identity"]["preprocess_hash"],
            "person_c_canonical_media_commit": authority[
                "person_c_canonical_media_commit"
            ],
        },
        "extraction_run": {
            "run_id": extraction["run_id"],
            "external_root": extraction["external_root"],
            "manifest_path": "unpooled_activation_manifest.json",
            "manifest_sha256": sha256_file(
                receipt_root / "unpooled_activation_manifest.json"
            ),
        },
        "checkpoint": {
            "checkpoint_sha256": extraction["runtime_identity"]["checkpoint_sha256"],
            "model_config_sha256": extraction["runtime_identity"][
                "model_config_sha256"
            ],
            "vae_config_sha256": extraction["runtime_identity"]["vae_config_sha256"],
            "vae_checkpoint_sha256": extraction["runtime_identity"][
                "vae_checkpoint_sha256"
            ],
            "mineworld_source_revision": extraction["runtime_identity"][
                "mineworld_source_revision"
            ],
            "tokenization_profile": extraction["runtime_identity"][
                "tokenization_profile"
            ],
        },
        "durable_analysis_code": {
            "path": str(Path(__file__).resolve().relative_to(ROOT)),
            "sha256": sha256_file(Path(__file__).resolve()),
            "runner_version": RUNNER_VERSION,
            "config_path": str(DEFAULT_CONFIG.relative_to(ROOT)),
            "config_sha256": sha256_file(DEFAULT_CONFIG),
            "modes": ["extract", "learning-curve", "token-analysis", "finalize"],
        },
        # provenance.json and diagnostic_receipt.json are written after this
        # map is sealed, so they cannot hash themselves; every other package
        # artifact is bound here.
        "artifacts": {
            name: {
                "sha256": sha256_file(receipt_root / name),
                "byte_size": (receipt_root / name).stat().st_size,
            }
            for name in PACKAGE_ARTIFACTS
            if (receipt_root / name).is_file()
        },
    }
    _write_json(provenance_path, provenance)

    receipt = {
        "schema_version": "1.0",
        "artifact_version": "visible-position-diagnostic-receipt-v0.1",
        "generated_at": _now_iso(),
        "experiment_id": config["experiment_id"],
        "frozen_base_sha": config["base_head"],
        "exploration_branch": "exploration/mentor-visible-position-diagnostics-v0-1",
        "ORIGINAL_MVP_RESULT_MODIFIED": False,
        "diagnostic_1_learning_curve": {
            "class": curve_class,
            "data_limitation_plausible": data_limitation_plausible,
            "subset_count": len(curve["results"]),
            "fixed_test_r2_median_by_k": curve_medians,
        },
        "diagnostic_2_token": {
            "class": token_class,
            "mean_pool_r2": token_metrics["mean_pool"]["r2"],
            "mean_pool_mae": token_metrics["mean_pool"]["mae"],
            "token_flattened_r2": token_metrics["token_flattened"]["r2"],
            "token_flattened_mae": token_metrics["token_flattened"]["mae"],
            "delta_r2": token_metrics["delta"]["delta_r2"],
            "delta_mae": token_metrics["delta"]["delta_mae"],
            "L03_delta_r2": token_metrics["delta"]["L03_delta_r2"],
            "L04_delta_r2": token_metrics["delta"]["L04_delta_r2"],
            "spatial_token_count": token_map["grid"]["token_count"],
            "token_grid": f"{TOKEN_GRID_ROWS}x{TOKEN_GRID_COLS}",
            "token_r2_max": token_map["summary"]["token_r2_max"],
            "token_r2_median": token_map["summary"]["token_r2_median"],
            "token_r2_min": token_map["summary"]["token_r2_min"],
            "positive_r2_token_count": token_map["summary"]["positive_r2_token_count"],
            "solver_equivalence_pass": token_metrics["solver"]["pass"],
        },
        "FINAL_DIAGNOSIS": final_diagnosis,
        "NEXT_SCIENTIFIC_DIRECTION": NEXT_SCIENTIFIC_DIRECTION,
        "package_files": list(PACKAGE_ARTIFACTS),
    }

    _write_json(receipt_path, receipt)
    return adjudication_path, provenance_path, receipt_path


def _default_manifest(config: Mapping[str, Any]) -> Path:
    return _resolved(ROOT, config["storage"]["receipt_root"]) / (
        "unpooled_activation_manifest.json"
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=("extract", "learning-curve", "token-analysis", "finalize"),
        required=True,
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--run-id")
    parser.add_argument("--frame-payload-root", type=Path)
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args(argv)
    config = load_config(args.config)
    if args.mode == "extract":
        if not args.run_id:
            parser.error("--mode extract requires --run-id")
        payload_root = args.frame_payload_root or Path(
            config["storage"]["frozen_frame_payload_root"]
        )
        receipt = run_extract(
            config, run_id=args.run_id, frame_payload_root=payload_root
        )
        print(json.dumps({"status": "COMPLETE", "manifest": str(receipt)}, indent=2))
        return 0
    if args.run_id or args.frame_payload_root:
        parser.error("--run-id/--frame-payload-root are extract-mode arguments")
    if args.mode == "finalize":
        outputs = run_finalize(config)
        print(
            json.dumps(
                {"status": "COMPLETE", "outputs": [str(path) for path in outputs]},
                indent=2,
            )
        )
        return 0
    manifest_path = args.manifest or _default_manifest(config)
    if args.mode == "token-analysis":
        outputs = run_token_analysis(config, manifest_path=manifest_path)
        print(
            json.dumps(
                {"status": "COMPLETE", "outputs": [str(path) for path in outputs]},
                indent=2,
            )
        )
        return 0
    outputs = run_learning_curve(config, manifest_path=manifest_path)
    print(
        json.dumps(
            {"status": "COMPLETE", "outputs": [str(path) for path in outputs]}, indent=2
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
