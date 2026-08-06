"""Steps 6.7 and 6.8 — certify the executed ten-pilot expansion without rerunning it."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from mineocclude.experiments.pilot_certification import (
    EXPECTED_LAYER_COUNT,
    ChangeClass,
    PilotCertificationError,
    PilotCertificationErrorCode,
    PilotChange,
    build_exclusion_record,
    build_pilot_closeout,
    build_runtime_storage_benchmark,
    certify_ten_pilot_expansion,
    forecast_queue,
    load_pilot_evidence,
)

ROOT = Path(__file__).resolve().parents[2]
SESSION_ROOT = (
    ROOT
    / "docs"
    / "status"
    / "phase6_runtime"
    / "person-a-phase6-ten-pilot-expansion-seed-20260725"
)
FOLD_MANIFEST = (
    ROOT
    / "data"
    / "handoff_a"
    / "person_b_ten_pilot_fold_manifest_v0_1"
    / "ten_pilot_frame_fold_manifest.json"
)


def _fold_manifest() -> dict:
    return json.loads(FOLD_MANIFEST.read_text(encoding="utf-8"))


class EvidenceLoadingTests(unittest.TestCase):
    def test_ten_committed_pilots_are_loaded(self):
        evidence = load_pilot_evidence(SESSION_ROOT)
        self.assertEqual(len(evidence), 10)
        self.assertEqual(
            sum(item.activation_row_count for item in evidence), 37480
        )
        self.assertEqual(sum(item.chunk_count for item in evidence), 200)

    def test_missing_session_root_is_reported_exactly(self):
        with self.assertRaises(PilotCertificationError) as caught:
            load_pilot_evidence(ROOT / "docs" / "status" / "absent-session")
        self.assertIs(
            caught.exception.code, PilotCertificationErrorCode.MISSING_EVIDENCE
        )


class CertificationTests(unittest.TestCase):
    def setUp(self):
        self.report = certify_ten_pilot_expansion(
            SESSION_ROOT, downstream_fold_manifest=_fold_manifest()
        )

    def test_step_6_7_certifies_from_committed_evidence(self):
        self.assertEqual(self.report["status"], "CERTIFIED")
        self.assertTrue(
            self.report["certified_from_committed_evidence_without_rerun"]
        )
        self.assertEqual(self.report["deterministic_seed"], 20260725)

    def test_every_pilot_has_exact_layer_and_frame_cardinality(self):
        cardinality = self.report["cardinality"]
        self.assertTrue(cardinality["all_pilots_exact"])
        self.assertEqual(cardinality["layer_count"], EXPECTED_LAYER_COUNT)
        self.assertEqual(cardinality["total_frame_count"], 1874)
        self.assertEqual(cardinality["total_activation_row_count"], 37480)
        for row in cardinality["per_pilot"]:
            self.assertEqual(
                row["expected_activation_row_count"],
                row["frame_count"] * EXPECTED_LAYER_COUNT,
            )

    def test_downstream_joins_are_exact(self):
        joins = self.report["downstream_joins"]
        self.assertEqual(joins["trajectory_identity_join"], "exact")
        self.assertEqual(joins["activation_row_join"], "exact")
        self.assertEqual(joins["activation_chunk_join"], "exact")
        self.assertEqual(joins["repository_input_hash_mismatch_count"], 0)

    def test_the_combined_activation_index_and_its_authority_are_recorded(self):
        index = self.report["activation_index"]
        self.assertEqual(
            index["combined_activation_index_sha256"],
            "1a25d2186912ba72fdbf123ea9f07b2255bd0e55c6a48a1a50e3b7c0f23eb1e9",
        )
        self.assertEqual(len(index["per_pilot_activation_index_sha256"]), 10)
        self.assertFalse(index["staged_in_git"])
        authority = index["producing_authority"]
        self.assertEqual(
            authority["person_a_expansion_runner_commit"],
            "c099fe970e2ea0dbf36d994923c9e40af357e585",
        )

    def test_per_pilot_status_records_the_reused_pilot(self):
        rows = {row["trajectory_id"]: row for row in self.report["per_pilot_status"]}
        self.assertEqual(
            rows["layout_00_ep9403"]["status"], "REUSED_EXACT_EXISTING_ARTIFACTS"
        )
        self.assertTrue(rows["layout_00_ep9403"]["reused_without_reextraction"])
        self.assertEqual(rows["layout_00_ep9403"]["step_receipts_present"], [])
        self.assertEqual(
            rows["layout_01_ep9405"]["step_receipts_present"],
            ["6.1", "6.2", "6.3", "6.4", "6.5"],
        )

    def test_audits_are_carried_through_unchanged(self):
        audits = self.report["audits"]
        self.assertTrue(audits["pooling_audit_pass"])
        self.assertTrue(audits["repeatability_audit_pass"])
        self.assertTrue(audits["source_identity_join_pass"])
        self.assertEqual(audits["duplicate_activation_row_count"], 0)
        self.assertEqual(audits["missing_activation_row_count"], 0)
        self.assertFalse(audits["u4_output_inspected"])

    def test_wrong_expected_pilot_count_is_refused(self):
        with self.assertRaises(PilotCertificationError) as caught:
            certify_ten_pilot_expansion(
                SESSION_ROOT,
                downstream_fold_manifest=_fold_manifest(),
                expected_pilot_count=9,
            )
        self.assertIs(
            caught.exception.code, PilotCertificationErrorCode.CARDINALITY_MISMATCH
        )

    def test_a_downstream_row_disagreement_is_refused(self):
        manifest = _fold_manifest()
        manifest["activation_row_count"] = 37481
        with self.assertRaises(PilotCertificationError) as caught:
            certify_ten_pilot_expansion(
                SESSION_ROOT, downstream_fold_manifest=manifest
            )
        self.assertIs(
            caught.exception.code, PilotCertificationErrorCode.JOIN_MISMATCH
        )

    def test_a_downstream_identity_disagreement_is_refused(self):
        manifest = _fold_manifest()
        manifest["accepted_pilot_ids"] = list(manifest["accepted_pilot_ids"])
        manifest["accepted_pilot_ids"][0] = "layout_99_ep0"
        with self.assertRaises(PilotCertificationError) as caught:
            certify_ten_pilot_expansion(
                SESSION_ROOT, downstream_fold_manifest=manifest
            )
        self.assertIs(
            caught.exception.code, PilotCertificationErrorCode.JOIN_MISMATCH
        )


class ExclusionTests(unittest.TestCase):
    def test_exclusions_are_attributed_to_the_admission_rule_owner(self):
        evidence = load_pilot_evidence(SESSION_ROOT)
        record = build_exclusion_record(evidence, _fold_manifest())
        self.assertEqual(record["exclusion_owner"], "person_b_analysis_admission_rule")
        self.assertEqual(record["person_a_extraction_exclusion_count"], 0)
        self.assertEqual(record["downstream_source_frame_count"], 1874)
        self.assertEqual(record["downstream_admitted_frame_count"], 1695)
        self.assertEqual(record["downstream_excluded_frame_count"], 179)
        self.assertTrue(record["admission_arithmetic_holds"])

    def test_broken_admission_arithmetic_is_refused(self):
        evidence = load_pilot_evidence(SESSION_ROOT)
        manifest = _fold_manifest()
        manifest["excluded_frame_count"] = 178
        with self.assertRaises(PilotCertificationError) as caught:
            build_exclusion_record(evidence, manifest)
        self.assertIs(
            caught.exception.code, PilotCertificationErrorCode.JOIN_MISMATCH
        )


class BenchmarkTests(unittest.TestCase):
    def setUp(self):
        self.evidence = load_pilot_evidence(SESSION_ROOT)
        self.benchmark = build_runtime_storage_benchmark(self.evidence)

    def test_benchmark_measures_only_timed_pilots(self):
        self.assertEqual(self.benchmark["measured_pilot_count"], 9)
        self.assertEqual(self.benchmark["total_pilot_count"], 10)
        self.assertEqual(self.benchmark["measured_frame_count"], 1626)

    def test_storage_covers_every_pilot(self):
        self.assertEqual(self.benchmark["total_activation_bytes"], 307061760)
        self.assertEqual(self.benchmark["total_activation_row_count"], 37480)
        self.assertAlmostEqual(
            self.benchmark["bytes_per_activation_row"], 8192.683, places=2
        )

    def test_reused_pilots_report_no_measured_time(self):
        rows = {row["trajectory_id"]: row for row in self.benchmark["per_pilot"]}
        self.assertFalse(rows["layout_00_ep9403"]["timing_measured"])
        self.assertIsNone(rows["layout_00_ep9403"]["measured_seconds"])
        self.assertTrue(rows["layout_01_ep9405"]["timing_measured"])

    def test_forecast_is_labelled_a_projection_not_a_run(self):
        forecast = forecast_queue(self.benchmark, trajectory_count=66)
        self.assertTrue(forecast["forecast_is_measured_projection_not_a_run"])
        self.assertEqual(forecast["target_trajectory_count"], 66)
        self.assertAlmostEqual(forecast["mean_frames_per_trajectory"], 187.4)
        self.assertGreater(forecast["projected_wall_seconds"], 0)

    def test_a_non_positive_forecast_target_is_refused(self):
        with self.assertRaises(PilotCertificationError):
            forecast_queue(self.benchmark, trajectory_count=0)


class CloseoutTests(unittest.TestCase):
    def setUp(self):
        self.certification = certify_ten_pilot_expansion(
            SESSION_ROOT, downstream_fold_manifest=_fold_manifest()
        )

    def _changes(self):
        return (
            PilotChange(
                change_id="A6-C01",
                summary="interface migration",
                classification=ChangeClass.INTERFACE_MIGRATION,
                commit="a5841be",
                review="consumer reratification",
            ),
            PilotChange(
                change_id="A6-C02",
                summary="defect correction",
                classification=ChangeClass.DEFECT_CORRECTION,
                commit="5a4a42f",
                review="internal",
            ),
        )

    def test_closeout_classifies_every_change(self):
        closeout = build_pilot_closeout(
            self.certification,
            self._changes(),
            locked_contract_path="docs/contracts/x.md",
            locked_contract_sha256="a" * 64,
        )
        self.assertEqual(closeout["status"], "CLOSED")
        self.assertEqual(closeout["change_count"], 2)
        self.assertEqual(closeout["result_changing_change_count"], 0)
        self.assertTrue(
            closeout["no_unresolved_alignment_schema_or_model_blocker"]
        )

    def test_a_scientific_change_is_flagged_result_changing(self):
        changes = (
            *self._changes(),
            PilotChange(
                change_id="A6-C99",
                summary="pooling rule changed",
                classification=ChangeClass.SCIENTIFIC_CHANGE,
                commit="deadbee",
                review="mentor approval required",
                supersedes_previous_runs=True,
            ),
        )
        closeout = build_pilot_closeout(
            self.certification,
            changes,
            locked_contract_path="docs/contracts/x.md",
            locked_contract_sha256="a" * 64,
        )
        self.assertEqual(closeout["result_changing_change_count"], 1)
        self.assertTrue(closeout["scientific_change_requires_mentor_approval"])
        self.assertTrue(
            closeout["result_changing_changes"][0]["supersedes_previous_runs"]
        )

    def test_a_closeout_without_changes_is_refused(self):
        with self.assertRaises(PilotCertificationError) as caught:
            build_pilot_closeout(
                self.certification,
                (),
                locked_contract_path="docs/contracts/x.md",
                locked_contract_sha256="a" * 64,
            )
        self.assertIs(
            caught.exception.code, PilotCertificationErrorCode.UNCLASSIFIED_CHANGE
        )

    def test_remaining_blockers_change_the_status(self):
        closeout = build_pilot_closeout(
            self.certification,
            self._changes(),
            locked_contract_path="docs/contracts/x.md",
            locked_contract_sha256="a" * 64,
            remaining_blockers=({"blocker_id": "X", "owner": "person_c_data"},),
        )
        self.assertEqual(closeout["status"], "CLOSED_WITH_BLOCKERS")
        self.assertFalse(
            closeout["no_unresolved_alignment_schema_or_model_blocker"]
        )


class CommittedPackageTests(unittest.TestCase):
    """The published Step 6.7/6.8 package must match what the code produces."""

    def test_published_certification_matches_a_fresh_certification(self):
        published = json.loads(
            (
                ROOT
                / "docs"
                / "status"
                / "person_a_phase6_closeout_v0_1"
                / "step_6_7_certification.json"
            ).read_text(encoding="utf-8")
        )
        fresh = certify_ten_pilot_expansion(
            SESSION_ROOT, downstream_fold_manifest=_fold_manifest()
        )
        self.assertEqual(published["status"], fresh["status"])
        self.assertEqual(published["cardinality"], fresh["cardinality"])
        self.assertEqual(published["downstream_joins"], fresh["downstream_joins"])
        self.assertEqual(published["activation_index"], fresh["activation_index"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
