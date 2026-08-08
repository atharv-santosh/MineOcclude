#!/usr/bin/env python3
"""Run only the current 66-cell no-wall positive-control repair."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mineocclude.analysis.no_wall_positive_control_66_cell_v0_1 import (  # noqa: E402
    RUN_ID,
    run_current_positive_control,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, default=ROOT)
    parser.add_argument(
        "--production-root",
        type=Path,
        default=Path("/mnt/sagemaker-nvme/mineocclude/phase6") / RUN_ID,
    )
    args = parser.parse_args()
    result = run_current_positive_control(
        repository=args.repository,
        production_root=args.production_root,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
