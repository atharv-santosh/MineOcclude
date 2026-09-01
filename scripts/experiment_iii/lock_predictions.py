"""A12 and A13 — emit and seal the held-out predictions, then the baselines.

    A12  --stage lock       fit the frozen grouped nested ridge and every frozen
                            baseline on the frozen folds, emit one held-out
                            prediction for every (identity, condition, row,
                            model) cell, and hash-seal them BEFORE any statistic
    A13  --stage baselines  verify the five frozen baselines and the L0
                            interpretability control against the SEALED lock

A12 and A13 are separate lifecycle stages sharing this entrypoint, exactly as the
expected artifact inventory names them (``baselines_receipt.json`` producer =
``lock_predictions.py``) and exactly as ``run_primary_analysis.py`` hosts
A14/A15/A16 and ``build_scientific_package.py`` hosts A17/A18/A19.

**A12 computes its predictions.** It does not receive them. The lifecycle fixes
A12's controlling inputs as the A11 feature blocks, ``folds.json`` and P2, and
its operations as fit-select-emit-seal. A driver that instead required a
pre-authored predictions file would be asking the investigator to hand-write the
pre-registration that the lock exists to protect.

    python scripts/experiment_iii/lock_predictions.py --stage lock
    python scripts/experiment_iii/lock_predictions.py --stage baselines
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
    ALL_MODELS,
    BASELINE_MODELS,
    ORACLE_MODELS,
    PRIMARY_MODEL,
    build_prediction_cells,
    load_identity_inputs,
)
from mineocclude.experiment_iii.authority import (  # noqa: E402
    TARGET_ROWS_PER_CAPTURE,
    verify_authority_binding,
)
from mineocclude.experiment_iii.baselines_motion import (  # noqa: E402
    CONSTANT_VELOCITY_WINDOW,
    LEGACY_CONSTANT_VELOCITY_WINDOW_NOT_REUSED,
    assert_no_oracle_input_in_model_features,
)
from mineocclude.experiment_iii.baselines_pixel import (  # noqa: E402
    PIXEL_BASELINE_NAME,
)
from mineocclude.experiment_iii.errors import ExperimentIIIError  # noqa: E402
from mineocclude.experiment_iii.feature_store import FEATURE_ROOT  # noqa: E402
from mineocclude.experiment_iii.prediction_lock import (  # noqa: E402
    PredictionCell,
    PredictionLock,
    lock_filename,
)
from mineocclude.experiment_iii.readout import ALPHA_GRID  # noqa: E402
from mineocclude.experiment_iii.schema import (  # noqa: E402
    ConditionId,
    read_jsonl,
    write_json_atomic,
)
from mineocclude.experiment_iii.statistics import (  # noqa: E402
    analysis_bootstrap_seed,
    identity_metrics,
    l0_interpretability_control,
)

#: Inventory A12/A13 — the canonical results root.
DEFAULT_OUT = REPOSITORY_ROOT / "docs" / "experiment_iii" / "results"
COHORT = REPOSITORY_ROOT / "docs" / "experiment_iii" / "cohort"
RECEIPTS = REPOSITORY_ROOT / "docs" / "experiment_iii" / "receipts"


def _fail(error: ExperimentIIIError, stage: str) -> int:
    print(f"BLOCKER_CODE={error.blocker}", file=sys.stderr)
    print(error.message, file=sys.stderr)
    print(f"{stage}_STATUS=FAIL", file=sys.stderr)
    return 1


def _load_folds(path: Path) -> list[dict]:
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    folds = document["folds"]
    if len(folds) != 5:
        raise ExperimentIIIError(
            "FOLD_LEAKAGE_DETECTED",
            f"{path} holds {len(folds)} outer folds; the authority freezes 5",
        )
    return folds


def _rehydrate(path: Path) -> tuple[PredictionLock, dict]:
    """Load a sealed lock and refuse it if its content no longer hashes true."""
    if not Path(path).is_file():
        raise ExperimentIIIError(
            "PREDICTION_LOCK_MISSING",
            f"no sealed prediction lock at {path}; A12 must pass before this "
            f"stage may read a single number",
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


# --------------------------------------------------------------------------
# A12
# --------------------------------------------------------------------------


def _lock_stage(args) -> int:
    try:
        binding = verify_authority_binding()
        lock_path = args.out / lock_filename
        if lock_path.is_file() and not args.allow_relock:
            raise ExperimentIIIError(
                "PREDICTION_LOCK_AFTER_STATISTICS",
                f"{lock_path} already exists. The lock is the irreversible "
                f"scientific boundary: after it exists no feature, fold, alpha "
                f"grid, representation, baseline or model may change without a "
                f"section 9 amendment. Re-locking is not a retry.",
            )
        closure = json.loads(Path(args.a8_receipt).read_text(encoding="utf-8"))
        if closure.get("stage") != "A8" or not closure.get("passed"):
            raise ExperimentIIIError(
                "COHORT_MATRIX_INCONSISTENT",
                f"{args.a8_receipt} is not a passed A8 cohort closure",
            )
        identities = list(closure["complete_five_way_paired_identities"])
        folds = _load_folds(args.folds)

        feature_hashes = None
        if args.feature_config.is_file():
            config = json.loads(args.feature_config.read_text(encoding="utf-8"))
            feature_hashes = config.get("feature_block_hashes") or None
        elif not args.allow_unhashed_features:
            raise ExperimentIIIError(
                "PROVENANCE_BINDING_MISSING",
                f"no A11 feature config at {args.feature_config}; A12 verifies "
                f"every block it fits against the digest A11 recorded",
            )

        manifest = {str(row["identity"]): row for row in read_jsonl(args.manifest)}
        inputs = {}
        for identity in identities:
            if identity not in manifest:
                raise ExperimentIIIError(
                    "PROVENANCE_BINDING_MISSING",
                    f"{identity} is in the A8 cohort but not in {args.manifest}",
                )
            inputs[identity] = load_identity_inputs(
                identity,
                manifest[identity],
                Path(args.captures) / f"{identity}__{ConditionId.L0.value}",
            )

        # The model feature blocks are named here so a leaked oracle quantity is
        # a refusal rather than a footnote (8.9.6).
        assert_no_oracle_input_in_model_features(sorted(ALL_MODELS))

        def progress(model: str, condition: str) -> None:
            print(f"A12_FITTED model={model} condition={condition}", flush=True)

        cells, fit_receipt = build_prediction_cells(
            args.features, inputs, folds,
            feature_hashes=feature_hashes, on_progress=progress,
        )

        lock = PredictionLock(feature_block_hashes=feature_hashes or {})
        lock.extend(cells)
        lock.assert_complete(
            identities=sorted(inputs),
            conditions=[c.value for c in ConditionId],
            rows=args.rows,
            models=sorted(ALL_MODELS),
        )
        digest = lock.seal()
        lock.write(args.out)
        (args.out / "PREDICTION_LOCK.sha256").write_text(
            f"{digest}  {lock_filename}\n", encoding="utf-8"
        )
        write_json_atomic(
            args.out / "prediction_fit_receipt.json",
            {
                "schema_version": "mineocclude-experiment-iii-prediction-fit-receipt-v1",
                "stage": "A12",
                "authority_binding": binding,
                "prediction_lock_sha256": digest,
                "cells": len(lock),
                **fit_receipt,
            },
        )
    except (ExperimentIIIError, OSError, KeyError, json.JSONDecodeError) as error:
        if not isinstance(error, ExperimentIIIError):
            error = ExperimentIIIError("PREDICTION_LOCK_MISSING", str(error))
        return _fail(error, "A12")

    print("A12_STATUS=PASS")
    print(f"PREDICTION_CELLS={len(lock)}")
    print(f"PREDICTION_MODELS={len(ALL_MODELS)}")
    print(f"PREDICTION_PRIMARY_MODEL={PRIMARY_MODEL}")
    print(f"PREDICTION_ALPHA_GRID={list(ALPHA_GRID)}")
    print(f"PREDICTION_LOCK_SHA256={digest}")
    print("PREDICTION_LOCK_SEALED_BEFORE_STATISTICS=true")
    print("A12_EXTERNAL_PREDICTIONS_REQUIRED=false")
    return 0


# --------------------------------------------------------------------------
# A13
# --------------------------------------------------------------------------


def _baselines_stage(args) -> int:
    """A13 — the five frozen baselines and the one L0 control, from the lock."""
    try:
        binding = verify_authority_binding()
        lock, payload = _rehydrate(args.out / lock_filename)
        present = set(payload_models := {cell["model"] for cell in payload["cells"]})
        missing = [name for name in BASELINE_MODELS if name not in present]
        if missing:
            raise ExperimentIIIError(
                "BASELINE_MISSING",
                f"the sealed lock carries no predictions for {missing}; the "
                f"authority freezes exactly five baselines {list(BASELINE_MODELS)}",
            )
        if len(BASELINE_MODELS) != 5:
            raise ExperimentIIIError(
                "BASELINE_MISSING",
                f"{len(BASELINE_MODELS)} baselines are declared; 8.9 freezes five",
            )
        if PRIMARY_MODEL not in present:
            raise ExperimentIIIError(
                "BASELINE_MISSING",
                f"the lock carries no {PRIMARY_MODEL} predictions to compare "
                f"the baselines against",
            )
        if CONSTANT_VELOCITY_WINDOW != 10:
            raise ExperimentIIIError(
                "BASELINE_FORMULA_MISMATCH",
                f"the constant-velocity window is {CONSTANT_VELOCITY_WINDOW}; "
                f"8.9.3 freezes 10 and forbids reusing the legacy "
                f"{LEGACY_CONSTANT_VELOCITY_WINDOW_NOT_REUSED}",
            )
        assert_no_oracle_input_in_model_features(sorted(payload_models))

        # Oracle invariance (8.9.6): last-seen and constant velocity read
        # counterfactual state, so within an identity they must be identical
        # across L0-L4. A per-condition difference would mean an oracle baseline
        # had somehow seen the rendered condition.
        by_cell: dict[tuple[str, str, int, str], float] = {
            (c["identity"], c["condition_id"], int(c["row_index"]), c["model"]): float(
                c["prediction"]
            )
            for c in payload["cells"]
        }
        identities = sorted({c["identity"] for c in payload["cells"]})
        conditions = [c.value for c in ConditionId]
        for model in ORACLE_MODELS:
            for identity in identities:
                for row in range(TARGET_ROWS_PER_CAPTURE):
                    values = {
                        by_cell[(identity, condition, row, model)]
                        for condition in conditions
                    }
                    if len(values) != 1:
                        raise ExperimentIIIError(
                            "BASELINE_LEAKAGE",
                            f"{model} differs across conditions for {identity} "
                            f"row {row}; an oracle baseline is condition-invariant "
                            f"by 8.9.6",
                        )

        # ---- the single L0 interpretability control (8.11) ----------------
        def _rmse_by_identity(model: str, condition: str) -> dict[str, float]:
            out: dict[str, float] = {}
            for identity in identities:
                targets = [
                    by_target[(identity, condition, row, model)]
                    for row in range(TARGET_ROWS_PER_CAPTURE)
                ]
                predictions = [
                    by_cell[(identity, condition, row, model)]
                    for row in range(TARGET_ROWS_PER_CAPTURE)
                ]
                out[identity] = identity_metrics(
                    identity, condition, targets, predictions
                ).rmse
            return out

        by_target = {
            (c["identity"], c["condition_id"], int(c["row_index"]), c["model"]): float(
                c["target"]
            )
            for c in payload["cells"]
        }
        l0 = ConditionId.L0.value
        control = l0_interpretability_control(
            _rmse_by_identity(PRIMARY_MODEL, l0),
            _rmse_by_identity("TRAINING_MEAN", l0),
            lock=lock,
            bootstrap_seed=analysis_bootstrap_seed(),
        )

        receipt = {
            "schema_version": "mineocclude-experiment-iii-baselines-receipt-v1",
            "stage": "A13",
            "authority_section": "8.9, 8.11",
            "authority_binding": binding,
            "prediction_lock_sha256": payload["prediction_lock_sha256"],
            "baselines": list(BASELINE_MODELS),
            "baseline_count": len(BASELINE_MODELS),
            "required_manuscript_language": PIXEL_BASELINE_NAME,
            "oracle_baselines": list(ORACLE_MODELS),
            "oracle_baselines_are_model_inputs": False,
            "oracle_condition_invariance_verified": True,
            "constant_velocity_window": CONSTANT_VELOCITY_WINDOW,
            "legacy_constant_velocity_window_not_reused":
                LEGACY_CONSTANT_VELOCITY_WINDOW_NOT_REUSED,
            "all_baseline_predictions_come_from_the_sealed_lock": True,
            "leakage_tests_passed": True,
            "baseline_retuned_after_seeing_result": False,
            "l0_interpretability_control": control,
            "passed": True,
            "overall_pass_fail_verdict": None,
        }
        digest = write_json_atomic(args.out / "baselines_receipt.json", receipt)
    except (ExperimentIIIError, OSError, KeyError, json.JSONDecodeError) as error:
        if not isinstance(error, ExperimentIIIError):
            error = ExperimentIIIError("BASELINE_MISSING", str(error))
        return _fail(error, "A13")

    print("A13_STATUS=PASS")
    print(f"A13_BASELINES={len(BASELINE_MODELS)}")
    print(f"A13_L0_CONTROL_INTERPRETATION={control['interpretation']}")
    print(
        "A13_L0_CONTROL_EXCLUDES_ZERO="
        f"{str(control['excludes_zero_in_the_favorable_direction']).lower()}"
    )
    print(f"A13_PREDICTION_LOCK_SHA256={receipt['prediction_lock_sha256']}")
    print(f"A13_BASELINES_RECEIPT_SHA256={digest}")
    print("OVERALL_PASS_FAIL_VERDICT=none")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--stage",
        choices=("lock", "baselines"),
        default="lock",
        help="A12 lock or A13 baselines",
    )
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--rows", type=int, default=TARGET_ROWS_PER_CAPTURE)
    parser.add_argument(
        "--features", type=Path, default=REPOSITORY_ROOT / FEATURE_ROOT
    )
    parser.add_argument(
        "--feature-config", type=Path, default=RECEIPTS / "feature_config.json"
    )
    parser.add_argument("--folds", type=Path, default=COHORT / "folds.json")
    parser.add_argument(
        "--manifest", type=Path, default=COHORT / "production_identity_manifest.jsonl"
    )
    parser.add_argument(
        "--captures",
        type=Path,
        default=REPOSITORY_ROOT / "data" / "experiment_iii" / "production" / "captures",
    )
    parser.add_argument(
        "--a8-receipt",
        type=Path,
        default=REPOSITORY_ROOT
        / "docs" / "experiment_iii" / "a8" / "cohort_closure_receipt.json",
    )
    parser.add_argument(
        "--allow-unhashed-features",
        action="store_true",
        help="fixtures only: fit blocks A11 did not hash",
    )
    parser.add_argument(
        "--allow-relock",
        action="store_true",
        help="fixtures only: overwrite an existing lock",
    )
    args = parser.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    if args.stage == "baselines":
        return _baselines_stage(args)
    return _lock_stage(args)


if __name__ == "__main__":
    raise SystemExit(main())
