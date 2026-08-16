"""Cohort/run identity invariants for prospective capture.

Historical defect this repairs (future-facing only):

``p2c_capture.package`` reads the scientific run identity as
``spec.get("scientific_run_id", "mineocclude-regime-a-first25-v2")``.  Neither
the P2 specs nor the P3 specs set that key, so the silent default stamped the
*Regime A first25 scientific* run identity onto 50 P2 diagnostic packages and
300 P3 development packages -- cohorts that the P3 authority declares
``permanently_excluded_from_confirmatory_a_prime``.

Independently checked on the historical evidence, episode ids and trajectory ids
are unique within and across P2 and P3 (25 + 150 distinct, zero collision), and
no analysis joins on ``run_id``.  The historical impact is therefore provenance
only, not data integrity.  The hazard is prospective: a future cohort selected
by ``run_id`` would silently sweep three different tiers together.

This module makes the identity explicit and required.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass

__all__ = ["CohortTier", "RunIdentity", "RunIdentityViolation", "assert_unique_identities"]


class RunIdentityViolation(ValueError):
    """Raised when a cohort identity is missing, defaulted, or ambiguous."""


class CohortTier(enum.Enum):
    """Scientific standing of a cohort.  Never inferred, always declared."""

    CONFIRMATORY = "confirmatory"
    DEVELOPMENT = "development"
    DIAGNOSTIC = "diagnostic"
    CALIBRATION = "calibration"

    @property
    def may_enter_confirmatory_analysis(self) -> bool:
        return self is CohortTier.CONFIRMATORY


@dataclass(frozen=True)
class RunIdentity:
    """Fully-qualified identity of one captured unit.

    ``scientific_run_id`` has no default.  Constructing this object without one
    is an error, which is exactly the failure mode the historical silent default
    hid.
    """

    scientific_run_id: str
    cohort_tier: CohortTier
    unit_id: str
    episode_id: int
    trajectory_spec_id: str
    confirmatory_membership: bool

    def __post_init__(self) -> None:
        for name in ("scientific_run_id", "unit_id", "trajectory_spec_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise RunIdentityViolation(f"{name} must be an explicit non-empty string")
        if not isinstance(self.cohort_tier, CohortTier):
            raise RunIdentityViolation("cohort_tier must be explicitly declared")
        if type(self.confirmatory_membership) is not bool:
            raise RunIdentityViolation("confirmatory_membership must be an explicit bool")
        if not self.scientific_run_id or not self.scientific_run_id.strip():
            raise RunIdentityViolation(
                "scientific_run_id must be declared explicitly; a defaulted run id "
                "silently merges cohort tiers"
            )
        if self.confirmatory_membership != self.cohort_tier.may_enter_confirmatory_analysis:
            raise RunIdentityViolation(
                f"confirmatory_membership={self.confirmatory_membership} contradicts "
                f"cohort_tier={self.cohort_tier.value}"
            )
        if (
            not isinstance(self.episode_id, int)
            or isinstance(self.episode_id, bool)
            or self.episode_id < 0
        ):
            raise RunIdentityViolation("episode_id must be non-negative")

    def to_dict(self) -> dict:
        return {
            "scientific_run_id": self.scientific_run_id,
            "cohort_tier": self.cohort_tier.value,
            "unit_id": self.unit_id,
            "episode_id": self.episode_id,
            "trajectory_spec_id": self.trajectory_spec_id,
            "confirmatory_membership": self.confirmatory_membership,
        }


def assert_unique_identities(identities: list[RunIdentity]) -> dict:
    """Verify the invariants a cohort join depends on.

    Checks that unit ids, episode ids and trajectory spec ids are each unique,
    and that a single ``scientific_run_id`` never spans more than one tier --
    the precise condition the historical default violated.
    """
    if not identities:
        raise RunIdentityViolation("identity cohort must be non-empty")
    if any(not isinstance(identity, RunIdentity) for identity in identities):
        raise RunIdentityViolation("every identity must be a RunIdentity")
    report: dict = {"unit_count": len(identities)}
    for field in ("unit_id", "episode_id", "trajectory_spec_id"):
        values = [getattr(identity, field) for identity in identities]
        duplicates = sorted({v for v in values if values.count(v) > 1})
        report[f"{field}_unique"] = not duplicates
        if duplicates:
            raise RunIdentityViolation(f"duplicate {field}: {duplicates}")

    tiers_by_run: dict[str, set[str]] = {}
    for identity in identities:
        tiers_by_run.setdefault(identity.scientific_run_id, set()).add(
            identity.cohort_tier.value
        )
    mixed = {run: sorted(tiers) for run, tiers in tiers_by_run.items() if len(tiers) > 1}
    report["run_ids"] = sorted(tiers_by_run)
    report["run_id_tier_collisions"] = mixed
    if mixed:
        raise RunIdentityViolation(
            f"scientific_run_id spans multiple cohort tiers: {mixed}"
        )
    return report
