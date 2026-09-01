"""I09 — the A9 PRODUCTION extraction driver. CPU/plan only in this build.

A9 is production: 125 captures, 2,375 forwards, 750 arrays. Its lifecycle entry
requires ``A8 == PASS``, the A6 freeze binding and
``MODEL_INFERENCE_AUTHORIZED == true``, which only the A6/P2 freeze exit may
emit. None of those exist, so this program reports the frozen extraction plan
and the verified slice arithmetic and refuses to run inference.

**This is not the P1 pilot entrypoint.** The A5 engineering pilot -- 10 captures,
190 forwards, 60 arrays -- is a different stage with a different gate, and lives
in ``run_p1_extraction.py``. Pointing the pilot at this driver would either
demand a P2 freeze the pilot does not need or spend production scope on it.

    python scripts/experiment_iii/run_extraction.py --plan-only
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from mineocclude.experiment_iii.authority import (  # noqa: E402
    TARGET_ROWS_PER_CAPTURE,
    verify_authority_binding,
)
from mineocclude.experiment_iii.errors import ExperimentIIIError  # noqa: E402
from mineocclude.experiment_iii.extraction import SELECTED_LAYERS  # noqa: E402
from mineocclude.experiment_iii.schema import TemporalSlice, write_json_atomic  # noqa: E402
from mineocclude.experiment_iii.slices import verify_slice_arithmetic  # noqa: E402

DEFAULT_OUT = REPOSITORY_ROOT / "docs" / "experiment_iii" / "a1_receipts"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan-only", action="store_true", default=True)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)

    if not args.plan_only:
        print(
            "BLOCKER_CODE=P2_PREREQUISITE_NOT_PASSED\n"
            "MineWorld inference is stage A9 and is not authorized by this task",
            file=sys.stderr,
        )
        return 1
    try:
        binding = verify_authority_binding()
        slices = verify_slice_arithmetic()
    except ExperimentIIIError as error:
        print(f"BLOCKER_CODE={error.blocker}", file=sys.stderr)
        print(error.message, file=sys.stderr)
        return 1

    captures = 125
    body = {
        "schema_version": "mineocclude-experiment-iii-extraction-plan-v1",
        "authority_section": "8.4",
        "authority_binding": binding,
        "selected_layers": list(SELECTED_LAYERS),
        "temporal_slices": [name.value for name in TemporalSlice],
        "target_rows_per_capture": TARGET_ROWS_PER_CAPTURE,
        "forwards_per_capture": TARGET_ROWS_PER_CAPTURE,
        "production_captures": captures,
        "total_forwards": captures * TARGET_ROWS_PER_CAPTURE,
        "arrays_per_capture": len(SELECTED_LAYERS) * len(TemporalSlice),
        "extra_forward_authorized": False,
        "mineworld_inference_run": False,
        "slice_arithmetic": slices,
    }
    digest = write_json_atomic(args.out / "extraction_plan.json", body)
    print(f"SELECTED_LAYERS={list(SELECTED_LAYERS)}")
    print(f"TOTAL_FORWARDS={body['total_forwards']}")
    print(f"ARRAYS_PER_CAPTURE={body['arrays_per_capture']}")
    print(f"EXTRACTION_PLAN_SHA256={digest}")
    print("MINEWORLD_INFERENCE_RUN=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
