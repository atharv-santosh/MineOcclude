"""Fail-closed join of Person E's measurements onto the U4 control matrix
(Person D Step 7.3).

Execution manual Step 7.3 requires a fail-closed *complete-manifest* join
against Person E's measurement table, keyed on authoritative IDs and
never on filenames or row order, in which every manifest clip must end up
measured, generation-failed, invalid, missing, non-persistent, or
excluded for a recorded reason. The join must validate detector,
homography, and SSIM versions, the event, seed, dose, control, layer,
timestep, direction, pair key, cardinality, and the missing reason -- and
produce the ``u4_control_matrix`` document.

"Fail-closed" here has a precise meaning: the join starts from the
*manifest*, not from the measurement table. A clip with no measurement
row becomes a ``missing`` outcome with a reason; it never silently drops
out of the denominator. Symmetrically, a measurement row that matches no
manifest clip is an error, not a bonus data point.

Nothing in this module measures anything. Person E owns measurement;
Person D owns the completeness contract over it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence

from mineocclude.baselines.u4_control_manifest_v0_1 import validate_control_manifest

SCHEMA_ID = "person-d-u4-control-matrix-v0-1"
SCHEMA_VERSION = "1.0"

#: The complete outcome vocabulary. Every manifest clip resolves to
#: exactly one of these -- there is no "other" and no implicit default.
CLIP_OUTCOMES: tuple[str, ...] = (
    "measured",
    "generation_failed",
    "invalid",
    "missing",
    "non_persistent",
    "excluded",
)

#: Outcomes that carry no numeric measurement. Their numeric fields must
#: be null; a null here is never a zero displacement or a zero SSIM.
NON_NUMERIC_OUTCOMES: frozenset[str] = frozenset(
    {"generation_failed", "invalid", "missing", "non_persistent", "excluded"}
)

#: Version fields Person E must declare on every measurement row. A row
#: missing any of them cannot be joined, because its comparability to the
#: other rows is unknown.
REQUIRED_MEASUREMENT_VERSIONS: tuple[str, ...] = (
    "detector_version",
    "homography_version",
    "ssim_version",
)

#: Identity fields that must agree between the manifest clip and Person
#: E's measurement row. A disagreement means the measurement was matched
#: to the wrong clip.
CROSS_CHECKED_IDENTITY_FIELDS: tuple[str, ...] = (
    "event_id",
    "rollout_seed",
    "dose_id",
    "control_type",
    "target_layer_idx",
    "target_timestep_idx",
    "direction_id",
    "pair_key",
)


class MeasurementJoinError(ValueError):
    """Raised when the join cannot be completed or expressed honestly."""


@dataclass(frozen=True)
class MeasurementRow:
    """One Person E measurement row, addressed by clip identity."""

    clip_id: str
    outcome: str
    event_id: str
    rollout_seed: int
    dose_id: Optional[str]
    control_type: str
    target_layer_idx: int
    target_timestep_idx: int
    direction_id: str
    pair_key: str
    detector_version: str
    homography_version: str
    ssim_version: str
    displacement_blocks: Optional[float] = None
    masked_ssim: Optional[float] = None
    missing_reason: Optional[str] = None

    def __post_init__(self) -> None:
        if self.outcome not in CLIP_OUTCOMES:
            raise MeasurementJoinError(
                f"clip {self.clip_id!r} has unknown outcome {self.outcome!r}"
            )
        if self.outcome in NON_NUMERIC_OUTCOMES:
            if self.displacement_blocks is not None or self.masked_ssim is not None:
                raise MeasurementJoinError(
                    f"clip {self.clip_id!r} is {self.outcome} but carries numeric "
                    "measurements; an unmeasured clip's values must be null, "
                    "never zero"
                )
            if not self.missing_reason:
                raise MeasurementJoinError(
                    f"clip {self.clip_id!r} is {self.outcome} without a recorded "
                    "reason"
                )
        else:
            if self.displacement_blocks is None:
                raise MeasurementJoinError(
                    f"measured clip {self.clip_id!r} carries no displacement"
                )
        for field_name in REQUIRED_MEASUREMENT_VERSIONS:
            if not getattr(self, field_name):
                raise MeasurementJoinError(
                    f"clip {self.clip_id!r} declares no {field_name}"
                )


def join_measurements_to_manifest(
    *,
    manifest: Mapping[str, Any],
    measurements: Sequence[MeasurementRow],
    expected_detector_version: Optional[str] = None,
    expected_homography_version: Optional[str] = None,
    expected_ssim_version: Optional[str] = None,
    run_id: str,
    evidence_kind: str = "synthetic",
) -> dict[str, Any]:
    """Join measurements onto the frozen manifest, fail-closed.

    Iteration is over the *manifest*, so a clip Person E never reported is
    an explicit ``missing`` row with a reason rather than an absence. The
    join key is ``clip_id``, cross-checked against every field in
    :data:`CROSS_CHECKED_IDENTITY_FIELDS`; filenames and row order are
    never consulted.
    """

    if evidence_kind not in ("real", "synthetic"):
        raise MeasurementJoinError("evidence_kind must be 'real' or 'synthetic'")
    validate_control_manifest(manifest)

    by_clip: dict[str, MeasurementRow] = {}
    for row in measurements:
        if row.clip_id in by_clip:
            raise MeasurementJoinError(
                f"clip {row.clip_id!r} has more than one measurement row; the "
                "join requires exactly one measurement per clip"
            )
        by_clip[row.clip_id] = row

    manifest_rows = {row["clip_id"]: row for row in manifest["rows"]}
    unexpected = sorted(set(by_clip) - set(manifest_rows))
    if unexpected:
        raise MeasurementJoinError(
            f"measurements reference clips that are not in the frozen manifest: "
            f"{unexpected[:5]}; a measurement with no planned control cannot be "
            "joined"
        )

    version_sets: dict[str, set[str]] = {
        field: set() for field in REQUIRED_MEASUREMENT_VERSIONS
    }
    identity_conflicts: list[dict[str, Any]] = []
    matrix_rows: list[dict[str, Any]] = []
    outcome_counts: dict[str, int] = {outcome: 0 for outcome in CLIP_OUTCOMES}

    for clip_id in sorted(manifest_rows):
        planned = manifest_rows[clip_id]
        measured = by_clip.get(clip_id)

        if measured is None:
            outcome = "missing"
            reason = "person_e_published_no_measurement_row_for_this_clip"
            entry = {
                "clip_id": clip_id,
                "pair_key": planned["pair_key"],
                "control_type": planned["control_type"],
                "event_id": planned["event_id"],
                "trajectory_id": planned["trajectory_id"],
                "layout_id": planned["layout_id"],
                "rollout_seed": planned["rollout_seed"],
                "dose_id": planned["dose_id"],
                "alpha_requested": planned["alpha_requested"],
                "alpha_applied": planned["alpha_applied"],
                "direction_id": planned["direction_id"],
                "direction_version": planned["direction_version"],
                "target_layer_idx": planned["target_layer_idx"],
                "target_timestep_idx": planned["target_timestep_idx"],
                "outcome": outcome,
                "displacement_blocks": None,
                "masked_ssim": None,
                "missing_reason": reason,
                "detector_version": None,
                "homography_version": None,
                "ssim_version": None,
            }
        else:
            for field in REQUIRED_MEASUREMENT_VERSIONS:
                version_sets[field].add(getattr(measured, field))
            conflicts = {
                field: (planned.get(field), getattr(measured, field))
                for field in CROSS_CHECKED_IDENTITY_FIELDS
                if planned.get(field) != getattr(measured, field)
            }
            if conflicts:
                identity_conflicts.append({"clip_id": clip_id, "conflicts": conflicts})
            outcome = measured.outcome
            entry = {
                "clip_id": clip_id,
                "pair_key": planned["pair_key"],
                "control_type": planned["control_type"],
                "event_id": planned["event_id"],
                "trajectory_id": planned["trajectory_id"],
                "layout_id": planned["layout_id"],
                "rollout_seed": planned["rollout_seed"],
                "dose_id": planned["dose_id"],
                "alpha_requested": planned["alpha_requested"],
                "alpha_applied": planned["alpha_applied"],
                "direction_id": planned["direction_id"],
                "direction_version": planned["direction_version"],
                "target_layer_idx": planned["target_layer_idx"],
                "target_timestep_idx": planned["target_timestep_idx"],
                "outcome": outcome,
                "displacement_blocks": measured.displacement_blocks,
                "masked_ssim": measured.masked_ssim,
                "missing_reason": measured.missing_reason,
                "detector_version": measured.detector_version,
                "homography_version": measured.homography_version,
                "ssim_version": measured.ssim_version,
            }

        outcome_counts[outcome] += 1
        matrix_rows.append(entry)

    version_findings: list[dict[str, Any]] = []
    expectations = {
        "detector_version": expected_detector_version,
        "homography_version": expected_homography_version,
        "ssim_version": expected_ssim_version,
    }
    for field, observed in version_sets.items():
        expected = expectations[field]
        consistent = len(observed) <= 1
        matches = expected is None or observed <= {expected}
        version_findings.append(
            {
                "field": field,
                "observed_values": tuple(sorted(observed)),
                "expected_value": expected,
                "consistent_across_rows": consistent,
                "matches_expected": matches,
            }
        )

    # Person E's baseline match rule is "exact event_id + seed", so a
    # measured pushed clip is only interpretable when the alpha-zero clip
    # for its own event/seed was also measured. Without that reference
    # there is no displacement to compute, only an absolute coordinate.
    baseline_measured_prefixes = {
        entry["pair_key"].rsplit("|dose", 1)[0]
        for entry in matrix_rows
        if entry["control_type"] == "alpha_zero" and entry["outcome"] == "measured"
    }
    unmatched_pairs = sorted(
        {
            entry["pair_key"]
            for entry in matrix_rows
            if entry["outcome"] == "measured"
            and entry["control_type"] != "alpha_zero"
            and entry["pair_key"].rsplit("|dose", 1)[0] not in baseline_measured_prefixes
        }
    )

    complete = (
        outcome_counts["missing"] == 0
        and not identity_conflicts
        and all(f["consistent_across_rows"] and f["matches_expected"] for f in version_findings)
        and not unmatched_pairs
    )

    return {
        "schema_id": SCHEMA_ID,
        "schema_version": SCHEMA_VERSION,
        "producer_role": "person_d",
        "run_id": run_id,
        "evidence_kind": evidence_kind,
        "manifest_id": manifest["manifest_id"],
        "manifest_version": manifest["manifest_version"],
        "manifest_checksum": manifest["manifest_checksum"],
        "join_keys": ("clip_id",),
        "cross_checked_identity_fields": CROSS_CHECKED_IDENTITY_FIELDS,
        "join_rule": (
            "The join iterates the frozen manifest and looks up clip_id. "
            "Filenames, paths, and row order are never used as identity."
        ),
        "planned_clip_count": len(manifest_rows),
        "measurement_row_count": len(by_clip),
        "outcome_counts": dict(sorted(outcome_counts.items())),
        "version_findings": tuple(version_findings),
        "identity_conflicts": tuple(identity_conflicts),
        "pair_keys_without_measured_baseline": tuple(unmatched_pairs),
        "rows": tuple(matrix_rows),
        "join_complete": complete,
    }


def validate_u4_control_matrix(document: Mapping[str, Any]) -> None:
    """Validate a joined control matrix, raising on the first violation."""

    if document.get("schema_id") != SCHEMA_ID:
        raise MeasurementJoinError(
            f"expected schema_id {SCHEMA_ID!r}, got {document.get('schema_id')!r}"
        )
    if document.get("evidence_kind") not in ("real", "synthetic"):
        raise MeasurementJoinError("evidence_kind must be 'real' or 'synthetic'")

    rows = document.get("rows") or ()
    if not rows:
        raise MeasurementJoinError("a control matrix must contain rows")

    clip_ids = [row["clip_id"] for row in rows]
    if len(set(clip_ids)) != len(clip_ids):
        raise MeasurementJoinError("duplicate clip_id in the joined matrix")
    if document.get("planned_clip_count") != len(rows):
        raise MeasurementJoinError(
            "planned_clip_count does not match the joined row count; the join "
            "must cover every planned clip"
        )

    counts = {outcome: 0 for outcome in CLIP_OUTCOMES}
    for row in rows:
        outcome = row["outcome"]
        if outcome not in CLIP_OUTCOMES:
            raise MeasurementJoinError(
                f"clip {row['clip_id']!r} has unknown outcome {outcome!r}"
            )
        counts[outcome] += 1
        if outcome in NON_NUMERIC_OUTCOMES:
            if row["displacement_blocks"] is not None or row["masked_ssim"] is not None:
                raise MeasurementJoinError(
                    f"clip {row['clip_id']!r} is {outcome} but carries a numeric "
                    "measurement; NA is never zero"
                )
            if not row["missing_reason"]:
                raise MeasurementJoinError(
                    f"clip {row['clip_id']!r} is {outcome} without a reason"
                )
        else:
            if row["displacement_blocks"] is None:
                raise MeasurementJoinError(
                    f"measured clip {row['clip_id']!r} carries no displacement"
                )
            for field in REQUIRED_MEASUREMENT_VERSIONS:
                if not row.get(field):
                    raise MeasurementJoinError(
                        f"measured clip {row['clip_id']!r} declares no {field}"
                    )

    if document.get("outcome_counts") != counts:
        raise MeasurementJoinError("outcome_counts do not match the rows")

    expected_complete = (
        counts["missing"] == 0
        and not document.get("identity_conflicts")
        and not document.get("pair_keys_without_measured_baseline")
        and all(
            finding["consistent_across_rows"] and finding["matches_expected"]
            for finding in document.get("version_findings", ())
        )
    )
    if document.get("join_complete") != expected_complete:
        raise MeasurementJoinError(
            "join_complete does not follow from the joined rows; an incomplete "
            "join must never present itself as complete"
        )


def dump_u4_control_matrix(document: Mapping[str, Any]) -> str:
    """Serialize a validated control matrix deterministically."""

    validate_u4_control_matrix(document)
    return json.dumps(document, indent=2, sort_keys=True, default=_json_default) + "\n"


def _json_default(value: Any) -> Any:
    if isinstance(value, tuple):
        return list(value)
    raise TypeError(f"{type(value).__name__} is not JSON serializable")


__all__ = [
    "CLIP_OUTCOMES",
    "CROSS_CHECKED_IDENTITY_FIELDS",
    "NON_NUMERIC_OUTCOMES",
    "REQUIRED_MEASUREMENT_VERSIONS",
    "SCHEMA_ID",
    "SCHEMA_VERSION",
    "MeasurementJoinError",
    "MeasurementRow",
    "dump_u4_control_matrix",
    "join_measurements_to_manifest",
    "validate_u4_control_matrix",
]
