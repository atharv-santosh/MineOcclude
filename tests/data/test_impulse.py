"""C4.7 one-tick impulse tests: lag 0 must win, adjacent lags must fail."""

import numpy as np
import pandas as pd

import mineocclude.contracts  # noqa: F401  (pre-existing import-order cycle)
from mineocclude.data.impulse import check_impulse, impulse_lag


def _impulse_frame_map(n=20, impulses=(5, 10, 15), shift=0):
    """Synthetic trajectory: yaw jumps at known ticks, camera_dx recorded at
    the same frame (or shifted by ``shift`` frames to model a capture bug)."""
    yaw = np.zeros(n)
    dx = np.zeros(n)
    for tick in impulses:
        yaw[tick:] += 7.0
        dx[tick] = 7.0
    if shift:
        dx = np.roll(dx, shift)
    return pd.DataFrame({
        "model_frame_idx": range(n),
        "player_yaw": yaw,
        "camera_dx": dx,
    })


def test_aligned_trajectory_passes():
    report = check_impulse(_impulse_frame_map())
    assert report["best_lag"] == 0
    assert report["aligned"]
    assert report["passed"], report["reasons"]


def test_plus_one_shift_fails():
    report = check_impulse(_impulse_frame_map(shift=1))
    assert report["best_lag"] != 0
    assert not report["passed"]


def test_minus_one_shift_fails():
    report = check_impulse(_impulse_frame_map(shift=-1))
    assert report["best_lag"] != 0
    assert not report["passed"]


def test_still_trajectory_abstains_and_fails():
    fm = pd.DataFrame({
        "model_frame_idx": range(10),
        "player_yaw": np.zeros(10),
        "camera_dx": np.zeros(10),
    })
    report = check_impulse(fm)
    assert not report["passed"]
    assert any("insufficient" in reason for reason in report["reasons"])


def test_exactly_one_index_relation_passes():
    """C4.7: the aligned relation passes and both adjacent relations fail."""
    aligned = check_impulse(_impulse_frame_map())
    assert aligned["passed"]
    for shift in (-1, 1):
        assert not check_impulse(_impulse_frame_map(shift=shift))["passed"]


def test_impulse_lag_reports_all_lags():
    report = impulse_lag(_impulse_frame_map())
    assert set(report["by_lag"]) == {-1, 0, 1}
    assert report["by_lag"][0]["residual_deg"] < report["by_lag"][1]["residual_deg"]
    assert report["by_lag"][0]["residual_deg"] < report["by_lag"][-1]["residual_deg"]
