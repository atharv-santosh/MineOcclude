"""Resume and recovery (authority 8.3, 8.6).

Two units, kept separable:

    capture unit     (identity x condition)
    extraction unit  (capture_unit_id, layer, temporal_slice) — six per capture

The six extraction units of a capture derive from ONE shared set of 19 forwards,
and the ledger records that shared forward set so a crash never re-runs a
completed capture's forwards. **An extraction failure may not force recapture of
a valid durable capture.**

Extraction lifecycle::

    PLANNED -> RUNNING -> EXTRACTED -> VALIDATED -> DURABLE -> COMPLETE

**Same-spec resume only.** A unit resumes only if its recorded source-capture hash
AND extraction-spec hash both match the current plan; a mismatch is
``EXTRACTION_SOURCE_CAPTURE_DRIFT`` / ``EXTRACTION_SPEC_DRIFT`` and the unit is
discarded and re-planned, never silently reused. Units already ``COMPLETE`` are
skipped without reading their bytes; ``DURABLE`` units are re-sealed; ``EXTRACTED``
units are re-validated rather than re-extracted.

The hash-chain ledger and atomic-store concepts are the authorized reuse from
``regime_a_execution.py``, adapted to these units.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from mineocclude.experiment_iii.authority import canonical_sha256
from mineocclude.experiment_iii.errors import ExperimentIIIError
from mineocclude.experiment_iii.extraction import SELECTED_LAYERS
from mineocclude.experiment_iii.namespace import guard_write_path
from mineocclude.experiment_iii.schema import TemporalSlice

__all__ = [
    "CAPTURE_STATES",
    "EXTRACTION_STATES",
    "TERMINAL_STATE",
    "ExtractionUnit",
    "HashChainLedger",
    "ExtractionPlan",
    "plan_extraction_units",
    "resume_decision",
]

CAPTURE_STATES = (
    "PLANNED",
    "RUNNING",
    "CAPTURED",
    "VALIDATED",
    "DURABLE",
    "COMPLETE",
)
#: Authority 8.6.
EXTRACTION_STATES = (
    "PLANNED",
    "RUNNING",
    "EXTRACTED",
    "VALIDATED",
    "DURABLE",
    "COMPLETE",
)
TERMINAL_STATE = "COMPLETE"

_ORDER = {name: index for index, name in enumerate(EXTRACTION_STATES)}


@dataclass(frozen=True)
class ExtractionUnit:
    """One persisted array's identity and its binding hashes."""

    capture_unit_id: str
    layer: int
    temporal_slice: str
    source_capture_hash: str
    extraction_spec_hash: str

    @property
    def unit_id(self) -> str:
        return f"{self.capture_unit_id}/layer_{self.layer:02d}/{self.temporal_slice}"

    def as_dict(self) -> dict[str, Any]:
        return {
            "unit_id": self.unit_id,
            "capture_unit_id": self.capture_unit_id,
            "layer": self.layer,
            "temporal_slice": self.temporal_slice,
            "source_capture_hash": self.source_capture_hash,
            "extraction_spec_hash": self.extraction_spec_hash,
        }


def plan_extraction_units(
    capture_unit_id: str,
    *,
    source_capture_hash: str,
    extraction_spec_hash: str,
    layers: Sequence[int] = SELECTED_LAYERS,
) -> list[ExtractionUnit]:
    """The six extraction units of one capture."""
    units = [
        ExtractionUnit(
            capture_unit_id=capture_unit_id,
            layer=int(layer),
            temporal_slice=name.value,
            source_capture_hash=source_capture_hash,
            extraction_spec_hash=extraction_spec_hash,
        )
        for layer in layers
        for name in TemporalSlice
    ]
    if len(units) != len(layers) * len(TemporalSlice):
        raise ExperimentIIIError(
            "EXTRACTION_INVENTORY_INCOMPLETE", "extraction plan is incomplete"
        )
    return units


class HashChainLedger:
    """Append-only, hash-chained state ledger. The only control-flow input."""

    def __init__(self, path: Path | None = None, *, root: Path | None = None):
        self._path = Path(path) if path is not None else None
        self._root = root
        self.records: list[dict[str, Any]] = []
        if self._path is not None and self._path.is_file():
            self._load()

    def _load(self) -> None:
        for line in self._path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                self.records.append(json.loads(line))
        self.verify_chain()

    @property
    def head(self) -> str:
        return self.records[-1]["record_hash"] if self.records else "0" * 64

    def append(self, unit_id: str, state: str, **fields: Any) -> dict[str, Any]:
        if state not in EXTRACTION_STATES and state not in CAPTURE_STATES:
            raise ExperimentIIIError(
                "EXTRACTION_SPEC_DRIFT", f"unknown ledger state {state!r}"
            )
        body = {
            "sequence": len(self.records),
            "unit_id": unit_id,
            "state": state,
            "previous_hash": self.head,
            **fields,
        }
        body["record_hash"] = canonical_sha256(body)
        self.records.append(body)
        if self._path is not None:
            target = guard_write_path(self._path, root=self._root)
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("a", encoding="utf-8") as stream:
                stream.write(
                    json.dumps(body, sort_keys=True, separators=(",", ":")) + "\n"
                )
                stream.flush()
                os.fsync(stream.fileno())
        return body

    def verify_chain(self) -> None:
        previous = "0" * 64
        for index, record in enumerate(self.records):
            body = {k: v for k, v in record.items() if k != "record_hash"}
            if body.get("previous_hash") != previous:
                raise ExperimentIIIError(
                    "PROVENANCE_AUTHORITY_DRIFT",
                    f"ledger chain broken at record {index}",
                )
            if canonical_sha256(body) != record["record_hash"]:
                raise ExperimentIIIError(
                    "PROVENANCE_AUTHORITY_DRIFT",
                    f"ledger record {index} has been modified",
                )
            previous = record["record_hash"]

    def last_state(self, unit_id: str) -> str | None:
        for record in reversed(self.records):
            if record["unit_id"] == unit_id:
                return str(record["state"])
        return None

    def binding(self, unit_id: str) -> dict[str, Any]:
        """The most recent recorded source/spec hashes for a unit."""
        for record in reversed(self.records):
            if record["unit_id"] == unit_id and "source_capture_hash" in record:
                return {
                    "source_capture_hash": record["source_capture_hash"],
                    "extraction_spec_hash": record.get("extraction_spec_hash"),
                }
        return {}

    def complete_units(self) -> set[str]:
        return {
            record["unit_id"]
            for record in self.records
            if record["state"] == TERMINAL_STATE
        }


def resume_decision(unit: ExtractionUnit, ledger: HashChainLedger) -> dict[str, Any]:
    """What to do with one extraction unit on restart.

    Same-spec only: a source-capture or extraction-spec mismatch discards and
    re-plans the unit rather than reusing it.
    """
    state = ledger.last_state(unit.unit_id)
    recorded = ledger.binding(unit.unit_id)

    if state is not None and recorded:
        if recorded.get("source_capture_hash") != unit.source_capture_hash:
            return {
                "action": "DISCARD_AND_REPLAN",
                "blocker": "EXTRACTION_SOURCE_CAPTURE_DRIFT",
                "state": state,
                "reason": "recorded source-capture hash does not match the plan",
                "forces_recapture": False,
            }
        if recorded.get("extraction_spec_hash") != unit.extraction_spec_hash:
            return {
                "action": "DISCARD_AND_REPLAN",
                "blocker": "EXTRACTION_SPEC_DRIFT",
                "state": state,
                "reason": "recorded extraction-spec hash does not match the plan",
                "forces_recapture": False,
            }

    if state is None:
        return {"action": "EXTRACT", "state": None, "blocker": None}
    if state == TERMINAL_STATE:
        return {
            "action": "SKIP",
            "state": state,
            "blocker": None,
            "reads_bytes": False,
        }
    if state == "DURABLE":
        return {"action": "RESEAL", "state": state, "blocker": None}
    if state == "EXTRACTED":
        return {"action": "REVALIDATE", "state": state, "blocker": None}
    if state == "VALIDATED":
        return {"action": "PUBLISH", "state": state, "blocker": None}
    return {"action": "EXTRACT", "state": state, "blocker": None}


@dataclass
class ExtractionPlan:
    """Plans and resumes extraction without ever forcing a recapture."""

    ledger: HashChainLedger
    units: list[ExtractionUnit] = field(default_factory=list)

    def add_capture(
        self,
        capture_unit_id: str,
        *,
        source_capture_hash: str,
        extraction_spec_hash: str,
    ) -> None:
        self.units.extend(
            plan_extraction_units(
                capture_unit_id,
                source_capture_hash=source_capture_hash,
                extraction_spec_hash=extraction_spec_hash,
            )
        )

    def resume(self) -> dict[str, list[str]]:
        """Group the units by the action a restart would take."""
        actions: dict[str, list[str]] = {}
        for unit in self.units:
            decision = resume_decision(unit, self.ledger)
            actions.setdefault(decision["action"], []).append(unit.unit_id)
        return actions

    def captures_requiring_forwards(self) -> list[str]:
        """Captures with at least one unit still needing the shared forward set.

        A capture whose six units are all complete needs no forwards; a capture
        with any unit still to extract needs its ONE shared set of 19 forwards,
        not one set per unit.
        """
        needed: list[str] = []
        for unit in self.units:
            decision = resume_decision(unit, self.ledger)
            if decision["action"] in {"EXTRACT", "DISCARD_AND_REPLAN"}:
                if unit.capture_unit_id not in needed:
                    needed.append(unit.capture_unit_id)
        return needed
