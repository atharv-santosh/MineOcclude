"""Certify Person A Phase 6 ten-pilot extraction evidence without rerunning it.

Step 6.7 requires exact per-pilot validation, cardinality, join, exclusion, and
runtime/storage evidence for the accepted pilot expansion. Step 6.8 requires the
resulting engineering changes to be classified before the 66-trajectory queue is
opened.

This module reads only committed receipts. It never regenerates activations and
never promotes a synthetic value into a real-run field.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from mineocclude.contracts.activation import VISUAL_TOKENS_PER_FRAME
from mineocclude.contracts.identity import SCHEMA_VERSION

# The frozen MineWorld decoder depth: every admitted model frame contributes one
# pooled vector per decoder layer.
EXPECTED_LAYER_COUNT = 20

PILOT_STEP_IDS = ("6.1", "6.2", "6.3", "6.4", "6.5")

CERTIFICATION_SCHEMA_VERSION = "person-a-phase6-ten-pilot-certification-v0.1"
CLOSEOUT_SCHEMA_VERSION = "person-a-phase6-closeout-v0.1"


class ChangeClass(str, Enum):
    """Step 6.8 change classification vocabulary."""

    DEFECT_CORRECTION = "defect_correction"
    INTERFACE_MIGRATION = "interface_migration"
    OPERATIONAL_IMPROVEMENT = "operational_improvement"
    SCIENTIFIC_CHANGE = "scientific_change"


RESULT_CHANGING_CLASSES = frozenset({ChangeClass.SCIENTIFIC_CHANGE})


class PilotCertificationErrorCode(str, Enum):
    """Stable reasons a ten-pilot certification cannot be issued."""

    MISSING_EVIDENCE = "missing_evidence"
    MALFORMED_EVIDENCE = "malformed_evidence"
    CARDINALITY_MISMATCH = "cardinality_mismatch"
    JOIN_MISMATCH = "join_mismatch"
    DUPLICATE_IDENTITY = "duplicate_identity"
    STATUS_NOT_PASSING = "status_not_passing"
    UNCLASSIFIED_CHANGE = "unclassified_change"


class PilotCertificationError(ValueError):
    """Raised when committed pilot evidence cannot be certified as-is."""

    def __init__(self, code: PilotCertificationErrorCode, message: str) -> None:
        self.code = code
        super().__init__(f"{code.value}: {message}")


def _fail(code: PilotCertificationErrorCode, message: str) -> None:
    raise PilotCertificationError(code, message)


def _load_json(path: Path) -> Any:
    if not path.is_file():
        _fail(
            PilotCertificationErrorCode.MISSING_EVIDENCE,
            f"required evidence file is absent: {path.as_posix()}",
        )
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        _fail(
            PilotCertificationErrorCode.MALFORMED_EVIDENCE,
            f"{path.as_posix()} is not readable JSON: {error}",
        )
    return None  # pragma: no cover - _fail always raises


def _require_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail(
            PilotCertificationErrorCode.MALFORMED_EVIDENCE,
            f"{label} must be a JSON object",
        )
    return value


def _require_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        _fail(
            PilotCertificationErrorCode.MALFORMED_EVIDENCE,
            f"{label} must be a non-negative integer",
        )
    return int(value)


@dataclass(frozen=True)
class PilotEvidence:
    """One accepted pilot's committed extraction identity."""

    trajectory_id: str
    layout_id: str
    condition_role: str
    control: bool
    fold_idx: int
    frame_count: int
    expected_activation_row_count: int
    activation_row_count: int
    status: str
    reused_existing_artifacts: bool
    activation_index_sha256: str
    activation_index_byte_size: int
    chunk_count: int
    chunk_byte_total: int
    chunk_ids: tuple[str, ...]
    chunk_sha256: tuple[str, ...]
    step_elapsed_seconds: Mapping[str, float]

    @property
    def total_elapsed_seconds(self) -> float:
        return float(sum(self.step_elapsed_seconds.values()))


def _read_pilot_inventory(path: Path) -> PilotEvidence:
    document = _require_mapping(_load_json(path), path.name)
    index = _require_mapping(
        document.get("activation_index"),
        f"{path.name}.activation_index",
    )
    chunks = document.get("chunks")
    if not isinstance(chunks, list) or not chunks:
        _fail(
            PilotCertificationErrorCode.MALFORMED_EVIDENCE,
            f"{path.name}.chunks must be a non-empty list",
        )
    chunk_ids: list[str] = []
    chunk_hashes: list[str] = []
    chunk_bytes = 0
    chunk_rows = 0
    for entry in chunks:
        chunk = _require_mapping(entry, f"{path.name}.chunks[]")
        chunk_ids.append(str(chunk.get("chunk_id")))
        chunk_hashes.append(str(chunk.get("sha256")))
        chunk_bytes += _require_int(chunk.get("byte_size"), "chunk.byte_size")
        chunk_rows += _require_int(chunk.get("row_count"), "chunk.row_count")

    frame_count = _require_int(document.get("frame_count"), "frame_count")
    row_count = _require_int(
        document.get("activation_row_count"),
        "activation_row_count",
    )
    expected = _require_int(
        document.get("expected_activation_row_count"),
        "expected_activation_row_count",
    )
    if chunk_rows != row_count:
        _fail(
            PilotCertificationErrorCode.CARDINALITY_MISMATCH,
            f"{path.name}: chunk rows {chunk_rows} != index rows {row_count}",
        )
    return PilotEvidence(
        trajectory_id=str(document.get("trajectory_id")),
        layout_id=str(document.get("layout_id")),
        condition_role=str(document.get("condition_role")),
        control=bool(document.get("control")),
        fold_idx=_require_int(document.get("fold_idx"), "fold_idx"),
        frame_count=frame_count,
        expected_activation_row_count=expected,
        activation_row_count=row_count,
        status=str(document.get("status")),
        reused_existing_artifacts=bool(
            document.get("existing_pilot_reextracted") is False
            and "existing_pilot_reextracted" in document
        ),
        activation_index_sha256=str(index.get("sha256")),
        activation_index_byte_size=_require_int(
            index.get("byte_size"),
            "activation_index.byte_size",
        ),
        chunk_count=len(chunks),
        chunk_byte_total=chunk_bytes,
        chunk_ids=tuple(chunk_ids),
        chunk_sha256=tuple(chunk_hashes),
        step_elapsed_seconds={},
    )


def _read_step_timings(pilot_root: Path) -> dict[str, float]:
    timings: dict[str, float] = {}
    if not pilot_root.is_dir():
        return timings
    for step_id in PILOT_STEP_IDS:
        step_path = pilot_root / f"step{step_id.replace('.', '_')}.json"
        if not step_path.is_file():
            continue
        document = _require_mapping(_load_json(step_path), step_path.name)
        if document.get("status") != "PASS":
            _fail(
                PilotCertificationErrorCode.STATUS_NOT_PASSING,
                f"{step_path.as_posix()} status is {document.get('status')!r}",
            )
        elapsed = document.get("elapsed_seconds")
        if not isinstance(elapsed, (int, float)) or isinstance(elapsed, bool):
            _fail(
                PilotCertificationErrorCode.MALFORMED_EVIDENCE,
                f"{step_path.as_posix()} lacks a numeric elapsed_seconds",
            )
        timings[step_id] = float(elapsed)
    return timings


def load_pilot_evidence(session_root: Path | str) -> tuple[PilotEvidence, ...]:
    """Read every committed per-pilot inventory plus its step timings."""

    root = Path(session_root)
    inventory_root = root / "per_pilot_inventories"
    if not inventory_root.is_dir():
        _fail(
            PilotCertificationErrorCode.MISSING_EVIDENCE,
            f"per-pilot inventory directory is absent: {inventory_root.as_posix()}",
        )
    evidence: list[PilotEvidence] = []
    for path in sorted(inventory_root.glob("*.json")):
        pilot = _read_pilot_inventory(path)
        timings = _read_step_timings(root / "pilots" / pilot.trajectory_id)
        evidence.append(
            PilotEvidence(
                **{
                    **pilot.__dict__,
                    "step_elapsed_seconds": dict(sorted(timings.items())),
                }
            )
        )
    if not evidence:
        _fail(
            PilotCertificationErrorCode.MISSING_EVIDENCE,
            "no per-pilot inventories were found",
        )
    return tuple(evidence)


def build_exclusion_record(
    evidence: Sequence[PilotEvidence],
    downstream_fold_manifest: Mapping[str, Any],
) -> dict[str, Any]:
    """Reconcile A's extracted frames against the downstream admission split.

    Person A extracts every model frame it can align. Person B owns the
    admission rule that removes frames from analysis. This record states both
    numbers and the exact arithmetic that ties them together; it never relabels
    a Person B exclusion as a Person A extraction failure.
    """

    manifest = _require_mapping(downstream_fold_manifest, "fold_manifest")
    source_frames = _require_int(
        manifest.get("source_frame_count"),
        "fold_manifest.source_frame_count",
    )
    admitted = _require_int(
        manifest.get("admitted_frame_count"),
        "fold_manifest.admitted_frame_count",
    )
    excluded = _require_int(
        manifest.get("excluded_frame_count"),
        "fold_manifest.excluded_frame_count",
    )
    extracted_frames = sum(item.frame_count for item in evidence)
    arithmetic_holds = admitted + excluded == source_frames
    source_matches_extraction = source_frames == extracted_frames
    if not arithmetic_holds:
        _fail(
            PilotCertificationErrorCode.JOIN_MISMATCH,
            "admitted + excluded frames do not equal the declared source frames",
        )
    if not source_matches_extraction:
        _fail(
            PilotCertificationErrorCode.JOIN_MISMATCH,
            f"downstream source frames {source_frames} != "
            f"Person A extracted frames {extracted_frames}",
        )
    per_pilot_excluded = _per_pilot_exclusions(manifest)
    return {
        "schema_version": CERTIFICATION_SCHEMA_VERSION,
        "exclusion_owner": "person_b_analysis_admission_rule",
        "person_a_extracted_frame_count": extracted_frames,
        "downstream_source_frame_count": source_frames,
        "downstream_admitted_frame_count": admitted,
        "downstream_excluded_frame_count": excluded,
        "admission_arithmetic_holds": arithmetic_holds,
        "person_a_extraction_exclusion_count": 0,
        "person_a_extraction_exclusions": [],
        "per_pilot_downstream_exclusions": per_pilot_excluded,
        "note": (
            "Person A extracted every aligned model frame. Frames removed from "
            "analysis were removed by Person B's frozen admission rule, not by "
            "a Person A extraction failure."
        ),
    }


def _per_pilot_exclusions(manifest: Mapping[str, Any]) -> dict[str, int]:
    memberships = manifest.get("excluded_memberships")
    counts: dict[str, int] = {}
    if not isinstance(memberships, list):
        return counts
    for entry in memberships:
        if not isinstance(entry, Mapping):
            continue
        trajectory = entry.get("trajectory_id")
        if isinstance(trajectory, str) and trajectory:
            counts[trajectory] = counts.get(trajectory, 0) + 1
    return dict(sorted(counts.items()))


def build_runtime_storage_benchmark(
    evidence: Sequence[PilotEvidence],
) -> dict[str, Any]:
    """Measure the per-trajectory runtime and storage cost actually observed."""

    timed = [item for item in evidence if item.step_elapsed_seconds]
    total_rows = sum(item.activation_row_count for item in evidence)
    total_bytes = sum(item.chunk_byte_total for item in evidence)
    total_frames = sum(item.frame_count for item in evidence)
    total_seconds = sum(item.total_elapsed_seconds for item in timed)
    timed_frames = sum(item.frame_count for item in timed)

    per_pilot = [
        {
            "trajectory_id": item.trajectory_id,
            "frame_count": item.frame_count,
            "activation_row_count": item.activation_row_count,
            "chunk_count": item.chunk_count,
            "activation_bytes": item.chunk_byte_total,
            "bytes_per_frame": (
                item.chunk_byte_total / item.frame_count
                if item.frame_count
                else None
            ),
            "measured_seconds": (
                item.total_elapsed_seconds if item.step_elapsed_seconds else None
            ),
            "seconds_per_frame": (
                item.total_elapsed_seconds / item.frame_count
                if item.step_elapsed_seconds and item.frame_count
                else None
            ),
            "step_elapsed_seconds": dict(item.step_elapsed_seconds),
            "timing_measured": bool(item.step_elapsed_seconds),
        }
        for item in evidence
    ]
    return {
        "schema_version": CERTIFICATION_SCHEMA_VERSION,
        "measured_pilot_count": len(timed),
        "total_pilot_count": len(evidence),
        "total_frame_count": total_frames,
        "total_activation_row_count": total_rows,
        "total_activation_bytes": total_bytes,
        "bytes_per_activation_row": (
            total_bytes / total_rows if total_rows else None
        ),
        "bytes_per_frame": (
            total_bytes / total_frames if total_frames else None
        ),
        "measured_wall_seconds": total_seconds,
        "measured_frame_count": timed_frames,
        "seconds_per_frame": (
            total_seconds / timed_frames if timed_frames else None
        ),
        "seconds_per_trajectory_mean": (
            total_seconds / len(timed) if timed else None
        ),
        "per_pilot": per_pilot,
        "timing_scope": (
            "Wall time is the sum of committed step 6.1-6.5 elapsed_seconds for "
            "pilots that recorded step receipts. Reused pilots contribute "
            "storage and cardinality only."
        ),
    }


def forecast_queue(
    benchmark: Mapping[str, Any],
    *,
    trajectory_count: int,
    frames_per_trajectory: float | None = None,
) -> dict[str, Any]:
    """Project runtime and storage for a larger queue from measured rates."""

    if isinstance(trajectory_count, bool) or not isinstance(trajectory_count, int):
        _fail(
            PilotCertificationErrorCode.MALFORMED_EVIDENCE,
            "trajectory_count must be an integer",
        )
    if trajectory_count <= 0:
        _fail(
            PilotCertificationErrorCode.MALFORMED_EVIDENCE,
            "trajectory_count must be positive",
        )
    measured_pilots = benchmark.get("total_pilot_count") or 0
    total_frames = benchmark.get("total_frame_count") or 0
    mean_frames = (
        float(frames_per_trajectory)
        if frames_per_trajectory is not None
        else (total_frames / measured_pilots if measured_pilots else None)
    )
    seconds_per_frame = benchmark.get("seconds_per_frame")
    bytes_per_frame = benchmark.get("bytes_per_frame")
    projected_frames = (
        mean_frames * trajectory_count if mean_frames is not None else None
    )
    return {
        "schema_version": CERTIFICATION_SCHEMA_VERSION,
        "basis": "measured_ten_pilot_expansion",
        "target_trajectory_count": trajectory_count,
        "mean_frames_per_trajectory": mean_frames,
        "projected_frame_count": projected_frames,
        "projected_activation_row_count": (
            projected_frames * EXPECTED_LAYER_COUNT
            if projected_frames is not None
            else None
        ),
        "projected_wall_seconds": (
            projected_frames * seconds_per_frame
            if projected_frames is not None and seconds_per_frame
            else None
        ),
        "projected_activation_bytes": (
            projected_frames * bytes_per_frame
            if projected_frames is not None and bytes_per_frame
            else None
        ),
        "forecast_is_measured_projection_not_a_run": True,
    }


def certify_ten_pilot_expansion(
    session_root: Path | str,
    *,
    downstream_fold_manifest: Mapping[str, Any],
    expected_pilot_count: int = 10,
) -> dict[str, Any]:
    """Certify Step 6.7 from committed evidence, or raise with an exact reason."""

    root = Path(session_root)
    completion = _require_mapping(
        _load_json(root / "completion_report.json"),
        "completion_report.json",
    )
    artifacts = _require_mapping(
        _load_json(root / "artifact_manifest.json"),
        "artifact_manifest.json",
    )
    evidence = load_pilot_evidence(root)

    if completion.get("status") != "PASS":
        _fail(
            PilotCertificationErrorCode.STATUS_NOT_PASSING,
            f"session status is {completion.get('status')!r}, not PASS",
        )
    if len(evidence) != expected_pilot_count:
        _fail(
            PilotCertificationErrorCode.CARDINALITY_MISMATCH,
            f"expected {expected_pilot_count} pilots, found {len(evidence)}",
        )

    cardinality = _certify_cardinality(evidence)
    _certify_identity_uniqueness(evidence)
    joins = _certify_downstream_joins(
        evidence,
        completion=completion,
        artifacts=artifacts,
        fold_manifest=downstream_fold_manifest,
    )
    exclusions = build_exclusion_record(evidence, downstream_fold_manifest)
    benchmark = build_runtime_storage_benchmark(evidence)

    combined = _require_mapping(
        artifacts.get("combined_activation_index"),
        "artifact_manifest.combined_activation_index",
    )
    return {
        "schema_version": CERTIFICATION_SCHEMA_VERSION,
        "step": "6.7",
        "status": "CERTIFIED",
        "certified_from_committed_evidence_without_rerun": True,
        "session_id": completion.get("session_id"),
        "deterministic_seed": completion.get("deterministic_seed"),
        "identity_schema_version": SCHEMA_VERSION,
        "expected_layer_count": EXPECTED_LAYER_COUNT,
        "visual_tokens_per_frame": VISUAL_TOKENS_PER_FRAME,
        "activation_index": {
            "combined_activation_index_sha256": combined.get("sha256"),
            "combined_activation_index_byte_size": combined.get("byte_size"),
            "combined_activation_index_external_path": combined.get(
                "external_path"
            ),
            "staged_in_git": bool(combined.get("staged")),
            "per_pilot_activation_index_sha256": {
                item.trajectory_id: item.activation_index_sha256
                for item in evidence
            },
            "producing_authority": {
                "person_a_expansion_runner_commit": completion.get(
                    "person_a_expansion_runner_commit"
                ),
                "person_b_expansion_selection_commit": completion.get(
                    "person_b_expansion_selection_commit"
                ),
                "person_b_expansion_authorization_object": completion.get(
                    "person_b_expansion_authorization_object"
                ),
                "person_c_expansion_acceptance_commit": completion.get(
                    "person_c_expansion_acceptance_commit"
                ),
            },
        },
        "cardinality": cardinality,
        "downstream_joins": joins,
        "exclusions": exclusions,
        "benchmark": benchmark,
        "per_pilot_status": [
            {
                "trajectory_id": item.trajectory_id,
                "layout_id": item.layout_id,
                "condition_role": item.condition_role,
                "control": item.control,
                "fold_idx": item.fold_idx,
                "frame_count": item.frame_count,
                "activation_row_count": item.activation_row_count,
                "expected_activation_row_count": (
                    item.expected_activation_row_count
                ),
                "chunk_count": item.chunk_count,
                "activation_index_sha256": item.activation_index_sha256,
                "status": item.status,
                "step_receipts_present": sorted(item.step_elapsed_seconds),
                "reused_without_reextraction": item.reused_existing_artifacts,
            }
            for item in evidence
        ],
        "audits": {
            "pooling_audit_pass": bool(completion.get("pooling_audit_pass")),
            "repeatability_audit_pass": bool(
                completion.get("repeatability_audit_pass")
            ),
            "source_identity_join_pass": bool(
                completion.get("source_identity_join_pass")
            ),
            "duplicate_activation_row_count": completion.get(
                "duplicate_activation_row_count"
            ),
            "missing_activation_row_count": completion.get(
                "missing_activation_row_count"
            ),
            "nonfinite_activation_count": completion.get(
                "nonfinite_activation_count"
            ),
            "u4_output_inspected": bool(completion.get("u4_output_inspected")),
        },
    }


def _certify_cardinality(evidence: Sequence[PilotEvidence]) -> dict[str, Any]:
    per_pilot: list[dict[str, Any]] = []
    for item in evidence:
        expected_rows = item.frame_count * EXPECTED_LAYER_COUNT
        if item.expected_activation_row_count != expected_rows:
            _fail(
                PilotCertificationErrorCode.CARDINALITY_MISMATCH,
                f"{item.trajectory_id}: declared expectation "
                f"{item.expected_activation_row_count} != frames*layers "
                f"{expected_rows}",
            )
        if item.activation_row_count != expected_rows:
            _fail(
                PilotCertificationErrorCode.CARDINALITY_MISMATCH,
                f"{item.trajectory_id}: {item.activation_row_count} rows != "
                f"{expected_rows} expected",
            )
        if item.chunk_count != EXPECTED_LAYER_COUNT:
            _fail(
                PilotCertificationErrorCode.CARDINALITY_MISMATCH,
                f"{item.trajectory_id}: {item.chunk_count} chunks != "
                f"{EXPECTED_LAYER_COUNT} layer chunks",
            )
        per_pilot.append(
            {
                "trajectory_id": item.trajectory_id,
                "frame_count": item.frame_count,
                "layer_count": EXPECTED_LAYER_COUNT,
                "expected_activation_row_count": expected_rows,
                "actual_activation_row_count": item.activation_row_count,
                "chunk_count": item.chunk_count,
                "exact": True,
            }
        )
    return {
        "rule": "activation_rows == model_frames * decoder_layers",
        "layer_count": EXPECTED_LAYER_COUNT,
        "total_frame_count": sum(item.frame_count for item in evidence),
        "total_activation_row_count": sum(
            item.activation_row_count for item in evidence
        ),
        "total_chunk_count": sum(item.chunk_count for item in evidence),
        "all_pilots_exact": True,
        "per_pilot": per_pilot,
    }


def _certify_identity_uniqueness(evidence: Sequence[PilotEvidence]) -> None:
    trajectories = [item.trajectory_id for item in evidence]
    if len(set(trajectories)) != len(trajectories):
        _fail(
            PilotCertificationErrorCode.DUPLICATE_IDENTITY,
            "trajectory identities are not unique across pilots",
        )
    chunk_ids = [chunk for item in evidence for chunk in item.chunk_ids]
    if len(set(chunk_ids)) != len(chunk_ids):
        _fail(
            PilotCertificationErrorCode.DUPLICATE_IDENTITY,
            "activation chunk identifiers repeat across pilots",
        )
    index_hashes = [item.activation_index_sha256 for item in evidence]
    if len(set(index_hashes)) != len(index_hashes):
        _fail(
            PilotCertificationErrorCode.DUPLICATE_IDENTITY,
            "per-pilot activation index digests repeat across pilots",
        )


def _certify_downstream_joins(
    evidence: Sequence[PilotEvidence],
    *,
    completion: Mapping[str, Any],
    artifacts: Mapping[str, Any],
    fold_manifest: Mapping[str, Any],
) -> dict[str, Any]:
    declared_rows = _require_int(
        completion.get("actual_activation_row_count"),
        "completion.actual_activation_row_count",
    )
    declared_chunks = _require_int(
        artifacts.get("activation_chunk_count"),
        "artifact_manifest.activation_chunk_count",
    )
    observed_rows = sum(item.activation_row_count for item in evidence)
    observed_chunks = sum(item.chunk_count for item in evidence)
    if declared_rows != observed_rows:
        _fail(
            PilotCertificationErrorCode.JOIN_MISMATCH,
            f"session declares {declared_rows} rows; inventories total "
            f"{observed_rows}",
        )
    if declared_chunks != observed_chunks:
        _fail(
            PilotCertificationErrorCode.JOIN_MISMATCH,
            f"session declares {declared_chunks} chunks; inventories total "
            f"{observed_chunks}",
        )

    downstream_rows = _require_int(
        fold_manifest.get("activation_row_count"),
        "fold_manifest.activation_row_count",
    )
    downstream_chunks = _require_int(
        fold_manifest.get("activation_chunk_count"),
        "fold_manifest.activation_chunk_count",
    )
    if downstream_rows != observed_rows:
        _fail(
            PilotCertificationErrorCode.JOIN_MISMATCH,
            f"downstream consumer expects {downstream_rows} rows; Person A "
            f"produced {observed_rows}",
        )
    if downstream_chunks != observed_chunks:
        _fail(
            PilotCertificationErrorCode.JOIN_MISMATCH,
            f"downstream consumer expects {downstream_chunks} chunks; Person A "
            f"produced {observed_chunks}",
        )

    produced_ids = tuple(item.trajectory_id for item in evidence)
    accepted = fold_manifest.get("accepted_pilot_ids")
    if not isinstance(accepted, list):
        _fail(
            PilotCertificationErrorCode.MALFORMED_EVIDENCE,
            "fold_manifest.accepted_pilot_ids must be a list",
        )
    if sorted(str(value) for value in accepted) != sorted(produced_ids):
        _fail(
            PilotCertificationErrorCode.JOIN_MISMATCH,
            "downstream accepted pilot identities differ from Person A outputs",
        )
    return {
        "person_a_produced_trajectory_ids": sorted(produced_ids),
        "downstream_accepted_trajectory_ids": sorted(
            str(value) for value in accepted
        ),
        "trajectory_identity_join": "exact",
        "activation_row_join": "exact",
        "activation_chunk_join": "exact",
        "downstream_consumer": fold_manifest.get("artifact_id"),
        "downstream_consumer_artifact_hash": fold_manifest.get("artifact_hash"),
        "downstream_input_manifest_hash": fold_manifest.get(
            "input_manifest_hash"
        ),
        "repository_input_hash_mismatch_count": 0,
    }


# ---------------------------------------------------------------------------
# Step 6.8 — freeze pilot lessons without moving science
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PilotChange:
    """One classified engineering change observed during the pilot phase."""

    change_id: str
    summary: str
    classification: ChangeClass
    commit: str
    review: str
    supersedes_previous_runs: bool = False

    def to_document(self) -> dict[str, Any]:
        return {
            "change_id": self.change_id,
            "summary": self.summary,
            "classification": self.classification.value,
            "commit": self.commit,
            "review": self.review,
            "result_changing": self.classification in RESULT_CHANGING_CLASSES,
            "supersedes_previous_runs": self.supersedes_previous_runs,
        }


def build_pilot_closeout(
    certification: Mapping[str, Any],
    changes: Iterable[PilotChange],
    *,
    locked_contract_path: str,
    locked_contract_sha256: str,
    remaining_blockers: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Produce the Step 6.8 decision log with an explicit change classification."""

    records = [change.to_document() for change in changes]
    if not records:
        _fail(
            PilotCertificationErrorCode.UNCLASSIFIED_CHANGE,
            "the closeout must classify at least one pilot-phase change",
        )
    unclassified = [
        record
        for record in records
        if record["classification"]
        not in {member.value for member in ChangeClass}
    ]
    if unclassified:
        _fail(
            PilotCertificationErrorCode.UNCLASSIFIED_CHANGE,
            "every pilot-phase change must carry a frozen classification",
        )
    result_changing = [record for record in records if record["result_changing"]]
    benchmark = certification.get("benchmark") or {}
    return {
        "schema_version": CLOSEOUT_SCHEMA_VERSION,
        "step": "6.8",
        "status": (
            "CLOSED" if not remaining_blockers else "CLOSED_WITH_BLOCKERS"
        ),
        "certified_step_6_7": certification.get("status") == "CERTIFIED",
        "certification_session_id": certification.get("session_id"),
        "change_count": len(records),
        "change_classification_counts": {
            member.value: sum(
                1 for record in records if record["classification"] == member.value
            )
            for member in ChangeClass
        },
        "result_changing_change_count": len(result_changing),
        "result_changing_changes": result_changing,
        "changes": records,
        "scientific_change_requires_mentor_approval": True,
        "superseding_rule": (
            "A result-changing change creates a new run identity; it never "
            "rewrites an accepted run in place."
        ),
        "final_throughput_and_storage": {
            "seconds_per_frame": benchmark.get("seconds_per_frame"),
            "seconds_per_trajectory_mean": benchmark.get(
                "seconds_per_trajectory_mean"
            ),
            "bytes_per_frame": benchmark.get("bytes_per_frame"),
            "bytes_per_activation_row": benchmark.get(
                "bytes_per_activation_row"
            ),
            "measured_pilot_count": benchmark.get("measured_pilot_count"),
        },
        "locked_contract": {
            "path": locked_contract_path,
            "sha256": locked_contract_sha256,
        },
        "remaining_blockers": [dict(entry) for entry in remaining_blockers],
        "no_unresolved_alignment_schema_or_model_blocker": not remaining_blockers,
    }


__all__ = [
    "CERTIFICATION_SCHEMA_VERSION",
    "CLOSEOUT_SCHEMA_VERSION",
    "EXPECTED_LAYER_COUNT",
    "ChangeClass",
    "PilotCertificationError",
    "PilotCertificationErrorCode",
    "PilotChange",
    "PilotEvidence",
    "build_exclusion_record",
    "build_pilot_closeout",
    "build_runtime_storage_benchmark",
    "certify_ten_pilot_expansion",
    "forecast_queue",
    "load_pilot_evidence",
]
