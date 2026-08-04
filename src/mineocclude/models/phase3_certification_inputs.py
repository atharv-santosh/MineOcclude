"""CPU-only preparation of bounded Person A Phase 3 certification inputs.

This module consumes an immutable Person C C6A handoff and produces a small
derivative package plus matching media outside Git.  It never loads PyTorch,
CUDA, MineWorld checkpoints, the VAE, or either model execution path.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import tarfile
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path, PurePosixPath
from typing import Any

from mineocclude.contracts.identity import SCHEMA_VERSION
from mineocclude.contracts.trajectory import ROW_STREAMS, validate_trajectory_package
from mineocclude.models._mineworld_adapter_wave2 import (
    ACTION_CONVERTER_IDENTITY,
    MCDATASET_BLOB_SHA256,
    PINNED_ASSET_REVISION,
    PINNED_MAX_POSITION_EMBEDDINGS,
    PINNED_SOURCE_REVISION,
    PINNED_TOKENS_PER_PAIR,
    PINNED_VISUAL_TOKENS,
    _OfficialActionConverter,
    _git_blob_sha256,
    _inspect_source,
)
from mineocclude.models.phase2_evidence import (
    canonical_json_bytes,
    parse_ffprobe_output,
    sha256_file,
)
from mineocclude.models.phase3_certification import _certify_action_fixture


PREPARATION_VERSION = "person-a-phase3-certification-inputs-v1.0"
EXPECTED_C6A_ARCHIVE_SHA256 = (
    "aaa38084e59cd20e70433c9ab169ecb140edde7a0f75e8bf86363bf95ebfbc2b"
)
EXPECTED_IMPULSE_ARCHIVE_SHA256 = (
    "823825b80d570d2f6df1bca40d765df62a2e3b47ffd82fda70d0bb18564c01d9"
)
EXPECTED_C6A_FRAME_COUNT = 129
EXPECTED_IMPULSE_FRAME_COUNT = 60
EXPECTED_BOUNDED_PAIR_COUNT = 8
MAX_CERTIFICATION_CONTEXT_PAIRS = 15
GENERATED_CERTIFICATION_FRAMES = 1
EXPECTED_WIDTH = 640
EXPECTED_HEIGHT = 360
EXPECTED_RATE = Fraction(20, 1)
_REPO_ROOT = Path(__file__).resolve().parents[3]
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_GIT_SHA = re.compile(r"^[0-9a-f]{40}$")
_FRAME_NAME = re.compile(r"^[0-9]{6}\.png$")
_CHECKSUM_LINE = re.compile(
    r"^([0-9A-Fa-f]{64})  ([^ \r\n].*?)(?:  ([0-9]+))?$"
)
_OUTPUT_DIRECTORY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_BUNDLE_DIRECTORY = "bundle"
_CHECKSUM_INVENTORY = "checksums.sha256"
_MANIFEST = "preparation_manifest.json"
_PACKAGE = "bounded_accepted_package.json"
_MP4 = "bounded_scene.mp4"


class PreparationError(RuntimeError):
    """Fail-closed preparation or validation error."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


@dataclass(frozen=True)
class ExtractedArchive:
    """Verified frame archive extraction result."""

    archive: Path
    archive_sha256: str
    inventory: Path
    inventory_sha256: str
    frame_directory: Path
    frame_paths: Mapping[str, Path]
    frame_hashes: Mapping[str, str]
    ignored_appledouble_members: tuple[str, ...]


@dataclass(frozen=True)
class SelectedWindow:
    """One deterministic accepted context window."""

    package_row_indices: tuple[int, ...]
    frame_rows: tuple[Mapping[str, Any], ...]
    action_records: tuple[Mapping[str, Any], ...]
    rejected_candidates: tuple[Mapping[str, Any], ...]


def _strict_json(path: Path, role: str) -> dict[str, Any]:
    resolved = path.resolve()
    if not resolved.is_file():
        raise PreparationError("missing_input", f"{role} does not exist: {resolved}")

    def reject_constant(value: str) -> None:
        raise ValueError(f"non-finite JSON constant {value!r}")

    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key {key!r}")
            result[key] = value
        return result

    try:
        document = json.loads(
            resolved.read_text(encoding="utf-8"),
            parse_constant=reject_constant,
            object_pairs_hook=unique_object,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise PreparationError(
            "invalid_json",
            f"{role} is not strict finite JSON: {exc}",
        ) from exc
    if not isinstance(document, dict):
        raise PreparationError("invalid_json", f"{role} must be one JSON object")
    return document


def _strict_jsonl(path: Path, role: str) -> list[dict[str, Any]]:
    resolved = path.resolve()
    if not resolved.is_file():
        raise PreparationError("missing_input", f"{role} does not exist: {resolved}")
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(
        resolved.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        if not line.strip():
            raise PreparationError(
                "invalid_jsonl",
                f"{role} contains a blank row at line {line_number}",
            )
        # Use the exact duplicate/non-finite rejection policy without
        # accepting Python literals or a permissive fallback parser.
        def reject_constant(value: str) -> None:
            raise ValueError(f"non-finite JSON constant {value!r}")

        def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
            result: dict[str, Any] = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError(f"duplicate JSON key {key!r}")
                result[key] = value
            return result

        try:
            row = json.loads(
                line,
                parse_constant=reject_constant,
                object_pairs_hook=unique_object,
            )
        except (json.JSONDecodeError, ValueError) as exc:
            raise PreparationError(
                "invalid_jsonl",
                f"{role} line {line_number}: {exc}",
            ) from exc
        if not isinstance(row, dict):
            raise PreparationError(
                "invalid_jsonl",
                f"{role} line {line_number} must be a JSON object",
            )
        rows.append(row)
    if not rows:
        raise PreparationError("invalid_jsonl", f"{role} contains no rows")
    return rows


def _write_json(path: Path, document: Mapping[str, Any]) -> None:
    payload = json.dumps(
        document,
        indent=2,
        sort_keys=True,
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8") + b"\n"
    path.write_bytes(payload)


def _git(root: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *arguments],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        raise PreparationError(
            "git_inspection_failed",
            (result.stderr or result.stdout or "git failed").strip(),
        )
    return result.stdout.strip()


def _git_identity(root: Path) -> dict[str, Any]:
    repository = Path(_git(root, "rev-parse", "--show-toplevel")).resolve()
    return {
        "root": repository,
        "head": _git(repository, "rev-parse", "HEAD"),
        "clean": not bool(_git(repository, "status", "--porcelain")),
    }


def _require_exact_repo(
    root: Path,
    *,
    expected_revision: str,
    role: str,
) -> dict[str, Any]:
    identity = _git_identity(root)
    if identity["head"] != expected_revision:
        raise PreparationError(
            "revision_mismatch",
            f"{role} expected {expected_revision}, observed {identity['head']}",
        )
    if identity["clean"] is not True:
        raise PreparationError("dirty_repository", f"{role} worktree is dirty")
    return identity


def parse_checksum_inventory(path: Path) -> dict[str, dict[str, Any]]:
    """Strictly parse a SHA-256 inventory with an optional byte-size column."""

    resolved = path.resolve()
    if not resolved.is_file():
        raise PreparationError(
            "missing_checksum_inventory",
            f"checksum inventory does not exist: {resolved}",
        )
    records: dict[str, dict[str, Any]] = {}
    lines = resolved.read_text(encoding="utf-8").splitlines()
    if not lines:
        raise PreparationError("malformed_checksum_inventory", "inventory is empty")
    for line_number, line in enumerate(lines, start=1):
        match = _CHECKSUM_LINE.fullmatch(line)
        if match is None:
            raise PreparationError(
                "malformed_checksum_inventory",
                f"line {line_number} is not '<sha256>  <path> [  <size>]'",
            )
        digest, name, size_text = match.groups()
        pure = PurePosixPath(name.replace("\\", "/"))
        if (
            pure.is_absolute()
            or ".." in pure.parts
            or "." in pure.parts
            or not pure.parts
        ):
            raise PreparationError(
                "unsafe_checksum_path",
                f"line {line_number} has unsafe path {name!r}",
            )
        normalized = pure.as_posix()
        if normalized in records:
            raise PreparationError(
                "duplicate_checksum_filename",
                f"duplicate checksum filename {normalized!r}",
            )
        records[normalized] = {
            "sha256": digest.lower(),
            "size_bytes": int(size_text) if size_text is not None else None,
        }
    return records


def _verify_checksum_inventory(
    directory: Path,
    inventory_path: Path,
    *,
    excluded_names: set[str] | None = None,
) -> dict[str, dict[str, Any]]:
    records = parse_checksum_inventory(inventory_path)
    excluded = excluded_names or set()
    actual = {
        path.relative_to(directory).as_posix()
        for path in directory.rglob("*")
        if path.is_file() and path.name not in excluded
    }
    if set(records) != actual:
        missing = sorted(set(records) - actual)
        unexpected = sorted(actual - set(records))
        raise PreparationError(
            "checksum_inventory_file_set_mismatch",
            f"missing={missing}, unexpected={unexpected}",
        )
    for name, record in records.items():
        path = directory / Path(name)
        observed_size = path.stat().st_size
        observed_hash = sha256_file(path)
        if record["size_bytes"] is not None and record["size_bytes"] != observed_size:
            raise PreparationError(
                "checksum_size_mismatch",
                f"{name}: expected {record['size_bytes']}, observed {observed_size}",
            )
        if record["sha256"] != observed_hash:
            raise PreparationError(
                "checksum_hash_mismatch",
                f"{name}: expected {record['sha256']}, observed {observed_hash}",
            )
    return records


def _is_appledouble_member(name: str, expected_frames: set[str]) -> bool:
    pure = PurePosixPath(name)
    if pure.as_posix() == "._frames_640x360":
        return True
    if len(pure.parts) != 2 or pure.parts[0] != "frames_640x360":
        return False
    basename = pure.name
    return (
        basename.startswith("._")
        and basename[2:] in expected_frames
        and _FRAME_NAME.fullmatch(basename[2:]) is not None
    )


def verify_and_extract_frame_archive(
    archive_path: Path,
    inventory_path: Path,
    destination: Path,
    *,
    expected_archive_sha256: str,
    expected_count: int,
) -> ExtractedArchive:
    """Verify and safely extract only inventoried PNG members."""

    archive = archive_path.resolve()
    inventory = inventory_path.resolve()
    if not archive.is_file():
        raise PreparationError("missing_archive", f"archive does not exist: {archive}")
    observed_archive_hash = sha256_file(archive)
    if observed_archive_hash != expected_archive_sha256:
        raise PreparationError(
            "archive_hash_mismatch",
            (
                f"{archive.name}: expected {expected_archive_sha256}, "
                f"observed {observed_archive_hash}"
            ),
        )
    inventory_records = parse_checksum_inventory(inventory)
    if len(inventory_records) != expected_count:
        raise PreparationError(
            "frame_inventory_count_mismatch",
            f"expected {expected_count} frames, observed {len(inventory_records)}",
        )
    expected_frames = set(inventory_records)
    if any(_FRAME_NAME.fullmatch(name) is None for name in expected_frames):
        raise PreparationError(
            "malformed_frame_inventory",
            "frame inventory must contain only zero-padded PNG basenames",
        )

    destination = destination.resolve()
    destination.mkdir(parents=True, exist_ok=False)
    members_by_frame: dict[str, tarfile.TarInfo] = {}
    ignored: list[str] = []
    seen_members: set[str] = set()
    with tarfile.open(archive, mode="r:gz") as handle:
        for member in handle.getmembers():
            normalized = PurePosixPath(member.name.replace("\\", "/"))
            normalized_name = normalized.as_posix()
            if (
                normalized.is_absolute()
                or ".." in normalized.parts
                or "." in normalized.parts
            ):
                raise PreparationError(
                    "unsafe_archive_path",
                    f"unsafe archive member {member.name!r}",
                )
            if normalized_name in seen_members:
                raise PreparationError(
                    "duplicate_archive_member",
                    f"duplicate archive member {normalized_name!r}",
                )
            seen_members.add(normalized_name)
            if member.isdir():
                if normalized_name != "frames_640x360":
                    raise PreparationError(
                        "unexpected_archive_member",
                        f"unexpected directory {normalized_name!r}",
                    )
                continue
            if not member.isfile():
                raise PreparationError(
                    "unsupported_archive_member",
                    f"unsupported member type for {normalized_name!r}",
                )
            if _is_appledouble_member(normalized_name, expected_frames):
                ignored.append(normalized_name)
                continue
            if (
                len(normalized.parts) != 2
                or normalized.parts[0] != "frames_640x360"
                or normalized.name not in expected_frames
            ):
                if normalized.suffix.lower() == ".png":
                    code = "unexpected_frame"
                else:
                    code = "unexpected_archive_member"
                raise PreparationError(code, f"unexpected member {normalized_name!r}")
            if normalized.name in members_by_frame:
                raise PreparationError(
                    "duplicate_frame",
                    f"duplicate frame member {normalized.name!r}",
                )
            members_by_frame[normalized.name] = member

        missing = sorted(expected_frames - set(members_by_frame))
        if missing:
            raise PreparationError("missing_frame", f"missing frames: {missing}")
        extracted: dict[str, Path] = {}
        for name in sorted(expected_frames):
            member = members_by_frame[name]
            source = handle.extractfile(member)
            if source is None:
                raise PreparationError(
                    "archive_extraction_failed",
                    f"could not read archive member {member.name!r}",
                )
            output = destination / name
            with source, output.open("xb") as target:
                shutil.copyfileobj(source, target)
            observed = sha256_file(output)
            expected = inventory_records[name]["sha256"]
            if observed != expected:
                raise PreparationError(
                    "extracted_frame_hash_mismatch",
                    f"{name}: expected {expected}, observed {observed}",
                )
            extracted[name] = output

    return ExtractedArchive(
        archive=archive,
        archive_sha256=observed_archive_hash,
        inventory=inventory,
        inventory_sha256=sha256_file(inventory),
        frame_directory=destination,
        frame_paths=extracted,
        frame_hashes={name: record["sha256"] for name, record in inventory_records.items()},
        ignored_appledouble_members=tuple(sorted(ignored)),
    )


def _verify_episode_checksums(episode: Path) -> dict[str, dict[str, Any]]:
    marker = episode / "COMPLETE"
    if not marker.is_file() or not marker.read_text(encoding="utf-8").strip():
        raise PreparationError("missing_complete_marker", "episode COMPLETE is absent")
    inventory = episode / _CHECKSUM_INVENTORY
    records = parse_checksum_inventory(inventory)
    actual = {
        path.name
        for path in episode.iterdir()
        if path.is_file() and path.name not in {"COMPLETE", _CHECKSUM_INVENTORY}
    }
    if set(records) != actual:
        raise PreparationError(
            "episode_checksum_file_set_mismatch",
            (
                f"declared-only={sorted(set(records) - actual)}, "
                f"undeclared={sorted(actual - set(records))}"
            ),
        )
    for name, record in records.items():
        path = episode / name
        if record["size_bytes"] != path.stat().st_size:
            raise PreparationError(
                "episode_file_size_mismatch",
                f"{name} size does not match checksums.sha256",
            )
        if record["sha256"] != sha256_file(path):
            raise PreparationError(
                "episode_file_hash_mismatch",
                f"{name} hash does not match checksums.sha256",
            )
    return records


def _jsonl_bytes(rows: Sequence[Mapping[str, Any]]) -> bytes:
    return b"".join(
        json.dumps(
            row,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
        + b"\n"
        for row in rows
    )


def _verify_original_package(episode: Path) -> dict[str, Any]:
    checksums = _verify_episode_checksums(episode)
    package_path = episode / "capture_package_v0_1.json"
    package = _strict_json(package_path, "C6A capture package")
    result = validate_trajectory_package(package)
    if not result.accepted:
        first = result.rejections[0]
        raise PreparationError(
            "original_package_rejected",
            f"{first.code.value}: {first.message}",
        )
    qa = _strict_json(episode / "qa_report.json", "C6A QA report")
    if qa.get("accepted") is not True or qa.get("status") != "accepted":
        raise PreparationError("original_qa_rejected", "C6A QA report is not accepted")
    if (
        package.get("schema_version") != SCHEMA_VERSION
        or package.get("synthetic") is not False
        or package.get("media", {}).get("frame_count") != EXPECTED_C6A_FRAME_COUNT
        or any(
            len(package["streams"].get(name, [])) != EXPECTED_C6A_FRAME_COUNT
            for name in ROW_STREAMS
        )
    ):
        raise PreparationError(
            "original_package_cardinality_mismatch",
            "C6A package must contain exactly 129 real synchronized rows",
        )
    media_path = episode / "scene.mp4"
    if (
        package["media"].get("sha256") != sha256_file(media_path)
        or checksums["scene.mp4"]["sha256"] != sha256_file(media_path)
    ):
        raise PreparationError(
            "original_media_hash_mismatch",
            "C6A package media identity does not match scene.mp4",
        )

    for stream_name in ROW_STREAMS:
        expected = package["artifacts"][stream_name]["sha256"]
        observed = hashlib.sha256(_jsonl_bytes(package["streams"][stream_name])).hexdigest()
        if expected != observed:
            raise PreparationError(
                "embedded_stream_hash_mismatch",
                f"{stream_name} does not match its producer artifact hash",
            )
    raw_rows = _strict_jsonl(episode / "raw_actions.jsonl", "C6A raw actions")
    client_rows = _strict_jsonl(episode / "client_tick.jsonl", "C6A client ticks")
    state_rows = _strict_jsonl(episode / "server_state.jsonl", "C6A server state")
    if not (
        len(raw_rows)
        == len(client_rows)
        == len(state_rows)
        == EXPECTED_C6A_FRAME_COUNT
    ):
        raise PreparationError(
            "source_stream_cardinality_mismatch",
            "committed C6A JSONL streams must each contain 129 rows",
        )
    for index, (raw, embedded) in enumerate(
        zip(raw_rows, package["streams"]["raw_actions"])
    ):
        identity_fields = (
            "episode_id",
            "trajectory_id",
            "server_tick",
            "render_frame_idx",
            "action_idx",
            "model_frame_idx",
        )
        if any(raw.get(field) != embedded.get(field) for field in identity_fields):
            raise PreparationError(
                "raw_action_identity_mismatch",
                f"committed raw action {index} differs from the accepted package",
            )
        if raw.get("raw_action") != embedded.get("raw_action"):
            raise PreparationError(
                "raw_action_payload_mismatch",
                f"committed raw action {index} differs from the accepted package",
            )
    return {
        "package": package,
        "package_path": package_path.resolve(),
        "package_sha256": sha256_file(package_path),
        "package_size_bytes": package_path.stat().st_size,
        "qa": qa,
        "qa_sha256": sha256_file(episode / "qa_report.json"),
        "checksums": checksums,
        "checksums_sha256": sha256_file(episode / _CHECKSUM_INVENTORY),
        "raw_rows": raw_rows,
        "client_rows": client_rows,
        "state_rows": state_rows,
    }


def _run_ffprobe(path: Path, executable: str) -> dict[str, Any]:
    command = [
        executable,
        "-v",
        "error",
        "-count_frames",
        "-select_streams",
        "v:0",
        "-show_entries",
        (
            "stream=codec_name,pix_fmt,width,height,r_frame_rate,avg_frame_rate,"
            "duration,nb_frames,nb_read_frames"
        ),
        "-show_entries",
        "format=duration",
        "-of",
        "json",
        str(path),
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=False)
    except FileNotFoundError as exc:
        raise PreparationError("ffprobe_missing", f"not found: {executable}") from exc
    if result.returncode:
        raise PreparationError(
            "ffprobe_failed",
            (result.stderr or result.stdout or "ffprobe failed").strip(),
        )
    raw = json.loads(result.stdout)
    stream = raw["streams"][0]
    strict_raw = copy.deepcopy(raw)
    strict_raw["streams"][0].pop("codec_name", None)
    strict_raw["streams"][0].pop("pix_fmt", None)
    parsed = parse_ffprobe_output(json.dumps(strict_raw))
    parsed["codec_name"] = stream.get("codec_name")
    parsed["pixel_format"] = stream.get("pix_fmt")
    parsed["command"] = command
    return parsed


def _require_exact_media_probe(
    probe: Mapping[str, Any],
    *,
    frame_count: int,
    role: str,
    expected_duration: float | None = None,
) -> None:
    if (
        probe.get("width") != EXPECTED_WIDTH
        or probe.get("height") != EXPECTED_HEIGHT
        or Fraction(str(probe.get("r_frame_rate"))) != EXPECTED_RATE
        or Fraction(str(probe.get("avg_frame_rate"))) != EXPECTED_RATE
        or probe.get("declared_frames") != frame_count
        or probe.get("decoded_frames") != frame_count
        or (
            expected_duration is not None
            and not math.isclose(
                float(probe.get("duration_seconds", -1)),
                expected_duration,
                rel_tol=0.0,
                abs_tol=1e-6,
            )
        )
    ):
        raise PreparationError(
            "mp4_metadata_mismatch",
            f"{role} is not exact {frame_count}-frame 640x360 20 fps media",
        )


def _require_declared_media_identity(
    media: Mapping[str, Any],
    path: Path,
    *,
    role: str,
) -> None:
    if (
        media.get("size_bytes") != path.stat().st_size
        or media.get("sha256") != sha256_file(path)
    ):
        raise PreparationError(
            "bounded_media_hash_mismatch",
            f"{role} bytes do not match the derivative package",
        )


def _tool_version(executable: str) -> str:
    try:
        result = subprocess.run(
            [executable, "-version"],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as exc:
        raise PreparationError("media_tool_missing", f"not found: {executable}") from exc
    if result.returncode or not result.stdout.strip():
        raise PreparationError(
            "media_tool_failed",
            (result.stderr or result.stdout or f"{executable} failed").strip(),
        )
    return result.stdout.splitlines()[0]


def _resolved_executable(executable: str) -> str:
    resolved = shutil.which(executable)
    if resolved is None:
        raise PreparationError("media_tool_missing", f"not found: {executable}")
    return str(Path(resolved).resolve())


def _validate_impulse_fixture(
    fixture: Path,
    extracted: ExtractedArchive,
    *,
    ffprobe_executable: str,
) -> dict[str, Any]:
    required = {
        "IMPULSE_EVIDENCE.txt",
        "frame_map.parquet",
        "qa_report.json",
        "raw_actions.jsonl",
        "reset_result.json",
        "scene.mp4",
        "server_state.jsonl",
    }
    actual = {path.name for path in fixture.iterdir() if path.is_file()}
    missing = sorted(required - actual)
    if missing:
        raise PreparationError("impulse_evidence_incomplete", f"missing {missing}")
    qa_path = fixture / "qa_report.json"
    qa = _strict_json(qa_path, "impulse QA report")
    reset = _strict_json(fixture / "reset_result.json", "impulse reset result")
    actions = _strict_jsonl(fixture / "raw_actions.jsonl", "impulse raw actions")
    states = _strict_jsonl(fixture / "server_state.jsonl", "impulse server state")
    if (
        qa.get("accepted") is not True
        or qa.get("status") != "accepted"
        or qa.get("trajectory_id") != "layout_00_ep9440"
        or len(actions) != EXPECTED_IMPULSE_FRAME_COUNT
        or len(states) != EXPECTED_IMPULSE_FRAME_COUNT
        or reset.get("impulse_yaw_deg") != 20.0
        or reset.get("impulse_tick") != 30
    ):
        raise PreparationError(
            "invalid_impulse_evidence",
            "impulse identity, acceptance, cardinality, or scripted magnitude changed",
        )
    impulse_checks = [
        check
        for check in qa.get("checks", [])
        if isinstance(check, Mapping) and check.get("name") == "impulse_orientation"
    ]
    if len(impulse_checks) != 1 or impulse_checks[0].get("status") != "pass":
        raise PreparationError(
            "invalid_impulse_evidence",
            "QA report lacks one passing impulse-orientation result",
        )
    measured = impulse_checks[0].get("measured")
    if not isinstance(measured, Mapping):
        raise PreparationError("invalid_impulse_evidence", "impulse result is malformed")

    camera = [row.get("camera_dx") for row in actions]
    if any(
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        for value in camera
    ):
        raise PreparationError("invalid_impulse_evidence", "camera_dx is malformed")
    spike = max(range(len(camera)), key=lambda index: abs(float(camera[index])))
    if spike != 29 or float(camera[spike]) != 20.0:
        raise PreparationError(
            "invalid_impulse_evidence",
            f"expected the real 20-degree yaw at action 29, observed {spike}",
        )

    try:
        import cv2
        import numpy as np
    except Exception as exc:
        raise PreparationError(
            "impulse_decoder_unavailable",
            f"OpenCV/NumPy unavailable: {exc}",
        ) from exc
    frames = []
    for index in range(EXPECTED_IMPULSE_FRAME_COUNT):
        path = extracted.frame_paths[f"{index:06d}.png"]
        frame = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if frame is None or frame.shape != (EXPECTED_HEIGHT, EXPECTED_WIDTH, 3):
            raise PreparationError(
                "impulse_frame_decode_failed",
                f"could not decode {path.name} as 640x360x3",
            )
        frames.append(frame.astype(np.int16))
    differences = [
        float(np.abs(frames[index + 1] - frames[index]).mean())
        for index in range(len(frames) - 1)
    ]
    lower = max(0, spike - 2)
    upper = min(len(differences), spike + 3)
    effect = lower + max(
        range(upper - lower),
        key=lambda offset: differences[lower + offset],
    )
    offset = effect - spike
    competing = [
        differences[index]
        for index in range(lower, upper)
        if index != effect
    ]
    runner_up = max(competing, default=0.0)
    if (
        offset != 0
        or list(measured.get("effect_transition", [])) != [effect, effect + 1]
        or measured.get("offset") != 0
        or measured.get("action_idx") != spike
        or not isinstance(measured.get("effect_diff"), (int, float))
        or not math.isfinite(float(measured["effect_diff"]))
        or float(measured["effect_diff"]) <= 0
        or (
            runner_up > 0
            and differences[effect] < 3.0 * runner_up
        )
    ):
        raise PreparationError(
            "invalid_impulse_evidence",
            "independent pixel check does not reproduce causal offset zero",
        )
    evidence_text = (fixture / "IMPULSE_EVIDENCE.txt").read_text(encoding="utf-8")
    if "20deg" not in evidence_text or "offset 0" not in evidence_text:
        raise PreparationError(
            "invalid_impulse_evidence",
            "IMPULSE_EVIDENCE.txt lacks the real magnitude or offset result",
        )
    media_probe = _run_ffprobe(fixture / "scene.mp4", ffprobe_executable)
    if (
        media_probe["width"] != EXPECTED_WIDTH
        or media_probe["height"] != EXPECTED_HEIGHT
        or Fraction(media_probe["avg_frame_rate"]) != EXPECTED_RATE
        or media_probe["decoded_frames"] != EXPECTED_IMPULSE_FRAME_COUNT
    ):
        raise PreparationError(
            "invalid_impulse_media",
            "impulse MP4 does not match its 60-frame QA evidence",
        )
    files = {
        name: {
            "path": str((fixture / name).resolve()),
            "size_bytes": (fixture / name).stat().st_size,
            "sha256": sha256_file(fixture / name),
        }
        for name in sorted(required)
    }
    return {
        "status": "PASS",
        "trajectory_id": qa["trajectory_id"],
        "episode_id": str(qa["episode_id"]),
        "qa_report": files["qa_report.json"],
        "evidence_file": files["IMPULSE_EVIDENCE.txt"],
        "files": files,
        "action_idx": spike,
        "action_step_degrees": float(camera[spike]),
        "effect_transition": [effect, effect + 1],
        "qa_effect_difference": float(measured["effect_diff"]),
        "independent_archive_effect_difference": differences[effect],
        "independent_archive_runner_up_difference": runner_up,
        "causal_offset": offset,
        "causal_semantics": "action_i affects visual_i -> visual_(i+1)",
        "media_probe": media_probe,
    }


def _capture_key(row: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        row.get("episode_id"),
        row.get("trajectory_id"),
        row.get("server_tick"),
        row.get("render_frame_idx"),
        row.get("action_idx"),
        row.get("model_frame_idx"),
    )


def _excluded_keys(package: Mapping[str, Any]) -> set[tuple[Any, ...]]:
    excluded: set[tuple[Any, ...]] = set()
    ledger = package.get("exclusion_ledger", [])
    if not isinstance(ledger, list):
        raise PreparationError("invalid_exclusion_ledger", "ledger must be a list")
    for row in ledger:
        if not isinstance(row, Mapping):
            raise PreparationError(
                "invalid_exclusion_ledger",
                "every exclusion entry must be a mapping",
            )
        key = _capture_key(row)
        if all(value is not None for value in key):
            excluded.add(key)
        elif "model_frame_idx" in row:
            excluded.add(
                (
                    package.get("episode_id"),
                    package.get("trajectory_id"),
                    row.get("server_tick"),
                    row.get("render_frame_idx"),
                    row.get("action_idx"),
                    row.get("model_frame_idx"),
                )
            )
    return excluded


def select_earliest_window(
    package: Mapping[str, Any],
    extracted_frames: Mapping[str, Path],
    frame_hashes: Mapping[str, str],
    *,
    pair_count: int,
    converter: Any,
) -> SelectedWindow:
    """Select the earliest contiguous valid window without scientific criteria."""

    if pair_count != EXPECTED_BOUNDED_PAIR_COUNT or pair_count > MAX_CERTIFICATION_CONTEXT_PAIRS:
        raise PreparationError(
            "invalid_pair_count",
            "production certification preparation requires exactly eight pairs",
        )
    streams = package["streams"]
    frame_rows = list(streams["frame_map"])
    index_by_stream: dict[str, dict[tuple[str, int], Mapping[str, Any]]] = {}
    for name in ROW_STREAMS:
        index_by_stream[name] = {
            (row["trajectory_id"], row["model_frame_idx"]): row
            for row in streams[name]
        }
        if len(index_by_stream[name]) != len(streams[name]):
            raise PreparationError(
                "duplicate_identity",
                f"{name} contains duplicate scientific identities",
            )
    excluded = _excluded_keys(package)
    rejections: list[Mapping[str, Any]] = []
    for start in range(0, len(frame_rows) - pair_count + 1):
        candidate = frame_rows[start : start + pair_count]
        reasons: list[str] = []
        model_indices = [row["model_frame_idx"] for row in candidate]
        server_ticks = [row["server_tick"] for row in candidate]
        if any(
            current != previous + 1
            for previous, current in zip(model_indices, model_indices[1:])
        ):
            reasons.append("model_frame_idx_not_consecutive")
        if any(
            current != previous + 1
            for previous, current in zip(server_ticks, server_ticks[1:])
        ):
            reasons.append("server_ticks_not_consecutive")
        if len({_capture_key(row) for row in candidate}) != pair_count:
            reasons.append("duplicate_scientific_identity")
        action_records: list[Mapping[str, Any]] = []
        for row in candidate:
            key = (row["trajectory_id"], row["model_frame_idx"])
            for stream_name in ROW_STREAMS:
                if key not in index_by_stream[stream_name]:
                    reasons.append(f"missing_{stream_name}:{key}")
            if _capture_key(row) in excluded:
                reasons.append(f"quarantined_identity:{key}")
            visibility = index_by_stream["visibility"].get(key, {}).get("visibility")
            if not isinstance(visibility, str) or "quarantin" in visibility.lower():
                reasons.append(f"invalid_or_quarantined_visibility:{key}")
            source_name = f"{row['render_frame_idx']:06d}.png"
            source_path = extracted_frames.get(source_name)
            if source_path is None:
                reasons.append(f"missing_png:{source_name}")
            elif sha256_file(source_path) != frame_hashes.get(source_name):
                reasons.append(f"png_hash_mismatch:{source_name}")
            raw_row = index_by_stream["raw_actions"].get(key)
            if raw_row is None or not isinstance(raw_row.get("raw_action"), Mapping):
                reasons.append(f"missing_raw_action:{key}")
                continue
            try:
                normalized, tokens, is_noop = converter.convert(raw_row["raw_action"])
            except Exception as exc:
                reasons.append(f"official_action_conversion_failed:{key}:{exc}")
                continue
            if len(tokens) != 11:
                reasons.append(f"wrong_action_token_count:{key}")
                continue
            action_records.append(
                {
                    "trajectory_id": row["trajectory_id"],
                    "model_frame_idx": row["model_frame_idx"],
                    "action_idx": row["action_idx"],
                    "raw_action_sha256": hashlib.sha256(
                        canonical_json_bytes(raw_row["raw_action"])
                    ).hexdigest(),
                    "normalized_action_sha256": hashlib.sha256(
                        canonical_json_bytes(normalized)
                    ).hexdigest(),
                    "token_ids": list(tokens),
                    "token_sha256": hashlib.sha256(
                        canonical_json_bytes(list(tokens))
                    ).hexdigest(),
                    "is_noop": bool(is_noop),
                }
            )
        position_budget = (
            pair_count * PINNED_TOKENS_PER_PAIR
            + GENERATED_CERTIFICATION_FRAMES * PINNED_VISUAL_TOKENS
        )
        if position_budget > PINNED_MAX_POSITION_EMBEDDINGS:
            reasons.append("position_budget_exceeded")
        if len(action_records) != pair_count:
            reasons.append("action_conversion_cardinality_mismatch")
        if not reasons:
            return SelectedWindow(
                package_row_indices=tuple(range(start, start + pair_count)),
                frame_rows=tuple(copy.deepcopy(candidate)),
                action_records=tuple(action_records),
                rejected_candidates=tuple(rejections),
            )
        rejections.append(
            {
                "package_row_indices": [start, start + pair_count - 1],
                "reasons": sorted(set(reasons)),
            }
        )
    raise PreparationError(
        "no_valid_window",
        f"no deterministic eight-pair window passed; rejections={rejections}",
    )


def _copy_verified(source: Path, destination: Path) -> dict[str, Any]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    if sha256_file(source) != sha256_file(destination):
        raise PreparationError(
            "copy_hash_mismatch",
            f"copy of {source} did not preserve bytes",
        )
    return {
        "path": destination.as_posix(),
        "size_bytes": destination.stat().st_size,
        "sha256": sha256_file(destination),
    }


def _encode_bounded_mp4(
    selected_sources: Sequence[Path],
    selected_directory: Path,
    output: Path,
    *,
    ffmpeg_executable: str,
    ffprobe_executable: str,
) -> dict[str, Any]:
    if len(selected_sources) != EXPECTED_BOUNDED_PAIR_COUNT:
        raise PreparationError("invalid_frame_count", "exactly eight frames are required")
    selected_directory.mkdir(parents=True, exist_ok=False)
    source_records = []
    for bounded_index, source in enumerate(selected_sources):
        target = selected_directory / f"{bounded_index:06d}.png"
        shutil.copyfile(source, target)
        if sha256_file(source) != sha256_file(target):
            raise PreparationError("selected_frame_copy_mismatch", source.name)
        source_records.append(
            {
                "bounded_media_frame_idx": bounded_index,
                "source_path": str(source.resolve()),
                "source_filename": source.name,
                "selected_path": target.relative_to(output.parent).as_posix(),
                "png_size_bytes": target.stat().st_size,
                "png_sha256": sha256_file(target),
            }
        )
    pattern = selected_directory / "%06d.png"
    command = [
        ffmpeg_executable,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-framerate",
        "20",
        "-start_number",
        "0",
        "-i",
        str(pattern),
        "-frames:v",
        str(EXPECTED_BOUNDED_PAIR_COUNT),
        "-an",
        "-c:v",
        "libx264rgb",
        "-crf",
        "0",
        "-preset",
        "medium",
        "-pix_fmt",
        "rgb24",
        "-threads",
        "1",
        "-fflags",
        "+bitexact",
        "-flags:v",
        "+bitexact",
        "-metadata",
        "creation_time=1970-01-01T00:00:00Z",
        "-movflags",
        "+faststart",
        str(output),
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode or not output.is_file():
        raise PreparationError(
            "mp4_encoding_failed",
            (result.stderr or result.stdout or "ffmpeg failed").strip(),
        )
    probe = _run_ffprobe(output, ffprobe_executable)
    _require_exact_media_probe(
        probe,
        frame_count=EXPECTED_BOUNDED_PAIR_COUNT,
        role="bounded MP4",
        expected_duration=EXPECTED_BOUNDED_PAIR_COUNT / 20.0,
    )

    try:
        import cv2
    except Exception as exc:
        raise PreparationError("mp4_decoder_unavailable", str(exc)) from exc
    capture = cv2.VideoCapture(str(output))
    decoded_hashes: list[str] = []
    try:
        for record in source_records:
            ok, decoded = capture.read()
            if not ok or decoded is None:
                raise PreparationError(
                    "mp4_decode_failed",
                    f"failed at bounded frame {record['bounded_media_frame_idx']}",
                )
            source = cv2.imread(
                str(selected_directory / f"{record['bounded_media_frame_idx']:06d}.png"),
                cv2.IMREAD_COLOR,
            )
            if source is None or decoded.shape != source.shape:
                raise PreparationError("mp4_decode_shape_mismatch", str(decoded.shape))
            source_hash = hashlib.sha256(source.tobytes(order="C")).hexdigest()
            decoded_hash = hashlib.sha256(decoded.tobytes(order="C")).hexdigest()
            if decoded_hash != source_hash:
                raise PreparationError(
                    "mp4_frame_sequence_mismatch",
                    (
                        "lossless decoded frame does not equal selected PNG at "
                        f"index {record['bounded_media_frame_idx']}"
                    ),
                )
            record["decoded_bgr_sha256"] = decoded_hash
            decoded_hashes.append(decoded_hash)
        ok, extra = capture.read()
        if ok or extra is not None:
            raise PreparationError("mp4_extra_frame", "decoded more than eight frames")
    finally:
        capture.release()
    return {
        "path": output.as_posix(),
        "size_bytes": output.stat().st_size,
        "sha256": sha256_file(output),
        "probe": probe,
        "codec": probe.get("codec_name"),
        "pixel_format": probe.get("pixel_format"),
        "ffmpeg_executable": _resolved_executable(ffmpeg_executable),
        "ffmpeg_version": _tool_version(ffmpeg_executable),
        "ffmpeg_command": command,
        "ffprobe_executable": _resolved_executable(ffprobe_executable),
        "ffprobe_version": _tool_version(ffprobe_executable),
        "selected_frames": source_records,
        "decoded_frame_sequence_sha256": hashlib.sha256(
            canonical_json_bytes(decoded_hashes)
        ).hexdigest(),
    }


def _build_derivative_package(
    source: Mapping[str, Any],
    selection: SelectedWindow,
    media: Mapping[str, Any],
    impulse: Mapping[str, Any],
    *,
    person_a_revision: str,
    person_c_revision: str,
) -> dict[str, Any]:
    package = copy.deepcopy(dict(source))
    source_artifacts = copy.deepcopy(package["artifacts"])
    selected_keys = {
        (row["trajectory_id"], row["model_frame_idx"]): index
        for index, row in enumerate(selection.frame_rows)
    }
    selected_streams: dict[str, list[dict[str, Any]]] = {}
    for stream_name in ROW_STREAMS:
        rows = []
        for source_row_index, row in enumerate(package["streams"][stream_name]):
            scientific_key = (row["trajectory_id"], row["model_frame_idx"])
            if scientific_key not in selected_keys:
                continue
            bounded_index = selected_keys[scientific_key]
            transformed = copy.deepcopy(row)
            transformed["source_identity"] = {
                "source_package_row_idx": selection.package_row_indices[bounded_index],
                "source_render_frame_idx": row["render_frame_idx"],
            }
            transformed["render_frame_idx"] = bounded_index
            rows.append(transformed)
        rows.sort(key=lambda row: row["model_frame_idx"])
        selected_streams[stream_name] = rows
    package["streams"] = selected_streams
    package["scientific_use"] = "forbidden_engineering_certification_only"
    package["certification_purpose"] = (
        "non-scientific engineering-certification input"
    )
    package["media"] = {
        "mode": "mp4",
        "path": _MP4,
        "width": EXPECTED_WIDTH,
        "height": EXPECTED_HEIGHT,
        "fps": 20.0,
        "frame_count": EXPECTED_BOUNDED_PAIR_COUNT,
        "size_bytes": media["size_bytes"],
        "sha256": media["sha256"],
    }
    required_paths = {
        "config": "producer_evidence/reset_result.json",
        "diagnostics": "producer_evidence/c6a_qa_report.json",
    }
    artifacts: dict[str, dict[str, Any]] = {}
    for name in ROW_STREAMS:
        artifacts[name] = {
            "format": "jsonl",
            "path": f"{_PACKAGE}#streams/{name}",
            "sha256": hashlib.sha256(_jsonl_bytes(selected_streams[name])).hexdigest(),
        }
    for name, path in required_paths.items():
        original = source_artifacts[name]
        artifacts[name] = {
            "format": "json",
            "path": path,
            "sha256": original["sha256"],
        }
    artifacts["media"] = {
        "format": "mp4",
        "path": _MP4,
        "sha256": media["sha256"],
    }
    package["artifacts"] = artifacts
    manifest = package.get("episode_manifest")
    if isinstance(manifest, dict):
        manifest["duration"] = EXPECTED_BOUNDED_PAIR_COUNT / 20.0
        manifest["noise_schedule_hash"] = artifacts["seed_noise"]["sha256"]
    package["impulse_orientation"] = {
        "status": "verified",
        "fixture_id": impulse["trajectory_id"],
        "camera_component_0_observed_effect": (
            source["impulse_orientation"]["camera_component_0_observed_effect"]
        ),
        "camera_component_1_observed_effect": (
            source["impulse_orientation"]["camera_component_1_observed_effect"]
        ),
        "evidence_hash": impulse["qa_report"]["sha256"],
        "evidence_scope": "real_scripted_impulse_fixture",
        "evidence_file_sha256": impulse["evidence_file"]["sha256"],
        "causal_offset": impulse["causal_offset"],
        "causal_semantics": impulse["causal_semantics"],
    }
    package["derivative_provenance"] = {
        "preparation_version": PREPARATION_VERSION,
        "person_a_revision": person_a_revision,
        "person_c_revision": person_c_revision,
        "mineworld_source_revision": PINNED_SOURCE_REVISION,
        "modelscope_asset_revision": PINNED_ASSET_REVISION,
        "source_scientific_use": source.get("scientific_use"),
        "selection_rule": "earliest contiguous valid eight-pair window",
        "source_package_row_indices": list(selection.package_row_indices),
        "source_model_frame_indices": [
            row["model_frame_idx"] for row in selection.frame_rows
        ],
        "source_render_frame_indices": [
            row["render_frame_idx"] for row in selection.frame_rows
        ],
        "bounded_media_frame_indices": list(range(EXPECTED_BOUNDED_PAIR_COUNT)),
        "official_action_conversion": {
            "source_revision": PINNED_SOURCE_REVISION,
            "source_blob_sha256": MCDATASET_BLOB_SHA256,
            "converter_identity": ACTION_CONVERTER_IDENTITY,
            "vocabulary_offset": 8192,
            "records": [dict(record) for record in selection.action_records],
        },
        "source_artifacts": source_artifacts,
        "no_rows_shifted_interpolated_duplicated_or_repaired": True,
    }
    return package


def _write_bundle_checksums(bundle: Path) -> Path:
    inventory = bundle / _CHECKSUM_INVENTORY
    paths = sorted(
        (
            path
            for path in bundle.rglob("*")
            if path.is_file() and path != inventory
        ),
        key=lambda path: path.relative_to(bundle).as_posix(),
    )
    lines = [
        (
            f"{sha256_file(path)}  {path.relative_to(bundle).as_posix()}  "
            f"{path.stat().st_size}"
        )
        for path in paths
    ]
    inventory.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return inventory


def _validate_action_provenance(
    package: Mapping[str, Any],
    *,
    source_root: Path,
) -> None:
    provenance = package.get("derivative_provenance")
    action = (
        provenance.get("official_action_conversion")
        if isinstance(provenance, Mapping)
        else None
    )
    records = action.get("records") if isinstance(action, Mapping) else None
    if (
        not isinstance(action, Mapping)
        or action.get("source_revision") != PINNED_SOURCE_REVISION
        or action.get("source_blob_sha256") != MCDATASET_BLOB_SHA256
        or action.get("converter_identity") != ACTION_CONVERTER_IDENTITY
        or action.get("vocabulary_offset") != 8192
        or not isinstance(records, list)
        or len(records) != EXPECTED_BOUNDED_PAIR_COUNT
    ):
        raise PreparationError(
            "action_converter_provenance_mismatch",
            "official action-converter identity or record set is incomplete",
        )
    observed_revision, clean = _inspect_source(source_root)
    observed_blob = _git_blob_sha256(
        source_root,
        PINNED_SOURCE_REVISION,
        "mcdataset.py",
    )
    if (
        observed_revision != PINNED_SOURCE_REVISION
        or not clean
        or observed_blob != MCDATASET_BLOB_SHA256
    ):
        raise PreparationError(
            "action_converter_provenance_mismatch",
            "observed MineWorld converter source differs from the pinned identity",
        )
    raw_rows = {
        (row["trajectory_id"], row["model_frame_idx"]): row
        for row in package["streams"]["raw_actions"]
    }
    for record in records:
        if (
            not isinstance(record, Mapping)
            or record.get("trajectory_id") is None
            or type(record.get("model_frame_idx")) is not int
            or type(record.get("action_idx")) is not int
            or not isinstance(record.get("token_ids"), list)
            or len(record["token_ids"]) != 11
            or any(type(token) is not int for token in record["token_ids"])
            or _SHA256.fullmatch(str(record.get("token_sha256"))) is None
        ):
            raise PreparationError(
                "action_converter_provenance_mismatch",
                "one action conversion record is malformed",
            )
        key = (record["trajectory_id"], record["model_frame_idx"])
        raw_row = raw_rows.get(key)
        if (
            raw_row is None
            or raw_row.get("action_idx") != record["action_idx"]
            or hashlib.sha256(
                canonical_json_bytes(raw_row.get("raw_action"))
            ).hexdigest()
            != record.get("raw_action_sha256")
            or hashlib.sha256(
                canonical_json_bytes(record["token_ids"])
            ).hexdigest()
            != record["token_sha256"]
        ):
            raise PreparationError(
                "action_conversion_record_mismatch",
                f"stored conversion does not bind raw action {key}",
            )


def validate_preparation_bundle(
    preparation_directory: Path,
    *,
    mineworld_source_root: Path,
    ffprobe_executable: str = "ffprobe",
) -> dict[str, Any]:
    """Independently validate a completed external bundle without PyTorch."""

    preparation = preparation_directory.resolve()
    bundle = preparation / _BUNDLE_DIRECTORY
    if not bundle.is_dir():
        raise PreparationError("missing_bundle", f"bundle does not exist: {bundle}")
    checksums = _verify_checksum_inventory(
        bundle,
        bundle / _CHECKSUM_INVENTORY,
        excluded_names={_CHECKSUM_INVENTORY},
    )
    manifest = _strict_json(bundle / _MANIFEST, "preparation manifest")
    package = _strict_json(bundle / _PACKAGE, "bounded accepted package")
    media_path = bundle / _MP4
    if (
        manifest.get("schema_version") != SCHEMA_VERSION
        or manifest.get("preparation_version") != PREPARATION_VERSION
        or manifest.get("status") != "READY_FOR_AWS_INPUT_UPLOAD"
        or manifest.get("non_scientific_engineering_certification") is not True
    ):
        raise PreparationError(
            "preparation_manifest_invalid",
            "manifest status, version, or non-scientific classification changed",
        )
    validation = validate_trajectory_package(package)
    if not validation.accepted:
        first = validation.rejections[0]
        raise PreparationError(
            "bounded_package_rejected",
            f"{first.code.value}: {first.message}",
        )
    rows = package["streams"]["frame_map"]
    if len(rows) != EXPECTED_BOUNDED_PAIR_COUNT:
        raise PreparationError(
            "bounded_package_cardinality_mismatch",
            "bounded package must contain exactly eight pairs",
        )
    for name in ROW_STREAMS:
        if len(package["streams"][name]) != EXPECTED_BOUNDED_PAIR_COUNT:
            raise PreparationError(
                "bounded_package_cardinality_mismatch",
                f"{name} does not contain exactly eight rows",
            )
        observed = hashlib.sha256(
            _jsonl_bytes(package["streams"][name])
        ).hexdigest()
        if observed != package["artifacts"][name]["sha256"]:
            raise PreparationError(
                "bounded_stream_hash_mismatch",
                f"{name} does not match its derivative descriptor",
            )
    _require_declared_media_identity(
        package["media"],
        media_path,
        role="bounded MP4",
    )
    probe = _run_ffprobe(media_path, ffprobe_executable)
    _require_exact_media_probe(
        probe,
        frame_count=EXPECTED_BOUNDED_PAIR_COUNT,
        role="bounded MP4",
        expected_duration=EXPECTED_BOUNDED_PAIR_COUNT / 20.0,
    )
    selected = manifest.get("selection", {}).get("frames")
    if not isinstance(selected, list) or len(selected) != EXPECTED_BOUNDED_PAIR_COUNT:
        raise PreparationError(
            "selected_frame_provenance_mismatch",
            "manifest must identify exactly eight selected frames",
        )
    for index, record in enumerate(selected):
        selected_path = bundle / record["selected_path"]
        if (
            record.get("bounded_media_frame_idx") != index
            or record.get("png_sha256") != sha256_file(selected_path)
            or record.get("model_frame_idx") != rows[index]["model_frame_idx"]
            or record.get("source_render_frame_idx")
            != rows[index]["source_identity"]["source_render_frame_idx"]
        ):
            raise PreparationError(
                "selected_frame_provenance_mismatch",
                f"selected frame {index} does not bind its scientific identity",
            )
    orientation = package["impulse_orientation"]
    impulse_qa = bundle / "producer_evidence" / "impulse_qa_report.json"
    impulse_text = bundle / "producer_evidence" / "IMPULSE_EVIDENCE.txt"
    if (
        orientation.get("status") != "verified"
        or orientation.get("fixture_id") != "layout_00_ep9440"
        or orientation.get("causal_offset") != 0
        or orientation.get("evidence_hash") != sha256_file(impulse_qa)
        or orientation.get("evidence_file_sha256") != sha256_file(impulse_text)
    ):
        raise PreparationError(
            "impulse_evidence_mismatch",
            "bounded package is not bound to the verified real impulse fixture",
        )
    _validate_action_provenance(
        package,
        source_root=mineworld_source_root.resolve(),
    )
    final = max(rows, key=lambda row: row["model_frame_idx"])
    actions = package["streams"]["raw_actions"]
    if sum(
        row["trajectory_id"] == final["trajectory_id"]
        and row["model_frame_idx"] == final["model_frame_idx"]
        and row["action_idx"] == final["action_idx"]
        for row in actions
    ) != 1:
        raise PreparationError(
            "missing_final_action",
            "bounded package does not retain exactly one final-frame action",
        )
    expected_uploads = manifest.get("aws_upload_files")
    if not isinstance(expected_uploads, list) or any(
        not (bundle / path).is_file() for path in expected_uploads
    ):
        raise PreparationError(
            "aws_upload_manifest_invalid",
            "AWS upload list contains a missing file",
        )
    return {
        "status": "PASS",
        "preparation_directory": str(preparation),
        "bundle_directory": str(bundle),
        "checksum_entries": len(checksums),
        "package_sha256": sha256_file(bundle / _PACKAGE),
        "mp4_sha256": sha256_file(media_path),
        "pair_count": len(rows),
        "position_budget": (
            len(rows) * PINNED_TOKENS_PER_PAIR
            + GENERATED_CERTIFICATION_FRAMES * PINNED_VISUAL_TOKENS
        ),
        "torch_required": False,
        "cuda_required": False,
    }


def _refresh_checksums_after_mutation(bundle: Path) -> None:
    inventory = bundle / _CHECKSUM_INVENTORY
    if inventory.exists():
        inventory.unlink()
    _write_bundle_checksums(bundle)


def run_negative_bundle_checks(
    preparation_directory: Path,
    *,
    mineworld_source_root: Path,
    ffprobe_executable: str,
) -> dict[str, str]:
    """Run five semantic corruptions against temporary external copies."""

    source_bundle = preparation_directory.resolve() / _BUNDLE_DIRECTORY
    work = preparation_directory.resolve() / "work" / "negative_checks"
    work.mkdir(parents=True, exist_ok=True)
    results: dict[str, str] = {}

    def exercise(name: str, mutate: Callable[[Path], None], expected_codes: set[str]) -> None:
        case_root = work / name
        if case_root.exists():
            shutil.rmtree(case_root)
        shutil.copytree(source_bundle, case_root / _BUNDLE_DIRECTORY)
        bundle = case_root / _BUNDLE_DIRECTORY
        mutate(bundle)
        _refresh_checksums_after_mutation(bundle)
        try:
            validate_preparation_bundle(
                case_root,
                mineworld_source_root=mineworld_source_root,
                ffprobe_executable=ffprobe_executable,
            )
        except PreparationError as exc:
            if exc.code not in expected_codes:
                raise PreparationError(
                    "negative_check_wrong_failure",
                    f"{name}: expected {sorted(expected_codes)}, observed {exc.code}",
                ) from exc
            results[name] = exc.code
            return
        raise PreparationError("negative_check_failed_open", f"{name} was accepted")

    def alter_png(bundle: Path) -> None:
        path = bundle / "selected_frames" / "000000.png"
        path.write_bytes(path.read_bytes() + b"tamper")

    def alter_mp4(bundle: Path) -> None:
        path = bundle / _MP4
        path.write_bytes(path.read_bytes() + b"tamper")

    def remove_action(bundle: Path) -> None:
        path = bundle / _PACKAGE
        package = _strict_json(path, "negative package")
        package["streams"]["raw_actions"].pop()
        _write_json(path, package)

    def unverify_impulse(bundle: Path) -> None:
        path = bundle / _PACKAGE
        package = _strict_json(path, "negative package")
        package["impulse_orientation"]["status"] = "unverified"
        _write_json(path, package)

    def mutate_raw_action(bundle: Path) -> None:
        path = bundle / _PACKAGE
        package = _strict_json(path, "negative package")
        package["streams"]["raw_actions"][0]["raw_action"]["mouse"]["dx"] = 1.0
        package["artifacts"]["raw_actions"]["sha256"] = hashlib.sha256(
            _jsonl_bytes(package["streams"]["raw_actions"])
        ).hexdigest()
        _write_json(path, package)

    exercise(
        "altered_selected_png",
        alter_png,
        {"selected_frame_provenance_mismatch"},
    )
    exercise(
        "altered_bounded_mp4",
        alter_mp4,
        {"bounded_media_hash_mismatch"},
    )
    exercise(
        "frame_action_cardinality_mismatch",
        remove_action,
        {"bounded_package_rejected"},
    )
    exercise(
        "unverified_impulse_evidence",
        unverify_impulse,
        {"bounded_package_rejected", "impulse_evidence_mismatch"},
    )
    exercise(
        "raw_action_mutation",
        mutate_raw_action,
        {"action_conversion_record_mismatch"},
    )
    shutil.rmtree(work, ignore_errors=True)
    return results


def _assert_external_output(
    output_root: Path,
    *,
    person_c_root: Path,
) -> Path:
    resolved = output_root.resolve()
    for repository in (_REPO_ROOT.resolve(), person_c_root.resolve()):
        if resolved == repository or resolved.is_relative_to(repository):
            raise PreparationError(
                "output_inside_git_repository",
                f"output root must be outside Git: {resolved}",
            )
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def prepare_certification_inputs(
    args: argparse.Namespace,
    *,
    converter_factory: Callable[[Path], Any] = _OfficialActionConverter,
) -> Path:
    """Execute one production preparation into a new external directory."""

    episode = args.episode_bundle.resolve()
    impulse_fixture = args.impulse_fixture.resolve()
    person_c_identity = _require_exact_repo(
        episode,
        expected_revision=args.person_c_revision,
        role="Person C",
    )
    mineworld_identity = _require_exact_repo(
        args.mineworld_source_root.resolve(),
        expected_revision=PINNED_SOURCE_REVISION,
        role="MineWorld source",
    )
    person_a_head = _git(_REPO_ROOT, "rev-parse", "HEAD")
    if person_a_head != args.person_a_revision:
        raise PreparationError(
            "revision_mismatch",
            f"Person A expected {args.person_a_revision}, observed {person_a_head}",
        )
    output_root = _assert_external_output(
        args.output_root,
        person_c_root=person_c_identity["root"],
    )
    if args.preparation_id:
        if _OUTPUT_DIRECTORY.fullmatch(args.preparation_id) is None:
            raise PreparationError("invalid_preparation_id", args.preparation_id)
        preparation_id = args.preparation_id
    else:
        preparation_id = f"person-a-phase3-input-{uuid.uuid4().hex}"
    preparation = output_root / preparation_id
    preparation.mkdir(exist_ok=False)
    work = preparation / "work"
    bundle = preparation / _BUNDLE_DIRECTORY
    work.mkdir()
    bundle.mkdir()
    try:
        original = _verify_original_package(episode)
        original_media_probe = _run_ffprobe(
            episode / "scene.mp4",
            args.ffprobe,
        )
        _require_exact_media_probe(
            original_media_probe,
            frame_count=EXPECTED_C6A_FRAME_COUNT,
            role="original C6A MP4",
            expected_duration=EXPECTED_C6A_FRAME_COUNT / 20.0,
        )
        c6a_archive = verify_and_extract_frame_archive(
            args.c6a_frame_archive,
            args.c6a_frame_checksums,
            work / "c6a_frames",
            expected_archive_sha256=EXPECTED_C6A_ARCHIVE_SHA256,
            expected_count=EXPECTED_C6A_FRAME_COUNT,
        )
        impulse_archive = verify_and_extract_frame_archive(
            args.impulse_frame_archive,
            args.impulse_frame_checksums,
            work / "impulse_frames",
            expected_archive_sha256=EXPECTED_IMPULSE_ARCHIVE_SHA256,
            expected_count=EXPECTED_IMPULSE_FRAME_COUNT,
        )
        frame_map = original["package"]["streams"]["frame_map"]
        for row in frame_map:
            name = f"{row['render_frame_idx']:06d}.png"
            if name not in c6a_archive.frame_paths:
                raise PreparationError(
                    "package_frame_mapping_missing",
                    f"accepted identity {_capture_key(row)} has no PNG",
                )
        impulse = _validate_impulse_fixture(
            impulse_fixture,
            impulse_archive,
            ffprobe_executable=args.ffprobe,
        )
        converter = converter_factory(mineworld_identity["root"])
        try:
            action_fixture_parity = _certify_action_fixture(
                mineworld_identity["root"]
            )
        except Exception as exc:
            raise PreparationError(
                "action_fixture_parity_failed",
                str(exc),
            ) from exc
        action_fixture_parity = dict(action_fixture_parity)
        action_fixture_parity["classification"] = (
            "committed_cpu_fixture_rechecked_during_local_preparation"
        )
        selection = select_earliest_window(
            original["package"],
            c6a_archive.frame_paths,
            c6a_archive.frame_hashes,
            pair_count=args.pair_count,
            converter=converter,
        )
        selected_sources = [
            c6a_archive.frame_paths[f"{row['render_frame_idx']:06d}.png"]
            for row in selection.frame_rows
        ]
        media = _encode_bounded_mp4(
            selected_sources,
            bundle / "selected_frames",
            bundle / _MP4,
            ffmpeg_executable=args.ffmpeg,
            ffprobe_executable=args.ffprobe,
        )
        producer_evidence = bundle / "producer_evidence"
        _copy_verified(
            episode / "reset_result.json",
            producer_evidence / "reset_result.json",
        )
        _copy_verified(
            episode / "qa_report.json",
            producer_evidence / "c6a_qa_report.json",
        )
        _copy_verified(
            impulse_fixture / "qa_report.json",
            producer_evidence / "impulse_qa_report.json",
        )
        _copy_verified(
            impulse_fixture / "IMPULSE_EVIDENCE.txt",
            producer_evidence / "IMPULSE_EVIDENCE.txt",
        )
        package = _build_derivative_package(
            original["package"],
            selection,
            media,
            impulse,
            person_a_revision=args.person_a_revision,
            person_c_revision=args.person_c_revision,
        )
        package_path = bundle / _PACKAGE
        _write_json(package_path, package)
        package_validation = validate_trajectory_package(package)
        if not package_validation.accepted:
            first = package_validation.rejections[0]
            raise PreparationError(
                "bounded_package_rejected",
                f"{first.code.value}: {first.message}",
            )

        selection_frames = []
        for row, source_record in zip(selection.frame_rows, media["selected_frames"]):
            selection_frames.append(
                {
                    **source_record,
                    "package_row_idx": selection.package_row_indices[
                        source_record["bounded_media_frame_idx"]
                    ],
                    "trajectory_id": row["trajectory_id"],
                    "model_frame_idx": row["model_frame_idx"],
                    "source_render_frame_idx": row["render_frame_idx"],
                    "action_idx": row["action_idx"],
                    "server_tick": row["server_tick"],
                    "client_tick": next(
                        item["client_tick"]
                        for item in original["package"]["streams"]["client_tick_log"]
                        if (
                            item["trajectory_id"] == row["trajectory_id"]
                            and item["model_frame_idx"] == row["model_frame_idx"]
                        )
                    ),
                }
            )
        upload_files = sorted(
            [
                _PACKAGE,
                _MP4,
                "producer_evidence/IMPULSE_EVIDENCE.txt",
                "producer_evidence/c6a_qa_report.json",
                "producer_evidence/impulse_qa_report.json",
                "producer_evidence/reset_result.json",
                *[
                    f"selected_frames/{index:06d}.png"
                    for index in range(EXPECTED_BOUNDED_PAIR_COUNT)
                ],
                _MANIFEST,
                _CHECKSUM_INVENTORY,
            ]
        )
        manifest: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "preparation_version": PREPARATION_VERSION,
            "status": "READY_FOR_AWS_INPUT_UPLOAD",
            "preparation_id": preparation_id,
            "non_scientific_engineering_certification": True,
            "person_a": {
                "commit_sha": args.person_a_revision,
                "preparation_worktree_clean": False,
                "reason": "project-owned preparation tool is under review and uncommitted",
            },
            "person_c": {
                "commit_sha": person_c_identity["head"],
                "worktree_clean": person_c_identity["clean"],
                "source_root": str(person_c_identity["root"]),
            },
            "mineworld": {
                "source_revision": mineworld_identity["head"],
                "source_clean": mineworld_identity["clean"],
            },
            "modelscope_asset_revision": PINNED_ASSET_REVISION,
            "original_c6a": {
                "package": {
                    "path": str(original["package_path"]),
                    "size_bytes": original["package_size_bytes"],
                    "sha256": original["package_sha256"],
                },
                "episode_checksums": {
                    "path": str((episode / _CHECKSUM_INVENTORY).resolve()),
                    "size_bytes": (episode / _CHECKSUM_INVENTORY).stat().st_size,
                    "sha256": original["checksums_sha256"],
                    "status": "PASS",
                },
                "archive": {
                    "path": str(c6a_archive.archive),
                    "size_bytes": c6a_archive.archive.stat().st_size,
                    "sha256": c6a_archive.archive_sha256,
                    "expected_frame_count": EXPECTED_C6A_FRAME_COUNT,
                    "verified_frame_count": len(c6a_archive.frame_paths),
                    "ignored_appledouble_members": list(
                        c6a_archive.ignored_appledouble_members
                    ),
                },
                "frame_checksum_inventory": {
                    "path": str(c6a_archive.inventory),
                    "size_bytes": c6a_archive.inventory.stat().st_size,
                    "sha256": c6a_archive.inventory_sha256,
                },
                "validation": "PASS",
                "media_probe": original_media_probe,
            },
            "impulse_fixture": {
                **impulse,
                "archive": {
                    "path": str(impulse_archive.archive),
                    "size_bytes": impulse_archive.archive.stat().st_size,
                    "sha256": impulse_archive.archive_sha256,
                    "expected_frame_count": EXPECTED_IMPULSE_FRAME_COUNT,
                    "verified_frame_count": len(impulse_archive.frame_paths),
                    "ignored_appledouble_members": list(
                        impulse_archive.ignored_appledouble_members
                    ),
                },
                "frame_checksum_inventory": {
                    "path": str(impulse_archive.inventory),
                    "size_bytes": impulse_archive.inventory.stat().st_size,
                    "sha256": impulse_archive.inventory_sha256,
                },
            },
            "action_converter": {
                "status": "PASS",
                "source_revision": PINNED_SOURCE_REVISION,
                "source_file": "mcdataset.py",
                "source_blob_sha256": MCDATASET_BLOB_SHA256,
                "converter_identity": ACTION_CONVERTER_IDENTITY,
                "vocabulary_offset": 8192,
                "selected_records": [dict(record) for record in selection.action_records],
                "golden_fixture_parity": action_fixture_parity,
            },
            "selection": {
                "rule": "earliest contiguous valid eight-pair window",
                "pair_count": EXPECTED_BOUNDED_PAIR_COUNT,
                "generated_certification_frames": GENERATED_CERTIFICATION_FRAMES,
                "position_budget": (
                    EXPECTED_BOUNDED_PAIR_COUNT * PINNED_TOKENS_PER_PAIR
                    + PINNED_VISUAL_TOKENS
                ),
                "maximum_positions": PINNED_MAX_POSITION_EMBEDDINGS,
                "package_row_indices": list(selection.package_row_indices),
                "frames": selection_frames,
                "rejected_earlier_candidates": list(selection.rejected_candidates),
            },
            "bounded_mp4": media,
            "bounded_package": {
                "path": _PACKAGE,
                "size_bytes": package_path.stat().st_size,
                "sha256": sha256_file(package_path),
                "frozen_trajectory_validation": "PASS",
            },
            "validation_commands": {
                "prepare": list(args.command_line),
                "validate": [
                    "python",
                    "scripts/prepare_phase3_certification_inputs.py",
                    "validate",
                    "--preparation-directory",
                    str(preparation),
                    "--mineworld-source-root",
                    str(args.mineworld_source_root),
                ],
            },
            "validation_results": {
                "original_package": "PASS",
                "episode_checksums": "PASS",
                "c6a_archive_and_frames": "PASS",
                "impulse_fixture": "PASS",
                "official_action_conversion": "PASS",
                "bounded_mp4": "PASS",
                "bounded_package": "PASS",
                "independent_output_validation": "PENDING",
                "negative_checks": "PENDING",
            },
            "aws_upload_files": upload_files,
            "checksum_inventory_self_hashed": False,
        }
        _write_json(bundle / _MANIFEST, manifest)
        _write_bundle_checksums(bundle)
        validate_preparation_bundle(
            preparation,
            mineworld_source_root=args.mineworld_source_root,
            ffprobe_executable=args.ffprobe,
        )
        negative = run_negative_bundle_checks(
            preparation,
            mineworld_source_root=args.mineworld_source_root,
            ffprobe_executable=args.ffprobe,
        )
        manifest["validation_results"]["independent_output_validation"] = "PASS"
        manifest["validation_results"]["negative_checks"] = {
            "status": "PASS",
            "cases": negative,
        }
        _write_json(bundle / _MANIFEST, manifest)
        _write_bundle_checksums(bundle)
        validate_preparation_bundle(
            preparation,
            mineworld_source_root=args.mineworld_source_root,
            ffprobe_executable=args.ffprobe,
        )
        return preparation
    except Exception:
        # Preserve a failed external attempt for audit instead of relabeling it.
        failure = preparation / "PREPARATION_FAILED.txt"
        if not failure.exists():
            failure.write_text(
                "This preparation attempt failed and is not an AWS input bundle.\n",
                encoding="utf-8",
            )
        raise


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prepare or validate bounded Phase 3 certification inputs."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare")
    prepare.add_argument("--episode-bundle", required=True, type=Path)
    prepare.add_argument("--c6a-frame-archive", required=True, type=Path)
    prepare.add_argument("--c6a-frame-checksums", required=True, type=Path)
    prepare.add_argument("--impulse-fixture", required=True, type=Path)
    prepare.add_argument("--impulse-frame-archive", required=True, type=Path)
    prepare.add_argument("--impulse-frame-checksums", required=True, type=Path)
    prepare.add_argument("--mineworld-source-root", required=True, type=Path)
    prepare.add_argument("--output-root", required=True, type=Path)
    prepare.add_argument("--pair-count", required=True, type=int)
    prepare.add_argument("--person-a-revision", required=True)
    prepare.add_argument("--person-c-revision", required=True)
    prepare.add_argument("--preparation-id")
    prepare.add_argument("--ffmpeg", default="ffmpeg")
    prepare.add_argument("--ffprobe", default="ffprobe")
    validate = commands.add_parser("validate")
    validate.add_argument("--preparation-directory", required=True, type=Path)
    validate.add_argument("--mineworld-source-root", required=True, type=Path)
    validate.add_argument("--ffprobe", default="ffprobe")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(argv) if argv is not None else None
    args = build_parser().parse_args(arguments)
    try:
        if args.command == "prepare":
            args.command_line = (
                ["python", "scripts/prepare_phase3_certification_inputs.py", *arguments]
                if arguments is not None
                else list(os.sys.argv)
            )
            result: object = prepare_certification_inputs(args)
        else:
            result = validate_preparation_bundle(
                args.preparation_directory,
                mineworld_source_root=args.mineworld_source_root,
                ffprobe_executable=args.ffprobe,
            )
    except (PreparationError, OSError, ValueError) as exc:
        print(str(exc), file=os.sys.stderr)
        return 1
    if isinstance(result, Path):
        print(result)
    else:
        print(json.dumps(result, indent=2, sort_keys=True))
    return 0


__all__ = [
    "EXPECTED_C6A_ARCHIVE_SHA256",
    "EXPECTED_IMPULSE_ARCHIVE_SHA256",
    "PREPARATION_VERSION",
    "PreparationError",
    "build_parser",
    "main",
    "parse_checksum_inventory",
    "prepare_certification_inputs",
    "run_negative_bundle_checks",
    "select_earliest_window",
    "validate_preparation_bundle",
    "verify_and_extract_frame_archive",
]
