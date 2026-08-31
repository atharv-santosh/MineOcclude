"""The capture liveness contract (authority 7.10f, Amendment 3).

Authority v1.5 invalidated a block on "byte-identical consecutive frames beyond
the frozen tolerance". Amendment 3 **withdrew** that rule as unsound, and this
module implements the replacement.

Why the old rule was wrong, concretely:

* P0 deliberately captures a **static settled scene**. Fixed noon, weather
  controlled, zero random ticks, an AI-disabled target held at one placement --
  repeated framebuffer bytes are the *expected* observation.
* An opaque ``L4`` production condition can legitimately render pixel-identical
  frames while a fully hidden target moves behind the wall.

In both cases the correct observation was indistinguishable from a frozen
renderer, so the rule would have thrown away valid science while still failing to
detect the fault it was written for.

Liveness is therefore proven where it is actually observable:

* **tick integrity** -- the server tick advances by exactly one per step, and the
  accepted frames carry complete, unique tick identities;
* **transition probes** -- at points where the image *must* change (target
  present/absent, a wall material change, and a mandatory pre-capture probe) the
  settled framebuffer is required to differ.

``CAPTURE_STALE_FRAME`` is raised only when a tick advanced across a known scene
transition and the settled framebuffer did not change. Frame hashes are recorded
throughout as diagnostics and are never a verdict on their own.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Sequence

from mineocclude.experiment_iii.authority import (
    FRAMEBUFFER_HEIGHT,
    FRAMEBUFFER_WIDTH,
    machine_authority,
)
from mineocclude.experiment_iii.errors import ExperimentIIIError

__all__ = [
    "TRANSITION_KINDS",
    "LivenessProbe",
    "assert_transition_observed",
    "liveness_contract",
    "OBSERVED_EVIDENCE_SOURCE",
    "verify_frame_dimensions",
    "verify_tick_integrity",
    "verify_unit_liveness",
]

#: Authority 7.10f -- the points at which the image must demonstrably change.
TRANSITION_KINDS = (
    "TARGET_PRESENT_TO_ABSENT",
    "TARGET_ABSENT_TO_PRESENT",
    "WALL_MATERIAL_CHANGE",
    "MANDATORY_PRE_CAPTURE_LIVENESS_PROBE",
)


def liveness_contract() -> dict[str, Any]:
    """The frozen contract, read from the authority rather than restated."""
    contract = machine_authority().get("capture_liveness_contract")
    if not contract:
        raise ExperimentIIIError(
            "AUTHORITY_INCOMPLETE",
            "the authority carries no capture_liveness_contract; Amendment 3 is absent",
        )
    return dict(contract)


class LivenessProbe:
    """One observed scene transition and the framebuffer hashes bracketing it."""

    def __init__(
        self,
        kind: str,
        *,
        before_hash: str,
        after_hash: str,
        before_tick: int,
        after_tick: int,
        settled: bool = True,
    ) -> None:
        if kind not in TRANSITION_KINDS:
            raise ExperimentIIIError(
                "CAPTURE_STALE_FRAME",
                f"{kind!r} is not a frozen transition kind {TRANSITION_KINDS}",
            )
        self.kind = kind
        self.before_hash = before_hash
        self.after_hash = after_hash
        self.before_tick = int(before_tick)
        self.after_tick = int(after_tick)
        self.settled = bool(settled)

    @property
    def tick_advanced(self) -> bool:
        return self.after_tick > self.before_tick

    @property
    def framebuffer_changed(self) -> bool:
        return self.before_hash != self.after_hash

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "before_tick": self.before_tick,
            "after_tick": self.after_tick,
            "before_frame_sha256": self.before_hash,
            "after_frame_sha256": self.after_hash,
            "tick_advanced": self.tick_advanced,
            "framebuffer_changed": self.framebuffer_changed,
            "settled": self.settled,
        }


def assert_transition_observed(probe: LivenessProbe) -> dict[str, Any]:
    """The only condition under which repeated bytes are staleness (7.10f)."""
    if not probe.tick_advanced:
        raise ExperimentIIIError(
            "TIMING_CARDINALITY_MISMATCH",
            f"the server tick did not advance across {probe.kind} "
            f"({probe.before_tick} -> {probe.after_tick})",
        )
    if not probe.framebuffer_changed:
        raise ExperimentIIIError(
            "CAPTURE_STALE_FRAME",
            f"the server tick advanced across {probe.kind} but the settled "
            f"framebuffer is byte-identical ({probe.before_hash}); the renderer "
            f"is not presenting the scene",
        )
    return probe.as_dict()


def verify_tick_integrity(ticks: Sequence[int], *, expected: int | None = None) -> dict[str, Any]:
    """Monotone step-one ticks, one accepted frame each, complete and unique."""
    values = [int(tick) for tick in ticks]
    if not values:
        raise ExperimentIIIError(
            "TIMING_CARDINALITY_MISMATCH", "a capture unit recorded no ticks"
        )
    if expected is not None and len(values) != int(expected):
        raise ExperimentIIIError(
            "TIMING_CARDINALITY_MISMATCH",
            f"expected {expected} accepted frames, got {len(values)}",
        )
    if len(set(values)) != len(values):
        duplicates = sorted({t for t in values if values.count(t) > 1})
        raise ExperimentIIIError(
            "TIMING_CARDINALITY_MISMATCH",
            f"duplicated tick identities: {duplicates[:8]}",
        )
    for previous, current in zip(values, values[1:]):
        if current != previous + 1:
            raise ExperimentIIIError(
                "TIMING_CARDINALITY_MISMATCH",
                f"ticks must advance by exactly one; {previous} -> {current}",
            )
    return {
        "accepted_frames": len(values),
        "first_tick": values[0],
        "last_tick": values[-1],
        "monotonic_step_one": True,
        "identities_unique": True,
        "identities_complete": True,
    }


#: A frame record may only be scientific evidence if its tick and dimensions were
#: read from the apparatus. The previous implementation accepted records whose
#: ``tick`` came from ``enumerate`` and whose ``width``/``height`` came from the
#: FRAMEBUFFER_* constants, so ``verify_frame_dimensions`` compared the constants
#: against themselves and ENV_FRAMEBUFFER_SIZE_MISMATCH could never fire.
OBSERVED_EVIDENCE_SOURCE = "OBSERVED_PHYSICAL_EVIDENCE"


def verify_frame_dimensions(frames: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Every framebuffer read succeeded and is exactly 640 x 360."""
    count = 0
    for frame in frames:
        count += 1
        if frame.get("evidence_source") != OBSERVED_EVIDENCE_SOURCE:
            raise ExperimentIIIError(
                "CAPTURE_STALE_FRAME",
                f"the frame at tick {frame.get('tick')} is not marked "
                f"{OBSERVED_EVIDENCE_SOURCE}; framebuffer dimensions and tick "
                f"identity must be read from the apparatus (the PNG header and "
                f"client_tick.jsonl), never restated from the requested "
                f"configuration",
            )
        if not frame.get("read_succeeded", True):
            raise ExperimentIIIError(
                "CAPTURE_STALE_FRAME",
                f"framebuffer read failed at tick {frame.get('tick')}",
            )
        width, height = int(frame["width"]), int(frame["height"])
        if (width, height) != (FRAMEBUFFER_WIDTH, FRAMEBUFFER_HEIGHT):
            raise ExperimentIIIError(
                "ENV_FRAMEBUFFER_SIZE_MISMATCH",
                f"frame at tick {frame.get('tick')} is {width}x{height}, not "
                f"{FRAMEBUFFER_WIDTH}x{FRAMEBUFFER_HEIGHT}",
            )
    if count == 0:
        raise ExperimentIIIError(
            "TIMING_CARDINALITY_MISMATCH", "a capture unit recorded no frames"
        )
    return {"frames": count, "all_640x360": True, "all_reads_succeeded": True}


def verify_unit_liveness(
    *,
    frames: Sequence[Mapping[str, Any]],
    probes: Sequence[LivenessProbe],
    process_alive: bool,
    expected_frames: int | None = None,
    material_transition: bool = False,
) -> dict[str, Any]:
    """The whole 7.10f contract for one capture unit.

    Repeated frame hashes inside the unit are reported as a diagnostic and are
    deliberately **not** a failure: within one settled static state that is the
    expected observation.
    """
    if not process_alive:
        raise ExperimentIIIError(
            "CAPTURE_STALE_FRAME",
            "the capture process did not stay alive for the whole unit",
        )
    tick_report = verify_tick_integrity(
        [int(frame["tick"]) for frame in frames], expected=expected_frames
    )
    dimension_report = verify_frame_dimensions(frames)

    # WALL_MATERIAL_CHANGE is required exactly when the unit actually changed the
    # material. Excluding it unconditionally -- as this did -- meant the frozen
    # probe was never demanded of any unit, and a wall left standing at the
    # previous material would still show present/absent differences and pass every
    # probe that WAS emitted, corrupting all 18 units of that condition.
    required = {kind for kind in TRANSITION_KINDS if kind != "WALL_MATERIAL_CHANGE"}
    if material_transition:
        required.add("WALL_MATERIAL_CHANGE")
    observed_kinds = {probe.kind for probe in probes}
    missing = sorted(required - observed_kinds)
    if "MANDATORY_PRE_CAPTURE_LIVENESS_PROBE" in missing:
        raise ExperimentIIIError(
            "CAPTURE_STALE_FRAME",
            "authority 7.10f requires a controlled pre-capture liveness probe on "
            "every unit; none was recorded",
        )
    if "WALL_MATERIAL_CHANGE" in missing:
        raise ExperimentIIIError(
            "CAPTURE_STALE_FRAME",
            "this unit changed the wall material, and authority 7.10f requires an "
            "explicit pixel-level WALL_MATERIAL_CHANGE probe across that "
            "transition; the arena cache key is a claim about intent, not evidence",
        )
    probe_reports = [assert_transition_observed(probe) for probe in probes]

    hashes = [str(frame["frame_sha256"]) for frame in frames]
    distinct = len(set(hashes))
    return {
        "schema_version": "mineocclude-experiment-iii-capture-liveness-v1",
        "authority_section": "7.10f",
        "process_alive": True,
        "ticks": tick_report,
        "framebuffer": dimension_report,
        "probes": probe_reports,
        "probe_kinds_observed": sorted(observed_kinds),
        "required_probe_kinds": sorted(required),
        "required_probe_kinds_present": sorted(required & observed_kinds),
        "material_transition_probed": "WALL_MATERIAL_CHANGE" in observed_kinds,
        # Diagnostics only. A static settled state legitimately repeats bytes;
        # the withdrawn v1.5 rule treated this as failure and was unsound.
        "distinct_frame_hashes": distinct,
        "repeated_frame_hashes": len(hashes) - distinct,
        "repeated_bytes_within_static_state_is_stale": False,
        "passed": True,
    }
