"""Schema and validation for Person B Regime A oracle targets."""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from mineocclude.contracts.identity import (
    SCHEMA_VERSION,
    IdentityValidationError,
    validate_identity,
)

ORACLE_TARGET_SCHEMA_VERSION = "person-b-oracle-target-v0.1"
PRODUCTION_ORACLE_DOCUMENT_FORMAT_VERSION = (
    "person-b-production-oracle-target-document-v0.1"
)
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


class OracleRejectionCode(str, Enum):
    """Stable codes for cross-row oracle/source-timing failures."""

    MIXED_EPISODE_ID = "mixed_episode_id"
    NONCONSECUTIVE_SERVER_TICK = "nonconsecutive_server_tick"
    TIMEBASE_MISMATCH = "timebase_mismatch"


class OracleValidationError(ValueError):
    """Raised when an oracle target violates Person B's Phase 1 contract."""

    def __init__(
        self,
        message: str,
        *,
        code: OracleRejectionCode | None = None,
    ) -> None:
        self.code = code
        rendered = f"{code.value}: {message}" if code is not None else message
        super().__init__(rendered)


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


def validate_trajectory_timebase_rows(
    rows: Iterable[Mapping[str, Any]],
) -> None:
    """Require one episode and a consecutive 20 Hz frame/tick timebase.

    Callers validate each universal identity before this cross-row check. Rows
    are grouped and sorted by explicit identity; input order is never timing.
    """

    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["trajectory_id"]].append(row)

    for trajectory_id, trajectory_rows in grouped.items():
        if len({row["episode_id"] for row in trajectory_rows}) != 1:
            raise OracleValidationError(
                f"Trajectory {trajectory_id!r} contains multiple episode IDs.",
                code=OracleRejectionCode.MIXED_EPISODE_ID,
            )

        ordered = sorted(
            trajectory_rows,
            key=lambda item: item["model_frame_idx"],
        )
        previous_model_frame_idx: int | None = None
        previous_server_tick: int | None = None
        last_visible_model_frame_idx: int | None = None
        last_visible_server_tick: int | None = None

        for row in ordered:
            model_frame_idx = row["model_frame_idx"]
            server_tick = row["server_tick"]
            if (
                previous_model_frame_idx is not None
                and model_frame_idx != previous_model_frame_idx + 1
            ):
                raise OracleValidationError(
                    f"Trajectory {trajectory_id!r} has nonconsecutive model frames.",
                    code=OracleRejectionCode.TIMEBASE_MISMATCH,
                )
            if (
                previous_server_tick is not None
                and server_tick != previous_server_tick + 1
            ):
                raise OracleValidationError(
                    f"Trajectory {trajectory_id!r} has nonconsecutive server ticks.",
                    code=OracleRejectionCode.NONCONSECUTIVE_SERVER_TICK,
                )

            tau = float(row["tau"])
            if row["visibility"] == VISIBLE:
                if not math.isclose(tau, 0.0, rel_tol=0.0, abs_tol=1e-12):
                    raise OracleValidationError(
                        "Visible rows must reset tau on the 20 Hz timebase.",
                        code=OracleRejectionCode.TIMEBASE_MISMATCH,
                    )
                last_visible_model_frame_idx = model_frame_idx
                last_visible_server_tick = server_tick
            elif (
                last_visible_model_frame_idx is not None
                and last_visible_server_tick is not None
            ):
                frame_ticks = model_frame_idx - last_visible_model_frame_idx
                server_ticks = server_tick - last_visible_server_tick
                expected_tau = server_ticks * REGIME_A_DT_SECONDS
                if frame_ticks != server_ticks or not math.isclose(
                    tau,
                    expected_tau,
                    rel_tol=0.0,
                    abs_tol=1e-12,
                ):
                    raise OracleValidationError(
                        "tau progression disagrees with the 20 Hz frame/tick timebase.",
                        code=OracleRejectionCode.TIMEBASE_MISMATCH,
                    )
            else:
                raise OracleValidationError(
                    "An occluded row cannot precede its visible timebase anchor.",
                    code=OracleRejectionCode.TIMEBASE_MISMATCH,
                )

            previous_model_frame_idx = model_frame_idx
            previous_server_tick = server_tick


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

    validate_trajectory_timebase_rows(materialized)

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


def validate_oracle_target_document(
    document: Mapping[str, Any],
    *,
    analysis_config_path: Path | str | None = None,
) -> None:
    """Validate the target envelope, coordinate frame, and all target rows."""

    if not isinstance(document, Mapping):
        raise OracleValidationError("Oracle target document must be a mapping.")
    production_format = document.get("oracle_document_format_version")
    if production_format is not None:
        if production_format != PRODUCTION_ORACLE_DOCUMENT_FORMAT_VERSION:
            raise OracleValidationError(
                "Unknown production oracle document format version."
            )
        _validate_production_oracle_target_document(
            document,
            analysis_config_path=analysis_config_path,
        )
        return
    if document.get("schema_version") != SCHEMA_VERSION:
        raise OracleValidationError("Oracle target document schema mismatch.")
    if document.get("target_schema_version") != ORACLE_TARGET_SCHEMA_VERSION:
        raise OracleValidationError("Oracle target document version mismatch.")
    if document.get("join_key") != ["trajectory_id", "model_frame_idx"]:
        raise OracleValidationError("Oracle target document join_key is invalid.")
    rows = document.get("rows")
    if not isinstance(rows, list):
        raise OracleValidationError("Oracle target document requires a rows list.")
    metadata = document.get("fixture_metadata")
    is_non_scientific_fixture = (
        isinstance(metadata, Mapping)
        and metadata.get("synthetic") is True
        and metadata.get("scientific_use") == "forbidden"
    )
    if not is_non_scientific_fixture:
        from mineocclude.analysis.config import (
            DEFAULT_CONFIG_PATH,
            hash_core_analysis_config,
        )
        from mineocclude.analysis.coordinates import (
            CoordinateContractError,
            validate_coordinate_frame,
        )

        try:
            validate_coordinate_frame(document.get("coordinate_frame"))
        except CoordinateContractError as error:
            raise OracleValidationError(
                f"Oracle target coordinate frame is invalid: {error}"
            ) from error
        bound_config_hash = hash_core_analysis_config(
            analysis_config_path or DEFAULT_CONFIG_PATH
        )
        if any(row.get("config_hash") != bound_config_hash for row in rows):
            raise OracleValidationError(
                "Oracle targets are not bound to the current literal analysis "
                "config bytes."
            )
    validate_oracle_target_rows(rows)


def _validate_production_oracle_target_document(
    document: Mapping[str, Any],
    *,
    analysis_config_path: Path | str | None,
) -> None:
    """Validate the explicit multi-trajectory production target dispatch.

    Historical target documents retain their single-manifest and single-frame
    semantics.  This format permits one exact accepted C manifest and one
    coordinate frame per trajectory without collapsing those identities.
    """

    from mineocclude.analysis.config import (
        DEFAULT_CONFIG_PATH,
        hash_core_analysis_config,
    )
    from mineocclude.analysis.coordinates import (
        CoordinateContractError,
        validate_coordinate_frame,
    )
    from mineocclude.analysis.manifests import (
        AnalysisArtifactError,
        validate_sealed_artifact,
    )

    try:
        validate_sealed_artifact(document, expected_type="oracle_target")
    except AnalysisArtifactError as error:
        raise OracleValidationError(
            f"Production oracle artifact is invalid: {error}"
        ) from error
    if document.get("schema_version") != SCHEMA_VERSION:
        raise OracleValidationError("Production oracle document schema mismatch.")
    if document.get("target_schema_version") != ORACLE_TARGET_SCHEMA_VERSION:
        raise OracleValidationError("Production oracle target version mismatch.")
    if document.get("join_key") != ["trajectory_id", "model_frame_idx"]:
        raise OracleValidationError("Production oracle join key is invalid.")
    if document.get("synthetic") is not False:
        raise OracleValidationError("Production oracle targets cannot be synthetic.")
    if document.get("scientific_use") != "permitted":
        raise OracleValidationError("Production oracle scientific use is not sealed.")
    if document.get("u4_output_inspected") is not False:
        raise OracleValidationError("Production oracle must not inspect U4 output.")

    rows = document.get("rows")
    if not isinstance(rows, list) or not rows:
        raise OracleValidationError("Production oracle requires target rows.")
    if rows != sorted(
        rows,
        key=lambda row: (row["trajectory_id"], row["model_frame_idx"]),
    ):
        raise OracleValidationError("Production oracle rows are not deterministic.")
    seen: set[tuple[str, int]] = set()
    for row in rows:
        validate_oracle_target(row)
        key = (row["trajectory_id"], row["model_frame_idx"])
        if key in seen:
            raise OracleValidationError(f"Duplicate production target key: {key}.")
        seen.add(key)
        required_lineage = (
            "accepted_c_manifest_sha256",
            "canonical_episode_manifest_sha256",
            "canonical_state_object_sha256",
            "c_frame_map_row_sha256",
            "c_frame_map_sha256",
            "c_state_row_sha256",
            "c_state_sha256",
            "condition_role",
            "fold_idx",
            "global_model_frame_idx",
            "source_frame_id",
            "source_frame_idx",
            "source_tick",
        )
        if any(field not in row for field in required_lineage):
            raise OracleValidationError(
                "Production target row is missing exact source lineage."
            )
        if (
            row["global_model_frame_idx"] != row["model_frame_idx"]
            or row["source_frame_idx"] != row["model_frame_idx"]
            or row["source_tick"] != row["server_tick"]
            or row["source_frame_id"]
            != f"{row['trajectory_id']}:render_frame:{row['model_frame_idx']}"
        ):
            raise OracleValidationError("Production target frame identity is not exact.")
        for field in required_lineage:
            if field.endswith("sha256") and not is_sha256(row[field]):
                raise OracleValidationError(
                    f"Production target lineage field {field} must be SHA-256."
                )
    for field in ("run_id", "code_sha", "config_hash", "model_hash", "preprocess_hash"):
        if len({row[field] for row in rows}) != 1:
            raise OracleValidationError(
                f"Production target table mixes {field} values."
            )
    bound_config_hash = hash_core_analysis_config(
        analysis_config_path or DEFAULT_CONFIG_PATH
    )
    if document.get("config_hash") != bound_config_hash or any(
        row["config_hash"] != bound_config_hash for row in rows
    ):
        raise OracleValidationError(
            "Production oracle is not bound to literal frozen config bytes."
        )

    pilot_ids = document.get("accepted_pilot_ids")
    lineage_rows = document.get("trajectory_lineage")
    coordinate_rows = document.get("coordinate_frames_by_trajectory")
    if (
        not isinstance(pilot_ids, list)
        or not pilot_ids
        or len(set(pilot_ids)) != len(pilot_ids)
        or not isinstance(lineage_rows, list)
        or not isinstance(coordinate_rows, list)
    ):
        raise OracleValidationError("Production trajectory authority is malformed.")
    expected_pilot_ids = [
        "layout_00_ep9403",
        "layout_00_ep9441",
        "layout_01_ep9405",
        "layout_01_ep9442",
        "layout_02_ep9407",
        "layout_02_ep9432",
        "layout_03_ep9404",
        "layout_03_ep9443",
        "layout_04_ep9406",
        "layout_04_ep9444",
    ]
    if pilot_ids != expected_pilot_ids:
        raise OracleValidationError("Production pilot order must be deterministic.")
    lineage_by_id = {
        row.get("trajectory_id"): row
        for row in lineage_rows
        if isinstance(row, Mapping)
    }
    coordinate_by_id = {
        row.get("trajectory_id"): row.get("coordinate_frame")
        for row in coordinate_rows
        if isinstance(row, Mapping)
    }
    if (
        len(lineage_rows) != len(pilot_ids)
        or len(coordinate_rows) != len(pilot_ids)
        or [row.get("trajectory_id") for row in lineage_rows] != pilot_ids
        or [row.get("trajectory_id") for row in coordinate_rows] != pilot_ids
        or set(lineage_by_id) != set(pilot_ids)
        or set(coordinate_by_id) != set(pilot_ids)
    ):
        raise OracleValidationError("Production trajectory authority is incomplete.")
    for coordinate in coordinate_by_id.values():
        try:
            validate_coordinate_frame(coordinate)
        except CoordinateContractError as error:
            raise OracleValidationError(
                f"Production coordinate frame is invalid: {error}"
            ) from error

    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["trajectory_id"]].append(row)
    if set(grouped) != set(pilot_ids):
        raise OracleValidationError("Production target pilot coverage is incomplete.")
    eligibility = document.get("eligibility_counts")
    if (
        document.get("row_count") != len(rows)
        or len(rows) != 1_695
        or eligibility
        != {
            "accepted_hidden_positive_spread_rows": 695,
            "accepted_post_first_seen_rows": 1_695,
            "visible_no_wall_control_rows": 1_000,
        }
    ):
        raise OracleValidationError("Production target row count does not reconcile.")

    expected_counts = {
        "by_fold": [
            {"fold_idx": key, "row_count": value}
            for key, value in sorted(Counter(row["fold_idx"] for row in rows).items())
        ],
        "by_layout": [
            {"layout_id": key, "row_count": value}
            for key, value in sorted(Counter(row["layout_id"] for row in rows).items())
        ],
        "by_pilot": [
            {"row_count": value, "trajectory_id": key}
            for key, value in sorted(
                Counter(row["trajectory_id"] for row in rows).items()
            )
        ],
        "by_visibility": [
            {"row_count": value, "visibility": key}
            for key, value in sorted(Counter(row["visibility"] for row in rows).items())
        ],
    }
    if document.get("target_counts") != expected_counts:
        raise OracleValidationError("Production target count audit is incomplete.")

    for trajectory_id in pilot_ids:
        trajectory_rows = grouped[trajectory_id]
        lineage = lineage_by_id[trajectory_id]
        ordered = sorted(trajectory_rows, key=lambda row: row["model_frame_idx"])
        if lineage.get("admitted_target_row_count") != len(ordered):
            raise OracleValidationError("Per-trajectory target count does not reconcile.")
        if len({row["accepted_manifest_hash"] for row in ordered}) != 1:
            raise OracleValidationError("Trajectory mixes canonical manifest identities.")
        expected_identity = {
            "accepted_manifest_hash": lineage.get(
                "canonical_episode_manifest_sha256"
            ),
            "accepted_c_manifest_sha256": lineage.get(
                "literal_capture_package_sha256"
            ),
            "canonical_episode_manifest_sha256": lineage.get(
                "canonical_episode_manifest_sha256"
            ),
            "canonical_state_object_sha256": lineage.get(
                "canonical_state_object_sha256"
            ),
            "layout_id": lineage.get("layout_id"),
            "fold_idx": lineage.get("fold_idx"),
            "condition_role": lineage.get("condition_role"),
        }
        if any(
            any(row.get(field) != value for field, value in expected_identity.items())
            for row in ordered
        ):
            raise OracleValidationError(
                "Production row identity crosses its trajectory authority."
            )
        if [row["model_frame_idx"] for row in ordered] != list(
            range(ordered[0]["model_frame_idx"], ordered[-1]["model_frame_idx"] + 1)
        ):
            raise OracleValidationError(
                "Production target membership must be frame-consecutive per pilot."
            )
        if lineage.get("condition_role") == "core_occluded":
            anchor = lineage.get("last_visible_anchor")
            if not isinstance(anchor, Mapping):
                raise OracleValidationError("Hidden production target lacks its anchor.")
            if (
                ordered[0]["model_frame_idx"] != anchor.get("model_frame_idx", -2) + 1
                or ordered[0]["server_tick"] != anchor.get("server_tick", -2) + 1
                or any(row["visibility"] != OCCLUDED for row in ordered)
            ):
                raise OracleValidationError("Hidden production anchor is not adjacent.")
            anchor_position = require_finite_number(
                "last_visible_anchor.position_blocks",
                anchor.get("position_blocks"),
            )
            interval_v = float(ordered[0]["v"])
            interval_q = float(ordered[0]["q"])
            for row in ordered:
                expected_tau = (
                    row["server_tick"] - anchor["server_tick"]
                ) * REGIME_A_DT_SECONDS
                if (
                    not math.isclose(
                        float(row["last_visible_position_blocks"]),
                        anchor_position,
                        rel_tol=0.0,
                        abs_tol=1e-10,
                    )
                    or float(row["v"]) != interval_v
                    or float(row["q"]) != interval_q
                    or not math.isclose(
                        float(row["tau"]),
                        expected_tau,
                        rel_tol=0.0,
                        abs_tol=1e-12,
                    )
                ):
                    raise OracleValidationError(
                        "Hidden production target changes its frozen interval."
                    )
        elif lineage.get("condition_role") == "no_wall_visible_control":
            if any(
                row["visibility"] != VISIBLE
                or float(row["tau"]) != 0.0
                or row["log_sigma_oracle"] is not None
                for row in ordered
            ):
                raise OracleValidationError("Visible-control target is not visible-only.")
            if lineage.get("last_visible_anchor") is not None:
                raise OracleValidationError("Visible controls cannot declare a hidden anchor.")
        else:
            raise OracleValidationError("Unknown production condition role.")

    distributions = document.get("target_distributions")
    if not isinstance(distributions, Mapping):
        raise OracleValidationError("Production target distributions are missing.")
    distribution_inputs = {
        "log_sigma_oracle": [
            float(row["log_sigma_oracle"])
            for row in rows
            if row["visibility"] == OCCLUDED
        ],
        "mu_oracle_blocks": [float(row["mu_oracle_blocks"]) for row in rows],
        "sigma_oracle_blocks": [float(row["sigma_oracle_blocks"]) for row in rows],
        "x_true_blocks": [float(row["x_true_blocks"]) for row in rows],
    }
    for target_name, values in distribution_inputs.items():
        declared = distributions.get(target_name)
        if not isinstance(declared, Mapping) or declared.get("count") != len(values):
            raise OracleValidationError("Production target distribution is malformed.")
        expected_values = {
            "maximum": max(values),
            "mean": sum(values) / len(values),
            "minimum": min(values),
        }
        if any(
            not isinstance(declared.get(name), (int, float))
            or isinstance(declared.get(name), bool)
            or not math.isclose(
                float(declared[name]),
                value,
                rel_tol=0.0,
                abs_tol=1e-9,
            )
            for name, value in expected_values.items()
        ):
            raise OracleValidationError("Production target distribution is stale.")
