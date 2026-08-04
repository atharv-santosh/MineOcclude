"""Operational wrappers over MineOcclude's shared registry authorities.

The frozen A-to-E rollout bundle and the Phase 1.2 immutable run/artifact
sub-schema both remain authoritative in ``contracts.rollout_registry``. This
module publishes, indexes, and raises friendly errors; it never defines a
competing registry schema.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import tempfile
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path
from typing import Any

from mineocclude.contracts.rollout_registry import (
    IMMUTABLE_REGISTRY_V2_SCHEMA_VERSION,
    ImmutableRegistryValidationResult,
    validate_immutable_run_artifact_registry,
    validate_rollout_registry_bundle,
)


class ProvenanceError(ValueError):
    """Raised when registry lineage cannot be trusted or written safely."""


_HASH_CHUNK_SIZE = 1024 * 1024


def hash_file_bytes(path: Path | str) -> str:
    """Stream SHA-256 over literal bytes, without path-derived identity."""

    hasher = hashlib.sha256()
    try:
        with Path(path).open("rb") as handle:
            while chunk := handle.read(_HASH_CHUNK_SIZE):
                hasher.update(chunk)
    except OSError as error:
        raise ProvenanceError(f"Could not hash {path}: {error}") from error
    return hasher.hexdigest()


def load_json_with_sha256(path: Path | str) -> tuple[Any, str]:
    """Read JSON bytes once, returning the parsed value and that byte digest."""

    source = Path(path)
    chunks: list[bytes] = []
    hasher = hashlib.sha256()
    try:
        with source.open("rb") as handle:
            while chunk := handle.read(_HASH_CHUNK_SIZE):
                chunks.append(chunk)
                hasher.update(chunk)
        payload = b"".join(chunks)
        document = json.loads(payload.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ProvenanceError(f"Could not load JSON {source}: {error}") from error
    return document, hasher.hexdigest()


def canonical_json_bytes(value: Any) -> bytes:
    """Serialize JSON deterministically while rejecting NaN and infinity."""

    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise ProvenanceError(f"Value is not canonical JSON: {error}") from error


def hash_json_value(value: Any) -> str:
    """Return a deterministic SHA-256 for one JSON-compatible value."""

    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def formatted_json_bytes(value: Any) -> bytes:
    """Serialize exactly as immutable JSON artifact writers persist it."""

    try:
        return (
            json.dumps(
                value,
                allow_nan=False,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise ProvenanceError(
            f"Value is not formatted-JSON serializable: {error}"
        ) from error


def write_bytes_exclusive(path: Path | str, payload: bytes) -> None:
    """Durably publish exact bytes without replacing an existing artifact."""

    if not isinstance(payload, bytes):
        raise ProvenanceError("payload must be bytes.")
    destination = Path(path)
    temporary_path: Path | None = None
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
        )
        temporary_path = Path(temporary_name)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())

        # A hard-link publish is atomic and, unlike replace/rename on POSIX,
        # refuses an already-existing destination.
        os.link(temporary_path, destination)
    except FileExistsError as error:
        raise ProvenanceError(
            f"Refusing to overwrite existing artifact: {destination}"
        ) from error
    except OSError as error:
        raise ProvenanceError(f"Could not write {destination}: {error}") from error
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                # The final artifact is already durable; a stale temporary file
                # is preferable to hiding a successfully published result.
                pass


def write_json_exclusive(path: Path | str, document: Any) -> None:
    """Durably publish JSON without replacing or exposing a partial artifact."""

    destination = Path(path)
    try:
        serialized = formatted_json_bytes(document)
    except ProvenanceError as error:
        raise ProvenanceError(f"Could not serialize {destination}: {error}") from error
    write_bytes_exclusive(destination, serialized)


def _raise_for_invalid_bundle(
    rollout_manifest: Mapping[str, Any], registry: Mapping[str, Any]
) -> None:
    result = validate_rollout_registry_bundle(rollout_manifest, registry)
    if result.accepted:
        return
    details = "; ".join(
        f"{rejection.code.value}: {rejection.message}"
        for rejection in result.rejections
    )
    raise ProvenanceError(f"Invalid rollout/registry bundle: {details}")


def require_valid_immutable_registry(
    document: Mapping[str, Any],
    *,
    previous_registry: Mapping[str, Any] | None = None,
    artifact_bytes_by_id: Mapping[str, bytes] | None = None,
    trusted_owner_authorities: Mapping[str, Mapping[str, Any]] | None = None,
    trusted_status_record_bytes: Mapping[str, bytes] | None = None,
    trusted_artifact_authorizations: Mapping[str, Mapping[str, Any]]
    | None = None,
    trusted_authorization_record_bytes: Mapping[str, bytes] | None = None,
    trusted_manifest_records: Mapping[str, Mapping[str, Any]] | None = None,
    trusted_artifact_receipts: Mapping[str, Mapping[str, Any]] | None = None,
) -> ImmutableRegistryValidationResult:
    """Delegate immutable-lineage validation to the one shared contract.

    The inputs are never mutated. A successful result is returned so callers
    can retain the shared validator's machine-readable decision; a rejected
    registry raises ``ProvenanceError`` without creating a second rule set.
    """

    result = validate_immutable_run_artifact_registry(
        document,
        previous_registry=previous_registry,
        artifact_bytes_by_id=artifact_bytes_by_id,
        trusted_owner_authorities=trusted_owner_authorities,
        trusted_status_record_bytes=trusted_status_record_bytes,
        trusted_artifact_authorizations=trusted_artifact_authorizations,
        trusted_authorization_record_bytes=trusted_authorization_record_bytes,
        trusted_manifest_records=trusted_manifest_records,
        trusted_artifact_receipts=trusted_artifact_receipts,
    )
    if result.accepted:
        return result
    details = "; ".join(
        f"{rejection.code.value}: {rejection.message}"
        for rejection in result.rejections
    )
    raise ProvenanceError(f"Invalid immutable registry: {details}")


PHASE1_LINEAGE_TRACE_SCHEMA_VERSION = "person-e-phase1-lineage-trace-v1.0"
PHASE2_STEP2_1_BLOCKER_SCHEMA_VERSION = (
    "person-e-phase2-step2.1-blocker-v0.1"
)
V2_IMPACT_QUERY_SCHEMA_VERSION = (
    "person-e-immutable-registry-v2-impact-query-v0.1"
)
V2_PROVENANCE_QUERY_SCHEMA_VERSION = (
    "person-e-immutable-registry-v2-provenance-query-v0.1"
)
V2_SUPERSESSION_IMPACT_SCHEMA_VERSION = (
    "person-e-immutable-registry-v2-supersession-impact-v0.1"
)


@dataclass(frozen=True)
class _EffectiveState:
    state: str
    reason: str
    stale_root_cause_artifact_ids: tuple[str, ...] = ()
    invalid_root_cause_artifact_ids: tuple[str, ...] = ()
    stale_root_causal_paths: tuple[tuple[str, ...], ...] = ()
    invalid_root_causal_paths: tuple[tuple[str, ...], ...] = ()

    @property
    def root_cause_artifact_ids(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                {
                    *self.stale_root_cause_artifact_ids,
                    *self.invalid_root_cause_artifact_ids,
                }
            )
        )


_PHASE2_STEP2_1_SOURCE_REVISIONS = {
    "person_a_execution_revision": "35baf673312af5c21ae3f22168de405bd4ee8bd9",
    "person_a_evidence_revision": "e5032cc00dd83716df6f8e1b863659477adddb95",
    "person_c_pilot_revision": "82ef1212091b3f32eac02d7eabe25d55376086f2",
}
_PHASE2_STEP2_1_MISSING_FIELDS = (
    {
        "authority": "person_a",
        "record_id": "person-a-phase2-aws-20260725-055616-step2.6",
        "fields": ["started_at", "ended_at"],
    },
    {
        "authority": "person_c",
        "record_id": "layout_00_ep9410",
        "fields": ["started_at", "ended_at"],
    },
    {
        "authority": "person_a",
        "record_id": "person-a-phase2-aws-20260725-055616-step2.6",
        "fields": ["external_artifact_byte_verification_authority"],
    },
    {
        "authority": "person_a",
        "record_id": "failed_attempts",
        "fields": ["authoritative_failed_attempt_registry_metadata"],
    },
)


def validate_phase2_step2_1_blocker_record(document: Mapping[str, Any]) -> None:
    """Validate the bounded, non-inferential Phase 2 Step 2.1 decision."""

    required = {
        "schema_version",
        "blocker_schema_version",
        "record_id",
        "step",
        "status",
        "pass_claimed",
        "real_completed_records_emitted",
        "located_committed_metadata",
        "source_revisions",
        "missing_authoritative_fields",
        "non_inference",
        "decision",
    }
    if not isinstance(document, Mapping) or set(document) != required:
        raise ProvenanceError("Step 2.1 blocker-record fields have changed.")
    if document["schema_version"] != "1.0":
        raise ProvenanceError("Step 2.1 blocker schema_version must remain '1.0'.")
    if (
        document["blocker_schema_version"]
        != PHASE2_STEP2_1_BLOCKER_SCHEMA_VERSION
    ):
        raise ProvenanceError("Unsupported Step 2.1 blocker-record version.")
    if document["record_id"] != "person_e_phase2_step2_1_blockers_v0_1":
        raise ProvenanceError("Step 2.1 blocker record_id is not authoritative.")
    if (
        document["step"] != "2.1"
        or document["status"] != "BLOCKED"
        or document["pass_claimed"] is not False
        or document["real_completed_records_emitted"] is not False
        or document["decision"] != "blocked_not_failed"
    ):
        raise ProvenanceError("Step 2.1 blocker decision overclaims completion.")
    if document["located_committed_metadata"] != {
        "person_a": True,
        "person_c": True,
    }:
        raise ProvenanceError("Located A/C metadata must be stated exactly.")
    if document["source_revisions"] != _PHASE2_STEP2_1_SOURCE_REVISIONS:
        raise ProvenanceError("Step 2.1 source revisions changed.")
    if document["missing_authoritative_fields"] != list(
        _PHASE2_STEP2_1_MISSING_FIELDS
    ):
        raise ProvenanceError("Step 2.1 missing authoritative fields changed.")
    if document["non_inference"] != {
        "timestamps_inferred": False,
        "external_byte_authority_inferred": False,
        "failed_attempts_manufactured": False,
    }:
        raise ProvenanceError("Step 2.1 non-inference declaration changed.")


class ImmutableRegistryIndex:
    """Deterministic read-only queries over the shared immutable registry."""

    def __init__(
        self,
        registry: Mapping[str, Any],
        *,
        artifact_bytes_by_id: Mapping[str, bytes] | None = None,
        trusted_owner_authorities: Mapping[str, Mapping[str, Any]]
        | None = None,
        trusted_status_record_bytes: Mapping[str, bytes] | None = None,
        trusted_artifact_authorizations: Mapping[str, Mapping[str, Any]]
        | None = None,
        trusted_authorization_record_bytes: Mapping[str, bytes] | None = None,
        trusted_manifest_records: Mapping[str, Mapping[str, Any]]
        | None = None,
        trusted_artifact_receipts: Mapping[str, Mapping[str, Any]]
        | None = None,
    ) -> None:
        if not isinstance(registry, Mapping):
            raise ProvenanceError("Immutable registry must be a mapping.")
        require_valid_immutable_registry(
            registry,
            artifact_bytes_by_id=artifact_bytes_by_id,
            trusted_owner_authorities=trusted_owner_authorities,
            trusted_status_record_bytes=trusted_status_record_bytes,
            trusted_artifact_authorizations=trusted_artifact_authorizations,
            trusted_authorization_record_bytes=trusted_authorization_record_bytes,
            trusted_manifest_records=trusted_manifest_records,
            trusted_artifact_receipts=trusted_artifact_receipts,
        )
        self._registry = copy.deepcopy(dict(registry))
        self._runs = {
            run["run_id"]: run for run in self._registry["runs"]
        }
        self._artifacts = {
            artifact["artifact_id"]: artifact
            for artifact in self._registry["artifacts"]
        }
        self._children: dict[str, list[str]] = {
            artifact_id: [] for artifact_id in self._artifacts
        }
        for artifact in self._artifacts.values():
            for input_id in artifact["direct_input_artifact_ids"]:
                self._children[input_id].append(artifact["artifact_id"])
        for children in self._children.values():
            children.sort()

    @staticmethod
    def _status_filter(
        statuses: Sequence[str] | None,
        *,
        allowed: set[str],
        name: str,
    ) -> set[str] | None:
        if statuses is None:
            return None
        if (
            not isinstance(statuses, Sequence)
            or isinstance(statuses, (str, bytes))
            or not statuses
            or any(not isinstance(status, str) for status in statuses)
        ):
            raise ProvenanceError(f"{name} must be a non-empty status sequence.")
        selected = set(statuses)
        if not selected <= allowed:
            raise ProvenanceError(f"{name} contains an unsupported status.")
        return selected

    def query_runs(
        self,
        *,
        statuses: Sequence[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Return all or lifecycle-filtered runs in canonical ID order."""

        selected = self._status_filter(
            statuses,
            allowed={"in_progress", "completed", "failed"},
            name="run statuses",
        )
        return [
            copy.deepcopy(self._runs[run_id])
            for run_id in sorted(self._runs)
            if selected is None or self._runs[run_id]["status"] in selected
        ]

    def query_artifacts(
        self,
        *,
        statuses: Sequence[str] | None = None,
        artifact_types: Sequence[str] | None = None,
        creator_run_statuses: Sequence[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Return deterministic all-status or explicitly filtered artifacts."""

        selected_statuses = self._status_filter(
            statuses,
            allowed={"accepted", "excluded", "superseded"},
            name="artifact statuses",
        )
        selected_run_statuses = self._status_filter(
            creator_run_statuses,
            allowed={"in_progress", "completed", "failed"},
            name="creator run statuses",
        )
        selected_types: set[str] | None = None
        if artifact_types is not None:
            if (
                not isinstance(artifact_types, Sequence)
                or isinstance(artifact_types, (str, bytes))
                or not artifact_types
                or any(
                    not isinstance(artifact_type, str) or not artifact_type
                    for artifact_type in artifact_types
                )
            ):
                raise ProvenanceError(
                    "artifact_types must be a non-empty string sequence."
                )
            selected_types = set(artifact_types)
        rows: list[dict[str, Any]] = []
        for artifact_id in sorted(self._artifacts):
            artifact = self._artifacts[artifact_id]
            creator_status = self._runs[artifact["creator_run_id"]]["status"]
            if (
                selected_statuses is not None
                and artifact["status"] not in selected_statuses
            ):
                continue
            if (
                selected_types is not None
                and artifact["artifact_type"] not in selected_types
            ):
                continue
            if (
                selected_run_statuses is not None
                and creator_status not in selected_run_statuses
            ):
                continue
            rows.append(copy.deepcopy(artifact))
        return rows

    def accepted_artifacts(
        self,
        *,
        artifact_types: Sequence[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Return only current artifacts from completed creator runs."""

        return self.query_artifacts(
            statuses=["accepted"],
            artifact_types=artifact_types,
            creator_run_statuses=["completed"],
        )

    def _lineage(
        self,
        artifact_id: str,
        *,
        direction: str,
    ) -> dict[str, Any]:
        if not isinstance(artifact_id, str) or not artifact_id:
            raise ProvenanceError("artifact_id must be non-empty.")
        if artifact_id not in self._artifacts:
            raise ProvenanceError(f"Unknown artifact_id {artifact_id!r}.")
        visited: set[str] = set()
        edges: set[tuple[str, str]] = set()

        def visit(current_id: str) -> None:
            neighbors = (
                self._artifacts[current_id]["direct_input_artifact_ids"]
                if direction == "backward"
                else self._children[current_id]
            )
            for neighbor_id in sorted(neighbors):
                edge = (
                    (neighbor_id, current_id)
                    if direction == "backward"
                    else (current_id, neighbor_id)
                )
                edges.add(edge)
                if neighbor_id not in visited:
                    visited.add(neighbor_id)
                    visit(neighbor_id)

        visit(artifact_id)
        return {
            "schema_version": self._registry["schema_version"],
            "registry_id": self._registry["registry_id"],
            "subject_artifact_id": artifact_id,
            "direction": direction,
            "artifact_nodes": [
                copy.deepcopy(self._artifacts[node_id])
                for node_id in sorted(visited)
            ],
            "direct_input_edges": [
                {
                    "input_artifact_id": input_id,
                    "output_artifact_id": output_id,
                }
                for input_id, output_id in sorted(edges)
            ],
        }

    def backward_lineage(self, artifact_id: str) -> dict[str, Any]:
        """Return deterministic transitive direct inputs for an artifact."""

        return self._lineage(artifact_id, direction="backward")

    def forward_lineage(self, artifact_id: str) -> dict[str, Any]:
        """Return deterministic transitive consumers for an artifact."""

        return self._lineage(artifact_id, direction="forward")

    def _require_v2(self) -> None:
        if (
            self._registry.get("immutable_registry_schema_version")
            != IMMUTABLE_REGISTRY_V2_SCHEMA_VERSION
        ):
            raise ProvenanceError(
                "This query requires an explicitly validated immutable-registry v2 document."
            )

    def _require_artifact_id(self, artifact_id: str) -> None:
        if not isinstance(artifact_id, str) or not artifact_id:
            raise ProvenanceError("artifact_id must be a non-empty string.")
        if artifact_id not in self._artifacts:
            raise ProvenanceError(f"Unknown artifact_id {artifact_id!r}.")

    def _require_run_id(self, run_id: str) -> None:
        if not isinstance(run_id, str) or not run_id:
            raise ProvenanceError("run_id must be a non-empty string.")
        if run_id not in self._runs:
            raise ProvenanceError(f"Unknown run_id {run_id!r}.")

    def _all_forward_paths(
        self,
        root_artifact_ids: Sequence[str],
    ) -> dict[str, tuple[tuple[str, ...], ...]]:
        paths_by_artifact: dict[str, set[tuple[str, ...]]] = {}

        def visit(current_id: str, path: tuple[str, ...]) -> None:
            for child_id in self._children[current_id]:
                child_path = (*path, child_id)
                paths_by_artifact.setdefault(child_id, set()).add(child_path)
                visit(child_id, child_path)

        for root_id in sorted(root_artifact_ids):
            visit(root_id, (root_id,))
        return {
            artifact_id: tuple(sorted(paths))
            for artifact_id, paths in paths_by_artifact.items()
        }

    def _all_backward_paths(
        self,
        subject_artifact_id: str,
    ) -> dict[str, tuple[tuple[str, ...], ...]]:
        paths_by_artifact: dict[str, set[tuple[str, ...]]] = {}

        def visit(current_id: str, reverse_path: tuple[str, ...]) -> None:
            inputs = self._artifacts[current_id]["direct_input_artifact_ids"]
            for input_id in sorted(inputs):
                input_reverse_path = (*reverse_path, input_id)
                causal_path = tuple(reversed(input_reverse_path))
                paths_by_artifact.setdefault(input_id, set()).add(causal_path)
                visit(input_id, input_reverse_path)

        visit(subject_artifact_id, (subject_artifact_id,))
        return {
            artifact_id: tuple(sorted(paths))
            for artifact_id, paths in paths_by_artifact.items()
        }

    def _effective_state(
        self,
        artifact_id: str,
        *,
        root_effects: Mapping[str, str],
        memo: dict[str, _EffectiveState],
        active: set[str],
    ) -> _EffectiveState:
        cached = memo.get(artifact_id)
        if cached is not None:
            return cached
        if artifact_id in active:
            raise ProvenanceError(
                f"Artifact dependency cycle encountered at {artifact_id!r}."
            )
        artifact = self._artifacts[artifact_id]
        creator = self._runs[artifact["creator_run_id"]]
        override = root_effects.get(artifact_id)
        own_stale_roots: set[str] = set()
        own_invalid_roots: set[str] = set()
        own_stale_paths: set[tuple[str, ...]] = set()
        own_invalid_paths: set[tuple[str, ...]] = set()
        own_stale_reason: str | None = None
        own_invalid_reason: str | None = None
        if override == "stale":
            own_stale_roots.add(artifact_id)
            own_stale_paths.add((artifact_id,))
            own_stale_reason = "hypothetical_structural_supersession"
        elif override == "invalid":
            own_invalid_roots.add(artifact_id)
            own_invalid_paths.add((artifact_id,))
            own_invalid_reason = "hypothetical_upstream_unusable"
        if artifact["status"] == "superseded":
            own_stale_roots.add(artifact_id)
            own_stale_paths.add((artifact_id,))
            own_stale_reason = "artifact_structurally_superseded"
        elif artifact["status"] == "excluded":
            own_invalid_roots.add(artifact_id)
            own_invalid_paths.add((artifact_id,))
            own_invalid_reason = "artifact_excluded"
        if creator["status"] != "completed":
            own_invalid_roots.add(artifact_id)
            own_invalid_paths.add((artifact_id,))
            own_invalid_reason = f"creator_run_{creator['status']}"

        next_active = {*active, artifact_id}
        dependency_states = [
            self._effective_state(
                input_id,
                root_effects=root_effects,
                memo=memo,
                active=next_active,
            )
            for input_id in artifact["direct_input_artifact_ids"]
        ]
        stale_roots = {
            *own_stale_roots,
            *(
                root_id
                for dependency in dependency_states
                for root_id in dependency.stale_root_cause_artifact_ids
            ),
        }
        invalid_roots = {
            *own_invalid_roots,
            *(
                root_id
                for dependency in dependency_states
                for root_id in dependency.invalid_root_cause_artifact_ids
            ),
        }
        stale_paths = {
            *own_stale_paths,
            *(
                (*path, artifact_id)
                for dependency in dependency_states
                for path in dependency.stale_root_causal_paths
            ),
        }
        invalid_paths = {
            *own_invalid_paths,
            *(
                (*path, artifact_id)
                for dependency in dependency_states
                for path in dependency.invalid_root_causal_paths
            ),
        }
        if invalid_roots:
            if stale_roots:
                reason = "invalid_precedence_with_stale_causes"
            elif (
                own_invalid_reason is not None
                and invalid_roots == {artifact_id}
            ):
                reason = own_invalid_reason
            else:
                reason = "depends_on_unusable_artifact"
            result = _EffectiveState(
                state="invalid",
                reason=reason,
                stale_root_cause_artifact_ids=tuple(sorted(stale_roots)),
                invalid_root_cause_artifact_ids=tuple(
                    sorted(invalid_roots)
                ),
                stale_root_causal_paths=tuple(sorted(stale_paths)),
                invalid_root_causal_paths=tuple(sorted(invalid_paths)),
            )
        elif stale_roots:
            if (
                own_stale_reason is not None
                and stale_roots == {artifact_id}
            ):
                reason = own_stale_reason
            else:
                reason = "depends_on_structurally_superseded_artifact"
            result = _EffectiveState(
                state="stale",
                reason=reason,
                stale_root_cause_artifact_ids=tuple(sorted(stale_roots)),
                stale_root_causal_paths=tuple(sorted(stale_paths)),
            )
        else:
            result = _EffectiveState(
                state="current",
                reason="no_unusable_or_superseded_dependency",
            )
        memo[artifact_id] = result
        return result

    @staticmethod
    def _effective_cause_fields(
        effective: _EffectiveState,
    ) -> dict[str, Any]:
        path_causes = [
            {
                "causal_path": list(path),
                "effective_state_cause": state,
                "root_cause_artifact_id": path[0],
            }
            for state, paths in (
                ("invalid", effective.invalid_root_causal_paths),
                ("stale", effective.stale_root_causal_paths),
            )
            for path in paths
        ]
        path_causes.sort(
            key=lambda row: (
                row["causal_path"],
                row["effective_state_cause"],
            )
        )
        return {
            "root_cause_artifact_ids": list(
                effective.root_cause_artifact_ids
            ),
            "stale_root_cause_artifact_ids": list(
                effective.stale_root_cause_artifact_ids
            ),
            "invalid_root_cause_artifact_ids": list(
                effective.invalid_root_cause_artifact_ids
            ),
            "stale_root_causal_paths": [
                list(path) for path in effective.stale_root_causal_paths
            ],
            "invalid_root_causal_paths": [
                list(path) for path in effective.invalid_root_causal_paths
            ],
            "causal_path_causes": path_causes,
        }

    def _validated_root_effects(
        self,
        *,
        root_artifact_ids: Sequence[str],
        root_effective_state: str | None,
        root_effective_states_by_artifact_id: Mapping[str, str] | None,
    ) -> dict[str, str]:
        if (
            root_effective_state is not None
            and root_effective_states_by_artifact_id is not None
        ):
            raise ProvenanceError(
                "Scalar and per-artifact root effective states are ambiguous."
            )
        if root_effective_state not in {None, "stale", "invalid"}:
            raise ProvenanceError(
                "root_effective_state must be stale, invalid, or null."
            )
        root_ids = set(root_artifact_ids)
        if root_effective_states_by_artifact_id is None:
            return (
                {
                    root_id: root_effective_state
                    for root_id in root_ids
                }
                if root_effective_state is not None
                else {}
            )
        if not isinstance(root_effective_states_by_artifact_id, Mapping):
            raise ProvenanceError(
                "root_effective_states_by_artifact_id must be a mapping."
            )
        effects: dict[str, str] = {}
        for artifact_id, state in root_effective_states_by_artifact_id.items():
            if not isinstance(artifact_id, str) or not artifact_id:
                raise ProvenanceError(
                    "Root effective-state mapping keys must be artifact IDs."
                )
            if artifact_id in effects:
                raise ProvenanceError(
                    "Root effective-state mapping contains a duplicate artifact."
                )
            if artifact_id not in self._artifacts:
                raise ProvenanceError(
                    f"Unknown root-state artifact_id {artifact_id!r}."
                )
            if artifact_id not in root_ids:
                raise ProvenanceError(
                    f"Artifact {artifact_id!r} is not an output of the queried run."
                )
            if state not in {"stale", "invalid"}:
                raise ProvenanceError(
                    "Mapped root effective states must be stale or invalid."
                )
            effects[artifact_id] = state
        return effects

    def _forward_impact(
        self,
        *,
        subject_type: str,
        subject_id: str,
        root_artifact_ids: Sequence[str],
        root_effective_state: str | None,
        root_effective_states_by_artifact_id: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        root_effects = self._validated_root_effects(
            root_artifact_ids=root_artifact_ids,
            root_effective_state=root_effective_state,
            root_effective_states_by_artifact_id=(
                root_effective_states_by_artifact_id
            ),
        )
        paths_by_artifact = self._all_forward_paths(root_artifact_ids)
        memo: dict[str, _EffectiveState] = {}
        root_ids = set(root_artifact_ids)
        subject_output_artifacts: list[dict[str, Any]] = []
        subject_output_dependency_edges: list[dict[str, str]] = []
        for root_id in sorted(root_ids):
            artifact = self._artifacts[root_id]
            effective = self._effective_state(
                root_id,
                root_effects=root_effects,
                memo=memo,
                active=set(),
            )
            direct_root_inputs = sorted(
                set(artifact["direct_input_artifact_ids"]) & root_ids
            )
            subject_output_artifacts.append(
                {
                    "artifact_id": root_id,
                    "artifact_type": artifact["artifact_type"],
                    "creator_run_id": artifact["creator_run_id"],
                    "subject_distance": 0,
                    "base_lifecycle_status": artifact["status"],
                    "assigned_hypothetical_root_state": root_effects.get(
                        root_id
                    ),
                    "effective_state": effective.state,
                    "effective_state_reason": effective.reason,
                    "direct_subject_output_dependency_artifact_ids": (
                        direct_root_inputs
                    ),
                    "causal_paths_from_subject_outputs": [
                        list(path)
                        for path in paths_by_artifact.get(root_id, ())
                    ],
                    **self._effective_cause_fields(effective),
                }
            )
            subject_output_dependency_edges.extend(
                {
                    "upstream_subject_output_artifact_id": input_id,
                    "downstream_subject_output_artifact_id": root_id,
                    "relationship": "direct_input_artifact_ids",
                }
                for input_id in direct_root_inputs
            )
        rows: list[dict[str, Any]] = []
        for artifact_id, paths in paths_by_artifact.items():
            if subject_type == "run" and artifact_id in root_ids:
                continue
            artifact = self._artifacts[artifact_id]
            effective = self._effective_state(
                artifact_id,
                root_effects=root_effects,
                memo=memo,
                active=set(),
            )
            distance = min(len(path) - 1 for path in paths)
            discovery_path = min(
                path for path in paths if len(path) - 1 == distance
            )
            rows.append(
                {
                    "subject_type": subject_type,
                    "subject_id": subject_id,
                    "affected_artifact_id": artifact_id,
                    "affected_creator_run_id": artifact["creator_run_id"],
                    "artifact_type": artifact["artifact_type"],
                    "graph_distance": distance,
                    "discovery_predecessor_artifact_id": discovery_path[-2],
                    "causal_paths": [list(path) for path in paths],
                    "multiple_causal_paths": len(paths) > 1,
                    "base_lifecycle_status": artifact["status"],
                    "effective_state": effective.state,
                    "effective_state_reason": effective.reason,
                    **self._effective_cause_fields(effective),
                }
            )
        rows.sort(
            key=lambda row: (
                row["graph_distance"],
                row["affected_artifact_id"],
            )
        )
        return {
            "query_schema_version": V2_IMPACT_QUERY_SCHEMA_VERSION,
            "registry_id": self._registry["registry_id"],
            "subject_type": subject_type,
            "subject_id": subject_id,
            "subject_output_artifact_ids": sorted(root_artifact_ids),
            "subject_output_artifacts": subject_output_artifacts,
            "subject_output_dependency_edges": (
                subject_output_dependency_edges
            ),
            "root_effective_state": root_effective_state,
            "root_effective_states_by_artifact_id": {
                root_id: root_effects.get(root_id)
                for root_id in sorted(root_artifact_ids)
            },
            "affected_artifacts": rows,
        }

    def forward_artifact_impact(
        self,
        artifact_id: str,
        *,
        root_effective_state: str | None = None,
    ) -> dict[str, Any]:
        """Return every explicit transitive consumer of one v2 artifact."""

        self._require_v2()
        self._require_artifact_id(artifact_id)
        return self._forward_impact(
            subject_type="artifact",
            subject_id=artifact_id,
            root_artifact_ids=(artifact_id,),
            root_effective_state=root_effective_state,
        )

    def forward_run_impact(
        self,
        run_id: str,
        *,
        root_effective_state: str | None = None,
        root_effective_states_by_artifact_id: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        """Return the transitive consumer union for all outputs of one v2 run."""

        self._require_v2()
        self._require_run_id(run_id)
        return self._forward_impact(
            subject_type="run",
            subject_id=run_id,
            root_artifact_ids=tuple(self._runs[run_id]["output_artifact_ids"]),
            root_effective_state=root_effective_state,
            root_effective_states_by_artifact_id=(
                root_effective_states_by_artifact_id
            ),
        )

    def backward_provenance(self, artifact_id: str) -> dict[str, Any]:
        """Return complete explicit v2 input provenance for one artifact."""

        self._require_v2()
        self._require_artifact_id(artifact_id)
        paths_by_artifact = self._all_backward_paths(artifact_id)
        memo: dict[str, _EffectiveState] = {}
        rows: list[dict[str, Any]] = []
        edges: set[tuple[str, str]] = set()
        for upstream_id, paths in paths_by_artifact.items():
            upstream = self._artifacts[upstream_id]
            effective = self._effective_state(
                upstream_id,
                root_effects={},
                memo=memo,
                active=set(),
            )
            distance = min(len(path) - 1 for path in paths)
            discovery_path = min(
                path for path in paths if len(path) - 1 == distance
            )
            for path in paths:
                edges.update(pairwise(path))
            rows.append(
                {
                    "artifact_id": upstream_id,
                    "creator_run_id": upstream["creator_run_id"],
                    "artifact_type": upstream["artifact_type"],
                    "graph_distance": distance,
                    "direct_successor_artifact_id": discovery_path[1],
                    "causal_paths": [list(path) for path in paths],
                    "multiple_causal_paths": len(paths) > 1,
                    "owner_authority_id": upstream.get(
                        "owner_authority_id"
                    ),
                    "manifest_id": upstream.get("manifest_id"),
                    "base_lifecycle_status": upstream["status"],
                    "effective_state": effective.state,
                    "effective_state_reason": effective.reason,
                    **self._effective_cause_fields(effective),
                }
            )
        rows.sort(
            key=lambda row: (
                row["graph_distance"],
                row["artifact_id"],
            )
        )
        return {
            "query_schema_version": V2_PROVENANCE_QUERY_SCHEMA_VERSION,
            "registry_id": self._registry["registry_id"],
            "subject_artifact_id": artifact_id,
            "subject_creator_run_id": self._artifacts[artifact_id][
                "creator_run_id"
            ],
            "upstream_artifacts": rows,
            "creator_run_ids": sorted(
                {row["creator_run_id"] for row in rows}
            ),
            "direct_input_edges": [
                {
                    "input_artifact_id": input_id,
                    "output_artifact_id": output_id,
                }
                for input_id, output_id in sorted(edges)
            ],
        }

    def supersession_impact(self, artifact_id: str) -> dict[str, Any]:
        """Report descendants made stale by a hypothetical valid supersession."""

        self._require_v2()
        self._require_artifact_id(artifact_id)
        source = self._artifacts[artifact_id]
        if source["status"] != "accepted":
            raise ProvenanceError(
                "Supersession impact requires a currently accepted source."
            )
        impact = self.forward_artifact_impact(
            artifact_id,
            root_effective_state="stale",
        )
        rows = impact["affected_artifacts"]
        affected_ids = {
            row["affected_artifact_id"] for row in rows
        }
        unaffected_ids = sorted(
            set(self._artifacts) - affected_ids - {artifact_id}
        )
        memo: dict[str, _EffectiveState] = {}
        return {
            "query_schema_version": V2_SUPERSESSION_IMPACT_SCHEMA_VERSION,
            "registry_id": self._registry["registry_id"],
            "superseded_source_artifact_id": artifact_id,
            "superseded_source": {
                "artifact_id": artifact_id,
                "base_lifecycle_status": source["status"],
                "effective_state": "stale",
                "effective_state_reason": (
                    "hypothetical_structural_supersession"
                ),
                "current_usable_input": False,
            },
            "directly_affected_artifact_ids": [
                row["affected_artifact_id"]
                for row in rows
                if row["graph_distance"] == 1
            ],
            "transitively_affected_artifact_ids": [
                row["affected_artifact_id"]
                for row in rows
                if row["graph_distance"] > 1
            ],
            "stale_artifact_ids": [
                row["affected_artifact_id"]
                for row in rows
                if row["effective_state"] == "stale"
            ],
            "invalid_artifact_ids": [
                row["affected_artifact_id"]
                for row in rows
                if row["effective_state"] == "invalid"
            ],
            "unaffected_artifact_ids": unaffected_ids,
            "unaffected_artifacts": [
                {
                    "artifact_id": unaffected_id,
                    "effective_state": self._effective_state(
                        unaffected_id,
                        root_effects={artifact_id: "stale"},
                        memo=memo,
                        active=set(),
                    ).state,
                }
                for unaffected_id in unaffected_ids
            ],
            "affected_artifacts": copy.deepcopy(rows),
        }


def trace_phase1_figure_lineage(
    registry: Mapping[str, Any],
    figure_input_artifact_id: str,
) -> dict[str, Any]:
    """Return one deterministic Phase 1 figure-to-source lineage trace.

    The shared immutable-registry validator remains the authority.  This is a
    read-only E query over its explicit IDs and direct-input edges; URIs and
    physical record order never participate in lineage resolution.
    """

    require_valid_immutable_registry(registry)
    if not isinstance(figure_input_artifact_id, str) or not figure_input_artifact_id:
        raise ProvenanceError("figure_input_artifact_id must be non-empty.")
    artifacts = {
        artifact["artifact_id"]: artifact for artifact in registry["artifacts"]
    }
    runs = {run["run_id"]: run for run in registry["runs"]}
    root = artifacts.get(figure_input_artifact_id)
    if root is None or root["artifact_type"] != "figure_input":
        raise ProvenanceError(
            "Phase 1 trace root must be an explicit figure_input artifact."
        )

    visited: set[str] = set()
    edges: set[tuple[str, str]] = set()

    def visit(artifact_id: str) -> None:
        artifact = artifacts[artifact_id]
        creator = runs[artifact["creator_run_id"]]
        if (
            artifact["status"] != "accepted"
            or artifact["superseded_by"] is not None
            or creator["status"] != "completed"
        ):
            raise ProvenanceError(
                f"Trace source {artifact_id!r} is not current and completed."
            )
        if artifact_id in visited:
            return
        visited.add(artifact_id)
        for input_id in artifact["direct_input_artifact_ids"]:
            edges.add((input_id, artifact_id))
            visit(input_id)

    visit(figure_input_artifact_id)

    def ancestors_of_type(start_id: str, allowed_types: set[str]) -> list[str]:
        matches: set[str] = set()

        def walk(current_id: str, active: set[str]) -> None:
            if current_id in active:
                raise ProvenanceError("Ambiguous cycle encountered during trace.")
            next_active = {*active, current_id}
            for input_id in artifacts[current_id]["direct_input_artifact_ids"]:
                if artifacts[input_id]["artifact_type"] in allowed_types:
                    matches.add(input_id)
                walk(input_id, next_active)

        walk(start_id, set())
        return sorted(matches)

    selected_chain: dict[str, str] | None = None
    for metric_id in ancestors_of_type(figure_input_artifact_id, {"metric_table"}):
        for prediction_id in ancestors_of_type(metric_id, {"prediction", "baseline"}):
            for intermediate_id in ancestors_of_type(
                prediction_id, {"activation", "oracle_target"}
            ):
                model_inputs = ancestors_of_type(intermediate_id, {"model_input"})
                for model_input_id in model_inputs:
                    raw_inputs = ancestors_of_type(model_input_id, {"raw_trajectory"})
                    if raw_inputs:
                        selected_chain = {
                            "figure_input": figure_input_artifact_id,
                            "metric": metric_id,
                            "prediction_or_baseline": prediction_id,
                            "activation_or_oracle": intermediate_id,
                            "model_input": model_input_id,
                            "raw_trajectory": raw_inputs[0],
                        }
                        break
                if selected_chain is not None:
                    break
            if selected_chain is not None:
                break
        if selected_chain is not None:
            break
    if selected_chain is None:
        raise ProvenanceError(
            "Figure input does not contain the required Phase 1 metric lineage chain."
        )

    artifact_nodes = [copy.deepcopy(artifacts[item]) for item in sorted(visited)]
    creator_run_ids = sorted(
        {artifact["creator_run_id"] for artifact in artifact_nodes}
    )
    run_nodes = [copy.deepcopy(runs[run_id]) for run_id in creator_run_ids]
    raw_run = runs[artifacts[selected_chain["raw_trajectory"]]["creator_run_id"]]
    provenance = {
        "source_data_identity_hash": raw_run["data_identity_hash"],
        "checkpoint_hashes": sorted({run["checkpoint_hash"] for run in run_nodes}),
        "config_snapshot_hashes": sorted(
            {run["config_snapshot_hash"] for run in run_nodes}
        ),
        "code_shas": sorted({run["code_sha"] for run in run_nodes}),
        "seeds_by_run_id": {
            run["run_id"]: copy.deepcopy(run["seeds"])
            for run in sorted(run_nodes, key=lambda item: item["run_id"])
        },
        "preprocess_hashes": sorted({run["preprocess_hash"] for run in run_nodes}),
        "environment_hashes": sorted({run["environment_hash"] for run in run_nodes}),
    }
    trace = {
        "schema_version": registry["schema_version"],
        "lineage_trace_schema_version": PHASE1_LINEAGE_TRACE_SCHEMA_VERSION,
        "registry_id": registry["registry_id"],
        "subject_artifact_id": figure_input_artifact_id,
        "synthetic": registry["synthetic"],
        "scientific_use": registry["scientific_use"],
        "phase1_chain_artifact_ids": selected_chain,
        "artifact_nodes": artifact_nodes,
        "run_nodes": run_nodes,
        "direct_input_edges": [
            {"input_artifact_id": source, "output_artifact_id": target}
            for source, target in sorted(edges)
        ],
        "provenance": provenance,
    }
    trace["trace_hash"] = hash_json_value(trace)
    return trace


def append_registry_records(
    rollout_manifest: Mapping[str, Any],
    registry: Mapping[str, Any],
    *,
    runs: Sequence[Mapping[str, Any]] = (),
    artifacts: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Return a validated copy with new immutable records appended.

    The submitted registry is never mutated. The combined A/E validator is run
    both before and after appending so callers cannot build on invalid lineage.
    """

    if not isinstance(rollout_manifest, Mapping) or not isinstance(registry, Mapping):
        raise ProvenanceError("Manifest and registry must be mappings.")
    if not isinstance(runs, Sequence) or isinstance(runs, (str, bytes)):
        raise ProvenanceError("runs must be a sequence of mappings.")
    if not isinstance(artifacts, Sequence) or isinstance(artifacts, (str, bytes)):
        raise ProvenanceError("artifacts must be a sequence of mappings.")
    if any(not isinstance(record, Mapping) for record in (*runs, *artifacts)):
        raise ProvenanceError("All appended run and artifact records must be mappings.")

    _raise_for_invalid_bundle(rollout_manifest, registry)
    updated = copy.deepcopy(dict(registry))
    updated_runs = updated.get("runs")
    updated_artifacts = updated.get("artifacts")
    if not isinstance(updated_runs, list) or not isinstance(updated_artifacts, list):
        raise ProvenanceError("Validated registry unexpectedly lacks record lists.")
    updated_runs.extend(copy.deepcopy(dict(record)) for record in runs)
    updated_artifacts.extend(copy.deepcopy(dict(record)) for record in artifacts)
    _raise_for_invalid_bundle(rollout_manifest, updated)
    return updated


class RegistryIndex:
    """Read-only trace and artifact-index view of a validated A/E bundle."""

    def __init__(
        self,
        rollout_manifest: Mapping[str, Any],
        registry: Mapping[str, Any],
    ) -> None:
        if not isinstance(rollout_manifest, Mapping) or not isinstance(
            registry, Mapping
        ):
            raise ProvenanceError("Manifest and registry must be mappings.")
        _raise_for_invalid_bundle(rollout_manifest, registry)
        self._manifest = copy.deepcopy(dict(rollout_manifest))
        self._registry = copy.deepcopy(dict(registry))
        self._runs = {
            row["run_id"]: row
            for row in self._registry["runs"]
        }
        self._artifacts = {
            row["artifact_id"]: row
            for row in self._registry["artifacts"]
        }
        self._rollouts = {
            row["rollout_id"]: row
            for row in self._manifest["rollout_rows"]
        }
        self._rollout_references = self._index_rollout_references()
        self._artifact_index_cache: list[dict[str, Any]] | None = None

    def require_completed_run(
        self,
        run_id: str,
        *,
        owner: str,
        config_hash: str,
    ) -> dict[str, Any]:
        """Return one completed run with the expected owner/config identity."""

        if not isinstance(run_id, str) or not run_id.strip():
            raise ProvenanceError("run_id must be non-empty.")
        if not isinstance(owner, str) or not owner.strip():
            raise ProvenanceError("owner must be non-empty.")
        run = self._runs.get(run_id)
        if run is None:
            raise ProvenanceError(f"Unknown producer run {run_id!r}.")
        if run["owner"] != owner:
            raise ProvenanceError(f"Producer run {run_id!r} has the wrong owner.")
        if run["config_hash"] != config_hash:
            raise ProvenanceError(
                f"Producer run {run_id!r} has the wrong config hash."
            )
        if run["execution_status"] != "completed":
            raise ProvenanceError(f"Producer run {run_id!r} is not completed.")
        return copy.deepcopy(run)

    def _index_rollout_references(self) -> dict[str, list[dict[str, Any]]]:
        references: dict[str, list[dict[str, Any]]] = {
            artifact_id: [] for artifact_id in self._artifacts
        }
        artifact_fields = (
            "input_context_artifact_id",
            "intervention_request_artifact_id",
            "output_artifact_id",
        )
        for rollout_id in sorted(self._rollouts):
            rollout = self._rollouts[rollout_id]
            for field in artifact_fields:
                artifact_id = rollout.get(field)
                if artifact_id is None:
                    continue
                references[artifact_id].append(
                    {
                        "reference_field": field,
                        "rollout_id": rollout_id,
                        "event_id": rollout["event_id"],
                        "seed": rollout["seed"],
                        "rollout_status": rollout["status"],
                        "outcome": rollout["outcome"],
                        "measurable": rollout["measurable"],
                    }
                )
        return references

    def _assess_transitive_sources(
        self, artifact_id: str
    ) -> tuple[list[str], list[str]]:
        """Return invalid source IDs and dependency-cycle IDs below an artifact."""

        invalid_sources: set[str] = set()
        cycle_artifacts: set[str] = set()
        visited: set[str] = set()

        def visit(current_id: str, active: set[str]) -> None:
            if current_id in active:
                cycle_artifacts.add(current_id)
                return
            if current_id in visited:
                return
            next_active = {*active, current_id}
            artifact = self._artifacts[current_id]
            producer = self._runs[artifact["producer_run_id"]]
            for input_id in producer["input_artifact_ids"]:
                input_artifact = self._artifacts[input_id]
                input_run = self._runs[input_artifact["producer_run_id"]]
                if (
                    input_artifact["status"] != "accepted"
                    or input_run["execution_status"] == "failed"
                ):
                    invalid_sources.add(input_id)
                visit(input_id, next_active)
            visited.add(current_id)

        visit(artifact_id, set())
        return sorted(invalid_sources), sorted(cycle_artifacts)

    def artifact_index(self) -> list[dict[str, Any]]:
        """Return stable provenance, lifecycle, and claim-readiness for artifacts."""

        if self._artifact_index_cache is not None:
            return copy.deepcopy(self._artifact_index_cache)
        rows: list[dict[str, Any]] = []
        for artifact_id in sorted(self._artifacts):
            artifact = self._artifacts[artifact_id]
            run = self._runs[artifact["producer_run_id"]]
            invalid_sources, cycle_artifacts = self._assess_transitive_sources(
                artifact_id
            )
            is_current = artifact["status"] == "accepted"
            claim_eligibility_reasons: list[str] = []
            if not is_current:
                claim_eligibility_reasons.append("artifact_not_accepted")
            if run["execution_status"] == "failed":
                claim_eligibility_reasons.append("producer_run_failed")
            if invalid_sources:
                claim_eligibility_reasons.append("transitive_invalid_source")
            if cycle_artifacts:
                claim_eligibility_reasons.append("artifact_dependency_cycle")
            rollout_references = copy.deepcopy(
                self._rollout_references[artifact_id]
            )
            rows.append(
                {
                    "artifact_id": artifact_id,
                    "artifact_type": artifact["artifact_type"],
                    "artifact_uri": artifact["uri"],
                    "artifact_status": artifact["status"],
                    "exclusion_reason": artifact["exclusion_reason"],
                    "superseded_by": artifact["superseded_by"],
                    "artifact_sha256": artifact["sha256"],
                    "producer_run_id": run["run_id"],
                    "run_command": list(run["command"]),
                    "run_owner": run["owner"],
                    "parent_run_id": run["parent_run_id"],
                    "run_execution_status": run["execution_status"],
                    "run_failure_reason": run["failure_reason"],
                    "code_sha": run["code_sha"],
                    "config_hash": run["config_hash"],
                    "model_hash": run["model_hash"],
                    "preprocess_hash": run["preprocess_hash"],
                    "direct_input_artifact_ids": list(run["input_artifact_ids"]),
                    "direct_output_artifact_ids": list(run["output_artifact_ids"]),
                    "referenced_by_rollout_ids": sorted(
                        {reference["rollout_id"] for reference in rollout_references}
                    ),
                    "rollout_references": rollout_references,
                    "is_current": is_current,
                    "claim_eligible": not claim_eligibility_reasons,
                    "claim_eligibility_reasons": claim_eligibility_reasons,
                    "transitive_invalid_source": bool(invalid_sources),
                    "invalid_source_artifact_ids": invalid_sources,
                    "artifact_dependency_cycle_ids": cycle_artifacts,
                }
            )
        self._artifact_index_cache = rows
        return copy.deepcopy(rows)

    def provenance_qa_report(self) -> dict[str, Any]:
        """Summarize lifecycle and flag artifacts unsafe for scientific claims."""

        rows = self.artifact_index()
        lifecycle_counts = Counter(row["artifact_status"] for row in rows)
        run_status_counts = Counter(
            run["execution_status"] for run in self._runs.values()
        )
        current_rows = [row for row in rows if row["is_current"]]
        eligible_rows = [row for row in rows if row["claim_eligible"]]
        transitive_invalid_rows = [
            row for row in rows if row["transitive_invalid_source"]
        ]
        cycle_rows = [
            row for row in rows if row["artifact_dependency_cycle_ids"]
        ]
        return {
            "provenance_qa_schema_version": "person-e-provenance-qa-v0.1",
            "schema_version": self._manifest["schema_version"],
            "manifest_id": self._manifest["manifest_id"],
            "registry_id": self._registry["registry_id"],
            "summary": {
                "artifact_count": len(rows),
                "run_count": len(self._runs),
                "rollout_count": len(self._rollouts),
                "lifecycle_counts": {
                    status: lifecycle_counts.get(status, 0)
                    for status in ("accepted", "excluded", "superseded")
                },
                "run_execution_status_counts": {
                    status: run_status_counts.get(status, 0)
                    for status in ("completed", "completed_with_failures", "failed")
                },
                "current_artifact_count": len(current_rows),
                "non_current_artifact_count": len(rows) - len(current_rows),
                "claim_eligible_artifact_count": len(eligible_rows),
                "claim_ineligible_artifact_count": len(rows) - len(eligible_rows),
                "transitive_invalid_source_artifact_count": len(
                    transitive_invalid_rows
                ),
                "artifact_dependency_cycle_count": len(cycle_rows),
            },
            "current_claim_ineligible_artifact_ids": [
                row["artifact_id"]
                for row in current_rows
                if not row["claim_eligible"]
            ],
            "transitive_invalid_source_artifact_ids": [
                row["artifact_id"] for row in transitive_invalid_rows
            ],
            "artifact_assessments": [
                {
                    "artifact_id": row["artifact_id"],
                    "artifact_type": row["artifact_type"],
                    "artifact_status": row["artifact_status"],
                    "is_current": row["is_current"],
                    "claim_eligible": row["claim_eligible"],
                    "claim_eligibility_reasons": row[
                        "claim_eligibility_reasons"
                    ],
                    "invalid_source_artifact_ids": row[
                        "invalid_source_artifact_ids"
                    ],
                    "artifact_dependency_cycle_ids": row[
                        "artifact_dependency_cycle_ids"
                    ],
                }
                for row in rows
            ],
        }

    def _parent_run_chain(self, run_id: str) -> list[dict[str, Any]]:
        chain: list[dict[str, Any]] = []
        current_id: str | None = run_id
        seen: set[str] = set()
        while current_id is not None:
            if current_id in seen:
                raise ProvenanceError(
                    f"Parent-run cycle encountered at {current_id!r}."
                )
            seen.add(current_id)
            run = self._runs.get(current_id)
            if run is None:
                raise ProvenanceError(f"Unknown parent run {current_id!r}.")
            chain.append(copy.deepcopy(run))
            current_id = run["parent_run_id"]
        return chain

    def trace_artifact(self, artifact_id: str) -> dict[str, Any]:
        """Trace an artifact recursively through producing-run direct inputs."""

        if not isinstance(artifact_id, str) or not artifact_id:
            raise ProvenanceError("artifact_id must be a non-empty string.")
        return self._trace_artifact(artifact_id, active=set())

    def _trace_artifact(
        self, artifact_id: str, *, active: set[str]
    ) -> dict[str, Any]:
        artifact = self._artifacts.get(artifact_id)
        if artifact is None:
            raise ProvenanceError(f"Unknown artifact_id {artifact_id!r}.")
        if artifact_id in active:
            raise ProvenanceError(
                f"Artifact dependency cycle encountered at {artifact_id!r}."
            )
        run = self._runs[artifact["producer_run_id"]]
        next_active = {*active, artifact_id}
        return {
            "artifact": copy.deepcopy(artifact),
            "producer_run": copy.deepcopy(run),
            "producer_to_root_run_chain": self._parent_run_chain(run["run_id"]),
            "direct_inputs": [
                self._trace_artifact(input_id, active=next_active)
                for input_id in run["input_artifact_ids"]
            ],
        }

    def trace_rollout(self, rollout_id: str) -> dict[str, Any]:
        """Trace a rollout row and every referenced input/output artifact."""

        if not isinstance(rollout_id, str) or not rollout_id:
            raise ProvenanceError("rollout_id must be a non-empty string.")
        rollout = self._rollouts.get(rollout_id)
        if rollout is None:
            raise ProvenanceError(f"Unknown rollout_id {rollout_id!r}.")
        traces: dict[str, Any] = {}
        for field in (
            "input_context_artifact_id",
            "intervention_request_artifact_id",
            "output_artifact_id",
        ):
            artifact_id = rollout.get(field)
            traces[field] = (
                None if artifact_id is None else self.trace_artifact(artifact_id)
            )
        return {
            "rollout": copy.deepcopy(rollout),
            "referenced_artifacts": traces,
        }

    def provenance_report(
        self,
        subject_id: str,
        *,
        subject_type: str | None = None,
    ) -> dict[str, Any]:
        """Trace a rollout or artifact without using path/name heuristics."""

        if not isinstance(subject_id, str) or not subject_id:
            raise ProvenanceError("subject_id must be a non-empty string.")
        if subject_type not in {None, "rollout", "artifact"}:
            raise ProvenanceError("subject_type must be 'rollout' or 'artifact'.")
        is_rollout = subject_id in self._rollouts
        is_artifact = subject_id in self._artifacts
        if subject_type is None:
            if is_rollout and is_artifact:
                raise ProvenanceError(
                    f"{subject_id!r} is both a rollout_id and artifact_id; "
                    "provide subject_type explicitly."
                )
            if is_rollout:
                subject_type = "rollout"
            elif is_artifact:
                subject_type = "artifact"
            else:
                raise ProvenanceError(
                    f"{subject_id!r} is not a rollout_id or artifact_id."
                )
        if subject_type == "rollout":
            if not is_rollout:
                raise ProvenanceError(f"Unknown rollout_id {subject_id!r}.")
            trace = self.trace_rollout(subject_id)
        else:
            if not is_artifact:
                raise ProvenanceError(f"Unknown artifact_id {subject_id!r}.")
            trace = self.trace_artifact(subject_id)
        return {
            "schema_version": self._manifest["schema_version"],
            "manifest_id": self._manifest["manifest_id"],
            "registry_id": self._registry["registry_id"],
            "subject_id": subject_id,
            "subject_type": subject_type,
            "trace": trace,
        }
