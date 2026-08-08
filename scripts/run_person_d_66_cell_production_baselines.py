#!/usr/bin/env python
"""Execute Person D's frozen baselines on the real 66-cell production universe.

Real bytes only. No synthetic stand-ins, no ten-pilot replacement rows,
no activation-derived representations (Person B's
``b_to_d_successor_handoff.json`` declares
``person_d_baselines_consume_activations = false``).

Pipeline:

1. Verify every foreign authority by raw-byte SHA-256 at its exact
   commit -- Person A's frame manifest and A->D handoff, Person C's
   canonical-media manifest and C->D handoff, and Person B's row
   universe, oracle targets, fold manifest, and B->D successor handoff.
2. Reconcile Person B's declared accounting against Person B's own
   records, and report the superseded 984-row admission difference.
3. Build the execution universe from ``status == 'accepted'`` only.
4. Run each frozen baseline family through
   ``eight_family_runner.compute_family_rows``, which dispatches to the
   existing implementation with its own frozen seeds and defaults.
5. Score against Person B's oracle targets using Person B's frozen
   metric implementations.
6. Emit the prediction manifest, metric package, and D->B handoff.

``raw_pixel`` is gated by the existing deterministic memory preflight
before any pixel byte is read. If the gate declines, the family is
recorded as blocked with the plan's own reason -- never forced, never
skipped silently.

Usage:

    python scripts/run_person_d_66_cell_production_baselines.py \\
        --authority-root <DIR WITH VERIFIED A/B/C ARTIFACTS> \\
        --frame-root <PERSON A EXTERNAL PAYLOAD ROOT> \\
        --output-root docs/status/person_d_66_cell_production_baselines_v0_1
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

import numpy as np  # noqa: E402

from mineocclude.baselines import frame_handoff_v0_3 as fh3  # noqa: E402
from mineocclude.baselines import (  # noqa: E402
    production_universe_66_cell_v0_1 as pu66,
)
from mineocclude.baselines.baseline_family_input_v0_2 import (  # noqa: E402
    FROZEN_BASELINE_FAMILY_IDS,
)
from mineocclude.baselines.baseline_metrics_66_cell_v0_1 import (  # noqa: E402
    CHANCE_FLOOR_FAMILY,
    COMPARISON_CLASS_BY_FAMILY,
    U1_TARGET,
    U2_TARGET,
    build_family_target_metrics,
    build_floor_comparison,
    build_metric_package,
    build_scored_rows,
)
from mineocclude.baselines.eight_family_runner import compute_family_rows  # noqa: E402
from mineocclude.baselines.memory_planning import (  # noqa: E402
    build_raw_pixel_memory_plan,
)

RUN_ID = "person-d-66-cell-production-baselines-v0-1"
PACKAGE_RELATIVE_ROOT = "docs/status/person_d_66_cell_production_baselines_v0_1"

RAW_PIXEL_FEATURE_DIM = (
    fh3.REQUIRED_PAYLOAD_SHAPE[0]
    * fh3.REQUIRED_PAYLOAD_SHAPE[1]
    * fh3.REQUIRED_PAYLOAD_SHAPE[2]
)
RAW_PIXEL_INNER_FOLD_COUNT = 4

#: Foreign artifacts this run consumes, each pinned to a raw-byte digest.
AUTHORITY_FILES: tuple[tuple[str, str, str, str], ...] = (
    (
        "person_a_preprocessed_frame_manifest",
        "a_preprocessed_frame_manifest.json",
        fh3.PERSON_A_FRAME_MANIFEST_SHA256,
        "person_a",
    ),
    (
        "person_a_to_d_frame_handoff",
        "a_to_d_frame_handoff.json",
        fh3.PERSON_A_TO_D_HANDOFF_SHA256,
        "person_a",
    ),
    (
        "person_c_canonical_media_manifest",
        "c_canonical_media_manifest.json",
        fh3.PERSON_C_CANONICAL_MEDIA_MANIFEST_SHA256,
        "person_c",
    ),
    (
        "person_c_to_d_media_handoff",
        "c_to_d_media_handoff.json",
        fh3.PERSON_C_TO_D_MEDIA_HANDOFF_SHA256,
        "person_c",
    ),
    (
        "person_b_row_universe_records",
        "row_universe_records.jsonl",
        pu66.PERSON_B_ROW_UNIVERSE_RECORDS_SHA256,
        "person_b",
    ),
    (
        "person_b_row_universe_receipt",
        "row_universe_receipt_v0_2.json",
        pu66.PERSON_B_ROW_UNIVERSE_RECEIPT_SHA256,
        "person_b",
    ),
    (
        "person_b_oracle_target_manifest",
        "oracle_target_manifest.json",
        pu66.PERSON_B_ORACLE_TARGET_MANIFEST_SHA256,
        "person_b",
    ),
    (
        "person_b_oracle_target_records",
        "oracle_target_records.jsonl",
        pu66.PERSON_B_ORACLE_TARGET_RECORDS_SHA256,
        "person_b",
    ),
    (
        "person_b_fold_manifest",
        "fold_manifest.json",
        pu66.PERSON_B_FOLD_MANIFEST_SHA256,
        "person_b",
    ),
    (
        "person_b_to_d_successor_handoff",
        "b_to_d_successor_handoff.json",
        pu66.PERSON_B_TO_D_HANDOFF_SHA256,
        "person_b",
    ),
)


class ProductionRunError(RuntimeError):
    """Raised when the production run cannot proceed honestly."""


def _write(output_root: Path, name: str, document: Any) -> str:
    text = json.dumps(document, indent=2, sort_keys=True, default=_json_default) + "\n"
    path = output_root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _json_default(value: Any) -> Any:
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    raise TypeError(f"{type(value).__name__} is not JSON serializable")


def verify_authorities(authority_root: Path) -> dict[str, Any]:
    """Verify every foreign artifact's raw bytes. Fails closed on mismatch."""

    verified: list[dict[str, Any]] = []
    failures: list[str] = []
    for artifact_id, filename, expected, owner in AUTHORITY_FILES:
        path = authority_root / filename
        errors = fh3.verify_artifact_raw_bytes(path, expected)
        entry = {
            "artifact_id": artifact_id,
            "owner_role": owner,
            "local_path": filename,
            "expected_sha256": expected,
            "verified": not errors,
        }
        if errors:
            entry["errors"] = list(errors)
            failures.append(f"{artifact_id}:{errors[0]}")
        else:
            entry["actual_sha256"] = fh3.sha256_of_file(path)
        verified.append(entry)
    if failures:
        raise ProductionRunError(f"authority verification failed: {failures}")
    return {
        "all_verified": True,
        "artifact_count": len(verified),
        "artifacts": verified,
        "person_a_commit": fh3.PERSON_A_66_CELL_COMMIT,
        "person_b_commit": pu66.PERSON_B_66_CELL_COMMIT,
        "person_c_commit": fh3.PERSON_C_66_CELL_COMMIT,
    }


def load_authorities(authority_root: Path) -> dict[str, Any]:
    return {
        "frame_manifest": pu66.load_verified_json(
            authority_root / "a_preprocessed_frame_manifest.json",
            fh3.PERSON_A_FRAME_MANIFEST_SHA256,
        ),
        "a_to_d": pu66.load_verified_json(
            authority_root / "a_to_d_frame_handoff.json",
            fh3.PERSON_A_TO_D_HANDOFF_SHA256,
        ),
        "c_to_d": pu66.load_verified_json(
            authority_root / "c_to_d_media_handoff.json",
            fh3.PERSON_C_TO_D_MEDIA_HANDOFF_SHA256,
        ),
        "row_universe": pu66.load_verified_jsonl(
            authority_root / "row_universe_records.jsonl",
            pu66.PERSON_B_ROW_UNIVERSE_RECORDS_SHA256,
        ),
        "oracle_targets": pu66.load_verified_jsonl(
            authority_root / "oracle_target_records.jsonl",
            pu66.PERSON_B_ORACLE_TARGET_RECORDS_SHA256,
        ),
        "fold_manifest": pu66.load_verified_json(
            authority_root / "fold_manifest.json",
            pu66.PERSON_B_FOLD_MANIFEST_SHA256,
        ),
        "b_to_d": pu66.load_verified_json(
            authority_root / "b_to_d_successor_handoff.json",
            pu66.PERSON_B_TO_D_HANDOFF_SHA256,
        ),
    }


def build_pixel_features(
    frame_manifest: dict[str, Any], frame_root: Path, wanted_keys: set
) -> dict[tuple[str, int], np.ndarray]:
    """Decode only the admitted rows' payloads into compact float32 arrays.

    Never a Python list of boxed floats -- that representation was the
    confirmed root cause of a prior production OOM kill.
    """

    features: dict[tuple[str, int], np.ndarray] = {}
    for record in frame_manifest.get("records", ()):
        key = (record.get("trajectory_id"), record.get("model_frame_idx"))
        if key not in wanted_keys:
            continue
        payload = (frame_root / record["output_path"]).read_bytes()
        if len(payload) != record["payload_byte_size"]:
            raise ProductionRunError(f"{key}: payload byte size mismatch")
        if hashlib.sha256(payload).hexdigest() != record["payload_sha256"]:
            raise ProductionRunError(f"{key}: payload sha256 mismatch")
        features[key] = np.frombuffer(payload, dtype="<f4").copy()
    return features


def run(authority_root: Path, frame_root: Path, output_root: Path) -> dict[str, Any]:
    started = time.time()
    inventory: dict[str, str] = {}

    # ---- 1. authorities ------------------------------------------------
    authority_receipt = verify_authorities(authority_root)
    art = load_authorities(authority_root)

    # ---- 2. Person B accounting reconciliation -------------------------
    accounting_errors = pu66.verify_person_b_accounting(
        row_universe=art["row_universe"],
        oracle_targets=art["oracle_targets"],
        handoff=art["b_to_d"],
    )
    if accounting_errors:
        raise ProductionRunError(f"Person B accounting mismatch: {accounting_errors}")
    fold_errors = pu66.verify_fold_manifest_agreement(
        row_universe=art["row_universe"], fold_manifest=art["fold_manifest"]
    )
    if fold_errors:
        raise ProductionRunError(f"fold manifest disagreement: {fold_errors}")

    # ---- frame manifest verification -----------------------------------
    summary_errors = fh3.verify_frame_manifest_summary_counts(art["frame_manifest"])
    if summary_errors:
        raise ProductionRunError(f"frame manifest summary mismatch: {summary_errors}")
    row_keys = [
        (r["trajectory_id"], r["model_frame_idx"]) for r in art["row_universe"]
    ]
    record_errors = fh3.verify_frame_manifest_records(
        art["frame_manifest"], expected_frame_keys=row_keys
    )
    if record_errors:
        raise ProductionRunError(
            f"frame manifest record mismatch: {record_errors[:5]}"
        )

    superseded = pu66.superseded_admission_difference(
        row_universe=art["row_universe"],
        frame_manifest_records=art["frame_manifest"]["records"],
    )

    # ---- 3. execution universe -----------------------------------------
    universe = pu66.build_execution_universe(
        row_universe=art["row_universe"], oracle_targets=art["oracle_targets"]
    )
    control_type_by_key = {
        (r["trajectory_id"], r["model_frame_idx"]): r["control_type"]
        for r in art["row_universe"]
    }

    inventory["authority_verification_receipt.json"] = _write(
        output_root,
        "authority_verification_receipt.json",
        {
            "schema_id": "person-d-66-cell-authority-verification-v0-1",
            "schema_version": "1.0",
            "producer_role": "person_d",
            "run_id": RUN_ID,
            **authority_receipt,
            "person_b_accounting_reconciled": True,
            "fold_manifest_agreement": True,
            "frame_manifest_verified": True,
            "superseded_admission_difference": superseded,
            "pixel_input_contract": fh3.build_pixel_input_contract(),
        },
    )

    inventory["execution_universe.json"] = _write(
        output_root,
        "execution_universe.json",
        {
            "schema_id": "person-d-66-cell-execution-universe-v0-1",
            "schema_version": "1.0",
            "producer_role": "person_d",
            "run_id": RUN_ID,
            "admission_authority": {
                "owner_role": "person_b",
                "commit": pu66.PERSON_B_66_CELL_COMMIT,
                "records_path": pu66.PERSON_B_ROW_UNIVERSE_RECORDS_PATH,
                "records_sha256": pu66.PERSON_B_ROW_UNIVERSE_RECORDS_SHA256,
                "selector": pu66.ADMISSION_SELECTOR,
                "person_d_infers_no_admission": True,
            },
            "total_model_frame_key_count": universe.total_model_frame_key_count,
            "trajectory_count": universe.trajectory_count,
            "admitted_row_count": len(universe.contexts),
            "admitted_trajectory_count": universe.admitted_trajectory_count,
            "excluded_row_count": (
                universe.total_model_frame_key_count - len(universe.contexts)
            ),
            "excluded_counts_by_reason": universe.excluded_counts_by_reason,
            "counts_by_fold": universe.counts_by_fold,
            "counts_by_layout": universe.counts_by_layout,
            "counts_by_control_type": universe.counts_by_control_type,
            "counts_by_admission_stratum": universe.counts_by_stratum,
            "counts_by_analysis_scope": universe.counts_by_scope,
            "mu_target_available_row_count": len(universe.mu_oracle_by_key),
            "log_sigma_target_available_row_count": len(
                universe.log_sigma_oracle_by_key
            ),
            "reconciles_to_person_b": True,
            "reconciliation_mismatch_count": 0,
        },
    )

    # ---- 4/5. run the frozen baseline suite ----------------------------
    admitted_keys = set(universe.admitted_keys)
    memory_plan = build_raw_pixel_memory_plan(
        row_count=len(universe.contexts),
        feature_dim=RAW_PIXEL_FEATURE_DIM,
        outer_fold_row_counts=list(universe.counts_by_fold.values()),
        inner_fold_count=RAW_PIXEL_INNER_FOLD_COUNT,
    )

    # Family status is part of the hashed prediction manifest, so it carries
    # only deterministic facts. Wall-clock runtimes live in the separate,
    # deliberately unhashed execution receipt: a package whose digest moved
    # because a machine was busier would make real determinism unverifiable.
    family_rows: dict[str, list] = {}
    family_status: dict[str, dict[str, Any]] = {}
    family_runtime: dict[str, float] = {}
    for family_id in FROZEN_BASELINE_FAMILY_IDS:
        family_started = time.time()
        pixel_features: dict = {}
        if family_id == "raw_pixel":
            if not memory_plan.admitted:
                # Only deterministic facts here: the live budget that the
                # plan compared against lives in the execution receipt, so a
                # busier host does not change this artifact's digest.
                family_status[family_id] = {
                    "status": "blocked",
                    "reason": "memory_plan_declined",
                    "blocker_kind": "host_capacity_not_missing_input",
                    "required_free_bytes": memory_plan.estimated_peak_bytes,
                    "required_free_gib": round(memory_plan.estimated_peak_gib, 3),
                    "all_inputs_present": True,
                    "remediation": (
                        "Re-run on a host with at least the required free "
                        "physical memory; no code or input change is needed."
                    ),
                }
                family_runtime[family_id] = 0.0
                continue
            pixel_features = build_pixel_features(
                art["frame_manifest"], frame_root, admitted_keys
            )
        try:
            rows = compute_family_rows(
                family_id,
                universe.contexts,
                mu_oracle_by_key=universe.mu_oracle_by_key,
                log_sigma_oracle_by_key=universe.log_sigma_oracle_by_key,
                visible_positions_by_trajectory=universe.visible_positions_by_trajectory,
                pixel_features_by_key=pixel_features,
            )
        except Exception as error:  # noqa: BLE001 - recorded, never swallowed
            family_status[family_id] = {
                "status": "failed",
                "reason": type(error).__name__,
                "detail": str(error),
            }
            family_runtime[family_id] = round(time.time() - family_started, 6)
            pixel_features = {}
            continue
        finally:
            pixel_features = {}

        family_rows[family_id] = rows
        applicable = sum(1 for r in rows if r.applicable)
        family_status[family_id] = {
            "status": "completed",
            "emitted_row_count": len(rows),
            "applicable_row_count": applicable,
            "non_applicable_row_count": len(rows) - applicable,
        }
        family_runtime[family_id] = round(time.time() - family_started, 6)

    # ---- prediction manifest -------------------------------------------
    prediction_records = []
    for family_id in FROZEN_BASELINE_FAMILY_IDS:
        for row in family_rows.get(family_id, ()):
            prediction_records.append(
                {
                    "baseline_family": row.baseline_name,
                    "comparison_class": COMPARISON_CLASS_BY_FAMILY[row.baseline_name],
                    "target_name": row.target_name,
                    "trajectory_id": row.trajectory_id,
                    "layout_id": row.layout_id,
                    "model_frame_idx": row.model_frame_idx,
                    "fold_idx": row.fold,
                    "applicable": row.applicable,
                    "prediction": row.prediction,
                    "reason": (
                        None if row.applicable else str(row.fit_metadata.get("reason"))
                    ),
                }
            )
    prediction_records.sort(
        key=lambda r: (
            r["baseline_family"],
            r["target_name"],
            r["trajectory_id"],
            r["model_frame_idx"],
        )
    )
    applicable_total = sum(1 for r in prediction_records if r["applicable"])
    inventory["prediction_manifest.json"] = _write(
        output_root,
        "prediction_manifest.json",
        {
            "schema_id": "person-d-66-cell-baseline-predictions-v0-1",
            "schema_version": "1.0",
            "producer_role": "person_d",
            "run_id": RUN_ID,
            "evidence_kind": "real",
            "join_key": ["trajectory_id", "model_frame_idx"],
            "admitted_row_count": len(universe.contexts),
            "family_status": family_status,
            "prediction_row_count": len(prediction_records),
            "applicable_prediction_count": applicable_total,
            "non_applicable_prediction_count": (
                len(prediction_records) - applicable_total
            ),
            "oracle_targets_used_only_for_evaluation": True,
            "records": prediction_records,
        },
    )

    # ---- 6. metrics -----------------------------------------------------
    truth_by_target = {
        U1_TARGET: universe.mu_oracle_by_key,
        U2_TARGET: universe.log_sigma_oracle_by_key,
    }
    scored_by_family_target: dict[tuple[str, str], list] = {}
    family_metrics: list[dict[str, Any]] = []
    for family_id in FROZEN_BASELINE_FAMILY_IDS:
        rows = family_rows.get(family_id)
        if not rows:
            continue
        for target_name in (U1_TARGET, U2_TARGET):
            scored, accounting = build_scored_rows(
                rows,
                target_name=target_name,
                truth_by_key=truth_by_target[target_name],
                tau_by_key=universe.tau_by_key,
                control_type_by_key=control_type_by_key,
            )
            scored_by_family_target[(family_id, target_name)] = scored
            if not scored:
                continue
            family_metrics.append(
                build_family_target_metrics(
                    family_id=family_id,
                    target_name=target_name,
                    scored=scored,
                    accounting=accounting,
                )
            )

    floor_comparisons: list[dict[str, Any]] = []
    for (family_id, target_name), scored in sorted(scored_by_family_target.items()):
        if family_id == CHANCE_FLOOR_FAMILY or not scored:
            continue
        floor_scored = scored_by_family_target.get(
            (CHANCE_FLOOR_FAMILY, target_name), []
        )
        if not floor_scored:
            continue
        floor_comparisons.append(
            build_floor_comparison(
                family_id=family_id,
                target_name=target_name,
                family_scored=scored,
                floor_scored=floor_scored,
            )
        )

    metric_package = build_metric_package(
        run_id=RUN_ID,
        family_metrics=family_metrics,
        floor_comparisons=floor_comparisons,
        source_identities={
            "person_a_commit": fh3.PERSON_A_66_CELL_COMMIT,
            "person_a_frame_manifest_sha256": fh3.PERSON_A_FRAME_MANIFEST_SHA256,
            "person_b_commit": pu66.PERSON_B_66_CELL_COMMIT,
            "person_b_oracle_target_manifest_sha256": (
                pu66.PERSON_B_ORACLE_TARGET_MANIFEST_SHA256
            ),
            "person_b_row_universe_receipt_sha256": (
                pu66.PERSON_B_ROW_UNIVERSE_RECEIPT_SHA256
            ),
            "person_b_fold_manifest_sha256": pu66.PERSON_B_FOLD_MANIFEST_SHA256,
            "person_b_to_d_handoff_sha256": pu66.PERSON_B_TO_D_HANDOFF_SHA256,
            "person_c_commit": fh3.PERSON_C_66_CELL_COMMIT,
            "person_c_to_d_media_handoff_sha256": (
                fh3.PERSON_C_TO_D_MEDIA_HANDOFF_SHA256
            ),
        },
        evidence_kind="real",
    )
    inventory["baseline_metrics.json"] = _write(
        output_root, "baseline_metrics.json", metric_package
    )

    # ---- 9. D -> B production baseline handoff -------------------------
    executed = [
        family_id
        for family_id in FROZEN_BASELINE_FAMILY_IDS
        if family_status.get(family_id, {}).get("status") == "completed"
    ]
    not_executed = [
        family_id
        for family_id in FROZEN_BASELINE_FAMILY_IDS
        if family_status.get(family_id, {}).get("status") != "completed"
    ]
    inventory["d_to_b_production_baseline_handoff.json"] = _write(
        output_root,
        "d_to_b_production_baseline_handoff.json",
        {
            "schema_id": "person-d-to-person-b-66-cell-baseline-handoff-v0-1",
            "schema_version": "1.0",
            "producer_role": "person_d",
            "consumer_role": "person_b",
            "run_id": RUN_ID,
            "evidence_kind": "real",
            # A package cannot contain the hash of the commit that
            # introduces it. The authority is the Git commit carrying these
            # bytes on the branch below; the artifact digests in
            # sha256_inventory.json pin the content independently.
            "person_d_branch": "role/person-d-baselines",
            "person_d_commit_authority": (
                "the Git commit on role/person-d-baselines containing this "
                "package; see sha256_inventory.json for content digests"
            ),
            "person_d_starting_commit": "8cd2fdfc7759b285a7748ccdb4564e475b3ce1cf",
            "frame_handoff_successor": {
                "module": "src/mineocclude/baselines/frame_handoff_v0_3.py",
                "supersedes": "src/mineocclude/baselines/frame_handoff_v0_2.py",
                "predecessor_retained_unmodified": True,
                "frozen_pilot_ids_in_production_path": False,
            },
            "input_authorities": {
                "person_a_commit": fh3.PERSON_A_66_CELL_COMMIT,
                "person_a_frame_manifest_path": fh3.PERSON_A_FRAME_MANIFEST_PATH,
                "person_a_frame_manifest_sha256": fh3.PERSON_A_FRAME_MANIFEST_SHA256,
                "person_a_to_d_handoff_sha256": fh3.PERSON_A_TO_D_HANDOFF_SHA256,
                "person_a_preprocess_hash": fh3.PERSON_A_PREPROCESS_HASH,
                "person_c_commit": fh3.PERSON_C_66_CELL_COMMIT,
                "person_c_canonical_media_manifest_sha256": (
                    fh3.PERSON_C_CANONICAL_MEDIA_MANIFEST_SHA256
                ),
                "person_c_to_d_media_handoff_sha256": (
                    fh3.PERSON_C_TO_D_MEDIA_HANDOFF_SHA256
                ),
                "person_b_commit": pu66.PERSON_B_66_CELL_COMMIT,
                "person_b_oracle_target_manifest_sha256": (
                    pu66.PERSON_B_ORACLE_TARGET_MANIFEST_SHA256
                ),
                "person_b_oracle_target_records_sha256": (
                    pu66.PERSON_B_ORACLE_TARGET_RECORDS_SHA256
                ),
                "person_b_row_universe_records_sha256": (
                    pu66.PERSON_B_ROW_UNIVERSE_RECORDS_SHA256
                ),
                "person_b_row_universe_receipt_sha256": (
                    pu66.PERSON_B_ROW_UNIVERSE_RECEIPT_SHA256
                ),
                "person_b_fold_manifest_sha256": pu66.PERSON_B_FOLD_MANIFEST_SHA256,
                "person_b_to_d_handoff_sha256": pu66.PERSON_B_TO_D_HANDOFF_SHA256,
            },
            "row_universe": {
                "total_model_frame_key_count": universe.total_model_frame_key_count,
                "admitted_analysis_row_count": len(universe.contexts),
                "excluded_analysis_row_count": (
                    universe.total_model_frame_key_count - len(universe.contexts)
                ),
                "admission_owner": "person_b",
                "admission_selector": pu66.ADMISSION_SELECTOR,
                "reconciliation_mismatch_count": 0,
                "excluded_counts_by_reason": universe.excluded_counts_by_reason,
                "superseded_admission_difference": superseded,
            },
            "baseline_implementations": {
                family_id: COMPARISON_CLASS_BY_FAMILY[family_id]
                for family_id in FROZEN_BASELINE_FAMILY_IDS
            },
            "families_executed": executed,
            "families_not_executed": {
                family_id: family_status.get(family_id, {"status": "absent"})
                for family_id in not_executed
            },
            "prediction_manifest": {
                "path": f"{PACKAGE_RELATIVE_ROOT}/prediction_manifest.json",
                "sha256": inventory["prediction_manifest.json"],
                "prediction_row_count": len(prediction_records),
                "applicable_prediction_count": applicable_total,
            },
            "metric_package": {
                "path": f"{PACKAGE_RELATIVE_ROOT}/baseline_metrics.json",
                "sha256": inventory["baseline_metrics.json"],
                "aggregate_result_count": metric_package["aggregate_result_count"],
                "fold_result_count": metric_package["fold_result_count"],
                "floor_comparison_count": metric_package["floor_comparison_count"],
            },
            "dtype_and_seed_authority": {
                "analysis_arithmetic_dtype": pu66.PERSON_B_ANALYSIS_ARITHMETIC_DTYPE,
                "bootstrap_seed": 20260721,
                "permutation_seed": 20260720,
                "owner_role": "person_b",
            },
            "person_b_obligations": {
                "oracle_targets_used_only_for_evaluation": True,
                "person_d_applied_no_threshold": True,
                "person_d_created_no_metric": True,
                "probe_versus_baseline_comparison_is_person_b_owned": True,
            },
            "u4_status": {
                "control_manifest_frozen": False,
                "supplemental_capture_required": True,
                "reason": (
                    "VALID_TERMINAL_REVEAL_COUNT = 0 on the 66-cell dataset; the "
                    "real U4 control manifest still awaits Person B's direction/"
                    "dose/held-out authority and supplemental captures."
                ),
            },
            "consumable_without_further_person_d_implementation": not not_executed,
        },
    )

    # sha256_inventory covers only the deterministic artifacts above. The
    # execution receipt below carries wall-clock runtime and the live host
    # memory reading, which legitimately vary between runs, and is
    # deliberately excluded from the inventory so a busy machine can never
    # look like a changed scientific result.
    inventory_document = {
        "schema_id": "person-d-66-cell-production-baselines-inventory-v0-1",
        "schema_version": "1.0",
        "producer_role": "person_d",
        "run_id": RUN_ID,
        "evidence_kind": "real",
        "deterministic_artifacts_only": True,
        "excluded_from_inventory": ["execution_receipt.json", "sha256_inventory.json"],
        "artifact_sha256": dict(sorted(inventory.items())),
        "artifact_count": len(inventory),
    }
    inventory_sha = _write(output_root, "sha256_inventory.json", inventory_document)

    _write(
        output_root,
        "execution_receipt.json",
        {
            "schema_id": "person-d-66-cell-production-execution-receipt-v0-1",
            "schema_version": "1.0",
            "producer_role": "person_d",
            "run_id": RUN_ID,
            "excluded_from_sha256_inventory": True,
            "exclusion_reason": (
                "Carries wall-clock runtime and a live host memory reading, "
                "both of which vary between runs on the same inputs."
            ),
            "sha256_inventory_sha256": inventory_sha,
            "total_runtime_seconds": round(time.time() - started, 3),
            "per_family_runtime_seconds": dict(sorted(family_runtime.items())),
            "environment": {
                "python_version": platform.python_version(),
                "platform": sys.platform,
                "numpy_version": np.__version__,
            },
            "raw_pixel_memory_plan": {
                "family": "raw_pixel",
                "row_count": len(universe.contexts),
                "feature_dim": RAW_PIXEL_FEATURE_DIM,
                "inner_fold_count": RAW_PIXEL_INNER_FOLD_COUNT,
                "estimated_peak_bytes": memory_plan.estimated_peak_bytes,
                "estimated_peak_gib": memory_plan.estimated_peak_gib,
                "compact_payload_gib": memory_plan.compact_payload_gib,
                "detected_host_physical_bytes": (
                    memory_plan.detected_host_physical_bytes
                ),
                "detected_host_available_bytes": (
                    memory_plan.detected_host_available_bytes
                ),
                "admitted": memory_plan.admitted,
                "reasons": list(memory_plan.reasons),
            },
        },
    )
    return {
        "inventory": inventory,
        "family_status": family_status,
        "universe": universe,
        "metric_package": metric_package,
        "prediction_count": len(prediction_records),
        "applicable_prediction_count": applicable_total,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authority-root", required=True)
    parser.add_argument("--frame-root", default=fh3.PERSON_A_EXTERNAL_FRAME_ROOT)
    parser.add_argument("--output-root", default=PACKAGE_RELATIVE_ROOT)
    args = parser.parse_args(argv)

    output_root = Path(args.output_root)
    if not output_root.is_absolute():
        output_root = REPO_ROOT / output_root

    result = run(Path(args.authority_root), Path(args.frame_root), output_root)
    print(f"admitted_rows={len(result['universe'].contexts)}")
    print(f"prediction_rows={result['prediction_count']}")
    print(f"applicable_predictions={result['applicable_prediction_count']}")
    for family_id, status in result["family_status"].items():
        print(f"  {family_id}: {status['status']}")
    print(f"wrote {len(result['inventory']) + 1} artifacts to {output_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
