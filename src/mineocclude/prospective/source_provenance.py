"""Fail-closed launch provenance for prospectively enumerated source files.

This module does not repair or upgrade any historical provenance claim. A
future launch verifies three independent byte sources for every critical path:
the expected commit tree, the staging index, and the working tree.
"""

from __future__ import annotations

import hashlib
import os
import stat
import subprocess
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

__all__ = [
    "ProvenanceViolation",
    "CriticalSource",
    "ProvenanceReceipt",
    "sha256_file",
    "verify_sources",
]


class ProvenanceViolation(RuntimeError):
    """Raised when critical source bytes are not bound to the expected commit."""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return _sha256(Path(path).read_bytes())


@dataclass(frozen=True)
class CriticalSource:
    """An explicitly enumerated source path and its authority-supplied digest."""

    relative_path: str
    expected_sha256: str

    def __post_init__(self) -> None:
        path = PurePosixPath(self.relative_path)
        if (
            not self.relative_path
            or path.is_absolute()
            or ".." in path.parts
            or str(path) != self.relative_path
        ):
            raise ValueError("relative_path must be a normalized repository-relative path")
        if (
            not isinstance(self.expected_sha256, str)
            or len(self.expected_sha256) != 64
            or any(character not in "0123456789abcdef" for character in self.expected_sha256)
        ):
            raise ValueError("expected_sha256 must be a lowercase SHA-256 hex digest")


@dataclass
class ProvenanceReceipt:
    verified: bool
    expected_commit: str | None
    repository_head: str | None
    sources: list[dict] = field(default_factory=list)
    violations: list[str] = field(default_factory=list)

    @property
    def head(self) -> str | None:
        """Compatibility alias for the repository HEAD recorded in the receipt."""
        return self.repository_head

    def to_dict(self) -> dict:
        return {
            "artifact_id": "prospective-source-provenance-receipt-v0.2",
            "verified": self.verified,
            "expected_commit": self.expected_commit,
            "repository_head": self.repository_head,
            "critical_sources_explicitly_enumerated": bool(self.sources),
            "sources": self.sources,
            "violations": self.violations,
            "enforcement": "fail_closed_before_execution",
            "does_not_repair_historical_p3_provenance": True,
        }

    def require_verified(self) -> "ProvenanceReceipt":
        if not self.verified:
            raise ProvenanceViolation("; ".join(self.violations))
        return self


def _git_bytes(repository: Path, *args: str) -> tuple[int, bytes, bytes]:
    result = subprocess.run(
        ["git", *args], cwd=repository, capture_output=True, check=False
    )
    return result.returncode, result.stdout, result.stderr


def _git_text(repository: Path, *args: str) -> tuple[int, str]:
    code, stdout, _ = _git_bytes(repository, *args)
    return code, stdout.decode("utf-8", errors="replace").strip()


def _tree_mode(repository: Path, commit: str, relative_path: str) -> str | None:
    code, stdout, _ = _git_bytes(
        repository, "ls-tree", "-z", commit, "--", relative_path
    )
    if code != 0 or not stdout:
        return None
    entries = [entry for entry in stdout.split(b"\0") if entry]
    if len(entries) != 1 or b"\t" not in entries[0]:
        return None
    metadata, _ = entries[0].split(b"\t", 1)
    fields = metadata.split()
    return fields[0].decode("ascii") if len(fields) == 3 else None


def _index_mode(repository: Path, relative_path: str) -> str | None:
    code, stdout, _ = _git_bytes(
        repository, "ls-files", "--stage", "-z", "--", relative_path
    )
    if code != 0 or not stdout:
        return None
    entries = [entry for entry in stdout.split(b"\0") if entry]
    if len(entries) != 1 or b"\t" not in entries[0]:
        return None
    metadata, _ = entries[0].split(b"\t", 1)
    fields = metadata.split()
    if len(fields) != 3 or fields[2] != b"0":
        return None
    return fields[0].decode("ascii")


def _working_entry(path: Path) -> tuple[str | None, bytes | None]:
    """Return the Git-compatible object mode and bytes for one worktree path."""
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return None, None
    if stat.S_ISLNK(metadata.st_mode):
        return "120000", os.fsencode(os.readlink(path))
    if stat.S_ISREG(metadata.st_mode):
        mode = "100755" if metadata.st_mode & 0o111 else "100644"
        return mode, path.read_bytes()
    return None, None


def verify_sources(
    repository: Path,
    sources: list[CriticalSource],
    *,
    expected_head: str,
) -> ProvenanceReceipt:
    """Bind every critical path to ``expected_head`` and its pinned SHA-256.

    Verification fails unless the current HEAD is the exact expected commit and
    tree, index, and working-tree bytes all independently equal the pinned tree
    bytes. Staged additions, modifications, deletions, and renames therefore
    cannot be hidden by a clean working-tree diff.
    """
    repository = Path(repository)
    violations: list[str] = []
    records: list[dict] = []

    code, head = _git_text(repository, "rev-parse", "HEAD")
    head = head if code == 0 else None
    if (
        not isinstance(expected_head, str)
        or len(expected_head) != 40
        or any(character not in "0123456789abcdef" for character in expected_head)
    ):
        violations.append("expected commit must be an exact lowercase 40-hex SHA")
        expected_commit = None
    else:
        code, expected_commit = _git_text(
            repository, "rev-parse", "--verify", f"{expected_head}^{{commit}}"
        )
        if code != 0:
            expected_commit = None
            violations.append(f"expected commit {expected_head!r} is missing or invalid")

    if expected_commit is not None and head != expected_commit:
        violations.append(f"HEAD {head} does not match expected {expected_commit}")
    if not sources:
        violations.append("critical source list is empty")

    seen: set[str] = set()
    for source in sources:
        record: dict = {
            "relative_path": source.relative_path,
            "expected_commit": expected_commit,
            "expected_sha256": source.expected_sha256,
        }
        if source.relative_path in seen:
            violations.append(f"{source.relative_path}: duplicate critical-source enumeration")
            record["duplicate_enumeration"] = True
            records.append(record)
            continue
        seen.add(source.relative_path)

        tree_bytes: bytes | None = None
        tree_mode: str | None = None
        if expected_commit is not None:
            tree_mode = _tree_mode(repository, expected_commit, source.relative_path)
            tree_code, tree_stdout, _ = _git_bytes(
                repository, "show", f"{expected_commit}:{source.relative_path}"
            )
            if tree_code == 0:
                tree_bytes = tree_stdout
            else:
                violations.append(
                    f"{source.relative_path}: missing from expected commit {expected_commit}"
                )

        index_mode = _index_mode(repository, source.relative_path)
        index_code, index_stdout, _ = _git_bytes(
            repository, "show", f":{source.relative_path}"
        )
        index_bytes = index_stdout if index_code == 0 else None
        path = repository / source.relative_path
        working_mode, working_bytes = _working_entry(path)

        tree_sha = _sha256(tree_bytes) if tree_bytes is not None else None
        index_sha = _sha256(index_bytes) if index_bytes is not None else None
        working_sha = _sha256(working_bytes) if working_bytes is not None else None
        record.update(
            tree_present=tree_bytes is not None,
            index_present=index_bytes is not None,
            working_tree_present=working_bytes is not None,
            tree_mode=tree_mode,
            index_mode=index_mode,
            working_tree_mode=working_mode,
            tree_sha256=tree_sha,
            index_sha256=index_sha,
            working_tree_sha256=working_sha,
            tree_matches_pin=tree_sha == source.expected_sha256,
            index_matches_tree=tree_bytes is not None and index_bytes == tree_bytes,
            working_tree_matches_tree=tree_bytes is not None and working_bytes == tree_bytes,
            index_mode_matches_tree=tree_mode is not None and index_mode == tree_mode,
            working_tree_mode_matches_tree=(
                tree_mode is not None and working_mode == tree_mode
            ),
        )

        if tree_bytes is not None and tree_sha != source.expected_sha256:
            violations.append(
                f"{source.relative_path}: expected-commit SHA-256 {tree_sha} "
                f"does not match pinned {source.expected_sha256}"
            )
        if index_bytes is None:
            violations.append(f"{source.relative_path}: absent or deleted in staging index")
        elif tree_bytes is None or index_bytes != tree_bytes:
            violations.append(
                f"{source.relative_path}: staging index differs from expected commit"
            )
        if tree_mode is None:
            violations.append(
                f"{source.relative_path}: expected-commit Git object mode is unavailable"
            )
        if index_mode is None:
            violations.append(
                f"{source.relative_path}: staging index Git object mode is unavailable"
            )
        elif tree_mode is None or index_mode != tree_mode:
            violations.append(
                f"{source.relative_path}: staging index mode {index_mode} differs "
                f"from expected-commit mode {tree_mode}"
            )
        if working_bytes is None:
            violations.append(f"{source.relative_path}: missing from working tree")
        elif tree_bytes is None or working_bytes != tree_bytes:
            violations.append(
                f"{source.relative_path}: working-tree bytes differ from expected commit"
            )
        if working_mode is None:
            violations.append(
                f"{source.relative_path}: working-tree Git object mode is unavailable"
            )
        elif tree_mode is None or working_mode != tree_mode:
            violations.append(
                f"{source.relative_path}: working-tree mode {working_mode} differs "
                f"from expected-commit mode {tree_mode}"
            )
        if working_sha is not None and working_sha != source.expected_sha256:
            violations.append(
                f"{source.relative_path}: working-tree SHA-256 {working_sha} "
                f"does not match pinned {source.expected_sha256}"
            )
        records.append(record)

    return ProvenanceReceipt(
        verified=not violations,
        expected_commit=expected_commit,
        repository_head=head,
        sources=records,
        violations=violations,
    )
