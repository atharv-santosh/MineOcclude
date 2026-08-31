"""Option B-prime feasibility study — deterministic feasible-subset selection.

Keeps the ORIGINAL candidate universe (indices 0..199 per direction) and every
frozen scientific gate, including gate 9 at exactly 0.10. It repairs only the
GREEDY ORDER DEPENDENCE of a pairwise constraint.

Caches the per-(candidate, q) evaluation to the scratch path given by --cache so
the study and the amended cohort build do not recompute it.

CPU only. Materializes no cohort. Reads no rendered frame, activation, RVE
value, prediction, decoder output or scientific outcome.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from mineocclude.experiment_iii.authority import (  # noqa: E402
    BINDING_Q_SET,
    CANDIDATE_INDEX_BOUND_PER_DIRECTION,
    DIAGNOSTIC_Q_FALLBACK,
    LEFT_TO_RIGHT_COUNT,
    RIGHT_TO_LEFT_COUNT,
    verify_authority_binding,
)
from mineocclude.experiment_iii.bprime import (  # noqa: E402
    build_candidate_evaluation_cache,
    compatibility_matrix,
    lexicographically_smallest_feasible_subset,
)
from mineocclude.experiment_iii.historical_seeds import (  # noqa: E402
    build_historical_seed_exclusion_set,
    excluded_seeds,
)
from mineocclude.experiment_iii.schema import write_json_atomic  # noqa: E402

DEFAULT_OUT = REPOSITORY_ROOT / "docs" / "experiment_iii" / "a1_receipts"
_QUOTA = {"LEFT_TO_RIGHT": LEFT_TO_RIGHT_COUNT, "RIGHT_TO_LEFT": RIGHT_TO_LEFT_COUNT}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--bound", type=int, default=CANDIDATE_INDEX_BOUND_PER_DIRECTION
    )
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)

    verify_authority_binding()
    historical = excluded_seeds(build_historical_seed_exclusion_set())

    cache = build_candidate_evaluation_cache(
        bound=args.bound,
        historical=historical,
        cache_path=args.cache,
        progress=lambda d, i: print(f"  {d} {i}", flush=True) if i % 25 == 0 else None,
    )

    study: dict[str, object] = {
        "schema_version": "mineocclude-experiment-iii-bprime-feasibility-v1",
        "candidate_universe": [0, args.bound - 1],
        "gate_9_threshold": 0.10,
        "compatibility_requires_all_binding_q": True,
        "binding_q_set": list(BINDING_Q_SET),
        "diagnostic_q": DIAGNOSTIC_Q_FALLBACK,
        "objective": "NONE_BEYOND_SATISFYING_THE_FROZEN_GATE",
        "selection_rule": "LEXICOGRAPHICALLY_SMALLEST_ASCENDING_INDEX_TUPLE",
        "per_direction": {},
    }

    for direction, needed in _QUOTA.items():
        entries = cache[direction]
        eligible = [e for e in entries if e["peer_independent_gates_passed"]]
        matrix, indices = compatibility_matrix(eligible)
        started = time.time()
        selection, nodes_explored = lexicographically_smallest_feasible_subset(
            matrix, indices, needed
        )
        elapsed = round(time.time() - started, 2)
        feasible = selection is not None
        detail: dict[str, object] = {
            "required": needed,
            "candidates_evaluated": len(entries),
            "peer_independent_survivors": len(eligible),
            "feasible": feasible,
            "selected_candidate_indices": selection,
            "search_nodes_explored": nodes_explored,
            "search_seconds": elapsed,
        }
        if feasible:
            detail["min_pairwise_rms_by_q"] = {
                f"{q:.4f}": min(
                    entry["rms"][f"{q:.4f}"][str(other)]
                    for position, entry in enumerate(
                        e for e in eligible if e["candidate_index"] in selection
                    )
                    for other in selection
                    if other != entry["candidate_index"]
                )
                for q in BINDING_Q_SET
            }
        study["per_direction"][direction] = detail
        print(
            f"{direction}: feasible={feasible} selection={selection} "
            f"({elapsed}s, {nodes_explored} nodes)",
            flush=True,
        )

    study["b_prime_feasible"] = all(
        study["per_direction"][d]["feasible"] for d in _QUOTA
    )
    digest = write_json_atomic(args.out / "bprime_feasibility_receipt.json", study)
    print(f"B_PRIME_FEASIBLE={study['b_prime_feasible']}")
    print(f"B_PRIME_RECEIPT_SHA256={digest}")
    return 0 if study["b_prime_feasible"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
