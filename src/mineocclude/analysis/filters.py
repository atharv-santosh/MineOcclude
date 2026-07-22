"""Ordered, auditable filtering for Person B claim-bearing analysis rows."""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any

from mineocclude.analysis.manifests import seal_artifact
from mineocclude.contracts.identity import FRAME_KEY
from mineocclude.oracle.schema import is_sha256


class FilterRejectionCode(str, Enum):
    NOT_A_MAPPING = "not_a_mapping"
    MISSING_REQUIRED_FIELD = "missing_required_field"
    INVALID_IDENTITY = "invalid_identity"
    INVALID_VISIBILITY = "invalid_visibility"
    DUPLICATE_FRAME_KEY = "duplicate_frame_key"
    LIFECYCLE_NOT_ACCEPTED = "lifecycle_not_accepted"
    NONFINITE_NUMERIC_VALUE = "nonfinite_numeric_value"
    NO_VISIBLE_ANCHOR = "no_visible_anchor"
    PRE_FIRST_SEEN = "pre_first_seen"
    INVALID_MANIFEST_HASH = "invalid_manifest_hash"
    ACCEPTED_MANIFEST_MISMATCH = "accepted_manifest_mismatch"


@dataclass(frozen=True)
class FilterRejection:
    row_index: int
    frame_key: tuple[Any, ...] | None
    step: str
    code: FilterRejectionCode
    message: str


@dataclass(frozen=True)
class FilterStepAudit:
    step: str
    input_count: int
    rejected_count: int
    output_count: int


@dataclass(frozen=True)
class FilterResult:
    accepted_rows: tuple[Mapping[str, Any], ...]
    rejections: tuple[FilterRejection, ...]
    steps: tuple[FilterStepAudit, ...]

    @property
    def input_count(self) -> int:
        return self.steps[0].input_count if self.steps else 0

    @property
    def accepted_count(self) -> int:
        return len(self.accepted_rows)


DEFAULT_REQUIRED_FIELDS = (
    "trajectory_id",
    "model_frame_idx",
    "layout_id",
    "visibility",
    "status",
    "accepted_manifest_hash",
)
DEFAULT_NUMERIC_FIELDS = ("tau", "v", "q", "duration")


def _key(row: Mapping[str, Any]) -> tuple[Any, ...] | None:
    try:
        return tuple(row[field] for field in FRAME_KEY)
    except KeyError:
        return None


def apply_ordered_filters(
    rows: Iterable[Mapping[str, Any]],
    *,
    accepted_manifest_hash: str,
    required_fields: Sequence[str] = DEFAULT_REQUIRED_FIELDS,
    numeric_fields: Sequence[str] = DEFAULT_NUMERIC_FIELDS,
) -> FilterResult:
    """Apply the frozen filter order and retain every first rejection reason.

    Rows are never silently repaired, clipped, or dropped. Each rejected input
    receives exactly one stable reason at the first failed filter step.
    """

    if not is_sha256(accepted_manifest_hash):
        raise ValueError("accepted_manifest_hash must be a SHA-256 digest.")
    indexed = list(enumerate(rows))
    rejections: list[FilterRejection] = []
    audits: list[FilterStepAudit] = []

    def run_step(
        step: str,
        candidates: list[tuple[int, Mapping[str, Any]]],
        predicate: Any,
    ) -> list[tuple[int, Mapping[str, Any]]]:
        kept: list[tuple[int, Mapping[str, Any]]] = []
        for index, row in candidates:
            rejection = predicate(index, row)
            if rejection is None:
                kept.append((index, row))
            else:
                code, message = rejection
                rejections.append(
                    FilterRejection(index, _key(row), step, code, message)
                )
        audits.append(
            FilterStepAudit(
                step,
                len(candidates),
                len(candidates) - len(kept),
                len(kept),
            )
        )
        return kept

    typed: list[tuple[int, Mapping[str, Any]]] = []
    seen: set[tuple[Any, ...]] = set()
    input_count = len(indexed)
    for index, value in indexed:
        if not isinstance(value, Mapping):
            rejections.append(
                FilterRejection(
                    index,
                    None,
                    "required_fields",
                    FilterRejectionCode.NOT_A_MAPPING,
                    "Analysis rows must be mappings.",
                )
            )
            continue
        missing = [field for field in required_fields if field not in value]
        if missing:
            rejections.append(
                FilterRejection(
                    index,
                    _key(value),
                    "required_fields",
                    FilterRejectionCode.MISSING_REQUIRED_FIELD,
                    "Missing required fields: " + ", ".join(missing),
                )
            )
            continue
        if (
            not isinstance(value["trajectory_id"], str)
            or not value["trajectory_id"]
            or not isinstance(value["layout_id"], str)
            or not value["layout_id"]
            or not isinstance(value["model_frame_idx"], int)
            or isinstance(value["model_frame_idx"], bool)
            or value["model_frame_idx"] < 0
        ):
            rejections.append(
                FilterRejection(
                    index,
                    _key(value),
                    "required_fields",
                    FilterRejectionCode.INVALID_IDENTITY,
                    "Trajectory/layout IDs and model_frame_idx are invalid.",
                )
            )
            continue
        if (
            not isinstance(value["visibility"], str)
            or value["visibility"] not in {"visible", "occluded"}
        ):
            rejections.append(
                FilterRejection(
                    index,
                    _key(value),
                    "required_fields",
                    FilterRejectionCode.INVALID_VISIBILITY,
                    "visibility must be visible or occluded.",
                )
            )
            continue
        frame_key = _key(value)
        if frame_key in seen:
            rejections.append(
                FilterRejection(
                    index,
                    frame_key,
                    "required_fields",
                    FilterRejectionCode.DUPLICATE_FRAME_KEY,
                    f"Duplicate frame key: {frame_key}.",
                )
            )
            continue
        seen.add(frame_key)
        typed.append((index, value))
    audits.append(
        FilterStepAudit(
            "required_fields",
            input_count,
            input_count - len(typed),
            len(typed),
        )
    )

    current = run_step(
        "lifecycle_status",
        typed,
        lambda _index, row: None
        if row["status"] == "accepted"
        else (
            FilterRejectionCode.LIFECYCLE_NOT_ACCEPTED,
            f"status={row['status']!r} is not accepted.",
        ),
    )

    def finite_rejection(_index: int, row: Mapping[str, Any]) -> Any:
        for field in numeric_fields:
            value = row.get(field)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
            ):
                return (
                    FilterRejectionCode.NONFINITE_NUMERIC_VALUE,
                    f"{field} must be finite numeric data.",
                )
        return None

    current = run_step("finite_numeric_values", current, finite_rejection)

    def manifest_rejection(_index: int, row: Mapping[str, Any]) -> Any:
        value = row["accepted_manifest_hash"]
        if not is_sha256(value):
            return (
                FilterRejectionCode.INVALID_MANIFEST_HASH,
                "accepted_manifest_hash is not SHA-256.",
            )
        if value != accepted_manifest_hash:
            return (
                FilterRejectionCode.ACCEPTED_MANIFEST_MISMATCH,
                "Row belongs to a different accepted manifest.",
            )
        return None

    current = run_step("accepted_manifest_match", current, manifest_rejection)

    # Visible-history eligibility is derived only from rows that belong to the
    # accepted source manifest. Otherwise a visible row from a rejected source
    # can incorrectly make an accepted occluded row look post-first-seen.
    first_visible: dict[str, int] = {}
    by_trajectory: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for _index, row in current:
        by_trajectory[str(row["trajectory_id"])].append(row)
    for trajectory_id, trajectory_rows in by_trajectory.items():
        visible_indices = [
            int(row["model_frame_idx"])
            for row in trajectory_rows
            if row["visibility"] == "visible"
            and isinstance(row["model_frame_idx"], int)
            and not isinstance(row["model_frame_idx"], bool)
        ]
        if visible_indices:
            first_visible[trajectory_id] = min(visible_indices)

    def seen_rejection(_index: int, row: Mapping[str, Any]) -> Any:
        trajectory_id = str(row["trajectory_id"])
        anchor = first_visible.get(trajectory_id)
        if anchor is None:
            return (
                FilterRejectionCode.NO_VISIBLE_ANCHOR,
                "Trajectory has no authoritative visible anchor.",
            )
        model_frame_idx = row["model_frame_idx"]
        if (
            not isinstance(model_frame_idx, int)
            or isinstance(model_frame_idx, bool)
            or model_frame_idx < anchor
        ):
            return (
                FilterRejectionCode.PRE_FIRST_SEEN,
                f"model_frame_idx precedes first visible frame {anchor}.",
            )
        return None

    current = run_step("post_first_seen", current, seen_rejection)
    return FilterResult(
        accepted_rows=tuple(row for _index, row in current),
        rejections=tuple(rejections),
        steps=tuple(audits),
    )


def build_filter_audit_artifact(
    result: FilterResult,
    *,
    artifact_id: str,
    code_sha: str,
    config_hash: str,
    input_manifest_hash: str,
) -> dict[str, Any]:
    """Persist ordered counts and stable first-rejection reasons."""

    return seal_artifact(
        {
            "artifact_type": "filter_audit",
            "artifact_id": artifact_id,
            "code_sha": code_sha,
            "config_hash": config_hash,
            "input_manifest_hash": input_manifest_hash,
            "filter_schema_version": "person-b-filter-audit-v0.1",
            "input_count": result.input_count,
            "accepted_count": result.accepted_count,
            "steps": [
                {
                    "step": step.step,
                    "input_count": step.input_count,
                    "rejected_count": step.rejected_count,
                    "output_count": step.output_count,
                }
                for step in result.steps
            ],
            "rejections": [
                {
                    "row_index": rejection.row_index,
                    "frame_key": list(rejection.frame_key)
                    if rejection.frame_key is not None
                    else None,
                    "step": rejection.step,
                    "code": rejection.code.value,
                    "message": rejection.message,
                }
                for rejection in result.rejections
            ],
        }
    )
