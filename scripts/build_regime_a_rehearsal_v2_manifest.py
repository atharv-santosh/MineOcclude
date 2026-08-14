#!/usr/bin/env python3
"""Build the v2 NON-SCIENTIFIC integration rehearsal manifest.

The rehearsal specs share the production camera, wall, lane, speed, noise, and
episode shape so they exercise the exact production capture path, but carry
independent non-scientific identity and seeds and can never enter Regime-A
results.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from mineocclude.regime_a import (  # noqa: E402
    MOTION_NOISE_Q,
    SPEED_BLOCKS_PER_SECOND,
    canonical_sha256,
    deterministic_seed,
    simulate_path,
    stable_hidden_interval,
)

STATUS = ROOT / "docs/status/integration/regime_a_occlusion_extraction_v0_1"
OUT = STATUS / "non_scientific_integration_rehearsal_manifest_v2.jsonl"
DOMAIN = "REHEARSAL_V2"
AUTHORITY = "regime-a-non-scientific-integration-rehearsal-v2"


def build(direction: str, episode_id: int, index: int) -> dict[str, object]:
    seed = deterministic_seed(DOMAIN, hashlib.sha256(AUTHORITY.encode()).hexdigest(), index)
    start = -7.80 if direction == "LEFT_TO_RIGHT" else 7.80
    positions, noise = simulate_path(seed, direction, start)
    entry, exit_frame = stable_hidden_interval(positions, direction)
    body: dict[str, object] = {
        "schema_version": "regime-a-integration-rehearsal-spec-v2.0",
        "NON_SCIENTIFIC_INTEGRATION_REHEARSAL": True,
        "ELIGIBLE_FOR_REGIME_A_RESULTS": False,
        "scientific_role": "NON_SCIENTIFIC_INTEGRATION_REHEARSAL",
        "execution_state": "NON_SCIENTIFIC_QUALIFICATION_ONLY",
        "trajectory_spec_id": f"regime_a_rehearsal_v2_{'ltr' if direction == 'LEFT_TO_RIGHT' else 'rtl'}",
        "episode_id": episode_id,
        "seed": seed,
        "noise_seed": seed,
        "direction": direction,
        "speed_blocks_per_second": SPEED_BLOCKS_PER_SECOND,
        "motion_noise_q": MOTION_NOISE_Q,
        "start_world_x": start,
        "start_world_y": 4.0,
        "start_world_z": 6.0,
        "expected_stable_hidden_onset_frame": entry,
        "expected_stable_hidden_exit_frame": exit_frame,
        "expected_tau_1_to_19_world_x": [float(v) for v in positions[entry : entry + 19]],
        "expected_profile_sha256": hashlib.sha256(np.asarray(positions, dtype="<f8").tobytes()).hexdigest(),
        "noise_schedule_sha256": hashlib.sha256(np.asarray(noise, dtype="<f8").tobytes()).hexdigest(),
        "expected_max_frames": len(positions),
        "target_entity_logical_id": f"regime_a_rehearsal_v2_{'ltr' if direction == 'LEFT_TO_RIGHT' else 'rtl'}:magenta_sheep",
        "camera_authority": "layout_01_fixed_v0.4",
        "wall_authority": "layout_01_long_wall_v0.4",
        "retry_policy": "IDENTICAL_SPEC_AND_SEED_ONLY",
    }
    body["spec_hash"] = canonical_sha256(body)
    return body


def main() -> int:
    rows = [
        build("LEFT_TO_RIGHT", 62001, 0),
        build("RIGHT_TO_LEFT", 62002, 1),
    ]
    with OUT.open("w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, sort_keys=True, allow_nan=False) + "\n")
    for row in rows:
        print(
            f"{row['trajectory_spec_id']:28s} dir={row['direction']:14s} "
            f"seed={row['seed']} episode={row['episode_id']} "
            f"onset={row['expected_stable_hidden_onset_frame']}"
        )
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
