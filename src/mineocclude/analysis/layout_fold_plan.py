"""Freeze real layout folds from Person C evidence before Person A joins."""

from __future__ import annotations

import hashlib
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from mineocclude.analysis.config import (
    ANALYSIS_CONFIG_VERSION,
    hash_core_analysis_config,
    load_core_analysis_config,
)
from mineocclude.analysis.manifests import (
    AnalysisArtifactError,
    is_hex_digest,
    seal_artifact,
    sha256_value,
    validate_sealed_artifact,
)
from mineocclude.analysis.selection import (
    ALLOWED_SCOPES,
    selections_from_condition_source,
)
from mineocclude.probes.splits import (
    FOLD_SCHEMA_VERSION,
    GroupedSplitError,
    assign_layout_grouped_folds,
    validate_fold_manifest,
)


LAYOUT_FOLD_PLAN_SCHEMA_VERSION = "person-b-layout-fold-plan-v0.1"
FOLD_ASSIGNMENT_SOURCE = "person_c_prejoin_layout_fold_plan"


class LayoutFoldPlanError(ValueError):
    """Raised when a pre-A fold plan is stale, ambiguous, or inconsistent."""


def derive_layout_fold_plan_code_sha() -> str:
    """Hash every code component that determines real pre-A fold evidence."""

    package_root = Path(__file__).resolve().parents[1]
    repository_root = package_root.parents[1]
    components = (
        (
            "scripts/build_person_b_layout_fold_plan.py",
            repository_root
            / "scripts"
            / "build_person_b_layout_fold_plan.py",
        ),
        (
            "src/mineocclude/analysis/layout_fold_plan.py",
            package_root / "analysis" / "layout_fold_plan.py",
        ),
        (
            "src/mineocclude/analysis/config.py",
            package_root / "analysis" / "config.py",
        ),
        (
            "src/mineocclude/analysis/manifests.py",
            package_root / "analysis" / "manifests.py",
        ),
        (
            "src/mineocclude/analysis/selection.py",
            package_root / "analysis" / "selection.py",
        ),
        (
            "src/mineocclude/probes/splits.py",
            package_root / "probes" / "splits.py",
        ),
    )
    digest = hashlib.sha1()
    for label, path in components:
        try:
            payload = path.read_bytes()
        except OSError as error:
            raise LayoutFoldPlanError(
                f"Could not read fold-plan code component {label}: {error}"
            ) from error
        digest.update(label.encode("utf-8"))
        digest.update(b"\0")
        digest.update(payload)
        digest.update(b"\0")
    return digest.hexdigest()


def _require_sha256(name: str, value: Any) -> str:
    if not is_hex_digest(value, 64):
        raise LayoutFoldPlanError(f"{name} must be a SHA-256 digest.")
    return str(value).lower()


def _source_rows(document: Mapping[str, Any]) -> list[dict[str, Any]]:
    try:
        selections_from_condition_source(document)
    except (KeyError, TypeError, ValueError) as error:
        raise LayoutFoldPlanError(
            f"Condition-selection source is invalid: {error}"
        ) from error
    rows = document.get("rows")
    if not isinstance(rows, list) or not rows:
        raise LayoutFoldPlanError(
            "Condition-selection source must contain accepted rows."
        )
    return [dict(row) for row in rows]


def _layout_evidence(
    rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    row_counts = Counter(str(row["layout_id"]) for row in rows)
    trajectories: dict[str, set[str]] = defaultdict(set)
    roles: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        layout_id = str(row["layout_id"])
        trajectories[layout_id].add(str(row["trajectory_id"]))
        roles[layout_id].add(str(row["condition_role"]))
    return [
        {
            "layout_id": layout_id,
            "accepted_row_count": row_counts[layout_id],
            "trajectory_count": len(trajectories[layout_id]),
            "trajectory_ids": sorted(trajectories[layout_id]),
            "condition_roles": sorted(roles[layout_id]),
        }
        for layout_id in sorted(row_counts)
    ]


def _trajectory_assignments(
    rows: Sequence[Mapping[str, Any]],
    assignments: Mapping[str, int],
) -> list[dict[str, Any]]:
    layout_by_trajectory: dict[str, str] = {}
    for row in rows:
        trajectory_id = str(row["trajectory_id"])
        layout_id = str(row["layout_id"])
        prior = layout_by_trajectory.setdefault(trajectory_id, layout_id)
        if prior != layout_id:
            raise LayoutFoldPlanError(
                f"Trajectory {trajectory_id!r} crosses layouts."
            )
    return [
        {
            "trajectory_id": trajectory_id,
            "layout_id": layout_id,
            "fold_idx": assignments[layout_id],
        }
        for trajectory_id, layout_id in sorted(layout_by_trajectory.items())
    ]


def _scope_fold_coverage(
    rows: Sequence[Mapping[str, Any]],
    assignments: Mapping[str, int],
) -> list[dict[str, Any]]:
    layouts_by_scope: dict[str, set[str]] = defaultdict(set)
    row_counts = Counter()
    for row in rows:
        scopes = row["analysis_scopes"]
        for scope in scopes:
            layouts_by_scope[str(scope)].add(str(row["layout_id"]))
            row_counts[str(scope)] += 1
    return [
        {
            "scope": scope,
            "accepted_row_count": row_counts[scope],
            "layout_ids": sorted(layouts),
            "fold_indices": sorted(
                {assignments[layout_id] for layout_id in layouts}
            ),
        }
        for scope, layouts in sorted(layouts_by_scope.items())
    ]


def _rows_from_layout_evidence(
    evidence: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in evidence:
        layout_id = str(item["layout_id"])
        row_count = int(item["accepted_row_count"])
        rows.extend(
            {
                "trajectory_id": f"fold_plan_count_{layout_id}",
                "model_frame_idx": index,
                "layout_id": layout_id,
                "status": "accepted",
            }
            for index in range(row_count)
        )
    return rows


def build_layout_fold_plan(
    condition_source: Mapping[str, Any],
    capture_intake_report: Mapping[str, Any],
    *,
    artifact_id: str,
    condition_source_file_hash: str,
    capture_intake_file_hash: str,
) -> dict[str, Any]:
    """Build a real fold plan using only accepted Person C condition rows."""

    try:
        validate_sealed_artifact(
            capture_intake_report,
            expected_type="capture_intake_report",
        )
    except AnalysisArtifactError as error:
        raise LayoutFoldPlanError(
            f"Capture intake report is invalid: {error}"
        ) from error
    if (
        capture_intake_report.get("status")
        != "accepted_c_inputs_pending_person_a"
        or capture_intake_report.get("source_role") != "person_c"
        or capture_intake_report.get("synthetic") is not False
    ):
        raise LayoutFoldPlanError(
            "Fold planning requires accepted, real Person C intake evidence."
        )

    selection_hash = _require_sha256(
        "condition_source_file_hash",
        condition_source_file_hash,
    )
    intake_file_hash = _require_sha256(
        "capture_intake_file_hash",
        capture_intake_file_hash,
    )
    if (
        condition_source.get("source_intake_artifact_hash")
        != capture_intake_report.get("artifact_hash")
        or condition_source.get("source_capture_set_hash")
        != capture_intake_report.get("input_manifest_hash")
        or condition_source.get("source_commit")
        != capture_intake_report.get("source_commit")
        or condition_source.get("source_branch")
        != capture_intake_report.get("source_branch")
    ):
        raise LayoutFoldPlanError(
            "Condition rows and capture intake report have different provenance."
        )

    rows = _source_rows(condition_source)
    config = load_core_analysis_config()
    cross_validation = config["cross_validation"]
    n_splits = int(cross_validation["fold_count"])
    seed = int(cross_validation["split_seed"])
    try:
        assignments = assign_layout_grouped_folds(
            rows,
            n_splits=n_splits,
            seed=seed,
        )
    except GroupedSplitError as error:
        raise LayoutFoldPlanError(
            f"Person C rows cannot support frozen grouped folds: {error}"
        ) from error
    if set(assignments.values()) != set(range(n_splits)):
        raise LayoutFoldPlanError(
            "Person C rows do not populate every frozen fold index."
        )

    layout_evidence = _layout_evidence(rows)
    trajectory_assignments = _trajectory_assignments(rows, assignments)
    scope_coverage = _scope_fold_coverage(rows, assignments)
    expected_folds = list(range(n_splits))
    if any(item["fold_indices"] != expected_folds for item in scope_coverage):
        raise LayoutFoldPlanError(
            "Every declared analysis scope must cover all frozen folds."
        )

    try:
        plan = seal_artifact(
            {
                "artifact_type": "layout_fold_plan",
                "artifact_id": artifact_id,
                "code_sha": derive_layout_fold_plan_code_sha(),
                "config_hash": hash_core_analysis_config(),
                "input_manifest_hash": selection_hash,
                "layout_fold_plan_schema_version": (
                    LAYOUT_FOLD_PLAN_SCHEMA_VERSION
                ),
                "analysis_config_version": ANALYSIS_CONFIG_VERSION,
                "fold_schema_version": FOLD_SCHEMA_VERSION,
                "strategy": cross_validation["strategy"],
                "n_splits": n_splits,
                "seed": seed,
                "status": "frozen_before_person_a_join",
                "assignment_basis": (
                    "person_c_accepted_condition_rows_only"
                ),
                "fold_assignment_source": FOLD_ASSIGNMENT_SOURCE,
                "producer_role": "person_b",
                "source_role": "person_c",
                "source_branch": condition_source["source_branch"],
                "source_commit": condition_source["source_commit"],
                "source_intake_artifact_hash": capture_intake_report[
                    "artifact_hash"
                ],
                "source_intake_file_hash": intake_file_hash,
                "source_capture_set_hash": capture_intake_report[
                    "input_manifest_hash"
                ],
                "source_selection_canonical_hash": sha256_value(
                    condition_source
                ),
                "person_a_artifacts_used": False,
                "outcome_fields_used": False,
                "synthetic": False,
                "scientific_use": "permitted",
                "accepted_row_count": len(rows),
                "trajectory_count": len(trajectory_assignments),
                "layout_count": len(layout_evidence),
                "layout_assignments": [
                    {
                        "layout_id": layout_id,
                        "fold_idx": fold_idx,
                    }
                    for layout_id, fold_idx in sorted(assignments.items())
                ],
                "layout_evidence": layout_evidence,
                "trajectory_assignments": trajectory_assignments,
                "scope_fold_coverage": scope_coverage,
            }
        )
    except (AnalysisArtifactError, KeyError, TypeError) as error:
        raise LayoutFoldPlanError(
            f"Could not seal the layout fold plan: {error}"
        ) from error
    validate_layout_fold_plan(plan)
    return plan


def validate_layout_fold_plan(document: Mapping[str, Any]) -> None:
    """Validate a self-contained, outcome-independent layout fold plan."""

    try:
        validate_sealed_artifact(document, expected_type="layout_fold_plan")
    except AnalysisArtifactError as error:
        raise LayoutFoldPlanError(f"Invalid fold plan artifact: {error}") from error
    config = load_core_analysis_config()
    cross_validation = config["cross_validation"]
    n_splits = cross_validation["fold_count"]
    seed = cross_validation["split_seed"]
    expected_base = {
        "layout_fold_plan_schema_version": LAYOUT_FOLD_PLAN_SCHEMA_VERSION,
        "analysis_config_version": ANALYSIS_CONFIG_VERSION,
        "fold_schema_version": FOLD_SCHEMA_VERSION,
        "strategy": cross_validation["strategy"],
        "n_splits": n_splits,
        "seed": seed,
        "status": "frozen_before_person_a_join",
        "assignment_basis": "person_c_accepted_condition_rows_only",
        "fold_assignment_source": FOLD_ASSIGNMENT_SOURCE,
        "producer_role": "person_b",
        "source_role": "person_c",
        "person_a_artifacts_used": False,
        "outcome_fields_used": False,
        "synthetic": False,
        "scientific_use": "permitted",
    }
    for field, expected in expected_base.items():
        if document.get(field) != expected:
            raise LayoutFoldPlanError(
                f"Fold plan field {field!r} disagrees with the frozen contract."
            )
    if document.get("config_hash") != hash_core_analysis_config():
        raise LayoutFoldPlanError("Fold plan config hash is stale.")
    for field in (
        "input_manifest_hash",
        "source_intake_artifact_hash",
        "source_intake_file_hash",
        "source_capture_set_hash",
        "source_selection_canonical_hash",
    ):
        _require_sha256(field, document.get(field))
    source_branch = document.get("source_branch")
    source_commit = document.get("source_commit")
    if not isinstance(source_branch, str) or not source_branch.strip():
        raise LayoutFoldPlanError("Fold plan source branch is missing.")
    if not is_hex_digest(source_commit, 40):
        raise LayoutFoldPlanError("Fold plan source commit must be a Git SHA.")

    evidence = document.get("layout_evidence")
    if not isinstance(evidence, list) or len(evidence) < n_splits:
        raise LayoutFoldPlanError(
            "Fold plan requires evidence for at least one layout per fold."
        )
    seen_layouts: set[str] = set()
    seen_trajectories: set[str] = set()
    for item in evidence:
        if not isinstance(item, Mapping):
            raise LayoutFoldPlanError("Layout evidence rows must be mappings.")
        layout_id = item.get("layout_id")
        row_count = item.get("accepted_row_count")
        trajectory_ids = item.get("trajectory_ids")
        condition_roles = item.get("condition_roles")
        if (
            not isinstance(layout_id, str)
            or not layout_id
            or layout_id in seen_layouts
            or not isinstance(row_count, int)
            or isinstance(row_count, bool)
            or row_count <= 0
            or not isinstance(trajectory_ids, list)
            or not trajectory_ids
            or any(
                not isinstance(value, str)
                or not value
                or value in seen_trajectories
                for value in trajectory_ids
            )
            or item.get("trajectory_count") != len(trajectory_ids)
            or not isinstance(condition_roles, list)
            or not condition_roles
            or any(
                not isinstance(value, str) or not value
                for value in condition_roles
            )
        ):
            raise LayoutFoldPlanError("Layout evidence is invalid or duplicated.")
        seen_layouts.add(layout_id)
        seen_trajectories.update(trajectory_ids)

    try:
        expected_assignments = assign_layout_grouped_folds(
            _rows_from_layout_evidence(evidence),
            n_splits=n_splits,
            seed=seed,
        )
    except (GroupedSplitError, KeyError, TypeError, ValueError) as error:
        raise LayoutFoldPlanError(
            f"Layout evidence cannot reproduce the fold plan: {error}"
        ) from error
    declared_assignments = document.get("layout_assignments")
    expected_rows = [
        {"layout_id": layout_id, "fold_idx": fold_idx}
        for layout_id, fold_idx in sorted(expected_assignments.items())
    ]
    if declared_assignments != expected_rows:
        raise LayoutFoldPlanError(
            "Layout assignments do not match the frozen seeded algorithm."
        )
    if set(expected_assignments.values()) != set(range(n_splits)):
        raise LayoutFoldPlanError("Fold plan does not populate every fold.")

    trajectory_rows = document.get("trajectory_assignments")
    if not isinstance(trajectory_rows, list) or not trajectory_rows:
        raise LayoutFoldPlanError("Fold plan requires trajectory assignments.")
    expected_trajectory_rows = sorted(
        (
            {
                "trajectory_id": trajectory_id,
                "layout_id": item["layout_id"],
                "fold_idx": expected_assignments[item["layout_id"]],
            }
            for item in evidence
            for trajectory_id in item["trajectory_ids"]
        ),
        key=lambda item: item["trajectory_id"],
    )
    if trajectory_rows != expected_trajectory_rows:
        raise LayoutFoldPlanError(
            "Trajectory assignments do not match layout evidence."
        )
    if document.get("trajectory_count") != len(trajectory_rows):
        raise LayoutFoldPlanError("Fold-plan trajectory count is incorrect.")
    if document.get("layout_count") != len(evidence):
        raise LayoutFoldPlanError("Fold-plan layout count is incorrect.")
    if document.get("accepted_row_count") != sum(
        int(item["accepted_row_count"]) for item in evidence
    ):
        raise LayoutFoldPlanError("Fold-plan accepted-row count is incorrect.")

    coverage = document.get("scope_fold_coverage")
    if (
        not isinstance(coverage, list)
        or any(not isinstance(item, Mapping) for item in coverage)
        or {item.get("scope") for item in coverage} != set(ALLOWED_SCOPES)
    ):
        raise LayoutFoldPlanError(
            "Fold plan must declare every frozen analysis scope."
        )
    expected_fold_indices = list(range(n_splits))
    seen_scopes: set[str] = set()
    for item in coverage:
        scope = item.get("scope") if isinstance(item, Mapping) else None
        layout_ids = (
            item.get("layout_ids") if isinstance(item, Mapping) else None
        )
        if (
            not isinstance(item, Mapping)
            or not isinstance(scope, str)
            or scope in seen_scopes
            or not isinstance(item.get("accepted_row_count"), int)
            or item["accepted_row_count"] <= 0
            or not isinstance(layout_ids, list)
            or not layout_ids
            or layout_ids != sorted(set(layout_ids))
            or any(
                layout_id not in expected_assignments
                for layout_id in layout_ids
            )
            or item.get("fold_indices")
            != sorted({expected_assignments[value] for value in layout_ids})
            or item.get("fold_indices") != expected_fold_indices
        ):
            raise LayoutFoldPlanError("Scope fold coverage is incomplete.")
        seen_scopes.add(scope)


def validate_layout_fold_plan_against_sources(
    document: Mapping[str, Any],
    condition_source: Mapping[str, Any],
    capture_intake_report: Mapping[str, Any],
    *,
    condition_source_file_hash: str,
    capture_intake_file_hash: str,
) -> None:
    """Rebuild a plan from its C sources and require byte-for-byte semantics."""

    validate_layout_fold_plan(document)
    expected = build_layout_fold_plan(
        condition_source,
        capture_intake_report,
        artifact_id=str(document["artifact_id"]),
        condition_source_file_hash=condition_source_file_hash,
        capture_intake_file_hash=capture_intake_file_hash,
    )
    if dict(document) != expected:
        raise LayoutFoldPlanError(
            "Fold plan does not match its checked-in Person C sources."
        )


def validate_frame_fold_manifest_against_layout_plan(
    layout_fold_plan: Mapping[str, Any],
    frame_fold_manifest: Mapping[str, Any],
) -> None:
    """Require a later A-bound frame manifest to preserve C-frozen layouts."""

    validate_layout_fold_plan(layout_fold_plan)
    try:
        validate_fold_manifest(frame_fold_manifest)
    except (GroupedSplitError, AnalysisArtifactError) as error:
        raise LayoutFoldPlanError(
            f"Frame fold manifest is invalid: {error}"
        ) from error
    if (
        frame_fold_manifest.get("synthetic") is not False
        or frame_fold_manifest.get("scientific_use") != "permitted"
    ):
        raise LayoutFoldPlanError(
            "Only a real, scientifically permitted frame manifest may bind "
            "to the real C-derived fold plan."
        )
    for field in ("config_hash", "n_splits", "seed", "strategy"):
        if frame_fold_manifest.get(field) != layout_fold_plan.get(field):
            raise LayoutFoldPlanError(
                f"Frame fold field {field!r} differs from the layout plan."
            )
    if frame_fold_manifest.get("layout_assignments") != (
        layout_fold_plan.get("layout_assignments")
    ):
        raise LayoutFoldPlanError(
            "A-bound frame folds changed C's frozen layout assignments."
        )
    planned_trajectories = {
        row["trajectory_id"]: (row["layout_id"], row["fold_idx"])
        for row in layout_fold_plan["trajectory_assignments"]
    }
    observed_trajectories: dict[str, tuple[str, int]] = {}
    for row in frame_fold_manifest["memberships"]:
        trajectory_id = row["trajectory_id"]
        assignment = (row["layout_id"], row["fold_idx"])
        prior = observed_trajectories.setdefault(trajectory_id, assignment)
        if prior != assignment:
            raise LayoutFoldPlanError(
                "A-bound trajectory crosses C-frozen layout/fold assignments."
            )
    if observed_trajectories != planned_trajectories:
        raise LayoutFoldPlanError(
            "A-bound frame folds do not exactly preserve C's trajectories."
        )


def bind_frame_fold_artifacts_to_layout_plan(
    layout_fold_plan: Mapping[str, Any],
    frame_fold_manifest: Mapping[str, Any],
    intake_receipt: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Seal the plan hash into the real frame folds and pilot receipt."""

    validate_frame_fold_manifest_against_layout_plan(
        layout_fold_plan,
        frame_fold_manifest,
    )
    try:
        validate_sealed_artifact(
            intake_receipt,
            expected_type="pilot_intake_receipt",
        )
    except AnalysisArtifactError as error:
        raise LayoutFoldPlanError(
            f"Pilot intake receipt is invalid: {error}"
        ) from error
    if intake_receipt.get("fold_manifest_hash") != frame_fold_manifest.get(
        "artifact_hash"
    ):
        raise LayoutFoldPlanError(
            "Pilot intake receipt names a different frame fold manifest."
        )

    fold_payload = dict(frame_fold_manifest)
    fold_payload.pop("artifact_hash")
    fold_payload.update(
        {
            "source_layout_fold_plan_hash": layout_fold_plan[
                "artifact_hash"
            ],
            "source_layout_fold_plan_schema_version": (
                LAYOUT_FOLD_PLAN_SCHEMA_VERSION
            ),
            "fold_assignment_source": FOLD_ASSIGNMENT_SOURCE,
        }
    )
    bound_fold = seal_artifact(fold_payload)
    validate_frame_fold_manifest_against_layout_plan(
        layout_fold_plan,
        bound_fold,
    )

    receipt_payload = dict(intake_receipt)
    receipt_payload.pop("artifact_hash")
    receipt_payload.update(
        {
            "fold_manifest_hash": bound_fold["artifact_hash"],
            "layout_fold_plan_hash": layout_fold_plan["artifact_hash"],
            "fold_assignment_source": FOLD_ASSIGNMENT_SOURCE,
        }
    )
    bound_receipt = seal_artifact(receipt_payload)
    return bound_fold, bound_receipt
