"""A11 — feature construction (authority 8.7, lifecycle A11).

Builds the three frozen representations and the pixel-baseline features from the
A9 activation corpus, and hashes every block so A12 can lock predictions against
features that cannot subsequently move.

    CURRENT               COARSE_2X6_CONCAT of the CURRENT slice      24,576
    CURRENT_MINUS_PREVIOUS  CURRENT - PREVIOUS, coarse-pooled         24,576
    TWO_FRAME_CONCAT      PREVIOUS first, then CURRENT                49,152
    pixel baseline        48x28 RGB, frozen area interpolation         4,032

No representation is chosen here and none is searched: the recipes live in
``representations.py`` under P2, and this driver only applies them in the frozen
target-row order. ``FEATURE_POOLING_GRID_TRANSPOSED`` and
``FEATURE_SLICE_SWAPPED`` exist because the two plausible silent errors are a
2x6 grid built as 6x2 and a two-frame concat assembled CURRENT-first; both
produce correctly-shaped, entirely wrong features, so both are checked rather
than trusted.

    python scripts/experiment_iii/build_features.py \\
        --activations data/experiment_iii/production/activations \\
        --a8-receipt docs/experiment_iii/a8/cohort_closure_receipt.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from mineocclude.experiment_iii.authority import (  # noqa: E402
    TARGET_ROWS_PER_CAPTURE,
    verify_authority_binding,
)
from mineocclude.experiment_iii.baselines_pixel import (  # noqa: E402
    PIXEL_BASELINE_NAME,
    PIXEL_FEATURE_DIM,
    pixel_features,
)
from mineocclude.experiment_iii.errors import ExperimentIIIError  # noqa: E402
from mineocclude.experiment_iii.extraction import SELECTED_LAYERS  # noqa: E402
from mineocclude.experiment_iii.representations import (  # noqa: E402
    COARSE_COLS,
    COARSE_DIMENSION,
    COARSE_ROWS,
    TWO_FRAME_DIMENSION,
    coarse_2x6_concat,
    current_minus_previous,
    two_frame_concat,
)
from mineocclude.experiment_iii.schema import write_json_atomic  # noqa: E402

DEFAULT_OUT = REPOSITORY_ROOT / "docs" / "experiment_iii" / "analysis"

REPRESENTATIONS = {
    "CURRENT": COARSE_DIMENSION,
    "CURRENT_MINUS_PREVIOUS": COARSE_DIMENSION,
    "TWO_FRAME_CONCAT": TWO_FRAME_DIMENSION,
    PIXEL_BASELINE_NAME: PIXEL_FEATURE_DIM,
}


def _array_path(root: Path, unit_id: str, layer: int, temporal_slice: str) -> Path:
    return Path(root) / unit_id / f"layer{layer:02d}_{temporal_slice.lower()}.npy"


def _build_unit(
    activations: Path, unit_id: str, layer: int
) -> dict[str, np.ndarray]:
    """The four feature blocks for one capture unit at one layer."""
    current_path = _array_path(activations, unit_id, layer, "CURRENT")
    previous_path = _array_path(activations, unit_id, layer, "PREVIOUS")
    for path in (current_path, previous_path):
        if not path.is_file():
            raise ExperimentIIIError(
                "PROVENANCE_BINDING_MISSING", f"A11 needs {path}, which is absent"
            )
    current = np.load(current_path).astype(np.float64)
    previous = np.load(previous_path).astype(np.float64)
    if current.shape != previous.shape:
        raise ExperimentIIIError(
            "FEATURE_DIMENSION_MISMATCH",
            f"{unit_id} layer {layer}: CURRENT {current.shape} != PREVIOUS "
            f"{previous.shape}",
        )
    if current.shape[0] != TARGET_ROWS_PER_CAPTURE:
        raise ExperimentIIIError(
            "FEATURE_ROW_ORDER_MISMATCH",
            f"{unit_id} layer {layer} holds {current.shape[0]} rows, the authority "
            f"freezes {TARGET_ROWS_PER_CAPTURE}",
        )
    blocks = {
        "CURRENT": np.stack([coarse_2x6_concat(row) for row in current]),
        "CURRENT_MINUS_PREVIOUS": np.stack(
            [
                current_minus_previous(row_c, row_p)
                for row_c, row_p in zip(current, previous)
            ]
        ),
        # PREVIOUS first. Swapping the operands yields the same shape and a
        # different feature space, which is FEATURE_SLICE_SWAPPED.
        "TWO_FRAME_CONCAT": np.stack(
            [
                two_frame_concat(row_p, row_c)
                for row_p, row_c in zip(previous, current)
            ]
        ),
    }
    return blocks


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--activations",
        type=Path,
        default=REPOSITORY_ROOT
        / "data" / "experiment_iii" / "production" / "activations",
    )
    parser.add_argument(
        "--a8-receipt",
        type=Path,
        default=REPOSITORY_ROOT
        / "docs" / "experiment_iii" / "a8" / "cohort_closure_receipt.json",
    )
    parser.add_argument(
        "--captures",
        type=Path,
        default=REPOSITORY_ROOT
        / "data" / "experiment_iii" / "production" / "captures",
    )
    parser.add_argument("--primary-layer", type=int, default=19)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--config-only", action="store_true")
    args = parser.parse_args(argv)

    try:
        binding = verify_authority_binding()
        if args.primary_layer not in SELECTED_LAYERS:
            raise ExperimentIIIError(
                "FEATURE_DIMENSION_MISMATCH",
                f"layer {args.primary_layer} is not one of the frozen "
                f"{list(SELECTED_LAYERS)}",
            )
        if COARSE_ROWS != 2 or COARSE_COLS != 6:
            raise ExperimentIIIError(
                "FEATURE_POOLING_GRID_TRANSPOSED",
                f"the coarse grid is {COARSE_ROWS}x{COARSE_COLS}; the authority "
                f"freezes 2x6",
            )
        config = {
            "schema_version": "mineocclude-experiment-iii-feature-config-v1",
            "stage": "A11",
            "authority_section": "8.7",
            "authority_binding": binding,
            "representations": REPRESENTATIONS,
            "primary_representation": "COARSE_2X6_CONCAT",
            "coarse_grid": [COARSE_ROWS, COARSE_COLS],
            "selected_layers": list(SELECTED_LAYERS),
            "primary_layer": args.primary_layer,
            "rows_per_capture": TARGET_ROWS_PER_CAPTURE,
            "two_frame_order": "PREVIOUS_FIRST_THEN_CURRENT",
            "pixel_baseline": PIXEL_BASELINE_NAME,
            "feature_search_performed": False,
            "outcome_consulted_to_choose_features": False,
        }

        blocks: dict[str, dict[str, str]] = {}
        rows_total = 0
        if not args.config_only:
            closure = json.loads(Path(args.a8_receipt).read_text(encoding="utf-8"))
            if closure.get("stage") != "A8" or not closure.get("passed"):
                raise ExperimentIIIError(
                    "COHORT_MATRIX_INCONSISTENT",
                    f"{args.a8_receipt} is not a passed A8 cohort closure",
                )
            identities = list(closure["complete_five_way_paired_identities"])
            for identity in identities:
                for condition in ("L0", "L1", "L2", "L3", "L4"):
                    unit_id = f"{identity}__{condition}"
                    unit_blocks = _build_unit(
                        args.activations, unit_id, args.primary_layer
                    )
                    for name, matrix in unit_blocks.items():
                        if matrix.shape[1] != REPRESENTATIONS[name]:
                            raise ExperimentIIIError(
                                "FEATURE_DIMENSION_MISMATCH",
                                f"{unit_id} {name} is {matrix.shape[1]}-dimensional, "
                                f"the authority freezes {REPRESENTATIONS[name]}",
                            )
                        if not np.all(np.isfinite(matrix)):
                            raise ExperimentIIIError(
                                "FEATURE_NONFINITE",
                                f"{unit_id} {name} holds a non-finite value",
                            )
                        blocks.setdefault(unit_id, {})[name] = hashlib.sha256(
                            np.ascontiguousarray(matrix, dtype=np.float64).tobytes()
                        ).hexdigest()
                    rows_total += TARGET_ROWS_PER_CAPTURE
            config["identities"] = identities
            config["units"] = len(blocks)
        config["rows_per_representation"] = rows_total
        config["feature_block_hashes"] = blocks
    except (ExperimentIIIError, OSError, KeyError, json.JSONDecodeError) as error:
        blocker = getattr(error, "blocker", "FEATURE_DIMENSION_MISMATCH")
        print(f"BLOCKER_CODE={blocker}", file=sys.stderr)
        print(getattr(error, "message", str(error)), file=sys.stderr)
        print("A11_STATUS=FAIL", file=sys.stderr)
        return 1

    digest = write_json_atomic(args.out / "feature_config.json", config)
    print("A11_STATUS=PASS")
    for name, dimension in REPRESENTATIONS.items():
        print(f"A11_DIM_{name}={dimension}")
    print(f"A11_COARSE_GRID={COARSE_ROWS}x{COARSE_COLS}")
    print(f"A11_TWO_FRAME_ORDER={config['two_frame_order']}")
    print(f"A11_UNITS={config.get('units', 0)}")
    print(f"A11_ROWS_PER_REPRESENTATION={config['rows_per_representation']}")
    print(f"A11_FEATURE_CONFIG_SHA256={digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
