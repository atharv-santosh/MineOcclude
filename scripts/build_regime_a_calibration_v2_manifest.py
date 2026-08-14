#!/usr/bin/env python3
"""Build prospective, permanently ineligible Regime-A v2 calibration specs."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mineocclude.regime_a import (  # noqa: E402
    MOTION_NOISE_Q,
    SPEED_BLOCKS_PER_SECOND,
    canonical_sha256,
    deterministic_seed,
    simulate_path,
)

AUTHORITY = "regime-a-qualified-directional-calibration-v2"
DOMAIN = "NON_SCIENTIFIC_CALIBRATION_V2"


def build(direction: str, replicate: int, episode_id: int) -> dict[str, object]:
    short = "ltr" if direction == "LEFT_TO_RIGHT" else "rtl"
    identity = f"regime_a_calibration_v2_{short}_r{replicate:02d}"
    authority_hash = hashlib.sha256(AUTHORITY.encode()).hexdigest()
    domain_index = (0 if direction == "LEFT_TO_RIGHT" else 100) + replicate
    seed = deterministic_seed(DOMAIN, authority_hash, domain_index)
    start = -7.80 if direction == "LEFT_TO_RIGHT" else 7.80
    positions, noise = simulate_path(seed, direction, start)
    body: dict[str, object] = {
        "schema_version": "regime-a-directional-calibration-spec-v2.0",
        "NON_SCIENTIFIC_CALIBRATION": True,
        "ELIGIBLE_FOR_REGIME_A_RESULTS": False,
        "scientific_role": "NON_SCIENTIFIC_DIRECTIONAL_CALIBRATION",
        "execution_state": "NON_SCIENTIFIC_QUALIFICATION_ONLY",
        "trajectory_spec_id": identity,
        "episode_id": episode_id,
        "seed": seed,
        "noise_seed": seed,
        "direction": direction,
        "calibration_replicate": replicate,
        "speed_blocks_per_second": SPEED_BLOCKS_PER_SECOND,
        "motion_noise_q": MOTION_NOISE_Q,
        "start_world_x": start,
        "start_world_y": 4.0,
        "start_world_z": 6.0,
        "expected_profile_sha256": hashlib.sha256(
            np.asarray(positions, dtype="<f8").tobytes()
        ).hexdigest(),
        "noise_schedule_sha256": hashlib.sha256(
            np.asarray(noise, dtype="<f8").tobytes()
        ).hexdigest(),
        "expected_max_frames": len(positions),
        "target_entity_logical_id": f"{identity}:magenta_sheep",
        "camera_authority": "layout_01_fixed_v0.4",
        "wall_authority": "layout_01_long_wall_v0.4",
        "capture_protocol": "capture_ack_lockstep",
        "retry_policy": "IDENTICAL_SPEC_AND_SEED_ONLY",
    }
    body["spec_hash"] = canonical_sha256(body)
    return body


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = [
        build("LEFT_TO_RIGHT", 1, 63001),
        build("LEFT_TO_RIGHT", 2, 63002),
        build("RIGHT_TO_LEFT", 1, 63003),
        build("RIGHT_TO_LEFT", 2, 63004),
    ]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, sort_keys=True, allow_nan=False) + "\n")
    print(json.dumps({"count": len(rows), "output": str(args.output)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
