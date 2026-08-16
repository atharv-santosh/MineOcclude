"""Cohort/run identity invariants."""

import pytest

from mineocclude.prospective.run_identity import (
    CohortTier,
    RunIdentity,
    RunIdentityViolation,
    assert_unique_identities,
)


def _identity(unit, episode, run="a-prime-dev-v1", tier=CohortTier.DEVELOPMENT, spec=None):
    return RunIdentity(
        scientific_run_id=run,
        cohort_tier=tier,
        unit_id=unit,
        episode_id=episode,
        trajectory_spec_id=spec or f"spec_{unit}",
        confirmatory_membership=tier is CohortTier.CONFIRMATORY,
    )


def test_scientific_run_id_has_no_default_and_cannot_be_blank():
    """The historical defect was a silent default:
    spec.get('scientific_run_id', 'mineocclude-regime-a-first25-v2')."""
    with pytest.raises(TypeError):
        RunIdentity(cohort_tier=CohortTier.DEVELOPMENT, unit_id="u", episode_id=1,
                    trajectory_spec_id="s")
    with pytest.raises(RunIdentityViolation):
        _identity("u", 1, run="")
    with pytest.raises(RunIdentityViolation):
        _identity("u", 1, run="   ")


def test_confirmatory_membership_has_no_default_and_is_strict_bool():
    with pytest.raises(TypeError):
        RunIdentity("run", CohortTier.DEVELOPMENT, "u", 1, "s")
    with pytest.raises(RunIdentityViolation):
        RunIdentity("run", CohortTier.DEVELOPMENT, "u", 1, "s", 0)


@pytest.mark.parametrize("field", ["unit_id", "trajectory_spec_id"])
def test_other_identity_fields_cannot_be_missing(field):
    kwargs = dict(
        scientific_run_id="run", cohort_tier=CohortTier.DEVELOPMENT,
        unit_id="u", episode_id=1, trajectory_spec_id="s",
        confirmatory_membership=False,
    )
    kwargs[field] = ""
    with pytest.raises(RunIdentityViolation):
        RunIdentity(**kwargs)


def test_empty_identity_cohort_fails_closed():
    with pytest.raises(RunIdentityViolation):
        assert_unique_identities([])


def test_confirmatory_membership_must_agree_with_tier():
    with pytest.raises(RunIdentityViolation):
        RunIdentity("run", CohortTier.DEVELOPMENT, "u", 1, "s", confirmatory_membership=True)
    with pytest.raises(RunIdentityViolation):
        RunIdentity("run", CohortTier.CONFIRMATORY, "u", 1, "s", confirmatory_membership=False)
    assert RunIdentity("run", CohortTier.CONFIRMATORY, "u", 1, "s", True).confirmatory_membership


def test_only_confirmatory_tier_may_enter_confirmatory_analysis():
    assert CohortTier.CONFIRMATORY.may_enter_confirmatory_analysis
    for tier in (CohortTier.DEVELOPMENT, CohortTier.DIAGNOSTIC, CohortTier.CALIBRATION):
        assert not tier.may_enter_confirmatory_analysis


def test_unique_identities_accepted():
    report = assert_unique_identities([_identity(f"u{i}", 100 + i) for i in range(5)])
    assert report["unit_count"] == 5
    assert report["unit_id_unique"] and report["episode_id_unique"]
    assert report["run_id_tier_collisions"] == {}


@pytest.mark.parametrize("field", ["unit", "episode", "spec"])
def test_duplicate_identities_rejected(field):
    ids = [_identity("u0", 100), _identity("u1", 101)]
    if field == "unit":
        ids[1] = _identity("u0", 101)
    elif field == "episode":
        ids[1] = _identity("u1", 100)
    else:
        ids[1] = _identity("u1", 101, spec="spec_u0")
    with pytest.raises(RunIdentityViolation):
        assert_unique_identities(ids)


def test_one_run_id_may_not_span_multiple_cohort_tiers():
    """Exactly the historical hazard: one run_id covering Regime A scientific,
    P2 diagnostic and P3 development units."""
    shared = "mineocclude-regime-a-first25-v2"
    ids = [
        _identity("u0", 100, run=shared, tier=CohortTier.CONFIRMATORY),
        _identity("u1", 101, run=shared, tier=CohortTier.DEVELOPMENT),
        _identity("u2", 102, run=shared, tier=CohortTier.DIAGNOSTIC),
    ]
    with pytest.raises(RunIdentityViolation) as excinfo:
        assert_unique_identities(ids)
    assert "multiple cohort tiers" in str(excinfo.value)


def test_distinct_run_ids_per_tier_accepted():
    ids = [
        _identity("u0", 100, run="a-prime-confirmatory-v1", tier=CohortTier.CONFIRMATORY),
        _identity("u1", 101, run="a-prime-dev-v1", tier=CohortTier.DEVELOPMENT),
        _identity("u2", 102, run="a-prime-cal-v1", tier=CohortTier.CALIBRATION),
    ]
    report = assert_unique_identities(ids)
    assert len(report["run_ids"]) == 3
    assert report["run_id_tier_collisions"] == {}
