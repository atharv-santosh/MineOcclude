"""B→A intervention-request contract for MineOcclude.

Person B produces a scientifically specified intervention request.
Person A validates the request before any intervention reaches generation.

The validator never repairs or silently converts invalid requests.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any

from mineocclude.contracts.identity import SCHEMA_VERSION


INTERVENTION_SCHEMA_VERSION = SCHEMA_VERSION

EXPECTED_DIRECTION_DIMENSION = 2048
MINEWORLD_LAYER_COUNT = 20
MINEWORLD_MODEL_FRAME_COUNT = 16

UNIT_NORM_REL_TOLERANCE = 1e-5
UNIT_NORM_ABS_TOLERANCE = 1e-6


class InterventionRejectionCode(str, Enum):
    """Machine-readable B→A intervention-request rejection reasons."""

    MISSING_REQUIRED_FIELD = "missing_required_field"
    INVALID_SCHEMA_VERSION = "invalid_schema_version"

    INVALID_DIRECTION = "invalid_direction"
    DIRECTION_NOT_RAW_SPACE = "direction_not_raw_space"
    DIRECTION_NOT_UNIT_NORM = "direction_not_unit_norm"
    NEAR_ZERO_RESIDUAL_DIRECTION = "near_zero_residual_direction"

    INVALID_INTERVENTION_LOCATION = "invalid_intervention_location"

    INVALID_ALPHA_TABLE = "invalid_alpha_table"
    INVALID_CAP = "invalid_cap"
    CAP_REDUCTION_MISMATCH = "cap_reduction_mismatch"
    ALPHA_EXCEEDS_CAP = "alpha_exceeds_cap"
    ALPHA_SIGN_REVERSAL = "alpha_sign_reversal"

    INVALID_DIRECTION_METADATA = "invalid_direction_metadata"
    INVALID_SCALER_METADATA = "invalid_scaler_metadata"
    RAW_SPACE_EQUIVALENCE_UNVERIFIED = (
        "raw_space_equivalence_unverified"
    )

    INVALID_SELECTION_POLICY = "invalid_selection_policy"
    TEST_SELECTED_DIRECTION = "test_selected_direction"

    INVALID_MANIFEST = "invalid_manifest"
    DATA_SPLIT_OVERLAP = "data_split_overlap"
    INVALID_HELDOUT_EVENTS = "invalid_heldout_events"

    INVALID_VALIDATION_FLAGS = "invalid_validation_flags"


@dataclass(frozen=True)
class InterventionRejection:
    """One machine-readable intervention-request rejection."""

    code: InterventionRejectionCode
    message: str


@dataclass(frozen=True)
class InterventionValidationResult:
    """Result returned by intervention-request validation."""

    accepted: bool
    rejections: tuple[InterventionRejection, ...]


def _add_rejection(
    rejections: list[InterventionRejection],
    code: InterventionRejectionCode,
    message: str,
) -> None:
    """Append one rejection record."""

    rejections.append(
        InterventionRejection(
            code=code,
            message=message,
        )
    )


def _missing_fields(
    value: Mapping[str, Any],
    required_fields: tuple[str, ...],
) -> list[str]:
    """Return required fields missing from a mapping."""

    return [
        field
        for field in required_fields
        if field not in value
    ]


def _is_finite_number(
    value: Any,
) -> bool:
    """Return True for finite numeric values that are not booleans."""

    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _is_non_negative_integer(
    value: Any,
) -> bool:
    """Return True for non-negative integers that are not booleans."""

    return (
        isinstance(value, int)
        and not isinstance(value, bool)
        and value >= 0
    )


def _is_sha256(
    value: Any,
) -> bool:
    """Return True for a 64-character hexadecimal SHA-256 value."""

    if (
        not isinstance(value, str)
        or len(value) != 64
    ):
        return False

    try:
        int(value, 16)

    except ValueError:
        return False

    return True


def _l2_norm(
    values: list[float],
) -> float:
    """Compute the Euclidean norm without overflow exceptions."""

    norm = 0.0

    for value in values:
        norm = math.hypot(
            norm,
            float(value),
        )

    return norm


def _validate_manifest(
    manifest_name: str,
    manifest: Any,
    rejections: list[InterventionRejection],
) -> set[str]:
    """Validate one fit/validation manifest and return its event IDs."""

    if not isinstance(
        manifest,
        Mapping,
    ):
        _add_rejection(
            rejections,
            InterventionRejectionCode.INVALID_MANIFEST,
            f"{manifest_name} must be a mapping.",
        )
        return set()

    required_fields = (
        "manifest_id",
        "manifest_hash",
        "event_ids",
    )

    missing = _missing_fields(
        manifest,
        required_fields,
    )

    if missing:
        _add_rejection(
            rejections,
            InterventionRejectionCode.INVALID_MANIFEST,
            (
                f"{manifest_name} is missing: "
                + ", ".join(missing)
            ),
        )
        return set()

    if (
        not isinstance(
            manifest["manifest_id"],
            str,
        )
        or not manifest[
            "manifest_id"
        ].strip()
    ):
        _add_rejection(
            rejections,
            InterventionRejectionCode.INVALID_MANIFEST,
            (
                f"{manifest_name}.manifest_id "
                "must be a non-empty string."
            ),
        )

    if not _is_sha256(
        manifest["manifest_hash"]
    ):
        _add_rejection(
            rejections,
            InterventionRejectionCode.INVALID_MANIFEST,
            (
                f"{manifest_name}.manifest_hash "
                "must be a valid SHA-256 value."
            ),
        )

    event_ids = manifest[
        "event_ids"
    ]

    if (
        not isinstance(event_ids, list)
        or not event_ids
        or not all(
            isinstance(event_id, str)
            and event_id.strip()
            for event_id in event_ids
        )
    ):
        _add_rejection(
            rejections,
            InterventionRejectionCode.INVALID_MANIFEST,
            (
                f"{manifest_name}.event_ids must be "
                "a non-empty list of non-empty strings."
            ),
        )
        return set()

    if len(event_ids) != len(
        set(event_ids)
    ):
        _add_rejection(
            rejections,
            InterventionRejectionCode.INVALID_MANIFEST,
            (
                f"{manifest_name}.event_ids "
                "contains duplicates."
            ),
        )

    return set(event_ids)


def validate_intervention_request(
    request: Mapping[str, Any],
) -> InterventionValidationResult:
    """Validate one Person B → Person A intervention request."""

    rejections: list[
        InterventionRejection
    ] = []

    if not isinstance(
        request,
        Mapping,
    ):
        _add_rejection(
            rejections,
            InterventionRejectionCode.MISSING_REQUIRED_FIELD,
            "Intervention request must be a mapping.",
        )

        return InterventionValidationResult(
            accepted=False,
            rejections=tuple(rejections),
        )

    required_top_level = (
        "schema_version",
        "request_id",
        "direction",
        "intervention_location",
        "alpha_table",
        "cap",
        "direction_metadata",
        "scaler_metadata",
        "selection_policy",
        "fit_manifest",
        "validation_manifest",
        "heldout_events",
        "validation_flags",
    )

    missing = _missing_fields(
        request,
        required_top_level,
    )

    if missing:
        _add_rejection(
            rejections,
            InterventionRejectionCode.MISSING_REQUIRED_FIELD,
            (
                "Missing top-level fields: "
                + ", ".join(missing)
            ),
        )

        return InterventionValidationResult(
            accepted=False,
            rejections=tuple(rejections),
        )

    # --------------------------------------------------------------
    # Schema and request identity
    # --------------------------------------------------------------

    if (
        request["schema_version"]
        != INTERVENTION_SCHEMA_VERSION
    ):
        _add_rejection(
            rejections,
            InterventionRejectionCode.INVALID_SCHEMA_VERSION,
            (
                "Expected intervention schema version "
                f"{INTERVENTION_SCHEMA_VERSION!r}."
            ),
        )

    if (
        not isinstance(
            request["request_id"],
            str,
        )
        or not request[
            "request_id"
        ].strip()
    ):
        _add_rejection(
            rejections,
            InterventionRejectionCode.MISSING_REQUIRED_FIELD,
            "request_id must be a non-empty string.",
        )

    # --------------------------------------------------------------
    # Raw-space unit direction
    # --------------------------------------------------------------

    direction = request[
        "direction"
    ]

    if not isinstance(
        direction,
        Mapping,
    ):
        _add_rejection(
            rejections,
            InterventionRejectionCode.INVALID_DIRECTION,
            "direction must be a mapping.",
        )

    else:
        required = (
            "space",
            "values",
            "dimension",
        )

        missing = _missing_fields(
            direction,
            required,
        )

        if missing:
            _add_rejection(
                rejections,
                InterventionRejectionCode.INVALID_DIRECTION,
                (
                    "direction is missing: "
                    + ", ".join(missing)
                ),
            )

        else:
            if (
                direction["space"]
                != "raw_activation"
            ):
                _add_rejection(
                    rejections,
                    InterventionRejectionCode.DIRECTION_NOT_RAW_SPACE,
                    (
                        "Intervention directions must already "
                        "be expressed in raw activation space."
                    ),
                )

            if (
                direction["dimension"]
                != EXPECTED_DIRECTION_DIMENSION
            ):
                _add_rejection(
                    rejections,
                    InterventionRejectionCode.INVALID_DIRECTION,
                    (
                        "direction.dimension must equal "
                        f"{EXPECTED_DIRECTION_DIMENSION}."
                    ),
                )

            values = direction[
                "values"
            ]

            if (
                not isinstance(values, list)
                or len(values)
                != EXPECTED_DIRECTION_DIMENSION
                or not all(
                    _is_finite_number(value)
                    for value in values
                )
            ):
                _add_rejection(
                    rejections,
                    InterventionRejectionCode.INVALID_DIRECTION,
                    (
                        "direction.values must contain exactly "
                        f"{EXPECTED_DIRECTION_DIMENSION} "
                        "finite numeric values."
                    ),
                )

            else:
                norm = _l2_norm(
                    values
                )

                if not math.isfinite(
                    norm
                ):
                    _add_rejection(
                        rejections,
                        InterventionRejectionCode.INVALID_DIRECTION,
                        (
                            "direction.values produce a "
                            "non-finite L2 norm."
                        ),
                    )

                elif not math.isclose(
                    norm,
                    1.0,
                    rel_tol=UNIT_NORM_REL_TOLERANCE,
                    abs_tol=UNIT_NORM_ABS_TOLERANCE,
                ):
                    _add_rejection(
                        rejections,
                        InterventionRejectionCode.DIRECTION_NOT_UNIT_NORM,
                        (
                            "The raw-space intervention direction "
                            "must have L2 norm 1."
                        ),
                    )

    # --------------------------------------------------------------
    # Exact intervention location
    # --------------------------------------------------------------

    location = request[
        "intervention_location"
    ]

    if not isinstance(
        location,
        Mapping,
    ):
        _add_rejection(
            rejections,
            InterventionRejectionCode.INVALID_INTERVENTION_LOCATION,
            "intervention_location must be a mapping.",
        )

    else:
        required = (
            "layer_idx",
            "hook_site",
            "timestep_idx",
        )

        missing = _missing_fields(
            location,
            required,
        )

        if missing:
            _add_rejection(
                rejections,
                InterventionRejectionCode.INVALID_INTERVENTION_LOCATION,
                (
                    "intervention_location is missing: "
                    + ", ".join(missing)
                ),
            )

        else:
            layer_idx = location[
                "layer_idx"
            ]

            timestep_idx = location[
                "timestep_idx"
            ]

            hook_site = location[
                "hook_site"
            ]

            if (
                not _is_non_negative_integer(
                    layer_idx
                )
                or layer_idx
                >= MINEWORLD_LAYER_COUNT
            ):
                _add_rejection(
                    rejections,
                    InterventionRejectionCode.INVALID_INTERVENTION_LOCATION,
                    (
                        "layer_idx must identify one of "
                        f"{MINEWORLD_LAYER_COUNT} MineWorld layers."
                    ),
                )

            if (
                not _is_non_negative_integer(
                    timestep_idx
                )
                or timestep_idx
                >= MINEWORLD_MODEL_FRAME_COUNT
            ):
                _add_rejection(
                    rejections,
                    InterventionRejectionCode.INVALID_INTERVENTION_LOCATION,
                    (
                        "timestep_idx must fall within the "
                        "16-frame model context."
                    ),
                )

            if (
                not isinstance(
                    hook_site,
                    str,
                )
                or not hook_site.strip()
            ):
                _add_rejection(
                    rejections,
                    InterventionRejectionCode.INVALID_INTERVENTION_LOCATION,
                    "hook_site must be a non-empty string.",
                )

    # --------------------------------------------------------------
    # Direction metadata
    # --------------------------------------------------------------

    direction_metadata = request[
        "direction_metadata"
    ]

    if not isinstance(
        direction_metadata,
        Mapping,
    ):
        _add_rejection(
            rejections,
            InterventionRejectionCode.INVALID_DIRECTION_METADATA,
            "direction_metadata must be a mapping.",
        )

    else:
        required = (
            "direction_version",
            "direction_hash",
            "source_run_id",
            "residual_norm_before_normalization",
            "near_zero_threshold",
        )

        missing = _missing_fields(
            direction_metadata,
            required,
        )

        if missing:
            _add_rejection(
                rejections,
                InterventionRejectionCode.INVALID_DIRECTION_METADATA,
                (
                    "direction_metadata is missing: "
                    + ", ".join(missing)
                ),
            )

        else:
            for field in (
                "direction_version",
                "source_run_id",
            ):
                if (
                    not isinstance(
                        direction_metadata[field],
                        str,
                    )
                    or not direction_metadata[
                        field
                    ].strip()
                ):
                    _add_rejection(
                        rejections,
                        InterventionRejectionCode.INVALID_DIRECTION_METADATA,
                        (
                            f"direction_metadata.{field} "
                            "must be a non-empty string."
                        ),
                    )

            if not _is_sha256(
                direction_metadata[
                    "direction_hash"
                ]
            ):
                _add_rejection(
                    rejections,
                    InterventionRejectionCode.INVALID_DIRECTION_METADATA,
                    (
                        "direction_metadata.direction_hash "
                        "must be a valid SHA-256 value."
                    ),
                )

            residual_norm = direction_metadata[
                "residual_norm_before_normalization"
            ]

            near_zero_threshold = direction_metadata[
                "near_zero_threshold"
            ]

            if (
                not _is_finite_number(
                    residual_norm
                )
                or residual_norm < 0
                or not _is_finite_number(
                    near_zero_threshold
                )
                or near_zero_threshold <= 0
            ):
                _add_rejection(
                    rejections,
                    InterventionRejectionCode.INVALID_DIRECTION_METADATA,
                    (
                        "Residual norm and near-zero threshold "
                        "must be valid finite values."
                    ),
                )

            elif (
                residual_norm
                <= near_zero_threshold
            ):
                _add_rejection(
                    rejections,
                    InterventionRejectionCode.NEAR_ZERO_RESIDUAL_DIRECTION,
                    (
                        "The pre-normalization residual direction "
                        "is zero or near zero."
                    ),
                )

    # --------------------------------------------------------------
    # Scaler metadata
    # --------------------------------------------------------------

    scaler_metadata = request[
        "scaler_metadata"
    ]

    if not isinstance(
        scaler_metadata,
        Mapping,
    ):
        _add_rejection(
            rejections,
            InterventionRejectionCode.INVALID_SCALER_METADATA,
            "scaler_metadata must be a mapping.",
        )

    else:
        required = (
            "used_during_fit",
            "scaler_id",
            "scaler_hash",
            "inverse_transformed_before_export",
        )

        missing = _missing_fields(
            scaler_metadata,
            required,
        )

        if missing:
            _add_rejection(
                rejections,
                InterventionRejectionCode.INVALID_SCALER_METADATA,
                (
                    "scaler_metadata is missing: "
                    + ", ".join(missing)
                ),
            )

        else:
            used_during_fit = scaler_metadata[
                "used_during_fit"
            ]

            inverse_transformed = scaler_metadata[
                "inverse_transformed_before_export"
            ]

            if not isinstance(
                used_during_fit,
                bool,
            ):
                _add_rejection(
                    rejections,
                    InterventionRejectionCode.INVALID_SCALER_METADATA,
                    "used_during_fit must be boolean.",
                )

            if not isinstance(
                inverse_transformed,
                bool,
            ):
                _add_rejection(
                    rejections,
                    InterventionRejectionCode.INVALID_SCALER_METADATA,
                    (
                        "inverse_transformed_before_export "
                        "must be boolean."
                    ),
                )

            if used_during_fit is True:
                if (
                    not isinstance(
                        scaler_metadata[
                            "scaler_id"
                        ],
                        str,
                    )
                    or not scaler_metadata[
                        "scaler_id"
                    ].strip()
                    or not _is_sha256(
                        scaler_metadata[
                            "scaler_hash"
                        ]
                    )
                ):
                    _add_rejection(
                        rejections,
                        InterventionRejectionCode.INVALID_SCALER_METADATA,
                        (
                            "A fitted scaler requires a scaler ID "
                            "and valid SHA-256 identity."
                        ),
                    )

                if (
                    inverse_transformed
                    is not True
                ):
                    _add_rejection(
                        rejections,
                        InterventionRejectionCode.RAW_SPACE_EQUIVALENCE_UNVERIFIED,
                        (
                            "Standardized fit-space directions "
                            "must be converted to raw activation "
                            "space before export."
                        ),
                    )

    # --------------------------------------------------------------
    # Direction-selection policy
    # --------------------------------------------------------------

    selection_policy = request[
        "selection_policy"
    ]

    if not isinstance(
        selection_policy,
        Mapping,
    ):
        _add_rejection(
            rejections,
            InterventionRejectionCode.INVALID_SELECTION_POLICY,
            "selection_policy must be a mapping.",
        )

    else:
        required = (
            "used_test_data_to_select_direction",
            "used_heldout_outcomes_to_select_direction",
            "description",
        )

        missing = _missing_fields(
            selection_policy,
            required,
        )

        if missing:
            _add_rejection(
                rejections,
                InterventionRejectionCode.INVALID_SELECTION_POLICY,
                (
                    "selection_policy is missing: "
                    + ", ".join(missing)
                ),
            )

        else:
            test_selected = selection_policy[
                "used_test_data_to_select_direction"
            ]

            heldout_selected = selection_policy[
                "used_heldout_outcomes_to_select_direction"
            ]

            if (
                not isinstance(
                    test_selected,
                    bool,
                )
                or not isinstance(
                    heldout_selected,
                    bool,
                )
            ):
                _add_rejection(
                    rejections,
                    InterventionRejectionCode.INVALID_SELECTION_POLICY,
                    (
                        "Direction-selection audit flags "
                        "must be boolean."
                    ),
                )

            elif (
                test_selected
                or heldout_selected
            ):
                _add_rejection(
                    rejections,
                    InterventionRejectionCode.TEST_SELECTED_DIRECTION,
                    (
                        "Test data or held-out outcomes cannot "
                        "select the intervention direction."
                    ),
                )

            if (
                not isinstance(
                    selection_policy[
                        "description"
                    ],
                    str,
                )
                or not selection_policy[
                    "description"
                ].strip()
            ):
                _add_rejection(
                    rejections,
                    InterventionRejectionCode.INVALID_SELECTION_POLICY,
                    (
                        "selection_policy.description "
                        "must be a non-empty string."
                    ),
                )

    # --------------------------------------------------------------
    # Fit, validation, and held-out identities
    # --------------------------------------------------------------

    fit_event_ids = _validate_manifest(
        "fit_manifest",
        request[
            "fit_manifest"
        ],
        rejections,
    )

    validation_event_ids = _validate_manifest(
        "validation_manifest",
        request[
            "validation_manifest"
        ],
        rejections,
    )

    heldout_events = request[
        "heldout_events"
    ]

    heldout_event_ids: set[str] = set()

    if (
        not isinstance(
            heldout_events,
            list,
        )
        or not heldout_events
    ):
        _add_rejection(
            rejections,
            InterventionRejectionCode.INVALID_HELDOUT_EVENTS,
            "heldout_events must be a non-empty list.",
        )

    else:
        for event_index, event in enumerate(
            heldout_events
        ):
            if not isinstance(
                event,
                Mapping,
            ):
                _add_rejection(
                    rejections,
                    InterventionRejectionCode.INVALID_HELDOUT_EVENTS,
                    (
                        f"heldout_events[{event_index}] "
                        "must be a mapping."
                    ),
                )
                continue

            required = (
                "event_id",
                "trajectory_id",
                "layout_id",
            )

            missing = _missing_fields(
                event,
                required,
            )

            if missing:
                _add_rejection(
                    rejections,
                    InterventionRejectionCode.INVALID_HELDOUT_EVENTS,
                    (
                        f"heldout_events[{event_index}] is missing: "
                        + ", ".join(missing)
                    ),
                )
                continue

            for field in required:
                if (
                    not isinstance(
                        event[field],
                        str,
                    )
                    or not event[
                        field
                    ].strip()
                ):
                    _add_rejection(
                        rejections,
                        InterventionRejectionCode.INVALID_HELDOUT_EVENTS,
                        (
                            f"heldout_events[{event_index}].{field} "
                            "must be a non-empty string."
                        ),
                    )

            event_id = event[
                "event_id"
            ]

            if isinstance(
                event_id,
                str,
            ):
                if (
                    event_id
                    in heldout_event_ids
                ):
                    _add_rejection(
                        rejections,
                        InterventionRejectionCode.INVALID_HELDOUT_EVENTS,
                        (
                            "heldout_events contains duplicate "
                            f"event ID {event_id!r}."
                        ),
                    )

                heldout_event_ids.add(
                    event_id
                )

    if (
        fit_event_ids
        & validation_event_ids
        or fit_event_ids
        & heldout_event_ids
        or validation_event_ids
        & heldout_event_ids
    ):
        _add_rejection(
            rejections,
            InterventionRejectionCode.DATA_SPLIT_OVERLAP,
            (
                "Fit, validation, and held-out event "
                "identities must be disjoint."
            ),
        )

    # --------------------------------------------------------------
    # Alpha table
    # --------------------------------------------------------------

    alpha_table = request[
        "alpha_table"
    ]

    has_cap_reduced_doses = False

    if (
        not isinstance(
            alpha_table,
            list,
        )
        or not alpha_table
    ):
        _add_rejection(
            rejections,
            InterventionRejectionCode.INVALID_ALPHA_TABLE,
            "alpha_table must be a non-empty list.",
        )

    else:
        seen_dose_ids: set[str] = set()

        for dose_index, dose in enumerate(
            alpha_table
        ):
            if not isinstance(
                dose,
                Mapping,
            ):
                _add_rejection(
                    rejections,
                    InterventionRejectionCode.INVALID_ALPHA_TABLE,
                    (
                        f"alpha_table[{dose_index}] "
                        "must be a mapping."
                    ),
                )
                continue

            required = (
                "dose_id",
                "alpha_requested",
                "alpha_applied",
                "intended_block_shift",
                "cap_reduced",
            )

            missing = _missing_fields(
                dose,
                required,
            )

            if missing:
                _add_rejection(
                    rejections,
                    InterventionRejectionCode.INVALID_ALPHA_TABLE,
                    (
                        f"alpha_table[{dose_index}] is missing: "
                        + ", ".join(missing)
                    ),
                )
                continue

            dose_id = dose[
                "dose_id"
            ]

            if (
                not isinstance(
                    dose_id,
                    str,
                )
                or not dose_id.strip()
            ):
                _add_rejection(
                    rejections,
                    InterventionRejectionCode.INVALID_ALPHA_TABLE,
                    (
                        f"alpha_table[{dose_index}].dose_id "
                        "must be a non-empty string."
                    ),
                )

            elif dose_id in seen_dose_ids:
                _add_rejection(
                    rejections,
                    InterventionRejectionCode.INVALID_ALPHA_TABLE,
                    (
                        f"Duplicate dose ID: "
                        f"{dose_id!r}."
                    ),
                )

            else:
                seen_dose_ids.add(
                    dose_id
                )

            numeric_fields_valid = True

            for field in (
                "alpha_requested",
                "alpha_applied",
                "intended_block_shift",
            ):
                if not _is_finite_number(
                    dose[field]
                ):
                    numeric_fields_valid = False

                    _add_rejection(
                        rejections,
                        InterventionRejectionCode.INVALID_ALPHA_TABLE,
                        (
                            f"alpha_table[{dose_index}].{field} "
                            "must be finite numeric."
                        ),
                    )

            cap_reduced = dose[
                "cap_reduced"
            ]

            if not isinstance(
                cap_reduced,
                bool,
            ):
                _add_rejection(
                    rejections,
                    InterventionRejectionCode.INVALID_ALPHA_TABLE,
                    (
                        f"alpha_table[{dose_index}].cap_reduced "
                        "must be boolean."
                    ),
                )

                continue

            if not numeric_fields_valid:
                continue

            requested = float(
                dose[
                    "alpha_requested"
                ]
            )

            applied = float(
                dose[
                    "alpha_applied"
                ]
            )

            if cap_reduced:
                has_cap_reduced_doses = True

                if (
                    abs(applied)
                    >= abs(requested)
                ):
                    _add_rejection(
                        rejections,
                        InterventionRejectionCode.CAP_REDUCTION_MISMATCH,
                        (
                            "A dose marked cap_reduced must have "
                            "a smaller applied alpha magnitude "
                            "than its requested alpha."
                        ),
                    )

            elif not math.isclose(
                requested,
                applied,
                rel_tol=1e-12,
                abs_tol=1e-12,
            ):
                _add_rejection(
                    rejections,
                    InterventionRejectionCode.CAP_REDUCTION_MISMATCH,
                    (
                        "A dose with cap_reduced=false must have "
                        "alpha_requested equal to alpha_applied."
                    ),
                )

    # --------------------------------------------------------------
    # Cap specification
    # --------------------------------------------------------------

    cap = request[
        "cap"
    ]

    cap_is_valid = False
    maximum_applied_alpha: float | None = None

    if not isinstance(
        cap,
        Mapping,
    ):
        _add_rejection(
            rejections,
            InterventionRejectionCode.INVALID_CAP,
            "cap must be a mapping.",
        )

    else:
        required = (
            "max_relative_activation_norm",
            "typical_activation_norm",
        )

        missing = _missing_fields(
            cap,
            required,
        )

        if missing:
            _add_rejection(
                rejections,
                InterventionRejectionCode.INVALID_CAP,
                (
                    "cap is missing: "
                    + ", ".join(missing)
                ),
            )

        else:
            max_relative_norm = cap[
                "max_relative_activation_norm"
            ]

            typical_norm = cap[
                "typical_activation_norm"
            ]

            if (
                not _is_finite_number(
                    max_relative_norm
                )
                or max_relative_norm <= 0
            ):
                _add_rejection(
                    rejections,
                    InterventionRejectionCode.INVALID_CAP,
                    (
                        "max_relative_activation_norm "
                        "must be positive and finite."
                    ),
                )

            elif (
                not _is_finite_number(
                    typical_norm
                )
                or typical_norm <= 0
            ):
                _add_rejection(
                    rejections,
                    InterventionRejectionCode.INVALID_CAP,
                    (
                        "typical_activation_norm "
                        "must be positive and finite."
                    ),
                )

            else:
                cap_is_valid = True

                maximum_applied_alpha = (
                    float(
                        max_relative_norm
                    )
                    * float(
                        typical_norm
                    )
                )

    # --------------------------------------------------------------
    # Applied-alpha cap and sign validation
    # --------------------------------------------------------------

    if (
        cap_is_valid
        and maximum_applied_alpha
        is not None
        and isinstance(
            alpha_table,
            list,
        )
    ):
        for dose_index, dose in enumerate(
            alpha_table
        ):
            if not isinstance(
                dose,
                Mapping,
            ):
                continue

            requested = dose.get(
                "alpha_requested"
            )

            applied = dose.get(
                "alpha_applied"
            )

            if not (
                _is_finite_number(
                    requested
                )
                and _is_finite_number(
                    applied
                )
            ):
                continue

            requested_value = float(
                requested
            )

            applied_value = float(
                applied
            )

            if (
                abs(
                    applied_value
                )
                > maximum_applied_alpha
            ):
                _add_rejection(
                    rejections,
                    InterventionRejectionCode.ALPHA_EXCEEDS_CAP,
                    (
                        f"alpha_table[{dose_index}].alpha_applied "
                        "exceeds the declared activation-norm cap."
                    ),
                )

            if (
                requested_value != 0.0
                and applied_value != 0.0
                and math.copysign(
                    1.0,
                    requested_value,
                )
                != math.copysign(
                    1.0,
                    applied_value,
                )
            ):
                _add_rejection(
                    rejections,
                    InterventionRejectionCode.ALPHA_SIGN_REVERSAL,
                    (
                        f"alpha_table[{dose_index}].alpha_applied "
                        "reverses the sign of alpha_requested."
                    ),
                )

    # --------------------------------------------------------------
    # Validation flags
    # --------------------------------------------------------------

    validation_flags = request[
        "validation_flags"
    ]

    if not isinstance(
        validation_flags,
        Mapping,
    ):
        _add_rejection(
            rejections,
            InterventionRejectionCode.INVALID_VALIDATION_FLAGS,
            "validation_flags must be a mapping.",
        )

    else:
        required = (
            "time_orthogonalization_checked",
            "raw_space_equivalence_verified",
            "near_zero_residual_detected",
            "contains_cap_reduced_doses",
        )

        missing = _missing_fields(
            validation_flags,
            required,
        )

        if missing:
            _add_rejection(
                rejections,
                InterventionRejectionCode.INVALID_VALIDATION_FLAGS,
                (
                    "validation_flags is missing: "
                    + ", ".join(missing)
                ),
            )

        else:
            flags_are_boolean = True

            for field in required:
                if not isinstance(
                    validation_flags[
                        field
                    ],
                    bool,
                ):
                    flags_are_boolean = False

                    _add_rejection(
                        rejections,
                        InterventionRejectionCode.INVALID_VALIDATION_FLAGS,
                        (
                            f"validation_flags.{field} "
                            "must be boolean."
                        ),
                    )

            if flags_are_boolean:
                if (
                    validation_flags[
                        "raw_space_equivalence_verified"
                    ]
                    is not True
                ):
                    _add_rejection(
                        rejections,
                        InterventionRejectionCode.RAW_SPACE_EQUIVALENCE_UNVERIFIED,
                        (
                            "Raw-space equivalence must be "
                            "verified before generation."
                        ),
                    )

                if (
                    validation_flags[
                        "near_zero_residual_detected"
                    ]
                    is True
                ):
                    _add_rejection(
                        rejections,
                        InterventionRejectionCode.NEAR_ZERO_RESIDUAL_DIRECTION,
                        (
                            "A request marked as near-zero residual "
                            "cannot enter generation."
                        ),
                    )

                if (
                    validation_flags[
                        "contains_cap_reduced_doses"
                    ]
                    != has_cap_reduced_doses
                ):
                    _add_rejection(
                        rejections,
                        InterventionRejectionCode.CAP_REDUCTION_MISMATCH,
                        (
                            "contains_cap_reduced_doses does not "
                            "match the alpha table."
                        ),
                    )

    return InterventionValidationResult(
        accepted=not rejections,
        rejections=tuple(rejections),
    )