"""Real-pilot preparation and staged Person B probe execution.

This module implements the artifact-independent part of roadmap steps 6.1
through 6.5.  It cannot manufacture A/C inputs, approve the visible-control
gate, or turn a one-trajectory plumbing check into a population result.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from mineocclude.analysis.config import (
    hash_core_analysis_config,
    load_core_analysis_config,
)
from mineocclude.analysis.filters import (
    FilterResult,
    apply_ordered_filters,
    build_filter_audit_artifact,
)
from mineocclude.analysis.manifests import (
    AnalysisArtifactError,
    is_hex_digest,
    seal_artifact,
    sha256_value,
    validate_sealed_artifact,
)
from mineocclude.analysis.selection import (
    SCOPE_HIDDEN_MEAN,
    SCOPE_HIDDEN_SPREAD,
    SCOPE_VISIBLE_NO_WALL,
    selected_frame_keys,
    validate_analysis_selection_manifest,
)
from mineocclude.analysis.outputs import build_result_artifact
from mineocclude.metrics.u2_calibration import (
    U2MetricError,
    calibration_metrics,
    partial_correlation_controlling_tau,
    reconstruct_sigma,
)
from mineocclude.probes.bridge import (
    ProbeReadyMatrix,
    RidgePermutationExecution,
    RidgeProbeExecution,
    build_frame_fold_manifest,
    build_joined_frame_table,
    build_probe_ready_matrices,
    derive_probe_code_sha,
    load_activation_vectors,
    run_grouped_ridge_permutation,
    run_ridge_oof_probe,
)
from mineocclude.probes.join import (
    ActivationTargetJoinError,
    join_activation_target_document,
)
from mineocclude.probes.ridge import ProbeFitError, fit_ridge
from mineocclude.oracle.audit import build_oracle_audit


PILOT_INTAKE_SCHEMA_VERSION = "person-b-pilot-intake-v0.1"
CONTROL_GATE_SCHEMA_VERSION = "person-b-positive-control-gate-v0.1"
SCOPE_BUNDLE_SCHEMA_VERSION = "person-b-probe-scope-bundle-v0.1"


class PilotAnalysisError(ValueError):
    """Raised when real-pilot execution is premature or unauthenticated."""


@dataclass(frozen=True)
class PilotPreparation:
    frame_table: Mapping[str, Any]
    oracle_audit: Mapping[str, Any]
    filter_result: FilterResult
    filter_audit: Mapping[str, Any]
    intake_receipt: Mapping[str, Any]
    fold_manifest: Mapping[str, Any] | None
    execution_class: str


@dataclass(frozen=True)
class ProbeScopeRun:
    scope: str
    target_name: str
    matrices: tuple[ProbeReadyMatrix, ...]
    ridge_runs: tuple[RidgeProbeExecution, ...]
    permutation_runs: tuple[RidgePermutationExecution, ...]
    bundle: Mapping[str, Any]


@dataclass(frozen=True)
class U2PilotRun:
    result_artifacts: tuple[Mapping[str, Any], ...]
    bundle: Mapping[str, Any]


def build_pilot_failure_artifact(
    *,
    artifact_id: str,
    stage: str,
    input_manifest_hash: str,
    error: BaseException,
    source_synthetic: bool,
) -> dict[str, Any]:
    """Persist a fail-closed pilot error without turning it into a zero result."""

    if not isinstance(stage, str) or not stage:
        raise PilotAnalysisError("Failure stage must be non-empty.")
    if not is_hex_digest(input_manifest_hash, 64):
        raise PilotAnalysisError("Failure input hash must be SHA-256.")
    rejection_code = getattr(error, "code", None)
    if hasattr(rejection_code, "value"):
        rejection_code = rejection_code.value
    if rejection_code is None:
        rejection_code = error.__class__.__name__
    return seal_artifact(
        {
            "artifact_type": "pilot_failure",
            "artifact_id": artifact_id,
            "code_sha": derive_probe_code_sha(),
            "config_hash": hash_core_analysis_config(),
            "input_manifest_hash": input_manifest_hash,
            "failure_schema_version": "person-b-pilot-failure-v0.1",
            "stage": stage,
            "rejection_code": str(rejection_code),
            "message": str(error),
            "outcome_value": None,
            "status": "failed",
            "source_synthetic": source_synthetic,
            "synthetic": source_synthetic,
            "scientific_use": "forbidden",
        }
    )


def _scope_target_name(scope: str) -> str:
    target_by_scope = {
        SCOPE_VISIBLE_NO_WALL: "x_true_blocks",
        SCOPE_HIDDEN_MEAN: "mu_oracle_blocks",
        SCOPE_HIDDEN_SPREAD: "log_sigma_oracle",
    }
    target_name = target_by_scope.get(scope)
    if target_name is None:
        raise PilotAnalysisError(f"Unknown probe scope: {scope!r}.")
    return target_name


def _layer_sites(activation_package: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = activation_package.get("index_rows")
    if not isinstance(rows, list):
        raise PilotAnalysisError("Activation index rows are malformed.")
    sites = {
        (row.get("layer_idx"), row.get("hook_site"))
        for row in rows
        if isinstance(row, Mapping)
    }
    if any(
        not isinstance(layer, int)
        or isinstance(layer, bool)
        or layer < 0
        or not isinstance(site, str)
        or not site
        for layer, site in sites
    ):
        raise PilotAnalysisError("Activation layer/site metadata is invalid.")
    return [
        {"layer_idx": layer, "hook_site": site}
        for layer, site in sorted(sites)
    ]


def prepare_pilot_inputs(
    activation_package: Mapping[str, Any],
    target_document: Mapping[str, Any],
    chunk_payloads_by_id: Mapping[str, bytes],
    *,
    artifact_id_prefix: str,
) -> PilotPreparation:
    """Authenticate the exact A/B pilot sources and persist intake evidence."""

    if not isinstance(artifact_id_prefix, str) or not artifact_id_prefix:
        raise PilotAnalysisError("artifact_id_prefix must be non-empty.")
    frame_table = build_joined_frame_table(activation_package, target_document)
    # Loading here authenticates every literal chunk byte and exact index claim
    # before a receipt can call the activation handoff usable.
    load_activation_vectors(activation_package, chunk_payloads_by_id)
    filter_result = apply_ordered_filters(
        target_document["rows"],
        accepted_manifest_hash=frame_table["accepted_manifest_hash"],
    )
    code_sha = derive_probe_code_sha()
    config_hash = hash_core_analysis_config()
    oracle_audit = build_oracle_audit(
        target_document,
        artifact_id=f"{artifact_id_prefix}:oracle_audit",
    )
    if oracle_audit["status"] != "pass":
        raise PilotAnalysisError(
            "Independent oracle audit failed; real joining/fitting is blocked."
        )
    filter_audit = build_filter_audit_artifact(
        filter_result,
        artifact_id=f"{artifact_id_prefix}:filter_audit",
        code_sha=code_sha,
        config_hash=config_hash,
        input_manifest_hash=frame_table["target_document_hash"],
    )
    filter_payload = dict(filter_audit)
    filter_payload.pop("artifact_hash")
    filter_payload.update(
        {
            "synthetic": frame_table["synthetic"],
            "scientific_use": frame_table["scientific_use"],
        }
    )
    filter_audit = seal_artifact(filter_payload)
    if filter_result.accepted_count != len(target_document["rows"]):
        raise PilotAnalysisError(
            "Validated target rows failed the frozen ordered filter; inspect "
            "the returned filter audit before continuing."
        )

    layouts = sorted({row["layout_id"] for row in frame_table["rows"]})
    trajectories = sorted(
        {row["trajectory_id"] for row in frame_table["rows"]}
    )
    execution_class = (
        "evaluative_grouped_oof"
        if len(layouts) >= 5
        else "plumbing_only_insufficient_layouts"
    )
    fold_manifest = (
        build_frame_fold_manifest(
            frame_table,
            artifact_id=f"{artifact_id_prefix}:folds",
        )
        if execution_class == "evaluative_grouped_oof"
        else None
    )
    try:
        intake_receipt = seal_artifact(
            {
                "artifact_type": "pilot_intake_receipt",
                "artifact_id": f"{artifact_id_prefix}:intake",
                "code_sha": code_sha,
                "config_hash": config_hash,
                "input_manifest_hash": frame_table["artifact_hash"],
                "pilot_intake_schema_version": PILOT_INTAKE_SCHEMA_VERSION,
                "activation_handoff_id": activation_package["handoff_id"],
                "activation_run_id": activation_package["run_id"],
                "activation_handoff_hash": frame_table[
                    "activation_handoff_hash"
                ],
                "target_run_id": frame_table["target_run_id"],
                "target_document_hash": frame_table["target_document_hash"],
                "frame_table_hash": frame_table["frame_table_hash"],
                "oracle_audit_hash": oracle_audit["artifact_hash"],
                "chunk_hashes": sorted(
                    (
                        {
                            "activation_chunk_id": descriptor["chunk_id"],
                            "sha256": descriptor["sha256"],
                        }
                        for descriptor in activation_package["chunks"]
                    ),
                    key=lambda row: row["activation_chunk_id"],
                ),
                "accepted_manifest_hash": frame_table[
                    "accepted_manifest_hash"
                ],
                "layout_ids": layouts,
                "trajectory_ids": trajectories,
                "frame_count": len(frame_table["rows"]),
                "layer_sites": _layer_sites(activation_package),
                "execution_class": execution_class,
                "fold_manifest_hash": (
                    fold_manifest["artifact_hash"]
                    if fold_manifest is not None
                    else None
                ),
                "filter_audit_hash": filter_audit["artifact_hash"],
                "synthetic": frame_table["synthetic"],
                "scientific_use": frame_table["scientific_use"],
                "status": "accepted",
                "interpretation": (
                    "eligible_for_grouped_oof"
                    if fold_manifest is not None
                    else "plumbing_evidence_only_not_a_population_claim"
                ),
            }
        )
    except (AnalysisArtifactError, KeyError, TypeError) as error:
        raise PilotAnalysisError(f"Could not build pilot receipt: {error}") from error
    return PilotPreparation(
        frame_table=frame_table,
        oracle_audit=oracle_audit,
        filter_result=filter_result,
        filter_audit=filter_audit,
        intake_receipt=intake_receipt,
        fold_manifest=fold_manifest,
        execution_class=execution_class,
    )


def run_probe_scope(
    preparation: PilotPreparation,
    activation_package: Mapping[str, Any],
    target_document: Mapping[str, Any],
    chunk_payloads_by_id: Mapping[str, bytes],
    selection_manifest: Mapping[str, Any],
    *,
    scope: str,
    artifact_id_prefix: str,
    permutation_count: int | None = None,
) -> ProbeScopeRun:
    """Run all declared layer/sites for one authenticated analysis scope."""

    if preparation.fold_manifest is None:
        raise PilotAnalysisError(
            "Grouped OOF probes require at least five layouts. This intake is "
            "plumbing evidence only."
        )
    target_name = _scope_target_name(scope)
    validate_analysis_selection_manifest(
        selection_manifest,
        frame_table=preparation.frame_table,
    )
    keys = selected_frame_keys(
        selection_manifest,
        scope=scope,
        frame_table=preparation.frame_table,
    )
    matrices = build_probe_ready_matrices(
        activation_package,
        target_document,
        preparation.frame_table,
        preparation.fold_manifest,
        chunk_payloads_by_id,
        target_name=target_name,
        selected_frame_keys=keys,
        selection_manifest_hash=selection_manifest["artifact_hash"],
        analysis_scope=scope,
    )
    ridge_runs: list[RidgeProbeExecution] = []
    permutation_runs: list[RidgePermutationExecution] = []
    for matrix in matrices:
        layer_prefix = (
            f"{artifact_id_prefix}:{scope}:layer_{matrix.layer_idx}:"
            f"{matrix.hook_site}"
        )
        ridge = run_ridge_oof_probe(
            matrix,
            artifact_id_prefix=layer_prefix,
        )
        permutation = run_grouped_ridge_permutation(
            matrix,
            ridge,
            artifact_id=f"{layer_prefix}:grouped_permutation",
            permutation_count=permutation_count,
        )
        ridge_runs.append(ridge)
        permutation_runs.append(permutation)

    records = []
    for matrix, ridge, permutation in zip(
        matrices,
        ridge_runs,
        permutation_runs,
    ):
        records.append(
            {
                "layer_idx": matrix.layer_idx,
                "hook_site": matrix.hook_site,
                "matrix_hash": matrix.matrix_hash,
                "matrix_artifact_hash": ridge.matrix_artifact["artifact_hash"],
                "row_count": len(matrix.targets),
                "prediction_artifact_hash": ridge.prediction_artifact[
                    "artifact_hash"
                ],
                "scaler_artifact_hashes": [
                    artifact["artifact_hash"]
                    for artifact in ridge.scaler_artifacts
                ],
                "fit_artifact_hashes": [
                    artifact["artifact_hash"] for artifact in ridge.fit_artifacts
                ],
                "metric_artifact_hash": ridge.u1_result_artifact[
                    "artifact_hash"
                ],
                "permutation_artifact_hash": permutation.result_artifact[
                    "artifact_hash"
                ],
                "observed_r2": permutation.observed_r2,
                "grouped_permutation_p_value": permutation.p_value,
                "observed_above_null_median": (
                    permutation.observed_r2
                    > sorted(permutation.null_r2)[
                        len(permutation.null_r2) // 2
                    ]
                    if permutation.observed_r2 is not None
                    and permutation.null_r2
                    else None
                ),
            }
        )
    try:
        bundle = seal_artifact(
            {
                "artifact_type": "probe_scope_bundle",
                "artifact_id": f"{artifact_id_prefix}:{scope}:bundle",
                "code_sha": derive_probe_code_sha(),
                "config_hash": hash_core_analysis_config(),
                "input_manifest_hash": preparation.frame_table[
                    "frame_table_hash"
                ],
                "scope_bundle_schema_version": SCOPE_BUNDLE_SCHEMA_VERSION,
                "scope": scope,
                "target_name": target_name,
                "selection_manifest_hash": selection_manifest["artifact_hash"],
                "fold_manifest_hash": preparation.fold_manifest[
                    "artifact_hash"
                ],
                "filter_audit_hash": preparation.filter_audit["artifact_hash"],
                "intake_receipt_hash": preparation.intake_receipt[
                    "artifact_hash"
                ],
                "layer_site_records": records,
                "synthetic": preparation.frame_table["synthetic"],
                "scientific_use": preparation.frame_table["scientific_use"],
                "interpretation": (
                    "control_evidence_requires_recorded_gate_decision"
                    if scope == SCOPE_VISIBLE_NO_WALL
                    else "hidden_probe_evidence"
                ),
            }
        )
    except (AnalysisArtifactError, KeyError, TypeError) as error:
        raise PilotAnalysisError(f"Could not seal scope bundle: {error}") from error
    return ProbeScopeRun(
        scope=scope,
        target_name=target_name,
        matrices=matrices,
        ridge_runs=tuple(ridge_runs),
        permutation_runs=tuple(permutation_runs),
        bundle=bundle,
    )


def run_plumbing_smoke(
    preparation: PilotPreparation,
    activation_package: Mapping[str, Any],
    target_document: Mapping[str, Any],
    chunk_payloads_by_id: Mapping[str, bytes],
    selection_manifest: Mapping[str, Any],
    *,
    scope: str,
    artifact_id: str,
) -> dict[str, Any]:
    """Exercise literal vectors and fit/predict shapes without a scientific metric.

    This path exists for the one-trajectory pilot in roadmap Step 6.5. It fits
    and predicts on the same selected rows, publishes no R²/MAE/p-value, and is
    always forbidden for scientific use even when its source rows are real.
    """

    if preparation.fold_manifest is not None:
        raise PilotAnalysisError(
            "Plumbing smoke is only for an intake that cannot support grouped OOF."
        )
    validate_analysis_selection_manifest(
        selection_manifest,
        frame_table=preparation.frame_table,
    )
    target_name = _scope_target_name(scope)
    keys = set(
        selected_frame_keys(
            selection_manifest,
            scope=scope,
            frame_table=preparation.frame_table,
        )
    )
    vectors = load_activation_vectors(activation_package, chunk_payloads_by_id)
    try:
        joined = join_activation_target_document(
            activation_package,
            target_document,
        )
    except ActivationTargetJoinError as error:
        raise PilotAnalysisError(f"Plumbing join failed: {error}") from error
    rows_by_site: dict[tuple[int, str], list[Any]] = {}
    for item in joined:
        activation = item.activation_index_row
        frame_key = (
            activation["trajectory_id"],
            activation["model_frame_idx"],
        )
        if frame_key not in keys:
            continue
        site = (activation["layer_idx"], activation["hook_site"])
        rows_by_site.setdefault(site, []).append(item)
    if not rows_by_site:
        raise PilotAnalysisError("Plumbing selection resolved no activation rows.")

    site_records: list[dict[str, Any]] = []
    for (layer_idx, hook_site), items in sorted(rows_by_site.items()):
        ordered = sorted(
            items,
            key=lambda item: (
                item.activation_index_row["trajectory_id"],
                item.activation_index_row["model_frame_idx"],
            ),
        )
        features = []
        targets = []
        identities = []
        for item in ordered:
            activation = item.activation_index_row
            target = item.target_row.get(target_name)
            if (
                isinstance(target, bool)
                or not isinstance(target, (int, float))
                or not math.isfinite(float(target))
            ):
                raise PilotAnalysisError(
                    f"Plumbing row lacks finite {target_name}."
                )
            claim = (
                activation["activation_chunk_id"],
                activation["chunk_row_idx"],
            )
            features.append(vectors[claim])
            targets.append(float(target))
            identities.append(
                {
                    "trajectory_id": activation["trajectory_id"],
                    "model_frame_idx": activation["model_frame_idx"],
                    "layout_id": activation["layout_id"],
                }
            )
        try:
            model = fit_ridge(features, targets, alpha=1.0)
            predictions = model.predict(features)
            raw_predictions = model.predict_raw_equivalent(features)
        except ProbeFitError as error:
            raise PilotAnalysisError(f"Plumbing fit failed: {error}") from error
        site_records.append(
            {
                "layer_idx": layer_idx,
                "hook_site": hook_site,
                "row_count": len(ordered),
                "feature_count": len(features[0]),
                "fixed_alpha": 1.0,
                "fit_scope": "in_sample_plumbing_only",
                "prediction_scope": "in_sample_plumbing_only",
                "identities": identities,
                "prediction_shape": [len(predictions)],
                "finite_predictions": all(
                    math.isfinite(value) for value in predictions
                ),
                "raw_standardized_prediction_max_abs_difference": max(
                    abs(left - right)
                    for left, right in zip(predictions, raw_predictions)
                ),
                "feature_hash": sha256_value(
                    [list(vector) for vector in features]
                ),
                "target_hash": sha256_value(targets),
                "prediction_hash": sha256_value(list(predictions)),
            }
        )
    return seal_artifact(
        {
            "artifact_type": "pilot_plumbing_smoke",
            "artifact_id": artifact_id,
            "code_sha": derive_probe_code_sha(),
            "config_hash": hash_core_analysis_config(),
            "input_manifest_hash": preparation.frame_table["frame_table_hash"],
            "plumbing_smoke_schema_version": "person-b-pilot-smoke-v0.1",
            "scope": scope,
            "target_name": target_name,
            "selection_manifest_hash": selection_manifest["artifact_hash"],
            "intake_receipt_hash": preparation.intake_receipt["artifact_hash"],
            "site_records": site_records,
            "source_synthetic": preparation.frame_table["synthetic"],
            "synthetic": preparation.frame_table["synthetic"],
            "scientific_use": "forbidden",
            "reported_metrics": [],
            "interpretation": "plumbing_only_not_a_population_claim",
        }
    )


def build_positive_control_gate(
    control_run: ProbeScopeRun | Mapping[str, Any],
    *,
    decision: str,
    approver: str,
    rationale: str,
) -> dict[str, Any]:
    """Record the required human decision before hidden-result interpretation."""

    bundle = (
        control_run.bundle
        if isinstance(control_run, ProbeScopeRun)
        else control_run
    )
    if (
        not isinstance(bundle, Mapping)
        or bundle.get("artifact_type") != "probe_scope_bundle"
        or bundle.get("scope") != SCOPE_VISIBLE_NO_WALL
    ):
        raise PilotAnalysisError("Gate evidence must be the visible no-wall scope.")
    try:
        validate_sealed_artifact(bundle, expected_type="probe_scope_bundle")
    except AnalysisArtifactError as error:
        raise PilotAnalysisError(
            f"Control bundle is not authenticated: {error}"
        ) from error
    if decision not in {"pass", "stop_for_diagnosis"}:
        raise PilotAnalysisError("Control decision must be pass or stop_for_diagnosis.")
    if not isinstance(approver, str) or not approver.strip():
        raise PilotAnalysisError("Control gate requires a named approver.")
    if not isinstance(rationale, str) or not rationale.strip():
        raise PilotAnalysisError("Control gate requires a rationale.")
    return seal_artifact(
        {
            "artifact_type": "positive_control_gate",
            "artifact_id": f"{bundle['artifact_id']}:gate",
            "code_sha": bundle["code_sha"],
            "config_hash": bundle["config_hash"],
            "input_manifest_hash": bundle["artifact_hash"],
            "control_gate_schema_version": CONTROL_GATE_SCHEMA_VERSION,
            "control_scope": SCOPE_VISIBLE_NO_WALL,
            "control_bundle_hash": bundle["artifact_hash"],
            "decision": decision,
            "approver": approver,
            "rationale": rationale,
            "threshold_policy": (
                "human_scientific_gate_no_unfrozen_numeric_threshold"
            ),
            "synthetic": bundle["synthetic"],
            "scientific_use": bundle["scientific_use"],
        }
    )


def require_positive_control_pass(
    gate: Mapping[str, Any],
    *,
    control_run: ProbeScopeRun,
) -> None:
    """Fail closed unless the exact visible-control bundle was approved."""

    try:
        validate_sealed_artifact(gate, expected_type="positive_control_gate")
        if (
            gate.get("artifact_type") != "positive_control_gate"
            or gate.get("control_gate_schema_version")
            != CONTROL_GATE_SCHEMA_VERSION
            or gate.get("control_bundle_hash")
            != control_run.bundle["artifact_hash"]
            or gate.get("input_manifest_hash")
            != control_run.bundle["artifact_hash"]
            or gate.get("decision") != "pass"
            or not is_hex_digest(gate.get("artifact_hash"), 64)
        ):
            raise PilotAnalysisError(
                "Hidden probes require a passing gate for the exact control bundle."
            )
    except (AnalysisArtifactError, AttributeError, KeyError, TypeError) as error:
        raise PilotAnalysisError("Positive-control gate is malformed.") from error


def build_u2_pilot_metrics(
    mean_run: ProbeScopeRun,
    spread_run: ProbeScopeRun,
    *,
    control_run: ProbeScopeRun,
    control_gate: Mapping[str, Any],
    artifact_id_prefix: str,
) -> U2PilotRun:
    """Combine paired OOF mean/spread predictions into U2 calibration evidence."""

    require_positive_control_pass(control_gate, control_run=control_run)
    if mean_run.scope != SCOPE_HIDDEN_MEAN or spread_run.scope != SCOPE_HIDDEN_SPREAD:
        raise PilotAnalysisError("U2 requires hidden-mean and hidden-spread runs.")
    mean_by_site = {
        (matrix.layer_idx, matrix.hook_site): (matrix, ridge)
        for matrix, ridge in zip(mean_run.matrices, mean_run.ridge_runs)
    }
    spread_by_site = {
        (matrix.layer_idx, matrix.hook_site): (matrix, ridge)
        for matrix, ridge in zip(spread_run.matrices, spread_run.ridge_runs)
    }
    if mean_by_site.keys() != spread_by_site.keys():
        raise PilotAnalysisError("Mean and spread runs cover different layer/sites.")
    config = load_core_analysis_config()
    levels = tuple(float(value) for value in config["coverage_levels"])
    results: list[Mapping[str, Any]] = []
    bundle_rows: list[dict[str, Any]] = []
    for layer_site in sorted(mean_by_site):
        mean_matrix, mean_ridge = mean_by_site[layer_site]
        spread_matrix, spread_ridge = spread_by_site[layer_site]
        mean_keys = [
            (row["trajectory_id"], row["model_frame_idx"])
            for row in mean_matrix.metadata_rows
        ]
        spread_keys = [
            (row["trajectory_id"], row["model_frame_idx"])
            for row in spread_matrix.metadata_rows
        ]
        mean_index_by_key = {
            key: index for index, key in enumerate(mean_keys)
        }
        if len(mean_index_by_key) != len(mean_keys) or not set(
            spread_keys
        ) <= mean_index_by_key.keys():
            raise PilotAnalysisError(
                f"Spread rows are not an exact subset of mean rows at {layer_site!r}."
            )
        aligned_mean_indices = [
            mean_index_by_key[key] for key in spread_keys
        ]
        aligned_mean_predictions = tuple(
            mean_ridge.oof_result.predictions[index]
            for index in aligned_mean_indices
        )
        decoded_sigma = reconstruct_sigma(spread_ridge.oof_result.predictions)
        oracle_sigma = reconstruct_sigma(spread_matrix.targets)
        truth = tuple(
            float(mean_matrix.metadata_rows[index]["x_true_blocks"])
            for index in aligned_mean_indices
        )
        tau = tuple(
            float(mean_matrix.metadata_rows[index]["tau"])
            for index in aligned_mean_indices
        )
        metric_records: list[dict[str, Any]] = []
        try:
            partial = partial_correlation_controlling_tau(
                decoded_sigma,
                oracle_sigma,
                tau,
            )
            metric_records.append(
                {
                    "metric_id": "u2_partial_correlation_controlling_tau",
                    "metric_name": "partial_correlation_controlling_tau",
                    "value": partial,
                    "unit": "dimensionless",
                    "sample_count": len(tau),
                    "sample_unit": "frame",
                    "status": "valid",
                    "diagnostic": None,
                }
            )
        except U2MetricError as error:
            metric_records.append(
                {
                    "metric_id": "u2_partial_correlation_controlling_tau",
                    "metric_name": "partial_correlation_controlling_tau",
                    "value": None,
                    "unit": "dimensionless",
                    "sample_count": len(tau),
                    "sample_unit": "frame",
                    "status": "invalid",
                    "diagnostic": str(error),
                }
            )
        try:
            calibration = calibration_metrics(
                truth,
                aligned_mean_predictions,
                decoded_sigma,
                levels=levels,
                near_zero_threshold=config["metric_rules"][
                    "near_zero_sigma_threshold_blocks"
                ],
            )
            metric_records.extend(
                [
                    {
                        "metric_id": "u2_expected_calibration_error",
                        "metric_name": "expected_calibration_error",
                        "value": calibration.expected_calibration_error,
                        "unit": "dimensionless",
                        "sample_count": calibration.sample_count,
                        "sample_unit": "frame",
                        "status": "valid",
                        "diagnostic": None,
                    },
                    {
                        "metric_id": "u2_z_mean",
                        "metric_name": "z_mean",
                        "value": calibration.z_diagnostics.mean,
                        "unit": "dimensionless",
                        "sample_count": calibration.sample_count,
                        "sample_unit": "frame",
                        "status": "valid",
                        "diagnostic": None,
                    },
                    {
                        "metric_id": "u2_z_sample_std",
                        "metric_name": "z_sample_std",
                        "value": calibration.z_diagnostics.sample_std,
                        "unit": "dimensionless",
                        "sample_count": calibration.sample_count,
                        "sample_unit": "frame",
                        "status": "valid",
                        "diagnostic": None,
                    },
                    {
                        "metric_id": "u2_z_root_mean_square",
                        "metric_name": "z_root_mean_square",
                        "value": calibration.z_diagnostics.root_mean_square,
                        "unit": "dimensionless",
                        "sample_count": calibration.sample_count,
                        "sample_unit": "frame",
                        "status": "valid",
                        "diagnostic": None,
                    },
                ]
            )
            for level, empirical, gap in zip(
                calibration.nominal_levels,
                calibration.empirical_coverage,
                calibration.coverage_gaps,
            ):
                label = str(level).replace(".", "_")
                metric_records.append(
                    {
                        "metric_id": f"u2_coverage_{label}",
                        "metric_name": f"coverage_at_{level}",
                        "value": empirical,
                        "unit": "proportion",
                        "sample_count": calibration.sample_count,
                        "sample_unit": "frame",
                        "status": "valid",
                        "diagnostic": f"nominal_minus_empirical_gap={-gap}",
                    }
                )
        except U2MetricError as error:
            metric_records.append(
                {
                    "metric_id": "u2_calibration",
                    "metric_name": "calibration",
                    "value": None,
                    "unit": "dimensionless",
                    "sample_count": len(tau),
                    "sample_unit": "frame",
                    "status": "invalid",
                    "diagnostic": str(error),
                }
            )
        result = build_result_artifact(
            metric_records,
            artifact_id=(
                f"{artifact_id_prefix}:u2:layer_{layer_site[0]}:"
                f"{layer_site[1]}"
            ),
            code_sha=mean_matrix.probe_code_sha,
            config_hash=mean_matrix.analysis_config_hash,
            input_manifest_hash=mean_ridge.matrix_artifact["artifact_hash"],
            fold_manifest_hash=mean_matrix.fold_manifest_hash,
            prediction_manifest_hashes=[
                mean_ridge.prediction_artifact["artifact_hash"],
                spread_ridge.prediction_artifact["artifact_hash"],
            ],
            analysis_family="U2",
        )
        payload = dict(result)
        payload.pop("artifact_hash")
        payload.update(
            {
                "mean_matrix_hash": mean_matrix.matrix_hash,
                "spread_matrix_hash": spread_matrix.matrix_hash,
                "mean_matrix_artifact_hash": mean_ridge.matrix_artifact[
                    "artifact_hash"
                ],
                "spread_matrix_artifact_hash": spread_ridge.matrix_artifact[
                    "artifact_hash"
                ],
                "mean_selection_manifest_hash": mean_matrix.selection_manifest_hash,
                "spread_selection_manifest_hash": (
                    spread_matrix.selection_manifest_hash
                ),
                "control_gate_hash": control_gate["artifact_hash"],
                "decoded_sigma_hash": sha256_value(list(decoded_sigma)),
                "oracle_sigma_hash": sha256_value(list(oracle_sigma)),
                "synthetic": mean_matrix.synthetic,
                "scientific_use": mean_matrix.scientific_use,
            }
        )
        result = seal_artifact(payload)
        results.append(result)
        bundle_rows.append(
            {
                "layer_idx": layer_site[0],
                "hook_site": layer_site[1],
                "result_artifact_hash": result["artifact_hash"],
            }
        )
    bundle = seal_artifact(
        {
            "artifact_type": "u2_calibration_bundle",
            "artifact_id": f"{artifact_id_prefix}:u2:bundle",
            "code_sha": mean_run.bundle["code_sha"],
            "config_hash": mean_run.bundle["config_hash"],
            "input_manifest_hash": sha256_value(
                [mean_run.bundle["artifact_hash"], spread_run.bundle["artifact_hash"]]
            ),
            "mean_scope_bundle_hash": mean_run.bundle["artifact_hash"],
            "spread_scope_bundle_hash": spread_run.bundle["artifact_hash"],
            "control_gate_hash": control_gate["artifact_hash"],
            "layer_site_results": bundle_rows,
            "synthetic": mean_run.bundle["synthetic"],
            "scientific_use": mean_run.bundle["scientific_use"],
        }
    )
    return U2PilotRun(tuple(results), bundle)
