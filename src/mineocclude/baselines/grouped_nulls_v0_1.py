"""Grouped nulls and paired comparison rows (Person D Step 6.3).

Execution manual Step 6.3 requires grouped null generation using
*explicit donor identities*, Person B's frozen resampling unit,
per-trajectory paired comparison rows carrying exact method / fold /
target / row / seed / metric identity, identical row-set enforcement
across paired methods, preserved non-applicable and missing reasons,
deterministic regeneration, duplicate and cardinality checks, and
machine-readable schemas for both outputs.

Person B owns the inference. This module never computes a p-value, a
confidence interval, or a decision -- it *constructs and validates the
row-level inputs* those computations consume, and refuses to emit a
comparison whose two sides do not score the identical requested rows.
Every frozen inferential constant below is copied from Person B's own
``person-b-step4-1-final-comparison-contract-v0-1`` package and is cited
as such; none of it is a Person D judgment call.

Donor identity comes from :mod:`mineocclude.baselines.shuffled` --
the same validated, seeded, trajectory-level derangement the Step 2.1
floor uses, never a fresh row-level shuffle. Reusing it is the point:
the null in a comparison must be the null the floor already published.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence

from mineocclude.baselines.interface import BaselineRow
from mineocclude.baselines.missingness_audit_v0_1 import comparison_class_for
from mineocclude.baselines.shuffled import build_donor_assignments

GROUPED_NULLS_SCHEMA_ID = "person-d-grouped-nulls-v0-1"
PAIRED_COMPARISONS_SCHEMA_ID = "person-d-paired-comparisons-v0-1"
SCHEMA_VERSION = "1.0"

#: Person B's frozen inferential specification, copied verbatim from
#: ``docs/status/person_b_phase4_step4_1_final_comparison_contract_v0_1/
#: final_comparison_contract.json`` on ``role/person-b-analysis``. Person D
#: consumes these; it never redefines or reinterprets them.
PERSON_B_FINAL_COMPARISON_CONTRACT_ID = "person-b-step4-1-final-comparison-contract-v0-1"
FROZEN_RESAMPLING_UNIT = "whole_trajectory_pair_with_one_shared_sign_per_layout"
FROZEN_PERMUTATION_COUNT = 999
FROZEN_PERMUTATION_SEED = 20260720
FROZEN_SIDEDNESS = "one_sided_in_predeclared_improvement_direction"
FROZEN_NULL_HYPOTHESIS = "layout-macro paired improvement is less than or equal to zero"
FROZEN_ROW_LEVEL_PAIRING_KEYS: tuple[str, ...] = (
    "trajectory_id",
    "model_frame_idx",
    "fold_idx",
    "target_name",
)
FROZEN_WEIGHTING_RULE = "equal_layout_then_equal_trajectory_then_equal_row"
FROZEN_SAMPLE_UNIT = "whole_trajectory"

#: Frozen per-target loss identity (``metric_contract`` in the same
#: package). Recorded on every paired row so a downstream table can never
#: silently compare a blocks-space loss to a log-space one.
FROZEN_LOSS_BY_TARGET: Mapping[str, str] = {
    "mu_oracle_blocks": "squared_error_in_blocks",
    "log_sigma_oracle": "squared_error_in_log_sigma",
}
FROZEN_POSITIVE_DIRECTION = "probe_better"

#: The frozen U1/U2 comparison sets: which baseline each objective is
#: compared against. Copied from ``acceptance_contract.scientific_gates``.
FROZEN_OBJECTIVE_BASELINES: Mapping[str, tuple[str, ...]] = {
    "U1": ("last_seen", "grouped_shuffled"),
    "U2": ("time_only", "visible_history_q"),
}


class GroupedNullError(ValueError):
    """Raised when a null or paired comparison cannot be built honestly."""


@dataclass(frozen=True)
class PairedRow:
    """One row-level paired observation, before any aggregation.

    ``loss_a``/``loss_b`` are ``None`` whenever the corresponding side is
    non-applicable or missing; a paired row with a ``None`` on either
    side is *not* scored and carries an explicit reason. It is never
    coerced to zero, dropped silently, or imputed.
    """

    trajectory_id: str
    layout_id: str
    model_frame_idx: int
    fold_idx: int
    target_name: str
    method_a: str
    method_b: str
    comparison_class_a: str
    comparison_class_b: str
    prediction_a: Optional[float]
    prediction_b: Optional[float]
    status_a: str
    status_b: str
    reason_a: Optional[str]
    reason_b: Optional[str]
    scored: bool
    unscored_reason: Optional[str]


def _row_status(row: Optional[BaselineRow]) -> tuple[str, Optional[str]]:
    if row is None:
        return "missing", "no_prediction_row_emitted_for_requested_row"
    if row.applicable:
        return "available", None
    reason = row.fit_metadata.get("reason")
    text = str(reason).strip() if reason is not None else ""
    return "non_applicable", text or "<no reason recorded>"


def _index_rows(rows: Sequence[BaselineRow]) -> dict[tuple[str, str, int, str], BaselineRow]:
    index: dict[tuple[str, str, int, str], BaselineRow] = {}
    for row in rows:
        key = (row.baseline_name, row.trajectory_id, row.model_frame_idx, row.target_name)
        if key in index:
            raise GroupedNullError(
                f"duplicate prediction row {key}; a method must emit exactly one "
                "prediction per (trajectory, frame, target)"
            )
        index[key] = row
    return index


# --------------------------------------------------------------------------
# Grouped nulls
# --------------------------------------------------------------------------


def build_grouped_null_document(
    *,
    contexts: Sequence[Any],
    trajectory_targets: Mapping[str, Mapping[str, Mapping[int, Optional[float]]]],
    null_rows: Sequence[BaselineRow],
    seed: int = FROZEN_PERMUTATION_SEED,
    run_id: str,
    evidence_kind: str = "synthetic",
    require_cross_group_donors: bool = False,
) -> dict[str, Any]:
    """Build the machine-readable grouped-null document.

    The donor mapping is recomputed here through the same validated
    :func:`~mineocclude.baselines.shuffled.build_donor_assignments` path
    the emitted ``null_rows`` were produced by, then checked against what
    those rows actually claim. A disagreement means the published null is
    not the null the rows were built from, which fails closed.
    """

    if evidence_kind not in ("real", "synthetic"):
        raise GroupedNullError("evidence_kind must be 'real' or 'synthetic'")

    assignments = build_donor_assignments(
        contexts,
        trajectory_targets,
        seed,
        require_cross_group_donors=require_cross_group_donors,
    )

    for row in null_rows:
        declared = row.fit_metadata.get("donor_trajectory_id")
        expected = assignments[row.trajectory_id].donor_trajectory_id
        if declared != expected:
            raise GroupedNullError(
                f"null row for {row.trajectory_id!r} frame {row.model_frame_idx} "
                f"records donor {declared!r} but the seeded derangement for seed "
                f"{seed} assigns {expected!r}; the published null must be the "
                "null the rows were generated from"
            )
        if row.fit_metadata.get("seed") != seed:
            raise GroupedNullError(
                f"null row for {row.trajectory_id!r} records seed "
                f"{row.fit_metadata.get('seed')!r}, not the document's {seed}"
            )

    layout_by_trajectory: dict[str, str] = {}
    fold_by_trajectory: dict[str, int] = {}
    for ctx in contexts:
        layout_by_trajectory[ctx.trajectory_id] = ctx.layout_id
        fold_by_trajectory[ctx.trajectory_id] = ctx.fold

    status_counts: dict[str, int] = defaultdict(int)
    for row in null_rows:
        status, _ = _row_status(row)
        status_counts[status] += 1

    return {
        "schema_id": GROUPED_NULLS_SCHEMA_ID,
        "schema_version": SCHEMA_VERSION,
        "producer_role": "person_d",
        "run_id": run_id,
        "evidence_kind": evidence_kind,
        "null_family": "grouped_shuffled",
        "grouping_unit": "trajectory_id",
        "alignment_key": "model_frame_idx",
        "requires_derangement": True,
        "cross_group_donors_required": require_cross_group_donors,
        "seed": seed,
        "person_b_contract_id": PERSON_B_FINAL_COMPARISON_CONTRACT_ID,
        "resampling_unit": FROZEN_RESAMPLING_UNIT,
        "permutation_count": FROZEN_PERMUTATION_COUNT,
        "sidedness": FROZEN_SIDEDNESS,
        "null_hypothesis": FROZEN_NULL_HYPOTHESIS,
        "donor_assignments": tuple(
            {
                "recipient_trajectory_id": assignment.recipient_trajectory_id,
                "donor_trajectory_id": assignment.donor_trajectory_id,
                "recipient_group_key": assignment.recipient_group_key,
                "donor_group_key": assignment.donor_group_key,
                "recipient_layout_id": layout_by_trajectory.get(
                    assignment.recipient_trajectory_id
                ),
                "recipient_fold_idx": fold_by_trajectory.get(
                    assignment.recipient_trajectory_id
                ),
            }
            for _, assignment in sorted(assignments.items())
        ),
        "trajectory_count": len(assignments),
        "null_row_count": len(null_rows),
        "row_status_counts": dict(sorted(status_counts.items())),
    }


def validate_grouped_null_document(document: Mapping[str, Any]) -> None:
    """Validate a grouped-null document, raising on the first violation."""

    if document.get("schema_id") != GROUPED_NULLS_SCHEMA_ID:
        raise GroupedNullError(
            f"expected schema_id {GROUPED_NULLS_SCHEMA_ID!r}, got "
            f"{document.get('schema_id')!r}"
        )
    if document.get("resampling_unit") != FROZEN_RESAMPLING_UNIT:
        raise GroupedNullError(
            "resampling_unit must be Person B's frozen "
            f"{FROZEN_RESAMPLING_UNIT!r}, got {document.get('resampling_unit')!r}"
        )
    if document.get("permutation_count") != FROZEN_PERMUTATION_COUNT:
        raise GroupedNullError(
            f"permutation_count must be {FROZEN_PERMUTATION_COUNT}, got "
            f"{document.get('permutation_count')!r}"
        )
    if document.get("grouping_unit") != "trajectory_id":
        raise GroupedNullError("grouping_unit must be 'trajectory_id'")
    if not document.get("requires_derangement"):
        raise GroupedNullError("requires_derangement must be true")
    if document.get("evidence_kind") not in ("real", "synthetic"):
        raise GroupedNullError("evidence_kind must be 'real' or 'synthetic'")

    assignments = document.get("donor_assignments") or ()
    recipients = [entry["recipient_trajectory_id"] for entry in assignments]
    donors = [entry["donor_trajectory_id"] for entry in assignments]
    if len(set(recipients)) != len(recipients):
        raise GroupedNullError("a recipient trajectory appears more than once")
    if len(set(donors)) != len(donors):
        raise GroupedNullError(
            "a donor trajectory is reused; the derangement must be a bijection"
        )
    if set(recipients) != set(donors):
        raise GroupedNullError(
            "the donor set must be a permutation of the recipient set"
        )
    for entry in assignments:
        if entry["recipient_trajectory_id"] == entry["donor_trajectory_id"]:
            raise GroupedNullError(
                f"{entry['recipient_trajectory_id']!r} is its own donor"
            )
    if document.get("trajectory_count") != len(assignments):
        raise GroupedNullError("trajectory_count does not match donor_assignments")


# --------------------------------------------------------------------------
# Paired comparisons
# --------------------------------------------------------------------------


def build_paired_rows(
    *,
    rows_a: Sequence[BaselineRow],
    rows_b: Sequence[BaselineRow],
    method_a: str,
    method_b: str,
    requested_keys: Sequence[tuple[str, int, str]],
) -> list[PairedRow]:
    """Pair two methods row-by-row over the exact requested row set.

    ``requested_keys`` are ``(trajectory_id, model_frame_idx,
    target_name)`` triples -- the authority for what both sides were
    asked to predict. Pairing is done on B's frozen row-level pairing
    keys, never on list order, and a row present on only one side becomes
    an explicitly unscored pair rather than a silently dropped one.
    """

    index_a = _index_rows(rows_a)
    index_b = _index_rows(rows_b)

    foreign_a = sorted({name for name, *_ in index_a} - {method_a})
    foreign_b = sorted({name for name, *_ in index_b} - {method_b})
    if foreign_a or foreign_b:
        raise GroupedNullError(
            f"rows for {method_a!r}/{method_b!r} contain foreign methods "
            f"{foreign_a + foreign_b}; each side must contain exactly one method"
        )

    identity_by_key: dict[tuple[str, int, str], BaselineRow] = {}
    for row in list(rows_a) + list(rows_b):
        identity_by_key.setdefault(
            (row.trajectory_id, row.model_frame_idx, row.target_name), row
        )

    class_a = comparison_class_for(method_a)
    class_b = comparison_class_for(method_b)

    paired: list[PairedRow] = []
    seen: set[tuple[str, int, str]] = set()
    for key in requested_keys:
        if key in seen:
            raise GroupedNullError(f"duplicate requested pairing key {key}")
        seen.add(key)
        trajectory_id, model_frame_idx, target_name = key
        if target_name not in FROZEN_LOSS_BY_TARGET:
            raise GroupedNullError(
                f"unknown target {target_name!r}; expected one of "
                f"{sorted(FROZEN_LOSS_BY_TARGET)}"
            )
        row_a = index_a.get((method_a, trajectory_id, model_frame_idx, target_name))
        row_b = index_b.get((method_b, trajectory_id, model_frame_idx, target_name))
        identity_row = row_a or row_b or identity_by_key.get(key)
        if identity_row is None:
            raise GroupedNullError(
                f"requested pair {key} has no row on either side and no known "
                "layout/fold identity; a pair cannot be manufactured from "
                "nothing"
            )

        status_a, reason_a = _row_status(row_a)
        status_b, reason_b = _row_status(row_b)
        scored = status_a == "available" and status_b == "available"
        unscored_reason = None
        if not scored:
            unscored_reason = (
                f"{method_a}={status_a}"
                if status_a != "available"
                else f"{method_b}={status_b}"
            )

        paired.append(
            PairedRow(
                trajectory_id=trajectory_id,
                layout_id=identity_row.layout_id,
                model_frame_idx=model_frame_idx,
                fold_idx=identity_row.fold,
                target_name=target_name,
                method_a=method_a,
                method_b=method_b,
                comparison_class_a=class_a,
                comparison_class_b=class_b,
                prediction_a=row_a.prediction if row_a is not None else None,
                prediction_b=row_b.prediction if row_b is not None else None,
                status_a=status_a,
                status_b=status_b,
                reason_a=reason_a,
                reason_b=reason_b,
                scored=scored,
                unscored_reason=unscored_reason,
            )
        )
    return paired


def build_paired_comparison_document(
    *,
    paired_rows: Sequence[PairedRow],
    objective: str,
    run_id: str,
    metric_id: str,
    evidence_kind: str = "synthetic",
    seed: int = FROZEN_PERMUTATION_SEED,
) -> dict[str, Any]:
    """Build the machine-readable paired-comparison document.

    Enforces identical row-set coverage: the two sides must have been
    *asked* the same questions. Rows where either side is non-applicable
    or missing stay in the document, unscored and with a reason, so a
    later reader can see exactly which rows the inference did and did not
    consume.
    """

    if evidence_kind not in ("real", "synthetic"):
        raise GroupedNullError("evidence_kind must be 'real' or 'synthetic'")
    if not paired_rows:
        raise GroupedNullError("paired_rows must not be empty")

    methods = {(row.method_a, row.method_b) for row in paired_rows}
    if len(methods) != 1:
        raise GroupedNullError(
            f"a paired-comparison document covers exactly one method pair, got "
            f"{sorted(methods)}"
        )
    method_a, method_b = methods.pop()

    targets = sorted({row.target_name for row in paired_rows})
    losses = sorted({FROZEN_LOSS_BY_TARGET[row.target_name] for row in paired_rows})
    if len(losses) != 1:
        raise GroupedNullError(
            f"a paired-comparison document must use one loss identity, got "
            f"{losses} across targets {targets}; mu and log-sigma are never "
            "combined"
        )

    keys = [
        (row.trajectory_id, row.model_frame_idx, row.target_name) for row in paired_rows
    ]
    if len(set(keys)) != len(keys):
        raise GroupedNullError("duplicate paired row identity in paired_rows")

    scored = [row for row in paired_rows if row.scored]
    unscored = [row for row in paired_rows if not row.scored]
    trajectories = sorted({row.trajectory_id for row in paired_rows})
    layouts = sorted({row.layout_id for row in paired_rows})

    return {
        "schema_id": PAIRED_COMPARISONS_SCHEMA_ID,
        "schema_version": SCHEMA_VERSION,
        "producer_role": "person_d",
        "run_id": run_id,
        "evidence_kind": evidence_kind,
        "objective": objective,
        "metric_id": metric_id,
        "method_a": method_a,
        "method_b": method_b,
        "comparison_class_a": comparison_class_for(method_a),
        "comparison_class_b": comparison_class_for(method_b),
        "target_names": tuple(targets),
        "loss_identity": losses[0],
        "positive_direction": FROZEN_POSITIVE_DIRECTION,
        "person_b_contract_id": PERSON_B_FINAL_COMPARISON_CONTRACT_ID,
        "row_level_pairing_keys": FROZEN_ROW_LEVEL_PAIRING_KEYS,
        "resampling_unit": FROZEN_RESAMPLING_UNIT,
        "sample_unit": FROZEN_SAMPLE_UNIT,
        "weighting_rule": FROZEN_WEIGHTING_RULE,
        "permutation_count": FROZEN_PERMUTATION_COUNT,
        "seed": seed,
        "sidedness": FROZEN_SIDEDNESS,
        "null_hypothesis": FROZEN_NULL_HYPOTHESIS,
        "requested_pair_count": len(paired_rows),
        "scored_pair_count": len(scored),
        "unscored_pair_count": len(unscored),
        "trajectory_count": len(trajectories),
        "layout_count": len(layouts),
        "trajectory_ids": tuple(trajectories),
        "layout_ids": tuple(layouts),
        "rows": tuple(
            {
                "trajectory_id": row.trajectory_id,
                "layout_id": row.layout_id,
                "model_frame_idx": row.model_frame_idx,
                "fold_idx": row.fold_idx,
                "target_name": row.target_name,
                "prediction_a": row.prediction_a,
                "prediction_b": row.prediction_b,
                "status_a": row.status_a,
                "status_b": row.status_b,
                "reason_a": row.reason_a,
                "reason_b": row.reason_b,
                "scored": row.scored,
                "unscored_reason": row.unscored_reason,
            }
            for row in sorted(
                paired_rows,
                key=lambda r: (r.target_name, r.trajectory_id, r.model_frame_idx),
            )
        ),
        "unscored_reason_counts": _count_unscored_reasons(unscored),
        "identical_row_sets": True,
    }


def _count_unscored_reasons(rows: Sequence[PairedRow]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for row in rows:
        counts[str(row.unscored_reason)] += 1
    return dict(sorted(counts.items()))


def validate_paired_comparison_document(document: Mapping[str, Any]) -> None:
    """Validate a paired-comparison document, raising on the first violation."""

    if document.get("schema_id") != PAIRED_COMPARISONS_SCHEMA_ID:
        raise GroupedNullError(
            f"expected schema_id {PAIRED_COMPARISONS_SCHEMA_ID!r}, got "
            f"{document.get('schema_id')!r}"
        )
    if document.get("resampling_unit") != FROZEN_RESAMPLING_UNIT:
        raise GroupedNullError(
            "resampling_unit must be Person B's frozen "
            f"{FROZEN_RESAMPLING_UNIT!r}"
        )
    if tuple(document.get("row_level_pairing_keys") or ()) != FROZEN_ROW_LEVEL_PAIRING_KEYS:
        raise GroupedNullError(
            "row_level_pairing_keys must be Person B's frozen "
            f"{FROZEN_ROW_LEVEL_PAIRING_KEYS}"
        )
    if document.get("evidence_kind") not in ("real", "synthetic"):
        raise GroupedNullError("evidence_kind must be 'real' or 'synthetic'")

    rows = document.get("rows") or ()
    if not rows:
        raise GroupedNullError("a paired-comparison document must contain rows")

    keys = [
        (row["trajectory_id"], row["model_frame_idx"], row["target_name"]) for row in rows
    ]
    if len(set(keys)) != len(keys):
        raise GroupedNullError("duplicate paired row identity")
    if document.get("requested_pair_count") != len(rows):
        raise GroupedNullError("requested_pair_count does not match the row count")

    scored = sum(1 for row in rows if row["scored"])
    unscored = len(rows) - scored
    if document.get("scored_pair_count") != scored:
        raise GroupedNullError("scored_pair_count does not match the rows")
    if document.get("unscored_pair_count") != unscored:
        raise GroupedNullError("unscored_pair_count does not match the rows")

    for row in rows:
        for side in ("a", "b"):
            status = row[f"status_{side}"]
            prediction = row[f"prediction_{side}"]
            reason = row[f"reason_{side}"]
            if status not in ("available", "non_applicable", "missing"):
                raise GroupedNullError(f"unknown status_{side} {status!r}")
            if status == "available":
                if prediction is None:
                    raise GroupedNullError(
                        f"available side {side} carries no prediction for "
                        f"{row['trajectory_id']}/{row['model_frame_idx']}"
                    )
            else:
                if prediction is not None:
                    raise GroupedNullError(
                        f"side {side} is {status} but carries prediction "
                        f"{prediction!r}; NA is never a number"
                    )
                if not reason:
                    raise GroupedNullError(
                        f"side {side} is {status} without a reason for "
                        f"{row['trajectory_id']}/{row['model_frame_idx']}"
                    )
        if row["scored"] != (row["status_a"] == "available" and row["status_b"] == "available"):
            raise GroupedNullError(
                f"row {row['trajectory_id']}/{row['model_frame_idx']} disagrees "
                "with its own scored flag"
            )
        if not row["scored"] and not row["unscored_reason"]:
            raise GroupedNullError(
                f"unscored row {row['trajectory_id']}/{row['model_frame_idx']} "
                "carries no reason"
            )

    losses = {FROZEN_LOSS_BY_TARGET[row["target_name"]] for row in rows}
    if len(losses) != 1 or document.get("loss_identity") not in losses:
        raise GroupedNullError(
            "a paired-comparison document must declare exactly one loss "
            "identity matching its rows"
        )


def dump_document(document: Mapping[str, Any]) -> str:
    """Serialize a grouped-null or paired-comparison document deterministically."""

    schema_id = document.get("schema_id")
    if schema_id == GROUPED_NULLS_SCHEMA_ID:
        validate_grouped_null_document(document)
    elif schema_id == PAIRED_COMPARISONS_SCHEMA_ID:
        validate_paired_comparison_document(document)
    else:
        raise GroupedNullError(f"unknown schema_id {schema_id!r}")
    return json.dumps(document, indent=2, sort_keys=True, default=_json_default) + "\n"


def _json_default(value: Any) -> Any:
    if isinstance(value, tuple):
        return list(value)
    raise TypeError(f"{type(value).__name__} is not JSON serializable")


__all__ = [
    "FROZEN_LOSS_BY_TARGET",
    "FROZEN_OBJECTIVE_BASELINES",
    "FROZEN_PERMUTATION_COUNT",
    "FROZEN_PERMUTATION_SEED",
    "FROZEN_RESAMPLING_UNIT",
    "FROZEN_ROW_LEVEL_PAIRING_KEYS",
    "GROUPED_NULLS_SCHEMA_ID",
    "PAIRED_COMPARISONS_SCHEMA_ID",
    "PERSON_B_FINAL_COMPARISON_CONTRACT_ID",
    "SCHEMA_VERSION",
    "GroupedNullError",
    "PairedRow",
    "build_grouped_null_document",
    "build_paired_comparison_document",
    "build_paired_rows",
    "dump_document",
    "validate_grouped_null_document",
    "validate_paired_comparison_document",
]
