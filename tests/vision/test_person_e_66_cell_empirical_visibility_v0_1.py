"""Focused Person E tests for the 66-cell empirical-visibility handoff.

Covers Person C request intake, Person B coordinate-frame co-sign intake, the
66-trajectory and exact 2468-key reconciliations, source-frame hash
verification, the frozen detector authority and its deterministic behavior,
the output schema, duplicate/missing rejection, the E-to-C handoff, and
deterministic serialization.

No U4 measurement is performed here.
"""

from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from mineocclude.operations.person_e_66_cell_empirical_visibility import (
    ACCEPTED_GEOMETRY_SHA256,
    B_COSIGN_SHA256,
    C_ACCEPTED_MANIFEST_SHA256,
    C_CAPTURE_PACKAGE_MANIFEST_SHA256,
    C_COORDINATE_FRAME_AUTHORITY_SHA256,
    C_FRAME_UNIVERSE_SHA256,
    C_PREPROCESS_SHA256,
    C_REQUEST_MANIFEST_SHA256,
    CANONICAL_FRAME_HEIGHT,
    CANONICAL_FRAME_WIDTH,
    DETECTOR_IDENTITY_SHA256,
    DETECTOR_STATUS_NOT_APPLICABLE,
    DETECTOR_STATUS_UNREADABLE,
    DETECTOR_VERSION,
    EMPIRICAL_RECORD_FIELDS,
    EXPECTED_APPLICABLE_COUNT,
    EXPECTED_FRAME_IDENTITY_COUNT,
    EXPECTED_NOT_APPLICABLE_COUNT,
    EXPECTED_TRAJECTORY_COUNT,
    LAYOUT_IDS,
    PERSON_B_COMMIT,
    PERSON_C_COMMIT,
    EmpiricalVisibilityError,
    accounting,
    build_record,
    canonical_frame_rgb,
    detector_arguments,
    jsonl_bytes,
    load_accepted_geometry,
    load_canonical_rule,
    load_coordinate_frame_authority,
    load_frame_universe,
    load_person_b_cosign,
    load_person_c_request,
    sha256_bytes,
    validate_record,
    verify_frozen_detector,
)

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "data/handoff_c/person_e_66_cell_empirical_visibility_v0_1"
RECORDS_PATH = PACKAGE / "empirical_visibility_records.jsonl"


def load_records() -> list[dict]:
    raw = RECORDS_PATH.read_bytes()
    assert raw.endswith(b"\n")
    return [json.loads(line) for line in raw.decode("utf-8").splitlines()]


def load_document(name: str) -> dict:
    return json.loads((PACKAGE / name).read_text("utf-8"))


class TestPersonCRequestIntake(unittest.TestCase):
    def test_request_binds_the_pinned_authorities(self) -> None:
        request = load_person_c_request(ROOT)
        self.assertEqual(
            request["person_c_accepted_manifest_sha256"], C_ACCEPTED_MANIFEST_SHA256
        )
        self.assertEqual(request["accepted_geometry_sha256"], ACCEPTED_GEOMETRY_SHA256)
        self.assertEqual(request["frame_universe_sha256"], C_FRAME_UNIVERSE_SHA256)
        self.assertEqual(
            request["expected_response_key"], ["trajectory_id", "model_frame_idx"]
        )

    def test_request_declares_exactly_66_trajectories(self) -> None:
        request = load_person_c_request(ROOT)
        self.assertEqual(request["trajectory_count"], EXPECTED_TRAJECTORY_COUNT)
        self.assertEqual(
            len(set(request["trajectory_ids"])), EXPECTED_TRAJECTORY_COUNT
        )

    def test_request_declares_exactly_2468_model_frame_identities(self) -> None:
        request = load_person_c_request(ROOT)
        self.assertEqual(
            request["expected_model_frame_identity_count"],
            EXPECTED_FRAME_IDENTITY_COUNT,
        )

    def test_person_c_did_not_supply_or_tune_the_detector(self) -> None:
        request = load_person_c_request(ROOT)
        for field in (
            "person_c_ran_detector",
            "person_c_tuned_detector",
            "person_c_supplied_detector_thresholds",
            "person_c_supplied_detector_version",
            "person_c_empirical_channel_supplied",
        ):
            with self.subTest(field=field):
                self.assertFalse(request[field])


class TestFrameUniverseReconciliation(unittest.TestCase):
    def test_universe_has_exactly_2468_unique_keys_over_66_trajectories(self) -> None:
        rows = load_frame_universe(ROOT)
        keys = [(row["trajectory_id"], row["model_frame_idx"]) for row in rows]
        self.assertEqual(len(rows), EXPECTED_FRAME_IDENTITY_COUNT)
        self.assertEqual(len(set(keys)), EXPECTED_FRAME_IDENTITY_COUNT)
        self.assertEqual(
            len({row["trajectory_id"] for row in rows}), EXPECTED_TRAJECTORY_COUNT
        )

    def test_applicability_accounting_matches_person_c(self) -> None:
        rows = load_frame_universe(ROOT)
        applicable = sum(1 for row in rows if row["detector_applicable"])
        self.assertEqual(applicable, EXPECTED_APPLICABLE_COUNT)
        self.assertEqual(
            len(rows) - applicable, EXPECTED_NOT_APPLICABLE_COUNT
        )

    def test_every_universe_layout_is_a_contract_layout(self) -> None:
        rows = load_frame_universe(ROOT)
        self.assertEqual(
            {row["layout_id"] for row in rows} - set(LAYOUT_IDS), set()
        )

    def test_declared_source_paths_exist(self) -> None:
        rows = load_frame_universe(ROOT)
        missing = [
            row["source_frame_runtime_path"]
            for row in rows
            if not Path(row["source_frame_runtime_path"]).is_file()
        ]
        self.assertEqual(missing, [])


class TestSourceFrameHashVerification(unittest.TestCase):
    def test_source_bytes_match_person_c_for_a_sample(self) -> None:
        rows = load_frame_universe(ROOT)
        sample = rows[:: max(1, len(rows) // 40)]
        for row in sample:
            with self.subTest(key=(row["trajectory_id"], row["model_frame_idx"])):
                payload = Path(row["source_frame_runtime_path"]).read_bytes()
                self.assertEqual(
                    sha256_bytes(payload), row["source_frame_sha256"]
                )
                self.assertEqual(len(payload), row["source_frame_byte_size"])

    def test_run_receipt_verified_every_source_frame(self) -> None:
        verification = load_document("production_run_receipt.json")[
            "source_frame_verification"
        ]
        self.assertEqual(
            verification["source_frame_count"], EXPECTED_FRAME_IDENTITY_COUNT
        )
        self.assertEqual(
            verification["sha256_verified_frame_count"], EXPECTED_FRAME_IDENTITY_COUNT
        )
        self.assertEqual(verification["source_frame_hash_mismatch_count"], 0)
        self.assertEqual(verification["unreadable_frame_count"], 0)


class TestPersonBCoSignIntake(unittest.TestCase):
    def test_cosign_is_valid_over_the_same_six_frames(self) -> None:
        frames = load_coordinate_frame_authority(ROOT)
        cosign = load_person_b_cosign(ROOT, frames)
        self.assertEqual(cosign["person_c_commit"], PERSON_C_COMMIT)
        self.assertEqual(
            [frame["layout_id"] for frame in cosign["cosigned_frames"]],
            list(LAYOUT_IDS),
        )

    def test_cosign_does_not_alter_the_coordinate_frame_authority_hash(self) -> None:
        frames = load_coordinate_frame_authority(ROOT)
        cosign = load_person_b_cosign(ROOT, frames)
        self.assertEqual(
            cosign["person_c_coordinate_frame_sha256"],
            C_COORDINATE_FRAME_AUTHORITY_SHA256,
        )
        self.assertEqual(
            cosign["input_manifest_hash"], C_COORDINATE_FRAME_AUTHORITY_SHA256
        )
        self.assertFalse(cosign["person_c_bytes_modified"])
        self.assertFalse(cosign["person_c_branch_merged"])

    def test_cosign_rejects_a_mutated_coordinate_frame(self) -> None:
        frames = copy.deepcopy(load_coordinate_frame_authority(ROOT))
        frames["frames"][0]["coordinate_frame_hash"] = "0" * 64
        with self.assertRaises(EmpiricalVisibilityError):
            load_person_b_cosign(ROOT, frames)


class TestFrozenDetectorAuthority(unittest.TestCase):
    def test_detector_identity_is_unchanged(self) -> None:
        detector = verify_frozen_detector(ROOT)
        self.assertEqual(detector["identity_sha256"], DETECTOR_IDENTITY_SHA256)
        self.assertEqual(detector["version"], DETECTOR_VERSION)

    def test_detector_applicability_is_the_canonical_frame(self) -> None:
        applicability = verify_frozen_detector(ROOT)["applicability"]
        self.assertEqual(applicability["image_width_px"], CANONICAL_FRAME_WIDTH)
        self.assertEqual(applicability["image_height_px"], CANONICAL_FRAME_HEIGHT)
        self.assertEqual(
            applicability["mismatched_input_behavior"], "reject_fail_closed"
        )

    def test_settings_match_the_published_no_tuning_receipt(self) -> None:
        detector = verify_frozen_detector(ROOT)
        receipt = load_document("no_tuning_receipt.json")
        self.assertEqual(receipt["detector_version"], detector["version"])
        self.assertEqual(receipt["detector_settings_sha256"], detector["settings_sha256"])
        self.assertFalse(receipt["detector_retuned_on_66_cell_population"])
        self.assertFalse(receipt["new_detector_version_created_for_this_run"])
        self.assertFalse(
            receipt["threshold_or_config_change_after_outcome_inspection"]
        )
        self.assertTrue(receipt["detector_authority_predates_this_execution"])

    def test_canonical_derivation_rule_is_person_c_owned_and_pinned(self) -> None:
        binding = load_document("authority_binding.json")["canonical_derivative_rule"]
        self.assertEqual(binding["owner_role"], "person_c")
        self.assertEqual(binding["source_sha256"], C_PREPROCESS_SHA256)
        self.assertEqual(binding["source_commit"], PERSON_C_COMMIT)
        self.assertEqual(binding["canonical_width_pixels"], CANONICAL_FRAME_WIDTH)
        self.assertEqual(binding["canonical_height_pixels"], CANONICAL_FRAME_HEIGHT)


class TestDetectorDeterminism(unittest.TestCase):
    def test_same_frame_and_detector_give_an_identical_result(self) -> None:
        from mineocclude.vision.magenta import detect_magenta

        rows = load_frame_universe(ROOT)
        detector = verify_frozen_detector(ROOT)
        arguments = detector_arguments(detector["settings"])
        rule = load_canonical_rule(ROOT)
        sample = [rows[0], rows[len(rows) // 2], rows[-1]]
        for row in sample:
            with self.subTest(key=(row["trajectory_id"], row["model_frame_idx"])):
                first_rgb, first_digest = canonical_frame_rgb(
                    row["source_frame_runtime_path"], canonical_rule=rule
                )
                second_rgb, second_digest = canonical_frame_rgb(
                    row["source_frame_runtime_path"], canonical_rule=rule
                )
                self.assertEqual(first_digest, second_digest)
                self.assertEqual(first_rgb, second_rgb)
                self.assertEqual(
                    detect_magenta(first_rgb, **arguments),
                    detect_magenta(second_rgb, **arguments),
                )

    def test_published_records_reproduce_for_a_sample(self) -> None:
        from mineocclude.vision.magenta import detect_magenta

        rows = {
            (row["trajectory_id"], row["model_frame_idx"]): row
            for row in load_frame_universe(ROOT)
        }
        detector = verify_frozen_detector(ROOT)
        arguments = detector_arguments(detector["settings"])
        rule = load_canonical_rule(ROOT)
        records = load_records()
        applicable = [
            record for record in records if record["detector_applicable"]
        ]
        sample = applicable[:: max(1, len(applicable) // 12)]
        for record in sample:
            key = (record["trajectory_id"], record["model_frame_idx"])
            with self.subTest(key=key):
                rgb, digest = canonical_frame_rgb(
                    rows[key]["source_frame_runtime_path"], canonical_rule=rule
                )
                self.assertEqual(digest, record["canonical_frame_rgb_sha256"])
                result = detect_magenta(rgb, **arguments)
                self.assertEqual(result.status, record["detector_status"])
                self.assertEqual(
                    result.detected, record["empirical_magenta_visible"]
                )
                self.assertEqual(result.area_pixels, record["detected_area_pixels"])

    def test_determinism_receipt_covers_the_full_universe(self) -> None:
        receipt = load_document("determinism_receipt.json")
        self.assertTrue(receipt["detector_outcomes_identical_across_passes"])
        self.assertEqual(receipt["independent_pass_count"], 2)
        self.assertEqual(receipt["rerun_coverage"], "full_requested_universe")
        self.assertEqual(
            receipt["rerun_frame_count"], EXPECTED_FRAME_IDENTITY_COUNT
        )


class TestOutputSchemaAndAccounting(unittest.TestCase):
    def test_every_record_has_the_exact_schema_fields(self) -> None:
        schema = load_document("empirical_visibility_schema.json")
        self.assertEqual(schema["fields"], sorted(EMPIRICAL_RECORD_FIELDS))
        self.assertEqual(
            schema["canonical_join_key"], ["trajectory_id", "model_frame_idx"]
        )
        expected = sorted(EMPIRICAL_RECORD_FIELDS)
        offending = [
            index
            for index, record in enumerate(load_records())
            if sorted(record) != expected
        ]
        self.assertEqual(offending, [])

    def test_no_forbidden_channel_leaks_into_the_output(self) -> None:
        forbidden = set(
            load_document("empirical_visibility_schema.json")["forbidden_fields"]
        )
        for record in load_records():
            self.assertEqual(set(record) & forbidden, set())

    def test_every_record_is_a_coherent_explicit_status(self) -> None:
        for record in load_records():
            validate_record(record)

    def test_exact_2468_key_reconciliation_against_person_c(self) -> None:
        requested = [
            (row["trajectory_id"], row["model_frame_idx"])
            for row in load_frame_universe(ROOT)
        ]
        records = load_records()
        summary = accounting(requested, records)
        self.assertEqual(
            summary["requested_frame_count"], EXPECTED_FRAME_IDENTITY_COUNT
        )
        self.assertEqual(
            summary["processed_frame_count"], EXPECTED_FRAME_IDENTITY_COUNT
        )
        self.assertEqual(summary["duplicate_output_key_count"], 0)
        self.assertEqual(summary["missing_output_key_count"], 0)
        self.assertEqual(summary["extra_output_key_count"], 0)
        self.assertEqual(summary["failed_frame_count"], 0)
        self.assertEqual(
            summary["not_applicable_count"], EXPECTED_NOT_APPLICABLE_COUNT
        )
        self.assertEqual(
            summary["empirical_visible_count"] + summary["empirical_hidden_count"],
            EXPECTED_APPLICABLE_COUNT,
        )
        coverage = load_document("coverage_report.json")
        self.assertEqual({field: coverage[field] for field in summary}, summary)

    def test_records_echo_the_person_c_frame_identity(self) -> None:
        rows = {
            (row["trajectory_id"], row["model_frame_idx"]): row
            for row in load_frame_universe(ROOT)
        }
        mismatched = [
            (record["trajectory_id"], record["model_frame_idx"])
            for record in load_records()
            for row in [rows[(record["trajectory_id"], record["model_frame_idx"])]]
            if (
                record["source_frame_sha256"] != row["source_frame_sha256"]
                or record["source_frame_reference"] != row["source_frame_runtime_path"]
                or record["layout_id"] != row["layout_id"]
                or record["episode_id"] != row["episode_id"]
                or record["detector_applicable"] != row["detector_applicable"]
            )
        ]
        self.assertEqual(mismatched, [])

    def test_not_applicable_controls_are_explicit_nulls(self) -> None:
        controls = [
            record
            for record in load_records()
            if record["detector_status"] == DETECTOR_STATUS_NOT_APPLICABLE
        ]
        self.assertEqual(len(controls), EXPECTED_NOT_APPLICABLE_COUNT)
        for record in controls:
            self.assertIsNone(record["empirical_magenta_visible"])
            self.assertFalse(record["detector_applicable"])
        report = load_document("no_object_control_report.json")
        self.assertEqual(
            report["control_row_count"], EXPECTED_NOT_APPLICABLE_COUNT
        )
        self.assertEqual(report["detector_detected_magenta_in_control_count"], 0)


class TestDuplicateAndMissingRejection(unittest.TestCase):
    def test_duplicate_output_keys_are_counted(self) -> None:
        records = load_records()
        summary = accounting(
            [(r["trajectory_id"], r["model_frame_idx"]) for r in records],
            records + [records[0]],
        )
        self.assertEqual(summary["duplicate_output_key_count"], 1)

    def test_missing_output_keys_are_counted(self) -> None:
        records = load_records()
        summary = accounting(
            [(r["trajectory_id"], r["model_frame_idx"]) for r in records],
            records[1:],
        )
        self.assertEqual(summary["missing_output_key_count"], 1)

    def test_incoherent_records_fail_closed(self) -> None:
        record = next(
            r for r in load_records() if r["detector_status"] == "detected"
        )
        for field, value in (
            ("empirical_magenta_visible", False),
            ("centroid_x_px", None),
            ("detected_area_pixels", 10**9),
        ):
            with self.subTest(field=field):
                mutated = {**record, field: value}
                with self.assertRaises(EmpiricalVisibilityError):
                    validate_record(mutated)

    def test_unknown_detector_status_fails_closed(self) -> None:
        record = load_records()[0]
        with self.assertRaises(EmpiricalVisibilityError):
            validate_record({**record, "detector_status": "probably_visible"})

    def test_build_record_rejects_an_unexpected_field_set(self) -> None:
        row = load_frame_universe(ROOT)[0]
        outcome = {
            "area_pixels": None,
            "bounding_box_xyxy": None,
            "candidate_blob_count": 0,
            "canonical_frame_rgb_sha256": "0" * 64,
            "centroid_xy": None,
            "detector_status": DETECTOR_STATUS_UNREADABLE,
            "detector_status_reason": "synthetic",
            "empirical_magenta_visible": None,
            "selected_blob_fraction_of_threshold_matches": None,
            "threshold_match_pixels": None,
        }
        record = build_record(
            row,
            outcome,
            marker_authority_id="synthetic",
            marker_authority_sha256="0" * 64,
        )
        self.assertEqual(sorted(record), sorted(EMPIRICAL_RECORD_FIELDS))
        with self.assertRaises(EmpiricalVisibilityError):
            validate_record({**record, "extra_field": 1})


class TestDeterministicSerialization(unittest.TestCase):
    def test_records_file_is_compact_sorted_key_jsonl(self) -> None:
        self.assertEqual(jsonl_bytes(load_records()), RECORDS_PATH.read_bytes())

    def test_json_documents_are_deterministically_formatted(self) -> None:
        for path in sorted(PACKAGE.glob("*.json")):
            with self.subTest(file=path.name):
                document = json.loads(path.read_text("utf-8"))
                expected = (
                    json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True)
                    + "\n"
                ).encode("utf-8")
                self.assertEqual(path.read_bytes(), expected)

    def test_records_are_sorted_by_the_canonical_join_key(self) -> None:
        keys = [
            (record["trajectory_id"], record["model_frame_idx"])
            for record in load_records()
        ]
        self.assertEqual(keys, sorted(keys))

    def test_sha256_inventory_covers_the_package(self) -> None:
        inventory = load_document("sha256_inventory.json")
        published = {path.name for path in PACKAGE.iterdir() if path.is_file()}
        self.assertEqual(
            published, set(inventory["files"]) | {"sha256_inventory.json"}
        )
        for name, expected in inventory["files"].items():
            with self.subTest(file=name):
                self.assertEqual(
                    sha256_bytes((PACKAGE / name).read_bytes()), expected
                )


class TestEToCHandoff(unittest.TestCase):
    def handoff(self) -> dict:
        return load_document("e_to_c_empirical_visibility_handoff.json")

    def test_handoff_is_ready_and_binds_every_authority(self) -> None:
        handoff = self.handoff()
        self.assertTrue(handoff["E_TO_C_EMPIRICAL_VISIBILITY_READY"])
        self.assertEqual(handoff["canonical_join_key"], ["trajectory_id", "model_frame_idx"])
        self.assertEqual(handoff["person_c"]["commit"], PERSON_C_COMMIT)
        self.assertEqual(
            handoff["person_c"]["request_manifest_sha256"], C_REQUEST_MANIFEST_SHA256
        )
        self.assertEqual(
            handoff["person_c"]["accepted_manifest_sha256"], C_ACCEPTED_MANIFEST_SHA256
        )
        self.assertEqual(
            handoff["person_c"]["capture_package_manifest_sha256"],
            C_CAPTURE_PACKAGE_MANIFEST_SHA256,
        )
        self.assertEqual(handoff["person_b"]["commit"], PERSON_B_COMMIT)
        self.assertEqual(
            handoff["person_b"]["coordinate_frame_cosign_sha256"], B_COSIGN_SHA256
        )
        self.assertTrue(handoff["person_b"]["coordinate_frame_cosign_valid"])
        self.assertEqual(handoff["accepted_geometry_sha256"], ACCEPTED_GEOMETRY_SHA256)
        self.assertEqual(
            handoff["detector"]["identity_sha256"], DETECTOR_IDENTITY_SHA256
        )
        self.assertEqual(
            handoff["marker_layout_authority"]["accepted_geometry_sha256"],
            ACCEPTED_GEOMETRY_SHA256,
        )

    def test_handoff_binds_the_exact_2468_key_universe(self) -> None:
        handoff = self.handoff()
        self.assertEqual(
            handoff["frame_universe"]["model_frame_identity_count"],
            EXPECTED_FRAME_IDENTITY_COUNT,
        )
        self.assertEqual(
            handoff["frame_universe"]["trajectory_count"], EXPECTED_TRAJECTORY_COUNT
        )
        self.assertEqual(
            handoff["frame_universe"]["sha256"], C_FRAME_UNIVERSE_SHA256
        )

    def test_handoff_hash_matches_the_published_records(self) -> None:
        handoff = self.handoff()
        self.assertEqual(
            handoff["empirical_visibility_records_sha256"],
            sha256_bytes(RECORDS_PATH.read_bytes()),
        )
        self.assertEqual(
            (ROOT / handoff["empirical_visibility_records_path"]).resolve(),
            RECORDS_PATH.resolve(),
        )

    def test_handoff_declares_no_retuning_and_no_person_e_join(self) -> None:
        handoff = self.handoff()
        statement = handoff["no_retuning_statement"]
        self.assertIn(DETECTOR_IDENTITY_SHA256, statement)
        self.assertIn(
            "was read from, derived from, or adjusted by this population", statement
        )
        self.assertIn("before or after outcome inspection", statement)
        self.assertFalse(handoff["geometric_visible_computed_by_person_e"])
        self.assertFalse(handoff["visible_flag_computed_by_person_e"])
        self.assertEqual(handoff["strict_join_owner_after_response"], "person_c")

    def test_handoff_accounting_matches_the_records(self) -> None:
        summary = self.handoff()["accounting_summary"]
        requested = [
            (row["trajectory_id"], row["model_frame_idx"])
            for row in load_frame_universe(ROOT)
        ]
        self.assertEqual(summary, accounting(requested, load_records()))

    def test_handoff_reports_failures_and_missingness_explicitly(self) -> None:
        failures = self.handoff()["failures_and_missingness"]
        self.assertEqual(
            set(failures.values()), {0}, f"unexpected non-zero failures: {failures}"
        )


class TestU4StructuralReportIsReportOnly(unittest.TestCase):
    def test_report_does_not_measure_or_reinterpret(self) -> None:
        report = load_document("u4_structural_report.json")
        for field in (
            "u4_measurement_performed",
            "reveal_window_rules_relaxed",
            "event_ids_invented",
            "frames_recollected_in_this_task",
            "heldout_partition_reinterpreted",
            "person_c_finding_reinterpreted",
        ):
            with self.subTest(field=field):
                self.assertFalse(report[field])

    def test_report_preserves_person_c_and_person_b_authorities(self) -> None:
        report = load_document("u4_structural_report.json")
        self.assertFalse(report["person_c_current_66_cell_u4_reveal_eligible"])
        self.assertTrue(report["person_c_u4_supplemental_capture_required"])
        self.assertEqual(report["heldout_partition_owner"], "person_b")
        self.assertEqual(report["heldout_layout_ids"], ["layout_03", "layout_04"])
        window = report["frozen_reveal_window_requirement"]
        self.assertEqual(window["reveal_window_owner"], "person_b")
        self.assertEqual(window["required_pre_frames"], 20)
        self.assertEqual(window["required_post_frames"], 20)
        self.assertEqual(window["required_centred_span_frames"], 41)
        self.assertFalse(window["reveal_may_be_final_frame"])

    def test_transitions_are_derived_only_from_the_empirical_channel(self) -> None:
        report = load_document("u4_structural_report.json")
        records = {
            (record["trajectory_id"], record["model_frame_idx"]): record
            for record in load_records()
        }
        for transition in report["transitions"]:
            key = (transition["trajectory_id"], transition["reveal_model_frame_idx"])
            with self.subTest(key=key):
                self.assertTrue(records[key]["empirical_magenta_visible"])


class TestAcceptedGeometryIntake(unittest.TestCase):
    def test_accepted_geometry_hash_and_layouts(self) -> None:
        geometry = load_accepted_geometry(ROOT)
        self.assertEqual(
            [layout["layout_id"] for layout in geometry["layouts"]], list(LAYOUT_IDS)
        )


if __name__ == "__main__":
    unittest.main()
