"""Immutable run/artifact lineage for the integrated MVP (Steps 7.4 and 7.7).

Person E owns the immutable run/artifact registry schema. This module builds
records in that exact shape so the ledger Person A produces is directly
consumable, without defining a competing registry.

Every queued task and produced artifact gets an immutable run identity carrying
its direct inputs, command, config/code/model/data hashes, seeds, status, logs,
outputs, checksums, parent/superseded references, and owner. A filename is never
scientific identity.

Step 7.7 archives the exact command, config snapshot, hashes, exclusions, folds,
logs, and output paths used when Person B's and Person D's frozen entry points
are invoked. Person A records the invocation; it never computes their metrics.
"""

from __future__ import annotations

import copy
import hashlib
import shlex
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from mineocclude.contracts.identity import SCHEMA_VERSION
from mineocclude.contracts.rollout_registry import (
    IMMUTABLE_ARTIFACT_TYPES,
    IMMUTABLE_REGISTRY_SCHEMA_VERSION,
    validate_immutable_run_artifact_registry,
)

LINEAGE_SCHEMA_VERSION = "person-a-mvp-lineage-v0.1"
ANALYSIS_INVOCATION_SCHEMA_VERSION = "person-a-u1-u3-invocation-v0.1"
ARTIFACT_SCHEMA_VERSION = "person-a-mvp-artifact-v0.1"

_ID_PREFIX = "mineocclude"

# Person E's run statuses. There is no "superseded" run status: supersession is
# expressed by the superseding run naming its target.
RUN_STATUS_IN_PROGRESS = "in_progress"
RUN_STATUS_COMPLETED = "completed"
RUN_STATUS_FAILED = "failed"


class LineageErrorCode(str, Enum):
    """Stable reasons a lineage record cannot be created or trusted."""

    INVALID_REQUEST = "invalid_request"
    DUPLICATE_RUN = "duplicate_run"
    DUPLICATE_ARTIFACT = "duplicate_artifact"
    UNKNOWN_RUN = "unknown_run"
    UNKNOWN_ARTIFACT = "unknown_artifact"
    FILENAME_AS_IDENTITY = "filename_as_identity"
    UNKNOWN_ARTIFACT_TYPE = "unknown_artifact_type"
    REGISTRY_REJECTED = "registry_rejected"
    RETRY_WITHOUT_PARENT = "retry_without_parent"
    ILLEGAL_SUPERSESSION = "illegal_supersession"


class LineageError(ValueError):
    """Raised when run or artifact lineage would become untraceable."""

    def __init__(self, code: LineageErrorCode, message: str) -> None:
        self.code = code
        super().__init__(f"{code.value}: {message}")


def _fail(code: LineageErrorCode, message: str) -> None:
    raise LineageError(code, message)


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _digest(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def make_run_id(
    *,
    stage_id: str,
    config_hash: str,
    code_sha: str,
    seed: int,
    attempt: int = 1,
) -> str:
    """Derive an immutable run identity from what actually determines a run."""

    return (
        f"{_ID_PREFIX}-run-"
        + _digest(stage_id, config_hash, code_sha, str(seed), str(attempt))[:32]
    )


def make_artifact_id(
    *,
    artifact_type: str,
    run_id: str,
    sha256: str,
) -> str:
    """Derive an artifact identity from its producing run and its content."""

    return f"{_ID_PREFIX}-artifact-" + _digest(artifact_type, run_id, sha256)[:32]


@dataclass(frozen=True)
class RunIdentity:
    """The hash set that makes one execution distinguishable from another."""

    code_sha: str
    git_dirty: bool
    config_snapshot_hash: str
    checkpoint_hash: str
    data_identity_hash: str
    preprocess_hash: str
    environment_hash: str
    seeds: Mapping[str, int]

    def to_document(self) -> dict[str, Any]:
        return {
            "code_sha": self.code_sha,
            "git_dirty": self.git_dirty,
            "config_snapshot_hash": self.config_snapshot_hash,
            "checkpoint_hash": self.checkpoint_hash,
            "data_identity_hash": self.data_identity_hash,
            "preprocess_hash": self.preprocess_hash,
            "environment_hash": self.environment_hash,
            "seeds": dict(sorted(self.seeds.items())),
        }


@dataclass(frozen=True)
class ArtifactRecord:
    """One produced artifact bound to content, not to a path."""

    artifact_id: str
    artifact_type: str
    creator_run_id: str
    sha256: str
    uri: str
    size_bytes: int
    status: str = "accepted"
    status_authority: str = "person_a_model"
    status_reason: str | None = None
    superseded_by: str | None = None
    direct_input_artifact_ids: tuple[str, ...] = ()

    def to_registry_record(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
            "artifact_id": self.artifact_id,
            "direct_input_artifact_ids": list(self.direct_input_artifact_ids),
            "creator_run_id": self.creator_run_id,
            "artifact_type": self.artifact_type,
            "uri": self.uri,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
            "status": self.status,
            "status_authority": self.status_authority,
            "status_reason": self.status_reason,
            "superseded_by": self.superseded_by,
        }


@dataclass(frozen=True)
class RunRecord:
    """One immutable execution identity, retained even when it failed."""

    run_id: str
    stage_id: str
    owner: str
    status: str
    command: tuple[str, ...]
    identity: RunIdentity
    started_at: str
    ended_at: str | None = None
    input_artifact_ids: tuple[str, ...] = ()
    output_artifact_ids: tuple[str, ...] = ()
    log_uris: tuple[str, ...] = ()
    parent_run_id: str | None = None
    supersedes_run_id: str | None = None
    supersession_reason: str | None = None
    failure_reason: str | None = None
    attempt: int = 1

    @property
    def command_line(self) -> str:
        return " ".join(shlex.quote(part) for part in self.command)

    def to_registry_record(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "run_id": self.run_id,
            "owner": self.owner,
            "status": self.status,
            "command": list(self.command),
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "input_artifact_ids": list(self.input_artifact_ids),
            "output_artifact_ids": list(self.output_artifact_ids),
            "parent_run_id": self.parent_run_id,
            "supersedes_run_id": self.supersedes_run_id,
            "supersession_reason": self.supersession_reason,
            "failure_reason": self.failure_reason,
            **self.identity.to_document(),
        }

    def to_document(self) -> dict[str, Any]:
        """Person A's own view, which additionally records the stage and attempt."""

        return {
            **self.to_registry_record(),
            "stage_id": self.stage_id,
            "attempt": self.attempt,
            "is_retry_of_parent": self.parent_run_id is not None,
            "command_line": self.command_line,
            "log_uris": list(self.log_uris),
        }


@dataclass
class MvpLineage:
    """An append-only run/artifact ledger for one integrated MVP execution."""

    registry_id: str
    synthetic: bool = False
    runs: dict[str, RunRecord] = field(default_factory=dict)
    artifacts: dict[str, ArtifactRecord] = field(default_factory=dict)

    @property
    def scientific_use(self) -> str:
        return "forbidden" if self.synthetic else "permitted"

    # -- append-only writes ---------------------------------------------

    def register_run(self, record: RunRecord) -> RunRecord:
        if record.run_id in self.runs:
            _fail(
                LineageErrorCode.DUPLICATE_RUN,
                f"run {record.run_id!r} is already registered",
            )
        if record.parent_run_id is not None and record.parent_run_id not in self.runs:
            _fail(
                LineageErrorCode.UNKNOWN_RUN,
                f"parent run {record.parent_run_id!r} is not registered",
            )
        if record.attempt > 1 and record.parent_run_id is None:
            _fail(
                LineageErrorCode.RETRY_WITHOUT_PARENT,
                "a retry must name the run it retries so it is not read as new",
            )
        for artifact_id in record.input_artifact_ids:
            if artifact_id not in self.artifacts:
                _fail(
                    LineageErrorCode.UNKNOWN_ARTIFACT,
                    f"direct input artifact {artifact_id!r} is not registered",
                )
        self.runs[record.run_id] = record
        return record

    def register_artifact(self, record: ArtifactRecord) -> ArtifactRecord:
        if record.artifact_id in self.artifacts:
            _fail(
                LineageErrorCode.DUPLICATE_ARTIFACT,
                f"artifact {record.artifact_id!r} is already registered",
            )
        if record.creator_run_id not in self.runs:
            _fail(
                LineageErrorCode.UNKNOWN_RUN,
                f"artifact names unregistered run {record.creator_run_id!r}",
            )
        if record.artifact_type not in IMMUTABLE_ARTIFACT_TYPES:
            _fail(
                LineageErrorCode.UNKNOWN_ARTIFACT_TYPE,
                f"artifact type {record.artifact_type!r} is outside the "
                "closed registry catalog",
            )
        if "/" not in record.uri and ":" not in record.uri:
            _fail(
                LineageErrorCode.FILENAME_AS_IDENTITY,
                "an artifact URI must locate content, not be a bare filename",
            )
        self.artifacts[record.artifact_id] = record
        run = self.runs[record.creator_run_id]
        if record.artifact_id not in run.output_artifact_ids:
            self.runs[run.run_id] = replace(
                run,
                output_artifact_ids=(*run.output_artifact_ids, record.artifact_id),
            )
        return record

    def complete_run(
        self,
        run_id: str,
        *,
        ended_at: str | None = None,
        log_uris: Sequence[str] = (),
    ) -> RunRecord:
        run = self._require_run(run_id)
        updated = replace(
            run,
            status=RUN_STATUS_COMPLETED,
            ended_at=ended_at or utc_now(),
            failure_reason=None,
            log_uris=tuple(log_uris) or run.log_uris,
        )
        self.runs[run_id] = updated
        return updated

    def fail_run(
        self,
        run_id: str,
        *,
        failure_reason: str,
        ended_at: str | None = None,
        log_uris: Sequence[str] = (),
    ) -> RunRecord:
        if not failure_reason:
            _fail(
                LineageErrorCode.INVALID_REQUEST,
                "a failed run requires an explicit failure_reason",
            )
        run = self._require_run(run_id)
        updated = replace(
            run,
            status=RUN_STATUS_FAILED,
            ended_at=ended_at or utc_now(),
            failure_reason=failure_reason,
            log_uris=tuple(log_uris) or run.log_uris,
        )
        self.runs[run_id] = updated
        return updated

    def supersede_run(
        self,
        superseded_run_id: str,
        *,
        by_run_id: str,
        reason: str,
    ) -> None:
        """Record supersession without deleting the superseded run's history."""

        old = self._require_run(superseded_run_id)
        new = self._require_run(by_run_id)
        if old.run_id == new.run_id:
            _fail(
                LineageErrorCode.ILLEGAL_SUPERSESSION,
                "a run cannot supersede itself",
            )
        if old.status != RUN_STATUS_COMPLETED:
            _fail(
                LineageErrorCode.ILLEGAL_SUPERSESSION,
                "only a completed run may be superseded",
            )
        if old.owner != new.owner:
            _fail(
                LineageErrorCode.ILLEGAL_SUPERSESSION,
                "supersession may not cross role ownership",
            )
        if not reason:
            _fail(
                LineageErrorCode.ILLEGAL_SUPERSESSION,
                "supersession requires an explicit reason",
            )
        self.runs[by_run_id] = replace(
            new,
            supersedes_run_id=superseded_run_id,
            supersession_reason=reason,
        )
        replacement_by_type = {
            artifact.artifact_type: artifact.artifact_id
            for artifact in self.artifacts.values()
            if artifact.creator_run_id == by_run_id
        }
        for artifact_id, artifact in list(self.artifacts.items()):
            if artifact.creator_run_id != superseded_run_id:
                continue
            replacement = replacement_by_type.get(artifact.artifact_type)
            if replacement is None:
                _fail(
                    LineageErrorCode.ILLEGAL_SUPERSESSION,
                    f"no replacement artifact of type {artifact.artifact_type!r} "
                    f"was produced by {by_run_id!r}",
                )
            self.artifacts[artifact_id] = replace(
                artifact,
                status="superseded",
                status_reason=reason,
                superseded_by=replacement,
            )

    # -- reads -----------------------------------------------------------

    def _require_run(self, run_id: str) -> RunRecord:
        run = self.runs.get(run_id)
        if run is None:
            _fail(LineageErrorCode.UNKNOWN_RUN, f"run {run_id!r} is not registered")
        return run  # type: ignore[return-value]

    def trace(self, artifact_id: str) -> dict[str, Any]:
        """Trace a displayed output back to its direct inputs and execution."""

        artifact = self.artifacts.get(artifact_id)
        if artifact is None:
            _fail(
                LineageErrorCode.UNKNOWN_ARTIFACT,
                f"artifact {artifact_id!r} is not registered",
            )
        assert artifact is not None
        run = self._require_run(artifact.creator_run_id)
        chain: list[dict[str, Any]] = []
        cursor: str | None = run.run_id
        seen: set[str] = set()
        while cursor is not None and cursor not in seen:
            seen.add(cursor)
            record = self.runs[cursor]
            chain.append(record.to_document())
            cursor = record.parent_run_id
        return {
            "artifact": artifact.to_registry_record(),
            "producing_run": run.to_document(),
            "direct_input_artifacts": [
                self.artifacts[a].to_registry_record()
                for a in run.input_artifact_ids
                if a in self.artifacts
            ],
            "run_chain": chain,
            "traceable_without_filename": True,
        }

    def to_document(self) -> dict[str, Any]:
        return {
            "schema_version": LINEAGE_SCHEMA_VERSION,
            "step": "7.4",
            "registry_id": self.registry_id,
            "synthetic": self.synthetic,
            "scientific_use": self.scientific_use,
            "run_count": len(self.runs),
            "artifact_count": len(self.artifacts),
            "run_status_counts": _status_counts(self.runs.values()),
            "artifact_status_counts": _status_counts(self.artifacts.values()),
            "runs": [self.runs[k].to_document() for k in sorted(self.runs)],
            "artifacts": [
                self.artifacts[k].to_registry_record() for k in sorted(self.artifacts)
            ],
            "failed_and_superseded_records_retained": True,
        }

    def to_immutable_registry(self) -> dict[str, Any]:
        """Project the ledger onto Person E's frozen immutable-registry schema."""

        return {
            "schema_version": SCHEMA_VERSION,
            "immutable_registry_schema_version": IMMUTABLE_REGISTRY_SCHEMA_VERSION,
            "registry_id": self.registry_id,
            "synthetic": self.synthetic,
            "scientific_use": self.scientific_use,
            "runs": [
                self.runs[k].to_registry_record() for k in sorted(self.runs)
            ],
            "artifacts": [
                self.artifacts[k].to_registry_record() for k in sorted(self.artifacts)
            ],
        }

    def validate_against_person_e_schema(
        self,
        *,
        previous_registry: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Report whether Person E's validator accepts this projection."""

        projection = self.to_immutable_registry()
        result = validate_immutable_run_artifact_registry(
            projection,
            previous_registry=copy.deepcopy(dict(previous_registry))
            if previous_registry is not None
            else None,
        )
        return {
            "accepted": bool(result.accepted),
            "rejections": [
                {
                    "code": getattr(rejection.code, "value", str(rejection.code)),
                    "message": rejection.message,
                }
                for rejection in result.rejections
            ],
            "registry_id": projection["registry_id"],
            "run_count": len(projection["runs"]),
            "artifact_count": len(projection["artifacts"]),
        }

    def require_person_e_acceptance(self) -> dict[str, Any]:
        """Raise unless Person E's validator accepts this ledger unchanged."""

        report = self.validate_against_person_e_schema()
        if not report["accepted"]:
            details = "; ".join(
                f"{item['code']}: {item['message']}" for item in report["rejections"]
            )
            _fail(
                LineageErrorCode.REGISTRY_REJECTED,
                f"Person E's registry validator rejected the ledger: {details}",
            )
        return report


def _status_counts(records: Any) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        counts[record.status] = counts.get(record.status, 0) + 1
    return dict(sorted(counts.items()))


# ---------------------------------------------------------------------------
# Step 7.7 — integrated U1-U3 invocation record
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AnalysisEntryPoint:
    """One teammate-owned entry point Person A may invoke but not reimplement."""

    owner: str
    entry_point: str
    command: tuple[str, ...]
    frozen_config_path: str
    frozen_config_sha256: str

    def to_document(self) -> dict[str, Any]:
        return {
            "owner": self.owner,
            "entry_point": self.entry_point,
            "command": list(self.command),
            "command_line": " ".join(shlex.quote(p) for p in self.command),
            "frozen_config_path": self.frozen_config_path,
            "frozen_config_sha256": self.frozen_config_sha256,
        }


def build_u1_u3_invocation_record(
    *,
    run_id: str,
    identity: Mapping[str, Any],
    entry_points: Sequence[AnalysisEntryPoint],
    accepted_manifest_sha256: str,
    activation_index_sha256: str | None,
    fold_manifest_sha256: str,
    fold_count: int,
    accepted_row_count: int | None,
    exclusion_count: int,
    log_uris: Sequence[str],
    output_paths: Sequence[str],
    executed: bool,
    blocked_reason: str | None = None,
) -> dict[str, Any]:
    """Archive exactly what was invoked, with what inputs, and what it produced.

    Metrics are not interpreted here. The record states whether the invocation
    actually ran; when it did not, it names the blocking input rather than
    implying a result.
    """

    if not entry_points:
        _fail(
            LineageErrorCode.INVALID_REQUEST,
            "an invocation record requires at least one entry point",
        )
    if not executed and not blocked_reason:
        _fail(
            LineageErrorCode.INVALID_REQUEST,
            "an unexecuted invocation must name its blocking reason",
        )
    if executed and activation_index_sha256 is None:
        _fail(
            LineageErrorCode.INVALID_REQUEST,
            "an executed invocation must name the activation index it consumed",
        )
    return {
        "schema_version": ANALYSIS_INVOCATION_SCHEMA_VERSION,
        "step": "7.7",
        "run_id": run_id,
        "executed": bool(executed),
        "status": "EXECUTED" if executed else "BLOCKED",
        "blocked_reason": blocked_reason,
        "identity": dict(identity),
        "entry_points": [entry.to_document() for entry in entry_points],
        "inputs": {
            "accepted_manifest_sha256": accepted_manifest_sha256,
            "activation_index_sha256": activation_index_sha256,
            "fold_manifest_sha256": fold_manifest_sha256,
            "fold_count": fold_count,
            "accepted_row_count": accepted_row_count,
            "exclusion_count": exclusion_count,
        },
        "logs": list(log_uris),
        "output_paths": list(output_paths),
        "metrics_interpreted_by_person_a": False,
        "interpretation_gate": (
            "Metrics are not interpreted until the model, alignment, oracle, "
            "positive/negative control, and reproducibility gates are known."
        ),
        "regenerable_by_owning_role": True,
    }


__all__ = [
    "ANALYSIS_INVOCATION_SCHEMA_VERSION",
    "ARTIFACT_SCHEMA_VERSION",
    "LINEAGE_SCHEMA_VERSION",
    "RUN_STATUS_COMPLETED",
    "RUN_STATUS_FAILED",
    "RUN_STATUS_IN_PROGRESS",
    "AnalysisEntryPoint",
    "ArtifactRecord",
    "LineageError",
    "LineageErrorCode",
    "MvpLineage",
    "RunIdentity",
    "RunRecord",
    "build_u1_u3_invocation_record",
    "make_artifact_id",
    "make_run_id",
    "utc_now",
]
