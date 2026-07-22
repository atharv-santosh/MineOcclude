"""Deterministic layout-grouped fold assignment for Person B analyses."""

from __future__ import annotations

import hashlib
from collections import Counter
from collections.abc import Iterable, Mapping
from typing import Any

from mineocclude.analysis.config import DEFAULT_SPLIT_SEED
from mineocclude.analysis.manifests import (
    AnalysisArtifactError,
    seal_artifact,
    validate_sealed_artifact,
)


FOLD_SCHEMA_VERSION = "person-b-fold-v0.1"
U4_PARTITION_SCHEMA_VERSION = "person-b-u4-partition-v0.1"


class GroupedSplitError(ValueError):
    """Raised when leakage-safe grouped folds cannot be constructed."""


def _tie_breaker(seed: int, layout_id: str) -> str:
    return hashlib.sha256(f"{seed}:{layout_id}".encode("utf-8")).hexdigest()


def _validate_rows(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    materialized: list[dict[str, Any]] = []
    seen_frames: set[tuple[str, int]] = set()
    layout_by_trajectory: dict[str, str] = {}

    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise GroupedSplitError(f"Row {index} must be a mapping.")

        layout_id = row.get("layout_id")
        trajectory_id = row.get("trajectory_id")
        model_frame_idx = row.get("model_frame_idx")
        if not isinstance(layout_id, str) or not layout_id.strip():
            raise GroupedSplitError("Every row requires a non-empty layout_id.")
        if not isinstance(trajectory_id, str) or not trajectory_id.strip():
            raise GroupedSplitError("Every row requires a non-empty trajectory_id.")
        if (
            not isinstance(model_frame_idx, int)
            or isinstance(model_frame_idx, bool)
            or model_frame_idx < 0
        ):
            raise GroupedSplitError(
                "Every row requires a non-negative integer model_frame_idx."
            )
        if "status" in row and row["status"] != "accepted":
            raise GroupedSplitError("Only accepted rows may receive analysis folds.")

        frame_key = (trajectory_id, model_frame_idx)
        if frame_key in seen_frames:
            raise GroupedSplitError(f"Duplicate model-frame identity: {frame_key}.")
        seen_frames.add(frame_key)

        existing_layout = layout_by_trajectory.setdefault(trajectory_id, layout_id)
        if existing_layout != layout_id:
            raise GroupedSplitError(
                f"Trajectory {trajectory_id!r} appears in multiple layouts."
            )
        materialized.append(dict(row))

    return materialized


def _assign_validated_rows(
    rows: list[dict[str, Any]],
    *,
    n_splits: int,
    seed: int,
) -> dict[str, int]:
    counts = Counter(row["layout_id"] for row in rows)
    if len(counts) < n_splits:
        raise GroupedSplitError(
            f"Need at least {n_splits} layouts, received {len(counts)}."
        )

    layouts = sorted(
        counts,
        key=lambda layout: (-counts[layout], _tie_breaker(seed, layout)),
    )
    fold_loads = [0] * n_splits
    assignment: dict[str, int] = {}
    for layout in layouts:
        fold = min(range(n_splits), key=lambda index: (fold_loads[index], index))
        assignment[layout] = fold
        fold_loads[fold] += counts[layout]
    return assignment


def assign_layout_grouped_folds(
    rows: Iterable[Mapping[str, Any]],
    *,
    n_splits: int = 5,
    seed: int = DEFAULT_SPLIT_SEED,
) -> dict[str, int]:
    """Assign accepted, unique model frames to layout-grouped folds."""

    if not isinstance(n_splits, int) or isinstance(n_splits, bool) or n_splits < 2:
        raise GroupedSplitError("n_splits must be an integer of at least two.")
    if not isinstance(seed, int) or isinstance(seed, bool):
        raise GroupedSplitError("seed must be an integer.")

    materialized = _validate_rows(rows)
    return _assign_validated_rows(materialized, n_splits=n_splits, seed=seed)


def annotate_grouped_folds(
    rows: Iterable[Mapping[str, Any]],
    *,
    n_splits: int = 5,
    seed: int = DEFAULT_SPLIT_SEED,
) -> list[dict[str, Any]]:
    """Return copied rows with a new or matching persisted ``fold_idx``."""

    if not isinstance(n_splits, int) or isinstance(n_splits, bool) or n_splits < 2:
        raise GroupedSplitError("n_splits must be an integer of at least two.")
    if not isinstance(seed, int) or isinstance(seed, bool):
        raise GroupedSplitError("seed must be an integer.")

    materialized = _validate_rows(rows)
    assignment = _assign_validated_rows(
        materialized,
        n_splits=n_splits,
        seed=seed,
    )
    annotated: list[dict[str, Any]] = []
    for row in materialized:
        expected_fold = assignment[row["layout_id"]]
        if "fold_idx" in row:
            existing_fold = row["fold_idx"]
            if (
                not isinstance(existing_fold, int)
                or isinstance(existing_fold, bool)
                or existing_fold != expected_fold
            ):
                raise GroupedSplitError(
                    "Existing fold_idx conflicts with the frozen layout assignment."
                )
        row["fold_idx"] = expected_fold
        annotated.append(row)
    return annotated


def build_grouped_inner_folds(
    rows: Iterable[Mapping[str, Any]],
    *,
    outer_fold_idx: int,
    n_splits: int = 4,
    seed: int = DEFAULT_SPLIT_SEED,
) -> list[dict[str, Any]]:
    """Assign inner folds using only the outer-training layouts."""

    if (
        not isinstance(outer_fold_idx, int)
        or isinstance(outer_fold_idx, bool)
        or outer_fold_idx < 0
    ):
        raise GroupedSplitError("outer_fold_idx must be a non-negative integer.")
    materialized = _validate_rows(rows)
    if not materialized or any("fold_idx" not in row for row in materialized):
        raise GroupedSplitError("Outer fold membership must be present on every row.")
    layout_fold: dict[str, int] = {}
    for row in materialized:
        fold_idx = row["fold_idx"]
        if (
            not isinstance(fold_idx, int)
            or isinstance(fold_idx, bool)
            or fold_idx < 0
        ):
            raise GroupedSplitError("Every outer fold index must be non-negative.")
        previous = layout_fold.setdefault(row["layout_id"], fold_idx)
        if previous != fold_idx:
            raise GroupedSplitError("One layout appears in multiple outer folds.")
    if not any(row["fold_idx"] == outer_fold_idx for row in materialized):
        raise GroupedSplitError("outer_fold_idx is absent from the fold membership.")
    training_rows = [
        row for row in materialized if row["fold_idx"] != outer_fold_idx
    ]
    if not training_rows:
        raise GroupedSplitError("Outer fold leaves no training rows.")
    assignments = assign_layout_grouped_folds(
        training_rows,
        n_splits=n_splits,
        seed=seed + outer_fold_idx,
    )
    annotated: list[dict[str, Any]] = []
    for row in training_rows:
        row["inner_fold_idx"] = assignments[row["layout_id"]]
        annotated.append(row)
    return annotated


def build_fold_manifest(
    rows: Iterable[Mapping[str, Any]],
    *,
    artifact_id: str,
    code_sha: str,
    config_hash: str,
    input_manifest_hash: str,
    n_splits: int = 5,
    seed: int = DEFAULT_SPLIT_SEED,
) -> dict[str, Any]:
    """Persist exact frame membership and provenance for grouped folds."""

    annotated = annotate_grouped_folds(rows, n_splits=n_splits, seed=seed)
    memberships = [
        {
            "trajectory_id": row["trajectory_id"],
            "model_frame_idx": row["model_frame_idx"],
            "layout_id": row["layout_id"],
            "fold_idx": row["fold_idx"],
        }
        for row in sorted(
            annotated,
            key=lambda item: (
                item["layout_id"],
                item["trajectory_id"],
                item["model_frame_idx"],
            ),
        )
    ]
    layout_assignments = sorted(
        (
            {"layout_id": layout_id, "fold_idx": fold_idx}
            for layout_id, fold_idx in assign_layout_grouped_folds(
                annotated,
                n_splits=n_splits,
                seed=seed,
            ).items()
        ),
        key=lambda item: item["layout_id"],
    )
    return seal_artifact(
        {
            "artifact_type": "fold_manifest",
            "artifact_id": artifact_id,
            "code_sha": code_sha,
            "config_hash": config_hash,
            "input_manifest_hash": input_manifest_hash,
            "fold_schema_version": FOLD_SCHEMA_VERSION,
            "strategy": "layout_grouped",
            "n_splits": n_splits,
            "seed": seed,
            "layout_assignments": layout_assignments,
            "memberships": memberships,
        }
    )


def validate_fold_manifest(document: Mapping[str, Any]) -> None:
    """Reject altered, incomplete, or layout-leaking fold manifests."""

    try:
        validate_sealed_artifact(document, expected_type="fold_manifest")
    except AnalysisArtifactError as error:
        raise GroupedSplitError(f"Invalid fold artifact: {error}") from error
    if document.get("fold_schema_version") != FOLD_SCHEMA_VERSION:
        raise GroupedSplitError("Fold schema version mismatch.")
    n_splits = document.get("n_splits")
    if not isinstance(n_splits, int) or isinstance(n_splits, bool) or n_splits < 2:
        raise GroupedSplitError("Fold manifest n_splits is invalid.")
    memberships = document.get("memberships")
    if not isinstance(memberships, list) or not memberships:
        raise GroupedSplitError("Fold manifest requires frame memberships.")
    layout_fold: dict[str, int] = {}
    seen_frames: set[tuple[str, int]] = set()
    validated_memberships = _validate_rows(memberships)
    for row in validated_memberships:
        required = ("trajectory_id", "model_frame_idx", "layout_id", "fold_idx")
        if any(field not in row for field in required):
            raise GroupedSplitError("Fold membership is missing required fields.")
        fold_idx = row["fold_idx"]
        if (
            not isinstance(fold_idx, int)
            or isinstance(fold_idx, bool)
            or not 0 <= fold_idx < n_splits
        ):
            raise GroupedSplitError("Fold membership index is invalid.")
        frame = (row["trajectory_id"], row["model_frame_idx"])
        if frame in seen_frames:
            raise GroupedSplitError(f"Duplicate fold membership: {frame}.")
        seen_frames.add(frame)
        previous = layout_fold.setdefault(row["layout_id"], fold_idx)
        if previous != fold_idx:
            raise GroupedSplitError("One layout appears in multiple folds.")
    declared = document.get("layout_assignments")
    expected = sorted(
        (
            {"layout_id": layout_id, "fold_idx": fold_idx}
            for layout_id, fold_idx in layout_fold.items()
        ),
        key=lambda item: item["layout_id"],
    )
    if declared != expected:
        raise GroupedSplitError("layout_assignments do not match frame memberships.")
    if set(layout_fold.values()) != set(range(n_splits)):
        raise GroupedSplitError("Fold manifest does not populate every fold index.")
    if document.get("strategy") != "layout_grouped":
        raise GroupedSplitError("Fold manifest strategy is not layout_grouped.")
    if not isinstance(document.get("seed"), int) or isinstance(document.get("seed"), bool):
        raise GroupedSplitError("Fold manifest seed must be an integer.")


def assign_u4_development_partition(
    layout_ids: Iterable[str],
    *,
    seed: int = DEFAULT_SPLIT_SEED,
) -> dict[str, str]:
    """Create the predeclared 3-fit/1-validation/2-test layout partition.

    Only layout identity and the frozen seed affect membership; outcomes and
    intervention measurements are deliberately absent from the interface.
    """

    if not isinstance(seed, int) or isinstance(seed, bool):
        raise GroupedSplitError("seed must be an integer.")
    materialized = list(layout_ids)
    if any(not isinstance(value, str) or not value for value in materialized):
        raise GroupedSplitError("Every U4 layout ID must be a non-empty string.")
    unique = sorted(set(materialized))
    if len(unique) != 6:
        raise GroupedSplitError(
            "The fixed U4 development partition requires exactly six layout IDs."
        )
    ordered = sorted(unique, key=lambda layout_id: _tie_breaker(seed, layout_id))
    return {
        layout_id: (
            "fit" if index < 3 else "validation" if index == 3 else "test"
        )
        for index, layout_id in enumerate(ordered)
    }


def build_u4_partition_manifest(
    layout_ids: Iterable[str],
    *,
    artifact_id: str,
    code_sha: str,
    config_hash: str,
    input_manifest_hash: str,
    seed: int = DEFAULT_SPLIT_SEED,
) -> dict[str, Any]:
    """Persist the exact outcome-independent U4 development membership."""

    assignments = assign_u4_development_partition(layout_ids, seed=seed)
    return seal_artifact(
        {
            "artifact_type": "u4_partition_manifest",
            "artifact_id": artifact_id,
            "code_sha": code_sha,
            "config_hash": config_hash,
            "input_manifest_hash": input_manifest_hash,
            "u4_partition_schema_version": U4_PARTITION_SCHEMA_VERSION,
            "seed": seed,
            "selection_source": "layout_manifest_only",
            "layout_assignments": [
                {"layout_id": layout_id, "partition": partition}
                for layout_id, partition in sorted(assignments.items())
            ],
        }
    )


def validate_u4_partition_manifest(document: Mapping[str, Any]) -> None:
    """Reject altered or incorrectly sized U4 development partitions."""

    try:
        validate_sealed_artifact(document, expected_type="u4_partition_manifest")
    except AnalysisArtifactError as error:
        raise GroupedSplitError(f"Invalid U4 partition artifact: {error}") from error
    if document.get("u4_partition_schema_version") != U4_PARTITION_SCHEMA_VERSION:
        raise GroupedSplitError("U4 partition schema version mismatch.")
    if document.get("selection_source") != "layout_manifest_only":
        raise GroupedSplitError("U4 partition must use layout identity only.")
    seed = document.get("seed")
    if not isinstance(seed, int) or isinstance(seed, bool):
        raise GroupedSplitError("U4 partition seed must be an integer.")
    declared = document.get("layout_assignments")
    if not isinstance(declared, list) or len(declared) != 6:
        raise GroupedSplitError("U4 partition requires exactly six layouts.")
    layout_ids: list[str] = []
    observed: dict[str, str] = {}
    for row in declared:
        if not isinstance(row, Mapping):
            raise GroupedSplitError("U4 partition rows must be mappings.")
        layout_id = row.get("layout_id")
        partition = row.get("partition")
        if (
            not isinstance(layout_id, str)
            or not layout_id
            or not isinstance(partition, str)
            or partition not in {"fit", "validation", "test"}
            or layout_id in observed
        ):
            raise GroupedSplitError("U4 partition membership is invalid.")
        layout_ids.append(layout_id)
        observed[layout_id] = partition
    expected = assign_u4_development_partition(layout_ids, seed=seed)
    if observed != expected:
        raise GroupedSplitError(
            "U4 partition membership differs from the frozen algorithm."
        )
