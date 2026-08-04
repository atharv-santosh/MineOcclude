"""Locked prediction/result manifests and append-only correction records."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

from .manifests import (
    AnalysisArtifactError,
    is_hex_digest,
    seal_artifact,
    validate_sealed_artifact,
)


CORRECTION_LOG_SCHEMA_VERSION = "person-b-correction-log-v0.1"


def _finite(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def build_prediction_artifact(
    rows: Sequence[Mapping[str, Any]],
    *,
    artifact_id: str,
    code_sha: str,
    config_hash: str,
    input_manifest_hash: str,
    fold_manifest_hash: str,
    model_family: str,
    target_name: str,
    layer_idx: int,
    hook_site: str,
) -> dict[str, Any]:
    """Seal exact OOF prediction rows and reject incomplete coverage metadata."""

    if not rows:
        raise AnalysisArtifactError("Prediction artifacts require rows.")
    if not is_hex_digest(fold_manifest_hash, 64):
        raise AnalysisArtifactError("fold_manifest_hash must be SHA-256.")
    for name, value in (
        ("model_family", model_family),
        ("target_name", target_name),
        ("hook_site", hook_site),
    ):
        if not isinstance(value, str) or not value.strip():
            raise AnalysisArtifactError(f"{name} must be non-empty.")
    if not isinstance(layer_idx, int) or isinstance(layer_idx, bool) or layer_idx < 0:
        raise AnalysisArtifactError("layer_idx must be a non-negative integer.")
    normalized: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise AnalysisArtifactError(
                f"Prediction row {index} must be a mapping."
            )
        required = (
            "trajectory_id",
            "model_frame_idx",
            "layout_id",
            "fold_idx",
            "prediction",
            "fit_id",
            "prediction_scope",
        )
        missing = [field for field in required if field not in row]
        if missing:
            raise AnalysisArtifactError(
                f"Prediction row {index} is missing: {', '.join(missing)}."
            )
        if (
            not isinstance(row["trajectory_id"], str)
            or not row["trajectory_id"]
            or not isinstance(row["model_frame_idx"], int)
            or isinstance(row["model_frame_idx"], bool)
            or row["model_frame_idx"] < 0
            or not isinstance(row["layout_id"], str)
            or not row["layout_id"]
            or not isinstance(row["fold_idx"], int)
            or isinstance(row["fold_idx"], bool)
            or row["fold_idx"] < 0
            or not isinstance(row["fit_id"], str)
            or not row["fit_id"]
        ):
            raise AnalysisArtifactError(
                f"Prediction row {index} has invalid identity metadata."
            )
        key = (row["trajectory_id"], row["model_frame_idx"])
        if key in seen:
            raise AnalysisArtifactError(f"Duplicate prediction identity: {key}.")
        seen.add(key)
        prediction_scope = row["prediction_scope"]
        if not isinstance(prediction_scope, str) or prediction_scope not in {
            "out_of_fold",
            "held_out",
        }:
            raise AnalysisArtifactError(
                "Claim-bearing predictions must be out-of-fold or held out."
            )
        if not _finite(row["prediction"]):
            raise AnalysisArtifactError("Predictions must be finite; no rows are dropped.")
        normalized.append(dict(row))
    return seal_artifact(
        {
            "artifact_type": "prediction_manifest",
            "artifact_id": artifact_id,
            "code_sha": code_sha,
            "config_hash": config_hash,
            "input_manifest_hash": input_manifest_hash,
            "fold_manifest_hash": fold_manifest_hash,
            "model_family": model_family,
            "target_name": target_name,
            "layer_idx": layer_idx,
            "hook_site": hook_site,
            "rows": sorted(
                normalized,
                key=lambda row: (row["trajectory_id"], row["model_frame_idx"]),
            ),
        }
    )


def build_result_artifact(
    metric_records: Sequence[Mapping[str, Any]],
    *,
    artifact_id: str,
    code_sha: str,
    config_hash: str,
    input_manifest_hash: str,
    fold_manifest_hash: str,
    prediction_manifest_hashes: Sequence[str],
    analysis_family: str,
) -> dict[str, Any]:
    """Seal U1-U4 or diagnostic records with explicit validity status."""

    if not isinstance(analysis_family, str) or analysis_family not in {
        "U1",
        "U2",
        "U3",
        "U4",
        "diagnostic",
    }:
        raise AnalysisArtifactError("Unknown analysis_family.")
    if not is_hex_digest(fold_manifest_hash, 64):
        raise AnalysisArtifactError("fold_manifest_hash must be SHA-256.")
    if not metric_records:
        raise AnalysisArtifactError("Result artifacts require metric records.")
    if not prediction_manifest_hashes or any(
        not is_hex_digest(value, 64) for value in prediction_manifest_hashes
    ):
        raise AnalysisArtifactError(
            "Result artifacts require valid prediction-manifest hashes."
        )
    if len(set(prediction_manifest_hashes)) != len(prediction_manifest_hashes):
        raise AnalysisArtifactError(
            "prediction_manifest_hashes cannot contain duplicates."
        )
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, record in enumerate(metric_records):
        if not isinstance(record, Mapping):
            raise AnalysisArtifactError(
                f"Metric record {index} must be a mapping."
            )
        required = (
            "metric_id",
            "metric_name",
            "value",
            "unit",
            "sample_count",
            "sample_unit",
            "status",
            "diagnostic",
        )
        missing = [field for field in required if field not in record]
        if missing:
            raise AnalysisArtifactError(
                f"Metric record {index} is missing: {', '.join(missing)}."
            )
        metric_id = record["metric_id"]
        if not isinstance(metric_id, str) or not metric_id or metric_id in seen:
            raise AnalysisArtifactError("metric_id must be unique and non-empty.")
        seen.add(metric_id)
        for field in ("metric_name", "unit", "sample_unit"):
            if not isinstance(record[field], str) or not record[field].strip():
                raise AnalysisArtifactError(f"{field} must be non-empty.")
        status = record["status"]
        if not isinstance(status, str) or status not in {"valid", "invalid"}:
            raise AnalysisArtifactError("Metric status must be valid or invalid.")
        value = record["value"]
        diagnostic = record["diagnostic"]
        if status == "valid" and not _finite(value):
            raise AnalysisArtifactError("Valid metrics require finite values.")
        if status == "invalid" and (
            value is not None
            or not isinstance(diagnostic, str)
            or not diagnostic.strip()
        ):
            raise AnalysisArtifactError(
                "Invalid metrics require value=null and a diagnostic reason."
            )
        count = record["sample_count"]
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            raise AnalysisArtifactError("sample_count must be non-negative integer data.")
        normalized.append(dict(record))
    return seal_artifact(
        {
            "artifact_type": "result_manifest",
            "artifact_id": artifact_id,
            "code_sha": code_sha,
            "config_hash": config_hash,
            "input_manifest_hash": input_manifest_hash,
            "fold_manifest_hash": fold_manifest_hash,
            "prediction_manifest_hashes": list(prediction_manifest_hashes),
            "analysis_family": analysis_family,
            "metric_records": sorted(normalized, key=lambda row: row["metric_id"]),
        }
    )


def create_correction_log(
    *,
    artifact_id: str,
    code_sha: str,
    config_hash: str,
    input_manifest_hash: str,
) -> dict[str, Any]:
    return seal_artifact(
        {
            "artifact_type": "correction_log",
            "artifact_id": artifact_id,
            "code_sha": code_sha,
            "config_hash": config_hash,
            "input_manifest_hash": input_manifest_hash,
            "correction_log_schema_version": CORRECTION_LOG_SCHEMA_VERSION,
            "previous_log_hash": None,
            "corrections": [],
        }
    )


def append_correction(
    log: Mapping[str, Any], correction: Mapping[str, Any]
) -> dict[str, Any]:
    """Append one correction while retaining a hash chain to the prior log."""

    validate_sealed_artifact(log, expected_type="correction_log")
    if log.get("correction_log_schema_version") != CORRECTION_LOG_SCHEMA_VERSION:
        raise AnalysisArtifactError("Correction log schema version mismatch.")
    required = (
        "correction_id",
        "affected_artifact_hash",
        "reason",
        "resolution",
        "requires_new_run",
        "approved_by_roles",
    )
    missing = [field for field in required if field not in correction]
    if missing:
        raise AnalysisArtifactError(
            "Correction is missing: " + ", ".join(missing)
        )
    if not is_hex_digest(correction["affected_artifact_hash"], 64):
        raise AnalysisArtifactError("affected_artifact_hash must be SHA-256.")
    if not isinstance(correction["requires_new_run"], bool):
        raise AnalysisArtifactError("requires_new_run must be boolean.")
    if (
        not isinstance(correction["approved_by_roles"], list)
        or not correction["approved_by_roles"]
        or any(
            not isinstance(value, str) or not value
            for value in correction["approved_by_roles"]
        )
    ):
        raise AnalysisArtifactError("approved_by_roles must be a non-empty list.")
    for field in ("correction_id", "reason", "resolution"):
        if not isinstance(correction[field], str) or not correction[field].strip():
            raise AnalysisArtifactError(f"{field} must be non-empty.")
    current_corrections = log.get("corrections")
    if not isinstance(current_corrections, list) or any(
        not isinstance(item, Mapping) for item in current_corrections
    ):
        raise AnalysisArtifactError("Correction log entries must be mappings.")
    prior_pointer = log.get("previous_log_hash")
    if prior_pointer is not None and not is_hex_digest(prior_pointer, 64):
        raise AnalysisArtifactError("previous_log_hash must be null or SHA-256.")
    existing = list(current_corrections)
    if correction["correction_id"] in {
        item.get("correction_id") for item in existing if isinstance(item, Mapping)
    }:
        raise AnalysisArtifactError("correction_id must be unique.")
    payload = dict(log)
    previous_hash = payload.pop("artifact_hash")
    payload["previous_log_hash"] = previous_hash
    payload["corrections"] = [*existing, dict(correction)]
    return seal_artifact(payload)
