"""Steps 9.4-9.8 — rehearsals, evidence chain, decision, and tag preflight."""

from __future__ import annotations

import unittest

from mineocclude.experiments.checkpoint import (
    MVP_TAG_NAME,
    RED_ENGINEERING_AREAS,
    CheckpointDecision,
    CheckpointError,
    CheckpointErrorCode,
    EvidenceLink,
    RehearsalStatus,
    RunbookStep,
    build_evidence_chain,
    build_rehearsal_receipt,
    build_tag_record,
    decide_checkpoint,
    index_digest,
)

TRACE = {
    "code_sha": "b" * 40,
    "config_hash": "a" * 64,
    "model_hash": "c" * 64,
    "data_identity_hash": "d" * 64,
    "seed": 20260725,
    "run_id": "mineocclude-run-1",
    "artifact_sha256": "e" * 64,
}

ENGINEERING_PASS = {name: True for name in RED_ENGINEERING_AREAS}


class RehearsalTests(unittest.TestCase):
    def test_a_fully_executed_rehearsal_succeeds(self):
        receipt = build_rehearsal_receipt(
            rehearsal_id="r1",
            owning_role="person_d_baselines",
            runbook_path="docs/baselines/person_d_phase1.md",
            runbook_sha256="a" * 64,
            steps=(
                RunbookStep(
                    step_id="D.1",
                    description="read",
                    status=RehearsalStatus.COMPLETED,
                ),
            ),
        )
        self.assertTrue(receipt["succeeded"])
        self.assertEqual(receipt["status"], "COMPLETED")
        self.assertIsNone(receipt["blocked_reason"])

    def test_a_blocked_step_forces_a_blocked_receipt_with_a_reason(self):
        receipt = build_rehearsal_receipt(
            rehearsal_id="r1",
            owning_role="person_c_data",
            runbook_path="docs/runbooks/x.md",
            runbook_sha256=None,
            steps=(
                RunbookStep(
                    step_id="C.1",
                    description="start server",
                    status=RehearsalStatus.BLOCKED,
                    detail="no Java runtime",
                ),
            ),
        )
        self.assertFalse(receipt["succeeded"])
        self.assertEqual(receipt["status"], "BLOCKED")
        self.assertTrue(receipt["blocked_reason"])

    def test_missing_instructions_are_documented(self):
        receipt = build_rehearsal_receipt(
            rehearsal_id="r1",
            owning_role="person_c_data",
            runbook_path="docs/runbooks/x.md",
            runbook_sha256=None,
            steps=(
                RunbookStep(
                    step_id="C.1",
                    description="start server",
                    status=RehearsalStatus.BLOCKED,
                    instruction_gap="no documented server start command",
                ),
            ),
        )
        self.assertEqual(receipt["instruction_gap_count"], 1)

    def test_credentials_are_never_recorded_in_the_receipt(self):
        receipt = build_rehearsal_receipt(
            rehearsal_id="r1",
            owning_role="person_c_data",
            runbook_path="docs/runbooks/x.md",
            runbook_sha256=None,
            steps=(
                RunbookStep(
                    step_id="C.1", description="x", status=RehearsalStatus.COMPLETED
                ),
            ),
        )
        self.assertFalse(
            receipt["credentials_in_git_s3_logs_notebooks_or_chat"]
        )

    def test_a_receipt_requires_at_least_one_step(self):
        with self.assertRaises(CheckpointError):
            build_rehearsal_receipt(
                rehearsal_id="r1",
                owning_role="person_c_data",
                runbook_path="x",
                runbook_sha256=None,
                steps=(),
            )


class EvidenceChainTests(unittest.TestCase):
    def _links(self, sha="a" * 64):
        return (
            EvidenceLink(
                order=2,
                claim="second",
                evidence_path="b.json",
                evidence_sha256=sha,
                real=True,
            ),
            EvidenceLink(
                order=1,
                claim="first",
                evidence_path="a.json",
                evidence_sha256="c" * 64,
                real=False,
            ),
        )

    def test_links_are_published_in_demonstration_order(self):
        chain = build_evidence_chain(self._links(), traced_example=TRACE)
        self.assertEqual(
            [link["order"] for link in chain["links"]], [1, 2]
        )
        self.assertEqual(chain["real_evidence_count"], 1)
        self.assertEqual(chain["synthetic_evidence_count"], 1)

    def test_unbound_evidence_is_surfaced(self):
        chain = build_evidence_chain(self._links(sha=None), traced_example=TRACE)
        self.assertEqual(chain["unbound_evidence_count"], 1)
        self.assertFalse(chain["followable_without_accepting_assertions"])

    def test_an_incomplete_trace_is_refused(self):
        trace = dict(TRACE)
        del trace["model_hash"]
        with self.assertRaises(CheckpointError) as caught:
            build_evidence_chain(self._links(), traced_example=trace)
        self.assertIs(caught.exception.code, CheckpointErrorCode.UNBOUND_ARTIFACT)

    def test_an_empty_chain_is_refused(self):
        with self.assertRaises(CheckpointError):
            build_evidence_chain((), traced_example=TRACE)


class DecisionTests(unittest.TestCase):
    def test_all_green_yields_green(self):
        decision = decide_checkpoint(
            engineering_gates=ENGINEERING_PASS,
            u1_green=True,
            u2_green=True,
            u3_directionally_correct=True,
            u4_is_smoke_test_only=True,
            scientific_test_failed_cleanly=False,
        )
        self.assertEqual(decision["decision"], CheckpointDecision.GREEN.value)

    def test_a_failed_engineering_area_forces_red_and_is_labelled_engineering(self):
        gates = {**ENGINEERING_PASS, "reproducibility": False}
        decision = decide_checkpoint(
            engineering_gates=gates,
            u1_green=True,
            u2_green=True,
            u3_directionally_correct=True,
            u4_is_smoke_test_only=True,
            scientific_test_failed_cleanly=False,
        )
        self.assertEqual(decision["decision"], CheckpointDecision.RED.value)
        self.assertEqual(decision["red_engineering_areas_triggered"], ["reproducibility"])
        self.assertFalse(
            decision["failed_engineering_reported_as_negative_model_finding"]
        )

    def test_a_failed_visible_control_forces_red(self):
        gates = {**ENGINEERING_PASS, "visible_positive_control": False}
        decision = decide_checkpoint(
            engineering_gates=gates,
            u1_green=True,
            u2_green=True,
            u3_directionally_correct=True,
            u4_is_smoke_test_only=True,
            scientific_test_failed_cleanly=False,
        )
        self.assertEqual(decision["decision"], CheckpointDecision.RED.value)

    def test_unevaluated_science_with_passing_engineering_is_yellow(self):
        decision = decide_checkpoint(
            engineering_gates=ENGINEERING_PASS,
            u1_green=None,
            u2_green=None,
            u3_directionally_correct=None,
            u4_is_smoke_test_only=True,
            scientific_test_failed_cleanly=False,
        )
        self.assertEqual(decision["decision"], CheckpointDecision.YELLOW.value)
        self.assertEqual(decision["scientific"]["unevaluated"], ["u1", "u2", "u3"])
        self.assertTrue(decision["alternative_results_ladder_applies"])

    def test_a_clean_scientific_failure_is_yellow_not_red(self):
        decision = decide_checkpoint(
            engineering_gates=ENGINEERING_PASS,
            u1_green=True,
            u2_green=False,
            u3_directionally_correct=True,
            u4_is_smoke_test_only=True,
            scientific_test_failed_cleanly=True,
        )
        self.assertEqual(decision["decision"], CheckpointDecision.YELLOW.value)

    def test_scope_cuts_prefer_breadth_over_validity(self):
        decision = decide_checkpoint(
            engineering_gates=ENGINEERING_PASS,
            u1_green=None,
            u2_green=None,
            u3_directionally_correct=None,
            u4_is_smoke_test_only=True,
            scientific_test_failed_cleanly=False,
            scope_cuts=(
                {"cut_id": "SC-1", "kind": "breadth", "preserves_validity": True},
            ),
        )
        self.assertTrue(decision["cut_breadth_before_validity"])
        self.assertEqual(len(decision["scope_cuts"]), 1)


class TagRecordTests(unittest.TestCase):
    def _artifacts(self, sha="a" * 64):
        return ({"artifact_id": "a1", "uri": "s3://bucket/a1", "sha256": sha},)

    def _record(self, **overrides):
        kwargs = dict(
            tag_name=MVP_TAG_NAME,
            target_commit="b" * 40,
            branch="role/person-a-model",
            identity={
                "code_sha": "b" * 40,
                "config_hash": "a" * 64,
                "model_hash": "c" * 64,
                "preprocess_hash": "d" * 64,
            },
            accepted_manifest_sha256="e" * 64,
            schema_version="1.0",
            external_artifacts=self._artifacts(),
            run_ids=("mineocclude-run-1",),
            review_completed=True,
        )
        kwargs.update(overrides)
        return build_tag_record(**kwargs)

    def test_a_complete_record_is_ready_for_coordinated_tagging(self):
        record = self._record()
        self.assertTrue(record["tag_record_complete"])
        self.assertEqual(record["status"], "READY_FOR_COORDINATED_TAGGING")
        self.assertTrue(record["reconstructs_accepted_mvp_identity"])

    def test_the_tag_is_never_pushed_from_a_role_branch(self):
        record = self._record()
        self.assertFalse(record["tag_pushed"])
        self.assertFalse(record["created_from_role_branch"])
        self.assertTrue(record["tag_creation_is_coordinated_five_role_operation"])

    def test_pushing_from_a_role_branch_is_refused(self):
        with self.assertRaises(CheckpointError) as caught:
            self._record(tag_pushed=True)
        self.assertIs(caught.exception.code, CheckpointErrorCode.TAG_PUSH_FORBIDDEN)

    def test_an_unbound_external_artifact_makes_the_record_incomplete(self):
        record = self._record(external_artifacts=({"artifact_id": "a1", "uri": "s3://b/a"},))
        self.assertEqual(record["unbound_external_artifact_count"], 1)
        self.assertFalse(record["tag_record_complete"])
        self.assertEqual(record["status"], "INCOMPLETE")

    def test_an_unreviewed_record_is_incomplete(self):
        record = self._record(review_completed=False)
        self.assertFalse(record["tag_record_complete"])

    def test_a_missing_identity_field_is_reported(self):
        record = self._record(identity={"code_sha": "b" * 40})
        self.assertEqual(
            sorted(record["missing_identity_fields"]),
            ["config_hash", "model_hash", "preprocess_hash"],
        )

    def test_the_artifact_index_has_a_stable_digest(self):
        self.assertEqual(
            index_digest(self._artifacts()), index_digest(self._artifacts())
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
