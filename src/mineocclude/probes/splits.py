"""Deterministic layout-grouped fold assignment for Person B analyses."""

from __future__ import annotations

import hashlib
from collections import Counter
from collections.abc import Iterable, Mapping
from typing import Any

from mineocclude.analysis.config import DEFAULT_SPLIT_SEED


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
