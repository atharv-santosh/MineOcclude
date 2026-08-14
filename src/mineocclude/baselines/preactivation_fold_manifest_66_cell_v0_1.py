"""Person D support for Person B's real 66-cell pre-activation fold manifest.

Person B's real builder/validator module
(``mineocclude.analysis.preactivation_66_cell_v0_1``) lives only on
``role/person-b-analysis`` at commit
``PERSON_B_PREACTIVATION_COMMIT`` and has not been merged onto this
branch. This module is Person D's own, independent verification of that
exact real document, built by reading that commit's Git objects
directly (never executed, never imported, never merged). Every frozen
constant and check below is copied or re-derived from that exact
commit; if Person B's fold manifest is ever revised, these must be
re-read from the new authoritative commit, never edited from local
judgment.

## Why the historical validator cannot validate this document

``mineocclude.probes.splits.validate_fold_manifest`` requires
``expected_type="fold_manifest"`` and recomputes the layout-to-fold
assignment from *only* the accepted memberships. This real document
declares ``artifact_type="person_b_66_cell_fold_manifest"`` (a real,
later schema evolution, not a defect), and -- verified directly, not
assumed -- recomputing from the 984 accepted rows alone cannot
reproduce the declared assignment: Person B's admission policy
deliberately balances every layout to exactly 164 admitted rows, so a
recomputation keyed on admitted-row counts alone has no distinct counts
to break ties with. Person B's own builder
(``build_66_cell_fold_manifest``) computes the assignment from *every*
model-frame row (984 accepted + 1,484 excluded = 2,468), via the same
shared, already-tested :func:`mineocclude.probes.splits
.assign_layout_grouped_folds` D's historical validator itself calls --
just over the full row set, not the admitted subset. Reproduced here
and verified to match exactly.

## Why ``export.attach_b_fold_assignments`` cannot attach from this document

That function requires the fold manifest's ``memberships`` to be
*exactly* the submitted row set. This document's ``memberships``
legitimately contains all 2,468 model-frame rows (each carrying a
``status`` field), because Person B's own fold-assignment computation
needs the excluded rows present. A caller submitting only its own
admitted rows -- e.g. the 351 real no-wall rows the Step 4.3 gate
needs -- is a legitimate subset, not a coverage mismatch, so
:func:`attach_66_cell_fold_assignments` below requires subset coverage
(every submitted key must be present and declared ``accepted``)
instead of exact-set coverage.

This module never fits a baseline, never computes a metric, and never
reads a U4 artifact. It only validates a fold manifest already claiming
to be this exact real format and attaches its real fold assignments to
Person D's own submitted rows.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import Any

from mineocclude.analysis.config import (
    hash_core_analysis_config,
    load_core_analysis_config,
)
from mineocclude.analysis.manifests import (
    AnalysisArtifactError,
    validate_sealed_artifact,
)
from mineocclude.baselines.interface import TrajectoryContext
from mineocclude.probes.splits import (
    ANALYSIS_CONFIG_VERSION,
    FOLD_SCHEMA_VERSION,
    GroupedSplitError,
    assign_layout_grouped_folds,
)

FrameKey = tuple[str, int]


class PreactivationFoldManifestError(ValueError):
    """Raised when the real 66-cell fold manifest does not validate honestly."""


#: Person B's real 66-cell pre-activation builder commit -- the sole
#: authority for every frozen constant in this module.
PERSON_B_PREACTIVATION_COMMIT = "3678cc90c583877d330c01807fe11d393902d146"
PERSON_B_PREACTIVATION_MODULE_PATH = "src/mineocclude/analysis/preactivation_66_cell_v0_1.py"
PERSON_B_PREACTIVATION_SOURCE_BRANCH = "role/person-b-analysis"

FROZEN_FOLD_ARTIFACT_TYPE = "person_b_66_cell_fold_manifest"
FROZEN_FOLD_MANIFEST_SCHEMA_VERSION = "person-b-66-cell-fold-manifest-v0.1"
FROZEN_PREACTIVATION_SCHEMA_VERSION = "person-b-66-cell-preactivation-v0.1"
FROZEN_ASSIGNMENT_SOURCE = "frozen_layout_grouped_policy_applied_to_66_cell_universe"

FROZEN_FOLD_MANIFEST_PATH = "docs/status/person_b_66_cell_preactivation_v0_1/fold_manifest.json"
FROZEN_FOLD_MANIFEST_SHA256 = (
    "86739975882f4926c3398d5bfa21611daf06c579b3893809eb385e8dcd03001d"
)

REQUIRED_MEMBERSHIP_STATUSES = ("accepted", "excluded")
REQUIRED_MEMBERSHIP_FIELDS = (
    "trajectory_id",
    "model_frame_idx",
    "layout_id",
    "fold_idx",
    "status",
    "exclusion_reason",
    "analysis_scopes",
    "admission_stratum",
)


def _fail(message: str) -> None:
    raise PreactivationFoldManifestError(message)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def validate_66_cell_fold_manifest_document(document: Mapping[str, Any]) -> None:
    """Validate the real 66-cell fold manifest's structure and assignment.

    Mirrors ``mineocclude.analysis.preactivation_66_cell_v0_1
    .build_66_cell_fold_manifest``'s own invariants at commit 3678cc9,
    reusing the same shared, already-tested
    ``mineocclude.probes.splits.assign_layout_grouped_folds`` rather
    than reimplementing fold assignment.
    """

    if not isinstance(document, Mapping):
        _fail("66-cell fold manifest must be an object.")
    try:
        validate_sealed_artifact(document, expected_type=FROZEN_FOLD_ARTIFACT_TYPE)
    except AnalysisArtifactError as error:
        raise PreactivationFoldManifestError(
            f"66-cell fold manifest artifact seal is invalid: {error}"
        ) from error

    frozen_cv = load_core_analysis_config()["cross_validation"]
    expected_fields = {
        "fold_manifest_schema_version": FROZEN_FOLD_MANIFEST_SCHEMA_VERSION,
        "preactivation_schema_version": FROZEN_PREACTIVATION_SCHEMA_VERSION,
        "fold_schema_version": FOLD_SCHEMA_VERSION,
        "analysis_config_version": ANALYSIS_CONFIG_VERSION,
        "config_hash": hash_core_analysis_config(),
        "strategy": "layout_grouped",
        "assignment_source": FROZEN_ASSIGNMENT_SOURCE,
        "random_split_used": False,
        "row_order_has_scientific_meaning": False,
        "row_order_dependence_checked": True,
        "grouping_policy_changed_after_results": False,
        "synthetic": False,
        "scientific_use": "permitted",
    }
    for field, expected in expected_fields.items():
        if document.get(field) != expected:
            _fail(f"66-cell fold manifest field {field!r} changed.")

    n_splits = document.get("n_splits")
    seed = document.get("seed")
    if n_splits != frozen_cv["fold_count"]:
        _fail("66-cell fold manifest n_splits disagrees with the frozen config.")
    if seed != frozen_cv["split_seed"] or document.get("fold_seed") != seed:
        _fail("66-cell fold manifest seed disagrees with the frozen config.")
    if frozen_cv["strategy"] != "layout_grouped":
        _fail("Frozen cross-validation strategy is no longer layout_grouped.")

    memberships = document.get("memberships")
    if not isinstance(memberships, list) or not memberships:
        _fail("66-cell fold manifest requires membership rows.")
    if document.get("model_frame_key_count") != len(memberships):
        _fail("66-cell fold manifest model_frame_key_count disagrees with memberships.")

    seen_keys: set[FrameKey] = set()
    status_counts: Counter = Counter()
    for row in memberships:
        if not isinstance(row, Mapping):
            _fail("66-cell fold membership row is not an object.")
        missing = [field for field in REQUIRED_MEMBERSHIP_FIELDS if field not in row]
        if missing:
            _fail(f"66-cell fold membership is missing required fields: {missing}.")
        if row["status"] not in REQUIRED_MEMBERSHIP_STATUSES:
            _fail(f"66-cell fold membership has unknown status {row['status']!r}.")
        if row["status"] == "excluded" and not row["exclusion_reason"]:
            _fail("66-cell fold membership is excluded but carries no exclusion_reason.")
        if row["status"] == "accepted" and row["exclusion_reason"] is not None:
            _fail("66-cell fold membership is accepted but carries an exclusion_reason.")
        key = (row["trajectory_id"], row["model_frame_idx"])
        if key in seen_keys:
            _fail(f"66-cell fold manifest has a duplicate model-frame key: {key}.")
        seen_keys.add(key)
        status_counts[row["status"]] += 1

    if status_counts["accepted"] != document.get("admitted_analysis_row_count"):
        _fail("66-cell fold manifest admitted_analysis_row_count disagrees with memberships.")
    if status_counts["excluded"] != document.get("excluded_analysis_row_count"):
        _fail("66-cell fold manifest excluded_analysis_row_count disagrees with memberships.")

    assignment_rows = [
        {
            "trajectory_id": row["trajectory_id"],
            "model_frame_idx": row["model_frame_idx"],
            "layout_id": row["layout_id"],
        }
        for row in memberships
    ]
    try:
        recomputed_assignment = assign_layout_grouped_folds(
            assignment_rows, n_splits=n_splits, seed=seed
        )
    except GroupedSplitError as error:
        raise PreactivationFoldManifestError(
            f"could not recompute the 66-cell layout-grouped fold assignment: {error}"
        ) from error

    declared_assignment = {}
    for entry in document.get("layout_assignments") or ():
        if not isinstance(entry, Mapping) or "layout_id" not in entry or "fold_idx" not in entry:
            _fail("66-cell fold manifest layout_assignments entry is malformed.")
        declared_assignment[entry["layout_id"]] = entry["fold_idx"]
    if declared_assignment != recomputed_assignment:
        _fail(
            "66-cell fold manifest layout_assignments do not match the "
            "recomputed layout-grouped assignment over the full row set."
        )

    for row in memberships:
        if row["fold_idx"] != recomputed_assignment[row["layout_id"]]:
            _fail(
                f"66-cell fold membership fold_idx for {row['trajectory_id']!r} "
                "disagrees with its layout's assignment."
            )

    rows_by_fold: Counter = Counter(row["fold_idx"] for row in memberships)
    admitted_by_fold: Counter = Counter(
        row["fold_idx"] for row in memberships if row["status"] == "accepted"
    )
    excluded_by_fold: Counter = Counter(
        row["fold_idx"] for row in memberships if row["status"] == "excluded"
    )
    trajectories_by_fold: dict[int, set[str]] = defaultdict(set)
    layouts_by_fold: dict[int, set[str]] = defaultdict(set)
    for row in memberships:
        trajectories_by_fold[row["fold_idx"]].add(row["trajectory_id"])
        layouts_by_fold[row["fold_idx"]].add(row["layout_id"])

    expected_row_counts_by_fold = [
        {
            "fold_idx": fold_idx,
            "model_frame_row_count": rows_by_fold[fold_idx],
            "admitted_row_count": admitted_by_fold[fold_idx],
            "excluded_row_count": excluded_by_fold[fold_idx],
        }
        for fold_idx in sorted(rows_by_fold)
    ]
    if document.get("row_counts_by_fold") != expected_row_counts_by_fold:
        _fail("66-cell fold manifest row_counts_by_fold disagrees with memberships.")

    expected_trajectory_counts_by_fold = [
        {
            "fold_idx": fold_idx,
            "trajectory_count": len(trajectories_by_fold[fold_idx]),
            "trajectory_ids": sorted(trajectories_by_fold[fold_idx]),
        }
        for fold_idx in sorted(trajectories_by_fold)
    ]
    if document.get("trajectory_counts_by_fold") != expected_trajectory_counts_by_fold:
        _fail("66-cell fold manifest trajectory_counts_by_fold disagrees with memberships.")

    expected_layout_counts_by_fold = [
        {
            "fold_idx": fold_idx,
            "layout_count": len(layouts_by_fold[fold_idx]),
            "layout_ids": sorted(layouts_by_fold[fold_idx]),
        }
        for fold_idx in sorted(layouts_by_fold)
    ]
    if document.get("layout_counts_by_fold") != expected_layout_counts_by_fold:
        _fail("66-cell fold manifest layout_counts_by_fold disagrees with memberships.")

    if set(recomputed_assignment.values()) != set(range(n_splits)):
        _fail("66-cell fold manifest does not populate every frozen fold index.")


def validate_66_cell_fold_manifest_bytes(payload: bytes) -> Mapping[str, Any]:
    """Validate the literal frozen manifest bytes, then its document semantics."""

    if not isinstance(payload, bytes):
        _fail("66-cell fold manifest payload must be bytes.")
    if _sha256(payload) != FROZEN_FOLD_MANIFEST_SHA256:
        _fail("66-cell fold manifest literal SHA-256 changed.")
    try:
        document = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PreactivationFoldManifestError(
            "66-cell fold manifest payload is not strict UTF-8 JSON."
        ) from error
    validate_66_cell_fold_manifest_document(document)
    return document


def attach_66_cell_fold_assignments(
    contexts: Sequence[TrajectoryContext],
    *,
    fold_manifest: Mapping[str, Any],
) -> list[TrajectoryContext]:
    """Attach real fold assignments from the real 66-cell fold manifest.

    Unlike :func:`mineocclude.baselines.export.attach_b_fold_assignments`
    (built for a manifest whose ``memberships`` is exactly the submitted
    row set), this requires only that every submitted context's key be
    present in the manifest and declared ``accepted`` -- the manifest
    itself legitimately covers more rows (982 excluded ones) than any
    one caller submits. A context whose key is absent, or present but
    declared ``excluded``, fails closed rather than silently receiving
    a fold.
    """

    validate_66_cell_fold_manifest_document(fold_manifest)

    membership_by_key: dict[FrameKey, Mapping[str, Any]] = {}
    for row in fold_manifest["memberships"]:
        membership_by_key[(row["trajectory_id"], row["model_frame_idx"])] = row

    annotated: list[TrajectoryContext] = []
    seen: set[FrameKey] = set()
    for context in contexts:
        key = (context.trajectory_id, context.model_frame_idx)
        if key in seen:
            _fail(f"duplicate requested row {key}")
        seen.add(key)

        membership = membership_by_key.get(key)
        if membership is None:
            _fail(f"{key} is not covered by the real 66-cell fold manifest")
        if membership["status"] != "accepted":
            _fail(
                f"{key} is declared {membership['status']!r} by Person B's real "
                "fold manifest, not accepted; a baseline may not run on an "
                "excluded row"
            )
        if membership["layout_id"] != context.layout_id:
            _fail(f"layout identity for {key} disagrees with the real fold manifest")
        authoritative_fold = membership["fold_idx"]
        if context.fold not in (-1, authoritative_fold):
            _fail(f"existing fold for {key} conflicts with the real fold manifest")
        annotated.append(replace(context, fold=authoritative_fold))
    return annotated


__all__ = [
    "FROZEN_FOLD_ARTIFACT_TYPE",
    "FROZEN_FOLD_MANIFEST_PATH",
    "FROZEN_FOLD_MANIFEST_SCHEMA_VERSION",
    "FROZEN_FOLD_MANIFEST_SHA256",
    "FROZEN_PREACTIVATION_SCHEMA_VERSION",
    "PERSON_B_PREACTIVATION_COMMIT",
    "PERSON_B_PREACTIVATION_MODULE_PATH",
    "PERSON_B_PREACTIVATION_SOURCE_BRANCH",
    "PreactivationFoldManifestError",
    "attach_66_cell_fold_assignments",
    "validate_66_cell_fold_manifest_bytes",
    "validate_66_cell_fold_manifest_document",
]
