"""Tamper-evident, provenance-complete inputs for Person E figures."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from mineocclude.analysis.manifests import is_hex_digest
from mineocclude.contracts.identity import CODE_SHA_LENGTH
from mineocclude.vision.config import (
    DEFAULT_PERSON_E_CONFIG_PATH,
    hash_person_e_config,
    require_live_ready_person_e_config,
)

from .registry import hash_json_value


FIGURE_FAMILIES = frozenset(
    {
        "baseline_comparison",
        "calibration_coverage",
        "context_analysis",
        "dose_response",
        "geometry_localization",
        "growth_dynamics",
        "layer_curve",
        "reveal_dynamics",
        "specificity_controls",
        "ssim_coherence",
    }
)

UNCERTAINTY_TYPES = frozenset(
    {
        "none",
        "standard_deviation",
        "standard_error",
        "bootstrap_95ci",
        "layout_trajectory_bootstrap_95ci",
        "binomial_wilson_95ci",
        "interquartile_range",
    }
)

SOURCE_LIFECYCLE_STATUSES = frozenset(
    {"accepted", "excluded", "superseded"}
)

FIGURE_INPUT_SCHEMA_VERSION = "person-e-figure-input-v0.2"


class FigureInputError(ValueError):
    """Raised when a visual could contain untraceable or invalid values."""


def _finite(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _require_nonempty_string(row: Mapping[str, Any], field: str, index: int) -> None:
    if not isinstance(row[field], str) or not row[field].strip():
        raise FigureInputError(f"Figure row {index}.{field} must be non-empty.")


def _validate_source_provenance(row: Mapping[str, Any], index: int) -> None:
    for field in (
        "source_result_id",
        "source_artifact_id",
        "source_run_id",
    ):
        _require_nonempty_string(row, field, index)
    if not is_hex_digest(row["source_artifact_hash"], 64):
        raise FigureInputError(
            f"Figure row {index}.source_artifact_hash must be SHA-256."
        )
    if not is_hex_digest(row["accepted_manifest_hash"], 64):
        raise FigureInputError(
            f"Figure row {index}.accepted_manifest_hash must be SHA-256."
        )
    fold_hash = row["fold_manifest_hash"]
    if fold_hash is not None and not is_hex_digest(fold_hash, 64):
        raise FigureInputError(
            f"Figure row {index}.fold_manifest_hash must be null or SHA-256."
        )

    lifecycle = row["source_lifecycle"]
    if lifecycle not in SOURCE_LIFECYCLE_STATUSES:
        raise FigureInputError(
            f"Figure row {index}.source_lifecycle is not recognized."
        )
    superseded_by = row["source_superseded_by"]
    if lifecycle == "superseded":
        if not isinstance(superseded_by, str) or not superseded_by.strip():
            raise FigureInputError(
                "Superseded sources require a non-empty source_superseded_by ID."
            )
    elif superseded_by is not None:
        raise FigureInputError(
            "Only superseded sources may carry source_superseded_by."
        )


def _validate_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    if not rows:
        raise FigureInputError("Figure inputs require at least one source row.")

    required = {
        "series_id",
        "source_result_id",
        "source_artifact_id",
        "source_artifact_hash",
        "source_run_id",
        "source_lifecycle",
        "source_superseded_by",
        "accepted_manifest_hash",
        "fold_manifest_hash",
        "x",
        "y",
        "x_unit",
        "y_unit",
        "sample_count",
        "uncertainty_type",
        "lower",
        "upper",
        "status",
        "diagnostic",
    }
    normalized: list[dict[str, Any]] = []
    seen: set[tuple[str, str, float]] = set()

    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise FigureInputError(f"Figure row {index} must be a mapping.")
        if set(row) != required:
            missing = sorted(required - set(row))
            extra = sorted(set(row) - required)
            raise FigureInputError(
                f"Figure row {index} fields changed; missing={missing}, extra={extra}."
            )

        for field in ("series_id", "x_unit", "y_unit"):
            _require_nonempty_string(row, field, index)
        _validate_source_provenance(row, index)

        if not _finite(row["x"]):
            raise FigureInputError(f"Figure row {index}.x must be finite.")
        count = row["sample_count"]
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            raise FigureInputError("sample_count must be a non-negative integer.")

        status = row["status"]
        if status not in {"valid", "invalid"}:
            raise FigureInputError("Figure status must be valid or invalid.")
        uncertainty = row["uncertainty_type"]
        if uncertainty not in UNCERTAINTY_TYPES:
            raise FigureInputError(
                f"Unknown uncertainty_type {uncertainty!r}; use a frozen value."
            )

        if status == "valid":
            if count <= 0:
                raise FigureInputError(
                    "Valid figure rows require a positive sample_count."
                )
            if row["source_lifecycle"] != "accepted" or row[
                "source_superseded_by"
            ] is not None:
                raise FigureInputError(
                    "Valid rows require an accepted, non-superseded source."
                )
            if not _finite(row["y"]):
                raise FigureInputError("Valid figure rows require finite y values.")
            if uncertainty == "none":
                if row["lower"] is not None or row["upper"] is not None:
                    raise FigureInputError(
                        "Rows with uncertainty_type='none' require null bounds."
                    )
            elif not (
                _finite(row["lower"])
                and _finite(row["upper"])
                and float(row["lower"]) <= float(row["y"]) <= float(row["upper"])
            ):
                raise FigureInputError(
                    "Uncertainty bounds must be finite and contain the plotted value."
                )
            if row["diagnostic"] is not None:
                raise FigureInputError("Valid figure rows require diagnostic=null.")
        elif (
            row["y"] is not None
            or row["lower"] is not None
            or row["upper"] is not None
            or not isinstance(row["diagnostic"], str)
            or not row["diagnostic"].strip()
        ):
            raise FigureInputError(
                "Invalid rows retain null numeric output and a diagnostic."
            )

        key = (row["series_id"], row["source_result_id"], float(row["x"]))
        if key in seen:
            raise FigureInputError(f"Duplicate figure row identity {key!r}.")
        seen.add(key)
        normalized.append(dict(row))

    return sorted(
        normalized,
        key=lambda row: (
            row["series_id"],
            float(row["x"]),
            row["source_result_id"],
        ),
    )


def _derived_provenance(rows: Sequence[Mapping[str, Any]]) -> dict[str, list[str]]:
    """Derive all figure-level lineage from the validated source rows."""

    return {
        "source_artifact_ids": sorted({row["source_artifact_id"] for row in rows}),
        "source_artifact_hashes": sorted(
            {row["source_artifact_hash"] for row in rows}
        ),
        "source_run_ids": sorted({row["source_run_id"] for row in rows}),
        "accepted_manifest_hashes": sorted(
            {row["accepted_manifest_hash"] for row in rows}
        ),
        "fold_manifest_hashes": sorted(
            {
                row["fold_manifest_hash"]
                for row in rows
                if row["fold_manifest_hash"] is not None
            }
        ),
    }


def build_figure_input(
    rows: Sequence[Mapping[str, Any]],
    *,
    figure_id: str,
    figure_family: str,
    code_sha: str,
    result_scope: str = "scientific",
    config_path: Path | str = DEFAULT_PERSON_E_CONFIG_PATH,
) -> dict[str, Any]:
    """Seal plot-ready values using provenance derived from every source row."""

    if not isinstance(figure_id, str) or not figure_id.strip():
        raise FigureInputError("figure_id must be non-empty.")
    if figure_family not in FIGURE_FAMILIES:
        raise FigureInputError(f"Unknown figure_family {figure_family!r}.")
    if not is_hex_digest(code_sha, CODE_SHA_LENGTH):
        raise FigureInputError("code_sha must be a full hexadecimal Git SHA.")
    if result_scope not in {"scientific", "known_answer"}:
        raise FigureInputError("result_scope must be scientific or known_answer.")
    if result_scope == "scientific":
        require_live_ready_person_e_config(config_path)
    if (
        not isinstance(rows, Sequence)
        or isinstance(rows, (str, bytes))
        or any(not isinstance(row, Mapping) for row in rows)
    ):
        raise FigureInputError("rows must be a sequence of mappings.")

    normalized_rows = _validate_rows(rows)
    document = {
        "figure_input_schema_version": FIGURE_INPUT_SCHEMA_VERSION,
        "figure_id": figure_id,
        "figure_family": figure_family,
        "result_scope": result_scope,
        "code_sha": code_sha,
        "config_hash": hash_person_e_config(config_path),
        **_derived_provenance(normalized_rows),
        "rows": normalized_rows,
    }
    document["figure_input_hash"] = hash_json_value(document)
    return document


def validate_figure_input(
    document: Mapping[str, Any],
    *,
    config_path: Path | str = DEFAULT_PERSON_E_CONFIG_PATH,
) -> None:
    """Rebuild once and require byte-independent semantic equality."""

    if not isinstance(document, Mapping):
        raise FigureInputError("Figure input must be a mapping.")
    required = {
        "figure_input_schema_version",
        "figure_id",
        "figure_family",
        "result_scope",
        "code_sha",
        "config_hash",
        "source_artifact_ids",
        "source_artifact_hashes",
        "source_run_ids",
        "accepted_manifest_hashes",
        "fold_manifest_hashes",
        "rows",
        "figure_input_hash",
    }
    if set(document) != required:
        raise FigureInputError("Figure-input envelope fields have changed.")
    if document["figure_input_schema_version"] != FIGURE_INPUT_SCHEMA_VERSION:
        raise FigureInputError("Figure-input schema version mismatch.")

    expected = build_figure_input(
        document["rows"],
        figure_id=document["figure_id"],
        figure_family=document["figure_family"],
        code_sha=document["code_sha"],
        result_scope=document["result_scope"],
        config_path=config_path,
    )
    if dict(document) != expected:
        raise FigureInputError(
            "Figure input differs from its validated rows, config, or derived provenance."
        )
