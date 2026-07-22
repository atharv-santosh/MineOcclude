"""Seal machine-readable plot values without retyping scientific results."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mineocclude.experiments.figure_inputs import (  # noqa: E402
    FIGURE_FAMILIES,
    build_figure_input,
)
from mineocclude.experiments.registry import (  # noqa: E402
    load_json_with_sha256,
    write_json_exclusive,
)
from mineocclude.vision.config import DEFAULT_PERSON_E_CONFIG_PATH  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Seal plot-ready rows with explicit source hashes and run IDs."
    )
    parser.add_argument("input", type=Path, help="JSON document containing rows.")
    parser.add_argument("output", type=Path)
    parser.add_argument("--figure-id", required=True)
    parser.add_argument("--figure-family", choices=sorted(FIGURE_FAMILIES), required=True)
    parser.add_argument("--code-sha", required=True)
    parser.add_argument(
        "--result-scope",
        choices=("scientific", "known_answer"),
        default="scientific",
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_PERSON_E_CONFIG_PATH)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    source, source_hash = load_json_with_sha256(args.input)
    if not isinstance(source, dict) or not isinstance(source.get("rows"), list):
        raise ValueError("Input must be a mapping containing rows.")
    rows = []
    for index, row in enumerate(source["rows"]):
        if not isinstance(row, dict):
            raise ValueError(f"Input row {index} must be a mapping.")
        if "source_artifact_hash" in row:
            raise ValueError(
                "Input rows must not supply source_artifact_hash; it is derived "
                "from the literal input bytes."
            )
        rows.append({**row, "source_artifact_hash": source_hash})
    document = build_figure_input(
        rows,
        figure_id=args.figure_id,
        figure_family=args.figure_family,
        code_sha=args.code_sha,
        result_scope=args.result_scope,
        config_path=args.config,
    )
    write_json_exclusive(args.output, document)


if __name__ == "__main__":
    main()
