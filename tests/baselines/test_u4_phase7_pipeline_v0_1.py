"""Tests for Phase 7 Steps 7.2-7.5.

7.2 audits Person B/A direction-construction evidence without ever
reconstructing the direction. 7.3 joins Person E's measurements onto the
frozen manifest fail-closed. 7.4 reports specificity and damage without
Person D authoring a causal threshold. 7.5 keeps control failures
visible, appending rather than editing.

Every fixture is synthetic; no real direction, rollout, or measurement is
read anywhere in this file.
"""

from __future__ import annotations

import json

import pytest

from mineocclude.baselines.control_failure_record_v0_1 import (
    DISPOSITIONS,
    ControlFailureEntry,
    ControlFailureError,
    add_control_failure,
    build_control_failure_record,
    compute_record_checksum,
    dump_control_failure_record,
    validate_control_failure_record,
)
from mineocclude.baselines.direction_control_audit_v0_1 import (
    REQUIRED_EVIDENCE_FIELDS,
    AuditFinding,
    DirectionAuditError,
    audit_direction_construction,
    build_direction_control_audit,
    dump_direction_control_audit,
    validate_direction_control_audit,
)
from mineocclude.baselines.specificity_damage_report_v0_1 import (
    REQUIRED_SECTION_IDS as DAMAGE_SECTION_IDS,
    DamageSection,
    SectionBlocker,
    SpecificityReportError,
    blocked_damage_section,
    build_specificity_damage_report,
    dump_specificity_damage_report,
    summarize_control_matrix,
    validate_specificity_damage_report,
)
from mineocclude.baselines.u4_control_manifest_v0_1 import (
    DirectionRef,
    DoseSpec,
    HeldOutEvent,
    build_control_manifest,
    build_control_manifest_rows,
    freeze_control_manifest,
)
from mineocclude.baselines.u4_measurement_join_v0_1 import (
    MeasurementJoinError,
    MeasurementRow,
    dump_u4_control_matrix,
    join_measurements_to_manifest,
    validate_u4_control_matrix,
)

SHA = "d" * 64

# --------------------------------------------------------------------------
# Step 7.2 -- direction-control construction audit
# --------------------------------------------------------------------------


def _evidence(**overrides):
    base = {
        "direction_id": "u4_primary",
        "direction_version": "v1",
        "direction_hash": SHA,
        "space": "raw_activation",
        "dimension": 2048,
        "seed": 20260720,
        "residual_norm_before_normalization": 3.5,
        "near_zero_threshold": 1e-6,
        "pre_projection_norm": 3.5,
        "post_projection_norm": 1.0,
        "standardized_during_fit": False,
        "inverse_transformed_before_export": False,
        "raw_space_equivalence_verified": True,
        "max_relative_activation_norm": 0.25,
        "typical_activation_norm": 20.0,
        "target_layer_idx": 12,
        "target_timestep_idx": 7,
        "hook_site": "decoder_layer_output_residual_stream",
        "held_out_partition_id": "heldout_v1",
        "used_test_data_to_select_direction": False,
        "used_heldout_outcomes_to_select_direction": False,
        "supersession_status": "current",
    }
    base.update(overrides)
    return base


def test_absent_direction_evidence_is_blocked_never_passed():
    findings = audit_direction_construction(None)
    assert len(findings) == 1
    assert findings[0].result == "blocked"

    document = build_direction_control_audit(
        audit_id="synthetic-audit",
        findings=findings,
        evidence_source={"note": "no real Person B direction artifact exists"},
    )
    validate_direction_control_audit(document)
    assert document["decision"] == "BLOCKED"


def test_complete_evidence_with_vectors_passes():
    findings = audit_direction_construction(
        _evidence(),
        real_direction_values=[1.0, 0.0, 0.0],
        control_direction_values=[0.0, 1.0, 0.0],
    )
    document = build_direction_control_audit(
        audit_id="synthetic-audit",
        findings=findings,
        evidence_source={"origin": "synthetic fixture"},
    )
    validate_direction_control_audit(document)
    assert document["decision"] == "PASS"


def test_missing_metadata_fails_rather_than_skipping_the_check():
    for field in ("seed", "post_projection_norm", "held_out_partition_id"):
        evidence = _evidence()
        del evidence[field]
        findings = audit_direction_construction(evidence)
        assert findings[0].check_name == "required_metadata_complete"
        assert findings[0].result == "fail"
        assert field in findings[0].detail


def test_every_required_evidence_field_is_checked_for_presence():
    evidence = _evidence()
    assert set(REQUIRED_EVIDENCE_FIELDS) <= set(evidence)


def test_standardized_direction_without_inverse_transform_fails():
    findings = audit_direction_construction(
        _evidence(standardized_during_fit=True, inverse_transformed_before_export=False)
    )
    failed = {f.check_name for f in findings if f.result == "fail"}
    assert "standardized_fit_was_inverse_transformed" in failed


def test_near_zero_residual_fails():
    findings = audit_direction_construction(
        _evidence(residual_norm_before_normalization=1e-9, near_zero_threshold=1e-6)
    )
    failed = {f.check_name for f in findings if f.result == "fail"}
    assert "residual_above_near_zero_threshold" in failed


def test_test_selected_direction_fails():
    findings = audit_direction_construction(
        _evidence(used_test_data_to_select_direction=True)
    )
    failed = {f.check_name for f in findings if f.result == "fail"}
    assert "direction_not_selected_by_test_or_heldout_outcomes" in failed


def test_non_unit_post_projection_norm_fails():
    findings = audit_direction_construction(_evidence(post_projection_norm=1.4))
    failed = {f.check_name for f in findings if f.result == "fail"}
    assert "post_projection_norm_is_unit" in failed


def test_non_orthogonal_control_direction_fails():
    findings = audit_direction_construction(
        _evidence(),
        real_direction_values=[1.0, 0.0],
        control_direction_values=[1.0, 0.0],
    )
    failed = {f.check_name for f in findings if f.result == "fail"}
    assert "control_direction_orthogonal_to_real" in failed


def test_norm_mismatched_control_direction_fails():
    findings = audit_direction_construction(
        _evidence(),
        real_direction_values=[1.0, 0.0],
        control_direction_values=[0.0, 5.0],
    )
    failed = {f.check_name for f in findings if f.result == "fail"}
    assert "control_direction_norm_matched" in failed


def test_a_blocked_check_can_never_be_reported_as_a_pass():
    findings = [
        AuditFinding("a", "pass", "fine"),
        AuditFinding("b", "blocked", "no artifact yet"),
    ]
    document = dict(
        build_direction_control_audit(
            audit_id="x", findings=findings, evidence_source={"k": "v"}
        )
    )
    assert document["decision"] == "BLOCKED"
    document["decision"] = "PASS"
    with pytest.raises(DirectionAuditError, match="never be reported as a pass"):
        validate_direction_control_audit(document)


def test_audit_document_is_deterministic():
    findings = audit_direction_construction(_evidence())
    kwargs = dict(audit_id="x", findings=findings, evidence_source={"k": "v"})
    assert dump_direction_control_audit(
        build_direction_control_audit(**kwargs)
    ) == dump_direction_control_audit(build_direction_control_audit(**kwargs))


def test_a_finding_without_detail_is_rejected():
    with pytest.raises(DirectionAuditError, match="records no detail"):
        AuditFinding("check", "pass", "")


# --------------------------------------------------------------------------
# Step 7.3 -- fail-closed measurement join
# --------------------------------------------------------------------------


def _frozen_manifest():
    kwargs = dict(
        held_out_events=(HeldOutEvent("e1", "traj-1", "layout_01"),),
        rollout_seeds=(11,),
        doses=(DoseSpec("pos_1", 4.0, 4.0, False),),
        primary_direction=DirectionRef("u4_primary", "v1", SHA),
        random_directions=(DirectionRef("rand_a", "v1", "e" * 64, seed=101),),
        orthogonal_directions=(DirectionRef("orth_a", "v1", "f" * 64, seed=202),),
        target_layer_idx=12,
        target_timestep_idx=7,
        wrong_layer_idx=3,
        wrong_timestep_idx=1,
    )
    rows = build_control_manifest_rows(**kwargs)
    document = build_control_manifest(
        manifest_id="synthetic-manifest",
        manifest_version="0.1.0",
        rows=rows,
        source_authorities={"origin": "synthetic"},
        **kwargs,
    )
    return freeze_control_manifest(document)


def _measurement(row, outcome="measured", **overrides):
    values = {
        "clip_id": row["clip_id"],
        "outcome": outcome,
        "event_id": row["event_id"],
        "rollout_seed": row["rollout_seed"],
        "dose_id": row["dose_id"],
        "control_type": row["control_type"],
        "target_layer_idx": row["target_layer_idx"],
        "target_timestep_idx": row["target_timestep_idx"],
        "direction_id": row["direction_id"],
        "pair_key": row["pair_key"],
        "detector_version": "detector-v0.4",
        "homography_version": "homography-v0.4",
        "ssim_version": "ssim-v0.1",
        "displacement_blocks": 0.35,
        "masked_ssim": 0.94,
    }
    values.update(overrides)
    return MeasurementRow(**values)


def _all_measured(manifest):
    return [_measurement(row) for row in manifest["rows"]]


def test_complete_join_covers_every_planned_clip():
    manifest = _frozen_manifest()
    matrix = join_measurements_to_manifest(
        manifest=manifest,
        measurements=_all_measured(manifest),
        run_id="synthetic-join",
    )
    validate_u4_control_matrix(matrix)
    assert matrix["join_complete"] is True
    assert matrix["planned_clip_count"] == len(manifest["rows"])
    assert matrix["outcome_counts"]["measured"] == len(manifest["rows"])


def test_an_unreported_clip_becomes_missing_with_a_reason_not_an_absence():
    manifest = _frozen_manifest()
    measurements = _all_measured(manifest)[:-1]
    matrix = join_measurements_to_manifest(
        manifest=manifest, measurements=measurements, run_id="synthetic-join"
    )
    validate_u4_control_matrix(matrix)
    assert matrix["join_complete"] is False
    assert matrix["outcome_counts"]["missing"] == 1
    assert matrix["planned_clip_count"] == len(manifest["rows"])
    missing_row = next(row for row in matrix["rows"] if row["outcome"] == "missing")
    assert missing_row["missing_reason"]
    assert missing_row["displacement_blocks"] is None


def test_a_measurement_for_an_unplanned_clip_is_rejected():
    manifest = _frozen_manifest()
    stray = _measurement(manifest["rows"][0], clip_id="never_planned")
    with pytest.raises(MeasurementJoinError, match="not in the frozen manifest"):
        join_measurements_to_manifest(
            manifest=manifest,
            measurements=_all_measured(manifest) + [stray],
            run_id="synthetic-join",
        )


def test_duplicate_measurement_rows_are_rejected():
    manifest = _frozen_manifest()
    measurements = _all_measured(manifest)
    with pytest.raises(MeasurementJoinError, match="more than one measurement row"):
        join_measurements_to_manifest(
            manifest=manifest,
            measurements=measurements + [measurements[0]],
            run_id="synthetic-join",
        )


def test_identity_conflict_between_manifest_and_measurement_is_reported():
    manifest = _frozen_manifest()
    measurements = _all_measured(manifest)
    measurements[0] = _measurement(manifest["rows"][0], target_layer_idx=19)
    matrix = join_measurements_to_manifest(
        manifest=manifest, measurements=measurements, run_id="synthetic-join"
    )
    assert matrix["identity_conflicts"]
    assert matrix["join_complete"] is False
    validate_u4_control_matrix(matrix)


def test_inconsistent_detector_version_is_reported():
    manifest = _frozen_manifest()
    measurements = _all_measured(manifest)
    measurements[0] = _measurement(manifest["rows"][0], detector_version="detector-v0.3")
    matrix = join_measurements_to_manifest(
        manifest=manifest, measurements=measurements, run_id="synthetic-join"
    )
    detector = next(
        f for f in matrix["version_findings"] if f["field"] == "detector_version"
    )
    assert detector["consistent_across_rows"] is False
    assert matrix["join_complete"] is False


def test_an_unexpected_version_value_is_reported():
    manifest = _frozen_manifest()
    matrix = join_measurements_to_manifest(
        manifest=manifest,
        measurements=_all_measured(manifest),
        expected_ssim_version="ssim-v0.2",
        run_id="synthetic-join",
    )
    ssim = next(f for f in matrix["version_findings"] if f["field"] == "ssim_version")
    assert ssim["matches_expected"] is False
    assert matrix["join_complete"] is False


def test_non_persistent_and_failed_clips_keep_null_measurements():
    manifest = _frozen_manifest()
    measurements = []
    for index, row in enumerate(manifest["rows"]):
        if index == 1:
            measurements.append(
                _measurement(
                    row,
                    outcome="non_persistent",
                    displacement_blocks=None,
                    masked_ssim=None,
                    missing_reason="no primary reappearance after reveal",
                )
            )
        elif index == 2:
            measurements.append(
                _measurement(
                    row,
                    outcome="generation_failed",
                    displacement_blocks=None,
                    masked_ssim=None,
                    missing_reason="rollout generation crashed",
                )
            )
        else:
            measurements.append(_measurement(row))
    matrix = join_measurements_to_manifest(
        manifest=manifest, measurements=measurements, run_id="synthetic-join"
    )
    validate_u4_control_matrix(matrix)
    assert matrix["outcome_counts"]["non_persistent"] == 1
    assert matrix["outcome_counts"]["generation_failed"] == 1
    for row in matrix["rows"]:
        if row["outcome"] != "measured":
            assert row["displacement_blocks"] is None
            assert row["missing_reason"]


def test_an_unmeasured_clip_carrying_numbers_is_rejected_at_construction():
    manifest = _frozen_manifest()
    with pytest.raises(MeasurementJoinError, match="never zero"):
        _measurement(
            manifest["rows"][0],
            outcome="non_persistent",
            displacement_blocks=0.0,
            missing_reason="no reappearance",
        )


def test_an_unmeasured_clip_without_a_reason_is_rejected():
    manifest = _frozen_manifest()
    with pytest.raises(MeasurementJoinError, match="without a recorded reason"):
        _measurement(
            manifest["rows"][0],
            outcome="excluded",
            displacement_blocks=None,
            masked_ssim=None,
        )


def test_a_pushed_clip_without_a_measured_baseline_is_reported():
    manifest = _frozen_manifest()
    measurements = []
    for row in manifest["rows"]:
        if row["control_type"] == "alpha_zero":
            measurements.append(
                _measurement(
                    row,
                    outcome="generation_failed",
                    displacement_blocks=None,
                    masked_ssim=None,
                    missing_reason="baseline rollout failed",
                )
            )
        else:
            measurements.append(_measurement(row))
    matrix = join_measurements_to_manifest(
        manifest=manifest, measurements=measurements, run_id="synthetic-join"
    )
    assert matrix["pair_keys_without_measured_baseline"]
    assert matrix["join_complete"] is False
    validate_u4_control_matrix(matrix)


def test_join_is_deterministic():
    manifest = _frozen_manifest()
    measurements = _all_measured(manifest)
    kwargs = dict(manifest=manifest, measurements=measurements, run_id="synthetic-join")
    assert dump_u4_control_matrix(
        join_measurements_to_manifest(**kwargs)
    ) == dump_u4_control_matrix(join_measurements_to_manifest(**kwargs))


def test_validator_rejects_a_matrix_claiming_completeness_with_missing_rows():
    manifest = _frozen_manifest()
    matrix = join_measurements_to_manifest(
        manifest=manifest,
        measurements=_all_measured(manifest)[:-1],
        run_id="synthetic-join",
    )
    tampered = json.loads(json.dumps(matrix, default=list))
    tampered["join_complete"] = True
    with pytest.raises(MeasurementJoinError, match="present itself as complete"):
        validate_u4_control_matrix(tampered)


# --------------------------------------------------------------------------
# Step 7.4 -- specificity and damage report
# --------------------------------------------------------------------------


def _damage_blocker():
    return SectionBlocker(
        missing_artifact="person_e_u4_measurement_table",
        expected_owner="person_e",
        expected_schema_or_version="person-b-u4-measurement-input-v0.1",
        exact_command_after_receipt=(
            "python scripts/run_person_d_step7_3_measurement_join.py "
            "--manifest <path> --measurements <path>"
        ),
    )


def _all_blocked_damage_sections():
    return [
        blocked_damage_section(sid, sid.replace("_", " "), [_damage_blocker()])
        for sid in DAMAGE_SECTION_IDS
    ]


def test_fully_blocked_damage_report_is_valid_and_incomplete():
    document = build_specificity_damage_report(
        sections=_all_blocked_damage_sections(),
        run_id="synthetic-damage",
        control_matrix_run_id=None,
        person_b_inferential_run_id=None,
    )
    validate_specificity_damage_report(document)
    assert document["report_complete"] is False
    assert document["blocked_section_count"] == len(DAMAGE_SECTION_IDS)
    assert document["person_d_created_any_causal_threshold"] is False


def test_omitting_a_damage_section_is_rejected():
    with pytest.raises(SpecificityReportError, match="missing required sections"):
        build_specificity_damage_report(
            sections=_all_blocked_damage_sections()[:-1],
            run_id="synthetic-damage",
            control_matrix_run_id=None,
            person_b_inferential_run_id=None,
        )


def test_person_d_cannot_author_a_causal_verdict():
    with pytest.raises(SpecificityReportError, match="only Person B may draw"):
        DamageSection(
            section_id="signed_displacement_pattern",
            title="Signed displacement",
            status="rendered",
            observed={"measured_clip_count": 8},
            verdict="the direction causally shifts the sheep",
            verdict_owner="person_d",
            verdict_source_record_id="person-d-made-this-up",
        )


def test_a_person_b_verdict_must_cite_a_record():
    with pytest.raises(SpecificityReportError, match="no Person B record to cite"):
        DamageSection(
            section_id="signed_displacement_pattern",
            title="Signed displacement",
            status="rendered",
            observed={"measured_clip_count": 8},
            verdict="supported",
            verdict_owner="person_b",
        )


def test_person_d_may_report_descriptive_coverage_without_a_verdict():
    manifest = _frozen_manifest()
    matrix = join_measurements_to_manifest(
        manifest=manifest,
        measurements=_all_measured(manifest),
        run_id="synthetic-join",
    )
    summary = summarize_control_matrix(matrix)
    assert summary["measured_clip_count"] == len(manifest["rows"])
    assert "outcome_counts_by_control_type" in summary

    sections = _all_blocked_damage_sections()
    sections[-2] = DamageSection(
        section_id="missingness_and_non_persistence",
        title="Missingness and non-persistence",
        status="rendered",
        observed=summary,
    )
    document = build_specificity_damage_report(
        sections=sections,
        run_id="synthetic-damage",
        control_matrix_run_id="synthetic-join",
        person_b_inferential_run_id=None,
    )
    validate_specificity_damage_report(document)
    rendered = next(
        s for s in document["sections"] if s["section_id"] == "missingness_and_non_persistence"
    )
    assert rendered["verdict"] is None
    assert rendered["observed"]["measured_clip_count"] == len(manifest["rows"])


def test_a_blocked_damage_section_stays_structurally_empty():
    with pytest.raises(SpecificityReportError, match="structurally empty"):
        DamageSection(
            section_id="wrong_layer_effects",
            title="Wrong layer",
            status="blocked",
            observed={"count": 1},
            blockers=(_damage_blocker(),),
        )


def test_damage_report_is_deterministic():
    kwargs = dict(
        sections=_all_blocked_damage_sections(),
        run_id="synthetic-damage",
        control_matrix_run_id=None,
        person_b_inferential_run_id=None,
    )
    assert dump_specificity_damage_report(
        build_specificity_damage_report(**kwargs)
    ) == dump_specificity_damage_report(build_specificity_damage_report(**kwargs))


# --------------------------------------------------------------------------
# Step 7.5 -- control-failure claim impact
# --------------------------------------------------------------------------


def _entry(entry_id="cf-1", **overrides):
    values = {
        "entry_id": entry_id,
        "control_clip_id": "e1|seed11|random_direction|dosepos_1+rand_a|L12|T7",
        "control_type": "random_direction",
        "failure_kind": "random_direction_shows_comparable_displacement",
        "failure_detail": "the norm-matched random direction moved the sheep as much as the primary",
        "affected_comparison": "primary_signed_dose_vs_random_direction",
        "affected_claim": "the fitted direction is specific to the hidden-state axis",
        "evidence_version": "u4-control-matrix-v0.1",
        "evidence_sha256": SHA,
        "owner_role": "person_d",
        "required_review": "person_b_scientific_methods_owner",
        "review_status": "required",
        "disposition": "plumbing_only",
        "disposition_owner": "person_d",
        "disposition_rationale": "generation config mismatch suspected; not yet a scientific statement",
    }
    values.update(overrides)
    return ControlFailureEntry(**values)


def test_empty_record_validates():
    document = build_control_failure_record(
        record_id="synthetic-failures", record_version="0.1.0"
    )
    validate_control_failure_record(document)
    assert document["entry_count"] == 0


def test_a_failure_entry_is_appended_and_visible():
    document = build_control_failure_record(
        record_id="synthetic-failures", record_version="0.1.0"
    )
    updated = add_control_failure(document, _entry())
    validate_control_failure_record(updated)
    assert updated["entry_count"] == 1
    assert updated["entries"][0]["affected_claim"]
    assert updated["disposition_counts"]["plumbing_only"] == 1


def test_reclassification_supersedes_and_never_removes():
    document = add_control_failure(
        build_control_failure_record(
            record_id="synthetic-failures", record_version="0.1.0"
        ),
        _entry("cf-1"),
    )
    updated = add_control_failure(
        document,
        _entry(
            "cf-2",
            disposition="clean_negative",
            disposition_owner="person_b",
            disposition_rationale="pipeline verified; the effect is genuinely absent",
            reclassifies="cf-1",
            reclassification_reason="generation config was verified correct after review",
        ),
    )
    validate_control_failure_record(updated)

    ids = [entry["entry_id"] for entry in updated["entries"]]
    assert ids == ["cf-1", "cf-2"]  # the original is still there
    original = next(e for e in updated["entries"] if e["entry_id"] == "cf-1")
    assert original["status"] == "reclassified"
    assert original["disposition"] == "plumbing_only"  # unchanged content
    assert updated["active_entry_count"] == 1
    assert updated["disposition_counts"]["clean_negative"] == 1
    assert updated["disposition_counts"]["plumbing_only"] == 0


def test_person_d_cannot_declare_a_clean_negative():
    with pytest.raises(ControlFailureError, match="only Person B may declare"):
        _entry(disposition="clean_negative", disposition_owner="person_d")


def test_person_d_cannot_authorize_causal_interpretation():
    with pytest.raises(ControlFailureError, match="only Person B may declare"):
        _entry(
            disposition="eligible_for_causal_interpretation",
            disposition_owner="person_d",
        )


def test_the_four_dispositions_stay_distinct():
    assert set(DISPOSITIONS) == {
        "plumbing_only",
        "invalid_measurement",
        "clean_negative",
        "eligible_for_causal_interpretation",
    }


def test_a_failure_with_no_stated_impact_is_rejected():
    with pytest.raises(ControlFailureError, match="records no affected_claim"):
        _entry(affected_claim="")


def test_reclassifying_an_unknown_entry_is_rejected():
    document = build_control_failure_record(
        record_id="synthetic-failures", record_version="0.1.0"
    )
    with pytest.raises(ControlFailureError, match="cannot reclassify unknown entry"):
        add_control_failure(
            document,
            _entry("cf-2", reclassifies="never-existed", reclassification_reason="x"),
        )


def test_deleting_an_entry_is_detected_by_the_checksum():
    document = add_control_failure(
        add_control_failure(
            build_control_failure_record(
                record_id="synthetic-failures", record_version="0.1.0"
            ),
            _entry("cf-1"),
        ),
        _entry("cf-2"),
    )
    censored = json.loads(json.dumps(document, default=list))
    censored["entries"] = [
        e for e in censored["entries"] if e["entry_id"] != "cf-2"
    ]  # the exact suppression this record forbids
    assert compute_record_checksum(censored) != censored["record_checksum"]
    with pytest.raises(ControlFailureError, match="does not match the entries"):
        validate_control_failure_record(censored)

    # Even a careful suppression that also patches every tally is caught,
    # because the checksum covers the entries themselves.
    thorough = json.loads(json.dumps(censored, default=list))
    thorough["entry_count"] = len(thorough["entries"])
    thorough["active_entry_count"] = len(thorough["entries"])
    thorough["disposition_counts"]["plumbing_only"] = len(thorough["entries"])
    with pytest.raises(ControlFailureError, match="edited in place"):
        validate_control_failure_record(thorough)


def test_relabelling_an_entry_in_place_is_detected():
    document = add_control_failure(
        build_control_failure_record(
            record_id="synthetic-failures", record_version="0.1.0"
        ),
        _entry("cf-1"),
    )
    relabelled = json.loads(json.dumps(document, default=list))
    relabelled["entries"][0]["disposition"] = "invalid_measurement"
    # Patch the tallies too, so the checksum is the check that fires.
    relabelled["disposition_counts"]["plumbing_only"] = 0
    relabelled["disposition_counts"]["invalid_measurement"] = 1
    with pytest.raises(ControlFailureError, match="edited in place"):
        validate_control_failure_record(relabelled)


def test_record_is_deterministic():
    def build():
        return add_control_failure(
            build_control_failure_record(
                record_id="synthetic-failures", record_version="0.1.0"
            ),
            _entry(),
        )

    assert dump_control_failure_record(build()) == dump_control_failure_record(build())
