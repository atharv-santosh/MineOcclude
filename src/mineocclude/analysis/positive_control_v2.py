"""Person B's frozen multi-pilot visible-position positive-control bridge."""

from __future__ import annotations

import hashlib
import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

from mineocclude.contracts.activation_v2 import LoadedActivationIndexV2
from mineocclude.experiments.registry import canonical_json_bytes

PERSON_A_TEN_PILOT_COMMIT = "55776dc88302b89b52eef483a710fbf6811cf536"
PERSON_B_SELECTION_COMMIT = "19f08b2e27217b781961da8f7299e1396a3ab703"
PERSON_B_AUTHORIZATION_COMMIT = "a838c9703003176d8e793bbd43dd6de917740be6"
PERSON_C_ACCEPTANCE_COMMIT = "c6bff25b5ef4f5fdb0e1ef0ce0d22e3f8b5e4960"

ALL_PILOT_IDS = (
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
)
VISIBLE_CONTROL_PILOT_IDS = (
    "layout_00_ep9441",
    "layout_01_ep9442",
    "layout_02_ep9432",
    "layout_03_ep9443",
    "layout_04_ep9444",
)
CORE_PILOT_IDS = tuple(
    pilot for pilot in ALL_PILOT_IDS if pilot not in VISIBLE_CONTROL_PILOT_IDS
)
FROZEN_LAYOUT_FOLDS = {
    "layout_00": 1,
    "layout_01": 2,
    "layout_02": 4,
    "layout_03": 0,
    "layout_04": 3,
}
FROZEN_TARGET_NAME = "x_true_blocks"
FROZEN_THRESHOLD_POLICY = "human_scientific_gate_no_unfrozen_numeric_threshold"
EXPECTED_TOTAL_ACTIVATION_ROWS = 37_480
EXPECTED_ACTIVATION_INDEX_COUNT = 10
EXPECTED_ACTIVATION_CHUNK_COUNT = 200
EXPECTED_VISIBLE_CONTROL_ROWS = 1_000
EXPECTED_VISIBLE_CONTROL_LAYOUT_COUNT = 5
EXPECTED_LAYER_COUNT = 20
POSITIVE_CONTROL_INPUT_FORMAT_VERSION = "person-b-positive-control-input-v2"


class PositiveControlV2Error(ValueError):
    """Fail-closed frozen positive-control bridge error."""


def _fail(message: str) -> None:
    raise PositiveControlV2Error(message)


def _is_sha256(value: Any) -> bool:
    if not isinstance(value, str) or len(value) != 64:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return value == value.lower()


def _is_int(value: Any, *, minimum: int = 0) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= minimum


def _hash_json(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


@dataclass(frozen=True)
class TenPilotEvidenceBinding:
    """Validated committed A/C metadata needed before external byte loading."""

    accepted_c_manifest_by_trajectory: Mapping[str, str]
    c_capture_path_by_trajectory: Mapping[str, str]
    fold_by_trajectory: Mapping[str, int]


@dataclass(frozen=True)
class PositiveControlMatrixV2:
    """One layer/site matrix in the existing B X/y/fold shape plus v2 lineage."""

    layer_idx: int
    hook_site: str
    features: tuple[np.ndarray, ...]
    targets: tuple[float, ...]
    outer_folds: tuple[int, ...]
    layout_ids: tuple[str, ...]
    metadata_rows: tuple[Mapping[str, Any], ...]
    matrix_hash: str


@dataclass(frozen=True)
class PositiveControlBridgeV2:
    """Complete prepared Step 6.6 inputs; no fit or scientific result."""

    matrices: tuple[PositiveControlMatrixV2, ...]
    per_pilot_lineage: tuple[Mapping[str, Any], ...]
    row_count: int
    layout_count: int
    target_name: str
    threshold_policy: str
    input_hash: str
    scientific_execution_performed: bool = False


def validate_ten_pilot_authority_documents(
    *,
    completion_report: Mapping[str, Any],
    artifact_manifest: Mapping[str, Any],
    positive_control_handoff: Mapping[str, Any],
    per_pilot_inventories: Mapping[str, Mapping[str, Any]],
    c_accepted_manifest: Mapping[str, Any],
) -> TenPilotEvidenceBinding:
    """Validate exact committed A/C inventories without accepting external bytes."""

    if completion_report.get("status") != "PASS":
        _fail("Person A ten-pilot completion status is not PASS.")
    expected_completion = {
        "accepted_pilot_count": EXPECTED_ACTIVATION_INDEX_COUNT,
        "actual_activation_row_count": EXPECTED_TOTAL_ACTIVATION_ROWS,
        "expected_activation_row_count": EXPECTED_TOTAL_ACTIVATION_ROWS,
        "no_wall_control_count": EXPECTED_VISIBLE_CONTROL_LAYOUT_COUNT,
        "person_b_expansion_authorization_object": (
            f"{PERSON_B_AUTHORIZATION_COMMIT}:docs/status/"
            "person_b_phase6_ten_pilot_expansion_authorization_v0_1/"
            "expansion_execution_authorization.json"
        ),
        "person_b_expansion_selection_commit": PERSON_B_SELECTION_COMMIT,
        "person_c_expansion_acceptance_commit": PERSON_C_ACCEPTANCE_COMMIT,
        "step6_6_complete": False,
        "u4_output_inspected": False,
    }
    if any(
        completion_report.get(key) != value
        for key, value in expected_completion.items()
    ):
        _fail("Person A completion report conflicts with the frozen authority.")
    if tuple(completion_report.get("ordered_pilot_ids", ())) != ALL_PILOT_IDS:
        _fail("Person A pilot order differs from Person B's frozen selection.")
    if (
        tuple(completion_report.get("no_wall_control_pilots", ()))
        != VISIBLE_CONTROL_PILOT_IDS
    ):
        _fail("Person A no-wall controls differ from the frozen selection.")
    if completion_report.get("hidden_state_interpretation_authorized") is True:
        _fail("Hidden-state interpretation cannot be authorized here.")
    if (
        artifact_manifest.get("activation_chunk_count")
        != EXPECTED_ACTIVATION_CHUNK_COUNT
        or artifact_manifest.get("per_pilot_inventory_count")
        != EXPECTED_ACTIVATION_INDEX_COUNT
        or artifact_manifest.get("activation_chunks_staged") is not False
    ):
        _fail("Person A artifact inventory counts are not frozen ten-pilot evidence.")
    if set(per_pilot_inventories) != set(ALL_PILOT_IDS):
        _fail("Exactly ten named per-pilot inventories are required.")
    inventory_chunks = 0
    inventory_rows = 0
    for trajectory_id in ALL_PILOT_IDS:
        inventory = per_pilot_inventories[trajectory_id]
        expected_status = (
            "REUSED_EXACT_EXISTING_ARTIFACTS"
            if trajectory_id == "layout_00_ep9403"
            else "PASS"
        )
        if (
            inventory.get("trajectory_id") != trajectory_id
            or inventory.get("status") != expected_status
        ):
            _fail(f"Per-pilot inventory {trajectory_id!r} has an invalid status.")
        activation_index = inventory.get("activation_index")
        chunks = inventory.get("chunks")
        if not isinstance(activation_index, Mapping) or not isinstance(chunks, list):
            _fail(f"Per-pilot inventory {trajectory_id!r} is malformed.")
        if not _is_sha256(activation_index.get("sha256")) or not _is_int(
            activation_index.get("byte_size"), minimum=1
        ):
            _fail(f"Per-pilot index identity {trajectory_id!r} is malformed.")
        if len(chunks) != EXPECTED_LAYER_COUNT:
            _fail(f"Per-pilot inventory {trajectory_id!r} must contain 20 chunks.")
        chunk_ids: set[str] = set()
        for chunk in chunks:
            if not isinstance(chunk, Mapping):
                _fail("Per-pilot chunk descriptor must be an object.")
            chunk_id = chunk.get("chunk_id")
            if (
                not isinstance(chunk_id, str)
                or not chunk_id
                or chunk_id in chunk_ids
                or not _is_sha256(chunk.get("sha256"))
                or not _is_int(chunk.get("byte_size"), minimum=1)
                or not _is_int(chunk.get("row_count"), minimum=1)
            ):
                _fail(f"Per-pilot chunk inventory for {trajectory_id!r} is invalid.")
            chunk_ids.add(chunk_id)
        inventory_chunks += len(chunks)
        row_count = inventory.get("activation_row_count")
        if not _is_int(row_count, minimum=1):
            _fail(f"Per-pilot activation count for {trajectory_id!r} is invalid.")
        inventory_rows += row_count
    if inventory_chunks != EXPECTED_ACTIVATION_CHUNK_COUNT:
        _fail("Per-pilot inventories do not reconcile to 200 chunks.")
    if inventory_rows != EXPECTED_TOTAL_ACTIVATION_ROWS:
        _fail("Per-pilot inventories do not reconcile to 37,480 activation rows.")

    controls = positive_control_handoff.get("no_wall_control_inputs")
    if (
        not isinstance(controls, list)
        or len(controls) != EXPECTED_VISIBLE_CONTROL_LAYOUT_COUNT
    ):
        _fail("Person A positive-control handoff must contain five no-wall pilots.")
    control_ids = tuple(control.get("trajectory_id") for control in controls)
    if control_ids != VISIBLE_CONTROL_PILOT_IDS:
        _fail("Person A positive-control handoff changes frozen pilot membership.")
    if sum(
        control.get("frame_count", -1) for control in controls
    ) != EXPECTED_VISIBLE_CONTROL_ROWS or any(
        control.get("condition_role") != "no_wall_visible_control"
        or control.get("control") is not True
        or control.get("status") != "PASS"
        or control.get("fold_idx") != FROZEN_LAYOUT_FOLDS.get(control.get("layout_id"))
        for control in controls
    ):
        _fail("Person A positive-control rows or grouped folds are not frozen.")
    for control in controls:
        trajectory_id = control["trajectory_id"]
        inventory = per_pilot_inventories[trajectory_id]
        if (
            control.get("activation_index") != inventory.get("activation_index")
            or control.get("chunks") != inventory.get("chunks")
            or control.get("activation_row_count")
            != inventory.get("activation_row_count")
            or control.get("expected_activation_row_count")
            != inventory.get("expected_activation_row_count")
        ):
            _fail(
                f"Positive-control handoff differs from inventory for {trajectory_id!r}."
            )
    if (
        positive_control_handoff.get("person_b_step_6_6_control_execution_complete")
        is not False
    ):
        _fail("Person A handoff cannot claim Person B Step 6.6 execution.")

    c_rows = c_accepted_manifest.get("intake_rows")
    if (
        c_accepted_manifest.get("accepted_pilot_count")
        != EXPECTED_ACTIVATION_INDEX_COUNT
        or not isinstance(c_rows, list)
        or len(c_rows) != EXPECTED_ACTIVATION_INDEX_COUNT
    ):
        _fail("Person C acceptance must contain exactly ten pilots.")
    c_by_trajectory: dict[str, Mapping[str, Any]] = {}
    for row in c_rows:
        if not isinstance(row, Mapping):
            _fail("Person C acceptance rows must be objects.")
        trajectory_id = row.get("trajectory_id")
        if not isinstance(trajectory_id, str) or trajectory_id in c_by_trajectory:
            _fail("Person C acceptance trajectory identity is missing or duplicate.")
        c_by_trajectory[trajectory_id] = row
    if set(c_by_trajectory) != set(ALL_PILOT_IDS):
        _fail("Person C accepted pilot set differs from Person B's selection.")

    manifest_by_trajectory: dict[str, str] = {}
    path_by_trajectory: dict[str, str] = {}
    fold_by_trajectory: dict[str, int] = {}
    for trajectory_id in ALL_PILOT_IDS:
        row = c_by_trajectory[trajectory_id]
        capture_hash = row.get("capture_package_sha256")
        capture_path = row.get("capture_package_path")
        fold = row.get("fold_idx")
        layout = row.get("layout_id")
        if (
            not _is_sha256(capture_hash)
            or not isinstance(capture_path, str)
            or not capture_path
            or fold != FROZEN_LAYOUT_FOLDS.get(layout)
        ):
            _fail(f"Person C binding for {trajectory_id!r} is invalid.")
        manifest_by_trajectory[trajectory_id] = capture_hash
        path_by_trajectory[trajectory_id] = capture_path
        fold_by_trajectory[trajectory_id] = fold
    if len(set(manifest_by_trajectory.values())) != EXPECTED_ACTIVATION_INDEX_COUNT:
        _fail("Each trajectory must retain its distinct accepted C manifest identity.")
    return TenPilotEvidenceBinding(
        accepted_c_manifest_by_trajectory=manifest_by_trajectory,
        c_capture_path_by_trajectory=path_by_trajectory,
        fold_by_trajectory=fold_by_trajectory,
    )


def validate_loaded_ten_pilot_indices(
    indices_by_trajectory: Mapping[str, LoadedActivationIndexV2],
    *,
    authority: TenPilotEvidenceBinding,
) -> None:
    """Require exact ten-index, 200-chunk, 37,480-row external evidence."""

    if set(indices_by_trajectory) != set(ALL_PILOT_IDS):
        _fail("Loaded activation evidence must contain exactly ten frozen pilots.")
    chunk_ids: set[str] = set()
    row_count = 0
    manifests: set[str] = set()
    for trajectory_id in ALL_PILOT_IDS:
        index = indices_by_trajectory[trajectory_id]
        if index.trajectory_id != trajectory_id:
            _fail("Loaded activation index crosses trajectory identity.")
        expected_manifest = authority.accepted_c_manifest_by_trajectory[trajectory_id]
        if index.accepted_manifest_sha256 != expected_manifest:
            _fail("Loaded activation index uses another trajectory's C manifest.")
        manifests.add(index.accepted_manifest_sha256)
        row_count += index.activation_row_count
        for chunk in index.chunks:
            chunk_id = str(chunk["chunk_id"])
            if chunk_id in chunk_ids:
                _fail("Activation chunk identity collides across trajectories.")
            chunk_ids.add(chunk_id)
    if row_count != EXPECTED_TOTAL_ACTIVATION_ROWS:
        _fail("Loaded activation rows do not reconcile to 37,480.")
    if len(chunk_ids) != EXPECTED_ACTIVATION_CHUNK_COUNT:
        _fail("Loaded activation chunks do not reconcile to 200.")
    if len(manifests) != EXPECTED_ACTIVATION_INDEX_COUNT:
        _fail("Loaded evidence collapsed per-trajectory manifest identities.")


def _validate_fold_plan(fold_plan: Mapping[str, Any]) -> None:
    if (
        fold_plan.get("strategy") != "layout_grouped"
        or fold_plan.get("n_splits") != 5
        or fold_plan.get("status") != "frozen_before_person_a_join"
        or fold_plan.get("outcome_fields_used") is not False
    ):
        _fail("Fold plan is not the frozen grouped pre-join plan.")
    assignments = {
        row.get("layout_id"): row.get("fold_idx")
        for row in fold_plan.get("layout_assignments", [])
        if isinstance(row, Mapping) and row.get("layout_id") in FROZEN_LAYOUT_FOLDS
    }
    if assignments != FROZEN_LAYOUT_FOLDS:
        _fail("Fold plan changes one of the five frozen control assignments.")
    scopes = fold_plan.get("scope_fold_coverage")
    if not isinstance(scopes, list):
        _fail("Fold plan scope coverage is malformed.")
    visible = [
        row
        for row in scopes
        if isinstance(row, Mapping) and row.get("scope") == "visible_no_wall_control"
    ]
    if len(visible) != 1 or visible[0].get("accepted_row_count") != 1_000:
        _fail("Fold plan does not preserve exactly 1,000 visible-control rows.")


def _state_rows_by_frame(
    document: Mapping[str, Any],
    *,
    trajectory_id: str,
    expected_manifest_sha256: str,
) -> dict[int, Mapping[str, Any]]:
    if document.get("trajectory_id") != trajectory_id:
        _fail("State document crosses its trajectory identity.")
    if document.get("accepted_c_manifest_sha256") != expected_manifest_sha256:
        _fail("State document literal C identity is stale.")
    literal_hash = document.get("literal_capture_package_sha256")
    canonical_hash = document.get("canonical_state_object_sha256")
    if not _is_sha256(literal_hash) or not _is_sha256(canonical_hash):
        _fail("State document must preserve literal and canonical SHA-256 fields.")
    if document.get("condition") != "no_wall_visible":
        _fail("Core-visible substitution is forbidden in the no-wall control.")
    rows = document.get("rows")
    if not isinstance(rows, list):
        _fail("State document rows are malformed.")
    by_frame: dict[int, Mapping[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            _fail("State row must be an object.")
        global_idx = row.get("global_model_frame_idx")
        if (
            not _is_int(global_idx)
            or global_idx in by_frame
            or row.get("trajectory_id") != trajectory_id
            or row.get("visibility") != "visible"
            or row.get("accepted_c_manifest_sha256") != expected_manifest_sha256
            or row.get("literal_capture_package_sha256") != literal_hash
            or row.get("canonical_state_object_sha256") != canonical_hash
        ):
            _fail("Visible-control state identity, visibility, or hash is invalid.")
        target = row.get(FROZEN_TARGET_NAME)
        if (
            isinstance(target, bool)
            or not isinstance(target, (int, float))
            or not math.isfinite(float(target))
        ):
            _fail("Frozen visible-position target is missing or non-finite.")
        by_frame[global_idx] = row
    if len(by_frame) != 200 or sorted(by_frame) != list(range(200)):
        _fail("Each frozen no-wall trajectory must contain exactly 200 global frames.")
    return by_frame


def _matrix_identity_payload(
    *,
    layer_idx: int,
    hook_site: str,
    targets: Sequence[float],
    folds: Sequence[int],
    metadata_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    return {
        "format_version": POSITIVE_CONTROL_INPUT_FORMAT_VERSION,
        "frozen_target_name": FROZEN_TARGET_NAME,
        "frozen_threshold_policy": FROZEN_THRESHOLD_POLICY,
        "hook_site": hook_site,
        "layer_idx": layer_idx,
        "rows": [
            {
                **dict(metadata),
                "outer_fold_idx": fold,
                "target": target,
            }
            for metadata, fold, target in zip(
                metadata_rows, folds, targets, strict=True
            )
        ],
    }


def build_positive_control_bridge_v2(
    indices_by_trajectory: Mapping[str, LoadedActivationIndexV2],
    state_inputs_by_trajectory: Mapping[str, Mapping[str, Any]],
    *,
    authority: TenPilotEvidenceBinding,
    fold_plan: Mapping[str, Any],
) -> PositiveControlBridgeV2:
    """Join exact v2 IDs into B's X/y/fold shape without running a probe."""

    validate_loaded_ten_pilot_indices(indices_by_trajectory, authority=authority)
    _validate_fold_plan(fold_plan)
    if set(state_inputs_by_trajectory) != set(VISIBLE_CONTROL_PILOT_IDS):
        _fail("State inputs must contain only the five frozen no-wall controls.")

    state_by_trajectory = {
        trajectory_id: _state_rows_by_frame(
            state_inputs_by_trajectory[trajectory_id],
            trajectory_id=trajectory_id,
            expected_manifest_sha256=authority.accepted_c_manifest_by_trajectory[
                trajectory_id
            ],
        )
        for trajectory_id in VISIBLE_CONTROL_PILOT_IDS
    }
    if (
        sum(len(rows) for rows in state_by_trajectory.values())
        != EXPECTED_VISIBLE_CONTROL_ROWS
    ):
        _fail("Visible-control state rows do not reconcile to exactly 1,000.")
    chunks_by_identity = {
        (trajectory_id, chunk["chunk_id"]): chunk
        for trajectory_id in VISIBLE_CONTROL_PILOT_IDS
        for chunk in indices_by_trajectory[trajectory_id].chunks
    }

    rows_by_site: dict[
        tuple[int, str],
        list[tuple[LoadedActivationIndexV2, Mapping[str, Any], Mapping[str, Any]]],
    ] = defaultdict(list)
    source_frames_seen: set[tuple[str, int, int, str]] = set()
    for trajectory_id in VISIBLE_CONTROL_PILOT_IDS:
        index = indices_by_trajectory[trajectory_id]
        if not index.arrays_by_chunk_id:
            _fail("Selected no-wall activation vectors were not retained.")
        state_rows = state_by_trajectory[trajectory_id]
        for activation_row in index.rows:
            global_idx = activation_row["global_model_frame_idx"]
            state_row = state_rows.get(global_idx)
            if state_row is None:
                _fail("Activation row has no exact visible-control target ID.")
            for field in (
                "source_frame_id",
                "source_frame_idx",
                "source_tick",
                "c_frame_map_sha256",
                "c_frame_map_row_sha256",
                "c_state_sha256",
                "c_state_row_sha256",
            ):
                if activation_row.get(field) != state_row.get(field):
                    _fail(f"Activation/C source lineage differs at {field}.")
            identity = (
                trajectory_id,
                global_idx,
                activation_row["layer_idx"],
                activation_row["hook_site"],
            )
            if identity in source_frames_seen:
                _fail("Activation identity collides after the rollover boundary.")
            source_frames_seen.add(identity)
            rows_by_site[
                (activation_row["layer_idx"], activation_row["hook_site"])
            ].append((index, activation_row, state_row))
    if len(rows_by_site) != EXPECTED_LAYER_COUNT:
        _fail("Positive-control evidence must contain the 20 frozen layer/sites.")

    matrices: list[PositiveControlMatrixV2] = []
    for (layer_idx, hook_site), joined_rows in sorted(rows_by_site.items()):
        ordered = sorted(
            joined_rows,
            key=lambda value: (
                value[1]["trajectory_id"],
                value[1]["global_model_frame_idx"],
            ),
        )
        if len(ordered) != EXPECTED_VISIBLE_CONTROL_ROWS:
            _fail("Each layer/site must retain exactly 1,000 visible-control rows.")
        features: list[np.ndarray] = []
        targets: list[float] = []
        folds: list[int] = []
        layouts: list[str] = []
        metadata: list[dict[str, Any]] = []
        for index, activation_row, state_row in ordered:
            trajectory_id = activation_row["trajectory_id"]
            layout_id = state_row["layout_id"]
            fold = FROZEN_LAYOUT_FOLDS.get(layout_id)
            if fold is None or authority.fold_by_trajectory[trajectory_id] != fold:
                _fail("Per-row grouped fold differs from the frozen layout assignment.")
            vector = index.vector_for_row(activation_row)
            if (
                vector.dtype != np.float32
                or vector.ndim != 1
                or not bool(np.isfinite(vector).all())
            ):
                _fail("Resolved activation vector is not finite float32 data.")
            features.append(vector)
            targets.append(float(state_row[FROZEN_TARGET_NAME]))
            folds.append(fold)
            layouts.append(layout_id)
            chunk = chunks_by_identity[
                (trajectory_id, activation_row["activation_chunk_id"])
            ]
            metadata.append(
                {
                    "accepted_c_manifest_sha256": index.accepted_manifest_sha256,
                    "activation_chunk_id": activation_row["activation_chunk_id"],
                    "activation_chunk_sha256": chunk["sha256"],
                    "activation_index_sha256": index.index_sha256,
                    "activation_row_identity_sha256": _hash_json(dict(activation_row)),
                    "canonical_state_object_sha256": state_row[
                        "canonical_state_object_sha256"
                    ],
                    "c_frame_map_row_sha256": activation_row["c_frame_map_row_sha256"],
                    "c_frame_map_sha256": activation_row["c_frame_map_sha256"],
                    "c_state_row_sha256": activation_row["c_state_row_sha256"],
                    "c_state_sha256": activation_row["c_state_sha256"],
                    "checkpoint_hash": index.store_identity["checkpoint_hash"],
                    "chunk_row_idx": activation_row["chunk_row_idx"],
                    "config_hash": index.store_identity["config_hash"],
                    "context_local_pair_idx": activation_row["context_local_pair_idx"],
                    "frame_token_map_sha256": activation_row["frame_token_map_sha256"],
                    "global_model_frame_idx": activation_row["global_model_frame_idx"],
                    "hook_site": hook_site,
                    "identity_projection": (
                        "model_frame_idx_is_exact_global_model_frame_idx_alias"
                    ),
                    "layer_idx": layer_idx,
                    "layout_id": layout_id,
                    "literal_capture_package_sha256": state_row[
                        "literal_capture_package_sha256"
                    ],
                    "model_hash": index.store_identity["model_hash"],
                    "model_frame_idx": activation_row["global_model_frame_idx"],
                    "preprocess_hash": index.store_identity["preprocess_hash"],
                    "producing_run_id": activation_row["run_id"],
                    "source_frame_id": activation_row["source_frame_id"],
                    "source_frame_idx": activation_row["source_frame_idx"],
                    "source_tick": activation_row["source_tick"],
                    "trajectory_id": trajectory_id,
                }
            )
        payload = _matrix_identity_payload(
            layer_idx=layer_idx,
            hook_site=hook_site,
            targets=targets,
            folds=folds,
            metadata_rows=metadata,
        )
        matrices.append(
            PositiveControlMatrixV2(
                layer_idx=layer_idx,
                hook_site=hook_site,
                features=tuple(features),
                targets=tuple(targets),
                outer_folds=tuple(folds),
                layout_ids=tuple(layouts),
                metadata_rows=tuple(metadata),
                matrix_hash=_hash_json(payload),
            )
        )

    per_pilot_lineage = []
    for trajectory_id in VISIBLE_CONTROL_PILOT_IDS:
        index = indices_by_trajectory[trajectory_id]
        state = state_inputs_by_trajectory[trajectory_id]
        per_pilot_lineage.append(
            {
                "accepted_c_manifest_sha256": index.accepted_manifest_sha256,
                "activation_index_byte_size": index.index_byte_size,
                "activation_index_sha256": index.index_sha256,
                "activation_row_count": index.activation_row_count,
                "canonical_state_object_sha256": state["canonical_state_object_sha256"],
                "chunk_count": len(index.chunks),
                "chunk_identities": [
                    {
                        "byte_size": chunk["byte_size"],
                        "chunk_id": chunk["chunk_id"],
                        "row_count": chunk["row_count"],
                        "sha256": chunk["sha256"],
                    }
                    for chunk in index.chunks
                ],
                "fold_idx": authority.fold_by_trajectory[trajectory_id],
                "literal_capture_package_sha256": state[
                    "literal_capture_package_sha256"
                ],
                "trajectory_id": trajectory_id,
            }
        )
    input_identity = {
        "format_version": POSITIVE_CONTROL_INPUT_FORMAT_VERSION,
        "frozen_folds": FROZEN_LAYOUT_FOLDS,
        "frozen_target_name": FROZEN_TARGET_NAME,
        "frozen_threshold_policy": FROZEN_THRESHOLD_POLICY,
        "matrix_hashes": [matrix.matrix_hash for matrix in matrices],
        "per_pilot_lineage": per_pilot_lineage,
        "visible_control_layout_count": EXPECTED_VISIBLE_CONTROL_LAYOUT_COUNT,
        "visible_control_row_count": EXPECTED_VISIBLE_CONTROL_ROWS,
    }
    return PositiveControlBridgeV2(
        matrices=tuple(matrices),
        per_pilot_lineage=tuple(per_pilot_lineage),
        row_count=EXPECTED_VISIBLE_CONTROL_ROWS,
        layout_count=EXPECTED_VISIBLE_CONTROL_LAYOUT_COUNT,
        target_name=FROZEN_TARGET_NAME,
        threshold_policy=FROZEN_THRESHOLD_POLICY,
        input_hash=_hash_json(input_identity),
    )


def bridge_lineage_document(bridge: PositiveControlBridgeV2) -> dict[str, Any]:
    """Emit complete row/pilot lineage without embedding or converting vectors."""

    if bridge.scientific_execution_performed:
        _fail("A prepared bridge cannot claim scientific execution.")
    return {
        "e_schema_change_required": False,
        "format_version": POSITIVE_CONTROL_INPUT_FORMAT_VERSION,
        "frozen_fold_unchanged": True,
        "frozen_target_name": bridge.target_name,
        "frozen_target_unchanged": True,
        "frozen_threshold_policy": bridge.threshold_policy,
        "frozen_threshold_unchanged": True,
        "input_hash": bridge.input_hash,
        "layout_count": bridge.layout_count,
        "matrix_lineage": [
            {
                "hook_site": matrix.hook_site,
                "layer_idx": matrix.layer_idx,
                "matrix_hash": matrix.matrix_hash,
                "row_count": len(matrix.targets),
                "rows": [
                    {
                        **dict(row),
                        "outer_fold_idx": fold,
                        "target": target,
                    }
                    for row, fold, target in zip(
                        matrix.metadata_rows,
                        matrix.outer_folds,
                        matrix.targets,
                        strict=True,
                    )
                ],
            }
            for matrix in bridge.matrices
        ],
        "per_pilot_lineage": [dict(row) for row in bridge.per_pilot_lineage],
        "row_count": bridge.row_count,
        "schema_version": "1.0",
        "scientific_execution_performed": False,
        "u4_output_inspected": False,
    }


__all__ = [
    "ALL_PILOT_IDS",
    "CORE_PILOT_IDS",
    "EXPECTED_ACTIVATION_CHUNK_COUNT",
    "EXPECTED_ACTIVATION_INDEX_COUNT",
    "EXPECTED_TOTAL_ACTIVATION_ROWS",
    "EXPECTED_VISIBLE_CONTROL_LAYOUT_COUNT",
    "EXPECTED_VISIBLE_CONTROL_ROWS",
    "FROZEN_LAYOUT_FOLDS",
    "FROZEN_TARGET_NAME",
    "FROZEN_THRESHOLD_POLICY",
    "PERSON_A_TEN_PILOT_COMMIT",
    "PERSON_B_AUTHORIZATION_COMMIT",
    "PERSON_B_SELECTION_COMMIT",
    "PERSON_C_ACCEPTANCE_COMMIT",
    "POSITIVE_CONTROL_INPUT_FORMAT_VERSION",
    "VISIBLE_CONTROL_PILOT_IDS",
    "PositiveControlBridgeV2",
    "PositiveControlMatrixV2",
    "PositiveControlV2Error",
    "TenPilotEvidenceBinding",
    "bridge_lineage_document",
    "build_positive_control_bridge_v2",
    "validate_loaded_ten_pilot_indices",
    "validate_ten_pilot_authority_documents",
]
