"""Minimal common Person D synthetic fit/predict/evaluate harness.

Scientific fold membership is consumed from Person B's sealed fold artifact,
target vocabulary comes from B's frozen config through ``BaselineSpec``, and
evaluation calls B's metric implementation directly.  The harness never
constructs fold membership or exposes target values as estimator features.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping, Protocol, Sequence

from mineocclude.analysis.manifests import sha256_value
from mineocclude.baselines.constant_velocity import predict_constant_velocity
from mineocclude.baselines.firewall import FrameKey, LegalInputRow, select_legal_inputs
from mineocclude.baselines.interface import TrajectoryContext
from mineocclude.baselines.last_seen import predict_last_seen
from mineocclude.baselines.spec import (
    PREDICTION_SCHEMA_VERSION,
    BaselineContractCode,
    BaselineContractError,
    BaselinePrediction,
    BaselineSpec,
    validate_baseline_spec,
    validate_prediction_row,
    validate_required_provenance,
)
from mineocclude.metrics.u1_mean import RegressionMetrics, U1MetricError, regression_metrics
from mineocclude.probes.splits import GroupedSplitError, validate_fold_manifest


TARGET_ROW_FIELDS = frozenset(
    {
        "trajectory_id",
        "model_frame_idx",
        "target_name",
        "target_value",
        "status",
        "target_manifest_hash",
        "accepted_manifest_hash",
    }
)


@dataclass(frozen=True)
class EstimatorPrediction:
    frame_key: FrameKey
    prediction: float


class BaselineEstimator(Protocol):
    """Narrow estimator interface used by the common harness and test spies."""

    def fit(
        self,
        spec: BaselineSpec,
        rows: Sequence[LegalInputRow],
        targets_by_key: Mapping[FrameKey, float],
    ) -> Mapping[str, object]: ...

    def predict(
        self,
        spec: BaselineSpec,
        fit_state: Mapping[str, object],
        rows: Sequence[LegalInputRow],
    ) -> Sequence[EstimatorPrediction]: ...


@dataclass(frozen=True)
class HarnessResult:
    """Validated outputs from one held-out-fold synthetic baseline run."""

    spec: BaselineSpec
    fit_metadata: Mapping[str, object]
    predictions: tuple[BaselinePrediction, ...]
    metrics: RegressionMetrics


class _ExistingAnalyticEstimator:
    """Adapter that runs existing D analytic baselines through one interface."""

    def fit(
        self,
        spec: BaselineSpec,
        rows: Sequence[LegalInputRow],
        targets_by_key: Mapping[FrameKey, float],
    ) -> Mapping[str, object]:
        # Analytic estimators have no learned parameters.  Recording the exact
        # keys proves the common harness called fit only with outer-train rows.
        keys = [list(row.frame_key) for row in rows]
        if set(targets_by_key) != {row.frame_key for row in rows}:
            raise BaselineContractError(
                BaselineContractCode.COVERAGE_MISMATCH,
                "analytic fit targets do not exactly cover training identities",
            )
        return {
            "fit_kind": "analytic_no_parameters",
            "train_identities": keys,
            "train_identity_hash": sha256_value(keys),
        }

    def predict(
        self,
        spec: BaselineSpec,
        fit_state: Mapping[str, object],
        rows: Sequence[LegalInputRow],
    ) -> Sequence[EstimatorPrediction]:
        contexts = [_to_context(row, spec) for row in rows]
        if spec.estimator == "analytic_last_seen":
            baseline_rows = predict_last_seen(contexts)
        elif spec.estimator == "analytic_constant_velocity":
            baseline_rows = predict_constant_velocity(contexts)
        else:  # Registry validation should make this unreachable, so fail closed.
            raise BaselineContractError(
                BaselineContractCode.ESTIMATOR_CONTRACT,
                f"no existing D adapter for estimator {spec.estimator!r}",
            )
        return tuple(
            EstimatorPrediction(
                frame_key=(row.trajectory_id, row.model_frame_idx),
                prediction=float(row.prediction),
            )
            for row in baseline_rows
            if row.target_name == spec.target_name and row.applicable
        )


def _to_context(row: LegalInputRow, spec: BaselineSpec) -> TrajectoryContext:
    features = row.features
    return TrajectoryContext(
        trajectory_id=row.trajectory_id,
        layout_id="__not_exposed_as_feature__",
        model_frame_idx=row.model_frame_idx,
        fold=-1,
        regime="A",
        tau_seconds=float(features["tau"]),
        visibility=features["visibility"] == "visible",
        last_seen_position_blocks=float(features["last_visible_position_blocks"]),
        last_seen_velocity_blocks_per_s=(
            float(features["estimated_velocity_blocks_per_s"])
            if "estimated_velocity_blocks_per_s" in features
            else None
        ),
        v_scripted_blocks_per_s=None,
        q_scripted_blocks2_per_s=None,
        duration_seconds=None,
        config_hash="__provenance_held_by_harness__",
        seed=spec.seed,
    )


def _validate_targets(
    target_rows: Sequence[Mapping[str, Any]],
    *,
    spec: BaselineSpec,
    provenance: Mapping[str, str],
) -> dict[FrameKey, float]:
    if not isinstance(target_rows, (list, tuple)) or not target_rows:
        raise BaselineContractError(
            BaselineContractCode.INVALID_TYPE,
            "target_rows must be a non-empty list or tuple",
        )
    result: dict[FrameKey, float] = {}
    for index, row in enumerate(target_rows):
        if not isinstance(row, Mapping):
            raise BaselineContractError(
                BaselineContractCode.INVALID_TYPE,
                f"target row {index} must be a mapping",
            )
        fields = set(row)
        missing = sorted(str(field) for field in TARGET_ROW_FIELDS - fields)
        unknown = sorted(repr(field) for field in fields - TARGET_ROW_FIELDS)
        if missing:
            raise BaselineContractError(
                BaselineContractCode.MISSING_FIELD,
                f"target row {index} is missing: {', '.join(missing)}",
            )
        if unknown:
            raise BaselineContractError(
                BaselineContractCode.UNKNOWN_FIELD,
                f"target row {index} has unknown fields: {', '.join(unknown)}",
            )
        trajectory_id = row.get("trajectory_id")
        frame_idx = row.get("model_frame_idx")
        if not isinstance(trajectory_id, str) or not trajectory_id.strip():
            raise BaselineContractError(
                BaselineContractCode.INVALID_IDENTITY,
                f"target row {index} has invalid trajectory_id",
            )
        if (
            not isinstance(frame_idx, int)
            or isinstance(frame_idx, bool)
            or frame_idx < 0
        ):
            raise BaselineContractError(
                BaselineContractCode.INVALID_IDENTITY,
                f"target row {index} has invalid model_frame_idx",
            )
        key = (trajectory_id, frame_idx)
        if key in result:
            raise BaselineContractError(
                BaselineContractCode.DUPLICATE_IDENTITY,
                f"duplicate target identity {key!r}",
            )
        if row.get("target_name") != spec.target_name:
            raise BaselineContractError(
                BaselineContractCode.INVALID_SPEC,
                f"target row {index} does not contain {spec.target_name!r}",
            )
        value = row.get("target_value")
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
        ):
            raise BaselineContractError(
                BaselineContractCode.INVALID_SPEC,
                f"target row {index} has a non-finite target",
            )
        if row.get("status") != "accepted":
            raise BaselineContractError(
                BaselineContractCode.INVALID_SPEC,
                f"target row {index} is not accepted",
            )
        if row.get("target_manifest_hash") != provenance["target_manifest_hash"]:
            raise BaselineContractError(
                BaselineContractCode.INVALID_PROVENANCE,
                f"target row {index} has a stale target manifest hash",
            )
        if row.get("accepted_manifest_hash") != provenance["accepted_manifest_hash"]:
            raise BaselineContractError(
                BaselineContractCode.INVALID_PROVENANCE,
                f"target row {index} has a stale accepted manifest hash",
            )
        result[key] = float(value)
    return result


def _fold_memberships(
    fold_manifest: Mapping[str, Any], provenance: Mapping[str, str]
) -> dict[FrameKey, tuple[str, int]]:
    try:
        validate_fold_manifest(fold_manifest)
    except (GroupedSplitError, TypeError, ValueError) as error:
        raise BaselineContractError(
            BaselineContractCode.INVALID_FOLD,
            f"Person B fold manifest is invalid: {error}",
        ) from error
    if fold_manifest.get("artifact_hash") != provenance["fold_manifest_hash"]:
        raise BaselineContractError(
            BaselineContractCode.INVALID_PROVENANCE,
            "fold artifact hash differs from required provenance",
        )
    if fold_manifest.get("input_manifest_hash") != provenance["accepted_manifest_hash"]:
        raise BaselineContractError(
            BaselineContractCode.INVALID_PROVENANCE,
            "fold input manifest differs from accepted-manifest provenance",
        )
    if fold_manifest.get("config_hash") != provenance["analysis_config_hash"]:
        raise BaselineContractError(
            BaselineContractCode.INVALID_PROVENANCE,
            "fold config hash differs from analysis-config provenance",
        )
    result: dict[FrameKey, tuple[str, int]] = {}
    trajectory_layout: dict[str, str] = {}
    for membership in fold_manifest["memberships"]:
        key = (membership["trajectory_id"], membership["model_frame_idx"])
        if key in result:
            raise BaselineContractError(
                BaselineContractCode.DUPLICATE_IDENTITY,
                f"duplicate fold identity {key!r}",
            )
        layout_id = membership["layout_id"]
        previous_layout = trajectory_layout.setdefault(key[0], layout_id)
        if previous_layout != layout_id:
            raise BaselineContractError(
                BaselineContractCode.INVALID_FOLD,
                f"trajectory {key[0]!r} crosses layouts",
            )
        result[key] = (layout_id, membership["fold_idx"])
    return result


def _requested_key_set(requested_test_keys: Sequence[FrameKey]) -> set[FrameKey]:
    if not isinstance(requested_test_keys, (list, tuple)) or not requested_test_keys:
        raise BaselineContractError(
            BaselineContractCode.INVALID_TYPE,
            "requested_test_keys must be a non-empty list or tuple",
        )
    result: set[FrameKey] = set()
    for key in requested_test_keys:
        if (
            not isinstance(key, tuple)
            or len(key) != 2
            or not isinstance(key[0], str)
            or not key[0]
            or not isinstance(key[1], int)
            or isinstance(key[1], bool)
            or key[1] < 0
        ):
            raise BaselineContractError(
                BaselineContractCode.INVALID_IDENTITY,
                f"invalid requested frame identity {key!r}",
            )
        if key in result:
            raise BaselineContractError(
                BaselineContractCode.DUPLICATE_IDENTITY,
                f"duplicate requested identity {key!r}",
            )
        result.add(key)
    return result


def run_synthetic_baseline_harness(
    spec_document: Mapping[str, Any],
    *,
    input_rows: Sequence[Mapping[str, Any]],
    target_rows: Sequence[Mapping[str, Any]],
    fold_manifest: Mapping[str, Any],
    requested_test_keys: Sequence[FrameKey],
    provenance: Mapping[str, Any],
    estimator: BaselineEstimator | None = None,
) -> HarnessResult:
    """Run one exact held-out fold through D's common synthetic foundation."""

    spec = validate_baseline_spec(spec_document)
    validated_provenance = validate_required_provenance(spec, provenance)

    # The firewall deliberately runs before any estimator method.  Tests use a
    # spy estimator to enforce that this ordering remains true.
    legal_rows = select_legal_inputs(
        spec, input_rows, provenance=validated_provenance
    )
    targets_by_key = _validate_targets(
        target_rows, spec=spec, provenance=validated_provenance
    )
    folds_by_key = _fold_memberships(fold_manifest, validated_provenance)

    legal_by_key = {row.frame_key: row for row in legal_rows}
    all_keys = set(legal_by_key)
    if all_keys != set(targets_by_key) or all_keys != set(folds_by_key):
        raise BaselineContractError(
            BaselineContractCode.COVERAGE_MISMATCH,
            "input, target, and authoritative fold identities must match exactly",
        )
    requested = _requested_key_set(requested_test_keys)
    if not requested <= all_keys:
        raise BaselineContractError(
            BaselineContractCode.COVERAGE_MISMATCH,
            "requested test identities are absent from validated inputs",
        )
    requested_folds = {folds_by_key[key][1] for key in requested}
    if len(requested_folds) != 1:
        raise BaselineContractError(
            BaselineContractCode.INVALID_FOLD,
            "one harness run must request exactly one outer fold",
        )
    held_out_fold = next(iter(requested_folds))
    authoritative_test = {
        key for key, (_, fold_idx) in folds_by_key.items() if fold_idx == held_out_fold
    }
    if requested != authoritative_test:
        raise BaselineContractError(
            BaselineContractCode.COVERAGE_MISMATCH,
            "requested test identities must exactly cover the held-out fold",
        )
    train_keys = all_keys - requested
    if train_keys & requested:
        raise BaselineContractError(
            BaselineContractCode.TRAIN_TEST_OVERLAP,
            "training and requested test identities overlap",
        )

    train_rows = tuple(legal_by_key[key] for key in sorted(train_keys))
    test_rows = tuple(legal_by_key[key] for key in sorted(requested))
    train_targets = {key: targets_by_key[key] for key in sorted(train_keys)}
    selected_estimator: BaselineEstimator = estimator or _ExistingAnalyticEstimator()
    try:
        fit_state = selected_estimator.fit(spec, train_rows, train_targets)
    except BaselineContractError:
        raise
    except Exception as error:
        raise BaselineContractError(
            BaselineContractCode.ESTIMATOR_CONTRACT,
            f"estimator fit failed: {error}",
        ) from error
    if not isinstance(fit_state, Mapping):
        raise BaselineContractError(
            BaselineContractCode.ESTIMATOR_CONTRACT,
            "estimator fit must return a metadata mapping",
        )

    try:
        estimator_predictions = selected_estimator.predict(spec, fit_state, test_rows)
    except BaselineContractError:
        raise
    except Exception as error:
        raise BaselineContractError(
            BaselineContractCode.ESTIMATOR_CONTRACT,
            f"estimator predict failed: {error}",
        ) from error
    if not isinstance(estimator_predictions, (list, tuple)):
        raise BaselineContractError(
            BaselineContractCode.ESTIMATOR_CONTRACT,
            "estimator predict must return a list or tuple",
        )
    prediction_by_key: dict[FrameKey, float] = {}
    for item in estimator_predictions:
        if not isinstance(item, EstimatorPrediction):
            raise BaselineContractError(
                BaselineContractCode.ESTIMATOR_CONTRACT,
                "estimator prediction has the wrong type",
            )
        if (
            not isinstance(item.frame_key, tuple)
            or len(item.frame_key) != 2
            or not isinstance(item.frame_key[0], str)
            or not item.frame_key[0]
            or not isinstance(item.frame_key[1], int)
            or isinstance(item.frame_key[1], bool)
            or item.frame_key[1] < 0
        ):
            raise BaselineContractError(
                BaselineContractCode.PREDICTION_IDENTITY,
                f"invalid estimator prediction identity {item.frame_key!r}",
            )
        if item.frame_key in prediction_by_key:
            raise BaselineContractError(
                BaselineContractCode.PREDICTION_IDENTITY,
                f"duplicate estimator prediction {item.frame_key!r}",
            )
        prediction_by_key[item.frame_key] = item.prediction
    if set(prediction_by_key) != requested:
        raise BaselineContractError(
            BaselineContractCode.PREDICTION_IDENTITY,
            "estimator predictions do not exactly match requested test identities",
        )

    train_identities = [list(key) for key in sorted(train_keys)]
    test_identities = [list(key) for key in sorted(requested)]
    fit_payload = {
        "baseline_name": spec.baseline_name,
        "baseline_version": spec.baseline_version,
        "estimator": spec.estimator,
        "hyperparameter_source": spec.hyperparameter_source,
        "seed": spec.seed,
        "fit_scope": spec.fit_scope,
        "held_out_fold": held_out_fold,
        "preprocessing_scope": "outer_train_rows_only",
        "train_identities": train_identities,
        "train_identity_hash": sha256_value(train_identities),
        "test_identities": test_identities,
        "test_identity_hash": sha256_value(test_identities),
        "fold_manifest_hash": validated_provenance["fold_manifest_hash"],
        "target_manifest_hash": validated_provenance["target_manifest_hash"],
        "accepted_manifest_hash": validated_provenance["accepted_manifest_hash"],
        "analysis_config_hash": validated_provenance["analysis_config_hash"],
        "preprocess_hash": validated_provenance["preprocess_hash"],
        "code_sha": validated_provenance["code_sha"],
        "estimator_fit_metadata": dict(fit_state),
    }
    fit_id = f"person-d:{spec.baseline_name}:{sha256_value(fit_payload)[:16]}"
    fit_metadata = {"fit_id": fit_id, **fit_payload}

    predictions: list[BaselinePrediction] = []
    for key in sorted(requested):
        row = {
            "prediction_schema_version": PREDICTION_SCHEMA_VERSION,
            "baseline_name": spec.baseline_name,
            "baseline_version": spec.baseline_version,
            "target_name": spec.target_name,
            "trajectory_id": key[0],
            "model_frame_idx": key[1],
            "fold_idx": held_out_fold,
            "prediction": prediction_by_key[key],
            "prediction_scope": "out_of_fold",
            "fit_id": fit_id,
            "provenance": validated_provenance,
        }
        predictions.append(validate_prediction_row(row, spec))

    try:
        metrics = regression_metrics(
            [targets_by_key[key] for key in sorted(requested)],
            [prediction_by_key[key] for key in sorted(requested)],
        )
    except U1MetricError as error:
        raise BaselineContractError(
            BaselineContractCode.METRIC_FAILURE,
            f"Person B regression metric rejected the result: {error}",
        ) from error
    return HarnessResult(
        spec=spec,
        fit_metadata=fit_metadata,
        predictions=tuple(predictions),
        metrics=metrics,
    )
