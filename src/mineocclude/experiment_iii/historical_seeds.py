"""The historical seed exclusion set (authority 2.4 gate 11, test A.19).

Gate 11 requires that a candidate seed appear in **no** historical Regime A,
Regime A-prime or Experiment II manifest reachable from this repository. A1
materializes the set explicitly and binds its hash rather than asserting the
property, so the gate is checked against evidence.

The scan is deliberately broad: any integer ``seed`` or ``noise_seed`` field in
any JSON/JSONL artifact under ``docs/`` or ``data/``, excluding the Experiment
III namespace itself. It also reads the two bound A-prime manifests out of the
git object database, which are not present in the worktree.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from mineocclude.experiment_iii.authority import (
    D2_REFERENCE_COMMIT,
    D2_REFERENCE_PATH,
    D2_REFERENCE_SHA256,
    FIR_RECOVERY_COMMIT,
    FIR_RECOVERY_PATH,
    FIR_RECOVERY_SHA256,
    REPOSITORY_ROOT,
    canonical_sha256,
)
from mineocclude.experiment_iii.errors import ExperimentIIIError

__all__ = [
    "SEED_FIELD_NAMES",
    "build_historical_seed_exclusion_set",
    "excluded_seeds",
]

#: Field names that carry a generator seed in the historical manifests.
SEED_FIELD_NAMES = ("seed", "noise_seed")

#: Scanned roots. The Experiment III namespace is excluded: its own seeds are
#: covered by gate 10 (uniqueness within Experiment III), not gate 11.
_SCAN_ROOTS = ("docs", "data")
_EXCLUDED_SUBTREES = ("docs/experiment_iii", "data/experiment_iii")


def _collect(value: Any, into: dict[int, set[str]], source: str) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if (
                key in SEED_FIELD_NAMES
                and isinstance(child, int)
                and not isinstance(child, bool)
                and child > 0
            ):
                into.setdefault(child, set()).add(source)
            else:
                _collect(child, into, source)
    elif isinstance(value, list):
        for child in value:
            _collect(child, into, source)


def _scan_worktree(root: Path, into: dict[int, set[str]]) -> int:
    scanned = 0
    for scan_root in _SCAN_ROOTS:
        base = root / scan_root
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if path.suffix not in (".json", ".jsonl") or not path.is_file():
                continue
            relative = path.relative_to(root).as_posix()
            if any(
                relative.startswith(excluded + "/") for excluded in _EXCLUDED_SUBTREES
            ):
                continue
            scanned += 1
            try:
                text = path.read_text(encoding="utf-8", errors="strict")
            except (OSError, UnicodeDecodeError):
                continue
            try:
                if path.suffix == ".jsonl":
                    for line in text.splitlines():
                        if line.strip():
                            _collect(json.loads(line), into, relative)
                else:
                    _collect(json.loads(text), into, relative)
            except json.JSONDecodeError:
                # A malformed historical artifact carries no readable seed; it is
                # recorded as scanned and skipped rather than failing the build.
                continue
    return scanned


def _scan_bound_git_manifests(into: dict[int, set[str]]) -> list[dict[str, str]]:
    from mineocclude.experiment_iii.aprime_reference import read_git_blob

    bound = [
        {
            "commit": FIR_RECOVERY_COMMIT,
            "path": FIR_RECOVERY_PATH,
            "sha256": FIR_RECOVERY_SHA256,
        },
        {
            "commit": D2_REFERENCE_COMMIT,
            "path": D2_REFERENCE_PATH,
            "sha256": D2_REFERENCE_SHA256,
        },
    ]
    for source in bound:
        payload = read_git_blob(
            source["commit"], source["path"], expected_sha256=source["sha256"]
        )
        _collect(
            json.loads(payload),
            into,
            f"git:{source['commit'][:7]}:{source['path']}",
        )
    return bound


def build_historical_seed_exclusion_set(
    root: Path | None = None,
) -> dict[str, Any]:
    """Materialize the exclusion set and its provenance."""
    base = Path(root) if root is not None else REPOSITORY_ROOT
    found: dict[int, set[str]] = {}
    scanned = _scan_worktree(base, found)
    bound = _scan_bound_git_manifests(found)
    seeds = sorted(found)
    body = {
        "schema_version": "mineocclude-experiment-iii-historical-seed-exclusion-v1",
        "authority_section": "2.4 gate 11",
        "seed_field_names": list(SEED_FIELD_NAMES),
        "scanned_roots": list(_SCAN_ROOTS),
        "excluded_subtrees": list(_EXCLUDED_SUBTREES),
        "worktree_files_scanned": scanned,
        "bound_git_manifests": bound,
        "excluded_seed_count": len(seeds),
        "excluded_seeds": seeds,
        "source_manifests": {
            str(seed): sorted(found[seed]) for seed in seeds
        },
    }
    body["exclusion_set_sha256"] = canonical_sha256(
        {"excluded_seeds": seeds}
    )
    if not seeds:
        raise ExperimentIIIError(
            "COHORT_SEED_COLLISION",
            "the historical seed exclusion set is empty; gate 11 would be "
            "vacuous, which is a defect in the scan rather than evidence",
        )
    return body


def excluded_seeds(exclusion_set: dict[str, Any]) -> frozenset[int]:
    return frozenset(int(value) for value in exclusion_set["excluded_seeds"])
