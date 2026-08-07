"""Resumable, checksum-valid extraction queue for the MVP (Steps 7.5 and 7.6).

The queue is derived from an immutable accepted manifest plus a frozen run
configuration. It skips only work whose recorded checksums still verify, retries
a bounded number of transient failures, quarantines identity/data/model
failures, and publishes a status and forecast that never over-claims.

Resuming a queue must not duplicate an accepted artifact and must not change the
run identity. Both properties are enforced here, not assumed.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from enum import Enum
from pathlib import Path
from typing import Any

QUEUE_SCHEMA_VERSION = "person-a-mvp-extraction-queue-v0.1"

DEFAULT_MAX_TRANSIENT_RETRIES = 3

# Failure kinds that may be retried inside one run identity.
TRANSIENT_FAILURE_KINDS = frozenset(
    {"transient_failure", "host_oom", "io_failure", "runtime_interrupted"}
)

# Failure kinds that must stop the item and preserve its evidence.
QUARANTINE_FAILURE_KINDS = frozenset(
    {"identity_failure", "data_failure", "model_failure", "checksum_failure"}
)


class ItemState(str, Enum):
    """Lifecycle states one queue item may occupy."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    QUARANTINED = "quarantined"
    EXCLUDED = "excluded"


TERMINAL_STATES = frozenset(
    {ItemState.COMPLETED, ItemState.QUARANTINED, ItemState.EXCLUDED}
)


class QueueErrorCode(str, Enum):
    """Stable reasons the queue refuses to proceed."""

    INVALID_REQUEST = "invalid_request"
    DUPLICATE_ITEM = "duplicate_item"
    UNKNOWN_ITEM = "unknown_item"
    RUN_IDENTITY_CHANGED = "run_identity_changed"
    DUPLICATE_COMPLETION = "duplicate_completion"
    CHECKSUM_MISMATCH = "checksum_mismatch"
    CARDINALITY_MISMATCH = "cardinality_mismatch"
    ILLEGAL_TRANSITION = "illegal_transition"
    CORRUPT_STATE = "corrupt_state"


class QueueError(ValueError):
    """Raised when a queue operation would damage run identity or evidence."""

    def __init__(self, code: QueueErrorCode, message: str) -> None:
        self.code = code
        super().__init__(f"{code.value}: {message}")


def _fail(code: QueueErrorCode, message: str) -> None:
    raise QueueError(code, message)


@dataclass(frozen=True)
class ExpectedKeys:
    """The exact trajectory/frame/layer keys one item must produce."""

    trajectory_id: str
    frame_count: int
    layer_count: int

    def __post_init__(self) -> None:
        if not isinstance(self.trajectory_id, str) or not self.trajectory_id.strip():
            _fail(QueueErrorCode.INVALID_REQUEST, "trajectory_id is required")
        for name in ("frame_count", "layer_count"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                _fail(
                    QueueErrorCode.INVALID_REQUEST,
                    f"{name} must be a positive integer",
                )

    @property
    def expected_row_count(self) -> int:
        return self.frame_count * self.layer_count

    @property
    def expected_chunk_count(self) -> int:
        return self.layer_count

    def keys(self) -> tuple[tuple[str, int, int], ...]:
        return tuple(
            (self.trajectory_id, frame, layer)
            for frame in range(self.frame_count)
            for layer in range(self.layer_count)
        )


@dataclass(frozen=True)
class CompletionRecord:
    """A completed item's produced identity, as recorded at completion time."""

    activation_index_sha256: str
    activation_row_count: int
    chunk_count: int
    chunk_sha256: tuple[str, ...]
    activation_bytes: int
    elapsed_seconds: float
    completed_at: str

    def to_document(self) -> dict[str, Any]:
        return {
            "activation_index_sha256": self.activation_index_sha256,
            "activation_row_count": self.activation_row_count,
            "chunk_count": self.chunk_count,
            "chunk_sha256": list(self.chunk_sha256),
            "activation_bytes": self.activation_bytes,
            "elapsed_seconds": self.elapsed_seconds,
            "completed_at": self.completed_at,
        }

    @classmethod
    def from_document(cls, document: Mapping[str, Any]) -> CompletionRecord:
        return cls(
            activation_index_sha256=str(document["activation_index_sha256"]),
            activation_row_count=int(document["activation_row_count"]),
            chunk_count=int(document["chunk_count"]),
            chunk_sha256=tuple(str(v) for v in document["chunk_sha256"]),
            activation_bytes=int(document["activation_bytes"]),
            elapsed_seconds=float(document["elapsed_seconds"]),
            completed_at=str(document["completed_at"]),
        )


@dataclass(frozen=True)
class AttemptRecord:
    """One recorded attempt, kept even when it failed."""

    attempt: int
    outcome: str
    failure_kind: str | None
    detail: str | None
    log_path: str | None = None

    def to_document(self) -> dict[str, Any]:
        return {
            "attempt": self.attempt,
            "outcome": self.outcome,
            "failure_kind": self.failure_kind,
            "detail": self.detail,
            "log_path": self.log_path,
        }


@dataclass(frozen=True)
class QueueItem:
    """One immutable extraction unit plus its mutable-by-replacement state."""

    item_id: str
    expected: ExpectedKeys
    layout_id: str
    group: str
    input_manifest_sha256: str
    state: ItemState = ItemState.PENDING
    attempts: tuple[AttemptRecord, ...] = ()
    completion: CompletionRecord | None = None
    quarantine_reason: str | None = None
    exclusion_reason: str | None = None

    @property
    def transient_attempt_count(self) -> int:
        return sum(
            1
            for attempt in self.attempts
            if attempt.failure_kind in TRANSIENT_FAILURE_KINDS
        )

    def to_document(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "trajectory_id": self.expected.trajectory_id,
            "layout_id": self.layout_id,
            "group": self.group,
            "frame_count": self.expected.frame_count,
            "layer_count": self.expected.layer_count,
            "expected_activation_row_count": self.expected.expected_row_count,
            "expected_chunk_count": self.expected.expected_chunk_count,
            "input_manifest_sha256": self.input_manifest_sha256,
            "state": self.state.value,
            "attempts": [attempt.to_document() for attempt in self.attempts],
            "attempt_count": len(self.attempts),
            "transient_attempt_count": self.transient_attempt_count,
            "completion": (
                self.completion.to_document() if self.completion else None
            ),
            "quarantine_reason": self.quarantine_reason,
            "exclusion_reason": self.exclusion_reason,
        }


@dataclass
class ExtractionQueue:
    """An immutable-identity, resumable extraction queue."""

    run_id: str
    config_hash: str
    code_sha: str
    accepted_manifest_sha256: str
    max_transient_retries: int = DEFAULT_MAX_TRANSIENT_RETRIES
    items: dict[str, QueueItem] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("run_id", "config_hash", "code_sha", "accepted_manifest_sha256"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                _fail(QueueErrorCode.INVALID_REQUEST, f"{name} is required")
        if (
            isinstance(self.max_transient_retries, bool)
            or not isinstance(self.max_transient_retries, int)
            or self.max_transient_retries < 0
        ):
            _fail(
                QueueErrorCode.INVALID_REQUEST,
                "max_transient_retries must be a non-negative integer",
            )

    # -- construction ----------------------------------------------------

    def add(self, item: QueueItem) -> None:
        if item.item_id in self.items:
            _fail(
                QueueErrorCode.DUPLICATE_ITEM,
                f"item {item.item_id!r} is already queued",
            )
        self.items[item.item_id] = item

    def extend(self, items: Iterable[QueueItem]) -> None:
        for item in items:
            self.add(item)

    # -- identity --------------------------------------------------------

    def identity(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "config_hash": self.config_hash,
            "code_sha": self.code_sha,
            "accepted_manifest_sha256": self.accepted_manifest_sha256,
        }

    def identity_digest(self) -> str:
        return hashlib.sha256(
            json.dumps(self.identity(), sort_keys=True).encode("utf-8")
        ).hexdigest()

    # -- scheduling ------------------------------------------------------

    def next_pending(self) -> QueueItem | None:
        """Return the next item that may legally run, in stable order."""

        for item_id in sorted(self.items):
            item = self.items[item_id]
            if item.state is ItemState.PENDING:
                return item
        return None

    def _require(self, item_id: str) -> QueueItem:
        item = self.items.get(item_id)
        if item is None:
            _fail(QueueErrorCode.UNKNOWN_ITEM, f"item {item_id!r} is not queued")
        return item  # type: ignore[return-value]

    def mark_running(self, item_id: str) -> QueueItem:
        item = self._require(item_id)
        if item.state is not ItemState.PENDING:
            _fail(
                QueueErrorCode.ILLEGAL_TRANSITION,
                f"item {item_id!r} cannot start from state {item.state.value}",
            )
        updated = replace(item, state=ItemState.RUNNING)
        self.items[item_id] = updated
        return updated

    def complete(
        self,
        item_id: str,
        record: CompletionRecord,
    ) -> QueueItem:
        """Record a completion after checking cardinality, never overwriting."""

        item = self._require(item_id)
        if item.state is ItemState.COMPLETED:
            _fail(
                QueueErrorCode.DUPLICATE_COMPLETION,
                f"item {item_id!r} is already completed and must not be rewritten",
            )
        if item.state is not ItemState.RUNNING:
            _fail(
                QueueErrorCode.ILLEGAL_TRANSITION,
                f"item {item_id!r} cannot complete from state {item.state.value}",
            )
        _require_cardinality(item, record)
        updated = replace(
            item,
            state=ItemState.COMPLETED,
            completion=record,
            attempts=(
                *item.attempts,
                AttemptRecord(
                    attempt=len(item.attempts) + 1,
                    outcome="completed",
                    failure_kind=None,
                    detail=None,
                ),
            ),
        )
        self.items[item_id] = updated
        return updated

    def fail(
        self,
        item_id: str,
        *,
        failure_kind: str,
        detail: str,
        log_path: str | None = None,
    ) -> QueueItem:
        """Record a failure; retry transient kinds, quarantine the rest."""

        item = self._require(item_id)
        if item.state not in {ItemState.RUNNING, ItemState.PENDING}:
            _fail(
                QueueErrorCode.ILLEGAL_TRANSITION,
                f"item {item_id!r} cannot fail from state {item.state.value}",
            )
        attempt = AttemptRecord(
            attempt=len(item.attempts) + 1,
            outcome="failed",
            failure_kind=failure_kind,
            detail=detail,
            log_path=log_path,
        )
        attempts = (*item.attempts, attempt)
        if failure_kind in QUARANTINE_FAILURE_KINDS:
            state = ItemState.QUARANTINED
            reason = f"{failure_kind}: {detail}"
        elif failure_kind in TRANSIENT_FAILURE_KINDS:
            transient = sum(
                1 for entry in attempts if entry.failure_kind in TRANSIENT_FAILURE_KINDS
            )
            if transient > self.max_transient_retries:
                state = ItemState.QUARANTINED
                reason = (
                    f"transient retry budget exhausted after {transient} attempts: "
                    f"{detail}"
                )
            else:
                state = ItemState.PENDING
                reason = None
        else:
            state = ItemState.QUARANTINED
            reason = f"unclassified_failure({failure_kind}): {detail}"
        updated = replace(
            item,
            state=state,
            attempts=attempts,
            quarantine_reason=reason,
        )
        self.items[item_id] = updated
        return updated

    def exclude(self, item_id: str, *, reason: str) -> QueueItem:
        item = self._require(item_id)
        if item.state is ItemState.COMPLETED:
            _fail(
                QueueErrorCode.ILLEGAL_TRANSITION,
                "a completed item is never retroactively excluded",
            )
        updated = replace(
            item,
            state=ItemState.EXCLUDED,
            exclusion_reason=reason,
        )
        self.items[item_id] = updated
        return updated

    # -- resume ----------------------------------------------------------

    def verify_completed(
        self,
        item_id: str,
        verifier: Callable[[CompletionRecord], bool],
    ) -> bool:
        """Return True only when a completed item's checksums still verify."""

        item = self._require(item_id)
        if item.state is not ItemState.COMPLETED or item.completion is None:
            return False
        return bool(verifier(item.completion))

    def resume(
        self,
        *,
        verifier: Callable[[CompletionRecord], bool] | None = None,
    ) -> dict[str, Any]:
        """Reopen only work that is not checksum-valid and complete.

        A `RUNNING` item from an interrupted session returns to `PENDING`
        because no completion record was ever written for it.
        """

        reopened_interrupted: list[str] = []
        reopened_invalid: list[str] = []
        skipped_valid: list[str] = []
        for item_id in sorted(self.items):
            item = self.items[item_id]
            if item.state is ItemState.RUNNING:
                self.items[item_id] = replace(item, state=ItemState.PENDING)
                reopened_interrupted.append(item_id)
                continue
            if item.state is not ItemState.COMPLETED:
                continue
            if verifier is None or self.verify_completed(item_id, verifier):
                skipped_valid.append(item_id)
                continue
            self.items[item_id] = replace(
                item,
                state=ItemState.PENDING,
                completion=None,
                attempts=(
                    *item.attempts,
                    AttemptRecord(
                        attempt=len(item.attempts) + 1,
                        outcome="reopened",
                        failure_kind="checksum_failure",
                        detail=(
                            "recorded completion checksums no longer verify; "
                            "the item was reopened rather than trusted"
                        ),
                    ),
                ),
            )
            reopened_invalid.append(item_id)
        return {
            "run_id": self.run_id,
            "identity_digest": self.identity_digest(),
            "skipped_checksum_valid": skipped_valid,
            "reopened_interrupted": reopened_interrupted,
            "reopened_checksum_invalid": reopened_invalid,
            "skip_rule": "checksum_valid_completed_only",
        }

    # -- reporting -------------------------------------------------------

    def status(self, *, forecast_basis: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """Publish the full queue state plus a measured-rate finish forecast."""

        counts = {state.value: 0 for state in ItemState}
        for item in self.items.values():
            counts[item.state.value] += 1
        completed = [
            item for item in self.items.values() if item.state is ItemState.COMPLETED
        ]
        remaining_frames = sum(
            item.expected.frame_count
            for item in self.items.values()
            if item.state not in TERMINAL_STATES
        )
        measured_seconds = sum(
            item.completion.elapsed_seconds for item in completed if item.completion
        )
        measured_frames = sum(item.expected.frame_count for item in completed)
        measured_bytes = sum(
            item.completion.activation_bytes for item in completed if item.completion
        )
        seconds_per_frame = (
            measured_seconds / measured_frames if measured_frames else None
        )
        bytes_per_frame = measured_bytes / measured_frames if measured_frames else None
        if seconds_per_frame is None and forecast_basis:
            seconds_per_frame = forecast_basis.get("seconds_per_frame")
        if bytes_per_frame is None and forecast_basis:
            bytes_per_frame = forecast_basis.get("bytes_per_frame")
        return {
            "schema_version": QUEUE_SCHEMA_VERSION,
            "step": "7.5",
            "run_id": self.run_id,
            "identity": self.identity(),
            "identity_digest": self.identity_digest(),
            "item_count": len(self.items),
            "state_counts": counts,
            "completed_activation_row_count": sum(
                item.completion.activation_row_count
                for item in completed
                if item.completion
            ),
            "completed_chunk_count": sum(
                item.completion.chunk_count for item in completed if item.completion
            ),
            "completed_activation_bytes": measured_bytes,
            "measured_wall_seconds": measured_seconds,
            "remaining_frame_count": remaining_frames,
            "forecast": {
                "seconds_per_frame": seconds_per_frame,
                "bytes_per_frame": bytes_per_frame,
                "estimated_remaining_seconds": (
                    remaining_frames * seconds_per_frame
                    if seconds_per_frame is not None
                    else None
                ),
                "estimated_remaining_bytes": (
                    remaining_frames * bytes_per_frame
                    if bytes_per_frame is not None
                    else None
                ),
                "basis": (
                    "measured_completed_items"
                    if measured_frames
                    else "prior_measured_pilot_rates"
                ),
            },
            "items": [
                self.items[item_id].to_document() for item_id in sorted(self.items)
            ],
        }

    # -- persistence -----------------------------------------------------

    def to_document(self) -> dict[str, Any]:
        return {
            "schema_version": QUEUE_SCHEMA_VERSION,
            "identity": self.identity(),
            "max_transient_retries": self.max_transient_retries,
            "items": [
                self.items[item_id].to_document() for item_id in sorted(self.items)
            ],
        }

    def save(self, path: Path | str) -> str:
        # Write bytes, not text: text mode translates "\n" to "\r\n" on Windows,
        # so the saved state would not hash to the digest this method returns.
        payload = (
            json.dumps(self.to_document(), indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        return hashlib.sha256(payload).hexdigest()

    @classmethod
    def load(
        cls,
        path: Path | str,
        *,
        expected_identity: Mapping[str, Any] | None = None,
    ) -> ExtractionQueue:
        """Reload a persisted queue, refusing a changed run identity."""

        document = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(document, Mapping):
            _fail(QueueErrorCode.CORRUPT_STATE, "queue state must be a JSON object")
        if document.get("schema_version") != QUEUE_SCHEMA_VERSION:
            _fail(
                QueueErrorCode.CORRUPT_STATE,
                f"queue schema must equal {QUEUE_SCHEMA_VERSION!r}",
            )
        identity = document.get("identity")
        if not isinstance(identity, Mapping):
            _fail(QueueErrorCode.CORRUPT_STATE, "queue state lacks a run identity")
        if expected_identity is not None and dict(identity) != dict(expected_identity):
            _fail(
                QueueErrorCode.RUN_IDENTITY_CHANGED,
                "persisted queue identity differs from the requested run identity",
            )
        queue = cls(
            run_id=str(identity["run_id"]),
            config_hash=str(identity["config_hash"]),
            code_sha=str(identity["code_sha"]),
            accepted_manifest_sha256=str(identity["accepted_manifest_sha256"]),
            max_transient_retries=int(
                document.get("max_transient_retries", DEFAULT_MAX_TRANSIENT_RETRIES)
            ),
        )
        for entry in document.get("items", ()):
            queue.add(_item_from_document(entry))
        return queue


def _item_from_document(document: Mapping[str, Any]) -> QueueItem:
    completion = document.get("completion")
    return QueueItem(
        item_id=str(document["item_id"]),
        expected=ExpectedKeys(
            trajectory_id=str(document["trajectory_id"]),
            frame_count=int(document["frame_count"]),
            layer_count=int(document["layer_count"]),
        ),
        layout_id=str(document.get("layout_id", "")),
        group=str(document.get("group", "")),
        input_manifest_sha256=str(document["input_manifest_sha256"]),
        state=ItemState(str(document["state"])),
        attempts=tuple(
            AttemptRecord(
                attempt=int(entry["attempt"]),
                outcome=str(entry["outcome"]),
                failure_kind=entry.get("failure_kind"),
                detail=entry.get("detail"),
                log_path=entry.get("log_path"),
            )
            for entry in document.get("attempts", ())
        ),
        completion=(
            CompletionRecord.from_document(completion) if completion else None
        ),
        quarantine_reason=document.get("quarantine_reason"),
        exclusion_reason=document.get("exclusion_reason"),
    )


def _require_cardinality(item: QueueItem, record: CompletionRecord) -> None:
    if record.activation_row_count != item.expected.expected_row_count:
        _fail(
            QueueErrorCode.CARDINALITY_MISMATCH,
            f"{item.item_id}: {record.activation_row_count} rows != expected "
            f"{item.expected.expected_row_count}",
        )
    if record.chunk_count != item.expected.expected_chunk_count:
        _fail(
            QueueErrorCode.CARDINALITY_MISMATCH,
            f"{item.item_id}: {record.chunk_count} chunks != expected "
            f"{item.expected.expected_chunk_count}",
        )
    if len(record.chunk_sha256) != record.chunk_count:
        _fail(
            QueueErrorCode.CARDINALITY_MISMATCH,
            f"{item.item_id}: chunk digest count does not match chunk count",
        )
    if len(set(record.chunk_sha256)) != len(record.chunk_sha256):
        _fail(
            QueueErrorCode.CHECKSUM_MISMATCH,
            f"{item.item_id}: chunk digests repeat within one completion",
        )


# ---------------------------------------------------------------------------
# Step 7.6 — cardinality and shape certification
# ---------------------------------------------------------------------------


def certify_queue_cardinality(
    queue: ExtractionQueue,
    *,
    expected_cell_count: int,
    vector_width: int,
    stored_dtype: str,
) -> dict[str, Any]:
    """Certify the produced activation dataset or publish the exact shortfall."""

    completed = [
        item for item in queue.items.values() if item.state is ItemState.COMPLETED
    ]
    outstanding = [
        item.to_document()
        for item in queue.items.values()
        if item.state is not ItemState.COMPLETED
    ]
    index_hashes = [
        item.completion.activation_index_sha256 for item in completed if item.completion
    ]
    chunk_hashes = [
        digest
        for item in completed
        if item.completion
        for digest in item.completion.chunk_sha256
    ]
    duplicate_index = len(index_hashes) != len(set(index_hashes))
    duplicate_chunk = len(chunk_hashes) != len(set(chunk_hashes))
    if duplicate_index:
        _fail(
            QueueErrorCode.CHECKSUM_MISMATCH,
            "completed items share an activation index digest",
        )
    if duplicate_chunk:
        _fail(
            QueueErrorCode.CHECKSUM_MISMATCH,
            "completed items share an activation chunk digest",
        )
    return {
        "schema_version": QUEUE_SCHEMA_VERSION,
        "step": "7.6",
        "run_id": queue.run_id,
        "identity": queue.identity(),
        "expected_cell_count": expected_cell_count,
        "queued_item_count": len(queue.items),
        "completed_item_count": len(completed),
        "complete": len(completed) == expected_cell_count,
        "expected_activation_row_count": sum(
            item.expected.expected_row_count for item in queue.items.values()
        ),
        "completed_activation_row_count": sum(
            item.completion.activation_row_count for item in completed if item.completion
        ),
        "completed_chunk_count": sum(
            item.completion.chunk_count for item in completed if item.completion
        ),
        "duplicate_activation_index_digest": duplicate_index,
        "duplicate_activation_chunk_digest": duplicate_chunk,
        "one_to_one_join_rule": (
            "one pooled vector per accepted (trajectory_id, model_frame_idx, "
            "layer_idx, hook_site)"
        ),
        "vector_shape": [vector_width],
        "stored_dtype": stored_dtype,
        "pooled_storage_preserved_16_bit": stored_dtype == "float16",
        "analysis_arithmetic_promoted_in_person_b_only": True,
        "shortfall_item_count": len(outstanding),
        "shortfall": outstanding,
        "critical_path_owner": (
            "person_c_data" if len(queue.items) < expected_cell_count else "person_a_model"
        ),
        "missing_queue_item_count": max(0, expected_cell_count - len(queue.items)),
    }


def build_queue_from_matrix(
    reconciliation: Mapping[str, Any],
    *,
    run_id: str,
    config_hash: str,
    code_sha: str,
    accepted_manifest_sha256: str,
    layer_count: int,
    frame_counts: Mapping[str, int],
    max_transient_retries: int = DEFAULT_MAX_TRANSIENT_RETRIES,
) -> ExtractionQueue:
    """Queue exactly the cells the accepted manifest actually admits.

    Cells that are not accepted are deliberately not queued; they remain visible
    in the Step 7.2 shortfall with their owner instead of becoming silent work.
    """

    queue = ExtractionQueue(
        run_id=run_id,
        config_hash=config_hash,
        code_sha=code_sha,
        accepted_manifest_sha256=accepted_manifest_sha256,
        max_transient_retries=max_transient_retries,
    )
    for row in reconciliation.get("cells", ()):
        if row.get("state") != "accepted":
            continue
        cell_id = str(row["cell_id"])
        frame_count = frame_counts.get(cell_id)
        if frame_count is None:
            _fail(
                QueueErrorCode.INVALID_REQUEST,
                f"accepted cell {cell_id!r} has no declared frame count",
            )
        queue.add(
            QueueItem(
                item_id=cell_id,
                expected=ExpectedKeys(
                    trajectory_id=cell_id,
                    frame_count=int(frame_count),
                    layer_count=layer_count,
                ),
                layout_id=str(row.get("layout_id", "")),
                group=str(row.get("group", "")),
                input_manifest_sha256=str(row.get("evidence_sha256") or ""),
            )
        )
    return queue


__all__ = [
    "DEFAULT_MAX_TRANSIENT_RETRIES",
    "QUARANTINE_FAILURE_KINDS",
    "QUEUE_SCHEMA_VERSION",
    "TRANSIENT_FAILURE_KINDS",
    "AttemptRecord",
    "CompletionRecord",
    "ExpectedKeys",
    "ExtractionQueue",
    "ItemState",
    "QueueError",
    "QueueErrorCode",
    "QueueItem",
    "build_queue_from_matrix",
    "certify_queue_cardinality",
]
