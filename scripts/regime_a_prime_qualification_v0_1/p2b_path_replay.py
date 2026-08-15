"""P2.3: NON-SCIENTIFIC deterministic wall replay and epsilon_path authority.

The original NVMe capture runtime was wiped between P1 and P2, so the runtime
was rebuilt (Corretto 17.0.20.8.1, one of the two JVMs the frozen provisioning
gate approves; system Xvfb/openbox/xdotool in place of the wiped operator-tools
bundle). Runtime identity therefore cannot be assumed and is measured here.

This replays ORIGINAL WALL specifications under the rebuilt runtime and compares
the realized sheep path against the historical wall coordinates. It produces no
neural outcome and touches no P2 no-wall data.

Unit selection is made WITHOUT any neural outcome: one LEFT_TO_RIGHT and one
RIGHT_TO_LEFT specification. Direction is the only factor that changes the sign
of the motion recurrence, so two units cover the materially distinct motion
behaviour; replaying all 25 would add cost without adding a distinct mechanism.
"""

from __future__ import annotations

import json
import time
from typing import Any

import numpy as np

from p2_common import (
    OUT,
    WORK,
    CaptureSession,
    expected_path,
    p2_episode_id,
    read_jsonl,
    run_git,
    source_specs,
    wall_coordinates,
    write_json,
)

# Episode ids for the non-scientific replay, disjoint from both the historical
# 52001..52025 range and the P2 scientific 61001..61025 range.
REPLAY_EPISODE_BASE = 60000


def select_units(specs: list[dict]) -> list[dict]:
    """First specification of each direction, by deterministic id order."""
    chosen: list[dict] = []
    for direction in ("LEFT_TO_RIGHT", "RIGHT_TO_LEFT"):
        match = next((s for s in specs if s["direction"] == direction), None)
        if match is None:
            raise RuntimeError(f"no source specification with direction {direction}")
        chosen.append(match)
    return chosen


def main() -> int:
    specs = source_specs()
    units = select_units(specs)
    root = WORK / "path_replay"
    root.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []
    started = time.monotonic()

    with CaptureSession("normal") as session:
        for spec in units:
            spec_id = str(spec["trajectory_spec_id"])
            episode = REPLAY_EPISODE_BASE + int(spec_id.rsplit("t", 1)[1])
            destination = root / spec_id
            info = session.capture(spec, episode, destination)

            state = read_jsonl(destination / "raw/server_state.jsonl")
            if len(state) != info["frames"]:
                raise RuntimeError(f"replay cardinality mismatch for {spec_id}")
            scenes = {row.get("scene") for row in state}
            if scenes != {"NORMAL"}:
                raise RuntimeError(f"replay scene mismatch for {spec_id}: {scenes}")

            replay = np.asarray([float(r["sheep_x"]) for r in state], dtype=np.float64)
            historical_map = wall_coordinates(spec_id)
            historical = np.asarray(
                [historical_map[i] for i in range(len(replay))], dtype=np.float64
            )
            analytic = np.asarray(expected_path(spec, info["schedule"]), dtype=np.float64)

            diff_hist = np.abs(replay - historical)
            diff_analytic = np.abs(replay - analytic)
            results.append({
                "trajectory_spec_id": spec_id,
                "direction": spec["direction"],
                "replay_episode_id": episode,
                "frames": int(len(replay)),
                "max_abs_diff_vs_historical_wall": float(diff_hist.max()),
                "mean_abs_diff_vs_historical_wall": float(diff_hist.mean()),
                "n_frames_bitwise_identical": int((replay == historical).sum()),
                "bitwise_identical_all_frames": bool((replay == historical).all()),
                "max_abs_diff_vs_analytic_recurrence": float(diff_analytic.max()),
                "capture_seconds": info["capture_seconds"],
            })

    aggregate_max = max(r["max_abs_diff_vs_historical_wall"] for r in results)
    all_exact = all(r["bitwise_identical_all_frames"] for r in results)

    # Stored-coordinate quantization: the capture stores IEEE-754 doubles in
    # JSON text, so the representable granularity near the lane extent is the
    # double ULP at |x| <= 8.
    quantization = float(np.spacing(np.float64(8.0)))

    if all_exact:
        epsilon_path = 0.0
        basis = (
            "EXACT_DETERMINISTIC_IDENTITY: every replayed frame reproduced the "
            "historical wall coordinate bit-for-bit, so exact equality is required"
        )
        rule = "EXACT_EQUALITY_REQUIRED"
    else:
        epsilon_path = max(quantization, aggregate_max)
        basis = (
            "max(stored_coordinate_quantization_unit, observed_repeatability_envelope)"
        )
        rule = "ABS_DIFFERENCE_AT_OR_BELOW_EPSILON_PATH"

    payload = {
        "artifact_id": "regime-a-prime-p2-path-equivalence-authority-v0.1",
        "schema_version": "1.0",
        "phase": "P2",
        "classification": "NON_SCIENTIFIC_PATH_REPEATABILITY_QUALIFICATION",
        "status": "PASS" if all_exact or aggregate_max < 1e-6 else "REVIEW",
        "frozen_before_any_p2_no_wall_outcome": True,
        "neural_outcomes_used_in_unit_selection": False,
        "neural_outcomes_used_in_epsilon_choice": False,
        "source_p1_commit": run_git("rev-parse", "HEAD"),
        "runtime_rebuild": {
            "reason": "the NVMe capture runtime was wiped between P1 and P2",
            "java": "Amazon Corretto 17.0.20.8.1 (build 17.0.20+8-LTS)",
            "java_approved_by_frozen_gate": True,
            "gate_weakened": False,
            "native_tools": "system Xvfb/openbox/xdotool/xdpyinfo replacing the wiped "
                            "operator-tools bundle; the frozen provisioning script "
                            "falls back to system tools by design",
            "server_and_client_trees": "original durable $HOME trees, unmodified",
        },
        "unit_selection_rule": "first specification of each direction in deterministic "
                               "id order; direction is the only factor that flips the "
                               "sign of the motion recurrence",
        "units": results,
        "aggregate_max_abs_diff_vs_historical_wall": aggregate_max,
        "all_replayed_frames_bitwise_identical": all_exact,
        "stored_coordinate_quantization_unit": quantization,
        "epsilon_path": epsilon_path,
        "epsilon_path_basis": basis,
        "path_equivalence_rule": rule,
        "motion_determinism_note":
            "The sheep path is a clamped cumulative recurrence over the immutable "
            "per-tick noise schedule; the wall occupies z=2 while the lane is z=6, so "
            "wall removal cannot enter the recurrence.",
        "replay_wall_clock_seconds": time.monotonic() - started,
        "wall_trajectories_recollected_for_science": 0,
        "replay_is_nonscientific_and_excluded_from_all_p2_results": True,
    }

    digest = write_json(OUT / "p2_path_equivalence_authority.json", payload)
    print(f"P2_PATH_AUTHORITY_STATUS={payload['status']}")
    print(f"P2_PATH_AUTHORITY_SHA256={digest}")
    for r in results:
        print(f"  {r['trajectory_spec_id']} {r['direction']}: "
              f"max|diff|={r['max_abs_diff_vs_historical_wall']:.3e} "
              f"exact={r['bitwise_identical_all_frames']} "
              f"({r['n_frames_bitwise_identical']}/{r['frames']} frames)")
    print(f"EPSILON_PATH={epsilon_path}")
    print(f"EPSILON_PATH_BASIS={basis}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
