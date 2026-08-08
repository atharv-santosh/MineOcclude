#!/usr/bin/env python3
"""Validate the blocked Person B U4 event/request preparation package.

Validation-only: no U4 outputs, intervention measurements, model activations,
or scientific outcomes are read or produced.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from mineocclude.analysis.u4_event_selection_intervention_request_v1_0 import (
    PACKAGE_DIRECTORY,
    U4EventRequestError,
    validate_package,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=ROOT,
        help="Person B repository containing the package and Git authorities.",
    )
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()
    repository_root = args.repository_root.resolve()
    package_root = repository_root / PACKAGE_DIRECTORY
    try:
        result = validate_package(package_root, repository_root)
    except (OSError, U4EventRequestError, ValueError) as error:
        print(f"PERSON_B_U4_EVENT_REQUEST_VALIDATION=FAIL {error}", file=sys.stderr)
        return 1
    if not args.quiet:
        print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
