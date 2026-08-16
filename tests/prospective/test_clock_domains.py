"""Clock-domain conversion and model-frame mapping."""

import math
import pytest

from mineocclude.prospective.clock_domains import (
    ClockDomain,
    DomainIndex,
    TimebaseSpec,
    UnresolvedAlignment,
    require_same_domain,
)


def test_domain_index_rejects_non_integer_and_negative():
    with pytest.raises(TypeError):
        DomainIndex(ClockDomain.SERVER_TICK, 3.0)
    with pytest.raises(TypeError):
        DomainIndex(ClockDomain.SERVER_TICK, True)
    with pytest.raises(ValueError):
        DomainIndex(ClockDomain.SERVER_TICK, -1)


def test_combining_distinct_domains_fails_closed():
    """The exact historical defect: server_tick treated as model_frame_idx."""
    tick = DomainIndex(ClockDomain.SERVER_TICK, 40)
    frame = DomainIndex(ClockDomain.MODEL_FRAME, 40)
    assert not tick.same_domain(frame)
    with pytest.raises(UnresolvedAlignment):
        require_same_domain(tick, frame)
    require_same_domain(tick, DomainIndex(ClockDomain.SERVER_TICK, 41))


def test_timebase_conversions_at_historical_cadence():
    base = TimebaseSpec(seconds_per_server_tick=0.05, server_ticks_per_model_frame=1)
    assert base.seconds_per_model_frame == pytest.approx(0.05)
    assert base.ticks_to_seconds(3.364) == pytest.approx(0.1682)
    assert base.seconds_to_ticks(0.1682) == pytest.approx(3.364)
    assert base.ticks_to_model_frames(3.364) == pytest.approx(3.364)


def test_model_frame_mapping_is_not_assumed_to_be_one_to_one():
    subsampled = TimebaseSpec(seconds_per_server_tick=0.05, server_ticks_per_model_frame=4)
    assert subsampled.seconds_per_model_frame == pytest.approx(0.2)
    assert subsampled.ticks_to_model_frames(8) == pytest.approx(2.0)
    assert subsampled.model_frames_to_ticks(2.0) == pytest.approx(8.0)


@pytest.mark.parametrize(
    "speed,expected_blocks",
    [(1.5, 0.2523), (2.0, 0.33640), (2.5, 0.42050), (3.0, 0.50460)],
)
def test_lag_ticks_to_world_blocks_scales_with_speed(speed, expected_blocks):
    """A lag constant in ticks is NOT constant in blocks; that asymmetry is
    what invalidated the fixed HIDDEN_BOUNDS constant above 2.0 blocks/s."""
    base = TimebaseSpec(0.05, 1)
    assert base.lag_ticks_to_blocks(3.364, speed) == pytest.approx(expected_blocks, abs=1e-4)


def test_invalid_timebase_rejected():
    with pytest.raises(ValueError):
        TimebaseSpec(seconds_per_server_tick=0.0, server_ticks_per_model_frame=1)
    with pytest.raises(ValueError):
        TimebaseSpec(seconds_per_server_tick=0.05, server_ticks_per_model_frame=0)
    with pytest.raises(TypeError):
        TimebaseSpec()


def test_invalid_domain_and_nonfinite_conversions_fail_closed():
    with pytest.raises(TypeError):
        DomainIndex("server_tick", 1)
    base = TimebaseSpec(0.05, 1)
    for bad in (math.nan, math.inf, -math.inf, True, "1"):
        with pytest.raises(ValueError):
            base.ticks_to_seconds(bad)
    with pytest.raises(ValueError):
        base.lag_ticks_to_blocks(3, 0)
