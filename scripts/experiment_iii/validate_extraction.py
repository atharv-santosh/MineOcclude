"""I10 — independent extraction validator.

Re-reads every persisted array's bytes and re-derives shape, dtype, byte size,
finiteness and SHA-256 rather than trusting the inventory.

A capture root is a directory holding ``extraction_inventory.json``. Passing the
*parent* of the capture roots -- the extraction output root -- is the natural
thing for a caller to do and is accepted: the root is expanded into the capture
directories beneath it. An expansion that finds nothing is a refusal, never an
empty pass.

    python scripts/experiment_iii/validate_extraction.py <capture-root> [...]
    python scripts/experiment_iii/validate_extraction.py \\
        data/experiment_iii/production/activations \\
        --expect-captures 125 --expect-arrays 750
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
from mineocclude.experiment_iii.authority import (  # noqa: E402
    verify_authority_binding,
)
from mineocclude.experiment_iii.errors import ExperimentIIIError  # noqa: E402
from mineocclude.experiment_iii.p1_extraction import (  # noqa: E402
    CANONICAL_INVENTORY_NAME,
)
from mineocclude.experiment_iii.schema import write_json_atomic  # noqa: E402

STAGE = "A10"
DEFAULT_RECEIPT = (
    REPOSITORY_ROOT / "docs" / "experiment_iii" / "receipts"
    / "extraction_validation_receipt.json"
)


def _capture_roots(roots: list[Path], inventory_name: str) -> list[Path]:
    """Expand any extraction output root into the capture roots beneath it."""
    resolved: list[Path] = []
    for root in roots:
        if (root / inventory_name).is_file():
            resolved.append(root)
            continue
        children = sorted(
            child for child in root.iterdir()
            if child.is_dir() and (child / inventory_name).is_file()
        ) if root.is_dir() else []
        if not children:
            # Neither a capture root nor a root holding any: say so, do not
            # quietly contribute zero captures to a passing total.
            raise ExperimentIIIError(
                "EXTRACTION_INVENTORY_INCOMPLETE",
                f"{root} is not a capture root (no {inventory_name}) and holds "
                f"no capture directory that is one",
            )
        resolved.extend(children)
    return resolved


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("roots", nargs="+", type=Path)
    # Authority 8.5 and EXPECTED_ARTIFACT_INVENTORY.json name this artifact
    # ``extraction_inventory.json``. The default is taken from the module that
    # writes it, so producer and validator cannot drift apart again.
    parser.add_argument("--inventory", default=CANONICAL_INVENTORY_NAME)
    parser.add_argument("--expect-captures", type=int, default=None)
    parser.add_argument("--expect-arrays", type=int, default=None)
    parser.add_argument("--receipt", type=Path, default=DEFAULT_RECEIPT)
    parser.add_argument("--no-receipt", action="store_true")
    # The namespace guard admits only Experiment III roots; a caller writing
    # the receipt into a temporary tree passes that tree as its root so the
    # guard still runs, against that tree, rather than being switched off.
    parser.add_argument("--namespace-root", type=Path, default=None)
    args = parser.parse_args(argv)

    try:
        roots = _capture_roots(list(args.roots), args.inventory)
    except ExperimentIIIError as error:
        print(f"BLOCKER_CODE={error.blocker}", file=sys.stderr)
        print(error.message, file=sys.stderr)
        return 1

    failures: list[dict[str, str]] = []
    arrays = 0
    units: list[dict[str, object]] = []
    for root in roots:
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
            failures.append({"root": str(root),
                             "blocker": "EXTRACTION_INVENTORY_INCOMPLETE",
                             "message": str(error)})
            continue
        except ExperimentIIIError as error:
            print(f"BLOCKER_CODE={error.blocker} {root}: {error.message}",
                  file=sys.stderr)
            failures.append({"root": str(root), "blocker": error.blocker,
                             "message": error.message})
            continue
        arrays += len(validated)
        units.append({"capture_root": root.name,
                      "stage": inventory.get("stage"),
                      "arrays_validated": len(validated),
                      "complete": len(validated) == UNITS_PER_CAPTURE})
        print(f"{root}: {len(validated)}/{UNITS_PER_CAPTURE} arrays VALIDATED")

    # A corpus that is merely self-consistent is not a corpus that is complete.
    # Without an expected count, "0 failures" says nothing about how much of the
    # frozen workload is actually on disk.
    shortfall = []
    if args.expect_captures is not None and len(roots) != args.expect_captures:
        shortfall.append(f"captures {len(roots)} != expected {args.expect_captures}")
    if args.expect_arrays is not None and arrays != args.expect_arrays:
        shortfall.append(f"arrays {arrays} != expected {args.expect_arrays}")

    passed = not failures and not shortfall
    print(f"EXPECTED_BYTES_PER_ARRAY={EXPECTED_NPY_BYTES}")
    print(f"CAPTURES_CHECKED={len(roots)}")
    print(f"CAPTURES_FAILED={len(failures)}")
    print(f"ARRAYS_VALIDATED={arrays}")
    print(f"A10_STATUS={'PASS' if passed else 'FAIL'}")
    for line in shortfall:
        print(f"BLOCKER_CODE=EXTRACTION_INVENTORY_INCOMPLETE {line}", file=sys.stderr)

    if not args.no_receipt:
        digest = write_json_atomic(args.receipt, {
            "schema_version": "mineocclude-experiment-iii-extraction-validation-v1",
            "stage": STAGE,
            "authority_section": "8.5",
            "authority_binding": verify_authority_binding(),
            "passed": passed,
            "captures_checked": len(roots),
            "captures_failed": len(failures),
            "arrays_validated": arrays,
            "expected_captures": args.expect_captures,
            "expected_arrays": args.expect_arrays,
            "expected_bytes_per_array": EXPECTED_NPY_BYTES,
            "arrays_per_capture": UNITS_PER_CAPTURE,
            "independent_revalidation": "BYTES_SHAPE_DTYPE_SIZE_FINITENESS_SHA256",
            "inventory_name": args.inventory,
            "failures": failures,
            "shortfall": shortfall,
            "units": units,
        }, root=args.namespace_root)
        print(f"EXTRACTION_VALIDATION_RECEIPT_SHA256={digest}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
