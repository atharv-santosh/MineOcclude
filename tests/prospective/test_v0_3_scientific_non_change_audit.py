"""The v0.3 builder synchronization changed no scientific rule. Proved here.

The ``134a242`` Stage-1 FAIL had two independent roots. One was a stale evidence
builder -- a pure software defect, repaired in this freeze. The other was a
genuine measurement: the ``a1x_rtl_wall_r01`` trajectory produced a trimodal
causal kernel whose cross-correlation lag departed 1.8213 ticks from its kernel
mode, against a 1.0-tick bound that the other seven trajectories cleared by
0.137-0.510 ticks.

That second root is a *result*, not a bug, and the next campaign exists to find
out whether it recurs. The standing temptation after a failure like it is to
adjust the rule that caught it -- widen the bound, add a unimodality exception,
exclude the trajectory, or re-seed around it. Any of those would convert a
prospective measurement into a retrospective one and destroy the qualification's
meaning.

So this module is an audit, not a unit test. It pins every scientific constant
the repair was forbidden to touch and fails if one moves, and it greps the
runtime-critical source closure for the shapes an outcome-derived exception
would take. It is deliberately blunt: a test that merely re-read the authority
would pass no matter what the authority said.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from mineocclude.prospective.development_workflow import (  # noqa: E402
    DESIGNATED_HIDDEN_ROW_SELECTION_RULE, EXTENT_TRUTH_PREDICATE,
    RUNTIME_CRITICAL_SOURCE_PATHS, load_json,
)
from mineocclude.prospective.extent_geometry import (  # noqa: E402
    TARGET_EXTENT_HALF_BLOCKS, derive_target_extent_half_blocks,
)
from mineocclude.prospective.package_binding import resolve_package_binding  # noqa: E402

#: The trajectory that legitimately failed temporal alignment at 134a242. It must
#: not appear anywhere in the runtime-critical source closure -- no exclusion, no
#: special case, no comment-driven branch.
FAILED_TRAJECTORY_ID = "a1x_rtl_wall_r01"


@pytest.fixture(scope="module")
def authority():
    return load_json(resolve_package_binding("v0.3", ROOT).authority_path)


# ---------------------------------------------------------------- extent


def test_target_extent_changed_false(authority):
    """TARGET_EXTENT_CHANGED=false, and it still reproduces from the model."""
    declared = authority["stage1_policy"]["visibility"]["target_extent"]
    assert declared["half_width_blocks"] == 0.8727621336620037
    assert declared["closed_form"] == "(7 + sqrt(48.5)) / 16"
    assert declared["detector_derived"] is False
    assert declared["outcome_derived"] is False
    assert declared["fitted"] is False
    assert declared["yaw_independent"] is True
    # Not merely equal to the constant -- rederived from the pinned client jar's
    # model geometry, so a hand-edited scalar cannot satisfy this.
    assert TARGET_EXTENT_HALF_BLOCKS == 0.8727621336620037
    assert derive_target_extent_half_blocks() == TARGET_EXTENT_HALF_BLOCKS
    # The detector-fitted alternative stays rejected and unused.
    assert declared["rejected_alternative"]["value_range"] == [0.6, 0.8]


def test_visibility_predicate_changed_false(authority):
    visibility = authority["stage1_policy"]["visibility"]
    assert visibility["primary_predicate"] == EXTENT_TRUTH_PREDICATE
    assert visibility["primary_predicate"] == (
        "extent_occlusion_geometry_over_rendered_target_extent")
    assert visibility["detector_truth_predicate_independent_of_scored_detector"] is True
    assert visibility["held_out_rows_classified_directly_from_geometry"] is True
    assert visibility["transition_band_transferred_to_held_out"] is False
    classification = visibility["extent_classification"]
    assert classification["detector_may_influence_classification"] is False
    assert classification["samples_per_axis"] == 5
    assert classification["regime_mapping"] == {
        "EXTENT_FULLY_OCCLUDED": "stable_occluded",
        "EXTENT_FULLY_VISIBLE": "stable_visible",
        "EXTENT_PARTIAL": "partial_transition"}
    assert classification["scored_classes"] == ["stable_visible", "stable_occluded"]
    assert classification["unscored_classes"] == ["partial_transition"]


def test_zero_error_gate_and_sample_floor_changed_false(authority):
    visibility = authority["stage1_policy"]["visibility"]
    assert visibility["maximum_observed_false_positive_rate"] == 0.0
    assert visibility["maximum_observed_false_negative_rate"] == 0.0
    assert visibility["minimum_stable_samples_per_direction_per_class"] == 60
    assert visibility["partial_transition_observation_required_on_held_out_wall"] is True
    assert visibility["calibration_detector_response_required"] is True
    assert visibility["pooled_accuracy_gate_forbidden"] is True
    assert visibility["precision_gate_forbidden"] is True


def test_hidden_first_n_rule_changed_false(authority):
    """The rule is unchanged; only the pool it reads was repaired."""
    contamination = authority["stage1_policy"]["contamination"]
    assert (contamination["designated_hidden_row_selection_rule"]
            == "FIRST_N_QUALIFIED_STABLE_OCCLUDED_ROWS_IN_ASCENDING_MODEL_FRAME_ORDER")
    assert (contamination["designated_hidden_row_selection_rule"]
            == DESIGNATED_HIDDEN_ROW_SELECTION_RULE)
    assert contamination["required_hidden_rows_per_wall_validation_run"] == 19
    assert contamination["maximum_rows_each_class"] == 0
    assert len(contamination["prohibited_classes"]) == 9


# ---------------------------------------------------------------- temporal


def test_temporal_refinement_bound_changed_false(authority):
    """The 1.0-tick bound the failing trajectory missed by 0.8213 ticks."""
    temporal = authority["stage1_policy"]["temporal_alignment"]
    assert temporal["cross_correlation_subtick_refinement_bound_ticks"] == 1.0
    assert (temporal["cross_correlation_subtick_refinement_bound_ticks_classification"]
            == "PURE_IMPLEMENTATION_CONSTANT")


def test_temporal_fir_rule_and_estimands_changed_false(authority):
    temporal = authority["stage1_policy"]["temporal_alignment"]
    assert temporal["required_method_ids"] == [
        "causal_fir_group_delay", "derivative_cross_correlation_lag"]
    assert temporal["maximum_lag_ticks_for_estimation"] == 8
    assert temporal["minimum_trajectories_per_direction"] == 4
    assert temporal["minimum_usable_samples_per_trajectory"] == 9
    assert temporal["confidence_level"] == 0.95
    assert temporal["pure_delay_interpretation_allowed"] is False
    assert temporal["pure_delay_off_peak_mass_tolerance"] == 1e-09
    assert temporal["causal_fir_must_beat_best_pure_delay"] is True
    assert temporal["causal_fir_must_beat_best_pure_delay_scope"] == "EVERY_TRAJECTORY"
    assert temporal["measurement_separate_by_direction"] is True
    assert temporal["unit_spaced_clock_coordinates_required"] is True
    assert temporal["prospective_ci_width"]["acceptance_threshold"] is None
    # Warm-up admissibility, the rule that keeps unaligned rows out of intervals.
    assert temporal["aligned_position_required_for_interval_derivation"] is True
    assert temporal["raw_world_x_may_substitute_for_aligned_position"] is False
    assert temporal["aligned_position_field"] == "world_x"


def test_no_unimodality_gate_or_multimodality_exception_exists(authority):
    """The observed kernel was trimodal. No rule may now mention that."""
    temporal = authority["stage1_policy"]["temporal_alignment"]
    forbidden = ("unimodal", "unimodality", "multimodal", "multimodality",
                 "modality_exception", "kernel_mode_count")
    flat = repr(temporal).lower()
    assert not [token for token in forbidden if token in flat]
    # The frozen forensic coherence check is a recorded observation, never a gate.
    reference = temporal["frozen_forensic_reference_agreement_check"]
    assert reference["acceptance_gate"] is False
    assert reference["observed_ordering_is_an_acceptance_gate"] is False


#: The authority *narrative* builders. Their job includes recording what the
#: predecessor Stage-1 did, so they legitimately name the failing trajectory in a
#: change log. They are exempted from the literal ban below and held to the
#: stronger structural check in
#: :func:`test_the_failed_trajectory_never_reaches_a_scientific_rule` instead.
AUTHORITY_NARRATIVE_BUILDERS = (
    "scripts/regime_a_prime_qualification_v0_3/build_authority.py",
    "scripts/regime_a_prime_qualification_v0_4/build_authority.py",
)


@pytest.mark.parametrize("relative", RUNTIME_CRITICAL_SOURCE_PATHS)
def test_no_outcome_derived_temporal_exception_in_runtime_critical_source(relative):
    """134A242_FAILED_ROW_EXCLUDED=false, checked at the byte level.

    A special case for the failing trajectory would most plausibly appear as its
    literal unit id, or as a seed/trajectory exclusion list. Neither may exist in
    any file whose bytes the runtime closure certifies.
    """
    text = (ROOT / relative).read_text()
    if relative not in AUTHORITY_NARRATIVE_BUILDERS:
        assert FAILED_TRAJECTORY_ID not in text, relative
    lowered = text.lower()
    for token in ("excluded_trajector", "trajectory_exclusion", "skip_trajectory",
                  "excluded_unit_ids"):
        assert token not in lowered, f"{relative} mentions {token}"
    # "unimodality" is banned outright everywhere, including the narrative
    # builders -- a change log may record that no such gate was added, but the
    # word must never name a rule.
    assert "unimodality_gate_added" in lowered or "unimodality" not in lowered, relative


@pytest.mark.parametrize("version_tag", ["v0.3", "v0.4"])
def test_the_failed_trajectory_never_reaches_a_scientific_rule(version_tag):
    """Naming the failure in a change log is history; naming it in a rule is not.

    The narrative builders are allowed to say what happened at 134a242. What
    none of them may do is let that identifier reach a subtree the evaluator
    actually reads, where it could become an exclusion or an exception.
    """
    import json

    from mineocclude.prospective.package_binding import resolve_package_binding

    authority = load_json(resolve_package_binding(version_tag, ROOT).authority_path)
    for subtree in ("stage1_policy", "stage2_policy", "apparatus",
                    "fixed_development_configuration", "clock_domains"):
        assert FAILED_TRAJECTORY_ID not in json.dumps(authority[subtree]), subtree


# ---------------------------------------------------------------- design


def test_trajectory_structure_and_speed_changed_false(authority):
    fixed = authority["fixed_development_configuration"]
    policy = authority["stage1_policy"]
    assert fixed["speed_blocks_per_second"] == 2.0
    assert fixed["speed_sweep_authorized"] is False
    assert fixed["expected_frames_per_run"] == 180
    assert fixed["motion_noise_q"] == 0.05
    assert fixed["start_world_x_by_direction"] == {
        "LEFT_TO_RIGHT": -7.8, "RIGHT_TO_LEFT": 7.8}
    assert policy["run_count"] == 8
    assert policy["directions"] == ["LEFT_TO_RIGHT", "RIGHT_TO_LEFT"]
    assert policy["scenes"] == ["WALL", "NO_WALL"]
    assert policy["replicate_roles"] == {
        "1": "TRANSITION_MEASUREMENT", "2": "HELD_OUT_VALIDATION"}


def test_stage2_preauthorized_false(authority):
    assert authority["STAGE_1_COLLECTION_AUTHORIZED"] is False
    assert authority["STAGE_2_COLLECTION_AUTHORIZED"] is False
    assert authority["confirmatory_collection_authorized"] is False
    assert authority["confirmatory_interpretation_authorized"] is False
    assert authority["REGIME_A_PRIME_COLLECTION_AUTHORIZED"] == "NO"
