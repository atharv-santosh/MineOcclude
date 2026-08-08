"""Real 66-cell production U1/U2 analysis.

This module is the narrow production successor to the historical ten-pilot
Step 4.1 implementation.  It consumes the already materialized activation
matrix and Person D prediction manifest, fits only Person B's frozen OOF ridge
probe, and applies the already frozen U1/U2 metrics and thresholds.  It does
not extract activations, regenerate folds or baselines, inspect U4, or attempt
the blocked U3 reveal analysis.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import random
import shutil
import subprocess
import tempfile
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from mineocclude.analysis.step4_1_final_comparison_v0_1 import (
    shared_sign_flip_max_t,
)
from mineocclude.analysis.step4_1_final_contract_v0_1 import (
    qualifying_layer_bands,
)
from mineocclude.metrics.resampling import bootstrap_confidence_interval
from mineocclude.metrics.u1_mean import regression_metrics
from mineocclude.metrics.u2_calibration import (
    calibration_metrics,
    partial_correlation_controlling_tau,
    reconstruct_sigma,
)
from mineocclude.probes.ridge import RidgeOOFResult, fit_ridge_oof

RUN_ID = "mineocclude-run-ea6169430d693f8adcd16a23a62c4422"
STARTING_AUTHORITY = "664be52c22be6b3161f0c10f4ccd73bfb277c5a6"
BRANCH = "integration/mvp-final"
LAYERS = tuple(range(20))
FOLD_COUNT = 5
ELIGIBLE_FRAME_COUNT = 662
ELIGIBLE_LAYER_ROW_COUNT = 13_240
HIDDEN_FRAME_COUNT = 311
NO_WALL_FRAME_COUNT = 351
VECTOR_WIDTH = 2_048
HOOK_SITE = "decoder_layer_output_residual_stream"

SCOPE_HIDDEN_MEAN = 1
SCOPE_HIDDEN_SPREAD = 2
SCOPE_VISIBLE_NO_WALL = 4

RIDGE_ALPHA_GRID = (0.1, 1.0, 10.0, 100.0)
RIDGE_INNER_FOLD_COUNT = 4
SPLIT_SEED = 20260719
PERMUTATION_COUNT = 999
PERMUTATION_SEED = 20260720
BOOTSTRAP_COUNT = 2000
BOOTSTRAP_SEED = 20260721
BOOTSTRAP_COVERAGE = 0.95
COVERAGE_LEVELS = (0.5, 0.8, 0.95)

U1_BASELINES = (
    "last_seen",
    "constant_velocity",
    "explicit_feature",
    "raw_pixel",
    "grouped_shuffled",
)
U1_PRIMARY_BASELINES = ("last_seen", "grouped_shuffled")
U2_BASELINES = (
    "time_only",
    "visible_history_q",
    "known_q_analytic",
    "grouped_shuffled",
)
U2_PRIMARY_BASELINES = ("time_only", "visible_history_q")
RESULT_FILENAMES = (
    "execution_receipt.json",
    "final_verdict.json",
    "fit_provenance.json",
    "oof_prediction_manifest.json",
    "scientific_results.json",
    "sha256_inventory.json",
)

READINESS_RECEIPT_SHA256 = (
    "19ddd379925b0c9cd226f284933db26cac7cc6febff02e2ebd35a840927654d7"
)
ANALYSIS_READY_MANIFEST_SHA256 = (
    "6e56bb6577312efe5efa7d9ffb1e065b04fd592bf0a44620940003d46a8982a7"
)
ACTIVATION_VECTORS_SHA256 = (
    "57d9300055a49e85f8b98bd98367caf65092a37107e4c98638b588fb876032c7"
)
SAMPLE_METADATA_SHA256 = (
    "b41d29b046b1245626d4e7ba2d5befddf3f774cb2039cfce057a248ef1c21b40"
)
D_PREDICTION_MANIFEST_SHA256 = (
    "ffd8f8316f8d3fd74e8ca441dda6f9f45d4d05c7834496abc461a76b97337ea7"
)
D_BASELINE_METRICS_SHA256 = (
    "cecaf081e3b320043419106686222c1f9508d13d125ce4055043d1e57e3254f5"
)
D_HANDOFF_SHA256 = "932a2d35a9739035bcb812eefcc6e2af728252baa0a8f08e9843293e6d1a8684"
ANALYSIS_CONFIG_SHA256 = (
    "b2e12e7049e0494c756be442a4f300cbc7dc0a6e262deecf682f1354e887f0ab"
)
ACTIVATION_INDEX_SHA256 = (
    "b5f97728bf4bcf957805f2664afbb53481d61db16318159cb0df6d8654c2f571"
)


class ProductionAnalysisError(RuntimeError):
    """Raised when production analysis cannot continue without changing scope."""


@dataclass(frozen=True)
class ProductionPaths:
    repository_root: Path
    analysis_ready_root: Path
    external_output_root: Path
    git_output_root: Path


@dataclass(frozen=True)
class LoadedInputs:
    vectors: np.ndarray
    metadata: np.ndarray
    hidden_indices_by_layer: Mapping[int, np.ndarray]
    hidden_metadata: np.ndarray
    d_rows: Mapping[tuple[str, str, str, int], Mapping[str, Any]]
    source_hashes: Mapping[str, str]
    source_commit: str


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_json_bytes(document: Any) -> bytes:
    try:
        text = json.dumps(
            document,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError) as error:
        raise ProductionAnalysisError(f"Result is not strict JSON: {error}") from error
    return (text + "\n").encode("utf-8")


def _load_json(path: Path, *, expected_sha256: str, label: str) -> Mapping[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ProductionAnalysisError(f"{label} is missing or a symlink: {path}")
    if _sha256_file(path) != expected_sha256:
        raise ProductionAnalysisError(f"{label} SHA-256 differs: {path}")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ProductionAnalysisError(f"Could not decode {label}: {error}") from error
    if not isinstance(document, Mapping):
        raise ProductionAnalysisError(f"{label} is not a JSON object")
    return document


def _git(repository: Path, *args: str) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=repository,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise ProductionAnalysisError(f"Git validation failed: {error}") from error
    return result.stdout.strip()


def _validate_repository(repository: Path) -> str:
    if _git(repository, "branch", "--show-current") != BRANCH:
        raise ProductionAnalysisError(f"Execution requires branch {BRANCH}")
    if _git(repository, "status", "--porcelain"):
        raise ProductionAnalysisError("Execution requires a clean worktree")
    try:
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", STARTING_AUTHORITY, "HEAD"],
            cwd=repository,
            check=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError as error:
        raise ProductionAnalysisError(
            "Required starting authority is not an ancestor of HEAD"
        ) from error
    return _git(repository, "rev-parse", "HEAD")


def _same_float_field(left: np.ndarray, right: np.ndarray) -> bool:
    return bool(np.array_equal(left, right, equal_nan=True))


def _validate_analysis_matrix(
    vectors: np.ndarray, metadata: np.ndarray
) -> tuple[dict[int, np.ndarray], np.ndarray]:
    if vectors.shape != (ELIGIBLE_LAYER_ROW_COUNT, VECTOR_WIDTH):
        raise ProductionAnalysisError(
            f"Activation vector shape differs: {vectors.shape}"
        )
    if vectors.dtype != np.dtype("float32") or not np.isfinite(vectors).all():
        raise ProductionAnalysisError("Activation vectors are not finite float32")
    if metadata.shape != (ELIGIBLE_LAYER_ROW_COUNT,) or metadata.dtype.names is None:
        raise ProductionAnalysisError("Metadata shape or dtype differs")
    required_fields = {
        "trajectory_id",
        "global_model_frame_idx",
        "layer_idx",
        "mu_oracle_blocks",
        "log_sigma_oracle",
        "log_sigma_available",
        "sigma_oracle_blocks",
        "x_true_blocks",
        "tau_seconds",
        "last_visible_position_blocks",
        "elapsed_hidden_frames",
        "context_fraction",
        "speed_blocks_per_second",
        "q_blocks_squared_per_second",
        "layout_id",
        "control_type",
        "admission_stratum",
        "fold_idx",
        "scope_mask",
    }
    if not required_fields.issubset(metadata.dtype.names):
        missing = sorted(required_fields - set(metadata.dtype.names))
        raise ProductionAnalysisError(f"Metadata fields are missing: {missing}")
    keys = {
        (
            str(row["trajectory_id"]),
            int(row["global_model_frame_idx"]),
            int(row["layer_idx"]),
        )
        for row in metadata
    }
    if len(keys) != ELIGIBLE_LAYER_ROW_COUNT:
        raise ProductionAnalysisError("Analysis matrix has duplicate row identities")
    if set(int(value) for value in np.unique(metadata["layer_idx"])) != set(LAYERS):
        raise ProductionAnalysisError("Layer universe differs from 0..19")

    by_layer: dict[int, np.ndarray] = {}
    frame_universe: tuple[tuple[str, int], ...] | None = None
    layer_zero: np.ndarray | None = None
    compare_fields = (
        "trajectory_id",
        "global_model_frame_idx",
        "mu_oracle_blocks",
        "log_sigma_oracle",
        "log_sigma_available",
        "sigma_oracle_blocks",
        "x_true_blocks",
        "tau_seconds",
        "last_visible_position_blocks",
        "elapsed_hidden_frames",
        "context_fraction",
        "speed_blocks_per_second",
        "q_blocks_squared_per_second",
        "layout_id",
        "control_type",
        "admission_stratum",
        "fold_idx",
        "scope_mask",
    )
    for layer in LAYERS:
        indices = np.flatnonzero(metadata["layer_idx"] == layer)
        if len(indices) != ELIGIBLE_FRAME_COUNT:
            raise ProductionAnalysisError(f"Layer {layer} does not have 662 rows")
        current = metadata[indices]
        frames = tuple(
            (str(row["trajectory_id"]), int(row["global_model_frame_idx"]))
            for row in current
        )
        if len(set(frames)) != ELIGIBLE_FRAME_COUNT:
            raise ProductionAnalysisError(f"Layer {layer} has duplicate frames")
        if frame_universe is None:
            frame_universe = frames
            layer_zero = current
        elif frames != frame_universe:
            raise ProductionAnalysisError(
                "Layers do not share one ordered frame universe"
            )
        assert layer_zero is not None
        for field in compare_fields:
            left = current[field]
            right = layer_zero[field]
            accepted = (
                _same_float_field(left, right)
                if left.dtype.kind == "f"
                else bool(np.array_equal(left, right))
            )
            if not accepted:
                raise ProductionAnalysisError(
                    f"Layer-invariant metadata differs at layer {layer}/{field}"
                )
        by_layer[layer] = indices

    assert layer_zero is not None
    hidden_mask = (layer_zero["scope_mask"] & SCOPE_HIDDEN_MEAN) != 0
    spread_mask = (layer_zero["scope_mask"] & SCOPE_HIDDEN_SPREAD) != 0
    no_wall_mask = (layer_zero["scope_mask"] & SCOPE_VISIBLE_NO_WALL) != 0
    if not np.array_equal(hidden_mask, spread_mask):
        raise ProductionAnalysisError("U1 and U2 hidden frame universes differ")
    if (
        int(hidden_mask.sum()) != HIDDEN_FRAME_COUNT
        or int(no_wall_mask.sum()) != NO_WALL_FRAME_COUNT
        or bool(np.any(hidden_mask & no_wall_mask))
        or not bool(np.all(hidden_mask | no_wall_mask))
    ):
        raise ProductionAnalysisError("Hidden/no-wall scope accounting differs")
    hidden = layer_zero[hidden_mask]
    finite_fields = (
        "mu_oracle_blocks",
        "log_sigma_oracle",
        "sigma_oracle_blocks",
        "x_true_blocks",
        "tau_seconds",
        "last_visible_position_blocks",
        "context_fraction",
        "speed_blocks_per_second",
        "q_blocks_squared_per_second",
    )
    for field in finite_fields:
        if not np.isfinite(hidden[field]).all():
            raise ProductionAnalysisError(f"Hidden metadata field {field} is nonfinite")
    if not bool(np.all(hidden["log_sigma_available"])):
        raise ProductionAnalysisError("A hidden U2 row lacks log sigma")
    if not bool(np.all(hidden["sigma_oracle_blocks"] > 0.0)):
        raise ProductionAnalysisError("A hidden U2 oracle spread is not positive")
    if set(int(value) for value in np.unique(hidden["fold_idx"])) != set(
        range(FOLD_COUNT)
    ):
        raise ProductionAnalysisError("Hidden rows do not populate all five folds")
    layout_fold: dict[str, int] = {}
    trajectory_fold: dict[str, int] = {}
    for row in layer_zero:
        layout = str(row["layout_id"])
        trajectory = str(row["trajectory_id"])
        fold = int(row["fold_idx"])
        if layout_fold.setdefault(layout, fold) != fold:
            raise ProductionAnalysisError("A layout crosses outer folds")
        if trajectory_fold.setdefault(trajectory, fold) != fold:
            raise ProductionAnalysisError("A trajectory crosses outer folds")
    if len(layout_fold) != 6:
        raise ProductionAnalysisError("Expected exactly six production layouts")

    hidden_by_layer = {
        layer: indices[hidden_mask] for layer, indices in by_layer.items()
    }
    return hidden_by_layer, hidden


def _load_d_rows(
    document: Mapping[str, Any], hidden_metadata: np.ndarray
) -> dict[tuple[str, str, str, int], Mapping[str, Any]]:
    records = document.get("records")
    if (
        document.get("schema_id") != "person-d-66-cell-baseline-predictions-v0-1"
        or document.get("prediction_row_count") != 10_592
        or not isinstance(records, list)
        or len(records) != 10_592
    ):
        raise ProductionAnalysisError("Person D prediction envelope differs")
    frame_identity = {
        (str(row["trajectory_id"]), int(row["global_model_frame_idx"])): (
            str(row["layout_id"]),
            int(row["fold_idx"]),
        )
        for row in hidden_metadata
    }
    required_keys = set(frame_identity)
    result: dict[tuple[str, str, str, int], Mapping[str, Any]] = {}
    for row in records:
        family = row.get("baseline_family")
        target = row.get("target_name")
        trajectory = row.get("trajectory_id")
        frame = row.get("model_frame_idx")
        if not isinstance(family, str) or not isinstance(target, str):
            raise ProductionAnalysisError("Person D prediction identity is malformed")
        if not isinstance(trajectory, str) or not isinstance(frame, int):
            raise ProductionAnalysisError("Person D frame identity is malformed")
        key = (family, target, trajectory, frame)
        if key in result:
            raise ProductionAnalysisError(f"Duplicate Person D prediction {key}")
        applicable = row.get("applicable")
        prediction = row.get("prediction")
        if not isinstance(applicable, bool):
            raise ProductionAnalysisError("Person D applicability is malformed")
        if applicable and (
            isinstance(prediction, bool)
            or not isinstance(prediction, (int, float))
            or not math.isfinite(float(prediction))
        ):
            raise ProductionAnalysisError(
                "An applicable Person D prediction is invalid"
            )
        if not applicable and prediction is not None:
            raise ProductionAnalysisError(
                "A non-applicable Person D row has a prediction"
            )
        result[key] = row

    for family, target in (
        *((family, "mu_oracle_blocks") for family in U1_BASELINES),
        *((family, "log_sigma_oracle") for family in U2_BASELINES),
    ):
        for trajectory, frame in required_keys:
            key = (family, target, trajectory, frame)
            if key not in result:
                raise ProductionAnalysisError(f"Person D row is missing: {key}")
            row = result[key]
            layout, fold = frame_identity[(trajectory, frame)]
            if row.get("layout_id") != layout or row.get("fold_idx") != fold:
                raise ProductionAnalysisError(f"Person D identity/fold mismatch: {key}")
    for family, target in (
        ("last_seen", "mu_oracle_blocks"),
        ("time_only", "log_sigma_oracle"),
        ("visible_history_q", "log_sigma_oracle"),
        ("known_q_analytic", "log_sigma_oracle"),
    ):
        if not all(
            result[(family, target, trajectory, frame)]["applicable"]
            for trajectory, frame in required_keys
        ):
            raise ProductionAnalysisError(
                f"Required full-universe D comparator is non-applicable: {family}/{target}"
            )
    for family, target in (
        ("grouped_shuffled", "mu_oracle_blocks"),
        ("grouped_shuffled", "log_sigma_oracle"),
    ):
        applicable_layouts = {
            str(result[(family, target, trajectory, frame)]["layout_id"])
            for trajectory, frame in required_keys
            if result[(family, target, trajectory, frame)]["applicable"]
        }
        if len(applicable_layouts) != 6:
            raise ProductionAnalysisError(
                f"Grouped shuffled intersection lacks all layouts: {family}/{target}"
            )
    return result


def load_production_inputs(paths: ProductionPaths) -> LoadedInputs:
    repository = paths.repository_root.resolve()
    source_commit = _validate_repository(repository)
    readiness_path = (
        repository
        / "docs/status/integration/bd_production_input_readiness_v0_1/readiness_receipt.json"
    )
    readiness = _load_json(
        readiness_path,
        expected_sha256=READINESS_RECEIPT_SHA256,
        label="input-readiness receipt",
    )
    if (
        readiness.get("run_id") != RUN_ID
        or readiness.get("readiness_decision", {}).get("can_real_u1_fitting_begin")
        is not True
        or readiness.get("readiness_decision", {}).get("can_real_u2_fitting_begin")
        is not True
        or readiness.get("readiness_decision", {}).get("can_real_u3_analysis_begin")
        is not False
        or readiness.get("person_d_compatibility", {}).get("required_comparators_ready")
        is not True
        or readiness.get("person_d_compatibility", {})
        .get("comparator_status", {})
        .get("no_wall_positive_control")
        != "READY_EXISTING"
    ):
        raise ProductionAnalysisError("Readiness decisions differ")

    analysis_root = paths.analysis_ready_root.resolve()
    manifest = _load_json(
        analysis_root / "analysis_ready_manifest.json",
        expected_sha256=ANALYSIS_READY_MANIFEST_SHA256,
        label="analysis-ready manifest",
    )
    if (
        manifest.get("run_id") != RUN_ID
        or manifest.get("eligible_frame_count") != ELIGIBLE_FRAME_COUNT
        or manifest.get("eligible_frame_layer_row_count") != ELIGIBLE_LAYER_ROW_COUNT
        or manifest.get("scientific_fitting_executed") is not False
    ):
        raise ProductionAnalysisError("Analysis-ready manifest differs")
    vector_path = analysis_root / "activation_vectors.npy"
    metadata_path = analysis_root / "sample_metadata.npy"
    if _sha256_file(vector_path) != ACTIVATION_VECTORS_SHA256:
        raise ProductionAnalysisError("Activation vector SHA-256 differs")
    if _sha256_file(metadata_path) != SAMPLE_METADATA_SHA256:
        raise ProductionAnalysisError("Sample metadata SHA-256 differs")
    vectors = np.load(vector_path, mmap_mode="r", allow_pickle=False)
    metadata = np.load(metadata_path, mmap_mode="r", allow_pickle=False)
    hidden_by_layer, hidden = _validate_analysis_matrix(vectors, metadata)

    d_root = repository / "docs/status/person_d_66_cell_production_baselines_v0_1"
    d_document = _load_json(
        d_root / "prediction_manifest.json",
        expected_sha256=D_PREDICTION_MANIFEST_SHA256,
        label="Person D prediction manifest",
    )
    if _sha256_file(d_root / "baseline_metrics.json") != D_BASELINE_METRICS_SHA256:
        raise ProductionAnalysisError("Person D metric package SHA-256 differs")
    if (
        _sha256_file(d_root / "d_to_b_production_baseline_handoff.json")
        != D_HANDOFF_SHA256
    ):
        raise ProductionAnalysisError("Person D handoff SHA-256 differs")
    if (
        _sha256_file(repository / "configs/analysis/core.yaml")
        != ANALYSIS_CONFIG_SHA256
    ):
        raise ProductionAnalysisError("Frozen analysis configuration differs")
    d_rows = _load_d_rows(d_document, hidden)
    return LoadedInputs(
        vectors=vectors,
        metadata=metadata,
        hidden_indices_by_layer=hidden_by_layer,
        hidden_metadata=hidden,
        d_rows=d_rows,
        source_hashes={
            "activation_index": ACTIVATION_INDEX_SHA256,
            "activation_vectors": ACTIVATION_VECTORS_SHA256,
            "analysis_config": ANALYSIS_CONFIG_SHA256,
            "analysis_ready_manifest": ANALYSIS_READY_MANIFEST_SHA256,
            "d_baseline_handoff": D_HANDOFF_SHA256,
            "d_baseline_metrics": D_BASELINE_METRICS_SHA256,
            "d_prediction_manifest": D_PREDICTION_MANIFEST_SHA256,
            "input_readiness_receipt": READINESS_RECEIPT_SHA256,
            "sample_metadata": SAMPLE_METADATA_SHA256,
        },
        source_commit=source_commit,
    )


def _layout_macro_values(
    rows: Sequence[Mapping[str, Any]], field: str
) -> dict[str, float]:
    grouped: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        value = row.get(field)
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
        ):
            raise ProductionAnalysisError(f"Invalid macro value at {field}")
        grouped[str(row["layout_id"])][str(row["trajectory_id"])].append(float(value))
    if len(grouped) < 2:
        raise ProductionAnalysisError("Macro statistic needs at least two layouts")
    return {
        layout: sum(sum(values) / len(values) for values in trajectories.values())
        / len(trajectories)
        for layout, trajectories in sorted(grouped.items())
    }


def _macro_weights(metadata: Sequence[Any]) -> np.ndarray:
    by_layout: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(list))
    for index, row in enumerate(metadata):
        by_layout[str(row["layout_id"])][str(row["trajectory_id"])].append(index)
    weights = np.zeros(len(metadata), dtype=np.float64)
    for trajectories in by_layout.values():
        for indices in trajectories.values():
            weight = 1.0 / len(by_layout) / len(trajectories) / len(indices)
            weights[indices] = weight
    if not math.isclose(float(weights.sum()), 1.0, rel_tol=0.0, abs_tol=1e-12):
        raise ProductionAnalysisError("Macro weights do not sum to one")
    return weights


def _weighted_regression(
    truth: Sequence[float], prediction: Sequence[float], metadata: Sequence[Any]
) -> dict[str, float | int]:
    actual = np.asarray(truth, dtype=np.float64)
    predicted = np.asarray(prediction, dtype=np.float64)
    if actual.shape != predicted.shape or actual.shape != (len(metadata),):
        raise ProductionAnalysisError("Weighted regression inputs do not align")
    weights = _macro_weights(metadata)
    mean = float(np.sum(weights * actual))
    mse = float(np.sum(weights * (actual - predicted) ** 2))
    denominator = float(np.sum(weights * (actual - mean) ** 2))
    if denominator == 0.0:
        raise ProductionAnalysisError("Weighted R2 is degenerate")
    return {
        "mae": float(np.sum(weights * np.abs(actual - predicted))),
        "mse": mse,
        "r2": 1.0 - mse / denominator,
        "sample_count": len(metadata),
    }


def _regression_record(
    truth: Sequence[float], prediction: Sequence[float]
) -> dict[str, Any]:
    metric = regression_metrics(list(map(float, truth)), list(map(float, prediction)))
    return {
        "mae": metric.mae,
        "mse": metric.mse,
        "r2": metric.r2,
        "sample_count": metric.sample_count,
    }


def _fold_regression(
    truth: np.ndarray, prediction: np.ndarray, metadata: np.ndarray
) -> list[dict[str, Any]]:
    records = []
    for fold in range(FOLD_COUNT):
        mask = metadata["fold_idx"] == fold
        record = _regression_record(truth[mask], prediction[mask])
        records.append(
            {
                "fold_idx": fold,
                "layout_count": len(set(map(str, metadata["layout_id"][mask]))),
                "trajectory_count": len(set(map(str, metadata["trajectory_id"][mask]))),
                **record,
            }
        )
    return records


def _fit_provenance(layer: int, target: str, result: RidgeOOFResult) -> dict[str, Any]:
    return {
        "alpha_grid": list(RIDGE_ALPHA_GRID),
        "hook_site": HOOK_SITE,
        "inner_fold_count": RIDGE_INNER_FOLD_COUNT,
        "layer_idx": layer,
        "outer_folds": [
            {
                "fold_idx": fit.outer_fold_idx,
                "inner_mean_mse_by_alpha": {
                    str(alpha): value
                    for alpha, value in sorted(
                        fit.alpha_selection.mean_mse_by_alpha.items()
                    )
                },
                "selected_alpha": fit.model.alpha,
                "test_row_count": len(fit.test_indices),
                "training_row_count": len(fit.training_indices),
            }
            for fit in result.fits
        ],
        "probe": "mineocclude.probes.ridge.fit_ridge_oof",
        "sample_count": len(result.predictions),
        "split_seed": SPLIT_SEED,
        "target_name": target,
        "train_only_scaling": True,
    }


def _paired_comparison(
    *,
    family: str,
    target: str,
    truth: np.ndarray,
    prediction: np.ndarray,
    metadata: np.ndarray,
    d_rows: Mapping[tuple[str, str, str, int], Mapping[str, Any]],
) -> tuple[dict[str, Any], dict[str, float]]:
    paired_rows: list[dict[str, Any]] = []
    paired_truth: list[float] = []
    paired_probe: list[float] = []
    paired_baseline: list[float] = []
    paired_metadata: list[Any] = []
    for index, row in enumerate(metadata):
        trajectory = str(row["trajectory_id"])
        frame = int(row["global_model_frame_idx"])
        baseline = d_rows[(family, target, trajectory, frame)]
        if not baseline["applicable"]:
            continue
        actual = float(truth[index])
        probe_value = float(prediction[index])
        baseline_value = float(baseline["prediction"])
        paired_rows.append(
            {
                "improvement": (baseline_value - actual) ** 2
                - (probe_value - actual) ** 2,
                "layout_id": str(row["layout_id"]),
                "trajectory_id": trajectory,
            }
        )
        paired_truth.append(actual)
        paired_probe.append(probe_value)
        paired_baseline.append(baseline_value)
        paired_metadata.append(row)
    if not paired_rows:
        raise ProductionAnalysisError(f"Empty D comparison for {family}/{target}")
    layout_values = _layout_macro_values(paired_rows, "improvement")
    if len(layout_values) != 6:
        raise ProductionAnalysisError(
            f"D comparison lacks layouts for {family}/{target}"
        )
    metadata_array = np.asarray(paired_metadata, dtype=metadata.dtype)
    probe_metric = _weighted_regression(paired_truth, paired_probe, metadata_array)
    baseline_metric = _weighted_regression(
        paired_truth, paired_baseline, metadata_array
    )
    record = {
        "applicable_intersection_count": len(paired_rows),
        "baseline_family": family,
        "baseline_layout_macro": baseline_metric,
        "baseline_micro": _regression_record(paired_truth, paired_baseline),
        "beats_baseline": sum(layout_values.values()) / len(layout_values) > 0.0,
        "layout_count": len(layout_values),
        "paired_layout_macro_loss_improvement": sum(layout_values.values())
        / len(layout_values),
        "probe_layout_macro": probe_metric,
        "probe_micro": _regression_record(paired_truth, paired_probe),
        "trajectory_count": len(
            set(str(row["trajectory_id"]) for row in paired_metadata)
        ),
    }
    return record, layout_values


def _pearson(left: Sequence[float], right: Sequence[float]) -> float:
    x = np.asarray(left, dtype=np.float64)
    y = np.asarray(right, dtype=np.float64)
    if x.shape != y.shape or x.ndim != 1 or len(x) < 2:
        raise ProductionAnalysisError("Pearson inputs do not align")
    x = x - x.mean()
    y = y - y.mean()
    denominator = float(np.sqrt(np.sum(x * x) * np.sum(y * y)))
    if denominator == 0.0:
        raise ProductionAnalysisError("Pearson correlation is degenerate")
    return float(np.sum(x * y) / denominator)


def _macro_partial(
    decoded: Sequence[float],
    oracle: Sequence[float],
    tau: Sequence[float],
    metadata: np.ndarray,
) -> tuple[float, dict[str, float]]:
    by_layout: dict[str, list[int]] = defaultdict(list)
    for index, row in enumerate(metadata):
        by_layout[str(row["layout_id"])].append(index)
    values = {
        layout: partial_correlation_controlling_tau(
            [float(decoded[index]) for index in indices],
            [float(oracle[index]) for index in indices],
            [float(tau[index]) for index in indices],
        )
        for layout, indices in sorted(by_layout.items())
    }
    if len(values) != 6:
        raise ProductionAnalysisError("Partial association lacks layouts")
    return sum(values.values()) / len(values), values


def _hierarchical_partial_bootstrap(
    decoded: Sequence[float],
    oracle: Sequence[float],
    tau: Sequence[float],
    metadata: np.ndarray,
) -> tuple[float, float]:
    hierarchy: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(list))
    for index, row in enumerate(metadata):
        hierarchy[str(row["layout_id"])][str(row["trajectory_id"])].append(index)
    layouts = sorted(hierarchy)
    if len(layouts) != 6:
        raise ProductionAnalysisError("Bootstrap requires six layouts")
    rng = random.Random(BOOTSTRAP_SEED)
    replicates: list[float] = []
    for _ in range(BOOTSTRAP_COUNT):
        layout_statistics: list[float] = []
        for layout in rng.choices(layouts, k=len(layouts)):
            trajectories = sorted(hierarchy[layout])
            indices: list[int] = []
            for trajectory in rng.choices(trajectories, k=len(trajectories)):
                indices.extend(hierarchy[layout][trajectory])
            layout_statistics.append(
                partial_correlation_controlling_tau(
                    [float(decoded[index]) for index in indices],
                    [float(oracle[index]) for index in indices],
                    [float(tau[index]) for index in indices],
                )
            )
        replicates.append(sum(layout_statistics) / len(layout_statistics))
    return bootstrap_confidence_interval(replicates, coverage=BOOTSTRAP_COVERAGE)


def _calibration_summary(
    truth: Sequence[float],
    mean: Sequence[float],
    sigma: Sequence[float],
    metadata: np.ndarray,
) -> dict[str, Any]:
    by_layout: dict[str, list[int]] = defaultdict(list)
    for index, row in enumerate(metadata):
        by_layout[str(row["layout_id"])].append(index)
    per_layout = {}
    for layout, indices in sorted(by_layout.items()):
        metric = calibration_metrics(
            [float(truth[index]) for index in indices],
            [float(mean[index]) for index in indices],
            [float(sigma[index]) for index in indices],
            levels=COVERAGE_LEVELS,
        )
        per_layout[layout] = metric
    if len(per_layout) != 6:
        raise ProductionAnalysisError("Calibration lacks layouts")
    pooled = calibration_metrics(
        list(map(float, truth)),
        list(map(float, mean)),
        list(map(float, sigma)),
        levels=COVERAGE_LEVELS,
    )
    coverages = [
        sum(metric.empirical_coverage[index] for metric in per_layout.values())
        / len(per_layout)
        for index in range(len(COVERAGE_LEVELS))
    ]
    return {
        "absolute_calibration_error_by_level": {
            str(level): abs(coverage - level)
            for level, coverage in zip(COVERAGE_LEVELS, coverages, strict=True)
        },
        "expected_calibration_error": sum(
            abs(coverage - level)
            for level, coverage in zip(COVERAGE_LEVELS, coverages, strict=True)
        )
        / len(COVERAGE_LEVELS),
        "layout_macro_observed_coverage": {
            str(level): coverage
            for level, coverage in zip(COVERAGE_LEVELS, coverages, strict=True)
        },
        "nominal_coverage": list(COVERAGE_LEVELS),
        "sample_count": len(truth),
        "z_diagnostics": {
            "coverage_1_96": pooled.z_diagnostics.coverage_1_96,
            "mean": pooled.z_diagnostics.mean,
            "root_mean_square": pooled.z_diagnostics.root_mean_square,
            "sample_std": pooled.z_diagnostics.sample_std,
        },
    }


def _fold_u2(
    decoded: np.ndarray,
    oracle: np.ndarray,
    tau: np.ndarray,
    truth: np.ndarray,
    mean: np.ndarray,
    metadata: np.ndarray,
) -> list[dict[str, Any]]:
    records = []
    for fold in range(FOLD_COUNT):
        mask = metadata["fold_idx"] == fold
        partial = partial_correlation_controlling_tau(
            decoded[mask].tolist(), oracle[mask].tolist(), tau[mask].tolist()
        )
        calibration = calibration_metrics(
            truth[mask].tolist(),
            mean[mask].tolist(),
            decoded[mask].tolist(),
            levels=COVERAGE_LEVELS,
        )
        records.append(
            {
                "fold_idx": fold,
                "layout_count": len(set(map(str, metadata["layout_id"][mask]))),
                "partial_correlation_controlling_tau": partial,
                "sample_count": int(mask.sum()),
                "trajectory_count": len(set(map(str, metadata["trajectory_id"][mask]))),
                "coverage": {
                    str(level): value
                    for level, value in zip(
                        COVERAGE_LEVELS, calibration.empirical_coverage, strict=True
                    )
                },
                "expected_calibration_error": calibration.expected_calibration_error,
            }
        )
    return records


def _baseline_calibration(
    *,
    family: str,
    mean_prediction: np.ndarray,
    truth: np.ndarray,
    metadata: np.ndarray,
    d_rows: Mapping[tuple[str, str, str, int], Mapping[str, Any]],
) -> dict[str, Any]:
    indices: list[int] = []
    log_sigma: list[float] = []
    for index, row in enumerate(metadata):
        key = (
            family,
            "log_sigma_oracle",
            str(row["trajectory_id"]),
            int(row["global_model_frame_idx"]),
        )
        baseline = d_rows[key]
        if baseline["applicable"]:
            indices.append(index)
            log_sigma.append(float(baseline["prediction"]))
    selected_metadata = metadata[indices]
    return _calibration_summary(
        truth[indices],
        mean_prediction[indices],
        reconstruct_sigma(log_sigma),
        selected_metadata,
    )


def _bands(layer_gates: Mapping[int, bool]) -> list[list[int]]:
    return [list(band) for band in qualifying_layer_bands(layer_gates)]


def compute_scientific_results(
    inputs: LoadedInputs,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, np.ndarray]]:
    metadata = inputs.hidden_metadata
    truth_mu = np.asarray(metadata["mu_oracle_blocks"], dtype=np.float64)
    truth_log_sigma = np.asarray(metadata["log_sigma_oracle"], dtype=np.float64)
    oracle_sigma = np.asarray(metadata["sigma_oracle_blocks"], dtype=np.float64)
    truth_position = np.asarray(metadata["x_true_blocks"], dtype=np.float64)
    tau = np.asarray(metadata["tau_seconds"], dtype=np.float64)
    u1_predictions = np.empty((len(LAYERS), HIDDEN_FRAME_COUNT), dtype=np.float64)
    u2_predictions = np.empty((len(LAYERS), HIDDEN_FRAME_COUNT), dtype=np.float64)
    fit_records: list[dict[str, Any]] = []
    u1_layers: list[dict[str, Any]] = []
    u2_layers: list[dict[str, Any]] = []
    u1_hypotheses: dict[str, Mapping[str, float]] = {}
    u2_hypotheses: dict[str, Mapping[str, float]] = {}

    for layer in LAYERS:
        features = np.asarray(
            inputs.vectors[inputs.hidden_indices_by_layer[layer]], dtype=np.float64
        )
        u1_fit = fit_ridge_oof(
            features,
            truth_mu,
            metadata["fold_idx"].astype(int).tolist(),
            metadata["layout_id"].tolist(),
            alpha_grid=RIDGE_ALPHA_GRID,
            inner_fold_count=RIDGE_INNER_FOLD_COUNT,
            seed=SPLIT_SEED,
        )
        u2_fit = fit_ridge_oof(
            features,
            truth_log_sigma,
            metadata["fold_idx"].astype(int).tolist(),
            metadata["layout_id"].tolist(),
            alpha_grid=RIDGE_ALPHA_GRID,
            inner_fold_count=RIDGE_INNER_FOLD_COUNT,
            seed=SPLIT_SEED,
        )
        mu_prediction = np.asarray(u1_fit.predictions, dtype=np.float64)
        log_sigma_prediction = np.asarray(u2_fit.predictions, dtype=np.float64)
        u1_predictions[layer] = mu_prediction
        u2_predictions[layer] = log_sigma_prediction
        fit_records.extend(
            (
                _fit_provenance(layer, "mu_oracle_blocks", u1_fit),
                _fit_provenance(layer, "log_sigma_oracle", u2_fit),
            )
        )

        u1_comparisons = []
        for family in U1_BASELINES:
            comparison, layout_values = _paired_comparison(
                family=family,
                target="mu_oracle_blocks",
                truth=truth_mu,
                prediction=mu_prediction,
                metadata=metadata,
                d_rows=inputs.d_rows,
            )
            u1_comparisons.append(comparison)
            if family in U1_PRIMARY_BASELINES:
                u1_hypotheses[f"u1:{family}:layer_{layer:02d}"] = layout_values
        u1_layers.append(
            {
                "baseline_comparisons": u1_comparisons,
                "fold_metrics": _fold_regression(truth_mu, mu_prediction, metadata),
                "layer_idx": layer,
                "layout_macro": _weighted_regression(truth_mu, mu_prediction, metadata),
                "micro": _regression_record(truth_mu, mu_prediction),
                "sample_count": HIDDEN_FRAME_COUNT,
            }
        )

        decoded_sigma = np.asarray(
            reconstruct_sigma(log_sigma_prediction), dtype=np.float64
        )
        if not np.isfinite(decoded_sigma).all() or not bool(
            np.all(decoded_sigma > 0.0)
        ):
            raise ProductionAnalysisError(f"Layer {layer} decoded spread is invalid")
        partial, partial_by_layout = _macro_partial(
            decoded_sigma, oracle_sigma, tau, metadata
        )
        ci_low, ci_high = _hierarchical_partial_bootstrap(
            decoded_sigma, oracle_sigma, tau, metadata
        )
        calibration = _calibration_summary(
            truth_position, mu_prediction, decoded_sigma, metadata
        )
        u2_comparisons = []
        for family in U2_BASELINES:
            comparison, layout_values = _paired_comparison(
                family=family,
                target="log_sigma_oracle",
                truth=truth_log_sigma,
                prediction=log_sigma_prediction,
                metadata=metadata,
                d_rows=inputs.d_rows,
            )
            if family in ("time_only", "visible_history_q", "known_q_analytic"):
                comparison["calibration"] = _baseline_calibration(
                    family=family,
                    mean_prediction=mu_prediction,
                    truth=truth_position,
                    metadata=metadata,
                    d_rows=inputs.d_rows,
                )
            u2_comparisons.append(comparison)
            if family in U2_PRIMARY_BASELINES:
                u2_hypotheses[f"u2:{family}:layer_{layer:02d}"] = layout_values
        u2_layers.append(
            {
                "association": {
                    "layout_macro_partial_correlation_controlling_tau": partial,
                    "partial_by_layout": partial_by_layout,
                    "pooled_pearson": _pearson(decoded_sigma, oracle_sigma),
                    "pooled_partial_correlation_controlling_tau": (
                        partial_correlation_controlling_tau(
                            decoded_sigma, oracle_sigma, tau
                        )
                    ),
                },
                "baseline_comparisons": u2_comparisons,
                "bootstrap": {
                    "ci_high": ci_high,
                    "ci_low": ci_low,
                    "coverage": BOOTSTRAP_COVERAGE,
                    "effective_layout_count": 6,
                    "effective_sample_count": HIDDEN_FRAME_COUNT,
                    "effective_trajectory_count": len(
                        set(map(str, metadata["trajectory_id"]))
                    ),
                    "hierarchy": ["layout_id", "trajectory_id", "all_rows"],
                    "resample_count": BOOTSTRAP_COUNT,
                    "seed": BOOTSTRAP_SEED,
                },
                "calibration": calibration,
                "fold_metrics": _fold_u2(
                    decoded_sigma,
                    oracle_sigma,
                    tau,
                    truth_position,
                    mu_prediction,
                    metadata,
                ),
                "layer_idx": layer,
                "sample_count": HIDDEN_FRAME_COUNT,
            }
        )

    u1_tests = shared_sign_flip_max_t(u1_hypotheses)
    u2_tests = shared_sign_flip_max_t(u2_hypotheses)
    u1_gates: dict[int, bool] = {}
    u2_gates: dict[int, bool] = {}
    for layer in LAYERS:
        u1 = u1_layers[layer]
        u1_by_family = {
            row["baseline_family"]: row for row in u1["baseline_comparisons"]
        }
        for family in U1_PRIMARY_BASELINES:
            u1_by_family[family]["permutation"] = u1_tests[
                f"u1:{family}:layer_{layer:02d}"
            ]
        u1_gate = u1["layout_macro"]["r2"] > 0.0 and all(
            u1_by_family[family]["paired_layout_macro_loss_improvement"] > 0.0
            and u1_by_family[family]["permutation"]["max_t_adjusted_p_value"] < 0.01
            for family in U1_PRIMARY_BASELINES
        )
        u1["gate"] = {
            "held_out_layout_macro_r2_gt_zero": u1["layout_macro"]["r2"] > 0.0,
            "last_seen_improvement_gt_zero": u1_by_family["last_seen"][
                "paired_layout_macro_loss_improvement"
            ]
            > 0.0,
            "last_seen_max_t_adjusted_p_lt_0_01": u1_by_family["last_seen"][
                "permutation"
            ]["max_t_adjusted_p_value"]
            < 0.01,
            "grouped_shuffled_improvement_gt_zero": u1_by_family["grouped_shuffled"][
                "paired_layout_macro_loss_improvement"
            ]
            > 0.0,
            "grouped_shuffled_max_t_adjusted_p_lt_0_01": u1_by_family[
                "grouped_shuffled"
            ]["permutation"]["max_t_adjusted_p_value"]
            < 0.01,
            "qualifies_layer": u1_gate,
        }
        u1_gates[layer] = u1_gate

        u2 = u2_layers[layer]
        u2_by_family = {
            row["baseline_family"]: row for row in u2["baseline_comparisons"]
        }
        for family in U2_PRIMARY_BASELINES:
            u2_by_family[family]["permutation"] = u2_tests[
                f"u2:{family}:layer_{layer:02d}"
            ]
        ece = u2["calibration"]["expected_calibration_error"]
        time_ece = u2_by_family["time_only"]["calibration"][
            "expected_calibration_error"
        ]
        history_ece = u2_by_family["visible_history_q"]["calibration"][
            "expected_calibration_error"
        ]
        u2_gate = (
            u2["bootstrap"]["ci_low"] > 0.0
            and ece <= 0.10
            and ece < time_ece
            and ece < history_ece
        )
        u2["gate"] = {
            "bootstrap_ci_lower_gt_zero": u2["bootstrap"]["ci_low"] > 0.0,
            "calibration_ece_at_most_0_10": ece <= 0.10,
            "coverage_error_better_than_time_only": ece < time_ece,
            "coverage_error_better_than_visible_history_q": ece < history_ece,
            "qualifies_layer": u2_gate,
        }
        u2_gates[layer] = u2_gate

    u1_bands = _bands(u1_gates)
    u2_bands = _bands(u2_gates)
    u1_best = max(
        LAYERS, key=lambda layer: (u1_layers[layer]["layout_macro"]["r2"], -layer)
    )
    u2_best = max(
        LAYERS,
        key=lambda layer: (
            u2_layers[layer]["association"][
                "layout_macro_partial_correlation_controlling_tau"
            ],
            -layer,
        ),
    )
    scientific = {
        "controls": {
            "grouped_shuffled": "READY_EXISTING_CONSUMED",
            "no_object_negative_control": "NOT_APPLICABLE",
            "no_wall_positive_control": "READY_EXISTING_CONSUMED",
        },
        "method": {
            "aggregation": "equal_layout_then_equal_trajectory_then_equal_row",
            "bootstrap": {
                "count": BOOTSTRAP_COUNT,
                "coverage": BOOTSTRAP_COVERAGE,
                "hierarchy": ["layout_id", "trajectory_id"],
                "seed": BOOTSTRAP_SEED,
            },
            "coverage_levels": list(COVERAGE_LEVELS),
            "fold_count": FOLD_COUNT,
            "layers": list(LAYERS),
            "permutation": {
                "adjustment": "single_step_shared_sign_flip_maxT",
                "count": PERMUTATION_COUNT,
                "resampling_unit": "whole_trajectory_pair_with_one_shared_sign_per_layout",
                "seed": PERMUTATION_SEED,
            },
            "ridge_alpha_grid": list(RIDGE_ALPHA_GRID),
            "ridge_inner_fold_count": RIDGE_INNER_FOLD_COUNT,
            "split_seed": SPLIT_SEED,
        },
        "provenance": {
            "branch": BRANCH,
            "hook_site": HOOK_SITE,
            "run_id": RUN_ID,
            "source_commit": inputs.source_commit,
            "source_hashes": dict(sorted(inputs.source_hashes.items())),
            "starting_authority": STARTING_AUTHORITY,
        },
        "schema_id": "mineocclude-66-cell-production-u1-u2-results-v0-1",
        "schema_version": "1.0",
        "u1": {
            "best_layer": u1_best,
            "layer_results": u1_layers,
            "qualifying_contiguous_bands": u1_bands,
            "qualifying_layers": [layer for layer in LAYERS if u1_gates[layer]],
            "selection_reason": "maximum frozen layout-macro held-out R2 after all 20 layers were evaluated",
            "verdict": "PASS" if u1_bands else "FAIL",
        },
        "u2": {
            "best_layer": u2_best,
            "layer_results": u2_layers,
            "qualifying_contiguous_bands": u2_bands,
            "qualifying_layers": [layer for layer in LAYERS if u2_gates[layer]],
            "selection_reason": (
                "maximum frozen layout-macro partial association controlling tau "
                "after all 20 layers were evaluated"
            ),
            "verdict": "PASS" if u2_bands else "FAIL",
        },
        "u3": {
            "blocker": "NO_VALID_TERMINAL_REVEAL_EVENTS",
            "status": "BLOCKED_NOT_EVALUATED",
        },
        "universe": {
            "eligible_frame_count": ELIGIBLE_FRAME_COUNT,
            "eligible_layer_row_count": ELIGIBLE_LAYER_ROW_COUNT,
            "hidden_analysis_frame_count": HIDDEN_FRAME_COUNT,
            "hidden_analysis_trajectory_count": len(
                set(map(str, metadata["trajectory_id"]))
            ),
            "layer_count": len(LAYERS),
            "layout_count": 6,
            "no_wall_positive_control_frame_count": NO_WALL_FRAME_COUNT,
        },
    }
    fits = {
        "coefficients_omitted_for_compact_publication": True,
        "fitted_probe_count": len(fit_records),
        "records": fit_records,
        "schema_id": "mineocclude-66-cell-production-u1-u2-fit-provenance-v0-1",
        "schema_version": "1.0",
    }
    arrays = {
        "fold_idx": np.asarray(metadata["fold_idx"], dtype=np.int16),
        "global_model_frame_idx": np.asarray(
            metadata["global_model_frame_idx"], dtype=np.int32
        ),
        "layer_idx": np.asarray(LAYERS, dtype=np.int16),
        "layout_id": np.asarray(metadata["layout_id"]),
        "trajectory_id": np.asarray(metadata["trajectory_id"]),
        "u1_mu_oof_prediction": u1_predictions,
        "u2_log_sigma_oof_prediction": u2_predictions,
    }
    return scientific, fits, arrays


def _final_verdict(scientific: Mapping[str, Any]) -> dict[str, Any]:
    u1 = scientific["u1"]
    u2 = scientific["u2"]
    u1_best = u1["layer_results"][u1["best_layer"]]
    u2_best = u2["layer_results"][u2["best_layer"]]
    u1_comparisons = {
        row["baseline_family"]: row for row in u1_best["baseline_comparisons"]
    }
    u2_comparisons = {
        row["baseline_family"]: row for row in u2_best["baseline_comparisons"]
    }
    return {
        "mean_position_decodable": u1["verdict"] == "PASS",
        "schema_id": "mineocclude-66-cell-production-u1-u2-final-verdict-v0-1",
        "schema_version": "1.0",
        "u1": {
            "beats_last_seen": u1_comparisons["last_seen"]["beats_baseline"],
            "best_layer": u1["best_layer"],
            "best_mae": u1_best["layout_macro"]["mae"],
            "best_r2": u1_best["layout_macro"]["r2"],
            "failed_gates_at_best_layer": [
                name
                for name, value in u1_best["gate"].items()
                if name != "qualifies_layer" and value is not True
            ],
            "grouped_permutation_max_t_adjusted_p": u1_comparisons["grouped_shuffled"][
                "permutation"
            ]["max_t_adjusted_p_value"],
            "qualifying_contiguous_bands": u1["qualifying_contiguous_bands"],
            "verdict": u1["verdict"],
        },
        "u2": {
            "beats_time_only": u2_best["gate"]["coverage_error_better_than_time_only"],
            "beats_visible_history": u2_best["gate"][
                "coverage_error_better_than_visible_history_q"
            ],
            "best_layer": u2["best_layer"],
            "bootstrap_ci_high": u2_best["bootstrap"]["ci_high"],
            "bootstrap_ci_low": u2_best["bootstrap"]["ci_low"],
            "calibration_pass": u2_best["gate"]["calibration_ece_at_most_0_10"],
            "coverage": u2_best["calibration"]["layout_macro_observed_coverage"],
            "failed_gates_at_best_layer": [
                name
                for name, value in u2_best["gate"].items()
                if name != "qualifies_layer" and value is not True
            ],
            "partial_association": u2_best["association"][
                "layout_macro_partial_correlation_controlling_tau"
            ],
            "qualifying_contiguous_bands": u2["qualifying_contiguous_bands"],
            "time_only_ece": u2_comparisons["time_only"]["calibration"][
                "expected_calibration_error"
            ],
            "verdict": u2["verdict"],
            "visible_history_ece": u2_comparisons["visible_history_q"]["calibration"][
                "expected_calibration_error"
            ],
        },
        "u3": {
            "blocker": "NO_VALID_TERMINAL_REVEAL_EVENTS",
            "status": "BLOCKED_NOT_EVALUATED",
        },
        "uncertainty_decodable": u2["verdict"] == "PASS",
    }


def _write_json(path: Path, document: Any) -> str:
    payload = _canonical_json_bytes(document)
    path.write_bytes(payload)
    return hashlib.sha256(payload).hexdigest()


def validate_result_package(
    git_root: Path,
    external_root: Path,
    *,
    expected_external_root: Path | None = None,
) -> None:
    """Validate the complete compact package and its external OOF payload."""

    if git_root.is_symlink() or external_root.is_symlink():
        raise ProductionAnalysisError("Result package roots cannot be symlinks")
    names = {path.name for path in git_root.iterdir() if path.is_file()}
    if names != set(RESULT_FILENAMES):
        raise ProductionAnalysisError("Result package file set differs")
    documents: dict[str, Mapping[str, Any]] = {}
    for name in RESULT_FILENAMES:
        path = git_root / name
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ProductionAnalysisError(
                f"Could not validate {name}: {error}"
            ) from error
        if not isinstance(document, Mapping):
            raise ProductionAnalysisError(f"Result document {name} is not an object")
        documents[name] = document
    inventory = documents["sha256_inventory.json"]
    expected_hashes = {
        name: _sha256_file(git_root / name)
        for name in RESULT_FILENAMES
        if name != "sha256_inventory.json"
    }
    if (
        inventory.get("schema_id")
        != "mineocclude-66-cell-production-u1-u2-inventory-v0-1"
        or inventory.get("inventory_excludes_self") is not True
        or inventory.get("files") != expected_hashes
    ):
        raise ProductionAnalysisError("Result inventory differs")
    scientific = documents["scientific_results.json"]
    verdict = documents["final_verdict.json"]
    fits = documents["fit_provenance.json"]
    receipt = documents["execution_receipt.json"]
    manifest = documents["oof_prediction_manifest.json"]
    if (
        scientific.get("schema_id")
        != "mineocclude-66-cell-production-u1-u2-results-v0-1"
        or len(scientific.get("u1", {}).get("layer_results", [])) != len(LAYERS)
        or len(scientific.get("u2", {}).get("layer_results", [])) != len(LAYERS)
        or scientific.get("u3", {}).get("status") != "BLOCKED_NOT_EVALUATED"
        or scientific.get("u3", {}).get("blocker") != "NO_VALID_TERMINAL_REVEAL_EVENTS"
    ):
        raise ProductionAnalysisError("Scientific result structure differs")
    if (
        verdict.get("schema_id")
        != "mineocclude-66-cell-production-u1-u2-final-verdict-v0-1"
        or not isinstance(verdict.get("mean_position_decodable"), bool)
        or not isinstance(verdict.get("uncertainty_decodable"), bool)
        or verdict.get("u3", {}).get("status") != "BLOCKED_NOT_EVALUATED"
    ):
        raise ProductionAnalysisError("Final verdict structure differs")
    if (
        fits.get("schema_id")
        != "mineocclude-66-cell-production-u1-u2-fit-provenance-v0-1"
        or fits.get("fitted_probe_count") != len(LAYERS) * 2
        or len(fits.get("records", [])) != len(LAYERS) * 2
    ):
        raise ProductionAnalysisError("Fit provenance structure differs")
    if (
        receipt.get("schema_id")
        != "mineocclude-66-cell-production-u1-u2-execution-receipt-v0-1"
        or receipt.get("u1_executed") is not True
        or receipt.get("u2_executed") is not True
        or receipt.get("u3_executed") is not False
        or receipt.get("u4_executed") is not False
        or receipt.get("activation_extraction_performed") is not False
        or receipt.get("baseline_recomputed") is not False
        or receipt.get("folds_regenerated") is not False
    ):
        raise ProductionAnalysisError("Execution receipt structure differs")
    expected_root = (expected_external_root or external_root).resolve()
    prediction_path = external_root / "oof_predictions.npz"
    if (
        manifest.get("schema_id")
        != "mineocclude-66-cell-production-u1-u2-oof-manifest-v0-1"
        or manifest.get("out_of_fold_only") is not True
        or manifest.get("prediction_count") != len(LAYERS) * HIDDEN_FRAME_COUNT * 2
        or manifest.get("path") != (expected_root / "oof_predictions.npz").as_posix()
        or manifest.get("sha256") != _sha256_file(prediction_path)
        or manifest.get("byte_size") != prediction_path.stat().st_size
        or receipt.get("oof_prediction_sha256") != manifest.get("sha256")
    ):
        raise ProductionAnalysisError("OOF prediction manifest differs")
    with np.load(prediction_path, allow_pickle=False) as arrays:
        expected_shapes = {
            "fold_idx": (HIDDEN_FRAME_COUNT,),
            "global_model_frame_idx": (HIDDEN_FRAME_COUNT,),
            "layer_idx": (len(LAYERS),),
            "layout_id": (HIDDEN_FRAME_COUNT,),
            "trajectory_id": (HIDDEN_FRAME_COUNT,),
            "u1_mu_oof_prediction": (len(LAYERS), HIDDEN_FRAME_COUNT),
            "u2_log_sigma_oof_prediction": (len(LAYERS), HIDDEN_FRAME_COUNT),
        }
        if set(arrays.files) != set(expected_shapes):
            raise ProductionAnalysisError("OOF array names differ")
        for name, shape in expected_shapes.items():
            if arrays[name].shape != shape:
                raise ProductionAnalysisError(f"OOF array shape differs: {name}")
        if (
            not np.isfinite(arrays["u1_mu_oof_prediction"]).all()
            or not np.isfinite(arrays["u2_log_sigma_oof_prediction"]).all()
        ):
            raise ProductionAnalysisError("OOF predictions are nonfinite")


def publish_results(
    paths: ProductionPaths,
    scientific: Mapping[str, Any],
    fits: Mapping[str, Any],
    arrays: Mapping[str, np.ndarray],
) -> dict[str, Any]:
    external_root = paths.external_output_root.resolve()
    git_root = paths.git_output_root.resolve()
    if external_root.exists() or external_root.is_symlink():
        raise ProductionAnalysisError(
            f"External output root already exists: {external_root}"
        )
    if git_root.exists() or git_root.is_symlink():
        raise ProductionAnalysisError(f"Git output root already exists: {git_root}")
    external_root.parent.mkdir(parents=True, exist_ok=True)
    git_root.parent.mkdir(parents=True, exist_ok=True)
    external_stage = Path(
        tempfile.mkdtemp(prefix=".u1-u2-production-", dir=external_root.parent)
    )
    git_stage = Path(tempfile.mkdtemp(prefix=".u1-u2-production-", dir=git_root.parent))
    try:
        prediction_path = external_stage / "oof_predictions.npz"
        np.savez_compressed(prediction_path, **arrays)
        prediction_sha = _sha256_file(prediction_path)
        prediction_size = prediction_path.stat().st_size
        oof_manifest = {
            "array_contract": {
                "fold_idx": [HIDDEN_FRAME_COUNT],
                "global_model_frame_idx": [HIDDEN_FRAME_COUNT],
                "layer_idx": [len(LAYERS)],
                "layout_id": [HIDDEN_FRAME_COUNT],
                "trajectory_id": [HIDDEN_FRAME_COUNT],
                "u1_mu_oof_prediction": [len(LAYERS), HIDDEN_FRAME_COUNT],
                "u2_log_sigma_oof_prediction": [len(LAYERS), HIDDEN_FRAME_COUNT],
            },
            "byte_size": prediction_size,
            "fold_count": FOLD_COUNT,
            "hook_site": HOOK_SITE,
            "out_of_fold_only": True,
            "path": (external_root / "oof_predictions.npz").as_posix(),
            "prediction_count": len(LAYERS) * HIDDEN_FRAME_COUNT * 2,
            "schema_id": "mineocclude-66-cell-production-u1-u2-oof-manifest-v0-1",
            "schema_version": "1.0",
            "sha256": prediction_sha,
        }
        verdict = _final_verdict(scientific)
        receipt = {
            "activation_extraction_performed": False,
            "baseline_recomputed": False,
            "branch": BRANCH,
            "folds_regenerated": False,
            "layer_count": len(LAYERS),
            "manual_u4_inspection": False,
            "oof_prediction_sha256": prediction_sha,
            "probe_fitted": True,
            "run_id": RUN_ID,
            "schema_id": "mineocclude-66-cell-production-u1-u2-execution-receipt-v0-1",
            "schema_version": "1.0",
            "source_commit": scientific["provenance"]["source_commit"],
            "u1_executed": True,
            "u2_executed": True,
            "u3_blocker": "NO_VALID_TERMINAL_REVEAL_EVENTS",
            "u3_executed": False,
            "u4_executed": False,
        }
        documents = {
            "execution_receipt.json": receipt,
            "final_verdict.json": verdict,
            "fit_provenance.json": fits,
            "oof_prediction_manifest.json": oof_manifest,
            "scientific_results.json": scientific,
        }
        hashes = {
            name: _write_json(git_stage / name, document)
            for name, document in sorted(documents.items())
        }
        inventory = {
            "files": hashes,
            "inventory_excludes_self": True,
            "schema_id": "mineocclude-66-cell-production-u1-u2-inventory-v0-1",
            "schema_version": "1.0",
        }
        inventory_sha = _write_json(git_stage / "sha256_inventory.json", inventory)
        validate_result_package(
            git_stage,
            external_stage,
            expected_external_root=external_root,
        )
        os.rename(external_stage, external_root)
        os.rename(git_stage, git_root)
        return {
            "inventory_sha256": inventory_sha,
            "oof_manifest": oof_manifest,
            "result_package_path": git_root.as_posix(),
            "verdict": verdict,
        }
    except Exception:
        shutil.rmtree(external_stage, ignore_errors=True)
        shutil.rmtree(git_stage, ignore_errors=True)
        raise


def run_production_analysis(paths: ProductionPaths) -> dict[str, Any]:
    inputs = load_production_inputs(paths)
    scientific, fits, arrays = compute_scientific_results(inputs)
    return publish_results(paths, scientific, fits, arrays)


__all__ = [
    "ProductionAnalysisError",
    "ProductionPaths",
    "compute_scientific_results",
    "load_production_inputs",
    "publish_results",
    "run_production_analysis",
    "validate_result_package",
]
