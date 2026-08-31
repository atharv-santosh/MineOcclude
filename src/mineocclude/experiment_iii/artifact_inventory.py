"""Stage-exit artifact completeness (``EXPECTED_ARTIFACT_INVENTORY.json``).

The inventory exists so that missing evidence is **auto-detectable** rather than
noticed later. Every artifact marked ``required_before_next_stage`` names its own
``missing_blocker``, and :func:`stage_exit_check` reports that exact code when the
artifact is absent -- never a generic "something is missing", because a generic
failure cannot be routed by the recovery runbook.

III-A closure never requires a III-B artifact, and
:func:`assert_iii_a_closure_needs_no_iii_b_artifact` proves it from the inventory
rather than from prose.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

from mineocclude.experiment_iii.authority import AUTHORITY_ROOT
from mineocclude.experiment_iii.errors import ExperimentIIIError

__all__ = [
    "INVENTORY_PATH",
    "REPOSITORY_PATH_ALIASES",
    "UNNAMED_MISSING_BLOCKER",
    "artifacts_for_stage",
    "assert_iii_a_closure_needs_no_iii_b_artifact",
    "expected_artifact_inventory",
    "required_before_next_stage",
    "resolve_artifact_path",
    "stage_exit_check",
    "stage_exit_check_fs",
    "stages",
]

INVENTORY_PATH = AUTHORITY_ROOT / "EXPECTED_ARTIFACT_INVENTORY.json"

#: Four inventory rows (three ``B-GEN`` III-B provenance artifacts and the
#: ``B-LOCK`` closure receipt) are ``required_before_next_stage`` with a **null**
#: ``missing_blocker``. That is a gap in the inventory data, not a licence to
#: exit the stage: the check still fails closed, under this taxonomy code.
UNNAMED_MISSING_BLOCKER = "PROVENANCE_BINDING_MISSING"


@lru_cache(maxsize=1)
def expected_artifact_inventory() -> dict[str, Any]:
    if not INVENTORY_PATH.is_file():
        raise ExperimentIIIError(
            "AUTHORITY_INCOMPLETE", f"artifact inventory is absent: {INVENTORY_PATH}"
        )
    return json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))


def stages() -> list[str]:
    """Every lifecycle stage that owns at least one expected artifact."""
    seen: list[str] = []
    for artifact in expected_artifact_inventory()["artifacts"]:
        stage = str(artifact["stage"])
        if stage not in seen:
            seen.append(stage)
    return seen


def artifacts_for_stage(stage: str) -> list[dict[str, Any]]:
    return [
        artifact
        for artifact in expected_artifact_inventory()["artifacts"]
        if str(artifact["stage"]) == stage
    ]


def required_before_next_stage(stage: str) -> list[dict[str, Any]]:
    return [
        artifact
        for artifact in artifacts_for_stage(stage)
        if artifact.get("required_before_next_stage")
    ]


def stage_exit_check(stage: str, present: Iterable[str]) -> dict[str, Any]:
    """Refuse to exit ``stage`` while a required artifact is absent.

    The raised blocker is the artifact's own ``missing_blocker``, so the failure
    routes straight into the recovery runbook.
    """
    have = set(str(path) for path in present)
    for artifact in required_before_next_stage(stage):
        pattern = str(artifact["path_or_pattern"])
        if pattern not in have:
            raise ExperimentIIIError(
                str(artifact.get("missing_blocker") or UNNAMED_MISSING_BLOCKER),
                f"stage {stage} cannot exit: {artifact['artifact']} "
                f"({pattern}) is absent",
            )
    return {
        "stage": stage,
        "required_count": len(required_before_next_stage(stage)),
        "present_count": len(have),
        "exit_permitted": True,
    }


#: Where this repository actually materialises artifacts whose frozen inventory
#: path differs. The inventory is frozen at ``A0`` and specifies
#: ``data/experiment_iii/...`` for the cohort and provenance receipts and
#: ``docs/experiment_iii/receipts/...`` for three more; the implementation
#: materialised them under ``docs/experiment_iii/cohort/`` and
#: ``docs/experiment_iii/a1_receipts/``. Both sets exist and are byte-stable --
#: only the location diverged -- so this table reconciles the implementation to
#: the frozen authority explicitly rather than leaving ``stage_exit_check`` unable
#: to find a single real file. Every entry is a location, never a substitution:
#: no artifact is satisfied by a *different* artifact.
REPOSITORY_PATH_ALIASES = {
    "data/experiment_iii/cohort/": "docs/experiment_iii/cohort/",
    "data/experiment_iii/provenance/aprime_port_receipt.json": (
        "docs/experiment_iii/a1_receipts/aprime_port_receipt.json"
    ),
    "data/experiment_iii/provenance/fir_kernel_recovery_receipt.json": (
        "docs/experiment_iii/a1_receipts/fir_kernel_recovery_receipt.json"
    ),
    "docs/experiment_iii/receipts/cohort_all_q_qualification_receipt.json": (
        "docs/experiment_iii/cohort/cohort_all_q_qualification_receipt.json"
    ),
    "docs/experiment_iii/receipts/q_regression_a1_receipt.json": (
        "docs/experiment_iii/cohort/q_regression_a1_receipt.json"
    ),
    "docs/experiment_iii/receipts/implementation_completion_receipt.json": (
        "docs/experiment_iii/a1_receipts/implementation_completion_receipt.json"
    ),
}


def resolve_artifact_path(pattern: str) -> str:
    """The repository-relative path where ``pattern`` is actually materialised."""
    text = str(pattern)
    if text in REPOSITORY_PATH_ALIASES:
        return REPOSITORY_PATH_ALIASES[text]
    for prefix, replacement in REPOSITORY_PATH_ALIASES.items():
        if prefix.endswith("/") and text.startswith(prefix):
            return replacement + text[len(prefix) :]
    return text


def stage_exit_check_fs(stage: str, root: Path) -> dict[str, Any]:
    """Refuse to exit ``stage`` while a required artifact is absent **on disk**.

    :func:`stage_exit_check` compares caller-supplied strings, so its only caller
    fed it the inventory's own patterns and asserted they were found -- a check
    that cannot fail, and therefore could not detect that not one ``A1`` artifact
    was at its specified path. This one stats the filesystem, which is what the
    authority means by "makes missing evidence auto-detectable".

    A pattern containing ``*`` or ``<`` is a glob or a host-parameterised name and
    is satisfied by any match; an exact path must exist exactly.
    """
    root = Path(root)
    present: list[str] = []
    resolved: dict[str, str] = {}
    for artifact in required_before_next_stage(stage):
        pattern = str(artifact["path_or_pattern"])
        target = resolve_artifact_path(pattern)
        resolved[pattern] = target
        if "*" in target or "<" in target:
            head, _, tail = target.rpartition("/")
            glob = tail.replace("<host>", "*")
            if "*" not in glob:
                glob = f"*{glob}*"
            if any((root / head).glob(glob)) if head else any(root.glob(glob)):
                present.append(pattern)
        elif (root / target).is_file():
            present.append(pattern)
    report = stage_exit_check(stage, present)
    report["filesystem_backed"] = True
    report["root"] = root.as_posix()
    report["resolved_paths"] = resolved
    return report


def assert_iii_a_closure_needs_no_iii_b_artifact() -> dict[str, Any]:
    """No III-A closure requirement may be satisfied by a III-B artifact."""
    inventory = expected_artifact_inventory()
    offending = sorted(
        str(artifact["artifact"])
        for artifact in inventory["artifacts"]
        if artifact.get("required_for_iii_a_closure")
        and str(artifact.get("module", "III_A")).upper().replace("-", "_") == "III_B"
    )
    if offending:
        raise ExperimentIIIError(
            "B_III_A_DEPENDENCY_DETECTED",
            f"III-A closure requires III-B artifacts: {offending}",
        )
    return {
        "iii_a_closure_requires_no_iii_b_artifact": True,
        "declared_in_inventory": bool(
            inventory.get("iii_a_closure_requires_no_iii_b_artifact")
        ),
        "artifact_count": inventory["artifact_count"],
    }
