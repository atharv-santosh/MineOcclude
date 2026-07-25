"""Bounded Person A Phase 3 real-runtime certification harness.

The command is prepared locally in Wave 4 but must only be executed in the
qualified CUDA environment. Large outputs remain under the caller-provided
external evidence root.
"""

from __future__ import annotations

import argparse
import contextlib
import dataclasses
import hashlib
import importlib
import json
import math
import subprocess
import sys
import time
from collections.abc import Iterator, Mapping, Sequence
from fractions import Fraction
from pathlib import Path
from typing import Any

from mineocclude.contracts.identity import SCHEMA_VERSION
from mineocclude.contracts.trajectory import validate_trajectory_package
from mineocclude.models._mineworld_adapter_wave2 import (
    ACTION_CONVERTER_IDENTITY,
    MCDATASET_BLOB_SHA256,
    PINNED_ASSET_REVISION,
    PINNED_ACTION_TOKENS,
    PINNED_DEVICE,
    PINNED_MAIN_CHECKPOINT_SHA256,
    PINNED_MAX_POSITION_EMBEDDINGS,
    PINNED_MODEL_CONFIG_SHA256,
    PINNED_PRECISION,
    PINNED_SOURCE_REVISION,
    PINNED_TOKENS_PER_PAIR,
    PINNED_VAE_CHECKPOINT_SHA256,
    PINNED_VAE_CONFIG_SHA256,
    PINNED_VISUAL_TOKENS,
    _OfficialActionConverter,
)
from mineocclude.models._mineworld_adapter_wave4 import (
    CODE_IDENTITY_VERSION,
    _CODE_FILES,
    _adapter_code_identity,
    _rollout_generation_config_sha256,
)
from mineocclude.models.mineworld_adapter import (
    MINEWORLD_ADAPTER_API_VERSION,
    AcceptedTrajectoryInput,
    ActionConversionRequest,
    FramePreprocessRequest,
    FreeRolloutRequest,
    MineWorldAdapterError,
    RuntimeLoadRequest,
    TeacherForcedRequest,
    TrajectoryTokenizationRequest,
    create_mineworld_adapter,
)
from mineocclude.models.phase2_evidence import (
    EvidenceValidationError,
    canonical_json_bytes,
    parse_ffprobe_output,
    sha256_file,
)


CERTIFICATION_VERSION = "person-a-phase3-certification-v1.0"
_REPO_ROOT = Path(__file__).resolve().parents[3]
_SESSION = __import__("re").compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_SHA256 = __import__("re").compile(r"^[0-9a-f]{64}$")
_CODE_SHA = __import__("re").compile(r"^[0-9a-f]{40}$")
_ACTION_FIXTURE = (
    _REPO_ROOT
    / "tests"
    / "fixtures"
    / "models"
    / "phase3_wave2_action_matrix.json"
)
_ASSET_LOCK = _REPO_ROOT / "configs" / "assets" / "mineworld_assets_v1.json"
_PINNED_ASSET_FILES = {
    "checkpoints/700M_16f.ckpt": PINNED_MAIN_CHECKPOINT_SHA256,
    "checkpoints/vae/config.json": PINNED_VAE_CONFIG_SHA256,
    "checkpoints/vae/vae.ckpt": PINNED_VAE_CHECKPOINT_SHA256,
}
_ENVIRONMENT_SECTIONS = (
    "=== SYSTEM ===",
    "=== PACKAGE VERSIONS ===",
    "=== IMPORT CHECKS ===",
    "=== PYTORCH / CUDA ===",
    "=== FINAL RESULT ===",
)
_ENVIRONMENT_PASS = "PASS: Official CUDA-capable environment validated."
_EXPECTED_CHECKS = {
    "runtime_load": "PASS",
    "real_frame_preprocessing": "PASS",
    "real_vae_336_tokens": "PASS",
    "official_action_fixture_parity": "PASS",
    "accepted_action_conversion": "PASS",
    "frame_token_map": "PASS",
    "teacher_forced": "PASS",
    "twenty_external_hooks": "PASS",
    "repeatability": "PASS",
    "free_rollout": "PASS",
    "output_identity": "PASS",
    "local_failure_matrix": "PASS_BY_COMMITTED_TESTS",
}


def _add_preflight_arguments(command: argparse.ArgumentParser) -> None:
    command.add_argument("--mineworld-source-root", required=True, type=Path)
    command.add_argument("--asset-root", required=True, type=Path)
    command.add_argument("--evidence-root", required=True, type=Path)
    command.add_argument(
        "--accepted-trajectory-package",
        required=True,
        type=Path,
    )
    command.add_argument("--input-mp4", required=True, type=Path)
    command.add_argument("--environment-report", required=True, type=Path)
    command.add_argument("--session-id", required=True)
    command.add_argument("--seed", required=True, type=int)
    command.add_argument("--precision", required=True)
    command.add_argument("--device", required=True)
    command.add_argument("--generated-frame-count", required=True, type=int)
    command.add_argument("--output-frame-rate", default=6.0, type=float)
    command.add_argument("--top-k", default=1, type=int)
    command.add_argument("--mineocclude-revision", required=True)
    command.add_argument("--ffprobe", default="ffprobe")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run or validate one immutable Person A Phase 3 adapter "
            "GPU-certification bundle."
        )
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    preflight = subparsers.add_parser(
        "preflight",
        help=(
            "validate real package, media, environment, and pinned identities "
            "without importing PyTorch or creating evidence"
        ),
    )
    _add_preflight_arguments(preflight)
    run = subparsers.add_parser("run", help="execute the real CUDA certification")
    _add_preflight_arguments(run)
    run.add_argument("--dry-run", action="store_true")
    run.add_argument("--confirm-gpu-certification", action="store_true")
    validate = subparsers.add_parser(
        "validate",
        help="validate a completed certification summary without GPU work",
    )
    validate.add_argument("--summary", required=True, type=Path)
    validate.add_argument(
        "--verify-files",
        action="store_true",
        help="also require and hash the generated rollout video and external inputs",
    )
    return parser


def _git(*arguments: str, root: Path = _REPO_ROOT) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *arguments],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        raise EvidenceValidationError(
            "git_inspection_failed",
            (result.stderr or result.stdout or "git failed").strip(),
        )
    return result.stdout.strip()


def _require_file(path: Path, role: str) -> Path:
    resolved = path.resolve()
    if not resolved.is_file():
        raise EvidenceValidationError(
            "missing_input",
            f"{role} does not exist: {resolved}",
        )
    return resolved


def _verify_file(path: Path, expected: str, role: str) -> Path:
    resolved = _require_file(path, role)
    observed = sha256_file(resolved)
    if observed != expected.lower():
        raise EvidenceValidationError(
            "input_hash_mismatch",
            f"{role}: expected {expected.lower()}, observed {observed}",
        )
    return resolved


def _require_directory(path: Path, role: str) -> Path:
    resolved = path.resolve()
    if not resolved.is_dir():
        raise EvidenceValidationError(
            "missing_input",
            f"{role} is not an existing directory: {resolved}",
        )
    return resolved


def _strict_json_mapping(path: Path, role: str) -> dict[str, Any]:
    resolved = _require_file(path, role)

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
        payload = resolved.read_text(encoding="utf-8")
        document = json.loads(
            payload,
            parse_constant=reject_constant,
            object_pairs_hook=unique_object,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise EvidenceValidationError(
            "invalid_json_input",
            f"{role} is not strict finite JSON: {exc}",
        ) from exc
    if not isinstance(document, dict):
        raise EvidenceValidationError(
            "invalid_json_input",
            f"{role} must contain one JSON object",
        )
    return document


def _validate_environment_report(path: Path) -> dict[str, object]:
    resolved = _require_file(path, "environment report")
    try:
        content = resolved.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise EvidenceValidationError(
            "environment_report_invalid",
            f"environment report is not readable UTF-8 text: {exc}",
        ) from exc
    if not content.strip():
        raise EvidenceValidationError(
            "environment_report_invalid",
            "environment report is empty",
        )
    lowered = content.lower()
    placeholders = (
        "<placeholder>",
        "<environment",
        "replace_me",
        "example only",
        "dry_run_only",
        "todo:",
    )
    missing_sections = [
        section for section in _ENVIRONMENT_SECTIONS if section not in content
    ]
    if (
        missing_sections
        or _ENVIRONMENT_PASS not in content
        or any(marker in lowered for marker in placeholders)
    ):
        detail = (
            "missing sections: " + ", ".join(missing_sections)
            if missing_sections
            else "required CUDA PASS marker is absent or placeholder text exists"
        )
        raise EvidenceValidationError(
            "environment_report_invalid",
            detail,
        )
    return {
        "path": resolved,
        "size_bytes": resolved.stat().st_size,
        "sha256": sha256_file(resolved),
        "status": "PASS",
    }


def _probe_input_mp4(path: Path, executable: str) -> dict[str, Any]:
    try:
        result = subprocess.run(
            [
                executable,
                "-v",
                "error",
                "-count_frames",
                "-select_streams",
                "v:0",
                "-show_entries",
                (
                    "stream=width,height,r_frame_rate,avg_frame_rate,"
                    "duration,nb_frames,nb_read_frames"
                ),
                "-show_entries",
                "format=duration",
                "-of",
                "json",
                str(path),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as exc:
        raise EvidenceValidationError(
            "ffprobe_missing",
            f"ffprobe executable not found: {executable}",
        ) from exc
    if result.returncode:
        raise EvidenceValidationError(
            "input_media_probe_failed",
            (result.stderr or result.stdout or "ffprobe failed").strip(),
        )
    return parse_ffprobe_output(result.stdout)


def _validate_asset_lock(asset_root: Path) -> dict[str, Path]:
    document = _strict_json_mapping(_ASSET_LOCK, "MineWorld asset lock")
    source = document.get("source")
    files = document.get("files")
    if (
        document.get("schema_version") != SCHEMA_VERSION
        or not isinstance(source, Mapping)
        or source.get("provider") != "ModelScope"
        or source.get("repository") != "AI-ModelScope/mineworld"
        or source.get("revision") != PINNED_ASSET_REVISION
        or not isinstance(files, Mapping)
    ):
        raise EvidenceValidationError(
            "asset_revision_mismatch",
            "project asset lock does not identify the pinned ModelScope revision",
        )
    verified: dict[str, Path] = {}
    for relative_path, expected_sha256 in _PINNED_ASSET_FILES.items():
        record = files.get(relative_path)
        recorded_sha256 = (
            record.get("sha256") if isinstance(record, Mapping) else None
        )
        if (
            not isinstance(record, Mapping)
            or not isinstance(recorded_sha256, str)
            or recorded_sha256.lower() != expected_sha256
            or type(record.get("size_bytes")) is not int
            or record["size_bytes"] <= 0
        ):
            raise EvidenceValidationError(
                "asset_revision_mismatch",
                f"asset-lock record is invalid for {relative_path}",
            )
        path = _verify_file(
            asset_root / Path(relative_path),
            expected_sha256,
            relative_path,
        )
        if path.stat().st_size != record["size_bytes"]:
            raise EvidenceValidationError(
                "input_size_mismatch",
                (
                    f"{relative_path}: expected {record['size_bytes']} bytes, "
                    f"observed {path.stat().st_size}"
                ),
            )
        verified[relative_path] = path
    return verified


def _validate_package_and_media(
    package_path: Path,
    input_mp4: Path,
    *,
    generated_frame_count: int,
    ffprobe_executable: str,
) -> dict[str, Any]:
    package = _strict_json_mapping(
        package_path,
        "accepted trajectory package",
    )
    validation = validate_trajectory_package(package)
    if not validation.accepted:
        first = validation.rejections[0]
        raise EvidenceValidationError(
            "trajectory_package_rejected",
            (
                f"{first.code.value}: {first.message} "
                f"({len(validation.rejections)} rejection(s))"
            ),
        )
    if package.get("schema_version") != SCHEMA_VERSION:
        raise EvidenceValidationError(
            "invalid_schema_version",
            f"accepted package must use schema version {SCHEMA_VERSION}",
        )
    acceptance_hashes = {
        f"artifacts.{name}.sha256": record.get("sha256")
        for name, record in package["artifacts"].items()
    }
    acceptance_hashes["impulse_orientation.evidence_hash"] = package[
        "impulse_orientation"
    ].get("evidence_hash")
    placeholders = [
        path
        for path, value in acceptance_hashes.items()
        if not isinstance(value, str)
        or _SHA256.fullmatch(value) is None
        or len(set(value)) == 1
    ]
    if placeholders:
        raise EvidenceValidationError(
            "acceptance_evidence_placeholder",
            (
                "accepted package contains missing or placeholder producer "
                "evidence hashes: " + ", ".join(sorted(placeholders))
            ),
        )
    frame_rows = package["streams"]["frame_map"]
    context_pairs = len(frame_rows)
    if context_pairs > 15:
        raise EvidenceValidationError(
            "certification_context_too_long",
            (
                "One-frame rollout certification permits at most 15 complete "
                "accepted context pairs"
            ),
        )
    if generated_frame_count != 1:
        raise EvidenceValidationError(
            "invalid_generated_frame_count",
            "bounded Phase 3 certification requires exactly one generated frame",
        )
    position_budget = (
        context_pairs * PINNED_TOKENS_PER_PAIR
        + generated_frame_count * PINNED_VISUAL_TOKENS
    )
    if position_budget > PINNED_MAX_POSITION_EMBEDDINGS:
        raise EvidenceValidationError(
            "position_budget_exceeded",
            (
                f"required {position_budget} positions but the pinned model "
                f"supports {PINNED_MAX_POSITION_EMBEDDINGS}"
            ),
        )

    final_frame = max(
        frame_rows,
        key=lambda row: row["model_frame_idx"],
    )
    final_actions = [
        row
        for row in package["streams"]["raw_actions"]
        if (
            row["trajectory_id"] == final_frame["trajectory_id"]
            and row["model_frame_idx"] == final_frame["model_frame_idx"]
            and row["action_idx"] == final_frame["action_idx"]
        )
    ]
    if len(final_actions) != 1 or not isinstance(
        final_actions[0].get("raw_action"),
        Mapping,
    ):
        raise EvidenceValidationError(
            "missing_final_action",
            "the final accepted model frame must retain exactly one raw action",
        )

    media = package["media"]
    declared_size = media.get("size_bytes")
    if type(declared_size) is not int or declared_size <= 0:
        raise EvidenceValidationError(
            "accepted_media_size_missing",
            "accepted package media.size_bytes must be a positive integer",
        )
    resolved_mp4 = _require_file(input_mp4, "accepted trajectory MP4")
    observed_size = resolved_mp4.stat().st_size
    if observed_size != declared_size:
        raise EvidenceValidationError(
            "accepted_media_size_mismatch",
            (
                f"package declares {declared_size} bytes, "
                f"observed {observed_size}"
            ),
        )
    observed_sha256 = sha256_file(resolved_mp4)
    if observed_sha256 != media["sha256"]:
        raise EvidenceValidationError(
            "accepted_media_hash_mismatch",
            (
                f"package declares {media['sha256']}, "
                f"observed {observed_sha256}"
            ),
        )
    probe = _probe_input_mp4(resolved_mp4, ffprobe_executable)
    expected_frame_count = media["frame_count"]
    if (
        media["mode"] != "mp4"
        or media["width"] != 640
        or media["height"] != 360
        or float(media["fps"]) != 20.0
        or probe["width"] != 640
        or probe["height"] != 360
        or Fraction(probe["r_frame_rate"]) != Fraction(20, 1)
        or Fraction(probe["avg_frame_rate"]) != Fraction(20, 1)
        or probe["declared_frames"] != expected_frame_count
        or probe["decoded_frames"] != expected_frame_count
        or context_pairs != expected_frame_count
    ):
        raise EvidenceValidationError(
            "accepted_media_metadata_mismatch",
            (
                "accepted MP4 must exactly match declared 640x360, 20 fps, "
                "frame-count, decoded-count, and package cardinality"
            ),
        )
    return {
        "package": package,
        "accepted_manifest_sha256": sha256_file(package_path),
        "input_mp4": resolved_mp4,
        "input_mp4_sha256": observed_sha256,
        "input_mp4_size_bytes": observed_size,
        "media_probe": probe,
        "context_pairs": context_pairs,
        "generated_frame_count": generated_frame_count,
        "position_budget": position_budget,
        "final_model_frame_idx": final_frame["model_frame_idx"],
    }


def _certify_action_fixture(source_root: Path) -> dict[str, object]:
    """Re-run the committed action matrix through the pinned converter."""

    fixture_path = _require_file(_ACTION_FIXTURE, "action parity fixture")
    try:
        document = json.loads(fixture_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise EvidenceValidationError(
            "action_fixture_invalid",
            f"action parity fixture could not be read: {exc}",
        ) from exc
    expected_header = {
        "schema_version": SCHEMA_VERSION,
        "fixture_version": "person-a-phase3-action-matrix-v1.0",
        "source_revision": PINNED_SOURCE_REVISION,
        "source_file": "mcdataset.py",
        "source_blob_sha256": MCDATASET_BLOB_SHA256,
        "converter_identity": ACTION_CONVERTER_IDENTITY,
        "vocabulary_offset": 8192,
    }
    if (
        not isinstance(document, Mapping)
        or any(document.get(key) != value for key, value in expected_header.items())
        or not isinstance(document.get("cases"), list)
        or not document["cases"]
    ):
        raise EvidenceValidationError(
            "action_fixture_invalid",
            "action parity fixture header or case matrix is incomplete",
        )
    try:
        converter = _OfficialActionConverter(source_root)
        for index, case in enumerate(document["cases"]):
            if not isinstance(case, Mapping) or not isinstance(
                case.get("raw_action"), Mapping
            ):
                raise ValueError(f"case {index} is malformed")
            normalized, token_ids, is_noop = converter.convert(
                case["raw_action"]
            )
            if (
                dict(normalized) != case.get("normalized_action")
                or list(token_ids) != case.get("token_ids")
                or is_noop is not case.get("is_noop")
            ):
                raise ValueError(
                    f"case {case.get('case_id', index)!r} differs from "
                    "the pinned converter"
                )
    except Exception as exc:
        raise EvidenceValidationError(
            "action_fixture_parity_failed",
            str(exc),
        ) from exc
    return {
        "classification": "committed_cpu_fixture_rechecked_on_gpu_host",
        "status": "PASS",
        "path": str(fixture_path),
        "sha256": sha256_file(fixture_path),
        "case_count": len(document["cases"]),
        "source_revision": PINNED_SOURCE_REVISION,
        "source_blob_sha256": MCDATASET_BLOB_SHA256,
        "converter_identity": ACTION_CONVERTER_IDENTITY,
    }


def preflight_certification_inputs(args: argparse.Namespace) -> dict[str, Any]:
    """Validate every CPU-visible certification input without side effects."""

    if _SESSION.fullmatch(args.session_id) is None or ".." in args.session_id:
        raise EvidenceValidationError(
            "invalid_session_id",
            "session ID must be a path-free stable identifier",
        )
    if args.seed < 0 or args.seed > 0xFFFFFFFF:
        raise EvidenceValidationError(
            "invalid_seed",
            "seed must be in the deterministic NumPy/PyTorch uint32 range",
        )
    if args.precision != PINNED_PRECISION or args.device != PINNED_DEVICE:
        raise EvidenceValidationError(
            "runtime_identity_mismatch",
            "precision/device must equal float16/cuda:0",
        )
    if args.top_k <= 0 or args.top_k > 8192:
        raise EvidenceValidationError(
            "invalid_sampling",
            "top-k must be an integer from 1 through 8192",
        )
    if not math.isfinite(args.output_frame_rate) or args.output_frame_rate <= 0:
        raise EvidenceValidationError(
            "invalid_output_frame_rate",
            "output frame rate must be a finite positive value",
        )
    if (
        _CODE_SHA.fullmatch(args.mineocclude_revision) is None
        or len(set(args.mineocclude_revision)) == 1
    ):
        raise EvidenceValidationError(
            "mineocclude_revision_mismatch",
            "MineOcclude revision must be a full non-placeholder commit SHA",
        )
    evidence_root = args.evidence_root.resolve()
    if evidence_root.is_relative_to(_REPO_ROOT):
        raise EvidenceValidationError(
            "evidence_inside_repository",
            "GPU evidence root must remain outside Git",
        )
    if evidence_root.exists() and not evidence_root.is_dir():
        raise EvidenceValidationError(
            "invalid_evidence_root",
            "evidence root exists but is not a directory",
        )
    if not evidence_root.exists() and not evidence_root.parent.is_dir():
        raise EvidenceValidationError(
            "invalid_evidence_root",
            "evidence-root parent must already exist",
        )
    session_root = evidence_root / args.session_id
    if session_root.exists():
        raise EvidenceValidationError(
            "session_collision",
            "immutable session directory already exists",
        )
    source_root = _require_directory(
        args.mineworld_source_root,
        "MineWorld source root",
    )
    asset_root = _require_directory(args.asset_root, "ModelScope asset root")
    package_path = _require_file(
        args.accepted_trajectory_package,
        "accepted trajectory package",
    )
    input_mp4 = _require_file(args.input_mp4, "accepted trajectory MP4")
    environment_report = _require_file(
        args.environment_report,
        "environment report",
    )
    code_revision = _git("rev-parse", "HEAD")
    if args.mineocclude_revision != code_revision:
        raise EvidenceValidationError(
            "mineocclude_revision_mismatch",
            f"expected {args.mineocclude_revision}, observed {code_revision}",
        )
    if _git("status", "--porcelain"):
        raise EvidenceValidationError(
            "mineocclude_dirty",
            "certification requires a clean MineOcclude checkout",
        )
    source_revision = _git("rev-parse", "HEAD", root=source_root)
    if source_revision != PINNED_SOURCE_REVISION:
        raise EvidenceValidationError(
            "source_revision_mismatch",
            f"expected {PINNED_SOURCE_REVISION}, observed {source_revision}",
        )
    if _git("status", "--porcelain", root=source_root):
        raise EvidenceValidationError(
            "source_dirty",
            "pinned MineWorld checkout is dirty",
        )
    package_evidence = _validate_package_and_media(
        package_path,
        input_mp4,
        generated_frame_count=args.generated_frame_count,
        ffprobe_executable=args.ffprobe,
    )
    environment_evidence = _validate_environment_report(environment_report)
    model_config = _verify_file(
        source_root / "configs" / "700M_16f.yaml",
        PINNED_MODEL_CONFIG_SHA256,
        "model configuration",
    )
    asset_paths = _validate_asset_lock(asset_root)
    paths = {
        "model_config": model_config,
        "main_checkpoint": asset_paths["checkpoints/700M_16f.ckpt"],
        "vae_config": asset_paths["checkpoints/vae/config.json"],
        "vae_checkpoint": asset_paths["checkpoints/vae/vae.ckpt"],
    }
    return {
        "status": "preflight_passed",
        "schema_version": SCHEMA_VERSION,
        "certification_version": CERTIFICATION_VERSION,
        "session_root": session_root,
        "source_root": source_root,
        "asset_root": asset_root,
        "package_path": package_path,
        "input_mp4": input_mp4,
        "environment_report": environment_report,
        "source_revision": source_revision,
        "asset_revision": PINNED_ASSET_REVISION,
        "mineocclude_revision": code_revision,
        "package": package_evidence["package"],
        "accepted_manifest_sha256": package_evidence[
            "accepted_manifest_sha256"
        ],
        "input_mp4_sha256": package_evidence["input_mp4_sha256"],
        "input_mp4_size_bytes": package_evidence["input_mp4_size_bytes"],
        "media_probe": package_evidence["media_probe"],
        "context_pairs": package_evidence["context_pairs"],
        "generated_frame_count": package_evidence["generated_frame_count"],
        "position_budget": package_evidence["position_budget"],
        "final_model_frame_idx": package_evidence["final_model_frame_idx"],
        "environment_report_sha256": environment_evidence["sha256"],
        "environment_report_size_bytes": environment_evidence["size_bytes"],
        **paths,
    }


def _preflight_report(prepared: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": prepared["schema_version"],
        "certification_version": prepared["certification_version"],
        "status": prepared["status"],
        "mineocclude_revision": prepared["mineocclude_revision"],
        "source_revision": prepared["source_revision"],
        "asset_revision": prepared["asset_revision"],
        "session_root": str(prepared["session_root"]),
        "session_directory_created": False,
        "torch_imported": False,
        "cuda_queried": False,
        "runtime_loaded": False,
        "accepted_trajectory_package": {
            "path": str(prepared["package_path"]),
            "sha256": prepared["accepted_manifest_sha256"],
            "trajectory_id": prepared["package"]["trajectory_id"],
            "schema_version": prepared["package"]["schema_version"],
        },
        "accepted_media": {
            "path": str(prepared["input_mp4"]),
            "size_bytes": prepared["input_mp4_size_bytes"],
            "sha256": prepared["input_mp4_sha256"],
            "probe": prepared["media_probe"],
        },
        "environment_report": {
            "path": str(prepared["environment_report"]),
            "size_bytes": prepared["environment_report_size_bytes"],
            "sha256": prepared["environment_report_sha256"],
        },
        "context": {
            "complete_pairs": prepared["context_pairs"],
            "generated_frames": prepared["generated_frame_count"],
            "visual_tokens_per_generated_frame": PINNED_VISUAL_TOKENS,
            "action_tokens_per_pair": PINNED_ACTION_TOKENS,
            "tokens_per_pair": PINNED_TOKENS_PER_PAIR,
            "position_budget": prepared["position_budget"],
            "max_position_embeddings": PINNED_MAX_POSITION_EMBEDDINGS,
            "final_model_frame_idx": prepared["final_model_frame_idx"],
        },
    }


@contextlib.contextmanager
def _hook_capture() -> Iterator[
    tuple[list[dict[str, object]], Any]
]:
    records: list[dict[str, object]] = []

    @contextlib.contextmanager
    def attach(modules: tuple[tuple[str, object], ...]):
        handles = []
        try:
            for layer_index, (name, module) in enumerate(modules):
                def record(
                    _module: object,
                    _inputs: object,
                    output: object,
                    *,
                    name: str = name,
                    layer_index: int = layer_index,
                ) -> None:
                    tensor = (
                        output[0]
                        if isinstance(output, tuple) and output
                        else output
                    )
                    records.append(
                        {
                            "module_name": name,
                            "layer_index": layer_index,
                            "shape": [
                                int(value)
                                for value in getattr(tensor, "shape", ())
                            ],
                            "dtype": str(getattr(tensor, "dtype", "")),
                            "device": str(getattr(tensor, "device", "")),
                        }
                    )

                handles.append(module.register_forward_hook(record))
            yield
        finally:
            for handle in reversed(handles):
                handle.remove()

    yield records, attach


def _decode_frames(
    input_mp4: Path,
    frame_indices: Sequence[int],
) -> tuple[object, ...]:
    cv2 = importlib.import_module("cv2")
    capture = cv2.VideoCapture(str(input_mp4))
    if not capture.isOpened():
        capture.release()
        raise EvidenceValidationError(
            "input_decode_failed",
            "accepted MP4 could not be opened",
        )
    frames = []
    try:
        for index in frame_indices:
            capture.set(cv2.CAP_PROP_POS_FRAMES, index)
            ok, frame = capture.read()
            if not ok:
                raise EvidenceValidationError(
                    "input_decode_failed",
                    f"could not decode accepted frame {index}",
                )
            frames.append(frame)
    finally:
        capture.release()
    return tuple(frames)


def _write_json(path: Path, document: Mapping[str, Any]) -> str:
    path.write_bytes(canonical_json_bytes(document))
    return sha256_file(path)


def execute_preflight(args: argparse.Namespace) -> dict[str, Any]:
    """Run the shared CPU-only preflight and return bounded evidence."""

    return _preflight_report(preflight_certification_inputs(args))


def execute_certification(args: argparse.Namespace) -> Path:
    prepared = preflight_certification_inputs(args)
    if args.dry_run:
        print(
            json.dumps(
                _preflight_report(prepared),
                indent=2,
                sort_keys=True,
            )
        )
        return prepared["session_root"]
    if not args.confirm_gpu_certification:
        raise EvidenceValidationError(
            "gpu_execution_not_confirmed",
            "--confirm-gpu-certification is required",
        )
    torch = importlib.import_module("torch")
    if not torch.cuda.is_available():
        raise EvidenceValidationError(
            "cuda_required",
            "real CUDA is required for certification",
        )
    torch.cuda.init()
    torch.cuda.set_device(0)
    if torch.cuda.current_device() != 0:
        raise EvidenceValidationError(
            "cuda_device_mismatch",
            "certification requires selected CUDA device 0",
        )
    session_root: Path = prepared["session_root"]
    session_root.mkdir(parents=True)
    raw_log = session_root / "raw_stdout_stderr.log"
    with raw_log.open("w", encoding="utf-8", newline="\n") as log:
        with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
            started = time.perf_counter()
            code_identity = _adapter_code_identity()
            adapter = create_mineworld_adapter()
            package = prepared["package"]
            accepted_manifest_sha256 = prepared[
                "accepted_manifest_sha256"
            ]
            input_mp4_sha256 = prepared["input_mp4_sha256"]
            environment_report_sha256 = prepared[
                "environment_report_sha256"
            ]
            validated = adapter.validate_trajectory(
                AcceptedTrajectoryInput(
                    schema_version=SCHEMA_VERSION,
                    trajectory_id=package["trajectory_id"],
                    accepted_manifest_sha256=accepted_manifest_sha256,
                    document=package,
                )
            )
            if len(validated.frame_identities) != prepared["context_pairs"]:
                raise EvidenceValidationError(
                    "preflight_runtime_identity_mismatch",
                    (
                        "runtime adapter validation changed the accepted "
                        "preflight frame count"
                    ),
                )
            declared_media_sha256 = package["media"]["sha256"]
            action_fixture_started = time.perf_counter()
            action_fixture = _certify_action_fixture(prepared["source_root"])
            action_fixture_seconds = (
                time.perf_counter() - action_fixture_started
            )
            load_request = RuntimeLoadRequest(
                schema_version=SCHEMA_VERSION,
                runtime_id=f"{args.session_id}:runtime",
                mineocclude_revision=prepared["mineocclude_revision"],
                mineworld_source_revision=PINNED_SOURCE_REVISION,
                modelscope_asset_revision=PINNED_ASSET_REVISION,
                mineworld_source_root=prepared["source_root"],
                model_config_path=prepared["model_config"],
                main_checkpoint_path=prepared["main_checkpoint"],
                vae_config_path=prepared["vae_config"],
                vae_checkpoint_path=prepared["vae_checkpoint"],
                model_config_sha256=PINNED_MODEL_CONFIG_SHA256,
                main_checkpoint_sha256=PINNED_MAIN_CHECKPOINT_SHA256,
                vae_config_sha256=PINNED_VAE_CONFIG_SHA256,
                vae_checkpoint_sha256=PINNED_VAE_CHECKPOINT_SHA256,
                environment_report_sha256=environment_report_sha256,
                precision=args.precision,
                device=args.device,
                expected_adapter_code_sha256=code_identity.sha256,
            )
            load_started = time.perf_counter()
            runtime_identity = adapter.load_runtime(load_request)
            load_seconds = time.perf_counter() - load_started

            frame_rows = sorted(
                package["streams"]["frame_map"],
                key=lambda row: row["model_frame_idx"],
            )
            decoded = _decode_frames(
                prepared["input_mp4"],
                [row["render_frame_idx"] for row in frame_rows],
            )
            raw_by_index = {
                row["model_frame_idx"]: row
                for row in package["streams"]["raw_actions"]
            }
            preprocess_started = time.perf_counter()
            frames = [
                adapter.preprocess_frame(
                    FramePreprocessRequest(
                        identity=identity,
                        source_frame_idx=frame_row["render_frame_idx"],
                        frame=frame,
                    )
                )
                for identity, frame, frame_row in zip(
                    validated.frame_identities,
                    decoded,
                    frame_rows,
                    strict=True,
                )
            ]
            preprocessing_seconds = time.perf_counter() - preprocess_started
            action_started = time.perf_counter()
            actions = []
            for identity, frame_row in zip(
                validated.frame_identities,
                frame_rows,
                strict=True,
            ):
                action_row = raw_by_index[identity.model_frame_idx]
                actions.append(
                    adapter.convert_action(
                        ActionConversionRequest(
                            identity=identity,
                            action_idx=frame_row["action_idx"],
                            raw_action=action_row["raw_action"],
                        )
                    )
                )
            action_conversion_seconds = time.perf_counter() - action_started
            tokenization_started = time.perf_counter()
            tokenized = adapter.tokenize_trajectory(
                TrajectoryTokenizationRequest(
                    runtime_identity=runtime_identity,
                    trajectory=validated,
                    frames=tuple(frames),
                    actions=tuple(actions),
                )
            )
            tokenization_seconds = time.perf_counter() - tokenization_started
            torch.cuda.reset_peak_memory_stats(0)
            teacher_results = []
            hook_runs = []
            for _repeat in range(2):
                with _hook_capture() as (records, attach):
                    teacher_results.append(
                        adapter.teacher_forced(
                            TeacherForcedRequest(
                                runtime_identity=runtime_identity,
                                trajectory=tokenized,
                                seed=args.seed,
                                precision=args.precision,
                                batch_size=1,
                                hook_context_factory=attach,
                                expected_adapter_code_sha256=(
                                    code_identity.sha256
                                ),
                                accepted_manifest_sha256=(
                                    accepted_manifest_sha256
                                ),
                            )
                        )
                    )
                    hook_runs.append(tuple(records))
            if (
                teacher_results[0].output_sha256
                != teacher_results[1].output_sha256
                or any(len(records) != 20 for records in hook_runs)
                or any(
                    record["shape"]
                    != [1, len(tokenized.token_ids), runtime_identity.hidden_size]
                    or record["dtype"] != "torch.float16"
                    or record["device"] != runtime_identity.device
                    for records in hook_runs
                    for record in records
                )
                or any(
                    [record["module_name"] for record in records]
                    != [
                        f"{runtime_identity.decoder_layer_path}.{index}"
                        for index in range(runtime_identity.layer_count)
                    ]
                    for records in hook_runs
                )
            ):
                raise EvidenceValidationError(
                    "teacher_certification_failed",
                    "repeat identity or 20-layer hook coverage failed",
                )
            teacher_report = {
                "schema_version": SCHEMA_VERSION,
                "certification_version": CERTIFICATION_VERSION,
                "status": "completed",
                "operation": "teacher_forced",
                "runtime_identity": dataclasses.asdict(runtime_identity),
                "runtime_id": runtime_identity.runtime_id,
                "adapter_code_sha256": runtime_identity.adapter_code_sha256,
                "trajectory_id": tokenized.trajectory_id,
                "accepted_manifest_sha256": accepted_manifest_sha256,
                "token_sha256": tokenized.token_sha256,
                "frame_token_map_sha256": (
                    tokenized.frame_token_map_sha256
                ),
                "repeat_count": 2,
                "precision": args.precision,
                "device": args.device,
                "batch_size": 1,
                "input_sequence_length": len(tokenized.token_ids),
                "included_frame_identities": [
                    dataclasses.asdict(identity)
                    for identity in tokenized.included_frame_identities
                ],
                "excluded_frame_identities": [
                    dataclasses.asdict(identity)
                    for identity in tokenized.excluded_frame_identities
                ],
                "repeat_output_sha256": [
                    result.output_sha256 for result in teacher_results
                ],
                "repeatability_status": "PASS",
                "inference_mode_applied": True,
                "forward_seconds": [
                    result.elapsed_seconds for result in teacher_results
                ],
                "total_forward_seconds": sum(
                    result.elapsed_seconds for result in teacher_results
                ),
                "hook_records": [list(records) for records in hook_runs],
                "peak_cuda_allocated_bytes": int(
                    torch.cuda.max_memory_allocated(0)
                ),
                "peak_cuda_reserved_bytes": int(
                    torch.cuda.max_memory_reserved(0)
                ),
            }
            teacher_path = session_root / "teacher_forced_certification.json"
            teacher_sha256 = _write_json(teacher_path, teacher_report)

            rollout_dir = session_root / "rollout"
            provisional = FreeRolloutRequest(
                runtime_identity=runtime_identity,
                context=tokenized,
                run_id=f"{args.session_id}-rollout",
                seed=args.seed,
                generated_frame_count=args.generated_frame_count,
                output_directory=rollout_dir,
                generation_config_sha256="0" * 64,
                generation_actions=(actions[-1],),
                temperature=1.0,
                top_k=args.top_k,
                top_p=None,
                output_frame_rate=args.output_frame_rate,
                precision=args.precision,
                device=args.device,
                expected_adapter_code_sha256=code_identity.sha256,
                accepted_manifest_sha256=accepted_manifest_sha256,
                protected_input_paths=(
                    prepared["input_mp4"],
                    prepared["package_path"],
                    prepared["model_config"],
                    prepared["main_checkpoint"],
                    prepared["vae_config"],
                    prepared["vae_checkpoint"],
                ),
            )
            rollout_request = dataclasses.replace(
                provisional,
                generation_config_sha256=(
                    _rollout_generation_config_sha256(provisional)
                ),
            )
            rollout = adapter.free_rollout(rollout_request)
            runtime_path = session_root / "adapter_runtime_identity.json"
            runtime_sha256 = _write_json(
                runtime_path,
                {
                    "schema_version": SCHEMA_VERSION,
                    "certification_version": CERTIFICATION_VERSION,
                    "status": "completed",
                    "identity": dataclasses.asdict(runtime_identity),
                    "model_load_seconds": load_seconds,
                },
            )
            summary = {
                "schema_version": SCHEMA_VERSION,
                "certification_version": CERTIFICATION_VERSION,
                "status": "real_runtime_certified",
                "session_id": args.session_id,
                "mineocclude_revision": prepared["mineocclude_revision"],
                "runtime_id": runtime_identity.runtime_id,
                "adapter_code_sha256": runtime_identity.adapter_code_sha256,
                "source_revision": PINNED_SOURCE_REVISION,
                "asset_revision": PINNED_ASSET_REVISION,
                "checks": {
                    "runtime_load": "PASS",
                    "real_frame_preprocessing": "PASS",
                    "real_vae_336_tokens": (
                        "PASS"
                        if all(
                            len(span.visual_positions) == 336
                            for span in tokenized.frame_token_map.spans
                        )
                        else "FAIL"
                    ),
                    "official_action_fixture_parity": action_fixture["status"],
                    "accepted_action_conversion": (
                        "PASS"
                        if all(
                            len(action.token_ids) == 11
                            and action.converter_identity
                            == runtime_identity.action_conversion_identity
                            for action in actions
                        )
                        else "FAIL"
                    ),
                    "frame_token_map": "PASS",
                    "teacher_forced": "PASS",
                    "twenty_external_hooks": "PASS",
                    "repeatability": "PASS",
                    "free_rollout": "PASS",
                    "output_identity": "PASS",
                    "local_failure_matrix": "PASS_BY_COMMITTED_TESTS",
                },
                "inputs": {
                    "accepted_trajectory_package": {
                        "path": str(prepared["package_path"]),
                        "sha256": accepted_manifest_sha256,
                    },
                    "accepted_media": {
                        "path": str(prepared["input_mp4"]),
                        "sha256": input_mp4_sha256,
                        "declared_sha256": declared_media_sha256,
                    },
                    "environment_report": {
                        "path": str(prepared["environment_report"]),
                        "sha256": environment_report_sha256,
                    },
                    "action_fixture": action_fixture,
                },
                "reports": {
                    "runtime": {
                        "path": runtime_path.relative_to(session_root).as_posix(),
                        "sha256": runtime_sha256,
                    },
                    "teacher_forced": {
                        "path": teacher_path.relative_to(session_root).as_posix(),
                        "sha256": teacher_sha256,
                    },
                    "rollout": {
                        "path": rollout.metadata_path.relative_to(
                            session_root
                        ).as_posix(),
                        "sha256": rollout.metadata_sha256,
                    },
                    "rollout_video": {
                        "path": rollout.video_path.relative_to(
                            session_root
                        ).as_posix(),
                        "sha256": rollout.video_sha256,
                    },
                    "raw_log": {
                        "path": raw_log.relative_to(session_root).as_posix()
                    },
                },
                "timings": {
                    "action_fixture_seconds": action_fixture_seconds,
                    "model_load_seconds": load_seconds,
                    "frame_preprocessing_seconds": preprocessing_seconds,
                    "accepted_action_conversion_seconds": (
                        action_conversion_seconds
                    ),
                    "vae_tokenization_seconds": tokenization_seconds,
                    "teacher_forward_seconds": [
                        result.elapsed_seconds for result in teacher_results
                    ],
                    "free_rollout_seconds": rollout.elapsed_seconds,
                    "total_seconds": time.perf_counter() - started,
                },
                "large_outputs_outside_git": True,
                "command": list(sys.argv),
                "environment": {
                    "python_version": sys.version,
                    "torch_version": str(torch.__version__),
                    "cuda_version": str(torch.version.cuda),
                    "device_name": str(torch.cuda.get_device_name(0)),
                    "environment_report_sha256": (
                        load_request.environment_report_sha256
                    ),
                },
            }
            summary_path = session_root / "certification_summary.json"
            _write_json(summary_path, summary)
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["reports"]["raw_log"]["sha256"] = sha256_file(raw_log)
    _write_json(summary_path, summary)
    validate_certification_summary(summary_path, verify_files=True)
    return summary_path


def validate_certification_summary(
    path: Path,
    *,
    verify_files: bool,
) -> None:
    summary_path = _require_file(path, "certification summary")
    session_root = summary_path.parent.resolve()
    document = json.loads(summary_path.read_text(encoding="utf-8"))
    if (
        not isinstance(document, Mapping)
        or document.get("schema_version") != SCHEMA_VERSION
        or document.get("certification_version") != CERTIFICATION_VERSION
        or document.get("status") != "real_runtime_certified"
        or not isinstance(document.get("session_id"), str)
        or _SESSION.fullmatch(document["session_id"]) is None
        or _CODE_SHA.fullmatch(str(document.get("mineocclude_revision"))) is None
        or _SHA256.fullmatch(str(document.get("adapter_code_sha256"))) is None
        or document.get("source_revision") != PINNED_SOURCE_REVISION
        or document.get("asset_revision") != PINNED_ASSET_REVISION
        or document.get("checks") != _EXPECTED_CHECKS
    ):
        raise EvidenceValidationError(
            "certification_summary_invalid",
            "summary identity, status, version, or exact check set is incomplete",
        )

    inputs = document.get("inputs")
    if not isinstance(inputs, Mapping) or set(inputs) != {
        "accepted_trajectory_package",
        "accepted_media",
        "environment_report",
        "action_fixture",
    }:
        raise EvidenceValidationError(
            "certification_inputs_invalid",
            "summary must contain the exact bounded input identity set",
        )
    for role in (
        "accepted_trajectory_package",
        "accepted_media",
        "environment_report",
        "action_fixture",
    ):
        record = inputs[role]
        if (
            not isinstance(record, Mapping)
            or not isinstance(record.get("path"), str)
            or _SHA256.fullmatch(str(record.get("sha256"))) is None
        ):
            raise EvidenceValidationError(
                "certification_input_invalid",
                f"{role} identity is malformed",
            )
        if verify_files:
            input_path = _require_file(Path(record["path"]), role)
            if sha256_file(input_path) != record["sha256"]:
                raise EvidenceValidationError(
                    "certification_input_hash_mismatch",
                    f"{role} hash mismatch",
                )
    if (
        inputs["accepted_media"].get("declared_sha256")
        != inputs["accepted_media"].get("sha256")
    ):
        raise EvidenceValidationError(
            "certification_input_invalid",
            "accepted media bytes do not match the accepted package declaration",
        )
    action_fixture = inputs["action_fixture"]
    if (
        action_fixture.get("status") != "PASS"
        or action_fixture.get("source_revision") != PINNED_SOURCE_REVISION
        or action_fixture.get("source_blob_sha256") != MCDATASET_BLOB_SHA256
        or action_fixture.get("converter_identity") != ACTION_CONVERTER_IDENTITY
        or type(action_fixture.get("case_count")) is not int
        or action_fixture["case_count"] <= 0
    ):
        raise EvidenceValidationError(
            "certification_action_fixture_invalid",
            "official action fixture parity evidence is incomplete",
        )

    reports = document.get("reports")
    required_reports = {
        "runtime",
        "teacher_forced",
        "rollout",
        "rollout_video",
        "raw_log",
    }
    if not isinstance(reports, Mapping) or set(reports) != required_reports:
        raise EvidenceValidationError(
            "certification_reports_incomplete",
            "summary report set is incomplete or ambiguous",
        )
    report_paths: dict[str, Path] = {}
    for role, record in reports.items():
        if (
            not isinstance(record, Mapping)
            or not isinstance(record.get("path"), str)
            or _SHA256.fullmatch(str(record.get("sha256"))) is None
        ):
            raise EvidenceValidationError(
                "certification_report_invalid",
                f"{role} report identity is malformed",
            )
        stored_path = Path(record["path"])
        report_path = (
            stored_path.resolve()
            if stored_path.is_absolute()
            else (session_root / stored_path).resolve()
        )
        if not report_path.is_relative_to(session_root):
            raise EvidenceValidationError(
                "certification_report_invalid",
                f"{role} is outside the immutable certification session",
            )
        if role == "rollout_video" and not verify_files:
            report_paths[role] = report_path
            continue
        report_path = _require_file(report_path, role)
        if sha256_file(report_path) != record["sha256"]:
            raise EvidenceValidationError(
                "certification_report_hash_mismatch",
                f"{role} report hash mismatch",
            )
        report_paths[role] = report_path

    runtime = json.loads(report_paths["runtime"].read_text(encoding="utf-8"))
    teacher = json.loads(
        report_paths["teacher_forced"].read_text(encoding="utf-8")
    )
    rollout = json.loads(report_paths["rollout"].read_text(encoding="utf-8"))
    runtime_identity = runtime.get("identity")
    expected_runtime = {
        "schema_version": SCHEMA_VERSION,
        "adapter_api_version": MINEWORLD_ADAPTER_API_VERSION,
        "runtime_id": document["runtime_id"],
        "mineocclude_revision": document["mineocclude_revision"],
        "mineworld_source_revision": PINNED_SOURCE_REVISION,
        "modelscope_asset_revision": PINNED_ASSET_REVISION,
        "model_config_sha256": PINNED_MODEL_CONFIG_SHA256,
        "main_checkpoint_sha256": PINNED_MAIN_CHECKPOINT_SHA256,
        "vae_config_sha256": PINNED_VAE_CONFIG_SHA256,
        "vae_checkpoint_sha256": PINNED_VAE_CHECKPOINT_SHA256,
        "environment_report_sha256": inputs["environment_report"]["sha256"],
        "model_class": "LlamaLVM",
        "transformer_class": "LlamaForCausalLM",
        "vae_class": "VAE",
        "decoder_layer_path": "transformer.model.layers",
        "layer_count": 20,
        "hidden_size": 2048,
        "max_position_embeddings": 5552,
        "visual_tokens_per_frame": 336,
        "action_tokens_per_frame": 11,
        "tokens_per_pair": 347,
        "max_context_pairs": 16,
        "precision": PINNED_PRECISION,
        "device": PINNED_DEVICE,
        "adapter_code_sha256": document["adapter_code_sha256"],
    }
    if (
        runtime.get("schema_version") != SCHEMA_VERSION
        or runtime.get("certification_version") != CERTIFICATION_VERSION
        or runtime.get("status") != "completed"
        or not isinstance(runtime_identity, Mapping)
        or any(
            runtime_identity.get(field) != expected
            for field, expected in expected_runtime.items()
        )
        or not _finite_nonnegative(runtime.get("model_load_seconds"))
    ):
        raise EvidenceValidationError(
            "certification_runtime_invalid",
            "runtime report does not match the exact pinned certified identity",
        )
    inventory = runtime_identity.get("adapter_code_inventory")
    if (
        not isinstance(inventory, list)
        or len(inventory) != len(_CODE_FILES)
        or any(
            not isinstance(row, list)
            or len(row) != 3
            or not isinstance(row[0], str)
            or _SHA256.fullmatch(str(row[1])) is None
            or type(row[2]) is not int
            or row[2] <= 0
            for row in inventory
        )
        or [row[0] for row in inventory] != sorted(_CODE_FILES)
    ):
        raise EvidenceValidationError(
            "certification_code_inventory_invalid",
            "adapter code inventory is incomplete or nondeterministic",
        )
    inventory_sha256 = hashlib.sha256(
        canonical_json_bytes(
            {
                "identity_version": CODE_IDENTITY_VERSION,
                "files": [
                    {"path": row[0], "sha256": row[1], "size_bytes": row[2]}
                    for row in inventory
                ],
            }
        )
    ).hexdigest()
    if inventory_sha256 != document["adapter_code_sha256"]:
        raise EvidenceValidationError(
            "certification_code_inventory_invalid",
            "adapter code inventory does not produce the certified identity",
        )

    sequence_length = teacher.get("input_sequence_length")
    hook_runs = teacher.get("hook_records")
    repeat_hashes = teacher.get("repeat_output_sha256")
    forward_seconds = teacher.get("forward_seconds")
    expected_names = [
        f"transformer.model.layers.{index}" for index in range(20)
    ]
    if (
        teacher.get("schema_version") != SCHEMA_VERSION
        or teacher.get("certification_version") != CERTIFICATION_VERSION
        or teacher.get("status") != "completed"
        or teacher.get("operation") != "teacher_forced"
        or teacher.get("runtime_identity") != runtime_identity
        or teacher.get("runtime_id") != document["runtime_id"]
        or teacher.get("adapter_code_sha256")
        != document["adapter_code_sha256"]
        or teacher.get("accepted_manifest_sha256")
        != inputs["accepted_trajectory_package"]["sha256"]
        or _SHA256.fullmatch(str(teacher.get("token_sha256"))) is None
        or _SHA256.fullmatch(str(teacher.get("frame_token_map_sha256"))) is None
        or teacher.get("repeat_count") != 2
        or teacher.get("repeatability_status") != "PASS"
        or teacher.get("inference_mode_applied") is not True
        or teacher.get("precision") != PINNED_PRECISION
        or teacher.get("device") != PINNED_DEVICE
        or teacher.get("batch_size") != 1
        or type(sequence_length) is not int
        or sequence_length <= 0
        or sequence_length > 5552
        or sequence_length % 347
        or not isinstance(repeat_hashes, list)
        or len(repeat_hashes) != 2
        or repeat_hashes[0] != repeat_hashes[1]
        or any(_SHA256.fullmatch(str(value)) is None for value in repeat_hashes)
        or not isinstance(forward_seconds, list)
        or len(forward_seconds) != 2
        or any(not _finite_nonnegative(value) for value in forward_seconds)
        or not math.isclose(
            float(teacher.get("total_forward_seconds", -1)),
            sum(float(value) for value in forward_seconds),
            rel_tol=1e-9,
            abs_tol=1e-9,
        )
        or not _nonnegative_integer(teacher.get("peak_cuda_allocated_bytes"))
        or not _nonnegative_integer(teacher.get("peak_cuda_reserved_bytes"))
        or not isinstance(hook_runs, list)
        or len(hook_runs) != 2
    ):
        raise EvidenceValidationError(
            "certification_teacher_invalid",
            "teacher report identity, repeats, timing, or memory is incomplete",
        )
    for hook_run in hook_runs:
        if (
            not isinstance(hook_run, list)
            or len(hook_run) != 20
            or [record.get("module_name") for record in hook_run]
            != expected_names
            or [record.get("layer_index") for record in hook_run]
            != list(range(20))
            or any(
                record.get("shape") != [1, sequence_length, 2048]
                or record.get("dtype") != "torch.float16"
                or record.get("device") != PINNED_DEVICE
                for record in hook_run
                if isinstance(record, Mapping)
            )
            or any(not isinstance(record, Mapping) for record in hook_run)
        ):
            raise EvidenceValidationError(
                "certification_teacher_invalid",
                "teacher hook names, indices, shapes, dtypes, or devices differ",
            )

    rollout_identity = rollout.get("identity")
    rollout_request = rollout.get("request")
    generation = rollout.get("generation")
    output = rollout.get("output")
    rollout_runtime = rollout.get("runtime")
    output_path_matches = (
        isinstance(output, Mapping)
        and isinstance(output.get("path"), str)
        and (
            Path(output["path"]).resolve() == report_paths["rollout_video"]
            if verify_files
            else Path(output["path"]).name
            == report_paths["rollout_video"].name
        )
    )
    if (
        rollout.get("schema_version") != SCHEMA_VERSION
        or rollout.get("adapter_api_version") != MINEWORLD_ADAPTER_API_VERSION
        or rollout.get("status") != "completed"
        or rollout.get("operation") != "free_rollout"
        or not isinstance(rollout_identity, Mapping)
        or rollout_identity.get("runtime") != runtime_identity
        or rollout_identity.get("accepted_manifest_sha256")
        != inputs["accepted_trajectory_package"]["sha256"]
        or _SHA256.fullmatch(str(rollout_identity.get("request_sha256"))) is None
        or not isinstance(rollout_request, Mapping)
        or rollout_request.get("generated_frame_count") != 1
        or rollout_request.get("precision") != PINNED_PRECISION
        or rollout_request.get("device") != PINNED_DEVICE
        or not isinstance(generation, Mapping)
        or generation.get("generated_frame_count") != 1
        or generation.get("generated_token_count") != 336
        or generation.get("inference_mode_applied") is not True
        or _SHA256.fullmatch(
            str(generation.get("generated_token_sha256"))
        )
        is None
        or not isinstance(output, Mapping)
        or output.get("decoded_frames") != 1
        or output.get("width") != 384
        or output.get("height") != 224
        or output.get("frame_rate") != rollout_request.get("output_frame_rate")
        or not _finite_positive(output.get("duration_seconds"))
        or not _positive_integer(output.get("size_bytes"))
        or output.get("sha256") != reports["rollout_video"]["sha256"]
        or not output_path_matches
        or not isinstance(rollout_runtime, Mapping)
        or not _finite_nonnegative(rollout_runtime.get("elapsed_seconds"))
        or not _nonnegative_integer(
            rollout_runtime.get("peak_cuda_allocated_bytes")
        )
        or not _nonnegative_integer(
            rollout_runtime.get("peak_cuda_reserved_bytes")
        )
    ):
        raise EvidenceValidationError(
            "certification_rollout_invalid",
            "rollout report does not prove the exact one-frame pinned result",
        )

    timings = document.get("timings")
    environment = document.get("environment")
    if (
        not isinstance(timings, Mapping)
        or set(timings)
        != {
            "action_fixture_seconds",
            "model_load_seconds",
            "frame_preprocessing_seconds",
            "accepted_action_conversion_seconds",
            "vae_tokenization_seconds",
            "teacher_forward_seconds",
            "free_rollout_seconds",
            "total_seconds",
        }
        or any(
            not _finite_nonnegative(value)
            for key, value in timings.items()
            if key != "teacher_forward_seconds"
        )
        or timings.get("teacher_forward_seconds") != forward_seconds
        or timings.get("model_load_seconds") != runtime.get("model_load_seconds")
        or timings.get("free_rollout_seconds")
        != rollout_runtime.get("elapsed_seconds")
        or not isinstance(environment, Mapping)
        or not all(
            isinstance(environment.get(field), str)
            and environment[field]
            for field in (
                "python_version",
                "torch_version",
                "cuda_version",
                "device_name",
            )
        )
        or environment.get("environment_report_sha256")
        != inputs["environment_report"]["sha256"]
        or document.get("large_outputs_outside_git") is not True
        or not isinstance(document.get("command"), list)
        or "--mineocclude-revision" not in document["command"]
        or document["mineocclude_revision"] not in document["command"]
    ):
        raise EvidenceValidationError(
            "certification_summary_invalid",
            "timing, environment, command, or storage evidence is incomplete",
        )


def _finite_nonnegative(value: object) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(float(value))
        and float(value) >= 0
    )


def _finite_positive(value: object) -> bool:
    return _finite_nonnegative(value) and float(value) > 0


def _nonnegative_integer(value: object) -> bool:
    return type(value) is int and value >= 0


def _positive_integer(value: object) -> bool:
    return type(value) is int and value > 0


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "run":
            result = execute_certification(args)
        elif args.command == "preflight":
            result = json.dumps(
                execute_preflight(args),
                indent=2,
                sort_keys=True,
            )
        else:
            validate_certification_summary(
                args.summary,
                verify_files=args.verify_files,
            )
            result = args.summary
    except (EvidenceValidationError, MineWorldAdapterError, OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
