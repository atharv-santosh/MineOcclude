"""Person B producer for the frozen B-to-A intervention request contract."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import math
from typing import Any

from mineocclude.analysis.manifests import (
    AnalysisArtifactError,
    is_hex_digest,
    require_disjoint_event_sets,
    sha256_value,
)
from mineocclude.contracts.identity import SCHEMA_VERSION
from mineocclude.contracts.intervention_request import (
    EXPECTED_DIRECTION_DIMENSION,
    validate_intervention_request,
)

from .directions import DirectionError, OrthogonalDirection
from .doses import Dose


def build_intervention_request(
    *,
    request_id: str,
    direction_version: str,
    source_run_id: str,
    direction: OrthogonalDirection,
    layer_idx: int,
    hook_site: str,
    timestep_idx: int,
    doses: Sequence[Dose],
    typical_activation_norm: float,
    scaler_id: str,
    scaler_hash: str,
    activation_norm_artifact_hash: str,
    fit_manifest: Mapping[str, Any],
    validation_manifest: Mapping[str, Any],
    heldout_events: Sequence[Mapping[str, str]],
    raw_space_equivalence_max_error: float,
    max_relative_activation_norm: float = 0.25,
) -> dict[str, Any]:
    """Build and self-validate a request; never repair a rejected document."""

    values = list(direction.unit_residual_direction)
    if len(values) != EXPECTED_DIRECTION_DIMENSION:
        raise DirectionError(
            f"B-to-A directions require {EXPECTED_DIRECTION_DIMENSION} values."
        )
    if not doses:
        raise DirectionError("At least one intervention dose is required.")
    try:
        require_disjoint_event_sets(
            fit_manifest, validation_manifest, tuple(heldout_events)
        )
    except AnalysisArtifactError as error:
        raise DirectionError(f"Intervention event manifests are invalid: {error}") from error
    if not is_hex_digest(activation_norm_artifact_hash, 64):
        raise DirectionError("activation_norm_artifact_hash must be SHA-256.")
    if (
        isinstance(raw_space_equivalence_max_error, bool)
        or not isinstance(raw_space_equivalence_max_error, (int, float))
        or not math.isfinite(float(raw_space_equivalence_max_error))
        or not 0.0 <= float(raw_space_equivalence_max_error) <= 1e-10
    ):
        raise DirectionError(
            "Raw-space equivalence must be numerically verified within 1e-10."
        )
    if abs(direction.post_projection_angle_degrees - 90.0) > 1e-8:
        raise DirectionError(
            "Elapsed-time projection audit is not orthogonal within tolerance."
        )
    alpha_table = [
        {
            "dose_id": dose.dose_id,
            "alpha_requested": dose.alpha_requested,
            "alpha_applied": dose.alpha_applied,
            "intended_block_shift": dose.intended_block_shift,
            "cap_reduced": dose.cap_reduced,
        }
        for dose in doses
    ]
    request = {
        "schema_version": SCHEMA_VERSION,
        "request_id": request_id,
        "direction": {
            "space": "raw_activation",
            "values": values,
            "dimension": len(values),
        },
        "intervention_location": {
            "layer_idx": layer_idx,
            "hook_site": hook_site,
            "timestep_idx": timestep_idx,
        },
        "alpha_table": alpha_table,
        "cap": {
            "max_relative_activation_norm": max_relative_activation_norm,
            "typical_activation_norm": typical_activation_norm,
            "activation_norm_artifact_hash": activation_norm_artifact_hash,
        },
        "direction_metadata": {
            "direction_version": direction_version,
            "direction_hash": sha256_value(values),
            "source_run_id": source_run_id,
            "residual_norm_before_normalization": (
                direction.residual_norm_before_normalization
            ),
            "near_zero_threshold": direction.near_zero_threshold,
            "raw_space_equivalence_max_error": float(
                raw_space_equivalence_max_error
            ),
        },
        "scaler_metadata": {
            "used_during_fit": True,
            "scaler_id": scaler_id,
            "scaler_hash": scaler_hash,
            "inverse_transformed_before_export": True,
        },
        "selection_policy": {
            "used_test_data_to_select_direction": False,
            "used_heldout_outcomes_to_select_direction": False,
            "description": (
                "Layer, timestep, and direction selected from fit/validation "
                "evidence only; held-out outcomes were unavailable to selection."
            ),
        },
        "fit_manifest": dict(fit_manifest),
        "validation_manifest": dict(validation_manifest),
        "heldout_events": [dict(event) for event in heldout_events],
        "validation_flags": {
            "time_orthogonalization_checked": True,
            "raw_space_equivalence_verified": True,
            "near_zero_residual_detected": False,
            "contains_cap_reduced_doses": any(
                dose.cap_reduced for dose in doses
            ),
        },
    }
    result = validate_intervention_request(request)
    if not result.accepted:
        details = "; ".join(
            f"{rejection.code.value}: {rejection.message}"
            for rejection in result.rejections
        )
        raise DirectionError(f"Produced intervention request is invalid: {details}")
    return request
