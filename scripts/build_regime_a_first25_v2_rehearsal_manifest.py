#!/usr/bin/env python3
"""Build two permanently ineligible first25-v2 production rehearsals."""

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
    V2_CALIBRATION,
    RegimeAError,
    canonical_sha256,
    deterministic_seed,
    sha256_file,
    simulate_path,
    stable_hidden_interval,
)

STATUS = ROOT / "docs/status/integration/regime_a_occlusion_extraction_v0_1/v2"
DOMAIN = "FIRST25_V2_NON_SCIENTIFIC_PRODUCTION_REHEARSAL"


def build(direction: str, episode_id: int, index: int) -> dict[str, object]:
    authority_hash = sha256_file(STATUS / "directional_visibility_authority.json")
    scientific = {
        json.loads(line)["seed"]
        for line in (STATUS / "trajectory_manifest.jsonl").read_text().splitlines()
        if line.strip()
    }
    candidate = index
    while True:
        seed = deterministic_seed(DOMAIN, authority_hash, candidate)
        candidate += 2
        if seed in scientific:
            continue
        start = -7.80 if direction == "LEFT_TO_RIGHT" else 7.80
        positions, noise = simulate_path(seed, direction, start)
        try:
            entry, exit_frame = stable_hidden_interval(positions, direction, V2_CALIBRATION)
        except RegimeAError:
            continue
        break
    short = "ltr" if direction == "LEFT_TO_RIGHT" else "rtl"
    identity = f"regime_a_first25_v2_rehearsal_{short}"
    body: dict[str, object] = {
        "schema_version": "regime-a-first25-v2-production-rehearsal-spec-v1.0",
        "NON_SCIENTIFIC_INTEGRATION_REHEARSAL": True,
        "ELIGIBLE_FOR_REGIME_A_RESULTS": False,
        "scientific_role": "NON_SCIENTIFIC_FIRST25_V2_PRODUCTION_REHEARSAL",
        "execution_state": "NON_SCIENTIFIC_QUALIFICATION_ONLY",
        "trajectory_spec_id": identity,
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
        "expected_tau_1_to_19_world_x": [float(value) for value in positions[entry : entry + 19]],
        "expected_profile_sha256": hashlib.sha256(
            np.asarray(positions, dtype="<f8").tobytes()
        ).hexdigest(),
        "noise_schedule_sha256": hashlib.sha256(
            np.asarray(noise, dtype="<f8").tobytes()
        ).hexdigest(),
        "expected_max_frames": len(positions),
        "entry_guard_frames": V2_CALIBRATION.entry_guard[direction],
        "exit_guard_frames": V2_CALIBRATION.exit_guard[direction],
        "visibility_calibration": V2_CALIBRATION.as_authority(),
        "expected_target_semantics": (
            "prospective conservative support forecast; target eligibility is independently "
            "reconciled against the frozen dual-visibility production path"
        ),
        "directional_visibility_authority_sha256": authority_hash,
        "scientific_manifest_sha256": sha256_file(STATUS / "trajectory_manifest.jsonl"),
        "target_entity_logical_id": f"{identity}:magenta_sheep",
        "camera_authority": "layout_01_fixed_v0.4",
        "wall_authority": "layout_01_long_wall_v0.4",
        "retry_policy": "IDENTICAL_SPEC_AND_SEED_ONLY",
    }
    body["spec_hash"] = canonical_sha256(body)
    return body


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = [
        build("LEFT_TO_RIGHT", 64001, 0),
        build("RIGHT_TO_LEFT", 64002, 1),
    ]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, sort_keys=True, allow_nan=False) + "\n")
    print(json.dumps({"status": "PASS", "count": 2, "output": str(args.output)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
