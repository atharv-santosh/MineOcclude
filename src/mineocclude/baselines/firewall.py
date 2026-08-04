"""Person D pre-fit legal-information firewall.

Only explicitly registered BaselineSpec features cross this boundary.  The
returned rows contain no target, filename, fold, layout hint, or unrequested
metadata, so estimator code cannot accidentally consume such information.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from mineocclude.baselines.spec import (
    BaselineContractCode,
    BaselineContractError,
    BaselineSpec,
    validate_required_provenance,
)
from mineocclude.contracts.identity import FRAME_KEY


FrameKey = tuple[str, int]


@dataclass(frozen=True)
class LegalInputRow:
    """A validated frame key plus the exact selected feature allowlist."""

    trajectory_id: str
    model_frame_idx: int
    features: Mapping[str, object]

    @property
    def frame_key(self) -> FrameKey:
        return (self.trajectory_id, self.model_frame_idx)


def _finite(name: str, value: Any, *, nonnegative: bool = False) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
    ):
        raise BaselineContractError(
            BaselineContractCode.ILLEGAL_FEATURE, f"{name} must be finite"
        )
    number = float(value)
    if nonnegative and number < 0.0:
        raise BaselineContractError(
            BaselineContractCode.ILLEGAL_FEATURE, f"{name} cannot be negative"
        )
    return number


def _validate_feature(name: str, value: Any) -> object:
    if name == "visibility":
        if not isinstance(value, str) or value not in {"visible", "occluded"}:
            raise BaselineContractError(
                BaselineContractCode.ILLEGAL_FEATURE,
                "visibility must be 'visible' or 'occluded'",
            )
        return value
    if name == "tau":
        return _finite(name, value, nonnegative=True)
    if name in {
        "last_visible_position_blocks",
        "estimated_velocity_blocks_per_s",
    }:
        return _finite(name, value)
    # No unregistered feature gets a permissive generic validator.
    raise BaselineContractError(
        BaselineContractCode.ILLEGAL_FEATURE,
        f"no Person D validator exists for feature {name!r}",
    )


def select_legal_inputs(
    spec: BaselineSpec,
    rows: Sequence[Mapping[str, Any]],
    *,
    provenance: Mapping[str, Any],
) -> tuple[LegalInputRow, ...]:
    """Validate and select only a BaselineSpec's exact legal feature set.

    Input mappings are never changed.  Output is canonically sorted by the
    scientific frame key so estimator behavior cannot depend on physical row
    order.
    """

    validate_required_provenance(spec, provenance)
    if not isinstance(rows, (list, tuple)) or not rows:
        raise BaselineContractError(
            BaselineContractCode.INVALID_TYPE,
            "legal-input rows must be a non-empty list or tuple",
        )
    allowed = set(FRAME_KEY) | set(spec.legal_features)
    selected: list[LegalInputRow] = []
    seen: set[FrameKey] = set()
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise BaselineContractError(
                BaselineContractCode.INVALID_TYPE,
                f"input row {index} must be a mapping",
            )
        fields = set(row)
        missing = sorted(str(field) for field in allowed - fields)
        if missing:
            raise BaselineContractError(
                BaselineContractCode.MISSING_FIELD,
                f"input row {index} is missing: {', '.join(missing)}",
            )
        unknown = sorted(repr(field) for field in fields - allowed)
        if unknown:
            raise BaselineContractError(
                BaselineContractCode.ILLEGAL_FEATURE,
                f"input row {index} contains undeclared fields: {', '.join(unknown)}",
            )
        trajectory_id = row.get(FRAME_KEY[0])
        frame_idx = row.get(FRAME_KEY[1])
        if not isinstance(trajectory_id, str) or not trajectory_id.strip():
            raise BaselineContractError(
                BaselineContractCode.INVALID_IDENTITY,
                f"input row {index} has invalid trajectory_id",
            )
        if (
            not isinstance(frame_idx, int)
            or isinstance(frame_idx, bool)
            or frame_idx < 0
        ):
            raise BaselineContractError(
                BaselineContractCode.INVALID_IDENTITY,
                f"input row {index} has invalid model_frame_idx",
            )
        key = (trajectory_id, frame_idx)
        if key in seen:
            raise BaselineContractError(
                BaselineContractCode.DUPLICATE_IDENTITY,
                f"duplicate legal-input identity {key!r}",
            )
        seen.add(key)
        features = {
            name: _validate_feature(name, row[name]) for name in spec.legal_features
        }
        selected.append(
            LegalInputRow(
                trajectory_id=trajectory_id,
                model_frame_idx=frame_idx,
                features=features,
            )
        )
    return tuple(sorted(selected, key=lambda item: item.frame_key))
