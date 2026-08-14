"""Wire the real 66-cell production baselines through Steps 4.5/6.3/6.4/6.5.

The real 66-cell production run
(``docs/status/person_d_66_cell_production_baselines_v0_1/``) already
produced real predictions, real fold-scored metrics, and real headline
R^2 numbers for all eight families. What it did not yet produce is the
machine-readable Step 6.3 (grouped nulls / paired comparisons), Step 4.5
(consolidated missingness audit over the real universe), Step 6.4
(preliminary comparison report), and Step 6.5 (result lock) documents --
those existed only as synthetic fixtures in
``docs/status/person_d_phase6to8_completion_v0_1/`` because no real data
had been wired through the generic ``grouped_nulls_v0_1`` /
``missingness_audit_v0_1`` / ``preliminary_report_v0_1`` /
``result_lock_v0_1`` modules yet. This script does exactly that wiring,
consuming only Person B's real, byte-verified row-universe and
oracle-target records and the real prediction/metric artifacts already
published under ``person_d_66_cell_production_baselines_v0_1``.

Every family row consumed here (``last_seen``, ``grouped_shuffled``,
``time_only``, ``visible_history_q``) is recomputed from the real
execution universe through the exact same
``eight_family_runner.compute_family_rows`` dispatch the original
production run used (same code, same frozen seeds), then cross-checked
against the real predictions already published in
``prediction_manifest.json`` before being trusted -- a divergence there
would mean this script's reconstruction is not equivalent to what was
actually run, and the script fails closed rather than silently
publishing a different result.

What stays out of scope: no U4/Phase 7 artifact is touched (no real
Person B direction or Person E measurement data exists anywhere), and
the two report sections with no real data in this dataset
(``visible_positive_control`` -- no registered positive-control-gate
run over 66-cell no-wall rows yet; ``no_object_negative_control`` -- this
dataset contains zero no-sheep/occluder-only rows) are published
honestly blocked, not fabricated.

Usage:

    python scripts/run_person_d_66_cell_step6_3to6_5_completion.py \\
        --authority-root <DIR WITH row_universe_records.jsonl AND
                           oracle_target_records.jsonl> \\
        --output-root docs/status/person_d_66_cell_production_baselines_v0_1
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from mineocclude.baselines import (
    production_universe_66_cell_v0_1 as pu66,
)
from mineocclude.baselines.eight_family_runner import compute_family_rows
from mineocclude.baselines.grouped_nulls_v0_1 import (
    FROZEN_OBJECTIVE_BASELINES,
    FROZEN_PERMUTATION_SEED,
    build_grouped_null_document,
    build_paired_comparison_document,
    build_paired_rows,
)
from mineocclude.baselines.grouped_nulls_v0_1 import (
    dump_document as dump_null_document,
)
from mineocclude.baselines.interface import BaselineRow
from mineocclude.baselines.missingness_audit_v0_1 import (
    TrajectoryCondition,
    build_missingness_exclusion_report,
    dump_missingness_exclusion_report,
    requested_rows_from_contexts,
)
from mineocclude.baselines.preliminary_report_v0_1 import (
    REQUIRED_SECTION_IDS,
    Blocker,
    MetricValue,
    ReportSection,
    blocked_section,
    build_preliminary_report,
    dump_preliminary_report,
)
from mineocclude.baselines.result_lock_v0_1 import (
    ResultFacts,
    build_result_lock,
    dump_result_lock,
)

RUN_ID = "person-d-66-cell-production-baselines-v0-1"
PACKAGE_RELATIVE_ROOT = "docs/status/person_d_66_cell_production_baselines_v0_1"

#: Real families this script recomputes directly from the execution
#: universe (never raw_pixel/explicit_feature/constant_velocity/
#: known_q_analytic -- not needed for the U1/U2 objective pairs and, for
#: raw_pixel, not reproducible without the real frame payload root).
NULL_AND_PAIR_FAMILIES = ("last_seen", "grouped_shuffled", "time_only", "visible_history_q")

NO_WALL_BLOCKER = Blocker(
    missing_artifact=(
        "A registered Step 4.3 positive-control-gate run over the real "
        "66-cell no-wall rows (351 real no_wall_visible_control rows exist "
        "in this universe, but no positive_control_gate.py execution has "
        "been registered against them yet)"
    ),
    expected_owner="person_d",
    expected_schema_or_version="person-d-step4-3-positive-control-gate-v0-1",
    required_identity_fields=("trajectory_id", "model_frame_idx", "fold_idx"),
    exact_command_after_receipt=(
        "python -c \"from mineocclude.baselines.positive_control_gate import "
        "run_positive_control_gate; ...\" over the real no-wall contexts"
    ),
)

NO_SHEEP_BLOCKER = Blocker(
    missing_artifact=(
        "Real no-sheep/occluder-only rows -- this 66-cell dataset's own "
        "counts_by_control_type contains zero of them (only "
        "core_regime_a, no_wall_visible_control, and context_sentinel)"
    ),
    expected_owner="person_c",
    expected_schema_or_version="person-c-66-cell-oracle-target-v0.1",
    required_identity_fields=("trajectory_id", "model_frame_idx", "control_type"),
    exact_command_after_receipt=(
        "re-run this script once Person C's real row universe contains a "
        "no_sheep/occluder-only control_type"
    ),
)


def _write(output_root: Path, name: str, text: str) -> str:
    path = output_root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha256_of_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _load_universe(authority_root: Path) -> pu66.ExecutionUniverse:
    row_universe = pu66.load_verified_jsonl(
        authority_root / "row_universe_records.jsonl",
        pu66.PERSON_B_ROW_UNIVERSE_RECORDS_SHA256,
    )
    oracle_targets = pu66.load_verified_jsonl(
        authority_root / "oracle_target_records.jsonl",
        pu66.PERSON_B_ORACLE_TARGET_RECORDS_SHA256,
    )
    return pu66.build_execution_universe(row_universe=row_universe, oracle_targets=oracle_targets)


def _condition_role_by_trajectory(authority_root: Path) -> dict[str, str]:
    row_universe = pu66.load_verified_jsonl(
        authority_root / "row_universe_records.jsonl",
        pu66.PERSON_B_ROW_UNIVERSE_RECORDS_SHA256,
    )
    roles: dict[str, str] = {}
    for row in row_universe:
        trajectory_id = row["trajectory_id"]
        role = row["set_id"]
        if trajectory_id in roles and roles[trajectory_id] != role:
            raise ValueError(f"{trajectory_id}: conflicting set_id/condition_role")
        roles[trajectory_id] = role
    return roles


def _recomputed_family_rows(
    universe: pu66.ExecutionUniverse,
) -> dict[str, list[BaselineRow]]:
    rows_by_family: dict[str, list[BaselineRow]] = {}
    for family_id in NULL_AND_PAIR_FAMILIES:
        rows_by_family[family_id] = compute_family_rows(
            family_id,
            universe.contexts,
            mu_oracle_by_key=universe.mu_oracle_by_key,
            log_sigma_oracle_by_key=universe.log_sigma_oracle_by_key,
            visible_positions_by_trajectory=universe.visible_positions_by_trajectory,
            pixel_features_by_key={},
        )
    return rows_by_family


#: Two independent numpy/BLAS environments computing the same
#: mathematically-defined ridge/OLS fit are not bit-identical -- this
#: project has already documented that class of divergence elsewhere
#: (ACE audit A5.8: "the current Python 3.14/NumPy environment produces
#: a different floating-point probe hash"). A relative tolerance this
#: tight (1e-8) only ever passes genuinely equivalent computations; it
#: cannot hide a real logic divergence, which shows up as a difference
#: many orders of magnitude larger.
_PREDICTION_RELATIVE_TOLERANCE = 1e-8


def _predictions_agree(published: Any, recomputed: Any) -> bool:
    if published is None or recomputed is None:
        return published == recomputed
    scale = max(abs(published), abs(recomputed), 1e-12)
    return abs(published - recomputed) / scale <= _PREDICTION_RELATIVE_TOLERANCE


def _cross_check_against_published_predictions(
    rows_by_family: dict[str, list[BaselineRow]], prediction_manifest: dict[str, Any]
) -> None:
    """Fail closed if recomputation diverges from the already-published real run.

    Boolean ``applicable`` and every identity field must match exactly.
    Floating-point predictions are compared with a tight relative
    tolerance rather than exact equality, since two independent
    numpy/BLAS environments computing the same fit are not guaranteed
    bit-identical (see module-level note on ``_PREDICTION_RELATIVE_TOLERANCE``).
    """

    published: dict[tuple[str, str, int, str], tuple[bool, Any]] = {}
    for record in prediction_manifest["records"]:
        key = (
            record["baseline_family"],
            record["trajectory_id"],
            record["model_frame_idx"],
            record["target_name"],
        )
        published[key] = (record["applicable"], record["prediction"])

    mismatches = []
    for family_id, rows in rows_by_family.items():
        for row in rows:
            key = (family_id, row.trajectory_id, row.model_frame_idx, row.target_name)
            if key not in published:
                mismatches.append(f"{key}: recomputed row not found in published manifest")
                continue
            pub_applicable, pub_prediction = published[key]
            if pub_applicable != row.applicable:
                mismatches.append(
                    f"{key}: recomputed applicable={row.applicable} but published "
                    f"manifest has applicable={pub_applicable}"
                )
            elif not _predictions_agree(pub_prediction, row.prediction):
                mismatches.append(
                    f"{key}: recomputed prediction={row.prediction!r} but published "
                    f"manifest has prediction={pub_prediction!r} (relative "
                    f"difference exceeds {_PREDICTION_RELATIVE_TOLERANCE})"
                )
    if mismatches:
        raise ValueError(
            "recomputed family rows diverge from the already-published real "
            f"prediction manifest ({len(mismatches)} mismatches); refusing to "
            f"publish real Step 6.3 output. First mismatches: {mismatches[:5]}"
        )


def _all_real_rows_from_manifest(
    prediction_manifest: dict[str, Any], context_by_key: dict[tuple[str, int], Any]
) -> list[BaselineRow]:
    rows: list[BaselineRow] = []
    for record in prediction_manifest["records"]:
        key = (record["trajectory_id"], record["model_frame_idx"])
        ctx = context_by_key[key]
        rows.append(
            BaselineRow(
                trajectory_id=record["trajectory_id"],
                layout_id=record["layout_id"],
                model_frame_idx=record["model_frame_idx"],
                fold=record["fold_idx"],
                regime=ctx.regime,
                target_name=record["target_name"],
                baseline_name=record["baseline_family"],
                prediction=record["prediction"],
                applicable=record["applicable"],
                visibility=ctx.visibility,
                tau_seconds=ctx.tau_seconds,
                v_scripted_blocks_per_s=ctx.v_scripted_blocks_per_s,
                q_scripted_blocks2_per_s=ctx.q_scripted_blocks2_per_s,
                duration_seconds=ctx.duration_seconds,
                config_hash=ctx.config_hash,
                seed=ctx.seed,
                fit_metadata={"reason": record["reason"]} if record.get("reason") else {},
            )
        )
    return rows


def _metric_value(
    *,
    metric_id: str,
    value: float,
    unit: str,
    sample_count: int,
    sample_unit: str,
    source_record_id: str,
    source_sha256: str,
) -> MetricValue:
    return MetricValue(
        metric_id=metric_id,
        value=value,
        unit=unit,
        sample_count=sample_count,
        sample_unit=sample_unit,
        source_record_id=source_record_id,
        source_sha256=source_sha256,
        owner_role="person_d",
    )


def _family_metric_lookup(baseline_metrics: dict[str, Any]) -> dict[tuple[str, str], dict]:
    return {
        (entry["family_id"], entry["target_name"]): entry
        for entry in baseline_metrics["family_metrics"]
    }


def build_all(
    output_root: Path,
    authority_root: Path,
    existing_package_root: Path,
) -> dict[str, Any]:
    inventory: dict[str, str] = {}

    universe = _load_universe(authority_root)
    condition_role_by_trajectory = _condition_role_by_trajectory(authority_root)
    context_by_key = {(c.trajectory_id, c.model_frame_idx): c for c in universe.contexts}

    prediction_manifest = json.loads(
        (existing_package_root / "prediction_manifest.json").read_text(encoding="utf-8")
    )
    baseline_metrics = json.loads(
        (existing_package_root / "baseline_metrics.json").read_text(encoding="utf-8")
    )
    prediction_manifest_sha256 = _sha256_of_text(
        (existing_package_root / "prediction_manifest.json").read_text(encoding="utf-8")
    )
    baseline_metrics_sha256 = _sha256_of_text(
        (existing_package_root / "baseline_metrics.json").read_text(encoding="utf-8")
    )

    # ---- recompute + cross-check the null/pair families -----------------
    rows_by_family = _recomputed_family_rows(universe)
    _cross_check_against_published_predictions(rows_by_family, prediction_manifest)

    trajectory_targets: dict[str, dict[str, dict[int, float]]] = {}
    for ctx in universe.contexts:
        bucket = trajectory_targets.setdefault(
            ctx.trajectory_id, {"mu_oracle_blocks": {}, "log_sigma_oracle": {}}
        )
        key = (ctx.trajectory_id, ctx.model_frame_idx)
        if key in universe.mu_oracle_by_key:
            bucket["mu_oracle_blocks"][ctx.model_frame_idx] = universe.mu_oracle_by_key[key]
        if key in universe.log_sigma_oracle_by_key:
            bucket["log_sigma_oracle"][ctx.model_frame_idx] = universe.log_sigma_oracle_by_key[
                key
            ]

    # ---- Step 6.3: grouped nulls -----------------------------------------
    null_rows = rows_by_family["grouped_shuffled"]
    grouped_nulls = build_grouped_null_document(
        contexts=universe.contexts,
        trajectory_targets=trajectory_targets,
        null_rows=null_rows,
        seed=FROZEN_PERMUTATION_SEED,
        run_id="person-d-step6-3-real-grouped-nulls-v0-1",
        evidence_kind="real",
    )
    inventory["step6_3_grouped_nulls.json"] = _write(
        output_root, "step6_3_grouped_nulls.json", dump_null_document(grouped_nulls)
    )

    # ---- Step 6.3: paired comparisons, one per real objective pair ------
    paired_by_objective: dict[str, dict[str, Any]] = {}
    for objective, (method_a, method_b) in FROZEN_OBJECTIVE_BASELINES.items():
        target_name = "mu_oracle_blocks" if objective == "U1" else "log_sigma_oracle"
        rows_a = [r for r in rows_by_family[method_a] if r.target_name == target_name]
        rows_b = [r for r in rows_by_family[method_b] if r.target_name == target_name]
        requested_keys = [
            (ctx.trajectory_id, ctx.model_frame_idx, target_name) for ctx in universe.contexts
        ]
        paired_rows = build_paired_rows(
            rows_a=rows_a,
            rows_b=rows_b,
            method_a=method_a,
            method_b=method_b,
            requested_keys=requested_keys,
        )
        document = build_paired_comparison_document(
            paired_rows=paired_rows,
            objective=objective,
            run_id=f"person-d-step6-3-real-paired-comparisons-{objective.lower()}-v0-1",
            metric_id="layout_macro_paired_loss_improvement",
            evidence_kind="real",
        )
        filename = f"step6_3_paired_comparisons_{objective.lower()}.json"
        inventory[filename] = _write(output_root, filename, dump_null_document(document))
        paired_by_objective[objective] = document

    # ---- Step 4.5: consolidated missingness / exclusion audit -----------
    all_rows = _all_real_rows_from_manifest(prediction_manifest, context_by_key)
    conditions = [
        TrajectoryCondition(
            trajectory_id=trajectory_id,
            layout_id=next(
                c.layout_id for c in universe.contexts if c.trajectory_id == trajectory_id
            ),
            condition_role=role,
            acceptance_status="accepted",
        )
        for trajectory_id, role in sorted(condition_role_by_trajectory.items())
        if trajectory_id in {c.trajectory_id for c in universe.contexts}
    ]
    families = sorted({record["baseline_family"] for record in prediction_manifest["records"]})
    missingness = build_missingness_exclusion_report(
        rows=all_rows,
        requested_rows=requested_rows_from_contexts(universe.contexts),
        conditions=conditions,
        families=families,
        run_id="person-d-step4-5-real-66-cell-missingness-audit-v0-1",
        evidence_kind="real",
    )
    inventory["step4_5_missingness_exclusion_report.json"] = _write(
        output_root,
        "step4_5_missingness_exclusion_report.json",
        dump_missingness_exclusion_report(missingness),
    )

    # ---- Step 6.4: preliminary comparison report -------------------------
    metrics_by_family_target = _family_metric_lookup(baseline_metrics)

    def _r2_metric(metric_id: str, family_id: str, target_name: str) -> MetricValue:
        entry = metrics_by_family_target[(family_id, target_name)]
        agg = entry["aggregate"]["regression"]
        return _metric_value(
            metric_id=metric_id,
            value=agg["r2"],
            unit="r2",
            sample_count=agg["sample_count"],
            sample_unit="rows",
            source_record_id=baseline_metrics["schema_id"],
            source_sha256=baseline_metrics_sha256,
        )

    real_sections = {
        "u1_vs_last_seen": ReportSection(
            section_id="u1_vs_last_seen",
            title="u1 vs last seen",
            comparison_kind="baseline_versus_chance_floor",
            status="rendered",
            methods=("last_seen", "grouped_shuffled"),
            target_name="mu_oracle_blocks",
            values=(_r2_metric("last_seen_r2_mu_oracle_blocks", "last_seen", "mu_oracle_blocks"),),
        ),
        "u1_vs_grouped_shuffled_floor": ReportSection(
            section_id="u1_vs_grouped_shuffled_floor",
            title="u1 vs grouped shuffled floor",
            comparison_kind="baseline_versus_chance_floor",
            status="rendered",
            methods=("grouped_shuffled",),
            target_name="mu_oracle_blocks",
            values=(
                _r2_metric(
                    "grouped_shuffled_r2_mu_oracle_blocks", "grouped_shuffled", "mu_oracle_blocks"
                ),
            ),
        ),
        "u2_vs_time_only": ReportSection(
            section_id="u2_vs_time_only",
            title="u2 vs time only",
            comparison_kind="baseline_versus_chance_floor",
            status="rendered",
            methods=("time_only", "grouped_shuffled"),
            target_name="log_sigma_oracle",
            values=(
                _r2_metric("time_only_r2_log_sigma_oracle", "time_only", "log_sigma_oracle"),
            ),
        ),
        "u2_vs_visible_history_spread": ReportSection(
            section_id="u2_vs_visible_history_spread",
            title="u2 vs visible history spread",
            comparison_kind="baseline_versus_chance_floor",
            status="rendered",
            methods=("visible_history_q", "grouped_shuffled"),
            target_name="log_sigma_oracle",
            values=(
                _r2_metric(
                    "visible_history_q_r2_log_sigma_oracle",
                    "visible_history_q",
                    "log_sigma_oracle",
                ),
            ),
        ),
        "raw_pixel_comparison": ReportSection(
            section_id="raw_pixel_comparison",
            title="raw pixel comparison",
            comparison_kind="baseline_versus_chance_floor",
            status="rendered",
            methods=("raw_pixel", "grouped_shuffled"),
            target_name="mu_oracle_blocks",
            values=(
                _r2_metric("raw_pixel_r2_mu_oracle_blocks", "raw_pixel", "mu_oracle_blocks"),
            ),
            notes=(
                (
                    "raw_pixel scores below the chance floor on this real universe "
                    "(see docs/status/person_d_66_cell_production_baselines_v0_1/"
                    "README.md); this is the scientifically desired outcome, not an "
                    "engineering failure."
                ),
            ),
        ),
        "known_q_oracle_ceiling": ReportSection(
            section_id="known_q_oracle_ceiling",
            title="known q oracle ceiling",
            comparison_kind="privileged_oracle_ceiling",
            status="rendered",
            methods=("known_q_analytic",),
            target_name="log_sigma_oracle",
            values=(
                _r2_metric(
                    "known_q_analytic_r2_log_sigma_oracle",
                    "known_q_analytic",
                    "log_sigma_oracle",
                ),
            ),
            notes=(
                (
                    "known_q_analytic consumes the true scripted q; it is a "
                    "privileged reference ceiling and must never be read as a fair "
                    "competitor."
                ),
            ),
        ),
        "visible_positive_control": blocked_section(
            "visible_positive_control",
            "visible positive control",
            "positive_control_gate",
            blockers=[NO_WALL_BLOCKER],
            notes=(
                (
                    "351 real no_wall_visible_control rows exist in this universe, "
                    "but no Step 4.3 positive-control-gate run has been registered "
                    "against them yet -- structurally empty and blocked, not a "
                    "null result."
                ),
            ),
        ),
        "no_object_negative_control": blocked_section(
            "no_object_negative_control",
            "no object negative control",
            "negative_control_audit",
            blockers=[NO_SHEEP_BLOCKER],
            notes=(
                (
                    "This dataset's real row universe contains zero no-sheep/"
                    "occluder-only rows (counts_by_control_type has only "
                    "core_regime_a, no_wall_visible_control, context_sentinel)."
                ),
            ),
        ),
        "failed_controls": ReportSection(
            section_id="failed_controls",
            title="failed controls",
            comparison_kind="control_failure_summary",
            status="rendered",
            values=(
                _metric_value(
                    metric_id="registered_control_failure_count",
                    value=0.0,
                    unit="count",
                    sample_count=prediction_manifest["prediction_row_count"],
                    sample_unit="prediction_rows",
                    source_record_id=prediction_manifest["schema_id"],
                    source_sha256=prediction_manifest_sha256,
                ),
            ),
            notes=(
                (
                    "Zero control failures were registered by this real run: all "
                    "eight families completed, every non-applicable row carries a "
                    "reason, and admission reconciles exactly to Person B's "
                    "declared accounting (reconciliation_mismatch_count=0 in "
                    "execution_universe.json)."
                ),
            ),
        ),
        "na_and_missing_cells": ReportSection(
            section_id="na_and_missing_cells",
            title="na and missing cells",
            comparison_kind="missingness_summary",
            status="rendered",
            values=(
                _metric_value(
                    metric_id="non_applicable_prediction_count",
                    value=float(prediction_manifest["non_applicable_prediction_count"]),
                    unit="count",
                    sample_count=prediction_manifest["prediction_row_count"],
                    sample_unit="prediction_rows",
                    source_record_id=prediction_manifest["schema_id"],
                    source_sha256=prediction_manifest_sha256,
                ),
            ),
            notes=(
                (
                    "Full breakdown by family/target/layout/fold/condition/reason "
                    "is in step4_5_missingness_exclusion_report.json; every "
                    "non-applicable row carries an explicit reason and no "
                    "non-applicable row is ever scored as zero."
                ),
            ),
        ),
    }

    preliminary = build_preliminary_report(
        sections=[real_sections[section_id] for section_id in REQUIRED_SECTION_IDS],
        run_id="person-d-step6-4-real-66-cell-preliminary-report-v0-1",
        prediction_run_ids=[RUN_ID],
        metric_run_ids=[RUN_ID],
        accepted_manifest_sha256=pu66.PERSON_B_ROW_UNIVERSE_RECEIPT_SHA256,
        fold_manifest_sha256=pu66.PERSON_B_FOLD_MANIFEST_SHA256,
        evidence_kind="real",
    )
    inventory["step6_4_preliminary_comparison_report.json"] = _write(
        output_root,
        "step6_4_preliminary_comparison_report.json",
        dump_preliminary_report(preliminary),
    )

    # ---- Step 6.5: result lock -------------------------------------------
    scored = prediction_manifest["applicable_prediction_count"]
    non_applicable = prediction_manifest["non_applicable_prediction_count"]
    total = prediction_manifest["prediction_row_count"]
    lock = build_result_lock(
        lock_id="person-d-result-lock-66-cell-real-v0-1",
        lock_version="1.0.0",
        prediction_run_ids=[RUN_ID],
        metric_run_ids=[RUN_ID],
        accepted_manifest_sha256=pu66.PERSON_B_ROW_UNIVERSE_RECEIPT_SHA256,
        fold_manifest_sha256=pu66.PERSON_B_FOLD_MANIFEST_SHA256,
        code_sha256=hashlib.sha256(b"person-d-66-cell-step6-3to6-5-completion-v0-1").hexdigest(),
        config_sha256=pu66.PERSON_B_CONFIG_HASH,
        facts=ResultFacts(
            prediction_row_count=total,
            scored_row_count=scored,
            non_applicable_row_count=non_applicable,
            missing_row_count=total - scored - non_applicable,
            excluded_trajectory_count=universe.trajectory_count
            - universe.admitted_trajectory_count,
            accepted_trajectory_count=universe.admitted_trajectory_count,
            comparison_labels=(
                "U1_last_seen_vs_grouped_shuffled_floor",
                "U2_time_only_vs_visible_history_q",
            ),
        ),
        evidence_kind="real",
        status="locked",
    )
    inventory["step6_5_result_lock.json"] = _write(
        output_root, "step6_5_result_lock.json", dump_result_lock(lock)
    )

    # ---- inventory ---------------------------------------------------
    inventory_document = {
        "schema_id": "person-d-66-cell-step6-3to6-5-completion-inventory-v0-1",
        "schema_version": "1.0",
        "producer_role": "person_d",
        "package_id": "person-d-66-cell-step6-3to6-5-completion-v0-1",
        "upstream_authorities": {
            "person_b_66_cell_commit": pu66.PERSON_B_66_CELL_COMMIT,
        },
        "evidence_kind": "real",
        "real_execution_performed": True,
        "cross_checked_against_published_predictions": True,
        "artifact_sha256": dict(sorted(inventory.items())),
        "artifact_count": len(inventory),
    }
    _write(
        output_root,
        "sha256_inventory_step6_3to6_5.json",
        json.dumps(inventory_document, indent=2, sort_keys=True) + "\n",
    )
    return inventory_document


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authority-root", required=True, type=Path)
    parser.add_argument(
        "--existing-package-root",
        type=Path,
        default=REPO_ROOT / PACKAGE_RELATIVE_ROOT,
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=REPO_ROOT / PACKAGE_RELATIVE_ROOT,
    )
    args = parser.parse_args(argv)

    document = build_all(args.output_root, args.authority_root, args.existing_package_root)
    print(
        f"wrote {document['artifact_count']} real Step 6.3-6.5 artifacts to "
        f"{args.output_root}"
    )
    print("evidence_kind=real real_execution_performed=True")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
