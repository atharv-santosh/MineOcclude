"""Fail-closed Step 4.1 consumer for the frozen ten-pilot v2 evidence.

This module is additive.  It leaves the historical v1 pilot runner and the
completed Step 6.6 control unchanged, while providing an explicit production
dispatch for Person A's accepted multi-pilot Activation Store v2 artifacts.
It prepares exact inputs only; no probe is fitted here.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from mineocclude.analysis.config import (
    ANALYSIS_CONFIG_VERSION,
    hash_core_analysis_config,
)
from mineocclude.analysis.manifests import seal_artifact, sha256_value
from mineocclude.analysis.positive_control_v2 import (
    ALL_PILOT_IDS,
    CORE_PILOT_IDS,
    EXPECTED_ACTIVATION_CHUNK_COUNT,
    EXPECTED_LAYER_COUNT,
    EXPECTED_TOTAL_ACTIVATION_ROWS,
    FROZEN_LAYOUT_FOLDS,
    PERSON_A_TEN_PILOT_COMMIT,
    PERSON_C_ACCEPTANCE_COMMIT,
    TenPilotEvidenceBinding,
    validate_loaded_ten_pilot_indices,
)
from mineocclude.contracts.activation_v2 import (
    LoadedActivationIndexV2,
    person_a_activation_index_v2_canonical_json_bytes,
)
from mineocclude.experiments.registry import canonical_json_bytes
from mineocclude.oracle.schema import (
    PRODUCTION_ORACLE_DOCUMENT_FORMAT_VERSION,
    validate_oracle_target_document,
)
from mineocclude.oracle.targets import build_regime_a_target_document
from mineocclude.probes.splits import (
    FOLD_SCHEMA_VERSION,
    TEN_PILOT_FRAME_FOLD_FORMAT_VERSION,
    validate_fold_manifest,
)

PERSON_E_HANDOFF_COMMIT = "21d83c19c9d8f36c4dbeeaf45d4626eaf082e7a7"
PERSON_B_STEP6_6_PASS_COMMIT = "e39fef4a59142a84dfb5991d51deeb506eb23a7b"
PERSON_B_SOURCE_ROW_RATIFICATION_COMMIT = (
    "a24cc316ab45b0063a11141c21a76044439042a0"
)
PERSON_D_RECORDED_AUTHORITY_COMMIT = "853e0acadf050a0b1f318b399b524e57379d03bf"

COMBINED_ACTIVATION_INDEX_FORMAT_VERSION = (
    "person-a-multi-pilot-activation-index-v1"
)
COMBINED_ACTIVATION_INDEX_PATH = (
    "/home/sagemaker-user/person-a-phase6-approved-outputs/"
    "person-a-phase6-ten-pilot-expansion-seed-20260725/"
    "combined_activation_index.json"
)
COMBINED_ACTIVATION_INDEX_SHA256 = (
    "1a25d2186912ba72fdbf123ea9f07b2255bd0e55c6a48a1a50e3b7c0f23eb1e9"
)
COMBINED_ACTIVATION_INDEX_BYTE_SIZE = 245_491_346

EXPECTED_SOURCE_FRAME_COUNT = 1_874
EXPECTED_ADMITTED_FRAME_COUNT = 1_695
EXPECTED_EXCLUDED_FRAME_COUNT = 179
EXPECTED_HIDDEN_PRODUCTION_ROWS = 695
EXPECTED_VISIBLE_CONTROL_ROWS = 1_000
PRODUCTION_INPUT_FORMAT_VERSION = "person-b-step4-1-production-input-v0.1"
FROZEN_PRODUCTION_TARGETS = ("mu_oracle_blocks", "log_sigma_oracle")
FROZEN_ANALYSIS_SCOPES = {
    "hidden_mean": "mu_oracle_blocks",
    "hidden_spread": "log_sigma_oracle",
}


class ProductionV2Error(ValueError):
    """Raised when production preparation would expand a frozen authority."""


def _fail(message: str) -> None:
    raise ProductionV2Error(message)


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _is_sha256(value: Any) -> bool:
    if not isinstance(value, str) or len(value) != 64:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return value == value.lower()


def _strict_json_bytes(payload: bytes, *, label: str) -> Mapping[str, Any]:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                _fail(f"{label} repeats JSON key {key!r}.")
            result[key] = value
        return result

    try:
        document = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=reject_duplicates,
            parse_constant=lambda value: _fail(
                f"{label} contains non-finite constant {value!r}."
            ),
        )
    except ProductionV2Error:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        _fail(f"{label} is not strict UTF-8 JSON: {error}")
    if not isinstance(document, Mapping):
        _fail(f"{label} root must be an object.")
    return document


def _require_exact_bytes(
    payload: bytes,
    *,
    expected_sha256: str,
    expected_byte_size: int,
    label: str,
) -> None:
    if (
        not isinstance(payload, bytes)
        or not _is_sha256(expected_sha256)
        or not isinstance(expected_byte_size, int)
        or isinstance(expected_byte_size, bool)
        or expected_byte_size < 1
    ):
        _fail(f"{label} byte authority is malformed.")
    if len(payload) != expected_byte_size:
        _fail(f"{label} byte size does not match authority.")
    if _sha256_bytes(payload) != expected_sha256:
        _fail(f"{label} SHA-256 does not match authority.")


def validate_combined_activation_index_bytes(
    payload: bytes,
    *,
    expected_sha256: str,
    expected_byte_size: int,
    per_pilot_inventories: Mapping[str, Mapping[str, Any]],
    accepted_manifest_by_trajectory: Mapping[str, str],
    expected_pilot_ids: Sequence[str] = ALL_PILOT_IDS,
    expected_no_wall_ids: Sequence[str] = (
        "layout_00_ep9441",
        "layout_01_ep9442",
        "layout_02_ep9432",
        "layout_03_ep9443",
        "layout_04_ep9444",
    ),
    expected_row_count: int = EXPECTED_TOTAL_ACTIVATION_ROWS,
) -> Mapping[str, Any]:
    """Validate exact Person A combined-index bytes without loading vectors."""

    _require_exact_bytes(
        payload,
        expected_sha256=expected_sha256,
        expected_byte_size=expected_byte_size,
        label="combined_activation_index",
    )
    document = _strict_json_bytes(payload, label="combined_activation_index")
    if payload != person_a_activation_index_v2_canonical_json_bytes(document):
        _fail("Combined activation index bytes are not Person A canonical JSON.")
    pilot_ids = tuple(expected_pilot_ids)
    no_wall_ids = tuple(expected_no_wall_ids)
    if (
        document.get("activation_index_format_version")
        != COMBINED_ACTIVATION_INDEX_FORMAT_VERSION
        or document.get("activation_store_format_version")
        != "person-a-activation-store-v2"
        or document.get("schema_version") != "1.0"
        or tuple(document.get("ordered_pilot_ids", ())) != pilot_ids
        or tuple(document.get("no_wall_control_pilot_ids", ())) != no_wall_ids
        or document.get("combined_activation_row_count") != expected_row_count
        or document.get("scientific_identity_collision_count") != 0
    ):
        _fail("Combined activation index conflicts with its producer contract.")
    if set(per_pilot_inventories) != set(pilot_ids) or set(
        accepted_manifest_by_trajectory
    ) != set(pilot_ids):
        _fail("Combined index authority does not bind the exact pilot set.")
    declared_per_pilot = document.get("per_pilot_indexes")
    rows = document.get("index_rows")
    if not isinstance(declared_per_pilot, list) or not isinstance(rows, list):
        _fail("Combined index payload lists are malformed.")
    expected_per_pilot = [
        {
            "activation_index": per_pilot_inventories[pilot]["activation_index"],
            "activation_row_count": per_pilot_inventories[pilot][
                "activation_row_count"
            ],
            "trajectory_id": pilot,
        }
        for pilot in pilot_ids
    ]
    if declared_per_pilot != expected_per_pilot or len(rows) != expected_row_count:
        _fail("Combined index per-pilot identity or cardinality is stale.")

    seen: set[tuple[Any, ...]] = set()
    observed_counts: Counter[str] = Counter()
    observed_order: list[str] = []
    previous_pilot: str | None = None
    previous_sort_key: tuple[int, int, int] | None = None
    for row in rows:
        if not isinstance(row, Mapping):
            _fail("Combined activation row must be an object.")
        trajectory_id = row.get("trajectory_id")
        if trajectory_id not in per_pilot_inventories:
            _fail("Combined activation row uses an unauthorized pilot.")
        if row.get("accepted_manifest_hash") != accepted_manifest_by_trajectory[
            trajectory_id
        ]:
            _fail("Combined activation row crosses its C manifest identity.")
        global_idx = row.get("global_model_frame_idx")
        local_idx = row.get("context_local_pair_idx")
        layer_idx = row.get("layer_idx")
        if (
            not isinstance(global_idx, int)
            or isinstance(global_idx, bool)
            or global_idx < 0
            or not isinstance(local_idx, int)
            or isinstance(local_idx, bool)
            or not 0 <= local_idx <= 15
            or not isinstance(layer_idx, int)
            or isinstance(layer_idx, bool)
            or layer_idx < 0
        ):
            _fail("Combined activation frame/layer identity is invalid.")
        if row.get("source_frame_id") != (
            f"{trajectory_id}:render_frame:{global_idx}"
        ) or row.get("source_tick") != global_idx:
            _fail("Combined activation source identity is not exact.")
        key = (
            trajectory_id,
            global_idx,
            row.get("source_frame_id"),
            row.get("source_tick"),
            layer_idx,
            row.get("hook_site"),
            row.get("checkpoint_hash"),
            row.get("preprocess_hash"),
        )
        if key in seen:
            _fail("Combined activation scientific identity collides.")
        seen.add(key)
        if trajectory_id != previous_pilot:
            observed_order.append(trajectory_id)
            previous_pilot = trajectory_id
            previous_sort_key = None
        sort_key = (global_idx, layer_idx, local_idx)
        if previous_sort_key is not None and sort_key < previous_sort_key:
            _fail("Combined activation rows are not in producer order.")
        previous_sort_key = sort_key
        observed_counts[trajectory_id] += 1
    if tuple(observed_order) != pilot_ids:
        _fail("Combined activation pilot block order is not frozen.")
    for trajectory_id in pilot_ids:
        inventory = per_pilot_inventories[trajectory_id]
        if observed_counts[trajectory_id] != inventory["activation_row_count"]:
            _fail("Combined activation per-pilot rows do not reconcile.")
    return document


def validate_production_activation_store_v2(
    payload: bytes,
    *,
    production_input_format_version: str,
    expected_sha256: str,
    expected_byte_size: int,
    per_pilot_inventories: Mapping[str, Mapping[str, Any]],
    accepted_manifest_by_trajectory: Mapping[str, str],
) -> Mapping[str, Any]:
    """Dispatch only an explicitly authorized Step 4.1 production v2 input."""

    if production_input_format_version != PRODUCTION_INPUT_FORMAT_VERSION:
        _fail("Unknown or missing Step 4.1 production input authorization.")
    return validate_combined_activation_index_bytes(
        payload,
        expected_sha256=expected_sha256,
        expected_byte_size=expected_byte_size,
        per_pilot_inventories=per_pilot_inventories,
        accepted_manifest_by_trajectory=accepted_manifest_by_trajectory,
    )


def validate_combined_against_loaded_indices(
    combined_document: Mapping[str, Any],
    loaded_indices: Mapping[str, LoadedActivationIndexV2],
) -> None:
    """Require the combined rows to equal the ten authenticated index rows."""

    rows = combined_document.get("index_rows")
    if not isinstance(rows, list):
        _fail("Combined activation document lacks rows.")
    expected = [
        dict(row)
        for trajectory_id in ALL_PILOT_IDS
        for row in loaded_indices[trajectory_id].rows
    ]
    if rows != expected:
        _fail("Combined index rows differ from authenticated per-pilot indexes.")


def build_ten_pilot_frame_fold_manifest(
    *,
    condition_selection: Mapping[str, Any],
    frozen_layout_plan: Mapping[str, Any],
    c_accepted_manifest: Mapping[str, Any],
    per_pilot_inventories: Mapping[str, Mapping[str, Any]],
    authority: TenPilotEvidenceBinding,
    code_sha: str,
    condition_selection_sha256: str,
    condition_selection_byte_size: int,
    frozen_layout_plan_sha256: str,
    frozen_layout_plan_byte_size: int,
    c_accepted_manifest_sha256: str,
    c_accepted_manifest_byte_size: int,
) -> dict[str, Any]:
    """Seal the unique ten-pilot subset of the predeclared frame selection."""

    if (
        condition_selection.get("status") != "accepted"
        or condition_selection.get("selection_policy")
        != "predeclared_before_probe_results"
        or frozen_layout_plan.get("status") != "frozen_before_person_a_join"
        or frozen_layout_plan.get("outcome_fields_used") is not False
        or frozen_layout_plan.get("strategy") != "layout_grouped"
        or frozen_layout_plan.get("seed") != 20260719
        or frozen_layout_plan.get("n_splits") != 5
    ):
        _fail("Frame selection or fold plan is not the frozen pre-result authority.")
    for value, label in (
        (condition_selection_sha256, "condition selection"),
        (frozen_layout_plan_sha256, "layout plan"),
        (c_accepted_manifest_sha256, "C accepted manifest"),
    ):
        if not _is_sha256(value):
            _fail(f"{label} literal hash is invalid.")
    for value, label in (
        (condition_selection_byte_size, "condition selection"),
        (frozen_layout_plan_byte_size, "layout plan"),
        (c_accepted_manifest_byte_size, "C accepted manifest"),
    ):
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            _fail(f"{label} byte size is invalid.")
    c_rows = c_accepted_manifest.get("intake_rows")
    if not isinstance(c_rows, list):
        _fail("Person C accepted pilot manifest is malformed.")
    c_by_id = {row.get("trajectory_id"): row for row in c_rows}
    if tuple(c_accepted_manifest.get("ordered_pilot_ids", ())) != ALL_PILOT_IDS:
        _fail("Person C pilot membership/order differs from frozen authority.")
    if set(c_by_id) != set(ALL_PILOT_IDS):
        _fail("Person C acceptance does not contain exactly ten pilots.")
    selection_rows = condition_selection.get("rows")
    if not isinstance(selection_rows, list):
        _fail("Frozen condition selection rows are malformed.")
    selected: dict[tuple[str, int], Mapping[str, Any]] = {}
    for row in selection_rows:
        if not isinstance(row, Mapping):
            _fail("Frozen condition selection row must be an object.")
        trajectory_id = row.get("trajectory_id")
        if trajectory_id not in ALL_PILOT_IDS:
            continue
        key = (trajectory_id, row.get("model_frame_idx"))
        if (
            not isinstance(key[1], int)
            or isinstance(key[1], bool)
            or key[1] < 0
            or key in selected
            or row.get("status") != "accepted"
        ):
            _fail("Frozen selected frame identity is invalid or duplicate.")
        selected[key] = row
    if len(selected) != EXPECTED_ADMITTED_FRAME_COUNT:
        _fail("Frozen ten-pilot condition selection must contain 1,695 frames.")

    memberships: list[dict[str, Any]] = []
    exclusions: list[dict[str, Any]] = []
    source_frame_counts: list[dict[str, Any]] = []
    source_manifests: list[dict[str, Any]] = []
    for trajectory_id in ALL_PILOT_IDS:
        c_row = c_by_id[trajectory_id]
        inventory = per_pilot_inventories.get(trajectory_id)
        if not isinstance(inventory, Mapping):
            _fail("Person A per-pilot inventory is absent.")
        frame_count = c_row.get("frame_count")
        layout_id = c_row.get("layout_id")
        fold_idx = FROZEN_LAYOUT_FOLDS.get(layout_id)
        if (
            not isinstance(frame_count, int)
            or isinstance(frame_count, bool)
            or frame_count < 1
            or c_row.get("fold_idx") != fold_idx
            or authority.fold_by_trajectory.get(trajectory_id) != fold_idx
            or inventory.get("frame_count") != frame_count
            or inventory.get("fold_idx") != fold_idx
        ):
            _fail("Pilot frame/fold authority does not reconcile.")
        source_frame_counts.append(
            {"source_frame_count": frame_count, "trajectory_id": trajectory_id}
        )
        source_manifests.append(
            {
                "activation_index": dict(inventory["activation_index"]),
                "activation_row_count": inventory["activation_row_count"],
                "capture_package_byte_size": c_row["capture_package_byte_size"],
                "capture_package_path": c_row["capture_package_path"],
                "capture_package_sha256": c_row["capture_package_sha256"],
                "chunk_count": len(inventory["chunks"]),
                "condition_role": c_row["condition_role"],
                "fold_idx": fold_idx,
                "layout_id": layout_id,
                "trajectory_id": trajectory_id,
            }
        )
        for frame_idx in range(frame_count):
            key = (trajectory_id, frame_idx)
            selection = selected.get(key)
            if selection is None:
                exclusions.append(
                    {
                        "exclusion_reason": "outside_frozen_condition_selection",
                        "layout_id": layout_id,
                        "model_frame_idx": frame_idx,
                        "source_frame_id": (
                            f"{trajectory_id}:render_frame:{frame_idx}"
                        ),
                        "target_availability_status": "not_admitted",
                        "trajectory_id": trajectory_id,
                    }
                )
                continue
            if (
                selection.get("layout_id") != layout_id
                or selection.get("condition_role") != c_row["condition_role"]
            ):
                _fail("Selected frame crosses its accepted pilot identity.")
            memberships.append(
                {
                    "analysis_scopes": list(selection["analysis_scopes"]),
                    "condition_role": selection["condition_role"],
                    "fold_idx": fold_idx,
                    "layout_id": layout_id,
                    "model_frame_idx": frame_idx,
                    "source_frame_id": f"{trajectory_id}:render_frame:{frame_idx}",
                    "status": "accepted",
                    "target_availability_status": "available",
                    "trajectory_id": trajectory_id,
                }
            )
    sort_key = lambda row: (row["trajectory_id"], row["model_frame_idx"])
    memberships.sort(key=sort_key)
    exclusions.sort(key=sort_key)
    source_frame_counts.sort(key=lambda row: row["trajectory_id"])
    source_manifests.sort(key=lambda row: row["trajectory_id"])
    input_identity = {
        "combined_activation_index_sha256": COMBINED_ACTIVATION_INDEX_SHA256,
        "condition_selection_sha256": condition_selection_sha256,
        "c_accepted_manifest_sha256": c_accepted_manifest_sha256,
        "frozen_layout_plan_sha256": frozen_layout_plan_sha256,
        "person_a_commit": PERSON_A_TEN_PILOT_COMMIT,
        "person_c_commit": PERSON_C_ACCEPTANCE_COMMIT,
    }
    admitted_by_fold = Counter(row["fold_idx"] for row in memberships)
    admitted_by_layout = Counter(row["layout_id"] for row in memberships)
    admitted_by_pilot = Counter(row["trajectory_id"] for row in memberships)
    excluded_by_pilot = Counter(row["trajectory_id"] for row in exclusions)
    manifest = seal_artifact(
        {
            "accepted_pilot_ids": list(ALL_PILOT_IDS),
            "activation_chunk_count": EXPECTED_ACTIVATION_CHUNK_COUNT,
            "activation_row_count": EXPECTED_TOTAL_ACTIVATION_ROWS,
            "admitted_frame_count": len(memberships),
            "analysis_config_version": ANALYSIS_CONFIG_VERSION,
            "artifact_id": "person_b_step4_1_ten_pilot_frame_folds_v0_1",
            "artifact_type": "fold_manifest",
            "assignment_source": "frozen_layout_plan_subset_without_reassignment",
            "code_sha": code_sha,
            "config_hash": hash_core_analysis_config(),
            "excluded_frame_count": len(exclusions),
            "excluded_memberships": exclusions,
            "fold_manifest_format_version": TEN_PILOT_FRAME_FOLD_FORMAT_VERSION,
            "fold_schema_version": FOLD_SCHEMA_VERSION,
            "input_manifest_hash": sha256_value(input_identity),
            "input_byte_inventory": [
                {
                    "byte_size": COMBINED_ACTIVATION_INDEX_BYTE_SIZE,
                    "path": COMBINED_ACTIVATION_INDEX_PATH,
                    "sha256": COMBINED_ACTIVATION_INDEX_SHA256,
                },
                {
                    "byte_size": condition_selection_byte_size,
                    "path": (
                        "data/person_b/phase6_c_intake/"
                        "condition_selection_source.json"
                    ),
                    "sha256": condition_selection_sha256,
                },
                {
                    "byte_size": frozen_layout_plan_byte_size,
                    "path": "data/person_b/phase6_c_intake/layout_fold_plan.json",
                    "sha256": frozen_layout_plan_sha256,
                },
                {
                    "byte_size": c_accepted_manifest_byte_size,
                    "path": (
                        "docs/status/"
                        "person_c_phase6_ten_pilot_expansion_acceptance_v0_1/"
                        "accepted_pilot_manifest.json"
                    ),
                    "sha256": c_accepted_manifest_sha256,
                },
            ],
            "layout_assignments": [
                {"fold_idx": FROZEN_LAYOUT_FOLDS[layout], "layout_id": layout}
                for layout in sorted(FROZEN_LAYOUT_FOLDS)
            ],
            "memberships": memberships,
            "n_splits": 5,
            "random_split_used": False,
            "row_order_has_scientific_meaning": False,
            "row_counts": {
                "admitted_by_fold": [
                    {"fold_idx": key, "row_count": admitted_by_fold[key]}
                    for key in sorted(admitted_by_fold)
                ],
                "admitted_by_layout": [
                    {"layout_id": key, "row_count": admitted_by_layout[key]}
                    for key in sorted(admitted_by_layout)
                ],
                "admitted_by_pilot": [
                    {"row_count": admitted_by_pilot[key], "trajectory_id": key}
                    for key in sorted(admitted_by_pilot)
                ],
                "excluded_by_pilot": [
                    {"row_count": excluded_by_pilot[key], "trajectory_id": key}
                    for key in ALL_PILOT_IDS
                ],
            },
            "scientific_use": "permitted",
            "seed": 20260719,
            "source_frame_count": sum(
                row["source_frame_count"] for row in source_frame_counts
            ),
            "source_frame_counts": source_frame_counts,
            "source_identities": input_identity,
            "source_manifests": source_manifests,
            "strategy": "layout_grouped",
            "synthetic": False,
            "u4_output_inspected": False,
        }
    )
    validate_fold_manifest(manifest)
    if (
        manifest["source_frame_count"] != EXPECTED_SOURCE_FRAME_COUNT
        or manifest["admitted_frame_count"] != EXPECTED_ADMITTED_FRAME_COUNT
        or manifest["excluded_frame_count"] != EXPECTED_EXCLUDED_FRAME_COUNT
    ):
        _fail("Ten-pilot fold manifest counts do not match frozen selection.")
    return manifest


def _numeric_distribution(values: Sequence[float]) -> dict[str, float | int]:
    if not values or any(not math.isfinite(float(value)) for value in values):
        _fail("Target distribution requires finite values.")
    materialized = [float(value) for value in values]
    return {
        "count": len(materialized),
        "maximum": max(materialized),
        "mean": sum(materialized) / len(materialized),
        "minimum": min(materialized),
    }


def build_production_oracle_target_document(
    state_inputs_by_trajectory: Mapping[str, Mapping[str, Any]],
    *,
    fold_manifest: Mapping[str, Any],
    code_sha: str,
    oracle_run_id: str,
    analysis_config_path: Path | str,
) -> dict[str, Any]:
    """Materialize the frozen oracle for exact admitted ten-pilot frames."""

    validate_fold_manifest(fold_manifest)
    if set(state_inputs_by_trajectory) != set(ALL_PILOT_IDS):
        _fail("Production oracle requires exactly ten state inputs.")
    rows: list[dict[str, Any]] = []
    trajectory_lineage: list[dict[str, Any]] = []
    coordinate_frames: list[dict[str, Any]] = []
    for trajectory_id in ALL_PILOT_IDS:
        state = state_inputs_by_trajectory[trajectory_id]
        state_rows = state.get("rows")
        if state.get("trajectory_id") != trajectory_id or not isinstance(
            state_rows, list
        ):
            _fail("Production state input crosses trajectory identity.")
        source_by_frame = {row["model_frame_idx"]: row for row in state_rows}
        if len(source_by_frame) != len(state_rows):
            _fail("Production state input repeats a frame identity.")
        oracle_state = dict(state)
        oracle_state["join_key"] = ["trajectory_id", "model_frame_idx"]
        full_target = build_regime_a_target_document(
            oracle_state,
            oracle_run_id=oracle_run_id,
            oracle_code_sha=code_sha,
            analysis_config_path=analysis_config_path,
        )
        target_by_frame = {
            row["model_frame_idx"]: row for row in full_target["rows"]
        }
        selected_memberships = [
            row
            for row in fold_manifest["memberships"]
            if row["trajectory_id"] == trajectory_id
        ]
        selected_memberships.sort(key=lambda row: row["model_frame_idx"])
        if not selected_memberships:
            _fail("Every accepted pilot requires admitted production frames.")
        for membership in selected_memberships:
            frame_idx = membership["model_frame_idx"]
            source = source_by_frame.get(frame_idx)
            target = target_by_frame.get(frame_idx)
            if source is None or target is None:
                _fail("Production target cannot join exact source frame identity.")
            decorated = dict(target)
            decorated.update(
                {
                    "accepted_c_manifest_sha256": source[
                        "accepted_c_manifest_sha256"
                    ],
                    "analysis_scopes": list(membership["analysis_scopes"]),
                    "c_frame_map_row_sha256": source["c_frame_map_row_sha256"],
                    "c_frame_map_sha256": source["c_frame_map_sha256"],
                    "c_state_row_sha256": source["c_state_row_sha256"],
                    "c_state_sha256": source["c_state_sha256"],
                    "canonical_episode_manifest_sha256": source[
                        "canonical_episode_manifest_sha256"
                    ],
                    "canonical_state_object_sha256": source[
                        "canonical_state_object_sha256"
                    ],
                    "condition_role": membership["condition_role"],
                    "fold_idx": membership["fold_idx"],
                    "global_model_frame_idx": source["global_model_frame_idx"],
                    "literal_capture_package_sha256": source[
                        "literal_capture_package_sha256"
                    ],
                    "source_frame_id": source["source_frame_id"],
                    "source_frame_idx": source["source_frame_idx"],
                    "source_tick": source["source_tick"],
                }
            )
            rows.append(decorated)
        first = source_by_frame[selected_memberships[0]["model_frame_idx"]]
        condition_role = selected_memberships[0]["condition_role"]
        anchor: dict[str, Any] | None = None
        if condition_role == "core_occluded":
            anchor_idx = first["model_frame_idx"] - 1
            anchor_row = source_by_frame.get(anchor_idx)
            if (
                anchor_row is None
                or anchor_row.get("visibility") != "visible"
                or first.get("visibility") != "occluded"
            ):
                _fail("Hidden production interval lacks its adjacent visible anchor.")
            anchor = {
                "model_frame_idx": anchor_idx,
                "position_blocks": anchor_row["observed_position_blocks"],
                "server_tick": anchor_row["server_tick"],
                "source_frame_id": anchor_row["source_frame_id"],
            }
        elif condition_role != "no_wall_visible_control":
            _fail("Unknown production condition role.")
        coordinate_frame = state.get("coordinate_frame")
        coordinate_frames.append(
            {"coordinate_frame": dict(coordinate_frame), "trajectory_id": trajectory_id}
        )
        trajectory_lineage.append(
            {
                "accepted_c_manifest_sha256": state[
                    "accepted_c_manifest_sha256"
                ],
                "admitted_target_row_count": len(selected_memberships),
                "canonical_episode_manifest_sha256": state[
                    "canonical_episode_manifest_sha256"
                ],
                "canonical_state_object_sha256": state[
                    "canonical_state_object_sha256"
                ],
                "condition_role": condition_role,
                "coordinate_frame_hash": coordinate_frame["coordinate_frame_hash"],
                "excluded_frame_count": len(state_rows) - len(selected_memberships),
                "fold_idx": selected_memberships[0]["fold_idx"],
                "last_visible_anchor": anchor,
                "layout_id": first["layout_id"],
                "literal_capture_package_sha256": state[
                    "literal_capture_package_sha256"
                ],
                "source_frame_count": len(state_rows),
                "source_run_id": first["run_id"],
                "trajectory_id": trajectory_id,
            }
        )
    rows.sort(key=lambda row: (row["trajectory_id"], row["model_frame_idx"]))
    trajectory_lineage.sort(key=lambda row: row["trajectory_id"])
    coordinate_frames.sort(key=lambda row: row["trajectory_id"])
    hidden_rows = [row for row in rows if row["visibility"] == "occluded"]
    visible_rows = [row for row in rows if row["visibility"] == "visible"]
    if (
        len(rows) != EXPECTED_ADMITTED_FRAME_COUNT
        or len(hidden_rows) != EXPECTED_HIDDEN_PRODUCTION_ROWS
        or len(visible_rows) != EXPECTED_VISIBLE_CONTROL_ROWS
    ):
        _fail("Production target eligibility counts do not reconcile.")
    config_hash = hash_core_analysis_config(analysis_config_path)
    document = seal_artifact(
        {
            "accepted_pilot_ids": list(ALL_PILOT_IDS),
            "artifact_id": "person_b_step4_1_production_oracle_targets_v0_1",
            "artifact_type": "oracle_target",
            "code_sha": code_sha,
            "config_hash": config_hash,
            "coordinate_frames_by_trajectory": coordinate_frames,
            "eligibility_counts": {
                "accepted_hidden_positive_spread_rows": len(hidden_rows),
                "accepted_post_first_seen_rows": len(rows),
                "visible_no_wall_control_rows": len(visible_rows),
            },
            "information_set": [
                "last_visible_position_blocks",
                "v",
                "q",
                "tau",
                "visibility",
            ],
            "input_manifest_hash": fold_manifest["artifact_hash"],
            "join_key": ["trajectory_id", "model_frame_idx"],
            "method": "primary_scalar_kalman_crosschecked_closed_form",
            "oracle_document_format_version": (
                PRODUCTION_ORACLE_DOCUMENT_FORMAT_VERSION
            ),
            "row_count": len(rows),
            "rows": rows,
            "schema_version": "1.0",
            "scientific_use": "permitted",
            "synthetic": False,
            "target_distributions": {
                "log_sigma_oracle": _numeric_distribution(
                    [row["log_sigma_oracle"] for row in hidden_rows]
                ),
                "mu_oracle_blocks": _numeric_distribution(
                    [row["mu_oracle_blocks"] for row in rows]
                ),
                "sigma_oracle_blocks": _numeric_distribution(
                    [row["sigma_oracle_blocks"] for row in rows]
                ),
                "x_true_blocks": _numeric_distribution(
                    [row["x_true_blocks"] for row in rows]
                ),
            },
            "target_counts": {
                "by_fold": [
                    {"fold_idx": key, "row_count": value}
                    for key, value in sorted(
                        Counter(row["fold_idx"] for row in rows).items()
                    )
                ],
                "by_layout": [
                    {"layout_id": key, "row_count": value}
                    for key, value in sorted(
                        Counter(row["layout_id"] for row in rows).items()
                    )
                ],
                "by_pilot": [
                    {"row_count": value, "trajectory_id": key}
                    for key, value in sorted(
                        Counter(row["trajectory_id"] for row in rows).items()
                    )
                ],
                "by_visibility": [
                    {"row_count": value, "visibility": key}
                    for key, value in sorted(
                        Counter(row["visibility"] for row in rows).items()
                    )
                ],
            },
            "target_schema_version": "person-b-oracle-target-v0.1",
            "trajectory_lineage": trajectory_lineage,
            "u4_output_inspected": False,
        }
    )
    validate_oracle_target_document(
        document,
        analysis_config_path=analysis_config_path,
    )
    return document


@dataclass(frozen=True)
class ProductionProbeMatrixV2:
    """One exact hidden target/layer matrix prepared without fitting."""

    target_name: str
    layer_idx: int
    hook_site: str
    features: tuple[np.ndarray, ...]
    targets: tuple[float, ...]
    outer_folds: tuple[int, ...]
    layout_ids: tuple[str, ...]
    metadata_rows: tuple[Mapping[str, Any], ...]
    matrix_hash: str


@dataclass(frozen=True)
class ProductionProbeBridgeV2:
    """Prepared production matrices and immutable lineage, before any fit."""

    matrices: tuple[ProductionProbeMatrixV2, ...]
    input_hash: str
    hidden_frame_count: int
    activation_row_count_verified: int
    activation_chunk_count_verified: int
    scientific_execution_performed: bool = False


def build_production_probe_bridge_v2(
    indices_by_trajectory: Mapping[str, LoadedActivationIndexV2],
    *,
    authority: TenPilotEvidenceBinding,
    fold_manifest: Mapping[str, Any],
    oracle_target_document: Mapping[str, Any],
) -> ProductionProbeBridgeV2:
    """Join exact IDs into frozen hidden-mean/spread matrices without fitting."""

    validate_loaded_ten_pilot_indices(indices_by_trajectory, authority=authority)
    validate_fold_manifest(fold_manifest)
    validate_oracle_target_document(oracle_target_document)
    target_by_key = {
        (row["trajectory_id"], row["model_frame_idx"]): row
        for row in oracle_target_document["rows"]
    }
    membership_by_key = {
        (row["trajectory_id"], row["model_frame_idx"]): row
        for row in fold_manifest["memberships"]
    }
    if set(target_by_key) != set(membership_by_key):
        _fail("Production target and frame-fold coverage differ.")
    hidden_keys = {
        key
        for key, membership in membership_by_key.items()
        if membership["analysis_scopes"] == ["hidden_mean", "hidden_spread"]
    }
    if len(hidden_keys) != EXPECTED_HIDDEN_PRODUCTION_ROWS:
        _fail("Production bridge requires exactly 695 hidden source frames.")

    by_site: dict[
        tuple[int, str],
        list[tuple[LoadedActivationIndexV2, Mapping[str, Any], Mapping[str, Any]]],
    ] = defaultdict(list)
    seen: set[tuple[str, int, int, str]] = set()
    for trajectory_id in CORE_PILOT_IDS:
        index = indices_by_trajectory[trajectory_id]
        if not index.arrays_by_chunk_id:
            _fail("Production core activation vectors were not retained.")
        for activation_row in index.rows:
            key = (trajectory_id, activation_row["global_model_frame_idx"])
            if key not in hidden_keys:
                continue
            target = target_by_key[key]
            for field in (
                "accepted_manifest_hash",
                "global_model_frame_idx",
                "source_frame_id",
                "source_frame_idx",
                "source_tick",
                "c_frame_map_sha256",
                "c_frame_map_row_sha256",
                "c_state_sha256",
                "c_state_row_sha256",
            ):
                target_field = (
                    "literal_capture_package_sha256"
                    if field == "accepted_manifest_hash"
                    else field
                )
                if activation_row.get(field) != target.get(target_field):
                    _fail(f"Production activation/oracle lineage differs at {field}.")
            identity = (
                trajectory_id,
                activation_row["global_model_frame_idx"],
                activation_row["layer_idx"],
                activation_row["hook_site"],
            )
            if identity in seen:
                _fail("Production activation identity collides.")
            seen.add(identity)
            by_site[(activation_row["layer_idx"], activation_row["hook_site"])].append(
                (index, activation_row, target)
            )
    if len(by_site) != EXPECTED_LAYER_COUNT:
        _fail("Production bridge must retain all 20 frozen layers.")

    matrices: list[ProductionProbeMatrixV2] = []
    for (layer_idx, hook_site), joined in sorted(by_site.items()):
        ordered = sorted(
            joined,
            key=lambda value: (
                value[1]["trajectory_id"],
                value[1]["global_model_frame_idx"],
            ),
        )
        if len(ordered) != EXPECTED_HIDDEN_PRODUCTION_ROWS:
            _fail("Each production layer must contain 695 hidden frames.")
        for target_name in FROZEN_PRODUCTION_TARGETS:
            features: list[np.ndarray] = []
            targets: list[float] = []
            folds: list[int] = []
            layouts: list[str] = []
            metadata: list[dict[str, Any]] = []
            for index, activation_row, target in ordered:
                value = target[target_name]
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    _fail(f"Production target {target_name} is missing.")
                vector = index.vector_for_row(activation_row)
                if (
                    vector.dtype != np.float32
                    or vector.ndim != 1
                    or not bool(np.isfinite(vector).all())
                ):
                    _fail("Production activation vector is not finite float32 data.")
                features.append(vector)
                targets.append(float(value))
                folds.append(target["fold_idx"])
                layouts.append(target["layout_id"])
                metadata.append(
                    {
                        "accepted_c_manifest_sha256": target[
                            "accepted_c_manifest_sha256"
                        ],
                        "activation_chunk_id": activation_row[
                            "activation_chunk_id"
                        ],
                        "activation_index_sha256": index.index_sha256,
                        "activation_row_identity_sha256": hashlib.sha256(
                            canonical_json_bytes(dict(activation_row))
                        ).hexdigest(),
                        "canonical_state_object_sha256": target[
                            "canonical_state_object_sha256"
                        ],
                        "chunk_row_idx": activation_row["chunk_row_idx"],
                        "context_local_pair_idx": activation_row[
                            "context_local_pair_idx"
                        ],
                        "global_model_frame_idx": activation_row[
                            "global_model_frame_idx"
                        ],
                        "hook_site": hook_site,
                        "layer_idx": layer_idx,
                        "layout_id": target["layout_id"],
                        "model_frame_idx": target["model_frame_idx"],
                        "literal_capture_package_sha256": target[
                            "literal_capture_package_sha256"
                        ],
                        "model_hash": activation_row["model_hash"],
                        "preprocess_hash": activation_row["preprocess_hash"],
                        "producing_run_id": activation_row["run_id"],
                        "source_frame_id": target["source_frame_id"],
                        "source_tick": target["source_tick"],
                        "target_id": target["target_id"],
                        "trajectory_id": target["trajectory_id"],
                    }
                )
            identity = {
                "folds": folds,
                "hook_site": hook_site,
                "layer_idx": layer_idx,
                "rows": metadata,
                "target_name": target_name,
                "targets": targets,
            }
            matrices.append(
                ProductionProbeMatrixV2(
                    target_name=target_name,
                    layer_idx=layer_idx,
                    hook_site=hook_site,
                    features=tuple(features),
                    targets=tuple(targets),
                    outer_folds=tuple(folds),
                    layout_ids=tuple(layouts),
                    metadata_rows=tuple(metadata),
                    matrix_hash=hashlib.sha256(
                        canonical_json_bytes(identity)
                    ).hexdigest(),
                )
            )
    input_identity = {
        "fold_artifact_hash": fold_manifest["artifact_hash"],
        "format_version": PRODUCTION_INPUT_FORMAT_VERSION,
        "matrix_hashes": [matrix.matrix_hash for matrix in matrices],
        "oracle_artifact_hash": oracle_target_document["artifact_hash"],
        "targets": list(FROZEN_PRODUCTION_TARGETS),
    }
    return ProductionProbeBridgeV2(
        matrices=tuple(matrices),
        input_hash=hashlib.sha256(canonical_json_bytes(input_identity)).hexdigest(),
        hidden_frame_count=EXPECTED_HIDDEN_PRODUCTION_ROWS,
        activation_row_count_verified=EXPECTED_TOTAL_ACTIVATION_ROWS,
        activation_chunk_count_verified=EXPECTED_ACTIVATION_CHUNK_COUNT,
    )


__all__ = [
    "COMBINED_ACTIVATION_INDEX_BYTE_SIZE",
    "COMBINED_ACTIVATION_INDEX_FORMAT_VERSION",
    "COMBINED_ACTIVATION_INDEX_PATH",
    "COMBINED_ACTIVATION_INDEX_SHA256",
    "EXPECTED_ADMITTED_FRAME_COUNT",
    "EXPECTED_EXCLUDED_FRAME_COUNT",
    "EXPECTED_HIDDEN_PRODUCTION_ROWS",
    "EXPECTED_SOURCE_FRAME_COUNT",
    "FROZEN_ANALYSIS_SCOPES",
    "FROZEN_PRODUCTION_TARGETS",
    "PERSON_B_SOURCE_ROW_RATIFICATION_COMMIT",
    "PERSON_B_STEP6_6_PASS_COMMIT",
    "PERSON_D_RECORDED_AUTHORITY_COMMIT",
    "PERSON_E_HANDOFF_COMMIT",
    "PRODUCTION_INPUT_FORMAT_VERSION",
    "ProductionProbeBridgeV2",
    "ProductionProbeMatrixV2",
    "ProductionV2Error",
    "build_production_oracle_target_document",
    "build_production_probe_bridge_v2",
    "build_ten_pilot_frame_fold_manifest",
    "validate_combined_activation_index_bytes",
    "validate_combined_against_loaded_indices",
    "validate_production_activation_store_v2",
]
