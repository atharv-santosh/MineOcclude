"""I15 — seal the held-out predictions before any statistic is opened.

Refuses to seal if any required (identity, condition, row, model) cell is missing
or duplicated, and refuses entirely once statistics have been opened.

    python scripts/experiment_iii/lock_predictions.py --predictions <jsonl> --out <dir>
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
from mineocclude.experiment_iii.prediction_lock import (  # noqa: E402
    PredictionCell,
    PredictionLock,
)
from mineocclude.experiment_iii.schema import ConditionId, read_jsonl  # noqa: E402

DEFAULT_OUT = REPOSITORY_ROOT / "docs" / "experiment_iii" / "analysis"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--rows", type=int, default=TARGET_ROWS_PER_CAPTURE)
    args = parser.parse_args(argv)

    try:
        verify_authority_binding()
        rows = read_jsonl(args.predictions)
        lock = PredictionLock()
        lock.extend(
            PredictionCell(
                identity=row["identity"],
                condition_id=row["condition_id"],
                row_index=int(row["row_index"]),
                model=row["model"],
                prediction=float(row["prediction"]),
                target=float(row["target"]),
            )
            for row in rows
        )
        lock.assert_complete(
            identities=sorted({row["identity"] for row in rows}),
            conditions=[c.value for c in ConditionId],
            rows=args.rows,
            models=sorted({row["model"] for row in rows}),
        )
        digest = lock.seal()
        lock.write(args.out)
    except ExperimentIIIError as error:
        print(f"BLOCKER_CODE={error.blocker}", file=sys.stderr)
        print(error.message, file=sys.stderr)
        return 1

    print(f"PREDICTION_CELLS={len(lock)}")
    print(f"PREDICTION_LOCK_SHA256={digest}")
    print("PREDICTION_LOCK_SEALED_BEFORE_STATISTICS=true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
