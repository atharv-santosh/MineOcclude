"""Build Regime A targets from a B-owned table using schema-v1 row identity."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mineocclude.analysis.config import DEFAULT_CONFIG_PATH  # noqa: E402
from mineocclude.experiments.registry import (  # noqa: E402
    load_json_with_sha256,
    write_json_exclusive,
)
from mineocclude.oracle.targets import build_regime_a_target_document  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate a B-owned derived-state table and build oracle targets."
    )
    parser.add_argument("input", type=Path, help="Derived-state JSON document.")
    parser.add_argument("output", type=Path, help="Destination target JSON document.")
    parser.add_argument("--run-id", required=True, help="Person B oracle run ID.")
    parser.add_argument("--code-sha", required=True, help="40-character code SHA.")
    config_group = parser.add_mutually_exclusive_group()
    config_group.add_argument(
        "--config",
        type=Path,
        help=(
            "Validated analysis config to hash byte-for-byte "
            f"(default: {DEFAULT_CONFIG_PATH})."
        ),
    )
    config_group.add_argument(
        "--config-hash",
        help=(
            "Legacy explicit hash accepted only for inputs marked synthetic "
            "and forbidden for scientific use."
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    state_document, _state_file_hash = load_json_with_sha256(args.input)
    build_options = (
        {"oracle_config_hash": args.config_hash}
        if args.config_hash is not None
        else {"analysis_config_path": args.config or DEFAULT_CONFIG_PATH}
    )
    target_document = build_regime_a_target_document(
        state_document,
        oracle_run_id=args.run_id,
        oracle_code_sha=args.code_sha,
        **build_options,
    )
    write_json_exclusive(args.output, target_document)


if __name__ == "__main__":
    main()
