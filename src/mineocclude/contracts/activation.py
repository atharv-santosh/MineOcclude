"""A→B activation handoff contract for MineOcclude.

This module defines and validates the activation-index handoff produced by
Person A and consumed by Person B.

The contract makes every activation row explicitly traceable to its source
trajectory, model frame, layer, hook site, token positions, storage chunk,
model/checkpoint identity, preprocessing identity, manifest, and producing run.

This module does not define probe targets, held-out labels, statistics, or
Person B's scientific methods.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any

from mineocclude.contracts.identity import (
    SCHEMA_VERSION,
    IdentityValidationError,
    validate_identity,
)


ACTIVATION_SCHEMA_VERSION = SCHEMA_VERSION

# MineWorld 700M_16f token layout locked by the roadmap.
VISUAL_TOKENS_PER_FRAME = 336
TOKENS_PER_FRAME_ACTION_PAIR = 347
MAX_MODEL_FRAMES = 16
EXPECTED_VECTOR_SHAPE = (2048,)


ALLOWED_DTYPES = {
    "float16",
    "bfloat16",
    "float32",
    "float64",
}


ALLOWED_RUN_STATUSES = {
    "completed",
    "partial",
    "failed",
}


ACTIVATION_KEY_FIELDS = (
    "trajectory_id",
    "model_frame_idx",
    "layer_idx",
    "hook_site",
)


REQUIRED_INDEX_FIELDS = (
    "activation_chunk_id",
    "chunk_row_idx",
    "layer_idx",
    "hook_site",
    "frame_token_positions",
    "token_region",
    "pooling_method",
    "dtype",
    "vector_shape",
    "checkpoint_hash",
    "accepted_manifest_hash",
    "run_status",
)


class ActivationRejectionCode(str, Enum):
    """Machine-readable activation-handoff rejection reasons."""

    MISSING_REQUIRED_FIELD = "missing_required_field"
    INVALID_SCHEMA_VERSION = "invalid_schema_version"
    INVALID_HASH = "invalid_hash"
    INVALID_RUN_STATUS = "invalid_run_status"

    INVALID_SELECTION_POLICY = "invalid_selection_policy"
    LEAKAGE_SELECTION_FORBIDDEN = "leakage_selection_forbidden"

    INVALID_CHUNK_DESCRIPTOR = "invalid_chunk_descriptor"
    DUPLICATE_CHUNK_ID = "duplicate_chunk_id"

    INVALID_INDEX_ROW = "invalid_index_row"
    DUPLICATE_ACTIVATION_IDENTITY = "duplicate_activation_identity"
    DUPLICATE_CHUNK_ROW = "duplicate_chunk_row"

    INVALID_TOKEN_POSITIONS = "invalid_token_positions"
    CHUNK_REFERENCE_MISMATCH = "chunk_reference_mismatch"
    METADATA_MISMATCH = "metadata_mismatch"

    INVALID_CARDINALITY_REPORT = "invalid_cardinality_report"
    CARDINALITY_MISMATCH = "cardinality_mismatch"


@dataclass(frozen=True)
class ActivationRejection:
    """One machine-readable activation-handoff rejection."""

    code: ActivationRejectionCode
    message: str


@dataclass(frozen=True)
class ActivationValidationResult:
    """Result returned by the activation-handoff validator."""

    accepted: bool
    rejections: tuple[ActivationRejection, ...]


def _add_rejection(
    rejections: list[ActivationRejection],
    code: ActivationRejectionCode,
    message: str,
) -> None:
    """Append one rejection record."""

    rejections.append(
        ActivationRejection(
            code=code,
            message=message,
        )
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


def _is_positive_integer(
    value: Any,
) -> bool:
    """Return True for strictly positive integers."""

    return (
        isinstance(value, int)
        and not isinstance(value, bool)
        and value > 0
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


def _is_valid_shape(
    value: Any,
) -> bool:
    """Return True for the locked pooled MineWorld vector shape."""

    return (
        isinstance(value, list)
        and value
        == list(
            EXPECTED_VECTOR_SHAPE
        )
    )


def _normalize_layer_counts(
    value: Any,
) -> dict[str, int] | None:
    """Validate and normalize a JSON per-layer count mapping."""

    if not isinstance(
        value,
        Mapping,
    ):
        return None

    normalized: dict[
        str,
        int,
    ] = {}

    for raw_layer, count in value.items():
        if (
            not isinstance(raw_layer, str)
            or not raw_layer.isdigit()
        ):
            return None

        layer = int(
            raw_layer
        )

        canonical_layer = str(
            layer
        )

        if (
            raw_layer != canonical_layer
            or canonical_layer in normalized
            or not _is_non_negative_integer(
                count
            )
        ):
            return None

        normalized[
            canonical_layer
        ] = count

    return normalized


def _expected_visual_token_positions(
    model_frame_idx: int,
) -> list[int]:
    """Return the exact visual-token positions for one model frame."""

    start = (
        model_frame_idx
        * TOKENS_PER_FRAME_ACTION_PAIR
    )

    return list(
        range(
            start,
            start + VISUAL_TOKENS_PER_FRAME,
        )
    )


def _missing_fields(
    value: Mapping[str, Any],
    required_fields: tuple[str, ...],
) -> list[str]:
    """Return required fields absent from a mapping."""

    return [
        field
        for field in required_fields
        if field not in value
    ]


def validate_activation_handoff(
    package: Mapping[str, Any],
) -> ActivationValidationResult:
    """Validate one Person A → Person B activation handoff.

    The validator checks structural identity, provenance, storage references,
    extraction independence from target/held-out labels, and cardinality.

    It does not mutate or repair the submitted handoff.
    """

    rejections: list[
        ActivationRejection
    ] = []

    if not isinstance(
        package,
        Mapping,
    ):
        _add_rejection(
            rejections,
            ActivationRejectionCode.MISSING_REQUIRED_FIELD,
            "Activation handoff must be a mapping.",
        )

        return ActivationValidationResult(
            accepted=False,
            rejections=tuple(rejections),
        )

    required_top_level = (
        "schema_version",
        "handoff_id",
        "accepted_manifest_hash",
        "checkpoint_hash",
        "preprocess_hash",
        "run_id",
        "run_status",
        "selection_policy",
        "chunks",
        "index_rows",
        "cardinality_report",
    )

    missing = _missing_fields(
        package,
        required_top_level,
    )

    if missing:
        _add_rejection(
            rejections,
            ActivationRejectionCode.MISSING_REQUIRED_FIELD,
            "Missing top-level fields: "
            + ", ".join(missing),
        )

        return ActivationValidationResult(
            accepted=False,
            rejections=tuple(rejections),
        )

    # ------------------------------------------------------------------
    # Top-level schema and provenance
    # ------------------------------------------------------------------

    if (
        package["schema_version"]
        != ACTIVATION_SCHEMA_VERSION
    ):
        _add_rejection(
            rejections,
            ActivationRejectionCode.INVALID_SCHEMA_VERSION,
            (
                "Expected activation schema version "
                f"{ACTIVATION_SCHEMA_VERSION!r}."
            ),
        )

    for field in (
        "handoff_id",
        "run_id",
    ):
        value = package[field]

        if (
            not isinstance(value, str)
            or not value.strip()
        ):
            _add_rejection(
                rejections,
                ActivationRejectionCode.MISSING_REQUIRED_FIELD,
                f"{field} must be a non-empty string.",
            )

    for field in (
        "accepted_manifest_hash",
        "checkpoint_hash",
        "preprocess_hash",
    ):
        if not _is_sha256(
            package[field]
        ):
            _add_rejection(
                rejections,
                ActivationRejectionCode.INVALID_HASH,
                (
                    f"{field} must be a valid "
                    "64-character SHA-256 value."
                ),
            )

    run_status = package[
        "run_status"
    ]

    if (
        not isinstance(run_status, str)
        or run_status
        not in ALLOWED_RUN_STATUSES
    ):
        _add_rejection(
            rejections,
            ActivationRejectionCode.INVALID_RUN_STATUS,
            (
                "run_status must be one of: "
                + ", ".join(
                    sorted(ALLOWED_RUN_STATUSES)
                )
            ),
        )

    # ------------------------------------------------------------------
    # Extraction-selection independence
    # ------------------------------------------------------------------

    selection_policy = package[
        "selection_policy"
    ]

    if not isinstance(
        selection_policy,
        Mapping,
    ):
        _add_rejection(
            rejections,
            ActivationRejectionCode.INVALID_SELECTION_POLICY,
            "selection_policy must be a mapping.",
        )

    else:
        required_selection_fields = (
            "uses_target_labels",
            "uses_heldout_labels",
            "description",
        )

        selection_missing = _missing_fields(
            selection_policy,
            required_selection_fields,
        )

        if selection_missing:
            _add_rejection(
                rejections,
                ActivationRejectionCode.INVALID_SELECTION_POLICY,
                (
                    "selection_policy is missing: "
                    + ", ".join(
                        selection_missing
                    )
                ),
            )

        else:
            for field in (
                "uses_target_labels",
                "uses_heldout_labels",
            ):
                if not isinstance(
                    selection_policy[field],
                    bool,
                ):
                    _add_rejection(
                        rejections,
                        ActivationRejectionCode.INVALID_SELECTION_POLICY,
                        f"{field} must be boolean.",
                    )

            if (
                selection_policy[
                    "uses_target_labels"
                ]
                is True
                or selection_policy[
                    "uses_heldout_labels"
                ]
                is True
            ):
                _add_rejection(
                    rejections,
                    ActivationRejectionCode.LEAKAGE_SELECTION_FORBIDDEN,
                    (
                        "Person A extraction selection "
                        "cannot use target or held-out labels."
                    ),
                )

            description = selection_policy[
                "description"
            ]

            if (
                not isinstance(
                    description,
                    str,
                )
                or not description.strip()
            ):
                _add_rejection(
                    rejections,
                    ActivationRejectionCode.INVALID_SELECTION_POLICY,
                    (
                        "selection_policy.description "
                        "must be a non-empty string."
                    ),
                )

    # ------------------------------------------------------------------
    # Activation chunk descriptors
    # ------------------------------------------------------------------

    chunks = package[
        "chunks"
    ]

    chunk_by_id: dict[
        str,
        Mapping[str, Any],
    ] = {}

    if not isinstance(
        chunks,
        list,
    ):
        _add_rejection(
            rejections,
            ActivationRejectionCode.INVALID_CHUNK_DESCRIPTOR,
            "chunks must be a list.",
        )

        chunks = []

    required_chunk_fields = (
        "chunk_id",
        "path",
        "sha256",
        "row_count",
        "dtype",
        "vector_shape",
    )

    for chunk_index, chunk in enumerate(
        chunks
    ):
        if not isinstance(
            chunk,
            Mapping,
        ):
            _add_rejection(
                rejections,
                ActivationRejectionCode.INVALID_CHUNK_DESCRIPTOR,
                (
                    f"chunks[{chunk_index}] "
                    "must be a mapping."
                ),
            )

            continue

        chunk_missing = _missing_fields(
            chunk,
            required_chunk_fields,
        )

        if chunk_missing:
            _add_rejection(
                rejections,
                ActivationRejectionCode.INVALID_CHUNK_DESCRIPTOR,
                (
                    f"chunks[{chunk_index}] is missing: "
                    + ", ".join(
                        chunk_missing
                    )
                ),
            )

            continue

        chunk_id = chunk[
            "chunk_id"
        ]

        if (
            not isinstance(
                chunk_id,
                str,
            )
            or not chunk_id.strip()
        ):
            _add_rejection(
                rejections,
                ActivationRejectionCode.INVALID_CHUNK_DESCRIPTOR,
                (
                    f"chunks[{chunk_index}].chunk_id "
                    "must be a non-empty string."
                ),
            )

            continue

        if chunk_id in chunk_by_id:
            _add_rejection(
                rejections,
                ActivationRejectionCode.DUPLICATE_CHUNK_ID,
                (
                    f"Duplicate activation chunk ID: "
                    f"{chunk_id!r}."
                ),
            )

        else:
            chunk_by_id[
                chunk_id
            ] = chunk

        path = chunk[
            "path"
        ]

        if (
            not isinstance(path, str)
            or not path.strip()
        ):
            _add_rejection(
                rejections,
                ActivationRejectionCode.INVALID_CHUNK_DESCRIPTOR,
                (
                    f"Chunk {chunk_id!r} requires "
                    "a non-empty path."
                ),
            )

        if not _is_sha256(
            chunk["sha256"]
        ):
            _add_rejection(
                rejections,
                ActivationRejectionCode.INVALID_HASH,
                (
                    f"Chunk {chunk_id!r} has "
                    "an invalid SHA-256 value."
                ),
            )

        if not _is_positive_integer(
            chunk["row_count"]
        ):
            _add_rejection(
                rejections,
                ActivationRejectionCode.INVALID_CHUNK_DESCRIPTOR,
                (
                    f"Chunk {chunk_id!r}.row_count "
                    "must be a positive integer."
                ),
            )

        chunk_dtype = chunk[
            "dtype"
        ]

        if (
            not isinstance(chunk_dtype, str)
            or chunk_dtype
            not in ALLOWED_DTYPES
        ):
            _add_rejection(
                rejections,
                ActivationRejectionCode.INVALID_CHUNK_DESCRIPTOR,
                (
                    f"Chunk {chunk_id!r} has "
                    "an unsupported dtype."
                ),
            )

        if not _is_valid_shape(
            chunk["vector_shape"]
        ):
            _add_rejection(
                rejections,
                ActivationRejectionCode.INVALID_CHUNK_DESCRIPTOR,
                (
                    f"Chunk {chunk_id!r} has "
                    "an invalid vector_shape."
                ),
            )

    # ------------------------------------------------------------------
    # Activation index rows
    # ------------------------------------------------------------------

    index_rows = package[
        "index_rows"
    ]

    if not isinstance(
        index_rows,
        list,
    ):
        _add_rejection(
            rejections,
            ActivationRejectionCode.INVALID_INDEX_ROW,
            "index_rows must be a list.",
        )

        index_rows = []

    seen_activation_keys: set[
        tuple[Any, ...]
    ] = set()

    seen_chunk_rows: set[
        tuple[str, int]
    ] = set()

    referenced_rows_by_chunk: Counter[
        str
    ] = Counter()

    actual_rows_by_layer: Counter[
        int
    ] = Counter()

    represented_manifest_keys: set[
        tuple[str, int]
    ] = set()

    for row_index, row in enumerate(
        index_rows
    ):
        if not isinstance(
            row,
            Mapping,
        ):
            _add_rejection(
                rejections,
                ActivationRejectionCode.INVALID_INDEX_ROW,
                (
                    f"index_rows[{row_index}] "
                    "must be a mapping."
                ),
            )

            continue

        # Validate the universal identity fields inherited from Step 1.2.
        try:
            validate_identity(
                row
            )

        except (
            IdentityValidationError,
            TypeError,
        ) as error:
            _add_rejection(
                rejections,
                ActivationRejectionCode.INVALID_INDEX_ROW,
                (
                    f"index_rows[{row_index}] "
                    f"has invalid universal identity: {error}"
                ),
            )

        missing_index_fields = _missing_fields(
            row,
            REQUIRED_INDEX_FIELDS,
        )

        if missing_index_fields:
            _add_rejection(
                rejections,
                ActivationRejectionCode.INVALID_INDEX_ROW,
                (
                    f"index_rows[{row_index}] is missing: "
                    + ", ".join(
                        missing_index_fields
                    )
                ),
            )

            continue

        # Only accepted activation rows enter the A→B handoff.
        if row.get(
            "status"
        ) != "accepted":
            _add_rejection(
                rejections,
                ActivationRejectionCode.INVALID_INDEX_ROW,
                (
                    f"index_rows[{row_index}] "
                    "must have status='accepted'."
                ),
            )

        layer_idx = row[
            "layer_idx"
        ]

        if not _is_non_negative_integer(
            layer_idx
        ):
            _add_rejection(
                rejections,
                ActivationRejectionCode.INVALID_INDEX_ROW,
                (
                    f"index_rows[{row_index}].layer_idx "
                    "must be a non-negative integer."
                ),
            )

        else:
            actual_rows_by_layer[
                layer_idx
            ] += 1

        hook_site = row[
            "hook_site"
        ]

        if (
            not isinstance(
                hook_site,
                str,
            )
            or not hook_site.strip()
        ):
            _add_rejection(
                rejections,
                ActivationRejectionCode.INVALID_INDEX_ROW,
                (
                    f"index_rows[{row_index}].hook_site "
                    "must be a non-empty string."
                ),
            )

        model_frame_idx = row.get(
            "model_frame_idx"
        )

        trajectory_id = row.get(
            "trajectory_id"
        )

        if (
            isinstance(
                trajectory_id,
                str,
            )
            and trajectory_id.strip()
            and _is_non_negative_integer(
                model_frame_idx
            )
        ):
            represented_manifest_keys.add(
                (
                    trajectory_id,
                    model_frame_idx,
                )
            )

        if (
            _is_non_negative_integer(
                model_frame_idx
            )
            and model_frame_idx
            >= MAX_MODEL_FRAMES
        ):
            _add_rejection(
                rejections,
                ActivationRejectionCode.INVALID_INDEX_ROW,
                (
                    f"index_rows[{row_index}].model_frame_idx "
                    f"must be less than {MAX_MODEL_FRAMES}."
                ),
            )

        # Exact visual-token positions used to produce the pooled vector.
        token_positions = row[
            "frame_token_positions"
        ]

        if (
            not isinstance(
                token_positions,
                list,
            )
            or len(
                token_positions
            )
            != VISUAL_TOKENS_PER_FRAME
            or not all(
                _is_non_negative_integer(
                    position
                )
                for position in token_positions
            )
        ):
            _add_rejection(
                rejections,
                ActivationRejectionCode.INVALID_TOKEN_POSITIONS,
                (
                    f"index_rows[{row_index}] must contain "
                    f"exactly {VISUAL_TOKENS_PER_FRAME} "
                    "non-negative visual-token positions."
                ),
            )

        elif (
            _is_non_negative_integer(
                model_frame_idx
            )
            and model_frame_idx
            < MAX_MODEL_FRAMES
            and token_positions
            != _expected_visual_token_positions(
                model_frame_idx
            )
        ):
            _add_rejection(
                rejections,
                ActivationRejectionCode.INVALID_TOKEN_POSITIONS,
                (
                    f"index_rows[{row_index}] "
                    "frame_token_positions do not match "
                    "the locked MineWorld frame layout."
                ),
            )

        if row[
            "token_region"
        ] != "visual":
            _add_rejection(
                rejections,
                ActivationRejectionCode.INVALID_INDEX_ROW,
                (
                    f"index_rows[{row_index}].token_region "
                    "must equal 'visual'."
                ),
            )

        if row[
            "pooling_method"
        ] != "mean":
            _add_rejection(
                rejections,
                ActivationRejectionCode.INVALID_INDEX_ROW,
                (
                    f"index_rows[{row_index}].pooling_method "
                    "must equal 'mean'."
                ),
            )

        row_dtype = row[
            "dtype"
        ]

        if (
            not isinstance(row_dtype, str)
            or row_dtype
            not in ALLOWED_DTYPES
        ):
            _add_rejection(
                rejections,
                ActivationRejectionCode.INVALID_INDEX_ROW,
                (
                    f"index_rows[{row_index}] "
                    "contains an unsupported dtype."
                ),
            )

        if not _is_valid_shape(
            row[
                "vector_shape"
            ]
        ):
            _add_rejection(
                rejections,
                ActivationRejectionCode.INVALID_INDEX_ROW,
                (
                    f"index_rows[{row_index}] "
                    "contains an invalid vector_shape."
                ),
            )

        # Package-level provenance must agree with each row.
        metadata_pairs = (
            (
                "checkpoint_hash",
                package[
                    "checkpoint_hash"
                ],
            ),
            (
                "preprocess_hash",
                package[
                    "preprocess_hash"
                ],
            ),
            (
                "accepted_manifest_hash",
                package[
                    "accepted_manifest_hash"
                ],
            ),
            (
                "run_id",
                package[
                    "run_id"
                ],
            ),
            (
                "run_status",
                package[
                    "run_status"
                ],
            ),
        )

        for (
            field,
            expected_value,
        ) in metadata_pairs:
            if row.get(
                field
            ) != expected_value:
                _add_rejection(
                    rejections,
                    ActivationRejectionCode.METADATA_MISMATCH,
                    (
                        f"index_rows[{row_index}].{field} "
                        "does not match handoff metadata."
                    ),
                )

        # Universal model_hash must agree with the explicit checkpoint hash.
        if row.get(
            "model_hash"
        ) != package[
            "checkpoint_hash"
        ]:
            _add_rejection(
                rejections,
                ActivationRejectionCode.METADATA_MISMATCH,
                (
                    f"index_rows[{row_index}].model_hash "
                    "does not match checkpoint_hash."
                ),
            )

        # ------------------------------------------------------------------
        # Chunk references
        # ------------------------------------------------------------------

        activation_chunk_id = row[
            "activation_chunk_id"
        ]

        chunk_row_idx = row[
            "chunk_row_idx"
        ]

        if (
            not isinstance(
                activation_chunk_id,
                str,
            )
            or not activation_chunk_id.strip()
        ):
            _add_rejection(
                rejections,
                ActivationRejectionCode.CHUNK_REFERENCE_MISMATCH,
                (
                    f"index_rows[{row_index}] has "
                    "an invalid activation_chunk_id."
                ),
            )

        elif (
            activation_chunk_id
            not in chunk_by_id
        ):
            _add_rejection(
                rejections,
                ActivationRejectionCode.CHUNK_REFERENCE_MISMATCH,
                (
                    f"index_rows[{row_index}] references "
                    f"unknown chunk {activation_chunk_id!r}."
                ),
            )

        elif not _is_non_negative_integer(
            chunk_row_idx
        ):
            _add_rejection(
                rejections,
                ActivationRejectionCode.CHUNK_REFERENCE_MISMATCH,
                (
                    f"index_rows[{row_index}].chunk_row_idx "
                    "must be a non-negative integer."
                ),
            )

        else:
            chunk = chunk_by_id[
                activation_chunk_id
            ]

            row_count = chunk.get(
                "row_count"
            )

            if (
                _is_positive_integer(
                    row_count
                )
                and chunk_row_idx
                >= row_count
            ):
                _add_rejection(
                    rejections,
                    ActivationRejectionCode.CHUNK_REFERENCE_MISMATCH,
                    (
                        f"index_rows[{row_index}].chunk_row_idx "
                        "falls outside the referenced chunk."
                    ),
                )

            if (
                row["dtype"]
                != chunk.get(
                    "dtype"
                )
                or row[
                    "vector_shape"
                ]
                != chunk.get(
                    "vector_shape"
                )
            ):
                _add_rejection(
                    rejections,
                    ActivationRejectionCode.CHUNK_REFERENCE_MISMATCH,
                    (
                        f"index_rows[{row_index}] dtype or "
                        "vector_shape does not match its chunk."
                    ),
                )

            chunk_row_key = (
                activation_chunk_id,
                chunk_row_idx,
            )

            if (
                chunk_row_key
                in seen_chunk_rows
            ):
                _add_rejection(
                    rejections,
                    ActivationRejectionCode.DUPLICATE_CHUNK_ROW,
                    (
                        "Multiple index rows reference "
                        f"the same chunk row {chunk_row_key}."
                    ),
                )

            else:
                seen_chunk_rows.add(
                    chunk_row_key
                )

            referenced_rows_by_chunk[
                activation_chunk_id
            ] += 1

        # ------------------------------------------------------------------
        # Scientific activation-row identity
        # ------------------------------------------------------------------

        if (
            _is_non_negative_integer(
                layer_idx
            )
            and isinstance(
                hook_site,
                str,
            )
            and hook_site.strip()
            and isinstance(
                row.get(
                    "trajectory_id"
                ),
                str,
            )
            and _is_non_negative_integer(
                model_frame_idx
            )
        ):
            activation_key = (
                row[
                    "trajectory_id"
                ],
                model_frame_idx,
                layer_idx,
                hook_site,
            )

            if (
                activation_key
                in seen_activation_keys
            ):
                _add_rejection(
                    rejections,
                    ActivationRejectionCode.DUPLICATE_ACTIVATION_IDENTITY,
                    (
                        "Duplicate activation identity: "
                        f"{activation_key}."
                    ),
                )

            else:
                seen_activation_keys.add(
                    activation_key
                )

    # Every declared chunk row must have exactly one index entry.
    for chunk_id, chunk in (
        chunk_by_id.items()
    ):
        declared_row_count = chunk.get(
            "row_count"
        )

        if (
            _is_positive_integer(
                declared_row_count
            )
            and referenced_rows_by_chunk[
                chunk_id
            ]
            != declared_row_count
        ):
            _add_rejection(
                rejections,
                ActivationRejectionCode.CARDINALITY_MISMATCH,
                (
                    f"Chunk {chunk_id!r} declares "
                    f"{declared_row_count} rows but "
                    f"{referenced_rows_by_chunk[chunk_id]} "
                    "index rows reference it."
                ),
            )

    # ------------------------------------------------------------------
    # Cardinality report companion
    # ------------------------------------------------------------------

    cardinality_report = package[
        "cardinality_report"
    ]

    required_cardinality_fields = (
        "accepted_manifest_rows",
        "expected_activation_rows",
        "actual_activation_rows",
        "expected_rows_by_layer",
        "actual_rows_by_layer",
    )

    if not isinstance(
        cardinality_report,
        Mapping,
    ):
        _add_rejection(
            rejections,
            ActivationRejectionCode.INVALID_CARDINALITY_REPORT,
            "cardinality_report must be a mapping.",
        )

    else:
        cardinality_missing = _missing_fields(
            cardinality_report,
            required_cardinality_fields,
        )

        if cardinality_missing:
            _add_rejection(
                rejections,
                ActivationRejectionCode.INVALID_CARDINALITY_REPORT,
                (
                    "cardinality_report is missing: "
                    + ", ".join(
                        cardinality_missing
                    )
                ),
            )

        else:
            for field in (
                "accepted_manifest_rows",
                "expected_activation_rows",
                "actual_activation_rows",
            ):
                if not _is_non_negative_integer(
                    cardinality_report[
                        field
                    ]
                ):
                    _add_rejection(
                        rejections,
                        ActivationRejectionCode.INVALID_CARDINALITY_REPORT,
                        (
                            f"cardinality_report.{field} "
                            "must be a non-negative integer."
                        ),
                    )

            if (
                cardinality_report[
                    "actual_activation_rows"
                ]
                != len(
                    index_rows
                )
            ):
                _add_rejection(
                    rejections,
                    ActivationRejectionCode.CARDINALITY_MISMATCH,
                    (
                        "cardinality_report.actual_activation_rows "
                        "does not match the activation index."
                    ),
                )

            if (
                cardinality_report[
                    "expected_activation_rows"
                ]
                != cardinality_report[
                    "actual_activation_rows"
                ]
            ):
                _add_rejection(
                    rejections,
                    ActivationRejectionCode.CARDINALITY_MISMATCH,
                    (
                        "Expected and actual activation "
                        "row counts do not match."
                    ),
                )

            expected_rows_by_layer = _normalize_layer_counts(
                cardinality_report[
                    "expected_rows_by_layer"
                ]
            )

            reported_actual_by_layer = _normalize_layer_counts(
                cardinality_report[
                    "actual_rows_by_layer"
                ]
            )

            if (
                expected_rows_by_layer is None
                or reported_actual_by_layer is None
            ):
                _add_rejection(
                    rejections,
                    ActivationRejectionCode.INVALID_CARDINALITY_REPORT,
                    (
                        "Per-layer cardinality reports "
                        "must be mappings."
                    ),
                )

            else:
                computed_actual_by_layer = {
                    str(layer): count
                    for (
                        layer,
                        count,
                    ) in actual_rows_by_layer.items()
                }

                if (
                    reported_actual_by_layer
                    != computed_actual_by_layer
                ):
                    _add_rejection(
                        rejections,
                        ActivationRejectionCode.CARDINALITY_MISMATCH,
                        (
                            "cardinality_report.actual_rows_by_layer "
                            "does not match the activation index."
                        ),
                    )

                if (
                    expected_rows_by_layer
                    != reported_actual_by_layer
                ):
                    _add_rejection(
                        rejections,
                        ActivationRejectionCode.CARDINALITY_MISMATCH,
                        (
                            "Expected and actual per-layer "
                            "activation counts do not match."
                        ),
                    )

                if (
                    _is_non_negative_integer(
                        cardinality_report[
                            "expected_activation_rows"
                        ]
                    )
                    and cardinality_report[
                        "expected_activation_rows"
                    ]
                    != sum(
                        expected_rows_by_layer.values()
                    )
                ):
                    _add_rejection(
                        rejections,
                        ActivationRejectionCode.CARDINALITY_MISMATCH,
                        (
                            "Expected per-layer counts do not sum "
                            "to expected_activation_rows."
                        ),
                    )

                if (
                    _is_non_negative_integer(
                        cardinality_report[
                            "actual_activation_rows"
                        ]
                    )
                    and cardinality_report[
                        "actual_activation_rows"
                    ]
                    != sum(
                        reported_actual_by_layer.values()
                    )
                ):
                    _add_rejection(
                        rejections,
                        ActivationRejectionCode.CARDINALITY_MISMATCH,
                        (
                            "Actual per-layer counts do not sum "
                            "to actual_activation_rows."
                        ),
                    )

            if (
                _is_non_negative_integer(
                    cardinality_report[
                        "accepted_manifest_rows"
                    ]
                )
                and cardinality_report[
                    "accepted_manifest_rows"
                ]
                != len(
                    represented_manifest_keys
                )
            ):
                _add_rejection(
                    rejections,
                    ActivationRejectionCode.CARDINALITY_MISMATCH,
                    (
                        "cardinality_report.accepted_manifest_rows "
                        "does not match the unique trajectory/frame "
                        "identities represented by the activation index."
                    ),
                )

    return ActivationValidationResult(
        accepted=not rejections,
        rejections=tuple(
            rejections
        ),
    )
