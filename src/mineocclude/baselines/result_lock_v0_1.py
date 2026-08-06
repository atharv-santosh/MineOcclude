"""Versioned result-lock package (Person D Step 6.5).

Execution manual Step 6.5 requires a versioned result-lock package
recording source prediction run IDs, metric run IDs, the accepted
manifest hash, the fold hash, code and configuration hashes, row counts,
exclusions and missingness, comparison labels, affected downstream
figures and tables, supersession relationships, checksums, and
acknowledgement slots for Persons A, B, and E.

The rule that gives the lock its value: **a correction supersedes, it
never overwrites.** :func:`supersede_result_lock` returns a *new* lock
whose ``supersedes`` field names the old one and leaves the old document
byte-identical. There is deliberately no function here that edits a lock
in place, and the validator rejects a successor that reuses its
predecessor's version or omits the supersession link or reason.

Publishing a lock over real results additionally requires
``evidence_kind='real'`` plus non-null result identities; a synthetic
lock can be built and validated freely but can never claim to be real
locked facts.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Sequence

SCHEMA_ID = "person-d-result-lock-v0-1"
SCHEMA_VERSION = "1.0"

#: Acknowledgement slots. A lock is *published* once it exists; it is
#: *acknowledged* only when the named role signs it. The two are separate
#: so an unacknowledged lock can never be presented as agreed.
ACKNOWLEDGEMENT_ROLES: tuple[str, ...] = ("person_a", "person_b", "person_e")

ACKNOWLEDGEMENT_STATUSES: tuple[str, ...] = ("pending", "acknowledged", "rejected")

LOCK_STATUSES: tuple[str, ...] = ("draft", "locked", "superseded")


class ResultLockError(ValueError):
    """Raised when a result lock cannot be built or validated honestly."""


@dataclass(frozen=True)
class LockedArtifact:
    """One artifact whose bytes this lock pins."""

    artifact_id: str
    path: str
    sha256: str
    byte_size: int
    owner_role: str

    def __post_init__(self) -> None:
        if len(self.sha256) != 64:
            raise ResultLockError(
                f"artifact {self.artifact_id!r} sha256 is not a SHA-256 digest"
            )
        if self.byte_size < 0:
            raise ResultLockError(f"artifact {self.artifact_id!r} has negative byte_size")


@dataclass(frozen=True)
class DownstreamImpact:
    """One figure/table this lock's facts feed, and who owns it."""

    artifact_id: str
    kind: str
    owner_role: str


@dataclass(frozen=True)
class ResultFacts:
    """The countable facts a lock freezes.

    Every count is stated explicitly, including the zeroes: a lock that
    silently omits its exclusion and missingness counts cannot be
    distinguished later from one that had none.
    """

    prediction_row_count: int
    scored_row_count: int
    non_applicable_row_count: int
    missing_row_count: int
    excluded_trajectory_count: int
    accepted_trajectory_count: int
    comparison_labels: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        partition = (
            self.scored_row_count
            + self.non_applicable_row_count
            + self.missing_row_count
        )
        if partition != self.prediction_row_count:
            raise ResultLockError(
                "scored + non_applicable + missing must equal prediction_row_count "
                f"({partition} != {self.prediction_row_count})"
            )
        for name, value in (
            ("prediction_row_count", self.prediction_row_count),
            ("excluded_trajectory_count", self.excluded_trajectory_count),
            ("accepted_trajectory_count", self.accepted_trajectory_count),
        ):
            if value < 0:
                raise ResultLockError(f"{name} must not be negative")


def build_result_lock(
    *,
    lock_id: str,
    lock_version: str,
    prediction_run_ids: Sequence[str],
    metric_run_ids: Sequence[str],
    accepted_manifest_sha256: Optional[str],
    fold_manifest_sha256: Optional[str],
    code_sha256: str,
    config_sha256: str,
    facts: ResultFacts,
    locked_artifacts: Sequence[LockedArtifact] = (),
    downstream: Sequence[DownstreamImpact] = (),
    supersedes: Optional[str] = None,
    supersession_reason: Optional[str] = None,
    evidence_kind: str = "synthetic",
    status: str = "locked",
) -> dict[str, Any]:
    """Build one versioned, immutable result-lock document."""

    if evidence_kind not in ("real", "synthetic"):
        raise ResultLockError("evidence_kind must be 'real' or 'synthetic'")
    if status not in LOCK_STATUSES:
        raise ResultLockError(f"unknown lock status {status!r}")
    if supersedes and not supersession_reason:
        raise ResultLockError(
            f"lock {lock_id!r} supersedes {supersedes!r} but records no reason; "
            "a correction must say what was wrong with what it replaces"
        )
    if supersession_reason and not supersedes:
        raise ResultLockError(
            f"lock {lock_id!r} records a supersession reason but names no "
            "predecessor"
        )
    if evidence_kind == "real":
        for name, value in (
            ("accepted_manifest_sha256", accepted_manifest_sha256),
            ("fold_manifest_sha256", fold_manifest_sha256),
        ):
            if not value:
                raise ResultLockError(
                    f"a real result lock requires {name}; real locked facts "
                    "cannot be published without the identity of the inputs "
                    "they were computed from"
                )
        if not prediction_run_ids or not metric_run_ids:
            raise ResultLockError(
                "a real result lock requires at least one prediction run ID and "
                "one metric run ID"
            )

    document: dict[str, Any] = {
        "schema_id": SCHEMA_ID,
        "schema_version": SCHEMA_VERSION,
        "producer_role": "person_d",
        "lock_id": lock_id,
        "lock_version": lock_version,
        "status": status,
        "evidence_kind": evidence_kind,
        "supersedes": supersedes,
        "supersession_reason": supersession_reason,
        "prediction_run_ids": tuple(sorted(set(prediction_run_ids))),
        "metric_run_ids": tuple(sorted(set(metric_run_ids))),
        "accepted_manifest_sha256": accepted_manifest_sha256,
        "fold_manifest_sha256": fold_manifest_sha256,
        "code_sha256": code_sha256,
        "config_sha256": config_sha256,
        "facts": {
            "prediction_row_count": facts.prediction_row_count,
            "scored_row_count": facts.scored_row_count,
            "non_applicable_row_count": facts.non_applicable_row_count,
            "missing_row_count": facts.missing_row_count,
            "excluded_trajectory_count": facts.excluded_trajectory_count,
            "accepted_trajectory_count": facts.accepted_trajectory_count,
            "comparison_labels": list(facts.comparison_labels),
        },
        "locked_artifacts": tuple(
            {
                "artifact_id": artifact.artifact_id,
                "path": artifact.path,
                "sha256": artifact.sha256,
                "byte_size": artifact.byte_size,
                "owner_role": artifact.owner_role,
            }
            for artifact in sorted(locked_artifacts, key=lambda a: a.artifact_id)
        ),
        "affected_downstream": tuple(
            {
                "artifact_id": item.artifact_id,
                "kind": item.kind,
                "owner_role": item.owner_role,
            }
            for item in sorted(downstream, key=lambda i: i.artifact_id)
        ),
        "acknowledgements": {
            role: {"status": "pending", "commit": None, "note": None}
            for role in ACKNOWLEDGEMENT_ROLES
        },
    }
    document["lock_checksum"] = compute_lock_checksum(document)
    return document


def compute_lock_checksum(document: Mapping[str, Any]) -> str:
    """Checksum the lock's content, excluding the checksum and signatures.

    Acknowledgements are excluded deliberately: a role signing a lock must
    not change the identity of the facts it signed.
    """

    payload = {
        key: value
        for key, value in document.items()
        if key not in ("lock_checksum", "acknowledgements")
    }
    encoded = json.dumps(payload, sort_keys=True, default=_json_default).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def acknowledge_result_lock(
    document: Mapping[str, Any],
    *,
    role: str,
    status: str,
    commit: Optional[str] = None,
    note: Optional[str] = None,
) -> dict[str, Any]:
    """Return a copy of the lock with one role's acknowledgement recorded.

    The facts themselves are untouched, so ``lock_checksum`` is unchanged
    and a signature can never be mistaken for a revision of the result.
    """

    if role not in ACKNOWLEDGEMENT_ROLES:
        raise ResultLockError(f"unknown acknowledgement role {role!r}")
    if status not in ACKNOWLEDGEMENT_STATUSES:
        raise ResultLockError(f"unknown acknowledgement status {status!r}")
    if status == "rejected" and not note:
        raise ResultLockError(
            f"{role} rejected the lock without a note; a rejection must say why"
        )

    updated = dict(document)
    acknowledgements = {
        key: dict(value) for key, value in document["acknowledgements"].items()
    }
    acknowledgements[role] = {"status": status, "commit": commit, "note": note}
    updated["acknowledgements"] = acknowledgements
    return updated


def supersede_result_lock(
    previous: Mapping[str, Any],
    *,
    lock_id: str,
    lock_version: str,
    reason: str,
    **overrides: Any,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Create a successor lock, returning ``(retired_previous, successor)``.

    The previous lock is returned as a copy with ``status='superseded'``
    and a ``superseded_by`` pointer -- its facts, checksum, and
    acknowledgements are preserved exactly. Nothing is deleted, and the
    caller is expected to persist both documents.
    """

    if not reason:
        raise ResultLockError("a supersession must record a reason")
    if lock_version == previous["lock_version"]:
        raise ResultLockError(
            f"successor reuses version {lock_version!r}; a correction must be a "
            "new version, never a rewrite of the old one"
        )

    retired = dict(previous)
    retired["status"] = "superseded"
    retired["superseded_by"] = lock_id

    facts_source = overrides.pop("facts", None)
    if facts_source is None:
        facts_source = ResultFacts(
            prediction_row_count=previous["facts"]["prediction_row_count"],
            scored_row_count=previous["facts"]["scored_row_count"],
            non_applicable_row_count=previous["facts"]["non_applicable_row_count"],
            missing_row_count=previous["facts"]["missing_row_count"],
            excluded_trajectory_count=previous["facts"]["excluded_trajectory_count"],
            accepted_trajectory_count=previous["facts"]["accepted_trajectory_count"],
            comparison_labels=tuple(previous["facts"]["comparison_labels"]),
        )

    kwargs: dict[str, Any] = {
        "prediction_run_ids": previous["prediction_run_ids"],
        "metric_run_ids": previous["metric_run_ids"],
        "accepted_manifest_sha256": previous["accepted_manifest_sha256"],
        "fold_manifest_sha256": previous["fold_manifest_sha256"],
        "code_sha256": previous["code_sha256"],
        "config_sha256": previous["config_sha256"],
        "evidence_kind": previous["evidence_kind"],
        "locked_artifacts": (),
        "downstream": (),
    }
    kwargs.update(overrides)

    successor = build_result_lock(
        lock_id=lock_id,
        lock_version=lock_version,
        facts=facts_source,
        supersedes=previous["lock_id"],
        supersession_reason=reason,
        **kwargs,
    )
    return retired, successor


def validate_result_lock(document: Mapping[str, Any]) -> None:
    """Validate a result lock, raising on the first violation."""

    if document.get("schema_id") != SCHEMA_ID:
        raise ResultLockError(
            f"expected schema_id {SCHEMA_ID!r}, got {document.get('schema_id')!r}"
        )
    if document.get("status") not in LOCK_STATUSES:
        raise ResultLockError(f"unknown status {document.get('status')!r}")
    if document.get("evidence_kind") not in ("real", "synthetic"):
        raise ResultLockError("evidence_kind must be 'real' or 'synthetic'")
    if not document.get("lock_version"):
        raise ResultLockError("a lock must carry a version")

    facts = document.get("facts") or {}
    partition = (
        facts.get("scored_row_count", 0)
        + facts.get("non_applicable_row_count", 0)
        + facts.get("missing_row_count", 0)
    )
    if partition != facts.get("prediction_row_count"):
        raise ResultLockError(
            "locked facts do not partition prediction_row_count"
        )

    if document.get("supersedes") and not document.get("supersession_reason"):
        raise ResultLockError("a superseding lock must record a reason")
    if document.get("supersedes") == document.get("lock_id"):
        raise ResultLockError("a lock cannot supersede itself")

    acknowledgements = document.get("acknowledgements") or {}
    if set(acknowledgements) != set(ACKNOWLEDGEMENT_ROLES):
        raise ResultLockError(
            f"acknowledgement slots must be exactly {ACKNOWLEDGEMENT_ROLES}"
        )
    for role, entry in acknowledgements.items():
        if entry.get("status") not in ACKNOWLEDGEMENT_STATUSES:
            raise ResultLockError(
                f"{role} has unknown acknowledgement status {entry.get('status')!r}"
            )
        if entry.get("status") == "rejected" and not entry.get("note"):
            raise ResultLockError(f"{role} rejected the lock without a note")

    expected_checksum = compute_lock_checksum(document)
    if document.get("lock_checksum") != expected_checksum:
        raise ResultLockError(
            "lock_checksum does not match the lock's own content; the document "
            "was edited after locking instead of being superseded"
        )

    if document["evidence_kind"] == "real":
        if not document.get("accepted_manifest_sha256"):
            raise ResultLockError("a real lock requires accepted_manifest_sha256")
        if not document.get("fold_manifest_sha256"):
            raise ResultLockError("a real lock requires fold_manifest_sha256")
        if not document.get("prediction_run_ids"):
            raise ResultLockError("a real lock requires prediction run IDs")


def dump_result_lock(document: Mapping[str, Any]) -> str:
    """Serialize a validated lock deterministically."""

    validate_result_lock(document)
    return json.dumps(document, indent=2, sort_keys=True, default=_json_default) + "\n"


def _json_default(value: Any) -> Any:
    if isinstance(value, tuple):
        return list(value)
    raise TypeError(f"{type(value).__name__} is not JSON serializable")


__all__ = [
    "ACKNOWLEDGEMENT_ROLES",
    "ACKNOWLEDGEMENT_STATUSES",
    "LOCK_STATUSES",
    "SCHEMA_ID",
    "SCHEMA_VERSION",
    "DownstreamImpact",
    "LockedArtifact",
    "ResultFacts",
    "ResultLockError",
    "acknowledge_result_lock",
    "build_result_lock",
    "compute_lock_checksum",
    "dump_result_lock",
    "supersede_result_lock",
    "validate_result_lock",
]
