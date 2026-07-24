"""Build a validated C-to-B state-input document without overwriting evidence."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mineocclude.analysis.coordinates import (  # noqa: E402
    build_state_input_from_capture_package,
)
from mineocclude.experiments.registry import (  # noqa: E402
    load_json_with_sha256,
    write_json_exclusive,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate one Person C capture package and project it into Person "
            "B's signed wall-parallel state contract."
        )
    )
    parser.add_argument("capture_package", type=Path)
    parser.add_argument("coordinate_frame", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--model-hash", required=True)
    parser.add_argument("--preprocess-hash", required=True)
    parser.add_argument(
        "--projection-tolerance-blocks",
        type=float,
        default=1e-9,
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    capture_package, _capture_file_hash = load_json_with_sha256(
        args.capture_package
    )
    coordinate_frame, _coordinate_file_hash = load_json_with_sha256(
        args.coordinate_frame
    )
    document = build_state_input_from_capture_package(
        capture_package,
        coordinate_frame=coordinate_frame,
        model_hash=args.model_hash,
        preprocess_hash=args.preprocess_hash,
        projection_tolerance_blocks=args.projection_tolerance_blocks,
    )
    write_json_exclusive(args.output, document)


if __name__ == "__main__":
    main()
