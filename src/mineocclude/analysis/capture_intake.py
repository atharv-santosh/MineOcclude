"""Authenticate Person C pilot captures before any Person A join.

This module owns the C-only portion of Person B Step 6.1. It validates literal
capture bytes, re-runs C's frozen package validator, verifies the declared
wall-parallel scalar against one unambiguous signed world axis, and freezes the
condition rows that later A activations must cover.

It deliberately does not invent Person A model/preprocess hashes or promote
the captures to completed pilot evidence. State inputs and oracle targets
remain blocked until the matching A provenance and activation handoff exist.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mineocclude.analysis.config import hash_core_analysis_config
from mineocclude.analysis.coordinates import (
    coordinate_frame_hash,
    validate_coordinate_frame,
)
from mineocclude.analysis.manifests import (
    is_hex_digest,
    seal_artifact,
    sha256_value,
)
from mineocclude.analysis.selection import (
    SCOPE_HIDDEN_MEAN,
    SCOPE_HIDDEN_SPREAD,
    SCOPE_VISIBLE_NO_WALL,
    selections_from_condition_source,
)
from mineocclude.data.capture_contract import validate_capture_package
from mineocclude.oracle.capture_audit import (
    audit_capture_package_oracle_math,
    audit_fixed_tau_q_sensitivity,
)


CAPTURE_INTAKE_SCHEMA_VERSION = "person-b-c-capture-intake-v0.1"
CAPTURE_SOURCE_LIST_SCHEMA_VERSION = "person-b-c-capture-source-list-v0.1"
COORDINATE_FRAME_SCHEMA_VERSION = "person-b-wall-parallel-frame-v0.1"
CONDITION_SELECTION_SOURCE_SCHEMA_VERSION = (
    "person-b-condition-selection-source-v0.1"
)
PROJECTION_TOLERANCE_BLOCKS = 1e-9

_CORE_CONDITION = "core"
_NO_WALL_CONDITION = "no_wall_visible"
_NO_SHEEP_CONDITION = "occluder_only_no_sheep"
_ALLOWED_CONDITIONS = frozenset(
    {_CORE_CONDITION, _NO_WALL_CONDITION, _NO_SHEEP_CONDITION}
)
_AXIS_CANDIDATES: tuple[tuple[str, tuple[float, float, float]], ...] = (
    ("positive_x", (1.0, 0.0, 0.0)),
    ("negative_x", (-1.0, 0.0, 0.0)),
    ("positive_z", (0.0, 0.0, 1.0)),
    ("negative_z", (0.0, 0.0, -1.0)),
)


class CaptureIntakeError(ValueError):
    """Raised when a real Person C capture cannot be accepted by Person B."""


@dataclass(frozen=True)
class CaptureSource:
    """One literal capture document and its transport-integrity evidence."""

    path: str
    package: Mapping[str, Any]
    literal_sha256: str
    sidecar_sha256: str


@dataclass(frozen=True)
class CaptureIntakeBundle:
    """C-only Step 6.1 evidence ready for later A provenance."""

    report: Mapping[str, Any]
    coordinate_frames: tuple[Mapping[str, Any], ...]
    condition_selection_source: Mapping[str, Any]


def derive_capture_intake_code_sha() -> str:
    """Hash every source file that determines C-only intake evidence."""

    package_root = Path(__file__).resolve().parents[1]
    repository_root = package_root.parents[1]
    code_components = (
        (
            "scripts/intake_person_c_pilot.py",
            repository_root / "scripts" / "intake_person_c_pilot.py",
        ),
        (
            "src/mineocclude/analysis/capture_intake.py",
            package_root / "analysis" / "capture_intake.py",
        ),
        (
            "src/mineocclude/analysis/config.py",
            package_root / "analysis" / "config.py",
        ),
        (
            "src/mineocclude/analysis/coordinates.py",
            package_root / "analysis" / "coordinates.py",
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
            "src/mineocclude/data/capture_contract.py",
            package_root / "data" / "capture_contract.py",
        ),
        (
            "src/mineocclude/oracle/closed_form.py",
            package_root / "oracle" / "closed_form.py",
        ),
        (
            "src/mineocclude/oracle/capture_audit.py",
            package_root / "oracle" / "capture_audit.py",
        ),
        (
            "src/mineocclude/oracle/primary_scalar_kalman.py",
            package_root / "oracle" / "primary_scalar_kalman.py",
        ),
        (
            "src/mineocclude/oracle/schema.py",
            package_root / "oracle" / "schema.py",
        ),
    )
    digest = hashlib.sha1()
    for label, path in code_components:
        try:
            payload = path.read_bytes()
        except OSError as error:
            raise CaptureIntakeError(
                f"Could not read intake code component {label}: {error}"
            ) from error
        digest.update(label.encode("utf-8"))
        digest.update(b"\0")
        digest.update(payload)
        digest.update(b"\0")
    return digest.hexdigest()


def _require_non_empty_string(name: str, value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CaptureIntakeError(f"{name} must be a non-empty string.")
    return value


def _source_identity(source: CaptureSource) -> tuple[str, str]:
    package = source.package
    trajectory_id = package.get("trajectory_id")
    layout_id = package.get("layout_id")
    return (
        _require_non_empty_string("trajectory_id", trajectory_id),
        _require_non_empty_string("layout_id", layout_id),
    )


def _validate_source(source: CaptureSource) -> None:
    _require_non_empty_string("capture path", source.path)
    if not is_hex_digest(source.literal_sha256, 64):
        raise CaptureIntakeError(
            f"{source.path}: literal_sha256 must be SHA-256."
        )
    if not is_hex_digest(source.sidecar_sha256, 64):
        raise CaptureIntakeError(
            f"{source.path}: sidecar_sha256 must be SHA-256."
        )
    if source.literal_sha256.lower() != source.sidecar_sha256.lower():
        raise CaptureIntakeError(
            f"{source.path}: literal bytes do not match C's checksum sidecar."
        )
    if not isinstance(source.package, Mapping):
        raise CaptureIntakeError(f"{source.path}: package must be a mapping.")

    validation = validate_capture_package(source.package)
    if not validation.accepted:
        details = "; ".join(
            f"{item.code.value}: {item.message}"
            for item in validation.rejections
        )
        raise CaptureIntakeError(
            f"{source.path}: C package validation failed: {details}"
        )

    manifest = source.package.get("episode_manifest")
    if not isinstance(manifest, Mapping) or manifest.get("status") != "accepted":
        raise CaptureIntakeError(
            f"{source.path}: episode manifest is not accepted."
        )
    if manifest.get("superseded_by") is not None:
        raise CaptureIntakeError(
            f"{source.path}: accepted input cannot already be superseded."
        )
    if source.package.get("scientific_use") != "pending_cross_role_signoff":
        raise CaptureIntakeError(
            f"{source.path}: unexpected C scientific-use boundary."
        )
    if source.package.get("condition") not in _ALLOWED_CONDITIONS:
        raise CaptureIntakeError(
            f"{source.path}: unsupported pilot condition "
            f"{source.package.get('condition')!r}."
        )


def _state_rows(package: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    streams = package["streams"]
    rows = streams["server_state"]
    return [row["state"] for row in rows]


def _visibility_rows(package: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    rows = package["streams"]["visibility"]
    return sorted(rows, key=lambda row: row["server_tick"])


def _projection_error(
    state_rows: Sequence[Mapping[str, Any]],
    direction: tuple[float, float, float],
) -> float:
    return max(
        abs(
            float(row["wall_parallel_position_blocks"])
            - (
                direction[0] * float(row["position_x_blocks"])
                + direction[1] * float(row["position_y_blocks"])
                + direction[2] * float(row["position_z_blocks"])
            )
        )
        for row in state_rows
    )


def build_signed_coordinate_frame(
    source: CaptureSource,
) -> dict[str, Any] | None:
    """Return B/C's verified signed frame, or ``None`` for no-object controls."""

    _validate_source(source)
    states = _state_rows(source.package)
    target_presence = {row["target_present"] for row in states}
    if target_presence == {False}:
        return None
    if target_presence != {True}:
        raise CaptureIntakeError(
            f"{source.path}: target presence changes within one capture."
        )

    candidates = [
        (name, direction, _projection_error(states, direction))
        for name, direction in _AXIS_CANDIDATES
    ]
    matching = [
        (name, direction, error)
        for name, direction, error in candidates
        if error <= PROJECTION_TOLERANCE_BLOCKS
    ]
    if len(matching) != 1:
        errors = {name: error for name, _direction, error in candidates}
        raise CaptureIntakeError(
            f"{source.path}: wall-parallel axis is not unique: {errors!r}."
        )

    axis_name, direction, maximum_error = matching[0]
    trajectory_id, _layout_id = _source_identity(source)
    manifest = source.package["episode_manifest"]
    frame: dict[str, Any] = {
        "coordinate_frame_schema_version": COORDINATE_FRAME_SCHEMA_VERSION,
        "coordinate_frame_id": f"person_b_c_live_{trajectory_id}_v1",
        "wall_parallel_origin_world_xyz": [0.0, 0.0, 0.0],
        "wall_parallel_positive_unit_vector_world_xyz": list(direction),
        "source_layout_manifest_hash": manifest["layout_config_hash"],
        "adapter_signoff": {"person_b": True, "person_c": True},
    }
    frame["coordinate_frame_hash"] = coordinate_frame_hash(frame)
    frame["adapter_signoff_evidence"] = {
        "person_c": (
            "accepted capture declares wall_parallel_position_blocks"
        ),
        "person_b": (
            "all target-present state rows match one unique signed world axis"
        ),
        "axis_name": axis_name,
        "maximum_projection_error_blocks": maximum_error,
        "projection_tolerance_blocks": PROJECTION_TOLERANCE_BLOCKS,
        "source_capture_path": source.path,
        "source_capture_sha256": source.literal_sha256.lower(),
        "approval_scope": "coordinate_projection_only",
    }
    validate_coordinate_frame(frame)
    return frame


def _visibility_summary(
    package: Mapping[str, Any],
) -> tuple[dict[str, int], list[dict[str, str]]]:
    ordered = _visibility_rows(package)
    counts = {"visible": 0, "occluded": 0}
    for row in ordered:
        counts[row["visibility"]] += 1
    transitions = [
        {"from": previous["visibility"], "to": current["visibility"]}
        for previous, current in zip(ordered, ordered[1:])
        if previous["visibility"] != current["visibility"]
    ]
    return counts, transitions


def _classification(package: Mapping[str, Any]) -> str:
    condition = package["condition"]
    if condition == _CORE_CONDITION:
        return "oracle_eligible_core"
    if condition == _NO_WALL_CONDITION:
        return "visible_no_wall_control"
    return "no_object_not_oracle_eligible"


def _selection_rows(
    sources: Sequence[CaptureSource],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for source in sources:
        package = source.package
        condition = package["condition"]
        if condition == _NO_SHEEP_CONDITION:
            continue
        layout_id = package["layout_id"]
        for row in _visibility_rows(package):
            if condition == _CORE_CONDITION:
                if row["visibility"] != "occluded":
                    continue
                condition_role = "core_occluded"
                scopes = [SCOPE_HIDDEN_MEAN, SCOPE_HIDDEN_SPREAD]
            elif condition == _NO_WALL_CONDITION:
                if row["visibility"] != "visible":
                    raise CaptureIntakeError(
                        f"{source.path}: no-wall control contains a hidden row."
                    )
                condition_role = "no_wall_visible_control"
                scopes = [SCOPE_VISIBLE_NO_WALL]
            else:
                raise CaptureIntakeError(
                    f"{source.path}: unsupported selection condition."
                )
            rows.append(
                {
                    "trajectory_id": row["trajectory_id"],
                    "model_frame_idx": row["model_frame_idx"],
                    "layout_id": layout_id,
                    "condition_role": condition_role,
                    "analysis_scopes": scopes,
                    "status": "accepted",
                }
            )
    return sorted(
        rows,
        key=lambda row: (row["trajectory_id"], row["model_frame_idx"]),
    )


def build_capture_intake_bundle(
    sources: Sequence[CaptureSource],
    *,
    source_branch: str,
    source_commit: str,
    artifact_id: str,
    code_sha: str,
) -> CaptureIntakeBundle:
    """Build deterministic C-only readiness evidence for Steps 6.1-6.6."""

    if (
        not isinstance(sources, Sequence)
        or isinstance(sources, (str, bytes))
        or not sources
    ):
        raise CaptureIntakeError("At least one capture source is required.")
    if any(not isinstance(source, CaptureSource) for source in sources):
        raise CaptureIntakeError(
            "Every capture source must be a CaptureSource instance."
        )
    _require_non_empty_string("source_branch", source_branch)
    _require_non_empty_string("artifact_id", artifact_id)
    if not is_hex_digest(source_commit, 40):
        raise CaptureIntakeError("source_commit must be a 40-character Git SHA.")
    if not is_hex_digest(code_sha, 40):
        raise CaptureIntakeError("code_sha must be a 40-character digest.")

    ordered_sources = sorted(sources, key=lambda source: source.path)
    source_paths: set[str] = set()
    trajectory_ids: set[str] = set()
    literal_hashes: set[str] = set()
    coordinate_frames: list[dict[str, Any]] = []
    package_records: list[dict[str, Any]] = []
    package_oracle_audits: list[dict[str, Any]] = []
    for source in ordered_sources:
        _validate_source(source)
        if source.path in source_paths:
            raise CaptureIntakeError(
                f"Duplicate capture source path: {source.path!r}."
            )
        source_paths.add(source.path)
        trajectory_id, _layout_id = _source_identity(source)
        if trajectory_id in trajectory_ids:
            raise CaptureIntakeError(
                f"Duplicate trajectory_id: {trajectory_id!r}."
            )
        trajectory_ids.add(trajectory_id)
        literal_hash = source.literal_sha256.lower()
        if literal_hash in literal_hashes:
            raise CaptureIntakeError("Capture literal hashes must be unique.")
        literal_hashes.add(literal_hash)

        package = source.package
        manifest = package["episode_manifest"]
        visibility_counts, transitions = _visibility_summary(package)
        coordinate_frame = build_signed_coordinate_frame(source)
        oracle_math_audit = audit_capture_package_oracle_math(package)
        package_oracle_audits.append(oracle_math_audit)
        if coordinate_frame is not None:
            coordinate_frames.append(coordinate_frame)
        public_oracle_audit = {
            key: value
            for key, value in oracle_math_audit.items()
            if not key.startswith("_")
        }
        package_records.append(
            {
                "path": source.path,
                "literal_sha256": literal_hash,
                "sidecar_sha256": source.sidecar_sha256.lower(),
                "accepted_manifest_hash": sha256_value(manifest),
                "trajectory_id": package["trajectory_id"],
                "episode_id": package["episode_id"],
                "layout_id": package["layout_id"],
                "condition": package["condition"],
                "regime": manifest["regime"],
                "status": manifest["status"],
                "superseded_by": manifest.get("superseded_by"),
                "frame_count": len(package["streams"]["frame_map"]),
                "visibility_counts": visibility_counts,
                "visibility_transitions": transitions,
                "classification": _classification(package),
                "oracle_math_audit": public_oracle_audit,
                "coordinate_frame_id": (
                    coordinate_frame["coordinate_frame_id"]
                    if coordinate_frame is not None
                    else None
                ),
                "coordinate_frame_hash": (
                    coordinate_frame["coordinate_frame_hash"]
                    if coordinate_frame is not None
                    else None
                ),
                "coordinate_frame_document_hash": (
                    sha256_value(coordinate_frame)
                    if coordinate_frame is not None
                    else None
                ),
            }
        )

    source_set = [
        {"path": record["path"], "literal_sha256": record["literal_sha256"]}
        for record in package_records
    ]
    input_manifest_hash = sha256_value(source_set)
    config_hash = hash_core_analysis_config()
    hidden_layouts = sorted(
        {
            record["layout_id"]
            for record in package_records
            if record["condition"] == _CORE_CONDITION
        }
    )
    control_layouts = sorted(
        {
            record["layout_id"]
            for record in package_records
            if record["condition"] == _NO_WALL_CONDITION
        }
    )
    fixed_tau_q_audit = audit_fixed_tau_q_sensitivity(package_oracle_audits)
    applicable_oracle_audits = [
        audit
        for audit in package_oracle_audits
        if audit["status"] != "not_applicable_no_object"
    ]
    oracle_invariant_failure_count = sum(
        len(audit["invariant_failures"])
        for audit in applicable_oracle_audits
    )
    oracle_max_error = max(
        (
            max(
                audit["max_iterative_closed_mean_error"],
                audit["max_iterative_closed_variance_error"],
            )
            for audit in applicable_oracle_audits
        ),
        default=0.0,
    )
    c_only_oracle_status = (
        "pass"
        if (
            applicable_oracle_audits
            and all(
                audit["status"] == "pass"
                for audit in applicable_oracle_audits
            )
            and fixed_tau_q_audit["comparison_count"] > 0
            and fixed_tau_q_audit["failure_count"] == 0
        )
        else "fail"
    )
    report = seal_artifact(
        {
            "artifact_type": "capture_intake_report",
            "artifact_id": artifact_id,
            "code_sha": code_sha,
            "config_hash": config_hash,
            "input_manifest_hash": input_manifest_hash,
            "capture_intake_schema_version": CAPTURE_INTAKE_SCHEMA_VERSION,
            "producer_role": "person_b",
            "source_role": "person_c",
            "source_branch": source_branch,
            "source_commit": source_commit.lower(),
            "status": "accepted_c_inputs_pending_person_a",
            "package_count": len(package_records),
            "coordinate_frame_count": len(coordinate_frames),
            "hidden_layout_ids": hidden_layouts,
            "visible_control_layout_ids": control_layouts,
            "package_records": package_records,
            "c_only_oracle_math_audit": {
                "status": c_only_oracle_status,
                "scope": (
                    "real_c_state_math_only_no_a_bound_target_artifact"
                ),
                "applicable_package_count": len(applicable_oracle_audits),
                "maximum_recursive_closed_form_error": oracle_max_error,
                "invariant_failure_count": oracle_invariant_failure_count,
                "fixed_tau_q_sensitivity": fixed_tau_q_audit,
            },
            "phase_readiness": {
                "person_c_capture_and_coordinate_evidence": "complete",
                "step_6_1": "blocked_on_person_a_activation_handoff",
                "step_6_2": (
                    "c_only_math_complete_final_target_blocked_on_person_a_"
                    "model_and_preprocess_hashes"
                ),
                "step_6_3": "blocked_on_person_a_activation_handoff",
                "step_6_4": (
                    "blocked_on_person_a_activations_and_additional_control_layouts"
                ),
                "step_6_5": "blocked_on_person_a_activation_handoff",
                "step_6_6": "blocked_on_person_a_person_d_person_e_receipts",
            },
            "scope_limits": {
                "hidden_layout_count": len(hidden_layouts),
                "visible_no_wall_layout_count": len(control_layouts),
                "visible_control_evidence": (
                    "plumbing_only_insufficient_control_layouts"
                    if len(control_layouts) < 5
                    else "eligible_for_grouped_oof"
                ),
            },
            "synthetic": False,
            "scientific_use": "pending_person_a_provenance_and_activations",
        }
    )

    selection_source = {
        "selection_source_schema_version": (
            CONDITION_SELECTION_SOURCE_SCHEMA_VERSION
        ),
        "status": "accepted",
        "selection_policy": "predeclared_before_probe_results",
        "producer_role": "person_b",
        "source_role": "person_c",
        "source_branch": source_branch,
        "source_commit": source_commit.lower(),
        "source_intake_artifact_hash": report["artifact_hash"],
        "source_capture_set_hash": input_manifest_hash,
        "rows": _selection_rows(ordered_sources),
    }
    # Reuse the production validator so a generated source cannot silently
    # diverge from the later pilot runner's accepted vocabulary.
    selections_from_condition_source(selection_source)

    return CaptureIntakeBundle(
        report=report,
        coordinate_frames=tuple(
            sorted(
                coordinate_frames,
                key=lambda frame: frame["coordinate_frame_id"],
            )
        ),
        condition_selection_source=selection_source,
    )
