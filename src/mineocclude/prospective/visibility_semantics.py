"""Visibility measurements separated from caller-owned regime policy."""

from __future__ import annotations

import enum
import math
from dataclasses import dataclass
from numbers import Real

__all__ = [
    "VisibilityPredicate",
    "OcclusionRegime",
    "IndependentRegimeEvidence",
    "VisibilitySample",
    "VisibilityPolicy",
    "classify_regime",
    "predicate_value",
]


class VisibilityPredicate(enum.Enum):
    POINT_VISIBILITY = "point_visibility"
    ANY_SILHOUETTE_VISIBILITY = "any_silhouette_visibility"
    FRACTIONAL_SILHOUETTE_VISIBILITY = "fractional_silhouette_visibility"

    @property
    def is_boolean(self) -> bool:
        return self is not VisibilityPredicate.FRACTIONAL_SILHOUETTE_VISIBILITY


class OcclusionRegime(enum.Enum):
    STABLE_VISIBLE = "stable_visible"
    STABLE_OCCLUDED = "stable_occluded"
    PARTIAL_TRANSITION = "partial_transition"
    UNRESOLVED = "unresolved"
    UNADJUDICATED = "unadjudicated"

    @property
    def is_stable(self) -> bool:
        return self in {self.STABLE_VISIBLE, self.STABLE_OCCLUDED}


class IndependentRegimeEvidence(enum.Enum):
    FULLY_VISIBLE = "fully_visible"
    FULLY_OCCLUDED = "fully_occluded"
    TRANSITION = "transition"


def _optional_bool(value: object, name: str) -> None:
    if value is not None and type(value) is not bool:
        raise TypeError(f"{name} must be bool or None")


def _optional_finite(value: object, name: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{name} must be a real number or None")
    converted = float(value)
    if not math.isfinite(converted):
        raise ValueError(f"{name} must be finite")
    return converted


@dataclass(frozen=True)
class VisibilitySample:
    """Independent measurements only; this type never chooses a regime."""

    point_visible: bool | None = None
    any_silhouette_visible: bool | None = None
    fractional_silhouette: float | None = None
    world_x: float | None = None
    wall_relative_x: float | None = None
    transition_geometry: float | None = None
    temporal_alignment_confident: bool | None = None
    independent_regime_evidence: IndependentRegimeEvidence | None = None

    def __post_init__(self) -> None:
        _optional_bool(self.point_visible, "point_visible")
        _optional_bool(self.any_silhouette_visible, "any_silhouette_visible")
        _optional_bool(
            self.temporal_alignment_confident, "temporal_alignment_confident"
        )
        fraction = _optional_finite(
            self.fractional_silhouette, "fractional_silhouette"
        )
        if fraction is not None and not 0.0 <= fraction <= 1.0:
            raise ValueError("fractional_silhouette must lie in [0, 1]")
        for name in ("world_x", "wall_relative_x", "transition_geometry"):
            _optional_finite(getattr(self, name), name)
        if self.independent_regime_evidence is not None and not isinstance(
            self.independent_regime_evidence, IndependentRegimeEvidence
        ):
            raise TypeError("independent_regime_evidence has an invalid type")

    @property
    def predicates_agree(self) -> bool | None:
        if self.point_visible is None or self.any_silhouette_visible is None:
            return None
        return self.point_visible == self.any_silhouette_visible

    def measurements(self) -> dict:
        return {
            "point_visibility": self.point_visible,
            "silhouette_evidence": self.any_silhouette_visible,
            "fractional_silhouette_estimate": self.fractional_silhouette,
            "transition_geometry": self.transition_geometry,
            "world_x": self.world_x,
            "wall_relative_x": self.wall_relative_x,
            "temporal_alignment_confident": self.temporal_alignment_confident,
            "independent_regime_evidence": None
            if self.independent_regime_evidence is None
            else self.independent_regime_evidence.value,
        }


@dataclass(frozen=True)
class VisibilityPolicy:
    """All scientific classification choices supplied explicitly by a caller."""

    primary_predicate: VisibilityPredicate
    visible_fraction_floor: float
    occluded_fraction_ceiling: float
    require_temporal_alignment: bool
    require_independent_evidence: bool

    def __post_init__(self) -> None:
        if not isinstance(self.primary_predicate, VisibilityPredicate):
            raise TypeError("primary_predicate must be a VisibilityPredicate")
        floor = _optional_finite(self.visible_fraction_floor, "visible_fraction_floor")
        ceiling = _optional_finite(
            self.occluded_fraction_ceiling, "occluded_fraction_ceiling"
        )
        if floor is None or ceiling is None or not 0 <= ceiling <= floor <= 1:
            raise ValueError(
                "require 0 <= occluded_fraction_ceiling <= visible_fraction_floor <= 1"
            )
        if type(self.require_temporal_alignment) is not bool:
            raise TypeError("require_temporal_alignment must be bool")
        if type(self.require_independent_evidence) is not bool:
            raise TypeError("require_independent_evidence must be bool")


def predicate_value(sample: VisibilitySample, predicate: VisibilityPredicate):
    if not isinstance(predicate, VisibilityPredicate):
        raise TypeError("predicate must be a VisibilityPredicate")
    if predicate is VisibilityPredicate.POINT_VISIBILITY:
        value = sample.point_visible
    elif predicate is VisibilityPredicate.ANY_SILHOUETTE_VISIBILITY:
        value = sample.any_silhouette_visible
    else:
        value = sample.fractional_silhouette
    if value is None:
        raise ValueError(f"sample carries no evidence for {predicate.value}")
    return value


def classify_regime(
    sample: VisibilitySample,
    *,
    policy: VisibilityPolicy | None = None,
) -> OcclusionRegime:
    """Apply explicit caller policy, or return ``UNADJUDICATED``.

    Agreement between point and silhouette predicates is exposed as a
    measurement but never promoted to a physical stable regime on its own.
    """
    if not isinstance(sample, VisibilitySample):
        raise TypeError("sample must be a VisibilitySample")
    if policy is None:
        return OcclusionRegime.UNADJUDICATED
    if not isinstance(policy, VisibilityPolicy):
        raise TypeError("policy must be VisibilityPolicy or None")
    if policy.require_temporal_alignment and sample.temporal_alignment_confident is not True:
        return OcclusionRegime.UNRESOLVED
    independent = sample.independent_regime_evidence
    if policy.require_independent_evidence and independent is None:
        return OcclusionRegime.UNRESOLVED

    fraction = sample.fractional_silhouette
    point = sample.point_visible
    silhouette = sample.any_silhouette_visible
    structurally_inconsistent = (
        (point is True and silhouette is False)
        or (silhouette is False and fraction is not None and fraction > 0.0)
        or (silhouette is True and fraction == 0.0)
        or (point is True and fraction == 0.0)
    )
    independent_inconsistent = (
        independent is IndependentRegimeEvidence.FULLY_VISIBLE
        and (point is False or silhouette is False or fraction == 0.0)
    ) or (
        independent is IndependentRegimeEvidence.FULLY_OCCLUDED
        and (point is True or silhouette is True or (fraction is not None and fraction > 0.0))
    )
    if structurally_inconsistent or independent_inconsistent:
        return OcclusionRegime.UNRESOLVED

    if policy.primary_predicate is VisibilityPredicate.FRACTIONAL_SILHOUETTE_VISIBILITY:
        if fraction is None:
            return OcclusionRegime.UNRESOLVED
        if fraction >= policy.visible_fraction_floor:
            measured = OcclusionRegime.STABLE_VISIBLE
        elif fraction <= policy.occluded_fraction_ceiling:
            measured = OcclusionRegime.STABLE_OCCLUDED
        else:
            measured = OcclusionRegime.PARTIAL_TRANSITION
    elif policy.primary_predicate is VisibilityPredicate.POINT_VISIBILITY:
        if point is None:
            return OcclusionRegime.UNRESOLVED
        if point is False and silhouette is True:
            measured = OcclusionRegime.PARTIAL_TRANSITION
        else:
            measured = (
                OcclusionRegime.STABLE_VISIBLE
                if point
                else OcclusionRegime.STABLE_OCCLUDED
            )
    else:
        if silhouette is None:
            return OcclusionRegime.UNRESOLVED
        if silhouette is True and point is False:
            measured = OcclusionRegime.PARTIAL_TRANSITION
        else:
            measured = (
                OcclusionRegime.STABLE_VISIBLE
                if silhouette
                else OcclusionRegime.STABLE_OCCLUDED
            )

    expected = {
        IndependentRegimeEvidence.FULLY_VISIBLE: OcclusionRegime.STABLE_VISIBLE,
        IndependentRegimeEvidence.FULLY_OCCLUDED: OcclusionRegime.STABLE_OCCLUDED,
        IndependentRegimeEvidence.TRANSITION: OcclusionRegime.PARTIAL_TRANSITION,
    }.get(independent)
    if expected is not None and measured is not expected:
        return OcclusionRegime.UNRESOLVED
    return measured
