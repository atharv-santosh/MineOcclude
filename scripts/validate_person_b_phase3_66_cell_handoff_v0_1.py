#!/usr/bin/env python3
"""Validate the additive Person B 66-cell C-consumer handoff."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPOSITORY_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from mineocclude.analysis.phase3_66_cell_validation_v0_1 import (
    PACKAGE_DIRECTORY,
    Phase3ValidationError,
    validate_package,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=REPOSITORY_ROOT,
        help="repository containing the exact C Git objects and B package",
    )
    parser.add_argument(
        "--package-root",
        type=Path,
        default=None,
        help=f"optional package root (default: <repository>/{PACKAGE_DIRECTORY})",
    )
    parser.add_argument("--json", action="store_true", help="emit validation evidence")
    args = parser.parse_args()
    try:
        result = validate_package(args.repository_root.resolve(), args.package_root)
    except (Phase3ValidationError, OSError, ValueError) as error:
        if args.json:
            print(json.dumps({"status": "FAIL", "error": str(error)}, sort_keys=True))
        else:
            print(f"FAIL: {error}", file=sys.stderr)
        return 1
    result["status"] = "PASS"
    if args.json:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    else:
        print("PASS: Person B 66-cell C consumer and Step 3.3 evidence validated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
