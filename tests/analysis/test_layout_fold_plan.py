from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from mineocclude.analysis.config import hash_core_analysis_config
from mineocclude.analysis.layout_fold_plan import (
    FOLD_ASSIGNMENT_SOURCE,
    LayoutFoldPlanError,
    bind_frame_fold_artifacts_to_layout_plan,
    build_layout_fold_plan,
    validate_frame_fold_manifest_against_layout_plan,
    validate_layout_fold_plan,
    validate_layout_fold_plan_against_sources,
)
from mineocclude.analysis.manifests import (
    seal_artifact,
    sha256_file,
)
from mineocclude.probes.splits import (
    assign_layout_grouped_folds,
    build_fold_manifest,
)


ROOT = Path(__file__).resolve().parents[2]
INTAKE_DIRECTORY = ROOT / "data" / "person_b" / "phase6_c_intake"
CONDITION_SOURCE_PATH = INTAKE_DIRECTORY / "condition_selection_source.json"
INTAKE_REPORT_PATH = INTAKE_DIRECTORY / "capture_intake_report.json"
SAVED_PLAN_PATH = INTAKE_DIRECTORY / "layout_fold_plan.json"
SOURCE_MANIFEST_PATH = (
    ROOT / "configs" / "analysis" / "person_b_phase6_c_sources.json"
)


def _sources() -> tuple[dict, dict]:
    return (
        json.loads(CONDITION_SOURCE_PATH.read_text(encoding="utf-8")),
        json.loads(INTAKE_REPORT_PATH.read_text(encoding="utf-8")),
    )


def _plan() -> dict:
    condition_source, intake_report = _sources()
    return build_layout_fold_plan(
        condition_source,
        intake_report,
        artifact_id="test_real_c_layout_fold_plan",
        condition_source_file_hash=sha256_file(CONDITION_SOURCE_PATH),
        capture_intake_file_hash=sha256_file(INTAKE_REPORT_PATH),
    )


def _real_frame_manifest(rows: list[dict]) -> dict:
    manifest = build_fold_manifest(
        rows,
        artifact_id="test_real_frame_folds",
        code_sha="a" * 40,
        input_manifest_hash="b" * 64,
    )
    payload = dict(manifest)
    payload.pop("artifact_hash")
    payload.update({"synthetic": False, "scientific_use": "permitted"})
    return seal_artifact(payload)


def test_real_c_rows_freeze_all_layouts_and_scopes_before_person_a() -> None:
    plan = _plan()
    validate_layout_fold_plan(plan)

    assert plan["person_a_artifacts_used"] is False
    assert plan["outcome_fields_used"] is False
    assert plan["accepted_row_count"] == 2_456
    assert plan["trajectory_count"] == 15
    assert plan["layout_count"] == 6
    assert plan["layout_assignments"] == [
        {"layout_id": "layout_00", "fold_idx": 1},
        {"layout_id": "layout_01", "fold_idx": 2},
        {"layout_id": "layout_02", "fold_idx": 4},
        {"layout_id": "layout_03", "fold_idx": 0},
        {"layout_id": "layout_04", "fold_idx": 3},
        {"layout_id": "layout_05", "fold_idx": 4},
    ]
    assert all(
        item["fold_indices"] == [0, 1, 2, 3, 4]
        for item in plan["scope_fold_coverage"]
    )


def test_real_plan_rebuilds_exactly_from_checked_c_sources() -> None:
    condition_source, intake_report = _sources()
    saved = json.loads(SAVED_PLAN_PATH.read_text(encoding="utf-8"))
    validate_layout_fold_plan_against_sources(
        saved,
        condition_source,
        intake_report,
        condition_source_file_hash=sha256_file(CONDITION_SOURCE_PATH),
        capture_intake_file_hash=sha256_file(INTAKE_REPORT_PATH),
    )


def test_plan_matches_all_target_present_frames_in_accepted_c_packages() -> None:
    source_manifest = json.loads(
        SOURCE_MANIFEST_PATH.read_text(encoding="utf-8")
    )
    rows: list[dict] = []
    for entry in source_manifest["capture_packages"]:
        package = json.loads(
            (ROOT / entry["path"]).read_text(encoding="utf-8")
        )
        if package["condition"] == "occluder_only_no_sheep":
            continue
        rows.extend(
            {
                "trajectory_id": frame["trajectory_id"],
                "model_frame_idx": frame["model_frame_idx"],
                "layout_id": package["layout_id"],
                "status": "accepted",
            }
            for frame in package["streams"]["frame_map"]
        )
    assignment = assign_layout_grouped_folds(rows)
    assert [
        {"layout_id": layout_id, "fold_idx": fold_idx}
        for layout_id, fold_idx in sorted(assignment.items())
    ] == _plan()["layout_assignments"]


def test_tampered_or_cross_source_plan_fails_closed() -> None:
    plan = _plan()
    altered = deepcopy(plan)
    altered.pop("artifact_hash")
    altered["layout_assignments"][0]["fold_idx"] = 0
    altered = seal_artifact(altered)
    with pytest.raises(LayoutFoldPlanError, match="seeded algorithm"):
        validate_layout_fold_plan(altered)

    condition_source, intake_report = _sources()
    condition_source["source_commit"] = "f" * 40
    with pytest.raises(LayoutFoldPlanError, match="different provenance"):
        build_layout_fold_plan(
            condition_source,
            intake_report,
            artifact_id="test_stale_source",
            condition_source_file_hash="1" * 64,
            capture_intake_file_hash="2" * 64,
        )


def test_later_frame_folds_must_match_and_embed_the_c_plan() -> None:
    condition_source, _intake_report = _sources()
    frame_manifest = _real_frame_manifest(condition_source["rows"])
    plan = _plan()
    validate_frame_fold_manifest_against_layout_plan(plan, frame_manifest)

    intake_receipt = seal_artifact(
        {
            "artifact_type": "pilot_intake_receipt",
            "artifact_id": "test_real_pilot_intake",
            "code_sha": "a" * 40,
            "config_hash": hash_core_analysis_config(),
            "input_manifest_hash": "c" * 64,
            "fold_manifest_hash": frame_manifest["artifact_hash"],
        }
    )
    bound_fold, bound_receipt = bind_frame_fold_artifacts_to_layout_plan(
        plan,
        frame_manifest,
        intake_receipt,
    )
    assert bound_fold["source_layout_fold_plan_hash"] == plan["artifact_hash"]
    assert bound_fold["fold_assignment_source"] == FOLD_ASSIGNMENT_SOURCE
    assert bound_receipt["fold_manifest_hash"] == bound_fold["artifact_hash"]
    assert bound_receipt["layout_fold_plan_hash"] == plan["artifact_hash"]

    one_row_per_trajectory = [
        {
            "trajectory_id": row["trajectory_id"],
            "model_frame_idx": 0,
            "layout_id": row["layout_id"],
            "status": "accepted",
        }
        for row in plan["trajectory_assignments"]
    ]
    incompatible = _real_frame_manifest(one_row_per_trajectory)
    with pytest.raises(LayoutFoldPlanError, match="changed C's frozen"):
        validate_frame_fold_manifest_against_layout_plan(plan, incompatible)
