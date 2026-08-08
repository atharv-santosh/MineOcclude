"""Record Person B's explicit visible-control decision without overwriting."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mineocclude.analysis.pilot import build_positive_control_gate  # noqa: E402
from mineocclude.experiments.registry import (  # noqa: E402
    load_json_with_sha256,
    write_json_exclusive,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Seal the human scientific decision for one exact visible no-wall "
            "probe bundle."
        )
    )
    parser.add_argument("control_bundle", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument(
        "--decision",
        required=True,
        choices=["pass", "stop_for_diagnosis"],
    )
    parser.add_argument("--approver", required=True)
    parser.add_argument("--rationale", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    control_bundle, _file_hash = load_json_with_sha256(args.control_bundle)
    gate = build_positive_control_gate(
        control_bundle,
        decision=args.decision,
        approver=args.approver,
        rationale=args.rationale,
    )
    write_json_exclusive(args.output, gate)


if __name__ == "__main__":
    main()
