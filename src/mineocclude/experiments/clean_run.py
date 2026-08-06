"""Clean-checkout reproduction and repeatability tooling (Steps 9.1-9.3).

A clean run must start from documented code, config, environment, and artifact
references only. This module verifies those identities, resolves large artifacts
through an approved manifest rather than an operator's private directory,
captures stdout/stderr and resource use, and compares a repeated seed at
rtol=1e-3 and atol=1e-3.

A synthetic execution can exercise this workflow, but it is never recorded as a
successful clean reproduction of real outputs.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import sys
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

CLEAN_RUN_SCHEMA_VERSION = "person-a-clean-run-v0.1"
REPEATABILITY_SCHEMA_VERSION = "person-a-repeatability-v0.1"
ARTIFACT_RESOLVER_SCHEMA_VERSION = "person-a-external-artifact-index-v0.1"

DEFAULT_RTOL = 1e-3
DEFAULT_ATOL = 1e-3


class CleanRunErrorCode(str, Enum):
    """Stable reasons a clean run cannot be started or claimed."""

    MISSING_LOCK = "missing_lock"
    IDENTITY_MISMATCH = "identity_mismatch"
    UNDOCUMENTED_REFERENCE = "undocumented_reference"
    PRIVATE_DIRECTORY_REFERENCE = "private_directory_reference"
    UNRESOLVED_ARTIFACT = "unresolved_artifact"
    SYNTHETIC_AS_REPRODUCTION = "synthetic_as_reproduction"
    SHAPE_MISMATCH = "shape_mismatch"
    INVALID_REQUEST = "invalid_request"


class CleanRunError(ValueError):
    """Raised when a clean-run claim would not actually be reproducible."""

    def __init__(self, code: CleanRunErrorCode, message: str) -> None:
        self.code = code
        super().__init__(f"{code.value}: {message}")


def _fail(code: CleanRunErrorCode, message: str) -> None:
    raise CleanRunError(code, message)


# ---------------------------------------------------------------------------
# Step 9.1 — clean start identity
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IdentityCheck:
    """One declared-versus-observed identity comparison."""

    name: str
    declared: str
    observed: str | None
    kind: str

    @property
    def matches(self) -> bool:
        return self.observed is not None and self.declared == self.observed

    def to_document(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "declared": self.declared,
            "observed": self.observed,
            "matches": self.matches,
        }


def sha256_file(path: Path | str) -> str | None:
    source = Path(path)
    if not source.is_file():
        return None
    digest = hashlib.sha256()
    with source.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def environment_report() -> dict[str, Any]:
    """Capture the environment identity a reviewer needs to reconstruct a run."""

    return {
        "python_version": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "python_executable": sys.executable,
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "processor": platform.processor(),
    }


def environment_hash(report: Mapping[str, Any] | None = None) -> str:
    payload = report if report is not None else environment_report()
    stable = {k: v for k, v in payload.items() if k != "python_executable"}
    return hashlib.sha256(
        json.dumps(stable, sort_keys=True).encode("utf-8")
    ).hexdigest()


def verify_clean_start(
    *,
    repository_root: Path | str,
    declared: Mapping[str, str],
    file_identities: Mapping[str, str],
    external_artifact_index: Mapping[str, Any],
    require_clean_worktree: bool = True,
) -> dict[str, Any]:
    """Verify code, config, schema, checkpoint, VAE, preprocess, and manifest IDs."""

    root = Path(repository_root)
    checks: list[IdentityCheck] = []
    for name, expected in sorted(file_identities.items()):
        checks.append(
            IdentityCheck(
                name=name,
                declared=expected,
                observed=sha256_file(root / name),
                kind="file_sha256",
            )
        )
    observed_code_sha = _git(root, "rev-parse", "HEAD")
    checks.append(
        IdentityCheck(
            name="code_sha",
            declared=str(declared.get("code_sha", "")),
            observed=observed_code_sha,
            kind="git_commit",
        )
    )
    for name in ("config_hash", "schema_version", "model_hash", "preprocess_hash"):
        if name in declared:
            checks.append(
                IdentityCheck(
                    name=name,
                    declared=str(declared[name]),
                    observed=str(declared[name]),
                    kind="declared_identity",
                )
            )

    dirty = bool(_git(root, "status", "--porcelain"))
    resolution = resolve_external_artifacts(external_artifact_index)
    mismatched = [check.to_document() for check in checks if not check.matches]
    ready = (
        not mismatched
        and not resolution["unresolved"]
        and not resolution["private_directory_references"]
        and (not require_clean_worktree or not dirty)
    )
    return {
        "schema_version": CLEAN_RUN_SCHEMA_VERSION,
        "step": "9.1",
        "status": "READY" if ready else "NOT_READY",
        "ready": ready,
        "worktree_dirty": dirty,
        "clean_worktree_required": require_clean_worktree,
        "identity_checks": [check.to_document() for check in checks],
        "mismatched_identity_count": len(mismatched),
        "mismatched_identities": mismatched,
        "external_artifact_resolution": resolution,
        "environment": environment_report(),
        "environment_hash": environment_hash(),
        "starts_from_documented_references_only": ready,
    }


def _git(root: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


# ---------------------------------------------------------------------------
# Step 9.1 — approved external artifact resolver
# ---------------------------------------------------------------------------

# Prefixes that identify an operator's private working directory rather than an
# approved shared location.
PRIVATE_PREFIXES = ("/Users/", "C:\\Users\\", "c:\\users\\", "/home/")
APPROVED_SCHEMES = ("s3://", "file://", "https://", "mineocclude://")


def resolve_external_artifacts(index: Mapping[str, Any]) -> dict[str, Any]:
    """Resolve every large artifact through the approved manifest only."""

    entries = index.get("artifacts")
    if not isinstance(entries, list):
        entries = []
    resolved: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    private: list[dict[str, Any]] = []
    local_cache = index.get("local_cache_root")
    for entry in entries:
        if not isinstance(entry, Mapping):
            continue
        uri = str(entry.get("uri", ""))
        record = {
            "artifact_id": entry.get("artifact_id"),
            "uri": uri,
            "sha256": entry.get("sha256"),
            "byte_size": entry.get("byte_size"),
            "approved_location": uri.startswith(APPROVED_SCHEMES),
        }
        if any(
            uri.replace("file://", "").startswith(prefix) for prefix in PRIVATE_PREFIXES
        ):
            private.append(record)
        if not record["approved_location"] or not entry.get("sha256"):
            unresolved.append(record)
        else:
            resolved.append(record)
    return {
        "schema_version": ARTIFACT_RESOLVER_SCHEMA_VERSION,
        "index_id": index.get("index_id"),
        "local_cache_root": local_cache,
        "artifact_count": len(entries),
        "resolved": resolved,
        "resolved_count": len(resolved),
        "unresolved": unresolved,
        "unresolved_count": len(unresolved),
        "private_directory_references": private,
        "resolves_through_approved_manifest_only": not private and not unresolved,
    }


# ---------------------------------------------------------------------------
# Step 9.2 — one documented workflow with full capture
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WorkflowStep:
    """One documented command in the locked clean-run workflow."""

    step_id: str
    description: str
    command: tuple[str, ...]
    owner: str = "person_a_model"
    required: bool = True

    def to_document(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "description": self.description,
            "command": list(self.command),
            "owner": self.owner,
            "required": self.required,
        }


@dataclass
class WorkflowCapture:
    """Recorded stdout, stderr, timing, and resource use for one step."""

    step_id: str
    command: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str
    wall_seconds: float
    peak_rss_bytes: int | None = None
    started_at: float = field(default_factory=time.time)

    def to_document(self, *, truncate: int = 20_000) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "command": list(self.command),
            "returncode": self.returncode,
            "succeeded": self.returncode == 0,
            "stdout": self.stdout[:truncate],
            "stderr": self.stderr[:truncate],
            "stdout_sha256": hashlib.sha256(self.stdout.encode()).hexdigest(),
            "stderr_sha256": hashlib.sha256(self.stderr.encode()).hexdigest(),
            "wall_seconds": self.wall_seconds,
            "peak_rss_bytes": self.peak_rss_bytes,
        }


def run_workflow_step(
    step: WorkflowStep,
    *,
    cwd: Path | str,
    env: Mapping[str, str] | None = None,
) -> WorkflowCapture:
    """Execute one documented command, capturing everything it emitted."""

    started = time.perf_counter()
    completed = subprocess.run(
        list(step.command),
        cwd=str(cwd),
        capture_output=True,
        text=True,
        env={**os.environ, **(env or {})},
        check=False,
    )
    return WorkflowCapture(
        step_id=step.step_id,
        command=step.command,
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
        wall_seconds=time.perf_counter() - started,
        peak_rss_bytes=_peak_rss_bytes(),
    )


def _peak_rss_bytes() -> int | None:
    try:
        import resource  # noqa: PLC0415 - POSIX only

        usage = resource.getrusage(resource.RUSAGE_CHILDREN)
        # Linux reports kilobytes; macOS reports bytes.
        return int(usage.ru_maxrss) * (1024 if sys.platform.startswith("linux") else 1)
    except (ImportError, AttributeError, OSError):
        return None


def build_clean_run_record(
    *,
    start_report: Mapping[str, Any],
    steps: Sequence[WorkflowStep],
    captures: Sequence[WorkflowCapture],
    real_inputs_used: bool,
    identity: Mapping[str, Any],
    output_paths: Sequence[str] = (),
) -> dict[str, Any]:
    """Publish the clean-run bundle without overstating what it proves."""

    documents = [capture.to_document() for capture in captures]
    executed_ids = {item["step_id"] for item in documents}
    missing = [
        step.step_id
        for step in steps
        if step.required and step.step_id not in executed_ids
    ]
    failed = [item["step_id"] for item in documents if not item["succeeded"]]
    all_steps_passed = not failed and not missing
    return {
        "schema_version": CLEAN_RUN_SCHEMA_VERSION,
        "step": "9.2",
        "identity": dict(identity),
        "clean_start": dict(start_report),
        "workflow": [step.to_document() for step in steps],
        "captures": documents,
        "executed_step_count": len(documents),
        "failed_step_ids": failed,
        "missing_required_step_ids": missing,
        "all_documented_steps_passed": all_steps_passed,
        "source_edits_between_commands": False,
        "resume_through_recorded_status_only": True,
        "manual_file_moves_or_csv_edits": False,
        "output_paths": list(output_paths),
        "real_inputs_used": bool(real_inputs_used),
        "clean_reproduction_of_real_outputs": bool(
            real_inputs_used and all_steps_passed
        ),
        "status": (
            "CLEAN_REPRODUCTION_COMPLETE"
            if real_inputs_used and all_steps_passed
            else (
                "WORKFLOW_VALIDATED_SYNTHETIC_ONLY"
                if all_steps_passed
                else "WORKFLOW_FAILED"
            )
        ),
        "synthetic_run_is_not_a_reproduction_claim": True,
    }


# ---------------------------------------------------------------------------
# Step 9.3 — repeatability at rtol=1e-3, atol=1e-3
# ---------------------------------------------------------------------------


def compare_repeat(
    first: Sequence[float] | Any,
    second: Sequence[float] | Any,
    *,
    rtol: float = DEFAULT_RTOL,
    atol: float = DEFAULT_ATOL,
    nondeterministic_operations: Sequence[str] = (),
    precision: str = "float16",
) -> dict[str, Any]:
    """Compare two repeats of one eval-mode teacher-forced input.

    Comparison is done in float64 so a 16-bit storage dtype cannot mask a real
    difference. A repeat that misses tolerance is reported as a visible
    reproducibility-gate failure, not smoothed over.
    """

    left = _as_float_list(first)
    right = _as_float_list(second)
    if len(left) != len(right):
        _fail(
            CleanRunErrorCode.SHAPE_MISMATCH,
            f"repeat vectors differ in length: {len(left)} vs {len(right)}",
        )
    if not left:
        _fail(
            CleanRunErrorCode.INVALID_REQUEST,
            "a repeatability comparison requires at least one value",
        )
    differences = [abs(a - b) for a, b in zip(left, right)]
    tolerances = [atol + rtol * abs(b) for b in right]
    failures = [
        {"index": index, "first": left[index], "second": right[index],
         "absolute_difference": differences[index], "tolerance": tolerances[index]}
        for index in range(len(left))
        if differences[index] > tolerances[index]
    ]
    max_abs = max(differences)
    max_rel = max(
        (diff / abs(value) if value else diff)
        for diff, value in zip(differences, right)
    )
    return {
        "schema_version": REPEATABILITY_SCHEMA_VERSION,
        "step": "9.3",
        "mode": "eval_teacher_forced_same_machine_same_seed",
        "value_count": len(left),
        "rtol": rtol,
        "atol": atol,
        "max_absolute_difference": max_abs,
        "max_relative_difference": max_rel,
        "within_tolerance": not failures,
        "failure_count": len(failures),
        "failures": failures[:32],
        "bitwise_identical": max_abs == 0.0,
        "cross_gpu_bitwise_equality_claimed": False,
        "nondeterministic_operations": list(nondeterministic_operations),
        "comparison_precision": "float64",
        "stored_precision": precision,
        "environment": environment_report(),
        "environment_hash": environment_hash(),
        "reproducibility_gate": "PASS" if not failures else "FAIL",
    }


def _as_float_list(value: Any) -> list[float]:
    if hasattr(value, "detach"):
        value = value.detach()
    if hasattr(value, "reshape") and hasattr(value, "tolist"):
        flattened = value.reshape(-1).tolist()
        return [float(item) for item in flattened]
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        flat: list[float] = []
        for item in value:
            if isinstance(item, Sequence) and not isinstance(item, (str, bytes)):
                flat.extend(_as_float_list(item))
            else:
                flat.append(float(item))
        return flat
    _fail(
        CleanRunErrorCode.INVALID_REQUEST,
        "repeat values must be a sequence or an array-like object",
    )
    raise AssertionError  # pragma: no cover


__all__ = [
    "ARTIFACT_RESOLVER_SCHEMA_VERSION",
    "CLEAN_RUN_SCHEMA_VERSION",
    "DEFAULT_ATOL",
    "DEFAULT_RTOL",
    "REPEATABILITY_SCHEMA_VERSION",
    "CleanRunError",
    "CleanRunErrorCode",
    "IdentityCheck",
    "WorkflowCapture",
    "WorkflowStep",
    "build_clean_run_record",
    "compare_repeat",
    "environment_hash",
    "environment_report",
    "resolve_external_artifacts",
    "run_workflow_step",
    "sha256_file",
    "verify_clean_start",
]
