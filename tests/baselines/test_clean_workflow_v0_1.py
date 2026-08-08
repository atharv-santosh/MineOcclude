"""Tests for Phase 8 Steps 8.1-8.3.

8.1: a clean-workflow run must cover every stage in order, capture the
command and streams, and only ever skip a stage because of registered
state -- never a hand-placed file. 8.2: every demonstration section
resolves to a registered source or stays empty and blocker-labelled.
8.3: the classifier must keep engineering failure apart from negative
science, refuse to call unavailable science successful, and reject a
manual override that upgrades the status.

All fixtures are synthetic and labeled as such.
"""

from __future__ import annotations

import json

import pytest

from mineocclude.baselines.clean_workflow_v0_1 import (
    CHECKPOINT_SECTION_IDS,
    RED_FAILURE_KINDS,
    WORKFLOW_STAGE_IDS,
    YELLOW_FAILURE_KINDS,
    CheckpointFinding,
    CheckpointSection,
    CleanWorkflowError,
    StageResult,
    build_checkpoint_demonstration,
    build_clean_workflow_run,
    classify_checkpoint,
    dump_document,
    validate_checkpoint_classification,
    validate_checkpoint_demonstration,
    validate_clean_workflow_run,
)

SHA = "a" * 64

ENVIRONMENT = {
    "python_version": "3.10.20",
    "platform": "win32",
    "interpreter_path": r"C:\Users\lollo\MineOcclude-TestRunner\Scripts\python.exe",
}


def _stage(stage_id, status="passed", **overrides):
    values = {
        "stage_id": stage_id,
        "status": status,
        "command": f"python scripts/run_person_d_{stage_id}.py --synthetic",
        "stdout_path": f"logs/{stage_id}.out",
        "stderr_path": f"logs/{stage_id}.err",
        "runtime_seconds": 0.5,
        "output_paths": (f"out/{stage_id}.json",),
    }
    if status in ("failed", "blocked"):
        values["failure_detail"] = f"{stage_id} could not complete"
    values.update(overrides)
    return StageResult(**values)


def _all_stages(**per_stage_status):
    return [
        _stage(stage_id, per_stage_status.get(stage_id, "passed"))
        for stage_id in WORKFLOW_STAGE_IDS
    ]


def _run(**overrides):
    kwargs = {
        "run_id": "person-d-synthetic-clean-run-v0-1",
        "stages": _all_stages(),
        "environment": ENVIRONMENT,
        "package_lock_sha256": SHA,
    }
    kwargs.update(overrides)
    return build_clean_workflow_run(**kwargs)


# --------------------------------------------------------------------------
# Step 8.1 -- clean workflow
# --------------------------------------------------------------------------


def test_synthetic_clean_reproduction_passes_and_stays_labeled_synthetic():
    document = _run()
    validate_clean_workflow_run(document)
    assert document["reproduction_complete"] is True
    assert document["evidence_kind"] == "synthetic"
    assert document["reproduction_kind"] == "synthetic_clean_reproduction"


def test_workflow_covers_every_stage_in_the_frozen_order():
    document = _run()
    assert tuple(s["stage_id"] for s in document["stages"]) == WORKFLOW_STAGE_IDS
    assert len(WORKFLOW_STAGE_IDS) == 13


def test_omitting_a_stage_is_rejected():
    with pytest.raises(CleanWorkflowError, match="missing stages"):
        _run(stages=_all_stages()[:-1])


def test_a_blocked_stage_keeps_the_run_incomplete():
    document = _run(stages=_all_stages(build_u4_control_matrix="blocked"))
    validate_clean_workflow_run(document)
    assert document["reproduction_complete"] is False
    assert document["stage_status_counts"]["blocked"] == 1


def test_a_stage_that_failed_must_say_why():
    with pytest.raises(CleanWorkflowError, match="is failed with no detail"):
        StageResult(
            stage_id="run_baselines",
            status="failed",
            command="python x.py",
            stdout_path=None,
            stderr_path=None,
            runtime_seconds=1.0,
        )


def test_a_stage_may_only_be_skipped_via_registered_state():
    with pytest.raises(CleanWorkflowError, match="never because a file was moved"):
        StageResult(
            stage_id="run_baselines",
            status="skipped_resumed",
            command="python x.py --resume",
            stdout_path=None,
            stderr_path=None,
            runtime_seconds=0.0,
            resumed_from_registered_state=False,
        )


def test_a_resumed_stage_must_name_its_registered_state_key():
    with pytest.raises(CleanWorkflowError, match="without naming the"):
        StageResult(
            stage_id="run_baselines",
            status="skipped_resumed",
            command="python x.py --resume",
            stdout_path=None,
            stderr_path=None,
            runtime_seconds=0.0,
            resumed_from_registered_state=True,
        )


def test_a_properly_resumed_stage_is_accepted():
    stages = _all_stages()
    stages[5] = _stage(
        "run_baselines",
        status="skipped_resumed",
        runtime_seconds=0.0,
        resumed_from_registered_state=True,
        registered_state_key="run_state.json:families.last_seen",
    )
    document = _run(stages=stages)
    validate_clean_workflow_run(document)
    assert document["stage_status_counts"]["skipped_resumed"] == 1
    assert document["reproduction_complete"] is True


def test_a_stage_without_a_command_is_rejected():
    with pytest.raises(CleanWorkflowError, match="records no command"):
        StageResult(
            stage_id="run_baselines",
            status="passed",
            command="",
            stdout_path=None,
            stderr_path=None,
            runtime_seconds=1.0,
        )


def test_the_environment_must_be_captured():
    with pytest.raises(CleanWorkflowError, match="python_version"):
        _run(environment={"platform": "win32", "interpreter_path": "x"})


def test_a_synthetic_run_cannot_be_relabeled_a_real_reproduction():
    document = dict(_run())
    document["reproduction_kind"] = "real_clean_reproduction"
    with pytest.raises(CleanWorkflowError, match="never be labeled a real one"):
        validate_clean_workflow_run(document)


def test_workflow_run_is_deterministic():
    assert dump_document(_run()) == dump_document(_run())


# --------------------------------------------------------------------------
# Step 8.2 -- checkpoint demonstration
# --------------------------------------------------------------------------


def _blocked_section(section_id):
    return CheckpointSection(
        section_id=section_id,
        status="blocked",
        blocker=f"real output for {section_id} does not exist yet",
        blocker_owner="person_b",
    )


def _resolved_section(section_id):
    return CheckpointSection(
        section_id=section_id,
        status="resolved",
        source_artifact_id=f"person-d-{section_id}",
        source_path=f"docs/status/{section_id}.json",
        source_sha256=SHA,
        owner_role="person_d",
        displayed_values={"row_count": 12},
    )


def _demonstration(resolved=()):
    sections = [
        _resolved_section(sid) if sid in resolved else _blocked_section(sid)
        for sid in CHECKPOINT_SECTION_IDS
    ]
    return build_checkpoint_demonstration(
        run_id="person-d-synthetic-checkpoint-v0-1", sections=sections
    )


def test_demonstration_covers_all_fourteen_sections_in_order():
    document = _demonstration()
    assert tuple(s["section_id"] for s in document["sections"]) == CHECKPOINT_SECTION_IDS
    assert len(CHECKPOINT_SECTION_IDS) == 14


def test_a_fully_blocked_demonstration_is_valid_and_incomplete():
    document = _demonstration()
    validate_checkpoint_demonstration(document)
    assert document["demonstration_complete"] is False
    assert document["artifact_index"] == ()


def test_a_resolved_section_must_resolve_to_a_registered_source():
    with pytest.raises(CleanWorkflowError, match="registered machine-readable source"):
        CheckpointSection(
            section_id="prediction_runs",
            status="resolved",
            displayed_values={"row_count": 12},
        )


def test_a_blocked_section_may_not_display_values():
    with pytest.raises(CleanWorkflowError, match="must stay empty"):
        CheckpointSection(
            section_id="paired_metrics",
            status="blocked",
            displayed_values={"improvement": 0.4},
            blocker="no real metrics",
            blocker_owner="person_b",
        )


def test_a_blocked_section_must_name_a_blocker_and_owner():
    with pytest.raises(CleanWorkflowError, match="names no blocker"):
        CheckpointSection(section_id="paired_metrics", status="blocked")


def test_resolved_sections_enter_the_artifact_index():
    document = _demonstration(resolved={"accepted_input_identity", "legal_input_firewall"})
    validate_checkpoint_demonstration(document)
    indexed = {entry["section_id"] for entry in document["artifact_index"]}
    assert indexed == {"accepted_input_identity", "legal_input_firewall"}
    assert document["resolved_section_count"] == 2
    assert document["demonstration_complete"] is False


def test_omitting_a_demonstration_section_is_rejected():
    sections = [_blocked_section(sid) for sid in CHECKPOINT_SECTION_IDS[:-1]]
    with pytest.raises(CleanWorkflowError, match="missing sections"):
        build_checkpoint_demonstration(run_id="x", sections=sections)


def test_demonstration_is_deterministic():
    assert dump_document(_demonstration()) == dump_document(_demonstration())


# --------------------------------------------------------------------------
# Step 8.3 -- GREEN / YELLOW / RED classifier
# --------------------------------------------------------------------------


ALL_GATES_PASS = dict(
    contracts_pass=True,
    controls_pass=True,
    result_lineage_pass=True,
    clean_reproduction_pass=True,
)


def _finding(finding_id, failure_kind, nature, **overrides):
    values = {
        "finding_id": finding_id,
        "failure_kind": failure_kind,
        "nature": nature,
        "evidence_artifact_id": "person-d-evidence-1",
        "evidence_sha256": SHA,
        "owner_role": "person_d",
        "next_action": "re-run the affected stage",
        "affected_claims": ("U1",),
        "detail": "synthetic finding",
    }
    values.update(overrides)
    return CheckpointFinding(**values)


def test_green_requires_all_gates_and_no_findings():
    document = classify_checkpoint(findings=[], **ALL_GATES_PASS)
    validate_checkpoint_classification(document)
    assert document["classification"] == "GREEN"


def test_a_failed_gate_forces_red():
    gates = dict(ALL_GATES_PASS)
    gates["clean_reproduction_pass"] = False
    document = classify_checkpoint(findings=[], **gates)
    validate_checkpoint_classification(document)
    assert document["classification"] == "RED"


@pytest.mark.parametrize("failure_kind", RED_FAILURE_KINDS)
def test_every_red_failure_kind_forces_red(failure_kind):
    document = classify_checkpoint(
        findings=[_finding("f1", failure_kind, "engineering")], **ALL_GATES_PASS
    )
    validate_checkpoint_classification(document)
    assert document["classification"] == "RED"


@pytest.mark.parametrize("failure_kind", YELLOW_FAILURE_KINDS)
def test_every_yellow_failure_kind_forces_yellow(failure_kind):
    document = classify_checkpoint(
        findings=[_finding("f1", failure_kind, "science")], **ALL_GATES_PASS
    )
    validate_checkpoint_classification(document)
    assert document["classification"] == "YELLOW"
    assert document["negative_science_count"] == 1
    assert document["engineering_failure_count"] == 0


def test_a_red_failure_cannot_be_relabeled_as_science():
    with pytest.raises(CleanWorkflowError, match="always engineering failures"):
        _finding("f1", "split_leakage", "science")


def test_a_weakened_claim_cannot_be_relabeled_as_an_engineering_defect():
    with pytest.raises(CleanWorkflowError, match="not an engineering defect"):
        _finding("f1", "negative_scientific_result", "engineering")


def test_unavailable_science_is_never_classified_as_successful_science():
    document = classify_checkpoint(
        findings=[
            _finding(
                "f1",
                "real_person_b_fold_manifest_absent",
                "unavailable_input",
                owner_role="person_b",
                next_action="publish the 66-cell fold manifest",
            )
        ],
        **ALL_GATES_PASS,
    )
    validate_checkpoint_classification(document)
    assert document["classification"] == "YELLOW"
    assert document["unavailable_input_count"] == 1


def test_a_manual_override_that_upgrades_the_status_is_rejected():
    document = classify_checkpoint(
        findings=[_finding("f1", "split_leakage", "engineering")],
        manual_override="GREEN",
        manual_override_evidence_artifact_id="person-d-evidence-1",
        **ALL_GATES_PASS,
    )
    assert document["classification"] == "RED"
    assert document["manual_override_accepted"] is False
    assert "may not upgrade" in document["manual_override_rejection_reason"]
    validate_checkpoint_classification(document)


def test_a_manual_override_without_evidence_is_rejected():
    document = classify_checkpoint(
        findings=[], manual_override="RED", **ALL_GATES_PASS
    )
    assert document["classification"] == "GREEN"
    assert document["manual_override_accepted"] is False
    assert "registered evidence" in document["manual_override_rejection_reason"]


def test_a_manual_override_that_escalates_with_evidence_is_accepted():
    document = classify_checkpoint(
        findings=[],
        manual_override="RED",
        manual_override_evidence_artifact_id="person-b-incident-1",
        **ALL_GATES_PASS,
    )
    validate_checkpoint_classification(document)
    assert document["classification"] == "RED"
    assert document["computed_classification"] == "GREEN"
    assert document["manual_override_accepted"] is True


def test_validator_rejects_a_hand_edited_classification():
    document = json.loads(
        json.dumps(classify_checkpoint(findings=[], **ALL_GATES_PASS), default=list)
    )
    document["classification"] = "GREEN"
    document["computed_classification"] = "RED"
    with pytest.raises(CleanWorkflowError, match="does not follow from the gates"):
        validate_checkpoint_classification(document)


def test_every_finding_names_evidence_owner_next_action_and_claims():
    document = classify_checkpoint(
        findings=[_finding("f1", "control_weakens_specificity", "science")],
        **ALL_GATES_PASS,
    )
    finding = document["findings"][0]
    assert finding["evidence_artifact_id"]
    assert finding["owner_role"]
    assert finding["next_action"]
    assert finding["affected_claims"] == ["U1"]


def test_a_finding_without_a_next_action_is_rejected():
    with pytest.raises(CleanWorkflowError, match="records no next_action"):
        _finding("f1", "control_weakens_specificity", "science", next_action="")


def test_classification_is_deterministic():
    def build():
        return classify_checkpoint(
            findings=[_finding("f1", "control_weakens_specificity", "science")],
            **ALL_GATES_PASS,
        )

    assert dump_document(build()) == dump_document(build())
