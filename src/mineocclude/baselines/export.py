"""Package baseline predictions into B's frozen consumer contract.

Every baseline module in this package produces a list of
:class:`~mineocclude.baselines.interface.BaselineRow`. Before those rows
mean anything to Person B, they must be shaped into one
``person-b-baseline-input-v0.1`` document per (baseline, target) pair
and pass B's real validator, ``mineocclude.contracts.analysis_inputs
.validate_baseline_input`` -- not a paraphrase of it. This module is the
only place that shape conversion happens, so every baseline stays
honest about the same handoff format.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Mapping, Optional, Sequence

from mineocclude.analysis.manifests import is_hex_digest
from mineocclude.baselines.interface import BaselineRow, TargetName, TrajectoryContext
from mineocclude.contracts.analysis_inputs import (
    AnalysisInputValidationResult,
    validate_baseline_input,
)
from mineocclude.contracts.identity import SCHEMA_VERSION
from mineocclude.probes.splits import assign_layout_grouped_folds

BASELINE_INPUT_SCHEMA_VERSION = "person-b-baseline-input-v0.1"
PRODUCER_ROLE = "person_d"

FrameKey = tuple[str, int]


class BaselineExportError(ValueError):
    """Raised when a baseline document cannot be honestly constructed."""


def attach_b_fold_assignments(
    contexts: Sequence[TrajectoryContext],
    *,
    n_splits: int = 5,
    seed: int = 20260719,
) -> list[TrajectoryContext]:
    """Return contexts with ``fold`` set from B's layout-grouped algorithm.

    Roadmap D1.1 / D2 Day 2: "Read B's exact fold assignments... never
    create a separate favorable split." This calls B's own
    ``assign_layout_grouped_folds`` (the same function B's frozen
    ``configs/analysis/core.yaml`` seed/fold-count drive) rather than
    reimplementing grouping logic, so any context set folds identically
    to B given the same accepted rows. When a real persisted
    ``fold_manifest`` artifact exists, prefer reading it directly
    (``mineocclude.probes.splits.validate_fold_manifest``) over
    recomputing; this helper is the offline/synthetic equivalent for
    contexts that do not yet have one.
    """

    rows = [
        {
            "trajectory_id": ctx.trajectory_id,
            "layout_id": ctx.layout_id,
            "model_frame_idx": ctx.model_frame_idx,
        }
        for ctx in contexts
    ]
    fold_by_layout = assign_layout_grouped_folds(rows, n_splits=n_splits, seed=seed)
    return [replace(ctx, fold=fold_by_layout[ctx.layout_id]) for ctx in contexts]


def build_baseline_document(
    rows: Sequence[BaselineRow],
    *,
    target_name: TargetName,
    baseline_id: str,
    baseline_family: str,
    config_hash: str,
    input_manifest_hash: str,
    fold_manifest_hash: str,
    fit_manifest_hash: str,
    fit_id_by_key: Optional[Mapping[FrameKey, str]] = None,
    default_fit_id: Optional[str] = None,
) -> dict[str, object]:
    """Build one ``person-b-baseline-input-v0.1`` document for one target.

    Only rows where ``target_name`` matches and ``applicable`` is true
    become prediction rows -- a baseline that cannot define a value for
    a frame omits that key rather than submitting a fabricated
    prediction (BaselineRow.__post_init__ already forbids a
    non-applicable row from carrying a numeric value). Whether the
    resulting key set exactly covers B's accepted/eligible frames is
    B's call, checked by passing ``expected_fold_by_frame`` to
    :func:`validate_document`; this function only shapes the document.
    """

    if fit_id_by_key is None and default_fit_id is None:
        raise BaselineExportError(
            "either fit_id_by_key or default_fit_id must be supplied"
        )
    for name, value in (
        ("config_hash", config_hash),
        ("input_manifest_hash", input_manifest_hash),
        ("fold_manifest_hash", fold_manifest_hash),
        ("fit_manifest_hash", fit_manifest_hash),
    ):
        if not is_hex_digest(value, 64):
            raise BaselineExportError(f"{name} must be a SHA-256 hex digest.")

    prediction_rows: list[dict[str, object]] = []
    seen_keys: set[FrameKey] = set()
    for row in rows:
        if row.target_name != target_name or not row.applicable:
            continue
        key = (row.trajectory_id, row.model_frame_idx)
        if key in seen_keys:
            raise BaselineExportError(f"duplicate baseline prediction for {key}")
        seen_keys.add(key)

        fit_id = (fit_id_by_key or {}).get(key, default_fit_id)
        if fit_id is None:
            raise BaselineExportError(f"no fit_id available for row {key}")

        prediction_rows.append(
            {
                "trajectory_id": row.trajectory_id,
                "model_frame_idx": row.model_frame_idx,
                "fold_idx": row.fold,
                "prediction": row.prediction,
                "prediction_scope": "out_of_fold",
                "fit_id": fit_id,
            }
        )

    if not prediction_rows:
        raise BaselineExportError(
            f"no applicable {target_name!r} rows for baseline {baseline_id!r}; "
            "an empty document cannot pass B's non-empty-rows requirement"
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "baseline_input_schema_version": BASELINE_INPUT_SCHEMA_VERSION,
        "producer_role": PRODUCER_ROLE,
        "baseline_id": baseline_id,
        "baseline_family": baseline_family,
        "target_name": target_name,
        "config_hash": config_hash,
        "input_manifest_hash": input_manifest_hash,
        "fold_manifest_hash": fold_manifest_hash,
        "fit_manifest_hash": fit_manifest_hash,
        "rows": prediction_rows,
    }


def validate_document(
    document: Mapping[str, object],
    *,
    expected_fold_by_frame: Optional[Mapping[FrameKey, int]] = None,
) -> AnalysisInputValidationResult:
    """Validate a baseline document against B's real consumer contract.

    Thin wrapper kept so every caller in this package validates through
    one place rather than re-importing B's contract module directly.
    """

    return validate_baseline_input(
        document, expected_fold_by_frame=expected_fold_by_frame
    )
