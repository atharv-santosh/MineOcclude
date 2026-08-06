"""Freeze, execute, hand off, and classify the Week 1 U4 rollouts (Steps 8.5-8.8).

The manifest is built before any video exists and contains no outcome-dependent
field. Generation runs strictly from it. Handoffs give the complete bundle, not a
selection. Classification separates working plumbing from a causal claim.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any

ROLLOUT_MANIFEST_SCHEMA_VERSION = "person-a-u4-rollout-manifest-v0.1"
ROLLOUT_BUNDLE_SCHEMA_VERSION = "person-a-u4-rollout-bundle-v0.1"
HANDOFF_SCHEMA_VERSION = "person-a-u4-handoff-v0.1"
CLASSIFICATION_SCHEMA_VERSION = "person-a-u4-classification-v0.1"

DEFAULT_INTENDED_SHIFTS: tuple[int, ...] = (-2, -1, 0, 1, 2)
DEFAULT_HELDOUT_EVENT_COUNT = 5
DEFAULT_SEEDS_PER_CELL = 2
DEFAULT_RANDOM_CONTROL_COUNT = 20
DEFAULT_RANDOM_CONTROL_SHIFT = 2

# Clips whose scientific value depends on never being regenerated in place.
NON_OVERWRITABLE_CONTROL_TYPES = frozenset({"alpha_zero", "random_direction"})


class ControlType(str, Enum):
    """What role one clip plays in the U4 design."""

    INTERVENTION = "intervention"
    ALPHA_ZERO = "alpha_zero"
    RANDOM_DIRECTION = "random_direction"
    D_SPECIFIED = "d_specified_control"


class ClipOutcome(str, Enum):
    """Terminal generation outcomes, kept distinct from measurement results."""

    PENDING = "pending"
    COMPLETED = "completed"
    GENERATION_FAILURE = "generation_failure"
    SUPERSEDED = "superseded"


class U4Classification(str, Enum):
    """The only labels Step 8.8 may assign."""

    CAUSAL_PILOT = "causal_pilot"
    PLUMBING_ONLY = "plumbing_only"
    CLEAN_NEGATIVE = "clean_negative"
    INVALID_MEASUREMENT = "invalid_measurement"


class RolloutErrorCode(str, Enum):
    INVALID_REQUEST = "invalid_request"
    DUPLICATE_CLIP_ID = "duplicate_clip_id"
    UNKNOWN_CLIP = "unknown_clip"
    OUTCOME_DEPENDENT_FIELD = "outcome_dependent_field"
    EXPECTED_COUNT_MISMATCH = "expected_count_mismatch"
    OVERWRITE_FORBIDDEN = "overwrite_forbidden"
    SUPERSESSION_REQUIRED = "supersession_required"
    INCOMPLETE_HANDOFF = "incomplete_handoff"
    CLASSIFICATION_NOT_SUPPORTED = "classification_not_supported"


class RolloutError(ValueError):
    """Raised when a rollout operation would corrupt the U4 design."""

    def __init__(self, code: RolloutErrorCode, message: str) -> None:
        self.code = code
        super().__init__(f"{code.value}: {message}")


def _fail(code: RolloutErrorCode, message: str) -> None:
    raise RolloutError(code, message)


# ---------------------------------------------------------------------------
# Step 8.5 — the immutable manifest
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HeldoutEvent:
    """One held-out evaluation event, selected without seeing any outcome."""

    event_id: str
    trajectory_id: str
    layout_id: str
    model_frame_idx: int

    def to_document(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "trajectory_id": self.trajectory_id,
            "layout_id": self.layout_id,
            "model_frame_idx": self.model_frame_idx,
        }


@dataclass(frozen=True)
class DoseSpec:
    """One dose, keyed by intended block shift rather than by observed effect."""

    dose_id: str
    intended_block_shift: int
    alpha_requested: float
    alpha_applied: float
    cap_reduced: bool = False

    def to_document(self) -> dict[str, Any]:
        return {
            "dose_id": self.dose_id,
            "intended_block_shift": self.intended_block_shift,
            "alpha_requested": self.alpha_requested,
            "alpha_applied": self.alpha_applied,
            "cap_reduced": self.cap_reduced,
        }


@dataclass(frozen=True)
class ClipSpec:
    """One planned clip with an immutable identity and output path."""

    clip_id: str
    control_type: ControlType
    event_id: str
    dose_id: str
    intended_block_shift: int
    alpha_applied: float
    seed: int
    direction_version: str
    layer_idx: int
    timestep_idx: int
    hook_site: str
    output_path: str
    d_control_id: str | None = None

    def to_document(self) -> dict[str, Any]:
        return {
            "clip_id": self.clip_id,
            "control_type": self.control_type.value,
            "event_id": self.event_id,
            "dose_id": self.dose_id,
            "intended_block_shift": self.intended_block_shift,
            "alpha_applied": self.alpha_applied,
            "seed": self.seed,
            "direction_version": self.direction_version,
            "layer_idx": self.layer_idx,
            "timestep_idx": self.timestep_idx,
            "hook_site": self.hook_site,
            "output_path": self.output_path,
            "d_control_id": self.d_control_id,
            "overwrite_permitted": (
                self.control_type not in NON_OVERWRITABLE_CONTROL_TYPES
            ),
        }


# Fields that would let an outcome choose what is reported. A manifest carrying
# any of these is rejected outright.
FORBIDDEN_CLIP_FIELDS = frozenset(
    {
        "displacement",
        "displacement_blocks",
        "ssim",
        "persistence",
        "persisted",
        "measured_shift",
        "selected_for_report",
        "include_in_analysis",
        "outcome_score",
        "visual_quality",
    }
)


def build_rollout_manifest(
    *,
    manifest_id: str,
    handoff_id: str,
    heldout_events: Sequence[HeldoutEvent],
    doses: Sequence[DoseSpec],
    seeds: Sequence[int],
    direction_version: str,
    layer_idx: int,
    timestep_idx: int,
    hook_site: str,
    output_root: str,
    random_control_seeds: Sequence[int],
    random_control_direction_versions: Sequence[str],
    random_control_shift: int = DEFAULT_RANDOM_CONTROL_SHIFT,
    d_control_ids: Sequence[str] = (),
    expected_primary_clip_count: int | None = None,
    expected_random_control_count: int = DEFAULT_RANDOM_CONTROL_COUNT,
) -> dict[str, Any]:
    """Encode events x shifts x seeds plus norm-matched and D-specified controls.

    Every clip gets a unique identity and a unique output path before any video
    is generated, so a later result can neither add a clip nor omit one.
    """

    if not heldout_events:
        _fail(RolloutErrorCode.INVALID_REQUEST, "held-out events are required")
    if not doses:
        _fail(RolloutErrorCode.INVALID_REQUEST, "at least one dose is required")
    if not seeds:
        _fail(RolloutErrorCode.INVALID_REQUEST, "at least one seed is required")
    if len({event.event_id for event in heldout_events}) != len(heldout_events):
        _fail(RolloutErrorCode.DUPLICATE_CLIP_ID, "held-out event IDs must be unique")
    if len({dose.dose_id for dose in doses}) != len(doses):
        _fail(RolloutErrorCode.DUPLICATE_CLIP_ID, "dose IDs must be unique")

    clips: list[ClipSpec] = []
    for event in heldout_events:
        for dose in doses:
            for seed in seeds:
                control_type = (
                    ControlType.ALPHA_ZERO
                    if dose.intended_block_shift == 0 and dose.alpha_applied == 0.0
                    else ControlType.INTERVENTION
                )
                clip_id = (
                    f"u4-{event.event_id}-{dose.dose_id}-seed{seed}"
                )
                clips.append(
                    ClipSpec(
                        clip_id=clip_id,
                        control_type=control_type,
                        event_id=event.event_id,
                        dose_id=dose.dose_id,
                        intended_block_shift=dose.intended_block_shift,
                        alpha_applied=dose.alpha_applied,
                        seed=seed,
                        direction_version=direction_version,
                        layer_idx=layer_idx,
                        timestep_idx=timestep_idx,
                        hook_site=hook_site,
                        output_path=f"{output_root}/primary/{clip_id}.mp4",
                    )
                )

    primary_count = len(clips)
    expected_primary = (
        expected_primary_clip_count
        if expected_primary_clip_count is not None
        else len(heldout_events) * len(doses) * len(seeds)
    )
    if primary_count != expected_primary:
        _fail(
            RolloutErrorCode.EXPECTED_COUNT_MISMATCH,
            f"{primary_count} primary clips were encoded but {expected_primary} "
            "were expected",
        )

    if len(random_control_seeds) * len(random_control_direction_versions) != (
        expected_random_control_count
    ):
        _fail(
            RolloutErrorCode.EXPECTED_COUNT_MISMATCH,
            f"{len(random_control_seeds)} seeds x "
            f"{len(random_control_direction_versions)} random directions != "
            f"{expected_random_control_count} expected controls",
        )
    control_dose = _matching_dose(doses, random_control_shift)
    for direction_id in random_control_direction_versions:
        for seed in random_control_seeds:
            clip_id = f"u4-random-{direction_id}-seed{seed}"
            clips.append(
                ClipSpec(
                    clip_id=clip_id,
                    control_type=ControlType.RANDOM_DIRECTION,
                    event_id=heldout_events[0].event_id,
                    dose_id=control_dose.dose_id,
                    intended_block_shift=random_control_shift,
                    alpha_applied=control_dose.alpha_applied,
                    seed=seed,
                    direction_version=direction_id,
                    layer_idx=layer_idx,
                    timestep_idx=timestep_idx,
                    hook_site=hook_site,
                    output_path=f"{output_root}/controls/{clip_id}.mp4",
                )
            )

    for control_id in d_control_ids:
        clip_id = f"u4-dcontrol-{control_id}"
        clips.append(
            ClipSpec(
                clip_id=clip_id,
                control_type=ControlType.D_SPECIFIED,
                event_id=heldout_events[0].event_id,
                dose_id=control_dose.dose_id,
                intended_block_shift=random_control_shift,
                alpha_applied=control_dose.alpha_applied,
                seed=random_control_seeds[0] if random_control_seeds else 0,
                direction_version=direction_version,
                layer_idx=layer_idx,
                timestep_idx=timestep_idx,
                hook_site=hook_site,
                output_path=f"{output_root}/controls/{clip_id}.mp4",
                d_control_id=control_id,
            )
        )

    clip_ids = [clip.clip_id for clip in clips]
    if len(set(clip_ids)) != len(clip_ids):
        _fail(RolloutErrorCode.DUPLICATE_CLIP_ID, "clip identities must be unique")
    paths = [clip.output_path for clip in clips]
    if len(set(paths)) != len(paths):
        _fail(RolloutErrorCode.DUPLICATE_CLIP_ID, "clip output paths must be unique")

    manifest = {
        "schema_version": ROLLOUT_MANIFEST_SCHEMA_VERSION,
        "step": "8.5",
        "manifest_id": manifest_id,
        "handoff_id": handoff_id,
        "immutable": True,
        "direction_version": direction_version,
        "intervention_location": {
            "layer_idx": layer_idx,
            "timestep_idx": timestep_idx,
            "hook_site": hook_site,
        },
        "heldout_events": [event.to_document() for event in heldout_events],
        "doses": [dose.to_document() for dose in doses],
        "seeds": list(seeds),
        "expected_counts": {
            "heldout_event_count": len(heldout_events),
            "dose_count": len(doses),
            "seed_count": len(seeds),
            "primary_clip_count": primary_count,
            "random_direction_control_count": expected_random_control_count,
            "d_specified_control_count": len(d_control_ids),
            "total_clip_count": len(clips),
        },
        "clips": [clip.to_document() for clip in clips],
        "outcome_dependent_selection_fields": [],
        "contains_outcome_dependent_selection": False,
        "non_overwritable_control_types": sorted(NON_OVERWRITABLE_CONTROL_TYPES),
    }
    validate_rollout_manifest(manifest)
    return manifest


def _matching_dose(doses: Sequence[DoseSpec], shift: int) -> DoseSpec:
    for dose in doses:
        if dose.intended_block_shift == shift:
            return dose
    _fail(
        RolloutErrorCode.INVALID_REQUEST,
        f"no dose maps to the requested control block shift {shift}",
    )
    raise AssertionError  # pragma: no cover


def validate_rollout_manifest(manifest: Mapping[str, Any]) -> None:
    """Reject a manifest that could let an outcome choose what is reported."""

    if manifest.get("schema_version") != ROLLOUT_MANIFEST_SCHEMA_VERSION:
        _fail(
            RolloutErrorCode.INVALID_REQUEST,
            f"manifest schema must equal {ROLLOUT_MANIFEST_SCHEMA_VERSION!r}",
        )
    clips = manifest.get("clips")
    if not isinstance(clips, list) or not clips:
        _fail(RolloutErrorCode.INVALID_REQUEST, "a manifest requires clips")
    for clip in clips:
        if not isinstance(clip, Mapping):
            _fail(RolloutErrorCode.INVALID_REQUEST, "each clip must be a mapping")
        offending = sorted(set(clip) & FORBIDDEN_CLIP_FIELDS)
        if offending:
            _fail(
                RolloutErrorCode.OUTCOME_DEPENDENT_FIELD,
                f"clip {clip.get('clip_id')!r} carries outcome-dependent fields: "
                + ", ".join(offending),
            )
    expected = manifest.get("expected_counts")
    if not isinstance(expected, Mapping):
        _fail(RolloutErrorCode.INVALID_REQUEST, "expected_counts is required")
    if int(expected.get("total_clip_count", -1)) != len(clips):
        _fail(
            RolloutErrorCode.EXPECTED_COUNT_MISMATCH,
            "declared total clip count does not match the encoded clips",
        )


def manifest_hash(manifest: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


# ---------------------------------------------------------------------------
# Step 8.6 — resumable generation strictly from the manifest
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ClipResult:
    """One clip's recorded generation outcome and produced identity."""

    clip_id: str
    outcome: ClipOutcome
    output_hash: str | None = None
    output_path: str | None = None
    runtime_seconds: float | None = None
    log_path: str | None = None
    failure_reason: str | None = None
    attempt: int = 1
    supersedes_attempt: int | None = None
    injection_audit: Mapping[str, Any] | None = None

    def to_document(self) -> dict[str, Any]:
        return {
            "clip_id": self.clip_id,
            "outcome": self.outcome.value,
            "output_hash": self.output_hash,
            "output_path": self.output_path,
            "runtime_seconds": self.runtime_seconds,
            "log_path": self.log_path,
            "failure_reason": self.failure_reason,
            "attempt": self.attempt,
            "supersedes_attempt": self.supersedes_attempt,
            "injection_audit": (
                dict(self.injection_audit) if self.injection_audit else None
            ),
            "generation_failure_distinct_from_non_persistence": True,
        }


@dataclass
class RolloutRunner:
    """Generate strictly from the immutable manifest, resumably and safely."""

    manifest: Mapping[str, Any]
    results: dict[str, ClipResult] = field(default_factory=dict)

    def __post_init__(self) -> None:
        validate_rollout_manifest(self.manifest)
        self._clips = {
            str(clip["clip_id"]): clip for clip in self.manifest["clips"]
        }

    @property
    def clip_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._clips))

    def pending_clip_ids(self) -> tuple[str, ...]:
        return tuple(
            clip_id
            for clip_id in self.clip_ids
            if self.results.get(clip_id) is None
            or self.results[clip_id].outcome is ClipOutcome.PENDING
        )

    def record(self, result: ClipResult) -> ClipResult:
        """Record one clip's outcome, refusing a silent overwrite."""

        clip = self._clips.get(result.clip_id)
        if clip is None:
            _fail(
                RolloutErrorCode.UNKNOWN_CLIP,
                f"clip {result.clip_id!r} is not in the immutable manifest",
            )
        assert clip is not None
        existing = self.results.get(result.clip_id)
        if existing is not None and existing.outcome is ClipOutcome.COMPLETED:
            if not clip.get("overwrite_permitted", True):
                _fail(
                    RolloutErrorCode.OVERWRITE_FORBIDDEN,
                    f"clip {result.clip_id!r} is a "
                    f"{clip['control_type']} control and must never be overwritten",
                )
            if result.supersedes_attempt is None:
                _fail(
                    RolloutErrorCode.SUPERSESSION_REQUIRED,
                    f"clip {result.clip_id!r} already completed; a replacement "
                    "must record the attempt it supersedes",
                )
            self.results[f"{result.clip_id}#attempt{existing.attempt}"] = replace(
                existing, outcome=ClipOutcome.SUPERSEDED
            )
        self.results[result.clip_id] = result
        return result

    def bundle(self) -> dict[str, Any]:
        """Publish the complete produced-versus-expected generation bundle."""

        expected = self.manifest["expected_counts"]
        rows = []
        for clip_id in self.clip_ids:
            clip = self._clips[clip_id]
            result = self.results.get(clip_id)
            rows.append(
                {
                    **clip,
                    **(
                        result.to_document()
                        if result
                        else {
                            "clip_id": clip_id,
                            "outcome": ClipOutcome.PENDING.value,
                            "output_hash": None,
                        }
                    ),
                }
            )
        outcome_counts: dict[str, int] = {member.value: 0 for member in ClipOutcome}
        for row in rows:
            outcome_counts[row["outcome"]] += 1
        superseded = [
            record.to_document()
            for key, record in sorted(self.results.items())
            if "#attempt" in key
        ]
        return {
            "schema_version": ROLLOUT_BUNDLE_SCHEMA_VERSION,
            "step": "8.6",
            "manifest_id": self.manifest["manifest_id"],
            "manifest_sha256": manifest_hash(self.manifest),
            "expected_counts": dict(expected),
            "produced_counts": outcome_counts,
            "expected_clip_count": int(expected["total_clip_count"]),
            "completed_clip_count": outcome_counts[ClipOutcome.COMPLETED.value],
            "generation_failure_count": outcome_counts[
                ClipOutcome.GENERATION_FAILURE.value
            ],
            "pending_clip_count": outcome_counts[ClipOutcome.PENDING.value],
            "complete": (
                outcome_counts[ClipOutcome.PENDING.value] == 0
                and outcome_counts[ClipOutcome.COMPLETED.value]
                + outcome_counts[ClipOutcome.GENERATION_FAILURE.value]
                == int(expected["total_clip_count"])
            ),
            "superseded_attempts": superseded,
            "clips": rows,
            "outcome_selection_applied": False,
        }


# ---------------------------------------------------------------------------
# Step 8.7 — complete handoffs, never a selection
# ---------------------------------------------------------------------------


def build_measurement_handoff(
    bundle: Mapping[str, Any],
    *,
    handoff_id: str,
    event_dose_table: Mapping[str, Any],
    detector_version: str,
    homography_version: str,
) -> dict[str, Any]:
    """Give Person E the complete bundle plus the frozen detector versions."""

    _require_complete_transfer(bundle)
    return {
        "schema_version": HANDOFF_SCHEMA_VERSION,
        "step": "8.7",
        "handoff_id": handoff_id,
        "recipient": "person_e_operations",
        "manifest_id": bundle["manifest_id"],
        "manifest_sha256": bundle["manifest_sha256"],
        "expected_clip_count": bundle["expected_clip_count"],
        "produced_clip_count": (
            bundle["completed_clip_count"] + bundle["generation_failure_count"]
        ),
        "completed_clip_count": bundle["completed_clip_count"],
        "generation_failure_count": bundle["generation_failure_count"],
        "missing_clip_count": bundle["pending_clip_count"],
        "complete_bundle_transferred": True,
        "selection_applied": False,
        "event_dose_table": dict(event_dose_table),
        "frozen_detector_version": detector_version,
        "frozen_homography_version": homography_version,
        "clips": list(bundle["clips"]),
        "summary_withheld_until_full_table": True,
    }


def build_control_handoff(
    bundle: Mapping[str, Any],
    *,
    handoff_id: str,
) -> dict[str, Any]:
    """Give Person D the complete control manifest and generation status."""

    _require_complete_transfer(bundle)
    controls = [
        clip
        for clip in bundle["clips"]
        if clip["control_type"] != ControlType.INTERVENTION.value
    ]
    return {
        "schema_version": HANDOFF_SCHEMA_VERSION,
        "step": "8.7",
        "handoff_id": handoff_id,
        "recipient": "person_d_baselines",
        "manifest_id": bundle["manifest_id"],
        "manifest_sha256": bundle["manifest_sha256"],
        "control_clip_count": len(controls),
        "control_type_counts": _control_type_counts(controls),
        "superseded_attempts": list(bundle["superseded_attempts"]),
        "omission_auditable": True,
        "overwrite_auditable": True,
        "controls": controls,
    }


def _control_type_counts(clips: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for clip in clips:
        counts[clip["control_type"]] = counts.get(clip["control_type"], 0) + 1
    return dict(sorted(counts.items()))


def _require_complete_transfer(bundle: Mapping[str, Any]) -> None:
    if bundle.get("schema_version") != ROLLOUT_BUNDLE_SCHEMA_VERSION:
        _fail(
            RolloutErrorCode.INCOMPLETE_HANDOFF,
            "a handoff requires a rollout bundle produced by the runner",
        )
    if not isinstance(bundle.get("clips"), list) or not bundle["clips"]:
        _fail(
            RolloutErrorCode.INCOMPLETE_HANDOFF,
            "a handoff must carry every clip, not a selection",
        )


# ---------------------------------------------------------------------------
# Step 8.8 — claim-safe classification
# ---------------------------------------------------------------------------


def classify_u4(
    *,
    injection_exact: bool,
    baseline_persistence_confirmed: bool,
    signed_displacement_pattern_confirmed: bool,
    random_direction_specificity_confirmed: bool,
    wrong_site_specificity_confirmed: bool,
    ssim_within_natural_variation: bool,
    predeclared_heldout_partition_present: bool,
    measurement_valid: bool,
    controls_valid: bool,
    evidence_tables: Mapping[str, str],
    detail: str | None = None,
) -> dict[str, Any]:
    """Label the U4 path from evidence, failing closed rather than claiming.

    A missing predeclared held-out partition caps the claim at plumbing-only. A
    measurement or control failure preserves the outputs and withholds a causal
    claim instead of retuning on test videos.
    """

    reasons: list[str] = []
    if not injection_exact:
        reasons.append("the injection did not modify exactly the intended positions")
    if not measurement_valid:
        reasons.append("measurement did not produce a valid table")
    if not controls_valid:
        reasons.append("controls did not complete or did not validate")
    if not predeclared_heldout_partition_present:
        reasons.append("no predeclared held-out partition was available")
    if not baseline_persistence_confirmed:
        reasons.append("baseline persistence was not confirmed")
    if not signed_displacement_pattern_confirmed:
        reasons.append("the signed displacement pattern was not confirmed")
    if not random_direction_specificity_confirmed:
        reasons.append("random-direction specificity was not confirmed")
    if not wrong_site_specificity_confirmed:
        reasons.append("wrong-site specificity was not confirmed")
    if not ssim_within_natural_variation:
        reasons.append("SSIM fell outside natural scene variation")

    if not injection_exact:
        label = U4Classification.INVALID_MEASUREMENT
    elif not measurement_valid:
        label = U4Classification.INVALID_MEASUREMENT
    elif not controls_valid:
        label = U4Classification.INVALID_MEASUREMENT
    elif not predeclared_heldout_partition_present:
        label = U4Classification.PLUMBING_ONLY
    elif (
        baseline_persistence_confirmed
        and signed_displacement_pattern_confirmed
        and random_direction_specificity_confirmed
        and wrong_site_specificity_confirmed
        and ssim_within_natural_variation
    ):
        label = U4Classification.CAUSAL_PILOT
    elif baseline_persistence_confirmed and (
        random_direction_specificity_confirmed and wrong_site_specificity_confirmed
    ):
        label = U4Classification.CLEAN_NEGATIVE
    else:
        label = U4Classification.INVALID_MEASUREMENT

    return {
        "schema_version": CLASSIFICATION_SCHEMA_VERSION,
        "step": "8.8",
        "classification": label.value,
        "causal_claim_made": label is U4Classification.CAUSAL_PILOT,
        "reasons": reasons,
        "checks": {
            "injection_exact": injection_exact,
            "baseline_persistence_confirmed": baseline_persistence_confirmed,
            "signed_displacement_pattern_confirmed": (
                signed_displacement_pattern_confirmed
            ),
            "random_direction_specificity_confirmed": (
                random_direction_specificity_confirmed
            ),
            "wrong_site_specificity_confirmed": wrong_site_specificity_confirmed,
            "ssim_within_natural_variation": ssim_within_natural_variation,
            "predeclared_heldout_partition_present": (
                predeclared_heldout_partition_present
            ),
            "measurement_valid": measurement_valid,
            "controls_valid": controls_valid,
        },
        "evidence_tables": dict(evidence_tables),
        "outputs_preserved_on_failure": True,
        "retuned_on_test_videos": False,
        "detail": detail,
    }


__all__ = [
    "CLASSIFICATION_SCHEMA_VERSION",
    "DEFAULT_HELDOUT_EVENT_COUNT",
    "DEFAULT_INTENDED_SHIFTS",
    "DEFAULT_RANDOM_CONTROL_COUNT",
    "DEFAULT_SEEDS_PER_CELL",
    "FORBIDDEN_CLIP_FIELDS",
    "HANDOFF_SCHEMA_VERSION",
    "NON_OVERWRITABLE_CONTROL_TYPES",
    "ROLLOUT_BUNDLE_SCHEMA_VERSION",
    "ROLLOUT_MANIFEST_SCHEMA_VERSION",
    "ClipOutcome",
    "ClipResult",
    "ClipSpec",
    "ControlType",
    "DoseSpec",
    "HeldoutEvent",
    "RolloutError",
    "RolloutErrorCode",
    "RolloutRunner",
    "U4Classification",
    "build_control_handoff",
    "build_measurement_handoff",
    "build_rollout_manifest",
    "classify_u4",
    "manifest_hash",
    "validate_rollout_manifest",
]
