"""Create an immutable Regime A target audit report."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mineocclude.experiments.registry import (  # noqa: E402
    load_json_with_sha256,
    write_json_exclusive,
)
from mineocclude.oracle.audit import build_oracle_audit  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("target_document", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--artifact-id", required=True)
    parser.add_argument("--tolerance", type=float, default=1e-6)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    targets, _file_hash = load_json_with_sha256(args.target_document)
    report = build_oracle_audit(
        targets,
        artifact_id=args.artifact_id,
        tolerance=args.tolerance,
    )
    write_json_exclusive(args.output, report)


if __name__ == "__main__":
    main()
