"""Option D feasibility diagnostic — extended candidate ceiling, CPU only.

Runs the EXISTING frozen candidate procedure unchanged, with one difference: the
scan may inspect candidate indices ``0 .. ceiling-1`` instead of ``0 .. 199``.

Unchanged: seed derivation, start derivation, master salt, q grid, the q = 0.05
III-A path, gates 1-11, gate 12 (all-q), the first-19-consecutive target window,
gate 9's 0.10 threshold, ascending-index order, and first-qualifying greedy
admission. No phase offset. No alternate ordering. No cohort optimization.

Materializes NO production cohort and reads no rendered frame, activation, RVE
value, prediction, decoder output or scientific result.

    python scripts/experiment_iii/option_d_feasibility_scan.py [--ceiling 2000]
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from mineocclude.experiment_iii.authority import (  # noqa: E402
    LEFT_TO_RIGHT_COUNT,
    RIGHT_TO_LEFT_COUNT,
    verify_authority_binding,
)
from mineocclude.experiment_iii.cohort_build import (  # noqa: E402
    assert_all_q_primitive_available,
    scan_direction,
)
from mineocclude.experiment_iii.errors import ExperimentIIIError  # noqa: E402
from mineocclude.experiment_iii.historical_seeds import (  # noqa: E402
    build_historical_seed_exclusion_set,
    excluded_seeds,
)
from mineocclude.experiment_iii.schema import write_json_atomic  # noqa: E402

#: Selected prospectively, BEFORE the additional candidates were inspected.
DIAGNOSTIC_CEILING = 2000

DEFAULT_OUT = REPOSITORY_ROOT / "docs" / "experiment_iii" / "a1_receipts"

_QUOTA = {
    "LEFT_TO_RIGHT": LEFT_TO_RIGHT_COUNT,
    "RIGHT_TO_LEFT": RIGHT_TO_LEFT_COUNT,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ceiling", type=int, default=DIAGNOSTIC_CEILING)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)

    binding = verify_authority_binding()
    assert_all_q_primitive_available()
    exclusion = build_historical_seed_exclusion_set()
    historical = excluded_seeds(exclusion)

    admitted_seeds: set[int] = set()
    result: dict[str, object] = {
        "schema_version": "mineocclude-experiment-iii-option-d-feasibility-v1",
        "purpose": "Determine whether the UNCHANGED frozen ascending greedy "
        "admission reaches 13 LTR / 12 RTL within an extended candidate ceiling.",
        "ceiling_selected_prospectively_before_scan": True,
        "diagnostic_ceiling": args.ceiling,
        "gate_9_threshold": 0.10,
        "target_window_rule": "FIRST_19_CONSECUTIVE_ELIGIBLE_ROWS",
        "phase_offsets": None,
        "master_salt_changed": False,
        "q_grid_changed": False,
        "admission_order": "STRICTLY_ASCENDING_INDEX_FIRST_QUALIFYING",
        "cohort_materialized": False,
        "reads_any_scientific_outcome": False,
        "per_direction": {},
    }

    for direction in ("LEFT_TO_RIGHT", "RIGHT_TO_LEFT"):
        needed = _QUOTA[direction]
        gate_counts: dict[str, int] = {}
        state = {"last_report": time.time()}

        def progress(index: int, count: int, gate: str | None) -> None:
            if gate is not None:
                gate_counts[gate] = gate_counts.get(gate, 0) + 1
            now = time.time()
            if now - state["last_report"] > 20.0:
                state["last_report"] = now
                print(
                    f"  {direction}: index {index}, admitted {count}/{needed}",
                    flush=True,
                )

        started = time.time()
        try:
            admitted, rejections = scan_direction(
                direction,
                historical=historical,
                admitted_seeds=admitted_seeds,
                bound=args.ceiling,
                progress=progress,
            )
            reached = True
            indices = [entry.candidate.index for entry in admitted]
            first_complete = indices[-1] if indices else None
            count = len(admitted)
            scanned = first_complete + 1 if first_complete is not None else args.ceiling
        except ExperimentIIIError as error:
            if error.blocker != "COHORT_ALL_Q_QUALIFICATION_INFEASIBLE":
                raise
            reached = False
            indices = []
            first_complete = None
            count = int(error.message.split("only ")[1].split(" of ")[0])
            rejections = []
            scanned = args.ceiling
        elapsed = round(time.time() - started, 1)

        result["per_direction"][direction] = {
            "required": needed,
            "admitted_count": count,
            "quota_reached": reached,
            "admitted_candidate_indices": indices,
            "first_index_at_which_quota_completed": first_complete,
            "candidates_scanned": scanned,
            "rejection_counts_by_first_failing_gate": dict(sorted(gate_counts.items())),
            "rejected_count": len(rejections),
            "elapsed_seconds": elapsed,
        }
        print(
            f"{direction}: {count}/{needed} admitted"
            + (
                f", quota completed at candidate index {first_complete}"
                if reached
                else f" — quota NOT reached within {args.ceiling}"
            )
            + f" ({elapsed}s)",
            flush=True,
        )

    left = result["per_direction"]["LEFT_TO_RIGHT"]
    right = result["per_direction"]["RIGHT_TO_LEFT"]
    result["option_d_feasible"] = bool(
        left["quota_reached"] and right["quota_reached"]
    )
    result["historical_seed_exclusion_sha256"] = exclusion["exclusion_set_sha256"]
    result["authority_binding"] = binding

    digest = write_json_atomic(
        args.out / "option_d_feasibility_receipt.json", result
    )
    print(f"OPTION_D_FEASIBLE={result['option_d_feasible']}")
    print(f"OPTION_D_RECEIPT_SHA256={digest}")
    return 0 if result["option_d_feasible"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
