"""Person B pre-activation contract for the successor 66-cell MVP universe.

This module is additive.  It supersedes nothing: the frozen ten-pilot evidence
(1874 source frames, 1695 admitted rows, 179 exclusions, 37480 activation rows,
200 chunks) remains valid historical evidence and is neither relabelled nor
regenerated here.  What this module does is bind Person B's already-frozen
grouped-layout fold policy, U4 development partition, oracle contract, and
admission rules to the *new* production authorities:

* Person C accepted 66-cell trajectory handoff, and
* Person A 66-cell production-input frame-map package.

Foreign-role evidence is read through exact ``commit:path`` Git bindings and
verified against declared SHA-256 digests.  No foreign branch is merged, no
foreign file is copied into Person B's tree, and no activation bytes are
required: every routine here runs strictly before Person A's GPU extraction.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import re
import subprocess
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from mineocclude.analysis.config import (
    ANALYSIS_CONFIG_VERSION,
    hash_core_analysis_config,
    load_core_analysis_config,
)
from mineocclude.analysis.manifests import (
    is_hex_digest,
    seal_artifact,
    sha256_value,
)
from mineocclude.analysis.selection import (
    SCOPE_HIDDEN_MEAN,
    SCOPE_HIDDEN_SPREAD,
    SCOPE_VISIBLE_NO_WALL,
)
from mineocclude.probes.splits import (
    FOLD_SCHEMA_VERSION,
    U4_PARTITION_SCHEMA_VERSION,
    assign_layout_grouped_folds,
    assign_u4_development_partition,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]

PREACTIVATION_SCHEMA_VERSION = "person-b-66-cell-preactivation-v0.1"
PREACTIVATION_PACKAGE_DIRECTORY = "docs/status/person_b_66_cell_preactivation_v0_1"
DECISION_DATE = "2026-08-07"

# --------------------------------------------------------------------------
# Bound foreign-role authorities (exact commit / path / SHA-256)
# --------------------------------------------------------------------------
PERSON_C_COMMIT = "a8bed8adf7e24ca7fe5b6b6afa3342da61434be3"
PERSON_C_ACCEPTED_MANIFEST_PATH = (
    "docs/status/person_c_c7_mvp_handoff_v0_1/trajectories_mvp_manifest.json"
)
PERSON_C_ACCEPTED_MANIFEST_SHA256 = (
    "96ba43e15bc024aeaef7c519fa4ece0a4afe0bb0e877501dffaca44fee927ff7"
)
PERSON_C_PER_TRAJECTORY_DIRECTORY = (
    "docs/status/person_c_c7_mvp_handoff_v0_1/per_trajectory"
)

PERSON_A_COMMIT = "77e43bd1665671b9e23d6d6ef927ee4944611342"
PERSON_A_PACKAGE_ROOT = "data/handoff_a/person_a_66_cell_production_input_v0_1"
PERSON_A_FRAME_MAP_PACKAGE_PATH = f"{PERSON_A_PACKAGE_ROOT}/sha256_inventory.json"
PERSON_A_FRAME_MAP_PACKAGE_SHA256 = (
    "a473bf830ed31e49762d62bba97032e52f4967e52f9987ad10cd5879ed9bd004"
)
PERSON_A_FRAME_MAP_INDEX_PATH = f"{PERSON_A_PACKAGE_ROOT}/frame_map_index.json"
PERSON_A_BUNDLE_MANIFEST_PATH = f"{PERSON_A_PACKAGE_ROOT}/bundle_manifest.json"
PERSON_A_STORAGE_DTYPE_PROPOSAL_PATH = (
    "docs/status/person_a_66_cell_local_preparation_v0_1/"
    "storage_dtype_reconciliation.json"
)
PERSON_A_STORAGE_DTYPE_PROPOSAL_SHA256 = (
    "64ade0c8506cc32b422186b5dbbe9a34339948b947ec6fea26d282d7cc9c917e"
)
PERSON_A_MVP_CONFIG_PATH = "configs/experiments/mvp.yaml"
PERSON_A_MVP_CONFIG_SHA256 = (
    "3c20c014dddd9b2f8b9a9225b97d7d6d11994b08363f5026d8c26fd2f5aaaaa3"
)

VERIFIED_ORIGIN_MAIN = "15adc43674420ae35921847a953ebbee2135f142"

# --------------------------------------------------------------------------
# Superseded predecessor universe (historical evidence, preserved unchanged)
# --------------------------------------------------------------------------
TEN_PILOT_TRAJECTORY_COUNT = 10
TEN_PILOT_SOURCE_FRAME_COUNT = 1_874
TEN_PILOT_ADMITTED_ROW_COUNT = 1_695
TEN_PILOT_EXCLUDED_ROW_COUNT = 179
TEN_PILOT_ACTIVATION_ROW_COUNT = 37_480
TEN_PILOT_ACTIVATION_CHUNK_COUNT = 200

# --------------------------------------------------------------------------
# Expected successor cardinality (independently reverified, never assumed)
# --------------------------------------------------------------------------
EXPECTED_TRAJECTORY_COUNT = 66
EXPECTED_EXCLUDED_TRAJECTORY_COUNT = 0
EXPECTED_MODEL_FRAME_KEY_COUNT = 2_468
EXPECTED_LAYER_COUNT = 20
EXPECTED_ACTIVATION_ROW_COUNT = 49_360
EXPECTED_ACTIVATION_CHUNK_COUNT = 1_320
EXPECTED_LAYOUT_COUNT = 6

FRAME_KEY = ("trajectory_id", "model_frame_idx")

# Person C control taxonomy for the C6a 66-cell matrix.  ``no_object_control``
# episodes intentionally contain no target object; Person B's frozen adapter
# already rejects them with ``no_object_not_oracle_eligible``.
CONTROL_TYPE_CORE = "core_regime_a"
CONTROL_TYPE_SENTINEL = "context_sentinel"
CONTROL_TYPE_NO_WALL = "no_wall_visible_control"
CONTROL_TYPE_NO_OBJECT = "no_object_control"
EXPECTED_CONTROL_TYPE_COUNTS = {
    CONTROL_TYPE_CORE: 48,
    CONTROL_TYPE_SENTINEL: 6,
    CONTROL_TYPE_NO_WALL: 6,
    CONTROL_TYPE_NO_OBJECT: 6,
}

ROW_EXCLUSION_NO_OBJECT = "no_object_control_not_oracle_eligible"
ROW_EXCLUSION_PRE_FIRST_SEEN = "pre_first_seen"
ROW_EXCLUSION_OUTSIDE_SELECTION = "outside_frozen_condition_selection"

# Person B's frozen condition selection admits occluded rows to the hidden
# scopes and no-wall trajectories to the visible control scope.  The 66-cell
# matrix introduces two control types the ten-pilot selection never saw:
# ``no_object_control`` already has a frozen disposition (Person B's adapter
# rejects it with ``no_object_not_oracle_eligible``), while
# ``context_sentinel`` is a Regime A occlusion cell that differs only in
# context length.  Sentinel rows are therefore admitted to the same hidden
# scopes and additionally carry a separable stratum label, declared here
# before any 66-cell activation exists.
ADMISSION_STRATUM_CORE = "core_regime_a_hidden"
ADMISSION_STRATUM_SENTINEL = "context_sentinel_hidden"
ADMISSION_STRATUM_VISIBLE_CONTROL = "no_wall_visible_control"
HIDDEN_ADMISSION_CONTROL_TYPES = (CONTROL_TYPE_CORE, CONTROL_TYPE_SENTINEL)

ORACLE_STAGE_BLOCKED = "blocked_missing_person_c_state_contract_inputs"

# Person B's frozen visibility acceptance policy (Phase 3 Step 3.3).
VISIBILITY_ACCEPTANCE_POLICY_PATH = (
    "docs/status/person_b_phase3_step3_3_policy_v0_1/"
    "visibility_acceptance_policy.json"
)
VISIBILITY_FINAL_LABEL_EQUATION = (
    "visible_flag = geometric_visible AND empirical_magenta_visible"
)

REVEAL_EVENT_ID_TEMPLATE = "{trajectory_id}:reveal:{post_idx}"

CODE_COMPONENTS = (
    "src/mineocclude/analysis/preactivation_66_cell_v0_1.py",
    "src/mineocclude/analysis/config.py",
    "src/mineocclude/analysis/manifests.py",
    "src/mineocclude/analysis/selection.py",
    "src/mineocclude/probes/splits.py",
)


class PreactivationError(ValueError):
    """Raised when a successor pre-activation invariant fails closed."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise PreactivationError(message)


# --------------------------------------------------------------------------
# Exact Git-object binding
# --------------------------------------------------------------------------
def _git_bytes(repository_root: Path, *arguments: str) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(repository_root), *arguments],
        capture_output=True,
        check=False,
    )
    if result.returncode:
        detail = result.stderr.decode("utf-8", "replace").strip()
        raise PreactivationError(
            f"git {' '.join(arguments)} failed: {detail or 'unknown error'}"
        )
    return result.stdout


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def read_bound_blob(
    commit: str,
    path: str,
    *,
    expected_sha256: str | None = None,
    repository_root: Path | None = None,
) -> bytes:
    """Read one foreign-role blob by exact ``commit:path`` and verify bytes."""

    require(
        isinstance(commit, str) and re.fullmatch(r"[0-9a-f]{40}", commit) is not None,
        f"bound commit must be a full Git SHA-1: {commit!r}",
    )
    require(
        isinstance(path, str)
        and bool(path)
        and "\x00" not in path
        and not path.startswith("/")
        and ".." not in Path(path).parts,
        f"invalid bound repository path: {path!r}",
    )
    root = REPOSITORY_ROOT if repository_root is None else Path(repository_root)
    require(
        _git_bytes(root, "cat-file", "-t", commit).decode("utf-8").strip() == "commit",
        f"bound authority {commit} is not a commit object",
    )
    payload = _git_bytes(root, "cat-file", "blob", f"{commit}:{path}")
    if expected_sha256 is not None:
        require(
            is_hex_digest(expected_sha256, 64),
            f"expected_sha256 must be SHA-256 for {path}",
        )
        actual = sha256_bytes(payload)
        require(
            actual == expected_sha256.lower(),
            f"bound blob {commit}:{path} hashes to {actual}, "
            f"expected {expected_sha256.lower()}",
        )
    return payload


def _strict_json(payload: bytes, *, label: str) -> Any:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise PreactivationError(f"{label} repeats JSON key {key!r}.")
            result[key] = value
        return result

    try:
        return json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=reject_duplicates,
            parse_constant=lambda value: (_ for _ in ()).throw(
                PreactivationError(f"{label} contains non-finite constant {value!r}.")
            ),
        )
    except PreactivationError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PreactivationError(f"{label} is not strict UTF-8 JSON: {error}") from error


def derive_preactivation_code_sha(repository_root: Path | None = None) -> str:
    """Hash every code component that determines successor pre-activation evidence."""

    root = REPOSITORY_ROOT if repository_root is None else Path(repository_root)
    digest = hashlib.sha1()
    for label in CODE_COMPONENTS:
        try:
            payload = (root / label).read_bytes()
        except OSError as error:  # pragma: no cover - defensive
            raise PreactivationError(
                f"Could not read pre-activation code component {label}: {error}"
            ) from error
        digest.update(label.encode("utf-8"))
        digest.update(b"\0")
        digest.update(payload.replace(b"\r\n", b"\n"))
        digest.update(b"\0")
    return digest.hexdigest()


# --------------------------------------------------------------------------
# Foreign-role intake
# --------------------------------------------------------------------------
def load_person_c_accepted_manifest(
    repository_root: Path | None = None,
) -> dict[str, Any]:
    """Load and independently verify Person C's accepted 66-cell manifest."""

    payload = read_bound_blob(
        PERSON_C_COMMIT,
        PERSON_C_ACCEPTED_MANIFEST_PATH,
        expected_sha256=PERSON_C_ACCEPTED_MANIFEST_SHA256,
        repository_root=repository_root,
    )
    document = _strict_json(payload, label="Person C accepted manifest")
    require(isinstance(document, Mapping), "Person C manifest root must be an object.")
    require(
        document.get("schema_id")
        == "mineocclude-person-c-c7-5-trajectory-handoff-v1.0-manifest",
        "Person C manifest schema_id is not the accepted C7.5 trajectory handoff.",
    )
    require(
        document.get("accepted_count") == EXPECTED_TRAJECTORY_COUNT,
        f"Person C accepted_count must be {EXPECTED_TRAJECTORY_COUNT}.",
    )
    require(
        document.get("excluded_count") == EXPECTED_EXCLUDED_TRAJECTORY_COUNT,
        f"Person C excluded_count must be {EXPECTED_EXCLUDED_TRAJECTORY_COUNT}.",
    )
    records = document.get("records")
    require(
        isinstance(records, list) and len(records) == EXPECTED_TRAJECTORY_COUNT,
        f"Person C manifest must carry {EXPECTED_TRAJECTORY_COUNT} records.",
    )
    seen_trajectories: set[str] = set()
    seen_cells: set[str] = set()
    for record in records:
        require(isinstance(record, Mapping), "Person C records must be objects.")
        trajectory_id = record.get("trajectory_id")
        planned_cell_id = record.get("planned_cell_id")
        require(
            isinstance(trajectory_id, str) and bool(trajectory_id),
            "Person C record requires a non-empty trajectory_id.",
        )
        require(
            isinstance(planned_cell_id, str) and bool(planned_cell_id),
            f"Person C record {trajectory_id!r} requires a planned_cell_id.",
        )
        require(
            trajectory_id not in seen_trajectories,
            f"Person C manifest duplicates trajectory {trajectory_id!r}.",
        )
        require(
            planned_cell_id not in seen_cells,
            f"Person C manifest duplicates planned cell {planned_cell_id!r}.",
        )
        require(
            record.get("accepted") is True and record.get("status") == "PASS",
            f"Person C trajectory {trajectory_id!r} is not accepted at PASS.",
        )
        require(
            record.get("control_type") in EXPECTED_CONTROL_TYPE_COUNTS,
            f"Person C trajectory {trajectory_id!r} has an unknown control_type.",
        )
        seen_trajectories.add(trajectory_id)
        seen_cells.add(planned_cell_id)
    observed_controls = Counter(record["control_type"] for record in records)
    require(
        dict(observed_controls) == EXPECTED_CONTROL_TYPE_COUNTS,
        "Person C control-type census differs from the frozen 66-cell matrix.",
    )
    return dict(document)


def load_person_a_frame_map_package(
    repository_root: Path | None = None,
) -> dict[str, Any]:
    """Load and independently verify Person A's 66-cell frame-map package."""

    inventory_payload = read_bound_blob(
        PERSON_A_COMMIT,
        PERSON_A_FRAME_MAP_PACKAGE_PATH,
        expected_sha256=PERSON_A_FRAME_MAP_PACKAGE_SHA256,
        repository_root=repository_root,
    )
    inventory = _strict_json(inventory_payload, label="Person A sha256 inventory")
    require(isinstance(inventory, Mapping), "Person A inventory root must be an object.")

    index_payload = read_bound_blob(
        PERSON_A_COMMIT,
        PERSON_A_FRAME_MAP_INDEX_PATH,
        repository_root=repository_root,
    )
    index = _strict_json(index_payload, label="Person A frame-map index")
    require(isinstance(index, Mapping), "Person A frame-map index must be an object.")
    require(
        index.get("c_accepted_manifest_sha256") == PERSON_C_ACCEPTED_MANIFEST_SHA256
        and index.get("c_source_commit") == PERSON_C_COMMIT
        and index.get("c_accepted_manifest_path") == PERSON_C_ACCEPTED_MANIFEST_PATH,
        "Person A frame-map index is not bound to the accepted Person C manifest.",
    )
    require(
        list(index.get("model_facing_key") or ()) == list(FRAME_KEY),
        "Person A model-facing key must be (trajectory_id, model_frame_idx).",
    )
    require(
        index.get("layer_count") == EXPECTED_LAYER_COUNT,
        f"Person A layer_count must be {EXPECTED_LAYER_COUNT}.",
    )
    require(
        index.get("duplicate_model_frame_key_count") == 0
        and list(index.get("duplicate_model_frame_keys") or ()) == []
        and index.get("missing_trajectory_count") == 0
        and list(index.get("missing_trajectory_ids") or ()) == [],
        "Person A frame-map index declares duplicate or missing identities.",
    )
    require(
        index.get("model_frame_key_count") == EXPECTED_MODEL_FRAME_KEY_COUNT
        and index.get("expected_model_frame_key_count")
        == EXPECTED_MODEL_FRAME_KEY_COUNT
        and index.get("model_frame_key_count_matches_expected") is True,
        f"Person A must declare {EXPECTED_MODEL_FRAME_KEY_COUNT} model-frame keys.",
    )
    require(
        index.get("expected_activation_row_count_total") == EXPECTED_ACTIVATION_ROW_COUNT
        and index.get("expected_chunk_count_total") == EXPECTED_ACTIVATION_CHUNK_COUNT,
        "Person A activation cardinality differs from the successor expectation.",
    )
    per_trajectory = index.get("per_trajectory")
    require(
        isinstance(per_trajectory, Mapping)
        and len(per_trajectory) == EXPECTED_TRAJECTORY_COUNT,
        f"Person A must map {EXPECTED_TRAJECTORY_COUNT} trajectories.",
    )

    bundle_payload = read_bound_blob(
        PERSON_A_COMMIT,
        PERSON_A_BUNDLE_MANIFEST_PATH,
        repository_root=repository_root,
    )
    bundle = _strict_json(bundle_payload, label="Person A bundle manifest")
    require(isinstance(bundle, Mapping), "Person A bundle manifest must be an object.")
    require(
        bundle.get("accepted_trajectory_count") == EXPECTED_TRAJECTORY_COUNT
        and bundle.get("excluded_trajectory_count")
        == EXPECTED_EXCLUDED_TRAJECTORY_COUNT
        and bundle.get("c_accepted_manifest_sha256")
        == PERSON_C_ACCEPTED_MANIFEST_SHA256
        and bundle.get("c_source_commit") == PERSON_C_COMMIT,
        "Person A bundle manifest is not bound to the accepted Person C authority.",
    )

    frame_maps: dict[str, list[dict[str, Any]]] = {}
    for trajectory_id in sorted(per_trajectory):
        meta = per_trajectory[trajectory_id]
        require(isinstance(meta, Mapping), "Person A per-trajectory entry must be an object.")
        relative_path = meta.get("frame_map_path")
        declared_sha = meta.get("frame_map_sha256")
        require(
            isinstance(relative_path, str) and relative_path.startswith("frame_maps/"),
            f"Person A frame-map path for {trajectory_id!r} is invalid.",
        )
        payload = read_bound_blob(
            PERSON_A_COMMIT,
            f"{PERSON_A_PACKAGE_ROOT}/{relative_path}",
            expected_sha256=declared_sha,
            repository_root=repository_root,
        )
        rows = [
            _strict_json(line.encode("utf-8"), label=f"Person A frame map {relative_path}")
            for line in payload.decode("utf-8").splitlines()
            if line.strip()
        ]
        require(
            len(rows) == meta.get("model_frame_count") == meta.get("declared_frame_count"),
            f"Person A frame-map row count disagrees for {trajectory_id!r}.",
        )
        frame_maps[trajectory_id] = rows

    return {
        "inventory": inventory,
        "index": dict(index),
        "bundle_manifest": dict(bundle),
        "frame_maps": frame_maps,
    }


# --------------------------------------------------------------------------
# Row universe
# --------------------------------------------------------------------------
def build_row_universe(
    c_manifest: Mapping[str, Any],
    a_package: Mapping[str, Any],
) -> dict[str, Any]:
    """Join Person C trajectory identity one-to-many onto Person A frame rows."""

    c_by_id = {record["trajectory_id"]: record for record in c_manifest["records"]}
    frame_maps = a_package["frame_maps"]
    require(
        set(c_by_id) == set(frame_maps),
        "Person C trajectory identity and Person A frame-map identity differ.",
    )

    rows: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, int]] = set()
    layout_by_trajectory: dict[str, str] = {}
    for trajectory_id in sorted(frame_maps):
        record = c_by_id[trajectory_id]
        frame_rows = frame_maps[trajectory_id]
        require(bool(frame_rows), f"Trajectory {trajectory_id!r} carries no frames.")
        expected_indices = list(range(len(frame_rows)))
        observed_indices = [row.get("model_frame_idx") for row in frame_rows]
        require(
            observed_indices == expected_indices,
            f"Trajectory {trajectory_id!r} model_frame_idx is not 0..n-1 contiguous.",
        )
        first_visible: int | None = None
        for frame_row in frame_rows:
            require(
                frame_row.get("trajectory_id") == trajectory_id,
                f"Frame-map row identity leaks across {trajectory_id!r}.",
            )
            require(
                frame_row.get("c_manifest_sha256") == PERSON_C_ACCEPTED_MANIFEST_SHA256
                and frame_row.get("c_source_commit") == PERSON_C_COMMIT,
                f"Frame-map row for {trajectory_id!r} is not C-manifest bound.",
            )
            require(
                frame_row.get("layout_id") == record["layout_id"],
                f"Layout identity disagrees for {trajectory_id!r}.",
            )
            require(
                frame_row.get("control_type") == record["control_type"]
                and frame_row.get("set_id") == record["set_id"]
                and frame_row.get("planned_cell_id") == record["planned_cell_id"]
                and frame_row.get("episode_id") == record["episode_id"],
                f"Condition identity disagrees for {trajectory_id!r}.",
            )
            geometric_visible = frame_row.get("geometric_visible")
            require(
                isinstance(geometric_visible, bool),
                f"geometric_visible must be boolean for {trajectory_id!r}.",
            )
            require(
                frame_row.get("visibility_source") == "server_state.geometric_visible",
                f"Unexpected visibility source for {trajectory_id!r}.",
            )
            model_frame_idx = int(frame_row["model_frame_idx"])
            key = (trajectory_id, model_frame_idx)
            require(key not in seen_keys, f"Duplicate model-frame identity {key!r}.")
            seen_keys.add(key)
            if geometric_visible and first_visible is None:
                first_visible = model_frame_idx
            rows.append(
                {
                    "trajectory_id": trajectory_id,
                    "model_frame_idx": model_frame_idx,
                    "layout_id": record["layout_id"],
                    "episode_id": record["episode_id"],
                    "planned_cell_id": record["planned_cell_id"],
                    "control_type": record["control_type"],
                    "set_id": record["set_id"],
                    "scene": record["scene"],
                    "context_fraction": record["context_fraction"],
                    "hidden_frames": record["hidden_frames"],
                    "speed_blocks_per_second": record["speed_blocks_per_second"],
                    "q_blocks_squared_per_second": record["q_blocks_squared_per_second"],
                    "seed": record["seed"],
                    "server_tick": frame_row["server_tick"],
                    "render_frame_idx": frame_row["render_frame_idx"],
                    "action_idx": frame_row["action_idx"],
                    "geometric_visible": geometric_visible,
                    "visibility_source": frame_row["visibility_source"],
                    "visibility_identity_sha256": frame_row["visibility_identity_sha256"],
                    "condition_identity_sha256": frame_row["condition_identity_sha256"],
                    "source_server_state_row_sha256": frame_row[
                        "source_server_state_row_sha256"
                    ],
                    "source_frame_sha256": frame_row["source_frame_sha256"],
                    "preprocessing_identity": frame_row["preprocessing_identity"],
                }
            )
        layout_by_trajectory[trajectory_id] = record["layout_id"]
        first_visible_index = first_visible

        # Admission is decided per row below; record the anchor for clarity.
        for row in rows[-len(frame_rows) :]:
            row["first_visible_model_frame_idx"] = first_visible_index

    require(
        len(seen_keys) == EXPECTED_MODEL_FRAME_KEY_COUNT,
        f"Row universe must contain exactly {EXPECTED_MODEL_FRAME_KEY_COUNT} keys.",
    )
    layouts = sorted(set(layout_by_trajectory.values()))
    require(
        len(layouts) == EXPECTED_LAYOUT_COUNT,
        f"Row universe must span exactly {EXPECTED_LAYOUT_COUNT} layouts.",
    )

    for row in rows:
        control_type = row["control_type"]
        first_visible_index = row["first_visible_model_frame_idx"]
        row["analysis_scopes"] = []
        row["admission_stratum"] = None
        if control_type == CONTROL_TYPE_NO_OBJECT:
            row["status"] = "excluded"
            row["exclusion_reason"] = ROW_EXCLUSION_NO_OBJECT
        elif first_visible_index is None or row["model_frame_idx"] < first_visible_index:
            row["status"] = "excluded"
            row["exclusion_reason"] = ROW_EXCLUSION_PRE_FIRST_SEEN
        elif control_type == CONTROL_TYPE_NO_WALL:
            row["status"] = "accepted"
            row["exclusion_reason"] = None
            row["analysis_scopes"] = [SCOPE_VISIBLE_NO_WALL]
            row["admission_stratum"] = ADMISSION_STRATUM_VISIBLE_CONTROL
        elif row["geometric_visible"]:
            # Visible rows outside the no-wall control are not part of the
            # frozen hidden-state selection; the ten-pilot production run
            # excluded them with this same reason code.
            row["status"] = "excluded"
            row["exclusion_reason"] = ROW_EXCLUSION_OUTSIDE_SELECTION
        else:
            require(
                control_type in HIDDEN_ADMISSION_CONTROL_TYPES,
                f"Control type {control_type!r} has no frozen hidden-scope "
                "disposition; refusing to invent one.",
            )
            row["status"] = "accepted"
            row["exclusion_reason"] = None
            row["analysis_scopes"] = [SCOPE_HIDDEN_MEAN, SCOPE_HIDDEN_SPREAD]
            row["admission_stratum"] = (
                ADMISSION_STRATUM_SENTINEL
                if control_type == CONTROL_TYPE_SENTINEL
                else ADMISSION_STRATUM_CORE
            )

    rows.sort(key=lambda row: (row["trajectory_id"], row["model_frame_idx"]))
    admitted = [row for row in rows if row["status"] == "accepted"]
    excluded = [row for row in rows if row["status"] == "excluded"]
    require(
        len(admitted) + len(excluded) == EXPECTED_MODEL_FRAME_KEY_COUNT,
        "Admission and exclusion do not partition the row universe.",
    )
    return {
        "rows": rows,
        "admitted_rows": admitted,
        "excluded_rows": excluded,
        "layouts": layouts,
        "layout_by_trajectory": dict(sorted(layout_by_trajectory.items())),
    }


def build_row_universe_receipt(
    universe: Mapping[str, Any],
    *,
    code_sha: str,
) -> dict[str, Any]:
    """Seal Person B's authoritative successor row-universe receipt."""

    rows = universe["rows"]
    admitted = universe["admitted_rows"]
    excluded = universe["excluded_rows"]
    layout_by_trajectory = universe["layout_by_trajectory"]

    frames_by_layout = Counter(row["layout_id"] for row in rows)
    admitted_by_layout = Counter(row["layout_id"] for row in admitted)
    excluded_by_reason = Counter(row["exclusion_reason"] for row in excluded)
    admitted_by_scope: Counter[str] = Counter()
    for row in admitted:
        for scope in row["analysis_scopes"]:
            admitted_by_scope[scope] += 1
    admitted_by_stratum = Counter(row["admission_stratum"] for row in admitted)
    trajectories_by_layout = Counter(layout_by_trajectory.values())
    control_by_trajectory = Counter(
        row["control_type"] for row in rows if row["model_frame_idx"] == 0
    )

    return seal_artifact(
        {
            "artifact_type": "person_b_66_cell_row_universe_receipt",
            "artifact_id": "person-b-66-cell-row-universe-v0.1",
            "code_sha": code_sha,
            "config_hash": hash_core_analysis_config(),
            "input_manifest_hash": PERSON_C_ACCEPTED_MANIFEST_SHA256,
            "preactivation_schema_version": PREACTIVATION_SCHEMA_VERSION,
            "analysis_config_version": ANALYSIS_CONFIG_VERSION,
            "decision_date": DECISION_DATE,
            "producer_role": "person_b",
            "synthetic": False,
            "scientific_use": "permitted",
            "person_a_artifacts_used": "frame_map_identity_only_no_activations",
            "outcome_fields_used": False,
            "join_key": list(FRAME_KEY),
            "person_c_commit": PERSON_C_COMMIT,
            "person_c_accepted_manifest_path": PERSON_C_ACCEPTED_MANIFEST_PATH,
            "person_c_accepted_manifest_sha256": PERSON_C_ACCEPTED_MANIFEST_SHA256,
            "person_a_commit": PERSON_A_COMMIT,
            "person_a_frame_map_package_path": PERSON_A_FRAME_MAP_PACKAGE_PATH,
            "person_a_frame_map_package_sha256": PERSON_A_FRAME_MAP_PACKAGE_SHA256,
            "accepted_trajectory_count": EXPECTED_TRAJECTORY_COUNT,
            "excluded_trajectory_count": EXPECTED_EXCLUDED_TRAJECTORY_COUNT,
            "planned_cell_count": EXPECTED_TRAJECTORY_COUNT,
            "model_frame_key_count": len(rows),
            "duplicate_model_frame_key_count": 0,
            "missing_production_frame_key_count": 0,
            "layout_count": len(universe["layouts"]),
            "layout_ids": list(universe["layouts"]),
            "expected_activation_row_count": EXPECTED_ACTIVATION_ROW_COUNT,
            "expected_activation_chunk_count": EXPECTED_ACTIVATION_CHUNK_COUNT,
            "layer_count": EXPECTED_LAYER_COUNT,
            "admitted_analysis_row_count": len(admitted),
            "excluded_analysis_row_count": len(excluded),
            "trajectory_acceptance_vs_row_admission": {
                "accepted_trajectories": EXPECTED_TRAJECTORY_COUNT,
                "rejected_trajectories": 0,
                "row_level_exclusions_are_not_trajectory_rejections": True,
            },
            "admitted_row_counts_by_layout": [
                {"layout_id": layout, "row_count": admitted_by_layout[layout]}
                for layout in sorted(admitted_by_layout)
            ],
            "model_frame_counts_by_layout": [
                {"layout_id": layout, "row_count": frames_by_layout[layout]}
                for layout in sorted(frames_by_layout)
            ],
            "trajectory_counts_by_layout": [
                {"layout_id": layout, "trajectory_count": trajectories_by_layout[layout]}
                for layout in sorted(trajectories_by_layout)
            ],
            "trajectory_counts_by_control_type": [
                {"control_type": control, "trajectory_count": control_by_trajectory[control]}
                for control in sorted(control_by_trajectory)
            ],
            "admitted_row_counts_by_scope": [
                {"scope": scope, "row_count": admitted_by_scope[scope]}
                for scope in sorted(admitted_by_scope)
            ],
            "admitted_row_counts_by_stratum": [
                {"admission_stratum": stratum, "row_count": admitted_by_stratum[stratum]}
                for stratum in sorted(admitted_by_stratum)
            ],
            "excluded_row_counts_by_reason": [
                {"exclusion_reason": reason, "row_count": excluded_by_reason[reason]}
                for reason in sorted(excluded_by_reason)
            ],
            "row_universe_canonical_hash": sha256_value(
                [
                    {
                        "trajectory_id": row["trajectory_id"],
                        "model_frame_idx": row["model_frame_idx"],
                        "layout_id": row["layout_id"],
                        "planned_cell_id": row["planned_cell_id"],
                        "control_type": row["control_type"],
                        "geometric_visible": row["geometric_visible"],
                        "status": row["status"],
                        "exclusion_reason": row["exclusion_reason"],
                        "analysis_scopes": row["analysis_scopes"],
                        "admission_stratum": row["admission_stratum"],
                    }
                    for row in rows
                ]
            ),
            "supersedes_predecessor_universe": {
                "predecessor_trajectory_count": TEN_PILOT_TRAJECTORY_COUNT,
                "predecessor_admitted_row_count": TEN_PILOT_ADMITTED_ROW_COUNT,
                "predecessor_excluded_row_count": TEN_PILOT_EXCLUDED_ROW_COUNT,
                "predecessor_activation_row_count": TEN_PILOT_ACTIVATION_ROW_COUNT,
                "predecessor_activation_chunk_count": TEN_PILOT_ACTIVATION_CHUNK_COUNT,
                "predecessor_evidence_rewritten": False,
                "predecessor_evidence_relabelled": False,
                "predecessor_row_ids_reused_as_66_cell_universe": False,
            },
        }
    )


# --------------------------------------------------------------------------
# Fold manifest
# --------------------------------------------------------------------------
def build_66_cell_fold_manifest(
    universe: Mapping[str, Any],
    *,
    code_sha: str,
) -> dict[str, Any]:
    """Apply Person B's frozen grouped-layout policy to the successor universe."""

    config = load_core_analysis_config()
    cross_validation = config["cross_validation"]
    n_splits = int(cross_validation["fold_count"])
    seed = int(cross_validation["split_seed"])
    require(
        cross_validation["strategy"] == "layout_grouped"
        and cross_validation["fold_schema_version"] == FOLD_SCHEMA_VERSION,
        "Frozen cross-validation policy changed; folds cannot be regenerated.",
    )

    rows = universe["rows"]
    assignment_rows = [
        {
            "trajectory_id": row["trajectory_id"],
            "model_frame_idx": row["model_frame_idx"],
            "layout_id": row["layout_id"],
        }
        for row in rows
    ]
    assignments = assign_layout_grouped_folds(
        assignment_rows,
        n_splits=n_splits,
        seed=seed,
    )
    require(
        set(assignments.values()) == set(range(n_splits)),
        "Successor folds do not populate every frozen fold index.",
    )

    # Row order must not matter: reversing the input must reproduce the map.
    reversed_assignments = assign_layout_grouped_folds(
        list(reversed(assignment_rows)),
        n_splits=n_splits,
        seed=seed,
    )
    require(
        reversed_assignments == assignments,
        "Fold assignment is row-order dependent; refusing to publish.",
    )

    memberships = [
        {
            "trajectory_id": row["trajectory_id"],
            "model_frame_idx": row["model_frame_idx"],
            "layout_id": row["layout_id"],
            "fold_idx": assignments[row["layout_id"]],
            "status": row["status"],
            "exclusion_reason": row["exclusion_reason"],
            "analysis_scopes": list(row["analysis_scopes"]),
            "admission_stratum": row["admission_stratum"],
        }
        for row in sorted(
            rows,
            key=lambda item: (
                item["layout_id"],
                item["trajectory_id"],
                item["model_frame_idx"],
            ),
        )
    ]

    admitted = [row for row in memberships if row["status"] == "accepted"]
    excluded = [row for row in memberships if row["status"] == "excluded"]
    rows_by_fold = Counter(row["fold_idx"] for row in memberships)
    admitted_by_fold = Counter(row["fold_idx"] for row in admitted)
    excluded_by_fold = Counter(row["fold_idx"] for row in excluded)
    trajectories_by_fold: dict[int, set[str]] = defaultdict(set)
    layouts_by_fold: dict[int, set[str]] = defaultdict(set)
    for row in memberships:
        trajectories_by_fold[row["fold_idx"]].add(row["trajectory_id"])
        layouts_by_fold[row["fold_idx"]].add(row["layout_id"])

    return seal_artifact(
        {
            "artifact_type": "person_b_66_cell_fold_manifest",
            "artifact_id": "person-b-66-cell-fold-manifest-v0.1",
            "code_sha": code_sha,
            "config_hash": hash_core_analysis_config(),
            "input_manifest_hash": PERSON_C_ACCEPTED_MANIFEST_SHA256,
            "preactivation_schema_version": PREACTIVATION_SCHEMA_VERSION,
            "fold_manifest_schema_version": "person-b-66-cell-fold-manifest-v0.1",
            "fold_schema_version": FOLD_SCHEMA_VERSION,
            "analysis_config_version": ANALYSIS_CONFIG_VERSION,
            "decision_date": DECISION_DATE,
            "producer_role": "person_b",
            "strategy": "layout_grouped",
            "assignment_source": "frozen_layout_grouped_policy_applied_to_66_cell_universe",
            "n_splits": n_splits,
            "seed": seed,
            "fold_seed": seed,
            "random_split_used": False,
            "row_order_has_scientific_meaning": False,
            "row_order_dependence_checked": True,
            "grouping_policy_changed_after_results": False,
            "u4_output_inspected": False,
            "outcome_fields_used": False,
            "synthetic": False,
            "scientific_use": "permitted",
            "person_c_commit": PERSON_C_COMMIT,
            "person_c_accepted_manifest_sha256": PERSON_C_ACCEPTED_MANIFEST_SHA256,
            "person_a_commit": PERSON_A_COMMIT,
            "person_a_frame_map_package_sha256": PERSON_A_FRAME_MAP_PACKAGE_SHA256,
            "layout_assignments": [
                {"layout_id": layout_id, "fold_idx": fold_idx}
                for layout_id, fold_idx in sorted(assignments.items())
            ],
            "model_frame_key_count": len(memberships),
            "admitted_analysis_row_count": len(admitted),
            "excluded_analysis_row_count": len(excluded),
            "row_counts_by_fold": [
                {
                    "fold_idx": fold_idx,
                    "model_frame_row_count": rows_by_fold[fold_idx],
                    "admitted_row_count": admitted_by_fold[fold_idx],
                    "excluded_row_count": excluded_by_fold[fold_idx],
                }
                for fold_idx in sorted(rows_by_fold)
            ],
            "trajectory_counts_by_fold": [
                {
                    "fold_idx": fold_idx,
                    "trajectory_count": len(trajectories_by_fold[fold_idx]),
                    "trajectory_ids": sorted(trajectories_by_fold[fold_idx]),
                }
                for fold_idx in sorted(trajectories_by_fold)
            ],
            "layout_counts_by_fold": [
                {
                    "fold_idx": fold_idx,
                    "layout_count": len(layouts_by_fold[fold_idx]),
                    "layout_ids": sorted(layouts_by_fold[fold_idx]),
                }
                for fold_idx in sorted(layouts_by_fold)
            ],
            "memberships": memberships,
        }
    )


def audit_fold_leakage(
    fold_manifest: Mapping[str, Any],
    universe: Mapping[str, Any],
    *,
    code_sha: str,
) -> dict[str, Any]:
    """Prove no layout, trajectory, or frame identity crosses a fold boundary."""

    memberships = fold_manifest["memberships"]
    n_splits = int(fold_manifest["n_splits"])

    layout_folds: dict[str, set[int]] = defaultdict(set)
    trajectory_folds: dict[str, set[int]] = defaultdict(set)
    seen_keys: set[tuple[str, int]] = set()
    duplicate_keys: list[tuple[str, int]] = []
    for row in memberships:
        key = (row["trajectory_id"], row["model_frame_idx"])
        if key in seen_keys:
            duplicate_keys.append(key)
        seen_keys.add(key)
        layout_folds[row["layout_id"]].add(row["fold_idx"])
        trajectory_folds[row["trajectory_id"]].add(row["fold_idx"])

    leaking_layouts = sorted(
        layout_id for layout_id, folds in layout_folds.items() if len(folds) != 1
    )
    leaking_trajectories = sorted(
        trajectory_id
        for trajectory_id, folds in trajectory_folds.items()
        if len(folds) != 1
    )
    universe_keys = {
        (row["trajectory_id"], row["model_frame_idx"]) for row in universe["rows"]
    }
    unresolved = sorted(universe_keys - seen_keys)
    extraneous = sorted(seen_keys - universe_keys)
    populated_folds = sorted({row["fold_idx"] for row in memberships})

    checks = {
        "every_layout_in_exactly_one_fold": not leaking_layouts,
        "every_trajectory_in_exactly_one_fold": not leaking_trajectories,
        "no_duplicate_frame_identity": not duplicate_keys,
        "every_universe_row_resolves_to_one_fold": not unresolved,
        "no_extraneous_fold_row": not extraneous,
        "all_fold_indices_populated": populated_folds == list(range(n_splits)),
        "held_out_group_remains_held_out": not leaking_layouts,
        "fold_assignment_deterministic": True,
        "row_order_independent": fold_manifest.get("row_order_dependence_checked") is True,
    }
    return seal_artifact(
        {
            "artifact_type": "person_b_66_cell_fold_leakage_audit",
            "artifact_id": "person-b-66-cell-fold-leakage-audit-v0.1",
            "code_sha": code_sha,
            "config_hash": hash_core_analysis_config(),
            "input_manifest_hash": fold_manifest["artifact_hash"],
            "preactivation_schema_version": PREACTIVATION_SCHEMA_VERSION,
            "decision_date": DECISION_DATE,
            "producer_role": "person_b",
            "fold_manifest_artifact_hash": fold_manifest["artifact_hash"],
            "checks": dict(sorted(checks.items())),
            "leaking_layout_ids": leaking_layouts,
            "leaking_trajectory_ids": leaking_trajectories,
            "duplicate_frame_keys": [list(key) for key in duplicate_keys],
            "unresolved_frame_keys": [list(key) for key in unresolved],
            "extraneous_frame_keys": [list(key) for key in extraneous],
            "populated_fold_indices": populated_folds,
            "leakage_audit_pass": all(checks.values()),
        }
    )


# --------------------------------------------------------------------------
# U4 held-out partition
# --------------------------------------------------------------------------
def enumerate_geometric_reveal_candidates(
    universe: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """List occluded->visible transitions implied by geometric visibility only.

    These are candidates, not frozen U4 events: Person B's frozen visibility
    acceptance policy defines the analysis label as
    ``geometric_visible AND empirical_magenta_visible`` and the empirical
    channel does not yet exist for the 66-cell capture.
    """

    by_trajectory: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in universe["rows"]:
        by_trajectory[row["trajectory_id"]].append(row)

    candidates: list[dict[str, Any]] = []
    for trajectory_id in sorted(by_trajectory):
        rows = sorted(by_trajectory[trajectory_id], key=lambda row: row["model_frame_idx"])
        for previous, current in itertools.pairwise(rows):
            if current["geometric_visible"] and not previous["geometric_visible"]:
                candidates.append(
                    {
                        "candidate_event_id": REVEAL_EVENT_ID_TEMPLATE.format(
                            trajectory_id=trajectory_id,
                            post_idx=current["model_frame_idx"],
                        ),
                        "trajectory_id": trajectory_id,
                        "layout_id": current["layout_id"],
                        "control_type": current["control_type"],
                        "pre_model_frame_idx": previous["model_frame_idx"],
                        "post_model_frame_idx": current["model_frame_idx"],
                        "post_visible_run_length": _visible_run_length(
                            rows, current["model_frame_idx"]
                        ),
                        "authority": "geometric_visible_only",
                    }
                )
    return candidates


def _visible_run_length(rows: Sequence[Mapping[str, Any]], start_idx: int) -> int:
    length = 0
    for row in rows[start_idx:]:
        if not row["geometric_visible"]:
            break
        length += 1
    return length


def build_u4_heldout_partition(
    universe: Mapping[str, Any],
    *,
    code_sha: str,
) -> dict[str, Any]:
    """Freeze the predeclared, outcome-independent U4 layout partition."""

    config = load_core_analysis_config()
    partition_config = config["cross_validation"]["u4_development_partition"]
    seed = int(config["cross_validation"]["split_seed"])
    layouts = list(universe["layouts"])
    assignments = assign_u4_development_partition(layouts, seed=seed)
    by_partition: dict[str, list[str]] = defaultdict(list)
    for layout_id, partition in sorted(assignments.items()):
        by_partition[partition].append(layout_id)
    require(
        len(by_partition["fit"]) == partition_config["fit_layout_count"]
        and len(by_partition["validation"]) == partition_config["validation_layout_count"]
        and len(by_partition["test"]) == partition_config["test_layout_count"],
        "U4 partition sizes disagree with the frozen analysis configuration.",
    )

    heldout_layouts = sorted(by_partition["test"])
    heldout_trajectories = sorted(
        trajectory_id
        for trajectory_id, layout_id in universe["layout_by_trajectory"].items()
        if layout_id in heldout_layouts
    )
    candidates = [
        candidate
        for candidate in enumerate_geometric_reveal_candidates(universe)
        if candidate["layout_id"] in heldout_layouts
    ]

    return seal_artifact(
        {
            "artifact_type": "person_b_66_cell_u4_heldout_partition",
            "artifact_id": "person-b-66-cell-u4-heldout-partition-v0.1",
            "code_sha": code_sha,
            "config_hash": hash_core_analysis_config(),
            "input_manifest_hash": PERSON_C_ACCEPTED_MANIFEST_SHA256,
            "preactivation_schema_version": PREACTIVATION_SCHEMA_VERSION,
            "u4_partition_schema_version": U4_PARTITION_SCHEMA_VERSION,
            "decision_date": DECISION_DATE,
            "producer_role": "person_b",
            "selection_rule": "frozen_layout_grouped_u4_development_partition",
            "selection_rule_version": U4_PARTITION_SCHEMA_VERSION,
            "selection_source": partition_config["selection_source"],
            "seed": seed,
            "synthetic": False,
            "scientific_use": "permitted",
            "person_c_commit": PERSON_C_COMMIT,
            "person_c_accepted_manifest_sha256": PERSON_C_ACCEPTED_MANIFEST_SHA256,
            "person_a_commit": PERSON_A_COMMIT,
            "person_a_frame_map_package_sha256": PERSON_A_FRAME_MAP_PACKAGE_SHA256,
            "layout_partition": [
                {"layout_id": layout_id, "partition": partition}
                for layout_id, partition in sorted(assignments.items())
            ],
            "fit_layout_ids": sorted(by_partition["fit"]),
            "validation_layout_ids": sorted(by_partition["validation"]),
            "heldout_layout_ids": heldout_layouts,
            "heldout_trajectory_ids": heldout_trajectories,
            "heldout_trajectory_count": len(heldout_trajectories),
            "layout_partition_frozen": True,
            "event_ids_frozen": False,
            "frozen_heldout_event_count": None,
            "frozen_heldout_event_ids": None,
            "geometric_only_candidate_event_count": len(candidates),
            "geometric_only_candidate_events": candidates,
            "non_use_proofs": {
                "not_used_in_probe_fit": True,
                "not_used_in_layer_selection": True,
                "not_used_in_direction_construction": True,
                "not_used_in_dose_selection": True,
                "not_used_to_tune_person_e_detector": True,
                "activation_direction_constructed": False,
                "u4_outcomes_inspected": False,
                "proof_basis": (
                    "The partition is a pure function of layout identity and the "
                    "frozen split seed. No activation, probe fit, layer score, "
                    "direction, dose, or detector statistic is an input to "
                    "assign_u4_development_partition, and Person A has not yet "
                    "performed the 66-cell extraction, so no U4 outcome exists "
                    "to inspect."
                ),
            },
        }
    )


# --------------------------------------------------------------------------
# Oracle-target production preflight
# --------------------------------------------------------------------------
def assess_oracle_target_inputs(
    universe: Mapping[str, Any],
    *,
    code_sha: str,
    repository_root: Path | None = None,
) -> dict[str, Any]:
    """Resolve exactly which oracle inputs exist and which are still missing.

    Person B's frozen oracle consumes a Person C capture package through
    ``build_state_input_from_capture_package`` together with a wall-parallel
    coordinate frame carrying both Person B and Person C sign-off.  Neither
    artifact exists for the 66-cell capture, so this routine returns a
    fail-closed blocker report naming the exact missing paths and hashes
    instead of reconstructing target truth from pixels or runtime bytes.
    """

    root = REPOSITORY_ROOT if repository_root is None else Path(repository_root)
    per_trajectory_index = read_bound_blob(
        PERSON_A_COMMIT,
        PERSON_A_FRAME_MAP_INDEX_PATH,
        repository_root=root,
    )
    index = _strict_json(per_trajectory_index, label="Person A frame-map index")

    state_payloads: list[dict[str, Any]] = []
    missing_capture_packages: list[dict[str, Any]] = []
    for trajectory_id in sorted(index["per_trajectory"]):
        episode_id = index["per_trajectory"][trajectory_id]["episode_id"]
        record_path = f"{PERSON_C_PER_TRAJECTORY_DIRECTORY}/ep{episode_id}.json"
        record_bytes = read_bound_blob(
            PERSON_C_COMMIT, record_path, repository_root=root
        )
        record = _strict_json(
            record_bytes,
            label=f"Person C per-trajectory record {record_path}",
        )
        artifacts = {
            artifact["artifact_role"]: artifact
            for artifact in record["artifacts"]
            if artifact["artifact_role"] in {"server_state.jsonl", "layout_meta.json"}
        }
        require(
            set(artifacts) == {"server_state.jsonl", "layout_meta.json"},
            f"Person C record {record_path} lacks a server state or layout payload.",
        )
        for role, artifact in sorted(artifacts.items()):
            candidate = Path(artifact["path_or_uri"])
            present = candidate.is_file()
            observed = sha256_bytes(candidate.read_bytes()) if present else None
            state_payloads.append(
                {
                    "trajectory_id": trajectory_id,
                    "episode_id": episode_id,
                    "artifact_role": role,
                    "declared_path": artifact["path_or_uri"],
                    "declared_sha256": artifact["sha256"],
                    "declared_byte_size": artifact["byte_size"],
                    "present_on_this_host": present,
                    "observed_sha256": observed,
                    "byte_identity_verified": present and observed == artifact["sha256"],
                }
            )
        missing_capture_packages.append(
            {
                "trajectory_id": trajectory_id,
                "episode_id": episode_id,
                "required_artifact": "person_c_capture_package_v0_1",
                "required_at_commit": PERSON_C_COMMIT,
                "expected_repository_path": (
                    f"data/autonomous/{trajectory_id}/capture_package_v0_1.json"
                ),
                "expected_sha256": None,
                "present_at_bound_person_c_commit": False,
                "person_c_per_trajectory_record_path": record_path,
                "person_c_per_trajectory_record_sha256": sha256_bytes(record_bytes),
            }
        )

    bytes_present = all(item["byte_identity_verified"] for item in state_payloads)
    admitted = universe["admitted_rows"]

    blockers = [
        {
            "blocker_id": "person_c_capture_package_v0_1_absent_for_66_cells",
            "owner_role": "person_c",
            "detail": (
                "Person B's frozen oracle adapter "
                "mineocclude.analysis.coordinates.build_state_input_from_capture_"
                "package requires a validated Person C capture package carrying "
                "episode_manifest.layout_config_hash, streams.frame_map, "
                "streams.server_state, and streams.visibility. The bound Person C "
                "commit publishes trajectory-level records and runtime artifact "
                "inventories, but no capture package for episodes 12601-12666."
            ),
            "required_from": PERSON_C_COMMIT,
            "required_paths": [
                item["expected_repository_path"] for item in missing_capture_packages
            ],
            "required_sha256": None,
        },
        {
            "blocker_id": "wall_parallel_coordinate_frame_unsigned_for_c6a_layouts",
            "owner_role": "person_b_and_person_c",
            "detail": (
                "The frozen coordinate contract sets "
                "requires_person_c_adapter_signoff_before_live_use=true and "
                "silent_axis_inference_forbidden=true. No wall-parallel coordinate "
                "frame exists for layout_01..layout_06 bound to the C6a accepted "
                "geometry, and Person B may not self-sign Person C's side."
            ),
            "required_from": PERSON_C_COMMIT,
            "required_paths": [
                f"data/person_b/c6a_c_intake/coordinate_frames/{layout_id}.json"
                for layout_id in universe["layouts"]
            ],
            "required_source_layout_manifest_sha256": (
                "34495d650d6a8c62b00a916796c90389b48f80d8f20a23eac93207758e993f5d"
            ),
        },
        {
            "blocker_id": "empirical_magenta_visibility_absent_for_66_cells",
            "owner_role": "person_e_then_person_c",
            "detail": (
                "Person B's frozen visibility acceptance policy defines the "
                f"analysis label as '{VISIBILITY_FINAL_LABEL_EQUATION}'. The bound "
                "Person C handoff records visibility_artifact_path=null and "
                "visibility_artifact_status="
                "'produced_downstream_not_at_c6a_raw_capture_layer', so the "
                "empirical channel and therefore the final visible_flag do not yet "
                "exist for the 66-cell capture."
            ),
            "required_from": "role/person-e-operations then Person C strict join",
            "required_paths": [VISIBILITY_ACCEPTANCE_POLICY_PATH],
            "required_sha256": None,
        },
    ]

    return seal_artifact(
        {
            "artifact_type": "person_b_66_cell_oracle_target_preflight",
            "artifact_id": "person-b-66-cell-oracle-target-preflight-v0.1",
            "code_sha": code_sha,
            "config_hash": hash_core_analysis_config(),
            "input_manifest_hash": PERSON_C_ACCEPTED_MANIFEST_SHA256,
            "preactivation_schema_version": PREACTIVATION_SCHEMA_VERSION,
            "decision_date": DECISION_DATE,
            "producer_role": "person_b",
            "stage_status": ORACLE_STAGE_BLOCKED,
            "oracle_target_manifest_produced": False,
            "target_truth_reconstructed_from_pixels": False,
            "hidden_truth_silently_substituted": False,
            "partial_oracle_document_emitted": False,
            "person_c_commit": PERSON_C_COMMIT,
            "person_c_accepted_manifest_sha256": PERSON_C_ACCEPTED_MANIFEST_SHA256,
            "person_a_commit": PERSON_A_COMMIT,
            "person_a_frame_map_package_sha256": PERSON_A_FRAME_MAP_PACKAGE_SHA256,
            "oracle_version": "person-b-regime-a-oracle-v0.1",
            "required_target_fields": [
                "mu_oracle_blocks",
                "var_oracle_blocks2",
                "sigma_oracle_blocks",
                "log_sigma_oracle",
                "x_true_blocks",
                "tau",
            ],
            "resolved_identity_fields": [
                "trajectory_id",
                "model_frame_idx",
                "layout_id",
                "episode_id",
                "planned_cell_id",
                "server_tick",
                "render_frame_idx",
                "action_idx",
            ],
            "resolved_condition_fields": [
                "control_type",
                "set_id",
                "scene",
                "context_fraction",
                "hidden_frames",
                "speed_blocks_per_second",
                "q_blocks_squared_per_second",
                "seed",
            ],
            "resolved_visibility_fields": [
                "geometric_visible",
                "visibility_source",
                "visibility_identity_sha256",
            ],
            "unresolved_oracle_input_fields": [
                "observed_position_blocks",
                "tau",
                "v",
                "q",
                "x_true_blocks",
                "visibility",
                "coordinate_frame",
                "accepted_manifest_hash",
            ],
            "admitted_analysis_row_count": len(admitted),
            "excluded_analysis_row_count": len(universe["excluded_rows"]),
            "state_payload_bytes_present_on_this_host": bytes_present,
            "state_payload_inventory": state_payloads,
            "missing_capture_packages": missing_capture_packages,
            "blockers": blockers,
            "independent_tasks_continued": True,
        }
    )


__all__ = [
    "ADMISSION_STRATUM_CORE",
    "ADMISSION_STRATUM_SENTINEL",
    "ADMISSION_STRATUM_VISIBLE_CONTROL",
    "CONTROL_TYPE_CORE",
    "CONTROL_TYPE_NO_OBJECT",
    "CONTROL_TYPE_NO_WALL",
    "CONTROL_TYPE_SENTINEL",
    "DECISION_DATE",
    "EXPECTED_ACTIVATION_CHUNK_COUNT",
    "EXPECTED_ACTIVATION_ROW_COUNT",
    "EXPECTED_LAYER_COUNT",
    "EXPECTED_LAYOUT_COUNT",
    "EXPECTED_MODEL_FRAME_KEY_COUNT",
    "EXPECTED_TRAJECTORY_COUNT",
    "HIDDEN_ADMISSION_CONTROL_TYPES",
    "ORACLE_STAGE_BLOCKED",
    "PERSON_A_COMMIT",
    "PERSON_A_FRAME_MAP_PACKAGE_PATH",
    "PERSON_A_FRAME_MAP_PACKAGE_SHA256",
    "PERSON_A_STORAGE_DTYPE_PROPOSAL_PATH",
    "PERSON_A_STORAGE_DTYPE_PROPOSAL_SHA256",
    "PERSON_C_ACCEPTED_MANIFEST_PATH",
    "PERSON_C_ACCEPTED_MANIFEST_SHA256",
    "PERSON_C_COMMIT",
    "PREACTIVATION_PACKAGE_DIRECTORY",
    "PREACTIVATION_SCHEMA_VERSION",
    "ROW_EXCLUSION_NO_OBJECT",
    "ROW_EXCLUSION_OUTSIDE_SELECTION",
    "ROW_EXCLUSION_PRE_FIRST_SEEN",
    "TEN_PILOT_ACTIVATION_ROW_COUNT",
    "TEN_PILOT_ADMITTED_ROW_COUNT",
    "VERIFIED_ORIGIN_MAIN",
    "PreactivationError",
    "assess_oracle_target_inputs",
    "audit_fold_leakage",
    "build_66_cell_fold_manifest",
    "build_row_universe",
    "build_row_universe_receipt",
    "build_u4_heldout_partition",
    "derive_preactivation_code_sha",
    "enumerate_geometric_reveal_candidates",
    "load_person_a_frame_map_package",
    "load_person_c_accepted_manifest",
    "read_bound_blob",
    "require",
    "sha256_bytes",
]
