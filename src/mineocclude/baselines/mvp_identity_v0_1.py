"""Person D Step 6.1: bind to Person C's real, accepted 66-trajectory MVP identity.

Person C's real MVP collection lives only on ``role/person-c-data`` (this
branch never merges it) at commit ``PERSON_C_MVP_COLLECTION_COMMIT`` --
the same commit already trusted elsewhere in this package as the
ten-pilot-expansion source authority. Two real, independently-produced
artifacts on that branch jointly define and evidence the 66-trajectory
MVP identity:

* ``configs/collection/mvp_matrix.csv`` -- the planned matrix (66 rows),
  with an explicit ``set`` column classifying each row as one of
  ``core`` (48), ``sentinel`` (6), ``nowall`` (6), or ``nosheep`` (6).
* ``data/autonomous/pilot_production_ledger.json`` -- the real capture
  ledger (66 cells), each recording the real ``accepted_episode`` and
  ``trajectory_id`` that fulfilled one planned cell.

Neither file alone proves acceptance: the matrix is a plan, and the
ledger's cells carry no ``set`` label of their own. This module joins
them on the full parameter tuple every planned cell is unique on
(layout, scene, v, q, hidden-frame duration, max ticks) and requires an
exact bijection -- if any planned cell lacks a real accepted capture, or
any real capture doesn't correspond to a planned cell, that is reported
as an explicit shortfall, never silently dropped or invented (roadmap
Step 6.1 pass check: "shortfalls are explicit").

This module never fits a baseline, never computes a metric, and never
reads a U4 artifact. It only reconciles Person D's accepted-MVP-identity
binding against Person C's exact real bytes.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
from collections import Counter
from dataclasses import dataclass, field
from typing import Any


class MvpIdentityError(ValueError):
    """Raised when the real Person C MVP identity does not reconcile."""


#: Person C's real 66-trajectory MVP collection branch/commit -- the sole
#: authority for the frozen byte identities below. Already trusted
#: elsewhere in this package (see ``production_fold_contract_v0_1``'s
#: ``source_identities.person_c_commit``) as the tip of person-c-data.
PERSON_C_SOURCE_BRANCH = "role/person-c-data"
PERSON_C_MVP_COLLECTION_COMMIT = "c6bff25b5ef4f5fdb0e1ef0ce0d22e3f8b5e4960"

FROZEN_MVP_MATRIX_PATH = "configs/collection/mvp_matrix.csv"
FROZEN_MVP_MATRIX_SHA256 = (
    "5eebbbd9f5950184b6c11a17722295c970e37a460e3963bed3b9390b99c1ac17"
)
FROZEN_MVP_MATRIX_BYTE_SIZE = 3_753

FROZEN_PILOT_LEDGER_PATH = "data/autonomous/pilot_production_ledger.json"
FROZEN_PILOT_LEDGER_SHA256 = (
    "8045a0e2eeb823a3f20da996eef546a4621a3fc578202947f1618480554472f9"
)
FROZEN_PILOT_LEDGER_BYTE_SIZE = 99_797

REQUIRED_LAYOUT_IDS = tuple(f"layout_0{i}" for i in range(1, 7))
REQUIRED_SET_COUNTS = {"core": 48, "sentinel": 6, "nowall": 6, "nosheep": 6}
REQUIRED_TRAJECTORY_COUNT = 66
REQUIRED_ROWS_PER_LAYOUT = REQUIRED_TRAJECTORY_COUNT // len(REQUIRED_LAYOUT_IDS)

MVP_IDENTITY_MANIFEST_SCHEMA_ID = "person-d-phase6-step6-1-mvp-identity-manifest"
MVP_IDENTITY_MANIFEST_SCHEMA_VERSION = "1.0"

_MATRIX_REQUIRED_COLUMNS = (
    "set",
    "scene",
    "layout_id",
    "v",
    "q",
    "hidden_frames",
    "max_ticks",
    "warmup",
    "episode_id",
    "seed",
    "collection_order",
)


@dataclass(frozen=True)
class MvpTrajectoryIdentity:
    """One real, accepted MVP trajectory bound to its planned cell."""

    set_name: str
    layout_id: str
    trajectory_id: str
    accepted_episode: int
    hidden_frames: int
    v: float
    q: float


@dataclass(frozen=True)
class MvpCountReconciliation:
    """Explicit required-vs-actual counts; never silently reconciled."""

    set_counts: dict
    layout_counts: dict
    total_count: int
    shortfalls: tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_complete(self) -> bool:
        return not self.shortfalls


def _fail(message: str) -> None:
    raise MvpIdentityError(message)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _join_key(
    *, layout_id: Any, scene: Any, v: Any, q: Any, hidden_frames: Any, max_ticks: Any
) -> tuple[Any, ...]:
    return (str(layout_id), str(scene), float(v), float(q), int(hidden_frames), int(max_ticks))


def _parse_mvp_matrix_rows(payload: bytes) -> list[dict[str, str]]:
    text = payload.decode("utf-8")
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None or tuple(reader.fieldnames) != _MATRIX_REQUIRED_COLUMNS:
        _fail(f"MVP matrix columns changed: {reader.fieldnames!r}.")
    rows = list(reader)
    if len(rows) != REQUIRED_TRAJECTORY_COUNT:
        _fail(f"MVP matrix row count changed: expected 66, found {len(rows)}.")
    return rows


def validate_mvp_matrix_bytes(payload: bytes) -> list[dict[str, str]]:
    """Validate the literal frozen matrix bytes and parse its 66 planned cells."""

    if not isinstance(payload, bytes):
        _fail("MVP matrix payload must be bytes.")
    if len(payload) != FROZEN_MVP_MATRIX_BYTE_SIZE:
        _fail("MVP matrix literal byte size changed.")
    if _sha256(payload) != FROZEN_MVP_MATRIX_SHA256:
        _fail("MVP matrix literal SHA-256 changed.")
    return _parse_mvp_matrix_rows(payload)


def _validate_ledger_cells(cells: Any) -> list[dict[str, Any]]:
    if not isinstance(cells, list) or len(cells) != REQUIRED_TRAJECTORY_COUNT:
        _fail(f"Pilot ledger cell count changed: expected 66, found {len(cells) if isinstance(cells, list) else 'n/a'}.")
    for cell in cells:
        if not isinstance(cell, dict) or cell.get("accepted_episode") is None:
            _fail("Pilot ledger has a cell with no accepted episode -- real acceptance is incomplete.")
    return cells


def validate_pilot_ledger_bytes(payload: bytes) -> list[dict[str, Any]]:
    """Validate the literal frozen ledger bytes and parse its 66 real cells."""

    if not isinstance(payload, bytes):
        _fail("Pilot ledger payload must be bytes.")
    if len(payload) != FROZEN_PILOT_LEDGER_BYTE_SIZE:
        _fail("Pilot ledger literal byte size changed.")
    if _sha256(payload) != FROZEN_PILOT_LEDGER_SHA256:
        _fail("Pilot ledger literal SHA-256 changed.")
    try:
        cells = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise MvpIdentityError("Pilot ledger payload is not strict UTF-8 JSON.") from error
    return _validate_ledger_cells(cells)


def _accepted_trajectory_id(cell: dict[str, Any]) -> str:
    accepted_episode = cell["accepted_episode"]
    accepted_attempts = [
        attempt
        for attempt in cell.get("attempts", ())
        if attempt.get("accepted") and attempt.get("episode_id") == accepted_episode
    ]
    if len(accepted_attempts) != 1:
        _fail(
            f"Pilot ledger cell for accepted_episode={accepted_episode!r} does not have "
            "exactly one matching accepted attempt."
        )
    trajectory_id = accepted_attempts[0].get("trajectory_id")
    if not isinstance(trajectory_id, str) or not trajectory_id:
        _fail(f"Pilot ledger accepted attempt for episode {accepted_episode!r} has no trajectory_id.")
    return trajectory_id


def join_matrix_and_ledger(
    matrix_rows: list[dict[str, str]], ledger_cells: list[dict[str, Any]]
) -> list[MvpTrajectoryIdentity]:
    """Bijectively join planned cells to real accepted captures; fail closed on any gap."""

    matrix_by_key = {}
    for row in matrix_rows:
        key = _join_key(
            layout_id=row["layout_id"],
            scene=row["scene"],
            v=row["v"],
            q=row["q"],
            hidden_frames=row["hidden_frames"],
            max_ticks=row["max_ticks"],
        )
        if key in matrix_by_key:
            _fail(f"MVP matrix key is not unique: {key!r}.")
        matrix_by_key[key] = row

    ledger_by_key = {}
    for cell in ledger_cells:
        cell_fields = cell["cell"]
        key = _join_key(
            layout_id=cell_fields["layout"],
            scene=cell_fields["scene"],
            v=cell_fields["v"],
            q=cell_fields["q"],
            hidden_frames=cell_fields["hidden"],
            max_ticks=cell_fields["max_ticks"],
        )
        if key in ledger_by_key:
            _fail(f"Pilot ledger key is not unique: {key!r}.")
        ledger_by_key[key] = cell

    matrix_only = sorted(set(matrix_by_key) - set(ledger_by_key))
    ledger_only = sorted(set(ledger_by_key) - set(matrix_by_key))
    if matrix_only or ledger_only:
        _fail(
            "MVP matrix and pilot ledger do not bijectively reconcile: "
            f"{len(matrix_only)} planned cell(s) have no real accepted capture "
            f"({matrix_only!r}), {len(ledger_only)} real capture(s) match no planned "
            f"cell ({ledger_only!r})."
        )

    identities = []
    for key in sorted(matrix_by_key):
        row = matrix_by_key[key]
        cell = ledger_by_key[key]
        identities.append(
            MvpTrajectoryIdentity(
                set_name=row["set"],
                layout_id=row["layout_id"],
                trajectory_id=_accepted_trajectory_id(cell),
                accepted_episode=cell["accepted_episode"],
                hidden_frames=int(row["hidden_frames"]),
                v=float(row["v"]),
                q=float(row["q"]),
            )
        )
    return identities


def reconcile_mvp_counts(identities: list[MvpTrajectoryIdentity]) -> MvpCountReconciliation:
    """Compute required-vs-actual counts; report every shortfall explicitly."""

    set_counts = dict(Counter(identity.set_name for identity in identities))
    layout_counts = dict(Counter(identity.layout_id for identity in identities))

    shortfalls: list[str] = []
    for set_name, required in REQUIRED_SET_COUNTS.items():
        actual = set_counts.get(set_name, 0)
        if actual != required:
            shortfalls.append(f"set {set_name!r}: required {required}, found {actual}")
    for unexpected_set in set(set_counts) - set(REQUIRED_SET_COUNTS):
        shortfalls.append(f"unexpected set {unexpected_set!r}: found {set_counts[unexpected_set]}")
    for layout_id in REQUIRED_LAYOUT_IDS:
        actual = layout_counts.get(layout_id, 0)
        if actual != REQUIRED_ROWS_PER_LAYOUT:
            shortfalls.append(
                f"layout {layout_id!r}: required {REQUIRED_ROWS_PER_LAYOUT}, found {actual}"
            )
    for unexpected_layout in set(layout_counts) - set(REQUIRED_LAYOUT_IDS):
        shortfalls.append(f"unexpected layout {unexpected_layout!r}: found {layout_counts[unexpected_layout]}")
    if len(identities) != REQUIRED_TRAJECTORY_COUNT:
        shortfalls.append(
            f"total accepted trajectory count: required {REQUIRED_TRAJECTORY_COUNT}, "
            f"found {len(identities)}"
        )

    return MvpCountReconciliation(
        set_counts=set_counts,
        layout_counts=layout_counts,
        total_count=len(identities),
        shortfalls=tuple(shortfalls),
    )


def build_mvp_input_manifest(
    matrix_payload: bytes, ledger_payload: bytes
) -> dict[str, Any]:
    """Build Person D's Step 6.1 MVP input manifest: identity hash + count table.

    Fails closed (raises ``MvpIdentityError``) if either input's literal
    bytes have drifted from the frozen Person C identity, or if the
    matrix/ledger join is not an exact bijection. Once joined, the count
    table is reported however it comes out -- ``reconcile_mvp_counts``
    never raises, so a real, honest shortfall (should one ever appear if
    Person C's collection changes) is surfaced in the manifest rather
    than blocking manifest production.
    """

    matrix_rows = validate_mvp_matrix_bytes(matrix_payload)
    ledger_cells = validate_pilot_ledger_bytes(ledger_payload)
    identities = join_matrix_and_ledger(matrix_rows, ledger_cells)
    reconciliation = reconcile_mvp_counts(identities)

    manifest = {
        "schema_id": MVP_IDENTITY_MANIFEST_SCHEMA_ID,
        "schema_version": MVP_IDENTITY_MANIFEST_SCHEMA_VERSION,
        "source_branch": PERSON_C_SOURCE_BRANCH,
        "source_commit": PERSON_C_MVP_COLLECTION_COMMIT,
        "source_mvp_matrix_path": FROZEN_MVP_MATRIX_PATH,
        "source_mvp_matrix_sha256": FROZEN_MVP_MATRIX_SHA256,
        "source_pilot_ledger_path": FROZEN_PILOT_LEDGER_PATH,
        "source_pilot_ledger_sha256": FROZEN_PILOT_LEDGER_SHA256,
        "required_set_counts": dict(REQUIRED_SET_COUNTS),
        "required_trajectory_count": REQUIRED_TRAJECTORY_COUNT,
        "count_table": {
            "set_counts": reconciliation.set_counts,
            "layout_counts": reconciliation.layout_counts,
            "total_count": reconciliation.total_count,
        },
        "shortfalls": list(reconciliation.shortfalls),
        "reconciliation_complete": reconciliation.is_complete,
        "trajectories": [
            {
                "set": identity.set_name,
                "layout_id": identity.layout_id,
                "trajectory_id": identity.trajectory_id,
                "accepted_episode": identity.accepted_episode,
                "hidden_frames": identity.hidden_frames,
                "v": identity.v,
                "q": identity.q,
            }
            for identity in identities
        ],
    }
    return manifest


__all__ = [
    "FROZEN_MVP_MATRIX_PATH",
    "FROZEN_MVP_MATRIX_SHA256",
    "FROZEN_PILOT_LEDGER_PATH",
    "FROZEN_PILOT_LEDGER_SHA256",
    "MVP_IDENTITY_MANIFEST_SCHEMA_ID",
    "MVP_IDENTITY_MANIFEST_SCHEMA_VERSION",
    "PERSON_C_MVP_COLLECTION_COMMIT",
    "PERSON_C_SOURCE_BRANCH",
    "REQUIRED_LAYOUT_IDS",
    "REQUIRED_SET_COUNTS",
    "REQUIRED_TRAJECTORY_COUNT",
    "MvpCountReconciliation",
    "MvpIdentityError",
    "MvpTrajectoryIdentity",
    "build_mvp_input_manifest",
    "join_matrix_and_ledger",
    "reconcile_mvp_counts",
    "validate_mvp_matrix_bytes",
    "validate_pilot_ledger_bytes",
]
