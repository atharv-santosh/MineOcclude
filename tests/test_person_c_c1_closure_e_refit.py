from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from scripts.person_c.prepare_c1_closure_e_refit import (
    C1_INGEST_STATUS,
    C6A_MANIFEST,
    C6A_SCHEDULE_SET_SHA256,
    CLOSURE_DIR,
    E_EXPECTED_ROOT,
    E_PRIOR_FILES,
    GEOMETRY,
    GEOMETRY_SHA256,
    GEOMETRY_VERSION,
    HANDOFF_DIR,
    REPO,
    SECOND_INGESTED,
    SECOND_INGESTED_SHA256,
    SECOND_SUCCESS_DIR,
    build_refit_layout,
    validate_c1_1_and_c1_3,
    validate_c6a,
    validate_failed_history,
    validate_first_operator,
    validate_second_operator,
)


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _validate_inventory(directory: Path) -> str:
    inventory = _load(directory / "sha256_inventory.json")
    disk = {
        path.relative_to(REPO).as_posix()
        for path in directory.iterdir()
        if path.is_file() and path.name != "sha256_inventory.json"
    }
    assert {row["path"] for row in inventory["files"]} == disk
    material = ""
    for row in sorted(inventory["files"], key=lambda item: item["path"]):
        data = (REPO / row["path"]).read_bytes()
        assert len(data) == row["size_bytes"]
        assert hashlib.sha256(data).hexdigest() == row["sha256"]
        material += f"{row['path']}\0{row['size_bytes']}\0{row['sha256']}\n"
    digest = hashlib.sha256(material.encode()).hexdigest()
    assert inventory["package_bundle_sha256"] == digest
    return digest


def test_second_operator_success_revalidates_from_runtime() -> None:
    receipt = _load(SECOND_SUCCESS_DIR / "second_operator_success_receipt.json")
    chronology = receipt["chronology"]
    assert receipt["runtime_evidence"]["ingested_output"]["sha256"] == SECOND_INGESTED_SHA256
    assert receipt["status"] == "PASS"
    assert receipt["operator_role"] == "second"
    assert receipt["independent_from_first_operator"] is True
    assert chronology["armed_to_status_seconds"] == 11
    assert chronology["armed_to_receipt_confirmation_seconds"] == 21
    assert chronology["armed_to_screenshot_seconds"] == 30
    assert chronology["armed_to_abort_seconds"] == 39
    assert chronology["screenshot_count_during_episode"] == 1
    assert chronology["recording_started"] is False


def test_c1_1_c1_3_first_operator_and_failed_history_remain_valid() -> None:
    closure = _load(CLOSURE_DIR / "c1_closure_status.json")
    first = _load(REPO / "docs/status/person_c_c1_5_first_operator_attempt_04_success_v0_1/first_operator_success_receipt.json")
    history = first["failed_timing_history"]
    assert closure["c1_1_complete"] is True
    assert closure["c1_3_complete"] is True
    assert first["status"] == "PASS"
    assert first["chronology"]["recording_started"] is False
    assert len(history) == 3
    assert all(row["path"].endswith("failure_record.json") for row in history)


def test_final_c1_closure_and_additive_roadmap_are_closed() -> None:
    prior = _load(C1_INGEST_STATUS)
    closure = _load(CLOSURE_DIR / "c1_closure_status.json")
    roadmap = _load(CLOSURE_DIR / "roadmap_status.json")
    assert prior["c1_5"]["complete"] is False
    assert closure["status"] == "PASS"
    assert closure["c1_1_complete"] is True
    assert closure["c1_3_complete"] is True
    assert closure["c1_5_first_operator_complete"] is True
    assert closure["c1_5_second_operator_complete"] is True
    assert closure["c1_5_complete"] is True
    assert closure["person_c_c1_stop_gate_closed"] is True
    assert closure["e_homography_refit_required"] is True
    assert closure["c6a_execution_authorized"] is False
    assert closure["c6a_remaining_blockers"] == [
        "E_HOMOGRAPHY_REFIT_AND_VALIDATION_FOR_PERSON_C_LAYOUT_CONFIG_V0_4"
    ]
    assert roadmap["next_owner"] == "Person E"


def test_refit_handoff_embeds_all_six_literal_v04_layouts() -> None:
    config = _load(GEOMETRY)
    handoff = _load(HANDOFF_DIR / "refit_input_authority.json")
    assert hashlib.sha256(GEOMETRY.read_bytes()).hexdigest() == GEOMETRY_SHA256
    assert handoff["accepted_geometry_version"] == GEOMETRY_VERSION
    assert handoff["accepted_geometry_sha256"] == GEOMETRY_SHA256
    assert handoff["e_homography_refit_required"] is True
    assert handoff["person_c_performed_refit"] is False
    assert len(handoff["layouts"]) == 6
    assert len(handoff["c1_3_session_screenshots"]) == 5
    assert len(handoff["canonical_screenshots"]) == 2
    assert len(handoff["six_c1_1_runtime_geometry_receipts"]) == 6
    for source, transferred in zip(config["layouts"], handoff["layouts"], strict=True):
        expected = build_refit_layout(source)
        assert transferred == expected
        assert transferred["layout_definition"] == source
        assert transferred["marker_order"] == [
            "near_west", "near_east", "far_east", "far_west"
        ]
    assert handoff["projection_authority"]["raw_framebuffer_width_pixels"] == 1920
    assert handoff["projection_authority"]["raw_framebuffer_height_pixels"] == 1046
    assert handoff["projection_authority"]["canonical_refit_resolution"] == {
        "width_pixels": 640, "height_pixels": 360
    }
    assert handoff["projection_authority"]["fov_degrees"] == 70.0


def test_prior_e_inputs_are_hash_bound_and_superseded_without_modification() -> None:
    handoff = _load(HANDOFF_DIR / "refit_input_authority.json")
    identities = handoff["prior_e_geometry_and_homography_inputs_superseded_for_v0_4"]
    assert len(identities) == len(E_PRIOR_FILES) == 13
    for path, row in zip(E_PRIOR_FILES, identities, strict=True):
        data = path.read_bytes()
        assert row["path"] == path.relative_to(REPO).as_posix()
        assert row["size_bytes"] == len(data)
        assert row["sha256"] == hashlib.sha256(data).hexdigest()
    assert "cannot authorize localization of v0.4 captures" in handoff["supersession_reason"]
    assert handoff["no_hidden_offsets_layout_id_shifts_plus_0_5_corrections_renumbering_or_adapters"] is True


def test_person_e_output_contract_paths_schema_and_tolerances_are_exact() -> None:
    contract = _load(HANDOFF_DIR / "expected_person_e_output_schema.json")
    assert contract["required_root"] == E_EXPECTED_ROOT
    assert contract["required_paths"] == {
        "homography_input": f"{E_EXPECTED_ROOT}/homography_input.json",
        "homography_report": f"{E_EXPECTED_ROOT}/homography_report.json",
        "validation_receipt": f"{E_EXPECTED_ROOT}/validation_receipt.json",
        "sha256_inventory": f"{E_EXPECTED_ROOT}/sha256_inventory.json",
    }
    assert contract["input_schema"]["homography_input_schema_version"] == "person-e-homography-input-v0.1"
    assert contract["homography_report_schema"]["homography_report_schema_version"] == "person-e-homography-report-v0.2"
    tolerances = contract["validation_tolerances"]
    assert tolerances["singular_pivot_tolerance"] == 1e-12
    assert tolerances["maximum_median_wall_parallel_error_blocks"] == 0.2
    assert tolerances["median_comparison"] == "<="
    assert tolerances["maximum_p95_wall_parallel_error_blocks"] == 0.5
    assert tolerances["p95_comparison"] == "<"


def test_c6a_schedules_manifest_and_post_refit_gate_are_valid_but_blocked() -> None:
    manifest = _load(C6A_MANIFEST)
    schedule = _load(REPO / "configs/collection/person_c_c6a_v0_1/schedule_set_manifest.json")
    readiness = _load(CLOSURE_DIR / "c6a_post_c1_closure_readiness.json")
    wrapper_record = readiness["execution_gate_wrapper"]
    wrapper = subprocess.run(
        ["git", "cat-file", "blob", wrapper_record["git_blob"]],
        cwd=REPO,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert schedule["schedule_set_sha256"] == C6A_SCHEDULE_SET_SHA256
    assert manifest["manifest_ready"] is True
    assert readiness["noise_schedule_still_valid"] is True
    assert readiness["capture_manifest_still_valid"] is True
    assert readiness["execution_authorized_now"] is False
    assert readiness["remaining_blockers"] == [
        "E_HOMOGRAPHY_REFIT_AND_VALIDATION_FOR_PERSON_C_LAYOUT_CONFIG_V0_4"
    ]
    assert "planning_gate_passed" in wrapper
    assert wrapper_record["git_blob"] == "d2375cb51e937f98615aeac8dea535c505bac0e2"
    assert "-ExecuteScientificCapture" in readiness["execution_command"]


def test_all_three_additive_package_inventories_are_valid() -> None:
    assert _validate_inventory(SECOND_SUCCESS_DIR) == "946a372164b759f173e2578f920c85fbe0688482306a08553757cc8b829eefc1"
    assert _validate_inventory(HANDOFF_DIR) == "c6e6bc0da867ffafd938bcae6a381a4def692b76157f14e80dd69ae4463dbc28"
    assert len(_validate_inventory(CLOSURE_DIR)) == 64
