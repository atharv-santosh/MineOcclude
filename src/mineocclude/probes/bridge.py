"""Fail-closed bridge from A activation handoffs to B OOF probe inputs."""

from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path
from typing import Any

from mineocclude.analysis.config import (
    ANALYSIS_CONFIG_VERSION,
    DEFAULT_CONFIG_PATH,
    hash_core_analysis_config,
    load_core_analysis_config,
)
from mineocclude.analysis.manifests import (
    AnalysisArtifactError,
    is_hex_digest,
    seal_artifact,
    sha256_value,
)
from mineocclude.analysis.outputs import (
    build_prediction_artifact,
    build_result_artifact,
)
from mineocclude.contracts.activation import validate_activation_handoff
from mineocclude.contracts.identity import FRAME_KEY, SCHEMA_VERSION
from mineocclude.metrics.u1_mean import U1MetricError, regression_metrics

from .join import (
    ActivationTargetJoinError,
    JoinedActivationTarget,
    join_activation_target_document,
)
from .ridge import ProbeFitError, RidgeOOFResult, fit_ridge_oof
from .splits import (
    FOLD_SCHEMA_VERSION,
    GroupedSplitError,
    build_fold_manifest,
    validate_fold_manifest,
)


FRAME_TABLE_VERSION = "person-b-joined-frame-v0.1"
MATRIX_VERSION = "person-b-probe-matrix-v0.1"
SUPPORTED_TARGETS = frozenset({"mu_oracle_blocks"})
FLOAT32_MAX = 3.4028234663852886e38


class ProbeBridgeRejectionCode(str, Enum):
    INVALID_JOIN = "invalid_join"
    INVALID_FRAME_TABLE = "invalid_frame_table"
    DUPLICATE_FRAME = "duplicate_frame"
    INCONSISTENT_FRAME_METADATA = "inconsistent_frame_metadata"
    STALE_FRAME_TABLE = "stale_frame_table"
    INVALID_FOLD_MANIFEST = "invalid_fold_manifest"
    STALE_FOLD_MANIFEST = "stale_fold_manifest"
    DUPLICATE_FOLD_ASSIGNMENT = "duplicate_fold_assignment"
    MISSING_FOLD_ASSIGNMENT = "missing_fold_assignment"
    CONFLICTING_FOLD_ASSIGNMENT = "conflicting_fold_assignment"
    INVALID_ACTIVATION_HANDOFF = "invalid_activation_handoff"
    MISSING_CHUNK = "missing_chunk"
    UNDECLARED_CHUNK = "undeclared_chunk"
    CHUNK_HASH_MISMATCH = "chunk_hash_mismatch"
    INVALID_CHUNK = "invalid_chunk"
    MISSING_CHUNK_ROW = "missing_chunk_row"
    DUPLICATE_CHUNK_ROW = "duplicate_chunk_row"
    DUPLICATE_CHUNK_ROW_CLAIM = "duplicate_chunk_row_claim"
    CHUNK_ROW_OUT_OF_BOUNDS = "chunk_row_out_of_bounds"
    VECTOR_METADATA_MISMATCH = "vector_metadata_mismatch"
    INVALID_VECTOR = "invalid_vector"
    INCOMPLETE_LAYER_SITE_GRID = "incomplete_layer_site_grid"
    MISSING_TARGET = "missing_target"
    INVALID_LIFECYCLE = "invalid_lifecycle"
    CONFLICTING_PROPAGATED_FOLD = "conflicting_propagated_fold"
    PROBE_FIT_FAILED = "probe_fit_failed"
    ARTIFACT_BUILD_FAILED = "artifact_build_failed"
    CONFIG_HASH_MISMATCH = "config_hash_mismatch"
    PROBE_CODE_MISMATCH = "probe_code_mismatch"
    INTERMEDIATE_PROVENANCE_MISMATCH = "intermediate_provenance_mismatch"
    MATRIX_HASH_MISMATCH = "matrix_hash_mismatch"
    FROZEN_PROBE_CONFIG_MISMATCH = "frozen_probe_config_mismatch"
    INVALID_SYNTHETIC_MARKING = "invalid_synthetic_marking"


class ProbeBridgeError(ValueError):
    """One stable fail-closed rejection from the synthetic probe bridge."""

    def __init__(self, code: ProbeBridgeRejectionCode, message: str) -> None:
        self.code = code
        super().__init__(f"{code.value}: {message}")


@dataclass(frozen=True)
class ProbeReadyMatrix:
    """One deterministic layer/site matrix with frozen row provenance."""

    schema_version: str
    layer_idx: int
    hook_site: str
    target_name: str
    features: tuple[tuple[float, ...], ...]
    targets: tuple[float, ...]
    outer_folds: tuple[int, ...]
    layout_ids: tuple[str, ...]
    metadata_rows: tuple[Mapping[str, Any], ...]
    accepted_manifest_hash: str
    frame_table_hash: str
    fold_manifest_hash: str
    fold_version: str
    analysis_config_hash: str
    analysis_config_version: str
    target_code_sha: str
    probe_code_sha: str
    activation_handoff_hash: str
    target_document_hash: str
    activation_chunk_hashes: tuple[tuple[str, str], ...]
    matrix_hash: str
    synthetic: bool
    scientific_use: str


@dataclass(frozen=True)
class RidgeProbeExecution:
    """OOF ridge output plus sealed prediction and U1 result artifacts."""

    oof_result: RidgeOOFResult
    prediction_artifact: Mapping[str, Any]
    u1_result_artifact: Mapping[str, Any]


def _fail(code: ProbeBridgeRejectionCode, message: str) -> None:
    raise ProbeBridgeError(code, message)


def derive_probe_code_sha() -> str:
    """Hash the literal B-owned bridge, split, and ridge implementation bytes."""

    digest = hashlib.sha1()
    directory = Path(__file__).resolve().parent
    for filename in ("bridge.py", "ridge.py", "splits.py"):
        path = directory / filename
        try:
            payload = path.read_bytes()
        except OSError as error:
            _fail(
                ProbeBridgeRejectionCode.PROBE_CODE_MISMATCH,
                f"Could not read probe code component {filename!r}: {error}",
            )
        digest.update(filename.encode("utf-8"))
        digest.update(b"\0")
        digest.update(payload)
        digest.update(b"\0")
    return digest.hexdigest()


def _frame_key(row: Mapping[str, Any]) -> tuple[str, int]:
    try:
        trajectory_id = row["trajectory_id"]
        model_frame_idx = row["model_frame_idx"]
    except (KeyError, TypeError):
        _fail(
            ProbeBridgeRejectionCode.INVALID_FRAME_TABLE,
            "A frame row is missing the universal frame key.",
        )
    if (
        not isinstance(trajectory_id, str)
        or not trajectory_id
        or not isinstance(model_frame_idx, int)
        or isinstance(model_frame_idx, bool)
        or model_frame_idx < 0
    ):
        _fail(
            ProbeBridgeRejectionCode.INVALID_FRAME_TABLE,
            "A frame row has an invalid universal frame key.",
        )
    return trajectory_id, model_frame_idx


def _normalized_handoff_hash(document: Mapping[str, Any]) -> str:
    normalized = dict(document)
    rows = document.get("index_rows")
    chunks = document.get("chunks")
    if not isinstance(rows, list) or not isinstance(chunks, list):
        _fail(
            ProbeBridgeRejectionCode.INVALID_ACTIVATION_HANDOFF,
            "Activation handoff rows or chunks are malformed.",
        )
    normalized["index_rows"] = sorted(
        (dict(row) for row in rows),
        key=lambda row: (
            row.get("trajectory_id"),
            row.get("model_frame_idx"),
            row.get("layer_idx"),
            row.get("hook_site"),
        ),
    )
    normalized["chunks"] = sorted(
        (dict(chunk) for chunk in chunks),
        key=lambda chunk: chunk.get("chunk_id", ""),
    )
    return sha256_value(normalized)


def _normalized_target_hash(document: Mapping[str, Any]) -> str:
    normalized = dict(document)
    rows = document.get("rows")
    if not isinstance(rows, list):
        _fail(
            ProbeBridgeRejectionCode.INVALID_JOIN,
            "Target document rows are malformed.",
        )
    normalized["rows"] = sorted(
        (dict(row) for row in rows),
        key=lambda row: (
            row.get("trajectory_id"),
            row.get("model_frame_idx"),
        ),
    )
    return sha256_value(normalized)


def _join(
    activation_package: Mapping[str, Any],
    target_document: Mapping[str, Any],
) -> tuple[JoinedActivationTarget, ...]:
    try:
        joined = join_activation_target_document(
            activation_package,
            target_document,
        )
    except (ActivationTargetJoinError, KeyError, TypeError, ValueError) as error:
        _fail(
            ProbeBridgeRejectionCode.INVALID_JOIN,
            f"A-to-B activation/target join failed: {error}",
        )
    if not joined:
        _fail(
            ProbeBridgeRejectionCode.INVALID_JOIN,
            "A-to-B activation/target join produced no rows.",
        )
    return tuple(joined)


def build_joined_frame_table(
    activation_package: Mapping[str, Any],
    target_document: Mapping[str, Any],
    *,
    analysis_config_hash: str | None = None,
) -> dict[str, Any]:
    """Collapse validated layer/site joins into one canonical row per frame."""

    if not isinstance(activation_package, Mapping) or not isinstance(
        target_document,
        Mapping,
    ):
        _fail(
            ProbeBridgeRejectionCode.INVALID_JOIN,
            "Activation and target documents must be mappings.",
        )
    try:
        frozen_config = load_core_analysis_config(DEFAULT_CONFIG_PATH)
        literal_config_hash = hash_core_analysis_config(DEFAULT_CONFIG_PATH)
    except ValueError as error:
        _fail(
            ProbeBridgeRejectionCode.CONFIG_HASH_MISMATCH,
            f"Frozen analysis config is unavailable or invalid: {error}",
        )
    if (
        analysis_config_hash is not None
        and analysis_config_hash != literal_config_hash
    ):
        _fail(
            ProbeBridgeRejectionCode.CONFIG_HASH_MISMATCH,
            "Caller-supplied analysis config hash does not match literal core.yaml.",
        )
    fixture_metadata = target_document.get("fixture_metadata")
    if not isinstance(fixture_metadata, Mapping) or (
        fixture_metadata.get("synthetic") is not True
        or fixture_metadata.get("scientific_use") != "forbidden"
    ):
        _fail(
            ProbeBridgeRejectionCode.INVALID_JOIN,
            "Repair Chunk 2 accepts only explicitly non-scientific target fixtures.",
        )
    joined = _join(activation_package, target_document)
    rows_by_frame: dict[tuple[str, int], dict[str, Any]] = {}

    for item in joined:
        activation = item.activation_index_row
        target = item.target_row
        key = _frame_key(target)
        if target.get("status") != "accepted" or activation.get("status") != "accepted":
            _fail(
                ProbeBridgeRejectionCode.INVALID_LIFECYCLE,
                f"Frame {key!r} is not accepted on both sides of the join.",
            )

        frame_row = dict(target)
        frame_row.update(
            {
                "activation_handoff_id": activation_package.get("handoff_id"),
                "activation_run_id": activation.get("run_id"),
                "activation_code_sha": activation.get("code_sha"),
                "activation_config_hash": activation.get("config_hash"),
                "activation_checkpoint_hash": activation.get("checkpoint_hash"),
                "activation_preprocess_hash": activation.get("preprocess_hash"),
                "target_run_id": target.get("run_id"),
                "target_code_sha": target.get("code_sha"),
                "target_config_hash": target.get("config_hash"),
            }
        )
        existing = rows_by_frame.get(key)
        if existing is not None and existing != frame_row:
            _fail(
                ProbeBridgeRejectionCode.INCONSISTENT_FRAME_METADATA,
                f"Layer/site rows disagree on frame metadata for {key!r}.",
            )
        rows_by_frame[key] = frame_row

    rows = [rows_by_frame[key] for key in sorted(rows_by_frame)]
    manifest_hashes = {row.get("accepted_manifest_hash") for row in rows}
    target_config_hashes = {row.get("target_config_hash") for row in rows}
    target_code_shas = {row.get("target_code_sha") for row in rows}
    target_run_ids = {row.get("target_run_id") for row in rows}
    if len(manifest_hashes) != 1 or not is_hex_digest(next(iter(manifest_hashes)), 64):
        _fail(
            ProbeBridgeRejectionCode.INCONSISTENT_FRAME_METADATA,
            "Frame rows do not share one accepted-manifest hash.",
        )
    if len(target_config_hashes) != 1 or not is_hex_digest(
        next(iter(target_config_hashes)),
        64,
    ):
        _fail(
            ProbeBridgeRejectionCode.INCONSISTENT_FRAME_METADATA,
            "Frame rows do not share one target config hash.",
        )
    if len(target_code_shas) != 1 or not is_hex_digest(
        next(iter(target_code_shas)),
        40,
    ):
        _fail(
            ProbeBridgeRejectionCode.INCONSISTENT_FRAME_METADATA,
            "Frame rows do not share one target code SHA.",
        )
    if len(target_run_ids) != 1:
        _fail(
            ProbeBridgeRejectionCode.INCONSISTENT_FRAME_METADATA,
            "Frame rows do not share one target run identity.",
        )

    body = {
        "schema_version": SCHEMA_VERSION,
        "frame_table_version": FRAME_TABLE_VERSION,
        "join_key": list(FRAME_KEY),
        "accepted_manifest_hash": next(iter(manifest_hashes)),
        "activation_handoff_id": activation_package.get("handoff_id"),
        "activation_handoff_hash": _normalized_handoff_hash(activation_package),
        "target_document_hash": _normalized_target_hash(target_document),
        "target_config_hash": next(iter(target_config_hashes)),
        "analysis_config_hash": literal_config_hash,
        "analysis_config_version": frozen_config["analysis_config_version"],
        "target_code_sha": next(iter(target_code_shas)),
        "probe_code_sha": derive_probe_code_sha(),
        "target_run_id": next(iter(target_run_ids)),
        "synthetic": True,
        "scientific_use": "forbidden",
        "rows": rows,
    }
    return {**body, "frame_table_hash": sha256_value(body)}


def validate_joined_frame_table(document: Mapping[str, Any]) -> None:
    """Reject altered, duplicate, non-v1, or internally inconsistent tables."""

    if not isinstance(document, Mapping):
        _fail(
            ProbeBridgeRejectionCode.INVALID_FRAME_TABLE,
            "Joined frame table must be a mapping.",
        )
    if (
        document.get("schema_version") != SCHEMA_VERSION
        or document.get("frame_table_version") != FRAME_TABLE_VERSION
        or document.get("join_key") != list(FRAME_KEY)
        or document.get("synthetic") is not True
        or document.get("scientific_use") != "forbidden"
    ):
        _fail(
            ProbeBridgeRejectionCode.INVALID_FRAME_TABLE,
            "Joined frame table envelope is invalid.",
        )
    for field, length in (
        ("accepted_manifest_hash", 64),
        ("activation_handoff_hash", 64),
        ("target_document_hash", 64),
        ("target_config_hash", 64),
        ("analysis_config_hash", 64),
        ("target_code_sha", 40),
        ("probe_code_sha", 40),
        ("frame_table_hash", 64),
    ):
        if not is_hex_digest(document.get(field), length):
            _fail(
                ProbeBridgeRejectionCode.INVALID_FRAME_TABLE,
                f"Joined frame table {field} is invalid.",
            )
    if document.get("analysis_config_version") != ANALYSIS_CONFIG_VERSION:
        _fail(
            ProbeBridgeRejectionCode.CONFIG_HASH_MISMATCH,
            "Joined frame table analysis config version is not frozen v0.2.",
        )
    if document.get("analysis_config_hash") != hash_core_analysis_config(
        DEFAULT_CONFIG_PATH
    ):
        _fail(
            ProbeBridgeRejectionCode.CONFIG_HASH_MISMATCH,
            "Joined frame table analysis config hash is not literal core.yaml.",
        )
    if document.get("probe_code_sha") != derive_probe_code_sha():
        _fail(
            ProbeBridgeRejectionCode.PROBE_CODE_MISMATCH,
            "Joined frame table probe code SHA is stale.",
        )
    rows = document.get("rows")
    if not isinstance(rows, list) or not rows:
        _fail(
            ProbeBridgeRejectionCode.INVALID_FRAME_TABLE,
            "Joined frame table requires non-empty rows.",
        )
    seen: set[tuple[str, int]] = set()
    layout_by_trajectory: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            _fail(
                ProbeBridgeRejectionCode.INVALID_FRAME_TABLE,
                "Joined frame rows must be mappings.",
            )
        key = _frame_key(row)
        if key in seen:
            _fail(
                ProbeBridgeRejectionCode.DUPLICATE_FRAME,
                f"Duplicate joined frame {key!r}.",
            )
        seen.add(key)
        if row.get("status") != "accepted":
            _fail(
                ProbeBridgeRejectionCode.INVALID_LIFECYCLE,
                f"Joined frame {key!r} is not accepted.",
            )
        if row.get("accepted_manifest_hash") != document.get(
            "accepted_manifest_hash"
        ):
            _fail(
                ProbeBridgeRejectionCode.INCONSISTENT_FRAME_METADATA,
                f"Joined frame {key!r} has a stale manifest hash.",
            )
        for field in (
            "episode_id",
            "layout_id",
            "server_tick",
            "tau",
            "regime",
            "visibility",
            "v",
            "q",
            "duration",
            "mu_oracle_blocks",
            "activation_run_id",
            "target_run_id",
        ):
            if field not in row:
                _fail(
                    ProbeBridgeRejectionCode.INVALID_FRAME_TABLE,
                    f"Joined frame {key!r} is missing {field}.",
                )
        layout = row["layout_id"]
        if not isinstance(layout, str) or not layout:
            _fail(
                ProbeBridgeRejectionCode.INVALID_FRAME_TABLE,
                f"Joined frame {key!r} has an invalid layout.",
            )
        prior_layout = layout_by_trajectory.setdefault(key[0], layout)
        if prior_layout != layout:
            _fail(
                ProbeBridgeRejectionCode.INCONSISTENT_FRAME_METADATA,
                f"Trajectory {key[0]!r} crosses layouts.",
            )
    unhashed = dict(document)
    supplied_hash = unhashed.pop("frame_table_hash", None)
    try:
        actual_hash = sha256_value(unhashed)
    except AnalysisArtifactError as error:
        _fail(
            ProbeBridgeRejectionCode.INVALID_FRAME_TABLE,
            f"Joined frame table is not canonical JSON: {error}",
        )
    if supplied_hash != actual_hash:
        _fail(
            ProbeBridgeRejectionCode.INVALID_FRAME_TABLE,
            "Joined frame table hash does not match its contents.",
        )


def build_frame_fold_manifest(
    frame_table: Mapping[str, Any],
    *,
    artifact_id: str,
    n_splits: int = 5,
    seed: int = 20260719,
) -> dict[str, Any]:
    """Build the existing tamper-evident fold artifact from frame rows."""

    validate_joined_frame_table(frame_table)
    try:
        fold_manifest = build_fold_manifest(
            frame_table["rows"],
            artifact_id=artifact_id,
            code_sha=frame_table["probe_code_sha"],
            config_hash=frame_table["analysis_config_hash"],
            input_manifest_hash=frame_table["frame_table_hash"],
            n_splits=n_splits,
            seed=seed,
        )
        payload = dict(fold_manifest)
        payload.pop("artifact_hash")
        payload.update(
            {
                "synthetic": True,
                "scientific_use": "forbidden",
            }
        )
        return seal_artifact(payload)
    except (GroupedSplitError, AnalysisArtifactError, KeyError, TypeError) as error:
        _fail(
            ProbeBridgeRejectionCode.INVALID_FOLD_MANIFEST,
            f"Frame-level fold construction failed: {error}",
        )


def _fold_memberships(
    fold_manifest: Mapping[str, Any],
) -> dict[tuple[str, int], Mapping[str, Any]]:
    memberships = fold_manifest.get("memberships")
    if not isinstance(memberships, list) or not memberships:
        _fail(
            ProbeBridgeRejectionCode.MISSING_FOLD_ASSIGNMENT,
            "Fold manifest has no frame memberships.",
        )
    by_key: dict[tuple[str, int], Mapping[str, Any]] = {}
    layout_folds: dict[str, int] = {}
    for membership in memberships:
        if not isinstance(membership, Mapping):
            _fail(
                ProbeBridgeRejectionCode.INVALID_FOLD_MANIFEST,
                "Fold memberships must be mappings.",
            )
        key = _frame_key(membership)
        if key in by_key:
            _fail(
                ProbeBridgeRejectionCode.DUPLICATE_FOLD_ASSIGNMENT,
                f"Frame {key!r} has duplicate fold memberships.",
            )
        fold = membership.get("fold_idx")
        layout = membership.get("layout_id")
        if (
            not isinstance(fold, int)
            or isinstance(fold, bool)
            or fold < 0
            or not isinstance(layout, str)
            or not layout
        ):
            _fail(
                ProbeBridgeRejectionCode.INVALID_FOLD_MANIFEST,
                f"Frame {key!r} has invalid fold metadata.",
            )
        prior = layout_folds.setdefault(layout, fold)
        if prior != fold:
            _fail(
                ProbeBridgeRejectionCode.CONFLICTING_FOLD_ASSIGNMENT,
                f"Layout {layout!r} appears in multiple folds.",
            )
        by_key[key] = membership
    return by_key


def propagate_frame_folds(
    activation_package: Mapping[str, Any],
    target_document: Mapping[str, Any],
    frame_table: Mapping[str, Any],
    fold_manifest: Mapping[str, Any],
) -> tuple[dict[str, Any], ...]:
    """Propagate each validated frame fold to every layer/site activation."""

    validate_joined_frame_table(frame_table)
    expected_table = build_joined_frame_table(
        activation_package,
        target_document,
    )
    if expected_table != dict(frame_table):
        _fail(
            ProbeBridgeRejectionCode.STALE_FRAME_TABLE,
            "Joined frame table does not match the submitted A/B documents.",
        )
    if not isinstance(fold_manifest, Mapping):
        _fail(
            ProbeBridgeRejectionCode.INVALID_FOLD_MANIFEST,
            "Fold manifest must be a mapping.",
        )
    if (
        fold_manifest.get("synthetic") is not True
        or fold_manifest.get("scientific_use") != "forbidden"
    ):
        _fail(
            ProbeBridgeRejectionCode.INVALID_SYNTHETIC_MARKING,
            "Chunk 2 fold evidence must remain explicitly synthetic and forbidden.",
        )
    memberships = _fold_memberships(fold_manifest)
    frame_rows = {_frame_key(row): row for row in frame_table["rows"]}
    if set(memberships) != set(frame_rows):
        _fail(
            ProbeBridgeRejectionCode.MISSING_FOLD_ASSIGNMENT,
            "Fold memberships do not exactly cover joined frames.",
        )
    try:
        validate_fold_manifest(fold_manifest)
    except (GroupedSplitError, AnalysisArtifactError, KeyError, TypeError) as error:
        _fail(
            ProbeBridgeRejectionCode.INVALID_FOLD_MANIFEST,
            f"Fold manifest validation failed: {error}",
        )
    if (
        fold_manifest.get("input_manifest_hash") != frame_table["frame_table_hash"]
        or fold_manifest.get("config_hash") != frame_table["analysis_config_hash"]
        or fold_manifest.get("analysis_config_version")
        != frame_table["analysis_config_version"]
        or fold_manifest.get("code_sha") != frame_table["probe_code_sha"]
    ):
        _fail(
            ProbeBridgeRejectionCode.STALE_FOLD_MANIFEST,
            "Fold manifest is not bound to this frame table and config.",
        )

    for key, membership in memberships.items():
        if membership.get("layout_id") != frame_rows[key].get("layout_id"):
            _fail(
                ProbeBridgeRejectionCode.CONFLICTING_FOLD_ASSIGNMENT,
                f"Fold membership for {key!r} names the wrong layout.",
            )

    joined = _join(activation_package, target_document)
    propagated: list[dict[str, Any]] = []
    seen: set[tuple[str, int, int, str]] = set()
    fold_by_frame: dict[tuple[str, int], int] = {}
    for item in joined:
        activation = item.activation_index_row
        target = item.target_row
        frame_key = _frame_key(activation)
        identity = (
            frame_key[0],
            frame_key[1],
            activation.get("layer_idx"),
            activation.get("hook_site"),
        )
        if identity in seen:
            _fail(
                ProbeBridgeRejectionCode.INCOMPLETE_LAYER_SITE_GRID,
                f"Duplicate activation identity {identity!r}.",
            )
        seen.add(identity)
        fold = memberships[frame_key]["fold_idx"]
        previous_fold = fold_by_frame.setdefault(frame_key, fold)
        if previous_fold != fold:
            _fail(
                ProbeBridgeRejectionCode.CONFLICTING_PROPAGATED_FOLD,
                f"Frame {frame_key!r} would receive multiple folds.",
            )
        row = dict(activation)
        for field in (
            "target_id",
            "target_schema_version",
            "target_source",
            "oracle_method",
            "oracle_information_set",
            "last_visible_position_blocks",
            "mu_oracle_blocks",
            "var_oracle_blocks2",
            "sigma_oracle_blocks",
            "log_sigma_oracle",
            "x_true_blocks",
            "source_run_id",
        ):
            if field in target:
                row[field] = target[field]
        row.update(
            {
                "target_run_id": target.get("run_id"),
                "target_code_sha": target.get("code_sha"),
                "target_config_hash": target.get("config_hash"),
                "outer_fold_idx": fold,
                "fold_manifest_hash": fold_manifest["artifact_hash"],
                "fold_version": fold_manifest["fold_schema_version"],
                "fold_config_hash": fold_manifest["config_hash"],
                "analysis_config_version": fold_manifest[
                    "analysis_config_version"
                ],
                "frame_table_hash": frame_table["frame_table_hash"],
                "activation_handoff_hash": frame_table[
                    "activation_handoff_hash"
                ],
                "target_document_hash": frame_table["target_document_hash"],
                "probe_code_sha": frame_table["probe_code_sha"],
                "synthetic": True,
                "scientific_use": "forbidden",
            }
        )
        propagated.append(row)
    return tuple(
        sorted(
            propagated,
            key=lambda row: (
                row["trajectory_id"],
                row["model_frame_idx"],
                row["layer_idx"],
                row["hook_site"],
            ),
        )
    )


def load_activation_vectors(
    activation_package: Mapping[str, Any],
    chunk_payloads_by_id: Mapping[str, bytes],
) -> dict[tuple[str, int], tuple[float, ...]]:
    """Load vectors from explicit chunk identities and verified literal bytes."""

    if not isinstance(activation_package, Mapping) or not isinstance(
        chunk_payloads_by_id,
        Mapping,
    ):
        _fail(
            ProbeBridgeRejectionCode.INVALID_ACTIVATION_HANDOFF,
            "Activation package and chunk payloads must be mappings.",
        )
    index_rows = activation_package.get("index_rows")
    if not isinstance(index_rows, list):
        _fail(
            ProbeBridgeRejectionCode.INVALID_ACTIVATION_HANDOFF,
            "Activation index rows are malformed.",
        )
    seen_claims: set[tuple[str, int]] = set()
    for row in index_rows:
        if not isinstance(row, Mapping):
            continue
        chunk_id = row.get("activation_chunk_id")
        chunk_row_idx = row.get("chunk_row_idx")
        if isinstance(chunk_id, str) and isinstance(chunk_row_idx, int):
            claim = (chunk_id, chunk_row_idx)
            if claim in seen_claims:
                _fail(
                    ProbeBridgeRejectionCode.DUPLICATE_CHUNK_ROW_CLAIM,
                    f"Multiple activation rows claim {claim!r}.",
                )
            seen_claims.add(claim)
    validation = validate_activation_handoff(activation_package)
    if not validation.accepted:
        codes = sorted({item.code.value for item in validation.rejections})
        _fail(
            ProbeBridgeRejectionCode.INVALID_ACTIVATION_HANDOFF,
            "Activation handoff validation failed: " + ", ".join(codes),
        )

    descriptors = activation_package.get("chunks")
    if not isinstance(descriptors, list):
        _fail(
            ProbeBridgeRejectionCode.INVALID_ACTIVATION_HANDOFF,
            "Activation chunk descriptors are malformed.",
        )
    descriptor_by_id = {descriptor["chunk_id"]: descriptor for descriptor in descriptors}
    declared_ids = set(descriptor_by_id)
    if any(
        not isinstance(chunk_id, str) or not chunk_id
        for chunk_id in chunk_payloads_by_id
    ):
        _fail(
            ProbeBridgeRejectionCode.INVALID_CHUNK,
            "Every supplied chunk payload key must be a non-empty chunk ID.",
        )
    supplied_ids = set(chunk_payloads_by_id)
    missing_ids = sorted(declared_ids - supplied_ids)
    if missing_ids:
        _fail(
            ProbeBridgeRejectionCode.MISSING_CHUNK,
            f"Missing payloads for chunks: {missing_ids}.",
        )
    extra_ids = sorted(supplied_ids - declared_ids)
    if extra_ids:
        _fail(
            ProbeBridgeRejectionCode.UNDECLARED_CHUNK,
            f"Undeclared chunk payloads were supplied: {extra_ids}.",
        )

    loaded: dict[tuple[str, int], tuple[float, ...]] = {}
    for chunk_id in sorted(declared_ids):
        descriptor = descriptor_by_id[chunk_id]
        payload = chunk_payloads_by_id[chunk_id]
        if not isinstance(payload, bytes):
            _fail(
                ProbeBridgeRejectionCode.INVALID_CHUNK,
                f"Chunk {chunk_id!r} payload must be bytes.",
            )
        actual_hash = hashlib.sha256(payload).hexdigest()
        if actual_hash != descriptor.get("sha256"):
            _fail(
                ProbeBridgeRejectionCode.CHUNK_HASH_MISMATCH,
                f"Chunk {chunk_id!r} literal-byte hash is stale.",
            )
        try:
            document = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            _fail(
                ProbeBridgeRejectionCode.INVALID_CHUNK,
                f"Chunk {chunk_id!r} is not valid UTF-8 JSON: {error}",
            )
        if not isinstance(document, Mapping) or document.get("chunk_id") != chunk_id:
            _fail(
                ProbeBridgeRejectionCode.INVALID_CHUNK,
                f"Chunk {chunk_id!r} document identity is invalid.",
            )
        if (
            document.get("dtype") != descriptor.get("dtype")
            or document.get("vector_shape") != descriptor.get("vector_shape")
        ):
            _fail(
                ProbeBridgeRejectionCode.VECTOR_METADATA_MISMATCH,
                f"Chunk {chunk_id!r} dtype or shape disagrees with its descriptor.",
            )
        rows = document.get("rows")
        row_count = descriptor.get("row_count")
        if not isinstance(rows, list) or not isinstance(row_count, int):
            _fail(
                ProbeBridgeRejectionCode.INVALID_CHUNK,
                f"Chunk {chunk_id!r} row metadata is invalid.",
            )
        by_index: dict[int, Mapping[str, Any]] = {}
        for row in rows:
            if not isinstance(row, Mapping):
                _fail(
                    ProbeBridgeRejectionCode.INVALID_CHUNK,
                    f"Chunk {chunk_id!r} contains a non-mapping row.",
                )
            row_idx = row.get("chunk_row_idx")
            if (
                not isinstance(row_idx, int)
                or isinstance(row_idx, bool)
                or not 0 <= row_idx < row_count
            ):
                _fail(
                    ProbeBridgeRejectionCode.CHUNK_ROW_OUT_OF_BOUNDS,
                    f"Chunk {chunk_id!r} has an out-of-bounds row index.",
                )
            if row_idx in by_index:
                _fail(
                    ProbeBridgeRejectionCode.DUPLICATE_CHUNK_ROW,
                    f"Chunk {chunk_id!r} duplicates row {row_idx}.",
                )
            by_index[row_idx] = row
        missing_rows = sorted(set(range(row_count)) - set(by_index))
        if missing_rows:
            _fail(
                ProbeBridgeRejectionCode.MISSING_CHUNK_ROW,
                f"Chunk {chunk_id!r} is missing rows {missing_rows}.",
            )
        if len(by_index) != row_count:
            _fail(
                ProbeBridgeRejectionCode.INVALID_CHUNK,
                f"Chunk {chunk_id!r} row count is inconsistent.",
            )
        shape = descriptor["vector_shape"]
        expected_size = shape[0]
        for row_idx in range(row_count):
            vector = by_index[row_idx].get("vector")
            if not isinstance(vector, list) or len(vector) != expected_size:
                _fail(
                    ProbeBridgeRejectionCode.VECTOR_METADATA_MISMATCH,
                    f"Chunk {chunk_id!r} row {row_idx} has the wrong vector shape.",
                )
            converted: list[float] = []
            for value in vector:
                if (
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not math.isfinite(float(value))
                    or abs(float(value)) > FLOAT32_MAX
                ):
                    _fail(
                        ProbeBridgeRejectionCode.INVALID_VECTOR,
                        f"Chunk {chunk_id!r} row {row_idx} is not finite float32 data.",
                    )
                converted.append(float(value))
            loaded[(chunk_id, row_idx)] = tuple(converted)

    loaded_claims = set(loaded)
    if seen_claims != loaded_claims:
        missing_claims = sorted(seen_claims - loaded_claims)
        unclaimed_rows = sorted(loaded_claims - seen_claims)
        _fail(
            ProbeBridgeRejectionCode.MISSING_CHUNK_ROW,
            "Activation/chunk row coverage differs; "
            f"missing={missing_claims}, unclaimed={unclaimed_rows}.",
        )
    return loaded


def _singleton(rows: Sequence[Mapping[str, Any]], field: str) -> Any:
    value = rows[0].get(field)
    if any(row.get(field) != value for row in rows[1:]):
        _fail(
            ProbeBridgeRejectionCode.INCONSISTENT_FRAME_METADATA,
            f"Propagated rows disagree on {field}.",
        )
    return value


def _probe_matrix_payload(matrix: ProbeReadyMatrix) -> dict[str, Any]:
    """Return the exact canonical content authenticated by ``matrix_hash``."""

    return {
        "schema_version": matrix.schema_version,
        "matrix_version": MATRIX_VERSION,
        "layer_idx": matrix.layer_idx,
        "hook_site": matrix.hook_site,
        "target_name": matrix.target_name,
        "accepted_manifest_hash": matrix.accepted_manifest_hash,
        "frame_table_hash": matrix.frame_table_hash,
        "fold_manifest_hash": matrix.fold_manifest_hash,
        "fold_version": matrix.fold_version,
        "analysis_config_hash": matrix.analysis_config_hash,
        "analysis_config_version": matrix.analysis_config_version,
        "target_code_sha": matrix.target_code_sha,
        "probe_code_sha": matrix.probe_code_sha,
        "activation_handoff_hash": matrix.activation_handoff_hash,
        "target_document_hash": matrix.target_document_hash,
        "activation_chunk_hashes": [
            {"activation_chunk_id": chunk_id, "sha256": chunk_hash}
            for chunk_id, chunk_hash in matrix.activation_chunk_hashes
        ],
        "synthetic": matrix.synthetic,
        "scientific_use": matrix.scientific_use,
        "rows": [
            {
                **dict(metadata),
                "target": target,
                "outer_fold_idx": fold,
                "layout_id": layout,
                "vector": list(vector),
            }
            for metadata, target, fold, layout, vector in zip(
                matrix.metadata_rows,
                matrix.targets,
                matrix.outer_folds,
                matrix.layout_ids,
                matrix.features,
            )
        ],
    }


def _validate_probe_matrix_hash(matrix: ProbeReadyMatrix) -> None:
    try:
        hash_matches = is_hex_digest(matrix.matrix_hash, 64) and (
            sha256_value(_probe_matrix_payload(matrix)) == matrix.matrix_hash
        )
    except (AnalysisArtifactError, KeyError, TypeError, ValueError):
        hash_matches = False
    if not hash_matches:
        _fail(
            ProbeBridgeRejectionCode.MATRIX_HASH_MISMATCH,
            "Probe matrix hash does not match exact X/y/fold/identity content.",
        )


def build_probe_ready_matrices(
    activation_package: Mapping[str, Any],
    target_document: Mapping[str, Any],
    frame_table: Mapping[str, Any],
    fold_manifest: Mapping[str, Any],
    chunk_payloads_by_id: Mapping[str, bytes],
    *,
    target_name: str = "mu_oracle_blocks",
    propagated_rows: Sequence[Mapping[str, Any]] | None = None,
    loaded_vectors: Mapping[tuple[str, int], Sequence[float]] | None = None,
    analysis_config_hash: str | None = None,
) -> tuple[ProbeReadyMatrix, ...]:
    """Rebuild and authenticate exact A/B evidence before constructing X/y."""

    if not isinstance(target_name, str) or target_name not in SUPPORTED_TARGETS:
        _fail(
            ProbeBridgeRejectionCode.MISSING_TARGET,
            f"Unsupported probe target {target_name!r}.",
        )
    expected_frame_table = build_joined_frame_table(
        activation_package,
        target_document,
        analysis_config_hash=analysis_config_hash,
    )
    if not isinstance(frame_table, Mapping) or expected_frame_table != dict(
        frame_table
    ):
        _fail(
            ProbeBridgeRejectionCode.INTERMEDIATE_PROVENANCE_MISMATCH,
            "Frame table does not authenticate the submitted A/B source evidence.",
        )
    rebuilt_rows = propagate_frame_folds(
        activation_package,
        target_document,
        frame_table,
        fold_manifest,
    )
    rebuilt_vectors = load_activation_vectors(
        activation_package,
        chunk_payloads_by_id,
    )
    if propagated_rows is not None:
        if (
            not isinstance(propagated_rows, Sequence)
            or tuple(dict(row) for row in propagated_rows if isinstance(row, Mapping))
            != rebuilt_rows
            or any(not isinstance(row, Mapping) for row in propagated_rows)
        ):
            _fail(
                ProbeBridgeRejectionCode.INTERMEDIATE_PROVENANCE_MISMATCH,
                "Caller-supplied propagated rows differ from rebuilt source evidence.",
            )
    if loaded_vectors is not None:
        if not isinstance(loaded_vectors, Mapping) or dict(loaded_vectors) != rebuilt_vectors:
            _fail(
                ProbeBridgeRejectionCode.INTERMEDIATE_PROVENANCE_MISMATCH,
                "Caller-supplied vectors differ from the authenticated chunk bytes.",
            )
    propagated_rows = rebuilt_rows
    loaded_vectors = rebuilt_vectors
    if not propagated_rows:
        _fail(
            ProbeBridgeRejectionCode.INCOMPLETE_LAYER_SITE_GRID,
            "Propagated activation rows are empty.",
        )
    rows = [dict(row) for row in propagated_rows if isinstance(row, Mapping)]
    if len(rows) != len(propagated_rows):
        _fail(
            ProbeBridgeRejectionCode.INCOMPLETE_LAYER_SITE_GRID,
            "Every propagated activation row must be a mapping.",
        )
    seen_identity: set[tuple[str, int, int, str]] = set()
    sites_by_frame: dict[tuple[str, int], set[tuple[int, str]]] = defaultdict(set)
    fold_by_frame: dict[tuple[str, int], int] = {}
    seen_vector_claims: set[tuple[str, int]] = set()
    rows_by_site: dict[tuple[int, str], list[dict[str, Any]]] = defaultdict(list)
    all_sites: set[tuple[int, str]] = set()

    for row in rows:
        frame = _frame_key(row)
        layer = row.get("layer_idx")
        site = row.get("hook_site")
        fold = row.get("outer_fold_idx")
        if (
            not isinstance(layer, int)
            or isinstance(layer, bool)
            or layer < 0
            or not isinstance(site, str)
            or not site
        ):
            _fail(
                ProbeBridgeRejectionCode.INCOMPLETE_LAYER_SITE_GRID,
                f"Frame {frame!r} has invalid layer/site metadata.",
            )
        if row.get("status") != "accepted":
            _fail(
                ProbeBridgeRejectionCode.INVALID_LIFECYCLE,
                f"Activation row {(frame, layer, site)!r} is not accepted.",
            )
        if not isinstance(fold, int) or isinstance(fold, bool) or fold < 0:
            _fail(
                ProbeBridgeRejectionCode.MISSING_FOLD_ASSIGNMENT,
                f"Frame {frame!r} has no valid propagated fold.",
            )
        prior_fold = fold_by_frame.setdefault(frame, fold)
        if prior_fold != fold:
            _fail(
                ProbeBridgeRejectionCode.CONFLICTING_PROPAGATED_FOLD,
                f"Frame {frame!r} crosses propagated folds.",
            )
        identity = (frame[0], frame[1], layer, site)
        if identity in seen_identity:
            _fail(
                ProbeBridgeRejectionCode.INCOMPLETE_LAYER_SITE_GRID,
                f"Duplicate propagated activation identity {identity!r}.",
            )
        seen_identity.add(identity)
        chunk_id = row.get("activation_chunk_id")
        chunk_row_idx = row.get("chunk_row_idx")
        if (
            not isinstance(chunk_id, str)
            or not chunk_id
            or not isinstance(chunk_row_idx, int)
            or isinstance(chunk_row_idx, bool)
            or chunk_row_idx < 0
        ):
            _fail(
                ProbeBridgeRejectionCode.MISSING_CHUNK_ROW,
                f"Activation identity {identity!r} has an invalid chunk claim.",
            )
        claim = (chunk_id, chunk_row_idx)
        if claim in seen_vector_claims:
            _fail(
                ProbeBridgeRejectionCode.DUPLICATE_CHUNK_ROW_CLAIM,
                f"Multiple propagated rows claim {claim!r}.",
            )
        seen_vector_claims.add(claim)
        if target_name not in row or (
            isinstance(row.get(target_name), bool)
            or not isinstance(row.get(target_name), (int, float))
            or not math.isfinite(float(row[target_name]))
        ):
            _fail(
                ProbeBridgeRejectionCode.MISSING_TARGET,
                f"Activation identity {identity!r} lacks a finite {target_name}.",
            )
        site_key = (layer, site)
        sites_by_frame[frame].add(site_key)
        all_sites.add(site_key)
        rows_by_site[site_key].append(row)

    incomplete = {
        frame: sorted(all_sites - sites)
        for frame, sites in sites_by_frame.items()
        if sites != all_sites
    }
    if incomplete:
        _fail(
            ProbeBridgeRejectionCode.INCOMPLETE_LAYER_SITE_GRID,
            f"Layer/site coverage is incomplete: {incomplete}.",
        )

    accepted_manifest_hash = _singleton(rows, "accepted_manifest_hash")
    frame_table_hash = _singleton(rows, "frame_table_hash")
    fold_manifest_hash = _singleton(rows, "fold_manifest_hash")
    fold_version = _singleton(rows, "fold_version")
    analysis_config_hash = _singleton(rows, "fold_config_hash")
    analysis_config_version = _singleton(rows, "analysis_config_version")
    target_code_sha = _singleton(rows, "target_code_sha")
    probe_code_sha = _singleton(rows, "probe_code_sha")
    activation_handoff_hash = _singleton(rows, "activation_handoff_hash")
    target_document_hash = _singleton(rows, "target_document_hash")
    synthetic = _singleton(rows, "synthetic")
    scientific_use = _singleton(rows, "scientific_use")
    for field, value, length in (
        ("accepted_manifest_hash", accepted_manifest_hash, 64),
        ("frame_table_hash", frame_table_hash, 64),
        ("fold_manifest_hash", fold_manifest_hash, 64),
        ("fold_config_hash", analysis_config_hash, 64),
        ("target_code_sha", target_code_sha, 40),
        ("probe_code_sha", probe_code_sha, 40),
        ("activation_handoff_hash", activation_handoff_hash, 64),
        ("target_document_hash", target_document_hash, 64),
    ):
        if not is_hex_digest(value, length):
            _fail(
                ProbeBridgeRejectionCode.INCONSISTENT_FRAME_METADATA,
                f"Propagated rows contain invalid {field} provenance.",
            )
    if fold_version != FOLD_SCHEMA_VERSION:
        _fail(
            ProbeBridgeRejectionCode.INCONSISTENT_FRAME_METADATA,
            "Propagated rows contain an unsupported fold version.",
        )
    if (
        analysis_config_hash != hash_core_analysis_config(DEFAULT_CONFIG_PATH)
        or analysis_config_version != ANALYSIS_CONFIG_VERSION
    ):
        _fail(
            ProbeBridgeRejectionCode.CONFIG_HASH_MISMATCH,
            "Propagated rows are not bound to literal frozen core.yaml.",
        )
    if probe_code_sha != derive_probe_code_sha():
        _fail(
            ProbeBridgeRejectionCode.PROBE_CODE_MISMATCH,
            "Propagated rows are not bound to current probe code.",
        )
    if synthetic is not True or scientific_use != "forbidden":
        _fail(
            ProbeBridgeRejectionCode.INVALID_SYNTHETIC_MARKING,
            "Chunk 2 propagated evidence must be synthetic and forbidden.",
        )
    if seen_vector_claims != set(loaded_vectors):
        _fail(
            ProbeBridgeRejectionCode.MISSING_CHUNK_ROW,
            "Propagated activation claims and verified vectors do not exactly match.",
        )
    matrices: list[ProbeReadyMatrix] = []
    activation_chunk_hashes = tuple(
        sorted(
            (descriptor["chunk_id"], descriptor["sha256"])
            for descriptor in activation_package["chunks"]
        )
    )

    for (layer, site), site_rows in sorted(rows_by_site.items()):
        ordered = sorted(
            site_rows,
            key=lambda row: (row["trajectory_id"], row["model_frame_idx"]),
        )
        features: list[tuple[float, ...]] = []
        metadata: list[dict[str, Any]] = []
        for row in ordered:
            claim = (row.get("activation_chunk_id"), row.get("chunk_row_idx"))
            vector = loaded_vectors.get(claim)
            if vector is None:
                _fail(
                    ProbeBridgeRejectionCode.MISSING_CHUNK_ROW,
                    f"No verified vector resolves activation claim {claim!r}.",
                )
            shape = row.get("vector_shape")
            if (
                row.get("dtype") != "float32"
                or not isinstance(shape, list)
                or len(shape) != 1
                or not isinstance(shape[0], int)
                or isinstance(shape[0], bool)
                or shape[0] <= 0
                or not isinstance(vector, Sequence)
                or isinstance(vector, (str, bytes, bytearray))
                or len(vector) != shape[0]
            ):
                _fail(
                    ProbeBridgeRejectionCode.VECTOR_METADATA_MISMATCH,
                    f"Activation claim {claim!r} has incompatible dtype or shape.",
                )
            converted: list[float] = []
            for value in vector:
                if (
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not math.isfinite(float(value))
                    or abs(float(value)) > FLOAT32_MAX
                ):
                    _fail(
                        ProbeBridgeRejectionCode.INVALID_VECTOR,
                        f"Activation claim {claim!r} is not finite float32 data.",
                    )
                converted.append(float(value))
            features.append(tuple(converted))
            metadata.append(
                {
                    "trajectory_id": row["trajectory_id"],
                    "model_frame_idx": row["model_frame_idx"],
                    "episode_id": row["episode_id"],
                    "layout_id": row["layout_id"],
                    "layer_idx": layer,
                    "hook_site": site,
                    "activation_chunk_id": row["activation_chunk_id"],
                    "chunk_row_idx": row["chunk_row_idx"],
                    "outer_fold_idx": row["outer_fold_idx"],
                    "fold_manifest_hash": row["fold_manifest_hash"],
                    "fold_version": row["fold_version"],
                    "frame_table_hash": row["frame_table_hash"],
                    "accepted_manifest_hash": row["accepted_manifest_hash"],
                    "target_id": row["target_id"],
                }
            )
        vector_sizes = {len(vector) for vector in features}
        if len(vector_sizes) != 1:
            _fail(
                ProbeBridgeRejectionCode.VECTOR_METADATA_MISMATCH,
                f"Layer/site {(layer, site)!r} has inconsistent vector shapes.",
            )
        matrix = ProbeReadyMatrix(
            schema_version=SCHEMA_VERSION,
            layer_idx=layer,
            hook_site=site,
            target_name=target_name,
            features=tuple(features),
            targets=tuple(float(row[target_name]) for row in ordered),
            outer_folds=tuple(row["outer_fold_idx"] for row in ordered),
            layout_ids=tuple(row["layout_id"] for row in ordered),
            metadata_rows=tuple(metadata),
            accepted_manifest_hash=accepted_manifest_hash,
            frame_table_hash=frame_table_hash,
            fold_manifest_hash=fold_manifest_hash,
            fold_version=fold_version,
            analysis_config_hash=analysis_config_hash,
            analysis_config_version=analysis_config_version,
            target_code_sha=target_code_sha,
            probe_code_sha=probe_code_sha,
            activation_handoff_hash=activation_handoff_hash,
            target_document_hash=target_document_hash,
            activation_chunk_hashes=activation_chunk_hashes,
            matrix_hash="",
            synthetic=True,
            scientific_use="forbidden",
        )
        matrices.append(
            replace(
                matrix,
                matrix_hash=sha256_value(_probe_matrix_payload(matrix)),
            )
        )
    return tuple(matrices)


def run_ridge_oof_probe(
    matrix: ProbeReadyMatrix,
    *,
    artifact_id_prefix: str,
    alpha_grid: Sequence[float] | None = None,
    inner_fold_count: int | None = None,
    seed: int | None = None,
) -> RidgeProbeExecution:
    """Run deterministic OOF ridge on verified vectors and seal U1 evidence."""

    if not isinstance(matrix, ProbeReadyMatrix):
        _fail(
            ProbeBridgeRejectionCode.PROBE_FIT_FAILED,
            "OOF ridge requires an authenticated ProbeReadyMatrix.",
        )
    if matrix.schema_version != SCHEMA_VERSION:
        _fail(
            ProbeBridgeRejectionCode.PROBE_FIT_FAILED,
            "Probe matrix does not use universal schema v1.0.",
        )
    _validate_probe_matrix_hash(matrix)
    if matrix.synthetic is not True or matrix.scientific_use != "forbidden":
        _fail(
            ProbeBridgeRejectionCode.INVALID_SYNTHETIC_MARKING,
            "Chunk 2 probe matrices must remain synthetic and forbidden.",
        )
    literal_config_hash = hash_core_analysis_config(DEFAULT_CONFIG_PATH)
    frozen_config = load_core_analysis_config(DEFAULT_CONFIG_PATH)
    frozen_cv = frozen_config["cross_validation"]
    frozen_alpha_grid = tuple(
        float(value) for value in frozen_config["ridge"]["alpha_grid"]
    )
    try:
        requested_alpha_grid = (
            frozen_alpha_grid
            if alpha_grid is None
            else tuple(float(value) for value in alpha_grid)
        )
        requested_inner_fold_count = (
            frozen_cv["inner_fold_count"]
            if inner_fold_count is None
            else inner_fold_count
        )
        requested_seed = frozen_cv["split_seed"] if seed is None else seed
    except (TypeError, ValueError) as error:
        _fail(
            ProbeBridgeRejectionCode.FROZEN_PROBE_CONFIG_MISMATCH,
            f"Probe tuning arguments are malformed: {error}",
        )
    if (
        matrix.analysis_config_hash != literal_config_hash
        or matrix.analysis_config_version != ANALYSIS_CONFIG_VERSION
    ):
        _fail(
            ProbeBridgeRejectionCode.CONFIG_HASH_MISMATCH,
            "Probe matrix is not bound to literal frozen core.yaml.",
        )
    if matrix.probe_code_sha != derive_probe_code_sha():
        _fail(
            ProbeBridgeRejectionCode.PROBE_CODE_MISMATCH,
            "Probe matrix code provenance is stale.",
        )
    if (
        requested_alpha_grid != frozen_alpha_grid
        or requested_inner_fold_count != frozen_cv["inner_fold_count"]
        or requested_seed != frozen_cv["split_seed"]
    ):
        _fail(
            ProbeBridgeRejectionCode.FROZEN_PROBE_CONFIG_MISMATCH,
            "Ridge alpha grid, inner-fold count, and seed must match core.yaml.",
        )
    if not isinstance(artifact_id_prefix, str) or not artifact_id_prefix:
        _fail(
            ProbeBridgeRejectionCode.ARTIFACT_BUILD_FAILED,
            "artifact_id_prefix must be non-empty.",
        )
    row_count = len(matrix.features)
    if row_count == 0 or any(
        len(values) != row_count
        for values in (
            matrix.targets,
            matrix.outer_folds,
            matrix.layout_ids,
            matrix.metadata_rows,
        )
    ):
        _fail(
            ProbeBridgeRejectionCode.PROBE_FIT_FAILED,
            "Probe matrix columns and metadata must have equal non-zero cardinality.",
        )
    seen_predictions: set[tuple[str, int, int, str]] = set()
    for index, metadata in enumerate(matrix.metadata_rows):
        if not isinstance(metadata, Mapping):
            _fail(
                ProbeBridgeRejectionCode.PROBE_FIT_FAILED,
                f"Probe metadata row {index} must be a mapping.",
            )
        identity = (
            metadata.get("trajectory_id"),
            metadata.get("model_frame_idx"),
            metadata.get("layer_idx"),
            metadata.get("hook_site"),
        )
        if (
            not isinstance(identity[0], str)
            or not identity[0]
            or not isinstance(identity[1], int)
            or isinstance(identity[1], bool)
            or identity[1] < 0
            or not isinstance(identity[2], int)
            or isinstance(identity[2], bool)
            or not isinstance(identity[3], str)
            or not identity[3]
            or identity in seen_predictions
            or identity[2] != matrix.layer_idx
            or identity[3] != matrix.hook_site
            or metadata.get("outer_fold_idx") != matrix.outer_folds[index]
            or metadata.get("layout_id") != matrix.layout_ids[index]
        ):
            _fail(
                ProbeBridgeRejectionCode.PROBE_FIT_FAILED,
                f"Probe metadata row {index} has conflicting identity or fold data.",
            )
        seen_predictions.add(identity)
    try:
        result = fit_ridge_oof(
            matrix.features,
            matrix.targets,
            matrix.outer_folds,
            matrix.layout_ids,
            alpha_grid=requested_alpha_grid,
            inner_fold_count=requested_inner_fold_count,
            seed=requested_seed,
        )
    except ProbeFitError as error:
        _fail(
            ProbeBridgeRejectionCode.PROBE_FIT_FAILED,
            f"OOF ridge fitting failed: {error}",
        )

    fit_by_fold = {fit.outer_fold_idx: fit for fit in result.fits}
    probe_parameters = {
        "alpha_grid": list(frozen_alpha_grid),
        "inner_fold_count": frozen_cv["inner_fold_count"],
        "outer_fold_seed": frozen_cv["split_seed"],
    }
    fold_fit_records: list[dict[str, Any]] = []
    for fit in sorted(result.fits, key=lambda item: item.outer_fold_idx):
        training_membership = [
            {
                "trajectory_id": matrix.metadata_rows[index]["trajectory_id"],
                "model_frame_idx": matrix.metadata_rows[index]["model_frame_idx"],
                "layout_id": matrix.layout_ids[index],
            }
            for index in fit.training_indices
        ]
        test_membership = [
            {
                "trajectory_id": matrix.metadata_rows[index]["trajectory_id"],
                "model_frame_idx": matrix.metadata_rows[index]["model_frame_idx"],
                "layout_id": matrix.layout_ids[index],
            }
            for index in fit.test_indices
        ]
        scaler = fit.model.scaler
        fold_fit_records.append(
            {
                "outer_fold_idx": fit.outer_fold_idx,
                "selected_alpha": fit.alpha_selection.selected_alpha,
                "mean_mse_by_alpha": [
                    {"alpha": alpha, "mean_mse": mse}
                    for alpha, mse in sorted(
                        fit.alpha_selection.mean_mse_by_alpha.items()
                    )
                ],
                "inner_fold_count": fit.alpha_selection.inner_fold_count,
                "training_indices": list(fit.training_indices),
                "test_indices": list(fit.test_indices),
                "training_membership": training_membership,
                "test_membership": test_membership,
                "scaler": {
                    "fit_scope": "outer_training_rows_only",
                    "training_row_count": scaler.training_row_count,
                    "feature_count": len(scaler.mean),
                    "constant_feature_indices": list(
                        scaler.constant_feature_indices
                    ),
                    "mean_hash": sha256_value(list(scaler.mean)),
                    "scale_hash": sha256_value(list(scaler.scale)),
                },
            }
        )
    prediction_rows: list[dict[str, Any]] = []
    for index, (metadata, prediction) in enumerate(
        zip(matrix.metadata_rows, result.predictions)
    ):
        fold = matrix.outer_folds[index]
        fit = fit_by_fold.get(fold)
        if fit is None or index not in fit.test_indices or index in fit.training_indices:
            _fail(
                ProbeBridgeRejectionCode.PROBE_FIT_FAILED,
                f"Prediction row {index} is not backed by its held-out fold fit.",
            )
        prediction_rows.append(
            {
                "trajectory_id": metadata["trajectory_id"],
                "model_frame_idx": metadata["model_frame_idx"],
                "episode_id": metadata["episode_id"],
                "layout_id": metadata["layout_id"],
                "layer_idx": matrix.layer_idx,
                "hook_site": matrix.hook_site,
                "fold_idx": fold,
                "prediction": prediction,
                "fit_id": f"{artifact_id_prefix}:outer_fold_{fold}",
                "prediction_scope": "out_of_fold",
                "target_id": metadata["target_id"],
            }
        )
    try:
        prediction_artifact = build_prediction_artifact(
            prediction_rows,
            artifact_id=f"{artifact_id_prefix}:predictions",
            code_sha=matrix.probe_code_sha,
            config_hash=matrix.analysis_config_hash,
            input_manifest_hash=matrix.matrix_hash,
            fold_manifest_hash=matrix.fold_manifest_hash,
            model_family="ridge",
            target_name=matrix.target_name,
            layer_idx=matrix.layer_idx,
            hook_site=matrix.hook_site,
        )
        prediction_payload = dict(prediction_artifact)
        prediction_payload.pop("artifact_hash")
        prediction_payload.update(
            {
                "analysis_config_version": matrix.analysis_config_version,
                "matrix_hash": matrix.matrix_hash,
                "activation_handoff_hash": matrix.activation_handoff_hash,
                "target_document_hash": matrix.target_document_hash,
                "activation_chunk_hashes": [
                    {"activation_chunk_id": chunk_id, "sha256": chunk_hash}
                    for chunk_id, chunk_hash in matrix.activation_chunk_hashes
                ],
                "probe_parameters": probe_parameters,
                "fold_fit_records": fold_fit_records,
                "synthetic": True,
                "scientific_use": "forbidden",
            }
        )
        prediction_artifact = seal_artifact(prediction_payload)

        metrics = regression_metrics(matrix.targets, result.predictions)
        u1_result_artifact = build_result_artifact(
            [
                {
                    "metric_id": "u1_mae",
                    "metric_name": "mae",
                    "value": metrics.mae,
                    "unit": "blocks",
                    "sample_count": metrics.sample_count,
                    "sample_unit": "frame",
                    "status": "valid",
                    "diagnostic": None,
                },
                {
                    "metric_id": "u1_mse",
                    "metric_name": "mse",
                    "value": metrics.mse,
                    "unit": "blocks_squared",
                    "sample_count": metrics.sample_count,
                    "sample_unit": "frame",
                    "status": "valid",
                    "diagnostic": None,
                },
                {
                    "metric_id": "u1_r2",
                    "metric_name": "r2",
                    "value": metrics.r2,
                    "unit": "dimensionless",
                    "sample_count": metrics.sample_count,
                    "sample_unit": "frame",
                    "status": "valid",
                    "diagnostic": None,
                },
            ],
            artifact_id=f"{artifact_id_prefix}:u1_results",
            code_sha=matrix.probe_code_sha,
            config_hash=matrix.analysis_config_hash,
            input_manifest_hash=matrix.matrix_hash,
            fold_manifest_hash=matrix.fold_manifest_hash,
            prediction_manifest_hashes=[prediction_artifact["artifact_hash"]],
            analysis_family="U1",
        )
        result_payload = dict(u1_result_artifact)
        result_payload.pop("artifact_hash")
        result_payload.update(
            {
                "analysis_config_version": matrix.analysis_config_version,
                "matrix_hash": matrix.matrix_hash,
                "probe_parameters": probe_parameters,
                "fold_fit_records": fold_fit_records,
                "fold_fit_records_hash": sha256_value(fold_fit_records),
                "synthetic": True,
                "scientific_use": "forbidden",
            }
        )
        u1_result_artifact = seal_artifact(result_payload)
    except (AnalysisArtifactError, U1MetricError, KeyError, TypeError) as error:
        _fail(
            ProbeBridgeRejectionCode.ARTIFACT_BUILD_FAILED,
            f"OOF prediction/result artifact construction failed: {error}",
        )
    return RidgeProbeExecution(
        oof_result=result,
        prediction_artifact=prediction_artifact,
        u1_result_artifact=u1_result_artifact,
    )
