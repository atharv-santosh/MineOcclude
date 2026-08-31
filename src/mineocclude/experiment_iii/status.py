"""The live status surface (LIVE_STATUS_CONTRACT.json).

**Cardinal rule: the status document is OBSERVATIONAL ONLY.** No code may read it
to decide what to do next. Control flow is driven exclusively by the hash-chain
ledger and the stage receipts; a status document that influences scientific
behavior is a defect.

It may carry counts, identifiers, timings, byte totals, error counts and blocker
codes. It must never carry a target value, a prediction, a metric, an RVE score or
any other scientific outcome — :func:`assert_observational_only` enforces that.

It is written atomically (``<name>.tmp`` then rename) and rewritten in full on
every update. Losing it must never affect resume, validation or results.
``III_A_STATUS`` is never a function of ``III_B_STATUS``, and
``III_B_STATUS = CLEAN_SKIP`` is an honourable pre-registered outcome, never an
error state.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from mineocclude.experiment_iii.authority import AUTHORITY_ROOT
from mineocclude.experiment_iii.blockers import validate_blocker_code
from mineocclude.experiment_iii.errors import ExperimentIIIError
from mineocclude.experiment_iii.namespace import guard_write_path

__all__ = [
    "STATUS_CONTRACT_PATH",
    "REQUIRED_FIELDS",
    "STAGES_REQUIRING_STATUS",
    "STAGE_STATUS_DOMAIN",
    "III_A_STATUS_DOMAIN",
    "III_B_STATUS_DOMAIN",
    "SCIENTIFIC_OUTCOME_FIELDS",
    "StatusDocument",
    "status_path",
    "assert_observational_only",
    "validate_status_document",
]

STATUS_CONTRACT_PATH = AUTHORITY_ROOT / "LIVE_STATUS_CONTRACT.json"

STAGES_REQUIRING_STATUS = (
    "A4", "A5", "A7", "A9", "A11", "A12",
    "B-PILOT", "B-CAP", "B-EXT", "B-U2", "B-U3",
)
STAGE_STATUS_DOMAIN = (
    "NOT_STARTED", "RUNNING", "PAUSED", "BLOCKED", "COMPLETE", "FAILED",
)
III_A_STATUS_DOMAIN = (
    "NOT_STARTED", "RUNNING", "BLOCKED", "RESULT_LOCKED", "TERMINALLY_ADJUDICATED",
)
III_B_STATUS_DOMAIN = (
    "NOT_STARTED", "PENDING_GATE", "RUNNING", "BLOCKED", "RESULT_LOCKED",
    "CLEAN_SKIP", "TERMINALLY_ADJUDICATED",
)
PROGRAM_STAGE_DOMAIN = ("III_A", "III_B", "BOTH", "PACKAGING")
VALIDATOR_STATUS_DOMAIN = ("NOT_RUN", "RUNNING", "PASS", "FAIL")

REQUIRED_FIELDS = (
    "PROCESS_ALIVE",
    "STAGE",
    "STAGE_STATUS",
    "TOTAL_UNITS",
    "COMPLETED_UNITS",
    "REMAINING_UNITS",
    "CURRENT_UNIT",
    "LAST_COMPLETED_UNIT",
    "ELAPSED_TIME",
    "LAST_MESSAGE_AT",
    "LAST_MESSAGE",
    "ERRORS_SEEN",
    "CURRENT_BLOCKER",
    "RETRY_COUNT",
    "POST_STAGE_VALIDATOR_STATUS",
    "NEXT_STAGE",
    "PROGRAM_STAGE",
    "III_A_STATUS",
    "III_B_STATUS",
)

#: Field names that would smuggle a scientific outcome into the status surface.
SCIENTIFIC_OUTCOME_FIELDS = frozenset(
    {
        "rmse", "mae", "r2", "target", "targets", "prediction", "predictions",
        "rve", "rve_score", "slope", "p_value", "estimand", "interval",
        "ci_low", "ci_high", "sigma_hat", "world_x", "label", "labels",
        "accuracy", "error", "result_value",
    }
)

STALENESS_WINDOW_SECONDS = 120


def status_path(stage: str, root: Path | None = None) -> Path:
    from mineocclude.experiment_iii.authority import REPOSITORY_ROOT

    base = Path(root) if root is not None else REPOSITORY_ROOT
    return base / "docs" / "experiment_iii" / "status" / f"{stage}_status.json"


def assert_observational_only(document: Mapping[str, Any]) -> None:
    """Refuse any scientific value in the status surface."""
    offending = sorted(
        key for key in document if key.lower() in SCIENTIFIC_OUTCOME_FIELDS
    )
    if offending:
        raise ExperimentIIIError(
            "STATUS_DOCUMENT_MALFORMED",
            f"the status document is observational only; it must never carry a "
            f"scientific outcome: {offending}",
        )
    message = document.get("LAST_MESSAGE")
    if isinstance(message, str) and len(message) > 512:
        raise ExperimentIIIError(
            "STATUS_DOCUMENT_MALFORMED", "LAST_MESSAGE exceeds 512 characters"
        )


@dataclass
class StatusDocument:
    """The frozen status surface for one long-running stage."""

    stage: str
    program_stage: str = "III_A"
    total_units: int = 0
    completed_units: int = 0
    stage_status: str = "NOT_STARTED"
    current_unit: str | None = None
    last_completed_unit: str | None = None
    last_message: str = ""
    errors_seen: int = 0
    current_blocker: str | None = None
    retry_count: int = 0
    post_stage_validator_status: str = "NOT_RUN"
    next_stage: str | None = None
    iii_a_status: str = "NOT_STARTED"
    iii_b_status: str = "NOT_STARTED"
    authority_sha256: str | None = None
    source_closure: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)
    _started: float = field(default_factory=time.monotonic, repr=False)

    def __post_init__(self) -> None:
        if self.stage not in STAGES_REQUIRING_STATUS:
            raise ExperimentIIIError(
                "STATUS_DOCUMENT_MALFORMED",
                f"{self.stage!r} is not a stage that emits status; expected one of "
                f"{list(STAGES_REQUIRING_STATUS)}",
            )

    def to_dict(self) -> dict[str, Any]:
        validate_blocker_code(self.current_blocker)
        document: dict[str, Any] = {
            "PROCESS_ALIVE": True,
            "STAGE": self.stage,
            "STAGE_STATUS": self.stage_status,
            "TOTAL_UNITS": int(self.total_units),
            "COMPLETED_UNITS": int(self.completed_units),
            "REMAINING_UNITS": int(self.total_units) - int(self.completed_units),
            "CURRENT_UNIT": self.current_unit,
            "LAST_COMPLETED_UNIT": self.last_completed_unit,
            "ELAPSED_TIME": round(time.monotonic() - self._started, 3),
            "LAST_MESSAGE_AT": datetime.now(timezone.utc).isoformat(),
            "LAST_MESSAGE": self.last_message,
            "ERRORS_SEEN": int(self.errors_seen),
            "CURRENT_BLOCKER": self.current_blocker,
            "RETRY_COUNT": int(self.retry_count),
            "POST_STAGE_VALIDATOR_STATUS": self.post_stage_validator_status,
            "NEXT_STAGE": self.next_stage,
            "PROGRAM_STAGE": self.program_stage,
            "III_A_STATUS": self.iii_a_status,
            "III_B_STATUS": self.iii_b_status,
        }
        if self.authority_sha256:
            document["AUTHORITY_SHA256"] = self.authority_sha256
        if self.source_closure:
            document["SOURCE_CLOSURE"] = self.source_closure
        document.update(self.extra)
        validate_status_document(document)
        return document

    def write(self, root: Path | None = None) -> Path:
        """Atomic full rewrite: write ``<name>.tmp`` then rename."""
        document = self.to_dict()
        target = guard_write_path(status_path(self.stage, root), root=root)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(target.name + ".tmp")
        payload = json.dumps(document, indent=2, sort_keys=True, allow_nan=False)
        with temporary.open("w", encoding="utf-8") as stream:
            stream.write(payload + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
        return target


def validate_status_document(document: Mapping[str, Any]) -> None:
    """Schema, domains, blocker validity and the observational-only rule."""
    missing = [name for name in REQUIRED_FIELDS if name not in document]
    if missing:
        raise ExperimentIIIError(
            "STATUS_DOCUMENT_MALFORMED", f"status document is missing {missing}"
        )
    if document["STAGE"] not in STAGES_REQUIRING_STATUS:
        raise ExperimentIIIError(
            "STATUS_DOCUMENT_MALFORMED", f"unknown STAGE {document['STAGE']!r}"
        )
    for field_name, domain in (
        ("STAGE_STATUS", STAGE_STATUS_DOMAIN),
        ("PROGRAM_STAGE", PROGRAM_STAGE_DOMAIN),
        ("III_A_STATUS", III_A_STATUS_DOMAIN),
        ("III_B_STATUS", III_B_STATUS_DOMAIN),
        ("POST_STAGE_VALIDATOR_STATUS", VALIDATOR_STATUS_DOMAIN),
    ):
        if document[field_name] not in domain:
            raise ExperimentIIIError(
                "STATUS_DOCUMENT_MALFORMED",
                f"{field_name}={document[field_name]!r} is outside {list(domain)}",
            )
    validate_blocker_code(document["CURRENT_BLOCKER"])
    if document["STAGE_STATUS"] == "BLOCKED" and document["CURRENT_BLOCKER"] is None:
        raise ExperimentIIIError(
            "STATUS_DOCUMENT_MALFORMED",
            "STAGE_STATUS=BLOCKED requires a CURRENT_BLOCKER",
        )
    if document["REMAINING_UNITS"] != (
        document["TOTAL_UNITS"] - document["COMPLETED_UNITS"]
    ):
        raise ExperimentIIIError(
            "STATUS_DOCUMENT_MALFORMED", "REMAINING_UNITS is inconsistent"
        )
    assert_observational_only(document)
