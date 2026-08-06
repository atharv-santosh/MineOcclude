"""Step 7.1 — reproduce the frozen Person E measurement path from clean inputs.

The manual's requirement is narrow and mechanical: a reviewer starting from a
clean checkout and the immutable MVP config must be able to re-run E's
measurement entry points, in order, with no source edit between stages, and
compare the result against the locked outputs.

This module owns the contract for that run. It validates the plan before
anything executes, executes the declared stages while capturing exactly what
happened, and assembles a receipt whose evidence class is always explicit.
A run over synthetic fixtures is a legitimate rehearsal of the workflow but is
never allowed to describe itself as a real reproduction.
"""

from __future__ import annotations

import os
import platform
import re
import subprocess
import sys
import time
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any

from mineocclude.analysis.manifests import is_hex_digest
from mineocclude.experiments.registry import (
    hash_file_bytes,
    hash_json_value,
)


CLEAN_REPRODUCTION_PLAN_SCHEMA_VERSION = "person-e-clean-reproduction-plan-v0.1"
CLEAN_REPRODUCTION_RECEIPT_SCHEMA_VERSION = (
    "person-e-clean-reproduction-receipt-v0.1"
)
CLEAN_REPRODUCTION_COMPARISON_SCHEMA_VERSION = (
    "person-e-clean-reproduction-comparison-v0.1"
)

#: Ordered measurement entry points. Order is part of the contract: registry
#: identity must be established before detection, detection before geometry,
#: geometry before displacement, and displacement before image coherence.
REPRODUCTION_STAGES = (
    "registry",
    "detector",
    "homography",
    "displacement",
    "ssim",
)

#: A reproduction is either over real accepted upstream inputs or over
#: repository fixtures. The two are never merged into one claim.
EVIDENCE_CLASSES = frozenset({"real", "synthetic_fixture"})

STAGE_OUTCOMES = frozenset({"passed", "failed", "skipped_external_input"})

#: Person E component files whose bytes define the measurement instrument.
#: A reproduction that does not pin these is not reproducing anything.
DEFAULT_COMPONENT_PATHS = (
    "src/mineocclude/vision/magenta.py",
    "src/mineocclude/vision/homography.py",
    "src/mineocclude/vision/measurement.py",
    "src/mineocclude/vision/ssim.py",
    "src/mineocclude/vision/config.py",
    "src/mineocclude/vision/detection_records.py",
    "src/mineocclude/experiments/registry.py",
    "scripts/fit_homographies.py",
    "scripts/localize_u4_frames.py",
    "scripts/measure_ssim.py",
    "scripts/compose_u4_evidence.py",
    "scripts/measure_u4.py",
)

_PRIVATE_PATH_PATTERNS = (
    re.compile(r"^[A-Za-z]:[\\/]"),
    re.compile(r"^\\\\"),
    re.compile(r"^/home/"),
    re.compile(r"^/Users/"),
    re.compile(r"^/mnt/"),
    re.compile(r"^~"),
)


SHA256_HEX_LENGTH = 64


def _is_sha256(value: object) -> bool:
    return is_hex_digest(value, SHA256_HEX_LENGTH)


class CleanReproductionError(ValueError):
    """Raised when a reproduction plan, run, or comparison cannot be trusted."""


def _require_mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CleanReproductionError(f"{name} must be a JSON object.")
    return value


def _require_sequence(value: Any, name: str) -> Sequence[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise CleanReproductionError(f"{name} must be a JSON array.")
    return value


def _require_text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CleanReproductionError(f"{name} must be a non-empty string.")
    return value


def is_private_path_token(token: str) -> bool:
    """Return whether ``token`` binds a command to one operator's machine.

    Absolute paths, UNC shares, and home-directory references cannot be
    reproduced by a reviewer, so they are rejected before a run rather than
    discovered when the receipt is already written.
    """

    return any(pattern.search(token) for pattern in _PRIVATE_PATH_PATTERNS)


def private_path_tokens(command: Sequence[str]) -> list[str]:
    return [token for token in command if is_private_path_token(token)]


def component_hashes(
    root: Path | str,
    component_paths: Sequence[str] = DEFAULT_COMPONENT_PATHS,
) -> dict[str, str]:
    """Hash every declared component file, relative to ``root``."""

    base = Path(root)
    digests: dict[str, str] = {}
    for relative in component_paths:
        candidate = base / relative
        if not candidate.is_file():
            raise CleanReproductionError(f"Missing component file: {relative}")
        digests[relative] = hash_file_bytes(candidate)
    return digests


def environment_lock() -> dict[str, Any]:
    """Capture the interpreter identity a reproduction actually ran under."""

    return {
        "implementation": platform.python_implementation(),
        "machine": platform.machine(),
        "python_version": platform.python_version(),
        "system": platform.system(),
    }


def validate_clean_reproduction_plan(document: Any) -> Mapping[str, Any]:
    """Fail closed on any plan that could not be re-run by a reviewer."""

    plan = _require_mapping(document, "clean reproduction plan")
    if (
        plan.get("clean_reproduction_plan_schema_version")
        != CLEAN_REPRODUCTION_PLAN_SCHEMA_VERSION
    ):
        raise CleanReproductionError("Unknown clean-reproduction plan schema version.")

    evidence_class = _require_text(plan.get("evidence_class"), "evidence_class")
    if evidence_class not in EVIDENCE_CLASSES:
        raise CleanReproductionError(f"Unsupported evidence class: {evidence_class}")

    _require_text(plan.get("code_commit"), "code_commit")
    _require_mapping(plan.get("environment_lock"), "environment_lock")

    components = _require_mapping(plan.get("component_hashes"), "component_hashes")
    if not components:
        raise CleanReproductionError("A plan must pin at least one component hash.")
    for relative, digest in components.items():
        if not _is_sha256(digest):
            raise CleanReproductionError(f"Component hash is not a digest: {relative}")

    inputs = _require_sequence(plan.get("inputs"), "inputs")
    if not inputs:
        raise CleanReproductionError("A plan must declare its direct inputs.")
    seen_input_ids: set[str] = set()
    for raw_input in inputs:
        row = _require_mapping(raw_input, "input row")
        input_id = _require_text(row.get("input_id"), "input_id")
        if input_id in seen_input_ids:
            raise CleanReproductionError(f"Duplicate input identity: {input_id}")
        seen_input_ids.add(input_id)
        _require_text(row.get("owner"), "input owner")
        if not _is_sha256(row.get("sha256")):
            raise CleanReproductionError(f"Input hash is not a digest: {input_id}")
        relative = _require_text(row.get("repository_path"), "repository_path")
        if is_private_path_token(relative):
            raise CleanReproductionError(
                f"Input {input_id} depends on a private path: {relative}"
            )

    stages = _require_sequence(plan.get("stages"), "stages")
    stage_names = [
        _require_text(_require_mapping(stage, "stage").get("stage"), "stage")
        for stage in stages
    ]
    if tuple(stage_names) != REPRODUCTION_STAGES:
        raise CleanReproductionError(
            "Stages must be exactly "
            f"{list(REPRODUCTION_STAGES)} in order; got {stage_names}."
        )
    for raw_stage in stages:
        stage = _require_mapping(raw_stage, "stage")
        name = str(stage.get("stage"))
        command = _require_sequence(stage.get("command"), f"{name} command")
        if not command:
            raise CleanReproductionError(f"Stage {name} declares no command.")
        tokens = [_require_text(token, f"{name} command token") for token in command]
        offending = private_path_tokens(tokens)
        if offending:
            raise CleanReproductionError(
                f"Stage {name} depends on private paths: {offending}"
            )
        _require_sequence(stage.get("expected_outputs"), f"{name} expected_outputs")
    return plan


def verify_component_hashes(
    plan: Mapping[str, Any],
    root: Path | str,
) -> dict[str, Any]:
    """Compare the plan's pinned component bytes against the working tree."""

    pinned = _require_mapping(plan.get("component_hashes"), "component_hashes")
    observed = component_hashes(root, tuple(sorted(pinned)))
    mismatched = sorted(
        relative for relative, digest in pinned.items() if observed[relative] != digest
    )
    return {
        "component_count": len(pinned),
        "mismatched_components": mismatched,
        "verified": not mismatched,
    }


def verify_input_hashes(
    plan: Mapping[str, Any],
    root: Path | str,
) -> dict[str, Any]:
    """Compare each declared direct input against its recorded digest."""

    base = Path(root)
    mismatched: list[str] = []
    missing: list[str] = []
    for raw_input in _require_sequence(plan.get("inputs"), "inputs"):
        row = _require_mapping(raw_input, "input row")
        input_id = str(row["input_id"])
        candidate = base / str(row["repository_path"])
        if not candidate.is_file():
            missing.append(input_id)
            continue
        if hash_file_bytes(candidate) != row["sha256"]:
            mismatched.append(input_id)
    return {
        "input_count": len(list(plan["inputs"])),
        "mismatched_inputs": sorted(mismatched),
        "missing_inputs": sorted(missing),
        "verified": not mismatched and not missing,
    }


def run_stage(
    stage: Mapping[str, Any],
    root: Path | str,
    *,
    timeout_seconds: float = 900.0,
    substitutions: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Execute one stage, capturing exactly what a reviewer would need.

    ``substitutions`` expands placeholders such as ``{workdir}`` at execution
    time. The portable, placeholder-bearing command is what gets recorded, so a
    receipt never carries one operator's scratch directory.
    """

    name = str(stage["stage"])
    command = [str(token) for token in stage["command"]]
    resolved = command
    if substitutions:
        resolved = [
            token.format_map({**substitutions}) if "{" in token else token
            for token in command
        ]
    started = time.monotonic()
    try:
        completed = subprocess.run(
            [sys.executable, *resolved],
            cwd=str(root),
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
    except subprocess.TimeoutExpired:
        return {
            "command": command,
            "exit_code": None,
            "outcome": "failed",
            "runtime_seconds": round(time.monotonic() - started, 6),
            "stage": name,
            "stderr_tail": f"timed out after {timeout_seconds} seconds",
            "stdout_tail": "",
        }
    runtime = time.monotonic() - started
    return {
        "command": command,
        "exit_code": completed.returncode,
        "outcome": "passed" if completed.returncode == 0 else "failed",
        "runtime_seconds": round(runtime, 6),
        "stage": name,
        "stderr_tail": completed.stderr[-4000:],
        "stdout_tail": completed.stdout[-4000:],
    }


def compare_outputs(
    locked: Mapping[str, Any],
    reproduced: Mapping[str, Any],
) -> dict[str, Any]:
    """Compare locked and reproduced measurement summaries field by field.

    Schema, counts, statuses, and hashes are compared separately so that a
    reviewer can tell a benign environment difference from a real divergence.
    """

    fields = ("schema_version", "row_count", "status_counts", "output_sha256")
    differences: list[dict[str, Any]] = []
    for field in fields:
        locked_value = locked.get(field)
        reproduced_value = reproduced.get(field)
        if locked_value != reproduced_value:
            differences.append(
                {
                    "field": field,
                    "locked": locked_value,
                    "reproduced": reproduced_value,
                }
            )
    return {
        "clean_reproduction_comparison_schema_version": (
            CLEAN_REPRODUCTION_COMPARISON_SCHEMA_VERSION
        ),
        "compared_fields": list(fields),
        "differences": differences,
        "identical": not differences,
    }


def build_clean_reproduction_receipt(
    *,
    plan: Mapping[str, Any],
    component_verification: Mapping[str, Any],
    input_verification: Mapping[str, Any],
    stage_results: Sequence[Mapping[str, Any]],
    comparison: Mapping[str, Any] | None,
    post_run_component_hashes: Mapping[str, str],
    blocking_external_inputs: Sequence[str] = (),
) -> dict[str, Any]:
    """Assemble the receipt. Every claim here is derived, never asserted."""

    validate_clean_reproduction_plan(plan)
    for result in stage_results:
        outcome = result.get("outcome")
        if outcome not in STAGE_OUTCOMES:
            raise CleanReproductionError(f"Unsupported stage outcome: {outcome}")

    # "No source edits between stages" is only meaningful if it is measured.
    pinned = dict(plan["component_hashes"])
    edited = sorted(
        relative
        for relative, digest in pinned.items()
        if post_run_component_hashes.get(relative) != digest
    )

    executed = [result for result in stage_results if result["outcome"] != "skipped_external_input"]
    failed = [result for result in stage_results if result["outcome"] == "failed"]
    skipped = [
        result for result in stage_results if result["outcome"] == "skipped_external_input"
    ]
    evidence_class = str(plan["evidence_class"])

    reproduction_complete = bool(
        evidence_class == "real"
        and component_verification.get("verified")
        and input_verification.get("verified")
        and not edited
        and not failed
        and not skipped
        and comparison is not None
        and comparison.get("identical")
        and not list(blocking_external_inputs)
    )

    receipt = {
        "clean_reproduction_receipt_schema_version": (
            CLEAN_REPRODUCTION_RECEIPT_SCHEMA_VERSION
        ),
        "blocking_external_inputs": sorted(blocking_external_inputs),
        "code_commit": plan["code_commit"],
        "comparison": dict(comparison) if comparison is not None else None,
        "component_verification": dict(component_verification),
        "environment_lock": dict(plan["environment_lock"]),
        "evidence_class": evidence_class,
        "executed_stage_count": len(executed),
        "failed_stages": sorted(str(result["stage"]) for result in failed),
        "input_verification": dict(input_verification),
        "real_clean_reproduction_complete": reproduction_complete,
        "skipped_stages": sorted(str(result["stage"]) for result in skipped),
        "source_edited_between_stages": bool(edited),
        "source_edited_components": edited,
        "stage_results": [dict(result) for result in stage_results],
        "stage_order": list(REPRODUCTION_STAGES),
        "total_runtime_seconds": round(
            sum(float(result.get("runtime_seconds") or 0.0) for result in stage_results),
            6,
        ),
    }
    receipt["receipt_content_hash"] = hash_json_value(
        {key: value for key, value in receipt.items() if key != "receipt_content_hash"}
    )
    return receipt


def validate_clean_reproduction_receipt(document: Any) -> Mapping[str, Any]:
    """Reject a receipt that claims more than its own contents support."""

    receipt = _require_mapping(document, "clean reproduction receipt")
    if (
        receipt.get("clean_reproduction_receipt_schema_version")
        != CLEAN_REPRODUCTION_RECEIPT_SCHEMA_VERSION
    ):
        raise CleanReproductionError(
            "Unknown clean-reproduction receipt schema version."
        )
    evidence_class = receipt.get("evidence_class")
    if evidence_class not in EVIDENCE_CLASSES:
        raise CleanReproductionError(f"Unsupported evidence class: {evidence_class}")
    complete = receipt.get("real_clean_reproduction_complete")
    if not isinstance(complete, bool):
        raise CleanReproductionError(
            "real_clean_reproduction_complete must be a boolean."
        )
    if complete and evidence_class != "real":
        raise CleanReproductionError(
            "A synthetic fixture run may not claim a real clean reproduction."
        )
    if complete and receipt.get("failed_stages"):
        raise CleanReproductionError(
            "A completed reproduction cannot report failed stages."
        )
    if complete and receipt.get("source_edited_between_stages"):
        raise CleanReproductionError(
            "A completed reproduction cannot report source edits between stages."
        )
    if complete and receipt.get("blocking_external_inputs"):
        raise CleanReproductionError(
            "A completed reproduction cannot report blocking external inputs."
        )
    recomputed = hash_json_value(
        {
            key: value
            for key, value in receipt.items()
            if key != "receipt_content_hash"
        }
    )
    if recomputed != receipt.get("receipt_content_hash"):
        raise CleanReproductionError("Clean-reproduction receipt content hash drift.")
    return receipt


def repository_relative(path: Path, root: Path) -> str:
    """Return a portable repository-relative path, rejecting outside paths."""

    try:
        relative = path.resolve().relative_to(Path(root).resolve())
    except ValueError as error:
        raise CleanReproductionError(
            f"Path escapes the repository root: {path}"
        ) from error
    return PurePosixPath(relative.as_posix()).as_posix()
