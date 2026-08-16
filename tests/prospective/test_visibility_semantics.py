import math

import pytest

from mineocclude.prospective.visibility_semantics import (
    IndependentRegimeEvidence,
    OcclusionRegime,
    VisibilityPolicy,
    VisibilityPredicate,
    VisibilitySample,
    classify_regime,
    predicate_value,
)


POLICY = VisibilityPolicy(
    primary_predicate=VisibilityPredicate.FRACTIONAL_SILHOUETTE_VISIBILITY,
    visible_fraction_floor=0.9,
    occluded_fraction_ceiling=0.1,
    require_temporal_alignment=True,
    require_independent_evidence=True,
)


def _sample(fraction, evidence, **kwargs):
    return VisibilitySample(
        fractional_silhouette=fraction,
        temporal_alignment_confident=True,
        independent_regime_evidence=evidence,
        **kwargs,
    )


def test_predicates_are_distinct_and_read_without_substitution():
    sample = VisibilitySample(point_visible=False, any_silhouette_visible=True)
    assert len(set(VisibilityPredicate)) == 3
    assert predicate_value(sample, VisibilityPredicate.POINT_VISIBILITY) is False
    assert predicate_value(sample, VisibilityPredicate.ANY_SILHOUETTE_VISIBILITY) is True
    with pytest.raises(ValueError):
        predicate_value(sample, VisibilityPredicate.FRACTIONAL_SILHOUETTE_VISIBILITY)


def test_no_policy_means_no_scientific_adjudication():
    sample = _sample(1.0, IndependentRegimeEvidence.FULLY_VISIBLE)
    assert classify_regime(sample) is OcclusionRegime.UNADJUDICATED
    assert sample.measurements()["fractional_silhouette_estimate"] == 1.0


def test_two_wrong_agreeing_predicates_do_not_establish_stability():
    sample = VisibilitySample(point_visible=True, any_silhouette_visible=True)
    assert sample.predicates_agree is True
    assert classify_regime(sample, policy=POLICY) is OcclusionRegime.UNRESOLVED


def test_point_hidden_silhouette_partly_visible_remains_transition():
    sample = _sample(
        0.5,
        IndependentRegimeEvidence.TRANSITION,
        point_visible=False,
        any_silhouette_visible=True,
    )
    assert classify_regime(sample, policy=POLICY) is OcclusionRegime.PARTIAL_TRANSITION


def test_full_visible_full_occluded_and_partial_under_explicit_policy():
    visible = _sample(1.0, IndependentRegimeEvidence.FULLY_VISIBLE)
    occluded = _sample(0.0, IndependentRegimeEvidence.FULLY_OCCLUDED)
    partial = _sample(0.5, IndependentRegimeEvidence.TRANSITION)
    assert classify_regime(visible, policy=POLICY) is OcclusionRegime.STABLE_VISIBLE
    assert classify_regime(occluded, policy=POLICY) is OcclusionRegime.STABLE_OCCLUDED
    assert classify_regime(partial, policy=POLICY) is OcclusionRegime.PARTIAL_TRANSITION


def test_missing_independent_or_temporal_evidence_is_unresolved():
    missing_independent = VisibilitySample(
        fractional_silhouette=1.0, temporal_alignment_confident=True
    )
    missing_temporal = VisibilitySample(
        fractional_silhouette=1.0,
        independent_regime_evidence=IndependentRegimeEvidence.FULLY_VISIBLE,
    )
    assert classify_regime(missing_independent, policy=POLICY) is OcclusionRegime.UNRESOLVED
    assert classify_regime(missing_temporal, policy=POLICY) is OcclusionRegime.UNRESOLVED


def test_conflicting_independent_evidence_fails_closed():
    sample = _sample(1.0, IndependentRegimeEvidence.FULLY_OCCLUDED)
    assert classify_regime(sample, policy=POLICY) is OcclusionRegime.UNRESOLVED


def test_policy_thresholds_are_explicit_and_change_classification():
    sample = _sample(0.85, IndependentRegimeEvidence.FULLY_VISIBLE)
    strict = POLICY
    permissive = VisibilityPolicy(
        VisibilityPredicate.FRACTIONAL_SILHOUETTE_VISIBILITY,
        0.8,
        0.1,
        True,
        True,
    )
    assert classify_regime(sample, policy=strict) is OcclusionRegime.UNRESOLVED
    assert classify_regime(sample, policy=permissive) is OcclusionRegime.STABLE_VISIBLE


@pytest.mark.parametrize("bad", ["true", 1, 1.0, [], {}])
def test_boolean_measurements_are_strictly_typed(bad):
    with pytest.raises(TypeError):
        VisibilitySample(point_visible=bad)


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf, -0.1, 1.1])
def test_fraction_is_finite_and_bounded(bad):
    with pytest.raises(ValueError):
        VisibilitySample(fractional_silhouette=bad)


def test_only_physically_adjudicated_stable_regimes_are_stable():
    assert OcclusionRegime.STABLE_VISIBLE.is_stable
    assert OcclusionRegime.STABLE_OCCLUDED.is_stable
    assert not OcclusionRegime.PARTIAL_TRANSITION.is_stable
    assert not OcclusionRegime.UNRESOLVED.is_stable
    assert not OcclusionRegime.UNADJUDICATED.is_stable


def test_exact_fractional_precedence_contradiction_is_unresolved():
    sample = VisibilitySample(
        point_visible=False,
        any_silhouette_visible=False,
        fractional_silhouette=1.0,
        temporal_alignment_confident=True,
        independent_regime_evidence=IndependentRegimeEvidence.FULLY_VISIBLE,
    )
    assert classify_regime(sample, policy=POLICY) is OcclusionRegime.UNRESOLVED


@pytest.mark.parametrize(
    "sample",
    [
        VisibilitySample(point_visible=True, any_silhouette_visible=False),
        VisibilitySample(any_silhouette_visible=True, fractional_silhouette=0.0),
        VisibilitySample(point_visible=True, fractional_silhouette=0.0),
        VisibilitySample(
            any_silhouette_visible=True,
            fractional_silhouette=0.05,
            independent_regime_evidence=IndependentRegimeEvidence.FULLY_OCCLUDED,
        ),
    ],
)
def test_other_logical_visibility_contradictions_are_unresolved(sample):
    policy = VisibilityPolicy(
        VisibilityPredicate.ANY_SILHOUETTE_VISIBILITY,
        0.9,
        0.1,
        False,
        False,
    )
    assert classify_regime(sample, policy=policy) is OcclusionRegime.UNRESOLVED


def test_primary_predicate_is_explicit_and_never_inferred_from_available_fields():
    sample = VisibilitySample(
        point_visible=False,
        temporal_alignment_confident=True,
        independent_regime_evidence=IndependentRegimeEvidence.FULLY_OCCLUDED,
    )
    point_policy = VisibilityPolicy(
        VisibilityPredicate.POINT_VISIBILITY, 0.9, 0.1, True, True
    )
    silhouette_policy = VisibilityPolicy(
        VisibilityPredicate.ANY_SILHOUETTE_VISIBILITY, 0.9, 0.1, True, True
    )
    assert classify_regime(sample, policy=point_policy) is OcclusionRegime.STABLE_OCCLUDED
    assert classify_regime(sample, policy=silhouette_policy) is OcclusionRegime.UNRESOLVED


def test_policy_rejects_missing_or_wrong_typed_primary_predicate():
    with pytest.raises(TypeError):
        VisibilityPolicy("fractional", 0.9, 0.1, True, True)
