"""Experiment III namespace isolation (authority 0.4).

Historical Regime A, Regime A-prime and Experiment II scientific artifacts are
immutable. Every Experiment III write goes through :func:`guard_write_path`,
which resolves the target and refuses anything outside the Experiment III
artifact and source roots, or anything under a historical namespace.

The guard is path-based and deliberately conservative: it refuses by default and
admits only the enumerated Experiment III roots, so a new historical directory
appearing later is refused without anyone having to remember to blocklist it.
"""

from __future__ import annotations

import os
from pathlib import Path, PurePosixPath

from mineocclude.experiment_iii.authority import REPOSITORY_ROOT
from mineocclude.experiment_iii.errors import ExperimentIIIError

__all__ = [
    "EXPERIMENT_III_ARTIFACT_ROOTS",
    "EXPERIMENT_III_SOURCE_ROOTS",
    "HISTORICAL_ARTIFACT_ROOTS",
    "guard_write_path",
    "is_experiment_iii_path",
    "experiment_iii_docs_root",
    "experiment_iii_data_root",
]


#: Authority 0.4. Repository-relative, POSIX form.
EXPERIMENT_III_ARTIFACT_ROOTS = (
    "docs/experiment_iii",
    "data/experiment_iii",
)

EXPERIMENT_III_SOURCE_ROOTS = (
    "src/mineocclude/experiment_iii",
    "scripts/experiment_iii",
    "tests/experiment_iii",
)

#: Named for the error message only. Admission is by allowlist, not by this list.
HISTORICAL_ARTIFACT_ROOTS = (
    "docs/status",
    "data/regime_a",
    "data/regime_a_prime",
    "data/experiment_ii",
    "docs/experiment_ii",
    "src/mineocclude/prospective",
    "p11_distributed_handoff",
    "preauthority_creation_inputs",
)

#: The frozen authority package itself is never written by an implementation
#: process. Authority drift requires stop-and-adjudicate (authority 9.2).
FROZEN_AUTHORITY_SUBTREE = "docs/experiment_iii/final_authorities"


def _resolve_root(root: Path | None) -> Path:
    """The repository root, read at call time.

    Read late rather than bound as a default argument so a relocated run root
    (and the guard's own tests) apply to every caller, including helpers that
    forward no root of their own.
    """
    return Path(root) if root is not None else REPOSITORY_ROOT


def _relative_posix(path: os.PathLike[str] | str, *, root: Path) -> PurePosixPath | None:
    """Repository-relative POSIX path, or None when the target is outside it."""
    resolved = Path(path)
    if not resolved.is_absolute():
        resolved = root / resolved
    # ``resolve`` on a not-yet-created file still normalizes ``..`` segments,
    # which is the traversal case this guard exists to catch.
    resolved = Path(os.path.normpath(resolved.resolve(strict=False)))
    try:
        return PurePosixPath(resolved.relative_to(root).as_posix())
    except ValueError:
        return None


def is_experiment_iii_path(
    path: os.PathLike[str] | str, *, root: Path | None = None
) -> bool:
    """Whether ``path`` lies inside an Experiment III artifact or source root."""
    relative = _relative_posix(path, root=_resolve_root(root))
    if relative is None:
        return False
    text = relative.as_posix()
    if text == FROZEN_AUTHORITY_SUBTREE or text.startswith(
        FROZEN_AUTHORITY_SUBTREE + "/"
    ):
        return False
    return any(
        text == owned or text.startswith(owned + "/")
        for owned in EXPERIMENT_III_ARTIFACT_ROOTS + EXPERIMENT_III_SOURCE_ROOTS
    )


def guard_write_path(
    path: os.PathLike[str] | str, *, root: Path | None = None
) -> Path:
    """Refuse any write outside the Experiment III namespace.

    Returns the resolved path so callers can use the guarded value directly and
    cannot accidentally write the unguarded one.
    """
    root = _resolve_root(root)
    relative = _relative_posix(path, root=root)
    if relative is None:
        raise ExperimentIIIError(
            "PROVENANCE_NAMESPACE_VIOLATION",
            f"write target is outside the repository: {path}",
        )
    text = relative.as_posix()
    if text == FROZEN_AUTHORITY_SUBTREE or text.startswith(
        FROZEN_AUTHORITY_SUBTREE + "/"
    ):
        raise ExperimentIIIError(
            "PROVENANCE_NAMESPACE_VIOLATION",
            "the frozen authority package is immutable during implementation: "
            f"{text}",
        )
    if not is_experiment_iii_path(path, root=root):
        owner = next(
            (
                historical
                for historical in HISTORICAL_ARTIFACT_ROOTS
                if text == historical or text.startswith(historical + "/")
            ),
            None,
        )
        detail = (
            f"path is owned by a prior experiment ({owner})"
            if owner
            else "path is not inside an Experiment III root"
        )
        raise ExperimentIIIError(
            "PROVENANCE_NAMESPACE_VIOLATION",
            f"refusing Experiment III write to {text}: {detail}",
        )
    return Path(root) / relative.as_posix()


def experiment_iii_docs_root(root: Path | None = None) -> Path:
    return _resolve_root(root) / "docs" / "experiment_iii"


def experiment_iii_data_root(root: Path | None = None) -> Path:
    return _resolve_root(root) / "data" / "experiment_iii"
