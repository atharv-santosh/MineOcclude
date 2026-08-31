"""Experiment III canonical row schema and condition enum (authority 4.1, 4.4).

Authority 4.4 keeps physical condition, counterfactual geometry, direct image
evidence, the magenta diagnostic and target eligibility as five separate fields.
They are separate here too, and only ``counterfactual_extent_class`` is a
selector input: ``server_geometric_status``, ``magenta_status``,
``magenta_area_pixels`` and ``rve_condition_score`` are diagnostics and are
rejected as selectors by :func:`assert_not_a_selector`.
"""

from __future__ import annotations

import enum
import hashlib
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from mineocclude.experiment_iii.authority import (
    EPISODE_ID_BLOCK,
    PILOT_EPISODE_IDS,
    PILOT_IDENTITY_IDS,
    PRODUCTION_EPISODE_ID_BASE,
    PRODUCTION_IDENTITY_IDS,
    canonical_sha256,
)
from mineocclude.experiment_iii.errors import ExperimentIIIError
from mineocclude.experiment_iii.namespace import guard_write_path

__all__ = [
    "ConditionId",
    "ExtentClassName",
    "TemporalSlice",
    "VISIBILITY_ROW_FIELDS",
    "DIAGNOSTIC_NEVER_SELECTOR_FIELDS",
    "VisibilityRow",
    "assert_not_a_selector",
    "validate_identity_id",
    "episode_id_for",
    "capture_unit_id",
    "episode_dir_name",
    "write_json_atomic",
    "write_jsonl_atomic",
    "read_jsonl",
]


class ConditionId(enum.Enum):
    """The five frozen conditions of authority 4.1."""

    L0 = "L0"
    L1 = "L1"
    L2 = "L2"
    L3 = "L3"
    L4 = "L4"

    @property
    def wall_present(self) -> bool:
        """Physical block presence. L0 alone has no blocks in the wall cells.

        This is NOT the counterfactual presence flag: the counterfactual
        occluder is present for every condition including L0 (authority 4.5).
        """
        return self is not ConditionId.L0

    @property
    def expected_scene(self) -> str:
        return "NO_WALL" if self is ConditionId.L0 else "NORMAL"

    @property
    def is_anchor(self) -> bool:
        return self in (ConditionId.L0, ConditionId.L4)


CONDITION_ORDER = tuple(ConditionId)


class ExtentClassName(enum.Enum):
    """String domain of ``counterfactual_extent_class`` (authority 4.4)."""

    EXTENT_FULLY_VISIBLE = "EXTENT_FULLY_VISIBLE"
    EXTENT_PARTIAL = "EXTENT_PARTIAL"
    EXTENT_FULLY_OCCLUDED = "EXTENT_FULLY_OCCLUDED"


class TemporalSlice(enum.Enum):
    """The two frozen temporal slices of authority 8.4."""

    PREVIOUS = "PREVIOUS"
    CURRENT = "CURRENT"


#: Authority 4.4, in document order. The row schema is exactly these fields.
VISIBILITY_ROW_FIELDS = (
    "condition_id",
    "wall_present",
    "wall_block_id",
    "counterfactual_extent_class",
    "server_geometric_status",
    "magenta_status",
    "magenta_area_pixels",
    "rve_condition_score",
    "target_eligible",
)

#: Fields the authority marks "never a selector".
DIAGNOSTIC_NEVER_SELECTOR_FIELDS = frozenset(
    {
        "server_geometric_status",
        "magenta_status",
        "magenta_area_pixels",
        "rve_condition_score",
    }
)

_GEOMETRIC_STATUS = frozenset({"visible", "occluded"})
_MAGENTA_STATUS = frozenset({"detected", "not_detected"})


@dataclass(frozen=True)
class VisibilityRow:
    """One row of ``raw/visibility.jsonl`` (authority 8.2, schema 4.4)."""

    model_frame_idx: int
    condition_id: str
    wall_present: bool
    wall_block_id: str
    counterfactual_extent_class: str
    server_geometric_status: str
    magenta_status: str
    magenta_area_pixels: int
    rve_condition_score: float | None
    target_eligible: bool

    def __post_init__(self) -> None:
        if not isinstance(self.model_frame_idx, int) or isinstance(
            self.model_frame_idx, bool
        ):
            raise ExperimentIIIError(
                "TARGET_ROW_MISMATCH", "model_frame_idx must be a plain int"
            )
        if self.model_frame_idx < 0:
            raise ExperimentIIIError(
                "TARGET_ROW_MISMATCH", "model_frame_idx must be non-negative"
            )
        condition = ConditionId(self.condition_id)
        if bool(self.wall_present) is not condition.wall_present:
            raise ExperimentIIIError(
                "WALL_CONDITION_SCENE_MISMATCH",
                f"{condition.value} declares wall_present={self.wall_present}",
            )
        if not isinstance(self.wall_block_id, str) or ":" not in self.wall_block_id:
            raise ExperimentIIIError(
                "WALL_MATERIAL_MISMATCH",
                f"wall_block_id must be a registry ID: {self.wall_block_id!r}",
            )
        ExtentClassName(self.counterfactual_extent_class)
        if self.server_geometric_status not in _GEOMETRIC_STATUS:
            raise ExperimentIIIError(
                "TARGET_ROW_MISMATCH",
                f"server_geometric_status must be one of {sorted(_GEOMETRIC_STATUS)}",
            )
        if self.magenta_status not in _MAGENTA_STATUS:
            raise ExperimentIIIError(
                "TARGET_ROW_MISMATCH",
                f"magenta_status must be one of {sorted(_MAGENTA_STATUS)}",
            )
        if not isinstance(self.magenta_area_pixels, int) or isinstance(
            self.magenta_area_pixels, bool
        ):
            raise ExperimentIIIError(
                "TARGET_ROW_MISMATCH", "magenta_area_pixels must be a plain int"
            )
        if self.rve_condition_score is not None and not isinstance(
            self.rve_condition_score, float
        ):
            raise ExperimentIIIError(
                "TARGET_ROW_MISMATCH", "rve_condition_score must be a float or null"
            )
        if not isinstance(self.target_eligible, bool):
            raise ExperimentIIIError(
                "TARGET_ROW_MISMATCH", "target_eligible must be a bool"
            )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_mapping(cls, row: Mapping[str, Any]) -> "VisibilityRow":
        missing = [
            field
            for field in ("model_frame_idx", *VISIBILITY_ROW_FIELDS)
            if field not in row
        ]
        if missing:
            raise ExperimentIIIError(
                "PROVENANCE_BINDING_MISSING",
                f"visibility row is missing required fields: {missing}",
            )
        return cls(
            model_frame_idx=row["model_frame_idx"],
            condition_id=row["condition_id"],
            wall_present=row["wall_present"],
            wall_block_id=row["wall_block_id"],
            counterfactual_extent_class=row["counterfactual_extent_class"],
            server_geometric_status=row["server_geometric_status"],
            magenta_status=row["magenta_status"],
            magenta_area_pixels=row["magenta_area_pixels"],
            rve_condition_score=row["rve_condition_score"],
            target_eligible=row["target_eligible"],
        )


def assert_not_a_selector(field_name: str) -> None:
    """Refuse a diagnostic field used as a target selector (authority 4.4/4.6)."""
    if field_name in DIAGNOSTIC_NEVER_SELECTOR_FIELDS:
        raise ExperimentIIIError(
            "TARGET_LEGACY_SELECTOR_PRESENT",
            f"{field_name} is a diagnostic and may never select a target row",
        )


# --------------------------------------------------------------------------
# Identity and episode naming (authority 0.4, 8.2)
# --------------------------------------------------------------------------

def validate_identity_id(identity: str, *, allow_pilot: bool = True) -> str:
    if identity in PRODUCTION_IDENTITY_IDS:
        return identity
    if identity in PILOT_IDENTITY_IDS:
        if not allow_pilot:
            raise ExperimentIIIError(
                "COHORT_PILOT_CONTAMINATION",
                f"pilot identity {identity} may not appear in a production input",
            )
        return identity
    raise ExperimentIIIError(
        "COHORT_MATRIX_INCONSISTENT",
        f"{identity!r} is not an Experiment III identity",
    )


def episode_id_for(identity: str, priority_rank: int | None = None) -> int:
    """``86001 + priority_rank`` for production, frozen ids for the pilots."""
    validate_identity_id(identity)
    if identity in PILOT_EPISODE_IDS:
        return PILOT_EPISODE_IDS[identity]
    if priority_rank is None or not isinstance(priority_rank, int):
        raise ExperimentIIIError(
            "COHORT_MATRIX_INCONSISTENT",
            "a production episode id requires an integer priority rank",
        )
    if not 0 <= priority_rank < len(PRODUCTION_IDENTITY_IDS):
        raise ExperimentIIIError(
            "COHORT_MATRIX_INCONSISTENT", f"priority rank out of range: {priority_rank}"
        )
    episode = PRODUCTION_EPISODE_ID_BASE + priority_rank
    low, high = EPISODE_ID_BLOCK
    if not low <= episode <= high:
        raise ExperimentIIIError(
            "PROVENANCE_NAMESPACE_VIOLATION",
            f"episode {episode} is outside the Experiment III block {EPISODE_ID_BLOCK}",
        )
    return episode


def capture_unit_id(identity: str, condition: ConditionId | str) -> str:
    validate_identity_id(identity)
    return f"{identity}__{ConditionId(condition).value}"


def episode_dir_name(episode_id: int, condition: ConditionId | str) -> str:
    low, high = EPISODE_ID_BLOCK
    if not low <= int(episode_id) <= high:
        raise ExperimentIIIError(
            "PROVENANCE_NAMESPACE_VIOLATION",
            f"episode {episode_id} is outside the Experiment III block",
        )
    return f"episode_{int(episode_id)}_{ConditionId(condition).value}"


# --------------------------------------------------------------------------
# Guarded atomic artifact writers
# --------------------------------------------------------------------------

def _atomic_write_bytes(target: Path, payload: bytes) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".tmp")
    with temporary.open("wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, target)
    return target


def write_json_atomic(
    path: os.PathLike[str] | str, value: object, *, root: Path | None = None
) -> str:
    """Write a guarded, namespace-checked JSON artifact; return its SHA-256."""
    target = guard_write_path(path, root=root)
    payload = json.dumps(value, indent=2, sort_keys=True, allow_nan=False).encode(
        "utf-8"
    ) + b"\n"
    _atomic_write_bytes(target, payload)
    return canonical_sha256(value)


def write_jsonl_atomic(
    path: os.PathLike[str] | str,
    rows: Iterable[Mapping[str, Any]],
    *,
    root: Path | None = None,
) -> tuple[str, int]:
    """Write a guarded JSONL artifact; return (sha256 of bytes, row count)."""
    target = guard_write_path(path, root=root)
    materialized = list(rows)
    body = "".join(
        json.dumps(row, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
        for row in materialized
    ).encode("utf-8")
    _atomic_write_bytes(target, body)
    import hashlib

    return hashlib.sha256(body).hexdigest(), len(materialized)


def read_jsonl(path: os.PathLike[str] | str) -> list[dict[str, Any]]:
    text = Path(path).read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]
