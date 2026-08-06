"""Tests for the consolidated Step 4.5 missingness and exclusion audit.

The audit's whole purpose is to make a silent exclusion impossible, so
these tests are written mostly as "the audit must refuse to call this
clean": a method that quietly produces no rows, a non-applicable row with
no reason, a duplicated or orphan emitted row, an unexplained divergence
from Person B's planned counts, and an invalid/superseded run that tries
to present itself as a current result.

No real capture, fold, or oracle-target data is read anywhere here.
"""

from __future__ import annotations

import json

import pytest

from mineocclude.baselines.interface import TrajectoryContext, make_baseline_row
from mineocclude.baselines.missingness_audit_v0_1 import (
    SCHEMA_ID,
    MissingnessAuditError,
    PlannedFamilyTarget,
    RequestedRow,
    TrajectoryCondition,
    build_missingness_exclusion_report,
    comparison_class_for,
    dump_missingness_exclusion_report,
    duration_bin,
    requested_rows_from_contexts,
    validate_missingness_exclusion_report,
)

FAMILIES = ("last_seen", "grouped_shuffled")


def _context(trajectory_id, layout_id, frame_idx, fold, duration=0.8):
    return TrajectoryContext(
        trajectory_id=trajectory_id,
        layout_id=layout_id,
        model_frame_idx=frame_idx,
        fold=fold,
        regime="A",
        tau_seconds=0.05 * frame_idx,
        visibility=frame_idx < 1,
        last_seen_position_blocks=float(frame_idx),
        last_seen_velocity_blocks_per_s=1.0,
        v_scripted_blocks_per_s=None,
        q_scripted_blocks2_per_s=None,
        duration_seconds=duration,
        config_hash="cfg-test",
        seed=7,
    )


def _fixture_contexts():
    return [
        _context("layout_01_ep10001", "layout_01", frame_idx, fold=0)
        for frame_idx in range(3)
    ] + [
        _context("layout_02_ep10002", "layout_02", frame_idx, fold=1, duration=0.2)
        for frame_idx in range(2)
    ]


def _conditions():
    return [
        TrajectoryCondition(
            trajectory_id="layout_01_ep10001",
            layout_id="layout_01",
            condition_role="core",
            acceptance_status="accepted",
        ),
        TrajectoryCondition(
            trajectory_id="layout_02_ep10002",
            layout_id="layout_02",
            condition_role="nowall",
            acceptance_status="accepted",
        ),
    ]


def _rows_for(contexts, families=FAMILIES, *, applicable_targets=("mu_oracle_blocks",)):
    """Emit one row per (family, target, context), NA outside the given targets."""

    rows = []
    for family in families:
        for ctx in contexts:
            for target in ("mu_oracle_blocks", "log_sigma_oracle"):
                applicable = target in applicable_targets
                rows.append(
                    make_baseline_row(
                        ctx,
                        baseline_name=family,
                        target_name=target,
                        prediction=1.5 if applicable else None,
                        applicable=applicable,
                        fit_metadata=(
                            {} if applicable else {"reason": f"{family} defines no {target}"}
                        ),
                    )
                )
    return rows


def _build(**overrides):
    contexts = overrides.pop("contexts", None) or _fixture_contexts()
    rows = overrides.pop("rows", None)
    if rows is None:
        rows = _rows_for(contexts)
    kwargs = {
        "rows": rows,
        "requested_rows": requested_rows_from_contexts(contexts),
        "conditions": _conditions(),
        "families": FAMILIES,
        "run_id": "person-d-step4-5-synthetic-v0-1",
    }
    kwargs.update(overrides)
    return build_missingness_exclusion_report(**kwargs)


# --------------------------------------------------------------------------
# Happy path: complete coverage across every required dimension
# --------------------------------------------------------------------------


def test_clean_report_passes_and_validates():
    document = _build()
    validate_missingness_exclusion_report(document)
    assert document["audit_passed"] is True
    assert document["schema_id"] == SCHEMA_ID
    assert document["totals"]["missing_predictions"] == 0


def test_report_covers_every_required_dimension():
    document = _build()
    required_dimensions = {
        "baseline_name",
        "comparison_class",
        "target_name",
        "layout_id",
        "condition_role",
        "acceptance_status",
        "duration_bin",
        "fold",
    }
    assert document["cells"]
    for cell in document["cells"]:
        assert required_dimensions <= set(cell)
    assert {cell["layout_id"] for cell in document["cells"]} == {"layout_01", "layout_02"}
    assert {cell["fold"] for cell in document["cells"]} == {0, 1}
    assert {cell["condition_role"] for cell in document["cells"]} == {"core", "nowall"}
    assert {cell["duration_bin"] for cell in document["cells"]} == {"0.8s", "0.2s"}
    assert {cell["target_name"] for cell in document["cells"]} == {
        "mu_oracle_blocks",
        "log_sigma_oracle",
    }


def test_statuses_partition_the_requested_row_set():
    document = _build()
    totals = document["totals"]
    assert (
        totals["available_predictions"]
        + totals["non_applicable_predictions"]
        + totals["missing_predictions"]
        == totals["requested_predictions"]
    )
    # 2 families x 2 targets x 5 requested rows.
    assert totals["requested_predictions"] == 20


def test_na_is_recorded_as_null_never_zero():
    document = _build()
    na_cells = [cell for cell in document["cells"] if cell["non_applicable_count"]]
    assert na_cells
    text = json.dumps(document, default=list)
    assert '"prediction": 0' not in text
    assert document["invariants"]["na_is_never_zero"] is True


def test_output_is_deterministic_across_repeated_builds():
    first = dump_missingness_exclusion_report(_build())
    second = dump_missingness_exclusion_report(_build())
    assert first == second


def test_output_is_unchanged_by_reordered_input_rows():
    contexts = _fixture_contexts()
    rows = _rows_for(contexts)
    forward = dump_missingness_exclusion_report(_build(contexts=contexts, rows=rows))
    backward = dump_missingness_exclusion_report(
        _build(contexts=contexts, rows=list(reversed(rows)))
    )
    assert forward == backward


# --------------------------------------------------------------------------
# Silent method-specific population
# --------------------------------------------------------------------------


def test_a_family_that_emits_nothing_is_reported_as_missing_not_absent():
    contexts = _fixture_contexts()
    rows = _rows_for(contexts, families=("last_seen",))
    document = _build(contexts=contexts, rows=rows)

    assert document["audit_passed"] is False
    assert document["invariants"]["no_silent_method_specific_population"] is False
    shuffled = [
        entry
        for entry in document["reconciliation"]
        if entry["baseline_name"] == "grouped_shuffled"
    ]
    assert shuffled
    for entry in shuffled:
        assert entry["missing_count"] == 5
        assert entry["emitted_count"] == 0
        assert entry["reconciled"] is False
        assert entry["row_set_differences"]
    validate_missingness_exclusion_report(document)


def test_a_family_missing_only_one_target_is_still_flagged():
    contexts = _fixture_contexts()
    rows = [
        row
        for row in _rows_for(contexts)
        if not (row.baseline_name == "grouped_shuffled" and row.target_name == "log_sigma_oracle")
    ]
    document = _build(contexts=contexts, rows=rows)
    entry = next(
        e
        for e in document["reconciliation"]
        if e["baseline_name"] == "grouped_shuffled"
        and e["target_name"] == "log_sigma_oracle"
    )
    assert entry["missing_count"] == 5
    assert document["audit_passed"] is False


def test_an_undeclared_family_cannot_enter_the_population():
    contexts = _fixture_contexts()
    rows = _rows_for(contexts, families=FAMILIES + ("smuggled_method",))
    with pytest.raises(MissingnessAuditError, match="does not declare"):
        _build(contexts=contexts, rows=rows)


def test_a_family_without_a_declared_comparison_class_is_rejected():
    with pytest.raises(MissingnessAuditError, match="no declared comparison class"):
        comparison_class_for("some_new_method")


# --------------------------------------------------------------------------
# Reason codes
# --------------------------------------------------------------------------


def test_non_applicable_row_without_a_reason_is_flagged():
    contexts = _fixture_contexts()
    rows = []
    for ctx in contexts:
        for family in FAMILIES:
            rows.append(
                make_baseline_row(
                    ctx,
                    baseline_name=family,
                    target_name="mu_oracle_blocks",
                    prediction=1.0,
                    applicable=True,
                )
            )
            rows.append(
                make_baseline_row(
                    ctx,
                    baseline_name=family,
                    target_name="log_sigma_oracle",
                    prediction=None,
                    applicable=False,
                    fit_metadata={},  # no reason at all
                )
            )
    document = _build(contexts=contexts, rows=rows)
    assert document["rows_missing_reason_code"]
    assert document["invariants"]["every_missing_prediction_has_one_reason"] is False
    assert document["audit_passed"] is False


def test_blank_reason_text_counts_as_no_reason():
    contexts = _fixture_contexts()[:1]
    rows = [
        make_baseline_row(
            contexts[0],
            baseline_name="last_seen",
            target_name=target,
            prediction=None,
            applicable=False,
            fit_metadata={"reason": "   "},
        )
        for target in ("mu_oracle_blocks", "log_sigma_oracle")
    ]
    document = _build(
        contexts=contexts,
        rows=rows,
        families=("last_seen",),
        requested_rows=requested_rows_from_contexts(contexts),
    )
    assert document["rows_missing_reason_code"]


def test_reason_counts_are_tabulated_per_family_and_target():
    document = _build()
    reasons = document["non_applicable_reason_counts"]
    assert reasons
    for entry in reasons:
        assert entry["count"] > 0
        assert entry["reason"]
        assert entry["baseline_name"] in FAMILIES


# --------------------------------------------------------------------------
# Row-set integrity
# --------------------------------------------------------------------------


def test_orphan_emitted_row_is_reported():
    contexts = _fixture_contexts()
    stranger = _context("layout_09_ep19999", "layout_09", 0, fold=4)
    rows = _rows_for(contexts) + [
        make_baseline_row(
            stranger,
            baseline_name="last_seen",
            target_name="mu_oracle_blocks",
            prediction=3.0,
            applicable=True,
        )
    ]
    document = _build(contexts=contexts, rows=rows)
    assert document["orphan_emitted_rows"]
    assert document["invariants"]["no_orphan_emitted_rows"] is False
    assert document["audit_passed"] is False


def test_duplicate_emitted_row_is_reported():
    contexts = _fixture_contexts()
    rows = _rows_for(contexts)
    document = _build(contexts=contexts, rows=rows + [rows[0]])
    assert document["duplicate_emitted_rows"]
    assert document["invariants"]["no_duplicate_emitted_rows"] is False


def test_duplicate_requested_row_identity_is_rejected():
    requested = [
        RequestedRow("t", 0, 0, "layout_01", 0.5),
        RequestedRow("t", 0, 0, "layout_01", 0.5),
    ]
    with pytest.raises(MissingnessAuditError, match="duplicate requested row identity"):
        build_missingness_exclusion_report(
            rows=[],
            requested_rows=requested,
            conditions=[
                TrajectoryCondition("t", "layout_01", "core", "accepted"),
            ],
            families=("last_seen",),
            run_id="r",
        )


def test_a_requested_trajectory_without_a_condition_is_rejected():
    contexts = _fixture_contexts()
    with pytest.raises(MissingnessAuditError, match="no declared condition"):
        _build(contexts=contexts, conditions=_conditions()[:1])


# --------------------------------------------------------------------------
# Planned versus requested versus emitted
# --------------------------------------------------------------------------


def test_planned_counts_are_reconciled_three_ways():
    plan = [
        PlannedFamilyTarget(
            family="last_seen",
            target_name="mu_oracle_blocks",
            planned_available_count=5,
            planned_non_applicable_count=0,
            source_contract_id="person-b-step4-1-family-target-applicability-v0.1",
        )
    ]
    document = _build(planned=plan)
    entry = next(
        e
        for e in document["reconciliation"]
        if e["baseline_name"] == "last_seen" and e["target_name"] == "mu_oracle_blocks"
    )
    assert entry["planned_available_count"] == 5
    assert entry["requested_count"] == 5
    assert entry["emitted_count"] == 5
    assert entry["reconciled"] is True


def test_divergence_from_the_planned_count_is_explained_not_hidden():
    plan = [
        PlannedFamilyTarget(
            family="last_seen",
            target_name="mu_oracle_blocks",
            planned_available_count=99,  # B expected far more than arrived
            planned_non_applicable_count=0,
            source_contract_id="person-b-step4-1-family-target-applicability-v0.1",
        )
    ]
    document = _build(planned=plan)
    entry = next(
        e
        for e in document["reconciliation"]
        if e["baseline_name"] == "last_seen" and e["target_name"] == "mu_oracle_blocks"
    )
    assert entry["reconciled"] is False
    assert any("planned" in difference for difference in entry["row_set_differences"])
    validate_missingness_exclusion_report(document)


# --------------------------------------------------------------------------
# Acceptance status, exclusions, and run validity
# --------------------------------------------------------------------------


def test_excluded_trajectory_must_carry_a_reason():
    with pytest.raises(MissingnessAuditError, match="no exclusion_reason"):
        TrajectoryCondition(
            trajectory_id="layout_03_ep10003",
            layout_id="layout_03",
            condition_role="core",
            acceptance_status="excluded",
        )


def test_excluded_and_pending_trajectories_are_listed_separately_from_accepted():
    conditions = [
        TrajectoryCondition(
            "layout_01_ep10001", "layout_01", "core", "excluded", "detector_gate_failed"
        ),
        TrajectoryCondition(
            "layout_02_ep10002", "layout_02", "nowall", "recollection_pending"
        ),
    ]
    document = _build(conditions=conditions)
    listed = {entry["trajectory_id"] for entry in document["excluded_trajectories"]}
    assert listed == {"layout_01_ep10001", "layout_02_ep10002"}
    assert document["trajectory_acceptance_counts"] == {
        "excluded": 1,
        "recollection_pending": 1,
    }


def test_unknown_condition_role_is_rejected():
    with pytest.raises(MissingnessAuditError, match="unknown condition_role"):
        TrajectoryCondition("t", "layout_01", "invented_role", "accepted")


def test_superseded_run_is_retained_in_history_but_not_current():
    history = [{"run_id": "older", "run_status": "superseded", "superseded_by": "newer"}]
    document = _build(run_status="superseded", run_history=history)
    assert document["contributes_to_current_results"] is False
    assert document["run_history"][0]["run_id"] == "older"
    validate_missingness_exclusion_report(document)


def test_invalid_run_cannot_claim_to_be_a_current_result():
    document = _build(run_status="invalid")
    assert document["contributes_to_current_results"] is False
    tampered = dict(document)
    tampered["contributes_to_current_results"] = True
    with pytest.raises(MissingnessAuditError, match="only a valid run"):
        validate_missingness_exclusion_report(tampered)


def test_unknown_run_status_is_rejected():
    with pytest.raises(MissingnessAuditError, match="unknown run_status"):
        _build(run_status="probably_fine")


def test_synthetic_evidence_is_labeled_and_never_implicitly_real():
    document = _build()
    assert document["evidence_kind"] == "synthetic"
    real = _build(evidence_kind="real")
    assert real["evidence_kind"] == "real"
    with pytest.raises(MissingnessAuditError, match="unknown evidence_kind"):
        _build(evidence_kind="probably_real")


# --------------------------------------------------------------------------
# Validator independence
# --------------------------------------------------------------------------


def test_validator_rejects_a_broken_partition():
    document = _build()
    tampered = json.loads(json.dumps(document, default=list))
    tampered["totals"]["available_predictions"] += 1
    with pytest.raises(MissingnessAuditError, match="must partition"):
        validate_missingness_exclusion_report(tampered)


def test_validator_rejects_a_relabeled_comparison_class():
    document = _build()
    tampered = json.loads(json.dumps(document, default=list))
    tampered["cells"][0]["comparison_class"] = "fair_baseline"
    with pytest.raises(MissingnessAuditError, match="not its frozen class"):
        validate_missingness_exclusion_report(tampered)


def test_validator_rejects_a_wrong_schema_id():
    document = _build()
    tampered = dict(document)
    tampered["schema_id"] = "something-else"
    with pytest.raises(MissingnessAuditError, match="expected schema_id"):
        validate_missingness_exclusion_report(tampered)


def test_duration_bin_is_value_based_not_threshold_based():
    assert duration_bin(None) == "unknown"
    assert duration_bin(0.2) == "0.2s"
    assert duration_bin(0.8) == "0.8s"
    assert duration_bin(1.2) == "1.2s"
