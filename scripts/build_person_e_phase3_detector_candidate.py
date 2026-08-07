"""Build Person E Phase 3 Detector v1 candidate-freeze evidence."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mineocclude.vision.phase3_detector_candidate import (
    build_candidate_evidence,
    write_candidate_evidence,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Freeze the development-only Detector v1 candidate. This command "
            "does not open or evaluate an untouched test package."
        )
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--freeze-timestamp-utc",
        required=True,
        help=(
            "Explicit ISO-8601 UTC freeze value reused unchanged for every "
            "deterministic regeneration."
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payloads = build_candidate_evidence(
        ROOT,
        freeze_timestamp_utc=args.freeze_timestamp_utc,
    )
    write_candidate_evidence(args.output_dir, payloads)


if __name__ == "__main__":
    main()
