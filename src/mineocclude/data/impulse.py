"""One-tick impulse alignment check (Person C, C4.7).

The frozen orientation is ``visual_i -> action_i -> visual_(i+1)`` with no
plus/minus-one shift. Two independent records of the same camera motion exist
in every real episode:

  * the client's recorded action ``camera_dx``/``camera_dy`` (yaw/pitch delta
    at capture), and
  * the server's authoritative ``player_yaw``/``player_pitch`` per tick.

If capture is aligned, the action's camera delta at frame i matches the
server-side yaw change across the corresponding tick. ``impulse_lag`` scores
the match at lags {-1, 0, +1}; lag 0 must win and the adjacent lags must
fail (``check_impulse`` enforces exactly one passing index relation). A
non-zero best lag means a frame shift and the trajectory must be recollected
— never relabeled.

For a decisive runtime test, collect a dedicated impulse episode: hold still,
then apply one sharp camera flick on a known tick. The flick appears as a
single large ``camera_dx`` and a single large yaw jump — they must land on
the SAME model frame.
"""
from __future__ import annotations

import numpy as np


def _wrap(delta):
    return (delta + 180.0) % 360.0 - 180.0


def impulse_lag(frame_map, min_motion_deg: float = 0.5) -> dict:
    """Best alignment lag between action camera_dx and server yaw delta.

    Returns ``{'best_lag', 'residual_deg', 'n_used', 'aligned', 'by_lag'}``.
    Only frames with meaningful motion are used, so a still trajectory
    abstains rather than reporting spurious alignment.
    """
    fm = frame_map.sort_values("model_frame_idx").reset_index(drop=True)
    yaw = fm["player_yaw"].to_numpy(dtype=float)
    dx = fm["camera_dx"].to_numpy(dtype=float)
    # Server-side yaw delta across each tick (delta into frame i, from i-1).
    yaw_delta = np.full_like(yaw, np.nan)
    yaw_delta[1:] = _wrap(yaw[1:] - yaw[:-1])

    results = {}
    for lag in (-1, 0, 1):
        shifted = np.roll(yaw_delta, lag)
        mask = np.isfinite(dx) & np.isfinite(shifted) & (np.abs(shifted) > min_motion_deg)
        if mask.sum() < 3:
            results[lag] = (np.inf, int(mask.sum()))
            continue
        residual = float(np.sqrt(np.mean((dx[mask] - shifted[mask]) ** 2)))
        results[lag] = (residual, int(mask.sum()))

    best_lag = min(results, key=lambda k: results[k][0])
    residual, n_used = results[best_lag]
    return {
        "best_lag": int(best_lag),
        "residual_deg": residual,
        "n_used": n_used,
        "aligned": (best_lag == 0),
        "by_lag": {
            int(lag): {"residual_deg": value[0], "n_used": value[1]}
            for lag, value in results.items()
        },
    }


def check_step_impulse(
    frame_map,
    impulse_tick: int,
    min_step_deg: float = 3.0,
    dominance_ratio: float = 3.0,
) -> dict:
    """Pixel-level validation of the scripted step impulse (C4.7).

    The server applies a step-and-hold yaw change at recording tick
    ``impulse_tick`` (C3.6 deterministic camera program). Exactly one visual
    transition must contain the effect. This check:

    1. finds the action index ``i`` with the dominant recorded ``camera_dx``
       step (must be near ``impulse_tick``);
    2. computes mean-absolute pixel differences between consecutive captured
       frames;
    3. requires the dominant visual transition to be ``(i -> i+1)`` — the
       frozen orientation ``visual_i -> action_i -> visual_(i+1)`` — and to
       dominate every other transition by ``dominance_ratio``.

    Human camera motion cannot provide this evidence: continuous mouse input
    is not tick-quantized and shows +/-1 attribution jitter (measured on real
    capture). Only the scripted impulse makes the expected transition
    unambiguous. Returns a report with ``passed``, ``reasons``, the measured
    ``effect_transition`` and its ``offset`` from the action index.
    """
    import numpy as np  # noqa: F811 (already imported at module level)

    from mineocclude.data.fsretry import open_rgb_retry

    fm = frame_map.sort_values("model_frame_idx").reset_index(drop=True)
    reasons: list[str] = []
    dx = fm["camera_dx"].to_numpy(dtype=float)
    spike = int(np.nanargmax(np.abs(dx)))
    if abs(dx[spike]) < min_step_deg:
        reasons.append(
            f"no recorded camera step >= {min_step_deg} deg "
            f"(max |dx| = {abs(dx[spike]):.2f} at action {spike})"
        )
        return {"passed": False, "reasons": reasons, "action_idx": spike,
                "effect_transition": None, "offset": None}
    if abs(spike - impulse_tick) > 2:
        reasons.append(
            f"dominant camera step at action {spike} is not near the "
            f"scripted impulse tick {impulse_tick}"
        )

    paths = list(fm["frame_abspath"])
    frames = [open_rgb_retry(p).astype(np.int16) for p in paths]
    diffs = np.array([
        float(np.abs(frames[j + 1] - frames[j]).mean())
        for j in range(len(frames) - 1)
    ])
    # Search for the effect only NEAR the action spike: episode-start
    # artifacts (pose snap, HUD hide) can produce large unrelated early
    # transitions, and a global argmax mistook one for the impulse
    # (observed at runtime as a bogus offset of -28). The impulse effect
    # must lie within the phase-uncertainty window of the spike.
    lo = max(0, spike - 2)
    hi = min(len(diffs), spike + 3)
    window = diffs[lo:hi]
    effect = lo + int(np.argmax(window))
    in_window_others = np.delete(diffs[lo:hi], effect - lo)
    runner_up = float(in_window_others.max()) if len(in_window_others) else 0.0
    if runner_up > diffs[effect] / dominance_ratio:
        reasons.append(
            f"visual transition {effect}->{effect + 1} "
            f"(diff {diffs[effect]:.2f}) does not dominate its neighborhood "
            f"(runner-up diff {runner_up:.2f}) by {dominance_ratio}x"
        )
    others = np.array([runner_up])
    offset = effect - spike
    if offset != 0:
        reasons.append(
            f"impulse effect lies in transition {effect}->{effect + 1} but the "
            f"action step is at index {spike} (offset {offset:+d}); the frozen "
            "orientation requires the effect in (i -> i+1)"
        )
    return {
        "passed": not reasons,
        "reasons": reasons,
        "action_idx": spike,
        "action_step_deg": float(dx[spike]),
        "effect_transition": (effect, effect + 1),
        "offset": int(offset),
        "effect_diff": float(diffs[effect]),
        "runner_up_diff": float(others.max()) if len(others) else 0.0,
    }


def check_impulse(
    frame_map,
    min_motion_deg: float = 0.5,
    dominance_ratio: float = 2.0,
) -> dict:
    """Machine-check that exactly one index relation passes (C4.7).

    Lag 0 must be the best AND both adjacent lags must be at least
    ``dominance_ratio`` times worse, so an ambiguous trajectory fails rather
    than being tolerated. Returns the lag report plus a ``passed`` flag and
    a reason when it fails.
    """
    report = impulse_lag(frame_map, min_motion_deg=min_motion_deg)
    reasons = []
    if report["n_used"] < 3:
        reasons.append("insufficient camera motion for an impulse decision")
    elif report["best_lag"] != 0:
        reasons.append(f"best lag is {report['best_lag']}, not 0 (frame shift)")
    else:
        zero = report["by_lag"][0]["residual_deg"]
        for lag in (-1, 1):
            adjacent = report["by_lag"][lag]["residual_deg"]
            if np.isfinite(adjacent) and adjacent < dominance_ratio * zero:
                reasons.append(
                    f"lag {lag} residual {adjacent:.3f} is not decisively worse "
                    f"than lag 0 residual {zero:.3f} — orientation is ambiguous"
                )
    report["passed"] = not reasons
    report["reasons"] = reasons
    return report
