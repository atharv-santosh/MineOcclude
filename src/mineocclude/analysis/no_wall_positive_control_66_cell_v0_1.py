"""Current-authority 66-cell no-wall activation positive control.

This is a narrow repair for the production-readiness control gate.  It uses
the already-materialized B analysis matrix, B's existing nested grouped OOF
ridge, and D's current grouped-shuffled prediction manifest.  It does not
extract activations, alter folds, refit U1/U2, or modify their numerical
results.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
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
from mineocclude.metrics.resampling import (
    bootstrap_confidence_interval,
    hierarchical_bootstrap_indices,
)
from mineocclude.metrics.u1_mean import regression_metrics
from mineocclude.probes.ridge import RidgeOOFResult, fit_ridge_oof


RUN_ID = "mineocclude-run-ea6169430d693f8adcd16a23a62c4422"
BRANCH = "integration/mvp-final"
LAYERS = tuple(range(20))
LAYER_COUNT = 20
NO_WALL_FRAME_COUNT = 351
NO_WALL_TRAJECTORY_COUNT = 6
NO_WALL_LAYOUT_COUNT = 6
VECTOR_WIDTH = 2_048
SCOPE_VISIBLE_NO_WALL = 4
HOOK_SITE = "decoder_layer_output_residual_stream"
TARGET_NAME = "x_true_blocks"
TARGET_DESCRIPTION = "signed wall-parallel visible sheep position"

RIDGE_ALPHA_GRID = (0.1, 1.0, 10.0, 100.0)
RIDGE_INNER_FOLD_COUNT = 4
SPLIT_SEED = 20260719
BOOTSTRAP_COUNT = 2_000
BOOTSTRAP_SEED = 20260721
BOOTSTRAP_COVERAGE = 0.95
R2_THRESHOLD = 0.50
GROUPED_SHUFFLE_MAX_T_P_THRESHOLD = 0.01

ACTIVATION_INDEX_SHA256 = (
    "b5f97728bf4bcf957805f2664afbb53481d61db16318159cb0df6d8654c2f571"
)
READINESS_V0_1_SHA256 = (
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
PERSON_B_FOLD_MANIFEST_SHA256 = (
    "86739975882f4926c3398d5bfa21611daf06c579b3893809eb385e8dcd03001d"
)
PERSON_B_ROW_UNIVERSE_RECORDS_SHA256 = (
    "29b4cf003f3d9479b3606f17947879078801b400b09d942bd6827544b95227b2"
)
PERSON_B_ORACLE_TARGET_RECORDS_SHA256 = (
    "d95c83518d2ad322e6862f5460727382511fe831c0c6658a6cf72c9f7a8858b1"
)
PERSON_D_PREDICTION_MANIFEST_SHA256 = (
    "ffd8f8316f8d3fd74e8ca441dda6f9f45d4d05c7834496abc461a76b97337ea7"
)
ANALYSIS_CONFIG_SHA256 = (
    "b2e12e7049e0494c756be442a4f300cbc7dc0a6e262deecf682f1354e887f0ab"
)

ANALYSIS_READY_RELATIVE = Path(
    "output/status/bd_production_input_readiness_v0_1"
)
CONTROL_EXTERNAL_RELATIVE = Path(
    "output/status/bd_66_cell_no_wall_positive_control_v0_1"
)
CONTROL_PACKAGE_RELATIVE = Path(
    "docs/status/integration/bd_66_cell_no_wall_positive_control_v0_1"
)
READINESS_V0_1_RELATIVE = Path(
    "docs/status/integration/bd_production_input_readiness_v0_1/readiness_receipt.json"
)
READINESS_V0_2_RELATIVE = Path(
    "docs/status/integration/bd_production_input_readiness_v0_2/readiness_receipt.json"
)
RESULT_STATUS_V0_2_RELATIVE = Path(
    "docs/status/integration/bd_u1_u2_production_result_status_v0_2/result_status.json"
)
D_PREDICTION_RELATIVE = Path(
    "docs/status/person_d_66_cell_production_baselines_v0_1/prediction_manifest.json"
)


class NoWallPositiveControlError(RuntimeError):
    """Raised when a current-authority control input fails closed."""


@dataclass(frozen=True)
class PositiveControlReadiness:
    artifact_present: bool
    statistical_gate_pass: bool
    r2_gate_pass: bool
    bootstrap_ci_gate_pass: bool
    shuffle_comparison_gate_pass: bool
    reason: str


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_bytes(document: Any) -> bytes:
    try:
        encoded = json.dumps(
            document,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError) as error:
        raise NoWallPositiveControlError(f"Document is not strict JSON: {error}") from error
    return (encoded + "\n").encode("utf-8")


def _load_exact_json(path: Path, expected_sha256: str, label: str) -> Mapping[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise NoWallPositiveControlError(f"{label} is missing or a symlink: {path}")
    if _sha256_file(path) != expected_sha256:
        raise NoWallPositiveControlError(f"{label} SHA-256 differs: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise NoWallPositiveControlError(f"Could not load {label}: {error}") from error
    if not isinstance(value, Mapping):
        raise NoWallPositiveControlError(f"{label} is not a JSON object")
    return value


def _publish_json(path: Path, document: Any) -> dict[str, Any]:
    payload = _json_bytes(document)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != payload:
            raise NoWallPositiveControlError(
                f"Refusing to replace a non-identical immutable artifact: {path}"
            )
    else:
        fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_name, path)
        except BaseException:
            Path(temporary_name).unlink(missing_ok=True)
            raise
    return {"path": str(path), "sha256": hashlib.sha256(payload).hexdigest(), "byte_size": len(payload)}


def evaluate_positive_control_readiness(
    receipt: Mapping[str, Any] | None,
    *,
    expected_run_id: str = RUN_ID,
    expected_activation_index_sha256: str = ACTIVATION_INDEX_SHA256,
) -> PositiveControlReadiness:
    """Recompute the gate from a current receipt; never use historical fallback."""

    if receipt is None:
        return PositiveControlReadiness(
            artifact_present=False,
            statistical_gate_pass=False,
            r2_gate_pass=False,
            bootstrap_ci_gate_pass=False,
            shuffle_comparison_gate_pass=False,
            reason="MISSING_CURRENT_POSITIVE_CONTROL_RECEIPT_NO_HISTORICAL_FALLBACK",
        )
    authorities = receipt.get("authority_bindings")
    metrics = receipt.get("best_layer_metrics")
    gates = receipt.get("gate_decision")
    if (
        receipt.get("schema_id")
        != "integration-bd-66-cell-no-wall-positive-control-v0-1"
        or receipt.get("run_id") != expected_run_id
        or not isinstance(authorities, Mapping)
        or authorities.get("activation_index_sha256")
        != expected_activation_index_sha256
        or authorities.get("person_b_fold_manifest_sha256")
        != PERSON_B_FOLD_MANIFEST_SHA256
        or authorities.get("person_b_row_universe_records_sha256")
        != PERSON_B_ROW_UNIVERSE_RECORDS_SHA256
        or authorities.get("person_d_prediction_manifest_sha256")
        != PERSON_D_PREDICTION_MANIFEST_SHA256
        or not isinstance(metrics, Mapping)
        or not isinstance(gates, Mapping)
    ):
        return PositiveControlReadiness(
            artifact_present=False,
            statistical_gate_pass=False,
            r2_gate_pass=False,
            bootstrap_ci_gate_pass=False,
            shuffle_comparison_gate_pass=False,
            reason="CURRENT_POSITIVE_CONTROL_RECEIPT_AUTHORITY_MISMATCH",
        )
    r2 = metrics.get("r2")
    ci_low = metrics.get("r2_ci_low")
    shuffle_p = metrics.get("grouped_shuffle_max_t_adjusted_p")
    shuffle_improvement = metrics.get("grouped_shuffle_layout_macro_improvement")
    numeric = (r2, ci_low, shuffle_p, shuffle_improvement)
    if any(
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        for value in numeric
    ):
        return PositiveControlReadiness(
            artifact_present=False,
            statistical_gate_pass=False,
            r2_gate_pass=False,
            bootstrap_ci_gate_pass=False,
            shuffle_comparison_gate_pass=False,
            reason="CURRENT_POSITIVE_CONTROL_RECEIPT_METRIC_INVALID",
        )
    r2_pass = float(r2) >= R2_THRESHOLD
    ci_pass = float(ci_low) > 0.0
    shuffle_pass = (
        float(shuffle_improvement) > 0.0
        and float(shuffle_p) < GROUPED_SHUFFLE_MAX_T_P_THRESHOLD
    )
    statistical_pass = r2_pass and ci_pass and shuffle_pass
    declared = {
        "r2_gate_pass": r2_pass,
        "bootstrap_ci_gate_pass": ci_pass,
        "shuffle_comparison_gate_pass": shuffle_pass,
        "positive_control_pass": statistical_pass,
    }
    if any(gates.get(key) is not value for key, value in declared.items()):
        return PositiveControlReadiness(
            artifact_present=True,
            statistical_gate_pass=False,
            r2_gate_pass=r2_pass,
            bootstrap_ci_gate_pass=ci_pass,
            shuffle_comparison_gate_pass=shuffle_pass,
            reason="CURRENT_POSITIVE_CONTROL_RECEIPT_DECLARED_GATE_MISMATCH",
        )
    return PositiveControlReadiness(
        artifact_present=True,
        statistical_gate_pass=statistical_pass,
        r2_gate_pass=r2_pass,
        bootstrap_ci_gate_pass=ci_pass,
        shuffle_comparison_gate_pass=shuffle_pass,
        reason=(
            "CURRENT_POSITIVE_CONTROL_STATISTICAL_GATE_PASS"
            if statistical_pass
            else "CURRENT_POSITIVE_CONTROL_STATISTICAL_GATE_FAIL"
        ),
    )


def load_current_positive_control_readiness(receipt_path: Path) -> PositiveControlReadiness:
    """Load only the named current receipt; absence cannot fall back historically."""

    if not receipt_path.is_file() or receipt_path.is_symlink():
        return evaluate_positive_control_readiness(None)
    try:
        document = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return evaluate_positive_control_readiness(None)
    return evaluate_positive_control_readiness(
        document if isinstance(document, Mapping) else None
    )


def _validate_no_wall_inputs(
    vectors: np.ndarray,
    metadata: np.ndarray,
    readiness: Mapping[str, Any],
) -> tuple[dict[int, np.ndarray], np.ndarray, dict[str, Any]]:
    if vectors.shape != (13_240, VECTOR_WIDTH) or vectors.dtype != np.dtype("float32"):
        raise NoWallPositiveControlError("Analysis-ready activation matrix differs")
    if metadata.shape != (13_240,) or metadata.dtype.names is None:
        raise NoWallPositiveControlError("Analysis-ready metadata matrix differs")
    required = {
        "trajectory_id",
        "global_model_frame_idx",
        "layer_idx",
        "mu_oracle_blocks",
        "x_true_blocks",
        "tau_seconds",
        "last_visible_position_blocks",
        "layout_id",
        "control_type",
        "admission_stratum",
        "fold_idx",
        "scope_mask",
    }
    if not required.issubset(metadata.dtype.names):
        raise NoWallPositiveControlError(
            f"No-wall metadata fields are missing: {sorted(required - set(metadata.dtype.names))}"
        )
    by_layer: dict[int, np.ndarray] = {}
    reference: np.ndarray | None = None
    frame_keys: tuple[tuple[str, int], ...] | None = None
    duplicate_count = 0
    missing_count = 0
    unauthorized_count = 0
    invariant_fields = (
        "trajectory_id",
        "global_model_frame_idx",
        "mu_oracle_blocks",
        "x_true_blocks",
        "tau_seconds",
        "last_visible_position_blocks",
        "layout_id",
        "control_type",
        "admission_stratum",
        "fold_idx",
        "scope_mask",
    )
    for layer in LAYERS:
        indices = np.flatnonzero(
            (metadata["layer_idx"] == layer)
            & ((metadata["scope_mask"] & SCOPE_VISIBLE_NO_WALL) != 0)
        )
        missing_count += max(0, NO_WALL_FRAME_COUNT - len(indices))
        current = metadata[indices]
        keys = tuple(
            (str(row["trajectory_id"]), int(row["global_model_frame_idx"]))
            for row in current
        )
        duplicate_count += len(keys) - len(set(keys))
        if len(indices) != NO_WALL_FRAME_COUNT:
            continue
        if reference is None:
            reference = current
            frame_keys = keys
        elif keys != frame_keys:
            missing_count += len(set(frame_keys or ()) - set(keys))
        if reference is not None:
            for field in invariant_fields:
                if reference[field].dtype.kind == "f":
                    equal = bool(np.array_equal(reference[field], current[field], equal_nan=True))
                else:
                    equal = bool(np.array_equal(reference[field], current[field]))
                if not equal:
                    unauthorized_count += 1
        by_layer[layer] = indices
    if reference is None:
        raise NoWallPositiveControlError("No no-wall metadata rows are available")
    unauthorized_count += int(
        np.count_nonzero(reference["control_type"] != "no_wall_visible_control")
    )
    unauthorized_count += int(
        np.count_nonzero(reference["admission_stratum"] != "no_wall_visible_control")
    )
    unauthorized_count += int(np.count_nonzero(reference["tau_seconds"] != 0.0))
    for field in ("x_true_blocks", "last_visible_position_blocks", "mu_oracle_blocks"):
        unauthorized_count += int(np.count_nonzero(~np.isfinite(reference[field])))
    unauthorized_count += int(
        np.count_nonzero(reference["x_true_blocks"] != reference["last_visible_position_blocks"])
    )
    unauthorized_count += int(
        np.count_nonzero(reference["x_true_blocks"] != reference["mu_oracle_blocks"])
    )
    layouts = set(map(str, reference["layout_id"]))
    trajectories = set(map(str, reference["trajectory_id"]))
    folds = set(map(int, reference["fold_idx"]))
    layout_fold: dict[str, int] = {}
    trajectory_fold: dict[str, int] = {}
    fold_integrity = True
    for row in reference:
        layout = str(row["layout_id"])
        trajectory = str(row["trajectory_id"])
        fold = int(row["fold_idx"])
        fold_integrity &= layout_fold.setdefault(layout, fold) == fold
        fold_integrity &= trajectory_fold.setdefault(trajectory, fold) == fold
    fold_integrity &= folds == set(range(5))
    fold_integrity &= len(layouts) == NO_WALL_LAYOUT_COUNT
    fold_integrity &= len(trajectories) == NO_WALL_TRAJECTORY_COUNT
    fold_integrity &= readiness.get("fold_integrity", {}).get("leakage_audit_pass") is True
    audit = {
        "schema_id": "integration-bd-66-cell-no-wall-input-join-audit-v0-1",
        "schema_version": "1.0",
        "run_id": RUN_ID,
        "activation_index_sha256": ACTIVATION_INDEX_SHA256,
        "join_key": ["trajectory_id", "global_model_frame_idx", "layer_idx"],
        "join_duplicate_count": duplicate_count,
        "join_missing_activation_count": missing_count,
        "join_unauthorized_source_count": unauthorized_count,
        "fold_integrity_pass": bool(fold_integrity),
        "fold_count": len(folds),
        "layer_count": len(by_layer),
        "no_wall_trajectory_count": len(trajectories),
        "no_wall_layout_count": len(layouts),
        "visible_eligible_frame_count": len(reference),
        "target_name": TARGET_NAME,
        "target_description": TARGET_DESCRIPTION,
        "target_unit": "blocks",
        "visible_target_identity_check": "x_true_blocks == last_visible_position_blocks == mu_oracle_blocks on all admitted no-wall rows",
        "visible_target_identity_pass": unauthorized_count == 0,
        "global_activation_audit_repeated": False,
        "upstream_activation_validation_reused": readiness.get("activation_validation", {}),
    }
    if duplicate_count or missing_count or unauthorized_count or not fold_integrity:
        raise NoWallPositiveControlError(f"No-wall join/fold audit failed: {audit}")
    if len(by_layer) != LAYER_COUNT or not np.isfinite(vectors[np.concatenate(tuple(by_layer.values()))]).all():
        raise NoWallPositiveControlError("No-wall activation vectors are missing/nonfinite")
    return by_layer, reference, audit


def score_oof_predictions(truth: Sequence[float], predictions: Sequence[float]) -> dict[str, Any]:
    metric = regression_metrics(list(map(float, truth)), list(map(float, predictions)))
    return {
        "r2": metric.r2,
        "mae": metric.mae,
        "mse": metric.mse,
        "sample_count": metric.sample_count,
    }


def bootstrap_r2_interval(
    truth: Sequence[float],
    predictions: Sequence[float],
    metadata_rows: Sequence[Mapping[str, Any]],
    *,
    resample_count: int = BOOTSTRAP_COUNT,
    seed: int = BOOTSTRAP_SEED,
) -> tuple[float, float, list[float]]:
    indices = hierarchical_bootstrap_indices(
        metadata_rows, resample_count=resample_count, seed=seed
    )
    actual = np.asarray(truth, dtype=np.float64)
    estimate = np.asarray(predictions, dtype=np.float64)
    values = [
        regression_metrics(actual[list(selection)].tolist(), estimate[list(selection)].tolist()).r2
        for selection in indices
    ]
    low, high = bootstrap_confidence_interval(values, coverage=BOOTSTRAP_COVERAGE)
    return low, high, values


def _fit_provenance(layer: int, result: RidgeOOFResult) -> dict[str, Any]:
    return {
        "layer_idx": layer,
        "probe": "mineocclude.probes.ridge.fit_ridge_oof",
        "alpha_grid": list(RIDGE_ALPHA_GRID),
        "inner_fold_count": RIDGE_INNER_FOLD_COUNT,
        "split_seed": SPLIT_SEED,
        "train_only_scaling": True,
        "outer_folds": [
            {
                "fold_idx": fit.outer_fold_idx,
                "selected_alpha": fit.alpha_selection.selected_alpha,
                "training_row_count": len(fit.training_indices),
                "test_row_count": len(fit.test_indices),
                "inner_mean_mse_by_alpha": {
                    str(alpha): value
                    for alpha, value in sorted(fit.alpha_selection.mean_mse_by_alpha.items())
                },
            }
            for fit in result.fits
        ],
    }


def _load_or_fit_oof(
    *,
    vectors: np.ndarray,
    by_layer: Mapping[int, np.ndarray],
    metadata: np.ndarray,
    external_archive: Path,
    existing_metrics_path: Path,
) -> tuple[np.ndarray, list[dict[str, Any]], bool, dict[str, Any]]:
    truth = np.asarray(metadata["x_true_blocks"], dtype=np.float64)
    folds = [int(value) for value in metadata["fold_idx"]]
    layouts = [str(value) for value in metadata["layout_id"]]
    trajectories = np.asarray(metadata["trajectory_id"], dtype="U32")
    frames = np.asarray(metadata["global_model_frame_idx"], dtype=np.int32)
    if existing_metrics_path.is_file() and external_archive.is_file():
        existing = json.loads(existing_metrics_path.read_text(encoding="utf-8"))
        archive_ref = existing.get("oof_prediction_archive", {})
        if (
            existing.get("authority_bindings", {}).get("activation_index_sha256")
            == ACTIVATION_INDEX_SHA256
            and existing.get("authority_bindings", {}).get("person_b_fold_manifest_sha256")
            == PERSON_B_FOLD_MANIFEST_SHA256
            and existing.get("target_name") == TARGET_NAME
            and existing.get("probe_configuration")
            == {
                "alpha_grid": list(RIDGE_ALPHA_GRID),
                "hook_site": HOOK_SITE,
                "inner_fold_count": RIDGE_INNER_FOLD_COUNT,
                "outer_fold_count": 5,
                "split_seed": SPLIT_SEED,
                "train_only_scaling": True,
            }
            and archive_ref.get("sha256") == _sha256_file(external_archive)
        ):
            with np.load(external_archive, allow_pickle=False) as archive:
                prediction = archive["predictions"]
                accepted = (
                    prediction.shape == (LAYER_COUNT, NO_WALL_FRAME_COUNT)
                    and np.array_equal(archive["truth"], truth)
                    and np.array_equal(archive["trajectory_id"], trajectories)
                    and np.array_equal(archive["global_model_frame_idx"], frames)
                    and np.array_equal(archive["fold_idx"], metadata["fold_idx"])
                    and np.array_equal(archive["layer_idx"], np.asarray(LAYERS))
                    and np.isfinite(prediction).all()
                )
                if accepted:
                    return (
                        np.asarray(prediction, dtype=np.float64),
                        list(existing["layers"]),
                        True,
                        {
                            "path": str(external_archive),
                            "sha256": archive_ref["sha256"],
                            "byte_size": external_archive.stat().st_size,
                        },
                    )

    predictions = np.empty((LAYER_COUNT, NO_WALL_FRAME_COUNT), dtype=np.float64)
    layer_records: list[dict[str, Any]] = []
    for layer in LAYERS:
        matrix = np.asarray(vectors[by_layer[layer]], dtype=np.float64)
        fitted = fit_ridge_oof(
            matrix,
            truth,
            folds,
            layouts,
            alpha_grid=RIDGE_ALPHA_GRID,
            inner_fold_count=RIDGE_INNER_FOLD_COUNT,
            seed=SPLIT_SEED,
        )
        layer_prediction = np.asarray(fitted.predictions, dtype=np.float64)
        predictions[layer] = layer_prediction
        layer_records.append(
            {
                "layer_idx": layer,
                "feature_matrix_sha256": hashlib.sha256(
                    matrix.astype("<f8", copy=False).tobytes(order="C")
                ).hexdigest(),
                "metrics": score_oof_predictions(truth, layer_prediction),
                "fit_provenance": _fit_provenance(layer, fitted),
            }
        )

    external_archive.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".oof_predictions.", suffix=".npz", dir=external_archive.parent)
    os.close(fd)
    temporary = Path(name)
    try:
        np.savez_compressed(
            temporary,
            predictions=predictions,
            truth=truth,
            layer_idx=np.asarray(LAYERS, dtype=np.int16),
            trajectory_id=trajectories,
            global_model_frame_idx=frames,
            layout_id=np.asarray(metadata["layout_id"], dtype="U16"),
            fold_idx=np.asarray(metadata["fold_idx"], dtype=np.int16),
        )
        os.replace(temporary, external_archive)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    archive_identity = {
        "path": str(external_archive),
        "sha256": _sha256_file(external_archive),
        "byte_size": external_archive.stat().st_size,
    }
    return predictions, layer_records, False, archive_identity


def _grouped_shuffle_comparison(
    *,
    repository: Path,
    metadata: np.ndarray,
    truth: np.ndarray,
    predictions: np.ndarray,
) -> dict[str, Any]:
    manifest_path = repository / D_PREDICTION_RELATIVE
    document = _load_exact_json(
        manifest_path,
        PERSON_D_PREDICTION_MANIFEST_SHA256,
        "Person D current prediction manifest",
    )
    records = document.get("records")
    if not isinstance(records, list):
        raise NoWallPositiveControlError("Person D prediction records are missing")
    index: dict[tuple[str, int], Mapping[str, Any]] = {}
    for row in records:
        if (
            row.get("baseline_family") == "grouped_shuffled"
            and row.get("target_name") == "mu_oracle_blocks"
        ):
            key = (str(row.get("trajectory_id")), int(row.get("model_frame_idx", -1)))
            if key in index:
                raise NoWallPositiveControlError("D grouped-shuffle row repeats")
            index[key] = row
    hypotheses: dict[str, dict[str, float]] = {}
    layer_summaries: dict[str, Any] = {}
    comparison_keys: tuple[tuple[str, int], ...] | None = None
    for layer in LAYERS:
        improvements: dict[str, list[float]] = defaultdict(list)
        keys: list[tuple[str, int]] = []
        baseline_truth: list[float] = []
        baseline_prediction: list[float] = []
        probe_prediction: list[float] = []
        for idx, row in enumerate(metadata):
            key = (str(row["trajectory_id"]), int(row["global_model_frame_idx"]))
            baseline = index.get(key)
            if baseline is None:
                raise NoWallPositiveControlError(f"D grouped-shuffle key is absent: {key}")
            if baseline.get("layout_id") != str(row["layout_id"]):
                raise NoWallPositiveControlError("D grouped-shuffle layout identity differs")
            if baseline.get("fold_idx") != int(row["fold_idx"]):
                raise NoWallPositiveControlError("D grouped-shuffle fold identity differs")
            if not baseline.get("applicable"):
                continue
            value = baseline.get("prediction")
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
                raise NoWallPositiveControlError("Applicable D grouped-shuffle value is invalid")
            actual = float(truth[idx])
            decoded = float(predictions[layer, idx])
            shuffled = float(value)
            improvements[str(row["layout_id"])].append(
                (shuffled - actual) ** 2 - (decoded - actual) ** 2
            )
            keys.append(key)
            baseline_truth.append(actual)
            baseline_prediction.append(shuffled)
            probe_prediction.append(decoded)
        current_keys = tuple(keys)
        if comparison_keys is None:
            comparison_keys = current_keys
        elif current_keys != comparison_keys:
            raise NoWallPositiveControlError("Grouped-shuffle comparison rows vary by layer")
        layout_values = {
            layout: float(sum(values) / len(values))
            for layout, values in sorted(improvements.items())
        }
        if len(layout_values) < 2:
            raise NoWallPositiveControlError("Grouped-shuffle comparison has fewer than two layouts")
        hypotheses[f"layer_{layer:02d}"] = layout_values
        layer_summaries[str(layer)] = {
            "applicable_intersection_count": len(keys),
            "layout_count": len(layout_values),
            "layout_macro_loss_improvement": float(sum(layout_values.values()) / len(layout_values)),
            "layout_macro_loss_improvement_by_layout": layout_values,
            "probe_metrics_on_intersection": score_oof_predictions(baseline_truth, probe_prediction),
            "grouped_shuffle_metrics_on_intersection": score_oof_predictions(
                baseline_truth, baseline_prediction
            ),
        }
    tests = shared_sign_flip_max_t(hypotheses)
    for layer in LAYERS:
        layer_summaries[str(layer)]["shared_layout_max_t"] = tests[f"layer_{layer:02d}"]
    return {
        "schema_id": "integration-bd-66-cell-no-wall-grouped-shuffle-results-v0-1",
        "schema_version": "1.0",
        "run_id": RUN_ID,
        "source_artifact": {
            "path": str(D_PREDICTION_RELATIVE),
            "sha256": PERSON_D_PREDICTION_MANIFEST_SHA256,
        },
        "grouped_shuffle_reused": True,
        "grouped_shuffle_executed": False,
        "comparison_inference_executed": True,
        "target_alias_validated": "mu_oracle_blocks equals x_true_blocks for all 351 current no-wall rows",
        "comparison_policy": {
            "method": "one-sided shared-layout single-step maxT paired squared-loss improvement",
            "permutation_count": 999,
            "permutation_seed": 20260720,
            "max_t_adjusted_p_threshold_exclusive": GROUPED_SHUFFLE_MAX_T_P_THRESHOLD,
            "missingness_policy": "explicit applicable intersection from current D artifact; no imputation",
        },
        "layers": layer_summaries,
    }


def _identity(path: Path, repository: Path | None = None) -> dict[str, Any]:
    shown = path
    if repository is not None:
        try:
            shown = path.relative_to(repository)
        except ValueError:
            shown = path
    return {
        "path": str(shown),
        "sha256": _sha256_file(path),
        "byte_size": path.stat().st_size,
    }


def run_current_positive_control(
    *, repository: Path, production_root: Path
) -> dict[str, Any]:
    repository = repository.resolve()
    production_root = production_root.resolve()
    readiness_path = repository / READINESS_V0_1_RELATIVE
    readiness = _load_exact_json(
        readiness_path, READINESS_V0_1_SHA256, "B/D readiness v0.1 receipt"
    )
    if (
        readiness.get("run_id") != RUN_ID
        or readiness.get("authorities", {}).get("person_a", {}).get("index", {}).get("sha256")
        != ACTIVATION_INDEX_SHA256
        or readiness.get("fold_integrity", {}).get("leakage_audit_pass") is not True
    ):
        raise NoWallPositiveControlError("Readiness v0.1 does not bind current authority")
    analysis_root = production_root / ANALYSIS_READY_RELATIVE
    manifest = _load_exact_json(
        analysis_root / "analysis_ready_manifest.json",
        ANALYSIS_READY_MANIFEST_SHA256,
        "analysis-ready manifest",
    )
    authorities = manifest.get("authorities", {})
    if (
        manifest.get("run_id") != RUN_ID
        or authorities.get("activation_index_sha256") != ACTIVATION_INDEX_SHA256
        or authorities.get("person_b_fold_manifest_sha256")
        != PERSON_B_FOLD_MANIFEST_SHA256
        or authorities.get("person_b_oracle_target_records_sha256")
        != PERSON_B_ORACLE_TARGET_RECORDS_SHA256
        or authorities.get("person_b_row_universe_records_sha256")
        != PERSON_B_ROW_UNIVERSE_RECORDS_SHA256
    ):
        raise NoWallPositiveControlError("Analysis-ready authority binding differs")
    vector_path = analysis_root / "activation_vectors.npy"
    metadata_path = analysis_root / "sample_metadata.npy"
    if _sha256_file(vector_path) != ACTIVATION_VECTORS_SHA256:
        raise NoWallPositiveControlError("Activation matrix SHA-256 differs")
    if _sha256_file(metadata_path) != SAMPLE_METADATA_SHA256:
        raise NoWallPositiveControlError("Metadata matrix SHA-256 differs")
    vectors = np.load(vector_path, mmap_mode="r", allow_pickle=False)
    metadata_all = np.load(metadata_path, mmap_mode="r", allow_pickle=False)
    by_layer, metadata, join_audit = _validate_no_wall_inputs(
        vectors, metadata_all, readiness
    )

    package_root = repository / CONTROL_PACKAGE_RELATIVE
    external_root = production_root / CONTROL_EXTERNAL_RELATIVE
    metrics_path = package_root / "all_layer_metrics.json"
    predictions, layers, reused_oof, archive_identity = _load_or_fit_oof(
        vectors=vectors,
        by_layer=by_layer,
        metadata=metadata,
        external_archive=external_root / "oof_predictions.npz",
        existing_metrics_path=metrics_path,
    )
    truth = np.asarray(metadata["x_true_blocks"], dtype=np.float64)
    if len(layers) != LAYER_COUNT or [int(row["layer_idx"]) for row in layers] != list(LAYERS):
        raise NoWallPositiveControlError("All-layer metric coverage differs")
    best_record = max(
        layers,
        key=lambda row: (float(row["metrics"]["r2"]), -int(row["layer_idx"])),
    )
    best_layer = int(best_record["layer_idx"])

    bootstrap_rows = [
        {"layout_id": str(row["layout_id"]), "trajectory_id": str(row["trajectory_id"])}
        for row in metadata
    ]
    ci_low, ci_high, bootstrap_values = bootstrap_r2_interval(
        truth, predictions[best_layer], bootstrap_rows
    )
    grouped_shuffle = _grouped_shuffle_comparison(
        repository=repository,
        metadata=metadata,
        truth=truth,
        predictions=predictions,
    )
    best_shuffle = grouped_shuffle["layers"][str(best_layer)]
    best_p = float(best_shuffle["shared_layout_max_t"]["max_t_adjusted_p_value"])
    best_improvement = float(best_shuffle["layout_macro_loss_improvement"])
    best_r2 = float(best_record["metrics"]["r2"])
    best_mae = float(best_record["metrics"]["mae"])
    r2_pass = best_r2 >= R2_THRESHOLD
    ci_pass = ci_low > 0.0
    shuffle_pass = best_improvement > 0.0 and best_p < GROUPED_SHUFFLE_MAX_T_P_THRESHOLD
    positive_pass = r2_pass and ci_pass and shuffle_pass

    authority_bindings = {
        "activation_index_sha256": ACTIVATION_INDEX_SHA256,
        "activation_vectors_sha256": ACTIVATION_VECTORS_SHA256,
        "analysis_config_sha256": ANALYSIS_CONFIG_SHA256,
        "analysis_ready_manifest_sha256": ANALYSIS_READY_MANIFEST_SHA256,
        "person_b_fold_manifest_sha256": PERSON_B_FOLD_MANIFEST_SHA256,
        "person_b_oracle_target_records_sha256": PERSON_B_ORACLE_TARGET_RECORDS_SHA256,
        "person_b_row_universe_records_sha256": PERSON_B_ROW_UNIVERSE_RECORDS_SHA256,
        "person_d_prediction_manifest_sha256": PERSON_D_PREDICTION_MANIFEST_SHA256,
        "readiness_v0_1_sha256": READINESS_V0_1_SHA256,
        "sample_metadata_sha256": SAMPLE_METADATA_SHA256,
    }
    all_layer_document = {
        "schema_id": "integration-bd-66-cell-no-wall-all-layer-metrics-v0-1",
        "schema_version": "1.0",
        "run_id": RUN_ID,
        "authority_bindings": authority_bindings,
        "target_name": TARGET_NAME,
        "target_description": TARGET_DESCRIPTION,
        "target_unit": "blocks",
        "probe_configuration": {
            "alpha_grid": list(RIDGE_ALPHA_GRID),
            "hook_site": HOOK_SITE,
            "inner_fold_count": RIDGE_INNER_FOLD_COUNT,
            "outer_fold_count": 5,
            "split_seed": SPLIT_SEED,
            "train_only_scaling": True,
        },
        "existing_current_oof_reused": reused_oof,
        "ridge_refit_required": not reused_oof,
        "oof_prediction_archive": archive_identity,
        "best_layer": best_layer,
        "layers": layers,
    }
    bootstrap_document = {
        "schema_id": "integration-bd-66-cell-no-wall-bootstrap-results-v0-1",
        "schema_version": "1.0",
        "run_id": RUN_ID,
        "best_layer": best_layer,
        "observed_r2": best_r2,
        "ci_low": ci_low,
        "ci_high": ci_high,
        "coverage": BOOTSTRAP_COVERAGE,
        "hierarchy": ["layout_id", "trajectory_id"],
        "resample_count": BOOTSTRAP_COUNT,
        "seed": BOOTSTRAP_SEED,
        "replicate_r2": bootstrap_values,
    }
    package_root.mkdir(parents=True, exist_ok=True)
    join_identity = _publish_json(package_root / "input_join_audit.json", join_audit)
    metrics_identity = _publish_json(metrics_path, all_layer_document)
    bootstrap_identity = _publish_json(
        package_root / "bootstrap_results.json", bootstrap_document
    )
    shuffle_identity = _publish_json(
        package_root / "grouped_shuffle_results.json", grouped_shuffle
    )
    receipt = {
        "schema_id": "integration-bd-66-cell-no-wall-positive-control-v0-1",
        "schema_version": "1.0",
        "branch": BRANCH,
        "run_id": RUN_ID,
        "current_66_cell_authority_used": True,
        "historical_control_used_as_gate": False,
        "authority_bindings": authority_bindings,
        "input_counts": {
            "no_wall_trajectory_count": NO_WALL_TRAJECTORY_COUNT,
            "no_wall_layout_count": NO_WALL_LAYOUT_COUNT,
            "visible_eligible_frame_count": NO_WALL_FRAME_COUNT,
            "layer_count": LAYER_COUNT,
        },
        "join_audit": {
            "join_duplicate_count": join_audit["join_duplicate_count"],
            "join_missing_activation_count": join_audit["join_missing_activation_count"],
            "join_unauthorized_source_count": join_audit["join_unauthorized_source_count"],
            "fold_integrity_pass": join_audit["fold_integrity_pass"],
        },
        "execution": {
            "existing_current_oof_reused": reused_oof,
            "ridge_refit_required": not reused_oof,
            "grouped_shuffle_reused": True,
            "grouped_shuffle_executed": False,
            "u1_u2_rerun": False,
            "activation_extraction_rerun": False,
        },
        "best_layer_metrics": {
            "layer_idx": best_layer,
            "r2": best_r2,
            "mae": best_mae,
            "r2_ci_low": ci_low,
            "r2_ci_high": ci_high,
            "grouped_shuffle_max_t_adjusted_p": best_p,
            "grouped_shuffle_layout_macro_improvement": best_improvement,
        },
        "gate_thresholds": {
            "r2_minimum_inclusive": R2_THRESHOLD,
            "bootstrap_ci_lower_exclusive": 0.0,
            "grouped_shuffle_layout_macro_improvement_exclusive": 0.0,
            "grouped_shuffle_max_t_adjusted_p_exclusive": GROUPED_SHUFFLE_MAX_T_P_THRESHOLD,
        },
        "gate_decision": {
            "r2_gate_pass": r2_pass,
            "bootstrap_ci_gate_pass": ci_pass,
            "shuffle_comparison_gate_pass": shuffle_pass,
            "positive_control_pass": positive_pass,
        },
        "artifacts": {
            "all_layer_metrics": metrics_identity,
            "bootstrap_results": bootstrap_identity,
            "grouped_shuffle_results": shuffle_identity,
            "input_join_audit": join_identity,
            "oof_prediction_archive": archive_identity,
        },
        "scientific_interpretation_status": (
            "INTERPRETABLE"
            if positive_pass
            else "NOT_INTERPRETABLE_POSITIVE_CONTROL_FAILED"
        ),
    }
    receipt_identity = _publish_json(
        package_root / "positive_control_receipt.json", receipt
    )
    checked = evaluate_positive_control_readiness(receipt)
    if not checked.artifact_present or checked.statistical_gate_pass != positive_pass:
        raise NoWallPositiveControlError(
            f"Published receipt does not validate through readiness gate: {checked}"
        )

    readiness_v0_2 = {
        "schema_id": "integration-bd-production-input-readiness-v0.2",
        "schema_version": "2.0",
        "branch": BRANCH,
        "run_id": RUN_ID,
        "supersedes": {
            "path": str(READINESS_V0_1_RELATIVE),
            "sha256": READINESS_V0_1_SHA256,
            "reason": "Prediction coverage no longer implies positive-control statistical pass.",
        },
        "authority_bindings": authority_bindings,
        "positive_control": {
            "receipt": {
                "path": str(CONTROL_PACKAGE_RELATIVE / "positive_control_receipt.json"),
                "sha256": receipt_identity["sha256"],
                "byte_size": receipt_identity["byte_size"],
            },
            "positive_control_artifact_present": checked.artifact_present,
            "positive_control_statistical_gate_pass": checked.statistical_gate_pass,
            "gate_reason": checked.reason,
        },
        "readiness_decision": {
            "ordinary_d_comparator_prediction_coverage_pass": True,
            "no_wall_positive_control_artifact_present": checked.artifact_present,
            "no_wall_positive_control_statistical_gate_pass": checked.statistical_gate_pass,
            "u1_u2_numerical_results_recomputed": False,
            "u1_u2_interpretation_permitted": checked.statistical_gate_pass,
        },
        "scientific_interpretation_status": (
            "INTERPRETABLE"
            if checked.statistical_gate_pass
            else "NOT_INTERPRETABLE_POSITIVE_CONTROL_FAILED"
        ),
        "historical_positive_control_fallback_allowed": False,
    }
    readiness_v0_2_path = repository / READINESS_V0_2_RELATIVE
    readiness_v0_2_identity = _publish_json(readiness_v0_2_path, readiness_v0_2)
    existing_result_root = repository / "docs/status/integration/bd_u1_u2_production_results_v0_1"
    result_status = {
        "schema_id": "integration-bd-u1-u2-production-result-status-v0-2",
        "schema_version": "2.0",
        "branch": BRANCH,
        "run_id": RUN_ID,
        "supersedes_interpretation_status_only": True,
        "existing_u1_u2_numerical_results_modified": False,
        "existing_result_package": {
            name: _identity(existing_result_root / name, repository)
            for name in (
                "execution_receipt.json",
                "final_verdict.json",
                "fit_provenance.json",
                "oof_prediction_manifest.json",
                "scientific_results.json",
                "sha256_inventory.json",
            )
        },
        "superseding_readiness": readiness_v0_2_identity,
        "positive_control_receipt": receipt_identity,
        "u1_u2_interpretation_permitted": checked.statistical_gate_pass,
        "scientific_interpretation_status": readiness_v0_2["scientific_interpretation_status"],
    }
    result_status_identity = _publish_json(
        repository / RESULT_STATUS_V0_2_RELATIVE, result_status
    )
    return {
        "receipt": receipt,
        "receipt_identity": receipt_identity,
        "readiness_v0_2_identity": readiness_v0_2_identity,
        "result_status_v0_2_identity": result_status_identity,
    }
