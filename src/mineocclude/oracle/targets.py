"""Build traceable Person B Regime A oracle-target documents."""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from mineocclude.contracts.identity import (
    FRAME_KEY,
    REQUIRED_FIELDS,
    SCHEMA_VERSION,
    IdentityValidationError,
    assert_trajectory_consistency,
    assert_unique,
    validate_identity,
)
from mineocclude.analysis.config import DEFAULT_CONFIG_PATH, hash_core_analysis_config
from mineocclude.analysis.coordinates import (
    CoordinateContractError,
    validate_coordinate_frame,
)

from .closed_form import closed_form_posterior
from .primary_scalar_kalman import scalar_kalman_posterior
from .schema import (
    ALLOWED_VISIBILITY,
    ORACLE_INFORMATION_SET,
    ORACLE_METHOD,
    ORACLE_TARGET_SCHEMA_VERSION,
    REGIME_A,
    REGIME_A_DT_SECONDS,
    SYNTHETIC_COMPATIBILITY_REGIME,
    TARGET_ID_SUFFIX,
    TARGET_SOURCE,
    VISIBLE,
    OracleValidationError,
    is_sha256,
    require_finite_number,
    validate_oracle_target_document,
    validate_oracle_target_rows,
    validate_trajectory_timebase_rows,
)


AGREEMENT_TOLERANCE = 1e-6


def _hidden_ticks(tau_seconds: float) -> int:
    raw_ticks = tau_seconds / REGIME_A_DT_SECONDS
    ticks = round(raw_ticks)
    if not math.isclose(raw_ticks, ticks, rel_tol=0.0, abs_tol=1e-9):
        raise OracleValidationError("tau must be an integer number of 20 Hz ticks.")
    return ticks


def _validate_state_row(row: Mapping[str, Any]) -> None:
    try:
        validate_identity(row)
    except IdentityValidationError as error:
        raise OracleValidationError(f"Invalid universal identity: {error}") from error

    if row["status"] != "accepted":
        raise OracleValidationError(
            "Oracle construction accepts only explicitly accepted source rows."
        )
    if row["visibility"] not in ALLOWED_VISIBILITY:
        raise OracleValidationError(
            f"visibility must be one of: {', '.join(sorted(ALLOWED_VISIBILITY))}."
        )
    if require_finite_number("q", row["q"]) < 0:
        raise OracleValidationError("q cannot be negative for the primary oracle.")

    for field in ("x_true_blocks", "observed_position_blocks"):
        if field not in row:
            raise OracleValidationError(f"State row is missing {field}.")

    true_position = require_finite_number("x_true_blocks", row["x_true_blocks"])
    if row["visibility"] == VISIBLE:
        observed_position = require_finite_number(
            "observed_position_blocks",
            row["observed_position_blocks"],
        )
        if not math.isclose(float(row["tau"]), 0.0, abs_tol=1e-12):
            raise OracleValidationError("Visible rows must reset tau to zero.")
        if not math.isclose(
            true_position,
            observed_position,
            rel_tol=0.0,
            abs_tol=1e-10,
        ):
            raise OracleValidationError(
                "Visible truth must equal the authoritative visible position."
            )
    else:
        if row["observed_position_blocks"] is not None:
            raise OracleValidationError(
                "Occluded rows cannot expose an observed position."
            )
        tau = require_finite_number("tau", row["tau"])
        if tau <= 0.0:
            raise OracleValidationError("Occluded rows require positive tau.")
        _hidden_ticks(tau)

    manifest_hash = row.get("accepted_manifest_hash")
    if not is_sha256(manifest_hash):
        raise OracleValidationError(
            "State rows require a valid SHA-256 accepted_manifest_hash."
        )

    synthetic = row.get("synthetic")
    if synthetic is not None and not isinstance(synthetic, bool):
        raise OracleValidationError("synthetic must be boolean when present.")
    if synthetic is True and row.get("scientific_use") != "forbidden":
        raise OracleValidationError(
            "Synthetic state rows must set scientific_use='forbidden'."
        )
    if row["regime"] != REGIME_A and not (
        row["regime"] == SYNTHETIC_COMPATIBILITY_REGIME
        and synthetic is True
        and row.get("scientific_use") == "forbidden"
    ):
        raise OracleValidationError(
            "Primary oracle inputs require regime_a; synthetic_test is allowed "
            "only for non-scientific compatibility fixtures."
        )


def _validate_document_envelope(state_document: Mapping[str, Any]) -> list[Any]:
    if state_document.get("schema_version") != SCHEMA_VERSION:
        raise OracleValidationError(
            f"State document must declare schema_version {SCHEMA_VERSION!r}."
        )
    if state_document.get("join_key") != list(FRAME_KEY):
        raise OracleValidationError(
            "State document join_key must be ['trajectory_id', 'model_frame_idx']."
        )

    rows = state_document.get("rows")
    if not isinstance(rows, list):
        raise OracleValidationError("State document must contain a rows list.")

    metadata = state_document.get("fixture_metadata")
    if metadata is not None:
        if not isinstance(metadata, Mapping):
            raise OracleValidationError("fixture_metadata must be a mapping.")
        if (
            metadata.get("synthetic") is not True
            or metadata.get("scientific_use") != "forbidden"
        ):
            raise OracleValidationError(
                "Fixture metadata must mark synthetic evidence as non-scientific."
            )
    return rows


def _build_regime_a_targets_with_hash(
    state_rows: Iterable[Mapping[str, Any]],
    *,
    oracle_run_id: str,
    oracle_code_sha: str,
    oracle_config_hash: str,
) -> list[dict[str, Any]]:
    """Build exact-oracle rows without using hidden truth as an input."""

    rows: list[dict[str, Any]] = []
    for index, row in enumerate(state_rows):
        if not isinstance(row, Mapping):
            raise OracleValidationError(f"State row {index} must be a mapping.")
        rows.append(dict(row))
    if not rows:
        raise OracleValidationError("At least one state row is required.")
    for row in rows:
        _validate_state_row(row)
    validate_trajectory_timebase_rows(rows)
    try:
        assert_unique(rows)
        assert_trajectory_consistency(rows)
    except IdentityValidationError as error:
        raise OracleValidationError(f"Invalid source row set: {error}") from error

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["trajectory_id"]].append(row)

    targets: list[dict[str, Any]] = []
    for trajectory_id in sorted(grouped):
        trajectory_rows = sorted(
            grouped[trajectory_id],
            key=lambda row: row["model_frame_idx"],
        )
        last_visible_position: float | None = None

        for row in trajectory_rows:
            source_run_id = row["run_id"]
            if row["visibility"] == VISIBLE:
                last_visible_position = float(row["observed_position_blocks"])
                iterative = scalar_kalman_posterior(
                    last_visible_position,
                    row["v"],
                    row["q"],
                    0,
                )
                closed = closed_form_posterior(
                    last_visible_position,
                    row["v"],
                    row["q"],
                    0.0,
                )
            else:
                if last_visible_position is None:
                    raise OracleValidationError(
                        "An occluded row cannot precede the first visible observation."
                    )
                tau = float(row["tau"])
                iterative = scalar_kalman_posterior(
                    last_visible_position,
                    row["v"],
                    row["q"],
                    _hidden_ticks(tau),
                )
                closed = closed_form_posterior(
                    last_visible_position,
                    row["v"],
                    row["q"],
                    tau,
                )

            if not math.isclose(
                iterative.mean_blocks,
                closed.mean_blocks,
                rel_tol=0.0,
                abs_tol=AGREEMENT_TOLERANCE,
            ) or not math.isclose(
                iterative.variance_blocks2,
                closed.variance_blocks2,
                rel_tol=0.0,
                abs_tol=AGREEMENT_TOLERANCE,
            ):
                raise OracleValidationError(
                    "Independent Regime A oracle implementations disagree."
                )

            target = {field: row[field] for field in REQUIRED_FIELDS}
            target.update(
                {
                    "code_sha": oracle_code_sha,
                    "config_hash": oracle_config_hash,
                    "run_id": oracle_run_id,
                    "target_schema_version": ORACLE_TARGET_SCHEMA_VERSION,
                    "target_id": (
                        f"{trajectory_id}:{row['model_frame_idx']}:{TARGET_ID_SUFFIX}"
                    ),
                    "target_source": TARGET_SOURCE,
                    "oracle_method": ORACLE_METHOD,
                    "oracle_information_set": list(ORACLE_INFORMATION_SET),
                    "accepted_manifest_hash": row["accepted_manifest_hash"],
                    "source_run_id": source_run_id,
                    "last_visible_position_blocks": last_visible_position,
                    "mu_oracle_blocks": iterative.mean_blocks,
                    "var_oracle_blocks2": iterative.variance_blocks2,
                    "sigma_oracle_blocks": iterative.sigma_blocks,
                    "log_sigma_oracle": iterative.log_sigma,
                    "x_true_blocks": float(row["x_true_blocks"]),
                }
            )
            if "synthetic" in row:
                target["synthetic"] = row["synthetic"]
            if "scientific_use" in row:
                target["scientific_use"] = row["scientific_use"]
            targets.append(target)

    validate_oracle_target_rows(targets)
    return targets


def build_regime_a_targets(
    state_rows: Iterable[Mapping[str, Any]],
    *,
    oracle_run_id: str,
    oracle_code_sha: str,
    coordinate_frame: Mapping[str, Any],
    analysis_config_path: Path | str = DEFAULT_CONFIG_PATH,
) -> list[dict[str, Any]]:
    """Build validated rows; claim-bearing joins still require the document."""

    try:
        validate_coordinate_frame(coordinate_frame)
        config_hash = hash_core_analysis_config(analysis_config_path)
    except (CoordinateContractError, ValueError) as error:
        raise OracleValidationError(
            f"Target construction metadata is invalid: {error}"
        ) from error
    return _build_regime_a_targets_with_hash(
        state_rows,
        oracle_run_id=oracle_run_id,
        oracle_code_sha=oracle_code_sha,
        oracle_config_hash=config_hash,
    )


def build_regime_a_target_document(
    state_document: Mapping[str, Any],
    *,
    oracle_run_id: str,
    oracle_code_sha: str,
    oracle_config_hash: str | None = None,
    analysis_config_path: Path | str | None = None,
) -> dict[str, Any]:
    """Build targets from a B-owned state table with schema-v1 row identity."""

    if not isinstance(state_document, Mapping):
        raise OracleValidationError("State document must be a mapping.")
    rows = _validate_document_envelope(state_document)
    fixture_metadata = state_document.get("fixture_metadata")
    is_non_scientific_fixture = (
        isinstance(fixture_metadata, Mapping)
        and fixture_metadata.get("synthetic") is True
        and fixture_metadata.get("scientific_use") == "forbidden"
    )
    coordinate_frame: Mapping[str, Any] | None = None
    if not is_non_scientific_fixture:
        coordinate_frame = state_document.get("coordinate_frame")
        try:
            validate_coordinate_frame(coordinate_frame)
        except CoordinateContractError as error:
            raise OracleValidationError(
                f"Live state document has an invalid coordinate frame: {error}"
            ) from error

    if oracle_config_hash is not None and analysis_config_path is not None:
        raise OracleValidationError(
            "Supply analysis_config_path or oracle_config_hash, not both."
        )
    if oracle_config_hash is None:
        try:
            oracle_config_hash = hash_core_analysis_config(
                analysis_config_path or DEFAULT_CONFIG_PATH
            )
        except ValueError as error:
            raise OracleValidationError(
                f"Analysis configuration is invalid: {error}"
            ) from error
    else:
        metadata = state_document.get("fixture_metadata")
        explicitly_non_scientific = (
            isinstance(metadata, Mapping)
            and metadata.get("synthetic") is True
            and metadata.get("scientific_use") == "forbidden"
            and all(
                isinstance(row, Mapping)
                and row.get("synthetic") is True
                and row.get("scientific_use") == "forbidden"
                for row in rows
            )
        )
        if not explicitly_non_scientific:
            raise OracleValidationError(
                "Claim-bearing target generation must hash the actual analysis "
                "config file; explicit hashes are restricted to legacy "
                "non-scientific fixtures."
            )
        if not is_sha256(oracle_config_hash):
            raise OracleValidationError("oracle_config_hash must be SHA-256.")

    targets = _build_regime_a_targets_with_hash(
        rows,
        oracle_run_id=oracle_run_id,
        oracle_code_sha=oracle_code_sha,
        oracle_config_hash=oracle_config_hash,
    )
    document: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "target_schema_version": ORACLE_TARGET_SCHEMA_VERSION,
        "join_key": ["trajectory_id", "model_frame_idx"],
        "rows": targets,
    }
    if coordinate_frame is not None:
        document["coordinate_frame"] = dict(coordinate_frame)
    if "fixture_metadata" in state_document:
        document["fixture_metadata"] = dict(state_document["fixture_metadata"])
        if any(row.get("synthetic") is not True for row in targets):
            raise OracleValidationError(
                "Every row in a synthetic fixture must set synthetic=true."
            )
    validate_oracle_target_document(
        document,
        analysis_config_path=analysis_config_path,
    )
    return document
