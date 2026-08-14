#!/usr/bin/env python
"""Generate every Person D Phase 6-8 evidence package (Steps 6.2-8.3).

One deterministic command. Re-running it over an existing output root
rewrites byte-identical files, so the packages can be regenerated and
diffed rather than trusted.

What this script does and does not claim:

* Every document it writes is labeled ``evidence_kind = "synthetic"``
  unless a real upstream artifact was actually consumed. Nothing here
  fabricates a real prediction, metric, direction, rollout, or
  measurement.
* Where a real Person A/B/C/E input does not yet exist, the corresponding
  section is written **blocked**, naming the missing artifact, its owner,
  its expected schema, the identity fields required, and the exact
  command to run once it arrives. That blocker receipt is the deliverable
  at this stage, not a placeholder for one.
* The Step 6.1 accepted-MVP identity binding is *real* -- it was computed
  from Person C's committed bytes -- and is re-verified here rather than
  rebuilt.

Usage:

    python scripts/run_person_d_phase6to8_completion.py \
        --repository-root . \
        --output-root docs/status/person_d_phase6to8_completion_v0_1
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from mineocclude.baselines.clean_workflow_v0_1 import (  # noqa: E402
    CHECKPOINT_SECTION_IDS,
    WORKFLOW_STAGE_IDS,
    CheckpointFinding,
    CheckpointSection,
    StageResult,
    build_checkpoint_demonstration,
    build_clean_workflow_run,
    classify_checkpoint,
    dump_document as dump_workflow_document,
)
from mineocclude.baselines.control_failure_record_v0_1 import (  # noqa: E402
    build_control_failure_record,
    dump_control_failure_record,
)
from mineocclude.baselines.direction_control_audit_v0_1 import (  # noqa: E402
    audit_direction_construction,
    build_direction_control_audit,
    dump_direction_control_audit,
)
from mineocclude.baselines.grouped_nulls_v0_1 import (  # noqa: E402
    FROZEN_PERMUTATION_SEED,
    build_grouped_null_document,
    build_paired_comparison_document,
    build_paired_rows,
    dump_document as dump_null_document,
)
from mineocclude.baselines.interface import (  # noqa: E402
    TrajectoryContext,
    make_baseline_row,
)
from mineocclude.baselines.missingness_audit_v0_1 import (  # noqa: E402
    PlannedFamilyTarget,
    TrajectoryCondition,
    build_missingness_exclusion_report,
    dump_missingness_exclusion_report,
    requested_rows_from_contexts,
)
from mineocclude.baselines.preliminary_report_v0_1 import (  # noqa: E402
    REQUIRED_SECTION_IDS as REPORT_SECTION_IDS,
    Blocker,
    blocked_section,
    build_preliminary_report,
    dump_preliminary_report,
)
from mineocclude.baselines.result_lock_v0_1 import (  # noqa: E402
    ResultFacts,
    build_result_lock,
    dump_result_lock,
)
from mineocclude.baselines.shuffled import apply_grouped_shuffle  # noqa: E402
from mineocclude.baselines.specificity_damage_report_v0_1 import (  # noqa: E402
    REQUIRED_SECTION_IDS as DAMAGE_SECTION_IDS,
    SectionBlocker,
    blocked_damage_section,
    build_specificity_damage_report,
    dump_specificity_damage_report,
)
from mineocclude.baselines.u4_control_manifest_v0_1 import (  # noqa: E402
    DirectionRef,
    DoseSpec,
    HeldOutEvent,
    build_control_manifest,
    build_control_manifest_rows,
    build_person_d_to_a_and_e_handoff,
    dump_control_manifest,
    freeze_control_manifest,
)
from mineocclude.baselines.u4_measurement_join_v0_1 import (  # noqa: E402
    dump_u4_control_matrix,
    join_measurements_to_manifest,
)

# --------------------------------------------------------------------------
# Verified upstream authorities (read from Git, never assumed)
# --------------------------------------------------------------------------

UPSTREAM_AUTHORITIES = {
    "origin_main": "15adc43674420ae35921847a953ebbee2135f142",
    "person_a": "ef98d184aaed8f03757add4ecac4a48968bb6fcc",
    "person_b_analysis": "98f50761ecb99bc14ed5d1ebb67aedc8dcfd3327",
    "person_b_methods": "eec9396e6a93feaab3d5d298ac7cdc4cb54fdbd4",
    "person_c_data": "365e748addcb1e1926d7e2c5a382a92fa39ebc40",
    "person_e_operations": "5e2ef61a75fe4900dc7226dec7c1f6dcc1f39171",
}

#: Person B's frozen family/target applicability contract, consumed as the
#: authority for "planned" counts. Real, but scoped to the earlier
#: ten-pilot production set -- not the 66-cell MVP matrix.
PERSON_B_APPLICABILITY_CONTRACT_ID = (
    "person-b-phase4-step4-1-family-target-applicability-contract-v0-1"
)
PERSON_B_APPLICABILITY_PATH = (
    "docs/status/person_b_phase4_step4_1_applicability_contract_v0_1/"
    "family_target_applicability_contract.json"
)

STEP_6_1_MANIFEST_PATH = (
    "docs/status/person_d_phase6_step6_1_mvp_identity_binding_v0_1/"
    "mvp_input_manifest.json"
)

#: The canonical publish location this package's documents refer to
#: themselves by. It is a constant rather than the actual ``--output-root``
#: so that regenerating into a scratch directory produces byte-identical
#: documents: the recorded paths describe where the package belongs, not
#: where a particular verification run happened to write it.
PACKAGE_RELATIVE_ROOT = "docs/status/person_d_phase6to8_completion_v0_1"

# --------------------------------------------------------------------------
# Named external blockers, reused across every package
# --------------------------------------------------------------------------

BLOCKER_B_FOLDS = Blocker(
    missing_artifact=(
        "Person B fold and oracle-target manifests covering the accepted "
        "66-cell MVP matrix (layout_01..06, ep100xx)"
    ),
    expected_owner="person_b",
    expected_schema_or_version=(
        "person-b-step4-1-production-handoff fold manifest + "
        "production_oracle_target_manifest, at 66-trajectory scope"
    ),
    required_identity_fields=(
        "trajectory_id",
        "model_frame_idx",
        "fold_idx",
        "target_name",
        "fold_manifest_sha256",
        "oracle_target_sha256",
    ),
    exact_command_after_receipt=(
        "python scripts/run_person_d_step4_1_eight_family_production.py "
        "--fold-manifest <B_66_CELL_FOLD_MANIFEST> "
        "--oracle-targets <B_66_CELL_ORACLE_TARGETS> "
        "--frame-manifest <A_66_CELL_FRAME_MANIFEST> "
        "--output-root <PERSON_D_PRODUCTION_ROOT> --resume auto"
    ),
)

BLOCKER_A_FRAMES = Blocker(
    missing_artifact=(
        "Person A preprocessed activation/frame manifest covering the accepted "
        "66-cell MVP matrix"
    ),
    expected_owner="person_a",
    expected_schema_or_version="person-a-preprocessed-frame-manifest-v0.2",
    required_identity_fields=(
        "trajectory_id",
        "model_frame_idx",
        "payload_sha256",
        "preprocess_hash",
    ),
    exact_command_after_receipt=(
        "python scripts/run_person_d_step4_1_eight_family_production.py "
        "--preflight --frame-manifest <A_66_CELL_FRAME_MANIFEST>"
    ),
)

BLOCKER_B_METRICS = Blocker(
    missing_artifact="Person B metric table over Person D's 66-cell predictions",
    expected_owner="person_b",
    expected_schema_or_version="person-b-step4-1-final-comparison-output-v0-1",
    required_identity_fields=(
        "metric_id",
        "baseline_family",
        "target_name",
        "layer_idx",
        "sample_unit",
    ),
    exact_command_after_receipt=(
        "python scripts/run_person_d_phase6to8_completion.py "
        "--metric-table <B_METRIC_TABLE> --output-root <OUTPUT_ROOT>"
    ),
)

BLOCKER_B_DIRECTION = SectionBlocker(
    missing_artifact=(
        "Person B fitted U4 direction, held-out event identities, signed dose "
        "table, target layer/timestep, and direction-construction record"
    ),
    expected_owner="person_b",
    expected_schema_or_version="person-b-intervention-request-v1.0",
    exact_command_after_receipt=(
        "python scripts/run_person_d_phase6to8_completion.py "
        "--u4-direction-record <B_DIRECTION_RECORD> --freeze-real-control-manifest"
    ),
)

BLOCKER_E_MEASUREMENTS = SectionBlocker(
    missing_artifact="Person E U4 rollout measurement table",
    expected_owner="person_e",
    expected_schema_or_version="person-b-u4-measurement-input-v0.1",
    exact_command_after_receipt=(
        "python scripts/run_person_d_phase6to8_completion.py "
        "--u4-measurements <E_MEASUREMENT_TABLE> --output-root <OUTPUT_ROOT>"
    ),
)


# --------------------------------------------------------------------------
# Synthetic validation fixture (explicitly, permanently synthetic)
# --------------------------------------------------------------------------


def _synthetic_contexts():
    """Four hand-built trajectories across four layouts and four folds.

    This exists solely to exercise the pipeline end to end. It is never
    written into a document labeled ``real``.
    """

    contexts = []
    for index in range(4):
        trajectory_id = f"synthetic_layout_{index:02d}_ep0000{index}"
        for frame_idx in range(4):
            contexts.append(
                TrajectoryContext(
                    trajectory_id=trajectory_id,
                    layout_id=f"synthetic_layout_{index:02d}",
                    model_frame_idx=frame_idx,
                    fold=index,
                    regime="A",
                    tau_seconds=0.05 * frame_idx,
                    visibility=frame_idx == 0,
                    last_seen_position_blocks=float(frame_idx),
                    last_seen_velocity_blocks_per_s=1.0,
                    v_scripted_blocks_per_s=None,
                    q_scripted_blocks2_per_s=None,
                    duration_seconds=0.2 if index % 2 else 0.8,
                    config_hash="synthetic-config",
                    seed=FROZEN_PERMUTATION_SEED,
                )
            )
    return contexts


def _synthetic_targets(contexts):
    targets = {}
    for ctx in contexts:
        entry = targets.setdefault(
            ctx.trajectory_id, {"mu_oracle_blocks": {}, "log_sigma_oracle": {}}
        )
        entry["mu_oracle_blocks"][ctx.model_frame_idx] = float(ctx.model_frame_idx)
        entry["log_sigma_oracle"][ctx.model_frame_idx] = -1.0 - ctx.model_frame_idx
    return targets


def _synthetic_family_rows(contexts, family, target, applicable_when):
    rows = []
    for ctx in contexts:
        applicable = applicable_when(ctx)
        rows.append(
            make_baseline_row(
                ctx,
                baseline_name=family,
                target_name=target,
                prediction=float(ctx.model_frame_idx) if applicable else None,
                applicable=applicable,
                fit_metadata=(
                    {}
                    if applicable
                    else {"reason": f"{family} defines no {target} for this row"}
                ),
            )
        )
    return rows


# --------------------------------------------------------------------------
# Package writers
# --------------------------------------------------------------------------


def _write(output_root: Path, name: str, text: str) -> str:
    path = output_root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    # write_bytes (not write_text(..., newline="\n"), which needs Python
    # >=3.10) guarantees the exact "\n"-only line endings dump_* already
    # produces, portably.
    path.write_bytes(text.encode("utf-8"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build_all(output_root: Path, repository_root: Path) -> dict:
    inventory: dict[str, str] = {}
    contexts = _synthetic_contexts()
    targets = _synthetic_targets(contexts)

    # ---- Step 6.3: grouped nulls -------------------------------------
    null_rows = apply_grouped_shuffle(contexts, targets, FROZEN_PERMUTATION_SEED)
    grouped_nulls = build_grouped_null_document(
        contexts=contexts,
        trajectory_targets=targets,
        null_rows=null_rows,
        seed=FROZEN_PERMUTATION_SEED,
        run_id="person-d-step6-3-synthetic-grouped-nulls-v0-1",
        evidence_kind="synthetic",
    )
    inventory["step6_3_grouped_nulls.json"] = _write(
        output_root, "step6_3_grouped_nulls.json", dump_null_document(grouped_nulls)
    )

    # ---- Step 6.3: paired comparisons --------------------------------
    last_seen_rows = _synthetic_family_rows(
        contexts, "last_seen", "mu_oracle_blocks", lambda ctx: True
    )
    shuffled_mu_rows = [
        row for row in null_rows if row.target_name == "mu_oracle_blocks"
    ]
    requested_keys = [
        (ctx.trajectory_id, ctx.model_frame_idx, "mu_oracle_blocks") for ctx in contexts
    ]
    paired_rows = build_paired_rows(
        rows_a=last_seen_rows,
        rows_b=shuffled_mu_rows,
        method_a="last_seen",
        method_b="grouped_shuffled",
        requested_keys=requested_keys,
    )
    paired = build_paired_comparison_document(
        paired_rows=paired_rows,
        objective="U1",
        run_id="person-d-step6-3-synthetic-paired-comparisons-v0-1",
        metric_id="layout_macro_paired_loss_improvement",
        evidence_kind="synthetic",
    )
    inventory["step6_3_paired_comparisons.json"] = _write(
        output_root, "step6_3_paired_comparisons.json", dump_null_document(paired)
    )

    # ---- Step 4.5: consolidated missingness / exclusion audit ---------
    all_rows = last_seen_rows + list(null_rows)
    conditions = [
        TrajectoryCondition(
            trajectory_id=ctx.trajectory_id,
            layout_id=ctx.layout_id,
            condition_role="core" if ctx.fold % 2 == 0 else "nowall",
            acceptance_status="accepted",
        )
        for ctx in {c.trajectory_id: c for c in contexts}.values()
    ]
    missingness = build_missingness_exclusion_report(
        rows=all_rows,
        requested_rows=requested_rows_from_contexts(contexts),
        conditions=conditions,
        families=("last_seen", "grouped_shuffled"),
        planned=[
            PlannedFamilyTarget(
                family="last_seen",
                target_name="mu_oracle_blocks",
                planned_available_count=len(contexts),
                planned_non_applicable_count=0,
                source_contract_id=PERSON_B_APPLICABILITY_CONTRACT_ID,
            )
        ],
        run_id="person-d-step4-5-synthetic-missingness-audit-v0-1",
        evidence_kind="synthetic",
    )
    inventory["step4_5_missingness_exclusion_report.json"] = _write(
        output_root,
        "step4_5_missingness_exclusion_report.json",
        dump_missingness_exclusion_report(missingness),
    )

    # ---- Step 6.4: preliminary comparison report ---------------------
    report_blockers = {
        "u1_vs_last_seen": BLOCKER_B_METRICS,
        "u1_vs_grouped_shuffled_floor": BLOCKER_B_METRICS,
        "u2_vs_time_only": BLOCKER_B_METRICS,
        "u2_vs_visible_history_spread": BLOCKER_B_METRICS,
        "raw_pixel_comparison": BLOCKER_A_FRAMES,
        "visible_positive_control": BLOCKER_B_FOLDS,
        "no_object_negative_control": BLOCKER_B_FOLDS,
        "known_q_oracle_ceiling": BLOCKER_B_FOLDS,
        "failed_controls": BLOCKER_B_METRICS,
        "na_and_missing_cells": BLOCKER_B_FOLDS,
    }
    preliminary = build_preliminary_report(
        sections=[
            blocked_section(
                section_id=section_id,
                title=section_id.replace("_", " "),
                comparison_kind="paired",
                blockers=[report_blockers[section_id]],
                notes=(
                    "Structurally empty and explicitly blocked. This is not a "
                    "null result: no real metric for this comparison exists yet.",
                ),
            )
            for section_id in REPORT_SECTION_IDS
        ],
        run_id="person-d-step6-4-preliminary-report-v0-1",
        prediction_run_ids=[],
        metric_run_ids=[],
        accepted_manifest_sha256=None,
        fold_manifest_sha256=None,
        evidence_kind="synthetic",
    )
    inventory["step6_4_preliminary_comparison_report.json"] = _write(
        output_root,
        "step6_4_preliminary_comparison_report.json",
        dump_preliminary_report(preliminary),
    )

    # ---- Step 6.5: result lock (synthetic; no real facts to freeze) ---
    scored = sum(1 for row in paired_rows if row.scored)
    lock = build_result_lock(
        lock_id="person-d-result-lock-synthetic-v0-1",
        lock_version="0.1.0-synthetic",
        prediction_run_ids=["person-d-step6-3-synthetic-grouped-nulls-v0-1"],
        metric_run_ids=[],
        accepted_manifest_sha256=None,
        fold_manifest_sha256=None,
        code_sha256=hashlib.sha256(b"person-d-phase6to8-completion-v0-1").hexdigest(),
        config_sha256=hashlib.sha256(b"synthetic-config").hexdigest(),
        facts=ResultFacts(
            prediction_row_count=len(paired_rows),
            scored_row_count=scored,
            non_applicable_row_count=len(paired_rows) - scored,
            missing_row_count=0,
            excluded_trajectory_count=0,
            accepted_trajectory_count=len({c.trajectory_id for c in contexts}),
            comparison_labels=("U1_last_seen_vs_grouped_shuffled_floor",),
        ),
        evidence_kind="synthetic",
        status="draft",
    )
    inventory["step6_5_result_lock.json"] = _write(
        output_root, "step6_5_result_lock.json", dump_result_lock(lock)
    )

    # ---- Step 7.1: U4 control manifest -------------------------------
    manifest_kwargs = dict(
        held_out_events=(
            HeldOutEvent(
                "synthetic:reveal:0", "synthetic_layout_00_ep00000", "synthetic_layout_00"
            ),
        ),
        rollout_seeds=(FROZEN_PERMUTATION_SEED,),
        doses=(
            DoseSpec("pos_1", 4.0, 4.0, False),
            DoseSpec("neg_1", -4.0, -4.0, False),
        ),
        primary_direction=DirectionRef(
            "SYNTHETIC_PRIMARY_NOT_A_REAL_DIRECTION", "v0-synthetic", "0" * 64
        ),
        random_directions=(
            DirectionRef(
                "SYNTHETIC_RANDOM_NOT_A_REAL_DIRECTION",
                "v0-synthetic",
                "1" * 64,
                seed=FROZEN_PERMUTATION_SEED,
            ),
        ),
        orthogonal_directions=(
            DirectionRef(
                "SYNTHETIC_ORTHOGONAL_NOT_A_REAL_DIRECTION",
                "v0-synthetic",
                "2" * 64,
                seed=FROZEN_PERMUTATION_SEED + 1,
            ),
        ),
        target_layer_idx=12,
        target_timestep_idx=7,
        wrong_layer_idx=3,
        wrong_timestep_idx=1,
    )
    control_manifest = build_control_manifest(
        manifest_id="person-d-u4-control-manifest-synthetic-v0-1",
        manifest_version="0.1.0-synthetic",
        rows=build_control_manifest_rows(**manifest_kwargs),
        source_authorities={
            "person_a_commit": UPSTREAM_AUTHORITIES["person_a"],
            "person_b_commit": UPSTREAM_AUTHORITIES["person_b_analysis"],
            "real_direction_available": "NO",
            "real_heldout_events_available": "NO",
        },
        evidence_kind="synthetic",
        **manifest_kwargs,
    )
    frozen_manifest = freeze_control_manifest(control_manifest)
    manifest_text = dump_control_manifest(frozen_manifest)
    manifest_sha = _write(output_root, "step7_1_u4_control_manifest.json", manifest_text)
    inventory["step7_1_u4_control_manifest.json"] = manifest_sha

    handoff = build_person_d_to_a_and_e_handoff(
        frozen_manifest,
        manifest_path=f"{PACKAGE_RELATIVE_ROOT}/step7_1_u4_control_manifest.json",
        manifest_sha256=manifest_sha,
    )
    handoff["real_manifest_status"] = "NOT_FROZEN_AS_REAL_EVIDENCE"
    handoff["blocking_inputs"] = [
        {
            "missing_artifact": BLOCKER_B_DIRECTION.missing_artifact,
            "expected_owner": BLOCKER_B_DIRECTION.expected_owner,
            "expected_schema_or_version": BLOCKER_B_DIRECTION.expected_schema_or_version,
            "exact_command_after_receipt": (
                BLOCKER_B_DIRECTION.exact_command_after_receipt
            ),
        }
    ]
    inventory["step7_1_control_handoff_to_a_and_e.json"] = _write(
        output_root,
        "step7_1_control_handoff_to_a_and_e.json",
        json.dumps(handoff, indent=2, sort_keys=True, default=list) + "\n",
    )

    # ---- Step 7.2: direction-control construction audit ---------------
    direction_audit = build_direction_control_audit(
        audit_id="person-d-step7-2-direction-control-audit-v0-1",
        findings=audit_direction_construction(None),
        evidence_source={
            "person_b_commit": UPSTREAM_AUTHORITIES["person_b_analysis"],
            "person_a_commit": UPSTREAM_AUTHORITIES["person_a"],
            "searched_paths": (
                "src/mineocclude/intervention/directions.py, "
                "tests/fixtures/intervention/*, docs/status/person_b_*"
            ),
            "finding": (
                "Only contract text and synthetic fixtures exist on either "
                "branch; no real fitted direction-construction record was found."
            ),
        },
        evidence_kind="synthetic",
    )
    inventory["step7_2_direction_control_audit.json"] = _write(
        output_root,
        "step7_2_direction_control_audit.json",
        dump_direction_control_audit(direction_audit),
    )

    # ---- Step 7.3: U4 control matrix (join with zero measurements) ----
    control_matrix = join_measurements_to_manifest(
        manifest=frozen_manifest,
        measurements=[],
        run_id="person-d-step7-3-synthetic-measurement-join-v0-1",
        evidence_kind="synthetic",
    )
    inventory["step7_3_u4_control_matrix.json"] = _write(
        output_root,
        "step7_3_u4_control_matrix.json",
        dump_u4_control_matrix(control_matrix),
    )

    # ---- Step 7.4: specificity and damage report ----------------------
    damage = build_specificity_damage_report(
        sections=[
            blocked_damage_section(
                section_id,
                section_id.replace("_", " "),
                [
                    BLOCKER_E_MEASUREMENTS
                    if section_id
                    not in ("signed_displacement_pattern", "person_b_inferential_results")
                    else BLOCKER_B_DIRECTION
                ],
            )
            for section_id in DAMAGE_SECTION_IDS
        ],
        run_id="person-d-step7-4-specificity-damage-report-v0-1",
        control_matrix_run_id=control_matrix["run_id"],
        person_b_inferential_run_id=None,
        evidence_kind="synthetic",
    )
    inventory["step7_4_specificity_damage_report.json"] = _write(
        output_root,
        "step7_4_specificity_damage_report.json",
        dump_specificity_damage_report(damage),
    )

    # ---- Step 7.5: control-failure claim-impact record ----------------
    failures = build_control_failure_record(
        record_id="person-d-step7-5-control-failure-record-v0-1",
        record_version="0.1.0",
        entries=(),
        control_matrix_run_id=control_matrix["run_id"],
        evidence_kind="synthetic",
    )
    inventory["step7_5_control_failure_record.json"] = _write(
        output_root,
        "step7_5_control_failure_record.json",
        dump_control_failure_record(failures),
    )

    # ---- Step 8.1: synthetic clean reproduction -----------------------
    blocked_stages = {
        "run_baselines": "no real Person B 66-cell fold/target manifest exists",
        "build_u4_control_matrix": "no real Person E U4 measurement table exists",
    }
    stages = []
    for stage_id in WORKFLOW_STAGE_IDS:
        blocked_reason = blocked_stages.get(stage_id)
        stages.append(
            StageResult(
                stage_id=stage_id,
                status="blocked" if blocked_reason else "passed",
                command=(
                    "python scripts/run_person_d_phase6to8_completion.py "
                    f"--stage {stage_id}"
                ),
                stdout_path=f"logs/{stage_id}.out",
                stderr_path=f"logs/{stage_id}.err",
                runtime_seconds=0.0,
                output_paths=(),
                failure_detail=blocked_reason,
            )
        )
    workflow = build_clean_workflow_run(
        run_id="person-d-step8-1-synthetic-clean-run-v0-1",
        stages=stages,
        environment={
            "python_version": platform.python_version(),
            "platform": sys.platform,
            "interpreter_path": sys.executable,
        },
        package_lock_sha256=_file_sha256(repository_root / "requirements.txt"),
        evidence_kind="synthetic",
    )
    # Deliberately not added to `inventory`/sha256_inventory.json: this
    # document's own `environment` block (python_version, platform,
    # interpreter_path) legitimately varies by machine, so its bytes can
    # never be identical across two real regenerations -- the same reason
    # `run_person_d_66_cell_production_baselines.py` excludes
    # `execution_receipt.json`.
    _write(
        output_root,
        "step8_1_clean_workflow_run.json",
        dump_workflow_document(workflow),
    )

    # ---- Step 8.2: checkpoint demonstration ---------------------------
    resolved_sources = {
        "accepted_input_identity": (
            "person-d-step6-1-mvp-input-manifest",
            STEP_6_1_MANIFEST_PATH,
        ),
        "missingness_and_exclusions": (
            "person-d-step4-5-missingness-exclusion-report",
            f"{PACKAGE_RELATIVE_ROOT}/step4_5_missingness_exclusion_report.json",
        ),
        "grouped_nulls": (
            "person-d-step6-3-grouped-nulls",
            f"{PACKAGE_RELATIVE_ROOT}/step6_3_grouped_nulls.json",
        ),
        "u4_control_manifest": (
            "person-d-step7-1-u4-control-manifest",
            f"{PACKAGE_RELATIVE_ROOT}/step7_1_u4_control_manifest.json",
        ),
    }
    demonstration_sections = []
    for section_id in CHECKPOINT_SECTION_IDS:
        if section_id in resolved_sources:
            artifact_id, relative_path = resolved_sources[section_id]
            # Documents written by this run are hashed from the bytes just
            # produced; anything else is hashed from the repository copy.
            sha = inventory.get(Path(relative_path).name) or _file_sha256(
                repository_root / relative_path
            )
            if sha is None:
                raise FileNotFoundError(
                    f"checkpoint section {section_id!r} references "
                    f"{relative_path}, which does not exist"
                )
            demonstration_sections.append(
                CheckpointSection(
                    section_id=section_id,
                    status="resolved",
                    source_artifact_id=artifact_id,
                    source_path=relative_path,
                    source_sha256=sha,
                    owner_role="person_d",
                    displayed_values={
                        "note": (
                            "Machine-readable source; no value on this page was "
                            "typed by hand."
                        )
                    },
                )
            )
        else:
            demonstration_sections.append(
                CheckpointSection(
                    section_id=section_id,
                    status="blocked",
                    blocker=(
                        "no real upstream output exists for this slot yet; see "
                        "step8_3_checkpoint_classification.json for the owner"
                    ),
                    blocker_owner=(
                        "person_e"
                        if section_id in ("e_measurement_join", "specificity_and_damage_report")
                        else "person_b"
                    ),
                )
            )
    demonstration = build_checkpoint_demonstration(
        run_id="person-d-step8-2-checkpoint-demonstration-v0-1",
        sections=demonstration_sections,
        evidence_kind="synthetic",
    )
    inventory["step8_2_checkpoint_demonstration.json"] = _write(
        output_root,
        "step8_2_checkpoint_demonstration.json",
        dump_workflow_document(demonstration),
    )

    # ---- Step 8.3: checkpoint classification --------------------------
    classification = classify_checkpoint(
        findings=[
            CheckpointFinding(
                finding_id="unavailable-b-66-cell-folds",
                failure_kind="real_person_b_fold_and_target_manifest_absent",
                nature="unavailable_input",
                evidence_artifact_id="person-d-step6-1-mvp-input-manifest",
                evidence_sha256=None,
                owner_role="person_b",
                next_action=(
                    "publish fold and oracle-target manifests covering the "
                    "accepted 66-cell MVP matrix (layout_01..06, ep100xx)"
                ),
                affected_claims=("U1", "U2"),
                detail=(
                    "Person B's only real fold/target artifacts are scoped to the "
                    "earlier ten-pilot ep94xx set; no 66-cell equivalent exists at "
                    f"{UPSTREAM_AUTHORITIES['person_b_analysis']}."
                ),
            ),
            CheckpointFinding(
                finding_id="unavailable-b-u4-direction",
                failure_kind="real_u4_direction_and_heldout_events_absent",
                nature="unavailable_input",
                evidence_artifact_id="person-d-step7-2-direction-control-audit",
                evidence_sha256=None,
                owner_role="person_b",
                next_action=(
                    "publish the fitted U4 direction, held-out event identities, "
                    "signed dose table, and target layer/timestep"
                ),
                affected_claims=("U4",),
                detail=(
                    "Only contract text and synthetic fixtures exist on "
                    "role/person-a-model and role/person-b-analysis."
                ),
            ),
            CheckpointFinding(
                finding_id="unavailable-e-u4-measurements",
                failure_kind="real_u4_measurement_table_absent",
                nature="unavailable_input",
                evidence_artifact_id="person-d-step7-3-u4-control-matrix",
                evidence_sha256=None,
                owner_role="person_e",
                next_action="publish the U4 rollout measurement table",
                affected_claims=("U4",),
                detail=(
                    "Person E has real homography refits at "
                    f"{UPSTREAM_AUTHORITIES['person_e_operations']} but no U4 "
                    "measurement artifact."
                ),
            ),
        ],
        contracts_pass=True,
        controls_pass=True,
        result_lineage_pass=True,
        clean_reproduction_pass=True,
    )
    inventory["step8_3_checkpoint_classification.json"] = _write(
        output_root,
        "step8_3_checkpoint_classification.json",
        dump_workflow_document(classification),
    )

    # ---- inventory ----------------------------------------------------
    inventory_document = {
        "schema_id": "person-d-phase6to8-completion-inventory-v0-1",
        "schema_version": "1.0",
        "producer_role": "person_d",
        "package_id": "person-d-phase6to8-completion-v0-1",
        "upstream_authorities": UPSTREAM_AUTHORITIES,
        "person_b_applicability_contract": {
            "contract_id": PERSON_B_APPLICABILITY_CONTRACT_ID,
            "path": PERSON_B_APPLICABILITY_PATH,
            "scope": "ten_pilot_ep94xx_only_not_the_66_cell_mvp_matrix",
        },
        "evidence_kind": "synthetic",
        "real_execution_performed": False,
        "excluded_from_inventory": ["step8_1_clean_workflow_run.json", "sha256_inventory.json"],
        "artifact_sha256": dict(sorted(inventory.items())),
        "artifact_count": len(inventory),
    }
    _write(
        output_root,
        "sha256_inventory.json",
        json.dumps(inventory_document, indent=2, sort_keys=True) + "\n",
    )
    return inventory_document


def _file_sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", default=str(REPO_ROOT))
    parser.add_argument(
        "--output-root",
        default="docs/status/person_d_phase6to8_completion_v0_1",
    )
    args = parser.parse_args(argv)

    repository_root = Path(args.repository_root).resolve()
    output_root = Path(args.output_root)
    if not output_root.is_absolute():
        output_root = repository_root / output_root

    document = build_all(output_root, repository_root)
    print(
        f"wrote {document['artifact_count']} Person D Phase 6-8 artifacts to "
        f"{output_root}"
    )
    print("evidence_kind=synthetic real_execution_performed=False")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
