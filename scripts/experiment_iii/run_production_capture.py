"""I04 — production capture driver (plan/validate only in this build).

Emits the frozen 125-unit capture plan and its 25 condition batches, and validates
the Latin balance and capture-order determinism. It does NOT launch Minecraft:
production capture is stage A7 and is not authorized here.

    python scripts/experiment_iii/run_production_capture.py --plan-only
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from mineocclude.experiment_iii.authority import verify_authority_binding  # noqa: E402
from mineocclude.experiment_iii.capture_schedule import (  # noqa: E402
    build_capture_schedule,
    condition_batches,
    validate_capture_order,
)
from mineocclude.experiment_iii.conditions import build_condition_map  # noqa: E402
from mineocclude.experiment_iii.errors import ExperimentIIIError  # noqa: E402
from mineocclude.experiment_iii.schema import read_jsonl, write_json_atomic  # noqa: E402

COHORT = REPOSITORY_ROOT / "docs" / "experiment_iii" / "cohort"
DEFAULT_OUT = REPOSITORY_ROOT / "docs" / "experiment_iii" / "capture"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--plan-only",
        action="store_true",
        default=True,
        help="the only supported mode here; A7 capture is not authorized",
    )
    parser.add_argument(
        "--ladder",
        type=Path,
        help="P0_SELECTED_LADDER json mapping L1/L2/L3 to registry IDs",
    )
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)

    if not args.plan_only:
        print(
            "BLOCKER_CODE=P2_PREREQUISITE_NOT_PASSED\n"
            "production capture is stage A7 and is not authorized by this task",
            file=sys.stderr,
        )
        return 1

    try:
        binding = verify_authority_binding()
        ladder = (
            json.loads(args.ladder.read_text(encoding="utf-8"))
            if args.ladder
            else None
        )
        conditions = build_condition_map(ladder)
        production = read_jsonl(COHORT / "production_identity_manifest.jsonl")
        schedule = build_capture_schedule(production, conditions)
        report = validate_capture_order(schedule)
        batches = condition_batches(schedule)
    except ExperimentIIIError as error:
        print(f"BLOCKER_CODE={error.blocker}", file=sys.stderr)
        print(error.message, file=sys.stderr)
        return 1

    digest = write_json_atomic(
        args.out / "capture_schedule.json",
        {
            "schema_version": "mineocclude-experiment-iii-capture-schedule-v1",
            "authority_section": "8.1",
            "authority_binding": binding,
            "conditions": {
                condition.value: spec.as_dict()
                for condition, spec in conditions.items()
            },
            "validation": report,
            "condition_batches": batches,
            "captures": [unit.as_dict() for unit in schedule],
        },
    )
    print(f"CAPTURES={report['captures']}")
    print(f"CONDITION_BATCHES={report['condition_batches']}")
    print(f"WALL_MATERIAL_TRANSITIONS={report['wall_material_transitions']}")
    print(f"CAPTURE_SCHEDULE_SHA256={digest}")
    print("CAPTURE_EXECUTED=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
