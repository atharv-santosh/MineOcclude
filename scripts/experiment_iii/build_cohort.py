"""I02 — materialize the fresh Experiment III cohort. CPU only.

All twelve gates of authority 2.4 are evaluated BEFORE anything is written, and
gate 12 is evaluated before the production manifest exists and before its hash is
taken. Fails closed with COHORT_ALL_Q_PRIMITIVE_MISSING if IB02/IB03 are not green.

    python scripts/experiment_iii/build_cohort.py [--out <dir>]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from mineocclude.experiment_iii.authority import (  # noqa: E402
    AUTHORITY_FREEZE_COMMIT,
    verify_authority_binding,
)
from mineocclude.experiment_iii.cohort_build import build_cohort, write_cohort  # noqa: E402
from mineocclude.experiment_iii.errors import ExperimentIIIError  # noqa: E402

DEFAULT_OUT = REPOSITORY_ROOT / "docs" / "experiment_iii" / "cohort"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)

    try:
        binding = verify_authority_binding()
        artifacts = build_cohort()
        digests = write_cohort(artifacts, args.out)
    except ExperimentIIIError as error:
        print(f"BLOCKER_CODE={error.blocker}", file=sys.stderr)
        print(error.message, file=sys.stderr)
        return 1

    left = sum(row["direction"] == "LEFT_TO_RIGHT" for row in artifacts.production)
    right = sum(row["direction"] == "RIGHT_TO_LEFT" for row in artifacts.production)
    print(f"AUTHORITY_SHA256={binding['AUTHORITY_SHA256']}")
    print(f"AUTHORITY_FREEZE_COMMIT={AUTHORITY_FREEZE_COMMIT}")
    print(f"COHORT_SIZE={len(artifacts.production)}")
    print(f"LTR={left}")
    print(f"RTL={right}")
    print(f"PILOTS={len(artifacts.pilots)}")
    print(
        "GATE_COUNT="
        f"{artifacts.qualification_receipt['gate_count']}"
    )
    print(
        "ALL_Q_GATE_PRECEDES_MATERIALIZATION="
        f"{artifacts.all_q_receipt['evaluated_before_materialization']}"
    )
    print(
        "CANDIDATE_BOUND_PER_DIRECTION="
        f"{artifacts.qualification_receipt['candidate_index_bound_per_direction']}"
    )
    for name, digest in sorted(digests.items()):
        print(f"  {name} {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
