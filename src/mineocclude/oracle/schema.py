"""Schema and validation for Person B Regime A oracle targets."""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from mineocclude.contracts.identity import (
    SCHEMA_VERSION,
    IdentityValidationError,
    validate_identity,
)


ORACLE_TARGET_SCHEMA_VERSION = "person-b-oracle-target-v0.1"
REGIME_A_DT_SECONDS = 0.05
TARGET_ID_SUFFIX = "regime_a_primary_v1"
TARGET_SOURCE = "authoritative_visible_state_known_v_q"
ORACLE_METHOD = "primary_scalar_kalman_crosschecked_closed_form"
VISIBLE = "visible"
OCCLUDED = "occluded"
ALLOWED_VISIBILITY = frozenset({VISIBLE, OCCLUDED})
REGIME_A = "regime_a"
SYNTHETIC_COMPATIBILITY_REGIME = "synthetic_test"
ORACLE_INFORMATION_SET = (
    "last_visible_position_blocks",
    "v",
    "q",
    "tau",
    "visibility",
)


class OracleValidationError(ValueError):
    """Raised when an oracle target violates Person B's Phase 1 contract."""


def require_finite_number(name: str, value: Any) -> float:
    """Return a finite float or raise the oracle's public validation error."""

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise OracleValidationError(f"{name} must be numeric.")
    result = float(value)
    if not math.isfinite(result):
        raise OracleValidationError(f"{name} must be finite.")
    return result


def is_sha256(value: Any) -> bool:
    """Return whether ``value`` is a canonical SHA-256 hexadecimal string."""

    if not isinstance(value, str) or len(value) != 64:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return True


@dataclass(frozen=True)
class ScalarPosterior:
    """One scalar Gaussian posterior in wall-parallel world coordinates."""

    mean_blocks: float
    variance_blocks2: float

    def __post_init__(self) -> None:
        mean = require_finite_number("Posterior mean", self.mean_blocks)
        variance = require_finite_number(
            "Posterior variance",
            self.variance_blocks2,
        )
        if variance < 0:
            raise OracleValidationError("Posterior variance cannot be negative.")
        object.__setattr__(self, "mean_blocks", mean)
        object.__setattr__(self, "variance_blocks2", variance)

    @property
    def sigma_blocks(self) -> float:
        return math.sqrt(self.variance_blocks2)

    @property
    def log_sigma(self) -> float | None:
        sigma = self.sigma_blocks
        return None if sigma == 0.0 else math.log(sigma)


def validate_oracle_target(row: Mapping[str, Any]) -> None:
    """Validate a claim-bearing Person B oracle-target row."""

    if not isinstance(row, Mapping):
        raise OracleValidationError("Oracle target must be a mapping.")
    try:
        validate_identity(row)
    except IdentityValidationError as error:
        raise OracleValidationError(f"Invalid universal identity: {error}") from error

    required = (
        "target_schema_version",
        "target_id",
        "target_source",
        "oracle_method",
        "oracle_information_set",
        "accepted_manifest_hash",
        "source_run_id",
        "last_visible_position_blocks",
        "mu_oracle_blocks",
        "var_oracle_blocks2",
        "sigma_oracle_blocks",
        "log_sigma_oracle",
        "x_true_blocks",
    )
    missing = [field for field in required if field not in row]
    if missing:
        raise OracleValidationError(
            "Missing oracle-target fields: " + ", ".join(missing)
        )

    if row["schema_version"] != SCHEMA_VERSION:
        raise OracleValidationError("Universal schema version mismatch.")
    if row["target_schema_version"] != ORACLE_TARGET_SCHEMA_VERSION:
        raise OracleValidationError("Oracle target schema version mismatch.")

    for field in ("target_id", "target_source", "oracle_method", "source_run_id"):
        value = row[field]
        if not isinstance(value, str) or not value.strip():
            raise OracleValidationError(f"{field} must be a non-empty string.")

    if (
        not isinstance(row["oracle_information_set"], list)
        or row["oracle_information_set"] != list(ORACLE_INFORMATION_SET)
    ):
        raise OracleValidationError("Oracle information set is not the frozen set.")
    if row["target_source"] != TARGET_SOURCE:
        raise OracleValidationError("Oracle target source is not the frozen source.")
    if row["oracle_method"] != ORACLE_METHOD:
        raise OracleValidationError("Oracle method is not the frozen primary method.")

    expected_target_id = (
        f"{row['trajectory_id']}:{row['model_frame_idx']}:{TARGET_ID_SUFFIX}"
    )
    if row["target_id"] != expected_target_id:
        raise OracleValidationError("target_id does not match the frame identity.")

    if not is_sha256(row["accepted_manifest_hash"]):
        raise OracleValidationError("accepted_manifest_hash must be SHA-256.")

    last_visible = require_finite_number(
        "last_visible_position_blocks",
        row["last_visible_position_blocks"],
    )
    mean = require_finite_number("mu_oracle_blocks", row["mu_oracle_blocks"])
    variance = require_finite_number(
        "var_oracle_blocks2",
        row["var_oracle_blocks2"],
    )
    sigma = require_finite_number(
        "sigma_oracle_blocks",
        row["sigma_oracle_blocks"],
    )
    true_position = require_finite_number("x_true_blocks", row["x_true_blocks"])
    tau = require_finite_number("tau", row["tau"])
    velocity = require_finite_number("v", row["v"])
    process_noise = require_finite_number("q", row["q"])
    if process_noise < 0:
        raise OracleValidationError("q cannot be negative for the primary oracle.")

    if variance < 0 or sigma < 0:
        raise OracleValidationError("Variance and spread cannot be negative.")
    if not math.isclose(sigma * sigma, variance, rel_tol=1e-10, abs_tol=1e-12):
        raise OracleValidationError("Spread squared must equal posterior variance.")

    log_sigma = row["log_sigma_oracle"]
    if sigma == 0.0:
        if log_sigma is not None:
            raise OracleValidationError("Zero-spread rows cannot receive a log target.")
    else:
        log_sigma = require_finite_number("log_sigma_oracle", log_sigma)
        if not math.isclose(
            log_sigma,
            math.log(sigma),
            rel_tol=1e-10,
            abs_tol=1e-12,
        ):
            raise OracleValidationError("log_sigma_oracle must equal ln(sigma).")

    visibility = row["visibility"]
    if visibility not in ALLOWED_VISIBILITY:
        raise OracleValidationError(
            f"visibility must be one of: {', '.join(sorted(ALLOWED_VISIBILITY))}."
        )

    expected_mean = last_visible + velocity * tau
    expected_variance = process_noise * tau
    if not math.isclose(mean, expected_mean, rel_tol=0.0, abs_tol=1e-10):
        raise OracleValidationError("Oracle mean does not match x_last + v*tau.")
    if not math.isclose(
        variance,
        expected_variance,
        rel_tol=0.0,
        abs_tol=1e-10,
    ):
        raise OracleValidationError("Oracle variance does not match q*tau.")

    if visibility == VISIBLE:
        if tau != 0.0 or variance != 0.0 or log_sigma is not None:
            raise OracleValidationError(
                "Visible rows require tau=0, zero variance, and no log target."
            )
        if not math.isclose(
            true_position,
            last_visible,
            rel_tol=0.0,
            abs_tol=1e-10,
        ):
            raise OracleValidationError(
                "Visible truth must equal the authoritative visible position."
            )
    elif tau <= 0.0:
        raise OracleValidationError("Occluded rows require positive tau.")

    synthetic = row.get("synthetic")
    if synthetic is not None and not isinstance(synthetic, bool):
        raise OracleValidationError("synthetic must be boolean when present.")
    if synthetic is True and row.get("scientific_use") != "forbidden":
        raise OracleValidationError(
            "Synthetic oracle targets must set scientific_use='forbidden'."
        )
    if row["regime"] != REGIME_A and not (
        row["regime"] == SYNTHETIC_COMPATIBILITY_REGIME
        and synthetic is True
        and row.get("scientific_use") == "forbidden"
    ):
        raise OracleValidationError(
            "Primary oracle targets require regime_a; synthetic_test is allowed "
            "only for non-scientific compatibility fixtures."
        )


def validate_oracle_target_rows(rows: Iterable[Mapping[str, Any]]) -> None:
    """Validate cross-row provenance and hidden/reveal state transitions."""

    materialized = list(rows)
    if not materialized:
        raise OracleValidationError("At least one oracle target is required.")

    seen_keys: set[tuple[str, int]] = set()
    for row in materialized:
        validate_oracle_target(row)
        key = (row["trajectory_id"], row["model_frame_idx"])
        if key in seen_keys:
            raise OracleValidationError(f"Duplicate oracle target key: {key}.")
        seen_keys.add(key)

    for field in (
        "run_id",
        "code_sha",
        "config_hash",
        "accepted_manifest_hash",
        "model_hash",
        "preprocess_hash",
    ):
        if len({row[field] for row in materialized}) != 1:
            raise OracleValidationError(
                f"One target table cannot mix {field} values."
            )
    if len({row.get("synthetic", False) for row in materialized}) != 1:
        raise OracleValidationError(
            "One target table cannot mix synthetic and non-synthetic rows."
        )

    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in materialized:
        grouped[row["trajectory_id"]].append(row)

    for trajectory_id, trajectory_rows in grouped.items():
        if len({row["source_run_id"] for row in trajectory_rows}) != 1:
            raise OracleValidationError(
                f"Trajectory {trajectory_id!r} mixes source run IDs."
            )
        if len({row["layout_id"] for row in trajectory_rows}) != 1:
            raise OracleValidationError(
                f"Trajectory {trajectory_id!r} mixes layout IDs."
            )

        last_visible: float | None = None
        interval_velocity: float | None = None
        interval_process_noise: float | None = None
        previous_hidden_tau = 0.0
        previous_server_tick: int | None = None

        for row in sorted(trajectory_rows, key=lambda item: item["model_frame_idx"]):
            server_tick = row["server_tick"]
            if previous_server_tick is not None and server_tick <= previous_server_tick:
                raise OracleValidationError(
                    f"Trajectory {trajectory_id!r} must have increasing server ticks."
                )
            previous_server_tick = server_tick

            if row["visibility"] == VISIBLE:
                last_visible = float(row["last_visible_position_blocks"])
                interval_velocity = float(row["v"])
                interval_process_noise = float(row["q"])
                previous_hidden_tau = 0.0
                continue

            if last_visible is None:
                raise OracleValidationError(
                    "An occluded target cannot precede the first visible target."
                )
            if not math.isclose(
                float(row["last_visible_position_blocks"]),
                last_visible,
                rel_tol=0.0,
                abs_tol=1e-10,
            ):
                raise OracleValidationError(
                    "Occluded targets must preserve the most recent visible position."
                )
            if (
                float(row["v"]) != interval_velocity
                or float(row["q"]) != interval_process_noise
            ):
                raise OracleValidationError(
                    "v and q must remain fixed throughout each occluded run."
                )

            tau = float(row["tau"])
            if tau <= previous_hidden_tau:
                raise OracleValidationError(
                    "tau must increase throughout an occluded run before reveal."
                )
            previous_hidden_tau = tau
