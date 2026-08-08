#!/usr/bin/env python3
"""Certify C1 closure and prepare the immutable Person E v0.4 refit handoff."""

from __future__ import annotations

import hashlib
import json
import re
import struct
import sys
from pathlib import Path
from typing import Any, Iterator

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from scripts.person_c.ingest_c1_5_second_operator_attempt_02_runtime import (
    validate_attempt_02_logs,
    validate_attestation,
)
from scripts.person_c.prepare_c1_5_first_success_second_operator import (
    validate_c6a,
    validate_first_operator,
)


SERVER = Path(r"C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\server")
CLIENT = Path(r"C:\Users\lollo\MineOcclude-Runtime\person-c-c1-v0_1\client")
SOURCE_COMMIT = "08fefd73325a90f797a55baa9bb1a8a171600953"
GEOMETRY_VERSION = "person-c-layout-config-v0.4"
GEOMETRY_SHA256 = "34495d650d6a8c62b00a916796c90389b48f80d8f20a23eac93207758e993f5d"
JAR_SHA256 = "9ecbb5e85b249409d38428ea479c3f09ec97dd884a97ecb48d79590e4c03de52"
FIRST_INGESTED_SHA256 = "55efd6c247d873f0bda59f48a66817952fbb22e3566c4e416a63e4b42461f5b9"
SECOND_INGESTED_SHA256 = "1b084ca97bbe2f367c30ad300e22c64ed080ab237d71d2c3d1f1a77e00c6f711"
SECOND_RECEIPT_SHA256 = "163559d8c1f74f8bb60d60a1d63cce00972e8e4b4ebffc011c1dadefe5ef4257"
SECOND_SCREENSHOT_SHA256 = "7deb0e1b3576cf8ad8043e73530b38be10b21d50bf60fb59130c28d17da18b74"
SECOND_ATTESTATION_SHA256 = "784d56eac2cb8d3acbf31fc41af9a061e5535ff1eeee289447c03e55e737ec57"
SECOND_SERVER_LOG_SHA256 = "706fcd2615a0002afa59710357b9988add0c0e4abc842f080c0e9f005d6ac23c"
SECOND_CLIENT_LOG_SHA256 = "ef5deeb2f27c5b27f67497a78104b29b954d0dda8674deb09318a52aa232659b"
C6A_SCHEDULE_SET_SHA256 = "79a81668362421fa91cb591d355b655e9b1a60aae088057de7bda977df663806"

GEOMETRY = REPO / "configs/scenes/layouts_v0_4.yaml"
C1_INGEST_DIR = REPO / "docs/status/person_c_c1_runtime_ingestion_v0_1"
C1_INGEST_STATUS = C1_INGEST_DIR / "c1_closure_status.json"
C1_INGEST_VALIDATION = C1_INGEST_DIR / "validation_report.json"
C1_LAYOUT_OBSERVATIONS = C1_INGEST_DIR / "layout_runtime_observations.json"
C1_SCREENSHOTS = C1_INGEST_DIR / "screenshot_manifest.json"
RENDER_SETTINGS = C1_INGEST_DIR / "render_settings_receipt.json"
ENVIRONMENT_LOCK = C1_INGEST_DIR / "final_environment_lock_receipt.json"
SERVER_RUNTIME_MANIFEST = REPO / "docs/status/person_c_c1_runtime_provisioning_v0_2/server_runtime_manifest.json"
CLIENT_RUNTIME_MANIFEST = REPO / "docs/status/person_c_c1_runtime_provisioning_v0_2/client_runtime_manifest.json"
GEOMETRY_AUTHORITY = REPO / "docs/status/person_c_geometry_authority_v0_2/accepted_geometry_authority.json"
FIRST_SUCCESS = REPO / "docs/status/person_c_c1_5_first_operator_attempt_04_success_v0_1/first_operator_success_receipt.json"
SECOND_FAILURE = REPO / "docs/status/person_c_c1_5_second_operator_attempt_02_v0_1/attempt_01_failure_record.json"
C6A_MANIFEST = REPO / "docs/status/person_c_c6a_capture_manifest_v0_2/c6a_capture_manifest.json"
C6A_SCHEDULE_MANIFEST = REPO / "configs/collection/person_c_c6a_v0_1/schedule_set_manifest.json"
C6A_WRAPPER = REPO / "scripts/person_c/run-c6a-after-e-refit.ps1"

FIRST_ATTESTATION = SERVER / "c1_5_evidence/first_operator_attempt_04_attestation.json"
FIRST_INGESTED = SERVER / "c1_5_evidence/first_operator_attempt_04_ingested.json"
SECOND_RECEIPT = SERVER / "mineocclude_observations/c1_5_second_operator_attempt_02_layout_01.json"
SECOND_SCREENSHOT = CLIENT / "c1_5_evidence/second_operator_attempt_02_layout_01.png"
SECOND_RAW_SCREENSHOT = CLIENT / "screenshots/2026-08-03_22.58.33.png"
SECOND_ATTESTATION = SERVER / "c1_5_evidence/second_operator_attempt_02_attestation.json"
SECOND_INGESTED = SERVER / "c1_5_evidence/second_operator_attempt_02_ingested.json"
SECOND_SERVER_LOG = SERVER / "c1_5_evidence/second_operator_attempt_02_success/server_latest.log"
SECOND_CLIENT_LOG = CLIENT / "c1_5_evidence/second_operator_attempt_02_success/client_latest.log"
INSTALLED_SERVER_JAR = SERVER / "mods/mineocclude-0.1.1.jar"
INSTALLED_CLIENT_JAR = CLIENT / "mods/mineocclude-0.1.1.jar"

FAILED_HISTORY = [
    REPO / "docs/status/person_c_c1_5_attempt_02_v0_1/attempt_01_failure_record.json",
    REPO / "docs/status/person_c_c1_5_attempt_03_v0_1/attempt_02_failure_record.json",
    REPO / "docs/status/person_c_c1_5_attempt_04_v0_1/attempt_03_failure_record.json",
    SECOND_FAILURE,
]

SECOND_SUCCESS_DIR = REPO / "docs/status/person_c_c1_5_second_operator_attempt_02_success_v0_1"
CLOSURE_DIR = REPO / "docs/status/person_c_c1_closure_v0_1"
HANDOFF_DIR = REPO / "docs/status/person_c_to_person_e_homography_refit_v0_1"
E_EXPECTED_ROOT = "data/handoff_e/person_e_v0_4_homography_refit_v0_1"

E_PRIOR_FILES = [
    *(REPO / f"data/handoff_e/markers_layout_{index:02d}.json" for index in range(1, 7)),
    REPO / "data/handoff_e/detector_calibration_inputs.json",
    REPO / "data/handoff_e/independent_probe_points.json",
    REPO / "data/handoff_e/phase3_homography_authority_v0_1/homography_applicability_manifest.json",
    REPO / "data/handoff_e/phase3_homography_authority_v0_1/homography_authority_receipt.json",
    REPO / "data/handoff_e/phase3_homography_authority_v0_1/known_direction_validation_records.json",
    REPO / "data/handoff_e/phase3_homography_authority_v0_1/marker_pose_resolution_bindings.json",
    REPO / "data/handoff_e/phase3_homography_authority_v0_1/wall_axis_sign_authority.json",
]
E_CONFIG = REPO / "configs/vision/person_e_phase1.yaml"
E_FITTER = REPO / "scripts/fit_homographies.py"
E_HOMOGRAPHY_CODE = REPO / "src/mineocclude/vision/homography.py"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git_blob(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


def dump(value: Any) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def identity(path: Path, *, display: str | None = None) -> dict[str, Any]:
    data = path.read_bytes()
    return {"path": display or str(path.resolve()), "size_bytes": len(data), "sha256": sha256(data)}


def repo_identity(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    return {
        "path": path.relative_to(REPO).as_posix(),
        "size_bytes": len(data),
        "sha256": sha256(data),
        "git_blob": git_blob(data),
    }


def generated_identity(path: Path, data: bytes) -> dict[str, Any]:
    return {"path": path.relative_to(REPO).as_posix(), "size_bytes": len(data), "sha256": sha256(data)}


def canonical_value_hash(value: Any) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))


def bundle_digest(entries: list[dict[str, Any]]) -> str:
    material = "".join(
        f"{entry['path']}\0{entry['size_bytes']}\0{entry['sha256']}\n"
        for entry in sorted(entries, key=lambda row: row["path"])
    ).encode("utf-8")
    return sha256(material)


def package_inventory(directory: Path, outputs: dict[Path, bytes]) -> tuple[bytes, str]:
    rows = [
        generated_identity(path, data)
        for path, data in sorted(outputs.items(), key=lambda item: item[0].as_posix())
        if path.parent == directory and path.name != "sha256_inventory.json"
    ]
    digest = bundle_digest(rows)
    return dump({
        "schema_version": "person-c-package-sha256-inventory-v1.1",
        "self_excluded": "sha256_inventory.json",
        "bundle_digest_algorithm": "sha256(path\\0size_bytes\\0sha256\\n sorted by path)",
        "package_bundle_sha256": digest,
        "files": rows,
    }), digest


def resolve_record_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else REPO / path


def iter_file_identities(value: Any, key_path: tuple[str, ...] = ()) -> Iterator[tuple[tuple[str, ...], dict[str, Any]]]:
    if isinstance(value, dict):
        if {"path", "size_bytes", "sha256"}.issubset(value):
            yield key_path, value
        for key, child in value.items():
            yield from iter_file_identities(child, (*key_path, str(key)))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from iter_file_identities(child, (*key_path, str(index)))


def validate_failed_history() -> list[dict[str, Any]]:
    expected = [
        (1, "first", "POST_FINALIZATION_OBSERVATION_INVALID_NOT_TARGET_RETENTION_FAILURE"),
        (2, "first", "POST_FINALIZATION_OBSERVATION_INVALID_NOT_TARGET_RETENTION_FAILURE"),
        (3, "first", "GEOMETRY_RECEIPT_VALID_BUT_SCREENSHOT_AND_ABORT_OCCURRED_AFTER_RECORDING_STARTED"),
        (1, "second", "SCREENSHOT_CAPTURED_BEFORE_GEOMETRY_RECEIPT_CONFIRMATION"),
    ]
    results: list[dict[str, Any]] = []
    ephemeral_latest = {(SERVER / "logs/latest.log").resolve(), (CLIENT / "logs/latest.log").resolve()}
    for record_path, (attempt, role, classification) in zip(FAILED_HISTORY, expected, strict=True):
        record = load(record_path)
        require(record.get("attempt") == attempt, f"failed-attempt number drift: {record_path}")
        record_role = record.get("operator_role") or "first"
        require(record_role == role, f"failed-attempt role drift: {record_path}")
        require(record.get("classification") == classification, f"failed-attempt classification drift: {record_path}")
        checked = 0
        skipped_ephemeral = 0
        for key_path, expected_identity in iter_file_identities(record):
            path = resolve_record_path(expected_identity["path"])
            if path.resolve() in ephemeral_latest:
                skipped_ephemeral += 1
                continue
            require(path.is_file(), f"preserved failed evidence absent: {path} ({'.'.join(key_path)})")
            current = identity(path)
            require(current["size_bytes"] == expected_identity["size_bytes"] and current["sha256"] == expected_identity["sha256"], f"preserved failed evidence drift: {path}")
            checked += 1
        if role == "second":
            for key in ("canonical_screenshot_path_not_created", "attestation_path_not_created", "ingested_path_not_created"):
                absent = resolve_record_path(record["files"][key])
                require(not absent.exists(), f"failed second attempt was later certified: {absent}")
        require(checked > 0, f"no stable failed evidence identities checked: {record_path}")
        results.append({
            "operator_role": role,
            "attempt": attempt,
            "classification": classification,
            "failure_record": repo_identity(record_path),
            "stable_file_identities_checked": checked,
            "ephemeral_latest_log_aliases_skipped": skipped_ephemeral,
            "preserved_unchanged": True,
            "certified": False,
        })
    return results


def validate_c1_1_and_c1_3(config: dict[str, Any]) -> dict[str, Any]:
    closure = load(C1_INGEST_STATUS)
    validation = load(C1_INGEST_VALIDATION)
    observations = load(C1_LAYOUT_OBSERVATIONS)
    screenshot_manifest = load(C1_SCREENSHOTS)
    render = load(RENDER_SETTINGS)
    require(closure["c1_1"]["complete"] is True and closure["c1_3"]["complete"] is True, "prior C1.1/C1.3 closure drift")
    require(validation["status"] == "PASS" and validation["all_focused_checks_pass"] is True and validation["check_count"] == 166, "C1 runtime ingestion validation drift")
    require(observations["status"] == "PASS" and observations["valid_receipt_count"] == 6, "six-layout observation manifest drift")
    layouts = {row["layout_id"]: row for row in config["layouts"]}
    receipts: list[dict[str, Any]] = []
    for entry in observations["receipts"]:
        path = Path(entry["path"])
        require(path.is_file(), f"C1.1 runtime receipt absent: {path}")
        current = identity(path)
        require(current["size_bytes"] == entry["size_bytes"] and current["sha256"] == entry["sha256"], f"C1.1 receipt hash drift: {path}")
        receipt = load(path)
        layout = layouts[entry["layout_id"]]
        require(receipt["layout_id"] == entry["layout_id"] and receipt["observed_marker_block_count"] == 4, f"C1.1 receipt identity drift: {path}")
        require(receipt["floor"]["mismatches"] == [] and receipt["wall"]["mismatches"] == [], f"C1.1 geometry mismatch: {path}")
        actual_markers = {row["role"]: row for row in receipt["markers"]}
        for marker in layout["markers"]:
            actual = actual_markers[marker["role"]]
            require(actual["block_pos_xyz"] == marker["block_pos_xyz"] and actual["top_face_centre_world_xyz"] == marker["top_face_centre_world_xyz"] and actual["matches"] is True, f"C1.1 marker mismatch: {entry['layout_id']} {marker['role']}")
        camera = receipt["camera"]["observed_players"][0]
        require(camera["feet_xyz"] == layout["camera"]["feet_xyz"] and camera["yaw_degrees"] == layout["camera"]["yaw_degrees"] and camera["pitch_degrees"] == layout["camera"]["pitch_degrees"], f"C1.1 camera mismatch: {entry['layout_id']}")
        receipts.append(current)
    require(screenshot_manifest["status"] == "PASS" and screenshot_manifest["c1_3_acceptance"]["result"] == "PASS", "C1.3 screenshot manifest drift")
    screenshots: list[dict[str, Any]] = []
    for entry in screenshot_manifest["screenshots"]:
        path = Path(entry["path"])
        current = identity(path)
        require(current["size_bytes"] == entry["size_bytes"] and current["sha256"] == entry["sha256"], f"C1.3 screenshot drift: {path}")
        screenshots.append(entry)
    require(render["displayed_fov"]["degrees"] == 70.0 and render["raw_framebuffer"]["width_pixels"] == 1920 and render["raw_framebuffer"]["height_pixels"] == 1046, "render/FOV authority drift")
    return {
        "c1_1_complete": True,
        "c1_3_complete": True,
        "validation_receipt": repo_identity(C1_INGEST_VALIDATION),
        "layout_observation_manifest": repo_identity(C1_LAYOUT_OBSERVATIONS),
        "geometry_receipts": receipts,
        "screenshot_manifest": repo_identity(C1_SCREENSHOTS),
        "screenshots": screenshots,
        "render_settings_receipt": repo_identity(RENDER_SETTINGS),
    }


def validate_second_operator(config: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    expected = {
        SECOND_RECEIPT: SECOND_RECEIPT_SHA256,
        SECOND_SCREENSHOT: SECOND_SCREENSHOT_SHA256,
        SECOND_RAW_SCREENSHOT: SECOND_SCREENSHOT_SHA256,
        SECOND_ATTESTATION: SECOND_ATTESTATION_SHA256,
        SECOND_INGESTED: SECOND_INGESTED_SHA256,
        SECOND_SERVER_LOG: SECOND_SERVER_LOG_SHA256,
        SECOND_CLIENT_LOG: SECOND_CLIENT_LOG_SHA256,
        INSTALLED_SERVER_JAR: JAR_SHA256,
        INSTALLED_CLIENT_JAR: JAR_SHA256,
    }
    for path, expected_hash in expected.items():
        require(path.is_file() and identity(path)["sha256"] == expected_hash, f"second-operator evidence absent or drifted: {path}")
    ingested = load(SECOND_INGESTED)
    attestation = load(SECOND_ATTESTATION)
    receipt = load(SECOND_RECEIPT)
    first_attestation = load(FIRST_ATTESTATION)
    failure = load(SECOND_FAILURE)
    validate_attestation(attestation, first_attestation, failure)
    chronology = validate_attempt_02_logs(
        SECOND_SERVER_LOG.read_text(encoding="utf-8", errors="replace").splitlines(),
        SECOND_CLIENT_LOG.read_text(encoding="utf-8", errors="replace").splitlines(),
    )
    require(ingested["status"] == "PASS" and ingested["c1_5_complete"] is True and ingested["chronology"] == chronology, "second ingested status/chronology mismatch")
    require(attestation["operator_role"] == "second" and attestation["operator_id"] == "Santa313" and attestation["independent_from_first_operator"] is True, "second-operator identity/independence mismatch")
    target = receipt["target"]
    require(target["valid"] is True and target["required"] is True and target["tagged_target_count"] == 1 and target["problems"] == [], "second target receipt mismatch")
    require(chronology["armed_to_status_seconds"] >= 10 and chronology["armed_to_observegeometry_seconds"] <= chronology["armed_to_receipt_confirmation_seconds"] < chronology["armed_to_screenshot_seconds"] < chronology["armed_to_abort_seconds"], "second chronology offsets mismatch")
    require(chronology["screenshot_count_during_episode"] == 1 and chronology["recording_started"] is False and chronology["episode_aborted_during_warmup"] is True, "second screenshot/abort/recording facts mismatch")
    require(ingested["accepted_geometry_version"] == GEOMETRY_VERSION, "second accepted geometry mismatch")
    for key, entry in ingested["files"].items():
        if not isinstance(entry, dict) or not {"path", "size_bytes", "sha256"}.issubset(entry):
            continue
        path = resolve_record_path(entry["path"])
        current = identity(path)
        require(current["size_bytes"] == entry["size_bytes"] and current["sha256"] == entry["sha256"], f"second ingested file binding drift: {key}")
    png = SECOND_SCREENSHOT.read_bytes()
    require(png[:8] == b"\x89PNG\r\n\x1a\n" and struct.unpack(">II", png[16:24]) == (640, 360), "second canonical screenshot is not 640x360 PNG")
    require(SECOND_SCREENSHOT.read_bytes() == SECOND_RAW_SCREENSHOT.read_bytes(), "second canonical screenshot differs from raw same-session F2")
    layout = next(row for row in config["layouts"] if row["layout_id"] == "layout_01")
    markers = {row["role"]: row for row in receipt["markers"]}
    for expected_marker in layout["markers"]:
        actual = markers[expected_marker["role"]]
        require(actual["block_pos_xyz"] == expected_marker["block_pos_xyz"] and actual["top_face_centre_world_xyz"] == expected_marker["top_face_centre_world_xyz"] and actual["matches"] is True, f"second receipt marker mismatch: {expected_marker['role']}")
    return ingested, chronology


def build_refit_layout(layout: dict[str, Any]) -> dict[str, Any]:
    by_role = {marker["role"]: marker for marker in layout["markers"]}
    marker_order = ["near_west", "near_east", "far_east", "far_west"]
    points = {role: [by_role[role]["top_face_centre_world_xyz"][0], by_role[role]["top_face_centre_world_xyz"][2]] for role in marker_order}
    marker_rows = [
        {
            "marker_id": role,
            "color": by_role[role]["color"],
            "block_pos_xyz": by_role[role]["block_pos_xyz"],
            "top_face_centre_world_xyz": by_role[role]["top_face_centre_world_xyz"],
            "world_xz_blocks": points[role],
        }
        for role in marker_order
    ]
    axis = layout["scalar_axis"]["world_axis"]
    lane_ortho = float(layout["lane"]["ortho"])
    origin = [0.0, lane_ortho] if axis == "x" else [lane_ortho, 0.0]
    unit = [1.0, 0.0] if axis == "x" else [0.0, 1.0]
    geometry_record = {
        "layout_id": layout["layout_id"],
        "layout_definition": layout,
        "canonical_camera_pose_id": f"{layout['layout_id']}_canonical_pose_v1",
        "camera": layout["camera"],
        "floor": layout["floor"],
        "wall": layout["wall"],
        "marker_order": marker_order,
        "markers": marker_rows,
        "world_points_by_marker": points,
        "wall_parallel_origin_xz": origin,
        "wall_parallel_positive_unit_xz": unit,
        "runtime_geometry_receipt": layout["runtime_evidence"],
    }
    return {
        **geometry_record,
        "geometry_record_hash_algorithm": "sha256(UTF-8 canonical JSON: sort_keys=true,separators=(',',':'))",
        "marker_set_source_hash": canonical_value_hash(geometry_record),
        "image_points_by_marker": "PERSON_E_OWNED_REQUIRED_FROM_A_V0_4_BOUND_640X360_CANONICAL_FRAME",
        "validation_pairs": "PERSON_E_OWNED_REQUIRED_FROM_INDEPENDENT_V0_4_BOUND_POINTS_NOT_THE_FOUR_FIT_MARKERS",
    }


def expected_output_schema() -> dict[str, Any]:
    return {
        "schema_version": "person-c-to-person-e-v0.4-refit-output-contract-v0.1",
        "owner_of_outputs": "Person E",
        "required_root": E_EXPECTED_ROOT,
        "required_paths": {
            "homography_input": f"{E_EXPECTED_ROOT}/homography_input.json",
            "homography_report": f"{E_EXPECTED_ROOT}/homography_report.json",
            "validation_receipt": f"{E_EXPECTED_ROOT}/validation_receipt.json",
            "sha256_inventory": f"{E_EXPECTED_ROOT}/sha256_inventory.json",
        },
        "input_schema": {
            "homography_input_schema_version": "person-e-homography-input-v0.1",
            "root_required_exact": ["homography_input_schema_version", "layouts"],
            "layout_required": [
                "layout_id", "canonical_camera_pose_id", "marker_set_source_hash",
                "validation_source_hash", "marker_ids", "image_points_by_marker",
                "world_points_by_marker", "validation_pairs", "wall_parallel_origin_xz",
                "wall_parallel_positive_unit_xz",
            ],
            "layout_count": 6,
        },
        "homography_report_schema": {
            "homography_report_schema_version": "person-e-homography-report-v0.2",
            "root_required": [
                "homography_report_schema_version", "input_hash", "producer_run_id", "code_sha",
                "config_hash", "config_instance_version", "settings_hash", "algorithm_version",
                "singular_pivot_tolerance", "maximum_median_wall_parallel_error_blocks",
                "maximum_p95_wall_parallel_error_blocks", "minimum_shift_error_multiplier_on_gate_failure",
                "layouts",
            ],
            "layout_required": [
                "layout_id", "canonical_camera_pose_id", "marker_set_source_hash",
                "validation_source_hash", "wall_parallel_origin_xz",
                "wall_parallel_positive_unit_xz", "homography", "heldout_localization",
            ],
            "homography_required_exact": [
                "matrix", "marker_ids", "layout_id", "canonical_camera_pose_id", "fit_hash",
                "homography_version_id", "algorithm_version", "pivot_tolerance",
                "denominator_tolerance", "image_coordinate_convention", "world_coordinate_convention",
            ],
            "matrix_shape": [3, 3],
            "algorithm_version": "four_point_projective_gauss_jordan_v0.1",
            "image_coordinate_convention": "pixel_center_xy_zero_based",
            "world_coordinate_convention": "ground_plane_world_xz_blocks",
            "layout_count": 6,
        },
        "validation_receipt_schema": {
            "schema_version": "person-e-person-c-v0.4-homography-refit-validation-v0.1",
            "required_exact": [
                "schema_version", "status", "owner", "source_commit", "accepted_geometry_version",
                "accepted_geometry_sha256", "person_c_handoff_bundle_sha256",
                "homography_input_sha256", "homography_report_sha256", "layout_ids",
                "layout_count", "all_layouts_planning_gate_passed", "validation_tolerances",
                "no_hidden_offsets_or_compatibility_adapters", "per_layout",
            ],
            "required_values": {
                "status": "PASS",
                "owner": "Person E",
                "accepted_geometry_version": GEOMETRY_VERSION,
                "accepted_geometry_sha256": GEOMETRY_SHA256,
                "layout_ids": [f"layout_{index:02d}" for index in range(1, 7)],
                "layout_count": 6,
                "all_layouts_planning_gate_passed": True,
                "no_hidden_offsets_or_compatibility_adapters": True,
            },
        },
        "sha256_inventory_schema": {
            "schema_version": "person-e-v0.4-homography-refit-sha256-inventory-v0.1",
            "root_required_exact": ["schema_version", "files"],
            "file_required_exact": ["path", "size_bytes", "sha256"],
            "required_listed_paths": [
                f"{E_EXPECTED_ROOT}/homography_input.json",
                f"{E_EXPECTED_ROOT}/homography_report.json",
                f"{E_EXPECTED_ROOT}/validation_receipt.json",
            ],
            "self_excluded": "sha256_inventory.json",
        },
        "validation_tolerances": {
            "authority": repo_identity(E_CONFIG),
            "singular_pivot_tolerance": 1e-12,
            "maximum_median_wall_parallel_error_blocks": 0.2,
            "median_comparison": "<=",
            "maximum_p95_wall_parallel_error_blocks": 0.5,
            "p95_comparison": "<",
            "minimum_shift_error_multiplier_on_gate_failure": 2.0,
            "percentile_method": "linear_interpolation_rank_n_minus_1",
        },
        "implementation_authorities": {
            "fitter": repo_identity(E_FITTER),
            "homography_code": repo_identity(E_HOMOGRAPHY_CODE),
        },
        "person_c_does_not_create_these_outputs": True,
    }


def main() -> int:
    require(GEOMETRY.is_file() and sha256(GEOMETRY.read_bytes()) == GEOMETRY_SHA256, "accepted geometry hash drift")
    config = load(GEOMETRY)
    require(config["config_version"] == GEOMETRY_VERSION and len(config["layouts"]) == 6, "accepted geometry version/layout count drift")
    authority = load(GEOMETRY_AUTHORITY)
    require(authority["accepted_geometry_owner"] == "SUCCESSOR" and authority["accepted_geometry_version"] == GEOMETRY_VERSION and authority["accepted_config_identity"]["sha256"] == GEOMETRY_SHA256 and authority["e_homography_refit_required"] is True, "geometry authority drift")

    c1 = validate_c1_1_and_c1_3(config)
    first_ingested, first_chronology = validate_first_operator()
    require(identity(FIRST_INGESTED)["sha256"] == FIRST_INGESTED_SHA256, "first ingested hash drift")
    second_ingested, second_chronology = validate_second_operator(config)
    failed_history = validate_failed_history()
    c6a = validate_c6a()
    require(c6a["schedule_set_sha256"] == C6A_SCHEDULE_SET_SHA256 and c6a["output_paths_absent"] is True, "C6A schedule/output validation drift")
    c6a_manifest = load(C6A_MANIFEST)
    require(C6A_WRAPPER.is_file(), "new C6A post-refit gate wrapper absent")

    second_success = {
        "schema_version": "person-c-c1.5-independent-second-operator-attempt-02-success-v0.1",
        "status": "PASS",
        "source_commit": SOURCE_COMMIT,
        "operator_role": "second",
        "operator_id": "Santa313",
        "attempt": 2,
        "same_human_as_second_operator_attempt_01": True,
        "independent_from_first_operator": True,
        "operator_differs_from_first_operator": True,
        "accepted_geometry_version": GEOMETRY_VERSION,
        "accepted_geometry_sha256": GEOMETRY_SHA256,
        "mineocclude_jar_sha256": JAR_SHA256,
        "target": {"valid": True, "required": True, "tagged_target_count": 1, "problems": []},
        "chronology": second_chronology,
        "same_runtime_session_proven": True,
        "geometry_receipt_valid": True,
        "screenshot_valid": True,
        "attestation_valid": True,
        "ingested_output_valid": True,
        "c1_5_first_operator_complete": True,
        "c1_5_second_operator_complete": True,
        "c1_5_complete": True,
        "runtime_evidence": {
            "geometry_receipt": identity(SECOND_RECEIPT),
            "canonical_screenshot": {**identity(SECOND_SCREENSHOT), "width_pixels": 640, "height_pixels": 360},
            "raw_same_session_screenshot": identity(SECOND_RAW_SCREENSHOT),
            "attestation": identity(SECOND_ATTESTATION),
            "ingested_output": identity(SECOND_INGESTED),
            "server_log_archive": identity(SECOND_SERVER_LOG),
            "client_log_archive": identity(SECOND_CLIENT_LOG),
            "installed_server_jar": identity(INSTALLED_SERVER_JAR),
            "installed_client_jar": identity(INSTALLED_CLIENT_JAR),
        },
        "first_operator_success": repo_identity(FIRST_SUCCESS),
        "failed_history": failed_history,
    }
    second_validation = {
        "schema_version": "person-c-c1.5-second-operator-success-validation-v0.1",
        "status": "PASS",
        "checks": {
            "receipt": True, "screenshot": True, "attestation": True, "ingested_output": True,
            "target": True, "strict_chronology": True, "same_session": True,
            "accepted_geometry": True, "repaired_jar": True, "failed_history_preserved": True,
        },
    }
    second_md = """# C1.5 independent second-operator attempt 02 success\n\nThe hash-bound finalizer evidence passes. `Santa313` is the same second human as failed second-operator attempt 01 and differs from the first operator. Target status passed at +11 seconds; geometry receipt confirmation completed at +21 seconds; exactly one F2 screenshot followed at +30 seconds; `mineocclude stop` aborted during warmup at +39 seconds; recording never began.\n\nAll earlier failures remain historical, unchanged, and uncertified. Runtime binaries and screenshots remain external and are referenced only by path, size, and SHA-256.\n"""
    second_outputs: dict[Path, bytes] = {
        SECOND_SUCCESS_DIR / "second_operator_success_receipt.json": dump(second_success),
        SECOND_SUCCESS_DIR / "validation_report.json": dump(second_validation),
        SECOND_SUCCESS_DIR / "evidence_matrix.md": second_md.encode("utf-8"),
    }
    second_inventory, second_bundle = package_inventory(SECOND_SUCCESS_DIR, second_outputs)
    second_outputs[SECOND_SUCCESS_DIR / "sha256_inventory.json"] = second_inventory

    refit_layouts = [build_refit_layout(layout) for layout in config["layouts"]]
    output_contract = expected_output_schema()
    output_contract_bytes = dump(output_contract)
    canonical_screenshots = [
        {**load(FIRST_SUCCESS)["runtime_evidence"]["screenshot"], "operator_role": "first", "width_pixels": 640, "height_pixels": 360},
        {**identity(SECOND_SCREENSHOT), "operator_role": "second", "width_pixels": 640, "height_pixels": 360},
    ]
    handoff = {
        "schema_version": "person-c-to-person-e-homography-refit-handoff-v0.1",
        "package_id": "person-c-to-person-e-v0.4-homography-refit-v0.1",
        "immutable": True,
        "source_commit": SOURCE_COMMIT,
        "owner_of_geometry": "SUCCESSOR_C_GOVERNED",
        "owner_of_refit_outputs": "Person E",
        "person_c_performed_refit": False,
        "e_homography_refit_required": True,
        "accepted_geometry": repo_identity(GEOMETRY),
        "accepted_geometry_version": GEOMETRY_VERSION,
        "accepted_geometry_sha256": GEOMETRY_SHA256,
        "coordinate_policy": config["coordinate_policy"],
        "no_hidden_offsets_layout_id_shifts_plus_0_5_corrections_renumbering_or_adapters": True,
        "layout_count": 6,
        "layouts": refit_layouts,
        "projection_authority": {
            **config["shared_capture_projection"],
            "canonical_refit_resolution": {"width_pixels": 640, "height_pixels": 360},
            "image_coordinate_convention": "pixel_center_xy_zero_based",
            "world_coordinate_convention": "ground_plane_world_xz_blocks_topface_centre",
            "canonical_pose_ids_retained_only_because_literal_camera_poses_match": True,
        },
        "render_setting_authorities": {
            "render_settings_receipt": repo_identity(RENDER_SETTINGS),
            "c1_3_screenshot_manifest": repo_identity(C1_SCREENSHOTS),
            "options_file": identity(CLIENT / "options.txt"),
            "displayed_fov_degrees": 70.0,
            "raw_framebuffer": {"width_pixels": 1920, "height_pixels": 1046},
            "canonical_derivative": {"width_pixels": 640, "height_pixels": 360},
        },
        "environment_lock": {
            "version": "person-c-c1-final-environment-lock-v1.0",
            "receipt": repo_identity(ENVIRONMENT_LOCK),
        },
        "runtime_identities": {
            "minecraft": "1.16.5", "fabric_loader": "0.15.11", "yarn": "1.16.5+build.10",
            "fabric_api": "0.42.0+1.16", "java": "17.0.19",
            "server_runtime_manifest": repo_identity(SERVER_RUNTIME_MANIFEST),
            "client_runtime_manifest": repo_identity(CLIENT_RUNTIME_MANIFEST),
            "server_properties": identity(SERVER / "server.properties"),
            "client_options": identity(CLIENT / "options.txt"),
        },
        "mineocclude_repaired_jar": {
            "source_commit": "538a176e1c83dc3b40e220dee8ebb2ac841bd9b4",
            "fabric_metadata": {"id": "mineocclude", "version": "0.1.1"},
            "server": identity(INSTALLED_SERVER_JAR),
            "client": identity(INSTALLED_CLIENT_JAR),
        },
        "six_c1_1_runtime_geometry_receipts": c1["geometry_receipts"],
        "c1_5_first_operator_evidence": {
            "success_receipt": repo_identity(FIRST_SUCCESS),
            "ingested_output": identity(FIRST_INGESTED),
            "chronology": first_chronology,
        },
        "c1_5_second_operator_evidence": {
            "success_package_bundle_sha256": second_bundle,
            "ingested_output": identity(SECOND_INGESTED),
            "chronology": second_chronology,
        },
        "c1_3_session_screenshots": c1["screenshots"],
        "canonical_screenshots": canonical_screenshots,
        "prior_e_geometry_and_homography_inputs_superseded_for_v0_4": [repo_identity(path) for path in E_PRIOR_FILES],
        "supersession_reason": "All six prior E correspondence sets and downstream homography applicability records are bound to marker world coordinates that differ from every literal person-c-layout-config-v0.4 marker set. Those frozen files remain historical evidence but cannot authorize localization of v0.4 captures. Refit all six matrices from v0.4-bound 640x360 image correspondences and independent v0.4 validation pairs; do not reuse old image/world pairs or apply an output offset.",
        "known_direction_records_use": "Historical sign records may be consulted only as a direction cross-check. They do not substitute for v0.4 marker correspondences or v0.4 independent validation pairs.",
        "expected_output_contract": {
            "path": (HANDOFF_DIR / "expected_person_e_output_schema.json").relative_to(REPO).as_posix(),
            "sha256": sha256(output_contract_bytes),
        },
        "expected_e_owned_artifact_paths": output_contract["required_paths"],
        "validation_tolerances": output_contract["validation_tolerances"],
        "required_person_e_action": "Create the exact E-owned input/report/validation/inventory package, fit six matrices, pass all held-out gates, and commit it on an E-authorized branch. Do not edit this Person C handoff.",
        "credentials_or_binaries_included": False,
    }
    handoff_md = """# Person C → Person E v0.4 homography-refit handoff\n\nThis immutable package transfers literal `person-c-layout-config-v0.4` geometry and hash-bound runtime authorities. Person C has not fit or altered Person E matrices. Person E must create the exact outputs named in `expected_person_e_output_schema.json`.\n\nThe old E correspondence and Phase 3 homography-authority files remain frozen historical evidence. They are out of domain for v0.4 because every layout's literal marker coordinates changed. No offset, `+0.5` correction, layout-ID shift, coordinate renumbering, role adapter, or compatibility transform is permitted.\n\nThe E validation gate remains median wall-parallel absolute error `<= 0.2` blocks and p95 `< 0.5` blocks on independent v0.4-bound points. Until all six layouts pass and the E-owned validation receipt exists, C6A is not authorized. No runtime binaries, screenshots, personal credentials, or world data are copied here; external evidence is referenced by path, size, and SHA-256.\n"""
    handoff_outputs: dict[Path, bytes] = {
        HANDOFF_DIR / "refit_input_authority.json": dump(handoff),
        HANDOFF_DIR / "expected_person_e_output_schema.json": output_contract_bytes,
        HANDOFF_DIR / "HANDOFF.md": handoff_md.encode("utf-8"),
    }
    handoff_inventory, handoff_bundle = package_inventory(HANDOFF_DIR, handoff_outputs)
    handoff_outputs[HANDOFF_DIR / "sha256_inventory.json"] = handoff_inventory

    c6a_command = (
        'powershell.exe -NoProfile -ExecutionPolicy Bypass -File '
        '"C:\\Users\\lollo\\MineOcclude-Person-C-C1-C6A\\scripts\\person_c\\run-c6a-after-e-refit.ps1" '
        '-ExecuteScientificCapture'
    )
    c6a_readiness = {
        "schema_version": "person-c-c6a-readiness-after-c1-closure-v0.1",
        "status": "BLOCKED_ONLY_BY_E_HOMOGRAPHY_REFIT",
        "c1_5_first_operator_prerequisite_satisfied": True,
        "c1_5_second_operator_prerequisite_satisfied": True,
        "person_c_c1_stop_gate_closed": True,
        "schedule_version": c6a_manifest["schedule_version"],
        "schedule_set_sha256": C6A_SCHEDULE_SET_SHA256,
        "noise_schedule_still_valid": True,
        "capture_manifest_still_valid": True,
        "capture_manifest": c6a["manifest"],
        "schedule_manifest": c6a["schedule_manifest"],
        "geometry_identity_current": True,
        "jar_identity_current": True,
        "runtime_schedule_hashes_current": True,
        "output_paths_absent": True,
        "execution_command": c6a_command,
        "execution_gate_wrapper": repo_identity(C6A_WRAPPER),
        "execution_authorized_now": False,
        "remaining_blockers": ["E_HOMOGRAPHY_REFIT_AND_VALIDATION_FOR_PERSON_C_LAYOUT_CONFIG_V0_4"],
        "supersession": "This additive readiness record supersedes only the mutable prerequisite status in the v0.2 manifest; the immutable episode plan, schedules, hashes, and historical manifest remain unchanged.",
        "c6a_executed": False,
    }
    closure_status = {
        "schema_version": "person-c-c1-final-closure-status-v0.1",
        "status": "PASS",
        "source_commit": SOURCE_COMMIT,
        "c1_1_complete": True,
        "c1_3_complete": True,
        "c1_5_first_operator_complete": True,
        "c1_5_second_operator_complete": True,
        "c1_5_complete": True,
        "person_c_c1_stop_gate_closed": True,
        "accepted_geometry_version": GEOMETRY_VERSION,
        "accepted_geometry_sha256": GEOMETRY_SHA256,
        "second_operator_success_package_bundle_sha256": second_bundle,
        "e_homography_refit_required": True,
        "e_refit_handoff_package_bundle_sha256": handoff_bundle,
        "c6a_execution_authorized": False,
        "c6a_remaining_blockers": c6a_readiness["remaining_blockers"],
        "historical_evidence_modified": False,
        "c6a_executed": False,
    }
    roadmap = {
        "schema_version": "person-c-roadmap-additive-status-v0.1",
        "milestone": "C1_CLOSED_E_REFIT_HANDOFF_READY",
        "completed": ["C1.1", "C1.3", "C1.5_FIRST_OPERATOR", "C1.5_SECOND_OPERATOR", "C1.5", "PERSON_C_C1_STOP_GATE"],
        "next_owner": "Person E",
        "next_required_action": "REFIT_AND_VALIDATE_ALL_SIX_HOMOGRAPHIES_FOR_PERSON_C_LAYOUT_CONFIG_V0.4",
        "person_c_c6a_state": "READY_BUT_NOT_AUTHORIZED_UNTIL_E_REFIT_VALIDATION",
        "remaining_blockers": c6a_readiness["remaining_blockers"],
        "c6a_execution_command_after_gate_passes": c6a_command,
    }
    closure_validation = {
        "schema_version": "person-c-c1-closure-validation-v0.1",
        "status": "PASS",
        "checks": {
            "c1_1": True, "c1_3": True, "first_operator": True, "second_operator": True,
            "failed_history": True, "geometry": True, "repaired_jar": True,
            "e_handoff": True, "c6a_schedules": True, "c6a_manifest": True,
            "c6a_not_executed": True, "only_e_refit_blocker_remains": True,
        },
    }
    closure_outputs: dict[Path, bytes] = {
        CLOSURE_DIR / "c1_closure_status.json": dump(closure_status),
        CLOSURE_DIR / "roadmap_status.json": dump(roadmap),
        CLOSURE_DIR / "c6a_post_c1_closure_readiness.json": dump(c6a_readiness),
        CLOSURE_DIR / "validation_report.json": dump(closure_validation),
    }
    closure_inventory, closure_bundle = package_inventory(CLOSURE_DIR, closure_outputs)
    closure_outputs[CLOSURE_DIR / "sha256_inventory.json"] = closure_inventory

    outputs = {**second_outputs, **handoff_outputs, **closure_outputs}
    for path, data in outputs.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    print(json.dumps({
        "status": "PASS",
        "second_operator_package_bundle_sha256": second_bundle,
        "e_refit_handoff_bundle_sha256": handoff_bundle,
        "c1_closure_package_bundle_sha256": closure_bundle,
        "c6a_execution_authorized": False,
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
