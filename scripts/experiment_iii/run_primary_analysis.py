"""A14, A15 and A16 — the frozen III-A analysis stages.

    A14  --stage primary   three primary estimands, Holm-3, bootstrap intervals
    A15  --stage temporal  the two predeclared temporal-rescue contrasts, Holm-2
    A16  --stage context   the four frozen context-age bins and the single
                           prespecified 12-15 vs 16-19 boundary interaction

A15 and A16 are separate lifecycle stages sharing this entrypoint, exactly as
``source_files_entrypoints`` names them ("run_primary_analysis.py (temporal
stage)" / "(context stage)"). Each stage reads the same sealed lock, so no stage
can be run against numbers a later stage produced.

**Every estimand is derived here, from the sealed lock and the P2-frozen
``V_c``.** The lifecycle fixes A14's controlling inputs as ``PREDICTION_LOCK``,
``FROZEN_V_C`` and P2, and its first operation as computing per-identity,
per-condition RMSE/MAE/R2. A driver that instead read an ``--estimands`` file was
skipping the computation the stage exists to perform and inviting an estimand
that no locked prediction supports.

The bootstrap seed defaults to the value Amendment 5 froze at authority 8.10.5a
and is verified against it -- a run may not quietly bootstrap under a different
stream.

    python scripts/experiment_iii/run_primary_analysis.py --stage primary
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from mineocclude.experiment_iii.a12_predictions import (  # noqa: E402
    PRIMARY_MODEL,
    TEMPORAL_MODELS,
)
from mineocclude.experiment_iii.authority import (  # noqa: E402
    TARGET_ROWS_PER_CAPTURE,
    verify_authority_binding,
)
from mineocclude.experiment_iii.errors import ExperimentIIIError  # noqa: E402
from mineocclude.experiment_iii.prediction_lock import (  # noqa: E402
    PredictionCell,
    PredictionLock,
    lock_filename,
)
from mineocclude.experiment_iii.schema import ConditionId, write_json_atomic  # noqa: E402
from mineocclude.experiment_iii.statistics import (  # noqa: E402
    BOUNDARY_INTERACTION_WINDOWS,
    BOOTSTRAP_REPLICATES,
    CONTEXT_AGE_BINS,
    analysis_bootstrap_seed,
    assert_concrete_bootstrap_seed,
    boundary_interaction,
    context_age_bin,
    evidence_coordinate,
    identity_bootstrap_interval,
    identity_metrics,
    primary_analysis,
    primary_estimands,
    temporal_rescue,
)

#: Inventory A14/A15/A16 — the canonical results root.
DEFAULT_OUT = REPOSITORY_ROOT / "docs" / "experiment_iii" / "results"
DEFAULT_P2 = (
    REPOSITORY_ROOT / "docs" / "experiment_iii" / "p2" / "P2_FREEZE_PACKAGE.json"
)

#: §5.4 — context age runs 1..19 over the frozen target window by construction.
CONTEXT_AGES = tuple(range(1, TARGET_ROWS_PER_CAPTURE + 1))

PARTIAL_CONDITIONS = (ConditionId.L1.value, ConditionId.L2.value, ConditionId.L3.value)
TEMPORAL_CONDITIONS = PARTIAL_CONDITIONS + (ConditionId.L4.value,)


def _rehydrate(path: Path) -> tuple[PredictionLock, dict]:
    if not Path(path).is_file():
        raise ExperimentIIIError(
            "ANALYSIS_INPUT_NOT_LOCKED",
            f"no sealed prediction lock at {path}; no statistic may be computed "
            f"before A12 seals one",
        )
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
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
    return lock, payload


def _frozen_v_c(p2_path: Path) -> dict[str, float]:
    """``V_c`` as P2 froze it. Never recomputed and never defaulted."""
    if not Path(p2_path).is_file():
        raise ExperimentIIIError(
            "P2_PREREQUISITE_NOT_PASSED",
            f"no P2 freeze package at {p2_path}; V_c is a frozen binding, not a "
            f"quantity this stage may derive",
        )
    package = json.loads(Path(p2_path).read_text(encoding="utf-8"))
    try:
        v_c = package["bindings"]["CONDITIONS_AND_EVIDENCE"]["V_c"]
    except (KeyError, TypeError) as error:
        raise ExperimentIIIError(
            "P2_BINDING_INCOMPLETE",
            f"{p2_path} carries no conditions.V_c binding",
        ) from error
    missing = [c.value for c in ConditionId if c.value not in v_c]
    if missing:
        raise ExperimentIIIError(
            "P2_BINDING_INCOMPLETE", f"V_c is missing conditions {missing}"
        )
    return {c.value: float(v_c[c.value]) for c in ConditionId}


def _cells_by_key(payload: dict) -> tuple[dict, dict, list[str], list[str]]:
    predictions: dict[tuple[str, str, int, str], float] = {}
    targets: dict[tuple[str, str, int, str], float] = {}
    for cell in payload["cells"]:
        key = (
            cell["identity"],
            cell["condition_id"],
            int(cell["row_index"]),
            cell["model"],
        )
        predictions[key] = float(cell["prediction"])
        targets[key] = float(cell["target"])
    identities = sorted({cell["identity"] for cell in payload["cells"]})
    models = sorted({cell["model"] for cell in payload["cells"]})
    return predictions, targets, identities, models


def _rmse_table(
    predictions, targets, identities, model: str, *, rows=None
) -> dict[str, dict[str, float]]:
    """``RMSE_ic`` for one model: {identity: {condition: rmse}}.

    ``rows`` restricts to a context-age window (A16); the default is the whole
    19-row target window (A14/A15).
    """
    indices = list(range(TARGET_ROWS_PER_CAPTURE)) if rows is None else list(rows)
    table: dict[str, dict[str, float]] = {}
    for identity in identities:
        table[identity] = {}
        for condition in (c.value for c in ConditionId):
            observed, predicted = [], []
            for row in indices:
                key = (identity, condition, row, model)
                if key not in predictions:
                    raise ExperimentIIIError(
                        "ANALYSIS_INPUT_NOT_LOCKED",
                        f"the lock has no {model} prediction for {identity}/"
                        f"{condition}/row {row}",
                    )
                observed.append(targets[key])
                predicted.append(predictions[key])
            table[identity][condition] = identity_metrics(
                identity, condition, observed, predicted
            ).rmse
    return table


def _full_metrics(predictions, targets, identities, model: str) -> dict:
    """RMSE, MAE and R2 per (identity, condition) — 8.10.1, reported in full."""
    out: dict[str, dict[str, dict[str, float]]] = {}
    for identity in identities:
        out[identity] = {}
        for condition in (c.value for c in ConditionId):
            observed = [
                targets[(identity, condition, row, model)]
                for row in range(TARGET_ROWS_PER_CAPTURE)
            ]
            predicted = [
                predictions[(identity, condition, row, model)]
                for row in range(TARGET_ROWS_PER_CAPTURE)
            ]
            metrics = identity_metrics(identity, condition, observed, predicted)
            out[identity][condition] = {
                "rmse": metrics.rmse,
                "mae": metrics.mae,
                "r2": metrics.r2,
            }
    return out


def _write_bootstrap(out: Path, stage: str, name: str, interval) -> None:
    """Inventory A14/A15/A16 — one bootstrap artifact per bootstrapped estimand."""
    directory = Path(out) / "bootstrap"
    write_json_atomic(
        directory / f"{stage.lower()}_{name}.json",
        {
            "schema_version": "mineocclude-experiment-iii-bootstrap-v1",
            "stage": stage,
            "estimand": name,
            **dict(interval),
        },
    )


# --------------------------------------------------------------------------
# A14
# --------------------------------------------------------------------------


def _primary_stage(predictions, targets, identities, *, lock, seed, v_c) -> dict:
    """A14 — derive the three estimands from the lock, then test them."""
    o_c = evidence_coordinate(v_c)
    rmse = _rmse_table(predictions, targets, identities, PRIMARY_MODEL)
    per_identity = {
        identity: primary_estimands(rmse[identity], o_c) for identity in identities
    }
    payload = primary_analysis(per_identity, lock=lock, bootstrap_seed=seed)
    payload["stage"] = "A14"
    payload["model"] = PRIMARY_MODEL
    payload["V_c"] = dict(v_c)
    payload["O_c"] = dict(o_c)
    payload["per_identity_estimands"] = per_identity
    payload["identity_condition_metrics"] = _full_metrics(
        predictions, targets, identities, PRIMARY_MODEL
    )
    payload["identities"] = identities
    payload["estimands_derived_from_lock"] = True
    return payload


# --------------------------------------------------------------------------
# A15
# --------------------------------------------------------------------------


def _temporal_stage(predictions, targets, identities, *, lock, seed) -> dict:
    """A15 — the two predeclared temporal-rescue contrasts, Holm across two.

    Per 8.12 family B the per-identity quantity is the RMSE **reduction** of the
    temporal representation against ``CURRENT``, averaged over L1..L4. Reduction,
    so the hypothesized direction stays positive as for every other test here.

    The family size is fixed at two and asserted rather than derived from what
    happened to be computed: ``ANALYSIS_FAMILY_ALTERED`` and
    ``STATS_MULTIPLICITY_FAMILY_MISMATCH`` are the two ways a rescue analysis
    stops being the prespecified one.
    """
    current = _rmse_table(predictions, targets, identities, PRIMARY_MODEL)
    per_identity: dict[str, dict[str, float]] = {}
    for representation, model in TEMPORAL_MODELS.items():
        table = _rmse_table(predictions, targets, identities, model)
        contrast = f"{representation}_VS_CURRENT"
        for identity in identities:
            reduction = [
                current[identity][condition] - table[identity][condition]
                for condition in TEMPORAL_CONDITIONS
            ]
            per_identity.setdefault(identity, {})[contrast] = float(
                sum(reduction) / len(reduction)
            )

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
    payload["schema_version"] = "mineocclude-experiment-iii-temporal-results-v1"
    payload["authority_section"] = "8.12 family B"
    payload["stage"] = "A15"
    payload["contrast_results"] = payload["contrasts"]
    payload["contrasts"] = count
    payload["holm_family_size"] = 2
    payload["averaged_over_conditions"] = list(TEMPORAL_CONDITIONS)
    payload["quantity"] = "RMSE_REDUCTION_VERSUS_CURRENT"
    payload["per_identity_contrasts"] = per_identity
    payload["may_replace_primary_readout"] = False
    payload["prediction_lock_sha256"] = lock.sealed_hash
    return payload


# --------------------------------------------------------------------------
# A16
# --------------------------------------------------------------------------


def _context_stage(predictions, targets, identities, *, lock, seed) -> dict:
    """A16 — the four frozen reporting bins and the one boundary interaction.

    Descriptive by construction: it enters no Holm family and licenses no graded
    claim. The bins are read from the frozen constant so a re-binning is a
    refusal (``ANALYSIS_CONTEXT_BIN_MISMATCH``) rather than a silent re-analysis.
    """
    lock.require_sealed("the context-age analysis")
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

    def _rows_for(low: int, high: int) -> list[int]:
        # Context age a = row_index + 1 (5.4, guaranteed by target_manifest).
        rows = [age - 1 for age in CONTEXT_AGES if low <= age <= high]
        if not rows:
            raise ExperimentIIIError(
                "ANALYSIS_CONTEXT_BIN_MISMATCH",
                f"window {low}-{high} selects no target row",
            )
        return rows

    l4 = ConditionId.L4.value
    bins: dict[str, dict] = {}
    for low, high in CONTEXT_AGE_BINS:
        table = _rmse_table(
            predictions, targets, identities, PRIMARY_MODEL, rows=_rows_for(low, high)
        )
        label = context_age_bin(low)
        bins[label] = {
            "low": low,
            "high": high,
            "rows": _rows_for(low, high),
            "identity_macro_rmse_by_condition": {
                condition: float(
                    sum(table[i][condition] for i in identities) / len(identities)
                )
                for condition in (c.value for c in ConditionId)
            },
        }

    # The single prespecified interaction, per identity, over the ADJACENT
    # 12-15 / 16-19 windows straddling the a = 15/16 context boundary.
    per_identity_interaction: dict[str, float] = {}
    for identity in identities:
        rmse_l4: dict[tuple[int, int], float] = {}
        rmse_partial: dict[tuple[int, int], float] = {}
        for window in BOUNDARY_INTERACTION_WINDOWS:
            table = _rmse_table(
                predictions, targets, [identity], PRIMARY_MODEL,
                rows=_rows_for(*window),
            )
            rmse_l4[window] = table[identity][l4]
            rmse_partial[window] = float(
                sum(table[identity][c] for c in PARTIAL_CONDITIONS)
                / len(PARTIAL_CONDITIONS)
            )
        per_identity_interaction[identity] = boundary_interaction(rmse_l4, rmse_partial)

    interval = identity_bootstrap_interval(per_identity_interaction, seed=seed)
    return {
        "stage": "A16",
        "schema_version": "mineocclude-experiment-iii-context-age-results-v1",
        "authority_section": "8.12 family C",
        "model": PRIMARY_MODEL,
        "reporting_bins": len(CONTEXT_AGE_BINS),
        "bins": bins,
        "boundary_interaction_windows": [list(w) for w in BOUNDARY_INTERACTION_WINDOWS],
        "boundary_interactions": 1,
        "per_identity_boundary_interaction": per_identity_interaction,
        "boundary_interaction_interval": interval,
        "inferential_role": "DESCRIPTIVE_ONLY",
        "enters_holm_family": False,
        "licenses_graded_claim": False,
        "causal_forgetting_claim_allowed": False,
        "identities": identities,
        "prediction_lock_sha256": lock.sealed_hash,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", type=Path, default=None)
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
    parser.add_argument("--p2", type=Path, default=DEFAULT_P2)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)
    lock_path = args.lock if args.lock is not None else args.out / lock_filename

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
        lock, payload = _rehydrate(lock_path)
        predictions, targets, identities, models = _cells_by_key(payload)
        if PRIMARY_MODEL not in models:
            raise ExperimentIIIError(
                "ANALYSIS_INPUT_NOT_LOCKED",
                f"the sealed lock carries no {PRIMARY_MODEL} predictions",
            )
        if args.stage == "primary":
            result = _primary_stage(
                predictions, targets, identities,
                lock=lock, seed=seed, v_c=_frozen_v_c(args.p2),
            )
            filename = "primary_results.json"
        elif args.stage == "temporal":
            result = _temporal_stage(
                predictions, targets, identities, lock=lock, seed=seed
            )
            filename = "temporal_results.json"
        else:
            result = _context_stage(
                predictions, targets, identities, lock=lock, seed=seed
            )
            filename = "context_age_results.json"
    except (ExperimentIIIError, OSError, KeyError, json.JSONDecodeError) as error:
        if not isinstance(error, ExperimentIIIError):
            error = ExperimentIIIError("ANALYSIS_INPUT_NOT_LOCKED", str(error))
        print(f"BLOCKER_CODE={error.blocker}", file=sys.stderr)
        print(error.message, file=sys.stderr)
        return 1

    result["authority_binding"] = binding
    result["bootstrap_seed"] = seed
    result["bootstrap_replicates"] = BOOTSTRAP_REPLICATES
    result.setdefault("prediction_lock_sha256", lock.sealed_hash)

    if args.stage == "primary":
        for name, entry in result["estimands"].items():
            _write_bootstrap(args.out, "A14", name, entry["interval"])
    elif args.stage == "temporal":
        for name, entry in result["contrast_results"].items():
            _write_bootstrap(args.out, "A15", name, entry["interval"])
    else:
        _write_bootstrap(
            args.out, "A16", "BOUNDARY_INTERACTION",
            result["boundary_interaction_interval"],
        )

    digest = write_json_atomic(args.out / filename, result)
    print(f"ANALYSIS_STAGE={args.stage}")
    print(f"BOOTSTRAP_SEED={seed}")
    print(f"BOOTSTRAP_REPLICATES={BOOTSTRAP_REPLICATES}")
    if args.stage == "primary":
        print("A14_STATUS=PASS")
        print(f"PRIMARY_FAMILY_SIZE={result['family_size']}")
        print(f"MULTIPLICITY={result['multiplicity']}")
        print(f"A14_IDENTITIES={len(result['identities'])}")
        print("A14_EXTERNAL_ESTIMANDS_REQUIRED=false")
    elif args.stage == "temporal":
        print("A15_STATUS=PASS")
        print(f"TEMPORAL_CONTRASTS={result['contrasts']}")
        print(f"HOLM_FAMILY_SIZE={result['holm_family_size']}")
    else:
        print("A16_STATUS=PASS")
        print(f"CONTEXT_REPORTING_BINS={result['reporting_bins']}")
        print(f"BOUNDARY_INTERACTIONS={result['boundary_interactions']}")
    print(f"PREDICTION_LOCK_SHA256={result['prediction_lock_sha256']}")
    print(f"ANALYSIS_SHA256={digest}")
    print("OVERALL_PASS_FAIL_VERDICT=none")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
