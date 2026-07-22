"""Immutable provenance operations over the frozen A-to-E registry contract.

This module deliberately does not broaden schema v1.0 artifact types or add
run-supersession fields. Those roadmap gaps require an approved migration.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import tempfile
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from mineocclude.contracts.rollout_registry import (
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
