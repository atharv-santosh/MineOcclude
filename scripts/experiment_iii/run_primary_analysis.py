"""I16 — the frozen III-A primary analysis.

Refuses to run before the prediction lock is sealed, emits no overall pass/fail
verdict, and never inspects a scientific outcome on import.

    python scripts/experiment_iii/run_primary_analysis.py --estimands <json> \
        --lock <PREDICTION_LOCK.json> --bootstrap-seed <int>
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from mineocclude.experiment_iii.authority import verify_authority_binding  # noqa: E402
from mineocclude.experiment_iii.errors import ExperimentIIIError  # noqa: E402
from mineocclude.experiment_iii.prediction_lock import (  # noqa: E402
    PredictionCell,
    PredictionLock,
)
from mineocclude.experiment_iii.schema import write_json_atomic  # noqa: E402
from mineocclude.experiment_iii.statistics import primary_analysis  # noqa: E402

DEFAULT_OUT = REPOSITORY_ROOT / "docs" / "experiment_iii" / "analysis"


def _rehydrate(path: Path) -> PredictionLock:
    payload = json.loads(path.read_text(encoding="utf-8"))
    lock = PredictionLock(feature_block_hashes=payload.get("feature_block_hashes", {}))
    lock.extend(
        PredictionCell(
            identity=row["identity"],
            condition_id=row["condition_id"],
            row_index=int(row["row_index"]),
            model=row["model"],
            prediction=float(row["prediction"]),
            target=float(row["target"]),
        )
        for row in payload["cells"]
    )
    sealed = lock.seal()
    recorded = payload.get("prediction_lock_sha256")
    if recorded and sealed != recorded:
        raise ExperimentIIIError(
            "PREDICTION_LOCK_AFTER_STATISTICS",
            f"the lock file no longer hashes to {recorded}",
        )
    return lock


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--estimands", type=Path, required=True)
    parser.add_argument("--lock", type=Path, required=True)
    parser.add_argument("--bootstrap-seed", type=int, required=True)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)

    try:
        binding = verify_authority_binding()
        lock = _rehydrate(args.lock)
        per_identity = json.loads(args.estimands.read_text(encoding="utf-8"))
        payload = primary_analysis(
            per_identity, lock=lock, bootstrap_seed=args.bootstrap_seed
        )
    except ExperimentIIIError as error:
        print(f"BLOCKER_CODE={error.blocker}", file=sys.stderr)
        print(error.message, file=sys.stderr)
        return 1

    payload["authority_binding"] = binding
    digest = write_json_atomic(args.out / "primary_analysis.json", payload)
    print(f"PRIMARY_FAMILY_SIZE={payload['family_size']}")
    print(f"MULTIPLICITY={payload['multiplicity']}")
    print(f"PREDICTION_LOCK_SHA256={payload['prediction_lock_sha256']}")
    print(f"PRIMARY_ANALYSIS_SHA256={digest}")
    print("OVERALL_PASS_FAIL_VERDICT=none")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
