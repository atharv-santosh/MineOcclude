"""Freeze Person B's real layout folds from accepted Person C evidence."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mineocclude.analysis.layout_fold_plan import (  # noqa: E402
    build_layout_fold_plan,
)
from mineocclude.experiments.registry import (  # noqa: E402
    load_json_with_sha256,
    write_json_exclusive,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Freeze five deterministic layout-grouped folds using only "
            "accepted Person C condition rows."
        )
    )
    parser.add_argument("condition_selection_source", type=Path)
    parser.add_argument("capture_intake_report", type=Path)
    parser.add_argument("output_path", type=Path)
    parser.add_argument(
        "--artifact-id",
        default="person_b_c_layout_fold_plan_2026_07_28",
    )
    return parser.parse_args()


def execute(args: argparse.Namespace) -> None:
    condition_source, condition_file_hash = load_json_with_sha256(
        args.condition_selection_source
    )
    intake_report, intake_file_hash = load_json_with_sha256(
        args.capture_intake_report
    )
    plan = build_layout_fold_plan(
        condition_source,
        intake_report,
        artifact_id=args.artifact_id,
        condition_source_file_hash=condition_file_hash,
        capture_intake_file_hash=intake_file_hash,
    )
    write_json_exclusive(args.output_path, plan)


def main() -> None:
    execute(parse_args())


if __name__ == "__main__":
    main()
