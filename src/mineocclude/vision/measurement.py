"""Reappearance, displacement, and E-to-B measurement production."""

from __future__ import annotations

import copy
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from statistics import median
from typing import Any

from mineocclude.analysis.manifests import sha256_value
from mineocclude.contracts.analysis_inputs import (
    MEASUREMENT_INPUT_SCHEMA_VERSION,
    validate_measurement_input,
)
from mineocclude.contracts.identity import SCHEMA_VERSION
from mineocclude.contracts.rollout_registry import validate_rollout_registry_bundle
from mineocclude.baselines.u4_control_matrix import ControlKind, build_control_matrix

from .config import (
    DEFAULT_PERSON_E_CONFIG_PATH,
    hash_person_e_config,
    require_live_ready_person_e_config,
)
from .ssim import SsimResult


class MeasurementError(ValueError):
    """Raised when rollout measurement would conflate or misjoin outcomes."""


EVIDENCE_INPUT_SCHEMA_VERSION = "person-e-u4-evidence-input-v0.1"
MEASUREMENT_EVIDENCE_SCHEMA_VERSION = "person-e-measurement-evidence-v0.2"
PHASE1_ROLLOUT_MEASUREMENT_FIXTURE_SCHEMA_VERSION = (
    "person-e-rollout-measurement-fixture-v1.0"
)
PHASE1_SCENARIO_KINDS = frozenset(
    {
        "alpha_zero",
        "positive_signed_dose",
        "negative_signed_dose",
        "random_control",
        "non_persistence",
        "missing_frame",
        "misaligned_frame",
    }
)


def _is_exact_hex_digest(value: Any, length: int) -> bool:
    return (
        isinstance(value, str)
        and len(value) == length
        and all(character in "0123456789abcdefABCDEF" for character in value)
    )


def _finite(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


@dataclass(frozen=True)
class FrameLocalization:
    """A detector/homography result at one rollout frame."""

    frame_idx: int
    wall_parallel_blocks: float | None
    detection_valid: bool
    bounding_box_xyxy: tuple[int, int, int, int] | None = None
    rejection_reason: str | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.frame_idx, int)
            or isinstance(self.frame_idx, bool)
            or self.frame_idx < 0
        ):
            raise MeasurementError("frame_idx must be a non-negative integer.")
        if not isinstance(self.detection_valid, bool):
            raise MeasurementError("detection_valid must be boolean.")
        if self.detection_valid:
            if not _finite(self.wall_parallel_blocks):
                raise MeasurementError(
                    "Valid detections require a finite wall-parallel coordinate."
                )
            if self.rejection_reason is not None:
                raise MeasurementError(
                    "Valid detections cannot carry a rejection_reason."
                )
        elif self.wall_parallel_blocks is not None:
            raise MeasurementError(
                "Invalid detections cannot carry a world coordinate."
            )
        elif (
            not isinstance(self.rejection_reason, str)
            or not self.rejection_reason.strip()
        ):
            raise MeasurementError(
                "Invalid detections require a non-empty rejection_reason."
            )
        if self.bounding_box_xyxy is not None:
            if not self.detection_valid:
                raise MeasurementError(
                    "Invalid detections cannot carry a localization bounding box."
                )
            if (
                not isinstance(self.bounding_box_xyxy, tuple)
                or len(self.bounding_box_xyxy) != 4
                or any(
                    not isinstance(value, int) or isinstance(value, bool)
                    for value in self.bounding_box_xyxy
                )
            ):
                raise MeasurementError(
                    "bounding_box_xyxy must be null or four integers."
                )
            x_min, y_min, x_max, y_max = self.bounding_box_xyxy
            if not (0 <= x_min < x_max and 0 <= y_min < y_max):
                raise MeasurementError("bounding_box_xyxy must have positive area.")


@dataclass(frozen=True)
class ReappearanceResult:
    """Primary and sensitivity reappearance outcomes for one clip."""

    status: str
    reveal_frame_idx: int
    primary_frame_idx: int | None
    detection_delay_frames: int | None
    primary_wall_parallel_blocks: float | None
    sensitivity_wall_parallel_blocks: float | None
    first_valid_frame_indices: tuple[int, ...]
    valid_post_reveal_count: int
    outcome_detail: str | None

    def __post_init__(self) -> None:
        if self.status not in {"measured", "non_persistence"}:
            raise MeasurementError("Unknown reappearance status.")
        if (
            not isinstance(self.reveal_frame_idx, int)
            or isinstance(self.reveal_frame_idx, bool)
            or self.reveal_frame_idx < 0
        ):
            raise MeasurementError("reveal_frame_idx must be a non-negative integer.")
        if (
            not isinstance(self.valid_post_reveal_count, int)
            or isinstance(self.valid_post_reveal_count, bool)
            or self.valid_post_reveal_count < 0
        ):
            raise MeasurementError("valid_post_reveal_count cannot be negative.")
        if (
            not isinstance(self.first_valid_frame_indices, tuple)
            or any(
                not isinstance(frame_idx, int)
                or isinstance(frame_idx, bool)
                or frame_idx <= self.reveal_frame_idx
                for frame_idx in self.first_valid_frame_indices
            )
            or tuple(sorted(self.first_valid_frame_indices))
            != self.first_valid_frame_indices
        ):
            raise MeasurementError("first_valid_frame_indices are invalid.")
        if (
            self.sensitivity_wall_parallel_blocks is not None
            and not _finite(self.sensitivity_wall_parallel_blocks)
        ):
            raise MeasurementError("Sensitivity coordinate must be finite or null.")
        if self.status == "measured":
            if (
                not isinstance(self.primary_frame_idx, int)
                or self.primary_frame_idx <= self.reveal_frame_idx
                or self.detection_delay_frames
                != self.primary_frame_idx - self.reveal_frame_idx
                or not _finite(self.primary_wall_parallel_blocks)
                or self.outcome_detail is not None
            ):
                raise MeasurementError("Measured reappearance fields are inconsistent.")
        elif (
            self.primary_frame_idx is not None
            or self.detection_delay_frames is not None
            or self.primary_wall_parallel_blocks is not None
            or not isinstance(self.outcome_detail, str)
            or not self.outcome_detail
        ):
            raise MeasurementError("Non-persistence fields are inconsistent.")

    @property
    def measured(self) -> bool:
        return self.status == "measured"

    def to_record(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "reveal_frame_idx": self.reveal_frame_idx,
            "primary_frame_idx": self.primary_frame_idx,
            "detection_delay_frames": self.detection_delay_frames,
            "primary_wall_parallel_blocks": self.primary_wall_parallel_blocks,
            "sensitivity_wall_parallel_blocks": self.sensitivity_wall_parallel_blocks,
            "first_valid_frame_indices": list(self.first_valid_frame_indices),
            "valid_post_reveal_count": self.valid_post_reveal_count,
            "outcome_detail": self.outcome_detail,
        }


def find_reappearance(
    localizations: Sequence[FrameLocalization],
    *,
    reveal_frame_idx: int,
    required_consecutive_frames: int = 2,
    sensitivity_first_valid_frames: int = 3,
) -> ReappearanceResult:
    """Find the first post-reveal detection valid on consecutive frames."""

    if (
        not isinstance(localizations, Sequence)
        or isinstance(localizations, (str, bytes))
        or any(not isinstance(item, FrameLocalization) for item in localizations)
    ):
        raise MeasurementError("localizations must contain FrameLocalization records.")
    if (
        not isinstance(reveal_frame_idx, int)
        or isinstance(reveal_frame_idx, bool)
        or reveal_frame_idx < 0
    ):
        raise MeasurementError("reveal_frame_idx must be a non-negative integer.")
    for name, value in (
        ("required_consecutive_frames", required_consecutive_frames),
        ("sensitivity_first_valid_frames", sensitivity_first_valid_frames),
    ):
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise MeasurementError(f"{name} must be a positive integer.")
    ordered = sorted(localizations, key=lambda item: item.frame_idx)
    if not ordered:
        raise MeasurementError(
            "Missing localization records cannot be classified as non-persistence."
        )
    frame_indices = [item.frame_idx for item in ordered]
    if len(frame_indices) != len(set(frame_indices)):
        raise MeasurementError("Frame localization identities must be unique.")
    if any(
        current != previous + 1
        for previous, current in zip(frame_indices, frame_indices[1:])
    ):
        raise MeasurementError(
            "Localization frame identities must be consecutive; interpolation is forbidden."
        )
    post_reveal = [item for item in ordered if item.frame_idx > reveal_frame_idx]
    if not post_reveal:
        raise MeasurementError(
            "Missing post-reveal frames cannot be classified as non-persistence."
        )
    if post_reveal[0].frame_idx != reveal_frame_idx + 1:
        raise MeasurementError(
            "Post-reveal coverage must begin at reveal_frame_idx + 1; "
            "omitted frames cannot be treated as detector negatives."
        )
    valid = [item for item in post_reveal if item.detection_valid]
    sensitivity_coordinate = None
    if len(valid) >= sensitivity_first_valid_frames:
        sensitivity_coordinate = float(median(
            [
                float(item.wall_parallel_blocks)
                for item in valid[:sensitivity_first_valid_frames]
                if item.wall_parallel_blocks is not None
            ]
        ))

    primary: FrameLocalization | None = None
    valid_by_frame = {item.frame_idx: item for item in valid}
    for item in valid:
        if all(
            item.frame_idx + offset in valid_by_frame
            for offset in range(required_consecutive_frames)
        ):
            primary = item
            break
    first_indices = tuple(item.frame_idx for item in valid[:sensitivity_first_valid_frames])
    if primary is None:
        return ReappearanceResult(
            status="non_persistence",
            reveal_frame_idx=reveal_frame_idx,
            primary_frame_idx=None,
            detection_delay_frames=None,
            primary_wall_parallel_blocks=None,
            sensitivity_wall_parallel_blocks=sensitivity_coordinate,
            first_valid_frame_indices=first_indices,
            valid_post_reveal_count=len(valid),
            outcome_detail="no_post_reveal_detection_valid_for_required_consecutive_frames",
        )
    return ReappearanceResult(
        status="measured",
        reveal_frame_idx=reveal_frame_idx,
        primary_frame_idx=primary.frame_idx,
        detection_delay_frames=primary.frame_idx - reveal_frame_idx,
        primary_wall_parallel_blocks=float(primary.wall_parallel_blocks),
        sensitivity_wall_parallel_blocks=sensitivity_coordinate,
        first_valid_frame_indices=first_indices,
        valid_post_reveal_count=len(valid),
        outcome_detail=None,
    )


def find_alpha_zero_matches(
    rollout_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Mapping[str, Any] | None]:
    """Map rollout IDs to unique event/seed-matched alpha-zero rows when present.

    A missing control is a per-rollout measurement exclusion, not a reason to
    suppress unrelated generation-failure or already-excluded rows.
    """

    if (
        not isinstance(rollout_rows, Sequence)
        or isinstance(rollout_rows, (str, bytes))
        or not rollout_rows
        or any(not isinstance(row, Mapping) for row in rollout_rows)
    ):
        raise MeasurementError("rollout_rows must be a sequence of mappings.")
    baselines: dict[tuple[str, int], Mapping[str, Any]] = {}
    seen_rollout_ids: set[str] = set()
    for index, row in enumerate(rollout_rows):
        for field in (
            "rollout_id",
            "event_id",
            "seed",
            "control_type",
            "status",
            "outcome",
        ):
            if field not in row:
                raise MeasurementError(f"Rollout row {index} is missing {field}.")
        rollout_id = row["rollout_id"]
        event_id = row["event_id"]
        seed = row["seed"]
        if not isinstance(rollout_id, str) or not rollout_id:
            raise MeasurementError("rollout_id must be non-empty.")
        if rollout_id in seen_rollout_ids:
            raise MeasurementError("rollout_id values must be unique.")
        seen_rollout_ids.add(rollout_id)
        if not isinstance(event_id, str) or not event_id:
            raise MeasurementError("event_id must be non-empty.")
        if not isinstance(seed, int) or isinstance(seed, bool):
            raise MeasurementError("seed must be an integer.")
        if (
            row["control_type"] == "alpha_zero"
            and row["status"] == "accepted"
            and row["outcome"] == "measurable_continuation"
        ):
            key = (event_id, seed)
            if key in baselines:
                raise MeasurementError(
                    f"Duplicate alpha-zero rollout for event/seed {key!r}."
                )
            baselines[key] = row
    matches: dict[str, Mapping[str, Any] | None] = {}
    for row in rollout_rows:
        key = (row["event_id"], row["seed"])
        matches[row["rollout_id"]] = baselines.get(key)
    return matches


def build_measurement_evidence(
    payload: Mapping[str, Any],
    *,
    evidence_id: str,
    rollout_id: str,
    producer_run_id: str,
    code_sha: str,
    accepted_rollout_manifest_hash: str,
    accepted_registry_hash: str,
    config_path: Path | str = DEFAULT_PERSON_E_CONFIG_PATH,
) -> dict[str, Any]:
    """Build immutable, separately persisted evidence for one measurement row.

    The detailed payload carries its own canonical hash. The B handoff also
    stores the SHA-256 of the exact persisted document bytes, avoiding a
    recursive whole-document checksum while keeping
    ``measurement_artifact_hash`` resolvable to a real file.
    """

    if not isinstance(payload, Mapping):
        raise MeasurementError("Measurement evidence payload must be a mapping.")
    for field, value in (
        ("evidence_id", evidence_id),
        ("rollout_id", rollout_id),
        ("producer_run_id", producer_run_id),
    ):
        if not isinstance(value, str) or not value.strip():
            raise MeasurementError(f"{field} must be non-empty.")
    if not _is_exact_hex_digest(code_sha, 40):
        raise MeasurementError("code_sha must be a full hexadecimal Git SHA.")
    for field, value in (
        ("accepted_rollout_manifest_hash", accepted_rollout_manifest_hash),
        ("accepted_registry_hash", accepted_registry_hash),
    ):
        if not _is_exact_hex_digest(value, 64):
            raise MeasurementError(f"{field} must be SHA-256.")
    try:
        payload_copy = json.loads(
            json.dumps(
                payload,
                allow_nan=False,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
        )
    except (TypeError, ValueError) as error:
        raise MeasurementError(
            f"Measurement evidence is not canonical JSON: {error}"
        ) from error
    document = {
        "measurement_evidence_schema_version": MEASUREMENT_EVIDENCE_SCHEMA_VERSION,
        "evidence_id": evidence_id,
        "rollout_id": rollout_id,
        "producer_run_id": producer_run_id,
        "code_sha": code_sha,
        "schema_version": SCHEMA_VERSION,
        "accepted_rollout_manifest_hash": accepted_rollout_manifest_hash,
        "accepted_registry_hash": accepted_registry_hash,
        "measurement_config_hash": hash_person_e_config(config_path),
        "payload_hash": sha256_value(payload_copy),
        "payload": payload_copy,
    }
    validate_measurement_evidence(document, config_path=config_path)
    return document


def validate_measurement_evidence(
    document: Mapping[str, Any],
    *,
    config_path: Path | str = DEFAULT_PERSON_E_CONFIG_PATH,
) -> None:
    """Validate one persisted evidence document and all hash bindings."""

    if not isinstance(document, Mapping):
        raise MeasurementError("Measurement evidence must be a mapping.")
    required = {
        "measurement_evidence_schema_version",
        "evidence_id",
        "rollout_id",
        "producer_run_id",
        "code_sha",
        "schema_version",
        "accepted_rollout_manifest_hash",
        "accepted_registry_hash",
        "measurement_config_hash",
        "payload_hash",
        "payload",
    }
    if set(document) != required:
        raise MeasurementError("Measurement evidence envelope fields have changed.")
    if (
        document["measurement_evidence_schema_version"]
        != MEASUREMENT_EVIDENCE_SCHEMA_VERSION
        or document["schema_version"] != SCHEMA_VERSION
    ):
        raise MeasurementError("Measurement evidence schema version mismatch.")
    for field in ("evidence_id", "rollout_id", "producer_run_id"):
        if not isinstance(document[field], str) or not document[field].strip():
            raise MeasurementError(f"{field} must be non-empty.")
    if not _is_exact_hex_digest(document["code_sha"], 40):
        raise MeasurementError("code_sha must be a full hexadecimal Git SHA.")
    for field in (
        "accepted_rollout_manifest_hash",
        "accepted_registry_hash",
        "measurement_config_hash",
        "payload_hash",
    ):
        if not _is_exact_hex_digest(document[field], 64):
            raise MeasurementError(f"{field} must be SHA-256.")
    if document["measurement_config_hash"] != hash_person_e_config(config_path):
        raise MeasurementError("Evidence config hash does not match literal config bytes.")
    if not isinstance(document["payload"], Mapping):
        raise MeasurementError("Measurement evidence payload must be a mapping.")
    try:
        actual_payload_hash = sha256_value(document["payload"])
    except (TypeError, ValueError) as error:
        raise MeasurementError(
            f"Measurement evidence payload is not canonical JSON: {error}"
        ) from error
    if document["payload_hash"] != actual_payload_hash:
        raise MeasurementError("Measurement evidence payload hash mismatch.")
    try:
        json.dumps(document, allow_nan=False, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError) as error:
        raise MeasurementError(
            f"Measurement evidence is not canonical JSON: {error}"
        ) from error


def build_measurement_row(
    rollout_row: Mapping[str, Any],
    *,
    measurement_id: str,
    measurement_artifact_hash: str,
    baseline_rollout_id: str | None = None,
    pushed_reappearance: ReappearanceResult | None = None,
    baseline_reappearance: ReappearanceResult | None = None,
    ssim_result: SsimResult | None = None,
) -> dict[str, Any]:
    """Build one detailed row compatible with Person B's frozen consumer."""

    if not isinstance(rollout_row, Mapping):
        raise MeasurementError("rollout_row must be a mapping.")
    required = (
        "rollout_id",
        "run_id",
        "event_id",
        "seed",
        "direction_version",
        "control_type",
        "dose_id",
        "alpha_requested",
        "alpha_applied",
        "cap_reduced",
        "intended_block_shift",
        "layer_idx",
        "hook_site",
        "timestep_idx",
        "outcome",
        "outcome_detail",
        "status",
    )
    missing = [field for field in required if field not in rollout_row]
    if missing:
        raise MeasurementError("Rollout row is missing: " + ", ".join(missing))
    if not isinstance(measurement_id, str) or not measurement_id:
        raise MeasurementError("measurement_id must be non-empty.")
    if not _is_exact_hex_digest(measurement_artifact_hash, 64):
        raise MeasurementError("measurement_artifact_hash must be SHA-256.")
    for field in (
        "rollout_id",
        "run_id",
        "event_id",
        "direction_version",
        "control_type",
        "dose_id",
        "hook_site",
    ):
        if not isinstance(rollout_row[field], str) or not rollout_row[field]:
            raise MeasurementError(f"Rollout {field} must be non-empty.")
    for field in ("alpha_requested", "alpha_applied", "intended_block_shift"):
        if not _finite(rollout_row[field]):
            raise MeasurementError(f"Rollout {field} must be finite.")
    if not isinstance(rollout_row["seed"], int) or isinstance(
        rollout_row["seed"], bool
    ):
        raise MeasurementError("Rollout seed must be an integer.")
    for field in ("layer_idx", "timestep_idx"):
        if (
            not isinstance(rollout_row[field], int)
            or isinstance(rollout_row[field], bool)
            or rollout_row[field] < 0
        ):
            raise MeasurementError(f"Rollout {field} must be a non-negative integer.")
    if not isinstance(rollout_row["cap_reduced"], bool):
        raise MeasurementError("Rollout cap_reduced must be boolean.")
    if baseline_rollout_id is not None and (
        not isinstance(baseline_rollout_id, str) or not baseline_rollout_id
    ):
        raise MeasurementError("baseline_rollout_id must be null or non-empty.")

    row: dict[str, Any] = {
        "measurement_id": measurement_id,
        "rollout_id": rollout_row["rollout_id"],
        "rollout_run_id": rollout_row["run_id"],
        "event_id": rollout_row["event_id"],
        "direction_version": rollout_row["direction_version"],
        "control_type": rollout_row["control_type"],
        "dose_id": rollout_row["dose_id"],
        "alpha_requested": float(rollout_row["alpha_requested"]),
        "alpha_applied": float(rollout_row["alpha_applied"]),
        "cap_reduced": rollout_row["cap_reduced"],
        "intended_block_shift": float(rollout_row["intended_block_shift"]),
        "layer_idx": rollout_row["layer_idx"],
        "hook_site": rollout_row["hook_site"],
        "timestep_idx": rollout_row["timestep_idx"],
        "matched_alpha_zero_rollout_id": baseline_rollout_id,
        "measurement_status": None,
        "displacement_blocks": None,
        "persistence_score": None,
        "ssim": None,
        "raw_ssim": None,
        "outcome_detail": None,
        "measurement_artifact_hash": measurement_artifact_hash,
        "rollout_seed": rollout_row["seed"],
        "pushed_primary_frame_idx": None,
        "pushed_reveal_frame_idx": None,
        "pushed_detection_delay_frames": None,
        "pushed_world_coordinate_blocks": None,
        "baseline_primary_frame_idx": None,
        "baseline_reveal_frame_idx": None,
        "baseline_detection_delay_frames": None,
        "baseline_world_coordinate_blocks": None,
        "sensitivity_displacement_blocks": None,
        "background_masked_ssim": None,
        "quality_flags": [],
    }

    outcome = rollout_row["outcome"]
    if outcome == "generation_failure":
        if rollout_row["status"] != "excluded":
            raise MeasurementError(
                "Generation-failure rollouts must retain excluded lifecycle status."
            )
        row["measurement_status"] = "generation_failure"
        row["outcome_detail"] = rollout_row["outcome_detail"] or "generation_failure"
        row["quality_flags"] = ["no_completed_rollout_clip"]
        return row
    lifecycle = rollout_row["status"]
    if lifecycle != "accepted":
        lifecycle_detail = (
            rollout_row.get("exclusion_reason")
            or rollout_row.get("outcome_detail")
            or "not accepted"
        )
        row["measurement_status"] = "excluded"
        row["outcome_detail"] = (
            f"rollout_lifecycle_{lifecycle}: {lifecycle_detail}"
        )
        row["quality_flags"] = ["rollout_not_accepted"]
        return row
    if outcome == "non_persistence":
        row["measurement_status"] = "non_persistence"
        row["outcome_detail"] = rollout_row["outcome_detail"] or "non_persistence"
        row["quality_flags"] = ["rollout_declared_non_persistence"]
        return row
    if outcome != "measurable_continuation":
        raise MeasurementError(f"Unknown rollout outcome {outcome!r}.")
    if pushed_reappearance is None:
        row["measurement_status"] = "excluded"
        row["outcome_detail"] = "missing_localization_evidence"
        row["quality_flags"] = ["localization_evidence_missing"]
        return row
    if not isinstance(pushed_reappearance, ReappearanceResult):
        raise MeasurementError("pushed_reappearance must be a ReappearanceResult.")
    if not pushed_reappearance.measured:
        row["measurement_status"] = "non_persistence"
        row["outcome_detail"] = pushed_reappearance.outcome_detail
        row["quality_flags"] = ["measurement_detected_non_persistence"]
        return row
    if baseline_rollout_id is None:
        row["measurement_status"] = "excluded"
        row["outcome_detail"] = "missing_event_seed_matched_alpha_zero_rollout"
        row["quality_flags"] = ["baseline_rollout_missing"]
        return row
    if (
        baseline_reappearance is None
        or not isinstance(baseline_reappearance, ReappearanceResult)
        or not baseline_reappearance.measured
    ):
        row["measurement_status"] = "excluded"
        row["outcome_detail"] = "missing_valid_event_seed_matched_alpha_zero_reappearance"
        row["quality_flags"] = ["baseline_measurement_missing"]
        return row
    if ssim_result is None or not isinstance(ssim_result, SsimResult):
        row["measurement_status"] = "excluded"
        row["outcome_detail"] = "missing_or_invalid_ssim_measurement"
        row["quality_flags"] = ["ssim_missing"]
        return row
    if not 0.0 <= ssim_result.full_frame_ssim <= 1.0:
        row["measurement_status"] = "excluded"
        row["outcome_detail"] = "ssim_outside_frozen_b_consumer_range"
        row["raw_ssim"] = ssim_result.full_frame_ssim
        row["quality_flags"] = ["ssim_consumer_schema_gap"]
        return row
    if (
        pushed_reappearance.primary_wall_parallel_blocks is None
        or baseline_reappearance.primary_wall_parallel_blocks is None
    ):
        raise MeasurementError("Measured reappearance coordinates cannot be null.")
    displacement = (
        pushed_reappearance.primary_wall_parallel_blocks
        - baseline_reappearance.primary_wall_parallel_blocks
    )
    sensitivity_displacement = None
    if (
        pushed_reappearance.sensitivity_wall_parallel_blocks is not None
        and baseline_reappearance.sensitivity_wall_parallel_blocks is not None
    ):
        sensitivity_displacement = (
            pushed_reappearance.sensitivity_wall_parallel_blocks
            - baseline_reappearance.sensitivity_wall_parallel_blocks
        )
    row.update(
        {
            "measurement_status": "measured",
            "displacement_blocks": displacement,
            "persistence_score": 1.0,
            "ssim": ssim_result.full_frame_ssim,
            "outcome_detail": None,
            "pushed_primary_frame_idx": pushed_reappearance.primary_frame_idx,
            "pushed_reveal_frame_idx": pushed_reappearance.reveal_frame_idx,
            "pushed_detection_delay_frames": (
                pushed_reappearance.detection_delay_frames
            ),
            "pushed_world_coordinate_blocks": (
                pushed_reappearance.primary_wall_parallel_blocks
            ),
            "baseline_primary_frame_idx": baseline_reappearance.primary_frame_idx,
            "baseline_reveal_frame_idx": baseline_reappearance.reveal_frame_idx,
            "baseline_detection_delay_frames": (
                baseline_reappearance.detection_delay_frames
            ),
            "baseline_world_coordinate_blocks": (
                baseline_reappearance.primary_wall_parallel_blocks
            ),
            "sensitivity_displacement_blocks": sensitivity_displacement,
            "background_masked_ssim": ssim_result.background_masked_ssim,
            "quality_flags": [],
        }
    )
    return row


def _alpha_zero_persistence_summary(
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    alpha_zero = [row for row in rows if row.get("control_type") == "alpha_zero"]
    counts = {
        status: sum(row.get("measurement_status") == status for row in alpha_zero)
        for status in (
            "measured",
            "non_persistence",
            "generation_failure",
            "excluded",
        )
    }
    classifiable = counts["measured"] + counts["non_persistence"]
    return {
        "definition": "before_any_persistence_conditioning",
        "submitted_count": len(alpha_zero),
        "persistent_count": counts["measured"],
        "non_persistence_count": counts["non_persistence"],
        "generation_failure_count": counts["generation_failure"],
        "excluded_count": counts["excluded"],
        "classifiable_count": classifiable,
        "persistence_rate_among_classifiable": (
            None if classifiable == 0 else counts["measured"] / classifiable
        ),
    }


def _validate_evidence_references(
    references: Sequence[Mapping[str, Any]],
    rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    if (
        not isinstance(references, Sequence)
        or isinstance(references, (str, bytes))
        or any(not isinstance(reference, Mapping) for reference in references)
    ):
        raise MeasurementError("measurement_evidence must be a sequence of mappings.")
    by_rollout: dict[str, dict[str, Any]] = {}
    required = {
        "evidence_id",
        "rollout_id",
        "uri",
        "sha256",
        "producer_run_id",
    }
    for index, reference in enumerate(references):
        if set(reference) != required:
            raise MeasurementError(
                f"Measurement-evidence reference {index} fields have changed."
            )
        rollout_id = reference["rollout_id"]
        for field in ("evidence_id", "rollout_id", "uri", "producer_run_id"):
            if not isinstance(reference[field], str) or not reference[field].strip():
                raise MeasurementError(f"Evidence reference {field} must be non-empty.")
        if not _is_exact_hex_digest(reference["sha256"], 64):
            raise MeasurementError("Evidence reference sha256 must be SHA-256.")
        if rollout_id in by_rollout:
            raise MeasurementError("Each rollout must reference one evidence file.")
        by_rollout[rollout_id] = dict(reference)
    expected_ids = {row.get("rollout_id") for row in rows}
    if set(by_rollout) != expected_ids:
        raise MeasurementError("Evidence references must exactly cover measurement rows.")
    for row in rows:
        reference = by_rollout[row["rollout_id"]]
        if row.get("measurement_artifact_hash") != reference["sha256"]:
            raise MeasurementError(
                "measurement_artifact_hash must equal the persisted evidence checksum."
            )
    return [by_rollout[rollout_id] for rollout_id in sorted(by_rollout)]


def build_measurement_document(
    rows: Sequence[Mapping[str, Any]],
    *,
    rollout_manifest: Mapping[str, Any],
    registry: Mapping[str, Any],
    accepted_rollout_manifest_hash: str,
    accepted_registry_hash: str,
    measurement_evidence: Sequence[Mapping[str, Any]],
    result_scope: str = "scientific",
    config_path: Path | str = DEFAULT_PERSON_E_CONFIG_PATH,
) -> dict[str, Any]:
    """Build a registry-validated, exact-coverage E-to-B measurement handoff."""

    if (
        not isinstance(rows, Sequence)
        or isinstance(rows, (str, bytes))
        or not rows
        or any(not isinstance(row, Mapping) for row in rows)
    ):
        raise MeasurementError("Measurement rows must be a sequence of mappings.")
    if result_scope not in {"scientific", "known_answer"}:
        raise MeasurementError("result_scope must be scientific or known_answer.")
    if result_scope == "scientific":
        require_live_ready_person_e_config(config_path)
    for field, value in (
        ("accepted_rollout_manifest_hash", accepted_rollout_manifest_hash),
        ("accepted_registry_hash", accepted_registry_hash),
    ):
        if not _is_exact_hex_digest(value, 64):
            raise MeasurementError(f"{field} must be SHA-256.")
    from mineocclude.experiments.registry import RegistryIndex

    RegistryIndex(rollout_manifest, registry)
    if accepted_rollout_manifest_hash != sha256_value(rollout_manifest):
        raise MeasurementError(
            "accepted_rollout_manifest_hash does not match the validated manifest."
        )
    if accepted_registry_hash != sha256_value(registry):
        raise MeasurementError(
            "accepted_registry_hash does not match the validated registry."
        )
    manifest_rows = rollout_manifest.get("rollout_rows")
    if not isinstance(manifest_rows, list) or not manifest_rows:
        raise MeasurementError("Validated rollout manifest unexpectedly has no rows.")
    ordered_rows = sorted(
        (copy.deepcopy(dict(row)) for row in rows),
        key=lambda row: str(row.get("rollout_id", "")),
    )
    evidence_references = _validate_evidence_references(
        measurement_evidence, ordered_rows
    )
    document = {
        "schema_version": SCHEMA_VERSION,
        "measurement_input_schema_version": MEASUREMENT_INPUT_SCHEMA_VERSION,
        "producer_role": "person_e",
        "result_scope": result_scope,
        "accepted_rollout_manifest_hash": accepted_rollout_manifest_hash,
        "accepted_registry_hash": accepted_registry_hash,
        "measurement_config_hash": hash_person_e_config(config_path),
        "measurement_evidence": evidence_references,
        "alpha_zero_persistence_summary": _alpha_zero_persistence_summary(
            ordered_rows
        ),
        "rows": ordered_rows,
    }
    validation = validate_measurement_input(
        document,
        rollout_manifest=rollout_manifest,
        registry=registry,
    )
    if not validation.accepted:
        details = "; ".join(
            f"{rejection.code.value}: {rejection.message}"
            for rejection in validation.rejections
        )
        raise MeasurementError(f"E-to-B measurement document is invalid: {details}")
    return document


def validate_phase1_rollout_measurement_fixture(
    document: Mapping[str, Any],
) -> dict[str, str]:
    """Validate the Phase 1 A-rollout/E-measurement scenario fixture.

    Rollout identity and outcomes come from A's authoritative validator. D's
    declared control IDs are derived through D's control-matrix implementation.
    E only records the measurement-facing expected result for each synthetic
    scenario.
    """

    if not isinstance(document, Mapping):
        raise MeasurementError("Phase 1 rollout fixture must be a mapping.")
    fields = {
        "schema_version",
        "scenario_schema_version",
        "fixture_id",
        "synthetic",
        "scientific_use",
        "rollout_manifest",
        "registry",
        "cases",
    }
    if set(document) != fields:
        raise MeasurementError("Phase 1 rollout fixture fields have changed.")
    if document["schema_version"] != SCHEMA_VERSION:
        raise MeasurementError("schema_version must remain '1.0'.")
    if (
        document["scenario_schema_version"]
        != PHASE1_ROLLOUT_MEASUREMENT_FIXTURE_SCHEMA_VERSION
    ):
        raise MeasurementError("Unsupported rollout-measurement fixture schema.")
    if not isinstance(document["fixture_id"], str) or not document["fixture_id"]:
        raise MeasurementError("fixture_id must be non-empty.")
    if document["synthetic"] is not True or document["scientific_use"] != "forbidden":
        raise MeasurementError(
            "Phase 1 rollout-measurement evidence must be synthetic and non-scientific."
        )
    rollout_manifest = document["rollout_manifest"]
    registry = document["registry"]
    validation = validate_rollout_registry_bundle(rollout_manifest, registry)
    if not validation.accepted:
        codes = ", ".join(sorted(rejection.code.value for rejection in validation.rejections))
        raise MeasurementError(f"A rollout/registry fixture is invalid: {codes}.")
    rollout_by_id = {
        row["rollout_id"]: row for row in rollout_manifest["rollout_rows"]
    }

    cases = document["cases"]
    if not isinstance(cases, list) or not cases:
        raise MeasurementError("cases must be a non-empty list.")
    required_case_fields = {
        "case_id",
        "scenario_kind",
        "rollout_id",
        "declared_control_id",
        "expected_frame_id",
        "observed_frame_id",
        "measurement_status",
        "displacement_blocks",
        "expected_result",
    }
    case_ids: set[str] = set()
    covered_kinds: set[str] = set()
    results: dict[str, str] = {}
    for index, case in enumerate(cases):
        name = f"cases[{index}]"
        if not isinstance(case, Mapping) or set(case) != required_case_fields:
            raise MeasurementError(f"{name} fields have changed.")
        for field in (
            "case_id",
            "scenario_kind",
            "rollout_id",
            "declared_control_id",
            "expected_frame_id",
            "measurement_status",
            "expected_result",
        ):
            if not isinstance(case[field], str) or not case[field]:
                raise MeasurementError(f"{name}.{field} must be non-empty.")
        case_id = case["case_id"]
        if case_id in case_ids:
            raise MeasurementError(f"Duplicate case_id {case_id!r}.")
        case_ids.add(case_id)
        kind = case["scenario_kind"]
        if kind not in PHASE1_SCENARIO_KINDS:
            raise MeasurementError(f"{name}.scenario_kind is unsupported.")
        covered_kinds.add(kind)
        rollout = rollout_by_id.get(case["rollout_id"])
        if rollout is None:
            raise MeasurementError(f"{name} references an unknown A rollout ID.")

        control_kind = ControlKind.PRIMARY
        if rollout["control_type"] == "alpha_zero":
            control_kind = ControlKind.ALPHA_ZERO
        elif rollout["control_type"] == "random_direction":
            control_kind = ControlKind.RANDOM_DIRECTION
        expected_control_id = next(
            item.control_id
            for item in build_control_matrix([rollout["event_id"]], [rollout["seed"]])
            if item.kind == control_kind
        )
        if case["declared_control_id"] != expected_control_id:
            raise MeasurementError(f"{name} redefines D's declared control identity.")

        alpha = float(rollout["alpha_applied"])
        if kind == "alpha_zero" and not (
            rollout["control_type"] == "alpha_zero" and alpha == 0.0
        ):
            raise MeasurementError(f"{name} does not reference an alpha-zero rollout.")
        if kind == "positive_signed_dose" and not (
            rollout["control_type"] == "intervention" and alpha > 0.0
        ):
            raise MeasurementError(f"{name} does not reference a positive dose.")
        if kind == "negative_signed_dose" and not (
            rollout["control_type"] == "intervention" and alpha < 0.0
        ):
            raise MeasurementError(f"{name} does not reference a negative dose.")
        if kind == "random_control" and rollout["control_type"] != "random_direction":
            raise MeasurementError(f"{name} does not reference a random control.")
        if kind == "non_persistence" and rollout["outcome"] != "non_persistence":
            raise MeasurementError(f"{name} does not reference non-persistence.")

        observed_frame_id = case["observed_frame_id"]
        if observed_frame_id is not None and (
            not isinstance(observed_frame_id, str) or not observed_frame_id
        ):
            raise MeasurementError(f"{name}.observed_frame_id is malformed.")
        if observed_frame_id is None:
            actual_result = "rejected_missing_frame"
        elif observed_frame_id != case["expected_frame_id"]:
            actual_result = "rejected_misaligned_frame"
        elif rollout["outcome"] == "non_persistence":
            actual_result = "accepted_non_persistence"
        elif rollout["outcome"] == "generation_failure":
            actual_result = "accepted_generation_failure"
        else:
            actual_result = "accepted_measurement"

        displacement = case["displacement_blocks"]
        if actual_result == "accepted_measurement":
            if case["measurement_status"] != "measured" or not _finite(displacement):
                raise MeasurementError(f"{name} measurable continuation is malformed.")
        elif actual_result == "accepted_non_persistence":
            if (
                case["measurement_status"] != "non_persistence"
                or displacement is not None
            ):
                raise MeasurementError(
                    f"{name} non-persistence cannot become numeric displacement."
                )
        elif actual_result == "accepted_generation_failure":
            if (
                case["measurement_status"] != "generation_failure"
                or displacement is not None
            ):
                raise MeasurementError(
                    f"{name} generation failure cannot become numeric displacement."
                )
        elif case["measurement_status"] != "rejected" or displacement is not None:
            raise MeasurementError(f"{name} rejected frame evidence is malformed.")
        if case["expected_result"] != actual_result:
            raise MeasurementError(
                f"{name} expected result disagrees with explicit frame/outcome evidence."
            )
        if kind == "missing_frame" and actual_result != "rejected_missing_frame":
            raise MeasurementError(f"{name} must exercise missing-frame rejection.")
        if kind == "misaligned_frame" and actual_result != "rejected_misaligned_frame":
            raise MeasurementError(f"{name} must exercise frame-alignment rejection.")
        results[case_id] = actual_result

    missing_kinds = sorted(PHASE1_SCENARIO_KINDS - covered_kinds)
    if missing_kinds:
        raise MeasurementError(f"Phase 1 rollout fixture lacks cases: {missing_kinds}.")
    return dict(sorted(results.items()))
