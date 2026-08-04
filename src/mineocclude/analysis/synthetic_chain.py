"""CPU-only composition proof for Person B Phase 1.7.

This module composes existing scientific implementations.  It is synthetic
contract evidence only and is never a substitute for later real-data runs.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Any

from mineocclude.analysis.config import DEFAULT_CONFIG_PATH, hash_core_analysis_config
from mineocclude.analysis.manifests import (
    build_event_manifest,
    seal_artifact,
    sha256_value,
    validate_sealed_artifact,
)
from mineocclude.analysis.outputs import build_prediction_artifact, build_result_artifact
from mineocclude.contracts.intervention_request import validate_intervention_request
from mineocclude.intervention.directions import (
    derive_time_orthogonal_direction,
    verify_standardized_raw_equivalence,
)
from mineocclude.intervention.doses import build_alpha_table, decoded_blocks_per_alpha
from mineocclude.intervention.producer import build_intervention_request
from mineocclude.metrics.u1_mean import regression_metrics
from mineocclude.metrics.u2_calibration import calibration_metrics, reconstruct_sigma
from mineocclude.metrics.u3_dynamics import (
    oracle_slope_ratio,
    reveal_snapback,
    trajectory_growth_slopes,
)
from mineocclude.oracle.targets import build_regime_a_target_document
from mineocclude.probes.bridge import (
    build_frame_fold_manifest,
    build_joined_frame_table,
    build_probe_ready_matrices,
    derive_probe_code_sha,
    run_ridge_oof_probe,
)
from mineocclude.probes.ridge import RidgeOOFResult, fit_ridge_oof


SYNTHETIC_CHAIN_VERSION = "person-b-synthetic-analysis-chain-v1.0"
FIXTURE_MARKER = {"synthetic": True, "scientific_use": "forbidden"}
PURE_NOISE_R2_RANGE = (-10.0, 0.25)


class SyntheticAnalysisChainError(ValueError):
    """Raised when the Phase 1 synthetic chain cannot fail closed."""


def _code_sha() -> str:
    digest = hashlib.sha1()
    paths = (
        Path(__file__),
        Path(__file__).resolve().parents[1] / "metrics" / "u1_mean.py",
        Path(__file__).resolve().parents[1] / "metrics" / "u2_calibration.py",
        Path(__file__).resolve().parents[1] / "metrics" / "u3_dynamics.py",
        Path(__file__).resolve().parents[1] / "intervention" / "directions.py",
    )
    for path in paths:
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _mark_sealed(document: Mapping[str, Any], **extra: Any) -> dict[str, Any]:
    validate_sealed_artifact(document)
    payload = dict(document)
    payload.pop("artifact_hash")
    payload.update(FIXTURE_MARKER)
    payload.update(extra)
    return seal_artifact(payload)


def _fit_signal(
    features: Sequence[Sequence[float]],
    targets: Sequence[float],
    folds: Sequence[int],
    layouts: Sequence[str],
) -> RidgeOOFResult:
    return fit_ridge_oof(
        features,
        targets,
        folds,
        layouts,
        alpha_grid=(0.1, 1.0, 10.0, 100.0),
        inner_fold_count=4,
        seed=20260719,
    )


def _prediction_artifact(
    *,
    name: str,
    target_name: str,
    predictions: Sequence[float],
    rows: Sequence[Mapping[str, Any]],
    folds: Sequence[int],
    input_hash: str,
    fold_hash: str,
    layer_idx: int,
    hook_site: str,
    code_sha: str,
    config_hash: str,
) -> dict[str, Any]:
    records = [
        {
            "trajectory_id": row["trajectory_id"],
            "model_frame_idx": row["model_frame_idx"],
            "layout_id": row["layout_id"],
            "fold_idx": fold,
            "prediction": prediction,
            "fit_id": f"{name}:outer_fold_{fold}",
            "prediction_scope": "out_of_fold",
        }
        for row, fold, prediction in zip(rows, folds, predictions, strict=True)
    ]
    return _mark_sealed(
        build_prediction_artifact(
            records,
            artifact_id=f"synthetic_{name}_predictions_v1",
            code_sha=code_sha,
            config_hash=config_hash,
            input_manifest_hash=input_hash,
            fold_manifest_hash=fold_hash,
            model_family="ridge_synthetic_contract",
            target_name=target_name,
            layer_idx=layer_idx,
            hook_site=hook_site,
        ),
        signal_case=name,
    )


def _result_artifact(
    *,
    family: str,
    records: Sequence[Mapping[str, Any]],
    input_hash: str,
    fold_hash: str,
    prediction_hashes: Sequence[str],
    code_sha: str,
    config_hash: str,
) -> dict[str, Any]:
    return _mark_sealed(
        build_result_artifact(
            records,
            artifact_id=f"synthetic_{family.lower()}_result_v1",
            code_sha=code_sha,
            config_hash=config_hash,
            input_manifest_hash=input_hash,
            fold_manifest_hash=fold_hash,
            prediction_manifest_hashes=prediction_hashes,
            analysis_family=family,
        )
    )


def _metric(
    metric_id: str,
    name: str,
    value: float,
    unit: str,
    count: int,
    sample_unit: str,
    *,
    diagnostic: str = "synthetic_contract_only",
) -> dict[str, Any]:
    return {
        "metric_id": metric_id,
        "metric_name": name,
        "value": float(value),
        "unit": unit,
        "sample_count": count,
        "sample_unit": sample_unit,
        "status": "valid",
        "diagnostic": diagnostic,
    }


def run_synthetic_analysis_chain(
    *,
    state_document: Mapping[str, Any],
    activation_package: Mapping[str, Any],
    chunk_payloads_by_id: Mapping[str, bytes],
) -> dict[str, Any]:
    """Execute the complete B Phase 1 synthetic chain deterministically."""

    if not all(isinstance(value, Mapping) for value in (state_document, activation_package)):
        raise SyntheticAnalysisChainError("State and activation inputs must be mappings.")
    if not isinstance(chunk_payloads_by_id, Mapping) or not chunk_payloads_by_id:
        raise SyntheticAnalysisChainError("Activation chunk evidence is required.")
    target_code_sha = hashlib.sha1(
        (Path(__file__).resolve().parents[1] / "oracle" / "targets.py").read_bytes()
    ).hexdigest()
    target_document = build_regime_a_target_document(
        state_document,
        oracle_run_id="synthetic_b_chain_oracle_run_v1",
        oracle_code_sha=target_code_sha,
    )
    frame_table = build_joined_frame_table(activation_package, target_document)
    fold_manifest = build_frame_fold_manifest(
        frame_table,
        artifact_id="synthetic_b_chain_fold_manifest_v1",
        n_splits=5,
        seed=20260719,
    )
    matrices = build_probe_ready_matrices(
        activation_package,
        target_document,
        frame_table,
        fold_manifest,
        chunk_payloads_by_id,
        target_name="mu_oracle_blocks",
    )
    if not matrices:
        raise SyntheticAnalysisChainError("No authenticated activation matrix was built.")
    authenticated_execution = run_ridge_oof_probe(
        matrices[0], artifact_id_prefix="synthetic_b_chain_authenticated_mean"
    )

    matrix = matrices[0]
    rows_by_key = {
        (row["trajectory_id"], row["model_frame_idx"]): row
        for row in target_document["rows"]
    }
    ordered_rows = [
        rows_by_key[(row["trajectory_id"], row["model_frame_idx"])]
        for row in matrix.metadata_rows
    ]
    folds = tuple(matrix.outer_folds)
    layouts = tuple(matrix.layout_ids)
    dimension = len(matrix.features[0])
    if dimension != 2048:
        raise SyntheticAnalysisChainError("Synthetic direction evidence requires 2048-D A activations.")

    # Contract-only signal injection: values are embedded in synthetic
    # activation dimensions, never copied into metadata or legal input fields.
    signal_features: list[list[float]] = []
    for source_vector, row in zip(matrix.features, ordered_rows, strict=True):
        vector = list(source_vector)
        vector[0] = float(row["mu_oracle_blocks"])
        vector[1] = float(row["tau"])
        vector[2] = float(row["log_sigma_oracle"] or 0.0)
        vector[3] = ((row["model_frame_idx"] + 3) * 7 % 11 - 5) / 5.0
        signal_features.append(vector)

    mean_truth = tuple(float(row["mu_oracle_blocks"]) for row in ordered_rows)
    mean_fit = _fit_signal(signal_features, mean_truth, folds, layouts)
    mean_metrics = regression_metrics(mean_truth, mean_fit.predictions)

    eligibility_rows = []
    spread_indices = []
    for index, row in enumerate(ordered_rows):
        eligible = row["log_sigma_oracle"] is not None
        eligibility_rows.append(
            {
                "trajectory_id": row["trajectory_id"],
                "model_frame_idx": row["model_frame_idx"],
                "target_name": "log_sigma_oracle",
                "eligible": eligible,
                "reason": "eligible_hidden_positive_spread" if eligible else "visible_zero_spread_null",
            }
        )
        if eligible:
            spread_indices.append(index)
    if len(spread_indices) + sum(not row["eligible"] for row in eligibility_rows) != len(ordered_rows):
        raise SyntheticAnalysisChainError("Spread eligibility ledger lost rows.")
    ledger = seal_artifact(
        {
            "artifact_type": "synthetic_eligibility_ledger",
            "artifact_id": "synthetic_b_chain_spread_eligibility_v1",
            "code_sha": _code_sha(),
            "config_hash": hash_core_analysis_config(DEFAULT_CONFIG_PATH),
            "input_manifest_hash": frame_table["target_document_hash"],
            **FIXTURE_MARKER,
            "rows": eligibility_rows,
        }
    )

    spread_rows = [ordered_rows[index] for index in spread_indices]
    spread_features = [signal_features[index] for index in spread_indices]
    spread_truth = tuple(float(row["log_sigma_oracle"]) for row in spread_rows)
    spread_folds = tuple(folds[index] for index in spread_indices)
    spread_layouts = tuple(layouts[index] for index in spread_indices)
    spread_fit = _fit_signal(spread_features, spread_truth, spread_folds, spread_layouts)
    decoded_sigma = reconstruct_sigma(spread_fit.predictions)
    oracle_sigma = tuple(float(row["sigma_oracle_blocks"]) for row in spread_rows)
    mean_by_key = {
        (row["trajectory_id"], row["model_frame_idx"]): prediction
        for row, prediction in zip(ordered_rows, mean_fit.predictions, strict=True)
    }
    spread_mean_predictions = tuple(
        mean_by_key[(row["trajectory_id"], row["model_frame_idx"])]
        for row in spread_rows
    )
    calibration = calibration_metrics(
        [float(row["x_true_blocks"]) for row in spread_rows],
        spread_mean_predictions,
        decoded_sigma,
    )

    time_truth = tuple(float(row["tau"]) for row in ordered_rows)
    time_fit = _fit_signal(signal_features, time_truth, folds, layouts)
    time_metrics = regression_metrics(time_truth, time_fit.predictions)
    noise_features = [[0.0] for _ in ordered_rows]
    noise_truth = tuple(
        (((index * 37) % 17) - 8) / 8.0 for index in range(len(ordered_rows))
    )
    noise_fit = _fit_signal(noise_features, noise_truth, folds, layouts)
    noise_metrics = regression_metrics(noise_truth, noise_fit.predictions)
    if not PURE_NOISE_R2_RANGE[0] <= noise_metrics.r2 <= PURE_NOISE_R2_RANGE[1]:
        raise SyntheticAnalysisChainError("Pure-noise OOF diagnostic left its predeclared range.")

    code_sha = _code_sha()
    config_hash = hash_core_analysis_config(DEFAULT_CONFIG_PATH)
    signal_matrix_hash = sha256_value(
        {
            "identities": [
                [row["trajectory_id"], row["model_frame_idx"]] for row in ordered_rows
            ],
            "features": signal_features,
            "mean_targets": mean_truth,
            "folds": folds,
            **FIXTURE_MARKER,
        }
    )
    mean_prediction = _prediction_artifact(
        name="decodable_mean",
        target_name="mu_oracle_blocks",
        predictions=mean_fit.predictions,
        rows=ordered_rows,
        folds=folds,
        input_hash=signal_matrix_hash,
        fold_hash=fold_manifest["artifact_hash"],
        layer_idx=matrix.layer_idx,
        hook_site=matrix.hook_site,
        code_sha=code_sha,
        config_hash=config_hash,
    )
    spread_prediction = _prediction_artifact(
        name="decodable_log_spread",
        target_name="log_sigma_oracle",
        predictions=spread_fit.predictions,
        rows=spread_rows,
        folds=spread_folds,
        input_hash=ledger["artifact_hash"],
        fold_hash=fold_manifest["artifact_hash"],
        layer_idx=matrix.layer_idx,
        hook_site=matrix.hook_site,
        code_sha=code_sha,
        config_hash=config_hash,
    )
    time_prediction = _prediction_artifact(
        name="time_only_diagnostic",
        target_name="tau_seconds_diagnostic",
        predictions=time_fit.predictions,
        rows=ordered_rows,
        folds=folds,
        input_hash=signal_matrix_hash,
        fold_hash=fold_manifest["artifact_hash"],
        layer_idx=matrix.layer_idx,
        hook_site=matrix.hook_site,
        code_sha=code_sha,
        config_hash=config_hash,
    )
    noise_prediction = _prediction_artifact(
        name="pure_noise_diagnostic",
        target_name="synthetic_noise_diagnostic",
        predictions=noise_fit.predictions,
        rows=ordered_rows,
        folds=folds,
        input_hash=signal_matrix_hash,
        fold_hash=fold_manifest["artifact_hash"],
        layer_idx=matrix.layer_idx,
        hook_site=matrix.hook_site,
        code_sha=code_sha,
        config_hash=config_hash,
    )

    u1 = _result_artifact(
        family="U1",
        records=(
            _metric("u1_r2", "out_of_fold_r2", mean_metrics.r2, "dimensionless", len(mean_truth), "frame"),
            _metric("u1_mae", "out_of_fold_mae", mean_metrics.mae, "blocks", len(mean_truth), "frame"),
        ),
        input_hash=signal_matrix_hash,
        fold_hash=fold_manifest["artifact_hash"],
        prediction_hashes=(mean_prediction["artifact_hash"],),
        code_sha=code_sha,
        config_hash=config_hash,
    )
    u2 = _result_artifact(
        family="U2",
        records=(
            _metric("u2_ece", "expected_calibration_error", calibration.expected_calibration_error, "dimensionless", len(spread_rows), "frame"),
            _metric("u2_z_rms", "z_root_mean_square", calibration.z_diagnostics.root_mean_square, "dimensionless", len(spread_rows), "frame"),
        ),
        input_hash=ledger["artifact_hash"],
        fold_hash=fold_manifest["artifact_hash"],
        prediction_hashes=(mean_prediction["artifact_hash"], spread_prediction["artifact_hash"]),
        code_sha=code_sha,
        config_hash=config_hash,
    )

    trajectory_ids = [row["trajectory_id"] for row in spread_rows]
    tau_seconds = [float(row["tau"]) for row in spread_rows]
    visibility = [row["visibility"] for row in spread_rows]
    decoded_slopes = trajectory_growth_slopes(
        trajectory_ids, tau_seconds, decoded_sigma, visibility
    )
    oracle_slopes = trajectory_growth_slopes(
        trajectory_ids, tau_seconds, oracle_sigma, visibility
    )
    slope_ratios = oracle_slope_ratio(decoded_slopes, oracle_slopes)
    snapback = reveal_snapback(
        ["reveal_a", "reveal_a", "reveal_b", "reveal_b"],
        [-0.05, 0.0, -0.05, 0.0],
        [0.20, 0.05, 0.24, 0.06],
        ["occluded", "visible", "occluded", "visible"],
    )
    u3 = _result_artifact(
        family="U3",
        records=(
            _metric("u3_slope_ratio", "mean_oracle_slope_ratio", sum(slope_ratios.values()) / len(slope_ratios), "dimensionless", len(slope_ratios), "trajectory"),
            _metric("u3_reveal_snapback", "median_reveal_reduction_fraction", snapback.median_reduction_fraction, "fraction", len(snapback.pairs), "event"),
        ),
        input_hash=ledger["artifact_hash"],
        fold_hash=fold_manifest["artifact_hash"],
        prediction_hashes=(spread_prediction["artifact_hash"],),
        code_sha=code_sha,
        config_hash=config_hash,
    )

    diagnostic = _result_artifact(
        family="diagnostic",
        records=(
            _metric("time_r2", "time_only_out_of_fold_r2", time_metrics.r2, "dimensionless", len(time_truth), "frame", diagnostic="time_only_diagnostic_not_scientific_evidence"),
            _metric("noise_r2", "pure_noise_out_of_fold_r2", noise_metrics.r2, "dimensionless", len(noise_truth), "frame", diagnostic=f"predeclared_range={PURE_NOISE_R2_RANGE}"),
        ),
        input_hash=signal_matrix_hash,
        fold_hash=fold_manifest["artifact_hash"],
        prediction_hashes=(time_prediction["artifact_hash"], noise_prediction["artifact_hash"]),
        code_sha=code_sha,
        config_hash=config_hash,
    )

    selection_fold = max(fit.outer_fold_idx for fit in mean_fit.fits)
    mean_fold_fit = next(fit for fit in mean_fit.fits if fit.outer_fold_idx == selection_fold)
    time_fold_fit = next(fit for fit in time_fit.fits if fit.outer_fold_idx == selection_fold)
    direction = derive_time_orthogonal_direction(
        mean_fold_fit.model.standardized_coefficients,
        mean_fold_fit.model.scaler.scale,
        time_fold_fit.model.standardized_coefficients,
        time_fold_fit.model.scaler.scale,
    )
    equivalence_error = verify_standardized_raw_equivalence(
        [signal_features[index] for index in mean_fold_fit.training_indices],
        standardized_coefficients=mean_fold_fit.model.standardized_coefficients,
        standardized_intercept=mean_fold_fit.model.standardized_intercept,
        scaler_mean=mean_fold_fit.model.scaler.mean,
        scaler_scale=mean_fold_fit.model.scaler.scale,
    )
    blocks_per_alpha = decoded_blocks_per_alpha(
        mean_fold_fit.model.raw_coefficients,
        direction.unit_residual_direction,
    )
    doses = build_alpha_table(
        (-1.0, 0.0, 1.0),
        blocks_per_alpha=blocks_per_alpha,
        typical_activation_norm=10.0,
    )
    intervention_request = build_intervention_request(
        request_id="synthetic_b_chain_intervention_request_v1",
        direction_version="synthetic_b_chain_mean_time_orthogonal_v1",
        source_run_id="synthetic_b_chain_direction_run_v1",
        direction=direction,
        layer_idx=matrix.layer_idx,
        hook_site=matrix.hook_site,
        timestep_idx=8,
        doses=doses,
        typical_activation_norm=10.0,
        scaler_id=f"synthetic_outer_fold_{selection_fold}_scaler",
        scaler_hash=sha256_value(asdict(mean_fold_fit.model.scaler)),
        activation_norm_artifact_hash=sha256_value(
            {"matrix_hash": signal_matrix_hash, "typical_activation_norm": 10.0}
        ),
        fit_manifest=build_event_manifest("synthetic_fit_events_v1", ["fit_event_v1"]),
        validation_manifest=build_event_manifest(
            "synthetic_validation_events_v1", ["validation_event_v1"]
        ),
        heldout_events=[
            {
                "event_id": "heldout_event_v1",
                "trajectory_id": "synthetic_heldout_trajectory_v1",
                "layout_id": "synthetic_heldout_layout_v1",
            }
        ],
        raw_space_equivalence_max_error=equivalence_error,
    )
    intervention_request.update(FIXTURE_MARKER)
    request_validation = validate_intervention_request(intervention_request)
    if not request_validation.accepted:
        raise SyntheticAnalysisChainError("Synthetic intervention request was rejected.")

    bundle = seal_artifact(
        {
            "artifact_type": "synthetic_analysis_result_bundle",
            "artifact_id": "synthetic_b_phase1_chain_bundle_v1",
            "code_sha": code_sha,
            "config_hash": config_hash,
            "input_manifest_hash": frame_table["frame_table_hash"],
            **FIXTURE_MARKER,
            "chain_version": SYNTHETIC_CHAIN_VERSION,
            "stage_artifact_hashes": {
                "fold_manifest": fold_manifest["artifact_hash"],
                "eligibility_ledger": ledger["artifact_hash"],
                "mean_predictions": mean_prediction["artifact_hash"],
                "spread_predictions": spread_prediction["artifact_hash"],
                "time_predictions": time_prediction["artifact_hash"],
                "noise_predictions": noise_prediction["artifact_hash"],
                "u1": u1["artifact_hash"],
                "u2": u2["artifact_hash"],
                "u3": u3["artifact_hash"],
                "diagnostic": diagnostic["artifact_hash"],
                "intervention_request": sha256_value(intervention_request),
            },
        }
    )
    return {
        "schema_version": "1.0",
        "chain_version": SYNTHETIC_CHAIN_VERSION,
        **FIXTURE_MARKER,
        "status": "passed",
        "target_document": target_document,
        "target_document_hash": frame_table["target_document_hash"],
        "frame_table": frame_table,
        "fold_manifest": fold_manifest,
        "authenticated_activation_probe": {
            "matrix_hash": matrix.matrix_hash,
            "prediction_artifact_hash": authenticated_execution.prediction_artifact["artifact_hash"],
            "u1_artifact_hash": authenticated_execution.u1_result_artifact["artifact_hash"],
        },
        "eligibility_ledger": ledger,
        "prediction_artifacts": {
            "decodable_mean": mean_prediction,
            "decodable_log_spread": spread_prediction,
            "time_only": time_prediction,
            "pure_noise": noise_prediction,
        },
        "result_artifacts": {"U1": u1, "U2": u2, "U3": u3, "diagnostic": diagnostic},
        "intervention_request": intervention_request,
        "result_bundle": bundle,
        "signal_expectations": {
            "decodable_mean_r2": mean_metrics.r2,
            "decodable_log_spread_r2": regression_metrics(spread_truth, spread_fit.predictions).r2,
            "time_only_r2": time_metrics.r2,
            "pure_noise_r2": noise_metrics.r2,
            "pure_noise_predeclared_range": list(PURE_NOISE_R2_RANGE),
        },
        "fit_audit": {
            "layout_disjoint": all(
                set(layouts[index] for index in fit.training_indices).isdisjoint(
                    set(layouts[index] for index in fit.test_indices)
                )
                for fit in mean_fit.fits
            ),
            "preprocessing_scope": "outer_training_rows_only",
            "feature_sources": ["synthetic_activation_signal"],
            "forbidden_feature_sources": [],
            "direction_selection_outer_fold": selection_fold,
        },
    }
