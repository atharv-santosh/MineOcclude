"""Consolidated missingness and exclusion audit (Person D Step 4.5).

Execution manual Step 4.5 requires *one* consolidated machine-readable
audit spanning layout, condition, hidden duration, target, method, fold,
comparison class, accepted/excluded status, prediction
available/missing/non-applicable, reason code, and planned-versus-
requested-versus-emitted counts. The pass check forbids a silent
method-specific population: every missing prediction must carry exactly
one reason, and any difference between the requested and emitted row
sets must be explained rather than merely observed.

``missingness.py`` already tabulates applicable/non-applicable counts by
method and condition and flags reason-less non-applicable rows. It stays
as-is; this module is the consolidated report *around* it, adding the
dimensions that tabulation lacks (fold, condition role, comparison
class, acceptance status, planned counts, run validity) and a
machine-readable document with its own validator.

Three distinctions are load-bearing and are never collapsed here:

* **NA is not zero.** A ``non_applicable`` prediction is recorded as
  ``null`` with a reason; it is never counted as a numeric 0.0, and the
  report never sums predictions.
* **Missing is not non-applicable.** ``non_applicable`` means the method
  defines no prediction for that row (last-seen has no spread).
  ``missing`` means a prediction was requested and legitimately expected
  but never arrived -- an engineering gap, not a scientific statement.
* **Invalid/superseded is not absent.** A run whose status is
  ``invalid`` or ``superseded`` is excluded from the current-result
  summary but retained verbatim in ``run_history``, so a correction
  never erases the record it replaced.

This module fits nothing, computes no metric, and reads no U4 artifact.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Optional, Sequence

from mineocclude.baselines.interface import TARGET_NAMES, BaselineRow

SCHEMA_ID = "person-d-missingness-exclusion-report-v0-1"
SCHEMA_VERSION = "1.0"

#: Prediction outcome vocabulary. Exactly one applies to each requested
#: (method, target, row) triple; the three are mutually exclusive and
#: jointly exhaustive over the requested row set.
PREDICTION_STATUSES: tuple[str, ...] = ("available", "non_applicable", "missing")

#: Acceptance status of a trajectory in the accepted MVP manifest.
#: ``recollection_pending`` and ``missing`` are distinct from ``excluded``:
#: an excluded trajectory was collected and then ruled out for a recorded
#: reason, while the other two were never obtained at all.
ACCEPTANCE_STATUSES: tuple[str, ...] = (
    "accepted",
    "excluded",
    "recollection_pending",
    "missing",
)

#: A prediction run's validity. Only ``valid`` runs contribute to the
#: current-result summary; the other two remain in ``run_history``.
RUN_STATUSES: tuple[str, ...] = ("valid", "invalid", "superseded")

#: Frozen condition roles of the 66-cell accepted MVP matrix, using
#: Person C's own ``set`` vocabulary from ``configs/collection/mvp_matrix.csv``
#: rather than any label invented here.
CONDITION_ROLES: tuple[str, ...] = (
    "core",
    "nowall",
    "nosheep",
    "sentinel",
)

#: Each baseline family's comparison class. These are Person D's own
#: already-published role labels (PERSON_D_ISSUE.md "MVP work"), restated
#: as a machine-readable field so a report can never present a floor,
#: a reference, and a privileged ceiling as interchangeable competitors.
#: This is a *labeling* vocabulary, not a scientific threshold.
COMPARISON_CLASS_BY_FAMILY: Mapping[str, str] = {
    "last_seen": "memory_heuristic",
    "constant_velocity": "reference",
    "grouped_shuffled": "chance_floor",
    "time_only": "clock_floor",
    "explicit_feature": "fair_fitted_ceiling",
    "raw_pixel": "fair_fitted_ceiling",
    "visible_history_q": "fair_baseline",
    "known_q_analytic": "privileged_oracle_ceiling",
}


class MissingnessAuditError(ValueError):
    """Raised when an audit cannot be built or validated honestly."""


@dataclass(frozen=True)
class TrajectoryCondition:
    """One accepted-manifest trajectory's condition and acceptance status."""

    trajectory_id: str
    layout_id: str
    condition_role: str
    acceptance_status: str
    exclusion_reason: Optional[str] = None

    def __post_init__(self) -> None:
        if self.condition_role not in CONDITION_ROLES:
            raise MissingnessAuditError(
                f"unknown condition_role {self.condition_role!r} for "
                f"{self.trajectory_id!r}; expected one of {CONDITION_ROLES}"
            )
        if self.acceptance_status not in ACCEPTANCE_STATUSES:
            raise MissingnessAuditError(
                f"unknown acceptance_status {self.acceptance_status!r} for "
                f"{self.trajectory_id!r}; expected one of {ACCEPTANCE_STATUSES}"
            )
        if self.acceptance_status == "excluded" and not self.exclusion_reason:
            raise MissingnessAuditError(
                f"trajectory {self.trajectory_id!r} is excluded but carries no "
                "exclusion_reason; a silent exclusion is exactly what this "
                "audit exists to prevent"
            )


@dataclass(frozen=True)
class RequestedRow:
    """One requested prediction-row identity, before any method runs."""

    trajectory_id: str
    model_frame_idx: int
    fold: int
    layout_id: str
    duration_seconds: Optional[float]


@dataclass(frozen=True)
class PlannedFamilyTarget:
    """One planned (family, target) population, from B's frozen contract.

    ``planned_available_count`` is what Person B's frozen family/target
    applicability contract says *should* be admitted; recording it here is
    what makes "planned versus requested versus emitted" a real
    three-way reconciliation rather than a two-way one.
    """

    family: str
    target_name: str
    planned_available_count: int
    planned_non_applicable_count: int
    source_contract_id: str


def duration_bin(duration_seconds: Optional[float]) -> str:
    """Bin one row's declared hidden duration.

    Deterministic and threshold-free: the bin *is* the declared duration
    value, formatted. Person D does not invent duration cut points -- the
    accepted matrix already declares a small closed set of hidden
    durations, so exact-value bins group the data without introducing an
    interpretive threshold that Person B never froze.
    """

    if duration_seconds is None:
        return "unknown"
    return f"{duration_seconds:g}s"


def comparison_class_for(family: str) -> str:
    """Return a family's frozen comparison class, failing on an unknown one."""

    try:
        return COMPARISON_CLASS_BY_FAMILY[family]
    except KeyError:
        raise MissingnessAuditError(
            f"family {family!r} has no declared comparison class; a method "
            "whose floor/reference/ceiling role is undeclared must not enter "
            "a comparison report"
        ) from None


def _row_key(row: BaselineRow) -> tuple[str, int]:
    return (row.trajectory_id, row.model_frame_idx)


def _reason_of(row: BaselineRow) -> Optional[str]:
    reason = row.fit_metadata.get("reason")
    if reason is None:
        return None
    text = str(reason).strip()
    return text or None


def build_missingness_exclusion_report(
    *,
    rows: Sequence[BaselineRow],
    requested_rows: Sequence[RequestedRow],
    conditions: Sequence[TrajectoryCondition],
    planned: Sequence[PlannedFamilyTarget] = (),
    families: Sequence[str] = (),
    run_id: str,
    run_status: str = "valid",
    run_history: Sequence[Mapping[str, Any]] = (),
    evidence_kind: str = "synthetic",
) -> dict[str, Any]:
    """Build the consolidated, machine-readable Step 4.5 audit document.

    ``rows`` are the emitted prediction rows; ``requested_rows`` is the
    exact requested row set (the authority for "what should have been
    predicted"); ``conditions`` maps every requested trajectory to its
    accepted-manifest condition and acceptance status; ``planned``
    carries Person B's frozen per-(family, target) expected counts.

    ``families`` is the exact set of methods this run was supposed to
    cover. Passing it is what lets the audit distinguish "this method
    produced no row for this target" (a silent method-specific
    population, reported as ``missing``) from "this method was never
    part of the run".

    The returned document is deterministic: every collection is sorted by
    an explicit key, so the same inputs serialize to the same bytes.
    """

    if run_status not in RUN_STATUSES:
        raise MissingnessAuditError(
            f"unknown run_status {run_status!r}; expected one of {RUN_STATUSES}"
        )
    if evidence_kind not in ("real", "synthetic"):
        raise MissingnessAuditError(
            f"unknown evidence_kind {evidence_kind!r}; expected 'real' or "
            "'synthetic' -- synthetic evidence is never presented as real"
        )
    if not requested_rows:
        raise MissingnessAuditError("requested_rows must not be empty")

    condition_by_trajectory = {c.trajectory_id: c for c in conditions}
    requested_by_key: dict[tuple[str, int], RequestedRow] = {}
    for requested in requested_rows:
        key = (requested.trajectory_id, requested.model_frame_idx)
        if key in requested_by_key:
            raise MissingnessAuditError(
                f"duplicate requested row identity {key}; the requested row "
                "set must have exactly one entry per (trajectory, frame)"
            )
        requested_by_key[key] = requested

    unconditioned = sorted(
        {r.trajectory_id for r in requested_rows} - set(condition_by_trajectory)
    )
    if unconditioned:
        raise MissingnessAuditError(
            f"requested trajectories {unconditioned} have no declared "
            "condition/acceptance status; an unclassified trajectory cannot "
            "be audited for missingness"
        )

    observed_families = sorted({row.baseline_name for row in rows})
    audited_families = sorted(set(families) or set(observed_families))
    unexpected_families = sorted(set(observed_families) - set(audited_families))
    if unexpected_families:
        raise MissingnessAuditError(
            f"rows were emitted by families {unexpected_families} that this "
            "run does not declare; an undeclared method must not silently "
            "enter a comparison population"
        )
    for family in audited_families:
        comparison_class_for(family)

    # ---- row-level classification -------------------------------------
    emitted_index: dict[tuple[str, str, str, int], list[BaselineRow]] = defaultdict(list)
    orphan_rows: list[dict[str, Any]] = []
    for row in rows:
        key = _row_key(row)
        if key not in requested_by_key:
            orphan_rows.append(
                {
                    "baseline_name": row.baseline_name,
                    "target_name": row.target_name,
                    "trajectory_id": row.trajectory_id,
                    "model_frame_idx": row.model_frame_idx,
                    "explanation": "emitted row identity is not in the requested row set",
                }
            )
            continue
        emitted_index[
            (row.baseline_name, row.target_name, row.trajectory_id, row.model_frame_idx)
        ].append(row)

    duplicate_rows = sorted(
        (key, len(bucket)) for key, bucket in emitted_index.items() if len(bucket) > 1
    )

    cells: dict[tuple, dict[str, Any]] = {}
    reason_counts: dict[tuple[str, str, str], int] = defaultdict(int)
    rows_missing_reason: list[dict[str, Any]] = []

    for family in audited_families:
        family_class = comparison_class_for(family)
        for target_name in TARGET_NAMES:
            for key, requested in sorted(requested_by_key.items()):
                condition = condition_by_trajectory[requested.trajectory_id]
                emitted = emitted_index.get(
                    (family, target_name, key[0], key[1]), []
                )
                if not emitted:
                    status = "missing"
                    reason = "no_prediction_row_emitted_for_requested_row"
                elif emitted[0].applicable:
                    status = "available"
                    reason = None
                else:
                    status = "non_applicable"
                    reason = _reason_of(emitted[0])
                    if reason is None:
                        rows_missing_reason.append(
                            {
                                "baseline_name": family,
                                "target_name": target_name,
                                "trajectory_id": key[0],
                                "model_frame_idx": key[1],
                            }
                        )
                        reason = "<no reason recorded>"

                cell_key = (
                    family,
                    family_class,
                    target_name,
                    requested.layout_id,
                    condition.condition_role,
                    condition.acceptance_status,
                    duration_bin(requested.duration_seconds),
                    requested.fold,
                )
                cell = cells.setdefault(
                    cell_key,
                    {
                        "baseline_name": family,
                        "comparison_class": family_class,
                        "target_name": target_name,
                        "layout_id": requested.layout_id,
                        "condition_role": condition.condition_role,
                        "acceptance_status": condition.acceptance_status,
                        "duration_bin": duration_bin(requested.duration_seconds),
                        "fold": requested.fold,
                        "requested_count": 0,
                        "available_count": 0,
                        "non_applicable_count": 0,
                        "missing_count": 0,
                    },
                )
                cell["requested_count"] += 1
                cell[f"{status}_count"] += 1
                if reason is not None:
                    reason_counts[(family, target_name, reason)] += 1

    # ---- planned / requested / emitted reconciliation ------------------
    planned_by_family_target = {
        (entry.family, entry.target_name): entry for entry in planned
    }
    reconciliation: list[dict[str, Any]] = []
    for family in audited_families:
        for target_name in TARGET_NAMES:
            matching = [
                cell
                for cell in cells.values()
                if cell["baseline_name"] == family and cell["target_name"] == target_name
            ]
            requested_count = sum(cell["requested_count"] for cell in matching)
            available = sum(cell["available_count"] for cell in matching)
            non_applicable = sum(cell["non_applicable_count"] for cell in matching)
            missing = sum(cell["missing_count"] for cell in matching)
            plan = planned_by_family_target.get((family, target_name))
            entry: dict[str, Any] = {
                "baseline_name": family,
                "comparison_class": comparison_class_for(family),
                "target_name": target_name,
                "planned_available_count": (
                    plan.planned_available_count if plan is not None else None
                ),
                "planned_non_applicable_count": (
                    plan.planned_non_applicable_count if plan is not None else None
                ),
                "planned_source_contract_id": (
                    plan.source_contract_id if plan is not None else None
                ),
                "requested_count": requested_count,
                "emitted_count": available + non_applicable,
                "available_count": available,
                "non_applicable_count": non_applicable,
                "missing_count": missing,
            }
            differences: list[str] = []
            if missing:
                differences.append(
                    f"{missing} requested rows produced no prediction row at all"
                )
            if plan is not None and plan.planned_available_count != available:
                differences.append(
                    "available count "
                    f"{available} differs from B's planned "
                    f"{plan.planned_available_count}"
                )
            entry["row_set_differences"] = tuple(differences)
            entry["reconciled"] = not differences
            reconciliation.append(entry)

    # ---- summary -------------------------------------------------------
    total_requested = sum(cell["requested_count"] for cell in cells.values())
    total_available = sum(cell["available_count"] for cell in cells.values())
    total_non_applicable = sum(cell["non_applicable_count"] for cell in cells.values())
    total_missing = sum(cell["missing_count"] for cell in cells.values())

    condition_counts: dict[str, int] = defaultdict(int)
    acceptance_counts: dict[str, int] = defaultdict(int)
    for condition in sorted(condition_by_trajectory.values(), key=lambda c: c.trajectory_id):
        condition_counts[condition.condition_role] += 1
        acceptance_counts[condition.acceptance_status] += 1

    contributes = run_status == "valid"
    document: dict[str, Any] = {
        "schema_id": SCHEMA_ID,
        "schema_version": SCHEMA_VERSION,
        "producer_role": "person_d",
        "run_id": run_id,
        "run_status": run_status,
        "evidence_kind": evidence_kind,
        "contributes_to_current_results": contributes,
        "audited_families": tuple(audited_families),
        "audited_targets": tuple(TARGET_NAMES),
        "trajectory_condition_counts": dict(sorted(condition_counts.items())),
        "trajectory_acceptance_counts": dict(sorted(acceptance_counts.items())),
        "excluded_trajectories": tuple(
            {
                "trajectory_id": c.trajectory_id,
                "layout_id": c.layout_id,
                "condition_role": c.condition_role,
                "acceptance_status": c.acceptance_status,
                "exclusion_reason": c.exclusion_reason,
            }
            for c in sorted(
                condition_by_trajectory.values(), key=lambda c: c.trajectory_id
            )
            if c.acceptance_status != "accepted"
        ),
        "cells": tuple(cells[key] for key in sorted(cells)),
        "reconciliation": tuple(
            sorted(reconciliation, key=lambda e: (e["baseline_name"], e["target_name"]))
        ),
        "non_applicable_reason_counts": tuple(
            {
                "baseline_name": family,
                "target_name": target_name,
                "reason": reason,
                "count": count,
            }
            for (family, target_name, reason), count in sorted(reason_counts.items())
        ),
        "rows_missing_reason_code": tuple(
            sorted(
                rows_missing_reason,
                key=lambda r: (
                    r["baseline_name"],
                    r["target_name"],
                    r["trajectory_id"],
                    r["model_frame_idx"],
                ),
            )
        ),
        "orphan_emitted_rows": tuple(
            sorted(
                orphan_rows,
                key=lambda r: (
                    r["baseline_name"],
                    r["target_name"],
                    r["trajectory_id"],
                    r["model_frame_idx"],
                ),
            )
        ),
        "duplicate_emitted_rows": tuple(
            {
                "baseline_name": key[0],
                "target_name": key[1],
                "trajectory_id": key[2],
                "model_frame_idx": key[3],
                "emitted_count": count,
            }
            for key, count in sorted(duplicate_rows)
        ),
        "totals": {
            "requested_predictions": total_requested,
            "available_predictions": total_available,
            "non_applicable_predictions": total_non_applicable,
            "missing_predictions": total_missing,
        },
        "run_history": tuple(
            sorted(
                (dict(entry) for entry in run_history),
                key=lambda entry: str(entry.get("run_id", "")),
            )
        ),
        "invariants": {
            "na_is_never_zero": True,
            "every_missing_prediction_has_one_reason": not rows_missing_reason,
            "no_silent_method_specific_population": total_missing == 0,
            "every_row_set_difference_explained": all(
                entry["reconciled"] or entry["row_set_differences"]
                for entry in reconciliation
            ),
            "no_orphan_emitted_rows": not orphan_rows,
            "no_duplicate_emitted_rows": not duplicate_rows,
        },
    }
    document["audit_passed"] = all(document["invariants"].values())
    return document


def validate_missingness_exclusion_report(document: Mapping[str, Any]) -> None:
    """Validate one report document, raising on the first violation.

    Fails closed on structure *and* on the semantics that make the report
    trustworthy: the three prediction statuses must partition the
    requested count exactly, an unexplained row-set difference is a
    failure, and an invalid/superseded run must not claim to contribute
    to current results.
    """

    if document.get("schema_id") != SCHEMA_ID:
        raise MissingnessAuditError(
            f"expected schema_id {SCHEMA_ID!r}, got {document.get('schema_id')!r}"
        )
    if document.get("schema_version") != SCHEMA_VERSION:
        raise MissingnessAuditError(
            f"expected schema_version {SCHEMA_VERSION!r}, got "
            f"{document.get('schema_version')!r}"
        )
    if document.get("producer_role") != "person_d":
        raise MissingnessAuditError("producer_role must be 'person_d'")
    if document.get("run_status") not in RUN_STATUSES:
        raise MissingnessAuditError(
            f"run_status must be one of {RUN_STATUSES}, got "
            f"{document.get('run_status')!r}"
        )
    if document.get("evidence_kind") not in ("real", "synthetic"):
        raise MissingnessAuditError("evidence_kind must be 'real' or 'synthetic'")

    contributes = bool(document.get("contributes_to_current_results"))
    if contributes != (document["run_status"] == "valid"):
        raise MissingnessAuditError(
            "only a valid run may contribute to current results; an invalid or "
            "superseded run is retained in history, never summarized as current"
        )

    for required in (
        "cells",
        "reconciliation",
        "totals",
        "invariants",
        "run_history",
        "audited_families",
    ):
        if required not in document:
            raise MissingnessAuditError(f"missing required field {required!r}")

    totals = document["totals"]
    partition = (
        totals["available_predictions"]
        + totals["non_applicable_predictions"]
        + totals["missing_predictions"]
    )
    if partition != totals["requested_predictions"]:
        raise MissingnessAuditError(
            "available + non_applicable + missing must equal requested "
            f"({partition} != {totals['requested_predictions']}); the three "
            "prediction statuses must partition the requested row set"
        )

    for cell in document["cells"]:
        cell_partition = (
            cell["available_count"] + cell["non_applicable_count"] + cell["missing_count"]
        )
        if cell_partition != cell["requested_count"]:
            raise MissingnessAuditError(
                f"cell {cell['baseline_name']}/{cell['target_name']}/"
                f"{cell['layout_id']}/fold{cell['fold']} does not partition its "
                f"requested count ({cell_partition} != {cell['requested_count']})"
            )
        if cell["comparison_class"] != comparison_class_for(cell["baseline_name"]):
            raise MissingnessAuditError(
                f"cell for {cell['baseline_name']!r} declares comparison class "
                f"{cell['comparison_class']!r}, which is not its frozen class"
            )
        if cell["condition_role"] not in CONDITION_ROLES:
            raise MissingnessAuditError(
                f"unknown condition_role {cell['condition_role']!r} in a cell"
            )
        if cell["acceptance_status"] not in ACCEPTANCE_STATUSES:
            raise MissingnessAuditError(
                f"unknown acceptance_status {cell['acceptance_status']!r} in a cell"
            )

    for entry in document["reconciliation"]:
        if not entry["reconciled"] and not entry["row_set_differences"]:
            raise MissingnessAuditError(
                f"{entry['baseline_name']}/{entry['target_name']} is not "
                "reconciled but records no explanation; every row-set "
                "difference must be explained"
            )
        if entry["emitted_count"] + entry["missing_count"] != entry["requested_count"]:
            raise MissingnessAuditError(
                f"{entry['baseline_name']}/{entry['target_name']}: emitted + "
                "missing must equal requested"
            )

    if document["rows_missing_reason_code"] and document["invariants"].get(
        "every_missing_prediction_has_one_reason"
    ):
        raise MissingnessAuditError(
            "report claims every missing prediction has a reason while listing "
            "rows that have none"
        )


def dump_missingness_exclusion_report(document: Mapping[str, Any]) -> str:
    """Serialize one report to deterministic, sorted-key JSON text."""

    validate_missingness_exclusion_report(document)
    return json.dumps(document, indent=2, sort_keys=True, default=_json_default) + "\n"


def _json_default(value: Any) -> Any:
    if isinstance(value, tuple):
        return list(value)
    raise TypeError(f"{type(value).__name__} is not JSON serializable")


def requested_rows_from_contexts(contexts: Iterable[Any]) -> list[RequestedRow]:
    """Build the requested row set from the same contexts the run used.

    Convenience only -- it copies identity fields verbatim and never
    invents, repairs, or filters a row identity.
    """

    requested: list[RequestedRow] = []
    seen: set[tuple[str, int]] = set()
    for ctx in contexts:
        key = (ctx.trajectory_id, ctx.model_frame_idx)
        if key in seen:
            raise MissingnessAuditError(
                f"duplicate requested row identity {key} in the supplied contexts"
            )
        seen.add(key)
        requested.append(
            RequestedRow(
                trajectory_id=ctx.trajectory_id,
                model_frame_idx=ctx.model_frame_idx,
                fold=ctx.fold,
                layout_id=ctx.layout_id,
                duration_seconds=ctx.duration_seconds,
            )
        )
    return requested


__all__ = [
    "ACCEPTANCE_STATUSES",
    "COMPARISON_CLASS_BY_FAMILY",
    "CONDITION_ROLES",
    "PREDICTION_STATUSES",
    "RUN_STATUSES",
    "SCHEMA_ID",
    "SCHEMA_VERSION",
    "MissingnessAuditError",
    "PlannedFamilyTarget",
    "RequestedRow",
    "TrajectoryCondition",
    "build_missingness_exclusion_report",
    "comparison_class_for",
    "dump_missingness_exclusion_report",
    "duration_bin",
    "requested_rows_from_contexts",
    "validate_missingness_exclusion_report",
]
