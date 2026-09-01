"""A0 revalidation of evidence bound to a predecessor authority.

Authority Amendment 5 moved ``AUTHORITY_SHA256``, so every P0 and P1 artifact --
all of them produced under v1.7 -- became, in A0's words, "invalidated and must
be revalidated". Revalidated, not regenerated: the amendment named a bootstrap
seed and touched nothing those artifacts consume, so re-running a valid 252-unit
P0 campaign would destroy good evidence to no purpose.

This program does not assert that. For each artifact it reads the predecessor
machine authority back out of the git object database, diffs it against the live
one, and admits the artifact only if the changed scientific roots are disjoint
from the roots that artifact depends on.

    python scripts/experiment_iii/build_authority_revalidation_receipt.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from mineocclude.experiment_iii.errors import ExperimentIIIError  # noqa: E402
from mineocclude.experiment_iii.revalidation import (  # noqa: E402
    REVALIDATION_INDEX_PATH,
    build_revalidation_receipt,
)
from mineocclude.experiment_iii.schema import write_json_atomic  # noqa: E402

#: Machine-authority roots the P0 calibration evidence consumes. ``p0_rve``
#: carries the P0 placement-bootstrap seed of 7.10b; ``statistics`` -- the only
#: root Amendment 5 moved -- is deliberately absent, because no P0 artifact reads
#: it: rve.py and p0_analysis.py take their seed from p0_bindings, never from
#: statistics.bootstrap_seed.
P0_ROOTS = (
    "phase0_inputs",
    "namespace",
    "identity",
    "apparatus",
    "conditions",
    "p0_candidate_roster",
    "p0_prospective_exclusions",
    "visibility_semantics",
    "p0_rve",
    "capture_liveness_contract",
    "gates",
    "resources",
)

#: The P1 engineering pilot additionally binds the cohort, the FIR kernels and
#: the extraction spec. It computes no interval and reads no bootstrap seed.
P1_ROOTS = P0_ROOTS + (
    "cohort",
    "fir",
    "context_age",
    "extraction",
    "representations",
    "p1_pilot",
)

ARTIFACTS = {
    "docs/experiment_iii/p0/P0_SELECTED_LADDER.json": P0_ROOTS,
    "docs/experiment_iii/p0/P0_MANIFEST.json": P0_ROOTS,
    "docs/experiment_iii/p0/P0_SELECTION_RECEIPT.json": P0_ROOTS,
    "docs/experiment_iii/p0/P0_RVE_TABLE.json": P0_ROOTS,
    "docs/experiment_iii/p0/P0_BOOTSTRAP_RESULTS.json": P0_ROOTS,
    "docs/experiment_iii/p0/P0_SENTINEL_ENVELOPE.json": P0_ROOTS,
    "docs/experiment_iii/p0/P0_MASK_INVENTORY.json": P0_ROOTS,
    "docs/experiment_iii/p0/p0_campaign_state.json": P0_ROOTS,
    "docs/experiment_iii/p1/p1_pilot_receipt.json": P1_ROOTS,
    "docs/experiment_iii/p1/p1_pilot_plan.json": P1_ROOTS,
    "docs/experiment_iii/p1/p1_extraction_plan.json": P1_ROOTS,
    "docs/experiment_iii/p1/P1_RESUME_RECEIPT.json": P1_ROOTS,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=REVALIDATION_INDEX_PATH)
    args = parser.parse_args(argv)

    try:
        receipt = build_revalidation_receipt(ARTIFACTS)
    except ExperimentIIIError as error:
        print(f"BLOCKER_CODE={error.blocker}", file=sys.stderr)
        print(error.message, file=sys.stderr)
        print("REVALIDATION_STATUS=FAIL", file=sys.stderr)
        return 1

    digest = write_json_atomic(args.out, receipt)
    for commit, delta in receipt["authority_deltas"].items():
        print(f"DELTA_SINCE={commit[:12]}")
        print(f"  CHANGED_KEY_PATHS={delta['changed_key_path_count']}")
        print(f"  CHANGED_SCIENTIFIC_ROOTS={delta['changed_scientific_roots']}")
    print(f"REVALIDATED_COUNT={receipt['revalidated_count']}")
    print(f"SCIENTIFIC_EVIDENCE_INVALIDATED={receipt['scientific_evidence_invalidated']}")
    print("REVALIDATION_STATUS=PASS")
    print(f"REVALIDATION_RECEIPT_SHA256={digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
