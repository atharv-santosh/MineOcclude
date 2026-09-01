"""I10 — independent extraction validator.

Re-reads every persisted array's bytes and re-derives shape, dtype, byte size,
finiteness and SHA-256 rather than trusting the inventory.

    python scripts/experiment_iii/validate_extraction.py <capture-root> [...]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from mineocclude.experiment_iii.activation_store import (  # noqa: E402
    EXPECTED_NPY_BYTES,
    UNITS_PER_CAPTURE,
    validate_extraction_inventory,
)
from mineocclude.experiment_iii.errors import ExperimentIIIError  # noqa: E402
from mineocclude.experiment_iii.p1_extraction import (  # noqa: E402
    CANONICAL_INVENTORY_NAME,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("roots", nargs="+", type=Path)
    # Authority 8.5 and EXPECTED_ARTIFACT_INVENTORY.json name this artifact
    # ``extraction_inventory.json``. The default is taken from the module that
    # writes it, so producer and validator cannot drift apart again.
    parser.add_argument("--inventory", default=CANONICAL_INVENTORY_NAME)
    args = parser.parse_args(argv)

    failures = 0
    for root in args.roots:
        inventory_path = root / args.inventory
        try:
            inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
            validated = validate_extraction_inventory(
                root,
                inventory,
                expected_target_rows=inventory.get("target_model_frame_indices"),
            )
        except (OSError, json.JSONDecodeError) as error:
            print(f"BLOCKER_CODE=EXTRACTION_INVENTORY_INCOMPLETE {root}: {error}",
                  file=sys.stderr)
            failures += 1
            continue
        except ExperimentIIIError as error:
            print(f"BLOCKER_CODE={error.blocker} {root}: {error.message}",
                  file=sys.stderr)
            failures += 1
            continue
        print(f"{root}: {len(validated)}/{UNITS_PER_CAPTURE} arrays VALIDATED")

    print(f"EXPECTED_BYTES_PER_ARRAY={EXPECTED_NPY_BYTES}")
    print(f"CAPTURES_CHECKED={len(args.roots)}")
    print(f"CAPTURES_FAILED={failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
