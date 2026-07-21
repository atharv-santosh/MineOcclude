"""Universal identity contract for claim-bearing MineOcclude artifacts.

This module defines only shared identity, provenance, lifecycle, and
cross-table joining rules.

Role-specific contracts such as capture, activation, intervention,
and rollout schemas are defined in later Phase 1 steps.
"""

from __future__ import annotations

import math
from enum import Enum
from typing import Any, Iterable, Mapping, Sequence


# This remains a draft until the cross-role sign-off in Phase 1, Step 1.8.
SCHEMA_VERSION = "0.1-draft"

# Shared frame-level identity used across model-analysis tables.
FRAME_KEY = (
    "trajectory_id",
    "model_frame_idx",
)

# Full Git commit SHA.
CODE_SHA_LENGTH = 40

# SHA-256 content hashes.
SHA256_LENGTH = 64

SHA256_FIELDS = (
    "config_hash",
    "model_hash",
    "preprocess_hash",
)

# Condition fields currently represented as scalar numeric values.
# Exact units and final scientific ranges are frozen with the relevant
# interface owners before schema v1.0 sign-off in Step 1.8.
NUMERIC_CONDITION_FIELDS = (
    "tau",
    "v",
    "q",
    "duration",
)


class ArtifactStatus(str, Enum):
    """Allowed lifecycle states for claim-bearing artifacts."""

    ACCEPTED = "accepted"
    EXCLUDED = "excluded"
    SUPERSEDED = "superseded"


class IdentityValidationError(ValueError):
    """Raised when universal identity rules are violated."""


# These fields must exist on every claim-bearing identity row.
REQUIRED_FIELDS = (
    # Original recording identity
    "episode_id",
    "trajectory_id",
    "server_tick",
    "render_frame_idx",
    "action_idx",
    "model_frame_idx",

    # Experimental-condition identity
    "layout_id",
    "regime",
    "visibility",
    "tau",
    "v",
    "q",
    "duration",

    # Reproducibility and provenance
    "code_sha",
    "config_hash",
    "model_hash",
    "preprocess_hash",
    "seed",
    "schema_version",
    "run_id",

    # Lifecycle
    "status",
    "exclusion_reason",
    "superseded_by",
)


NON_EMPTY_STRING_FIELDS = (
    "episode_id",
    "trajectory_id",
    "layout_id",
    "regime",
    "visibility",
    "code_sha",
    "config_hash",
    "model_hash",
    "preprocess_hash",
    "schema_version",
    "run_id",
)


NON_NEGATIVE_INTEGER_FIELDS = (
    "server_tick",
    "render_frame_idx",
    "action_idx",
    "model_frame_idx",
)


def _is_hex_string(value: Any, length: int) -> bool:
    """Return True when value is a hexadecimal string of exact length."""

    if not isinstance(value, str) or len(value) != length:
        return False

    try:
        int(value, 16)
    except ValueError:
        return False

    return True


def validate_identity(row: Mapping[str, Any]) -> None:
    """Validate one row against the universal identity contract."""

    # Every universal field must exist.
    missing_fields = [
        field
        for field in REQUIRED_FIELDS
        if field not in row
    ]

    if missing_fields:
        raise IdentityValidationError(
            "Missing required fields: "
            + ", ".join(missing_fields)
        )

    # Required string identifiers and provenance values cannot be blank.
    for field in NON_EMPTY_STRING_FIELDS:
        value = row[field]

        if not isinstance(value, str) or not value.strip():
            raise IdentityValidationError(
                f"{field} must be a non-empty string."
            )

    # Source/model index fields must be non-negative integers.
    for field in NON_NEGATIVE_INTEGER_FIELDS:
        value = row[field]

        if (
            not isinstance(value, int)
            or isinstance(value, bool)
            or value < 0
        ):
            raise IdentityValidationError(
                f"{field} must be a non-negative integer."
            )

    # The random seed must always be explicitly recorded as an integer.
    if (
        not isinstance(row["seed"], int)
        or isinstance(row["seed"], bool)
    ):
        raise IdentityValidationError(
            "seed must be an integer."
        )

    # Shared numeric condition fields must be non-null, numeric, and finite.
    for field in NUMERIC_CONDITION_FIELDS:
        value = row[field]

        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
        ):
            raise IdentityValidationError(
                f"{field} must be a numeric value."
            )

        if not math.isfinite(float(value)):
            raise IdentityValidationError(
                f"{field} must be finite."
            )

    # Time-like quantities cannot be negative.
    if row["tau"] < 0:
        raise IdentityValidationError(
            "tau cannot be negative."
        )

    if row["duration"] < 0:
        raise IdentityValidationError(
            "duration cannot be negative."
        )

    # Prevent accidental mixing of incompatible schema versions.
    if row["schema_version"] != SCHEMA_VERSION:
        raise IdentityValidationError(
            f"Expected schema version {SCHEMA_VERSION!r}, "
            f"got {row['schema_version']!r}."
        )

    # Validate the Git revision format.
    if not _is_hex_string(
        row["code_sha"],
        CODE_SHA_LENGTH,
    ):
        raise IdentityValidationError(
            "code_sha must be a 40-character hexadecimal Git SHA."
        )

    # Validate content hashes.
    for field in SHA256_FIELDS:
        if not _is_hex_string(
            row[field],
            SHA256_LENGTH,
        ):
            raise IdentityValidationError(
                f"{field} must be a 64-character "
                "hexadecimal SHA-256 value."
            )

    # Validate lifecycle status.
    try:
        status = ArtifactStatus(
            row["status"]
        )

    except ValueError as error:
        allowed = ", ".join(
            item.value
            for item in ArtifactStatus
        )

        raise IdentityValidationError(
            f"Invalid status. Allowed values: {allowed}."
        ) from error

    exclusion_reason = row["exclusion_reason"]
    superseded_by = row["superseded_by"]

    # Accepted rows are currently valid and usable.
    if status is ArtifactStatus.ACCEPTED:
        if exclusion_reason is not None:
            raise IdentityValidationError(
                "Accepted rows cannot have exclusion_reason."
            )

        if superseded_by is not None:
            raise IdentityValidationError(
                "Accepted rows cannot have superseded_by."
            )

    # Excluded rows remain preserved but require a reason.
    elif status is ArtifactStatus.EXCLUDED:
        if (
            not isinstance(exclusion_reason, str)
            or not exclusion_reason.strip()
        ):
            raise IdentityValidationError(
                "Excluded rows require a non-empty "
                "exclusion_reason."
            )

        if superseded_by is not None:
            raise IdentityValidationError(
                "Excluded rows cannot have superseded_by."
            )

    # Superseded rows remain preserved and point to their replacement.
    elif status is ArtifactStatus.SUPERSEDED:
        if exclusion_reason is not None:
            raise IdentityValidationError(
                "Superseded rows cannot have exclusion_reason."
            )

        if (
            not isinstance(superseded_by, str)
            or not superseded_by.strip()
        ):
            raise IdentityValidationError(
                "Superseded rows require a non-empty "
                "superseded_by value."
            )


def get_key(
    row: Mapping[str, Any],
    key_fields: Sequence[str] = FRAME_KEY,
) -> tuple[Any, ...]:
    """Return an explicit identity key for a row."""

    try:
        return tuple(
            row[field]
            for field in key_fields
        )

    except KeyError as error:
        raise IdentityValidationError(
            f"Missing key field: {error.args[0]!r}."
        ) from error


def assert_unique(
    rows: Iterable[Mapping[str, Any]],
    key_fields: Sequence[str] = FRAME_KEY,
) -> None:
    """Require each requested identity key to occur only once."""

    seen: set[tuple[Any, ...]] = set()

    for row in rows:
        key = get_key(
            row,
            key_fields,
        )

        if key in seen:
            raise IdentityValidationError(
                f"Duplicate key {key} for fields "
                f"{tuple(key_fields)}."
            )

        seen.add(key)


def assert_trajectory_consistency(
    rows: Iterable[Mapping[str, Any]],
) -> None:
    """Require trajectory-level identity to remain internally consistent."""

    expected_by_trajectory: dict[
        str,
        tuple[Any, ...],
    ] = {}

    # These values must remain constant within one trajectory.
    # Frame-level fields such as visibility and tau are intentionally
    # excluded because they may change over time.
    constant_fields = (
        "episode_id",
        "layout_id",
        "seed",
    )

    for row in rows:
        trajectory_id = row["trajectory_id"]

        values = tuple(
            row[field]
            for field in constant_fields
        )

        existing = expected_by_trajectory.get(
            trajectory_id
        )

        if existing is None:
            expected_by_trajectory[
                trajectory_id
            ] = values

        elif existing != values:
            raise IdentityValidationError(
                f"Trajectory {trajectory_id!r} contains "
                "inconsistent trajectory-level identity."
            )


def assert_same_key_set(
    reference_rows: Iterable[Mapping[str, Any]],
    other_rows: Iterable[Mapping[str, Any]],
    key_fields: Sequence[str] = FRAME_KEY,
) -> None:
    """Require two tables to contain exactly the same unique keys."""

    reference_rows = list(
        reference_rows
    )

    other_rows = list(
        other_rows
    )

    assert_unique(
        reference_rows,
        key_fields,
    )

    assert_unique(
        other_rows,
        key_fields,
    )

    reference_keys = {
        get_key(row, key_fields)
        for row in reference_rows
    }

    other_keys = {
        get_key(row, key_fields)
        for row in other_rows
    }

    if reference_keys != other_keys:
        missing = reference_keys - other_keys
        extra = other_keys - reference_keys

        raise IdentityValidationError(
            "Table identity mismatch. "
            f"Missing keys: {sorted(missing)}. "
            f"Extra keys: {sorted(extra)}."
        )