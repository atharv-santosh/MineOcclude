"""I16 — the frozen III-A analysis stages A14, A15 and A16.

Refuses to run before the prediction lock is sealed, emits no overall pass/fail
verdict, and never inspects a scientific outcome on import.

    A14  --stage primary   three primary estimands, Holm-3, bootstrap intervals
    A15  --stage temporal  the two predeclared temporal-rescue contrasts, Holm-2
    A16  --stage context   the four frozen context-age bins and the single
                           prespecified 12-15 vs 16-19 boundary interaction

A15 and A16 are separate lifecycle stages sharing this entrypoint, exactly as
``source_files_entrypoints`` names them ("run_primary_analysis.py (temporal
stage)" / "(context stage)"). They were never reachable: the driver had one
mode. Each stage reads the same sealed lock, so no stage can be run against
numbers a later stage produced.

The bootstrap seed defaults to the value Amendment 5 froze at authority 8.10.5a
and is verified against it -- a run may not quietly bootstrap under a different
stream.

    python scripts/experiment_iii/run_primary_analysis.py --stage primary \
        --estimands <json> --lock <PREDICTION_LOCK.json>
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
from mineocclude.experiment_iii.statistics import (  # noqa: E402
    BOUNDARY_INTERACTION_WINDOWS,
    BOOTSTRAP_REPLICATES,
    CONTEXT_AGE_BINS,
    analysis_bootstrap_seed,
    assert_concrete_bootstrap_seed,
    boundary_interaction,
    context_age_bin,
    holm_adjust,
    identity_bootstrap_interval,
    one_sided_t_test,
    primary_analysis,
    temporal_rescue,
)

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


def _temporal_stage(per_identity, *, lock, seed: int) -> dict:
    """A15 — the two predeclared temporal-rescue contrasts, Holm across two.

    The family size is fixed at two and asserted rather than derived from what
    happened to be computed: ``ANALYSIS_FAMILY_ALTERED`` and
    ``STATS_MULTIPLICITY_FAMILY_MISMATCH`` are the two ways a rescue analysis
    stops being the prespecified one.
    """
    payload = temporal_rescue(per_identity, lock=lock, bootstrap_seed=seed)
    contrasts = payload.get("contrasts")
    count = len(contrasts) if isinstance(contrasts, (list, tuple, dict)) else int(contrasts or 0)
    if count != 2:
        raise ExperimentIIIError(
            "ANALYSIS_FAMILY_ALTERED",
            f"A15 computed {count} temporal contrasts; the authority freezes "
            f"exactly two (CURRENT_MINUS_PREVIOUS vs CURRENT, TWO_FRAME_CONCAT "
            f"vs CURRENT)",
        )
    payload["stage"] = "A15"
    payload["contrasts"] = count
    payload["holm_family_size"] = 2
    payload["prediction_lock_sha256"] = lock.seal()
    return payload


def _context_stage(per_identity, *, lock, seed: int) -> dict:
    """A16 — the four frozen reporting bins and the one boundary interaction.

    Descriptive by construction: it enters no Holm family and licenses no graded
    claim. The bins are read from the frozen constant so a re-binning is a
    refusal (``ANALYSIS_CONTEXT_BIN_MISMATCH``) rather than a silent re-analysis.
    """
    if len(CONTEXT_AGE_BINS) != 4:
        raise ExperimentIIIError(
            "ANALYSIS_CONTEXT_BIN_MISMATCH",
            f"the frozen context-age bins are {CONTEXT_AGE_BINS}; the authority "
            f"freezes exactly four",
        )
    if tuple(BOUNDARY_INTERACTION_WINDOWS) != ((12, 15), (16, 19)):
        raise ExperimentIIIError(
            "ANALYSIS_CONTEXT_BIN_MISMATCH",
            f"the boundary interaction windows are "
            f"{BOUNDARY_INTERACTION_WINDOWS}; the authority freezes the adjacent "
            f"(12,15) and (16,19)",
        )
    bins = {f"{low}_{high}": {"low": low, "high": high} for low, high in CONTEXT_AGE_BINS}
    return {
        "stage": "A16",
        "schema_version": "mineocclude-experiment-iii-context-age-results-v1",
        "authority_section": "A16",
        "reporting_bins": len(CONTEXT_AGE_BINS),
        "bins": bins,
        "boundary_interaction_windows": [list(w) for w in BOUNDARY_INTERACTION_WINDOWS],
        "boundary_interactions": 1,
        "inferential_role": "DESCRIPTIVE_ONLY",
        "enters_holm_family": False,
        "licenses_graded_claim": False,
        "prediction_lock_sha256": lock.seal(),
        "per_identity_input_keys": sorted(per_identity)[:25]
        if isinstance(per_identity, dict)
        else [],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--estimands", type=Path, required=True)
    parser.add_argument("--lock", type=Path, required=True)
    parser.add_argument(
        "--stage",
        choices=("primary", "temporal", "context"),
        default="primary",
        help="A14 primary, A15 temporal, or A16 context-age",
    )
    parser.add_argument(
        "--bootstrap-seed",
        type=int,
        default=None,
        help="defaults to the 8.10.5a frozen seed; a different value is refused",
    )
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)

    try:
        binding = verify_authority_binding()
        frozen_seed = analysis_bootstrap_seed()
        seed = frozen_seed if args.bootstrap_seed is None else args.bootstrap_seed
        assert_concrete_bootstrap_seed(seed)
        if seed != frozen_seed:
            raise ExperimentIIIError(
                "STATS_BOOTSTRAP_SEED_MISMATCH",
                f"--bootstrap-seed {seed} is not the frozen analysis seed "
                f"{frozen_seed} of authority 8.10.5a; the bootstrap stream is "
                f"frozen in P2 and may not be varied per run",
            )
        lock = _rehydrate(args.lock)
        per_identity = json.loads(args.estimands.read_text(encoding="utf-8"))
        if args.stage == "primary":
            payload = primary_analysis(per_identity, lock=lock, bootstrap_seed=seed)
            filename = "primary_analysis.json"
        elif args.stage == "temporal":
            payload = _temporal_stage(per_identity, lock=lock, seed=seed)
            filename = "temporal_results.json"
        else:
            payload = _context_stage(per_identity, lock=lock, seed=seed)
            filename = "context_age_results.json"
    except ExperimentIIIError as error:
        print(f"BLOCKER_CODE={error.blocker}", file=sys.stderr)
        print(error.message, file=sys.stderr)
        return 1

    payload["authority_binding"] = binding
    payload["bootstrap_seed"] = seed
    payload["bootstrap_replicates"] = BOOTSTRAP_REPLICATES
    digest = write_json_atomic(args.out / filename, payload)
    print(f"ANALYSIS_STAGE={args.stage}")
    print(f"BOOTSTRAP_SEED={seed}")
    print(f"BOOTSTRAP_REPLICATES={BOOTSTRAP_REPLICATES}")
    if args.stage == "primary":
        print(f"PRIMARY_FAMILY_SIZE={payload['family_size']}")
        print(f"MULTIPLICITY={payload['multiplicity']}")
    elif args.stage == "temporal":
        print(f"TEMPORAL_CONTRASTS={payload['contrasts']}")
        print(f"HOLM_FAMILY_SIZE={payload['holm_family_size']}")
    else:
        print(f"CONTEXT_REPORTING_BINS={payload['reporting_bins']}")
        print(f"BOUNDARY_INTERACTIONS={payload['boundary_interactions']}")
    print(f"PREDICTION_LOCK_SHA256={payload['prediction_lock_sha256']}")
    print(f"ANALYSIS_SHA256={digest}")
    print("OVERALL_PASS_FAIL_VERDICT=none")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
