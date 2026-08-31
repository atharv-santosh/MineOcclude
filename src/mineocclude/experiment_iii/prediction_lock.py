"""Prospective prediction locking (authority 8.8, test A.27).

Held-out predictions are emitted and hash-sealed **before** any final statistical
summary is opened. The lock is what makes the analysis prospective in practice:
once sealed, a feature block cannot be changed without the lock detecting it, and
no statistic may be computed before the seal exists.

There must be exactly **one** held-out prediction per
``(identity, condition, row, model)`` cell. A duplicate is
``PREDICTION_DUPLICATE_CELL``; computing a statistic first is
``PREDICTION_LOCK_MISSING``; sealing after statistics exist is
``PREDICTION_LOCK_AFTER_STATISTICS``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np

from mineocclude.experiment_iii.authority import canonical_sha256
from mineocclude.experiment_iii.errors import ExperimentIIIError
from mineocclude.experiment_iii.schema import ConditionId, write_json_atomic

__all__ = [
    "PredictionCell",
    "PredictionLock",
    "lock_filename",
]

lock_filename = "PREDICTION_LOCK.json"


@dataclass(frozen=True)
class PredictionCell:
    """One held-out prediction for one scored row."""

    identity: str
    condition_id: str
    row_index: int
    model: str
    prediction: float
    target: float

    @property
    def key(self) -> tuple[str, str, int, str]:
        return (self.identity, self.condition_id, self.row_index, self.model)

    def as_dict(self) -> dict[str, Any]:
        return {
            "identity": self.identity,
            "condition_id": self.condition_id,
            "row_index": self.row_index,
            "model": self.model,
            "prediction": float(self.prediction),
            "target": float(self.target),
        }


class PredictionLock:
    """Collects held-out predictions, then seals them before any statistic."""

    def __init__(self, *, feature_block_hashes: Mapping[str, str] | None = None):
        self._cells: dict[tuple[str, str, int, str], PredictionCell] = {}
        self._sealed_hash: str | None = None
        self._feature_block_hashes = dict(feature_block_hashes or {})
        self.statistics_opened = False

    # -- collection --------------------------------------------------------

    def add(self, cell: PredictionCell) -> None:
        if self._sealed_hash is not None:
            raise ExperimentIIIError(
                "PREDICTION_LOCK_AFTER_STATISTICS",
                "predictions cannot be added after the lock is sealed",
            )
        ConditionId(cell.condition_id)
        if not np.isfinite(cell.prediction) or not np.isfinite(cell.target):
            raise ExperimentIIIError(
                "PREDICTION_NONFINITE",
                f"non-finite prediction or target for {cell.key}",
            )
        if cell.key in self._cells:
            raise ExperimentIIIError(
                "PREDICTION_DUPLICATE_CELL",
                f"{cell.key} already has a held-out prediction; exactly one is "
                "permitted per (identity, condition, row, model) cell",
            )
        self._cells[cell.key] = cell

    def extend(self, cells: Iterable[PredictionCell]) -> None:
        for cell in cells:
            self.add(cell)

    # -- state -------------------------------------------------------------

    @property
    def sealed(self) -> bool:
        return self._sealed_hash is not None

    @property
    def sealed_hash(self) -> str | None:
        return self._sealed_hash

    def __len__(self) -> int:
        return len(self._cells)

    def cells(self) -> list[PredictionCell]:
        return [self._cells[key] for key in sorted(self._cells)]

    def assert_complete(
        self,
        *,
        identities: Sequence[str],
        conditions: Sequence[str],
        rows: int,
        models: Sequence[str],
    ) -> None:
        """Exactly one prediction for every required cell — no gaps, no extras."""
        required = {
            (identity, condition, row, model)
            for identity in identities
            for condition in conditions
            for row in range(rows)
            for model in models
        }
        present = set(self._cells)
        missing = required - present
        if missing:
            raise ExperimentIIIError(
                "PREDICTION_LOCK_MISSING",
                f"{len(missing)} required cells have no held-out prediction, "
                f"e.g. {sorted(missing)[:3]}",
            )
        extra = present - required
        if extra:
            raise ExperimentIIIError(
                "PREDICTION_DUPLICATE_CELL",
                f"{len(extra)} predictions fall outside the required cell set, "
                f"e.g. {sorted(extra)[:3]}",
            )

    # -- sealing -----------------------------------------------------------

    def body(self) -> dict[str, Any]:
        cells = [cell.as_dict() for cell in self.cells()]
        return {
            "schema_version": "mineocclude-experiment-iii-prediction-lock-v1",
            "authority_section": "8.8",
            "cell_count": len(cells),
            "models": sorted({cell["model"] for cell in cells}),
            "identities": sorted({cell["identity"] for cell in cells}),
            "conditions": sorted({cell["condition_id"] for cell in cells}),
            "feature_block_hashes": dict(sorted(self._feature_block_hashes.items())),
            "cells": cells,
        }

    def seal(self) -> str:
        """Hash-seal the predictions. Refused once statistics have been opened."""
        if self.statistics_opened:
            raise ExperimentIIIError(
                "PREDICTION_LOCK_AFTER_STATISTICS",
                "the lock must be sealed BEFORE any statistic is computed",
            )
        if not self._cells:
            raise ExperimentIIIError(
                "PREDICTION_LOCK_MISSING", "there is nothing to lock"
            )
        self._sealed_hash = canonical_sha256(self.body())
        return self._sealed_hash

    def write(self, directory: Path, *, root: Path | None = None) -> str:
        if not self.sealed:
            raise ExperimentIIIError(
                "PREDICTION_LOCK_MISSING",
                "seal the lock before writing it",
            )
        payload = self.body() | {"prediction_lock_sha256": self._sealed_hash}
        write_json_atomic(Path(directory) / lock_filename, payload, root=root)
        return self._sealed_hash

    # -- guards ------------------------------------------------------------

    def require_sealed(self, what: str = "a statistic") -> None:
        """Every statistical entry point calls this first."""
        if not self.sealed:
            raise ExperimentIIIError(
                "PREDICTION_LOCK_MISSING",
                f"{what} may not be computed before the prediction lock is sealed",
            )
        self.statistics_opened = True

    def verify_unmodified(self) -> None:
        """Re-hash the sealed content; a post-lock edit is an invalidation."""
        if not self.sealed:
            raise ExperimentIIIError(
                "PREDICTION_LOCK_MISSING", "the lock has not been sealed"
            )
        current = canonical_sha256(self.body())
        if current != self._sealed_hash:
            raise ExperimentIIIError(
                "PREDICTION_LOCK_AFTER_STATISTICS",
                f"locked content changed after sealing: {self._sealed_hash} -> "
                f"{current}",
            )

    def note_feature_block(self, name: str, digest: str) -> None:
        if self.sealed:
            raise ExperimentIIIError(
                "PREDICTION_LOCK_AFTER_STATISTICS",
                "feature blocks cannot be rebound after the lock is sealed",
            )
        self._feature_block_hashes[name] = digest
