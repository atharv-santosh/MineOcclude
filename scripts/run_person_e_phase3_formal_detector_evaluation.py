"""Run the single authorized Detector v1 untouched-test evaluation.

This script deliberately separates inference from truth joining. During the
inference loop, the detector receives only decoded RGB pixels and frozen
settings. Each outcome is appended to an fsync'd truth-free journal. Truth
artifacts are opened only after all 48 inference outcomes are durably recorded.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import subprocess
import sys
import traceback
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path
from typing import Any

PERSON_E_BRANCH = "role/person-e-operations"
PERSON_E_FREEZE_COMMIT = "3930669eddc026ecb081e947f71f1855a7415904"
PERSON_C_PACKAGE_COMMIT = "3ba6c091426a537d60c950dd1bb38f5fc02826d5"
PERSON_C_REGISTER_COMMIT = "51c98aaa0a97257a6a4c9a979da8922f326ae6ee"
PERSON_C_PREDECLARATION_COMMIT = "24791b155a8962adce451a804a2bad94165392cc"
PACKAGE_ID = "person-c-phase3-detector-v1-untouched-test-v0_3"
PACKAGE_RELATIVE_PATH = Path(
    "data/handoff_e/phase3_detector_v1_untouched_test_v0_3"
)
EXPECTED_PNG_INVENTORY_SHA256 = (
    "54fdfd69673404773395e11f7b60bad8f048b005e97d8c624672417a803c5700"
)
EXPECTED_DETECTOR_ALGORITHM = "hsv-largest-valid-blob-v1.0-candidate"
EXPECTED_DETECTOR_VERSION = (
    "hsv-largest-valid-blob-v1.0-candidate:sha256:"
    "0cadf618fca1578196bde4982021c38627ccb9c39e46353812e7da3fce6aa125"
)
EXPECTED_IDENTITY_SHA256 = (
    "0cadf618fca1578196bde4982021c38627ccb9c39e46353812e7da3fce6aa125"
)
EXPECTED_CONFIG_SHA256 = (
    "acfecd659958891eaee0d582c946abdfaaf47d1ab3307a24f7652e634c045bfa"
)
EXPECTED_SETTINGS_SHA256 = (
    "0dbb426adf99f53455eea04c4aaeb56f3cb22cbc351d87269bb605445eb8f2ea"
)
EXPECTED_IMPLEMENTATION_SHA256 = (
    "026f3b9f25c8aef7ac43fada5b8de92662b605af4868f930698651e59a228214"
)
EXPECTED_PYARROW_VERSION = "25.0.0"
FORMAL_RUN_ORDINAL = 1
EXPECTED_FRAME_COUNT = 48


class FormalEvaluationError(RuntimeError):
    """Raised when the authorized formal run cannot proceed safely."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Execute the single authorized formal Detector v1 evaluation. "
            "The output directory must not exist."
        )
    )
    parser.add_argument("--person-e-repository", type=Path, required=True)
    parser.add_argument("--person-c-worktree", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument(
        "--formal-run-ordinal",
        type=int,
        required=True,
        choices=(FORMAL_RUN_ORDINAL,),
    )
    return parser.parse_args()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FormalEvaluationError(message)


def _canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
            sort_keys=True,
        ).encode("utf-8")
        + b"\n"
    )


def _journal_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        + b"\n"
    )


def _write_bytes_exclusive(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    try:
        with os.fdopen(descriptor, "wb", closefd=True) as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        try:
            os.close(descriptor)
        except OSError:
            pass
        raise


def _write_json_exclusive(path: Path, value: Any) -> None:
    _write_bytes_exclusive(path, _canonical_json_bytes(value))


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _load_json(path: Path, name: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise FormalEvaluationError(f"Could not load {name}: {error}") from error
    if not isinstance(value, dict):
        raise FormalEvaluationError(f"{name} must contain one mapping.")
    return value


def _git(repository: Path, *arguments: str) -> str:
    process = subprocess.run(
        ["git", "-C", str(repository), *arguments],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if process.returncode != 0:
        raise FormalEvaluationError(
            f"git {' '.join(arguments)} failed: {process.stderr.strip()}"
        )
    return process.stdout.strip()


def _utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def _package_inventory_sha256(rows: Sequence[Mapping[str, Any]]) -> str:
    """Hash sorted ``frame_id:png_sha256`` entries without a trailing newline."""

    lines = [
        f"{row['frame_id']}:{row['sha256']}"
        for row in sorted(rows, key=lambda item: item["frame_id"])
    ]
    return _sha256_bytes("\n".join(lines).encode("utf-8"))


def _installed_version(distribution: str) -> str | None:
    try:
        return importlib.metadata.version(distribution)
    except importlib.metadata.PackageNotFoundError:
        return None


def _runtime_versions() -> dict[str, str | None]:
    return {
        "python": platform.python_version(),
        "numpy": _installed_version("numpy"),
        "pandas": _installed_version("pandas"),
        "pyarrow": _installed_version("pyarrow"),
        "opencv": (
            _installed_version("opencv-python")
            or _installed_version("opencv-python-headless")
        ),
    }


def _validate_png_header(payload: bytes, frame_id: str) -> None:
    _require(payload.startswith(b"\x89PNG\r\n\x1a\n"), f"{frame_id} is not PNG.")
    _require(len(payload) >= 33, f"{frame_id} PNG is truncated.")
    _require(payload[12:16] == b"IHDR", f"{frame_id} has no leading IHDR.")
    width = int.from_bytes(payload[16:20], "big")
    height = int.from_bytes(payload[20:24], "big")
    bit_depth = payload[24]
    colour_type = payload[25]
    _require(
        (width, height, bit_depth, colour_type) == (640, 360, 8, 2),
        f"{frame_id} is not a 640x360 8-bit RGB PNG.",
    )


def _load_inference_rows(
    person_c_worktree: Path,
    package_root: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    capture_path = package_root / "untouched_test_capture_provenance.json"
    index_path = package_root / "untouched_test_provenance_index.json"
    capture = _load_json(capture_path, "capture provenance")
    index = _load_json(index_path, "provenance index")
    _require(capture.get("package_id") == PACKAGE_ID, "Capture package ID changed.")
    _require(index.get("package_id") == PACKAGE_ID, "Index package ID changed.")
    capture_rows = capture.get("frames")
    index_rows = index.get("index")
    _require(
        isinstance(capture_rows, list) and len(capture_rows) == EXPECTED_FRAME_COUNT,
        "Capture provenance must contain exactly 48 rows.",
    )
    _require(
        isinstance(index_rows, list) and len(index_rows) == EXPECTED_FRAME_COUNT,
        "Provenance index must contain exactly 48 rows.",
    )
    forbidden_truth_fields = {"truth_class", "truth_present", "target_magenta_sheep_present"}
    rows: list[dict[str, Any]] = []
    for index_number, row in enumerate(capture_rows):
        _require(isinstance(row, Mapping), f"Capture row {index_number} is invalid.")
        _require(
            not (forbidden_truth_fields & set(row)),
            "Truth fields are present in the inference source.",
        )
        required = {"frame_id", "source_relative_path", "sha256"}
        _require(required <= set(row), f"Capture row {index_number} is incomplete.")
        frame_id = row["frame_id"]
        source_relative_path = row["source_relative_path"]
        declared_sha256 = row["sha256"]
        _require(isinstance(frame_id, str) and frame_id, "frame_id is invalid.")
        _require(
            isinstance(source_relative_path, str) and source_relative_path,
            f"{frame_id} source path is invalid.",
        )
        relative = Path(source_relative_path)
        _require(
            not relative.is_absolute() and ".." not in relative.parts,
            f"{frame_id} source path is unsafe.",
        )
        _require(
            isinstance(declared_sha256, str)
            and len(declared_sha256) == 64
            and declared_sha256 == declared_sha256.lower(),
            f"{frame_id} SHA-256 is invalid.",
        )
        source_path = person_c_worktree / relative
        payload = source_path.read_bytes()
        actual_sha256 = _sha256_bytes(payload)
        _require(
            actual_sha256 == declared_sha256,
            f"{frame_id} committed PNG SHA-256 changed.",
        )
        _validate_png_header(payload, frame_id)
        rows.append(
            {
                "frame_id": frame_id,
                "source_relative_path": source_relative_path,
                "source_path": source_path,
                "sha256": actual_sha256,
            }
        )
    ordered = sorted(rows, key=lambda item: item["frame_id"])
    frame_ids = [row["frame_id"] for row in ordered]
    hashes = [row["sha256"] for row in ordered]
    _require(len(set(frame_ids)) == EXPECTED_FRAME_COUNT, "Frame IDs repeat.")
    _require(len(set(hashes)) == EXPECTED_FRAME_COUNT, "PNG hashes repeat.")
    index_projection = sorted(
        (
            row["frame_id"],
            row["source_relative_path"],
            row["sha256"],
        )
        for row in index_rows
    )
    capture_projection = sorted(
        (row["frame_id"], row["source_relative_path"], row["sha256"])
        for row in ordered
    )
    _require(
        index_projection == capture_projection,
        "Capture provenance and provenance index disagree.",
    )
    inventory_sha256 = _package_inventory_sha256(ordered)
    _require(
        inventory_sha256 == EXPECTED_PNG_INVENTORY_SHA256,
        "PNG inventory SHA-256 changed.",
    )
    return ordered, {
        "capture_provenance_path": str(capture_path.relative_to(person_c_worktree)).replace(
            "\\", "/"
        ),
        "capture_provenance_sha256": _sha256_file(capture_path),
        "provenance_index_path": str(index_path.relative_to(person_c_worktree)).replace(
            "\\", "/"
        ),
        "provenance_index_sha256": _sha256_file(index_path),
        "png_inventory_sha256": inventory_sha256,
    }


def _validate_candidate(
    person_e_repository: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    sys.path.insert(0, str(person_e_repository / "src"))
    from mineocclude.experiments.registry import hash_json_value

    evidence_root = (
        person_e_repository
        / "docs/status/person_e_phase3_step3_1_candidate_freeze_v0_1"
    )
    config_path = evidence_root / "detector_candidate_config.json"
    version_path = evidence_root / "detector_candidate_version_record.json"
    config = _load_json(config_path, "frozen candidate config")
    version = _load_json(version_path, "frozen candidate version")
    implementation_sha256 = _sha256_file(
        person_e_repository / "src/mineocclude/vision/magenta.py"
    )
    computed = {
        "identity_sha256": hash_json_value(version["identity"]),
        "config_sha256": hash_json_value(config["configuration"]),
        "settings_sha256": hash_json_value(
            config["configuration"]["detector_settings"]
        ),
        "implementation_sha256": implementation_sha256,
    }
    expected = {
        "identity_sha256": EXPECTED_IDENTITY_SHA256,
        "config_sha256": EXPECTED_CONFIG_SHA256,
        "settings_sha256": EXPECTED_SETTINGS_SHA256,
        "implementation_sha256": EXPECTED_IMPLEMENTATION_SHA256,
    }
    declared = {
        "identity_sha256": version.get("detector_identity_sha256"),
        "config_sha256": version.get("detector_config_sha256"),
        "settings_sha256": version.get("detector_settings_sha256"),
        "implementation_sha256": version.get("detector_implementation_sha256"),
    }
    _require(computed == expected == declared, "Frozen detector hashes changed.")
    _require(
        version.get("detector_algorithm_id") == EXPECTED_DETECTOR_ALGORITHM,
        "Frozen detector algorithm changed.",
    )
    _require(
        version.get("detector_version") == EXPECTED_DETECTOR_VERSION,
        "Frozen detector version changed.",
    )
    _require(
        version.get("pyarrow_version") == EXPECTED_PYARROW_VERSION,
        "Frozen PyArrow binding changed.",
    )
    return config, version, {
        "config_path": str(config_path.relative_to(person_e_repository)).replace(
            "\\", "/"
        ),
        "config_file_sha256": _sha256_file(config_path),
        "version_path": str(version_path.relative_to(person_e_repository)).replace(
            "\\", "/"
        ),
        "version_file_sha256": _sha256_file(version_path),
        "computed_hashes": computed,
    }


def _preflight(args: argparse.Namespace) -> dict[str, Any]:
    person_e_repository = args.person_e_repository.resolve()
    person_c_worktree = args.person_c_worktree.resolve()
    output_directory = args.output_dir.resolve()
    _require(
        args.formal_run_ordinal == FORMAL_RUN_ORDINAL,
        "Formal run ordinal must be exactly one.",
    )
    _require(
        args.run_id == "person-e-phase3-step3-1-v0_3-formal-ordinal-1",
        "Formal run ID changed.",
    )
    _require(person_e_repository.is_dir(), "Person E repository is missing.")
    _require(person_c_worktree.is_dir(), "Person C worktree is missing.")
    _require(not output_directory.exists(), "Formal result output already exists.")
    _require(
        _git(person_e_repository, "branch", "--show-current") == PERSON_E_BRANCH,
        "Person E branch changed.",
    )
    _require(
        _git(person_e_repository, "rev-parse", "HEAD") == PERSON_E_FREEZE_COMMIT,
        "Person E local HEAD changed.",
    )
    _require(
        _git(
            person_e_repository,
            "rev-parse",
            f"origin/{PERSON_E_BRANCH}",
        )
        == PERSON_E_FREEZE_COMMIT,
        "Person E remote HEAD changed.",
    )
    _require(
        _git(person_e_repository, "status", "--porcelain=v1", "--untracked-files=all")
        == "",
        "Person E worktree is not clean.",
    )
    _require(
        _git(person_e_repository, "diff", "--cached", "--name-only") == "",
        "Person E staged state is not empty.",
    )
    _require(
        _git(person_c_worktree, "rev-parse", "HEAD") == PERSON_C_PACKAGE_COMMIT,
        "Person C package worktree HEAD changed.",
    )
    _require(
        _git(person_c_worktree, "branch", "--show-current") == "",
        "Person C package worktree is not detached.",
    )
    _require(
        _git(person_c_worktree, "status", "--porcelain=v1", "--untracked-files=all")
        == "",
        "Person C package worktree is not clean/read-only.",
    )
    _require(
        _git(person_c_worktree, "rev-parse", f"{PERSON_C_PACKAGE_COMMIT}^")
        == PERSON_C_REGISTER_COMMIT,
        "Person C direct package parent changed.",
    )
    package_root = person_c_worktree / PACKAGE_RELATIVE_PATH
    _require(package_root.is_dir(), "Accepted Person C package is missing.")
    config, version, candidate_binding = _validate_candidate(person_e_repository)
    inference_rows, package_binding = _load_inference_rows(
        person_c_worktree,
        package_root,
    )
    runtime = _runtime_versions()
    _require(
        runtime["pyarrow"] == EXPECTED_PYARROW_VERSION,
        "Runtime PyArrow version changed.",
    )
    return {
        "person_e_repository": person_e_repository,
        "person_c_worktree": person_c_worktree,
        "package_root": package_root,
        "output_directory": output_directory,
        "run_id": args.run_id,
        "config": config,
        "version": version,
        "candidate_binding": candidate_binding,
        "inference_rows": inference_rows,
        "package_binding": package_binding,
        "runtime": runtime,
        "orchestration_script_sha256": _sha256_file(Path(__file__).resolve()),
    }


def _detector_arguments(config: Mapping[str, Any]) -> dict[str, Any]:
    from mineocclude.vision.magenta import HsvRange

    settings = config["configuration"]["detector_settings"]
    return {
        "hsv_ranges": tuple(HsvRange(*values) for values in settings["hsv_ranges"]),
        "min_area_pixels": settings["min_area_pixels"],
        "max_area_pixels": settings["max_area_pixels"],
        "open_iterations": settings["open_iterations"],
        "close_iterations": settings["close_iterations"],
        "morphology_radius_pixels": settings["morphology_radius_pixels"],
        "connectivity": settings["connectivity"],
    }


def _raw_outcome(
    inference_row: Mapping[str, Any],
    result: Any,
    *,
    ordinal: int,
) -> dict[str, Any]:
    centroid = result.centroid_xy
    box = result.bounding_box_xyxy
    selected_fraction = (
        None
        if result.area_pixels is None or result.threshold_match_pixels == 0
        else result.area_pixels / result.threshold_match_pixels
    )
    return {
        "outcome_ordinal": ordinal,
        "frame_id": inference_row["frame_id"],
        "source_relative_png_path": inference_row["source_relative_path"],
        "png_sha256": inference_row["sha256"],
        "detected_present": result.detected,
        "detector_status": result.status,
        "centroid_x": None if centroid is None else centroid[0],
        "centroid_y": None if centroid is None else centroid[1],
        "selected_bounding_box_xyxy": None if box is None else list(box),
        "selected_blob_area_pixels": result.area_pixels,
        "rejection_reason": result.rejection_reason,
        "threshold_match_pixels": result.threshold_match_pixels,
        "candidate_blob_count": result.candidate_blob_count,
        "selected_blob_fraction_of_threshold_matches": selected_fraction,
    }


def _load_truth_after_inference(
    package_root: Path,
    raw_outcomes: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    final_path = package_root / "untouched_test_final_manifest.json"
    truth_path = package_root / "untouched_test_truth_records.json"
    frame_path = package_root / "untouched_test_frame_manifest.json"
    final = _load_json(final_path, "final manifest")
    truth = _load_json(truth_path, "truth records")
    frame_manifest = _load_json(frame_path, "frozen frame manifest")
    _require(final.get("package_id") == PACKAGE_ID, "Final package ID changed.")
    _require(truth.get("package_id") == PACKAGE_ID, "Truth package ID changed.")
    _require(
        frame_manifest.get("package_id") == PACKAGE_ID,
        "Frame manifest package ID changed.",
    )
    final_rows = final.get("frames")
    truth_rows = truth.get("records")
    planned_rows = frame_manifest.get("frames")
    _require(
        isinstance(final_rows, list) and len(final_rows) == EXPECTED_FRAME_COUNT,
        "Final manifest must contain exactly 48 rows.",
    )
    _require(
        isinstance(truth_rows, list) and len(truth_rows) == EXPECTED_FRAME_COUNT,
        "Truth records must contain exactly 48 rows.",
    )
    _require(
        isinstance(planned_rows, list) and len(planned_rows) == EXPECTED_FRAME_COUNT,
        "Frozen frame manifest must contain exactly 48 rows.",
    )
    final_by_id = {row["frame_id"]: row for row in final_rows}
    truth_by_id = {row["frame_id"]: row for row in truth_rows}
    planned_by_id = {row["frame_id"]: row for row in planned_rows}
    outcome_ids = {row["frame_id"] for row in raw_outcomes}
    _require(
        len(final_by_id)
        == len(truth_by_id)
        == len(planned_by_id)
        == EXPECTED_FRAME_COUNT,
        "Truth identity duplicates exist.",
    )
    _require(
        set(final_by_id) == set(truth_by_id) == set(planned_by_id) == outcome_ids,
        "Inference and truth identity coverage differs.",
    )
    joined: list[dict[str, Any]] = []
    for outcome in sorted(raw_outcomes, key=lambda row: row["frame_id"]):
        frame_id = outcome["frame_id"]
        final_row = final_by_id[frame_id]
        truth_row = truth_by_id[frame_id]
        planned_row = planned_by_id[frame_id]
        _require(
            final_row["sha256"] == outcome["png_sha256"],
            f"{frame_id} truth join PNG hash changed.",
        )
        _require(
            final_row["source_relative_path"]
            == outcome["source_relative_png_path"],
            f"{frame_id} truth join path changed.",
        )
        for key in ("layout_id", "truth_class", "truth_present"):
            _require(
                final_row[key] == truth_row[key] == planned_row[key],
                f"{frame_id} {key} truth authorities disagree.",
            )
        _require(
            truth_row["canonical_camera_pose_id"]
            == planned_row["canonical_camera_pose_id"],
            f"{frame_id} camera pose authorities disagree.",
        )
        joined.append(
            {
                **dict(outcome),
                "layout_id": truth_row["layout_id"],
                "truth_class": truth_row["truth_class"],
                "truth_present": truth_row["truth_present"],
                "canonical_camera_pose_id": truth_row[
                    "canonical_camera_pose_id"
                ],
                "image_region": planned_row["image_region_stratum"],
                "background_stratum": planned_row["scene_element_stratum"],
                "visible_negative_pairing_id": final_row[
                    "visible_negative_pairing_id"
                ],
            }
        )
    truth_counts = Counter(row["truth_present"] for row in joined)
    _require(truth_counts == {True: 24, False: 24}, "Truth balance changed.")
    per_layout = Counter(
        (row["layout_id"], row["truth_present"]) for row in joined
    )
    _require(
        {row["layout_id"] for row in joined}
        == {f"layout_{index:02d}" for index in range(1, 7)},
        "Layout coverage changed.",
    )
    _require(
        all(
            per_layout[(f"layout_{index:02d}", truth)] == 4
            for index in range(1, 7)
            for truth in (False, True)
        ),
        "Per-layout truth balance changed.",
    )
    pair_counts: dict[str, list[bool]] = {}
    for row in joined:
        pair_counts.setdefault(row["visible_negative_pairing_id"], []).append(
            row["truth_present"]
        )
    _require(
        len(pair_counts) == 24
        and all(sorted(values) == [False, True] for values in pair_counts.values()),
        "Present/absent pairing changed.",
    )
    return joined, {
        "final_manifest_sha256": _sha256_file(final_path),
        "truth_records_sha256": _sha256_file(truth_path),
        "frame_manifest_sha256": _sha256_file(frame_path),
    }


def _classification(truth_present: bool, detected_present: bool) -> str:
    if truth_present and detected_present:
        return "TP"
    if not truth_present and detected_present:
        return "FP"
    if not truth_present and not detected_present:
        return "TN"
    return "FN"


def _fraction_record(numerator: int, denominator: int) -> dict[str, Any]:
    _require(denominator > 0, "Formal metric denominator is zero.")
    value = Fraction(numerator, denominator)
    return {
        "numerator": numerator,
        "denominator": denominator,
        "fraction": f"{value.numerator}/{value.denominator}",
        "decimal": numerator / denominator,
    }


def _confusion(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    counts = Counter(record["classification"] for record in records)
    tp = counts["TP"]
    fp = counts["FP"]
    tn = counts["TN"]
    fn = counts["FN"]
    return {
        "total_frames": len(records),
        "true_positive": tp,
        "false_positive": fp,
        "true_negative": tn,
        "false_negative": fn,
        "precision": _fraction_record(tp, tp + fp),
        "recall": _fraction_record(tp, tp + fn),
    }


def _final_records(
    joined: Sequence[Mapping[str, Any]],
    *,
    context: Mapping[str, Any],
    evaluation_start_utc: str,
    evaluation_end_utc: str,
) -> list[dict[str, Any]]:
    runtime = context["runtime"]
    records: list[dict[str, Any]] = []
    for row in joined:
        detected = row["detected_present"]
        records.append(
            {
                "package_id": PACKAGE_ID,
                "package_commit": PERSON_C_PACKAGE_COMMIT,
                "frame_id": row["frame_id"],
                "layout_id": row["layout_id"],
                "canonical_camera_pose_id": row["canonical_camera_pose_id"],
                "truth_class": row["truth_class"],
                "truth_present": row["truth_present"],
                "source_relative_png_path": row["source_relative_png_path"],
                "png_sha256": row["png_sha256"],
                "detector_algorithm": EXPECTED_DETECTOR_ALGORITHM,
                "detector_version": EXPECTED_DETECTOR_VERSION,
                "detector_identity_sha256": EXPECTED_IDENTITY_SHA256,
                "detector_config_sha256": EXPECTED_CONFIG_SHA256,
                "detector_settings_sha256": EXPECTED_SETTINGS_SHA256,
                "detector_implementation_sha256": (
                    EXPECTED_IMPLEMENTATION_SHA256
                ),
                "detected_present": detected,
                "accepted": detected,
                "rejected": not detected,
                "disposition": "accepted" if detected else "rejected",
                "detector_status": row["detector_status"],
                "centroid_x": row["centroid_x"],
                "centroid_y": row["centroid_y"],
                "selected_bounding_box_xyxy": row[
                    "selected_bounding_box_xyxy"
                ],
                "selected_blob_area_pixels": row[
                    "selected_blob_area_pixels"
                ],
                "rejection_reason": row["rejection_reason"],
                "threshold_match_pixels": row["threshold_match_pixels"],
                "threshold_match_fraction": (
                    row["threshold_match_pixels"] / (640 * 360)
                ),
                "candidate_blob_count": row["candidate_blob_count"],
                "selected_blob_fraction_of_threshold_matches": row[
                    "selected_blob_fraction_of_threshold_matches"
                ],
                "image_region": row["image_region"],
                "background_stratum": row["background_stratum"],
                "classification": _classification(
                    row["truth_present"],
                    detected,
                ),
                "run_id": context["run_id"],
                "formal_run_ordinal": FORMAL_RUN_ORDINAL,
                "evaluation_start_utc": evaluation_start_utc,
                "evaluation_end_utc": evaluation_end_utc,
                "runtime_python_version": runtime["python"],
                "runtime_numpy_version": runtime["numpy"],
                "runtime_pandas_version": runtime["pandas"],
                "runtime_pyarrow_version": runtime["pyarrow"],
                "runtime_opencv_version": runtime["opencv"],
                "source_commit": PERSON_E_FREEZE_COMMIT,
                "test_package_commit": PERSON_C_PACKAGE_COMMIT,
                "truth_exposed_to_detector": False,
                "candidate_version_record_sha256": context[
                    "candidate_binding"
                ]["version_file_sha256"],
            }
        )
    return records


def _parquet_bytes(records: Sequence[Mapping[str, Any]]) -> bytes:
    import pyarrow as pa
    import pyarrow.parquet as pq

    fields = [
        ("package_id", pa.string(), False),
        ("package_commit", pa.string(), False),
        ("frame_id", pa.string(), False),
        ("layout_id", pa.string(), False),
        ("canonical_camera_pose_id", pa.string(), False),
        ("truth_class", pa.string(), False),
        ("truth_present", pa.bool_(), False),
        ("source_relative_png_path", pa.string(), False),
        ("png_sha256", pa.string(), False),
        ("detector_algorithm", pa.string(), False),
        ("detector_version", pa.string(), False),
        ("detector_identity_sha256", pa.string(), False),
        ("detector_config_sha256", pa.string(), False),
        ("detector_settings_sha256", pa.string(), False),
        ("detector_implementation_sha256", pa.string(), False),
        ("detected_present", pa.bool_(), False),
        ("accepted", pa.bool_(), False),
        ("rejected", pa.bool_(), False),
        ("disposition", pa.string(), False),
        ("detector_status", pa.string(), False),
        ("centroid_x", pa.float64(), True),
        ("centroid_y", pa.float64(), True),
        ("bbox_x_min", pa.int64(), True),
        ("bbox_y_min", pa.int64(), True),
        ("bbox_x_max_exclusive", pa.int64(), True),
        ("bbox_y_max_exclusive", pa.int64(), True),
        ("selected_blob_area_pixels", pa.int64(), True),
        ("rejection_reason", pa.string(), True),
        ("threshold_match_pixels", pa.int64(), False),
        ("threshold_match_fraction", pa.float64(), False),
        ("candidate_blob_count", pa.int64(), False),
        (
            "selected_blob_fraction_of_threshold_matches",
            pa.float64(),
            True,
        ),
        ("image_region", pa.string(), False),
        ("background_stratum", pa.string(), False),
        ("classification", pa.string(), False),
        ("run_id", pa.string(), False),
        ("formal_run_ordinal", pa.int64(), False),
        ("evaluation_start_utc", pa.string(), False),
        ("evaluation_end_utc", pa.string(), False),
        ("runtime_python_version", pa.string(), False),
        ("runtime_numpy_version", pa.string(), False),
        ("runtime_pandas_version", pa.string(), False),
        ("runtime_pyarrow_version", pa.string(), False),
        ("runtime_opencv_version", pa.string(), False),
        ("source_commit", pa.string(), False),
        ("test_package_commit", pa.string(), False),
        ("truth_exposed_to_detector", pa.bool_(), False),
        ("candidate_version_record_sha256", pa.string(), False),
    ]
    schema = pa.schema(
        [pa.field(name, kind, nullable=nullable) for name, kind, nullable in fields],
        metadata={
            b"schema_version": b"person-e-phase3-formal-detection-record-v1.0",
            b"package_id": PACKAGE_ID.encode("utf-8"),
            b"package_commit": PERSON_C_PACKAGE_COMMIT.encode("ascii"),
            b"detector_version": EXPECTED_DETECTOR_VERSION.encode("ascii"),
            b"formal_run_ordinal": b"1",
        },
    )
    parquet_rows: list[dict[str, Any]] = []
    for record in records:
        box = record["selected_bounding_box_xyxy"]
        parquet_rows.append(
            {
                **{
                    name: record[name]
                    for name, _, _ in fields
                    if name
                    not in {
                        "bbox_x_min",
                        "bbox_y_min",
                        "bbox_x_max_exclusive",
                        "bbox_y_max_exclusive",
                    }
                },
                "bbox_x_min": None if box is None else box[0],
                "bbox_y_min": None if box is None else box[1],
                "bbox_x_max_exclusive": None if box is None else box[2],
                "bbox_y_max_exclusive": None if box is None else box[3],
            }
        )
    table = pa.Table.from_pylist(parquet_rows, schema=schema)
    sink = pa.BufferOutputStream()
    pq.write_table(
        table,
        sink,
        compression="NONE",
        use_dictionary=False,
        write_statistics=False,
        version="2.6",
        data_page_version="1.0",
        row_group_size=1024,
        write_batch_size=1024,
        store_schema=True,
        write_page_index=False,
        write_page_checksum=False,
        use_byte_stream_split=False,
    )
    return sink.getvalue().to_pybytes()


def _formal_run(context: Mapping[str, Any], argv: Sequence[str]) -> None:
    from mineocclude.vision.calibration import decode_png_rgb_bytes
    from mineocclude.vision.magenta import detect_magenta

    output_directory: Path = context["output_directory"]
    output_directory.mkdir(parents=True, exist_ok=False)
    start_utc = _utc_now()
    rendered_command = subprocess.list2cmdline([sys.executable, *argv])
    start_receipt = {
        "schema_version": "1.0",
        "run_id": context["run_id"],
        "formal_run_ordinal": FORMAL_RUN_ORDINAL,
        "evaluation_start_utc": start_utc,
        "exact_command": rendered_command,
        "argv": [sys.executable, *argv],
        "person_e_source_commit": PERSON_E_FREEZE_COMMIT,
        "person_c_test_package_commit": PERSON_C_PACKAGE_COMMIT,
        "orchestration_script_sha256": context[
            "orchestration_script_sha256"
        ],
        "truth_artifacts_opened": False,
        "detector_outcome_count_at_receipt": 0,
    }
    _write_json_exclusive(
        output_directory / "formal_run_started.json",
        start_receipt,
    )
    journal_path = output_directory / "inference_outcomes.jsonl"
    journal_descriptor = os.open(
        journal_path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
        0o644,
    )
    raw_outcomes: list[dict[str, Any]] = []
    detector_arguments = _detector_arguments(context["config"])
    try:
        with os.fdopen(journal_descriptor, "wb", buffering=0) as journal:
            for ordinal, inference_row in enumerate(
                context["inference_rows"],
                start=1,
            ):
                payload = inference_row["source_path"].read_bytes()
                _require(
                    _sha256_bytes(payload) == inference_row["sha256"],
                    f"{inference_row['frame_id']} changed before inference.",
                )
                rgb = decode_png_rgb_bytes(payload)
                result = detect_magenta(rgb, **detector_arguments)
                outcome = _raw_outcome(
                    inference_row,
                    result,
                    ordinal=ordinal,
                )
                journal.write(_journal_json_bytes(outcome))
                os.fsync(journal.fileno())
                raw_outcomes.append(outcome)
    except BaseException:
        try:
            os.close(journal_descriptor)
        except OSError:
            pass
        raise
    _require(
        len(raw_outcomes) == EXPECTED_FRAME_COUNT,
        "Formal inference did not produce exactly 48 outcomes.",
    )
    end_utc = _utc_now()
    _write_json_exclusive(
        output_directory / "inference_complete.json",
        {
            "schema_version": "1.0",
            "run_id": context["run_id"],
            "formal_run_ordinal": FORMAL_RUN_ORDINAL,
            "evaluation_start_utc": start_utc,
            "evaluation_end_utc": end_utc,
            "outcome_count": len(raw_outcomes),
            "truth_artifacts_opened_during_inference": False,
            "inference_journal_sha256": _sha256_file(journal_path),
        },
    )
    joined, truth_binding = _load_truth_after_inference(
        context["package_root"],
        raw_outcomes,
    )
    records = _final_records(
        joined,
        context=context,
        evaluation_start_utc=start_utc,
        evaluation_end_utc=end_utc,
    )
    classifications = Counter(record["classification"] for record in records)
    metrics = _confusion(records)
    per_layout = []
    for layout_id in sorted({record["layout_id"] for record in records}):
        layout_records = [
            record for record in records if record["layout_id"] == layout_id
        ]
        layout_counts = Counter(
            record["classification"] for record in layout_records
        )
        per_layout.append(
            {
                "layout_id": layout_id,
                "total_frames": len(layout_records),
                "true_positive": layout_counts["TP"],
                "false_positive": layout_counts["FP"],
                "true_negative": layout_counts["TN"],
                "false_negative": layout_counts["FN"],
            }
        )
    reason_counts = Counter(
        record["rejection_reason"]
        for record in records
        if record["rejection_reason"] is not None
    )
    accepted_count = sum(record["accepted"] for record in records)
    rejected_count = sum(record["rejected"] for record in records)
    missing_count = EXPECTED_FRAME_COUNT - len(records)
    duplicate_count = len(records) - len({record["frame_id"] for record in records})
    extra_count = len({record["frame_id"] for record in records}) - EXPECTED_FRAME_COUNT
    complete = (
        len(records) == EXPECTED_FRAME_COUNT
        and missing_count == 0
        and duplicate_count == 0
        and extra_count == 0
        and sum(classifications.values()) == EXPECTED_FRAME_COUNT
    )
    precision_decimal = metrics["precision"]["decimal"]
    recall_decimal = metrics["recall"]["decimal"]
    passed = complete and precision_decimal >= 0.95 and recall_decimal >= 0.95
    records_document = {
        "schema_version": "1.0",
        "records_schema_version": (
            "person-e-phase3-formal-detection-records-v1.0"
        ),
        "package_id": PACKAGE_ID,
        "package_commit": PERSON_C_PACKAGE_COMMIT,
        "detector_version": EXPECTED_DETECTOR_VERSION,
        "run_id": context["run_id"],
        "formal_run_ordinal": FORMAL_RUN_ORDINAL,
        "record_count": len(records),
        "records": records,
    }
    _write_json_exclusive(
        output_directory / "formal_detection_records.json",
        records_document,
    )
    parquet_payload = _parquet_bytes(records)
    _write_bytes_exclusive(
        output_directory / "formal_detection_records.parquet",
        parquet_payload,
    )
    report = {
        "schema_version": "1.0",
        "formal_evaluation_schema_version": (
            "person-e-phase3-detector-v1-formal-evaluation-v1.0"
        ),
        "package_id": PACKAGE_ID,
        "package_commit": PERSON_C_PACKAGE_COMMIT,
        "detector_version": EXPECTED_DETECTOR_VERSION,
        "run_id": context["run_id"],
        "formal_run_ordinal": FORMAL_RUN_ORDINAL,
        "evaluation_start_utc": start_utc,
        "evaluation_end_utc": end_utc,
        "metrics": metrics,
        "formal_thresholds": {
            "minimum_precision": 0.95,
            "minimum_recall": 0.95,
        },
        "all_records_valid": complete,
        "formal_gate_passed": passed,
        "per_layout": per_layout,
        "accepted_frame_count": accepted_count,
        "rejected_frame_count": rejected_count,
        "rejection_reason_counts": dict(sorted(reason_counts.items())),
        "missing_record_count": missing_count,
        "duplicate_record_count": duplicate_count,
        "extra_record_count": extra_count,
        "truth_exposed_to_detector": False,
        "detector_tuned_after_result": False,
        "second_formal_run_occurred": False,
        "u4_output_inspected": False,
    }
    _write_json_exclusive(
        output_directory / "formal_evaluation_report.json",
        report,
    )
    _write_json_exclusive(
        output_directory / "runtime_environment.json",
        {
            "schema_version": "1.0",
            "runtime": context["runtime"],
            "orchestration_script_sha256": context[
                "orchestration_script_sha256"
            ],
            "source_commit": PERSON_E_FREEZE_COMMIT,
            "test_package_commit": PERSON_C_PACKAGE_COMMIT,
        },
    )
    _write_json_exclusive(
        output_directory / "package_binding.json",
        {
            "schema_version": "1.0",
            "package_id": PACKAGE_ID,
            "package_commit": PERSON_C_PACKAGE_COMMIT,
            "direct_parent_register_commit": PERSON_C_REGISTER_COMMIT,
            "predeclaration_commit": PERSON_C_PREDECLARATION_COMMIT,
            "frame_count": EXPECTED_FRAME_COUNT,
            "png_inventory_sha256": EXPECTED_PNG_INVENTORY_SHA256,
            "candidate_binding": context["candidate_binding"],
            "inference_source_binding": context["package_binding"],
            "truth_binding": truth_binding,
            "truth_artifacts_opened_only_after_inference_complete": True,
        },
    )
    _write_json_exclusive(
        output_directory / "phase3_status.json",
        {
            "schema_version": "1.0",
            "phase_3_status": "INCOMPLETE",
            "step_3_1_status": "PASS" if passed else "FAIL",
            "step_3_1_pass_claimed": passed,
            "step_3_1_formal_run_ordinal": FORMAL_RUN_ORDINAL,
            "step_3_2_status": "INCOMPLETE_NOT_MODIFIED",
            "step_3_3_status": "BLOCKED_OWNER_CONTRACTS_NOT_MODIFIED",
            "development_metrics_are_formal_gate_result": False,
        },
    )
    _write_json_exclusive(
        output_directory / "formal_run_receipt.json",
        {
            "schema_version": "1.0",
            "run_id": context["run_id"],
            "formal_run_ordinal": FORMAL_RUN_ORDINAL,
            "formal_run_count": 1,
            "formal_run_consumed": True,
            "evaluation_start_utc": start_utc,
            "evaluation_end_utc": end_utc,
            "exact_command": rendered_command,
            "result_record_count": len(records),
            "inference_outcome_count": len(raw_outcomes),
            "formal_gate_passed": passed,
            "detector_tuned_after_result": False,
            "second_formal_run_occurred": False,
            "u4_output_inspected": False,
            "new_untouched_test_package_modified": False,
        },
    )
    artifact_names = sorted(
        path.name for path in output_directory.iterdir() if path.is_file()
    )
    provenance_records = [
        {
            "path": name,
            "sha256": _sha256_file(output_directory / name),
            "size_bytes": (output_directory / name).stat().st_size,
        }
        for name in artifact_names
    ]
    _write_json_exclusive(
        output_directory / "provenance_index.json",
        {
            "schema_version": "1.0",
            "package_id": PACKAGE_ID,
            "package_commit": PERSON_C_PACKAGE_COMMIT,
            "detector_version": EXPECTED_DETECTOR_VERSION,
            "run_id": context["run_id"],
            "formal_run_ordinal": FORMAL_RUN_ORDINAL,
            "records": provenance_records,
            "self_reference_excluded": True,
        },
    )


def _write_failure_receipt(
    output_directory: Path,
    *,
    run_id: str,
    error: BaseException,
) -> None:
    if not output_directory.exists():
        return
    failure_path = output_directory / "formal_run_failure.json"
    if failure_path.exists():
        return
    journal_path = output_directory / "inference_outcomes.jsonl"
    outcome_count = 0
    if journal_path.is_file():
        outcome_count = sum(1 for line in journal_path.read_bytes().splitlines() if line)
    _write_json_exclusive(
        failure_path,
        {
            "schema_version": "1.0",
            "run_id": run_id,
            "formal_run_ordinal": FORMAL_RUN_ORDINAL,
            "formal_run_consumed": outcome_count > 0,
            "preserved_outcome_count": outcome_count,
            "error_type": type(error).__name__,
            "error_message": str(error),
            "traceback": traceback.format_exc(),
            "retry_forbidden_if_consumed": True,
        },
    )


def main() -> None:
    args = parse_args()
    try:
        context = _preflight(args)
    except BaseException as error:
        print(f"RUN_NOT_STARTED: {type(error).__name__}: {error}", file=sys.stderr)
        raise
    try:
        _formal_run(context, sys.argv)
    except BaseException as error:
        _write_failure_receipt(
            context["output_directory"],
            run_id=context["run_id"],
            error=error,
        )
        raise


if __name__ == "__main__":
    main()
