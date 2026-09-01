"""A8 — capture cohort validation (lifecycle ``source_files_entrypoints``).

Closes the production cohort after A7 finishes or halts, and decides what
population the analysis has. Outcome-blind by construction: it reads the
hash-chained capture ledger, the per-unit durable receipts and the frozen
identity manifest, and nothing else. No activation, prediction or statistic is
reachable from here.

    python scripts/experiment_iii/validate_capture_cohort.py \\
        --ledger data/experiment_iii/production/production_capture_ledger.jsonl \\
        --capture-root data/experiment_iii/production/captures
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from mineocclude.experiment_iii.cohort_closure import close_cohort  # noqa: E402
from mineocclude.experiment_iii.errors import ExperimentIIIError  # noqa: E402
from mineocclude.experiment_iii.schema import read_jsonl, write_json_atomic  # noqa: E402

COHORT = REPOSITORY_ROOT / "docs" / "experiment_iii" / "cohort"
DEFAULT_PRODUCTION = REPOSITORY_ROOT / "data" / "experiment_iii" / "production"
DEFAULT_OUT = REPOSITORY_ROOT / "docs" / "experiment_iii" / "a8"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ledger",
        type=Path,
        default=DEFAULT_PRODUCTION / "production_capture_ledger.jsonl",
    )
    parser.add_argument(
        "--capture-root", type=Path, default=DEFAULT_PRODUCTION / "captures"
    )
    parser.add_argument(
        "--manifest", type=Path, default=COHORT / "production_identity_manifest.jsonl"
    )
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--allow-missing-durable-receipt",
        action="store_true",
        help="count a COMPLETE ledger entry whose banked receipt is absent "
        "(diagnostic only; never for a cohort of record)",
    )
    args = parser.parse_args(argv)

    try:
        rows = read_jsonl(args.manifest)
        receipt = close_cohort(
            ledger_path=args.ledger,
            capture_root=args.capture_root,
            identity_rows=rows,
            require_durable_receipt=not args.allow_missing_durable_receipt,
        )
    except ExperimentIIIError as error:
        print(f"BLOCKER_CODE={error.blocker}", file=sys.stderr)
        print(error.message, file=sys.stderr)
        print("A8_STATUS=FAIL", file=sys.stderr)
        return 1

    digest = write_json_atomic(args.out / "cohort_closure_receipt.json", receipt)
    print(f"A8_STATUS={'PASS' if receipt['passed'] else 'FAIL'}")
    print(f"N_COMPLETE={receipt['N_complete']}")
    print(f"ATTRITION_BRANCH={receipt['attrition_branch']}")
    print(
        "GRADED_INFERENTIAL_CLAIM_PERMITTED="
        f"{str(receipt['attrition']['graded_inferential_claim_permitted']).lower()}"
    )
    print(f"ANALYSABLE_UNITS={receipt['analysable_units']}")
    print(f"ANALYSABLE_TARGET_ROWS={receipt['analysable_target_rows']}")
    print(f"PARTIAL_IDENTITIES={len(receipt['partial_identities'])}")
    print(f"ABSENT_IDENTITIES={len(receipt['absent_identities'])}")
    print(f"IMPUTED_CELLS={receipt['imputed_cells']}")
    print("MODEL_OUTCOME_CONSULTED=false")
    print(f"COHORT_CLOSURE_RECEIPT_SHA256={digest}")
    if not receipt["passed"]:
        print(f"BLOCKER_CODE={receipt['blocker']}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
