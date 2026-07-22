"""Build Regime A targets from a B-owned table using schema-v1 row identity."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mineocclude.analysis.config import DEFAULT_CONFIG_PATH  # noqa: E402
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
    with args.input.open("r", encoding="utf-8") as handle:
        state_document = json.load(handle)
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
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(target_document, handle, indent=2, sort_keys=True)
        handle.write("\n")


if __name__ == "__main__":
    main()
