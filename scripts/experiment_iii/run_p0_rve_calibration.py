"""I07 — P0 RVE calibration driver. Plan/validate only in this build.

The P0 capture campaign is stage A4 and is NOT authorized here. Without captured
frames this reports the frozen P0 design and refuses to run the campaign.

    python scripts/experiment_iii/run_p0_rve_calibration.py --plan-only
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from mineocclude.experiment_iii.authority import verify_authority_binding  # noqa: E402
from mineocclude.experiment_iii.conditions import (  # noqa: E402
    ELIGIBLE_STAINED_GLASS,
    PROSPECTIVELY_EXCLUDED_MATERIALS,
    STONE,
)
from mineocclude.experiment_iii.errors import ExperimentIIIError  # noqa: E402
from mineocclude.experiment_iii.placements import (  # noqa: E402
    placement_coordinates,
    placement_manifest,
    sentinel_placement_indices,
)
from mineocclude.experiment_iii.rve import (  # noqa: E402
    ABBA_BLOCKS,
    ADJACENT_SEPARATION_MIN,
    BOOTSTRAP_REPLICATES,
    L3_SNR_MIN,
    LADDER_ZONES,
    PLACEMENT_COUNT,
    REPLICATE_CV_MAX,
    TARGET_RVE_POINTS,
)
from mineocclude.experiment_iii.schema import write_json_atomic  # noqa: E402

DEFAULT_OUT = REPOSITORY_ROOT / "docs" / "experiment_iii" / "a1_receipts"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan-only", action="store_true", default=True)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)

    if not args.plan_only:
        print(
            "BLOCKER_CODE=P2_PREREQUISITE_NOT_PASSED\n"
            "the P0 capture campaign is stage A4 and is not authorized by this task",
            file=sys.stderr,
        )
        return 1
    try:
        binding = verify_authority_binding()
    except ExperimentIIIError as error:
        print(f"BLOCKER_CODE={error.blocker}", file=sys.stderr)
        return 1

    conditions = 1 + len(ELIGIBLE_STAINED_GLASS) + 1  # L0 + 12 candidates + stone
    body = {
        "schema_version": "mineocclude-experiment-iii-p0-manifest-v1",
        "authority_section": "7.1-7.8",
        "authority_binding": binding,
        "placements": PLACEMENT_COUNT,
        "conditions_measured": conditions,
        "candidate_roster": list(ELIGIBLE_STAINED_GLASS),
        "roster_size": len(ELIGIBLE_STAINED_GLASS),
        "opaque_anchor": STONE,
        "prospective_exclusions": list(PROSPECTIVELY_EXCLUDED_MATERIALS),
        "abba_blocks": [list(block) for block in ABBA_BLOCKS],
        "replicate_blocks_per_cell": len(ABBA_BLOCKS),
        "min_settled_frames_per_state_per_block": 8,
        "ladder_zones": {key: list(value) for key, value in LADDER_ZONES.items()},
        "adjacent_separation_min": ADJACENT_SEPARATION_MIN,
        "l3_snr_min": L3_SNR_MIN,
        "replicate_cv_max": REPLICATE_CV_MAX,
        "bootstrap_replicates": BOOTSTRAP_REPLICATES,
        "target_rve_points": list(TARGET_RVE_POINTS),
        "selection_rule": "MIN_SQUARED_DISTANCE_THEN_LEXICOGRAPHIC_REGISTRY_ID",
        "source": "RAW_SOURCE_RGB_640x360_NEVER_MODEL_NORMALIZED",
        "mask_rule": "ONE_PER_PLACEMENT_FROM_L0_SHARED_BY_EVERY_CANDIDATE",
        # Authority 7.2 delegates the nine placement coordinates to A1; they are
        # computed from the frozen occluded-lane corridor, never hand-picked.
        "placement_coordinates": [dict(p) for p in placement_coordinates()],
        "sentinel_placement_indices": list(sentinel_placement_indices()),
        "p0_executed": False,
    }
    placements = placement_manifest()
    placement_digest = write_json_atomic(
        args.out / "p0_placement_manifest.json", placements
    )
    body["p0_placement_manifest_sha256"] = placement_digest
    digest = write_json_atomic(args.out / "p0_manifest.json", body)
    print(f"PLACEMENTS={PLACEMENT_COUNT}")
    print(f"CONDITIONS_MEASURED={conditions}")
    print(f"PLACEMENTS_SHA256={placements['placements_sha256']}")
    print(f"P0_PLACEMENT_MANIFEST_SHA256={placement_digest}")
    print(f"P0_MANIFEST_SHA256={digest}")
    print("P0_EXECUTED=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
