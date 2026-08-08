"""Real production input materialization and ingestion (Person D Step 4.1).

Closes the last gap the eight-family production CLI left open: turning
Person B's real, committed target/fold/source-context artifacts and
Person C's real, committed capture packages into the exact in-memory
inputs :func:`mineocclude.baselines.eight_family_runner.fit_and_export_family`
already knows how to consume (contexts, ``mu_oracle_by_key``,
``log_sigma_oracle_by_key``, ``visible_positions_by_trajectory``,
``pixel_features_by_key``).

Two different kinds of "not locally present" input are handled
differently, matching what each artifact actually is:

* ``fold_manifest``, ``oracle_target``, ``source_context_manifest``, and
  Person A's ``preprocessed_frame_manifest`` are all committed Git blobs
  living only on another role's branch (never merged onto
  ``role/person-d-baselines``). :func:`materialize_git_committed_artifact`
  reads the exact blob via ``git show <commit>:<path>`` and writes it,
  byte-verified, into a local runtime-input directory -- it never checks
  out, merges, or mutates the source branch.
* The 1,695 real preprocessed frame *payloads* are not committed to Git
  at all (they are multi-gigabyte binary files that only exist in the
  approved SageMaker environment) -- those are read directly from
  ``--frame-root``, exactly as the existing preflight path already does.

Capture-package provenance note: Person B's own frozen
``FROZEN_SOURCE_CONTEXTS``/``source_context_manifest.json`` cite a
``capture_package`` identity (path/sha256/byte_size) for each of the ten
pilots. That exact identity does **not** match the content committed at
the same path on Person B's own branch (``role/person-b-analysis``) --
it does match the content at the same path on Person C's branch
(``role/person-c-data``), at the commit Person B's own
``source_context_manifest.json`` already separately cites as
``person_c_expansion_acceptance``. This was verified directly (byte-for-
byte, all ten pilots) before writing ``PERSON_C_EXPANSION_ACCEPTANCE_COMMIT``
below; capture packages are therefore materialized from Person C's
branch, the contract's own designated producer of this data
(docs/contracts/trajectory_v1.md), never from Person B's.

Nothing in this module fits a baseline, computes a metric, or reads a
U4 artifact.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np

from mineocclude.analysis.manifests import sha256_value
from mineocclude.baselines.baseline_family_input_v0_2 import (
    FROZEN_DIRECT_INPUTS,
    FROZEN_PILOT_IDS,
)
from mineocclude.baselines.capture_ingest import (
    CaptureIngestError,
    build_contexts_from_capture,
)
from mineocclude.baselines.eight_family_execution_manifest import FROZEN_SOURCE_CONTEXTS
from mineocclude.baselines.export import BaselineExportError, attach_b_fold_assignments
from mineocclude.baselines.interface import TrajectoryContext

RowKey = tuple[str, int]

#: Person C's branch and the exact commit Person B's own
#: ``source_context_manifest.json`` cites (``person_c_expansion_acceptance``)
#: as the authoritative acceptance of these ten pilots' capture packages.
#: Independently re-verified: the raw bytes at this commit, for every one
#: of the ten frozen ``FROZEN_SOURCE_CONTEXTS`` paths, match that entry's
#: declared sha256/byte_size exactly.
PERSON_C_BRANCH = "role/person-c-data"
PERSON_C_EXPANSION_ACCEPTANCE_COMMIT = "c6bff25b5ef4f5fdb0e1ef0ce0d22e3f8b5e4960"

#: Person A's committed frame-handoff commit/path (already bound in
#: frame_handoff_v0_2.py) is the materialization source for the frame
#: manifest itself -- never for the frame payloads, which never enter Git.
ORACLE_TARGET_SCHEMA_VERSION = "person-b-oracle-target-v0.1"
ORACLE_TARGET_JOIN_KEY = ("trajectory_id", "model_frame_idx")
REQUIRED_ORACLE_TARGET_ROW_COUNT = 1695


class ProductionInputIngestError(ValueError):
    """Raised when a real production input cannot be honestly loaded, verified, or joined."""


def verify_raw_bytes(
    path: Path, *, expected_sha256: str, expected_byte_size: int
) -> tuple[str, ...]:
    """Verify a local file's actual raw bytes before anything parses it."""

    if not path.exists():
        return ("file_not_found",)
    raw = path.read_bytes()
    errors: list[str] = []
    if len(raw) != expected_byte_size:
        errors.append(f"byte_size_mismatch:expected={expected_byte_size}:actual={len(raw)}")
    actual_sha256 = hashlib.sha256(raw).hexdigest()
    if actual_sha256 != expected_sha256:
        errors.append(f"sha256_mismatch:expected={expected_sha256}:actual={actual_sha256}")
    return tuple(errors)


def load_and_verify_json_artifact(
    path: Path, *, expected_sha256: str, expected_byte_size: int
) -> Any:
    """Verify a local JSON artifact's raw bytes, then parse it.

    Never trusts parsed content ahead of an exact raw-byte match --
    the same discipline :func:`mineocclude.baselines.frame_handoff_v0_2
    .verify_frame_manifest_raw_bytes` already applies to the frame manifest.
    """

    errors = verify_raw_bytes(
        path, expected_sha256=expected_sha256, expected_byte_size=expected_byte_size
    )
    if errors:
        raise ProductionInputIngestError(
            f"{path}: raw-byte verification failed: {errors}"
        )
    return json.loads(path.read_text(encoding="utf-8"))


def materialize_git_committed_artifact(
    *,
    repo_root: Path,
    commit: str,
    repo_relative_path: str,
    output_path: Path,
    expected_sha256: str,
    expected_byte_size: int,
) -> Path:
    """Read one committed blob from another role's branch and verify+persist it.

    Uses ``git show <commit>:<path>`` -- a plain object read, never a
    checkout, merge, or working-tree mutation of the source branch. Fails
    closed if the object cannot be read at all, or if its raw bytes do
    not match the exact frozen identity the caller expects; never writes
    anything back to the source path.
    """

    result = subprocess.run(
        ["git", "show", f"{commit}:{repo_relative_path}"],
        cwd=repo_root,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise ProductionInputIngestError(
            f"failed to read {commit}:{repo_relative_path}: "
            f"{result.stderr.decode('utf-8', 'replace')}"
        )
    raw = result.stdout
    actual_sha256 = hashlib.sha256(raw).hexdigest()
    if len(raw) != expected_byte_size or actual_sha256 != expected_sha256:
        raise ProductionInputIngestError(
            f"materialized {commit}:{repo_relative_path} failed raw-byte "
            f"verification: expected=({expected_sha256},{expected_byte_size}) "
            f"actual=({actual_sha256},{len(raw)})"
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(raw)
    return output_path


def verify_oracle_target_manifest_structure(document: Any) -> tuple[str, ...]:
    """Independent structural check over Person B's real oracle-target document.

    Deliberately does not call :func:`mineocclude.oracle.schema
    .validate_oracle_target_document` -- that validator's ``coordinate_frame``
    (singular) expectation does not match the real production document's
    ``coordinate_frames_by_trajectory`` (per-trajectory, plural) shape, a
    known unresolved schema-shape mismatch noted in earlier preparation.
    This function checks only the fields this module actually consumes.
    """

    if not isinstance(document, Mapping):
        return ("document_not_mapping",)

    errors: list[str] = []
    if document.get("target_schema_version") != ORACLE_TARGET_SCHEMA_VERSION:
        errors.append("target_schema_version_mismatch")
    if document.get("config_hash") != FROZEN_DIRECT_INPUTS["analysis_config"]["sha256"]:
        errors.append("config_hash_mismatch")
    if tuple(document.get("join_key") or ()) != ORACLE_TARGET_JOIN_KEY:
        errors.append("join_key_mismatch")
    if document.get("row_count") != REQUIRED_ORACLE_TARGET_ROW_COUNT:
        errors.append("row_count_mismatch")
    accepted_pilot_ids = document.get("accepted_pilot_ids")
    if not isinstance(accepted_pilot_ids, list) or tuple(accepted_pilot_ids) != FROZEN_PILOT_IDS:
        errors.append("accepted_pilot_ids_mismatch")
    if document.get("u4_output_inspected") is not False:
        errors.append("u4_access_not_forbidden")
    rows = document.get("rows")
    if not isinstance(rows, list) or len(rows) != REQUIRED_ORACLE_TARGET_ROW_COUNT:
        errors.append("rows_count_mismatch")
    return tuple(errors)


def build_oracle_target_lookups(
    document: Mapping[str, Any],
) -> tuple[dict[RowKey, float], dict[RowKey, float]]:
    """Extract ``mu_oracle_by_key``/``log_sigma_oracle_by_key`` from real oracle rows.

    Only ``status == "accepted"`` rows contribute, and only the target a
    given row actually carries a finite numeric value for -- matching
    the oracle document's own ``null_policy: null_outside_eligibility``
    convention for ``log_sigma_oracle`` (about 695 of 1,695 rows).
    """

    mu_oracle_by_key: dict[RowKey, float] = {}
    log_sigma_oracle_by_key: dict[RowKey, float] = {}
    for row in document.get("rows", ()):
        if not isinstance(row, Mapping) or row.get("status") != "accepted":
            continue
        trajectory_id = row.get("trajectory_id")
        model_frame_idx = row.get("model_frame_idx")
        if not isinstance(trajectory_id, str) or not isinstance(model_frame_idx, int):
            continue
        key = (trajectory_id, model_frame_idx)
        mu = row.get("mu_oracle_blocks")
        if isinstance(mu, (int, float)) and not isinstance(mu, bool):
            mu_oracle_by_key[key] = float(mu)
        log_sigma = row.get("log_sigma_oracle")
        if isinstance(log_sigma, (int, float)) and not isinstance(log_sigma, bool):
            log_sigma_oracle_by_key[key] = float(log_sigma)
    return mu_oracle_by_key, log_sigma_oracle_by_key


def build_scripted_context_by_trajectory(document: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Extract each trajectory's known experimental condition from real oracle rows.

    Every row for one trajectory must agree on ``layout_id``/``v``/``q``/
    ``duration``/``seed`` -- a disagreement is an upstream data problem to
    raise, not something this function averages or silently picks one of.
    """

    by_trajectory: dict[str, dict[str, Any]] = {}
    for row in document.get("rows", ()):
        if not isinstance(row, Mapping):
            continue
        trajectory_id = row.get("trajectory_id")
        if not isinstance(trajectory_id, str) or not trajectory_id:
            continue
        fields = {
            "layout_id": row.get("layout_id"),
            "v_scripted_blocks_per_s": row.get("v"),
            "q_scripted_blocks2_per_s": row.get("q"),
            "duration_seconds": row.get("duration"),
            "seed": row.get("seed"),
        }
        existing = by_trajectory.get(trajectory_id)
        if existing is None:
            by_trajectory[trajectory_id] = fields
        elif existing != fields:
            raise ProductionInputIngestError(
                f"trajectory {trajectory_id!r} has inconsistent scripted "
                f"fields across oracle target rows: {existing} != {fields}"
            )
    return by_trajectory


def load_capture_package(
    *,
    source_context_root: Path,
    trajectory_id: str,
    expected_reference: Mapping[str, Any],
) -> dict:
    """Load and byte-verify one real capture package against its frozen reference."""

    relative_path = expected_reference.get("path")
    if not isinstance(relative_path, str) or not relative_path:
        raise ProductionInputIngestError(
            f"{trajectory_id}: invalid capture_package path reference"
        )
    full_path = source_context_root / relative_path
    document = load_and_verify_json_artifact(
        full_path,
        expected_sha256=expected_reference["sha256"],
        expected_byte_size=expected_reference["byte_size"],
    )
    if document.get("trajectory_id") != trajectory_id:
        raise ProductionInputIngestError(
            f"{trajectory_id}: capture package trajectory_id mismatch: "
            f"{document.get('trajectory_id')!r}"
        )
    return document


def extract_visible_positions(capture_package: Mapping[str, Any]) -> list[float]:
    """Real chronological visible-window positions, for visible_history_q's q-estimate.

    Read directly from the capture package's own ``server_state``/
    ``visibility`` streams (never from a derived last-seen scalar) so the
    full pre-occlusion visible history is available, not just its most
    recent point.
    """

    streams = capture_package.get("streams")
    if not isinstance(streams, Mapping):
        raise ProductionInputIngestError("capture package is missing 'streams'")
    server_state_rows = streams.get("server_state")
    visibility_rows = streams.get("visibility")
    if not isinstance(server_state_rows, list) or not isinstance(visibility_rows, list):
        raise ProductionInputIngestError(
            "capture package is missing server_state/visibility row streams"
        )
    visibility_by_idx = {
        row.get("model_frame_idx"): row.get("visibility")
        for row in visibility_rows
        if isinstance(row, Mapping)
    }
    positions: list[tuple[int, float]] = []
    for row in server_state_rows:
        if not isinstance(row, Mapping):
            continue
        idx = row.get("model_frame_idx")
        if visibility_by_idx.get(idx) != "visible":
            continue
        state = row.get("state")
        if not isinstance(state, Mapping) or "wall_parallel_position_blocks" not in state:
            continue
        positions.append((idx, float(state["wall_parallel_position_blocks"])))
    positions.sort(key=lambda item: item[0])
    return [position for _, position in positions]


def build_all_trajectory_contexts(
    *,
    source_context_root: Path,
    oracle_target_document: Mapping[str, Any],
    fold_manifest: Mapping[str, Any],
    config_hash: str,
) -> tuple[list[TrajectoryContext], dict[str, list[float]]]:
    """Build every admitted frame's :class:`TrajectoryContext` from real inputs.

    Joins the ten real capture packages (causal contexts only, via
    :func:`mineocclude.baselines.capture_ingest.build_contexts_from_capture`)
    against Person B's real fold manifest (via
    :func:`mineocclude.baselines.export.attach_b_fold_assignments`, which
    validates the manifest itself and requires exact coverage). Only
    frames the fold manifest actually admits are ever requested -- the
    raw capture packages describe more frames (excluded ones too) than
    the frozen 1,695-frame admitted set.
    """

    scripted_by_trajectory = build_scripted_context_by_trajectory(oracle_target_document)
    memberships = fold_manifest.get("memberships")
    if not isinstance(memberships, list):
        raise ProductionInputIngestError("fold manifest has no memberships")
    admitted_keys = {
        (membership.get("trajectory_id"), membership.get("model_frame_idx"))
        for membership in memberships
        if isinstance(membership, Mapping)
    }

    all_contexts: list[TrajectoryContext] = []
    visible_positions_by_trajectory: dict[str, list[float]] = {}

    for source_context in FROZEN_SOURCE_CONTEXTS:
        trajectory_id = source_context["trajectory_id"]
        scripted = scripted_by_trajectory.get(trajectory_id)
        if scripted is None:
            raise ProductionInputIngestError(
                f"{trajectory_id}: no scripted context found in the oracle target manifest"
            )
        capture_package = load_capture_package(
            source_context_root=source_context_root,
            trajectory_id=trajectory_id,
            expected_reference=source_context["capture_package"],
        )
        streams = capture_package.get("streams")
        if not isinstance(streams, Mapping):
            raise ProductionInputIngestError(f"{trajectory_id}: capture package is missing 'streams'")
        try:
            contexts = build_contexts_from_capture(
                streams.get("frame_map", []),
                streams.get("server_state", []),
                streams.get("visibility", []),
                layout_id=scripted["layout_id"],
                config_hash=config_hash,
                v_scripted_blocks_per_s=scripted["v_scripted_blocks_per_s"],
                q_scripted_blocks2_per_s=scripted["q_scripted_blocks2_per_s"],
                duration_seconds=scripted["duration_seconds"],
                seed=scripted["seed"],
            )
        except CaptureIngestError as error:
            raise ProductionInputIngestError(f"{trajectory_id}: {error}") from error

        admitted_contexts = [
            ctx for ctx in contexts if (ctx.trajectory_id, ctx.model_frame_idx) in admitted_keys
        ]
        all_contexts.extend(admitted_contexts)
        visible_positions_by_trajectory[trajectory_id] = extract_visible_positions(capture_package)

    try:
        annotated_contexts = attach_b_fold_assignments(all_contexts, fold_manifest=fold_manifest)
    except BaselineExportError as error:
        raise ProductionInputIngestError(f"fold assignment failed: {error}") from error

    return annotated_contexts, visible_positions_by_trajectory


def build_pixel_features_by_key(
    *, frame_manifest: Mapping[str, Any], frame_root: Path
) -> dict[RowKey, np.ndarray]:
    """Read every real preprocessed frame payload into a compact feature vector.

    Only ``raw_pixel`` consumes this, and it is the single largest
    in-memory structure this runner ever builds (437,391,360 float32
    values across all 1,695 admitted frames -- roughly 1.6 GiB compact).
    Every value is decoded straight into a ``float32`` NumPy array via
    :func:`_decode_little_endian_float32` -- never a Python list of
    boxed ``float`` objects, which would multiply this footprint by
    roughly 8x (each boxed Python float is 24+ bytes versus 4 bytes
    packed) and was the confirmed root cause of a production OOM kill
    (13.035 GiB minimum boxed footprint on a 15 GiB, zero-swap host).

    Assumes the caller has already run
    :func:`mineocclude.baselines.frame_handoff_v0_2.verify_frame_payloads_on_disk`
    against this exact ``frame_manifest``/``frame_root`` pair (the
    production CLI's ``run`` mode always does, unconditionally) -- this
    function does not re-verify each payload's hash, only decodes it.

    Callers must treat the returned mapping as a single family-scoped,
    short-lived structure: build it immediately before ``raw_pixel``
    fits and drop every reference to it immediately afterward (the
    production CLI's ``run_production`` does exactly this) so the
    following families never carry this memory forward.
    """

    features: dict[RowKey, np.ndarray] = {}
    for record in frame_manifest.get("records", ()):
        if not isinstance(record, Mapping):
            continue
        trajectory_id = record.get("trajectory_id")
        model_frame_idx = record.get("model_frame_idx")
        relative_path = record.get("output_relative_path")
        if (
            not isinstance(trajectory_id, str)
            or not isinstance(model_frame_idx, int)
            or not isinstance(relative_path, str)
        ):
            continue
        payload = (frame_root / relative_path).read_bytes()
        features[(trajectory_id, model_frame_idx)] = _decode_little_endian_float32(payload)
    return features


def _decode_little_endian_float32(payload: bytes) -> np.ndarray:
    """Decode raw little-endian float32 bytes into a compact, owned array.

    ``np.frombuffer`` returns a read-only view over ``payload``; ``.copy()``
    detaches it from that (short-lived, per-call) ``bytes`` buffer into
    its own owned, writeable allocation -- exactly one float32 array per
    frame, never a Python list of boxed floats.
    """

    return np.frombuffer(payload, dtype="<f4").copy()


def build_input_manifest_hash(execution_manifest: Mapping[str, Any]) -> str:
    """Hash the real, verified input-identity binding for this exact run.

    Derived only from already-verified direct-input/source-context
    identities the preflight execution manifest binds -- never a
    fabricated placeholder.
    """

    return sha256_value(
        {
            "direct_inputs": execution_manifest["direct_inputs"],
            "source_contexts": execution_manifest["source_contexts"],
        }
    )


def build_fit_manifest_hash(execution_manifest: Mapping[str, Any]) -> str:
    """Hash the real, verified per-family code/configuration identity for this run."""

    return sha256_value({"baseline_families": execution_manifest["baseline_families"]})


__all__ = [
    "PERSON_C_BRANCH",
    "PERSON_C_EXPANSION_ACCEPTANCE_COMMIT",
    "ProductionInputIngestError",
    "build_all_trajectory_contexts",
    "build_fit_manifest_hash",
    "build_input_manifest_hash",
    "build_oracle_target_lookups",
    "build_pixel_features_by_key",
    "build_scripted_context_by_trajectory",
    "extract_visible_positions",
    "load_and_verify_json_artifact",
    "load_capture_package",
    "materialize_git_committed_artifact",
    "verify_oracle_target_manifest_structure",
    "verify_raw_bytes",
]
