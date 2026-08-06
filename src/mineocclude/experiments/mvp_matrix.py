"""Encode the locked 66-cell MVP matrix and reconcile it against acceptance.

Step 7.2 makes queue completeness machine-checkable. Every planned cell is tied
to its layout, speed, q, hidden duration, seed, and set membership, and every
cell ends in exactly one reconciliation state with a named owner.

This module never invents an accepted cell. A cell with no acceptance evidence
is published as a shortfall.
"""

from __future__ import annotations

import csv
import hashlib
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from io import StringIO
from pathlib import Path
from typing import Any

MATRIX_SCHEMA_VERSION = "person-a-mvp-expected-matrix-v0.1"

EXPECTED_CELL_COUNT = 66

# Person C's collection-set vocabulary mapped onto the roadmap's cell groups.
SET_TO_GROUP: Mapping[str, str] = {
    "core": "core_regime_a",
    "nowall": "no_wall_visible_control",
    "nosheep": "occluder_only_no_sheep_control",
    "sentinel": "context_sentinel",
}

EXPECTED_GROUP_COUNTS: Mapping[str, int] = {
    "core_regime_a": 48,
    "no_wall_visible_control": 6,
    "occluder_only_no_sheep_control": 6,
    "context_sentinel": 6,
}

REQUIRED_COLUMNS: tuple[str, ...] = (
    "collection_order",
    "set",
    "scene",
    "layout_id",
    "v",
    "q",
    "hidden_frames",
    "max_ticks",
    "warmup_ticks",
    "episode_id",
    "seed",
)


class CellState(str, Enum):
    """The only reconciliation states a planned cell may end in."""

    ACCEPTED = "accepted"
    EXCLUDED = "excluded"
    RECOLLECTION_PENDING = "recollection_pending"
    MISSING = "missing"


class MatrixErrorCode(str, Enum):
    """Stable reasons an expected matrix cannot be built or reconciled."""

    MISSING_FILE = "missing_file"
    MALFORMED_MATRIX = "malformed_matrix"
    MISSING_COLUMN = "missing_column"
    DUPLICATE_CELL = "duplicate_cell"
    CARDINALITY_MISMATCH = "cardinality_mismatch"
    UNKNOWN_SET = "unknown_set"
    HASH_MISMATCH = "hash_mismatch"
    UNKNOWN_ACCEPTED_CELL = "unknown_accepted_cell"


class MatrixError(ValueError):
    """Raised when the expected MVP matrix is not trustworthy."""

    def __init__(self, code: MatrixErrorCode, message: str) -> None:
        self.code = code
        super().__init__(f"{code.value}: {message}")


def _fail(code: MatrixErrorCode, message: str) -> None:
    raise MatrixError(code, message)


@dataclass(frozen=True)
class ExpectedCell:
    """One planned MVP trajectory tied to its complete condition identity."""

    cell_id: str
    collection_order: int
    group: str
    collection_set: str
    scene: str
    layout_id: str
    v: float
    q: float
    hidden_frames: int
    max_ticks: int
    warmup_ticks: int
    episode_id: int
    seed: int

    @property
    def is_control(self) -> bool:
        return self.group in {
            "no_wall_visible_control",
            "occluder_only_no_sheep_control",
        }

    def to_document(self) -> dict[str, Any]:
        return {
            "cell_id": self.cell_id,
            "collection_order": self.collection_order,
            "group": self.group,
            "collection_set": self.collection_set,
            "scene": self.scene,
            "layout_id": self.layout_id,
            "v": self.v,
            "q": self.q,
            "hidden_frames": self.hidden_frames,
            "max_ticks": self.max_ticks,
            "warmup_ticks": self.warmup_ticks,
            "episode_id": self.episode_id,
            "seed": self.seed,
            "is_control": self.is_control,
        }


def _require_column(row: Mapping[str, str], name: str) -> str:
    value = row.get(name)
    if value is None or value == "":
        _fail(
            MatrixErrorCode.MISSING_COLUMN,
            f"expected-matrix row is missing column {name!r}",
        )
    return str(value)


def _int(value: str, name: str) -> int:
    try:
        return int(value)
    except ValueError:
        _fail(
            MatrixErrorCode.MALFORMED_MATRIX,
            f"column {name!r} is not an integer: {value!r}",
        )
        raise  # pragma: no cover


def _float(value: str, name: str) -> float:
    try:
        return float(value)
    except ValueError:
        _fail(
            MatrixErrorCode.MALFORMED_MATRIX,
            f"column {name!r} is not a number: {value!r}",
        )
        raise  # pragma: no cover


def parse_expected_matrix(text: str) -> tuple[ExpectedCell, ...]:
    """Parse Person C's episode matrix into typed expected cells."""

    reader = csv.DictReader(StringIO(text))
    if reader.fieldnames is None:
        _fail(MatrixErrorCode.MALFORMED_MATRIX, "expected matrix has no header")
    missing = [
        name for name in REQUIRED_COLUMNS if name not in (reader.fieldnames or ())
    ]
    if missing:
        _fail(
            MatrixErrorCode.MISSING_COLUMN,
            "expected matrix is missing columns: " + ", ".join(missing),
        )
    cells: list[ExpectedCell] = []
    for row in reader:
        collection_set = _require_column(row, "set")
        group = SET_TO_GROUP.get(collection_set)
        if group is None:
            _fail(
                MatrixErrorCode.UNKNOWN_SET,
                f"collection set {collection_set!r} has no frozen cell group",
            )
        layout = _require_column(row, "layout_id")
        episode = _int(_require_column(row, "episode_id"), "episode_id")
        cells.append(
            ExpectedCell(
                cell_id=f"{layout}_ep{episode}",
                collection_order=_int(
                    _require_column(row, "collection_order"), "collection_order"
                ),
                group=group,
                collection_set=collection_set,
                scene=_require_column(row, "scene"),
                layout_id=layout,
                v=_float(_require_column(row, "v"), "v"),
                q=_float(_require_column(row, "q"), "q"),
                hidden_frames=_int(
                    _require_column(row, "hidden_frames"), "hidden_frames"
                ),
                max_ticks=_int(_require_column(row, "max_ticks"), "max_ticks"),
                warmup_ticks=_int(
                    _require_column(row, "warmup_ticks"), "warmup_ticks"
                ),
                episode_id=episode,
                seed=_int(_require_column(row, "seed"), "seed"),
            )
        )
    _require_unique(cells)
    return tuple(cells)


def _require_unique(cells: Sequence[ExpectedCell]) -> None:
    ids = [cell.cell_id for cell in cells]
    if len(set(ids)) != len(ids):
        _fail(
            MatrixErrorCode.DUPLICATE_CELL,
            "expected matrix contains duplicate cell identities",
        )
    orders = [cell.collection_order for cell in cells]
    if len(set(orders)) != len(orders):
        _fail(
            MatrixErrorCode.DUPLICATE_CELL,
            "expected matrix contains duplicate collection orders",
        )
    episodes = [cell.episode_id for cell in cells]
    if len(set(episodes)) != len(episodes):
        _fail(
            MatrixErrorCode.DUPLICATE_CELL,
            "expected matrix contains duplicate episode identities",
        )


def load_expected_matrix(
    path: Path | str,
    *,
    expected_sha256: str | None = None,
    expected_cell_count: int = EXPECTED_CELL_COUNT,
) -> tuple[tuple[ExpectedCell, ...], str]:
    """Load, hash-verify, and cardinality-check the expected MVP matrix."""

    source = Path(path)
    if not source.is_file():
        _fail(
            MatrixErrorCode.MISSING_FILE,
            f"expected matrix is absent: {source.as_posix()}",
        )
    raw = source.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if expected_sha256 is not None and digest != expected_sha256:
        _fail(
            MatrixErrorCode.HASH_MISMATCH,
            f"expected matrix digest {digest} != declared {expected_sha256}",
        )
    cells = parse_expected_matrix(raw.decode("utf-8"))
    if len(cells) != expected_cell_count:
        _fail(
            MatrixErrorCode.CARDINALITY_MISMATCH,
            f"expected matrix has {len(cells)} cells, not {expected_cell_count}",
        )
    counts = _group_counts(cells)
    if counts != dict(EXPECTED_GROUP_COUNTS):
        _fail(
            MatrixErrorCode.CARDINALITY_MISMATCH,
            f"cell group counts {counts} differ from the frozen plan "
            f"{dict(EXPECTED_GROUP_COUNTS)}",
        )
    return cells, digest


def _group_counts(cells: Iterable[ExpectedCell]) -> dict[str, int]:
    counts = {name: 0 for name in EXPECTED_GROUP_COUNTS}
    for cell in cells:
        counts[cell.group] = counts.get(cell.group, 0) + 1
    return dict(sorted(counts.items()))


@dataclass(frozen=True)
class AcceptanceEvidence:
    """One cell's acceptance state as published by its owning role."""

    cell_id: str
    state: CellState
    owner: str
    evidence_path: str | None = None
    evidence_sha256: str | None = None
    detail: str | None = None

    def to_document(self) -> dict[str, Any]:
        return {
            "cell_id": self.cell_id,
            "state": self.state.value,
            "owner": self.owner,
            "evidence_path": self.evidence_path,
            "evidence_sha256": self.evidence_sha256,
            "detail": self.detail,
        }


def reconcile_matrix(
    expected: Sequence[ExpectedCell],
    acceptance: Sequence[AcceptanceEvidence],
    *,
    default_missing_owner: str = "person_c_data",
    default_missing_detail: str = (
        "No per-trajectory accepted handoff bundle has been published to "
        "Person A for this cell."
    ),
) -> dict[str, Any]:
    """Compare the expected cells to published acceptance and name every gap."""

    expected_by_id = {cell.cell_id: cell for cell in expected}
    seen: dict[str, AcceptanceEvidence] = {}
    for record in acceptance:
        if record.cell_id not in expected_by_id:
            _fail(
                MatrixErrorCode.UNKNOWN_ACCEPTED_CELL,
                f"acceptance evidence names unplanned cell {record.cell_id!r}",
            )
        if record.cell_id in seen:
            _fail(
                MatrixErrorCode.DUPLICATE_CELL,
                f"cell {record.cell_id!r} has more than one acceptance record",
            )
        seen[record.cell_id] = record

    rows: list[dict[str, Any]] = []
    for cell in expected:
        record = seen.get(cell.cell_id)
        if record is None:
            record = AcceptanceEvidence(
                cell_id=cell.cell_id,
                state=CellState.MISSING,
                owner=default_missing_owner,
                detail=default_missing_detail,
            )
        rows.append({**cell.to_document(), **record.to_document()})

    counts = {state.value: 0 for state in CellState}
    for row in rows:
        counts[row["state"]] += 1
    shortfall = [row for row in rows if row["state"] != CellState.ACCEPTED.value]
    accepted_by_group = _accepted_by_group(rows)
    return {
        "schema_version": MATRIX_SCHEMA_VERSION,
        "step": "7.2",
        "expected_cell_count": len(expected),
        "accepted_cell_count": counts[CellState.ACCEPTED.value],
        "state_counts": counts,
        "expected_group_counts": _group_counts(expected),
        "accepted_group_counts": accepted_by_group,
        "complete": counts[CellState.ACCEPTED.value] == len(expected),
        "every_cell_has_a_state_and_owner": all(
            row["state"] and row["owner"] for row in rows
        ),
        "shortfall_count": len(shortfall),
        "shortfall": shortfall,
        "shortfall_owners": sorted({row["owner"] for row in shortfall}),
        "cells": rows,
        "no_data_invented": True,
    }


def _accepted_by_group(rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counts = {name: 0 for name in EXPECTED_GROUP_COUNTS}
    for row in rows:
        if row["state"] == CellState.ACCEPTED.value:
            counts[row["group"]] = counts.get(row["group"], 0) + 1
    return dict(sorted(counts.items()))


def acceptance_from_handoff_bundles(
    bundles: Sequence[Mapping[str, Any]],
    *,
    owner: str = "person_c_data",
) -> tuple[AcceptanceEvidence, ...]:
    """Turn received per-trajectory handoff bundles into acceptance records."""

    records: list[AcceptanceEvidence] = []
    for bundle in bundles:
        cell_id = bundle.get("trajectory_id")
        if not isinstance(cell_id, str) or not cell_id:
            _fail(
                MatrixErrorCode.MALFORMED_MATRIX,
                "handoff bundle entries require a trajectory_id",
            )
        records.append(
            AcceptanceEvidence(
                cell_id=cell_id,
                state=CellState.ACCEPTED,
                owner=owner,
                evidence_path=bundle.get("bundle_manifest"),
                evidence_sha256=bundle.get("bundle_manifest_sha256"),
                detail="Per-trajectory accepted handoff bundle received.",
            )
        )
    return tuple(records)


__all__ = [
    "EXPECTED_CELL_COUNT",
    "EXPECTED_GROUP_COUNTS",
    "MATRIX_SCHEMA_VERSION",
    "SET_TO_GROUP",
    "AcceptanceEvidence",
    "CellState",
    "ExpectedCell",
    "MatrixError",
    "MatrixErrorCode",
    "acceptance_from_handoff_bundles",
    "load_expected_matrix",
    "parse_expected_matrix",
    "reconcile_matrix",
]
