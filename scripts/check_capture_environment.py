"""Check the Person C capture environment lock without launching Minecraft."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from mineocclude.data.environment_lock import (
    load_environment_lock,
    validate_environment_lock,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate a Person C environment lock. This command reads recorded "
            "configuration only; it does not launch or inspect Minecraft."
        )
    )
    parser.add_argument("--lock", required=True, type=Path, help="Environment lock path")
    parser.add_argument(
        "--structure-only",
        action="store_true",
        help="Succeed on a structurally valid template even when runtime proof is pending.",
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        document = load_environment_lock(args.lock)
        result = validate_environment_lock(document)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        print(
            json.dumps(
                {
                    "lock": str(args.lock),
                    "structurally_valid": False,
                    "runtime_ready": False,
                    "error": str(exc),
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 1

    payload = {
        "lock": str(args.lock),
        "mode": "structure_only" if args.structure_only else "runtime_readiness",
        "structurally_valid": result.structurally_valid,
        "runtime_ready": result.runtime_ready,
        "structural_rejections": [
            {"code": rejection.code.value, "message": rejection.message}
            for rejection in result.rejections
        ],
        "runtime_rejections": [
            {"code": rejection.code.value, "message": rejection.message}
            for rejection in result.runtime_rejections
        ],
    }
    print(json.dumps(payload, indent=2, sort_keys=True))

    if args.structure_only:
        return 0 if result.structurally_valid else 1
    return 0 if result.runtime_ready else 2


if __name__ == "__main__":
    raise SystemExit(main())
