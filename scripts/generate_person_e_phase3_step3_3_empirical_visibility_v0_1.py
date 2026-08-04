"""Produce Person E's frozen Step 3.3 empirical-visibility handoff exactly once.

Production consumes only Person C's truth-free generation-input package. The
detector is imported from the frozen Person E implementation; this module does
not duplicate thresholds or detector behavior. Validation mode never imports
or executes the detector.
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
import tarfile
from collections import Counter, defaultdict
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from itertools import groupby
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

SCHEMA_ID = "person-e-phase3-step3-3-empirical-visibility-v0-1"
REPOSITORY = Path(__file__).resolve().parents[1]
OUTPUT_RELATIVE_PATH = Path(
    "data/handoff_c/person_e_phase3_step3_3_empirical_visibility_v0_1"
)
C_PACKAGE_RELATIVE_PATH = Path(
    "data/handoff_e/phase3_visibility_repair_v0_1"
)
C_GENERATION_MANIFEST = "generation_input_manifest.jsonl"
C_IDENTITY_MANIFEST = "derived_identity_manifest.jsonl"

PERSON_E_BRANCH = "role/person-e-operations"
PERSON_E_START_COMMIT = "bfe7d55acc1fcf0b90aca5c152672070b15e6ee7"
PERSON_B_POLICY_COMMIT = "eec9396e6a93feaab3d5d298ac7cdc4cb54fdbd4"
PERSON_C_CURRENT_COMMIT = "cbe673d7d765178b3175af60e69c609547be1d68"
PERSON_C_PACKAGE_COMMIT = "903c9ff4409e551226e92609bf0d70b8b0c36444"
PERSON_C_INVENTORY_SHA256 = (
    "0c299852552cdb4995e4aca24b72fb21f10619cd4ced1005b014d91d894c3d43"
)
PERSON_C_AGGREGATE_SHA256 = (
    "023d7d9c7776cdca6b8e304db8ba94cc25927ba4a10f6aff9534576e0deee4f5"
)
DETECTOR_FREEZE_COMMIT = "3930669eddc026ecb081e947f71f1855a7415904"
STEP_3_1_COMMIT = "ed3ca072b184ccb45dbf154d4209c5893b67f42e"
STEP_3_2_COMMIT = PERSON_E_START_COMMIT
DETECTOR_ALGORITHM = "hsv-largest-valid-blob-v1.0-candidate"
DETECTOR_IDENTITY_SHA256 = (
    "0cadf618fca1578196bde4982021c38627ccb9c39e46353812e7da3fce6aa125"
)
DETECTOR_VERSION = f"{DETECTOR_ALGORITHM}:sha256:{DETECTOR_IDENTITY_SHA256}"
DETECTOR_CONFIG_SHA256 = (
    "acfecd659958891eaee0d582c946abdfaaf47d1ab3307a24f7652e634c045bfa"
)
DETECTOR_SETTINGS_SHA256 = (
    "0dbb426adf99f53455eea04c4aaeb56f3cb22cbc351d87269bb605445eb8f2ea"
)
DETECTOR_IMPLEMENTATION_SHA256 = (
    "026f3b9f25c8aef7ac43fada5b8de92662b605af4868f930698651e59a228214"
)

EXPECTED_INPUT_COUNT = 1850
EXPECTED_ARCHIVE_COUNT = 56
EXPECTED_PACKAGE_FILE_COUNT = 73
PRODUCTION_RUN_ORDINAL = 1
PRODUCTION_RUN_COUNT = 1
EXPECTED_RUN_ID = (
    "person-e-phase3-step3-3-empirical-v0-1-production-ordinal-1"
)
EXPECTED_RESOLUTION = "640x360"
EXPECTED_COORDINATE_CONVENTION = "pixel_center_xy_zero_based"
EXPECTED_WIDTH = 640
EXPECTED_HEIGHT = 360
EXPECTED_CAMERA_POSES = {
    f"layout_{index:02d}": f"layout_{index:02d}_canonical_pose_v1"
    for index in range(1, 7)
}

EMPIRICAL_FIELDS = frozenset(
    {
        "trajectory_id",
        "model_frame_idx",
        "empirical_magenta_visible",
        "detector_version",
        "layout_id",
        "canonical_camera_pose_id",
        "resolution",
        "coordinate_convention",
    }
)
DIAGNOSTIC_FIELDS = frozenset(
    {
        "accepted",
        "bounding_box_xyxy",
        "candidate_blob_count",
        "centroid_xy",
        "decision_ordinal",
        "detector_identity_sha256",
        "detector_status",
        "detector_version",
        "empirical_magenta_visible",
        "frame_640_sha256",
        "model_frame_idx",
        "rejection_reason",
        "selected_blob_area_pixels",
        "threshold_match_pixels",
        "trajectory_id",
    }
)
GENERATION_FORBIDDEN_FIELDS = frozenset(
    {
        "accepted",
        "blob_area",
        "blob_cx",
        "blob_cy",
        "detector_id",
        "detector_version",
        "empirical_magenta_visible",
        "empirical_visible",
        "geometric_visible",
        "invalidity_reason",
        "quarantine_category",
        "quarantined",
        "rejection_reason",
        "visible_flag",
    }
)
IMPORT_FORBIDDEN_FIELDS = frozenset(
    {
        "archive_member_path",
        "archive_path",
        "blob_diagnostics",
        "detector_thresholds",
        "detector_truth",
        "false_negative",
        "false_positive",
        "geometric_visible",
        "invalidity_reason",
        "precision",
        "quarantine_category",
        "quarantined",
        "recall",
        "true_negative",
        "true_positive",
        "visible_flag",
    }
)
ACCURACY_FIELD_NAMES = frozenset(
    {
        "classification",
        "confusion_matrix",
        "false_negative",
        "false_positive",
        "fn",
        "fp",
        "precision",
        "recall",
        "tn",
        "tp",
        "true_negative",
        "true_positive",
    }
)
EXPECTED_OUTPUT_FILES = frozenset(
    {
        "authority_binding.json",
        "coverage_report.json",
        "detector_diagnostics.jsonl",
        "detector_diagnostics_schema.json",
        "empirical_visibility_records.jsonl",
        "empirical_visibility_schema.json",
        "phase3_status.json",
        "production_run_receipt.json",
        "provenance_index.json",
        "run_predeclaration.json",
        "sha256_inventory.json",
        "validation_receipt.json",
    }
)


class FailClosed(RuntimeError):
    """Raised when production or validation cannot prove an exact invariant."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise FailClosed(message)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def jsonl_line(value: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(
            dict(value),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
        require(not raw.startswith(b"\xef\xbb\xbf"), f"{label} contains a BOM.")
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FailClosed(f"{label} is not valid UTF-8 JSON: {exc}") from exc
    require(isinstance(value, dict), f"{label} must be a JSON object.")
    return value


def load_jsonl(path: Path, label: str) -> list[dict[str, Any]]:
    try:
        raw = path.read_bytes()
        require(not raw.startswith(b"\xef\xbb\xbf"), f"{label} contains a BOM.")
        require(raw.endswith(b"\n"), f"{label} lacks a final newline.")
        lines = raw.decode("utf-8").splitlines()
        values = [json.loads(line) for line in lines]
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FailClosed(f"{label} is not valid UTF-8 JSONL: {exc}") from exc
    require(
        all(isinstance(value, dict) for value in values),
        f"{label} rows must be JSON objects.",
    )
    return values


def write_exclusive(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        try:
            os.close(descriptor)
        except OSError:
            pass
        raise


def write_json_exclusive(path: Path, value: Mapping[str, Any]) -> None:
    write_exclusive(path, json_bytes(dict(value)))


def safe_relative_path(value: Any) -> bool:
    if not isinstance(value, str) or not value or "\\" in value:
        return False
    posix = PurePosixPath(value)
    windows = PureWindowsPath(value)
    return (
        not posix.is_absolute()
        and not windows.is_absolute()
        and not windows.drive
        and ".." not in posix.parts
        and all(part not in {"", "."} for part in posix.parts)
    )


def reject_u4_path(path: Path) -> None:
    parts = [part.lower() for part in path.resolve().parts]
    require(
        not any("u4" in part for part in parts),
        f"U4-like path is prohibited: {path}",
    )


def git(repository: Path, *arguments: str) -> str:
    try:
        return subprocess.check_output(
            ["git", "-C", str(repository), *arguments],
            stderr=subprocess.STDOUT,
            text=True,
        ).strip()
    except subprocess.CalledProcessError as exc:
        raise FailClosed(
            f"Git command failed in {repository}: {exc.output.strip()}"
        ) from exc


def hash_json_value(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return sha256_bytes(payload)


def runtime_versions() -> dict[str, str]:
    import cv2
    import numpy
    import pandas
    import pyarrow

    opencv_distribution = None
    for distribution in ("opencv-python", "opencv-python-headless"):
        try:
            opencv_distribution = importlib.metadata.version(distribution)
            break
        except importlib.metadata.PackageNotFoundError:
            continue
    require(
        opencv_distribution == "4.11.0.86",
        "OpenCV distribution version is outside the frozen runtime family.",
    )
    values = {
        "executable": str(Path(sys.executable).resolve()),
        "numpy": numpy.__version__,
        "opencv": cv2.__version__,
        "opencv_distribution": opencv_distribution,
        "operating_system": platform.platform(),
        "pandas": pandas.__version__,
        "pyarrow": pyarrow.__version__,
        "python": platform.python_version(),
    }
    require(values["python"] == "3.10.20", "Python version changed.")
    require(values["numpy"] == "1.26.4", "NumPy version changed.")
    require(values["pandas"] == "2.3.3", "pandas version changed.")
    require(values["pyarrow"] == "25.0.0", "PyArrow version changed.")
    require(values["opencv"] == "4.11.0", "OpenCV runtime version changed.")
    return values


def validate_person_e_scope(output_directory: Path) -> None:
    require(
        git(REPOSITORY, "branch", "--show-current") == PERSON_E_BRANCH,
        "Person E branch changed.",
    )
    require(
        git(REPOSITORY, "rev-parse", "HEAD") == PERSON_E_START_COMMIT,
        "Person E starting commit changed.",
    )
    require(
        git(REPOSITORY, "rev-parse", f"origin/{PERSON_E_BRANCH}")
        == PERSON_E_START_COMMIT,
        "Person E remote authority changed.",
    )
    require(
        git(REPOSITORY, "diff", "--name-only") == "",
        "A pre-existing tracked Person E path changed.",
    )
    require(
        git(REPOSITORY, "diff", "--cached", "--name-only") == "",
        "Person E has staged changes before production.",
    )
    expected_output = (REPOSITORY / OUTPUT_RELATIVE_PATH).resolve()
    require(
        output_directory.resolve() == expected_output,
        "Production output path is not the authorized package root.",
    )


def validate_person_c_worktree(person_c_root: Path) -> Path:
    reject_u4_path(person_c_root)
    require(person_c_root.is_dir(), "Detached Person C worktree is missing.")
    require(
        git(person_c_root, "rev-parse", "HEAD") == PERSON_C_CURRENT_COMMIT,
        "Person C worktree authority changed.",
    )
    require(
        git(person_c_root, "branch", "--show-current") == "",
        "Person C input worktree is not detached.",
    )
    require(
        git(person_c_root, "status", "--porcelain=v1", "--untracked-files=all")
        == "",
        "Person C input worktree is not clean.",
    )
    require(
        git(
            person_c_root,
            "diff",
            "--name-only",
            PERSON_C_PACKAGE_COMMIT,
            PERSON_C_CURRENT_COMMIT,
            "--",
            C_PACKAGE_RELATIVE_PATH.as_posix(),
        )
        == "",
        "Person C package changed after its package commit.",
    )
    package_root = person_c_root / C_PACKAGE_RELATIVE_PATH
    require(package_root.is_dir(), "Person C generation package is missing.")
    return package_root


def validate_frozen_detector() -> tuple[dict[str, Any], dict[str, Any], dict[str, str]]:
    config_path = (
        REPOSITORY
        / "docs/status/person_e_phase3_step3_1_candidate_freeze_v0_1"
        / "detector_candidate_config.json"
    )
    version_path = (
        REPOSITORY
        / "docs/status/person_e_phase3_step3_1_candidate_freeze_v0_1"
        / "detector_candidate_version_record.json"
    )
    config = load_json(config_path, "frozen detector config")
    version = load_json(version_path, "frozen detector version")
    configuration = config.get("configuration")
    require(isinstance(configuration, dict), "Frozen detector config is malformed.")
    settings = configuration.get("detector_settings")
    require(isinstance(settings, dict), "Frozen detector settings are malformed.")
    implementation_path = configuration.get("detector_core_implementation_path")
    require(
        isinstance(implementation_path, str)
        and safe_relative_path(implementation_path),
        "Frozen detector implementation path is invalid.",
    )
    computed = {
        "config_sha256": hash_json_value(configuration),
        "identity_sha256": hash_json_value(version.get("identity")),
        "implementation_sha256": sha256_file(REPOSITORY / implementation_path),
        "settings_sha256": hash_json_value(settings),
    }
    expected = {
        "config_sha256": DETECTOR_CONFIG_SHA256,
        "identity_sha256": DETECTOR_IDENTITY_SHA256,
        "implementation_sha256": DETECTOR_IMPLEMENTATION_SHA256,
        "settings_sha256": DETECTOR_SETTINGS_SHA256,
    }
    declared = {
        "config_sha256": version.get("detector_config_sha256"),
        "identity_sha256": version.get("detector_identity_sha256"),
        "implementation_sha256": version.get("detector_implementation_sha256"),
        "settings_sha256": version.get("detector_settings_sha256"),
    }
    require(computed == expected == declared, "Frozen detector hashes changed.")
    require(
        config.get("detector_config_sha256") == DETECTOR_CONFIG_SHA256,
        "Frozen config document hash binding changed.",
    )
    require(
        configuration.get("detector_settings_sha256")
        == DETECTOR_SETTINGS_SHA256,
        "Frozen settings document hash binding changed.",
    )
    require(
        configuration.get("detector_implementation_sha256")
        == DETECTOR_IMPLEMENTATION_SHA256,
        "Frozen implementation document hash binding changed.",
    )
    require(
        version.get("detector_algorithm_id") == DETECTOR_ALGORITHM,
        "Frozen detector algorithm changed.",
    )
    require(
        version.get("detector_version") == DETECTOR_VERSION,
        "Frozen detector version changed.",
    )
    require(
        git(
            REPOSITORY,
            "diff",
            "--name-only",
            DETECTOR_FREEZE_COMMIT,
            "HEAD",
            "--",
            implementation_path,
            str(config_path.relative_to(REPOSITORY)).replace("\\", "/"),
            str(version_path.relative_to(REPOSITORY)).replace("\\", "/"),
        )
        == "",
        "Frozen detector authority paths changed after freeze.",
    )
    return config, version, {
        **computed,
        "config_file_sha256": sha256_file(config_path),
        "config_path": str(config_path.relative_to(REPOSITORY)).replace("\\", "/"),
        "version_file_sha256": sha256_file(version_path),
        "version_path": str(version_path.relative_to(REPOSITORY)).replace("\\", "/"),
    }


def package_aggregate_sha256(package_root: Path) -> str:
    digest = hashlib.sha256()
    files = sorted(path for path in package_root.rglob("*") if path.is_file())
    for path in files:
        relative = path.relative_to(package_root).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(sha256_file(path).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def validate_generation_rows(
    rows: Sequence[Mapping[str, Any]],
    identity_rows: Sequence[Mapping[str, Any]],
    *,
    expected_count: int = EXPECTED_INPUT_COUNT,
) -> list[tuple[str, int]]:
    require(len(rows) == expected_count, "Generation-input row count changed.")
    require(len(identity_rows) == expected_count, "Identity row count changed.")
    keys: list[tuple[str, int]] = []
    for index, row in enumerate(rows):
        require(
            not (set(row) & GENERATION_FORBIDDEN_FIELDS),
            f"Generation row {index} contains prohibited outcome fields.",
        )
        trajectory = row.get("trajectory_id")
        model_index = row.get("model_frame_idx")
        require(
            isinstance(trajectory, str) and trajectory,
            f"Generation row {index} trajectory_id is invalid.",
        )
        require(
            isinstance(model_index, int)
            and not isinstance(model_index, bool)
            and model_index >= 0,
            f"Generation row {index} model_frame_idx is invalid.",
        )
        require(
            type(row.get("resolution")) is str
            and row["resolution"] == EXPECTED_RESOLUTION,
            f"Generation row {index} resolution changed.",
        )
        require(
            type(row.get("coordinate_convention")) is str
            and row["coordinate_convention"] == EXPECTED_COORDINATE_CONVENTION,
            f"Generation row {index} coordinate convention changed.",
        )
        for field in ("layout_id", "canonical_camera_pose_id"):
            require(
                isinstance(row.get(field), str) and row[field],
                f"Generation row {index} {field} is invalid.",
            )
        require(
            row["layout_id"] in EXPECTED_CAMERA_POSES,
            f"Generation row {index} layout is unsupported.",
        )
        require(
            row["canonical_camera_pose_id"]
            == EXPECTED_CAMERA_POSES[row["layout_id"]],
            f"Generation row {index} camera context changed.",
        )
        for field in ("archive_path", "archive_member_path"):
            require(
                safe_relative_path(row.get(field)),
                f"Generation row {index} {field} is unsafe.",
            )
        keys.append((trajectory, model_index))
    identity_keys = [
        (row.get("trajectory_id"), row.get("model_frame_idx"))
        for row in identity_rows
    ]
    require(keys == sorted(keys), "Generation rows are not deterministically sorted.")
    require(
        identity_keys == sorted(identity_keys),
        "Identity rows are not deterministically sorted.",
    )
    require(len(set(keys)) == expected_count, "Generation identities are duplicated.")
    require(
        len(set(identity_keys)) == expected_count,
        "Derived identities are duplicated.",
    )
    require(
        set(keys) == set(identity_keys),
        "Generation and identity key sets differ.",
    )
    return keys


def validate_package_inventory(
    package_root: Path,
    *,
    expected_inventory_sha256: str = PERSON_C_INVENTORY_SHA256,
    expected_aggregate_sha256: str = PERSON_C_AGGREGATE_SHA256,
    expected_file_count: int = EXPECTED_PACKAGE_FILE_COUNT,
    expected_archive_count: int = EXPECTED_ARCHIVE_COUNT,
) -> dict[str, Any]:
    inventory_path = package_root / "sha256_inventory.json"
    require(
        sha256_file(inventory_path) == expected_inventory_sha256,
        "Person C inventory SHA-256 changed.",
    )
    inventory = load_json(inventory_path, "Person C SHA-256 inventory")
    require(
        inventory.get("package_file_count") == expected_file_count,
        "Person C package file count changed.",
    )
    require(
        inventory.get("archive_count") == expected_archive_count,
        "Person C archive count changed.",
    )
    actual_files = sorted(path for path in package_root.rglob("*") if path.is_file())
    require(
        len(actual_files) == expected_file_count,
        "Person C package contains an unexpected number of files.",
    )
    declared = inventory.get("files")
    require(isinstance(declared, dict), "Person C file inventory is malformed.")
    actual_relative = {
        path.relative_to(package_root).as_posix() for path in actual_files
    }
    require(
        actual_relative == set(declared) | {"sha256_inventory.json"},
        "Person C package file set differs from its inventory.",
    )
    for relative, expected_hash in declared.items():
        require(safe_relative_path(relative), f"Unsafe inventory path: {relative}")
        require(
            sha256_file(package_root / relative) == expected_hash,
            f"Inventory file hash mismatch: {relative}",
        )
    aggregate = package_aggregate_sha256(package_root)
    require(
        aggregate == expected_aggregate_sha256,
        "Person C package aggregate SHA-256 changed.",
    )
    return {
        "aggregate_sha256": aggregate,
        "file_sha256": dict(sorted(declared.items())),
        "inventory_sha256": expected_inventory_sha256,
    }


def verify_archive_members(
    package_root: Path,
    rows: Sequence[Mapping[str, Any]],
    *,
    expected_archive_count: int = EXPECTED_ARCHIVE_COUNT,
    expected_member_count: int = EXPECTED_INPUT_COUNT,
    decode: bool,
    decoder: Callable[[bytes], Any] | None = None,
) -> dict[str, Any]:
    archive_inventory = load_json(
        package_root / "archive_inventory.json",
        "Person C archive inventory",
    )
    archives = archive_inventory.get("archives")
    require(isinstance(archives, list), "Archive inventory records are malformed.")
    archive_by_path = {
        record.get("archive_path"): record
        for record in archives
        if isinstance(record, dict)
    }
    require(
        len(archive_by_path) == expected_archive_count,
        "Archive inventory contains duplicate or missing paths.",
    )
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["archive_path"])].append(row)
    require(
        len(grouped) == expected_archive_count,
        "Generation rows reference an unexpected archive count.",
    )
    require(
        set(grouped) == set(archive_by_path),
        "Generation and archive-inventory path sets differ.",
    )
    checked = 0
    archive_hashes: dict[str, str] = {}
    for relative in sorted(grouped):
        require(safe_relative_path(relative), f"Unsafe archive path: {relative}")
        path = package_root / relative
        require(path.is_file(), f"Archive is missing: {relative}")
        archive_hash = sha256_file(path)
        archive_record = archive_by_path[relative]
        require(
            archive_hash == archive_record.get("archive_sha256"),
            f"Archive SHA-256 mismatch: {relative}",
        )
        archive_hashes[relative] = archive_hash
        expected = {
            str(row["archive_member_path"]): row for row in grouped[relative]
        }
        require(
            len(expected) == len(grouped[relative]),
            f"Duplicate member identity in {relative}.",
        )
        require(
            all(row.get("archive_sha256") == archive_hash for row in expected.values()),
            f"Row/archive SHA-256 binding mismatch: {relative}",
        )
        with tarfile.open(path, "r:gz") as archive:
            members = archive.getmembers()
            names = [member.name for member in members]
            require(names == sorted(names), f"Archive is not sorted: {relative}")
            require(
                len(names) == len(set(names)),
                f"Archive has duplicate member names: {relative}",
            )
            require(
                set(names) == set(expected),
                f"Archive member coverage differs: {relative}",
            )
            for member in members:
                require(
                    safe_relative_path(member.name)
                    and member.isfile()
                    and not member.issym()
                    and not member.islnk(),
                    f"Unsafe archive member: {relative}:{member.name}",
                )
                extracted = archive.extractfile(member)
                require(
                    extracted is not None,
                    f"Archive member cannot be read: {relative}:{member.name}",
                )
                payload = extracted.read()
                row = expected[member.name]
                require(
                    len(payload) == row.get("frame_size_bytes")
                    and member.size == row.get("frame_size_bytes"),
                    f"Archive member size mismatch: {relative}:{member.name}",
                )
                require(
                    sha256_bytes(payload) == row.get("frame_640_sha256"),
                    f"Archive member hash mismatch: {relative}:{member.name}",
                )
                if decode:
                    require(decoder is not None, "Decode preflight lacks a decoder.")
                    try:
                        rgb = decoder(payload)
                    except Exception as exc:
                        raise FailClosed(
                            f"PNG decode failed: {relative}:{member.name}: {exc}"
                        ) from exc
                    decoded_shape = getattr(rgb, "shape", None)
                    dimensions_match = (
                        isinstance(decoded_shape, tuple)
                        and len(decoded_shape) >= 2
                        and decoded_shape[:2] == (EXPECTED_HEIGHT, EXPECTED_WIDTH)
                    ) or (
                        isinstance(rgb, Sequence)
                        and len(rgb) == EXPECTED_HEIGHT
                        and all(
                            isinstance(line, Sequence)
                            and len(line) == EXPECTED_WIDTH
                            for line in rgb
                        )
                    )
                    require(
                        dimensions_match,
                        f"PNG dimensions changed: {relative}:{member.name}",
                    )
                checked += 1
    require(
        checked == expected_member_count,
        "Archive member verification count changed.",
    )
    return {
        "archive_count": len(archive_hashes),
        "archive_sha256": dict(sorted(archive_hashes.items())),
        "member_count": checked,
    }


def load_and_verify_c_package(
    person_c_root: Path,
    *,
    decode_preflight: bool,
) -> dict[str, Any]:
    package_root = validate_person_c_worktree(person_c_root)
    inventory_binding = validate_package_inventory(package_root)
    rows = load_jsonl(
        package_root / C_GENERATION_MANIFEST,
        "Person C generation manifest",
    )
    identity_rows = load_jsonl(
        package_root / C_IDENTITY_MANIFEST,
        "Person C identity manifest",
    )
    keys = validate_generation_rows(rows, identity_rows)
    decoder = None
    if decode_preflight:
        import cv2
        import numpy

        def decode_for_preflight(payload: bytes) -> Any:
            image = cv2.imdecode(
                numpy.frombuffer(payload, dtype=numpy.uint8),
                cv2.IMREAD_UNCHANGED,
            )
            require(image is not None, "OpenCV could not decode the PNG.")
            return image

        decoder = decode_for_preflight
    archive_binding = verify_archive_members(
        package_root,
        rows,
        decode=decode_preflight,
        decoder=decoder,
    )
    return {
        "archive_binding": archive_binding,
        "identity_keys": keys,
        "inventory_binding": inventory_binding,
        "package_root": package_root,
        "rows": rows,
        "generation_manifest_sha256": sha256_file(
            package_root / C_GENERATION_MANIFEST
        ),
        "identity_manifest_sha256": sha256_file(
            package_root / C_IDENTITY_MANIFEST
        ),
    }


def detector_arguments(config: Mapping[str, Any]) -> dict[str, Any]:
    sys.path.insert(0, str(REPOSITORY / "src"))
    from mineocclude.vision.magenta import HsvRange

    settings = config["configuration"]["detector_settings"]
    return {
        "close_iterations": settings["close_iterations"],
        "connectivity": settings["connectivity"],
        "hsv_ranges": tuple(HsvRange(*values) for values in settings["hsv_ranges"]),
        "max_area_pixels": settings["max_area_pixels"],
        "min_area_pixels": settings["min_area_pixels"],
        "morphology_radius_pixels": settings["morphology_radius_pixels"],
        "open_iterations": settings["open_iterations"],
    }


def validate_detector_result(result: Any) -> bool:
    required = (
        "area_pixels",
        "bounding_box_xyxy",
        "candidate_blob_count",
        "centroid_xy",
        "detected",
        "rejection_reason",
        "status",
        "threshold_match_pixels",
    )
    require(
        all(hasattr(result, field) for field in required),
        "Frozen detector returned a malformed result.",
    )
    require(
        type(result.detected) is bool,
        "Frozen detector result lacks a Boolean decision.",
    )
    require(
        result.status in {"detected", "not_detected"},
        "Frozen detector returned an invalid status.",
    )
    require(
        isinstance(result.threshold_match_pixels, int)
        and not isinstance(result.threshold_match_pixels, bool)
        and result.threshold_match_pixels >= 0,
        "Frozen detector threshold-match count is invalid.",
    )
    require(
        isinstance(result.candidate_blob_count, int)
        and not isinstance(result.candidate_blob_count, bool)
        and result.candidate_blob_count >= 0,
        "Frozen detector component count is invalid.",
    )
    if result.detected:
        require(result.status == "detected", "Detected result status disagrees.")
        require(
            result.rejection_reason is None,
            "Accepted detector result has a rejection reason.",
        )
        require(
            isinstance(result.area_pixels, int)
            and not isinstance(result.area_pixels, bool)
            and result.area_pixels > 0,
            "Accepted detector result lacks a valid area.",
        )
        require(
            isinstance(result.centroid_xy, tuple)
            and len(result.centroid_xy) == 2,
            "Accepted detector result lacks a centroid.",
        )
        require(
            isinstance(result.bounding_box_xyxy, tuple)
            and len(result.bounding_box_xyxy) == 4,
            "Accepted detector result lacks a bounding box.",
        )
    else:
        require(
            result.status == "not_detected",
            "Rejected detector result status disagrees.",
        )
        require(
            result.rejection_reason in {"no_threshold_match", "no_valid_blob"},
            "Rejected detector result lacks the exact frozen rejection code.",
        )
        require(
            result.area_pixels is None
            and result.centroid_xy is None
            and result.bounding_box_xyxy is None,
            "Rejected detector result contains selected-blob diagnostics.",
        )
    return result.detected


def execute_frozen_detector(
    rgb: Sequence[Sequence[Sequence[float]]],
    arguments: Mapping[str, Any],
) -> Any:
    from mineocclude.vision.magenta import detect_magenta

    return detect_magenta(rgb, **dict(arguments))


def call_detector_fail_closed(
    detector: Callable[..., Any],
    rgb: Sequence[Sequence[Sequence[float]]],
    arguments: Mapping[str, Any],
) -> Any:
    try:
        result = detector(rgb, arguments)
    except Exception as exc:
        raise FailClosed(f"Frozen detector execution failed: {exc}") from exc
    validate_detector_result(result)
    return result


def diagnostic_row(
    source: Mapping[str, Any],
    result: Any,
    *,
    ordinal: int,
) -> dict[str, Any]:
    visible = validate_detector_result(result)
    return {
        "accepted": visible,
        "bounding_box_xyxy": (
            None
            if result.bounding_box_xyxy is None
            else list(result.bounding_box_xyxy)
        ),
        "candidate_blob_count": result.candidate_blob_count,
        "centroid_xy": (
            None if result.centroid_xy is None else list(result.centroid_xy)
        ),
        "decision_ordinal": ordinal,
        "detector_identity_sha256": DETECTOR_IDENTITY_SHA256,
        "detector_status": result.status,
        "detector_version": DETECTOR_VERSION,
        "empirical_magenta_visible": visible,
        "frame_640_sha256": source["frame_640_sha256"],
        "model_frame_idx": source["model_frame_idx"],
        "rejection_reason": result.rejection_reason,
        "selected_blob_area_pixels": result.area_pixels,
        "threshold_match_pixels": result.threshold_match_pixels,
        "trajectory_id": source["trajectory_id"],
    }


def validate_empirical_records(
    empirical_rows: Sequence[Mapping[str, Any]],
    diagnostic_rows: Sequence[Mapping[str, Any]],
    generation_rows: Sequence[Mapping[str, Any]],
    *,
    expected_count: int = EXPECTED_INPUT_COUNT,
) -> dict[str, Any]:
    require(
        len(empirical_rows) == expected_count,
        "Empirical record count changed.",
    )
    require(
        len(diagnostic_rows) == expected_count,
        "Diagnostic record count changed.",
    )
    generation_by_key = {
        (row["trajectory_id"], row["model_frame_idx"]): row
        for row in generation_rows
    }
    require(
        len(generation_by_key) == expected_count,
        "Generation keys are not unique.",
    )
    empirical_keys: list[tuple[str, int]] = []
    empirical_by_key: dict[tuple[str, int], Mapping[str, Any]] = {}
    for index, row in enumerate(empirical_rows):
        require(
            set(row) == EMPIRICAL_FIELDS,
            f"Empirical row {index} does not have the exact eight fields.",
        )
        require(
            not (set(row) & IMPORT_FORBIDDEN_FIELDS),
            f"Empirical row {index} contains a forbidden field.",
        )
        key = (row["trajectory_id"], row["model_frame_idx"])
        require(
            isinstance(key[0], str)
            and isinstance(key[1], int)
            and not isinstance(key[1], bool),
            f"Empirical row {index} identity types are invalid.",
        )
        require(
            type(row["empirical_magenta_visible"]) is bool,
            f"Empirical row {index} decision is not Boolean.",
        )
        require(
            row["detector_version"] == DETECTOR_VERSION,
            f"Empirical row {index} detector version changed.",
        )
        source = generation_by_key.get(key)
        require(source is not None, f"Empirical row {index} is extra.")
        for field in (
            "layout_id",
            "canonical_camera_pose_id",
            "resolution",
            "coordinate_convention",
        ):
            require(
                type(row[field]) is type(source[field])
                and row[field] == source[field],
                f"Empirical row {index} {field} differs from Person C.",
            )
        empirical_keys.append(key)
        empirical_by_key[key] = row
    require(
        empirical_keys == sorted(empirical_keys),
        "Empirical records are not deterministically sorted.",
    )
    require(
        len(empirical_by_key) == expected_count,
        "Empirical record identities are duplicated.",
    )
    diagnostic_keys: list[tuple[str, int]] = []
    accepted = 0
    rejection_reasons: Counter[str] = Counter()
    for index, row in enumerate(diagnostic_rows):
        require(
            set(row) == DIAGNOSTIC_FIELDS,
            f"Diagnostic row {index} fields changed.",
        )
        key = (row["trajectory_id"], row["model_frame_idx"])
        require(
            isinstance(key[0], str)
            and isinstance(key[1], int)
            and not isinstance(key[1], bool),
            f"Diagnostic row {index} identity types are invalid.",
        )
        require(
            row["decision_ordinal"] == index + 1,
            f"Diagnostic row {index} decision ordinal changed.",
        )
        require(
            row["detector_version"] == DETECTOR_VERSION
            and row["detector_identity_sha256"] == DETECTOR_IDENTITY_SHA256,
            f"Diagnostic row {index} detector identity changed.",
        )
        require(
            type(row["accepted"]) is bool
            and type(row["empirical_magenta_visible"]) is bool,
            f"Diagnostic row {index} decision types are invalid.",
        )
        require(
            row["accepted"] == row["empirical_magenta_visible"],
            f"Diagnostic row {index} accepted/empirical values differ.",
        )
        empirical = empirical_by_key.get(key)
        require(empirical is not None, f"Diagnostic row {index} is extra.")
        require(
            empirical["empirical_magenta_visible"]
            == row["empirical_magenta_visible"],
            f"Diagnostic row {index} differs from the import record.",
        )
        if row["accepted"]:
            accepted += 1
            require(
                row["detector_status"] == "detected"
                and row["rejection_reason"] is None,
                f"Accepted diagnostic row {index} is malformed.",
            )
        else:
            require(
                row["detector_status"] == "not_detected"
                and row["rejection_reason"]
                in {"no_threshold_match", "no_valid_blob"},
                f"Rejected diagnostic row {index} is malformed.",
            )
            rejection_reasons[row["rejection_reason"]] += 1
        diagnostic_keys.append(key)
    require(
        len(set(diagnostic_keys)) == expected_count,
        "Diagnostic identities are duplicated.",
    )
    require(
        set(empirical_keys) == set(generation_by_key),
        "Person C and empirical key sets differ.",
    )
    require(
        set(empirical_keys) == set(diagnostic_keys),
        "Empirical and diagnostic key sets differ.",
    )
    return {
        "accepted_count": accepted,
        "rejected_count": expected_count - accepted,
        "rejection_reason_counts": dict(sorted(rejection_reasons.items())),
    }


def schema_document(*, empirical: bool) -> dict[str, Any]:
    if empirical:
        return {
            "fields": [
                {"json_type": "string", "name": "trajectory_id", "required": True},
                {"json_type": "integer", "name": "model_frame_idx", "required": True},
                {
                    "json_type": "boolean",
                    "name": "empirical_magenta_visible",
                    "required": True,
                },
                {"json_type": "string", "name": "detector_version", "required": True},
                {"json_type": "string", "name": "layout_id", "required": True},
                {
                    "json_type": "string",
                    "name": "canonical_camera_pose_id",
                    "required": True,
                },
                {"json_type": "string", "name": "resolution", "required": True},
                {
                    "json_type": "string",
                    "name": "coordinate_convention",
                    "required": True,
                },
            ],
            "forbidden_fields": sorted(IMPORT_FORBIDDEN_FIELDS),
            "record_format": "compact_sorted_key_jsonl",
            "schema_id": f"{SCHEMA_ID}-empirical-records-schema-v1.0",
            "schema_version": "1.0",
        }
    return {
        "fields": [
            {"json_type": "boolean", "name": "accepted", "nullable": False},
            {"json_type": "array[integer]|null", "name": "bounding_box_xyxy"},
            {"json_type": "integer", "name": "candidate_blob_count", "nullable": False},
            {"json_type": "array[number]|null", "name": "centroid_xy"},
            {"json_type": "integer", "name": "decision_ordinal", "nullable": False},
            {
                "json_type": "string",
                "name": "detector_identity_sha256",
                "nullable": False,
            },
            {"json_type": "string", "name": "detector_status", "nullable": False},
            {"json_type": "string", "name": "detector_version", "nullable": False},
            {
                "json_type": "boolean",
                "name": "empirical_magenta_visible",
                "nullable": False,
            },
            {"json_type": "string", "name": "frame_640_sha256", "nullable": False},
            {"json_type": "integer", "name": "model_frame_idx", "nullable": False},
            {"json_type": "string|null", "name": "rejection_reason"},
            {"json_type": "integer|null", "name": "selected_blob_area_pixels"},
            {
                "json_type": "integer",
                "name": "threshold_match_pixels",
                "nullable": False,
            },
            {"json_type": "string", "name": "trajectory_id", "nullable": False},
        ],
        "record_format": "compact_sorted_key_jsonl",
        "schema_id": f"{SCHEMA_ID}-detector-diagnostics-schema-v1.0",
        "schema_version": "1.0",
    }


def authority_binding(candidate: Mapping[str, str]) -> dict[str, Any]:
    return {
        "detector": {
            "algorithm": DETECTOR_ALGORITHM,
            "config_sha256": DETECTOR_CONFIG_SHA256,
            "freeze_commit": DETECTOR_FREEZE_COMMIT,
            "identity_sha256": DETECTOR_IDENTITY_SHA256,
            "implementation_sha256": DETECTOR_IMPLEMENTATION_SHA256,
            "settings_sha256": DETECTOR_SETTINGS_SHA256,
            "version": DETECTOR_VERSION,
        },
        "detector_candidate_files": {
            "config_path": candidate["config_path"],
            "config_sha256": candidate["config_file_sha256"],
            "version_path": candidate["version_path"],
            "version_sha256": candidate["version_file_sha256"],
        },
        "person_b_policy_commit": PERSON_B_POLICY_COMMIT,
        "person_c_current_commit": PERSON_C_CURRENT_COMMIT,
        "person_c_package_aggregate_sha256": PERSON_C_AGGREGATE_SHA256,
        "person_c_package_commit": PERSON_C_PACKAGE_COMMIT,
        "person_c_package_inventory_sha256": PERSON_C_INVENTORY_SHA256,
        "person_e_starting_commit": PERSON_E_START_COMMIT,
        "schema_id": f"{SCHEMA_ID}-authority-binding-v1.0",
        "schema_version": "1.0",
        "step_3_1_commit": STEP_3_1_COMMIT,
        "step_3_2_commit": STEP_3_2_COMMIT,
    }


def predeclaration(
    *,
    command: str,
    run_id: str,
    start_utc: str,
    script_sha256: str,
) -> dict[str, Any]:
    return {
        "config_sha256": DETECTOR_CONFIG_SHA256,
        "detector_identity_sha256": DETECTOR_IDENTITY_SHA256,
        "detector_version": DETECTOR_VERSION,
        "expected_input_count": EXPECTED_INPUT_COUNT,
        "formal_production_ordinal": PRODUCTION_RUN_ORDINAL,
        "formal_production_run_count": PRODUCTION_RUN_COUNT,
        "geometric_visible_opened": False,
        "implementation_sha256": DETECTOR_IMPLEMENTATION_SHA256,
        "person_c_input_commit": PERSON_C_CURRENT_COMMIT,
        "person_c_package_aggregate_sha256": PERSON_C_AGGREGATE_SHA256,
        "person_c_package_inventory_sha256": PERSON_C_INVENTORY_SHA256,
        "person_e_starting_commit": PERSON_E_START_COMMIT,
        "production_command": command,
        "run_id": run_id,
        "run_start_utc": start_utc,
        "schema_id": f"{SCHEMA_ID}-run-predeclaration-v1.0",
        "schema_version": "1.0",
        "settings_sha256": DETECTOR_SETTINGS_SHA256,
        "truth_channels_available_to_detector": False,
        "tuning_authorized": False,
        "u4_output_inspected": False,
        "visible_flag_available_to_detector": False,
        "production_generator_sha256": script_sha256,
    }


def empirical_rows_from_diagnostics(
    diagnostics: Sequence[Mapping[str, Any]],
    generation_rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    source_by_key = {
        (row["trajectory_id"], row["model_frame_idx"]): row
        for row in generation_rows
    }
    output: list[dict[str, Any]] = []
    for diagnostic in diagnostics:
        key = (diagnostic["trajectory_id"], diagnostic["model_frame_idx"])
        source = source_by_key.get(key)
        require(source is not None, f"Outcome identity is absent from Person C: {key}")
        output.append(
            {
                "canonical_camera_pose_id": source["canonical_camera_pose_id"],
                "coordinate_convention": source["coordinate_convention"],
                "detector_version": DETECTOR_VERSION,
                "empirical_magenta_visible": diagnostic[
                    "empirical_magenta_visible"
                ],
                "layout_id": source["layout_id"],
                "model_frame_idx": source["model_frame_idx"],
                "resolution": source["resolution"],
                "trajectory_id": source["trajectory_id"],
            }
        )
    return sorted(
        output,
        key=lambda row: (row["trajectory_id"], row["model_frame_idx"]),
    )


def per_layout_coverage(
    empirical_rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    grouped: dict[str, Counter[str]] = defaultdict(Counter)
    for row in empirical_rows:
        grouped[row["layout_id"]]["input"] += 1
        grouped[row["layout_id"]][
            "accepted" if row["empirical_magenta_visible"] else "rejected"
        ] += 1
    return [
        {
            "accepted_count": counts["accepted"],
            "input_count": counts["input"],
            "layout_id": layout_id,
            "rejected_count": counts["rejected"],
        }
        for layout_id, counts in sorted(grouped.items())
    ]


def assert_no_accuracy_fields(value: Any, *, location: str) -> None:
    if isinstance(value, Mapping):
        prohibited = set(value) & ACCURACY_FIELD_NAMES
        require(
            not prohibited,
            f"Accuracy fields are prohibited in {location}: {sorted(prohibited)}",
        )
        for key, child in value.items():
            assert_no_accuracy_fields(child, location=f"{location}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            assert_no_accuracy_fields(child, location=f"{location}[{index}]")


def validate_output_package(
    output_directory: Path,
    generation_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    reject_u4_path(output_directory)
    actual_files = {
        path.relative_to(output_directory).as_posix()
        for path in output_directory.rglob("*")
        if path.is_file()
    }
    require(
        actual_files == EXPECTED_OUTPUT_FILES,
        "Empirical package file set changed.",
    )
    json_documents: dict[str, dict[str, Any]] = {}
    for relative in sorted(name for name in actual_files if name.endswith(".json")):
        path = output_directory / relative
        raw = path.read_bytes()
        document = load_json(path, relative)
        require(
            raw == json_bytes(document),
            f"{relative} is not deterministically formatted.",
        )
        require(
            document.get("schema_version") == "1.0",
            f"{relative} schema_version changed.",
        )
        schema_identifier = document.get("schema_id")
        require(
            isinstance(schema_identifier, str) and SCHEMA_ID in schema_identifier,
            f"{relative} schema identifier is invalid.",
        )
        assert_no_accuracy_fields(document, location=relative)
        json_documents[relative] = document
    empirical_path = output_directory / "empirical_visibility_records.jsonl"
    diagnostics_path = output_directory / "detector_diagnostics.jsonl"
    empirical = load_jsonl(empirical_path, "empirical records")
    diagnostics = load_jsonl(diagnostics_path, "detector diagnostics")
    for path, rows in ((empirical_path, empirical), (diagnostics_path, diagnostics)):
        raw_lines = path.read_text(encoding="utf-8").splitlines()
        require(
            raw_lines
            == [
                jsonl_line(row).decode("utf-8").rstrip("\n") for row in rows
            ],
            f"{path.name} is not deterministically formatted.",
        )
        for index, row in enumerate(rows):
            assert_no_accuracy_fields(row, location=f"{path.name}[{index}]")
    counts = validate_empirical_records(empirical, diagnostics, generation_rows)
    coverage = json_documents["coverage_report.json"]
    require(
        coverage.get("expected_rows")
        == coverage.get("produced_rows")
        == coverage.get("unique_keys")
        == EXPECTED_INPUT_COUNT,
        "Coverage row counts changed.",
    )
    require(
        coverage.get("missing_keys")
        == coverage.get("duplicate_keys")
        == coverage.get("extra_keys")
        == 0,
        "Coverage identity accounting changed.",
    )
    require(
        coverage.get("diagnostic_rows") == EXPECTED_INPUT_COUNT
        and coverage.get("c_empirical_key_set_equality") is True
        and coverage.get("empirical_diagnostic_key_set_equality") is True,
        "Coverage key-set assertions changed.",
    )
    require(
        coverage.get("accepted_count") == counts["accepted_count"]
        and coverage.get("rejected_count") == counts["rejected_count"]
        and coverage.get("accepted_count") + coverage.get("rejected_count")
        == EXPECTED_INPUT_COUNT,
        "Accepted/rejected accounting changed.",
    )
    require(
        coverage.get("rejection_reason_counts")
        == counts["rejection_reason_counts"],
        "Rejection-reason accounting changed.",
    )
    require(
        coverage.get("per_layout") == per_layout_coverage(empirical),
        "Per-layout coverage changed.",
    )
    receipt = json_documents["production_run_receipt.json"]
    require(
        receipt.get("completed_count") == EXPECTED_INPUT_COUNT
        and receipt.get("missing_count") == 0
        and receipt.get("duplicate_count") == 0
        and receipt.get("extra_count") == 0
        and receipt.get("detector_exception_count") == 0,
        "Production receipt coverage changed.",
    )
    require(
        receipt.get("formal_production_ordinal") == PRODUCTION_RUN_ORDINAL
        and receipt.get("formal_production_run_count") == PRODUCTION_RUN_COUNT,
        "Production chronology ordinal changed.",
    )
    for field in (
        "detector_config_changed_after_start",
        "detector_implementation_changed_after_start",
        "geometric_visible_opened",
        "second_production_pass_occurred",
        "tuning_after_start",
        "u4_output_inspected",
        "visible_flag_computed",
    ):
        require(receipt.get(field) is False, f"Production receipt {field} changed.")
    start = datetime.fromisoformat(
        receipt["run_start_utc"].replace("Z", "+00:00")
    )
    end = datetime.fromisoformat(receipt["run_end_utc"].replace("Z", "+00:00"))
    require(end >= start, "Production chronology timestamps are invalid.")
    authority = json_documents["authority_binding.json"]
    require(
        authority.get("person_c_current_commit") == PERSON_C_CURRENT_COMMIT
        and authority.get("person_c_package_commit") == PERSON_C_PACKAGE_COMMIT
        and authority.get("person_b_policy_commit") == PERSON_B_POLICY_COMMIT,
        "Authority commit binding changed.",
    )
    require(
        authority.get("detector", {}).get("identity_sha256")
        == DETECTOR_IDENTITY_SHA256
        and authority.get("detector", {}).get("version") == DETECTOR_VERSION,
        "Authority detector binding changed.",
    )
    inventory_path = output_directory / "sha256_inventory.json"
    inventory = json_documents["sha256_inventory.json"]
    declared = inventory.get("files")
    require(isinstance(declared, dict), "Output SHA-256 inventory is malformed.")
    require(
        set(declared) == actual_files - {"sha256_inventory.json"},
        "Output SHA-256 inventory coverage changed.",
    )
    for relative, expected_hash in declared.items():
        require(
            sha256_file(output_directory / relative) == expected_hash,
            f"Output SHA-256 mismatch: {relative}",
        )
    require(
        inventory.get("package_file_count") == len(EXPECTED_OUTPUT_FILES),
        "Output package file count changed.",
    )
    require(
        json_documents["provenance_index.json"]
        .get("output_hashes", {})
        .get("empirical_visibility_records_sha256")
        == sha256_file(empirical_path),
        "Empirical provenance hash changed.",
    )
    require(
        json_documents["provenance_index.json"]
        .get("output_hashes", {})
        .get("detector_diagnostics_sha256")
        == sha256_file(diagnostics_path),
        "Diagnostic provenance hash changed.",
    )
    return {
        **counts,
        "diagnostic_rows": len(diagnostics),
        "empirical_rows": len(empirical),
        "inventory_sha256": sha256_file(inventory_path),
        "output_file_sha256": {
            relative: sha256_file(output_directory / relative)
            for relative in sorted(actual_files)
        },
    }


def finalize_package(
    *,
    output_directory: Path,
    generation_rows: Sequence[Mapping[str, Any]],
    diagnostics: Sequence[Mapping[str, Any]],
    c_binding: Mapping[str, Any],
    candidate_binding: Mapping[str, str],
    runtime: Mapping[str, str],
    run_id: str,
    run_start_utc: str,
    run_end_utc: str,
    command: str,
    script_sha256: str,
) -> dict[str, Any]:
    empirical = empirical_rows_from_diagnostics(diagnostics, generation_rows)
    counts = validate_empirical_records(
        empirical,
        diagnostics,
        generation_rows,
    )
    empirical_path = output_directory / "empirical_visibility_records.jsonl"
    write_exclusive(
        empirical_path,
        b"".join(jsonl_line(row) for row in empirical),
    )
    write_json_exclusive(
        output_directory / "empirical_visibility_schema.json",
        schema_document(empirical=True),
    )
    write_json_exclusive(
        output_directory / "detector_diagnostics_schema.json",
        schema_document(empirical=False),
    )
    write_json_exclusive(
        output_directory / "authority_binding.json",
        authority_binding(candidate_binding),
    )
    diagnostics_path = output_directory / "detector_diagnostics.jsonl"
    diagnostics_sha256 = sha256_file(diagnostics_path)
    empirical_sha256 = sha256_file(empirical_path)
    production_receipt = {
        "completed_count": EXPECTED_INPUT_COUNT,
        "detector_config_changed_after_start": False,
        "detector_exception_count": 0,
        "detector_implementation_changed_after_start": False,
        "diagnostic_ledger_sha256": diagnostics_sha256,
        "duplicate_count": 0,
        "extra_count": 0,
        "formal_production_ordinal": PRODUCTION_RUN_ORDINAL,
        "formal_production_run_count": PRODUCTION_RUN_COUNT,
        "geometric_visible_opened": False,
        "missing_count": 0,
        "run_end_utc": run_end_utc,
        "run_id": run_id,
        "run_start_utc": run_start_utc,
        "schema_id": f"{SCHEMA_ID}-production-run-receipt-v1.0",
        "schema_version": "1.0",
        "second_production_pass_occurred": False,
        "tuning_after_start": False,
        "u4_output_inspected": False,
        "visible_flag_computed": False,
    }
    write_json_exclusive(
        output_directory / "production_run_receipt.json",
        production_receipt,
    )
    coverage = {
        "accepted_count": counts["accepted_count"],
        "accepted_plus_rejected_equals_input": (
            counts["accepted_count"] + counts["rejected_count"]
            == EXPECTED_INPUT_COUNT
        ),
        "c_empirical_key_set_equality": True,
        "diagnostic_rows": EXPECTED_INPUT_COUNT,
        "duplicate_keys": 0,
        "empirical_diagnostic_key_set_equality": True,
        "expected_rows": EXPECTED_INPUT_COUNT,
        "extra_keys": 0,
        "missing_keys": 0,
        "per_layout": per_layout_coverage(empirical),
        "produced_rows": EXPECTED_INPUT_COUNT,
        "rejected_count": counts["rejected_count"],
        "rejection_reason_counts": counts["rejection_reason_counts"],
        "schema_id": f"{SCHEMA_ID}-coverage-report-v1.0",
        "schema_version": "1.0",
        "unique_keys": EXPECTED_INPUT_COUNT,
    }
    write_json_exclusive(output_directory / "coverage_report.json", coverage)
    provenance = {
        "authority_bindings": {
            "person_b_policy_commit": PERSON_B_POLICY_COMMIT,
            "person_c_current_commit": PERSON_C_CURRENT_COMMIT,
            "person_c_package_commit": PERSON_C_PACKAGE_COMMIT,
            "person_e_starting_commit": PERSON_E_START_COMMIT,
        },
        "detector": {
            "config_sha256": DETECTOR_CONFIG_SHA256,
            "identity_sha256": DETECTOR_IDENTITY_SHA256,
            "implementation_sha256": DETECTOR_IMPLEMENTATION_SHA256,
            "settings_sha256": DETECTOR_SETTINGS_SHA256,
            "version": DETECTOR_VERSION,
        },
        "exact_command": command,
        "formal_production_ordinal": PRODUCTION_RUN_ORDINAL,
        "formal_production_run_count": PRODUCTION_RUN_COUNT,
        "input_hashes": {
            "archive_sha256": c_binding["archive_binding"]["archive_sha256"],
            "generation_input_manifest_sha256": c_binding[
                "generation_manifest_sha256"
            ],
            "identity_manifest_sha256": c_binding["identity_manifest_sha256"],
            "package_aggregate_sha256": PERSON_C_AGGREGATE_SHA256,
            "package_inventory_sha256": PERSON_C_INVENTORY_SHA256,
        },
        "output_hashes": {
            "detector_diagnostics_sha256": diagnostics_sha256,
            "empirical_visibility_records_sha256": empirical_sha256,
        },
        "production_generator_sha256": script_sha256,
        "run_end_utc": run_end_utc,
        "run_id": run_id,
        "run_start_utc": run_start_utc,
        "runtime": dict(runtime),
        "schema_id": f"{SCHEMA_ID}-provenance-index-v1.0",
        "schema_version": "1.0",
    }
    write_json_exclusive(output_directory / "provenance_index.json", provenance)
    validation_receipt = {
        "accepted_plus_rejected_equals_input": True,
        "all_context_values_exact": True,
        "all_empirical_values_boolean": True,
        "c_empirical_key_set_equality": True,
        "detector_config_changed": False,
        "detector_executed_in_validation_only_mode": False,
        "detector_identity_exact": True,
        "detector_implementation_changed": False,
        "empirical_diagnostic_key_set_equality": True,
        "forbidden_fields_absent": True,
        "geometric_visible_opened": False,
        "no_accuracy_metrics_generated": True,
        "production_run_count": PRODUCTION_RUN_COUNT,
        "production_run_ordinal": PRODUCTION_RUN_ORDINAL,
        "schema_id": f"{SCHEMA_ID}-validation-receipt-v1.0",
        "schema_version": "1.0",
        "second_production_pass_occurred": False,
        "tuning_occurred": False,
        "u4_output_inspected": False,
        "validation_only_mode_passed": True,
        "visible_flag_computed": False,
    }
    write_json_exclusive(
        output_directory / "validation_receipt.json",
        validation_receipt,
    )
    phase3_status = {
        "overall_phase_3": "IN_PROGRESS",
        "person_b_final_joined_package_validation": "PENDING",
        "person_b_step_3_3_policy": "READY",
        "person_c_final_strict_join": "PENDING",
        "person_c_generation_input_authority": "READY",
        "person_e_empirical_generation": "READY",
        "schema_id": f"{SCHEMA_ID}-phase3-status-v1.0",
        "schema_version": "1.0",
        "step_3_1": "PASS",
        "step_3_2": "PASS",
        "u4_output_inspected": False,
    }
    write_json_exclusive(output_directory / "phase3_status.json", phase3_status)
    current_files = {
        path.relative_to(output_directory).as_posix(): sha256_file(path)
        for path in output_directory.rglob("*")
        if path.is_file() and path.name != "sha256_inventory.json"
    }
    write_json_exclusive(
        output_directory / "sha256_inventory.json",
        {
            "files": dict(sorted(current_files.items())),
            "package_file_count": len(EXPECTED_OUTPUT_FILES),
            "schema_id": f"{SCHEMA_ID}-sha256-inventory-v1.0",
            "schema_version": "1.0",
        },
    )
    return validate_output_package(output_directory, generation_rows)


def production(args: argparse.Namespace) -> int:
    output_directory = args.output_dir.resolve()
    person_c_root = args.person_c_root.resolve()
    reject_u4_path(output_directory)
    validate_person_e_scope(output_directory)
    require(args.run_id == EXPECTED_RUN_ID, "Production run ID changed.")
    require(
        args.formal_production_ordinal == PRODUCTION_RUN_ORDINAL,
        "Formal production ordinal must be exactly one.",
    )
    require(
        not output_directory.exists(),
        "Production output already exists; a second pass is prohibited.",
    )
    runtime = runtime_versions()
    config, _, candidate_binding = validate_frozen_detector()
    c_binding = load_and_verify_c_package(
        person_c_root,
        decode_preflight=True,
    )
    original_argv = getattr(sys, "orig_argv", [sys.executable, *sys.argv])
    command = subprocess.list2cmdline(
        [str(Path(sys.executable).resolve()), *original_argv[1:]]
    )
    run_start_utc = utc_now()
    script_sha256 = sha256_file(Path(__file__).resolve())
    output_directory.mkdir(parents=True, exist_ok=False)
    write_json_exclusive(
        output_directory / "run_predeclaration.json",
        predeclaration(
            command=command,
            run_id=args.run_id,
            start_utc=run_start_utc,
            script_sha256=script_sha256,
        ),
    )
    arguments = detector_arguments(config)
    sys.path.insert(0, str(REPOSITORY / "src"))
    from mineocclude.vision.calibration import decode_png_rgb_bytes

    ledger_path = output_directory / "detector_diagnostics.jsonl"
    descriptor = os.open(
        ledger_path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
        0o644,
    )
    detector_execution_count = 0
    seen: set[tuple[str, int]] = set()
    try:
        with os.fdopen(descriptor, "wb") as ledger:
            for archive_relative, grouped_rows_iterator in groupby(
                c_binding["rows"],
                key=lambda row: row["archive_path"],
            ):
                grouped_rows = list(grouped_rows_iterator)
                archive_path = c_binding["package_root"] / archive_relative
                archive_sha256 = sha256_file(archive_path)
                expected_archive_sha256 = c_binding["archive_binding"][
                    "archive_sha256"
                ][archive_relative]
                require(
                    archive_sha256 == expected_archive_sha256,
                    f"Archive changed immediately before inference: {archive_relative}",
                )
                with tarfile.open(archive_path, "r:gz") as archive:
                    members = {member.name: member for member in archive.getmembers()}
                    for source in grouped_rows:
                        key = (
                            source["trajectory_id"],
                            source["model_frame_idx"],
                        )
                        require(key not in seen, f"Duplicate production identity: {key}")
                        require(
                            source["archive_sha256"] == archive_sha256,
                            f"Source/archive hash binding changed: {key}",
                        )
                        member = members.get(source["archive_member_path"])
                        require(
                            member is not None
                            and member.isfile()
                            and safe_relative_path(member.name),
                            f"Production archive member is missing or unsafe: {key}",
                        )
                        extracted = archive.extractfile(member)
                        require(
                            extracted is not None,
                            f"Production archive member cannot be read: {key}",
                        )
                        payload = extracted.read()
                        require(
                            len(payload) == source["frame_size_bytes"],
                            f"Production member size mismatch: {key}",
                        )
                        require(
                            sha256_bytes(payload) == source["frame_640_sha256"],
                            f"Production member SHA-256 mismatch: {key}",
                        )
                        try:
                            rgb = decode_png_rgb_bytes(payload)
                        except Exception as exc:
                            raise FailClosed(
                                f"Production PNG decode failed for {key}: {exc}"
                            ) from exc
                        require(
                            len(rgb) == EXPECTED_HEIGHT
                            and all(len(line) == EXPECTED_WIDTH for line in rgb),
                            f"Production frame dimensions changed: {key}",
                        )
                        result = call_detector_fail_closed(
                            execute_frozen_detector,
                            rgb,
                            arguments,
                        )
                        detector_execution_count += 1
                        row = diagnostic_row(
                            source,
                            result,
                            ordinal=detector_execution_count,
                        )
                        ledger.write(jsonl_line(row))
                        ledger.flush()
                        os.fsync(ledger.fileno())
                        seen.add(key)
                        if detector_execution_count % 25 == 0:
                            print(
                                f"production_progress={detector_execution_count}/"
                                f"{EXPECTED_INPUT_COUNT}",
                                flush=True,
                            )
            ledger.flush()
            os.fsync(ledger.fileno())
    except BaseException:
        try:
            os.close(descriptor)
        except OSError:
            pass
        raise
    require(
        detector_execution_count == EXPECTED_INPUT_COUNT,
        "Production detector execution count changed.",
    )
    require(
        seen == set(c_binding["identity_keys"]),
        "Production detector identity coverage changed.",
    )
    diagnostics = load_jsonl(ledger_path, "durable detector outcome ledger")
    require(
        len(diagnostics) == EXPECTED_INPUT_COUNT,
        "Durable detector outcome ledger is incomplete.",
    )
    run_end_utc = utc_now()
    final = finalize_package(
        output_directory=output_directory,
        generation_rows=c_binding["rows"],
        diagnostics=diagnostics,
        c_binding=c_binding,
        candidate_binding=candidate_binding,
        runtime=runtime,
        run_id=args.run_id,
        run_start_utc=run_start_utc,
        run_end_utc=run_end_utc,
        command=command,
        script_sha256=script_sha256,
    )
    print(
        json.dumps(
            {
                "accepted_count": final["accepted_count"],
                "detector_execution_count": detector_execution_count,
                "diagnostic_rows": final["diagnostic_rows"],
                "empirical_rows": final["empirical_rows"],
                "rejected_count": final["rejected_count"],
                "run_end_utc": run_end_utc,
                "run_id": args.run_id,
                "run_start_utc": run_start_utc,
                "validation_only_result": "PASS",
            },
            sort_keys=True,
        ),
        flush=True,
    )
    return 0


def validation_only(args: argparse.Namespace) -> int:
    output_directory = args.output_dir.resolve()
    person_c_root = args.person_c_root.resolve()
    reject_u4_path(output_directory)
    validate_person_e_scope(output_directory)
    validate_frozen_detector()
    c_binding = load_and_verify_c_package(
        person_c_root,
        decode_preflight=False,
    )
    result = validate_output_package(output_directory, c_binding["rows"])
    print(
        json.dumps(
            {
                "accepted_count": result["accepted_count"],
                "detector_executed": False,
                "diagnostic_rows": result["diagnostic_rows"],
                "empirical_rows": result["empirical_rows"],
                "rejected_count": result["rejected_count"],
                "validation_only_result": "PASS",
            },
            sort_keys=True,
        )
    )
    return 0


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    subcommands = root.add_subparsers(dest="mode", required=True)
    production_parser = subcommands.add_parser("production")
    production_parser.add_argument("--person-c-root", required=True, type=Path)
    production_parser.add_argument("--output-dir", required=True, type=Path)
    production_parser.add_argument("--run-id", required=True)
    production_parser.add_argument(
        "--formal-production-ordinal",
        required=True,
        type=int,
    )
    validation_parser = subcommands.add_parser("validate")
    validation_parser.add_argument("--person-c-root", required=True, type=Path)
    validation_parser.add_argument("--output-dir", required=True, type=Path)
    return root


def main() -> int:
    arguments = parser().parse_args()
    try:
        if arguments.mode == "production":
            return production(arguments)
        return validation_only(arguments)
    except FailClosed as exc:
        print(f"FAIL_CLOSED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
