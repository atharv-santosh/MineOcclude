from __future__ import annotations

import copy
import hashlib
import json
import unittest
from pathlib import Path

from mineocclude.experiments.registry import formatted_json_bytes
from mineocclude.vision.homography import (
    GROUND_CONTACT_LOCALIZATION_METHOD_VERSION,
    homography_from_record,
)
from mineocclude.vision.markers import (
    MARKER_COLOUR_GATES,
    MARKER_DETECTOR_VERSION,
)
from mineocclude.vision.png_decode import PNG_DECODER_VERSION
from scripts.correct_person_e_phase2_step2_4_evidence import (
    MARKER_ORDER,
    validate_correction_documents,
)

ROOT = Path(__file__).resolve().parents[2]
BASE_EVIDENCE = ROOT / "docs" / "status" / "person_e_phase2_v0_1"
EVIDENCE = (
    ROOT / "docs" / "status" / "person_e_phase2_step2_4_v0_2"
)
EXPECTED_DOCUMENTS = {
    "source_and_ground_contact_validation.json",
    "homography_correspondences.json",
    "homography_record.json",
    "localization_validation_report.json",
    "provenance_index.json",
    "phase2_status.json",
}


def load(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_all() -> dict[str, dict[str, object]]:
    return {
        name: load(EVIDENCE / name) for name in sorted(EXPECTED_DOCUMENTS)
    }


class TestPhase2Step24Correction(unittest.TestCase):
    def test_document_set_is_canonical_and_fail_closed(self) -> None:
        self.assertEqual(
            {path.name for path in EVIDENCE.glob("*.json")},
            EXPECTED_DOCUMENTS,
        )
        documents = load_all()
        validate_correction_documents(documents)
        for name, document in documents.items():
            with self.subTest(name=name):
                payload = (EVIDENCE / name).read_bytes()
                self.assertFalse(payload.startswith(b"\xef\xbb\xbf"))
                self.assertNotIn(b"\r\n", payload)
                self.assertEqual(payload, formatted_json_bytes(document))

    def test_all_pngs_and_ground_contact_pairs_are_identity_bound(self) -> None:
        source = load(EVIDENCE / "source_and_ground_contact_validation.json")
        frozen_split = load(BASE_EVIDENCE / "frozen_split_manifest.json")
        source_records = {
            row["frame_id"]: row for row in source["source_png_records"]
        }
        frozen_frames = {
            row["frame_id"]: row for row in frozen_split["frames"]
        }
        self.assertEqual(source["png_decoder_version"], PNG_DECODER_VERSION)
        self.assertEqual(len(source_records), 72)
        self.assertEqual(set(source_records), set(frozen_frames))
        for frame_id, record in source_records.items():
            with self.subTest(frame_id=frame_id):
                frozen = frozen_frames[frame_id]
                self.assertEqual(
                    record["source_frame_hash"],
                    frozen["source_frame_hash"],
                )
                self.assertEqual(
                    record["decoded_rgb_hash"],
                    frozen["decoded_rgb_hash"],
                )
        pairs = source["ground_contact_pairs"]
        self.assertEqual(len(pairs), 36)
        self.assertEqual(
            source["ground_contact_method_assessment"][
                "selected_method_version"
            ],
            GROUND_CONTACT_LOCALIZATION_METHOD_VERSION,
        )
        self.assertFalse(
            source["ground_contact_method_assessment"][
                "probe_targets_used_for_method_selection"
            ]
        )
        for pair in pairs:
            with self.subTest(frame_id=pair["visible"]["frame_id"]):
                visible = pair["visible"]
                background = pair["background"]
                self.assertEqual(
                    visible["layout_id"], background["layout_id"]
                )
                self.assertEqual(visible["split"], background["split"])
                self.assertEqual(
                    visible["source_frame_idx"],
                    background["source_frame_idx"],
                )
                for frame in (visible, background):
                    source_record = source_records[frame["frame_id"]]
                    self.assertEqual(
                        frame["source_frame_hash"],
                        source_record["source_frame_hash"],
                    )
                    self.assertEqual(
                        frame["decoded_rgb_hash"],
                        source_record["decoded_rgb_hash"],
                    )

    def test_public_markers_and_homographies_preserve_all_bindings(
        self,
    ) -> None:
        correspondences = load(
            EVIDENCE / "homography_correspondences.json"
        )
        homographies = load(EVIDENCE / "homography_record.json")
        self.assertEqual(
            correspondences["marker_detector_version"],
            MARKER_DETECTOR_VERSION,
        )
        self.assertEqual(
            correspondences["png_decoder_version"], PNG_DECODER_VERSION
        )
        self.assertEqual(
            correspondences["white_marker_gate"],
            list(MARKER_COLOUR_GATES["white"]),
        )
        self.assertEqual(correspondences["marker_order"], list(MARKER_ORDER))
        self.assertEqual(correspondences["corrected_layout_count"], 5)
        self.assertEqual(correspondences["blocked_layout_count"], 1)
        blocked = correspondences["blocked_layouts"][0]
        self.assertEqual(blocked["layout_id"], "layout_02")
        self.assertEqual(
            {
                failure["marker_role"]
                for failure in blocked["marker_failures"]
            },
            {"north_west", "north_east"},
        )
        self.assertEqual(
            [
                (result["marker_role"], result["status"])
                for result in blocked["marker_results"]
            ],
            [
                ("north_west", "rejected"),
                ("north_east", "rejected"),
                ("south_east", "accepted"),
                ("south_west", "accepted"),
            ],
        )
        self.assertEqual(
            len(blocked["declared_negative_frame_assessments"]), 6
        )
        for assessment in blocked["declared_negative_frame_assessments"]:
            self.assertEqual(
                set(assessment["rejected_marker_roles"]),
                {"north_west", "north_east"},
            )
        records = {
            record["layout_id"]: record
            for record in homographies["records"]
        }
        self.assertEqual(
            set(records),
            {"layout_00", "layout_01", "layout_03", "layout_04", "layout_05"},
        )
        for layout in correspondences["corrected_layouts"]:
            with self.subTest(layout_id=layout["layout_id"]):
                self.assertEqual(
                    [row["marker_role"] for row in layout["markers"]],
                    list(MARKER_ORDER),
                )
                record = records[layout["layout_id"]]
                self.assertEqual(
                    record["source_correspondence_hash"],
                    layout["correspondence_hash"],
                )
                homography = homography_from_record(record)
                self.assertEqual(
                    homography.canonical_camera_pose_id,
                    layout["canonical_camera_pose_id"],
                )
                self.assertEqual(
                    homography.resolution_id, "resolution_640x360_rgb8"
                )
                self.assertEqual(homography.image_width_px, 640)
                self.assertEqual(homography.image_height_px, 360)

    def test_independent_probes_remain_held_out_and_gate_fails(self) -> None:
        localization = load(
            EVIDENCE / "localization_validation_report.json"
        )
        self.assertEqual(localization["required_sample_count"], 36)
        self.assertEqual(localization["evaluated_sample_count"], 30)
        self.assertEqual(localization["blocked_sample_count"], 6)
        self.assertFalse(localization["all_required_probes_evaluated"])
        self.assertFalse(localization["probe_targets_used_for_fitting"])
        self.assertFalse(
            localization["probe_targets_used_for_method_selection"]
        )
        self.assertFalse(localization["evaluated_subset_gate_passed"])
        self.assertFalse(localization["planning_gate_passed"])
        records = localization["records"]
        self.assertEqual(len(records), 30)
        self.assertEqual(
            {row["split"] for row in records}, {"calibration", "heldout"}
        )
        self.assertEqual(
            sum(row["split"] == "calibration" for row in records), 15
        )
        self.assertEqual(
            sum(row["split"] == "heldout" for row in records), 15
        )
        self.assertNotIn(
            "layout_02", {row["layout_id"] for row in records}
        )
        self.assertGreater(
            localization[
                "median_absolute_wall_parallel_error_blocks"
            ],
            localization["required_gate"][
                "maximum_median_absolute_wall_parallel_error_blocks"
            ],
        )
        self.assertGreaterEqual(
            localization["p95_absolute_wall_parallel_error_blocks"],
            localization["required_gate"][
                "maximum_p95_absolute_wall_parallel_error_blocks_exclusive"
            ],
        )

    def test_source_hash_and_correspondence_order_tampering_is_rejected(
        self,
    ) -> None:
        documents = load_all()
        tampered_hash = copy.deepcopy(documents)
        tampered_hash["source_and_ground_contact_validation.json"][
            "source_png_records"
        ][0]["source_frame_hash"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "source binding"):
            validate_correction_documents(tampered_hash)

        tampered_order = copy.deepcopy(documents)
        tampered_order["homography_correspondences.json"][
            "corrected_layouts"
        ][0]["markers"].reverse()
        with self.assertRaisesRegex(ValueError, "canonical ordering"):
            validate_correction_documents(tampered_order)

    def test_provenance_retains_the_failed_baseline_exactly(self) -> None:
        provenance = load(EVIDENCE / "provenance_index.json")
        retained = provenance["superseded_step2_4_evidence_retained"]
        for stem, name in (
            ("homography_correspondences", "homography_correspondences.json"),
            ("homography_record", "homography_record.json"),
            (
                "localization_validation_report",
                "localization_validation_report.json",
            ),
        ):
            with self.subTest(name=name):
                digest = hashlib.sha256(
                    (BASE_EVIDENCE / name).read_bytes()
                ).hexdigest()
                self.assertEqual(retained[f"{stem}_hash"], digest)


if __name__ == "__main__":
    unittest.main()
