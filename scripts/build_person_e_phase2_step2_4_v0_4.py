"""Build Person E Phase 2 Step 2.4 v0.4 from repaired layout_03 inputs."""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import platform
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from types import ModuleType
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mineocclude.experiments.registry import (
    formatted_json_bytes,
    hash_json_value,
    write_json_exclusive,
)
from mineocclude.vision.homography import (
    GROUND_CONTACT_LOCALIZATION_METHOD_VERSION,
    HOMOGRAPHY_ALGORITHM_VERSION,
)
from mineocclude.vision.markers import MARKER_DETECTOR_VERSION
from mineocclude.vision.png_decode import PNG_DECODER_VERSION

PERSON_E_STARTING_REVISION = "8e5dcae51d306a450aece4b61353e3c87e0a7efb"
PERSON_C_REVISION = "fa70424530f422a2e6140e0e90d0ff18f583141e"
PERSON_C_PARENT_REVISION = "aa2e8ed127b829092e866af1f2c099acc3a20051"
PERSON_C_REMOTE_REF = "origin/role/person-c-data"
PERSON_C_DEFAULT_REPOSITORY = Path(r"C:\Users\lollo\MineOcclude-Person-C")
CORRECTION_SCHEMA_VERSION = "person-e-phase2-step2.4-correction-v0.4"
MAXIMUM_MEDIAN_WALL_ERROR_BLOCKS = 0.2
MAXIMUM_P95_WALL_ERROR_BLOCKS = 0.5
V0_3_GENERATOR = ROOT / "scripts" / "build_person_e_phase2_step2_4_v0_3.py"
V0_3_EVIDENCE = ROOT / "docs" / "status" / "person_e_phase2_step2_4_v0_3"
V0_4_RECEIPT = "step2_4_v0_4_receipt.json"
V0_3_RECEIPT = "step2_4_v0_3_receipt.json"
CORE_DOCUMENT_NAMES = (
    "detector_outputs.json",
    "homography_correspondences.json",
    "homography_record.json",
    "localization_validation_report.json",
    "phase2_status.json",
    "provenance_index.json",
    "source_validation.json",
    V0_4_RECEIPT,
)
DOCUMENT_NAMES = frozenset((*CORE_DOCUMENT_NAMES, "deterministic_generation.json"))
HISTORICAL_DIRECTORIES = (
    "docs/status/person_e_phase2_v0_1",
    "docs/status/person_e_phase2_step2_4_v0_2",
    "docs/status/person_e_phase2_step2_4_v0_3",
)
EXPECTED_PERSON_C_CHANGED_PATHS = (
    "data/autonomous/layout_03_ep33005/capture_provenance.json",
    "data/autonomous/layout_03_ep33005/frame_map.parquet",
    "data/autonomous/layout_03_ep33005/mineworld_actions.jsonl",
    "data/autonomous/layout_03_ep33005/qa_report_33005.json",
    "data/autonomous/layout_03_ep33005/qa_report_33005.json.sha256",
    "data/autonomous/layout_03_ep33005/video_640x360.mp4",
    "data/autonomous/layout_03_ep33006/capture_provenance.json",
    "data/autonomous/layout_03_ep33006/frame_map.parquet",
    "data/autonomous/layout_03_ep33006/mineworld_actions.jsonl",
    "data/autonomous/layout_03_ep33006/qa_report_33006.json",
    "data/autonomous/layout_03_ep33006/qa_report_33006.json.sha256",
    "data/autonomous/layout_03_ep33006/video_640x360.mp4",
    *(
        f"data/handoff_e/calibration_frames/negative/layout_03/{index:03d}.png"
        for index in range(6)
    ),
    *(
        f"data/handoff_e/calibration_frames/visible/layout_03/{index:03d}.png"
        for index in range(6)
    ),
    "data/handoff_e/detector_calibration_inputs.json",
    "data/handoff_e/independent_probe_points.json",
    "data/handoff_e/markers_layout_03.json",
    "data/handoff_e/provenance_calibration_clean.json",
)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _run_git(repository: Path, arguments: Sequence[str]) -> bytes:
    completed = subprocess.run(
        ["git", "-C", str(repository), *arguments],
        check=False,
        capture_output=True,
    )
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise ValueError(f"Git command failed in {repository}: {detail}")
    return completed.stdout


def _git_blob(repository: Path, revision: str, path: str) -> bytes:
    return _run_git(repository, ["cat-file", "blob", f"{revision}:{path}"])


def _git_json(repository: Path, revision: str, path: str) -> dict[str, Any]:
    payload = _git_blob(repository, revision, path)
    try:
        document = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"Invalid committed JSON {revision}:{path}.") from error
    if not isinstance(document, dict):
        raise TypeError(f"Committed JSON {revision}:{path} must be a mapping.")
    return document


def _historical_paths() -> tuple[str, ...]:
    output = _run_git(
        ROOT,
        [
            "ls-tree",
            "-r",
            "--name-only",
            PERSON_E_STARTING_REVISION,
            "--",
            *HISTORICAL_DIRECTORIES,
        ],
    )
    paths = tuple(output.decode("utf-8").splitlines())
    if not paths:
        raise ValueError("No historical Step 2.4 evidence was found.")
    return paths


def _historical_hashes() -> dict[str, str]:
    expected_paths = _historical_paths()
    current_paths = tuple(
        sorted(
            path.relative_to(ROOT).as_posix()
            for directory in HISTORICAL_DIRECTORIES
            for path in (ROOT / directory).rglob("*")
            if path.is_file()
        )
    )
    if current_paths != tuple(sorted(expected_paths)):
        raise ValueError("The v0.1-v0.3 historical evidence inventory changed.")
    hashes: dict[str, str] = {}
    for path in expected_paths:
        committed = _git_blob(ROOT, PERSON_E_STARTING_REVISION, path)
        current = (ROOT / path).read_bytes()
        if current != committed:
            raise ValueError(f"Historical Step 2.4 evidence changed: {path}.")
        hashes[path] = _sha256(current)
    return hashes


def _records_by_id(
    document: Mapping[str, Any],
    collection: str,
) -> dict[str, Mapping[str, Any]]:
    records = document.get(collection)
    if not isinstance(records, list):
        raise TypeError(f"{collection} must be a list.")
    by_id: dict[str, Mapping[str, Any]] = {}
    for record in records:
        if not isinstance(record, Mapping) or not isinstance(
            record.get("frame_id"), str
        ):
            raise TypeError(f"{collection} contains an invalid frame record.")
        by_id[record["frame_id"]] = record
    if len(by_id) != len(records):
        raise ValueError(f"{collection} contains duplicate frame IDs.")
    return by_id


def _source_delta_validation(repository: Path) -> dict[str, Any]:
    changed_paths = tuple(
        sorted(
            _run_git(
                repository,
                [
                    "diff",
                    "--name-only",
                    PERSON_C_PARENT_REVISION,
                    PERSON_C_REVISION,
                ],
            )
            .decode("utf-8")
            .splitlines()
        )
    )
    if changed_paths != tuple(sorted(EXPECTED_PERSON_C_CHANGED_PATHS)):
        raise ValueError("Person C repair commit changed paths outside the contract.")

    input_path = "data/handoff_e/detector_calibration_inputs.json"
    probe_path = "data/handoff_e/independent_probe_points.json"
    old_source = _records_by_id(
        _git_json(repository, PERSON_C_PARENT_REVISION, input_path),
        "frames",
    )
    new_source = _records_by_id(
        _git_json(repository, PERSON_C_REVISION, input_path),
        "frames",
    )
    old_probes = _records_by_id(
        _git_json(repository, PERSON_C_PARENT_REVISION, probe_path),
        "points",
    )
    new_probes = _records_by_id(
        _git_json(repository, PERSON_C_REVISION, probe_path),
        "points",
    )
    if {
        key: value
        for key, value in old_source.items()
        if value.get("layout_id") != "layout_03"
    } != {
        key: value
        for key, value in new_source.items()
        if value.get("layout_id") != "layout_03"
    }:
        raise ValueError("A non-layout_03 source frame changed.")
    if {
        key: value
        for key, value in old_probes.items()
        if value.get("layout_id") != "layout_03"
    } != {
        key: value
        for key, value in new_probes.items()
        if value.get("layout_id") != "layout_03"
    }:
        raise ValueError("A non-layout_03 probe changed.")

    old_layout_probes = {
        key: value
        for key, value in old_probes.items()
        if value.get("layout_id") == "layout_03"
    }
    new_layout_probes = {
        key: value
        for key, value in new_probes.items()
        if value.get("layout_id") == "layout_03"
    }
    if set(old_layout_probes) != set(new_layout_probes):
        raise ValueError("The layout_03 probe population changed.")
    for frame_id in sorted(old_layout_probes):
        old = old_layout_probes[frame_id]
        new = new_layout_probes[frame_id]
        for field in (
            "split",
            "probe_point_world_xz_blocks",
            "probe_point_world_y_blocks",
        ):
            if old.get(field) != new.get(field):
                raise ValueError(f"{frame_id} frozen probe {field} changed.")

    layout_frames = [
        record
        for record in new_source.values()
        if record.get("layout_id") == "layout_03"
    ]
    split_sequence = [
        new_layout_probes[f"layout_03_visible_{index:03d}"]["split"]
        for index in range(6)
    ]
    if (
        sum(record.get("truth_class") == "visible" for record in layout_frames) != 6
        or sum(record.get("truth_class") == "negative" for record in layout_frames)
        != 6
        or split_sequence != ["calibration"] * 3 + ["heldout"] * 3
        or any(
            record.get("canonical_camera_pose_id")
            != "layout_03_canonical_pose_v1"
            for record in layout_frames
        )
    ):
        raise ValueError("The repaired layout_03 inventory or split changed.")

    markers = _git_json(
        repository,
        PERSON_C_REVISION,
        "data/handoff_e/markers_layout_03.json",
    )
    correspondences = markers.get("marker_correspondences")
    if (
        markers.get("world_coordinate_system")
        != "ground_plane_world_xz_blocks_topface_centre"
        or not isinstance(correspondences, list)
        or len(correspondences) != 4
        or any(
            marker.get("world_point_convention") != "block_top_face_centre"
            for marker in correspondences
        )
    ):
        raise ValueError("The repaired layout_03 marker contract changed.")
    return {
        "parent_revision": PERSON_C_PARENT_REVISION,
        "changed_path_count": len(changed_paths),
        "changed_paths": list(changed_paths),
        "scope_validation_passed": True,
        "non_layout_03_handoff_records_unchanged": True,
        "layout_03_probe_coordinates_unchanged": True,
        "layout_03_split_unchanged": True,
        "layout_03_inventory": {
            "visible_png_count": 6,
            "negative_png_count": 6,
            "marker_correspondence_count": 4,
            "calibration_probe_count": 3,
            "heldout_probe_count": 3,
        },
    }


def _verify_person_c_revision(repository: Path, revision: str) -> None:
    remote = (
        _run_git(repository, ["rev-parse", f"{PERSON_C_REMOTE_REF}^{{commit}}"])
        .decode("ascii")
        .strip()
    )
    parent = (
        _run_git(repository, ["rev-parse", f"{PERSON_C_REVISION}^"])
        .decode("ascii")
        .strip()
    )
    if remote != PERSON_C_REVISION or revision != PERSON_C_REVISION:
        raise ValueError(
            "Person C remote or requested revision is not the exact repaired commit."
        )
    if parent != PERSON_C_PARENT_REVISION:
        raise ValueError("Person C repair commit has an unexpected parent.")
    _run_git(repository, ["cat-file", "-e", f"{revision}^{{commit}}"])
    _source_delta_validation(repository)


def _runtime_identity() -> tuple[dict[str, Any], str]:
    source_paths = (
        "src/mineocclude/vision/png_decode.py",
        "src/mineocclude/vision/markers.py",
        "src/mineocclude/vision/homography.py",
        "scripts/build_person_e_phase2_step2_4_v0_4.py",
    )
    identity = {
        "implementation_base_sha": PERSON_E_STARTING_REVISION,
        "python_implementation": platform.python_implementation(),
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "source_file_sha256": {
            path: _sha256((ROOT / path).read_bytes()) for path in source_paths
        },
        "png_decoder_version": PNG_DECODER_VERSION,
        "marker_detector_version": MARKER_DETECTOR_VERSION,
        "ground_contact_localization_method_version": (
            GROUND_CONTACT_LOCALIZATION_METHOD_VERSION
        ),
        "homography_algorithm_version": HOMOGRAPHY_ALGORITHM_VERSION,
    }
    return identity, hash_json_value(identity)


def _load_v0_3_generator() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "_person_e_step2_4_v0_3_compat",
        V0_3_GENERATOR,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load the v0.3 generator.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.PERSON_E_STARTING_REVISION = PERSON_E_STARTING_REVISION
    module.PERSON_C_REVISION = PERSON_C_REVISION
    module.CORRECTION_SCHEMA_VERSION = CORRECTION_SCHEMA_VERSION
    module.IMMUTABLE_HISTORICAL_PATHS = _historical_paths()
    module._verify_person_c_revision = _verify_person_c_revision
    module._historical_hashes = _historical_hashes
    module._runtime_identity = _runtime_identity
    return module


def _artifact_hash(document: Mapping[str, Any]) -> tuple[str, int]:
    payload = formatted_json_bytes(document)
    return _sha256(payload), len(payload)


def _upgrade_schema_versions(documents: dict[str, dict[str, Any]]) -> None:
    fields = {
        "source_validation.json": "source_validation_schema_version",
        "detector_outputs.json": "detector_output_schema_version",
        "homography_correspondences.json": (
            "homography_correspondence_schema_version"
        ),
        "homography_record.json": "homography_record_schema_version",
        "localization_validation_report.json": (
            "localization_report_schema_version"
        ),
        V0_4_RECEIPT: "receipt_schema_version",
        "provenance_index.json": "provenance_index_schema_version",
        "phase2_status.json": "status_schema_version",
    }
    for name, field in fields.items():
        value = documents[name].get(field)
        if not isinstance(value, str) or "v0.3" not in value:
            raise ValueError(f"{name} lacks its inherited v0.3 schema identity.")
        documents[name][field] = value.replace("v0.3", "v0.4")


def _add_border_validation(detector: dict[str, Any]) -> None:
    layouts = detector.get("marker_layouts")
    if not isinstance(layouts, list):
        raise TypeError("Detector layouts are missing.")
    for layout in layouts:
        for frame in layout["negative_frame_results"]:
            passed = (
                frame.get("status") == "detected"
                and frame.get("marker_count") == 4
                and len(frame.get("markers", [])) == 4
                and frame.get("failures") == []
            )
            frame["border_validation"] = {
                "passed": passed,
                "criterion": (
                    "public_detector_rejects_any_marker_core_touching_frame_border"
                ),
                "all_four_marker_cores_strictly_inside_frame": passed,
            }
    layout_03 = next(
        (layout for layout in layouts if layout.get("layout_id") == "layout_03"),
        None,
    )
    if (
        layout_03 is None
        or layout_03.get("all_negative_frames_detected") is not True
        or any(
            frame["border_validation"]["passed"] is not True
            for frame in layout_03["negative_frame_results"]
        )
    ):
        raise ValueError("Repaired layout_03 did not pass 6/6 four-marker coverage.")


def _refresh_linked_hashes(documents: dict[str, dict[str, Any]]) -> None:
    correspondences_hash, _ = _artifact_hash(
        documents["homography_correspondences.json"]
    )
    documents["homography_record.json"][
        "correspondence_document_hash"
    ] = correspondences_hash
    detector_hash, _ = _artifact_hash(documents["detector_outputs.json"])
    homography_hash, _ = _artifact_hash(documents["homography_record.json"])
    localization = documents["localization_validation_report.json"]
    localization["detector_output_document_hash"] = detector_hash
    localization["homography_document_hash"] = homography_hash

    provenance = documents["provenance_index.json"]
    for record in provenance["records"]:
        if record["path"] == V0_3_RECEIPT:
            record["path"] = V0_4_RECEIPT
        record["artifact_id"] = record["artifact_id"].replace("v0_3", "v0_4")
        record["status"] = "accepted_v0_4_evidence"
        record["direct_inputs"] = [
            value.replace(V0_3_RECEIPT, V0_4_RECEIPT)
            for value in record["direct_inputs"]
        ]
        digest, size = _artifact_hash(documents[record["path"]])
        record["sha256"] = digest
        record["size_bytes"] = size
    provenance_hash, _ = _artifact_hash(provenance)
    documents["phase2_status.json"]["provenance_index_hash"] = provenance_hash


def build_core_documents(
    *,
    person_c_repository: Path,
    person_c_revision: str,
    base_evidence: Path,
    v0_2_evidence: Path,
) -> dict[str, dict[str, Any]]:
    """Build v0.4 using unchanged v0.3 computation and frozen public methods."""

    base = _load_v0_3_generator()
    documents = base.build_core_documents(
        person_c_repository=person_c_repository,
        person_c_revision=person_c_revision,
        base_evidence=base_evidence,
        v0_2_evidence=v0_2_evidence,
    )
    documents[V0_4_RECEIPT] = documents.pop(V0_3_RECEIPT)
    _upgrade_schema_versions(documents)

    delta = _source_delta_validation(person_c_repository)
    source = documents["source_validation.json"]
    source["source_parent_revision"] = PERSON_C_PARENT_REVISION
    source["source_commit_delta_validation"] = delta
    _add_border_validation(documents["detector_outputs.json"])

    receipt = documents[V0_4_RECEIPT]
    receipt["person_c_source_parent_revision"] = PERSON_C_PARENT_REVISION
    correction = receipt["corner_to_top_face_centre_correction"]
    correction["born_correct_recapture_layout_ids"] = ["layout_02", "layout_03"]
    receipt["layout_03_coverage_repair"] = {
        "source_revision": PERSON_C_REVISION,
        "source_parent_revision": PERSON_C_PARENT_REVISION,
        "source_delta_scope_validation_passed": True,
        "previous_blocker": (
            "north-west/blue and north-east/yellow marker cores touched "
            "the image border in every layout_03 negative frame"
        ),
        "repair_result": (
            "the unchanged public detector accepted four marker cores strictly "
            "inside every repaired layout_03 negative frame"
        ),
        "detected_negative_frame_count": 6,
        "required_negative_frame_count": 6,
        "evaluated_probe_count": 6,
        "required_probe_count": 6,
        "probe_coordinates_changed": False,
        "split_membership_changed": False,
    }

    provenance = documents["provenance_index.json"]
    provenance["source_revisions"]["person_c_parent"] = PERSON_C_PARENT_REVISION
    provenance["source_commit_delta_validation"] = delta
    v0_3_status = V0_3_EVIDENCE / "phase2_status.json"
    provenance["unchanged_upstream_evidence"]["previous_v0_3_status_hash"] = _sha256(
        v0_3_status.read_bytes()
    )
    status = documents["phase2_status.json"]
    status["previous_status"] = {
        "path": "../person_e_phase2_step2_4_v0_3/phase2_status.json",
        "sha256": _sha256(v0_3_status.read_bytes()),
        "status": "retained_not_overwritten",
    }
    _refresh_linked_hashes(documents)
    validate_v0_4_documents(documents, require_determinism=False)
    return documents


def validate_v0_4_documents(
    documents: Mapping[str, Mapping[str, Any]],
    *,
    require_determinism: bool = True,
) -> None:
    """Validate v0.4 identity, method integrity, hashes, and measured status."""

    expected = DOCUMENT_NAMES if require_determinism else frozenset(CORE_DOCUMENT_NAMES)
    if set(documents) != expected:
        raise ValueError("The v0.4 evidence document set changed.")
    mutable = copy.deepcopy(dict(documents))
    compatibility = {
        name: document
        for name, document in mutable.items()
        if name != "deterministic_generation.json"
    }
    compatibility[V0_3_RECEIPT] = compatibility.pop(V0_4_RECEIPT)
    base = _load_v0_3_generator()
    base.validate_v0_3_documents(compatibility, require_determinism=False)

    source = documents["source_validation.json"]
    detector = documents["detector_outputs.json"]
    correspondences = documents["homography_correspondences.json"]
    homographies = documents["homography_record.json"]
    localization = documents["localization_validation_report.json"]
    receipt = documents[V0_4_RECEIPT]
    provenance = documents["provenance_index.json"]
    status = documents["phase2_status.json"]
    for document in documents.values():
        if (
            document.get("schema_version") != "1.0"
            or document.get("correction_schema_version")
            != CORRECTION_SCHEMA_VERSION
        ):
            raise ValueError("A v0.4 schema binding changed.")
    if (
        source.get("source_revision") != PERSON_C_REVISION
        or source.get("source_parent_revision") != PERSON_C_PARENT_REVISION
        or source.get("source_commit_delta_validation", {}).get(
            "changed_paths"
        )
        != sorted(EXPECTED_PERSON_C_CHANGED_PATHS)
        or source.get("source_commit_delta_validation", {}).get(
            "scope_validation_passed"
        )
        is not True
    ):
        raise ValueError("Exact source revision, parent, or delta binding changed.")

    layouts = detector.get("marker_layouts", [])
    layout_03 = next(
        (layout for layout in layouts if layout.get("layout_id") == "layout_03"),
        None,
    )
    if (
        detector.get("all_layouts_detected") is not True
        or detector.get("detected_layout_count") != 6
        or detector.get("blocked_layout_count") != 0
        or layout_03 is None
        or layout_03.get("all_negative_frames_detected") is not True
        or len(layout_03.get("negative_frame_results", [])) != 6
        or any(
            frame.get("marker_count") != 4
            or frame.get("border_validation", {}).get("passed") is not True
            or frame.get("border_validation", {}).get(
                "all_four_marker_cores_strictly_inside_frame"
            )
            is not True
            for frame in layout_03["negative_frame_results"]
        )
    ):
        raise ValueError("Layout_03 four-marker border-safe coverage changed.")
    required_gate = localization.get("required_gate", {})
    if (
        localization.get("required_probe_count") != 36
        or localization.get("evaluated_probe_count") != 36
        or localization.get("calibration_probe_count") != 18
        or localization.get("heldout_probe_count") != 18
        or localization.get("coverage_passed") is not True
        or localization.get("all_required_probes_evaluated") is not True
        or required_gate.get("maximum_median_absolute_wall_parallel_error_blocks")
        != MAXIMUM_MEDIAN_WALL_ERROR_BLOCKS
        or required_gate.get(
            "maximum_p95_absolute_wall_parallel_error_blocks_exclusive"
        )
        != MAXIMUM_P95_WALL_ERROR_BLOCKS
    ):
        raise ValueError("Complete coverage or formal thresholds changed.")
    if (
        localization.get("output_bias_adjustment_applied") is not False
        or localization.get("output_offset_blocks") is not None
        or localization.get("probe_targets_used_for_fitting") is not False
        or localization.get("probe_targets_used_for_detector_selection") is not False
        or localization.get("probe_targets_used_for_ground_contact_selection")
        is not False
        or localization.get("probe_targets_used_for_exclusion_selection") is not False
        or localization.get("excluded_layout_ids") != []
    ):
        raise ValueError("A prohibited correction or probe-derived choice appeared.")

    correspondence_hash, _ = _artifact_hash(correspondences)
    detector_hash, _ = _artifact_hash(detector)
    homography_hash, _ = _artifact_hash(homographies)
    provenance_hash, _ = _artifact_hash(provenance)
    if (
        homographies.get("correspondence_document_hash") != correspondence_hash
        or localization.get("detector_output_document_hash") != detector_hash
        or localization.get("homography_document_hash") != homography_hash
        or status.get("provenance_index_hash") != provenance_hash
    ):
        raise ValueError("An evidence hash link changed.")
    for record in provenance.get("records", []):
        digest, size = _artifact_hash(documents[record["path"]])
        if record.get("sha256") != digest or record.get("size_bytes") != size:
            raise ValueError("A provenance record does not match its artifact.")

    records = localization.get("records", [])
    base_summary = base._metric_summary(records)
    measured_pass = (
        len(records) == 36
        and base_summary["median_absolute_wall_parallel_error_blocks"]
        <= MAXIMUM_MEDIAN_WALL_ERROR_BLOCKS
        and base_summary["p95_absolute_wall_parallel_error_blocks"]
        < MAXIMUM_P95_WALL_ERROR_BLOCKS
    )
    step_by_id = {step["step"]: step for step in status.get("steps", [])}
    if (
        localization.get("formal_planning_gate_passed") is not measured_pass
        or localization.get("planning_gate_passed") is not measured_pass
        or step_by_id.get("2.4", {}).get("status")
        != ("PASS" if measured_pass else "PARTIAL")
        or status.get("overall_status") != ("PASS" if measured_pass else "PARTIAL")
    ):
        raise ValueError("Status is not derived strictly from measured formal gates.")
    historical_hashes = _historical_hashes()
    if (
        receipt.get("historical_step2_4_evidence_immutable") is not True
        or receipt.get("historical_step2_4_sha256") != historical_hashes
        or provenance.get("historical_step2_4_sha256") != historical_hashes
    ):
        raise ValueError("v0.1-v0.3 immutability evidence changed.")

    if require_determinism:
        determinism = documents["deterministic_generation.json"]
        expected_hashes = {
            name: _sha256(formatted_json_bytes(documents[name]))
            for name in CORE_DOCUMENT_NAMES
        }
        if (
            determinism.get("byte_identical") is not True
            or determinism.get("compared_document_count") != len(CORE_DOCUMENT_NAMES)
            or determinism.get("first_generation_sha256") != expected_hashes
            or determinism.get("second_generation_sha256") != expected_hashes
        ):
            raise ValueError("Deterministic regeneration evidence changed.")


def attest_determinism(
    first_dir: Path,
    second_dir: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """Compare two core generations and write the stable v0.4 attestation."""

    first_hashes: dict[str, str] = {}
    second_hashes: dict[str, str] = {}
    for name in CORE_DOCUMENT_NAMES:
        first = (first_dir / name).read_bytes()
        second = (second_dir / name).read_bytes()
        output = (output_dir / name).read_bytes()
        if first != second or first != output:
            raise ValueError(f"Deterministic regeneration mismatch: {name}.")
        first_hashes[name] = _sha256(first)
        second_hashes[name] = _sha256(second)
    document = {
        "schema_version": "1.0",
        "correction_schema_version": CORRECTION_SCHEMA_VERSION,
        "deterministic_generation_schema_version": (
            "person-e-deterministic-generation-v0.4"
        ),
        "generation_labels": [
            "independent_regeneration_a",
            "independent_regeneration_b",
        ],
        "compared_document_count": len(CORE_DOCUMENT_NAMES),
        "first_generation_sha256": first_hashes,
        "second_generation_sha256": second_hashes,
        "byte_identical": first_hashes == second_hashes,
        "canonical_json_required": True,
    }
    write_json_exclusive(output_dir / "deterministic_generation.json", document)
    documents = {
        path.name: json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(output_dir.glob("*.json"))
    }
    validate_v0_4_documents(documents)
    return document


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build or attest deterministic Person E Phase 2 Step 2.4 v0.4 evidence."
        )
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    generate = subparsers.add_parser("generate")
    generate.add_argument("output_dir", type=Path)
    generate.add_argument(
        "--person-c-repository",
        type=Path,
        default=PERSON_C_DEFAULT_REPOSITORY,
    )
    generate.add_argument("--person-c-revision", default=PERSON_C_REVISION)
    generate.add_argument(
        "--base-evidence",
        type=Path,
        default=ROOT / "docs" / "status" / "person_e_phase2_v0_1",
    )
    generate.add_argument(
        "--v0-2-evidence",
        type=Path,
        default=ROOT / "docs" / "status" / "person_e_phase2_step2_4_v0_2",
    )
    attest = subparsers.add_parser("attest-determinism")
    attest.add_argument("first_dir", type=Path)
    attest.add_argument("second_dir", type=Path)
    attest.add_argument("output_dir", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.command == "generate":
        documents = build_core_documents(
            person_c_repository=args.person_c_repository,
            person_c_revision=args.person_c_revision,
            base_evidence=args.base_evidence,
            v0_2_evidence=args.v0_2_evidence,
        )
        for relative_path, document in sorted(documents.items()):
            write_json_exclusive(args.output_dir / relative_path, document)
        return
    attest_determinism(args.first_dir, args.second_dir, args.output_dir)


if __name__ == "__main__":
    main()
