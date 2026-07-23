"""C5.3-C5.5 tests: detector import, final flag + quarantine, stable events."""

import pandas as pd
import pytest

import mineocclude.contracts  # noqa: F401  (pre-existing import-order cycle)
from mineocclude.data.visibility import (
    EVENT_RULE_VERSION,
    QUARANTINE_GEO_HIDDEN_DET_VISIBLE,
    QUARANTINE_GEO_VISIBLE_DET_HIDDEN,
    QUARANTINE_INVALID_GEOMETRY,
    QUARANTINE_MISSING_DETECTOR,
    QUARANTINE_NONE,
    SUPPORTED_DETECTION_SCHEMA,
    disagreement_summary,
    finalize_visibility,
    import_detector_records,
    stabilize,
    visibility_events,
)


def _frame_map(n=4, trajectory_id="layout_01_ep1"):
    return pd.DataFrame({
        "trajectory_id": [trajectory_id] * n,
        "model_frame_idx": list(range(n)),
        "layout_id": ["layout_01"] * n,
    })


def _detector_document(records):
    return {
        "detection_schema_version": SUPPORTED_DETECTION_SCHEMA,
        "detector_version": "magenta_detector_v1",
        "records": records,
    }


def _record(trajectory_id, idx, status):
    return {
        "detection_id": f"det_{idx}",
        "trajectory_id": trajectory_id,
        "model_frame_idx": idx,
        "status": status,
        "detector_version": "magenta_detector_v1",
        "threshold_version": "threshold_v1",
        "centroid_xy": [1.0, 2.0] if status == "detected" else None,
        "area_pixels": 10 if status == "detected" else 0,
        "bounding_box_xyxy": [0, 0, 2, 2] if status == "detected" else None,
        "rejection_reason": None,
    }


class TestDetectorImport:
    def test_one_to_one_join_preserves_provenance(self):
        fm = _frame_map(3)
        statuses = ["detected", "not_detected", "detected"]
        doc = _detector_document(
            [_record("layout_01_ep1", i, s) for i, s in enumerate(statuses)]
        )
        out, report = import_detector_records(doc, fm)
        assert report.accepted, report.problems
        assert list(out["empirical_visible"]) == [True, False, True]
        assert set(out["detector_id"]) == {"magenta_detector_v1"}
        assert list(out["detector_threshold_version"]) == ["threshold_v1"] * 3

    def test_missing_record_is_a_visible_problem(self):
        fm = _frame_map(3)
        doc = _detector_document(
            [_record("layout_01_ep1", i, "detected") for i in (0, 2)]
        )
        out, report = import_detector_records(doc, fm)
        assert not report.accepted
        assert out is None
        assert any("missing detector record" in p for p in report.problems)

    def test_wrong_schema_version_rejects(self):
        fm = _frame_map(1)
        doc = _detector_document([_record("layout_01_ep1", 0, "detected")])
        doc["detection_schema_version"] = "someone-elses-schema"
        out, report = import_detector_records(doc, fm)
        assert not report.accepted and out is None

    def test_duplicate_record_rejects(self):
        fm = _frame_map(2)
        doc = _detector_document([
            _record("layout_01_ep1", 0, "detected"),
            _record("layout_01_ep1", 0, "detected"),
            _record("layout_01_ep1", 1, "detected"),
        ])
        out, report = import_detector_records(doc, fm)
        assert not report.accepted
        assert any("duplicate detector record" in p for p in report.problems)


class TestFinalFlag:
    def test_and_rule_and_quarantine_categories(self):
        fm = pd.DataFrame({
            "layout_id": ["layout_01"] * 5,
            "geometric_visible": [True, True, False, None, False],
            "empirical_visible": [True, False, True, True, None],
        })
        out = finalize_visibility(fm)
        assert list(out["visible_flag"]) == [True, False, False, False, False]
        assert list(out["quarantine_category"]) == [
            QUARANTINE_NONE,
            QUARANTINE_GEO_VISIBLE_DET_HIDDEN,
            QUARANTINE_GEO_HIDDEN_DET_VISIBLE,
            QUARANTINE_INVALID_GEOMETRY,
            QUARANTINE_MISSING_DETECTOR,
        ]
        assert list(out["visibility_quarantine"]) == [False, True, True, True, True]
        # Raw channels are preserved unchanged.
        assert list(out["geometric_visible"])[:3] == [True, True, False]

    def test_disagreement_summary_counts(self):
        fm = finalize_visibility(pd.DataFrame({
            "layout_id": ["layout_01", "layout_01", "layout_02"],
            "geometric_visible": [True, True, False],
            "empirical_visible": [True, False, True],
        }))
        summary = disagreement_summary(fm)
        assert summary["total"][QUARANTINE_NONE] == 1
        assert summary["total"][QUARANTINE_GEO_VISIBLE_DET_HIDDEN] == 1
        assert summary["by_layout"]["layout_02"][
            QUARANTINE_GEO_HIDDEN_DET_VISIBLE
        ] == 1


class TestEvents:
    def test_clean_event(self):
        visible = [True] * 4 + [False] * 5 + [True] * 4
        result = visibility_events(visible)
        assert result["rule_version"] == EVENT_RULE_VERSION
        assert result["n_events"] == 1
        event = result["events"][0]
        assert event["onset_idx"] == 4
        assert event["reveal_idx"] == 9
        assert event["hidden_frames"] == 5
        assert event["hidden_seconds"] == pytest.approx(0.25)
        assert not result["multiple_events"]
        assert not result["missing_reveal"]

    def test_one_frame_flicker_creates_no_event(self):
        visible = [True] * 4 + [False] + [True] * 4
        result = visibility_events(visible, stability=2)
        assert result["n_events"] == 0
        # The raw flicker is preserved as an onset candidate for audit.
        assert result["raw_onset_candidates"] == [4]

    def test_repeated_flicker_within_event_does_not_split_it(self):
        visible = [True] * 3 + [False, False, True, False, False] + [True] * 3
        result = visibility_events(visible, stability=2)
        assert result["n_events"] == 1
        assert result["events"][0]["onset_idx"] == 3
        assert result["events"][0]["reveal_idx"] == 8

    def test_missing_reveal_is_flagged(self):
        visible = [True] * 3 + [False] * 5
        result = visibility_events(visible)
        assert result["n_events"] == 1
        assert result["events"][0]["reveal_idx"] is None
        assert result["missing_reveal"]

    def test_multiple_events_are_flagged(self):
        visible = ([True] * 3 + [False] * 3 + [True] * 3
                   + [False] * 3 + [True] * 3)
        result = visibility_events(visible)
        assert result["n_events"] == 2
        assert result["multiple_events"]

    def test_stabilize_preserves_length_and_raw_input(self):
        raw = [True, True, False, True, True, False, False, True, True]
        stable = stabilize(raw, stability=2)
        assert len(stable) == len(raw)
        assert stable == [True, True, True, True, True,
                          False, False, True, True]
        # stabilize returns a new list; raw is untouched.
        assert raw[2] is False

    def test_empty_sequence(self):
        assert visibility_events([])["n_events"] == 0
        assert stabilize([]) == []
