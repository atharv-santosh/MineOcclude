"""Tests for the Step 6.4 report pipeline and the Step 6.5 result lock.

Two properties carry the weight here. For the report: no scientific
number can enter without a registered source, and a section with no real
inputs must be present-and-blocked rather than absent. For the lock: a
correction produces a *successor*, and the predecessor survives
byte-identical with a supersession pointer.

All fixtures are synthetic and labeled as such.
"""

from __future__ import annotations

import json

import pytest

from mineocclude.baselines.preliminary_report_v0_1 import (
    PERSON_B_SCIENTIFIC_THRESHOLDS,
    PERSON_D_PLANNING_THRESHOLDS,
    REQUIRED_SECTION_IDS,
    Blocker,
    MetricValue,
    PreliminaryReportError,
    ReportSection,
    blocked_section,
    build_preliminary_report,
    dump_preliminary_report,
    validate_preliminary_report,
)
from mineocclude.baselines.result_lock_v0_1 import (
    ACKNOWLEDGEMENT_ROLES,
    DownstreamImpact,
    LockedArtifact,
    ResultFacts,
    ResultLockError,
    acknowledge_result_lock,
    build_result_lock,
    compute_lock_checksum,
    dump_result_lock,
    supersede_result_lock,
    validate_result_lock,
)

SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64


def _blocker(artifact="person_b_metric_table"):
    return Blocker(
        missing_artifact=artifact,
        expected_owner="person_b",
        expected_schema_or_version="person-b-step4-1-final-comparison-output-v0-1",
        required_identity_fields=("metric_id", "layer_idx", "target_name"),
        exact_command_after_receipt=(
            "python scripts/run_person_d_step6_4_preliminary_report.py "
            "--metric-table <path> --output-root <path>"
        ),
    )


def _all_blocked_sections():
    return [
        blocked_section(
            section_id=section_id,
            title=section_id.replace("_", " "),
            comparison_kind="paired",
            blockers=[_blocker()],
        )
        for section_id in REQUIRED_SECTION_IDS
    ]


def _report(**overrides):
    kwargs = {
        "sections": _all_blocked_sections(),
        "run_id": "synthetic-report-v0-1",
        "prediction_run_ids": ["synthetic-pred-1"],
        "metric_run_ids": ["synthetic-metric-1"],
        "accepted_manifest_sha256": SHA_A,
        "fold_manifest_sha256": SHA_B,
    }
    kwargs.update(overrides)
    return build_preliminary_report(**kwargs)


# --------------------------------------------------------------------------
# Step 6.4 -- preliminary comparison report
# --------------------------------------------------------------------------


def test_fully_blocked_report_is_valid_and_marked_incomplete():
    document = _report()
    validate_preliminary_report(document)
    assert document["report_complete"] is False
    assert document["blocked_section_count"] == len(REQUIRED_SECTION_IDS)
    assert document["rendered_section_count"] == 0


def test_every_required_section_is_present_in_the_frozen_order():
    document = _report()
    assert tuple(s["section_id"] for s in document["sections"]) == REQUIRED_SECTION_IDS


def test_omitting_a_section_is_rejected():
    sections = _all_blocked_sections()[:-1]
    with pytest.raises(PreliminaryReportError, match="missing required sections"):
        _report(sections=sections)


def test_a_value_without_a_registered_source_cannot_be_constructed():
    with pytest.raises(PreliminaryReportError, match="no registered source record"):
        MetricValue(
            metric_id="paired_loss_improvement",
            value=0.42,
            unit="blocks_squared",
            sample_count=5,
            sample_unit="whole_trajectory",
            source_record_id="",
            source_sha256=SHA_C,
        )


def test_a_rendered_section_without_values_is_rejected():
    with pytest.raises(PreliminaryReportError, match="carries no registered metric"):
        ReportSection(
            section_id="u1_vs_last_seen",
            title="U1 versus last-seen",
            comparison_kind="paired",
            status="rendered",
        )


def test_a_blocked_section_carrying_values_is_rejected():
    value = MetricValue(
        metric_id="paired_loss_improvement",
        value=0.42,
        unit="blocks_squared",
        sample_count=5,
        sample_unit="whole_trajectory",
        source_record_id="person-b-metric-1",
        source_sha256=SHA_C,
    )
    with pytest.raises(PreliminaryReportError, match="must be structurally empty"):
        ReportSection(
            section_id="u1_vs_last_seen",
            title="U1 versus last-seen",
            comparison_kind="paired",
            status="blocked",
            values=(value,),
            blockers=(_blocker(),),
        )


def test_a_blocked_section_without_a_named_artifact_is_rejected():
    with pytest.raises(PreliminaryReportError, match="names no missing artifact"):
        ReportSection(
            section_id="u1_vs_last_seen",
            title="U1 versus last-seen",
            comparison_kind="paired",
            status="blocked",
        )


def test_a_rendered_section_carries_its_source_and_sample_unit_through():
    sections = _all_blocked_sections()
    value = MetricValue(
        metric_id="layout_macro_paired_loss_improvement",
        value=0.25,
        unit="blocks_squared",
        sample_count=5,
        sample_unit="whole_trajectory",
        source_record_id="person-b-metric-record-7",
        source_sha256=SHA_C,
    )
    sections[0] = ReportSection(
        section_id="u1_vs_last_seen",
        title="U1 versus last-seen",
        comparison_kind="paired",
        status="rendered",
        methods=("last_seen",),
        target_name="mu_oracle_blocks",
        values=(value,),
        na_count=3,
        missing_count=0,
    )
    document = _report(sections=sections)
    validate_preliminary_report(document)
    rendered = document["sections"][0]
    assert rendered["status"] == "rendered"
    assert rendered["comparison_classes"] == ["memory_heuristic"]
    assert rendered["values"][0]["source_record_id"] == "person-b-metric-record-7"
    assert rendered["values"][0]["sample_unit"] == "whole_trajectory"
    assert document["totals"]["na_cells"] == 3
    assert document["report_complete"] is False  # other sections remain blocked


def test_planning_and_scientific_thresholds_never_share_a_key():
    assert not set(PERSON_B_SCIENTIFIC_THRESHOLDS) & set(PERSON_D_PLANNING_THRESHOLDS)
    document = _report()
    assert document["scientific_thresholds"]["owner_role"] == "person_b"
    assert document["planning_thresholds"]["owner_role"] == "person_d"


def test_validator_rejects_a_planning_threshold_smuggled_into_the_gates():
    document = _report()
    tampered = json.loads(json.dumps(document, default=list))
    key = next(iter(PERSON_D_PLANNING_THRESHOLDS))
    tampered["scientific_thresholds"]["gates"][key] = 1
    with pytest.raises(PreliminaryReportError, match="share keys"):
        validate_preliminary_report(tampered)


def test_validator_rejects_a_manually_entered_value():
    document = _report()
    tampered = json.loads(json.dumps(document, default=list))
    tampered["sections"][0]["status"] = "rendered"
    tampered["sections"][0]["values"] = [
        {
            "metric_id": "hand_typed",
            "value": 0.9,
            "unit": "blocks_squared",
            "sample_count": 5,
            "sample_unit": "whole_trajectory",
            "source_record_id": "",
            "source_sha256": "",
            "owner_role": "person_b",
        }
    ]
    with pytest.raises(PreliminaryReportError, match="hand-copied number"):
        validate_preliminary_report(tampered)


def test_validator_rejects_a_report_declaring_manual_values():
    document = dict(_report())
    document["manual_scientific_values_present"] = True
    with pytest.raises(PreliminaryReportError, match="manually copied"):
        validate_preliminary_report(document)


def test_report_is_deterministic():
    assert dump_preliminary_report(_report()) == dump_preliminary_report(_report())


def test_report_blockers_are_actionable():
    document = _report()
    assert document["blockers"]
    for blocker in document["blockers"]:
        assert blocker["missing_artifact"]
        assert blocker["expected_owner"]
        assert blocker["expected_schema_or_version"]
        assert blocker["exact_command_after_receipt"]


# --------------------------------------------------------------------------
# Step 6.5 -- result lock and supersession
# --------------------------------------------------------------------------


def _facts(**overrides):
    values = {
        "prediction_row_count": 100,
        "scored_row_count": 80,
        "non_applicable_row_count": 15,
        "missing_row_count": 5,
        "excluded_trajectory_count": 1,
        "accepted_trajectory_count": 4,
        "comparison_labels": ("U1_vs_last_seen", "U1_vs_grouped_shuffled"),
    }
    values.update(overrides)
    return ResultFacts(**values)


def _lock(**overrides):
    kwargs = {
        "lock_id": "person-d-result-lock-synthetic-1",
        "lock_version": "0.1.0",
        "prediction_run_ids": ["synthetic-pred-1"],
        "metric_run_ids": ["synthetic-metric-1"],
        "accepted_manifest_sha256": SHA_A,
        "fold_manifest_sha256": SHA_B,
        "code_sha256": SHA_C,
        "config_sha256": SHA_A,
        "facts": _facts(),
        "locked_artifacts": [
            LockedArtifact("predictions", "out/predictions.json", SHA_B, 1234, "person_d")
        ],
        "downstream": [DownstreamImpact("figure_u1", "figure", "person_e")],
    }
    kwargs.update(overrides)
    return build_result_lock(**kwargs)


def test_result_lock_validates_and_carries_acknowledgement_slots():
    document = _lock()
    validate_result_lock(document)
    assert set(document["acknowledgements"]) == set(ACKNOWLEDGEMENT_ROLES)
    assert all(
        entry["status"] == "pending" for entry in document["acknowledgements"].values()
    )


def test_facts_must_partition_the_prediction_row_count():
    with pytest.raises(ResultLockError, match="must equal prediction_row_count"):
        _facts(scored_row_count=90)


def test_acknowledgement_does_not_change_the_locked_facts():
    document = _lock()
    signed = acknowledge_result_lock(
        document, role="person_b", status="acknowledged", commit="deadbeef"
    )
    assert signed["lock_checksum"] == document["lock_checksum"]
    assert signed["facts"] == document["facts"]
    assert signed["acknowledgements"]["person_b"]["status"] == "acknowledged"
    validate_result_lock(signed)


def test_a_rejection_must_carry_a_note():
    document = _lock()
    with pytest.raises(ResultLockError, match="rejected the lock without a note"):
        acknowledge_result_lock(document, role="person_a", status="rejected")


def test_supersession_preserves_the_predecessor_and_links_both_ways():
    original = _lock()
    original_bytes = dump_result_lock(original)

    retired, successor = supersede_result_lock(
        original,
        lock_id="person-d-result-lock-synthetic-2",
        lock_version="0.2.0",
        reason="fold manifest v2 corrected two trajectory fold assignments",
    )

    # The predecessor's facts, checksum, and version are untouched.
    assert retired["facts"] == original["facts"]
    assert retired["lock_checksum"] == original["lock_checksum"]
    assert retired["lock_version"] == original["lock_version"]
    assert retired["status"] == "superseded"
    assert retired["superseded_by"] == successor["lock_id"]

    assert successor["supersedes"] == original["lock_id"]
    assert successor["supersession_reason"]
    assert successor["lock_version"] == "0.2.0"
    validate_result_lock(successor)

    # And the original document object was not mutated in place.
    assert dump_result_lock(original) == original_bytes


def test_supersession_requires_a_new_version():
    original = _lock()
    with pytest.raises(ResultLockError, match="new version"):
        supersede_result_lock(
            original,
            lock_id="person-d-result-lock-synthetic-2",
            lock_version="0.1.0",
            reason="same version",
        )


def test_supersession_requires_a_reason():
    original = _lock()
    with pytest.raises(ResultLockError, match="must record a reason"):
        supersede_result_lock(
            original,
            lock_id="person-d-result-lock-synthetic-2",
            lock_version="0.2.0",
            reason="",
        )


def test_editing_a_lock_in_place_is_detected_by_the_checksum():
    document = _lock()
    tampered = json.loads(json.dumps(document, default=list))
    tampered["facts"]["scored_row_count"] = 81
    tampered["facts"]["missing_row_count"] = 4
    assert compute_lock_checksum(tampered) != tampered["lock_checksum"]
    with pytest.raises(ResultLockError, match="edited after locking"):
        validate_result_lock(tampered)


def test_a_real_lock_requires_real_input_identities():
    with pytest.raises(ResultLockError, match="requires accepted_manifest_sha256"):
        _lock(evidence_kind="real", accepted_manifest_sha256=None)
    with pytest.raises(ResultLockError, match="requires fold_manifest_sha256"):
        _lock(evidence_kind="real", fold_manifest_sha256=None)
    with pytest.raises(ResultLockError, match="prediction run ID"):
        _lock(evidence_kind="real", prediction_run_ids=[])


def test_a_synthetic_lock_never_claims_to_be_real():
    document = _lock()
    assert document["evidence_kind"] == "synthetic"
    real = _lock(evidence_kind="real")
    assert real["evidence_kind"] == "real"
    validate_result_lock(real)


def test_lock_is_deterministic():
    assert dump_result_lock(_lock()) == dump_result_lock(_lock())


def test_a_lock_cannot_supersede_itself():
    document = dict(_lock())
    document["supersedes"] = document["lock_id"]
    document["supersession_reason"] = "self"
    with pytest.raises(ResultLockError, match="cannot supersede itself"):
        validate_result_lock(document)
