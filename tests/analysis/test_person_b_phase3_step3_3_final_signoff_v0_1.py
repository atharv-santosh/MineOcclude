"""Focused tests for Person B's final Step 3.3 validation-only signoff."""

from __future__ import annotations

import ast
import copy
import json
import os
from pathlib import Path

import pytest

from scripts import validate_person_b_phase3_step3_3_final_signoff_v0_1 as signoff

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_C_PACKAGE_ROOT = (
    ROOT.parent
    / "MineOcclude-person-c-step3-3-authority"
    / "data"
    / "handoff_b"
    / signoff.C_PACKAGE_DIRECTORY
)
C_PACKAGE_ROOT = Path(
    os.environ.get(
        "PERSON_C_STEP3_3_PACKAGE_ROOT",
        str(DEFAULT_C_PACKAGE_ROOT),
    )
)
SIGNOFF_ROOT = ROOT / "docs" / "status" / signoff.SIGNOFF_DIRECTORY


def _synthetic_row(**updates: object) -> dict[str, object]:
    row: dict[str, object] = {
        "canonical_camera_pose_id": "synthetic_pose",
        "coordinate_convention": "pixel_center_xy_zero_based",
        "detector_version": signoff.DETECTOR_VERSION,
        "empirical_magenta_visible": False,
        "geometric_visible": False,
        "label_owner": "Person C",
        "layout_id": "synthetic_layout",
        "model_frame_idx": 0,
        "quarantine_category": "none",
        "quarantined": False,
        "resolution": "640x360",
        "trajectory_id": "synthetic_trajectory",
        "visible_flag": False,
    }
    row.update(updates)
    return row


@pytest.fixture(scope="module")
def c_documents() -> dict[str, dict[str, object]]:
    return {
        name: signoff.load_json_file(C_PACKAGE_ROOT / name)
        for name in (
            "authority_binding.json",
            "provenance_index.json",
        )
    }


@pytest.fixture(scope="module")
def joined_rows() -> list[dict[str, object]]:
    path = C_PACKAGE_ROOT / "joined_visibility_records.jsonl"
    return signoff.load_jsonl_bytes(path.read_bytes(), str(path))


@pytest.fixture(scope="module")
def c_result() -> dict[str, object]:
    return signoff.validate_c_package(ROOT, C_PACKAGE_ROOT)


@pytest.fixture(scope="module")
def detector_documents() -> tuple[
    dict[str, object],
    dict[str, object],
    dict[str, object],
]:
    directory = signoff.E_FORMAL_DIRECTORY
    return (
        signoff.git_json(
            ROOT,
            signoff.E_STEP_3_1_COMMIT,
            f"{directory}/formal_evaluation_report.json",
        ),
        signoff.git_json(
            ROOT,
            signoff.E_STEP_3_1_COMMIT,
            f"{directory}/formal_run_receipt.json",
        ),
        signoff.git_json(
            ROOT,
            signoff.E_STEP_3_1_COMMIT,
            f"{directory}/phase3_status.json",
        ),
    )


@pytest.fixture(scope="module")
def homography_report() -> dict[str, object]:
    return signoff.git_json(
        ROOT,
        signoff.E_STEP_3_2_COMMIT,
        (f"{signoff.E_HOMOGRAPHY_DIRECTORY}/step3_2_closure_report.json"),
    )


def test_exact_authority_bindings() -> None:
    assert signoff.validate_authority_commits(ROOT) == {
        "person_a_model_preprocessing": signoff.A_AUTHORITY_COMMIT,
        "person_b_historical": signoff.B_HISTORICAL_AUTHORITY,
        "person_b_operational_parent": signoff.B_OPERATIONAL_PARENT,
        "person_b_step3_3_policy": signoff.B_POLICY_COMMIT,
        "person_c_joined_visibility": signoff.C_JOINED_COMMIT,
        "person_e_detector_freeze": signoff.E_DETECTOR_FREEZE_COMMIT,
        "person_e_empirical_visibility": signoff.E_EMPIRICAL_COMMIT,
        "person_e_step_3_1": signoff.E_STEP_3_1_COMMIT,
        "person_e_step_3_2": signoff.E_STEP_3_2_COMMIT,
    }


def test_step_3_1_thresholds_pass(
    detector_documents: tuple[
        dict[str, object],
        dict[str, object],
        dict[str, object],
    ],
) -> None:
    result = signoff.validate_detector_gate(*detector_documents)
    assert result["status"] == "PASS"
    assert result["precision"] == 1.0
    assert result["recall"] == 1.0
    assert result["minimum_precision"] == 0.95
    assert result["minimum_recall"] == 0.95


def test_incorrect_step_3_1_threshold_result_fails(
    detector_documents: tuple[
        dict[str, object],
        dict[str, object],
        dict[str, object],
    ],
) -> None:
    report, receipt, status = copy.deepcopy(detector_documents)
    report["metrics"]["precision"]["decimal"] = 0.94
    with pytest.raises(signoff.SignoffValidationError):
        signoff.validate_detector_gate(report, receipt, status)


def test_step_3_2_median_threshold_passes(
    homography_report: dict[str, object],
) -> None:
    result = signoff.validate_homography_gate(homography_report)
    assert result["median_error_blocks"] <= result["median_threshold_blocks"]


def test_step_3_2_p95_threshold_passes(
    homography_report: dict[str, object],
) -> None:
    result = signoff.validate_homography_gate(homography_report)
    assert result["p95_error_blocks"] < result["p95_threshold_exclusive_blocks"]


def test_step_3_2_equality_at_strict_p95_boundary_fails(
    homography_report: dict[str, object],
) -> None:
    report = copy.deepcopy(homography_report)
    report["p95_absolute_wall_parallel_error_blocks"] = 0.5
    with pytest.raises(signoff.SignoffValidationError):
        signoff.validate_homography_gate(report)


def test_wrong_coordinate_sha_fails(
    c_documents: dict[str, dict[str, object]],
) -> None:
    with pytest.raises(signoff.SignoffValidationError):
        signoff.validate_coordinate_authority(
            b"not the coordinate authority",
            c_documents["authority_binding.json"],
            c_documents["provenance_index.json"],
        )


def test_missing_b_coordinate_signoff_fails(
    c_documents: dict[str, dict[str, object]],
) -> None:
    authority = copy.deepcopy(c_documents["authority_binding.json"])
    authority["person_b_coordinate_authority"]["required_signoff"]["person_b"] = False
    source = signoff.git_file_bytes(
        ROOT,
        signoff.B_POLICY_COMMIT,
        signoff.COORDINATE_PATH,
    )
    with pytest.raises(signoff.SignoffValidationError):
        signoff.validate_coordinate_authority(
            source,
            authority,
            c_documents["provenance_index.json"],
        )


def test_missing_c_coordinate_signoff_fails(
    c_documents: dict[str, dict[str, object]],
) -> None:
    authority = copy.deepcopy(c_documents["authority_binding.json"])
    authority["person_b_coordinate_authority"]["required_signoff"]["person_c"] = False
    source = signoff.git_file_bytes(
        ROOT,
        signoff.B_POLICY_COMMIT,
        signoff.COORDINATE_PATH,
    )
    with pytest.raises(signoff.SignoffValidationError):
        signoff.validate_coordinate_authority(
            source,
            authority,
            c_documents["provenance_index.json"],
        )


def test_person_a_coordinate_ownership_claim_fails(
    c_documents: dict[str, dict[str, object]],
) -> None:
    authority = copy.deepcopy(c_documents["authority_binding.json"])
    person_a = authority["person_a_model_preprocessing_authority"]
    person_a["owns"] = "model, preprocessing, and coordinate frame"
    person_a["does_not_own"] = ["final_visibility_label"]
    source = signoff.git_file_bytes(
        ROOT,
        signoff.B_POLICY_COMMIT,
        signoff.COORDINATE_PATH,
    )
    with pytest.raises(signoff.SignoffValidationError):
        signoff.validate_coordinate_authority(
            source,
            authority,
            c_documents["provenance_index.json"],
        )


def test_joined_row_count(c_result: dict[str, object]) -> None:
    assert c_result["summary"]["total"]["input_rows"] == 1850


def test_joined_key_uniqueness(c_result: dict[str, object]) -> None:
    assert c_result["summary"]["unique_primary_keys"] == 1850


def test_exact_and_rule_rejects_wrong_label() -> None:
    row = _synthetic_row(
        geometric_visible=False,
        empirical_magenta_visible=True,
        visible_flag=True,
    )
    with pytest.raises(signoff.SignoffValidationError):
        signoff.summarize_joined_rows([row])


def test_raw_channel_preservation_passes_authority(
    c_result: dict[str, object],
) -> None:
    assert c_result["summary"]["raw_channels_preserved_as_distinct_fields"]


def test_raw_channel_change_fails() -> None:
    joined = _synthetic_row()
    geometric = {
        "canonical_camera_pose_id": "synthetic_pose",
        "geometric_visible": False,
        "layout_id": "synthetic_layout",
        "model_frame_idx": 0,
        "trajectory_id": "synthetic_trajectory",
    }
    empirical = {
        "canonical_camera_pose_id": "synthetic_pose",
        "coordinate_convention": "pixel_center_xy_zero_based",
        "detector_version": signoff.DETECTOR_VERSION,
        "empirical_magenta_visible": True,
        "layout_id": "synthetic_layout",
        "model_frame_idx": 0,
        "resolution": "640x360",
        "trajectory_id": "synthetic_trajectory",
    }
    with pytest.raises(signoff.SignoffValidationError):
        signoff.validate_source_channel_preservation(
            [joined],
            [geometric],
            [empirical],
        )


def test_quarantine_categories_and_totals(
    c_result: dict[str, object],
) -> None:
    assert set(signoff.ALLOWED_QUARANTINE_CATEGORIES) == {
        "geometry_hidden_detector_visible",
        "geometry_visible_detector_hidden",
        "invalid_geometry",
        "missing_detector",
        "none",
    }
    assert c_result["summary"]["total"] == signoff.EXPECTED_TOTALS


def test_missing_detector_nonzero_fails(
    joined_rows: list[dict[str, object]],
) -> None:
    rows = copy.deepcopy(joined_rows)
    rows[0].update(
        {
            "empirical_magenta_visible": False,
            "geometric_visible": False,
            "quarantine_category": "missing_detector",
            "quarantined": True,
            "visible_flag": False,
        }
    )
    summary = signoff.summarize_joined_rows(rows)
    with pytest.raises(signoff.SignoffValidationError):
        signoff.validate_expected_accounting(summary)


def test_invalid_quarantine_category_fails() -> None:
    with pytest.raises(signoff.SignoffValidationError):
        signoff.summarize_joined_rows(
            [_synthetic_row(quarantine_category="not_authorized")]
        )


def test_quarantined_visible_row_fails() -> None:
    row = _synthetic_row(
        empirical_magenta_visible=True,
        geometric_visible=True,
        quarantine_category="geometry_hidden_detector_visible",
        quarantined=True,
        visible_flag=True,
    )
    with pytest.raises(signoff.SignoffValidationError):
        signoff.summarize_joined_rows([row])


def test_visible_row_with_non_none_category_fails() -> None:
    row = _synthetic_row(
        empirical_magenta_visible=True,
        geometric_visible=True,
        quarantine_category="geometry_visible_detector_hidden",
        quarantined=False,
        visible_flag=True,
    )
    with pytest.raises(signoff.SignoffValidationError):
        signoff.summarize_joined_rows([row])


def test_per_layout_accounting(c_result: dict[str, object]) -> None:
    assert c_result["summary"]["per_layout"] == signoff.EXPECTED_PER_LAYOUT


def test_wrong_c_commit_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        signoff,
        "C_JOINED_COMMIT",
        signoff.B_POLICY_COMMIT,
    )
    with pytest.raises(signoff.SignoffValidationError):
        signoff.validate_c_package(ROOT, C_PACKAGE_ROOT)


def test_wrong_joined_record_hash_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(signoff, "JOINED_RECORDS_SHA256", "0" * 64)
    with pytest.raises(signoff.SignoffValidationError):
        signoff.validate_c_package(ROOT, C_PACKAGE_ROOT)


def test_e_visible_flag_ownership_fails(
    c_documents: dict[str, dict[str, object]],
) -> None:
    b_policy = signoff.validate_b_policy(ROOT)["documents"][
        "visibility_acceptance_policy.json"
    ]
    b_policy = copy.deepcopy(b_policy)
    b_policy["channel_preservation"][
        "person_e_may_supply_or_overwrite_visible_flag"
    ] = True
    with pytest.raises(signoff.SignoffValidationError):
        signoff.validate_ownership(
            c_documents["authority_binding.json"],
            c_documents["provenance_index.json"],
            b_policy,
        )


def test_b_visible_flag_computation_claim_fails(
    c_documents: dict[str, dict[str, object]],
) -> None:
    b_policy = signoff.validate_b_policy(ROOT)["documents"][
        "visibility_acceptance_policy.json"
    ]
    b_policy = copy.deepcopy(b_policy)
    b_policy["channel_preservation"][
        "person_b_may_recompute_or_overwrite_visible_flag"
    ] = True
    with pytest.raises(signoff.SignoffValidationError):
        signoff.validate_ownership(
            c_documents["authority_binding.json"],
            c_documents["provenance_index.json"],
            b_policy,
        )


def test_accuracy_metrics_on_production_package_fail() -> None:
    with pytest.raises(signoff.SignoffValidationError):
        signoff.validate_no_production_accuracy_metrics([{"precision": 1.0}])


def test_u4_path_rejection(tmp_path: Path) -> None:
    with pytest.raises(signoff.SignoffValidationError):
        signoff.reject_u4_path(tmp_path / "u4_output")


def test_person_a_phase6_authorization_fails() -> None:
    document = {
        "person_a_phase6_authorized": True,
        "u4_output_inspected": False,
    }
    with pytest.raises(signoff.SignoffValidationError):
        signoff.validate_phase_restrictions(document)


def test_validation_only_mode_rejects_other_mode() -> None:
    with pytest.raises(signoff.SignoffValidationError):
        signoff.validate_all(
            repository_root=ROOT,
            signoff_root=SIGNOFF_ROOT,
            person_c_package_root=C_PACKAGE_ROOT,
            mode="write",
        )


def test_deterministic_json_rejects_noncanonical_file(tmp_path: Path) -> None:
    path = tmp_path / "nondeterministic.json"
    path.write_text('{"schema_version":"1.0","a":1}', encoding="utf-8")
    with pytest.raises(signoff.SignoffValidationError):
        signoff.validate_pretty_json(path)


def test_no_pre_existing_path_modifications() -> None:
    result = signoff.validate_repository_scope(ROOT)
    assert result["pre_existing_paths_modified"] is False
    assert result["authorized_paths_only"] is True


def test_validator_source_is_validation_only() -> None:
    source_path = Path(signoff.__file__)
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imports.update(
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    )
    assert all(not name.startswith("mineocclude.vision") for name in imports)
    forbidden_write_calls = {
        "open",
        "write_bytes",
        "write_text",
    }
    calls = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    calls.update(
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    )
    assert not (calls & forbidden_write_calls)
    assert "run_detector" not in calls
    assert "evaluate_magenta_detector" not in calls


def test_full_validation_only_signoff_passes() -> None:
    result = signoff.validate_all(
        repository_root=ROOT,
        signoff_root=SIGNOFF_ROOT,
        person_c_package_root=C_PACKAGE_ROOT,
        mode="validation-only",
    )
    assert result["status"] == "PASS"
    assert result["step_3_3_final_decision"] == "PASS"
    assert result["analysis_readiness"] == "READY"
    assert result["phase3_closure_recommendation"] == "READY"
    assert result["repository_scope"]["pre_existing_paths_modified"] is False


def test_signoff_json_is_deterministic() -> None:
    for name in signoff.SIGNOFF_FILES:
        path = SIGNOFF_ROOT / name
        document = json.loads(path.read_text(encoding="utf-8"))
        assert path.read_bytes() == signoff.canonical_json_bytes(document)
