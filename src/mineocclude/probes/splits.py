"""Deterministic layout-grouped fold assignment for Person B analyses."""

from __future__ import annotations

import hashlib
from collections import Counter
from collections.abc import Iterable, Mapping
from typing import Any

from mineocclude.analysis.config import (
    ANALYSIS_CONFIG_VERSION,
    DEFAULT_SPLIT_SEED,
    hash_core_analysis_config,
    load_core_analysis_config,
)
from mineocclude.analysis.manifests import (
    AnalysisArtifactError,
    is_hex_digest,
    seal_artifact,
    validate_sealed_artifact,
)

FOLD_SCHEMA_VERSION = "person-b-fold-v0.1"
TEN_PILOT_FRAME_FOLD_FORMAT_VERSION = "person-b-ten-pilot-frame-fold-v0.1"
U4_PARTITION_SCHEMA_VERSION = "person-b-u4-partition-v0.1"


class GroupedSplitError(ValueError):
    """Raised when leakage-safe grouped folds cannot be constructed."""


def _tie_breaker(seed: int, layout_id: str) -> str:
    return hashlib.sha256(f"{seed}:{layout_id}".encode()).hexdigest()


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
    config_hash: str | None = None,
    input_manifest_hash: str,
    n_splits: int = 5,
    seed: int = DEFAULT_SPLIT_SEED,
) -> dict[str, Any]:
    """Persist exact frame membership and provenance for grouped folds."""

    frozen_config = load_core_analysis_config()
    frozen_cv = frozen_config["cross_validation"]
    expected_config_hash = hash_core_analysis_config()
    if config_hash is not None and config_hash != expected_config_hash:
        raise GroupedSplitError(
            "Fold config_hash does not match the literal frozen analysis config."
        )
    if (
        n_splits != frozen_cv["fold_count"]
        or seed != frozen_cv["split_seed"]
        or frozen_cv["strategy"] != "layout_grouped"
        or frozen_cv["fold_schema_version"] != FOLD_SCHEMA_VERSION
    ):
        raise GroupedSplitError(
            "Fold count, seed, strategy, or version disagrees with the frozen config."
        )

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
            "config_hash": expected_config_hash,
            "input_manifest_hash": input_manifest_hash,
            "analysis_config_version": ANALYSIS_CONFIG_VERSION,
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

    production_format = document.get("fold_manifest_format_version")
    if production_format is not None:
        if production_format != TEN_PILOT_FRAME_FOLD_FORMAT_VERSION:
            raise GroupedSplitError("Unknown production fold manifest format.")
        _validate_ten_pilot_frame_fold_manifest(document)
        return

    try:
        validate_sealed_artifact(document, expected_type="fold_manifest")
    except AnalysisArtifactError as error:
        raise GroupedSplitError(f"Invalid fold artifact: {error}") from error
    if document.get("fold_schema_version") != FOLD_SCHEMA_VERSION:
        raise GroupedSplitError("Fold schema version mismatch.")
    frozen_config = load_core_analysis_config()
    frozen_cv = frozen_config["cross_validation"]
    if document.get("config_hash") != hash_core_analysis_config():
        raise GroupedSplitError(
            "Fold config hash does not match the literal frozen analysis config."
        )
    if document.get("analysis_config_version") != ANALYSIS_CONFIG_VERSION:
        raise GroupedSplitError("Fold analysis config version mismatch.")
    n_splits = document.get("n_splits")
    if not isinstance(n_splits, int) or isinstance(n_splits, bool) or n_splits < 2:
        raise GroupedSplitError("Fold manifest n_splits is invalid.")
    if n_splits != frozen_cv["fold_count"]:
        raise GroupedSplitError("Fold count disagrees with the frozen config.")
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
    seed = document.get("seed")
    if not isinstance(seed, int) or isinstance(seed, bool):
        raise GroupedSplitError("Fold manifest seed must be an integer.")
    if seed != frozen_cv["split_seed"]:
        raise GroupedSplitError("Fold seed disagrees with the frozen config.")
    expected_layout_fold = _assign_validated_rows(
        validated_memberships,
        n_splits=n_splits,
        seed=seed,
    )
    if layout_fold != expected_layout_fold:
        raise GroupedSplitError(
            "Fold memberships differ from the deterministic seeded assignment."
        )
    expected = sorted(
        (
            {"layout_id": layout_id, "fold_idx": fold_idx}
            for layout_id, fold_idx in expected_layout_fold.items()
        ),
        key=lambda item: item["layout_id"],
    )
    if declared != expected:
        raise GroupedSplitError("layout_assignments do not match frame memberships.")
    if set(layout_fold.values()) != set(range(n_splits)):
        raise GroupedSplitError("Fold manifest does not populate every fold index.")
    if document.get("strategy") != "layout_grouped":
        raise GroupedSplitError("Fold manifest strategy is not layout_grouped.")
    if document.get("strategy") != frozen_cv["strategy"]:
        raise GroupedSplitError("Fold strategy disagrees with the frozen config.")


def _validate_ten_pilot_frame_fold_manifest(document: Mapping[str, Any]) -> None:
    """Validate the sealed ten-pilot subset without rebalancing frozen folds."""

    try:
        validate_sealed_artifact(document, expected_type="fold_manifest")
    except AnalysisArtifactError as error:
        raise GroupedSplitError(f"Invalid production fold artifact: {error}") from error
    if document.get("fold_schema_version") != FOLD_SCHEMA_VERSION:
        raise GroupedSplitError("Production fold schema version mismatch.")
    if document.get("config_hash") != hash_core_analysis_config():
        raise GroupedSplitError("Production folds are not bound to frozen config bytes.")
    if document.get("analysis_config_version") != ANALYSIS_CONFIG_VERSION:
        raise GroupedSplitError("Production fold analysis version mismatch.")
    if (
        document.get("strategy") != "layout_grouped"
        or document.get("assignment_source")
        != "frozen_layout_plan_subset_without_reassignment"
        or document.get("random_split_used") is not False
        or document.get("row_order_has_scientific_meaning") is not False
        or document.get("u4_output_inspected") is not False
        or document.get("n_splits") != 5
        or document.get("seed") != 20260719
    ):
        raise GroupedSplitError("Production split policy differs from frozen authority.")
    expected_layout_folds = {
        "layout_00": 1,
        "layout_01": 2,
        "layout_02": 4,
        "layout_03": 0,
        "layout_04": 3,
    }
    declared = document.get("layout_assignments")
    if declared != [
        {"fold_idx": expected_layout_folds[layout], "layout_id": layout}
        for layout in sorted(expected_layout_folds)
    ]:
        raise GroupedSplitError("Production layout folds are not the frozen subset.")
    expected_pilot_ids = [
        "layout_00_ep9403",
        "layout_00_ep9441",
        "layout_01_ep9405",
        "layout_01_ep9442",
        "layout_02_ep9407",
        "layout_02_ep9432",
        "layout_03_ep9404",
        "layout_03_ep9443",
        "layout_04_ep9406",
        "layout_04_ep9444",
    ]
    pilot_ids = document.get("accepted_pilot_ids")
    source_counts = document.get("source_frame_counts")
    source_manifests = document.get("source_manifests")
    memberships = document.get("memberships")
    exclusions = document.get("excluded_memberships")
    if (
        not isinstance(pilot_ids, list)
        or pilot_ids != expected_pilot_ids
        or not isinstance(source_counts, list)
        or len(source_counts) != len(expected_pilot_ids)
        or not isinstance(source_manifests, list)
        or len(source_manifests) != len(expected_pilot_ids)
        or not isinstance(memberships, list)
        or not memberships
        or not isinstance(exclusions, list)
    ):
        raise GroupedSplitError("Production fold membership envelope is malformed.")
    count_by_pilot = {
        row.get("trajectory_id"): row.get("source_frame_count")
        for row in source_counts
        if isinstance(row, Mapping)
    }
    if (
        [row.get("trajectory_id") for row in source_counts] != expected_pilot_ids
        or set(count_by_pilot) != set(pilot_ids)
        or any(
        not isinstance(count, int) or isinstance(count, bool) or count < 1
        for count in count_by_pilot.values()
        )
    ):
        raise GroupedSplitError("Production source-frame counts are invalid.")
    if (
        document.get("source_frame_count") != sum(count_by_pilot.values())
        or document.get("source_frame_count") != 1_874
        or document.get("admitted_frame_count") != 1_695
        or document.get("excluded_frame_count") != 179
        or document.get("activation_row_count") != 37_480
        or document.get("activation_chunk_count") != 200
    ):
        raise GroupedSplitError("Production source-frame total does not reconcile.")
    if document.get("admitted_frame_count") != len(memberships):
        raise GroupedSplitError("Production admitted-frame total does not reconcile.")
    if document.get("excluded_frame_count") != len(exclusions):
        raise GroupedSplitError("Production excluded-frame total does not reconcile.")

    included_keys: set[tuple[str, int]] = set()
    excluded_keys: set[tuple[str, int]] = set()
    for row in memberships:
        if not isinstance(row, Mapping):
            raise GroupedSplitError("Production fold membership must be an object.")
        key = (row.get("trajectory_id"), row.get("model_frame_idx"))
        layout_id = row.get("layout_id")
        if (
            key[0] not in count_by_pilot
            or not isinstance(key[1], int)
            or isinstance(key[1], bool)
            or not 0 <= key[1] < count_by_pilot[key[0]]
            or key in included_keys
            or layout_id not in expected_layout_folds
            or row.get("fold_idx") != expected_layout_folds[layout_id]
            or row.get("target_availability_status") != "available"
            or row.get("status") != "accepted"
            or row.get("source_frame_id")
            != f"{key[0]}:render_frame:{key[1]}"
        ):
            raise GroupedSplitError("Production admitted membership is invalid.")
        scopes = row.get("analysis_scopes")
        if scopes not in (["hidden_mean", "hidden_spread"], ["visible_no_wall_control"]):
            raise GroupedSplitError("Production analysis scope is not frozen.")
        included_keys.add(key)
    for row in exclusions:
        if not isinstance(row, Mapping):
            raise GroupedSplitError("Production exclusion must be an object.")
        key = (row.get("trajectory_id"), row.get("model_frame_idx"))
        if (
            key[0] not in count_by_pilot
            or not isinstance(key[1], int)
            or isinstance(key[1], bool)
            or not 0 <= key[1] < count_by_pilot[key[0]]
            or key in excluded_keys
            or key in included_keys
            or row.get("exclusion_reason")
            != "outside_frozen_condition_selection"
            or row.get("target_availability_status") != "not_admitted"
            or row.get("source_frame_id")
            != f"{key[0]}:render_frame:{key[1]}"
        ):
            raise GroupedSplitError("Production excluded membership is invalid.")
        excluded_keys.add(key)
    expected_keys = {
        (trajectory_id, frame_idx)
        for trajectory_id, count in count_by_pilot.items()
        for frame_idx in range(count)
    }
    if included_keys | excluded_keys != expected_keys:
        raise GroupedSplitError("Production frame coverage is incomplete.")
    sort_key = lambda row: (row["trajectory_id"], row["model_frame_idx"])
    if memberships != sorted(memberships, key=sort_key) or exclusions != sorted(
        exclusions, key=sort_key
    ):
        raise GroupedSplitError("Production frame membership order is not stable.")
    if {row["fold_idx"] for row in memberships} != set(range(5)):
        raise GroupedSplitError("Production folds do not populate all five indices.")
    source_manifest_by_id = {
        row.get("trajectory_id"): row
        for row in source_manifests
        if isinstance(row, Mapping)
    }
    if (
        [row.get("trajectory_id") for row in source_manifests]
        != expected_pilot_ids
        or set(source_manifest_by_id) != set(expected_pilot_ids)
    ):
        raise GroupedSplitError("Production source manifests are incomplete.")
    for trajectory_id in expected_pilot_ids:
        source = source_manifest_by_id[trajectory_id]
        activation_index = source.get("activation_index")
        expected_layout = trajectory_id.split("_ep", 1)[0]
        expected_condition = (
            "no_wall_visible_control"
            if trajectory_id.endswith(("9441", "9442", "9432", "9443", "9444"))
            else "core_occluded"
        )
        if (
            not isinstance(activation_index, Mapping)
            or not isinstance(activation_index.get("path"), str)
            or not is_hex_digest(activation_index.get("sha256"), 64)
            or not isinstance(activation_index.get("byte_size"), int)
            or isinstance(activation_index.get("byte_size"), bool)
            or activation_index["byte_size"] < 1
            or not is_hex_digest(source.get("capture_package_sha256"), 64)
            or not isinstance(source.get("capture_package_byte_size"), int)
            or isinstance(source.get("capture_package_byte_size"), bool)
            or source["capture_package_byte_size"] < 1
            or source.get("layout_id") != expected_layout
            or source.get("condition_role") != expected_condition
            or source.get("fold_idx") != expected_layout_folds[expected_layout]
            or source.get("chunk_count") != 20
            or not isinstance(source.get("activation_row_count"), int)
            or isinstance(source.get("activation_row_count"), bool)
            or source["activation_row_count"] != count_by_pilot[trajectory_id] * 20
        ):
            raise GroupedSplitError("Production source manifest identity is malformed.")
        if any(
            row["layout_id"] != expected_layout
            or row["condition_role"] != expected_condition
            for row in memberships
            if row["trajectory_id"] == trajectory_id
        ):
            raise GroupedSplitError("Production row crosses its pilot source manifest.")
    expected_admitted_by_fold = Counter(row["fold_idx"] for row in memberships)
    expected_admitted_by_pilot = Counter(
        row["trajectory_id"] for row in memberships
    )
    expected_admitted_by_layout = Counter(row["layout_id"] for row in memberships)
    expected_excluded_by_pilot = Counter(
        row["trajectory_id"] for row in exclusions
    )
    declared_counts = document.get("row_counts")
    expected_counts = {
        "admitted_by_fold": [
            {"fold_idx": key, "row_count": expected_admitted_by_fold[key]}
            for key in sorted(expected_admitted_by_fold)
        ],
        "admitted_by_layout": [
            {"layout_id": key, "row_count": expected_admitted_by_layout[key]}
            for key in sorted(expected_admitted_by_layout)
        ],
        "admitted_by_pilot": [
            {"row_count": expected_admitted_by_pilot[key], "trajectory_id": key}
            for key in sorted(expected_admitted_by_pilot)
        ],
        "excluded_by_pilot": [
            {"row_count": expected_excluded_by_pilot[key], "trajectory_id": key}
            for key in sorted(count_by_pilot)
        ],
    }
    if declared_counts != expected_counts:
        raise GroupedSplitError("Production fold row-count audit is incomplete.")
    input_byte_inventory = document.get("input_byte_inventory")
    if not isinstance(input_byte_inventory, list) or len(input_byte_inventory) != 4:
        raise GroupedSplitError("Production fold byte inventory is incomplete.")
    for item in input_byte_inventory:
        if (
            not isinstance(item, Mapping)
            or not isinstance(item.get("path"), str)
            or not item["path"]
            or not is_hex_digest(item.get("sha256"), 64)
            or not isinstance(item.get("byte_size"), int)
            or isinstance(item.get("byte_size"), bool)
            or item["byte_size"] < 1
        ):
            raise GroupedSplitError("Production fold byte inventory is malformed.")
    if len({item["path"] for item in input_byte_inventory}) != 4:
        raise GroupedSplitError("Production fold byte inventory repeats a path.")


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
