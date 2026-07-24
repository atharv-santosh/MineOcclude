"""Manifest-bound row selection for Person B probe scopes.

Selection is a scientific input, not a convenience filter.  This module
persists the exact frame keys used for the visible positive control and the
hidden mean/spread analyses so a caller cannot silently select rows after
seeing probe performance.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

from mineocclude.analysis.config import hash_core_analysis_config
from mineocclude.analysis.manifests import (
    AnalysisArtifactError,
    is_hex_digest,
    seal_artifact,
    validate_sealed_artifact,
)
from mineocclude.probes.bridge import validate_joined_frame_table


SELECTION_SCHEMA_VERSION = "person-b-analysis-selection-v0.1"
SELECTION_SOURCE_SCHEMA_VERSION = "person-b-condition-selection-source-v0.1"
SCOPE_VISIBLE_NO_WALL = "visible_no_wall_control"
SCOPE_HIDDEN_MEAN = "hidden_mean"
SCOPE_HIDDEN_SPREAD = "hidden_spread"
ALLOWED_SCOPES = frozenset(
    {
        SCOPE_VISIBLE_NO_WALL,
        SCOPE_HIDDEN_MEAN,
        SCOPE_HIDDEN_SPREAD,
    }
)
FORBIDDEN_SELECTION_SOURCE_FIELDS = frozenset(
    {
        "metric",
        "metrics",
        "outcome",
        "prediction",
        "predictions",
        "r2",
        "mae",
        "p_value",
    }
)


class AnalysisSelectionError(ValueError):
    """Raised when a row subset is ambiguous, stale, or outcome-selected."""


def _frame_key(row: Mapping[str, Any]) -> tuple[str, int]:
    trajectory_id = row.get("trajectory_id")
    model_frame_idx = row.get("model_frame_idx")
    if (
        not isinstance(trajectory_id, str)
        or not trajectory_id
        or not isinstance(model_frame_idx, int)
        or isinstance(model_frame_idx, bool)
        or model_frame_idx < 0
    ):
        raise AnalysisSelectionError("Selection rows require a valid frame key.")
    return trajectory_id, model_frame_idx


def _validate_scope_row(
    selection: Mapping[str, Any],
    frame: Mapping[str, Any],
) -> None:
    scope = selection.get("scope")
    if scope not in ALLOWED_SCOPES:
        raise AnalysisSelectionError(f"Unsupported analysis scope: {scope!r}.")
    condition_role = selection.get("condition_role")
    if not isinstance(condition_role, str) or not condition_role:
        raise AnalysisSelectionError("condition_role must be non-empty.")

    if scope == SCOPE_VISIBLE_NO_WALL:
        if condition_role != "no_wall_visible_control":
            raise AnalysisSelectionError(
                "Visible positive-control rows must be declared "
                "no_wall_visible_control by the source condition manifest."
            )
        if frame.get("visibility") != "visible":
            raise AnalysisSelectionError(
                "Visible positive-control rows must have visibility='visible'."
            )
        target_name = "x_true_blocks"
    elif scope == SCOPE_HIDDEN_MEAN:
        if frame.get("visibility") != "occluded":
            raise AnalysisSelectionError("Hidden-mean rows must be occluded.")
        target_name = "mu_oracle_blocks"
    else:
        if frame.get("visibility") != "occluded":
            raise AnalysisSelectionError("Hidden-spread rows must be occluded.")
        target_name = "log_sigma_oracle"

    value = frame.get(target_name)
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
    ):
        raise AnalysisSelectionError(
            f"Scope {scope!r} requires a finite {target_name}."
        )


def build_analysis_selection_manifest(
    frame_table: Mapping[str, Any],
    selections: Sequence[Mapping[str, Any]],
    *,
    artifact_id: str,
    code_sha: str,
    source_condition_manifest_hash: str,
) -> dict[str, Any]:
    """Seal exact manifest-declared frame membership for each analysis scope."""

    validate_joined_frame_table(frame_table)
    if frame_table.get("synthetic") is True:
        scientific_use = "forbidden"
        synthetic = True
    else:
        scientific_use = "permitted"
        synthetic = False
    if not is_hex_digest(source_condition_manifest_hash, 64):
        raise AnalysisSelectionError(
            "source_condition_manifest_hash must be SHA-256."
        )
    if not isinstance(selections, Sequence) or isinstance(
        selections, (str, bytes)
    ):
        raise AnalysisSelectionError("selections must be a sequence.")
    if not selections:
        raise AnalysisSelectionError("At least one selection row is required.")

    frame_rows = {
        _frame_key(row): row
        for row in frame_table["rows"]
        if isinstance(row, Mapping)
    }
    normalized: list[dict[str, Any]] = []
    seen: set[tuple[str, int, str]] = set()
    for selection in selections:
        if not isinstance(selection, Mapping):
            raise AnalysisSelectionError("Every selection must be a mapping.")
        key = _frame_key(selection)
        scope = selection.get("scope")
        identity = (*key, scope)
        if identity in seen:
            raise AnalysisSelectionError(
                f"Duplicate frame/scope selection: {identity!r}."
            )
        seen.add(identity)
        frame = frame_rows.get(key)
        if frame is None:
            raise AnalysisSelectionError(
                f"Selection frame {key!r} is absent from the joined frame table."
            )
        if selection.get("layout_id") != frame.get("layout_id"):
            raise AnalysisSelectionError(
                f"Selection frame {key!r} names the wrong layout."
            )
        _validate_scope_row(selection, frame)
        normalized.append(
            {
                "trajectory_id": key[0],
                "model_frame_idx": key[1],
                "layout_id": frame["layout_id"],
                "scope": scope,
                "condition_role": selection["condition_role"],
            }
        )

    try:
        return seal_artifact(
            {
                "artifact_type": "analysis_selection_manifest",
                "artifact_id": artifact_id,
                "code_sha": code_sha,
                "config_hash": hash_core_analysis_config(),
                "input_manifest_hash": frame_table["artifact_hash"],
                "selection_schema_version": SELECTION_SCHEMA_VERSION,
                "source_condition_manifest_hash": source_condition_manifest_hash,
                "selection_policy": "source_manifest_declared_before_probe_results",
                "synthetic": synthetic,
                "scientific_use": scientific_use,
                "rows": sorted(
                    normalized,
                    key=lambda row: (
                        row["scope"],
                        row["layout_id"],
                        row["trajectory_id"],
                        row["model_frame_idx"],
                    ),
                ),
            }
        )
    except AnalysisArtifactError as error:
        raise AnalysisSelectionError(
            f"Could not seal analysis selection: {error}"
        ) from error


def selections_from_condition_source(
    document: Mapping[str, Any],
) -> tuple[dict[str, Any], ...]:
    """Validate a predeclared accepted condition source and flatten its scopes."""

    if not isinstance(document, Mapping):
        raise AnalysisSelectionError("Condition selection source must be a mapping.")
    if document.get("selection_source_schema_version") != (
        SELECTION_SOURCE_SCHEMA_VERSION
    ):
        raise AnalysisSelectionError("Condition selection source version mismatch.")
    if document.get("status") != "accepted":
        raise AnalysisSelectionError("Condition selection source must be accepted.")
    if document.get("selection_policy") != "predeclared_before_probe_results":
        raise AnalysisSelectionError("Condition selection policy is not frozen.")
    rows = document.get("rows")
    if not isinstance(rows, list) or not rows:
        raise AnalysisSelectionError("Condition selection source requires rows.")

    flattened: list[dict[str, Any]] = []
    seen: set[tuple[str, int, str]] = set()
    for row in rows:
        if not isinstance(row, Mapping) or row.get("status") != "accepted":
            raise AnalysisSelectionError(
                "Every condition-selection row must be an accepted mapping."
            )
        if FORBIDDEN_SELECTION_SOURCE_FIELDS & {
            str(field).lower() for field in row
        }:
            raise AnalysisSelectionError(
                "Condition selection rows cannot contain result or outcome fields."
            )
        trajectory_id, model_frame_idx = _frame_key(row)
        layout_id = row.get("layout_id")
        condition_role = row.get("condition_role")
        scopes = row.get("analysis_scopes")
        if (
            not isinstance(layout_id, str)
            or not layout_id
            or not isinstance(condition_role, str)
            or not condition_role
            or not isinstance(scopes, list)
            or not scopes
            or any(scope not in ALLOWED_SCOPES for scope in scopes)
            or len(scopes) != len(set(scopes))
        ):
            raise AnalysisSelectionError(
                "Condition selection row metadata or scopes are invalid."
            )
        for scope in scopes:
            identity = (trajectory_id, model_frame_idx, scope)
            if identity in seen:
                raise AnalysisSelectionError(
                    f"Duplicate source frame/scope selection: {identity!r}."
                )
            seen.add(identity)
            flattened.append(
                {
                    "trajectory_id": trajectory_id,
                    "model_frame_idx": model_frame_idx,
                    "layout_id": layout_id,
                    "scope": scope,
                    "condition_role": condition_role,
                }
            )
    return tuple(flattened)


def validate_analysis_selection_manifest(
    document: Mapping[str, Any],
    *,
    frame_table: Mapping[str, Any],
) -> None:
    """Authenticate a selection against the exact joined frame table."""

    validate_joined_frame_table(frame_table)
    try:
        validate_sealed_artifact(
            document,
            expected_type="analysis_selection_manifest",
        )
    except AnalysisArtifactError as error:
        raise AnalysisSelectionError(f"Invalid selection artifact: {error}") from error
    if document.get("selection_schema_version") != SELECTION_SCHEMA_VERSION:
        raise AnalysisSelectionError("Selection schema version mismatch.")
    if document.get("input_manifest_hash") != frame_table.get("artifact_hash"):
        raise AnalysisSelectionError("Selection belongs to a different frame table.")
    if document.get("config_hash") != hash_core_analysis_config():
        raise AnalysisSelectionError(
            "Selection is not bound to the literal frozen analysis config."
        )
    expected_scope = (
        (True, "forbidden")
        if frame_table.get("synthetic") is True
        else (False, "permitted")
    )
    if (
        document.get("synthetic"),
        document.get("scientific_use"),
    ) != expected_scope:
        raise AnalysisSelectionError("Selection evidence scope is inconsistent.")
    if not is_hex_digest(document.get("source_condition_manifest_hash"), 64):
        raise AnalysisSelectionError("Source condition manifest hash is invalid.")
    if (
        document.get("selection_policy")
        != "source_manifest_declared_before_probe_results"
    ):
        raise AnalysisSelectionError("Selection policy is not frozen.")
    rows = document.get("rows")
    if not isinstance(rows, list) or not rows:
        raise AnalysisSelectionError("Selection manifest requires rows.")

    # Rebuild from the declared rows to apply every semantic check, then compare
    # its normalized row content.  Artifact IDs and hashes remain those of the
    # submitted document.
    rebuilt = build_analysis_selection_manifest(
        frame_table,
        rows,
        artifact_id=document["artifact_id"],
        code_sha=document["code_sha"],
        source_condition_manifest_hash=document[
            "source_condition_manifest_hash"
        ],
    )
    if rebuilt["rows"] != rows:
        raise AnalysisSelectionError("Selection rows are not canonically ordered.")


def selected_frame_keys(
    document: Mapping[str, Any],
    *,
    scope: str,
    frame_table: Mapping[str, Any],
) -> tuple[tuple[str, int], ...]:
    """Return authenticated exact frame keys for one frozen analysis scope."""

    validate_analysis_selection_manifest(document, frame_table=frame_table)
    if scope not in ALLOWED_SCOPES:
        raise AnalysisSelectionError(f"Unsupported analysis scope: {scope!r}.")
    keys = tuple(
        (row["trajectory_id"], row["model_frame_idx"])
        for row in document["rows"]
        if row["scope"] == scope
    )
    if not keys:
        raise AnalysisSelectionError(f"Selection contains no rows for {scope!r}.")
    return keys
