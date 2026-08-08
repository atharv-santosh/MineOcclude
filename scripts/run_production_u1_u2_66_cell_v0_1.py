#!/usr/bin/env python3
"""Run the frozen real 66-cell U1/U2 production analysis once."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from mineocclude.analysis.production_u1_u2_66_cell_v0_1 import (
    RUN_ID,
    ProductionPaths,
    run_production_analysis,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--analysis-ready-root",
        type=Path,
        default=Path(
            "/mnt/sagemaker-nvme/mineocclude/phase6"
            f"/{RUN_ID}/output/status/bd_production_input_readiness_v0_1"
        ),
    )
    parser.add_argument(
        "--external-output-root",
        type=Path,
        default=Path(
            "/mnt/sagemaker-nvme/mineocclude/phase6"
            f"/{RUN_ID}/output/status/bd_u1_u2_production_results_v0_1"
        ),
    )
    parser.add_argument(
        "--git-output-root",
        type=Path,
        default=Path("docs/status/integration/bd_u1_u2_production_results_v0_1"),
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    repository = args.repository_root.resolve()
    git_output = args.git_output_root
    if not git_output.is_absolute():
        git_output = repository / git_output
    result = run_production_analysis(
        ProductionPaths(
            repository_root=repository,
            analysis_ready_root=args.analysis_ready_root,
            external_output_root=args.external_output_root,
            git_output_root=git_output,
        )
    )
    print(json.dumps(result, allow_nan=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
