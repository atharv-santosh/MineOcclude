"""Control-failure claim-impact record (Person D Step 7.5).

Execution manual Step 7.5 requires a claim-impact decision record that
keeps contradictory locked controls *visible*, identifying the failed or
contradictory control, the affected comparison, the affected claim, the
evidence version, the owner, the required review, and whether the result
is plumbing-only, an invalid measurement, a clean negative, or eligible
for Person B's causal interpretation.

The module is written around one prohibition: **do not suppress, delete,
filter, or relabel an inconvenient control result.** Consequently:

* There is no delete or filter function. :func:`add_control_failure`
  only ever appends.
* A reclassification is a *versioned successor* entry that cites the
  prior classification and a reason, never an edit of the original.
* :func:`validate_control_failure_record` recomputes the record's
  checksum and rejects a document whose entries were edited in place.
* The four dispositions are kept strictly apart, because collapsing them
  is how an engineering failure gets published as a scientific negative.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Sequence

SCHEMA_ID = "person-d-control-failure-claim-impact-v0-1"
SCHEMA_VERSION = "1.0"

#: The four dispositions, deliberately non-overlapping.
#:
#: ``plumbing_only``       -- the pipeline broke; the science is untouched.
#: ``invalid_measurement`` -- a measurement exists but cannot be trusted.
#: ``clean_negative``      -- the pipeline worked and the effect is absent.
#: ``eligible_for_causal_interpretation`` -- Person B may interpret it.
DISPOSITIONS: tuple[str, ...] = (
    "plumbing_only",
    "invalid_measurement",
    "clean_negative",
    "eligible_for_causal_interpretation",
)

#: Only Person B may assign the disposition that authorizes causal
#: interpretation. Person D can record every other disposition because
#: they are statements about the pipeline, not about the science.
PERSON_B_ONLY_DISPOSITIONS: frozenset[str] = frozenset(
    {"clean_negative", "eligible_for_causal_interpretation"}
)

REVIEW_STATUSES: tuple[str, ...] = ("required", "in_review", "complete", "waived")

ENTRY_STATUSES: tuple[str, ...] = ("open", "reclassified", "closed")


class ControlFailureError(ValueError):
    """Raised when a claim-impact entry cannot be recorded honestly."""


@dataclass(frozen=True)
class ControlFailureEntry:
    """One failed or contradictory control and what it costs.

    ``reclassifies`` points at the entry this one supersedes. The
    superseded entry is never removed; it is marked ``reclassified`` and
    stays in the record, so the history of how a result was interpreted
    remains readable.
    """

    entry_id: str
    control_clip_id: str
    control_type: str
    failure_kind: str
    failure_detail: str
    affected_comparison: str
    affected_claim: str
    evidence_version: str
    evidence_sha256: Optional[str]
    owner_role: str
    required_review: str
    review_status: str
    disposition: str
    disposition_owner: str
    disposition_rationale: str
    reclassifies: Optional[str] = None
    reclassification_reason: Optional[str] = None
    status: str = "open"
    notes: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.disposition not in DISPOSITIONS:
            raise ControlFailureError(
                f"entry {self.entry_id!r} has unknown disposition "
                f"{self.disposition!r}; expected one of {DISPOSITIONS}"
            )
        if self.review_status not in REVIEW_STATUSES:
            raise ControlFailureError(
                f"entry {self.entry_id!r} has unknown review_status "
                f"{self.review_status!r}"
            )
        if self.status not in ENTRY_STATUSES:
            raise ControlFailureError(
                f"entry {self.entry_id!r} has unknown status {self.status!r}"
            )
        if (
            self.disposition in PERSON_B_ONLY_DISPOSITIONS
            and self.disposition_owner != "person_b"
        ):
            raise ControlFailureError(
                f"entry {self.entry_id!r} assigns disposition "
                f"{self.disposition!r} under owner {self.disposition_owner!r}; "
                "only Person B may declare a clean negative or authorize causal "
                "interpretation"
            )
        for name, value in (
            ("failure_detail", self.failure_detail),
            ("affected_comparison", self.affected_comparison),
            ("affected_claim", self.affected_claim),
            ("evidence_version", self.evidence_version),
            ("required_review", self.required_review),
            ("disposition_rationale", self.disposition_rationale),
        ):
            if not value:
                raise ControlFailureError(
                    f"entry {self.entry_id!r} records no {name}; a control "
                    "failure with no stated impact cannot be reviewed"
                )
        if self.reclassifies and not self.reclassification_reason:
            raise ControlFailureError(
                f"entry {self.entry_id!r} reclassifies {self.reclassifies!r} "
                "without a reason"
            )
        if self.reclassification_reason and not self.reclassifies:
            raise ControlFailureError(
                f"entry {self.entry_id!r} records a reclassification reason but "
                "names no prior entry"
            )
        if self.reclassifies == self.entry_id:
            raise ControlFailureError(
                f"entry {self.entry_id!r} cannot reclassify itself"
            )


def build_control_failure_record(
    *,
    record_id: str,
    record_version: str,
    entries: Sequence[ControlFailureEntry] = (),
    control_matrix_run_id: Optional[str] = None,
    evidence_kind: str = "synthetic",
) -> dict[str, Any]:
    """Build the claim-impact decision record."""

    if evidence_kind not in ("real", "synthetic"):
        raise ControlFailureError("evidence_kind must be 'real' or 'synthetic'")

    entry_ids = [entry.entry_id for entry in entries]
    duplicates = sorted({eid for eid in entry_ids if entry_ids.count(eid) > 1})
    if duplicates:
        raise ControlFailureError(f"duplicate entry IDs {duplicates}")

    known = set(entry_ids)
    for entry in entries:
        if entry.reclassifies and entry.reclassifies not in known:
            raise ControlFailureError(
                f"entry {entry.entry_id!r} reclassifies unknown entry "
                f"{entry.reclassifies!r}; the superseded entry must remain in "
                "the record"
            )

    disposition_counts = {disposition: 0 for disposition in DISPOSITIONS}
    for entry in entries:
        if entry.status != "reclassified":
            disposition_counts[entry.disposition] += 1

    document: dict[str, Any] = {
        "schema_id": SCHEMA_ID,
        "schema_version": SCHEMA_VERSION,
        "producer_role": "person_d",
        "record_id": record_id,
        "record_version": record_version,
        "evidence_kind": evidence_kind,
        "control_matrix_run_id": control_matrix_run_id,
        "suppression_policy": (
            "Control failures are appended, never deleted, filtered, or "
            "relabelled. A changed interpretation is recorded as a new entry "
            "that cites the one it supersedes; the superseded entry remains "
            "visible."
        ),
        "entry_count": len(entries),
        "active_entry_count": sum(1 for e in entries if e.status != "reclassified"),
        "disposition_counts": disposition_counts,
        "entries": tuple(
            _entry_to_dict(entry) for entry in sorted(entries, key=lambda e: e.entry_id)
        ),
    }
    document["record_checksum"] = compute_record_checksum(document)
    return document


def _entry_to_dict(entry: ControlFailureEntry) -> dict[str, Any]:
    return {
        "entry_id": entry.entry_id,
        "control_clip_id": entry.control_clip_id,
        "control_type": entry.control_type,
        "failure_kind": entry.failure_kind,
        "failure_detail": entry.failure_detail,
        "affected_comparison": entry.affected_comparison,
        "affected_claim": entry.affected_claim,
        "evidence_version": entry.evidence_version,
        "evidence_sha256": entry.evidence_sha256,
        "owner_role": entry.owner_role,
        "required_review": entry.required_review,
        "review_status": entry.review_status,
        "disposition": entry.disposition,
        "disposition_owner": entry.disposition_owner,
        "disposition_rationale": entry.disposition_rationale,
        "reclassifies": entry.reclassifies,
        "reclassification_reason": entry.reclassification_reason,
        "status": entry.status,
        "notes": list(entry.notes),
    }


def compute_record_checksum(document: Mapping[str, Any]) -> str:
    """Checksum the record's content, excluding the checksum itself."""

    payload = {
        key: value for key, value in document.items() if key != "record_checksum"
    }
    encoded = json.dumps(payload, sort_keys=True, default=_json_default).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def add_control_failure(
    document: Mapping[str, Any], entry: ControlFailureEntry
) -> dict[str, Any]:
    """Append one entry, returning a new record. Never removes anything.

    When ``entry`` reclassifies a prior entry, the prior entry's status
    becomes ``reclassified`` -- its content is otherwise untouched and it
    stays in the record.
    """

    existing = [dict(item) for item in document["entries"]]
    if any(item["entry_id"] == entry.entry_id for item in existing):
        raise ControlFailureError(f"entry {entry.entry_id!r} already exists")

    if entry.reclassifies:
        target = next(
            (item for item in existing if item["entry_id"] == entry.reclassifies), None
        )
        if target is None:
            raise ControlFailureError(
                f"cannot reclassify unknown entry {entry.reclassifies!r}"
            )
        target["status"] = "reclassified"

    existing.append(_entry_to_dict(entry))
    existing.sort(key=lambda item: item["entry_id"])

    disposition_counts = {disposition: 0 for disposition in DISPOSITIONS}
    for item in existing:
        if item["status"] != "reclassified":
            disposition_counts[item["disposition"]] += 1

    updated = dict(document)
    updated["entries"] = tuple(existing)
    updated["entry_count"] = len(existing)
    updated["active_entry_count"] = sum(
        1 for item in existing if item["status"] != "reclassified"
    )
    updated["disposition_counts"] = disposition_counts
    updated["record_checksum"] = compute_record_checksum(updated)
    return updated


def validate_control_failure_record(document: Mapping[str, Any]) -> None:
    """Validate the record, raising on the first violation."""

    if document.get("schema_id") != SCHEMA_ID:
        raise ControlFailureError(
            f"expected schema_id {SCHEMA_ID!r}, got {document.get('schema_id')!r}"
        )
    if document.get("evidence_kind") not in ("real", "synthetic"):
        raise ControlFailureError("evidence_kind must be 'real' or 'synthetic'")

    entries = document.get("entries") or ()
    entry_ids = [entry["entry_id"] for entry in entries]
    if len(set(entry_ids)) != len(entry_ids):
        raise ControlFailureError("duplicate entry IDs in the record")

    for entry in entries:
        if entry["disposition"] not in DISPOSITIONS:
            raise ControlFailureError(
                f"entry {entry['entry_id']!r} has unknown disposition "
                f"{entry['disposition']!r}"
            )
        if (
            entry["disposition"] in PERSON_B_ONLY_DISPOSITIONS
            and entry["disposition_owner"] != "person_b"
        ):
            raise ControlFailureError(
                f"entry {entry['entry_id']!r} claims {entry['disposition']!r} "
                "without Person B ownership"
            )
        if entry["status"] not in ENTRY_STATUSES:
            raise ControlFailureError(
                f"entry {entry['entry_id']!r} has unknown status {entry['status']!r}"
            )
        if entry["reclassifies"]:
            if entry["reclassifies"] not in entry_ids:
                raise ControlFailureError(
                    f"entry {entry['entry_id']!r} reclassifies "
                    f"{entry['reclassifies']!r}, which is not in the record; a "
                    "superseded entry must never be removed"
                )
            if not entry["reclassification_reason"]:
                raise ControlFailureError(
                    f"entry {entry['entry_id']!r} reclassifies without a reason"
                )

    if document.get("entry_count") != len(entries):
        raise ControlFailureError("entry_count does not match the entries")

    active = sum(1 for entry in entries if entry["status"] != "reclassified")
    if document.get("active_entry_count") != active:
        raise ControlFailureError("active_entry_count does not match the entries")

    counts = {disposition: 0 for disposition in DISPOSITIONS}
    for entry in entries:
        if entry["status"] != "reclassified":
            counts[entry["disposition"]] += 1
    if document.get("disposition_counts") != counts:
        raise ControlFailureError("disposition_counts do not match the entries")

    if document.get("record_checksum") != compute_record_checksum(document):
        raise ControlFailureError(
            "record_checksum does not match the record's own content; an entry "
            "was edited in place instead of being superseded by a new one"
        )


def dump_control_failure_record(document: Mapping[str, Any]) -> str:
    """Serialize a validated record deterministically."""

    validate_control_failure_record(document)
    return json.dumps(document, indent=2, sort_keys=True, default=_json_default) + "\n"


def _json_default(value: Any) -> Any:
    if isinstance(value, tuple):
        return list(value)
    raise TypeError(f"{type(value).__name__} is not JSON serializable")


__all__ = [
    "DISPOSITIONS",
    "ENTRY_STATUSES",
    "PERSON_B_ONLY_DISPOSITIONS",
    "REVIEW_STATUSES",
    "SCHEMA_ID",
    "SCHEMA_VERSION",
    "ControlFailureEntry",
    "ControlFailureError",
    "add_control_failure",
    "build_control_failure_record",
    "compute_record_checksum",
    "dump_control_failure_record",
    "validate_control_failure_record",
]
