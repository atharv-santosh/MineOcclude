"""Publish Person D's exact Person B row/fold baseline request."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mineocclude.analysis.handoffs import build_d_baseline_request  # noqa: E402
from mineocclude.experiments.registry import (  # noqa: E402
    load_json_with_sha256,
    write_json_exclusive,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("frame_table", type=Path)
    parser.add_argument("fold_manifest", type=Path)
    parser.add_argument("selection_manifest", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--artifact-id", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    frame_table, _ = load_json_with_sha256(args.frame_table)
    fold_manifest, _ = load_json_with_sha256(args.fold_manifest)
    selection_manifest, _ = load_json_with_sha256(args.selection_manifest)
    request = build_d_baseline_request(
        frame_table,
        fold_manifest,
        selection_manifest,
        artifact_id=args.artifact_id,
    )
    write_json_exclusive(args.output, request)


if __name__ == "__main__":
    main()
