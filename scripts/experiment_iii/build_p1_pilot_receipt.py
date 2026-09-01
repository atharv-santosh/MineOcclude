"""A5 exit — build ``docs/experiment_iii/p1/p1_pilot_receipt.json``.

The lifecycle's A5 exit condition is ``p1_pilot_receipt.json == PASS``. This is
the producer ``EXPECTED_ARTIFACT_INVENTORY.json`` names for that artifact, and
it writes nothing until every binding resolves and every count matches.

    python scripts/experiment_iii/build_p1_pilot_receipt.py \\
        --extraction-host-a3 docs/experiment_iii/receipts/environment_receipt_gpu.json \\
        --activations data/experiment_iii/p1/activations

The receipt records the two implementation identities P1 actually spans -- the
capture-side closure read out of the capture ledger, and the extraction-side
closure of the host that produced the arrays -- rather than pretending one
checkpoint produced both halves.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from mineocclude.experiment_iii.errors import ExperimentIIIError  # noqa: E402
from mineocclude.experiment_iii.p1_receipt import (  # noqa: E402
    build_p1_pilot_receipt,
    p1_full_pass,
)
from mineocclude.experiment_iii.schema import write_json_atomic  # noqa: E402
from mineocclude.experiment_iii.source_closure import source_closure  # noqa: E402

DOCS = REPOSITORY_ROOT / "docs" / "experiment_iii"
DATA = REPOSITORY_ROOT / "data" / "experiment_iii" / "p1"


def _head_commit() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, default=DOCS / "p1" / "p1_pilot_plan.json")
    parser.add_argument("--captures", type=Path, default=DATA / "captures")
    parser.add_argument(
        "--capture-ledger", type=Path, default=DATA / "p1_capture_ledger.jsonl"
    )
    parser.add_argument("--activations", type=Path, default=DATA / "activations")
    parser.add_argument(
        "--p0-selection-receipt",
        type=Path,
        default=DOCS / "p0" / "P0_SELECTION_RECEIPT.json",
    )
    parser.add_argument(
        "--resume-receipt", type=Path, default=DOCS / "p1" / "P1_RESUME_RECEIPT.json"
    )
    parser.add_argument(
        "--capture-host-a3",
        type=Path,
        default=DOCS / "receipts" / "environment_receipt_wsl2_capture_host.json",
    )
    parser.add_argument("--extraction-host-a3", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=DOCS / "p1" / "p1_pilot_receipt.json")
    args = parser.parse_args(argv)

    try:
        closure = source_closure()
        receipt = build_p1_pilot_receipt(
            plan_path=args.plan,
            captures_root=args.captures,
            capture_ledger_path=args.capture_ledger,
            activations_root=args.activations,
            p0_selection_receipt_path=args.p0_selection_receipt,
            resume_receipt_path=args.resume_receipt,
            capture_host_a3_path=args.capture_host_a3,
            extraction_host_a3_path=args.extraction_host_a3,
            extraction_implementation={
                "checkpoint_commit": _head_commit(),
                "source_closure": closure["source_closure_sha256"],
                "record_count": closure.get("record_count"),
                "includes_uncommitted_working_tree": closure.get(
                    "includes_uncommitted_working_tree"
                ),
            },
        )
    except ExperimentIIIError as error:
        print(f"BLOCKER_CODE={error.blocker}", file=sys.stderr)
        print(error.message, file=sys.stderr)
        print("P1_RESULT=FAIL", file=sys.stderr)
        return 1

    digest = write_json_atomic(args.out, receipt)
    for name in receipt["failed_items"]:
        item = receipt["verification_items"][name]
        print(
            f"P1_ITEM_FAILED={name} expected={item['expected']} "
            f"observed={item['observed']}",
            file=sys.stderr,
        )
    for name in receipt["missing_bindings"]:
        print(f"P1_BINDING_MISSING={name}", file=sys.stderr)

    capture_impl = receipt["bindings"]["capture_implementation"]
    extraction_impl = receipt["bindings"]["extraction_implementation"]
    print(f"P1_RESULT={receipt['P1_RESULT']}")
    print(f"P1_FULL_PASS={str(receipt['P1_FULL_PASS']).lower()}")
    print(f"P1_VERIFICATION_ITEMS={len(receipt['verification_items'])}")
    print(f"P1_ITEMS_FAILED={len(receipt['failed_items'])}")
    print(f"CAPTURE_SOURCE_CLOSURE={capture_impl.get('source_closure')}")
    print(f"CAPTURE_CHECKPOINT_COMMIT={capture_impl.get('checkpoint_commit')}")
    print(f"EXTRACTION_SOURCE_CLOSURE={extraction_impl.get('source_closure')}")
    print(f"EXTRACTION_CHECKPOINT_COMMIT={extraction_impl.get('checkpoint_commit')}")
    print(f"P1_PILOT_RECEIPT={args.out.relative_to(REPOSITORY_ROOT).as_posix()}")
    print(f"P1_PILOT_RECEIPT_SHA256={digest}")
    print("PRODUCTION_AUTHORIZED=false")
    print("MODEL_INFERENCE_AUTHORIZED=false")
    return 0 if p1_full_pass(receipt) else 1


if __name__ == "__main__":
    raise SystemExit(main())
