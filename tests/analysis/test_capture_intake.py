from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from mineocclude.analysis.capture_intake import (
    CaptureIntakeError,
    CaptureSource,
    build_capture_intake_bundle,
)
from mineocclude.analysis.manifests import sha256_file, sha256_value
from mineocclude.analysis.selection import selections_from_condition_source


ROOT = Path(__file__).resolve().parents[2]
SOURCE_MANIFEST = (
    ROOT / "configs" / "analysis" / "person_b_phase6_c_sources.json"
)


def _sources() -> tuple[list[CaptureSource], dict]:
    source_manifest = json.loads(SOURCE_MANIFEST.read_text(encoding="utf-8"))
    sources: list[CaptureSource] = []
    for entry in source_manifest["capture_packages"]:
        path = ROOT / entry["path"]
        sources.append(
            CaptureSource(
                path=entry["path"],
                package=json.loads(path.read_text(encoding="utf-8")),
                literal_sha256=sha256_file(path),
                sidecar_sha256=Path(str(path) + ".sha256")
                .read_text(encoding="ascii")
                .strip(),
            )
        )
    return sources, source_manifest


def test_real_person_c_capture_set_is_authenticated_and_classified() -> None:
    sources, source_manifest = _sources()
    bundle = build_capture_intake_bundle(
        sources,
        source_branch=source_manifest["source_branch"],
        source_commit=source_manifest["source_commit"],
        artifact_id="test_person_c_intake",
        code_sha="a" * 40,
    )

    report = bundle.report
    assert report["package_count"] == 16
    assert report["coordinate_frame_count"] == 15
    assert report["hidden_layout_ids"] == [
        "layout_00",
        "layout_01",
        "layout_02",
        "layout_03",
        "layout_04",
        "layout_05",
    ]
    assert report["visible_control_layout_ids"] == [
        "layout_00",
        "layout_01",
        "layout_02",
        "layout_03",
        "layout_04",
    ]
    assert (
        report["scope_limits"]["visible_control_evidence"]
        == "eligible_for_grouped_oof"
    )
    assert report["scope_limits"]["grouped_oof_min_layouts"] == 5
    assert (
        report["phase_readiness"]["step_6_4"]
        == "blocked_on_person_a_activation_handoff"
    )
    assert report["c_only_oracle_math_audit"]["status"] == "pass"
    assert (
        report["c_only_oracle_math_audit"][
            "maximum_recursive_closed_form_error"
        ]
        <= 1e-6
    )
    assert (
        report["c_only_oracle_math_audit"]["fixed_tau_q_sensitivity"][
            "comparison_count"
        ]
        > 0
    )
    no_sheep = next(
        row
        for row in report["package_records"]
        if row["condition"] == "occluder_only_no_sheep"
    )
    assert no_sheep["classification"] == "no_object_not_oracle_eligible"
    assert no_sheep["coordinate_frame_id"] is None

    axes = {
        tuple(frame["wall_parallel_positive_unit_vector_world_xyz"])
        for frame in bundle.coordinate_frames
    }
    assert axes == {(1.0, 0.0, 0.0), (0.0, 0.0, 1.0)}
    assert all(
        frame["adapter_signoff"] == {"person_b": True, "person_c": True}
        for frame in bundle.coordinate_frames
    )
    records_by_trajectory = {
        record["trajectory_id"]: record for record in report["package_records"]
    }
    assert all(
        records_by_trajectory[
            frame["coordinate_frame_id"]
            .removeprefix("person_b_c_live_")
            .removesuffix("_v1")
        ]["coordinate_frame_document_hash"]
        == sha256_value(frame)
        for frame in bundle.coordinate_frames
    )
    assert {
        frame["coordinate_frame_id"]
        .removeprefix("person_b_c_live_")
        .removesuffix("_v1")
        for frame in bundle.coordinate_frames
    } == {
        record["trajectory_id"]
        for record in report["package_records"]
        if record["coordinate_frame_id"] is not None
    }


def test_real_condition_source_freezes_only_eligible_rows() -> None:
    sources, source_manifest = _sources()
    bundle = build_capture_intake_bundle(
        sources,
        source_branch=source_manifest["source_branch"],
        source_commit=source_manifest["source_commit"],
        artifact_id="test_person_c_selection",
        code_sha="b" * 40,
    )

    rows = bundle.condition_selection_source["rows"]
    assert len(rows) == 2_456
    assert sum(
        row["analysis_scopes"] == ["hidden_mean", "hidden_spread"]
        for row in rows
    ) == 1_456
    assert sum(
        row["analysis_scopes"] == ["visible_no_wall_control"]
        for row in rows
    ) == 1_000
    control_rows = [
        row
        for row in rows
        if row["analysis_scopes"] == ["visible_no_wall_control"]
    ]
    assert Counter(row["layout_id"] for row in control_rows) == {
        "layout_00": 200,
        "layout_01": 200,
        "layout_02": 200,
        "layout_03": 200,
        "layout_04": 200,
    }
    assert all("layout_05_ep9422" != row["trajectory_id"] for row in rows)
    assert len(selections_from_condition_source(bundle.condition_selection_source)) == (
        3_912
    )


def test_checksum_mismatch_fails_before_scientific_intake() -> None:
    sources, source_manifest = _sources()
    first = sources[0]
    sources[0] = CaptureSource(
        path=first.path,
        package=first.package,
        literal_sha256=first.literal_sha256,
        sidecar_sha256="0" * 64,
    )
    with pytest.raises(CaptureIntakeError, match="checksum sidecar"):
        build_capture_intake_bundle(
            sources,
            source_branch=source_manifest["source_branch"],
            source_commit=source_manifest["source_commit"],
            artifact_id="test_bad_checksum",
            code_sha="c" * 40,
        )


def test_duplicate_source_path_fails_before_scientific_intake() -> None:
    sources, source_manifest = _sources()
    sources.append(sources[0])
    with pytest.raises(CaptureIntakeError, match="Duplicate capture source path"):
        build_capture_intake_bundle(
            sources,
            source_branch=source_manifest["source_branch"],
            source_commit=source_manifest["source_commit"],
            artifact_id="test_duplicate_capture",
            code_sha="d" * 40,
        )


def test_duplicate_trajectory_fails_before_scientific_intake() -> None:
    sources, source_manifest = _sources()
    first = sources[0]
    sources.append(
        CaptureSource(
            path=f"copy/{first.path}",
            package=first.package,
            literal_sha256=first.literal_sha256,
            sidecar_sha256=first.sidecar_sha256,
        )
    )
    with pytest.raises(CaptureIntakeError, match="Duplicate trajectory_id"):
        build_capture_intake_bundle(
            sources,
            source_branch=source_manifest["source_branch"],
            source_commit=source_manifest["source_commit"],
            artifact_id="test_duplicate_trajectory",
            code_sha="e" * 40,
        )
