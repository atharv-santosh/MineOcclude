"""Fail-closed evidence helpers for Person A Phase 2.6-2.9.

This module is deliberately independent of CUDA and the external MineWorld
checkout.  It defines the project-owned evidence boundary that can be tested on
CPU while the commands in :mod:`mineocclude.models.phase2_aws` perform the
actual, later AWS execution.

The shared MineOcclude schema remains ``1.0``.  ``EVIDENCE_SCHEMA_VERSION`` is
an additive sub-schema identifier for these runtime-gate reports; it does not
replace or reinterpret any frozen cross-role contract.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from mineocclude.contracts.identity import SCHEMA_VERSION


EVIDENCE_SCHEMA_VERSION = "mineocclude-phase2-runtime-evidence-v1.0"
ROLLOUT_EVIDENCE_TYPE = "phase2.6_formal_rollout"
ARCHITECTURE_EVIDENCE_TYPE = "phase2.7_architecture"
TEACHER_FORCED_EVIDENCE_TYPE = "phase2.8_2.9_teacher_forced"
ACTION_COMPATIBILITY_TRANSFORMATION = (
    "mineworld_mcdataset_json_action_to_env_action"
)
ACTION_COMPATIBILITY_VERSION = "1.0"
ACTION_COMPATIBILITY_SERIALIZATION = (
    "UTF-8 JSON/Python-literal subset; sorted keys; compact separators; "
    "finite numbers; integer binary values; one LF-terminated object per row"
)

SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
GIT_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
VISUAL_TOKENS = 336
ACTION_TOKENS = 11
TOKENS_PER_PAIR = 347
CONTEXT_PAIRS = 16
SEQUENCE_LENGTH = 5552
REPO_ROOT = Path(__file__).resolve().parents[3]

ROLLOUT_OUTPUT_ROLES = frozenset(
    {"generated_video", "paired_metadata", "raw_stdout_stderr"}
)

COMMON_IDENTITY_FIELDS = frozenset(
    {
        "run_id",
        "seed",
        "source_revision",
        "asset_revision",
        "mineocclude_code_sha",
        "mineocclude_dirty",
        "model_config_sha256",
        "main_checkpoint_sha256",
        "vae_config_sha256",
        "vae_checkpoint_sha256",
        "environment_report_sha256",
        "command",
    }
)


@dataclass(frozen=True)
class EvidenceRejection:
    """One stable, machine-readable runtime-evidence rejection."""

    code: str
    message: str
    path: str


@dataclass(frozen=True)
class EvidenceValidationResult:
    """Non-throwing validation result used by CLIs and local tests."""

    rejections: tuple[EvidenceRejection, ...]

    @property
    def accepted(self) -> bool:
        return not self.rejections


class EvidenceValidationError(ValueError):
    """Raised by execution helpers when fail-closed evidence checks fail."""

    def __init__(self, code: str, message: str, path: str = "$") -> None:
        super().__init__(f"{code} at {path}: {message}")
        self.code = code
        self.message = message
        self.path = path


def canonical_json_bytes(value: Any) -> bytes:
    """Return deterministic UTF-8 JSON bytes and reject non-finite numbers."""

    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    """Return the lowercase SHA-256 identity of literal bytes."""

    if not isinstance(value, bytes):
        raise TypeError("sha256_bytes requires bytes")
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path, *, chunk_size: int = 8 * 1024 * 1024) -> str:
    """Hash one file without loading a checkpoint-sized payload into memory."""

    if not isinstance(path, Path):
        path = Path(path)
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def artifact_record(role: str, path: Path) -> dict[str, Any]:
    """Build a durable-output record from literal file bytes."""

    if not isinstance(role, str) or not role.strip():
        raise EvidenceValidationError(
            "invalid_artifact_role", "Artifact role must be non-empty."
        )
    resolved = Path(path).resolve()
    if not resolved.is_file():
        raise EvidenceValidationError(
            "missing_output", f"Required output does not exist: {resolved}"
        )
    return {
        "role": role,
        "path": str(resolved),
        "size_bytes": resolved.stat().st_size,
        "sha256": sha256_file(resolved),
    }


def _reject(
    rejections: list[EvidenceRejection],
    code: str,
    message: str,
    path: str,
) -> None:
    rejections.append(EvidenceRejection(code=code, message=message, path=path))


def _exact_fields(
    value: Any,
    expected: Iterable[str],
    path: str,
    rejections: list[EvidenceRejection],
) -> bool:
    if not isinstance(value, Mapping):
        _reject(rejections, "invalid_type", "Expected an object.", path)
        return False
    expected_set = set(expected)
    actual = set(value)
    missing = sorted(expected_set - actual)
    unknown = sorted(actual - expected_set)
    if missing:
        _reject(
            rejections,
            "missing_required_field",
            "Missing fields: " + ", ".join(missing),
            path,
        )
    if unknown:
        _reject(
            rejections,
            "unknown_field",
            "Unknown fields: " + ", ".join(unknown),
            path,
        )
    return not missing and not unknown


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and SHA256_PATTERN.fullmatch(value) is not None


def _is_git_sha(value: Any) -> bool:
    return isinstance(value, str) and GIT_SHA_PATTERN.fullmatch(value) is not None


def _is_nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_nonnegative_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _is_nonnegative_finite(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
        and float(value) >= 0.0
    )


def _is_positive_finite(value: Any) -> bool:
    return _is_nonnegative_finite(value) and float(value) > 0.0


def validate_common_identity(
    identity: Any,
    *,
    path: str = "$.identity",
) -> tuple[EvidenceRejection, ...]:
    """Validate the immutable identity shared by all Phase 2 runtime reports."""

    rejections: list[EvidenceRejection] = []
    if not _exact_fields(identity, COMMON_IDENTITY_FIELDS, path, rejections):
        return tuple(rejections)
    assert isinstance(identity, Mapping)

    for field in ("run_id",):
        if not _is_nonempty_string(identity[field]):
            _reject(
                rejections,
                "invalid_run_identity",
                f"{field} must be a non-empty string.",
                f"{path}.{field}",
            )
    if not _is_nonnegative_int(identity["seed"]):
        _reject(
            rejections,
            "invalid_seed",
            "seed must be a non-negative integer.",
            f"{path}.seed",
        )
    for field in ("source_revision", "asset_revision", "mineocclude_code_sha"):
        if not _is_git_sha(identity[field]):
            _reject(
                rejections,
                "invalid_git_sha",
                f"{field} must be a lowercase full Git SHA.",
                f"{path}.{field}",
            )
    if not isinstance(identity["mineocclude_dirty"], bool):
        _reject(
            rejections,
            "invalid_dirty_flag",
            "mineocclude_dirty must be boolean.",
            f"{path}.mineocclude_dirty",
        )
    for field in (
        "model_config_sha256",
        "main_checkpoint_sha256",
        "vae_config_sha256",
        "vae_checkpoint_sha256",
        "environment_report_sha256",
    ):
        if not _is_sha256(identity[field]):
            _reject(
                rejections,
                "invalid_sha256",
                f"{field} must be a lowercase SHA-256 value.",
                f"{path}.{field}",
            )
    command = identity["command"]
    if (
        not isinstance(command, list)
        or not command
        or any(not _is_nonempty_string(item) for item in command)
    ):
        _reject(
            rejections,
            "invalid_command",
            "command must be a non-empty list of non-empty arguments.",
            f"{path}.command",
        )
    return tuple(rejections)


def validate_timing_fields(
    timings: Any,
    *,
    path: str = "$.runtime.timings",
) -> tuple[EvidenceRejection, ...]:
    """Validate bounded rollout timing fields without accepting missing values."""

    expected = {
        "model_initialization_seconds",
        "first_generated_frame_seconds",
        "generation_kernel_seconds",
        "total_runtime_seconds",
    }
    rejections: list[EvidenceRejection] = []
    if not _exact_fields(timings, expected, path, rejections):
        return tuple(rejections)
    assert isinstance(timings, Mapping)
    for field in expected:
        if not _is_positive_finite(timings[field]):
            _reject(
                rejections,
                "invalid_timing",
                f"{field} must be finite and positive.",
                f"{path}.{field}",
            )
    if all(_is_positive_finite(timings[field]) for field in expected):
        minimum_total = (
            float(timings["model_initialization_seconds"])
            + float(timings["first_generated_frame_seconds"])
        )
        if float(timings["total_runtime_seconds"]) < minimum_total:
            _reject(
                rejections,
                "inconsistent_timing",
                "total_runtime_seconds is shorter than initialization plus generation.",
                f"{path}.total_runtime_seconds",
            )
    return tuple(rejections)


def _parse_rate(value: Any, path: str) -> str:
    if not isinstance(value, str) or "/" not in value:
        raise EvidenceValidationError(
            "invalid_ffprobe_rate", "Frame rate must be a fraction.", path
        )
    numerator_text, denominator_text = value.split("/", 1)
    try:
        numerator = int(numerator_text)
        denominator = int(denominator_text)
    except ValueError as exc:
        raise EvidenceValidationError(
            "invalid_ffprobe_rate", "Frame rate contains non-integers.", path
        ) from exc
    if numerator <= 0 or denominator <= 0:
        raise EvidenceValidationError(
            "invalid_ffprobe_rate", "Frame rate must be positive.", path
        )
    return f"{numerator}/{denominator}"


def parse_ffprobe_output(payload: str | bytes | Mapping[str, Any]) -> dict[str, Any]:
    """Parse and strictly validate ffprobe JSON for one generated video."""

    if isinstance(payload, bytes):
        try:
            payload = payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise EvidenceValidationError(
                "invalid_ffprobe_json", "ffprobe output is not UTF-8."
            ) from exc
    if isinstance(payload, str):
        try:
            document = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise EvidenceValidationError(
                "invalid_ffprobe_json", "ffprobe output is not valid JSON."
            ) from exc
    elif isinstance(payload, Mapping):
        document = deepcopy(dict(payload))
    else:
        raise EvidenceValidationError(
            "invalid_ffprobe_json", "ffprobe output must be JSON text or an object."
        )

    if set(document) - {"programs", "stream_groups", "streams", "format"}:
        raise EvidenceValidationError(
            "unknown_ffprobe_field",
            "ffprobe document contains unsupported top-level fields.",
        )
    streams = document.get("streams")
    if not isinstance(streams, list) or len(streams) != 1:
        raise EvidenceValidationError(
            "invalid_ffprobe_streams",
            "Exactly one selected video stream is required.",
            "$.streams",
        )
    stream = streams[0]
    if not isinstance(stream, Mapping):
        raise EvidenceValidationError(
            "invalid_ffprobe_stream", "Video stream must be an object.", "$.streams[0]"
        )
    required = {
        "width",
        "height",
        "r_frame_rate",
        "avg_frame_rate",
        "duration",
        "nb_frames",
        "nb_read_frames",
    }
    missing = required - set(stream)
    if missing:
        raise EvidenceValidationError(
            "missing_ffprobe_field",
            "Missing ffprobe fields: " + ", ".join(sorted(missing)),
            "$.streams[0]",
        )
    unknown = set(stream) - required
    if unknown:
        raise EvidenceValidationError(
            "unknown_ffprobe_field",
            "Unknown ffprobe fields: " + ", ".join(sorted(unknown)),
            "$.streams[0]",
        )
    try:
        width = int(stream["width"])
        height = int(stream["height"])
        duration = float(stream["duration"])
        declared_frames = int(stream["nb_frames"])
        decoded_frames = int(stream["nb_read_frames"])
    except (TypeError, ValueError) as exc:
        raise EvidenceValidationError(
            "invalid_ffprobe_value",
            "Resolution, duration, and frame counts must be numeric.",
            "$.streams[0]",
        ) from exc
    if width <= 0 or height <= 0:
        raise EvidenceValidationError(
            "invalid_video_resolution", "Generated video resolution must be positive."
        )
    if not math.isfinite(duration) or duration <= 0:
        raise EvidenceValidationError(
            "invalid_video_duration", "Generated video duration must be positive."
        )
    if declared_frames < 1 or decoded_frames < 1:
        raise EvidenceValidationError(
            "video_decode_failed",
            "Generated video must declare and decode at least one frame.",
        )
    if decoded_frames != declared_frames:
        raise EvidenceValidationError(
            "video_frame_count_mismatch",
            "Declared and decoded generated frame counts disagree.",
        )
    return {
        "width": width,
        "height": height,
        "r_frame_rate": _parse_rate(
            stream["r_frame_rate"], "$.streams[0].r_frame_rate"
        ),
        "avg_frame_rate": _parse_rate(
            stream["avg_frame_rate"], "$.streams[0].avg_frame_rate"
        ),
        "duration_seconds": duration,
        "declared_frames": declared_frames,
        "decoded_frames": decoded_frames,
    }


def _validate_artifact_shape(
    value: Any,
    path: str,
    rejections: list[EvidenceRejection],
) -> None:
    expected = {"role", "path", "size_bytes", "sha256"}
    if not _exact_fields(value, expected, path, rejections):
        return
    assert isinstance(value, Mapping)
    if not _is_nonempty_string(value["role"]):
        _reject(
            rejections,
            "invalid_artifact_role",
            "Artifact role must be non-empty.",
            f"{path}.role",
        )
    if not _is_nonempty_string(value["path"]):
        _reject(
            rejections,
            "invalid_artifact_path",
            "Artifact path must be non-empty.",
            f"{path}.path",
        )
    if not _is_nonnegative_int(value["size_bytes"]):
        _reject(
            rejections,
            "invalid_artifact_size",
            "Artifact size must be a non-negative integer.",
            f"{path}.size_bytes",
        )
    if not _is_sha256(value["sha256"]):
        _reject(
            rejections,
            "invalid_sha256",
            "Artifact sha256 is invalid.",
            f"{path}.sha256",
        )


def validate_output_file_completeness(
    outputs: Any,
    *,
    required_roles: Iterable[str] = ROLLOUT_OUTPUT_ROLES,
    verify_bytes: bool = True,
    path: str = "$.outputs",
) -> tuple[EvidenceRejection, ...]:
    """Require exact output roles and optionally re-hash every referenced file."""

    rejections: list[EvidenceRejection] = []
    if not isinstance(outputs, list):
        _reject(rejections, "invalid_type", "outputs must be a list.", path)
        return tuple(rejections)
    roles: list[str] = []
    for index, output in enumerate(outputs):
        item_path = f"{path}[{index}]"
        _validate_artifact_shape(output, item_path, rejections)
        if not isinstance(output, Mapping):
            continue
        role = output.get("role")
        if isinstance(role, str):
            roles.append(role)
        if not verify_bytes or not _is_nonempty_string(output.get("path")):
            continue
        file_path = Path(output["path"])
        if not file_path.is_file():
            _reject(
                rejections,
                "missing_output",
                "Referenced durable output is absent.",
                f"{item_path}.path",
            )
            continue
        if (
            file_path.stat().st_size != output.get("size_bytes")
            or sha256_file(file_path) != output.get("sha256")
        ):
            _reject(
                rejections,
                "output_integrity_mismatch",
                "Output size or SHA-256 disagrees with literal bytes.",
                item_path,
            )
    if len(roles) != len(set(roles)):
        _reject(
            rejections,
            "duplicate_output_role",
            "Each durable output role must be unique.",
            path,
        )
    required = set(required_roles)
    if set(roles) != required:
        _reject(
            rejections,
            "incomplete_outputs",
            "Output roles must equal: " + ", ".join(sorted(required)),
            path,
        )
    return tuple(rejections)


def _validate_provenance_file_bytes(
    value: Mapping[str, Any],
    path: str,
    rejections: list[EvidenceRejection],
) -> None:
    file_path = Path(value["path"])
    if not file_path.is_file():
        _reject(
            rejections,
            "missing_provenance_file",
            "Referenced action provenance file is absent.",
            f"{path}.path",
        )
        return
    if (
        file_path.stat().st_size != value["size_bytes"]
        or sha256_file(file_path) != value["sha256"]
    ):
        _reject(
            rejections,
            "provenance_integrity_mismatch",
            "Action provenance size or SHA-256 disagrees with literal bytes.",
            path,
        )


def _action_sequence_facts(
    path: Path,
    *,
    original_json: bool,
) -> tuple[int, str, list[str]]:
    """Recompute row-order facts from literal original or derived JSONL bytes."""

    payload = path.read_bytes()
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise EvidenceValidationError(
            "invalid_action_encoding", "Action provenance file is not UTF-8."
        ) from exc
    lines = text.splitlines()
    if not lines or any(not line.strip() for line in lines):
        raise EvidenceValidationError(
            "invalid_action_cardinality",
            "Action provenance must contain only nonempty rows.",
        )

    sequence_rows: list[bytes] = []
    row_hashes: list[str] = []
    if original_json:
        def reject_constant(value: str) -> None:
            raise ValueError(f"Non-standard JSON numeric constant: {value}")

        for index, line in enumerate(lines):
            try:
                row = json.loads(line, parse_constant=reject_constant)
            except (json.JSONDecodeError, ValueError) as exc:
                raise EvidenceValidationError(
                    "malformed_action_json",
                    f"Original provenance row {index} is not strict JSON.",
                ) from exc
            if not isinstance(row, Mapping):
                raise EvidenceValidationError(
                    "invalid_action_row",
                    f"Original provenance row {index} is not an object.",
                )
            canonical = canonical_json_bytes(row)
            sequence_rows.append(canonical)
            row_hashes.append(sha256_bytes(canonical))
    else:
        if not payload.endswith(b"\n") or b"\r" in payload:
            raise EvidenceValidationError(
                "invalid_action_serialization",
                "Derived compatibility JSONL must use exact LF-terminated rows.",
            )
        for line in lines:
            literal = (line + "\n").encode("utf-8")
            sequence_rows.append(literal)
            row_hashes.append(sha256_bytes(literal))
    return len(lines), sha256_bytes(b"".join(sequence_rows)), row_hashes


def validate_action_compatibility_provenance(
    value: Any,
    *,
    inputs: Any | None = None,
    outputs: Any | None = None,
    identity: Any | None = None,
    verify_bytes: bool = False,
    path: str = "$.action_compatibility",
) -> tuple[EvidenceRejection, ...]:
    """Validate original/derived/generated JSONL identity without repairing it."""

    rejections: list[EvidenceRejection] = []
    if not _exact_fields(
        value, {"original", "derived", "generated"}, path, rejections
    ):
        return tuple(rejections)
    assert isinstance(value, Mapping)
    original = value["original"]
    derived = value["derived"]
    generated = value["generated"]

    original_fields = {
        "classification",
        "path",
        "size_bytes",
        "sha256",
        "row_count",
        "asset_revision",
        "pre_size_bytes",
        "pre_sha256",
        "post_size_bytes",
        "post_sha256",
        "row_sequence_sha256",
        "canonical_input",
        "unchanged",
    }
    derived_fields = {
        "classification",
        "path",
        "size_bytes",
        "sha256",
        "row_count",
        "transformation_name",
        "transformation_version",
        "deterministic_serialization",
        "parent_original_sha256",
        "parent_row_sequence_sha256",
        "row_sequence_sha256",
        "source_to_derived_sequence_sha256",
        "rows_dropped",
        "rows_added",
        "row_order_preserved",
        "storage_classification",
    }
    generated_fields = {
        "classification",
        "path",
        "size_bytes",
        "sha256",
        "row_count",
        "relationship_to_generated_mp4",
        "generated_video_sha256",
        "relationship_to_original",
        "original_jsonl_sha256",
        "relationship_to_derived",
        "derived_jsonl_sha256",
        "materialization_method",
    }
    shapes_valid = (
        _exact_fields(original, original_fields, f"{path}.original", rejections),
        _exact_fields(derived, derived_fields, f"{path}.derived", rejections),
        _exact_fields(generated, generated_fields, f"{path}.generated", rejections),
    )
    if not all(shapes_valid):
        return tuple(rejections)
    assert isinstance(original, Mapping)
    assert isinstance(derived, Mapping)
    assert isinstance(generated, Mapping)

    for name, record, expected_classification in (
        ("original", original, "original"),
        ("derived", derived, "derived"),
        ("generated", generated, "generated"),
    ):
        record_path = f"{path}.{name}"
        if record["classification"] != expected_classification:
            _reject(
                rejections,
                "invalid_provenance_classification",
                f"{name} classification must be {expected_classification!r}.",
                f"{record_path}.classification",
            )
        if not _is_nonempty_string(record["path"]):
            _reject(
                rejections,
                "invalid_artifact_path",
                "Provenance path must be non-empty.",
                f"{record_path}.path",
            )
        if not _is_nonnegative_int(record["size_bytes"]):
            _reject(
                rejections,
                "invalid_artifact_size",
                "Provenance size must be a non-negative integer.",
                f"{record_path}.size_bytes",
            )
        if not _is_sha256(record["sha256"]):
            _reject(
                rejections,
                "invalid_sha256",
                "Provenance SHA-256 is invalid.",
                f"{record_path}.sha256",
            )
        if not _is_nonnegative_int(record["row_count"]) or record["row_count"] < 1:
            _reject(
                rejections,
                "invalid_action_row_count",
                "Action provenance row_count must be a positive integer.",
                f"{record_path}.row_count",
            )
        if verify_bytes and _is_nonempty_string(record["path"]):
            _validate_provenance_file_bytes(record, record_path, rejections)

    if not _is_git_sha(original["asset_revision"]):
        _reject(
            rejections,
            "invalid_git_sha",
            "Original asset_revision must be a full lowercase Git SHA.",
            f"{path}.original.asset_revision",
        )
    for field in (
        "pre_size_bytes",
        "post_size_bytes",
    ):
        if not _is_nonnegative_int(original[field]):
            _reject(
                rejections,
                "invalid_artifact_size",
                f"{field} must be a non-negative integer.",
                f"{path}.original.{field}",
            )
    for field in (
        "pre_sha256",
        "post_sha256",
        "row_sequence_sha256",
    ):
        if not _is_sha256(original[field]):
            _reject(
                rejections,
                "invalid_sha256",
                f"{field} must be a lowercase SHA-256.",
                f"{path}.original.{field}",
            )
    if (
        original["canonical_input"] is not True
        or original["unchanged"] is not True
        or original["size_bytes"] != original["pre_size_bytes"]
        or original["size_bytes"] != original["post_size_bytes"]
        or original["sha256"] != original["pre_sha256"]
        or original["sha256"] != original["post_sha256"]
    ):
        _reject(
            rejections,
            "original_action_mutated",
            "Original identity must equal both pre- and post-conversion identity.",
            f"{path}.original",
        )

    for field in (
        "parent_original_sha256",
        "parent_row_sequence_sha256",
        "row_sequence_sha256",
        "source_to_derived_sequence_sha256",
    ):
        if not _is_sha256(derived[field]):
            _reject(
                rejections,
                "invalid_sha256",
                f"{field} must be a lowercase SHA-256.",
                f"{path}.derived.{field}",
            )
    if derived["transformation_name"] != ACTION_COMPATIBILITY_TRANSFORMATION:
        _reject(
            rejections,
            "invalid_action_transformation",
            "Unsupported action compatibility transformation.",
            f"{path}.derived.transformation_name",
        )
    if derived["transformation_version"] != ACTION_COMPATIBILITY_VERSION:
        _reject(
            rejections,
            "invalid_action_transformation_version",
            "Unsupported action compatibility transformation version.",
            f"{path}.derived.transformation_version",
        )
    if derived["deterministic_serialization"] != ACTION_COMPATIBILITY_SERIALIZATION:
        _reject(
            rejections,
            "invalid_action_serialization",
            "Derived serialization description is not the frozen value.",
            f"{path}.derived.deterministic_serialization",
        )
    if derived["storage_classification"] != "runtime_only_outside_git":
        _reject(
            rejections,
            "invalid_action_storage_classification",
            "Derived JSONL must be classified runtime_only_outside_git.",
            f"{path}.derived.storage_classification",
        )
    if (
        _is_nonempty_string(derived["path"])
        and Path(derived["path"]).resolve().is_relative_to(REPO_ROOT)
    ):
        _reject(
            rejections,
            "derived_action_inside_repository",
            "Derived compatibility JSONL must remain outside the Git tree.",
            f"{path}.derived.path",
        )
    if (
        derived["parent_original_sha256"] != original["sha256"]
        or derived["parent_row_sequence_sha256"]
        != original["row_sequence_sha256"]
    ):
        _reject(
            rejections,
            "broken_action_parent_lineage",
            "Derived action lineage does not reference the original identity.",
            f"{path}.derived",
        )
    if (
        derived["row_sequence_sha256"] != derived["sha256"]
        or derived["row_count"] != original["row_count"]
        or derived["rows_dropped"] != 0
        or derived["rows_added"] != 0
        or derived["row_order_preserved"] is not True
    ):
        _reject(
            rejections,
            "invalid_action_cardinality",
            "Derived actions must preserve exact row count and order with no edits.",
            f"{path}.derived",
        )

    for field in (
        "generated_video_sha256",
        "original_jsonl_sha256",
        "derived_jsonl_sha256",
    ):
        if not _is_sha256(generated[field]):
            _reject(
                rejections,
                "invalid_sha256",
                f"{field} must be a lowercase SHA-256.",
                f"{path}.generated.{field}",
            )
    if (
        generated["relationship_to_generated_mp4"]
        != "paired_action_metadata_for_generated_video"
        or generated["relationship_to_original"]
        != "derived_from_original_via_compatibility_jsonl"
        or generated["relationship_to_derived"]
        != "byte_identical_copy_of_derived_jsonl"
        or generated["materialization_method"]
        != "upstream_byte_copy_of_derived_jsonl"
    ):
        _reject(
            rejections,
            "invalid_generated_action_relationship",
            "Generated metadata relationships are not the frozen values.",
            f"{path}.generated",
        )
    if (
        generated["original_jsonl_sha256"] != original["sha256"]
        or generated["derived_jsonl_sha256"] != derived["sha256"]
        or generated["sha256"] != derived["sha256"]
        or generated["size_bytes"] != derived["size_bytes"]
        or generated["row_count"] != derived["row_count"]
    ):
        _reject(
            rejections,
            "broken_generated_action_lineage",
            "Generated metadata is not bound to original and derived inputs.",
            f"{path}.generated",
        )

    if verify_bytes and all(
        _is_nonempty_string(record["path"])
        and Path(record["path"]).is_file()
        for record in (original, derived, generated)
    ):
        try:
            original_count, original_sequence, original_row_hashes = (
                _action_sequence_facts(
                    Path(original["path"]),
                    original_json=True,
                )
            )
            derived_count, derived_sequence, derived_row_hashes = (
                _action_sequence_facts(
                    Path(derived["path"]),
                    original_json=False,
                )
            )
        except EvidenceValidationError as exc:
            _reject(rejections, exc.code, exc.message, path)
        else:
            if (
                original_count != original["row_count"]
                or derived_count != derived["row_count"]
                or original_sequence != original["row_sequence_sha256"]
                or derived_sequence != derived["row_sequence_sha256"]
            ):
                _reject(
                    rejections,
                    "action_sequence_integrity_mismatch",
                    "Recorded row counts or sequence hashes disagree with bytes.",
                    path,
                )
            pair_binding = sha256_bytes(
                b"".join(
                    (source_hash + ":" + derived_hash + "\n").encode("ascii")
                    for source_hash, derived_hash in zip(
                        original_row_hashes,
                        derived_row_hashes,
                        strict=False,
                    )
                )
            )
            if (
                original_count != derived_count
                or pair_binding != derived["source_to_derived_sequence_sha256"]
            ):
                _reject(
                    rejections,
                    "action_row_order_mismatch",
                    "Ordered original-to-derived row binding disagrees with bytes.",
                    f"{path}.derived.source_to_derived_sequence_sha256",
                )

    if isinstance(inputs, list):
        input_by_role = {
            item.get("role"): item
            for item in inputs
            if isinstance(item, Mapping) and isinstance(item.get("role"), str)
        }
        canonical = input_by_role.get("input_jsonl")
        if (
            not isinstance(canonical, Mapping)
            or canonical.get("path") != original["path"]
            or canonical.get("size_bytes") != original["size_bytes"]
            or canonical.get("sha256") != original["sha256"]
        ):
            _reject(
                rejections,
                "canonical_input_provenance_mismatch",
                "Original provenance must equal the canonical input_jsonl artifact.",
                f"{path}.original",
            )
    if (
        not isinstance(identity, Mapping)
        or identity.get("asset_revision") != original["asset_revision"]
    ):
        _reject(
            rejections,
            "asset_revision_provenance_mismatch",
            "Original action asset revision must equal the run identity.",
            f"{path}.original.asset_revision",
        )

    if isinstance(outputs, list):
        by_role = {
            item.get("role"): item
            for item in outputs
            if isinstance(item, Mapping) and isinstance(item.get("role"), str)
        }
        paired = by_role.get("paired_metadata")
        video = by_role.get("generated_video")
        if (
            not isinstance(paired, Mapping)
            or paired.get("path") != generated["path"]
            or paired.get("size_bytes") != generated["size_bytes"]
            or paired.get("sha256") != generated["sha256"]
        ):
            _reject(
                rejections,
                "generated_metadata_output_mismatch",
                "Generated provenance does not equal the paired_metadata output.",
                f"{path}.generated",
            )
        if (
            not isinstance(video, Mapping)
            or video.get("sha256") != generated["generated_video_sha256"]
        ):
            _reject(
                rejections,
                "generated_video_lineage_mismatch",
                "Generated provenance does not bind the generated_video output.",
                f"{path}.generated.generated_video_sha256",
            )
    return tuple(rejections)


def _manifest_projection(document: Mapping[str, Any]) -> dict[str, Any]:
    projection = deepcopy(dict(document))
    projection.pop("manifest_integrity", None)
    return projection


def seal_document(document: Mapping[str, Any]) -> dict[str, Any]:
    """Return a deep-copied, canonical-hash-bound evidence document."""

    if not isinstance(document, Mapping):
        raise TypeError("document must be a mapping")
    sealed = deepcopy(dict(document))
    sealed.pop("manifest_integrity", None)
    canonical_hash = sha256_bytes(canonical_json_bytes(sealed))
    sealed["manifest_integrity"] = {
        "canonical_sha256": canonical_hash,
        "size_bytes": 0,
    }
    for _ in range(8):
        payload = canonical_json_bytes(sealed)
        size = len(payload)
        if sealed["manifest_integrity"]["size_bytes"] == size:
            return sealed
        sealed["manifest_integrity"]["size_bytes"] = size
    raise EvidenceValidationError(
        "manifest_size_unstable", "Could not stabilize manifest byte size."
    )


def write_sealed_document(path: Path, document: Mapping[str, Any]) -> dict[str, Any]:
    """Seal and atomically write one deterministic evidence document."""

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    sealed = seal_document(document)
    payload = canonical_json_bytes(sealed)
    if len(payload) != sealed["manifest_integrity"]["size_bytes"]:
        raise EvidenceValidationError(
            "manifest_size_mismatch", "Sealed manifest size is inconsistent."
        )
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_bytes(payload)
    temporary.replace(destination)
    return sealed


def validate_manifest_integrity(
    document: Any,
    *,
    literal_bytes: bytes | None = None,
    path: str = "$.manifest_integrity",
) -> tuple[EvidenceRejection, ...]:
    """Validate the canonical self-seal and, when supplied, literal byte size."""

    rejections: list[EvidenceRejection] = []
    if not isinstance(document, Mapping):
        _reject(rejections, "invalid_type", "Document must be an object.", "$")
        return tuple(rejections)
    integrity = document.get("manifest_integrity")
    expected = {"canonical_sha256", "size_bytes"}
    if not _exact_fields(integrity, expected, path, rejections):
        return tuple(rejections)
    assert isinstance(integrity, Mapping)
    expected_hash = sha256_bytes(canonical_json_bytes(_manifest_projection(document)))
    if integrity["canonical_sha256"] != expected_hash:
        _reject(
            rejections,
            "manifest_hash_mismatch",
            "Manifest canonical SHA-256 does not bind its current content.",
            f"{path}.canonical_sha256",
        )
    if not _is_nonnegative_int(integrity["size_bytes"]):
        _reject(
            rejections,
            "invalid_manifest_size",
            "Manifest size must be a non-negative integer.",
            f"{path}.size_bytes",
        )
    elif literal_bytes is not None and integrity["size_bytes"] != len(literal_bytes):
        _reject(
            rejections,
            "manifest_size_mismatch",
            "Manifest byte size disagrees with literal serialized bytes.",
            f"{path}.size_bytes",
        )
    return tuple(rejections)


def _validate_report_header(
    document: Any,
    evidence_type: str,
    expected_fields: Iterable[str],
    rejections: list[EvidenceRejection],
) -> bool:
    if not _exact_fields(document, expected_fields, "$", rejections):
        return False
    assert isinstance(document, Mapping)
    if document["schema_version"] != SCHEMA_VERSION:
        _reject(
            rejections,
            "invalid_schema_version",
            f"schema_version must remain {SCHEMA_VERSION!r}.",
            "$.schema_version",
        )
    if document["evidence_schema_version"] != EVIDENCE_SCHEMA_VERSION:
        _reject(
            rejections,
            "invalid_evidence_schema_version",
            "Unsupported Phase 2 evidence sub-schema.",
            "$.evidence_schema_version",
        )
    if document["evidence_type"] != evidence_type:
        _reject(
            rejections,
            "invalid_evidence_type",
            f"evidence_type must equal {evidence_type!r}.",
            "$.evidence_type",
        )
    if document["status"] not in {"completed", "failed"}:
        _reject(
            rejections,
            "invalid_status",
            "status must be completed or failed.",
            "$.status",
        )
    rejections.extend(validate_common_identity(document["identity"]))
    rejections.extend(validate_manifest_integrity(document))
    return True


def validate_rollout_manifest(
    document: Any,
    *,
    verify_output_bytes: bool = False,
    literal_bytes: bytes | None = None,
) -> EvidenceValidationResult:
    """Validate a formal Step 2.6 rollout record without repairing it."""

    expected_fields = {
        "schema_version",
        "evidence_schema_version",
        "evidence_type",
        "status",
        "identity",
        "inputs",
        "runtime",
        "outputs",
        "action_compatibility",
        "ffprobe",
        "manifest_integrity",
    }
    rejections: list[EvidenceRejection] = []
    if not _validate_report_header(
        document, ROLLOUT_EVIDENCE_TYPE, expected_fields, rejections
    ):
        return EvidenceValidationResult(tuple(rejections))
    assert isinstance(document, Mapping)
    if literal_bytes is not None:
        rejections.extend(validate_manifest_integrity(document, literal_bytes=literal_bytes))

    inputs = document["inputs"]
    input_roles = {
        "model_config",
        "main_checkpoint",
        "vae_config",
        "vae_checkpoint",
        "input_mp4",
        "input_jsonl",
        "environment_report",
    }
    if isinstance(inputs, list):
        roles = []
        for index, item in enumerate(inputs):
            _validate_artifact_shape(item, f"$.inputs[{index}]", rejections)
            if isinstance(item, Mapping) and isinstance(item.get("role"), str):
                roles.append(item["role"])
        if len(roles) != len(set(roles)) or set(roles) != input_roles:
            _reject(
                rejections,
                "incomplete_inputs",
                "Input artifact roles are incomplete or duplicated.",
                "$.inputs",
            )
    else:
        _reject(rejections, "invalid_type", "inputs must be a list.", "$.inputs")

    runtime_fields = {
        "timings",
        "process_exit_status",
        "peak_cuda_allocated_bytes",
        "peak_cuda_reserved_bytes",
        "gpu",
        "torch_version",
        "cuda_version",
        "generated_frames_requested",
    }
    runtime = document["runtime"]
    if _exact_fields(runtime, runtime_fields, "$.runtime", rejections):
        assert isinstance(runtime, Mapping)
        rejections.extend(validate_timing_fields(runtime["timings"]))
        if runtime["process_exit_status"] != 0:
            _reject(
                rejections,
                "generation_failed",
                "Completed rollout requires process exit status zero.",
                "$.runtime.process_exit_status",
            )
        for field in ("peak_cuda_allocated_bytes", "peak_cuda_reserved_bytes"):
            if not _is_nonnegative_int(runtime[field]):
                _reject(
                    rejections,
                    "invalid_cuda_memory",
                    f"{field} must be a non-negative integer.",
                    f"$.runtime.{field}",
                )
        if runtime["generated_frames_requested"] != 1:
            _reject(
                rejections,
                "unbounded_generation",
                "Formal smoke rollout must request exactly one generated frame.",
                "$.runtime.generated_frames_requested",
            )
        gpu = runtime["gpu"]
        gpu_fields = {"name", "device_index", "total_memory_bytes", "capability"}
        if _exact_fields(gpu, gpu_fields, "$.runtime.gpu", rejections):
            assert isinstance(gpu, Mapping)
            if not _is_nonempty_string(gpu["name"]):
                _reject(
                    rejections,
                    "invalid_gpu_identity",
                    "GPU name is required.",
                    "$.runtime.gpu.name",
                )
            if not _is_nonnegative_int(gpu["device_index"]) or not _is_nonnegative_int(
                gpu["total_memory_bytes"]
            ):
                _reject(
                    rejections,
                    "invalid_gpu_identity",
                    "GPU index and memory must be non-negative integers.",
                    "$.runtime.gpu",
                )
            if not _is_nonempty_string(gpu["capability"]):
                _reject(
                    rejections,
                    "invalid_gpu_identity",
                    "GPU capability is required.",
                    "$.runtime.gpu.capability",
                )
        for field in ("torch_version", "cuda_version"):
            if not _is_nonempty_string(runtime[field]):
                _reject(
                    rejections,
                    "invalid_runtime_version",
                    f"{field} must be non-empty.",
                    f"$.runtime.{field}",
                )

    rejections.extend(
        validate_output_file_completeness(
            document["outputs"], verify_bytes=verify_output_bytes
        )
    )
    rejections.extend(
        validate_action_compatibility_provenance(
            document["action_compatibility"],
            inputs=document["inputs"],
            outputs=document["outputs"],
            identity=document["identity"],
            verify_bytes=verify_output_bytes,
        )
    )
    try:
        parsed_ffprobe = parse_ffprobe_output(
            {"streams": [{
                "width": document["ffprobe"]["width"],
                "height": document["ffprobe"]["height"],
                "r_frame_rate": document["ffprobe"]["r_frame_rate"],
                "avg_frame_rate": document["ffprobe"]["avg_frame_rate"],
                "duration": document["ffprobe"]["duration_seconds"],
                "nb_frames": document["ffprobe"]["declared_frames"],
                "nb_read_frames": document["ffprobe"]["decoded_frames"],
            }]}
        )
        if parsed_ffprobe != document["ffprobe"]:
            _reject(
                rejections,
                "ffprobe_normalization_mismatch",
                "Stored ffprobe facts are not canonical.",
                "$.ffprobe",
            )
    except (EvidenceValidationError, KeyError, TypeError) as exc:
        _reject(
            rejections,
            "invalid_ffprobe_evidence",
            str(exc),
            "$.ffprobe",
        )
    if document["status"] != "completed":
        _reject(
            rejections,
            "incomplete_rollout",
            "Formal Step 2.6 evidence must be completed.",
            "$.status",
        )
    return EvidenceValidationResult(tuple(rejections))


EXPECTED_ARCHITECTURE = {
    "layer_count": 20,
    "hidden_size": 2048,
    "intermediate_size": 4096,
    "vocab_size": 8262,
    "max_position_embeddings": 5552,
    "num_attention_heads": 32,
    "num_key_value_heads": 4,
    "visual_tokens": VISUAL_TOKENS,
    "action_tokens": ACTION_TOKENS,
    "tokens_per_pair": TOKENS_PER_PAIR,
    "context_pairs": CONTEXT_PAIRS,
}


def validate_architecture_facts(
    architecture: Any,
    *,
    path: str = "$.architecture",
) -> tuple[EvidenceRejection, ...]:
    """Assert the exact pinned 700M/16-frame architecture facts."""

    expected_fields = set(EXPECTED_ARCHITECTURE) | {
        "decoder_layer_path",
        "model_class",
        "transformer_class",
        "vae_class",
        "dtype_distribution",
        "device_distribution",
        "parameter_counts",
    }
    rejections: list[EvidenceRejection] = []
    if not _exact_fields(architecture, expected_fields, path, rejections):
        return tuple(rejections)
    assert isinstance(architecture, Mapping)
    for field, expected in EXPECTED_ARCHITECTURE.items():
        if architecture[field] != expected:
            _reject(
                rejections,
                "architecture_mismatch",
                f"{field} must equal {expected!r}.",
                f"{path}.{field}",
            )
    for field in ("decoder_layer_path", "model_class", "transformer_class", "vae_class"):
        if not _is_nonempty_string(architecture[field]):
            _reject(
                rejections,
                "invalid_architecture_identity",
                f"{field} must be non-empty.",
                f"{path}.{field}",
            )
    for field in ("dtype_distribution", "device_distribution"):
        value = architecture[field]
        if (
            not isinstance(value, Mapping)
            or not value
            or any(
                not _is_nonempty_string(key) or not _is_nonnegative_int(count)
                for key, count in value.items()
            )
        ):
            _reject(
                rejections,
                "invalid_distribution",
                f"{field} must map names to non-negative parameter counts.",
                f"{path}.{field}",
            )
    counts = architecture["parameter_counts"]
    expected_count_fields = {"model", "transformer", "vae"}
    if _exact_fields(counts, expected_count_fields, f"{path}.parameter_counts", rejections):
        assert isinstance(counts, Mapping)
        if any(not _is_nonnegative_int(counts[field]) for field in expected_count_fields):
            _reject(
                rejections,
                "invalid_parameter_count",
                "Parameter counts must be non-negative integers.",
                f"{path}.parameter_counts",
            )
    return tuple(rejections)


def validate_architecture_report(document: Any) -> EvidenceValidationResult:
    """Validate a complete Step 2.7 report."""

    expected_fields = {
        "schema_version",
        "evidence_schema_version",
        "evidence_type",
        "status",
        "identity",
        "architecture",
        "load_state",
        "module_tree",
        "cuda_memory",
        "manifest_integrity",
    }
    rejections: list[EvidenceRejection] = []
    if not _validate_report_header(
        document, ARCHITECTURE_EVIDENCE_TYPE, expected_fields, rejections
    ):
        return EvidenceValidationResult(tuple(rejections))
    assert isinstance(document, Mapping)
    rejections.extend(validate_architecture_facts(document["architecture"]))

    load_state = document["load_state"]
    load_fields = {
        "transformer_missing_keys",
        "transformer_unexpected_keys",
        "vae_missing_keys",
        "vae_unexpected_keys",
    }
    if _exact_fields(load_state, load_fields, "$.load_state", rejections):
        assert isinstance(load_state, Mapping)
        for field in load_fields:
            value = load_state[field]
            if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
                _reject(
                    rejections,
                    "invalid_load_key_list",
                    f"{field} must be a list of strings.",
                    f"$.load_state.{field}",
                )
            elif value:
                _reject(
                    rejections,
                    "state_dict_mismatch",
                    f"{field} is non-empty and requires review.",
                    f"$.load_state.{field}",
                )
    module_tree = document["module_tree"]
    if not isinstance(module_tree, list) or not module_tree:
        _reject(
            rejections,
            "missing_module_tree",
            "Complete named_modules() evidence is required.",
            "$.module_tree",
        )
    else:
        seen_names: set[str] = set()
        for index, item in enumerate(module_tree):
            item_path = f"$.module_tree[{index}]"
            if not _exact_fields(
                item, {"name", "class_name", "direct_parameters"}, item_path, rejections
            ):
                continue
            assert isinstance(item, Mapping)
            if not isinstance(item["name"], str) or item["name"] in seen_names:
                _reject(
                    rejections,
                    "duplicate_module_name",
                    "Module names must be unique strings.",
                    f"{item_path}.name",
                )
            else:
                seen_names.add(item["name"])
            if not _is_nonempty_string(item["class_name"]):
                _reject(
                    rejections,
                    "invalid_module_class",
                    "Module class name must be non-empty.",
                    f"{item_path}.class_name",
                )
            if not _is_nonnegative_int(item["direct_parameters"]):
                _reject(
                    rejections,
                    "invalid_parameter_count",
                    "direct_parameters must be non-negative.",
                    f"{item_path}.direct_parameters",
                )
    memory = document["cuda_memory"]
    if _exact_fields(
        memory,
        {"peak_allocated_bytes", "peak_reserved_bytes"},
        "$.cuda_memory",
        rejections,
    ):
        assert isinstance(memory, Mapping)
        if any(not _is_nonnegative_int(value) for value in memory.values()):
            _reject(
                rejections,
                "invalid_cuda_memory",
                "CUDA memory values must be non-negative integers.",
                "$.cuda_memory",
            )
    if document["status"] != "completed":
        _reject(
            rejections,
            "incomplete_architecture_report",
            "Step 2.7 report must be completed.",
            "$.status",
        )
    return EvidenceValidationResult(tuple(rejections))


def token_layout_sha256(token_positions: Sequence[int]) -> str:
    """Bind an exact ordered token-position list without storing it per hook."""

    if (
        not isinstance(token_positions, Sequence)
        or isinstance(token_positions, (str, bytes))
        or any(not _is_nonnegative_int(value) for value in token_positions)
    ):
        raise EvidenceValidationError(
            "invalid_token_positions",
            "Token positions must be a sequence of non-negative integers.",
        )
    return sha256_bytes(canonical_json_bytes(list(token_positions)))


def expected_teacher_token_layout() -> dict[str, Any]:
    """Return the exact 16-pair visual/action token-position contract."""

    positions = list(range(SEQUENCE_LENGTH))
    pair_ranges = []
    for pair_index in range(CONTEXT_PAIRS):
        pair_start = pair_index * TOKENS_PER_PAIR
        action_start = pair_start + VISUAL_TOKENS
        pair_ranges.append(
            {
                "pair_index": pair_index,
                "visual_start": pair_start,
                "visual_end_exclusive": action_start,
                "action_start": action_start,
                "action_end_exclusive": pair_start + TOKENS_PER_PAIR,
            }
        )
    return {
        "visual_tokens_per_frame": VISUAL_TOKENS,
        "action_tokens_per_frame": ACTION_TOKENS,
        "tokens_per_pair": TOKENS_PER_PAIR,
        "context_pairs": CONTEXT_PAIRS,
        "sequence_length": SEQUENCE_LENGTH,
        "positions": positions,
        "positions_sha256": token_layout_sha256(positions),
        "pair_ranges": pair_ranges,
    }


def validate_hook_records(
    records: Any,
    *,
    repeats: int,
    expected_layers: int,
    sequence_length: int,
    hidden_size: int,
    expected_token_positions_sha256: str,
    expected_dtype: str | None = None,
    require_cuda: bool = False,
    path: str = "$.hooks",
) -> tuple[EvidenceRejection, ...]:
    """Validate exact layer/repeat coverage and hook output metadata."""

    rejections: list[EvidenceRejection] = []
    if not isinstance(records, list):
        _reject(rejections, "invalid_type", "hooks must be a list.", path)
        return tuple(rejections)
    expected_fields = {
        "repeat_index",
        "layer_index",
        "module_name",
        "shape",
        "dtype",
        "device",
        "token_positions_sha256",
        "output_sha256",
        "summary",
    }
    seen: set[tuple[int, int]] = set()
    module_by_layer: dict[int, str] = {}
    for index, record in enumerate(records):
        item_path = f"{path}[{index}]"
        if not _exact_fields(record, expected_fields, item_path, rejections):
            continue
        assert isinstance(record, Mapping)
        repeat_index = record["repeat_index"]
        layer_index = record["layer_index"]
        if (
            not _is_nonnegative_int(repeat_index)
            or repeat_index >= repeats
            or not _is_nonnegative_int(layer_index)
            or layer_index >= expected_layers
        ):
            _reject(
                rejections,
                "invalid_hook_identity",
                "Hook repeat/layer index is outside the expected grid.",
                item_path,
            )
            continue
        key = (repeat_index, layer_index)
        if key in seen:
            _reject(
                rejections,
                "duplicate_hook",
                "Duplicate hook claim for one repeat/layer.",
                item_path,
            )
        seen.add(key)
        module_name = record["module_name"]
        if not _is_nonempty_string(module_name):
            _reject(
                rejections,
                "invalid_hook_module",
                "Hook module name must be non-empty.",
                f"{item_path}.module_name",
            )
        elif layer_index in module_by_layer and module_by_layer[layer_index] != module_name:
            _reject(
                rejections,
                "inconsistent_hook_module",
                "One layer resolved to different modules across repeats.",
                f"{item_path}.module_name",
            )
        else:
            module_by_layer[layer_index] = module_name
        if record["shape"] != [1, sequence_length, hidden_size]:
            _reject(
                rejections,
                "hook_shape_mismatch",
                "Hook output shape disagrees with batch/token/hidden dimensions.",
                f"{item_path}.shape",
            )
        for field in ("dtype", "device"):
            if not _is_nonempty_string(record[field]):
                _reject(
                    rejections,
                    "invalid_hook_tensor_metadata",
                    f"{field} must be non-empty.",
                    f"{item_path}.{field}",
                )
        if expected_dtype is not None and record["dtype"] != expected_dtype:
            _reject(
                rejections,
                "hook_dtype_mismatch",
                f"Hook dtype must equal {expected_dtype}.",
                f"{item_path}.dtype",
            )
        if require_cuda and (
            not isinstance(record["device"], str)
            or not record["device"].startswith("cuda:")
        ):
            _reject(
                rejections,
                "hook_device_mismatch",
                "AWS hook output must originate on a CUDA device.",
                f"{item_path}.device",
            )
        for field in ("token_positions_sha256", "output_sha256"):
            if not _is_sha256(record[field]):
                _reject(
                    rejections,
                    "invalid_sha256",
                    f"{field} must be SHA-256.",
                    f"{item_path}.{field}",
                )
        if record["token_positions_sha256"] != expected_token_positions_sha256:
            _reject(
                rejections,
                "hook_token_layout_mismatch",
                "Hook token-position identity is stale or inconsistent.",
                f"{item_path}.token_positions_sha256",
            )
        summary = record["summary"]
        if not _exact_fields(
            summary, {"min", "max", "mean", "std"}, f"{item_path}.summary", rejections
        ):
            continue
        assert isinstance(summary, Mapping)
        summary_values = tuple(summary.values())
        if any(
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not math.isfinite(float(value))
            for value in summary_values
        ):
            _reject(
                rejections,
                "invalid_output_summary",
                "Hook summaries must contain finite numbers.",
                f"{item_path}.summary",
            )
    expected_grid = {
        (repeat_index, layer_index)
        for repeat_index in range(repeats)
        for layer_index in range(expected_layers)
    }
    if seen != expected_grid:
        _reject(
            rejections,
            "incomplete_hook_coverage",
            "Every expected layer must emit exactly once per repeat.",
            path,
        )
    return tuple(rejections)


def compare_numeric_sequences(
    left: Sequence[float],
    right: Sequence[float],
    *,
    rtol: float = 1e-3,
    atol: float = 1e-3,
) -> dict[str, Any]:
    """CPU-safe equivalent of an elementwise allclose repeatability check."""

    if not isinstance(left, Sequence) or not isinstance(right, Sequence):
        raise EvidenceValidationError(
            "invalid_repeatability_input", "Repeatability inputs must be sequences."
        )
    if len(left) != len(right):
        return {
            "allclose": False,
            "element_count": min(len(left), len(right)),
            "max_absolute_difference": None,
            "rtol": rtol,
            "atol": atol,
            "reason": "length_mismatch",
        }
    if (
        not _is_nonnegative_finite(rtol)
        or not _is_nonnegative_finite(atol)
        or any(
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not math.isfinite(float(value))
            for value in list(left) + list(right)
        )
    ):
        raise EvidenceValidationError(
            "invalid_repeatability_input",
            "Tolerances and sequence values must be finite numbers.",
        )
    differences = [abs(float(a) - float(b)) for a, b in zip(left, right)]
    close = all(
        difference <= float(atol) + float(rtol) * abs(float(b))
        for difference, b in zip(differences, right)
    )
    return {
        "allclose": close,
        "element_count": len(left),
        "max_absolute_difference": max(differences, default=0.0),
        "rtol": float(rtol),
        "atol": float(atol),
        "reason": None if close else "tolerance_exceeded",
    }


def validate_teacher_forced_report(document: Any) -> EvidenceValidationResult:
    """Validate a combined Step 2.8-2.9 hook/repeatability report."""

    expected_fields = {
        "schema_version",
        "evidence_schema_version",
        "evidence_type",
        "status",
        "identity",
        "execution",
        "input",
        "token_layout",
        "hooks",
        "repeatability",
        "timing",
        "memory",
        "cleanup",
        "manifest_integrity",
    }
    rejections: list[EvidenceRejection] = []
    if not _validate_report_header(
        document, TEACHER_FORCED_EVIDENCE_TYPE, expected_fields, rejections
    ):
        return EvidenceValidationResult(tuple(rejections))
    assert isinstance(document, Mapping)

    execution = document["execution"]
    execution_fields = {"repeats", "precision", "batch_size", "eval_mode", "no_grad"}
    repeats = 0
    if _exact_fields(execution, execution_fields, "$.execution", rejections):
        assert isinstance(execution, Mapping)
        repeats = execution["repeats"]
        if not _is_nonnegative_int(repeats) or repeats < 2:
            _reject(
                rejections,
                "invalid_repeat_count",
                "At least two identical forwards are required.",
                "$.execution.repeats",
            )
            repeats = 0
        if execution["precision"] not in {"float16", "bfloat16"}:
            _reject(
                rejections,
                "invalid_precision",
                "precision must be float16 or bfloat16.",
                "$.execution.precision",
            )
        if execution["batch_size"] != 1:
            _reject(
                rejections,
                "invalid_batch_size",
                "Teacher-forced batch size must equal one.",
                "$.execution.batch_size",
            )
        if execution["eval_mode"] is not True or execution["no_grad"] is not True:
            _reject(
                rejections,
                "unsafe_forward_mode",
                "eval_mode and no_grad must both be true.",
                "$.execution",
            )

    input_record = document["input"]
    input_fields = {
        "input_id",
        "input_kind",
        "mp4_sha256",
        "jsonl_sha256",
        "frame_indices",
    }
    if _exact_fields(input_record, input_fields, "$.input", rejections):
        assert isinstance(input_record, Mapping)
        if not _is_nonempty_string(input_record["input_id"]):
            _reject(
                rejections,
                "invalid_input_identity",
                "input_id must be non-empty.",
                "$.input.input_id",
            )
        if input_record["input_kind"] not in {"accepted", "synthetic"}:
            _reject(
                rejections,
                "invalid_input_kind",
                "input_kind must be accepted or synthetic.",
                "$.input.input_kind",
            )
        for field in ("mp4_sha256", "jsonl_sha256"):
            if not _is_sha256(input_record[field]):
                _reject(
                    rejections,
                    "invalid_sha256",
                    f"{field} must be SHA-256.",
                    f"$.input.{field}",
                )
        frames = input_record["frame_indices"]
        if frames != list(range(16)):
            _reject(
                rejections,
                "invalid_teacher_input_frames",
                "Pinned teacher-forced input must use frame indices 0 through 15.",
                "$.input.frame_indices",
            )

    layout = document["token_layout"]
    layout_fields = {
        "visual_tokens_per_frame",
        "action_tokens_per_frame",
        "tokens_per_pair",
        "context_pairs",
        "sequence_length",
        "positions",
        "positions_sha256",
        "pair_ranges",
    }
    sequence_length = 0
    positions_hash = ""
    if _exact_fields(layout, layout_fields, "$.token_layout", rejections):
        assert isinstance(layout, Mapping)
        expected_values = {
            "visual_tokens_per_frame": VISUAL_TOKENS,
            "action_tokens_per_frame": ACTION_TOKENS,
            "tokens_per_pair": TOKENS_PER_PAIR,
            "context_pairs": CONTEXT_PAIRS,
            "sequence_length": SEQUENCE_LENGTH,
        }
        for field, expected in expected_values.items():
            if layout[field] != expected:
                _reject(
                    rejections,
                    "token_layout_mismatch",
                    f"{field} must equal {expected}.",
                    f"$.token_layout.{field}",
                )
        sequence_length = (
            layout["sequence_length"]
            if layout["sequence_length"] == SEQUENCE_LENGTH
            else 0
        )
        positions = layout["positions"]
        expected_layout = expected_teacher_token_layout()
        if positions != expected_layout["positions"]:
            _reject(
                rejections,
                "token_positions_mismatch",
                "Token positions must be exactly 0 through 5551.",
                "$.token_layout.positions",
            )
        else:
            positions_hash = token_layout_sha256(positions)
            if layout["positions_sha256"] != positions_hash:
                _reject(
                    rejections,
                    "token_layout_hash_mismatch",
                    "Token position hash is stale.",
                    "$.token_layout.positions_sha256",
                )
        if layout["pair_ranges"] != expected_layout["pair_ranges"]:
            _reject(
                rejections,
                "token_pair_ranges_mismatch",
                "Visual/action token ranges do not match the exact 16-pair layout.",
                "$.token_layout.pair_ranges",
            )

    if repeats and sequence_length and positions_hash:
        rejections.extend(
            validate_hook_records(
                document["hooks"],
                repeats=repeats,
                expected_layers=20,
                sequence_length=sequence_length,
                hidden_size=2048,
                expected_token_positions_sha256=positions_hash,
                expected_dtype=f"torch.{execution['precision']}",
                require_cuda=True,
            )
        )

    repeatability = document["repeatability"]
    if not isinstance(repeatability, list) or len(repeatability) != 20:
        _reject(
            rejections,
            "incomplete_repeatability",
            "One repeatability result per transformer layer is required.",
            "$.repeatability",
        )
    else:
        seen_layers: set[int] = set()
        for index, item in enumerate(repeatability):
            item_path = f"$.repeatability[{index}]"
            fields = {
                "layer_index",
                "allclose",
                "max_absolute_difference",
                "rtol",
                "atol",
            }
            if not _exact_fields(item, fields, item_path, rejections):
                continue
            assert isinstance(item, Mapping)
            layer = item["layer_index"]
            if not _is_nonnegative_int(layer) or layer >= 20 or layer in seen_layers:
                _reject(
                    rejections,
                    "invalid_repeatability_layer",
                    "Repeatability layer identity is missing or duplicated.",
                    f"{item_path}.layer_index",
                )
            else:
                seen_layers.add(layer)
            if item["allclose"] is not True:
                _reject(
                    rejections,
                    "repeatability_failure",
                    "Layer outputs are not repeatable at the required tolerances.",
                    f"{item_path}.allclose",
                )
            if item["rtol"] != 1e-3 or item["atol"] != 1e-3:
                _reject(
                    rejections,
                    "repeatability_tolerance_mismatch",
                    "Required tolerances are rtol=1e-3 and atol=1e-3.",
                    item_path,
                )
            if not _is_nonnegative_finite(item["max_absolute_difference"]):
                _reject(
                    rejections,
                    "invalid_repeatability_statistic",
                    "Maximum absolute difference must be finite and non-negative.",
                    f"{item_path}.max_absolute_difference",
                )

    timing = document["timing"]
    if not isinstance(timing, Mapping):
        _reject(rejections, "invalid_type", "timing must be an object.", "$.timing")
    else:
        expected_timing = {"load_seconds", "forward_seconds"}
        if _exact_fields(timing, expected_timing, "$.timing", rejections):
            if not _is_positive_finite(timing["load_seconds"]):
                _reject(
                    rejections,
                    "invalid_timing",
                    "load_seconds must be finite and positive.",
                    "$.timing.load_seconds",
                )
            forwards = timing["forward_seconds"]
            if (
                not isinstance(forwards, list)
                or len(forwards) != repeats
                or any(not _is_positive_finite(value) for value in forwards)
            ):
                _reject(
                    rejections,
                    "invalid_timing",
                    "One positive forward time is required per repeat.",
                    "$.timing.forward_seconds",
                )

    memory = document["memory"]
    memory_fields = {
        "cpu_peak_rss_bytes",
        "peak_cuda_allocated_bytes",
        "peak_cuda_reserved_bytes",
    }
    if _exact_fields(memory, memory_fields, "$.memory", rejections):
        assert isinstance(memory, Mapping)
        if any(not _is_nonnegative_int(memory[field]) for field in memory_fields):
            _reject(
                rejections,
                "invalid_memory_report",
                "All memory measurements must be non-negative integers.",
                "$.memory",
            )
    cleanup = document["cleanup"]
    if not isinstance(cleanup, Mapping) or set(cleanup) != {"hooks_removed"}:
        _reject(
            rejections,
            "invalid_cleanup_report",
            "cleanup must contain only hooks_removed.",
            "$.cleanup",
        )
    elif cleanup["hooks_removed"] is not True:
        _reject(
            rejections,
            "hook_cleanup_failure",
            "Every temporary hook must be removed.",
            "$.cleanup.hooks_removed",
        )
    if document["status"] != "completed":
        _reject(
            rejections,
            "incomplete_teacher_forced_report",
            "Steps 2.8-2.9 evidence must be completed.",
            "$.status",
        )
    return EvidenceValidationResult(tuple(rejections))


def validate_phase2_document(
    document: Any,
    *,
    verify_output_bytes: bool = False,
) -> EvidenceValidationResult:
    """Dispatch one runtime report to its exact fail-closed validator."""

    if not isinstance(document, Mapping):
        return EvidenceValidationResult(
            (
                EvidenceRejection(
                    code="invalid_type",
                    message="Evidence document must be an object.",
                    path="$",
                ),
            )
        )
    evidence_type = document.get("evidence_type")
    if evidence_type == ROLLOUT_EVIDENCE_TYPE:
        return validate_rollout_manifest(
            document, verify_output_bytes=verify_output_bytes
        )
    if evidence_type == ARCHITECTURE_EVIDENCE_TYPE:
        return validate_architecture_report(document)
    if evidence_type == TEACHER_FORCED_EVIDENCE_TYPE:
        return validate_teacher_forced_report(document)
    return EvidenceValidationResult(
        (
            EvidenceRejection(
                code="invalid_evidence_type",
                message="Unsupported Phase 2 evidence type.",
                path="$.evidence_type",
            ),
        )
    )


def validation_main(argv: Sequence[str] | None = None) -> int:
    """Validate saved evidence without importing PyTorch or MineWorld."""

    parser = argparse.ArgumentParser(
        description="Fail-closed validator for saved Phase 2.6-2.9 evidence."
    )
    parser.add_argument("documents", nargs="+", type=Path)
    parser.add_argument(
        "--verify-output-bytes",
        action="store_true",
        help="Re-hash the durable outputs referenced by a rollout manifest.",
    )
    args = parser.parse_args(argv)
    failed = False
    for path in args.documents:
        try:
            literal = path.read_bytes()
            document = json.loads(literal)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            print(f"FAIL {path}: unreadable evidence: {exc}", file=sys.stderr)
            failed = True
            continue
        result = validate_phase2_document(
            document,
            verify_output_bytes=args.verify_output_bytes,
        )
        integrity_rejections = validate_manifest_integrity(
            document,
            literal_bytes=literal,
        )
        rejections = result.rejections + integrity_rejections
        if rejections:
            failed = True
            for rejection in rejections:
                print(
                    f"FAIL {path}: {rejection.code} at {rejection.path}: "
                    f"{rejection.message}",
                    file=sys.stderr,
                )
        else:
            print(f"PASS {path}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(validation_main())
