import math

import numpy as np
import pytest

from mineocclude.prospective.clock_domains import TimebaseSpec, UnresolvedAlignment
from mineocclude.prospective.temporal_alignment import (
    AlignmentEvidence,
    AlignmentRequirements,
    EvidenceScope,
    UncertaintyRequest,
    estimate_alignment,
)

RNG_SEED = 20260816
TIMEBASE = TimebaseSpec(0.05, 1)
UNCERTAINTY = UncertaintyRequest(0.95, 1000, 1234)


def _trajectory(
    lag_ticks,
    *,
    direction="LEFT_TO_RIGHT",
    speed=2.0,
    n=260,
    seed=0,
    kernel=None,
    scale=-23.3,
    offset=320.0,
):
    rng = np.random.default_rng(RNG_SEED + seed)
    sign = 1.0 if direction == "LEFT_TO_RIGHT" else -1.0
    step = sign * speed * 0.05
    noise = rng.standard_normal(n) * 0.05
    logged = np.cumsum(np.full(n, step) + noise) + (-7.8 if sign > 0 else 7.8)
    if kernel is None:
        kernel = np.zeros(lag_ticks + 1)
        kernel[lag_ticks] = 1.0
    padded = np.concatenate([np.full(len(kernel), logged[0]), logged])
    filtered = np.convolve(padded, kernel, mode="full")[len(kernel) : len(kernel) + n]
    return logged, offset + scale * filtered


def _evidence(lag, *, scene="NO_WALL", mask=None, **kwargs):
    logged, rendered = _trajectory(lag, **kwargs)
    n = len(logged)
    return AlignmentEvidence(
        trajectory_id=f"t{kwargs.get('seed', 0)}",
        logged_position=logged,
        rendered_position=rendered,
        direction=kwargs.get("direction", "LEFT_TO_RIGHT"),
        blocks_per_second=kwargs.get("speed", 2.0),
        scene=scene,
        exclude_mask=np.zeros(n, dtype=bool) if mask is None else mask,
        server_state_ticks=np.arange(n),
        render_model_frame_indices=np.arange(n),
    )


def _requirements(*, directions=None, speeds=None, scenes=None, minimum=4, samples=40, discrepancy=1.0):
    return AlignmentRequirements(
        minimum_trajectories=minimum,
        required_directions=frozenset(directions or {"LEFT_TO_RIGHT"}),
        required_speeds=frozenset(speeds or {2.0}),
        required_scenes=frozenset(scenes or {"NO_WALL"}),
        minimum_usable_samples_per_trajectory=samples,
        maximum_t_interval_width_ticks=10.0,
        maximum_pure_delay_relative_improvement=discrepancy,
    )


def _estimate(evidence, requirements=None, uncertainty=UNCERTAINTY, max_lag=8):
    return estimate_alignment(
        evidence,
        timebase=TIMEBASE,
        max_lag_ticks=max_lag,
        requirements=requirements,
        uncertainty=uncertainty,
    )


@pytest.mark.parametrize("lag", [0, 1, 3, 4, 6])
def test_recovers_known_delay_with_explicit_requirements(lag):
    evidence = [_evidence(lag, seed=index) for index in range(6)]
    estimate = _estimate(evidence, _requirements()).require_resolved()
    assert estimate.group_delay_ticks == pytest.approx(lag, abs=0.15)
    assert estimate.receipt()["scientific_requirements_are_caller_supplied"] is True


def test_measurement_without_requirements_is_not_adjudicated_or_resolved():
    estimate = _estimate([_evidence(3, seed=index) for index in range(6)])
    assert estimate.measured
    assert not estimate.resolved
    assert estimate.adjudication == "MEASURED_NOT_ADJUDICATED"
    assert estimate.group_delay_ticks == pytest.approx(3.0, abs=0.2)
    with pytest.raises(UnresolvedAlignment):
        estimate.require_resolved()


def test_spread_kernel_is_measured_and_strict_pure_delay_requirement_fails():
    kernel = np.array([0.0, 0.05, 0.30, 0.26, 0.15, 0.12, 0.05, 0.04, 0.03])
    kernel /= kernel.sum()
    evidence = []
    for index in range(6):
        logged, rendered = _trajectory(0, seed=index, kernel=kernel)
        evidence.append(
            AlignmentEvidence(
                f"t{index}", logged, rendered, "LEFT_TO_RIGHT", 2.0, "NO_WALL",
                np.zeros(len(logged), dtype=bool), np.arange(len(logged)), np.arange(len(logged))
            )
        )
    estimate = _estimate(evidence, _requirements(discrepancy=0.01))
    assert estimate.measured and not estimate.resolved
    assert estimate.kernel_is_pure_delay is False
    assert "discrepancy" in estimate.refusal_reason


def test_same_direction_only_cannot_satisfy_both_direction_authority():
    evidence = [_evidence(3, seed=index) for index in range(6)]
    estimate = _estimate(
        evidence,
        _requirements(directions={"LEFT_TO_RIGHT", "RIGHT_TO_LEFT"}),
    )
    assert not estimate.resolved
    assert "direction coverage" in estimate.refusal_reason


def test_single_speed_cannot_satisfy_multiple_speed_authority():
    evidence = [_evidence(3, seed=index, speed=2.0) for index in range(6)]
    estimate = _estimate(evidence, _requirements(speeds={2.0, 3.0}))
    assert not estimate.resolved
    assert "speed coverage" in estimate.refusal_reason


def test_caller_supplied_direction_speed_scene_requirements_are_enforced_and_can_pass():
    evidence = []
    for index, (direction, speed, scene) in enumerate(
        [
            ("LEFT_TO_RIGHT", 2.0, "NO_WALL"),
            ("RIGHT_TO_LEFT", 2.0, "NO_WALL"),
            ("LEFT_TO_RIGHT", 3.0, "NORMAL"),
            ("RIGHT_TO_LEFT", 3.0, "NORMAL"),
        ]
    ):
        evidence.append(_evidence(3, seed=index, direction=direction, speed=speed, scene=scene))
    estimate = _estimate(
        evidence,
        _requirements(
            directions={"LEFT_TO_RIGHT", "RIGHT_TO_LEFT"},
            speeds={2.0, 3.0},
            scenes={"NO_WALL", "NORMAL"},
        ),
    )
    assert estimate.resolved, estimate.refusal_reason


def test_mask_is_mandatory_boolean_and_shape_consistent():
    logged, rendered = _trajectory(3)
    common = ("t", logged, rendered, "LEFT_TO_RIGHT", 2.0, "NO_WALL")
    with pytest.raises(ValueError):
        AlignmentEvidence(*common, None, np.arange(260), np.arange(260))
    with pytest.raises(ValueError):
        AlignmentEvidence(*common, np.zeros(259, dtype=bool), np.arange(260), np.arange(260))
    with pytest.raises(ValueError):
        AlignmentEvidence(*common, np.zeros(260, dtype=int), np.arange(260), np.arange(260))


def test_nonfinite_observations_rejected_even_if_masked():
    logged, rendered = _trajectory(3)
    rendered[40] = np.nan
    mask = np.zeros(len(logged), dtype=bool)
    mask[40] = True
    with pytest.raises(ValueError):
        AlignmentEvidence("t", logged, rendered, "LEFT_TO_RIGHT", 2.0, "NO_WALL", mask, np.arange(260), np.arange(260))


def test_validated_evidence_is_detached_from_mutable_caller_arrays():
    logged, rendered = _trajectory(3)
    mask = np.zeros(len(logged), dtype=bool)
    ticks = np.arange(len(logged))
    frames = np.arange(len(logged))
    item = AlignmentEvidence(
        "t", logged, rendered, "LEFT_TO_RIGHT", 2.0, "NO_WALL",
        mask, ticks, frames,
    )
    logged[0] = np.nan
    rendered[0] = np.inf
    mask[0] = True
    ticks[1] = 10
    frames[1] = 10
    assert np.isfinite(item.logged_position).all()
    assert np.isfinite(item.rendered_position).all()
    assert not item.exclude_mask.any()
    assert np.array_equal(item.server_state_ticks, np.arange(len(logged)))
    assert np.array_equal(item.render_model_frame_indices, np.arange(len(logged)))
    with pytest.raises(ValueError):
        item.server_state_ticks[1] = 10


def test_duplicate_trajectories_fail_closed():
    estimate = _estimate([_evidence(3, seed=1), _evidence(3, seed=1)], _requirements(minimum=2))
    assert not estimate.measured and not estimate.resolved
    assert "not unique" in estimate.refusal_reason


@pytest.mark.parametrize("direction", ["LTR", "", None, "SIDEWAYS"])
def test_wrong_direction_labels_rejected(direction):
    logged, rendered = _trajectory(3)
    with pytest.raises(ValueError):
        AlignmentEvidence("t", logged, rendered, direction, 2.0, "NO_WALL", np.zeros(260, bool), np.arange(260), np.arange(260))


@pytest.mark.parametrize("speed", [0, -1, math.nan, math.inf])
def test_invalid_speeds_rejected(speed):
    logged, rendered = _trajectory(3)
    with pytest.raises(ValueError):
        AlignmentEvidence("t", logged, rendered, "LEFT_TO_RIGHT", speed, "NO_WALL", np.zeros(260, bool), np.arange(260), np.arange(260))


def test_insufficient_sample_support_fails_caller_requirement():
    evidence = [_evidence(3, seed=index, n=60) for index in range(4)]
    estimate = _estimate(evidence, _requirements(samples=55), max_lag=8)
    assert not estimate.resolved
    assert "usable support" in estimate.refusal_reason


def test_missing_uncertainty_request_cannot_satisfy_uncertainty_requirement():
    estimate = _estimate(
        [_evidence(3, seed=index) for index in range(6)],
        _requirements(),
        uncertainty=None,
    )
    assert not estimate.resolved
    assert "uncertainty" in estimate.refusal_reason


def test_t_and_trajectory_bootstrap_intervals_are_reported_when_requested():
    estimate = _estimate([_evidence(3, seed=index) for index in range(6)], _requirements())
    assert estimate.t_interval_ticks is not None
    assert estimate.trajectory_bootstrap_interval_ticks is not None
    assert estimate.t_interval_ticks[0] <= estimate.group_delay_ticks <= estimate.t_interval_ticks[1]


def test_exact_server_state_to_render_model_mapping_is_exposed():
    estimate = _estimate([_evidence(3, seed=index) for index in range(4)], _requirements())
    mapping = estimate.per_trajectory[0]["server_state_to_render_model_target_mapping"]
    assert mapping
    assert set(mapping[0]) == {"render_model_frame_index", "server_state_ticks_in_fir"}
    assert len(mapping[0]["server_state_ticks_in_fir"]) == 9
    assert mapping[0]["render_model_frame_index"] == 9
    assert mapping[0]["server_state_ticks_in_fir"] == list(range(9, 0, -1))


def test_server_ticks_spaced_by_ten_cannot_resolve_index_displacement_as_ticks():
    logged, rendered = _trajectory(3)
    n = len(logged)
    with pytest.raises(ValueError, match="unit spacing"):
        AlignmentEvidence(
            "t", logged, rendered, "LEFT_TO_RIGHT", 2.0, "NO_WALL",
            np.zeros(n, dtype=bool), np.arange(n) * 10, np.arange(n),
        )


def test_irregular_render_or_server_spacing_is_rejected():
    logged, rendered = _trajectory(3)
    n = len(logged)
    server_ticks = np.arange(n)
    server_ticks[50:] += 1
    with pytest.raises(ValueError, match="unit spacing"):
        AlignmentEvidence(
            "t", logged, rendered, "LEFT_TO_RIGHT", 2.0, "NO_WALL",
            np.zeros(n, dtype=bool), server_ticks, np.arange(n),
        )
    model_frames = np.arange(n)
    model_frames[80:] += 1
    with pytest.raises(ValueError, match="unit spacing"):
        AlignmentEvidence(
            "t", logged, rendered, "LEFT_TO_RIGHT", 2.0, "NO_WALL",
            np.zeros(n, dtype=bool), np.arange(n), model_frames,
        )


@pytest.mark.parametrize(
    "ticks",
    [
        lambda n: np.concatenate([np.arange(n - 1), [n - 2]]),
        lambda n: np.concatenate([np.arange(10), [11, 10], np.arange(12, n)]),
        lambda n: None,
    ],
)
def test_duplicate_nonmonotonic_or_missing_tick_coordinates_are_rejected(ticks):
    logged, rendered = _trajectory(3)
    n = len(logged)
    with pytest.raises(ValueError):
        AlignmentEvidence(
            "t", logged, rendered, "LEFT_TO_RIGHT", 2.0, "NO_WALL",
            np.zeros(n, dtype=bool), ticks(n), np.arange(n),
        )


def test_timebase_inconsistent_with_explicit_unit_mapping_is_invalid():
    estimate = estimate_alignment(
        [_evidence(3, seed=index) for index in range(4)],
        timebase=TimebaseSpec(0.05, 2),
        max_lag_ticks=8,
        requirements=_requirements(),
        uncertainty=UNCERTAINTY,
    )
    assert not estimate.measured and not estimate.resolved
    assert estimate.adjudication == "INVALID_EVIDENCE"
    assert "different cadence" in estimate.refusal_reason


def test_receipt_declares_real_entity_scope_and_unit_conversions():
    estimate = _estimate([_evidence(4, seed=index) for index in range(6)], _requirements()).require_resolved()
    assert estimate.receipt()["evidence_scope"] == EvidenceScope.REAL_ENTITY_RENDER_VS_STATE
    assert estimate.group_delay_seconds() == pytest.approx(estimate.group_delay_ticks * 0.05)
    assert estimate.group_delay_model_frames() == pytest.approx(estimate.group_delay_ticks)
