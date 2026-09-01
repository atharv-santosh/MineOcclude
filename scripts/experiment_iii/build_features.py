"""A11 — feature construction (authority 8.7, 8.9.1, lifecycle A11).

Builds the three frozen representations, the descriptive depth-panel blocks and
the pixel-baseline features from the A9 activation corpus and the A7 captures,
**persists every block** where the expected artifact inventory names it, and
hashes each one so A12 can lock predictions against features that cannot
subsequently move.

    CURRENT               COARSE_2X6_CONCAT of the CURRENT slice      24,576
    CURRENT_MINUS_PREVIOUS  CURRENT - PREVIOUS, coarse-pooled         24,576
    TWO_FRAME_CONCAT      PREVIOUS first, then CURRENT                49,152
    CURRENT_L04/L10       the 8.12 family E depth panel, descriptive  24,576
    PIXEL_BASELINE        48x28 RGB, frozen area interpolation         4,032

No representation is chosen here and none is searched: the recipes live in
``representations.py`` and ``baselines_pixel.py`` under P2, and this driver only
applies them in the frozen target-row order. ``FEATURE_POOLING_GRID_TRANSPOSED``
and ``FEATURE_SLICE_SWAPPED`` exist because the two plausible silent errors are a
2x6 grid built as 6x2 and a two-frame concat assembled CURRENT-first; both
produce correctly-shaped, entirely wrong features, so both are checked rather
than trusted.

The blocks are written, not merely hashed. A11 that only hashed them left A12
with no feature artifact to fit, which is how A12 came to demand an
investigator-authored prediction file it was supposed to compute.

    python scripts/experiment_iii/build_features.py \\
        --activations data/experiment_iii/production/activations \\
        --a8-receipt docs/experiment_iii/a8/cohort_closure_receipt.json
"""

from __future__ import annotations

import argparse
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
)
from mineocclude.experiment_iii.errors import ExperimentIIIError  # noqa: E402
from mineocclude.experiment_iii.extraction import SELECTED_LAYERS  # noqa: E402
from mineocclude.experiment_iii.feature_store import (  # noqa: E402
    BLOCK_DIMENSIONS,
    DEPTH_PANEL_LAYERS,
    FEATURE_ROOT,
    PIXEL_BLOCK,
    PRIMARY_LAYER,
    build_activation_blocks,
    build_pixel_block,
    store_inventory,
    unit_id,
    write_block,
)
from mineocclude.experiment_iii.representations import (  # noqa: E402
    COARSE_COLS,
    COARSE_DIMENSION,
    COARSE_ROWS,
    TWO_FRAME_DIMENSION,
)
from mineocclude.experiment_iii.schema import (  # noqa: E402
    ConditionId,
    read_jsonl,
    write_json_atomic,
)

#: Inventory A11: the feature config is a receipt, not an analysis result.
DEFAULT_OUT = REPOSITORY_ROOT / "docs" / "experiment_iii" / "receipts"
COHORT = REPOSITORY_ROOT / "docs" / "experiment_iii" / "cohort"

REPRESENTATIONS = {
    "CURRENT": COARSE_DIMENSION,
    "CURRENT_MINUS_PREVIOUS": COARSE_DIMENSION,
    "TWO_FRAME_CONCAT": TWO_FRAME_DIMENSION,
    PIXEL_BASELINE_NAME: PIXEL_FEATURE_DIM,
}


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
    parser.add_argument(
        "--features",
        type=Path,
        default=REPOSITORY_ROOT / FEATURE_ROOT,
        help="where the persisted feature blocks are written",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=COHORT / "production_identity_manifest.jsonl",
    )
    parser.add_argument("--primary-layer", type=int, default=PRIMARY_LAYER)
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
            "persisted_blocks": dict(BLOCK_DIMENSIONS),
            "primary_representation": "COARSE_2X6_CONCAT",
            "coarse_grid": [COARSE_ROWS, COARSE_COLS],
            "selected_layers": list(SELECTED_LAYERS),
            "primary_layer": args.primary_layer,
            "depth_panel_layers": list(DEPTH_PANEL_LAYERS),
            "depth_panel_role": "DESCRIPTIVE_ONLY_MAY_NOT_REPLACE_LAYER_19",
            "rows_per_capture": TARGET_ROWS_PER_CAPTURE,
            "two_frame_order": "PREVIOUS_FIRST_THEN_CURRENT",
            "pixel_baseline": PIXEL_BASELINE_NAME,
            "feature_root": Path(args.features).as_posix(),
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
            manifest = {
                str(row["identity"]): row for row in read_jsonl(args.manifest)
            }
            for identity in identities:
                if identity not in manifest:
                    raise ExperimentIIIError(
                        "PROVENANCE_BINDING_MISSING",
                        f"{identity} is in the A8 cohort but not in "
                        f"{args.manifest}",
                    )
                target_rows = [
                    int(index)
                    for index in manifest[identity]["target_model_frame_indices"]
                ]
                for condition in (c.value for c in ConditionId):
                    unit = unit_id(identity, condition)
                    unit_blocks = build_activation_blocks(
                        args.activations, unit, primary_layer=args.primary_layer
                    )
                    unit_blocks[PIXEL_BLOCK] = build_pixel_block(
                        Path(args.captures) / unit, target_rows
                    )
                    for name, matrix in unit_blocks.items():
                        if matrix.shape[1] != BLOCK_DIMENSIONS[name]:
                            raise ExperimentIIIError(
                                "FEATURE_DIMENSION_MISMATCH",
                                f"{unit} {name} is {matrix.shape[1]}-dimensional, "
                                f"the authority freezes {BLOCK_DIMENSIONS[name]}",
                            )
                        if not np.all(np.isfinite(matrix)):
                            raise ExperimentIIIError(
                                "FEATURE_NONFINITE",
                                f"{unit} {name} holds a non-finite value",
                            )
                        digest = write_block(args.features, name, unit, matrix)
                        blocks.setdefault(unit, {})[name] = digest
                    rows_total += TARGET_ROWS_PER_CAPTURE
            config["identities"] = identities
            config["units"] = len(blocks)
        config["rows_per_representation"] = rows_total
        config["feature_block_hashes"] = blocks
        config["store"] = store_inventory(args.features)
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
    print(f"A11_PERSISTED_BLOCKS={len(BLOCK_DIMENSIONS)}")
    print(f"A11_FEATURE_ROOT={config['feature_root']}")
    print(f"A11_ROWS_PER_REPRESENTATION={config['rows_per_representation']}")
    print(f"A11_FEATURE_CONFIG_SHA256={digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
