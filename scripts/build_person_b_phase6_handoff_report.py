"""Build the Step 6.6 outgoing-packet report without claiming acknowledgements."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mineocclude.analysis.handoffs import (  # noqa: E402
    build_phase6_handoff_report,
)
from mineocclude.experiments.registry import (  # noqa: E402
    load_json_with_sha256,
    write_json_exclusive,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("d_request", type=Path)
    parser.add_argument("e_registration_request", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--artifact-id", required=True)
    parser.add_argument("--repository-root", type=Path, default=ROOT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    d_request, _ = load_json_with_sha256(args.d_request)
    e_request, _ = load_json_with_sha256(args.e_registration_request)
    report = build_phase6_handoff_report(
        d_request,
        e_request,
        artifact_id=args.artifact_id,
        repository_root=args.repository_root,
    )
    write_json_exclusive(args.output, report)


if __name__ == "__main__":
    main()
