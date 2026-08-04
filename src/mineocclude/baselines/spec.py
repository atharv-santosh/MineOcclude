"""Strict Person D Phase 1 baseline and prediction contracts.

This module is the single D-owned authority for the small synthetic
fit/predict/evaluate foundation.  Target names are checked against Person B's
frozen analysis configuration; their scientific meanings and units remain
Person B-owned.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from mineocclude.analysis.config import load_core_analysis_config
from mineocclude.analysis.manifests import is_hex_digest
from mineocclude.contracts.identity import CODE_SHA_LENGTH, FRAME_KEY, SCHEMA_VERSION


BASELINE_SPEC_SCHEMA_VERSION = "person-d-baseline-spec-v1.0"
PREDICTION_SCHEMA_VERSION = "person-d-baseline-prediction-v1.0"
FIT_SCOPE = "outer_train_only"
DEFAULT_PHASE1_SEED = 20260719

REQUIRED_PROVENANCE: tuple[str, ...] = (
    "schema_version",
    "accepted_manifest_hash",
    "fold_manifest_hash",
    "target_manifest_hash",
    "analysis_config_hash",
    "preprocess_hash",
    "code_sha",
)


class BaselineContractCode(str, Enum):
    """Stable machine-readable rejection codes for D's Phase 1 boundary."""

    INVALID_TYPE = "invalid_type"
    MISSING_FIELD = "missing_field"
    UNKNOWN_FIELD = "unknown_field"
    UNSUPPORTED_BASELINE = "unsupported_baseline"
    INVALID_SPEC = "invalid_spec"
    INVALID_PROVENANCE = "invalid_provenance"
    INVALID_IDENTITY = "invalid_identity"
    DUPLICATE_IDENTITY = "duplicate_identity"
    ILLEGAL_FEATURE = "illegal_feature"
    INVALID_FOLD = "invalid_fold"
    COVERAGE_MISMATCH = "coverage_mismatch"
    TRAIN_TEST_OVERLAP = "train_test_overlap"
    ESTIMATOR_CONTRACT = "estimator_contract"
    PREDICTION_IDENTITY = "prediction_identity"
    METRIC_FAILURE = "metric_failure"


class BaselineContractError(ValueError):
    """Fail-closed D Phase 1 validation error carrying a stable code."""

    def __init__(self, code: BaselineContractCode, message: str) -> None:
        self.code = code
        super().__init__(f"{code.value}: {message}")


@dataclass(frozen=True)
class BaselineSpec:
    """Validated, immutable definition of one supported D baseline."""

    baseline_spec_schema_version: str
    baseline_name: str
    baseline_version: str
    target_name: str
    legal_features: tuple[str, ...]
    fit_scope: str
    estimator: str
    hyperparameter_source: str
    seed: int
    applicable_outputs: tuple[str, ...]
    required_provenance: tuple[str, ...]

    def as_document(self) -> dict[str, object]:
        return {
            "baseline_spec_schema_version": self.baseline_spec_schema_version,
            "baseline_name": self.baseline_name,
            "baseline_version": self.baseline_version,
            "target_name": self.target_name,
            "legal_features": list(self.legal_features),
            "fit_scope": self.fit_scope,
            "estimator": self.estimator,
            "hyperparameter_source": self.hyperparameter_source,
            "seed": self.seed,
            "applicable_outputs": list(self.applicable_outputs),
            "required_provenance": list(self.required_provenance),
        }


_SUPPORTED_SPECS: dict[tuple[str, str], BaselineSpec] = {
    ("last_seen", "1.0"): BaselineSpec(
        baseline_spec_schema_version=BASELINE_SPEC_SCHEMA_VERSION,
        baseline_name="last_seen",
        baseline_version="1.0",
        target_name="mu_oracle_blocks",
        legal_features=("last_visible_position_blocks", "tau", "visibility"),
        fit_scope=FIT_SCOPE,
        estimator="analytic_last_seen",
        hyperparameter_source="none",
        seed=DEFAULT_PHASE1_SEED,
        applicable_outputs=("prediction",),
        required_provenance=REQUIRED_PROVENANCE,
    ),
    ("constant_velocity", "1.0"): BaselineSpec(
        baseline_spec_schema_version=BASELINE_SPEC_SCHEMA_VERSION,
        baseline_name="constant_velocity",
        baseline_version="1.0",
        target_name="mu_oracle_blocks",
        legal_features=(
            "estimated_velocity_blocks_per_s",
            "last_visible_position_blocks",
            "tau",
            "visibility",
        ),
        fit_scope=FIT_SCOPE,
        estimator="analytic_constant_velocity",
        hyperparameter_source="none",
        seed=DEFAULT_PHASE1_SEED,
        applicable_outputs=("prediction",),
        required_provenance=REQUIRED_PROVENANCE,
    ),
}

_SPEC_FIELDS = frozenset(next(iter(_SUPPORTED_SPECS.values())).as_document())


def supported_baseline_spec(
    baseline_name: str, baseline_version: str = "1.0"
) -> dict[str, object]:
    """Return a new JSON-shaped document for a supported baseline identity."""

    spec = _SUPPORTED_SPECS.get((baseline_name, baseline_version))
    if spec is None:
        raise BaselineContractError(
            BaselineContractCode.UNSUPPORTED_BASELINE,
            f"unsupported baseline identity {(baseline_name, baseline_version)!r}",
        )
    return spec.as_document()


def validate_baseline_spec(document: Mapping[str, Any]) -> BaselineSpec:
    """Validate a submitted spec exactly; no caller-defined extensions pass."""

    if not isinstance(document, Mapping):
        raise BaselineContractError(
            BaselineContractCode.INVALID_TYPE, "BaselineSpec must be a mapping"
        )
    fields = set(document)
    missing = sorted(str(field) for field in _SPEC_FIELDS - fields)
    if missing:
        raise BaselineContractError(
            BaselineContractCode.MISSING_FIELD,
            "BaselineSpec is missing: " + ", ".join(missing),
        )
    unknown = sorted(repr(field) for field in fields - _SPEC_FIELDS)
    if unknown:
        raise BaselineContractError(
            BaselineContractCode.UNKNOWN_FIELD,
            "BaselineSpec contains unknown fields: " + ", ".join(unknown),
        )

    name = document.get("baseline_name")
    version = document.get("baseline_version")
    if not isinstance(name, str) or not isinstance(version, str):
        raise BaselineContractError(
            BaselineContractCode.UNSUPPORTED_BASELINE,
            "baseline_name and baseline_version must be strings",
        )
    expected = _SUPPORTED_SPECS.get((name, version))
    if expected is None:
        raise BaselineContractError(
            BaselineContractCode.UNSUPPORTED_BASELINE,
            f"unsupported baseline identity {(name, version)!r}",
        )

    expected_document = expected.as_document()
    for field, expected_value in expected_document.items():
        if document.get(field) != expected_value:
            raise BaselineContractError(
                BaselineContractCode.INVALID_SPEC,
                f"{field} does not match the registered {name} {version} contract",
            )

    # This is deliberately a reference check into B's current authority, not a
    # second D definition of target units or meaning.
    targets = load_core_analysis_config()["targets"]
    if expected.target_name not in targets:
        raise BaselineContractError(
            BaselineContractCode.INVALID_SPEC,
            "registered target is absent from Person B's frozen analysis config",
        )
    return expected


def validate_required_provenance(
    spec: BaselineSpec, provenance: Mapping[str, Any]
) -> dict[str, str]:
    """Validate exact A/B provenance required by a registered BaselineSpec."""

    if not isinstance(provenance, Mapping):
        raise BaselineContractError(
            BaselineContractCode.INVALID_PROVENANCE,
            "provenance must be a mapping",
        )
    required = set(spec.required_provenance)
    fields = set(provenance)
    if fields != required:
        missing = sorted(str(field) for field in required - fields)
        unknown = sorted(repr(field) for field in fields - required)
        raise BaselineContractError(
            BaselineContractCode.INVALID_PROVENANCE,
            f"provenance fields differ; missing={missing}, unknown={unknown}",
        )
    if provenance.get("schema_version") != SCHEMA_VERSION:
        raise BaselineContractError(
            BaselineContractCode.INVALID_PROVENANCE,
            f"schema_version must remain {SCHEMA_VERSION!r}",
        )
    for field in (
        "accepted_manifest_hash",
        "fold_manifest_hash",
        "target_manifest_hash",
        "analysis_config_hash",
        "preprocess_hash",
    ):
        if not is_hex_digest(provenance.get(field), 64):
            raise BaselineContractError(
                BaselineContractCode.INVALID_PROVENANCE,
                f"{field} must be a SHA-256 digest",
            )
    if not is_hex_digest(provenance.get("code_sha"), CODE_SHA_LENGTH):
        raise BaselineContractError(
            BaselineContractCode.INVALID_PROVENANCE,
            "code_sha must be a 40-character hexadecimal code-provenance digest",
        )
    return {field: str(provenance[field]) for field in spec.required_provenance}


@dataclass(frozen=True)
class BaselinePrediction:
    """One strict D prediction row with complete frame identity/provenance."""

    prediction_schema_version: str
    baseline_name: str
    baseline_version: str
    target_name: str
    trajectory_id: str
    model_frame_idx: int
    fold_idx: int
    prediction: float
    prediction_scope: str
    fit_id: str
    provenance: Mapping[str, str]

    @property
    def frame_key(self) -> tuple[str, int]:
        return (self.trajectory_id, self.model_frame_idx)

    def as_document(self) -> dict[str, object]:
        return {
            "prediction_schema_version": self.prediction_schema_version,
            "baseline_name": self.baseline_name,
            "baseline_version": self.baseline_version,
            "target_name": self.target_name,
            "trajectory_id": self.trajectory_id,
            "model_frame_idx": self.model_frame_idx,
            "fold_idx": self.fold_idx,
            "prediction": self.prediction,
            "prediction_scope": self.prediction_scope,
            "fit_id": self.fit_id,
            "provenance": dict(self.provenance),
        }


_PREDICTION_FIELDS = frozenset(BaselinePrediction.__dataclass_fields__)


def validate_prediction_row(
    document: Mapping[str, Any], spec: BaselineSpec
) -> BaselinePrediction:
    """Validate one prediction document without inferring or repairing fields."""

    if not isinstance(document, Mapping):
        raise BaselineContractError(
            BaselineContractCode.INVALID_TYPE, "prediction row must be a mapping"
        )
    fields = set(document)
    missing = sorted(str(field) for field in _PREDICTION_FIELDS - fields)
    unknown = sorted(repr(field) for field in fields - _PREDICTION_FIELDS)
    if missing:
        raise BaselineContractError(
            BaselineContractCode.MISSING_FIELD,
            "prediction row is missing: " + ", ".join(missing),
        )
    if unknown:
        raise BaselineContractError(
            BaselineContractCode.UNKNOWN_FIELD,
            "prediction row has unknown fields: " + ", ".join(unknown),
        )
    if (
        document.get("prediction_schema_version") != PREDICTION_SCHEMA_VERSION
        or document.get("baseline_name") != spec.baseline_name
        or document.get("baseline_version") != spec.baseline_version
        or document.get("target_name") != spec.target_name
        or document.get("prediction_scope") != "out_of_fold"
    ):
        raise BaselineContractError(
            BaselineContractCode.INVALID_SPEC,
            "prediction identity or scope disagrees with BaselineSpec",
        )
    trajectory_id = document.get(FRAME_KEY[0])
    frame_idx = document.get(FRAME_KEY[1])
    fold_idx = document.get("fold_idx")
    prediction = document.get("prediction")
    fit_id = document.get("fit_id")
    if not isinstance(trajectory_id, str) or not trajectory_id.strip():
        raise BaselineContractError(
            BaselineContractCode.INVALID_IDENTITY, "trajectory_id must be non-empty"
        )
    if not isinstance(frame_idx, int) or isinstance(frame_idx, bool) or frame_idx < 0:
        raise BaselineContractError(
            BaselineContractCode.INVALID_IDENTITY,
            "model_frame_idx must be a non-negative integer",
        )
    if not isinstance(fold_idx, int) or isinstance(fold_idx, bool) or fold_idx < 0:
        raise BaselineContractError(
            BaselineContractCode.INVALID_FOLD, "fold_idx must be non-negative"
        )
    if (
        isinstance(prediction, bool)
        or not isinstance(prediction, (int, float))
        or not math.isfinite(float(prediction))
    ):
        raise BaselineContractError(
            BaselineContractCode.INVALID_SPEC, "prediction must be finite"
        )
    if not isinstance(fit_id, str) or not fit_id.strip():
        raise BaselineContractError(
            BaselineContractCode.INVALID_SPEC, "fit_id must be non-empty"
        )
    provenance = validate_required_provenance(spec, document.get("provenance"))
    return BaselinePrediction(
        prediction_schema_version=PREDICTION_SCHEMA_VERSION,
        baseline_name=spec.baseline_name,
        baseline_version=spec.baseline_version,
        target_name=spec.target_name,
        trajectory_id=trajectory_id,
        model_frame_idx=frame_idx,
        fold_idx=fold_idx,
        prediction=float(prediction),
        prediction_scope="out_of_fold",
        fit_id=fit_id,
        provenance=provenance,
    )
