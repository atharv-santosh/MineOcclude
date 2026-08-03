"""Run or validate the exact Person B Step 4.1 final comparison.

The CLI deliberately exposes no method, layer, test, threshold, refit,
extraction, or U4 option.  All such choices live in the ratified contract.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from mineocclude.analysis.step4_1_final_comparison_runtime_v0_1 import (
    ExecutionRequest,
    run_final_comparison,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the exact ratified Person B Step 4.1 final comparison."
    )
    parser.add_argument("--repository-root", required=True, type=Path)
    parser.add_argument("--person-b-contract-commit", required=True)
    parser.add_argument("--person-e-ratification-commit", required=True)
    parser.add_argument(
        "--person-b-predictions", required=True, type=Path
    )
    parser.add_argument("--person-d-root", required=True, type=Path)
    parser.add_argument(
        "--post-reveal-predictions", required=True, type=Path
    )
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--mode", choices=("validate", "run"), default="run")
    parser.add_argument(
        "--resume",
        choices=("validate-complete-no-write",),
        default="validate-complete-no-write",
    )
    return parser


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    return build_parser().parse_args(argv)


def request_from_args(args: argparse.Namespace) -> ExecutionRequest:
    return ExecutionRequest(
        repository_root=args.repository_root.resolve(),
        person_b_contract_commit=args.person_b_contract_commit,
        person_e_ratification_commit=args.person_e_ratification_commit,
        person_b_predictions=args.person_b_predictions,
        person_d_root=args.person_d_root,
        post_reveal_predictions=args.post_reveal_predictions,
        output_root=args.output_root,
        mode=args.mode,
        resume=args.resume,
    )


def main(argv: list[str] | None = None) -> int:
    result = run_final_comparison(request_from_args(parse_args(argv)))
    # Never print predictions, hidden-state rows, or per-layer results.
    print(f"PERSON_B_STEP4_1_FINAL_COMPARISON_STATUS={result['status']}")
    if result.get("output_root"):
        print(f"PERSON_B_STEP4_1_FINAL_COMPARISON_OUTPUT={result['output_root']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
